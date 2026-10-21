# Purpose: 반입·Qual 단계의 일정·실적·상태를 맞댄 미확인·실적 누락·상태 갱신 필요 알림을 검증한다.

"""일정 확인 알림(2026-10-16 사용자 결정 3).

- **미확인** — 상태 계획·확정 + 실적 공백 + **일정 < 오늘**. 일정 당일은 아직 아니고 다음 날부터다.
- **실적 누락** — 상태 완료 + 실적 공백.
- **상태 갱신 필요** — 실적이 있는데 상태가 계획·확정.

오늘을 인자로 받는다 — 검증(`prepare_*`)에 두면 날이 지나 저장 때 통과한 리비전이 깨진다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.schedule_confirmation import (
    CONFIRMATION_COLUMNS,
    CONFIRMATION_KINDS,
    MISSING_ACTUAL,
    STATUS_UPDATE_NEEDED,
    UNCONFIRMED,
    confirmation_counts,
    flagged_equipment,
    schedule_confirmation_issues,
    schedule_confirmation_notice,
    unconfirmed_issues,
)

TODAY = date(2026, 10, 16)


def _unit(name: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update({"설비명": name, "공정소분류": "DEMO_P", "기존설비여부": "N", "보관유무": "N"})
    row.update(overrides)
    return row


def _master(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(EQUIPMENT_COLUMNS))


def _kinds(issues: pd.DataFrame) -> list[tuple[str, str, str]]:
    return list(zip(issues["설비명"], issues["확인구분"], issues["단계"], strict=True))


@pytest.mark.parametrize(
    ("days_after_schedule", "flagged"),
    [(-1, False), (0, False), (1, True), (30, True)],
)
@pytest.mark.parametrize("status", ["계획", "확정"])
def test_an_open_stage_is_unconfirmed_from_the_day_after_its_schedule(
    days_after_schedule: int, flagged: bool, status: str
) -> None:
    """일정 당일은 아직 진행 중일 수 있다 — 다음 날부터 미확인이다."""
    schedule = TODAY - timedelta(days=days_after_schedule)
    master = _master(
        _unit("ARR", 반입일정=schedule.isoformat(), 반입상태=status),
        _unit("QUAL", Qual일정=schedule.isoformat(), Qual상태=status),
    )

    issues = schedule_confirmation_issues(master, today=TODAY)

    expected = [("ARR", UNCONFIRMED, "반입"), ("QUAL", UNCONFIRMED, "Qual")] if flagged else []
    assert _kinds(issues) == expected


def test_moving_today_forward_turns_a_plan_into_unconfirmed() -> None:
    """같은 표라도 오늘이 바뀌면 답이 바뀐다 — 그래서 검증이 아니라 따로 둔 알림이다."""
    master = _master(_unit("EQ-1", 반입일정="2026-10-20", 반입상태="확정"))

    assert schedule_confirmation_issues(master, today=date(2026, 10, 20)).empty
    later = schedule_confirmation_issues(master, today=date(2026, 10, 21))
    assert _kinds(later) == [("EQ-1", UNCONFIRMED, "반입")]
    assert later.loc[0, "일정"] == pd.Timestamp("2026-10-20")
    assert pd.isna(later.loc[0, "실적"])
    assert later.loc[0, "상태"] == "확정"


@pytest.mark.parametrize("status", ["완료", "지연", None])
def test_other_statuses_are_not_unconfirmed(status: str | None) -> None:
    """완료(실적 누락은 따로)·지연(Space 빨강이 맡는다)·빈칸은 미확인이 아니다."""
    master = _master(_unit("EQ-1", Qual일정="2026-01-01", Qual상태=status))

    issues = schedule_confirmation_issues(master, today=TODAY)

    assert UNCONFIRMED not in set(issues["확인구분"])


def test_a_recorded_actual_clears_unconfirmed_but_asks_for_a_status_update() -> None:
    master = _master(
        _unit("EQ-1", 반입일정="2026-09-01", 반입실적="2026-09-03", 반입상태="확정"),
        _unit("EQ-2", Qual일정="2026-09-10", Qual실적="2026-09-12", Qual상태="완료"),
        _unit("EQ-3", Qual일정="2026-09-10", Qual실적="2026-09-12", Qual상태="계획"),
    )

    issues = schedule_confirmation_issues(master, today=TODAY)

    assert _kinds(issues) == [
        ("EQ-1", STATUS_UPDATE_NEEDED, "반입"),
        ("EQ-3", STATUS_UPDATE_NEEDED, "Qual"),
    ]


def test_a_done_stage_without_an_actual_is_a_missing_actual() -> None:
    master = _master(
        _unit("EQ-1", 반입일정="2026-12-01", 반입상태="완료"),
        _unit("EQ-2", Qual상태="완료"),
    )

    issues = schedule_confirmation_issues(master, today=TODAY)

    # 일정과 상관없이 고른다 — 일정이 없어도, 앞으로여도 완료인데 실적이 비면 누락이다.
    assert _kinds(issues) == [("EQ-1", MISSING_ACTUAL, "반입"), ("EQ-2", MISSING_ACTUAL, "Qual")]


def test_rows_are_ordered_by_kind_stage_and_schedule() -> None:
    master = _master(
        _unit("B", 반입일정="2026-09-02", 반입상태="계획", Qual상태="완료"),
        _unit("A", 반입일정="2026-09-05", 반입상태="계획", Qual일정="2026-09-01", Qual상태="계획"),
        _unit("C", 반입일정="2026-09-01", 반입실적="2026-09-01", 반입상태="계획"),
    )

    issues = schedule_confirmation_issues(master, today=TODAY)

    assert tuple(issues.columns) == CONFIRMATION_COLUMNS
    assert _kinds(issues) == [
        ("B", UNCONFIRMED, "반입"),
        ("A", UNCONFIRMED, "반입"),
        ("A", UNCONFIRMED, "Qual"),
        ("B", MISSING_ACTUAL, "Qual"),
        ("C", STATUS_UPDATE_NEEDED, "반입"),
    ]
    assert issues["공정소분류"].tolist() == ["DEMO_P"] * 5
    # 미확인 하나만 묻는 길(Space 「!」)은 같은 행을 같은 칸·차례로 낸다.
    only = unconfirmed_issues(master, today=TODAY)
    expected = issues.loc[issues["확인구분"].eq(UNCONFIRMED)].reset_index(drop=True)
    pd.testing.assert_frame_equal(only, expected)


def test_counts_are_units_and_a_unit_late_on_both_stages_counts_once() -> None:
    master = _master(
        _unit("A", 반입일정="2026-09-05", 반입상태="계획", Qual일정="2026-09-20", Qual상태="확정"),
        _unit("B", 반입일정="2026-09-05", 반입상태="확정", 공정소분류="DEMO_Q"),
    )
    issues = schedule_confirmation_issues(master, today=TODAY)

    assert confirmation_counts(issues) == {
        UNCONFIRMED: 2,
        MISSING_ACTUAL: 0,
        STATUS_UPDATE_NEEDED: 0,
    }
    assert confirmation_counts(issues, processes=["DEMO_Q"])[UNCONFIRMED] == 1
    assert confirmation_counts(issues, unit_ids=["A"])[UNCONFIRMED] == 1
    assert flagged_equipment(issues) == frozenset({"A", "B"})
    assert flagged_equipment(issues, MISSING_ACTUAL) == frozenset()
    notice = schedule_confirmation_notice(issues)
    assert notice is not None
    assert notice.startswith("미확인 2대 (반입 2 · Qual 1) — ")
    assert schedule_confirmation_notice(issues, processes=["없는 공정"]) is None


def test_modules_of_one_unit_count_as_one_unit_but_are_flagged_box_by_box() -> None:
    """대수 축은 행이 아니라 설비를 센다 — Main 설비로 묶은 모듈 넷이 걸려도 「미확인 1대」다.
    모듈 하나만 걸려도 그 설비 한 대다(확인할 대상의 수라 몫으로 나누지 않는다). 「!」는
    상자마다다."""
    late = {"반입일정": "2026-10-01", "반입상태": "확정", "Main 설비": "APW01"}
    master = _master(
        *(_unit(f"APW01{module}", **late) for module in "ABCD"),
        _unit("APW02A", **{**late, "Main 설비": "APW02"}),
        _unit("APW02B", **{"반입일정": "2026-10-01", "반입상태": "완료", "Main 설비": "APW02"}),
        _unit("EQ-1", 반입일정="2026-10-01", 반입상태="계획"),
    )

    issues = schedule_confirmation_issues(master, today=TODAY)

    assert issues.loc[issues["설비명"].eq("APW01C"), "설비키"].tolist() == ["APW01"]
    assert issues.loc[issues["설비명"].eq("EQ-1"), "설비키"].tolist() == ["EQ-1"]
    assert confirmation_counts(issues) == {
        UNCONFIRMED: 3,
        MISSING_ACTUAL: 1,
        STATUS_UPDATE_NEEDED: 0,
    }
    notice = schedule_confirmation_notice(issues)
    assert notice is not None
    assert notice.startswith("미확인 3대 (반입 3) — ")
    # 호기 필터가 모듈 하나만 골라도 그 설비 한 대다.
    assert confirmation_counts(issues, unit_ids=["APW01B", "APW01C"])[UNCONFIRMED] == 1
    assert flagged_equipment(issues) == frozenset(
        {"APW01A", "APW01B", "APW01C", "APW01D", "APW02A", "EQ-1"}
    )


def test_an_unknown_kind_is_refused() -> None:
    assert set(CONFIRMATION_KINDS) == {UNCONFIRMED, MISSING_ACTUAL, STATUS_UPDATE_NEEDED}
    with pytest.raises(ValueError, match="확인구분"):
        flagged_equipment(schedule_confirmation_issues(_master(), today=TODAY), "지연")


def test_an_unvalidated_buffer_and_an_old_frame_are_read_without_errors() -> None:
    """검증 전 편집본도 받는다 — 못 읽는 날짜는 빈 칸, 설비명이 빈 행은 버린다. 실적·반입상태 칸이
    없던 옛 표는 걸리는 것이 없다(Qual상태만으로는 실적을 알 수 없다)."""
    buffer = pd.DataFrame(
        {
            "설비명": [" EQ-1 ", "", None, "EQ-4"],
            "공정소분류": ["P", "P", "P", "P"],
            "반입일정": ["2026-09-01", "2026-09-01", "2026-09-01", "언젠가"],
            "반입실적": ["", None, None, None],
            "반입상태": [" 계획 ", "계획", "계획", "확정"],
        }
    )
    old = buffer.drop(columns=["반입실적", "반입상태"]).assign(Qual상태="확정")

    issues = schedule_confirmation_issues(buffer, today=TODAY)

    assert _kinds(issues) == [("EQ-1", UNCONFIRMED, "반입")]
    assert schedule_confirmation_issues(old, today=TODAY).empty
    assert schedule_confirmation_issues(pd.DataFrame(), today=TODAY).empty
