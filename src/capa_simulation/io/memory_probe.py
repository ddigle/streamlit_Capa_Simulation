# Purpose: 로그인 하위 프로세스 앞뒤의 메모리 · 하위 최고 RSS 와 띄우기 앞 프로세스 단서를 읽는다.

"""메모리 · 프로세스 단서 — 자동 로그인 하위 프로세스가 바깥 신호(SIGKILL)로 끝났을 때 가를 값.

`io/bdq_login.attempt_login` 이 하위 프로세스를 띄우기 바로 앞과 끝난 바로 뒤에 한 번씩 읽고
(`read`), 하위가 도는 동안 그 하위의 최고 RSS 를 되풀이해 읽어(`process_peak_bytes` — 가장 큰 값을
쥔다) 셋을 MiB · 수로 접어(`child_memory`) 진단(`container_start_report.ChildMemory`)에 싣는다. 앞뒤
OOM 종료 수가 다르면 그 사이 cgroup 이 프로세스를 죽인 것이다 — 진단 줄이 그 수를 보이고, 이 모듈은
판정하지 않는다.

- **cgroup** — v2 면 뿌리의 `memory.current` · `memory.max`(「max」 는 한도 없음) · `memory.events`
  의 `oom_kill` 줄, v1 이면 `memory/` 아래 `memory.usage_in_bytes` · `memory.limit_in_bytes`(아주 큰
  값은 한도 없음) · `memory.oom_control` 의 `oom_kill` 줄. 뿌리는 시작 스크립트의 한도 읽기
  (`scripts/container_start.py` 의 `CGROUP_ROOT`)와 같은 `/sys/fs/cgroup` 이다.
- **앱 RSS** — `/proc/self/status` 의 `VmRSS`.
- **하위 최고 RSS** — 그 하위 프로세스 자신의 `/proc/<pid>/status` 의 `VmHWM`(exec 뒤 그 프로세스의
  주소 공간이 닿은 최고). 부르는 쪽이 하위가 끝날 때까지 짧은 틈마다 읽어 가장 큰 값을 쥔다 — 끝나
  거두기 전(좀비)에는 그 줄이 없어, 마지막 틈 안에 늘어난 몫은 놓칠 수 있다.
  `getrusage(RUSAGE_CHILDREN)` 은 쓰지 않는다 — Linux 의 하위 `ru_maxrss` 는 exec 앞에 물려받은 부모
  주소 공간의 최고를 세어 앱 RSS 아래로 내려가지 않는다. `/proc` 가 없는 자리(Windows)는 모른다.

띄우기 바로 앞에는 프로세스 단서도 한 번 읽는다(`process_clues` →
`container_start_report.ProcessClues`) — 막 뜬 pod 에서는 되고 오래 떠 있던 pod 에서는 끊기는
갈래(2026-11-21 사내 확인)를 가를 값이다.

- **앱이 뜬 시간** — 로그인을 부른 프로세스(앱이면 Streamlit 서버, 시작 스크립트면 그 프로세스)의
  `/proc/self/stat` 시작 틱(22째 칸 — `comm` 이 괄호 · 공백을 품을 수 있어 마지막 `)` 뒤부터
  가른다)을 `os.sysconf("SC_CLK_TCK")` 로 나눈 초와 `/proc/uptime` 의 차.
- **스레드** — `/proc/self/status` 의 `Threads`. **열린 파일** — `/proc/self/fd` 항목 수(세는
  동안 연 것 하나를 품는다).
- **프로세스 수** — cgroup v2 면 뿌리의 `pids.current` · `pids.max`(「max」 는 한도 없음), v1
  이면 `pids/` 아래 같은 이름. **좀비** — `/proc` 의 숫자 폴더마다 `stat` 의 상태가 `Z` 인
  수(세는 사이 사라진 프로세스는 건너뛴다 — 하나도 못 읽으면 모름).

파일이 없거나 못 읽은 값은 `None` 이고 화면에는 「모름」 이다. 표준 라이브러리만 쓴다 — 시작
스크립트가 앱 의존성을 깔기 전에 이 길을 지난다. 무엇이 나도 예외를 내지 않는다 — 로그인을 막는
진단은 없다.
"""

from __future__ import annotations

import math
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeVar

from capa_simulation.io.container_start_report import ChildMemory, ProcessClues

CGROUP_ROOT: Final = Path("/sys/fs/cgroup")
PROC_STATUS: Final = Path("/proc/self/status")
# 하위 프로세스 상태 파일의 뿌리(`<뿌리>/<pid>/status`) — 프로세스 단서도 여기서 읽는다
# (`<뿌리>/uptime` · `<뿌리>/self/stat` · `<뿌리>/self/fd` · 좀비를 세는 `<뿌리>/<pid>/stat`).
PROC_ROOT: Final = Path("/proc")
# v1 의 「한도 없음」 은 아주 큰 수로 온다 — 시작 스크립트와 같은 문턱.
V1_UNLIMITED_BYTES: Final = 1 << 60
MIB: Final = 1024 * 1024
_OOM_LINE: Final = re.compile(r"^oom_kill\s+(\d+)\s*$", re.MULTILINE)
_RSS_LINE: Final = re.compile(r"^VmRSS:\s+(\d+)\s+kB\s*$", re.MULTILINE)
_PEAK_LINE: Final = re.compile(r"^VmHWM:\s+(\d+)\s+kB\s*$", re.MULTILINE)
_THREADS_LINE: Final = re.compile(r"^Threads:\s+(\d+)\s*$", re.MULTILINE)
# `stat` 의 마지막 `)` 뒤 칸 차례 — 3째(상태)가 0, 22째(시작 틱)가 19.
_STAT_STATE: Final = 0
_STAT_START_TICKS: Final = 19
# 시작 틱 칸의 자릿수 상한 — 64비트 틱은 20자리다. 그보다 긴 수는 꼴이 어긋난 값이다(아주 긴 수는
# 정수 · 실수 바꾸기에서 예외를 낸다).
_START_TICKS_DIGITS: Final = 20
_ZOMBIE: Final = "Z"
_HOUR_SECONDS: Final = 3600.0
_NO_PIDS: Final[tuple[int | None, int | None, bool]] = (None, None, False)
_T = TypeVar("_T")


@dataclass(frozen=True)
class MemoryReading:
    """한 번 읽은 값 — 바이트 · 수. 못 읽은 값은 `None`."""

    cgroup_bytes: int | None = None
    limit_bytes: int | None = None
    unlimited: bool = False
    oom_kill: int | None = None
    rss_bytes: int | None = None


def read(cgroup_root: Path | None = None, status_path: Path | None = None) -> MemoryReading:
    """지금 값을 한 번 읽는다. 뿌리 · 상태 파일을 주지 않으면 모듈 값(`CGROUP_ROOT` ·
    `PROC_STATUS` — 시험이 바꿔 끼운다)을 부를 때 읽는다. 예외를 내지 않는다."""
    root = CGROUP_ROOT if cgroup_root is None else cgroup_root
    status = PROC_STATUS if status_path is None else status_path
    try:
        cgroup, limit, unlimited, oom = _cgroup(root)
    except Exception:  # 진단 값 하나 — 무엇이 나도 모름으로 물러선다
        cgroup, limit, unlimited, oom = None, None, False, None
    return MemoryReading(
        cgroup_bytes=cgroup,
        limit_bytes=limit,
        unlimited=unlimited,
        oom_kill=oom,
        rss_bytes=_line_bytes(status, _RSS_LINE),
    )


def child_memory(
    before: MemoryReading, after: MemoryReading, child_peak_bytes: int | None = None
) -> ChildMemory:
    """앞뒤 두 읽기와 하위 최고 RSS(`child_peak_bytes` — 바이트, 모르면 `None`)를 진단 꼴(MiB ·
    수)로 접는다. 한도는 뒤 읽기를 앞세운다(앞뒤 같은 값이다)."""
    limit = after.limit_bytes if after.limit_bytes is not None else before.limit_bytes
    return ChildMemory(
        cgroup_before=_mib(before.cgroup_bytes),
        cgroup_after=_mib(after.cgroup_bytes),
        limit=_mib(limit),
        unlimited=after.unlimited or before.unlimited,
        oom_before=before.oom_kill,
        oom_after=after.oom_kill,
        rss_before=_mib(before.rss_bytes),
        rss_after=_mib(after.rss_bytes),
        child_peak=_mib(child_peak_bytes),
    )


def process_peak_bytes(pid: int, proc_root: Path | None = None) -> int | None:
    """그 프로세스 자신의 최고 RSS(바이트) — `<뿌리>/<pid>/status` 의 `VmHWM`. 뿌리를 주지 않으면
    모듈 값(`PROC_ROOT` — 시험이 바꿔 끼운다)을 부를 때 읽는다. 끝나 거두기 전(좀비 — 그 줄이 없다)
    · 없는 프로세스 · `/proc` 가 없는 자리(Windows)는 `None`. 예외를 내지 않는다."""
    root = PROC_ROOT if proc_root is None else proc_root
    return _line_bytes(root / str(pid) / "status", _PEAK_LINE)


def process_clues(
    proc_root: Path | None = None,
    status_path: Path | None = None,
    cgroup_root: Path | None = None,
) -> ProcessClues:
    """로그인 하위 프로세스를 띄우기 바로 앞의 프로세스 단서를 한 번 읽는다 — 부른 프로세스가 뜬
    시간 · 스레드 · 열린 파일과 컨테이너의 cgroup 프로세스 수 · 한도 · 좀비 수. 뿌리 · 상태 파일을
    주지 않으면 모듈 값(`PROC_ROOT` · `PROC_STATUS` · `CGROUP_ROOT` — 시험이 바꿔 끼운다)을 부를 때
    읽는다. 예외를 내지 않는다."""
    proc = PROC_ROOT if proc_root is None else proc_root
    status = PROC_STATUS if status_path is None else status_path
    cgroup = CGROUP_ROOT if cgroup_root is None else cgroup_root
    seconds = _quiet(lambda: age_seconds(proc / "self" / "stat", proc / "uptime"), None)
    pids, limit, unlimited = _quiet(lambda: _pids(cgroup), _NO_PIDS)
    return ProcessClues(
        app_hours=None if seconds is None else round(seconds / _HOUR_SECONDS, 1),
        threads=_quiet(lambda: _line_number(status, _THREADS_LINE), None),
        open_files=_quiet(lambda: _entry_count(proc / "self" / "fd"), None),
        pids=pids,
        pids_limit=limit,
        pids_unlimited=unlimited,
        zombies=_quiet(lambda: _zombies(proc), None),
    )


def age_seconds(stat_path: Path, uptime_path: Path) -> float | None:
    """그 `stat` 의 프로세스가 뜬 지 몇 초 — 시작 틱(22째 칸) ÷ 초당 틱(`clock_ticks`)을 부팅 뒤
    초(`uptime` 의 첫 값)에서 뺀다. 못 읽으면 · 틱을 모르면 · 시작 틱이 수가 아니거나 20자리를
    넘으면 · 1초 넘게 거꾸로면 `None`, 반올림으로 살짝 거꾸로면 0. 예외를 내지 않는다."""
    fields = _stat_fields(stat_path)
    ticks = clock_ticks()
    uptime = _uptime_seconds(uptime_path)
    if fields is None or ticks is None or uptime is None or len(fields) <= _STAT_START_TICKS:
        return None
    start = fields[_STAT_START_TICKS]
    if not start.isdecimal() or len(start) > _START_TICKS_DIGITS:
        return None
    age = uptime - int(start) / ticks
    if age < -1.0:
        return None
    return max(age, 0.0)


def clock_ticks() -> int | None:
    """초당 클록 틱(`SC_CLK_TCK`) — `stat` 의 시작 틱을 초로 바꾼다. Windows · 못 읽으면 `None`."""
    if sys.platform == "win32":
        return None
    try:
        ticks = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError):
        return None
    return ticks if ticks > 0 else None


def higher(peak: int | None, sample: int | None) -> int | None:
    """지금까지의 최고와 새 표본 가운데 큰 것 — 모르는 표본(`None`)은 버린다."""
    if sample is None:
        return peak
    return sample if peak is None or sample > peak else peak


def _mib(value: int | None) -> int | None:
    return None if value is None else round(value / MIB)


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None


def _number(path: Path) -> int | None:
    text = _text(path)
    if text is None:
        return None
    value = text.strip()
    return int(value) if value.isdecimal() else None


def _oom(path: Path) -> int | None:
    text = _text(path)
    match = None if text is None else _OOM_LINE.search(text)
    return None if match is None else int(match.group(1))


def _cgroup(root: Path) -> tuple[int | None, int | None, bool, int | None]:
    """(사용, 한도, 한도 없음, OOM 종료 수). v2 를 먼저 보고 없으면 v1 이다."""
    if (root / "memory.current").exists():
        limit_text = (_text(root / "memory.max") or "").strip()
        unlimited = limit_text == "max"
        limit = int(limit_text) if limit_text.isdecimal() else None
        return (
            _number(root / "memory.current"),
            limit,
            unlimited,
            _oom(root / "memory.events"),
        )
    v1 = root / "memory"
    limit = _number(v1 / "memory.limit_in_bytes")
    unlimited = limit is not None and limit >= V1_UNLIMITED_BYTES
    return (
        _number(v1 / "memory.usage_in_bytes"),
        None if unlimited else limit,
        unlimited,
        _oom(v1 / "memory.oom_control"),
    )


def _quiet(read_value: Callable[[], _T], fallback: _T) -> _T:
    """진단 값 하나 — 무엇이 나도 `fallback`(모름)으로 물러선다."""
    try:
        return read_value()
    except Exception:
        return fallback


def _stat_fields(path: Path) -> list[str] | None:
    """`stat` 의 마지막 `)` 뒤 칸들(3째 상태부터) — `comm` 이 괄호 · 공백을 품어도 갈린다. 파일이
    없거나 `)` 가 없으면 `None`."""
    text = _text(path)
    if text is None:
        return None
    _, close, rest = text.rpartition(")")
    return rest.split() if close else None


def _uptime_seconds(path: Path) -> float | None:
    text = _text(path)
    words = [] if text is None else text.split()
    if not words:
        return None
    try:
        value = float(words[0])
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _entry_count(path: Path) -> int | None:
    """폴더의 항목 수. 폴더가 없거나 못 읽으면 `None`."""
    try:
        with os.scandir(path) as entries:
            return sum(1 for _ in entries)
    except OSError:
        return None


def _pids(root: Path) -> tuple[int | None, int | None, bool]:
    """(프로세스 수, 한도, 한도 없음). v2 뿌리의 `pids.current` 를 먼저 보고 없으면 v1
    `pids/` 다."""
    folder = root if (root / "pids.current").exists() else root / "pids"
    limit_text = (_text(folder / "pids.max") or "").strip()
    unlimited = limit_text == "max"
    limit = int(limit_text) if limit_text.isdecimal() else None
    return _number(folder / "pids.current"), limit, unlimited


def _zombies(root: Path) -> int | None:
    """`/proc` 의 숫자 폴더마다 `stat` 상태가 `Z` 인 수. 뿌리를 못 읽거나 `stat` 을 하나도 못 읽으면
    `None` — 세는 사이 사라진 프로세스는 건너뛴다."""
    try:
        entries = [entry for entry in root.iterdir() if entry.name.isdecimal()]
    except OSError:
        return None
    seen = zombies = 0
    for entry in entries:
        fields = _stat_fields(entry / "stat")
        if not fields:
            continue
        seen += 1
        if fields[_STAT_STATE] == _ZOMBIE:
            zombies += 1
    return zombies if seen else None


def _line_number(path: Path, line: re.Pattern[str]) -> int | None:
    """상태 파일의 `<이름>: n` 줄 값. 파일 · 줄이 없으면 `None`."""
    text = _text(path)
    match = None if text is None else line.search(text)
    return None if match is None else int(match.group(1))


def _line_bytes(path: Path, line: re.Pattern[str]) -> int | None:
    """상태 파일의 `<이름>: n kB` 줄 값(바이트). 파일 · 줄이 없으면 `None`."""
    text = _text(path)
    match = None if text is None else line.search(text)
    return None if match is None else int(match.group(1)) * 1024
