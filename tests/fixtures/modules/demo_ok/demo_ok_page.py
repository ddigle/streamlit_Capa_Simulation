# Purpose: 견본 모듈 demo_ok 의 첫 화면 — 공개 창구 v1 의 이름을 모두 쓰는 합성 화면이다.

import pandas as pd
import streamlit as st

from capa_simulation import module_api as api

try:
    ctx: api.ModuleContext = api.context(__file__)
except api.ModuleContextError:
    st.error("이 화면의 module.json 을 찾지 못했습니다.")
    st.stop()

api.page_header(ctx, "데모 화면", description="합성 데이터로 도는 예시 모듈입니다.")

colors = api.palette()
major, minor = api.API_VERSION
st.caption(
    f"창구 API {major}.{minor} · 역할 색 {len(api.PALETTE_KEYS)}가지 · "
    f"강조색 {colors['accent']} · 글꼴 {api.FONT_FAMILY.split(',')[0]} · "
    f"성숙도 표기 {api.IMPLEMENTING_SUFFIX}"
)

COUNT_KEY = ctx.key("count")


def _add_one() -> None:
    st.session_state[COUNT_KEY] = int(st.session_state.get(COUNT_KEY, 0)) + 1


st.button("하나 더", key=ctx.key("add"), on_click=ctx.callback(_add_one))
st.metric("누른 수", int(st.session_state.get(COUNT_KEY, 0)))
saved = sorted(path.name for path in ctx.data_dir.glob("*.csv"))
st.caption(f"저장한 합성 파일 {len(saved)}개")


@st.fragment
def _sample_table() -> None:
    with ctx.guard():
        frame = pd.DataFrame({"월": ["2026-01", "2026-02", "2026-03"], "값": [10, 12, 9]})
        st.dataframe(frame, hide_index=True, width="stretch")


_sample_table()
