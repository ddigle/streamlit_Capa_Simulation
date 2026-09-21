# Purpose: 시나리오와 분리된 공용 과거 구간 프로필의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 과거 구간 프로필의 조회·교체 SQL."""

from __future__ import annotations

from collections.abc import Mapping

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_profile_header,
    quote,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalPastData
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    empty_past_table,
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


def load_global_past_data(connection: duckdb.DuckDBPyConnection) -> GlobalPastData:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    metadata = load_profile_header(connection, "global_past_data")
    if metadata is None:
        return GlobalPastData(
            version=0,
            source="",
            updated_at=None,
            monthly=empty_past_table(PAST_TABLES["월별"][1]),
            plan_detail=empty_past_table(PAST_TABLES["계획"][1]),
            securement=empty_past_table(PAST_TABLES["확보율"][1]),
        )
    loaded = {
        name: prepare_past_table(load_global_past_table(connection, name), columns)
        for name, (_, columns) in PAST_TABLES.items()
    }
    return GlobalPastData(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        monthly=loaded["월별"],
        plan_detail=loaded["계획"],
        securement=loaded["확보율"],
    )


def replace_global_past_data(
    connection: duckdb.DuckDBPyConnection, prepared: Mapping[str, pd.DataFrame], *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(
        connection, "global_past_data", *(table for table, _ in PAST_TABLES.values())
    )
    insert_global_past_data(
        connection,
        dict(prepared),
        version=version,
        source=source,
    )
