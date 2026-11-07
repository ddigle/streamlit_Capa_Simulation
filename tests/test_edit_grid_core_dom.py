# Purpose: 범용 편집 그리드 core JS 를 가짜 DOM 에 마운트해 그리기·편집·이동·출납·feed 받기를 본다.

"""브라우저 없이 core 의 배선을 본다 — 등록 JS 전체(고르기 기능 `eg_select` 포함 — 그 기능 몫은
`test_edit_grid_select_js` 가 따로 본다)를
`tests/edit_grid_node.FAKE_DOM` 에 마운트하고, 껍데기·feed 는 Python 이 지은 그대로 넘긴다. 실제
그리기 크기·스크롤·초점은 사본 앱 브라우저로 본다(명세 13-5)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from edit_grid_node import FAKE_DOM, mountable, run_node

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import build_base, encode_base, encode_feed

MONTHS = ("202701", "202702", "202703", "202704")
SPEC = eg.GridSpec(
    "RQ_DEMO",
    "효율",
    ("공정", "구분"),
    MONTHS,
    eg.ValueFormat("percent", 2, max_value=1.0),
    value_help="데모 월 칸 풍선",
)
OTHER = eg.GridSpec("RQ_OTHER", "일수", ("공정",), MONTHS, eg.ValueFormat("fixed", 0, integer=True))


def _frame() -> pd.DataFrame:
    frame = pd.DataFrame({"공정": ["DEMO_A", "DEMO_B", "DEMO_C"], "구분": ["양산", "양산", "ER"]})
    for column, month in enumerate(MONTHS):
        frame[month] = [0.9, 0.8 - column / 100, np.nan if column == 0 else 0.7]
    return frame


def _shell(spec: eg.GridSpec, frame: pd.DataFrame, key: str) -> tuple[dict[str, Any], eg.GridIndex]:
    base = build_base(frame, spec, {"공정": {"DEMO_A": "공정 에이"}})
    shell = encode_base(
        base.body,
        host="demo_grid",
        base_key=key,
        texts=edit_grid.texts(spec, changes_label="적용 전 변경"),
        palette={"text": "black-ink", "surface": "white-face"},
        row_height=30,
    )
    return shell, base.index


def _feed(
    index: eg.GridIndex, key: str, draft: eg.DraftState | None, undo: int = 0
) -> dict[str, Any]:
    step: eg.Step = {"rows": (), "cols": (), "before": (), "after": ()}
    history: eg.HistoryState = {"gen": "g1", "undo": [step] * undo, "redo": []}
    return encode_feed(index, draft, history, host="demo_grid", base_key=key, acks={}, toast=None)


RUNNER = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const sent = []
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.setAttribute('data-eg-root', '')
host.className = 'eg'
const mount = (data) => globalThis.__mount({
  data, parentElement,
  setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]),
})
const sendFeed = (feed) => {
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  ;(store[feed.host] = store[feed.host] || {}).feed = feed
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: feed.host }))
}
const q = (selector) => host.querySelector(selector)
const rows = () => q('.eg-body').children
const cell = (r, c) => rows()[r].children[c]
const text = (r, c) => cell(r, c).textContent
const has = (r, c, name) => cell(r, c).classList.contains(name)
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const lastOps = () => (sent.length ? sent[sent.length - 1][1].ops : [])
const here = (S) => Object.assign({}, S.anchor)
const R = {}
;(async () => {
  // feed 가 껍데기보다 먼저 와도 칸에 두었다가 껍데기가 오면 쓴다.
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  R.first = {
    rows: rows().length,
    cols: rows()[0].children.length,
    texts: [text(0, 0), text(0, 1), text(0, 2), text(2, 2), text(1, 3)],
    head: q('.eg-head').children.map((c) => c.textContent),
    active: has(0, 2, 'is-active'),
    gen: S.gen,
    where: q('.eg-where').textContent,
    palette: host.style.vars['--eg-text'],
    keyLocked: cell(0, 0).getAttribute('aria-readonly'),
    frozen: has(0, 0, 'eg-fz'),
    grid: ['role', 'aria-rowcount', 'aria-colcount'].map((name) => scroller.getAttribute(name)),
  }
  const drawn = cell(0, 2)
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowDown')
  R.moved = [here(S), has(1, 3, 'is-active'), scroller.getAttribute('aria-activedescendant')]
  // 고름만 바뀌면 칸을 다시 짓지 않고 표지만 고친다(보이는 창 다시 그리기 비용).
  R.kept = [cell(0, 2) === drawn, has(0, 2, 'is-active'), cell(0, 2).id, cell(1, 3).id]
  key(scroller, 'Enter')
  const editor = q('.eg-ed')
  R.editStart = {
    hidden: editor.hidden, value: editor.value, top: editor.style.top, left: editor.style.left,
  }
  editor.value = '50%'
  key(editor, 'Enter')
  R.commit = {
    hidden: editor.hidden,
    sends: sent.length,
    name: sent[0] && sent[0][0],
    op: lastOps()[0],
    anchor: here(S),
  }
  R.preview = { text: text(1, 3), changed: has(1, 3, 'is-changed') }
  // feed 가 ack 와 초안을 싣고 온다 — 미리보기를 걷고 정본을 그린다. 못 읽은 칸은 빨강 + 적은 글.
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: 1 } }))
  R.acked = {
    box: S.box.ops.length,
    pending: S.pending.size,
    text: text(1, 3),
    changed: has(1, 3, 'is-changed'),
    bad: [text(2, 2), has(2, 2, 'is-error'), cell(2, 2).getAttribute('aria-invalid')],
  }
  // 오류 칸으로 가면 상태 줄에 그 문구.
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowLeft')
  R.whereBad = q('.eg-where').textContent
  // 글자 입력으로 시작한 편집을 Esc 로 거두면 보내지 않는다.
  const before = sent.length
  key(scroller, '7')
  R.typed = q('.eg-ed').value
  key(q('.eg-ed'), 'Escape')
  R.cancelled = [q('.eg-ed').hidden, sent.length === before]
  // Ctrl+Z 는 바로 보낸다(feed 의 되돌리기 수 1).
  key(scroller, 'z', { ctrlKey: true })
  R.undo = lastOps().map((op) => op.op)
  // Delete 는 지금 칸 비우기 — 초안이 있는 표라 300ms 조용하면 보낸다.
  key(scroller, 'Delete')
  const queued = sent.length
  await tick(360)
  R.cleared = {
    waited: sent.length === queued + 1,
    ops: lastOps().map((op) => [op.op, op.rows, op.cols]),
  }
  // 분류 칸은 잠겨 있다.
  key(scroller, 'Home')
  key(scroller, 'Enter')
  R.locked = [q('.eg-ed').hidden, q('.eg-note').textContent]
  // 큰 이동 키.
  key(scroller, 'End', { ctrlKey: true })
  R.end = here(S)
  key(scroller, 'Home', { ctrlKey: true })
  R.home = here(S)
  key(scroller, 'PageDown')
  R.pageDown = here(S)
  // 붙여넣기 — 고르기 기능(eg_select)이 지금 칸부터 덩어리를 편다(분류 칸뿐이면 안내만).
  key(scroller, 'ArrowRight')
  fire(scroller, 'paste', { clipboardData: { getData: () => 'x' } })
  R.pasteLocked = q('.eg-note').textContent
  key(scroller, 'ArrowRight')
  fire(scroller, 'paste', { clipboardData: { getData: () => '12%\t13%\r\n' } })
  await tick(360)
  R.paste = lastOps().filter((op) => op.op === 'write').map((op) => [op.values, op.cols])
  // 머리 누름 = 정렬(보기만) — 지금 칸은 같은 원본 줄을 따라간다.
  fire(q('.eg-head').children[3].children[0], 'click')
  R.sorted = {
    order: Array.from(S.view.order),
    sort: q('.eg-head').children[3].getAttribute('aria-sort'),
  }
  // 값 칸 머리 풍선(role=tooltip, 300ms 뒤).
  fire(q('.eg-head').children[2], 'pointerover')
  await tick(340)
  const tip = q('.eg-tip')
  R.tip = [
    tip.hidden, tip.textContent, tip.getAttribute('role'),
    q('.eg-head').children[2].getAttribute('aria-describedby') === tip.id,
  ]
  // 다른 baseKey 의 feed 는 쓰지 않는다.
  const draftSize = S.model.draft.size
  sendFeed(Object.assign({}, input.feed2, { baseKey: 'other', drows: [] }))
  R.ignored = S.model.draft.size === draftSize
  // 같은 마운트에 다른 표 — 다시 마운트하지 않고(mount id 그대로) 그 표의 feed 를 기다린다.
  const mountId = S.mount
  mount(input.other)
  R.switched = {
    same: host.__eg === S && S.mount === mountId,
    table: S.model.table,
    gen: S.gen,
    cols: rows()[0].children.length,
  }
  sendFeed(input.otherFeed)
  R.otherFeed = { gen: S.gen, text: text(0, 1) }
  cleanup()
  R.cleaned = S.dom === null && S.listeners.length === 0
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_the_core_draws_edits_moves_and_talks_to_python() -> None:
    frame = _frame()
    shell, index = _shell(SPEC, frame, "k1")
    feed = _feed(index, "k1", None)
    feed2 = _feed(
        index,
        "k1",
        {
            "cells": {"DEMO_B\x1f양산": {"202702": 0.5}},
            "bad": {"DEMO_C\x1fER": {"202701": ("85", "max")}},
        },
        undo=1,
    )
    other_frame = pd.DataFrame({"공정": ["DEMO_A"], **{month: [30.0] for month in MONTHS}})
    other, other_index = _shell(OTHER, other_frame, "k2")
    other_feed = _feed(other_index, "k2", None)
    other_feed["gen"] = "g9"
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(
        source,
        RUNNER,
        {"shell": shell, "feed": feed, "feed2": feed2, "other": other, "otherFeed": other_feed},
    )
    first = result["first"]
    assert first["rows"] == 3 and first["cols"] == 6
    assert first["texts"] == ["공정 에이", "양산", "90%", "", "79%"]
    assert first["head"] == ["공정", "구분", *MONTHS]
    assert first["active"] and first["gen"] == "g1" and first["palette"] == "black-ink"
    assert first["where"] == "효율 › 공정 에이 · 양산 · 202701"
    assert first["keyLocked"] == "true" and first["frozen"]
    assert first["grid"] == ["grid", "4", "6"]
    anchor, active, descendant = result["moved"]
    assert anchor == {"r": 1, "c": 3} and active and descendant.endswith("-active")
    kept, was_active, old_id, new_id = result["kept"]
    assert kept and not was_active and old_id == "" and new_id == descendant
    assert result["editStart"] == {"hidden": False, "value": "79%", "top": "62px", "left": "288px"}
    commit = result["commit"]
    assert commit["hidden"] and commit["sends"] == 1 and commit["name"] == "outbox"
    op = commit["op"]
    assert {key: op[key] for key in ("op", "rows", "cols", "values", "table", "gen", "seq")} == {
        "op": "write",
        "rows": ["DEMO_B\x1f양산"],
        "cols": ["202702"],
        "values": [["50%"]],
        "table": "RQ_DEMO",
        "gen": "g1",
        "seq": 1,
    }
    assert commit["anchor"] == {"r": 2, "c": 3}, "Enter 확정은 아래 칸으로"
    assert result["preview"] == {"text": "50%", "changed": True}
    acked = result["acked"]
    assert acked["box"] == 0 and acked["pending"] == 0
    assert acked["text"] == "50%" and acked["changed"]
    assert acked["bad"] == ["85", True, "true"]
    assert result["whereBad"].endswith(
        "202701 — 100% 이하로 적습니다 — 85% 는 0.85 또는 85% 로 적습니다"
    )
    assert result["typed"] == "7" and result["cancelled"] == [True, True]
    assert result["undo"] == ["undo"]
    assert result["cleared"]["waited"]
    assert ["clear", ["DEMO_C\x1fER"], ["202701"]] in result["cleared"]["ops"]
    assert result["locked"] == [True, "분류 칸은 고칠 수 없습니다"]
    assert result["end"] == {"r": 2, "c": 5} and result["home"] == {"r": 0, "c": 0}
    assert result["pageDown"] == {"r": 2, "c": 0}
    assert result["pasteLocked"] == "분류 칸은 고칠 수 없습니다"
    assert result["paste"][-1] == [[["12%", "13%"]], ["202701", "202702"]]
    assert result["sorted"]["sort"] == "ascending"
    # 202702 오름차순 — 지금 보이는 값(초안·붙여넣기 미리보기 포함)으로: C 13% < B 50% < A 90%.
    assert result["sorted"]["order"] == [2, 1, 0]
    assert result["tip"] == [False, "데모 월 칸 풍선", "tooltip", True]
    assert result["ignored"]
    assert result["switched"] == {"same": True, "table": "RQ_OTHER", "gen": "", "cols": 5}
    assert result["otherFeed"] == {"gen": "g9", "text": "30"}
    assert result["cleaned"]


# 보기 차례·표 바꿈·페이지 배치·한글 자판·도구 막대 초점 — 리뷰(2026-11-03)가 사본 앱에서 잰
# 결함들을 가짜 DOM 으로 본다. 본문 블록(`stMainBlockContainer`)을 지켜보는지 보려고 그림자 호스트
# 사슬과 ResizeObserver 대역을 마운트 전에 세운다.
RUNNER_VIEW = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const sent = []
const observers = []
globalThis.ResizeObserver = class {
  constructor(callback) {
    this.callback = callback
    this.targets = []
    observers.push(this)
  }
  observe(target) {
    this.targets.push(target)
  }
  disconnect() {
    this.targets = []
  }
}
const main = new FakeNode('section')
main.setAttribute('data-testid', 'stMain')
const block = main.appendChild(new FakeNode('div'))
block.setAttribute('data-testid', 'stMainBlockContainer')
const shadowHost = block.appendChild(new FakeNode('div'))
FAKE_ROOT.host = shadowHost
let cleared = 0
document.getSelection = () => ({ rangeCount: 1, removeAllRanges() { cleared += 1 } })
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.setAttribute('data-eg-root', '')
const mount = (data) => globalThis.__mount({
  data, parentElement,
  setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]),
})
const sendFeed = (feed) => {
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  ;(store[feed.host] = store[feed.host] || {}).feed = feed
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: feed.host }))
}
const q = (selector) => host.querySelector(selector)
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const here = (S) => Object.assign({}, S.anchor)
const lastOps = () => (sent.length ? sent[sent.length - 1][1].ops : [])
const R = {}
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  let top = 271
  scroller.getBoundingClientRect = () => ({
    left: 0, top, right: 1000, bottom: top + 600, width: 1000, height: 600,
  })
  // 위쪽 알림이 서면 표가 내려간다 — frame 크기는 그대로라 본문 블록을 지켜봐야 다시 잰다.
  R.watched = observers.map((item) => item.targets.includes(block))
  top = 336
  for (const item of observers) if (item.targets.includes(block)) item.callback([])
  await tick(5)
  R.height = scroller.style.height
  // 여러 줄을 고른 채 정렬 — 지금 칸 하나로 접고(요약도 다시), 한 줄 안의 고름은 그 줄을 따라간다.
  key(scroller, 'ArrowDown', { shiftKey: true })
  key(scroller, 'ArrowRight', { shiftKey: true })
  await tick(5)
  R.beforeSort = [S.range(), q('.eg-summary').textContent]
  fire(q('.eg-head').children[3].children[0], 'click')
  await tick(5)
  R.sorted = [Array.from(S.view.order), here(S), S.range(), q('.eg-summary').textContent]
  key(scroller, 'Delete')
  await tick(360)
  R.cleared = lastOps().filter((op) => op.op === 'clear').map((op) => [op.rows, op.cols])
  key(scroller, 'ArrowRight', { shiftKey: true })
  fire(q('.eg-head').children[3].children[0], 'click')
  R.oneRow = [Array.from(S.view.order), here(S), S.range()]
  fire(q('.eg-head').children[3].children[0], 'click')
  // 고정(분류) 칸으로 가는 Ctrl+Home·Home 은 가로 스크롤을 처음으로.
  scroller.scrollLeft = 300
  key(scroller, 'Home', { ctrlKey: true })
  R.ctrlHome = [here(S), scroller.scrollLeft]
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowDown')
  scroller.scrollLeft = 300
  key(scroller, 'Home')
  R.home = [here(S), scroller.scrollLeft]
  // 한글 자판 — key 는 한글, code 는 라틴 자리.
  key(scroller, 'ArrowRight')
  const before = sent.length
  const undo = key(scroller, 'ㅋ', { code: 'KeyZ', ctrlKey: true })
  R.hangulUndo = [sent.length - before, lastOps().map((op) => op.op), undo.defaultPrevented]
  const all = key(scroller, 'ㅁ', { code: 'KeyA', ctrlKey: true })
  R.hangulAll = [S.range(), here(S), all.defaultPrevented]
  const clearedBefore = cleared
  const copy = key(scroller, 'ㅊ', { code: 'KeyC', ctrlKey: true })
  R.hangulCopy = [cleared - clearedBefore, copy.defaultPrevented]
  key(scroller, 'ㄹ', { code: 'KeyF', ctrlKey: true })
  R.hangulFind = document.activeElement === S.tb.dom.input
  fire(S.tb.dom.input, 'keydown', { key: 'ㄹ', code: 'KeyF', ctrlKey: true })
  R.hangulFindInInput = document.activeElement === S.tb.dom.input
  // 도구 막대 「적용 전 변경」·찾기 ▲▼ 를 마우스로 누르면 초점이 표로 돈다(찾을 글이 없으면
  // 찾기 칸).
  S.tb.dom.changes.focus()
  fire(S.tb.dom.changes, 'click', { detail: 1 })
  R.changesFocus = document.activeElement === scroller
  fire(S.tb.dom.changes, 'click', { detail: 1 })
  S.tb.dom.next.focus()
  fire(S.tb.dom.next, 'click', { detail: 1 })
  R.emptyFindFocus = document.activeElement === S.tb.dom.input
  S.tb.dom.input.value = '9'
  fire(S.tb.dom.input, 'input', {})
  await tick(150)
  S.tb.dom.next.focus()
  fire(S.tb.dom.next, 'click', { detail: 1 })
  R.findFocus = document.activeElement === scroller
  S.tb.dom.prev.focus()
  fire(S.tb.dom.prev, 'click', { detail: 0 })
  R.keyboardFindFocus = document.activeElement === S.tb.dom.prev
  // 다른 표로 바꾸면 앞 표의 토스트·상태 글이 걷힌다.
  toast(S, '앞 표 토스트')
  setStatus(S, '앞 표 상태 글')
  R.shownBefore = [q('.eg-toast').hidden, q('.eg-note').textContent]
  mount(input.other)
  R.hushed = [
    q('.eg-toast').hidden, q('.eg-toast').textContent, q('.eg-note').textContent,
    Boolean(S.timers.toast), Boolean(S.timers.note),
  ]
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_view_changes_layout_hangul_keys_toolbar_focus_and_table_switches() -> None:
    frame = _frame()
    shell, index = _shell(SPEC, frame, "k1")
    feed = _feed(index, "k1", None, undo=1)
    other_frame = pd.DataFrame({"공정": ["DEMO_A"], **{month: [30.0] for month in MONTHS}})
    other, _ = _shell(OTHER, other_frame, "k2")
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_VIEW, {"shell": shell, "feed": feed, "other": other})
    # 본문 블록을 지켜보고, 표가 65px 내려가면 높이를 950 − 336 − 24 − 24 = 566px 로 다시 잰다.
    assert True in result["watched"], "본문 블록(stMainBlockContainer)을 지켜보지 않는다"
    assert result["height"] == "566px"
    # 0~1줄 × 202701~202702 를 고른 뒤 202702 오름차순 — 첫 줄(DEMO_A 90%)은 끝으로 간다.
    before_range, before_summary = result["beforeSort"]
    assert before_range == {"r0": 0, "r1": 1, "c0": 2, "c1": 3}
    assert before_summary.startswith("개수 4")
    order, anchor, rng, summary = result["sorted"]
    assert order == [2, 1, 0]
    assert anchor == {"r": 2, "c": 2}, "지금 칸은 같은 원본 줄(DEMO_A)을 따라간다"
    assert rng == {"r0": 2, "r1": 2, "c0": 2, "c1": 2}, "여러 줄 고름은 지금 칸 하나로 접는다"
    assert summary == "", "요약도 접힌 범위로 다시 센다"
    assert result["cleared"][-1] == [["DEMO_A\x1f양산"], ["202701"]], "Delete 는 고른 칸만"
    # 한 줄 안의 고름(2칸)은 정렬을 풀어도 그 줄을 따라간다.
    one_order, one_anchor, one_range = result["oneRow"]
    assert one_order == [0, 1, 2]
    assert one_anchor == {"r": 0, "c": 2}
    assert one_range == {"r0": 0, "r1": 0, "c0": 2, "c1": 3}
    assert result["ctrlHome"] == [{"r": 0, "c": 0}, 0]
    assert result["home"] == [{"r": 1, "c": 0}, 0]
    sends, ops, prevented = result["hangulUndo"]
    assert sends == 1 and ops[-1] == "undo" and prevented, "Ctrl+ㅋ 은 되돌리기"
    all_range, all_anchor, all_prevented = result["hangulAll"]
    assert all_range == {"r0": 0, "r1": 2, "c0": 0, "c1": 5} and all_prevented
    assert all_anchor == {"r": 1, "c": 1}, "Ctrl+ㅁ 도 지금 칸을 지킨다"
    # Ctrl+ㅊ 은 페이지 글 고름을 지우고 copy 를 막지 않는다(브라우저가 표에 copy 를 쏜다).
    assert result["hangulCopy"] == [1, False]
    assert result["hangulFind"] and result["hangulFindInInput"]
    assert result["changesFocus"], "「적용 전 변경」 누름 뒤 초점은 표"
    assert result["emptyFindFocus"], "찾을 글이 없으면 ▼ 는 찾기 칸에 초점"
    assert result["findFocus"], "찾기 ▼ 누름 뒤 초점은 표"
    assert result["keyboardFindFocus"], "자판으로 누른 ▲ 는 단추에 남는다"
    assert result["shownBefore"] == [False, "앞 표 상태 글"]
    assert result["hushed"] == [True, "", "", False, False]


RUNNER_ACKS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const sent = []
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.setAttribute('data-eg-root', '')
host.className = 'eg'
const mount = (data) => globalThis.__mount({
  data, parentElement,
  setStateValue: (name, value) => sent.push(JSON.parse(JSON.stringify(value))),
})
const sendFeed = (feed) => {
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  ;(store[feed.host] = store[feed.host] || {}).feed = feed
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: feed.host }))
}
const docListeners = {}
document.addEventListener = (type, fn) => {
  ;(docListeners[type] = docListeners[type] || []).push(fn)
}
document.removeEventListener = (type, fn) => {
  docListeners[type] = (docListeners[type] || []).filter((f) => f !== fn)
}
const fireDoc = (type) => (docListeners[type] || []).slice().forEach((fn) => fn({ type }))
const q = (selector) => host.querySelector(selector)
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const seqs = () => (sent.length ? sent[sent.length - 1].ops.map((op) => op.seq) : [])
const edit = (value) => {
  key(q('.eg-scroll'), 'Enter')
  q('.eg-ed').value = value
  key(q('.eg-ed'), 'Enter')
}
const R = {}
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  edit('50%')  // 초안 없는 표의 첫 편집 — 곧바로 보낸다(seq 1)
  R.firstEdit = { sent: sent.length, box: S.box.ops.length, seqs: seqs() }
  // 보낸 op 가 아직 ack 되지 않았다 — 브라우저 탭을 바꿔도 다시 보내지 않는다.
  fireDoc('visibilitychange')
  R.inFlight = { sent: sent.length }
  // 읽기 보기 — 같은 회차가 표 없는 껍데기와 그 op 의 ack 를 싣고 온다(feed 다음 껍데기 차례).
  sendFeed(Object.assign({}, input.emptyFeed, { acks: { [S.mount]: 1 } }))
  mount(input.emptyShell)
  R.readView = { box: S.box.ops.length, model: S.model }
  fireDoc('visibilitychange')
  R.readViewHidden = { sent: sent.length }
  // 표로 돌아와(초안 1칸) 고치면 300ms 묶음 — 묶음 안의 op 는 아직 보내지 않았으니 탭을 바꾸면
  // 보낸다.
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: 1 } }))
  mount(input.shell)
  edit('60%')
  R.batched = { sent: sent.length, box: S.box.ops.length }
  fireDoc('visibilitychange')
  R.flushed = { sent: sent.length, seqs: seqs() }
  // 묶음이 차서 보낸 뒤(ack 전) 그리드를 내리면 정리 함수는 다시 보내지 않는다.
  edit('71%')
  await tick(360)
  R.timed = { sent: sent.length, seqs: seqs() }
  const cleanup = mount(input.shell)
  cleanup()
  R.cleanup = { sent: sent.length }
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_read_view_takes_acks_and_a_flush_sends_only_unsent_ops() -> None:
    """읽기 보기(표 없는 껍데기)를 고른 회차의 feed 도 ack 를 싣는다 — 그리드가 그 ack 로 출납을
    비우고, focusout·visibilitychange·정리 함수의 「보내기」 는 아직 보내지 않은 op 가 있을 때만
    보낸다. 전에는 읽기 보기에서 ack 를 버려(`!S.model`) 이미 반영된 op 를 탭을 바꿀 때마다·화면을
    떠날 때 다시 보내 앱 회차가 하나씩 더 돌았다(2026-11-03 마지막 검토 C3)."""
    shell, index = _shell(SPEC, _frame(), "k1")
    feed = _feed(index, "k1", None)
    feed2 = _feed(index, "k1", {"cells": {"DEMO_B\x1f양산": {"202702": 0.5}}, "bad": {}}, undo=1)
    empty_shell = edit_grid.shell_data(
        "demo_grid", None, None, base_key="", changes_label="적용 전 변경"
    )
    empty_feed = encode_feed(None, None, None, host="demo_grid", base_key="", acks={}, toast=None)
    result = run_node(
        FAKE_DOM + mountable(edit_grid.registered_js()),
        RUNNER_ACKS,
        {
            "shell": shell,
            "feed": feed,
            "feed2": feed2,
            "emptyShell": empty_shell,
            "emptyFeed": empty_feed,
        },
    )
    assert result["firstEdit"] == {"sent": 1, "box": 1, "seqs": [1]}
    assert result["inFlight"] == {"sent": 1}, "ack 전에 탭을 바꿔도 같은 op 를 다시 보내지 않는다"
    assert result["readView"] == {"box": 0, "model": None}, "읽기 보기 회차의 ack 로 출납이 빈다"
    assert result["readViewHidden"] == {"sent": 1}
    assert result["batched"] == {"sent": 1, "box": 1}
    assert result["flushed"] == {"sent": 2, "seqs": [2]}, "묶음 안의 op 는 탭을 바꾸면 보낸다"
    assert result["timed"] == {"sent": 3, "seqs": [2, 3]}, "보낼 때는 ack 안 된 op 전부를 싣는다"
    assert result["cleanup"] == {"sent": 3}, "정리 함수는 이미 보낸 op 를 다시 보내지 않는다"


RUNNER_BURST = (
    RUNNER_ACKS[: RUNNER_ACKS.index("const R = {}")]
    + r"""
const R = {}
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const editor = q('.eg-ed')
  // 브라우저처럼 — 초점 든 칸을 숨기면 대상 없는 focusout 이 난다(초점을 먼저 옮기면 나지 않는다).
  let hidden = editor.hidden
  Object.defineProperty(editor, 'hidden', {
    get: () => hidden,
    set(value) {
      hidden = value
      if (value && document.activeElement === editor) {
        document.activeElement = null
        fire(editor, 'focusout', { relatedTarget: null })
      }
    },
  })
  const typing = (value, leave) => {
    key(scroller, 'Enter')
    editor.value = value
    leave()
  }
  const xOf = (c) => S.lefts[c] + S.widths[c] / 2
  const yOf = (r) => S.headH + r * S.rowH + S.rowH / 2
  const press = (r, c) => {
    const at = { clientX: xOf(c), clientY: yOf(r), pointerId: 1 }
    fire(scroller, 'pointerdown', at)
    fire(scroller, 'pointerup', at)
  }
  // 앞서 고친 칸이 있는 표 — 첫 편집을 곧바로 보내는 갈래를 타지 않는다.
  const enter = () => key(editor, 'Enter')
  for (const value of ['61%', '62%', '63%', '64%', '65%', '66%']) typing(value, enter)
  const active = () => document.activeElement === scroller
  R.enter = { sent: sent.length, box: S.box.ops.length, active: active() }
  await tick(360)
  R.enterQuiet = { sent: sent.length, ops: sent[sent.length - 1].ops.length }
  for (const value of ['71%', '72%', '73%']) typing(value, () => key(editor, 'Tab'))
  R.tab = { sent: sent.length }
  await tick(360)
  R.tabQuiet = { sent: sent.length }
  for (let r = 0; r < 3; r += 1) typing('8' + r + '%', () => press(r, 4))
  R.press = { sent: sent.length, edit: S.edit, active: active() }
  await tick(360)
  R.pressQuiet = { sent: sent.length }
  // 칸 편집 취소도 묶음을 끊지 않는다.
  typing('91%', enter)
  key(scroller, 'Enter')
  key(editor, 'Escape')
  R.cancel = { sent: sent.length, active: active() }
  await tick(360)
  R.cancelQuiet = { sent: sent.length }
  // 진짜로 표 밖을 누르면 — 초점이 먼저 나가고 blur 뒤 focusout 이 온다 — 기다리지 않고 보낸다.
  typing('92%', () => {
    document.activeElement = null
    fire(editor, 'blur', { relatedTarget: null })
    fire(editor, 'focusout', { relatedTarget: null })
  })
  R.outside = { sent: sent.length, edit: S.edit }
  // 창이 숨어도 기다리지 않고 보낸다.
  typing('93%', enter)
  const queued = sent.length
  fireDoc('visibilitychange')
  R.hidden = { queued, sent: sent.length }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_burst_of_cell_edits_goes_out_once_after_the_quiet_time() -> None:
    """칸을 잇달아 고치면 보냄은 300ms 묶음 한 번이다(UI-PRF-02 「연속 N회 → 보냄 1회」). 확정이
    초점 든 편집 칸을 숨기면 브라우저가 대상 없는 focusout 을 내고, 그것을 표 밖으로 나간 것으로
    읽어 칸마다 회차가 돌았다(u4-02 — 기준 정보 10칸 7회차, 샘플 관측). 진짜로 표 밖을 누른 때와
    창이 숨을 때는 지금처럼 곧바로 보낸다."""
    shell, index = _shell(SPEC, _frame(), "k1")
    feed = _feed(index, "k1", {"cells": {"DEMO_B\x1f양산": {"202702": 0.5}}, "bad": {}}, undo=1)
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_BURST, {"shell": shell, "feed": feed})
    assert result["enter"] == {"sent": 0, "box": 6, "active": True}
    assert result["enterQuiet"] == {"sent": 1, "ops": 6}, "Enter 연속 6칸 → 보냄 1회"
    assert result["tab"] == {"sent": 1}
    assert result["tabQuiet"] == {"sent": 2}, "Tab 연속 3칸 → 보냄 1회"
    assert result["press"] == {"sent": 2, "edit": None, "active": True}
    assert result["pressQuiet"] == {"sent": 3}, "칸을 눌러 옮긴 3칸 → 보냄 1회"
    assert result["cancel"] == {"sent": 3, "active": True}
    assert result["cancelQuiet"] == {"sent": 4}, "칸 편집 취소는 묶음을 끊지 않는다"
    assert result["outside"] == {"sent": 5, "edit": None}, "표 밖 누름은 곧바로 보낸다"
    assert result["hidden"] == {"queued": 5, "sent": 6}, "창이 숨으면 곧바로 보낸다"


RUNNER_NEW_GEN = (
    RUNNER_ACKS[: RUNNER_ACKS.index("const R = {}")]
    + r"""
const R = {}
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const newGen = Object.assign({}, input.feed, { gen: 'g2' })
  edit('61%')
  await tick(360)
  R.sentOne = { sent: sent.length, seqs: seqs() }
  // 적용이 도는 사이 친 칸 — 묶음이 든 채 새 세대가 온다.
  edit('62%')
  edit('63%')
  sendFeed(newGen)
  R.newGen = { sent: sent.length, box: S.box.ops.length, previews: S.pending.size, gen: S.gen }
  edit('64%')
  await tick(360)
  R.quiet = { sent: sent.length }
  R.outbox = sent[sent.length - 1]
  sendFeed(Object.assign({}, newGen, { acks: { [S.mount]: 4 }, toast: { id: 1, text: '셌다' } }))
  R.acked = { box: S.box.ops.length, toast: S.dom.toast.hidden ? '' : S.dom.toast.textContent }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_ops_held_by_the_batch_when_the_table_renews_are_sent_and_counted() -> None:
    """세대가 바뀌어도 보낼 목록에서 빼지 않는다. 묶음이 든 op 는 묶음이 끝나 나가고, 이미 보낸 op
    도 함께 실린다 — 서버가 옛 세대를 세어 알리고 ack 가 지운다. 전에는 브라우저가 묶음이 든 op 를
    말없이 뺐다(「변경사항 적용」 이 도는 사이 잇달아 친 칸이 토스트 없이 사라졌다, 샘플 관측)."""
    shell, index = _shell(SPEC, _frame(), "k1")
    feed = _feed(index, "k1", {"cells": {"DEMO_B\x1f양산": {"202702": 0.5}}, "bad": {}}, undo=1)
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_NEW_GEN, {"shell": shell, "feed": feed})
    assert result["sentOne"] == {"sent": 1, "seqs": [1]}
    assert result["newGen"] == {"sent": 1, "box": 3, "previews": 0, "gen": "g2"}
    assert result["quiet"] == {"sent": 2}
    outbox = result["outbox"]
    assert [(op["seq"], op["gen"]) for op in outbox["ops"]] == [
        (1, "g1"),
        (2, "g1"),
        (3, "g1"),
        (4, "g2"),
    ]
    assert result["acked"] == {"box": 0, "toast": "셌다"}
    ops, _ = eg.new_ops({"demo_grid": outbox}, {})
    history: eg.HistoryState = {"gen": "g2", "undo": [], "redo": []}
    applied = eg.apply_ops(index, SPEC, None, history, ops)
    assert applied.toasts == [eg.DROPPED_TOAST.format(n="3")], "서버가 옛 세대 셋을 센다"
    assert eg.change_counts(applied.draft)[0] == 1, "새 세대 칸은 들어간다"


RUNNER_FILTERED_PASTE = (
    RUNNER_ACKS[: RUNNER_ACKS.index("const R = {}")]
    + r"""
const R = {}
const paste = (scroller, text) => fire(scroller, 'paste', {
  clipboardData: { getData: () => text },
})
;(async () => {
  sendFeed(input.filtered)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const note = () => q('.eg-note').textContent
  const ops = () => S.box.ops.map((op) => [op.rows, op.cols, op.values])
  const seen = () => ({ rows: S.view.order.length, ops: ops(), note: note() })
  R.shown = S.view.order.length
  paste(scroller, '1\t2\n3\t4\n5\t6\n')
  R.many = seen()
  paste(scroller, '1\r\n2\r\n')
  R.column = seen()
  paste(scroller, '11%\t12%\r\n')
  R.oneRow = seen()
  paste(scroller, '21%\r\n')
  R.oneCell = seen()
  sendFeed(input.whole)
  R.wholeShown = S.view.order.length
  paste(scroller, '31%\n32%\n')
  R.wholeMany = seen()
  // 큰 표는 서버가 필터로 고른 줄만 싣는다 — 보기 줄 수가 실은 줄 수와 같아도 좁힌 표다.
  sendFeed(input.capped)
  mount(input.cappedShell)
  const before = S.box.ops.length
  R.cappedShown = [S.view.order.length, S.model.rows]
  paste(scroller, '41%\n42%\n')
  R.capped = { added: S.box.ops.length - before, note: note() }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_filtered_table_takes_one_row_of_paste_only() -> None:
    """필터로 좁힌 표에 여러 줄을 붙이면 덩어리 줄이 보이는 줄에 차례로 들어가 다른 공정 값이
    바뀐다 — 다섯 줄이 보이는 두 줄에 6칸 들어갔다(샘플 관측). 여러 줄은 막고 까닭을 상태 줄에
    적는다. 한 줄 붙여넣기는 그대로 되고, 필터가 없는 표는 전처럼 여러 줄을 받는다."""
    frame = _frame()
    shell, index = _shell(SPEC, frame, "k1")
    codes = {str(value): code for code, value in enumerate(shell["dims"][0])}
    picked = {"0": [codes["DEMO_A"], codes["DEMO_C"]]}
    whole = _feed(index, "k1", None)
    filtered = {**whole, "filters": picked}
    capped_shell, capped_index = _shell(SPEC, frame[frame["공정"] != "DEMO_B"], "k2")
    capped_codes = {str(value): code for code, value in enumerate(capped_shell["dims"][0])}
    capped = {
        **_feed(capped_index, "k2", None),
        "filters": {"0": [capped_codes["DEMO_A"], capped_codes["DEMO_C"]]},
    }
    result = run_node(
        FAKE_DOM + mountable(edit_grid.registered_js()),
        RUNNER_FILTERED_PASTE,
        {
            "shell": shell,
            "filtered": filtered,
            "whole": whole,
            "capped": capped,
            "cappedShell": capped_shell,
        },
    )
    refused = str(edit_grid.texts(SPEC, changes_label="적용 전 변경")["pasteFiltered"])
    assert "Excel 붙여넣기" in refused and "필터" in refused
    assert result["shown"] == 2
    assert result["many"] == {"rows": 2, "ops": [], "note": refused}, "여러 줄은 막는다"
    assert result["column"] == {"rows": 2, "ops": [], "note": refused}, "한 칸 여러 줄도 막는다"
    assert result["oneRow"]["ops"] == [
        [["DEMO_A\x1f양산"], ["202701", "202702"], [["11%", "12%"]]]
    ], "한 줄은 그대로 붙는다"
    assert result["oneRow"]["note"] == "2칸 붙여넣음"
    assert result["oneCell"]["ops"][-1][2] == [["21%"]], "끝 줄바꿈 하나는 여러 줄이 아니다"
    assert result["wholeShown"] == 3
    assert result["wholeMany"]["ops"][-1][2] == [["31%"], ["32%"]], "필터가 없으면 여러 줄을 받는다"
    assert result["cappedShown"] == [2, 2]
    assert result["capped"] == {"added": 0, "note": refused}, "서버가 좁힌 큰 표도 막는다"
