// 범용 편집 그리드 — 마운트·모델·그리기·칸 편집·키 나눔·출납 보내기·feed 받기(CORE). 등록 JS 의 끝 조각이다.
// 껍데기(이 요소의 data — 표 본문·글·팔레트)는 표가 같으면 회차마다 같아 해시 참조로 오고, 초안·오류·ack 는 작은 요소
// `capa_edit_grid_feed` 가 window.__capaEditGrid[host].feed 칸과 'capa-edit-grid' 이벤트로 넘긴다 — 차례에 기대지 않는다(feed 의
// baseKey 가 껍데기와 다르면 칸에 둔 채 껍데기가 오면 그때 쓴다). 편집은 상태 값 outbox 하나다(트리거 없음 — 반영 안 된 op 전부를
// {mount, ops} 로). 사용자 글은 textContent 로만 넣는다. 기능 파일(select·fill·toolbar)은 FEATURES 갈고리로 붙고, 아래 이름의
// 함수를 부른다(내부 API — 이름을 바꾸지 않는다): paint · scrollToCell · setRange · displayText · rawText · valueAt · isLocked ·
// rowKeys · colNames · queueOp · sendNow · sendOnce · startEdit · commitEdit · cancelEdit · setStatus · announce · toast ·
// focusGrid · cellAtPoint · visibleRowCount · setWidths.

const EG_SEND_MS = 300
const EG_BUFFER_ROWS = 8
const EG_TIP_MS = 300
const EG_TOAST_MS = 5000
const EG_STATUS_MS = 4000
const EG_MIN_HEIGHT = 360
const EG_BOTTOM_GAP = 24
const EG_KEY_WIDTH = 104
const EG_VALUE_WIDTH = 80
const EG_FROZEN_RATIO = 0.45
const EG_FEED_EVENT = 'capa-edit-grid'
const EG_HOST_KEY = /^[\w-]+$/
const EG_MOVES = { down: [1, 0], up: [-1, 0], right: [0, 1], left: [0, -1] }
// 표마다 보기 상태(스크롤·정렬·지금 칸) — 모듈 공용. 표를 바꿨다 돌아오면 그 자리로 간다.
const EG_VIEWS = new Map()

function egEl(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined && text !== null) node.textContent = String(text)
  return node
}

function egState(host) {
  const S = {
    host, mount: 'g-' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4),
    hostKey: '', shell: null, feedData: null, model: null, gen: '', texts: {}, limits: {},
    view: { order: new Int32Array(0), rank: new Int32Array(0), filtered: false, sort: null, filterKey: 'null' },
    anchor: { r: 0, c: 0 }, focus: { r: 0, c: 0 }, edit: null, full: false, committing: false,
    box: createBox(), pending: new Map(), pendingBySeq: new Map(),
    widths: [], lefts: [], total: 0, frozen: 1, frozenWidth: 0, widthsTable: null,
    rowH: 30, headH: 32, dom: null, listeners: [], timers: {}, frames: {}, observer: null,
    lastToast: null, seenFeed: false, setState: null, inRender: false, sendQueued: false, window: null, paletteKey: '',
  }
  S.range = () => egRange(S.anchor, S.focus)
  return S
}

function egRange(a, b) {
  return { r0: Math.min(a.r, b.r), r1: Math.max(a.r, b.r), c0: Math.min(a.c, b.c), c1: Math.max(a.c, b.c) }
}

function egListen(S, target, type, handler, options) {
  target.addEventListener(type, handler, options)
  S.listeners.push([target, type, handler, options])
}

function egTimer(S, name, ms, run) {
  if (S.timers[name]) clearTimeout(S.timers[name])
  S.timers[name] = setTimeout(() => {
    S.timers[name] = 0
    run()
  }, ms)
}

function egFrame(S, name, run) {
  if (S.frames[name]) return
  S.frames[name] = requestAnimationFrame(() => {
    S.frames[name] = 0
    run()
  })
}

function egText(S, name, fallback) {
  const value = S.texts && S.texts[name]
  return typeof value === 'string' ? value : fallback
}

// ---------------------------------------------------------------- 뼈대

function egBuild(S) {
  const root = egEl('div', 'eg-grid')
  const toolbar = egEl('div', 'eg-toolbar')
  toolbar.setAttribute('role', 'toolbar')
  toolbar.setAttribute('aria-label', egText(S, 'toolbar', '표 도구'))
  const frame = egEl('div', 'eg-frame')
  const scroller = egEl('div', 'eg-scroll')
  scroller.tabIndex = 0
  scroller.setAttribute('role', 'grid')
  scroller.setAttribute('aria-multiselectable', 'true')
  const canvas = egEl('div', 'eg-canvas')
  const head = egEl('div', 'eg-row eg-head')
  head.setAttribute('role', 'row')
  head.setAttribute('aria-rowindex', '1')
  const body = egEl('div', 'eg-body')
  body.setAttribute('role', 'rowgroup')
  const overlay = egEl('div', 'eg-overlay')
  overlay.setAttribute('aria-hidden', 'true')
  const editor = egEl('input', 'eg-ed')
  editor.type = 'text'
  editor.autocomplete = 'off'
  editor.spellcheck = false
  editor.hidden = true
  canvas.appendChild(head)
  canvas.appendChild(body)
  canvas.appendChild(overlay)
  canvas.appendChild(editor)
  scroller.appendChild(canvas)
  const empty = egEl('div', 'eg-empty')
  empty.hidden = true
  const tip = egEl('div', 'eg-tip')
  tip.id = S.mount + '-tip'
  tip.setAttribute('role', 'tooltip')
  tip.hidden = true
  const toastBox = egEl('div', 'eg-toast')
  toastBox.setAttribute('role', 'status')
  toastBox.hidden = true
  frame.appendChild(scroller)
  frame.appendChild(empty)
  frame.appendChild(tip)
  frame.appendChild(toastBox)
  const status = egEl('div', 'eg-status')
  const where = egEl('span', 'eg-where')
  where.id = S.mount + '-where'
  const note = egEl('span', 'eg-note')
  const summary = egEl('span', 'eg-summary')
  status.appendChild(where)
  status.appendChild(note)
  status.appendChild(summary)
  const live = egEl('div', 'eg-live')
  live.setAttribute('aria-live', 'polite')
  root.appendChild(toolbar)
  root.appendChild(frame)
  root.appendChild(status)
  root.appendChild(live)
  S.host.textContent = ''
  S.host.appendChild(root)
  S.dom = { root, toolbar, frame, scroller, canvas, head, body, overlay, editor, empty, tip, toast: toastBox, status, where, note, summary, live, dialog: null }
}

function egBind(S) {
  const { root, scroller, editor, head, frame } = S.dom
  // 그리드 안의 키는 문서로 올려 보내지 않는다 — Streamlit 문서 단축키(r 다시 실행·c 캐시)가 글자를 먹는다.
  egListen(S, root, 'keydown', (event) => event.stopPropagation())
  egListen(S, scroller, 'keydown', (event) => egOnKey(S, event))
  egListen(S, editor, 'keydown', (event) => egOnEditorKey(S, event))
  egListen(S, editor, 'blur', () => {
    if (S.edit && !S.committing) commitEdit(S, null, false)
  })
  egListen(S, scroller, 'pointerdown', (event) => egOnPointerDown(S, event))
  egListen(S, scroller, 'dblclick', (event) => egOnDoubleClick(S, event))
  egListen(S, head, 'click', (event) => egOnHeadClick(S, event))
  egListen(S, head, 'pointerover', (event) => egOnHeadOver(S, event))
  egListen(S, head, 'pointerout', (event) => egOnHeadOut(S, event))
  egListen(S, scroller, 'scroll', () => egFrame(S, 'scroll', () => egOnScroll(S)))
  // 기능(fill)이 처리하지 않은 붙여넣기만 여기로 온다(뿌리 거품 단계) — 한 칸에 첫 값 하나를 넣는다.
  egListen(S, root, 'paste', (event) => egOnPaste(S, event))
  egListen(S, root, 'focusout', (event) => {
    if (!egInside(S, event.relatedTarget)) sendNow(S)
  })
  egListen(S, document, 'visibilitychange', () => sendNow(S))
  egListen(S, window, 'resize', () => egFrame(S, 'layout', () => egLayout(S)))
  egListen(S, window, EG_FEED_EVENT, (event) => {
    if (event && event.detail === S.hostKey) egTakeFeed(S)
  })
  if (typeof ResizeObserver === 'function') {
    S.observer = new ResizeObserver(() => egFrame(S, 'layout', () => egLayout(S)))
    S.observer.observe(frame)
  }
}

function egInside(S, node) {
  if (!node || !S.dom) return false
  return S.dom.root.contains(node) || Boolean(S.dom.dialog && S.dom.dialog.contains(node))
}

function egPalette(S, palette) {
  const key = JSON.stringify(palette || {})
  if (key === S.paletteKey) return
  S.paletteKey = key
  for (const [name, value] of Object.entries(palette || {})) S.host.style.setProperty('--eg-' + name, String(value))
}

// ---------------------------------------------------------------- 껍데기 받기

function egReceiveShell(S, data) {
  S.texts = data.texts || {}
  S.limits = data.limits || {}
  S.rowH = Number(data.rowHeight) || 30
  S.headH = Number(data.headHeight) || 32
  S.host.style.setProperty('--eg-row-h', S.rowH + 'px')
  S.host.style.setProperty('--eg-head-h', S.headH + 'px')
  const hostKey = String(data.host || '')
  S.hostKey = EG_HOST_KEY.test(hostKey) ? hostKey : ''
  const baseKey = data.table ? String(data.baseKey || '') : ''
  const current = S.shell && S.model ? String(S.shell.baseKey || '') : ''
  if (S.model && baseKey === current) {
    S.shell = data
    egHead(S)
    paint(S)
    return
  }
  if (S.edit) commitEdit(S, null, false)
  egSaveView(S)
  S.shell = data
  S.feedData = null
  S.pending.clear()
  S.pendingBySeq.clear()
  S.dom.root.hidden = !data.table
  if (!data.table) {
    S.model = null
    S.gen = ''
    paint(S)
    return
  }
  const sameTable = S.model && S.model.table === data.table
  S.model = decodeBase(data)
  if (!sameTable) S.gen = ''
  S.view.sort = null
  S.view.filterKey = 'null'
  egRestoreView(S)
  egRebuildView(S, false)
  egApplyWidths(S, defaultWidths(S.model.keyCols, S.model.valueCount, EG_KEY_WIDTH, EG_VALUE_WIDTH))
  egLayout(S)
  egWhere(S)
}

function egViewKey(S) {
  return S.hostKey + ':' + (S.model ? S.model.table : '')
}

function egSaveView(S) {
  if (!S.model || !S.dom) return
  const order = S.view.order
  EG_VIEWS.set(egViewKey(S), {
    top: S.dom.scroller.scrollTop, left: S.dom.scroller.scrollLeft, sort: S.view.sort,
    anchor: order.length ? { row: order[Math.min(S.anchor.r, order.length - 1)], c: S.anchor.c } : null,
  })
}

function egRestoreView(S) {
  const saved = EG_VIEWS.get(egViewKey(S))
  S.view.sort = saved && saved.sort ? saved.sort : null
  S.restore = saved || null
}

// 보기 차례를 다시 짓는다(필터·정렬). keepCell 이면 지금 칸이 가리키던 원본 줄을 따라간다.
function egRebuildView(S, keepCell) {
  const m = S.model
  const old = S.view.order
  const anchorRow = keepCell && old.length ? old[Math.min(S.anchor.r, old.length - 1)] : -1
  const focusRow = keepCell && old.length ? old[Math.min(S.focus.r, old.length - 1)] : -1
  const sort = S.view.sort && S.view.sort.col < m.colCount ? S.view.sort : null
  const numeric = Boolean(sort && sort.col >= m.keyCount)
  const keyOf = sort ? (row) => (numeric ? egNumberAt(S, row, sort.col - m.keyCount) : egLabel(S, row, sort.col)) : null
  const filters = S.feedData && S.feedData.table === m.table ? S.feedData.filters : null
  S.view.order = viewOrder(m.rows, m.keyCodes, filters, sort, keyOf, numeric)
  S.view.rank = viewRank(S.view.order, m.rows)
  S.view.filtered = S.view.order.length !== m.rows
  const n = S.view.order.length
  const restore = S.restore
  if (restore && restore.anchor) {
    const r = S.view.rank[restore.anchor.row]
    S.anchor = { r: r >= 0 ? r : 0, c: clampNum(restore.anchor.c, 0, m.colCount - 1) }
    S.focus = Object.assign({}, S.anchor)
  } else if (keepCell) {
    const ar = anchorRow >= 0 ? S.view.rank[anchorRow] : -1
    const fr = focusRow >= 0 ? S.view.rank[focusRow] : -1
    S.anchor = { r: ar >= 0 ? ar : 0, c: clampNum(S.anchor.c, 0, m.colCount - 1) }
    S.focus = fr >= 0 ? { r: fr, c: clampNum(S.focus.c, 0, m.colCount - 1) } : Object.assign({}, S.anchor)
  } else {
    S.anchor = { r: 0, c: Math.min(m.keyCount, m.colCount - 1) }
    S.focus = Object.assign({}, S.anchor)
  }
  if (!n) {
    S.anchor = { r: 0, c: S.anchor.c }
    S.focus = Object.assign({}, S.anchor)
  }
}

// ---------------------------------------------------------------- feed 받기

function egTakeFeed(S) {
  const store = window.__capaEditGrid
  const slot = store && S.hostKey ? store[S.hostKey] : null
  const feed = slot && slot.feed
  if (!feed || feed === S.feedData || !S.dom || !S.model || !S.shell) return
  if (feed.table !== S.model.table || feed.baseKey !== S.shell.baseKey) return
  egApplyFeed(S, feed)
}

function egApplyFeed(S, feed) {
  const m = S.model
  S.feedData = feed
  S.gen = String(feed.gen || '')
  const acked = Number((feed.acks || {})[S.mount] || 0)
  if (acked > 0) {
    for (const op of S.box.ops) if (op.seq <= acked) egDropPreview(S, op.seq)
    boxAck(S.box, acked)
  }
  for (const op of boxDropStale(S.box, m.table, S.gen)) egDropPreview(S, op.seq)
  const decoded = decodeDraft(feed, m.valueCount)
  m.draft = decoded.draft
  m.bad = decoded.bad
  const filterKey = JSON.stringify(feed.filters || null)
  if (filterKey !== S.view.filterKey) {
    S.view.filterKey = filterKey
    egRebuildView(S, true)
  }
  const note = feed.toast
  if (note && note.id !== S.lastToast) {
    if (S.seenFeed) toast(S, String(note.text || ''))
    S.lastToast = note.id
  }
  S.seenFeed = true
  egApplyRestore(S)
  egHead(S)
  paint(S)
  egWhere(S)
  for (const item of FEATURES) if (item.onFeed) item.onFeed(S)
}

function egApplyRestore(S) {
  const restore = S.restore
  if (!restore || !S.dom) return
  S.restore = null
  S.dom.scroller.scrollTop = restore.top || 0
  S.dom.scroller.scrollLeft = restore.left || 0
}

// ---------------------------------------------------------------- 값 읽기

function egLabel(S, row, c) {
  const m = S.model
  const code = m.keyCodes[c][row]
  const labels = m.labels[c]
  return labels ? String(labels[code]) : String(m.dims[c][code])
}

// 원본 줄·값 칸의 지금 상태 — 보내는 중(미리보기) → 초안 → 양식 차례.
function egCellState(S, row, vc) {
  const m = S.model
  const cell = row * m.valueCount + vc
  const base = m.values[cell]
  const template = Number.isNaN(base) ? null : base
  const pend = S.pending.get(cell)
  if (pend) {
    if (pend.bad) return { value: null, bad: pend.bad, changed: true, template }
    if (pend.revert) return { value: template, bad: null, changed: false, template }
    return { value: pend.value, bad: null, changed: pend.value !== template, template }
  }
  if (m.draft.has(cell)) {
    const value = m.draft.get(cell)
    if (value === DRAFT_BAD) return { value: null, bad: m.bad.get(cell) || { text: egText(S, 'badHidden', '?'), code: 'num' }, changed: true, template }
    return { value, bad: null, changed: true, template }
  }
  return { value: template, bad: null, changed: false, template }
}

function egNumberAt(S, row, vc) {
  const state = egCellState(S, row, vc)
  return state.bad || state.value === null ? NaN : state.value
}

function egErrorText(S, code) {
  const errors = (S.texts && S.texts.errors) || {}
  return typeof errors[code] === 'string' ? errors[code] : code
}

// 지금 보이는 값 — 분류 칸은 원값 글, 값 칸은 수 | null(빈칸) | 글(못 읽은 칸). r 은 보기 줄.
function valueAt(S, r, c) {
  const m = S.model
  const row = S.view.order[r]
  if (c < m.keyCount) return String(m.dims[c][m.keyCodes[c][row]])
  const state = egCellState(S, row, c - m.keyCount)
  return state.bad ? state.bad.text : state.value
}

// 칸에 보이는 글(분류 칸은 표시명).
function displayText(S, r, c) {
  const m = S.model
  const row = S.view.order[r]
  if (c < m.keyCount) return egLabel(S, row, c)
  const state = egCellState(S, row, c - m.keyCount)
  return state.bad ? state.bad.text : formatValue(state.value, m.fmt)
}

// 복사 글 — 수 칸은 원값(소수점 ., 천 단위 없음, percent 는 분수), 분류 칸은 표시명, 못 읽은 칸은 적은 글.
function rawText(S, r, c) {
  const m = S.model
  const row = S.view.order[r]
  if (c < m.keyCount) return egLabel(S, row, c)
  const state = egCellState(S, row, c - m.keyCount)
  if (state.bad) return state.bad.text
  return state.value === null ? '' : numberText(state.value)
}

function isLocked(S, c) {
  return !S.model || c < S.model.keyCount
}

// 보기 줄 r0..r1 의 업무 키(보기 차례).
function rowKeys(S, r0, r1) {
  const keys = []
  for (let r = Math.max(r0, 0); r <= Math.min(r1, S.view.order.length - 1); r += 1) keys.push(S.model.keys[S.view.order[r]])
  return keys
}

// 칸 c0..c1 가운데 값 칸 이름만.
function colNames(S, c0, c1) {
  const m = S.model
  const names = []
  for (let c = Math.max(c0, m.keyCount); c <= Math.min(c1, m.colCount - 1); c += 1) names.push(m.valueCols[c - m.keyCount])
  return names
}

function egIsBlank(S, r, c) {
  const value = valueAt(S, r, c)
  return value === null || value === ''
}

// ---------------------------------------------------------------- 칸 폭·높이

function egApplyWidths(S, widths) {
  S.widths = widths.slice()
  S.widthsTable = S.model ? S.model.table : null
  const placed = columnLefts(S.widths)
  S.lefts = placed.lefts
  S.total = placed.total
  if (S.dom) S.dom.canvas.style.width = S.total + 'px'
  egFreeze(S)
}

function egFreeze(S) {
  if (!S.model || !S.dom) return
  const width = S.dom.scroller.clientWidth || S.total
  S.frozen = frozenCount(S.widths, S.model.keyCount, width, EG_FROZEN_RATIO)
  S.frozenWidth = S.frozen ? S.lefts[S.frozen - 1] + S.widths[S.frozen - 1] : 0
}

// 칸 폭을 바꾼다(기능 — 머리 경계 끌기·칸 폭 맞춤이 부른다). 고정 칸 수를 다시 셈하고 다시 그린다.
function setWidths(S, widths) {
  if (!S.model) return
  egApplyWidths(S, widths)
  egHead(S)
  paint(S)
  for (const item of FEATURES) if (item.onLayout) item.onLayout(S)
}

// 표 높이 = 창 높이 − 표 위 끝 − 아래 여백(24px), 최소 360px. 전체 화면이면 창(대화 상자) 안에서 같은 셈.
function egLayout(S) {
  if (!S.dom || !S.model) return
  const scroller = S.dom.scroller
  const statusHeight = S.dom.status.offsetHeight || 24
  const rect = scroller.getBoundingClientRect()
  let top = rect.top
  if (!S.full) {
    const shadowHost = S.host.getRootNode && S.host.getRootNode().host
    const main = shadowHost && shadowHost.closest ? shadowHost.closest('[data-testid="stMain"]') : null
    top = rect.top + (main ? main.scrollTop - main.getBoundingClientRect().top : window.scrollY || 0)
  }
  const height = Math.max(Math.round(window.innerHeight - top - statusHeight - EG_BOTTOM_GAP), EG_MIN_HEIGHT)
  if (scroller.style.height !== height + 'px') scroller.style.height = height + 'px'
  egFreeze(S)
  egHead(S)
  paint(S)
  for (const item of FEATURES) if (item.onLayout) item.onLayout(S)
}

function visibleRowCount(S) {
  if (!S.dom) return 1
  return Math.max(Math.floor((S.dom.scroller.clientHeight - S.headH) / S.rowH), 1)
}

function egVisibleColCount(S) {
  if (!S.dom || !S.model) return 1
  const room = S.dom.scroller.clientWidth - S.frozenWidth
  return Math.max(Math.floor(room / EG_VALUE_WIDTH), 1)
}

// ---------------------------------------------------------------- 그리기

function egHead(S) {
  const m = S.model
  const head = S.dom.head
  head.textContent = ''
  const scroller = S.dom.scroller
  if (!m) return
  scroller.setAttribute('aria-label', m.title)
  scroller.setAttribute('aria-rowcount', String(S.view.order.length + 1))
  scroller.setAttribute('aria-colcount', String(m.colCount))
  const help = S.shell && typeof S.shell.valueHelp === 'string' ? S.shell.valueHelp : ''
  const sortHint = egText(S, 'sortHint', '눌러서 정렬')
  for (let c = 0; c < m.colCount; c += 1) {
    const isKey = c < m.keyCount
    const cell = egEl('div', 'eg-c eg-hc')
    cell.dataset.c = String(c)
    cell.dataset.kind = isKey ? 'key' : 'value'
    cell.setAttribute('role', 'columnheader')
    cell.setAttribute('aria-colindex', String(c + 1))
    cell.style.width = S.widths[c] + 'px'
    if (c < S.frozen) {
      cell.classList.add('eg-fz')
      cell.style.left = S.lefts[c] + 'px'
      if (c === S.frozen - 1) cell.classList.add('eg-fz-last')
    }
    const label = isKey ? String(m.keyCols[c].label || m.keyCols[c].name) : String(m.valueCols[c - m.keyCount])
    cell.appendChild(egEl('span', 'eg-hl', label))
    const sort = S.view.sort
    if (sort && sort.col === c) {
      cell.appendChild(egEl('span', 'eg-sort', sort.dir === 'asc' ? '▲' : '▼'))
      cell.setAttribute('aria-sort', sort.dir === 'asc' ? 'ascending' : 'descending')
    }
    if (!isKey && help) cell.setAttribute('aria-describedby', S.dom.tip.id)
    else cell.title = label + ' · ' + sortHint
    cell.appendChild(egEl('span', 'eg-edge'))
    head.appendChild(cell)
  }
}

function paint(S) {
  if (!S.dom) return
  const m = S.model
  const n = m ? S.view.order.length : 0
  S.dom.empty.hidden = !m || n > 0
  if (!S.dom.empty.hidden) S.dom.empty.textContent = egText(S, 'empty', '')
  if (!m) {
    S.dom.body.textContent = ''
    return
  }
  const scroller = S.dom.scroller
  const viewHeight = Math.max(scroller.clientHeight - S.headH, S.rowH)
  const start = Math.max(Math.floor(scroller.scrollTop / S.rowH) - EG_BUFFER_ROWS, 0)
  const end = Math.min(n, Math.ceil((scroller.scrollTop + viewHeight) / S.rowH) + EG_BUFFER_ROWS)
  const fragment = document.createDocumentFragment()
  const range = S.range()
  for (let r = start; r < end; r += 1) fragment.appendChild(egRow(S, r, range))
  S.dom.body.style.paddingTop = start * S.rowH + 'px'
  S.dom.body.style.height = n * S.rowH + 'px'
  S.dom.body.textContent = ''
  S.dom.body.appendChild(fragment)
  S.window = { start, end }
  egPlaceEditor(S)
  egActive(S)
  for (const item of FEATURES) if (item.paintOverlay) item.paintOverlay(S)
}

function egRow(S, r, range) {
  const m = S.model
  const row = S.view.order[r]
  const line = egEl('div', 'eg-row')
  line.setAttribute('role', 'row')
  line.setAttribute('aria-rowindex', String(r + 2))
  line.dataset.r = String(r)
  for (let c = 0; c < m.colCount; c += 1) {
    const cell = document.createElement('div')
    cell.className = 'eg-c'
    cell.setAttribute('role', 'gridcell')
    cell.setAttribute('aria-colindex', String(c + 1))
    cell.dataset.c = String(c)
    cell.style.width = S.widths[c] + 'px'
    if (c < S.frozen) {
      cell.classList.add('eg-fz')
      cell.style.left = S.lefts[c] + 'px'
      if (c === S.frozen - 1) cell.classList.add('eg-fz-last')
    }
    let text
    if (c < m.keyCount) {
      text = egLabel(S, row, c)
      cell.classList.add('is-key')
      cell.setAttribute('aria-readonly', 'true')
      cell.title = text
    } else {
      const state = egCellState(S, row, c - m.keyCount)
      cell.classList.add('is-num')
      if (state.changed) {
        cell.classList.add('is-changed')
        cell.dataset.changed = '1'
      }
      if (state.bad) {
        cell.classList.add('is-error')
        cell.setAttribute('aria-invalid', 'true')
        text = state.bad.text
      } else text = formatValue(state.value, m.fmt)
    }
    cell.textContent = text
    const selected = r >= range.r0 && r <= range.r1 && c >= range.c0 && c <= range.c1
    cell.setAttribute('aria-selected', selected ? 'true' : 'false')
    if (r === S.anchor.r && c === S.anchor.c) {
      cell.classList.add('is-active')
      cell.id = S.mount + '-active'
      if (cell.classList.contains('is-error')) cell.setAttribute('aria-describedby', S.dom.where.id)
    }
    for (const item of FEATURES) if (item.paintCell) item.paintCell(S, cell, r, c)
    line.appendChild(cell)
  }
  return line
}

function egActive(S) {
  const scroller = S.dom.scroller
  const active = S.window && S.anchor.r >= S.window.start && S.anchor.r < S.window.end
  if (active) scroller.setAttribute('aria-activedescendant', S.mount + '-active')
  else scroller.removeAttribute('aria-activedescendant')
}

function egOnScroll(S) {
  const scroller = S.dom.scroller
  const shown = S.window
  const top = Math.floor(scroller.scrollTop / S.rowH)
  const bottom = Math.ceil((scroller.scrollTop + scroller.clientHeight) / S.rowH)
  if (!shown || top < shown.start || bottom > shown.end) paint(S)
  else egPlaceEditor(S)
  for (const item of FEATURES) if (item.paintOverlay) item.paintOverlay(S)
}

// 상태 줄 왼쪽 — 「표 › 분류 · 월」 과 그 칸 오류 문구.
function egWhere(S) {
  const where = S.dom.where
  const m = S.model
  if (!m || !S.view.order.length) {
    where.textContent = ''
    return
  }
  const row = S.view.order[Math.min(S.anchor.r, S.view.order.length - 1)]
  const keys = []
  for (let j = 0; j < m.keyCount; j += 1) keys.push(egLabel(S, row, j))
  let text = m.title + ' › ' + keys.join(' · ')
  if (S.anchor.c >= m.keyCount) {
    text += ' · ' + m.valueCols[S.anchor.c - m.keyCount]
    const state = egCellState(S, row, S.anchor.c - m.keyCount)
    if (state.bad) text += ' — ' + egErrorText(S, state.bad.code)
  }
  where.textContent = text
}

function egOnHeadOver(S, event) {
  const cell = event.target.closest && event.target.closest('.eg-hc')
  const help = S.shell && typeof S.shell.valueHelp === 'string' ? S.shell.valueHelp : ''
  if (!cell || cell.dataset.kind !== 'value' || !help) return
  if (S.tipCell === cell) return
  S.tipCell = cell
  egTimer(S, 'tip', EG_TIP_MS, () => {
    if (S.tipCell !== cell || !S.dom) return
    const tip = S.dom.tip
    tip.textContent = help
    const frameBox = S.dom.frame.getBoundingClientRect()
    const cellBox = cell.getBoundingClientRect()
    tip.style.left = Math.max(cellBox.left - frameBox.left, 0) + 'px'
    tip.style.top = cellBox.bottom - frameBox.top + 4 + 'px'
    tip.hidden = false
  })
}

function egOnHeadOut(S, event) {
  const cell = event.target.closest && event.target.closest('.eg-hc')
  if (!cell || (event.relatedTarget && cell.contains(event.relatedTarget))) return
  S.tipCell = null
  if (S.timers.tip) clearTimeout(S.timers.tip)
  S.timers.tip = 0
  if (S.dom) S.dom.tip.hidden = true
}

// ---------------------------------------------------------------- 고름·옮김

function setRange(S, anchor, focus) {
  const m = S.model
  if (!m) return
  const rows = S.view.order.length
  if (!rows) return
  const clampCell = (pos) => ({ r: clampNum(pos.r, 0, rows - 1), c: clampNum(pos.c, 0, m.colCount - 1) })
  S.anchor = clampCell(anchor)
  S.focus = clampCell(focus || anchor)
  paint(S)
  egWhere(S)
  for (const item of FEATURES) if (item.onSelect) item.onSelect(S)
}

function scrollToCell(S, r, c) {
  if (!S.dom || !S.model) return
  const scroller = S.dom.scroller
  const top = r * S.rowH
  const room = scroller.clientHeight - S.headH
  if (top < scroller.scrollTop) scroller.scrollTop = top
  else if (top + S.rowH > scroller.scrollTop + room) scroller.scrollTop = top + S.rowH - room
  if (c >= S.frozen) {
    const left = S.lefts[c]
    const width = S.widths[c]
    if (left - S.frozenWidth < scroller.scrollLeft) scroller.scrollLeft = left - S.frozenWidth
    else if (left + width > scroller.scrollLeft + scroller.clientWidth) scroller.scrollLeft = left + width - scroller.clientWidth
  }
}

// 화면 좌표 → 보기 칸. 가상 스크롤이라 손 밑 칸이 DOM 에 없을 수 있어 좌표로 셈한다. clamp 면 표 밖 좌표도 끝 칸으로.
function cellAtPoint(S, x, y, clamp) {
  if (!S.dom || !S.model || !S.view.order.length) return null
  const scroller = S.dom.scroller
  const box = scroller.getBoundingClientRect()
  let px = x - box.left - (scroller.clientLeft || 0)
  let py = y - box.top - (scroller.clientTop || 0)
  const width = scroller.clientWidth
  const height = scroller.clientHeight
  if (!clamp && (px < 0 || py < S.headH || px >= width || py >= height)) return null
  px = clampNum(px, 0, Math.max(width - 1, 0))
  py = clampNum(py, S.headH, Math.max(height - 1, S.headH))
  const cx = px < S.frozenWidth ? px : px + scroller.scrollLeft
  if (!clamp && cx >= S.total) return null
  const r = clampNum(Math.floor((py - S.headH + scroller.scrollTop) / S.rowH), 0, S.view.order.length - 1)
  return { r, c: clampNum(colAtX(S.lefts, cx), 0, S.model.colCount - 1) }
}

function focusGrid(S) {
  if (S.dom) S.dom.scroller.focus({ preventScroll: true })
}

function egOnPointerDown(S, event) {
  if (!S.model || event.button !== 0) return
  const hit = egHit(S, event)
  if (!hit) return
  for (const item of FEATURES) if (item.pointerdown && item.pointerdown(S, event, hit) === true) return
  if (hit.kind !== 'cell') return
  event.preventDefault()
  if (S.edit) commitEdit(S, null, false)
  const selection = document.getSelection ? document.getSelection() : null
  if (selection && selection.rangeCount) selection.removeAllRanges()
  focusGrid(S)
  setRange(S, hit, hit)
}

function egHit(S, event) {
  const target = event.target
  if (!target || !target.closest || target.closest('.eg-ed')) return null
  const headCell = target.closest('.eg-hc')
  if (headCell) return { kind: target.closest('.eg-edge') ? 'edge' : 'head', r: -1, c: Number(headCell.dataset.c) }
  if (target.closest('.eg-handle')) return { kind: 'handle', r: S.focus.r, c: S.focus.c }
  const cell = cellAtPoint(S, event.clientX, event.clientY, false)
  return cell ? { kind: 'cell', r: cell.r, c: cell.c } : null
}

function egOnDoubleClick(S, event) {
  if (!S.model || (event.target.closest && event.target.closest('.eg-hc, .eg-ed'))) return
  const cell = cellAtPoint(S, event.clientX, event.clientY, false)
  if (!cell || isLocked(S, cell.c)) return
  setRange(S, cell, cell)
  startEdit(S)
}

function egOnHeadClick(S, event) {
  if (!S.model || !event.target.closest || event.target.closest('.eg-edge')) return
  const cell = event.target.closest('.eg-hc')
  if (!cell) return
  if (S.suppressHeadClick) {
    S.suppressHeadClick = false
    return
  }
  egSort(S, Number(cell.dataset.c))
}

// 머리 누름 = 정렬(오름 → 내림 → 없음, 보기만). 지금 칸은 같은 원본 줄을 따라간다.
function egSort(S, c) {
  if (S.edit) commitEdit(S, null, false)
  S.view.sort = nextSort(S.view.sort, c)
  egRebuildView(S, true)
  egHead(S)
  scrollToCell(S, S.anchor.r, S.anchor.c)
  paint(S)
  egWhere(S)
  const sort = S.view.sort
  announce(S, sort ? egText(S, sort.dir === 'asc' ? 'sortedAsc' : 'sortedDesc', '') : egText(S, 'sortCleared', ''))
}

// ---------------------------------------------------------------- 키

function egOnKey(S, event) {
  if (!S.model || event.target === S.dom.editor) return
  for (const item of FEATURES) {
    if (item.keydown && item.keydown(S, event) === true) {
      event.stopPropagation()
      return
    }
  }
  if (egCoreKey(S, event)) {
    event.preventDefault()
    event.stopPropagation()
  }
}

function egCoreKey(S, event) {
  const m = S.model
  const rows = S.view.order.length
  const ctrl = event.ctrlKey || event.metaKey
  const key = event.key
  const lower = key.length === 1 ? key.toLowerCase() : key
  if (ctrl && !event.altKey && (lower === 'z' || lower === 'y')) {
    egHistory(S, lower === 'y' || event.shiftKey ? 'redo' : 'undo')
    return true
  }
  if (!rows) return false
  if (ctrl && (lower === 'c' || lower === 'v' || lower === 'x')) return false
  if (key === 'Tab') {
    const next = tabMove(S.anchor, event.shiftKey, m.colCount)
    if (!next) return false
    setRange(S, next, next)
    scrollToCell(S, next.r, next.c)
    return true
  }
  const moved = moveCell(S.anchor, key, { ctrl, alt: event.altKey }, rows, m.colCount, visibleRowCount(S), egVisibleColCount(S), (r, c) => egIsBlank(S, r, c))
  if (moved) {
    setRange(S, moved, moved)
    scrollToCell(S, moved.r, moved.c)
    return true
  }
  if (key === 'Enter' || key === 'F2') {
    startEdit(S)
    return true
  }
  if (key === 'Delete') {
    const range = S.range()
    const cols = colNames(S, range.c0, range.c1)
    if (!cols.length) setStatus(S, egText(S, 'locked', ''))
    else queueOp(S, { op: 'clear', rows: rowKeys(S, range.r0, range.r1), cols })
    return true
  }
  if (key === 'Backspace') {
    startEdit(S, '')
    return true
  }
  if (key.length === 1 && !ctrl && !event.altKey) {
    startEdit(S, key)
    return true
  }
  return false
}

function egHistory(S, kind) {
  if (S.edit) return
  const name = kind === 'undo' ? 'undo' : 'redo'
  const counts = S.feedData || {}
  const editing = S.box.ops.some((op) => op.table === (S.model && S.model.table) && op.op !== 'undo' && op.op !== 'redo')
  if (!Number(counts[name]) && !(name === 'undo' && editing)) {
    setStatus(S, egText(S, name === 'undo' ? 'undoEmpty' : 'redoEmpty', ''))
    return
  }
  queueOp(S, { op: name })
  announce(S, egText(S, name === 'undo' ? 'undone' : 'redone', ''))
}

// ---------------------------------------------------------------- 칸 편집

function egEditTextAt(S, r, c) {
  const m = S.model
  const state = egCellState(S, S.view.order[r], c - m.keyCount)
  return state.bad ? state.bad.text : editText(state.value, m.fmt)
}

// 칸 편집 시작 — text 를 주면 그 글로 바꿔 쓰기(글자 입력·Backspace), 없으면 지금 값(Enter·F2·두 번 누름).
function startEdit(S, text) {
  const m = S.model
  if (!m || S.edit || !S.view.order.length) return
  const { r, c } = S.anchor
  if (isLocked(S, c)) {
    setStatus(S, egText(S, 'locked', ''))
    return
  }
  if (!S.gen) {
    setStatus(S, egText(S, 'waiting', ''))
    return
  }
  scrollToCell(S, r, c)
  const original = egEditTextAt(S, r, c)
  S.edit = { r, c, original, typed: text !== undefined }
  const editor = S.dom.editor
  editor.value = text !== undefined ? text : original
  editor.setAttribute('aria-label', m.title + ' ' + m.valueCols[c - m.keyCount])
  editor.hidden = false
  egPlaceEditor(S)
  editor.focus({ preventScroll: true })
  const end = editor.value.length
  editor.setSelectionRange(end, end)
  paint(S)
}

function egPlaceEditor(S) {
  const editor = S.dom.editor
  if (!S.edit) {
    editor.hidden = true
    return
  }
  const { r, c } = S.edit
  editor.style.top = S.headH + r * S.rowH + 'px'
  editor.style.left = S.lefts[c] + 'px'
  editor.style.width = S.widths[c] + 'px'
  editor.style.height = S.rowH + 'px'
}

// 확정 — 글이 처음과 다르면 write 1×1 을 보낸다(화면은 곧바로 미리보기, ack 와 함께 온 feed 가 정본). move 는 down·up·right·left.
function commitEdit(S, move, refocus) {
  const edit = S.edit
  if (!edit) return
  S.committing = true
  const editor = S.dom.editor
  const text = editor.value
  S.edit = null
  editor.hidden = true
  const m = S.model
  if (m && text !== edit.original && edit.r < S.view.order.length) {
    queueOp(S, { op: 'write', rows: rowKeys(S, edit.r, edit.r), cols: colNames(S, edit.c, edit.c), values: [[text]] })
  }
  if (move && EG_MOVES[move] && m) {
    const [dr, dc] = EG_MOVES[move]
    const next = { r: clampNum(edit.r + dr, 0, S.view.order.length - 1), c: clampNum(edit.c + dc, 0, m.colCount - 1) }
    setRange(S, next, next)
    scrollToCell(S, next.r, next.c)
  }
  if (refocus !== false) focusGrid(S)
  S.committing = false
  paint(S)
  egWhere(S)
}

function cancelEdit(S) {
  if (!S.edit) return
  S.committing = true
  S.edit = null
  S.dom.editor.hidden = true
  focusGrid(S)
  S.committing = false
  paint(S)
}

function egOnEditorKey(S, event) {
  event.stopPropagation()
  if (!S.edit || event.isComposing) return
  for (const item of FEATURES) if (item.keydown && item.keydown(S, event) === true) return
  const key = event.key
  if (key === 'Enter') {
    event.preventDefault()
    commitEdit(S, event.shiftKey ? 'up' : 'down')
  } else if (key === 'Tab') {
    event.preventDefault()
    commitEdit(S, event.shiftKey ? 'left' : 'right')
  } else if (key === 'Escape') {
    // 칸 편집만 그만둔다 — 기본 동작을 막아 전체 화면(대화 상자 cancel)으로 번지지 않는다.
    event.preventDefault()
    cancelEdit(S)
  } else if (S.edit.typed && key.startsWith('Arrow') && !event.shiftKey) {
    event.preventDefault()
    commitEdit(S, { ArrowDown: 'down', ArrowUp: 'up', ArrowRight: 'right', ArrowLeft: 'left' }[key])
  }
}

function egOnPaste(S, event) {
  if (event.defaultPrevented || !S.model || S.edit || !S.view.order.length) return
  const target = event.target
  if (target && target !== S.dom.scroller && !S.dom.scroller.contains(target)) return
  event.preventDefault()
  const text = (event.clipboardData && event.clipboardData.getData('text/plain')) || ''
  const first = text.replace(/\r?\n$/, '').split(/[\t\r\n]/)[0]
  const { r, c } = S.anchor
  if (isLocked(S, c)) {
    setStatus(S, egText(S, 'locked', ''))
    return
  }
  queueOp(S, { op: 'write', rows: rowKeys(S, r, r), cols: colNames(S, c, c), values: [[first]] })
}

// ---------------------------------------------------------------- 출납

// op 하나를 쌓는다 — table·gen·seq·at 을 붙이고 화면에는 곧바로 미리보기. 초안이 없던 표의 첫 op 는 기다리지 않고 바로
// 보낸다(「변경사항 적용」 이 한 회차 안에 켜지게). 쌓지 못하면(보낼 칸이 너무 많음) null.
function queueOp(S, op) {
  const m = S.model
  if (!m || !m.table) return null
  if (!S.gen) {
    setStatus(S, egText(S, 'waiting', ''))
    return null
  }
  const full = Object.assign({}, op, { table: m.table, gen: S.gen })
  const queued = boxQueue(S.box, full, Number(S.limits.outbox) || 30000, Date.now())
  if (!queued) {
    setStatus(S, egText(S, 'outboxFull', ''))
    return null
  }
  const cells = []
  for (const [cell, item] of egPreview(S, queued)) {
    item.seq = queued.seq
    S.pending.set(cell, item)
    cells.push(cell)
  }
  S.pendingBySeq.set(queued.seq, cells)
  const counts = (S.feedData && S.feedData.counts) || {}
  const first = S.box.ops.length === 1 && !Number(counts.cells)
  if (first || op.op === 'undo' || op.op === 'redo') sendNow(S)
  else egTimer(S, 'send', EG_SEND_MS, () => sendNow(S))
  paint(S)
  egWhere(S)
  return queued
}

function egPreviewOf(m, row, col, raw) {
  const base = m.values[row * m.valueCount + col]
  const template = Number.isNaN(base) ? null : base
  const parsed = parseInput(raw, m.fmt, template)
  if (parsed.error) return { bad: { text: String(parsed.text), code: parsed.error } }
  if (parsed.value === template) return { revert: true }
  return { value: parsed.value }
}

// 보내는 op 의 칸별 미리보기(서버 규칙과 같은 다듬기). 되돌리기·다시 실행은 미리보기 없이 feed 를 기다린다.
function egPreview(S, op) {
  const m = S.model
  const out = new Map()
  const rows = (op.rows || []).map((key) => m.rowOf.get(key))
  const cols = (op.cols || []).map((name) => m.colOf.get(name))
  const put = (row, col, item) => out.set(row * m.valueCount + col, item)
  if (op.op === 'write' || op.op === 'clear') {
    const values = op.op === 'write' ? op.values || [] : [['']]
    rows.forEach((row, i) => {
      if (row === undefined || !values.length) return
      const line = values[i % values.length] || []
      if (!line.length) return
      cols.forEach((col, j) => {
        const raw = line[j % line.length]
        if (col !== undefined && raw !== null && raw !== undefined) put(row, col, egPreviewOf(m, row, col, raw))
      })
    })
  } else if (op.op === 'revert') {
    rows.forEach((row) => cols.forEach((col) => {
      if (row !== undefined && col !== undefined) put(row, col, { revert: true })
    }))
  } else if (op.op === 'fill' && op.src) {
    const srcRows = (op.src.rows || []).map((key) => m.rowOf.get(key))
    const srcCols = (op.src.cols || []).map((name) => m.colOf.get(name))
    if (srcRows.some((row) => row === undefined) || srcCols.some((col) => col === undefined)) return out
    const vertical = op.dir === 'down' || op.dir === 'up'
    const forward = op.dir === 'down' || op.dir === 'right'
    const pick = (k, size) => (forward ? k % size : size - 1 - (k % size))
    rows.forEach((row, i) => cols.forEach((col, j) => {
      if (row === undefined || col === undefined) return
      const sr = vertical ? srcRows[pick(i, srcRows.length)] : srcRows[i]
      const sc = vertical ? srcCols[j] : srcCols[pick(j, srcCols.length)]
      if (sr === undefined || sc === undefined) return
      const state = egCellState(S, sr, sc)
      put(row, col, egPreviewOf(m, row, col, state.bad ? state.bad.text : state.value === null ? '' : state.value))
    }))
  }
  return out
}

function egDropPreview(S, seq) {
  const cells = S.pendingBySeq.get(seq)
  if (cells) {
    for (const cell of cells) {
      const item = S.pending.get(cell)
      if (item && item.seq <= seq) S.pending.delete(cell)
    }
  }
  S.pendingBySeq.delete(seq)
}

// 반영 안 된 op 전부를 보낸다(보낼 것이 있을 때만). 받은 data 로 다시 불린 함수 안에서는 보내지 않는다 — 마이크로태스크 뒤로.
function sendNow(S) {
  if (S.timers.send) clearTimeout(S.timers.send)
  S.timers.send = 0
  if (!S.box.ops.length || !S.setState) return
  if (S.inRender) {
    if (!S.sendQueued) {
      S.sendQueued = true
      queueMicrotask(() => {
        S.sendQueued = false
        sendNow(S)
      })
    }
    return
  }
  S.setState('outbox', { mount: S.mount, ops: S.box.ops.slice() })
}

// 단추 하나가 보내는 op — 같은 op 가 아직 ack 되지 않았으면(더블클릭의 둘째 누름) 보내지 않는다. 보냈으면 참.
function sendOnce(S, op) {
  if (!S.model) return false
  if (boxHasOp(S.box, Object.assign({}, op, { table: S.model.table, gen: S.gen }))) return false
  if (!queueOp(S, op)) return false
  sendNow(S)
  return true
}

// ---------------------------------------------------------------- 알림

// 상태 줄의 잠깐 글(4초).
function setStatus(S, text) {
  if (!S.dom || !text) return
  S.dom.note.textContent = text
  announce(S, text)
  egTimer(S, 'note', EG_STATUS_MS, () => {
    if (S.dom) S.dom.note.textContent = ''
  })
}

function announce(S, text) {
  if (!S.dom || !text) return
  S.dom.live.textContent = ''
  S.dom.live.textContent = text
}

// 그리드 뿌리 안 토스트(전체 화면으로 옮겨도 함께 간다).
function toast(S, text) {
  if (!S.dom || !text) return
  const box = S.dom.toast
  box.textContent = text
  box.hidden = false
  announce(S, text)
  egTimer(S, 'toast', EG_TOAST_MS, () => {
    if (S.dom) S.dom.toast.hidden = true
  })
}

// ---------------------------------------------------------------- 마운트

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const host = parentElement.querySelector('[data-eg-root]')
  if (!host || !data) return
  const S = host.__eg || (host.__eg = egState(host))
  S.setState = setStateValue
  S.inRender = true
  try {
    egPalette(S, data.palette)
    if (!S.dom) {
      egBuild(S)
      egBind(S)
      for (const item of FEATURES) if (item.init) item.init(S)
    }
    egReceiveShell(S, data)
    egTakeFeed(S)
  } finally {
    S.inRender = false
  }
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    sendNow(S)
    for (const item of FEATURES) if (item.cleanup) item.cleanup(S)
    for (const [target, type, handler, options] of S.listeners) target.removeEventListener(type, handler, options)
    S.listeners = []
    for (const name of Object.keys(S.timers)) if (S.timers[name]) clearTimeout(S.timers[name])
    for (const name of Object.keys(S.frames)) if (S.frames[name]) cancelAnimationFrame(S.frames[name])
    S.timers = {}
    S.frames = {}
    if (S.observer) S.observer.disconnect()
    S.observer = null
    egSaveView(S)
    S.dom = null
    S.shell = null
    S.model = null
    S.feedData = null
  }
}
