# Purpose: 시나리오와 분리된 공용 과거 구간 프로필의 조회·삽입 SQL을 담당한다.

"""시나리오와 분리된 공용 과거 구간 프로필의 조회·삽입 SQL."""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name, insert_profile_header, quote
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    prepare_past_table,
)

# 논리 이름 → (테이블, 컬럼 계약). 세 표가 같은 프로필 버전을 공유한다.
PAST_TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "월별": ("global_past_month", PAST_MONTH_COLUMNS),
    "계획": ("global_past_plan_detail", PAST_DETAIL_COLUMNS),
    "확보율": ("global_past_securement", PAST_SECUREMENT_COLUMNS),
}


def load_global_past_table(
    connection: duckdb.DuckDBPyConnection,
    name: str,
) -> pd.DataFrame:
    table, columns = PAST_TABLES[name]
    projection = ", ".join(quote(column) for column in columns)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.{quote(table)}
        WHERE profile_id = 1
        ORDER BY "생산계획년월"
        """
    ).fetchdf()


def insert_global_past_data(
    connection: duckdb.DuckDBPyConnection,
    tables: dict[str, pd.DataFrame],
    *,
    version: int,
    source: str,
) -> None:
    """헤더 한 행과 세 표를 넣는다. 표가 모두 비어도 헤더는 기록한다.

    캐시 키가 version 을 보므로 '전체 해제' 도 버전이 올라야 무효화된다.
    """
    insert_profile_header(connection, "global_past_data", version=version, source=source)
    for name, (table, columns) in PAST_TABLES.items():
        prepared = prepare_past_table(tables[name], columns)
        if prepared.empty:
            continue
        payload = prepared.loc[:, list(columns)].copy()
        payload.insert(0, "profile_id", 1)
        insert_by_name(connection, schema="app_meta", table_name=table, frame=payload)
