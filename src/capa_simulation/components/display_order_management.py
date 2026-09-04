# Purpose: Web editor and Excel clipboard import for the global display-order profile.

"""Web editor and Excel clipboard import for the global display-order profile."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.io.reference_cache import apply_global_display_order
from capa_simulation.persistence.cache import (
    clear_global_display_order_cache,
    load_global_display_order,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.display_order_csv import (
    display_order_from_clipboard,
    display_order_to_csv,
)
from capa_simulation.services.display_order_editor import (
    DISPLAY_ORDER_RULE_COLUMNS,
    replace_display_order_scope,
    validate_display_order,
)


def render_display_order_management(repository: DuckDBScenarioRepository) -> None:
    st.subheader("표시순서 관리")
    st.caption(
        "표시순서는 시나리오와 분리된 공용 설정입니다. 여기서 저장한 규칙은 현재와 이후 "
        "불러오는 모든 시나리오에 동일하게 적용됩니다."
    )
    database_path = str(repository.database_path)
    try:
        profile = load_global_display_order(database_path)
        display_order = validate_display_order(profile.rules)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
        return

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(
            f"공용 버전 v{profile.version} · {profile.source} · {profile.updated_at:%Y-%m-%d %H:%M}"
        )
        render_csv_download(
            data=display_order_to_csv(display_order),
            file_name=f"RQ_DISPLAY_ORDER_v{profile.version}.csv",
            key="display_order_download",
        )

    _render_clipboard_import(repository, display_order)
    _render_direct_editor(repository, display_order)


def _render_clipboard_import(
    repository: DuckDBScenarioRepository,
    current: pd.DataFrame,
) -> None:
    with st.expander("Excel 붙여넣기 일괄 적용", icon=":material/content_paste:"):
        st.caption(
            "다운로드한 양식을 Excel에서 수정한 뒤 헤더를 포함한 전체 표를 복사해 "
            "붙여넣으세요. 적용하면 현재 공용 표시순서 전체가 교체되며 시나리오 "
            "리비전은 생성하지 않습니다."
        )
        with st.form("global_display_order_clipboard_form", border=False):
            clipboard_text = st.text_area(
                "표시순서 표 붙여넣기",
                key="global_display_order_clipboard",
                height=220,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            confirmed = st.checkbox("현재 공용 표시순서 전체 교체를 확인했습니다.")
            submitted = st.form_submit_button(
                "붙여넣기 표시순서 적용",
                icon=":material/content_paste:",
                type="primary",
                width="stretch",
            )
        if not submitted:
            return
        if not clipboard_text.strip():
            st.error("적용할 표시순서 표를 Excel에서 복사해 붙여넣으세요.")
            return
        if not confirmed:
            st.error("전체 교체 확인을 선택하세요.")
            return
        try:
            imported = display_order_from_clipboard(clipboard_text)
            if imported.equals(current):
                st.info("붙여넣은 표시순서가 현재 공용 설정과 동일합니다.")
                return
            _save_global_display_order(repository, imported, source="Excel 붙여넣기")
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.success("붙여넣은 표시순서를 모든 시나리오의 공용 설정으로 적용했습니다.")
            st.rerun()


def _render_direct_editor(
    repository: DuckDBScenarioRepository,
    display_order: pd.DataFrame,
) -> None:
    st.markdown("#### 직접 편집")
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
        "정렬우선순위는 행 그룹 정렬과 왼쪽 분류컬럼 배치 순서에 함께 적용됩니다. "
        "사용자지정은 분류값마다 값표시순서를 입력하고, 오름차순·내림차순은 한 행만 "
        "유지하세요. 경로 상세가 있는 탭의 STEP_SEQ·MCP_SEQ는 항상 마지막 계층으로 "
        "유지됩니다."
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
        note = st.text_input("변경 메모", placeholder="예: 환산 탭 제품 표시순서 변경")
        submitted = st.form_submit_button(
            "공용 표시순서 저장",
            icon=":material/save:",
            type="primary",
            width="stretch",
        )
    if not submitted:
        return
    try:
        revised = replace_display_order_scope(
            display_order,
            str(selected_page),
            str(selected_tab),
            pd.DataFrame(edited),
        )
        source = note.strip() or f"웹 직접 편집 · {selected_page}/{selected_tab}"
        _save_global_display_order(repository, revised, source=source)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        st.success("표시순서를 모든 시나리오의 공용 설정으로 저장했습니다.")
        st.rerun()


def _save_global_display_order(
    repository: DuckDBScenarioRepository,
    display_order: pd.DataFrame,
    *,
    source: str,
) -> None:
    validated = validate_display_order(display_order)
    profile = repository.replace_global_display_order(validated, source=source)
    clear_global_display_order_cache()
    try:
        apply_global_display_order(profile.rules, profile.version)
    except RuntimeError:
        pass
