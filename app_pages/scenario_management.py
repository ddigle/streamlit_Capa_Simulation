# Purpose: 시뮬레이션·설비 시나리오 관리, BigDataQuery 등록, 공식버전 자동 갱신을 탭으로 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.auto_official_update_tab import render_auto_official_update
from capa_simulation.components.bigdataquery_registration import (
    render_bigdataquery_registration,
)
from capa_simulation.components.equipment_scenario_management import (
    EQUIPMENT_KIND,
    SCENARIO_KIND_KEY,
    SCENARIO_KINDS,
    SCENARIO_MANAGEMENT_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
    SIMULATION_KIND,
    render_equipment_scenario_section,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.scenario_management import render_scenario_management
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
    st.error("시나리오 저장소를 준비하지 못했습니다: " + bootstrap_error_message(exc))
    st.stop()

# 세 탭을 항상 그린다(`tab.open` 으로 본문을 건너뛰지 않는다). 예전에는 열린 탭만 그렸는데,
# 그러면 다른 탭을 잠깐 여는 순간 그 탭의 form 위젯이 사라져 입력 중이던 값이 없어졌다.
# BigDataQuery 탭에 시뮬레이션 코드 목록 표가 생겼지만 그 표는 세션에 담긴 조회 결과를 표시만 하고
# 사내 DB 조회는 버튼 제출로만 돈다 — 숨은 탭을 다시 그리는 비용은 검색으로 좁힌 뷰의 직렬화뿐이다.
# 그 비용보다 탭을 오갈 때 폼 입력(기간 2개 + 등록 폼 6개)이 사라지는 쪽이 훨씬 나쁘다.
# 「자동 갱신」 탭은 설정·기록을 DB 에서 읽기만 하고(이 회차의 DB 핀 안이라 연결이 값싸다) 사내
# 조회·계산은 「지금 실행」을 누른 회차에만 돈다.
#
# 열린 탭은 기억한다(`stateful_tabs`, 2026-10-24 사용자 결정) — 화면 탭 줄로 다른 화면에 갔다
# 와도 보던 탭이 열린다. 대가로 탭을 누를 때마다 rerun 이 한 번 돈다. 세 탭을 다 그리므로 그
# rerun 에도 폼 위젯은 같은 자리에 남는다.
# 탭 이름 앞 아이콘은 그 탭이 하는 일이다(탭 목록 개선안 B).
management_tab, query_tab, auto_update_tab = stateful_tabs(
    [
        SCENARIO_MANAGEMENT_TAB,
        ":material/cloud_download: BigDataQuery 등록",
        ":material/autorenew: 자동 갱신",
    ],
    key=SCENARIO_MANAGEMENT_TABS_KEY,
)

with management_tab:
    # 「관리할 시나리오」 전환 — 시뮬레이션 시나리오(지금까지의 저장소 상태·시나리오 작업)와 설비
    # 시나리오(가용설비 현황의 탭이던 것, 2026-10-24 사용자 결정 D4). 고른 쪽 구획만 그린다 — 고르지
    # 않은 쪽의 위젯은 그 회차에 버려진다(아래 「시나리오 작업」 전환과 같은 성질). 설비 시나리오
    # 구획만 설비 DB 를 연다(시뮬레이션 쪽을 고른 회차에는 설비 DB 연결이 없다). 다른 화면(옛 배포
    # 흔적 경고의 단추)이 값을 적으므로 `default=` 를 주지 않고 칸이 없거나 목록 밖일 때만 심는다.
    if st.session_state.get(SCENARIO_KIND_KEY) not in SCENARIO_KINDS:
        st.session_state[SCENARIO_KIND_KEY] = SIMULATION_KIND
    kind = st.segmented_control(
        "관리할 시나리오",
        list(SCENARIO_KINDS),
        key=SCENARIO_KIND_KEY,
        persist_state="session",
        # 선택 해제를 허용하면 None 이 되어 아무 구획도 그리지 않는다.
        required=True,
    )
    if kind == EQUIPMENT_KIND:
        render_equipment_scenario_section()
    else:
        render_scenario_management(repository, database_path)
with query_tab:
    render_bigdataquery_registration(repository, database_path)
with auto_update_tab:
    render_auto_official_update(repository)
