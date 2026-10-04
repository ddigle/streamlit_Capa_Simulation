# Purpose: RQ_REQB 경로와 소요기준 부하량·대당 Capa를 연결해 STEP별 소요대수를 계산한다.

import pandas as pd

from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import (
    UNIMPLEMENTED_BASES,
    assert_complete,
    match_key,
    normalize_area_name,
    normalize_month_column,
    require_columns,
    scalar_match_key,
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
# ------------------------------------------------------------------ 소요기준 PKG
# 소요기준 PKG 는 Buffer 위에 Core·Top·Dummy 를 쌓고(스택) Mold·MPGA Saw 로 PKG Chip 단위까지
# 자른 **뒤의** 공정이다. 그때부터는 Wafer 가 아니라 PKG Chip 을 투입한다(2026-09-28 사용자
# 설명). 그래서 두 가지가 다르다.
#
# - **부하량에 수율을 걸지 않는다.** EDS·BE 불량 Die 는 이미 걸러졌고 Good Die 만 들어온다.
#   부하량은 생산수량 그대로다.
# - **Buffer 로만 센다.** Core·Top·Dummy 는 Buffer 위에 쌓여 있어 따로 세면 같은 PKG 를 스택
#   수만큼 센다. `RQ_REQB` 의 PKG 행에 다른 WF 구분이 와도 부하량을 붙이지 않는다.
#
# PKG 부하량에는 WF 구분이 없다 — 스택된 PKG 한 개가 한 개다. 그래서 부하량과 `RQ_REQB` 를
# 이을 때 WF 구분을 키로 쓰지 않는다. 예전에는 부하량에 `WF 구분 = "PKG"` 를 얹어 이었는데,
# 실제 `RQ_REQB` 의 PKG 행은 `BUFFER` 처럼 실제 분류값을 싣고 `"PKG"` 라는 값은 없어서 연결이
# 늘 실패했다. 실패한 부하량은 0 으로 채워져 PKG 기준 소요대수가 **말없이 0** 이었다.
#
# 이름만 보고 가른다(제품타입을 보지 않는다). `RQ_REQB` 에는 제품타입이 없고, `Buffer` 라는
# 이름은 두 제품군 가운데 HBM 에만 있어 `Top` 처럼 양쪽에 걸릴 일이 없다. 비교는 대소문자를
# 가리지 않는다(원천 `BUFFER` · 표본 `Buffer`).
PKG_BASIS = "PKG"
PKG_COUNTED_DIVISIONS = ("Buffer",)
PKG_UNCOUNTED_REASON = "PKG 기준은 Buffer 로만 계수"

REQB_TEXT_COLUMNS = [column for column in REQB_COLUMNS if column != "생산계획년월"]
REQB_REQUIRED_KEYS = list(dict.fromkeys([*LOAD_KEYS, *CAPACITY_KEYS]))
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
    strip_text_columns(prepared_reqb, REQB_TEXT_COLUMNS)
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

    # PKG 행 가운데 Buffer 가 아닌 것은 계산에 넣지 않고 사유를 달아 제외 목록에 남긴다.
    # 0 으로 두고 넘어가면 「부하량이 없어서 0」과 「세지 않아서 0」이 화면에서 갈리지 않는다.
    is_pkg = prepared_reqb["소요기준"].eq(PKG_BASIS)
    counted_divisions = {scalar_match_key(name) for name in PKG_COUNTED_DIVISIONS}
    uncounted_pkg = is_pkg & ~match_key(prepared_reqb["WF 구분"]).isin(counted_divisions)
    uncounted_rows = prepared_reqb.loc[uncounted_pkg, REQB_COLUMNS].copy()
    uncounted_rows["부하량"] = 0.0
    uncounted_rows["대당 Capa"] = float("nan")
    uncounted_rows["제외사유"] = PKG_UNCOUNTED_REASON
    counted_reqb = prepared_reqb.loc[~uncounted_pkg]

    result = _attach_loads(counted_reqb, loads)
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
    exclusions = [frame for frame in (uncounted_rows, excluded_rows) if not frame.empty]
    output.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR] = (
        pd.concat(exclusions, ignore_index=True)
        if exclusions
        else excluded_rows.reset_index(drop=True)
    )
    return output


def _attach_loads(reqb: pd.DataFrame, loads: pd.DataFrame) -> pd.DataFrame:
    """`RQ_REQB` 행마다 부하량을 붙인다. 행 순서는 `reqb` 그대로다.

    PKG 행은 WF 구분 없이 잇고, CHIP·WF 행은 WF 구분까지 잇는다. 한 번의
    병합으로 하려고 키 하나(`_부하량_WF`)를 만든다 — PKG 는 빈 문자열, 나머지는 WF 구분이다.
    둘로 나눠 병합해 다시 붙이면 행 순서가 바뀐다.

    연결되지 않은 부하량은 0 이다. 그 공정·제품이 그 달에 계획이 없으면 정말 0 이다.
    """
    join_column = "_부하량_WF"
    keys = [join_column if key == "WF 구분" else key for key in LOAD_KEYS]
    left = reqb.assign(**{join_column: reqb["WF 구분"].where(reqb["소요기준"].ne(PKG_BASIS), "")})
    right = loads.assign(
        **{join_column: loads["WF 구분"].where(loads["소요기준"].ne(PKG_BASIS), "")}
    ).drop(columns="WF 구분")
    result = left.merge(right, on=keys, how="left", validate="many_to_one")
    result["부하량"] = result["부하량"].fillna(0.0)
    return result.drop(columns=join_column)


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
    strip_text_columns(
        prepared_plan,
        ["양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS"],
    )
    prepared_plan["생산수량"] = to_numeric_strict(prepared_plan["생산수량"], "RQ_PKG_PLAN.생산수량")
    # 이 경로는 load_calculator._prepare_plan 을 거치지 않으므로 여기서도 제외한다.
    prepared_plan = drop_unplanned_rows(prepared_plan)

    load_frames: list[pd.DataFrame] = []
    if PKG_BASIS in required_bases:
        # 수율을 걸지 않는다 — PKG 공정에는 Good Die 만 들어온다. WF 구분도 없다(위 설명).
        pkg = prepared_plan[plan_columns].rename(columns={"생산수량": "부하량"})
        pkg["WF 구분"] = ""
        pkg["소요기준"] = PKG_BASIS
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
    strip_text_columns(loads, [key for key in LOAD_KEYS if key not in {"생산계획년월", "소요기준"}])
    loads["소요기준"] = validate_demand_basis(loads["소요기준"], "부하량")
    return loads.groupby(LOAD_KEYS, as_index=False, dropna=False)[["부하량"]].sum()


def _prepare_capacities(data: pd.DataFrame) -> pd.DataFrame:
    require_columns(data, [*CAPACITY_KEYS, "대당 Capa"], "대당 Capa")
    result = data[[*CAPACITY_KEYS, "대당 Capa"]].copy()
    normalize_month_column(result, "대당 Capa")
    strip_text_columns(
        result,
        [key for key in CAPACITY_KEYS if key not in {"생산계획년월", "소요기준"}],
    )
    result["Area_Name"] = normalize_area_name(result["Area_Name"], "대당 Capa")
    result["소요기준"] = validate_demand_basis(result["소요기준"], "대당 Capa")
    result["대당 Capa"] = to_numeric_strict(result["대당 Capa"], "대당 Capa")
    assert_unique_keys(result, CAPACITY_KEYS, "대당 Capa 연결 키가")
    return result
