# Purpose: 상단 띠 CSS 와 껍데기 스타일이 접기 버튼·툴바 폭·메뉴·인쇄·인증 표시를 지키는지 고정한다.

import re

from capa_simulation.components.app_header import SHELL_STYLE, _header_css
from capa_simulation.settings import APP_AUTH_CODE, APP_AUTH_EXPIRY


def test_sidebar_collapse_button_is_always_visible_on_screen() -> None:
    """Streamlit 은 마우스를 올렸을 때만 버튼을 띄운다 — 화면 매체에서는 늘 보이게 덮는다."""
    css = _header_css()
    screen = re.search(r"@media screen \{(.*?)\n\}", css, re.S)
    assert screen is not None
    block = screen.group(1)
    assert '[data-testid="stSidebarCollapseButton"]' in block
    assert "visibility: visible !important;" in block


def test_the_header_text_leaves_room_for_the_whole_toolbar() -> None:
    """툴바(Summary·Guide·테마·Print·Deploy)가 1100px 창에서 355px 를 쓴다(⋮ 를 감추고 Print 를
    더한 뒤 실측). 16rem(224px)만 비우면 머리 글자가 Summary 밑으로 들어갔다(2026-10-05 E2E)."""
    widths = re.findall(r"max-width: calc\(100% - (\d+)rem\)", _header_css())
    root_px = 14
    assert widths and int(widths[0]) * root_px >= 355 + 21 + 12
    # 사이드바를 접으면 글자가 4rem 에서 시작한다. 민 만큼(2.5rem) 최대 폭도 줄어야 한다.
    collapsed = re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", _header_css())[-1]
    assert float(collapsed) * root_px >= 355 + 4 * root_px + 12


def test_inline_code_in_body_text_is_close_to_the_body_size() -> None:
    """인라인 코드의 한글이 0.75em 대체 글꼴로 9~10px 까지 작아졌다(2026-10-05 E2E)."""
    css = _header_css()
    block = css[css.index('[data-testid="stMarkdownContainer"] :not(pre) > code') :]
    block = block[: block.index("}")]
    assert "font-size: 0.9em;" in block
    # 캡션(`st.caption`)은 마크다운 칸이 아니라 따로 된 칸이다 — 둘 다 걸어야 한다.
    assert '[data-testid="stCaptionContainer"] :not(pre) > code' in block


def _split_shell_style() -> tuple[str, str]:
    """껍데기 스타일을 `@media print` 덩어리와 그 밖(화면에도 걸리는 규칙)으로 나눈다."""
    body = re.fullmatch(r"<style>(.*)</style>", SHELL_STYLE, re.S)
    assert body is not None
    css = body.group(1)
    # 안쪽 중괄호 한 겹(`@page {}`·규칙들)까지만 품는 덩어리다.
    blocks = re.findall(r"@media print \{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", css)
    assert len(blocks) == 1, blocks
    return css.replace(blocks[0], ""), blocks[0]


def test_the_streamlit_main_menu_is_hidden_and_nothing_else() -> None:
    """⋮ 메뉴는 통째로 감춘다(2026-10-05 사용자 결정 — 인쇄·테마는 툴바 단추가 맡는다). 최소 모드는
    테마 항목을 남겨 메뉴가 사라지지 않는다. 화면에 걸리는 규칙은 메뉴 하나만 고른다 — Deploy 와
    우리 단추가 앉는 툴바 슬롯은 그대로여야 한다. 규칙은 머리 띠 CSS 가 아니라 부트스트랩 앞에서
    따로 나가는 껍데기 스타일에 있다(차례는 `test_app_navigation` 이 지킨다)."""
    for css in (SHELL_STYLE, _header_css()):
        assert "stToolbarActions" not in css
        assert "stAppDeployButton" not in css
    screen, _ = _split_shell_style()
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", screen)
    assert [(selector.strip(), rule.strip()) for selector, rule in rules] == [
        ('[data-testid="stMainMenu"]', "display: none !important;")
    ]
    # 머리 띠는 부트스트랩 뒤에야 나가므로 거기에 두 벌 두지 않는다.
    assert "stMainMenu" not in _header_css()


def test_print_always_leaves_out_the_sidebar_header_and_overlay() -> None:
    """화면에 펼쳐 둔 사이드바도 인쇄에서는 늘 뺀다(2026-10-05 사용자 요청). 머리 띠(툴바 단추
    포함)와 입장 화면·Summary 덮개도 뺀다. Streamlit 은 펼친 사이드바를 `display: initial` 로
    찍으므로 `!important` 여야 이긴다."""
    _, block = _split_shell_style()
    hidden = re.search(r"([^{}]+)\{\s*display: none !important;\s*\}", block)
    assert hidden is not None
    selectors = {selector.strip() for selector in hidden.group(1).split(",")}
    assert selectors == {
        '[data-testid="stSidebar"]',
        '[data-testid="stHeader"]',
        "#capa-intro-host",
    }
    # 본문은 종이 폭을 다 쓴다.
    assert re.search(
        r'\[data-testid="stMainBlockContainer"\] \{\s*max-width: none !important;\s*\}', block
    )


def test_print_keeps_screen_colours_and_leaves_orientation_to_the_browser() -> None:
    """상태색·차트색·표 바탕이 남게 화면 색 그대로 찍는다. 용지 방향은 인쇄 창에 맡긴다 —
    `@page` 에는 여백만 있고 `size` 가 없다."""
    _, block = _split_shell_style()
    assert "print-color-adjust: exact;" in block
    assert "-webkit-print-color-adjust: exact;" in block
    page = re.search(r"@page \{([^{}]*)\}", block)
    assert page is not None
    assert "margin:" in page.group(1)
    assert "size" not in page.group(1)
    # 화면에는 아무것도 바꾸지 않는다 — 인쇄 규칙은 이 덩어리 하나에만 있고 머리 띠 CSS 에는 없다.
    assert SHELL_STYLE.count("@media print") == 1
    assert "@media print" not in _header_css()


def test_print_does_not_split_charts_but_lets_long_tables_break() -> None:
    """Vega 차트·CCv2 칸·지표 카드는 쪽 사이에서 자르지 않는다. 긴 표에 걸면 통째로 다음 쪽으로
    밀려 빈 쪽이 생기므로 표에는 걸지 않는다. Plotly 도 표로 친다 — 월별 표가 Plotly 라, 걸면 행
    이름 열만 다음 쪽으로 밀려 쪼개지지 않는 월 스크롤 칸과 어긋나고 값이 잘려 나갔다(PDF 실측)."""
    _, block = _split_shell_style()
    avoid = re.search(r"([^{}]+)\{\s*break-inside: avoid;\s*\}", block)
    assert avoid is not None
    selectors = {selector.strip() for selector in avoid.group(1).split(",")}
    assert selectors == {
        '[data-testid="stVegaLiteChart"]',
        '[data-testid="stBidiComponentIsolated"]',
        '[data-testid="stBidiComponentRegular"]',
        '[data-testid="stMetric"]',
    }
    for table in ("stDataFrame", "stTable", "stPlotlyChart"):
        assert table not in block


def test_the_header_shows_the_auth_code_with_its_expiry() -> None:
    """⋮ 메뉴의 About 이 없어져 인증 유효기간을 보여 줄 곳은 머리 띠 둘째 줄뿐이다."""
    assert f"인증번호 {APP_AUTH_CODE}(유효기간 {APP_AUTH_EXPIRY})" in _header_css()
