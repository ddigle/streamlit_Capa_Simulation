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

        # 보관본만 남아도 빈 저장소가 아니다 — 보관본을 빼고 세면 그 위에 데모가 공식으로 선다.
        scenarios = repository.list_scenarios(include_archived=True)
        # 발행 전에 멈춘 시드는 저장소에 그것 하나뿐이다. 곁에 다른 시나리오가 있으면 보관에서
        # 되돌린 시드이고, 발행하면 공식은 지울 수 없으니 데모가 공식 자리를 차지한다.
        lone_scenario = scenarios[0] if len(scenarios) == 1 else None
        if (
            lone_scenario is not None
            and lone_scenario.status == "ACTIVE"
            and lone_scenario.source_simulation_code == BUILTIN_SEED_SOURCE_CODE
        ):
            release = repository.publish_official_revision(
                lone_scenario.scenario_id,
                lone_scenario.active_revision_id,
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
