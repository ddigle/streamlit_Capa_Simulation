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

# `<style>` 여는 태그와 닫는 태그만 허용한다. 그 밖의 `<...>` 는 살균기가 태그로 읽는다.
ALLOWED = {"<style>", "</style>"}
TAG_LIKE = re.compile(r"<[^\s<>][^<>]*>")


def _style_block(active_href: str = "") -> str:
    return build_sidebar_stylesheet(
        SIDEBAR_GROUPS,
        active_href,
        scenario_box_key="test_scenario",
        month_box_key="test_month",
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
