// 범용 편집 그리드 — 도구 막대(TOOLBAR): 찾기(일치 칸 칠함 · ▲▼ · Enter/Shift+Enter · F3/Shift+F3 · Ctrl+F · Esc 지움)·되돌리기/
// 다시 실행 단추(feed 의 수가 0 이면 꺼짐, ack 까지 기다림 표시)·칸 폭 맞춤(전체 — 머리 경계를 두 번 누르면 그 칸)·머리 경계 끌어
// 폭 바꾸기(40~480px, 표마다 브라우저 저장 — 저장이 없는 첫 진입에 맞춤 한 번)·적용 전 변경 서랍(옛 값 → 새 값, 누르면 그 칸,
// ✕ 는 revert)·전체 화면(그림자 DOM 안 <dialog>.showModal() — top layer 라 긴 회차의 opacity·머리 띠·사이드바에 묻히지 않는다)·
// 상태 줄 선택 범위 요약(개수 · 합계 · 평균)·상태 줄 편집 범위 글(feed `scope`). 순수 구획 `// <eg-search>`·`// <eg-summary>`·`// <eg-width>` 은 node 시험이 떼어
// 돌린다. 갈고리는 `feature({ name: 'toolbar', ... })` 하나로 단다.
//
// core 의 고정 API 밖에서 부르는 것 둘(이름을 바꾸면 이 파일도 고친다 — test_edit_grid_toolbar_js 가 본다):
// - `egLayout(S)` — 전체 화면을 여닫거나 서랍을 연 뒤 표 높이·고정 칸 수를 다시 셈한다.
// - `egHistory(S, kind)` — 되돌리기·다시 실행 단추가 Ctrl+Z·Ctrl+Y 와 같은 길을 탄다.

// <eg-search>
// 찾기 — 보이는 글(분류 표시명 · 형식 적용 값)에서 대소문자를 가리지 않는 부분 일치. 칸 번호는 보기 좌표 r × cols + c(줄 우선
// 차례 — 보기 차례가 곧 찾는 차례다).
function searchNeedle(query) {
  return String(query === null || query === undefined ? '' : query).trim().toLowerCase()
}

function searchHas(text, needle) {
  return needle !== '' && String(text).toLowerCase().indexOf(needle) >= 0
}

// test(r, c) 가 참인 칸 번호(오름차순).
function searchCells(rows, cols, test) {
  const found = []
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) if (test(r, c)) found.push(r * cols + c)
  }
  return Int32Array.from(found)
}

// 칸 번호의 자리(없으면 -1) — 목록은 오름차순이다.
function searchIndex(list, cell) {
  let low = 0
  let high = list.length - 1
  while (low <= high) {
    const mid = (low + high) >> 1
    if (list[mid] === cell) return mid
    if (list[mid] < cell) low = mid + 1
    else high = mid - 1
  }
  return -1
}

// 다음(dir 1)·이전(-1) 일치의 자리. at 이 일치 자리면 거기서 한 걸음, -1 이면 from 칸에서 — 다음은 from 이나 그 뒤의 첫 일치,
// 이전은 from 앞의 마지막 일치. 끝에서 처음으로(처음에서 끝으로) 돈다. 일치가 없으면 -1.
function searchStep(list, at, dir, from) {
  const n = list.length
  if (!n) return -1
  if (at >= 0) return (((at + dir) % n) + n) % n
  let low = 0
  let high = n
  while (low < high) {
    const mid = (low + high) >> 1
    if (list[mid] < from) low = mid + 1
    else high = mid
  }
  if (dir > 0) return low < n ? low : 0
  return low > 0 ? low - 1 : n - 1
}
// </eg-search>

// <eg-summary>
// 고른 칸 요약(엑셀 상태 표시줄) — 값 칸만 센다. 개수 = 비지 않은 칸(못 읽은 글 칸 포함), 합계·평균 = 수 칸만.
function summaryStart() {
  return { count: 0, nums: 0, sum: 0 }
}

function summaryAdd(acc, value) {
  if (value === null || value === undefined || value === '') return
  if (typeof value === 'number' && Number.isNaN(value)) return
  acc.count += 1
  if (typeof value === 'number' && Number.isFinite(value)) {
    acc.nums += 1
    acc.sum += value
  }
}

// 합계·평균 글 — 표 형식 그대로. 다만 고정 소수 표(일수 0자리·설비대수 2자리)의 평균은 소수 둘째 자리까지(끝 0 걷음 — 30.5),
// 유효숫자 표(UPEH)는 지수 꼴이 되는 큰 수(10^digits 이상)를 천 단위 + 소수 둘째 자리로(23,409,039.71) 보인다.
function summaryNumber(value, fmt, average) {
  const digits = Number(fmt.digits) || 0
  if (fmt.kind === 'fixed' && average) return groupedText(stripZeros(value.toFixed(Math.max(digits, 2))))
  if (fmt.kind === 'sig' && Math.abs(value) >= Math.pow(10, Math.max(digits, 1))) return groupedText(stripZeros(value.toFixed(2)))
  return formatValue(value, fmt)
}

// 요약 글. cells = 고른 칸 수, valueCells = 그 가운데 값 칸 수. 한 칸이면 빈 글, 값 칸이 없으면 「칸 n개」, 수가 없으면
// 「개수 n」, 그 밖은 「개수 · 합계 · 평균」.
function summaryText(acc, cells, valueCells, fmt, texts) {
  const pick = (name, fallback) => (texts && typeof texts[name] === 'string' ? texts[name] : fallback)
  const count = (n) => Number(n).toLocaleString('ko-KR')
  if (cells <= 1) return ''
  if (!valueCells) return pick('summaryCells', '칸 {n}개').replace('{n}', count(cells))
  if (!acc.nums) return pick('summaryCount', '개수 {count}').replace('{count}', count(acc.count))
  return pick('summary', '개수 {count} · 합계 {sum} · 평균 {avg}')
    .replace('{count}', count(acc.count))
    .replace('{sum}', summaryNumber(acc.sum, fmt, false))
    .replace('{avg}', summaryNumber(acc.sum / acc.nums, fmt, true))
}
// </eg-summary>

// <eg-width>
// 칸 폭 맞춤 — 머리 글(굵게) + headPad 와 칸 글 + pad 가운데 넓은 쪽을 [low, high] 로 자른다. measure(text, head) 는 글 폭(px).
// 같은 글은 한 번만 잰다. numeric 이면 가장 긴 글보다 두 글자 넘게 짧은 글은 재지 않는다(수 글은 글자 수가 폭을 정한다).
function fitWidth(texts, measure, head, pad, headPad, low, high, numeric) {
  let most = measure(String(head), true) + headPad
  const seen = new Set()
  let longest = 0
  for (const text of texts) {
    if (seen.has(text)) continue
    seen.add(text)
    if (text.length > longest) longest = text.length
  }
  for (const text of seen) {
    if (text === '' || (numeric && text.length < longest - 2)) continue
    const width = measure(text, false) + pad
    if (width > most) most = width
  }
  return clampNum(Math.ceil(most), low, high)
}

// 머리 경계 끌기 — 누른 자리에서 옮긴 만큼, [low, high] 로 자른다.
function dragWidth(startWidth, startX, x, low, high) {
  return clampNum(Math.round(startWidth + x - startX), low, high)
}

function widthStoreKey(host, table) {
  return 'capa-edit-grid-v1:' + host + ':' + table + ':widths'
}

// 칸 이름(저장 열쇠) — 분류 칸 'k:이름', 값 칸 'v:월'. 월이 밀려도 같은 이름 칸의 폭을 되찾는다.
function widthNames(keyCols, valueCols) {
  return keyCols.map((col) => 'k:' + String(col && col.name)).concat(valueCols.map((name) => 'v:' + String(name)))
}

// 저장된 폭 — 없거나 읽지 못하면 null. 저장에 없는 칸은 fallback 폭, 저장 값은 [low, high] 로 자른다. storage 는 getItem 을
// 가진 것(브라우저 저장소 — 막혀 있으면 null).
function readWidths(storage, key, names, fallback, low, high) {
  let saved = null
  try {
    const text = storage ? storage.getItem(key) : null
    saved = text ? JSON.parse(text) : null
  } catch (error) {
    return null
  }
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return null
  let found = 0
  const widths = names.map((name, c) => {
    const value = Number(saved[name])
    if (!Number.isFinite(value) || value <= 0) return fallback[c]
    found += 1
    return clampNum(Math.round(value), low, high)
  })
  return found ? widths : null
}

// 폭을 저장한다(지금 칸 이름만 — 지난 월 이름은 버린다). 저장하지 못하면(막힘·가득 참) false.
function writeWidths(storage, key, names, widths) {
  if (!storage) return false
  const saved = {}
  names.forEach((name, c) => {
    saved[name] = Math.round(widths[c])
  })
  try {
    storage.setItem(key, JSON.stringify(saved))
    return true
  } catch (error) {
    return false
  }
}
// </eg-width>

// ---------------------------------------------------------------- 상수·도우미

const TB_FIT_LOW = 40
const TB_FIT_HIGH = 160
const TB_DRAG_LOW = 40
const TB_DRAG_HIGH = 480
const TB_CELL_PAD = 16
const TB_HEAD_PAD = 30
const TB_FIND_MS = 120
const TB_CHANGES_LIMIT = 500
const TB_DRAG_SLOP = 2
const TB_EMPTY = new Int32Array(0)

function tbText(S, name, fallback) {
  return S.texts && typeof S.texts[name] === 'string' ? S.texts[name] : fallback
}

function tbFill(text, vars) {
  return String(text).replace(/\{(\w+)\}/g, (whole, name) => (Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole))
}

function tbNumber(n) {
  return Number(n).toLocaleString('ko-KR')
}

function tbEl(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined && text !== null) node.textContent = String(text)
  return node
}

function tbButton(className, text) {
  const button = tbEl('button', 'eg-tb-btn ' + className, text)
  button.type = 'button'
  return button
}

function tbLabel(node, text) {
  node.setAttribute('aria-label', text)
  node.title = text
}

function tbListen(S, target, type, handler) {
  target.addEventListener(type, handler)
  S.tb.listeners.push([target, type, handler])
}

function tbStorage() {
  try {
    return window.localStorage || null
  } catch (error) {
    return null
  }
}

function tbErrorText(S, code) {
  const errors = (S.texts && S.texts.errors) || {}
  return typeof errors[code] === 'string' ? errors[code] : String(code)
}

// 원본 줄의 분류 표시명 「공정 · 양산」.
function tbRowLabel(S, row) {
  const m = S.model
  const parts = []
  for (let j = 0; j < m.keyCount; j += 1) {
    const code = m.keyCodes[j][row]
    const labels = m.labels[j]
    parts.push(String(labels ? labels[code] : m.dims[j][code]))
  }
  return parts.join(' · ')
}

// ---------------------------------------------------------------- 뼈대

function tbInit(S) {
  const tb = (S.tb = {
    listeners: [], dom: null, timers: {}, frames: {}, resize: null, widthsModel: null, measure: null, drawerOpen: false,
    entries: [], labelsFor: null, syncKey: '', headMarked: null, summarySeq: -1, lastSummary: null, lastFit: null,
    find: { query: '', needle: '', list: TB_EMPTY, at: -1, atRow: -1, atCol: 0, sig: null, ms: 0 },
  })
  const bar = S.dom.toolbar
  const find = tbEl('div', 'eg-tb-find')
  const input = tbEl('input', 'eg-tb-q')
  input.type = 'text'
  input.autocomplete = 'off'
  input.spellcheck = false
  input.setAttribute('aria-keyshortcuts', 'Control+F')
  const prev = tbButton('eg-tb-icon eg-tb-prev', '▲')
  const next = tbButton('eg-tb-icon eg-tb-next', '▼')
  const count = tbEl('span', 'eg-tb-count')
  find.appendChild(input)
  find.appendChild(prev)
  find.appendChild(next)
  find.appendChild(count)
  const undo = tbButton('eg-tb-undo')
  const redo = tbButton('eg-tb-redo')
  undo.setAttribute('aria-keyshortcuts', 'Control+Z')
  redo.setAttribute('aria-keyshortcuts', 'Control+Y')
  const fit = tbButton('eg-tb-fit')
  const changes = tbButton('eg-tb-changes')
  changes.setAttribute('aria-pressed', 'false')
  const full = tbButton('eg-tb-full')
  full.setAttribute('aria-pressed', 'false')
  bar.appendChild(find)
  bar.appendChild(tbEl('span', 'eg-tb-sep'))
  bar.appendChild(undo)
  bar.appendChild(redo)
  bar.appendChild(tbEl('span', 'eg-tb-sep'))
  bar.appendChild(fit)
  bar.appendChild(changes)
  bar.appendChild(full)
  for (const sep of bar.querySelectorAll('.eg-tb-sep')) sep.setAttribute('aria-hidden', 'true')
  const drawer = tbEl('div', 'eg-drawer')
  drawer.setAttribute('role', 'region')
  drawer.hidden = true
  const drawerHead = tbEl('div', 'eg-drawer-head')
  const title = tbEl('span', 'eg-drawer-title')
  const close = tbButton('eg-tb-icon eg-drawer-close', '✕')
  drawerHead.appendChild(title)
  drawerHead.appendChild(close)
  const list = tbEl('div', 'eg-drawer-list')
  list.setAttribute('role', 'list')
  const more = tbEl('div', 'eg-drawer-more')
  const empty = tbEl('div', 'eg-drawer-empty')
  drawer.appendChild(drawerHead)
  drawer.appendChild(list)
  drawer.appendChild(more)
  drawer.appendChild(empty)
  S.dom.frame.appendChild(drawer)
  const dialog = tbEl('dialog', 'eg-dialog')
  S.host.appendChild(dialog)
  S.dom.dialog = dialog
  const scope = tbEl('span', 'eg-scope')
  S.dom.status.appendChild(scope)
  tb.dom = { input, prev, next, count, undo, redo, fit, changes, full, drawer, title, close, list, more, empty, dialog, scope }
  tbLabels(S)
  tbListen(S, input, 'input', () => tbFindSoon(S))
  tbListen(S, input, 'keydown', (event) => tbFindKey(S, event))
  tbListen(S, prev, 'click', (event) => tbGridCommand(S, event, () => tbFindGo(S, -1)))
  tbListen(S, next, 'click', (event) => tbGridCommand(S, event, () => tbFindGo(S, 1)))
  tbListen(S, undo, 'click', (event) => tbGridCommand(S, event, () => tbHistoryButton(S, 'undo')))
  tbListen(S, redo, 'click', (event) => tbGridCommand(S, event, () => tbHistoryButton(S, 'redo')))
  tbListen(S, fit, 'click', (event) => tbGridCommand(S, event, () => {
    tbFitColumns(S, null, false)
  }))
  tbListen(S, changes, 'click', (event) => tbGridCommand(S, event, () => tbToggleDrawer(S)))
  tbListen(S, full, 'click', () => tbSetFull(S, !S.full))
  tbListen(S, close, 'click', () => {
    tbToggleDrawer(S, false)
    focusGrid(S)
  })
  tbListen(S, list, 'click', (event) => tbOnChangeClick(S, event))
  // Esc(바깥 초점)·브라우저가 대화 상자를 닫으려 할 때 — 기본 닫기 대신 뿌리를 제자리로 옮기며 닫는다.
  tbListen(S, dialog, 'cancel', (event) => {
    event.preventDefault()
    tbSetFull(S, false)
  })
  tbListen(S, dialog, 'close', () => {
    if (S.full) tbSetFull(S, false)
  })
  const scroller = S.dom.scroller
  tbListen(S, scroller, 'pointermove', (event) => tbResizeMove(S, event))
  tbListen(S, scroller, 'pointerup', (event) => tbResizeEnd(S, event, false))
  tbListen(S, scroller, 'pointercancel', (event) => tbResizeEnd(S, event, true))
  tbListen(S, scroller, 'lostpointercapture', (event) => tbResizeEnd(S, event, false))
  tbListen(S, S.dom.head, 'dblclick', (event) => tbOnEdgeDoubleClick(S, event))
}

// 글(껍데기 texts)이 바뀌면 단추 글·풍선을 다시 단다 — 마운트 때는 아직 texts 가 없어 기본 글이다.
function tbLabels(S) {
  const tb = S.tb
  const d = tb.dom
  tb.labelsFor = S.texts
  d.input.placeholder = tbText(S, 'find', '찾기')
  d.input.setAttribute('aria-label', tbText(S, 'findHint', '표에서 찾기 (Ctrl+F)'))
  tbLabel(d.prev, tbText(S, 'findPrev', '이전 일치 (Shift+Enter)'))
  tbLabel(d.next, tbText(S, 'findNext', '다음 일치 (Enter)'))
  d.undo.textContent = tbText(S, 'undo', '되돌리기')
  d.undo.title = tbText(S, 'undoHint', '되돌리기 (Ctrl+Z)')
  d.redo.textContent = tbText(S, 'redo', '다시 실행')
  d.redo.title = tbText(S, 'redoHint', '다시 실행 (Ctrl+Y)')
  d.fit.textContent = tbText(S, 'fit', '칸 폭 맞춤')
  d.fit.title = tbText(S, 'fitHint', '모든 칸 폭을 글에 맞춥니다')
  tbLabel(d.close, tbText(S, 'changesClose', '닫기'))
  d.drawer.setAttribute('aria-label', tbText(S, 'changes', '적용 전 변경'))
  d.dialog.setAttribute('aria-label', tbFill(tbText(S, 'fullLabel', '{title} 전체 화면'), { title: S.model ? S.model.title : '' }))
  S.dom.toolbar.setAttribute('aria-label', tbText(S, 'toolbar', '표 도구'))
  tbFullLabel(S)
  tb.syncKey = ''
  tb.headMarked = null
}

function tbFullLabel(S) {
  const button = S.tb.dom.full
  button.textContent = S.full ? tbText(S, 'fullExit', '전체 화면 닫기 (Esc)') : tbText(S, 'full', '전체 화면')
  button.setAttribute('aria-pressed', S.full ? 'true' : 'false')
}

// 단추 상태 — 되돌리기·다시 실행 켜짐(feed 의 수, 보내는 편집)·기다림(ack 전 undo/redo)·적용 전 변경 수. 바뀐 것만 고친다.
function tbSync(S) {
  const tb = S.tb
  if (!tb || !S.model || !S.dom) return
  if (tb.labelsFor !== S.texts) tbLabels(S)
  const table = S.model.table
  const feed = S.feedData && S.feedData.table === table ? S.feedData : null
  let editing = false
  let busy = ''
  for (const op of S.box.ops) {
    if (op.table !== table) continue
    if (op.op === 'undo' || op.op === 'redo') busy = op.op
    else editing = true
  }
  const undoOn = Boolean(feed && Number(feed.undo)) || editing
  const redoOn = Boolean(feed && Number(feed.redo))
  const cells = feed && feed.counts ? Number(feed.counts.cells) || 0 : 0
  const key = [undoOn, redoOn, busy, cells].join('|')
  if (key === tb.syncKey) return
  tb.syncKey = key
  const d = tb.dom
  for (const [button, on, kind] of [[d.undo, undoOn, 'undo'], [d.redo, redoOn, 'redo']]) {
    button.setAttribute('aria-disabled', on ? 'false' : 'true')
    button.classList.toggle('is-off', !on)
    button.classList.toggle('is-busy', busy === kind)
    if (busy === kind) button.setAttribute('aria-busy', 'true')
    else button.removeAttribute('aria-busy')
  }
  d.changes.textContent = tbText(S, 'changes', '적용 전 변경') + ' (' + tbNumber(cells) + ')'
}

// 머리를 다시 지었으면 경계 칸에 풍선을 단다(core 가 머리를 지을 때마다 새 칸이다).
function tbMarkEdges(S) {
  const head = S.dom.head
  const first = head.children[0] || null
  if (first === S.tb.headMarked) return
  S.tb.headMarked = first
  const hint = tbText(S, 'resizeHint', '끌어 칸 폭 바꾸기 · 두 번 눌러 맞춤')
  for (const cell of head.children) {
    const edge = cell.children[cell.children.length - 1]
    if (edge && edge.classList.contains('eg-edge')) edge.title = hint
  }
}

// ---------------------------------------------------------------- 찾기

function tbFocusFind(S) {
  const input = S.tb.dom.input
  input.focus()
  if (typeof input.select === 'function') input.select()
}

function tbFindSoon(S) {
  const tb = S.tb
  if (tb.timers.find) clearTimeout(tb.timers.find)
  tb.timers.find = setTimeout(() => {
    tb.timers.find = 0
    tbFindRun(S)
  }, TB_FIND_MS)
}

function tbFindFlush(S) {
  const tb = S.tb
  if (!tb.timers.find) return
  clearTimeout(tb.timers.find)
  tb.timers.find = 0
  tbFindRun(S)
}

// 찾을 글이 바뀌었다 — 다시 찾고 지금 칸이나 그 뒤의 첫 일치로 간다(브라우저 찾기와 같다).
function tbFindRun(S) {
  const f = S.tb.find
  f.query = S.tb.dom.input.value
  f.needle = searchNeedle(f.query)
  f.sig = null
  f.at = -1
  f.atRow = -1
  tbFindFresh(S)
  if (S.model && f.list.length) {
    const cols = S.model.colCount
    tbFindSelect(S, searchStep(f.list, -1, 1, S.anchor.r * cols + S.anchor.c))
  } else paint(S)
  tbFindCount(S)
}

// 보기 칸 하나가 찾는 글을 품는가 — 분류 칸은 사전 코드마다 한 번, 값 칸은 같은 수마다 한 번만 형식을 짓는다.
function tbFindTest(S, needle) {
  const m = S.model
  const order = S.view.order
  const keyHit = []
  for (let j = 0; j < m.keyCount; j += 1) {
    const labels = m.labels[j]
    keyHit.push(m.dims[j].map((dim, code) => searchHas(labels ? String(labels[code]) : dim, needle)))
  }
  const memo = new Map()
  const plain = !S.pending.size
  return (r, c) => {
    const row = order[r]
    if (c < m.keyCount) return keyHit[c][m.keyCodes[c][row]]
    const cell = row * m.valueCount + c - m.keyCount
    if (plain && !m.draft.has(cell)) {
      const value = m.values[cell]
      if (Number.isNaN(value)) return false
      let hit = memo.get(value)
      if (hit === undefined) {
        hit = searchHas(formatValue(value, m.fmt), needle)
        memo.set(value, hit)
      }
      return hit
    }
    return searchHas(displayText(S, r, c), needle)
  }
}

// 일치 목록 — 표·보기 차례·feed·보내는 편집이 그대로면 앞 셈을 쓴다(칸을 그릴 때마다 불린다).
function tbFindFresh(S) {
  const f = S.tb.find
  const m = S.model
  if (!f.needle || !m) {
    f.list = TB_EMPTY
    return f
  }
  const sig = f.sig
  if (sig && sig.model === m && sig.order === S.view.order && sig.feed === S.feedData && sig.seq === S.box.seq && sig.pending === S.pending.size) return f
  if (sig && sig.model !== m) f.atRow = -1
  const began = performance.now()
  f.list = searchCells(S.view.order.length, m.colCount, tbFindTest(S, f.needle))
  f.sig = { model: m, order: S.view.order, feed: S.feedData, seq: S.box.seq, pending: S.pending.size }
  f.at = -1
  if (f.atRow >= 0 && f.atRow < S.view.rank.length) {
    const r = S.view.rank[f.atRow]
    if (r >= 0) f.at = searchIndex(f.list, r * m.colCount + f.atCol)
  }
  f.ms = performance.now() - began
  tbFindCount(S)
  return f
}

function tbFindCount(S) {
  const f = S.tb.find
  const count = S.tb.dom.count
  let text = ''
  if (f.needle && S.model) {
    text = f.list.length
      ? tbFill(tbText(S, 'findCount', '{i}/{n}'), { i: tbNumber(f.at + 1), n: tbNumber(f.list.length) })
      : tbText(S, 'findNone', '없음')
  }
  if (count.textContent !== text) count.textContent = text
  return text
}

function tbFindSelect(S, at) {
  const f = S.tb.find
  f.at = at
  if (at < 0 || !S.model) return
  const cols = S.model.colCount
  const cell = f.list[at]
  const r = Math.floor(cell / cols)
  const c = cell % cols
  f.atRow = S.view.order[r]
  f.atCol = c
  setRange(S, { r, c }, { r, c })
  scrollToCell(S, r, c)
}

// 다음·이전 일치로 — 지금 칸이 일치 칸이면 거기서 한 걸음, 아니면 지금 칸에서 가까운 쪽으로. 찾을 글이 없어 찾기 칸에
// 초점을 주었으면 false(단추가 초점을 표로 돌리지 않는다).
function tbFindGo(S, dir) {
  tbFindFlush(S)
  const f = tbFindFresh(S)
  if (!S.model) return false
  if (!f.needle) {
    tbFocusFind(S)
    return false
  }
  if (!f.list.length) {
    setStatus(S, tbText(S, 'find', '찾기') + ' ' + tbFindCount(S))
    return
  }
  const cols = S.model.colCount
  const from = S.anchor.r * cols + S.anchor.c
  tbFindSelect(S, searchStep(f.list, searchIndex(f.list, from), dir, from))
  announce(S, tbText(S, 'find', '찾기') + ' ' + tbFindCount(S))
}

function tbFindClear(S) {
  const f = S.tb.find
  S.tb.dom.input.value = ''
  if (S.tb.timers.find) clearTimeout(S.tb.timers.find)
  S.tb.timers.find = 0
  f.query = ''
  f.needle = ''
  f.list = TB_EMPTY
  f.at = -1
  f.atRow = -1
  f.sig = null
  tbFindCount(S)
  paint(S)
}

// 찾기 칸의 키 — 칸 안의 복사·붙여넣기·되돌리기는 브라우저 기본에 맡긴다.
function tbFindKey(S, event) {
  if (event.isComposing) return
  const key = event.key
  if (key === 'Enter' || key === 'F3') {
    event.preventDefault()
    tbFindGo(S, event.shiftKey ? -1 : 1)
  } else if (key === 'Escape') {
    // 찾기만 지운다 — 기본 동작을 막아 전체 화면(대화 상자 cancel)으로 번지지 않는다.
    event.preventDefault()
    tbFindClear(S)
    focusGrid(S)
  } else if ((event.ctrlKey || event.metaKey) && !event.altKey && shortcutLetter(key, event.code) === 'f') {
    event.preventDefault()
    tbFocusFind(S)
  }
}

// ---------------------------------------------------------------- 칸 그리기·키·누름 갈고리

function tbPaintCell(S, el, r, c) {
  const f = tbFindFresh(S)
  let mask = 0
  if (f.list.length) {
    const cell = r * S.model.colCount + c
    const at = searchIndex(f.list, cell)
    if (at >= 0) mask = at === f.at ? 3 : 1
  }
  const before = el.__egFind || 0
  if (before === mask) return
  el.__egFind = mask
  el.classList.toggle('is-match', Boolean(mask & 1))
  el.classList.toggle('is-match-now', Boolean(mask & 2))
}

function tbPaintOverlay(S) {
  if (!S.tb || !S.model) return
  tbSync(S)
  tbMarkEdges(S)
  if (S.tb.summarySeq !== S.box.seq) tbSummarySoon(S)
}

function tbKey(S, event) {
  if (S.edit || !S.model) return false
  const ctrl = event.ctrlKey || event.metaKey
  const key = event.key
  if (ctrl && !event.altKey && !event.shiftKey && shortcutLetter(key, event.code) === 'f') {
    event.preventDefault()
    tbFocusFind(S)
    return true
  }
  if (key === 'F3') {
    event.preventDefault()
    if (S.tb.find.needle) tbFindGo(S, event.shiftKey ? -1 : 1)
    else tbFocusFind(S)
    return true
  }
  if (key === 'Escape' && S.full) {
    event.preventDefault()
    tbSetFull(S, false)
    return true
  }
  return false
}

function tbPointerDown(S, event, hit) {
  if (hit.kind !== 'edge') return false
  tbStartResize(S, event, hit.c)
  return true
}

// ---------------------------------------------------------------- 되돌리기 단추

// 표에 하는 단추(되돌리기·다시 실행·칸 폭 맞춤·적용 전 변경·찾기 ▲▼)를 마우스로 누르면 초점을 표로 돌린다 — 이어 누르는
// Ctrl+Z·화살표·Ctrl+C/V·Delete 가 단추가 아니라 표에 간다(뿌리가 keydown 을 페이지로 내보내지 않으므로 단추에 남으면 아무
// 일도 없다). 자판(Enter·Space — click 의 detail 0)으로 누르면 단추에 남아 되풀이해 누를 수 있다. run 이 false 를 돌려주면
// (다른 칸에 초점을 주었다) 돌리지 않는다.
function tbGridCommand(S, event, run) {
  const result = run()
  if (result !== false && event && event.detail > 0) focusGrid(S)
}

function tbHistoryButton(S, kind) {
  if (!S.model) return
  egHistory(S, kind)
  tbSync(S)
}

// ---------------------------------------------------------------- 칸 폭

function tbMeasurer(S) {
  if (S.tb.measure) return S.tb.measure
  const canvas = document.createElement('canvas')
  const context = canvas && typeof canvas.getContext === 'function' ? canvas.getContext('2d') : null
  if (!context) return null
  const style = typeof getComputedStyle === 'function' ? getComputedStyle(S.dom.scroller) : null
  const family = style && style.fontFamily ? style.fontFamily : 'sans-serif'
  const fonts = ['13px ' + family, '700 12px ' + family]
  let current = ''
  return (text, head) => {
    const font = fonts[head ? 1 : 0]
    if (font !== current) {
      context.font = font
      current = font
    }
    return context.measureText(text).width
  }
}

// 칸의 보이는 글(지금 보기의 줄) — 분류 칸은 쓰인 사전 코드의 표시명, 값 칸은 같은 수마다 한 번 형식을 짓는다.
function tbColumnTexts(S, c, memo) {
  const m = S.model
  const order = S.view.order
  if (c < m.keyCount) {
    const used = new Set()
    for (let k = 0; k < order.length; k += 1) used.add(m.keyCodes[c][order[k]])
    const labels = m.labels[c]
    return Array.from(used, (code) => String(labels ? labels[code] : m.dims[c][code]))
  }
  const vc = c - m.keyCount
  const plain = !S.pending.size
  const texts = new Array(order.length)
  for (let r = 0; r < order.length; r += 1) {
    const cell = order[r] * m.valueCount + vc
    if (plain && !m.draft.has(cell)) {
      const value = m.values[cell]
      let text = memo.get(value)
      if (text === undefined) {
        text = formatValue(value, m.fmt)
        memo.set(value, text)
      }
      texts[r] = text
    } else texts[r] = displayText(S, r, c)
  }
  return texts
}

// 칸 폭 맞춤 — only 가 null 이면 모든 칸. auto 는 첫 진입 맞춤(상태 줄 글을 쓰지 않는다). 글 폭을 잴 수 없으면 false.
function tbFitColumns(S, only, auto) {
  const m = S.model
  if (!m) return false
  const measure = tbMeasurer(S)
  if (!measure) return false
  if (S.edit) commitEdit(S, null, false)
  const began = performance.now()
  const memo = new Map()
  const widths = S.widths.slice()
  const cols = only || Array.from({ length: m.colCount }, (item, c) => c)
  for (const c of cols) {
    const isKey = c < m.keyCount
    const head = isKey ? String(m.keyCols[c].label || m.keyCols[c].name) : String(m.valueCols[c - m.keyCount])
    widths[c] = fitWidth(tbColumnTexts(S, c, memo), measure, head, TB_CELL_PAD, TB_HEAD_PAD, TB_FIT_LOW, TB_FIT_HIGH, !isKey)
  }
  S.tb.widthsModel = m
  setWidths(S, widths)
  tbSaveWidths(S)
  S.tb.lastFit = { cols: cols.length, ms: performance.now() - began, auto: Boolean(auto) }
  if (!auto) setStatus(S, tbFill(tbText(S, 'fitDone', '칸 폭 맞춤 — {n}칸'), { n: tbNumber(cols.length) }))
  return true
}

function tbWidthKey(S) {
  return S.hostKey && S.model ? widthStoreKey(S.hostKey, S.model.table) : ''
}

function tbSaveWidths(S) {
  const key = tbWidthKey(S)
  if (!key) return false
  return writeWidths(tbStorage(), key, widthNames(S.model.keyCols, S.model.valueCols), S.widths)
}

function tbLoadWidths(S) {
  const key = tbWidthKey(S)
  if (!key) return null
  const m = S.model
  return readWidths(tbStorage(), key, widthNames(m.keyCols, m.valueCols), S.widths.slice(), TB_DRAG_LOW, TB_DRAG_HIGH)
}

// 새 표(모델)가 섰다 — 저장된 폭이 있으면 되살리고, 없으면 맞춤을 한 번 돌려 저장한다.
function tbOnLayout(S) {
  const tb = S.tb
  if (!tb || !S.model || tb.widthsModel === S.model) return
  tb.widthsModel = S.model
  const saved = tbLoadWidths(S)
  if (saved) setWidths(S, saved)
  else tbFitColumns(S, null, true)
}

// 머리 경계 끌기 — 손이 조금이라도 움직이면 스크롤 칸이 손을 붙든다(그 전에는 붙들지 않아 두 번 누름이 경계로 간다). 폭은 한
// 프레임에 한 번 고친다.
function tbStartResize(S, event, c) {
  event.preventDefault()
  if (S.edit) commitEdit(S, null, false)
  if (!S.model || c < 0 || c >= S.widths.length) return
  S.tb.resize = { c, id: event.pointerId, x: event.clientX, start: S.widths[c], width: S.widths[c], frame: 0, moved: false, captured: false }
}

function tbResizeMove(S, event) {
  const drag = S.tb.resize
  if (!drag || (drag.id !== undefined && event.pointerId !== undefined && event.pointerId !== drag.id)) return
  if (!drag.captured && Math.abs(event.clientX - drag.x) >= TB_DRAG_SLOP) {
    drag.captured = true
    const scroller = S.dom.scroller
    if (drag.id !== undefined && typeof scroller.setPointerCapture === 'function') {
      try {
        scroller.setPointerCapture(drag.id)
      } catch (error) {
        drag.lost = true
      }
    }
  }
  if (!drag.captured) return
  drag.width = dragWidth(drag.start, drag.x, event.clientX, TB_DRAG_LOW, TB_DRAG_HIGH)
  if (drag.frame) return
  drag.frame = requestAnimationFrame(() => {
    drag.frame = 0
    tbResizeApply(S, drag)
  })
}

function tbResizeApply(S, drag) {
  if (!S.model || !S.dom || S.widths[drag.c] === drag.width) return
  const widths = S.widths.slice()
  widths[drag.c] = drag.width
  drag.moved = true
  setWidths(S, widths)
}

function tbResizeEnd(S, event, cancelled) {
  const drag = S.tb && S.tb.resize
  if (!drag || (drag.id !== undefined && event.pointerId !== undefined && event.pointerId !== drag.id)) return
  S.tb.resize = null
  if (drag.frame) cancelAnimationFrame(drag.frame)
  drag.frame = 0
  if (cancelled) drag.width = drag.start
  else if (drag.captured && event.clientX !== undefined) drag.width = dragWidth(drag.start, drag.x, event.clientX, TB_DRAG_LOW, TB_DRAG_HIGH)
  tbResizeApply(S, drag)
  const scroller = S.dom && S.dom.scroller
  if (drag.captured && scroller && drag.id !== undefined && typeof scroller.releasePointerCapture === 'function') {
    try {
      scroller.releasePointerCapture(drag.id)
    } catch (error) {
      drag.captured = false
    }
  }
  if (drag.moved && S.model) {
    tbSaveWidths(S)
    announce(S, tbFill(tbText(S, 'widthDone', '칸 폭 {width}px'), { width: S.widths[drag.c] }))
  }
}

function tbOnEdgeDoubleClick(S, event) {
  const edge = event.target && event.target.closest ? event.target.closest('.eg-edge') : null
  const cell = edge && edge.closest('.eg-hc')
  if (!cell || !S.model) return
  event.preventDefault()
  tbFitColumns(S, [Number(cell.dataset.c)], false)
}

// ---------------------------------------------------------------- 적용 전 변경 서랍

function tbToggleDrawer(S, open) {
  const tb = S.tb
  if (!tb || !S.dom) return
  const want = open === undefined ? !tb.drawerOpen : Boolean(open)
  tb.drawerOpen = want
  tb.dom.drawer.hidden = !want
  S.dom.frame.classList.toggle('has-drawer', want)
  tb.dom.changes.setAttribute('aria-pressed', want ? 'true' : 'false')
  if (want) tbRenderDrawer(S)
  else tb.dom.list.textContent = ''
  if (S.model) egLayout(S)
}

function tbValueText(S, value) {
  return value === null || value === undefined ? tbText(S, 'changesBlank', '빈칸') : formatValue(value, S.model.fmt)
}

// 서랍 목록 — 초안 칸(feed 가 실어 온 것)을 보기 차례로, 앞 500개. 줄마다 「분류 · 월」 과 「옛 값 → 새 값」(오류는 적은 글).
function tbRenderDrawer(S) {
  const tb = S.tb
  const m = S.model
  if (!tb.drawerOpen || !m) return
  const listing = changeEntries(m.draft, m.bad, m.values, m.valueCount, S.view.rank, TB_CHANGES_LIMIT)
  tb.entries = listing.entries
  const fragment = document.createDocumentFragment()
  listing.entries.forEach((entry, i) => fragment.appendChild(tbChangeRow(S, entry, i)))
  tb.dom.list.textContent = ''
  tb.dom.list.appendChild(fragment)
  tb.dom.title.textContent = tbFill(tbText(S, 'changesTitle', '{label} {n}칸'), { label: tbText(S, 'changes', '적용 전 변경'), n: tbNumber(listing.total) })
  const rest = listing.total - listing.entries.length
  tb.dom.more.hidden = rest <= 0
  tb.dom.more.textContent = rest > 0 ? tbFill(tbText(S, 'changesMore', '외 {n}개'), { n: tbNumber(rest) }) : ''
  tb.dom.empty.hidden = listing.total > 0
  tb.dom.empty.textContent = tbText(S, 'changesEmpty', '적용 전 변경이 없습니다')
}

function tbChangeRow(S, entry, i) {
  const m = S.model
  const item = tbEl('div', 'eg-chg')
  item.setAttribute('role', 'listitem')
  item.dataset.i = String(i)
  const where = tbRowLabel(S, entry.row) + ' · ' + m.valueCols[entry.col]
  const go = tbEl('button', 'eg-chg-go')
  go.type = 'button'
  go.title = where
  go.appendChild(tbEl('span', 'eg-chg-where', where))
  const line = tbEl('span', 'eg-chg-val')
  line.appendChild(tbEl('span', 'eg-chg-old', tbValueText(S, entry.before)))
  line.appendChild(tbEl('span', 'eg-chg-arrow', ' → '))
  const after = tbEl('span', 'eg-chg-new', entry.bad ? entry.bad.text : tbValueText(S, entry.after))
  if (entry.bad) {
    item.classList.add('is-bad')
    after.title = tbErrorText(S, entry.bad.code)
  }
  line.appendChild(after)
  go.appendChild(line)
  const undo = tbButton('eg-tb-icon eg-chg-x', '✕')
  tbLabel(undo, tbFill(tbText(S, 'revertHint', '{where} 되돌리기'), { where }))
  item.appendChild(go)
  item.appendChild(undo)
  return item
}

function tbOnChangeClick(S, event) {
  const item = event.target && event.target.closest ? event.target.closest('.eg-chg') : null
  const entry = item ? S.tb.entries[Number(item.dataset.i)] : null
  if (!entry || !S.model) return
  if (event.target.closest('.eg-chg-x')) {
    const op = { op: 'revert', rows: [S.model.keys[entry.row]], cols: [S.model.valueCols[entry.col]] }
    if (sendOnce(S, op)) item.classList.add('is-pending')
    return
  }
  const r = S.view.rank[entry.row]
  if (r === undefined || r < 0) {
    setStatus(S, tbText(S, 'changesHidden', '지금 보기(필터)에 없는 줄입니다'))
    return
  }
  const c = S.model.keyCount + entry.col
  setRange(S, { r, c }, { r, c })
  scrollToCell(S, r, c)
  focusGrid(S)
}

// ---------------------------------------------------------------- 전체 화면

// 그림자 DOM 안 <dialog> 에 그리드 뿌리(도구 막대·표·상태 줄)를 옮겨 붙이고 showModal() — top layer 라 조상 opacity·z-index 를
// 받지 않고 바깥은 inert 다. 옮기면 스크롤이 0 으로 돌아가므로 기억했다가 되돌린다.
function tbSetFull(S, on) {
  const tb = S.tb
  if (!tb || !S.dom || Boolean(S.full) === Boolean(on)) return
  const dialog = tb.dom.dialog
  if (on && (!S.model || typeof dialog.showModal !== 'function')) return
  if (S.edit) commitEdit(S, null, false)
  const scroller = S.dom.scroller
  const keep = { top: scroller.scrollTop, left: scroller.scrollLeft }
  S.full = Boolean(on)
  if (S.full) {
    dialog.appendChild(S.dom.root)
    if (!dialog.open) dialog.showModal()
  } else {
    if (dialog.open && typeof dialog.close === 'function') dialog.close()
    S.host.insertBefore(S.dom.root, dialog)
  }
  tbFullLabel(S)
  egLayout(S)
  scroller.scrollTop = keep.top
  scroller.scrollLeft = keep.left
  paint(S)
  focusGrid(S)
  announce(S, S.full ? tbText(S, 'full', '전체 화면') : tbText(S, 'fullClosed', '전체 화면 닫음'))
}

// ---------------------------------------------------------------- 선택 범위 요약(상태 줄 오른쪽)

function tbSummarySoon(S) {
  const tb = S.tb
  if (tb.frames.summary) return
  tb.frames.summary = requestAnimationFrame(() => {
    tb.frames.summary = 0
    tbSummary(S)
  })
}

function tbSummary(S) {
  const tb = S.tb
  if (!S.dom || !tb) return
  tb.summarySeq = S.box.seq
  const m = S.model
  let text = ''
  if (m && S.view.order.length) {
    const began = performance.now()
    const rect = S.range()
    const cells = (rect.r1 - rect.r0 + 1) * (rect.c1 - rect.c0 + 1)
    const c0 = Math.max(rect.c0, m.keyCount)
    const valueCells = c0 <= rect.c1 ? (rect.r1 - rect.r0 + 1) * (rect.c1 - c0 + 1) : 0
    const acc = summaryStart()
    if (cells > 1) {
      for (let r = rect.r0; r <= rect.r1; r += 1) for (let c = c0; c <= rect.c1; c += 1) summaryAdd(acc, valueAt(S, r, c))
    }
    text = summaryText(acc, cells, valueCells, m.fmt, S.texts)
    tb.lastSummary = { cells, valueCells, count: acc.count, nums: acc.nums, sum: acc.sum, ms: performance.now() - began }
  }
  if (S.dom.summary.textContent !== text) S.dom.summary.textContent = text
}

// ---------------------------------------------------------------- feed·정리

// 상태 줄 편집 범위 글 — 같은 줄의 칸 위치 · 오류 문구가 먼저라 좁으면 이 글이 먼저 줄고(`.eg-scope`),
// 말줄임이 되면 풍선으로 다 읽는다. 빈 글 · 메모 · 요약은 접어 틈도 먹지 않는다. 글은 feed 가 준 값뿐이다.
function tbScope(S) {
  const scope = S.tb.dom.scope
  const text = S.feedData && typeof S.feedData.scope === 'string' ? S.feedData.scope : ''
  if (scope.textContent === text) return
  scope.textContent = text
  scope.title = text
}

function tbOnFeed(S) {
  if (!S.tb) return
  tbSync(S)
  tbScope(S)
  if (S.tb.drawerOpen) tbRenderDrawer(S)
  tbSummarySoon(S)
}

function tbCleanup(S) {
  const tb = S.tb
  if (!tb) return
  if (tb.resize && tb.resize.frame) cancelAnimationFrame(tb.resize.frame)
  tb.resize = null
  for (const name of Object.keys(tb.timers)) if (tb.timers[name]) clearTimeout(tb.timers[name])
  for (const name of Object.keys(tb.frames)) if (tb.frames[name]) cancelAnimationFrame(tb.frames[name])
  tb.timers = {}
  tb.frames = {}
  S.full = false
  const dialog = tb.dom && tb.dom.dialog
  if (dialog && dialog.open && typeof dialog.close === 'function') dialog.close()
  for (const [target, type, handler] of tb.listeners) target.removeEventListener(type, handler)
  tb.listeners = []
}

feature({
  name: 'toolbar', init: tbInit, keydown: tbKey, pointerdown: tbPointerDown, paintCell: tbPaintCell, paintOverlay: tbPaintOverlay,
  onFeed: tbOnFeed, onSelect: tbSummarySoon, onLayout: tbOnLayout, cleanup: tbCleanup,
})
