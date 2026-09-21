# Purpose: 시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·삽입 SQL을 담당한다.

"""시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·삽입 SQL."""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name, insert_profile_header, quote
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
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
