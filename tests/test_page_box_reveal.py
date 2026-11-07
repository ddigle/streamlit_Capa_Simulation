# Purpose: 화면 조작 상자 보이기 스크립트의 판정 · 회차 끝 동작 · 듣개 계약을 고정한다.

"""화면 조작 상자 보이기(`components/page_box_reveal.py`).

AppTest 는 브라우저 스크롤도 부모 문서의 듣개도 돌리지 못한다. 굴림 양 판정
(`// <page-box-reveal>`)은 떼어 돌리고, 회차 끝 동작은 가짜 부모 문서 위에서 스크립트 전체를 돌린다.
실제 칸 자리는 사본 앱을 브라우저로 잰다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from js_runner import run_js_json

from capa_simulation.components.app_credits import APP_CREDITS_KEY
from capa_simulation.components.page_box_reveal import (
    HANDLER_NAME,
    INPUT_HANDLER_NAME,
    REVEAL_GAP_PX,
    SETTLE_LOOKS,
    page_box_reveal_script,
)
from capa_simulation.sidebar_status import PAGE_BOX_PREFIX

SCRIPT = page_box_reveal_script()
ROOT = Path(__file__).resolve().parents[1]

# 1283×911 창 · 「실행 관리」 펼침 · 두 줄 카드에서 잰 자리(합성 표본 샘플 관측).
BOX_TOP = 771.7
BOX_BOTTOM = 953.5
HEADER_BOTTOM = 52.5
CARD_TOP = 864.9
REVEALED = BOX_BOTTOM + REVEAL_GAP_PX - CARD_TOP


def _judge(*args: float) -> float:
    match = re.search(
        r"// <page-box-reveal>\n(?P<body>.*?)\n\s*// </page-box-reveal>", SCRIPT, re.S
    )
    assert match, "page_box_reveal 스크립트에 // <page-box-reveal> 구획이 없습니다"
    runner = f"process.stdout.write(JSON.stringify(revealScroll(...{json.dumps(args)})))"
    result = run_js_json(match.group("body") + "\n" + runner, what="화면 조작 상자 굴림 판정 시험")
    return float(result)


def test_a_box_cut_by_the_card_scrolls_only_as_far_as_its_bottom_clears_the_card() -> None:
    moved = _judge(BOX_TOP, BOX_BOTTOM, HEADER_BOTTOM, CARD_TOP, REVEAL_GAP_PX)
    assert moved == pytest.approx(BOX_BOTTOM + REVEAL_GAP_PX - CARD_TOP)


def test_a_box_that_already_shows_does_not_move_the_sidebar() -> None:
    assert _judge(470.0, 652.0, HEADER_BOTTOM, CARD_TOP, REVEAL_GAP_PX) == 0
    assert _judge(700.0, CARD_TOP, HEADER_BOTTOM, CARD_TOP, REVEAL_GAP_PX) == 0


def test_a_box_taller_than_the_window_keeps_its_top_under_the_header() -> None:
    moved = _judge(BOX_TOP, BOX_BOTTOM, HEADER_BOTTOM, 200.0, REVEAL_GAP_PX)
    assert BOX_TOP - moved == pytest.approx(HEADER_BOTTOM + REVEAL_GAP_PX)


def test_a_box_already_past_the_header_never_scrolls_back_up() -> None:
    assert _judge(10.0, 900.0, HEADER_BOTTOM, CARD_TOP, REVEAL_GAP_PX) == 0


# 가짜 부모 문서 — 칸 자리는 스크롤을 뺀 값이고, 프레임 · 타이머는 시험이 넘긴다.
_FAKE_PARENT = """
const page = {
  run: "notRunning", hasBox: true, rows: 6, top: %(top)s, bottom: %(bottom)s, connected: true,
  expanded: "true",
}
const frames = []
const timers = []
const observed = []
const listeners = {}
const removed = []
let observer = null
const box = () => ({
  get children() { return { length: page.rows } },
  get isConnected() { return page.connected },
  closest: (selector) => (selector.includes("stSidebarContent") ? side : sidebar),
  getBoundingClientRect: () => ({
    top: page.top - side.scrollTop, bottom: page.bottom - side.scrollTop,
  }),
})
const side = {
  scrollTop: 0,
  getBoundingClientRect: () => ({ top: 0, bottom: 911 }),
}
const sidebar = {
  getAttribute: () => page.expanded,
  matches: (selector) => selector.includes("stSidebar"),
}
const app = { getAttribute: () => page.run }
const otherButton = { matches: () => false }
const inside = { closest: () => side }
const outside = { closest: () => null }
const card = { getBoundingClientRect: () => ({ top: %(card)s }) }
const head = { getBoundingClientRect: () => ({ bottom: %(head)s }) }
const theBox = box()
const doc = {
  body: {},
  addEventListener(name, listener) { (listeners[name] = listeners[name] || []).push(listener) },
  removeEventListener(name, listener) {
    listeners[name] = (listeners[name] || []).filter((item) => item !== listener)
    removed.push([name, listener])
  },
  querySelector(selector) {
    if (selector.startsWith(".stApp")) return app
    if (selector.includes("st-key-" + %(prefix)s)) return page.hasBox ? theBox : null
    if (selector.includes(":has(")) return card
    if (selector.includes("stSidebarHeader")) return head
    return null
  },
}
class FakeObserver {
  constructor(callback) { this.callback = callback; observer = this }
  observe(target, options) { observed.push(options) }
  disconnect() { this.disconnected = true }
}
const old = new FakeObserver(() => {})
const oldInput = () => {}
const parentWindow = {
  document: doc,
  requestAnimationFrame: (fn) => frames.push(fn),
  MutationObserver: FakeObserver,
  %(handler)s: old,
  %(input_handler)s: oldInput,
}
globalThis.window = { parent: parentWindow, setTimeout: (fn) => timers.push(fn) }
const flushFrames = () => { while (frames.length) frames.shift()() }
const flushTimers = () => { while (timers.length) timers.shift()() }
const settleAll = () => { while (timers.length || frames.length) { flushTimers(); flushFrames() } }
const runEnds = () => {
  observer.callback([{ attributeName: "data-test-script-state", target: app }])
  flushFrames()
}
const groupOpens = () => { observer.callback([{ attributeName: "open", target: {} }]) }
const sidebarChanges = (expanded) => {
  page.expanded = expanded
  observer.callback([{ attributeName: "aria-expanded", target: sidebar }])
}
const press = (name, target) => { (listeners[name] || []).forEach((fn) => fn({ target })) }
"""


def _in_browser(steps: str) -> Any:
    fake = _FAKE_PARENT % {
        "top": BOX_TOP,
        "bottom": BOX_BOTTOM,
        "card": CARD_TOP,
        "head": HEADER_BOTTOM,
        "prefix": json.dumps(PAGE_BOX_PREFIX),
        "handler": HANDLER_NAME,
        "input_handler": INPUT_HANDLER_NAME,
    }
    return run_js_json(
        fake
        + SCRIPT
        + "\nconst out = {}\n"
        + steps
        + "\nprocess.stdout.write(JSON.stringify(out))",
        what="화면 조작 상자 회차 끝 동작 시험",
    )


def test_opening_the_page_reveals_the_box_once_the_run_has_finished() -> None:
    result = _in_browser(
        """
page.run = "running"
flushFrames()
out.while_running = side.scrollTop
page.run = "notRunning"
runEnds()
out.finished = side.scrollTop
out.old_disconnected = old.disconnected === true
out.options = observed[observed.length - 1]
"""
    )
    assert result["while_running"] == 0
    assert result["finished"] == pytest.approx(REVEALED)
    assert result["old_disconnected"] is True
    assert result["options"]["attributeFilter"] == [
        "data-test-script-state",
        "open",
        "aria-expanded",
    ]


def test_a_run_with_the_same_rows_keeps_where_the_person_scrolled() -> None:
    result = _in_browser(
        """
flushFrames()
flushTimers()
side.scrollTop = 0
runEnds()
flushTimers()
out.after_rerun = side.scrollTop
"""
    )
    assert result["after_rerun"] == 0


def test_more_rows_in_the_box_reveal_it_again() -> None:
    result = _in_browser(
        """
flushFrames()
const opened = side.scrollTop
page.rows = 7
page.bottom += 41
runEnds()
out.moved = side.scrollTop - opened
"""
    )
    assert result["moved"] == pytest.approx(41)


def test_coming_back_to_the_page_reveals_the_box_again() -> None:
    result = _in_browser(
        """
flushFrames()
side.scrollTop = 0
page.hasBox = false
runEnds()
out.away = side.scrollTop
page.hasBox = true
runEnds()
out.back = side.scrollTop
"""
    )
    assert result["away"] == 0
    assert result["back"] == pytest.approx(REVEALED)


def test_the_group_opening_after_the_run_is_caught_by_the_second_look() -> None:
    result = _in_browser(
        """
flushFrames()
const first = side.scrollTop
page.top += 30
page.bottom += 30
flushTimers()
out.moved = side.scrollTop - first
"""
    )
    assert result["moved"] == pytest.approx(30)


@pytest.mark.parametrize("cut_to", [0, 65])
def test_a_scroll_the_browser_cut_back_is_written_again(cut_to: int) -> None:
    result = _in_browser(
        f"""
flushFrames()
side.scrollTop = {cut_to}
flushTimers()
out.moved = side.scrollTop
"""
    )
    assert result["moved"] == pytest.approx(REVEALED)


def test_a_cut_after_the_first_look_again_is_caught_by_a_later_look() -> None:
    result = _in_browser(
        """
flushFrames()
timers.shift()()
side.scrollTop = 0
flushTimers()
out.moved = side.scrollTop
"""
    )
    assert result["moved"] == pytest.approx(REVEALED)


def test_the_looks_stop_after_the_set_count() -> None:
    result = _in_browser(
        """
flushFrames()
out.looks = 0
while (timers.length) { timers.shift()(); out.looks += 1 }
"""
    )
    assert result["looks"] == SETTLE_LOOKS


@pytest.mark.parametrize("name", ["wheel", "touchmove", "pointerdown", "keydown"])
def test_the_looks_leave_a_sidebar_the_person_touched(name: str) -> None:
    result = _in_browser(
        f"""
flushFrames()
side.scrollTop = 12
press("{name}", inside)
page.bottom += 30
flushTimers()
out.left = side.scrollTop
"""
    )
    assert result["left"] == 12


def test_a_person_touching_between_two_looks_stops_the_rest() -> None:
    result = _in_browser(
        """
flushFrames()
timers.shift()()
side.scrollTop = 12
press("wheel", inside)
flushTimers()
out.left = side.scrollTop
"""
    )
    assert result["left"] == 12


def test_input_outside_the_sidebar_does_not_stop_the_looks() -> None:
    result = _in_browser(
        """
flushFrames()
side.scrollTop = 0
press("pointerdown", outside)
press("wheel", { closest: undefined })
press("keydown", null)
flushTimers()
out.moved = side.scrollTop
"""
    )
    assert result["moved"] == pytest.approx(REVEALED)


def test_the_click_that_opened_the_page_does_not_stop_the_looks() -> None:
    result = _in_browser(
        """
press("pointerdown", inside)
flushFrames()
side.scrollTop = 0
flushTimers()
out.moved = side.scrollTop
"""
    )
    assert result["moved"] == pytest.approx(REVEALED)


def test_the_second_look_ignores_a_box_that_has_left_the_page() -> None:
    result = _in_browser(
        """
flushFrames()
const first = side.scrollTop
page.connected = false
page.bottom += 30
flushTimers()
out.moved = side.scrollTop - first
"""
    )
    assert result["moved"] == 0


def test_a_collapsed_sidebar_is_left_alone() -> None:
    result = _in_browser(
        """
page.expanded = "false"
flushFrames()
flushTimers()
out.left = side.scrollTop
"""
    )
    assert result["left"] == 0


def test_a_box_that_stood_in_a_collapsed_sidebar_is_revealed_when_it_opens() -> None:
    result = _in_browser(
        """
page.expanded = "false"
flushFrames()
flushTimers()
runEnds()
flushTimers()
out.collapsed = side.scrollTop
sidebarChanges("true")
flushFrames()
out.right_after = side.scrollTop
settleAll()
out.opened = side.scrollTop
"""
    )
    assert result["collapsed"] == 0
    assert result["right_after"] == 0
    assert result["opened"] == pytest.approx(REVEALED)


def test_a_sidebar_collapsed_during_the_looks_is_measured_when_it_opens() -> None:
    result = _in_browser(
        """
flushFrames()
page.expanded = "false"
flushTimers()
side.scrollTop = 0
sidebarChanges("true")
settleAll()
out.opened = side.scrollTop
"""
    )
    assert result["opened"] == pytest.approx(REVEALED)


def test_collapsing_and_opening_the_sidebar_keeps_where_the_person_scrolled() -> None:
    result = _in_browser(
        """
flushFrames()
flushTimers()
side.scrollTop = 25
sidebarChanges("false")
settleAll()
sidebarChanges("true")
settleAll()
out.left = side.scrollTop
"""
    )
    assert result["left"] == 25


def test_another_element_opening_does_not_wake_the_script() -> None:
    result = _in_browser(
        """
settleAll()
observer.callback([{ attributeName: "aria-expanded", target: otherButton }])
out.timers = timers.length
out.frames = frames.length
"""
    )
    assert result == {"timers": 0, "frames": 0}


def test_a_group_opening_reveals_the_box_when_the_run_marker_never_changed() -> None:
    result = _in_browser(
        """
page.hasBox = false
flushFrames()
page.hasBox = true
groupOpens()
flushFrames()
out.moved = side.scrollTop
"""
    )
    assert result["moved"] == pytest.approx(REVEALED)


def test_a_new_frame_replaces_the_old_input_listener() -> None:
    result = _in_browser(
        """
out.removed = removed.filter((item) => item[1] === oldInput).map((item) => item[0])
out.counts = Object.values(listeners).map((items) => items.length)
out.names = Object.keys(listeners)
"""
    )
    assert result["removed"] == result["names"]
    assert result["names"] == ["wheel", "touchmove", "pointerdown", "keydown"]
    assert result["counts"] == [1, 1, 1, 1]


def test_the_script_is_one_fixed_string_that_watches_only_three_attributes() -> None:
    assert page_box_reveal_script() == SCRIPT
    assert "%(" not in SCRIPT
    assert f'[class*="st-key-{PAGE_BOX_PREFIX}"]' in SCRIPT
    assert f":has(> .st-key-{APP_CREDITS_KEY})" in SCRIPT
    assert "childList" not in SCRIPT
    assert "scrollIntoView" not in SCRIPT


def test_the_app_loads_the_script_with_the_other_toolbar_scripts() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("render_theme_toggle(")
    assert "page_box_reveal_script()," in source[start : source.index("\n)\n", start)]
