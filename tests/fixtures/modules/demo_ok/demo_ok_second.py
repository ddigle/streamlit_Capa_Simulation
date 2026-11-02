# Purpose: 견본 모듈 demo_ok 의 둘째 화면 — 한 모듈이 화면 여럿을 두는 꼴을 보인다.

import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(ctx, "데모 둘째")
st.write("둘째 화면입니다.")
