# Purpose: Atomic route STEP edits shared by the four route-owned reference tables.

"""Atomic route STEP edits shared by the four route-owned reference tables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.frame_contracts import (
    normalize_demand_basis,
    normalize_demand_basis_value,
)

ROUTE_GROUP_COLUMNS = (
    "Area_Name",
    "공정",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "소요기준",
)
STEP_PAIR_COLUMNS = ("MCP_SEQ", "STEP_SEQ")
PERFORMANCE_ROUTE_COLUMNS = (
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
)
REQB_VARIANT_COLUMNS = ("Capa Code", "Customer", "CS")
ROUTE_TABLES = ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO")

_REQB_COLUMNS = (
    "생산계획년월",
    *ROUTE_GROUP_COLUMNS,
    *REQB_VARIANT_COLUMNS,
    *STEP_PAIR_COLUMNS,
)
_UPEH_COLUMNS = (
    "생산계획년월",
    *ROUTE_GROUP_COLUMNS,
    *STEP_PAIR_COLUMNS,
)
_RATIO_COLUMNS = PERFORMANCE_ROUTE_COLUMNS


@dataclass(frozen=True)
class StepChangeResult:
    """Selected-month replacement tables and an audit-friendly impact summary."""

    replacements: dict[str, pd.DataFrame]
    affected_months: tuple[int, ...]
    affected_reqb_rows: int
    affected_variants: int


def route_step_summary(reqb: pd.DataFrame) -> pd.DataFrame:
    """Count distinct MCP/STEP pairs without multiplying Capa/Customer/CS variants."""
    data = _prepare(reqb, _REQB_COLUMNS, "RQ_REQB")
    group_columns = ["생산계획년월", *ROUTE_GROUP_COLUMNS]
    if data.empty:
        return pd.DataFrame(columns=[*group_columns, "STEP 수", "수요 변형 수"])

    distinct_steps = data[[*group_columns, *STEP_PAIR_COLUMNS]].drop_duplicates()
    step_counts = (
        distinct_steps.groupby(group_columns, as_index=False, dropna=False)
        .size()
        .rename(columns={"size": "STEP 수"})
    )
    distinct_variants = data[[*group_columns, *REQB_VARIANT_COLUMNS]].drop_duplicates()
    variant_counts = (
        distinct_variants.groupby(group_columns, as_index=False, dropna=False)
        .size()
        .rename(columns={"size": "수요 변형 수"})
    )
    return (
        step_counts.merge(variant_counts, on=group_columns, validate="one_to_one")
        .sort_values(group_columns, kind="stable")
        .reset_index(drop=True)
    )


def route_step_catalog(upeh: pd.DataFrame, reqb: pd.DataFrame) -> pd.DataFrame:
    """Return one selectable row per route group and distinct MCP/STEP pair."""
    performance = _prepare(upeh, _UPEH_COLUMNS, "RQ_UPEH")
    paths = _prepare(reqb, _REQB_COLUMNS, "RQ_REQB")
    catalog_columns = [
        *ROUTE_GROUP_COLUMNS,
        *STEP_PAIR_COLUMNS,
        "적용월수",
        "적용월",
        "수요 변형 수",
    ]
    if performance.empty or paths.empty:
        return pd.DataFrame(columns=catalog_columns)

    route_columns = [*ROUTE_GROUP_COLUMNS, *STEP_PAIR_COLUMNS]
    months = (
        performance[["생산계획년월", *route_columns]]
        .drop_duplicates()
        .groupby(route_columns, as_index=False, dropna=False)["생산계획년월"]
        .agg(
            적용월수="nunique",
            적용월=lambda values: ", ".join(str(int(value)) for value in sorted(pd.unique(values))),
        )
    )
    variants = paths[[*route_columns, *REQB_VARIANT_COLUMNS]].drop_duplicates()
    variant_counts = (
        variants.groupby(route_columns, as_index=False, dropna=False)
        .size()
        .rename(columns={"size": "수요 변형 수"})
    )
    result: pd.DataFrame = (
        months.merge(variant_counts, on=route_columns, how="inner", validate="one_to_one")
        .sort_values(route_columns, kind="stable")
        .reset_index(drop=True)
        .reindex(columns=catalog_columns)
    )
    return result


def clone_route_step(
    tables: Mapping[str, pd.DataFrame],
    route: Mapping[str, object],
    *,
    source_mcp_seq: str,
    source_step_seq: str,
    new_mcp_seq: str,
    new_step_seq: str,
) -> StepChangeResult:
    """Clone one route STEP across every matching Capa Code/Customer/CS variant."""
    prepared = _prepare_route_tables(tables)
    normalized_route = _normalize_route(route)
    source_pair = _normalize_pair(source_mcp_seq, source_step_seq, "복제 원본")
    target_pair = _normalize_pair(new_mcp_seq, new_step_seq, "신규")
    if source_pair == target_pair:
        raise ValueError("신규 MCP_SEQ·STEP_SEQ는 복제 원본과 달라야 합니다.")

    upeh = prepared["RQ_UPEH"]
    reqb = prepared["RQ_REQB"]
    source_upeh_mask = _route_pair_mask(upeh, normalized_route, source_pair)
    source_reqb_mask = _route_pair_mask(reqb, normalized_route, source_pair)
    source_upeh = upeh.loc[source_upeh_mask].copy()
    source_reqb = reqb.loc[source_reqb_mask].copy()
    if source_upeh.empty:
        raise ValueError("선택한 복제 원본 STEP의 RQ_UPEH 행이 없습니다.")
    if source_reqb.empty:
        raise ValueError("선택한 복제 원본 STEP에 연결된 RQ_REQB 수요 변형이 없습니다.")

    affected_months = tuple(sorted(int(month) for month in source_reqb["생산계획년월"].unique()))
    source_upeh = source_upeh.loc[source_upeh["생산계획년월"].isin(affected_months)].copy()
    _assert_one_upeh_per_month(source_upeh, affected_months)
    _assert_unique_reqb(source_reqb)

    target_upeh_mask = _route_pair_mask(upeh, normalized_route, target_pair)
    target_reqb_mask = _route_pair_mask(reqb, normalized_route, target_pair)
    target_upeh_mask &= upeh["생산계획년월"].isin(affected_months)
    target_reqb_mask &= reqb["생산계획년월"].isin(affected_months)
    if target_upeh_mask.any() or target_reqb_mask.any():
        raise ValueError("신규 MCP_SEQ·STEP_SEQ 조합이 적용 대상 월에 이미 존재합니다.")

    cloned_upeh = source_upeh.copy()
    cloned_upeh["MCP_SEQ"], cloned_upeh["STEP_SEQ"] = target_pair
    cloned_reqb = source_reqb.copy()
    cloned_reqb["MCP_SEQ"], cloned_reqb["STEP_SEQ"] = target_pair

    replacements = dict(prepared)
    replacements["RQ_UPEH"] = _append_like(upeh, cloned_upeh)
    replacements["RQ_REQB"] = _append_like(reqb, cloned_reqb)
    for table_name in ("RQ_LOT_RATIO", "RQ_WF_RATIO"):
        replacements[table_name] = _clone_ratio_rows(
            prepared[table_name],
            source_upeh,
            target_pair,
            table_name,
        )

    return StepChangeResult(
        replacements=replacements,
        affected_months=affected_months,
        affected_reqb_rows=len(source_reqb),
        affected_variants=_variant_count(source_reqb),
    )


def delete_route_step(
    tables: Mapping[str, pd.DataFrame],
    route: Mapping[str, object],
    *,
    mcp_seq: str,
    step_seq: str,
) -> StepChangeResult:
    """Delete one route STEP while preserving ratios still used by another basis."""
    prepared = _prepare_route_tables(tables)
    normalized_route = _normalize_route(route)
    pair = _normalize_pair(mcp_seq, step_seq, "삭제 대상")
    upeh = prepared["RQ_UPEH"]
    reqb = prepared["RQ_REQB"]
    source_upeh_mask = _route_pair_mask(upeh, normalized_route, pair)
    source_reqb_mask = _route_pair_mask(reqb, normalized_route, pair)
    source_upeh = upeh.loc[source_upeh_mask].copy()
    source_reqb = reqb.loc[source_reqb_mask].copy()
    if source_upeh.empty or source_reqb.empty:
        raise ValueError("삭제 대상 STEP의 네 테이블 연결 경로가 완전하지 않습니다.")

    affected_months = tuple(sorted(int(month) for month in source_reqb["생산계획년월"].unique()))
    _assert_not_last_step(reqb, normalized_route, affected_months)
    source_upeh_mask &= upeh["생산계획년월"].isin(affected_months)
    remaining_upeh = upeh.loc[~source_upeh_mask].copy()
    replacements = dict(prepared)
    replacements["RQ_UPEH"] = remaining_upeh.reset_index(drop=True)
    replacements["RQ_REQB"] = reqb.loc[~source_reqb_mask].reset_index(drop=True)

    removed_performance_keys = source_upeh.loc[
        source_upeh["생산계획년월"].isin(affected_months),
        PERFORMANCE_ROUTE_COLUMNS,
    ].drop_duplicates()
    remaining_key_set = _row_key_set(remaining_upeh, PERFORMANCE_ROUTE_COLUMNS)
    orphaned_keys = {
        key
        for key in _row_key_set(removed_performance_keys, PERFORMANCE_ROUTE_COLUMNS)
        if key not in remaining_key_set
    }
    for table_name in ("RQ_LOT_RATIO", "RQ_WF_RATIO"):
        ratio = prepared[table_name]
        remove_mask = _key_membership_mask(ratio, PERFORMANCE_ROUTE_COLUMNS, orphaned_keys)
        replacements[table_name] = ratio.loc[~remove_mask].reset_index(drop=True)

    return StepChangeResult(
        replacements=replacements,
        affected_months=affected_months,
        affected_reqb_rows=len(source_reqb),
        affected_variants=_variant_count(source_reqb),
    )


def _prepare_route_tables(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    missing = [name for name in ROUTE_TABLES if name not in tables]
    if missing:
        raise KeyError(f"STEP 편집 기준정보가 없습니다: {', '.join(missing)}")
    return {
        "RQ_REQB": _prepare(tables["RQ_REQB"], _REQB_COLUMNS, "RQ_REQB"),
        "RQ_UPEH": _prepare(tables["RQ_UPEH"], _UPEH_COLUMNS, "RQ_UPEH"),
        "RQ_LOT_RATIO": _prepare(tables["RQ_LOT_RATIO"], _RATIO_COLUMNS, "RQ_LOT_RATIO"),
        "RQ_WF_RATIO": _prepare(tables["RQ_WF_RATIO"], _RATIO_COLUMNS, "RQ_WF_RATIO"),
    }


def _prepare(data: pd.DataFrame, required: tuple[str, ...], table_name: str) -> pd.DataFrame:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{table_name} STEP 편집 필수 컬럼이 없습니다: {', '.join(missing)}")
    result = data.copy(deep=True)
    numeric_months = pd.to_numeric(result["생산계획년월"], errors="coerce")
    valid_months = numeric_months.notna() & numeric_months.mod(1).eq(0)
    months = numeric_months.fillna(0).astype("int64")
    valid_months &= months.mod(100).between(1, 12)
    if not valid_months.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    result["생산계획년월"] = months
    text_columns = [column for column in required if column != "생산계획년월"]
    for column in text_columns:
        result[column] = result[column].astype("string").str.strip()
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"{table_name}의 {column}에 누락값이 있습니다.")
    if "소요기준" in result.columns:
        result["소요기준"] = normalize_demand_basis(result["소요기준"])
    return result


def _normalize_route(route: Mapping[str, object]) -> dict[str, str]:
    missing = [column for column in ROUTE_GROUP_COLUMNS if column not in route]
    if missing:
        raise ValueError(f"STEP 편집 경로 값이 없습니다: {', '.join(missing)}")
    result: dict[str, str] = {}
    for column in ROUTE_GROUP_COLUMNS:
        value = str(route[column]).strip()
        if not value:
            raise ValueError(f"STEP 편집 경로의 {column} 값이 비어 있습니다.")
        result[column] = normalize_demand_basis_value(value) if column == "소요기준" else value
    return result


def _normalize_pair(mcp_seq: str, step_seq: str, label: str) -> tuple[str, str]:
    pair = (str(mcp_seq).strip(), str(step_seq).strip())
    if not all(pair):
        raise ValueError(f"{label} MCP_SEQ와 STEP_SEQ를 모두 입력하세요.")
    return pair


def _route_pair_mask(
    data: pd.DataFrame,
    route: Mapping[str, str],
    pair: tuple[str, str],
) -> pd.Series:
    mask = pd.Series(True, index=data.index)
    for column, value in route.items():
        if column in data.columns:
            mask &= data[column].eq(value)
    mask &= data["MCP_SEQ"].eq(pair[0]) & data["STEP_SEQ"].eq(pair[1])
    return mask


def _assert_one_upeh_per_month(data: pd.DataFrame, months: tuple[int, ...]) -> None:
    counts = data.groupby("생산계획년월", dropna=False).size()
    missing = [month for month in months if int(counts.get(month, 0)) == 0]
    duplicates = [int(str(month)) for month, count in counts.items() if int(count) > 1]
    if missing:
        raise ValueError(f"복제 원본 RQ_UPEH가 없는 적용월이 있습니다: {missing[:5]}")
    if duplicates:
        raise ValueError(f"복제 원본 RQ_UPEH 경로가 중복된 적용월이 있습니다: {duplicates[:5]}")


def _assert_unique_reqb(data: pd.DataFrame) -> None:
    keys = ["생산계획년월", *ROUTE_GROUP_COLUMNS, *REQB_VARIANT_COLUMNS, *STEP_PAIR_COLUMNS]
    if data.duplicated(keys, keep=False).any():
        raise ValueError("복제 원본 RQ_REQB에 동일 수요 변형·STEP 경로가 중복되어 있습니다.")


def _clone_ratio_rows(
    ratio: pd.DataFrame,
    source_upeh: pd.DataFrame,
    target_pair: tuple[str, str],
    table_name: str,
) -> pd.DataFrame:
    source_keys = source_upeh[list(PERFORMANCE_ROUTE_COLUMNS)].drop_duplicates()
    source_key_set = _row_key_set(source_keys, PERFORMANCE_ROUTE_COLUMNS)
    source_mask = _key_membership_mask(ratio, PERFORMANCE_ROUTE_COLUMNS, source_key_set)
    source_ratio = ratio.loc[source_mask].copy()
    found_keys = _row_key_set(source_ratio, PERFORMANCE_ROUTE_COLUMNS)
    missing_keys = source_key_set - found_keys
    if missing_keys:
        raise ValueError(f"복제 원본 STEP에 연결된 {table_name} 행이 없습니다.")
    if source_ratio.duplicated(list(PERFORMANCE_ROUTE_COLUMNS), keep=False).any():
        raise ValueError(f"복제 원본 STEP의 {table_name} 경로가 중복되어 있습니다.")

    cloned = source_ratio.copy()
    cloned["MCP_SEQ"], cloned["STEP_SEQ"] = target_pair
    existing_target_keys = _row_key_set(ratio, PERFORMANCE_ROUTE_COLUMNS)
    target_is_new = ~_key_membership_mask(
        cloned,
        PERFORMANCE_ROUTE_COLUMNS,
        existing_target_keys,
    )
    return _append_like(ratio, cloned.loc[target_is_new])


def _assert_not_last_step(
    reqb: pd.DataFrame,
    route: Mapping[str, str],
    affected_months: tuple[int, ...],
) -> None:
    route_mask = pd.Series(True, index=reqb.index)
    for column, value in route.items():
        route_mask &= reqb[column].eq(value)
    selected = reqb.loc[
        route_mask & reqb["생산계획년월"].isin(affected_months),
        ["생산계획년월", *STEP_PAIR_COLUMNS],
    ].drop_duplicates()
    counts = selected.groupby("생산계획년월", dropna=False).size()
    last_step_months = [int(str(month)) for month, count in counts.items() if int(count) <= 1]
    if last_step_months:
        raise ValueError(
            f"공정·제품 경로의 마지막 STEP은 삭제할 수 없습니다. 대상월: {last_step_months[:5]}"
        )


def _append_like(base: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return base.reset_index(drop=True)
    result = pd.concat(
        [base, rows.reindex(columns=base.columns)],
        ignore_index=True,
    ).reindex(columns=base.columns)
    sort_columns = [
        column
        for column in (
            "생산계획년월",
            *ROUTE_GROUP_COLUMNS,
            *STEP_PAIR_COLUMNS,
            *REQB_VARIANT_COLUMNS,
        )
        if column in result.columns
    ]
    return result.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def _row_key_set(data: pd.DataFrame, columns: tuple[str, ...]) -> set[tuple[object, ...]]:
    return set(data.loc[:, list(columns)].itertuples(index=False, name=None))


def _key_membership_mask(
    data: pd.DataFrame,
    columns: tuple[str, ...],
    keys: set[tuple[object, ...]],
) -> pd.Series:
    if not keys:
        return pd.Series(False, index=data.index)
    row_keys = data.loc[:, list(columns)].itertuples(index=False, name=None)
    return pd.Series((key in keys for key in row_keys), index=data.index)


def _variant_count(reqb: pd.DataFrame) -> int:
    return len(reqb.loc[:, list(REQB_VARIANT_COLUMNS)].drop_duplicates())
