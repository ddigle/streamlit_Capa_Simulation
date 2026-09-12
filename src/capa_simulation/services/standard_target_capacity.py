# Purpose: Weekly standard target Capa from effective daily Capa and manual availability.

"""Weekly standard target Capa from effective daily Capa and manual availability."""

from __future__ import annotations

from datetime import date

import pandas as pd

from capa_simulation.services.frame_contracts import (
    assert_complete,
    normalize_demand_basis,
    normalize_month_column,
    to_numeric_strict,
)
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.weekly_availability_input import prepare_weekly_availability
from capa_simulation.services.weighted_unit_capacity import (
    DEMAND_ID_COLUMNS,
    WEIGHTED_CAPACITY_HIERARCHY,
    effective_process_capacity_long,
)

STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES = ("Pre B/D",)
PKG_EQUIVALENT_COLUMN = "PKG 환산 일 표준 가능량"
# 소요대수 상세와 계획을 잇는 키. `Pack Code` 는 **넣지 않는다** — 연결 상대인
# `DEMAND_ID_COLUMNS` 에 그 컬럼이 없어 `KeyError` 가 난다. Pack Code 별 계획 줄은
# `_prepare_pkg_plan_for_equivalent` 가 이 7키 합계로 접어서 넘긴다.
PKG_PLAN_KEYS = [
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
]


def build_weekly_standard_target_capacity(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
) -> pd.DataFrame:
    """Calculate weekly standard daily input for each process/product classification."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    production_required_equipment = prepare_standard_target_required_equipment(required_equipment)
    monthly_capacity = effective_process_capacity_long(
        production_required_equipment,
        detail_level,
    )
    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    result_columns = [
        "Weeknum",
        "주차시작일",
        "주차종료일",
        "생산계획년월",
        *display_dimensions,
        "원수요_부하량",
        "STEP_소요대수",
        "공정 유효 Capa",
        "RUN_DAY",
        "대당 일 Capa",
        "가용대수",
        "일 표준 가능량",
    ]
    if monthly_capacity.empty:
        return pd.DataFrame(columns=result_columns)

    prepared_run_day = _prepare_run_day(run_day)
    monthly_capacity = monthly_capacity.merge(
        prepared_run_day,
        on=["생산계획년월", "공정"],
        how="left",
        validate="many_to_one",
    )
    missing_run_day = monthly_capacity["RUN_DAY"].isna()
    if missing_run_day.any():
        examples = (
            monthly_capacity.loc[missing_run_day, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_RUN_DAY 연결값이 없는 표준 목표 Capa 기준이 있습니다: {examples}")
    monthly_capacity["대당 일 Capa"] = monthly_capacity["공정 유효 Capa"].div(
        monthly_capacity["RUN_DAY"]
    )

    calendar = build_iso_week_calendar(start_date, end_date)
    # This is an intentional month-to-week expansion, not an accidental many-to-many join.
    weekly = monthly_capacity.merge(calendar, on="생산계획년월", validate="many_to_many")
    prepared_availability = prepare_weekly_availability(weekly_availability)
    weekly = weekly.merge(
        prepared_availability,
        on=["공정", "Weeknum"],
        how="left",
        validate="many_to_one",
    )
    weekly["일 표준 가능량"] = weekly["대당 일 Capa"] * weekly["가용대수"]
    return weekly[result_columns].sort_values(
        ["주차시작일", *display_dimensions],
        ignore_index=True,
    )


def add_pkg_equivalent_standard_target(
    weekly_target: pd.DataFrame,
    required_equipment: pd.DataFrame,
    plan: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """Add daily PKG Kea equivalent while preserving the calculated demand mix."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    group_keys = ["생산계획년월", *display_dimensions]
    target_required = [*group_keys, "원수요_부하량", "일 표준 가능량"]
    missing_target = [column for column in target_required if column not in weekly_target.columns]
    if missing_target:
        raise ValueError(f"표준 목표 Capa 필수 컬럼이 없습니다: {', '.join(missing_target)}")

    result = weekly_target.copy()
    if result.empty:
        result[PKG_EQUIVALENT_COLUMN] = pd.Series(dtype="float64")
        return result

    source = prepare_standard_target_required_equipment(required_equipment)
    source_required = [*DEMAND_ID_COLUMNS, "부하량"]
    missing_source = [column for column in source_required if column not in source.columns]
    if missing_source:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing_source)}")
    source = source[source_required].copy()
    normalize_month_column(source, "소요대수 상세")
    source_text_columns = [
        column for column in DEMAND_ID_COLUMNS if column not in {"생산계획년월", "소요기준"}
    ]
    _normalize_text_values(source, source_text_columns, "소요대수 상세")
    source["소요기준"] = normalize_demand_basis(source["소요기준"])
    assert_complete(source, DEMAND_ID_COLUMNS, "소요대수 상세")
    source["부하량"] = to_numeric_strict(source["부하량"], "소요대수 상세.부하량")
    source = source.loc[source["부하량"].gt(0)].drop_duplicates(DEMAND_ID_COLUMNS)

    prepared_plan = _prepare_pkg_plan_for_equivalent(plan)
    link_columns = list(dict.fromkeys([*group_keys, *PKG_PLAN_KEYS]))
    demand_links = source[link_columns].drop_duplicates()
    demand_links = demand_links.merge(
        prepared_plan,
        on=PKG_PLAN_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_pkg_plan_merge",
    )
    missing_plan = demand_links["_pkg_plan_merge"].ne("both")
    if missing_plan.any():
        examples = demand_links.loc[missing_plan, PKG_PLAN_KEYS].head(5).to_dict("records")
        raise ValueError(f"PKG 환산에 필요한 RQ_PKG_PLAN 연결값이 없습니다: {examples}")
    demand_links = demand_links.drop(columns="_pkg_plan_merge")

    pkg_plan_by_group = demand_links.groupby(group_keys, as_index=False, dropna=False).agg(
        PKG_계획=("생산수량", "sum")
    )
    result = result.merge(
        pkg_plan_by_group,
        on=group_keys,
        how="left",
        validate="many_to_one",
    )
    original_load = pd.to_numeric(result["원수요_부하량"], errors="coerce")
    daily_target = pd.to_numeric(result["일 표준 가능량"], errors="coerce")
    conversion_ratio = result["PKG_계획"].div(original_load.where(original_load.gt(0)))
    result[PKG_EQUIVALENT_COLUMN] = daily_target * conversion_ratio
    return result.drop(columns="PKG_계획")


def weekly_standard_target_to_wide(
    data: pd.DataFrame,
    classification_columns: list[str],
    value_column: str = "일 표준 가능량",
) -> pd.DataFrame:
    """Pivot one weekly metric into Weeknum columns for Plotly display."""
    required = ["Weeknum", "주차시작일", *classification_columns, value_column]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"표준 목표 Capa 필수 컬럼이 없습니다: {', '.join(missing)}")
    if data.empty:
        return pd.DataFrame(columns=classification_columns)

    week_order = (
        data[["Weeknum", "주차시작일"]]
        .drop_duplicates()
        .sort_values("주차시작일")["Weeknum"]
        .tolist()
    )
    duplicated = data.duplicated([*classification_columns, "Weeknum"], keep=False)
    if duplicated.any():
        examples = (
            data.loc[duplicated, [*classification_columns, "Weeknum"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"표준 목표 Capa의 분류·Weeknum이 중복되었습니다: {examples}")
    wide = data.pivot(
        index=classification_columns,
        columns="Weeknum",
        values=value_column,
    ).reset_index()
    wide.columns.name = None
    return wide.reindex(columns=[*classification_columns, *week_order])


def exclude_er_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Exclude engineering-run demand before standard Capa aggregation."""
    if "양산구분" not in data.columns:
        raise ValueError("소요대수 상세 필수 컬럼이 없습니다: 양산구분")
    production_mask = ~data["양산구분"].astype("string").str.strip().str.upper().eq("ER")
    return data.loc[production_mask].reset_index(drop=True)


def prepare_standard_target_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Apply every demand exclusion used only by standard target Capa."""
    production = exclude_er_required_equipment(data)
    exception_mask = _standard_target_exception_mask(production)
    return production.loc[~exception_mask].reset_index(drop=True)


def standard_target_exception_row_count(data: pd.DataFrame) -> int:
    """Count detailed rows omitted by process-specific standard target rules."""
    production = exclude_er_required_equipment(data)
    return int(_standard_target_exception_mask(production).sum())


def _standard_target_exception_mask(data: pd.DataFrame) -> pd.Series:
    required = ["공정", "WF 구분"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing)}")
    process = data["공정"].astype("string").str.strip().str.upper()
    wf_type = data["WF 구분"].astype("string").str.strip().str.upper()
    excluded_processes = {
        value.strip().upper() for value in STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES
    }
    return process.isin(excluded_processes) & wf_type.eq("DUMMY")


def _prepare_run_day(data: pd.DataFrame) -> pd.DataFrame:
    required = ["생산계획년월", "공정", "RUN_DAY"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"RQ_RUN_DAY 필수 컬럼이 없습니다: {', '.join(missing)}")
    result = data[required].copy()
    normalize_month_column(result, "RQ_RUN_DAY")
    result["공정"] = result["공정"].astype("string").str.strip()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError("RQ_RUN_DAY의 공정에는 누락값이 없어야 합니다.")
    run_day = pd.to_numeric(result["RUN_DAY"], errors="coerce")
    if run_day.isna().any() or run_day.le(0).any():
        raise ValueError("RQ_RUN_DAY의 RUN_DAY는 0보다 큰 숫자여야 합니다.")
    result["RUN_DAY"] = run_day.astype("float64")
    duplicated = result.duplicated(["생산계획년월", "공정"], keep=False)
    if duplicated.any():
        examples = (
            result.loc[duplicated, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_RUN_DAY의 생산계획년월·공정이 중복되었습니다: {examples}")
    return result


def _prepare_pkg_plan_for_equivalent(data: pd.DataFrame) -> pd.DataFrame:
    required = [*PKG_PLAN_KEYS, "생산수량"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"RQ_PKG_PLAN 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = data[required].copy()
    normalize_month_column(result, "RQ_PKG_PLAN")
    text_columns = [column for column in PKG_PLAN_KEYS if column != "생산계획년월"]
    _normalize_text_values(result, text_columns, "RQ_PKG_PLAN")
    assert_complete(result, PKG_PLAN_KEYS, "RQ_PKG_PLAN")
    result["생산수량"] = to_numeric_strict(result["생산수량"], "RQ_PKG_PLAN.생산수량")
    if result["생산수량"].lt(0).any():
        raise ValueError("RQ_PKG_PLAN의 생산수량은 0 이상이어야 합니다.")
    # `Pack Code` 가 업무 키로 올라가 같은 7키에 계획 줄이 여럿 있을 수 있다. 연결 상대인
    # 소요대수 상세(`DEMAND_ID_COLUMNS`)에는 Pack Code 가 없으므로 여기서 7키 합계로 접는다.
    # 중복을 예외로 막으면 Pack Code 가 갈린 리비전에서 PKG 환산이 통째로 실패한다.
    return result.groupby(PKG_PLAN_KEYS, as_index=False).agg(생산수량=("생산수량", "sum"))


def _normalize_text_values(data: pd.DataFrame, columns: list[str], table_name: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
    assert_complete(data, columns, table_name)
