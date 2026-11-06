# Purpose: 탭 줄 자산의 트리거·접근성·색 계약을 글자로, 기록·누름 구획을 node 로 검사한다.

"""AppTest 는 탭 줄 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속을 여기서 붙잡고, DOM 을 모르는
순수 구획(`// <tabs-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI 에서는 실패한다.
나머지 동작은 브라우저로 본다."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from js_runner import run_js_json

from capa_simulation.components import page_tabs

ASSETS = page_tabs._ASSETS
HTML = (ASSETS / "page_tabs.html").read_text(encoding="utf-8")
CSS = (ASSETS / "page_tabs.css").read_text(encoding="utf-8")
JS = (ASSETS / "page_tabs.js").read_text(encoding="utf-8")


def test_the_strip_sends_only_one_shot_triggers() -> None:
    """누름은 트리거 넷(`select`·`close`·`pin`·`move`)뿐이다 — 남는 상태 값은 앱 전체를 다시 돌린다.
    `move` 는 끌어서 차례 바꾸기(2026-11-02 사용자 요청)다."""
    assert "setStateValue" not in JS
    assert set(re.findall(r"S\.send\('([a-z]+)'", JS)) == {"select", "close", "pin", "move"}
    source = Path(page_tabs.__file__).read_text(encoding="utf-8")
    for name in ("on_select_change", "on_close_change", "on_pin_change", "on_move_change"):
        assert name in source


def test_strip_only_presses_carry_the_order_the_script_already_drew() -> None:
    """고정·차례·닫기는 누르자마자 서버 규칙(`<tabs-order>`)으로 그리고 그
    차례(`order`)·고정(`pins`)을 싣는다 — 서버(`page_tabs._settle_drawn`)는 같은 차례면 페이지를
    다시 돌리지 않는다(2026-11-02 사용자 요청 — 핀 고정에 페이지 로딩). 차례 바꾸기는 묶어 보내고
    (`flushMove`), 고정·닫기는 지금 그림과 번호(`claimDrawn` — 담긴 차례를 데려간다)를, 고르기는
    담긴 차례가 있을 때만 그것을 싣는다(2026-11-03 사용자 검수 — 연달아 옮기면 불필요한 로딩)."""
    move = re.search(r"S\.send\('move', \{([^}]*)\}\)", JS)
    assert move is not None
    assert all(f"{name}:" in move.group(1) for name in ("order", "pins")) and "seq" in move.group(1)
    pin = re.search(r"S\.send\('pin', \{([^}]*)\}\)", JS)
    assert pin is not None and "...claimDrawn()" in pin.group(1)
    sent_close = re.search(r"S\.send\('close', \{([^}]*)\}\)", JS)
    assert sent_close is not None and "...carried" in sent_close.group(1)
    claim = JS[JS.index("const claimDrawn = () => {") :]
    claim = claim[: claim.index("\n  }\n")]
    assert "order: drawn.ids, pins: drawn.pinned, seq: claimOrder(" in claim
    select = JS[JS.index("const sendSelect = (item) => {") :]
    select = select[: select.index("\n  }\n")]
    assert "S.moves.due !== null ? claimDrawn() : {}" in select
    click = JS[JS.index("list.onclick = (event) => {") :]
    click = click[: click.index("\n  }\n")]
    assert click.index("pinnedOrder(") < click.index("arrange(plan)") < click.index("S.send('pin'")
    close = JS[JS.index("const closeNow = (item) => {") :]
    close = close[: close.index("\n  }\n")]
    # 닫기는 숨기기 전에 그림을 담는다 — 닫는 탭이 제자리에 있어야 서버가 보이는 이웃으로 옮긴다.
    assert (
        close.index("const carried = claimDrawn()")
        < close.index("item.hidden = true")
        < close.index("syncControls()")
        < close.index("S.send('close'")
    )


def test_tabs_are_dragged_with_pointer_events_and_a_keyboard_alternative() -> None:
    """HTML5 끌어 놓기가 아니라 포인터 이벤트다 — 그림자 DOM·가로로 넘치는 목록 안에서 축을 묶고
    고정 묶음 앞에서 멈추고 터치 길게 누르기를 다뤄야 한다. 끈 뒤의 누름은 고르기가 아니다(화면을
    옮기지 않는다). 키보드 대안은 `Ctrl+Shift+←/→` 이고 단추가 `aria-keyshortcuts` 로 알린다. 놓을
    자리는 세로 막대가 말하고 옮긴 뒤 읽기 도구에 알린다."""
    assert "draggable" not in JS + HTML and "dragstart" not in JS
    assert "list.onpointerdown = (event) => {" in JS and "startDrag(event)" in JS
    for event in ("pointermove", "pointerup", "pointercancel"):
        assert f"['{event}'," in JS
    click = JS[JS.index("list.onclick = (event) => {") :]
    assert click.index("dragClick(S.dragEndAt") < click.index("const button = ")
    assert "event.ctrlKey" in JS and "event.shiftKey" in JS and "keyboardMove(" in JS
    assert "const MOVE_KEYS = 'Control+Shift+ArrowLeft Control+Shift+ArrowRight'" in JS
    assert "setAttr(P.tab, 'aria-keyshortcuts', pinned ? null : MOVE_KEYS)" in JS
    assert 'class="capa-tabs-drop" aria-hidden="true" hidden' in HTML
    assert 'class="capa-tabs-announce capa-tabs-sr" role="status"' in HTML
    assert "text.moved" in JS and page_tabs.TEXT["moved"].startswith("{label} 탭을 {index}번째로")
    # 끄는 중에 새 data 가 오면 끌기를 접는다 — 새 data 가 탭을 다시 놓는다.
    head = JS[JS.index("export default function") :]
    folded = head.index("if (S.drag && S.endDrag) S.endDrag(false, true)")
    assert folded < head.index("const paint =")
    # 비수동 touchmove 로만 끄는 동안의 목록 굴리기를 막는다.
    assert "list.addEventListener('touchmove', S.onTouchMove, { passive: false })" in JS
    assert "list.removeEventListener('touchmove', S.onTouchMove)" in JS


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


def test_the_current_tab_keeps_room_for_its_name_when_the_strip_is_crowded() -> None:
    """탭 10개면 모두 최소 폭으로 줄고 지금 탭은 핀·× 가 자리를 먹어 이름이 「A.」 로 줄었다(1024px
    E2E). 지금 탭은 줄지 않는다(제 폭, 길어야 15rem). 최소 폭을 넓히지는 않는다 — 탭이 적을 때도
    HOME 처럼 짧은 지금 탭이 넓어져(헤드리스 Chrome 108 → 184px) 탭을 옮길 때마다 뒤 탭들이 옆으로
    밀렸다. 좁은 창(휴대폰 폭)에서는 고정하지 않은 지금 탭의 핀도 두지 않는다 — 고정한 탭의 핀(고정
    풀기)은 남는다."""
    active = _rule(".capa-tabs-item.is-active")
    assert "flex-shrink: 0;" in active
    assert "min-width" not in active
    assert "max-width: 15rem;" in _rule(".capa-tabs-item")
    narrow = re.search(r"@media \(max-width: 640px\)\s*\{(.*?)\n\}", CSS, re.S)
    assert narrow is not None
    rule = re.search(
        r"\.capa-tabs-item\.is-active:not\(\.is-pinned\) \.capa-tabs-pin \{([^}]*)\}",
        narrow.group(1),
    )
    assert rule is not None and "display: none" in rule.group(1)


def test_the_strip_raises_its_notices_in_the_alert_center_and_keeps_no_notice_box() -> None:
    """상한 알림 · 공식 복귀 알림은 탭 줄 칸이 아니라 같은 문서의 알림 칸(오른쪽 아래 알림창 한 꼴 ·
    Alarm 기록 — 2026-11-03 결정 보드 D3)에 낸다. 탭 줄의 옛 알림 칸(`.capa-tabs-notice`)은 걷었다 —
    한 칸이라 뒤 알림이 앞 알림을 덮었다(설계 1장). 알림 칸이 아직 서지 않았으면(탭 줄이 먼저
    그려진다) 담아 두고 칸이 설 때 꺼낸다. 코드 · 단계는 파이썬 등록부가 data 로 준다."""
    assert "capa-tabs-notice" not in HTML and "capa-tabs-notice" not in CSS
    assert "capa-tabs-notice" not in JS
    raise_alert = JS[JS.index("function raiseAlert(note) {") :]
    raise_alert = raise_alert[: raise_alert.index("\n}\n")]
    assert "window.__capaAlerts" in raise_alert and "window.__capaAlertQueue" in raise_alert
    assert JS.count("flash('limit',") == 2
    from capa_simulation import alerts
    from capa_simulation.page_tabs_state import TabStrip

    data = page_tabs.tabs_data(
        TabStrip(paths=(), pinned=frozenset()),
        active=None,
        hrefs={},
        marks={},
        leave="",
        epoch=0,
        notice=None,
    )
    assert data["alerts"] == {
        kind: {"code": code, "level": alerts.spec(code).level}
        for kind, code in page_tabs.ALERT_CODES.items()
    }
    assert [alerts.spec(code).kind for code in page_tabs.ALERT_CODES.values()] == ["event"] * 3
    # 짧은 글(알림창)은 60자 안팎이고 전문(패널 · 로그)은 옛 글 그대로다.
    for short in (page_tabs.RETURN_SHORT, page_tabs.THEME_RETURN_SHORT):
        assert len(short.format(label="「셋업 가속안」 r3")) <= alerts.SHORT_LIMIT
    assert "const SHORT_LIMIT = 60" in JS and alerts.SHORT_LIMIT == 60


def test_an_alert_center_go_to_page_rides_the_strips_own_move() -> None:
    """알림 칸 「그 화면으로」(`capa-open-page` — {href})는 탭 줄의 이동 길을 탄다 — 열린 탭이면 탭
    고르기(떠나기 확인 · 한 번에 하나), 아니면 그 화면 링크를 눌러 상한 거름(`S.onLink`)이 받는다.
    처리기는 문서에 하나이고 컴포넌트가 내려갈 때 걷는다."""
    handler = JS[JS.index("S.onOpenPage = (event) => {") :]
    handler = handler[: handler.index("window.addEventListener(OPEN_PAGE_EVENT, S.onOpenPage)")]
    assert "select(item)" in handler and "link.click()" in handler
    assert "const OPEN_PAGE_EVENT = 'capa-open-page'" in JS
    assert "window.removeEventListener(OPEN_PAGE_EVENT, S.onOpenPage)" in JS
    from capa_simulation.components import alert_center

    center = (alert_center._ASSETS / "alert_center.js").read_text(encoding="utf-8")
    assert "const OPEN_PAGE_EVENT = 'capa-open-page'" in center


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

_SECTIONS = (
    "tabs-history",
    "tabs-hold",
    "tabs-grid",
    "tabs-queue",
    "tabs-press",
    "tabs-order",
    "tabs-batch",
    "tabs-drag",
    "tabs-links",
    "tabs-edges",
    "tabs-focus",
    "tabs-return",
)


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"page_tabs.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(runner: str, *, prelude: str | None = None) -> Any:
    """`prelude`(기본은 순수 구획들) 뒤에 `runner` 를 붙여 node 로 돌리고 찍은 JSON 을 읽는다."""
    return run_js_json(
        (_sections() if prelude is None else prelude) + "\n" + runner, what="탭 줄 JS 구획 시험"
    )


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
const GRACE = 400
const ids = ['home', 'plan', 'ref', 'calc']
const out = {}
// 산출 결과(calc)에서 생산 계획 → 곧바로 기준 정보. 둘째 누름은 기다리고 마지막 누름만 남긴다.
let q = createSelectQueue()
out.first = pressSelect(q, 'plan', 'calc', 0, MS)
sentSelect(q, 'plan', 'calc', 0)
out.second = pressSelect(q, 'home', 'calc', 100, MS)
out.third = pressSelect(q, 'ref', 'calc', 150, MS)
// 아직 옮긴 화면의 data 가 오지 않았다(지금 탭 그대로) — 보내지 않는다.
out.early = settleSelect(q, 'calc', 200, MS, ids, false, GRACE)
// 옮긴 화면의 탭 줄이 막 왔고 그 회차가 아직 돈다 — 잠깐(GRACE) 기다린다.
out.running = settleSelect(q, 'plan', 300, MS, ids, true, GRACE)
// 그 회차가 다 돌았다 — 기다리던 마지막 누름(가벼운 화면은 GRACE 안에 끝나 전과 같다).
out.settled = settleSelect(q, 'plan', 400, MS, ids, false, GRACE)
out.idle = [q.flight, q.waiting, pressSelect(q, 'plan', 'plan', 500, MS)]
// 기다리던 누름이 옮긴 화면 자신이면 할 일이 없다.
q = createSelectQueue()
sentSelect(q, 'plan', 'calc', 0)
pressSelect(q, 'plan', 'calc', 50, MS)
out.same = settleSelect(q, 'plan', 300, MS, ids, false, GRACE)
// 옮긴 화면이 끝내 오지 않거나 회차가 계속 돌면 기다림이 다 된 뒤 보낸다.
q = createSelectQueue()
sentSelect(q, 'plan', 'calc', 0)
pressSelect(q, 'ref', 'calc', 50, MS)
out.timeout = [
  settleSelect(q, 'calc', 999, MS, ids, true, GRACE),
  settleSelect(q, 'calc', 1000, MS, ids, true, GRACE),
]
out.late = pressSelect(q, 'ref', 'calc', 1200, MS)
// 그 사이 닫힌 탭은 보내지 않는다. 지금 탭 닫기(옮길 이웃은 서버가 정한다)도 같은 기다림이다.
q = createSelectQueue()
sentSelect(q, null, 'calc', 0)
pressSelect(q, 'ref', 'calc', 50, MS)
out.closed = settleSelect(q, 'plan', 300, MS, ['home', 'plan'], false, GRACE)
process.stdout.write(JSON.stringify(out))
"""


def test_taps_while_a_tab_move_is_in_flight_wait_and_only_the_last_is_sent() -> None:
    """옮기는 동안 누른 탭은 옮긴 화면의 탭 줄이 오고 그 회차가 다 돈 뒤(가벼운 화면)에 마지막
    누름만 보낸다 — 0.1~0.2초 간격으로 두 탭을 누르면 둘째 누름이 떠나는 화면 주소로 회차를 청하거나
    탭 줄이 온 그리기 안에서 보내져 트리거 값을 잃어 둘 다 먹히지 않았다(E2E 결함, `_on_select`
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


_SLOW_SCREEN_RUNNER = """
const MS = 10000
const GRACE = 1000
const ids = ['home', 'plan', 'ref']
const out = {}
// 생산 계획(plan)에서 HOME 탭 — HOME 첫 계산이 몇 초 돈다(회차 표지가 늘 「돈다」).
let q = createSelectQueue()
sentSelect(q, 'home', 'plan', 0)
out.arrive = settleSelect(q, 'home', 300, MS, ids, true, GRACE)
out.inGrace = settleSelect(q, 'home', 1250, MS, ids, true, GRACE)
out.afterGrace = settleSelect(q, 'home', 1300, MS, ids, true, GRACE)
out.cleared = q.flight === null
// 계산 중(2초)에 누른 생산 계획 탭은 기다리지 않고 곧바로 간다 —
// 서버가 곧바로 새 회차로 받는다(runner.fastReruns).
out.press = pressSelect(q, 'plan', 'home', 2000, MS)
// HOME 탭 뒤 0.15초에 누른 기준 정보 탭은 HOME 탭 줄이 온 뒤 GRACE 에 간다 —
// HOME 이 끝나기를 기다리지 않는다.
q = createSelectQueue()
sentSelect(q, 'home', 'plan', 0)
out.rapidPress = pressSelect(q, 'ref', 'plan', 150, MS)
out.rapid = [
  settleSelect(q, 'home', 300, MS, ids, true, GRACE),
  settleSelect(q, 'home', 1299, MS, ids, true, GRACE),
  settleSelect(q, 'home', 1300, MS, ids, true, GRACE),
]
// 탭 줄을 처음 본 때부터 센다 — 늦게 본 탭 줄은 그때부터다(회차가 끝나면 그 전에도 간다).
q = createSelectQueue()
sentSelect(q, 'home', 'plan', 0)
pressSelect(q, 'ref', 'plan', 100, MS)
out.lateArrival = [
  settleSelect(q, 'plan', 2000, MS, ids, true, GRACE),
  settleSelect(q, 'home', 2500, MS, ids, true, GRACE),
  settleSelect(q, 'home', 3499, MS, ids, true, GRACE),
  settleSelect(q, 'home', 3500, MS, ids, true, GRACE),
]
process.stdout.write(JSON.stringify(out))
"""


def test_a_tap_while_the_moved_screen_still_computes_is_sent_after_a_short_grace() -> None:
    """옮긴 화면이 오래 돌 때(HOME 첫 계산) 누른 탭은 그 회차가 끝나기를 기다리지 않는다 — 탭
    줄이 온 뒤 `MOVED_GRACE_MS` 가 지나면 보내고 서버가 곧바로 새 회차로 받는다(`fastReruns`).
    회차 끝까지만 기다리면 누른 탭이 HOME 계산과 브라우저 그리기가 끝날 때까지 묶였다(사내 리뷰
    202610271800 발견 3 — HOME 로딩 끝 + 약 2초)."""
    out = _node(_SLOW_SCREEN_RUNNER)

    assert [out["arrive"], out["inGrace"], out["afterGrace"]] == [None, None, None]
    assert out["cleared"] is True
    assert out["press"] == "send"
    assert out["rapidPress"] == "wait"
    assert out["rapid"] == [None, None, "ref"]
    assert out["lateArrival"] == [None, None, None, "ref"]
    assert "const MOVED_GRACE_MS = 1000" in JS
    assert "BUSY_MS, open, running, MOVED_GRACE_MS)" in JS


def test_new_data_never_sends_a_trigger_from_inside_the_component_render() -> None:
    """새 data 로 부품이 다시 불릴 때 보낸 이동·붙든 누름은 그 함수 **밖**(다음 차례)에서 본다.
    탭 줄이 온 그리기 안에서 트리거를 보내면 Streamlit 프런트가 그 값을 회차 요청에 싣지 않아
    누름이 사라졌다(사외 사본 30번 중 4번 — 서버에 닿은 요청에 탭 줄 칸이 없었다)."""
    tail = JS[JS.rindex("// 새 data 가 왔다") : JS.rindex("return () => {")]
    assert "S.settleTimer = setTimeout(() => settle(), 0)" in tail
    assert "S.holdTimer = setTimeout(() => release(), 0)" in tail
    assert "if (S.queue.flight !== null) settle()" not in JS
    assert "if (S.hold) release()" not in JS


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


_ORDER_RUNNER = """
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const out = cases.map((c) => {
  if (c.op === 'pin') return pinnedOrder(c.ids, c.pinned, c.id, c.pin)
  if (c.op === 'move') return movedOrder(c.ids, c.pinned, c.id, c.before)
  if (c.op === 'closable') return closableIds(c.ids, c.pinned)
  if (c.op === 'merge') return mergedOrder(c.ids, c.pinned, c.want)
  const plan = keyboardMove(c.ids, c.pinned, c.id, c.step)
  return plan === null ? null : movedOrder(c.ids, c.pinned, c.id, plan.before).ids
})
process.stdout.write(JSON.stringify(out))
"""


def _order_cases() -> tuple[list[dict[str, Any]], list[Any]]:
    """`<tabs-order>` 과 서버 규칙을 맞댈 표 — (JS 에 줄 경우, 파이썬 답)."""
    from capa_simulation.navigation import (
        CAPA_CHATBOT,
        HOME,
        LOAD_CONVERSION,
        SCENARIO_MANAGEMENT,
    )
    from capa_simulation.page_tabs_state import TabStrip, arranged, moved, pinned_to

    h, a, b, c = HOME.path, LOAD_CONVERSION.path, SCENARIO_MANAGEMENT.path, CAPA_CHATBOT.path
    gone = "app_pages/gone.py"
    strips = [
        TabStrip((h, a, b, c), frozenset({h})),
        TabStrip((h, c, a, b), frozenset({h, c})),
        TabStrip((a, b, c), frozenset()),
        TabStrip((h, a), frozenset({h, a})),
        TabStrip((a,), frozenset()),
    ]
    cases: list[dict[str, Any]] = []
    answers: list[Any] = []
    for strip in strips:
        ids, pins = list(strip.paths), [p for p in strip.paths if p in strip.pinned]
        base = {"ids": ids, "pinned": pins}
        cases.append({**base, "op": "closable"})
        answers.append([p for p in ids if strip.closable(p)])
        # 그린 차례 입히기(`arranged` — 2026-11-03 묶어 보내기): 뒤집은 차례 · 모르는 탭 · 빠진 탭 ·
        # 겹침.
        for want in (
            list(reversed(ids)),
            [gone, *ids[1:], ids[0]],
            ids[1:],
            [*ids[:1], *ids[:1], *reversed(ids)],
            [],
        ):
            cases.append({**base, "op": "merge", "want": want})
            result = arranged(strip, want)
            answers.append(
                {
                    "ids": list(result.paths),
                    "pinned": [p for p in result.paths if p in result.pinned],
                }
            )
        for target in [*ids, gone]:
            for pin in (True, False):
                cases.append({**base, "op": "pin", "id": target, "pin": pin})
                result = pinned_to(strip, target, pin)
                answers.append(
                    {
                        "ids": list(result.paths),
                        "pinned": [p for p in result.paths if p in result.pinned],
                    }
                )
            for before in [*ids, gone, None]:
                cases.append({**base, "op": "move", "id": target, "before": before})
                result = moved(strip, target, before)
                answers.append(
                    {
                        "ids": list(result.paths),
                        "pinned": [p for p in result.paths if p in result.pinned],
                    }
                )
            if target == gone:
                continue
            for step in (-1, 1):
                cases.append({**base, "op": "key", "id": target, "step": step})
                index, to = ids.index(target), ids.index(target) + step
                if target in strip.pinned or to < len(pins) or to >= len(ids):
                    answers.append(None)
                else:
                    swapped = list(ids)
                    swapped[index], swapped[to] = swapped[to], swapped[index]
                    answers.append(swapped)
    return cases, answers


def test_the_script_draws_presses_with_the_same_rules_as_the_server() -> None:
    """누르자마자 그린 차례가 서버 목록과 같아야 페이지를 다시 돌리지 않는다 —
    고정(`pinned_to`)·차례 (`moved`)·닫기 단추(`closable`)를 파이썬과 같은 표로 맞댄다. 키보드 한
    칸은 이웃과 자리를 바꾸고 고정 묶음을 넘지 않는다."""
    cases, answers = _order_cases()
    got = run_js_json(
        _sections() + "\n" + _ORDER_RUNNER, what="탭 줄 JS 구획 시험", stdin=json.dumps(cases)
    )
    wrong = [
        (case, want, have)
        for case, want, have in zip(cases, answers, got, strict=True)
        if want != have
    ]
    assert not wrong, wrong[:3]
    assert len(cases) > 150


_BATCH_RUNNER = """
const out = {}
const H = 'h', A = 'a', B = 'b', C = 'c', D = 'd'
const start = { ids: [H, A, B, C, D], pinned: [H] }
// 끝 탭 D 를 80ms 간격으로 왼쪽 · 왼쪽 · 오른쪽 · 왼쪽 — 그릴 때마다 담고, 쉼(400ms) 안에는
// 기다린다.
const batch = createMoveBatch()
let drawn = start
let sends = 0
const verdicts = []
let t = 0
for (const step of [-1, -1, 1, -1]) {
  const plan = keyboardMove(drawn.ids, drawn.pinned, D, step)
  drawn = movedOrder(drawn.ids, drawn.pinned, D, plan.before)
  dueMove(batch, drawn, t)
  verdicts.push(moveVerdict(batch, drawn, knownOrder(batch, start), t + 50, 400, false, 10000))
  t += 80
}
out.burstWaits = verdicts
// 마지막 누름 뒤 399ms 는 아직 쉼, 400ms 에 보낸다 — 앱이 돌면 끝날 때까지(길어야 10초) 더
// 기다린다.
const last = t - 80
out.quiet = [
  moveVerdict(batch, drawn, knownOrder(batch, start), last + 399, 400, false, 10000),
  moveVerdict(batch, drawn, knownOrder(batch, start), last + 400, 400, true, 10000),
  moveVerdict(batch, drawn, knownOrder(batch, start), last + 10000, 400, true, 10000),
  moveVerdict(batch, drawn, knownOrder(batch, start), last + 400, 400, false, 10000),
]
const verdict = (b, d, known, now, busy) =>
  moveVerdict(b, d, knownOrder(b, known), now, 400, busy, 10000)
const seq = claimOrder(batch, drawn, last + 400)
sends += 1
const after = verdict(batch, drawn, start, last + 900, false)
out.sent = { seq, ids: batch.sent.ids, due: batch.due, after }
// 보낸 차례가 data 에 오기 전에 다시 처음 차례로 되돌리면 — 서버가 아는 것은 보낸 차례라 보낸다.
dueMove(batch, start, last + 1000)
out.backToStartAfterSend = verdict(batch, start, start, last + 1400, false)
// 보내기 전에 되돌아오면(왼쪽 갔다 오른쪽) 서버가 이미 아는 차례 — 보내지 않는다.
const round = createMoveBatch()
const left = movedOrder(start.ids, start.pinned, D, C)
dueMove(round, left, 0)
dueMove(round, start, 80)
out.roundTrip = moveVerdict(round, start, knownOrder(round, start), 480, 400, false, 10000)
// 새 data — 앞 번호(낡은 data)는 보낸 그림을 놓지 않고 그 차례를 data 목록에 입힌다(새 탭 E 는
// 뒤에).
const fresh = createMoveBatch()
const moved = { ids: [H, D, A, B, C], pinned: [H] }
claimOrder(fresh, moved, 0)
const stale = { ids: [H, A, B, C, D, 'e'], pinned: [H] }
dataArrived(fresh, 0, 300, 2000)
out.staleShown = shownOrder(fresh, stale)
out.staleKept = fresh.sent !== null
// 서버가 받은 번호가 오면 놓고 data 그대로.
dataArrived(fresh, 1, 600, 2000)
const confirmed = { ids: [H, D, A, B, C, 'e'], pinned: [H] }
out.confirmed = { sent: fresh.sent, shown: shownOrder(fresh, confirmed) }
// 받은 흔적 없이 2초가 지난 data — 곧 다시 보내게 담는다(번호는 data 의 것 아래로 붙이지 않는다).
const lost = createMoveBatch()
claimOrder(lost, moved, 0)
dataArrived(lost, 0, 2500, 2000)
const again = verdict(lost, moved, start, 2500, false)
out.lost = { due: lost.due && lost.due.ids, sent: lost.sent, verdict: again }
const resumed = createMoveBatch()
dataArrived(resumed, 57, 0, 2000)
out.resumedSeq = claimOrder(resumed, moved, 0)
out.sends = sends
process.stdout.write(JSON.stringify(out))
"""


def test_consecutive_tab_moves_are_drawn_at_once_and_sent_once_after_a_pause() -> None:
    """연달아 옮긴 차례는 곧바로 그리고 서버에는 마지막 그림만 한 번 보낸다(`<tabs-batch>`,
    2026-11-03 사용자 검수 — 「몇 번 연속으로 좌우로 움직이는 경우 불필요한 로딩이 발생하거나 멈추는
    경우」). 쉼 안의 누름은 기다리고, 앱이 돌면 끝날 때까지(길어야 `BUSY_MS`) 더 기다린다. 서버가
    아는 차례(data, 아직 따라오지 않은 보낸 그림이 있으면 그것)와 같으면 보내지 않는다. 새 data 가
    앞 번호면 보낸 그림을 그 위에 입혀 보이고, 서버가 받은 번호가 오면 놓으며, 받은 흔적 없이 오래면
    다시 담는다."""
    out = _node(_BATCH_RUNNER)
    assert out["burstWaits"] == ["wait"] * 4
    assert out["quiet"] == ["wait", "wait", "send", "send"]
    assert out["sent"] == {"seq": 1, "ids": ["h", "a", "d", "b", "c"], "due": None, "after": "idle"}
    assert out["backToStartAfterSend"] == "send"
    assert out["roundTrip"] == "drop"
    assert out["staleShown"] == {"ids": ["h", "d", "a", "b", "c", "e"], "pinned": ["h"]}
    assert out["staleKept"] is True
    assert out["confirmed"] == {
        "sent": None,
        "shown": {"ids": ["h", "d", "a", "b", "c", "e"], "pinned": ["h"]},
    }
    assert out["lost"] == {"due": ["h", "d", "a", "b", "c"], "sent": None, "verdict": "send"}
    assert out["resumedSeq"] == 58
    assert out["sends"] == 1


def test_a_move_waits_for_a_running_app_and_presses_take_the_unsent_order_along() -> None:
    """차례 바꾸기는 누를 때 보내지 않는다 — 담고(`dueMove`) 쉼 뒤 `flushMove` 가 앱 · 옮기는 누름 ·
    붙든 누름 · 끌기가 끝났을 때 보낸다. 새 data 가 오면 그 그림을 먼저 입혀 놓아(`shownOrder`)
    옮기던 탭이 data 차례로 밀렸다 돌아오지 않는다. 키보드 대안은 그린 뒤 초점을 옮긴 탭에 둔다."""
    commit = JS[JS.index("function commitMove(item, before) {") :]
    commit = commit[: commit.index("\n  }\n")]
    assert "S.send(" not in commit
    assert commit.index("arrange(plan)") < commit.index("dueMove(S.moves, plan, Date.now())")
    assert "setTimeout(() => flushMove(), MOVE_SEND_MS)" in commit
    flush = JS[JS.index("function flushMove() {") :]
    flush = flush[: flush.index("\n  }\n")]
    for wait in ("appRunning()", "S.queue.flight !== null", "S.hold !== null", "S.drag.on"):
        assert wait in flush, wait
    assert flush.index("moveVerdict(") < flush.index("claimOrder(") < flush.index("S.send('move'")
    head = JS[JS.index("export default function") :]
    place = head.index("const placed = shownOrder(S.moves, dataOrder)")
    assert head.index("dataArrived(S.moves,") < place < head.index("placed.ids.forEach(")
    assert "const MOVE_SEND_MS = 400" in JS
    keys = JS[JS.index("list.onkeydown = (event) => {") :]
    keys = keys[: keys.index("\n  }\n")]
    assert keys.index("commitMove(item, plan.before)") < keys.index("tab.focus(")
    assert "clearTimeout(S.moveTimer)" in JS[JS.rindex("return () => {") :]


_DRAG_RUNNER = """
const out = {}
// 마우스·펜 — 가로로 5px 를 넘어야 끌기다. 세로만 움직이면 끌지 않는다.
out.mouse = [dragStarts('mouse', 5, 0, 0, 5, 350), dragStarts('mouse', -6, 0, 0, 5, 350),
  dragStarts('pen', 0, 40, 900, 5, 350)]
// 터치 — 길게 누른 뒤에야 끌기, 그 전에 움직이면 목록 굴리기라 그만둔다.
out.touch = [dragStarts('touch', 2, 2, 100, 5, 350), dragStarts('touch', 9, 0, 100, 5, 350),
  dragStarts('touch', 2, 1, 350, 5, 350)]
// 놓을 자리 — 다른 탭 가운데를 지난 수. 고정 탭 수(1) 아래로는 내려가지 않는다.
const mids = [40, 140, 240, 340]
out.slots = [dropSlot(mids, 10, 1), dropSlot(mids, 141, 1), dropSlot(mids, 239, 1),
  dropSlot(mids, 500, 1), dropSlot(mids, 10, 0)]
// 가장자리 굴리기 — 가장자리에 가까울수록 빠르고 안쪽에서는 멈춘다.
out.edge = [edgeSpeed(100, 100, 600, 32, 12), edgeSpeed(120, 100, 600, 32, 12),
  edgeSpeed(300, 100, 600, 32, 12), edgeSpeed(590, 100, 600, 32, 12), edgeSpeed(700, 100, 600, 32,
  12)]
// 끈 뒤 400ms 안의 누름만 버린다.
out.click = [dragClick(null, 0, 400), dragClick(1000, 1399, 400), dragClick(1000, 1400, 400)]
process.stdout.write(JSON.stringify(out))
"""


def test_a_drag_starts_past_a_slop_stops_at_the_pinned_group_and_swallows_its_click() -> None:
    """끌기 판정 — 마우스는 가로 5px 문턱(그 전의 누름은 고르기·고정·× 그대로), 터치는 350ms 길게
    누르기 (그 전에 움직이면 목록 굴리기). 놓을 자리는 다른 탭 가운데를 지난 수이고 고정 묶음
    앞으로는 가지 않는다. 가장자리에서는 목록을 굴린다. 끈 뒤의 click 은 고르기로 보내지 않는다."""
    out = _node(_DRAG_RUNNER)

    assert out["mouse"] == ["wait", "drag", "wait"]
    assert out["touch"] == ["wait", "cancel", "drag"]
    assert out["slots"] == [1, 2, 2, 4, 0]
    assert out["edge"] == [-12, -5, 0, 9, 12]
    assert out["click"] == [False, True, False]


_DRAG_BOUND_RUNNER = """
const out = {}
// 넘친 줄(사본 1000px · 탭 10개 — 반박 검토 측정): 끄는 탭(91px) 밖 아홉 탭의 left.
// 모두 91px 로 줄었다. scrollWidth 928.
const lefts = [0, 186, 279, 372, 465, 558, 651, 744, 837]
const mids = lefts.map((left) => left + 91 / 2)
const low = 91
const high = 928 - 91
// 오른쪽 가장자리까지 끌었다 — 끄는 탭이 끝(high)에 묶인다. 맨 끝 자리(9)다.
const end = dragLeft(1000, low, high)
out.end = [end.left, end.bound, dropSlot(mids, end.left + 91 / 2, 1, end.bound)]
// 가운데만 보던 옛 판정은 끝에서 둘째(8)였다.
out.centerOnly = dropSlot(mids, high + 91 / 2, 1, null)
// 넘치지 않는 줄(사본 1500px): 고정 HOME(0·91)·VOC(93·91)·공정 Capa 상세(186·134) 앞으로
// 가용설비 현황(128px)을 끈다 — 고정 묶음 바로 뒤(1)다. 옛 판정은 끄는 탭 가운데가 이미 VOC
// 가운데를 지나 2였다.
const short = [45.5, 93 + 45.5, 186 + 67]
const front = dragLeft(-50, 91, 1155 - 128)
out.front = [front.left, front.bound, dropSlot(short, front.left + 64, 1, front.bound)]
out.frontCenterOnly = dropSlot(short, 91 + 64, 1, null)
// 두 끝 사이는 가운데로 센다. 고정 탭이 없으면 앞 끝은 맨 앞(0)이다.
const middle = dragLeft(300, low, high)
out.middle = [middle.left, middle.bound, dropSlot(mids, middle.left + 45.5, 1, middle.bound)]
out.noPin = dropSlot(mids, 0, 0, 'low')
process.stdout.write(JSON.stringify(out))
"""


def test_a_tab_dragged_against_either_end_lands_in_that_end_slot() -> None:
    """끄는 탭이 끝(고정 묶음 바로 뒤·목록 끝)에 묶이면 그 끝 자리다. 가운데만 보면 끄는 탭이 이웃
    탭보다 넓거나 같을 때 끝 자리에 못 놓였다 — 넘친 줄은 맨 끝에 놓을 수 없었고(끝에서 둘째),
    넘치지 않아도 긴 이름 탭을 짧은 이름 탭 앞에 놓을 수 없었다(2026-11-02 반박 검토)."""
    out = _node(_DRAG_BOUND_RUNNER)

    assert out["end"] == [837, "high", 9]
    assert out["centerOnly"] == 8
    assert out["front"] == [91, "low", 1]
    assert out["frontCenterOnly"] == 2
    assert out["middle"] == [300, None, 3]
    assert out["noPin"] == 0
    # 그리기도 그 판정을 쓴다 — 묶은 왼쪽과 닿은 끝을 함께 넘긴다.
    assert "dragLeft(d.x - box.left + list.scrollLeft - d.grab, d.low, high)" in JS
    assert "d.slot = dropSlot(mids, left + d.width / 2, d.pinned, bound)" in JS


_HELD_RELEASE_RUNNER = """
const out = {}
let held = 1
let endedAt = 1000
const step = (type, pointer, now) => {
  const next = heldRelease(held, type, pointer, now)
  held = next.held
  if (next.endedAt !== null) endedAt = next.endedAt
  return [held, next.endedAt]
}
// Esc 로 끌기를 접었다(1000ms) — 포인터 1 은 아직 눌려 있다. 다른 포인터의 놓음은 상관없다.
out.otherPointer = step('pointerup', 2, 1500)
// 손떨림 뒤 1800ms 에 놓았다 — 그 click(1801ms)은 버린다. 접은 시각부터만 세던 옛 판정은
// 버리지 못했다.
out.release = step('pointerup', 1, 1800)
out.click = [dragClick(endedAt, 1801, 400), dragClick(1000, 1801, 400)]
// 놓은 뒤에는 지켜보지 않는다 — 다음 누름의 click 은 고르기다.
out.afterRelease = step('pointerup', 1, 2600)
out.laterClick = dragClick(endedAt, 2600, 400)
// 놓음을 놓쳤다(창 밖에서 놓음) — 같은 포인터의 새 누름이 기다림을 거둔다. 그 누름의 click 은
// 고르기다.
held = 1
endedAt = 1000
out.missed = step('pointerdown', 1, 5000)
out.missedClick = dragClick(endedAt, 5100, 400)
// 포인터 취소 뒤에는 click 이 없다 — 기다림만 거둔다.
held = 1
out.cancel = step('pointercancel', 1, 6000)
out.none = heldRelease(null, 'pointerup', 1, 7000)
process.stdout.write(JSON.stringify(out))
"""


def test_a_drag_cancelled_with_escape_swallows_the_click_of_its_release() -> None:
    """Esc(또는 끄는 중 새 data)로 접은 끌기는 포인터가 아직 눌려 있다 — 그 포인터를 놓을 때의
    click 도 고르기로 보내지 않는다. 접은 시각부터 0.4초만 버리면 손을 떼기 전 작은 움직임 뒤 0.4초
    넘어 놓은 click 이 그 탭으로 화면을 옮겼다(2026-11-02 반박 검토 — 사본 1280: Esc · 3단계 되돌림
    · 0.8초 뒤 놓기 → `/reference_data`)."""
    out = _node(_HELD_RELEASE_RUNNER)

    assert out["otherPointer"] == [1, None]
    assert out["release"] == [None, 1800]
    assert out["click"] == [True, False]
    assert out["afterRelease"] == [None, None]
    assert out["laterClick"] is False
    assert out["missed"] == [None, None]
    assert out["missedClick"] is False
    assert out["cancel"] == [None, None]
    assert out["none"] == {"held": None, "endedAt": None}
    # Esc 와 끄는 중 새 data 는 눌린 포인터를 지켜보게 접고, 포인터 취소·떼어 냄은 그러지 않는다.
    assert "key.stopPropagation()\n        endDrag(false, true)\n" in JS
    assert "if (S.drag && S.endDrag) S.endDrag(false, true)" in JS
    assert "if (own(cancel)) endDrag(false) }" in JS
    end = JS[JS.index("const endDrag = (commit, pressed = false) => {") :]
    assert end.index("S.dragEndAt = Date.now()") < end.index("if (pressed) watchRelease(d.pointer)")
    watch = "for (const type of RELEASE_EVENTS) window.addEventListener(type, S.onRelease, true)"
    assert watch in JS
    cleanup = JS[JS.rindex("return () => {") :]
    assert "stopRelease()" in cleanup


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


_EDGES_RUNNER = """
const out = {
  fits: overflowEdges(0, 355, 355),
  start: overflowEdges(0, 649, 355),
  middle: overflowEdges(140.5, 649, 355),
  end: overflowEdges(294, 649, 355),
  nearEnd: overflowEdges(293.4, 649, 355),
  subpixel: overflowEdges(0, 355.6, 355),
}
process.stdout.write(JSON.stringify(out))
"""


def test_an_overflowing_strip_marks_the_side_that_has_more_tabs() -> None:
    """390px 에서 탭이 여럿이면 목록이 지금 탭 쪽으로 굴러 HOME 등 왼쪽 탭이 화면 밖에 있는데,
    넘친다는 표지가 없어 더 있는 줄 몰랐다(E2E — 목록 scrollWidth 649 / clientWidth 355). 넘치면
    탭이 더 있는 쪽에만 가장자리 흐림과 화살표를 단다 — 굴릴 때·목록 폭이 바뀔 때·data 가 바뀔 때
    다시 본다."""
    out = _node(_EDGES_RUNNER)

    assert out["fits"] == {"start": False, "end": False}
    assert out["start"] == {"start": False, "end": True}
    assert out["middle"] == {"start": True, "end": True}
    assert out["end"] == {"start": True, "end": False}
    assert out["nearEnd"] == {"start": True, "end": False}
    assert out["subpixel"] == {"start": False, "end": False}
    assert "list.addEventListener('scroll', S.onScroll, { passive: true })" in JS
    assert "list.removeEventListener('scroll', S.onScroll)" in JS
    assert "S.resizer.observe(list)" in JS and "S.resizer.disconnect()" in JS
    for side, edge in (("start", "before"), ("end", "after")):
        assert f"nav.classList.toggle('has-more-{side}', more.{side})" in JS
        mask = _rule(f".capa-tabs.has-more-{side} .capa-tabs-list")
        # 접두 없는 `mask-image` 는 Chrome 120 부터라 접두 꼴도 둔다(입장 화면 `.stage.masked`
        # 와 같다).
        assert "\n  mask-image:" in mask and "-webkit-mask-image:" in mask
        assert f".capa-tabs.has-more-{side}::{edge}" in CSS
    marks = _rule(".capa-tabs::before,\n.capa-tabs::after")
    assert "pointer-events: none" in marks and "opacity: 0" in marks
    # 지금 탭을 보이게 굴릴 때도 흐림 폭만큼 띄운다 — 가장자리 탭이 흐림 밑에 깔리지 않게.
    assert "const EDGE_PX = 32" in JS and "black 2rem" in CSS
    assert "list.scrollLeft, list.clientWidth, EDGE_PX)" in JS


_REVEAL_RUNNER = """
const out = {
  // 1024px · 탭 10개 — 목록 689px(내용 988px)가 끝(299)까지 굴러 있고 지금 탭(가용설비
  // 현황)은 맨 끝 838~988 이다. 사이드바를 접었다 펴니 굴린 위치가 0 으로 돌아갔다 — 지금
  // 탭이 오른쪽 밖이다. 끝 너머 값은 브라우저가 끝으로 줄인다.
  expanded: revealScroll(838, 988, 0, 689, 32),
  // 1024 → 390 으로 좁히니 위치 299 그대로 목록이 355px 로 줄었다 — 지금 탭이 오른쪽 밖이다.
  narrowed: revealScroll(838, 988, 299, 355, 32),
  // 이미 흐림 밖에 온전히 보이면 그대로다.
  shown: revealScroll(500, 650, 299, 689, 32),
  // 왼쪽 밖(HOME)은 흐림 폭만큼 띄워 왼쪽 끝으로, 0 아래로는 가지 않는다.
  left: revealScroll(0, 120, 299, 689, 32),
  partly: revealScroll(300, 420, 299, 689, 32),
}
process.stdout.write(JSON.stringify(out))
"""


def test_the_current_tab_is_brought_back_into_view_when_the_strip_width_changes() -> None:
    """탭을 옮길 때만 지금 탭까지 굴려 사이드바를 접었다 펴거나(굴린 위치가 0 으로 돌아간다) 창을
    좁히면(위치 그대로 목록만 준다) 지금 탭이 목록 밖에 남았다(2026-10-30 E2E — 1024px 탭 10개,
    가용설비 현황이 지금 탭). 목록 폭이 바뀔 때도 같은 계산(`revealScroll`)으로 맞춘다. 이미 보이면
    그대로라 data 만 다시 올 때는 사람이 굴려 둔 위치를 두는 것과 같다."""
    out = _node(_REVEAL_RUNNER)

    assert out["expanded"] == 988 - 689 + 32
    assert out["narrowed"] == 988 - 355 + 32
    assert out["shown"] == 299
    assert out["left"] == 0
    assert out["partly"] == 300 - 32
    observer = re.search(r"new ResizeObserver\(\(\) => \{(.*?)\}\)", JS, re.S)
    assert observer is not None
    assert "S.reveal()" in observer.group(1)
    assert observer.group(1).index("S.reveal()") < observer.group(1).index("S.onScroll()")


_FOCUS_RUNNER = """
const ids = ['home', 'plan', 'ref', 'calc']
const MS = 10000
const out = {
  middle: focusAfterClose(ids, 'plan'),
  last: focusAfterClose(ids, 'calc'),
  first: focusAfterClose(ids, 'home'),
  alone: focusAfterClose(['home'], 'home'),
  missing: focusAfterClose(ids, 'gone'),
  // 키보드 누름 뒤 옮긴 화면이 다 섰고 초점이 body 로 빠졌고 다른 입력이 없다 — 돌려준다.
  lost: refocusAfterMove(1000, 990, true, false, 2000, MS),
  sameMs: refocusAfterMove(1000, 1000, true, false, 2000, MS),
  // 옮긴 화면 회차가 아직 돈다 — 기다리던 누름은 잠깐 뒤 보내도 초점은 화면이 다 서야 본다.
  running: refocusAfterMove(1000, 990, false, true, 2500, MS),
  // 회차가 끝내 끝나지 않아도 키보드 누름에서 `ms` 가 지나면 그때 본다.
  overdue: refocusAfterMove(1000, 990, true, true, 11000, MS),
  // 초점이 탭 줄·본문 어딘가에 남았다 — 두기.
  kept: refocusAfterMove(1000, 990, false, false, 2000, MS),
  // 그 뒤 사용자가 키·포인터로 움직였다 — 기다리는 중이어도 그만둔다.
  moved: refocusAfterMove(1000, 1500, true, false, 2000, MS),
  movedWhileRunning: refocusAfterMove(1000, 1500, true, true, 2000, MS),
  // 마우스로 누른 이동이다 — 두기.
  mouse: refocusAfterMove(null, -Infinity, true, false, 2000, MS),
}
process.stdout.write(JSON.stringify(out))
"""


def test_keyboard_focus_stays_on_the_strip_when_a_tab_closes_or_the_screen_moves() -> None:
    """키보드로 탭 × 에서 Enter·Space 를 누르면 숨긴 단추의 초점이 body 로 빠졌다(E2E d16).
    키보드 초점이 있던 탭을 닫으면 숨기기 **전에** 이웃 탭으로 옮긴다 — 서버가 지금 탭을 닫고 옮겨
    가는 이웃과 같은 규칙(오른쪽, 없으면 왼쪽)이다. 키보드로 옮긴 화면이 다 선 뒤 초점이 body 로
    빠졌으면(그 사이 다른 입력이 없을 때만) 지금 탭으로 돌려준다. 기다리던 누름은 옮긴 화면 회차가
    끝나기 전에도 보내므로(`MOVED_GRACE_MS`) 초점은 그 회차가 다 설 때까지 따로 기다린다."""
    out = _node(_FOCUS_RUNNER)

    assert (out["middle"], out["last"], out["first"]) == ("ref", "ref", "plan")
    assert out["alone"] is None and out["missing"] is None
    assert (out["lost"], out["sameMs"], out["overdue"]) == ("focus", "focus", "focus")
    assert out["running"] == "wait"
    assert (out["kept"], out["moved"], out["movedWhileRunning"], out["mouse"]) == (
        "drop",
        "drop",
        "drop",
        "drop",
    )
    close_now = JS[JS.index("const closeNow = (item) => {") :]
    close_now = close_now[: close_now.index("\n  }\n")]
    # 키보드 초점(`:focus-visible`)일 때만 옮긴다 — 마우스로 누른 × 도 초점을 받는데, 그때
    # 옮기면 이웃 탭의 숨은 핀이 `:focus-within` 으로 드러나 남았다(헤드리스 Chrome — 마우스 뒤
    # 이웃 핀 opacity 1).
    assert "item.contains(focused) && focused.matches(':focus-visible')" in close_now
    # 이웃은 보이는 차례(목록 DOM)로 고른다 — 만든 차례(`S.items`)는 고정한 탭이 왼쪽으로 옮긴
    # 차례와 어긋난다.
    assert "[...list.children].filter((other) => !other.hidden)" in close_now
    assert close_now.index("next.__parts.tab.focus(") < close_now.index("item.hidden = true")
    # 키보드 누름(`detail` 0)만 적고, 옮긴 화면이 다 서면(`settle` 이 더 보낼 누름이 없을 때)
    # 돌려줄지 본다.
    assert "if (event.detail === 0) S.keyPressAt = Date.now()" in JS
    settle = JS[JS.index("function settle() {") : JS.index("const appRunning = () => {")]
    assert "else restoreFocus()" in settle
    # 회차가 아직 돌면(`MOVED_GRACE_MS` 로 기다리던 누름을 먼저 보냈을 수 있다) 다 설 때까지
    # 다시 본다.
    restore = JS[JS.index("function restoreFocus() {") :]
    restore = restore[: restore.index("\n  }\n")]
    verdict = "refocusAfterMove(S.keyPressAt, S.inputAt, lost, appRunning(), Date.now(), BUSY_MS)"
    assert verdict in restore
    assert "S.focusTimer = setTimeout(() => restoreFocus(), SETTLE_POLL_MS)" in restore
    assert "clearTimeout(S.focusTimer)" in JS[JS.index("  return () => {") :]
    assert "document.addEventListener(type, S.onInput, true)" in JS
    assert "document.removeEventListener(type, S.onInput, true)" in JS


# ---------------------------------------- 새로 읽은 문서의 공식 복귀 알림(개선 거리 I1)

_RETURN_RUNNER = """
const text = %s
const out = {}
// 띠 CSS 변수 — 따옴표 친 퍼센트 인코딩 글이면 이름, `none`·빈 값·깨진 글이면 빈 글.
out.marks = [
  returnMark(' "%%E3%%80%%8C%%EC%%85%%8B%%EC%%97%%85%%20B%%E3%%80%%8D%%20r8"'),
  returnMark("'%%EA%%B0%%80'"),
  returnMark('none'),
  returnMark(''),
  returnMark('"%%E3%%80"'),
]
// 떠날 때 적을 값 — 떠나는 까닭에 맞는 변수(테마 단추 몫, 새로고침 몫)를 읽고, 이름이 없으면 적지
// 않는다(앞 문서 몫을 지우지 않는다).
const named = '"%%E3%%80%%8C%%EC%%85%%8B%%EC%%97%%85%%20B%%E3%%80%%8D%%20r8"'
out.records = [
  returnRecord(named, named, true),
  returnRecord(named, named, false),
  returnRecord('none', 'none', true),
  // 공식 시나리오의 옛 리비전 — 테마 단추 몫에만 이름이 있다(새로고침은 가정일 때만).
  returnRecord(named, 'none', false),
  returnRecord(named, 'none', true),
]
// 새로 읽은 문서의 알림 — 테마 단추와 새로고침이 다른 글이다. 적어 둔 값이 없거나 꼴이
// 어긋나면 알리지 않는다.
out.notices = [
  returnNotice(out.records[0], text),
  returnNotice(out.records[1], text),
  returnNotice(null, text),
  returnNotice('{', text),
  returnNotice('{"label": ""}', text),
]
process.stdout.write(JSON.stringify(out))
"""


def test_a_reloaded_document_tells_once_that_the_equipment_scenario_went_back_to_official() -> None:
    """테마 단추·새로고침은 새 세션이라 가정 설비 시나리오가 아무 확인 없이 공식으로 돌아갔다(E2E
    1~3회차 — 「셋업 실무 r8 → 운영 일정 r6 공식 v3」, 개선 거리 I1). 띠 CSS 변수에 그 이름이
    실리고(테마 단추 몫은 공식 발행 쌍이 아니면 모두, 새로고침 몫은 가정일 때만), 문서를 떠날 때
    까닭에 맞는 몫을 적어 새로 읽은 문서가 한 번 알린다 — 새 세션마다 알리지 않는다. 공식
    시나리오 옛 리비전을 보던 F5 는 적지 않는다(E2E 10-31)."""
    out = _node(_RETURN_RUNNER % json.dumps(page_tabs.TEXT, ensure_ascii=False))

    assert out["marks"] == ["「셋업 B」 r8", "가", "", "", ""]
    assert [json.loads(record) if record else None for record in out["records"]] == [
        {"label": "「셋업 B」 r8", "cause": "theme"},
        {"label": "「셋업 B」 r8", "cause": "reload"},
        None,
        None,
        {"label": "「셋업 B」 r8", "cause": "theme"},
    ]
    themed, reloaded, *rest = out["notices"]
    assert themed == page_tabs.THEME_RETURN_NOTICE.format(label="「셋업 B」 r8")
    assert reloaded == page_tabs.RETURN_NOTICE.format(label="「셋업 B」 r8")
    assert themed.startswith("테마를 바꾸며") and reloaded.startswith("새로고침해")
    assert rest == ["", "", ""]


def test_the_return_notice_reads_the_header_variable_and_the_theme_switch_mark() -> None:
    """변수 이름은 띠(`app_header`)와, 테마 표지는 테마 단추(`theme_toggle`)와 같은 글이다. 떠날 때
    적는 처리기와 알리기는 문서에 하나다(탭 줄이 다시 마운트돼도 두 번 알리지 않는다)."""
    from capa_simulation.components.app_header import (
        EQUIPMENT_RELOAD_RETURN_VARIABLE,
        EQUIPMENT_RETURN_VARIABLE,
    )
    from capa_simulation.components.theme_toggle import THEME_SWITCH_STORAGE_KEY

    assert f"const RETURN_VARIABLE = '{EQUIPMENT_RETURN_VARIABLE}'" in JS
    assert f"const RELOAD_RETURN_VARIABLE = '{EQUIPMENT_RELOAD_RETURN_VARIABLE}'" in JS
    # 떠날 때 두 몫을 다 읽어 까닭(테마 표지)으로 고른다.
    leave = JS[JS.index("window.addEventListener('pagehide',") :]
    leave = leave[: leave.index("})")]
    assert "style.getPropertyValue(RETURN_VARIABLE)" in leave
    assert "style.getPropertyValue(RELOAD_RETURN_VARIABLE)" in leave
    assert f"const THEME_SWITCH_KEY = '{THEME_SWITCH_STORAGE_KEY}'" in JS
    assert "if (!window.__capaReturnWatch) {" in JS
    assert "window.addEventListener('pagehide'," in JS
    assert "if (!window.__capaReturnChecked) {" in JS
    assert "flash(theme ? 'themed' : 'returned', message," in JS
    # 알리기 전에 떠난 문서의 몫은 지우지 않는다 — 떠날 때 이름이 없으면 적지 않는다.
    assert "if (record !== null) storage.setItem(RETURN_KEY, record)" in JS
    # 탭 줄이 없던 문서(부트스트랩 오류)에서 누른 테마 단추의 표지는 떠날 때 읽히지 않고 남는다 —
    # 새 문서가 처음 볼 때 지우지 않으면 그 문서의 다음 새로고침을 테마 전환 글로 알린다.
    first = JS.index("if (!window.__capaReturnChecked) {")
    checked = JS[first : JS.index("if (!window.__capaReturnWatch) {")]
    assert "window.sessionStorage.removeItem(THEME_SWITCH_KEY)" in checked


def test_the_theme_button_leave_goes_through_the_same_edit_hold() -> None:
    """탭 줄 밖의 떠나기(테마 단추)도 편집표에서 막 손을 뗀 누름이면 그 편집 회차가 돌아올 때까지
    붙든다(개선 거리 I4). 탭 줄이 그릴 때마다 붙들기 처리를 문서에 걸고 내려갈 때 걷는다 — 누를 때
    편집표 포커스를 적고(`press`), 막 손을 뗀 누름이 아니면 곧바로, 아니면 탭 누름과 같은 붙듦
    (`S.hold` — `release` 가 `holdVerdict` 로 놓는다)에 싣는다."""
    gate = JS[JS.index("const gate = {") : JS.index("window.__capaLeaveGate = gate")]
    assert "press: () => { S.pressFromGrid = S.gridFocused }" in gate
    assert gate.index("if (fresh())") < gate.index("S.hold = { id: null")
    assert "release()" in gate
    assert "if (window.__capaLeaveGate === gate) delete window.__capaLeaveGate" in JS
    # 붙든 테마 누름은 탭이 아니다 — 놓을 때 탭 표지를 건드리지 않고 부른 쪽을 잇는다.
    release = JS[JS.index("function release() {") :]
    release = release[: release.index("\n  }\n")]
    assert "const held = S.items.get(hold.id)" in release and "hold.go()" in release


_UNLOAD_RUNNER = """
// 창 · 문서 대역 — 걸린 `beforeunload` 처리기를 모으고, 떠날 때 CSS 변수 값을 돌려준다.
const fakeWindow = (value, extra) => {
  const win = {
    handlers: [],
    addEventListener(type, fn) { this.handlers.push([type, fn]) },
    getComputedStyle(element) {
      if (value === null) throw new Error('detached')
      return { getPropertyValue: (name) => (name === UNSAVED_VARIABLE ? value : '') }
    },
  }
  return Object.assign(win, extra || {})
}
const leave = (win) => {
  const event = {
    prevented: false,
    returnValue: undefined,
    preventDefault() { this.prevented = true },
  }
  for (const [type, fn] of win.handlers) if (type === 'beforeunload') fn(event)
  return [event.prevented, event.returnValue === undefined ? null : event.returnValue]
}
const doc = { documentElement: {} }
const out = {}
const cases = {
  clean: [''],
  none: ['0'],
  dirty: ['1'],
  spaced: [' 1 '],
  themeAsked: ['1', { [RELOAD_ASKED]: true }],
  themeSync: ['1', { __capaThemeReloading: true }],
  detached: [null],
}
for (const [name, [value, extra]] of Object.entries(cases)) {
  const win = fakeWindow(value, extra)
  installUnloadGuard(win, doc)
  out[name] = leave(win)
}
// 처리기는 문서에 하나다 — 탭 줄이 다시 마운트돼 두 번 불러도 하나만 건다.
const twice = fakeWindow('1')
installUnloadGuard(twice, doc)
installUnloadGuard(twice, doc)
out.handlers = twice.handlers.map(([type]) => type)
// 표지는 떠나는 순간 읽는다 — 건 뒤에 편집이 생기거나 사라져도 그때의 값으로 묻는다.
let live = ''
const late = fakeWindow('')
late.getComputedStyle = () => ({ getPropertyValue: () => live })
installUnloadGuard(late, doc)
live = '1'
out.lateDirty = leave(late)
live = ''
out.lateClean = leave(late)
process.stdout.write(JSON.stringify(out))
"""


def _unload_block() -> str:
    match = re.search(r"// <tabs-unload>\n(?P<body>.*?)\n// </tabs-unload>", JS, re.S)
    assert match, "page_tabs.js 에 // <tabs-unload> 구획이 없습니다"
    return match.group("body")


def test_a_reload_or_tab_close_asks_only_while_there_are_unsaved_edits() -> None:
    """새로고침·브라우저 탭 닫기는 새 세션이라 저장 전 설비 편집·적용 전 편집이 말없이 사라졌다
    (E2E #101·#119 — 테마 단추는 묻는데 새로고침은 묻지 않았다, 개선 거리 I3). 탭 줄 JS 가 문서에
    `beforeunload` 처리기를 하나 걸고, 떠나는 순간 저장 안 함 표지(테마 단추와 같은 CSS 변수)가
    '1' 일 때만 브라우저 확인 창을 띄운다. 편집이 없으면 묻지 않는다. 테마 단추가 이미 물은 새로
    읽기와 열릴 때의 테마 키 맞추기 새로고침도 묻지 않는다. 표지를 못 읽으면 묻지 않는다."""
    out = _node(_UNLOAD_RUNNER, prelude=_unload_block())

    assert out["clean"] == [False, None]
    assert out["none"] == [False, None]
    assert out["dirty"] == [True, ""]
    assert out["spaced"] == [True, ""]
    assert out["themeAsked"] == [False, None]
    assert out["themeSync"] == [False, None]
    assert out["detached"] == [False, None]
    assert out["handlers"] == ["beforeunload"]
    assert out["lateDirty"] == [True, ""]
    assert out["lateClean"] == [False, None]


def test_the_unload_guard_reads_the_theme_button_marker_and_is_installed_by_the_strip() -> None:
    """확인 창의 표지는 테마 단추가 읽는 CSS 변수(`unsaved_edits_marker` — 탭 점과 한 벌의 판정)와
    같은 이름이고, 테마 단추가 새로 읽기 직전에 다는 창 표지도 같은 이름이다 — 둘이 어긋나면 테마
    단추가 물은 뒤 브라우저가 한 번 더 묻거나, 편집이 있는데 묻지 않는다. 탭 줄이 그릴 때 문서에
    건다(처리기는 문서에 하나 — `installUnloadGuard` 가 거른다)."""
    from capa_simulation.components.theme_toggle import (
        RELOAD_ASKED_FLAG,
        UNSAVED_EDITS_CSS_VARIABLE,
    )

    block = _unload_block()
    assert f"const UNSAVED_VARIABLE = '{UNSAVED_EDITS_CSS_VARIABLE}'" in block
    assert f"const RELOAD_ASKED = '{RELOAD_ASKED_FLAG}'" in block
    assert "win.addEventListener('beforeunload'," in block
    body = JS[JS.index("export default function (component) {") :]
    assert body.count("installUnloadGuard(window, document)") == 1
    # 처리기는 컴포넌트가 내려가도 걷지 않는다(떠날 때의 표지를 그때 읽는다).
    cleanup = body[body.rindex("  return () => {") :]
    assert "beforeunload" not in cleanup


_GATE_RUNNER = """
(() => {
  // 시계·타이머 대역 — `advance(t)` 가 t 까지 걸린 타이머를 차례로 부른다.
  let now = 0
  Date.now = () => now
  const timers = []
  const setTimeout = (fn, ms) => {
    timers.push({ fn, at: now + (ms || 0), live: true })
    return timers.length
  }
  const clearTimeout = (id) => { if (id && timers[id - 1]) timers[id - 1].live = false }
  const advance = (to) => {
    for (;;) {
      const due = timers.filter((t) => t.live && t.at <= to).sort((a, b) => a.at - b.at)[0]
      if (!due) break
      due.live = false
      now = Math.max(now, due.at)
      due.fn()
    }
    now = to
  }
  let scriptState = 'notRunning'
  const document = { querySelector: () => ({ getAttribute: () => scriptState }) }
  const window = {}
  %(constants)s
  const mount = (S, log) => {
    const setAttr = (element, name, value) => { if (element) element[name] = value }
    const busy = (item) => setAttr(item.__parts.tab, 'aria-busy', 'true')
    const sendSelect = (item) => log.push('tab:' + item.dataset.id)
    %(slice)s
    return { gate, select }
  }
  const strip = (log) => {
    const parts = { tab: {}, close: { hidden: false } }
    const tab = { dataset: { id: 'b' }, hidden: false, __parts: parts }
    const S = {
      items: new Map([['b', tab]]), queue: createSelectQueue(), data: { active: 'a' },
      editAt: -Infinity, gridFocused: false, pressFromGrid: false, hold: null, holdTimer: 0,
    }
    return { S, tab, ...mount(S, log) }
  }
  const theme = (log) => () => log.push('theme')
  const out = {}

  // 편집표와 상관없는 누름 — 곧바로 잇는다.
  let log = []
  let T = strip(log)
  T.gate.press()
  T.gate.go(theme(log))
  out.fresh = [log.slice(), T.S.hold]

  // 사이드바 링크 — 붙들면 참이고 누른 쪽이 기본 동작을 막는다. 아니면 거짓이고 그대로 간다.
  timers.length = 0; now = 1000; log = []; T = strip(log)
  out.linkFresh = [T.gate.hold(theme(log)), log.slice()]
  T.S.editAt = now
  out.linkHeld = [T.gate.hold(theme(log)), log.slice()]
  advance(now + 500)
  out.linkLate = log.slice()

  // 칸 편집기에 쓰는 중 — 편집 회차가 도는 동안 붙들고, 끝나고 새 data 가 오면 잇는다.
  timers.length = 0; now = 1000; log = []; T = strip(log)
  T.S.gridFocused = true
  T.S.editAt = now
  T.gate.press()
  T.gate.go(theme(log))
  out.typingHeld = [log.slice(), T.S.hold ? ['held', T.S.hold.id] : null]
  scriptState = 'running'
  advance(2000)
  out.typingWhileRunning = log.slice()
  scriptState = 'notRunning'
  T.S.data = { active: 'a' }
  advance(2100)
  out.typingAfterRun = [log.slice(), T.S.hold, T.tab.__parts.tab['aria-busy'] || null]

  // 막 Enter 한 직후(포커스는 이미 단추) — 회차가 아직 돌지 않아도 0.4초는 기다린다.
  timers.length = 0; now = 10000; log = []; T = strip(log)
  T.S.editAt = now - 1000
  T.gate.press()
  T.gate.go(theme(log))
  advance(10300)
  out.enterEarly = log.slice()
  advance(10500)
  out.enterLate = log.slice()

  // 붙든 사이 탭을 누르면 마지막 누름(탭)만 남는다 — 테마 누름은 버려진다.
  timers.length = 0; now = 20000; log = []; T = strip(log)
  T.S.gridFocused = true
  T.S.editAt = now
  T.gate.press()
  T.gate.go(theme(log))
  T.S.pressFromGrid = T.S.gridFocused
  T.select(T.tab)
  T.S.data = { active: 'a' }
  advance(21000)
  out.dropped = log.slice()

  // 회차가 끝나지 않아도 붙들기는 `BUSY_MS` 에서 놓는다.
  timers.length = 0; now = 30000; log = []; T = strip(log)
  T.S.gridFocused = true
  T.S.editAt = now
  T.gate.press()
  T.gate.go(theme(log))
  scriptState = 'running'
  advance(30000 + BUSY_MS - 200)
  out.capEarly = log.slice()
  advance(30000 + BUSY_MS + 200)
  out.capLate = log.slice()
  process.stdout.write(JSON.stringify(out))
})()
"""


def test_the_leave_gate_holds_a_theme_press_until_the_edit_run_returns() -> None:
    """테마 단추가 지나는 붙들기(`window.__capaLeaveGate`)를 탭 줄 JS 그대로 node 에서 돌린다(개선
    거리 I4). 편집표와 상관없는 누름은 곧바로 잇고, 칸에 쓰는 중이거나 막 Enter 한 직후의 누름은
    편집 회차가 돌아올 때까지(최소 0.4초, 최대 `BUSY_MS`) 붙든다. 붙든 사이 탭을 누르면 테마
    누름은 버려지고 탭 누름만 잇는다."""
    lines = [
        re.search(rf"^const {name} = .+$", JS, re.M)
        for name in ("BUSY_MS", "SETTLE_POLL_MS", "HOLD_MS", "EDIT_MS", "APP_ROOT")
    ]
    constants = "\n".join(line.group(0) for line in lines if line is not None)
    assert len(constants.splitlines()) == len(lines)
    start = JS.index("  const appRunning = () => {")
    end = JS.index("  window.__capaLeaveGate = gate")
    runner = _GATE_RUNNER % {"constants": constants, "slice": JS[start:end]}

    out = _node(runner)

    assert out["fresh"] == [["theme"], None]
    assert out["linkFresh"] == [False, []]
    assert out["linkHeld"] == [True, []]
    assert out["linkLate"] == ["theme"]
    assert out["typingHeld"] == [[], ["held", None]]
    assert out["typingWhileRunning"] == []
    assert out["typingAfterRun"] == [["theme"], None, None]
    assert out["enterEarly"] == []
    assert out["enterLate"] == ["theme"]
    assert out["dropped"] == ["tab:b"]
    assert out["capEarly"] == []
    assert out["capLate"] == ["theme"]


def test_a_sidebar_link_press_right_after_a_table_edit_waits_for_its_run() -> None:
    """표 칸을 쓰다 사이드바 링크를 터치로 누르면 초점이 빠지며 출납이 곧바로 나가고, 그 회차가 지금
    화면 주소로 돌아 링크 이동을 덮었다(2026-11-07 E2E — 톡 3/3 이동 안 함). 탭 누름과 같은 붙들기를
    지난 뒤 같은 링크를 다시 누른다 — 상한 거름은 다시 누를 때 한 번만 돈다(열기 표지를 적는다)."""
    on_link = JS[
        JS.index("S.onLink = (event) => {") : JS.index(
            "document.addEventListener('click', S.onLink, true)"
        )
    ]
    assert on_link.index("S.linkReplay === href") < on_link.index("refusal(")
    assert "gate.hold(() => replayLink(href))" in on_link
    held = on_link[on_link.index("gate.hold(") : on_link.index("refusal(")]
    assert "event.preventDefault()" in held and "event.stopPropagation()" in held
    # 누르는 순간 표에 있던 초점을 적는다 — 링크 click 때는 이미 표를 떠났다.
    on_input = JS[JS.index("S.onInput = (event) => {") : JS.index("S.onInput, true)")]
    assert "closest(PAGE_LINK)" in on_input and "S.pressFromGrid = S.gridFocused" in on_input
    # 다시 누를 때는 그 사이 다시 지어졌을 수 있는 링크를 주소로 찾는다.
    replay = JS[JS.index("const replayLink = (href) => {") : JS.index("S.onLink = (event) => {")]
    assert "querySelectorAll(PAGE_LINK)" in replay
    assert "S.linkReplay = href" in replay and "link.click()" in replay


def test_the_equipment_master_grid_and_its_side_panels_count_as_edit_tables() -> None:
    """떠나기 붙들기가 편집표로 보는 Components v2 칸은 설비 마스터 표와 오른쪽 칸의 key, 기준 정보
    범용 편집 그리드의 호스트 key, 시나리오 목록 표 셋이다 — 그 모듈의 key 를 바꾸면 이 묶음도 같이
    바뀌어야 한다(`page_tabs` 는 읽을 때 컴포넌트를 등록하는 그 모듈을 불러오지 않는다). 탭 줄
    data 의 `grids` 로 실려 JS 가 그릴 때마다 선택자를 다시 짓는다."""
    from capa_simulation.components import equipment_master_grid as emg
    from capa_simulation.components.scenario_list_state import MOUNT_KEYS
    from capa_simulation.page_tabs_state import INITIAL_STRIP
    from capa_simulation.reference_grid_keys import GRID_HOST

    assert set(page_tabs.EDIT_HOST_KEYS) == {
        emg.GRID_KEY,
        *(emg.side_key(panel) for panel in emg.SIDE_PANELS),
        GRID_HOST,
        *MOUNT_KEYS,
    }
    assert emg.LOADER_KEY not in page_tabs.EDIT_HOST_KEYS
    data = page_tabs.tabs_data(
        INITIAL_STRIP,
        active=INITIAL_STRIP.paths[0],
        hrefs={},
        marks={},
        leave="",
        epoch=1,
        notice=None,
    )
    assert data["grids"] == list(page_tabs.EDIT_HOST_KEYS)
    assert "S.gridSelector = gridSelector(GRID, data.grids)" in JS
    assert "node.closest(S.gridSelector)" in JS
    assert "node.closest(GRID)" not in JS


_EDIT_HOST_RUNNER = """
(() => {
  let now = 0
  Date.now = () => now
  const timers = []
  const setTimeout = (fn, ms) => {
    timers.push({ fn, at: now + (ms || 0), live: true })
    return timers.length
  }
  const clearTimeout = (id) => { if (id && timers[id - 1]) timers[id - 1].live = false }
  const advance = (to) => {
    for (;;) {
      const due = timers.filter((t) => t.live && t.at <= to).sort((a, b) => a.at - b.at)[0]
      if (!due) break
      due.live = false
      now = Math.max(now, due.at)
      due.fn()
    }
    now = to
  }
  let scriptState = 'notRunning'
  const listeners = []
  const document = {
    querySelector: () => ({ getAttribute: () => scriptState }),
    addEventListener: (type, fn) => listeners.push([type, fn]),
  }
  const window = {}
  %(constants)s
  // DOM 대역 — `closest` 는 그 칸이나 조상이 맞는 선택자 조각(쉼표로 가른 것)이
  // 하나라도 있으면 맞는다.
  const node = (...marks) => ({
    closest: (selector) =>
      selector.split(',').some((part) => marks.includes(part.trim())) ? {} : null,
  })
  const fire = (type, target) => {
    for (const [kind, fn] of listeners) if (kind === type) fn({ type, target })
  }
  const mount = (S, log) => {
    const setAttr = (element, name, value) => { if (element) element[name] = value }
    const busy = (item) => setAttr(item.__parts.tab, 'aria-busy', 'true')
    const sendSelect = (item) => log.push('tab:' + item.dataset.id)
    %(slice)s
    if (!S.onEdit) {
%(edit)s
    }
    return { gate }
  }
  // 칸 편집기에 쓰는 중(Enter 전) 테마 단추를 누른다 — 문서 capture 단계에서 보면
  // 그림자 DOM 칸 편집기의 focusin·keydown 대상은 그림자 호스트다. 누르는 순간
  // (pointerdown) 붙들기에 편집표 포커스를 적고, 초점이 단추로 옮긴 뒤 놓는다. 편집
  // 회차가 돌고 끝나 새 data 가 오면 그때 잇는다.
  const press = (grids, target) => {
    timers.length = 0; listeners.length = 0; now = 1000; scriptState = 'notRunning'
    const log = []
    const S = {
      items: new Map(), queue: createSelectQueue(), data: { active: 'a', grids },
      editAt: -Infinity, gridFocused: false, pressFromGrid: false, hold: null, holdTimer: 0,
      gridSelector: gridSelector(GRID, grids),
    }
    const T = mount(S, log)
    fire('focusin', target)
    fire('keydown', target)
    now = 7000
    T.gate.press()
    fire('focusin', node())
    T.gate.go(() => log.push('theme'))
    const at = log.slice()
    scriptState = 'running'
    advance(7100)
    const running = log.slice()
    scriptState = 'notRunning'
    S.data = { ...S.data }
    advance(7200)
    return [at, running, log.slice()]
  }
  const hosts = ['equipment_grid_table', 'equipment_grid_side_detail']
  const out = {}
  out.gridHost = press(hosts, node('.st-key-equipment_grid_table'))
  out.sideHost = press(hosts, node('.st-key-equipment_grid_side_detail'))
  out.withoutHosts = press(undefined, node('.st-key-equipment_grid_table'))
  out.otherHost = press(hosts, node('.st-key-equipment_grid_loader'))
  out.glide = press(hosts, node('.gdg-clip-region'))
  out.selector = gridSelector('.base', ['equipment_grid_table', 'a b', 'x"]', 3, ''])
  process.stdout.write(JSON.stringify(out))
})()
"""


def test_a_theme_press_while_typing_in_the_equipment_master_grid_waits_for_the_edit() -> None:
    """설비 마스터 표(그림자 DOM Components v2)의 칸 편집기에 쓰는 중(Enter 전) 누른 테마
    단추는 그 편집 회차가 돌아올 때까지 붙든다(E2E 결함 — 문서 capture 단계 대상이 그림자
    호스트로 바뀌어 glide 격자 선택자에 들지 않았다. 누름이 회차 왕복보다 짧으면 저장 안 함
    표지가 서기 전이라 확인 없이 새로 읽어 친 글이 사라졌다). data `grids` 의 key 칸
    (`.st-key-<key>`)으로 알아본다 — 그 key 가 없으면 붙들지 않는 것이 결함의 꼴이다. glide
    격자는 그대로 붙들고, 묶음 밖 칸(불러오기)은 붙들지 않는다."""
    lines = [
        re.search(rf"^const {name} = .+$", JS, re.M)
        for name in ("GRID", "BUSY_MS", "SETTLE_POLL_MS", "HOLD_MS", "EDIT_MS", "APP_ROOT")
    ]
    constants = "\n".join(line.group(0) for line in lines if line is not None)
    assert len(constants.splitlines()) == len(lines)
    start = JS.index("  const appRunning = () => {")
    end = JS.index("  window.__capaLeaveGate = gate")
    edit_start = JS.index("    const inGrid = (node) =>")
    listen = "    for (const type of ['focusin', 'keydown', 'paste', 'cut', 'input'])"
    edit_end = JS.index(listen, edit_start)
    runner = _EDIT_HOST_RUNNER % {
        "constants": constants,
        "slice": JS[start:end],
        "edit": JS[edit_start:edit_end]
        + listen
        + " document.addEventListener(type, S.onEdit, true)",
    }

    out = _node(runner)

    assert out["gridHost"] == [[], [], ["theme"]]
    assert out["sideHost"] == [[], [], ["theme"]]
    assert out["glide"] == [[], [], ["theme"]]
    assert out["withoutHosts"][0] == ["theme"]
    assert out["otherHost"][0] == ["theme"]
    assert out["selector"] == ".base, .st-key-equipment_grid_table"
