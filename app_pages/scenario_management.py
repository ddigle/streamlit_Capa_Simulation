# Purpose: 시나리오 관리와 BigDataQuery 등록 기능을 탭으로 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.bigdataquery_registration import (
    render_bigdataquery_registration,
)
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.scenario_management import render_scenario_management
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.settings import DUCKDB_PATH

render_page_header(
    "시나리오 관리",
    description="DuckDB 시나리오·리비전·공식버전과 BigDataQuery 등록을 관리합니다.",
)

try:
    database_path = str(DUCKDB_PATH.resolve())
    repository = get_scenario_repository(database_path)
except Exception as exc:
    st.error(f"시나리오 저장소를 준비하지 못했습니다: {exc}")
    st.stop()

# 두 탭을 항상 그린다. 예전에는 열린 탭만 그렸는데(`if tab.open`), 그러면 다른 탭을 잠깐 여는
# 순간 그 탭의 form 위젯이 사라져 입력 중이던 값이 없어졌다. BigDataQuery 탭에 시뮬레이션
# 코드 목록 표가 생겼지만 그 표는 세션에 담긴 조회 결과를 표시만 하고 사내 DB 조회는 버튼
# 제출로만 돈다 — 숨은 탭을 다시 그리는 비용은 검색으로 좁힌 뷰의 직렬화뿐이다. 그 비용보다
# 탭을 오갈 때 폼 입력(기간 2개 + 등록 폼 6개)이 사라지는 쪽이 훨씬 나쁘다. 그래서 탭
# 전환에 rerun 을 걸 이유도 없다.
management_tab, query_tab = st.tabs(["시나리오 관리", "BigDataQuery 등록"])

with management_tab:
    render_scenario_management(repository, database_path)
with query_tab:
    render_bigdataquery_registration(repository, database_path)
