# Purpose: 상단 띠 CSS 가 사이드바 접기 버튼을 마우스와 무관하게 늘 보이게 두는지 고정한다.

import re

from capa_simulation.components.app_header import _header_css


def test_sidebar_collapse_button_is_always_visible_on_screen() -> None:
    """Streamlit 은 마우스를 올렸을 때만 버튼을 띄운다 — 화면 매체에서는 늘 보이게 덮는다."""
    css = _header_css()
    screen = re.search(r"@media screen \{(.*?)\n\}", css, re.S)
    assert screen is not None
    block = screen.group(1)
    assert '[data-testid="stSidebarCollapseButton"]' in block
    assert "visibility: visible !important;" in block
