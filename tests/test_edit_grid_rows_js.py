# Purpose: 범용 편집 그리드 줄 갈래 JS(글 · 고르기 칸 · 줄 잠금 · 줄 지우기)를 node 로 본다.

"""줄 규칙 표의 등록(`components/edit_grid.ROWS_JS_PARTS` — `eg_rows.js` 를 더 실음)을 브라우저 없이
본다. 글 · 고르기 칸 다듬기는 Python 과 같은 사례 표의 쌍둥이 시험이고, 줄 잠금 · 줄 지우기 단추 ·
지운 줄 표지 · 고르기 목록 · 변경 목록 되살리기는 등록 JS 전체를 가짜 DOM(`tests/edit_grid_node.
FAKE_DOM`)에 마운트해 본다. 껍데기 · feed 는 Python 이 지은 그대로 넘긴다. 값은 모두 합성이다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from edit_grid_node import FAKE_DOM, RUNNER_HEAD, asset, mountable, run_node, section
from test_edit_grid_rows import RULES, SPEC, _frame

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import build_base, encode_base, encode_feed

KINDS = json.loads(
    (Path(__file__).parent / "fixtures" / "edit_grid_cases.json").read_text(encoding="utf-8")
)["kinds"]
ROWS = asset("eg_rows.js")
PURE = asset("eg_pure.js")


def test_text_and_choice_parsing_match_python_for_every_case() -> None:
    """쌍둥이 — `kinds` 사례의 다듬기 · 표시를 JS 가 Python 과 같은 답으로 낸다."""
    runner = (
        RUNNER_HEAD
        + """
const formats = input.formats
done({
  coerce: input.coerce.map((c) => parseInput(c.raw, formats[c.fmt], c.template)),
  format: input.format.map((c) => formatValue(c.value, formats[c.fmt])),
})
"""
    )
    source = section(PURE, "eg-format") + section(ROWS, "eg-kinds")
    result = run_node(source, runner, KINDS)
    for case, got in zip(KINDS["coerce"], result["coerce"], strict=True):
        assert [got["value"], got["error"], got["text"]] == [
            case["value"],
            case["error"],
            case["text"],
        ], case
    assert result["format"] == [case["text"] for case in KINDS["format"]]


def test_the_row_plan_skips_locked_rows_and_restores_only_removed_ones() -> None:
    runner = (
        RUNNER_HEAD
        + """
const locks = input.locks
const keys = ['demo.a', 'demo.me', '+1', '+2']
done([
  rowPlan([0, 2], keys, locks, new Set()),
  rowPlan([0], keys, locks, new Set([0])),
  rowPlan([0, 2], keys, locks, new Set([0])),
  rowPlan([1], keys, locks, new Set()),
  rowRule(null, 0),
])
"""
    )
    locks = build_base(_frame(), SPEC, None, RULES).body["locks"]
    source = section(PURE, "eg-format") + section(ROWS, "eg-kinds")
    result = run_node(source, runner, {"locks": locks})
    assert result == [
        {"keys": ["demo.a", "+1"], "restore": False, "why": ""},
        {"keys": ["demo.a"], "restore": True, "why": ""},
        {"keys": ["demo.a", "+1"], "restore": False, "why": ""},
        {"keys": [], "restore": False, "why": "나 자신은 못 지움"},
        None,
    ]


def _shell(key: str) -> tuple[dict[str, Any], eg.GridIndex]:
    base = build_base(_frame(), SPEC, None, RULES)
    shell = encode_base(
        base.body,
        host="demo_rows",
        base_key=key,
        texts=edit_grid.texts(SPEC, changes_label="저장 전 변경"),
        palette={"text": "black-ink"},
        row_height=30,
    )
    return shell, base.index


def _feed(index: eg.GridIndex, key: str, draft: eg.DraftState | None) -> dict[str, Any]:
    history: eg.HistoryState = {"gen": "g1", "undo": [], "redo": []}
    return encode_feed(index, draft, history, host="demo_rows", base_key=key, acks={}, toast=None)


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
const has = (r, c, name) => cell(r, c).classList.contains(name)
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const lastOps = () => (sent.length ? sent[sent.length - 1][1].ops : [])
const R = {}
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const button = q('.eg-tb-rows')
  R.first = {
    texts: [0, 1, 2, 3].map((r) => [1, 2, 3].map((c) => cell(r, c).textContent)),
    locked: [[0, 1], [0, 3], [1, 3], [2, 1]].map(([r, c]) => has(r, c, 'is-locked')),
    text: [has(0, 1, 'is-text'), has(0, 3, 'is-text')],
    titles: [cell(0, 1).title || '', cell(0, 3).title || '', cell(1, 3).title || ''],
    where: q('.eg-where').textContent,
    button: [button.hidden, button.textContent, button.getAttribute('aria-disabled')],
  }
  // 잠긴 칸은 편집이 열리지 않고 그 까닭이 상태 줄에 선다.
  setRange(S, { r: 0, c: 1 }, { r: 0, c: 1 })
  key(scroller, 'Enter')
  R.lockedEdit = [q('.eg-ed').hidden, q('.eg-note').textContent]
  // 나 자신 줄 — 줄 지우기가 잠기고 풍선이 까닭이다.
  setRange(S, { r: 1, c: 3 }, { r: 1, c: 3 })
  R.selfButton = [button.getAttribute('aria-disabled'), button.title]
  fire(button, 'click')
  R.selfPress = [q('.eg-note').textContent, sent.length]
  // 고르기 칸 — 편집을 열면 칸 아래 항목 목록 전부(지금 값 강조 · 글 전체 고름), ↓ 가 강조를
  // 다음 항목으로(편집기 글은 그대로), Enter 가 강조한 항목으로 확정.
  setRange(S, { r: 0, c: 3 }, { r: 0, c: 3 })
  key(scroller, 'Enter')
  const list = q('.eg-choices')
  R.choiceOpen = [
    list.hidden, list.children.map((n) => n.textContent), q('.eg-ed').value,
    list.children.map((n) => n.classList.contains('is-on')), q('.eg-ed').selection,
  ]
  key(q('.eg-ed'), 'ArrowDown')
  R.choiceDown = [q('.eg-ed').value, list.children.map((n) => n.classList.contains('is-on'))]
  key(q('.eg-ed'), 'Enter')
  R.choiceCommit = { op: lastOps()[0], hidden: list.hidden, text: cell(0, 3).textContent }
  // 마우스 — 칸 위에 뜬 목록의 항목을 누르면 그 항목으로 확정한다(뿌리의 칸 누름으로 새지 않는다).
  setRange(S, { r: 0, c: 3 }, { r: 0, c: 3 })
  key(scroller, 'Enter')
  const over = { clientX: S.lefts[3] + 5, clientY: S.headH + S.rowH * 1.5, pointerId: 1 }
  const item = list.children[2]
  const down = fire(item, 'pointerdown', over)
  fire(item, 'mousedown', over)
  fire(item, 'click', over)
  R.choiceMouse = {
    stopped: down.stopped, op: S.box.ops[S.box.ops.length - 1], hidden: list.hidden,
    text: cell(0, 3).textContent, focus: [S.focus.r, S.focus.c],
  }
  // 새 줄 계정 칸에 틀린 꼴 — 미리보기가 빨간 칸.
  setRange(S, { r: 2, c: 1 }, { r: 2, c: 1 })
  key(scroller, 'B')
  q('.eg-ed').value = 'Bad Name'
  key(q('.eg-ed'), 'Enter')
  R.badPreview = [has(2, 1, 'is-error'), cell(2, 1).textContent]
  // 명단 줄을 고르고 줄 지우기 — remove op.
  setRange(S, { r: 0, c: 2 }, { r: 0, c: 2 })
  R.removeButton = [button.textContent, button.getAttribute('aria-disabled')]
  fire(button, 'click')
  await tick(360)
  R.removeOp = lastOps().find((op) => op.op === 'remove')
  // feed 가 지운 줄을 싣고 오면 지움선 · 잠김, 단추는 되살리기, 변경 목록 맨 앞에 「줄 지움」.
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: 99 } }))
  R.removed = {
    marks: [has(0, 0, 'is-removed'), has(0, 3, 'is-removed'), has(1, 3, 'is-removed')],
    button: button.textContent,
    lockedWhy: S.lockAt(S, 0, 2),
  }
  fire(q('.eg-tb-changes'), 'click')
  const first = q('.eg-drawer-list').children[0]
  R.drawer = first.textContent
  fire(first.querySelector('.eg-chg-x'), 'click')
  R.restoreOp = lastOps().find((op) => op.op === 'restore')
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_the_row_feature_locks_cells_lists_choices_and_removes_rows() -> None:
    shell, index = _shell("k1")
    removed: eg.DraftState = {"cells": {"demo.a": {eg.ROW_REMOVED: 1.0}}, "bad": {}}
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))
    result = run_node(
        source,
        RUNNER,
        {"shell": shell, "feed": _feed(index, "k1", None), "feed2": _feed(index, "k1", removed)},
    )
    first = result["first"]
    assert first["texts"] == [
        ["demo.a", "데모 가", "열람"],
        ["demo.me", "", "개발자"],
        ["", "", ""],
        ["", "", ""],
    ]
    assert first["locked"] == [True, False, True, False]
    assert first["text"] == [True, True]
    assert first["titles"] == ["명단 칸은 잠김", "", "나 자신"], "잠긴 칸은 까닭 풍선"
    assert first["where"].startswith("데모 명단 › demo.a · 계정")
    assert first["button"] == [False, "줄 지우기", "false"]
    assert result["lockedEdit"] == [True, "명단 칸은 잠김"]
    assert result["selfButton"] == ["true", "나 자신은 못 지움"]
    assert result["selfPress"][0] == "나 자신은 못 지움"
    assert result["choiceOpen"] == [
        False,
        ["열람", "실무자", "관리자", "개발자"],
        "열람",
        [True, False, False, False],
        [0, 2],
    ]
    assert result["choiceDown"] == ["열람", [False, True, False, False]]
    commit = result["choiceCommit"]
    assert commit["op"]["op"] == "write" and commit["op"]["values"] == [["실무자"]]
    assert commit["op"]["rows"] == ["demo.a"] and commit["op"]["cols"] == ["등급"]
    assert commit["hidden"] is True and commit["text"] == "실무자"
    mouse = result["choiceMouse"]
    assert mouse["stopped"] is True, "목록 pointerdown 은 칸 누름으로 새지 않는다"
    assert mouse["op"]["op"] == "write" and mouse["op"]["values"] == [["관리자"]]
    assert mouse["op"]["rows"] == ["demo.a"] and mouse["op"]["cols"] == ["등급"]
    assert mouse["hidden"] is True and mouse["text"] == "관리자" and mouse["focus"] == [0, 3]
    assert result["badPreview"] == [True, "Bad Name"]
    assert result["removeButton"] == ["줄 지우기", "false"]
    assert result["removeOp"]["rows"] == ["demo.a"]
    assert result["removed"]["marks"] == [True, True, False]
    assert result["removed"]["button"] == "줄 되살리기"
    assert result["removed"]["lockedWhy"].startswith("지운 줄입니다")
    assert "demo.a · 줄 지움" in result["drawer"]
    assert result["restoreOp"]["rows"] == ["demo.a"]


PASTE_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const paste = (text) => fire(scroller, 'paste', { clipboardData: { getData: () => text } })
  // 새 줄 1 의 계정 칸에서 세 줄을 붙인다 — 새 줄은 둘뿐이라 통째로 거절한다(잘라 붙이지 않는다).
  setRange(S, { r: 2, c: 1 }, { r: 2, c: 1 })
  const before = S.box.ops.length
  paste('demo.x\t관리자\r\ndemo.y\t열람\r\ndemo.z\t열람\r\n')
  R.short = [S.box.ops.length === before, q('.eg-note').textContent]
  // 둘이면 들어간다.
  paste('demo.x\r\ndemo.y\r\n')
  R.fits = S.box.ops.length > before ? S.box.ops[S.box.ops.length - 1] : null
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_paste_longer_than_the_new_rows_is_refused_whole() -> None:
    """줄 규칙 표 — 붙일 줄이 표 끝(빈 새 줄)을 넘으면 앞 몇 줄만 넣고 나머지를 조용히 버리지 않고
    통째로 거절하고 모자란 줄 수를 알린다(`pasteGuard`). 맞으면 그대로 붙는다."""
    shell, index = _shell("k1")
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(source, PASTE_RUNNER, {"shell": shell, "feed": _feed(index, "k1", None)})

    assert result["short"] == [
        True,
        "새 줄이 1줄 모자라 붙이지 않았습니다 — 나눠 붙이면 새 줄이 늘어납니다",
    ]
    assert result["fits"]["op"] == "write" and result["fits"]["rows"] == ["+1", "+2"]


LOCKED_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const paste = (text) => fire(scroller, 'paste', { clipboardData: { getData: () => text } })
  // 한 동작 뒤 쌓인 op 와 상태 줄 — 줄마다 op 를 비운다.
  const after = (act) => {
    S.box.ops.length = 0
    q('.eg-note').textContent = ''
    act()
    const op = S.box.ops[S.box.ops.length - 1]
    return [op ? op.op : null, q('.eg-note').textContent]
  }
  const pick = (r0, r1) => setRange(S, { r: r0, c: 3 }, { r: r1, c: 3 })
  // 나 자신 줄(1) 등급 칸만 — 붙여넣기 · Delete · Ctrl+D 모두 보내지 않고 그 까닭.
  R.onlyLocked = [
    after(() => { pick(1, 1); paste('관리자') }),
    after(() => { pick(1, 1); key(scroller, 'Delete') }),
    after(() => { pick(0, 1); key(scroller, 'd', { ctrlKey: true, code: 'KeyD' }) }),
  ]
  // 열린 줄(0)과 잠긴 줄(1)을 함께 — 보내되 상태 줄은 건너뛴 칸을 뺀 수와 건너뛴 수.
  R.mixed = [
    after(() => { pick(0, 1); paste('관리자') }),
    after(() => { pick(0, 0); paste('관리자\r\n열람\r\n') }),
    after(() => { pick(0, 1); key(scroller, 'Delete') }),
  ]
  // 지운 줄(0)은 서버가 쓰고 세지 않는다 — 브라우저도 잠긴 칸으로 세지 않는다.
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: 99 } }))
  R.removed = [
    after(() => { pick(0, 2); key(scroller, 'Delete') }),
    after(() => { pick(0, 0); paste('관리자') }),
  ]
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_paste_delete_and_fill_skip_locked_rows_and_say_so() -> None:
    """줄 규칙이 잠근 칸(나 자신 줄 등급 칸)에 붙여넣기 · Delete · Ctrl+D 를 하면 서버가 그 칸을
    건너뛰는데 상태 줄은 「1칸 붙여넣음 / 1칸 비움」 이었다(2026-11-18 E2E — 토스트는 「잠긴 칸
    1칸은 건너뛰었습니다」). 브라우저도 잠긴 칸을 미리 센다 — 모두 잠겼으면 op 를 보내지 않고
    잠긴 칸 편집과 같은 까닭 한 줄, 섞였으면 보내고 건너뛴 칸을 뺀 수 · 건너뛴 수(서버 알림과
    같은 글)."""
    shell, index = _shell("k1")
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    removed: eg.DraftState = {"cells": {"demo.a": {eg.ROW_REMOVED: 1.0}}, "bad": {}}
    result = run_node(
        source,
        LOCKED_RUNNER,
        {"shell": shell, "feed": _feed(index, "k1", None), "feed2": _feed(index, "k1", removed)},
    )

    assert result["onlyLocked"] == [[None, "나 자신"]] * 3
    skipped = eg.LOCKED_TOAST.format(n=1)
    assert result["mixed"] == [
        ["write", f"1칸 붙여넣음 · {skipped} · 고른 범위에 되풀이"],
        ["write", f"1칸 붙여넣음 · {skipped}"],
        ["clear", f"1칸 비움 · {skipped}"],
    ]
    assert result["removed"] == [["clear", f"2칸 비움 · {skipped}"], ["write", "1칸 붙여넣음"]]


def test_the_list_filter_keeps_matching_items_with_prefix_matches_first() -> None:
    """공용 거름(2026-11-27 보드 답 「거름 더함」) — 친 글이 보이는 글 · 넣을 글에 든 항목만
    (대소문자 무시), 앞머리가 맞는 항목이 앞이고 그 안은 항목 차례다. 칸을 막 연 때(null) · 빈
    글은 전부. 강조는 같은 글(넣을 글 먼저, 다음 보이는 글 — 대소문자 그대로)뿐이다."""
    runner = (
        RUNNER_HEAD
        + """
const items = input.items.map(([label, value]) => ({ label, value }))
const names = (list) => list.map((item) => item.value)
done({
  open: names(listFilter(items, null)),
  blank: names(listFilter(items, '  ')),
  demo: names(listFilter(items, 'demo')),
  inner: names(listFilter(items, ' _b ')),
  label: names(listFilter(items, '표시')),
  none: names(listFilter(items, 'zz')),
  match: [' DEMO_B_A ', 'demo_b_a', 'C 표시', ''].map((text) => listMatch(items, text)),
})
"""
    )
    source = section(PURE, "eg-format") + section(ROWS, "eg-kinds")
    items = [
        ["A_DEMO", "A_DEMO"],
        ["DEMO_B_A", "DEMO_B_A"],
        ["C 표시", "demo_c"],
        ["X_B", "X_B"],
    ]
    result = run_node(source, runner, {"items": items})
    everything = ["A_DEMO", "DEMO_B_A", "demo_c", "X_B"]
    assert result["open"] == everything and result["blank"] == everything
    assert result["demo"] == ["DEMO_B_A", "demo_c", "A_DEMO"], "앞머리 맞음이 앞"
    assert result["inner"] == ["DEMO_B_A", "X_B"]
    assert result["label"] == ["demo_c"], "보이는 글로도 거른다"
    assert result["none"] == []
    assert result["match"] == [1, -1, 2, -1]


REFS = tuple(f"DEMO_REF_{k:03d}" for k in range(60))
LIST_SPEC = eg.GridSpec(
    "DEMO_LIST",
    "데모 공정",
    ("No.",),
    ("공정", "참조", "Area"),
    eg.ValueFormat("text", 0),
    column_formats=(
        ("공정", eg.ValueFormat("text", 0, max_length=8)),
        ("참조", eg.ValueFormat("choice", 0, options=REFS)),
        ("Area", eg.ValueFormat("choice", 0, options=("Main", "MI"))),
    ),
    id_column="_id",
    label_column="_label",
    row_ops=True,
)
LIST_RULES = eg.RowRules((eg.LockKind(fresh=True),), (-1, -1, 0))


def _list_shell() -> tuple[dict[str, Any], eg.GridIndex]:
    frame = pd.DataFrame(
        {
            "No.": ["1", "2", "새 1"],
            "_id": ["p1", "p2", "+1"],
            "_label": ["DEMO_A", "DEMO_B", "새 줄 1"],
            "공정": ["DEMO_A", "DEMO_B", None],
            "참조": [3.0, 12.0, None],
            "Area": [0.0, 1.0, None],
        }
    )
    base = build_base(frame, LIST_SPEC, None, LIST_RULES)
    shell = encode_base(
        base.body,
        host="demo_rows",
        base_key="k1",
        texts=edit_grid.texts(LIST_SPEC, changes_label="적용 전 변경"),
        palette={"text": "black-ink"},
        row_height=30,
    )
    return shell, base.index


LIST_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const list = q('.eg-choices')
  const ed = () => q('.eg-ed')
  // 목록 높이 상한 안의 굴림 — 보이는 높이를 항목 다섯(24px)으로 둔다.
  list.clientHeight = 120
  const type = (text) => {
    ed().value = text
    fire(ed(), 'input')
  }
  const view = () => ({
    n: list.children.length,
    hidden: list.hidden,
    first: list.children.length ? list.children[0].textContent : '',
    on: list.children.findIndex((n) => n.classList.contains('is-on')),
    top: list.scrollTop,
    value: ed().value,
  })
  const open = (r, c) => {
    setRange(S, { r, c }, { r, c })
    key(scroller, 'Enter')
  }
  // 칸을 연 때 — 후보 60개 전부, 지금 값(DEMO_REF_012) 강조가 보이게 굴린다.
  open(1, 2)
  R.open = view()
  // ↓ 열 번 — 강조가 보이는 자리로 따라 굴린다. 사용자가 목록을 굴린 뒤 다시 그려도 굴림은
  // 그대로다(강조가 그대로면).
  for (let k = 0; k < 10; k += 1) key(ed(), 'ArrowDown')
  R.down = view()
  list.scrollTop = 0
  paint(S)
  R.repaint = view()
  key(ed(), 'ArrowUp')
  R.up = view()
  key(ed(), 'Escape')
  R.escape = [list.hidden, S.edit]
  // 친 글로 거름 — 강조 없음, ↓ 가 거른 목록 첫 항목, Enter 가 그 항목.
  open(0, 2)
  type('ref_01')
  R.typed = view()
  key(ed(), 'ArrowDown')
  key(ed(), 'ArrowDown')
  R.typedDown = view()
  key(ed(), 'Enter')
  R.typedCommit = [S.box.ops[S.box.ops.length - 1].values, list.hidden, cell(0, 2).textContent]
  // ↑ 는 강조가 없으면 끝 항목, 처음에서 ↑ 는 끝으로 돈다.
  open(0, 2)
  type('ref_00')
  key(ed(), 'ArrowUp')
  R.upFromNone = view()
  key(ed(), 'ArrowDown')
  R.wrapDown = view().on
  key(ed(), 'ArrowUp')
  R.wrapUp = view().on
  key(ed(), 'Escape')
  // 글자로 연 칸은 그 글로 거르고 강조가 없다. ↓ 뒤에도 blur 는 친 글 그대로(자동 고름 없음) —
  // 목록 밖 글은 고르기 오류 칸.
  setRange(S, { r: 1, c: 2 }, { r: 1, c: 2 })
  key(scroller, 'D')
  R.typedOpen = view()
  key(ed(), 'ArrowDown')
  fire(ed(), 'blur')
  const lastValues = () => S.box.ops[S.box.ops.length - 1].values
  R.blur = [lastValues(), has(1, 2, 'is-error'), q('.eg-where').textContent]
  // 칸마다 오류 글 — Area 고르기 · 공정 글자 수.
  setRange(S, { r: 1, c: 3 }, { r: 1, c: 3 })
  key(scroller, 'x')
  key(ed(), 'Enter')
  setRange(S, { r: 1, c: 3 }, { r: 1, c: 3 })
  R.areaWhere = q('.eg-where').textContent
  setRange(S, { r: 2, c: 1 }, { r: 2, c: 1 })
  key(scroller, '1')
  type('123456789')
  key(ed(), 'Enter')
  setRange(S, { r: 2, c: 1 }, { r: 2, c: 1 })
  R.lenWhere = q('.eg-where').textContent
  // 마우스 — 목록 자체(굴림 막대 자리) 누름은 칸 누름으로 새지 않고 편집도 닫지 않는다. 그 뒤
  // 항목 누름이 확정한다.
  open(0, 3)
  const over = { clientX: S.lefts[3] + 5, clientY: S.headH + S.rowH * 1.5 }
  const bar = fire(list, 'pointerdown', over)
  const keep = fire(list, 'mousedown')
  R.bar = [bar.stopped, keep.defaultPrevented, Boolean(S.edit), list.hidden]
  key(ed(), 'Escape')
  open(0, 2)
  list.scrollTop = 600
  fire(list.children[30], 'pointerdown')
  fire(list.children[30], 'mousedown')
  fire(list.children[30], 'click')
  R.pick = [S.box.ops[S.box.ops.length - 1].values, list.hidden, cell(0, 2).textContent]
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_long_choice_list_filters_scrolls_and_keeps_typed_text_on_blur() -> None:
    """고르기 후보 60개(spike-grid 2장 꼴) — 칸을 연 때 전부와 지금 값 강조, ↑ ↓ 는 거른 목록 안에서
    강조만 옮기고(끝에서 돎) 강조가 보이는 자리로 목록을 굴린다(높이 상한 안). 다시 그려도 사용자가
    굴린 자리는 그대로다. 친 글로 거르고 Enter 는 강조한 항목, blur 는 친 글 그대로(2026-11-27 총괄
    결정 R2). 오류 글은 칸마다 맞고 긴 목록은 줄인다(spike 2-6 · 2-7). 목록 자체 누름(굴림 막대)은
    편집을 닫지 않는다(bdff5a6b 마우스 확정 유지)."""
    shell, index = _list_shell()
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(source, LIST_RUNNER, {"shell": shell, "feed": _feed(index, "k1", None)})

    assert result["open"] == {
        "n": 60,
        "hidden": False,
        "first": "DEMO_REF_000",
        "on": 12,
        "top": 12 * 24 + 24 - 120,
        "value": "DEMO_REF_012",
    }
    assert result["down"]["on"] == 22 and result["down"]["top"] == 22 * 24 + 24 - 120
    assert result["down"]["value"] == "DEMO_REF_012", "↓ 는 편집기 글을 바꾸지 않는다"
    assert result["repaint"]["top"] == 0 and result["repaint"]["on"] == 22
    assert result["up"]["on"] == 21 and result["up"]["top"] == 21 * 24 + 24 - 120
    assert result["escape"] == [True, None]
    assert result["typed"]["n"] == 10 and result["typed"]["first"] == "DEMO_REF_010"
    assert result["typed"]["on"] == -1 and result["typed"]["top"] == 0
    assert result["typedDown"]["on"] == 1 and result["typedDown"]["value"] == "ref_01"
    assert result["typedCommit"] == [[["DEMO_REF_011"]], True, "DEMO_REF_011"]
    assert result["upFromNone"]["on"] == 9 and result["upFromNone"]["n"] == 10
    assert [result["wrapDown"], result["wrapUp"]] == [0, 9]
    assert result["typedOpen"]["n"] == 60 and result["typedOpen"]["on"] == -1
    assert result["typedOpen"]["value"] == "D"
    values, error, where = result["blur"]
    assert values == [["D"]] and error is True
    assert where.endswith(
        "참조 — DEMO_REF_000 · DEMO_REF_001 · DEMO_REF_002 … 60개 가운데 하나를 적습니다"
    )
    assert result["areaWhere"].endswith("Area — Main · MI 가운데 하나를 적습니다")
    assert result["lenWhere"].endswith("공정 — 8자 이하로 적습니다")
    assert result["bar"] == [True, True, True, False]
    assert result["pick"] == [[["DEMO_REF_030"]], True, "DEMO_REF_030"]


IME_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const list = q('.eg-choices')
  const ed = q('.eg-ed')
  const shown = () => list.children.map((n) => n.textContent)
  // 한글은 글자로 칸을 열지 못한다(조합 키) — Enter 로 열고 글 전체가 골라져 있어 조합 글이
  // 갈아 쓴다.
  setRange(S, { r: 0, c: 3 }, { r: 0, c: 3 })
  key(scroller, 'Enter')
  fire(ed, 'compositionstart')
  ed.value = '관'
  fire(ed, 'input', { isComposing: true })
  R.composing = shown()
  key(ed, 'Enter', { isComposing: true })
  R.stillEditing = Boolean(S.edit)
  ed.value = '관리'
  fire(ed, 'input', { isComposing: true })
  fire(ed, 'compositionend')
  R.ended = shown()
  ed.value = '자'
  fire(ed, 'compositionend')
  R.endOnly = shown()
  key(ed, 'ArrowDown')
  key(ed, 'ArrowDown')
  key(ed, 'Enter')
  R.commit = [S.box.ops[S.box.ops.length - 1].values, cell(0, 3).textContent]
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_korean_composition_filters_the_list_as_it_goes() -> None:
    """한글 IME 조합 중에도 거름이 따라간다 — 조합 중 input(값에 조합 글이 든다)과 조합 끝
    (compositionend)에서 거르고, 조합 중 Enter 는 확정하지 않는다."""
    shell, index = _shell("k1")
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(source, IME_RUNNER, {"shell": shell, "feed": _feed(index, "k1", None)})

    assert result["composing"] == ["관리자"]
    assert result["stillEditing"] is True
    assert result["ended"] == ["관리자"]
    assert result["endOnly"] == ["실무자", "관리자", "개발자"]
    assert result["commit"] == [[["관리자"]], "관리자"]


SUGGEST_SPEC = eg.GridSpec(
    "DEMO_SUGGEST",
    "데모 공정",
    ("No.",),
    ("공정", "참조공정", "STEP_MCP"),
    eg.ValueFormat("text", 0),
    column_formats=(
        ("공정", eg.ValueFormat("text", 0)),
        ("참조공정", eg.ValueFormat("suggest", 0, max_length=20)),
        ("STEP_MCP", eg.ValueFormat("suggest", 0)),
    ),
    id_column="_id",
    label_column="_label",
    row_ops=True,
)


def _suggestions(tag: str) -> dict[str, eg.Suggestions]:
    """후보 60개(보이는 글 「<tag> nn (원본)」 · 넣을 글 원본)와 참조공정에 딸린 STEP/MCP 후보."""
    items = tuple(eg.Suggestion(f"{tag} {k:02d} ({ref})", ref) for k, ref in enumerate(REFS))
    table = {
        ref: tuple(eg.Suggestion(f"S{k}/M{j}", f"S{k}/M{j}") for j in range(2))
        for k, ref in enumerate(REFS[:3])
    }
    fallback = (eg.Suggestion("S9/M9", "S9/M9"),)
    return {
        "참조공정": eg.Suggestions(items=items),
        "STEP_MCP": eg.Suggestions(by="참조공정", table=table, items=fallback),
    }


def _suggest_shell(tag: str) -> tuple[dict[str, Any], eg.GridIndex]:
    frame = pd.DataFrame(
        {
            "No.": ["1", "2", "새 1"],
            "_id": ["p1", "p2", "+1"],
            "_label": ["DEMO_A", "DEMO_B", "새 줄 1"],
            "공정": ["DEMO_A", "DEMO_B", None],
            "참조공정": ["DEMO_REF_001", "DEMO_OLD", None],
            "STEP_MCP": ["S1/M0", None, None],
        }
    )
    base = build_base(frame, SUGGEST_SPEC, None, LIST_RULES)
    shell = edit_grid.shell_data(
        "demo_rows",
        base,
        SUGGEST_SPEC,
        base_key="k1",
        changes_label="적용 전 변경",
        suggest=_suggestions(tag),
    )
    return shell, base.index


SUGGEST_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const list = q('.eg-choices')
  const ed = () => q('.eg-ed')
  const labels = () => list.children.map((n) => n.textContent)
  const lastValues = () => S.box.ops[S.box.ops.length - 1].values
  const type = (text) => {
    ed().value = text
    fire(ed(), 'input')
  }
  const open = (r, c) => {
    setRange(S, { r, c }, { r, c })
    key(scroller, 'Enter')
  }
  const on = () => list.children.findIndex((n) => n.classList.contains('is-on'))
  // 참조공정 — 보이는 글은 「표시 nn (원본)」, 지금 값(원본)과 같은 항목이 강조, 고르면 원본을
  // 넣는다.
  open(0, 2)
  R.open = [labels().length, labels()[0], on(), ed().value]
  type('ref_00')
  key(ed(), 'ArrowDown')
  key(ed(), 'Enter')
  R.pick = [lastValues(), cell(0, 2).textContent]
  // 보이는 글로 거르고 보이는 글을 다 치면 그 항목이 강조 — Enter 가 원본을 넣는다.
  open(2, 2)
  type('표시 02 (DEMO_REF_002)')
  R.label = [labels(), on()]
  key(ed(), 'Enter')
  R.labelPick = lastValues()
  // 목록 밖 글(바탕 판 참조 · 새 글)은 그대로 칸에 남고 오류가 아니다 — 판정은 부르는 쪽.
  open(1, 2)
  R.outside = [on(), labels().length]
  type('DEMO_NEW')
  R.outsideList = list.hidden
  key(ed(), 'Enter')
  R.outsideCommit = [lastValues(), cell(1, 2).textContent, has(1, 2, 'is-error')]
  // 딸린 후보 — 그 줄 참조공정의 지금 칸(보내는 중 · 초안 포함)으로 고르고, 표에 없는 참조면
  // 기본 후보.
  open(0, 3)
  R.dep0 = labels()
  key(ed(), 'Escape')
  open(1, 3)
  R.dep1 = labels()
  key(ed(), 'Escape')
  open(2, 3)
  R.dep2 = labels()
  key(ed(), 'Escape')
  // 후보 표가 바뀐 껍데기(같은 baseKey)가 와도 모델 · 마운트 · 편집 중 칸 · 보낼 op 는 그대로이고
  // 목록만 새 벌.
  open(0, 2)
  const model = S.model
  const mountId = S.mount
  const ops = S.box.ops.length
  mount(input.shell2)
  R.swap = {
    model: S.model === model, mount: S.mount === mountId, edit: Boolean(S.edit), value: ed().value,
    ops: S.box.ops.length === ops, first: labels()[0], on: on(), cell: cell(1, 2).textContent,
  }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_suggest_cells_list_labels_put_values_and_follow_the_row() -> None:
    """글 + 후보 칸(R1) — 목록은 보이는 글, 고르면 넣을 글(원본), 목록 밖 글은 그대로 남는다.
    딸린 후보는 같은 줄 참조공정의 지금 칸(보내지 않은 초안 포함)으로 브라우저가 고른다. 후보 표가
    바뀐 껍데기는 `baseKey` 가 같아 모델을 다시 짓지 않는다 — 편집 중 칸 · 보낼 op 가 그대로다."""
    shell, index = _suggest_shell("표시")
    shell2, _ = _suggest_shell("다른")
    assert shell2["baseKey"] == shell["baseKey"] and shell2["suggest"] != shell["suggest"]
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(
        source,
        SUGGEST_RUNNER,
        {"shell": shell, "shell2": shell2, "feed": _feed(index, "k1", None)},
    )

    assert result["open"] == [60, "표시 00 (DEMO_REF_000)", 1, "DEMO_REF_001"]
    assert result["pick"] == [[["DEMO_REF_000"]], "DEMO_REF_000"]
    assert result["label"] == [["표시 02 (DEMO_REF_002)"], 0]
    assert result["labelPick"] == [["DEMO_REF_002"]]
    assert result["outside"] == [-1, 60]
    assert result["outsideList"] is True, "맞는 후보가 없으면 목록을 걷는다"
    assert result["outsideCommit"] == [[["DEMO_NEW"]], "DEMO_NEW", False]
    assert result["dep0"] == ["S0/M0", "S0/M1"], "보내는 중인 참조공정(DEMO_REF_000)을 따른다"
    assert result["dep1"] == ["S9/M9"], "표에 없는 참조는 기본 후보"
    assert result["dep2"] == ["S2/M0", "S2/M1"]
    assert result["swap"] == {
        "model": True,
        "mount": True,
        "edit": True,
        "value": "DEMO_REF_000",
        "ops": True,
        "first": "다른 00 (DEMO_REF_000)",
        "on": 0,
        "cell": "DEMO_NEW",
    }


RERUN_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const list = q('.eg-choices')
  const ed = () => q('.eg-ed')
  const on = () => list.children.findIndex((n) => n.classList.contains('is-on'))
  // 목록을 연 채 ↓ 세 번 · 목록을 굴린 뒤, 같은 내용의 껍데기(새 객체)와 ack 를 실은 feed 가
  // 오는 회차.
  setRange(S, { r: 0, c: 2 }, { r: 0, c: 2 })
  key(scroller, 'Enter')
  for (let k = 0; k < 3; k += 1) key(ed(), 'ArrowDown')
  list.scrollTop = 50
  const first = list.children[0]
  const before = [on(), list.scrollTop]
  mount(JSON.parse(JSON.stringify(input.shell)))
  sendFeed(Object.assign({}, input.feed, { acks: { [S.mount]: 0 } }))
  R.rerun = {
    before, after: [on(), list.scrollTop], same: list.children[0] === first,
    edit: Boolean(S.edit), value: ed().value,
  }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_rerun_with_the_same_candidates_keeps_the_open_list() -> None:
    """앞 칸의 묶음 보내기 회차가 목록을 연 다음 칸에 닿는 흔한 경우 — 같은 내용의 후보가 새 객체로
    와도 목록을 다시 짓지 않아 강조(↑ ↓ 로 옮긴 자리)와 사용자가 굴린 자리가 그대로다."""
    shell, index = _suggest_shell("표시")
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(source, RERUN_RUNNER, {"shell": shell, "feed": _feed(index, "k1", None)})

    assert result["rerun"] == {
        "before": [4, 50],
        "after": [4, 50],
        "same": True,
        "edit": True,
        "value": "DEMO_REF_001",
    }


def _rebased_shell(
    key: str, *, form: str | None, fresh: int
) -> tuple[dict[str, Any], eg.GridIndex]:
    """`_suggest_shell` 과 같은 표의 다른 바탕 — 새 줄 `+1` 의 STEP_MCP 양식(`form`)과 빈 새 줄 수가
    바뀌어 `baseKey` 가 다르다(부대공정 편집기에서 참조를 적은 회차 꼴)."""
    numbers = range(1, fresh + 1)
    frame = pd.DataFrame(
        {
            "No.": ["1", "2", *(f"새 {k}" for k in numbers)],
            "_id": ["p1", "p2", *(f"+{k}" for k in numbers)],
            "_label": ["DEMO_A", "DEMO_B", *(f"새 줄 {k}" for k in numbers)],
            "공정": ["DEMO_A", "DEMO_B", *([None] * fresh)],
            "참조공정": ["DEMO_REF_001", "DEMO_OLD", *([None] * fresh)],
            "STEP_MCP": ["S1/M0", None, form, *([None] * (fresh - 1))],
        }
    )
    rules = eg.RowRules((eg.LockKind(fresh=True),), (-1, -1, *([0] * fresh)))
    base = build_base(frame, SUGGEST_SPEC, None, rules)
    shell = edit_grid.shell_data(
        "demo_rows",
        base,
        SUGGEST_SPEC,
        base_key=key,
        changes_label="적용 전 변경",
        suggest=_suggestions("표시"),
    )
    return shell, base.index


REBASE_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  const scroller = q('.eg-scroll')
  const list = q('.eg-choices')
  const ed = () => q('.eg-ed')
  const labels = () => (list.hidden ? null : list.children.map((n) => n.textContent))
  const type = (text) => {
    ed().value = text
    fire(ed(), 'input')
  }
  const state = () => ({
    edit: Boolean(S.edit), value: ed().hidden ? null : ed().value, list: labels(),
    base: S.shell.baseKey, ops: S.box.ops.map((op) => [op.seq, op.cols, op.values]),
    sent: sent.length,
  })
  // 새 줄 참조공정을 적고(표의 첫 op — 곧바로 감) 같은 줄 STEP_MCP 를 글자로 연 채 반쯤 친다.
  setRange(S, { r: 2, c: 2 }, { r: 2, c: 2 })
  key(scroller, 'Enter')
  type('DEMO_REF_000')
  key(ed(), 'Enter')
  setRange(S, { r: 2, c: 3 }, { r: 2, c: 3 })
  key(scroller, 'S')
  type('S0/')
  R.typing = state()
  // 그 op 를 실은 회차 — 양식 · 새 줄 수가 바뀐 껍데기와 ack 를 실은 feed.
  mount(input.shell2)
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: 1 } }))
  await tick(5)
  R.during = Object.assign(state(), { focus: document.activeElement === ed(), rows: S.model.rows })
  type('S0/M1')
  key(ed(), 'Enter')
  await tick(5)
  R.after = Object.assign(state(), {
    rows: S.model.rows, ref: cell(2, 2).textContent, step: cell(2, 3).textContent,
    fresh: cell(3, 0).textContent,
  })
  // Esc 로 그만둔 편집도 끝에 미룬 껍데기를 받는다.
  setRange(S, { r: 0, c: 1 }, { r: 0, c: 1 })
  key(scroller, 'Enter')
  mount(input.shell3)
  await tick(5)
  R.cancelDuring = state()
  key(ed(), 'Escape')
  await tick(5)
  R.cancelAfter = state()
  // 다른 표의 껍데기는 지금처럼 편집 중 칸을 친 글로 확정하고 바꾼다.
  setRange(S, { r: 0, c: 1 }, { r: 0, c: 1 })
  key(scroller, 'X')
  mount(input.other)
  await tick(5)
  const last = S.box.ops[S.box.ops.length - 1]
  R.other = { edit: Boolean(S.edit), table: S.model.table, last: last.values }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_new_base_while_a_cell_is_open_waits_until_the_edit_ends() -> None:
    """양식 · 새 줄 수가 바뀐 같은 표의 껍데기(다른 `baseKey`)가 칸을 고치는 중에 와도 칸을
    닫지 않는다 — 친 글 · 딸린 목록 · 초점이 그대로이고 ack 도 그때 받지 않는다(받으면 보내는
    중 참조가 걷혀 딸린 목록이 비었다). 확정 · 취소 뒤 그 껍데기로 다시 짓고, 아직 ack 되지 않은
    op 의 미리보기는 새 모델에 다시 얹어 친 칸에 양식이 보이지 않는다. 다른 표의 껍데기는
    지금처럼 확정하고 바꾼다."""
    shell, index = _rebased_shell("k1", form=None, fresh=1)
    shell2, index2 = _rebased_shell("k2", form="S0/M0", fresh=2)
    shell3, _ = _rebased_shell("k3", form="S0/M0", fresh=3)
    other, _ = _list_shell()
    draft2: eg.DraftState = {"cells": {"+1": {"참조공정": "DEMO_REF_000"}}, "bad": {}}
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(
        source,
        REBASE_RUNNER,
        {
            "shell": shell,
            "shell2": shell2,
            "shell3": shell3,
            "other": other,
            "feed": _feed(index, "k1", None),
            "feed2": _feed(index2, "k2", draft2),
        },
    )

    ref_op = [1, ["참조공정"], [["DEMO_REF_000"]]]
    assert result["typing"] == {
        "edit": True,
        "value": "S0/",
        "list": ["S0/M0", "S0/M1"],
        "base": "k1",
        "ops": [ref_op],
        "sent": 1,
    }
    assert result["during"] == {
        "edit": True,
        "value": "S0/",
        "list": ["S0/M0", "S0/M1"],
        "base": "k1",
        "ops": [ref_op],
        "sent": 1,
        "focus": True,
        "rows": 3,
    }, "칸 · 친 글 · 딸린 목록 · 초점이 그대로, ack 도 미룸"
    assert result["after"] == {
        "edit": False,
        "value": None,
        "list": None,
        "base": "k2",
        "ops": [[2, ["STEP_MCP"], [["S0/M1"]]]],
        "sent": 1,
        "rows": 4,
        "ref": "DEMO_REF_000",
        "step": "S0/M1",
        "fresh": "새 2",
    }, "다 친 글 하나로 확정하고 새 바탕 · 새 줄, 보내는 중 칸은 양식이 아니라 친 글"
    assert result["cancelDuring"]["edit"] is True and result["cancelDuring"]["base"] == "k2"
    assert result["cancelAfter"]["edit"] is False and result["cancelAfter"]["base"] == "k3"
    assert result["other"] == {"edit": False, "table": "DEMO_LIST", "last": [["X"]]}


DRAWER_RUNNER = (
    RUNNER.split(";(async () => {")[0]
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  fire(q('.eg-tb-changes'), 'click')
  R.bad = q('.eg-drawer-list').children
    .filter((item) => item.classList.contains('is-bad'))
    .map((item) => [
      item.querySelector('.eg-chg-where').textContent,
      item.querySelector('.eg-chg-new').title,
    ])
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_changes_drawer_names_each_columns_own_error() -> None:
    """변경 목록의 오류 칸 풍선도 칸마다 글이다 — 고르기 칸 둘(후보 60 · Area)과 글자 수 칸."""
    shell, index = _list_shell()
    draft: eg.DraftState = {
        "cells": {},
        "bad": {
            "p2": {"참조": ("D", "choice"), "Area": ("x", "choice")},
            "+1": {"공정": ("123456789", "len")},
        },
    }
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))

    result = run_node(source, DRAWER_RUNNER, {"shell": shell, "feed": _feed(index, "k1", draft)})

    assert result["bad"] == [
        [
            "DEMO_B · 참조",
            "DEMO_REF_000 · DEMO_REF_001 · DEMO_REF_002 … 60개 가운데 하나를 적습니다",
        ],
        ["DEMO_B · Area", "Main · MI 가운데 하나를 적습니다"],
        ["새 줄 1 · 공정", "8자 이하로 적습니다"],
    ]
