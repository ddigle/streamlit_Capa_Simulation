# Purpose: HOME 토글의 세션 키와 기본값을 UI·계산·시나리오 초기화에 공유한다.

"""UI 모듈을 import 하지 않아도 읽을 수 있는 HOME 표시 상태 계약."""

from collections.abc import Mapping
from types import MappingProxyType

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

# 계산은 위젯보다 먼저 실행되므로 두 곳이 같은 기본값을 읽는다. 시나리오를 바꿀 때도
# 이 키들만 지워 기본 표시로 돌아가며, 탭·조회 조건과 공용 프로필 선택은 유지한다.
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
