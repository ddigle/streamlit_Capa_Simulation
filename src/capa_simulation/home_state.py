# Purpose: HOME 토글의 세션 키·기본값과 「설정」 팝업 열림 칸을 UI·계산·시나리오 초기화에 공유한다.

"""UI 모듈을 import 하지 않아도 읽을 수 있는 HOME 표시 상태 계약."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

EDP_TOGGLE_KEY = "home_preference_include_edp"
PAST_DATA_TOGGLE_KEY = "home_preference_include_past"
# 화면 이름은 「선행 B/O」다. 키는 세션 계약이라 예전 이름(advance) 그대로 둔다.
ADVANCE_TOGGLE_KEY = "home_show_advance"
# 「선행 입고」 — 선행 입고 실적을 Density 칸에 적기만 한다(계산은 바꾸지 않는다).
ADVANCE_SHIPMENT_TOGGLE_KEY = "home_show_advance_shipment"
EXECUTION_TOGGLE_KEY = "home_show_execution"
PLAN_DETAIL_CUSTOMER_KEY = "home_preference_plan_detail_customer"
COMPARISON_TOGGLE_KEY = "home_show_comparison"
# 제품별 비중 행의 단위(`Wafer`·`PKG`). 토글이 아니라 고르는 칸이라 아래 토글 기본값 묶음에
# 넣지 않는다 — 그 묶음은 시나리오를 바꿀 때 지우는 목록이기도 한데, 단위는 시나리오와
# 무관한 보는 방식이라 바꿔도 남는 것이 맞다.
PRODUCT_SHARE_BASIS_KEY = "home_product_share_basis"
PRODUCT_SHARE_BASIS_DEFAULT = "Wafer"

# 계산은 위젯보다 먼저 실행되므로 두 곳이 같은 기본값을 읽는다 — 계산은 칸이 없을 때의 값으로,
# 사이드바 카드는 칸이 없을 때 세션에 심는 값으로(위젯 `value=` 로 주지 않는다). 시나리오를
# 바꿀 때도 이 키들에만 기본값을 다시 **적어**(지우면 브라우저가 옛 값을 되보낸다) 기본 표시로
# 돌아가며, 탭·조회 조건과 공용 프로필 선택은 유지한다.
HOME_TOGGLE_DEFAULTS: Mapping[str, bool] = MappingProxyType(
    {
        EDP_TOGGLE_KEY: False,
        PAST_DATA_TOGGLE_KEY: True,
        ADVANCE_TOGGLE_KEY: False,
        ADVANCE_SHIPMENT_TOGGLE_KEY: False,
        EXECUTION_TOGGLE_KEY: False,
        PLAN_DETAIL_CUSTOMER_KEY: False,
        COMPARISON_TOGGLE_KEY: False,
    }
)


def home_toggle(state: Mapping[Any, Any], key: str) -> bool:
    """HOME 토글 하나의 값 — 세션 칸(`st.session_state` 를 넘긴다)이 없으면 위 기본값.

    위젯보다 먼저 도는 계산과 다른 화면이 HOME 토글을 읽는 한 길이다. 기본값 표에 없는 키는
    `KeyError` 다(토글이 아닌 칸을 이 길로 읽지 않는다).
    """
    return bool(state.get(key, HOME_TOGGLE_DEFAULTS[key]))


# HOME 「설정」 팝업(2026-11-02 사용자 요청 — 전에는 HOME 의 `Preference`·`Past Data` 탭). HOME 은
# 탭 없이 Main 한 화면이고, 공용 설정은 사이드바 「HOME 설정」 상자가 여는 큰 팝업의 안쪽 탭이다
# (`components/home_settings.py`). 페이지 스크립트는 import 할 수 없어 키·라벨을 여기 둔다 — 「LOB
# 표시 조건」 카드의 주요 Case 칩(`components/home_main_case_chips.py`)은 「지정 안 함」 칩을 누르면
# 이 팝업을 `비교 · 주요 Case` 탭으로 연다.
#
# 안쪽 탭은 쓰는 묶음 다섯이다(2026-11-04 사용자 검수 home-u01 — 전에는 옮겨 온 `Preference`·`Past
# Data` 둘이라 Preference 한 탭에 상자 아홉이 세로로 섰다): 고르면 곧 저장되는 비교 대상 둘, 판정
# 기준, 「LOB 표시 조건」 토글이 켜는 월별 입력 셋(선행 B/O · 선행 입고 실적 · 확보율 보정), 화면에
# 보이는 것을 정하는 공지 · 표시 셋(Summary 공지 · B/N Top5 구간 · 주요공정 프리셋), 과거 구간. 앞
# 넷은 Preference 편집기(`home_preference`)가, 마지막은 Past Data 편집기(`past_data_management`)가
# 그린다 (`HOME_PREFERENCE_TABS`).
#
# 열림 칸은 HOME 한 화면에 하나(`<페이지>_open_dialog` — `page_bootstrap.PAGE_DIALOG_SUFFIX`, AGENTS
# 9장 「팝업과 콜백」)이고 값이 팝업을 가른다. 안쪽 탭 라벨은 탭의 위젯 값이라 바꾸면 세션에 남은
# 값과 어긋난다.
HOME_DIALOG_KEY = "home_open_dialog"
HOME_SETTINGS_DIALOG = "settings"
HOME_SETTINGS_TAB_KEY = "home_settings_tab"
HOME_CASES_TAB = ":material/compare_arrows: 비교 · 주요 Case"
HOME_THRESHOLD_TAB = ":material/rule: 판정 기준"
HOME_MONTHLY_TAB = ":material/edit_calendar: 선행 · 보정"
HOME_DISPLAY_TAB = ":material/campaign: 공지 · 표시"
HOME_PAST_TAB = ":material/history: Past Data"
HOME_PREFERENCE_TABS = (HOME_CASES_TAB, HOME_THRESHOLD_TAB, HOME_MONTHLY_TAB, HOME_DISPLAY_TAB)
HOME_SETTINGS_TAB_LABELS = (*HOME_PREFERENCE_TABS, HOME_PAST_TAB)
