"""Scenario load, create, revise, rename, archive, and official-release UI."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from capa_simulation.io.core_data_source import CsvCoreDataProvider
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSummary
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
)
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    clear_persisted_scenario_activation,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ActiveScenario, ensure_active_scenario
from capa_simulation.services.builtin_seed import BUILTIN_SEED_SOURCE_CODE
from capa_simulation.services.core_data_pipeline import fetch_core_data_dataset
from capa_simulation.settings import CORE_DATA_CSV_PATH

CLONE_PIPELINE_VERSION = "duckdb-rq-snapshot-v3"
CORE_DATA_PIPELINE_VERSION = "core-data-pandas-v3"
FLASH_KEY = "scenario_management_flash"


def render_scenario_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    scenarios = repository.list_scenarios()
    _render_store_status(repository)
    mode = st.segmented_control(
        "시나리오 작업",
        ["불러오기", "신규 저장", "리비전 저장"],
        default="불러오기",
        key="scenario_page_mode",
        persist_state="session",
    )
    if mode == "불러오기":
        _render_load(repository, database_path, scenarios)
    elif mode == "신규 저장":
        _render_create(repository, database_path)
    else:
        _render_revision_save(repository)


def _render_store_status(repository: DuckDBScenarioRepository) -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if isinstance(flash, str):
        st.success(flash)
    official = repository.latest_official_release()
    with st.container(border=True):
        st.markdown("#### :material/database: 저장소 상태")
        active_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        if active_id and active_revision_id:
            dirty = " · 저장하지 않은 변경 있음" if has_unsaved_scenario_changes() else ""
            st.write(f"활성 시나리오 `{active_id}` · 리비전 `{active_revision_id}`{dirty}")
        else:
            st.write("현재 활성화된 DuckDB 리비전이 없습니다.")
        if official is None:
            st.warning("공식버전이 없습니다. 새 웹 세션에서 자동으로 불러올 기준이 없습니다.")
        else:
            st.success(
                f"최신 공식 v{official.release_no} · {official.scenario_name} "
                f"r{official.revision_no} · {official.release_name}"
            )
            if official.source_simulation_code == BUILTIN_SEED_SOURCE_CODE:
                st.info(
                    "현재 공식버전은 GitHub 독립 실행용 합성 DEMO 데이터입니다. "
                    "운영 전 Core Data CSV 또는 BigDataQuery 시나리오를 등록해 새 공식버전으로 "
                    "지정하세요."
                )


def _render_load(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: list[ScenarioSummary],
) -> None:
    if not scenarios:
        st.info("저장된 활성 시나리오가 없습니다. 초기 이관 또는 신규 등록이 필요합니다.")
        return
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
    if st.button(
        "선택 리비전 불러오기",
        icon=":material/download:",
        type="primary",
        disabled=not discard_changes,
        width="stretch",
    ):
        snapshot = load_scenario_snapshot(database_path, selected_revision_id)
        activate_persisted_snapshot(snapshot)
        st.session_state[FLASH_KEY] = (
            f"{snapshot.scenario.scenario_name} r{snapshot.revision.revision_no}을 불러왔습니다."
        )
        st.rerun()

    with st.expander("시나리오명 수정", icon=":material/edit:"):
        with st.form("scenario_rename_form"):
            renamed = st.text_input(
                "새 시나리오명",
                value=scenario_by_id[selected_scenario_id].scenario_name,
            )
            rename_submitted = st.form_submit_button("이름 저장", width="stretch")
        if rename_submitted:
            try:
                summary = repository.rename_scenario(selected_scenario_id, renamed)
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                st.session_state[FLASH_KEY] = (
                    f"시나리오명을 '{summary.scenario_name}'으로 변경했습니다."
                )
                st.rerun()

    with st.expander("공식버전 지정", icon=":material/verified:"):
        st.caption("공식 지정은 기존 리비전을 변경하지 않고 발행 이력을 새로 추가합니다.")
        with st.form("scenario_official_form"):
            release_name = st.text_input(
                "공식버전명",
                value=f"{scenario_by_id[selected_scenario_id].scenario_name} 공식안",
            )
            release_note = st.text_area("공식 지정 메모", height=80)
            official_submitted = st.form_submit_button(
                "선택 리비전을 공식버전으로 지정",
                icon=":material/publish:",
                type="primary",
                width="stretch",
            )
        if official_submitted:
            try:
                release = repository.publish_official_revision(
                    selected_scenario_id,
                    selected_revision_id,
                    release_name=release_name,
                    note=release_note,
                )
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                st.session_state[FLASH_KEY] = (
                    f"공식 v{release.release_no} · {release.release_name}을 지정했습니다."
                )
                st.rerun()
        releases = repository.list_official_releases(limit=10)
        if releases:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "공식버전": f"v{release.release_no}",
                            "시나리오": release.scenario_name,
                            "리비전": f"r{release.revision_no}",
                            "공식버전명": release.release_name,
                            "지정시각": release.published_at,
                        }
                        for release in releases
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

    with st.expander("시나리오 보관", icon=":material/archive:"):
        archive_confirmed = st.checkbox(
            "선택 시나리오를 목록에서 보관 처리합니다.",
            key="scenario_archive_confirmed",
        )
        if st.button(
            "시나리오 보관",
            icon=":material/archive:",
            disabled=not archive_confirmed,
            width="stretch",
        ):
            try:
                repository.archive_scenario(selected_scenario_id)
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                if selected_scenario_id == active_persisted_scenario_id():
                    clear_persisted_scenario_activation()
                st.session_state[FLASH_KEY] = "시나리오를 보관 상태로 변경했습니다."
                st.rerun()


def _render_create(repository: DuckDBScenarioRepository, database_path: str) -> None:
    try:
        reference_tables, active_scenario = _current_reference_context()
    except Exception as exc:
        st.error(f"신규 시나리오의 기준 표시순서를 준비하지 못했습니다: {exc}")
        return
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
            "개발용 Core_Data.csv를 pandas로 읽어 typed raw와 RQ 16개를 같은 독립 "
            "데이터셋에 저장합니다. 표시순서는 현재 활성 공식 구조를 사용합니다."
        )
        st.caption(f"개발 원천: {CORE_DATA_CSV_PATH}")
    else:
        st.info("현재 활성 RQ 16개와 프리셋을 독립 데이터셋으로 물리 복제합니다.")
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
    if not create_submitted:
        return
    try:
        source_data: pd.DataFrame | None = None
        revision_source: dict[str, pd.DataFrame] | None = None
        if source_mode == "Core Data CSV":
            official = repository.latest_official_release()
            if official is None:
                raise ValueError("표시순서 기준으로 사용할 공식버전이 없습니다.")
            official_display_order = load_scenario_snapshot(
                database_path,
                official.revision_id,
            ).tables["RQ_DISPLAY_ORDER"]
            provider = CsvCoreDataProvider(CORE_DATA_CSV_PATH, source_name)
            prepared = fetch_core_data_dataset(
                provider,
                source_code,
                official_display_order,
            )
            scenario_tables = prepared.reference_tables
            source_data = prepared.source_data
            source_type = prepared.batch.source_type
            pipeline_version = CORE_DATA_PIPELINE_VERSION
            source_registered_at = prepared.batch.source_registered_at
            source_name = prepared.batch.simulation_name
        else:
            scenario_tables = reference_tables
            revision_source = revision_tables_for_save(active_scenario, reference_tables)
            source_type = "DUCKDB_SCENARIO_CLONE"
            pipeline_version = CLONE_PIPELINE_VERSION
            source_registered_at = None
        preset_tables = revision_source if revision_source is not None else scenario_tables
        preset = _compatible_preset(capture_scenario_preset(preset_tables), preset_tables)
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
    except (FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        activate_persisted_snapshot(snapshot)
        st.session_state[FLASH_KEY] = f"{snapshot.scenario.scenario_name}을 저장했습니다."
        st.rerun()


def _render_revision_save(repository: DuckDBScenarioRepository) -> None:
    scenario_id = active_persisted_scenario_id()
    if scenario_id is None:
        st.info("먼저 저장된 시나리오를 불러오거나 신규 시나리오를 저장하세요.")
        return
    try:
        reference_tables, active_scenario = _current_reference_context()
    except Exception as exc:
        st.error(f"리비전 기준정보를 불러오지 못했습니다: {exc}")
        return
    with st.form("scenario_revision_form"):
        revision_name = st.text_input("새 리비전명")
        note = st.text_area("변경 메모", height=100)
        revision_submitted = st.form_submit_button(
            "새 리비전 저장",
            icon=":material/save_as:",
            type="primary",
            width="stretch",
        )
    if not revision_submitted:
        return
    try:
        revision_tables = revision_tables_for_save(active_scenario, reference_tables)
        preset = capture_scenario_preset(
            {**reference_tables, "RQ_REQB": revision_tables["RQ_REQB"]}
        )
        snapshot = repository.save_revision(
            scenario_id,
            revision_tables,
            preset,
            revision_name=revision_name,
            parent_revision_id=active_persisted_revision_id(),
            note=note.strip() or None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        activate_persisted_snapshot(snapshot)
        st.session_state[FLASH_KEY] = f"새 리비전 r{snapshot.revision.revision_no}을 저장했습니다."
        st.rerun()


def revision_tables_for_save(
    active_scenario: ActiveScenario,
    reference_tables: dict[str, pd.DataFrame],
    *,
    display_order: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    result = {
        name: active_scenario["tables"][name].copy(deep=True)
        for name in REVISION_TABLES
        if name in active_scenario["tables"]
    }
    selected_display_order = (
        display_order if display_order is not None else reference_tables["RQ_DISPLAY_ORDER"]
    )
    result["RQ_DISPLAY_ORDER"] = selected_display_order.copy(deep=True)
    return result


def _current_reference_context() -> tuple[dict[str, pd.DataFrame], ActiveScenario]:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    return reference_tables, ensure_active_scenario(reference_tables, reference_version)


def _compatible_preset(
    preset: ScenarioPreset,
    reference_tables: dict[str, pd.DataFrame],
) -> ScenarioPreset:
    available = set(
        reference_tables["RQ_REQB"]["공정"].astype("string").str.strip().dropna().tolist()
    )
    return replace(
        preset,
        included_processes=tuple(
            process for process in preset.included_processes if process in available
        ),
    )


def _scenario_label(summary: ScenarioSummary) -> str:
    return (
        f"{summary.scenario_name} · {summary.source_simulation_code} "
        f"· r{summary.active_revision_no}"
    )
