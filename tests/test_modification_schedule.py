# Purpose: 개조 일정 서비스의 배치·기준 지킴·목적·대안 셋·어댑터를 손계산과 작은 완전 탐색으로 본다.

"""개조 일정(`services/modification_schedule.py`) 시험.

손계산은 Cut-off 0 이라 W/D 구간이 달력 달과 같은 꼴로 둔다(2027-01 = 1/1~1/31, 31일). 대부분 R = 10
· G = 100% 라 「확보율 ≥ 기준」 이 「그 달 비가동 대·일 ≤ (A − 10) × W」 와 같다 — A 11 이면 1월 31
대·일, 2월 28 대·일이 예산이다.

작은 무작위 문제(두~세 달, N ≤ 3, D 3~40일, 동시 상한 1·2·3·없음)를 완전 탐색과 맞대는 시험은 검토
문서(제약 시뮬레이션 2판 「개조 일정」 3-2)의 스크래치 대조를 옮긴 것이다 — 시드를 박아 늘 같은
문제를 본다. 예산 B 를 정수 대·일로 두고 A = 1 + (B + 0.5) ÷ W · R = 1 · G = 1 로 바꾸면 「대·일 ≤
B」 가 곧 판정이다(0.5 는 경계 잡음을 피하는 여유). 견주는 것은 **완료 W/D 달**이다 — 확보율이 달
평균이라 「몇 월에 끝나나」 가 답이고 날은 탐욕마다 다를 수 있다.
"""

from __future__ import annotations

import ast
import itertools
import random
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.constraint_simulation import secure
from capa_simulation.services.modification_schedule import (
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
    assert result.lowest_month == JAN and result.lowest_margin == 0.0
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
    months = [
        ScheduleMonthInput(month, 1.0, 1.0 + (budget + 0.5) / wd_window(month, 0).days, 1.0)
        for month, budget in budgets.items()
    ]
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
    result = _plan(months, units=2, days=31)

    assert _starts(result) == [(date(2027, 1, 1), 1)]
    assert result.month(JAN).rate is None and result.month(JAN).secure_after is None
    assert result.lowest_month is None
    shortfall = result.shortfall
    assert shortfall is not None and shortfall.placed == 1
    assert shortfall.by_deadline is False and shortfall.finish_without_deadline is None
    # 기준을 0 까지 낮춰도 가용이 모자라 들어가지 않는다.
    assert shortfall.relief is None


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


def test_the_even_objective_raises_the_lowest_month_as_high_as_possible() -> None:
    """1대 × 10일 · 기한 3/31 — 1월 5 · 2월 5 일로 나누면 2월이 1.1 − 5/280 = 108.21% 로 가장 높다
    (1월만 10일이면 106.77%, 1월 6 · 2월 4 면 1월 108.06%)."""
    result = _plan(_three(), units=1, days=10, deadline=date(2027, 3, 31), objective="even")

    best = 0.1 - 5 / 280
    assert result.applied_margin == pytest.approx(best, abs=1e-6)
    assert _starts(result) == [(date(2027, 1, 27), 1)]
    assert result.lowest_month == FEB
    assert result.lowest_margin == pytest.approx(best, abs=1e-9)
    assert result.month(FEB).threshold == pytest.approx(1.0 + best, abs=1e-6)
    # 올린 δ 때문에만 비는 달은 「개조 없이도 미달」 이 아니다.
    assert not any(row.blocked for row in result.months)
    _assert_keeps_every_month(result)


def test_the_even_objective_falls_back_with_alternatives_when_the_margin_alone_misses() -> None:
    result = _plan(_three(), units=2, days=31, deadline=date(2027, 2, 28), objective="even")

    assert result.applied_margin == 0.0
    assert result.shortfall is not None and result.shortfall.placed == 1


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


# ------------------------------------------------------------------ 완전 탐색 대조


def _brute_finish(
    lengths: list[int],
    budgets: list[int],
    units: int,
    days: int,
    concurrent: int | None,
    pool: list[int],
) -> int | None:
    """가장 이른 완료 달 차례(없으면 None) — 마지막 시작을 앞에서부터 늘리며 처음 되는 것."""
    owner = [index for index, length in enumerate(lengths) for _ in range(length)]
    overlaps: dict[int, list[int]] = {}
    for start in pool:
        counts = [0] * len(lengths)
        for day in range(start, start + days):
            counts[owner[day]] += 1
        overlaps[start] = counts
    for position, last in enumerate(pool):
        for rest in itertools.combinations_with_replacement(pool[: position + 1], units - 1):
            starts = (*rest, last)
            use = [sum(overlaps[start][index] for start in starts) for index in range(len(lengths))]
            if any(spent > budget for spent, budget in zip(use, budgets, strict=True)):
                continue
            if concurrent is not None:
                # 길이가 같은 구간은 서로 겹치면 한 점을 함께 지난다 — 시작이 D 일 안인 묶음 크기가
                # 동시.
                busiest = max(
                    sum(1 for other in starts if 0 <= other - start < days) for start in starts
                )
                if busiest > concurrent:
                    continue
            return owner[last + days - 1]
    return None


def _next_month(month: int) -> int:
    year, number = divmod(month, 100)
    return (year + 1) * 100 + 1 if number == 12 else month + 1


@pytest.mark.parametrize(("seed", "aligned"), [(11, False), (12, False), (13, False), (14, True)])
def test_the_completion_month_matches_a_brute_force_search(seed: int, aligned: bool) -> None:
    rng = random.Random(seed)
    checked = 0
    mismatches: list[tuple[object, ...]] = []
    while checked < 40:
        first = rng.choice(
            [year * 100 + month for year in (2026, 2027, 2028) for month in range(1, 13)]
        )
        months = [first]
        for _ in range(rng.choice([2, 3]) - 1):
            months.append(_next_month(months[-1]))
        lengths = [wd_window(month, 0).days for month in months]
        budgets = [rng.randint(0, 50) for _ in months]
        units = rng.randint(1, 3 if len(months) == 2 else 2)
        days = rng.randint(3, 40)
        concurrent = rng.choice([1, 2, 3, None])
        if days > sum(lengths):
            continue
        checked += 1
        if aligned:
            ends = list(itertools.accumulate(lengths))
            pool = [end - days for end in ends if end - days >= 0]
        else:
            pool = list(range(sum(lengths) - days + 1))
        expected = _brute_finish(lengths, budgets, units, days, concurrent, pool)
        inputs = [
            ScheduleMonthInput(month, 1.0, 1.0 + (budget + 0.5) / length, 1.0)
            for month, budget, length in zip(months, budgets, lengths, strict=True)
        ]
        result = plan_modification_schedule(
            inputs,
            ScheduleConditions(
                units=units,
                days=days,
                cutoff_days=0,
                earliest=wd_window(first, 0).first_day,
                concurrent=concurrent,
                aligned=aligned,
            ),
        )
        _assert_keeps_every_month(result)
        if concurrent is not None:
            assert result.max_concurrent <= concurrent
        got = months.index(result.finish_month) if result.finish_month is not None else None
        if got != expected:
            mismatches.append((months, budgets, units, days, concurrent, expected, got))
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
