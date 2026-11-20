// 편집기 공용 조각 — 떠나기 신호 · 편집기 명부 · 편집기 구역 회차 표지(AGENTS 9장 「구역 회차 규칙」 R8). 표 공용 조각(설비
// 마스터 표 · 시나리오 목록 표)과 범용 편집 그리드 · 화면 탭 줄이 함께 싣는다. 이 글은 등록마다 잇대어 실려 모듈마다 따로 돈다 — 상태는
// 모두 창 칸(`window.__capaEditors` · `window.__capaScopeRun`)에 두고 모듈 전역에 두지 않는다. 먼저 선 칸을 뒤 모듈이 그대로 쓴다.
//
// 화면을 떠나는 누름(탭 줄 고르기 · 지금 탭 닫기 · 사이드바 화면 링크 · 테마 단추 · 알림 칸 「그 화면으로」)은 화면을 옮기는 요청을
// 보내기 **전에** 창 사건 `capa-leaving` 을 쏜다(`announceLeaving`). 편집기는 그 자리에서 묶음 타이머를 멈추고 남은 op 를 곧바로
// 보낸다(`joinLeaving` 의 `flush`). 보낼 것이 남았거나 ack 가 오지 않은 동안 편집기는 명부에 busy 다 — 탭 줄 붙들기
// (`page_tabs.js` 의 `<tabs-hold>`)가 그 busy 가 걷히고 회차가 끝날 때까지(길어야 `BUSY_MS`) 기다린 뒤 떠난다. 떠나기 신호 뒤로는
// 묶지 않고 곧바로 보내며(`leavingNow`), 보낼 것이 다 걷히면(`settleLeaving`) 다시 묶는다 — 떠나기를 취소하고 머문 편집도 다음
// 묶음부터는 전처럼이다.

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
// 멈추고 남은 op 를 곧바로 보낸다. 돌려준 손잡이(`leaving` · `drop`)는 편집기 상태에 두고, 정리 함수에서 `drop()` 한다.
function joinLeaving(win, hooks) {
  const book = editorBook(win)
  const handle = { leaving: false, id: 0, drop: () => {} }
  const onLeave = () => {
    handle.leaving = true
    try {
      hooks.flush()
    } catch (error) {
      // 보내지 못해도 붙들기는 busy 를 보고 기다린다(상한 `BUSY_MS`).
    }
  }
  handle.id = enrollEditor(book, () => Boolean(hooks.busy()))
  win.addEventListener(LEAVING_EVENT, onLeave)
  handle.drop = () => {
    win.removeEventListener(LEAVING_EVENT, onLeave)
    dropEditor(book, handle.id)
  }
  return handle
}
// </capa-leave-window>
