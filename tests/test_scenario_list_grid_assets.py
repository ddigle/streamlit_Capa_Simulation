# Purpose: 시나리오 목록 표 자산 — 상태 값 하나 · 색 없음 · 순수 구획 · 가짜 DOM 손짓을 잰다.
# ruff: noqa: E501

"""`components/scenario_list_grid_assets/`. AppTest 는 그 JS 를 못 돌린다 — 순수 구획은 떼어
돌리고, 손짓(칸 편집 · 키 · 끌기 · 한글 조합 · 회차가 돌아오는 때)은 파일 전체를 작은 가짜 DOM 에
올려 본다. 실제 폭 · 그림자 DOM · 풍선은 사본 앱 브라우저로 잰다(`scripts/check_deploy_screens.py`
의 `scenario_list_grid`)."""

from __future__ import annotations

import json
import re
from typing import Any

from js_runner import run_js_json

from capa_simulation.components import grid_shared
from capa_simulation.components import scenario_list_grid as grid
from capa_simulation.services.scenario_list_edits import move_before

ASSETS = grid._ASSETS
OWN_JS = (ASSETS / "list.js").read_text(encoding="utf-8")
OWN_CSS = (ASSETS / "list.css").read_text(encoding="utf-8")
JS = grid.registered_js()
CSS = grid.registered_css()
_SECTIONS = ("grid-nav", "grid-outbox", "list-move", "list-head", "list-ime")
_MOUNT_HEAD = "export default function (component) {"


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"// <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(payload: dict[str, Any], runner: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = run_js_json(
        source + runner, what="시나리오 목록 표 JS", stdin=json.dumps(payload)
    )
    return result


# ---------------------------------------------------------------- 자산 글


def test_the_table_sends_one_state_value_and_no_trigger() -> None:
    """브라우저 → 서버는 상태 값 `outbox` 하나다 — 트리거는 다음 트리거에 덮여 잃는다."""
    assert grid.STATE_NAMES == {"outbox"} and grid.TRIGGER_NAMES == set()
    assert set(re.findall(r"S\.setState\('(\w+)'", OWN_JS)) == grid.STATE_NAMES
    assert "setTriggerValue" not in OWN_JS and "setTrigger" not in OWN_JS


def test_colours_come_from_the_palette_and_text_goes_in_as_text() -> None:
    """등록 CSS 에 색이 없고(테마를 따라오지 않는다) 데이터 글은 textContent 로만 넣는다."""
    used = set(re.findall(r"var\(--emg-([a-z-]+)", OWN_CSS))
    assert used <= set(grid_shared.grid_palette()), used
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", OWN_CSS)
    assert "rgb(" not in OWN_CSS and "rgba(" not in OWN_CSS
    assert "/*" not in OWN_CSS and "position: fixed" not in OWN_CSS
    assert "innerHTML" not in OWN_JS and "insertAdjacentHTML" not in OWN_JS
    assert "localStorage" not in OWN_JS


def test_the_shared_fragments_come_first_and_a_folded_row_keeps_its_height() -> None:
    assert CSS.endswith(OWN_CSS) and JS.endswith(OWN_JS)
    assert CSS.index(".emg-c.is-changed {") < CSS.index(".sgl-tools {")
    # 편집 줄은 잘리지 않게 그리고, 건너뛰는 줄의 크기는 세로 한 축만 잡는다(가로는 줄 폭을 따른다).
    assert "contain-intrinsic-block-size: auto 34px;" in OWN_CSS
    assert "contain-intrinsic-size" not in OWN_CSS
    assert re.search(r"\.is-editing-row \{\s*content-visibility: visible;", OWN_CSS)
    assert re.search(r"dd\.sgl-memo \{[^}]*-webkit-line-clamp: 3;", OWN_CSS)
    # 줄 봉쇄 안에서 잘리지 않게 칸 윤곽은 안쪽으로 그린다.
    assert re.search(r"\.sgl-row \.emg-cb:focus-visible \{[^}]*outline-offset: -2px;", OWN_CSS)


def test_a_long_name_does_not_widen_the_table() -> None:
    """표 최소 폭은 칸 합이다 — `max-content` 면 긴 이름 한 줄이 그려지는 순간 모든 줄의 값 칸이
    밀린다(`content-visibility` 라 그 줄이 화면에 들어올 때에야 정해진다). 이름 칸은 말줄임이다."""
    assert "max-content" not in OWN_CSS
    widths = {
        name: int(value)
        for name, value in re.findall(r"\.sgl-w-(\w+) \{\n\s*width: (\d+)px", OWN_CSS)
    }
    scenarios = re.search(r"\.sgl-scenarios \.sgl-table \{\s*min-width: (\d+)px;", OWN_CSS)
    revisions = re.search(r"\.sgl-revisions \.sgl-table \{\s*min-width: (\d+)px;", OWN_CSS)
    assert scenarios and int(scenarios[1]) == (
        widths["grip"]
        + widths["place"]
        + 180
        + widths["latest"]
        + widths["official"]
        + widths["updated"]
    )
    assert revisions and int(revisions[1]) == widths["no"] + 120 + widths["status"]
    # 칸 너비가 글자에 끌려 늘지 않는다.
    assert re.search(r"\.sgl-w-name \{[^}]*flex: 1 1 0;", OWN_CSS)
    assert re.search(r"\.sgl-table \.emg-row \{\s*width: 100%;", OWN_CSS)
    # 저장 전 변경의 묶음 머리 이름도 칸 안에서 접힌다.
    assert re.search(r"\.sgl-changes \.emg-link \{[^}]*overflow-wrap: anywhere;", OWN_CSS)


def test_the_keyboard_sees_the_focused_cell_and_a_blocked_open_row_keeps_its_line() -> None:
    # 붙은 머리(34px) 밑으로 초점 칸이 들어가지 않는다.
    assert re.search(r"\.sgl-box \{[^}]*scroll-padding-top: 34px;", OWN_CSS)
    # 연 줄 막대가 막힘 윤곽을 덮지 않는다 — 두 그림자를 함께 싣는다.
    blocked = re.search(
        r"\.sgl-row\.is-open \.sgl-w-name\.is-error \{\s*box-shadow: ([^;]+);", OWN_CSS
    )
    assert blocked
    assert "var(--emg-accent)" in blocked[1] and "var(--emg-error-line)" in blocked[1]


def test_many_revisions_leave_the_action_row_inside_the_panel() -> None:
    """리비전 표가 패널 높이를 다 쓰면 작업 줄이 패널 스크롤 아래로 숨는다(UI-LAY-03) — 표 높이
    상한을 패널 상한보다 작업 줄 · 값 줄 몫만큼 낮춘다."""
    from capa_simulation.components import side_panel

    rule = re.search(
        r"\.sgl-revisions \.sgl-box \{\s*max-height: max\((\d+)px, calc\(100vh - (\d+)px\)\);",
        OWN_CSS,
    )
    assert rule
    floor, reserve = int(rule[1]), int(rule[2])
    # 머리 + 세 줄은 늘 보인다.
    assert floor == 34 * 4
    # 인쇄에는 상한이 없다 — 칸 상한보다 특이도가 높아 따로 푼다.
    assert re.search(
        r"@media print \{.*?\.sgl-revisions \.sgl-box \{\s*max-height: none;", OWN_CSS, re.S
    )
    # 패널 상한(100vh − 붙는 높이 − 예비) 안에 값 줄 · 작업 줄 · 보관 몫 260px 이 남는다.
    panel_reserve = side_panel.SIDE_TOP_FALLBACK_PX + side_panel.SIDE_BODY_RESERVE_PX
    assert reserve - panel_reserve >= 260


def test_column_widths_fit_their_heads() -> None:
    """칸 폭은 머리 글자(굵은 12px, 양옆 여백 8)가 다 드는 폭 아래로 두지 않는다 — 좁은 창에서는 표
    안에서만 옆으로 민다."""
    heads = dict(re.findall(r"\{ key: '(\w+)', head: '([^']*)'", OWN_JS))
    widths = {
        name: int(value)
        for name, value in re.findall(r"\.sgl-w-(\w+) \{\n\s*width: (\d+)px", OWN_CSS)
    }
    assert {"place", "latest", "official", "updated", "no", "status", "grip"} <= set(widths)
    for name, width in widths.items():
        assert width >= len(heads.get(name, "")) * 12 + 16, name
    assert "min-width: 180px" in OWN_CSS and "min-width: 120px" in OWN_CSS


# ---------------------------------------------------------------- 순수 구획


def test_the_tools_line_is_as_tall_as_the_side_head() -> None:
    """두 표 머리의 윗선이 같다 — 왼쪽 작업 줄 높이 + 아래 간격이 오른쪽 칸 머리 높이다. 재 보면
    마운트 · 표 틀에 위 여백이 없어 차이는 이 둘뿐이다(창 폭 · 사이드바 · 테마와 무관). 작업 줄이
    단추보다 낮게 적히면 `min-height` 가 듣지 않아 합이 어긋난다."""
    from capa_simulation.components import side_panel

    tools = re.search(
        r"\.sgl-tools \{[^}]*min-height: (\d+)px;[^}]*margin-bottom: (\d+)px;", OWN_CSS
    )
    assert tools
    assert int(tools[1]) + int(tools[2]) == side_panel.SIDE_HEAD_PX
    # 맞춤이 지키는 간격 하한은 이 CSS 값이다 — 어긋나면 머리 맞춤이 CSS 와 다른 간격을 만든다.
    floor = re.search(r"const TOOLS_GAP = (\d+)", OWN_JS)
    assert floor and floor[1] == tools[2]
    small = re.search(r"\.emg-btn\.is-small \{\s*height: (\d+)px;", CSS)
    assert small and int(small[1]) == int(tools[1])
    assert "button('emg-btn is-small'" in OWN_JS
    # 두 표 머리 높이는 한 규칙이고, 표 틀 · 마운트에 머리를 내리는 여백을 두지 않는다.
    assert re.search(r"\.sgl-head \{\s*height: 34px;", OWN_CSS)
    assert ".sgl-root" not in OWN_CSS
    assert not re.search(r"\.sgl-box \{[^}]*\n\s*(margin|padding)", OWN_CSS)


_HEAD_FIT_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({ fits: input.cases.map((item) => headFit(...item)) }))
"""


def _head_fits(cases: list[list[Any]]) -> list[dict[str, Any]]:
    fits: list[dict[str, Any]] = _node({"cases": cases}, _HEAD_FIT_RUNNER, _sections())["fits"]
    return fits


def test_the_two_heads_meet_at_the_taller_one() -> None:
    """머리는 두 쪽 가운데 높은 쪽에 맞춘다. 오른쪽이 높으면 간격이 늘고, 작업 줄이 접혀 왼쪽이 높으면
    간격으로는 왼쪽을 올릴 수 없어 오른쪽 본문을 내린다. 맞출 짝이 없으면(접힘 · 쌓임) CSS 값이다."""
    tools = {"right": 700, "height": 30}
    wrapped = {"right": 700, "height": 66}
    one = {"left": 720, "top": 200, "height": 28}
    two = {"left": 720, "top": 200, "height": 59.5}
    cases = [
        [tools, one, {"top": 242}, 0],
        [tools, two, {"top": 273.5}, 0],
        [tools, {"left": 0, "top": 0, "height": 0}, {"top": 0}, 0],
        [tools, {"left": 20, "top": 572, "height": 28}, {"top": 614}, 0],
        # 작업 줄만 접힘 — 창 916 ~ 948 에 칸 폭을 저장해 둔 꼴. 66 + 12 = 78 인데 오른쪽 머리는 42 다.
        [wrapped, one, {"top": 242}, 0],
        # 둘 다 접혀도 간격을 CSS 값 밑으로 붙이지 않고 모자란 만큼만 내린다.
        [wrapped, two, {"top": 273.5}, 0],
        [{"right": 700, "height": 102}, two, {"top": 273.5}, 0],
        # 오른쪽 머리가 더 높아 내릴 일이 없다.
        [wrapped, {"left": 720, "top": 200, "height": 122.5}, {"top": 336.5}, 0],
    ]
    assert _head_fits(cases) == [
        {"gap": 12, "push": 0},
        {"gap": 43.5, "push": 0},
        {"gap": None, "push": 0},
        {"gap": None, "push": 0},
        {"gap": 12, "push": 36},
        {"gap": 12, "push": 4.5},
        {"gap": 12, "push": 40.5},
        {"gap": 70.5, "push": 0},
    ]


def test_the_head_fit_lands_both_tables_on_one_line() -> None:
    """어떤 줄 수 조합이든 왼쪽 머리 위 끝과 오른쪽 머리 위 끝이 같고, 이미 내려 둔 상태에서 다시
    재도 같은 답이다(내린 값을 머리 높이로 잘못 읽어 회차마다 쌓이지 않는다)."""
    top = 200.0
    cases: list[list[Any]] = []
    for tools_height in (30, 66, 102):
        for choice_height in (28, 59.5, 91, 122.5):
            right_head = choice_height + 14
            tools = {"right": 700, "height": tools_height}
            choice = {"left": 720, "top": top, "height": choice_height}
            cases.append([tools, choice, {"top": top + right_head}, 0])
    fits = _head_fits(cases)
    for case, fit in zip(cases, fits, strict=True):
        tools, choice, body, _ = case
        assert tools["height"] + fit["gap"] == body["top"] + fit["push"] - choice["top"]
        assert fit["gap"] >= 12 and fit["push"] >= 0
    again = [
        [tools, choice, {"top": body["top"] + fit["push"]}, fit["push"]]
        for (tools, choice, body, _), fit in zip(cases, fits, strict=True)
    ]
    assert _head_fits(again) == fits


_PURE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const out = {}
out.moves = input.moves.map(([order, id, before]) => moveBefore(order, id, before))
out.applied = applyMoves(['a', 'b', 'c', 'd'], [{ id: 'd', before: 'a' }, { id: 'a', before: null }])
out.place = input.place.map(([order, id, place]) => beforeForPlace(order, id, place))
out.step = input.step.map(([order, id, step]) => {
  const before = beforeForStep(order, id, step)
  return before === undefined ? 'END' : before
})
out.slot = input.slot.map(([y, top, height, count]) => slotFromY(y, top, height, count))
out.slotBefore = input.slotBefore.map(([order, id, slot]) => beforeForSlot(order, id, slot))
out.parse = input.parse.map(parsePlace)
out.composing = [
  composingKey({ isComposing: true }), composingKey({ keyCode: 229 }), composingKey({ keyCode: 13 }),
  remembersEnter({ isComposing: true, code: 'Enter' }), remembersEnter({ isComposing: true, code: 'KeyA' }),
  remembersEnter({ code: 'Enter' }),
]
out.typed = input.typed.map(([key, ctrl, meta, alt]) => typedStart(key, ctrl, meta, alt))
process.stdout.write(JSON.stringify(out))
"""


def test_the_pure_sections_agree_with_python() -> None:
    order = ["a", "b", "c", "d"]
    cases: list[tuple[list[str], str, str | None]] = [
        (order, row, before) for row in (*order, "z") for before in (None, *order, "z")
    ]
    out = _node(
        {
            "moves": cases,
            "place": [
                [order, "c", 1],
                [order, "c", 3],
                [order, "a", 2],
                [order, "a", 99],
                [order, "b", 0],
            ],
            "step": [
                [order, "a", -1],
                [order, "a", 1],
                [order, "c", 1],
                [order, "d", 1],
                [order, "b", -1],
                [order, "a", None],
                [order, "c", None],
                [order, "z", 1],
            ],
            "slot": [[0, 100, 34, 4], [116, 100, 34, 4], [134, 100, 34, 4], [999, 100, 34, 4]],
            "slotBefore": [[order, "c", 0], [order, "c", 2], [order, "c", 3], [order, "c", 4]],
            "parse": ["3", " 12 ", "", "x", "1.5", "-1", None],
            "typed": [
                ["a", False, False, False],
                ["가", False, False, False],
                ["ㅎ", False, False, False],
                ["Process", False, False, False],
                ["Enter", False, False, False],
                [" ", False, False, False],
                ["a", True, False, False],
                ["a", False, False, True],
            ],
        },
        _PURE_RUNNER,
        _sections(),
    )
    assert out["moves"] == [list(move_before(*case)) for case in cases]
    assert out["applied"] == ["d", "b", "c", "a"]
    assert out["place"] == ["a", "d", "c", None, "a"]
    assert out["step"] == ["END", "c", None, "END", "a", "END", "a", "END"]
    assert out["slot"] == [0, 0, 1, 4]
    assert out["slotBefore"] == ["a", "d", "d", None]
    assert out["parse"] == [3, 12, None, None, None, None, None]
    assert out["composing"] == [True, True, False, True, False, False]
    assert out["typed"] == [
        {"text": "a"},
        {"text": "가"},
        {"select": True},
        {"select": True},
        None,
        None,
        None,
        None,
    ]


# ---------------------------------------------------------------- 가짜 DOM


_DOM = """
const focusCalls = []
class FakeNode {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase()
    this.children = []
    this.parentNode = null
    this.attributes = {}
    this.dataset = {}
    this.listeners = {}
    this.style = { setProperty() {} }
    this.className = ''
    this.hidden = false
    this.title = ''
    this.ownText = ''
    this.disabled = false
    this.value = ''
    this.tabIndex = -1
    this.scrollTop = 0
    this.offsetTop = 34
  }
  appendChild(child) {
    child.parentNode = this
    this.children.push(child)
    return child
  }
  replaceChild(next, old) {
    next.parentNode = this
    this.children[this.children.indexOf(old)] = next
    old.parentNode = null
    return old
  }
  get textContent() {
    return this.ownText + this.children.map((child) => child.textContent).join('')
  }
  set textContent(value) {
    for (const child of this.children) child.parentNode = null
    this.children = []
    this.ownText = String(value)
  }
  set innerHTML(value) {
    this.textContent = ''
  }
  setAttribute(name, value) { this.attributes[name] = String(value) }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null }
  removeAttribute(name) { delete this.attributes[name] }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler) }
  removeEventListener(type, handler) {
    this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== handler)
  }
  get classList() {
    const names = () => this.className.split(/\\s+/).filter(Boolean)
    return {
      add: (name) => { if (!names().includes(name)) this.className = (this.className + ' ' + name).trim() },
      remove: (name) => { this.className = names().filter((item) => item !== name).join(' ') },
      contains: (name) => names().includes(name),
      toggle: (name, on) => {
        if (on) this.classList.add(name)
        else this.classList.remove(name)
      },
    }
  }
  contains(node) {
    for (let at = node; at; at = at.parentNode) if (at === this) return true
    return false
  }
  getRootNode() { return document }
  getBoundingClientRect() { return { top: 100, bottom: 500, left: 0, width: 600 } }
  focus(options) {
    const previous = document.activeElement
    focusCalls.push(options || null)
    if (previous && previous !== this) fireOnly(previous, 'focusout', { relatedTarget: this })
    document.activeElement = this
    fireOnly(this, 'focusin', {})
  }
  select() { this.selected = true }
  setPointerCapture(id) { this.captured = id }
  matches(selector) {
    if (selector === '[data-col]') return this.dataset.col !== undefined
    if (selector === '[data-fk]') return this.dataset.fk !== undefined
    if (selector.startsWith('.')) return this.className.split(/\\s+/).includes(selector.slice(1))
    return this.tagName === selector.toUpperCase()
  }
  closest(selector) {
    for (let at = this; at; at = at.parentNode) if (at.matches && at.matches(selector)) return at
    return null
  }
  querySelectorAll(selector) {
    const found = []
    const walk = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child)
        walk(child)
      }
    }
    walk(this)
    return found
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null }
}

function fireOnly(target, type, extra) {
  const event = Object.assign({
    type, target, stopped: false, prevented: false, relatedTarget: null,
    stopPropagation() { this.stopped = true },
    preventDefault() { this.prevented = true },
  }, extra || {})
  for (let at = target; at && !event.stopped; at = at.parentNode) {
    for (const handler of (at.listeners[type] || []).slice()) handler.call(at, event)
  }
  return event
}

const documentListeners = {}
globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeNode(tag),
  addEventListener(type, handler) { (documentListeners[type] = documentListeners[type] || []).push(handler) },
  removeEventListener(type, handler) {
    documentListeners[type] = (documentListeners[type] || []).filter((item) => item !== handler)
  },
}
const fireDocument = (type, extra) => {
  const event = Object.assign({ type, stopPropagation() {} }, extra || {})
  for (const handler of (documentListeners[type] || []).slice()) handler(event)
}
const realTimeout = setTimeout
const tick = (ms) => new Promise((resolve) => realTimeout(resolve, ms))

function mount(data) {
  const parentElement = new FakeNode('div')
  const host = parentElement.appendChild(new FakeNode('div'))
  host.className = 'emg sgl'
  const sent = []
  const component = { data, parentElement, setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]) }
  const cleanup = globalThis.__mount(component)
  return { host, sent, cleanup, rerender: (next) => globalThis.__mount({ ...component, data: next }) }
}
const cell = (host, id, col) => host.querySelectorAll('[data-col]').find((node) => node.dataset.id === id && node.dataset.col === col)
const press = (node) => node.querySelector('.emg-cb')
const click = (node) => fireOnly(node, 'click', {})
const key = (node, name, extra) => fireOnly(node, 'keydown', { key: name, ...(extra || {}) })
const ops = (entry) => entry[1].ops.map((op) => op.op)
const editor = (host) => host.querySelector('.emg-ed')
const type = (node, text) => {
  node.value = text
  fireOnly(node, 'input', {})
}
const rows = (host) => host.querySelectorAll('.sgl-body').flatMap((body) => body.children.map((row) => row.dataset.row))

const SCENARIOS = {
  mode: 'scenarios', base: 's:0', orderToken: 'tok', open: 'a', limits: { outboxCells: 2000 },
  rows: [
    { id: 'a', name: '가', latest: 'r1', official: '', updated: '' },
    { id: 'b', name: '나', latest: 'r2', official: '', updated: '' },
    { id: 'c', name: '다', latest: 'r3', official: '', updated: '' },
  ],
}
const REVISIONS = {
  mode: 'revisions', base: 's:0', owner: 'a', title: '가', sub: '코드', picked: 'r2', limits: {},
  rows: [
    { id: 'r2', no: 'r2', name: '둘째', status: '공식 v1', memo: '메모 둘', created: '26.11.05', parent: 'r1' },
    { id: 'r1', no: 'r1', name: '첫째', status: '', memo: '', created: '26.11.04', parent: '' },
  ],
}
"""

_MOUNT_SOURCE = JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")

_GESTURES = (
    _DOM
    + """
const out = {}
;(async () => {
  // 처음 그림 — 연 줄 표시, 머리 포함 줄 수, 끝 닿은 단추 잠금 + 까닭.
  let m = mount(SCENARIOS)
  out.first = {
    rows: rows(m.host),
    open: m.host.querySelectorAll('.is-open').map((node) => node.dataset.row),
    rowcount: m.host.querySelector('.sgl-table').getAttribute('aria-rowcount'),
    tools: m.host.querySelectorAll('.emg-btn').map((node) => node.disabled),
    slots: m.host.querySelectorAll('.sgl-tool-slot').map((node) => node.querySelector('.emg-tip').textContent),
    stop: m.host.querySelectorAll('.emg-cb').filter((node) => node.tabIndex === 0).length,
  }

  // 안 연 줄의 이름을 누르면 연다 — 바로 보내고, 다시 누르면 편집이다(두 번 누르면 열고 편집).
  click(press(cell(m.host, 'b', 'name')))
  out.openSent = m.sent.map(ops)
  out.openOptimistic = m.host.querySelectorAll('.is-open').map((node) => node.dataset.row)
  out.noEditor = editor(m.host) === null
  click(press(cell(m.host, 'b', 'name')))
  const input = editor(m.host)
  out.editing = { value: input.value, selected: input.selected === true, focus: document.activeElement === input }

  // 쓰는 동안 아무것도 보내지 않는다. 회차가 돌아와도 입력칸을 다시 짓지 않고 받은 data 만 든다.
  type(input, '새 나')
  const during = m.sent.length
  m.rerender({ ...SCENARIOS, open: 'b', ack: { mount: m.sent[0][1].mount, seq: m.sent[0][1].ops[0].seq } })
  out.keptInput = editor(m.host) === input && input.value === '새 나'

  // Enter — 확정. 300ms 묶음으로 간다.
  key(input, 'Enter')
  out.afterEnter = { editor: editor(m.host) === null, sentNow: m.sent.length === during }
  await tick(330)
  const named = m.sent[m.sent.length - 1]
  out.named = named[1].ops.filter((op) => op.op === 'name').map((op) => [op.kind, op.id, op.text, op.seen, op.base])
  // 이미 보낸 op 만 남았으면 다시 보내지 않는다.
  const before = m.sent.length
  fireOnly(m.host, 'focusout', { relatedTarget: null })
  fireDocument('visibilitychange')
  out.noResend = m.sent.length === before

  // 낙관 표시 — 반영 전 글자는 기울임, 고친 칸은 data 가 오면 노랑 + 저장본 풍선.
  out.pending = cell(m.host, 'b', 'name').classList.contains('is-pending')
  m.rerender({
    ...SCENARIOS, open: 'b', ack: { mount: named[1].mount, seq: named[1].ops[named[1].ops.length - 1].seq },
    rows: [SCENARIOS.rows[0], { ...SCENARIOS.rows[1], name: '새 나', saved: '나', problem: '먼저 바뀜' }, SCENARIOS.rows[2]],
  })
  const changed = cell(m.host, 'b', 'name')
  out.changed = {
    pending: changed.classList.contains('is-pending'),
    changed: changed.classList.contains('is-changed'),
    error: changed.classList.contains('is-error'),
    tip: changed.title,
    text: press(changed).textContent,
    invalid: press(changed).getAttribute('aria-invalid'),
    label: press(changed).getAttribute('aria-label'),
  }

  // Esc — 취소, 아무것도 보내지 않는다. 받은 data 가 있으면 끝나고 그린다.
  const count = m.sent.length
  click(press(cell(m.host, 'b', 'name')))
  const second = editor(m.host)
  type(second, '버릴 글')
  key(second, 'Escape')
  await tick(330)
  out.escape = { editor: editor(m.host) === null, sent: m.sent.length === count, text: press(cell(m.host, 'b', 'name')).textContent }

  // Tab · ↑↓ — 옆 · 위아래 편집 칸으로. Shift+Tab 은 왼쪽(순서 칸).
  click(press(cell(m.host, 'b', 'name')))
  key(editor(m.host), 'ArrowDown')
  out.down = editor(m.host).parentNode.dataset.id
  key(editor(m.host), 'ArrowUp')
  out.up = editor(m.host).parentNode.dataset.id
  key(editor(m.host), 'Tab', { shiftKey: true })
  out.left = [editor(m.host).parentNode.dataset.id, editor(m.host).parentNode.dataset.col]
  key(editor(m.host), 'Tab')
  out.right = [editor(m.host).parentNode.dataset.id, editor(m.host).parentNode.dataset.col]
  key(editor(m.host), 'Tab')
  out.noneRight = editor(m.host) === null
  m.cleanup()

  // 키 — Enter · F2 는 어느 줄이든 바로 편집, 글자 치면 그 글자로, Space 는 연다, 화살표는 칸 이동.
  m = mount(SCENARIOS)
  const name = press(cell(m.host, 'c', 'name'))
  name.focus()
  key(name, 'F2')
  out.f2 = editor(m.host).value
  key(editor(m.host), 'Escape')
  const again = press(cell(m.host, 'c', 'name'))
  key(again, 'x')
  out.typed = editor(m.host).value
  key(editor(m.host), 'Escape')
  key(press(cell(m.host, 'c', 'name')), 'ㅎ')
  out.jamo = { value: editor(m.host).value, selected: editor(m.host).selected === true }
  key(editor(m.host), 'Escape')
  key(press(cell(m.host, 'c', 'name')), ' ')
  out.space = m.sent.map(ops)
  key(press(cell(m.host, 'c', 'name')), 'ArrowUp')
  out.arrow = [document.activeElement.parentNode.dataset.id, document.activeElement.parentNode.dataset.col]
  m.cleanup()

  // 한글 조합 — 조합 중 Enter 는 확정하지 않고 기억했다가 조합이 끝나면 한 번 확정한다.
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  const composing = editor(m.host)
  type(composing, '하')
  const held = key(composing, 'Enter', { isComposing: true, code: 'Enter', keyCode: 229 })
  out.ime = { open: editor(m.host) === composing, prevented: held.prevented }
  key(composing, 'Tab', { isComposing: true, keyCode: 229 })
  key(composing, 'Escape', { isComposing: true, keyCode: 229 })
  out.ime.stillOpen = editor(m.host) === composing
  type(composing, '한글')
  fireOnly(composing, 'compositionend', {})
  out.ime.closed = editor(m.host) === null
  await tick(330)
  out.ime.op = m.sent[m.sent.length - 1][1].ops.map((op) => [op.op, op.text])
  m.cleanup()

  // 칸 밖 누름 — 확정한다. 줄을 다시 짓지 않아 누른 칸의 click 이 닿는다.
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  const open = editor(m.host)
  type(open, '칸 밖')
  fireOnly(press(cell(m.host, 'c', 'latest')), 'pointerdown', { button: 0 })
  const rowNode = m.host.querySelector('.sgl-body').children[2]
  press(cell(m.host, 'c', 'latest')).focus()
  out.outside = { closed: editor(m.host) === null, sameRow: m.host.querySelector('.sgl-body').children[2] === rowNode }
  // 누르는 동안 회차가 돌아와도 줄을 다시 짓지 않는다 — 그 click 이 op 가 된다.
  m.rerender({ ...SCENARIOS, rows: SCENARIOS.rows.slice() })
  out.outside.keptDuringPress = m.host.querySelector('.sgl-body').children[2] === rowNode
  click(press(cell(m.host, 'c', 'latest')))
  fireDocument('pointerup')
  await tick(5)
  out.outside.rebuiltAfter = m.host.querySelector('.sgl-body').children[2] !== rowNode
  await tick(330)
  out.outside.ops = m.sent.flatMap((entry) => entry[1].ops).map((op) => [op.op, op.id]).filter(([name]) => name === 'open')
  m.cleanup()

  // 편집을 연 뒤 세대가 올라도(저장 직후 data) op 는 연 때의 세대로 간다 — 서버가 세어 알린다.
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  type(editor(m.host), '옛 세대 글')
  m.rerender({ ...SCENARIOS, base: 's:1' })
  key(editor(m.host), 'Enter')
  await tick(330)
  out.base = m.sent[m.sent.length - 1][1].ops.map((op) => [op.op, op.base])
  // 세대가 바뀌어도 보낼 목록을 비우지 않는다 — 낙관 표시만 걷는다.
  out.baseOptimistic = cell(m.host, 'a', 'name').classList.contains('is-pending')
  m.cleanup()

  // 옮기기 — 단추 · Alt+↑↓ · 순서 칸 번호. 회차 없이 낙관으로 옮기고, 열 번 눌러도 묶음 한 번이다.
  m = mount(SCENARIOS)
  const down = m.host.querySelectorAll('.emg-btn')[1]
  click(down)
  out.moved = rows(m.host)
  out.movedSent = m.sent.length
  const up = m.host.querySelectorAll('.emg-btn')[0]
  for (let k = 0; k < 10; k += 1) click(k % 2 ? down : up)
  await tick(330)
  out.batched = m.sent.length
  out.moveOps = m.sent[0][1].ops.map((op) => [op.op, op.id, op.token])[0]
  const place = press(cell(m.host, 'c', 'place'))
  click(place)
  type(editor(m.host), '1')
  key(editor(m.host), 'Enter')
  out.placed = rows(m.host)
  key(press(cell(m.host, 'c', 'name')), 'ArrowDown', { altKey: true })
  out.alt = rows(m.host)
  out.status = m.host.querySelector('.sgl-status').textContent
  m.cleanup()

  // 끌기 — 4px 넘게 움직이면 시작, 끄는 동안 다시 그리지 않고, 놓으면 그 자리로. Esc 는 취소.
  m = mount(SCENARIOS)
  const grip = cell(m.host, 'a', 'grip').querySelector('.sgl-grip')
  const body = m.host.querySelector('.sgl-body')
  fireOnly(grip, 'pointerdown', { button: 0, clientY: 110, pointerId: 3 })
  fireOnly(body, 'pointermove', { clientY: 112 })
  out.dragIdle = m.host.classList.contains('is-dragging')
  fireOnly(body, 'pointermove', { clientY: 100 + 34 * 2 })
  out.dragging = { on: m.host.classList.contains('is-dragging'), line: m.host.querySelector('.sgl-drop').hidden === false }
  const held2 = body.children[0]
  m.rerender({ ...SCENARIOS })
  out.dragKept = body.children[0] === held2
  fireDocument('pointerup')
  await tick(5)
  out.dropped = rows(m.host)
  fireOnly(press(cell(m.host, 'b', 'latest')), 'click', {})
  await tick(330)
  fireOnly(cell(m.host, 'c', 'grip').querySelector('.sgl-grip'), 'pointerdown', { button: 0, clientY: 110, pointerId: 3 })
  fireOnly(body, 'pointermove', { clientY: 300 })
  fireDocument('keydown', { key: 'Escape' })
  await tick(5)
  out.dragCancelled = { rows: rows(m.host), on: m.host.classList.contains('is-dragging') }
  m.cleanup()

  // 리비전 표 — 줄을 누르면 회차 전에 값 줄이 바뀌고, 고른 줄의 이름을 다시 누르면 편집이다.
  m = mount(REVISIONS)
  const values = () => m.host.querySelector('.sgl-values').textContent
  const memo = () => {
    const node = m.host.querySelector('.sgl-memo')
    return node && { text: node.textContent, title: node.title }
  }
  out.revisionFirst = { title: m.host.querySelector('.sgl-title').textContent, values: values(), memo: memo() }
  click(press(cell(m.host, 'r1', 'status')))
  out.revisionPick = {
    op: m.sent[m.sent.length - 1][1].ops.map((op) => [op.op, op.owner, op.id]),
    values: values(),
    memo: memo(),
    open: m.host.querySelectorAll('.is-open').map((node) => node.dataset.row),
  }
  click(press(cell(m.host, 'r1', 'name')))
  type(editor(m.host), '새 첫째')
  key(editor(m.host), 'Enter')
  await tick(330)
  out.revisionName = m.sent[m.sent.length - 1][1].ops.filter((op) => op.op === 'name').map((op) => [op.kind, op.id, op.text, op.seen])
  m.cleanup()

  // A → B → A — 마지막이 이긴다(고름에는 sendOnce 를 쓰지 않는다).
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'b', 'latest')))
  click(press(cell(m.host, 'a', 'latest')))
  click(press(cell(m.host, 'b', 'latest')))
  out.lastWins = m.sent[m.sent.length - 1][1].ops.map((op) => op.id)
  m.cleanup()

  // 정리 — 열린 칸을 확정하고 보낸다. 듣기를 푼다.
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  type(editor(m.host), '내리며 확정')
  m.cleanup()
  out.cleanup = {
    op: m.sent[m.sent.length - 1][1].ops.map((op) => [op.op, op.text]),
    listeners: Object.values(documentListeners).reduce((sum, list) => sum + list.length, 0),
  }
  process.stdout.write(JSON.stringify(out))
})()
"""
)


_REPAINTS = (
    _DOM
    + """
const out = {}
const many = {
  ...SCENARIOS,
  open: 'r250',
  rows: Array.from({ length: 500 }, (_, k) => ({ id: 'r' + k, name: '줄 ' + k, latest: 'r1', official: '', updated: '' })),
}
;(async () => {
  // 줄 옮기기 — 칸마다 op 를 다시 접으면 누를수록 느려진다. 누름 하나에 차례를 한 번만 짓는다.
  let m = mount(many)
  press(cell(m.host, 'r250', 'name')).focus()
  globalThis.__views = 0
  for (let k = 0; k < 8; k += 1) key(press(cell(m.host, 'r250', 'name')), 'ArrowDown', { altKey: true })
  out.perf = { views: globalThis.__views, at: rows(m.host).indexOf('r250') }
  m.cleanup()

  // 회차가 돌아온 다시 그리기는 스크롤을 끌고 가지 않는다 — 칸 확정 뒤 · 줄 열기 뒤.
  m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  type(editor(m.host), '새 가')
  key(editor(m.host), 'Enter')
  await tick(330)
  focusCalls.length = 0
  m.rerender({ ...SCENARIOS, rows: SCENARIOS.rows.slice() })
  out.afterCommit = focusCalls.slice()
  press(cell(m.host, 'c', 'latest')).focus()
  click(press(cell(m.host, 'c', 'latest')))
  focusCalls.length = 0
  m.rerender({ ...SCENARIOS, open: 'c', rows: SCENARIOS.rows.slice() })
  out.afterOpen = focusCalls.slice()
  // 키보드 손짓은 그 칸으로 스크롤을 따라간다.
  focusCalls.length = 0
  key(press(cell(m.host, 'c', 'name')), 'ArrowUp', { altKey: true })
  out.keyboard = focusCalls.slice()
  m.cleanup()

  // 끝에 닿은 이동 단추 — 감싼 칸이 탭 자리 · 초점을 받고, 그 초점 이동은 부품 안이라 보내지 않는다.
  m = mount(SCENARIOS)
  const slots = m.host.querySelectorAll('.sgl-tool-slot')
  const buttons = m.host.querySelectorAll('.emg-btn')
  out.tabs = slots.map((node) => node.tabIndex)
  click(buttons[1])
  out.tabsMiddle = slots.map((node) => node.tabIndex)
  buttons[0].focus()
  click(buttons[0])
  out.end = {
    inSlot: document.activeElement === slots[0],
    disabled: buttons[0].disabled,
    sent: m.sent.length,
    label: slots[0].getAttribute('aria-label'),
    described: slots[0].getAttribute('aria-describedby') === slots[0].querySelector('.emg-tip').id,
  }
  // 다시 켜지면 초점이 단추로 돌아간다.
  click(buttons[1])
  out.back = { onButton: document.activeElement === buttons[0], label: slots[0].getAttribute('aria-label'), tip: slots[0].querySelector('.emg-tip').textContent }
  m.cleanup()

  // 칸 풍선 — 잘릴 수 있는 칸은 값 전체를 풍선에 둔다.
  m = mount({ ...SCENARIOS, rows: [{ id: 'a', name: '아주 긴 이름', latest: 'r1', official: 'v12 · r3 · 최신', updated: '26.11.06 09:00' }] })
  out.tips = { name: cell(m.host, 'a', 'name').title, official: cell(m.host, 'a', 'official').title, updated: cell(m.host, 'a', 'updated').title }
  m.cleanup()
  m = mount({ ...REVISIONS, rows: [{ ...REVISIONS.rows[0], status: '공식 v12 · 올라와 있음 · 가상 2' }] })
  out.statusTip = cell(m.host, 'r2', 'status').title
  m.cleanup()

  // 옛 리비전 줄 — 누르는 동안 다른 시나리오의 data 가 왔으면 고르지 않는다. 지금 줄이 그려진다.
  m = mount(REVISIONS)
  const old = press(cell(m.host, 'r1', 'status'))
  fireOnly(old, 'pointerdown', { button: 0 })
  m.rerender({ ...REVISIONS, owner: 'b', title: '나', picked: 'r9', rows: [{ ...REVISIONS.rows[0], id: 'r9', no: 'r9' }] })
  click(old)
  fireDocument('pointerup')
  await tick(5)
  out.oldRow = { sent: m.sent.length, rows: rows(m.host) }
  m.cleanup()
  process.stdout.write(JSON.stringify(out))
})()
"""
)


_BURST = (
    _DOM
    + """
// 브라우저처럼 — 초점 든 칸이 다시 그리기로 사라지면 그 자리에서 대상 없는 focusout 이 난다.
const leaveIfGone = (node) => {
  const active = document.activeElement
  if (active && node.contains(active)) {
    document.activeElement = null
    fireOnly(active, 'focusout', { relatedTarget: null })
  }
}
const replaceChild = FakeNode.prototype.replaceChild
FakeNode.prototype.replaceChild = function (next, old) {
  leaveIfGone(old)
  return replaceChild.call(this, next, old)
}
const clearText = Object.getOwnPropertyDescriptor(FakeNode.prototype, 'textContent')
Object.defineProperty(FakeNode.prototype, 'textContent', {
  get() { return clearText.get.call(this) },
  set(value) {
    if (this.children.length) leaveIfGone(this)
    clearText.set.call(this, value)
  },
})
const out = {}
;(async () => {
  const m = mount(SCENARIOS)
  click(press(cell(m.host, 'a', 'name')))
  for (const [i, leave] of ['ArrowDown', 'ArrowDown', 'Enter'].entries()) {
    type(editor(m.host), '이름' + i)
    key(editor(m.host), leave)
  }
  out.burst = { sent: m.sent.length, box: m.host.__sgl.box.ops.length }
  // 묶음이 든 동안 회차가 돌아와 표를 다시 그려도 끊지 않는다.
  m.rerender({ ...SCENARIOS, orderToken: 'tok2' })
  out.repaint = { sent: m.sent.length, edit: m.host.__sgl.edit }
  await tick(330)
  out.quiet = { sent: m.sent.length, ops: m.sent[m.sent.length - 1][1].ops.length }
  // 진짜로 표 밖을 누르면 기다리지 않고 보낸다.
  click(press(cell(m.host, 'a', 'name')))
  const input = editor(m.host)
  type(input, '밖')
  document.activeElement = null
  fireOnly(input, 'focusout', { relatedTarget: null })
  out.outside = { sent: m.sent.length, edit: m.host.__sgl.edit }
  m.cleanup()
  process.stdout.write(JSON.stringify(out))
})()
"""
)


def test_a_burst_of_name_edits_goes_out_once_after_the_quiet_time() -> None:
    """이름 칸을 잇달아 고치면 보냄은 300ms 묶음 한 번이다(UI-PRF-02 「연속 N회 → 보냄 1회」). 확정이
    입력 칸을 다시 그리면 대상 없는 focusout 이 나고, 그것을 부품 밖으로 나간 것으로 읽어 칸마다
    회차가 돌았다(이름 4칸 3회차, 샘플 관측). 진짜로 표 밖을 누른 때는 곧바로 보낸다."""
    out = _node({}, _BURST, _MOUNT_SOURCE)
    assert out["burst"] == {"sent": 0, "box": 3}
    assert out["repaint"] == {"sent": 0, "edit": None}
    assert out["quiet"] == {"sent": 1, "ops": 3}, "이름 3칸 → 보냄 1회"
    assert out["outside"] == {"sent": 2, "edit": None}, "표 밖 누름은 곧바로 보낸다"


def test_repainting_keeps_speed_scroll_and_focus() -> None:
    source = _MOUNT_SOURCE.replace(
        "function applyMoves(order, moves) {\n",
        "function applyMoves(order, moves) {\n  globalThis.__views += 1\n",
    )
    assert source != _MOUNT_SOURCE
    out = _node({}, _REPAINTS, source)
    # 누름 여덟 번, 칸은 3000개다 — 칸마다 접으면 수천 번이다.
    assert out["perf"]["views"] <= 16
    assert out["perf"]["at"] == 258
    assert out["afterCommit"] == [{"preventScroll": True}]
    assert out["afterOpen"] == [{"preventScroll": True}]
    assert out["keyboard"] == [None]
    assert out["tabs"] == [0, -1, 0]
    assert out["tabsMiddle"] == [-1, -1, -1]
    assert out["end"] == {
        "inSlot": True,
        "disabled": True,
        "sent": 0,
        "label": "↑ 위로 — 맨 위 줄입니다",
        "described": True,
    }
    assert out["back"] == {"onButton": True, "label": None, "tip": ""}
    assert out["tips"] == {
        "name": "아주 긴 이름",
        "official": "v12 · r3 · 최신",
        "updated": "",
    }
    assert out["statusTip"] == "공식 v12 · 올라와 있음 · 가상 2"
    assert out["oldRow"] == {"sent": 0, "rows": ["r9"]}


def test_the_gestures_in_a_fake_dom() -> None:
    out = _node({}, _GESTURES, _MOUNT_SOURCE)
    assert out["first"] == {
        "rows": ["a", "b", "c"],
        "open": ["a"],
        "rowcount": "4",
        "tools": [True, False, True],
        "slots": ["맨 위 줄입니다", "", "맨 위 줄입니다"],
        "stop": 1,
    }
    assert out["openSent"] == [["open"]]
    assert out["openOptimistic"] == ["b"]
    assert out["noEditor"] is True
    assert out["editing"] == {"value": "나", "selected": True, "focus": True}
    assert out["keptInput"] is True
    assert out["afterEnter"] == {"editor": True, "sentNow": True}
    assert out["named"] == [["scenario", "b", "새 나", "나", "s:0"]]
    assert out["noResend"] is True
    assert out["pending"] is True
    assert out["changed"] == {
        "pending": False,
        "changed": True,
        "error": True,
        "tip": "새 나\n저장본: 나\n막힘: 먼저 바뀜",
        "text": "! 새 나",
        "invalid": "true",
        "label": "새 나 시나리오명, 고침 — 저장본 나, 막힘 — 먼저 바뀜",
    }
    assert out["escape"] == {"editor": True, "sent": True, "text": "! 새 나"}
    assert out["down"] == "c" and out["up"] == "b"
    assert out["left"] == ["b", "place"] and out["right"] == ["b", "name"]
    assert out["noneRight"] is True
    assert out["f2"] == "다"
    assert out["typed"] == "x"
    assert out["jamo"] == {"value": "다", "selected": True}
    assert out["space"] == [["open"]]
    assert out["arrow"] == ["b", "name"]
    assert out["ime"] == {
        "open": True,
        "prevented": False,
        "stillOpen": True,
        "closed": True,
        "op": [["name", "한글"]],
    }
    assert out["outside"] == {
        "closed": True,
        "sameRow": True,
        "keptDuringPress": True,
        "rebuiltAfter": True,
        "ops": [["open", "c"]],
    }
    assert out["base"] == [["name", "s:0"]]
    assert out["baseOptimistic"] is False
    assert out["moved"] == ["b", "a", "c"]
    assert out["movedSent"] == 0
    assert out["batched"] == 1
    assert out["moveOps"] == ["move", "a", "tok"]
    assert out["placed"][0] == "c"
    assert out["alt"][1] == "c"
    assert "번째로 옮김" in out["status"]
    assert out["dragIdle"] is False
    assert out["dragging"] == {"on": True, "line": True}
    assert out["dragKept"] is True
    assert out["dropped"] == ["b", "a", "c"]
    assert out["dragCancelled"]["on"] is False
    assert out["dragCancelled"]["rows"] == ["b", "a", "c"]
    assert out["revisionFirst"]["title"] == "가"
    assert "메모 둘" in out["revisionFirst"]["values"]
    # 긴 메모가 작업 줄을 밀어내지 않게 세 줄로 자르고(CSS) 전문은 풍선에 둔다. 빈 메모에는 풍선이 없다.
    assert out["revisionFirst"]["memo"] == {"text": "메모 둘", "title": "메모 둘"}
    assert out["revisionPick"]["memo"] is None
    assert out["revisionPick"]["op"] == [["pick", "a", "r1"]]
    assert "메모 둘" not in out["revisionPick"]["values"]
    assert out["revisionPick"]["open"] == ["r1"]
    assert out["revisionName"] == [["revision", "r1", "새 첫째", "첫째"]]
    assert out["lastWins"] == ["b", "a", "b"]
    assert out["cleanup"] == {"op": [["name", "내리며 확정"]], "listeners": 0}


_CHANGES = (
    _DOM
    + """
const out = {}
const DATA = {
  mode: 'changes', base: 's:0', limits: {},
  counts: { scenario: 1, order: 2, revision: 1, blocked: 1 },
  order: { moved: 2, problem: '차례 막힘' },
  groups: [{
    id: 'a', name: '가 새',
    lines: [
      { kind: 'scenario', id: 'a', label: '시나리오명', before: '가', after: '가 새' },
      { kind: 'revision', id: 'r1', label: '리비전명 r1', before: '첫', after: '', problem: '막힘 글', mark: '공식 v4', note: '공식버전명은 그대로' },
    ],
  }],
}
let m = mount(DATA)
out.sum = m.host.querySelector('.emg-sum').textContent
out.text = m.host.textContent
const undos = m.host.querySelectorAll('.emg-icon')
out.undoCount = undos.length
out.markTip = m.host.querySelector('.sgl-mark').title
fireOnly(undos[1], 'click', {})
fireOnly(undos[1], 'click', {})
out.revert = m.sent.map((entry) => entry[1].ops.map((op) => [op.op, op.kind, op.id]))
fireOnly(m.host.querySelector('.emg-link'), 'click', {})
out.open = m.sent[m.sent.length - 1][1].ops.filter((op) => op.op === 'open').map((op) => [op.id, op.detail])
// 누르는 동안 온 회차는 손을 뗄 때까지 미룬다 — 되돌리기 아이콘의 click 을 잃지 않는다.
const kept = m.host.querySelector('.emg-icon')
fireOnly(kept, 'pointerdown', { button: 0 })
m.rerender({ ...DATA, groups: [] })
out.keptDuringPress = m.host.querySelector('.emg-icon') === kept
fireDocument('pointerup')
const after = () => {
  out.afterPress = m.host.querySelector('.emg-unit-head').textContent
  m.cleanup()
  m = mount({ ...DATA, groups: [], order: { moved: 0 }, counts: {} })
  out.empty = m.host.querySelector('.emg-side-empty').textContent
  process.stdout.write(JSON.stringify(out))
}
realTimeout(after, 5)
"""
)

_CHANGE_FOCUS = (
    _DOM
    + """
const out = {}
const line = (id) => ({ kind: 'scenario', id, label: '시나리오명 ' + id, before: '옛', after: '새' })
const data = (ids, moved) => ({
  mode: 'changes', base: 's:0', limits: {}, counts: {},
  order: { moved },
  groups: ids.map((id) => ({ id, name: '이름 ' + id, lines: [line(id)] })),
})
const m = mount(data(['a', 'b'], 2))
const undo = (label) => m.host.querySelectorAll('.emg-icon').find((node) => node.getAttribute('aria-label') === label)
const active = () => document.activeElement.getAttribute('aria-label')
undo('시나리오명 a 되돌리기').focus()
// 그 줄이 남으면 그 자리, 사라지면 그 다음 되돌리기, 다 사라지면 칸 머리다.
m.rerender(data(['a', 'b'], 2))
out.same = active()
focusCalls.length = 0
m.rerender(data(['b'], 2))
out.next = active()
out.options = focusCalls.slice()
undo('순서 되돌리기').focus()
m.rerender(data(['b'], 0))
out.previous = active()
m.rerender(data([], 0))
out.empty = document.activeElement.className
// 부품 밖에 있던 초점은 빼앗지 않는다.
const outside = new FakeNode('button')
document.activeElement = outside
m.rerender(data(['a'], 0))
out.outside = document.activeElement === outside
// 묶음 마지막 줄을 되돌리면 다음 묶음의 되돌리기로 간다 — 그 묶음의 시나리오 링크가 아니다.
const pair = (rows) => ({
  mode: 'changes', base: 's:0', limits: {}, counts: {}, order: {},
  groups: [
    { id: 'a', name: '이름 a', lines: rows },
    { id: 'b', name: '이름 b', lines: [line('b')] },
  ],
})
const second = { kind: 'revision', id: 'r1', label: '리비전명 a', before: '옛', after: '새' }
const fks = () => m.host.querySelectorAll('[data-fk]').map((node) => node.dataset.fk)
m.rerender(pair([line('a'), second]))
out.marks = fks()
undo('리비전명 a 되돌리기').focus()
m.rerender(pair([line('a')]))
out.lastOfGroup = document.activeElement.dataset.fk
// 시나리오 링크에 있던 초점도 그 묶음이 사라지면 다음 되돌리기로 간다.
m.rerender(pair([line('a')]))
m.host.querySelectorAll('[data-fk]').find((node) => node.dataset.fk === 'open-a').focus()
m.rerender({ ...pair([]), groups: [{ id: 'b', name: '이름 b', lines: [line('b')] }] })
out.linkGone = document.activeElement.dataset.fk
// 되돌리기가 없으면 링크가 남아도 칸 머리다.
m.rerender(pair([line('a')]))
undo('시나리오명 b 되돌리기').focus()
m.rerender({ ...pair([]), groups: [{ id: 'a', name: '이름 a', lines: [] }] })
out.noUndo = document.activeElement.className
process.stdout.write(JSON.stringify(out))
"""
)


_HEAD_LINE = (
    _DOM
    + """
const out = {}
const parts = (m) => m.host.querySelector('.sgl-root').children.map((node) => node.className.split(' ')[0])
const observers = []
globalThis.ResizeObserver = class {
  constructor(callback) { this.callback = callback; this.watched = []; this.stopped = false; observers.push(this) }
  observe(node) { this.watched.push(node) }
  disconnect() { this.stopped = true }
}
const side = {}
document.querySelector = (selector) => side[selector] || null
const placed = (top, height, left) => ({ style: {}, getBoundingClientRect: () => ({ top, height, left, bottom: top + height }) })
const SIDE = { choice: 'c', body: 'b' }
;(async () => {
  // 제목 · 부제는 표 아래, 값 줄 바로 위다 — 빈 표에서도 사라지지 않는다.
  let m = mount(REVISIONS)
  out.revisions = parts(m)
  out.title = m.host.querySelector('.sgl-title').textContent
  m.cleanup()
  m = mount({ ...REVISIONS, rows: [], picked: null })
  out.empty = { parts: parts(m), title: m.host.querySelector('.sgl-title').textContent, sub: m.host.querySelector('.sgl-sub').textContent }
  out.revisionObservers = observers.length
  m.cleanup()

  // 왼쪽 표가 먼저 서고 오른쪽 칸이 뒤따른다 — 기다렸다 맞춘다.
  m = mount({ ...SCENARIOS, side: SIDE })
  out.scenarios = parts(m)
  const tools = m.host.querySelector('.sgl-tools')
  tools.getBoundingClientRect = () => ({ right: 700, height: 30 })
  out.beforeSide = { observers: observers.length, gap: tools.style.marginBottom }
  const choice = placed(200, 28, 720)
  const body = placed(242, 300, 720)
  side['.st-key-c'] = choice
  side['.st-key-b'] = body
  await tick(230)
  out.oneLine = { gap: tools.style.marginBottom, push: body.style.marginTop }
  const seen = observers[observers.length - 1]
  out.watching = seen.watched.length === 2 && seen.watched[0] === choice && seen.watched[1] === tools

  // 작업 줄만 접힘 — 고르기는 그대로라 작업 줄을 지켜봐야 안다. 왼쪽을 올릴 수 없어 오른쪽 본문을 내린다.
  tools.getBoundingClientRect = () => ({ right: 700, height: 66 })
  seen.callback()
  out.toolsWrapped = { gap: tools.style.marginBottom, push: body.style.marginTop }
  // 내린 뒤 다시 재도 내린 값이 쌓이지 않는다 — 본문 위치는 내린 만큼 내려와 있다.
  body.getBoundingClientRect = () => ({ top: 278, height: 300, left: 720, bottom: 578 })
  seen.callback()
  out.toolsWrappedAgain = body.style.marginTop
  // 작업 줄이 펴지면 내림을 거두고 간격은 CSS 값이다.
  tools.getBoundingClientRect = () => ({ right: 700, height: 30 })
  seen.callback()
  out.toolsBack = { gap: tools.style.marginBottom, push: body.style.marginTop }
  body.getBoundingClientRect = () => ({ top: 242, height: 300, left: 720, bottom: 542 })

  // 회차 없이 일어나는 접힘 — 지켜보던 고르기 크기로 다시 맞춘다.
  choice.getBoundingClientRect = () => ({ top: 200, height: 59.5, left: 720, bottom: 259.5 })
  body.getBoundingClientRect = () => ({ top: 273.5, height: 300, left: 720, bottom: 573.5 })
  seen.callback()
  out.twoLines = tools.style.marginBottom
  // 내려 둔 채 칸을 접으면 내림도 거둔다.
  body.style.marginTop = '36px'
  choice.getBoundingClientRect = () => ({ top: 0, height: 0, left: 0, bottom: 0 })
  seen.callback()
  out.folded = { gap: tools.style.marginBottom, push: body.style.marginTop }

  // 같은 고르기면 옵저버를 새로 만들지 않고, 새로 선 고르기는 그것을 지켜본다.
  const count = observers.length
  m.rerender({ ...SCENARIOS, side: SIDE })
  out.sameChoice = observers.length === count
  const fresh = placed(200, 28, 720)
  side['.st-key-c'] = fresh
  side['.st-key-b'] = placed(242, 300, 720)
  m.rerender({ ...SCENARIOS, side: SIDE })
  const next = observers[observers.length - 1]
  out.swapped = { oldStopped: seen.stopped, watching: next.watched[0] === fresh && next.watched[1] === tools, gap: tools.style.marginBottom }
  // 표가 내려가면 오른쪽 칸은 남는다 — 넣어 둔 내림을 거두고 간다.
  side['.st-key-b'].style.marginTop = '36px'
  m.cleanup()
  out.cleanedUp = { stopped: next.stopped, push: side['.st-key-b'].style.marginTop }

  // 칸이 끝내 안 서면 기다림은 끝나고, 내리면 기다림도 멈춘다.
  delete side['.st-key-c']
  const before = observers.length
  m = mount({ ...SCENARIOS, side: SIDE })
  m.cleanup()
  side['.st-key-c'] = fresh
  await tick(230)
  out.stoppedWaiting = observers.length === before
  process.stdout.write(JSON.stringify(out))
})()
"""
)


def test_the_revision_table_comes_first_and_the_head_lines_up() -> None:
    """리비전 표가 칸 맨 위라 머리가 왼쪽 표 머리와 윗선이 같고, 제목 · 부제는 표 아래 값 줄 바로
    위다. 고르기가 접히면 왼쪽이, 작업 줄만 접히면 오른쪽이 따라간다."""
    out = _node({}, _HEAD_LINE, _MOUNT_SOURCE)
    # 맨 뒤 낭독 칸(`.sgl-status`)은 자리를 차지하지 않는다.
    order = ["sgl-box", "sgl-title", "sgl-sub", "sgl-values", "sgl-status"]
    assert out["revisions"] == order
    assert out["title"] == "가"
    assert out["empty"] == {"parts": order, "title": "가", "sub": "코드"}
    assert out["revisionObservers"] == 0
    assert out["scenarios"][:2] == ["sgl-tools", "sgl-box"]
    assert out["beforeSide"] == {"observers": 0}
    assert out["oneLine"] == {"gap": "12px", "push": ""} and out["watching"] is True
    assert out["toolsWrapped"] == {"gap": "12px", "push": "36px"}
    assert out["toolsWrappedAgain"] == "36px"
    assert out["toolsBack"] == {"gap": "12px", "push": ""}
    assert out["twoLines"] == "43.5px"
    assert out["folded"] == {"gap": "", "push": ""}
    assert out["sameChoice"] is True
    assert out["swapped"] == {"oldStopped": True, "watching": True, "gap": "12px"}
    assert out["cleanedUp"] == {"stopped": True, "push": ""}
    assert out["stoppedWaiting"] is True


def test_a_reverted_line_hands_the_keyboard_focus_on() -> None:
    out = _node({}, _CHANGE_FOCUS, _MOUNT_SOURCE)
    assert out["same"] == "시나리오명 a 되돌리기"
    assert out["next"] == "시나리오명 b 되돌리기"
    assert out["options"] == [{"preventScroll": True}]
    assert out["previous"] == "시나리오명 b 되돌리기"
    assert "sgl-changes" in out["empty"]
    assert out["outside"] is True
    assert out["marks"] == [
        "open-a",
        "undo-scenario-a",
        "undo-revision-r1",
        "open-b",
        "undo-scenario-b",
    ]
    assert out["lastOfGroup"] == "undo-scenario-b"
    assert out["linkGone"] == "undo-scenario-b"
    assert "sgl-changes" in out["noUndo"]


def test_the_changes_panel_lists_old_and_new_and_reverts_once() -> None:
    out = _node({}, _CHANGES, _MOUNT_SOURCE)
    assert out["sum"] == "1시나리오명2순서1리비전명1막힘"
    for piece in (
        "가 → 가 새",
        "첫 → (빈 이름)",
        "! 막힘 글",
        "2줄 자리 바뀜",
        "! 차례 막힘",
        "공식 v4",
    ):
        assert piece in out["text"], piece
    assert out["undoCount"] == 3
    assert out["markTip"] == "공식버전명은 그대로"
    # 더블클릭의 둘째 누름은 첫 op 의 회차가 돌아오기 전에 닿는다 — 보내지 않는다.
    assert out["revert"] == [[["revert", "revision", "r1"]]]
    assert out["open"] == [["a", True]]
    assert out["keptDuringPress"] is True
    assert out["afterPress"] == "목록 차례"
    assert out["empty"] == "아직 고친 것이 없습니다."
