import streamlit as st

from capa_simulation.settings import (
    APP_NAME,
    MONTH_SELECTION_END,
    MONTH_SELECTION_OPTIONS,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    register_month_range_placeholder,
    show_applied_month_range,
)

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")

pages = [
    st.Page(
        "app_pages/home.py",
        title="Home",
        icon=":material/home:",
        default=True,
    ),
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

navigation = st.navigation(pages, position="hidden")

st.html(
    """
    <style>
    .st-key-home_navigation a,
    .st-key-home_navigation a p {
        font-size: 1.15rem;
        font-weight: 700;
    }
    </style>
    """
)
with st.sidebar.container(key="home_navigation"):
    st.page_link(pages[0], width="stretch")

with st.sidebar.container(border=True):
    for page in pages[1:]:
        st.page_link(page, width="stretch")

with st.sidebar.container(border=True):
    st.markdown("#### 📅 조회 기간")
    st.caption("월 단위로 분석할 생산계획 범위를 선택하세요.")
    selected_start_label, selected_end_label = st.select_slider(
        "분석 년월",
        options=MONTH_SELECTION_OPTIONS,
        value=(format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END)),
        key="production_month_range_v2",
    )
    register_month_range_placeholder(st.empty())
    show_applied_month_range(
        int(selected_start_label.replace("-", "")),
        int(selected_end_label.replace("-", "")),
    )

navigation.run()
