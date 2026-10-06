# Purpose: HOME 결론 문장의 강조가 두 테마 모두에서 읽히는 색 짝으로 그려지는지 고정한다.

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.design.tokens import palette_value

SCRIPT = """
import streamlit as st

from capa_simulation.components.decision_summary import render_home_capacity_decision
from capa_simulation.design import theme
from capa_simulation.services.home_decision import CapacityDecision
from capa_simulation.services.securement_threshold import SecurementThresholds

theme.begin_run()
render_home_capacity_decision(
    CapacityDecision(
        process="Laser & Saw", month=202807, rate=0.81, judged=10, warning=2, shortage=3
    ),
    thresholds=SecurementThresholds(1.095, 0.995),
)
"""


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_headline_highlight_puts_text_on_the_status_fill(mode: str) -> None:
    """`STATUS_*` 는 면색이다. 글자색으로 쓰면 어두운 테마의 부족이 2.0:1 로 읽히지 않았다.

    면에 깔고 글자는 `TEXT` 로 쓴다 — 토큰이 두 테마 모두에서 보증하는 짝이다.
    """
    app = AppTest.from_string(SCRIPT)
    app.query_params["theme"] = mode
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    headline = next(
        element.value for element in app.markdown if "가장 낮은 확보율" in element.value
    )
    shortage = palette_value(mode, "STATUS_SHORTAGE")
    text = palette_value(mode, "TEXT")
    assert f"background:{shortage};color:{text}" in headline
    assert f'style="color:{shortage}"' not in headline
    # 공정명은 HTML 로 해석되지 않게 이스케이프한다.
    assert "Laser &amp; Saw" in headline
