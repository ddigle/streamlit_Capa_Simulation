# Purpose: 로그인 하위 프로세스 앞뒤의 cgroup 메모리 · OOM 종료 수 · RSS 를 읽는다.

"""메모리 단서 — 자동 로그인 하위 프로세스가 바깥 신호(SIGKILL)로 끝났을 때 가를 값.

`io/bdq_login.attempt_login` 이 하위 프로세스를 띄우기 바로 앞과 끝난 바로 뒤에 한 번씩 읽고
(`read`), 두 읽기를 MiB · 수로 접어(`child_memory`) 진단(`container_start_report.ChildMemory`)에
싣는다. 앞뒤 OOM 종료 수가 다르면 그 사이 cgroup 이 프로세스를 죽인 것이다 — 진단 줄이 그 수를
보이고, 이 모듈은 판정하지 않는다.

- **cgroup** — v2 면 뿌리의 `memory.current` · `memory.max`(「max」 는 한도 없음) · `memory.events`
  의 `oom_kill` 줄, v1 이면 `memory/` 아래 `memory.usage_in_bytes` · `memory.limit_in_bytes`(아주 큰
  값은 한도 없음) · `memory.oom_control` 의 `oom_kill` 줄. 뿌리는 시작 스크립트의 한도 읽기
  (`scripts/container_start.py` 의 `CGROUP_ROOT`)와 같은 `/sys/fs/cgroup` 이다.
- **앱 RSS** — `/proc/self/status` 의 `VmRSS`.
- **하위 최고 RSS** — `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`(거둔 하위 프로세스 모두의
  최고 — 앞뒤가 같으면 이번 하위는 그보다 작았다). `resource` 가 없는 자리(Windows)는 모른다.

파일이 없거나 못 읽은 값은 `None` 이고 화면에는 「모름」 이다. 표준 라이브러리만 쓴다 — 시작
스크립트가 앱 의존성을 깔기 전에 이 길을 지난다. 무엇이 나도 예외를 내지 않는다 — 로그인을 막는
진단은 없다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from capa_simulation.io.container_start_report import ChildMemory

CGROUP_ROOT: Final = Path("/sys/fs/cgroup")
PROC_STATUS: Final = Path("/proc/self/status")
# v1 의 「한도 없음」 은 아주 큰 수로 온다 — 시작 스크립트와 같은 문턱.
V1_UNLIMITED_BYTES: Final = 1 << 60
MIB: Final = 1024 * 1024
_OOM_LINE: Final = re.compile(r"^oom_kill\s+(\d+)\s*$", re.MULTILINE)
_RSS_LINE: Final = re.compile(r"^VmRSS:\s+(\d+)\s+kB\s*$", re.MULTILINE)


@dataclass(frozen=True)
class MemoryReading:
    """한 번 읽은 값 — 바이트 · 수. 못 읽은 값은 `None`."""

    cgroup_bytes: int | None = None
    limit_bytes: int | None = None
    unlimited: bool = False
    oom_kill: int | None = None
    rss_bytes: int | None = None
    child_peak_bytes: int | None = None


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
        rss_bytes=_rss(status),
        child_peak_bytes=children_peak_bytes(),
    )


def child_memory(before: MemoryReading, after: MemoryReading) -> ChildMemory:
    """앞뒤 두 읽기를 진단 꼴(MiB · 수)로 접는다. 한도는 뒤 읽기를 앞세운다(앞뒤 같은 값이다)."""
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
        child_peak_before=_mib(before.child_peak_bytes),
        child_peak_after=_mib(after.child_peak_bytes),
    )


def children_peak_bytes() -> int | None:
    """거둔 하위 프로세스들의 최고 RSS(바이트). `resource` 가 없거나 못 읽으면 `None`."""
    if sys.platform == "win32":
        return None
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    except (ImportError, OSError, ValueError, AttributeError):
        return None
    if peak <= 0:
        return None
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024


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


def _rss(path: Path) -> int | None:
    text = _text(path)
    match = None if text is None else _RSS_LINE.search(text)
    return None if match is None else int(match.group(1)) * 1024
