import streamlit as st

st.title("Dynamic Capa")
st.caption("실적과 운영 현황을 기반으로 Dynamic Capa 관리 항목을 확인합니다.")

with st.container(border=True):
    st.page_link(
        "app_pages/available_equipment_status.py",
        label="가용설비 현황",
        icon=":material/precision_manufacturing:",
        width="stretch",
    )
    st.page_link(
        "app_pages/actual_efficiency.py",
        label="실적 효율",
        icon=":material/speed:",
        width="stretch",
    )
    st.page_link(
        "app_pages/actual_upeh.py",
        label="UPEH 실적",
        icon=":material/timer:",
        width="stretch",
    )
    st.page_link(
        "app_pages/space_status.py",
        label="Space 현황",
        icon=":material/grid_view:",
        width="stretch",
    )
