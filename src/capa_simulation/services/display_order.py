# Purpose: Apply workbook-managed display order rules to Streamlit tables.

"""Apply workbook-managed display order rules to Streamlit tables."""

from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.frame_contracts import match_key, require_columns, scalar_match_key
from capa_simulation.services.product_type import (
    EDP_TOP_DIVISION,
    SOURCE_TOP_DIVISION,
    WF_DIVISION_COLUMN,
)

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
    require_columns(display_order, DISPLAY_ORDER_RULE_COLUMNS, "RQ_DISPLAY_ORDER")

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


def _with_edp_top_rule(rules: pd.DataFrame) -> pd.DataFrame:
    """`WF 구분` 의 `Top` 규칙에서 `Top_e` 규칙을 파생해 바로 뒤에 끼운다.

    표시순서는 **입력 데이터**다. 원천 어디에도 `Top_e` 가 없으므로 사용자가 관리하는
    `RQ_DISPLAY_ORDER` 에도 없다. 규칙이 없으면 `apply_display_order` 가 그 값을 무한대로
    보내 화면 맨 뒤로 밀어 버린다 — 오류는 안 나고 순서만 조용히 틀린다.

    그래서 `WF 구분` 변환과 같은 원칙을 쓴다. 입력은 그대로 받고, 앱이 파생한다.
    `Top` 바로 다음 자리에 넣기 위해 그 그룹의 `값표시순서` 를 다시 매긴다.
    """
    # 규칙에 적힌 표기가 `TOP`·`top` 이어도 같은 규칙으로 본다. 여기서 글자 그대로 맞추면
    # 파생이 일어나지 않고, `Top_e` 가 규칙 없는 값이 되어 화면 맨 뒤로 조용히 밀린다.
    rule_keys = match_key(rules["분류값"])
    target = rules["분류컬럼"].eq(WF_DIVISION_COLUMN) & rules["정렬방식"].eq("사용자지정")
    tops = rules.loc[target & rule_keys.eq(SOURCE_TOP_DIVISION.casefold())]
    if tops.empty:
        return rules

    group_keys = ["페이지 구분", "탭 구분", "분류컬럼"]
    derived = tops.copy()
    derived["분류값"] = EDP_TOP_DIVISION
    # 이미 사용자가 직접 넣어 둔 그룹에는 다시 넣지 않는다.
    existing = set(
        map(
            tuple,
            rules.loc[target & rule_keys.eq(EDP_TOP_DIVISION.casefold()), group_keys]
            .to_numpy()
            .tolist(),
        )
    )
    if existing:
        keep = ~derived[group_keys].apply(lambda row: tuple(row) in existing, axis=1)
        derived = derived.loc[keep]
    if derived.empty:
        return rules

    combined = pd.concat([rules, derived], ignore_index=True)
    # `Top` 과 같은 순서값을 갖게 되므로 동률이다. `Top` 다음에 오도록 보조 키를 둔 뒤
    # 그룹 안에서 1부터 다시 매긴다 — 중복 검사를 통과해야 하기 때문이다.
    tie = match_key(combined["분류값"]).eq(EDP_TOP_DIVISION.casefold()).astype(int)
    renumber = combined["분류컬럼"].eq(WF_DIVISION_COLUMN) & combined["정렬방식"].eq("사용자지정")
    ordered = (
        combined.loc[renumber]
        .assign(__tie=tie[renumber])
        .sort_values([*group_keys, "값표시순서", "__tie"], kind="stable")
    )
    ordered["값표시순서"] = (
        ordered.groupby(group_keys, dropna=False).cumcount().add(1).astype("Int64")
    )
    combined.loc[ordered.index, "값표시순서"] = ordered["값표시순서"]
    return combined.sort_values(
        ["페이지 구분", "탭 구분", "정렬우선순위", "분류컬럼", "값표시순서"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)


def _prepared_rules(display_order: DisplayOrderInput) -> pd.DataFrame | None:
    prepared = prepare_display_order(display_order)
    return None if prepared is None else _with_edp_top_rule(prepared.rules)


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
        if not mask.any():
            continue
        # 별칭(공정 표시명 → 원본 공정명)도 대소문자를 가리지 않는다. 여기서 못 바꾸면 그 값은
        # 원본 공정명과도 어긋난 채 남아 규칙이 통째로 헛돈다.
        folded = {scalar_match_key(alias): value for alias, value in mapping.items()}
        original = rules.loc[mask, "분류값"]
        rules.loc[mask, "분류값"] = match_key(original).map(folded).fillna(original)

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
            # 중복도 맞대어 보는 형태로 판정한다. `Top` 과 `TOP` 을 따로 두면 둘 다 같은
            # 값에 걸려 하나가 조용히 이긴다 — 어느 쪽이 이길지는 행 순서가 정한다.
            keys = match_key(custom["분류값"])
            duplicated = keys.duplicated(keep=False)
            if duplicated.any():
                values = custom.loc[duplicated, "분류값"].drop_duplicates().tolist()
                raise ValueError(
                    "RQ_DISPLAY_ORDER의 사용자지정 값이 중복되었습니다: "
                    f"{page}.{tab_name}.{column} {values}"
                )
            mapping = dict(zip(keys, custom["값표시순서"], strict=True))
            result[helper] = match_key(result[column]).map(mapping).fillna(float("inf"))
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
