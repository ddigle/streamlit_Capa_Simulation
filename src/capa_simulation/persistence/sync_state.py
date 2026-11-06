# Purpose: DB 옆 사이드카에 미반영 변경 표시를, 데이터 폴더의 한 파일에 게시 상태를 기록한다.

"""동기화 상태를 DB 파일 옆 작은 JSON 에 남기는 계층.

상태를 DuckDB 안에 넣지 않는다 — 그 파일 자체가 동기화 대상이라 순환이 된다. 메모리에도
두지 않는다: 프로세스가 죽으면 "이 PC 에만 있는 변경" 표시가 사라지고, 다음 기동의 받기가
그 리비전을 백업 없이 덮는다.

파일은 둘로 나뉜다.

- **DB 별 사이드카**(`<db>.sync.json`) — 변경 번호와 심장박동. 저장마다 쓴다.
- **게시 상태 한 파일**(`sync_generation.json`) — 두 DB 가 어느 세대에서 왔는지(`base`), 올리는 중인
  포인터(`pending`), 게시하지 못한 세대(`unpublished`), 넘긴 표지(`handed_over_utc`). 게시 단위가 두
  DB 한 쌍이라 파일도 하나다. DB 별로 나누면 두 쓰기 사이의 실패가 스스로 「세대 모름」 을 만든다.

`_write_transaction` 이 COMMIT 직후에 부르는 유일한 대상이라 **Streamlit·aws·io 를 import
하지 않는다.** 그리고 `enable()` 되지 않은 환경(개발 PC·CI)에서는 파일을 하나도 만들지
않는다 — 지금 동작을 한 글자도 바꾸지 않기 위해서다.

읽지 못하는 사이드카는 "변경 있음" 으로 본다(`treat_as_dirty`). 모르면 올리는 쪽이 안전하다.

변경 표시는 불리언 하나가 아니라 **세대 번호 둘**이다 — `dirty_seq`(저장마다 1 오름)와
`cleared_seq`(올라간 스냅샷이 담은 마지막 번호). 지우기는 「스냅샷 직전에 읽은 번호와 지금 번호가
같을 때만」이다(`read_dirty_mark` → `clear_dirty`). 불리언으로만 두면 올리는 동안 들어온 저장의
표시까지 지워, 그 저장이 다음 올리기에서 빠진다.

사이드카 schema 는 1 그대로 두고 칸만 더한다. 옛 코드는 schema 가 1 이 아니면 None 으로 읽고 빈
상태로 덮는다. 옛 코드는 모르는 칸을 버리고 `dirty` 불리언만 쓰므로, 새 코드는 두 번호와 그
불리언(`dirty = dirty_seq > cleared_seq`)을 늘 함께 맞추고, 번호가 없는 파일은 불리언에서 세운다.

**시각과 깨우기는 메모리다.** 일꾼은 이 모듈이 적어 둔 첫 표시 · 마지막 표시 시각(단조 시계)으로
모으는 시간을 재고, 표시 때 리스너로 깨어난다. 리스너는 `_STATE_LOCK` 을 놓은 뒤 부른다 — 저장
경로가 일꾼을 기다리지 않게. 첫 미반영 시각을 일꾼 밖(여기)에 두는 까닭은 일꾼이 멈춰도 그 값이
함께 멈추지 않게 하려는 것이다 — 멈춤을 알아채는 판정이 멈춘 쪽의 값을 읽으면 못 본다.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from capa_simulation.services.object_storage_manifest import DATASET_NAMES, DatasetName

SIDECAR_SUFFIX: Final = ".sync.json"
SIDECAR_SCHEMA_VERSION: Final = 1
GENERATION_FILENAME: Final = "sync_generation.json"
GENERATION_SCHEMA_VERSION: Final = 1
HEARTBEAT_INTERVAL_SECONDS: Final = 10.0
HEARTBEAT_STALE_SECONDS: Final = 90.0

# managed 모드에서 boot 가 한 번 등록한다. 비어 있으면 이 모듈은 아무 일도 하지 않는다.
_ENABLED: dict[Path, DatasetName] = {}
# 심장박동을 10초에 한 번만 쓰기 위한 마지막 기록 시각(단조 시계).
_LAST_HEARTBEAT: dict[Path, float] = {}
# 사이드카 읽기-고치기-쓰기를 한 덩어리로 묶는다. Streamlit 은 세션마다 스크립트를 **같은
# 프로세스의 다른 스레드**에서 돌리므로, 커밋의 `mark_dirty` 와 업로드의 `clear_dirty` 가
# 겹치면 나중에 쓰는 쪽이 앞의 변경을 통째로 덮어 dirty 표시가 사라진다. 파일 쓰기 자체는
# `os.replace` 라 원자적이지만, 원자적이어야 하는 것은 읽기부터 쓰기까지다.
_STATE_LOCK = threading.Lock()
# 쓰지 못한 변경 표시. `_update` 는 저장 경로로 예외를 올리지 않으므로 대신 여기 남긴다 — 경로마다
# 지금까지 못 쓴 표시의 누적 수(비교 후 지우기의 대조 값)와, 아직 파일에 옮기지 못한 수·마지막 오류.
_UNSAVED_MARKS: dict[Path, int] = {}
_PENDING_MARKS: dict[Path, int] = {}
_LAST_WRITE_ERROR: dict[Path, str] = {}
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncState:
    """한 DB 의 변경 표시."""

    dataset: DatasetName
    dirty: bool = False
    last_error: str | None = None
    instance_id: str | None = None
    heartbeat_utc: str | None = None
    # 저장마다 1 오르는 변경 번호와, 올라간 스냅샷이 담은 마지막 번호. `dirty` 는 둘의 비교다.
    dirty_seq: int = 0
    cleared_seq: int = 0


@dataclass(frozen=True)
class DirtyMark:
    """스냅샷 직전에 읽어 두는 변경 표시. 게시 뒤 지금 값과 같을 때만 지운다.

    `unsaved` 는 이 프로세스가 사이드카에 쓰지 못한 표시의 누적 수다. 디스크가 차 표시를 못
    쓰면 `dirty_seq` 는 그대로라, 번호만 견주면 그 저장을 담지 않은 스냅샷이 표시를 지운다.
    """

    dirty_seq: int
    unsaved: int


@dataclass(frozen=True)
class PendingPublish:
    """포인터를 PUT 하기 **앞에** 적는 칸. 그 PUT 의 답이 끊겨도 다음 회차가 결과를 가린다.

    `pointer_json` 을 그대로 들고 있어 다시 PUT 할 때 스냅샷을 다시 올리지 않고 같은 키로 쓴다.
    `observed` 는 이번 세대가 실제로 담은 DB 의 변경 번호다 — 이어 적은 DB 는 칸이 없어 표시를
    건드리지 않는다(그 사이 들어온 저장의 표시를 지우지 않는다).
    """

    pointer_key: str
    pointer_json: str
    observed: Mapping[DatasetName, DirtyMark]


@dataclass(frozen=True)
class UnpublishedGeneration:
    """스냅샷은 올라갔는데 포인터를 게시하지 못한 세대. 이 칸이 곧 복구 수단이다."""

    pointer_json: str
    reason: str
    observed: Mapping[DatasetName, DirtyMark]


@dataclass(frozen=True)
class GenerationState:
    """두 DB 한 쌍의 게시 상태."""

    base_pointer_key: str | None = None
    base_seq: int | None = None
    # 이어 적을 멤버를 GET 없이 읽으려고 포인터 본문을 그대로 든다.
    base_pointer_json: str | None = None
    base_synced_at_utc: str | None = None
    pending: PendingPublish | None = None
    unpublished: UnpublishedGeneration | None = None
    # 사내 PC 가 정본을 운영 앱에 넘긴 시각. 그 뒤 그 PC 의 쓰기 명령은 거절된다.
    handed_over_utc: str | None = None


@dataclass(frozen=True)
class GenerationRead:
    """게시 상태 파일을 읽은 결과. 없음과 깨짐을 가른다 — 깨진 파일은 「모름」 이 아니다."""

    state: GenerationState
    exists: bool
    readable: bool


@dataclass(frozen=True)
class MarkClock:
    """이 프로세스의 표시 시각(단조 시계).

    `first`·`last` 는 아직 어느 회차도 들고 가지 않은 표시, `carrying` 은 도는 회차가 들고 간 표시의
    첫 시각이다. 첫 미반영 시각은 둘 가운데 앞선 쪽이다(`oldest`).
    """

    first: float | None = None
    last: float | None = None
    carrying: float | None = None

    @property
    def oldest(self) -> float | None:
        moments = [moment for moment in (self.first, self.carrying) if moment is not None]
        return min(moments) if moments else None


def sidecar_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + SIDECAR_SUFFIX)


def generation_path(database_path: Path) -> Path:
    """게시 상태 파일 자리 — 두 DB 가 함께 있는 폴더."""
    return Path(database_path).with_name(GENERATION_FILENAME)


def _registry_key(database_path: Path) -> Path:
    """등록 대조에만 쓰는 정규화 경로.

    저장소는 `database_path.resolve()` 를 들고 있고 부트는 설정에 적힌 경로를 그대로 넘긴다.
    정규화하지 않으면 같은 파일인데 키가 달라 `_update` 가 조용히 아무 일도 하지 않는다 —
    변경 표시가 사라지고 다음 push 가 "올릴 것 없음" 으로 끝난다.
    """
    try:
        return Path(database_path).resolve()
    except OSError:
        return Path(database_path)


def enable(paths: Mapping[Path, DatasetName]) -> None:
    """managed 모드의 등록. 앱은 `sync_boot` 가 프로세스에 한 번, 스크립트는 명령마다 부른다.

    등록 내용이 그대로면 아무것도 건드리지 않는다. `clear()` 와 `update()` 사이에는
    `_ENABLED` 가 비어 있고, 그 틈에 다른 세션 스레드가 COMMIT 을 끝내고 `mark_dirty` 를
    부르면 `_update` 가 등록을 못 찾아 조용히 돌아간다 — 변경 표시가 사라지고 다음 push 가
    "올릴 것 없음" 으로 끝난다. rerun 마다 그 틈이 열릴 이유가 없다.
    """
    registry = {_registry_key(path): dataset for path, dataset in paths.items()}
    if registry == _ENABLED:
        return
    _ENABLED.clear()
    _ENABLED.update(registry)


def is_enabled(database_path: Path) -> bool:
    return _registry_key(database_path) in _ENABLED


def clear_all() -> None:
    """테스트 전용. 등록과 심장박동 · 쓰지 못한 표시 · 시각 · 리스너를 비운다."""
    global _MARK_FIRST, _MARK_LAST, _MARK_CARRYING, _UPLOAD_REQUESTED, _LISTENER
    _ENABLED.clear()
    _LAST_HEARTBEAT.clear()
    _UNSAVED_MARKS.clear()
    _PENDING_MARKS.clear()
    _LAST_WRITE_ERROR.clear()
    with _CLOCK_LOCK:
        _MARK_FIRST = None
        _MARK_LAST = None
        _MARK_CARRYING = None
        _UPLOAD_REQUESTED = False
        _LISTENER = None


# --------------------------------------------------------------------------- 시각 · 깨우기
_CLOCK_LOCK = threading.Lock()
_MARK_FIRST: float | None = None
_MARK_LAST: float | None = None
_MARK_CARRYING: float | None = None
_UPLOAD_REQUESTED = False
_LISTENER: Callable[[], None] | None = None


def _monotonic() -> float:
    return time.monotonic()


def set_listener(listener: Callable[[], None] | None) -> None:
    """일꾼이 등록한다. 표시 · 올리기 요청 때 부른다 — 막히지 않는 함수만 준다."""
    global _LISTENER
    with _CLOCK_LOCK:
        _LISTENER = listener


def _notify() -> None:
    """`_STATE_LOCK` 밖에서 부른다. 리스너가 실패해도 저장 경로로 올리지 않는다."""
    with _CLOCK_LOCK:
        listener = _LISTENER
    if listener is None:
        return
    try:
        listener()
    except Exception:  # noqa: BLE001 — 깨우기 실패는 일꾼의 주기적 재확인이 만회한다
        _LOGGER.exception("동기화 일꾼을 깨우지 못했습니다.")


def _note_mark() -> None:
    global _MARK_FIRST, _MARK_LAST
    now = _monotonic()
    with _CLOCK_LOCK:
        if _MARK_FIRST is None:
            _MARK_FIRST = now
        _MARK_LAST = now


def mark_clock() -> MarkClock:
    with _CLOCK_LOCK:
        return MarkClock(first=_MARK_FIRST, last=_MARK_LAST, carrying=_MARK_CARRYING)


def note_leftover_marks() -> None:
    """파일에는 변경이 남았는데 이 프로세스의 시각이 없을 때 — 시작 때 남은 표시, 놓친 깨우기."""
    with _CLOCK_LOCK:
        if _MARK_FIRST is not None or _MARK_CARRYING is not None:
            return
    _note_mark()


def begin_cycle() -> None:
    """회차가 지금까지의 표시를 들고 간다. 그 뒤의 표시는 새로 센다."""
    global _MARK_FIRST, _MARK_LAST, _MARK_CARRYING
    with _CLOCK_LOCK:
        moments = [item for item in (_MARK_FIRST, _MARK_CARRYING) if item is not None]
        _MARK_CARRYING = min(moments) if moments else None
        _MARK_FIRST = None
        _MARK_LAST = None


def end_cycle(*, carried: bool) -> None:
    """회차가 끝났다. `carried` 면 들고 간 표시가 정본에 닿았고, 아니면 다시 미반영으로 돌린다."""
    global _MARK_FIRST, _MARK_LAST, _MARK_CARRYING
    with _CLOCK_LOCK:
        if not carried and _MARK_CARRYING is not None:
            _MARK_FIRST = (
                _MARK_CARRYING if _MARK_FIRST is None else min(_MARK_FIRST, _MARK_CARRYING)
            )
            _MARK_LAST = _MARK_FIRST if _MARK_LAST is None else _MARK_LAST
        _MARK_CARRYING = None


def request_upload() -> None:
    """공식 발행 COMMIT 뒤에 부른다 — 모으지 않고 바로 올린다. 등록이 없으면 아무 일도 없다."""
    global _UPLOAD_REQUESTED
    if not _ENABLED:
        return
    with _CLOCK_LOCK:
        _UPLOAD_REQUESTED = True
    _notify()


def take_upload_request() -> bool:
    global _UPLOAD_REQUESTED
    with _CLOCK_LOCK:
        requested = _UPLOAD_REQUESTED
        _UPLOAD_REQUESTED = False
    return requested


def upload_requested() -> bool:
    """요청을 지우지 않고 본다 — 정리가 낱개 사이에 물러날지 볼 때."""
    with _CLOCK_LOCK:
        return _UPLOAD_REQUESTED


# --------------------------------------------------------------------------- 사이드카
def read_state(database_path: Path) -> SyncState | None:
    """사이드카를 읽는다. 없거나 깨졌으면 None — 호출자는 `treat_as_dirty` 로 판단한다."""
    path = sidecar_path(database_path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SIDECAR_SCHEMA_VERSION:
        return None
    dataset = payload.get("dataset")
    if dataset not in ("simulation", "equipment"):
        return None
    counters = ("dirty", "dirty_seq", "cleared_seq")
    known = {
        field: payload.get(field)
        for field in SyncState.__dataclass_fields__
        if field != "dataset" and field not in counters
    }
    dirty, dirty_seq, cleared_seq = _dirty_counters(payload)
    return SyncState(
        dataset=dataset, dirty=dirty, dirty_seq=dirty_seq, cleared_seq=cleared_seq, **known
    )


def _dirty_counters(payload: Mapping[str, Any]) -> tuple[bool, int, int]:
    """(dirty, dirty_seq, cleared_seq). 옛 코드가 쓴 파일에는 번호가 없어 불리언에서 세운다.

    둘이 어긋나면 「변경 있음」 쪽을 따른다 — 모르면 올리는 쪽이 안전하다.
    """
    flag = bool(payload.get("dirty"))
    dirty_seq = payload.get("dirty_seq")
    cleared_seq = payload.get("cleared_seq")
    if (
        not isinstance(dirty_seq, int)
        or not isinstance(cleared_seq, int)
        or isinstance(dirty_seq, bool)
        or isinstance(cleared_seq, bool)
        or cleared_seq < 0
        or dirty_seq < cleared_seq
    ):
        return flag, (1 if flag else 0), 0
    if flag and dirty_seq == cleared_seq:
        dirty_seq = cleared_seq + 1
    return flag or dirty_seq > cleared_seq, dirty_seq, cleared_seq


def _write_json_atomically(path: Path, text: str) -> None:
    """임시파일에 쓰고 바꿔치기한다. 중간에 죽어도 반쪽 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), prefix=path.name + ".", delete=False
    )
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except OSError:
        Path(handle.name).unlink(missing_ok=True)
        raise


def write_state(database_path: Path, state: SyncState) -> None:
    path = sidecar_path(database_path)
    payload = {"schema": SIDECAR_SCHEMA_VERSION, **asdict(state)}
    _write_json_atomically(path, json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _registered_dataset(database_path: Path) -> DatasetName | None:
    return _ENABLED.get(_registry_key(database_path))


def _mutate(
    database_path: Path,
    dataset: DatasetName,
    change: Callable[[SyncState], SyncState],
    *,
    fold_pending: bool = True,
) -> SyncState:
    """읽고 고쳐 쓴다. 호출자가 `_STATE_LOCK` 을 쥔 채 부르고, 실패는 그대로 올린다.

    앞서 쓰지 못한 변경 표시가 있으면 이번 쓰기에 함께 옮긴다(`fold_pending`) — 디스크가 돌아온
    다음 쓰기가 놓친 표시를 되살린다. 그 표시를 이미 담은 쓰기(받기·기준 정하기, 그대로인 비교 후
    지우기)는 옮기지 않고 버린다.
    """
    path = Path(database_path)
    key = _registry_key(path)
    state = read_state(path) or SyncState(dataset=dataset)
    updated = change(state)
    pending = _PENDING_MARKS.get(key, 0) if fold_pending else 0
    if pending:
        updated = _with_dirty_seq(updated, updated.dirty_seq + pending)
    write_state(path, updated)
    _PENDING_MARKS.pop(key, None)
    _LAST_WRITE_ERROR.pop(key, None)
    return updated


def _with_dirty_seq(state: SyncState, dirty_seq: int) -> SyncState:
    return replace(state, dirty_seq=dirty_seq, dirty=dirty_seq > state.cleared_seq)


def _remember_write_failure(database_path: Path, action: str, exc: OSError) -> None:
    message = f"{action} 기록을 쓰지 못했습니다: {exc}"
    _LAST_WRITE_ERROR[_registry_key(database_path)] = message
    _LOGGER.warning("동기화 사이드카 %s — %s", sidecar_path(Path(database_path)), message)


def _update(database_path: Path, **changes: object) -> None:
    """등록된 경로에만 쓴다. 실패는 저장 경로로 올리지 않고 로그와 `last_write_error` 로 남긴다."""
    path = Path(database_path)
    dataset = _registered_dataset(path)
    if dataset is None:
        return
    try:
        with _STATE_LOCK:
            _mutate(path, dataset, lambda state: replace(state, **changes))  # type: ignore[arg-type]
    except OSError as exc:
        _remember_write_failure(path, "동기화 상태", exc)


def mark_dirty(database_path: Path) -> None:
    """쓰기 트랜잭션이 COMMIT 된 직후, 그 쓰기 잠금을 놓기 전에 부른다. 변경 번호를 1 올린다.

    사이드카를 쓰지 못해도 저장은 성공해야 한다. 대신 못 쓴 표시를 프로세스에 세어 두고
    (`treat_as_dirty` 가 그것도 「변경 있음」 으로 본다) 경고 로그를 남긴다. 그 수가 비교 후
    지우기의 대조 값에 들어가므로, 그 사이 뜬 스냅샷이 이 저장의 표시를 지우지 못한다.
    """
    path = Path(database_path)
    dataset = _registered_dataset(path)
    if dataset is None:
        return
    with _STATE_LOCK:
        try:
            _mutate(path, dataset, lambda state: _with_dirty_seq(state, state.dirty_seq + 1))
        except OSError as exc:
            key = _registry_key(path)
            _UNSAVED_MARKS[key] = _UNSAVED_MARKS.get(key, 0) + 1
            _PENDING_MARKS[key] = _PENDING_MARKS.get(key, 0) + 1
            _remember_write_failure(path, "변경 표시", exc)
    _note_mark()
    _notify()


def read_dirty_mark(database_path: Path) -> DirtyMark:
    """스냅샷을 뜨기 **직전**에 읽는다. 사이드카가 없거나 깨졌으면 번호 0 으로 본다."""
    path = Path(database_path)
    with _STATE_LOCK:
        state = read_state(path)
        return DirtyMark(
            dirty_seq=0 if state is None else state.dirty_seq,
            unsaved=_UNSAVED_MARKS.get(_registry_key(path), 0),
        )


def clear_dirty(
    database_path: Path, *, observed: DirtyMark, dataset: DatasetName | None = None
) -> bool:
    """게시가 끝난 뒤 표시를 지운다 — 스냅샷 직전 값 그대로일 때만 전부 지운다.

    돌려주는 값은 표시를 다 지웠는지다. 그 사이 들어온 저장이 있으면 「변경 있음」 을 남겨 다음
    올리기가 그 저장을 싣는다. 등록과 무관하게 쓰고(스크립트도 부른다) 쓰기 실패는 그대로 올린다.
    """
    path = Path(database_path)
    owner = dataset or _registered_dataset(path) or _dataset_of(path)
    key = _registry_key(path)
    with _STATE_LOCK:
        state = read_state(path) or SyncState(dataset=owner)
        unchanged = (
            state.dirty_seq == observed.dirty_seq and _UNSAVED_MARKS.get(key, 0) == observed.unsaved
        )
        dirty_seq = state.dirty_seq
        if unchanged:
            cleared_seq = dirty_seq
        else:
            cleared_seq = max(state.cleared_seq, min(observed.dirty_seq, dirty_seq))
            if dirty_seq <= cleared_seq:
                # 번호는 그대로인데 그 사이 못 쓴 표시가 있다 — 그 저장은 이 스냅샷에 없을 수 있다.
                dirty_seq = cleared_seq + 1
        updated = replace(
            state,
            dataset=dataset or state.dataset,
            dirty_seq=dirty_seq,
            cleared_seq=cleared_seq,
            dirty=dirty_seq > cleared_seq,
            last_error=None,
        )
        # 그대로면 앞서 못 쓴 표시도 이 스냅샷이 담았다(표시는 COMMIT 뒤라 그 커밋이 먼저다).
        _mutate(path, owner, lambda _state: updated, fold_pending=not unchanged)
    return unchanged


def adopt_clean(database_path: Path, *, dataset: DatasetName) -> None:
    """파일이 어느 세대 자체가 되었다(받았다) — 변경 표시를 모두 지운다. 앞선 못 쓴 표시도 버린다.

    읽기부터 쓰기까지 `_STATE_LOCK` 안이다 — 밖에서 덮으면 그 사이 들어온 표시를 옛 내용으로 지운다.
    """

    def change(state: SyncState) -> SyncState:
        return replace(state, dataset=dataset, dirty=False, cleared_seq=state.dirty_seq)

    with _STATE_LOCK:
        _mutate(database_path, dataset, change, fold_pending=False)


def adopt_dirty(database_path: Path, *, dataset: DatasetName) -> None:
    """사람이 로컬 파일을 기준으로 삼았다 — 다음 push 가 이 파일을 올리게 표시를 세운다."""

    def change(state: SyncState) -> SyncState:
        return _with_dirty_seq(
            replace(state, dataset=dataset), max(state.dirty_seq, state.cleared_seq) + 1
        )

    with _STATE_LOCK:
        _mutate(database_path, dataset, change, fold_pending=False)


def record_error(database_path: Path, message: str | None) -> None:
    _update(database_path, last_error=message)


def unsaved_mark_error(database_path: Path) -> str | None:
    """이 프로세스가 마지막으로 사이드카를 쓰지 못한 까닭. 다음에 쓰는 데 성공하면 None 이다."""
    return _LAST_WRITE_ERROR.get(_registry_key(Path(database_path)))


def touch_heartbeat(database_path: Path, *, instance_id: str) -> None:
    """살아 있음을 알린다. 10초에 한 번만 실제로 쓴다 — rerun 마다 쓸 이유가 없다."""
    path = Path(database_path)
    if _registry_key(path) not in _ENABLED:
        return
    now = time.monotonic()
    last = _LAST_HEARTBEAT.get(path)
    if last is not None and now - last < HEARTBEAT_INTERVAL_SECONDS:
        return
    _LAST_HEARTBEAT[path] = now
    _update(path, instance_id=instance_id, heartbeat_utc=utc_now_text())


def live_instance(database_path: Path, *, exclude: str | None = None) -> str | None:
    """다른 인스턴스가 살아 있으면 그 id. 90초 넘게 조용하면 죽은 것으로 본다."""
    state = read_state(Path(database_path))
    if state is None or not state.instance_id or not state.heartbeat_utc:
        return None
    if exclude is not None and state.instance_id == exclude:
        return None
    beat = _parse_utc(state.heartbeat_utc)
    if beat is None:
        return None
    if datetime.now(timezone.utc) - beat > timedelta(seconds=HEARTBEAT_STALE_SECONDS):
        return None
    return state.instance_id


def treat_as_dirty(database_path: Path) -> bool:
    """올려야 하는지. **사이드카를 읽지 못하면 True** — 모르면 올리는 쪽이 안전하다."""
    path = Path(database_path)
    if _PENDING_MARKS.get(_registry_key(path), 0):
        # 이 프로세스가 표시를 못 쓴 저장이 있다. 파일이 「변경 없음」 이어도 믿지 않는다.
        return True
    state = read_state(path)
    if state is None:
        return True
    return state.dirty


def sidecar_exists(database_path: Path) -> bool:
    """사이드카 파일이 있는가 — 받기 판정이 「없음」 과 「깨짐」 을 가른다."""
    return sidecar_path(Path(database_path)).exists()


def has_pending_marks(paths: Iterable[Path]) -> bool:
    """이 프로세스가 사이드카에 옮기지 못한 저장이 있는가. 파일을 읽지 않는다."""
    return any(_PENDING_MARKS.get(_registry_key(Path(path)), 0) for path in paths)


# --------------------------------------------------------------------------- 게시 상태
def _mark_payload(marks: Mapping[DatasetName, DirtyMark]) -> dict[str, dict[str, int]]:
    return {name: asdict(mark) for name, mark in marks.items()}


def _marks_from(raw: object) -> dict[DatasetName, DirtyMark]:
    if not isinstance(raw, dict):
        raise ValueError("observed 칸이 객체가 아닙니다.")
    marks: dict[DatasetName, DirtyMark] = {}
    for name in DATASET_NAMES:
        item = raw.get(name)
        if isinstance(item, dict):
            marks[name] = DirtyMark(int(item["dirty_seq"]), int(item["unsaved"]))
    return marks


def _pending_from(raw: object) -> PendingPublish | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("pending 칸이 객체가 아닙니다.")
    return PendingPublish(
        pointer_key=str(raw["pointer_key"]),
        pointer_json=str(raw["pointer_json"]),
        observed=_marks_from(raw.get("observed")),
    )


def _unpublished_from(raw: object) -> UnpublishedGeneration | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("unpublished 칸이 객체가 아닙니다.")
    return UnpublishedGeneration(
        pointer_json=str(raw["pointer_json"]),
        reason=str(raw["reason"]),
        observed=_marks_from(raw.get("observed")),
    )


def _text_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def load_generation(path: Path) -> GenerationRead:
    """게시 상태 파일을 읽는다. 없음(새 디스크)과 깨짐을 가른다."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return GenerationRead(GenerationState(), exists=False, readable=True)
    except (OSError, UnicodeDecodeError):
        return GenerationRead(GenerationState(), exists=True, readable=False)
    try:
        payload: Any = json.loads(text)
        if not isinstance(payload, dict) or payload.get("schema") != GENERATION_SCHEMA_VERSION:
            raise ValueError("게시 상태 파일 꼴이 아닙니다.")
        base_seq = payload.get("base_seq")
        state = GenerationState(
            base_pointer_key=_text_or_none(payload.get("base_pointer_key")),
            base_seq=None if base_seq is None else int(base_seq),
            base_pointer_json=_text_or_none(payload.get("base_pointer_json")),
            base_synced_at_utc=_text_or_none(payload.get("base_synced_at_utc")),
            pending=_pending_from(payload.get("pending")),
            unpublished=_unpublished_from(payload.get("unpublished")),
            handed_over_utc=_text_or_none(payload.get("handed_over_utc")),
        )
    except (ValueError, TypeError, KeyError):
        return GenerationRead(GenerationState(), exists=True, readable=False)
    return GenerationRead(state, exists=True, readable=True)


def read_generation(path: Path) -> GenerationState:
    """게시 상태. 없거나 깨졌으면 빈 상태다 — 가를 때는 `load_generation`."""
    return load_generation(path).state


def write_generation(path: Path, state: GenerationState) -> None:
    """임시파일에 쓰고 바꿔치기한다. 실패는 그대로 올린다 — 게시 차례가 그것을 알아야 한다."""
    payload = {
        "schema": GENERATION_SCHEMA_VERSION,
        "base_pointer_key": state.base_pointer_key,
        "base_seq": state.base_seq,
        "base_pointer_json": state.base_pointer_json,
        "base_synced_at_utc": state.base_synced_at_utc,
        "pending": None
        if state.pending is None
        else {
            "pointer_key": state.pending.pointer_key,
            "pointer_json": state.pending.pointer_json,
            "observed": _mark_payload(state.pending.observed),
        },
        "unpublished": None
        if state.unpublished is None
        else {
            "pointer_json": state.unpublished.pointer_json,
            "reason": state.unpublished.reason,
            "observed": _mark_payload(state.unpublished.observed),
        },
        "handed_over_utc": state.handed_over_utc,
    }
    _write_json_atomically(
        Path(path), json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    )


def with_base(
    state: GenerationState, *, pointer_key: str, seq: int, pointer_json: str
) -> GenerationState:
    """base 를 그 세대로 옮기고 올리는 중 · 미게시 칸을 비운 상태. 넘긴 표지는 그대로다."""
    return replace(
        state,
        base_pointer_key=pointer_key,
        base_seq=seq,
        base_pointer_json=pointer_json,
        base_synced_at_utc=utc_now_text(),
        pending=None,
        unpublished=None,
    )


def _dataset_of(database_path: Path) -> DatasetName:
    """경로가 어느 DB 인지. 설비 DB 만 이름이 다르고 나머지는 시뮬레이션으로 본다."""
    return "equipment" if "equipment" in Path(database_path).name else "simulation"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
