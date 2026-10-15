# Purpose: 칸 선택 그림의 터치 스크롤 막이 스크립트가 고르는 그림과 듣개 계약을 고정한다.

"""터치 스크롤 막이(`components/plotly_touch_scroll.py`).

브라우저 동작(스와이프가 본문을 움직이고 탭이 칸 클릭이 되는지)은 터치를 켠 Chrome 으로 쟀다
(2026-10-15 — 막이 없이 선택을 켠 그림 위 스와이프는 본문 `scrollTop` 이 그대로, 막이를 건 뒤에는
세로·가로 모두 움직였고 탭 한 번에 공정 Capa 상세로 옮겼다). 여기서는 그 동작을 떠받치는 스크립트
계약을 고정한다 — 기본 동작을 막지 않는 캡처 단계 듣개이고, 넘긴 key 의 그림만 고른다.
"""

from __future__ import annotations

import json

import pytest

from capa_simulation.components.home_rendering import HOME_CELL_CHART_KEYS
from capa_simulation.components.plotly_touch_scroll import (
    HANDLER_NAME,
    plotly_touch_scroll_script,
    touch_scroll_selector,
)


def test_the_selector_picks_the_plotly_plot_inside_each_keyed_chart() -> None:
    assert touch_scroll_selector(["a_chart", "b-chart", "a_chart"]) == (
        ".st-key-a_chart .js-plotly-plot, .st-key-b-chart .js-plotly-plot"
    )


@pytest.mark.parametrize("keys", [[], ["bad key"], ["x'];alert(1);//"], ["a.b"]])
def test_a_missing_or_unsafe_key_is_refused(keys: list[str]) -> None:
    """key 는 CSS 선택자·JS 문자열에 들어간다. Streamlit `st-key-` 칸 이름에 쓰는 글자만 받는다."""
    with pytest.raises(ValueError):
        touch_scroll_selector(keys)


def test_the_guard_stops_the_touch_before_plotly_and_never_blocks_scrolling() -> None:
    """Plotly 끌기 층이 `touchstart` 에서 `preventDefault` 를 부르는 것이 스크롤을 막는 원인이다.
    막이는 캡처 단계에서 전파만 끊는다 — 기본 동작은 그대로 두어 브라우저가 스크롤하고, 탭은 호환
    마우스 사건으로 클릭이 된다. `passive` 라 스크롤을 기다리게 하지도 않는다."""
    script = plotly_touch_scroll_script(HOME_CELL_CHART_KEYS)

    assert json.dumps(touch_scroll_selector(HOME_CELL_CHART_KEYS)) in script
    for key in HOME_CELL_CHART_KEYS:
        assert f".st-key-{key} .js-plotly-plot" in script
    assert 'doc.addEventListener("touchstart", guard, { capture: true, passive: true });' in script
    assert "event.stopPropagation();" in script
    # 설명 주석은 원인을 `preventDefault` 로 부른다. 막이 자신은 그것을 부르지 않는다.
    assert ".preventDefault(" not in script
    assert "%(" not in script


def test_a_recreated_iframe_replaces_its_old_listener() -> None:
    """iframe 이 다시 만들어지면 옛 iframe 의 함수는 브라우저가 부르지 않는다. 창에 남긴 옛
    듣개를 떼고 새로 달아야 막이가 살아 있다 — 떼지 않고 건너뛰면 죽은 듣개만 남는다."""
    script = plotly_touch_scroll_script(HOME_CELL_CHART_KEYS)

    remove = (
        f"var previous = parentWindow.{HANDLER_NAME};\n"
        '  if (previous) doc.removeEventListener("touchstart", previous, true);'
    )
    assert remove in script
    assert script.index(remove) < script.index('doc.addEventListener("touchstart"')
    assert f"parentWindow.{HANDLER_NAME} = guard;" in script


def test_the_script_is_the_same_text_on_every_run() -> None:
    """테마 버튼 iframe 내용은 회차마다 같아야 한다 — 바뀌면 iframe 을 새로 만든다."""
    assert plotly_touch_scroll_script(HOME_CELL_CHART_KEYS) == plotly_touch_scroll_script(
        tuple(HOME_CELL_CHART_KEYS)
    )
