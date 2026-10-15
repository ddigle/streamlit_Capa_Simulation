# Purpose: RQ_REQB 경로와 부하량·대당 Capa를 연결해 STEP별 소요대수와 그 제외 목록을 만든다.

from typing import NamedTuple

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
    LOAD_EXCLUSION_COLUMNS,
    LOAD_EXCLUSIONS_ATTR,
    PLAN_QUANTITY_BLANK_REASON,
    blank_quantity_exclusions,
    calculate_chip_and_wafer_loads,
    calculate_chip_load,
    calculate_wafer_load,
    drop_unplanned_rows,
    plan_quantities,
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
# `RQ_REQB` 경로 쪽 제외 — 대당 Capa 가 없거나 0 이하인 경로, PKG 의 Buffer 외 행.
REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR = "excluded_required_equipment_rows"
# ------------------------------------------------------------------ 소요대수에 들지 않은 계획
# 경로 쪽 제외와 달리 **계획 쪽**에서 빠진 것 둘이다. 어느 쪽이든 그 수요는 어느 공정의
# 소요대수에도 들지 않아 확보율이 그만큼 높게 나온다. 0 으로 접고 말하지 않으면 「계획이 없어
# 0」과 갈리지 않으므로 결과 attrs 로 이어 산출 결과·HOME·저장·발행 검사가 건수를 알린다
# (`required_exclusion_counts`).
#
# - 부하량에서 빠진 계획: `RQ_CHIP_QTY`·`RQ_YLD` 가 없거나 값이 비어 환산하지 못한 계획 행과
#   생산수량이 빈 행. 레코드 꼴은 환산 탭의 제외 목록(`load_calculator.LOAD_EXCLUSION_COLUMNS`)과
#   같다.
# - 경로 없는 계획: 부하량은 났는데 같은 소요기준의 `RQ_REQB` 경로 키에 하나도 닿지 않은 부하.
#   사유가 셋이고 앞의 둘만 센다(아래).
#
# 둘 다 `생산계획년월` 컬럼을 가진 DataFrame 이라 조회기간 자르기(`slice_capacity_months`)가
# 같이 자른다.
REQUIRED_LOAD_EXCLUSIONS_ATTR = "excluded_required_load_rows"
UNROUTED_LOADS_ATTR = "unrouted_required_loads"
# 경로 없는 계획의 사유. 부하량은 계획 전 행에 소요기준마다 만들어지므로(PKG 는 REQB 어딘가에 PKG
# 행만 있으면 모든 계획에) 「닿지 않음」에는 고칠 어긋남과 구조가 섞인다. 경로 쪽 제외의
# `PKG_UNCOUNTED_REASON` 처럼 구조는 목록에 남기되 세지 않는다 — 세면 HOME·저장·발행 경고가 모두에게
# 늘 뜨고, 그 경고(「확보율이 실제보다 높게」)는 그 경우 사실도 아니다.
#
# - 경로 키 어긋남(셈): 같은 (소요기준, 제품정보, Stack, 연결용 WF 구분) 경로가 다른 달·양산구분·
#   Capa Code·Customer·CS 에는 있는데 이 부하 키만 못 닿았다. 계획 편집·연도 이동·월 병합이 만든다.
# - RQ_REQB 에 없는 제품(셈): 그 제품정보·Stack 의 경로가 `RQ_REQB` 에 하나도 없다(소요기준·WF 구분
#   무관). 그 제품의 수요 전체가 어느 공정에도 들지 않는다.
# - 그 소요기준·WF 구분 경로 없음(세지 않음): 제품은 `RQ_REQB` 에 있는데 이 소요기준·WF 구분의
#   경로를 아예 갖지 않는다 — EDP-TSV 의 PKG(사내 실데이터는 PKG 경로가 HBM 에만 있고 모두
#   BUFFER), PKG 경로가 Buffer 외 행뿐인 제품, 경로 없는 WF 구분의 Chip 부하. 규칙상 쓰지 않는
#   조합이다.
UNROUTED_REASON_COLUMN = "제외사유"
UNROUTED_KEY_MISMATCH_REASON = "경로 키 어긋남"
UNROUTED_UNKNOWN_PRODUCT_REASON = "RQ_REQB 에 없는 제품"
UNROUTED_UNUSED_REASON = "그 소요기준·WF 구분 경로 없음"
UNROUTED_LOAD_COLUMNS = [*LOAD_KEYS, "부하량", UNROUTED_REASON_COLUMN]


class RequiredExclusionCounts(NamedTuple):
    """소요대수에 들지 않은 수요의 건수. 화면·검사가 한 줄로 알릴 때 쓴다."""

    # `RQ_CHIP_QTY`·`RQ_YLD` 가 없거나 값이 비어 부하량에서 빠진 계획(레코드 수).
    excluded_plans: int = 0
    # 생산수량이 비어 계획 없음(0)으로 본 계획(레코드 수).
    blank_plans: int = 0
    # 부하량은 났는데 `RQ_REQB` 경로 키에 닿지 않은 부하(부하량 키 수). 규칙상 쓰지 않는 조합
    # (`UNROUTED_UNUSED_REASON`)은 세지 않는다.
    unrouted_loads: int = 0
    # 부하가 붙었는데 대당 Capa 가 없거나 0 이하라 소요대수에서 뺀 경로(`RQ_REQB` 행 수).
    excluded_routes: int = 0


def calculate_required_equipment(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate required equipment for every RQ_REQB row."""
    prepared_reqb, route_products = _prepare_reqb(reqb)
    if prepared_reqb.empty:
        return _empty_required_equipment_result()

    loads, load_exclusions = _build_loads(
        plan,
        yield_data,
        chip_qty,
        set(prepared_reqb["소요기준"].unique()),
    )
    output = _calculate_required_equipment_from_prepared(
        prepared_reqb,
        loads,
        unit_capacity,
        route_products,
    )
    output.attrs[REQUIRED_LOAD_EXCLUSIONS_ATTR] = load_exclusions
    return output


def required_exclusion_counts(required_equipment: pd.DataFrame) -> RequiredExclusionCounts:
    """소요대수 결과의 attrs 에서 소요대수에 들지 않은 수요 건수를 센다.

    경로 쪽 제외는 **부하가 붙은 것만** 센다. 부하 0 인 경로는 빠져도 소요대수가 같고, PKG 의
    Buffer 외 행은 규칙대로 세지 않은 것이라 고칠 것이 없다 — 둘을 세면 늘 뜨는 경고가 된다.
    경로 없는 계획도 같은 까닭으로 규칙상 쓰지 않는 조합은 세지 않는다(`counted_unrouted_loads`).
    """
    load_rows = required_equipment.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR)
    unrouted = required_equipment.attrs.get(UNROUTED_LOADS_ATTR)
    routes = required_equipment.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR)
    excluded_routes = 0
    if isinstance(routes, pd.DataFrame) and {"제외사유", "부하량"} <= set(routes.columns):
        lost = routes["제외사유"].ne(PKG_UNCOUNTED_REASON) & pd.to_numeric(
            routes["부하량"], errors="coerce"
        ).gt(0)
        excluded_routes = int(lost.sum())
    blank_plans = excluded_plans = 0
    if isinstance(load_rows, pd.DataFrame) and "누락 기준정보" in load_rows.columns:
        blank = load_rows["누락 기준정보"].eq(PLAN_QUANTITY_BLANK_REASON)
        blank_plans = int(blank.sum())
        excluded_plans = len(load_rows) - blank_plans
    return RequiredExclusionCounts(
        excluded_plans=excluded_plans,
        blank_plans=blank_plans,
        unrouted_loads=(
            len(counted_unrouted_loads(unrouted)) if isinstance(unrouted, pd.DataFrame) else 0
        ),
        excluded_routes=excluded_routes,
    )


def counted_unrouted_loads(unrouted: pd.DataFrame) -> pd.DataFrame:
    """경로 없는 계획 가운데 **고칠 것**(경로 키 어긋남·RQ_REQB 에 없는 제품)만 고른다.

    건수(`required_exclusion_counts`)와 산출 결과 목록이 같은 행을 보게 한 곳에 둔다. 사유 컬럼이
    없는 프레임은 모두 고칠 것으로 본다 — 세지 않을 근거가 없다.
    """
    if UNROUTED_REASON_COLUMN not in unrouted.columns:
        return unrouted
    return unrouted.loc[unrouted[UNROUTED_REASON_COLUMN].ne(UNROUTED_UNUSED_REASON)]


# 「RQ_REQB 에 없는 제품」을 가르는 키. 소요기준·WF 구분과 무관하게 그 제품의 경로가 하나라도
# 있는지.
_ROUTE_PRODUCT_KEYS = ["제품정보", "Stack"]


def _prepare_reqb(reqb: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """계산할 경로(구현된 소요기준만)와 경로가 있는 제품정보·Stack 고유 목록.

    제품 목록은 미구현 소요기준(BOX·PCB)을 빼기 **전에** 만든다 — 그런 경로만 있는 제품도
    `RQ_REQB` 에 있는 제품이다(그 부하는 규칙상 쓰지 않는 조합).
    """
    require_columns(reqb, REQB_COLUMNS, "RQ_REQB")
    prepared_reqb = reqb[REQB_COLUMNS].copy()
    normalize_month_column(prepared_reqb, "RQ_REQB")
    strip_text_columns(prepared_reqb, REQB_TEXT_COLUMNS)
    route_products = prepared_reqb[_ROUTE_PRODUCT_KEYS].drop_duplicates()
    prepared_reqb["소요기준"] = prepared_reqb["소요기준"].str.upper()
    prepared_reqb = prepared_reqb.loc[~prepared_reqb["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if prepared_reqb.empty:
        return prepared_reqb, route_products
    prepared_reqb["소요기준"] = validate_demand_basis(prepared_reqb["소요기준"], "RQ_REQB")
    assert_complete(prepared_reqb, REQB_REQUIRED_KEYS, "RQ_REQB")
    prepared_reqb["Area_Name"] = normalize_area_name(prepared_reqb["Area_Name"], "RQ_REQB")
    # 표기만 다른 경로 행(`WF`·`Wafer`, `Main`·`MAIN`, 앞뒤 공백)을 접는다. 접지 않으면 같은 부하량·
    # 대당 Capa 를 두 번 받아 소요대수가 두 배다. 위에서 이미 계산 꼴로 정규화했으므로 그대로
    # `duplicated` 로 접는다 — 등록의 `frame_contracts.duplicate_route_rows` 와 같은 행이 남는다.
    folded = prepared_reqb.loc[~prepared_reqb.duplicated(subset=REQB_COLUMNS)]
    return folded.reset_index(drop=True), route_products


def _empty_required_equipment_result() -> pd.DataFrame:
    empty_result = pd.DataFrame(columns=[*REQB_COLUMNS, "부하량", "대당 Capa", "소요대수"])
    empty_result.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR] = pd.DataFrame()
    empty_result.attrs[REQUIRED_LOAD_EXCLUSIONS_ATTR] = pd.DataFrame(columns=LOAD_EXCLUSION_COLUMNS)
    empty_result.attrs[UNROUTED_LOADS_ATTR] = pd.DataFrame(columns=UNROUTED_LOAD_COLUMNS)
    return empty_result


def _calculate_required_equipment_from_prepared(
    prepared_reqb: pd.DataFrame,
    loads: pd.DataFrame,
    unit_capacity: pd.DataFrame,
    route_products: pd.DataFrame,
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
    output.attrs[UNROUTED_LOADS_ATTR] = _unrouted_loads(counted_reqb, loads, route_products)
    return output


# PKG 부하량은 WF 구분 없이 경로에 잇는다(위 「소요기준 PKG」). 두 병합이 같은 키를 쓰도록
# 한 곳에서 만든다.
_LOAD_JOIN_COLUMN = "_부하량_WF"
_LOAD_JOIN_KEYS = [_LOAD_JOIN_COLUMN if key == "WF 구분" else key for key in LOAD_KEYS]


def _with_load_join_key(frame: pd.DataFrame) -> pd.DataFrame:
    """PKG 는 빈 문자열, 나머지는 WF 구분인 연결 키 컬럼을 더한 사본."""
    return frame.assign(
        **{_LOAD_JOIN_COLUMN: frame["WF 구분"].where(frame["소요기준"].ne(PKG_BASIS), "")}
    )


def _attach_loads(reqb: pd.DataFrame, loads: pd.DataFrame) -> pd.DataFrame:
    """`RQ_REQB` 행마다 부하량을 붙인다. 행 순서는 `reqb` 그대로다.

    PKG 행은 WF 구분 없이 잇고, CHIP·WF 행은 WF 구분까지 잇는다. 한 번의
    병합으로 하려고 키 하나(`_부하량_WF`)를 만든다 — PKG 는 빈 문자열, 나머지는 WF 구분이다.
    둘로 나눠 병합해 다시 붙이면 행 순서가 바뀐다.

    연결되지 않은 경로의 부하량은 0 이다. 그 공정·제품이 그 달에 계획이 없으면 정말 0 이다.
    반대쪽 — 어느 경로에도 닿지 않은 부하량 — 은 `_unrouted_loads` 가 따로 남긴다.
    """
    left = _with_load_join_key(reqb)
    right = _with_load_join_key(loads).drop(columns="WF 구분")
    result = left.merge(right, on=_LOAD_JOIN_KEYS, how="left", validate="many_to_one")
    result["부하량"] = result["부하량"].fillna(0.0)
    return result.drop(columns=_LOAD_JOIN_COLUMN)


# 「경로 키 어긋남」을 가르는 키 — 연결 키에서 달·양산구분·Capa Code·Customer·CS 를 뺀 것.
_ROUTE_FAMILY_KEYS = ["소요기준", "제품정보", "Stack", _LOAD_JOIN_COLUMN]


def _unrouted_loads(
    reqb: pd.DataFrame, loads: pd.DataFrame, route_products: pd.DataFrame
) -> pd.DataFrame:
    """같은 소요기준의 `RQ_REQB` 경로 키에 하나도 닿지 않은 부하량(0 초과)을 사유와 함께 돌려준다.

    `_attach_loads` 는 경로를 왼쪽에 두므로 닿지 않은 부하량은 결과 어디에도 남지 않는다 — 계획
    총 부하가 결과 부하보다 큰데 그 차이를 설명할 목록이 없다. 연결 키는 `_attach_loads` 와 같다
    (PKG 는 Buffer 행만 남긴 경로에 WF 구분 없이). 그래서 「계획 총 부하 = 결과에 붙은 부하 + 이
    목록」이 부하량 키 단위로 맞는다 — 세지 않는 사유의 행도 목록에서 빼지 않는 까닭이다.
    """
    keyed_routes = _with_load_join_key(reqb)
    routes = keyed_routes[_LOAD_JOIN_KEYS].drop_duplicates()
    merged = _with_load_join_key(loads).merge(
        routes,
        on=_LOAD_JOIN_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_route_merge",
    )
    unrouted = merged.loc[merged["_route_merge"].eq("left_only") & merged["부하량"].gt(0)]
    has_family = _keys_in(unrouted, keyed_routes, _ROUTE_FAMILY_KEYS)
    has_product = _keys_in(unrouted, route_products, _ROUTE_PRODUCT_KEYS)
    reasons = (
        pd.Series(UNROUTED_UNKNOWN_PRODUCT_REASON, index=unrouted.index, dtype="object")
        .mask(has_product, UNROUTED_UNUSED_REASON)
        .mask(has_family, UNROUTED_KEY_MISMATCH_REASON)
    )
    result = unrouted.assign(**{UNROUTED_REASON_COLUMN: reasons})
    return result[UNROUTED_LOAD_COLUMNS].reset_index(drop=True)


def _keys_in(frame: pd.DataFrame, known: pd.DataFrame, keys: list[str]) -> pd.Series:
    """`frame` 행마다 `keys` 조합이 `known` 에 있는지. 행 순서·색인은 `frame` 그대로다."""
    if frame.empty:
        return pd.Series(False, index=frame.index, dtype="bool")
    present = pd.MultiIndex.from_frame(frame[keys]).isin(
        pd.MultiIndex.from_frame(known[keys].drop_duplicates())
    )
    return pd.Series(present, index=frame.index, dtype="bool")


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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """소요기준별 부하량과 **부하량에서 빠진 계획** 목록.

    빠진 계획은 Chip·Wafer 환산의 제외 attrs 와 생산수량이 빈 행이다. 부하량 프레임들은 아래에서
    concat·groupby 를 지나 attrs 가 사라지므로 따로 꺼내 돌려준다.
    """
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
    prepared_plan["생산수량"] = plan_quantities(prepared_plan).astype("float64")
    # 이 경로는 load_calculator._prepare_plan 을 거치지 않으므로 여기서도 제외한다. 빈 생산수량은
    # 환산과 같이 「계획 없음(0)」으로 빼되 목록에 남긴다 — 환산은 0 으로 보는데 소요대수만 멈추면
    # 같은 계획이 화면마다 다른 뜻이 된다.
    excluded_rows: list[tuple[object, ...]] = list(blank_quantity_exclusions(prepared_plan))
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
    for load in (chip_load, wafer_load):
        # Chip·Wafer 는 같은 환산 바탕에서 나와 제외 목록이 같다. 겹치는 레코드는 아래에서 접는다.
        if load is not None:
            excluded_rows.extend(load.attrs.get(LOAD_EXCLUSIONS_ATTR, ()))
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
    excluded = pd.DataFrame(list(dict.fromkeys(excluded_rows)), columns=LOAD_EXCLUSION_COLUMNS)
    return loads.groupby(LOAD_KEYS, as_index=False, dropna=False)[["부하량"]].sum(), excluded


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
