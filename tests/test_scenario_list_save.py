# Purpose: 목록 저장이 시나리오명 · 순서 · 리비전명을 한 트랜잭션으로 쓰고 막힘 판정과 맞는지 잰다.

"""`DuckDBScenarioRepository.apply_scenario_list_edits(revision_renames=)`. 시나리오명 · 차례 ·
리비전명을 한 번에 쓰고 하나라도 막히면 아무것도 쓰지 않는다. 화면이 미리 보이는
막힘(`list_problems`)은 저장소 거부와 같은 판정이어야 한다 — 이 시험이 두 쪽을 같은 입력으로
맞댄다."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import (
    DUPLICATE_SCENARIO_NAME_MESSAGE,
    SCENARIO_LIST_MOVED_MESSAGE,
    BatchEditRefused,
    DuckDBScenarioRepository,
    name_moved_message,
)
from capa_simulation.services.scenario_list_edits import (
    ListDraft,
    ListProblems,
    ListRules,
    NameEdit,
    SavedList,
    SavedRevision,
    list_problems,
    reconcile,
    save_plan,
)

RULES = ListRules(
    duplicate=DUPLICATE_SCENARIO_NAME_MESSAGE,
    order=SCENARIO_LIST_MOVED_MESSAGE,
    moved=name_moved_message,
    empty=lambda label: f"{label}은 비어 있을 수 없습니다.",
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


def _revision(repository: DuckDBScenarioRepository, scenario_id: str) -> tuple[str, str]:
    summary = repository.list_revisions(scenario_id)[0]
    return summary.revision_id, summary.revision_name


def _names(repository: DuckDBScenarioRepository) -> dict[str, str]:
    return {
        item.scenario_id: item.scenario_name
        for item in repository.list_scenarios(include_archived=True)
    }


def _saved(repository: DuckDBScenarioRepository, draft: ListDraft) -> SavedList:
    active = repository.list_scenarios()
    rows = repository.list_revisions_by_ids(list(draft.revisions))
    return SavedList(
        order=tuple(item.scenario_id for item in active),
        names={item.scenario_id: item.scenario_name for item in active},
        all_names=_names(repository),
        revisions={
            revision_id: SavedRevision(
                revision_id,
                summary.revision_no,
                summary.revision_name,
                summary.scenario_id,
                active=status == "ACTIVE",
            )
            for revision_id, (summary, status) in rows.items()
        },
    )


def _write(repository: DuckDBScenarioRepository, draft: ListDraft) -> None:
    saved = _saved(repository, draft)
    plan = save_plan(reconcile(draft, saved).draft, saved)
    repository.apply_scenario_list_edits(
        plan.scenario_renames,
        plan.order,
        expected_order=plan.order_base,
        revision_renames=plan.revision_renames,
    )


def _refused(
    repository: DuckDBScenarioRepository, draft: ListDraft
) -> tuple[ListProblems, dict[str | None, str]]:
    """같은 초안의 미리 보인 막힘과 저장소 거부 — 저장소 거부는 쓰지 않는다."""
    saved = _saved(repository, draft)
    fitted = reconcile(draft, saved).draft
    shown = list_problems(fitted, saved, RULES)
    plan = save_plan(fitted, saved)
    with pytest.raises(BatchEditRefused) as refused:
        repository.apply_scenario_list_edits(
            plan.scenario_renames,
            plan.order,
            expected_order=plan.order_base,
            revision_renames=plan.revision_renames,
        )
    return shown, dict(refused.value.problems)


def test_scenario_names_order_and_revision_names_are_written_together(tmp_path: Path) -> None:
    """다른 시나리오의 리비전 고침도 함께 저장된다 — 시나리오를 바꿔도 고침이 남는다."""
    repository = _repository(tmp_path)
    first, second, third = _scenarios(repository, "하나", "둘", "셋")
    revision_one, name_one = _revision(repository, first)
    revision_three, name_three = _revision(repository, third)
    stored = tuple(item.scenario_id for item in repository.list_scenarios())
    order = (third, first, second)
    assert order != stored

    _write(
        repository,
        ListDraft(
            scenarios={second: NameEdit("둘", "새 둘")},
            revisions={
                revision_one: NameEdit(name_one, "하나 리비전"),
                revision_three: NameEdit(name_three, "셋 리비전"),
            },
            order=order,
            order_base=stored,
        ),
    )

    assert tuple(item.scenario_id for item in repository.list_scenarios()) == order
    assert _names(repository)[second] == "새 둘"
    assert repository.list_revisions(first)[0].revision_name == "하나 리비전"
    assert repository.list_revisions(third)[0].revision_name == "셋 리비전"


def test_one_refused_line_writes_neither_the_names_nor_the_order(tmp_path: Path) -> None:
    """시나리오 쪽이 막혀도 리비전명을 쓰지 않고, 리비전 쪽이 막혀도 시나리오명 · 차례를 쓰지
    않는다."""
    repository = _repository(tmp_path)
    first, second = _scenarios(repository, "하나", "둘")
    revision, name = _revision(repository, first)
    stored = tuple(item.scenario_id for item in repository.list_scenarios())

    shown, refused = _refused(
        repository,
        ListDraft(
            scenarios={first: NameEdit("하나", "둘")},
            revisions={revision: NameEdit(name, "쓰면 안 되는 이름")},
        ),
    )
    assert refused == {first: DUPLICATE_SCENARIO_NAME_MESSAGE} == dict(shown.scenarios)
    assert repository.list_revisions(first)[0].revision_name == name

    shown, refused = _refused(
        repository,
        ListDraft(
            scenarios={first: NameEdit("하나", "쓰면 안 되는 이름")},
            revisions={revision: NameEdit("남이 먼저 바꾼 뒤 옛 이름", "내 이름")},
            order=(second, first) if stored == (first, second) else (first, second),
            order_base=stored,
        ),
    )
    assert refused == {revision: name_moved_message(name)} == dict(shown.revisions)
    assert _names(repository)[first] == "하나"
    assert tuple(item.scenario_id for item in repository.list_scenarios()) == stored


def test_the_preview_says_what_the_store_refuses(tmp_path: Path) -> None:
    """미리 보인 막힘과 저장소 거부가 줄마다 같다 — 남이 바꾼 줄의 새 이름은 겹침에 들지 않고,
    맞바꾸기는 막히지 않으며, 보관본과는 겹칠 수 없다."""
    repository = _repository(tmp_path)
    first, second, third, archived = _scenarios(repository, "하나", "둘", "셋", "보관본")
    repository.archive_scenario(archived)

    # 남이 먼저 바꾼 줄(셋)의 새 이름 「하나」 는 겹침에 들지 않는다 — 하나 · 둘 맞바꾸기는 지나고
    # 셋만 막힌다.
    shown, refused = _refused(
        repository,
        ListDraft(
            scenarios={
                first: NameEdit("하나", "둘"),
                second: NameEdit("둘", "하나"),
                third: NameEdit("옛 셋", "하나"),
            }
        ),
    )
    assert refused == {third: name_moved_message("셋")} == dict(shown.scenarios)

    # 보관본 이름 · 빈 이름.
    shown, refused = _refused(
        repository,
        ListDraft(scenarios={first: NameEdit("하나", "보관본"), second: NameEdit("둘", "")}),
    )
    assert set(refused) == {first, second} == set(shown.scenarios)
    assert refused[first] == shown.scenarios[first] == DUPLICATE_SCENARIO_NAME_MESSAGE
    assert (
        "비어 있을 수 없습니다" in refused[second]
        and "비어 있을 수 없습니다" in shown.scenarios[second]
    )

    # 남이 바꾼 차례 — 저장소도 화면도 목록 전체의 까닭이다.
    stored = tuple(item.scenario_id for item in repository.list_scenarios())
    repository.reorder_scenarios(list(reversed(stored)))
    shown, refused = _refused(repository, ListDraft(order=stored, order_base=stored))
    assert refused == {None: SCENARIO_LIST_MOVED_MESSAGE}
    assert shown.order == SCENARIO_LIST_MOVED_MESSAGE


def test_revision_names_follow_the_single_rename_rules(tmp_path: Path) -> None:
    """리비전명 규칙은 `rename_revision` 과 같다 — 앞뒤 공백 떼기 · 같은 이름 허용 · 보관된
    시나리오 거절 · 지워진 리비전 거절, 시나리오 「최근 수정」 은 오르지 않는다."""
    repository = _repository(tmp_path)
    first, second = _scenarios(repository, "하나", "둘")
    revision, name = _revision(repository, first)
    other, other_name = _revision(repository, second)
    updated = {item.scenario_id: item.updated_at for item in repository.list_scenarios()}

    repository.apply_scenario_list_edits(
        {}, revision_renames={revision: (name, " 같은 이름 "), other: (other_name, "같은 이름")}
    )
    assert repository.list_revisions(first)[0].revision_name == "같은 이름"
    assert repository.list_revisions(second)[0].revision_name == "같은 이름"
    assert {item.scenario_id: item.updated_at for item in repository.list_scenarios()} == updated

    repository.archive_scenario(first)
    with pytest.raises(BatchEditRefused) as refused:
        repository.apply_scenario_list_edits(
            {}, revision_renames={revision: ("같은 이름", "보관 뒤"), "없는 리비전": ("옛", "새")}
        )
    assert dict(refused.value.problems) == {
        revision: "보관된 시나리오의 리비전명은 바꿀 수 없습니다.",
        "없는 리비전": "리비전을 찾을 수 없습니다(시나리오가 지워짐).",
    }
    assert refused.value.moved_names == {}
    assert repository.list_revisions(first)[0].revision_name == "같은 이름"


def test_a_scenario_without_a_revision_does_not_trip_the_id_read(tmp_path: Path) -> None:
    """고친 리비전이 없으면 DB 를 열지 않고, 없는 id 는 빠진다. 한 쿼리로 시나리오를 가리지 않고
    읽는다."""
    repository = _repository(tmp_path)
    first, second = _scenarios(repository, "하나", "둘")
    revision, _ = _revision(repository, first)
    other, _ = _revision(repository, second)
    assert repository.list_revisions_by_ids([]) == {}
    rows = repository.list_revisions_by_ids([revision, other, "없는 리비전"])
    assert set(rows) == {revision, other}
    assert rows[revision][0].scenario_id == first and rows[revision][1] == "ACTIVE"
    repository.archive_scenario(first)
    assert repository.list_revisions_by_ids([revision])[revision][1] == "ARCHIVED"
