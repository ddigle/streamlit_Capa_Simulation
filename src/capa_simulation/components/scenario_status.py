"""Read-only sidebar summary for the active persisted scenario revision."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
    has_unsaved_scenario_changes,
)
from capa_simulation.settings import DUCKDB_PATH


def render_scenario_status(database_path: Path = DUCKDB_PATH) -> None:
    """Show the active scenario without offering selection controls."""
    resolved_path = str(database_path.resolve())
    with st.sidebar.container(border=True):
        st.markdown("#### :material/database: 활성 시나리오")
        try:
            repository = get_scenario_repository(resolved_path)
            scenarios = repository.list_scenarios()
            official = repository.latest_official_release()
        except Exception as exc:
            st.error(f"시나리오 저장소를 읽지 못했습니다: {exc}")
            return

        active_scenario_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        if active_scenario_id is None or active_revision_id is None:
            st.warning("활성화된 시나리오·리비전이 없습니다.")
            st.caption("시나리오 관리 페이지에서 불러올 리비전을 선택하세요.")
            return

        scenario = next(
            (item for item in scenarios if item.scenario_id == active_scenario_id),
            None,
        )
        if scenario is None:
            st.warning("현재 활성 시나리오 정보를 조회하지 못했습니다.")
            return

        revisions = repository.list_revisions(active_scenario_id)
        revision = next(
            (item for item in revisions if item.revision_id == active_revision_id),
            None,
        )
        if revision is None:
            st.warning("현재 활성 리비전 정보를 조회하지 못했습니다.")
            return

        st.markdown(f"**{scenario.scenario_name}**")
        st.caption(f"{scenario.source_simulation_code} · {scenario.source_simulation_name}")
        st.write(f"리비전 · **r{revision.revision_no} {revision.revision_name}**")

        if official is not None and official.revision_id == active_revision_id:
            st.markdown(f":green-badge[공식 v{official.release_no}]")
        elif official is not None and official.scenario_id == active_scenario_id:
            st.markdown(":blue-badge[공식 이력 보유 · 현재 리비전은 비공식]")
        else:
            st.markdown(":gray-badge[비공식 시나리오]")

        if has_unsaved_scenario_changes():
            st.markdown(":orange-badge[저장하지 않은 변경 있음]")
        else:
            st.caption("저장된 리비전과 동일한 상태입니다.")
