# Purpose: 시나리오와 분리된 공용 선행 입고 실적 프로필의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 선행 입고 실적 프로필의 조회·교체 SQL(마이그레이션 0031)."""

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
from capa_simulation.persistence.models import GlobalAdvanceShipment
from capa_simulation.services.advance_shipment import (
    ADVANCE_SHIPMENT_COLUMNS,
    empty_advance_shipment,
    prepare_advance_shipment,
)

HEADER_TABLE = "global_advance_shipment"
MONTH_TABLE = "global_advance_shipment_month"


def load_global_advance_shipment_rows(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    projection = ", ".join(quote(column) for column in ADVANCE_SHIPMENT_COLUMNS)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.{MONTH_TABLE}
        WHERE profile_id = 1
        ORDER BY "생산계획년월"
        """
    ).fetchdf()


def load_global_advance_shipment(connection: duckdb.DuckDBPyConnection) -> GlobalAdvanceShipment:
    """열린 연결에서 공용 프로필을 복원한다. 한 번도 저장하지 않았으면 version 0·행 0건이다."""
    metadata = load_profile_header(connection, HEADER_TABLE)
    if metadata is None:
        return GlobalAdvanceShipment(
            version=0,
            source="",
            updated_at=None,
            rows=empty_advance_shipment(),
        )
    return GlobalAdvanceShipment(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        rows=prepare_advance_shipment(load_global_advance_shipment_rows(connection)),
    )


def replace_global_advance_shipment(
    connection: duckdb.DuckDBPyConnection, prepared_rows: pd.DataFrame, *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다.

    월이 0건이어도 헤더는 기록한다 — 캐시 키가 version 을 보므로 「전체 해제」도 version 이
    올라야 다른 세션의 그림이 풀린다.
    """
    version = reset_profile(connection, HEADER_TABLE, MONTH_TABLE)
    insert_profile_header(connection, HEADER_TABLE, version=version, source=source)
    prepared = prepare_advance_shipment(prepared_rows)
    if prepared.empty:
        return
    payload = prepared.loc[:, list(ADVANCE_SHIPMENT_COLUMNS)].copy()
    payload.insert(0, "profile_id", 1)
    insert_by_name(connection, schema="app_meta", table_name=MONTH_TABLE, frame=payload)
