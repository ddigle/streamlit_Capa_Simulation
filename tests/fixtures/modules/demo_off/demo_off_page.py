# Purpose: 견본 사내 모듈 demo_off 의 화면 — module.json 이 꺼 두어 앱에 등록되지 않는다.

import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(ctx, "꺼진 데모")
st.write("꺼진 모듈의 화면입니다.")
