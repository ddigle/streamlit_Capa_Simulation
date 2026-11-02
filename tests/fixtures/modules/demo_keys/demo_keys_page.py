# Purpose: 견본 모듈 demo_keys 의 화면 — 접두 없는 세션 키를 만들어 실행 알림을 보인다.

import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(ctx, "키 데모")
st.session_state["plain_key"] = 1
st.write("접두 없는 키를 하나 만들었습니다.")
