# Purpose: Validation and scope replacement for web-managed display-order rules.

"""Validation and scope replacement for web-managed display-order rules."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from capa_simulation.services.display_order_scopes import (
    PAGE_CALCULATION,
    PAGE_REFERENCE,
    TAB_LOT_RATIO,
    TAB_REQUIRED,
    TAB_UNIT_CAPACITY,
    TAB_UPEH,
    TAB_WF_RATIO,
)
from capa_simulation.services.frame_contracts import require_columns

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
ROUTE_SEQUENCE_COLUMNS = ("STEP_SEQ", "MCP_SEQ")
ROUTE_SEQUENCE_SCOPES = (
    (PAGE_CALCULATION, TAB_UNIT_CAPACITY),
    (PAGE_REFERENCE, TAB_UPEH),
    (PAGE_REFERENCE, TAB_LOT_RATIO),
    (PAGE_REFERENCE, TAB_WF_RATIO),
    (PAGE_CALCULATION, TAB_REQUIRED),
)


def validate_display_order(source: pd.DataFrame) -> pd.DataFrame:
    """Return normalized rules or reject every incomplete/conflicting row."""
    if not isinstance(source, pd.DataFrame):
        raise TypeError("표시순서 설정은 pandas DataFrame이어야 합니다.")
    require_columns(source, DISPLAY_ORDER_COLUMNS, "표시순서")
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


def ensure_route_sequence_rules(source: pd.DataFrame) -> pd.DataFrame:
    """Keep STEP and MCP as the final configured hierarchy in route-aware scopes."""
    normalized = validate_display_order(source)
    result = normalized.copy()
    for page, tab in ROUTE_SEQUENCE_SCOPES:
        scope = result["페이지 구분"].eq(page) & result["탭 구분"].eq(tab)
        if not scope.any():
            continue
        route_rows = scope & result["분류컬럼"].isin(ROUTE_SEQUENCE_COLUMNS)
        preserved_route_rules = {
            column: result.loc[scope & result["분류컬럼"].eq(column)].copy()
            for column in ROUTE_SEQUENCE_COLUMNS
        }
        non_route = result.loc[scope & ~route_rows]
        maximum_priority = int(non_route["정렬우선순위"].max()) if not non_route.empty else 0
        result = result.loc[~route_rows].copy()
        additions: list[dict[str, object]] = []
        for offset, column in enumerate(ROUTE_SEQUENCE_COLUMNS, start=1):
            rules = preserved_route_rules[column]
            if rules.empty:
                additions.append(
                    {
                        "페이지 구분": page,
                        "탭 구분": tab,
                        "정렬우선순위": maximum_priority + offset,
                        "분류컬럼": column,
                        "정렬방식": "오름차순",
                        "분류값": pd.NA,
                        "값표시순서": pd.NA,
                        "활성여부": "Y",
                    }
                )
            else:
                rules.loc[:, "정렬우선순위"] = maximum_priority + offset
                rules.loc[:, "활성여부"] = "Y"
                for row in rules.itertuples(index=False, name=None):
                    additions.append(dict(zip(DISPLAY_ORDER_COLUMNS, row, strict=True)))
        result = pd.DataFrame(
            [*result.to_dict("records"), *additions],
            columns=DISPLAY_ORDER_COLUMNS,
        )
    return validate_display_order(result)


def _required_text(value: str, label: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
    return result


def transform_display_order(source: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "페이지 구분",
        "탭 구분",
        "정렬우선순위",
        "분류컬럼",
        "정렬방식",
        "분류값",
        "값표시순서",
        "활성여부",
    ]
    require_columns(source, columns, "RQ_DISPLAY_ORDER")
    result = source.loc[:, columns].copy()
    text_columns = [
        "페이지 구분",
        "탭 구분",
        "분류컬럼",
        "정렬방식",
        "분류값",
        "활성여부",
    ]
    for column in text_columns:
        result[column] = result[column].astype("string").str.strip()
    result["활성여부"] = result["활성여부"].str.upper()
    result["정렬우선순위"] = _nullable_integer(result["정렬우선순위"], "정렬우선순위")
    result["값표시순서"] = _nullable_integer(result["값표시순서"], "값표시순서")

    required_text_columns = [
        "페이지 구분",
        "탭 구분",
        "분류컬럼",
        "정렬방식",
        "활성여부",
    ]
    required_text_valid = pd.Series(True, index=result.index, dtype=bool)
    for column in required_text_columns:
        required_text_valid &= result[column].notna() & result[column].ne("")
    allowed_sort = result["정렬방식"].isin(["사용자지정", "오름차순", "내림차순"])
    allowed_active = result["활성여부"].isin(["Y", "N"])
    custom = result["정렬방식"].eq("사용자지정")
    custom_valid = (~custom) | (
        result["분류값"].notna() & result["분류값"].ne("") & result["값표시순서"].notna()
    )
    mask = (
        required_text_valid
        & result["정렬우선순위"].notna()
        & allowed_sort
        & allowed_active
        & custom_valid
    )
    return result.loc[mask].reset_index(drop=True)


def _nullable_integer(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    source_missing = series.isna() | series.astype("string").str.strip().eq("").fillna(False)
    invalid = numeric.isna() & ~source_missing
    fractional = numeric.notna() & numeric.mod(1).ne(0)
    if invalid.any() or fractional.any():
        raise ValueError(f"RQ_DISPLAY_ORDER {label}은 정수여야 합니다.")
    return numeric.astype("Int64")


def display_label_mistakes(
    rules: pd.DataFrame,
    column_labels: Mapping[str, str],
) -> dict[str, str]:
    """`분류컬럼` 에 원본 컬럼명 대신 화면 표시명을 적은 항목. `{적은 값: 원본 컬럼명}`.

    `apply_display_order` 는 프레임에 없는 분류컬럼 규칙을 **조용히 건너뛴다**. 그래서
    `Customer` 대신 화면에 보이는 `거래선` 을 적으면 저장은 통과하는데 정렬은 걸리지 않고,
    사용자는 "설정했는데 왜 안 되지" 가 된다. 저장을 막지는 않고 화면이 물어보게 한다.

    표시명이 다른 범위에서는 실제 컬럼일 수 있다(`구분` 이 그렇다). 그래서 판정이 아니라
    **제안**이고, 문구도 단정하지 않는다.
    """
    if "분류컬럼" not in rules.columns:
        return {}
    by_label = {
        str(label): str(column) for column, label in column_labels.items() if str(label).strip()
    }
    typed = {str(value).strip() for value in rules["분류컬럼"].dropna()}
    return {value: by_label[value] for value in sorted(typed) if value in by_label}
