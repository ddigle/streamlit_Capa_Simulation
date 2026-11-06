# Purpose: 저장소의 목록 이름 · 순서 일괄 쓰기(전부 아니면 전무)와 차례 규칙을 잰다.

"""저장소 쪽 — 목록 이름 · 순서 · 리비전명(`apply_scenario_list_edits`)을 한 트랜잭션으로 쓰고
하나라도 거부되면 아무것도 쓰지 않는다. 가상 제품 수는 리비전 id 목록으로 한 번에 센다. 초안 접기는
`tests/test_scenario_list_ops.py`, 시나리오 + 리비전 함께 쓰기는 `tests/test_scenario_list_save.py`
다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import (
    DUPLICATE_SCENARIO_NAME_MESSAGE,
    SCENARIO_LIST_MOVED_MESSAGE,
    BatchEditRefused,
    DuckDBScenarioRepository,
)


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
    위로 가지 않는다 — NULL 행은 만든 시각 차례라 「최근 수정」이 올라도 움직이지 않는다.
    「최근 수정」은 그대로 오른다."""
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
    """이름만 바꾼 저장은 차례를 쓰지 않는다 — 표를 그린 뒤 다른 곳에서 바꾼 차례를 옛 차례로
    덮지 않는다."""
    repository = _repository(tmp_path)
    first, second, third = _scenarios(repository, "하나", "둘", "셋")
    repository.reorder_scenarios([second, third, first])

    repository.apply_scenario_list_edits({first: ("하나", "새 하나")})

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        second,
        third,
        first,
    ]


def test_a_scenario_made_after_a_name_only_save_still_lands_on_top(tmp_path: Path) -> None:
    """이름만 바꾼 저장이 차례를 고정하지 않는다 — 순서를 저장한 적 없는 목록에서는 그 뒤 새로
    만든 시나리오(BigDataQuery 등록·복제·머지·Shift·자동 갱신)가 계속 맨 위에 선다.

    2026-10-23 리뷰 — 이름 저장이 활성 시나리오 전부의 `list_order` 를 1..n 으로 적어 그 뒤
    새 것이 맨 아래로 갔다.
    """
    repository = _repository(tmp_path)
    _scenarios(repository, "하나", "둘", "셋")
    shown = [scenario.scenario_id for scenario in repository.list_scenarios()]
    bottom = shown[-1]
    repository.apply_scenario_list_edits({bottom: (_names(repository)[bottom], "새 이름")})

    (newest,) = _scenarios(repository, "새 것")

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        newest,
        *shown,
    ]


def test_a_new_revision_does_not_move_a_row_that_was_never_ordered(tmp_path: Path) -> None:
    """순서를 저장한 적 없는 행은 새 리비전을 저장해 「최근 수정」이 올라도 그 자리에 있다 —
    다른 세션의 리비전 저장이 고치던 표의 행 차례를 흔들지 않는다."""
    repository = _repository(tmp_path)
    _scenarios(repository, "하나", "둘", "셋")
    shown = [scenario.scenario_id for scenario in repository.list_scenarios()]
    bottom = shown[-1]
    snapshot = repository.load_revision(repository.list_scenarios()[-1].active_revision_id)

    repository.save_revision(
        bottom,
        snapshot.tables,
        snapshot.preset,
        revision_name="둘째",
        parent_revision_id=snapshot.revision.revision_id,
    )

    after = repository.list_scenarios()
    assert [scenario.scenario_id for scenario in after] == shown
    assert after[-1].active_revision_no == 2


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
    assert problems[first] == "시나리오명은 비어 있을 수 없습니다."
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

    repository.apply_scenario_list_edits(
        {},
        revision_renames={
            second.revision_id: ("probe save", " 필터 "),
            first.revision_id: (first.revision_name, "초기"),
        },
    )
    assert [item.revision_name for item in repository.list_revisions(scenario_id)] == [
        "필터",
        "초기",
    ]

    with pytest.raises(BatchEditRefused) as refused:
        repository.apply_scenario_list_edits(
            {},
            revision_renames={
                second.revision_id: ("probe save", "또"),
                first.revision_id: ("초기", ""),
            },
        )
    assert dict(refused.value.problems) == {
        second.revision_id: "다른 사용자가 먼저 이름을 바꿨습니다(지금: 필터).",
        first.revision_id: "리비전명은 비어 있을 수 없습니다.",
    }
    assert [item.revision_name for item in repository.list_revisions(scenario_id)] == [
        "필터",
        "초기",
    ]

    repository.archive_scenario(scenario_id)
    with pytest.raises(BatchEditRefused) as archived:
        repository.apply_scenario_list_edits(
            {}, revision_renames={first.revision_id: ("초기", "보관 뒤")}
        )
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
