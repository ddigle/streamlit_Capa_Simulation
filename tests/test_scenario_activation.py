# Purpose: 시나리오를 활성화할 때 버려야 하는 세션 값의 목록을 고정한다.

from capa_simulation.components.home_preference import (
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.scenario_activation import _STALE_UI_KEYS


def test_home_toggles_are_dropped_when_another_scenario_is_activated() -> None:
    """선행·GAP·상세는 **지금 그 시나리오**를 전제로 켠 것이다.

    켠 채로 시나리오를 바꾸면 남의 선행 물량과 남의 비교 대상이 새 계획 위에 얹혀 그려진다.
    화면에는 토글이 켜져 있으니 사용자는 그것이 새 시나리오의 값이라고 읽는다.
    """
    for key in (ADVANCE_TOGGLE_KEY, COMPARISON_TOGGLE_KEY, PLAN_DETAIL_CUSTOMER_KEY):
        assert key in _STALE_UI_KEYS, key


def test_the_stale_key_list_has_no_duplicates() -> None:
    assert len(set(_STALE_UI_KEYS)) == len(_STALE_UI_KEYS)
