// 설비 마스터 오른쪽 칸 칸막이 — 오른쪽 칸 왼쪽 끝을 끌어 폭을 바꾸고 ‹ › 로 접고 편다.
// 상태는 브라우저에만 둔다(브라우저 저장소 + <html> 의 CSS 변수·속성) — 파이썬으로 보내지 않는다(AGENTS 9장 「브라우저 전용
// 보기 상태」). 폭의 한계는 페이지 CSS 의 clamp 가 지키고, 여기 `clampWidth` 는 같은 식으로 저장값·aria 값을 낸다.
const STORE = 'capa-equipment-side-v1'
const VAR_W = '--emd-side-w'
const VAR_TOP = '--emd-top'
const VAR_GAP = '--emd-gap'
const ATTR = 'data-emd-side'
// 화면 탭 줄이 없을 때 가리는 머리 띠 높이(설비 마스터 표 `TOAST_REVEAL_MARGIN` 과 같다)와 그 아래 틈.
const HEADER_COVER = 72
const COVER_GAP = 8
// 저장값으로 받는 폭의 바깥 한계 — 망가진 값만 거른다(실제 한계는 CSS clamp).
const STORED_LIMIT = 4000

// <splitter-clamp>
// 폭 한계 — 페이지 CSS `clamp(min(최소px, 최소몫), 폭, min(최대px, 최대몫))` 과 같은 식(몫은 두 칸 줄 폭의 비율).
// `bounds` = {minPx, minShare, maxPx, maxShare, defaultShare, defaultOffset}(파이썬 data).
function sideBounds(rowWidth, bounds) {
  const row = Math.max(0, Number(rowWidth) || 0)
  return {
    lo: Math.min(bounds.minPx, row * bounds.minShare),
    hi: Math.min(bounds.maxPx, row * bounds.maxShare),
  }
}
function clampWidth(px, rowWidth, bounds) {
  const { lo, hi } = sideBounds(rowWidth, bounds)
  const width = Number(px)
  const value = Number.isFinite(width) ? width : defaultWidth(rowWidth, bounds)
  return Math.round(Math.max(lo, Math.min(hi, value)))
}
// 처음 폭 — CSS `calc(몫% - 덜기px)`(옛 7:3 두 칸의 오른쪽 폭).
function defaultWidth(rowWidth, bounds) {
  const row = Math.max(0, Number(rowWidth) || 0)
  const { lo, hi } = sideBounds(row, bounds)
  return Math.round(Math.max(lo, Math.min(hi, row * bounds.defaultShare - bounds.defaultOffset)))
}
// 저장값 읽기 — 꼴이 다르면 처음 상태. 폭은 유한한 수(0 초과 상한 이하)만, 접힘은 참일 때만.
function storedState(raw, limit) {
  let value = null
  try {
    value = JSON.parse(raw || 'null')
  } catch (error) {
    value = null
  }
  if (!value || typeof value !== 'object') return { w: null, min: false }
  const w = typeof value.w === 'number' && Number.isFinite(value.w) && value.w > 0 && value.w <= limit ? value.w : null
  return { w, min: value.min === true }
}
// </splitter-clamp>

// <splitter-drag>
// 끌기 — 칸막이는 오른쪽 칸의 왼쪽 끝이라 왼쪽으로 끌수록 넓어진다. 시작 폭·시작 x 에서 지금 x 까지 움직인 만큼.
function widthFromPointer(startW, startX, x) {
  return Number(startW) + (Number(startX) - Number(x))
}
// </splitter-drag>

// <splitter-keys>
// 칸막이 키 — ← 넓힘 · → 좁힘(한 걸음 16px, Shift 64px), Home 최대 · End 최소, Enter 접기. 그 밖의 키는 null(놓아 둔다).
const KEY_STEP = 16
const KEY_STEP_WIDE = 64
function keyAction(key, shift, now, lo, hi) {
  const step = shift ? KEY_STEP_WIDE : KEY_STEP
  if (key === 'ArrowLeft') return { width: now + step }
  if (key === 'ArrowRight') return { width: now - step }
  if (key === 'Home') return { width: hi }
  if (key === 'End') return { width: lo }
  if (key === 'Enter') return { fold: true }
  return null
}
// </splitter-keys>

// 저장소를 막은 브라우저(사내 DRM 등) — 읽기·쓰기가 한 번이라도 막히면 `<html>` 에 이 표를 단다. 그 뒤 마운트(안쪽 탭·
// 화면을 옮겨 다시 그린 칸막이)는 저장값 대신 `<html>` 에 걸린 이 문서의 폭·접힘을 그대로 둔다 — 새로 읽어야 처음 상태다.
const LOCAL_ONLY = '__essLocalOnly'

// 저장값 — 저장소를 못 쓰면 null(문서 상태를 그대로 둔다).
function readStore() {
  if (document.documentElement[LOCAL_ONLY]) return null
  try {
    return storedState(window.localStorage.getItem(STORE), STORED_LIMIT)
  } catch (error) {
    document.documentElement[LOCAL_ONLY] = true
    return null
  }
}
function writeStore(patch) {
  const prev = readStore()
  if (!prev) return
  try {
    window.localStorage.setItem(STORE, JSON.stringify({ ...prev, ...patch }))
  } catch (error) {
    document.documentElement[LOCAL_ONLY] = true
  }
}

function el(tag, cls, text) {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text != null) node.textContent = text
  return node
}

function listen(S, target, type, handler, options) {
  target.addEventListener(type, handler, options)
  S.listeners.push([target, type, handler, options])
}

function keyClass(name) {
  return typeof name === 'string' && /^[\w-]+$/.test(name) ? '.st-key-' + name : null
}

// 그림자 DOM 밖의 자리 — 두 칸 줄·오른쪽 칸 감싸개(flex 항목)·그 앞 형제(왼쪽 칸 감싸개)·오른쪽 칸 본문 칸(스크롤 칸).
function anchors(host, keys) {
  const root = host.getRootNode ? host.getRootNode() : null
  const outer = root && root.host ? root.host : host
  const rowSel = keyClass(keys.row)
  const rightSel = keyClass(keys.right)
  const bodySel = keyClass(keys.body)
  const row = rowSel && outer.closest ? outer.closest(rowSel) : null
  const right = rightSel && outer.closest ? outer.closest(rightSel) : null
  const column = right ? right.parentElement : null
  const body = right && bodySel && right.querySelector ? right.querySelector(bodySel) : null
  return { row, column, body }
}

function rowWidth(S) {
  return S.row ? S.row.getBoundingClientRect().width : 0
}
function columnWidth(S) {
  return S.column ? S.column.getBoundingClientRect().width : 0
}
function minimized() {
  return document.documentElement.getAttribute(ATTR) === 'min'
}

// 붙는 높이 — 화면 탭 줄 아래 끝(본문 스크롤 칸 위 끝 기준) + 8px, 탭 줄이 없으면 머리 띠 72px + 8px. 탭 줄이 붙는
// 칸(sticky)이면 붙었을 때의 아래 끝(그 `top` + 높이)을 쓴다 — 잰 때의 스크롤과 상관없이 같다(맨 위에서는 탭 줄이 3px
// 아래에 있어 지금 자리로 재면 내린 뒤 오른쪽 칸이 탭 줄과 11px 떨어졌다).
function coverTop(selector) {
  const strip = selector ? document.querySelector(selector) : null
  const main = document.querySelector('[data-testid="stMain"]')
  const top = main ? main.getBoundingClientRect().top : 0
  let bottom = 0
  if (strip) {
    const rect = strip.getBoundingClientRect()
    bottom = rect.bottom - top
    const style = typeof window.getComputedStyle === 'function' ? window.getComputedStyle(strip) : null
    const stuck = style && style.position === 'sticky' ? parseFloat(style.top) : NaN
    if (Number.isFinite(stuck)) bottom = stuck + rect.height
  }
  return Math.round(Math.max(HEADER_COVER, bottom)) + COVER_GAP
}

function measure(S) {
  const doc = document.documentElement
  doc.style.setProperty(VAR_TOP, coverTop(S.cover) + 'px')
  const prev = S.column && S.column.previousElementSibling
  if (prev && !minimized()) {
    const gap = Math.max(0, S.column.getBoundingClientRect().left - prev.getBoundingClientRect().right)
    doc.style.setProperty(VAR_GAP, Math.round(gap) + 'px')
  }
}

function paint(S) {
  const folded = minimized()
  S.host.classList.toggle('is-min', folded)
  const { lo, hi } = sideBounds(rowWidth(S), S.bounds)
  S.gutter.setAttribute('aria-valuemin', String(Math.round(lo)))
  S.gutter.setAttribute('aria-valuemax', String(Math.round(hi)))
  S.gutter.setAttribute('aria-valuenow', String(Math.round(columnWidth(S))))
  S.railLabel.textContent = S.label
  S.rail.setAttribute('aria-label', '오른쪽 칸 펼치기 — ' + S.label)
}

function setWidth(S, px) {
  const width = clampWidth(px, rowWidth(S), S.bounds)
  document.documentElement.style.setProperty(VAR_W, width + 'px')
  return width
}

function setFolded(S, folded, focus) {
  const doc = document.documentElement
  if (folded) doc.setAttribute(ATTR, 'min')
  else doc.removeAttribute(ATTR)
  writeStore({ min: folded })
  paint(S)
  if (!folded) measure(S)
  if (focus) (folded ? S.rail : S.toggle).focus()
}

function build(S, host) {
  host.textContent = ''
  const gutter = el('div', 'ess-gutter')
  gutter.setAttribute('role', 'separator')
  gutter.setAttribute('aria-orientation', 'vertical')
  gutter.setAttribute('aria-label', '오른쪽 칸 폭 — 끌거나 ←·→ 로 바꿉니다. 두 번 누르면 처음 폭, Enter 는 접기')
  gutter.title = '끌어 오른쪽 칸 폭 바꾸기 · 두 번 누르면 처음 폭'
  gutter.tabIndex = 0
  gutter.appendChild(el('span', 'ess-line'))
  const toggle = el('button', 'ess-toggle', '›')
  toggle.type = 'button'
  toggle.title = '오른쪽 칸 접기'
  toggle.setAttribute('aria-label', '오른쪽 칸 접기')
  toggle.setAttribute('aria-expanded', 'true')
  const rail = el('button', 'ess-rail')
  rail.type = 'button'
  rail.title = '오른쪽 칸 펼치기'
  rail.setAttribute('aria-expanded', 'false')
  rail.appendChild(el('span', 'ess-chev', '‹'))
  const railLabel = el('span', 'ess-rail-label')
  rail.appendChild(railLabel)
  host.appendChild(gutter)
  host.appendChild(toggle)
  host.appendChild(rail)
  S.gutter = gutter
  S.toggle = toggle
  S.rail = rail
  S.railLabel = railLabel

  // 처리한 키는 문서로 올리지 않는다 — Streamlit 단축키(r 다시 실행 등)가 먹지 않게.
  listen(S, toggle, 'click', () => setFolded(S, true, true))
  listen(S, rail, 'click', () => setFolded(S, false, true))
  listen(S, gutter, 'pointerdown', (event) => {
    if (event.button !== 0 || !S.row || !S.column) return
    // 끄는 동안 글자를 고르지 않는다.
    event.preventDefault()
    if (gutter.setPointerCapture) gutter.setPointerCapture(event.pointerId)
    S.drag = { startW: columnWidth(S), startX: event.clientX, x: event.clientX, w: null }
    host.classList.add('is-drag')
    document.documentElement.style.cursor = 'col-resize'
  })
  listen(S, gutter, 'pointermove', (event) => {
    if (!S.drag) return
    S.drag.x = event.clientX
    if (S.frame) return
    // 한 프레임에 한 번만 폭을 바꾼다(다시 흐르기는 브라우저 몫 — 회차 없음).
    S.frame = window.requestAnimationFrame(() => {
      S.frame = 0
      if (!S.drag) return
      S.drag.w = setWidth(S, widthFromPointer(S.drag.startW, S.drag.startX, S.drag.x))
    })
  })
  const end = () => {
    if (!S.drag) return
    if (S.drag.w !== null) writeStore({ w: S.drag.w })
    S.drag = null
    host.classList.remove('is-drag')
    document.documentElement.style.cursor = ''
    measure(S)
    paint(S)
  }
  listen(S, gutter, 'pointerup', end)
  listen(S, gutter, 'pointercancel', end)
  listen(S, gutter, 'lostpointercapture', end)
  listen(S, gutter, 'dblclick', () => {
    document.documentElement.style.removeProperty(VAR_W)
    writeStore({ w: null })
    paint(S)
  })
  listen(S, gutter, 'keydown', (event) => {
    const { lo, hi } = sideBounds(rowWidth(S), S.bounds)
    const action = keyAction(event.key, event.shiftKey, columnWidth(S), lo, hi)
    if (!action) return
    event.preventDefault()
    event.stopPropagation()
    if (action.fold) {
      setFolded(S, true, true)
      return
    }
    writeStore({ w: setWidth(S, action.width) })
    paint(S)
  })
  for (const node of [toggle, rail]) {
    listen(S, node, 'keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') event.stopPropagation()
    })
  }
  listen(S, window, 'resize', () => {
    if (S.resizeFrame) return
    S.resizeFrame = window.requestAnimationFrame(() => {
      S.resizeFrame = 0
      measure(S)
      paint(S)
    })
  })
  S.built = true
}

export default function (component) {
  const { data, parentElement } = component
  const host = parentElement.querySelector('.ess')
  if (!host || !data) return
  const S = host.__ess || (host.__ess = { built: false, listeners: [], frame: 0, resizeFrame: 0, drag: null, reveal: null })
  S.host = host
  const palette = data.palette || {}
  const paletteKey = JSON.stringify(palette)
  if (S.paletteKey !== paletteKey) {
    S.paletteKey = paletteKey
    for (const [name, value] of Object.entries(palette)) host.style.setProperty('--ess-' + name, String(value))
  }
  if (!data.bounds || typeof data.bounds !== 'object') return
  S.bounds = data.bounds
  S.cover = typeof data.cover === 'string' ? data.cover : ''
  S.label = String(data.label || '오른쪽 칸')
  const { row, column, body } = anchors(host, data.keys || {})
  S.row = row
  S.column = column
  const doc = document.documentElement
  if (!S.built) {
    // 처음 마운트 — 저장해 둔 폭·접힘을 문서에 다시 건다(폭 한계는 CSS clamp 가 창 폭에 맞춘다). 저장소를 못 쓰면
    // `<html>` 에 걸린 이 문서의 폭·접힘을 그대로 둔다(`LOCAL_ONLY`).
    const stored = readStore()
    if (stored) {
      if (stored.w !== null) doc.style.setProperty(VAR_W, stored.w + 'px')
      else doc.style.removeProperty(VAR_W)
      if (stored.min) doc.setAttribute(ATTR, 'min')
      else doc.removeAttribute(ATTR)
    }
    build(S, host)
    S.reveal = data.reveal
  } else if (data.reveal !== S.reveal) {
    // 표에서 호기 상세·새 호기를 연 회차 — 접혀 있으면 편다(누른 것이 보이게). 본문 칸은 key 칸이라 회차가 바뀌어도 같은
    // 요소로 남아 스크롤 자리를 잇는다 — 맨 위로 올려 새로 연 호기의 이름 머리(와 토스트)가 보이게 한다.
    S.reveal = data.reveal
    if (minimized()) setFolded(S, false, false)
    if (body) body.scrollTop = 0
  }
  measure(S)
  paint(S)
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    if (S.frame) window.cancelAnimationFrame(S.frame)
    if (S.resizeFrame) window.cancelAnimationFrame(S.resizeFrame)
    for (const [target, type, handler, options] of S.listeners) target.removeEventListener(type, handler, options)
    S.listeners = []
    S.frame = 0
    S.resizeFrame = 0
    S.drag = null
    S.built = false
    document.documentElement.style.cursor = ''
  }
}
