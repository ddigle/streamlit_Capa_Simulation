import pandas as pd

from capa_simulation.services.load_calculator import (
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
CAPACITY_KEYS = ["생산계획년월", "공정", "소요기준", "양산구분", "제품정보", "Stack", "WF 구분"]
RESULT_DIMENSIONS = [
    "Area_Name",
    "공정",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "소요기준",
]
REQB_TEXT_COLUMNS = [column for column in REQB_COLUMNS if column != "생산계획년월"]
REQB_REQUIRED_KEYS = list(dict.fromkeys([*LOAD_KEYS, *CAPACITY_KEYS]))


def calculate_required_equipment(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate required equipment for every RQ_REQB row."""
    _require_columns(reqb, REQB_COLUMNS, "RQ_REQB")
    prepared_reqb = reqb[REQB_COLUMNS].copy()
    _normalize_month(prepared_reqb, "RQ_REQB")
    _normalize_text(prepared_reqb, REQB_TEXT_COLUMNS)
    _normalize_basis(prepared_reqb, "RQ_REQB")
    _assert_complete(prepared_reqb, REQB_REQUIRED_KEYS, "RQ_REQB")

    loads = _build_loads(
        plan,
        yield_data,
        chip_qty,
        set(prepared_reqb["소요기준"].unique()),
    )
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
    if missing_capacity.any():
        examples = result.loc[missing_capacity, CAPACITY_KEYS].drop_duplicates().head(5)
        raise ValueError(
            "대당 Capa가 연결되지 않는 RQ_REQB 기준이 있습니다: "
            f"{examples.to_dict('records')}"
        )
    result = result.drop(columns="_capacity_merge")
    if result["대당 Capa"].le(0).any():
        examples = result.loc[result["대당 Capa"].le(0), CAPACITY_KEYS].drop_duplicates().head(5)
        raise ValueError(f"대당 Capa는 0보다 커야 합니다: {examples.to_dict('records')}")
    result["소요대수"] = result["부하량"] / result["대당 Capa"]
    return result[[*REQB_COLUMNS, "부하량", "대당 Capa", "소요대수"]]


def required_equipment_to_month_table(data: pd.DataFrame) -> pd.DataFrame:
    """Aggregate RQ_REQB results by output dimensions and pivot month columns."""
    required = [*REQB_COLUMNS, "소요대수"]
    _require_columns(data, required, "소요대수")
    pivot_input = (
        data.groupby(
            ["생산계획년월", *RESULT_DIMENSIONS],
            as_index=False,
            dropna=False,
        )["소요대수"]
        .sum()
    )
    pivot_input[RESULT_DIMENSIONS] = pivot_input[RESULT_DIMENSIONS].fillna("")
    result = pivot_input.pivot(
        index=RESULT_DIMENSIONS,
        columns="생산계획년월",
        values="소요대수",
    ).reset_index()
    result.columns.name = None
    month_columns = sorted(column for column in result.columns if column not in RESULT_DIMENSIONS)
    result = result.rename(columns={month: str(int(month)) for month in month_columns})
    return result[[*RESULT_DIMENSIONS, *[str(int(month)) for month in month_columns]]]


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
    if "CHIP" in required_bases:
        chip = calculate_chip_load(prepared_plan, yield_data, chip_qty).rename(
            columns={"물량": "부하량"}
        )
        chip["소요기준"] = "CHIP"
        load_frames.append(chip)
    if "WF" in required_bases:
        wafer = calculate_wafer_load(prepared_plan, yield_data, chip_qty).rename(
            columns={"물량": "부하량"}
        )
        wafer["소요기준"] = "WF"
        load_frames.append(wafer)

    loads = pd.concat(load_frames, ignore_index=True)[[*LOAD_KEYS, "부하량"]]
    _normalize_text(loads, [key for key in LOAD_KEYS if key not in {"생산계획년월", "소요기준"}])
    _normalize_basis(loads, "부하량")
    return loads.groupby(LOAD_KEYS, as_index=False, dropna=False)["부하량"].sum()


def _prepare_capacities(data: pd.DataFrame) -> pd.DataFrame:
    _require_columns(data, [*CAPACITY_KEYS, "대당 Capa"], "대당 Capa")
    result = data[[*CAPACITY_KEYS, "대당 Capa"]].copy()
    _normalize_month(result, "대당 Capa")
    _normalize_text(result, [key for key in CAPACITY_KEYS if key not in {"생산계획년월", "소요기준"}])
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
    if data[columns].isna().any(axis=None) or data[columns].eq("").any(axis=None):
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
