# Purpose: 시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·교체 SQL."""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_profile_header,
    quote,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalExecutionCapacity
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    empty_execution_capacity,
    prepare_execution_capacity,
)


def load_global_execution_capacity_rows(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    projection = ", ".join(quote(column) for column in EXECUTION_CAPACITY_COLUMNS)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.global_execution_capacity_row
        WHERE profile_id = 1
        ORDER BY "생산계획년월", "공정"
        """
    ).fetchdf()


def insert_global_execution_capacity(
    connection: duckdb.DuckDBPyConnection,
    rows: pd.DataFrame,
    *,
    version: int,
    source: str,
) -> None:
    """헤더 한 행과 조정 N행을 넣는다. 조정이 0건이어도 헤더는 기록한다.

    캐시 키가 version 을 보므로 '전체 해제' 도 버전이 올라야 무효화된다.
    """
    prepared = prepare_execution_capacity(rows)
    insert_profile_header(connection, "global_execution_capacity", version=version, source=source)
    if prepared.empty:
        return
    payload = prepared.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()
    payload.insert(0, "profile_id", 1)
    insert_by_name(
        connection,
        schema="app_meta",
        table_name="global_execution_capacity_row",
        frame=payload,
    )


def load_global_execution_capacity(
    connection: duckdb.DuckDBPyConnection,
) -> GlobalExecutionCapacity:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    metadata = load_profile_header(connection, "global_execution_capacity")
    if metadata is None:
        return GlobalExecutionCapacity(
            version=0,
            source="",
            updated_at=None,
            rows=empty_execution_capacity(),
        )
    rows = load_global_execution_capacity_rows(connection)
    return GlobalExecutionCapacity(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        rows=prepare_execution_capacity(rows),
    )


def replace_global_execution_capacity(
    connection: duckdb.DuckDBPyConnection, prepared: pd.DataFrame, *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(
        connection, "global_execution_capacity", "global_execution_capacity_row"
    )
    insert_global_execution_capacity(connection, prepared, version=version, source=source)
