# Purpose: RQ_REQB 경로와 소요기준 부하량·대당 Capa를 연결해 STEP별 소요대수를 계산한다.

import pandas as pd

from capa_simulation.services.frame_contracts import (
    assert_complete,
    normalize_area_name,
    normalize_month_column,
    require_columns,
    to_numeric_strict,
    validate_demand_basis,
)
from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    calculate_chip_load,
    calculate_wafer_load,
    drop_unplanned_rows,
)

REQB_COLUMNS = [
    "생산계획년월",
    "Area_Name",
    "공정",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
    "소요기준",
]
LOAD_KEYS = [
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "WF 구분",
    "소요기준",
]
CAPACITY_KEYS = [
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "소요기준",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
]
RESULT_DIMENSIONS = [
    "공정",
    "Area_Name",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "소요기준",
    "STEP_SEQ",
    "MCP_SEQ",
]
REQB_TEXT_COLUMNS = [column for column in REQB_COLUMNS if column != "생산계획년월"]
REQB_REQUIRED_KEYS = list(dict.fromkeys([*LOAD_KEYS, *CAPACITY_KEYS]))
UNIMPLEMENTED_BASES = {"BOX", "PCB"}
REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR = "excluded_required_equipment_rows"


def calculate_required_equipment(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate required equipment for every RQ_REQB row."""
    prepared_reqb = _prepare_reqb(reqb)
    if prepared_reqb.empty:
        return _empty_required_equipment_result()

    loads = _build_loads(
        plan,
        yield_data,
        chip_qty,
        set(prepared_reqb["소요기준"].unique()),
    )
    return _calculate_required_equipment_from_prepared(
        prepared_reqb,
        loads,
        unit_capacity,
    )


def _prepare_reqb(reqb: pd.DataFrame) -> pd.DataFrame:
    require_columns(reqb, REQB_COLUMNS, "RQ_REQB")
    prepared_reqb = reqb[REQB_COLUMNS].copy()
    normalize_month_column(prepared_reqb, "RQ_REQB")
    _normalize_text(prepared_reqb, REQB_TEXT_COLUMNS)
    prepared_reqb["소요기준"] = prepared_reqb["소요기준"].str.upper()
    prepared_reqb = prepared_reqb.loc[~prepared_reqb["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if prepared_reqb.empty:
        return prepared_reqb
    prepared_reqb["소요기준"] = validate_demand_basis(prepared_reqb["소요기준"], "RQ_REQB")
    assert_complete(prepared_reqb, REQB_REQUIRED_KEYS, "RQ_REQB")
    prepared_reqb["Area_Name"] = normalize_area_name(prepared_reqb["Area_Name"], "RQ_REQB")
    return prepared_reqb


def _empty_required_equipment_result() -> pd.DataFrame:
    empty_result = pd.DataFrame(columns=[*REQB_COLUMNS, "부하량", "대당 Capa", "소요대수"])
    empty_result.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR] = pd.DataFrame()
    return empty_result


def _calculate_required_equipment_from_prepared(
    prepared_reqb: pd.DataFrame,
    loads: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> pd.DataFrame:
    capacities = _prepare_capacities(unit_capacity)

    result = prepared_reqb.merge(loads, on=LOAD_KEYS, how="left", validate="many_to_one")
    result["부하량"] = result["부하량"].fillna(0.0)
    result = result.merge(
        capacities,
        on=CAPACITY_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_capacity_merge",
    )
    missing_capacity = result["_capacity_merge"].ne("both")
    result = result.drop(columns="_capacity_merge")
    nonpositive_capacity = result["대당 Capa"].le(0).fillna(False)
    excluded_capacity = missing_capacity | nonpositive_capacity
    excluded_rows = result.loc[excluded_capacity, [*REQB_COLUMNS, "부하량", "대당 Capa"]].copy()
    excluded_rows["제외사유"] = "대당 Capa 없음"
    excluded_rows.loc[nonpositive_capacity.loc[excluded_capacity], "제외사유"] = "대당 Capa 0 이하"
    result = result.loc[~excluded_capacity].copy()
    result["소요대수"] = result["부하량"] / result["대당 Capa"]
    output = result[[*REQB_COLUMNS, "부하량", "대당 Capa", "소요대수"]]
    output.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR] = excluded_rows.reset_index(drop=True)
    return output


def required_equipment_to_month_table(data: pd.DataFrame) -> pd.DataFrame:
    """Aggregate RQ_REQB results by output dimensions and pivot month columns."""
    required = [*REQB_COLUMNS, "소요대수"]
    require_columns(data, required, "소요대수")
    if data.empty:
        return pd.DataFrame(columns=RESULT_DIMENSIONS)
    pivot_input = data.groupby(
        ["생산계획년월", *RESULT_DIMENSIONS],
        as_index=False,
        dropna=False,
    )["소요대수"].sum()
    pivot_input[RESULT_DIMENSIONS] = pivot_input[RESULT_DIMENSIONS].fillna("")
    result: pd.DataFrame = pivot_input.pivot(
        index=RESULT_DIMENSIONS,
        columns="생산계획년월",
        values="소요대수",
    ).reset_index()
    result.columns.name = None
    month_columns = sorted(column for column in result.columns if column not in RESULT_DIMENSIONS)
    result = result.rename(columns={month: str(int(month)) for month in month_columns})
    ordered_columns = [*RESULT_DIMENSIONS, *[str(int(month)) for month in month_columns]]
    return result.reindex(columns=ordered_columns)


def _build_loads(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    required_bases: set[str],
) -> pd.DataFrame:
    plan_columns = [
        "생산계획년월",
        "양산구분",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "CS",
        "생산수량",
    ]
    require_columns(plan, plan_columns, "RQ_PKG_PLAN")
    prepared_plan = plan.copy()
    normalize_month_column(prepared_plan, "RQ_PKG_PLAN")
    _normalize_text(
        prepared_plan,
        ["양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS"],
    )
    prepared_plan["생산수량"] = to_numeric_strict(prepared_plan["생산수량"], "RQ_PKG_PLAN.생산수량")
    # 이 경로는 load_calculator._prepare_plan 을 거치지 않으므로 여기서도 제외한다.
    prepared_plan = drop_unplanned_rows(prepared_plan)

    load_frames: list[pd.DataFrame] = []
    if "PKG" in required_bases:
        pkg = prepared_plan[plan_columns].rename(columns={"생산수량": "부하량"})
        pkg["WF 구분"] = "PKG"
        pkg["소요기준"] = "PKG"
        load_frames.append(pkg)
    needs_chip = "CHIP" in required_bases
    needs_wafer = "WF" in required_bases
    chip_load: pd.DataFrame | None = None
    wafer_load: pd.DataFrame | None = None
    # 둘 다 필요하면 한 번에 만든다. 따로 부르면 같은 계획을 두 번 훑는다.
    if needs_chip and needs_wafer:
        chip_load, wafer_load = calculate_chip_and_wafer_loads(
            prepared_plan,
            yield_data,
            chip_qty,
        )
    elif needs_chip:
        chip_load = calculate_chip_load(prepared_plan, yield_data, chip_qty)
    elif needs_wafer:
        wafer_load = calculate_wafer_load(prepared_plan, yield_data, chip_qty)
    if chip_load is not None:
        chip = chip_load.rename(columns={"물량": "부하량"})
        chip["소요기준"] = "CHIP"
        load_frames.append(chip)
    if wafer_load is not None:
        wafer = wafer_load.rename(columns={"물량": "부하량"})
        wafer["소요기준"] = "WF"
        load_frames.append(wafer)

    loads = pd.concat(load_frames, ignore_index=True)[[*LOAD_KEYS, "부하량"]]
    _normalize_text(loads, [key for key in LOAD_KEYS if key not in {"생산계획년월", "소요기준"}])
    loads["소요기준"] = validate_demand_basis(loads["소요기준"], "부하량")
    return loads.groupby(LOAD_KEYS, as_index=False, dropna=False)[["부하량"]].sum()


def _prepare_capacities(data: pd.DataFrame) -> pd.DataFrame:
    require_columns(data, [*CAPACITY_KEYS, "대당 Capa"], "대당 Capa")
    result = data[[*CAPACITY_KEYS, "대당 Capa"]].copy()
    normalize_month_column(result, "대당 Capa")
    _normalize_text(
        result,
        [key for key in CAPACITY_KEYS if key not in {"생산계획년월", "소요기준"}],
    )
    result["Area_Name"] = normalize_area_name(result["Area_Name"], "대당 Capa")
    result["소요기준"] = validate_demand_basis(result["소요기준"], "대당 Capa")
    result["대당 Capa"] = to_numeric_strict(result["대당 Capa"], "대당 Capa")
    duplicated = result.duplicated(CAPACITY_KEYS, keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, CAPACITY_KEYS].drop_duplicates().head(5)
        raise ValueError(f"대당 Capa 연결 키가 중복되었습니다: {examples.to_dict('records')}")
    return result


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
