# Purpose: 감사 스풀 — 큐를 비워 해시 사슬을 잇고 UTC 날짜 파일에 덧붙이며 올림 표지를 적는다.

"""로컬 스풀(표준 라이브러리만).

**비우기(`drain`)** 는 잠금 하나 안에서 큐를 꺼내 순번(`seq`) · 앞 해시(`prev`) · 이 줄
해시(`h`)를 매기고 `<스풀 뿌리>/spool/<UTC날짜>__<inst>.jsonl` 끝에 덧붙인 뒤 fsync 한다.
스크립트 스레드(`app.py` 부트스트랩 뒤)와 동기화 일꾼(고리마다)이 부르고, 이벤트 루프는 부르지
않는다(파일 IO 를 하지 않는다). 큐가 비었으면 파일을 건드리지 않는다.

**스풀 뿌리** 는 기본이 `data/temp/audit` 이고 `configure` 로 바꾼다 — 통합인증을 켠 시험이 저장소
`data/temp/` 에 쓰지 않고 `tmp_path` 에 쓴다(conftest 그물).

**올림 표지** 는 파일 옆 `.shipped` 에 올린 마지막 seq 를 적는다. 스풀 파일은 그 날짜의 일별 파일이
미러에 들어오고 다 올린 뒤에야 지운다(`prune`) — 지난 날짜라도 일별 파일이 오기 전에는 화면이 그
날짜를 읽을 곳이 스풀뿐이다.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from io import FileIO
from pathlib import Path
from typing import Any, Final

from capa_simulation.audit import chain, layout, recorder, text

_LOGGER = logging.getLogger(__name__)

SPOOL_DIR: Final = "spool"
SUFFIX: Final = ".jsonl"
SHIPPED_SUFFIX: Final = ".shipped"

_LOCK = threading.Lock()


@dataclass
class _Chain:
    seq: int = 0
    prev: str = chain.GENESIS
    shipped: int = 0


_ROOT: Path | None = None
_CHAIN = _Chain()


def configure(root: Path | None) -> None:
    """스풀 뿌리를 정한다(`None` 이면 기본 `data/temp/audit`)."""
    global _ROOT
    _ROOT = root


def configured() -> Path | None:
    """`configure` 로 정한 뿌리(정하지 않았으면 `None`)."""
    return _ROOT


def root() -> Path:
    if _ROOT is not None:
        return _ROOT
    from capa_simulation import settings

    return settings.DATA_DIR / "temp" / "audit"


def spool_dir(base: Path | None = None) -> Path:
    return (root() if base is None else base) / SPOOL_DIR


def spool_path(date: str, inst: str, base: Path | None = None) -> Path:
    return spool_dir(base) / f"{date}__{inst}{SUFFIX}"


def parse_spool_name(path: Path) -> tuple[str, str] | None:
    """스풀 파일 이름 → (UTC 날짜, inst)."""
    if not path.name.endswith(SUFFIX):
        return None
    date, sep, inst = path.name[: -len(SUFFIX)].partition("__")
    if not sep or len(date) != 10 or not inst:
        return None
    return date, inst


def reset() -> None:
    """시험 전용 — 사슬 상태를 처음으로 돌린다(뿌리는 그대로)."""
    global _CHAIN
    with _LOCK:
        _CHAIN = _Chain()


# ------------------------------------------------------------------ 비우기
def _append(path: Path, lines: list[dict[str, Any]]) -> None:
    """줄 묶음을 파일 끝에 덧붙이고 fsync 한다(버퍼 없이 — 닫을 때 남은 바이트를 다시 쓰지 않는다).

    쓰다 실패하면(디스크 참 등) 쓰기 전 길이로 되자르고 예외를 올린다 — 반쯤 쓴 꼬리가 다음
    비우기의 첫 줄과 한 줄로 붙어 그 순번이 영영 읽히지 않는 일을 막는다. 되자르기마저 실패해
    꼬리가 남았으면 다음 덧붙이기가 줄바꿈부터 적는다(꼬리 한 줄만 읽히지 않는다).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(chain.dump(line) + "\n" for line in lines).encode("utf-8")
    with path.open("ab", buffering=0) as handle:
        start = os.fstat(handle.fileno()).st_size
        if start and not _ends_with_newline(path, start):
            payload = b"\n" + payload
        try:
            _write_all(handle, payload)
            os.fsync(handle.fileno())
        except BaseException:
            try:
                handle.truncate(start)
            except OSError:
                _LOGGER.exception("감사 스풀의 반쯤 쓴 꼬리를 되자르지 못했습니다.")
            raise


def _write_all(handle: FileIO, payload: bytes) -> None:
    """버퍼 없는 파일에 바이트를 끝까지 적는다(한 번에 다 적지 못할 수 있다)."""
    view = memoryview(payload)
    while view:
        written = handle.write(view)
        if not written:
            raise OSError("감사 스풀에 한 바이트도 적지 못했습니다.")
        view = view[written:]


def _ends_with_newline(path: Path, size: int) -> bool:
    with path.open("rb") as reader:
        reader.seek(size - 1)
        return reader.read(1) == b"\n"


def drain() -> int:
    """큐를 비워 스풀에 적는다. 적은 줄 수. 꺼졌거나 빈 큐면 0(파일 IO 없음).

    꺼낸 줄은 모두 셋 가운데 하나가 된다 — 스풀에 적힘 · 큐 앞으로 되돌림 · 버린 수로 셈
    (`sys_audit_dropped`). 날짜 묶음 하나를 쓰다 실패하면(어떤 예외든) 그 묶음부터의 줄을 큐 앞에
    돌려놓고 사슬은 쓴 데까지만 나아간다 — 빈 순번이 생기지 않는다. 해시를 매길 수 없는 줄(UTF-8 로
    적을 수 없는 글)은 글을 고쳐 다시 매기고, 그래도 안 되면 순번을 쓰지 않고 버린 수로 센다 — 줄
    하나가 묶음 전체를 잃게 하지 않는다.
    """
    if not recorder.enabled():
        return 0
    with _LOCK:
        pending = recorder.take_pending()
        if not pending:
            return 0
        inst = recorder.instance_id()
        groups: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
        seq, prev = _CHAIN.seq, _CHAIN.prev
        lost = 0
        for line in pending:
            date = str(line.get("ts", ""))[:10]
            sealed = _seal(line, seq + 1, prev)
            if sealed is None:
                lost += 1
                continue
            seq, prev = sealed["seq"], sealed["h"]
            if not groups or groups[-1][0] != date:
                groups.append((date, [], []))
            groups[-1][1].append(sealed)
            groups[-1][2].append(line)
        recorder.note_dropped(lost)
        written = 0
        for index, (date, sealed_lines, _) in enumerate(groups):
            try:
                _append(spool_path(date, inst), sealed_lines)
            except Exception:  # noqa: BLE001 — 어떤 실패든 꺼낸 줄을 잃지 않는다
                _LOGGER.exception("감사 스풀에 적지 못했습니다.")
                rest = [line for _, _, group in groups[index:] for line in group]
                recorder.requeue_front(rest)
                break
            last = sealed_lines[-1]
            _CHAIN.seq, _CHAIN.prev = int(last["seq"]), str(last["h"])
            written += len(sealed_lines)
        return written


def _seal(line: dict[str, Any], seq: int, prev: str) -> dict[str, Any] | None:
    """해시를 매긴 줄. 못 매기면 글의 짝 없는 서로게이트를 고쳐 한 번 더, 그래도 안 되면 `None`."""
    try:
        return chain.seal(line, seq=seq, prev=prev)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("감사 줄에 해시를 매기지 못해 글을 고쳐 다시 매깁니다.")
    try:
        repaired = _repaired(line)
        if not isinstance(repaired, dict):
            return None
        return chain.seal(repaired, seq=seq, prev=prev)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("감사 줄을 적을 수 없어 버립니다.")
        return None


def _repaired(value: object) -> object:
    if isinstance(value, str):
        return text.without_surrogates(value)
    if isinstance(value, dict):
        return {_repaired(key): _repaired(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_repaired(item) for item in value]
    return value


def last_sealed() -> tuple[int, str]:
    """이 프로세스가 스풀에 적은 마지막 (seq, h)."""
    with _LOCK:
        return _CHAIN.seq, _CHAIN.prev


# ------------------------------------------------------------------ 올림 표지
def shipped_seq(path: Path) -> int:
    marker = path.with_name(path.name + SHIPPED_SUFFIX)
    try:
        return int(marker.read_text(encoding="ascii").strip() or "0")
    except (OSError, ValueError):
        return 0


def mark_shipped(path: Path, seq: int) -> None:
    """올린 마지막 seq 를 적는다(바꿔 쓰기 — 반쯤 쓴 표지가 남지 않게)."""
    marker = path.with_name(path.name + SHIPPED_SUFFIX)
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(str(seq), encoding="ascii")
    os.replace(temporary, marker)
    parsed = parse_spool_name(path)
    if parsed is not None and parsed[1] == recorder.instance_id():
        with _LOCK:
            _CHAIN.shipped = max(_CHAIN.shipped, seq)


def unshipped_count() -> int:
    """이 프로세스의 아직 올리지 않은 줄(큐 + 스풀) — 「감사 미전송 n줄」. 메모리만 읽는다."""
    with _LOCK:
        drained = _CHAIN.seq - _CHAIN.shipped
    return max(drained, 0) + recorder.pending_count()


def spool_files(base: Path | None = None) -> list[Path]:
    folder = spool_dir(base)
    try:
        return sorted(path for path in folder.iterdir() if parse_spool_name(path) is not None)
    except OSError:
        return []


def read_lines(path: Path) -> list[dict[str, Any]]:
    try:
        return layout.parse_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def unshipped_lines(path: Path) -> list[dict[str, Any]]:
    """이 스풀 파일에서 아직 올리지 않은 줄(seq 차례). 순번이 정수가 아닌 줄은 건너뛴다."""
    done = shipped_seq(path)
    numbered = [(chain.seq_of(line), line) for line in read_lines(path)]
    lines = [(seq, line) for seq, line in numbered if seq is not None and seq > done]
    return [line for _, line in sorted(lines, key=lambda item: item[0])]


def prune(daily_dates: Iterable[str], base: Path | None = None) -> list[Path]:
    """일별 파일이 미러에 든 날짜의 스풀 가운데 다 올린 것을 지운다. 지운 파일 목록."""
    covered = set(daily_dates)
    removed: list[Path] = []
    for path in spool_files(base):
        parsed = parse_spool_name(path)
        if parsed is None or parsed[0] not in covered or unshipped_lines(path):
            continue
        try:
            path.unlink()
            path.with_name(path.name + SHIPPED_SUFFIX).unlink(missing_ok=True)
        except OSError:
            continue
        removed.append(path)
    return removed
