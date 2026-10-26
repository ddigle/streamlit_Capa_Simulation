# Purpose: 개조 일정 서비스의 배치·기준 지킴·동시 한도·목적·대안 셋·어댑터를 손계산과 작은 완전
# 탐색으로 본다.

"""개조 일정(`services/modification_schedule.py`) 시험.

손계산은 Cut-off 0 이라 W/D 구간이 달력 달과 같은 꼴로 둔다(2027-01 = 1/1~1/31, 31일). 대부분 R = 10
· G = 100% 라 「확보율 ≥ 기준」 이 「그 달 비가동 대·일 ≤ (A − 10) × W」 와 같다 — A 11 이면 1월 31
대·일, 2월 28 대·일이 예산이다.

예산을 정수 대·일 B 로 바로 주고 싶을 때는 A = 10 · R = 1 · G = 10 − (B + 0.5) ÷ W 로 둔다
(`_budget_month`) — 「대·일 ≤ B」 가 곧 판정이고(0.5 는 경계 잡음을 피하는 여유) 그 달 동시 한도
⌊A⌋ = 10 이 N ≤ 3 을 막지 않는다.

**완전 탐색 대조**(`_brute`)는 서비스와 따로 짠 것이다 — 시작 후보의 모든 중복 조합을 보며 달마다
대·일 · 날마다 동시 대수(동시 상한 · ⌊A⌋) · `secure` 판정을 다시 센다. 두 꼴을 시드를 박아 늘 같은
문제로 본다(검토 탐침 probe1 · probe5 를 옮긴 것). 실수 꼴은 두~세 달 · 실수 R·A·G · 여유 ·
기한 · 목적 · 동시 상한 · Cut-off · 달 맞춤 · 늦은 시작이고, 넓은 예산 꼴은 두 달 · 3대 · 한 달
예산이 2D 를 넘을 수 있는 문제다(이른 시작 탐욕이 하루에 2대 이상을 몰아 넣어 못 넣는 자리).
견주는 것은 완료 W/D 달 · 다 넣었나 · 넣을 수 있는 대수 · 필요 완화 · 못 넣는 까닭 · 「가장
고르게」 δ 와 물러남이다 — 확보율이 달 평균이라 「몇 월에 끝나나」 가 답이고 날은 길마다 다를 수
있다.
"""

from __future__ import annotations

import ast
import itertools
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import capa_simulation.services.modification_schedule as modification_schedule
from capa_simulation.services.constraint_simulation import secure
from capa_simulation.services.modification_schedule import (
    Objective,
    ScheduleConditions,
    ScheduleMonthInput,
    ScheduleResult,
    plan_modification_schedule,
    schedule_month_inputs,
)
from capa_simulation.services.wd_window import wd_window

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "capa_simulation"
    / "services"
    / "modification_schedule.py"
)
JAN, FEB, MAR = 202701, 202702, 202703


def _month(
    month: int, available: float, required: float = 10.0, target: float = 1.0
) -> ScheduleMonthInput:
    return ScheduleMonthInput(
        month=month, required=required, available=available, general_target=target
    )


def _three(available: float = 11.0) -> list[ScheduleMonthInput]:
    return [_month(JAN, available), _month(FEB, available), _month(MAR, available)]


def _budget_month(month: int, budget: int, cutoff: int = 0) -> ScheduleMonthInput:
    """그 달 대·일 예산이 정확히 `budget` 인 달(A 10 · R 1 — 동시 한도 10)."""
    width = wd_window(month, cutoff).days
    return ScheduleMonthInput(month, 1.0, 10.0, 10.0 - (budget + 0.5) / width)


def _plan(
    months: list[ScheduleMonthInput], *, earliest: date = date(2027, 1, 1), **kwargs: Any
) -> ScheduleResult:
    return plan_modification_schedule(
        months,
        ScheduleConditions(cutoff_days=kwargs.pop("cutoff_days", 0), earliest=earliest, **kwargs),
    )


def _starts(result: ScheduleResult) -> list[tuple[date, int]]:
    return [(batch.start, batch.units) for batch in result.batches]


def _assert_keeps_every_month(result: ScheduleResult) -> None:
    """서비스 밖에서 다시 셈 — 겹친 일수(`overlap_days`) 합과 같은 판정(`secure`)."""
    cutoff = result.conditions.cutoff_days
    for row in result.months:
        window = wd_window(row.month, cutoff)
        unit_days = sum(
            batch.units * window.overlap_days(batch.start, batch.last_day)
            for batch in result.batches
        )
        assert unit_days == row.downtime_unit_days
        if unit_days == 0:
            continue
        usable = row.available - unit_days / window.days
        assert usable >= -1e-9
        if row.required > 0:
            assert secure(usable / row.required, row.threshold)


# ------------------------------------------------------------------ 손계산


def test_one_unit_fills_january_exactly_at_the_threshold() -> None:
    """A 11 · R 10 · 31일 → (11 − 31/31) ÷ 10 = 100% — 기준과 같으면 지킨다(「이상」)."""
    result = _plan(_three(), units=1, days=31)

    assert _starts(result) == [(date(2027, 1, 1), 1)]
    assert result.finish_day == date(2027, 1, 31)
    assert result.finish_month == JAN
    january = result.month(JAN)
    assert january.downtime_unit_days == 31
    assert january.downtime == 1.0
    assert january.rate == 1.0
    assert january.secure_after is True
    assert result.tightest_month == JAN and result.tightest_margin == 0.0
    assert result.shortfall is None and result.complete
    _assert_keeps_every_month(result)


def test_the_second_unit_waits_for_the_february_budget() -> None:
    """1월 예산 31 을 첫 대가 다 쓰고, 둘째 대는 2/1 부터(2월 28 + 3월 3) — 끝 3/3."""
    result = _plan(_three(), units=2, days=31)

    assert _starts(result) == [(date(2027, 1, 1), 1), (date(2027, 2, 1), 1)]
    assert result.finish_day == date(2027, 3, 3)
    assert result.finish_month == MAR
    assert result.strategy == "early"
    assert result.batches[1].shares == ((FEB, 28), (MAR, 3))
    assert result.max_concurrent == 1
    _assert_keeps_every_month(result)


def test_the_late_greedy_finishes_a_month_earlier_than_the_early_one() -> None:
    """검토 문서 3-2 의 예를 10·11·12월(31·30·31일)로 — 예산 28·50·36, 2대 × 35일, 동시 3.

    이른 시작은 첫 대가 10/4 에 시작해 10월 예산 28 을 혼자 다 쓰고 둘째 대가 12월에 끝난다. 11월 끝
    고정 늦은 시작은 10/27(10월 5 · 11월 30)과 10/17(10월 15 · 11월 20)로 11월 안에 끝낸다.
    """
    budgets = {202610: 28, 202611: 50, 202612: 36}
    months = [_budget_month(month, budget) for month, budget in budgets.items()]
    result = _plan(months, earliest=date(2026, 10, 1), units=2, days=35, concurrent=3)

    assert result.strategy == "late"
    assert result.finish_month == 202611
    assert _starts(result) == [(date(2026, 10, 17), 1), (date(2026, 10, 27), 1)]
    assert result.month(202610).downtime_unit_days == 20
    assert result.month(202611).downtime_unit_days == 50
    _assert_keeps_every_month(result)


def test_a_concurrency_cap_lines_the_units_up() -> None:
    months = _three(available=20.0)
    capped = _plan(months, units=3, days=10, concurrent=1)
    free = _plan(months, units=3, days=10)

    assert _starts(capped) == [
        (date(2027, 1, 1), 1),
        (date(2027, 1, 11), 1),
        (date(2027, 1, 21), 1),
    ]
    assert capped.max_concurrent == 1 and capped.finish_day == date(2027, 1, 30)
    assert _starts(free) == [(date(2027, 1, 1), 3)]
    assert free.max_concurrent == 3 and free.finish_day == date(2027, 1, 10)


def test_a_month_already_below_the_threshold_gets_no_downtime() -> None:
    """1월은 개조 없이도 95% — 하루도 넣지 않고 2/1 에 시작한다(C11)."""
    months = [_month(JAN, 9.5), _month(FEB, 11.0), _month(MAR, 11.0)]
    result = _plan(months, units=1, days=10)

    assert _starts(result) == [(date(2027, 2, 1), 1)]
    january = result.month(JAN)
    assert january.blocked and january.downtime_unit_days == 0
    assert january.secure_after is False and january.baseline_secure is False
    assert not result.month(FEB).blocked


def test_the_safety_margin_lifts_the_placement_threshold() -> None:
    """여유 5%p — 1월 예산 (11 − 10.5) × 31 = 15.5 → 15 대·일. 20일은 1/17(1월 15 · 2월 5)."""
    plain = _plan(_three(), units=1, days=20)
    lifted = _plan(_three(), units=1, days=20, margin=0.05)

    assert _starts(plain) == [(date(2027, 1, 1), 1)]
    assert _starts(lifted) == [(date(2027, 1, 17), 1)]
    assert lifted.applied_margin == 0.05
    assert lifted.month(JAN).threshold == pytest.approx(1.05)
    assert lifted.month(JAN).general_target == 1.0
    _assert_keeps_every_month(lifted)


def test_a_zero_demand_month_only_keeps_the_available_non_negative() -> None:
    """R 0 달은 가용이 음수가 아니기만 — 1월 A 1 이면 31 대·일 한 대뿐, 2월 A 0 은 못 넣는다."""
    months = [_month(JAN, 1.0, required=0.0), _month(FEB, 0.0, required=0.0)]
    fitted = _plan(months, units=1, days=31)

    assert _starts(fitted) == [(date(2027, 1, 1), 1)]
    assert fitted.month(JAN).rate is None and fitted.month(JAN).secure_after is None
    assert fitted.tightest_month is None and fitted.shortfall is None

    # 32일이면 2월(A 0)에 하루가 걸려 넣을 곳이 없다 — 기준을 0 까지 낮춰도 가용이 모자란다.
    missed = _plan(months, units=1, days=32)
    shortfall = missed.shortfall
    assert shortfall is not None and shortfall.placed == 0
    assert shortfall.by_deadline is False and shortfall.finish_without_deadline is None
    assert shortfall.relief is None and shortfall.cause == "capacity" and shortfall.exact


def test_aligned_windows_end_on_the_wd_last_day() -> None:
    """달 맞춤 창 — 끝이 그 달 W/D 끝 날(1/31)이라 1/22 시작. 날 단위는 1/1."""
    aligned = _plan(_three(), units=2, days=10, aligned=True)
    daily = _plan(_three(), units=2, days=10)

    assert _starts(aligned) == [(date(2027, 1, 22), 2)]
    assert aligned.finish_day == date(2027, 1, 31)
    assert _starts(daily) == [(date(2027, 1, 1), 2)]


def test_the_wd_coordinate_follows_the_cutoff() -> None:
    """Cut-off 9 — 12월 W/D 는 11/22~12/22 라 달력 11월 22일 시작 비가동이 12월 몫이다."""
    months = [_month(202611, 11.0), _month(202612, 11.0)]
    result = _plan(months, earliest=date(2026, 11, 22), units=1, days=10, cutoff_days=9)

    assert _starts(result) == [(date(2026, 11, 22), 1)]
    assert result.batches[0].shares == ((202612, 10),)
    assert result.month(202611).downtime_unit_days == 0
    assert result.month(202612).downtime_unit_days == 10
    assert result.month(202611).open is False


def test_months_before_the_earliest_start_are_closed() -> None:
    result = _plan(_three(), earliest=date(2027, 2, 10), units=1, days=5)

    assert [row.open for row in result.months] == [False, True, True]
    assert result.first_day == date(2027, 2, 10)
    assert _starts(result) == [(date(2027, 2, 10), 1)]


def test_a_missed_deadline_reports_the_three_alternatives() -> None:
    """2대 × 31일을 2/28 까지 — 1대뿐. 기한 없이 3/3 끝. 1월 33 · 2월 29 대·일로 넣으려면 1월이
    (11 − 33/31) ÷ 10 = 1 − 2/310 → 기준을 2/310 = 0.645%p 낮춰야 한다."""
    result = _plan(_three(), units=2, days=31, deadline=date(2027, 2, 28))

    assert result.complete is False and result.placed == 1 and result.remaining == 1
    assert result.finish_day is None
    assert result.last_day == date(2027, 2, 28)
    shortfall = result.shortfall
    assert shortfall is not None
    assert shortfall.placed == 1 and shortfall.by_deadline
    assert shortfall.finish_without_deadline == date(2027, 3, 3)
    assert shortfall.finish_month_without_deadline == MAR
    assert shortfall.relief == pytest.approx(2 / 310, abs=1e-6)
    _assert_keeps_every_month(result)


def test_lowering_by_the_reported_relief_fits_the_deadline() -> None:
    """적힌 완화만큼 기준(G)을 낮추면 같은 기한 안에 다 든다."""
    missed = _plan(_three(), units=2, days=31, deadline=date(2027, 2, 28))
    assert missed.shortfall is not None and missed.shortfall.relief is not None
    lowered = 1.0 - missed.shortfall.relief
    months = [_month(month, 11.0, target=lowered) for month in (JAN, FEB, MAR)]

    fitted = _plan(months, units=2, days=31, deadline=date(2027, 2, 28))

    assert fitted.complete and fitted.strategy == "late"
    assert fitted.month(JAN).downtime_unit_days == 33
    assert fitted.month(FEB).downtime_unit_days == 29
    _assert_keeps_every_month(fitted)


def test_a_deadline_before_any_open_day_places_nothing() -> None:
    result = _plan(_three(), units=1, days=5, deadline=date(2026, 12, 31))

    assert result.placed == 0 and not result.batches
    assert result.shortfall is not None
    assert result.shortfall.by_deadline and result.shortfall.relief is None
    assert result.shortfall.finish_without_deadline == date(2027, 1, 5)
    # 기한이 시작보다 앞이라 넣을 창이 없다(가용 탓이 아니다).
    assert result.shortfall.cause == "window"


def test_the_even_objective_raises_the_lowest_month_as_high_as_possible() -> None:
    """1대 × 10일 · 기한 3/31 — 1월 5 · 2월 5 일로 나누면 2월이 1.1 − 5/280 = 108.21% 로 가장 높다
    (1월만 10일이면 106.77%, 1월 6 · 2월 4 면 1월 108.06%)."""
    result = _plan(_three(), units=1, days=10, deadline=date(2027, 3, 31), objective="even")

    best = 0.1 - 5 / 280
    assert result.applied_margin == pytest.approx(best, abs=1e-6)
    assert _starts(result) == [(date(2027, 1, 27), 1)]
    assert result.tightest_month == FEB
    assert result.tightest_margin == pytest.approx(best, abs=1e-9)
    assert result.fell_back is False
    assert result.month(FEB).threshold == pytest.approx(1.0 + best, abs=1e-6)
    # 올린 δ 때문에만 비는 달은 「개조 없이도 미달」 이 아니다.
    assert not any(row.blocked for row in result.months)
    _assert_keeps_every_month(result)


def test_the_even_objective_falls_back_with_alternatives_when_the_margin_alone_misses() -> None:
    result = _plan(_three(), units=2, days=31, deadline=date(2027, 2, 28), objective="even")

    assert result.applied_margin == 0.0
    assert result.shortfall is not None and result.shortfall.placed == 1
    # 「가장 고르게」 를 못 해 「가장 빨리」 로 풀었다는 것을 결과가 들고 있다(화면이 적는다).
    assert result.fell_back is True


def test_months_must_be_visible_ascending_and_fine() -> None:
    with pytest.raises(ValueError, match="오름차순"):
        _plan([_month(FEB, 11.0), _month(JAN, 11.0)], units=1, days=5)
    with pytest.raises(ValueError, match="보이는 달이 없어"):
        _plan([], units=1, days=5)
    with pytest.raises(ValueError, match="공정 소요"):
        _plan([_month(JAN, 11.0, required=-1.0)], units=1, days=5)
    with pytest.raises(ValueError, match="기준 확보율"):
        _plan([_month(JAN, 11.0, target=0.0)], units=1, days=5)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"units": 0}, "개조 대수"),
        ({"days": 0}, "개조 기간"),
        ({"days": 366}, "개조 기간"),
        ({"concurrent": 0}, "동시 개조 상한"),
        ({"margin": -0.01}, "안전 여유"),
        ({"margin": 0.31}, "안전 여유"),
        ({"objective": "even"}, "기한"),
        ({"cutoff_days": -1}, "Cut-off"),
    ],
)
def test_conditions_are_checked(changes: dict[str, Any], message: str) -> None:
    kwargs: dict[str, Any] = {"units": 1, "days": 5, **changes}
    with pytest.raises(ValueError, match=message):
        _plan(_three(), **kwargs)


def test_the_service_judges_only_through_secure() -> None:
    """기준과 비율을 `>=`·`<` 로 직접 견주는 식이 없고 `secure` 한 길을 부른다(AGENTS 6장)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"target", "targets", "general_target", "threshold"}

    def compared(node: ast.Compare) -> set[str]:
        found: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                found.add(child.id)
            elif isinstance(child, ast.Attribute):
                found.add(child.attr)
        return found

    offending = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and compared(node) & names
    ]
    assert offending == []
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "secure" in calls


def test_units_are_spread_when_the_greedy_would_bunch_them() -> None:
    """1월 65 · 2월 34 대·일에 3대 × 33일 — 첫날 2대를 몰아 넣으면 셋째가 못 든다(검토 탐침
    probe3).

    1/1 · 1/9 · 1/21 시작이면 1월 31 + 23 + 11 = 65 · 2월 2 + 10 + 22 = 34 로 꼭 맞고 2/22 에
    끝난다.
    """
    months = [_budget_month(JAN, 65), _budget_month(FEB, 34)]

    free = _plan(months, units=3, days=33)
    held = _plan(months, units=3, days=33, deadline=date(2027, 2, 22))

    for result in (free, held):
        assert result.complete and result.shortfall is None
        assert result.finish_month == FEB
        assert [row.downtime_unit_days for row in result.months] == [65, 34]
        _assert_keeps_every_month(result)
    assert held.finish_day == date(2027, 2, 22)


def test_the_reported_relief_is_the_smallest_one() -> None:
    """실수 입력 — 기한 9/18 · 여유 2%p 로 3대 × 33일을 넣으려면 13.67%p 가 아니라 11.53%p 면 된다
    (검토 탐침 probe1 seed 3 — 그 값은 완전 탐색이 낸 것이다)."""
    months = [
        ScheduleMonthInput(202608, 10.532963657848278, 11.62584257716873, 1.0),
        ScheduleMonthInput(202609, 10.446182077142389, 11.109502620188698, 1.05),
    ]
    result = _plan(
        months,
        earliest=date(2026, 7, 27),
        units=3,
        days=33,
        cutoff_days=5,
        deadline=date(2026, 9, 18),
        margin=0.02,
    )

    shortfall = result.shortfall
    assert shortfall is not None and shortfall.exact
    assert shortfall.relief == pytest.approx(0.11530985834930872, abs=1e-6)


def test_the_even_objective_is_not_capped_by_a_fixed_span() -> None:
    """여유가 큰 공정(개조 전 400% · 150% · 400%) — 1월 · 3월에 한 대씩이면 두 달 모두 396.8%.

    위 끝이 고정 +100%p 면 그 값에서 멈춰 「가장 빨리」 와 같은 배치(두 대 1/1)를 냈다(검토 탐침
    probe8).
    """
    months = [_month(JAN, 40.0), _month(FEB, 15.0), _month(MAR, 40.0)]
    earliest = _plan(months, units=2, days=10, deadline=date(2027, 3, 31))
    even = _plan(months, units=2, days=10, deadline=date(2027, 3, 31), objective="even")

    best = (40 - 10 / 31) / 10 - 1.0
    assert even.applied_margin == pytest.approx(best, abs=1e-6)
    assert [batch.start.month for batch in even.batches] == [1, 3]
    assert earliest.tightest_margin is not None and even.tightest_margin is not None
    assert even.tightest_margin > earliest.tightest_margin
    _assert_keeps_every_month(even)


def test_the_even_objective_raises_the_smallest_margin_not_the_smallest_rate() -> None:
    """달마다 기준이 다르면(1월 100% · 2월 110%) 「가장 고르게」 가 키우는 것은 기준 대비 여유다 —
    요약의 가장 빠듯한 달도 같은 값으로 고른다(확보율이 낮은 1월이 아니라 여유가 작은 2월)."""
    months = [_month(JAN, 11.0), _month(FEB, 12.0, target=1.1), _month(MAR, 0.0)]
    result = _plan(months, units=1, days=10, deadline=date(2027, 2, 28), objective="even")

    assert result.tightest_month == FEB
    assert result.tightest_margin == pytest.approx(result.applied_margin, abs=1e-6)
    january, february = result.month(JAN), result.month(FEB)
    assert january.rate is not None and february.rate is not None
    assert january.rate < february.rate


def test_units_under_modification_never_outnumber_the_available() -> None:
    """1월 가용 1대(소요 0.1 이라 예산은 넉넉) — 3대 × 7일을 같은 날 넣지 않고 줄을 세운다(검토 탐침
    probe10 의 「가용 3대에 10대 동시」 를 막는 날 동시 한도 ⌊A⌋)."""
    months = [
        _month(JAN, 1.0, required=0.1),
        _month(FEB, 3.0, required=0.1),
        _month(MAR, 3.0, required=0.1),
    ]
    result = _plan(months, units=3, days=7)

    assert _starts(result) == [
        (date(2027, 1, 1), 1),
        (date(2027, 1, 8), 1),
        (date(2027, 1, 15), 1),
    ]
    assert result.max_concurrent == 1
    assert [row.concurrent_cap for row in result.months] == [1, 3, 3]
    _assert_keeps_every_month(result)


def test_more_units_than_the_process_ever_has_are_rejected() -> None:
    months = [ScheduleMonthInput(month, 0.5, 3.0, 1.1) for month in (JAN, FEB, MAR)]
    with pytest.raises(ValueError, match="개조 대수 10대가 이 공정 가용보다 많습니다"):
        _plan(months, units=10, days=7)
    assert _plan(months, units=3, days=7).complete


def test_the_cause_tells_a_short_window_from_the_concurrency_cap() -> None:
    """기준을 0% 까지 낮춰도 못 넣는 까닭 — 시작 ~ 기한이 D 보다 짧으면 창, 동시 상한을 걷으면 들면
    동시 상한, 아니면 가용.

    - 창: 1/1 ~ 1/5 는 5일이라 10일 개조가 한 대도 들지 않는다.
    - 동시 상한: 1대씩 30일이면 90일에 세 대뿐이다 — 상한을 걷으면 열 대가 1월에 다 든다.
    - 가용: 2월 가용 1대(⌊A⌋ = 1)라 40일 창은 모두 2월 초를 지나 한 대만 선다.
    """
    short = _plan(_three(), units=1, days=10, deadline=date(2027, 1, 5))
    capped = _plan(_three(20.0), units=10, days=30, concurrent=1)
    scarce = _plan(
        [
            _month(JAN, 3.0, required=1.0),
            _month(FEB, 1.0, required=0.5),
            _month(MAR, 1.0, required=0.5),
        ],
        units=3,
        days=40,
    )

    assert short.shortfall is not None and short.shortfall.cause == "window"
    assert capped.shortfall is not None and capped.shortfall.placed == 3
    assert capped.shortfall.relief is None and capped.shortfall.cause == "concurrent"
    assert scarce.shortfall is not None and scarce.shortfall.cause == "capacity"
    for result in (short, capped, scarce):
        assert result.shortfall is not None and result.shortfall.exact


def test_an_exhausted_search_marks_the_alternatives_as_found_not_proven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """완전 탐색 마디 한도를 다 쓰면 대안 셋은 「이 계산으로 찾은 범위」 다 — 탐욕이 못 넣은 자리를
    확인하지 못했다는 것을 결과가 들고 있다."""
    monkeypatch.setattr(modification_schedule, "SEARCH_CALL_NODES", 1)
    months = [_budget_month(JAN, 65), _budget_month(FEB, 34)]

    result = _plan(months, units=3, days=33)

    assert result.shortfall is not None and result.shortfall.exact is False
    assert result.placed == 2


# ------------------------------------------------------------------ 완전 탐색 대조


class _Brute:
    """서비스와 따로 짠 완전 탐색 — 시작 후보의 모든 중복 조합."""

    def __init__(self, inputs: list[ScheduleMonthInput], conditions: ScheduleConditions) -> None:
        self.inputs = inputs
        self.conditions = conditions
        self.windows = [wd_window(row.month, conditions.cutoff_days) for row in inputs]
        self.first = max(conditions.earliest, self.windows[0].first_day)
        horizon = self.windows[-1].boundary_end
        deadline = conditions.deadline
        self.limit = horizon if deadline is None else min(deadline, horizon)
        days = conditions.days
        if conditions.aligned:
            raw = [window.boundary_end - timedelta(days=days - 1) for window in self.windows]
            starts = [
                start
                for start in raw
                if start >= self.first and start + timedelta(days=days - 1) <= self.limit
            ]
        else:
            count = (self.limit - self.first).days - days + 2
            starts = [self.first + timedelta(days=offset) for offset in range(max(count, 0))]
        self.has_candidates = bool(starts)
        self.pool: list[tuple[date, tuple[tuple[int, int], ...]]] = []
        for start in starts:
            last = start + timedelta(days=days - 1)
            shares = tuple(
                (index, (min(last, window.boundary_end) - max(start, window.first_day)).days + 1)
                for index, window in enumerate(self.windows)
                if max(start, window.first_day) <= min(last, window.boundary_end)
            )
            if sum(share for _, share in shares) == days:
                self.pool.append((start, shares))
        self.whole = [max(0, math.floor(row.available + 1e-9)) for row in inputs]

    def month_of(self, day: date) -> int:
        return next(
            index
            for index, window in enumerate(self.windows)
            if window.first_day <= day <= window.boundary_end
        )

    def value(self, combo: tuple[int, ...], concurrent: int | None) -> tuple[float, date] | None:
        """그 조합이 서면 (개조 달 최저 기준 대비 여유 — R 0 달뿐이면 ∞, 마지막 날), 아니면 None."""
        days = self.conditions.days
        used = [0] * len(self.inputs)
        for position in combo:
            for index, share in self.pool[position][1]:
                used[index] += share
        caps = [whole if concurrent is None else min(whole, concurrent) for whole in self.whole]
        if any(cap < len(combo) for cap in caps):
            busy: dict[date, int] = {}
            for position in combo:
                for offset in range(days):
                    day = self.pool[position][0] + timedelta(days=offset)
                    busy[day] = busy.get(day, 0) + 1
            if any(count > caps[self.month_of(day)] for day, count in busy.items()):
                return None
        lowest = math.inf
        for index, row in enumerate(self.inputs):
            if used[index] == 0:
                continue
            usable = row.available - used[index] / self.windows[index].days
            if usable < -1e-9:
                return None
            if row.required > 0:
                lowest = min(lowest, usable / row.required - row.general_target)
        last = max(self.pool[position][0] for position in combo) + timedelta(days=days - 1)
        return lowest, last

    def combos(self, units: int) -> itertools.combinations_with_replacement[tuple[int, ...]]:
        return itertools.combinations_with_replacement(range(len(self.pool)), units)


def _brute_check(inputs: list[ScheduleMonthInput], conditions: ScheduleConditions) -> list[str]:
    """서비스 결과와 완전 탐색이 어긋난 곳(없으면 빈 목록)."""
    result = plan_modification_schedule(inputs, conditions)
    _assert_keeps_every_month(result)
    if conditions.concurrent is not None:
        assert result.max_concurrent <= conditions.concurrent
    brute = _Brute(inputs, conditions)
    margin = conditions.margin
    finish: int | None = None
    best: float | None = None
    best_free: float | None = None
    for combo in brute.combos(conditions.units):
        found = brute.value(combo, conditions.concurrent)
        if found is not None:
            best = found[0] if best is None else max(best, found[0])
            if found[0] >= margin - 1e-12:
                month = brute.month_of(found[1])
                finish = month if finish is None else min(finish, month)
        if conditions.concurrent is not None:
            free = brute.value(combo, None)
            if free is not None:
                best_free = free[0] if best_free is None else max(best_free, free[0])
    problems: list[str] = []
    months = [row.month for row in inputs]
    if conditions.objective == "earliest" or result.fell_back:
        got = months.index(result.finish_month) if result.finish_month is not None else None
        if result.complete != (finish is not None):
            problems.append(f"다 넣었나 {finish is not None} ≠ {result.complete}")
        elif conditions.objective == "earliest" and got != finish:
            problems.append(f"완료 달 {finish} ≠ {got}")
    if conditions.objective == "even":
        falls_back = best is None or best < margin - 1e-12
        if result.fell_back != falls_back:
            problems.append(f"물러남 {falls_back} ≠ {result.fell_back}")
        elif best is not None and not falls_back:
            ceiling = max(
                [margin]
                + [
                    row.available / row.required - row.general_target
                    for row, window in zip(inputs, brute.windows, strict=True)
                    if row.required > 0
                    and window.boundary_end >= brute.first
                    and window.first_day <= brute.limit
                ]
            )
            if abs(result.applied_margin - min(best, ceiling)) > 1e-6:
                problems.append(f"가장 고르게 δ {min(best, ceiling)} ≠ {result.applied_margin}")
    shortfall = result.shortfall
    if shortfall is not None:
        placed = 0
        for units in range(conditions.units - 1, 0, -1):
            if any(
                (found := brute.value(combo, conditions.concurrent)) is not None
                and found[0] >= margin - 1e-12
                for combo in brute.combos(units)
            ):
                placed = units
                break
        if not shortfall.exact:
            problems.append("마디 한도")
        if shortfall.placed != placed:
            problems.append(f"넣을 수 있는 대수 {placed} ≠ {shortfall.placed}")
        floor = -min(row.general_target for row in inputs)
        if best is None or best < floor - 1e-12:
            if not brute.has_candidates:
                cause = "window"
            elif (
                conditions.concurrent is not None
                and best_free is not None
                and best_free >= floor - 1e-12
            ):
                cause = "concurrent"
            else:
                cause = "capacity"
            if shortfall.relief is not None or shortfall.cause != cause:
                problems.append(f"까닭 {cause} ≠ {shortfall.relief}·{shortfall.cause}")
        elif shortfall.relief is None or abs(shortfall.relief - (margin - best)) > 1e-6:
            problems.append(f"필요 완화 {margin - best} ≠ {shortfall.relief}")
    return problems


def _next_month(month: int) -> int:
    year, number = divmod(month, 100)
    return (year + 1) * 100 + 1 if number == 12 else month + 1


def _real_case(rng: random.Random) -> tuple[list[ScheduleMonthInput], ScheduleConditions] | None:
    """실수 R·A·G · 여유 · 기한 · 목적 · 동시 상한 · Cut-off · 달 맞춤 · 늦은 시작(검토 탐침
    probe1)."""
    first = rng.choice([year * 100 + month for year in (2026, 2027) for month in range(1, 13)])
    months = [first]
    for _ in range(rng.choice([2, 3]) - 1):
        months.append(_next_month(months[-1]))
    cutoff = rng.choice([0, 0, 5, 9])
    inputs: list[ScheduleMonthInput] = []
    for month in months:
        required = 0.0 if rng.random() < 0.1 else rng.uniform(1, 8)
        target = rng.choice([1.0, 1.05, 1.095, 1.1])
        available = (
            max(target * required + rng.uniform(-0.3, 3.0), 0.0)
            if required > 0
            else rng.uniform(0, 4)
        )
        inputs.append(ScheduleMonthInput(month, required, available, target))
    fleet = max(math.floor(row.available + 1e-9) for row in inputs)
    if fleet < 1:
        return None
    units = min(rng.randint(1, 3 if len(months) == 2 else 2), fleet)
    days = rng.randint(3, 40)
    concurrent = rng.choice([1, 2, None, None])
    margin = rng.choice([0.0, 0.0, 0.02])
    head = wd_window(months[0], cutoff)
    tail = wd_window(months[-1], cutoff)
    deadline = (
        head.first_day + timedelta(days=rng.randint(0, (tail.boundary_end - head.first_day).days))
        if rng.random() < 0.5
        else None
    )
    objective: Objective = "even" if deadline is not None and rng.random() < 0.5 else "earliest"
    earliest = head.first_day + timedelta(days=rng.choice([0, 0, 0, rng.randint(0, 20)]))
    return inputs, ScheduleConditions(
        units=units,
        days=days,
        cutoff_days=cutoff,
        earliest=earliest,
        deadline=deadline,
        concurrent=concurrent,
        margin=margin,
        objective=objective,
        aligned=rng.random() < 0.15,
    )


def _wide_case(rng: random.Random) -> tuple[list[ScheduleMonthInput], ScheduleConditions]:
    """두 달 · 3대 · 한 달 예산 0 ~ 3W 대·일(검토 탐침 probe5 — 이른 시작이 몰아 넣어 못 넣는
    자리)."""
    first = rng.choice([year * 100 + month for year in (2026, 2027) for month in range(1, 13)])
    months = [first, _next_month(first)]
    inputs = [
        _budget_month(month, rng.randint(0, 3 * wd_window(month, 0).days)) for month in months
    ]
    return inputs, ScheduleConditions(
        units=3,
        days=rng.randint(15, 40),
        cutoff_days=0,
        earliest=wd_window(first, 0).first_day,
        concurrent=rng.choice([None, None, 2, 3]),
    )


@pytest.mark.parametrize(("seed", "wide"), [(31, False), (32, False), (33, True), (34, True)])
def test_the_service_matches_a_brute_force_search(seed: int, wide: bool) -> None:
    rng = random.Random(seed)
    checked = 0
    mismatches: list[tuple[object, ...]] = []
    while checked < (25 if wide else 50):
        case = _wide_case(rng) if wide else _real_case(rng)
        if case is None:
            continue
        checked += 1
        problems = _brute_check(*case)
        if problems:
            mismatches.append((case[1], problems))
    assert mismatches == []


# ------------------------------------------------------------------ 어댑터


def _plan_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Saw ", "Saw", "Bond", "Saw"],
            "생산계획년월": [202701, 202702, 202701, 202703],
            "소요대수": [10.0, 12.0, 3.0, 9.0],
            "가용대수": [11.0, 13.5, 4.0, 10.0],
            "단축대수": [1.0, 0.0, 0.0, 0.0],
        }
    )


def test_the_adapter_reads_the_process_months_and_the_monthly_target() -> None:
    inputs = schedule_month_inputs(
        _plan_frame(),
        process="Saw",
        months=[JAN, FEB],
        general_target=lambda month: 1.1 if month == FEB else 1.05,
    )

    assert inputs == (
        ScheduleMonthInput(JAN, 10.0, 11.0, 1.05),
        ScheduleMonthInput(FEB, 12.0, 13.5, 1.1),
    )


def test_the_adapter_rejects_a_missing_process_or_month() -> None:
    with pytest.raises(KeyError, match="공정 「Grind」"):
        schedule_month_inputs(_plan_frame(), process="Grind", months=[JAN], general_target=float)
    with pytest.raises(ValueError, match="202704"):
        schedule_month_inputs(
            _plan_frame(), process="Saw", months=[JAN, 202704], general_target=lambda _: 1.0
        )
    duplicated = pd.concat([_plan_frame(), _plan_frame().iloc[[1]]], ignore_index=True)
    with pytest.raises(ValueError, match="둘 이상"):
        schedule_month_inputs(duplicated, process="Saw", months=[JAN], general_target=lambda _: 1.0)
