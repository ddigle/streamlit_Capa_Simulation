// 편집기 공용 조각 — 떠나기 신호 · 편집기 명부 · 편집기 구역 회차 표지(AGENTS 9장 「구역 회차 규칙」 R8). 표 공용 조각(설비
// 마스터 표 · 시나리오 목록 표)과 범용 편집 그리드 · 화면 탭 줄이 함께 싣는다. 이 글은 등록마다 잇대어 실려 모듈마다 따로 돈다 — 상태는
// 모두 창 칸(`window.__capaEditors` · `window.__capaScopeRun`)에 두고 모듈 전역에 두지 않는다. 먼저 선 칸을 뒤 모듈이 그대로 쓴다.
//
// 화면을 떠나는 누름(탭 줄 고르기 · 지금 탭 닫기 · 사이드바 화면 링크 · 테마 단추 · 알림 칸 「그 화면으로」)은 화면을 옮기는 요청을
// 보내기 **전에** 창 사건 `capa-leaving` 을 쏜다(`announceLeaving`). 편집기는 그 자리에서 묶음 타이머를 멈추고 남은 op 를 곧바로
// 보낸다(`joinLeaving` 의 `flush`). 보낼 것이 남았거나 ack 가 오지 않은 동안 편집기는 명부에 busy 다 — 탭 줄 붙들기
// (`page_tabs.js` 의 `<tabs-hold>`)가 그 busy 가 걷히고 회차가 끝날 때까지(길어야 `BUSY_MS`) 기다린 뒤 떠난다. 떠나기 신호 뒤로는
// 묶지 않고 곧바로 보내며(`leavingNow`), 보낼 것이 다 걷히면(`settleLeaving`) 다시 묶는다. 신호를 받은 순간 보낼 것도 ack
// 기다림도 없는 편집기는 그 자리에서 걷는다 — 화면에 머무는 누름(지금 화면 링크 · 떠나기 확인 취소 · 상한에 막힌 링크)도 신호를
// 쏘므로, 머문 뒤 다음 고침도 묶인다.

// <capa-leave>
// 편집기 명부(순수) — 창 칸 하나(`book`)에 편집기마다 busy 판정 함수를 단다. 판정이 던지면 busy 가 아니다(내린 편집기의 낡은
// 함수가 남아 붙들기를 묶지 않게).
const LEAVING_EVENT = 'capa-leaving'
const EDITORS_SLOT = '__capaEditors'
function editorBook(host) {
  let book = host[EDITORS_SLOT]
  if (!book || typeof book !== 'object' || !(book.entries instanceof Map)) {
    book = { entries: new Map(), next: 0 }
    host[EDITORS_SLOT] = book
  }
  return book
}
function enrollEditor(book, busy) {
  book.next += 1
  book.entries.set(book.next, busy)
  return book.next
}
function dropEditor(book, id) {
  book.entries.delete(id)
}
function editorsBusy(book) {
  for (const busy of book.entries.values()) {
    try {
      if (busy()) return true
    } catch (error) {
      // 판정할 수 없는 편집기는 붙들기를 묶지 않는다.
    }
  }
  return false
}
// 떠나기 신호를 받은 편집기는 다음 op 를 묶지 않는다 — 보낼 것이 다 걷히면 다시 묶는다.
function leavingNow(handle) {
  return Boolean(handle && handle.leaving)
}
function settleLeaving(handle, busy) {
  if (handle && !busy) handle.leaving = false
}
// </capa-leave>

// <capa-leave-window>
// 떠나기 신호를 쏜다 — 받는 편집기는 처리기 안에서 곧바로 보낸다(동기). 쏜 뒤의 busy 는 `editorsBusy(editorBook(win))` 로 본다.
function announceLeaving(win) {
  if (typeof win.dispatchEvent !== 'function' || typeof win.CustomEvent !== 'function') return
  win.dispatchEvent(new win.CustomEvent(LEAVING_EVENT))
}
// 편집기 하나를 명부에 올리고 떠나기 신호를 받는다 — `busy()` 는 보낼 것이 남았거나 ack 를 기다리는가, `flush()` 는 묶음 타이머를
// 멈추고 남은 op 를 곧바로 보낸다. 보낸 뒤에도 busy 가 아니면(보낼 것도 ack 기다림도 없었다) 곧바로 걷는다(`settleLeaving` 과
// 같은 뜻 — ack 뒤 스스로 걷는 편집기와 겹쳐도 같다). 돌려준 손잡이(`leaving` · `drop`)는 편집기 상태에 두고, 정리 함수에서
// `drop()` 한다. `root`(부품 뿌리 — 편집기 상태를 단 요소처럼 부품과 함께 문서에서 떨어지는 요소, 주지 않아도 된다)를 주면
// 그 뿌리가 문서에서 떨어진 뒤(`isConnected` 거짓)의 판정은 busy 가 아니다 — `drop()` 을 빠뜨린 채 내린 편집기가 떠나는 누름마다
// 붙들기를 묶지 않게. 명부에 오르는 편집기는 모두 넘긴다(`tests/test_leave_assets.py` 의 `_ENROLLING_EDITORS` 에 한 줄).
function joinLeaving(win, hooks, root = null) {
  const book = editorBook(win)
  const handle = { leaving: false, id: 0, drop: () => {} }
  const busy = () => !(root && root.isConnected === false) && Boolean(hooks.busy())
  const onLeave = () => {
    handle.leaving = true
    try {
      hooks.flush()
    } catch (error) {
      // 보내지 못해도 붙들기는 busy 를 보고 기다린다(상한 `BUSY_MS`).
    }
    let still = false
    try {
      still = busy()
    } catch (error) {
      // 판정할 수 없는 편집기는 busy 가 아니다(명부와 같다).
    }
    settleLeaving(handle, still)
  }
  handle.id = enrollEditor(book, busy)
  win.addEventListener(LEAVING_EVENT, onLeave)
  handle.drop = () => {
    win.removeEventListener(LEAVING_EVENT, onLeave)
    dropEditor(book, handle.id)
  }
  return handle
}
// </capa-leave-window>

// <capa-scope-run>
// 편집기 구역 회차 판정(순수). Streamlit 1.63 은 회차가 돌기 시작한 순간 앱 전체 회차면 모든 요소를, 프래그먼트 회차면 그
// 프래그먼트 요소만 낡음(`data-stale`)으로 친다. 그래서 구역 밖 기준 요소(머리 띠 아래 화면 탭 줄 — 프래그먼트 밖)가 낡음이
// 아니고(`outsideStale` 거짓) 구역 칸(`.st-key-capa_scope_…` — 파이썬 `fragment_scope.SCOPE_BOX_PREFIX`) 안에 낡음 요소가
// 있으면(`insideStale`) 편집기 구역만 도는 회차다. 기준 요소가 없으면(`null` — 탭 줄이 서지 않은 화면) 판정하지 않는다.
const SCOPE_BOX_PREFIX = 'capa_scope_'
const SCOPE_RUN_ATTRIBUTE = 'data-capa-scope-run'
const SCOPE_OUTSIDE = '.st-key-page_tabs_strip'
const SCOPE_STALE = '[class*="st-key-' + SCOPE_BOX_PREFIX + '"] [data-stale="true"]'
// 회차가 끝난 뒤 표지를 걷기까지 — Streamlit 실행 표시가 사라지는 전이(200ms) 동안 다시 보이지 않게.
const SCOPE_RUN_LINGER_MS = 250
function scopeRunVerdict(running, outsideStale, insideStale) {
  return Boolean(running) && outsideStale === false && Boolean(insideStale)
}
// </capa-scope-run>

// <capa-scope-run-window>
// 편집기 구역만 도는 회차 동안 문서 뿌리(`<html>`)에 `SCOPE_RUN_ATTRIBUTE` 를 단다 — 머리 띠 스타일(파이썬
// `fragment_scope.SCOPE_RUN_STYLE`)이 그동안 실행 표시(달리는 사람 · Stop)와 구역 칸 안 낡음 흐림을 감춘다. 앱 전체 회차 ·
// 연결 끊김은 그대로다. 판정은 회차 표지(`data-test-script-state`)가 「돈다」 로 바뀐 순간 한 번이다 — 그 순간에는 이번 회차가
// 보낼 요소가 아직 하나도 오지 않았다. 문서에 지킴이 하나(`window.__capaScopeRun`)이고, Streamlit 뿌리가 바뀌었으면 다시 건다.
function watchScopeRuns(win, doc) {
  const root = doc.querySelector('[data-testid="stApp"]')
  if (!root || typeof win.MutationObserver !== 'function') return
  const old = win.__capaScopeRun
  if (old && old.root === root) return
  if (old && old.observer) old.observer.disconnect()
  const watch = { root, observer: null, timer: 0 }
  const mark = doc.documentElement
  const running = () => {
    const state = root.getAttribute('data-test-script-state')
    return state === 'running' || state === 'rerunRequested'
  }
  const update = () => {
    if (running()) {
      win.clearTimeout(watch.timer)
      watch.timer = 0
      const outside = doc.querySelector(SCOPE_OUTSIDE)
      const outsideStale = outside ? outside.getAttribute('data-stale') === 'true' : null
      if (scopeRunVerdict(true, outsideStale, doc.querySelector(SCOPE_STALE) !== null)) mark.setAttribute(SCOPE_RUN_ATTRIBUTE, '')
      else mark.removeAttribute(SCOPE_RUN_ATTRIBUTE)
      return
    }
    if (!mark.hasAttribute(SCOPE_RUN_ATTRIBUTE) || watch.timer) return
    watch.timer = win.setTimeout(() => {
      watch.timer = 0
      if (!running()) mark.removeAttribute(SCOPE_RUN_ATTRIBUTE)
    }, SCOPE_RUN_LINGER_MS)
  }
  watch.observer = new win.MutationObserver(update)
  watch.observer.observe(root, { attributes: true, attributeFilter: ['data-test-script-state'] })
  win.__capaScopeRun = watch
}
// </capa-scope-run-window>
