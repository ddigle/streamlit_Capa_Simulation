# Purpose: Initialize an empty scenario store from Git-tracked, non-sensitive seed data.

"""Initialize an empty scenario store from Git-tracked, non-sensitive seed data."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from capa_simulation.persistence.models import (
    OfficialReleaseSummary,
    ScenarioCreate,
    ScenarioPreset,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import (
    BUILTIN_SEED_MONTHS,
    BUILTIN_SEED_PIPELINE_VERSION,
    BUILTIN_SEED_RELEASE_NAME,
    BUILTIN_SEED_REVISION_NAME,
    BUILTIN_SEED_SCENARIO_NAME,
    BUILTIN_SEED_SOURCE_CODE,
    build_builtin_seed_dataset,
    builtin_seed_processes,
)

InitialScenarioBootstrapStatus = Literal[
    "existing_official",
    "created_builtin_seed",
    "repaired_builtin_seed",
    "existing_without_official",
]


@dataclass(frozen=True)
class InitialScenarioBootstrap:
    status: InitialScenarioBootstrapStatus
    release: OfficialReleaseSummary | None


_BOOTSTRAP_LOCK = threading.RLock()


def ensure_initial_scenario(
    repository: DuckDBScenarioRepository,
) -> InitialScenarioBootstrap:
    """Create and publish the built-in seed only when the scenario store is empty."""
    with _BOOTSTRAP_LOCK:
        release = repository.latest_official_release()
        if release is not None:
            return InitialScenarioBootstrap("existing_official", release)

        scenarios = repository.list_scenarios()
        interrupted_seed = next(
            (
                scenario
                for scenario in scenarios
                if scenario.status == "ACTIVE"
                and scenario.source_simulation_code == BUILTIN_SEED_SOURCE_CODE
            ),
            None,
        )
        if interrupted_seed is not None:
            release = repository.publish_official_revision(
                interrupted_seed.scenario_id,
                interrupted_seed.active_revision_id,
                release_name=BUILTIN_SEED_RELEASE_NAME,
                note="내장 시드 생성 후 중단된 공식 발행 단계를 복구",
            )
            return InitialScenarioBootstrap("repaired_builtin_seed", release)
        if scenarios:
            return InitialScenarioBootstrap("existing_without_official", None)

        prepared = build_builtin_seed_dataset()
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name=BUILTIN_SEED_SCENARIO_NAME,
                source_simulation_code=prepared.batch.simulation_code,
                source_simulation_name=prepared.batch.simulation_name,
                source_type=prepared.batch.source_type,
                pipeline_version=BUILTIN_SEED_PIPELINE_VERSION,
            ),
            prepared.reference_tables,
            ScenarioPreset(
                start_month=min(BUILTIN_SEED_MONTHS),
                end_month=max(BUILTIN_SEED_MONTHS),
                included_processes=builtin_seed_processes(),
            ),
            source_data=prepared.source_data,
            revision_name=BUILTIN_SEED_REVISION_NAME,
            note="GitHub 소스만으로 실행하기 위한 비민감 합성 기준정보",
        )
        release = repository.publish_official_revision(
            snapshot.scenario.scenario_id,
            snapshot.revision.revision_id,
            release_name=BUILTIN_SEED_RELEASE_NAME,
            note="빈 저장소의 최초 실행을 위한 합성 공식버전",
        )
        return InitialScenarioBootstrap("created_builtin_seed", release)
