# Purpose: 편집 그리드 출납의 묶어 보내기 쉼 · 곧바로 보내는 길 · 한 번만 다는 리스너를 본다.

"""묶어 보내기 정책 — 쉼은 `edit_grid.SEND_MS` 하나가 정하고 껍데기 `limits.sendMs` 로 JS 에
간다(개발 · 측정 사본은 실행 줄 `CAPA_DEV_BATCH_MS` 로 덮어씀 — `grid_shared.batch_ms`). 초안
없던 표의 첫 op · 붙여넣기 · 줄 지우기 단추 · 되돌리기 · 표 밖 누름 · 창 숨김 · 마운트 정리는
쉼을 기다리지 않는다. Streamlit 은 data 가 바뀔 때마다 default export 를 다시 부르고 앞 호출의
정리 함수는 부르지 않으므로, 다시 불러도 리스너 · 관찰자는 한 벌이고 걸어 둔 묶음은 한 번만
나간다. 등록 JS 두 벌(보통 · 줄 규칙 표) 모두 본다."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from edit_grid_node import FAKE_DOM, mountable, run_node

from capa_simulation.components import edit_grid, grid_shared
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import (
    LIMITS,
    EditGridBase,
    build_base,
    encode_feed,
)

HOST = "demo_grid"
MONTHS = ("202701", "202702", "202703", "202704")
SPEC = eg.GridSpec(
    "RQ_DEMO", "효율", ("공정", "구분"), MONTHS, eg.ValueFormat("percent", 2, max_value=1.0)
)
EDITED: eg.DraftState = {"cells": {"DEMO_B\x1f양산": {"202702": 0.5}}, "bad": {}}


def _frame() -> pd.DataFrame:
    frame = pd.DataFrame({"공정": ["DEMO_A", "DEMO_B", "DEMO_C"], "구분": ["양산", "양산", "ER"]})
    for column, month in enumerate(MONTHS):
        frame[month] = [0.9, 0.8 - column / 100, np.nan if column == 0 else 0.7]
    return frame


def _base() -> tuple[EditGridBase, eg.GridIndex]:
    base = build_base(_frame(), SPEC, None)
    return base, base.index


def _shell(monkeypatch: pytest.MonkeyPatch, send_ms: str | None) -> dict[str, Any]:
    """앱과 같은 길(`shell_data`)로 지은 껍데기 — 실행 줄 덮어쓰기 `send_ms`(None 이면 없음)."""
    monkeypatch.delenv("APP_ENV", raising=False)
    if send_ms is None:
        monkeypatch.delenv(grid_shared.BATCH_OVERRIDE_ENV, raising=False)
    else:
        monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, send_ms)
    base, _ = _base()
    return edit_grid.shell_data(HOST, base, SPEC, base_key="k1", changes_label="적용 전 변경")


def _feed(draft: eg.DraftState | None, undo: int = 0) -> dict[str, Any]:
    _, index = _base()
    step: eg.Step = {"rows": (), "cols": (), "before": (), "after": ()}
    history: eg.HistoryState = {"gen": "g1", "undo": [step] * undo, "redo": []}
    return encode_feed(index, draft, history, host=HOST, base_key="k1", acks={}, toast=None)


# ------------------------------------------------------------------ 파이썬 — 쉼 값과 껍데기


def test_the_quiet_time_comes_from_one_python_constant_unless_the_dev_run_line_overrides_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """쉼은 결정값 `SEND_MS` 이고, 개발 실행 줄 `CAPA_DEV_BATCH_MS` 가 범위 안이면 그 값이다(운영
    `APP_ENV` 는 덮어쓰기를 읽지 않는다 — `grid_shared.batch_ms`)."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv(grid_shared.BATCH_OVERRIDE_ENV, raising=False)
    assert edit_grid.shell_limits()["sendMs"] == edit_grid.SEND_MS
    monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, "800")
    assert edit_grid.shell_limits()["sendMs"] == 800
    for wrong in ("abc", "0.8", "0", "-300", "99999"):
        monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, wrong)
        assert edit_grid.shell_limits()["sendMs"] == edit_grid.SEND_MS, wrong
    assert not hasattr(edit_grid, "SEND_MS_ENV"), "덮어쓰기 이름은 공용 하나다"


def test_the_shell_carries_the_quiet_time_and_stays_the_same_dict_between_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """껍데기는 칸 수 상한에 `sendMs` 를 더 싣고, 같은 표 · 같은 프로세스면 회차마다 같은 dict 다
    (해시 참조). 표 없는 껍데기는 그대로다."""
    shell = _shell(monkeypatch, None)
    assert shell["limits"] == {**LIMITS, "sendMs": edit_grid.SEND_MS}
    assert _shell(monkeypatch, None) == shell
    assert _shell(monkeypatch, "1000")["limits"]["sendMs"] == 1000
    empty = edit_grid.shell_data(HOST, None, None, base_key="", changes_label="적용 전 변경")
    assert "limits" not in empty


def test_the_core_reads_the_quiet_time_from_the_shell_with_a_fallback() -> None:
    core = (edit_grid._ASSETS / "eg_core.js").read_text(encoding="utf-8")
    reader = core[core.index("function egSendMs(") : core.index("function sendNow(")]
    assert "S.limits.sendMs" in reader and "EG_SEND_MS" in reader
    queue = core[core.index("function queueOp(") : core.index("function egPreviewOf(")]
    assert "egTimer(S, 'send', egSendMs(S)" in queue and "EG_SEND_MS" not in queue


# ------------------------------------------------------------------ node — 묶음 정책

RUNNER_HEAD = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const sent = []
const winCount = {}
const winAdd = window.addEventListener.bind(window)
const winRemove = window.removeEventListener.bind(window)
window.addEventListener = (type, fn, options) => {
  winCount[type] = (winCount[type] || 0) + 1
  winAdd(type, fn, options)
}
window.removeEventListener = (type, fn, options) => {
  winCount[type] = (winCount[type] || 0) - 1
  winRemove(type, fn, options)
}
let observers = 0
globalThis.ResizeObserver = class {
  constructor() {
    observers += 1
    this.on = true
  }
  observe() {}
  disconnect() {
    if (this.on) observers -= 1
    this.on = false
  }
}
const docListeners = {}
document.addEventListener = (type, fn) => {
  ;(docListeners[type] = docListeners[type] || []).push(fn)
}
document.removeEventListener = (type, fn) => {
  docListeners[type] = (docListeners[type] || []).filter((f) => f !== fn)
}
const fireDoc = (type) => (docListeners[type] || []).slice().forEach((fn) => fn({ type }))
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
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const seqs = () => (sent.length ? sent[sent.length - 1][1].ops.map((op) => op.seq) : [])
const edit = (value) => {
  key(q('.eg-scroll'), 'Enter')
  q('.eg-ed').value = value
  key(q('.eg-ed'), 'Enter')
}
const sum = (counts) => Object.values(counts).reduce(
  (total, n) => total + (Array.isArray(n) ? n.length : n), 0)
const nodeListeners = (node) => node.children.reduce(
  (total, child) => total + nodeListeners(child), sum(node.listeners))
const tally = (S) => ({
  own: S.listeners.length, doc: sum(docListeners), win: sum(winCount),
  nodes: nodeListeners(host), observers,
})
const R = {}
"""

RUNNER_LONG = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  // 앞서 고친 칸이 있는 표 — 쉼(실행 줄 5초)을 기다린다. 0.5초 뒤에도 안 나갔다(대비 값이 아니다).
  edit('61%')
  await tick(500)
  R.held = { sent: sent.length, box: S.box.ops.length }
  // 표 밖 누름 — 곧바로.
  fire(q('.eg-scroll'), 'focusout', { relatedTarget: null })
  R.outside = { sent: sent.length, seqs: seqs(), name: sent.length ? sent[sent.length - 1][0] : '' }
  // 표 안에서 옮긴 초점은 묶음을 끊지 않는다.
  edit('62%')
  fire(q('.eg-scroll'), 'focusout', { relatedTarget: q('.eg-ed') })
  R.inside = { sent: sent.length }
  // 창 숨김 — 곧바로(보낸 op 도 ack 전이라 함께 실린다).
  fireDoc('visibilitychange')
  R.hidden = { sent: sent.length, seqs: seqs() }
  // 되돌리기 — 곧바로.
  edit('63%')
  key(q('.eg-scroll'), 'z', { ctrlKey: true })
  R.undo = { sent: sent.length, ops: sent[sent.length - 1][1].ops.map((op) => op.op) }
  // 마운트 정리 — 곧바로, 이미 보낸 것만 남았으면 다시 보내지 않는다.
  edit('64%')
  const before = sent.length
  cleanup()
  R.cleanup = { before, sent: sent.length, last: seqs() }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_long_quiet_time_holds_cell_edits_but_leaving_moves_send_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """실행 줄 덮어쓰기(5초)가 `shell_data` → 껍데기 → JS 쉼까지 간다. 쉼 안이라도 표 밖 누름 ·
    창 숨김 · 되돌리기 · 마운트 정리는 기다리지 않는다."""
    shell = _shell(monkeypatch, "5000")
    assert shell["limits"]["sendMs"] == 5000
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_LONG, {"shell": shell, "feed": _feed(EDITED, undo=1)})
    assert result["held"] == {"sent": 0, "box": 1}, "쉼 안의 칸 고침은 나가지 않는다"
    assert result["outside"] == {"sent": 1, "seqs": [1], "name": "outbox"}, "표 밖 누름은 곧바로"
    assert result["inside"] == {"sent": 1}, "표 안에서 옮긴 초점은 묶음을 끊지 않는다"
    assert result["hidden"] == {"sent": 2, "seqs": [1, 2]}, "창이 숨으면 곧바로"
    assert result["undo"] == {"sent": 3, "ops": ["write", "write", "write", "undo"]}
    assert result["cleanup"] == {"before": 3, "sent": 4, "last": [1, 2, 3, 4, 5]}


RUNNER_FIRST = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  // 초안 없던 표의 첫 op — 쉼(5초)을 기다리지 않는다. 둘째부터는 쉼.
  edit('61%')
  R.first = { sent: sent.length, seqs: seqs() }
  edit('62%')
  R.second = { sent: sent.length }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_first_op_on_a_clean_table_goes_out_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    shell = _shell(monkeypatch, "5000")
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_FIRST, {"shell": shell, "feed": _feed(None)})
    assert result["first"] == {"sent": 1, "seqs": [1]}
    assert result["second"] == {"sent": 1}


RUNNER_SHORT = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  const began = Date.now()
  for (const value of ['61%', '62%', '63%']) edit(value)
  R.queued = { sent: sent.length, box: host.__eg.box.ops.length }
  await until(() => sent.length > 0)
  R.waited = Date.now() - began
  await tick(input.sendMs * 3)
  R.quiet = { sent: sent.length, seqs: seqs() }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_burst_goes_out_once_after_the_shell_quiet_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """칸 셋을 잇달아 고치면 쉼(실행 줄 60ms) 뒤 한 번에 세 op 를 싣는다."""
    shell = _shell(monkeypatch, "60")
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(
        source, RUNNER_SHORT, {"shell": shell, "feed": _feed(EDITED, undo=1), "sendMs": 60}
    )
    assert result["queued"] == {"sent": 0, "box": 3}
    assert result["waited"] >= 55, "쉼보다 일찍 나가지 않는다"
    assert result["quiet"] == {"sent": 1, "seqs": [1, 2, 3]}


RUNNER_BIND_ONCE = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  R.before = tally(S)
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  // 쉼에 걸린 op 하나를 둔 채 data 가 바뀐 회차마다 default export 를 다시 부른다(앞 정리 함수는
  // 불리지 않는다). 리스너 · 관찰자는 한 벌 그대로이고 걸린 묶음은 한 번만 나간다.
  edit('61%')
  for (let i = 0; i < 50; i += 1) {
    sendFeed(Object.assign({}, input.feed))
    const palette = Object.assign({}, input.shell.palette, { text: 'ink-' + i })
    mount(Object.assign({}, input.shell, { palette }))
  }
  R.after = tally(S)
  R.held = { sent: sent.length, box: S.box.ops.length }
  await until(() => sent.length > 0)
  await tick(input.sendMs * 3)
  R.flushed = { sent: sent.length, seqs: seqs() }
  // 마운트를 내리면 다 걷힌다.
  const cleanup = mount(input.shell)
  cleanup()
  R.down = tally({ listeners: S.listeners })
  process.stdout.write(JSON.stringify(R))
})()
"""
)


@pytest.mark.parametrize(
    "parts", [edit_grid.JS_PARTS, edit_grid.ROWS_JS_PARTS], ids=["grid", "rows"]
)
def test_mounting_again_binds_listeners_once_and_keeps_one_pending_batch(
    monkeypatch: pytest.MonkeyPatch, parts: tuple[str, ...]
) -> None:
    shell = _shell(monkeypatch, "80")
    source = FAKE_DOM + mountable(edit_grid.registered_js(parts))
    result = run_node(
        source, RUNNER_BIND_ONCE, {"shell": shell, "feed": _feed(EDITED, undo=1), "sendMs": 80}
    )
    before = result["before"]
    assert (
        before["own"] > 0 and before["doc"] > 0 and before["win"] > 0 and before["observers"] == 1
    )
    assert result["after"] == before, "다시 불러도 리스너 · 관찰자는 한 벌"
    assert result["held"] == {"sent": 0, "box": 1}
    assert result["flushed"] == {"sent": 1, "seqs": [1]}, "걸린 묶음은 한 번만 나간다"
    down = result["down"]
    assert down["own"] == 0 and down["doc"] == 0 and down["observers"] == 0
    assert down["win"] == 0, "창 리스너도 정리 함수가 걷는다"


# ------------------------------------------------------------------ node — 붙여넣기 · 단추 op

RUNNER_PASTE = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const scroller = q('.eg-scroll')
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowRight')
  // 앞서 고친 칸이 있는 표(쉼 5초) — 붙여넣기는 곧바로, 칸 고침은 쉼.
  fire(scroller, 'paste', { clipboardData: { getData: () => '12%\t13%\r\n' } })
  const kinds = () => (sent.length ? sent[sent.length - 1][1].ops.map((op) => op.op) : [])
  R.paste = { sent: sent.length, ops: kinds() }
  key(scroller, 'ArrowDown')
  edit('61%')
  R.cell = { sent: sent.length }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_paste_goes_out_at_once_while_cell_edits_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """붙여넣기는 묶음 쉼을 기다리지 않는다(2026-11-20 사용자 결정 — 쉼을 늘려도 붙여넣기 ·
    단추 op 는 곧바로)."""
    shell = _shell(monkeypatch, "5000")
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_PASTE, {"shell": shell, "feed": _feed(EDITED, undo=1)})
    assert result["paste"] == {"sent": 1, "ops": ["write"]}
    assert result["cell"] == {"sent": 1}, "칸 고침은 그대로 쉼을 기다린다"


RUNNER_ROW_BUTTON = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const button = q('.eg-tb-rows')
  // 새 줄 이름 칸 첫 고침(초안 없던 표 — 곧바로), 명단 줄 고침(쉼 5초), 줄 지우기 단추(곧바로).
  setRange(S, { r: 2, c: 2 }, { r: 2, c: 2 })
  edit('데모 나')
  R.first = { sent: sent.length }
  setRange(S, { r: 0, c: 2 }, { r: 0, c: 2 })
  edit('데모 다')
  R.held = { sent: sent.length }
  setRange(S, { r: 0, c: 2 }, { r: 0, c: 2 })
  fire(button, 'click')
  R.button = { sent: sent.length, ops: sent[sent.length - 1][1].ops.map((op) => op.op) }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_row_remove_button_goes_out_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_edit_grid_rows import RULES, SPEC, _frame

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, "5000")
    base = build_base(_frame(), SPEC, None, RULES)
    shell = edit_grid.shell_data(
        "demo_rows", base, SPEC, base_key="k1", changes_label="저장 전 변경"
    )
    history: eg.HistoryState = {"gen": "g1", "undo": [], "redo": []}
    feed = encode_feed(
        base.index, None, history, host="demo_rows", base_key="k1", acks={}, toast=None
    )
    source = FAKE_DOM + mountable(edit_grid.registered_js(edit_grid.ROWS_JS_PARTS))
    result = run_node(source, RUNNER_ROW_BUTTON, {"shell": shell, "feed": feed})
    assert result["first"] == {"sent": 1}
    assert result["held"] == {"sent": 1}
    assert result["button"] == {"sent": 2, "ops": ["write", "write", "remove"]}


# ------------------------------------------------------------------ node — 떠나기 신호(R8)

RUNNER_LEAVE = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  const cleanup = mount(input.shell)
  const S = host.__eg
  const book = editorBook(window)
  const busy = () => editorsBusy(book)
  key(q('.eg-scroll'), 'ArrowRight')
  key(q('.eg-scroll'), 'ArrowRight')
  R.mounted = { editors: book.entries.size, busy: busy() }
  // 앞서 고친 칸이 있는 표 — 쉼(5초)에 걸린다. 명부는 busy(보내지 않은 op).
  edit('61%')
  R.held = { sent: sent.length, busy: busy() }
  // 화면을 떠나는 누름이 쏜 신호 — 곧바로 보내고 ack 전까지 busy 다.
  window.dispatchEvent(new CustomEvent('capa-leaving'))
  R.left = { sent: sent.length, seqs: seqs(), busy: busy(), leaving: S.leave.leaving }
  // 신호 뒤 편집은 묶지 않는다.
  edit('62%')
  R.after = { sent: sent.length, seqs: seqs(), busy: busy() }
  // ack 로 보낼 목록이 비면 busy 가 걷히고 다시 묶는다.
  sendFeed(Object.assign({}, input.feed, { acks: { [S.mount]: 2 } }))
  R.acked = { box: S.box.ops.length, busy: busy(), leaving: S.leave.leaving }
  edit('63%')
  R.again = { sent: sent.length, busy: busy() }
  // 마운트를 내리면 명부에서 빠진다(남은 op 는 보내고).
  cleanup()
  R.down = { sent: sent.length, editors: book.entries.size, busy: busy(), leave: S.leave }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_leaving_signal_sends_at_once_and_holds_busy_until_the_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """떠나기 신호(`capa-leaving`)를 받으면 묶음 쉼(5초) 안의 op 를 곧바로 보내고, ack 가 올 때까지
    편집기 명부(`window.__capaEditors`)에 busy 다. 신호 뒤 편집은 묶지 않고, ack 로 보낼 목록이
    비면 다시 묶는다. 마운트를 내리면 명부에서 빠진다."""
    shell = _shell(monkeypatch, "5000")
    source = FAKE_DOM + mountable(edit_grid.registered_js())
    result = run_node(source, RUNNER_LEAVE, {"shell": shell, "feed": _feed(EDITED, undo=1)})
    assert result["mounted"] == {"editors": 1, "busy": False}
    assert result["held"] == {"sent": 0, "busy": True}
    assert result["left"] == {"sent": 1, "seqs": [1], "busy": True, "leaving": True}
    assert result["after"] == {"sent": 2, "seqs": [1, 2], "busy": True}
    assert result["acked"] == {"box": 0, "busy": False, "leaving": False}
    assert result["again"] == {"sent": 2, "busy": True}, "ack 뒤 편집은 다시 쉼을 탄다"
    assert result["down"] == {"sent": 3, "editors": 0, "busy": False, "leave": None}


RUNNER_LEAVE_BIND_ONCE = (
    RUNNER_HEAD
    + r"""
;(async () => {
  sendFeed(input.feed)
  mount(input.shell)
  const S = host.__eg
  const book = editorBook(window)
  R.before = { leaving: winCount['capa-leaving'] || 0, editors: book.entries.size }
  for (let i = 0; i < 50; i += 1) {
    sendFeed(Object.assign({}, input.feed))
    const palette = Object.assign({}, input.shell.palette, { text: 'ink-' + i })
    mount(Object.assign({}, input.shell, { palette }))
  }
  R.after = { leaving: winCount['capa-leaving'] || 0, editors: book.entries.size }
  const cleanup = mount(input.shell)
  cleanup()
  R.down = { leaving: winCount['capa-leaving'] || 0, editors: book.entries.size }
  // 내린 뒤 다시 마운트하면 다시 한 번 오른다.
  mount(input.shell)
  R.again = { leaving: winCount['capa-leaving'] || 0, editors: book.entries.size }
  process.stdout.write(JSON.stringify(R))
})()
"""
)


@pytest.mark.parametrize(
    "parts", [edit_grid.JS_PARTS, edit_grid.ROWS_JS_PARTS], ids=["grid", "rows"]
)
def test_mounting_again_joins_the_editor_book_once(
    monkeypatch: pytest.MonkeyPatch, parts: tuple[str, ...]
) -> None:
    """data 가 바뀔 때마다 default export 를 다시 불러도 떠나기 신호 처리기와 명부 칸은 하나다(앞
    호출의 정리 함수는 불리지 않는다). 정리 함수가 둘 다 걷고, 다시 마운트하면 다시 하나다."""
    shell = _shell(monkeypatch, "80")
    source = FAKE_DOM + mountable(edit_grid.registered_js(parts))
    result = run_node(source, RUNNER_LEAVE_BIND_ONCE, {"shell": shell, "feed": _feed(EDITED)})
    assert result["before"] == {"leaving": 1, "editors": 1}
    assert result["after"] == {"leaving": 1, "editors": 1}
    assert result["down"] == {"leaving": 0, "editors": 0}
    assert result["again"] == {"leaving": 1, "editors": 1}


def test_the_core_joins_the_leaving_book_in_bind_and_drops_it_in_cleanup() -> None:
    """글 약속 — 신호 받기는 처리기를 한 번 다는 `egBind` 안이고, 정리 함수가 걷는다. busy 는 보낼
    목록이 남았는가이고, ack 를 받은 뒤 걷힘을 알린다. 떠나기 뒤 op 는 묶음 타이머를 타지 않는다."""
    core = (edit_grid._ASSETS / "eg_core.js").read_text(encoding="utf-8")
    bind = core[core.index("function egBind(") : core.index("function egInside(")]
    assert (
        "S.leave = joinLeaving(window, { busy: () => egBusy(S), flush: () => sendNow(S) }, S.host)"
        in bind
    )
    assert "return S.box.ops.length > 0" in core[core.index("function egBusy(") :]
    acks = core[core.index("function egTakeAcks(") : core.index("function egApplyFeed(")]
    assert acks.index("boxAck(S.box, acked)") < acks.index("settleLeaving(S.leave, egBusy(S))")
    queue = core[core.index("function queueOp(") : core.index("function egPreviewOf(")]
    assert "leavingNow(S.leave)) sendNow(S)" in queue
    cleanup = core[core.index("return () => {") :]
    assert "if (S.leave) S.leave.drop()" in cleanup
