# Purpose: 제약 시뮬레이션의 보유 제약 설비·「신규 설비는 개조 없이」 옵션이 채우는 차례·신규 대기와
# 확보율을 손계산과 맞댄다.

"""제약 시뮬레이션 2판 옵션(`services/constraint_simulation.py` — 2026-10-26 사용자 결정).

**기대값은 손계산이다.** 하네스는 `tests/test_constraint_simulation.py` 의 합성 TC Bonding 예시
그대로다 (업무 사실이 아니다) — 기간 202706~202712, 제약 120%, 개조 30일, Cut-off 7. 그 하네스의
늘어난 전용 대수(growth)는 06 6 · 07 2 · 08 1 · 09 1 · 10 0 · 11 1 · 12 0 이고 1판 개조 창은 (06
6대) (07 2대) (08 1대) (09 1대) (11 1대)다. 30일 개조 창은 앞 달 W/D 한 칸에 다 들어 06 몫 n대는
5월에 n × 30/31, 07 몫은 6월에 n × 30/30, 08·09·11 몫은 7·8·10월에 n × 30/31 이다.

W/D 첫날(그 달 1일 − 7일)은 06 5/25 · 07 6/24 · 08 7/25 · 09 8/25 · 11 10/25, W/D 구간은 5월
4/24~5/24(31일) · 6월 5/25~6/23(30일) · 7월 6/24~7/24(31일)이다.

채우는 차례는 `FILL_ORDER`(① 신규 → ② 보유 — 2026-10-26 오후 사용자 답) 뒤 남는 몫이 ③ 개조이고
③ 만 창을 낸다. 신규
호기는 기여 시작 d 에서 개조 일수 D 안에 아직 채우지 않은 증가(그 달 W/D 첫날 t — `0 ≤ t − d ≤ D`)가
있으면 붙고 `[d, t)` 가 신규 대기(개조 비가동처럼 W/D 일할)다. 없으면 일반 설비다(2026-10-26 오후
사용자 결정 — 「같은 달 증가분만」·「반 달 신규는 다음 달」 을 대신한다).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import cast

import pytest
from test_constraint_simulation import (
    AVAILABLE,
    CONDITIONS,
    MONTHS,
    PRODUCT,
    REQUIRED,
    _inputs,
    _one,
    _pct,
    _run,
)

import capa_simulation.services.constraint_simulation as constraint_simulation
from capa_simulation.services.constraint_simulation import (
    FILL_NEW,
    FILL_OWNED,
    ConstraintConditions,
    ConstraintResult,
    FillSource,
    NewUnit,
    simulate_constraint,
)

SINCE = date(2026, 10, 26)
NEW_ON = replace(CONDITIONS, new_unit_since=SINCE)
JUNE_FIRST = date(2027, 5, 25)
"""6월 W/D 첫날 — 6월 증가의 t."""

JULY_FIRST = date(2027, 6, 24)
"""7월 W/D 첫날 — 7월 증가의 t."""

D_BEFORE_JUNE = JUNE_FIRST - timedelta(days=30)
"""6월 증가보다 개조 일수(30)만큼 앞 — 4/25."""


def _unit(name: str, start: date, *, units: float = 1.0, until: date | None = None) -> NewUnit:
    return NewUnit(name=name, start=start, units=units, until=until)


def _new(
    *units: NewUnit, owned: int = 0, conditions: ConstraintConditions = NEW_ON
) -> ConstraintResult:
    """하네스 + 신규 옵션 켬(+ 보유)."""
    return simulate_constraint(_inputs(), replace(conditions, owned_units=owned), units)


def _windows(result: ConstraintResult) -> list[tuple[int, int]]:
    return [(window.month, window.units) for window in result.windows]


def _assignments(result: ConstraintResult) -> list[tuple[str, int, float, int]]:
    return [(item.unit, item.month, item.units, item.days) for item in result.assignments]


def _assert_conserved(result: ConstraintResult) -> None:
    """개조 켬이면 달마다 구성 합 = 전용, 늘어난 대수 = pool − 앞 달 pool, 창 대수 합 = 개조
    대수, 붙인 신규 몫의 합 = 신규 누적이다."""
    previous_pool, previous_inside = 0, False
    for row in result.months:
        carried = previous_pool if row.in_period and previous_inside else 0
        if row.in_period:
            assert row.owned_dedicated + row.new_dedicated + row.modified_dedicated == row.dedicated
            assert row.growth == row.dedicated - carried
        else:
            assert (row.owned_dedicated, row.new_dedicated, row.modified_dedicated) == (0, 0, 0)
            assert row.growth == 0
        assigned = sum(item.units for item in result.assignments if item.month == row.month)
        assert assigned == pytest.approx(row.new_increment)
        previous_pool, previous_inside = row.dedicated, row.in_period
    assert sum(window.units for window in result.windows) == result.kpis.modified_units
    for item in result.assignments:
        assert 0 <= item.days <= (result.conditions.modification_days or 0)


# ------------------------------------------------------------------ 기본값은 1판 그대로


def test_the_defaults_leave_every_value_of_the_first_version() -> None:
    """보유 0 · 신규 끔이면 결과가 1판과 같다 — 신규 호기가 실려 와도(틀린 값이어도) 끈 옵션은 보지
    않는다. 신규 대기·붙인 몫·받은 신규가 모두 빈다."""
    plain = _run()
    carried = simulate_constraint(
        _inputs(), CONDITIONS, (_unit("N1", JUNE_FIRST), _unit("N1", JUNE_FIRST, units=-1.0))
    )
    assert carried == plain
    assert (plain.new_units, plain.assignments, plain.waits_before_range) == ((), (), False)
    assert all(row.waiting == 0.0 and row.waiting_shares == () for row in plain.months)
    assert plain.kpis.modified_units == plain.kpis.max_dedicated == 11
    assert (plain.kpis.owned_used, plain.kpis.new_used) == (0, 0)
    assert not CONDITIONS.splits_dedicated
    _assert_conserved(plain)


def test_modification_off_locks_both_options() -> None:
    """개조 끔은 설비가 서로 바뀐다는 뜻이라 개조가 없다 — 보유·신규가 걸리지 않고 결과가 같다."""
    off = replace(CONDITIONS, modification_days=None)
    locked = replace(off, owned_units=5, new_unit_since=SINCE)
    plain = simulate_constraint(_inputs(), off)
    result = simulate_constraint(_inputs(), locked, (_unit("N1", JUNE_FIRST),))

    assert not locked.uses_owned_units and not locked.uses_new_units
    assert not locked.splits_dedicated
    assert [row.existing_rate for row in result.months] == [
        row.existing_rate for row in plain.months
    ]
    assert result.kpis.modified_units is None and result.kpis.max_dedicated is None
    for row in result.months:
        assert (row.owned_increment, row.new_increment, row.waiting) == (0, 0, 0.0)
    assert (result.new_units, result.assignments) == ((), ())


# ------------------------------------------------------------------ ① 보유 제약 설비


def test_four_owned_units_cover_the_first_month_before_any_modification() -> None:
    """보유 4 — 6월 몫 6대 중 4대는 개조 없이, 2대만 개조. 5월 비가동 6 × 30/31 → 2 × 30/31.

    5월 기존 = (48 − 60/31) ÷ 42 = 109.68%(1판 100.46%, 제약 없을 때 114.29%). 6월부터는 1판과 같다.
    """
    result = simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=4))
    plain = _run()

    assert _windows(result) == [(202706, 2), (202707, 2), (202708, 1), (202709, 1), (202711, 1)]
    may = result.month(202705)
    assert may.downtime == pytest.approx(60 / 31)
    assert may.existing_rate == pytest.approx((48 - 60 / 31) / 42)
    assert may.existing_rate == _pct(109.68)
    june = result.month(202706)
    assert (june.owned_increment, june.new_increment, june.increment) == (4, 0, 2)
    assert (june.owned_dedicated, june.modified_dedicated, june.dedicated) == (4, 2, 6)
    for month in MONTHS[MONTHS.index(202706) :]:
        assert result.month(month).existing_rate == plain.month(month).existing_rate
    kpis = result.kpis
    assert (kpis.max_dedicated, kpis.owned_used, kpis.new_used, kpis.modified_units) == (
        11,
        4,
        0,
        7,
    )
    assert kpis.window_count == 5
    assert kpis.first_downtime_day == date(2027, 4, 25)
    assert kpis.below_months == (202705, 202706, 202707, 202708, 202710)
    assert CONDITIONS.modifies and replace(CONDITIONS, owned_units=4).splits_dedicated
    _assert_conserved(result)


def test_six_owned_units_clear_may_and_start_the_impact_in_june() -> None:
    """보유 6 — 6월 몫이 모두 보유라 5월 비가동이 없다(114.29% = 제약 없을 때). 첫 창은 7월 몫 2대,
    6월 비가동 2 × 30/30 → 6월 기존 = (48 − 2 − 6) ÷ 38 = 105.26%."""
    result = simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=6))

    assert _windows(result) == [(202707, 2), (202708, 1), (202709, 1), (202711, 1)]
    assert result.month(202705).downtime == 0.0
    assert result.month(202705).existing_rate == result.month(202705).baseline_rate
    assert result.month(202706).existing_rate == pytest.approx(40 / 38)
    assert result.kpis.first_downtime_day == date(2027, 5, 25)
    assert result.kpis.first_impact_month == 202706
    assert result.kpis.below_months == (202706, 202707, 202708, 202710)
    assert result.kpis.modified_units == 5
    _assert_conserved(result)


def test_owned_units_left_over_are_used_when_the_need_grows_later() -> None:
    """보유 7 — 6월 6대를 보유로 쓰고 남은 1대가 7월 증가 2대 중 1대를 덮는다(남는 동안은
    기존 몫)."""
    result = simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=7))

    assert _windows(result) == [(202707, 1), (202708, 1), (202709, 1), (202711, 1)]
    june, july = result.month(202706), result.month(202707)
    assert (june.owned_increment, june.increment) == (6, 0)
    # 6월은 보유 7대 중 6대만 뗀다 — 남는 1대는 기존 제품 몫(기존 가용 = 48 − 6월 비가동 1 − 6).
    assert june.allocated == 6
    assert june.existing_available == pytest.approx(48 - 1.0 - 6)
    assert (july.owned_increment, july.increment, july.owned_dedicated) == (1, 1, 7)
    assert result.kpis.owned_used == 7
    _assert_conserved(result)


@pytest.mark.parametrize("owned", [11, 20])
def test_owned_units_beyond_the_need_go_to_existing_products(owned: int) -> None:
    """보유가 기간 최대 필요(11)보다 많으면 개조가 없고, 실제로 뗀 대수만 전용이다 — 남는 보유는
    기존 제품 몫이라 확보율이 개조 끔과 같다(이 하네스는 필요가 줄지 않는다)."""
    result = simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=owned))
    off = _run(replace(CONDITIONS, modification_days=None))

    assert result.windows == ()
    assert [row.existing_rate for row in result.months] == [row.existing_rate for row in off.months]
    assert result.month(202712).dedicated == 11
    assert result.kpis.owned_used == 11
    assert result.kpis.modified_units == 0
    _assert_conserved(result)


# ---------------------------------------------------- ② 신규 설비는 개조 없이(미리 붙이기)


def test_a_unit_exactly_d_days_before_the_growth_waits_instead_of_a_modification() -> None:
    """N1 기여 시작 4/25 = 6월 W/D 첫날 5/25 − 30일 — `t − d = 30 = D` 라 붙인다.

    6월 증가 6 = 신규 1 + 개조 5. 대기 [4/25, 5/25) 30일은 모두 5월 W/D(4/24~5/24, 31일) 안이라 5월
    대기 = 1 × 30/31, 개조 비가동 = 5 × 30/31 → 합 180/31 로 1판(6 × 30/31)과 같다 — 손해는 개조와
    같고 개조가 한 대 준다. 그래서 모든 달의 기존 확보율이 1판과 같다.
    """
    result = _new(_unit("N1", D_BEFORE_JUNE))
    plain = _run()

    assert _windows(result) == [(202706, 5), (202707, 2), (202708, 1), (202709, 1), (202711, 1)]
    assert _assignments(result) == [("N1", 202706, 1.0, 30)]
    may = result.month(202705)
    assert may.waiting == pytest.approx(30 / 31)
    assert may.downtime == pytest.approx(150 / 31)
    assert [share.days for share in may.waiting_shares] == [30]
    for month in MONTHS:
        assert result.month(month).existing_rate == pytest.approx(plain.month(month).existing_rate)
    june = result.month(202706)
    assert (june.new_increment, june.increment, june.new_dedicated) == (1, 5, 1)
    assert (result.kpis.modified_units, result.kpis.new_used) == (10, 1)
    assert result.ordinary_units == ()
    _assert_conserved(result)


def test_one_day_more_than_d_leaves_the_unit_ordinary() -> None:
    """4/24(`t − d = 31 > 30`)는 6월 증가에 못 붙고 7월(6/24 − 4/24 = 61일)에도 못 붙는다 — 기간
    전에 기존 제품에 쓰인 일반 설비라 1판과 모든 값이 같다(답 1-3 의 좁혀진 뜻)."""
    result = _new(_unit("N1", D_BEFORE_JUNE - timedelta(days=1)))
    plain = _run()

    assert _windows(result) == _windows(plain)
    assert result.assignments == ()
    assert [row.existing_rate for row in result.months] == [
        row.existing_rate for row in plain.months
    ]
    assert all(row.waiting == 0.0 for row in result.months)
    assert [unit.name for unit in result.ordinary_units] == ["N1"]
    assert result.kpis.new_used == 0
    _assert_conserved(result)


def test_a_mid_month_arrival_waits_for_the_next_month_growth() -> None:
    """6/10(6월 W/D 5/25~6/23 가운데) — 6월 증가(5/25)는 지났고 7월 증가(6/24)가 14일 뒤라 붙인다.

    7월 증가 2 = 신규 1 + 개조 1. 6월 비가동 = 7월 개조 1 × 30/30, 6월 대기 = 1 × 14/30 → 6월 기존 =
    (48 − 1 − 14/30 − 6) ÷ 38 = 106.67%(1판 105.26%). 반 달 신규를 다음 달 몫으로 그냥 넘기던 옛
    규칙과 달리 그 14일이 손해로 선다.
    """
    result = _new(_unit("N1", date(2027, 6, 10)))

    assert _windows(result) == [(202706, 6), (202707, 1), (202708, 1), (202709, 1), (202711, 1)]
    assert _assignments(result) == [("N1", 202707, 1.0, 14)]
    june = result.month(202706)
    assert june.downtime == pytest.approx(1.0)
    assert june.waiting == pytest.approx(14 / 30)
    assert june.existing_rate == pytest.approx((48 - 1 - 14 / 30 - 6) / 38)
    assert june.existing_rate == _pct(106.67)
    july = result.month(202707)
    assert (july.new_increment, july.increment) == (1, 1)
    assert july.waiting == 0.0
    assert result.month(202705).existing_rate == _run().month(202705).existing_rate
    _assert_conserved(result)


def test_a_unit_arriving_before_the_period_within_d_is_dedicated_early() -> None:
    """5/10 — 제약 기간 전이지만 6월 증가(5/25)가 15일 뒤라 미리 붙인다(옛 답 1-3 이면 개조).

    6월 증가 6 = 신규 1 + 개조 5. 5월 = 개조 5 × 30/31 + 대기 1 × 15/31 = 165/31 → 기존 (48 −
    165/31) ÷ 42 = 101.61%(1판 100.46%).
    """
    result = _new(_unit("N1", date(2027, 5, 10)))

    assert _assignments(result) == [("N1", 202706, 1.0, 15)]
    may = result.month(202705)
    assert may.downtime + may.waiting == pytest.approx(165 / 31)
    assert may.existing_rate == pytest.approx((48 - 165 / 31) / 42)
    assert may.existing_rate == _pct(101.61)
    assert result.kpis.modified_units == 10
    _assert_conserved(result)


def test_two_units_cover_one_growth() -> None:
    """5/20 · 5/25 두 대가 6월 증가 6 중 2대 — 개조 4. 5/25 는 그 달 W/D 첫날이라 대기 0일이다.

    5월 = 개조 4 × 30/31 + 대기 1 × 5/31 = 125/31.
    """
    result = _new(_unit("N1", date(2027, 5, 20)), _unit("N2", JUNE_FIRST))

    assert _assignments(result) == [("N1", 202706, 1.0, 5), ("N2", 202706, 1.0, 0)]
    may = result.month(202705)
    assert may.downtime == pytest.approx(120 / 31)
    assert may.waiting == pytest.approx(5 / 31)
    assert [share.unit for share in may.waiting_shares] == ["N1"]
    june = result.month(202706)
    assert (june.new_increment, june.increment) == (2, 4)
    assert result.month(202705).existing_rate == pytest.approx((48 - 125 / 31) / 42)
    _assert_conserved(result)


def test_units_are_taken_in_arrival_order() -> None:
    """6/1 · 6/10 · 6/20 세 대와 7월 증가 2 — 호기마다 들어온 날 D 일 안의 가장 이른 미충족 증가에
    붙이므로 앞의 둘(대기 23 · 14일)이 붙고, 6/20 은 8월 증가(7/25, 35일 뒤)에 닿지 않아 일반
    설비다.

    6월 대기 = (23 + 14) ÷ 30, 7월 개조 없음 → 6월 비가동 0 → 6월 기존 (48 − 37/30 − 6) ÷ 38.
    """
    result = _new(
        _unit("N1", date(2027, 6, 1)),
        _unit("N2", date(2027, 6, 10)),
        _unit("N3", date(2027, 6, 20)),
    )

    assert _assignments(result) == [("N1", 202707, 1.0, 23), ("N2", 202707, 1.0, 14)]
    assert _windows(result) == [(202706, 6), (202708, 1), (202709, 1), (202711, 1)]
    june = result.month(202706)
    assert june.downtime == 0.0
    assert june.waiting == pytest.approx(37 / 30)
    assert june.existing_rate == pytest.approx((48 - 37 / 30 - 6) / 38)
    assert [unit.name for unit in result.ordinary_units] == ["N3"]
    _assert_conserved(result)


def test_new_then_owned_then_modification() -> None:
    """보유 4 + 신규 5/20(6월) · 6/24(7월 W/D 첫날).

    6월 증가 6 = 신규 1(5/20 — 대기 5일) + 보유 4 + 개조 1 → 5월 = 30/31 + 대기 5/31. 7월 증가 2 =
    신규 1(대기 0) + 개조 1(보유는 6월에 다 씀) → 6월 비가동 1. 개조 창 (06 1) (07 1) (08 1) (09 1)
    (11 1). 이 보기는 보유가 6월에 다 쓰여 차례(신규 먼저 · 보유 먼저)를 바꿔도 수가 같다 — 차례가
    수를 바꾸는 보기는 `test_the_fill_order_is_one_constant`.
    """
    result = _new(_unit("N1", date(2027, 5, 20)), _unit("N2", JULY_FIRST), owned=4)

    june, july = result.month(202706), result.month(202707)
    assert (june.owned_increment, june.new_increment, june.increment) == (4, 1, 1)
    assert (july.owned_increment, july.new_increment, july.increment) == (0, 1, 1)
    assert _windows(result) == [(202706, 1), (202707, 1), (202708, 1), (202709, 1), (202711, 1)]
    assert result.month(202705).existing_rate == pytest.approx((48 - 35 / 31) / 42)
    assert june.existing_rate == pytest.approx((48 - 1 - 6) / 38)
    kpis = result.kpis
    assert (kpis.owned_used, kpis.new_used, kpis.modified_units, kpis.max_dedicated) == (
        4,
        2,
        5,
        11,
    )
    assert result.month(202712).dedicated == 4 + 2 + 5
    _assert_conserved(result)


@pytest.mark.parametrize(
    ("days", "order", "expected"),
    [
        # 지금 차례(신규 → 보유 — 2026-10-26 오후 사용자 답) — 신규는 들어온 날 붙어 대기 0, 7월은
        # 보유.
        (30, (FILL_NEW, FILL_OWNED), ((0, 2, 0), (2, 0, 0), 0.0)),
        # 옛 차례(보유 → 신규) — 6월 증가 2 는 보유, 두 신규는 7월 증가(30일 뒤)에 붙어 30일 대기.
        (30, (FILL_OWNED, FILL_NEW), ((2, 0, 0), (0, 2, 0), 2.0)),
        # 개조 15일 — 옛 차례면 두 신규가 7월 증가(30일 뒤)에 닿지 않아 일반 설비, 7월은 개조 2.
        (15, (FILL_NEW, FILL_OWNED), ((0, 2, 0), (2, 0, 0), 0.0)),
        (15, (FILL_OWNED, FILL_NEW), ((2, 0, 0), (0, 0, 2), 0.0)),
    ],
)
def test_the_fill_order_is_one_constant(
    monkeypatch: pytest.MonkeyPatch,
    days: int,
    order: tuple[FillSource, ...],
    expected: tuple[tuple[int, int, int], tuple[int, int, int], float],
) -> None:
    """채우는 차례는 `FILL_ORDER` 하나다(신규 → 보유 — 2026-10-26 오후 사용자 답, 그 전은 보유 →
    신규). 보유 2 · 5/25 신규 두 대 · 필요 6월 2 → 7월 4(합성) — 차례가 개조·대기를 바꾼다. 6월
    대기는 그 6월 W/D(30일)에 든다."""
    assert constraint_simulation.FILL_ORDER == (FILL_NEW, FILL_OWNED)
    monkeypatch.setattr(constraint_simulation, "FILL_ORDER", order)
    result = simulate_constraint(
        [
            _one(202706, required=20, available=30, demand=2),
            _one(202707, required=20, available=30, demand=4),
        ],
        ConstraintConditions(202706, 202707, 1.0, days, 7, owned_units=2, new_unit_since=SINCE),
        (_unit("N1", JUNE_FIRST), _unit("N2", JUNE_FIRST)),
    )
    june, july = result.month(202706), result.month(202707)
    first, second, waiting = expected
    assert (june.owned_increment, june.new_increment, june.increment) == first
    assert (july.owned_increment, july.new_increment, july.increment) == second
    assert june.waiting == pytest.approx(waiting)


def test_new_units_go_before_owned_units() -> None:
    """상수 그대로(교체 없이) — 그날 붙일 수 있는 신규를 먼저 쓰고 보유를 뒤 증가에 남긴다.

    위 합성 보기(개조 30일): 6월 증가 2 = 신규 2(5/25 = 6월 W/D 첫날, 대기 0), 7월 증가 2 = 보유 2 —
    개조 0 · 대기 0. 옛 차례(보유 먼저)는 같은 보기에서 신규 두 대가 30일 기다렸다.
    """
    result = simulate_constraint(
        [
            _one(202706, required=20, available=30, demand=2),
            _one(202707, required=20, available=30, demand=4),
        ],
        ConstraintConditions(202706, 202707, 1.0, 30, 7, owned_units=2, new_unit_since=SINCE),
        (_unit("N1", JUNE_FIRST), _unit("N2", JUNE_FIRST)),
    )
    june, july = result.month(202706), result.month(202707)
    assert (june.new_increment, june.owned_increment, june.increment) == (2, 0, 0)
    assert (july.new_increment, july.owned_increment, july.increment) == (0, 2, 0)
    assert _assignments(result) == [("N1", 202706, 1.0, 0), ("N2", 202706, 1.0, 0)]
    assert result.windows == ()
    assert all(row.waiting == 0.0 for row in result.months)
    _assert_conserved(result)


def test_new_first_waits_even_when_the_owned_units_would_cover_the_period() -> None:
    """신규 먼저의 대가 — 보유만으로 기간을 다 덮어도 그날 붙일 수 있는 신규를 먼저 붙여 대기가
    선다(합성: 보유 2 · 5/20 신규 한 대 · 필요 6월 2 그대로, 개조 30일).

    6월 증가 2 = 신규 1(5/20 → 5/25, 대기 5일) + 보유 1. 5월 W/D(4/24~5/24, 31일)에 대기 1 × 5/31 이
    빠진다. 보유 먼저였다면 보유 2 로 덮고 그 신규는 일반 설비라 대기가 없다. 개조는 둘 다 0 이다.
    """
    months = [
        _one(202705, required=20, available=30),
        _one(202706, required=20, available=30, demand=2),
        _one(202707, required=20, available=30, demand=2),
    ]
    conditions = ConstraintConditions(
        202706, 202707, 1.0, 30, 7, owned_units=2, new_unit_since=SINCE
    )
    result = simulate_constraint(months, conditions, (_unit("N1", date(2027, 5, 20)),))
    june = result.month(202706)
    assert (june.new_increment, june.owned_increment, june.increment) == (1, 1, 0)
    assert _assignments(result) == [("N1", 202706, 1.0, 5)]
    assert result.month(202705).waiting == pytest.approx(5 / 31)
    assert result.kpis.modified_units == 0
    assert result.kpis.owned_used == 1
    _assert_conserved(result)


def test_a_unit_leaving_before_the_growth_is_not_dedicated() -> None:
    """5/20 에 들어와 5/25(6월 W/D 첫날)에 정지되는 신규는 그날 이후 증가에 붙지 않는다."""
    result = _new(_unit("N1", date(2027, 5, 20), until=JUNE_FIRST))
    assert result.assignments == ()
    assert _windows(result) == _windows(_run())


def test_fractional_units_are_split_like_modifications() -> None:
    """환산 대수는 개조처럼 나눠 붙인다 — 0.5 두 대는 6월 1대, 1.5 한 대는 6월 1대 + 남는 0.5(7월
    증가에는 내림 0 이라 못 붙어 일반 설비)."""
    halves = _new(_unit("A", JUNE_FIRST, units=0.5), _unit("B", JUNE_FIRST, units=0.5))
    assert _assignments(halves) == [("A", 202706, 0.5, 0), ("B", 202706, 0.5, 0)]
    assert halves.month(202706).new_increment == 1
    assert halves.ordinary_units == ()

    big = _new(_unit("C", JUNE_FIRST, units=1.5))
    assert _assignments(big) == [("C", 202706, 1.0, 0)]
    assert big.month(202707).new_increment == 0
    # C 는 일부만 붙었다 — 일반 설비 목록에 들지만 기존 제품 몫이 된 것은 남는 0.5대뿐이다.
    assert [unit.name for unit in big.ordinary_units] == ["C"]
    assert big.assigned_units(big.new_units[0]) == pytest.approx(1.0)
    assert big.left_units(big.new_units[0]) == 0.5
    assert halves.left_units(halves.new_units[0]) == 0.0


def test_a_wait_before_the_first_shown_month_is_flagged() -> None:
    """표가 6월부터면 5/10 신규의 대기(5월)는 표에 없다 — `waits_before_range` 로 알린다."""
    result = simulate_constraint(
        _inputs()[MONTHS.index(202706) :], NEW_ON, (_unit("N1", date(2027, 5, 10)),)
    )
    assert result.waits_before_range
    assert result.month(202706).waiting == 0.0
    assert not _new(_unit("N1", date(2027, 5, 10))).waits_before_range


def test_new_units_after_the_period_change_nothing() -> None:
    """기간 끝 뒤(2028)에 들어온 신규는 붙일 증가가 없어 일반 설비다."""
    result = _new(_unit("N1", date(2028, 1, 10)), _unit("N2", date(2028, 2, 10)))
    assert result.assignments == ()
    assert [row.existing_rate for row in result.months] == [
        row.existing_rate for row in _run().months
    ]
    assert len(result.ordinary_units) == 2


def test_units_starting_in_a_month_follow_the_wd_window() -> None:
    """화면 「들어오는 신규」 는 기여 시작이 그 달 W/D 구간에 드는 호기다 — 6/23 은 6월, 6/24 는
    7월."""
    result = _new(_unit("N1", date(2027, 6, 23)), _unit("N2", JULY_FIRST))
    assert [unit.name for unit in result.units_starting_in(202706)] == ["N1"]
    assert [unit.name for unit in result.units_starting_in(202707)] == ["N2"]


# ------------------------------------------------------------------ 검증


@pytest.mark.parametrize("owned", [-1, 1000, True, 1.5])
def test_invalid_owned_units_are_rejected(owned: object) -> None:
    with pytest.raises(ValueError, match="보유 제약 설비"):
        simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=cast(int, owned)))


def test_a_reference_day_must_be_a_date() -> None:
    with pytest.raises(ValueError, match="기준일"):
        simulate_constraint(_inputs(), replace(CONDITIONS, new_unit_since=cast(date, "2026-10-26")))


@pytest.mark.parametrize(
    "unit",
    [
        NewUnit(name="N1", start=JUNE_FIRST, units=0.0),
        NewUnit(name="N1", start=JUNE_FIRST, units=float("nan")),
        NewUnit(name="N1", start=JUNE_FIRST, units=-1.0),
        NewUnit(name="", start=JUNE_FIRST, units=1.0),
        NewUnit(name="N1", start=cast(date, "2027-05-25"), units=1.0),
        NewUnit(name="N1", start=JUNE_FIRST, units=1.0, until=cast(date, "2027-07-01")),
    ],
)
def test_invalid_new_units_are_rejected(unit: NewUnit) -> None:
    with pytest.raises(ValueError, match="신규 설비"):
        simulate_constraint(_inputs(), NEW_ON, (unit,))


def test_duplicate_new_unit_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="겹칩니다"):
        _new(_unit("N1", JUNE_FIRST), _unit("N1", JULY_FIRST))


def test_the_harness_constants_are_unchanged() -> None:
    """이 파일의 손계산은 1판 하네스 값에 기댄다 — 하네스가 바뀌면 여기도 다시 센다."""
    assert REQUIRED[MONTHS.index(202705)] == 42 and AVAILABLE[MONTHS.index(202705)] == 48
    assert PRODUCT[MONTHS.index(202706) : MONTHS.index(202712) + 1] == (5, 6, 7, 8, 8, 9, 9)
