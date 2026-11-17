# Purpose: DuckDB 메모리 한도 환경변수를 연결 설정으로 풀고 회차 끝 DB 메모리 표본을 모은다.

"""DuckDB 메모리 — 한도 칸과 회차 끝 표본.

**한도 칸**(`MEMORY_LIMIT_ENV` = `CAPA_DUCKDB_MEMORY_LIMIT`). 값이 없거나 비면 연결 설정에 넣지
않는다 — DuckDB 기본(프로세스가 보는 메모리의 80%) 그대로다. 값은 사용자가 정한다 — 코드 · 이미지에
기본값을 두지 않는다. 꼴은 수 + 단위다 — 단위는 `KB` · `MB` · `GB` · `TB`(1000 배) 또는 `KiB` ·
`MiB` · `GiB` · `TiB`(1024 배)이고 대소문자 · 사이 띄어 씀은 가리지 않는다. 수는 ASCII 숫자만이고 값
전체가 ASCII 여야 한다 — 전각 · 아라비아 숫자는 `float` 이 읽어도 DuckDB 가 거절해 모든 연결이
실패한다. 이 꼴은 DuckDB 가 받는 꼴의 부분이라 범위 안이면 DuckDB 가 그대로 받는다(앞 0 · 긴 소수
자리까지 — `tests/test_duckdb_memory.py` 가 단위마다 연다). 비율(DuckDB 가 거절한다)
· 단위 없는 수 · `none` · `-1` 은 받지 않는다. 받는 범위는 `MEMORY_LIMIT_FLOOR_BYTES` ~
`MEMORY_LIMIT_CEILING_BYTES` 다 — 꼴이 맞아도 너무 작으면 DuckDB 가 첫 표를 만들다 메모리 부족으로
멈춰 모든 DB 열기가 실패하고(16MiB · 스레드 32 에서 그 실패를 재었다), 너무 크면 DuckDB 가 범위
밖이라 거절한다(끝없이 긴 수는 무한대라 범위 밖이다). 판정은 `_sql_helpers` import 때 돌아
어떤 값에도 예외를 내지 않는다. 틀린 값은 넣지 않고(기본 그대로) Admin 「서버 시작 점검」 의
「DuckDB 메모리 한도」 줄이 실패로 알린다(`components/memory_diagnostic.py` — 시작 점검 관리자
알림 `AD-01` 에 든다).

환경변수는 `_sql_helpers` 가 import 때 한 번 읽어 `DUCKDB_CONNECT_CONFIG` 에 넣는다 — 같은 파일의
연결은 설정이 모두 같아야 해서 프로세스 중간에 바뀌면 안 된다. 그 설정 한 벌을 두 DB(시뮬레이션 ·
설비)가 함께 쓰므로 한도는 DB(인스턴스)마다 같은 값이고, 두 DB 가 함께 차면 합이 그 두 배까지 간다.
같은 `connect()` 로 잠깐 여는 파일(동기화가 받은 사본 확인 · 스냅샷 짓기)도 같은 한도다.

**회차 끝 표본**(`observe` · `memory_sample`). 이 앱은 작업마다 연결을 여닫아 회차가 끝나면 DuckDB
인스턴스가 내려가고 그 메모리도 풀린다. 그래서 아무 때나 재면 거의 늘 0 이거나 열린 연결이 없다.
`_sql_helpers.pinned_connections` 가 가장 바깥 블록을 닫으며 핀을 닫기 **직전**에 그 핀으로
`duckdb_memory()` 를 한 번 읽어(새 연결을 열지 않는다) DB 마다 마지막 · 최고 사용량 · 임시 파일
최고를 프로세스 메모리에 모은다. 한도(`current_setting('memory_limit')` — DuckDB 가 실제로 쓰는
값)는 DB 마다 처음 한 번만 읽는다. 질의는 회차당 0.2ms 안팎이고(샘플 관측 — 합성 DB, 스레드 3) 핀은
그 회차에 DB 를 연 회차에만 있다. 질의 중 순간 최고는 잡지 못한다 — 회차 끝에 버퍼에 남은 양이다.
읽다 무엇이 나도 건너뛴다(진단이 회차를 멈추지 않는다). Streamlit 을 import 하지 않는다(동기화
일꾼도 이 패키지를 쓴다).
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import duckdb

MEMORY_LIMIT_ENV: Final = "CAPA_DUCKDB_MEMORY_LIMIT"
MIB: Final = 1024**2
# 받는 범위 — 모듈 설명. 둘 다 권하는 값이 아니라 앱이 멈추지 않게 막는 울타리다.
MEMORY_LIMIT_FLOOR_BYTES: Final = 64 * MIB
MEMORY_LIMIT_CEILING_BYTES: Final = 1024**4
MEMORY_LIMIT_RANGE_TEXT: Final = "64MiB ~ 1TiB"

PROBLEM_FORM: Final = "form"
PROBLEM_RANGE: Final = "range"
LimitProblem = Literal["form", "range"]

_LIMIT_FORM = re.compile(r"(?P<number>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>[KMGT]I?B)", re.ASCII)
_UNIT_BYTES: Final[Mapping[str, int]] = {
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}
# DuckDB 에 넘길 단위 철자 — 화면 · 복사 글에도 이 철자로 싣는다.
_UNIT_NAMES: Final[Mapping[str, str]] = {
    "KB": "KB",
    "MB": "MB",
    "GB": "GB",
    "TB": "TB",
    "KIB": "KiB",
    "MIB": "MiB",
    "GIB": "GiB",
    "TIB": "TiB",
}


@dataclass(frozen=True)
class MemoryLimitSetting:
    """환경변수 한 칸의 판정. `value` 가 None 이면 연결 설정에 넣지 않는다(DuckDB 기본)."""

    raw: str | None
    value: str | None = None
    limit_bytes: int | None = None
    problem: LimitProblem | None = None


def memory_limit_setting(environ: Mapping[str, str]) -> MemoryLimitSetting:
    """`CAPA_DUCKDB_MEMORY_LIMIT` 를 판정한다 — 없음 · 빈 값은 `raw=None`, 틀린 값은 `problem`.

    import 때 도는 판정이라 어떤 값에도 예외를 내지 않는다(모듈 설명)."""
    text = environ.get(MEMORY_LIMIT_ENV, "").strip()
    if not text:
        return MemoryLimitSetting(raw=None)
    match = _LIMIT_FORM.fullmatch(text.upper()) if text.isascii() else None
    if match is None:
        return MemoryLimitSetting(raw=text, problem=PROBLEM_FORM)
    unit = match["unit"]
    limit = float(match["number"]) * _UNIT_BYTES[unit]
    in_range = MEMORY_LIMIT_FLOOR_BYTES <= limit <= MEMORY_LIMIT_CEILING_BYTES
    if not (math.isfinite(limit) and in_range):
        return MemoryLimitSetting(raw=text, problem=PROBLEM_RANGE)
    value = f"{match['number']}{_UNIT_NAMES[unit]}"
    return MemoryLimitSetting(raw=text, value=value, limit_bytes=int(limit))


def memory_limit_config(setting: MemoryLimitSetting) -> dict[str, str]:
    """연결 설정에 더할 칸 — 받은 값이 있을 때만 `memory_limit` 하나."""
    return {} if setting.value is None else {"memory_limit": setting.value}


@dataclass(frozen=True)
class MemorySample:
    """DB 하나의 회차 끝 표본 모음 — 바이트 수와, DuckDB 가 알려 준 한도 글(예 `819.1 MiB`)."""

    last_bytes: int
    peak_bytes: int
    peak_temporary_bytes: int
    limit: str | None
    count: int


_MEMORY_QUERY: Final = "select memory_usage_bytes, temporary_storage_bytes from duckdb_memory()"
_LIMIT_QUERY: Final = "select current_setting('memory_limit')"
_SAMPLES: dict[str, MemorySample] = {}
_SAMPLES_LOCK = threading.Lock()


def database_key(database_path: Path | str) -> str:
    """표본을 가르는 열쇠 — `_sql_helpers` 의 핀 열쇠와 같은 꼴(상대 · 절대 경로가 섞여도 같다)."""
    return str(Path(database_path).resolve())


def observe(key: str, connection: duckdb.DuckDBPyConnection) -> None:
    """핀을 닫기 직전에 그 핀으로 DB 메모리를 한 번 읽어 모은다. 무엇이 나도 건너뛴다."""
    with _SAMPLES_LOCK:
        known = _SAMPLES.get(key)
    try:
        rows = connection.execute(_MEMORY_QUERY).fetchall()
        limit = known.limit if known is not None and known.limit else _read_limit(connection)
        used = sum(int(row[0] or 0) for row in rows)
        temporary = sum(int(row[1] or 0) for row in rows)
    except Exception:  # 진단이 회차를 멈추지 않는다(모듈 설명)
        return
    with _SAMPLES_LOCK:
        before = _SAMPLES.get(key)
        _SAMPLES[key] = MemorySample(
            last_bytes=used,
            peak_bytes=max(used, before.peak_bytes if before else 0),
            peak_temporary_bytes=max(temporary, before.peak_temporary_bytes if before else 0),
            limit=limit,
            count=(before.count if before else 0) + 1,
        )


def _read_limit(connection: duckdb.DuckDBPyConnection) -> str | None:
    row = connection.execute(_LIMIT_QUERY).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def memory_sample(database_path: Path | str) -> MemorySample | None:
    """그 DB 의 표본 모음. 이 프로세스에서 아직 한 번도 못 쟀으면 None."""
    with _SAMPLES_LOCK:
        return _SAMPLES.get(database_key(database_path))


def reset_samples() -> None:
    """표본을 비운다 — 시험이 쓴다."""
    with _SAMPLES_LOCK:
        _SAMPLES.clear()
