"""Streamlit registration workflow for the company BigDataQuery adapter."""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
import streamlit as st

from capa_simulation.io.company_bigdataquery_adapter import (
    BigDataQueryCoreDataProvider,
    is_bigdataquery_adapter_configured,
)
from capa_simulation.persistence.cache import load_global_display_order
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import activate_persisted_snapshot
from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset
from capa_simulation.services.core_data_pipeline import (
    fetch_core_data_dataset,
    reference_conflicts_to_csv,
    summarize_reference_conflicts,
)

PIPELINE_VERSION = "bigdataquery-core-data-v4"
CONFLICT_REPORT_STATE_KEY = "bigdataquery_reference_conflict_report"
REGISTRATION_FLASH_KEY = "bigdataquery_registration_flash"


def render_bigdataquery_registration(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    st.subheader("BigDataQuery 시나리오 등록")
    st.caption(
        "시뮬레이션 코드를 조회해 반환된 pandas DataFrame을 검증한 뒤, CSV 파일 없이 "
        "typed raw와 RQ 16개를 한 트랜잭션으로 저장합니다. 등록 후에는 내려받은 전체 "
        "생산계획년월과 전체 B/N 공정이 기본 활성화됩니다."
    )
    flash = st.session_state.pop(REGISTRATION_FLASH_KEY, None)
    if isinstance(flash, str) and flash:
        st.success(flash)
    configured = is_bigdataquery_adapter_configured()
    if configured:
        st.success("사내 BigDataQuery SQL 설정이 준비되었습니다.")
    else:
        st.warning(
            "사내 SQL과 DB→Core Data 컬럼 매핑이 아직 비어 있습니다. "
            "company_bigdataquery_adapter.py의 사내 환경 설정 영역을 먼저 채우세요."
        )
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
        _render_reference_conflict_report()
        return
    st.session_state.pop(CONFLICT_REPORT_STATE_KEY, None)
    try:
        registered_at = _optional_datetime(source_registered_text)
        display_order = load_global_display_order(database_path).rules
        provider = BigDataQueryCoreDataProvider(
            simulation_name=source_name,
            source_registered_at=registered_at,
        )
        with st.spinner("사내 DB에서 Core Data를 조회하고 검증하는 중입니다..."):
            prepared = fetch_core_data_dataset(provider, simulation_code, display_order)
            _store_reference_conflict_report(
                prepared.reference_conflicts,
                prepared.batch.simulation_code,
            )
            preset = capture_full_data_scenario_preset(prepared.reference_tables)
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
        _render_reference_conflict_report()
    else:
        activate_persisted_snapshot(snapshot)
        st.session_state[REGISTRATION_FLASH_KEY] = (
            f"{snapshot.scenario.scenario_name}을 저장하고 r{snapshot.revision.revision_no}을 "
            "활성화했습니다."
        )
        st.rerun()


def _store_reference_conflict_report(conflicts: pd.DataFrame, simulation_code: str) -> None:
    if conflicts.empty:
        return
    safe_code = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", simulation_code).strip("._")
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    st.session_state[CONFLICT_REPORT_STATE_KEY] = {
        "report": conflicts.copy(),
        "file_name": f"RQ_업무키_충돌_{safe_code or 'query'}_{timestamp}.csv",
    }


def _render_reference_conflict_report() -> None:
    payload = st.session_state.get(CONFLICT_REPORT_STATE_KEY)
    if not isinstance(payload, dict):
        return
    report = payload.get("report")
    file_name = payload.get("file_name")
    if not isinstance(report, pd.DataFrame) or report.empty or not isinstance(file_name, str):
        return
    summary = summarize_reference_conflicts(report)
    st.warning(
        f"{len(report):,}개 업무 키 그룹에서 값 충돌을 확인했습니다. "
        "등록은 중단하지 않고 각 그룹의 원천 첫 행을 임시 적용했습니다."
    )
    st.dataframe(summary, hide_index=True, width="stretch")
    st.download_button(
        "RQ 업무 키 충돌 CSV 다운로드",
        data=reference_conflicts_to_csv(report),
        file_name=file_name,
        mime="text/csv",
        icon=":material/download:",
        width="content",
        on_click="ignore",
    )
    with st.expander("충돌 상세 미리보기"):
        st.dataframe(report, hide_index=True, width="stretch")


def _optional_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("원천 DB 등록시점은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다.") from exc
