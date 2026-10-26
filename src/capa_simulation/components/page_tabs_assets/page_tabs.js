// 머리 띠 아래 화면 탭 줄. 파이썬(`components/page_tabs.py`)이 연 탭·지금 탭·점·고정을 data 로 주고, 누름은
// 트리거(`select`·`close`·`pin`) 한 번으로만 돌려준다 — 남는 상태 값은 보내지 않는다(보내면 앱 전체가 다시 돈다).
// 이 함수는 data·테마가 바뀔 때마다 다시 불린다. 뼈대는 처음 한 번 세우고, 다시 불리면 탭 id 로 맞춰 고친다.
// 탭은 `<nav>` 안의 목록과 단추다. 탭 패널이 없는 이동 목록이라 탭 역할(ARIA)을 쓰지 않는다 — 배포 화면 확인
// 스크립트가 그 역할로 본문 탭을 찾는다.
// 탭이 상한이면 사이드바·본문 화면 링크로 열린 탭이 아닌 화면에 가는 누름을 옮기기 전에 막는다 — 이 모듈은 iframe 이
// 아니라 본 문서에서 돌아 문서 capture 단계에서 Streamlit(React 뿌리)보다 먼저 받는다. 서버가 옮긴 뒤 되돌리면 두
// 화면이 브라우저 기록에 쌓여 뒤로가기가 그 화면에 갇힌다(`page_tabs_state.switch_to_queued_tab` 은 마지막 안전망이다).
// 뒤로·앞으로가기는 막지 못한다 — Streamlit 의 `popstate` 처리기가 이 모듈보다 먼저 걸려 먼저 돈다(1.63 브라우저 확인).
// 브라우저 기록은 문서 하나에서 지킨다 — 서버가 주소 인자를 바꿀 때 Streamlit 프런트가 쌓는 칸은 늘 칸 바꾸기다
// (`<tabs-history>`, 탭 줄 누름뿐 아니라 본문 단추·HOME 칸·링크 인자를 받아 지우는 화면 모두). 탭으로 화면을 옮기는
// 누름(다른 탭 고르기·지금 탭 닫기)은 하나를 더 지킨다 — 한 번에 하나. 옮기는 동안 누른 탭은 옮긴 화면의 탭 줄이 올
// 때까지 기다렸다 마지막 것만 보낸다(`<tabs-queue>`). 아래 `// <tabs-…>` 구획은 DOM 을 모르는 순수 함수라 node 시험이
// 떼어 돌린다(`tests/test_page_tabs_assets.py`). 지킴이를 거는 `<tabs-history-install>` 만 창을 만지고, 입장 화면 JS 가
// `<tabs-history>` 와 함께 떼어 싣는다(`components/history_guard.py`).
// 떠나기 확인은 앞 회차 data 의 `leave` 로 정한다. 편집표 칸을 쓰는 중이거나 막 적용(Enter)한 직후에 누르면 그 편집을 실은
// 회차가 아직 돌아오지 않아 `leave` 가 비어 있었다 — 확인 없이 옮기고 편집이 말없이 사라졌다(E2E 결함). 그래서 편집표에서
// 막 손을 뗀 누름은 그 회차가 돌아올 때까지 잠깐 붙들었다가 새 `leave` 로 묻는다(`<tabs-hold>`).
// 닫기·고정은 누르자마자 목록을 움직이므로, 그 뒤 같은 자리로 온 더블클릭의 둘째 누름이 다른 탭에 닿으면 버린다(`<tabs-press>`).
const ICON_FONT = 'Material Symbols Rounded'
const PAGE_LINK = 'a[data-testid="stPageLink-NavLink"]'
const NOTICE_MS = 8000
const BUSY_MS = 10000
// 보낸 이동이 끝났는지 다시 보는 간격 — 옮긴 화면 회차가 다 돌았는지는 Streamlit 뿌리의 회차 표지로 본다.
const SETTLE_POLL_MS = 100
const APP_ROOT = '[data-testid="stApp"]'
// 편집표(glide 격자)와 그 칸 편집기. 편집기는 격자 밖 포털에 뜰 수 있어 그 틀(`gdg-clip-region`)도 본다.
const GRID = '[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"], .gdg-clip-region'
// 편집표에서 손을 뗀 뒤 이만큼 안의 누름은 붙든다(쓰는 중이면 시간과 상관없이 붙든다).
const EDIT_MS = 5000
// 붙든 누름은 적어도 이만큼은 편집 회차를 기다린다 — 편집이 보낸 회차 요청에 서버가 답해 뿌리 표지가 「돈다」로 바뀌기 전.
const HOLD_MS = 400
// 닫기·고정 누름 뒤 같은 자리의 둘째 누름을 더블클릭의 꼬리로 보는 창(`<tabs-press>`) — Windows 기본 더블클릭 시간과
// 손떨림 너비.
const DOUBLE_PRESS_MS = 500
const DOUBLE_PRESS_PX = 8

// <tabs-history>
// 화면 이동 한 번이 브라우저 기록을 한 칸만 쌓게 한다. Streamlit 1.63 프런트는 서버가 주소 인자를 바꿀 때마다
// (`page_info_changed` — `st.query_params` 쓰기·지우기, `st.switch_page` 의 인자 다시 적기) **지금 경로**로 한 칸
// 쌓는다(`pushState`). 그래서 (1) `st.switch_page` 는 떠나는 화면 경로로 한 칸 먼저 쌓고 옮긴 화면을 또 쌓아 뒤로가기
// 한 번이 제자리였고, (2) 링크 인자를 받아 지우는 화면(공정 Capa 상세 `?process=`·Space `?layer=`·제약 시뮬레이션)은
// 인자 달린 칸 뒤에 인자 없는 칸을 또 쌓아, 뒤로가기로 인자 달린 칸에 닿으면 화면이 그 인자를 다시 지우며 또 쌓아 —
// 앞쪽 기록이 잘려 — 그 화면을 떠나지 못했다(E2E 결함). 지금 경로와 같은 경로로 쌓는 것은 늘 그 칸 바꾸기
// (`replaceState`)로 돌린다 — 화면을 옮기는 쌓기(다른 경로)만 칸을 더한다. 처리기는 문서에 하나다(`history` 의
// `pushState` 를 한 번 감싼다).
// `st.switch_page` 의 첫 쌓기는 떠나는 칸 주소를 옮길 화면 인자로 바꾼다(HOME 칸 → `/?process=…&from=home`). 그대로
// 두면 뒤로가기로 돌아온 그 칸이 남의 인자를 달고, 거기서 사이드바로 옮기면 그 인자가 따라가 링크처럼 적용됐다. 그래서
// 인자를 지우지 않은(더하거나 바꾸기만 한) 칸 바꾸기 뒤 `ms` 안에 같은 인자로 다른 경로를 쌓으면 — 그 쌓기가
// `switch_page` 의 옮긴 화면이다 — 떠나는 칸을 원래 주소로 되돌리고 쌓는다. 인자를 지운 칸 바꾸기(링크 인자를 받아
// 지운 화면)는 되돌리지 않는다.
function guardHistory(history, href, clock, ms) {
  const push = history.pushState
  const at = (url) => new URL(String(url), href())
  let covered = null
  history.pushState = function (state, title, url) {
    if (url === undefined || url === null) return push.apply(this, arguments)
    const here = at(href())
    const next = at(url)
    if (next.pathname === here.pathname) {
      const kept = [...here.searchParams.keys()].every((name) => next.searchParams.has(name))
      covered = kept
        ? { url: here.pathname + here.search + here.hash, state: history.state, search: next.search, at: clock() }
        : null
      return history.replaceState(state, title, url)
    }
    const prior = covered
    covered = null
    if (prior !== null && clock() - prior.at < ms && next.search === prior.search) {
      history.replaceState(prior.state, '', prior.url)
    }
    return push.apply(this, arguments)
  }
  return history
}
// </tabs-history>

// <tabs-history-install>
// 기록 지킴이는 문서에 하나다 — 먼저 도는 쪽이 걸고 다른 쪽은 지나간다. 입장 화면 JS(`intro_overlay`)가 모듈을 읽는
// 순간 이 구획을 부른다 — 회차 맨 앞(부트스트랩 전)에 그리는 요소라 링크 인자를 받는 화면이 첫 회차에 인자를 지우기
// 전이다. 탭 줄은 페이지 바로 앞에 그려 그 지우기보다 늦게 마운트돼, 새 브라우저 탭으로 연 링크가 지킴이 없이 기록을 한
// 칸 더 쌓았다(E2E 결함 — 뒤로가기 첫 번이 화면은 그대로 둔 채 주소의 인자만 되살렸다). 탭 줄도 부른다(안전망).
// `st.switch_page` 가 떠나는 칸에 적은 옮길 화면 인자를 되돌리는 기다림 — 그 바로 뒤 옮긴 화면 쌓기가 이 안에 온다.
const LEAVE_MS = 1000
function installHistoryGuard() {
  if (!window.__capaHistoryGuard) {
    window.__capaHistoryGuard = guardHistory(window.history, () => window.location.href, Date.now, LEAVE_MS)
  }
}
// </tabs-history-install>

// <tabs-hold>
// 편집표에서 막 손을 뗀 누름을 붙든다. `editPending` — 누르는 순간 포커스가 편집표(칸 편집기 포함)에 있었거나 마지막 편집표
// 입력에서 `ms` 가 지나지 않았다. `holdVerdict` 는 붙든 누름({at, data})을 'wait'(더 기다린다)·'go'(지금 data 로 묻고
// 보낸다)로 가른다 — 앱 회차가 돌면 기다리고, 돌지 않아도 새 data 가 오지 않았으면 `minMs` 까지는 기다린다(편집 회차
// 요청이 아직 서버에 닿지 않았을 수 있다). `maxMs` 가 지나면 그대로 보낸다.
function editPending(now, editAt, focused, ms) {
  return Boolean(focused) || now - editAt < ms
}
function holdVerdict(hold, now, running, data, minMs, maxMs) {
  const elapsed = now - hold.at
  if (elapsed >= maxMs) return 'go'
  if (running) return 'wait'
  if (elapsed < minMs && data === hold.data) return 'wait'
  return 'go'
}
// </tabs-hold>

// <tabs-queue>
// 옮기는 동안 누른 탭은 보내지 않고 기다린다 — 마지막 누름 하나만. 보낸 고르기는 옮긴 화면의 탭 줄(지금 탭이 바뀐
// data)이 오고 **그 화면 회차가 다 돈 뒤**(`busy` 거짓)에, 아니면 `ms` 가 지나야 끝난다. 그 전에 보낸 누름은 둘 다
// 먹히지 않았다(Streamlit 경합 — 0.1~0.2초 간격 두 누름). 옮기기 전이면 프런트가 아직 떠나는 화면에 있다고 믿고 그
// 화면 주소로 회차를 청했고, 옮긴 화면이 도는 동안이면 그 화면 부품들이 곧이어 보낸 회차 요청과 서버에서 합쳐지며 탭
// 줄 트리거 값이 떨어졌다(1.63 은 합칠 때 단추 트리거만 남기고 컴포넌트 트리거는 새 요청 값으로 덮는다). `press` 는
// 'send'(지금 보낸다)·'wait'(기다린다)·'none'(지금 탭이라 할 일 없음)을 돌려주고, 'send' 면 부르는 쪽이 보내기 전에
// `sent` 를 부른다(떠나기 확인을 취소하면 부르지 않는다). `settle` 은 끝났으면 기다리던 누름의 id(열린 탭이고 지금
// 탭이 아닐 때만)를, 아니면 null 을 돌려준다. 지금 탭 닫기(옮겨 갈 이웃은 서버가 정한다)도 `sent(queue, null, …)` 로
// 같은 기다림을 건다.
function createSelectQueue() {
  return { flight: null, waiting: null }
}
function pressSelect(queue, id, active, now, ms) {
  if (queue.flight !== null && now - queue.flight.at < ms) {
    queue.waiting = id
    return 'wait'
  }
  queue.flight = null
  queue.waiting = null
  return id === active ? 'none' : 'send'
}
function sentSelect(queue, id, active, now) {
  queue.flight = { id, from: active, at: now }
  queue.waiting = null
}
function settleSelect(queue, active, now, ms, ids, busy) {
  const flight = queue.flight
  if (flight === null) return null
  const moved = active !== flight.from && !busy
  if (!moved && now - flight.at < ms) return null
  queue.flight = null
  const next = queue.waiting
  queue.waiting = null
  if (next === null || next === active || !ids.includes(next)) return null
  return next
}
// </tabs-queue>

// <tabs-press>
// 닫기·고정 누름은 곧 목록을 바꾼다 — 닫은 탭은 누르자마자 숨겨 이웃이 그 자리로 당겨 오고, 고정한 탭은 다음 data 에서
// 왼쪽으로 옮긴다. 그래서 × 더블클릭(·0.3초 간격 두 번 누름)의 둘째 누름이 포인터 아래로 밀려 온 이웃 탭에 닿아 그 탭을
// 닫거나 고정했다 — 같은 프레임의 두 'close' 는 마지막 것만 서버에 닿아 누른 탭은 남고 이웃이 닫혔다(E2E 결함).
// `strayPress` 는 앞 닫기·고정 누름(`last` — {id, at, x, y})에서 `ms` 안에 `px` 안의 같은 자리로 온 누름이 **다른 탭**에
// 닿았는가다 — 참이면 그 누름은 버린다. 같은 탭의 둘째 누름(핀 두 번 — 고정했다 푼다)과 자리를 옮긴 누름은 그대로다.
function strayPress(last, id, now, x, y, ms, px) {
  if (last === null || id === last.id || now - last.at >= ms) return false
  return Math.abs(x - last.x) <= px && Math.abs(y - last.y) <= px
}
// </tabs-press>
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
    onLink: null, queue: createSelectQueue(), settleTimer: 0, lastPress: null,
    onEdit: null, editAt: -Infinity, gridFocused: false, pressFromGrid: false, hold: null, holdTimer: 0,
  })
  // 기록 지킴이는 문서에 하나다 — 탭 줄이 다시 마운트돼도 `pushState` 를 두 번 감싸지 않는다. 보통은 입장 화면 JS 가
  // 이미 걸었다(`<tabs-history-install>`). 이것은 그 JS 가 서지 못한 문서의 안전망이다.
  installHistoryGuard()
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
  // 새 data 가 왔으면 누른 뒤 기다리던 표지를 걷는다 — 아직 보내지 않고 기다리는 누름(`<tabs-queue>`·`<tabs-hold>`)의
  // 표지는 둔다.
  for (const [id, item] of S.items) {
    const waiting = id === S.queue.waiting || (S.hold !== null && S.hold.id === id)
    setAttr(item.__parts.tab, 'aria-busy', waiting ? 'true' : null)
  }

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
  const busy = (item) => {
    setAttr(item.__parts.tab, 'aria-busy', 'true')
    clearTimeout(S.busyTimer)
    S.busyTimer = setTimeout(() => setAttr(item.__parts.tab, 'aria-busy', null), BUSY_MS)
  }
  // 화면을 옮기는 누름을 보내기 직전 — 한 번에 하나(`<tabs-queue>`)를 건다. 기록 한 칸은 늘 걸린 지킴이가 맡는다.
  const moving = (id) => {
    sentSelect(S.queue, id, S.data.active, Date.now())
    clearTimeout(S.settleTimer)
    S.settleTimer = setTimeout(() => settle(), SETTLE_POLL_MS)
  }
  const sendSelect = (item) => {
    // 지금 화면에 적용하지 않은 편집표 편집이 있으면 묻는다 — 화면을 떠나면 Streamlit 이 그 편집을 버린다.
    if (!leaveOk()) return
    busy(item)
    moving(item.dataset.id)
    S.send('select', { id: item.dataset.id, epoch: S.data.epoch })
  }
  // 보낸 이동이 끝났으면(옮긴 화면의 data 가 왔고 그 회차가 다 돌았다, 아니면 기다림이 다 됐다) 기다리던 누름을
  // 보낸다. 끝나기 전에는 짧은 간격으로 다시 본다 — 회차가 끝났다는 알림은 컴포넌트에 오지 않는다.
  function settle() {
    clearTimeout(S.settleTimer)
    const open = []
    for (const [id, item] of S.items) if (!item.hidden) open.push(id)
    const root = document.querySelector(APP_ROOT)
    const run = root ? root.getAttribute('data-test-script-state') : null
    const running = run === 'running' || run === 'rerunRequested'
    const next = settleSelect(S.queue, S.data.active, Date.now(), BUSY_MS, open, running)
    if (S.queue.flight !== null) {
      S.settleTimer = setTimeout(() => settle(), SETTLE_POLL_MS)
      return
    }
    const item = next === null ? null : S.items.get(next)
    if (item) sendSelect(item)
  }
  const appRunning = () => {
    const root = document.querySelector(APP_ROOT)
    const run = root ? root.getAttribute('data-test-script-state') : null
    return run === 'running' || run === 'rerunRequested'
  }
  // 떠나는 누름을 편집표 편집 회차가 돌아올 때까지 붙든다(`<tabs-hold>`). 붙든 동안 또 누르면 마지막 누름만 남는다.
  const holding = (item, go) => {
    busy(item)
    S.hold = { id: item.dataset.id, at: Date.now(), data: S.data, go }
    clearTimeout(S.holdTimer)
    S.holdTimer = setTimeout(() => release(), SETTLE_POLL_MS)
  }
  function release() {
    clearTimeout(S.holdTimer)
    const hold = S.hold
    if (!hold) return
    if (holdVerdict(hold, Date.now(), appRunning(), S.data, HOLD_MS, BUSY_MS) === 'wait') {
      S.holdTimer = setTimeout(() => release(), SETTLE_POLL_MS)
      return
    }
    S.hold = null
    // 붙든 표지는 걷는다 — 보내면 `sendSelect` 가 다시 단다(떠나기를 취소하면 표지 없이 남는다).
    const held = S.items.get(hold.id)
    if (held) setAttr(held.__parts.tab, 'aria-busy', null)
    hold.go()
  }
  // 이 누름이 편집표에서 막 손을 뗀 누름이 아닌가 — 아니면 곧바로 묻고 보낸다.
  const fresh = () => {
    const pending = editPending(Date.now(), S.editAt, S.pressFromGrid, EDIT_MS)
    S.pressFromGrid = false
    return !pending
  }
  const select = (item) => {
    const verdict = pressSelect(S.queue, item.dataset.id, S.data.active, Date.now(), BUSY_MS)
    if (verdict === 'wait') busy(item)
    if (verdict !== 'send') return
    if (fresh()) {
      S.hold = null
      sendSelect(item)
      return
    }
    const id = item.dataset.id
    holding(item, () => {
      const target = S.items.get(id)
      if (target && !target.hidden && id !== S.data.active) sendSelect(target)
      else if (target) setAttr(target.__parts.tab, 'aria-busy', null)
    })
  }
  const close = (item) => {
    const id = item.dataset.id
    if (item.__parts.close.hidden) return
    if (id === S.data.active && !fresh()) {
      holding(item, () => {
        const target = S.items.get(id)
        if (target && !target.hidden) closeNow(target)
      })
      return
    }
    S.hold = null
    closeNow(item)
  }
  const closeNow = (item) => {
    const id = item.dataset.id
    if (item.__parts.close.hidden) return
    const leaving = id === S.data.active
    if (leaving && !leaveOk()) return
    // 곧바로 숨긴다 — 다음 회차가 목록에서 뺄 때까지 기다림이 보이지 않게.
    item.hidden = true
    // 지금 탭을 닫으면 서버가 이웃으로 옮긴다 — 그 이동도 기록 한 칸·한 번에 하나다.
    if (leaving) moving(null)
    S.send('close', { id, epoch: S.data.epoch })
  }
  // 2단계(끌어서 떼어 내기·차례 바꾸기)가 포인터 처리를 붙일 자리.
  const startDrag = () => {}
  // 누르는 순간(포커스가 탭으로 옮기기 전) 편집표에 포커스가 있었는지 적는다 — 칸 편집기는 바깥 누름에 편집을 적용하고 닫는다.
  list.onpointerdown = (event) => {
    S.pressFromGrid = S.gridFocused
    startDrag(event)
  }
  // 닫기·고정 누름 뒤 포인터 아래로 밀려 온 다른 탭에 닿은 둘째 누름인가(`<tabs-press>`). 포인터 누름(`detail` > 0)만
  // 본다 — 키보드로 누른 단추는 좌표가 없다.
  const stray = (event, item) =>
    event.detail > 0 &&
    strayPress(S.lastPress, item.dataset.id, Date.now(), event.clientX, event.clientY, DOUBLE_PRESS_MS, DOUBLE_PRESS_PX)
  const pressed = (event, item) => {
    S.lastPress = event.detail > 0
      ? { id: item.dataset.id, at: Date.now(), x: event.clientX, y: event.clientY }
      : null
  }
  list.onclick = (event) => {
    const button = event.target.closest('button')
    const item = button && button.closest('.capa-tabs-item')
    if (!item || !list.contains(item)) return
    const closing = button.classList.contains('capa-tabs-x')
    const pinning = button.classList.contains('capa-tabs-pin')
    if (closing || pinning) event.stopPropagation()
    if (stray(event, item)) return
    if (closing) {
      pressed(event, item)
      close(item)
    } else if (pinning) {
      pressed(event, item)
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
    if (stray(event, item)) return
    pressed(event, item)
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
  if (!S.onEdit) {
    // 편집표에서 손을 뗀 때와 포커스가 편집표에 있는지를 문서 capture 단계에서 적는다(DOM 이 아니라 시각·참거짓만).
    const inGrid = (node) => Boolean(node && node.closest && node.closest(GRID))
    S.onEdit = (event) => {
      if (event.type === 'focusin') S.gridFocused = inGrid(event.target)
      if (inGrid(event.target)) S.editAt = Date.now()
    }
    for (const type of ['focusin', 'keydown', 'paste', 'cut', 'input']) document.addEventListener(type, S.onEdit, true)
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

  // 새 data 가 왔다 — 보낸 이동이 끝났는지 본다(지금 탭이 바뀐 data 와 그 회차의 끝이 표지다).
  if (S.queue.flight !== null) settle()
  // 붙든 누름이 있으면 새 data 로 다시 본다.
  if (S.hold) release()

  return () => {
    clearTimeout(S.noticeTimer)
    clearTimeout(S.busyTimer)
    clearTimeout(S.settleTimer)
    clearTimeout(S.holdTimer)
    if (S.onEdit) {
      for (const type of ['focusin', 'keydown', 'paste', 'cut', 'input']) document.removeEventListener(type, S.onEdit, true)
    }
    S.onEdit = null
    if (S.onFonts && document.fonts && document.fonts.removeEventListener) {
      document.fonts.removeEventListener('loadingdone', S.onFonts)
    }
    S.onFonts = null
    if (S.onLink) document.removeEventListener('click', S.onLink, true)
    S.onLink = null
  }
}
