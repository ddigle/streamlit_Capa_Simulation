# Purpose: 공정별 부하 산출 예외가 선언 공정의 Wafer 경로 부하량만 바꾸고 나머지는 두는지 본다.

"""공정별 부하 산출 예외(`services/route_load_exceptions.py` · `required_equipment` 훅).

견본은 `dummy_series_tables` 의 합성 표(제품 셋 · 달 둘)이고 공정 이름은 합성 `DEMO-*` 다. 선언
공정 `DEMO-EXC` 와 같은 경로를 가진 다른 공정 `DEMO-PROC` 를 함께 두어, 선언이 그 공정에만
걸리는지 본다. 기대값은 계산기 출력이 아니라 손으로 푼 산식이다. 경로 달에는 계획이 없는
달(202603)을 하나 더 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence

import dummy_series_tables as demo
import pandas as pd
import pytest

from capa_simulation.services import route_load_exceptions
from capa_simulation.services.dashboard import (
    build_monthly_wafer_load_from_load,
    home_aggregation_wafer_load,
)
from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    calculate_wafer_load,
)
from capa_simulation.services.product_share import build_product_volume
from capa_simulation.services.required_equipment import (
    LOAD_KEYS,
    REQB_COLUMNS,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
    UNROUTED_LOADS_ATTR,
    calculate_required_equipment,
    required_exclusion_counts,
)
from capa_simulation.services.route_load_exceptions import (
    BUFFER_X_CORE_CHIP,
    NO_ROUTE_LOAD_EXCEPTIONS,
    ROUTE_LOAD_BASIS_MISSING_REASON,
    ROUTE_LOAD_FORMULAS,
    RouteLoadDeclaration,
    build_route_load_bases,
    route_load_basis,
)
from capa_simulation.services.weighted_unit_capacity import effective_process_capacity_long

_EXC = "DEMO-EXC"
_OTHER = "DEMO-PROC"
_FOLLOWER = "DEMO-EXTRA"
_STEPS = ("S10", "S20")
_NO_PLAN_MONTH = 202603
_ROUTE_MONTHS = (*demo.MONTHS, _NO_PLAN_MONTH)
_CAPACITY = 10.0
# (제품정보, WF 구분) — 표기는 `dummy_series_tables` 그대로다. DEMO-HBM 의 Top_Dummy 는
# 대문자 `TOP_DUMMY` 다.
_ROUTES = (
    (demo.HBM, "Buffer"),
    (demo.HBM, "Core"),
    (demo.HBM, "Top"),
    (demo.HBM, "Dummy"),
    (demo.HBM, "TOP_DUMMY"),
    (demo.DUMMY_ONLY, "Dummy"),
    (demo.DUMMY_ONLY, "Top_Dummy"),
)
_DECLARED: RouteLoadDeclaration = {_EXC: BUFFER_X_CORE_CHIP}
_ROUTE_KEYS = ["공정", "생산계획년월", "STEP_SEQ", "제품정보", "WF 구분"]

# 손으로 푼 DEMO-HBM 부하량(`dummy_series_tables._ROUTE_ROWS`). 생산수량 202601 100 · 202602 120.
# Buffer 는 구분_Chip 1 · Net Die 400 · EDS 0.9, Core 는 구분_Chip 12 · Net Die 800 · EDS 0.8,
# BE 는 모두 0.95 다.
_HBM_QUANTITY = {202601: 100.0, 202602: 120.0}


def _buffer_wafer(month: int) -> float:
    return _HBM_QUANTITY[month] * 1_000 * 1.0 / 0.9 / 0.95 / 400


def _core_general(month: int) -> float:
    return _HBM_QUANTITY[month] * 1_000 * 12.0 / 0.8 / 0.95 / 800


def _core_exception(month: int) -> float:
    return _buffer_wafer(month) * 12.0


def _route_tables(
    processes: Sequence[str] = (_EXC, _OTHER), *, basis: str = "WF"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """공정마다 같은 경로(두 STEP)를 둔 `RQ_REQB` 와 대당 Capa(경로마다 같은 값)."""
    keys = [
        {
            "생산계획년월": month,
            "Area_Name": "Main",
            "공정": process,
            "양산구분": "양산",
            "제품정보": product,
            "Stack": "12H",
            "WF 구분": division,
            "STEP_SEQ": step,
            "MCP_SEQ": "1",
            "소요기준": basis,
        }
        for process in processes
        for month in _ROUTE_MONTHS
        for step in _STEPS
        for product, division in _ROUTES
    ]
    reqb = pd.DataFrame(
        [
            {**key, "Capa Code": f"{key['제품정보']}-CC", "Customer": "DEMO-CUST", "CS": "MP"}
            for key in keys
        ]
    )
    capacity = pd.DataFrame([{**key, "대당 Capa": _CAPACITY} for key in keys])
    return reqb, capacity


def _calculate(
    declaration: RouteLoadDeclaration = NO_ROUTE_LOAD_EXCEPTIONS,
    *,
    processes: Sequence[str] = (_EXC, _OTHER),
    basis: str = "WF",
    chip_qty: pd.DataFrame | None = None,
) -> pd.DataFrame:
    reqb, capacity = _route_tables(processes, basis=basis)
    return calculate_required_equipment(
        reqb,
        demo.plan(),
        demo.yields(),
        demo.chip_qty() if chip_qty is None else chip_qty,
        capacity,
        route_exceptions=declaration,
    )


def _by_route(result: pd.DataFrame) -> pd.DataFrame:
    return result.set_index(_ROUTE_KEYS).sort_index()


def _values(
    result: pd.DataFrame,
    process: str,
    division: str,
    *,
    column: str = "부하량",
    month: int | None = None,
    step: str | None = None,
) -> list[float]:
    """한 공정 · 한 `WF 구분` 경로 줄의 값(달 · STEP 으로 좁힐 수 있다). 결과 행 차례다."""
    mask = result["공정"].eq(process) & result["WF 구분"].eq(division)
    if month is not None:
        mask &= result["생산계획년월"].eq(month)
    if step is not None:
        mask &= result["STEP_SEQ"].eq(step)
    return [float(value) for value in result.loc[mask, column].to_numpy(dtype="float64")]


def _basis_missing(result: pd.DataFrame) -> pd.DataFrame:
    excluded = result.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR]
    assert isinstance(excluded, pd.DataFrame)
    if excluded.empty:
        return excluded
    return excluded.loc[excluded["제외사유"].eq(ROUTE_LOAD_BASIS_MISSING_REASON)]


def test_the_declared_core_route_takes_buffer_wafer_times_the_core_chip_count() -> None:
    result = _calculate(_DECLARED)

    for month in demo.MONTHS:
        assert _core_exception(month) != pytest.approx(_core_general(month))
        expected = [_core_exception(month)] * len(_STEPS)
        assert _values(result, _EXC, "Core", month=month) == pytest.approx(expected)
        assert _values(result, _EXC, "Core", column="소요대수", month=month) == pytest.approx(
            [load / _CAPACITY for load in expected]
        )
    assert _values(result, _EXC, "Core", month=_NO_PLAN_MONTH) == [0.0] * len(_STEPS)


def test_the_declared_top_dummy_route_keeps_its_row_with_zero_load() -> None:
    """Top_Dummy 는 부하 0 이고 줄은 남는다 — 표기(`TOP_DUMMY` · `Top_Dummy`)를 가리지 않는다."""
    off = _calculate()
    result = _calculate(_DECLARED)

    rows = len(_ROUTE_MONTHS) * len(_STEPS)
    for division in ("TOP_DUMMY", "Top_Dummy"):
        assert _values(result, _EXC, division) == [0.0] * rows
        assert _values(result, _EXC, division, column="소요대수") == [0.0] * rows
        assert min(_values(off, _EXC, division, month=202601)) > 0
    assert _basis_missing(result).empty


def test_other_divisions_and_other_processes_keep_the_general_load() -> None:
    off = _by_route(_calculate())
    result = _by_route(_calculate(_DECLARED))

    assert result.index.equals(off.index)
    division = result.index.get_level_values("WF 구분").str.casefold()
    changed = result.index.get_level_values("공정").isin([_EXC]) & division.isin(
        ["core", "top_dummy"]
    )
    pd.testing.assert_frame_equal(result.loc[~changed], off.loc[~changed])
    other = result.index.get_level_values("공정") == _OTHER
    pd.testing.assert_frame_equal(result.loc[other], off.loc[other])
    assert _values(off.reset_index(), _OTHER, "Core", month=202601) == pytest.approx(
        [_core_general(202601)] * len(_STEPS)
    )


def test_every_step_of_the_declared_process_gets_the_same_original_demand() -> None:
    """공정 단위로 건다 — 공정 유효 Capa 의 원수요 일치 검사를 지나고 원수요는 예외 부하 하나다."""
    result = _calculate(_DECLARED)

    effective = effective_process_capacity_long(result, "WF 구분")

    core = effective.loc[
        effective["공정"].eq(_EXC)
        & effective["WF 구분"].eq("Core")
        & effective["생산계획년월"].eq(202601)
    ]
    assert len(core) == 1
    assert core["원수요_부하량"].iloc[0] == pytest.approx(_core_exception(202601))
    assert core["STEP_소요대수"].iloc[0] == pytest.approx(
        len(_STEPS) * _core_exception(202601) / _CAPACITY
    )


def test_a_zero_core_chip_count_gives_zero_without_an_exclusion() -> None:
    chip = demo.chip_qty()
    chip.loc[chip["제품정보"].eq(demo.HBM) & chip["WF 구분"].eq("Core"), "구분_Chip"] = 0.0

    result = _calculate(_DECLARED, chip_qty=chip)

    core = result.loc[result["공정"].eq(_EXC) & result["WF 구분"].eq("Core")]
    assert len(core) == len(_ROUTE_MONTHS) * len(_STEPS)
    assert core["부하량"].eq(0.0).all()
    assert _basis_missing(result).empty


def test_a_missing_buffer_load_with_a_general_core_load_is_a_counted_exclusion() -> None:
    """바탕 없음은 일반 Core 부하가 0 보다 클 때만 세는 제외다 — 계획 없는 달은 0 으로 남는다."""
    chip = demo.chip_qty()
    chip = chip.loc[~(chip["제품정보"].eq(demo.HBM) & chip["WF 구분"].eq("Buffer"))]
    off = _calculate(chip_qty=chip)

    result = _calculate(_DECLARED, chip_qty=chip)

    missing = _basis_missing(result)
    assert list(missing.columns) == [*REQB_COLUMNS, "부하량", "대당 Capa", "제외사유"]
    assert sorted(zip(missing["생산계획년월"], missing["STEP_SEQ"], strict=True)) == sorted(
        (month, step) for month in demo.MONTHS for step in _STEPS
    )
    assert set(missing["공정"]) == {_EXC}
    assert set(missing["WF 구분"]) == {"Core"}
    for month in demo.MONTHS:
        loads = missing.loc[missing["생산계획년월"].eq(month), "부하량"]
        assert loads.tolist() == pytest.approx([_core_general(month)] * len(_STEPS))
    assert missing["대당 Capa"].isna().all()

    core = result.loc[result["공정"].eq(_EXC) & result["WF 구분"].eq("Core")]
    assert core["생산계획년월"].tolist() == [_NO_PLAN_MONTH] * len(_STEPS)
    assert core["부하량"].eq(0.0).all()
    other_core = result.loc[result["공정"].eq(_OTHER) & result["WF 구분"].eq("Core")]
    assert other_core["부하량"].max() == pytest.approx(_core_general(202602))
    counts_on, counts_off = required_exclusion_counts(result), required_exclusion_counts(off)
    assert counts_on.excluded_routes == counts_off.excluded_routes + len(demo.MONTHS) * len(_STEPS)
    assert counts_on._replace(excluded_routes=0) == counts_off._replace(excluded_routes=0)


def test_a_top_dummy_route_without_unit_capacity_is_not_counted_as_lost_demand() -> None:
    """예외는 대당 Capa 를 잇기 전에 걸린다 — 부하 0 이 된 Top_Dummy 경로는 대당 Capa 가 없어도
    소요대수 밖 수요로 세지 않는다(끔에서는 제 부하가 있어 센다)."""
    reqb, capacity = _route_tables()
    lost = (
        capacity["공정"].eq(_EXC)
        & capacity["생산계획년월"].eq(202601)
        & capacity["STEP_SEQ"].eq("S10")
        & capacity["WF 구분"].eq("TOP_DUMMY")
    )
    capacity = capacity.loc[~lost]
    tables = (reqb, demo.plan(), demo.yields(), demo.chip_qty(), capacity)

    off = calculate_required_equipment(*tables)
    on = calculate_required_equipment(*tables, route_exceptions=_DECLARED)

    excluded = on.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR]
    assert isinstance(excluded, pd.DataFrame)
    row = excluded.loc[excluded["공정"].eq(_EXC) & excluded["WF 구분"].eq("TOP_DUMMY")]
    assert row["제외사유"].tolist() == ["대당 Capa 없음"]
    assert row["부하량"].tolist() == [0.0]
    counts_on, counts_off = required_exclusion_counts(on), required_exclusion_counts(off)
    assert counts_off.excluded_routes == 1
    assert counts_on.excluded_routes == 0


def _hbm_spelled_upper(frame: pd.DataFrame) -> pd.DataFrame:
    """DEMO-HBM 의 `WF 구분` 을 원천처럼 대문자(`BUFFER` · `CORE` · `TOP` · `DUMMY` ·
    `TOP_DUMMY`)로 적은 사본. 다른 제품은 그대로다."""
    hbm = frame["제품정보"].eq(demo.HBM)
    division = frame["WF 구분"].astype("string")
    return frame.assign(**{"WF 구분": division.mask(hbm, division.str.upper()).astype("object")})


def test_an_upper_case_source_takes_the_same_exception() -> None:
    """원천 표기는 대문자다 — 경로 · 수율 · Chip 구성이 모두 `BUFFER` · `CORE` 여도 같은 값을
    받는다.

    경로 쪽(Core 줄 고르기)과 바탕 쪽(Buffer 부하 · Core `구분_Chip` 고르기)이 저마다 표기를
    가리지 않아야 한다. 경로 쪽만 글자 그대로 견주면 Core 줄이 일반 산식 값으로 남고, 바탕 쪽만
    그러면 Core 줄이 「부하 예외 바탕 없음」 으로 빠진다.
    """
    reqb, capacity = _route_tables()
    tables = (
        _hbm_spelled_upper(reqb),
        demo.plan(),
        _hbm_spelled_upper(demo.yields()),
        _hbm_spelled_upper(demo.chip_qty()),
        _hbm_spelled_upper(capacity),
    )

    off = calculate_required_equipment(*tables)
    result = calculate_required_equipment(*tables, route_exceptions=_DECLARED)

    for month in demo.MONTHS:
        assert _values(off, _EXC, "CORE", month=month) == pytest.approx(
            [_core_general(month)] * len(_STEPS)
        )
        assert _values(result, _EXC, "CORE", month=month) == pytest.approx(
            [_core_exception(month)] * len(_STEPS)
        )
    assert _values(result, _EXC, "TOP_DUMMY") == [0.0] * (len(_ROUTE_MONTHS) * len(_STEPS))
    assert _basis_missing(result).empty
    off_routes, result_routes = _by_route(off), _by_route(result)
    assert result_routes.index.equals(off_routes.index)
    division = result_routes.index.get_level_values("WF 구분").str.casefold()
    changed = result_routes.index.get_level_values("공정").isin([_EXC]) & division.isin(
        ["core", "top_dummy"]
    )
    pd.testing.assert_frame_equal(result_routes.loc[~changed], off_routes.loc[~changed])


@pytest.mark.parametrize(
    ("key", "value"),
    [("Capa Code", "DEMO-HBM-CC2"), ("Customer", "DEMO-CUST2"), ("CS", "ES")],
)
def test_each_business_key_keeps_its_own_buffer_basis(key: str, value: str) -> None:
    """바탕 키는 `WF 구분` 만 뺀 부하 키다 — Capa Code · Customer · CS 가 다른 계획은 제 Buffer
    부하를 바탕으로 가져 섞이지 않는다.

    DEMO-HBM 계획에 그 키 하나만 다르고 생산수량이 다른 행을 더한다(경로는 없다). 선언 공정의
    Core 줄은 제 계획의 Buffer 부하만 곱한다 — 바탕 키에서 그 칸이 빠지면 한 키에 바탕이 둘이
    되어 멈춘다.
    """
    reqb, capacity = _route_tables()
    plan = demo.plan()
    sibling = plan.loc[plan["제품정보"].eq(demo.HBM)]
    sibling = sibling.assign(생산수량=sibling["생산수량"] * 3)
    sibling[key] = value
    plan = pd.concat([plan, sibling], ignore_index=True)

    result = calculate_required_equipment(
        reqb, plan, demo.yields(), demo.chip_qty(), capacity, route_exceptions=_DECLARED
    )

    for month in demo.MONTHS:
        assert _values(result, _EXC, "Core", month=month) == pytest.approx(
            [_core_exception(month)] * len(_STEPS)
        )
    assert _basis_missing(result).empty


# 경로가 없는 제품 — DEMO-HBM 과 같은 기준정보를 가진 합성 제품이다(이 시험만 쓴다).
_UNROUTED_HBM = "DEMO-HBM2"


def _with_buffer_spelled_twice(product: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """`product` 의 Buffer 를 `BUFFER` 로 한 벌 더 적은 계획 · `RQ_YLD` · `RQ_CHIP_QTY`.

    같은 부하 키에 Buffer Wafer 부하가 둘 생긴다(옛 리비전이 경로를 두 표기로 저장한 일이 있다).
    `_UNROUTED_HBM` 이면 DEMO-HBM 의 계획 · 기준정보를 그 이름으로 한 벌 더한 뒤 겹친다.
    """
    plan, yields, chip = demo.plan(), demo.yields(), demo.chip_qty()
    if product == _UNROUTED_HBM:
        plan = pd.concat(
            [plan, plan.loc[plan["제품정보"].eq(demo.HBM)].assign(제품정보=product)],
            ignore_index=True,
        )
        yields = pd.concat(
            [yields, yields.loc[yields["제품정보"].eq(demo.HBM)].assign(제품정보=product)],
            ignore_index=True,
        )
        chip = pd.concat(
            [chip, chip.loc[chip["제품정보"].eq(demo.HBM)].assign(제품정보=product)],
            ignore_index=True,
        )
    buffer_yield = yields.loc[yields["제품정보"].eq(product) & yields["WF 구분"].eq("Buffer")]
    buffer_chip = chip.loc[chip["제품정보"].eq(product) & chip["WF 구분"].eq("Buffer")]
    return (
        plan,
        pd.concat([yields, buffer_yield.assign(**{"WF 구분": "BUFFER"})], ignore_index=True),
        pd.concat([chip, buffer_chip.assign(**{"WF 구분": "BUFFER"})], ignore_index=True),
    )


def test_two_buffer_bases_for_one_key_stop_only_where_a_declared_core_route_uses_it() -> None:
    """한 부하 키에 바탕이 둘이면 어느 값을 곱할지 모른다 — 선언 공정의 Core 줄이 그 키를 쓸 때만
    멈추고(끔에서는 그대로 선다), 경로가 없는 다른 제품의 겹침으로는 멈추지 않는다."""
    reqb, capacity = _route_tables()
    plan, yields, chip = _with_buffer_spelled_twice(demo.HBM)
    calculate_required_equipment(reqb, plan, yields, chip, capacity)

    with pytest.raises(ValueError, match="부하 예외 바탕"):
        calculate_required_equipment(reqb, plan, yields, chip, capacity, route_exceptions=_DECLARED)

    plan, yields, chip = _with_buffer_spelled_twice(_UNROUTED_HBM)
    wafer = calculate_wafer_load(plan, yields, chip)
    loads = wafer.rename(columns={"물량": "부하량"}).assign(소요기준="WF")
    bases = build_route_load_bases(loads, chip, LOAD_KEYS)
    unrouted_bases = bases.loc[bases["제품정보"].eq(_UNROUTED_HBM)]
    assert unrouted_bases.duplicated(subset=[*bases.columns[:-1]]).any()
    result = calculate_required_equipment(
        reqb, plan, yields, chip, capacity, route_exceptions=_DECLARED
    )
    assert _values(result, _EXC, "Core", month=202601) == pytest.approx(
        [_core_exception(202601)] * len(_STEPS)
    )


def _assert_same_result(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(left, right)
    assert set(left.attrs) == set(right.attrs)
    for name in left.attrs:
        pd.testing.assert_frame_equal(left.attrs[name], right.attrs[name], obj=str(name))


@pytest.mark.parametrize(
    ("declaration", "basis"),
    [
        ({"DEMO-ABSENT": BUFFER_X_CORE_CHIP}, "WF"),
        ({_EXC: BUFFER_X_CORE_CHIP}, "CHIP"),
    ],
    ids=["absent-process", "chip-basis-only"],
)
def test_a_declaration_that_reaches_no_wafer_route_leaves_the_result_as_today(
    declaration: RouteLoadDeclaration, basis: str
) -> None:
    """선언 공정이 이번 경로에 없거나 그 공정이 CHIP 경로뿐이면 결과 · attrs 가 선언 없음과 같다.

    빈 선언이 지금 계산과 같다는 것은 선언을 넘기지 않는 `tests/test_required_equipment.py` 가
    받친다 — 빈 선언과 기본값은 같은 길이라 여기서 견줘도 드러나는 것이 없다.
    """
    off = _calculate(basis=basis)

    result = _calculate(declaration, basis=basis)

    _assert_same_result(result, off)


def _home_outputs(plan: pd.DataFrame, wafer_load: pd.DataFrame) -> list[pd.DataFrame]:
    home = home_aggregation_wafer_load(wafer_load)
    return [home, build_monthly_wafer_load_from_load(home), build_product_volume(plan, home)]


def test_wafer_counts_home_aggregation_and_load_table_do_not_move() -> None:
    """경로 부하량만 바뀐다 — 입력 표 · Wafer 매수 집계 · HOME 세 함수 · 부하량 표에서 나온 셈은
    켬/끔에서 같다.

    HOME 계산 캐시 래퍼는 아직 선언을 받지 않는다(답 대기). 여기서는 캐시 없는 세 함수를 선언
    계산 앞뒤로 같은 입력 객체에서 다시 불러, 훅이 입력을 제자리에서 고치지 않았는지까지 본다.
    """
    reqb, capacity = _route_tables()
    plan, yields, chip = demo.plan(), demo.yields(), demo.chip_qty()
    inputs_before = [frame.copy() for frame in (reqb, plan, yields, chip, capacity)]
    chip_before, wafer_before = calculate_chip_and_wafer_loads(plan, yields, chip)
    home_before = _home_outputs(plan, wafer_before)

    off = calculate_required_equipment(reqb, plan, yields, chip, capacity)
    on = calculate_required_equipment(
        reqb, plan, yields, chip, capacity, route_exceptions=_DECLARED
    )

    for frame, before in zip((reqb, plan, yields, chip, capacity), inputs_before, strict=True):
        pd.testing.assert_frame_equal(frame, before)
    chip_after, wafer_after = calculate_chip_and_wafer_loads(plan, yields, chip)
    pd.testing.assert_frame_equal(chip_after, chip_before)
    pd.testing.assert_frame_equal(wafer_after, wafer_before)
    for after, before in zip(_home_outputs(plan, wafer_after), home_before, strict=True):
        pd.testing.assert_frame_equal(after, before)
    for name in (REQUIRED_LOAD_EXCLUSIONS_ATTR, UNROUTED_LOADS_ATTR):
        pd.testing.assert_frame_equal(on.attrs[name], off.attrs[name], obj=name)
    assert not on["부하량"].equals(off["부하량"])


def test_an_extra_process_following_the_declared_process_is_not_carried_along() -> None:
    """부대공정은 따라 걸리지 않는다.

    따라가기 꼴 부대공정은 참조 공정의 경로 줄을 제 이름으로 이어받는다(`extra_process_merge`
    R-02). 선언은 공정 이름으로만 고르므로 그 줄은 일반 산식이고, 그 이름을 선언에 더할 때만
    걸린다.
    """
    processes = (_EXC, _OTHER, _FOLLOWER)
    off = _calculate(processes=processes)

    reference_only = _calculate(_DECLARED, processes=processes)
    both = _calculate({**_DECLARED, _FOLLOWER: BUFFER_X_CORE_CHIP}, processes=processes)

    follower = _by_route(reference_only).index.get_level_values("공정") == _FOLLOWER
    pd.testing.assert_frame_equal(
        _by_route(reference_only).loc[follower], _by_route(off).loc[follower]
    )
    per_step = len(_STEPS)
    assert _values(reference_only, _EXC, "Core", month=202601) == pytest.approx(
        [_core_exception(202601)] * per_step
    )
    assert _values(reference_only, _FOLLOWER, "Core", month=202601) == pytest.approx(
        [_core_general(202601)] * per_step
    )
    assert _values(both, _FOLLOWER, "Core", month=202601) == pytest.approx(
        [_core_exception(202601)] * per_step
    )
    assert _values(both, _FOLLOWER, "TOP_DUMMY", month=202601) == [0.0] * per_step


def test_process_names_are_matched_without_case_or_surrounding_spaces() -> None:
    expected = _calculate(_DECLARED)

    result = _calculate({f"  {_EXC.lower()} ": BUFFER_X_CORE_CHIP})

    _assert_same_result(result, expected)


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ({_EXC: "no_such_formula"}, "모르는 산식 id"),
        ({"  ": BUFFER_X_CORE_CHIP}, "빈 공정 이름"),
    ],
)
def test_an_unusable_declaration_stops_instead_of_falling_back(
    declaration: RouteLoadDeclaration, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _calculate(declaration)


def test_two_spellings_of_one_process_with_different_formulas_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        route_load_exceptions,
        "ROUTE_LOAD_FORMULAS",
        {**ROUTE_LOAD_FORMULAS, "demo_second": "견본 산식"},
    )

    with pytest.raises(ValueError, match="대소문자만 다른 두 공정"):
        route_load_exceptions.normalize_route_load_declaration(
            {_EXC: BUFFER_X_CORE_CHIP, _EXC.lower(): "demo_second"}
        )


@pytest.mark.parametrize(
    ("process", "division", "basis", "expected"),
    [
        (_EXC, "Core", "WF", "Buffer Wafer × Core 구분_Chip"),
        (_EXC, "CORE", "Wafer", "Buffer Wafer × Core 구분_Chip"),
        (_EXC, "TOP_DUMMY", "WF", "부하 0"),
        (_EXC, "Buffer", "WF", ""),
        (_EXC, "Top", "WF", ""),
        (_EXC, "Core", "CHIP", ""),
        (_OTHER, "Core", "WF", ""),
    ],
)
def test_the_route_basis_text_names_only_the_rows_the_formula_changes(
    process: str, division: str, basis: str, expected: str
) -> None:
    assert route_load_basis(process, division, basis, _DECLARED) == expected
    assert route_load_basis(process, division, basis, NO_ROUTE_LOAD_EXCEPTIONS) == ""


def test_formula_ids_carry_no_process_name() -> None:
    """산식 id 는 공정 이름이 아니라 식의 이름이다 — 소문자 · 숫자 · 밑줄만, 글은 식을 말한다."""
    assert set(ROUTE_LOAD_FORMULAS) == {BUFFER_X_CORE_CHIP}
    for formula_id, label in ROUTE_LOAD_FORMULAS.items():
        assert formula_id.replace("_", "").isalnum() and formula_id == formula_id.lower()
        assert "Buffer" in label and "Core" in label
