# Purpose: 시나리오와 분리된 공용 공정 표시명 프로필의 조회·삽입 SQL을 담당한다.

"""시나리오와 분리된 공용 공정 표시명 프로필의 조회·삽입 SQL."""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name, insert_profile_header, quote
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    prepare_process_rename_rules,
)


def load_global_process_rename_rules(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    projection = ", ".join(quote(column) for column in PROCESS_RENAME_COLUMNS)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.global_process_rename_rule
        WHERE profile_id = 1
        ORDER BY source_row_no
        """
    ).fetchdf()


def insert_global_process_rename(
    connection: duckdb.DuckDBPyConnection,
    rules: pd.DataFrame,
    *,
    version: int,
    source: str,
) -> None:
    """헤더 한 행과 규칙 N행을 넣는다. 규칙이 0건이어도 헤더는 기록한다.

    캐시 키가 version 을 보므로 '전체 해제' 도 버전이 올라야 무효화된다.
    """
    prepared = prepare_process_rename_rules(rules)
    insert_profile_header(connection, "global_process_rename", version=version, source=source)
    if prepared.empty:
        return
    payload = prepared.loc[:, list(PROCESS_RENAME_COLUMNS)].copy()
    payload.insert(0, "source_row_no", range(1, len(payload) + 1))
    payload.insert(0, "profile_id", 1)
    insert_by_name(
        connection,
        schema="app_meta",
        table_name="global_process_rename_rule",
        frame=payload,
    )
