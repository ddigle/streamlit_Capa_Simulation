# Purpose: 자동 갱신 한 회차를 가짜 BigDataQuery·주입 시계로 돌려 등록·판정·발행·기록을 검증한다.

"""자동 갱신 한 회차(`auto_official_update_runner.run_auto_official_update`).

사외에서는 BigDataQuery 를 부를 수 없다 — 목록·상세 조회는 가짜를, 원천은 내장 합성 시드의
78컬럼을 쓴다(공정 셋, 확보율 245~1,270% — 샘플 관측, `services/builtin_seed.py` 의 리터럴).
확보율을 낮추려면 그 달의 `설비보유` 를 `설비대여평가` 와 같게 해 가용을 0 으로 만든다.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

import capa_simulation.auto_official_update_runner as runner
from capa_simulation.auto_official_update_runner import (
    ALREADY_CLAIMED_MESSAGE,
    BUSY_MESSAGE,
    AutoUpdateSources,
    DetailRequest,
    abandon_interrupted_runs,
    current_official_baseline,
    run_auto_official_update,
)
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.io.core_data_source import CoreDataBatch, CoreDataProvider
from capa_simulation.persistence.models import (
    AutoOfficialUpdateRun,
    OfficialReleaseSummary,
    ScenarioPreset,
    ScenarioSnapshot,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import (
    BIGDATAQUERY_PIPELINE_VERSION,
    save_bigdataquery_scenario,
)
from capa_simulation.services.auto_official_update import (
    FILTERED_REVISION_NAME,
    MISSING_WEEK_MESSAGE,
    STATUS_ERROR,
    STATUS_PUBLISH_SKIPPED,
    STATUS_PUBLISHED,
    STATUS_SKIPPED,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    AutoUpdateConfig,
    MissingOfficialWeek,
)
from capa_simulation.services.builtin_seed import (
    build_builtin_seed_dataset,
    load_builtin_display_order,
)
from capa_simulation.services.core_data_pipeline import prepare_core_data_dataset
from capa_simulation.services.simulation_cache import CapacityOutcome, full_capacity_outcome

NOW = datetime(2026, 10, 15, 7, 0)
WAFER = "DEMO_Wafer_Inspect"
CHIP = "DEMO_Chip_Attach"
FINAL = "DEMO_Final_Test"
ALL_PROCESSES = (CHIP, FINAL, WAFER)
SEED_SOURCE = build_builtin_seed_dataset().source_data
DISPLAY_ORDER = load_builtin_display_order()


def _clock() -> datetime:
    return NOW


def _source(
    *,
    zero_available: Sequence[tuple[str, int]] = (),
    missing_available: Sequence[tuple[str, int]] = (),
    broken_run_rate_month: int | None = None,
) -> pd.DataFrame:
    """내장 시드 원천의 사본. 고른 (공정, 달)의 가용을 0 으로 만들거나 비우고, 가동률을 깨뜨린다."""
    frame = SEED_SOURCE.copy()
    for process, month in zero_available:
        mask = frame["공정"].eq(process) & frame["생산계획년월"].eq(month)
        frame.loc[mask, "설비보유"] = frame.loc[mask, "설비대여평가"]
    for process, month in missing_available:
        mask = frame["공정"].eq(process) & frame["생산계획년월"].eq(month)
        frame.loc[mask, ["설비보유", "설비대여평가"]] = pd.NA
    if broken_run_rate_month is not None:
        mask = frame["생산계획년월"].eq(broken_run_rate_month) & frame["공정"].notna()
        frame.loc[mask, "CAPA_RUN_RATE"] = pd.NA
    return frame


def _catalog(*rows: tuple[str, str, str]) -> pd.DataFrame:
    """(시뮬레이션명, 코드, 원천 등록시각) 행의 목록 조회 결과(계약 5컬럼)."""
    return pd.DataFrame(
        {
            "simulation_name": [row[0] for row in rows],
            "simulation_code": [row[1] for row in rows],
            "plan_name": ["PLAN A" for _ in rows],
            "plan_code": ["PLAN-A" for _ in rows],
            "regist_data": [row[2] for row in rows],
        }
    )


@dataclass
class _FakeProvider:
    request: DetailRequest
    frame: pd.DataFrame

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        return CoreDataBatch(
            simulation_code=simulation_code,
            simulation_name=self.request.simulation_name,
            source_type="BIGDATAQUERY",
            frame=self.frame.copy(),
            source_registered_at=self.request.registered_at,
        )


@dataclass
class FakeBigDataQuery:
    """목록·상세 조회 가짜. 부른 기간과 요청을 남긴다."""

    catalog: pd.DataFrame
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    catalog_windows: list[QueryWindow] = field(default_factory=list)
    requests: list[DetailRequest] = field(default_factory=list)

    def fetch_catalog(self, window: QueryWindow) -> pd.DataFrame:
        self.catalog_windows.append(window)
        return self.catalog.copy()

    def provider(self, request: DetailRequest) -> CoreDataProvider:
        self.requests.append(request)
        return _FakeProvider(request, self.frames.get(request.simulation_code, _source()))

    @property
    def sources(self) -> AutoUpdateSources:
        return AutoUpdateSources(fetch_catalog=self.fetch_catalog, detail_provider=self.provider)


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "auto_runner.duckdb")
    repository.initialize()
    repository.initialize_global_display_order(DISPLAY_ORDER)
    return repository


def _register(
    repository: DuckDBScenarioRepository,
    *,
    code: str,
    name: str,
    registered_at: datetime,
    frame: pd.DataFrame | None = None,
    legacy: tuple[float, float] = (1.095, 0.995),
) -> ScenarioSnapshot:
    """화면 등록과 같은 길로 한 코드를 시나리오로 저장한다."""
    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code=code,
            simulation_name=name,
            source_type="BIGDATAQUERY",
            frame=_source() if frame is None else frame,
            source_registered_at=registered_at,
        ),
        DISPLAY_ORDER,
    )
    return save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(
            prepared.reference_tables, secure_threshold=legacy[0], warning_threshold=legacy[1]
        ),
        scenario_name=f"{name} ({code})",
        revision_name="초기 리비전",
        note="",
    )


def _save_filtered(
    repository: DuckDBScenarioRepository, snapshot: ScenarioSnapshot, included: Sequence[str]
) -> ScenarioSnapshot:
    """사람이 공정 필터에서 공정을 빼고 리비전을 저장한 것."""
    return repository.save_revision(
        snapshot.scenario.scenario_id,
        {name: snapshot.tables[name] for name in REVISION_TABLES},
        ScenarioPreset(
            start_month=snapshot.preset.start_month,
            end_month=snapshot.preset.end_month,
            included_processes=tuple(included),
            secure_threshold=snapshot.preset.secure_threshold,
            warning_threshold=snapshot.preset.warning_threshold,
        ),
        revision_name="수동 공정 필터",
        parent_revision_id=snapshot.revision.revision_id,
    )


def _publish(
    repository: DuckDBScenarioRepository, snapshot: ScenarioSnapshot
) -> OfficialReleaseSummary:
    return repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=f"{snapshot.scenario.scenario_name} 공식안",
    )


def _official_w40(repository: DuckDBScenarioRepository, **kwargs: object) -> ScenarioSnapshot:
    snapshot = _register(
        repository,
        code="SIM-W40",
        name="PSM W40",
        registered_at=datetime(2026, 10, 5, 9, 0),
        **kwargs,  # type: ignore[arg-type]
    )
    _publish(repository, snapshot)
    return snapshot


def _run(
    repository: DuckDBScenarioRepository,
    fake: FakeBigDataQuery,
    *,
    trigger: str = TRIGGER_MANUAL,
    **kwargs: object,
) -> AutoOfficialUpdateRun:
    result = run_auto_official_update(
        repository,
        trigger=trigger,  # type: ignore[arg-type]
        sources=fake.sources,
        clock=_clock,
        **kwargs,  # type: ignore[arg-type]
    )
    assert result.not_run_reason is None
    assert result.run is not None
    return result.run


def test_without_a_week_on_the_official_version_nothing_happens(
    repository: DuckDBScenarioRepository,
) -> None:
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    ensure_initial_scenario(repository)
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_ERROR, "baseline")
    assert run.reason is not None and MISSING_WEEK_MESSAGE in run.reason
    assert fake.catalog_windows == [] and fake.requests == []
    assert len(repository.list_scenarios()) == 1
    with pytest.raises(MissingOfficialWeek):
        current_official_baseline(repository)


def test_an_empty_store_has_no_official_week(repository: DuckDBScenarioRepository) -> None:
    with pytest.raises(MissingOfficialWeek, match="아직 공식버전이 없습니다"):
        current_official_baseline(repository)


def test_no_newer_code_only_records_a_skip(repository: DuckDBScenarioRepository) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(
        _catalog(
            ("PSM W40", "SIM-W40", "2026-10-05 09:00:00"),
            ("PSM W39", "SIM-W39", "2026-10-08 09:00:00"),
            ("PSS W45", "SIM-PSS", "2026-10-14 09:00:00"),
        )
    )

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_SKIPPED, "select")
    assert run.reason is not None and run.reason.startswith("새 코드 없음")
    assert (run.baseline_release_no, run.baseline_week, run.candidate_count) == (1, 40, 0)
    assert fake.catalog_windows == [
        QueryWindow(start_date=date(2026, 9, 15), end_date=date(2026, 10, 15))
    ]
    assert fake.requests == []
    assert len(repository.list_scenarios()) == 1
    assert repository.latest_official_release() is not None
    assert repository.latest_official_release().release_no == 1  # type: ignore[union-attr]


def test_a_new_week_is_registered_judged_and_published(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository, legacy=(1.10, 1.00))
    fake = FakeBigDataQuery(
        _catalog(
            ("PSM W41", "SIM-W41", "2026-10-11 09:00:00"),
            ("PSM W41", "SIM-W41", "2026-10-12 09:00:00"),
        ),
        frames={"SIM-W41": _source(zero_available=[(WAFER, 202603)])},
    )
    published: list[str] = []

    run = _run(repository, fake, after_publish=lambda: published.append("cleared"))

    assert (run.status, run.stage) == (STATUS_PUBLISHED, "done")
    assert (run.simulation_code, run.simulation_week, run.official_release_no) == (
        "SIM-W41",
        41,
        2,
    )
    assert run.source_registered_at == datetime(2026, 10, 12, 9, 0)
    assert (run.auto_off_count, run.inherited_off_count) == (1, 0)
    assert published == ["cleared"]
    # 상세 조회는 화면 등록의 기본 창과 같다 — 등록일 7일 전 ~ 3일 뒤(오늘을 넘지 않는다).
    request = fake.requests[0]
    assert request.window == QueryWindow(start_date=date(2026, 10, 4), end_date=date(2026, 10, 15))
    assert run.detail_window == "2026-10-04 ~ 2026-10-15"

    release = repository.latest_official_release()
    assert release is not None and release.release_no == 2
    assert release.release_name == "PSM W41 (SIM-W41) 공식안"
    assert release.note == "자동 갱신 · 기준 확보율 80% · off 1공정 · 이어받은 수동 off 0공정"
    assert release.revision_id == run.filtered_revision_id

    base = repository.load_revision(str(run.base_revision_id))
    filtered = repository.load_revision(str(run.filtered_revision_id))
    assert base.scenario.scenario_name == run.created_scenario_name == "PSM W41 (SIM-W41)"
    assert base.scenario.source_registered_at == datetime(2026, 10, 12, 9, 0)
    assert base.revision.revision_no == 1 and base.preset.included_processes == ALL_PROCESSES
    assert base.revision.note is not None
    assert base.revision.note.startswith("자동 갱신 등록 · 원천 PLAN PLAN A(PLAN-A)")
    assert base.revision.note.endswith("상세 조회기간 2026-10-04 ~ 2026-10-15")
    assert (filtered.revision.revision_no, filtered.revision.revision_name) == (
        2,
        FILTERED_REVISION_NAME,
    )
    assert filtered.revision.parent_revision_id == base.revision.revision_id
    assert filtered.preset.included_processes == (CHIP, FINAL)
    # 레거시 확보·경고 값은 직전 공식버전 프리셋에서 실어 온다.
    assert (filtered.preset.secure_threshold, filtered.preset.warning_threshold) == (1.10, 1.00)
    assert filtered.scenario.active_revision_id == filtered.revision.revision_id

    exclusions = repository.list_auto_official_update_exclusions(run_ids=[run.run_id])
    assert [(row.process, row.kind, row.min_rate, row.min_month) for row in exclusions] == [
        (WAFER, "AUTO", 0.0, 202603)
    ]
    assert exclusions[0].filtered_revision_id == run.filtered_revision_id


def test_the_auto_registration_saves_like_the_manual_one(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    scenario = next(
        item for item in repository.list_scenarios() if item.scenario_id == run.created_scenario_id
    )
    assert (scenario.source_simulation_code, scenario.source_simulation_name) == (
        "SIM-W41",
        "PSM W41",
    )
    assert scenario.source_type == "BIGDATAQUERY"
    assert BIGDATAQUERY_PIPELINE_VERSION == "bigdataquery-core-data-v5"
    assert repository.load_source_row_count(scenario.scenario_id) == len(SEED_SOURCE)


def test_an_already_registered_code_is_skipped_even_if_archived(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    archived = _register(
        repository, code="SIM-W42", name="PSM W42", registered_at=datetime(2026, 10, 13, 9, 0)
    )
    repository.archive_scenario(archived.scenario.scenario_id)
    fake = FakeBigDataQuery(
        _catalog(
            ("PSM W42", "SIM-W42", "2026-10-13 09:00:00"),
            ("PSM W41", "SIM-W41", "2026-10-12 09:00:00"),
        )
    )

    run = _run(repository, fake)

    assert run.status == STATUS_PUBLISHED and run.simulation_code == "SIM-W41"


def test_the_same_week_is_taken_when_a_newer_code_arrives(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(
        _catalog(
            ("PSM W40 수정", "SIM-W40B", "2026-10-07 09:00:00"),
            ("PSM W40 옛", "SIM-W40A", "2026-10-03 09:00:00"),
        )
    )

    run = _run(repository, fake)

    assert run.status == STATUS_PUBLISHED and run.simulation_code == "SIM-W40B"
    assert run.candidate_count == 1


def test_a_manual_off_on_the_previous_official_is_inherited(
    repository: DuckDBScenarioRepository,
) -> None:
    base = _register(
        repository, code="SIM-W40", name="PSM W40", registered_at=datetime(2026, 10, 5, 9, 0)
    )
    _publish(repository, _save_filtered(repository, base, (CHIP, WAFER)))
    fake = FakeBigDataQuery(
        _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
        # 손으로 뺀 공정이 이번에 기준 미만이어도 이어받은 수동 off 로 남는다.
        frames={"SIM-W41": _source(zero_available=[(FINAL, 202605), (WAFER, 202603)])},
    )

    run = _run(repository, fake)

    assert run.status == STATUS_PUBLISHED
    assert (run.auto_off_count, run.inherited_off_count) == (1, 1)
    filtered = repository.load_revision(str(run.filtered_revision_id))
    assert filtered.preset.included_processes == (CHIP,)
    rows = repository.list_auto_official_update_exclusions(run_ids=[run.run_id])
    assert [(row.process, row.kind, row.min_month) for row in rows] == [
        (WAFER, "AUTO", 202603),
        (FINAL, "INHERITED", 202605),
    ]
    release = repository.latest_official_release()
    assert release is not None and release.note is not None
    assert release.note.endswith("off 1공정 · 이어받은 수동 off 1공정")


def test_an_earlier_auto_off_is_judged_again_and_a_later_manual_off_is_kept(
    repository: DuckDBScenarioRepository,
) -> None:
    """자동 리비전 2 에서 사람이 리비전 3 을 저장해 발행해도 리비전 2 의 자동 off 는 자동이다."""
    _official_w40(repository)
    first = _run(
        repository,
        FakeBigDataQuery(
            _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
            frames={"SIM-W41": _source(zero_available=[(WAFER, 202603)])},
        ),
    )
    auto_revision = repository.load_revision(str(first.filtered_revision_id))
    _publish(repository, _save_filtered(repository, auto_revision, (FINAL,)))

    second = _run(
        repository,
        FakeBigDataQuery(_catalog(("PSM W42", "SIM-W42", "2026-10-14 09:00:00"))),
    )

    assert second.status == STATUS_PUBLISHED
    assert (second.auto_off_count, second.inherited_off_count) == (0, 1)
    filtered = repository.load_revision(str(second.filtered_revision_id))
    # WAFER 는 이번 데이터에서 기준을 넘어 돌아오고, 사람이 뺀 CHIP 은 그대로 빠진다.
    assert filtered.preset.included_processes == (FINAL, WAFER)


def test_a_broken_capacity_calculation_registers_but_does_not_publish(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(
        _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
        frames={"SIM-W41": _source(broken_run_rate_month=202612)},
    )

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_PUBLISH_SKIPPED, "judge")
    assert run.reason is not None and "Capa 계산이 실패" in run.reason
    assert run.base_revision_id is not None and run.filtered_revision_id is None
    assert len(repository.list_revisions(str(run.created_scenario_id))) == 1
    release = repository.latest_official_release()
    assert release is not None and release.release_no == 1


def test_a_securement_failure_registers_but_does_not_publish(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(
        _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
        frames={"SIM-W41": _source(missing_available=[(WAFER, 202603)])},
    )

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_PUBLISH_SKIPPED, "judge")
    assert run.reason is not None and "확보율 계산이 실패" in run.reason
    assert run.created_scenario_id is not None and run.filtered_revision_id is None
    assert repository.latest_official_release().release_no == 1  # type: ignore[union-attr]


def test_when_every_process_is_off_nothing_is_published(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(
        _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
        frames={"SIM-W41": _source(zero_available=[(name, 202604) for name in ALL_PROCESSES])},
    )

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_PUBLISH_SKIPPED, "judge")
    assert run.reason is not None and "남는 공정이 없어" in run.reason
    assert run.filtered_revision_id is None and run.auto_off_count == 3
    rows = repository.list_auto_official_update_exclusions(run_ids=[run.run_id])
    assert {row.process for row in rows} == set(ALL_PROCESSES)
    assert all(row.filtered_revision_id is None for row in rows)
    assert repository.latest_official_release().release_no == 1  # type: ignore[union-attr]


def test_a_failed_publish_check_keeps_the_filtered_revision(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    _official_w40(repository)
    real = full_capacity_outcome
    calls: list[int] = []

    def fail_on_publish_check(scenario_tables: object, reference_tables: object) -> CapacityOutcome:
        calls.append(1)
        if len(calls) == 1:
            return real(scenario_tables, reference_tables)  # type: ignore[arg-type]
        return CapacityOutcome(None, None, "RQ_RUN_RATE 시험 오류")

    monkeypatch.setattr(runner, "full_capacity_outcome", fail_on_publish_check)
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_PUBLISH_SKIPPED, "publish")
    assert run.reason is not None and "RQ_RUN_RATE 시험 오류" in run.reason
    assert run.filtered_revision_id is not None and run.official_release_no is None
    assert repository.latest_official_release().release_no == 1  # type: ignore[union-attr]


def test_a_scheduled_day_runs_once_and_manual_runs_always_run(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(_catalog(("PSM W39", "SIM-W39", "2026-10-01 09:00:00")))

    first = run_auto_official_update(
        repository, trigger=TRIGGER_SCHEDULED, sources=fake.sources, clock=_clock
    )
    again = run_auto_official_update(
        repository, trigger=TRIGGER_SCHEDULED, sources=fake.sources, clock=_clock
    )
    other_day = run_auto_official_update(
        repository,
        trigger=TRIGGER_SCHEDULED,
        run_day=date(2026, 10, 16),
        sources=fake.sources,
        clock=_clock,
    )
    manual = [
        run_auto_official_update(
            repository, trigger=TRIGGER_MANUAL, sources=fake.sources, clock=_clock
        )
        for _ in range(2)
    ]

    assert first.run is not None and first.run.run_key == "scheduled:2026-10-15"
    assert (again.run, again.not_run_reason) == (None, ALREADY_CLAIMED_MESSAGE)
    assert other_day.run is not None and other_day.run.run_date == date(2026, 10, 16)
    assert all(result.run is not None for result in manual)
    assert len(repository.list_auto_official_update_runs()) == 4


def test_overlapping_runs_in_one_process_do_not_claim(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    fake = FakeBigDataQuery(_catalog())
    started = threading.Event()
    release = threading.Event()

    def slow_catalog(window: QueryWindow) -> pd.DataFrame:
        started.set()
        release.wait(timeout=10)
        return fake.fetch_catalog(window)

    results: list[object] = []
    worker = threading.Thread(
        target=lambda: results.append(
            run_auto_official_update(
                repository,
                trigger=TRIGGER_SCHEDULED,
                sources=AutoUpdateSources(
                    fetch_catalog=slow_catalog, detail_provider=fake.provider
                ),
                clock=_clock,
            )
        )
    )
    worker.start()
    try:
        assert started.wait(timeout=10)
        overlapping = run_auto_official_update(
            repository, trigger=TRIGGER_MANUAL, sources=fake.sources, clock=_clock
        )
    finally:
        release.set()
        worker.join(timeout=30)

    assert (overlapping.run, overlapping.not_run_reason) == (None, BUSY_MESSAGE)
    assert len(results) == 1
    assert len(repository.list_auto_official_update_runs()) == 1


def test_a_catalog_failure_is_recorded_with_its_stage(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)

    def unavailable(window: QueryWindow) -> pd.DataFrame:
        raise RuntimeError("현재 환경에 bigdataquery 패키지가 없습니다.")

    result = run_auto_official_update(
        repository,
        trigger=TRIGGER_MANUAL,
        sources=AutoUpdateSources(fetch_catalog=unavailable),
        clock=_clock,
    )

    assert result.run is not None
    assert (result.run.status, result.run.stage) == (STATUS_ERROR, "catalog")
    assert result.run.reason == (
        "목록 조회 단계에서 멈췄습니다 — 현재 환경에 bigdataquery 패키지가 없습니다."
    )
    assert result.run.finished_at == NOW


def test_a_registration_failure_keeps_nothing_half_made(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    # 같은 이름의 다른 코드 시나리오가 이미 있다 — 이름 중복으로 저장이 막힌다.
    _register(
        repository, code="SIM-OTHER", name="PSM W41", registered_at=datetime(2026, 10, 1, 9, 0)
    )
    repository.rename_scenario(
        next(
            item.scenario_id
            for item in repository.list_scenarios()
            if item.source_simulation_code == "SIM-OTHER"
        ),
        "PSM W41 (SIM-W41)",
    )
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    assert (run.status, run.stage) == (STATUS_ERROR, "register")
    assert run.reason is not None and "같은 이름의 시나리오" in run.reason
    assert run.created_scenario_id is None
    assert len(repository.list_scenarios()) == 2


def test_an_unexpected_error_names_its_type(repository: DuckDBScenarioRepository) -> None:
    _official_w40(repository)

    def broken_provider(request: DetailRequest) -> CoreDataProvider:
        raise TypeError("예상하지 못한 결함")

    result = run_auto_official_update(
        repository,
        trigger=TRIGGER_MANUAL,
        sources=AutoUpdateSources(
            fetch_catalog=FakeBigDataQuery(
                _catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00"))
            ).fetch_catalog,
            detail_provider=broken_provider,
        ),
        clock=_clock,
    )

    assert result.run is not None
    assert result.run.status == STATUS_ERROR and result.run.stage == "register"
    assert result.run.reason == "상세 조회·등록 단계에서 멈췄습니다 — TypeError: 예상하지 못한 결함"


def test_a_failing_cache_clear_after_publishing_still_counts_as_published(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)

    def failing_clear() -> None:
        raise RuntimeError("캐시 정리 실패")

    run = _run(
        repository,
        FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00"))),
        after_publish=failing_clear,
    )

    assert run.status == STATUS_PUBLISHED


def test_the_keyword_and_threshold_come_from_the_saved_settings(
    repository: DuckDBScenarioRepository,
) -> None:
    _official_w40(repository)
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=True, check_time=NOW.time(), keyword="WEEKLY", threshold=0.5),
        expected_version=0,
    )
    fake = FakeBigDataQuery(
        _catalog(
            ("PSM W43", "SIM-PSM", "2026-10-14 09:00:00"),
            ("weekly W41", "SIM-WEEKLY", "2026-10-12 09:00:00"),
        ),
        frames={"SIM-WEEKLY": _source(zero_available=[(WAFER, 202603)])},
    )

    run = _run(repository, fake)

    assert (run.keyword, run.threshold, run.settings_version) == ("WEEKLY", 0.5, 1)
    assert run.simulation_code == "SIM-WEEKLY"
    release = repository.latest_official_release()
    assert release is not None and release.note is not None
    assert "기준 확보율 50%" in release.note


def test_runs_cut_off_by_a_stopped_app_are_closed(repository: DuckDBScenarioRepository) -> None:
    run_id = repository.claim_auto_official_update_run(
        run_key="scheduled:2026-10-14",
        trigger_kind=TRIGGER_SCHEDULED,
        run_date=date(2026, 10, 14),
        started_at=datetime(2026, 10, 14, 7, 0),
        keyword="PSM",
        threshold=0.8,
        settings_version=0,
    )
    assert run_id is not None

    closed = abandon_interrupted_runs(repository, started_before=NOW, now=NOW)

    run = repository.load_auto_official_update_run(run_id)
    assert closed == 1 and run.status == STATUS_ERROR
    assert run.reason == runner.INTERRUPTED_REASON
