from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.io.core_data_source import CsvCoreDataProvider
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSummary
from capa_simulation.persistence.repository import REVISION_TABLES
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    clear_persisted_scenario_activation,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ActiveScenario, ensure_active_scenario
from capa_simulation.services.core_data_pipeline import fetch_core_data_dataset
from capa_simulation.settings import CORE_DATA_CSV_PATH, DUCKDB_PATH, PROJECT_ROOT

CLONE_PIPELINE_VERSION = "duckdb-rq-snapshot-v1"
CORE_DATA_PIPELINE_VERSION = "core-data-pandas-v1"
FLASH_KEY = "scenario_page_flash"
WORKBOOK_PATH = PROJECT_ROOT / "templates" / "structure_template.xlsb"


def _revision_tables(
    active_tables: dict[str, pd.DataFrame],
    reference_tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    result = {
        name: active_tables[name].copy(deep=True)
        for name in REVISION_TABLES
        if name in active_tables
    }
    result["RQ_DISPLAY_ORDER"] = reference_tables["RQ_DISPLAY_ORDER"].copy(deep=True)
    return result


def _scenario_label(summary: ScenarioSummary) -> str:
    return (
        f"{summary.scenario_name} · {summary.source_simulation_code} "
        f"· r{summary.active_revision_no}"
    )


def _current_reference_context() -> tuple[dict[str, pd.DataFrame], ActiveScenario]:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables(str(WORKBOOK_PATH.resolve()))
    return reference_tables, ensure_active_scenario(reference_tables, reference_version)


st.title("시나리오 및 결과")
st.caption("현재 기준정보와 화면 프리셋을 DuckDB의 불변 리비전으로 저장하고 복원합니다.")

flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

try:
    repository = get_scenario_repository(str(DUCKDB_PATH.resolve()))
    scenarios = repository.list_scenarios()
except Exception as exc:
    st.error(f"시나리오 저장소를 준비하지 못했습니다: {exc}")
    st.stop()

with st.container(border=True):
    st.markdown("#### :material/database: 저장소 상태")
    st.caption(f"DuckDB: {repository.database_path}")
    active_id = active_persisted_scenario_id()
    active_revision_id = active_persisted_revision_id()
    if active_id and active_revision_id:
        dirty_label = " · 저장하지 않은 변경 있음" if has_unsaved_scenario_changes() else ""
        st.write(f"활성 시나리오 `{active_id}` · 리비전 `{active_revision_id}`{dirty_label}")
    else:
        st.write("현재 XLSB 기준정보를 사용 중이며 아직 영구 시나리오를 불러오지 않았습니다.")

mode = st.segmented_control(
    "시나리오 작업",
    ["불러오기", "신규 저장", "리비전 저장"],
    default="불러오기",
    key="scenario_page_mode",
    persist_state="session",
)

if mode == "불러오기":
    if not scenarios:
        st.info("저장된 활성 시나리오가 없습니다. 먼저 신규 시나리오를 저장하세요.")
    else:
        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        selected_scenario_id = st.selectbox(
            "시나리오",
            options=list(scenario_by_id),
            format_func=lambda value: _scenario_label(scenario_by_id[value]),
            key="scenario_load_scenario_id",
            persist_state="session",
        )
        revisions = repository.list_revisions(selected_scenario_id)
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        selected_revision_id = st.selectbox(
            "리비전",
            options=list(revision_by_id),
            format_func=lambda value: (
                f"r{revision_by_id[value].revision_no} · {revision_by_id[value].revision_name}"
            ),
            key="scenario_load_revision_id",
            persist_state="session",
        )
        discard_changes = True
        if has_unsaved_scenario_changes():
            st.warning("현재 활성 시나리오에 저장하지 않은 편집값이 있습니다.")
            discard_changes = st.checkbox(
                "저장하지 않은 변경을 버리고 불러오기",
                key="scenario_discard_unsaved_changes",
            )
        with st.container(horizontal=True):
            if st.button(
                "선택 리비전 불러오기",
                icon=":material/download:",
                type="primary",
                disabled=not discard_changes,
            ):
                snapshot = load_scenario_snapshot(
                    str(DUCKDB_PATH.resolve()),
                    selected_revision_id,
                )
                activate_persisted_snapshot(snapshot)
                st.session_state[FLASH_KEY] = (
                    f"{snapshot.scenario.scenario_name} r{snapshot.revision.revision_no}을 "
                    "불러왔습니다."
                )
                st.rerun()
            archive_confirmed = st.checkbox(
                "선택 시나리오 보관 확인",
                key="scenario_archive_confirmed",
            )
            if st.button(
                "시나리오 보관",
                icon=":material/archive:",
                disabled=not archive_confirmed,
            ):
                repository.archive_scenario(selected_scenario_id)
                if selected_scenario_id == active_persisted_scenario_id():
                    clear_persisted_scenario_activation()
                st.session_state[FLASH_KEY] = "시나리오를 보관 상태로 변경했습니다."
                st.rerun()

elif mode == "신규 저장":
    try:
        reference_tables, active_scenario = _current_reference_context()
    except Exception as exc:
        st.error(f"저장할 기준정보를 불러오지 못했습니다: {exc}")
        st.stop()
    source_mode = st.segmented_control(
        "원천 데이터",
        ["Core Data CSV", "현재 활성 RQ 복제"],
        default="Core Data CSV",
        required=True,
        key="scenario_create_source_mode",
        persist_state="session",
    )
    if source_mode == "Core Data CSV":
        st.info(
            "개발용 Core_Data.csv를 pandas DataFrame으로 읽고, Python에서 RQ 16개를 "
            "생성한 뒤 원천 78개 컬럼과 함께 독립 데이터셋으로 저장합니다."
        )
        st.caption(f"개발 원천: {CORE_DATA_CSV_PATH}")
    else:
        st.info(
            "현재 활성 RQ 16개를 독립 데이터셋으로 복제하고, 편집 가능한 8개 테이블과 "
            "표시순서·사이드바 프리셋을 초기 리비전으로 저장합니다."
        )
    with st.form("scenario_create_form"):
        scenario_name = st.text_input("시나리오명")
        source_code = st.text_input("원천 시뮬레이션 코드")
        source_name = st.text_input("원천 시뮬레이션명")
        revision_name = st.text_input("초기 리비전명", value="초기 리비전")
        note = st.text_area("메모", height=100)
        create_submitted = st.form_submit_button(
            "신규 시나리오 저장",
            icon=":material/save:",
            type="primary",
            width="stretch",
        )
    if create_submitted:
        try:
            source_data: pd.DataFrame | None = None
            revision_source: dict[str, pd.DataFrame] | None = None
            if source_mode == "Core Data CSV":
                provider = CsvCoreDataProvider(CORE_DATA_CSV_PATH, source_name)
                prepared = fetch_core_data_dataset(
                    provider,
                    source_code,
                    reference_tables["RQ_DISPLAY_ORDER"],
                )
                scenario_tables = prepared.reference_tables
                source_data = prepared.source_data
                source_type = prepared.batch.source_type
                pipeline_version = CORE_DATA_PIPELINE_VERSION
                source_registered_at = prepared.batch.source_registered_at
                source_name = prepared.batch.simulation_name
            else:
                scenario_tables = reference_tables
                revision_source = _revision_tables(active_scenario["tables"], reference_tables)
                source_type = (
                    "DUCKDB_SCENARIO_CLONE"
                    if active_persisted_scenario_id() is not None
                    else "XLSB_RQ_SNAPSHOT"
                )
                pipeline_version = CLONE_PIPELINE_VERSION
                source_registered_at = None
            preset = capture_scenario_preset(scenario_tables)
            snapshot = repository.create_scenario(
                ScenarioCreate(
                    scenario_name=scenario_name,
                    source_simulation_code=source_code,
                    source_simulation_name=source_name,
                    source_type=source_type,
                    pipeline_version=pipeline_version,
                    source_registered_at=source_registered_at,
                ),
                scenario_tables,
                preset,
                source_data=source_data,
                revision_tables=revision_source,
                revision_name=revision_name,
                note=note.strip() or None,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            activate_persisted_snapshot(snapshot)
            st.session_state[FLASH_KEY] = f"{snapshot.scenario.scenario_name}을 저장했습니다."
            st.rerun()

elif mode == "리비전 저장":
    scenario_id = active_persisted_scenario_id()
    if scenario_id is None:
        st.info("먼저 저장된 시나리오를 불러오거나 신규 시나리오를 저장하세요.")
    else:
        try:
            reference_tables, active_scenario = _current_reference_context()
        except Exception as exc:
            st.error(f"리비전 기준정보를 불러오지 못했습니다: {exc}")
            st.stop()
        with st.form("scenario_revision_form"):
            revision_name = st.text_input("새 리비전명")
            note = st.text_area("변경 메모", height=100)
            revision_submitted = st.form_submit_button(
                "새 리비전 저장",
                icon=":material/save_as:",
                type="primary",
                width="stretch",
            )
        if revision_submitted:
            try:
                preset = capture_scenario_preset(reference_tables)
                snapshot = repository.save_revision(
                    scenario_id,
                    _revision_tables(active_scenario["tables"], reference_tables),
                    preset,
                    revision_name=revision_name,
                    parent_revision_id=active_persisted_revision_id(),
                    note=note.strip() or None,
                )
            except (KeyError, TypeError, ValueError) as exc:
                st.error(str(exc))
            else:
                activate_persisted_snapshot(snapshot)
                st.session_state[FLASH_KEY] = (
                    f"새 리비전 r{snapshot.revision.revision_no}을 저장했습니다."
                )
                st.rerun()
