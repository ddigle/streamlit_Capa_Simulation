// 설비 마스터 표 — 가용설비 현황 「설비 마스터」 탭의 Components v2. 한 등록을 세 자리(data.mode)에 마운트한다:
// loader(불러오기) · grid(표) · side(오른쪽 칸 — data.panel 로 호기 상세 / 새 호기 / 저장 전 변경).
// 편집본을 바꾸는 조작은 모두 상태 값 `outbox` 로 보낸다(반영되지 않은 조작 전부, mount·seq — 「호기 추가」 도 `add`
// op). 상태 값은 그 밖에 「새 호기」 초안 `draft`(편집본을 바꾸지 않는다 — 확정마다 번호를 올려 39칸 전부) 하나다.
// 잃어도 되는 화면 조작만 트리거다(불러오기 load·clear·new·dialog, 표 open·unload, 오른쪽 칸 open·goto·copy). 업무
// 검증은 파이썬이 한다 — 여기는 data 가 준 잠금·고를 값·자리 계산만 안다. 데이터 글은 textContent 로만 넣고
// innerHTML 은 고정 아이콘에만 쓴다. 아래 `// <grid-…>` 구획은 DOM 을 모르는 순수 함수라 node 시험이 떼어 돌린다.

// <grid-paste>
// 붙인 글을 칸 판으로. 끝 줄바꿈 하나는 떼고 \r 은 버린다. 탭·줄바꿈이 없으면(한 칸) null — 보통 붙여넣기다.
// 엑셀은 줄바꿈·탭이 든 칸을 따옴표로 감싸고 안의 따옴표를 겹쳐(`""`) 복사한다 — `"` 로 시작해 `"` + 탭·줄바꿈·끝으로
// 닫히는 칸은 그 규칙으로 읽어 한 칸으로 둔다(「엑셀·CSV로 한꺼번에」 의 pandas 읽기와 같은 값). 닫히지 않거나 닫는
// 따옴표 뒤에 글이 더 있으면 따옴표 칸이 아니다 — 그 칸은 글자 그대로(다음 탭·줄바꿈까지) 읽는다.
function parseClipboard(text) {
  const body = String(text == null ? '' : text).replace(/\r/g, '').replace(/\n$/, '')
  if (!/[\t\n]/.test(body)) return null
  const rows = [[]]
  let at = 0
  for (;;) {
    const quoted = body[at] === '"' ? readQuotedCell(body, at) : null
    let end = at
    if (quoted) end = quoted.end
    else while (end < body.length && body[end] !== '\t' && body[end] !== '\n') end += 1
    rows[rows.length - 1].push(quoted ? quoted.value : body.slice(at, end))
    if (end >= body.length) return rows
    if (body[end] === '\n') rows.push([])
    at = end + 1
  }
}

// `start` 의 `"` 로 연 칸을 읽는다 — 값과 닫는 따옴표 다음 자리. 따옴표 칸이 아니면 null.
function readQuotedCell(body, start) {
  let value = ''
  for (let at = start + 1; at < body.length; at += 1) {
    if (body[at] !== '"') {
      value += body[at]
    } else if (body[at + 1] === '"') {
      value += '"'
      at += 1
    } else {
      const next = at + 1
      return next === body.length || body[next] === '\t' || body[next] === '\n' ? { value, end: next } : null
    }
  }
  return null
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

// 잠긴 단추의 까닭(`lockButton`) — 빈 글이면 켠다.
function searchLockText(query) {
  return String(query || '').trim() ? '' : '설비명을 치면 누를 수 있습니다'
}

function conditionLockText(picked, rows) {
  if (rows) return ''
  return picked ? '조건에 맞는 호기가 없습니다' : '조건을 고르면 누를 수 있습니다'
}

function loadAllLockText(shown, total) {
  return total && shown >= total ? '전체를 불러왔습니다' : ''
}

function applyLockText(count, ready, lockReason) {
  if (count) return ''
  if (lockReason) return lockReason
  return ready ? '바뀔 칸이 없습니다' : '넣을 값을 고르면 누를 수 있습니다'
}

function shiftLockText(count, days, lockReason) {
  if (count) return ''
  if (lockReason) return lockReason
  return days === null ? '밀 날 수를 적으면 누를 수 있습니다' : '밀 일정이 있는 칸이 없습니다'
}

// 일정이 있는 칸이 모두 잠겼으면 그 첫 칸([줄, 칸]) — 풀린 일정이 있거나 일정이 아예 없으면 null(잠금이 까닭이 아니다).
function lockedShiftCell(rows, cols, locked) {
  let first = null
  for (const row of rows) {
    for (const col of cols) {
      if (!shiftIso(String(row.values[col] || ''), 0)) continue
      if (!locked(row, col)) return null
      if (!first) first = [row, col]
    }
  }
  return first
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

// <grid-new>
// 「새 호기」 초안 — 받은 초안(파이썬)이 제 것보다 번호가 크면(가져오기·「호기 추가」 뒤·처음 마운트) 그것으로
// 바꾸고, 아니면 제 것(아직 판정 전인 칸 포함)을 둔다. 확정마다 번호를 둘 가운데 큰 것 + 1 로 올린다.
function adoptDraft(local, server) {
  if (!server || !Array.isArray(server.values)) return local
  if (!local || Number(server.seq) > Number(local.seq)) {
    return { seq: Number(server.seq) || 0, values: server.values.slice() }
  }
  return local
}

function bumpDraft(draft, serverSeq) {
  return { seq: Math.max(Number(draft.seq) || 0, Number(serverSeq) || 0) + 1, values: draft.values.slice() }
}

// 체크 상자 한 칸 — 판정(파이썬)이 이 초안 번호의 것이고 그 칸을 그 뒤에 고치지 않았으면 그 판정, 아니면 칸이
// 찼는지만(아직 판정 전).
function tierDone(serverDone, value, fresh) {
  return fresh ? Boolean(serverDone) : String(value || '').trim() !== ''
}

// 「호기 추가」 를 켤까 — 필수 칸(설비명·공정소분류·Y/N 셋)이 찼고, 판정이 지금 초안의 것이면 막힘이 없을 때. 판정
// 전이면 켜 두고 파이썬이 「호기 추가」 를 다시 본다(업무 검증은 늘 파이썬).
function canAdd(values, required, blocked, fresh, locked) {
  if (locked) return false
  if (!required.every((k) => String(values[k] || '').trim() !== '')) return false
  return !(fresh && blocked)
}

// 「호기 추가」 풍선 글 — 판정(파이썬)이 지금 초안의 것이면 그 글(더 말할 것이 없으면 빈 글), 보낸 초안의 판정을
// 기다리면 확인 중이다. 아직 보내지 않은 글(`typed`)에는 아무 확인도 돌지 않는다 — 칸을 벗어나거나 Enter 를 쳐야
// 판정이 돈다. 그래서 빈 필수 칸(`missing`)이 있으면 판정과 같은 말로 그 칸 이름을, 없으면 언제 확인하는지를 말한다.
function addTip(hint, judged, typed, missing) {
  if (judged) return String(hint || '')
  if (!typed) return '고친 칸을 확인하는 중입니다'
  if (missing.length) return '아직 추가할 수 없습니다 — ' + missing.join(' · ') + ' 칸을 확인합니다'
  return '칸을 벗어나면 확인합니다'
}

// 새 호기 칸 오류를 보일까 — 판정이 지금 초안의 것이고, 값이 있거나 만졌거나, 늘 필수인 칸(설비명·공정소분류·Y/N 셋 —
// 처음 연 빈 양식을 빨갛게 칠하지 않게 만지기 전에는 굵은 테만)이 아니면. 다른 칸 값 때문에 막는 칸(Qual일정이 있는
// 신규 호기의 Qual상태, 좌표가 있는데 빈 크기 등)은 만지지 않아도 까닭을 보인다.
function showsError(hasError, fresh, value, touched, base) {
  if (!hasError || !fresh) return false
  return String(value || '').trim() !== '' || touched || !base
}

// 칸 머리가 화면 위로 나갔는가(`top` — getBoundingClientRect, `margin` — 앱 머리 띠가 가리는 높이).
function needsReveal(top, margin) {
  return Number(top) < Number(margin || 0)
}

// 스크롤 칸 안 칸 머리를 그 칸 위 끝으로 — 머리(`top`)가 칸 위 끝(`boxTop`)보다 위에 있는 만큼 올린 스크롤 자리(0 아래로
// 가지 않는다). 칸 안에서 머리가 보이면 지금 자리(`scrollTop`) 그대로.
function boxScrollFor(scrollTop, top, boxTop) {
  const now = Number(scrollTop) || 0
  const over = Number(boxTop) - Number(top)
  return over > 0 ? Math.max(0, now - over) : now
}
// </grid-new>

// <grid-choice>
// 고르는 칸의 선택지 — 칸 단위 `options`(+ 비움)에서, 칸 정의에 `optionsBy` 가 있으면 그 줄의 기준 칸 값으로 좁힌다
// (층 칸 `{"동": {"C1": ["1F", …]}}` — 그 동의 사용 층만, Space 층 비활성의 짝 단위 거름). 기준 칸이 비었거나 표에
// 없는 값이면 칸 단위 그대로다. 지금 값(`current`)은 늘 남긴다 — 비활성 층에 이미 있는 호기도 제 값을 고른 채 보인다.
function choiceOptions(columns, column, valueAt, current) {
  let options = column.options || []
  const by = column.optionsBy || {}
  for (const name of Object.keys(by)) {
    const k = columns.findIndex((item) => item && item.name === name)
    const key = k < 0 ? '' : String(valueAt(k) || '').trim()
    const table = by[name] || {}
    if (!key || !Object.prototype.hasOwnProperty.call(table, key)) continue
    const allowed = new Set(table[key] || [])
    options = options.filter((option) => allowed.has(option) || option === current)
  }
  return options.concat(column.blank ? [''] : [])
}
// </grid-choice>

// <grid-place>
// 팝오버를 단추 왼쪽에서 얼마나 당길지(px, 0 이하) — 화면 오른쪽 밖으로 나가면 왼쪽으로, 왼쪽 끝 `margin` 은 남긴다.
function popoverShift(left, width, viewport, margin) {
  const over = left + width - (viewport - margin)
  if (over <= 0) return 0
  return -Math.min(over, Math.max(left - margin, 0))
}

// `end` 가 `start` 를 넘어간 px(올림, 안 넘으면 0) — 가려진 만큼만 옮길 때 쓴다.
function overPx(end, start) {
  return Math.max(Math.ceil(Number(end) - Number(start)), 0)
}
// </grid-place>

const NAME_PASTE_NOTE = '설비명은 붙여 넣지 않습니다 — 이름은 오른쪽 호기 상세의 설비명 칸에서 바꿉니다'
// 표 밑 「⌨ 키보드 조작」 표지의 풍선.
const KEYS_HELP = '칸을 누르면 바로 고칩니다 · Enter 확정 · Esc 취소 · Tab ↑ ↓ 옆·위아래 칸 · 엑셀 여러 칸을 칸 위에서 Ctrl+V · 칸 위 Space = 줄 고르기 · 체크 Shift+클릭 = 범위 · 줄 끝 − 는 목록에서 빼기'
// 지우기 단추 풍선 — 저장본 호기를 지우면 어떻게 되나(누르기 전에 보이게, 설계 규칙 UI-NTF-09). 지운 뒤 칸 머리 글은 값 한 줄이다.
const DELETE_TIP = '리비전을 저장하면 모든 설비 시나리오에서 지워집니다 — 이 시나리오에서만 빼려면 정지·반출/이설일정을 적습니다'
// 불러오기 줄은 줄인 이름 「일정 확인」 이다 — 원래 뜻은 풍선이 말한다.
const ALERTS_TIP = '일정 확인 필요 — 일정이 지났는데 실적이 없거나, 상태와 실적이 맞지 않는 호기'
// 찾기 칸 한 줄에 입력 칸 180 · 테 · 여백 · 돋보기 · 「불러오기」 가 드는 폭(1.63 측정 298 + 여유).
const SEARCH_LINE_PX = 300
const ROW_H = 34
const BUFFER_ROWS = 10
const SEND_MS = 300
const COLSET_KEY = 'capa.equipmentGrid.colSet'
// 머리 띠 밑에 붙는 화면 탭 줄(`app_header.PAGE_TABS_SELECTOR` — 시험이 같은지 본다).
const PAGE_TABS_STRIP = '.st-key-page_tabs_strip'
// 페이지 본문 스크롤 칸 — 토스트를 감싼 스크롤 칸을 찾을 때 여기서 멈춘다(그 위는 scrollIntoView 몫).
const PAGE_SCROLLER = '[data-testid="stMain"]'
// 빈 날짜 칸 자리표시 — 꼴만 적는다. 실제 날짜(「2026-11-09」)를 적으면 어두운 테마에서 값처럼 읽혔다(E2E).
const DATE_PLACEHOLDER = 'YYYY-MM-DD'
// 저장 갈래 꼬리표(칸 머리·상세 묶음·값 넣기 칸·변경 줄). 공통·상태 칸은 꼬리표 없이 「공통」 이다.
const SCOPE_LABELS = { scenario: '시나리오', layout: '배치' }
const SCOPE_SHORT = { scenario: '시', layout: '배' }
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

function freshState() {
  return {
    mount: newMount(), box: createBox(), sentSeq: 0, pending: new Map(), timer: 0, base: null, view: null,
    selected: new Set(), anchor: null, sort: null, colSet: null, edit: null, focus: null, toastClosed: null,
    note: '', noteSeq: 0, noteTimer: 0, scrollFrame: 0, query: '', pop: null, pops: {}, procQuery: '', conds: [{ col: 4, text: null }],
    suggest: -1, drafts: new Map(), unitId: null, listeners: [], bulkCol: 'Qual상태', bulkValue: '', days: '7',
    nd: null, ndSent: [], ndTouched: new Set(), ndDirty: new Set(), copyQuery: '',
    dialogOpener: null, dialogClosed: null,
  }
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

// ---------------------------------------------------------------- 출납(표·오른쪽 칸 공용)

// 칸을 연 채 편집본이 다시 섰다 — 친 글도 옛 base op 로 보내 서버가 함께 세어 알린다(`receive` 가 칸을 닫는다).
function queueOpenEdit(S) {
  const edit = S.edit
  if (!edit || edit.draft === edit.original) return
  enqueue(S, { op: 'cell', id: edit.id, col: S.model.columns[edit.col].name, text: edit.draft }, [])
  schedule(S)
}

function receive(S, data) {
  const base = String(data.base || '')
  if (S.box.base !== base) queueOpenEdit(S)
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
    // 기다리던 op 가 돌아왔다 — 진행 한 줄(붙여넣는 중)을 거둔다. 결과는 알림창이 말한다.
    if (S.noteSeq && S.noteSeq <= ack.seq) clearNote(S)
  }
  S.limit = Number((data.limits || {}).outboxCells) || 10000
}

// 이미 보낸 op 만 남았으면 보내지 않는다 — 「호기 추가」 는 그 회차가 「새 호기」 마운트를 내리고 칸 고르기를 「호기 상세」 로
// 적는데, ack 를 못 받은 마운트가 내려가며 다시 보내면 그 회차가 고르기 값을 브라우저에 적용하기 전의 옛 값을 실어 눌림은
// 「호기 상세」, 본문은 「새 호기」 로 어긋났다.
function send(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = 0
  const last = S.box.ops[S.box.ops.length - 1]
  if (!last || last.seq <= S.sentSeq || !S.setState) return
  S.sentSeq = last.seq
  S.setState('outbox', { mount: S.mount, ops: S.box.ops.slice() })
}

function schedule(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = setTimeout(() => send(S), SEND_MS)
}

// 단추 하나가 보내는 op — 같은 op 가 아직 회차에서 돌아오지 않았으면(더블클릭의 둘째 누름) 보내지 않는다. 밀기는 두 번 밀렸고,
// 넣기·되살리기·지우기는 둘째 op 의 헛결과(「0칸 바뀜」·「0대를 되살렸습니다」)가 첫 결과를 덮었다(2026-10-27 E2E). 둘째
// 누름이라 버렸으면 거짓.
function sendOnce(S, op, cells) {
  if (hasPendingOp(S.box, op)) return false
  enqueue(S, op, cells)
  send(S)
  return true
}

function enqueue(S, op, cells) {
  const queued = queueOp(S.box, op, S.limit, Date.now())
  if (!queued) {
    showNote(S, '보낼 고침이 너무 많습니다 — 잠시 뒤 다시 하거나 「엑셀·CSV」 의 「엑셀·CSV로 한꺼번에」 를 씁니다')
    return null
  }
  for (const [id, col, text] of cells || []) S.pending.set(id + '\t' + col, { seq: queued.seq, text })
  return queued
}

// 브라우저 한 줄 — 칸 수 상한 · 이름 붙여넣기 거부와 진행(붙여넣는 중). `seq` 를 주면 그 op 가 돌아올 때 거둔다.
function showNote(S, text, seq) {
  S.note = text
  S.noteSeq = seq || 0
  if (S.noteTimer) clearTimeout(S.noteTimer)
  S.noteTimer = setTimeout(() => clearNote(S), 6000)
  if (S.repaintNote) S.repaintNote()
}

function clearNote(S) {
  if (S.noteTimer) clearTimeout(S.noteTimer)
  S.note = ''
  S.noteSeq = 0
  S.noteTimer = 0
  if (S.repaintNote) S.repaintNote()
}

// 꺼진 단추의 풍선(설계 규칙 UI-INP-07) — 꺼진 단추는 마우스 · 초점을 받지 않아 감싼 칸이 받는다. 꺼진 동안은 감싼 칸이 탭
// 자리와 다시 그릴 때의 초점 표지(data-fk)를 맡고, 켜지면 단추에 돌려준다.
function tipWrap(target, id) {
  const host = el('span', 'emg-tip-host')
  const tip = el('span', 'emg-tip')
  tip.id = id
  tip.setAttribute('role', 'tooltip')
  target.setAttribute('aria-describedby', id)
  host.setAttribute('aria-describedby', id)
  host.appendChild(target)
  host.appendChild(tip)
  const place = () => placeTip(host, tip)
  host.addEventListener('pointerenter', place)
  host.addEventListener('focusin', place)
  return { host, tip, target }
}

// 풍선은 단추 오른쪽 끝에 맞춰 왼쪽으로 자란다 — 단추가 칸 왼쪽 끝에 오면(띠가 접힌 줄의 「넣기」) 사이드바 밑으로 들어가니
// 그만큼 칸 안으로 민다. 창 폭 · 줄 접힘에 따라 달라져 뜰 때 잰다.
function placeTip(host, tip) {
  const frame = host.closest('.emg')
  if (!frame) return
  tip.style.transform = ''
  const shift = overPx(frame.getBoundingClientRect().left, tip.getBoundingClientRect().left)
  if (shift) tip.style.transform = 'translateX(' + shift + 'px)'
}

function holdFocus(wrap, fk) {
  const off = wrap.target.disabled
  wrap.host.tabIndex = off ? 0 : -1
  wrap.host.dataset.fk = off ? fk : ''
  wrap.target.dataset.fk = off ? '' : fk
}

// 까닭이 있으면 잠그고 그 글을 풍선에 둔다 — 빈 글이면 켜고 풍선도 서지 않는다.
function lockButton(wrap, reason, fk) {
  wrap.target.disabled = Boolean(reason)
  wrap.tip.textContent = reason
  holdFocus(wrap, fk)
}

function pendingText(S, id, col) {
  const item = S.pending.get(id + '\t' + col)
  return item ? item.text : null
}

// 그 줄의 칸 값(보내는 중인 값 먼저) — 고르는 칸이 그 줄의 동으로 층 선택지를 좁힐 때(`choiceOptions`) 쓴다.
function rowValueAt(S, row) {
  return (k) => {
    const pending = pendingText(S, row.id, k)
    return pending !== null ? pending : String((row.values || [])[k] || '')
  }
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
  // 단추 셋은 한 덩이로 줄을 바꾼다 — 낱개로 바뀌면 찾기 칸 곁에 하나둘 남아 입력 칸을 누른다.
  const picks = el('div', 'emg-lb-picks')
  bar.appendChild(picks)
  picks.appendChild(processPopover(S, model))
  picks.appendChild(conditionPopover(S, model))
  const alertIds = Array.isArray(data.alertIds) ? data.alertIds : []
  const alerts = button('emg-btn is-warn', '일정 확인 ' + alertIds.length.toLocaleString() + '대', () => {
    load(S, 'alerts', alertIds, [], '일정 확인')
  })
  alerts.disabled = alertIds.length === 0
  alerts.title = ALERTS_TIP
  picks.appendChild(alerts)
  const loaded = Array.isArray(data.loaded) ? data.loaded.length : 0
  const total = Number(data.total) || 0
  // 불러온 수는 전체(살아 있는 호기)와 같은 기준 — 지울 목록에 든 호기는 표에 남아도 세지 않는다.
  const shown = Number.isFinite(data.loadedCount) ? data.loadedCount : loaded
  const info = el('div', 'emg-info')
  const count = el('span')
  count.appendChild(el('span', null, '불러온 호기 '))
  count.appendChild(el('b', null, shown.toLocaleString()))
  count.appendChild(el('span', 'emg-muted', '대 / 전체 ' + total.toLocaleString() + '대'))
  info.appendChild(count)
  if (loaded) info.appendChild(button('emg-link', '목록 비우기', () => S.setTrigger('clear', {})))
  if (total) {
    const all = tipWrap(button('emg-link', '전체 ' + total.toLocaleString() + '대 불러오기', () => load(S, 'all', [], [], '전체')), 'emg-all-tip')
    lockButton(all, loadAllLockText(shown, total), 'load-all')
    info.appendChild(all.host)
  }
  const missing = Array.isArray(data.missing) ? data.missing : []
  if (missing.length) info.appendChild(el('span', 'emg-miss', '못 찾은 설비명: ' + missing.join(', ')))
  root.appendChild(info)
  if (!loaded) root.appendChild(emptyState(S, data, alertIds, total))
  S.painting = false
  const focus = S.refocus
  S.refocus = null
  // 「엑셀·CSV로 한꺼번에」 팝업이 닫혔다(파이썬이 닫힐 때마다 센 수 `dialogClosed`) — Streamlit 은 닫은 뒤 초점을 그림자
  // DOM 안 여는 단추로도, 팝업을 열며 닫힌 메뉴 안 단추로도 돌려주지 못해 BODY 로 빠진다. 첫 화면 단추로
  // 열었으면 그 단추(넣어서 사라졌으면 메뉴 단추), 메뉴로 열었으면(`dialogFromMenu`) 메뉴 단추로 초점이 빈 때만 돌린다.
  const closed = Number(data.dialogClosed) || 0
  const justClosed = S.dialogClosed !== null && closed !== S.dialogClosed
  const opener = justClosed ? S.dialogOpener : null
  S.dialogClosed = closed
  if (opener) S.dialogOpener = null
  let back = null
  if (opener) back = root.querySelector('[data-fk="' + opener + '"]') || menuButton(data)
  else if (justClosed && data.dialogFromMenu) back = menuButton(data)
  if (back && focusIsFree(host)) back.focus()
  else if (focus === 'search' && S.searchInput && focusIsFree(host)) {
    S.searchInput.focus()
    S.searchInput.setSelectionRange(S.query.length, S.query.length)
  } else restoreFocus(host, saved)
}

// 왼쪽 칸 폭으로 고르는 불러오기 줄 꼴 — 메뉴 자리(`reserve`)까지 한 줄에 못 들면 `stack`(메뉴가 찾기 칸 위 제 줄에 서고 찾기
// 칸은 폭을 다 쓴다), 찾기 칸 혼자도 못 들면 `tight`(「불러오기」 가 입력 칸 아래로 내려간다). 브라우저 안 보기 상태다(UI-PRF-04).
function loaderFit(width, reserve) {
  if (width < SEARCH_LINE_PX) return 'tight'
  return width < SEARCH_LINE_PX + reserve ? 'stack' : ''
}

// 숨은 탭에서는 폭이 0 이다 — 탭을 열어 폭이 생기면 관찰자가 다시 고른다. 메뉴 자리는 접힘에 따라 페이지 CSS 가 정한다.
function fitLoader(host) {
  const width = host.clientWidth
  if (!width) return
  const reserve = parseFloat(window.getComputedStyle(host).getPropertyValue('--emd-tools-reserve')) || 0
  const fit = loaderFit(width, reserve)
  if (host.dataset.lb !== fit) host.dataset.lb = fit
}

function watchLoaderFit(host, S) {
  fitLoader(host)
  if (S.fitObserver || typeof ResizeObserver !== 'function') return
  S.fitObserver = new ResizeObserver(() => fitLoader(host))
  S.fitObserver.observe(host)
}

// 불러오기 줄 끝의 메뉴 「엑셀·CSV」 를 여는 단추 — 표 컴포넌트 밖 Streamlit 팝오버다(패널은 포털이라 이 칸의 단추는 이것 하나).
function menuButton(data) {
  return data.menuKey ? document.querySelector('.st-key-' + data.menuKey + ' button') : null
}

// 첫 화면 「엑셀·CSV로 한꺼번에」 — 누른 단추를 적어 두고 팝업이 닫힌 회차에 초점을 그리로 돌린다(`drawLoader`).
function firstImportButton(S) {
  const press = button('emg-btn is-primary', '엑셀·CSV로 한꺼번에', () => {
    S.dialogOpener = 'import-first'
    S.setTrigger('dialog', { name: 'import' })
  })
  press.dataset.fk = 'import-first'
  return press
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
  if (S.lockSearchGo) S.lockSearchGo()
}

function emptyState(S, data, alertIds, total) {
  const box = el('div', 'emg-empty')
  const buttons = el('div', 'emg-row-buttons')
  // 빈 표는 값 한 줄(「…없습니다」)만 — 하는 법은 그 줄의 풍선(title)이다(설계 규칙 UI-TXT-01 · UI-TXT-04).
  if (data.firstData) {
    box.appendChild(el('b', null, '저장된 설비 데이터가 없습니다'))
    box.title = '첫 데이터는 「엑셀·CSV로 한꺼번에」 로 붙여 넣고, 「저장 전 변경」 에서 리비전을 저장합니다'
    buttons.appendChild(firstImportButton(S))
    if (data.newEnabled) {
      const fresh = button('emg-btn', '+ 새 호기', () => S.setTrigger('new', {}))
      fresh.disabled = Boolean(data.newRowsLocked)
      buttons.appendChild(fresh)
    }
  } else {
    box.appendChild(el('b', null, '불러온 호기가 없습니다'))
    box.title = '고칠 호기를 먼저 불러옵니다 — 위 칸에 설비명을 치거나, 메일·엑셀의 설비명 목록을 붙여 넣거나, 「공정별」 로 불러옵니다'
    const alerts = button('emg-btn', '일정 확인 ' + alertIds.length.toLocaleString() + '대 불러오기', () => load(S, 'alerts', alertIds, [], '일정 확인'))
    alerts.disabled = !alertIds.length
    alerts.title = ALERTS_TIP
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
  // 작업 줄이 한 줄이라 좁으면 자리표시 글이 잘린다(말줄임) — 다 읽는 자리는 풍선이다.
  input.title = input.placeholder
  input.setAttribute('aria-label', '설비명으로 불러오기')
  input.autocomplete = 'off'
  input.dataset.fk = 'search'
  S.searchInput = input
  box.appendChild(input)
  const go = tipWrap(button('emg-btn is-small is-primary', '불러오기', () => loadQuery(S, model)), 'emg-search-tip')
  S.lockSearchGo = () => lockButton(go, searchLockText(S.query), 'search-go')
  S.lockSearchGo()
  const list = el('div', 'emg-pop is-full')
  S.searchList = list
  list.setAttribute('role', 'listbox')
  list.setAttribute('aria-label', '맞는 설비명')
  const paintSuggestions = () => {
    list.textContent = ''
    const query = S.query.trim()
    S.lockSearchGo()
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
  box.appendChild(go.host)
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

// 팝오버를 열면 초점을 패널 안 첫 칸(입력·고르는 칸·단추)으로 — 열자마자 누른 Esc 가 패널에 닿는다. 이미 패널 안이면 그대로.
function enterPanel(panel) {
  const active = activeIn(panel)
  if (active && panel.contains(active)) return
  const first = panel.querySelector('input, select, button')
  if (first) first.focus()
}

// `label` 은 줄에 서는 짧은 이름, `fullName` 은 풍선 · 패널 접근성 이름에 남는 원래 이름이다.
function popover(S, name, label, fullName, build, wide) {
  const wrap = el('div', 'emg-pop-wrap')
  const toggle = button('emg-btn', label + ' ', () => {
    S.pop = S.pop === name ? null : name
    paint()
    if (S.pop === name) enterPanel(panel)
  })
  const caret = el('span')
  caret.innerHTML = ICONS.down
  toggle.appendChild(caret)
  toggle.setAttribute('aria-haspopup', 'dialog')
  toggle.title = fullName
  // 패널 안에서 불러오고 닫으면 초점이 여는 단추로 온다 — 불러오기 회차가 다시 지어도 그 단추로 돌아온다(data-fk).
  toggle.dataset.fk = 'pop-' + name
  const panel = el('div', 'emg-pop' + (wide ? ' is-wide' : ''))
  panel.setAttribute('role', 'dialog')
  panel.setAttribute('aria-label', fullName)
  // 패널이 초점을 받는다(Tab 정지는 아님) — 안내 글·여백을 누르면 초점이 초점 받는 가장 가까운 조상으로 가는데, 패널이 그
  // 조상이 아니면 본문 stMain 으로 빠져 Esc 가 패널의 keydown 에 닿지 않고 열린 채 남았다(2026-10-27 E2E).
  panel.tabIndex = -1
  const close = () => {
    S.pop = null
    paint()
    toggle.focus()
  }
  panel.addEventListener('keydown', (event) => {
    stopKeys(event)
    if (event.key === 'Escape') close()
  })
  // 열린 채 여는 단추로 돌아와도(Shift+Tab) Esc 로 닫는다. 닫혀 있으면 Esc 를 막지 않는다.
  toggle.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || S.pop !== name) return
    stopKeys(event)
    close()
  })
  // 초점이 패널·여는 단추 밖으로 나가면(Tab) 닫는다 — 열린 채 남으면 초점이 간 칸(오른쪽 호기 상세 등)을 덮고, 그 칸의 Esc
  // 는 패널에 닿지 않는다. 받을 칸이 없는 나감(다시 지으며 지운 칸·창 밖)은 닫지 않는다. 초점은 옮겨 간 칸에 둔다.
  // 패널 안 글자·여백을 누른 나감도 닫지 않는다 — 초점을 못 받는 칸을 누르면 초점이 초점 받는 가장 가까운 조상(본문
  // stMain)으로 가 relatedTarget 이 감싸개 밖이 된다. 누름 뒤 초점 이동은 같은 일 안이라 다음 일에 표를 걷는다.
  let pressed = false
  wrap.addEventListener('mousedown', () => {
    pressed = true
    setTimeout(() => { pressed = false }, 0)
  })
  wrap.addEventListener('focusout', (event) => {
    const next = event.relatedTarget
    if (S.pop !== name || pressed || !next || wrap.contains(next)) return
    S.pop = null
    paint()
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
    build(panel, paint, close)
    const rect = panel.getBoundingClientRect()
    const shift = popoverShift(rect.left, rect.width, document.documentElement.clientWidth, 8)
    if (shift) panel.style.left = shift + 'px'
    restoreFocus(panel, saved)
  }
  wrap.appendChild(toggle)
  wrap.appendChild(panel)
  paint()
  // 문서 mousedown 이 불러오기 줄의 다른 단추 누름에 이 팝오버만 닫는다(`closeOtherPress`) — 다시 짓지 않는다.
  S.pops[name] = { wrap, hide: () => {
    if (S.pop !== name) return
    S.pop = null
    paint()
  } }
  return wrap
}

// 불러오기 줄 안에서 열린 팝오버 밖(일정 확인·목록 비우기·전체 불러오기·찾기·다른 팝오버)을 누르면 그
// 팝오버를 닫는다 — 열린 채 남아 오른쪽 칸을 덮었다(E2E). 누른 단추가 지워지면 click 이 서지 않으므로 다시 짓지 않고 패널만 닫는다.
function closeOtherPress(S, path, target) {
  const open = S.pops[S.pop]
  if (!open) return
  const within = path ? path.includes(open.wrap) : open.wrap.contains(target)
  if (!within) open.hide()
}

function processPopover(S, model) {
  return popover(S, 'process', '공정별', '공정으로 불러오기', (panel, repaint, done) => {
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
          done()
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
  // 팝업 머리에 하는 법을 늘 두지 않는다 — 여는 단추의 풍선이다(설계 규칙 UI-TXT-01).
  const wrap = popover(S, 'conditions', '조건별', '조건으로 불러오기', (panel, repaint, done) => {
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
      done()
      load(S, 'conditions', rows.map((row) => model.ids[row]), [], '조건 「' + label + '」')
    })
    const tipped = tipWrap(go, 'emg-cond-tip')
    lockButton(tipped, conditionLockText(picked.length, rows.length), 'cond-go')
    actions.appendChild(tipped.host)
    panel.appendChild(actions)
  }, true)
  // 감싸개의 첫 칸이 여는 단추다(`popover` — 둘째 칸이 패널).
  const toggle = wrap.children[0]
  if (toggle) toggle.title = '조건으로 불러오기 — 칸과 값을 골라 모두 맞는 호기를 불러옵니다'
  return wrap
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
  S.repaintNote()
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
  // 고른 줄 띠는 표 틀 맨 끝에 서고, 표 아래 끝이 창 밖이면 창 아래 끝에 붙는다(서식 `sticky`). 맨 끝이라 줄을 골라도 위 칸이
  // 밀리지 않고(설계 규칙 UI-PRF-03) 다른 칸을 덮어 두지 않으며, 본문을 어디까지 굴렸든 조작이 창 안에 있다.
  const sel = el('div', 'emg-sel')
  const note = el('div', 'emg-note')
  note.setAttribute('role', 'status')
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
  // 키보드 조작은 표지 하나와 그 풍선이다 — 표 밑에 늘 세우지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-02).
  const keys = el('span', 'emg-muted emg-keys', '⌨ 키보드 조작')
  keys.title = KEYS_HELP
  const legend = el('span', 'emg-legend')
  for (const [kind, label] of [['is-changed', '고친 칸'], ['is-error', '오류'], ['is-locked', '잠긴 칸(모듈 좌표 등)']]) {
    const item = el('span')
    item.appendChild(el('span', 'emg-swatch ' + kind))
    item.appendChild(el('span', null, label))
    legend.appendChild(item)
  }
  foot.appendChild(keys)
  foot.appendChild(legend)
  for (const part of [bar, note, box, foot, sel]) root.appendChild(part)
  host.appendChild(root)
  Object.assign(S, { skeleton: true, root, bar, selBar: sel, noteBar: note, scroller: box, table, head, body, foot })
  S.repaintNote = () => fillNote(S, S.noteBar, null)
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
    // 표 밖에서 들어온 초점만 — 표를 굴려 칸을 다시 그릴 때 돌려준 초점은 사람이 옮긴 것이 아니다.
    if (cell && event.relatedTarget && !body.contains(event.relatedTarget)) clearOfBar(S, cell.dataset.id)
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
  // 표지 낱말 셋만 둔다 — 어디에 저장되는지는 표지 풍선이 말한다(설계 규칙 UI-TXT-01, 긴 시나리오 이름이 범례를 제 줄로 내리지 않게).
  const legend = el('div', 'emg-legend')
  const scenarioData = S.data.scenario || {}
  const scenario = scenarioData.name || '지금 설비 시나리오'
  const scope = (kind, word, tip) => {
    const mark = el('span', 'emg-scope' + kind, word)
    mark.title = tip
    legend.appendChild(mark)
  }
  scope(' is-scenario', '시나리오', scenario + '에만 저장')
  // 배치 칸은 공식 설비 시나리오면 공식 배치, 가정이면 그 시나리오의 배치 차이로 간다(설비 시나리오 2단계 S3).
  scope(' is-layout', '배치', scenarioData.official === false ? scenario + '에만 저장(공식과 다른 것만)' : '공식 배치에 저장')
  scope('', '공통', '모든 설비 시나리오에 함께 저장')
  bar.appendChild(legend)
}

// 자리에 남는 한 줄(표·오른쪽 칸 공용) — 브라우저 한 줄(`showNote`)과 그 칸에서 고칠 파이썬 거부(`toast` — 오른쪽 칸만). 동작
// 결과는 알림창으로 간다(설계 규칙 UI-NTF-03).
function fillNote(S, bar, toast) {
  bar.textContent = ''
  if (toast && toast.id !== S.lastToast) {
    // 파이썬이 새 거부를 보냈다 — 브라우저 한 줄은 거둔다.
    S.lastToast = toast.id
    S.note = ''
  }
  const text = S.note || (toast && toast.id !== S.toastClosed ? toast.text : '')
  bar.hidden = !text
  if (!text) return
  bar.appendChild(el('span', null, text))
  bar.appendChild(icon('close', '알림 닫기', () => {
    if (S.note) S.note = ''
    else S.toastClosed = toast.id
    fillNote(S, bar, toast)
  }))
}

function selectedRows(S) {
  return S.model.live.filter((row) => S.selected.has(row.id))
}

function paintSelection(S) {
  const bar = S.selBar
  const main = pageMain()
  const scrolled = main ? main.scrollTop : 0
  const saved = captureFocus(bar)
  S.painting = true
  bar.textContent = ''
  buildSelection(S, bar)
  S.painting = false
  restoreFocus(bar, saved)
  holdPlace(S, main, scrolled)
}

// 띠를 닫아 본문이 줄면 띠 자리까지 굴려 둔 스크롤이 잘려 표가 그만큼 내려앉는다 — 잘린 만큼 표 틀 아래 자리를 남겨 표를 그 자리에
// 둔다(설계 규칙 UI-PRF-03). 띠가 다시 서면 걷는다.
function holdPlace(S, main, scrolled) {
  if (!S.selBar.hidden) {
    S.root.style.marginBottom = ''
    return
  }
  const cut = main ? overPx(scrolled, main.scrollTop) : 0
  if (!cut) return
  S.root.style.marginBottom = cut + 'px'
  main.scrollTop = scrolled
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
    const option = el('option', null, column.name + (SCOPE_LABELS[column.scope] ? ' (' + SCOPE_LABELS[column.scope] + ')' : ''))
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
    if (sendOnce(S, { op: 'set', ids: targets, col: column.name, text: S.bulkValue }, targets.map((id) => [id, col, S.bulkValue]))) paintWindow(S)
  })
  const applyTip = tipWrap(apply, 'emg-apply-tip')
  const repaintApply = () => {
    const m = count()
    apply.textContent = '넣기 (' + m.toLocaleString() + '칸)'
    const reason = rows.length && col >= 0 && rows.every((row) => locked(row, col)) ? S.model.reasons[lockOf(rows[0], col, S.model.locks)] : ''
    lockButton(applyTip, applyLockText(m, ready, reason || ''), 'bulk-apply')
  }
  if (column.kind === 'choice') {
    const chips = el('div', 'emg-chips')
    // 여러 줄에 한 값을 넣으니 줄마다 다른 동으로 좁히지 않는다 — 칸 단위 선택지 그대로(`choiceOptions` 를 거치지 않음).
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
    input.placeholder = column.kind === 'date' ? DATE_PLACEHOLDER + ' (비우면 지움)' : '값 (비우면 지움)'
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
  bar.appendChild(applyTip.host)
  bar.appendChild(el('span', 'emg-vsep'))
  // 「반입·Qual 일정 [n] 일 밀기」 는 한 덩이로 줄을 바꾼다 — 줄이 좁으면 단위 「일」 만 다음 줄로 넘어가 칸과 떨어졌다(E2E).
  const shiftGroup = el('span', 'emg-shift')
  shiftGroup.appendChild(el('span', null, '반입·Qual 일정'))
  const days = el('input', 'emg-input emg-days')
  days.value = S.days
  days.setAttribute('aria-label', '밀 날 수')
  days.dataset.fk = 'bulk-days'
  shiftGroup.appendChild(days)
  shiftGroup.appendChild(el('span', null, '일'))
  const dateCols = columns.map((c, k) => (c.name === '반입일정' || c.name === 'Qual일정' ? k : -1)).filter((k) => k >= 0)
  const shift = button('emg-btn is-small', '', () => {
    const value = parseDays(S.days)
    if (value === null) return
    const targets = rows.map((row) => row.id)
    const cells = []
    for (const row of rows) for (const k of dateCols) if (!locked(row, k) && shiftIso(String(row.values[k] || ''), value)) cells.push([row.id, k, shiftIso(String(row.values[k]), value)])
    if (sendOnce(S, { op: 'shift', ids: targets, days: value }, cells)) paintWindow(S)
  })
  const shiftTip = tipWrap(shift, 'emg-shift-tip')
  const held = lockedShiftCell(rows, dateCols, locked)
  const shiftReason = held ? S.model.reasons[lockOf(held[0], held[1], S.model.locks)] : ''
  const repaintShift = () => {
    const value = parseDays(S.days)
    const k = planShift(rows, dateCols, value, locked)
    shift.textContent = '밀기 (' + k.toLocaleString() + '칸)'
    lockButton(shiftTip, shiftLockText(k, value, shiftReason || ''), 'bulk-shift')
  }
  days.addEventListener('input', () => {
    S.days = days.value
    repaintShift()
  })
  days.addEventListener('keydown', stopKeys)
  repaintShift()
  shiftGroup.appendChild(shiftTip.host)
  bar.appendChild(shiftGroup)
  bar.appendChild(el('span', 'emg-vsep'))
  const lock = S.data.deleteLock
  const deletable = rows.filter((row) => !(lock && row.tag !== 'new'))
  const remove = button('emg-btn is-small is-danger', '선택 ' + rows.length.toLocaleString() + '대 지우기', () => {
    enqueue(S, { op: 'delete', ids: rows.map((row) => row.id) }, [])
    S.selected = new Set()
    send(S)
    paintSelection(S)
    refocusTable(S, rows[0].id)
  })
  remove.disabled = deletable.length === 0
  remove.title = lock || (rows.some((row) => row.tag !== 'new') ? DELETE_TIP : '')
  bar.appendChild(remove)
  bar.appendChild(button('emg-btn is-small is-ghost', '선택 풀기', () => {
    const first = rows[0].id
    S.selected = new Set()
    S.anchor = null
    paintSelection(S)
    refocusTable(S, first)
  }))
}

// 고른 줄 띠가 닫히는 단추(지우기·선택 풀기)는 누른 단추가 사라진다 — 초점을 표 본문의 초점 칸(없으면 고른 첫 줄의
// 설비명)으로 돌린다. 그대로 두면 문서 맨 앞(BODY)으로 빠져 다음 Tab 이 사이드바 머리로 간다.
function refocusTable(S, fallbackId) {
  const known = S.focus && S.model.ordered.some((row) => row.id === S.focus.id)
  if (!known) S.focus = { id: fallbackId, col: S.model.nameCol }
  ensureVisible(S, S.focus.id)
  S.wantFocus = true
  paintWindow(S)
}

function headCell(S, k) {
  const column = S.model.columns[k]
  const cell = el('div', 'emg-c emg-w-' + column.width + (SCOPE_LABELS[column.scope] ? ' is-' + column.scope : ''))
  cell.setAttribute('role', 'columnheader')
  cell.setAttribute('aria-colindex', String(k + 1))
  const sort = S.sort && S.sort.col === k ? (S.sort.dir === 'asc' ? ' ▲' : ' ▼') : ''
  const press = button('emg-hb', null, () => toggleSort(S, k))
  press.appendChild(el('span', null, column.name + sort))
  if (SCOPE_LABELS[column.scope]) press.appendChild(el('small', null, SCOPE_LABELS[column.scope]))
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
  const caret = keptCaret(S, active)
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

// 다시 그려도 이어 쓸 글자 자리 — 초점 든 편집 칸이 다시 그린 뒤에도 같은 칸으로 열려 있을 때만이다. Tab · ↓ 로 다음 칸을
// 열면 나가는 칸의 자리를 새 칸에 넘기지 않는다 — 넘기면 새 칸의 「값 통째로 고름」 을 이겨 친 글이 옛 값 안에 끼었다
// (「MI」 칸 뒤 Tab 하고 「D1」 → 「MID1」).
function keptCaret(S, active) {
  if (!active || !active.classList || !active.classList.contains('emg-ed') || !S.edit) return null
  const cell = active.closest('.emg-c')
  if (!cell || cell.dataset.id !== S.edit.id || Number(cell.dataset.col) !== S.edit.col) return null
  return [active.selectionStart, active.selectionEnd]
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
    const back = icon('undo', name + ' 되살리기', () => sendOnce(S, { op: 'restore', ids: [row.id] }, []))
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
  const nameTip = [errors[model.nameCol] !== undefined ? '오류: ' + errors[model.nameCol] : '', changed[model.nameCol] !== undefined ? '저장본: ' + changed[model.nameCol] : '', row.alert || '', tag === 'deleted' ? '지운 호기 — Space 로 되살립니다' : '', '누르면 오른쪽에 이 호기의 모든 칸이 열립니다']
  open.title = nameTip.filter(Boolean).join('\n')
  open.setAttribute('aria-label', (name || '새 호기') + ' 상세 열기' + (tag === 'deleted' ? ' (지운 호기 — Space 로 되살리기)' : ''))
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
    const input = textEditor('emg-ed', S.edit.draft)
    input.placeholder = column.kind === 'date' ? DATE_PLACEHOLDER : ''
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
    const options = choiceOptions(model.columns, column, rowValueAt(S, row), value)
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
  const options = choiceOptions(S.model.columns, column, rowValueAt(S, row), current)
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
  clearOfBar(S, id)
}

// 띠가 창 아래 끝에 붙으면 그 자리의 줄을 덮는다 — 방금 고른 줄 · 초점이 간 줄이 그 밑에 들면 덮인 만큼만 본문을 올린다. 덮이지
// 않으면 아무것도 움직이지 않는다(설계 규칙 UI-PRF-03). 다시 그린 뒤의 자리를 재려고 다음 프레임에 본다.
function clearOfBar(S, id) {
  const frame = typeof window !== 'undefined' && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : (fn) => setTimeout(fn, 0)
  frame(() => {
    const main = pageMain()
    const line = S.body.querySelector('[data-id="' + cssEscape(id) + '"]')
    if (!main || !line || S.selBar.hidden) return
    const lift = overPx(line.getBoundingClientRect().bottom, S.selBar.getBoundingClientRect().top)
    if (lift) main.scrollTop += lift
  })
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
  clearOfBar(S, id)
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
    const editRow = S.model.rows.find((item) => item.id === S.edit.id) || { id: S.edit.id, values: [] }
    const options = choiceOptions(S.model.columns, column, rowValueAt(S, editRow), S.edit.original)
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
    const next = moveFocus(model.ordered.map((row) => row.id), columns, { id, col }, moves[event.key])
    if (next) {
      S.focus = next
      ensureVisible(S, S.focus.id)
      S.wantFocus = true
      paintWindow(S)
    }
    return
  }
  if (event.key === ' ' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Space = 그 줄의 체크 칸 — 산 줄은 고르기(Shift+Space 는 기준 줄부터 범위), 지운 줄은 되살리기. 체크 칸은
    // Tab 정지가 아니다.
    event.preventDefault()
    if (live.some((row) => row.id === id)) toggleRow(S, id, event.shiftKey)
    else if (model.ordered.some((row) => row.id === id && row.tag === 'deleted')) sendOnce(S, { op: 'restore', ids: [id] }, [])
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
    showNote(S, '한 번에 ' + (Number((S.data.limits || {}).pasteCells) || 5000).toLocaleString() + '칸까지 붙입니다 — 더 많으면 「엑셀·CSV」 의 「엑셀·CSV로 한꺼번에」 를 씁니다')
    return
  }
  S.edit = null
  const pendingCells = []
  plan.rows.forEach((line, r) => line.forEach((value, c) => {
    if (value !== null) pendingCells.push([plan.ids[r], byName.get(plan.cols[c]), value])
  }))
  const queued = enqueue(S, { op: 'paste', ids: plan.ids, cols: plan.cols, rows: plan.rows, cut: plan.cut, skipped: plan.skipped }, pendingCells)
  if (queued) showNote(S, '붙여넣는 중 — ' + cells.length.toLocaleString() + '줄', queued.seq)
  send(S)
  S.wantFocus = true
  paintWindow(S)
}

// ---------------------------------------------------------------- side

function drawSide(host, S, data) {
  receive(S, data)
  S.data = data
  S.host = host
  const saved = captureFocus(host)
  S.painting = true
  host.textContent = ''
  const root = el('div', 'emg-side')
  host.appendChild(root)
  // 이 칸에서 고칠 거부 · 브라우저 한 줄은 칸 머리에 선다. 동작 결과는 알림창으로 간다.
  const note = el('div', 'emg-note')
  note.setAttribute('role', 'status')
  root.appendChild(note)
  S.repaintNote = () => fillNote(S, note, S.data && S.data.toast)
  const first = !S.sideDrawn
  S.sideDrawn = true
  S.repaintNote()
  if (data.panel === 'changes') drawChanges(S, root, data)
  else if (data.panel === 'new') drawNew(S, root, data)
  else drawDetail(S, root, data)
  S.painting = false
  restoreFocus(host, saved)
  // 칸 아래쪽에서 누른 조작이 연 다른 칸(「호기 추가」 → 상세, 「이 호기로 새 호기 만들기」 → 새 호기 칸)은 그 칸 머리를 보인다 —
  // 스크롤이 그대로면 새 칸의 가운데부터 보여 무엇이 열렸는지 모른다.
  if (first && data.revealHead) revealHead(root)
  if (!S.sideBound) {
    S.sideBound = true
    listen(S, host, 'keydown', stopKeys)
  }
}

function revealHead(head) {
  const frame = typeof window !== 'undefined' && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : (fn) => setTimeout(fn, 0)
  frame(() => {
    if (!head.isConnected) return
    // 넘치는 스크롤 칸(설비 마스터 오른쪽 칸 본문 칸) 안이면 먼저 그 칸만 올린다 — 바로 scrollIntoView 하면 Chrome 이 붙은
    // (sticky) 자리가 아니라 원래 흐름 자리로 셈해 바깥 페이지(stMain)까지 밀어 왼쪽 표가 튄다(사본 앱 1500×950 에서 0 → 223px).
    // 칸 위 끝 아래·머리 띠 아래에 가려 있던 머리(칸이 조금만 내려가 있을 때)도 이 길로 보인다.
    const box = scrollBoxOf(head)
    if (box) {
      const next = boxScrollFor(box.scrollTop, head.getBoundingClientRect().top, box.getBoundingClientRect().top)
      if (next !== box.scrollTop) box.scrollTop = next
    }
    // 그래도 머리 띠 아래로 가려 있으면(칸이 페이지 흐름에 있을 때 — 좁은 창에서 쌓인 칸 등) 칸 머리를 보인다.
    if (needsReveal(head.getBoundingClientRect().top, HEAD_REVEAL_MARGIN)) head.scrollIntoView({ block: 'start' })
  })
}

function pageMain() {
  return typeof document !== 'undefined' && document.querySelector ? document.querySelector(PAGE_SCROLLER) : null
}

// 칸 머리를 감싼 가장 가까운 넘치는 스크롤 칸 — 그림자 DOM 밖으로 건너 올라간다. 페이지 본문(`PAGE_SCROLLER`)에 닿거나 못
// 찾으면 null.
function scrollBoxOf(node) {
  if (typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') return null
  for (let at = node; at;) {
    let up = at.parentElement || null
    if (!up) {
      const root = at.getRootNode ? at.getRootNode() : null
      up = root && root.host ? root.host : null
    }
    if (!up || (up.matches && up.matches(PAGE_SCROLLER))) return null
    const overflow = window.getComputedStyle(up).overflowY
    if ((overflow === 'auto' || overflow === 'scroll') && up.scrollHeight > up.clientHeight) return up
    at = up
  }
  return null
}

// 화면 위를 가리는 높이 — 머리 띠 밑에 붙는 화면 탭 줄(sticky, `app_header.PAGE_TABS_SELECTOR`)이 있으면 그 아래 끝, 없으면
// 머리 띠(`HEAD_REVEAL_MARGIN`). 그 아래 조금(8px) 띄운다.
function coverHeight() {
  const strip = typeof document !== 'undefined' && document.querySelector ? document.querySelector(PAGE_TABS_STRIP) : null
  const bottom = strip && strip.getBoundingClientRect ? Number(strip.getBoundingClientRect().bottom) || 0 : 0
  return Math.round(Math.max(HEAD_REVEAL_MARGIN, bottom)) + 8
}

// 「비가동 일정 표에서 고치기」 — 그 표는 왼쪽 칸 맨 위에 선다. 긴 호기 상세 맨 아래에서 누르면 화면이 내려간 채라 왼쪽이
// 빈 칸처럼 보였다(E2E). 누를 때 두 칸 줄(그림자 DOM 밖 Streamlit 가로 줄 — 못 찾으면 이 칸)의 머리가 가린 높이 위로 나가
// 있으면 그 머리를 머리 띠·화면 탭 줄 아래로 올린다. 다시 그린 회차에도 두 칸 줄의 자리는 같다(위 줄·알림은 그대로).
function revealColumnsTop(host) {
  if (!host) return
  const root = host.getRootNode ? host.getRootNode() : null
  const outer = root && root.host ? root.host : host
  const row = (outer.closest && outer.closest('[data-testid="stHorizontalBlock"]')) || host
  if (!row.getBoundingClientRect || !row.scrollIntoView) return
  const cover = coverHeight()
  if (!needsReveal(row.getBoundingClientRect().top, cover)) return
  row.style.scrollMarginTop = cover + 'px'
  row.scrollIntoView({ block: 'start' })
}

function drawDetail(S, root, data) {
  const unit = data.unit
  if (!unit) {
    S.unitId = null
    S.drafts.clear()
    const empty = el('p', 'emg-side-empty', '고른 호기가 없습니다')
    empty.title = '표에서 설비명을 누르면 그 호기의 모든 칸이 여기 한 장에 펼쳐집니다'
    root.appendChild(empty)
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
    title.appendChild(el('span', 'emg-scope' + (SCOPE_LABELS[group[2]] ? ' is-' + group[2] : ''), SCOPE_LABELS[group[2]] || '공통'))
    // 묶음의 뜻(「어떤 설비인가」 · 좌표를 고치는 곳)은 머리의 풍선이다 — 머리에 늘 적지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-03).
    if (group[3]) title.title = group[3]
    box.appendChild(title)
    const fields = el('div', 'emg-fields')
    for (const k of group[4] || []) if (columns[k]) fields.appendChild(detailField(S, unit, columns[k], k, sets, reasons))
    box.appendChild(fields)
    // 가정 설비 시나리오에서 공식과 다른 자리의 호기 — 공식 자리 한 줄과 「공식 자리로 되돌리기」(모듈이면 묶음 통째).
    if (group[0] === 'place' && unit.official && unit.tag !== 'deleted') {
      const line = el('div', 'emg-official')
      line.appendChild(el('span', 'emg-muted', String(unit.official.text || '')))
      const count = Number(unit.official.count) || 1
      const back = button('emg-link', '공식 자리로 되돌리기' + (count > 1 ? ' (묶음 ' + count + '대)' : ''), () => sendOnce(S, { op: 'official', id: unit.id }, []))
      back.title = '이 호기의 배치 일곱 칸을 공식 값으로 — 저장하면 이 설비 시나리오의 배치 차이에서 빠집니다'
      line.appendChild(back)
      box.appendChild(line)
    }
    root.appendChild(box)
  }
  const downtime = el('div', 'emg-side-group')
  const title = el('h4')
  title.appendChild(el('span', null, '그 호기의 비가동 일정'))
  title.appendChild(el('span', 'emg-scope is-scenario', '시나리오'))
  downtime.appendChild(title)
  const rows = Array.isArray(unit.downtime) ? unit.downtime : []
  if (!rows.length) downtime.appendChild(el('span', 'emg-muted emg-none', '없음'))
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
    downtime.appendChild(button('emg-link', '비가동 일정 표에서 고치기', () => {
      revealColumnsTop(S.host)
      S.setTrigger('goto', { table: '비가동 일정', unit: values[nameCol] || '' })
    }))
  }
  root.appendChild(downtime)
  const actions = el('div', 'emg-side-actions')
  if (unit.tag === 'deleted') {
    actions.appendChild(button('emg-btn', '되살리기', () => sendOnce(S, { op: 'restore', ids: [unit.id] }, [])))
  } else {
    const remove = button('emg-btn is-danger', '이 호기 지우기', () => sendOnce(S, { op: 'delete', ids: [unit.id] }, []))
    remove.disabled = !unit.deletable
    remove.title = unit.deleteLock || (unit.tag === 'new' ? '' : DELETE_TIP)
    actions.appendChild(remove)
    const copy = button('emg-btn', '이 호기로 새 호기 만들기', () => S.setTrigger('copy', { id: unit.id }))
    copy.disabled = Boolean(data.newRowsLocked)
    copy.title = '오른쪽 「새 호기」 칸을 이 호기의 호기 정보·위치(동·층)로 채웁니다 — 설비명·일정·실적·좌표는 비웁니다'
    actions.appendChild(copy)
  }
  root.appendChild(actions)
}

// ---------------------------------------------------------------- side — 새 호기

const NEW_TIERS = [['required', '에러 없이 추가하려면'], ['calc', '가용대수에 세려면'], ['map', '도면에 놓으려면']]
// 화면 위 머리 띠(Streamlit 머리·화면 탭 줄)가 가리는 높이 — 이보다 위에 있는 칸 머리는 보이지 않는 것으로 친다.
const HEAD_REVEAL_MARGIN = 72
const TIER_TAGS = { required: '필수', calc: '가용대수', map: '도면' }

function drawNew(S, root, data) {
  const columns = Array.isArray(data.columns) ? data.columns : []
  const server = data.draft || {}
  const adopted = adoptDraft(S.nd, server)
  if (adopted !== S.nd) {
    S.nd = adopted
    S.ndSent = adopted.values.slice()
    S.ndTouched.clear()
    S.ndDirty.clear()
  }
  if (Number(data.checked) === S.nd.seq) S.ndDirty.clear()
  const locked = data.locked ? String(data.locked) : null
  const locks = data.locks || {}
  if (!locked) {
    for (const k of Object.keys(locks)) {
      S.nd.values[Number(k)] = ''
      S.ndSent[Number(k)] = ''
    }
  }
  const values = S.nd.values
  const fresh = Number(data.checked) === S.nd.seq
  const errors = data.errors || {}
  const warns = data.warns || {}
  const tiers = data.tiers || {}
  const required = (Array.isArray(data.required) ? data.required : []).map(Number)
  const base = new Set(required)
  // 칸 자리 → (체크 상자 줄, 파이썬 판정). Y/N 셋은 「필수」 표지로 그린다.
  const tierOf = new Map()
  for (const [name] of NEW_TIERS) for (const [k, ok] of tiers[name] || []) if (!tierOf.has(Number(k))) tierOf.set(Number(k), [name, ok])
  for (const [k, ok] of tiers.flags || []) tierOf.set(Number(k), ['required', ok])
  const done = (item) => tierDone(item[1], values[Number(item[0])], fresh && !S.ndDirty.has(Number(item[0])))
  const head = el('div', 'emg-side-head')
  // 넣는 차례는 칸 이름의 풍선이다 — 칸 머리에 늘 두지 않는다(설계 규칙 UI-TXT-01).
  const heading = el('div', 'emg-side-name', '새 호기 추가')
  heading.title = '한 장에 채우고 「호기 추가」를 누르면 표 맨 위에 들어가고, 리비전 저장 때 함께 저장됩니다'
  head.appendChild(heading)
  root.appendChild(head)
  if (locked) {
    root.appendChild(el('p', 'emg-side-empty', locked))
    return
  }
  // 체크 상자 — 막대는 「에러 없이 추가하려면」 칸(설비명·공정소분류·Y/N 셋)이 찬 비율.
  const check = el('div', 'emg-check')
  check.setAttribute('aria-live', 'polite')
  const must = (tiers.required || []).concat(tiers.flags || [])
  const ready = must.filter(done).length
  const bar = el('div', 'emg-progress')
  bar.setAttribute('role', 'progressbar')
  bar.setAttribute('aria-label', '에러 없이 추가하려면')
  bar.setAttribute('aria-valuemin', '0')
  bar.setAttribute('aria-valuemax', String(must.length))
  bar.setAttribute('aria-valuenow', String(ready))
  const fill = el('span')
  fill.style.width = (must.length ? Math.round((ready / must.length) * 100) : 0) + '%'
  bar.appendChild(fill)
  check.appendChild(bar)
  const flagsOk = (tiers.flags || []).every(done)
  for (const [name, title] of NEW_TIERS) {
    const line = el('div', 'emg-check-row')
    line.appendChild(el('span', 'emg-check-head', title))
    const items = (tiers[name] || []).concat(name === 'required' && !flagsOk ? tiers.flags || [] : [])
    for (const item of items) {
      const k = Number(item[0])
      const ok = done(item)
      const label = (columns[k] || {}).name || ''
      const shown = name === 'calc' && label === '사용기준' ? '사용기준 HBM·EDP' : label
      line.appendChild(el('span', 'emg-check-item ' + (ok ? 'is-ok' : name === 'required' ? 'is-no' : 'is-opt'), (ok ? '✓ ' : '· ') + shown))
    }
    if (name === 'required' && flagsOk) {
      check.appendChild(line)
      const note = el('div', 'emg-check-row')
      note.appendChild(el('span', 'emg-check-head'))
      const defaults = el('span', 'emg-muted', '기본값 · 보관유무 N · 기존설비여부 N · 레이아웃표시 Y')
      defaults.title = '필수 Y/N 칸을 기본값으로 채워 두었습니다'
      note.appendChild(defaults)
      check.appendChild(note)
      continue
    }
    if (name === 'map') {
      // 좌표 · 크기를 정하는 곳은 줄의 풍선이다 — 길 안내를 자리에 두지 않는다(설계 규칙 UI-TXT-03).
      if ((tiers.map || []).length) line.title = '좌표·크기는 Space 배치 편집기에서 정합니다'
      else {
        const off = el('span', 'emg-muted', '레이아웃표시 N')
        off.title = '도면에 그리지 않습니다'
        line.appendChild(off)
      }
    }
    check.appendChild(line)
  }
  const rest = el('div', 'emg-check-row')
  rest.appendChild(el('span', 'emg-check-head'))
  const optional = el('span', 'emg-muted', '나머지 칸 · 선택')
  optional.title = '나머지 칸은 비워도 됩니다. 넣은 값끼리 맞지 않으면(일정 차례 등) 칸 아래에 바로 알려 줍니다'
  rest.appendChild(optional)
  check.appendChild(rest)
  root.appendChild(check)
  // 안내는 글 하나이거나 [표지, 풍선] 짝이다(가정 배치 — 설계 규칙 UI-TXT-01).
  for (const note of Array.isArray(data.notes) ? data.notes : []) {
    const [text, tip] = Array.isArray(note) ? note : [note, '']
    const line = el('div', 'emg-sec emg-muted', String(text || ''))
    if (tip) line.title = String(tip)
    root.appendChild(line)
  }
  root.appendChild(copyRow(S))
  for (const group of data.groups || []) {
    const box = el('div', 'emg-side-group')
    const title = el('h4')
    title.appendChild(el('span', null, group[1]))
    title.appendChild(el('span', 'emg-scope' + (SCOPE_LABELS[group[2]] ? ' is-' + group[2] : ''), SCOPE_LABELS[group[2]] || '공통'))
    // 묶음의 뜻(「어떤 설비인가」 · 좌표를 고치는 곳)은 머리의 풍선이다 — 머리에 늘 적지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-03).
    if (group[3]) title.title = group[3]
    box.appendChild(title)
    const fields = el('div', 'emg-fields')
    for (const k of group[4] || []) {
      if (!columns[k]) continue
      const tier = tierOf.get(k) || null
      fields.appendChild(newField(S, columns[k], k, {
        tier: tier ? tier[0] : null,
        ok: tier ? done([k, tier[1]]) : false,
        error: errors[k], warn: warns[k], lock: locks[k],
        fresh: fresh && !S.ndDirty.has(k), base: base.has(k),
      }))
    }
    box.appendChild(fields)
    root.appendChild(box)
  }
  const foot = el('div', 'emg-side-actions emg-new-foot')
  const buttons = el('div', 'emg-row-buttons')
  const reset = button('emg-btn', '양식 비우기', () => {
    const blank = Array.isArray(data.blank) ? data.blank : S.nd.values.map(() => '')
    S.nd = { seq: S.nd.seq, values: blank.slice() }
    S.ndTouched.clear()
    S.ndDirty.clear()
    commitDraft(S)
    drawSide(S.host, S, S.data)
  })
  // 다시 그려도 초점이 이 단추로 돌아온다(data-fk — 칩도 같다). 키보드로 채우는 동안 칸 처음으로 가지 않게.
  reset.dataset.fk = 'reset'
  buttons.appendChild(reset)
  const add = button('emg-btn is-primary', '호기 추가', () => {
    for (const k of required) S.ndTouched.add(k)
    if (!canAdd(S.nd.values, required, Boolean(data.blocked), fresh && !S.ndDirty.size, locked)) {
      drawSide(S.host, S, S.data)
      return
    }
    enqueue(S, { op: 'add', draftSeq: S.nd.seq, draft: S.nd.values.slice() }, [])
    send(S)
  })
  // 막힌 까닭은 단추 풍선이다 — 칸에 늘 두지 않는다(설계 규칙 UI-TXT-01 · UI-INP-07). 꺼진 단추는 마우스 · 초점을
  // 받지 않아 감싼 칸이 받고, 그동안은 감싼 칸이 탭 자리와 다시 그릴 때의 초점(data-fk)을 맡는다.
  const addTipWrap = tipWrap(add, 'emg-add-tip')
  // 친 글이 보낸 초안과 다르면(아직 확정 전) 판정은 옛 것이다 — 필수 칸이 찼는지만 보고 켠다(누르면 칸이 먼저 확정되고
  // 「호기 추가」 가 그 초안 전부를 싣는다).
  S.refreshAdd = () => {
    const typed = S.nd.values.some((value, k) => value !== S.ndSent[k])
    const judged = fresh && !S.ndDirty.size && !typed
    add.disabled = !canAdd(S.nd.values, required, Boolean(data.blocked), judged, locked)
    const missing = required.filter((k) => String(S.nd.values[k] || '').trim() === '').map((k) => (columns[k] || {}).name || '')
    addTipWrap.tip.textContent = addTip(data.hint, judged, typed, missing)
    holdFocus(addTipWrap, 'add')
  }
  S.refreshAdd()
  buttons.appendChild(addTipWrap.host)
  foot.appendChild(buttons)
  root.appendChild(foot)
}

function commitDraft(S) {
  S.nd = bumpDraft(S.nd, (S.data && S.data.draft && S.data.draft.seq) || 0)
  S.ndSent = S.nd.values.slice()
  if (S.setState) S.setState('draft', { seq: S.nd.seq, values: S.nd.values.slice() })
}

function copyRow(S) {
  const row = el('div', 'emg-sec emg-copy')
  // 무엇을 가져오나는 줄의 풍선이다(설계 규칙 UI-TXT-01).
  row.title = '호기 정보·위치(동·층)만 가져옵니다 — 설비명·일정·실적·좌표는 가져오지 않습니다'
  row.appendChild(el('span', null, '비슷한 호기에서 값 가져오기'))
  const input = el('input', 'emg-input')
  input.type = 'text'
  input.value = S.copyQuery
  input.placeholder = '설비명 (예: WBA-08)'
  input.setAttribute('aria-label', '값을 가져올 설비명')
  input.dataset.fk = 'copy'
  const go = button('emg-btn is-small', '가져오기', null)
  go.disabled = !S.copyQuery.trim()
  const fire = () => {
    if (!S.copyQuery.trim()) return
    S.setTrigger('copy', { query: S.copyQuery.trim(), draft: { seq: S.nd.seq, values: S.nd.values.slice() } })
  }
  input.addEventListener('input', () => {
    S.copyQuery = input.value
    go.disabled = !S.copyQuery.trim()
  })
  input.addEventListener('keydown', (event) => {
    stopKeys(event)
    if (event.key === 'Enter') {
      event.preventDefault()
      fire()
    }
  })
  go.addEventListener('click', fire)
  row.appendChild(input)
  row.appendChild(go)
  return row
}

function newField(S, column, k, mark) {
  const field = el('div', 'emg-field' + (column.kind === 'memo' ? ' is-wide' : ''))
  const value = String(S.nd.values[k] || '')
  const showError = showsError(mark.error !== undefined, mark.fresh, value, S.ndTouched.has(k), mark.base)
  if (showError) field.classList.add('is-error')
  if (mark.tier === 'required' && !mark.ok && !showError) field.classList.add('is-need')
  if (S.ndDirty.has(k)) field.classList.add('is-pending')
  const id = 'emg-n-' + S.mount + '-' + k
  const label = el('label')
  label.htmlFor = id
  label.appendChild(el('span', null, column.name))
  if (mark.tier) label.appendChild(el('span', 'emg-tier is-' + mark.tier + (mark.ok ? ' is-done' : ''), TIER_TAGS[mark.tier]))
  field.appendChild(label)
  field.title = [mark.lock || '', column.help || ''].filter(Boolean).join('\n')
  // 확정 — 보낸 값(`ndSent`)과 다를 때만. 다시 그린 칸(초점 되돌림)도 보낸 값과 견주므로 친 글을 잃지 않는다.
  const commit = (text) => {
    S.nd.values[k] = text
    S.ndTouched.add(k)
    if (text === S.ndSent[k]) return
    S.ndDirty.add(k)
    commitDraft(S)
    if (S.refreshAdd) S.refreshAdd()
  }
  if (column.kind === 'choice' && !mark.lock) {
    const chips = el('div', 'emg-chips')
    chips.setAttribute('role', 'group')
    chips.setAttribute('aria-label', column.name)
    const columns = (S.data && Array.isArray(S.data.columns)) ? S.data.columns : []
    const options = choiceOptions(columns, column, (j) => S.nd.values[j], value)
    for (const option of options) {
      const chip = button('emg-chip', option || '(비움)', () => {
        commit(option)
        drawSide(S.host, S, S.data)
      })
      chip.dataset.fk = 'n' + k + '=' + option
      chip.setAttribute('aria-pressed', option === value ? 'true' : 'false')
      chips.appendChild(chip)
    }
    field.appendChild(chips)
  } else {
    const input = textEditor('emg-input', value)
    input.id = id
    input.dataset.fk = 'n' + k
    input.disabled = Boolean(mark.lock)
    if (column.kind === 'date') input.placeholder = DATE_PLACEHOLDER
    if (column.kind === 'name') input.placeholder = '예: WBA-11'
    input.addEventListener('input', () => {
      S.nd.values[k] = input.value
      if (S.refreshAdd) S.refreshAdd()
    })
    input.addEventListener('keydown', (event) => {
      stopKeys(event)
      if (event.key === 'Enter') {
        event.preventDefault()
        commit(input.value)
      } else if (event.key === 'Escape') {
        event.preventDefault()
        const sent = String(S.ndSent[k] || '')
        input.value = sent
        S.nd.values[k] = sent
        if (S.refreshAdd) S.refreshAdd()
      }
    })
    input.addEventListener('blur', () => {
      if (S.painting) return
      commit(input.value)
    })
    field.appendChild(input)
  }
  if (showError) field.appendChild(el('span', 'emg-field-error', mark.error))
  if (mark.warn !== undefined && mark.fresh) field.appendChild(el('span', 'emg-field-warn', mark.warn))
  if (mark.lock) field.appendChild(el('span', 'emg-muted emg-field-lock', mark.lock))
  return field
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
    const columns = (S.data && Array.isArray(S.data.columns)) ? S.data.columns : []
    const options = choiceOptions(columns, column, rowValueAt(S, unit), shown)
    for (const value of options) {
      const chip = button('emg-chip', value || '(비움)', () => {
        commit(value)
        S.drafts.delete(k)
        send(S)
      })
      // 회차가 돌아와 칸을 다시 그려도 초점이 같은 칩으로 돌아온다(data-fk).
      chip.dataset.fk = 'f' + k + '=' + value
      chip.setAttribute('aria-pressed', value === shown ? 'true' : 'false')
      chips.appendChild(chip)
    }
    field.appendChild(chips)
  } else {
    const input = textEditor('emg-input', S.drafts.has(k) ? S.drafts.get(k) : shown)
    input.id = id
    input.dataset.fk = 'f' + k
    input.disabled = Boolean(lock)
    if (column.kind === 'date') input.placeholder = DATE_PLACEHOLDER
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
    // 못 읽은 칸 초안 같은 고칠 것만 있으면 위 「저장하기 전에 고칠 것」 과 어긋나지 않게 말한다.
    root.appendChild(el('p', 'emg-side-empty', errors.length ? '고친 값은 없고 고칠 칸이 있습니다.' : '아직 고친 것이 없습니다.'))
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
    head.appendChild(button('emg-link', '이 호기 되돌리기', () => sendOnce(S, { op: 'revert', id: unit.id, col: null }, [])))
    box.appendChild(head)
    for (const [col, scope, before, after] of unit.lines || []) {
      const line = el('div', 'emg-line')
      const label = el('span', 'emg-muted', col)
      if (SCOPE_SHORT[scope]) label.appendChild(el('span', 'emg-scope is-' + scope, SCOPE_SHORT[scope]))
      line.appendChild(label)
      const value = el('span', 'emg-value')
      value.appendChild(el('span', 'emg-from', before || '(빈칸)'))
      value.appendChild(el('span', null, ' → '))
      value.appendChild(el('b', null, after || '(빈칸)'))
      line.appendChild(value)
      line.appendChild(icon('undo', col + ' 되돌리기', () => sendOnce(S, { op: 'revert', id: unit.id, col }, [])))
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
    // 표 밖으로 초점이 나가거나(「리비전 저장」 누름 포함) 창이 숨으면 기다리지 않고 보낸다 — 보낼 것이 있을 때만. 그리는 중의
    // focusout 은 다시 그려 초점 든 칸이 사라진 것이다 — 나간 것이 아니라 300ms 묶음을 끊지 않는다.
    listen(S, host, 'focusout', (event) => {
      if (!S.painting && (!event.relatedTarget || !host.contains(event.relatedTarget))) send(S)
      // 불러오기 밖(표 칸 등)으로 초점을 옮겼다 — 돌아온 불러오기 회차가 찾기 칸으로 초점을 빼앗지 않는다.
      if (!S.painting && event.relatedTarget && !host.contains(event.relatedTarget)) S.refocus = null
    })
    listen(S, document, 'visibilitychange', () => send(S))
    listen(S, document, 'mousedown', (event) => {
      // 그림자 DOM 밖에서 보면 대상이 호스트로 바뀐다 — 지나온 길(composedPath)로 안쪽 누름을 가른다.
      const path = typeof event.composedPath === 'function' ? event.composedPath() : null
      const inside = path ? path.includes(host) : host.contains(event.target)
      if (!S.pop || S.pop === 'search') return
      if (!inside) {
        S.pop = null
        if (S.data && S.data.mode === 'loader') drawLoader(host, S, S.data)
        return
      }
      closeOtherPress(S, path, event.target)
    })
  }
  if (data.mode === 'loader') {
    drawLoader(host, S, data)
    watchLoaderFit(host, S)
  } else if (data.mode === 'grid') drawGrid(host, S, data)
  else drawSide(host, S, data)
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    send(S)
    for (const [target, type, handler, options] of S.listeners) target.removeEventListener(type, handler, options)
    S.listeners = []
    if (S.timer) clearTimeout(S.timer)
    if (S.noteTimer) clearTimeout(S.noteTimer)
    if (S.scrollFrame) cancelAnimationFrame(S.scrollFrame)
    if (S.fitObserver) S.fitObserver.disconnect()
    S.fitObserver = null
    S.timer = 0
    S.noteTimer = 0
    S.scrollFrame = 0
    S.bound = false
    S.sideBound = false
    S.skeleton = false
  }
}
