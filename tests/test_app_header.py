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


def test_the_header_text_leaves_room_for_the_whole_toolbar() -> None:
    """툴바(Summary·Guide·테마·Deploy·⋮)가 1100px 창에서 323px 를 쓴다. 16rem(224px)만 비우면
    머리 글자가 Summary 밑으로 들어갔다(2026-10-05 E2E)."""
    widths = re.findall(r"max-width: calc\(100% - (\d+)rem\)", _header_css())
    root_px = 14
    assert widths and int(widths[0]) * root_px >= 323 + 21 + 12


def test_inline_code_in_body_text_is_close_to_the_body_size() -> None:
    """인라인 코드의 한글이 0.75em 대체 글꼴로 9~10px 까지 작아졌다(2026-10-05 E2E)."""
    css = _header_css()
    block = css[css.index('[data-testid="stMarkdownContainer"] :not(pre) > code') :]
    block = block[: block.index("}")]
    assert "font-size: 0.9em;" in block
