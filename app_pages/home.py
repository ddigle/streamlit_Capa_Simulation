import streamlit as st

from capa_simulation.settings import APP_NAME

st.title(APP_NAME)

with st.container(border=True):
    st.subheader("생산계획 현황")
    production_chart_column, production_detail_column = st.columns([2, 1], gap="medium")
    with production_chart_column.container(
        border=True,
        height=280,
        vertical_alignment="center",
    ):
        st.markdown("#### 차트 영역")
    with production_detail_column.container(
        border=True,
        height=280,
        vertical_alignment="center",
    ):
        st.markdown("#### 세부수량 영역")

with st.container(border=True):
    st.subheader("주요공정 확보율 현황")
    process_chart_column, process_detail_column = st.columns([2, 1], gap="medium")
    with process_chart_column.container(
        border=True,
        height=280,
        vertical_alignment="center",
    ):
        st.markdown("#### 차트 영역")
    with process_detail_column.container(
        border=True,
        height=280,
        vertical_alignment="center",
    ):
        st.markdown("#### 세부공정 영역")
