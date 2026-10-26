# Purpose: 탭 줄 자산의 트리거·접근성·색 계약을 글자로, 기록·누름 구획을 node 로 검사한다.

"""AppTest 는 탭 줄 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속을 여기서 붙잡고, DOM 을 모르는
순수 구획(`// <tabs-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI 에서는 실패한다.
나머지 동작은 브라우저로 본다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

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
    # 기록을 만지는 것은 탭 이동의 기록 한 칸 구획(`// <tabs-history>`)뿐이다.
    outside = re.sub(r"// <tabs-history>\n.*?\n// </tabs-history>", "", JS, flags=re.S)
    assert "pushState(" not in outside and "replaceState(" not in outside
    # 같은 알림 글을 서버(되돌림 안전망·파이썬 도우미)와 JS 가 함께 쓴다.
    from capa_simulation.page_tabs_state import LIMIT_NOTICE, limit_notice

    assert page_tabs.TEXT["limit"] == LIMIT_NOTICE
    assert limit_notice("생산 계획") == LIMIT_NOTICE.format(max=10, label="생산 계획")


# ---------------------------------------------------------------- JS 순수 구획(node)

_SECTIONS = ("tabs-history", "tabs-hold", "tabs-queue", "tabs-press", "tabs-links")


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"page_tabs.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(runner: str, *, prelude: str | None = None) -> Any:
    """`prelude`(기본은 순수 구획들) 뒤에 `runner` 를 붙여 node 로 돌리고 찍은 JSON 을 읽는다."""
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 탭 줄 JS 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", (_sections() if prelude is None else prelude) + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


_HISTORY_RUNNER = """
// 브라우저 기록 대역 — 칸 목록과 지금 칸. 프런트처럼 `history.pushState` 를 부를 때마다 찾는다.
const entries = ['http://app.test/calculation_result']
let index = 0
let now = 0
const history = {
  state: {},
  pushState(state, title, url) {
    entries.splice(index + 1)
    entries.push(new URL(url, entries[index]).href)
    index += 1
  },
  replaceState(state, title, url) {
    entries[index] = new URL(url, entries[index]).href
  },
}
guardHistory(history, () => entries[index], () => now, 1000)
const out = {}
const here = () => entries[index].replace('http://app.test', '')
const back = () => { index -= 1 }
// 같은 화면의 주소 인자 바꾸기(서버의 `st.query_params` 쓰기)는 칸을 더하지 않는다.
history.pushState({}, '', '/calculation_result?a=1')
out.sameScreen = [entries.length, here()]
// 탭 이동 — st.switch_page 의 두 번 쌓기: 지금 경로(주소 인자 다시 적기) → 옮긴 경로.
history.pushState({}, '', '/calculation_result?theme=dark')
history.pushState({}, '', '/load_conversion?theme=dark')
out.tabMove = [entries.length, here()]
// 링크로 들어와 인자를 지우는 화면 — 인자 달린 칸(다른 경로)을 쌓고, 지우기는 그 칸 바꾸기다.
history.pushState({}, '', '/process_capa_detail?process=A&month=202610&theme=dark')
history.pushState({}, '', '/process_capa_detail?theme=dark')
out.linkArrival = [entries.length, here()]
// 뒤로가기 한 번이면 직전 화면이다 — 인자 달린 칸이 남지 않아 그 화면에 갇히지 않는다.
back()
out.back = here()
process.stdout.write(JSON.stringify(out))
"""

_LEAVING_RUNNER = """
const entries = ['http://app.test/']
let index = 0
let now = 0
const history = {
  state: {},
  pushState(state, title, url) {
    entries.splice(index + 1)
    entries.push(new URL(url, entries[index]).href)
    index += 1
  },
  replaceState(state, title, url) {
    entries[index] = new URL(url, entries[index]).href
  },
}
guardHistory(history, () => entries[index], () => now, 1000)
const out = {}
const all = () => entries.map((url) => url.replace('http://app.test', ''))
// HOME 칸 — st.switch_page 가 떠나는 HOME 칸에 옮길 화면 인자를 적고(같은 경로)
// 곧이어 옮긴 화면을 쌓는다. 공정 Capa 상세는 받은 인자를 지운다.
history.pushState({}, '', '/?process=A&month=202607&from=home')
now = 60
history.pushState({}, '', '/process_capa_detail?process=A&month=202607&from=home')
now = 200
history.pushState({}, '', '/process_capa_detail')
out.home = [all(), index]
// 인자를 지운 직후 다른 화면으로 옮겨도 지운 칸(인자 달린 칸)을 되살리지 않는다.
now = 300
history.pushState({}, '', '/required_shortening')
out.consumed = all()
// 같은 경로 바꾸기 뒤 늦게 온 다른 경로 쌓기(기다림 밖)는 되돌리지 않는다.
now = 1000
history.pushState({}, '', '/required_shortening?k=1')
now = 2500
history.pushState({}, '', '/space_status?k=1')
out.late = all().slice(-2)
process.stdout.write(JSON.stringify(out))
"""


def test_a_screen_move_stacks_one_history_entry_and_back_leaves_a_link_target() -> None:
    """화면 이동 한 번은 브라우저 기록 한 칸이다. 서버가 주소 인자를 바꾸면 Streamlit 프런트가 지금
    경로로 한 칸 쌓는다 — `st.switch_page` 는 떠나는 화면 주소로 먼저 쌓아 뒤로가기 한 번이
    제자리였고(E2E 결함, 명세 B3 「뒤로가기 → 이전 화면」), 링크 인자를 받아 지우는 화면(공정 Capa
    상세 `?process=` 등)은 인자 달린 칸 뒤에 또 쌓아 뒤로가기가 그 화면에 갇혔다(E2E 결함). 같은
    경로의 쌓기는 늘 그 칸 바꾸기로 돌린다."""
    out = _node(_HISTORY_RUNNER)

    assert out["sameScreen"] == [1, "/calculation_result?a=1"]
    assert out["tabMove"] == [2, "/load_conversion?theme=dark"]
    assert out["linkArrival"] == [3, "/process_capa_detail?theme=dark"]
    assert out["back"] == "/load_conversion?theme=dark"


_QUEUE_RUNNER = """
const MS = 1000
const ids = ['home', 'plan', 'ref', 'calc']
const out = {}
// 산출 결과(calc)에서 생산 계획 → 곧바로 기준 정보. 둘째 누름은 기다리고 마지막 누름만 남긴다.
let q = createSelectQueue()
out.first = pressSelect(q, 'plan', 'calc', 0, MS)
sentSelect(q, 'plan', 'calc', 0)
out.second = pressSelect(q, 'home', 'calc', 100, MS)
out.third = pressSelect(q, 'ref', 'calc', 150, MS)
// 아직 옮긴 화면의 data 가 오지 않았다(지금 탭 그대로) — 보내지 않는다.
out.early = settleSelect(q, 'calc', 200, MS, ids, false)
// 옮긴 화면의 탭 줄이 왔지만 그 회차가 아직 돈다 — 부품 요청과 합쳐져 트리거가 떨어지니 기다린다.
out.running = settleSelect(q, 'plan', 300, MS, ids, true)
// 그 회차가 다 돌았다 — 기다리던 마지막 누름.
out.settled = settleSelect(q, 'plan', 400, MS, ids, false)
out.idle = [q.flight, q.waiting, pressSelect(q, 'plan', 'plan', 500, MS)]
// 기다리던 누름이 옮긴 화면 자신이면 할 일이 없다.
q = createSelectQueue()
sentSelect(q, 'plan', 'calc', 0)
pressSelect(q, 'plan', 'calc', 50, MS)
out.same = settleSelect(q, 'plan', 300, MS, ids, false)
// 옮긴 화면이 끝내 오지 않거나 회차가 계속 돌면 기다림이 다 된 뒤 보낸다.
q = createSelectQueue()
sentSelect(q, 'plan', 'calc', 0)
pressSelect(q, 'ref', 'calc', 50, MS)
out.timeout = [
  settleSelect(q, 'calc', 999, MS, ids, true),
  settleSelect(q, 'calc', 1000, MS, ids, true),
]
out.late = pressSelect(q, 'ref', 'calc', 1200, MS)
// 그 사이 닫힌 탭은 보내지 않는다. 지금 탭 닫기(옮길 이웃은 서버가 정한다)도 같은 기다림이다.
q = createSelectQueue()
sentSelect(q, null, 'calc', 0)
pressSelect(q, 'ref', 'calc', 50, MS)
out.closed = settleSelect(q, 'plan', 300, MS, ['home', 'plan'], false)
process.stdout.write(JSON.stringify(out))
"""


def test_taps_while_a_tab_move_is_in_flight_wait_and_only_the_last_is_sent() -> None:
    """옮기는 동안 누른 탭은 옮긴 화면의 탭 줄이 오고 그 회차가 다 돈 뒤에 마지막 누름만 보낸다 —
    0.1~0.2초 간격으로 두 탭을 누르면 둘째 누름이 떠나는 화면 주소로 회차를 청하거나, 옮긴 화면
    부품의 회차 요청과 서버에서 합쳐지며 트리거 값을 잃어 둘 다 먹히지 않았다(E2E 결함, `_on_select`
    「빠른 두 번 누름도 마지막 누름이 맞다」)."""
    out = _node(_QUEUE_RUNNER)

    assert (out["first"], out["second"], out["third"]) == ("send", "wait", "wait")
    assert out["early"] is None
    assert out["running"] is None
    assert out["settled"] == "ref"
    assert out["idle"] == [None, None, "none"]
    assert out["same"] is None
    assert out["timeout"] == [None, "ref"]
    assert out["late"] == "send"
    assert out["closed"] is None


_HOLD_RUNNER = """
const out = {}
// 편집표에서 막 손을 뗀 누름인가 — 누를 때 포커스가 편집표였거나 마지막 편집표 입력이 5초 안이다.
out.pending = [
  editPending(1000, -Infinity, true, 5000),
  editPending(1000, 900, false, 5000),
  editPending(9000, 900, false, 5000),
]
// 칸을 쓰는 중에 탭을 누름 — 편집기가 바깥 누름에 편집을 적용해 회차를 청한다.
// 서버가 답하기 전(돌지 않음·data 그대로)에는 기다리고, 회차가 도는 동안도 기다리며,
// 새 data(편집 회차의 탭 줄 — leave 가 찼다)가 오고 회차가 끝나면 그때 묻고 보낸다.
const before = { leave: '' }
const after = { leave: '기준 정보 · UPEH' }
const hold = { at: 0, data: before }
out.flow = [
  holdVerdict(hold, 100, false, before, 400, 10000),
  holdVerdict(hold, 200, true, before, 400, 10000),
  holdVerdict(hold, 300, true, after, 400, 10000),
  holdVerdict(hold, 350, false, after, 400, 10000),
]
// 편집이 회차를 청하지 않았으면(값이 같다) 최소 기다림 뒤 보낸다.
// 회차가 끝없이 돌면 최대 기다림 뒤 보낸다.
out.noRun = [
  holdVerdict(hold, 399, false, before, 400, 10000),
  holdVerdict(hold, 400, false, before, 400, 10000),
]
out.cap = holdVerdict(hold, 10000, true, before, 400, 10000)
process.stdout.write(JSON.stringify(out))
"""


def test_a_press_right_after_a_table_edit_waits_for_that_edit_before_asking_to_leave() -> None:
    """떠나기 확인은 앞 회차 data 의 `leave` 로 정한다. 편집표 칸을 쓰는 중이거나 Enter 직후 0.2초
    안에 다른 탭을 누르면 그 편집을 실은 회차가 아직 돌아오지 않아 확인 없이 옮기고 편집이 말없이
    사라졌다(E2E 결함 — 기준 정보 UPEH). 편집표에서 막 손을 뗀 누름은 그 회차가 돌아올 때까지
    붙들었다가 새 data 로 묻는다."""
    out = _node(_HOLD_RUNNER)

    assert out["pending"] == [True, True, False]
    assert out["flow"] == ["wait", "wait", "wait", "go"]
    assert out["noRun"] == ["wait", "go"]
    assert out["cap"] == "go"


def test_leaving_presses_consult_the_edit_hold_before_asking() -> None:
    """다른 탭 고르기와 지금 탭 × 는 묻기(`leaveOk`) 전에 편집표에서 막 손을 뗀 누름인지
    본다. 누르는 순간의 편집표 포커스는 `pointerdown`(포커스가 탭으로 옮기기 전)에서 적는다."""
    select = JS[JS.index("const select = (item) => {") :]
    assert select.index("if (fresh())") < select.index("holding(item")
    close = JS[JS.index("const close = (item) => {") :]
    assert close.index("!fresh()") < close.index("closeNow(item)")
    assert "S.pressFromGrid = S.gridFocused" in JS
    assert "document.addEventListener(type, S.onEdit, true)" in JS
    assert "document.removeEventListener(type, S.onEdit, true)" in JS


def test_a_switch_page_leaves_the_leaving_entry_with_its_own_address() -> None:
    """`st.switch_page` 의 첫 쌓기는 떠나는 칸 주소를 옮길 화면 인자로 바꾼다 — HOME 칸이면 HOME
    기록 칸이 `/?process=…&from=home` 이 되어, 뒤로가기로 돌아온 HOME 에서 사이드바로 옮기면 그
    인자가 따라가 링크처럼 적용됐다(E2E 결함 — HOME 칸 이동이 세 칸을 쌓고 첫 칸이 인자 달린 HOME).
    옮긴 화면을 곧이어 같은 인자로 쌓으면 떠나는 칸을 원래 주소로 되돌린다. 링크 인자를 받아 지운
    칸은 되살리지 않는다."""
    out = _node(_LEAVING_RUNNER)

    assert out["home"] == [["/", "/process_capa_detail"], 1]
    assert out["consumed"] == ["/", "/process_capa_detail", "/required_shortening"]
    assert out["late"] == ["/required_shortening?k=1", "/space_status?k=1"]


def test_moving_taps_arm_the_queue_first_and_the_history_guard_is_one_per_document() -> None:
    """다른 탭 고르기와 지금 탭 닫기(서버가 이웃으로 옮긴다)는 트리거를 보내기 **전에** 누름
    기다림을 건다. 기록 지킴이는 걸고 풀지 않고 늘 걸려 있다 — 문서에 하나다."""
    send_select = JS.index("S.send('select'")
    assert JS.rindex("moving(item.dataset.id)", 0, send_select) > JS.rindex(
        "busy(item)", 0, send_select
    )
    send_close = JS.index("S.send('close'")
    assert 0 < JS.rindex("if (leaving) moving(null)", 0, send_close)
    assert "historyGuard" not in JS
    assert "if (!window.__capaHistoryGuard) {" in JS
    assert "window.__capaHistoryGuard = guardHistory(window.history" in JS
    # 옮긴 화면 회차가 다 돌았는지는 Streamlit 뿌리의 회차 표지로 본다(1.63 프런트 속성).
    assert "data-test-script-state" in JS and "'running'" in JS


_PRESS_RUNNER = """
const MS = 500
const PX = 8
const out = {}
// 「기준 정보」(ref) × 를 (300, 20) 에서 누른 직후 —
// 숨긴 자리로 「산출 결과」(calc) 의 × 나 핀이 당겨 왔다.
const last = { id: 'ref', at: 1000, x: 300, y: 20 }
out.doubleClick = strayPress(last, 'calc', 1002, 300, 20, MS, PX)
out.slowSecond = strayPress(last, 'calc', 1300, 301, 21, MS, PX)
// 더블클릭 창이 지난 누름·자리를 옮긴 누름·같은 탭의 둘째 누름(핀 두 번)은 그대로 받는다.
out.afterWindow = strayPress(last, 'calc', 1500, 300, 20, MS, PX)
out.moved = strayPress(last, 'calc', 1100, 340, 20, MS, PX)
out.sameTab = strayPress(last, 'ref', 1002, 300, 20, MS, PX)
out.first = strayPress(null, 'calc', 1002, 300, 20, MS, PX)
process.stdout.write(JSON.stringify(out))
"""


def test_a_second_press_that_lands_on_the_tab_that_slid_under_the_pointer_is_dropped() -> None:
    """× 를 더블클릭하면 누른 탭은 남고 × 자리로 밀려 들어온 이웃 탭이 닫혔다 — 닫은 탭을 누르자마자
    숨겨 이웃이 당겨 오고, 같은 프레임의 'close' 둘은 마지막 것만 서버에 닿았다(E2E 결함 — 지금 탭의
    왼쪽 탭이면 지금 탭이 고정되고, 0.3초 간격 두 번이면 탭 둘이 닫혔다). 닫기·고정 뒤 더블클릭
    창(0.5초) 안에 같은 자리로 온 누름이 다른 탭에 닿으면 버린다."""
    out = _node(_PRESS_RUNNER)

    assert out == {
        "doubleClick": True,
        "slowSecond": True,
        "afterWindow": False,
        "moved": False,
        "sameTab": False,
        "first": False,
    }


def test_every_press_on_the_strip_consults_the_double_press_guard_first() -> None:
    """× ·핀·탭 누름과 가운데 단추 닫기 모두 보내기 전에 앞 닫기·고정 누름의 꼬리인지
    본다. 닫기·고정만 그 누름을 적는다(고르기는 목록을 움직이지 않는다). 키보드로 누른
    단추(`detail` 0)는 좌표가 없어 보지 않는다."""
    click = JS[JS.index("list.onclick = (event) => {") :]
    click = click[: click.index("\n  }\n")]
    assert click.index("if (stray(event, item)) return") < click.index("close(item)")
    assert click.index("if (stray(event, item)) return") < click.index("S.send('pin'")
    assert click.index("if (stray(event, item)) return") < click.index("select(item)")
    assert click.count("pressed(event, item)") == 2
    aux = JS[JS.index("list.onauxclick = (event) => {") :]
    aux = aux[: aux.index("\n  }\n")]
    assert aux.index("if (stray(event, item)) return") < aux.index("pressed(event, item)")
    assert aux.index("pressed(event, item)") < aux.index("close(item)")
    assert "event.detail > 0" in JS


_LINKS_RUNNER = """
const MS = 1000
const pages = {
  '': 'HOME', plan: '생산 계획', ref: '기준 정보', calc: '산출 결과',
  wip_status: '표준 대비 재공 현황', dynamic_capa: '현황 요약',
  a: 'A', b: 'B', c: 'C', d: 'D', e: 'E',
}
const nine = ['', 'plan', 'ref', 'calc', 'a', 'b', 'c', 'd', 'e']
const verdict = (open, href, flight, epoch, now) =>
  linkVerdict(pages, open, 10, href, linkOpening(flight, epoch, now, MS))
const out = {}
// 탭 9개 — 사이드바 「표준 대비 재공 현황」 링크는 10번째 탭을 여는 누름이라 지나 보내고 적는다.
out.first = verdict(nine, 'wip_status', null, 5, 0)
const flight = { href: 'wip_status', at: 0, epoch: 5 }
// 0.05초 뒤 — 그 탭이 아직 data 에 오지 않았다(같은 epoch). 둘째 화면 링크는 상한이다.
out.second = verdict(nine, 'dynamic_capa', flight, 5, 50)
// 같은 링크를 다시 누름·열린 탭·모르는 주소는 그대로 지나간다.
out.sameLink = verdict(nine, 'wip_status', flight, 5, 60)
out.openTab = verdict(nine, 'plan', flight, 5, 60)
out.unknown = verdict(nine, 'https://example.invalid/', flight, 5, 60)
// 그 탭이 온 data(epoch 가 올랐다) — 이제 열린 탭 10개로 센다.
const ten = [...nine, 'wip_status']
out.arrived = [linkOpening(flight, 6, 300, MS), verdict(ten, 'dynamic_capa', flight, 6, 300)]
// 그 탭이 끝내 오지 않으면(서버가 열지 않았다) 기다림이 다 된 뒤에는 세지 않는다.
out.expired = [linkOpening(flight, 5, 1000, MS), verdict(nine, 'dynamic_capa', flight, 5, 1000)]
// 탭 8개면 앞 누름이 여는 탭을 세어도 9개라 둘째 링크도 연다.
out.room = verdict(nine.slice(1), 'dynamic_capa', flight, 5, 50)
// 앞 누름의 화면이 이미 열린 탭이면 두 번 세지 않는다(8 + 그 탭 = 9개).
out.counted = verdict([...nine.slice(1), 'wip_status'], 'dynamic_capa', flight, 5, 50)
process.stdout.write(JSON.stringify(out))
"""


def test_a_second_page_link_before_the_first_link_tab_arrives_counts_that_tab() -> None:
    """상한 거름은 앞 회차 data 의 탭 목록으로 센다. 탭 9개에서 사이드바 링크 둘을 0.05~0.1초
    간격으로 누르면 첫 링크가 연 10번째 탭이 data 에 오기 전에 둘째 누름이 탭 9개로 세어 거름을
    지났다 — 서버 되돌림(`switch_to_queued_tab`)이 두 화면을 기록에 쌓아 뒤로가기 두 번이 모두 그
    화면·상한 알림에 갇혔다(2026-10-27 E2E). 지나 보낸 링크가 여는 탭은 그 탭이 data 에 올
    때까지(같은 epoch) 열린 탭으로 센다."""
    out = _node(_LINKS_RUNNER)

    assert out["first"] == "open"
    assert out["second"] == "refuse"
    assert (out["sameLink"], out["openTab"], out["unknown"]) == ("pass", "pass", "pass")
    assert out["arrived"] == [None, "refuse"]
    assert out["expired"] == [None, "open"]
    assert out["room"] == "open"
    assert out["counted"] == "open"


def test_the_link_guard_counts_and_records_the_link_it_lets_through() -> None:
    """화면 링크 거름은 `<tabs-links>` 로 정하고, 새 탭을 여는 누름이면 지나 보내며 적는다(다음
    누름이 함께 센다). 적은 누름은 그 탭이 data 에 오면(epoch) 세지 않는다."""
    refusal = JS[JS.index("const refusal = (href) => {") :]
    refusal = refusal[: refusal.index("\n  }\n")]
    counted = "linkOpening(S.linkFlight, D.epoch, now, BUSY_MS)"
    assert f"linkVerdict(pages, open, D.max, href, {counted})" in refusal
    assert "if (verdict === 'open') S.linkFlight = { href, at: now, epoch: D.epoch }" in refusal
    assert "linkFlight: null" in JS


_INSTALL_PRELUDE = """
const calls = []
globalThis.window = {
  location: { href: 'http://app.test/constraint_simulation?process=A&theme=light' },
  history: {
    state: {},
    pushState(state, title, url) { calls.push(['push', String(url)]) },
    replaceState(state, title, url) { calls.push(['replace', String(url)]) },
  },
}
"""

_INSTALL_RUNNER = """
const first = window.__capaHistoryGuard
installHistoryGuard()
// 첫 회차가 링크 인자를 지운다 — Streamlit 프런트가 지금 경로로 쌓는다.
window.history.pushState({}, '', '/constraint_simulation?theme=light')
process.stdout.write(JSON.stringify({
  installed: first === window.history,
  once: window.__capaHistoryGuard === first,
  calls,
}))
"""


def test_the_intro_overlay_installs_the_history_guard_before_the_first_run_drops_link_args() -> (
    None
):
    """새 브라우저 탭으로 링크 인자 화면(제약 시뮬레이션·공정 Capa 상세 `?process=`)에 들어오면 그
    화면이 첫 회차에 인자를 지우는 주소 메시지가 탭 줄 JS 가 마운트되기 전에 닿아(탭 줄은 페이지
    바로 앞이다) 기록이 한 칸 더 쌓였다 — 뒤로가기 첫 번이 화면은 그대로 둔 채 주소의 인자만
    되살렸다(2026-10-26 E2E). 회차 맨 앞(부트스트랩 전)의 입장 화면 JS 가 모듈을 읽는 순간
    지킴이를 건다. 글은 탭 줄 자산의 구획 그대로이고 탭 줄도 같은 함수를 안전망으로 부른다."""
    from capa_simulation.components import intro_overlay
    from capa_simulation.components.history_guard import history_guard_script

    guard = history_guard_script()
    registered = intro_overlay._registered_js()
    assert registered.startswith(guard)
    assert guard.rstrip().endswith("installHistoryGuard()")
    assert registered.index("installHistoryGuard()") < registered.index("export default")
    for name in ("tabs-history", "tabs-history-install"):
        body = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert body is not None and body.group("body") in guard
    strip = JS[JS.index("export default function") :]
    assert "installHistoryGuard()" in strip
    assert "guardHistory(" not in strip

    out = _node(_INSTALL_RUNNER, prelude=_INSTALL_PRELUDE + guard)

    assert out == {
        "installed": True,
        "once": True,
        "calls": [["replace", "/constraint_simulation?theme=light"]],
    }
