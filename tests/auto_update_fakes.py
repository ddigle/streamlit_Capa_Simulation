# Purpose: 자동 갱신 시험들이 함께 쓰는 가짜 BigDataQuery·합성 원천·등록·발행 도우미를 둔다.

"""자동 갱신 시험의 공용 대역.

사외에서는 BigDataQuery 를 부를 수 없다 — 목록·상세 조회는 가짜를, 원천은 내장 합성 시드의
78컬럼을 쓴다(공정 셋, 확보율 245~1,270% — 샘플 관측, `services/builtin_seed.py` 의 리터럴).
확보율을 낮추려면 그 달의 `설비보유` 를 `설비대여평가` 와 같게 해 가용을 0 으로 만든다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from capa_simulation.auto_official_update_runner import AutoUpdateSources, DetailRequest
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.io.core_data_source import CoreDataBatch, CoreDataProvider
from capa_simulation.persistence.models import OfficialReleaseSummary, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import save_bigdataquery_scenario
from capa_simulation.services.builtin_seed import (
    build_builtin_seed_dataset,
    load_builtin_display_order,
)
from capa_simulation.services.core_data_pipeline import prepare_core_data_dataset

NOW = datetime(2026, 10, 15, 7, 0)
WAFER = "DEMO_Wafer_Inspect"
CHIP = "DEMO_Chip_Attach"
FINAL = "DEMO_Final_Test"
ALL_PROCESSES = (CHIP, FINAL, WAFER)
SEED_SOURCE = build_builtin_seed_dataset().source_data
DISPLAY_ORDER = load_builtin_display_order()


def fixed_clock() -> datetime:
    return NOW


def source_frame(
    *,
    zero_available: Sequence[tuple[str, int]] = (),
    missing_available: Sequence[tuple[str, int]] = (),
    broken_run_rate_month: int | None = None,
    blank_first_plan: bool = False,
) -> pd.DataFrame:
    """내장 시드 원천의 사본. 고른 (공정, 달)의 가용을 0 으로 만들거나 비우고, 가동률을 깨뜨린다.

    `blank_first_plan` 은 첫 계획 행(계획기초정보여부 Y)의 생산수량을 비운다 — 계산은 서고, 그
    계획은 「생산수량이 비어 계획 없음으로 본 계획」으로 소요대수에 들지 않는다(발행은 막지 않고
    건수를 경고한다).
    """
    frame = SEED_SOURCE.copy()
    if blank_first_plan:
        plan = frame["계획기초정보여부"].eq("Y")
        first = frame.loc[plan].iloc[0]
        target = (
            plan
            & frame["제품정보"].eq(first["제품정보"])
            & frame["생산계획년월"].eq(first["생산계획년월"])
        )
        frame.loc[target, "생산수량"] = pd.NA
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


def catalog_frame(*rows: tuple[str, str, str]) -> pd.DataFrame:
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
class FakeProvider:
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
        return FakeProvider(request, self.frames.get(request.simulation_code, source_frame()))

    @property
    def sources(self) -> AutoUpdateSources:
        return AutoUpdateSources(fetch_catalog=self.fetch_catalog, detail_provider=self.provider)


def new_repository(path: Path) -> DuckDBScenarioRepository:
    """마이그레이션과 공용 표시순서까지 마친 빈 시뮬레이션 DB."""
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.initialize_global_display_order(DISPLAY_ORDER)
    return repository


def register_code(
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
            frame=source_frame() if frame is None else frame,
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


def publish_snapshot(
    repository: DuckDBScenarioRepository, snapshot: ScenarioSnapshot
) -> OfficialReleaseSummary:
    return repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=f"{snapshot.scenario.scenario_name} 공식안",
    )


def official_w40(repository: DuckDBScenarioRepository, **kwargs: object) -> ScenarioSnapshot:
    """`PSM W40 (SIM-W40)` 를 등록해 공식버전으로 지정한다 — 자동 갱신이 견줄 W40 기준선."""
    snapshot = register_code(
        repository,
        code="SIM-W40",
        name="PSM W40",
        registered_at=datetime(2026, 10, 5, 9, 0),
        **kwargs,  # type: ignore[arg-type]
    )
    publish_snapshot(repository, snapshot)
    return snapshot
