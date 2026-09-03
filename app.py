# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import render_scenario_controls
from capa_simulation.navigation import build_navigation_pages
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset
from capa_simulation.settings import (
    APP_NAME,
    DUCKDB_PATH,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    register_month_range_placeholder,
    show_applied_month_range,
)

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")
bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
apply_pending_scenario_preset()


pages = build_navigation_pages()
navigation = st.navigation(pages.ordered, position="hidden")

st.html(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-top: 3rem !important;
    }

    .st-key-home_navigation a,
    .st-key-home_navigation a p {
        font-size: 1.5rem;
        font-weight: 700;
    }
    .st-key-home_navigation a {
        justify-content: center;
    }
    .st-key-home_navigation a p {
        text-align: center;
    }

    .st-key-capa_chatbot_navigation a p,
    .st-key-scenario_management_navigation a p,
    .st-key-static_capa_navigation a p,
    .st-key-dynamic_capa_navigation a p {
        font-size: 1.15rem;
        font-weight: 700;
    }

    .st-key-static_capa_subpages [data-testid="stPageLink-NavLink"],
    .st-key-dynamic_capa_subpages [data-testid="stPageLink-NavLink"] {
        margin-left: 1rem;
        width: calc(100% - 1rem);
    }
    </style>
    """
)
with st.sidebar.container(key="home_navigation"):
    st.page_link(pages.home, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="capa_chatbot_navigation"):
        st.page_link(pages.capa_chatbot, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="scenario_management_navigation"):
        st.page_link(pages.scenario_management, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="static_capa_navigation"):
        st.page_link(pages.static_capa, width="stretch")
    with st.container(key="static_capa_subpages"):
        for page in pages.static_capa_subpages:
            st.page_link(page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="dynamic_capa_navigation"):
        st.page_link(pages.dynamic_capa, width="stretch")
    with st.container(key="dynamic_capa_subpages"):
        for page in pages.dynamic_capa_subpages:
            st.page_link(page, width="stretch")

render_scenario_controls()

with st.sidebar.container(border=True):
    st.markdown("#### 📅 조회 기간")
    st.caption("시작 월과 종료 월을 각각 선택하세요.")
    default_month_range = (
        format_month(MONTH_SELECTION_START),
        format_month(MONTH_SELECTION_END),
    )
    current_month_range = st.session_state.get("production_month_range_v2", default_month_range)
    if not isinstance(current_month_range, (list, tuple)) or len(current_month_range) != 2:
        current_month_range = default_month_range
    selected_start_label, selected_end_label = render_month_range_picker(
        start=str(current_month_range[0]),
        end=str(current_month_range[1]),
        min_month=default_month_range[0],
        max_month=default_month_range[1],
        key="production_month_picker",
    )
    st.session_state["production_month_range_v2"] = (
        selected_start_label,
        selected_end_label,
    )
    register_month_range_placeholder(st.empty())
    show_applied_month_range(
        int(selected_start_label.replace("-", "")),
        int(selected_end_label.replace("-", "")),
    )

navigation.run()
