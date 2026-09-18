# Purpose: 시나리오를 활성화할 때 버려야 하는 세션 값의 목록을 고정한다.

from capa_simulation.components.home_preference import (
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.scenario_activation import _STALE_UI_KEYS


def test_view_state_survives_a_scenario_change() -> None:
    """보던 조건은 시나리오가 바뀌어도 그대로 있어야 한다. **데이터만 바뀐다.**

    예전에는 선행·GAP·상세를 껐다. 「지금 그 시나리오를 전제로 켠 것」이라는 이유였는데,
    셋 중 어느 것도 시나리오에 딸려 있지 않다.

    - 선행 물량은 `app_meta.global_advance_load` 한 장이고 키가 **생산계획년월 하나**다.
      제품에 붙지 않으므로 어느 시나리오에도 그대로 적용된다. 「남의 선행 물량」이라고
      부를 두 번째 값이 애초에 없다.
    - GAP 비교 대상도 공용 프로필이고, 고른 시나리오·리비전을 스스로 들고 있다. 다른
      시나리오와 견주는 것이 이 기능의 목적이다.
    - 상세는 거래선을 분류로 더할지일 뿐이라 값에 닿지 않는다.

    실행 토글은 처음부터 목록에 없었다. 같은 성격인데 하나만 빠져 있었다는 것이,
    이 규칙이 무엇을 지키고 있지 않았다는 증거이기도 하다.
    """
    for key in (
        ADVANCE_TOGGLE_KEY,
        COMPARISON_TOGGLE_KEY,
        PLAN_DETAIL_CUSTOMER_KEY,
        EXECUTION_TOGGLE_KEY,
        EDP_TOGGLE_KEY,
    ):
        assert key not in _STALE_UI_KEYS, key


def test_only_previous_scenario_values_are_dropped() -> None:
    """목록에 남는 것은 **앞 시나리오의 값이 담긴 칸**뿐이다.

    그것들은 지우지 않으면 새 시나리오 화면에 옛 수치가 그대로 그려진다. 화면 상태와 달리
    되살릴 수 있는 종류가 아니라 반드시 버려야 한다.
    """
    assert set(_STALE_UI_KEYS) == {
        "load_conversion_inputs",
        "unit_capacity_result",
        "capacity_standards_inputs",
        "load_conversion_source_token",
        "capacity_standards_source_token",
        HOME_FIGURE_CACHE_KEY,
    }


def test_the_stale_key_list_has_no_duplicates() -> None:
    assert len(set(_STALE_UI_KEYS)) == len(_STALE_UI_KEYS)


def test_the_figure_cache_key_has_one_owner() -> None:
    """Figure 캐시 칸의 이름은 세 곳이 쓴다. 리터럴로 흩어 두면 이름을 바꿀 때 한 곳만 고쳐진다.

    그러면 시나리오를 바꿔도 옛 칸이 남아 **남의 시나리오 그림이 그대로 뜬다.**
    소유자는 `io/reference_cache` 하나다 — pandas·streamlit 만 보는 잎이라 셋 다 여기서
    가져올 수 있고, `components` 쪽에 두면 `scenario_activation` 이 import 하지 못한다.
    """
    from capa_simulation.components.home_rendering import (
        HOME_FIGURE_CACHE_KEY as rendering_key,
    )

    assert rendering_key is HOME_FIGURE_CACHE_KEY
    assert HOME_FIGURE_CACHE_KEY in _STALE_UI_KEYS
