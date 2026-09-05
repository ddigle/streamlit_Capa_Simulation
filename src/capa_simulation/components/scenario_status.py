# Purpose: Sidebar controls for loading and revising persisted scenarios.

"""Sidebar controls for loading and revising persisted scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import streamlit as st

from capa_simulation.components.scenario_management import revision_tables_for_save
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioSummary
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.settings import DUCKDB_PATH

SIDEBAR_SCENARIO_KEY = "sidebar_scenario_id"
SIDEBAR_REVISION_KEY = "sidebar_revision_id"
SIDEBAR_SYNC_TOKEN_KEY = "sidebar_scenario_sync_token"
SIDEBAR_FLASH_KEY = "sidebar_scenario_flash"


def render_scenario_controls(database_path: Path = DUCKDB_PATH) -> None:
    """Load a saved revision or persist the current edits from every page."""
    resolved_path = str(database_path.resolve())
    with st.sidebar.container(border=True):
        st.markdown("#### :material/database: 시나리오·리비전")
        flash = st.session_state.pop(SIDEBAR_FLASH_KEY, None)
        if isinstance(flash, str):
            st.success(flash)

        try:
            repository = get_scenario_repository(resolved_path)
            scenarios = repository.list_scenarios()
            official = repository.latest_official_release()
        except Exception as exc:
            st.error(f"시나리오 저장소를 읽지 못했습니다: {exc}")
            return

        if not scenarios:
            st.info("저장된 활성 시나리오가 없습니다.")
            st.caption("시나리오 관리 페이지에서 신규 시나리오를 등록하세요.")
            return

        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        active_scenario_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        _synchronize_active_selection(
            scenario_by_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
        )

        selected_scenario_id = st.selectbox(
            "시나리오",
            options=list(scenario_by_id),
            format_func=lambda value: _scenario_label(scenario_by_id[value]),
            key=SIDEBAR_SCENARIO_KEY,
            persist_state="session",
        )
        revisions = repository.list_revisions(selected_scenario_id)
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        if not revision_by_id:
            st.warning("선택한 시나리오에 저장된 리비전이 없습니다.")
            return

        _ensure_revision_selection(
            scenario_by_id[selected_scenario_id],
            revision_by_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
        )
        selected_revision_id = st.selectbox(
            "리비전",
            options=list(revision_by_id),
            format_func=lambda value: (
                f"r{revision_by_id[value].revision_no} · {revision_by_id[value].revision_name}"
            ),
            key=SIDEBAR_REVISION_KEY,
            persist_state="session",
        )

        selection_is_active = (
            selected_scenario_id == active_scenario_id
            and selected_revision_id == active_revision_id
        )
        if selection_is_active:
            # 선택과 활성이 같으면 위의 두 선택 상자가 이미 이름을 보여준다. 아래에서
            # 이름을 한 번 더 적을 이유가 없어 배지만 같은 줄에 붙인다.
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.caption("현재 불러온 시나리오·리비전입니다.", width="content")
                badge = _status_badge(
                    active_revision_id=active_revision_id,
                    official_revision_id=official.revision_id if official is not None else None,
                    official_release_no=official.release_no if official is not None else None,
                )
                if badge:
                    st.markdown(badge, width="content")
        else:
            st.caption("선택값은 아직 계산에 적용되지 않았습니다.")

        discard_changes = True
        if has_unsaved_scenario_changes():
            st.markdown(":orange-badge[저장하지 않은 변경 있음]")
            discard_changes = st.checkbox(
                "변경을 버리고 불러오기",
                key="sidebar_discard_unsaved_changes",
            )

        if st.button(
            "선택 리비전 불러오기",
            icon=":material/download:",
            type="primary",
            disabled=not discard_changes,
            width="stretch",
            key="sidebar_load_revision",
        ):
            try:
                snapshot = load_scenario_snapshot(resolved_path, selected_revision_id)
                activate_persisted_snapshot(snapshot)
            except (KeyError, RuntimeError, TypeError, ValueError) as exc:
                st.error(f"리비전을 불러오지 못했습니다: {exc}")
            else:
                st.session_state[SIDEBAR_FLASH_KEY] = (
                    f"{snapshot.scenario.scenario_name} "
                    f"r{snapshot.revision.revision_no}을 불러왔습니다."
                )
                st.rerun()

        _render_revision_save(
            repository,
            scenario_by_id,
            selected_scenario_id=selected_scenario_id,
            selected_revision_id=selected_revision_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
        )
        if not selection_is_active:
            # 고른 것과 올라와 있는 것이 다를 때만 "지금 무엇이 올라와 있는지" 를 적는다.
            _render_active_status(
                scenario_by_id,
                active_scenario_id=active_scenario_id,
                active_revision_id=active_revision_id,
                official_revision_id=official.revision_id if official is not None else None,
                official_release_no=official.release_no if official is not None else None,
            )


def _render_revision_save(
    repository: DuckDBScenarioRepository,
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    selected_scenario_id: str,
    selected_revision_id: str,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    with st.expander("신규 리비전 저장", icon=":material/save_as:"):
        if active_scenario_id is None or active_revision_id is None:
            st.info("먼저 저장된 리비전을 불러오세요.")
            return
        if selected_scenario_id != active_scenario_id or selected_revision_id != active_revision_id:
            st.info("위에서 선택한 리비전을 먼저 불러온 뒤 저장하세요.")
            return

        active_summary = scenario_by_id.get(active_scenario_id)
        if active_summary is None:
            st.warning("현재 활성 시나리오 정보를 찾지 못했습니다.")
            return
        st.caption(f"저장 대상 · {active_summary.scenario_name}")
        with st.form("sidebar_revision_save_form", clear_on_submit=True):
            revision_name = st.text_input(
                "새 리비전명",
                placeholder="예: 공정 조건 변경안",
                key="sidebar_revision_name",
            )
            note = st.text_area(
                "변경 메모",
                height=80,
                key="sidebar_revision_note",
            )
            submitted = st.form_submit_button(
                "신규 리비전 저장",
                icon=":material/save_as:",
                width="stretch",
            )
        if not submitted:
            return

        try:
            reference_version = get_effective_reference_version()
            reference_tables = get_effective_reference_tables()
            active_scenario = ensure_active_scenario(reference_tables, reference_version)
            revision_tables = revision_tables_for_save(active_scenario, reference_tables)
            snapshot = repository.save_revision(
                active_scenario_id,
                revision_tables,
                capture_scenario_preset(
                    {**reference_tables, "RQ_REQB": revision_tables["RQ_REQB"]}
                ),
                revision_name=revision_name,
                parent_revision_id=active_revision_id,
                note=note.strip() or None,
            )
            activate_persisted_snapshot(snapshot)
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"신규 리비전을 저장하지 못했습니다: {bootstrap_error_message(exc)}")
        else:
            st.session_state[SIDEBAR_FLASH_KEY] = (
                f"신규 리비전 r{snapshot.revision.revision_no}을 저장했습니다."
            )
            st.rerun()


def _status_badge(
    *,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> str:
    """활성 리비전의 상태 배지를 고른다.

    미저장 변경이 있으면 빈 문자열을 준다. 그 상태는 바로 아래 "변경을 버리고 불러오기"
    체크박스 위에서 이미 같은 배지로 알리고 있어서, 여기서 또 적으면 같은 문구가 한 상자
    안에 두 번 나온다.
    """
    if has_unsaved_scenario_changes():
        return ""
    if official_revision_id == active_revision_id and official_release_no is not None:
        return f":green-badge[공식 v{official_release_no}]"
    return ":gray-badge[저장된 리비전]"


def _render_active_status(
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> None:
    if active_scenario_id is None or active_revision_id is None:
        st.warning("활성화된 시나리오·리비전이 없습니다.")
        return
    scenario = scenario_by_id.get(active_scenario_id)
    if scenario is None:
        st.warning("현재 활성 시나리오 정보를 조회하지 못했습니다.")
        return
    st.divider()
    st.caption(f"활성 · {scenario.scenario_name} · {scenario.source_simulation_code}")
    badge = _status_badge(
        active_revision_id=active_revision_id,
        official_revision_id=official_revision_id,
        official_release_no=official_release_no,
    )
    if badge:
        st.markdown(badge)


def _synchronize_active_selection(
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    active_token = (active_scenario_id, active_revision_id)
    previous_token = st.session_state.get(SIDEBAR_SYNC_TOKEN_KEY)
    if previous_token != active_token and active_scenario_id in scenario_by_id:
        st.session_state[SIDEBAR_SCENARIO_KEY] = active_scenario_id
        st.session_state[SIDEBAR_REVISION_KEY] = active_revision_id
    st.session_state[SIDEBAR_SYNC_TOKEN_KEY] = active_token

    selected = st.session_state.get(SIDEBAR_SCENARIO_KEY)
    if selected not in scenario_by_id:
        st.session_state[SIDEBAR_SCENARIO_KEY] = next(iter(scenario_by_id))


def _ensure_revision_selection(
    scenario: ScenarioSummary,
    revision_by_id: Mapping[str, object],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    selected = st.session_state.get(SIDEBAR_REVISION_KEY)
    if selected in revision_by_id:
        return
    preferred = (
        active_revision_id
        if scenario.scenario_id == active_scenario_id
        else scenario.active_revision_id
    )
    st.session_state[SIDEBAR_REVISION_KEY] = (
        preferred if preferred in revision_by_id else next(iter(revision_by_id))
    )


def _scenario_label(summary: ScenarioSummary) -> str:
    return f"{summary.scenario_name} · {summary.source_simulation_code}"


# Backward-compatible alias for callers that still use the old read-only name.
