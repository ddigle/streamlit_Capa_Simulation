# Purpose: 시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·삽입 SQL을 담당한다.

"""시나리오와 분리된 공용 실행 Capa 반영 프로필의 조회·삽입 SQL."""

from __future__ import annotations

from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import quote
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
    connection.execute(
        """
        INSERT INTO app_meta.global_execution_capacity (profile_id, version, source)
        VALUES (1, ?, ?)
        """,
        [version, source],
    )
    if prepared.empty:
        return
    payload = prepared.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()
    payload.insert(0, "profile_id", 1)
    view_name = f"_incoming_global_execution_capacity_{uuid4().hex}"
    connection.register(view_name, payload)
    try:
        connection.execute(
            f"INSERT INTO app_meta.global_execution_capacity_row BY NAME "
            f"SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
