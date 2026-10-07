# Purpose: 상단 띠의 시나리오 두 줄·CSS·껍데기 스타일과 사이드바 앱 정보 두 줄의 규칙을 고정한다.

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from capa_simulation.components.app_credits import credit_lines
from capa_simulation.components.app_header import (
    SHELL_STYLE,
    _header_css,
    css_string,
    header_lines,
    source_type_label,
)
from capa_simulation.scenario_activation import ActiveScenarioLabel
from capa_simulation.settings import (
    APP_CONTACT_EMAIL,
    APP_NAME,
    APP_OWNER_TEAM,
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
    실측: 툴바 단추 묶음(Guide·테마·Print)이 197px(테마 글자가 `Light` 면 2px 더). 여기에 글자
    시작(펼침 21px · 접힘 4rem), 띠 안쪽 여백·선 11px(최대 폭은 글자 칸에만 걸린다)과 틈 12px 가
    들어가야 글자가 툴바 밑으로 가지 않는다. Deploy 는 껍데기 스타일이 늘 감추므로(2026-10-07
    사용자 결정) 그 몫을 따로 비우지 않는다.
    """
    css = _header_css()
    assert NARROW_MEDIA in css
    narrow = css.split(NARROW_MEDIA)[1]
    expanded, collapsed = (
        float(value) * 14 for value in re.findall(r"max-width: calc\(100% - ([\d.]+)rem\)", narrow)
    )
    light, frame, gap = 2, 11, 12
    assert 197 + light + 21 + frame + gap <= expanded < 28 * 14
    assert 197 + light + 4 * 14 + frame + gap <= collapsed < 30.5 * 14
    # 감춘 Deploy 는 DOM 에 남아 있어 `:has()` 로 가르면 늘 「있음」 쪽이 걸린다 — 가르지 않는다.
    assert "stAppDeployButton" not in css


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
    공식이 아니다 — 사이드바 시나리오 상자의 배지와 같은 판정이다."""
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
    """활성 시나리오가 없으면 앱 이름 한 줄로 물러나고, 그 한 줄은 띠 가운데에 선다."""
    top, bottom = header_lines(None, official=("revision-4", 4), unsaved=False)
    assert (top, bottom) == (APP_NAME, "")
    css = _header_css(top, bottom)
    before = css[css.index('[data-testid="stHeader"]::before {') :]
    before = before[: before.index("}")]
    assert f'content: "{APP_NAME}";' in before
    assert "top: calc(50% - 0.55rem);" in before
    two_lines = _header_css("위", "아래")
    assert "top: calc(50% - 1.1rem);" in two_lines


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


def test_scenario_text_cannot_be_rewritten_by_the_template_sentinels() -> None:
    """두 줄은 맨 마지막에 넣는다. 시나리오명에 센티넬 글자가 들어 있어도 색으로 바뀌지 않는다."""
    css = _header_css("__TEXT__ __ACCENT__", "__BOTTOM_LINE__")
    assert 'content: "__TEXT__ __ACCENT__";' in css
    assert 'content: "__BOTTOM_LINE__";' in css


def test_the_sidebar_header_carries_no_pseudo_element_text() -> None:
    """사이드바 머리칸의 앱 이름·버전 글은 걷었다 — 그 자리는 `S.PKG CAPA` 라벨이다(iframe
    스크립트).
    머리칸을 띠 위에 고정하는 규칙은 남는다."""
    css = _header_css()
    assert '[data-testid="stSidebarHeader"]::before' not in css
    assert '[data-testid="stSidebarHeader"]::after' not in css
    block = css[css.index('[data-testid="stSidebarHeader"] {') :]
    block = block[: block.index("}")]
    assert "position: sticky;" in block and "z-index: 11;" in block
