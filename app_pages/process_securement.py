import streamlit as st

TAB_NAMES = ("📊 확보율", "설비대수", "소요대수")

st.title("공정별 확보율")

tabs = st.tabs(TAB_NAMES)
for tab, tab_name in zip(tabs, TAB_NAMES, strict=True):
    with tab:
        st.caption(f"{tab_name.removeprefix('📊 ')} 영역")
