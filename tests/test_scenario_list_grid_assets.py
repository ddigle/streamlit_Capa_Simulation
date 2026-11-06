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
_SECTIONS = ("grid-nav", "grid-outbox", "list-move", "list-ime")
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
  focus() {
    const previous = document.activeElement
    if (previous && previous !== this) fireOnly(previous, 'focusout', { relatedTarget: this })
    document.activeElement = this
    fireOnly(this, 'focusin', {})
  }
  select() { this.selected = true }
  setPointerCapture(id) { this.captured = id }
  matches(selector) {
    if (selector === '[data-col]') return this.dataset.col !== undefined
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
    slots: m.host.querySelectorAll('.sgl-tool-slot').map((node) => node.title),
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
        "tip": "저장본: 나\n막힘: 먼저 바뀜",
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
