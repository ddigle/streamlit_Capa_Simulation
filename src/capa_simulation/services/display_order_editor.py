"""Validation and scope replacement for web-managed display-order rules."""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.reference_transformer import transform_display_order

DISPLAY_ORDER_COLUMNS = (
    "페이지 구분",
    "탭 구분",
    "정렬우선순위",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "값표시순서",
    "활성여부",
)
DISPLAY_ORDER_RULE_COLUMNS = DISPLAY_ORDER_COLUMNS[2:]


def validate_display_order(source: pd.DataFrame) -> pd.DataFrame:
    """Return normalized rules or reject every incomplete/conflicting row."""
    if not isinstance(source, pd.DataFrame):
        raise TypeError("표시순서 설정은 pandas DataFrame이어야 합니다.")
    missing = [column for column in DISPLAY_ORDER_COLUMNS if column not in source.columns]
    if missing:
        raise ValueError(f"표시순서 필수 컬럼이 없습니다: {', '.join(missing)}")
    selected = source.loc[:, list(DISPLAY_ORDER_COLUMNS)].dropna(how="all").reset_index(drop=True)
    normalized = transform_display_order(selected)
    if len(normalized) != len(selected):
        raise ValueError("표시순서 설정에 빈 값, 잘못된 정렬방식 또는 정수가 아닌 순서가 있습니다.")
    if normalized.empty:
        return normalized
    if normalized["정렬우선순위"].le(0).any():
        raise ValueError("정렬우선순위는 1 이상의 정수여야 합니다.")
    custom = normalized["정렬방식"].eq("사용자지정")
    if normalized.loc[custom, "값표시순서"].le(0).any():
        raise ValueError("사용자지정 값표시순서는 1 이상의 정수여야 합니다.")

    scope_priority = ["페이지 구분", "탭 구분", "정렬우선순위"]
    priority_conflicts = (
        normalized.groupby(scope_priority, dropna=False)["분류컬럼"].nunique().gt(1)
    )
    if priority_conflicts.any():
        raise ValueError("같은 페이지·탭·정렬우선순위에 서로 다른 분류컬럼이 있습니다.")

    scope_column = ["페이지 구분", "탭 구분", "분류컬럼"]
    rule_conflicts = normalized.groupby(scope_column, dropna=False).agg(
        우선순위수=("정렬우선순위", "nunique"),
        정렬방식수=("정렬방식", "nunique"),
    )
    if rule_conflicts.gt(1).any(axis=None):
        raise ValueError("같은 페이지·탭·분류컬럼의 우선순위 또는 정렬방식이 충돌합니다.")

    custom_rules = normalized.loc[custom]
    custom_key = [*scope_column, "분류값"]
    if custom_rules.duplicated(custom_key).any():
        raise ValueError("사용자지정 분류값이 같은 페이지·탭·분류컬럼에서 중복됩니다.")
    custom_order_key = [*scope_column, "값표시순서"]
    if custom_rules.duplicated(custom_order_key).any():
        raise ValueError("사용자지정 값표시순서가 같은 페이지·탭·분류컬럼에서 중복됩니다.")

    noncustom_counts = normalized.loc[~custom].groupby(scope_column, dropna=False).size()
    if noncustom_counts.gt(1).any():
        raise ValueError("오름차순·내림차순 규칙은 분류컬럼마다 한 행만 입력하세요.")
    return normalized.sort_values(
        ["페이지 구분", "탭 구분", "정렬우선순위", "값표시순서"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)


def replace_display_order_scope(
    current: pd.DataFrame,
    page: str,
    tab: str,
    edited_rules: pd.DataFrame,
) -> pd.DataFrame:
    """Replace one page/tab rule set while preserving all other scopes."""
    page_name = _required_text(page, "페이지 구분")
    tab_name = _required_text(tab, "탭 구분")
    missing = [column for column in DISPLAY_ORDER_RULE_COLUMNS if column not in edited_rules]
    if missing:
        raise ValueError(f"편집 규칙 컬럼이 없습니다: {', '.join(missing)}")
    normalized_current = validate_display_order(current)
    rules = edited_rules.loc[:, list(DISPLAY_ORDER_RULE_COLUMNS)].dropna(how="all").copy()
    rules.insert(0, "탭 구분", tab_name)
    rules.insert(0, "페이지 구분", page_name)
    mask = normalized_current["페이지 구분"].eq(page_name) & normalized_current["탭 구분"].eq(
        tab_name
    )
    merged = pd.concat([normalized_current.loc[~mask], rules], ignore_index=True)
    return validate_display_order(merged)


def _required_text(value: str, label: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
    return result
