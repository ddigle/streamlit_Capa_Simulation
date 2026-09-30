# Purpose: 사이드바 스타일시트가 통째로 사라지는 실수를 막는다.

"""**`st.html` 은 태그처럼 생긴 글자를 만나면 블록을 조용히 버린다.**

`app.py` 는 빌더가 만든 사이드바 CSS 를 `st.html` 한 덩어리로 넘긴다. 그 안 어딘가에
`<details>` 같은 **태그 꼴 문자열**이 있으면 — CSS 주석 안이어도 — Streamlit 의 살균기가 그
지점에서 블록을 잘라 버린다. 오류도 경고도 없고, 화면은 멀쩡히 뜬 채 **사이드바 서식만 전부
사라진다.**

실제로 그렇게 됐다. 주석에 `<details>` 라고 적은 한 번으로 스타일시트 전체가 날아갔고,
그라데이션이 있는 상자와 없는 상자가 섞여 「서식이 뒤죽박죽」으로 보였다. 원인을 찾는 데
브라우저 실측이 여러 번 들었다.

예외가 나지 않는 종류의 고장이라 검사로만 잡힌다.
"""

from __future__ import annotations

import re

import pytest

from capa_simulation.components.sidebar_style import build_sidebar_stylesheet
from capa_simulation.design import theme, tokens
from capa_simulation.navigation import SIDEBAR_GROUPS
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

# `<style>` 여는 태그와 닫는 태그만 허용한다. 그 밖의 `<...>` 는 살균기가 태그로 읽는다.
ALLOWED = {"<style>", "</style>"}
TAG_LIKE = re.compile(r"<[^\s<>][^<>]*>")


def _style_block(active_href: str = "") -> str:
    return build_sidebar_stylesheet(
        SIDEBAR_GROUPS,
        active_href,
        scenario_box_key="test_scenario",
        month_box_key="test_month",
        month_applied_key="test_month_applied",
        bottleneck_box_key="test_bottleneck",
        admin_box_key="test_admin",
    ).strip()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_sidebar_stylesheet_has_no_tag_like_text(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    block = _style_block()
    offenders = sorted({tag for tag in TAG_LIKE.findall(block) if tag not in ALLOWED})

    assert not offenders, (
        "사이드바 CSS 안에 태그처럼 생긴 글자가 있습니다. `st.html` 이 그 지점에서 블록을 "
        "**조용히 잘라** 사이드바 서식이 통째로 사라집니다. 주석에서도 쓰지 마세요 — "
        "`<details>` 대신 「확장 패널」처럼 풀어 적습니다:\n  " + "\n  ".join(offenders)
    )


def test_the_style_block_is_actually_found() -> None:
    """위 검사가 빈 문자열을 보고 통과하지 않게 한다."""
    block = _style_block()

    assert block.startswith("<style>") and block.endswith("</style>")
    # 선택자를 실제로 들고 있는지. 한 줄짜리로 줄어들면 위 검사가 무의미해진다.
    assert "st-key-" in block
    assert len(block) > 2000, len(block)


def test_stylesheet_reads_the_active_page_and_theme_on_each_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """import 때 굳은 색·주소를 재사용하면 테마·페이지를 바꿔도 예전 강조가 남는다."""
    monkeypatch.setattr(theme, "current_mode", lambda: "light")
    home = _style_block()
    assert '[href=""]::before' in home
    assert f"background-color: {tokens.SURFACE};" in home

    monkeypatch.setattr(theme, "current_mode", lambda: "dark")
    dynamic = _style_block("dynamic_capa")
    assert '[href="dynamic_capa"]::before' in dynamic
    assert '[href=""]::before' not in dynamic
    assert f"background-color: {tokens.SURFACE};" in dynamic
    assert dynamic != home


def _rules_with(block: str, declaration: str) -> list[list[str]]:
    """`declaration` 을 몸에 가진 규칙마다 그 선택자 목록. 주석은 걷어 내고 읽는다."""
    without_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    rules: list[list[str]] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", without_comments):
        selectors, body = match.group(1), match.group(2)
        if declaration in body:
            rules.append([part.strip() for part in selectors.split(",") if part.strip()])
    return rules


@pytest.mark.parametrize("active_href", ["", "capa_chatbot"])
def test_box_markers_follow_the_declarations(active_href: str) -> None:
    """상자 오른쪽 끝 표식이 **선언에서 나온 상자 전부**에, 그리고 **그 상자에만** 걸린다.

    표식이 빠진 상자는 다시 「누르면 무슨 일이 일어나는지」를 말하지 못한다. 그룹을 더하거나
    조회 컨트롤을 늘릴 때 한쪽만 고치면 예외 없이 표식만 사라지므로 선언과 대조한다.
    `→` 규칙이 상자 key 밖으로 새면 HOME 링크의 `::after` 광택 띠를 덮거나(표식 규칙) 지운다
    (HOME 의 `href` 는 빈 문자열이라 「지금 보는 링크에서는 뺀다」 규칙이 HOME 에 걸린다).
    """
    block = _style_block(active_href)
    boxed = [f"{group.slug}_box" for group in SIDEBAR_GROUPS if group.subpages]
    solo = [f"{group.slug}_box" for group in SIDEBAR_GROUPS if not group.subpages]
    expanding = [*boxed, "test_scenario", "test_month", "test_bottleneck", "test_admin"]

    (expand_rule,) = _rules_with(block, 'content: "expand_more" / "";')
    # 화면 조건 카드는 페이지마다 이름이 달라 key 대신 접두어 선택자 하나로 걸린다.
    assert expand_rule == [
        *(f".st-key-{key} details > summary::after" for key in expanding),
        f'[class*="st-key-{CONDITION_CARD_PREFIX}"] details > summary::after',
    ]
    # 합자 이름만 적은 폴백 선언이 같은 규칙에 먼저 있다.
    assert _rules_with(block, 'content: "expand_more";') == [expand_rule]

    link = 'a[data-testid="stPageLink-NavLink"]'
    (arrow_rule,) = _rules_with(block, 'content: "arrow_forward" / "";')
    assert arrow_rule == [f".st-key-{key} {link}::after" for key in solo]

    off_rules = [
        rule for rule in _rules_with(block, "content: none;") if any("[href=" in s for s in rule)
    ]
    assert off_rules == [[f'.st-key-{key} {link}[href="{active_href}"]::after' for key in solo]]
    # HOME 광택 띠는 그대로 남는다.
    assert '.st-key-home_navigation a[data-testid="stPageLink-NavLink"]::after' in block


def test_condition_cards_wear_the_condition_box_face() -> None:
    """화면 조건 카드는 공통 조건 상자와 같은 청록 면·`ACCENT` 아이콘이다.

    카드 key 가 페이지마다 달라 서식이 접두어 하나에 걸린다. 그 선택자가 빠지면 카드만 목록
    상자처럼 보여 「이 화면의 조건」이라는 구역의 뜻이 흐려진다.
    """
    block = _style_block()
    card = f'[class*="st-key-{CONDITION_CARD_PREFIX}"]'

    (face_rule,) = _rules_with(block, f"background-color: {tokens.NAV_CONTROL_TINT};")
    assert f"{card} details" in face_rule
    (icon_rule,) = [
        rule
        for rule in _rules_with(block, f"color: {tokens.ACCENT};")
        if any("stExpanderIcon" in selector for selector in rule)
    ]
    assert f'{card} summary [data-testid="stExpanderIcon"]' in icon_rule


def test_the_support_box_sits_last_and_apart() -> None:
    """`Support` 상자는 **맨 아래**이고 **앞에 간격**을 둔다. 두 선언이 한 규칙에 있다.

    파이썬 차례로는 HOME 의 B/N 상자가 이 상자 뒤에 그려진다(`navigation.run()` 안). 그래서
    맨 아래를 지키는 것은 `order` 뿐이다. 간격은 계산 조건 구역을 닫는다 — 없으면 목록인
    `Support` 가 조건 구역의 네 번째 상자로 읽힌다. flex 항목이 상자와 확장 패널에서 다르므로
    두 선택자를 함께 건다.
    """
    block = _style_block()
    (rule,) = _rules_with(block, "order: 99;")
    assert rule == [
        '[data-testid="stLayoutWrapper"]:has(> .st-key-test_admin)',
        ".st-key-test_admin",
    ]
    # 간격은 **같은 규칙**에 있다 — 따로 두면 한쪽 선택자만 고치는 일이 생긴다.
    assert _rules_with(block, "margin-top: 0.9rem;") == [rule]


def test_the_toggle_sink_is_hidden_and_short_runs_do_not_dim_the_body() -> None:
    """사이드바 상자를 여닫을 때 도는 빈 프래그먼트의 칸은 숨기고, 짧은 실행은 본문을 흐리지 않는다.

    여닫기는 본문을 다시 돌리지 않지만 콜백이 프래그먼트로 바꾸기 전에 앱 실행이 잠깐 시작돼,
    Streamlit 이 본문을 40~120ms 즉시 흐렸다(2026-09-30 실측). 흐림에 지연을 둔다.
    """
    from capa_simulation.components.sidebar_style import STALE_DIM_DELAY
    from capa_simulation.sidebar_status import SIDEBAR_TOGGLE_SINK_KEY

    block = _style_block()
    (sink_rule,) = _rules_with(block, "display: none !important;")
    assert sink_rule == [
        f'[data-testid="stLayoutWrapper"]:has(> .st-key-{SIDEBAR_TOGGLE_SINK_KEY})',
        f".st-key-{SIDEBAR_TOGGLE_SINK_KEY}",
    ]
    assert _rules_with(block, f"transition: opacity 0s linear {STALE_DIM_DELAY} !important;") == [
        ['[data-stale="true"]']
    ]
