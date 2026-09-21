# Purpose: 시나리오와 분리된 공용 표시순서 프로필의 검증·이관·저장을 담당한다.

"""시나리오와 분리된 공용 표시순서 프로필의 검증·이관·저장을 담당한다."""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_frame,
    load_profile_header,
    quote,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalDisplayOrder
from capa_simulation.services.display_order_editor import ensure_route_sequence_rules

GLOBAL_DISPLAY_ORDER_COLUMNS = (
    "페이지 구분",
    "탭 구분",
    "정렬우선순위",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "값표시순서",
    "활성여부",
)


def validate_global_display_order_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("공용 표시순서는 pandas DataFrame이어야 합니다.")
    missing = [column for column in GLOBAL_DISPLAY_ORDER_COLUMNS if column not in frame.columns]
    extra = [column for column in frame.columns if column not in GLOBAL_DISPLAY_ORDER_COLUMNS]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(str(column) for column in extra)}")
        raise ValueError(f"공용 표시순서 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")
    if frame.empty:
        raise ValueError("공용 표시순서에는 한 개 이상의 규칙이 필요합니다.")


def prepare_global_display_order_rules(frame: pd.DataFrame) -> pd.DataFrame:
    validate_global_display_order_frame(frame)
    return ensure_route_sequence_rules(frame)


def display_order_frames_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    left_values = (
        left.loc[:, list(GLOBAL_DISPLAY_ORDER_COLUMNS)]
        .reset_index(drop=True)
        .astype("string")
        .fillna("<NULL>")
    )
    right_values = (
        right.loc[:, list(GLOBAL_DISPLAY_ORDER_COLUMNS)]
        .reset_index(drop=True)
        .astype("string")
        .fillna("<NULL>")
    )
    return left_values.equals(right_values)


def load_existing_display_order(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame | None:
    candidates = (
        (
            """
            SELECT o.revision_id
            FROM app_meta.official_release o
            WHERE EXISTS (
                SELECT 1 FROM rev_data.rq_display_order d
                WHERE d.revision_id = o.revision_id
            )
            ORDER BY o.release_no DESC LIMIT 1
            """,
            "rev_data",
            "revision_id",
        ),
        (
            """
            SELECT ds.dataset_id
            FROM app_meta.official_release o
            JOIN app_meta.scenario_revision r ON r.revision_id = o.revision_id
            JOIN app_meta.dataset ds ON ds.scenario_id = r.scenario_id
            WHERE EXISTS (
                SELECT 1 FROM ref_data.rq_display_order d
                WHERE d.dataset_id = ds.dataset_id
            )
            ORDER BY o.release_no DESC LIMIT 1
            """,
            "ref_data",
            "dataset_id",
        ),
        (
            """
            SELECT r.revision_id
            FROM app_meta.scenario_revision r
            WHERE EXISTS (
                SELECT 1 FROM rev_data.rq_display_order d
                WHERE d.revision_id = r.revision_id
            )
            ORDER BY r.created_at DESC, r.revision_no DESC LIMIT 1
            """,
            "rev_data",
            "revision_id",
        ),
        (
            """
            SELECT ds.dataset_id
            FROM app_meta.scenario s
            JOIN app_meta.dataset ds ON ds.scenario_id = s.scenario_id
            WHERE EXISTS (
                SELECT 1 FROM ref_data.rq_display_order d
                WHERE d.dataset_id = ds.dataset_id
            )
            ORDER BY s.updated_at DESC LIMIT 1
            """,
            "ref_data",
            "dataset_id",
        ),
    )
    for query, schema, owner_column in candidates:
        owner = connection.execute(query).fetchone()
        if owner is None:
            continue
        return load_frame(
            connection,
            schema=schema,
            table_name="rq_display_order",
            owner_column=owner_column,
            owner_id=str(owner[0]),
        )
    return None


def load_global_display_order_rules(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    projection = ", ".join(quote(column) for column in GLOBAL_DISPLAY_ORDER_COLUMNS)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.global_display_order_rule
        WHERE profile_id = 1
        ORDER BY source_row_no
        """
    ).fetchdf()


def insert_global_display_order(
    connection: duckdb.DuckDBPyConnection,
    rules: pd.DataFrame,
    *,
    version: int,
    source: str,
) -> None:
    validate_global_display_order_frame(rules)
    insert_profile_header(connection, "global_display_order", version=version, source=source)
    prepared = rules.loc[:, list(GLOBAL_DISPLAY_ORDER_COLUMNS)].copy()
    prepared.insert(0, "source_row_no", range(1, len(prepared) + 1))
    prepared.insert(0, "profile_id", 1)
    insert_by_name(
        connection,
        schema="app_meta",
        table_name="global_display_order_rule",
        frame=prepared,
    )


def load_global_display_order(connection: duckdb.DuckDBPyConnection) -> GlobalDisplayOrder:
    """열린 연결에서 공용 표시순서를 읽고 초기화 전이면 기존 오류를 전달한다."""
    metadata = load_profile_header(connection, "global_display_order")
    if metadata is None:
        raise RuntimeError("공용 표시순서가 초기화되지 않았습니다.")
    rules = load_global_display_order_rules(connection)
    return GlobalDisplayOrder(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        rules=rules,
    )


def replace_global_display_order(
    connection: duckdb.DuckDBPyConnection, prepared_rules: pd.DataFrame, *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_display_order", "global_display_order_rule")
    insert_global_display_order(
        connection,
        prepared_rules,
        version=version,
        source=source,
    )


def initialize_global_display_order(
    connection: duckdb.DuckDBPyConnection, prepared_fallback: pd.DataFrame
) -> None:
    """공용 표시순서가 없을 때 기존 리비전 또는 준비된 시드로 처음 저장한다."""
    existing = load_profile_header(connection, "global_display_order")
    if existing is None:
        migrated = load_existing_display_order(connection)
        if migrated is None:
            initial = prepared_fallback
            source = "초기 표시순서 시드"
        else:
            initial = prepare_global_display_order_rules(migrated)
            source = "기존 시나리오 표시순서 이관"
            if len(initial) < len(prepared_fallback):
                initial = prepared_fallback
                source = "초기 표시순서 시드"
        insert_global_display_order(
            connection,
            initial,
            version=1,
            source=source,
        )
