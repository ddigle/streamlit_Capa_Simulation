# Purpose: 접속 명단 편집 표의 저장 판(빼기 · 등급 바꿈 · 넣기)과 저장을 막는 문제 수를 본다.

"""`services/access_list_plan` — 초안만 읽어 저장할 일과 문제 수를 낸다(값은 문제 글에 싣지 않는다).
값은 모두 합성(`demo.*`)이다."""

from __future__ import annotations

from capa_simulation.auth import grades
from capa_simulation.services import access_list_plan as plan
from capa_simulation.services.edit_grid import ROW_REMOVED, DraftState

LISTED = {"demo.a": grades.VIEWER, "demo.b": grades.EDITOR, "demo.me": grades.DEVELOPER}
FRESH = ("+1", "+2", "+3", "+4", "+5", "+6")


def _plan(
    draft: DraftState | None, locked: frozenset[str] = frozenset({"demo.me"})
) -> plan.AccessPlan:
    return plan.plan_changes(draft, listed=LISTED, fresh=FRESH, locked=locked)


def test_no_draft_is_an_empty_plan() -> None:
    result = _plan(None)
    assert result.empty and not result.problems.any


def test_removal_beats_a_grade_change_and_unchanged_grades_are_not_written() -> None:
    draft: DraftState = {
        "cells": {
            "demo.a": {ROW_REMOVED: 1.0, plan.GRADE_COLUMN: 2.0},
            "demo.b": {plan.GRADE_COLUMN: 1.0},
            "gone.person": {ROW_REMOVED: 1.0},
        },
        "bad": {},
    }
    result = _plan(draft)
    assert result.removed == ("demo.a",), "표에 없는 사람은 읽지 않는다"
    assert dict(result.graded) == {}, "실무자 → 실무자는 쓸 일이 아니다"
    assert not result.problems.any


def test_new_rows_become_people_grouped_by_grade_with_their_row_keys() -> None:
    draft: DraftState = {
        "cells": {
            "+1": {
                plan.ACCOUNT_COLUMN: "Demo.New",
                plan.NAME_COLUMN: "데모 나",
                plan.GRADE_COLUMN: 2.0,
            },
            "+3": {plan.ACCOUNT_COLUMN: "demo.c", plan.GRADE_COLUMN: 1.0},
            "+4": {
                plan.ACCOUNT_COLUMN: "demo.d",
                plan.GRADE_COLUMN: 1.0,
                plan.DEPT_COLUMN: "DEMO 팀",
            },
            "demo.b": {plan.GRADE_COLUMN: 3.0},
        },
        "bad": {},
    }
    result = _plan(draft)
    assert not result.problems.any
    assert dict(result.graded) == {"demo.b": grades.DEVELOPER}
    groups = result.added_by_grade()
    assert list(groups) == [grades.EDITOR, grades.MANAGER], "낮은 등급부터"
    assert [(p.loginid, p.row) for p in groups[grades.EDITOR]] == [
        ("demo.c", "+3"),
        ("demo.d", "+4"),
    ]
    (new,) = groups[grades.MANAGER]
    assert (new.loginid, new.name, new.dept, new.row) == ("demo.new", "데모 나", "", "+1")


def test_every_problem_is_counted_and_blocks_the_save_without_values() -> None:
    draft: DraftState = {
        "cells": {
            "+1": {plan.NAME_COLUMN: "이름만"},
            "+2": {plan.ACCOUNT_COLUMN: "loginid", plan.GRADE_COLUMN: 1.0},
            "+3": {plan.ACCOUNT_COLUMN: "demo.a", plan.GRADE_COLUMN: 1.0},
            "+4": {plan.ACCOUNT_COLUMN: "demo.x", plan.GRADE_COLUMN: 1.0},
            "+5": {plan.ACCOUNT_COLUMN: "DEMO.X", plan.GRADE_COLUMN: 1.0},
            "+6": {plan.ACCOUNT_COLUMN: "demo.y"},
            "demo.b": {plan.GRADE_COLUMN: None},
            "demo.me": {plan.GRADE_COLUMN: 0.0, ROW_REMOVED: 1.0},
        },
        "bad": {"+1": {plan.ACCOUNT_COLUMN: ("bad name", "pattern")}},
    }
    result = _plan(draft)
    problems = result.problems
    assert problems == plan.Problems(
        errors=1, no_account=1, header=1, duplicate=2, no_grade=2, locked=1
    )
    text = problems.text()
    assert text.startswith("고칠 칸 1개 · 계정이 빈 새 줄 1개")
    for value in ("demo.a", "demo.x", "demo.y", "loginid 이"):
        assert value not in text
    assert result.removed == (), "잠긴 사람은 빼지 않는다"


def test_a_locked_cell_of_a_listed_person_in_the_draft_blocks_that_row() -> None:
    """명단 사람 줄의 계정 칸 등에 초안이 들었으면(표가 잠그고 계정이 다른 붙여넣기 줄은 건너뛰지만)
    그 줄은 고칠 수 없는 줄로 세고 등급을 쓰지 않는다."""
    draft: DraftState = {
        "cells": {
            "demo.a": {plan.ACCOUNT_COLUMN: "demo.b", plan.GRADE_COLUMN: 3.0},
            "demo.b": {plan.GRADE_COLUMN: 2.0},
        },
        "bad": {"demo.b": {plan.NAME_COLUMN: ("x" * 200, "length")}},
    }
    result = _plan(draft)
    assert result.problems.locked == 2
    assert dict(result.graded) == {}


def test_a_bad_account_is_caught_even_without_a_cell_error() -> None:
    draft: DraftState = {
        "cells": {"+1": {plan.ACCOUNT_COLUMN: "---", plan.GRADE_COLUMN: 1.0}},
        "bad": {},
    }
    assert _plan(draft).problems.bad_account == 1


def test_grade_values_map_back_to_the_four_grades() -> None:
    assert [plan.grade_at(float(at)) for at in range(4)] == list(grades.GRADES)
    assert plan.grade_at(None) is None and plan.grade_at(4.0) is None and plan.grade_at(1.5) is None
    assert plan.GRADE_OPTIONS == ("열람", "실무자", "관리자", "개발자")
    assert plan.fresh_key(3) == "+3" and plan.is_fresh("+3") and not plan.is_fresh("demo.a")
