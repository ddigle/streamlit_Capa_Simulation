# Purpose: 데이터 작업 감사 줄 — 쓰기마다 한 줄 · 값 원문 없음 · 실패 줄 · 삭제 흔적 · 꺼짐 0줄.

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.audit import recorder
from capa_simulation.audit.work import EVENT_ATTRIBUTE, audited
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import BatchEditRefused, DuckDBScenarioRepository

ACTOR = "demo.writer"

# 설계서 2-3 표의 쓰기 함수 → 사건. 표에 없는 함수가 생기거나 이름이 바뀌면 여기서 걸린다.
SIMULATION_EVENTS: dict[str, str | tuple[str, ...]] = {
    "create_scenario": "data_scenario_create",
    "rename_scenario": "data_scenario_rename",
    "archive_scenario": "data_scenario_archive",
    "restore_scenario": "data_scenario_restore",
    "delete_scenario": "data_scenario_delete",
    "save_revision": "data_revision_save",
    "rename_revision": "data_revision_rename",
    "reorder_scenarios": "data_scenario_reorder",
    "apply_scenario_list_edits": (
        "data_scenario_rename",
        "data_revision_rename",
        "data_scenario_reorder",
    ),
    "publish_official_revision": "data_official_publish",
    "record_auto_official_update_exclusions": "data_auto_update_exclusions",
    "replace_global_display_order": "data_profile_save",
    "replace_global_process_rename": "data_profile_save",
    "replace_global_execution_capacity": "data_profile_save",
    "replace_global_top5_band": "data_profile_save",
    "replace_global_key_process_presets": "data_profile_save",
    "replace_global_summary_note": "data_profile_save",
    "replace_global_comparison_scenario": "data_profile_save",
    "replace_global_main_case": "data_profile_save",
    "clear_global_main_case_scenario": "data_profile_save",
    "replace_global_advance_load": "data_profile_save",
    "replace_global_advance_shipment": "data_profile_save",
    "replace_global_securement_threshold": "data_profile_save",
    "replace_global_past_data": "data_profile_save",
    "create_voc_post": "data_voc_post",
    "create_voc_reply": "data_voc_reply",
    "set_voc_post_resolved": "data_voc_resolve",
    "remove_voc_post": "data_voc_delete",
}
EQUIPMENT_EVENTS: dict[str, str | tuple[str, ...]] = {
    "save_equipment": "data_equipment_save",
    "save_snapshot": "data_equipment_save",
    "save_space_layout": "data_layout_save",
    "clone_equipment_scenario": "data_equipment_scenario_clone",
    "rename_equipment_scenario": "data_equipment_scenario_rename",
    "publish_equipment_release": "data_equipment_publish",
    "rename_schedule_revision": "data_schedule_rename",
    "restore_schedule_revision": "data_schedule_restore",
    "clear_layout_overlay": "data_layout_overlay_clear",
    "save_manual_downtime": "data_downtime_save",
    "save_shortening_baseline": "data_baseline_save",
    "delete_shortening_baseline": "data_baseline_delete",
    "save_process_cutoff": "data_cutoff_save",
    "save_standard_target_availability": "data_target_save",
    "clear_standard_target_availability": "data_target_clear",
    "save_floor_states": "data_floor_state_save",
    "save_fab_layout": "data_drawing_save",
    "save_fab_layout_canvas": "data_drawing_save",
    "save_floor_layout_canvas": "data_drawing_save",
    "replace_floor_layout_marks": "data_drawing_save",
}
# 업무 값이 아니라 보기 상태라 기록하지 않는 쓰기(설계서 2-3).
UNRECORDED = ("save_shortening_filter_months", "save_shortening_filter_processes")


@pytest.fixture()
def on() -> Iterator[None]:
    recorder.start(env="cdep", version="test", inst="cdcdcdcdcdcd")
    recorder.set_resolver(lambda: recorder.Actor(ACTOR, True, "user"))
    yield


@pytest.fixture()
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repo = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repo.initialize()
    return repo


def _preset() -> ScenarioPreset:
    return ScenarioPreset(
        start_month=202608,
        end_month=202608,
        included_processes=("Process-A",),
        standard_target_processes=("Process-A",),
    )


def _work(prefix: str = "data_") -> list[dict[str, Any]]:
    return [line for line in recorder.take_pending() if line["ev"].startswith(prefix)]


@pytest.mark.parametrize(
    ("owner", "table"),
    [(DuckDBScenarioRepository, SIMULATION_EVENTS), (DuckDBEquipmentRepository, EQUIPMENT_EVENTS)],
)
def test_every_listed_write_carries_its_event(
    owner: type, table: dict[str, str | tuple[str, ...]]
) -> None:
    for name, event in table.items():
        assert getattr(getattr(owner, name), EVENT_ATTRIBUTE, None) == event, name
    for name in UNRECORDED:
        if hasattr(owner, name):
            assert not hasattr(getattr(owner, name), EVENT_ATTRIBUTE), name


def test_scenario_writes_leave_one_line_each_and_delete_leaves_a_trace(
    on: None, repository: DuckDBScenarioRepository
) -> None:
    snapshot = repository.create_scenario(_metadata(), _reference_tables(), _preset())
    scenario_id = snapshot.scenario.scenario_id
    repository.rename_scenario(scenario_id, "Scenario Renamed")
    repository.delete_scenario(scenario_id)

    lines = _work()
    assert [line["ev"] for line in lines] == [
        "data_scenario_create",
        "data_scenario_rename",
        "data_scenario_delete",
    ]
    create, rename, delete = lines
    assert create["tgt"] == {"type": "scenario", "id": scenario_id, "label": "Scenario A"}
    assert create["det"] == {"source": "TEST"}
    assert rename["tgt"]["label"] == "Scenario Renamed"
    assert delete["tgt"] == {"type": "scenario", "id": scenario_id}
    assert all(
        (line["actor"], line["verified"], line["out"]) == (ACTOR, True, "success") for line in lines
    )
    assert "Product-A" not in json.dumps(lines, ensure_ascii=False)


def test_the_list_screen_batch_save_leaves_a_line_per_rename_and_one_for_the_order(
    on: None, repository: DuckDBScenarioRepository
) -> None:
    """목록 관리 「변경 저장」 의 실제 길(`apply_scenario_list_edits`) — 이름을 바꾼 시나리오 ·
    리비전마다 한 줄(저장처럼 앞뒤 공백을 뗀 새 이름표), 순서를 고쳤으면 한 줄."""
    first = repository.create_scenario(_metadata(), _reference_tables(), _preset())
    second = repository.create_scenario(_metadata("Scenario B"), _reference_tables(), _preset())
    one, two = first.scenario.scenario_id, second.scenario.scenario_id
    revision = first.revision.revision_id
    _work()

    repository.apply_scenario_list_edits(
        {one: ("Scenario A", "  Scenario A2 ")},
        (one, two),
        revision_renames={revision: (first.revision.revision_name, "Rev Renamed")},
    )

    lines = _work()
    assert [(line["ev"], line.get("tgt"), line.get("det")) for line in lines] == [
        ("data_scenario_rename", {"type": "scenario", "id": one, "label": "Scenario A2"}, None),
        (
            "data_revision_rename",
            {"type": "revision", "id": revision, "label": "Rev Renamed"},
            None,
        ),
        ("data_scenario_reorder", None, {"rows": 2}),
    ]
    assert all((line["actor"], line["out"]) == (ACTOR, "success") for line in lines)
    repository.reorder_scenarios([two, one])
    (reorder,) = _work()
    assert (reorder["ev"], reorder["det"]) == ("data_scenario_reorder", {"rows": 2})


def test_a_refused_batch_save_leaves_failure_lines(
    on: None, repository: DuckDBScenarioRepository
) -> None:
    snapshot = repository.create_scenario(_metadata(), _reference_tables(), _preset())
    scenario_id = snapshot.scenario.scenario_id
    _work()

    with pytest.raises(BatchEditRefused):
        repository.apply_scenario_list_edits({scenario_id: ("someone else saw", "Mine")})

    (line,) = _work()
    assert (line["ev"], line["out"], line["why"]) == (
        "data_scenario_rename",
        "fail",
        "BatchEditRefused",
    )
    assert line["tgt"] == {"type": "scenario", "id": scenario_id, "label": "Mine"}


def test_a_failed_write_is_one_failure_line_and_the_error_still_rises(
    on: None, repository: DuckDBScenarioRepository
) -> None:
    with pytest.raises(Exception) as caught:
        repository.rename_scenario("no-such-scenario", "Nope")

    (line,) = _work()
    assert (line["ev"], line["out"], line["lvl"]) == ("data_scenario_rename", "fail", "warn")
    assert line["why"] == type(caught.value).__name__
    assert line["tgt"]["id"] == "no-such-scenario"


def test_voc_and_profile_lines_carry_no_free_text(
    on: None, repository: DuckDBScenarioRepository
) -> None:
    post = repository.create_voc_post(
        category="질문",
        title="제목 원문",
        body="본문 원문은 남기지 않는다",
        author="손 입력 작성자",
    )
    repository.create_voc_reply(post_id=post, body="답글 원문", author=ACTOR)
    repository.set_voc_post_resolved(post, resolved=True)
    repository.replace_global_summary_note("공지 원문", source="웹 직접 편집")

    lines = _work()
    assert [line["ev"] for line in lines] == [
        "data_voc_post",
        "data_voc_reply",
        "data_voc_resolve",
        "data_profile_save",
    ]
    assert lines[0]["tgt"] == {"type": "voc", "id": post}
    assert lines[0]["claimed"] == "손 입력 작성자"
    assert "claimed" not in lines[1], "인증 신원과 같은 손입력 이름은 남기지 않는다"
    assert lines[2]["det"] == {"resolved": True}
    assert lines[3]["det"]["profile"] == "summary_note"
    assert lines[3]["det"]["version_to"] == 1
    payload = json.dumps(lines, ensure_ascii=False)
    for text in ("제목 원문", "본문 원문", "답글 원문", "공지 원문"):
        assert text not in payload


def test_equipment_writes_record_too(on: None, tmp_path: Path) -> None:
    equipment = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    equipment.initialize()

    equipment.clear_standard_target_availability()
    equipment.delete_shortening_baseline("demo-missing-baseline")

    lines = _work()
    assert [(line["ev"], line.get("tgt")) for line in lines] == [
        ("data_target_clear", None),
        ("data_baseline_delete", {"type": "baseline", "id": "demo-missing-baseline"}),
    ]


def test_an_off_recorder_writes_no_line_and_resolves_nobody(
    repository: DuckDBScenarioRepository,
) -> None:
    def refuse() -> recorder.Actor:
        raise AssertionError("꺼진 기록기는 행위자를 정하지 않는다")

    recorder.set_resolver(refuse)
    snapshot = repository.create_scenario(_metadata(), _reference_tables(), _preset())
    repository.delete_scenario(snapshot.scenario.scenario_id)

    assert recorder.take_pending() == []
    assert recorder.pending_count() == 0


class _Nested:
    @audited("data_scenario_rename")
    def outer(self) -> None:
        self.inner()

    @audited("data_scenario_archive")
    def inner(self) -> None:
        return None


def test_a_write_inside_a_write_is_one_line(on: None) -> None:
    _Nested().outer()
    _Nested().inner()

    assert [line["ev"] for line in _work()] == ["data_scenario_rename", "data_scenario_archive"]


def test_a_broken_describe_never_blocks_the_write(on: None) -> None:
    def broken(args: object, result: object) -> Any:
        raise RuntimeError("꼴 실패")

    class Owner:
        @audited("data_scenario_rename", broken)
        def write(self) -> int:
            return 7

    assert Owner().write() == 7
    (line,) = _work()
    assert line["ev"] == "data_scenario_rename" and "tgt" not in line
