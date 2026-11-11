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

STORE_KEY = ctx.key("store")
QUERY_KEY = ctx.key("query")


def _upload() -> None:
    result: api.S3Result = api.s3_upload(ctx, "demo.csv")
    st.session_state[STORE_KEY] = "올림" if result.ok else result.reason


def _download() -> None:
    result = api.s3_download(ctx, "demo.csv")
    st.session_state[STORE_KEY] = "받음" if result.ok else result.reason


def _query() -> None:
    try:
        frame = api.query_bigdataquery(ctx, "SELECT 1 AS 값")
    except api.BigDataQueryError as error:
        st.session_state[QUERY_KEY] = error.kind
    else:
        st.session_state[QUERY_KEY] = f"{len(frame)}행"


upload, download, query = st.columns(3)
upload.button("올리기", key=ctx.key("upload"), on_click=ctx.callback(_upload))
download.button("받기", key=ctx.key("download"), on_click=ctx.callback(_download))
query.button("조회", key=ctx.key("ask"), on_click=ctx.callback(_query))
st.caption(
    f"S3 {st.session_state.get(STORE_KEY, '-')} · 상한 {api.S3_MAX_BYTES // 1024 // 1024} MiB · "
    f"조회 {st.session_state.get(QUERY_KEY, '-')}"
)
saved = sorted(path.name for path in ctx.data_dir.glob("*.csv"))
st.caption(f"저장한 합성 파일 {len(saved)}개")


@st.fragment
def _sample_table() -> None:
    with ctx.guard():
        frame = pd.DataFrame({"월": ["2026-01", "2026-02", "2026-03"], "값": [10, 12, 9]})
        st.dataframe(frame, hide_index=True, width="stretch")


_sample_table()
