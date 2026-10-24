# Purpose: 제약 시뮬레이션 계산의 일곱 가정·개조 비가동·우선 배정·비중 견주기를 손계산과 맞댄다.

"""제약 시뮬레이션 계산(`services/constraint_simulation.py`).

**기대값은 손계산이다.** 공통 하네스는 승인 초안(2판)의 합성 예시 `DATA['TC Bonding']` 이고 업무
사실이 아니다 — 달 202701~202803(15), 제약 제품(합성 「HBM라E」) 소요 0,…,5,6,7,8,8,9,9,10,10,11,
Cut-off 7, 기간 202706~202712, 제약 120%, 기준 110%, 개조 켬 30일. 표의 수는 명세(2-8)의 손계산과,
저장소 `wd_window`·`overlap_days` 로 같은 식을 따로 짠 검토 계산이 같게 낸 값이다. 확보율 단언은
비율 `pytest.approx(abs=1e-4)` 다(표가 소수 둘째 자리 % 라 반올림 차이가 5e-5 안이다).
"""

from __future__ import annotations

import ast
import math
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.services.constraint_simulation import (
    IMPACT_TOLERANCE,
    ConstraintConditions,
    ConstraintMonthInput,
    ConstraintResult,
    DowntimeShare,
    constraint_month_inputs,
    modification_window,
    required_units,
    secure,
    simulate_constraint,
)
from capa_simulation.services.process_capa_detail import (
    OTHER_ROW_COLUMN,
    build_process_product_demand,
)
from capa_simulation.services.required_shortening import PROCESS_MONTH_COLUMNS
from capa_simulation.services.securement_threshold import capacity_status
from capa_simulation.services.wd_window import wd_window

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "capa_simulation"
    / "services"
    / "constraint_simulation.py"
)

MONTHS = (*range(202701, 202713), 202801, 202802, 202803)
REQUIRED = (38, 39, 40, 41, 42, 43, 44, 45, 46, 46, 47, 47, 48, 48, 49)
AVAILABLE = (44, 44, 46, 46, 48, 48, 50, 50, 52, 52, 54, 54, 54, 56, 56)
PRODUCT = (0, 0, 0, 0, 0, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11)
CONDITIONS = ConstraintConditions(
    period_start=202706,
    period_end=202712,
    constraint_target=1.2,
    modification_days=30,
    cutoff_days=7,
)


def _inputs(
    *,
    general: float = 1.1,
    general_by_month: dict[int, float] | None = None,
    product: tuple[float, ...] = PRODUCT,
) -> tuple[ConstraintMonthInput, ...]:
    by_month = general_by_month or {}
    return tuple(
        ConstraintMonthInput(
            month=month,
            required=float(required),
            constrained_demand=float(demand),
            available=float(available),
            general_target=by_month.get(month, general),
        )
        for month, required, available, demand in zip(
            MONTHS, REQUIRED, AVAILABLE, product, strict=True
        )
    )


def _run(
    conditions: ConstraintConditions = CONDITIONS,
    *,
    general: float = 1.1,
    general_by_month: dict[int, float] | None = None,
    product: tuple[float, ...] = PRODUCT,
) -> ConstraintResult:
    months = _inputs(general=general, general_by_month=general_by_month, product=product)
    return simulate_constraint(months, conditions)


def _one(
    month: int,
    *,
    required: float,
    available: float,
    demand: float = 0.0,
    general: float = 1.1,
) -> ConstraintMonthInput:
    return ConstraintMonthInput(month, required, demand, available, general)


# ------------------------------------------------------------------ ① TC Bonding 기본 예


# 월: (R, A, Rc', Re, need, pool, inc, 비가동, 배정, 기존 가용,
#      기존 %, 제약 %, 제약 없을 때 %, 비중 제약, 비중 기존 %)
EXPECTED_ROWS = {
    202704: (41, 46, 0, 41, 0, 0, 0, 0.0, 0, 46.0, 112.20, None, 112.20, 0, 112.20),
    202705: (42, 48, 0, 42, 0, 0, 0, 180 / 31, 0, 48 - 180 / 31, 100.46, None, 114.29, 0, 114.29),
    202706: (43, 48, 5, 38, 6, 6, 6, 2.0, 6, 40.0, 105.26, 120.00, 111.63, 6, 110.53),
    202707: (44, 50, 6, 38, 8, 8, 2, 30 / 31, 8, 42 - 30 / 31, 107.98, 133.33, 113.64, 7, 113.16),
    202708: (45, 50, 7, 38, 9, 9, 1, 30 / 31, 9, 41 - 30 / 31, 105.35, 128.57, 111.11, 8, 110.53),
    202709: (46, 52, 8, 38, 10, 10, 1, 0.0, 10, 42.0, 110.53, 125.00, 113.04, 9, 113.16),
    202710: (
        46,
        52,
        8,
        38,
        10,
        10,
        0,
        30 / 31,
        10,
        42 - 30 / 31,
        107.98,
        125.00,
        113.04,
        9,
        113.16,
    ),
    202711: (47, 54, 9, 38, 11, 11, 1, 0.0, 11, 43.0, 113.16, 122.22, 114.89, 10, 115.79),
    202712: (47, 54, 9, 38, 11, 11, 0, 0.0, 11, 43.0, 113.16, 122.22, 114.89, 10, 115.79),
    202801: (48, 54, 0, 48, 0, 0, 0, 0.0, 0, 54.0, 112.50, None, 112.50, 0, 112.50),
}


def _pct(value: float | None) -> object:
    return None if value is None else pytest.approx(value / 100, abs=1e-4)


@pytest.mark.parametrize("month", sorted(EXPECTED_ROWS))
def test_the_tc_bonding_example_matches_the_hand_calculation(month: int) -> None:
    (
        required,
        available,
        constrained,
        existing,
        need,
        pool,
        increment,
        downtime,
        allocated,
        existing_available,
        existing_pct,
        constrained_pct,
        baseline_pct,
        proportional,
        proportional_pct,
    ) = EXPECTED_ROWS[month]
    row = _run().month(month)

    assert (row.required, row.available) == (required, available)
    assert (row.constrained_demand, row.existing_demand) == (constrained, existing)
    assert (row.need, row.dedicated, row.increment, row.allocated) == (
        need,
        pool,
        increment,
        allocated,
    )
    assert row.downtime == pytest.approx(downtime, abs=1e-9)
    assert row.existing_available == pytest.approx(existing_available, abs=1e-9)
    assert row.existing_rate == _pct(existing_pct)
    assert row.constrained_rate == _pct(constrained_pct)
    assert row.baseline_rate == _pct(baseline_pct)
    assert row.proportional_constrained == proportional
    # 비중 기존 % 는 기간 밖이면 그리지 않는다 — 값은 제약 없을 때와 같다.
    assert row.proportional_existing_rate == _pct(proportional_pct)
    assert not row.short and not row.overdrawn


def test_the_tc_bonding_example_has_five_windows_in_the_month_before() -> None:
    """30일 개조는 앞 달 W/D 한 칸에 다 든다 — 「제약은 6월부터지만 5월부터 확보율이 준다」."""
    result = _run()

    assert [
        (window.month, window.units, window.start, window.last_day) for window in result.windows
    ] == [
        (202706, 6, date(2027, 4, 25), date(2027, 5, 24)),
        (202707, 2, date(2027, 5, 25), date(2027, 6, 23)),
        (202708, 1, date(2027, 6, 25), date(2027, 7, 24)),
        (202709, 1, date(2027, 7, 26), date(2027, 8, 24)),
        (202711, 1, date(2027, 9, 25), date(2027, 10, 24)),
    ]
    shares = {row.month: row.downtime_shares for row in result.months if row.downtime_shares}
    assert shares == {
        202705: (DowntimeShare(202706, 6, 30, 31),),
        202706: (DowntimeShare(202707, 2, 30, 30),),
        202707: (DowntimeShare(202708, 1, 30, 31),),
        202708: (DowntimeShare(202709, 1, 30, 31),),
        202710: (DowntimeShare(202711, 1, 30, 31),),
    }
    # 개조 창 끝은 그 달 W/D 첫날이다.
    for window in result.windows:
        assert window.end == wd_window(window.month, 7).first_day
    assert result.starts_before_range is False
    assert result.short_months == () and result.overdrawn_months == ()


def test_the_tc_bonding_kpis() -> None:
    kpis = _run().kpis

    assert (kpis.constrained_met_months, kpis.constrained_months) == (7, 7)
    assert kpis.lowest_existing_month == 202705
    assert kpis.lowest_existing_rate == pytest.approx((48 - 180 / 31) / 42)
    assert kpis.lowest_existing_rate == _pct(100.46)
    assert kpis.lowest_baseline_rate == _pct(114.29)
    assert kpis.below_months == (202705, 202706, 202707, 202708, 202710)
    assert kpis.newly_below_months == kpis.below_months
    assert kpis.first_impact_month == 202705
    assert kpis.max_dedicated == 11
    assert kpis.window_count == 5
    assert kpis.first_downtime_day == date(2027, 4, 25)


def test_the_month_before_the_first_downtime_is_untouched() -> None:
    """202704 는 영향이 없다 — 기존 = 제약 없을 때(초안의 달력 월 일할이면 4월이 1.2대 줄었다)."""
    row = _run().month(202704)

    assert row.downtime == 0.0
    assert row.existing_rate == row.baseline_rate


def test_the_home_default_threshold_keeps_the_same_five_months() -> None:
    """HOME 관례값 109.5% 로 돌려도 미달 다섯 달은 같다."""
    assert _run(general=1.095).kpis.below_months == (202705, 202706, 202707, 202708, 202710)


# ------------------------------------------------------------------ ② 합 보존


def test_demand_and_availability_are_conserved_every_month() -> None:
    for row in _run().months:
        assert row.constrained_demand + row.existing_demand == row.required
        assert row.existing_available + row.allocated + row.downtime == pytest.approx(
            row.available, abs=1e-9
        )
        assert row.proportional_constrained + row.proportional_existing == row.available


# ------------------------------------------------------------------ ③ 올림 잡음


@pytest.mark.parametrize(
    ("demand", "target", "expected"),
    [(10, 1.1, 11), (5, 1.2, 6), (4.3, 1.2, 6), (0, 1.2, 0), (-1, 1.2, 0), (7, 1.0, 7)],
)
def test_required_units_rounds_up_after_removing_float_noise(
    demand: float, target: float, expected: int
) -> None:
    assert required_units(demand, target) == expected


# ------------------------------------------------------------------ ④ 개조 끔


def test_without_modification_only_the_month_need_is_set_aside() -> None:
    result = _run(replace(CONDITIONS, modification_days=None))

    assert result.windows == ()
    assert all(row.downtime == 0.0 and row.increment == 0 for row in result.months)
    for row in result.months:
        assert row.dedicated == row.need
    assert result.month(202708).existing_available == 41.0
    assert result.month(202708).existing_rate == _pct(107.89)
    assert result.month(202706).existing_rate == _pct(110.53)
    assert result.month(202705).existing_rate == result.month(202705).baseline_rate
    assert result.kpis.max_dedicated is None
    assert result.kpis.window_count == 0 and result.kpis.first_downtime_day is None


# ------------------------------------------------------------------ ⑤ 누적 최대


def test_dedicated_units_never_shrink_inside_the_period() -> None:
    """Rc' 가 8 → 7 로 줄어도 개조한 10대는 전용으로 남고 그 달 새 개조는 없다."""
    product = list(PRODUCT)
    product[MONTHS.index(202710)] = 7
    result = _run(product=tuple(product))
    row = result.month(202710)

    assert row.need == 9
    assert (row.dedicated, row.increment, row.allocated) == (10, 0, 10)
    assert row.constrained_rate == pytest.approx(10 / 7)
    assert 202710 not in {window.month for window in result.windows}


# ------------------------------------------------------------------ ⑥ 기간 끝 복귀


def test_the_month_after_the_period_returns_everything_to_existing_products() -> None:
    result = _run()
    row = result.month(202801)

    assert row.in_period is False
    assert (row.constrained_demand, row.product_demand) == (0.0, 10.0)
    assert (row.dedicated, row.allocated, row.downtime) == (0, 0, 0.0)
    assert row.existing_available == 54.0
    assert row.existing_rate == pytest.approx(54 / 48) == row.baseline_rate
    assert row.constrained_rate is None and row.met is None
    assert all(window.month <= 202712 for window in result.windows)


# ------------------------------------------------------------------ ⑦ Cut-off 0 · 45일


def test_a_long_modification_spreads_over_calendar_months_without_cutoff() -> None:
    result = _run(replace(CONDITIONS, modification_days=45, cutoff_days=0))

    first = result.windows[0]
    assert (first.month, first.start, first.end) == (202706, date(2027, 4, 17), date(2027, 6, 1))
    downtime = {row.month: row.downtime for row in result.months if row.downtime}
    assert downtime == {
        202704: pytest.approx(6 * 14 / 30),
        202705: pytest.approx(6 + 2 * 15 / 31),
        202706: pytest.approx(2 * 30 / 30 + 1 * 14 / 30),
        202707: pytest.approx(1.4516, abs=1e-4),
        202708: pytest.approx(1.0),
        202709: pytest.approx(0.4667, abs=1e-4),
        202710: pytest.approx(1.0),
    }


# ------------------------------------------------------------------ ⑧ 첫 달 앞 시작


def test_a_window_before_the_first_visible_month_is_flagged_and_dropped() -> None:
    months = [
        _one(month, required=10, available=12, demand=2) for month in (202701, 202702, 202703)
    ]
    conditions = ConstraintConditions(202701, 202703, 1.0, 30, 7)
    result = simulate_constraint(months, conditions)

    assert [(window.month, window.start, window.end) for window in result.windows] == [
        (202701, date(2026, 11, 25), date(2026, 12, 25))
    ]
    assert result.starts_before_range is True
    first = result.month(202701)
    assert first.downtime == 0.0
    assert first.allocated == 2
    assert first.existing_rate == pytest.approx(10 / 8)


# ------------------------------------------------------------------ ⑨ 가용 부족


def test_short_availability_fills_the_constraint_first() -> None:
    result = simulate_constraint(
        [_one(202706, required=10, available=7.6, demand=6)],
        ConstraintConditions(202706, 202706, 1.2, None, 7),
    )
    row = result.month(202706)

    assert (row.need, row.dedicated, row.allocated) == (8, 8, 7)
    assert row.short is True
    assert result.short_months == (202706,)
    assert row.existing_available == pytest.approx(0.6)
    assert row.existing_rate == pytest.approx(0.15)
    assert row.constrained_rate == pytest.approx(7 / 6)
    assert row.met is False
    assert (result.kpis.constrained_met_months, result.kpis.constrained_months) == (0, 1)


# ------------------------------------------------------------------ ⑩ 과개조


@pytest.mark.parametrize("period_start", [202706, 202705])
def test_downtime_beyond_availability_clamps_to_zero_and_warns(period_start: int) -> None:
    result = simulate_constraint(
        [
            _one(202705, required=4, available=5, demand=0),
            _one(202706, required=8, available=5, demand=6),
        ],
        ConstraintConditions(period_start, 202706, 1.0, 30, 7),
    )
    before, during = result.month(202705), result.month(202706)

    assert before.downtime == pytest.approx(6 * 30 / 31)
    assert before.usable == 0.0 and before.overdrawn is True
    assert result.overdrawn_months == (202705,)
    assert before.existing_rate == 0.0
    assert during.downtime == 0.0
    assert during.allocated == 5 and during.short is True
    assert result.short_months == (202706,)
    assert during.constrained_rate == pytest.approx(5 / 6)
    assert during.met is False
    assert during.existing_rate == 0.0


# ------------------------------------------------------------------ ⑪ 소요 0


def test_a_month_without_demand_has_no_rates() -> None:
    result = simulate_constraint(
        [_one(202706, required=0, available=5)], ConstraintConditions(202706, 202706, 1.2, 30, 7)
    )
    row = result.month(202706)

    assert (row.baseline_rate, row.existing_rate, row.constrained_rate) == (None, None, None)
    assert (row.existing_secure, row.baseline_secure, row.met) == (None, None, None)
    assert result.kpis.below_months == ()
    assert result.kpis.lowest_existing_month is None
    assert result.kpis.constrained_months == 0


# ------------------------------------------------------------------ ⑫ 기간이 보이는 달 밖


def test_a_period_outside_the_visible_months_changes_nothing() -> None:
    result = _run(replace(CONDITIONS, period_start=202901, period_end=202903))

    assert result.windows == ()
    assert result.kpis.constrained_months == 0
    assert result.kpis.max_dedicated == 0
    for row in result.months:
        assert row.in_period is False
        assert row.existing_rate == row.baseline_rate
        assert row.proportional_existing_rate == row.baseline_rate


# ------------------------------------------------------------------ ⑬ 달마다 다른 기준


def test_each_month_is_judged_against_its_own_threshold() -> None:
    result = _run(general_by_month={202706: 1.05})

    assert result.month(202706).existing_secure is True
    assert result.kpis.below_months == (202705, 202707, 202708, 202710)


def test_a_home_exception_outside_the_input_range_is_used_as_is() -> None:
    """HOME 월별 예외는 50~200% 밖일 수 있다 — 막지 않고 그 달을 그대로 판정한다."""
    result = _run(general_by_month={202709: 2.5, 202801: 0.3})

    assert 202709 in result.kpis.below_months
    assert 202801 not in result.kpis.below_months


# ------------------------------------------------------------------ ⑭ 비중 사사오입


def test_the_proportional_split_rounds_half_up() -> None:
    """10 × 1/4 = 2.5 → 3(파이썬 `round` 의 은행가 반올림이면 2)."""
    result = simulate_constraint(
        [_one(202706, required=4, available=10, demand=1)],
        ConstraintConditions(202706, 202706, 1.0, None, 0),
    )
    row = result.month(202706)

    assert row.proportional_constrained == 3
    assert row.proportional_existing == 7.0
    assert row.proportional_existing_rate == pytest.approx(7 / 3)
    assert row.proportional_constrained_rate == pytest.approx(3.0)


# ------------------------------------------------------------------ ⑮ 검증


@pytest.mark.parametrize(
    "conditions",
    [
        replace(CONDITIONS, period_start=202713),
        replace(CONDITIONS, period_start=202712, period_end=202706),
        replace(CONDITIONS, constraint_target=0.4),
        replace(CONDITIONS, constraint_target=3.1),
        replace(CONDITIONS, constraint_target=math.nan),
        replace(CONDITIONS, modification_days=0),
        replace(CONDITIONS, modification_days=366),
        replace(CONDITIONS, cutoff_days=-1),
    ],
)
def test_invalid_conditions_are_rejected(conditions: ConstraintConditions) -> None:
    with pytest.raises(ValueError):
        simulate_constraint(_inputs(), conditions)


@pytest.mark.parametrize(
    "months",
    [
        [_one(202707, required=1, available=1), _one(202706, required=1, available=1)],
        [_one(202706, required=1, available=1), _one(202706, required=1, available=1)],
        [_one(202613, required=1, available=1)],
        [_one(202706, required=1, available=1, demand=2)],
        [_one(202706, required=-1, available=1)],
        [_one(202706, required=1, available=math.nan)],
        [_one(202706, required=1, available=1, general=0.0)],
        [_one(202706, required=1, available=1, general=-1.1)],
        [_one(202706, required=1, available=1, general=math.nan)],
    ],
)
def test_invalid_months_are_rejected(months: list[ConstraintMonthInput]) -> None:
    with pytest.raises(ValueError):
        simulate_constraint(months, CONDITIONS)


@pytest.mark.parametrize("general", [2.5, 0.3])
def test_any_positive_threshold_is_accepted(general: float) -> None:
    simulate_constraint([_one(202706, required=1, available=1, general=general)], CONDITIONS)


# ------------------------------------------------------------------ ⑯ 어댑터


def _plan_rows() -> pd.DataFrame:
    rows = [
        {"공정": " TC Bonding ", "생산계획년월": 202706, "소요대수": 43.0, "가용대수": 48.0},
        {"공정": " TC Bonding ", "생산계획년월": 202707, "소요대수": 44.0, "가용대수": 50.0},
        {"공정": "Saw", "생산계획년월": 202706, "소요대수": 9.0, "가용대수": 99.0},
    ]
    frame = pd.DataFrame(rows).reindex(columns=list(PROCESS_MONTH_COLUMNS))
    return frame


def _required_equipment() -> pd.DataFrame:
    rows = [
        ("HBM라E", "양산", 202706, 3.0),
        ("HBM라E", "ER", 202706, 2.0),
        ("HBM라E", "양산", 202707, 6.0),
        ("DDR5", "양산", 202706, 38.0),
        ("DDR5", "양산", 202707, 38.0),
    ]
    frame = pd.DataFrame(rows, columns=["제품정보", "양산구분", "생산계획년월", "소요대수"])
    frame["공정"] = "TC Bonding"
    return frame


def _product_table() -> pd.DataFrame:
    return build_process_product_demand(
        _required_equipment(),
        process="TC Bonding",
        split="제품정보",
        months=(202706, 202707),
        limit=10_000,
    )


def test_the_adapter_splits_the_plan_demand_by_product() -> None:
    inputs = constraint_month_inputs(
        _plan_rows(),
        _product_table(),
        process="TC Bonding",
        product="HBM라E",
        months=(202706, 202707),
        general_target=lambda month: 1.1 if month == 202706 else 1.2,
    )

    assert inputs == (
        ConstraintMonthInput(202706, 43.0, 5.0, 48.0, 1.1),
        ConstraintMonthInput(202707, 44.0, 6.0, 50.0, 1.2),
    )


def test_an_unknown_product_has_no_constrained_demand() -> None:
    inputs = constraint_month_inputs(
        _plan_rows(),
        _product_table(),
        process="TC Bonding",
        product="없는 제품",
        months=(202706,),
        general_target=lambda _month: 1.1,
    )

    assert inputs[0].constrained_demand == 0.0


def test_the_adapter_rejects_a_product_table_that_does_not_add_up() -> None:
    table = _product_table()
    table["202706"] = table["202706"] + [1e-3] + [0.0] * (len(table) - 1)

    with pytest.raises(ValueError, match="제품별 소요 합이 공정 소요와 다릅니다"):
        constraint_month_inputs(
            _plan_rows(),
            table,
            process="TC Bonding",
            product="HBM라E",
            months=(202706,),
            general_target=lambda _month: 1.1,
        )


def test_the_adapter_raises_key_error_for_a_process_missing_from_the_plan() -> None:
    with pytest.raises(KeyError):
        constraint_month_inputs(
            _plan_rows(),
            _product_table(),
            process="Wire Bonding",
            product="HBM라E",
            months=(202706,),
            general_target=lambda _month: 1.1,
        )


def test_the_adapter_ignores_the_other_bucket_and_blank_names() -> None:
    """「그 밖」 묶음 행은 분류값이 빈 글자다 — 빈 이름을 골라도 그 행을 고르지 않는다."""
    table = pd.DataFrame(
        {
            "제품정보": ["HBM라E", ""],
            "분류": ["HBM라E", "그 밖 1개"],
            OTHER_ROW_COLUMN: [False, True],
            "묶은 수": [1, 1],
            "202706": [5.0, 38.0],
        }
    )

    def constrained(product: str) -> float:
        (row,) = constraint_month_inputs(
            _plan_rows(),
            table,
            process="TC Bonding",
            product=product,
            months=(202706,),
            general_target=lambda _month: 1.1,
        )
        return row.constrained_demand

    assert constrained("") == 0.0
    assert constrained("HBM라E") == 5.0


def test_the_adapter_folds_float_noise_onto_the_process_demand() -> None:
    """다른 제품이 없는 달은 Rc = R 로 접는다 — 합 차례가 다른 두 근거의 잡음이 Re 로 남지 않게."""
    plan = pd.DataFrame(
        [{"공정": "TC Bonding", "생산계획년월": 202706, "소요대수": 0.1 + 0.2, "가용대수": 1.0}]
    ).reindex(columns=list(PROCESS_MONTH_COLUMNS))
    table = pd.DataFrame(
        {
            "제품정보": ["HBM라E"],
            "분류": ["HBM라E"],
            OTHER_ROW_COLUMN: [False],
            "묶은 수": [1],
            "202706": [0.3],
        }
    )
    (row,) = constraint_month_inputs(
        plan,
        table,
        process="TC Bonding",
        product="HBM라E",
        months=(202706,),
        general_target=lambda _month: 1.1,
    )

    assert row.constrained_demand == row.required
    result = simulate_constraint([row], ConstraintConditions(202706, 202706, 1.2, None, 0))
    assert result.month(202706).existing_demand == 0.0
    assert result.month(202706).existing_rate is None


# ------------------------------------------------------------------ ⑰ Cut-off 소수


def test_a_fractional_cutoff_floors_like_the_wd_window() -> None:
    """`readiness.cutoff_days` 는 int(7.9) = 7 이고 `wd_window(m, 7.9)` 도 7 로 내린다 — 같은 창."""
    window = modification_window(202706, units=6, days=30, cutoff_days=int(7.9))

    assert window.end == wd_window(202706, 7.9).first_day == date(2027, 5, 25)
    assert window.start == date(2027, 4, 25)


# ------------------------------------------------------------------ ⑱ 판정 한 길


def test_the_securement_judgment_is_capacity_status_without_tolerance() -> None:
    """41.8 ÷ 38 = 1.0999999999999999 < 1.1 — HOME 과 똑같이 「미달」 이다."""
    result = simulate_constraint(
        [_one(202706, required=38, available=41.8)],
        ConstraintConditions(202706, 202706, 1.2, None, 7),
    )
    row = result.month(202706)
    rate = 41.8 / 38

    assert row.existing_rate == rate
    expected = capacity_status(rate, secure_threshold=1.1, warning_threshold=1.1) == "secure"
    assert row.existing_secure is expected is False
    assert secure(rate, 1.1) is expected
    assert secure(None, 1.1) is False
    assert result.kpis.below_months == (202706,)


def _compare_names(node: ast.Compare) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def test_the_service_does_not_write_its_own_threshold_comparison() -> None:
    """기준·제약 확보율을 비율과 `>=`·`<` 로 직접 견주는 식이 없고 `capacity_status` 를 부른다."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    threshold_names = {
        "target",
        "general_target",
        "constraint_target",
        "secure_threshold",
        "warning_threshold",
    }

    offending = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and _compare_names(node) & threshold_names
    ]
    assert offending == []
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "capacity_status" in calls


# ------------------------------------------------------------------ ⑲ 충족은 정수


@pytest.mark.parametrize("target", [1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4])
def test_the_integer_need_always_meets_the_constraint_target(target: float) -> None:
    """`need/Rc' ≥ T` 가 늘 성립한다 — `met`(정수)과 「제약 % ≥ T」 가 같은 답이다."""
    missed = [
        step / 100
        for step in range(1, 2001)
        if required_units(step / 100, target) / (step / 100) < target
    ]

    assert missed == []


# ------------------------------------------------------------------ 그 밖의 가장자리


def test_sparse_months_carry_from_the_previous_visible_month() -> None:
    """「앞 달」 은 보이는 차례의 앞 달이다 — 빠진 달(202707)에 든 비가동은 셈하지 않는다."""
    result = simulate_constraint(
        [
            _one(202706, required=20, available=30, demand=5),
            _one(202708, required=20, available=30, demand=7),
        ],
        ConstraintConditions(202706, 202708, 1.0, 30, 7),
    )

    assert [(window.month, window.units) for window in result.windows] == [
        (202706, 5),
        (202708, 2),
    ]
    later = result.month(202708)
    assert (later.dedicated, later.increment) == (7, 2)
    assert later.downtime == 0.0
    assert result.month(202706).downtime == 0.0


def test_a_period_month_without_constrained_demand_keeps_the_dedicated_units() -> None:
    """기간 안인데 Rc 0 인 달도 개조 켬이면 앞 달 전용 대수를 그대로 뗀다(가정 3)."""
    result = simulate_constraint(
        [
            _one(202706, required=20, available=30, demand=5),
            _one(202707, required=20, available=30, demand=0),
        ],
        ConstraintConditions(202706, 202707, 1.0, 30, 7),
    )
    idle = result.month(202707)

    assert (idle.need, idle.dedicated, idle.allocated) == (0, 5, 5)
    assert idle.met is None and idle.constrained_rate is None
    assert idle.existing_available == 25.0


@pytest.mark.parametrize(("available", "impact"), [(96.0, None), (94.0, 202706)])
def test_the_first_impact_ignores_differences_within_the_display_threshold(
    available: float, impact: int | None
) -> None:
    """기존이 제약 없을 때보다 0.05%p 이하로 낮은 달은 영향 시작이 아니다.

    R 100 · Rc 1 · 제약 100% · 개조 끔이면 기존 (A − 1)/99 − 제약 없을 때 A/100
    = (A − 100)/9900 이다 — A 96 은 −0.040%p, A 94 는 −0.061%p.
    """
    result = simulate_constraint(
        [_one(202706, required=100, available=available, demand=1)],
        ConstraintConditions(202706, 202706, 1.0, None, 7),
    )
    row = result.month(202706)

    assert row.existing_rate is not None and row.baseline_rate is not None
    gap = row.baseline_rate - row.existing_rate
    assert gap > 0
    assert (gap > IMPACT_TOLERANCE) is (impact is not None)
    assert result.kpis.first_impact_month == impact


def test_no_visible_months_gives_an_empty_result() -> None:
    result = simulate_constraint([], CONDITIONS)

    assert result.months == () and result.windows == ()
    assert result.starts_before_range is False
    assert result.kpis.lowest_existing_month is None
    assert result.kpis.max_dedicated == 0
