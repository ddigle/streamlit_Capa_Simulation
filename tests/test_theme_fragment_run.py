# Purpose: 프래그먼트 회차가 그 세션의 앱 전체 회차와 같은 테마 팔레트를 읽는지 고정한다.

"""프래그먼트만 도는 회차의 테마 — 페이지가 아니라 장치(`design/theme.py`)를 시험한다.

프래그먼트 회차는 `app.py` 머리의 `theme.begin_run()` 을 지나지 않고, Streamlit 은 앞 회차가
끝났으면 새 스레드에서 돌린다(AppTest 도 그렇다). 그 회차가 읽는 토큰은 세션이 적어 둔 앱 전체
회차의 테마여야 한다. 팝업(`st.dialog`) 본문도 같은 프래그먼트 회차라, 팝업 안 조작이 다시 그리는
스타일(HOME 공정 필터 타일 풍선 `process_picker.tile_tooltip_style`)도 여기서 함께 본다.
"""

from __future__ import annotations

import pytest
from fragment_browser import install_fragment_browser
from streamlit.testing.v1 import AppTest

from capa_simulation.design import tokens

_SCRIPT = """
import streamlit as st

from capa_simulation.components.process_picker import tile_tooltip_style
from capa_simulation.design import theme, tokens

theme.begin_run()


@st.fragment
def body() -> None:
    st.button("tick", key="tick")
    st.html(f"<div>mode={theme.current_mode()} surface={tokens.SURFACE}</div>")
    st.html(tile_tooltip_style(["x"]))


body()
"""


def _bodies(messages: list[object]) -> list[str]:
    out: list[str] = []
    for message in messages:
        delta = getattr(message, "delta", None)
        if delta is None or delta.WhichOneof("type") != "new_element":
            continue
        if delta.new_element.WhichOneof("type") == "html":
            out.append(str(delta.new_element.html.body))
    return out


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_a_fragment_run_reads_the_theme_its_full_run_resolved(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 전체 회차와 프래그먼트 회차가 같은 팔레트다 — 본문 글자와 이벤트 칸의 풍선 스타일 모두."""
    runner = install_fragment_browser(monkeypatch)
    app = AppTest.from_string(_SCRIPT, default_timeout=60)
    app.query_params["theme"] = mode
    app.run()
    surface = tokens.palette_value(mode, "SURFACE")
    full = _bodies(list(runner.messages))
    assert f"mode={mode} surface={surface}" in " ".join(full)
    assert f"background: {surface};" in " ".join(full)

    fragment = runner.fragment_of("tick")
    runner.fragment_queue = [fragment]
    app.button(key="tick").click().run()
    assert runner.started == [[fragment]]
    in_fragment = _bodies(list(runner.messages))
    assert f"mode={mode} surface={surface}" in " ".join(in_fragment), in_fragment
    assert f"background: {surface};" in " ".join(in_fragment), in_fragment
