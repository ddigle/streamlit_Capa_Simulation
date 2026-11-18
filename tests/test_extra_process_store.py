# Purpose: 부대공정 판 이력 · 판 내용 · 데이터셋 출처(마이그레이션 0037) 저장과 끄기 · 다시 켜기를
# 본다.

"""부대공정 판 저장소(`repository.*_extra_process*` · `persistence/extra_process_store.py`).

판 이력은 넣기만 하고 마지막 줄이 지금 상태다. 판 표에는 소유 칸이 없어 시나리오를 지워도 남고,
데이터셋 출처는 `dataset_id` 칸이 있어 시나리오와 함께 지워진다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_update_fakes import new_repository
from extra_process_fixtures import bump_version, template_files, zip_files

from capa_simulation.persistence.extra_process_store import ExtraProcessMoved
from capa_simulation.persistence.models import (
    EXTRA_KIND_APPLY,
    EXTRA_KIND_OFF,
    EXTRA_KIND_RESUME,
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
