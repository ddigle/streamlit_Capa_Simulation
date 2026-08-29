"""Web editor for revision-owned RQ_DISPLAY_ORDER rules."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.scenario_management import revision_tables_for_save
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.services.display_order_editor import (
    DISPLAY_ORDER_RULE_COLUMNS,
    replace_display_order_scope,
    validate_display_order,
)


def render_display_order_management(repository: DuckDBScenarioRepository) -> None:
    st.subheader("표시순서 관리")
    st.caption(
        "페이지와 탭 범위를 선택해 정렬 규칙을 수정합니다. 저장할 때 현재 편집값과 "
        "프리셋을 포함한 새 불변 리비전이 생성됩니다."
    )
    scenario_id = active_persisted_scenario_id()
    if scenario_id is None:
        st.info("먼저 저장된 시나리오 리비전을 불러오세요.")
        return
    try:
        reference_tables = get_effective_reference_tables()
        reference_version = get_effective_reference_version()
        active_scenario = ensure_active_scenario(reference_tables, reference_version)
        display_order = validate_display_order(reference_tables["RQ_DISPLAY_ORDER"])
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
        return
    if display_order.empty:
        st.warning("현재 리비전에 표시순서 규칙이 없습니다.")
        return
    pages = display_order["페이지 구분"].drop_duplicates().tolist()
    selected_page = st.selectbox(
        "페이지 구분",
        options=pages,
        key="display_order_page",
        persist_state="session",
    )
    tabs = (
        display_order.loc[display_order["페이지 구분"].eq(selected_page), "탭 구분"]
        .drop_duplicates()
        .tolist()
    )
    selected_tab = st.selectbox(
        "탭 구분",
        options=tabs,
        key="display_order_tab",
        persist_state="session",
    )
    scope_mask = display_order["페이지 구분"].eq(selected_page) & display_order["탭 구분"].eq(
        selected_tab
    )
    scope_rules = display_order.loc[scope_mask, list(DISPLAY_ORDER_RULE_COLUMNS)].reset_index(
        drop=True
    )
    st.caption(
        "사용자지정은 분류값마다 값표시순서를 입력하고, 오름차순·내림차순은 한 행만 "
        "유지하세요. 행 추가·삭제가 가능합니다."
    )
    with st.form("display_order_edit_form"):
        edited = st.data_editor(
            scope_rules,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            height=460,
            column_config={
                "정렬우선순위": st.column_config.NumberColumn(min_value=1, step=1),
                "정렬방식": st.column_config.SelectboxColumn(
                    options=["사용자지정", "오름차순", "내림차순"],
                    required=True,
                ),
                "값표시순서": st.column_config.NumberColumn(min_value=1, step=1),
                "활성여부": st.column_config.SelectboxColumn(
                    options=["Y", "N"],
                    required=True,
                ),
            },
            key=f"display_order_editor::{selected_page}::{selected_tab}",
        )
        revision_name = st.text_input("새 리비전명", value="표시순서 변경")
        note = st.text_area("변경 메모", height=80)
        submitted = st.form_submit_button(
            "표시순서 새 리비전 저장",
            icon=":material/save_as:",
            type="primary",
            width="stretch",
        )
    if not submitted:
        return
    try:
        revised_display_order = replace_display_order_scope(
            display_order,
            str(selected_page),
            str(selected_tab),
            pd.DataFrame(edited),
        )
        snapshot = repository.save_revision(
            scenario_id,
            revision_tables_for_save(
                active_scenario,
                reference_tables,
                display_order=revised_display_order,
            ),
            capture_scenario_preset(reference_tables),
            revision_name=revision_name,
            parent_revision_id=active_persisted_revision_id(),
            note=note.strip() or None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        activate_persisted_snapshot(snapshot)
        st.success(f"표시순서를 새 리비전 r{snapshot.revision.revision_no}에 저장했습니다.")
        st.rerun()
