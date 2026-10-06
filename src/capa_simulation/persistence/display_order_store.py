# Purpose: 시나리오와 분리된 공용 표시순서 프로필의 검증·이관·저장을 담당한다.

"""시나리오와 분리된 공용 표시순서 프로필의 검증·이관·저장을 담당한다."""

from __future__ import annotations

from collections.abc import Collection

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
from capa_simulation.services.display_order_editor import ClashKey, ensure_route_sequence_rules
from capa_simulation.services.frame_contracts import require_exact_columns

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
    require_exact_columns(frame.columns, GLOBAL_DISPLAY_ORDER_COLUMNS, "공용 표시순서 컬럼")
    if frame.empty:
        raise ValueError("공용 표시순서에는 한 개 이상의 규칙이 필요합니다.")


def prepare_global_display_order_rules(
    frame: pd.DataFrame,
    *,
    allow_value_clashes: bool = False,
    tolerated_clashes: Collection[ClashKey] = (),
) -> pd.DataFrame:
    """저장 전 검증과 경로 식별 컬럼 보강.

    겹친 분류값 허용(`allow_value_clashes`)은 이미 있는 값을 옮길 때만 켠다. 범위 하나를 고치는
    직접 편집 저장은 다른 범위에 이미 있던 겹침만 `tolerated_clashes` 로 넘긴다.
    """
    validate_global_display_order_frame(frame)
    return ensure_route_sequence_rules(
        frame, allow_value_clashes=allow_value_clashes, tolerated_clashes=tolerated_clashes
    )


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
            # 사용자가 지금 저장하는 값이 아니라 예전에 저장된 값을 옮기는 것이다. 대소문자만
            # 다른 분류값이 섞여 있어도 막지 않는다 — 막으면 앱이 기동하지 못한다. 그 값은
            # 그 범위를 쓰는 화면과 Admin 표시순서 탭이 알린다.
            initial = prepare_global_display_order_rules(migrated, allow_value_clashes=True)
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
