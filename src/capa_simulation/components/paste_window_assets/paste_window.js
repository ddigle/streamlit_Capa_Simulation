// 붙여넣기 · 양식 창의 크기 조절과 「적용」 잠금 — 팝업(`st.dialog`) 안 숨은 컴포넌트가 그 창을 맡는다.
//
// 크기: 창 오른쪽 아래 손잡이(변 둘 포함)를 끌면 창 폭과 글 칸 높이가 따라 바뀌고, 창 높이는 글 칸을 따라간다.
// 값은 `<html>` 의 CSS 변수(`--capa-paste-w` · `--capa-paste-text-h`)와 속성(`data-capa-paste-sized`)에만 쓰고,
// 그 변수를 읽는 규칙은 이 컴포넌트의 서식에 있어 창이 닫히면 함께 사라진다. 서버로 보내지 않는다 — 회차가 다시
// 돌아도 `<html>` 은 그대로이고, 그 브라우저의 `localStorage`(읽기 · 쓰기 모두 try/catch)가 다음 창을 연 때의 값이다.
// 손잡이를 두 번 누르면 기본 크기로 돌아간다. 손잡이에 초점을 두면 방향키로도 줄이고 늘린다.
//
// 잠금: 글 칸이 비었거나 전체 교체 확인 체크가 꺼져 있으면 「적용」 을 잠그고 까닭 풍선을 단다. 판정이 브라우저
// 안에서 끝나는 잠금이다 — 서버는 눌린 회차에 같은 조건을 다시 보아 알림창으로 거절한다(자바스크립트가 못 돌아도
// 쓰이지 않는다). 꺼진 단추는 Tab 이 건너뛰므로 잠긴 동안은 감싼 칸이 탭 자리를 맡아 키보드로도 풍선이 뜬다(설계 규칙
// UI-INP-07).

// <paste-window-core>
const MIN_WIDTH = 360
const MIN_TEXT = 100
const VIEWPORT_GUTTER = 32
// 글 칸 밖 높이의 기본값 — 글 칸이 아직 없어 잴 수 없을 때만 쓴다. 실제 값은 창 폭(작업 줄이 제목 아래로 접히는지)과
// 칸 구성(확인 체크)에 따라 달라 잰다(`install` 의 `outsideText`).
const WINDOW_CHROME = 230
// 글 칸 · 입력 칸 아래 창 여백과 창 · 화면 사이 틈.
const FORM_BOTTOM_GAP = 32
const KEY_STEP = 40
// 잠금 까닭 풍선 — 창 오른쪽 끝과 남기는 틈과, 자리가 아주 좁아도 읽을 수 있게 남기는 폭.
const TIP_GUTTER = 8
const MIN_TIP_ROOM = 96

// 글 칸의 끝은 창의 글 칸 · 입력 칸이 화면 안에 들 만큼이다(`chrome` — 화면 위 끝부터 그 칸들 아래까지 글 칸 밖 높이).
function clampSize(size, viewport, chrome = WINDOW_CHROME) {
  const maxWidth = Math.max(MIN_WIDTH, viewport.width - VIEWPORT_GUTTER)
  const maxText = Math.max(MIN_TEXT, viewport.height - chrome)
  const within = (value, low, high) => Math.min(high, Math.max(low, value))
  return {
    width: Math.round(within(size.width, Math.min(MIN_WIDTH, maxWidth), maxWidth)),
    text: Math.round(within(size.text, MIN_TEXT, maxText)),
  }
}

function parseSize(raw) {
  try {
    const value = JSON.parse(raw)
    if (value && Number.isFinite(value.width) && Number.isFinite(value.text)) {
      return { width: value.width, text: value.text }
    }
  } catch (error) {
    return null
  }
  return null
}

// 창은 가운데 놓여 양쪽으로 넓어지므로 손 이동의 두 배가 폭이다. 위는 그대로라 글 칸은 손 이동만큼이다.
function dragSize(start, delta, axes) {
  return {
    width: axes.x ? start.width + 2 * delta.x : start.width,
    text: axes.y ? start.text + delta.y : start.text,
  }
}

function lockReason(text, confirmed, reasons) {
  if (!String(text ?? '').trim()) return reasons.empty || ''
  if (!confirmed) return reasons.confirm || ''
  return ''
}

// 잠금 까닭 풍선이 쓸 폭 — 단추 왼쪽 끝에서 창 오른쪽 끝까지. 창 상자가 넘치는 것을 자르므로 이 폭에서 접는다.
function tipRoom(windowRight, buttonLeft) {
  return Math.max(MIN_TIP_ROOM, Math.floor(windowRight - buttonLeft - TIP_GUTTER))
}
// </paste-window-core>

const TEXT_SELECTOR = '[class*="st-key-capa_paste_text_"]'
const TEXT_BOX_SELECTOR = TEXT_SELECTOR + ' [data-testid="stTextArea"]'
const APPLY_SELECTOR = '[class*="st-key-capa_paste_apply_"]'
const HEAD_ROW_SELECTOR = '[class*="st-key-capa_paste_head_"]'
const CONFIRM_BOX_SELECTOR = '[class*="st-key-capa_paste_confirm_"]'
const CONFIRM_SELECTOR = CONFIRM_BOX_SELECTOR + ' input[type="checkbox"]'
const LOCK_ATTRIBUTE = 'data-capa-paste-locked'
const TIP_ROOM_VARIABLE = '--capa-paste-tip-room'

function install(host, data) {
  const doc = host.ownerDocument || document
  const win = doc.defaultView || window
  const dialog = host.closest('[role="dialog"]')
  if (!dialog) return null
  const box = dialog.parentElement
  const root = doc.documentElement
  const storageKey = data.storagePrefix + data.sizeKey

  const viewport = () => ({ width: win.innerWidth, height: win.innerHeight })
  const textBox = () => dialog.querySelector(TEXT_BOX_SELECTOR)
  const measured = () => {
    const text = textBox()
    return {
      width: box.getBoundingClientRect().width,
      text: text ? text.getBoundingClientRect().height : MIN_TEXT,
    }
  }
  // 화면 위 끝(창이 스크롤된 만큼 되돌린 자리)부터 글 칸 · 입력 칸 아래까지 글 칸 밖 높이. 미리보기처럼 그 아래 구획은 넣지
  // 않는다 — 넣으면 값이 큰 창의 글 칸을 늘릴 수 없다(그 구획은 창 스크롤로 간다). 표 상자 안 칸(작업 줄이 제목 줄에 없는
  // 창)은 창이 어차피 화면보다 길고 글 칸이 아래쪽에 있어 재면 글 칸을 거의 못 늘린다 — 기본값이다.
  const outsideText = () => {
    const text = textBox()
    if (!text || !dialog.querySelector(HEAD_ROW_SELECTOR)) return WINDOW_CHROME
    const scroller = box.closest('[data-testid="stDialog"]')
    const textRect = text.getBoundingClientRect()
    const last = dialog.querySelector(CONFIRM_BOX_SELECTOR)
    const formBottom = last ? last.getBoundingClientRect().bottom : textRect.bottom
    return Math.ceil(formBottom + (scroller ? scroller.scrollTop : 0) - textRect.height + FORM_BOTTOM_GAP)
  }
  let wanted = null
  const paint = (size) => {
    wanted = size
    // 크기 서식이 걸리는 순간 글 칸 높이가 있어야 한다 — 없으면 재는 사이 글 칸이 접혀 창 스크롤이 튄다.
    if (!root.hasAttribute('data-capa-paste-sized')) {
      root.style.setProperty('--capa-paste-text-h', measured().text + 'px')
      root.setAttribute('data-capa-paste-sized', '')
    }
    // 폭을 먼저 입힌다 — 폭에 따라 작업 줄이 접혀 글 칸 밖 높이가 달라진다.
    root.style.setProperty('--capa-paste-w', clampSize(size, viewport()).width + 'px')
    const fitted = clampSize(size, viewport(), outsideText())
    root.style.setProperty('--capa-paste-text-h', fitted.text + 'px')
    return fitted
  }
  const unpaint = () => {
    wanted = null
    root.style.removeProperty('--capa-paste-w')
    root.style.removeProperty('--capa-paste-text-h')
    root.removeAttribute('data-capa-paste-sized')
  }
  const load = () => {
    try {
      return parseSize(win.localStorage.getItem(storageKey))
    } catch (error) {
      return null
    }
  }
  const save = (size) => {
    try {
      if (size) win.localStorage.setItem(storageKey, JSON.stringify(size))
      else win.localStorage.removeItem(storageKey)
    } catch (error) { /* 저장을 못 하면 이 창에서만 유지한다 */ }
  }

  const makeHandle = (name, axes) => {
    const handle = doc.createElement('div')
    handle.className = 'capa-paste-handle capa-paste-handle-' + name
    handle.setAttribute('data-capa-paste-handle', name)
    let drag = null
    handle.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return
      event.preventDefault()
      handle.setPointerCapture(event.pointerId)
      drag = { x: event.clientX, y: event.clientY, start: measured(), size: null }
      root.setAttribute('data-capa-paste-dragging', '')
    })
    handle.addEventListener('pointermove', (event) => {
      if (!drag) return
      const delta = { x: event.clientX - drag.x, y: event.clientY - drag.y }
      drag.size = paint(dragSize(drag.start, delta, axes))
    })
    const finish = (event) => {
      if (!drag) return
      if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId)
      if (drag.size) save(drag.size)
      drag = null
      root.removeAttribute('data-capa-paste-dragging')
      judge()
    }
    handle.addEventListener('pointerup', finish)
    handle.addEventListener('pointercancel', finish)
    handle.addEventListener('dblclick', () => {
      save(null)
      unpaint()
    })
    return handle
  }
  const handles = []
  if (data.resizable) {
    const remembered = load()
    if (remembered) paint(remembered)
    else unpaint()
    handles.push(
      makeHandle('right', { x: true, y: false }),
      makeHandle('bottom', { x: false, y: true }),
      makeHandle('corner', { x: true, y: true }),
    )
    const corner = handles[2]
    corner.tabIndex = 0
    corner.setAttribute('role', 'button')
    corner.setAttribute('aria-label', data.handleLabel)
    corner.title = data.handleLabel
    corner.addEventListener('keydown', (event) => {
      const steps = {
        ArrowRight: { x: KEY_STEP, y: 0 },
        ArrowLeft: { x: -KEY_STEP, y: 0 },
        ArrowDown: { x: 0, y: KEY_STEP },
        ArrowUp: { x: 0, y: -KEY_STEP },
      }
      const step = steps[event.key]
      if (!step) return
      event.preventDefault()
      const start = measured()
      save(paint({ width: start.width + step.x, text: start.text + step.y }))
      judge()
    })
    handles.forEach((handle) => dialog.appendChild(handle))
  }

  // 알림 칸은 앱 회차가 끝날 때 문서의 표지를 훑는데, 막 뜨는 팝업의 본문은 그때 아직 문서에 없을 수
  // 있다 — 표지가 팝업에 든 순간 한 번 더 훑게 한다(같은 id 는 한 번만 뜬다).
  let lastMarkers = ''
  const passMarkers = () => {
    const found = [...dialog.querySelectorAll('[' + data.marker + ']')]
      .map((node) => node.getAttribute(data.marker))
      .join('|')
    if (!found || found === lastMarkers) return
    lastMarkers = found
    const center = win.__capaAlerts
    if (center && typeof center.scan === 'function') center.scan()
  }

  const unlock = (holder) => {
    holder.removeAttribute(LOCK_ATTRIBUTE)
    holder.removeAttribute('tabindex')
    holder.removeAttribute('aria-label')
  }

  const judge = () => {
    if (!data.lock) return
    const area = dialog.querySelector(TEXT_SELECTOR + ' textarea')
    const holder = dialog.querySelector(APPLY_SELECTOR)
    const button = holder && holder.querySelector('button')
    if (!area || !button) return
    const tick = dialog.querySelector(CONFIRM_SELECTOR)
    const why = lockReason(area.value, tick ? tick.checked : true, data.reasons)
    if (button.disabled !== Boolean(why)) button.disabled = Boolean(why)
    if (why) {
      holder.setAttribute(LOCK_ATTRIBUTE, why)
      holder.setAttribute('tabindex', '0')
      holder.setAttribute('aria-label', why)
      const room = tipRoom(box.getBoundingClientRect().right, holder.getBoundingClientRect().left)
      holder.style.setProperty(TIP_ROOM_VARIABLE, room + 'px')
    } else unlock(holder)
  }
  dialog.addEventListener('input', judge, true)
  dialog.addEventListener('change', judge, true)
  win.addEventListener('resize', judge)
  const watch = () => {
    // 창을 여는 동안 칸이 하나씩 서므로 기억한 크기를 다시 맞춘다 — 글 칸 밖 높이가 그때 정해진다.
    if (wanted) paint(wanted)
    judge()
    passMarkers()
  }
  const observer = new win.MutationObserver(watch)
  observer.observe(dialog, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['disabled'],
  })
  watch()

  return () => {
    observer.disconnect()
    dialog.removeEventListener('input', judge, true)
    dialog.removeEventListener('change', judge, true)
    win.removeEventListener('resize', judge)
    handles.forEach((handle) => handle.remove())
    const holder = dialog.querySelector(APPLY_SELECTOR)
    if (holder) unlock(holder)
    root.removeAttribute('data-capa-paste-dragging')
    unpaint()
  }
}

export default function (component) {
  const { data, parentElement } = component
  const host = parentElement.querySelector('.capa-paste-host')
  if (!host) return undefined
  if (!host.__capaPasteDispose) {
    const dispose = install(host, data)
    if (!dispose) return undefined
    host.__capaPasteDispose = dispose
  }
  return () => {
    if (host.__capaPasteDispose) host.__capaPasteDispose()
    delete host.__capaPasteDispose
  }
}
