"""Streamlit registration workflow for the company BigDataQuery adapter."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import streamlit as st

from capa_simulation.io.company_bigdataquery_adapter import (
    BigDataQueryCoreDataProvider,
    is_bigdataquery_adapter_configured,
)
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import activate_persisted_snapshot
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.services.core_data_pipeline import fetch_core_data_dataset

PIPELINE_VERSION = "bigdataquery-core-data-v2"


def render_bigdataquery_registration(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    st.subheader("BigDataQuery 시나리오 등록")
    st.caption(
        "시뮬레이션 코드를 조회해 반환된 pandas DataFrame을 검증한 뒤, CSV 파일 없이 "
        "typed raw와 RQ 16개를 한 트랜잭션으로 저장합니다."
    )
    configured = is_bigdataquery_adapter_configured()
    if configured:
        st.success("사내 BigDataQuery SQL 설정이 준비되었습니다.")
    else:
        st.warning(
            "사내 SQL과 DB→Core Data 컬럼 매핑이 아직 비어 있습니다. "
            "company_bigdataquery_adapter.py의 사내 환경 설정 영역을 먼저 채우세요."
        )
    official = repository.latest_official_release()
    if official is None:
        st.error("표시순서 기준으로 사용할 공식버전이 없습니다. 공식버전을 먼저 지정하세요.")
        return
    with st.form("bigdataquery_registration_form"):
        simulation_code = st.text_input("조회할 시뮬레이션 코드")
        source_name = st.text_input("원천 시뮬레이션명")
        scenario_name = st.text_input("저장할 시나리오명")
        revision_name = st.text_input("초기 리비전명", value="초기 리비전")
        source_registered_text = st.text_input(
            "원천 DB 등록시점 (선택)",
            placeholder="2026-08-29 14:30:00",
        )
        note = st.text_area("등록 메모", height=90)
        submitted = st.form_submit_button(
            "DB 조회 후 시나리오 저장",
            icon=":material/cloud_download:",
            type="primary",
            width="stretch",
            disabled=not configured,
        )
    if not submitted:
        return
    try:
        registered_at = _optional_datetime(source_registered_text)
        display_order = load_scenario_snapshot(
            database_path,
            official.revision_id,
        ).tables["RQ_DISPLAY_ORDER"]
        provider = BigDataQueryCoreDataProvider(
            simulation_name=source_name,
            source_registered_at=registered_at,
        )
        with st.spinner("사내 DB에서 Core Data를 조회하고 검증하는 중입니다..."):
            prepared = fetch_core_data_dataset(provider, simulation_code, display_order)
            preset = capture_scenario_preset(prepared.reference_tables)
            available = set(
                prepared.reference_tables["RQ_REQB"]["공정"]
                .astype("string")
                .str.strip()
                .dropna()
                .tolist()
            )
            preset = replace(
                preset,
                included_processes=tuple(
                    process for process in preset.included_processes if process in available
                ),
            )
            snapshot = repository.create_scenario(
                ScenarioCreate(
                    scenario_name=scenario_name,
                    source_simulation_code=prepared.batch.simulation_code,
                    source_simulation_name=prepared.batch.simulation_name,
                    source_type=prepared.batch.source_type,
                    pipeline_version=PIPELINE_VERSION,
                    source_registered_at=prepared.batch.source_registered_at,
                ),
                prepared.reference_tables,
                preset,
                source_data=prepared.source_data,
                revision_name=revision_name,
                note=note.strip() or None,
            )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        activate_persisted_snapshot(snapshot)
        st.success(
            f"{snapshot.scenario.scenario_name}을 저장하고 r{snapshot.revision.revision_no}을 "
            "활성화했습니다."
        )
        st.rerun()


def _optional_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("원천 DB 등록시점은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다.") from exc
