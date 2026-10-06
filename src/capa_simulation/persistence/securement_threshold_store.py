# Purpose: 시나리오와 분리된 공용 확보율 판정 기준 프로필의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 확보율 판정 기준 프로필(0029)의 조회·교체 SQL.

헤더 한 행이 기본 확보·경고 기준을 갖고 월별 표가 예외를 갖는다. 헤더에 값 칸이 있어
`insert_profile_header` 대신 여기서 헤더를 직접 쓴다. 지우기와 다음 version 은 공용
`reset_profile` 이다.

저장은 **버전 대조**를 한다. 편집을 시작할 때 본 version 과 지금 저장된 version 이 다르면 다른
세션이 먼저 저장한 것이다 — 그대로 쓰면 그 사람이 넣은 달을 모르는 새 덮는다.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name, quote, reset_profile
from capa_simulation.services.securement_threshold import (
    SECUREMENT_THRESHOLD_COLUMNS,
    prepare_securement_threshold_rows,
)

_HEADER_TABLE = "global_securement_threshold"
_MONTH_TABLE = "global_securement_threshold_month"


class SecurementThresholdConflict(ValueError):
    """편집을 시작한 뒤 다른 세션이 판정 기준을 먼저 저장했다. 저장하지 않고 알린다."""


def load_securement_threshold_header(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[int, str, datetime, float, float] | None:
    """(version, source, updated_at, 기본 확보, 기본 경고). 한 번도 저장하지 않았으면 None."""
    row = connection.execute(
        f"""
        SELECT version, source, updated_at, "기본 확보 기준", "기본 경고 기준"
        FROM app_meta.{_HEADER_TABLE}
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), str(row[1]), row[2], float(row[3]), float(row[4])


def load_securement_threshold_rows(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    projection = ", ".join(quote(column) for column in SECUREMENT_THRESHOLD_COLUMNS)
    rows = connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.{_MONTH_TABLE}
        WHERE profile_id = 1
        ORDER BY "생산계획년월"
        """
    ).fetchdf()
    return prepare_securement_threshold_rows(rows)


def stored_securement_threshold_version(connection: duckdb.DuckDBPyConnection) -> int:
    """지금 저장된 version. 한 번도 저장하지 않았으면 0 이다(화면의 미저장 version 과 같다)."""
    row = connection.execute(
        f"SELECT version FROM app_meta.{_HEADER_TABLE} WHERE profile_id = 1"
    ).fetchone()
    return 0 if row is None else int(row[0])


def replace_global_securement_threshold(
    connection: duckdb.DuckDBPyConnection,
    *,
    default_secure: float,
    default_warning: float,
    prepared_rows: pd.DataFrame,
    source: str,
    expected_version: int,
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다.

    `expected_version` 은 편집을 시작할 때 본 version 이다. 지금 저장본과 다르면 아무것도 쓰지
    않고 `SecurementThresholdConflict` 를 올린다.
    """
    stored = stored_securement_threshold_version(connection)
    if stored != int(expected_version):
        raise SecurementThresholdConflict(
            "다른 사용자가 먼저 판정 기준을 저장해 이번 저장은 반영하지 않았습니다"
            f"(편집 시작 v{int(expected_version)} · 지금 v{stored}). 최신 저장본을 확인한 뒤 다시 "
            "저장하세요."
        )
    version = reset_profile(connection, _HEADER_TABLE, _MONTH_TABLE)
    connection.execute(
        f"""
        INSERT INTO app_meta.{_HEADER_TABLE}
            (profile_id, version, source, "기본 확보 기준", "기본 경고 기준")
        VALUES (1, ?, ?, ?, ?)
        """,
        [version, source, float(default_secure), float(default_warning)],
    )
    if prepared_rows.empty:
        return
    payload = prepared_rows.loc[:, list(SECUREMENT_THRESHOLD_COLUMNS)].copy()
    payload.insert(0, "profile_id", 1)
    insert_by_name(connection, schema="app_meta", table_name=_MONTH_TABLE, frame=payload)
