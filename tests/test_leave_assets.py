# Purpose: 떠나기 신호 조각(leave.js)의 편집기 명부 · 신호 · 묶음 정책을 node 로, 공용 조각 잇기를
# 글자로 검사한다.

"""떠나기 신호(AGENTS 9장 「구역 회차 규칙」 R8)의 브라우저 몫.

AppTest 는 컴포넌트 JS 를 돌리지 못한다. `grid_shared_assets/leave.js` 의 구획
(`// <capa-leave…>`)과 표 공용 출납(`outbox.js` 의 `<grid-outbox>`)을 떼어 node(없으면 bun)로
돌린다 — 없으면 건너뛰고 CI 에서는 실패한다. 편집기가 이 조각을 쓰는 꼴(묶음 타이머 · 신호에 곧바로
보냄 · ack 까지 busy)은 설비 마스터 · 시나리오 목록 · 범용 편집 그리드가 같은 몇 줄로 잇는다 —
여기서는 그 몇 줄을 대역 편집기로 돌린다.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from js_runner import run_js_json

from capa_simulation.components import grid_shared, page_tabs

LEAVE_JS = grid_shared.leave_js()
OUTBOX_JS = (grid_shared.SHARED_ASSETS / "outbox.js").read_text(encoding="utf-8")


def _section(source: str, name: str) -> str:
    match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", source, re.S)
    assert match, f"// <{name}> 구획이 없습니다"
    return match.group("body")


def _node(runner: str) -> Any:
    prelude = "\n".join(
        [
            _section(LEAVE_JS, "capa-leave"),
            _section(LEAVE_JS, "capa-leave-window"),
            _section(OUTBOX_JS, "grid-outbox"),
        ]
    )
    return run_js_json(prelude + "\n" + runner, what="떠나기 신호 JS 구획 시험")


def test_the_leave_piece_rides_every_shared_grid_and_the_tab_strip() -> None:
    """떠나기 조각은 표 공용 조각(`SHARED_JS`)에 들어 설비 마스터 · 시나리오 목록 등록에 실리고,
    탭 줄 등록 글은 그 조각 뒤에 탭 줄 파일을 잇는다. 상태는 창 칸에만 둔다(모듈마다 따로 돈다)."""
    assert grid_shared.LEAVE_JS in grid_shared.SHARED_JS
    assert page_tabs.registered_js().startswith(LEAVE_JS)
    assert "const LEAVING_EVENT = 'capa-leaving'" in LEAVE_JS
    assert "const EDITORS_SLOT = '__capaEditors'" in LEAVE_JS
    assert re.search(r"^let ", LEAVE_JS, re.M) is None, "모듈 전역 상태를 두지 않는다"


_BOOK_RUNNER = """
const out = {}
const host = {}
const book = editorBook(host)
out.same = editorBook(host) === book
host.__capaEditors = { entries: 'broken' }
out.rebuilt = editorBook(host).entries instanceof Map
const fresh = editorBook(host)
let pending = false
const a = enrollEditor(fresh, () => pending)
const b = enrollEditor(fresh, () => { throw new Error('gone') })
out.idle = editorsBusy(fresh)
pending = true
out.busy = editorsBusy(fresh)
dropEditor(fresh, a)
out.dropped = [editorsBusy(fresh), fresh.entries.size, b > a]
const handle = { leaving: true }
settleLeaving(handle, true)
out.stillLeaving = leavingNow(handle)
settleLeaving(handle, false)
out.settled = leavingNow(handle)
out.noHandle = [leavingNow(null), leavingNow(undefined)]
process.stdout.write(JSON.stringify(out))
"""


def test_the_editor_book_lives_on_the_window_and_a_failing_judge_is_not_busy() -> None:
    """명부는 창 칸 하나다 — 다시 불러도 같은 칸, 꼴이 깨졌으면 새로 세운다. busy 판정이 던지는
    편집기(내린 편집기의 낡은 함수)는 붙들기를 묶지 않는다. 떠나기 손잡이는 보낼 것이 다 걷히면 다시
    묶는다."""
    out = _node(_BOOK_RUNNER)

    assert out["same"] is True and out["rebuilt"] is True
    assert out["idle"] is False and out["busy"] is True
    assert out["dropped"] == [False, 1, True]
    assert out["stillLeaving"] is True and out["settled"] is False
    assert out["noHandle"] == [False, False]


# 대역 편집기 — 설비 마스터 표(`grid.js`)의 출납 몇 줄과 같은 꼴: 칸 고침은 묶음
# 타이머(`SEND_MS`) 뒤 `send`, 떠나기 신호 뒤로는 곧바로, 받은 data 의 ack 로 op 를 걷고 다
# 걷히면 다시 묶는다. `root` 를 주면 부품 뿌리를 셋째 인자로 넘긴다. 대본은 이 대역 뒤에
# 잇는다(`_editor_node`).
_EDITOR_HARNESS = """
  let now = 0
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
  // 창 대역 — 사건 처리기 수를 센다(다시 불러도 늘지 않는가).
  const win = new EventTarget()
  win.CustomEvent = globalThis.CustomEvent || class extends Event {}
  let listeners = 0
  const add = win.addEventListener.bind(win)
  const remove = win.removeEventListener.bind(win)
  win.addEventListener = (type, fn) => { listeners += 1; add(type, fn) }
  win.removeEventListener = (type, fn) => { listeners -= 1; remove(type, fn) }
  const SEND_MS = 800
  const mount = (name, sent, root) => {
    const S = { box: createBox(), sentSeq: 0, timer: 0 }
    S.box.base = 'b1'
    const send = () => {
      clearTimeout(S.timer)
      S.timer = 0
      const last = S.box.ops[S.box.ops.length - 1]
      if (!last || last.seq <= S.sentSeq) return
      S.sentSeq = last.seq
      sent.push(name + ':' + last.seq + '@' + now)
    }
    const hooks = { busy: () => boxBusy(S.box), flush: send }
    S.leave = root === undefined ? joinLeaving(win, hooks) : joinLeaving(win, hooks, root)
    S.edit = (id) => {
      queueOp(S.box, { op: 'cell', id }, 100, now)
      if (leavingNow(S.leave)) return send()
      clearTimeout(S.timer)
      S.timer = setTimeout(send, SEND_MS)
    }
    S.receive = (seq) => {
      ackBox(S.box, seq)
      settleLeaving(S.leave, boxBusy(S.box))
    }
    return S
  }
  const book = () => editorBook(win)
"""


def _editor_node(script: str) -> Any:
    return _node("(() => {\n" + _EDITOR_HARNESS + script + "\n})()")


_EDITOR_RUNNER = """
  const out = {}
  const sent = []
  const grid = mount('grid', sent)
  const list = mount('list', sent)
  // 칸 둘을 0.3초 간격으로 고친다 — 묶음 타이머 안이라 아직 보내지 않았고 명부는 busy 다.
  grid.edit('U1'); now = 300; grid.edit('U2'); now = 400
  out.batched = [sent.slice(), editorsBusy(book())]
  // 떠나는 누름 — 신호에 곧바로 보낸다(타이머를 기다리지 않는다). ack 가 올 때까지 busy.
  announceLeaving(win)
  out.flushed = [sent.slice(), editorsBusy(book())]
  // 타이머는 걷혔다 — 묶음 쉼이 지나도 다시 보내지 않는다.
  advance(2000)
  out.noTimer = sent.slice()
  // 떠나기 뒤 편집은 곧바로 보낸다. ack 가 다 오면 busy 가 걷히고 다시 묶는다.
  grid.edit('U3')
  out.afterLeave = sent.slice()
  grid.receive(3)
  out.cleared = [editorsBusy(book()), leavingNow(grid.leave)]
  grid.edit('U4')
  out.rebatched = sent.slice()
  advance(now + SEND_MS)
  out.sentLater = sent.slice()
  grid.receive(4)
  // 보낼 것이 없는 편집기는 신호에 아무것도 보내지 않는다.
  const before = sent.length
  announceLeaving(win)
  out.idleSignal = [sent.length - before, editorsBusy(book())]
  // 다시 그려도(마운트 · 정리 50번) 처리기와 명부가 늘지 않는다.
  for (let i = 0; i < 50; i += 1) {
    const again = mount('again', [])
    again.leave.drop()
  }
  out.listeners = [listeners, book().entries.size]
  grid.leave.drop()
  list.leave.drop()
  out.dropped = [listeners, book().entries.size]
  process.stdout.write(JSON.stringify(out))
"""


def test_an_editor_flushes_its_batch_on_the_leaving_signal_and_stays_busy_until_acked() -> None:
    """편집기는 칸 고침을 묶음 타이머로 모으다가 떠나기 신호에 곧바로 보내고 ack 가 올 때까지 명부에
    busy 다. 신호 뒤 편집은 묶지 않고 보내며, 다 걷히면 다시 묶는다. 보낼 것이 없는 편집기는 신호에
    보내지 않는다. 마운트 · 정리를 거듭해도 처리기 · 명부가 늘지 않는다."""
    out = _editor_node(_EDITOR_RUNNER)

    assert out["batched"] == [[], True]
    assert out["flushed"] == [["grid:2@400"], True]
    assert out["noTimer"] == ["grid:2@400"]
    assert out["afterLeave"] == ["grid:2@400", "grid:3@2000"]
    assert out["cleared"] == [False, False]
    assert out["rebatched"] == ["grid:2@400", "grid:3@2000"]
    assert out["sentLater"] == ["grid:2@400", "grid:3@2000", "grid:4@2800"]
    assert out["idleSignal"] == [0, False]
    assert out["listeners"] == [2, 2]
    assert out["dropped"] == [0, 0]


_IDLE_SIGNAL_RUNNER = """
  const out = {}
  const sent = []
  const grid = mount('grid', sent)
  const list = mount('list', sent)
  // 쉬는 편집기(보낼 것도 ack 기다림도 없음)가 신호를 받는다 — 지금 화면 링크 · 떠나기 확인
  // 취소 · 상한에 막힌 링크처럼 화면에 머무는 누름도 신호를 쏜다.
  announceLeaving(win)
  out.idle = [sent.slice(), editorsBusy(book()), leavingNow(grid.leave), leavingNow(list.leave)]
  // 머문 뒤 다음 고침은 다시 묶음 타이머를 탄다.
  now = 100
  grid.edit('U1')
  out.batched = sent.slice()
  advance(now + SEND_MS)
  out.sentLater = sent.slice()
  // 묶음이 남은 채 받은 신호 — 곧바로 보내고 ack 를 기다리는 동안 걷히지 않는다.
  grid.receive(1)
  grid.edit('U2')
  announceLeaving(win)
  out.flushed = [sent.slice(), leavingNow(grid.leave), leavingNow(list.leave)]
  // 이미 보내고 ack 만 기다리는 중에 받은 신호도 걷히지 않는다 — 다음 고침은 곧바로 보낸다.
  announceLeaving(win)
  out.waiting = leavingNow(grid.leave)
  grid.edit('U3')
  out.afterLeave = sent.slice()
  // ack 뒤 스스로 걷는 편집기(`settleLeaving`)와 겹쳐도 그대로다 — 다 걷히면 다시 묶는다.
  grid.receive(3)
  out.settled = [leavingNow(grid.leave), editorsBusy(book())]
  announceLeaving(win)
  out.idleAgain = leavingNow(grid.leave)
  grid.leave.drop()
  list.leave.drop()
  process.stdout.write(JSON.stringify(out))
"""


def test_an_idle_editor_settles_at_the_leaving_signal_and_keeps_batching_after_staying() -> None:
    """보낼 것도 ack 기다림도 없는 편집기는 신호를 받은 자리에서 곧바로 걷는다 — 화면에 머문
    누름(지금 화면 링크 · 확인 취소 · 상한 거름) 뒤에도 다음 고침은 묶음 타이머를 탄다. 묶음을
    보낸 편집기 · ack 를 기다리는 편집기가 받은 신호는 걷지 않고(다음 고침은 곧바로), ack 가 다
    오면 걷는다."""
    out = _editor_node(_IDLE_SIGNAL_RUNNER)

    assert out["idle"] == [[], False, False, False]
    assert out["batched"] == []
    assert out["sentLater"] == ["grid:1@900"]
    assert out["flushed"] == [["grid:1@900", "grid:2@900"], True, False]
    assert out["waiting"] is True
    assert out["afterLeave"] == ["grid:1@900", "grid:2@900", "grid:3@900"]
    assert out["settled"] == [False, False]
    assert out["idleAgain"] is False


_DETACHED_RUNNER = """
  const out = {}
  const sent = []
  const host = { isConnected: true }
  const grid = mount('grid', sent, host)
  grid.edit('U1')
  out.attached = editorsBusy(book())
  // 내렸는데 정리 함수에서 `drop()` 을 빠뜨렸다 — 뿌리가 문서에서 떨어진 편집기는 busy 가 아니다.
  host.isConnected = false
  out.detached = editorsBusy(book())
  // 뿌리를 넘기지 않는 꼴 · 연결 여부를 모르는 뿌리는 판정 그대로다.
  const plain = mount('plain', sent)
  plain.edit('V1')
  out.plain = editorsBusy(book())
  plain.leave.drop()
  const unknown = mount('unknown', sent, {})
  unknown.edit('W1')
  out.unknown = editorsBusy(book())
  unknown.leave.drop()
  grid.leave.drop()
  process.stdout.write(JSON.stringify(out))
"""


def test_a_detached_editor_root_is_not_busy() -> None:
    """편집기가 부품 뿌리(편집기 상태를 단 요소)를 셋째 인자로 넘기면, 그 뿌리가 문서에서 떨어진
    뒤의 낡은 판정은 busy 가 아니다 — 정리 함수에서 `drop()` 을 빠뜨린 편집기가 떠나는 누름마다
    붙들기를 `BUSY_MS` 묶지 않는다. 뿌리를 넘기지 않거나 연결 여부를 모르면 판정 그대로다."""
    out = _editor_node(_DETACHED_RUNNER)

    assert out["attached"] is True
    assert out["detached"] is False
    assert out["plain"] is True
    assert out["unknown"] is True


# 떠나기 명부에 오르는 편집기 → (부품 JS — 부품 폴더 기준, 셋째 인자로 넘기는 부품 뿌리 — 편집기
# 상태를 단 요소). `joinLeaving(` 을 부르는 부품 JS 는 모두 여기에 한 줄이 있어야 한다(아래 그물).
_ENROLLING_EDITORS = {
    "범용 편집 그리드": ("edit_grid_assets/eg_core.js", "S.host"),
    "시나리오 목록 표": ("scenario_list_grid_assets/list.js", "host"),
    "Space 「호기 정보」 창": ("space_layout_editor_assets/editor.js", "host"),
}
_COMPONENTS = grid_shared.SHARED_ASSETS.parent
# 명부에 오르는 부름 — 정의(`function joinLeaving(`) · 설명 글(`` `joinLeaving` ``)은 아니다.
_JOIN_CALL = r"(?<!function )\bjoinLeaving\("


def _join_callers() -> dict[str, int]:
    """부품 폴더의 JS 가운데 `joinLeaving(` 을 부르는 파일 → 부른 수(정의 `function joinLeaving(` 은
    빼고)."""
    found: dict[str, int] = {}
    for path in sorted(_COMPONENTS.rglob("*.js")):
        calls = len(re.findall(_JOIN_CALL, path.read_text(encoding="utf-8")))
        if calls:
            found[path.relative_to(_COMPONENTS).as_posix()] = calls
    return found


def test_every_join_leaving_caller_is_in_the_enrolling_table() -> None:
    """`joinLeaving(` 을 부르는 부품 JS 는 모두 `_ENROLLING_EDITORS` 에 있고 파일마다 한 곳에서
    부른다 — 새 편집기가 명부에 오르면 표에 한 줄을 더해 아래 시험이 부품 뿌리를 넘기는지 본다."""
    sample = (
        "function joinLeaving(win, hooks) {}\nS.leave = joinLeaving(window, {})\n// `joinLeaving`"
    )
    assert len(re.findall(_JOIN_CALL, sample)) == 1, "그물 대조"
    callers = _join_callers()
    assert set(callers) == {path for path, _ in _ENROLLING_EDITORS.values()}, callers
    assert all(count == 1 for count in callers.values()), callers


def _call_arguments(source: str, name: str) -> str:
    """`name(` 으로 여는 호출 하나의 괄호 안 글(중첩 괄호 · 중괄호를 센다)."""
    start = source.index(f"{name}(") + len(name)
    depth = 0
    for index in range(start, len(source)):
        depth += {"(": 1, "{": 1, ")": -1, "}": -1}.get(source[index], 0)
        if depth == 0:
            return source[start + 1 : index]
    raise AssertionError(f"{name} 호출이 닫히지 않는다")


@pytest.mark.parametrize("editor", sorted(_ENROLLING_EDITORS))
def test_every_enrolling_editor_passes_its_root(editor: str) -> None:
    """명부에 오르는 편집기는 모두 셋째 인자로 부품 뿌리(편집기 상태를 단 요소)를 넘긴다 — 위
    시험의 보호(문서에서 떨어진 편집기의 낡은 판정은 busy 가 아니다)가 실제 편집기에 닿는다."""
    path, root = _ENROLLING_EDITORS[editor]
    source = (_COMPONENTS / path).read_text(encoding="utf-8")
    arguments = _call_arguments(source, "joinLeaving")
    assert arguments.startswith("window, {"), arguments
    assert arguments.endswith(f"}}, {root}"), arguments


_SCOPE_RUN_RUNNER = """
(() => {
  let now = 0
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
  // DOM 대역 — Streamlit 뿌리(회차 표지), 화면 탭 줄(구역 밖 기준 요소), 구역 칸 안 낡음 요소.
  const makeRoot = () => ({ state: 'notRunning', getAttribute(name) { return this.state } })
  let root = makeRoot()
  let tabs = { stale: 'false', getAttribute() { return this.stale } }
  let insideStale = false
  const marks = new Set()
  const doc = {
    documentElement: {
      setAttribute: (name) => marks.add(name),
      removeAttribute: (name) => marks.delete(name),
      hasAttribute: (name) => marks.has(name),
    },
    querySelector: (selector) => {
      if (selector === '[data-testid="stApp"]') return root
      if (selector === SCOPE_OUTSIDE) return tabs
      if (selector === SCOPE_STALE) return insideStale ? {} : null
      return null
    },
  }
  let observers = 0
  let disconnects = 0
  let notify = () => {}
  class FakeObserver {
    constructor(fn) { this.fn = fn }
    observe(target, options) {
      observers += 1
      notify = this.fn
      this.options = options
    }
    disconnect() { disconnects += 1 }
  }
  const win = { MutationObserver: FakeObserver, setTimeout, clearTimeout }
  const flip = (state) => { root.state = state; notify() }
  const marked = () => marks.has(SCOPE_RUN_ATTRIBUTE)
  const out = {}
  out.verdicts = [
    scopeRunVerdict(true, false, true),
    scopeRunVerdict(true, true, true),
    scopeRunVerdict(true, false, false),
    scopeRunVerdict(true, null, true),
    scopeRunVerdict(false, false, true),
  ]
  watchScopeRuns(win, doc)
  watchScopeRuns(win, doc)
  out.once = observers
  // 편집기 구역 회차 — 탭 줄은 낡음이 아니고 구역 칸 안만 낡음이다. 끝나면 실행 표시 전이 뒤
  // 걷는다.
  insideStale = true
  flip('running')
  out.scope = marked()
  flip('notRunning')
  out.lingers = marked()
  advance(now + SCOPE_RUN_LINGER_MS)
  out.cleared = marked()
  // 앱 전체 회차 — 그 순간 탭 줄도 낡음이다.
  tabs.stale = 'true'
  flip('running')
  out.app = marked()
  flip('notRunning')
  // 다른 프래그먼트(사이드바 조건 칸 등) — 구역 칸 안에 낡음이 없다.
  tabs.stale = 'false'
  insideStale = false
  flip('running')
  out.otherFragment = marked()
  flip('notRunning')
  // 구역 회차가 본문 뒤에서 앱 전체로 올라감 — 걷기 전에 선 앱 전체 회차는 곧바로 걷는다.
  insideStale = true
  flip('running')
  flip('notRunning')
  advance(now + 80)
  tabs.stale = 'true'
  flip('running')
  out.escalated = marked()
  advance(now + 1000)
  out.escalatedLater = marked()
  flip('notRunning')
  // 탭 줄이 서지 않은 화면은 판정하지 않는다.
  tabs = null
  flip('running')
  out.noTabs = marked()
  flip('notRunning')
  // Streamlit 뿌리가 바뀌면 다시 건다.
  root = makeRoot()
  watchScopeRuns(win, doc)
  out.rebound = [observers, disconnects]
  process.stdout.write(JSON.stringify(out))
})()
"""


def test_a_scope_only_run_marks_the_document_and_an_app_run_does_not() -> None:
    """편집기 구역만 도는 회차 동안 문서 뿌리에 표지를 단다 — 회차 표지가 「돈다」 로 바뀐 순간 구역
    밖 기준 요소(화면 탭 줄)가 낡음이 아니고 구역 칸 안에 낡음 요소가 있을 때다. 앱 전체 회차(탭
    줄도 낡음) · 다른 프래그먼트 회차 · 탭 줄이 없는 화면은 달지 않는다. 회차가 끝나면 실행 표시가
    사라지는 전이 뒤 걷고, 그 사이 선 앱 전체 회차는 곧바로 걷는다. 지킴이는 문서에 하나다."""
    prelude = "\n".join(
        [_section(LEAVE_JS, "capa-scope-run"), _section(LEAVE_JS, "capa-scope-run-window")]
    )
    out = run_js_json(prelude + "\n" + _SCOPE_RUN_RUNNER, what="구역 회차 표지 JS 시험")

    assert out["verdicts"] == [True, False, False, False, False]
    assert out["once"] == 1
    assert [out["scope"], out["lingers"], out["cleared"]] == [True, True, False]
    assert out["app"] is False and out["otherFragment"] is False
    assert out["escalated"] is False and out["escalatedLater"] is False
    assert out["noTabs"] is False
    assert out["rebound"] == [2, 1]


def test_the_scope_run_marks_share_the_python_names_and_the_tab_strip_installs_the_watch() -> None:
    """구역 칸 접두 · 문서 표지 · 구역 밖 기준 요소는 파이썬(`fragment_scope` · `app_header`)과 같은
    글이고, 화면 탭 줄이 그릴 때마다 지킴이를 부른다(문서에 하나). 머리 띠 스타일이 구역 회차 규칙을
    진행 막대 자리 규칙 앞에 싣는다."""
    from capa_simulation.components import app_header, fragment_scope

    assert f"const SCOPE_BOX_PREFIX = '{fragment_scope.SCOPE_BOX_PREFIX}'" in LEAVE_JS
    assert f"const SCOPE_RUN_ATTRIBUTE = '{fragment_scope.SCOPE_RUN_ATTRIBUTE}'" in LEAVE_JS
    assert f"const SCOPE_OUTSIDE = '{app_header.PAGE_TABS_SELECTOR}'" in LEAVE_JS
    tabs_js = (page_tabs._ASSETS / "page_tabs.js").read_text(encoding="utf-8")
    assert "watchScopeRuns(window, document)" in tabs_js
    header = app_header._header_css()
    assert fragment_scope.SCOPE_RUN_STYLE in header
    assert header.index(fragment_scope.SCOPE_RUN_STYLE) < header.index(
        app_header._status_slot_css()
    )


def test_the_batch_length_override_is_for_development_runs_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """묶음 길이 덮어쓰기(`CAPA_DEV_BATCH_MS`)는 개발 · 측정 사본의 실행 줄 전용이다 — 운영
    `APP_ENV` · 숫자가 아님 · 범위 밖이면 결정값 그대로다."""
    monkeypatch.delenv(grid_shared.BATCH_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert grid_shared.batch_ms(800) == 800
    monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, "1500")
    assert grid_shared.batch_ms(800) == 1500
    for raw in ("abc", "10", "60000"):
        monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, raw)
        assert grid_shared.batch_ms(800) == 800
    monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, "1500")
    monkeypatch.setenv("APP_ENV", "prod")
    assert grid_shared.batch_ms(800) == 800
