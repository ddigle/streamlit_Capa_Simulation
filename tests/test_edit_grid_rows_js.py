# Purpose: 범용 편집 그리드 줄 갈래 JS(글 · 고르기 칸 · 줄 잠금 · 줄 지우기)를 node 로 본다.

"""줄 규칙 표의 등록(`components/edit_grid.ROWS_JS_PARTS` — `eg_rows.js` 를 더 실음)을 브라우저 없이
본다. 글 · 고르기 칸 다듬기는 Python 과 같은 사례 표의 쌍둥이 시험이고, 줄 잠금 · 줄 지우기 단추 ·
지운 줄 표지 · 고르기 목록 · 변경 목록 되살리기는 등록 JS 전체를 가짜 DOM(`tests/edit_grid_node.
FAKE_DOM`)에 마운트해 본다. 껍데기 · feed 는 Python 이 지은 그대로 넘긴다. 값은 모두 합성이다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
  // 고르기 칸 — 편집을 열면 칸 아래 항목 목록, ↓ 가 다음 항목, Enter 가 그 글로 확정.
  setRange(S, { r: 0, c: 3 }, { r: 0, c: 3 })
  key(scroller, 'Enter')
  const list = q('.eg-choices')
  R.choiceOpen = [list.hidden, list.children.map((n) => n.textContent), q('.eg-ed').value]
  key(q('.eg-ed'), 'ArrowDown')
  R.choiceDown = [q('.eg-ed').value, list.children.map((n) => n.classList.contains('is-on'))]
  key(q('.eg-ed'), 'Enter')
  R.choiceCommit = { op: lastOps()[0], hidden: list.hidden, text: cell(0, 3).textContent }
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
    assert result["choiceOpen"] == [False, ["열람", "실무자", "관리자", "개발자"], "열람"]
    assert result["choiceDown"] == ["실무자", [False, True, False, False]]
    commit = result["choiceCommit"]
    assert commit["op"]["op"] == "write" and commit["op"]["values"] == [["실무자"]]
    assert commit["op"]["rows"] == ["demo.a"] and commit["op"]["cols"] == ["등급"]
    assert commit["hidden"] is True and commit["text"] == "실무자"
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
