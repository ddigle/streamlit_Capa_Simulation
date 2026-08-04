import streamlit as st

from capa_simulation.settings import APP_NAME

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")

pages = [
    st.Page(
        "app_pages/home.py",
        title="홈",
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
        title="Capa 기준정보",
        icon=":material/settings:",
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

navigation = st.navigation(pages, position="sidebar")
navigation.run()
