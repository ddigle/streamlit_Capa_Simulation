// 설비 마스터 표 — 가용설비 현황 「설비 마스터」 탭의 Components v2. 한 등록을 세 자리(data.mode)에 마운트한다:
// loader(불러오기) · grid(표) · side(오른쪽 칸 — 호기 상세 / 저장 전 변경).
// 편집본을 바꾸는 조작은 모두 상태 값 `outbox` 로 보낸다(반영되지 않은 조작 전부, mount·seq). 잃어도 되는 화면 조작만
// 트리거다. 업무 검증은 파이썬이 한다 — 여기는 data 가 준 잠금·고를 값·자리 계산만 안다. 데이터 글은 textContent 로만
// 넣고 innerHTML 은 고정 아이콘에만 쓴다. 아래 `// <grid-…>` 구획은 DOM 을 모르는 순수 함수라 node 시험이 떼어 돌린다.

// <grid-paste>
// 붙인 글을 칸 판으로. 끝 줄바꿈 하나는 떼고 \r 은 버린다. 탭·줄바꿈이 없으면(한 칸) null — 보통 붙여넣기다.
function parseClipboard(text) {
  const body = String(text == null ? '' : text).replace(/\r/g, '').replace(/\n$/, '')
  if (!/[\t\n]/.test(body)) return null
  return body.split('\n').map((line) => line.split('\t'))
}

// 붙일 자리: 시작 줄·칸부터 보이는 차례대로. 표 끝을 넘은 줄은 cut, 칸 끝을 넘거나 잠긴 칸은 skipped(그 칸은 null).
function planPaste(cells, startRow, startCol, rowIds, colNames, editable, limit) {
  const height = Math.min(cells.length, Math.max(rowIds.length - startRow, 0))
  const width = cells.reduce((most, line) => Math.max(most, line.length), 0)
  const cols = colNames.slice(startCol, startCol + width)
  const ids = rowIds.slice(startRow, startRow + height)
  let skipped = 0
  let count = 0
  const rows = ids.map((id, r) => {
    const line = cells[r]
    skipped += Math.max(line.length - cols.length, 0)
    return cols.map((col, c) => {
      if (c >= line.length) return null
      if (!editable(id, col)) {
        skipped += 1
        return null
      }
      count += 1
      return line[c]
    })
  })
  const total = cells.reduce((sum, line) => sum + line.length, 0)
  return { ids, cols, rows, cut: cells.length - height, skipped, count, tooMany: total > limit }
}
// </grid-paste>

// <grid-nav>
// 옆·위아래 칸. 잠긴 칸·지운 줄은 건너뛰고 한 방향으로 `limit` 칸까지만 찾는다.
function nextCell(rowCount, colCount, from, dir, editable, limit) {
  let row = from.row
  let col = from.col
  const most = Number.isInteger(limit) ? limit : 80
  for (let step = 0; step < most; step += 1) {
    if (dir === 'right') col += 1
    else if (dir === 'left') col -= 1
    else if (dir === 'down') row += 1
    else row -= 1
    if (row < 0 || row >= rowCount || col < 0 || col >= colCount) return null
    if (editable(row, col)) return { row, col }
  }
  return null
}
// </grid-nav>

// <grid-outbox>
// 보낼 목록. seq 는 마운트 안에서 늘 늘고, ack 가 온 seq 이하는 뺀다. base 가 바뀌면 통째로 버린다.
function opCells(op) {
  if (op.op === 'paste') return (op.rows || []).reduce((sum, line) => sum + line.filter((v) => v !== null).length, 0)
  if (op.op === 'set') return (op.ids || []).length
  if (op.op === 'shift') return (op.ids || []).length * 2
  return 1
}

function createBox() {
  return { seq: 0, ops: [], base: null }
}

function boxCells(box) {
  return box.ops.reduce((sum, op) => sum + opCells(op), 0)
}

function queueOp(box, op, limit, now) {
  if (boxCells(box) + opCells(op) > limit) return null
  box.seq += 1
  const queued = Object.assign({}, op, { seq: box.seq, base: box.base, at: now })
  box.ops.push(queued)
  return queued
}

function ackBox(box, seq) {
  const before = box.ops.length
  box.ops = box.ops.filter((op) => op.seq > seq)
  return before - box.ops.length
}

function rebaseBox(box, base) {
  if (box.base === base) return false
  const had = box.base !== null
  box.base = base
  box.ops = []
  return had
}
// </grid-outbox>

// <grid-match>
// 설비명 찾기 — 낱말 하나면 대소문자 무시 부분 일치, 여럿(쉼표·세미콜론·공백·탭·줄바꿈)이면 낱말마다 같음 또는 앞부분 일치.
function splitNames(text) {
  return String(text || '').split(/[,;\s]+/).map((token) => token.trim()).filter(Boolean)
}

function isNameList(text) {
  return splitNames(text).length > 1 || /[,;\n\t]/.test(String(text || '').trim())
}

function matchNames(text, names) {
  const tokens = splitNames(text)
  const found = []
  const missing = []
  const lower = names.map((name) => String(name).toLowerCase())
  if (!tokens.length) return { found, missing, list: false }
  if (!isNameList(text)) {
    const needle = tokens[0].toLowerCase()
    lower.forEach((name, index) => { if (name.includes(needle)) found.push(index) })
    if (!found.length) missing.push(tokens[0])
    return { found, missing, list: false }
  }
  const seen = new Set()
  for (const token of tokens) {
    const needle = token.toLowerCase()
    let hit = false
    lower.forEach((name, index) => {
      if (name === needle || name.startsWith(needle)) {
        hit = true
        if (!seen.has(index)) {
          seen.add(index)
          found.push(index)
        }
      }
    })
    if (!hit) missing.push(token)
  }
  return { found, missing, list: true }
}
// </grid-match>

// <grid-plan>
// 한꺼번에 고치기의 칸 수 — 잠긴 칸·같은 값은 뺀다. 밀기는 날짜가 있는 칸만, 날 수는 음수(「−」 기호도)를 받는다.
function parseDays(text) {
  const value = String(text == null ? '' : text).trim().replace(/\u2212/g, '-').replace(/^\+/, '')
  if (!/^-?\d+$/.test(value)) return null
  const days = Number(value)
  return days === 0 ? null : days
}

function shiftIso(iso, days) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null
  const moment = new Date(iso + 'T00:00:00Z')
  if (Number.isNaN(moment.getTime())) return null
  moment.setUTCDate(moment.getUTCDate() + days)
  return moment.toISOString().slice(0, 10)
}

function planSet(rows, col, text, locked) {
  const value = String(text == null ? '' : text).trim()
  return rows.filter((row) => !locked(row, col) && String(row.values[col] || '').trim() !== value).length
}

function planShift(rows, cols, days, locked) {
  if (days === null) return 0
  let count = 0
  for (const row of rows) {
    for (const col of cols) {
      if (!locked(row, col) && shiftIso(String(row.values[col] || ''), days)) count += 1
    }
  }
  return count
}
// </grid-plan>

// <grid-sort>
// 머리 누름 정렬 — 빈 값은 늘 아래, 수 칸은 수로, 글은 한국어 차례(localeCompare 'ko').
function compareCells(left, right, kind) {
  const a = String(left == null ? '' : left)
  const b = String(right == null ? '' : right)
  if (a === '' && b === '') return 0
  if (a === '') return 1
  if (b === '') return -1
  if (kind === 'number') {
    const x = Number(a)
    const y = Number(b)
    if (Number.isFinite(x) && Number.isFinite(y) && x !== y) return x - y
  }
  return a.localeCompare(b, 'ko')
}

function sortOrder(values, dir, kind) {
  const order = values.map((_, index) => index)
  if (!dir) return order
  const sign = dir === 'desc' ? -1 : 1
  return order.sort((i, j) => {
    const a = values[i]
    const b = values[j]
    if (a === '' || b === '') return compareCells(a, b, kind) || i - j
    return sign * compareCells(a, b, kind) || i - j
  })
}
// </grid-sort>

// <grid-codes>
// 불러오기 조건 칸 — 파이썬 `equipment_grid.encode_codes` 와 같은 64자 고정 폭 번호.
const CODE_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'

function decodeCodes(text, width) {
  const codes = []
  const size = Math.max(width || 1, 1)
  for (let at = 0; at + size <= text.length; at += size) {
    let code = 0
    for (let k = 0; k < size; k += 1) code = code * CODE_ALPHABET.length + CODE_ALPHABET.indexOf(text[at + k])
    codes.push(code)
  }
  return codes
}

// 조건 여럿(칸 번호·값 번호)을 모두 맞는 줄 자리. 값 번호가 null 인 조건은 건너뛴다.
function matchConditions(columns, picks, count) {
  const found = []
  for (let row = 0; row < count; row += 1) {
    if (picks.every((pick) => pick.value === null || columns[pick.col][row] === pick.value)) found.push(row)
  }
  return found
}

// 조건이 기억한 값 **글**을 이 회차 값 번호로 푼다 — 값 목록은 회차마다 다시 만들어져 번호가 밀린다. 그 값이 목록에서
// 사라졌으면 null(값 고르기로 돌아간다).
function resolvePicks(picks, values) {
  return picks.map((pick) => {
    if (typeof pick.text !== 'string') return { col: pick.col, value: null }
    const code = (values[pick.col] || []).indexOf(pick.text)
    return { col: pick.col, value: code < 0 ? null : code }
  })
}
// </grid-codes>

// <grid-place>
// 팝오버를 단추 왼쪽에서 얼마나 당길지(px, 0 이하) — 화면 오른쪽 밖으로 나가면 왼쪽으로, 왼쪽 끝 `margin` 은 남긴다.
function popoverShift(left, width, viewport, margin) {
  const over = left + width - (viewport - margin)
  if (over <= 0) return 0
  return -Math.min(over, Math.max(left - margin, 0))
}
// </grid-place>

const NAME_PASTE_NOTE = '설비명은 붙여 넣지 않습니다 — 이름은 오른쪽 호기 상세의 설비명 칸에서 바꿉니다'
const ROW_H = 34
const BUFFER_ROWS = 10
const SEND_MS = 300
const COLSET_KEY = 'capa.equipmentGrid.colSet'
const ICONS = {
  search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>',
  close: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>',
  minus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"></path></svg>',
  undo: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 14L4 9l5-5"></path><path d="M4 9h10a6 6 0 0 1 0 12h-3"></path></svg>',
  down: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>',
}

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined && text !== null) node.textContent = String(text)
  return node
}

function button(className, text, onClick) {
  const node = el('button', className, text)
  node.type = 'button'
  if (onClick) node.addEventListener('click', onClick)
  return node
}

function icon(name, label, onClick) {
  const node = button('emg-icon', null, onClick)
  node.innerHTML = ICONS[name]
  node.setAttribute('aria-label', label)
  node.title = label
  return node
}

function readColSet() {
  try {
    return window.localStorage.getItem(COLSET_KEY)
  } catch (error) {
    return null
  }
}

function writeColSet(value) {
  try {
    window.localStorage.setItem(COLSET_KEY, value)
  } catch (error) {
    // 저장소가 막힌 창(시크릿·미리보기)에서는 기억하지 않는다.
  }
}

function newMount() {
  return 'm-' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4)
}

function freshState() {
  return {
    mount: newMount(), box: createBox(), pending: new Map(), timer: 0, base: null, view: null,
    selected: new Set(), anchor: null, sort: null, colSet: null, edit: null, focus: null, toastClosed: null,
    note: '', noteTimer: 0, scrollFrame: 0, query: '', pop: null, procQuery: '', conds: [{ col: 4, text: null }],
    suggest: -1, drafts: new Map(), unitId: null, listeners: [], bulkCol: 'Qual상태', bulkValue: '', days: '7',
  }
}

function listen(S, target, type, handler, options) {
  target.addEventListener(type, handler, options)
  S.listeners.push([target, type, handler, options])
}

function cssEscape(text) {
  return String(text).replace(/["\\]/g, '\\$&')
}

// 그림자 DOM 안에서는 document.activeElement 가 호스트다 — 그 칸이 든 뿌리의 activeElement 를 본다.
function activeIn(node) {
  const root = node.getRootNode ? node.getRootNode() : document
  return root.activeElement || null
}

// 다시 그려도 쓰던 칸을 잃지 않게 — 초점을 가진 칸(data-fk)과 글자 자리를 잡았다가 새 칸에 돌려준다.
function captureFocus(root) {
  const active = activeIn(root)
  if (!active || !root.contains(active) || !active.dataset || !active.dataset.fk) return null
  return { key: active.dataset.fk, start: active.selectionStart, end: active.selectionEnd }
}

function restoreFocus(root, saved) {
  if (!saved) return
  const node = root.querySelector('[data-fk="' + cssEscape(saved.key) + '"]')
  if (!node) return
  node.focus()
  if (typeof saved.start === 'number' && node.setSelectionRange) {
    try {
      node.setSelectionRange(saved.start, saved.end)
    } catch (error) {
      // 글자 칸이 아니면 자리를 돌려줄 것이 없다.
    }
  }
}

function stopKeys(event) {
  // 칸·찾기 칸의 키는 문서로 올려 보내지 않는다 — Streamlit 문서 단축키(r 다시 실행·c 캐시)가 글자를 먹는다.
  event.stopPropagation()
}

// ---------------------------------------------------------------- 출납(표·오른쪽 칸 공용)

function receive(S, data) {
  const base = String(data.base || '')
  if (rebaseBox(S.box, base)) {
    S.pending.clear()
    S.edit = null
    S.drafts.clear()
  }
  S.base = base
  const ack = data.ack || {}
  if (ack.mount === S.mount && Number.isInteger(ack.seq)) {
    ackBox(S.box, ack.seq)
    for (const [key, item] of S.pending) if (item.seq <= ack.seq) S.pending.delete(key)
  }
  S.limit = Number((data.limits || {}).outboxCells) || 10000
}

function send(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = 0
  if (!S.box.ops.length || !S.setState) return
  S.setState('outbox', { mount: S.mount, ops: S.box.ops.slice() })
}

function schedule(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = setTimeout(() => send(S), SEND_MS)
}

function enqueue(S, op, cells) {
  const queued = queueOp(S.box, op, S.limit, Date.now())
  if (!queued) {
    showNote(S, '보낼 고침이 너무 많습니다 — 잠시 뒤 다시 하거나 「엑셀·CSV로 한꺼번에」 를 씁니다')
    return null
  }
  for (const [id, col, text] of cells || []) S.pending.set(id + '\t' + col, { seq: queued.seq, text })
  return queued
}

function showNote(S, text) {
  S.note = text
  if (S.noteTimer) clearTimeout(S.noteTimer)
  S.noteTimer = setTimeout(() => {
    S.note = ''
    S.noteTimer = 0
    if (S.repaintToast) S.repaintToast()
  }, 6000)
  if (S.repaintToast) S.repaintToast()
}

function pendingText(S, id, col) {
  const item = S.pending.get(id + '\t' + col)
  return item ? item.text : null
}

// ---------------------------------------------------------------- 칸 공용

function lockSets(data) {
  const sets = {}
  for (const [kind, cols] of Object.entries(data.lockSets || {})) sets[kind] = new Set(cols)
  return sets
}

function lockOf(row, col, sets) {
  if (row.tag === 'deleted') return 'deleted'
  for (const kind of row.locks || []) if (sets[kind] && sets[kind].has(col)) return kind
  return null
}

function cellTip(row, col, columns, reasons, lock) {
  const parts = []
  const errors = row.errors || {}
  const warns = row.warns || {}
  const changed = row.changed || {}
  if (lock) parts.push(reasons[lock] || '')
  if (errors[col] !== undefined) parts.push('오류: ' + errors[col])
  if (warns[col] !== undefined) parts.push('경고: ' + warns[col])
  if (changed[col] !== undefined) parts.push('저장본: ' + (changed[col] || '(빈칸)'))
  if (!parts.length && columns[col]) parts.push(columns[col].help || '')
  return parts.filter(Boolean).join('\n')
}

// ---------------------------------------------------------------- loader

function loaderModel(data) {
  const names = Array.isArray(data.names) ? data.names.map(String) : []
  const sparse = data.ids || {}
  const ids = names.map((name, index) => sparse[String(index)] || 's:' + name)
  const conds = data.conditions || { columns: [], values: [], codes: [], widths: [] }
  const columns = (conds.codes || []).map((text, k) => decodeCodes(String(text), (conds.widths || [])[k]))
  return { names, ids, conds, columns }
}

function drawLoader(host, S, data) {
  S.data = data
  const model = loaderModel(data)
  S.model = model
  const saved = captureFocus(host)
  S.painting = true
  host.textContent = ''
  const root = el('div', 'emg-loader')
  host.appendChild(root)
  const bar = el('div', 'emg-lb')
  root.appendChild(bar)
  bar.appendChild(searchBox(S, model))
  bar.appendChild(processPopover(S, model))
  bar.appendChild(conditionPopover(S, model))
  const alertIds = Array.isArray(data.alertIds) ? data.alertIds : []
  const alerts = button('emg-btn is-warn', '일정 확인 필요 ' + alertIds.length.toLocaleString() + '대', () => {
    load(S, 'alerts', alertIds, [], '일정 확인 필요')
  })
  alerts.disabled = alertIds.length === 0
  alerts.title = '일정이 지났는데 실적이 없거나, 상태와 실적이 맞지 않는 호기'
  bar.appendChild(alerts)
  if (data.newEnabled) {
    const fresh = button('emg-btn', '+ 새 호기', () => S.setTrigger('new', {}))
    fresh.disabled = Boolean(data.newRowsLocked)
    bar.appendChild(fresh)
  }
  bar.appendChild(button('emg-btn', '엑셀·CSV로 한꺼번에', () => S.setTrigger('dialog', { name: 'import' })))
  const loaded = Array.isArray(data.loaded) ? data.loaded.length : 0
  const total = Number(data.total) || 0
  const info = el('div', 'emg-info')
  const count = el('span')
  count.appendChild(el('span', null, '불러온 호기 '))
  count.appendChild(el('b', null, loaded.toLocaleString()))
  count.appendChild(el('span', 'emg-muted', '대 / 전체 ' + total.toLocaleString() + '대'))
  info.appendChild(count)
  if (loaded) info.appendChild(button('emg-link', '목록 비우기', () => S.setTrigger('clear', {})))
  if (total) info.appendChild(button('emg-link', '전체 ' + total.toLocaleString() + '대 불러오기', () => load(S, 'all', [], [], '전체')))
  const missing = Array.isArray(data.missing) ? data.missing : []
  if (missing.length) info.appendChild(el('span', 'emg-miss', '못 찾은 설비명: ' + missing.join(', ')))
  root.appendChild(info)
  if (!loaded) root.appendChild(emptyState(S, data, alertIds, total))
  S.painting = false
  const focus = S.refocus
  S.refocus = null
  if (focus === 'search' && S.searchInput && focusIsFree(host)) {
    S.searchInput.focus()
    S.searchInput.setSelectionRange(S.query.length, S.query.length)
  } else restoreFocus(host, saved)
}

// 불러오기 회차가 돌아와 찾기 칸에 초점을 돌려줘도 되는가 — 초점이 아무 데도 없거나(다시 그리며 지운 칸) 이 불러오기
// 안일 때만. 그 사이 표 칸을 눌러 치고 있으면 빼앗지 않는다(남은 글자가 찾기 칸으로 가 불러오기가 된다).
function focusIsFree(host) {
  const root = host.getRootNode ? host.getRootNode() : document
  const inner = root !== document ? root.activeElement : null
  if (inner) return host.contains(inner)
  const outer = document.activeElement
  return !outer || outer === document.body || outer === document.documentElement || (root !== document && outer === root.host)
}

// 찾기 칸을 바로 비운다 — 이미 불러온 이름을 다시 찾으면 data 가 같아 다시 그려지지 않으므로 기다리지 않는다.
function clearSearch(S) {
  S.query = ''
  S.pop = null
  S.suggest = -1
  if (S.searchInput) S.searchInput.value = ''
  if (S.searchList) {
    S.searchList.textContent = ''
    S.searchList.hidden = true
  }
  if (S.searchGo) S.searchGo.disabled = true
}

function emptyState(S, data, alertIds, total) {
  const box = el('div', 'emg-empty')
  const buttons = el('div', 'emg-row-buttons')
  if (data.firstData) {
    box.appendChild(el('b', null, '첫 데이터는 엑셀·CSV로 한꺼번에 붙여 넣습니다'))
    box.appendChild(el('span', 'emg-muted', '저장된 설비 데이터가 아직 없습니다. 붙여 넣은 뒤 「저장 전 변경」 에서 리비전을 저장합니다.'))
    buttons.appendChild(button('emg-btn is-primary', '엑셀·CSV로 한꺼번에', () => S.setTrigger('dialog', { name: 'import' })))
  } else {
    box.appendChild(el('b', null, '고칠 호기를 먼저 불러옵니다'))
    box.appendChild(el('span', 'emg-muted', '위 칸에 설비명을 치거나, 메일·엑셀의 설비명 목록을 붙여 넣거나, 공정으로 불러옵니다.'))
    const alerts = button('emg-btn', '일정 확인 필요 ' + alertIds.length.toLocaleString() + '대 불러오기', () => load(S, 'alerts', alertIds, [], '일정 확인 필요'))
    alerts.disabled = !alertIds.length
    buttons.appendChild(alerts)
    const all = button('emg-btn', '전체 ' + total.toLocaleString() + '대 불러오기', () => load(S, 'all', [], [], '전체'))
    all.disabled = !total
    buttons.appendChild(all)
  }
  box.appendChild(buttons)
  return box
}

function load(S, kind, ids, missing, label, extra) {
  S.setTrigger('load', Object.assign({ kind, ids: ids.slice(), missing: missing.slice(0, 50), label }, extra || {}))
}

function searchBox(S, model) {
  const wrap = el('div', 'emg-search-wrap')
  const box = el('label', 'emg-search')
  const glyph = el('span')
  glyph.innerHTML = ICONS.search
  box.appendChild(glyph)
  const input = el('input')
  input.type = 'text'
  input.value = S.query
  input.placeholder = '설비명으로 불러오기 — 일부만 쳐도 되고(WBA), 여러 대는 쉼표·줄바꿈(엑셀 한 열 붙여넣기)'
  input.setAttribute('aria-label', '설비명으로 불러오기')
  input.autocomplete = 'off'
  input.dataset.fk = 'search'
  S.searchInput = input
  box.appendChild(input)
  const go = button('emg-btn is-small is-primary', '불러오기', () => loadQuery(S, model))
  go.disabled = !S.query.trim()
  S.searchGo = go
  const list = el('div', 'emg-pop is-full')
  S.searchList = list
  list.setAttribute('role', 'listbox')
  list.setAttribute('aria-label', '맞는 설비명')
  const paintSuggestions = () => {
    list.textContent = ''
    const query = S.query.trim()
    go.disabled = !query
    if (!query || isNameList(S.query) || S.pop !== 'search') {
      list.hidden = true
      return
    }
    const matched = matchNames(query, model.names)
    if (!matched.found.length) {
      list.hidden = true
      return
    }
    const loaded = new Set(S.data.loaded || [])
    matched.found.slice(0, 8).forEach((index, order) => {
      const option = button('emg-option' + (S.suggest === order ? ' is-active' : ''))
      option.setAttribute('role', 'option')
      option.appendChild(el('b', null, model.names[index]))
      const row = model.columns.length ? describeIndex(model, index) : ''
      option.appendChild(el('span', 'emg-muted', row))
      if (loaded.has(model.ids[index])) option.appendChild(el('span', 'emg-tail', '불러옴'))
      option.addEventListener('mousedown', (event) => event.preventDefault())
      option.addEventListener('click', () => {
        clearSearch(S)
        load(S, 'names', [model.ids[index]], [], model.names[index])
      })
      list.appendChild(option)
    })
    if (matched.found.length > 1) {
      const all = button('emg-option')
      all.appendChild(el('b', null, '맞는 ' + matched.found.length.toLocaleString() + '대 모두 불러오기'))
      all.appendChild(el('span', 'emg-tail', 'Enter'))
      all.addEventListener('mousedown', (event) => event.preventDefault())
      all.addEventListener('click', () => loadQuery(S, model))
      list.appendChild(all)
    }
    list.hidden = false
  }
  input.addEventListener('input', () => {
    S.query = input.value
    S.pop = 'search'
    S.suggest = -1
    paintSuggestions()
  })
  input.addEventListener('focus', () => {
    S.pop = 'search'
    paintSuggestions()
  })
  input.addEventListener('blur', () => {
    if (S.painting) return
    if (S.pop === 'search') S.pop = null
    list.hidden = true
  })
  input.addEventListener('paste', (event) => {
    const text = (event.clipboardData && event.clipboardData.getData('text/plain')) || ''
    if (!/[\r\n\t]/.test(text.trim())) return
    event.preventDefault()
    S.query = splitNames(text.replace(/\r/g, '')).join(', ')
    input.value = S.query
    paintSuggestions()
  })
  input.addEventListener('keydown', (event) => {
    stopKeys(event)
    const options = list.hidden ? [] : Array.from(list.querySelectorAll('.emg-option'))
    if (event.key === 'Enter') {
      event.preventDefault()
      if (S.suggest >= 0 && options[S.suggest]) options[S.suggest].click()
      else loadQuery(S, model)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      S.query = ''
      input.value = ''
      paintSuggestions()
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && options.length) {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      S.suggest = (S.suggest + step + options.length) % options.length
      paintSuggestions()
    }
  })
  wrap.appendChild(box)
  box.appendChild(go)
  wrap.appendChild(list)
  paintSuggestions()
  return wrap
}

function describeIndex(model, index) {
  const columns = model.conds.columns || []
  const value = (name) => {
    const k = columns.indexOf(name)
    if (k < 0) return ''
    return (model.conds.values[k] || [])[model.columns[k][index]] || ''
  }
  return [value('공정소분류'), (value('동') + ' ' + value('층')).trim()].filter(Boolean).join(' · ')
}

function loadQuery(S, model) {
  const query = S.query.trim()
  if (!query) return
  const matched = matchNames(query, model.names)
  const label = matched.list ? '설비명 목록' : '「' + query + '」'
  clearSearch(S)
  S.refocus = 'search'
  load(S, 'names', matched.found.map((index) => model.ids[index]), matched.missing, label)
}

function popover(S, name, label, build, wide) {
  const wrap = el('div', 'emg-pop-wrap')
  const toggle = button('emg-btn', label + ' ', () => {
    S.pop = S.pop === name ? null : name
    paint()
  })
  const caret = el('span')
  caret.innerHTML = ICONS.down
  toggle.appendChild(caret)
  toggle.setAttribute('aria-haspopup', 'dialog')
  const panel = el('div', 'emg-pop' + (wide ? ' is-wide' : ''))
  panel.setAttribute('role', 'dialog')
  panel.setAttribute('aria-label', label)
  panel.addEventListener('keydown', (event) => {
    stopKeys(event)
    if (event.key === 'Escape') {
      S.pop = null
      paint()
      toggle.focus()
    }
  })
  const paint = () => {
    const open = S.pop === name
    // 고르는 칸을 바꾸면 패널을 다시 짓는다 — 쓰던 칸(data-fk)에 초점을 돌려줘 키보드로 이어 쓴다.
    const saved = captureFocus(panel)
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false')
    panel.hidden = !open
    panel.textContent = ''
    panel.style.left = ''
    if (!open) return
    build(panel, paint)
    const rect = panel.getBoundingClientRect()
    const shift = popoverShift(rect.left, rect.width, document.documentElement.clientWidth, 8)
    if (shift) panel.style.left = shift + 'px'
    restoreFocus(panel, saved)
  }
  wrap.appendChild(toggle)
  wrap.appendChild(panel)
  paint()
  return wrap
}

function processPopover(S, model) {
  return popover(S, 'process', '공정으로 불러오기', (panel) => {
    const find = el('input', 'emg-input')
    find.placeholder = '공정 이름 찾기'
    find.setAttribute('aria-label', '공정 이름 찾기')
    find.value = S.procQuery
    find.dataset.fk = 'proc'
    panel.appendChild(find)
    const list = el('div', 'emg-pop-list')
    panel.appendChild(list)
    const k = (model.conds.columns || []).indexOf('공정소분류')
    const paintList = () => {
      list.textContent = ''
      const needle = S.procQuery.trim().toLowerCase()
      for (const [label, count] of S.data.processes || []) {
        if (needle && !String(label).toLowerCase().includes(needle)) continue
        const option = button('emg-option', null, () => {
          const value = label === '(빈칸)' ? '' : label
          const code = k < 0 ? -1 : (model.conds.values[k] || []).indexOf(value)
          const rows = code < 0 ? [] : matchConditions(model.columns, [{ col: k, value: code }], model.names.length)
          S.pop = null
          load(S, 'process', rows.map((row) => model.ids[row]), [], '공정 ' + label, { process: label })
        })
        option.appendChild(el('span', null, label))
        option.appendChild(el('span', 'emg-tail', Number(count).toLocaleString() + '대'))
        list.appendChild(option)
      }
    }
    find.addEventListener('input', () => {
      S.procQuery = find.value
      paintList()
    })
    paintList()
    setTimeout(() => find.focus(), 0)
  })
}

function conditionPopover(S, model) {
  const columns = model.conds.columns || []
  const values = model.conds.values || []
  return popover(S, 'conditions', '조건으로 불러오기', (panel, repaint) => {
    panel.appendChild(el('span', 'emg-muted', '칸과 값을 골라 모두 맞는 호기를 불러옵니다.'))
    S.conds = S.conds.filter((pick) => pick.col >= 0 && pick.col < columns.length)
    if (!S.conds.length) S.conds = [{ col: Math.max(columns.indexOf('동'), 0), text: null }]
    // 값은 글로 기억한다 — 목록에서 사라진 값은 비운다(번호로 기억하면 다른 값을 가리킨다).
    const resolved = resolvePicks(S.conds, values)
    resolved.forEach((pick, index) => { if (pick.value === null) S.conds[index].text = null })
    S.conds.forEach((pick, index) => {
      const line = el('div', 'emg-cond')
      const colSelect = el('select')
      colSelect.setAttribute('aria-label', '조건 칸 ' + (index + 1))
      colSelect.dataset.fk = 'cond-col-' + index
      columns.forEach((name, k) => {
        const option = el('option', null, name)
        option.value = String(k)
        option.selected = k === pick.col
        colSelect.appendChild(option)
      })
      colSelect.addEventListener('change', () => {
        pick.col = Number(colSelect.value)
        pick.text = null
        repaint()
      })
      const before = matchConditions(model.columns, resolved.slice(0, index), model.names.length)
      const counts = new Map()
      for (const row of before) {
        const code = model.columns[pick.col][row]
        counts.set(code, (counts.get(code) || 0) + 1)
      }
      const valueSelect = el('select')
      valueSelect.setAttribute('aria-label', '조건 값 ' + (index + 1))
      valueSelect.dataset.fk = 'cond-val-' + index
      const none = el('option', null, '값 고르기')
      none.value = ''
      valueSelect.appendChild(none)
      ;(values[pick.col] || []).forEach((value, code) => {
        if (!counts.has(code)) return
        const option = el('option', null, (value || '(빈칸)') + ' (' + counts.get(code).toLocaleString() + ')')
        option.value = String(code)
        option.selected = resolved[index].value === code
        valueSelect.appendChild(option)
      })
      valueSelect.addEventListener('change', () => {
        pick.text = valueSelect.value === '' ? null : String((values[pick.col] || [])[Number(valueSelect.value)])
        repaint()
      })
      line.appendChild(colSelect)
      line.appendChild(valueSelect)
      if (S.conds.length > 1) {
        const drop = icon('close', '조건 빼기', () => {
          S.conds.splice(index, 1)
          repaint()
        })
        drop.dataset.fk = 'cond-rm-' + index
        line.appendChild(drop)
      }
      panel.appendChild(line)
    })
    const actions = el('div', 'emg-row-buttons')
    if (S.conds.length < 4) {
      const more = button('emg-btn is-small', '+ 조건 더하기', () => {
        S.conds.push({ col: Math.max(columns.indexOf('Qual상태'), 0), text: null })
        repaint()
      })
      more.dataset.fk = 'cond-add'
      actions.appendChild(more)
    }
    const picked = resolvePicks(S.conds, values).filter((pick) => pick.value !== null)
    const rows = picked.length ? matchConditions(model.columns, picked, model.names.length) : []
    const go = button('emg-btn is-small is-primary', '맞는 ' + rows.length.toLocaleString() + '대 불러오기', () => {
      const label = picked.map((pick) => columns[pick.col] + ' ' + ((values[pick.col] || [])[pick.value] || '(빈칸)')).join(' · ')
      S.pop = null
      load(S, 'conditions', rows.map((row) => model.ids[row]), [], '조건 「' + label + '」')
    })
    go.dataset.fk = 'cond-go'
    go.disabled = !rows.length
    actions.appendChild(go)
    panel.appendChild(actions)
  }, true)
}

// ---------------------------------------------------------------- grid

function gridModel(S, data) {
  const columns = Array.isArray(data.columns) ? data.columns : []
  const rows = Array.isArray(data.rows) ? data.rows : []
  const sets = Array.isArray(data.colSets) ? data.colSets : []
  if (!S.colSet) S.colSet = readColSet()
  let set = sets.find((item) => item[0] === S.colSet)
  if (!set) set = sets[0] || ['all', '전체', '', columns.map((_, k) => k).filter((k) => columns[k].kind !== 'name')]
  S.colSet = set[0]
  const visible = set[3].filter((k) => columns[k] && columns[k].kind !== 'name')
  const nameCol = columns.findIndex((col) => col.kind === 'name')
  let order = rows.map((_, index) => index)
  if (S.sort) {
    const col = S.sort.col
    const kind = columns[col] ? columns[col].kind : 'text'
    const values = rows.map((row) => String((row.values || [])[col] || ''))
    order = sortOrder(values, S.sort.dir, kind)
  }
  const ordered = order.map((index) => rows[index])
  const live = ordered.filter((row) => row.tag !== 'deleted')
  return { columns, rows, ordered, live, visible, nameCol, sets, locks: lockSets(data), reasons: data.lockReasons || {} }
}

function editableIn(S, row, col) {
  const column = S.model.columns[col]
  if (!column || column.kind === 'name') return false
  return lockOf(row, col, S.model.locks) === null
}

function drawGrid(host, S, data) {
  receive(S, data)
  S.data = data
  // 새 호기 이름 바꿈(과 그 되돌리기)은 행 id 를 바꿔 목록 지문도 바꾼다 — 옮김을 먼저 얹고, 그 회차에는 고름·스크롤을
  // 처음으로 돌리지 않는다(옮길 고름이 사라진다).
  const moved = Object.entries(data.moved || {})
  for (const [from, to] of moved) {
    if (S.selected.delete(from)) S.selected.add(to)
    if (S.anchor === from) S.anchor = to
    if (S.openId === from) S.openId = to
    if (S.edit && S.edit.id === from) S.edit.id = to
    if (S.focus && S.focus.id === from) S.focus.id = to
  }
  const view = String(data.view || '')
  if (S.view !== view) {
    S.view = view
    if (!moved.length) {
      S.selected = new Set()
      S.anchor = null
      S.resetScroll = true
    }
  }
  // 상세에 연 줄의 띠는 파이썬이 아는 상세 id 를 따른다(「저장 전 변경」·고칠 것 줄로 연 호기도).
  if (Object.prototype.hasOwnProperty.call(data, 'open')) S.openId = typeof data.open === 'string' ? data.open : null
  S.model = gridModel(S, data)
  const known = new Set(S.model.live.map((row) => row.id))
  for (const id of Array.from(S.selected)) if (!known.has(id)) S.selected.delete(id)
  if (!S.skeleton) buildGridSkeleton(host, S)
  paintBar(S)
  S.repaintToast()
  paintSelection(S)
  paintHead(S)
  paintWindow(S)
  if (S.resetScroll) {
    S.resetScroll = false
    S.scroller.scrollTop = 0
  }
}

function buildGridSkeleton(host, S) {
  host.textContent = ''
  const root = el('div', 'emg-grid')
  const bar = el('div', 'emg-bar')
  const sel = el('div', 'emg-sel')
  const toast = el('div', 'emg-toast')
  toast.setAttribute('role', 'status')
  const box = el('div', 'emg-box')
  const table = el('div', 'emg-table')
  table.setAttribute('role', 'grid')
  const head = el('div', 'emg-row emg-head')
  head.setAttribute('role', 'row')
  const body = el('div', 'emg-body')
  table.appendChild(head)
  table.appendChild(body)
  box.appendChild(table)
  const foot = el('div', 'emg-foot')
  const keys = el('span', 'emg-muted', '칸을 누르면 바로 고칩니다 · Enter 확정 · Esc 취소 · Tab ↑ ↓ 옆·위아래 칸 · 엑셀 여러 칸을 칸 위에서 Ctrl+V · 칸 위 Space = 줄 고르기 · 체크 Shift+클릭 = 범위 · 줄 끝 − 는 목록에서 빼기')
  const legend = el('span', 'emg-legend')
  for (const [kind, label] of [['is-changed', '고친 칸'], ['is-error', '오류'], ['is-locked', '잠긴 칸(모듈 좌표 등)']]) {
    const item = el('span')
    item.appendChild(el('span', 'emg-swatch ' + kind))
    item.appendChild(el('span', null, label))
    legend.appendChild(item)
  }
  foot.appendChild(keys)
  foot.appendChild(legend)
  for (const part of [bar, sel, toast, box, foot]) root.appendChild(part)
  host.appendChild(root)
  Object.assign(S, { skeleton: true, root, bar, selBar: sel, toastBar: toast, scroller: box, table, head, body, foot })
  S.repaintToast = () => paintToast(S)
  listen(S, box, 'scroll', () => {
    if (S.scrollFrame) return
    S.scrollFrame = requestAnimationFrame(() => {
      S.scrollFrame = 0
      paintWindow(S)
    })
  })
  listen(S, body, 'click', (event) => onBodyClick(S, event))
  listen(S, body, 'keydown', (event) => onBodyKey(S, event))
  listen(S, body, 'paste', (event) => onPaste(S, event))
  listen(S, body, 'input', (event) => {
    if (event.target.classList.contains('emg-ed') && S.edit) S.edit.draft = event.target.value
  })
  listen(S, body, 'focusout', (event) => {
    const target = event.target
    if (S.painting || S.committing || !S.edit) return
    if (target.classList && target.classList.contains('emg-ed')) {
      commitEdit(S, null, false)
      return
    }
    // 고르는 칸 목록 밖으로 초점이 나가면 목록을 닫는다(고르지 않은 채).
    const cell = target.closest && target.closest('.emg-c[data-col]')
    if (cell && target.closest('.emg-dd') && !(event.relatedTarget && cell.contains(event.relatedTarget))) {
      const edit = S.edit
      S.edit = null
      repaintCell(S, edit.id, edit.col)
    }
  })
  listen(S, body, 'focusin', (event) => {
    const cell = event.target.closest && event.target.closest('.emg-c[data-col]')
    if (cell && !S.painting) S.focus = { id: cell.dataset.id, col: Number(cell.dataset.col) }
  })
}

function paintBar(S) {
  const bar = S.bar
  bar.textContent = ''
  const seg = el('div', 'emg-seg')
  seg.setAttribute('role', 'group')
  seg.setAttribute('aria-label', '볼 칸 묶음')
  for (const set of S.model.sets) {
    const item = button(null, set[1], () => {
      S.colSet = set[0]
      writeColSet(set[0])
      S.edit = null
      S.model = gridModel(S, S.data)
      paintBar(S)
      paintHead(S)
      paintWindow(S)
    })
    item.title = set[2]
    item.setAttribute('aria-pressed', set[0] === S.colSet ? 'true' : 'false')
    seg.appendChild(item)
  }
  bar.appendChild(seg)
  const legend = el('div', 'emg-legend')
  const scenario = ((S.data.scenario || {}).name) || '지금 설비 시나리오'
  const left = el('span')
  left.appendChild(el('span', 'emg-scope is-scenario', '시나리오'))
  left.appendChild(el('span', null, ' ' + scenario + '에만 저장'))
  const right = el('span')
  right.appendChild(el('span', 'emg-scope', '공통'))
  right.appendChild(el('span', null, ' 모든 설비 시나리오에 함께 저장'))
  legend.appendChild(left)
  legend.appendChild(right)
  bar.appendChild(legend)
}

function paintToast(S) {
  fillToast(S, S.toastBar, S.data && S.data.toast)
}

// 토스트 한 줄(표·오른쪽 칸 공용). 「되돌리기」 는 그 토스트가 가리킨 단계(toast.undo — 파이썬이 맨 위일 때만 싣는다)를
// 보낸다 — 파이썬도 그 단계가 맨 위가 아니면 되돌리지 않는다(그 사이 칸 고침이 쌓인 경합).
function fillToast(S, bar, toast) {
  bar.textContent = ''
  if (toast && toast.id !== S.lastToast) {
    // 파이썬이 새 토스트를 보냈다 — 브라우저 한 줄(붙여넣는 중 등)은 거둔다.
    S.lastToast = toast.id
    S.note = ''
  }
  const text = S.note || (toast && toast.id !== S.toastClosed ? toast.text : '')
  bar.hidden = !text
  if (!text) return
  bar.appendChild(el('span', null, text))
  if (!S.note && typeof toast.undo === 'string' && toast.undo) {
    bar.appendChild(button('emg-link', '되돌리기', () => {
      S.toastClosed = toast.id
      enqueue(S, { op: 'undo', step: toast.undo }, [])
      send(S)
      fillToast(S, bar, toast)
    }))
  }
  bar.appendChild(icon('close', '알림 닫기', () => {
    if (S.note) S.note = ''
    else S.toastClosed = toast.id
    fillToast(S, bar, toast)
  }))
}

function selectedRows(S) {
  return S.model.live.filter((row) => S.selected.has(row.id))
}

function paintSelection(S) {
  const bar = S.selBar
  const saved = captureFocus(bar)
  S.painting = true
  bar.textContent = ''
  buildSelection(S, bar)
  S.painting = false
  restoreFocus(bar, saved)
}

function buildSelection(S, bar) {
  const rows = selectedRows(S)
  bar.hidden = rows.length === 0
  if (!rows.length) return
  const columns = S.model.columns
  bar.appendChild(el('span', null, '선택 ' + rows.length.toLocaleString() + '대'))
  const pick = el('select')
  pick.setAttribute('aria-label', '값을 넣을 칸')
  columns.forEach((column, k) => {
    if (column.kind === 'name') return
    const option = el('option', null, column.name + (column.scope === 'scenario' ? ' (시나리오)' : ''))
    option.value = column.name
    option.selected = column.name === S.bulkCol
    pick.appendChild(option)
  })
  pick.dataset.fk = 'bulk-col'
  pick.addEventListener('change', () => {
    S.bulkCol = pick.value
    S.bulkValue = ''
    S.bulkChosen = false
    paintSelection(S)
  })
  pick.addEventListener('keydown', stopKeys)
  bar.appendChild(pick)
  bar.appendChild(el('span', null, '에'))
  const col = columns.findIndex((column) => column.name === S.bulkCol)
  const column = columns[col] || {}
  const locked = (row, k) => !editableIn(S, row, k)
  const ready = column.kind !== 'choice' || S.bulkChosen
  const count = () => (col < 0 || !ready ? 0 : planSet(rows, col, S.bulkValue, locked))
  const apply = button('emg-btn is-small is-primary', '', () => {
    const targets = rows.filter((row) => !locked(row, col)).map((row) => row.id)
    if (!targets.length || !ready) return
    enqueue(S, { op: 'set', ids: targets, col: column.name, text: S.bulkValue }, targets.map((id) => [id, col, S.bulkValue]))
    send(S)
    paintWindow(S)
  })
  const repaintApply = () => {
    const m = count()
    apply.textContent = '넣기 (' + m.toLocaleString() + '칸)'
    apply.disabled = m === 0
    const reason = rows.length && col >= 0 && rows.every((row) => locked(row, col)) ? S.model.reasons[lockOf(rows[0], col, S.model.locks)] : ''
    apply.title = reason || ''
  }
  if (column.kind === 'choice') {
    const chips = el('div', 'emg-chips')
    const options = (column.options || []).concat(column.blank ? [''] : [])
    for (const value of options) {
      const chip = button('emg-chip', value || '(비움)', () => {
        S.bulkValue = value
        S.bulkChosen = true
        paintSelection(S)
      })
      chip.setAttribute('aria-pressed', S.bulkChosen && S.bulkValue === value ? 'true' : 'false')
      chips.appendChild(chip)
    }
    bar.appendChild(chips)
  } else {
    const input = el('input', 'emg-input')
    input.value = S.bulkValue
    input.placeholder = column.kind === 'date' ? '2026-11-09 (비우면 지움)' : '값 (비우면 지움)'
    input.setAttribute('aria-label', '넣을 값')
    input.dataset.fk = 'bulk-value'
    input.addEventListener('input', () => {
      S.bulkValue = input.value
      repaintApply()
    })
    input.addEventListener('keydown', stopKeys)
    bar.appendChild(input)
  }
  repaintApply()
  bar.appendChild(apply)
  bar.appendChild(el('span', 'emg-vsep'))
  bar.appendChild(el('span', null, '반입·Qual 일정'))
  const days = el('input', 'emg-input emg-days')
  days.value = S.days
  days.setAttribute('aria-label', '밀 날 수')
  days.dataset.fk = 'bulk-days'
  bar.appendChild(days)
  bar.appendChild(el('span', null, '일'))
  const dateCols = columns.map((c, k) => (c.name === '반입일정' || c.name === 'Qual일정' ? k : -1)).filter((k) => k >= 0)
  const shift = button('emg-btn is-small', '', () => {
    const value = parseDays(S.days)
    if (value === null) return
    const targets = rows.map((row) => row.id)
    const cells = []
    for (const row of rows) for (const k of dateCols) if (!locked(row, k) && shiftIso(String(row.values[k] || ''), value)) cells.push([row.id, k, shiftIso(String(row.values[k]), value)])
    enqueue(S, { op: 'shift', ids: targets, days: value }, cells)
    send(S)
    paintWindow(S)
  })
  const repaintShift = () => {
    const k = planShift(rows, dateCols, parseDays(S.days), locked)
    shift.textContent = '밀기 (' + k.toLocaleString() + '칸)'
    shift.disabled = k === 0
  }
  days.addEventListener('input', () => {
    S.days = days.value
    repaintShift()
  })
  days.addEventListener('keydown', stopKeys)
  repaintShift()
  bar.appendChild(shift)
  bar.appendChild(el('span', 'emg-vsep'))
  const lock = S.data.deleteLock
  const deletable = rows.filter((row) => !(lock && row.tag !== 'new'))
  const remove = button('emg-btn is-small is-danger', '선택 ' + rows.length.toLocaleString() + '대 지우기', () => {
    enqueue(S, { op: 'delete', ids: rows.map((row) => row.id) }, [])
    S.selected = new Set()
    send(S)
    paintSelection(S)
  })
  remove.disabled = deletable.length === 0
  if (lock) remove.title = lock
  bar.appendChild(remove)
  bar.appendChild(button('emg-btn is-small is-ghost', '선택 풀기', () => {
    S.selected = new Set()
    S.anchor = null
    paintSelection(S)
    paintWindow(S)
  }))
}

function headCell(S, k) {
  const column = S.model.columns[k]
  const cell = el('div', 'emg-c emg-w-' + column.width + (column.scope === 'scenario' ? ' is-scenario' : ''))
  cell.setAttribute('role', 'columnheader')
  cell.setAttribute('aria-colindex', String(k + 1))
  const sort = S.sort && S.sort.col === k ? (S.sort.dir === 'asc' ? ' ▲' : ' ▼') : ''
  const press = button('emg-hb', null, () => toggleSort(S, k))
  press.appendChild(el('span', null, column.name + sort))
  if (column.scope === 'scenario') press.appendChild(el('small', null, '시나리오'))
  press.title = (column.help || '') + ' · 눌러서 정렬'
  if (S.sort && S.sort.col === k) cell.setAttribute('aria-sort', S.sort.dir === 'asc' ? 'ascending' : 'descending')
  cell.appendChild(press)
  return cell
}

function toggleSort(S, k) {
  const current = S.sort
  if (!current || current.col !== k) S.sort = { col: k, dir: 'asc' }
  else if (current.dir === 'asc') S.sort = { col: k, dir: 'desc' }
  else S.sort = null
  S.model = gridModel(S, S.data)
  paintHead(S)
  paintWindow(S)
}

function paintHead(S) {
  const head = S.head
  head.textContent = ''
  const model = S.model
  S.table.setAttribute('aria-rowcount', String(model.ordered.length + 1))
  S.table.setAttribute('aria-colcount', String(model.visible.length + 1))
  const check = el('div', 'emg-c emg-w-chk emg-c-chk')
  const all = el('input')
  all.type = 'checkbox'
  all.setAttribute('aria-label', '불러온 호기 모두 고르기')
  all.checked = model.live.length > 0 && model.live.every((row) => S.selected.has(row.id))
  all.addEventListener('change', () => {
    const on = !(model.live.length > 0 && model.live.every((row) => S.selected.has(row.id)))
    S.selected = on ? new Set(model.live.map((row) => row.id)) : new Set()
    S.anchor = null
    paintHead(S)
    paintSelection(S)
    paintWindow(S)
  })
  check.appendChild(all)
  head.appendChild(check)
  if (model.nameCol >= 0) {
    const name = headCell(S, model.nameCol)
    name.classList.add('emg-c-name')
    head.appendChild(name)
  }
  for (const k of model.visible) head.appendChild(headCell(S, k))
  head.appendChild(el('div', 'emg-c emg-w-rm'))
  const empty = model.ordered.length === 0
  S.scroller.hidden = empty
  S.foot.hidden = empty
  S.bar.hidden = empty
  S.selBar.hidden = empty || S.selBar.hidden
  S.root.classList.toggle('is-empty', empty)
}

function paintWindow(S) {
  const model = S.model
  const body = S.body
  const total = model.ordered.length
  const viewport = S.scroller.clientHeight || 600
  const start = Math.max(Math.floor(S.scroller.scrollTop / ROW_H) - BUFFER_ROWS, 0)
  const end = Math.min(start + Math.ceil(viewport / ROW_H) + BUFFER_ROWS * 2, total)
  const active = activeIn(body)
  const hadFocus = active && body.contains(active)
  const caret = active && active.classList && active.classList.contains('emg-ed') ? [active.selectionStart, active.selectionEnd] : null
  S.painting = true
  body.style.paddingTop = start * ROW_H + 'px'
  body.style.height = total * ROW_H + 'px'
  body.textContent = ''
  for (let index = start; index < end; index += 1) body.appendChild(rowElement(S, model.ordered[index], index))
  if (!body.querySelector('[tabindex="0"]')) {
    const first = body.querySelector('.emg-name')
    if (first) first.tabIndex = 0
  }
  S.painting = false
  if (hadFocus || S.wantFocus) {
    S.wantFocus = false
    focusTarget(S, caret)
  }
}

function repaintCell(S, id, col) {
  const node = S.body.querySelector('.emg-c[data-id="' + cssEscape(id) + '"][data-col="' + col + '"]')
  const row = S.model.rows.find((item) => item.id === id)
  if (!node || !row) return
  S.painting = true
  node.replaceWith(cellElement(S, row, col))
  S.painting = false
}

function focusTarget(S, caret) {
  if (S.edit) {
    const input = S.body.querySelector('.emg-ed')
    if (input) {
      input.focus()
      if (caret && caret[0] !== null) input.setSelectionRange(caret[0], caret[1])
      else if (S.edit.selectAll) {
        input.select()
        S.edit.selectAll = false
      }
      return
    }
    const option = S.body.querySelector('.emg-dd button.is-active') || S.body.querySelector('.emg-dd button')
    if (option) option.focus()
    return
  }
  if (S.focus) {
    const cell = S.body.querySelector('[data-id="' + cssEscape(S.focus.id) + '"][data-col="' + S.focus.col + '"] button')
    if (cell) cell.focus()
  }
}

function rowElement(S, row, index) {
  const model = S.model
  const tag = row.tag || ''
  const node = el('div', 'emg-row')
  node.setAttribute('role', 'row')
  node.setAttribute('aria-rowindex', String(index + 2))
  if (S.selected.has(row.id)) node.classList.add('is-selected')
  if (tag === 'new') node.classList.add('is-new')
  if (tag === 'deleted') node.classList.add('is-deleted')
  if (S.openId === row.id) node.classList.add('is-open')
  const values = row.values || []
  const name = values[model.nameCol] || ''
  const check = el('div', 'emg-c emg-w-chk emg-c-chk')
  if (tag === 'deleted') {
    const back = icon('undo', name + ' 되살리기', () => {
      enqueue(S, { op: 'restore', ids: [row.id] }, [])
      send(S)
    })
    back.title = '되살리기'
    back.tabIndex = -1
    check.appendChild(back)
  } else {
    const box = el('input')
    box.type = 'checkbox'
    box.checked = S.selected.has(row.id)
    box.setAttribute('aria-label', (name || '새 호기') + ' 고르기')
    box.dataset.check = row.id
    // 표 본문의 Tab 정지는 초점 칸 하나다(로빙) — 줄 고르기는 칸 위 Space 로 닿는다.
    box.tabIndex = -1
    check.appendChild(box)
  }
  node.appendChild(check)
  const nameCell = el('div', 'emg-c emg-w-name emg-c-name')
  nameCell.dataset.id = row.id
  nameCell.dataset.col = String(model.nameCol)
  const errors = row.errors || {}
  const changed = row.changed || {}
  if (errors[model.nameCol] !== undefined) nameCell.classList.add('is-error')
  if (changed[model.nameCol] !== undefined) nameCell.classList.add('is-changed')
  const open = button('emg-name')
  open.dataset.open = row.id
  open.tabIndex = S.focus && S.focus.id === row.id && S.focus.col === model.nameCol ? 0 : -1
  open.appendChild(el('span', 'emg-name-text', name || '(설비명 없음)'))
  if (row.alert) {
    const dot = el('span', 'emg-alert')
    dot.title = row.alert
    open.appendChild(dot)
  }
  if (tag === 'new') open.appendChild(el('span', 'emg-tag is-new', '새 호기'))
  if (tag === 'deleted') open.appendChild(el('span', 'emg-tag is-deleted', '지움'))
  const nameTip = [errors[model.nameCol] !== undefined ? '오류: ' + errors[model.nameCol] : '', changed[model.nameCol] !== undefined ? '저장본: ' + changed[model.nameCol] : '', row.alert || '', '누르면 오른쪽에 이 호기의 모든 칸이 열립니다']
  open.title = nameTip.filter(Boolean).join('\n')
  open.setAttribute('aria-label', (name || '새 호기') + ' 상세 열기')
  nameCell.appendChild(open)
  node.appendChild(nameCell)
  model.visible.forEach((k) => node.appendChild(cellElement(S, row, k)))
  const rm = el('div', 'emg-c emg-w-rm')
  const unload = icon('minus', '목록에서 빼기 (지우는 것이 아닙니다)', () => {
    S.selected.delete(row.id)
    S.setTrigger('unload', { view: S.view, ids: [row.id] })
  })
  unload.tabIndex = -1
  rm.appendChild(unload)
  node.appendChild(rm)
  return node
}

function cellElement(S, row, k) {
  const model = S.model
  const column = model.columns[k]
  const cell = el('div', 'emg-c emg-w-' + column.width)
  cell.setAttribute('role', 'gridcell')
  cell.setAttribute('aria-colindex', String(k + 1))
  cell.dataset.id = row.id
  cell.dataset.col = String(k)
  const lock = lockOf(row, k, model.locks)
  const pending = pendingText(S, row.id, k)
  const value = pending !== null ? pending : String((row.values || [])[k] || '')
  if ((row.changed || {})[k] !== undefined) cell.classList.add('is-changed')
  if ((row.errors || {})[k] !== undefined) cell.classList.add('is-error')
  if ((row.warns || {})[k] !== undefined) cell.classList.add('is-warn')
  if (lock) cell.classList.add('is-locked')
  if (pending !== null) cell.classList.add('is-pending')
  cell.title = cellTip(row, k, model.columns, model.reasons, lock)
  const editing = S.edit && S.edit.id === row.id && S.edit.col === k
  const label = ((row.values || [])[model.nameCol] || '새 호기') + ' ' + column.name + ' ' + (value || '빈칸')
  if (editing && column.kind !== 'choice') {
    cell.classList.add('is-editing')
    const input = el('input', 'emg-ed')
    input.value = S.edit.draft
    input.placeholder = column.kind === 'date' ? '2026-11-09' : ''
    input.setAttribute('aria-label', label)
    cell.appendChild(input)
    return cell
  }
  const press = button('emg-cb', value)
  press.tabIndex = S.focus && S.focus.id === row.id && S.focus.col === k ? 0 : -1
  press.setAttribute('aria-label', label)
  cell.appendChild(press)
  if (editing) {
    cell.classList.add('is-editing')
    const list = el('div', 'emg-dd')
    list.setAttribute('role', 'listbox')
    const options = (column.options || []).concat(column.blank ? [''] : [])
    options.forEach((option, index) => {
      const item = button(index === S.edit.active ? 'is-active' : null, option || '(비움)')
      item.dataset.pick = option
      item.setAttribute('aria-pressed', option === value ? 'true' : 'false')
      item.setAttribute('role', 'option')
      list.appendChild(item)
    })
    const close = button(null, '닫기')
    close.dataset.close = '1'
    list.appendChild(close)
    cell.appendChild(list)
  }
  return cell
}

function cellAt(S, id, col) {
  const model = S.model
  const rowIndex = model.live.findIndex((row) => row.id === id)
  const colIndex = model.visible.indexOf(col)
  return { row: rowIndex, col: colIndex }
}

function startEdit(S, id, col, initial) {
  const row = S.model.rows.find((item) => item.id === id)
  if (!row || !editableIn(S, row, col)) return
  const column = S.model.columns[col]
  const pending = pendingText(S, id, col)
  const current = pending !== null ? pending : String((row.values || [])[col] || '')
  const options = (column.options || []).concat(column.blank ? [''] : [])
  S.edit = { id, col, draft: initial !== undefined ? initial : current, original: current, selectAll: initial === undefined, active: Math.max(options.indexOf(current), 0) }
  S.focus = { id, col }
  S.wantFocus = true
  paintWindow(S)
}

function commitEdit(S, move, refocus) {
  const edit = S.edit
  if (!edit) return
  S.committing = true
  if (edit.draft !== edit.original) {
    const column = S.model.columns[edit.col]
    enqueue(S, { op: 'cell', id: edit.id, col: column.name, text: edit.draft }, [[edit.id, edit.col, edit.draft]])
    schedule(S)
  }
  S.edit = null
  let target = null
  if (move) {
    const live = S.model.live
    const from = cellAt(S, edit.id, edit.col)
    if (from.row >= 0 && from.col >= 0) {
      const next = nextCell(live.length, S.model.visible.length, from, move, (r, c) => editableIn(S, live[r], S.model.visible[c]), 80)
      if (next) target = { id: live[next.row].id, col: S.model.visible[next.col] }
    }
  }
  S.committing = false
  if (target) {
    ensureVisible(S, target.id)
    startEdit(S, target.id, target.col)
    return
  }
  if (refocus === false) {
    // 다른 칸을 눌러 초점이 빠졌다 — 그 칸만 바꿔야 누른 칸의 click 이 그대로 닿는다.
    repaintCell(S, edit.id, edit.col)
    return
  }
  S.wantFocus = true
  paintWindow(S)
}

function pickChoice(S, value) {
  const edit = S.edit
  if (!edit) return
  edit.draft = value
  commitEdit(S, null, true)
}

function ensureVisible(S, id) {
  const index = S.model.ordered.findIndex((row) => row.id === id)
  if (index < 0) return
  const top = index * ROW_H
  const box = S.scroller
  const headH = 42
  if (top < box.scrollTop) box.scrollTop = top
  else if (top + ROW_H + headH > box.scrollTop + box.clientHeight) box.scrollTop = top + ROW_H + headH - box.clientHeight
}

function onBodyClick(S, event) {
  const target = event.target
  const check = target.closest('[data-check]')
  if (check) {
    toggleRow(S, check.dataset.check, event.shiftKey)
    return
  }
  const open = target.closest('[data-open]')
  if (open) {
    S.openId = open.dataset.open
    // 띠는 누른 회차에 바로 — 상세를 여는 회차는 표 data 가 같을 수 있어 다시 그려지기를 기다리지 않는다.
    for (const row of S.body.querySelectorAll('.emg-row.is-open')) row.classList.remove('is-open')
    const line = open.closest('.emg-row')
    if (line) line.classList.add('is-open')
    S.setTrigger('open', { view: S.view, id: open.dataset.open })
    return
  }
  const pick = target.closest('[data-pick]')
  if (pick) {
    pickChoice(S, pick.dataset.pick)
    return
  }
  if (target.closest('[data-close]')) {
    S.edit = null
    S.wantFocus = true
    paintWindow(S)
    return
  }
  const cell = target.closest('.emg-c[data-col]')
  if (!cell || cell.querySelector('.emg-ed')) return
  const col = Number(cell.dataset.col)
  if (col === S.model.nameCol) return
  startEdit(S, cell.dataset.id, col)
}

function toggleRow(S, id, shift) {
  const live = S.model.live
  const index = live.findIndex((row) => row.id === id)
  const on = !S.selected.has(id)
  const anchor = S.anchor ? live.findIndex((row) => row.id === S.anchor) : -1
  if (shift && anchor >= 0 && index >= 0) {
    for (let k = Math.min(anchor, index); k <= Math.max(anchor, index); k += 1) {
      if (on) S.selected.add(live[k].id)
      else S.selected.delete(live[k].id)
    }
  } else if (on) S.selected.add(id)
  else S.selected.delete(id)
  S.anchor = id
  paintHead(S)
  paintSelection(S)
  paintWindow(S)
}

function onBodyKey(S, event) {
  const target = event.target
  stopKeys(event)
  if (target.classList.contains('emg-ed')) {
    const key = event.key
    if (key === 'Enter') {
      event.preventDefault()
      commitEdit(S, null, true)
    } else if (key === 'Escape') {
      event.preventDefault()
      S.edit = null
      S.wantFocus = true
      paintWindow(S)
    } else if (key === 'Tab') {
      event.preventDefault()
      commitEdit(S, event.shiftKey ? 'left' : 'right', true)
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault()
      commitEdit(S, key === 'ArrowDown' ? 'down' : 'up', true)
    }
    return
  }
  if (S.edit && target.closest('.emg-dd')) {
    const column = S.model.columns[S.edit.col]
    const options = (column.options || []).concat(column.blank ? [''] : [])
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      S.edit.active = (S.edit.active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length
      S.wantFocus = true
      paintWindow(S)
    } else if (event.key === 'Enter' && target.dataset.pick === undefined && !target.dataset.close) {
      event.preventDefault()
      pickChoice(S, options[S.edit.active])
    } else if (event.key === 'Escape') {
      event.preventDefault()
      S.edit = null
      S.wantFocus = true
      paintWindow(S)
    }
    return
  }
  const cell = target.closest('.emg-c[data-col]')
  if (!cell) return
  const id = cell.dataset.id
  const col = Number(cell.dataset.col)
  const model = S.model
  const live = model.live
  const moves = { ArrowRight: 'right', ArrowLeft: 'left', ArrowDown: 'down', ArrowUp: 'up' }
  if (moves[event.key]) {
    event.preventDefault()
    const columns = [model.nameCol].concat(model.visible)
    const from = { row: live.findIndex((row) => row.id === id), col: columns.indexOf(col) }
    const next = nextCell(live.length, columns.length, from, moves[event.key], () => true, 1)
    if (next) {
      S.focus = { id: live[next.row].id, col: columns[next.col] }
      ensureVisible(S, S.focus.id)
      S.wantFocus = true
      paintWindow(S)
    }
    return
  }
  if (event.key === ' ' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Space = 그 줄 고르기(Shift+Space 는 기준 줄부터 범위) — 체크 칸은 Tab 정지가 아니다.
    event.preventDefault()
    if (live.some((row) => row.id === id)) toggleRow(S, id, event.shiftKey)
    return
  }
  if (col === model.nameCol) return
  if (event.key === 'Enter' || event.key === 'F2') {
    event.preventDefault()
    startEdit(S, id, col)
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const column = model.columns[col]
    if (column.kind === 'choice') return
    event.preventDefault()
    startEdit(S, id, col, event.key)
  }
}

function onPaste(S, event) {
  const cell = event.target.closest('.emg-c[data-col]')
  if (!cell) return
  const text = (event.clipboardData && event.clipboardData.getData('text/plain')) || ''
  const cells = parseClipboard(text)
  const id = cell.dataset.id
  const col = Number(cell.dataset.col)
  const model = S.model
  const onName = col === model.nameCol
  if (!cells) {
    if (event.target.classList.contains('emg-ed')) return
    event.preventDefault()
    if (onName) {
      showNote(S, NAME_PASTE_NOTE)
      return
    }
    const row = model.rows.find((item) => item.id === id)
    if (!row || !editableIn(S, row, col)) return
    enqueue(S, { op: 'cell', id, col: model.columns[col].name, text: text.replace(/\r?\n$/, '') }, [[id, col, text]])
    schedule(S)
    paintWindow(S)
    return
  }
  event.preventDefault()
  const live = model.live
  // 설비명 칸에서 붙이면(엑셀에서 설비명 열부터 잡은 흔한 꼴) 설비명 열은 넣지 못한 칸으로 세고 옆 칸부터 편다.
  const order = onName ? [model.nameCol].concat(model.visible) : model.visible
  const start = { row: live.findIndex((row) => row.id === id), col: order.indexOf(col) }
  if (start.row < 0 || start.col < 0) return
  const names = order.map((k) => model.columns[k].name)
  const byName = new Map(order.map((k) => [model.columns[k].name, k]))
  const byId = new Map(live.map((row) => [row.id, row]))
  const plan = planPaste(cells, start.row, start.col, live.map((row) => row.id), names, (rowId, name) => editableIn(S, byId.get(rowId), byName.get(name)), Number((S.data.limits || {}).pasteCells) || 5000)
  if (plan.tooMany) {
    showNote(S, '한 번에 ' + (Number((S.data.limits || {}).pasteCells) || 5000).toLocaleString() + '칸까지 붙입니다 — 더 많으면 「엑셀·CSV로 한꺼번에」 를 씁니다')
    return
  }
  S.edit = null
  const pendingCells = []
  plan.rows.forEach((line, r) => line.forEach((value, c) => {
    if (value !== null) pendingCells.push([plan.ids[r], byName.get(plan.cols[c]), value])
  }))
  enqueue(S, { op: 'paste', ids: plan.ids, cols: plan.cols, rows: plan.rows, cut: plan.cut, skipped: plan.skipped }, pendingCells)
  showNote(S, '붙여넣는 중 — ' + cells.length.toLocaleString() + '줄')
  send(S)
  S.wantFocus = true
  paintWindow(S)
}

// ---------------------------------------------------------------- side

function drawSide(host, S, data) {
  receive(S, data)
  S.data = data
  const saved = captureFocus(host)
  S.painting = true
  host.textContent = ''
  const root = el('div', 'emg-side')
  host.appendChild(root)
  // 이 마운트가 보낸 조작(상세 「이 호기 지우기」·칸·호기 되돌리기)의 토스트는 이 마운트가 그린다.
  const toast = el('div', 'emg-toast')
  toast.setAttribute('role', 'status')
  root.appendChild(toast)
  S.repaintToast = () => fillToast(S, toast, S.data && S.data.toast)
  S.repaintToast()
  if (data.panel === 'changes') drawChanges(S, root, data)
  else drawDetail(S, root, data)
  S.painting = false
  restoreFocus(host, saved)
  if (!S.sideBound) {
    S.sideBound = true
    listen(S, host, 'keydown', stopKeys)
  }
}

function drawDetail(S, root, data) {
  const unit = data.unit
  if (!unit) {
    S.unitId = null
    S.drafts.clear()
    root.appendChild(el('p', 'emg-side-empty', '표에서 설비명을 누르면 그 호기의 모든 칸이 여기 한 장에 펼쳐집니다.'))
    return
  }
  if (S.unitId !== unit.id) {
    S.unitId = unit.id
    S.drafts.clear()
    S.pending.clear()
  }
  const columns = Array.isArray(data.columns) ? data.columns : []
  const nameCol = columns.findIndex((column) => column.kind === 'name')
  const values = unit.values || []
  const sets = lockSets(data)
  const reasons = data.lockReasons || {}
  const head = el('div', 'emg-side-head')
  head.appendChild(el('div', 'emg-side-name', values[nameCol] || '(설비명 없음)'))
  if (unit.meta) head.appendChild(el('div', 'emg-muted', unit.meta))
  if (unit.tag === 'deleted') head.appendChild(el('span', 'emg-tag is-deleted', '지울 목록'))
  if (unit.tag === 'new') head.appendChild(el('span', 'emg-tag is-new', '새 호기'))
  root.appendChild(head)
  for (const group of data.groups || []) {
    const box = el('div', 'emg-side-group')
    const title = el('h4')
    title.appendChild(el('span', null, group[1]))
    title.appendChild(el('span', 'emg-scope' + (group[2] === 'scenario' ? ' is-scenario' : ''), group[2] === 'scenario' ? '시나리오' : '공통'))
    if (group[3]) title.appendChild(el('span', null, group[3]))
    box.appendChild(title)
    const fields = el('div', 'emg-fields')
    for (const k of group[4] || []) if (columns[k]) fields.appendChild(detailField(S, unit, columns[k], k, sets, reasons))
    box.appendChild(fields)
    root.appendChild(box)
  }
  const downtime = el('div', 'emg-side-group')
  const title = el('h4')
  title.appendChild(el('span', null, '그 호기의 비가동 일정'))
  title.appendChild(el('span', 'emg-scope is-scenario', '시나리오'))
  downtime.appendChild(title)
  const rows = Array.isArray(unit.downtime) ? unit.downtime : []
  if (!rows.length) downtime.appendChild(el('span', 'emg-muted', '없음'))
  else {
    const table = el('table', 'emg-mini')
    const headRow = el('tr')
    for (const label of ['유형', '시작일', '종료일', '상세사유']) headRow.appendChild(el('th', null, label))
    table.appendChild(headRow)
    for (const line of rows) {
      const tr = el('tr')
      for (const value of line) tr.appendChild(el('td', null, value))
      table.appendChild(tr)
    }
    downtime.appendChild(table)
  }
  if (unit.tag !== 'deleted') {
    downtime.appendChild(button('emg-link', '비가동 일정 표에서 고치기', () => S.setTrigger('goto', { table: '비가동 일정', unit: values[nameCol] || '' })))
  }
  root.appendChild(downtime)
  const actions = el('div', 'emg-side-actions')
  if (unit.tag === 'deleted') {
    actions.appendChild(button('emg-btn', '되살리기', () => {
      enqueue(S, { op: 'restore', ids: [unit.id] }, [])
      send(S)
    }))
  } else {
    const remove = button('emg-btn is-danger', '이 호기 지우기', () => {
      enqueue(S, { op: 'delete', ids: [unit.id] }, [])
      send(S)
    })
    remove.disabled = !unit.deletable
    if (unit.deleteLock) remove.title = unit.deleteLock
    actions.appendChild(remove)
  }
  root.appendChild(actions)
}

function detailField(S, unit, column, k, sets, reasons) {
  const field = el('div', 'emg-field' + (column.kind === 'memo' ? ' is-wide' : ''))
  const lock = lockOf(unit, k, sets)
  const values = unit.values || []
  const pending = pendingText(S, unit.id, k)
  const shown = pending !== null ? pending : String(values[k] || '')
  const error = (unit.errors || {})[k]
  const warn = (unit.warns || {})[k]
  const changed = (unit.changed || {})[k]
  if (changed !== undefined) field.classList.add('is-changed')
  if (error !== undefined) field.classList.add('is-error')
  if (pending !== null) field.classList.add('is-pending')
  const id = 'emg-f-' + S.mount + '-' + k
  const label = el('label', null, column.name)
  label.htmlFor = id
  field.appendChild(label)
  const tips = []
  if (lock) tips.push(reasons[lock] || '')
  if (changed !== undefined) tips.push('저장본: ' + (changed || '(빈칸)'))
  tips.push(column.help || '')
  field.title = tips.filter(Boolean).join('\n')
  const commit = (text) => {
    if (text === shown) return
    enqueue(S, { op: 'cell', id: unit.id, col: column.name, text }, [[unit.id, k, text]])
    schedule(S)
  }
  if (column.kind === 'choice' && !lock) {
    const chips = el('div', 'emg-chips')
    chips.setAttribute('role', 'group')
    chips.setAttribute('aria-label', column.name)
    const options = (column.options || []).concat(column.blank ? [''] : [])
    for (const value of options) {
      const chip = button('emg-chip', value || '(비움)', () => {
        commit(value)
        S.drafts.delete(k)
        send(S)
      })
      chip.setAttribute('aria-pressed', value === shown ? 'true' : 'false')
      chips.appendChild(chip)
    }
    field.appendChild(chips)
  } else {
    const input = el('input', 'emg-input')
    input.id = id
    input.dataset.fk = 'f' + k
    input.value = S.drafts.has(k) ? S.drafts.get(k) : shown
    input.disabled = Boolean(lock)
    if (column.kind === 'date') input.placeholder = '2026-11-09'
    input.addEventListener('input', () => S.drafts.set(k, input.value))
    input.addEventListener('keydown', (event) => {
      stopKeys(event)
      if (event.key === 'Enter') {
        event.preventDefault()
        commit(input.value)
        S.drafts.delete(k)
        send(S)
      } else if (event.key === 'Escape') {
        event.preventDefault()
        S.drafts.delete(k)
        input.value = shown
      }
    })
    input.addEventListener('blur', () => {
      if (S.painting || !S.drafts.has(k)) return
      const text = S.drafts.get(k)
      S.drafts.delete(k)
      commit(text)
    })
    field.appendChild(input)
  }
  if (error !== undefined) field.appendChild(el('span', 'emg-field-error', error))
  if (warn !== undefined) field.appendChild(el('span', 'emg-field-warn', warn))
  return field
}

function drawChanges(S, root, data) {
  const counts = data.counts || {}
  const sum = el('div', 'emg-sum')
  for (const [key, label] of [['cells', '고친 칸'], ['new', '새 호기'], ['deleted', '지울 호기'], ['errors', '오류']]) {
    const cell = el('div', key === 'errors' ? 'is-error' : null)
    cell.appendChild(el('b', null, Number(counts[key] || 0).toLocaleString()))
    cell.appendChild(el('span', 'emg-muted', label))
    sum.appendChild(cell)
  }
  root.appendChild(sum)
  const errors = Array.isArray(data.errors) ? data.errors : []
  if (errors.length) {
    const sec = el('div', 'emg-sec')
    sec.appendChild(el('h4', null, '저장하기 전에 고칠 것'))
    for (const [id, name, col, message] of errors) {
      const line = button('emg-errline', null, id ? () => S.setTrigger('open', { id }) : null)
      line.disabled = !id
      if (name) line.appendChild(el('b', null, name))
      line.appendChild(el('span', null, (name ? ' · ' : '') + (col ? col + ' — ' : '') + message))
      sec.appendChild(line)
    }
    if (data.moreErrors) sec.appendChild(el('span', 'emg-muted', '외 ' + Number(data.moreErrors).toLocaleString() + '개'))
    root.appendChild(sec)
  }
  const units = Array.isArray(data.units) ? data.units : []
  if (!units.length && !data.others) {
    root.appendChild(el('p', 'emg-side-empty', '아직 고친 것이 없습니다.'))
    return
  }
  const list = el('div', 'emg-changes')
  for (const unit of units) {
    const box = el('div', 'emg-unit')
    const head = el('div', 'emg-unit-head')
    head.appendChild(button('emg-link', unit.name || '(설비명 없음)', () => S.setTrigger('open', { id: unit.id })))
    if (unit.tag === 'new') head.appendChild(el('span', 'emg-tag is-new', '새 호기'))
    if (unit.tag === 'deleted') head.appendChild(el('span', 'emg-tag is-deleted', '지움'))
    head.appendChild(el('span', 'emg-grow'))
    head.appendChild(button('emg-link', '이 호기 되돌리기', () => {
      enqueue(S, { op: 'revert', id: unit.id, col: null }, [])
      send(S)
    }))
    box.appendChild(head)
    for (const [col, scope, before, after] of unit.lines || []) {
      const line = el('div', 'emg-line')
      const label = el('span', 'emg-muted', col)
      if (scope === 'scenario') label.appendChild(el('span', 'emg-scope is-scenario', '시'))
      line.appendChild(label)
      const value = el('span', 'emg-value')
      value.appendChild(el('span', 'emg-from', before || '(빈칸)'))
      value.appendChild(el('span', null, ' → '))
      value.appendChild(el('b', null, after || '(빈칸)'))
      line.appendChild(value)
      line.appendChild(icon('undo', col + ' 되돌리기', () => {
        enqueue(S, { op: 'revert', id: unit.id, col }, [])
        send(S)
      }))
      box.appendChild(line)
    }
    list.appendChild(box)
  }
  if (data.moreLines) list.appendChild(el('p', 'emg-side-empty', '외 ' + Number(data.moreLines).toLocaleString() + '칸'))
  root.appendChild(list)
  if (data.others) root.appendChild(el('div', 'emg-sec', data.others))
}

// ---------------------------------------------------------------- 마운트

export default function (component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component
  const host = parentElement.querySelector('.emg')
  if (!host || !data) return
  const S = host.__emg || (host.__emg = freshState())
  S.setState = setStateValue
  S.setTrigger = setTriggerValue
  const palette = data.palette || {}
  const paletteKey = JSON.stringify(palette)
  if (S.paletteKey !== paletteKey) {
    S.paletteKey = paletteKey
    for (const [name, value] of Object.entries(palette)) host.style.setProperty('--emg-' + name, String(value))
  }
  host.dataset.mode = String(data.mode || '')
  if (!S.bound) {
    S.bound = true
    // 표 밖으로 초점이 나가거나(「리비전 저장」 누름 포함) 창이 숨으면 기다리지 않고 보낸다 — 보낼 것이 있을 때만.
    listen(S, host, 'focusout', (event) => {
      if (!event.relatedTarget || !host.contains(event.relatedTarget)) send(S)
      // 불러오기 밖(표 칸 등)으로 초점을 옮겼다 — 돌아온 불러오기 회차가 찾기 칸으로 초점을 빼앗지 않는다.
      if (!S.painting && event.relatedTarget && !host.contains(event.relatedTarget)) S.refocus = null
    })
    listen(S, document, 'visibilitychange', () => send(S))
    listen(S, document, 'mousedown', (event) => {
      // 그림자 DOM 밖에서 보면 대상이 호스트로 바뀐다 — 지나온 길(composedPath)로 안쪽 누름을 가른다.
      const inside = typeof event.composedPath === 'function' ? event.composedPath().includes(host) : host.contains(event.target)
      if (S.pop && S.pop !== 'search' && !inside) {
        S.pop = null
        if (S.data && S.data.mode === 'loader') drawLoader(host, S, S.data)
      }
    })
  }
  if (data.mode === 'loader') drawLoader(host, S, data)
  else if (data.mode === 'grid') drawGrid(host, S, data)
  else drawSide(host, S, data)
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    send(S)
    for (const [target, type, handler, options] of S.listeners) target.removeEventListener(type, handler, options)
    S.listeners = []
    if (S.timer) clearTimeout(S.timer)
    if (S.noteTimer) clearTimeout(S.noteTimer)
    if (S.scrollFrame) cancelAnimationFrame(S.scrollFrame)
    S.timer = 0
    S.noteTimer = 0
    S.scrollFrame = 0
    S.bound = false
    S.sideBound = false
    S.skeleton = false
  }
}
