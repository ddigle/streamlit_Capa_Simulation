# Purpose: 제약 시뮬레이션의 보유 제약 설비·「신규 설비는 개조 없이」 옵션이 채우는 차례와 확보율을
# 손계산과 맞댄다.

"""제약 시뮬레이션 2판 옵션(`services/constraint_simulation.py` — 2026-10-26 사용자 결정).

**기대값은 손계산이다.** 하네스는 `tests/test_constraint_simulation.py` 의 합성 TC Bonding 예시
그대로다 (업무 사실이 아니다) — 기간 202706~202712, 제약 120%, 개조 30일, Cut-off 7. 그 하네스의
늘어난 전용 대수(growth)는 06 6 · 07 2 · 08 1 · 09 1 · 10 0 · 11 1 · 12 0 이고 1판 개조 창은 (06
6대) (07 2대) (08 1대) (09 1대) (11 1대)다. 30일 개조 창은 앞 달 W/D 한 칸에 다 들어 06 몫 n대는
5월에 n × 30/31, 07 몫은 6월에 n × 30/30, 08·09·11 몫은 7·8·10월에 n × 30/31 이다.

채우는 차례는 ① 보유(아직 쓰지 않은 만큼) → ② 그 달 새로 붙은 신규 → ③ 개조이고 ③ 만 창을 낸다.
신규는 **들어오는 그 달에만** 붙인다 — 기간 전에 들어온 신규와 그 달 증가분보다 많은 신규는 기존
제품 몫이 되어 다음 달로 넘어가지 않는다(사용자 답 1-2·1-3).
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date
from itertools import accumulate
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
    _plan_rows,
    _product_table,
    _run,
)

from capa_simulation.services.constraint_simulation import (
    ConstraintConditions,
    ConstraintMonthInput,
    ConstraintResult,
    constraint_month_inputs,
    new_unit_arrivals,
    simulate_constraint,
)

SINCE = date(2026, 10, 26)


def _with_arrivals(arrivals: dict[int, int]) -> tuple[ConstraintMonthInput, ...]:
    """하네스 입력에 달마다 새로 붙는 신규 대수를 싣는다 — 신규 몫은 그 누적(검증을 지나게)."""
    counts = [arrivals.get(month, 0) for month in MONTHS]
    shares = list(accumulate(counts))
    return tuple(
        replace(row, new_available=float(share), new_arrivals=count)
        for row, share, count in zip(_inputs(), shares, counts, strict=True)
    )


def _windows(result: ConstraintResult) -> list[tuple[int, int]]:
    return [(window.month, window.units) for window in result.windows]


def _assert_conserved(result: ConstraintResult) -> None:
    """개조 켬이면 달마다 구성 합 = 전용, 늘어난 대수 = pool − 앞 달 pool, 창 대수 합 = 개조 대수.
    """
    previous_pool, previous_inside = 0, False
    for row in result.months:
        carried = previous_pool if row.in_period and previous_inside else 0
        if row.in_period:
            assert row.owned_dedicated + row.new_dedicated + row.modified_dedicated == row.dedicated
            assert row.growth == row.dedicated - carried
        else:
            assert (row.owned_dedicated, row.new_dedicated, row.modified_dedicated) == (0, 0, 0)
            assert row.growth == 0
        assert row.new_increment <= row.new_arrivals
        previous_pool, previous_inside = row.dedicated, row.in_period
    assert sum(window.units for window in result.windows) == result.kpis.modified_units


# ------------------------------------------------------------------ 기본값은 1판 그대로


def test_the_defaults_leave_every_value_of_the_first_version() -> None:
    """보유 0 · 신규 끔이면 결과가 1판과 같다 — 달마다 신규 대수가 실려 와도 끈 옵션은 보지 않는다.
    """
    plain = _run()
    carried = simulate_constraint(_with_arrivals({202706: 4, 202707: 2}), CONDITIONS)
    assert carried == plain
    assert plain.kpis.modified_units == plain.kpis.max_dedicated == 11
    assert (plain.kpis.owned_used, plain.kpis.new_used) == (0, 0)
    assert not CONDITIONS.splits_dedicated
    _assert_conserved(plain)


def test_modification_off_locks_both_options() -> None:
    """개조 끔은 설비가 서로 바뀐다는 뜻이라 개조가 없다 — 보유·신규가 걸리지 않고 결과가 같다."""
    off = replace(CONDITIONS, modification_days=None)
    locked = replace(off, owned_units=5, new_unit_since=SINCE)
    plain = simulate_constraint(_inputs(), off)
    result = simulate_constraint(_with_arrivals({202706: 4}), locked)

    assert not locked.uses_owned_units and not locked.uses_new_units
    assert not locked.splits_dedicated
    assert [row.existing_rate for row in result.months] == [
        row.existing_rate for row in plain.months
    ]
    assert result.kpis.modified_units is None and result.kpis.max_dedicated is None
    for row in result.months:
        assert (row.owned_increment, row.new_increment, row.new_arrivals) == (0, 0, 0)
        assert row.new_available == 0.0


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
    """보유 7 — 6월 6대를 보유로 쓰고 남은 1대가 7월 증가 2대 중 1대를 덮는다(남는 동안은 기존 몫).
    """
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


# ------------------------------------------------------------------ ② 신규 설비는 개조 없이


def test_new_units_cover_only_their_own_month_and_leftovers_become_ordinary() -> None:
    """신규 05 3대 · 06 4대 · 07 1대 · 09 3대.

    - 05 3대는 기간 전에 들어와 기존 제품에 쓰인다 — 6월 몫을 덮지 못한다(사용자 답 1-3).
    - 06 증가 6 = 신규 4 + 개조 2 · 07 증가 2 = 신규 1 + 개조 1 · 08 증가 1 = 개조 1(신규 없음).
    - 09 증가 1 = 신규 1, 남는 2대는 기존 제품 몫 → 11월 증가 1 은 다시 개조(넘어가지 않는다).

    창 (06 2) (07 1) (08 1) (11 1). 비가동 5월 2 × 30/31 · 6월 1 × 30/30 · 7월 30/31 · 8월 0 · 10월
    30/31. 기존 5월 (48 − 60/31)/42 · 6월 (48 − 1 − 6)/38 · 7월 (50 − 30/31 − 8)/38 · 8월 41/38 ·
    9월 42/38 · 10월 (42 − 30/31)/38 · 11·12월 43/38.
    """
    conditions = replace(CONDITIONS, new_unit_since=SINCE)
    result = simulate_constraint(
        _with_arrivals({202705: 3, 202706: 4, 202707: 1, 202709: 3}), conditions
    )

    assert _windows(result) == [(202706, 2), (202707, 1), (202708, 1), (202711, 1)]
    split = {
        row.month: (row.new_arrivals, row.new_increment, row.increment, row.unused_arrivals)
        for row in result.months
        if row.new_arrivals or row.growth
    }
    assert split == {
        202705: (3, 0, 0, 3),
        202706: (4, 4, 2, 0),
        202707: (1, 1, 1, 0),
        202708: (0, 0, 1, 0),
        202709: (3, 1, 0, 2),
        202711: (0, 0, 1, 0),
    }
    expected = {
        202705: (48 - 60 / 31) / 42,
        202706: 41 / 38,
        202707: (42 - 30 / 31) / 38,
        202708: 41 / 38,
        202709: 42 / 38,
        202710: (42 - 30 / 31) / 38,
        202711: 43 / 38,
        202712: 43 / 38,
    }
    for month, rate in expected.items():
        assert result.month(month).existing_rate == pytest.approx(rate)
    assert result.month(202708).downtime == 0.0
    kpis = result.kpis
    assert (kpis.max_dedicated, kpis.owned_used, kpis.new_used, kpis.modified_units) == (
        11,
        0,
        6,
        5,
    )
    assert result.month(202712).new_dedicated == 6
    assert conditions.uses_new_units and conditions.splits_dedicated
    _assert_conserved(result)


def test_new_units_arriving_before_the_period_do_not_help_its_first_month() -> None:
    """기간 앞(03·05월)에만 들어온 신규는 일반 설비다 — 창·확보율이 1판과 같다."""
    result = simulate_constraint(
        _with_arrivals({202703: 5, 202705: 6}), replace(CONDITIONS, new_unit_since=SINCE)
    )
    plain = _run()

    assert _windows(result) == _windows(plain)
    assert [row.existing_rate for row in result.months] == [
        row.existing_rate for row in plain.months
    ]
    assert result.kpis.new_used == 0
    assert result.month(202705).unused_arrivals == 6


def test_owned_then_new_then_modification_without_any_window() -> None:
    """보유 3 + 신규 06 4대 · 07 2대 · 08 1대 · 09 1대 · 11 1대 — 06 증가 6 = 보유 3 + 신규 3(남는
    1대는 기존 몫), 07 신규 2, 08·09·11 신규 1. 개조가 없어 확보율은 개조 끔과 같다."""
    result = simulate_constraint(
        _with_arrivals({202706: 4, 202707: 2, 202708: 1, 202709: 1, 202711: 1}),
        replace(CONDITIONS, owned_units=3, new_unit_since=SINCE),
    )
    off = _run(replace(CONDITIONS, modification_days=None))

    assert result.windows == ()
    june = result.month(202706)
    assert (june.owned_increment, june.new_increment, june.increment) == (3, 3, 0)
    assert june.unused_arrivals == 1
    assert [row.existing_rate for row in result.months] == [row.existing_rate for row in off.months]
    kpis = result.kpis
    assert (kpis.owned_used, kpis.new_used, kpis.modified_units, kpis.window_count) == (3, 8, 0, 0)
    assert kpis.first_downtime_day is None
    _assert_conserved(result)


def test_new_units_do_not_cover_months_outside_the_period() -> None:
    """기간 끝 뒤(202801~)에 들어온 신규는 아무것도 바꾸지 않는다 — 기간 밖은 전용이 0 이다."""
    result = simulate_constraint(
        _with_arrivals({202801: 4, 202802: 2}), replace(CONDITIONS, new_unit_since=SINCE)
    )
    assert _windows(result) == _windows(_run())
    for month in (202801, 202802):
        row = result.month(month)
        assert (row.dedicated, row.new_increment, row.unused_arrivals) == (0, 0, row.new_arrivals)


def test_the_counters_restart_in_the_first_period_month_of_sparse_months() -> None:
    """띄엄 달(202706, 202708) + 보유 3 — 「앞 달」 은 보이는 차례라 보유 누적도 그 차례로 잇는다.

    06 증가 5 = 보유 3 + 개조 2, 08 증가 2 = 개조 2(보유를 다 썼다).
    """
    result = simulate_constraint(
        [
            _one(202706, required=20, available=30, demand=5),
            _one(202708, required=20, available=30, demand=7),
        ],
        ConstraintConditions(202706, 202708, 1.0, 30, 7, owned_units=3),
    )
    assert _windows(result) == [(202706, 2), (202708, 2)]
    later = result.month(202708)
    assert (later.owned_dedicated, later.modified_dedicated, later.dedicated) == (3, 4, 7)
    _assert_conserved(result)


# ------------------------------------------------------------------ 새로 붙는 대수(내림 차이)


@pytest.mark.parametrize(
    ("shares", "before", "expected"),
    [
        # 반 달씩 붙는 신규 — 0.5 는 다음 달 몫이고 둘이면 그 달 1대다.
        ((0.5, 1.0, 1.5, 2.0), 0.0, (0, 1, 0, 1)),
        ((1.0,), 0.0, (1,)),
        # 첫 달 앞에 이미 들어온 몫(1.0)은 첫 달 대수가 아니다.
        ((1.2, 2.7, 3.3), 1.0, (0, 1, 1)),
        # 내림 전 잡음 — 1 − 1e-12 는 1대다.
        ((1 - 1e-12,), 0.0, (1,)),
        # 정지·반출로 줄었다가 다시 느는 달은 다시 붙은 몫만 센다.
        ((3.0, 2.0, 3.0), 0.0, (3, 0, 1)),
        ((), 2.0, ()),
    ],
)
def test_new_unit_arrivals_floor_the_cumulative_share(
    shares: tuple[float, ...], before: float, expected: tuple[int, ...]
) -> None:
    assert new_unit_arrivals(shares, before=before) == expected


def test_half_month_arrivals_move_the_cover_to_the_next_month() -> None:
    """06 W/D 에 반 달만 붙은 신규 1대(0.5)는 6월 몫을 덮지 못하고 7월 증가 2대 중 1대를 덮는다."""
    shares = [0.0] * len(MONTHS)
    shares[MONTHS.index(202706)] = 0.5
    for month in MONTHS[MONTHS.index(202707) :]:
        shares[MONTHS.index(month)] = 1.0
    arrivals = new_unit_arrivals(shares)
    months = tuple(
        replace(row, new_available=share, new_arrivals=count)
        for row, share, count in zip(_inputs(), shares, arrivals, strict=True)
    )
    result = simulate_constraint(months, replace(CONDITIONS, new_unit_since=SINCE))

    assert result.month(202706).new_arrivals == 0
    assert (result.month(202707).new_increment, result.month(202707).increment) == (1, 1)
    assert _windows(result) == [(202706, 6), (202707, 1), (202708, 1), (202709, 1), (202711, 1)]


# ------------------------------------------------------------------ 어댑터


def test_the_adapter_turns_the_new_unit_share_into_arrivals() -> None:
    """A_new 06 1.5 · 07 3.2 · 첫 달 앞 1.0 → 06 0대(1 → 1) · 07 2대(1 → 3). 빠진 달은 0 이다."""
    inputs = constraint_month_inputs(
        _plan_rows(),
        _product_table(),
        process="TC Bonding",
        product="HBM라E",
        months=(202706, 202707),
        general_target=lambda _month: 1.1,
        new_units={202706: 1.5, 202707: 3.2},
        new_units_before=1.0,
    )
    assert [(row.new_available, row.new_arrivals) for row in inputs] == [(1.5, 0), (3.2, 2)]
    missing = constraint_month_inputs(
        _plan_rows(),
        _product_table(),
        process="TC Bonding",
        product="HBM라E",
        months=(202706, 202707),
        general_target=lambda _month: 1.1,
        new_units={202707: 2.0},
    )
    assert [(row.new_available, row.new_arrivals) for row in missing] == [(0.0, 0), (2.0, 2)]


@pytest.mark.parametrize(
    ("shares", "before"),
    [
        ({202706: math.nan}, 0.0),
        ({202706: -0.1}, 0.0),
        ({202706: 1.0}, -1.0),
        ({202706: math.inf}, 0.0),
    ],
)
def test_the_adapter_rejects_a_broken_new_unit_share(
    shares: dict[int, float], before: float
) -> None:
    with pytest.raises(ValueError, match="신규 설비 몫"):
        constraint_month_inputs(
            _plan_rows(),
            _product_table(),
            process="TC Bonding",
            product="HBM라E",
            months=(202706,),
            general_target=lambda _month: 1.1,
            new_units=shares,
            new_units_before=before,
        )


# ------------------------------------------------------------------ 검증


@pytest.mark.parametrize("owned", [-1, 1000, True, 1.5])
def test_invalid_owned_units_are_rejected(owned: object) -> None:
    with pytest.raises(ValueError, match="보유 제약 설비"):
        simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=cast(int, owned)))


def test_a_reference_day_must_be_a_date() -> None:
    with pytest.raises(ValueError, match="기준일"):
        simulate_constraint(_inputs(), replace(CONDITIONS, new_unit_since=cast(date, "2026-10-26")))


@pytest.mark.parametrize(
    ("share", "arrivals"),
    [(math.nan, 0), (-0.1, 0), (2.5, 3), (1.0, -1), (1.0, True), (1.0, 1.0)],
)
def test_invalid_new_unit_months_are_rejected(share: float, arrivals: object) -> None:
    month = replace(
        _one(202706, required=20, available=30, demand=5),
        new_available=share,
        new_arrivals=cast(int, arrivals),
    )
    with pytest.raises(ValueError, match="신규"):
        simulate_constraint([month], replace(CONDITIONS, new_unit_since=SINCE))


def test_arrivals_within_the_rounding_noise_are_accepted() -> None:
    month = replace(
        _one(202706, required=20, available=30, demand=5), new_available=3 - 1e-12, new_arrivals=3
    )
    result = simulate_constraint(
        [month], ConstraintConditions(202706, 202706, 1.0, 30, 7, new_unit_since=SINCE)
    )
    assert (result.month(202706).new_increment, result.month(202706).increment) == (3, 2)


def test_the_harness_constants_are_unchanged() -> None:
    """이 파일의 손계산은 1판 하네스 값에 기댄다 — 하네스가 바뀌면 여기도 다시 센다."""
    assert REQUIRED[MONTHS.index(202705)] == 42 and AVAILABLE[MONTHS.index(202705)] == 48
    assert PRODUCT[MONTHS.index(202706) : MONTHS.index(202712) + 1] == (5, 6, 7, 8, 8, 9, 9)
