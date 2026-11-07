// 범용 편집 그리드 — DOM 을 모르는 순수 구획과 기능 갈고리 표(CORE). 등록 때 eg_select·eg_fill·eg_toolbar·eg_core 와
// 이 차례로 이어 붙인다(`components/edit_grid.JS_PARTS` — 주석만 든 줄은 걷는다). 아래 `// <eg-…>` 구획은 node 시험이
// 떼어 돌린다. 값 다듬기·표시 형식은 Python `services/edit_grid.coerce`·`format_value` 와 같은 답을 낸다(쌍둥이 시험).

// <eg-codes>
// 껍데기·feed 의 64자 코드. 칸 코드는 고정 폭 글자(높은 자리 먼저), 값은 줄마다 (코드 + 길이 1글자) 짝의 이음이다.
const CODE_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'
const CODE_INDEX = (() => {
  const table = new Int16Array(128).fill(-1)
  for (let k = 0; k < CODE_ALPHABET.length; k += 1) table[CODE_ALPHABET.charCodeAt(k)] = k
  return table
})()
const KEY_SEPARATOR = '\x1f'
const DUPLICATE_SEPARATOR = '\x1e'
const DRAFT_BAD = 'bad'

function codeAt(text, at, width) {
  let code = 0
  for (let d = 0; d < width; d += 1) code = code * 64 + CODE_INDEX[text.charCodeAt(at + d)]
  return code
}

function decodeCodes(text, width) {
  const size = Math.max(width || 1, 1)
  const body = String(text || '')
  const codes = new Int32Array(Math.floor(body.length / size))
  for (let at = 0, k = 0; k < codes.length; at += size, k += 1) codes[k] = codeAt(body, at, size)
  return codes
}

// 줄 RLE 하나를 풀어 out[offset..] 에 코드를 쓴다(많아야 count 칸). 쓴 칸 수.
function decodeRuns(text, width, out, offset, count) {
  const body = String(text || '')
  const size = Math.max(width || 1, 1)
  let col = 0
  for (let at = 0; at + size < body.length && col < count; at += size + 1) {
    const code = codeAt(body, at, size)
    const length = CODE_INDEX[body.charCodeAt(at + size)]
    for (let k = 0; k < length && col < count; k += 1) out[offset + col++] = code
  }
  return col
}

// 업무 키 — 분류 칸 원값을 \x1f 로 잇고, 같은 키의 둘째부터 \x1e<n>(Python `row_keys` 와 같은 글).
function rowKeyText(dims, keyCodes, dupes, r) {
  const parts = []
  for (let j = 0; j < keyCodes.length; j += 1) parts.push(dims[j][keyCodes[j][r]])
  const count = dupes.get(r)
  return parts.join(KEY_SEPARATOR) + (count ? DUPLICATE_SEPARATOR + count : '')
}

// 껍데기 → 모델. 값은 Float64Array(줄 × 값 칸, 빈칸 NaN).
function decodeBase(shell) {
  const keyCols = shell.keyCols || []
  const valueCols = shell.valueCols || []
  const rows = Math.max(Number(shell.rows) || 0, 0)
  const keyCount = keyCols.length
  const valueCount = valueCols.length
  const dims = shell.dims || []
  const keyCodes = (shell.codes || []).map((text, j) => decodeCodes(text, (shell.codeWidths || [])[j]))
  const vals = shell.vals || [null]
  const runs = shell.runs || []
  const values = new Float64Array(rows * valueCount)
  const line = new Int32Array(valueCount)
  for (let r = 0; r < rows; r += 1) {
    line.fill(0)
    decodeRuns(runs[r], shell.valWidth, line, 0, valueCount)
    for (let c = 0; c < valueCount; c += 1) {
      const value = vals[line[c]]
      values[r * valueCount + c] = value === null || value === undefined ? NaN : Number(value)
    }
  }
  const dupes = new Map((shell.dupes || []).map((pair) => [pair[0], pair[1]]))
  const keys = new Array(rows)
  const rowOf = new Map()
  for (let r = 0; r < rows; r += 1) {
    keys[r] = rowKeyText(dims, keyCodes, dupes, r)
    rowOf.set(keys[r], r)
  }
  const colOf = new Map(valueCols.map((name, c) => [name, c]))
  return {
    table: shell.table, title: shell.title || '', rows, keyCount, valueCount, colCount: keyCount + valueCount,
    keyCols, valueCols, dims, labels: shell.labels || [], keyCodes, values, keys, rowOf, colOf,
    fmt: shell.fmt || { kind: 'fixed', digits: 0 }, draft: new Map(), bad: new Map(),
  }
}

// feed 초안 → Map(셀번호 → 값 | null(빈칸) | DRAFT_BAD) 과 Map(셀번호 → {text, code}). 셀번호 = 줄 × 값 칸 + 칸.
function decodeDraft(feed, valueCount) {
  const draft = new Map()
  const bad = new Map()
  const dvals = feed.dvals || []
  const width = feed.dwidth || 1
  const codes = new Int32Array(Math.max(valueCount, 1))
  for (const item of feed.drows || []) {
    const row = item[0]
    const start = item[1]
    codes.fill(0)
    const count = decodeRuns(item[2], width, codes, 0, Math.max(valueCount - start, 0))
    for (let k = 0; k < count; k += 1) {
      const code = codes[k]
      if (!code) continue
      draft.set(row * valueCount + start + k, code === 1 ? null : code === 2 ? DRAFT_BAD : Number(dvals[code - 3]))
    }
  }
  for (const item of feed.bad || []) bad.set(item[0] * valueCount + item[1], { text: String(item[2]), code: String(item[3]) })
  return { draft, bad }
}
// </eg-codes>

// <eg-format>
// 값 다듬기(Python `coerce` 와 같은 규칙)와 표시 형식(`format_value`). 공백은 이 글자 묶음만 걷는다.
const STRIP_EDGES = /^[ \t\n\r\f\v 　]+|[ \t\n\r\f\v 　]+$/g
const STRIP_END = /[ \t\n\r\f\v 　]+$/
const NUMBER_TEXT = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/
const GROUPED_TEXT = /^[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]*)?$/
const NONFINITE_TEXT = /^[+-]?(?:inf|infinity|nan)$/i

function numberText(value) {
  return String(value)
}

// percent 면 소수점을 두 자리 옮긴 글로 읽는다(「99.99%」 → 0.9999 — 100 으로 나누면 0.9998999… 이 된다).
function parseNumberText(body, percent) {
  let text = body
  if (text.indexOf(',') >= 0) {
    if (!GROUPED_TEXT.test(text)) return { value: null, error: 'num' }
    text = text.replace(/,/g, '')
  }
  if (NONFINITE_TEXT.test(text)) return { value: null, error: 'finite' }
  if (!NUMBER_TEXT.test(text)) return { value: null, error: 'num' }
  let value
  if (percent) value = /e/i.test(text) ? Number(text) / 100 : Number(text + 'e-2')
  else value = Number(text)
  if (!Number.isFinite(value)) return { value: null, error: 'finite' }
  return { value, error: null }
}

// 칸에 적은 글(또는 수) → {value, error, text}. 빈 글은 빈칸(null — blankZero 면 0). 범위 검사는 양식과 같은 값이면 하지 않는다.
function parseInput(raw, fmt, templateValue) {
  const blank = { value: fmt.blankZero ? 0 : null, error: null, text: null }
  if (raw === null || raw === undefined) return blank
  let number
  let text
  if (typeof raw === 'number') {
    text = numberText(raw)
    if (!Number.isFinite(raw)) return { value: null, error: 'finite', text }
    number = raw
  } else if (typeof raw === 'string') {
    text = raw
    let body = raw.replace(STRIP_EDGES, '')
    if (!body) return blank
    const percent = fmt.kind === 'percent' && body.endsWith('%')
    if (percent) body = body.slice(0, -1).replace(STRIP_END, '')
    const parsed = parseNumberText(body, percent)
    if (parsed.error) return { value: null, error: parsed.error, text }
    number = parsed.value
  } else {
    return { value: null, error: 'num', text: String(raw) }
  }
  number += 0
  const template = templateValue === null || templateValue === undefined || Number.isNaN(templateValue) ? null : templateValue
  if (template !== null && number === template) return { value: number, error: null, text: null }
  if (fmt.min !== null && fmt.min !== undefined && number < fmt.min) return { value: null, error: 'min', text }
  if (fmt.max !== null && fmt.max !== undefined && number > fmt.max) return { value: null, error: 'max', text }
  if (fmt.int && number !== Math.floor(number)) return { value: null, error: 'int', text }
  return { value: number, error: null, text: null }
}

function groupDigits(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function groupedText(text) {
  const sign = text.startsWith('-') ? '-' : ''
  const body = sign ? text.slice(1) : text
  const dot = body.indexOf('.')
  return sign + (dot < 0 ? groupDigits(body) : groupDigits(body.slice(0, dot)) + body.slice(dot))
}

function stripZeros(text) {
  return text.indexOf('.') < 0 ? text : text.replace(/0+$/, '').replace(/\.$/, '')
}

// 유효숫자 digits 자리(%g 꼴 — 지수 -4 이상 digits 미만이면 고정 소수, 아니면 e±XX).
function significantText(value, digits) {
  if (value === 0) return '0'
  const rounded = Number(Math.abs(value).toPrecision(digits))
  const parts = rounded.toExponential(digits - 1).split('e')
  const exponent = Number(parts[1])
  const sign = value < 0 ? '-' : ''
  if (exponent >= -4 && exponent < digits) return sign + groupedText(stripZeros(rounded.toFixed(Math.max(digits - 1 - exponent, 0))))
  const mantissa = stripZeros(parts[0])
  const size = String(Math.abs(exponent)).padStart(2, '0')
  return sign + mantissa + 'e' + (exponent >= 0 ? '+' : '-') + size
}

// 칸에 보이는 글. percent 98.75% · fixed 천 단위 + 소수 digits · sig 유효숫자. 빈칸은 빈 글.
function formatValue(value, fmt) {
  if (value === null || value === undefined || Number.isNaN(value)) return ''
  const number = value + 0
  const digits = Number(fmt.digits) || 0
  if (fmt.kind === 'percent') return groupedText(stripZeros((number * 100).toFixed(digits))) + '%'
  if (fmt.kind === 'fixed') return groupedText(number.toFixed(digits))
  return significantText(number, Math.max(digits, 1))
}

// 칸 편집기의 처음 글 — percent 는 「98.75%」(100 배를 15자리로 다듬음), 그 밖은 원값 글.
function editText(value, fmt) {
  if (value === null || value === undefined || Number.isNaN(value)) return ''
  if (fmt.kind === 'percent') return numberText(Number((value * 100).toPrecision(15))) + '%'
  return numberText(value)
}
// </eg-format>

// <eg-outbox>
// 보낼 목록. seq 는 마운트 안에서 늘 늘고, ack 가 온 seq 이하는 뺀다. 칸 수는 실어 보내는 크기다(write 는 값 칸,
// 채우기·비우기·되돌리기는 줄 + 칸 이름 수).
function opCells(op) {
  if (op.op === 'write') return (op.values || []).reduce((sum, line) => sum + line.length, 0)
  if (op.op === 'fill' || op.op === 'clear' || op.op === 'revert') return (op.rows || []).length + (op.cols || []).length
  return 1
}

function createBox() {
  return { seq: 0, ops: [] }
}

function boxCells(box) {
  return box.ops.reduce((sum, op) => sum + opCells(op), 0)
}

function boxQueue(box, op, limit, now) {
  if (boxCells(box) + opCells(op) > limit) return null
  box.seq += 1
  const queued = Object.assign({}, op, { seq: box.seq, at: now })
  box.ops.push(queued)
  return queued
}

function boxAck(box, seq) {
  const before = box.ops.length
  box.ops = box.ops.filter((op) => op.seq > seq)
  return before - box.ops.length
}

// 그 표의 이력 세대(gen)가 바뀐 뒤의 옛 세대 op. 출납에서 빼지 않는다 — 서버가 버리면서 세어 알리고 ack 가 지운다. 묶음이 아직 든
// op 도 서버까지 가야 세이고, 보낸 op 도 다음 보냄에 함께 실려야 합쳐진 회차에서 수가 빠지지 않는다.
function boxStale(box, table, gen) {
  return box.ops.filter((op) => op.table === table && op.gen !== gen)
}

// 아직 ack 가 오지 않은 같은 op(seq·at 밖의 칸이 모두 같은 것)가 있는가 — 더블클릭의 둘째 누름을 거른다.
function boxHasOp(box, op) {
  const keys = Object.keys(op).filter((key) => key !== 'seq' && key !== 'at')
  return box.ops.some((queued) => keys.every((key) => JSON.stringify(queued[key]) === JSON.stringify(op[key])))
}
// </eg-outbox>

// <eg-nav>
// 키 → 옮겨 갈 칸(보기 좌표). 표 밖으로는 나가지 않는다. 모르는 키면 null. page 는 보이는 줄 수, pageCols 는 보이는 칸 수,
// isBlank(r, c) 는 Ctrl+화살표(덩어리 끝)가 쓴다.
function clampNum(value, low, high) {
  return Math.min(Math.max(value, low), high)
}

function moveCell(pos, key, mods, rows, cols, page, pageCols, isBlank) {
  if (rows <= 0 || cols <= 0) return null
  const ctrl = Boolean(mods && mods.ctrl)
  const alt = Boolean(mods && mods.alt)
  const steps = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }
  let r = pos.r
  let c = pos.c
  if (steps[key]) {
    const [dr, dc] = steps[key]
    if (ctrl) return blockEdge(pos, dr, dc, rows, cols, isBlank || (() => false))
    r += dr
    c += dc
  } else if (key === 'PageUp' || key === 'PageDown') {
    const sign = key === 'PageUp' ? -1 : 1
    if (alt) c += sign * Math.max(pageCols || 1, 1)
    else r += sign * Math.max(page || 1, 1)
  } else if (key === 'Home') {
    c = 0
    if (ctrl) r = 0
  } else if (key === 'End') {
    c = cols - 1
    if (ctrl) r = rows - 1
  } else return null
  return { r: clampNum(r, 0, rows - 1), c: clampNum(c, 0, cols - 1) }
}

// 엑셀 Ctrl+화살표 — 지금 칸과 다음 칸이 다 차 있으면 그 덩어리 끝, 아니면 다음으로 찬 칸(없으면 표 끝).
function blockEdge(pos, dr, dc, rows, cols, isBlank) {
  const inside = (r, c) => r >= 0 && r < rows && c >= 0 && c < cols
  let r = pos.r
  let c = pos.c
  if (!inside(r + dr, c + dc)) return { r, c }
  if (!isBlank(r, c) && !isBlank(r + dr, c + dc)) {
    while (inside(r + dr, c + dc) && !isBlank(r + dr, c + dc)) {
      r += dr
      c += dc
    }
    return { r, c }
  }
  r += dr
  c += dc
  while (inside(r + dr, c + dc) && isBlank(r, c)) {
    r += dr
    c += dc
  }
  return { r, c }
}

// Tab — 오른쪽(Shift 면 왼쪽) 칸. 줄 끝·첫 칸이면 null(그리드 밖으로 초점이 나간다).
function tabMove(pos, back, cols) {
  const c = pos.c + (back ? -1 : 1)
  return c < 0 || c >= cols ? null : { r: pos.r, c }
}

// 단축키 글자(소문자 라틴) — key 가 라틴 글자면 그 글자, 아니면 자판 자리(code 'KeyZ' → 'z'). 한글 자판에서는 Ctrl 조합의
// key 가 「ㅋ」 처럼 오므로 Ctrl+Z·Y·A·C·X·D·R·F 판정은 모두 이 한 길을 탄다. 글자 키가 아니면 빈 글.
function shortcutLetter(key, code) {
  const text = String(key === null || key === undefined ? '' : key)
  if (/^[a-z]$/i.test(text)) return text.toLowerCase()
  const match = /^Key([A-Z])$/.exec(String(code === null || code === undefined ? '' : code))
  return match ? match[1].toLowerCase() : ''
}
// </eg-nav>

// <eg-view>
// 보기 차례(보기 줄 → 원본 줄). filters = {열쇠 칸 번호: [사전 코드…]} — 모두 맞는 줄만. sort = {col, dir} 면 keyOf(원본 줄)로
// 안정 정렬하고 빈 값(NaN·빈 글)은 방향과 상관없이 끝에 둔다. numeric 이면 수로, 아니면 한국어 자연 차례로 견준다.
const VIEW_COLLATOR = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' })

function viewOrder(rows, keyCodes, filters, sort, keyOf, numeric) {
  const picks = []
  for (const [col, codes] of Object.entries(filters || {})) {
    const index = Number(col)
    if (keyCodes[index] && Array.isArray(codes)) picks.push([keyCodes[index], new Set(codes.map(Number))])
  }
  const order = []
  for (let r = 0; r < rows; r += 1) if (picks.every(([codes, set]) => set.has(codes[r]))) order.push(r)
  if (sort && keyOf) {
    const keys = new Map(order.map((r) => [r, keyOf(r)]))
    const blank = (value) => (numeric ? value === null || value === undefined || Number.isNaN(value) : value === '' || value === null || value === undefined)
    const sign = sort.dir === 'desc' ? -1 : 1
    order.sort((a, b) => {
      const x = keys.get(a)
      const y = keys.get(b)
      const bx = blank(x)
      const by = blank(y)
      if (bx || by) return bx === by ? a - b : bx ? 1 : -1
      const diff = numeric ? x - y : VIEW_COLLATOR.compare(String(x), String(y))
      return diff ? diff * sign : a - b
    })
  }
  return Int32Array.from(order)
}

// 원본 줄 → 보기 줄(보기에 없으면 -1).
function viewRank(order, rows) {
  const rank = new Int32Array(rows).fill(-1)
  for (let k = 0; k < order.length; k += 1) rank[order[k]] = k
  return rank
}

function nextSort(sort, col) {
  if (!sort || sort.col !== col) return { col, dir: 'asc' }
  return sort.dir === 'asc' ? { col, dir: 'desc' } : null
}
// </eg-view>

// <eg-layout>
// 칸 폭 → 왼쪽 끝 자리, 고정 칸 수. 앞에서부터 열쇠 칸을 고정하되 누적 폭이 표 폭 × ratio 를 넘는 칸부터는 풀어 함께
// 굴린다(첫 열쇠 칸은 늘 고정).
function columnLefts(widths) {
  const lefts = []
  let x = 0
  for (const width of widths) {
    lefts.push(x)
    x += width
  }
  return { lefts, total: x }
}

function frozenCount(widths, keyCount, gridWidth, ratio) {
  if (keyCount <= 0) return 0
  const limit = Math.max(gridWidth, 0) * ratio
  let used = widths[0] || 0
  let count = 1
  while (count < keyCount && used + (widths[count] || 0) <= limit) {
    used += widths[count] || 0
    count += 1
  }
  return count
}

function colAtX(lefts, x) {
  let low = 0
  let high = lefts.length - 1
  while (low < high) {
    const mid = (low + high + 1) >> 1
    if (lefts[mid] <= x) low = mid
    else high = mid - 1
  }
  return Math.max(low, 0)
}

function defaultWidths(keyCols, valueCount, keyWidth, valueWidth) {
  const widths = keyCols.map((col) => (Number(col && col.width) > 0 ? Number(col.width) : keyWidth))
  for (let c = 0; c < valueCount; c += 1) widths.push(valueWidth)
  return widths
}
// </eg-layout>

// <eg-changes>
// 「적용 전 변경」 줄 — 초안 칸(draft ∪ bad)을 보기 차례(줄 → 칸)로, 보기에 없는 줄(필터)은 그 뒤에 원본 차례로. 앞 limit 개와 전체 수.
// 줄마다 {row, col, before(양식 값 | null), after(새 값 | null), bad({text, code} | null)}.
function changeEntries(draft, bad, values, valueCount, rank, limit) {
  const cells = Array.from(draft.keys())
  for (const cell of bad.keys()) if (!draft.has(cell)) cells.push(cell)
  const place = (cell) => {
    const row = Math.floor(cell / valueCount)
    const at = rank && row < rank.length ? rank[row] : -1
    return [at < 0 ? 1 : 0, at < 0 ? row : at, cell % valueCount]
  }
  const keyed = cells.map((cell) => [place(cell), cell])
  keyed.sort((x, y) => x[0][0] - y[0][0] || x[0][1] - y[0][1] || x[0][2] - y[0][2])
  const entries = []
  for (const [, cell] of keyed.slice(0, Math.max(limit, 0))) {
    const row = Math.floor(cell / valueCount)
    const col = cell % valueCount
    const base = values[cell]
    const value = draft.get(cell)
    const isBad = value === DRAFT_BAD || bad.has(cell)
    entries.push({
      row, col,
      before: Number.isNaN(base) ? null : base,
      after: isBad || value === undefined ? null : value,
      bad: isBad ? bad.get(cell) || { text: '', code: 'num' } : null,
    })
  }
  return { entries, total: keyed.length }
}
// </eg-changes>

// ---------------------------------------------------------------- 기능 갈고리
// 기능 파일(eg_select·eg_fill·eg_toolbar)은 모듈을 읽을 때 `feature({...})` 로 갈고리를 등록하고, eg_core 가 마운트 때 이
// 차례(select → fill → toolbar)로 부른다. 갈고리: init · keydown(true 면 처리함) · pointerdown(true 면 처리함) · paintCell ·
// paintOverlay · onFeed · onSelect · onLayout · cleanup.
const FEATURES = []
const FEATURE_ORDER = ['select', 'fill', 'toolbar']

function feature(def) {
  if (!def || typeof def.name !== 'string') return
  const at = FEATURES.findIndex((item) => item.name === def.name)
  if (at >= 0) FEATURES[at] = def
  else FEATURES.push(def)
  FEATURES.sort((a, b) => FEATURE_ORDER.indexOf(a.name) - FEATURE_ORDER.indexOf(b.name))
}
