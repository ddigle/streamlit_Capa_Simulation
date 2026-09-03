# Purpose: Apply workbook-managed display order rules to Streamlit tables.

"""Apply workbook-managed display order rules to Streamlit tables."""

from dataclasses import dataclass

import pandas as pd

DISPLAY_ORDER_RULE_COLUMNS = [
    "정렬우선순위",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "값표시순서",
    "활성여부",
]
DISPLAY_ORDER_SCOPE_COLUMNS = ["페이지 구분", "탭 구분"]
LEGACY_SCOPE_COLUMN = "적용화면"
DISPLAY_ORDER_MODES = {"사용자지정", "오름차순", "내림차순"}
ROUTE_SEQUENCE_COLUMNS = ("STEP_SEQ", "MCP_SEQ")


@dataclass(frozen=True)
class PreparedDisplayOrder:
    """Validated display-order rules that can be reused within one rerun."""

    rules: pd.DataFrame


DisplayOrderInput = pd.DataFrame | PreparedDisplayOrder | None


def _prepare_display_order(display_order: pd.DataFrame) -> pd.DataFrame:
    missing = [
        column for column in DISPLAY_ORDER_RULE_COLUMNS if column not in display_order.columns
    ]
    if missing:
        raise ValueError(f"RQ_DISPLAY_ORDER 필수 컬럼이 없습니다: {', '.join(missing)}")

    if all(column in display_order.columns for column in DISPLAY_ORDER_SCOPE_COLUMNS):
        prepared = display_order[[*DISPLAY_ORDER_SCOPE_COLUMNS, *DISPLAY_ORDER_RULE_COLUMNS]].copy()
        required_scope_columns = DISPLAY_ORDER_SCOPE_COLUMNS
    elif LEGACY_SCOPE_COLUMN in display_order.columns:
        prepared = display_order[[LEGACY_SCOPE_COLUMN, *DISPLAY_ORDER_RULE_COLUMNS]].copy()
        prepared = prepared.rename(columns={LEGACY_SCOPE_COLUMN: "탭 구분"})
        prepared.insert(0, "페이지 구분", "")
        required_scope_columns = ["탭 구분"]
    else:
        raise ValueError(
            "RQ_DISPLAY_ORDER에 페이지 구분·탭 구분 또는 기존 적용화면 컬럼이 필요합니다."
        )

    text_columns = [
        "페이지 구분",
        "탭 구분",
        "분류컬럼",
        "정렬방식",
        "분류값",
        "활성여부",
    ]
    for column in text_columns:
        prepared[column] = prepared[column].astype("string").str.strip()
    prepared["활성여부"] = prepared["활성여부"].str.upper()
    prepared["정렬우선순위"] = pd.to_numeric(prepared["정렬우선순위"], errors="coerce")
    prepared["값표시순서"] = pd.to_numeric(prepared["값표시순서"], errors="coerce")

    required_values = prepared[
        [*required_scope_columns, "정렬우선순위", "분류컬럼", "정렬방식", "활성여부"]
    ]
    has_missing = any(required_values[column].isna().any() for column in required_values)
    has_blank = any(required_values[column].eq("").any() for column in required_values)
    if has_missing or has_blank:
        raise ValueError("RQ_DISPLAY_ORDER의 필수 설정값에 누락이 있습니다.")
    invalid_modes = sorted(set(prepared["정렬방식"].dropna()) - DISPLAY_ORDER_MODES)
    if invalid_modes:
        raise ValueError(f"RQ_DISPLAY_ORDER에 지원하지 않는 정렬방식이 있습니다: {invalid_modes}")
    invalid_active = sorted(set(prepared["활성여부"].dropna()) - {"Y", "N"})
    if invalid_active:
        raise ValueError(f"RQ_DISPLAY_ORDER 활성여부는 Y 또는 N이어야 합니다: {invalid_active}")
    return prepared


def prepare_display_order(display_order: DisplayOrderInput) -> PreparedDisplayOrder | None:
    """Validate a display-order profile once and make it reusable by sort helpers."""
    if display_order is None:
        return None
    if isinstance(display_order, PreparedDisplayOrder):
        return display_order
    return PreparedDisplayOrder(_prepare_display_order(display_order))


def _prepared_rules(display_order: DisplayOrderInput) -> pd.DataFrame | None:
    prepared = prepare_display_order(display_order)
    return None if prepared is None else prepared.rules


def apply_display_order(
    data: pd.DataFrame,
    display_order: DisplayOrderInput,
    page: str,
    tab: str | None = None,
    value_aliases: dict[str, dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Sort data using active rules for a page and tab."""
    prepared = _prepared_rules(display_order)
    if prepared is None:
        return data
    tab_name = tab or page
    rules = prepared.loc[
        prepared["활성여부"].eq("Y")
        & prepared["탭 구분"].eq(tab_name)
        & (prepared["페이지 구분"].eq("") | prepared["페이지 구분"].eq(page))
    ].copy()
    if rules.empty:
        return data

    aliases = value_aliases or {}
    for column, mapping in aliases.items():
        mask = rules["분류컬럼"].eq(column)
        rules.loc[mask, "분류값"] = rules.loc[mask, "분류값"].replace(mapping)

    rule_summary = rules[["정렬우선순위", "분류컬럼", "정렬방식"]].drop_duplicates()
    conflicts = rule_summary.groupby("분류컬럼").agg(
        정렬우선순위수=("정렬우선순위", "nunique"),
        정렬방식수=("정렬방식", "nunique"),
    )
    if conflicts.gt(1).any(axis=None):
        invalid_columns = conflicts.loc[conflicts.gt(1).any(axis=1)].index.tolist()
        raise ValueError(f"RQ_DISPLAY_ORDER의 컬럼 정렬 규칙이 충돌합니다: {invalid_columns}")

    rule_summary = rule_summary.sort_values("정렬우선순위", kind="stable")
    result = data.copy()
    helper_columns: list[str] = []
    ascending: list[bool] = []

    for position, rule in enumerate(rule_summary.itertuples(index=False)):
        column = str(rule.분류컬럼)
        mode = str(rule.정렬방식)
        if column not in result.columns:
            continue

        helper = f"__display_order_{position}"
        column_rules = rules.loc[rules["분류컬럼"].eq(column)]
        if mode == "사용자지정":
            custom = column_rules[["분류값", "값표시순서"]]
            if custom.isna().any(axis=None):
                raise ValueError(
                    "RQ_DISPLAY_ORDER의 사용자지정 규칙에 값이 누락되었습니다: "
                    f"{page}.{tab_name}.{column}"
                )
            duplicated = custom["분류값"].duplicated(keep=False)
            if duplicated.any():
                values = custom.loc[duplicated, "분류값"].drop_duplicates().tolist()
                raise ValueError(
                    "RQ_DISPLAY_ORDER의 사용자지정 값이 중복되었습니다: "
                    f"{page}.{tab_name}.{column} {values}"
                )
            mapping = dict(zip(custom["분류값"], custom["값표시순서"], strict=True))
            result[helper] = result[column].astype("string").map(mapping).fillna(float("inf"))
            ascending.append(True)
        else:
            result[helper] = result[column].astype("string")
            ascending.append(mode == "오름차순")
        helper_columns.append(helper)

    if not helper_columns:
        return result

    result["__display_original_order"] = range(len(result))
    sorted_result = result.sort_values(
        [*helper_columns, "__display_original_order"],
        ascending=[*ascending, True],
        kind="stable",
        na_position="last",
    )
    return sorted_result.drop(columns=[*helper_columns, "__display_original_order"]).reset_index(
        drop=True
    )


def classification_columns_in_display_order(
    columns: list[str],
    display_order: DisplayOrderInput,
    page: str,
    tab: str | None = None,
) -> list[str]:
    """Resolve the visible hierarchy while keeping route identifiers at the bottom."""
    available = list(dict.fromkeys(columns))
    route_columns = [column for column in ROUTE_SEQUENCE_COLUMNS if column in available]
    non_route_columns = [column for column in available if column not in route_columns]
    prepared = _prepared_rules(display_order)
    if prepared is None:
        return [*non_route_columns, *route_columns]
    tab_name = tab or page
    rules = prepared.loc[
        prepared["활성여부"].eq("Y")
        & prepared["탭 구분"].eq(tab_name)
        & (prepared["페이지 구분"].eq("") | prepared["페이지 구분"].eq(page))
    ]
    configured = (
        rules[["정렬우선순위", "분류컬럼"]]
        .drop_duplicates()
        .sort_values("정렬우선순위", kind="stable")["분류컬럼"]
        .astype(str)
        .tolist()
    )
    configured_non_route = [column for column in configured if column in non_route_columns]
    unconfigured_non_route = [
        column for column in non_route_columns if column not in configured_non_route
    ]
    configured_route = [column for column in configured if column in route_columns]
    unconfigured_route = [column for column in route_columns if column not in configured_route]
    return [
        *configured_non_route,
        *unconfigured_non_route,
        *configured_route,
        *unconfigured_route,
    ]


def reorder_display_columns(
    data: pd.DataFrame,
    classification_columns: list[str],
    display_order: DisplayOrderInput,
    page: str,
    tab: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Place configured classifications before value columns and return their order."""
    ordered = classification_columns_in_display_order(
        classification_columns,
        display_order,
        page,
        tab,
    )
    classification_set = set(classification_columns)
    remaining = [column for column in data.columns if column not in classification_set]
    return data.reindex(columns=[*ordered, *remaining]), ordered
