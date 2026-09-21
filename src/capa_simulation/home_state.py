# Purpose: HOME 토글의 세션 키와 기본값을 UI·계산·시나리오 초기화에 공유한다.

"""UI 모듈을 import 하지 않아도 읽을 수 있는 HOME 표시 상태 계약."""

from collections.abc import Mapping
from types import MappingProxyType

EDP_TOGGLE_KEY = "home_preference_include_edp"
PAST_DATA_TOGGLE_KEY = "home_preference_include_past"
ADVANCE_TOGGLE_KEY = "home_show_advance"
EXECUTION_TOGGLE_KEY = "home_show_execution"
PLAN_DETAIL_CUSTOMER_KEY = "home_preference_plan_detail_customer"
COMPARISON_TOGGLE_KEY = "home_show_comparison"

# 계산은 위젯보다 먼저 실행되므로 두 곳이 같은 기본값을 읽는다. 시나리오를 바꿀 때도
# 이 키들만 지워 기본 표시로 돌아가며, 탭·조회 조건과 공용 프로필 선택은 유지한다.
HOME_TOGGLE_DEFAULTS: Mapping[str, bool] = MappingProxyType(
    {
        EDP_TOGGLE_KEY: False,
        PAST_DATA_TOGGLE_KEY: True,
        ADVANCE_TOGGLE_KEY: False,
        EXECUTION_TOGGLE_KEY: False,
        PLAN_DETAIL_CUSTOMER_KEY: False,
        COMPARISON_TOGGLE_KEY: False,
    }
)
