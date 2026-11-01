# Purpose: 견본 사내 모듈 demo_crash 의 화면 — 한 줄 그린 뒤 오류를 내 오류 카드를 보인다.

import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(ctx, "고장 데모")
st.write("오류 앞까지 그린 줄입니다.")
raise RuntimeError("데모 오류")
