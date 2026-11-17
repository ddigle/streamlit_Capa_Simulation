# Purpose: 「서버 시작 점검」 의 메모리 값 줄(RSS · 세션 · cache_data · DuckDB)과 한도 줄을 짓는다.

"""메모리 진단.

사내가 메모리 줄이기 앞뒤를 재는 값 줄이다. Admin 「서버 시작 점검」 펼침(C-DEP 에만 선다)이 표 아래
사실 줄 끝에 싣고 「복사」 글에도 든다. 값은 결과 파일이 아니라 이 프로세스의 지금이다(「지금 토큰」
줄과 같은 꼴). 화면에는 값 줄만 두고 뜻은 Guide 「서버 시작 점검」 이 말한다.

- **메모리 지금** — RSS 지금 · 최고(`/proc/self/status` 의 `VmRSS` · `VmHWM`). 그 파일이 없으면
  최고만 `resource.getrusage` 로 읽고(Linux 는 KiB, macOS 는 바이트), Windows 는 둘 다 「모름」.
  세션은 연결된 세션 · 전체 세션(끊긴 뒤 아직 지우지 않은 세션까지 — 메모리를 쥔 수다)이고 Streamlit
  내부 `Runtime` 의 세션 관리자를 읽는다 — 무엇이 나도(시험 · 판이 바뀜) 「모름」. `cache_data` 는
  `st.cache_data` 메모리 칸의 합이다 — Streamlit 이 `/_stcore/metrics` 에 내는 값과 같은 저장된
  pickle 길이라 값을 깊이 재지 않는다. `cache_resource` · 세션 상태는 깊이 재야 해서(잠긴 표의 크기
  재기) 싣지 않는다.
- **DuckDB <DB> 회차 끝** — DB 마다 회차 끝 표본(`persistence/duckdb_memory.py` — 새 연결을 열지
  않는다): 마지막 · 최고 · 임시 파일 최고와 DuckDB 가 실제로 쓰는 한도. 이 프로세스에서 아직 못
  쟀으면 「모름」.

「DuckDB 메모리 한도」 단계 줄(`memory_limit_step`)은 이 프로세스가 연결 설정에 넣은 한도 칸의
판정이다 — 통합인증 줄처럼 결과 파일이 아니라 지금 설정이다. 틀린 값이면 「실패」 라 펼침 제목
판정과 시작 점검 관리자 알림 `AD-01` 에 든다(`container_start_check`). 까닭은 값 없는 고정 낱말이다
— 틀린 값은 옆 칸(비밀 키 · 토큰)을 잘못 붙여 넣은 것일 수 있고, 이 줄은 복사 글로 리뷰에 옮긴다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import capa_simulation.settings as settings
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.io.container_start_report import (
    STATUS_FAILED,
    STATUS_LABELS,
    STATUS_OK,
    STATUS_SKIPPED,
)
from capa_simulation.persistence import _sql_helpers
from capa_simulation.persistence.duckdb_memory import (
    MEMORY_LIMIT_ENV,
    MEMORY_LIMIT_RANGE_TEXT,
    MIB,
    PROBLEM_FORM,
    MemoryLimitSetting,
    MemorySample,
    memory_sample,
)

NOT_KNOWN: Final = "모름"
MEMORY_LIMIT_STEP_LABEL: Final = "DuckDB 메모리 한도"
PROC_STATUS: Final = Path("/proc/self/status")
_STATUS_LINE = re.compile(r"^(?P<name>Vm[A-Za-z]+):\s+(?P<value>\d+)\s+kB\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ProcessMemory:
    """프로세스 메모리 — 바이트 수, 못 읽으면 None."""

    rss_bytes: int | None
    peak_bytes: int | None


def process_memory(status_path: Path = PROC_STATUS) -> ProcessMemory:
    """RSS 지금 · 최고. `status_path` 를 못 읽으면 최고만 `resource` 로 읽는다."""
    try:
        text = status_path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return ProcessMemory(rss_bytes=None, peak_bytes=_peak_from_resource())
    values = {match["name"]: int(match["value"]) * 1024 for match in _STATUS_LINE.finditer(text)}
    peak = values.get("VmHWM")
    return ProcessMemory(
        rss_bytes=values.get("VmRSS"),
        peak_bytes=peak if peak is not None else _peak_from_resource(),
    )


def _peak_from_resource() -> int | None:
    if sys.platform == "win32":
        return None
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, OSError, ValueError):
        return None
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024


def session_counts() -> tuple[int, int] | None:
    """(연결된 세션, 전체 세션). Streamlit 내부 API 라 무엇이 나도 None."""
    try:
        from streamlit.runtime import Runtime

        if not Runtime.exists():
            return None
        manager = Runtime.instance()._session_mgr
        return manager.num_active_sessions(), manager.num_sessions()
    except Exception:  # 내부 API — 판이 바뀌어도 진단 줄은 「모름」 으로 선다
        return None


def cache_data_bytes() -> int | None:
    """`st.cache_data` 메모리 칸의 합(저장된 pickle 길이). 무엇이 나도 None."""
    try:
        from streamlit.runtime.caching.cache_data_api import get_data_cache_stats_provider
        from streamlit.runtime.stats import CacheStat

        stats = get_data_cache_stats_provider().get_stats()
        return sum(
            stat.byte_length
            for family in stats.values()
            for stat in family
            if isinstance(stat, CacheStat)
        )
    except Exception:  # 내부 API — 판이 바뀌어도 진단 줄은 「모름」 으로 선다
        return None


def mib_text(value: int | None) -> str:
    return NOT_KNOWN if value is None else f"{value / MIB:.1f} MiB"


def process_line(
    process: ProcessMemory, sessions: tuple[int, int] | None, cache: int | None
) -> str:
    """「**메모리 지금** · RSS · 최고 · 세션 · cache_data」 한 줄."""
    session = NOT_KNOWN if sessions is None else f"연결 {sessions[0]} · 전체 {sessions[1]}"
    parts = [
        f"RSS {mib_text(process.rss_bytes)}",
        f"최고 {mib_text(process.peak_bytes)}",
        f"세션 {session}",
        f"cache_data {mib_text(cache)}",
    ]
    return f"**메모리 지금** · {' · '.join(parts)}"


def duckdb_line(label: str, sample: MemorySample | None) -> str:
    """「**DuckDB <DB> 회차 끝** · 마지막 · 최고 · 임시 파일 최고 · 한도」 한 줄."""
    head = f"**DuckDB {label} 회차 끝**"
    if sample is None:
        return f"{head} · {NOT_KNOWN}"
    limit = literal_markdown(sample.limit) if sample.limit else NOT_KNOWN
    parts = [
        f"마지막 {mib_text(sample.last_bytes)}",
        f"최고 {mib_text(sample.peak_bytes)}",
        f"임시 파일 최고 {mib_text(sample.peak_temporary_bytes)}",
        f"한도 {limit}",
    ]
    return f"{head} · {' · '.join(parts)}"


def memory_lines() -> list[str]:
    """펼침 사실 줄 끝에 더하는 값 줄 셋 — 프로세스 한 줄, DB 마다 한 줄."""
    databases = (("시뮬레이션", settings.DUCKDB_PATH), ("설비", settings.EQUIPMENT_DUCKDB_PATH))
    return [
        process_line(process_memory(), session_counts(), cache_data_bytes()),
        *(duckdb_line(label, memory_sample(path)) for label, path in databases),
    ]


def memory_limit_step(setting: MemoryLimitSetting | None = None) -> tuple[str, str, str]:
    """「서버 시작 점검」 표의 `(단계, 결과, 까닭)` — 이 프로세스가 연결 설정에 넣은 한도 칸."""
    current = _sql_helpers.DUCKDB_MEMORY_LIMIT if setting is None else setting
    if current.problem is not None and current.raw is not None:
        why = "꼴이 틀림" if current.problem == PROBLEM_FORM else f"{MEMORY_LIMIT_RANGE_TEXT} 밖"
        reason = f"{MEMORY_LIMIT_ENV} {why} — DuckDB 기본 그대로"
        return MEMORY_LIMIT_STEP_LABEL, STATUS_LABELS[STATUS_FAILED], reason
    if current.value is None:
        reason = f"{MEMORY_LIMIT_ENV} 없음 — DuckDB 기본"
        return MEMORY_LIMIT_STEP_LABEL, STATUS_LABELS[STATUS_SKIPPED], reason
    return MEMORY_LIMIT_STEP_LABEL, STATUS_LABELS[STATUS_OK], f"DB 마다 {current.value}"


def memory_limit_failed(setting: MemoryLimitSetting | None = None) -> bool:
    """한도 칸 값이 틀려 기본으로 물러섰는가 — 펼침 제목 판정과 `AD-01` 이 본다."""
    return memory_limit_step(setting)[1] == STATUS_LABELS[STATUS_FAILED]
