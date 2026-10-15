# Purpose: BigDataQuery 로 받은 원천을 세션 없이 시나리오(리비전 1)로 저장하는 등록 경로를 제공한다.

"""BigDataQuery 원천 → 시나리오 저장. 화면 등록과 공식버전 자동 갱신이 같은 길을 지난다.

화면(`components/bigdataquery_registration.py`)은 폼 값을 읽고 조회 중 안내를 그리고 저장한 뒤
그 세션에서 새 리비전을 활성화한다. 자동 갱신은 세션이 없는 배경 작업이다. 둘 다 저장 자체 —
원천 메타데이터·파이프라인 버전·리비전 메모의 상세 조회기간 — 는 여기 한 곳에서 정한다. 그래서
자동으로 받은 시나리오와 손으로 받은 시나리오가 같은 꼴로 남는다.

Streamlit 을 import 하지 않고 세션을 읽지 않는다. 프리셋은 부르는 쪽이 만든다 — 화면은 세션의 레거시
확보·경고 값을 실은 `capture_full_data_scenario_preset`, 자동 갱신은 세션 없는
`full_data_scenario_preset` 이다.
"""

from __future__ import annotations

from typing import Final

from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.core_data_pipeline import PreparedCoreDataset

BIGDATAQUERY_PIPELINE_VERSION: Final = "bigdataquery-core-data-v5"


def registration_note(note: str, window: QueryWindow) -> str:
    """리비전 1 메모 — 적은 메모 뒤에 실제로 조회한 상세 기간을 붙인다.

    기간을 넓혀 다시 받은 리비전과 기본 창으로 받은 리비전이 어떻게 다른지 나중에 알 수 있어야 한다.
    """
    return " · ".join(part for part in (note.strip(), f"상세 조회기간 {window.label()}") if part)


def save_bigdataquery_scenario(
    repository: DuckDBScenarioRepository,
    prepared: PreparedCoreDataset,
    preset: ScenarioPreset,
    *,
    scenario_name: str,
    revision_name: str,
    note: str,
) -> ScenarioSnapshot:
    """조회·변환을 마친 원천을 새 시나리오와 리비전 1 로 저장한다. 세션을 활성화하지 않는다.

    이름 중복(보관본 포함)·원천 코드 불변 검사는 저장소가 쓰기 트랜잭션 안에서 한다.
    """
    return repository.create_scenario(
        ScenarioCreate(
            scenario_name=scenario_name,
            source_simulation_code=prepared.batch.simulation_code,
            source_simulation_name=prepared.batch.simulation_name,
            source_type=prepared.batch.source_type,
            pipeline_version=BIGDATAQUERY_PIPELINE_VERSION,
            source_registered_at=prepared.batch.source_registered_at,
        ),
        prepared.reference_tables,
        preset,
        source_data=prepared.source_data,
        revision_name=revision_name,
        note=note,
    )
