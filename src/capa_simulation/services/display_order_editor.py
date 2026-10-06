# Purpose: Validation and scope replacement for web-managed display-order rules.

"""Validation and scope replacement for web-managed display-order rules."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import NamedTuple

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
from capa_simulation.services.frame_contracts import match_key, require_columns

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
# 중복 오류문에 적는 범위 수. 그 뒤는 「외 N건」으로 줄인다 — 붙여넣은 표 전체가 잘못이면
# 오류문이 화면을 덮는다.
CLASH_REPORT_LIMIT = 5
_SCOPE_COLUMNS = ("페이지 구분", "탭 구분", "분류컬럼")


class DisplayOrderValueClashError(ValueError):
    """사용자지정 분류값이 맞대어 보는 형태(`match_key`)로 겹친다.

    저장·가져오기는 이것으로 막는다. 따로 둔 까닭은 **이미 저장된 프로필**을 읽는 길이 이것만
    견디게 하려는 것이다 — 이 규칙 전에 저장된 프로필에 `Top`·`TOP` 이 함께 있으면, 기동마다
    도는 보강이나 Admin 표시순서 탭이 이 오류로 죽어 고칠 화면에조차 못 들어간다.
    """


# 겹침 하나를 가리키는 키 — (페이지 구분, 탭 구분, 분류컬럼, `match_key`).
ClashKey = tuple[str, str, str, str]


class ValueClash(NamedTuple):
    """한 페이지·탭·분류컬럼 안에서 `match_key` 가 같은 활성 사용자지정 분류값 묶음."""

    page: str
    tab: str
    column: str
    key: str
    # 적은 표기 그대로다. 줄인 키(`top`)로 알리면 어느 행인지 찾을 수 없다.
    values: tuple[str, ...]

    @property
    def identity(self) -> ClashKey:
        return (self.page, self.tab, self.column, self.key)


def custom_value_clashes(rules: pd.DataFrame) -> list[ValueClash]:
    """활성 사용자지정 규칙 가운데 같은 페이지·탭·분류컬럼에서 `match_key` 가 겹치는 값들.

    적용(`display_order.apply_display_order`)이 분류값을 맞대는 형태와 같은 키로 보고, 적용처럼
    **활성(`활성여부 = Y`) 규칙만** 본다 — 대소문자와 앞뒤 공백만 다른 두 값은 같은 값이고, 꺼 둔
    규칙은 화면에 걸리지 않는다. 글자 그대로 보면 저장은 통과하고 그 범위를 쓰는 화면에서야
    ValueError 가 났다. 돌려주는 값은 **원래 표기** 그대로다.
    """
    if rules.empty or not {*_SCOPE_COLUMNS, "정렬방식", "분류값"} <= set(rules.columns):
        return []
    custom = rules["정렬방식"].eq("사용자지정")
    if "활성여부" in rules.columns:
        custom &= rules["활성여부"].astype("string").str.strip().str.upper().eq("Y").fillna(False)
    active = rules.loc[custom]
    if active.empty:
        return []
    keyed = active.loc[:, [*_SCOPE_COLUMNS, "분류값"]].assign(__key=match_key(active["분류값"]))
    duplicated = keyed.duplicated([*_SCOPE_COLUMNS, "__key"], keep=False)
    clashes: list[ValueClash] = []
    for group, rows in keyed.loc[duplicated].groupby([*_SCOPE_COLUMNS, "__key"], sort=False):
        page, tab, column, key = (str(value) for value in group)
        clashes.append(ValueClash(page, tab, column, key, tuple(rows["분류값"].astype(str))))
    return clashes


def clashes_outside_scope(rules: pd.DataFrame, page: str, tab: str) -> frozenset[ClashKey]:
    """고르지 않은 페이지·탭에 **이미** 있는 겹침. 한 범위만 고치는 저장이 그것에 막히지 않게 한다.

    직접 편집은 한 범위씩 저장한다. 저장 검사가 프로필 전체의 겹침을 보면, 두 범위에 예전 겹침이
    있을 때 어느 쪽을 고쳐도 다른 쪽 때문에 막혀 고칠 길이 없다. 고르는 범위 안의 겹침은 여기 들지
    않으므로 그 범위는 언제나 깨끗해야 저장된다.
    """
    return frozenset(
        clash.identity
        for clash in custom_value_clashes(rules)
        if (clash.page, clash.tab) != (page, tab)
    )


def describe_value_clashes(clashes: Sequence[ValueClash]) -> str:
    """겹친 값을 범위마다 한 덩어리로 적는다. 앞 `CLASH_REPORT_LIMIT` 개만, 나머지는 건수."""
    parts = [
        f"{clash.page} › {clash.tab} › {clash.column}: "
        + " · ".join(f"`{value}`" for value in clash.values)
        for clash in clashes[:CLASH_REPORT_LIMIT]
    ]
    rest = len(clashes) - CLASH_REPORT_LIMIT
    if rest > 0:
        parts.append(f"외 {rest}건")
    return "; ".join(parts)


def reject_value_clashes(rules: pd.DataFrame, *, tolerated: Collection[ClashKey] = ()) -> None:
    """활성 사용자지정 분류값이 겹치면 막는다. `tolerated` 의 겹침(다른 범위에 있던 것)만 넘긴다."""
    clashes = [clash for clash in custom_value_clashes(rules) if clash.identity not in tolerated]
    if clashes:
        raise DisplayOrderValueClashError(
            "사용자지정 분류값이 같은 페이지·탭·분류컬럼에서 중복됩니다(대소문자·앞뒤 공백만 "
            "다른 값도 같은 값으로 봅니다): " + describe_value_clashes(clashes)
        )


def validate_display_order(
    source: pd.DataFrame,
    *,
    allow_value_clashes: bool = False,
    tolerated_clashes: Collection[ClashKey] = (),
) -> pd.DataFrame:
    """Return normalized rules or reject every incomplete/conflicting row.

    `allow_value_clashes` 는 **이미 저장된 프로필을 읽는 길**만 켠다(기동 보강·Admin 탭 열기·
    내려받기). `tolerated_clashes` 는 범위 하나를 고치는 직접 편집 저장이 **다른 범위에 이미 있던**
    겹침만 넘기게 한다(`clashes_outside_scope`). 어느 쪽이든 글자까지 같은 중복은 예전처럼 막고,
    붙여넣기·CSV 처럼 프로필 전체를 바꾸는 저장은 둘 다 끄고 부른다.
    """
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
    if not allow_value_clashes:
        reject_value_clashes(custom_rules, tolerated=tolerated_clashes)
    # 겹침 검사는 화면에 걸리는 활성 규칙만 본다. 글자까지 같은 중복은 꺼 둔 규칙도 막는다 —
    # 전부터 그랬고, 켜는 순간 겹친다.
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
    """Replace one page/tab rule set while preserving all other scopes.

    지금 프로필은 겹친 값을 견디며 읽고(저장된 그대로다), 합친 결과는 **고르는 범위 안에서**
    겹침이 없어야 한다. 다른 범위에 이미 있던 겹침은 넘긴다 — 그것까지 막으면 두 범위에 겹침이
    있을 때 어느 쪽도 고쳐 저장할 수 없다. 저장 사슬은 같은 `clashes_outside_scope` 를 받는다.
    """
    page_name = _required_text(page, "페이지 구분")
    tab_name = _required_text(tab, "탭 구분")
    missing = [column for column in DISPLAY_ORDER_RULE_COLUMNS if column not in edited_rules]
    if missing:
        raise ValueError(f"편집 규칙 컬럼이 없습니다: {', '.join(missing)}")
    normalized_current = validate_display_order(current, allow_value_clashes=True)
    rules = edited_rules.loc[:, list(DISPLAY_ORDER_RULE_COLUMNS)].dropna(how="all").copy()
    rules.insert(0, "탭 구분", tab_name)
    rules.insert(0, "페이지 구분", page_name)
    mask = normalized_current["페이지 구분"].eq(page_name) & normalized_current["탭 구분"].eq(
        tab_name
    )
    merged = pd.concat([normalized_current.loc[~mask], rules], ignore_index=True)
    return validate_display_order(
        merged, tolerated_clashes=clashes_outside_scope(normalized_current, page_name, tab_name)
    )


def ensure_route_sequence_rules(
    source: pd.DataFrame,
    *,
    allow_value_clashes: bool = False,
    tolerated_clashes: Collection[ClashKey] = (),
) -> pd.DataFrame:
    """Keep STEP and MCP as the final configured hierarchy in route-aware scopes."""
    normalized = validate_display_order(
        source, allow_value_clashes=allow_value_clashes, tolerated_clashes=tolerated_clashes
    )
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
    return validate_display_order(
        result, allow_value_clashes=allow_value_clashes, tolerated_clashes=tolerated_clashes
    )


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
        raise ValueError(f"RQ_DISPLAY_ORDER {label} 값은 정수여야 합니다.")
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
