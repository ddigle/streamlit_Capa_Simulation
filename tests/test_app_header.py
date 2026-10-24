# Purpose: 상단 띠의 시나리오 두 줄·진행 막대 자리·껍데기 스타일과 사이드바 앱 정보 규칙을 고정한다.

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.string_util import clean_text

from capa_simulation.components.app_credits import credit_lines
from capa_simulation.components.app_header import (
    PAGE_TABS_SELECTOR,
    PAGE_TITLE_SELECTOR,
    SHELL_STYLE,
    STATUS_SLOT_SELECTOR,
    _header_css,
    _status_slot_css,
    css_string,
    header_lines,
    source_type_label,
)
from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY
from capa_simulation.components.page_header import PAGE_TITLE_KEY, STATUS_SLOT_KEY
from capa_simulation.design import theme
from capa_simulation.page_tabs_state import PAGE_TABS_COMPONENT_KEY
from capa_simulation.scenario_activation import ActiveScenarioLabel
from capa_simulation.settings import (
    APP_CONTACT_EMAIL,
    APP_LABEL,
    APP_NAME,
    APP_OWNER_TEAM,
    APP_SUBTITLE,
    APP_VERSION,
)

LABEL = ActiveScenarioLabel(
    scenario_id="scenario-1",
    revision_id="revision-4",
    scenario_name="DEMO 시나리오",
    simulation_code="DEMO-CODE-70",
    source_type="BIGDATAQUERY",
    registered_at=datetime(2026, 9, 28, 10, 30),
    revision_no=4,
    revision_name="월간 보정",
    saved_at=datetime(2026, 10, 5, 9, 0),
    first_month=202607,
    last_month=202812,
)


def test_sidebar_collapse_button_is_always_visible_on_screen() -> None:
    """Streamlit 은 마우스를 올렸을 때만 버튼을 띄운다 — 화면 매체에서는 늘 보이게 덮는다."""
    css = _header_css()
    screen = re.search(r"@media screen \{(.*?)\n\}", css, re.S)
    assert screen is not None
    block = screen.group(1)
    assert '[data-testid="stSidebarCollapseButton"]' in block
    assert "visibility: visible !important;" in block


NARROW_MEDIA = "@media (max-width: 1399.98px)"


def test_the_header_text_leaves_room_for_the_whole_toolbar() -> None:
    """툴바가 Summary 를 품고 있던 때 1100px 창에서 355px 를 썼다(⋮ 를 감추고 Print 를 더한
    뒤 실측). 16rem(224px)만 비우면 머리 글자가 툴바 밑으로 들어갔다(2026-10-05 E2E). Summary 를
    사이드바 라벨로 옮겨 툴바가 좁아졌어도 그 폭은 지킨다."""
    wide = _header_css().split(NARROW_MEDIA)[0]
    widths = re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", wide)
    root_px = 14
    assert widths and float(widths[0]) * root_px >= 355 + 21 + 12
    # 사이드바를 접으면 글자가 4rem 에서 시작한다. 민 만큼(2.5rem) 최대 폭도 줄어야 한다.
    assert float(widths[-1]) * root_px >= 355 + 4 * root_px + 12


def test_narrow_windows_reserve_only_what_todays_toolbar_uses() -> None:
    """1400px 보다 좁은 창은 지금 툴바 실측으로 비움 폭을 잡는다(2026-10-07).

    28rem 그대로면 1100px 창(사이드바 300px)에서 글자 폭이 408px 뿐이라 긴 이름이 잘렸다. 그 창의
    실측: 툴바 단추 묶음(Guide·Print·테마)이 197px(테마 글자가 `Light` 면 2px 더). 여기에 글자
    시작(펼침 21px · 접힘 4rem), 띠 안쪽 여백·선 11px(최대 폭은 글자 칸에만 걸린다)과 틈 12px 가
    들어가야 글자가 툴바 밑으로 가지 않는다. Deploy 는 껍데기 스타일이 늘 감추므로(2026-10-07
    사용자 결정) 그 몫을 따로 비우지 않는다.
    """
    css = _header_css()
    assert NARROW_MEDIA in css
    # 그 미디어 덩어리만 본다 — 뒤에 붙는 진행 막대 자리 규칙에도 최대 폭이 있다.
    narrow = css.split(NARROW_MEDIA)[1].split("\n}\n")[0]
    expanded, collapsed = (
        float(value) * 14 for value in re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", narrow)
    )
    light, frame, gap = 2, 11, 12
    assert 197 + light + 21 + frame + gap <= expanded < 28 * 14
    assert 197 + light + 4 * 14 + frame + gap <= collapsed < 30.5 * 14
    # 감춘 Deploy 는 DOM 에 남아 있어 `:has()` 로 가르면 늘 「있음」 쪽이 걸린다 — 가르지 않는다.
    assert "stAppDeployButton" not in css


def _rule(css: str, selector: str) -> str:
    """`selector {` 로 시작하는 첫 규칙의 본문."""
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def _rem(block: str, prop: str) -> float:
    match = re.search(rf"{prop}: ([\d.]+)rem;", block)
    assert match is not None, prop
    return float(match.group(1))


def test_the_progress_slot_is_pinned_in_the_header_band_out_of_the_flow() -> None:
    """HOME `Capa LOB Summary` 의 로딩 막대는 머리 띠의 툴바 단추 바로 왼쪽에 앉는다(2026-10-08
    사용자 결정). 띠는 가상요소뿐이라 본문의 키 컨테이너를 고정 배치로 띠 위에 얹는다.

    고정하는 것은 `stLayoutWrapper`(본문 세로 블록의 flex 항목)다 — 안쪽 블록만 고정하면 감싼 칸이
    흐름에 남아 요소 간격 한 칸을 먹고, 막대가 뜨고 질 때 아래가 움직이지는 않아도 모든 회차에
    본문이 그만큼 내려간다. 층은 헤더(999990) 위·모바일 사이드바(999995) 아래이고, 빈 칸이 띠의
    클릭을 가로채지 않게 마우스를 받지 않는다.
    """
    assert STATUS_SLOT_SELECTOR == (
        f'[data-testid="stLayoutWrapper"]:has(> .st-key-{STATUS_SLOT_KEY})'
    )
    css = _status_slot_css()
    slot = _rule(css, STATUS_SLOT_SELECTOR)
    assert "position: fixed;" in slot
    assert "top: 0;" in slot
    assert "height: 3.75rem;" in slot  # 띠 높이(`_HEADER_TEMPLATE` 의 3.75rem)와 같다.
    assert "pointer-events: none;" in slot
    z_index = re.search(r"z-index: (\d+);", slot)
    assert z_index is not None and 999990 < int(z_index.group(1)) < 999995
    # 툴바 단추 묶음 실측 197px(`Light` 면 199px)과 틈 10px 이상. 가이드가 없는 화면은 Guide
    # (58.7px + 여백 6px)만큼 오른쪽으로 붙는다.
    right, width = _rem(slot, "right"), _rem(slot, "width")
    assert 197 + 2 + 10 <= right * 14 < 197 + 2 + 20
    no_guide = _rule(
        css,
        f'[data-testid="stAppViewContainer"]:not(:has(.st-key-{GUIDE_TRIGGER_KEY})) '
        + STATUS_SLOT_SELECTOR,
    )
    assert 197 - 65 + 2 + 10 <= _rem(no_guide, "right") * 14 < right * 14
    # 가장 긴 단계 글자(0.72rem 에서 194px)가 다 들어간다.
    assert width * 14 >= 194
    # 머리 띠 규칙 뒤에 붙는다 — 막대가 떠 있는 동안의 최대 폭이 같은 구체도의 규칙을 이긴다.
    header = _header_css()
    assert header.endswith(css)
    assert header.index(NARROW_MEDIA) < header.index(css)


def test_the_scenario_lines_yield_to_the_bar_only_while_it_is_visible() -> None:
    """막대가 떠 있는 동안만 시나리오 두 줄이 막대 몫을 비켜 말줄임으로 줄어든다 — 덮지 않는다.
    막대가 사라지면(`LoadingProgress.close` → 빈 자리) 두 줄은 원래 폭으로 돌아온다. 900px 보다
    좁은 창은 단계 이름을 화면에서 빼고 막대와 퍼센트만 둔다(768px 창에서 글자 칸 264px → 383px).
    """
    css = _status_slot_css()
    slot = _rule(css, STATUS_SLOT_SELECTOR)
    right, width = _rem(slot, "right"), _rem(slot, "width")
    loading = (
        '[data-testid="stAppViewContainer"]'
        f':has(.st-key-{STATUS_SLOT_KEY} [data-testid="stProgress"])'
    )
    collapsed = ':has([data-testid="stSidebar"][aria-expanded="false"])'
    wide, narrow = css.split("@media (max-width: 899.98px)")
    widths = [float(value) for value in re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", wide)]
    assert len(widths) == 2
    # 글자 칸 왼쪽 끝(펼침 1.5rem + 여백 0.55rem + 선 3px, 접힘은 4rem 부터) + 틈 12px + 막대 칸.
    frame, gap = 0.55 + 3 / 14, 12 / 14
    assert widths[0] >= 1.5 + frame + gap + right + width
    assert widths[1] >= 4 + frame + gap + right + width
    # 1400px 이상의 평소 비움(28rem)보다 넓다 — 창 폭과 상관없이 이 값이 걸린다.
    assert min(widths) > 28
    assert loading + '\n  [data-testid="stHeader"]::before' in wide
    assert loading + collapsed + '\n  [data-testid="stHeader"]::after' in wide
    # 좁은 창: 단계 이름은 화면에서만 빼고(입장 화면이 `innerText` 로 읽는다) 퍼센트를
    # 가상요소로 적는다.
    compact = _rem(_rule(narrow, "  " + STATUS_SLOT_SELECTOR), "width")
    assert compact < width
    assert "clip-path: inset(50%);" in narrow
    assert "display: none" not in narrow
    assert 'content: attr(aria-valuenow) "%";' in narrow
    narrow_widths = [
        float(value) for value in re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", narrow)
    ]
    assert narrow_widths[0] >= 1.5 + frame + gap + right + compact
    assert narrow_widths[1] >= 4 + frame + gap + right + compact
    # 색은 이 실행의 토큰이다(센티넬이 남지 않는다).
    assert "__" not in css.replace(f"st-key-{STATUS_SLOT_KEY}", "").replace(
        f"st-key-{GUIDE_TRIGGER_KEY}", ""
    )


def test_streamlits_running_widget_steps_aside_only_while_the_bar_runs() -> None:
    """오래 도는 실행에서 Streamlit 의 실행 표시(달리는 사람·Stop)는 툴바 단추 바로 왼쪽 81px 에
    서서 막대와 같은 자리를 쓴다. 막대가 떠 있고 그 표시가 실행 중 모양일 때만 감춘다 — 연결 끊김
    같은 다른 상태는 그대로 보인다."""
    css = _status_slot_css()
    rule = re.search(
        r'\[data-testid="stAppViewContainer"\]:has\(\.st-key-'
        + STATUS_SLOT_KEY
        + r' \[data-testid="stProgress"\]\)\s+'
        r'\[data-testid="stStatusWidget"\]:has\(\[data-testid="stStatusWidgetRunningIcon"\]\) \{'
        r"\s*visibility: hidden;\s*\}",
        css,
    )
    assert rule is not None
    assert css.count("stStatusWidget") == 2


def test_inline_code_in_body_text_is_close_to_the_body_size() -> None:
    """인라인 코드의 한글이 0.75em 대체 글꼴로 9~10px 까지 작아졌다(2026-10-05 E2E)."""
    css = _header_css()
    block = css[css.index('[data-testid="stMarkdownContainer"] :not(pre) > code') :]
    block = block[: block.index("}")]
    assert "font-size: 0.9em;" in block
    # 캡션(`st.caption`)은 마크다운 칸이 아니라 따로 된 칸이다 — 둘 다 걸어야 한다.
    assert '[data-testid="stCaptionContainer"] :not(pre) > code' in block


def _media_block(css: str, media: str) -> str:
    # 안쪽 중괄호 한 겹(`@page {}`·규칙들)까지만 품는 덩어리다.
    blocks = re.findall(rf"@media {media} \{{(?:[^{{}}]*\{{[^{{}}]*\}})*[^{{}}]*\}}", css)
    assert len(blocks) == 1, blocks
    return str(blocks[0])


def _split_shell_style() -> tuple[str, str]:
    """껍데기 스타일을 `@media print` 덩어리와 그 밖(늘 걸리는 규칙)으로 나눈다. 화면 덩어리
    (`@media screen`)는 어느 쪽에도 넣지 않는다 — `_screen_block` 이 따로 본다."""
    body = re.fullmatch(r"<style>(.*)</style>", SHELL_STYLE, re.S)
    assert body is not None
    css = body.group(1)
    printed = _media_block(css, "print")
    return css.replace(printed, "").replace(_media_block(css, "screen"), ""), printed


def _screen_block() -> str:
    body = re.fullmatch(r"<style>(.*)</style>", SHELL_STYLE, re.S)
    assert body is not None
    return _media_block(body.group(1), "screen")


def test_the_streamlit_main_menu_and_deploy_are_hidden_and_nothing_else() -> None:
    """⋮ 메뉴는 통째로 감춘다(2026-10-05 사용자 결정 — 인쇄·테마는 툴바 단추가 맡는다). 최소 모드는
    테마 항목을 남겨 메뉴가 사라지지 않는다. Deploy 단추도 감춘다(2026-10-07 사용자 결정 — 개발
    모드에서만 서는 Community Cloud 배포 창이라 이 앱에 쓸 일이 없다). 화면에 걸리는 규칙은 이 둘만
    고른다 — 우리 단추가 앉는 툴바 슬롯은 그대로여야 한다. 규칙은 머리 띠 CSS 가 아니라 부트스트랩
    앞에서 따로 나가는 껍데기 스타일에 있다(차례는 `test_app_navigation` 이 지킨다)."""
    for css in (SHELL_STYLE, _header_css()):
        assert "stToolbarActions" not in css
    screen, _ = _split_shell_style()
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", screen)
    assert [
        ({selector.strip() for selector in selectors.split(",")}, rule.strip())
        for selectors, rule in rules
    ] == [
        (
            {'[data-testid="stMainMenu"]', '[data-testid="stAppDeployButton"]'},
            "display: none !important;",
        ),
        ({HEADING_ANCHOR_SELECTOR}, "display: none !important;"),
    ]
    # 머리 띠는 부트스트랩 뒤에야 나가므로 거기에 두 벌 두지 않는다.
    assert "stMainMenu" not in _header_css()
    assert "stAppDeployButton" not in _header_css()


# Streamlit 1.63 이 제목(`st.title`·`st.subheader`·마크다운 `#`)마다 붙이는 칸과 그 안의
# `#제목` 링크.
HEADING_ANCHOR_SELECTOR = '[data-testid="stHeaderActionElements"] > a[href^="#"]'


def test_heading_anchor_links_are_hidden_but_help_tooltips_stay() -> None:
    """제목 옆 링크 아이콘은 늘 뺀다(2026-10-07 사용자 결정 — 제목 주소를 쓰지 않는다).

    한 규칙이 페이지 제목·`st.subheader`·마크다운 제목을 다 덮는다 — 셋 다 같은 칸에 같은 링크를
    둔다. 링크 하나만 고른다: 같은 칸의 `help=` 풍선까지 빼면 제목에 단 도움말이 사라진다.
    `opacity` 로 숨기면 Tab 으로 포커스가 닿아 다시 뜨므로 `display: none` 이다. 화면 규칙이라
    인쇄 덩어리 밖, 부트스트랩 앞 껍데기 스타일에 있다.
    """
    screen, printed = _split_shell_style()
    assert re.search(
        re.escape(HEADING_ANCHOR_SELECTOR) + r" \{\s*display: none !important;\s*\}", screen
    )
    assert "stHeaderActionElements" not in printed
    # 칸 전체(`stHeaderActionElements` 단독)를 고르는 규칙은 없다.
    assert not re.search(r'\[data-testid="stHeaderActionElements"\]\s*[,{]', SHELL_STYLE)
    assert "stHeaderActionElements" not in _header_css()


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
        STATUS_SLOT_SELECTOR,
        PAGE_TABS_SELECTOR,
        "#capa-intro-host",
    }
    # 본문은 종이 폭을 다 쓴다.
    assert re.search(
        r'\[data-testid="stMainBlockContainer"\] \{\s*max-width: none !important;\s*\}', block
    )


def test_the_screen_block_hides_only_the_page_title_and_pins_the_tab_strip() -> None:
    """화면 덩어리는 둘뿐이다(2026-10-24 사용자 결정 — 페이지 탭). 탭 줄은 머리 띠(3.75rem) 바로
    밑에 붙고 z-index 는 펼침 목록·팝업보다 낮다. 큰 제목은 `display: none` 이 아니라 sr-only 라
    읽기 도구에 남고, 인쇄에는 보인다(규칙이 `@media screen` 안이다)."""
    block = _screen_block()
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", block.split("{", 1)[1])
    assert {selector.strip() for selector, _ in rules} == {PAGE_TABS_SELECTOR, PAGE_TITLE_SELECTOR}
    by_selector = {selector.strip(): body for selector, body in rules}
    strip = by_selector[PAGE_TABS_SELECTOR]
    assert "position: sticky;" in strip and "top: 3.75rem;" in strip
    z_index = re.search(r"z-index: (\d+);", strip)
    assert z_index is not None and int(z_index.group(1)) < 1000
    title = by_selector[PAGE_TITLE_SELECTOR]
    assert "display" not in title
    assert "clip-path: inset(50%);" in title and "position: absolute !important;" in title
    assert PAGE_TITLE_SELECTOR.endswith(f".st-key-{PAGE_TITLE_KEY})")
    assert PAGE_TABS_SELECTOR == f".st-key-{PAGE_TABS_COMPONENT_KEY}"


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


def test_the_app_credits_are_two_lines_without_the_clearance_sentence() -> None:
    """⋮ 메뉴의 About 이 없고 머리 띠는 시나리오를 싣는다 — 앱 정보는 사이드바 맨 아래 카드뿐이다.

    두 줄이다 — 앱·버전·빌드, 개발 팀·문의처. 보안 등급·인증번호(유효기간)·취급 주의 문장은 싣지
    않고, 그것만 쓰는 설정 상수도 두지 않는다(2026-10-07 사용자 결정).
    """
    import capa_simulation.settings as settings

    assert credit_lines(stamp="202610081234") == (
        f"{APP_NAME} v{APP_VERSION} · 배포 202610081234",
        f"개발 {APP_OWNER_TEAM} · {APP_CONTACT_EMAIL}",
    )
    text = "\n".join(credit_lines())
    for removed in ("인증번호", "유효기간", "반출", "CONFIDENTIAL"):
        assert removed not in text
    for name in ("APP_SECURITY_LEVEL", "APP_AUTH_CODE", "APP_AUTH_EXPIRY", "APP_HANDLING_NOTE"):
        assert not hasattr(settings, name), name
    # 머리 띠에는 싣지 않는다.
    css = _header_css(*header_lines(LABEL, official=None, unsaved=False))
    assert APP_CONTACT_EMAIL not in css and "배포 " not in css
    assert not hasattr(settings, "APP_BUILD_DATE")


def test_the_credits_show_the_applied_deploy_stamp_or_say_outside(tmp_path: Path) -> None:
    """첫 줄 끝은 사내 적용 기록의 배포 번호, 기록이 없으면 「사외 개발」 이다(2026-10-08 사용자
    결정 — 손으로 적던 빌드일은 배포마다 고치지 않아 2026-09-08 로 남아 있었다). 깨진 기록도
    「사외 개발」. 기록은 프로세스에서 한 번만 읽으므로 경우마다 다른 경로를 쓴다."""
    from capa_simulation.components.app_credits import OUTSIDE_BUILD_LABEL, deployed_stamp

    assert deployed_stamp(tmp_path / "missing" / "applied.json") is None
    state = tmp_path / ".deploy" / "applied.json"
    state.parent.mkdir()
    state.write_text('{"stamp": "202610081234", "commit": "abc"}', encoding="utf-8")
    assert deployed_stamp(state) == "202610081234"
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert deployed_stamp(broken) is None
    assert credit_lines(stamp="")[0].endswith(f" · {OUTSIDE_BUILD_LABEL}")


def test_the_header_names_the_official_version_with_its_source_registration() -> None:
    """공식버전이면 위 줄 끝이 `공식 vN` 이고, 아래 줄은 원천과 등록일이다(2026-10-06 사용자
    결정)."""
    top, bottom = header_lines(LABEL, official=("revision-4", 4), unsaved=False)
    assert top == "DEMO 시나리오 · r4 월간 보정 · 공식 v4"
    assert bottom == "DEMO-CODE-70 · 적용 26.07–28.12 · BigDataQuery 26.09.28 등록"


def test_a_saved_revision_shows_its_save_date_instead_of_the_registration() -> None:
    """공식버전이 아닌 저장 리비전은 등록일 대신 리비전 저장일이다. 최신 공식버전이 다른 리비전이면
    공식이 아니다 — 사이드바 시나리오 줄의 배지와 같은 판정이다."""
    for official in (None, ("revision-other", 5)):
        top, bottom = header_lines(LABEL, official=official, unsaved=False)
        assert top == "DEMO 시나리오 · r4 월간 보정 · 저장된 리비전"
        assert bottom == "DEMO-CODE-70 · 적용 26.07–28.12 · 26.10.05 저장"


def test_unsaved_edits_win_the_status_slot() -> None:
    """적용했지만 저장하지 않은 편집이 있으면 상태는 `미저장 변경` 이다(공식버전 위에서도)."""
    top, bottom = header_lines(LABEL, official=("revision-4", 4), unsaved=True)
    assert top.endswith(" · 미저장 변경")
    assert "공식" not in top
    # 아래 줄은 올라와 있는 리비전의 출처를 그대로 말한다.
    assert bottom.endswith("BigDataQuery 26.09.28 등록")


def test_the_header_leaves_out_the_period_it_does_not_know_and_the_view_range() -> None:
    """계획에 월이 없으면 기간을 빼고 적는다. 조회기간은 어느 경우에도 싣지 않는다."""
    _, bottom = header_lines(
        replace(LABEL, first_month=None, last_month=None), official=None, unsaved=False
    )
    assert bottom == "DEMO-CODE-70 · 26.10.05 저장"
    assert "조회" not in bottom


def test_source_types_read_as_short_names() -> None:
    assert source_type_label("BIGDATAQUERY") == "BigDataQuery"
    assert source_type_label("BUILTIN_SYNTHETIC_SEED") == "내장 시드"
    assert source_type_label("CSV_CORE_DATA_INITIAL_BOOTSTRAP") == "CSV"
    assert source_type_label("SOMETHING_NEW") == "SOMETHING_NEW"


def test_without_an_active_scenario_the_header_falls_back_to_the_app_name() -> None:
    """활성 시나리오가 없으면 앱 이름 두 줄 — 위 줄 메인 라벨, 아래 줄 부제 — 로 물러난다. 한 줄로
    이으면 휴대폰 폭(글자 칸 110px)에서 부제가 말줄임에 통째로 먹힌다. 아래 줄이 비면 위 줄이 띠
    가운데에 선다."""
    top, bottom = header_lines(None, official=("revision-4", 4), unsaved=False)
    assert (top, bottom) == (APP_LABEL, APP_SUBTITLE)
    assert f"{top} {bottom}" == APP_NAME
    css = _header_css(top, bottom)
    before = css[css.index('[data-testid="stHeader"]::before {') :]
    before = before[: before.index("}")]
    assert f'content: "{APP_LABEL}";' in before
    assert "top: calc(50% - 1.1rem);" in before
    assert f'[data-testid="stHeader"]::after {{\n  content: "{APP_SUBTITLE}";' in css
    one_line = _header_css("위", "")
    assert "top: calc(50% - 0.55rem);" in one_line


def test_user_text_is_escaped_inside_the_css_string() -> None:
    """시나리오명은 사용자 글이다. 따옴표·역슬래시가 CSS 문자열을 끊거나 `</style>` 이 스타일 요소를
    끝내면 띠 전체가 깨진다. 줄바꿈은 한 줄 띠라 빈칸으로 바꾼다."""
    assert css_string('a"b') == 'a\\"b'
    assert css_string("a\\b") == "a\\\\b"
    assert css_string("a\nb\tc") == "a b c"
    assert css_string("</style>") == "\\3c /style\\3e "
    assert css_string("한글 · r4") == "한글 · r4"
    css = _header_css('x"</style><b>', "y")
    assert "</style>" not in css and "<b>" not in css


def test_the_styles_sent_every_run_carry_no_css_comments() -> None:
    """머리 띠 CSS 와 껍데기 스타일은 회차마다 소켓으로 다시 간다. CSS 주석은 그때마다 함께 가는
    바이트일 뿐이라 싣지 않는다 — 규칙의 설명은 `app_header` 의 파이썬 주석에 둔다.

    주석은 템플릿에서 뺀다. 시나리오명을 넣은 뒤의 CSS 에 정규식을 걸어 걷으면 안 된다 —
    `css_string` 은 `/*`·`*/` 를 이스케이프하지 않는다. 그 글자는 CSS 문자열 안이라 브라우저에는
    주석이 아니지만, 정규식은 그것을 주석으로 읽고 사이의 규칙까지 지운다.
    """
    for css in (
        SHELL_STYLE,
        _header_css(),
        _header_css(*header_lines(LABEL, official=("revision-4", 4), unsaved=False)),
    ):
        assert "/*" not in css and "*/" not in css
    css = _header_css("이름 /* 위", "아래 */ 끝")
    assert 'content: "이름 /* 위";' in css
    assert 'content: "아래 */ 끝";' in css


def _min_cached_message_size() -> int:
    """`.streamlit/config.toml` 의 `[global] minCachedMessageSize` 를 읽는다.

    3.10 이라 `tomllib` 이 없다 — `test_typography` 가 `[server]` 를 읽듯 정규식으로 한 줄만 본다.
    """
    text = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(
        encoding="utf-8"
    )
    block = re.search(r"^\[global\]\n(.*?)(?=^\[)", text, flags=re.MULTILINE | re.DOTALL)
    assert block, "config.toml 에 [global] 블록이 없습니다."
    value = re.search(r"^minCachedMessageSize = (\d+)$", block.group(1), flags=re.MULTILINE)
    assert value, "config.toml [global] 에 minCachedMessageSize 가 없습니다."
    return int(value.group(1))


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_styles_sent_every_run_stay_above_the_browser_cache_threshold(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """회차마다 다시 가는 머리 띠·HOME 제목 줄·공지 상자 스타일은 캐시 문턱 이상이어야 한다.

    Streamlit 은 메타데이터를 뺀 직렬화가 `global.minCachedMessageSize` 이상인 요소만 브라우저
    캐시에 올리고, 같은 내용이 다시 오면 해시 참조로 보낸다. 문턱 아래면 내용이 그대로여도 회차마다
    통째로 간다. 머리 띠(수 KB)와 HOME 두 블록(1KB 남짓)은 기본 문턱(10,000B)보다 작아 문턱을
    `config.toml` 에서 낮춰 두었다 — 세 블록이 그 아래로 내려가지 않는지 여기서 본다. 본문의
    UTF-8 길이는 직렬화 크기의 하한이라 이 비교를 통과하면 실제 메시지도 문턱 이상이다. 실패하면
    문턱을 더 낮출지, 그 블록이 회차마다 통째로 가도 되는지 따져 본다.
    """
    from capa_simulation.components.home_rendering import (
        dashboard_title_row_style,
        summary_notice_style,
    )

    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    threshold = _min_cached_message_size()
    blocks = {
        # 두 줄을 비운 머리 띠 — 실제 머리 띠는 시나리오 이름만큼 이보다 길다.
        "머리 띠": f"<style>{_header_css('', '')}</style>",
        "HOME 제목 줄": dashboard_title_row_style(),
        "HOME 공지 상자": summary_notice_style(),
    }
    for name, body in blocks.items():
        # `st.html` 은 본문을 `clean_text`(들여쓰기 걷기·앞뒤 공백 자르기)로 다듬어 싣는다.
        size = len(clean_text(body).encode("utf-8"))
        assert size >= threshold, f"{name} {size}B < minCachedMessageSize {threshold}B"


def test_scenario_text_cannot_be_rewritten_by_the_template_sentinels() -> None:
    """두 줄은 맨 마지막에 넣는다. 시나리오명에 센티넬 글자가 들어 있어도 색으로 바뀌지 않는다."""
    css = _header_css("__TEXT__ __ACCENT__", "__BOTTOM_LINE__")
    assert 'content: "__TEXT__ __ACCENT__";' in css
    assert 'content: "__BOTTOM_LINE__";' in css


def test_the_sidebar_header_carries_no_pseudo_element_text() -> None:
    """사이드바 머리칸의 앱 이름·버전 글은 걷었다 — 그 자리는 앱 이름 라벨이다(iframe
    스크립트).
    머리칸을 띠 위에 고정하는 규칙은 남는다."""
    css = _header_css()
    assert '[data-testid="stSidebarHeader"]::before' not in css
    assert '[data-testid="stSidebarHeader"]::after' not in css
    block = css[css.index('[data-testid="stSidebarHeader"] {') :]
    block = block[: block.index("}")]
    assert "position: sticky;" in block and "z-index: 11;" in block
