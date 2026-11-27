# Purpose: 부대공정 판 이력 · 판 내용 · 데이터셋 출처(마이그레이션 0037)와 S3 Drive 쓰기 기록(0038)
# 저장, 끄기 · 다시 켜기 · 새 판(리비전 · 앱 입력) · 기준 ETag 를 본다.

"""부대공정 판 저장소(`repository.*_extra_process*` · `persistence/extra_process_store.py`).

판 이력은 넣기만 하고 마지막 줄이 지금 상태다. 판 표에는 소유 칸이 없어 시나리오를 지워도 남고,
데이터셋 출처는 `dataset_id` 칸이 있어 시나리오와 함께 지워진다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from auto_update_fakes import new_repository
from extra_process_fixtures import bump_version, template_files, zip_files

from capa_simulation.audit import events, recorder
from capa_simulation.persistence.extra_process_store import ExtraProcessMoved
from capa_simulation.persistence.models import (
    EXTRA_EDITOR_LABEL,
    EXTRA_EDITOR_PLACE,
    EXTRA_KIND_APPLY,
    EXTRA_KIND_OFF,
    EXTRA_KIND_RESUME,
    EXTRA_KIND_REVISION,
    EXTRA_REVISION_PLACE,
    EXTRA_WRITE_FAILED,
    EXTRA_WRITE_KEPT,
    EXTRA_WRITE_WRITTEN,
    ExtraProcessProvenance,
    ScenarioCreate,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository, _owned_tables
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.extra_process_pack import pack_sha256, read_pack_zip


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    return new_repository(tmp_path / "extra.duckdb")


def _apply(repository: DuckDBScenarioRepository, data: bytes, *, expected_seq: int) -> None:
    reading = read_pack_zip(data)
    assert reading.pack is not None
    repository.apply_extra_process(
        data,
        sha256=reading.sha256,
        version_no=reading.pack.info.version_no,
        expected_seq=expected_seq,
        applied_by="개발자 A",
        process_count=len(reading.pack.processes),
        row_counts=json.dumps(reading.pack.row_counts()),
        source_place="test",
    )


def test_an_empty_store_has_no_versions(repository: DuckDBScenarioRepository) -> None:
    state = repository.load_extra_process_state()

    assert state.history == () and state.active is None and not state.off
    assert state.last_seq == 0 and state.latest_content is None


def test_apply_off_resume_keep_an_append_only_history(repository: DuckDBScenarioRepository) -> None:
    one = zip_files(template_files())
    _apply(repository, one, expected_seq=0)
    state = repository.load_extra_process_state()
    assert state.active is not None and state.active.kind == EXTRA_KIND_APPLY
    assert state.active.version_no == 1 and state.active.sha256 == pack_sha256(one)
    assert repository.load_extra_process_content(pack_sha256(one)) == one

    off = repository.turn_off_extra_process(expected_seq=1, applied_by=None)
    assert off.off and off.active is None
    assert off.latest_content is not None and off.latest_content.version_no == 1

    resumed = repository.resume_extra_process(expected_seq=2, applied_by=None)
    assert resumed.active is not None and resumed.active.kind == EXTRA_KIND_RESUME
    assert resumed.active.sha256 == pack_sha256(one) and resumed.active.version_no == 1
    assert [item.kind for item in resumed.history] == [
        EXTRA_KIND_APPLY,
        EXTRA_KIND_OFF,
        EXTRA_KIND_RESUME,
    ]

    two = zip_files(bump_version(template_files(), 2))
    _apply(repository, two, expected_seq=3)
    latest = repository.load_extra_process_state()
    assert latest.active is not None and latest.active.version_no == 2
    assert [item.seq for item in latest.history] == [1, 2, 3, 4]


def test_a_stale_screen_or_a_backward_version_writes_nothing(
    repository: DuckDBScenarioRepository,
) -> None:
    _apply(repository, zip_files(template_files()), expected_seq=0)

    with pytest.raises(ExtraProcessMoved):
        repository.turn_off_extra_process(expected_seq=0, applied_by=None)
    with pytest.raises(ValueError, match="보다 커야"):
        _apply(repository, zip_files(bump_version(template_files(), 1)), expected_seq=1)
    with pytest.raises(ValueError, match="꺼진 동안만"):
        repository.resume_extra_process(expected_seq=1, applied_by=None)

    assert repository.load_extra_process_state().last_seq == 1


def test_off_twice_is_refused(repository: DuckDBScenarioRepository) -> None:
    _apply(repository, zip_files(template_files()), expected_seq=0)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)

    with pytest.raises(ValueError, match="이미 꺼져"):
        repository.turn_off_extra_process(expected_seq=2, applied_by=None)


def test_only_the_provenance_table_is_owned_by_a_scenario(
    repository: DuckDBScenarioRepository,
) -> None:
    with repository._connect() as connection:
        owned = {(schema, table) for schema, table, _ in _owned_tables(connection)}

    assert ("app_meta", "dataset_extra_process") in owned
    assert ("app_meta", "extra_process_version") not in owned
    assert ("app_meta", "extra_process_content") not in owned


def test_provenance_rides_with_the_dataset_and_leaves_with_the_scenario(
    repository: DuckDBScenarioRepository,
) -> None:
    _apply(repository, zip_files(template_files()), expected_seq=0)
    record = ExtraProcessProvenance(
        process_name="DEMO_New_Bond",
        version_seq=1,
        version_no=1,
        sha256="a" * 64,
        outcome="MERGED",
        row_counts=json.dumps({"RQ_REQB": 24}),
    )
    seed = build_builtin_seed_dataset()
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="부대공정 출처 시험",
            source_simulation_code="SIM-EXTRA",
            source_simulation_name="합성",
            source_type="TEST",
            pipeline_version="test",
        ),
        seed.reference_tables,
        full_data_scenario_preset(seed.reference_tables),
        # 같은 (공정, 판 차례)가 겹치면 앞 줄만 남는다.
        extra_process=(record, record),
    )

    dataset_id = snapshot.scenario.dataset_id
    assert repository.load_dataset_extra_process(dataset_id) == (record,)

    repository.delete_scenario(snapshot.scenario.scenario_id)
    assert repository.load_dataset_extra_process(dataset_id) == ()
    # 판 이력은 시나리오 삭제와 상관없이 남는다.
    assert repository.load_extra_process_state().last_seq == 1


def _revise(repository: DuckDBScenarioRepository, data: bytes, *, expected_seq: int) -> None:
    reading = read_pack_zip(data)
    assert reading.pack is not None
    repository.revise_extra_process(
        data,
        sha256=reading.sha256,
        version_no=reading.pack.info.version_no,
        expected_seq=expected_seq,
        applied_by="개발자 A",
        process_count=len(reading.pack.processes),
        row_counts=json.dumps(reading.pack.row_counts()),
        base_scenario_ref="scenario-1",
        base_revision_ref="revision-2",
    )


def test_a_revision_version_points_at_its_base_and_needs_a_larger_number(
    repository: DuckDBScenarioRepository,
) -> None:
    _apply(repository, zip_files(template_files()), expected_seq=0)
    with pytest.raises(ValueError, match="커야 합니다"):
        _revise(repository, zip_files(template_files()), expected_seq=1)

    _revise(repository, zip_files(bump_version(template_files(), 2)), expected_seq=1)

    active = repository.load_extra_process_state().active
    assert active is not None and active.kind == EXTRA_KIND_REVISION
    assert active.version_no == 2 and active.source_place == EXTRA_REVISION_PLACE
    assert (active.base_scenario_ref, active.base_revision_ref) == ("scenario-1", "revision-2")
    assert active.kind_label == "새 판"


def _apply_editor(repository: DuckDBScenarioRepository, data: bytes, *, expected_seq: int) -> None:
    reading = read_pack_zip(data)
    assert reading.pack is not None
    repository.apply_editor_extra_process(
        data,
        sha256=reading.sha256,
        version_no=reading.pack.info.version_no,
        expected_seq=expected_seq,
        applied_by="개발자 A",
        process_count=len(reading.pack.processes),
        row_counts=json.dumps(reading.pack.row_counts()),
    )


def _audit_lines(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    def capture(event: str, **fields: Any) -> None:
        lines.append({"ev": event, **fields})

    monkeypatch.setattr(recorder, "record", capture)
    return lines


def test_an_editor_version_is_an_app_input_new_version_without_a_base(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """편집기 판은 갈래 「새 판」 그대로 원천 자리 「앱 입력」 이고 바탕 칸이 비어 있다 — 판
    번호 검사 · 화면이 본 차례 대조는 다른 쓰기와 같고, 감사는 따로 한 사건(갈래 · 차례 · 판 ·
    공정 수만)이다."""
    _apply(repository, zip_files(template_files()), expected_seq=0)
    lines = _audit_lines(monkeypatch)

    with pytest.raises(ValueError, match="커야 합니다"):
        _apply_editor(repository, zip_files(template_files()), expected_seq=1)
    with pytest.raises(ExtraProcessMoved):
        _apply_editor(repository, zip_files(bump_version(template_files(), 2)), expected_seq=0)
    assert repository.load_extra_process_state().last_seq == 1

    _apply_editor(repository, zip_files(bump_version(template_files(), 2)), expected_seq=1)

    active = repository.load_extra_process_state().active
    assert active is not None and active.kind == EXTRA_KIND_REVISION and active.version_no == 2
    assert active.source_place == EXTRA_EDITOR_PLACE and active.editor_made
    assert (active.base_scenario_ref, active.base_revision_ref) == (None, None)
    assert active.kind_label == EXTRA_EDITOR_LABEL == "앱 입력"
    assert lines == [
        {
            "ev": "admin_extra_process_editor",
            "out": "fail",
            "claimed": "개발자 A",
            "det": {"kind": EXTRA_KIND_REVISION},
        },
        {
            "ev": "admin_extra_process_editor",
            "out": "fail",
            "claimed": "개발자 A",
            "det": {"kind": EXTRA_KIND_REVISION},
        },
        {
            "ev": "admin_extra_process_editor",
            "claimed": "개발자 A",
            "det": {"kind": EXTRA_KIND_REVISION, "entry": 2, "version": 2, "processes": 2},
        },
    ]
    spec = events.spec_of("admin_extra_process_editor")
    assert spec is not None and spec.det_keys == {"kind", "entry", "version", "processes"}


def test_an_editor_version_applied_while_off_turns_the_pack_back_on(
    repository: DuckDBScenarioRepository,
) -> None:
    """끈 동안 편집기 판을 넣으면 그 판이 활성이 된다(다시 켜짐 — 가져온 판의 「적용」 과
    같다). 끄고 단추로 다시 켜면 그 「다시 켜기」 줄은 원천 자리를 옮겨 적어도 편집기 판 줄이
    아니다."""
    _apply(repository, zip_files(template_files()), expected_seq=0)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)

    _apply_editor(repository, zip_files(bump_version(template_files(), 2)), expected_seq=2)

    state = repository.load_extra_process_state()
    assert not state.off and state.active is not None and state.active.version_no == 2
    assert state.active.editor_made

    repository.turn_off_extra_process(expected_seq=3, applied_by=None)
    resumed = repository.resume_extra_process(expected_seq=4, applied_by=None).active
    assert resumed is not None and resumed.kind == EXTRA_KIND_RESUME
    assert resumed.source_place == EXTRA_EDITOR_PLACE and not resumed.editor_made
    assert resumed.kind_label == "다시 켜기"


def test_s3_writes_are_appended_and_pick_the_baseline_etag(
    repository: DuckDBScenarioRepository,
) -> None:
    one = zip_files(template_files())
    reading = read_pack_zip(one)
    assert reading.pack is not None
    repository.apply_extra_process(
        one,
        sha256=reading.sha256,
        version_no=1,
        expected_seq=0,
        applied_by=None,
        process_count=2,
        row_counts="{}",
        source_place="S3 Drive",
        s3_etag='"etag-1"',
    )
    assert repository.load_extra_process_state().baseline == ('"etag-1"', 1)

    _revise(repository, zip_files(bump_version(template_files(), 2)), expected_seq=1)
    # 「새 판으로」 가 아직 쓰지 못한 동안은 앞 판 파일의 ETag 를 잇는다.
    state = repository.load_extra_process_state()
    assert state.baseline == ('"etag-1"', 1)

    state = repository.record_extra_process_write(
        version_seq=2, result=EXTRA_WRITE_KEPT, written_by="개발자 A", seen_etag='"사람"'
    )
    state = repository.record_extra_process_write(
        version_seq=2, result=EXTRA_WRITE_FAILED, written_by=None, stage="PUT", reason="닿지 못함"
    )
    assert state.baseline == ('"etag-1"', 1)
    last = state.last_write(2)
    assert last is not None and last.result == EXTRA_WRITE_FAILED and last.result_label == "실패"

    state = repository.record_extra_process_write(
        version_seq=2, result=EXTRA_WRITE_WRITTEN, written_by=None, etag='"etag-2"'
    )
    assert state.baseline == ('"etag-2"', 2)
    assert [item.result for item in state.writes] == [
        EXTRA_WRITE_KEPT,
        EXTRA_WRITE_FAILED,
        EXTRA_WRITE_WRITTEN,
    ]
    # 판 이력 줄은 고치지 않았다(넣기만).
    assert state.active is not None and state.active.s3_write_result is None


def test_a_write_needs_a_content_version_and_matching_fields(
    repository: DuckDBScenarioRepository,
) -> None:
    with pytest.raises(ValueError, match="판 이력에 없습니다"):
        repository.record_extra_process_write(
            version_seq=1, result=EXTRA_WRITE_WRITTEN, written_by=None, etag='"x"'
        )
    _apply(repository, zip_files(template_files()), expected_seq=0)
    with pytest.raises(ValueError, match="ETag"):
        repository.record_extra_process_write(
            version_seq=1, result=EXTRA_WRITE_WRITTEN, written_by=None
        )
    with pytest.raises(ValueError, match="단계"):
        repository.record_extra_process_write(
            version_seq=1, result=EXTRA_WRITE_FAILED, written_by=None
        )
    assert repository.load_extra_process_state().writes == ()


def test_resume_from_an_imported_file_keeps_its_etag(repository: DuckDBScenarioRepository) -> None:
    _apply(repository, zip_files(template_files()), expected_seq=0)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)

    state = repository.resume_extra_process(
        expected_seq=2, applied_by=None, s3_key="extra_process/current.zip", s3_etag='"etag-r"'
    )

    assert state.active is not None and state.active.kind == EXTRA_KIND_RESUME
    assert state.baseline == ('"etag-r"', 3)
