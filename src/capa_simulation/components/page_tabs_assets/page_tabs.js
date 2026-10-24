// 머리 띠 아래 화면 탭 줄. 파이썬(`components/page_tabs.py`)이 연 탭·지금 탭·점·고정을 data 로 주고, 누름은
// 트리거(`select`·`close`·`pin`) 한 번으로만 돌려준다 — 남는 상태 값은 보내지 않는다(보내면 앱 전체가 다시 돈다).
// 이 함수는 data·테마가 바뀔 때마다 다시 불린다. 뼈대는 처음 한 번 세우고, 다시 불리면 탭 id 로 맞춰 고친다.
// 탭은 `<nav>` 안의 목록과 단추다. 탭 패널이 없는 이동 목록이라 탭 역할(ARIA)을 쓰지 않는다 — 배포 화면 확인
// 스크립트가 그 역할로 본문 탭을 찾는다.
// 탭이 상한이면 사이드바·본문 화면 링크로 열린 탭이 아닌 화면에 가는 누름을 옮기기 전에 막는다 — 이 모듈은 iframe 이
// 아니라 본 문서에서 돌아 문서 capture 단계에서 Streamlit(React 뿌리)보다 먼저 받는다. 서버가 옮긴 뒤 되돌리면 두
// 화면이 브라우저 기록에 쌓여 뒤로가기가 그 화면에 갇힌다(`page_tabs_state.switch_to_queued_tab` 은 마지막 안전망이다).
// 뒤로·앞으로가기는 막지 못한다 — Streamlit 의 `popstate` 처리기가 이 모듈보다 먼저 걸려 먼저 돈다(1.63 브라우저 확인).
const ICON_FONT = 'Material Symbols Rounded'
const PAGE_LINK = 'a[data-testid="stPageLink-NavLink"]'
const NOTICE_MS = 8000
const BUSY_MS = 10000
const SVG_NS = 'http://www.w3.org/2000/svg'
const CLOSE_PATH = 'M4 4 L12 12 M12 4 L4 12'
const PIN_PATH = 'M6 2 H10 L9.5 6 L12 8.5 V10 H8.75 V14.5 L8 15 L7.25 14.5 V10 H4 V8.5 L6.5 6 Z'

function icon(path, fillClass) {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 16 16')
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('focusable', 'false')
  const shape = document.createElementNS(SVG_NS, 'path')
  shape.setAttribute('d', path)
  shape.setAttribute('stroke', 'currentColor')
  shape.setAttribute('stroke-width', '1.5')
  shape.setAttribute('stroke-linecap', 'round')
  shape.setAttribute('stroke-linejoin', 'round')
  if (fillClass) shape.setAttribute('class', fillClass)
  else shape.setAttribute('fill', 'none')
  svg.append(shape)
  return svg
}

function fill(template, values) {
  return String(template || '').replace(/\{(\w+)\}/g, (_, name) => (name in values ? String(values[name]) : ''))
}

function setAttr(element, name, value) {
  if (value === null || value === undefined) {
    if (element.hasAttribute(name)) element.removeAttribute(name)
  } else if (element.getAttribute(name) !== value) {
    element.setAttribute(name, value)
  }
}

function setText(element, value) {
  if (element.textContent !== value) element.textContent = value
}

function iconFontLoaded() {
  try {
    for (const face of document.fonts) {
      if (face.family.replace(/["']/g, '') === ICON_FONT && face.status === 'loaded') return true
    }
  } catch (error) {
    return false
  }
  return false
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const nav = parentElement.querySelector('.capa-tabs')
  if (!nav || !data) return
  const list = nav.querySelector('.capa-tabs-list')
  const notice = nav.querySelector('.capa-tabs-notice')
  const S = nav.__capaTabs || (nav.__capaTabs = {
    items: new Map(), noticeId: null, noticeTimer: 0, busyTimer: 0, lastActive: null, onFonts: null,
    onLink: null,
  })
  // 처리기는 처음 한 번 단다. 지금 data·트리거 함수는 S 에서 읽는다 — 다시 불릴 때마다 새 값으로 바뀐다.
  S.data = data
  S.send = setTriggerValue
  const text = data.text || {}

  setAttr(nav, 'aria-label', text.nav || '')
  const pending = (data.palette && data.palette.pending) || ''
  if (pending && nav.style.getPropertyValue('--capa-tabs-pending') !== pending) {
    nav.style.setProperty('--capa-tabs-pending', pending)
  }

  // 사이드바와 같은 Material 아이콘. 글꼴이 아직 없으면 아이콘을 빼고 글만 둔다(글꼴 이름 글자가 보이지 않게).
  nav.classList.toggle('has-icons', iconFontLoaded())
  if (!S.onFonts && document.fonts && document.fonts.addEventListener) {
    S.onFonts = () => nav.classList.toggle('has-icons', iconFontLoaded())
    document.fonts.addEventListener('loadingdone', S.onFonts)
  }

  const build = (id) => {
    const item = document.createElement('li')
    item.className = 'capa-tabs-item'
    item.dataset.id = id
    const tab = document.createElement('button')
    tab.type = 'button'
    tab.className = 'capa-tabs-tab'
    const glyph = document.createElement('span')
    glyph.className = 'capa-tabs-icon'
    glyph.setAttribute('aria-hidden', 'true')
    const label = document.createElement('span')
    label.className = 'capa-tabs-label'
    const dot = document.createElement('span')
    dot.className = 'capa-tabs-dot'
    dot.setAttribute('aria-hidden', 'true')
    const sr = document.createElement('span')
    sr.className = 'capa-tabs-sr'
    tab.append(glyph, label, dot, sr)
    const pin = document.createElement('button')
    pin.type = 'button'
    pin.className = 'capa-tabs-pin'
    pin.append(icon(PIN_PATH, 'capa-tabs-pin-fill'))
    const close = document.createElement('button')
    close.type = 'button'
    close.className = 'capa-tabs-x'
    close.append(icon(CLOSE_PATH, ''))
    item.append(tab, pin, close)
    item.__parts = { tab, glyph, label, dot, sr, pin, close }
    S.items.set(id, item)
    return item
  }

  const paint = (item, tab) => {
    const P = item.__parts
    const label = String(tab.label || '')
    const active = tab.id === data.active
    item.hidden = false
    item.__href = String(tab.href || '')
    setText(P.label, label)
    setText(P.glyph, String(tab.icon || ''))
    setAttr(P.tab, 'title', String(tab.title || label))
    setAttr(P.tab, 'aria-current', active ? 'page' : null)
    item.classList.toggle('is-active', active)
    item.classList.toggle('is-dirty', Boolean(tab.dirty))
    setText(P.sr, tab.dirty ? ' ' + String(text.dirty || '') : '')
    const pinned = Boolean(tab.pinned)
    item.classList.toggle('is-pinned', pinned)
    // 이름은 하나(「… 고정」)이고 고정 여부는 `aria-pressed` 만 말한다 — 이름까지 바꾸면 읽기 도구가 상태를 두 번 읽는다.
    setAttr(P.pin, 'aria-pressed', pinned ? 'true' : 'false')
    setAttr(P.pin, 'aria-label', fill(text.pin, { label }))
    setAttr(P.pin, 'title', fill(text.pin, { label }))
    P.close.hidden = !tab.closable
    setAttr(P.close, 'aria-label', fill(text.close, { label }))
    setAttr(P.close, 'title', fill(text.close, { label }))
  }

  const tabs = Array.isArray(data.tabs) ? data.tabs.filter((tab) => tab && typeof tab.id === 'string') : []
  const keep = new Set(tabs.map((tab) => tab.id))
  for (const [id, item] of S.items) {
    if (!keep.has(id)) {
      item.remove()
      S.items.delete(id)
    }
  }
  tabs.forEach((tab, index) => {
    const item = S.items.get(tab.id) || build(tab.id)
    paint(item, tab)
    const at = list.children[index]
    if (at !== item) list.insertBefore(item, at || null)
  })
  // 새 data 가 왔으면 누른 뒤 기다리던 표지를 걷는다.
  for (const item of S.items.values()) setAttr(item.__parts.tab, 'aria-busy', null)

  // 지금 탭이 늘 보이게 목록의 가로 위치만 맞춘다 — `scrollIntoView` 는 본문 세로 스크롤까지 움직일 수 있다.
  const current = S.items.get(data.active)
  if (current && S.lastActive !== data.active) {
    S.lastActive = data.active
    const left = current.offsetLeft
    const right = left + current.offsetWidth
    if (left < list.scrollLeft) list.scrollLeft = Math.max(0, left - 8)
    else if (right > list.scrollLeft + list.clientWidth) list.scrollLeft = right - list.clientWidth + 8
  }

  const leaveOk = () => !S.data.leave || window.confirm(fill(text.leave, { list: S.data.leave }))
  const select = (item) => {
    const id = item.dataset.id
    if (id === S.data.active) return
    // 지금 화면에 적용하지 않은 편집표 편집이 있으면 묻는다 — 화면을 떠나면 Streamlit 이 그 편집을 버린다.
    if (!leaveOk()) return
    setAttr(item.__parts.tab, 'aria-busy', 'true')
    clearTimeout(S.busyTimer)
    S.busyTimer = setTimeout(() => setAttr(item.__parts.tab, 'aria-busy', null), BUSY_MS)
    S.send('select', { id, epoch: S.data.epoch })
  }
  const close = (item) => {
    const id = item.dataset.id
    if (item.__parts.close.hidden) return
    if (id === S.data.active && !leaveOk()) return
    // 곧바로 숨긴다 — 다음 회차가 목록에서 뺄 때까지 기다림이 보이지 않게.
    item.hidden = true
    S.send('close', { id, epoch: S.data.epoch })
  }
  // 2단계(끌어서 떼어 내기·차례 바꾸기)가 포인터 처리를 붙일 자리.
  const startDrag = () => {}
  list.onpointerdown = startDrag
  list.onclick = (event) => {
    const button = event.target.closest('button')
    const item = button && button.closest('.capa-tabs-item')
    if (!item || !list.contains(item)) return
    if (button.classList.contains('capa-tabs-x')) {
      event.stopPropagation()
      close(item)
    } else if (button.classList.contains('capa-tabs-pin')) {
      event.stopPropagation()
      S.send('pin', { id: item.dataset.id, pinned: !item.classList.contains('is-pinned'), epoch: S.data.epoch })
    } else {
      select(item)
    }
  }
  // 가운데 단추 누름도 닫는다(브라우저 탭과 같다). 누르는 순간의 자동 스크롤은 막는다.
  list.onmousedown = (event) => {
    if (event.button === 1) event.preventDefault()
  }
  list.onauxclick = (event) => {
    if (event.button !== 1) return
    const item = event.target.closest('.capa-tabs-item')
    if (!item || !list.contains(item)) return
    event.preventDefault()
    close(item)
  }

  const flash = (message) => {
    setText(notice, String(message || ''))
    notice.hidden = false
    clearTimeout(S.noticeTimer)
    S.noticeTimer = setTimeout(() => { notice.hidden = true }, NOTICE_MS)
  }
  // 서버가 남긴 상한 알림은 새 일련번호가 올 때 한 번 띄우고 잠시 뒤 걷는다.
  const message = data.notice
  if (message && typeof message.id === 'number' && message.id !== S.noticeId) {
    S.noticeId = message.id
    flash(message.text)
  }

  // 탭 상한에 걸리는 주소(`url_path`, HOME 은 빈 글자)인가 — 아는 화면이고, 열린 탭(닫는 중이라 숨긴 탭은 뺀다)에
  // 없고, 열린 탭이 이미 상한이다. 걸리면 알림 글을, 아니면 빈 글자를 돌려준다.
  const refusal = (href) => {
    const D = S.data
    const pages = (D && D.pages) || {}
    if (!Object.prototype.hasOwnProperty.call(pages, href)) return ''
    let open = 0
    for (const item of S.items.values()) {
      if (item.hidden) continue
      if (item.__href === href) return ''
      open += 1
    }
    if (open < Number(D.max)) return ''
    // 글 틀은 파이썬 상수(`TEXT`)라 처리기를 단 회차의 것을 그대로 쓴다.
    return fill(text.limit, { max: D.max, label: pages[href] })
  }
  if (!S.onLink) {
    // 왼쪽 단추 누름만 본다 — Streamlit 은 보조 키를 눌러도 같은 창에서 옮긴다. 가운데 단추(새 브라우저 탭)는
    // 새 접속이라 막지 않는다. 새 창으로 여는 바깥 링크도 그대로다.
    S.onLink = (event) => {
      if (event.defaultPrevented || event.button !== 0) return
      const link = event.target && event.target.closest ? event.target.closest(PAGE_LINK) : null
      if (!link || link.target === '_blank') return
      const why = refusal((link.getAttribute('href') || '').split(/[?#]/)[0])
      if (!why) return
      event.preventDefault()
      event.stopPropagation()
      flash(why)
    }
    document.addEventListener('click', S.onLink, true)
  }

  return () => {
    clearTimeout(S.noticeTimer)
    clearTimeout(S.busyTimer)
    if (S.onFonts && document.fonts && document.fonts.removeEventListener) {
      document.fonts.removeEventListener('loadingdone', S.onFonts)
    }
    S.onFonts = null
    if (S.onLink) document.removeEventListener('click', S.onLink, true)
    S.onLink = null
  }
}
