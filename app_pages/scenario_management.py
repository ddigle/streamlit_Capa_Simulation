# Purpose: 시나리오·BigDataQuery 등록·공용 표시순서 관리 기능을 탭으로 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.bigdataquery_registration import (
    render_bigdataquery_registration,
)
from capa_simulation.components.display_order_management import (
    render_display_order_management,
)
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.scenario_management import render_scenario_management
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.settings import DUCKDB_PATH

render_page_header(
    "시나리오 관리",
    description="DuckDB 시나리오·리비전·공식버전과 웹 표시순서를 관리합니다.",
)

try:
    database_path = str(DUCKDB_PATH.resolve())
    repository = get_scenario_repository(database_path)
except Exception as exc:
    st.error(f"시나리오 저장소를 준비하지 못했습니다: {exc}")
    st.stop()

# 세 탭을 항상 그린다. 예전에는 열린 탭만 그렸는데(`if tab.open`), 그러면 다른 탭을 잠깐 여는
# 순간 그 탭의 form 위젯이 사라져 입력 중이던 값(폼 7개)이 없어졌다. 숨은 탭에서 건너뛰어도
# 되는 것은 계산·표·차트뿐인데 이 페이지에는 그런 것이 없다 — 표시순서 검증·CSV 는
# 공용 버전 키로 캐시했다. 그래서 탭 전환에 rerun 을 걸 이유도 없다.
management_tab, query_tab, display_order_tab = st.tabs(
    ["시나리오 관리", "BigDataQuery 등록", "표시순서 관리"]
)

with management_tab:
    render_scenario_management(repository, database_path)
with query_tab:
    render_bigdataquery_registration(repository, database_path)
with display_order_tab:
    render_display_order_management(repository)
