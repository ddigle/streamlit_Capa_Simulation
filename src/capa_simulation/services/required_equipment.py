# Purpose: RQ_REQB 경로와 소요기준 부하량·대당 Capa를 연결해 STEP별 소요대수를 계산한다.

import pandas as pd

from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    calculate_chip_load,
    calculate_wafer_load,
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


def calculate_required_equipment_from_loads(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    unit_capacity: pd.DataFrame,
    chip_load: pd.DataFrame,
    wafer_load: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate required equipment from already prepared Chip and Wafer loads."""
    prepared_reqb = _prepare_reqb(reqb)
    if prepared_reqb.empty:
        return _empty_required_equipment_result()
    loads = _build_loads(
        plan,
        None,
        None,
        set(prepared_reqb["소요기준"].unique()),
        chip_load=chip_load,
        wafer_load=wafer_load,
    )
    return _calculate_required_equipment_from_prepared(
        prepared_reqb,
        loads,
        unit_capacity,
    )


def _prepare_reqb(reqb: pd.DataFrame) -> pd.DataFrame:
    _require_columns(reqb, REQB_COLUMNS, "RQ_REQB")
    prepared_reqb = reqb[REQB_COLUMNS].copy()
    _normalize_month(prepared_reqb, "RQ_REQB")
    _normalize_text(prepared_reqb, REQB_TEXT_COLUMNS)
    prepared_reqb["소요기준"] = prepared_reqb["소요기준"].str.upper()
    prepared_reqb = prepared_reqb.loc[~prepared_reqb["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if prepared_reqb.empty:
        return prepared_reqb
    _normalize_basis(prepared_reqb, "RQ_REQB")
    _assert_complete(prepared_reqb, REQB_REQUIRED_KEYS, "RQ_REQB")
    _normalize_area_name(prepared_reqb, "RQ_REQB")
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
    _require_columns(data, required, "소요대수")
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
    yield_data: pd.DataFrame | None,
    chip_qty: pd.DataFrame | None,
    required_bases: set[str],
    *,
    chip_load: pd.DataFrame | None = None,
    wafer_load: pd.DataFrame | None = None,
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
    _require_columns(plan, plan_columns, "RQ_PKG_PLAN")
    prepared_plan = plan.copy()
    _normalize_month(prepared_plan, "RQ_PKG_PLAN")
    _normalize_text(
        prepared_plan,
        ["양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS"],
    )
    prepared_plan["생산수량"] = _numeric(prepared_plan["생산수량"], "RQ_PKG_PLAN.생산수량")

    load_frames: list[pd.DataFrame] = []
    if "PKG" in required_bases:
        pkg = prepared_plan[plan_columns].rename(columns={"생산수량": "부하량"})
        pkg["WF 구분"] = "PKG"
        pkg["소요기준"] = "PKG"
        load_frames.append(pkg)
    needs_chip = "CHIP" in required_bases
    needs_wafer = "WF" in required_bases
    if needs_chip and chip_load is None and needs_wafer and wafer_load is None:
        if yield_data is None or chip_qty is None:
            raise ValueError("Chip·Wafer 부하량 또는 수율·Chip 기준정보가 필요합니다.")
        chip_load, wafer_load = calculate_chip_and_wafer_loads(
            prepared_plan,
            yield_data,
            chip_qty,
        )
    if needs_chip:
        if chip_load is None:
            if yield_data is None or chip_qty is None:
                raise ValueError("Chip 부하량 또는 수율·Chip 기준정보가 필요합니다.")
            chip_load = calculate_chip_load(prepared_plan, yield_data, chip_qty)
        chip = chip_load.rename(columns={"물량": "부하량"})
        chip["소요기준"] = "CHIP"
        load_frames.append(chip)
    if needs_wafer:
        if wafer_load is None:
            if yield_data is None or chip_qty is None:
                raise ValueError("Wafer 부하량 또는 수율·Chip 기준정보가 필요합니다.")
            wafer_load = calculate_wafer_load(prepared_plan, yield_data, chip_qty)
        wafer = wafer_load.rename(columns={"물량": "부하량"})
        wafer["소요기준"] = "WF"
        load_frames.append(wafer)

    loads = pd.concat(load_frames, ignore_index=True)[[*LOAD_KEYS, "부하량"]]
    _normalize_text(loads, [key for key in LOAD_KEYS if key not in {"생산계획년월", "소요기준"}])
    _normalize_basis(loads, "부하량")
    return loads.groupby(LOAD_KEYS, as_index=False, dropna=False)[["부하량"]].sum()


def _prepare_capacities(data: pd.DataFrame) -> pd.DataFrame:
    _require_columns(data, [*CAPACITY_KEYS, "대당 Capa"], "대당 Capa")
    result = data[[*CAPACITY_KEYS, "대당 Capa"]].copy()
    _normalize_month(result, "대당 Capa")
    _normalize_text(
        result,
        [key for key in CAPACITY_KEYS if key not in {"생산계획년월", "소요기준"}],
    )
    _normalize_area_name(result, "대당 Capa")
    _normalize_basis(result, "대당 Capa")
    result["대당 Capa"] = _numeric(result["대당 Capa"], "대당 Capa")
    duplicated = result.duplicated(CAPACITY_KEYS, keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, CAPACITY_KEYS].drop_duplicates().head(5)
        raise ValueError(f"대당 Capa 연결 키가 중복되었습니다: {examples.to_dict('records')}")
    return result


def _normalize_basis(data: pd.DataFrame, table_name: str) -> None:
    data["소요기준"] = data["소요기준"].astype("string").str.strip().str.upper()
    data["소요기준"] = data["소요기준"].replace({"WAFER": "WF"})
    invalid = ~data["소요기준"].isin(["PKG", "WF", "CHIP"])
    if invalid.any():
        values = data.loc[invalid, "소요기준"].drop_duplicates().head(5).tolist()
        raise ValueError(f"{table_name}에 지원하지 않는 소요기준이 있습니다: {values}")


def _normalize_area_name(data: pd.DataFrame, table_name: str) -> None:
    area_names = data["Area_Name"].astype("string").str.strip().str.casefold()
    invalid = area_names.isna() | ~area_names.isin(["main", "mi"])
    if invalid.any():
        values = data.loc[invalid, "Area_Name"].drop_duplicates().head(5).tolist()
        raise ValueError(f"{table_name}의 Area_Name은 Main 또는 MI여야 합니다: {values}")
    data["Area_Name"] = area_names.map({"main": "Main", "mi": "MI"})


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()


def _normalize_month(data: pd.DataFrame, table_name: str) -> None:
    numeric = pd.to_numeric(data["생산계획년월"], errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    data["생산계획년월"] = months


def _assert_complete(data: pd.DataFrame, columns: list[str], table_name: str) -> None:
    has_missing = any(data[column].isna().any() for column in columns)
    has_blank = any(data[column].eq("").any() for column in columns)
    if has_missing or has_blank:
        raise ValueError(f"{table_name}의 필수 컬럼에 누락값이 있습니다.")


def _numeric(series: pd.Series, label: str) -> pd.Series:
    result = pd.to_numeric(series, errors="coerce")
    if result.isna().any():
        raise ValueError(f"{label}에 숫자가 아닌 값 또는 누락값이 있습니다.")
    return result.astype("float64")


def _require_columns(data: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{table_name} 필수 컬럼이 없습니다: {', '.join(missing)}")
