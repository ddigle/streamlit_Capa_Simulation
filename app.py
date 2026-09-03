import streamlit as st

from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import render_scenario_controls
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


home_page = st.Page(
    "app_pages/home.py",
    title="HOME",
    default=True,
)
capa_chatbot_page = st.Page(
    "app_pages/capa_chatbot.py",
    title="Capa Chatbot",
    icon=":material/chat:",
)
scenario_management_page = st.Page(
    "app_pages/scenario_management.py",
    title="시나리오 관리",
    icon=":material/database:",
)
static_capa_page = st.Page(
    "app_pages/static_capa.py",
    title="Static Capa",
    icon=":material/factory:",
)
static_capa_pages = [
    st.Page(
        "app_pages/load_conversion.py",
        title="부하량",
        icon=":material/scale:",
    ),
    st.Page(
        "app_pages/capacity_standards.py",
        title="공정별 Capa",
        icon=":material/settings:",
    ),
    st.Page(
        "app_pages/process_securement.py",
        title="공정별 확보율",
        icon=":material/monitoring:",
    ),
    st.Page(
        "app_pages/standard_target_capa.py",
        title="표준 목표 Capa",
        icon=":material/track_changes:",
    ),
]
dynamic_capa_page = st.Page(
    "app_pages/reference_integrity.py",
    title="Dynamic Capa (구현중)",
    icon=":material/sync_alt:",
)
dynamic_capa_pages = [
    st.Page(
        "app_pages/wip_status.py",
        title="표준 대비 재공 현황 (DB 셋팅중)",
        icon=":material/inventory_2:",
    ),
    st.Page(
        "app_pages/available_equipment_status.py",
        title="가용설비 현황 (구현 중)",
        icon=":material/precision_manufacturing:",
    ),
    st.Page(
        "app_pages/actual_efficiency.py",
        title="효율 실적 (DB 셋팅중)",
        icon=":material/speed:",
    ),
    st.Page(
        "app_pages/actual_upeh.py",
        title="UPEH 실적 (DB 셋팅중)",
        icon=":material/timer:",
    ),
    st.Page(
        "app_pages/space_status.py",
        title="Space 현황 (구현 중)",
        icon=":material/grid_view:",
    ),
]
pages = [
    home_page,
    capa_chatbot_page,
    scenario_management_page,
    static_capa_page,
    *static_capa_pages,
    dynamic_capa_page,
    *dynamic_capa_pages,
]

navigation = st.navigation(pages, position="hidden")

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
    st.page_link(home_page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="capa_chatbot_navigation"):
        st.page_link(capa_chatbot_page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="scenario_management_navigation"):
        st.page_link(scenario_management_page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="static_capa_navigation"):
        st.page_link(static_capa_page, width="stretch")
    with st.container(key="static_capa_subpages"):
        for page in static_capa_pages:
            st.page_link(page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="dynamic_capa_navigation"):
        st.page_link(dynamic_capa_page, width="stretch")
    with st.container(key="dynamic_capa_subpages"):
        for page in dynamic_capa_pages:
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
