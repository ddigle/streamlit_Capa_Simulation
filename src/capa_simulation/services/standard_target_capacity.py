# Purpose: Weekly standard target Capa from effective daily Capa and manual availability.

"""Weekly standard target Capa from effective daily Capa and manual availability."""

from __future__ import annotations

from datetime import date

import pandas as pd

from capa_simulation.services.frame_checks import assert_unique_keys
from capa_simulation.services.frame_contracts import (
    assert_complete,
    normalize_demand_basis,
    normalize_month_column,
    require_columns,
    to_numeric_strict,
)
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.load_calculator import plan_quantities
from capa_simulation.services.weekly_availability_input import prepare_weekly_availability
from capa_simulation.services.weighted_unit_capacity import (
    DEMAND_ID_COLUMNS,
    WEIGHTED_CAPACITY_HIERARCHY,
    effective_process_capacity_long,
)

STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES = ("Pre B/D",)
PKG_EQUIVALENT_COLUMN = "PKG 환산 일 표준 가능량"
# `RQ_RUN_DAY` 를 붙이는 동안만 들고 가는 칸. 빈 칸 여부·원래 적힌 값·붙었는지.
_RUN_DAY_BLANK = "_RUN_DAY_빈값"
_RUN_DAY_RAW = "_RUN_DAY_원래값"
_RUN_DAY_JOINED = "_RUN_DAY_연결"
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
    *,
    already_split: bool = False,
) -> pd.DataFrame:
    """Calculate weekly standard daily input for each process/product classification.

    `already_split` 은 `required_equipment` 가 이미 `split_standard_target_required_equipment`
    를 거친 프레임(또는 그 행을 거른 것)일 때만 켠다 — 표준 목표 캐시 래퍼가 분리 결과 캐시에서
    받은 프레임을 넘길 때다. 분리는 멱등이라 결과는 같고, 소요대수 전체에 ER·예외 마스크를 한 번
    더 거는 비용만 빠진다. 분리하지 않은 프레임에 켜면 ER·`Pre B/D` DUMMY 가 계산에 섞인다.
    """
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    production_required_equipment = _standard_target_rows(
        required_equipment, already_split=already_split
    )
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

    monthly_capacity = _attach_run_day(monthly_capacity, _prepare_run_day(run_day))
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
    *,
    already_split: bool = False,
) -> pd.DataFrame:
    """Add daily PKG Kea equivalent while preserving the calculated demand mix.

    `already_split` 의 뜻과 계약은 `build_weekly_standard_target_capacity` 와 같다.
    """
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    group_keys = ["생산계획년월", *display_dimensions]
    target_required = [*group_keys, "원수요_부하량", "일 표준 가능량"]
    require_columns(weekly_target, target_required, "표준 목표 Capa")

    result = weekly_target.copy()
    if result.empty:
        result[PKG_EQUIVALENT_COLUMN] = pd.Series(dtype="float64")
        return result

    source = _standard_target_rows(required_equipment, already_split=already_split)
    source_required = [*DEMAND_ID_COLUMNS, "부하량"]
    require_columns(source, source_required, "소요대수 상세")
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
    require_columns(data, required, "표준 목표 Capa")
    if data.empty:
        return pd.DataFrame(columns=classification_columns)

    week_order = (
        data[["Weeknum", "주차시작일"]]
        .drop_duplicates()
        .sort_values("주차시작일")["Weeknum"]
        .tolist()
    )
    assert_unique_keys(
        data,
        [*classification_columns, "Weeknum"],
        "표준 목표 Capa의 분류·Weeknum이",
    )
    wide = data.pivot(
        index=classification_columns,
        columns="Weeknum",
        values=value_column,
    ).reset_index()
    wide.columns.name = None
    return wide.reindex(columns=[*classification_columns, *week_order])


def exclude_er_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Exclude engineering-run demand before standard Capa aggregation."""
    require_columns(data, ["양산구분"], "소요대수 상세")
    production_mask = ~data["양산구분"].astype("string").str.strip().str.upper().eq("ER")
    return data.loc[production_mask].reset_index(drop=True)


def split_standard_target_required_equipment(data: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """표준 목표 전용 제외를 적용한 소요대수 상세와 공정 예외로 뺀 행 수를 함께 돌려준다.

    ER 제외와 예외 마스크는 소요대수 상세 전체를 훑는다. 화면이 남는 표와 제외 건수를 둘 다
    쓰므로 한 번 만든 마스크로 둘을 낸다. 아래 두 함수는 한쪽만 필요한 호출부용 래퍼다.
    """
    production = exclude_er_required_equipment(data)
    exception_mask = _standard_target_exception_mask(production)
    prepared = production.loc[~exception_mask].reset_index(drop=True)
    return prepared, int(exception_mask.sum())


def prepare_standard_target_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Apply every demand exclusion used only by standard target Capa."""
    return split_standard_target_required_equipment(data)[0]


def standard_target_exception_row_count(data: pd.DataFrame) -> int:
    """Count detailed rows omitted by process-specific standard target rules."""
    return split_standard_target_required_equipment(data)[1]


def _standard_target_rows(data: pd.DataFrame, *, already_split: bool) -> pd.DataFrame:
    """표준 목표 제외를 거친 소요대수. 이미 거친 프레임이면 그대로 쓴다(다시 훑지 않는다)."""
    if already_split:
        return data
    return prepare_standard_target_required_equipment(data)


def _standard_target_exception_mask(data: pd.DataFrame) -> pd.Series:
    require_columns(data, ["공정", "WF 구분"], "소요대수 상세")
    process = data["공정"].astype("string").str.strip().str.upper()
    wf_type = data["WF 구분"].astype("string").str.strip().str.upper()
    excluded_processes = {
        value.strip().upper() for value in STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES
    }
    return process.isin(excluded_processes) & wf_type.eq("DUMMY")


def _prepare_run_day(data: pd.DataFrame) -> pd.DataFrame:
    """키를 맞추고 값을 숫자로 읽는다. **값 검사는 붙인 뒤에 한다**(`_attach_run_day`).

    표 전체를 여기서 검사하면 소요대수가 없는 (월, 공정)의 0 하나가 표준 목표와 재공 현황을
    멈춘다. 기준 정보 적용 검사는 UPEH 경로가 쓰지 않는 칸의 0 을 허락하므로(대당 Capa 가 멈추지
    않는다, `reference_consistency.nonpositive_keys_in_use`) 그 0 은 정상 상태다.
    """
    required = ["생산계획년월", "공정", "RUN_DAY"]
    require_columns(data, required, "RQ_RUN_DAY")
    result = data[required].copy()
    normalize_month_column(result, "RQ_RUN_DAY")
    result["공정"] = result["공정"].astype("string").str.strip()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError("RQ_RUN_DAY의 공정에는 누락값이 없어야 합니다.")
    raw = result["RUN_DAY"]
    result[_RUN_DAY_BLANK] = raw.isna() | raw.astype("string").str.strip().eq("").fillna(False)
    result[_RUN_DAY_RAW] = raw
    result["RUN_DAY"] = pd.to_numeric(raw, errors="coerce").astype("float64")
    assert_unique_keys(result, ["생산계획년월", "공정"], "RQ_RUN_DAY의 생산계획년월·공정이")
    return result


def _attach_run_day(monthly_capacity: pd.DataFrame, run_day: pd.DataFrame) -> pd.DataFrame:
    """(월, 공정)마다 RUN_DAY 를 붙이고 **붙은 칸만** 검사한다. 걸리면 그 (월, 공정)을 적는다.

    대당 일 Capa 는 RUN_DAY 로 나누므로 붙은 칸은 0보다 큰 숫자여야 한다. 행이 없는 것·빈 값·숫자가
    아닌 값·0 이하를 각각 다른 문장으로 알린다.
    """
    keys = ["생산계획년월", "공정"]
    joined = monthly_capacity.merge(
        run_day,
        on=keys,
        how="left",
        validate="many_to_one",
        indicator=_RUN_DAY_JOINED,
    )
    attached = joined[_RUN_DAY_JOINED].eq("both")
    blank = attached & joined[_RUN_DAY_BLANK].eq(True)
    checks = (
        (
            ~attached,
            "RQ_RUN_DAY 연결값이 없는 표준 목표 Capa 기준이 있습니다: ",
            keys,
        ),
        (
            blank,
            "RQ_RUN_DAY의 RUN_DAY 값이 빈 표준 목표 Capa 기준이 있습니다: ",
            keys,
        ),
        (
            attached & ~blank & joined["RUN_DAY"].isna(),
            "RQ_RUN_DAY의 RUN_DAY에 숫자가 아닌 값이 있습니다: ",
            [*keys, _RUN_DAY_RAW],
        ),
        (
            attached & joined["RUN_DAY"].le(0),
            "RQ_RUN_DAY의 RUN_DAY는 0보다 커야 합니다: ",
            [*keys, "RUN_DAY"],
        ),
    )
    for mask, message, columns in checks:
        if not bool(mask.any()):
            continue
        found = joined.loc[mask, columns].drop_duplicates(subset=keys)
        examples = found.rename(columns={_RUN_DAY_RAW: "RUN_DAY"}).head(5).to_dict("records")
        raise ValueError(f"{message}{len(found):,}건, 예시 {examples}")
    return joined.drop(columns=[_RUN_DAY_JOINED, _RUN_DAY_BLANK, _RUN_DAY_RAW])


def _prepare_pkg_plan_for_equivalent(data: pd.DataFrame) -> pd.DataFrame:
    required = [*PKG_PLAN_KEYS, "생산수량"]
    require_columns(data, required, "RQ_PKG_PLAN")

    result = data[required].copy()
    normalize_month_column(result, "RQ_PKG_PLAN")
    text_columns = [column for column in PKG_PLAN_KEYS if column != "생산계획년월"]
    _normalize_text_values(result, text_columns, "RQ_PKG_PLAN")
    assert_complete(result, PKG_PLAN_KEYS, "RQ_PKG_PLAN")
    # 빈 생산수량은 「계획 없음(0)」이다 — 환산·소요대수와 한 규칙(소요대수 결과가 그 행을 목록으로
    # 알린다). 숫자가 아닌 글자만 같은 함수·같은 문구(키 예시)로 막는다.
    result["생산수량"] = plan_quantities(result).fillna(0.0).astype("float64")
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
