import streamlit as st

st.title("Static Capa")
st.caption("생산계획과 기준정보를 기반으로 Static Capa 산출·검토 항목을 확인합니다.")

with st.container(border=True):
    st.page_link(
        "app_pages/load_conversion.py",
        label="부하량",
        icon=":material/scale:",
        width="stretch",
    )
    st.page_link(
        "app_pages/capacity_standards.py",
        label="공정별 Capa",
        icon=":material/settings:",
        width="stretch",
    )
    st.page_link(
        "app_pages/process_securement.py",
        label="공정별 확보율",
        icon=":material/monitoring:",
        width="stretch",
    )
    st.page_link(
        "app_pages/bottleneck_analysis.py",
        label="B/N 분석",
        icon=":material/analytics:",
        width="stretch",
    )
    st.page_link(
        "app_pages/scenarios.py",
        label="시나리오 및 결과",
        icon=":material/science:",
        width="stretch",
    )
