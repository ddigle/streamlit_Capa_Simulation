# Purpose: 공식버전 자동 갱신 설정·변경 기록·실행 기록·자동 off 기록(0035)의 저장소 계약을 검증한다.

"""자동 갱신의 저장 계약.

- 설정은 공용 프로필이다 — 미저장이면 코드 기본값이고, 저장은 버전을 대조하며 바꾼 칸을 기록한다.
- 실행 기록의 `run_key` 가 회차 선점이다. 같은 키는 두 번 잡히지 않는다.
- 기록은 시나리오 소유가 아니다 — 그 시나리오를 지워도 남는다.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.auto_official_update_store import (
    AutoOfficialUpdateSettingsConflict,
)
from capa_simulation.persistence.models import AutoOfficialUpdateExclusion, ScenarioCreate
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import (
    DEFAULT_CONFIG,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    AutoUpdateConfig,
)

STARTED = datetime(2026, 10, 15, 7, 0)


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "auto_store.duckdb")
    repository.initialize()
    return repository


def _claim(repository: DuckDBScenarioRepository, run_key: str) -> str | None:
    return repository.claim_auto_official_update_run(
        run_key=run_key,
        trigger_kind=TRIGGER_SCHEDULED,
        run_date=date(2026, 10, 15),
        started_at=STARTED,
        keyword="PSM",
        threshold=0.8,
        settings_version=0,
    )


def test_unsaved_settings_are_the_code_defaults(repository: DuckDBScenarioRepository) -> None:
    settings = repository.load_auto_official_update_settings()

    assert (settings.version, settings.updated_at, settings.config) == (0, None, DEFAULT_CONFIG)
    assert repository.list_auto_official_update_setting_changes() == []


def test_saving_settings_bumps_the_version_and_records_what_changed(
    repository: DuckDBScenarioRepository,
) -> None:
    first = repository.replace_auto_official_update_settings(
        AutoUpdateConfig(True, time(8, 30), "PSM", 0.75),
        expected_version=0,
        changed_by="  김담당 ",
    )
    second = repository.replace_auto_official_update_settings(
        AutoUpdateConfig(False, time(8, 30), "PSM", 0.75),
        expected_version=1,
        changed_by="   ",
    )

    assert first.version == 1 and first.config.check_time == time(8, 30)
    assert second.version == 2 and not second.config.enabled
    changes = repository.list_auto_official_update_setting_changes()
    assert [(change.version, change.changed_by) for change in changes] == [(2, None), (1, "김담당")]
    assert (
        changes[1].change_text
        == "자동 갱신 끔 → 켬 · 확인 시각 07:00 → 08:30 · 기준 확보율 80% → 75%"
    )
    assert changes[0].change_text == "자동 갱신 켬 → 끔"
    assert repository.list_auto_official_update_setting_changes(limit=1)[0].version == 2


def test_a_stale_settings_edit_is_refused(repository: DuckDBScenarioRepository) -> None:
    repository.replace_auto_official_update_settings(DEFAULT_CONFIG, expected_version=0)

    with pytest.raises(AutoOfficialUpdateSettingsConflict, match="v0 · 지금 v1"):
        repository.replace_auto_official_update_settings(
            AutoUpdateConfig(True, time(7, 0), "PSM", 0.8), expected_version=0
        )
    assert not repository.load_auto_official_update_settings().config.enabled


def test_a_run_key_is_claimed_once(repository: DuckDBScenarioRepository) -> None:
    first = _claim(repository, "scheduled:2026-10-15")
    again = _claim(repository, "scheduled:2026-10-15")
    other_day = _claim(repository, "scheduled:2026-10-16")

    assert first is not None and other_day is not None and again is None
    run = repository.load_auto_official_update_run(first)
    assert (run.status, run.stage, run.trigger_kind, run.run_date) == (
        STATUS_RUNNING,
        "claim",
        TRIGGER_SCHEDULED,
        date(2026, 10, 15),
    )
    assert {item.run_id for item in repository.list_auto_official_update_runs()} == {
        first,
        other_day,
    }


def test_only_progress_columns_can_be_rewritten(repository: DuckDBScenarioRepository) -> None:
    run_id = _claim(repository, "manual:1")
    assert run_id is not None

    repository.update_auto_official_update_run(
        run_id,
        {
            "status": STATUS_SKIPPED,
            "stage": "select",
            "reason": "새 코드 없음",
            "finished_at": datetime(2026, 10, 15, 7, 1),
            "candidate_count": 0,
        },
    )

    run = repository.load_auto_official_update_run(run_id)
    assert (run.status, run.stage, run.reason, run.candidate_count) == (
        STATUS_SKIPPED,
        "select",
        "새 코드 없음",
        0,
    )
    with pytest.raises(KeyError, match="run_key"):
        repository.update_auto_official_update_run(run_id, {"run_key": "다른 키"})
    with pytest.raises(KeyError, match="찾을 수 없습니다"):
        repository.update_auto_official_update_run("없는 회차", {"reason": "x"})
    with pytest.raises(KeyError):
        repository.load_auto_official_update_run("없는 회차")


def test_runs_left_running_by_a_stopped_app_are_closed_as_errors(
    repository: DuckDBScenarioRepository,
) -> None:
    stale = _claim(repository, "scheduled:2026-10-14")
    fresh = repository.claim_auto_official_update_run(
        run_key="manual:new",
        trigger_kind=TRIGGER_MANUAL,
        run_date=date(2026, 10, 15),
        started_at=datetime(2026, 10, 15, 9, 0),
        keyword="PSM",
        threshold=0.8,
        settings_version=0,
    )
    assert stale is not None and fresh is not None

    closed = repository.abandon_running_auto_official_update_runs(
        started_before=datetime(2026, 10, 15, 8, 0),
        finished_at=datetime(2026, 10, 15, 8, 0),
        reason="앱이 꺼져 중단됐습니다.",
    )

    assert closed == 1
    assert repository.load_auto_official_update_run(stale).status == STATUS_ERROR
    assert repository.load_auto_official_update_run(fresh).status == STATUS_RUNNING
    assert (
        repository.abandon_running_auto_official_update_runs(
            started_before=datetime(2026, 10, 15, 8, 0),
            finished_at=datetime(2026, 10, 15, 8, 0),
            reason="다시",
        )
        == 0
    )


def test_exclusions_are_listed_by_run_or_by_filtered_revision(
    repository: DuckDBScenarioRepository,
) -> None:
    rows = [
        AutoOfficialUpdateExclusion("run-1", "rev-2", "B", "INHERITED", None, None),
        AutoOfficialUpdateExclusion("run-1", "rev-2", "A", "AUTO", 0.5, 202611),
        AutoOfficialUpdateExclusion("run-2", None, "C", "AUTO", 0.1, 202701),
    ]
    repository.record_auto_official_update_exclusions(rows)
    repository.record_auto_official_update_exclusions([])

    by_run = repository.list_auto_official_update_exclusions(run_ids=["run-1"])
    by_revision = repository.list_auto_official_update_exclusions(filtered_revision_ids=["rev-2"])

    assert [(row.process, row.kind) for row in by_run] == [("A", "AUTO"), ("B", "INHERITED")]
    assert by_run == by_revision
    assert by_run[0].min_rate == 0.5 and by_run[0].min_month == 202611
    assert repository.list_auto_official_update_exclusions(run_ids=[]) == []
    assert len(repository.list_auto_official_update_exclusions()) == 3


def test_deleting_the_scenario_a_run_made_keeps_the_run_log(
    repository: DuckDBScenarioRepository,
) -> None:
    """기록은 시나리오 소유가 아니다 — 소유 컬럼이 있으면 시나리오 삭제가 함께 지운다."""
    release = ensure_initial_scenario(repository).release
    assert release is not None
    official = repository.load_revision(release.revision_id)
    copied = repository.create_scenario(
        ScenarioCreate(
            scenario_name=f"{official.scenario.scenario_name} 사본",
            source_simulation_code="COPY-1",
            source_simulation_name="사본",
            source_type="TEST",
            pipeline_version="test",
        ),
        official.tables,
        official.preset,
    )
    run_id = _claim(repository, "manual:delete")
    assert run_id is not None
    repository.update_auto_official_update_run(
        run_id,
        {
            "created_scenario_id": copied.scenario.scenario_id,
            "base_revision_id": copied.revision.revision_id,
        },
    )
    repository.record_auto_official_update_exclusions(
        [
            AutoOfficialUpdateExclusion(
                run_id, copied.revision.revision_id, "DEMO_Chip_Attach", "AUTO", 0.5, 202601
            )
        ]
    )

    repository.delete_scenario(copied.scenario.scenario_id)

    assert repository.load_auto_official_update_run(run_id).created_scenario_id == (
        copied.scenario.scenario_id
    )
    assert len(repository.list_auto_official_update_exclusions(run_ids=[run_id])) == 1


def test_a_revision_preset_is_read_without_its_tables(
    repository: DuckDBScenarioRepository,
) -> None:
    release = ensure_initial_scenario(repository).release
    assert release is not None

    preset = repository.load_revision_preset(release.revision_id)

    assert preset == repository.load_revision(release.revision_id).preset
    assert set(REVISION_TABLES) <= set(repository.load_revision(release.revision_id).tables)
