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
