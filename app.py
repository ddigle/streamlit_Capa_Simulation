import streamlit as st

from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_selector_demo import render_scenario_selector_demo
from capa_simulation.io.reference_cache import (
    clear_reference_tables,
    get_reference_cache_version,
)
from capa_simulation.scenario_activation import clear_persisted_scenario_activation
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset
from capa_simulation.services.simulation_cache import clear_simulation_caches
from capa_simulation.settings import (
    APP_NAME,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    register_month_range_placeholder,
    show_applied_month_range,
)

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")
apply_pending_scenario_preset()


def refresh_reference_data() -> None:
    clear_reference_tables()
    clear_simulation_caches()
    clear_persisted_scenario_activation()
    for key in (
        "load_conversion_inputs",
        "unit_capacity_result",
        "capacity_standards_inputs",
        "load_conversion_source_token",
        "capacity_standards_source_token",
        "home_dashboard_figure_cache",
    ):
        st.session_state.pop(key, None)


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
        "app_pages/bottleneck_analysis.py",
        title="B/N 분석",
        icon=":material/analytics:",
    ),
    st.Page(
        "app_pages/scenarios.py",
        title="시나리오 및 결과",
        icon=":material/science:",
    ),
]
dynamic_capa_page = st.Page(
    "app_pages/reference_integrity.py",
    title="Dynamic Capa",
    icon=":material/sync_alt:",
)
dynamic_capa_pages = [
    st.Page(
        "app_pages/available_equipment_status.py",
        title="가용설비 현황",
        icon=":material/precision_manufacturing:",
    ),
    st.Page(
        "app_pages/actual_efficiency.py",
        title="실적 효율",
        icon=":material/speed:",
    ),
    st.Page(
        "app_pages/actual_upeh.py",
        title="UPEH 실적",
        icon=":material/timer:",
    ),
    st.Page(
        "app_pages/space_status.py",
        title="Space 현황",
        icon=":material/grid_view:",
    ),
]
pages = [
    home_page,
    capa_chatbot_page,
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
    st.page_link(capa_chatbot_page, width="stretch")

with st.sidebar.container(border=True):
    st.page_link(static_capa_page, width="stretch")
    with st.container(key="static_capa_subpages"):
        for page in static_capa_pages:
            st.page_link(page, width="stretch")

with st.sidebar.container(border=True):
    st.page_link(dynamic_capa_page, width="stretch")
    with st.container(key="dynamic_capa_subpages"):
        for page in dynamic_capa_pages:
            st.page_link(page, width="stretch")

render_scenario_selector_demo()

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

with st.sidebar.container(border=True):
    st.markdown("#### :material/database: 기준정보 캐시")
    st.caption("XLSB는 서버 공통 캐시, 저장 시나리오는 DuckDB 스냅샷을 사용합니다.")
    st.button(
        ":material/refresh: 기준정보 새로고침",
        key="refresh_reference_data",
        on_click=refresh_reference_data,
        width="stretch",
    )
    st.caption(f"캐시 버전 {get_reference_cache_version()}")

navigation.run()
