import streamlit as st

st.title("기준정보 정합성 관리")
st.caption("확인할 기준정보 항목을 선택하세요.")

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
