# Purpose: 강조색으로 칠한 단추(primary)의 글자색 스타일이 테마마다 강조 면 위 글자색인지 검사한다.

"""강조색으로 칠한 단추의 글자색(`components/accent_button_style.py`).

어두운 테마의 강조색 `#2DD4BF` 위 Streamlit 흰 글자는 1.86:1 이었다(브라우저 E2E — 표준 목표
「가용설비 붙여넣기」). 앱 전체의 primary·primary 폼 제출 단추 글자를 `ACCENT_TEXT` 로 다시 건다.
`app.py` 가 매 회차 그 스타일을 보내는지는 `tests/test_app_navigation.py` 가 본다.
"""

from __future__ import annotations

import pytest
from test_design_tokens import SMALL_TEXT_MINIMUM, contrast_ratio

from capa_simulation.components.accent_button_style import (
    ACCENT_BUTTON_SELECTORS,
    accent_button_style,
)
from capa_simulation.design import tokens


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_painted_buttons_write_in_the_text_colour_for_the_accent_fill(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """칠한 단추(보통·폼 제출)의 글자는 그 테마의 강조 면 위 글자색이다 — 밝게는 Streamlit 의
    흰 글자 그대로, 어둡게는 바탕색. 잠긴 단추(투명 바탕·흐린 글자)는 고르지 않는다."""
    from capa_simulation.design import theme

    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    colour = tokens.palette_value(mode, "ACCENT_TEXT")

    assert accent_button_style() == (
        '<style>button[kind="primary"]:not(:disabled), '
        f'button[kind="primaryFormSubmit"]:not(:disabled) {{ color: {colour}; }}</style>'
    )
    assert all(selector.endswith(":not(:disabled)") for selector in ACCENT_BUTTON_SELECTORS)
    assert contrast_ratio(colour, tokens.palette_value(mode, "ACCENT")) >= SMALL_TEXT_MINIMUM


def test_the_light_theme_keeps_the_white_streamlit_draws() -> None:
    """밝은 테마는 Streamlit 이 그리던 흰 글자 그대로다 — 이 스타일이 밝은 화면을 바꾸지 않는다."""
    assert tokens.palette_value("light", "ACCENT_TEXT") == "#FFFFFF"
    assert contrast_ratio("#FFFFFF", tokens.palette_value("dark", "ACCENT")) < SMALL_TEXT_MINIMUM
