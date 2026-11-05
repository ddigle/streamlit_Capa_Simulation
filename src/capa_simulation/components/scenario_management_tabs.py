# Purpose: 시나리오 관리 화면의 탭 이름 · 탭 기억 key 와 다른 화면에서 그 탭으로 옮기는 길을 둔다.

"""시나리오 관리 탭 넷의 이름은 여기 한 곳이다.

화면(`app_pages/scenario_management.py`)과 탭 본문 조각들, 그 탭으로 데려가는 다른 화면이 같은
이름을 본다 — 알림의 `tab`(「그 화면으로」)도 이 이름에서 나온다(`*_TAB_NAME`).
"""

from __future__ import annotations

from typing import Final

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from capa_simulation.components.state_alerts import tab_name
from capa_simulation.components.tab_state import remember_open_tab
from capa_simulation.navigation import SCENARIO_MANAGEMENT
from capa_simulation.page_tabs_state import refused_at_tab_limit

SCENARIO_MANAGEMENT_TABS_KEY: Final = "scenario_management_tabs"
# 탭 이름 앞 아이콘은 그 탭이 하는 일이다(탭 목록 개선안 B). 설비 시나리오 아이콘은 사이드바 설비
# 시나리오 칸(`EQUIPMENT_SCENARIO_FIELD_ICON`)과 같다.
CAPA_SCENARIO_TAB: Final = ":material/database: Capa 시나리오"
EQUIPMENT_SCENARIO_TAB: Final = ":material/account_tree: 설비 시나리오"
QUERY_TAB: Final = ":material/cloud_download: DB 등록"
AUTO_UPDATE_TAB: Final = ":material/autorenew: 자동 갱신"
# 알림의 `tab` — 탭 본문이 낸 줄의 「그 화면으로」 가 그 탭을 연다.
CAPA_SCENARIO_TAB_NAME: Final = tab_name(CAPA_SCENARIO_TAB)
EQUIPMENT_SCENARIO_TAB_NAME: Final = tab_name(EQUIPMENT_SCENARIO_TAB)
QUERY_TAB_NAME: Final = tab_name(QUERY_TAB)
AUTO_UPDATE_TAB_NAME: Final = tab_name(AUTO_UPDATE_TAB)


def open_scenario_management_tab(label: str) -> None:
    """시나리오 관리의 그 탭으로 옮긴다 — 그 화면의 탭 기억 칸만 적는다.

    링크(`st.page_link`)로는 탭을 고르지 못해 기억된 탭이 열리므로, 특정 탭을 가리키는 길은 단추와
    이 함수다. 위젯 콜백이 아니라 회차 본문에서 부른다(AGENTS 9장 — 콜백 안 `st.switch_page` 금지).
    화면 탭 상한에 걸리면 아무것도 적지 않는다(`refused_at_tab_limit`). 갈 곳이 없으면(내비게이션
    없는 단독 실행) 칸만 적고 옮기지 않는다.
    """
    if refused_at_tab_limit(SCENARIO_MANAGEMENT.path):
        return
    remember_open_tab(SCENARIO_MANAGEMENT_TABS_KEY, label)
    try:
        st.switch_page(SCENARIO_MANAGEMENT.path)
    except StreamlitPageNotFoundError:
        return
