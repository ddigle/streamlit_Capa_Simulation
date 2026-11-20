# Purpose: Space 「호기 정보」 창 칸 확인의 묶어 보내기 · 다시 보냄 · 떠나기 신호 · 한 번만
# 달기와 창 칸 초점 · 「적용」 잇기를 node(가짜 DOM 포함)로 검사한다.

"""Space 배치 편집 「호기 정보」 창 칸 확인 보내기(2026-11-20 사용자 결정 Q3 — 설계 규칙집 7-1:
잇달아 고친 칸은 잠깐 모아 묻고, 칸 떠남 · 「적용」 직전 · 떠나기 신호 때는 곧바로).

AppTest 는 편집기 JS 를 돌리지 못한다. `editor.js` 의 순수 구획 `// <sheet-send>`(묶음 타이머 ·
판정 기다림 · 한 번 다시 보냄)와 떠나기 신호 조각(`leave.js` 의 `<capa-leave>` ·
`<capa-leave-window>`)을 떼어 가짜 시계로 node(없으면 bun)에서 돌린다. 편집기 몸은 느슨한 DOM
대역(`tests/test_ccv2_hygiene.py` 의 `BIND_ONCE`)으로 돌지 않아, 잇는 몇 줄(`<sheet-send-bind>` ·
`<sheet-send-unbind>`)을 떼어 50번 불러 처리기가 한 벌인지 여기서 본다(AGENTS 9장 「구역 회차
규칙」 R7). 창 칸 열기 · 닫기 · 확정 · 칸 떠남과 「적용」 처리기 · 판정 받기는 편집기 몸의 그
함수들을 떼어 초점을 쥔 가짜 DOM 에서 돌린다 — 표 다시 그리기 · 칠하기는 대역이라 실제 줄 다시
그리기 사이의 초점과 브라우저의 사건 차례는 실제 브라우저 몫이다. 서버 쪽 seq 거름은
`tests/test_space_layout_editor_page.py` 가 본다.
"""

from __future__ import annotations

import re
from typing import Any

from js_runner import check_js_module, run_js_json

from capa_simulation.components import grid_shared, space_layout_editor
from capa_simulation.components.date_panel import DATE_PANEL_MOUNT_JS

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
LEAVE_JS = grid_shared.leave_js()
MODULE = (ASSETS.parent / "space_layout_editor.py").read_text(encoding="utf-8")


def _section(source: str, name: str) -> str:
    match = re.search(
        rf"^[ \t]*// <{name}>\n(?P<body>.*?)\n[ \t]*// </{name}>", source, re.S | re.M
    )
    assert match, f"// <{name}> 구획이 없습니다"
    return match.group("body")


_CLOCK = """
const clock = { now: 0, next: 1, timers: new Map() }
const fakeSetTimeout = (fn, ms) => {
  const id = clock.next++
  clock.timers.set(id, { at: clock.now + ms, fn })
  return id
}
const fakeClearTimeout = (id) => {
  clock.timers.delete(id)
}
function advance(ms) {
  const end = clock.now + ms
  for (;;) {
    let first = null
    for (const [id, timer] of clock.timers) {
      if (timer.at <= end && (first === null || timer.at < first[1].at)) first = [id, timer]
    }
    if (first === null) break
    clock.timers.delete(first[0])
    clock.now = first[1].at
    first[1].fn()
  }
  clock.now = end
}
// 시나리오마다 시계를 0 에서 다시 센다.
function resetClock() {
  clock.now = 0
  clock.timers.clear()
}
"""

_ENV = """
function makeEnv(over) {
  const env = {
    sendMs: 500, retryMs: 1500, pollMs: 250, quietMs: 600,
    setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout,
    seqNow: 0, cells: 0, run: createSheetRun(false, -100000), sent: [], settles: 0,
    current: () => env,
    seq: () => env.seqNow,
    body: () => (env.cells ? { seq: env.seqNow, cells: env.cells } : null),
    send: (body) => env.sent.push([clock.now, body.seq, body.cells]),
    quiet: () => sheetRunQuiet(env.run, clock.now),
    settled: () => { env.settles += 1 },
  }
  return Object.assign(env, over || {})
}
// 회차 표지가 바뀌었다(편집기는 뿌리 감시가 적는다) — 지금 시각으로 적는다.
function setRun(env, running) {
  markSheetRun(env.run, running, clock.now)
}
// 칸 하나를 확정한 것 — seq 를 올리고 고친 칸을 하나 늘려 싣는다(편집기 `sheetEditSend`).
function edit(box, env, now) {
  env.seqNow += 1
  env.cells += 1
  sheetSendQueue(box, env, now)
}
"""


def _node(runner: str, *, leave: bool = False) -> Any:
    parts = [_CLOCK]
    if leave:
        parts += [_section(LEAVE_JS, "capa-leave"), _section(LEAVE_JS, "capa-leave-window")]
    parts += [_section(JS, "sheet-send"), _ENV, runner]
    return run_js_json("\n".join(parts), what="Space 호기 정보 창 칸 확인 보내기 시험")


_BATCH_RUNNER = """
const out = {}
{
  resetClock()
  // 잇달아 고친 셋 — 마지막 고침 뒤 쉼에 한 번, 마지막 seq · 칸 전부로.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, false)
  advance(200)
  edit(box, env, false)
  advance(200)
  edit(box, env, false)
  out.dueBusy = sheetSendBusy(box)
  advance(499)
  out.beforeQuiet = env.sent.length
  advance(1)
  out.batched = env.sent
  out.awaitBusy = sheetSendBusy(box)
  out.heard = sheetSendHeard(box, env, 3)
  out.idle = sheetSendBusy(box)
  advance(10000)
  out.afterVerdict = env.sent.length
}
{
  resetClock()
  // 첫 칸 · 단추 op 는 곧바로, 그 뒤 고침은 다시 묶는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  out.first = env.sent.slice()
  sheetSendHeard(box, env, 1)
  edit(box, env, false)
  out.secondAtOnce = env.sent.length
  advance(500)
  out.second = env.sent
}
{
  resetClock()
  // 쉼이 없으면(0) 곧바로 보낸다.
  const box = createSheetSend()
  const env = makeEnv({ sendMs: 0 })
  edit(box, env, false)
  out.noPause = env.sent
}
{
  resetClock()
  // 칸 떠남 · 「적용」 직전(flush)은 묶음을 곧바로 보내고 타이머를 걷는다.
  // 보낼 것이 없으면 보내지 않고 기다림이 걷혔다고만 알린다.
  const box = createSheetSend()
  const env = makeEnv()
  sheetSendFlush(box, env)
  out.flushIdle = [env.sent.length, env.settles]
  edit(box, env, false)
  advance(100)
  sheetSendFlush(box, env)
  out.flushed = env.sent.slice()
  advance(1000)
  out.flushedOnce = env.sent.length
}
{
  resetClock()
  // 묶는 동안 칸이 모두 빠졌으면(보낼 요청이 없음) 보내지 않고 기다림을 걷는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, false)
  env.cells = 0
  advance(500)
  out.emptied = [env.sent.length, sheetSendBusy(box), env.settles]
}
{
  resetClock()
  // 처음 상태로 · 새 도면 · 마운트 내림 — 묶음과 기다림을 버린다(보내지 않는다).
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, false)
  sheetSendStop(box, env)
  advance(5000)
  out.stopped = [env.sent.length, sheetSendBusy(box), clock.timers.size]
}
process.stdout.write(JSON.stringify(out))
"""


def test_cells_typed_in_a_row_go_out_once_after_the_pause_and_first_or_flush_go_at_once() -> None:
    """잇달아 고친 칸은 마지막 고침 뒤 쉼(`sendMs`)이 지나야 한 번 — 마지막 seq 와 고친 칸 전부로 —
    나간다. 첫 칸 · 단추 op(`now`)와 칸 떠남 · 「적용」 직전(`sheetSendFlush`)은 곧바로이고, 쉼이
    0 이면 묶지 않는다. 보낼 것이 남았거나 판정을 기다리는 동안 busy 이고 판정이 오면 걷힌다."""
    out = _node(_BATCH_RUNNER)

    assert out["dueBusy"] is True
    assert out["beforeQuiet"] == 0
    assert out["batched"] == [[900, 3, 3]]
    assert out["awaitBusy"] is True
    assert out["heard"] is True and out["idle"] is False
    assert out["afterVerdict"] == 1
    assert out["first"] == [[0, 1, 1]]
    assert out["secondAtOnce"] == 1
    assert out["second"] == [[0, 1, 1], [500, 2, 2]]
    assert out["noPause"] == [[0, 1, 1]]
    assert out["flushIdle"] == [0, 1]
    assert out["flushed"] == [[100, 1, 1]]
    assert out["flushedOnce"] == 1
    assert out["emptied"] == [0, False, 1]
    assert out["stopped"] == [0, False, 0]


_RETRY_RUNNER = """
const out = {}
{
  resetClock()
  // 판정이 오지 않음(회차 끝 창에서 잃은 트리거) — 회차가 돌지 않으면 같은 요청을 한 번만
  // 다시 보내고, 그것도 오지 않으면 걷는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1499)
  out.beforeRetry = env.sent.length
  advance(1)
  out.resent = env.sent.slice()
  advance(1500)
  out.gaveUp = [env.sent.length, sheetSendBusy(box), env.settles]
  advance(10000)
  out.quiet = env.sent.length
}
{
  resetClock()
  // 회차가 도는 동안은 다시 보내지 않고 `pollMs` 마다 다시 본다 — 끝났는데도 판정이 없으면 회차
  // 끝 뒤 `quietMs` 가 지나서 다시 보낸다(끝을 처음 본 폴에서 곧바로 보내지 않는다).
  const box = createSheetSend()
  const env = makeEnv()
  setRun(env, true)
  edit(box, env, true)
  advance(1900)
  out.whileRunning = env.sent.length
  setRun(env, false)
  advance(100)
  out.firstIdlePoll = env.sent.length
  advance(499)
  out.beforeQuiet = env.sent.length
  advance(1)
  out.afterRun = env.sent.slice()
}
{
  resetClock()
  // 다시 볼 때가 왔는데 회차가 방금 끝났다 — 그 끝에서 `quietMs` 를 센다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1000)
  setRun(env, true)
  advance(450)
  setRun(env, false)
  advance(50)
  out.justEnded = env.sent.length
  advance(600)
  out.afterJustEnded = env.sent.slice()
}
{
  resetClock()
  // 조용한 틈을 세는 동안 다른 회차가 돌면 그 끝에서 다시 센다(폴 사이의 짧은 회차도 표지 감시가
  // 적는다).
  const box = createSheetSend()
  const env = makeEnv()
  setRun(env, true)
  edit(box, env, true)
  advance(1900)
  setRun(env, false)
  advance(300)
  setRun(env, true)
  advance(100)
  setRun(env, false)
  advance(599)
  out.restartedQuiet = env.sent.length
  advance(1)
  out.restarted = env.sent.slice()
}
{
  resetClock()
  // 다시 보낸 것도 오지 않음 — 그 회차가 끝나면 조용한 틈을 기다리지 않고 걷는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1500)
  setRun(env, true)
  advance(1600)
  out.againRunning = [env.sent.length, sheetSendBusy(box)]
  setRun(env, false)
  advance(250)
  out.againDropped = [env.sent.length, sheetSendBusy(box)]
}
{
  resetClock()
  // 그 seq 의 판정이 시간 안에 오면 다시 보내지 않는다. 앞 seq 의 판정은 뒤 seq 의 기다림을
  // 걷지 않는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(400)
  out.older = sheetSendHeard(box, env, 0)
  out.heard = sheetSendHeard(box, env, 1)
  advance(10000)
  out.noResend = env.sent.length
}
{
  resetClock()
  // 보낸 뒤 다시 고쳤으면 옛 요청은 다시 보내지 않는다 — 그 묶음이 새 seq 로 보낸다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1200)
  edit(box, env, false)
  advance(300)
  out.superseded = [env.sent.length, sheetSendBusy(box)]
  advance(200)
  out.newer = env.sent
}
process.stdout.write(JSON.stringify(out))
"""


def test_a_check_without_a_verdict_is_resent_once_after_a_quiet_gap_and_then_dropped() -> None:
    """확인은 트리거라 앞 회차 끝 직후에 보낸 것은 서버에 닿지 않을 수 있다. 보낸 seq 의 판정이
    `retryMs` 안에 오지 않으면 같은 요청(같은 seq · 칸)을 한 번만 다시 보내고, 그것도 오지 않으면
    기다림을 걷는다(busy 가 떠나기를 10초 붙들지 않게). 회차가 도는 동안은 기다리고, 다시 보내는
    것은 회차 끝 뒤 `quietMs` 동안 조용할 때다 — 끝을 처음 본 폴 · 방금 끝난 회차 · 그 틈에 다시 돈
    회차 끝에서 곧바로 보내면 다시 보낸 것도 같은 회차 끝 창에서 지워질 수 있다. 시간 안에 온
    판정 · 그 뒤 다시 고친 칸이 있으면 다시 보내지 않는다."""
    out = _node(_RETRY_RUNNER)

    assert out["beforeRetry"] == 1
    assert out["resent"] == [[0, 1, 1], [1500, 1, 1]]
    assert out["gaveUp"] == [2, False, 1]
    assert out["quiet"] == 2
    assert out["whileRunning"] == 1
    assert out["firstIdlePoll"] == 1 and out["beforeQuiet"] == 1
    assert out["afterRun"] == [[0, 1, 1], [2500, 1, 1]]
    assert out["justEnded"] == 1
    assert out["afterJustEnded"] == [[0, 1, 1], [2050, 1, 1]]
    assert out["restartedQuiet"] == 1
    assert out["restarted"] == [[0, 1, 1], [2900, 1, 1]]
    assert out["againRunning"] == [2, True]
    assert out["againDropped"] == [2, False]
    assert out["older"] is False and out["heard"] is True
    assert out["noResend"] == 1
    assert out["superseded"] == [1, True]
    assert out["newer"] == [[0, 1, 1], [1700, 2, 2]]


_APPLY_RUNNER = """
const out = {}
{
  resetClock()
  // 확인(seq 1)이 닿지 않은 채 「적용」 — 다시 보냄을 `retryMs` 뒤로 미루고, 그 사이 온
  // 거부(「적용」 때 seq 1 까지)가 기다림을 걷어 같은 칸을 다시 묻지 않는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1400)
  sheetSendDefer(box, env)
  advance(1000)
  out.deferred = env.sent.length
  out.refusal = sheetSendHeard(box, env, 1)
  advance(10000)
  out.afterRefusal = [env.sent.length, sheetSendBusy(box)]
}
{
  resetClock()
  // 「적용」 도 닿지 않음 — 미룬 시간이 지나면 그대로 한 번 다시 보낸다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  advance(1400)
  sheetSendDefer(box, env)
  advance(1500)
  out.applyLost = env.sent
}
{
  resetClock()
  // 「적용」 뒤 다시 고친 칸 — 「적용」 때 seq 의 거부는 그 뒤 seq 의 기다림을 걷지 않는다.
  const box = createSheetSend()
  const env = makeEnv()
  edit(box, env, true)
  sheetSendHeard(box, env, 1)
  sheetSendDefer(box, env)
  out.nothingToDefer = clock.timers.size
  edit(box, env, false)
  advance(500)
  out.later = sheetSendHeard(box, env, 1)
  out.laterBusy = sheetSendBusy(box)
}
process.stdout.write(JSON.stringify(out))
"""


def test_an_apply_defers_the_resend_and_its_refusal_ends_the_wait_up_to_its_seq() -> None:
    """「적용」 은 고친 칸 전부를 한 번 더 판정한다. 기다리던 확인이 닿지 않은 채 「적용」 을
    보내면 다시 보냄을 `retryMs` 뒤로 미루고(`sheetSendDefer`), 막힌 칸으로 거부한 판정이 오면
    「적용」 때 seq 까지의 기다림을 걷는다 — 다시 보낸 확인이 거부 뒤에 닿아 같은 막힌 칸을
    `EQ-25` 로 한 번 더 알리지 않게. 「적용」 도 닿지 않았으면 미룬 뒤 그대로 다시 보내고, 「적용」
    뒤에 고친 칸의 기다림은 그 거부로 걷지 않는다. 기다릴 것이 없으면 미룰 것도 없다."""
    out = _node(_APPLY_RUNNER)

    assert out["deferred"] == 1
    assert out["refusal"] is True
    assert out["afterRefusal"] == [1, False]
    assert out["applyLost"] == [[0, 1, 1], [2900, 1, 1]]
    assert out["nothingToDefer"] == 0
    assert out["later"] is False and out["laterBusy"] is True


_LEAVE_RUNNER = """
const handlers = new Map()
const win = {
  CustomEvent: class {
    constructor(type) {
      this.type = type
    }
  },
  addEventListener(type, fn) {
    if (!handlers.has(type)) handlers.set(type, new Set())
    handlers.get(type).add(fn)
  },
  removeEventListener(type, fn) {
    if (handlers.has(type)) handlers.get(type).delete(fn)
  },
  dispatchEvent(event) {
    for (const fn of handlers.get(event.type) || []) fn(event)
    return true
  },
}
const out = {}
const box = createSheetSend()
const env = makeEnv()
const handle = joinLeaving(win, {
  busy: () => sheetSendBusy(box),
  flush: () => sheetSendFlush(box, env),
})
env.settled = () => settleLeaving(handle, sheetSendBusy(box))
const book = editorBook(win)
// 편집기는 떠나기 신호 뒤로는 묶지 않는다(`sheetEditSend` 의 `leavingNow`).
const typed = () => edit(box, env, leavingNow(handle))
typed()
out.idle = [env.sent.length, editorsBusy(book)]
announceLeaving(win)
out.onLeave = [env.sent.slice(), leavingNow(handle), editorsBusy(book)]
typed()
out.whileLeaving = env.sent.length
if (sheetSendHeard(box, env, 2)) env.settled()
out.settled = [leavingNow(handle), editorsBusy(book)]
typed()
out.batchedAgain = env.sent.length
advance(500)
// 판정을 기다리는 동안 받은 신호 — 보낼 것은 없지만 판정이 올 때까지 묶지 않고 붙든다.
announceLeaving(win)
out.awaiting = [env.sent.length, leavingNow(handle), editorsBusy(book)]
// 떠나기 뒤 잃은 확인 — 한 번 다시 보내고 그것도 오지 않으면 걷혀 붙들기를 풀고 다시 묶는다.
advance(1500)
advance(1500)
out.lost = [env.sent.length, leavingNow(handle), editorsBusy(book)]
// 보낼 것도 기다릴 판정도 없을 때 받은 신호 — 곧바로 걷혀,
// 떠나기를 취소하고 머문 뒤 고침은 다시 묶는다.
announceLeaving(win)
out.idleSignal = [env.sent.length, leavingNow(handle), editorsBusy(book)]
advance(5000)
typed()
out.stayed = env.sent.length
advance(500)
out.stayedBatched = env.sent.slice(4)
handle.drop()
out.dropped = [book.entries.size, (handlers.get('capa-leaving') || new Set()).size]
process.stdout.write(JSON.stringify(out))
"""


def test_the_leave_signal_sends_the_pending_cells_at_once_and_holds_until_the_verdict() -> None:
    """화면을 떠나는 누름의 떠나기 신호(`capa-leaving`)에 묶어 두던 칸을 곧바로 보낸다. 판정이 올
    때까지 명부에 busy 라 탭 줄 붙들기가 기다리고, 신호 뒤 고침은 묶지 않는다. 판정이 오면(또는
    다시 보낸 것도 오지 않아 걷으면) 붙들기가 풀리고 다시 묶는다. 보낼 것도 기다릴 판정도 없을 때
    받은 신호는 곧바로 걷혀, 떠나기를 취소하고 머문 뒤 고침도 다시 묶는다. 마운트를 내리면 명부 ·
    처리기에서 빠진다."""
    out = _node(_LEAVE_RUNNER, leave=True)

    assert out["idle"] == [0, True]
    assert out["onLeave"] == [[[0, 1, 1]], True, True]
    assert out["whileLeaving"] == 2
    assert out["settled"] == [False, False]
    assert out["batchedAgain"] == 2
    assert out["awaiting"] == [3, True, True]
    assert out["lost"] == [4, False, False]
    assert out["idleSignal"] == [4, False, False]
    assert out["stayed"] == 4
    assert out["stayedBatched"] == [[9000, 4, 4]]
    assert out["dropped"] == [0, 0]


_BIND_RUNNER = """
const handlers = new Map()
const target = (name) => ({
  addEventListener(type, fn) {
    const key = name + ':' + type
    if (!handlers.has(key)) handlers.set(key, new Set())
    handlers.get(key).add(fn)
  },
  removeEventListener(type, fn) {
    const key = name + ':' + type
    if (handlers.has(key)) handlers.get(key).delete(fn)
  },
  dispatchEvent(event) {
    for (const fn of handlers.get(name + ':' + event.type) || []) fn(event)
    return true
  },
})
const window = Object.assign(target('window'), {
  setTimeout: fakeSetTimeout,
  clearTimeout: fakeClearTimeout,
  CustomEvent: class {
    constructor(type) {
      this.type = type
    }
  },
})
// 편집기는 회차 표지가 바뀐 때를 `Date.now` 로 적는다 — 가짜 시계로 돌린다.
Date.now = () => clock.now
let scriptState = 'notRunning'
const appRoot = { getAttribute: (name) => (name === 'data-test-script-state' ? scriptState : null) }
const watches = { made: 0, observed: 0, cut: 0, fire: null }
class MutationObserver {
  constructor(fn) {
    watches.made += 1
    watches.fire = fn
  }
  observe(node, options) {
    const named = options.attributeFilter.includes('data-test-script-state')
    if (node === appRoot && named) watches.observed += 1
  }
  disconnect() {
    watches.cut += 1
  }
}
// 표지를 바꾸고 감시에 알린다.
function runState(state) {
  scriptState = state
  watches.fire()
}
const document = Object.assign(target('document'), {
  visibilityState: 'visible',
  querySelector: (selector) => (selector === '[data-testid="stApp"]' ? appRoot : null),
})
const count = (key) => (handlers.get(key) || new Set()).size
const S = { sheetCells: new Map(), sheetSeq: 0, epoch: 'e1' }
// 편집기 상태를 단 요소(`.sle`) — 떠나기 명부의 셋째 인자(부품 뿌리).
const host = { isConnected: true }
const sheetEditCells = () => S.sheetCells
const sheetEditPayload = (cells) => [...cells.values()]
const sent = []
function call(i) {
  const data = { sheetSendMs: 500 + i, sheetEdit: { cols: [] } }
  const SHEET_EDIT = data.sheetEdit
  const setTriggerValue = (name, value) => sent.push([i, name, value.seq])
  %(bind)s
}
function cleanup() {
  %(unbind)s
}
const out = {}
call(0)
const counts = [[count('window:capa-leaving'), count('document:visibilitychange')]]
// 첫 호출에 걸어 둔 묶음 타이머는 마지막 호출의 바깥 몫(`current`)으로 보낸다.
S.sheetCells.set('k', { id: 'U1', col: 'c', text: 't' })
S.sheetSeq = 1
sheetSendQueue(S.sheetSend, S.sheetEnv, false)
for (let i = 1; i < 50; i += 1) call(i)
counts.push([count('window:capa-leaving'), count('document:visibilitychange')])
out.counts = counts
out.watches = [watches.made, watches.observed, watches.cut]
out.latest = S.sheetEnv.sendMs
out.mount = typeof S.sheetMount === 'string' && S.sheetMount.length > 3
advance(500)
out.sentBy = sent.slice()
sheetSendHeard(S.sheetSend, S.sheetEnv, 1)
// 창 숨김은 묶음을 곧바로 보낸다.
S.sheetSeq = 2
sheetSendQueue(S.sheetSend, S.sheetEnv, false)
document.visibilityState = 'hidden'
document.dispatchEvent({ type: 'visibilitychange' })
out.hidden = sent.length
// 그 확인(seq 2)의 판정이 오지 않음 — 감시가 적은 회차 끝(1800)에서 조용한 틈을 센 뒤 한 번 다시
// 보낸다(다시 볼 때 2000 에는 끝난 지 200 이다).
advance(500)
runState('running')
advance(800)
runState('notRunning')
advance(599)
out.quietWait = sent.length
advance(1)
out.resent = sent.slice(-1)
// 판정을 기다리는 동안 busy 이고, 부품 뿌리가 문서에서 떨어지면 그 판정은 busy 가 아니다.
out.rooted = [editorsBusy(editorBook(window))]
host.isConnected = false
out.rooted.push(editorsBusy(editorBook(window)))
host.isConnected = true
cleanup()
out.unbound = [count('window:capa-leaving'), count('document:visibilitychange'), clock.timers.size]
out.unwatched = [watches.cut, S.sheetRunWatch]
S.sheetSeq = 3
sheetSendQueue(S.sheetSend, S.sheetEnv, false)
window.dispatchEvent(new window.CustomEvent('capa-leaving'))
out.afterUnbind = sent.length
process.stdout.write(JSON.stringify(out))
"""


def test_the_editor_binds_the_leave_and_hide_listeners_once_and_unbinds_them() -> None:
    """편집기 default export 는 data 가 바뀔 때마다 다시 불리고 앞 호출의 정리 함수는 불리지 않는다
    — 떠나기 명부 · 창 숨김 처리기 · 회차 표지 감시는 50번 불러도 한 벌이다. 타이머는 늘 마지막
    호출의 바깥 몫(새 `setTriggerValue` · 쉼)으로 보내고, 창 숨김은 묶음을 곧바로 보낸다. 판정이
    오지 않은 확인은 감시가 적은 회차 끝에서 조용한 틈(`SHEET_QUIET_MS`)을 센 뒤 다시 보낸다.
    명부에는 부품 뿌리(`host`)와 함께 올라 뿌리가 문서에서 떨어지면 busy 가 아니다. 정리 함수는
    명부 · 처리기 · 감시 · 타이머를 걷는다."""
    bind = _section(JS, "sheet-send-bind")
    unbind = _section(JS, "sheet-send-unbind")
    out = _node(_BIND_RUNNER % {"bind": bind, "unbind": unbind}, leave=True)

    assert out["counts"] == [[1, 1], [1, 1]]
    assert out["watches"] == [1, 1, 0]
    assert out["latest"] == 549
    assert out["mount"] is True
    assert out["sentBy"] == [[49, "sheetCheck", 1]]
    assert out["hidden"] == 2
    assert out["quietWait"] == 2
    assert out["resent"] == [[49, "sheetCheck", 2]]
    assert out["rooted"] == [True, False]
    assert out["unbound"] == [0, 0, 0]
    assert out["unwatched"] == [1, None]
    assert out["afterUnbind"] == 3


def test_the_registered_script_carries_the_leave_piece_ahead_of_the_editor() -> None:
    """등록 글은 떠나기 조각(`grid_shared.leave_js`) · 날짜 판 머리 · 편집기 차례다 — 편집기가
    부르는 `joinLeaving` · `leavingNow` · `settleLeaving` 이 실리고, 이어 붙인 글 전체가 한 ES
    모듈로 읽힌다(같은 이름을 두 번 선언하지 않는다)."""
    register = MODULE[MODULE.index("_EDITOR = st.components.v2.component(") :]
    register = register[: register.index("\n)\n")]
    assert register.index("js=grid_shared.leave_js()") < register.index("DATE_PANEL_MOUNT_JS")
    for name in (
        "joinLeaving(window, {",
        "leavingNow(S.sheetLeave)",
        "settleLeaving(S.sheetLeave,",
    ):
        assert name in JS, name
    joined = LEAVE_JS + "\n" + DATE_PANEL_MOUNT_JS + JS
    checked = check_js_module(joined, what="Space 편집기 등록 글 문법 시험")
    assert checked.returncode == 0, checked.stderr


def test_the_window_cells_leave_apply_and_reset_reach_the_sender() -> None:
    """편집기 잇기 — 창 밖으로 초점이 나가면(입력 칸 blur · 창 focusout — 처리기가 끝난 뒤 지금
    초점으로 봄) 곧바로 보내고, 「적용」 은 묶어 두던 확인을 적용 트리거보다 먼저 보낸다(같은
    틱의 두 트리거는 한 요청에 실린다). 처음 상태로 · 새 도면은 묶음 · 기다림을 버리고, 판정은 이
    마운트가 보낸 seq 의 기다림을 걷는다."""
    left = JS[JS.index("  function sheetLeftSoon() {") :]
    left = left[: left.index("\n  }\n")]
    assert "window.setTimeout(() => {" in left
    assert "sheetBox.contains(host.getRootNode().activeElement)) return" in left
    assert "sheetSendFlush(S.sheetSend, S.sheetEnv)" in left
    assert "sheetBox.onfocusout = () => sheetLeftSoon()" in JS
    apply = JS[JS.index("  applyButton.onclick = () => {") :]
    apply = apply[: apply.index("\n  }\n")]
    assert apply.index("closeSheetCell(true)") < apply.index(
        "sheetSendFlush(S.sheetSend, S.sheetEnv)"
    )
    assert apply.index("sheetSendFlush(S.sheetSend, S.sheetEnv)") < apply.index(
        "setTriggerValue('apply', {"
    )
    reset = JS[JS.index("  function resetSheetEdit() {") :]
    reset = reset[: reset.index("\n  }\n")]
    assert reset.index("sheetSendStop(S.sheetSend, S.sheetEnv)") < reset.index(
        "S.sheetSeq = (S.sheetSeq || 0) + 1"
    )
    adopt = JS[JS.index("  function adoptSheetEdit() {") :]
    adopt = adopt[: adopt.index("\n  }\n")]
    assert "verdict.mount === S.sheetMount" in adopt
    assert adopt.index("sheetSendHeard(S.sheetSend, S.sheetEnv, verdict.seq)") < adopt.index(
        "S.sheetVerdict = sheetEditVerdict(verdict)"
    )
    # 묶음 쉼은 파이썬 상수 하나가 data 로 넘긴다(개발 · 측정 사본만 실행 줄 덮어쓰기).
    assert '"sheetSendMs": grid_shared.batch_ms(SHEET_SEND_MS),' in MODULE


def _function(name: str) -> str:
    """편집기 몸의 함수 하나(2칸 들여 쓴 `function name(` 부터 그 닫는 줄까지)."""
    start = JS.index(f"  function {name}(")
    return JS[start : JS.index("\n  }\n", start) + 4]


def _handler(head: str) -> str:
    """편집기 몸에서 처리기 하나를 다는 글(`head` 부터 그 닫는 줄까지)."""
    start = JS.index(head)
    return JS[start : JS.index("\n  }\n", start) + 4]


_FOCUS_DOM = """
Date.now = () => clock.now
// 그림자 뿌리 안의 초점을 쥔 가짜 요소. 초점이 옮겨 가면 앞 요소의 blur 를 먼저 부르고, 그
// 뒤의 조상 길(blur 처리기가 요소를 걷었으면 그만큼 짧다)로 focusout 을 올린다. 초점을 쥔 요소를
// 걷으면 걷기 전 조상 길로 focusout 을 올린다(Chrome 처럼 — 걷는 동안 사건이 나도 편집기가
// 견뎌야 한다).
let focused = null
function ancestors(node) {
  const path = []
  for (let at = node; at; at = at.parentElement) path.push(at)
  return path
}
function bubbleOut(path, from, to) {
  for (const at of path) {
    if (typeof at.onfocusout === 'function') at.onfocusout({ target: from, relatedTarget: to })
  }
}
function moveFocus(target) {
  if (focused === target) return
  const was = focused
  focused = target
  if (!was) return
  if (typeof was.onblur === 'function') was.onblur({ relatedTarget: target })
  bubbleOut(ancestors(was), was, target)
}
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase()
    this.children = []
    this.parentElement = null
    this.dataset = {}
    this.attrs = {}
    this.value = ''
    this.textContent = ''
    const names = new Set()
    this.classList = {
      add: (...list) => list.forEach((one) => names.add(one)),
      remove: (...list) => list.forEach((one) => names.delete(one)),
      toggle: (one, on) => (on ? names.add(one) : names.delete(one)),
      contains: (one) => names.has(one),
    }
  }
  get nextElementSibling() {
    const up = this.parentElement
    return up ? up.children[up.children.indexOf(this) + 1] || null : null
  }
  get previousElementSibling() {
    const up = this.parentElement
    return up ? up.children[up.children.indexOf(this) - 1] || null : null
  }
  append(...nodes) {
    for (const node of nodes) {
      node.parentElement = this
      this.children.push(node)
    }
  }
  replaceChildren(...nodes) {
    const lost = focused !== null && this.children.some((child) => child.contains(focused))
    const path = lost ? ancestors(focused) : []
    const was = focused
    for (const child of this.children) child.parentElement = null
    this.children = []
    this.append(...nodes)
    if (!lost) return
    focused = null
    bubbleOut(path, was, null)
  }
  contains(node) {
    for (let at = node; at; at = at.parentElement) if (at === this) return true
    return false
  }
  focus() {
    moveFocus(this)
  }
  select() {}
  setAttribute(name, value) {
    this.attrs[name] = String(value)
  }
  removeAttribute(name) {
    delete this.attrs[name]
  }
}
const handlers = new Map()
const target = (name) => ({
  addEventListener(type, fn) {
    const key = name + ':' + type
    if (!handlers.has(key)) handlers.set(key, new Set())
    handlers.get(key).add(fn)
  },
  removeEventListener(type, fn) {
    const key = name + ':' + type
    if (handlers.has(key)) handlers.get(key).delete(fn)
  },
  dispatchEvent(event) {
    for (const fn of handlers.get(name + ':' + event.type) || []) fn(event)
    return true
  },
})
const window = Object.assign(target('window'), {
  setTimeout: fakeSetTimeout,
  clearTimeout: fakeClearTimeout,
  CustomEvent: class {
    constructor(type) {
      this.type = type
    }
  },
})
const document = Object.assign(target('document'), {
  visibilityState: 'visible',
  querySelector: () => null,
  createElement: (tag) => new El(tag),
  createTextNode: (text) => Object.assign(new El('#text'), { textContent: text }),
})
// 편집기 몸 — 창(`sheetBox`) 안의 표 줄, 창 밖의 도면 자리, 그림자 뿌리 밖의 자리.
const host = new El('div')
const sheetBox = new El('div')
const sheetBodyRows = new El('tbody')
const drawing = new El('svg')
const page = new El('body')
host.append(sheetBox, drawing)
sheetBox.append(sheetBodyRows)
const shadow = {
  get activeElement() {
    return focused !== null && host.contains(focused) ? focused : null
  },
}
host.getRootNode = () => shadow
const COLS = ['A', 'B']
for (const id of ['U1', 'U2', 'U3']) {
  const tr = new El('tr')
  tr.dataset.id = id
  for (const col of COLS) {
    const td = new El('td')
    td.dataset.col = col
    td.dataset.shown = id + col
    td.append(document.createTextNode(id + col))
    tr.append(td)
  }
  sheetBodyRows.append(tr)
}
const SHEET_EDIT = {
  cols: COLS,
  rows: {
    U1: { t: ['U1A', 'U1B'], k: [] },
    U2: { t: ['U2A', 'U2B'], k: [] },
    U3: { t: ['U3A', 'U3B'], k: [] },
  },
  kinds: {},
  fixed: {},
  locks: {},
  reasons: {},
}
const S = { epoch: 'e1', sheet: { columns: COLS.map((name) => ({ name })) } }
let data = { sheetSendMs: 500, sheetEdit: SHEET_EDIT, sheetVerdict: null, sheetRefused: null }
const triggers = []
// 확인은 seq 를, 적용은 실은 칸 수를 적는다.
const setTriggerValue = (name, value) => {
  triggers.push([clock.now, name, name === 'sheetCheck' ? value.seq : value.cells.length])
}
const noop = () => {}
const showTip = noop
const hideTip = noop
const revealSheetCell = noop
const paintSheetCell = noop
const renderSheet = noop
const pushUndo = noop
const updateStatus = noop
// 「적용」 의 배치 몫 — 창 칸만 고친 적용이다.
const applyButton = {}
const FAB = false
const changes = () => []
const renames = () => []
const ghostChanges = () => []
const markChangeCount = () => 0
const groupLabelChangeCount = () => 0
const canvasChanged = () => false
const stackChanged = () => false
const marksPayload = () => null
const groupLabelsPayload = () => ({})
const stackPayload = () => null
const W = () => 100
const H = () => 60
const rowOf = (id) => sheetBodyRows.children.find((tr) => tr.dataset.id === id)
const key = (name) => ({ key: name, shiftKey: false, preventDefault: noop, stopPropagation: noop })
const checks = () => triggers.filter((one) => one[1] === 'sheetCheck')
// 이 마운트가 마지막으로 보낸 seq 의 판정(막힌 칸 없음)이 와 받는다.
function heardAll() {
  const verdict = { epoch: 'e1', mount: S.sheetMount, seq: S.sheetSeq, blocked: [], follow: [] }
  data = { ...data, sheetVerdict: verdict }
  adoptSheetEdit()
}
// 칸을 열어 글을 친다 — 열린 입력 칸을 돌려준다. 여는 동안 줄에서 입력 칸으로 옮긴 초점의
// focusout 은 그 자리에서 끝낸다(사람이 치는 사이에 지나간다).
function typeInto(id, col, text) {
  openSheetCell(id, col)
  advance(0)
  S.sheetOpen.input.value = text
  return S.sheetOpen.input
}
"""

_FOCUS_RUNNER = """
const out = {}
// Enter — 입력 칸을 걷는 동안 초점이 잠깐 빠졌다가 같은 처리기 안에서 아래 줄로 돌아온다. 첫
// 칸은 곧바로.
typeInto('U1', 'A', 'x1').onkeydown(key('Enter'))
advance(0)
out.enterFirst = [checks(), shadow.activeElement === rowOf('U2')]
// Enter · 창 안 다른 칸 누름(초점이 그 줄로) · Tab — 묶는다.
typeInto('U2', 'A', 'x2').onkeydown(key('Enter'))
advance(0)
typeInto('U3', 'A', 'x3')
moveFocus(rowOf('U1'))
advance(0)
typeInto('U3', 'B', 'y3').onkeydown(key('Tab'))
advance(0)
out.inside = [checks().length, sheetSendBusy(S.sheetSend), sheetBox.contains(shadow.activeElement)]
advance(499)
out.beforePause = checks().length
advance(1)
out.batched = checks().slice(1)
heardAll()
out.heard = sheetSendBusy(S.sheetSend)
// 창 밖(도면 · 화면 밖) 누름 — 곧바로 보낸다.
advance(1000)
typeInto('U1', 'B', 'y1')
moveFocus(drawing)
out.drawingSync = checks().length
advance(0)
out.drawing = checks().slice(-1)
heardAll()
moveFocus(rowOf('U1'))
typeInto('U2', 'B', 'y2')
moveFocus(page)
advance(0)
out.page = checks().slice(-1)
process.stdout.write(JSON.stringify(out))
"""

_APPLY_EDITOR_RUNNER = """
const out = {}
// Enter 로 고친 칸 셋 — 묶어 둔 확인은 「적용」 이 적용 트리거보다 먼저(같은 틱) 보낸다.
typeInto('U1', 'A', 'x1').onkeydown(key('Enter'))
typeInto('U2', 'A', 'x2').onkeydown(key('Enter'))
typeInto('U3', 'A', 'x3').onkeydown(key('Enter'))
advance(100)
applyButton.onclick()
out.sameTick = triggers.slice(1)
// 그 확인(seq 3)이 닿지 않은 채 거부가 온다 — 「적용」 때의 seq 까지 기다림을 걷어 다시 묻지
// 않는다.
advance(1400)
out.deferred = checks().length
data = {
  ...data,
  sheetRefused: {
    epoch: 'e1',
    nonce: 'n1',
    blocked: [{ id: 'U3', col: 'A', text: 'x3', rule: 'r', message: 'm' }],
    follow: [],
  },
}
adoptSheetEdit()
out.refused = [sheetSendBusy(S.sheetSend), sheetEditBlocked(sheetEditCells(), S.sheetVerdict)]
advance(10000)
out.afterRefusal = checks().length
// 막힌 칸을 고친 확인이 쉼 뒤에 나갔으나 닿지 않았고, 1.4초 뒤 「적용」 도 닿지 않음 — 다시 보냄은
// 「적용」 뒤 `SHEET_RETRY_MS` 로 미룬 자리에서 한 번이다.
typeInto('U3', 'A', 'x4').onkeydown(key('Enter'))
advance(500)
out.fixedSent = checks().slice(-1)
advance(1400)
applyButton.onclick()
const appliedAt = clock.now
out.applied = triggers.slice(-1)
advance(1499)
out.lostBoth = checks().length
advance(1)
out.resentAfterApply = checks().slice(-1).map(([at, name, seq]) => [at - appliedAt, name, seq])
process.stdout.write(JSON.stringify(out))
"""


def _editor_harness(runner: str) -> Any:
    names = (
        "sheetEditCells",
        "sheetEditTd",
        "sheetEditRow",
        "setSheetCursor",
        "moveSheetCursor",
        "openSheetCell",
        "closeSheetCell",
        "commitSheetCell",
        "sheetEditSend",
        "sheetLeftSoon",
        "adoptSheetEdit",
    )
    wire = "    sheetBox.onfocusout = () => sheetLeftSoon()"
    assert wire in JS
    parts = [
        _CLOCK,
        _section(LEAVE_JS, "capa-leave"),
        _section(LEAVE_JS, "capa-leave-window"),
        _section(JS, "sheet-edit"),
        _section(JS, "sheet-send"),
        _FOCUS_DOM,
        _section(JS, "sheet-send-bind"),
        *(_function(name) for name in names),
        wire,
        _handler("  applyButton.onclick = () => {"),
        runner,
    ]
    return run_js_json("\n".join(parts), what="Space 호기 정보 창 초점 · 적용 시험")


def test_moving_within_the_window_batches_and_leaving_it_sends_at_once() -> None:
    """편집기 몸의 칸 열기 · 닫기 · 확정 · 칸 떠남(`openSheetCell` · `closeSheetCell` ·
    `sheetLeftSoon` · 창 focusout)을 가짜 DOM 에서 돌린다. Enter · Tab 으로 칸을 옮기거나 창 안 다른
    칸을 누르면 초점이 창(줄)에 남아 묶이고 — 입력 칸을 걷는 동안 초점이 잠깐 빠져 focusout 이 나도
    처리기가 끝난 뒤 지금 초점으로 본다 — 마지막 고침 뒤 쉼에 한 번 나간다. 첫 칸은 곧바로다. 도면
    · 화면 밖을 누르면 그 자리에서 곧바로 보낸다."""
    out = _editor_harness(_FOCUS_RUNNER)

    assert out["enterFirst"] == [[[0, "sheetCheck", 1]], True]
    assert out["inside"] == [1, True, True]
    assert out["beforePause"] == 1
    assert out["batched"] == [[500, "sheetCheck", 4]]
    assert out["heard"] is False
    assert out["drawingSync"] == 2
    assert out["drawing"] == [[1500, "sheetCheck", 5]]
    assert out["page"] == [[1500, "sheetCheck", 6]]


def test_the_apply_button_sends_the_pending_check_first_and_a_refusal_ends_its_wait() -> None:
    """편집기 몸의 「적용」 처리기 · 판정 받기(`applyButton.onclick` · `adoptSheetEdit`)를 가짜
    DOM 에서 돌린다. 묶어 둔 확인은 적용 트리거보다 먼저 같은 틱에 나간다. 그 확인이 닿지 않은 채
    막힌 칸으로 거부(`sheetRefused`)가 오면 「적용」 때 seq 까지의 기다림을 걷어 같은 칸을 다시
    묻지 않는다(다시 보낸 확인이 `EQ-25` 를 한 번 더 내지 않게). 적용까지 닿지 않았으면 다시 보냄은
    「적용」 뒤 `SHEET_RETRY_MS` 에 한 번이다."""
    out = _editor_harness(_APPLY_EDITOR_RUNNER)

    assert out["sameTick"] == [[100, "sheetCheck", 3], [100, "apply", 3]]
    assert out["deferred"] == 2
    assert out["refused"] == [False, 1]
    assert out["afterRefusal"] == 2
    assert out["fixedSent"] == [[12000, "sheetCheck", 4]]
    assert out["applied"] == [[13400, "apply", 3]]
    assert out["lostBoth"] == 3
    assert out["resentAfterApply"] == [[1500, "sheetCheck", 4]]
