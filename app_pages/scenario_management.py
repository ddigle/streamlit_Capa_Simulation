# Purpose: Capa · 설비 시나리오 관리, DB 등록, 공식버전 자동 갱신을 탭 넷으로 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.auto_official_update_tab import render_auto_official_update
from capa_simulation.components.bigdataquery_registration import (
    render_bigdataquery_registration,
)
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.equipment_scenario_management import (
    CAPA_SCENARIO_TAB,
    EQUIPMENT_SCENARIO_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
    render_equipment_scenario_section,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.scenario_management import render_scenario_management
from capa_simulation.components.state_alerts import open_tab_name
from capa_simulation.components.tab_state import stateful_tabs
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.settings import DUCKDB_PATH

render_page_header("시나리오 관리")
render_page_guide("scenario_management", title="시나리오 관리")

try:
    database_path = str(DUCKDB_PATH.resolve())
    repository = get_scenario_repository(database_path)
except BOOTSTRAP_ERRORS as exc:
    message = "시나리오 저장소를 준비하지 못했습니다: " + bootstrap_error_message(exc)
    render_data_error(message, code="SC-02", text="시나리오 저장소를 준비하지 못했습니다")
    st.stop()

# Capa 시나리오 · DB 등록 · 자동 갱신 탭은 항상 그린다(`tab.open` 으로 본문을 건너뛰지 않는다).
# 열린 탭만 그리면 다른 탭을 잠깐 여는 순간 그 탭의 form 위젯이 사라져 입력 중이던 값이 없어진다.
# DB 등록 탭의 시뮬레이션 코드 목록 표는 세션에 담긴 조회 결과를 표시만 하고 사내 DB 조회는 버튼
# 제출로만 돈다 — 숨은 탭을 다시 그리는 비용은 검색으로 좁힌 뷰의 직렬화뿐이다. 그 비용보다 탭을
# 오갈 때 폼 입력(기간 2개 + 등록 폼 6개)이 사라지는 쪽이 훨씬 나쁘다. 「자동 갱신」 탭은 설정 ·
# 기록을 DB 에서 읽기만 하고(이 회차의 DB 핀 안이라 연결이 값싸다) 사내 조회 · 계산은 「지금
# 실행」 을 누른 회차에만 돈다.
#
# 설비 시나리오 탭만 그 탭이 열린 회차에 그린다 — 설비 DB 를 여는 것은 이 탭을 고른 회차뿐이다
# (AGENTS 5장 9). 대가로 그 탭 입력 칸에 적던 글은 다른 탭으로 옮기면 사라진다.
#
# 설비 시나리오 탭이 열린 회차에도 Capa 시나리오 탭은 숨은 채 그린다. 숨은 본문이 그 회차에 드는
# 시간은 24~41ms(그 회차 페이지 본문 83~97ms 가운데 — 샘플 관측, 검수용 합성 샘플 · 작업 넷 · 실제
# 앱 회차 중앙값)이고 건너뛰어도 본문은 74ms 라 얼마 줄지 않는다. 그 비용보다 복제 폼 · 고르던
# 작업이 설비 탭을 다녀오는 사이 사라지는 쪽이 나쁘다.
#
# 열린 탭은 기억한다(`stateful_tabs`, 2026-10-24 사용자 결정) — 화면 탭 줄로 다른 화면에 갔다
# 와도 보던 탭이 열린다. 대가로 탭을 누를 때마다 rerun 이 한 번 돈다.
# 탭 이름 앞 아이콘은 그 탭이 하는 일이다(탭 목록 개선안 B). 옛 세션에 남은 옛 탭 이름은 목록
# 밖이라 첫 탭이 열린다(Streamlit 이 첫 값으로 되돌리고 기억 칸은 `stateful_tabs` 가 목록 안 값만
# 쓴다).
QUERY_TAB = ":material/cloud_download: DB 등록"
AUTO_UPDATE_TAB = ":material/autorenew: 자동 갱신"
capa_tab, equipment_tab, query_tab, auto_update_tab = stateful_tabs(
    [CAPA_SCENARIO_TAB, EQUIPMENT_SCENARIO_TAB, QUERY_TAB, AUTO_UPDATE_TAB],
    key=SCENARIO_MANAGEMENT_TABS_KEY,
)
# 탭 안 상태 알림(공식버전 없음 `SC-01` · BigDataQuery 설정 `AD-04` · 자동 갱신 예약
# `AU-01/02`)은 그 탭이 열린 회차에만 낸다 — 닫힌 탭이면 None(`open_tab_name`). 「그 화면으로」 가
# 그 탭을 연다.

with capa_tab:
    render_scenario_management(
        repository,
        database_path,
        alert_tab=open_tab_name(capa_tab, CAPA_SCENARIO_TAB),
    )
with equipment_tab:
    if equipment_tab.open:
        render_equipment_scenario_section()
with query_tab:
    render_bigdataquery_registration(
        repository, database_path, alert_tab=open_tab_name(query_tab, QUERY_TAB)
    )
with auto_update_tab:
    render_auto_official_update(
        repository, alert_tab=open_tab_name(auto_update_tab, AUTO_UPDATE_TAB)
    )
