# Purpose: 누적 진척 기록 · 목표의 주차 차례 · 머리 요약 · 값 규칙 · 화면 합계 · 저장 대조를 본다.

"""필요 단축 일정 「누적 진척」(`services/shortening_progress_log.py` · 설비 DB `0036`).

일수는 합성 예시(DEMO)다 — 142 → 131 → 138 → 96 처럼 손으로 셀 수 있게 잡았다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from test_required_shortening import JUNE, MAY, _plan, _unit
from test_shortening_progress import DA, LG, _frame, _real, _virtual

from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.required_shortening import LEVEL_COLUMN
from capa_simulation.services.shortening_baseline import freeze_plan
from capa_simulation.services.shortening_progress import compare_progress, summarize_progress
from capa_simulation.services.shortening_progress_log import (
    ProgressEntry,
    ProgressGoal,
    ProgressGoalState,
    ProgressLog,
    ProgressLogConflictError,
    ProgressLogInvalidError,
    ProgressWeek,
    goal_week_options,
    normalize_progress_days,
    record_week_options,
    screen_shortening_days,
    summarize_log,
)

TODAY = date(2026, 11, 20)  # 26-W47
W47 = ProgressWeek(2026, 47)


def _log(*pairs: tuple[ProgressWeek, int], goal: ProgressGoal | None = None) -> ProgressLog:
    return ProgressLog(
        entries=tuple(ProgressEntry(week, days) for week, days in pairs),
        goal=ProgressGoalState(goal=goal, version=0 if goal is None else 1),
    )


# ------------------------------------------------------------------ 주차


def test_weeks_follow_the_iso_year_across_new_year() -> None:
    """해 넘김 — 25-W52 → 26-W01 이 (해, 주) 차례로 맞고 글은 앱 주차 도우미의 `YY-W##` 다."""
    last = ProgressWeek.of(date(2025, 12, 24))
    first = ProgressWeek.of(date(2026, 1, 1))
    assert (last.label, first.label) == ("25-W52", "26-W01")
    assert last < first and last.shifted(1) == first
    assert last.weeks_until(first) == 1
    assert ProgressWeek.parse("26-w01") == first
    # 2026-01-01 은 ISO 2026 1주(목요일)다 — 달력 해가 아니라 ISO 해다.
    assert ProgressWeek.of(date(2027, 1, 1)) == ProgressWeek(2026, 53)


@pytest.mark.parametrize("year_week", [(2025, 53), (2026, 0), (2026, 54)])
def test_a_week_that_does_not_exist_is_refused(year_week: tuple[int, int]) -> None:
    with pytest.raises(ProgressLogInvalidError):
        ProgressWeek(*year_week)


def test_the_record_weeks_go_back_a_year_and_keep_older_records() -> None:
    old = ProgressWeek(2024, 10)
    options = record_week_options(TODAY, [ProgressEntry(old, 5)])
    assert options[0] == W47, "이번 주가 맨 앞이다"
    assert options[52] == W47.shifted(-52)
    assert options[-1] == old
    assert all(week <= W47 for week in options), "앞날의 주는 없다"


def test_the_goal_weeks_reach_two_years_ahead_and_keep_a_saved_goal() -> None:
    options = goal_week_options(TODAY, ProgressGoal(30, ProgressWeek(2030, 1)))
    assert options[0] == W47.shifted(-26)
    assert W47.shifted(104) in options
    assert options[-1] == ProgressWeek(2030, 1)


# ------------------------------------------------------------------ 머리 요약


def test_no_record_has_no_numbers() -> None:
    headline = summarize_log(_log(), TODAY)
    assert (headline.latest, headline.change, headline.remaining, headline.progress) == (
        None,
        None,
        None,
        None,
    )


def test_one_record_has_no_change_rather_than_zero() -> None:
    headline = summarize_log(_log((W47, 96)), TODAY)
    assert headline.latest is not None and headline.latest.days == 96
    assert headline.change is None


def test_the_headline_reads_the_records_and_the_goal() -> None:
    """지금 일수 · 지난 기록 대비는 마지막 기록과 그 앞 기록(기록 기준) — 순서는 넣은 차례가 아니라
    주차다."""
    log = _log(
        (W47, 96),
        (W47.shifted(-7), 142),
        (W47.shifted(-1), 115),
        goal=ProgressGoal(30, W47.shifted(5)),
    )
    headline = summarize_log(log, TODAY)
    assert headline.first is not None and headline.first.days == 142
    assert headline.change == 96 - 115
    assert headline.remaining == 66 and not headline.reached and not headline.overdue
    assert headline.progress == pytest.approx((142 - 96) / (142 - 30))
    assert log.changes() == (None, 115 - 142, 96 - 115)


def test_a_goal_reached_or_passed_by_week() -> None:
    reached = summarize_log(
        _log((W47.shifted(-1), 40), (W47, 28), goal=ProgressGoal(30, W47)), TODAY
    )
    assert reached.reached and reached.progress == 1.0 and not reached.overdue
    late = summarize_log(
        _log((W47.shifted(-3), 80), (W47.shifted(-1), 60), goal=ProgressGoal(30, W47.shifted(-2))),
        TODAY,
    )
    assert late.remaining == 30 and late.overdue


@pytest.mark.parametrize(("value", "days"), [(0, 0), ("12", 12), (12.0, 12)])
def test_days_are_whole_and_not_negative(value: object, days: int) -> None:
    assert normalize_progress_days(value) == days


@pytest.mark.parametrize("value", [None, -1, 1.5, "x", 100_000])
def test_days_outside_the_rule_are_refused(value: object) -> None:
    with pytest.raises(ProgressLogInvalidError):
        normalize_progress_days(value)


# ------------------------------------------------------------------ 화면 합계


def test_the_screen_total_sums_pulled_units_in_scope_only() -> None:
    units = _frame(
        [
            _real(LG, "LG-01", date(2026, 3, 1), date(2026, 3, 11)),
            _real(LG, "LG-02", date(2026, 3, 5), date(2026, 3, 9)),
            _real(DA, "DA-01", date(2026, 3, 1), date(2026, 4, 1)),
            _virtual(LG, "추가1", date(2026, 3, 20)),
        ]
    )
    assert screen_shortening_days(units, [LG, DA]) == 10 + 4 + 31
    assert screen_shortening_days(units, [LG]) == 14, "범위 밖 공정 · 가상 호기는 빠진다"
    assert screen_shortening_days(units.iloc[0:0], [LG]) == 0


def test_the_screen_total_is_the_progress_total_plus_the_lapsed_days() -> None:
    """진척 비교 요약의 지금 합계는 필요 시점 지남 행을 따로 빼 둔다 — 화면 합계는 그 둘의
    합이다."""
    units = [
        _unit("A1", date(2026, 5, 1)),
        _unit("B2", date(2026, 5, 31)),
        _unit("C3", date(2026, 6, 15)),
    ]
    required = {MAY: 12 + 20 / 31, JUNE: 12 + 20 / 31}
    then = _plan(units, required, today=date(2026, 4, 1))
    now = _plan(units, required, today=date(2026, 5, 25))
    frozen = freeze_plan(then, name="이전").units
    past = frozen.loc[frozen[LEVEL_COLUMN].eq(100)].drop(columns=LEVEL_COLUMN)
    current = now.at(1.0).units
    rows = compare_progress(past, current, current_processes=now.processes, today=now.today)
    summary = summarize_progress(rows, now.processes)
    assert summary.lapsed > 0
    assert screen_shortening_days(current, now.processes) == (
        summary.current_days + summary.lapsed_current_days
    )


# ------------------------------------------------------------------ 저장 왕복 · 대조


@pytest.fixture()
def repository(tmp_path: Path) -> DuckDBEquipmentRepository:
    repo = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repo.initialize()
    return repo


def test_a_record_is_added_edited_and_deleted_against_what_was_seen(
    repository: DuckDBEquipmentRepository,
) -> None:
    assert repository.load_shortening_progress_log() == ProgressLog()
    assert repository.save_shortening_progress_entry(
        W47, 96, expected_days=None, recorded_by=" DEMO 사원 "
    )
    assert repository.save_shortening_progress_entry(W47.shifted(-1), "115", expected_days=None)
    log = repository.load_shortening_progress_log()
    assert [(entry.week, entry.days) for entry in log.entries] == [
        (W47.shifted(-1), 115),
        (W47, 96),
    ]
    assert log.entries[1].recorded_by == "DEMO 사원"

    # 같은 값(빠른 둘째 누름)은 쓰지 않는다.
    assert not repository.save_shortening_progress_entry(W47, 96, expected_days=None)
    # 고치기 — 본 값이 지금 값과 같아야 한다.
    assert repository.save_shortening_progress_entry(W47, 90, expected_days=96)
    with pytest.raises(ProgressLogConflictError, match="26-W47"):
        repository.save_shortening_progress_entry(W47, 80, expected_days=96)
    with pytest.raises(ProgressLogConflictError):
        repository.delete_shortening_progress_entry(W47, expected_days=96)
    assert repository.load_shortening_progress_log().days_of(W47) == 90

    assert repository.delete_shortening_progress_entry(W47, expected_days=90)
    assert not repository.delete_shortening_progress_entry(W47, expected_days=90)
    with pytest.raises(ProgressLogInvalidError):
        repository.save_shortening_progress_entry(W47, -3, expected_days=None)
    assert repository.load_shortening_progress_log().days_of(W47) is None


def test_the_goal_is_one_shared_value_checked_by_version(
    repository: DuckDBEquipmentRepository,
) -> None:
    goal = ProgressGoal(30, ProgressWeek(2026, 52))
    assert repository.save_shortening_progress_goal(goal, expected_version=0, saved_by="DEMO") == 1
    state = repository.load_shortening_progress_log().goal
    assert (state.goal, state.version, state.saved_by) == (goal, 1, "DEMO")

    assert repository.save_shortening_progress_goal(goal, expected_version=1) is None
    with pytest.raises(ProfileVersionConflict):
        repository.save_shortening_progress_goal(ProgressGoal(25, goal.week), expected_version=0)
    # 지우기는 행을 남기고 version 을 올린다 — 목표선이 없어진다.
    assert repository.save_shortening_progress_goal(None, expected_version=1) == 2
    state = repository.load_shortening_progress_log().goal
    assert (state.goal, state.version) == (None, 2)
