# Purpose: 목록·리비전 편집표의 초안 접기와 저장소 일괄 이름·순서 쓰기(전부 아니면 전무)를 잰다.

"""시나리오 관리 C안의 두 층.

- 초안 접기(`components/pick_edit_table.py`): 브라우저의 행 위치 편집을 행 id 로 접는다 — 고름은
  하나, 순서 칸은 끼워 넣기, 두 번 접어도 같다, 저장된 행에 맞춘다.
- 저장소: 목록 이름·순서(`apply_scenario_list_edits`)와 리비전명(`rename_revisions`)을 한
  트랜잭션으로 쓰고 하나라도 거부되면 아무것도 쓰지 않는다. 가상 제품 수는 리비전 id 목록으로
  한 번에 센다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.components.pick_edit_table import (
    TableColumns,
    TableDraft,
    changed_names,
    drop_names,
    fold_edits,
    move_row,
    moved_count,
    moved_names,
    reconcile,
    with_order,
)
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import (
    DUPLICATE_SCENARIO_NAME_MESSAGE,
    SCENARIO_LIST_MOVED_MESSAGE,
    BatchEditRefused,
    DuckDBScenarioRepository,
)

COLUMNS = TableColumns(pick="선택", name="이름", order="순서")
ROWS = ("a", "b", "c")
NAMES = {"a": "가", "b": "나", "c": "다"}


def test_a_second_check_keeps_only_the_newly_picked_row_and_the_name_edits() -> None:
    """두 줄이 골라지면 초안의 고른 줄이 아닌 쪽만 남기고 표를 다시 세운다. 이름 편집은 남는다."""
    draft = TableDraft(picked="a")
    folded, remount = fold_edits(
        draft, ROWS, NAMES, {1: {"선택": True}, 2: {"이름": " 새 다 "}}, COLUMNS
    )
    assert remount
    assert folded == TableDraft(names={"c": "새 다"}, name_base={"c": "다"}, picked="b")


def test_unchecking_then_checking_another_row_needs_no_remount() -> None:
    draft = TableDraft(picked="a")
    folded, remount = fold_edits(
        draft, ROWS, NAMES, {0: {"선택": False}, 2: {"선택": True}}, COLUMNS
    )
    assert not remount
    assert folded.picked == "c"
    folded, remount = fold_edits(draft, ROWS, NAMES, {0: {"선택": False}}, COLUMNS)
    assert not remount and folded.picked is None


def test_a_name_set_back_to_the_stored_one_is_no_edit() -> None:
    draft = TableDraft(names={"b": "임시"})
    folded, _ = fold_edits(draft, ROWS, NAMES, {1: {"이름": "나"}}, COLUMNS)
    assert folded.names == {}
    # 빈 칸은 고친 것이다 — 저장할 때 저장소가 「비어 있을 수 없습니다」로 거절한다.
    folded, _ = fold_edits(draft, ROWS, NAMES, {1: {"이름": None}}, COLUMNS)
    assert changed_names(folded, NAMES) == {"b": ("나", "")}


def test_a_name_is_compared_with_the_name_seen_when_the_cell_was_first_edited() -> None:
    """이름은 비교 후 쓰기다 — 비교 대상은 그 칸을 처음 고친 편집이 붙은 표가 보인 저장 이름이다.

    마지막 회차에 다시 읽은 이름을 비교 대상으로 삼으면, 다른 곳에서 먼저 바뀐 뒤 회차가 한 번만 더
    돌아도 대조가 통과해 남의 변경을 알림 없이 덮는다(2026-10-22 리뷰).
    """
    # 표가 「나」를 보인 회차에 「새 나」로 고쳤다. 접는 회차에 이미 다른 곳에서 「남의 나」로
    # 바뀌었어도 비교 대상은 표가 보인 「나」다.
    moved = {**NAMES, "b": "남의 나"}
    folded, _ = fold_edits(TableDraft(), ROWS, moved, {1: {"이름": "새 나"}}, COLUMNS, NAMES)
    assert folded.name_base == {"b": "나"}
    assert changed_names(folded, moved) == {"b": ("나", "새 나")}
    assert moved_names(folded, moved) == {"b": "남의 나"}
    # 그 뒤 회차마다 같은 편집을 다시 접어도(그 표는 이제 「남의 나」를 보인다) 비교 대상은
    # 그대로다.
    again, _ = fold_edits(folded, ROWS, moved, {1: {"이름": "새 나"}}, COLUMNS, moved)
    assert again == folded
    # 지금 이름과 같게 고치면 쓸 것이 없다 — 비교 대상도 함께 지운다.
    same, _ = fold_edits(folded, ROWS, moved, {1: {"이름": "남의 나"}}, COLUMNS, moved)
    assert same.names == {} and same.name_base == {}
    # 거부된 행의 이름 편집을 버리면 다시 고칠 때 그때 보인 이름이 비교 대상이 된다.
    fresh, _ = fold_edits(
        drop_names(folded, ["b"]), ROWS, moved, {1: {"이름": "새 나"}}, COLUMNS, moved
    )
    assert changed_names(fresh, moved) == {"b": ("남의 나", "새 나")}
    assert moved_names(fresh, moved) == {}
    # 다른 곳에서 바뀐 이름이 내가 고친 이름과 같으면 쓸 것도, 막을 것도 없다.
    assert changed_names(folded, {**NAMES, "b": "새 나"}) == {}
    # 사라진 행의 비교 대상은 초안에서 빠진다.
    assert reconcile(folded, ("a", "c")) == TableDraft()


def test_a_place_number_inserts_the_row_and_folding_twice_is_the_same() -> None:
    """순서 칸 숫자는 그 자리로 끼워 넣기다. 처음 고치는 순서면 그 회차 차례를 기준으로 적는다."""
    folded, remount = fold_edits(TableDraft(), ROWS, NAMES, {2: {"순서": 1}}, COLUMNS)
    assert remount
    assert folded.order == ("c", "a", "b")
    assert folded.order_base == ROWS
    again, remount_again = fold_edits(TableDraft(), ROWS, NAMES, {2: {"순서": 1}}, COLUMNS)
    assert again == folded and remount_again
    # 같은 자리 번호는 움직이지 않는다.
    same, remount = fold_edits(TableDraft(), ROWS, NAMES, {1: {"순서": 2.0}}, COLUMNS)
    assert same.order is None and not remount


def test_reconcile_drops_gone_rows_and_appends_new_ones() -> None:
    draft = TableDraft(
        names={"a": "새 가", "z": "사라짐"}, order=("c", "a", "b"), order_base=ROWS, picked="z"
    )
    fitted = reconcile(draft, ("a", "b", "c", "d"))
    assert fitted == TableDraft(
        names={"a": "새 가"}, order=("c", "a", "b", "d"), order_base=ROWS, picked=None
    )
    # 고친 차례가 저장 차례와 같아지면 순서 편집이 없는 것이다.
    assert reconcile(TableDraft(order=("a", "b"), order_base=("b", "a")), ("a", "b")).order is None


def test_move_and_counts() -> None:
    assert move_row(ROWS, "c", 0) == ("c", "a", "b")
    assert move_row(ROWS, "a", 9) == ("b", "c", "a")
    assert move_row(ROWS, "b", -3) == ("b", "a", "c")
    moved = with_order(TableDraft(picked="c"), ("c", "a", "b"), ROWS)
    assert moved.order_base == ROWS and moved_count(moved, ROWS) == 3
    assert with_order(moved, ROWS, ROWS).order is None


def _repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    return repository


def _scenarios(repository: DuckDBScenarioRepository, *names: str) -> list[str]:
    return [
        repository.create_scenario(
            _metadata(name), _reference_tables(), ScenarioPreset(202608, 202608, ("Process-A",))
        ).scenario.scenario_id
        for name in names
    ]


def _names(repository: DuckDBScenarioRepository) -> dict[str, str]:
    return {
        scenario.scenario_id: scenario.scenario_name
        for scenario in repository.list_scenarios(include_archived=True)
    }


def test_list_edits_write_names_and_order_in_one_go(tmp_path: Path) -> None:
    """이름 맞바꾸기와 차례를 한 번에 쓴다. 이름 바꾼 시나리오는 「최근 수정」이 오른다."""
    repository = _repository(tmp_path)
    first, second, third = _scenarios(repository, "하나", "둘", "셋")
    stored = [scenario.scenario_id for scenario in repository.list_scenarios()]

    repository.apply_scenario_list_edits(
        {first: ("하나", " 둘 "), second: ("둘", "하나")},
        [third, first, second],
        expected_order=stored,
    )

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        third,
        first,
        second,
    ]
    assert _names(repository) == {first: "둘", second: "하나", third: "셋"}


def _updated_at(repository: DuckDBScenarioRepository) -> dict[str, datetime]:
    return {
        scenario.scenario_id: scenario.updated_at
        for scenario in repository.list_scenarios(include_archived=True)
    }


def test_a_name_only_save_keeps_the_shown_order_and_still_bumps_the_recent_edit(
    tmp_path: Path,
) -> None:
    """순서를 한 번도 저장하지 않은(`list_order` 가 모두 NULL) 목록에서 이름만 바꿔도 행이 맨
    위로 가지 않는다 — 이름을 쓰기 전의 차례를 `list_order` 로 함께 적는다. 「최근 수정」은
    그대로 오른다."""
    repository = _repository(tmp_path)
    _scenarios(repository, "하나", "둘", "셋")
    shown = [scenario.scenario_id for scenario in repository.list_scenarios()]
    bottom = shown[-1]
    before = _updated_at(repository)

    repository.apply_scenario_list_edits({bottom: (_names(repository)[bottom], "새 이름")})

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == shown
    assert _names(repository)[bottom] == "새 이름"
    after = _updated_at(repository)
    assert after[bottom] > before[bottom]
    assert all(after[other] == before[other] for other in shown if other != bottom)


def test_a_name_only_save_does_not_overwrite_an_order_saved_elsewhere(tmp_path: Path) -> None:
    """이름만 바꾼 저장이 적는 차례는 이 트랜잭션 안에서 읽은 지금 차례다 — 표를 그린 뒤 다른
    곳에서 바꾼 차례를 옛 차례로 덮지 않는다."""
    repository = _repository(tmp_path)
    first, second, third = _scenarios(repository, "하나", "둘", "셋")
    repository.reorder_scenarios([second, third, first])

    repository.apply_scenario_list_edits({first: ("하나", "새 하나")})

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        second,
        third,
        first,
    ]


def test_list_edits_refuse_everything_when_one_row_is_refused(tmp_path: Path) -> None:
    """빈 이름·보관본과 겹치는 이름·먼저 바뀐 이름·바뀐 차례를 행마다 모아 한 번에 거부한다."""
    repository = _repository(tmp_path)
    first, second, third, archived = _scenarios(repository, "하나", "둘", "셋", "보관본")
    repository.archive_scenario(archived)
    stored = [scenario.scenario_id for scenario in repository.list_scenarios()]
    repository.rename_scenario(third, "남이 바꾼 셋")
    before = _names(repository)

    with pytest.raises(BatchEditRefused) as refused:
        repository.apply_scenario_list_edits(
            {
                first: ("하나", "  "),
                second: ("둘", "보관본"),
                third: ("셋", "내가 바꾼 셋"),
            },
            list(reversed(stored)),
            expected_order=[second, first, third],
        )

    problems = dict(refused.value.problems)
    assert problems[first] == "시나리오명은(는) 비어 있을 수 없습니다."
    assert problems[second] == DUPLICATE_SCENARIO_NAME_MESSAGE
    assert problems[third] == "다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 바꾼 셋)."
    assert problems[None] == SCENARIO_LIST_MOVED_MESSAGE
    assert _names(repository) == before
    assert [scenario.scenario_id for scenario in repository.list_scenarios()] != list(
        reversed(stored)
    )


def test_list_edits_refuse_a_row_that_left_the_list(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first, second = _scenarios(repository, "하나", "둘")
    repository.archive_scenario(second)
    with pytest.raises(BatchEditRefused) as refused:
        repository.apply_scenario_list_edits({second: ("둘", "새 둘"), first: ("하나", "새 하나")})
    assert dict(refused.value.problems) == {second: "목록에서 빠진 시나리오입니다(보관·삭제됨)."}
    assert _names(repository)[first] == "하나"


def test_revision_names_are_renamed_together_or_not_at_all(tmp_path: Path) -> None:
    """여러 리비전명을 한 트랜잭션으로 쓴다. 하나가 먼저 바뀌었으면 아무것도 쓰지 않는다."""
    repository = _repository(tmp_path)
    (scenario_id,) = _scenarios(repository, "하나")
    first = repository.list_revisions(scenario_id)[0]
    snapshot = repository.load_revision(first.revision_id)
    second = repository.save_revision(
        scenario_id, snapshot.tables, snapshot.preset, revision_name="probe save"
    ).revision

    renamed = repository.rename_revisions(
        {
            second.revision_id: ("probe save", " 필터 "),
            first.revision_id: (first.revision_name, "초기"),
        }
    )
    assert [(item.revision_id, item.revision_name) for item in renamed] == [
        (second.revision_id, "필터"),
        (first.revision_id, "초기"),
    ]

    with pytest.raises(BatchEditRefused) as refused:
        repository.rename_revisions(
            {second.revision_id: ("probe save", "또"), first.revision_id: ("초기", "")}
        )
    assert dict(refused.value.problems) == {
        second.revision_id: "다른 사용자가 먼저 이름을 바꿨습니다(지금: 필터).",
        first.revision_id: "리비전명은(는) 비어 있을 수 없습니다.",
    }
    assert [item.revision_name for item in repository.list_revisions(scenario_id)] == [
        "필터",
        "초기",
    ]
    assert repository.rename_revisions({}) == []

    repository.archive_scenario(scenario_id)
    with pytest.raises(BatchEditRefused) as archived:
        repository.rename_revisions({first.revision_id: ("초기", "보관 뒤")})
    assert dict(archived.value.problems) == {
        first.revision_id: "보관된 시나리오의 리비전명은 바꿀 수 없습니다."
    }


def test_virtual_products_are_counted_for_many_revisions_at_once(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (scenario_id,) = _scenarios(repository, "하나")
    first = repository.list_revisions(scenario_id)[0]
    snapshot = repository.load_revision(first.revision_id)
    record = {
        "product": "DEMO_VIRTUAL",
        "stack": "8H",
        "source_product": "DEMO_SOURCE",
        "source_stack": "8H",
    }
    second = repository.save_revision(
        scenario_id,
        snapshot.tables,
        snapshot.preset,
        revision_name="가상",
        virtual_products=[record, {**record, "product": "DEMO_VIRTUAL_2"}],
    ).revision

    assert repository.count_virtual_products([first.revision_id, second.revision_id]) == {
        first.revision_id: 0,
        second.revision_id: 2,
    }
    assert repository.count_virtual_products([]) == {}
