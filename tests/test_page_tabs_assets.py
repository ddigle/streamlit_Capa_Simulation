# Purpose: 탭 줄 자산의 트리거 이름·접근성 표지·탭 역할 금지·색 변수 계약을 글자로 검사한다.

"""AppTest 는 탭 줄 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속을 여기서 붙잡고, 동작은
브라우저로 본다."""

from __future__ import annotations

import re
from pathlib import Path

from capa_simulation.components import page_tabs

ASSETS = page_tabs._ASSETS
HTML = (ASSETS / "page_tabs.html").read_text(encoding="utf-8")
CSS = (ASSETS / "page_tabs.css").read_text(encoding="utf-8")
JS = (ASSETS / "page_tabs.js").read_text(encoding="utf-8")


def test_the_strip_sends_only_one_shot_triggers() -> None:
    """누름은 트리거 셋(`select`·`close`·`pin`)뿐이다 — 남는 상태 값은 앱 전체를 다시 돌린다."""
    assert "setStateValue" not in JS
    assert set(re.findall(r"S\.send\('([a-z]+)'", JS)) == {"select", "close", "pin"}
    source = Path(page_tabs.__file__).read_text(encoding="utf-8")
    for name in ("on_select_change", "on_close_change", "on_pin_change"):
        assert name in source


def test_the_strip_is_a_labelled_nav_of_buttons_without_the_tab_role() -> None:
    """패널이 없는 이동 목록이다. 탭 역할을 쓰면 배포 화면 확인의 `get_by_role("tab")` 이
    본문 탭보다 이 줄을 먼저 잡는다."""
    for text in (HTML, CSS, JS):
        assert not re.search(r"""role\s*[=:,]\s*['"]tab""", text)
        assert "'role'" not in text
    assert "<nav" in HTML and "aria-label" in HTML
    assert "aria-current" in JS and "'page'" in JS
    assert "aria-label" in JS and "aria-pressed" in JS


def test_the_active_tab_is_kept_in_view_without_scrolling_the_page() -> None:
    assert ".scrollIntoView(" not in JS
    assert "scrollLeft" in JS


def test_colours_come_from_streamlit_variables_and_the_data_palette() -> None:
    """등록 CSS 는 테마를 따라오지 않는다 — 색은 `--st-*` 와 data 의 팔레트(점 색)로만 쓴다."""
    used = set(re.findall(r"var\((--[a-z-]+)", CSS))
    assert used <= {
        "--st-background-color",
        "--st-text-color",
        "--st-primary-color",
        "--st-font",
        "--capa-tabs-pending",
    }, used
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", CSS)
    assert "palette" in JS and "--capa-tabs-pending" in JS


def test_the_data_carries_the_pending_colour_and_every_text_the_script_reads() -> None:
    from capa_simulation.page_tabs_state import INITIAL_STRIP

    data = page_tabs.tabs_data(
        INITIAL_STRIP,
        active=INITIAL_STRIP.paths[0],
        hrefs={},
        marks={},
        leave="",
        epoch=1,
        notice=None,
    )
    assert set(data["palette"]) == {"pending"}
    read = set(re.findall(r"text\.([a-z]+)", JS))
    assert read <= set(data["text"]), read - set(data["text"])


def _rule(selector: str) -> str:
    """`selector` 로 시작하는 CSS 규칙 하나의 몸통."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match is not None, selector
    return match.group(1)


def test_a_hidden_pin_takes_no_taps_and_touch_devices_pin_only_the_current_tab() -> None:
    """숨은 핀(opacity 0)이 누름을 받으면 터치로 탭 이름 오른쪽을 누를 때 이동 대신 고정이 된다
    (서피스). 숨은 동안은 `pointer-events: none`, 가리키거나 포커스가 들 때만 받는다. 가리킬 수 없는
    기기에서는 지금 탭이 아닌 탭의 핀을 아예 두지 않는다."""
    hidden = ".capa-tabs-item:not(.is-pinned):not(.is-active) .capa-tabs-pin"
    assert "opacity: 0" in _rule(hidden) and "pointer-events: none" in _rule(hidden)
    shown = ".capa-tabs-item:not(.is-pinned):not(.is-active):focus-within .capa-tabs-pin"
    assert "opacity: 1" in _rule(shown) and "pointer-events: auto" in _rule(shown)
    touch = re.search(r"@media \(hover: none\)\s*\{(.*?)\n\}", CSS, re.S)
    assert touch is not None
    assert hidden in touch.group(1) and "display: none" in touch.group(1)


def test_the_pin_keeps_one_name_and_tells_its_state_with_aria_pressed() -> None:
    """이름까지 「고정 풀기」로 바꾸면 읽기 도구가 상태를 두 번 말한다."""
    assert "text.unpin" not in JS and "unpin" not in page_tabs.TEXT
    assert "setAttr(P.pin, 'aria-label', fill(text.pin, { label }))" in JS
    assert "setAttr(P.pin, 'aria-pressed'" in JS


def test_the_strip_refuses_page_links_at_the_limit_before_streamlit_moves() -> None:
    """상한에서 열린 탭이 아닌 화면으로 가는 링크 누름은 옮기기 전에 막는다 — 서버가 옮긴 뒤
    되돌리면 두 화면이 브라우저 기록에 쌓여 뒤로가기가 갇힌다. 문서 capture 단계에서 Streamlit(React
    뿌리)보다 먼저 받고, 걸어 둔 처리기는 컴포넌트가 내려갈 때 걷는다. 기록은 쌓지 않는다."""
    assert 'a[data-testid="stPageLink-NavLink"]' in JS
    assert "document.addEventListener('click', S.onLink, true)" in JS
    assert "document.removeEventListener('click', S.onLink, true)" in JS
    assert "event.preventDefault()" in JS and "event.stopPropagation()" in JS
    assert "pushState(" not in JS and "replaceState(" not in JS
    # 같은 알림 글을 서버(되돌림 안전망·파이썬 도우미)와 JS 가 함께 쓴다.
    from capa_simulation.page_tabs_state import LIMIT_NOTICE, limit_notice

    assert page_tabs.TEXT["limit"] == LIMIT_NOTICE
    assert limit_notice("생산 계획") == LIMIT_NOTICE.format(max=10, label="생산 계획")
