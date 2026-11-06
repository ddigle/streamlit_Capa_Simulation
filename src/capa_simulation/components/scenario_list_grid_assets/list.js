// 시나리오 관리 › 목록 관리 표 — 한 등록을 세 자리(data.mode)에 마운트한다: scenarios(시나리오 표) · revisions(연 시나리오의
// 리비전 표와 값 줄) · changes(저장 전 변경).
// 브라우저 → 서버는 상태 값 `outbox` 하나다(반영되지 않은 조작 전부, mount·seq) — 트리거는 다음 트리거에 덮여 잃으므로 쓰지
// 않는다. 고름도 출납이다: 리비전 줄을 누르고 바로 「공식으로 지정…」 을 눌러도 그 리비전에 걸려야 한다. 글자를 치는 동안에는
// 아무것도 보내지 않고, 확정 뒤 묶어 보낸다. 칸을 쓰거나 줄을 끄는 동안(누르는 동안도) 돌아온 회차는 다시 그리지 않고 받은
// data 만 들고 있다가 끝나면 그린다 — 입력칸을 다시 지으면 한글 조합이 깨지고, 누른 사이 줄을 다시 지으면 click 이 사라진다.
// 업무 판정은 파이썬이 한다. 데이터 글은 textContent 로만 넣는다(고정 아이콘은 공용 조각이 그린다).

const SEND_MS = 300
const ROW_HEIGHT = 34
const DRAG_START_PX = 4
const EDGE_SCROLL_PX = 28
const EDGE_SCROLL_STEP = 14
const KEYS_HELP = '이름 칸: 연 줄이면 한 번 눌러 고칩니다(처음 누르면 엽니다) · Enter · F2 어느 줄이든 고치기 · Enter 확정 · Esc 취소 · Tab ↑ ↓ 옆·위아래 칸 · Space 열기 · 손잡이를 끌어 옮기기 · Alt+↑ ↓ 줄 옮기기 · 순서 칸에 자리 번호'
const COLUMNS = {
  scenarios: [
    { key: 'grip', head: '' },
    { key: 'place', head: '순서', editable: true },
    { key: 'name', head: '시나리오명', editable: true },
    { key: 'latest', head: '최신' },
    { key: 'official', head: '공식버전' },
    { key: 'updated', head: '최근 수정' },
  ],
  revisions: [
    { key: 'no', head: 'r' },
    { key: 'name', head: '리비전명', editable: true },
    { key: 'status', head: '상태' },
  ],
}
const TABLE_LABELS = { scenarios: '시나리오 목록', revisions: '리비전' }
const NAME_KIND = { scenarios: 'scenario', revisions: 'revision' }
// 말줄임으로 잘릴 수 있는 칸 — 값 전체를 칸 풍선에 둔다.
const TIP_COLUMNS = new Set(['name', 'official', 'status'])

// <list-move>
// 줄 옮기기 — 파이썬 `move_before` 와 같은 답을 낸다(시험이 대 본다). `before` 가 없거나 모르는 줄이면 끝이다.
function moveBefore(order, id, before) {
  if (!order.includes(id)) return order.slice()
  const rest = order.filter((item) => item !== id)
  if (before === null || before === undefined || !rest.includes(before)) return rest.concat([id])
  const at = rest.indexOf(before)
  return rest.slice(0, at).concat([id], rest.slice(at))
}

function applyMoves(order, moves) {
  return moves.reduce((ids, op) => moveBefore(ids, op.id, op.before), order)
}

// 자리 번호(1부터)로 끼워 넣을 때의 `before`. 끝 밖 번호는 끝에 붙는다.
function beforeForPlace(order, id, place) {
  const rest = order.filter((item) => item !== id)
  const at = Math.min(Math.max(Math.trunc(place) - 1, 0), rest.length)
  return at < rest.length ? rest[at] : null
}

// 위로 · 아래로(step ±1) · 맨 위로(step null)의 `before`. 끝에 닿아 움직일 수 없으면 undefined.
function beforeForStep(order, id, step) {
  const index = order.indexOf(id)
  if (index < 0) return undefined
  if (step === null) return index === 0 ? undefined : order[0]
  const target = index + step
  if (target < 0 || target >= order.length) return undefined
  return beforeForPlace(order, id, target + 1)
}

// 줄 높이가 고정이라 놓을 자리(줄 사이 0..n)는 산수 하나다.
function slotFromY(y, top, rowHeight, count) {
  return Math.max(0, Math.min(count, Math.round((Number(y) - Number(top)) / rowHeight)))
}

function beforeForSlot(order, id, slot) {
  let at = slot
  while (at < order.length && order[at] === id) at += 1
  return at < order.length ? order[at] : null
}

function parsePlace(text) {
  const value = String(text == null ? '' : text).trim()
  return /^\d+$/.test(value) ? Number(value) : null
}
// </list-move>

// <list-ime>
// 한글 조합 — 조합 중 keydown 은 칸 동작으로 쓰지 않는다(`isComposing` 또는 keyCode 229). 조합 중 Enter 는 기억했다가 조합이
// 끝난 뒤 한 번 확정한다(그 플랫폼이 둘째 keydown 을 보내도 편집이 이미 닫혀 두 번 되지 않는다).
function composingKey(event) {
  return Boolean(event.isComposing) || event.keyCode === 229
}

function remembersEnter(event) {
  return composingKey(event) && (event.code === 'Enter' || event.key === 'Enter')
}

// 칸 위 타자로 편집 열기 — 일반 글자는 그 글자로, 자모 · `Process` 키는 글자를 넣지 않고 값을 전체 선택한 채 연다(낱자로
// 깨지는 쪽이 더 나쁘다). 그 밖이면 null.
function typedStart(key, ctrl, meta, alt) {
  if (ctrl || meta || alt) return null
  if (key === 'Process') return { select: true }
  if (typeof key !== 'string' || key.length !== 1 || key === ' ') return null
  if (/[ᄀ-ᇿ㄰-㆏]/.test(key)) return { select: true }
  return { text: key }
}
// </list-ime>

// <list-gate>
// 다시 그려도 되는가 — 칸을 쓰는 중 · 줄을 끄는 중 · 누르는 중이면 안 된다.
function canRepaint(S) {
  return !S.edit && !S.drag && !S.pressing
}
// </list-gate>

function freshState() {
  return {
    mount: newMount(), box: createBox(), sentSeq: 0, timer: 0, base: null, limit: 2000, data: null, mode: null,
    edit: null, focus: null, drag: null, pressing: false, dirty: false, wantFocus: false, listeners: [], bound: false,
    built: null, rowNodes: new Map(), settleTimer: 0, enterAfter: false, suppressClick: false, note: '', view: null,
  }
}

// ---------------------------------------------------------------- 출납

function receive(S, data) {
  const base = String(data.base || '')
  S.base = base
  // 설비 마스터 `rebaseBox` 와 달리 비우지 않는다 — 옛 base op 는 서버가 세어 알리고 ack 로 지운다. 사라지는 고침을 한 길로
  // 알리기 위해서다. 낙관 표시는 `liveOps` 가 base 로 걷는다.
  S.box.base = base
  const ack = data.ack || {}
  if (ack.mount === S.mount && Number.isInteger(ack.seq)) ackBox(S.box, ack.seq)
  S.limit = Number((data.limits || {}).outboxCells) || S.limit
}

// 이미 보낸 op 만 남았으면 보내지 않는다 — 그렇지 않으면 이동 단추 열 번이 회차 열 번이 된다.
function flush(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = 0
  const last = S.box.ops[S.box.ops.length - 1]
  if (!last || last.seq <= S.sentSeq || !S.setState) return
  S.sentSeq = last.seq
  S.setState('outbox', { mount: S.mount, ops: S.box.ops.slice() })
}

function schedule(S) {
  if (S.timer) clearTimeout(S.timer)
  S.timer = setTimeout(() => flush(S), SEND_MS)
}

function queue(S, op, base) {
  const queued = queueOp(S.box, op, S.limit, Date.now())
  if (!queued) {
    showNote(S, '보낼 고침이 너무 많습니다 — 잠시 뒤 다시 합니다')
    return null
  }
  // 칸을 연 때의 세대로 보낸다 — 저장 직후 data 가 오기 전에 연 칸이 새 세대로 통과하면 자기 저장을 「다른 사용자가 먼저
  // 바꿨습니다」 로 막는다.
  if (base !== undefined) queued.base = base
  return queued
}

function showNote(S, text) {
  S.note = text
  if (S.noteNode) S.noteNode.textContent = text
}

function announce(S, text) {
  if (S.status) S.status.textContent = text
}

// 낙관 표시 재료 — 아직 반영되지 않은 op. 고침은 지금 세대의 것만 보인다.
function liveOps(S, kind) {
  return S.box.ops.filter((op) => op.op === kind && (kind === 'open' || kind === 'pick' || op.base === S.base))
}

function openedId(S) {
  const ops = liveOps(S, 'open')
  if (ops.length) return ops[ops.length - 1].id
  return S.data && S.data.open !== undefined ? S.data.open : null
}

function pickedId(S) {
  const ops = liveOps(S, 'pick')
  if (ops.length) return ops[ops.length - 1].id
  return S.data && S.data.picked !== undefined ? S.data.picked : null
}

// 받은 data 에 아직 반영되지 않은 op 를 얹은 화면 차례. 칸마다 다시 접으면 줄 수 × op 수로 느려져, data · 보낼 목록 · 세대가
// 그대로인 동안 한 벌을 쓴다(보낼 목록은 늘 때도 ack 로 줄 때도 수나 끝 seq 가 바뀐다).
function currentView(S) {
  const rows = (S.data && S.data.rows) || []
  const ops = S.box.ops
  const last = ops.length ? ops[ops.length - 1].seq : 0
  const held = S.view
  if (held && held.rows === rows && held.count === ops.length && held.last === last && held.base === S.base) return held
  const moves = S.mode === 'scenarios' ? liveOps(S, 'move') : []
  const known = new Map(rows.map((row) => [row.id, row]))
  const shown = moves.length ? applyMoves(rows.map((row) => row.id), moves).map((id) => known.get(id)).filter(Boolean) : rows
  const kind = NAME_KIND[S.mode]
  const names = new Map(liveOps(S, 'name').filter((op) => op.kind === kind).map((op) => [op.id, op.text]))
  const places = new Map(shown.map((row, index) => [row.id, index]))
  S.view = { rows, count: ops.length, last, base: S.base, shown, known, names, places }
  return S.view
}

function pendingName(S, id) {
  const text = currentView(S).names.get(id)
  return text === undefined ? null : text
}

function viewRows(S) {
  return currentView(S).shown
}

function rowOf(S, id) {
  return currentView(S).known.get(id) || null
}

function rowPlace(S, id) {
  return currentView(S).places.get(id)
}

// ---------------------------------------------------------------- 받기 · 그리기

function accept(S, data) {
  receive(S, data)
  S.data = data
  S.mode = String(data.mode || '')
  if (!canRepaint(S)) {
    S.dirty = true
    return
  }
  paint(S)
}

function settle(S) {
  if (S.dirty && canRepaint(S)) paint(S)
}

function paint(S) {
  S.dirty = false
  if (S.mode === 'changes') paintChanges(S)
  else paintTable(S)
}

function emptyHost(S) {
  S.host.textContent = ''
  S.rowNodes = new Map()
}

function buildTable(S) {
  emptyHost(S)
  S.built = S.mode
  const root = el('div', 'sgl-root sgl-' + S.mode)
  if (S.mode === 'revisions') {
    S.titleNode = el('h4', 'sgl-title')
    S.subNode = el('p', 'sgl-sub')
    root.appendChild(S.titleNode)
    root.appendChild(S.subNode)
  }
  if (S.mode === 'scenarios') {
    const tools = el('div', 'sgl-tools')
    S.tools = [
      toolButton(S, '↑ 위로', -1, '연 줄을 한 칸 위로 옮깁니다', '맨 위 줄입니다'),
      toolButton(S, '↓ 아래로', 1, '연 줄을 한 칸 아래로 옮깁니다', '맨 아래 줄입니다'),
      toolButton(S, '⤒ 맨 위로', null, '연 줄을 맨 위로 옮깁니다', '맨 위 줄입니다'),
    ]
    for (const tool of S.tools) tools.appendChild(tool.slot)
    root.appendChild(tools)
  }
  const box = el('div', 'sgl-box')
  const table = el('div', 'emg-table sgl-table')
  table.setAttribute('role', 'grid')
  table.setAttribute('aria-label', TABLE_LABELS[S.mode])
  table.setAttribute('aria-colcount', String(COLUMNS[S.mode].length))
  const head = el('div', 'emg-row emg-head sgl-row sgl-head')
  head.setAttribute('role', 'row')
  head.setAttribute('aria-rowindex', '1')
  COLUMNS[S.mode].forEach((column, index) => {
    const cell = el('div', 'emg-c sgl-w-' + column.key, column.head)
    cell.setAttribute('role', 'columnheader')
    cell.setAttribute('aria-colindex', String(index + 1))
    head.appendChild(cell)
  })
  const body = el('div', 'sgl-body')
  const drop = el('div', 'sgl-drop')
  drop.hidden = true
  table.appendChild(head)
  table.appendChild(body)
  table.appendChild(drop)
  box.appendChild(table)
  root.appendChild(box)
  S.scroller = box
  S.table = table
  S.body = body
  S.dropLine = drop
  if (S.mode === 'revisions') {
    S.valuesNode = el('dl', 'sgl-values')
    root.appendChild(S.valuesNode)
  }
  if (S.mode === 'scenarios') {
    const foot = el('div', 'emg-foot')
    // 키보드 조작은 표지 하나와 그 풍선이다 — 표 밑에 늘 세우지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-02).
    const keys = el('span', 'emg-muted emg-keys', '⌨ 키보드 조작')
    keys.title = KEYS_HELP
    const legend = el('span', 'emg-legend')
    for (const [kind, label] of [['is-changed', '고친 칸'], ['is-error', '막힘']]) {
      const item = el('span')
      item.appendChild(el('span', 'emg-swatch ' + kind))
      item.appendChild(el('span', null, label))
      legend.appendChild(item)
    }
    foot.appendChild(keys)
    S.noteNode = el('span', 'sgl-note', S.note)
    foot.appendChild(S.noteNode)
    foot.appendChild(legend)
    root.appendChild(foot)
  }
  S.status = el('div', 'sgl-status')
  S.status.setAttribute('role', 'status')
  root.appendChild(S.status)
  S.host.appendChild(root)
  listen(S, body, 'click', (event) => onBodyClick(S, event))
  listen(S, body, 'keydown', (event) => onBodyKey(S, event))
  listen(S, body, 'input', (event) => {
    if (S.edit && event.target === S.edit.node) S.edit.draft = event.target.value
  })
  listen(S, body, 'compositionend', () => {
    if (!S.enterAfter) return
    S.enterAfter = false
    commitEdit(S, null, true)
  })
  listen(S, body, 'focusin', (event) => {
    const cell = event.target.closest ? event.target.closest('[data-col]') : null
    if (cell) S.focus = { id: cell.dataset.id, col: cell.dataset.col }
  })
  listen(S, body, 'focusout', (event) => {
    // 칸 밖을 눌러 초점이 빠지면 확정한다. 누른 칸의 click 이 닿도록 그 칸만 바꾼다.
    if (S.edit && event.target === S.edit.node) commitEdit(S, null, false)
  })
  listen(S, body, 'pointerdown', (event) => onPointerDown(S, event))
  listen(S, body, 'pointermove', (event) => onPointerMove(S, event))
}

function toolButton(S, label, step, tip, endTip) {
  const slot = el('span', 'emg-tip-host sgl-tool-slot')
  const node = button('emg-btn is-small', label, () => {
    const id = openedId(S)
    if (id !== null) moveRow(S, id, step)
  })
  node.title = tip
  const reason = el('span', 'emg-tip')
  reason.id = 'sgl-tool-tip-' + String(step)
  reason.setAttribute('role', 'tooltip')
  slot.setAttribute('aria-describedby', reason.id)
  slot.appendChild(node)
  slot.appendChild(reason)
  return { slot, node, reason, label, step, tip, endTip }
}

function paintTools(S) {
  if (S.mode !== 'scenarios') return
  const opened = openedId(S)
  const order = viewRows(S).map((row) => row.id)
  const active = activeIn(S.host)
  for (const tool of S.tools) {
    const stuck = opened === null || beforeForStep(order, opened, tool.step) === undefined
    // 꺼진 단추는 마우스 · 초점을 받지 않아 감싼 칸이 탭 자리와 까닭 풍선을 맡는다. 초점을 쥔 단추를 끄기 **전에** 옮긴다 — 끈 뒤면
    // 초점이 문서로 빠지고, 부품 밖 이탈로 읽혀 묶음이 풀린다.
    tool.slot.tabIndex = stuck ? 0 : -1
    if (stuck && active === tool.node) tool.slot.focus({ preventScroll: true })
    tool.node.disabled = stuck
    if (!stuck && active === tool.slot) tool.node.focus({ preventScroll: true })
    tool.reason.textContent = stuck ? tool.endTip : ''
    if (stuck) tool.slot.setAttribute('aria-label', tool.label + ' — ' + tool.endTip)
    else tool.slot.removeAttribute('aria-label')
  }
}

function paintTable(S) {
  if (S.built !== S.mode) buildTable(S)
  const keyboard = S.wantFocus
  const hadFocus = keyboard || activeInside(S)
  const rows = viewRows(S)
  S.body.textContent = ''
  S.rowNodes = new Map()
  rows.forEach((row, index) => {
    const node = rowElement(S, row, index)
    S.rowNodes.set(row.id, node)
    S.body.appendChild(node)
  })
  S.table.setAttribute('aria-rowcount', String(rows.length + 1))
  if (S.mode === 'revisions') paintRevisionHead(S)
  paintTools(S)
  S.wantFocus = false
  // 키보드 손짓만 초점 칸으로 스크롤을 따라간다 — 회차가 돌아온 다시 그리기가 사용자가 내리던 스크롤을 끌고 가지 않는다.
  if (hadFocus) restoreCellFocus(S, keyboard ? undefined : { preventScroll: true })
}

function activeInside(S) {
  const active = activeIn(S.host)
  return Boolean(active && S.body && S.body.contains(active))
}

function paintRevisionHead(S) {
  S.titleNode.textContent = String(S.data.title || '')
  S.subNode.textContent = String(S.data.sub || '')
  const picked = rowOf(S, pickedId(S))
  S.valuesNode.textContent = ''
  for (const [label, value] of [['메모', picked && picked.memo], ['저장일', picked && picked.created], ['부모', picked && picked.parent]]) {
    S.valuesNode.appendChild(el('dt', null, label))
    const item = el('dd', null, value || (picked ? '없음' : ''))
    // 메모는 월 머지 · 연도 Shift 출처처럼 길 수 있다 — 작업 줄을 밀어내지 않게 세 줄까지 보이고 전부는 풍선이다.
    if (label === '메모' && value) {
      item.classList.add('sgl-memo')
      item.title = value
    }
    S.valuesNode.appendChild(item)
  }
}

function isSelected(S, id) {
  return (S.mode === 'scenarios' ? openedId(S) : pickedId(S)) === id
}

function rowElement(S, row, index) {
  const node = el('div', 'emg-row sgl-row')
  node.setAttribute('role', 'row')
  node.setAttribute('aria-rowindex', String(index + 2))
  node.dataset.row = row.id
  if (isSelected(S, row.id)) {
    node.classList.add('is-open')
    node.setAttribute('aria-selected', 'true')
  }
  COLUMNS[S.mode].forEach((column, k) => node.appendChild(cellElement(S, row, column, k, index)))
  if (S.edit && S.edit.id === row.id) node.classList.add('is-editing-row')
  return node
}

function cellValue(S, row, column, index) {
  if (column.key === 'place') return String(index + 1)
  if (column.key === 'name') {
    const pending = pendingName(S, row.id)
    return pending !== null ? pending : String(row.name || '')
  }
  return String(row[column.key] || '')
}

function cellElement(S, row, column, k, index) {
  const cell = el('div', 'emg-c sgl-w-' + column.key)
  cell.setAttribute('role', 'gridcell')
  cell.setAttribute('aria-colindex', String(k + 1))
  cell.dataset.id = row.id
  cell.dataset.col = column.key
  const pending = pendingName(S, row.id)
  const name = pending !== null ? pending : String(row.name || '')
  if (column.key === 'grip') {
    const grip = el('span', 'sgl-grip', '⋮⋮')
    grip.title = '끌어 옮기기 · Alt+↑ ↓'
    grip.setAttribute('aria-label', name + ' 줄 옮기기')
    grip.setAttribute('aria-keyshortcuts', 'Alt+ArrowUp Alt+ArrowDown')
    cell.appendChild(grip)
    return cell
  }
  const editing = S.edit && S.edit.id === row.id && S.edit.col === column.key
  const value = cellValue(S, row, column, index)
  const tips = []
  let label = name + ' ' + column.head
  if (column.key === 'name') {
    if (row.saved !== undefined) {
      cell.classList.add('is-changed')
      tips.push('저장본: ' + row.saved)
      label += ', 고침 — 저장본 ' + row.saved
    }
    if (row.problem) {
      cell.classList.add('is-error')
      tips.push('막힘: ' + row.problem)
      label += ', 막힘 — ' + row.problem
    }
    if (pending !== null) cell.classList.add('is-pending')
  }
  if (column.key === 'place' && row.place !== undefined) {
    cell.classList.add('is-changed')
    tips.push('저장 차례 ' + row.place + '번째')
  }
  if (TIP_COLUMNS.has(column.key) && value) tips.unshift(value)
  if (!column.editable) cell.classList.add('sgl-ro')
  if (tips.length) cell.title = tips.join('\n')
  if (editing) {
    cell.classList.add('is-editing')
    const input = textEditor('emg-ed', S.edit.draft)
    input.setAttribute('aria-label', label)
    if (row.problem && column.key === 'name') input.setAttribute('aria-invalid', 'true')
    S.edit.node = input
    cell.appendChild(input)
    return cell
  }
  const shown = (column.key === 'name' && row.problem ? '! ' : '') + (value || (column.key === 'name' ? '(빈 이름)' : ''))
  const press = button('emg-cb', shown)
  press.tabIndex = tabStop(S, row, column) ? 0 : -1
  press.setAttribute('aria-label', label + (column.editable ? '' : ' ' + value))
  if (row.problem && column.key === 'name') press.setAttribute('aria-invalid', 'true')
  cell.appendChild(press)
  return cell
}

// 표 본문의 Tab 정지는 초점 칸 하나다(로빙). 아직 초점이 없으면 연 줄(없으면 맨 위 줄)의 이름 칸이다.
function tabStop(S, row, column) {
  if (S.focus && S.rowNodes && rowOf(S, S.focus.id)) return S.focus.id === row.id && S.focus.col === column.key
  if (column.key !== 'name') return false
  const selected = S.mode === 'scenarios' ? openedId(S) : pickedId(S)
  const first = viewRows(S)[0]
  return selected ? selected === row.id : Boolean(first && first.id === row.id)
}

function restoreCellFocus(S, options) {
  if (!S.focus) return
  const node = cellNode(S, S.focus.id, S.focus.col)
  const press = node ? node.querySelector('.emg-cb') : null
  if (press) press.focus(options)
}

function cellNode(S, id, col) {
  const row = S.rowNodes.get(id)
  if (!row) return null
  return Array.from(row.children).find((cell) => cell.dataset.col === col) || null
}

function repaintCell(S, id, col) {
  const row = rowOf(S, id)
  const node = S.rowNodes.get(id)
  const old = cellNode(S, id, col)
  if (!row || !node || !old) return
  const k = COLUMNS[S.mode].findIndex((column) => column.key === col)
  node.replaceChild(cellElement(S, row, COLUMNS[S.mode][k], k, rowPlace(S, id)), old)
  node.classList.toggle('is-editing-row', Boolean(S.edit && S.edit.id === id))
}

// ---------------------------------------------------------------- 칸 고치기

function startEdit(S, id, col, initial) {
  const row = rowOf(S, id)
  const column = COLUMNS[S.mode].find((item) => item.key === col)
  if (!row || !column || !column.editable) return
  const current = cellValue(S, row, column, rowPlace(S, id))
  const typed = initial !== undefined
  S.edit = {
    id,
    col,
    draft: typed ? initial : current,
    original: current,
    // 사용자가 **본** 이름 — 저장본 값(고친 칸이면 처음 저장본)이다. 서버가 처음 고칠 때 값을 지킨다.
    seen: row.saved !== undefined ? String(row.saved) : String(row.name || ''),
    // 칸을 연 때의 세대.
    base: S.base,
    node: null,
  }
  S.focus = { id, col }
  repaintCell(S, id, col)
  const input = S.edit.node
  if (input) {
    input.focus()
    if (!typed && input.select) input.select()
  }
}

// `refocus` 가 거짓이면 다른 칸을 눌러 초점이 빠진 것이다 — 줄을 다시 짓지 않고 그 칸만 바꾼다(누른 칸의 click 이 닿는다).
function commitEdit(S, move, refocus) {
  const edit = S.edit
  if (!edit) return
  if (edit.node) edit.draft = edit.node.value
  S.edit = null
  S.enterAfter = false
  let reordered = false
  if (edit.col === 'place') {
    const order = viewRows(S).map((row) => row.id)
    const place = parsePlace(edit.draft)
    if (place !== null && place !== order.indexOf(edit.id) + 1) {
      queueMove(S, edit.id, beforeForPlace(order, edit.id, place))
      reordered = true
    }
  } else if (edit.draft !== edit.original) {
    queue(S, { op: 'name', kind: NAME_KIND[S.mode], id: edit.id, text: edit.draft, seen: edit.seen }, edit.base)
    schedule(S)
  }
  const target = move ? nextEditable(S, edit, move) : null
  if (reordered) {
    S.dirty = true
    announceMoved(S, edit.id)
  }
  if (target) {
    if (!reordered) repaintCell(S, edit.id, edit.col)
    else paint(S)
    startEdit(S, target.id, target.col)
    return
  }
  if (S.dirty && canRepaint(S)) {
    S.wantFocus = refocus !== false
    paint(S)
    return
  }
  repaintCell(S, edit.id, edit.col)
  if (refocus !== false) restoreCellFocus(S)
}

function cancelEdit(S) {
  const edit = S.edit
  if (!edit) return
  S.edit = null
  S.enterAfter = false
  if (S.dirty && canRepaint(S)) {
    S.wantFocus = true
    paint(S)
    return
  }
  repaintCell(S, edit.id, edit.col)
  restoreCellFocus(S)
}

function nextEditable(S, edit, dir) {
  const rows = viewRows(S)
  const columns = COLUMNS[S.mode]
  const from = { row: rows.findIndex((row) => row.id === edit.id), col: columns.findIndex((column) => column.key === edit.col) }
  if (from.row < 0 || from.col < 0) return null
  const next = nextCell(rows.length, columns.length, from, dir, (r, c) => Boolean(columns[c].editable), columns.length + rows.length)
  return next ? { id: rows[next.row].id, col: columns[next.col].key } : null
}

// ---------------------------------------------------------------- 고르기 · 옮기기

// 잃으면 안 되는 조작이라 묶지 않고 바로 보낸다. `sendOnce` 를 쓰지 않는다 — A → B → A 의 셋째가 버려지면 마지막이 이기지 못한다.
function activate(S, id) {
  // 누르는 동안 온 data 가 표를 바꿨으면 옛 줄이다(다른 시나리오의 리비전일 수 있다) — 손을 떼면 지금 data 로 다시 그린다.
  if (!rowOf(S, id)) return
  const op = S.mode === 'scenarios' ? { op: 'open', id } : { op: 'pick', owner: S.data.owner, id }
  queue(S, op)
  flush(S)
  paintSelection(S)
  if (S.mode === 'revisions') paintRevisionHead(S)
}

// 다시 그리기 전 고른 표시만 바꾼다 — 줄 노드를 다시 짓지 않아 이어 누른 click 이 닿는다.
function paintSelection(S) {
  for (const [id, node] of S.rowNodes) {
    const on = isSelected(S, id)
    node.classList.toggle('is-open', on)
    if (on) node.setAttribute('aria-selected', 'true')
    else node.removeAttribute('aria-selected')
  }
  paintTools(S)
}

function queueMove(S, id, before) {
  const queued = queue(S, { op: 'move', id, before, token: String(S.data.orderToken || '') })
  if (queued) schedule(S)
  return queued
}

function moveRow(S, id, step) {
  const order = viewRows(S).map((row) => row.id)
  const before = beforeForStep(order, id, step)
  if (before === undefined) return
  queueMove(S, id, before)
  announceMoved(S, id)
  if (canRepaint(S)) paint(S)
  else S.dirty = true
}

function announceMoved(S, id) {
  const row = rowOf(S, id)
  if (row) announce(S, String(row.name || '') + ' ' + (rowPlace(S, id) + 1) + '번째로 옮김')
}

function onBodyClick(S, event) {
  if (S.suppressClick) {
    S.suppressClick = false
    return
  }
  const cell = event.target.closest ? event.target.closest('[data-col]') : null
  if (!cell) return
  const id = cell.dataset.id
  const col = cell.dataset.col
  if (col === 'grip') return
  if (S.edit && S.edit.id === id && S.edit.col === col) return
  S.focus = { id, col }
  if (col === 'place') {
    startEdit(S, id, col)
    return
  }
  // 이름 칸 — 연 줄이면 한 번 눌러 고치고, 아니면 먼저 연다. 두 번 누르면 열고 고친다.
  if (col === 'name' && isSelected(S, id)) {
    startEdit(S, id, col)
    return
  }
  activate(S, id)
}

function onEditorKey(S, event) {
  if (composingKey(event)) {
    if (remembersEnter(event)) S.enterAfter = true
    return
  }
  const key = event.key
  if (key === 'Enter') {
    event.preventDefault()
    commitEdit(S, null, true)
  } else if (key === 'Escape') {
    event.preventDefault()
    cancelEdit(S)
  } else if (key === 'Tab') {
    event.preventDefault()
    commitEdit(S, event.shiftKey ? 'left' : 'right', true)
  } else if (key === 'ArrowDown' || key === 'ArrowUp') {
    event.preventDefault()
    commitEdit(S, key === 'ArrowDown' ? 'down' : 'up', true)
  }
}

function onBodyKey(S, event) {
  const target = event.target
  // 칸의 키는 문서로 올려 보내지 않는다 — Streamlit 문서 단축키(r 다시 실행 · c 캐시)가 글자를 먹는다.
  stopKeys(event)
  if (S.edit && target === S.edit.node) {
    onEditorKey(S, event)
    return
  }
  const cell = target.closest ? target.closest('[data-col]') : null
  if (!cell) return
  const id = cell.dataset.id
  const col = cell.dataset.col
  const key = event.key
  if (event.altKey && S.mode === 'scenarios' && (key === 'ArrowUp' || key === 'ArrowDown')) {
    event.preventDefault()
    S.focus = { id, col }
    S.wantFocus = true
    moveRow(S, id, key === 'ArrowUp' ? -1 : 1)
    return
  }
  const moves = { ArrowRight: 'right', ArrowLeft: 'left', ArrowDown: 'down', ArrowUp: 'up' }
  if (moves[key]) {
    event.preventDefault()
    const columns = COLUMNS[S.mode].map((column) => column.key).filter((name) => name !== 'grip')
    const next = moveFocus(viewRows(S).map((row) => row.id), columns, { id, col }, moves[key])
    if (next) focusCell(S, next.id, next.col)
    return
  }
  if (key === ' ') {
    event.preventDefault()
    activate(S, id)
    return
  }
  const column = COLUMNS[S.mode].find((item) => item.key === col)
  const editable = Boolean(column && column.editable)
  if (key === 'Enter' || key === 'F2') {
    event.preventDefault()
    if (editable) startEdit(S, id, col)
    else activate(S, id)
    return
  }
  if (!editable) return
  const typed = typedStart(key, event.ctrlKey, event.metaKey, event.altKey)
  if (!typed) return
  event.preventDefault()
  if (typed.select) startEdit(S, id, col)
  else startEdit(S, id, col, typed.text)
}

function focusCell(S, id, col) {
  const previous = S.focus ? cellNode(S, S.focus.id, S.focus.col) : null
  const stale = previous ? previous.querySelector('.emg-cb') : null
  if (stale) stale.tabIndex = -1
  S.focus = { id, col }
  const node = cellNode(S, id, col)
  const press = node ? node.querySelector('.emg-cb') : null
  if (press) {
    press.tabIndex = 0
    press.focus()
  }
}

// ---------------------------------------------------------------- 누름 · 끌기

function onPointerDown(S, event) {
  if (S.mode !== 'scenarios' || event.button !== 0) return
  const grip = event.target.closest ? event.target.closest('.sgl-grip') : null
  if (!grip) return
  event.preventDefault()
  commitEdit(S, null, false)
  const cell = grip.closest('[data-col]')
  if (!cell) return
  S.drag = { id: cell.dataset.id, startY: event.clientY, y: event.clientY, active: false, slot: 0 }
  if (S.body.setPointerCapture) S.body.setPointerCapture(event.pointerId)
}

function onPointerMove(S, event) {
  const drag = S.drag
  if (!drag) return
  drag.y = event.clientY
  if (!drag.active) {
    if (Math.abs(drag.y - drag.startY) <= DRAG_START_PX) return
    drag.active = true
    S.host.classList.add('is-dragging')
    const node = S.rowNodes.get(drag.id)
    if (node) node.classList.add('is-dragged')
    S.dropLine.hidden = false
  }
  const scroller = S.scroller.getBoundingClientRect()
  if (drag.y < scroller.top + EDGE_SCROLL_PX) S.scroller.scrollTop -= EDGE_SCROLL_STEP
  else if (drag.y > scroller.bottom - EDGE_SCROLL_PX) S.scroller.scrollTop += EDGE_SCROLL_STEP
  const rect = S.body.getBoundingClientRect()
  drag.slot = slotFromY(drag.y, rect.top, ROW_HEIGHT, viewRows(S).length)
  S.dropLine.style.top = S.body.offsetTop + drag.slot * ROW_HEIGHT - 1 + 'px'
}

function endDrag(S, cancelled) {
  const drag = S.drag
  if (!drag) return
  S.drag = null
  S.host.classList.remove('is-dragging')
  S.dropLine.hidden = true
  const node = S.rowNodes.get(drag.id)
  if (node) node.classList.remove('is-dragged')
  if (!drag.active) return
  S.suppressClick = true
  setTimeout(() => {
    S.suppressClick = false
  }, 0)
  if (cancelled) return
  const order = viewRows(S).map((row) => row.id)
  const before = beforeForSlot(order, drag.id, drag.slot)
  if (moveBefore(order, drag.id, before).join('\n') === order.join('\n')) return
  queueMove(S, drag.id, before)
  announceMoved(S, drag.id)
  S.dirty = true
}

function onPointerEnd(S, cancelled) {
  if (!S.pressing && !S.drag) return
  S.pressing = false
  endDrag(S, cancelled)
  // click 이 먼저 닿게 다음 틱에 그린다.
  if (S.settleTimer) clearTimeout(S.settleTimer)
  S.settleTimer = setTimeout(() => {
    S.settleTimer = 0
    settle(S)
  }, 0)
}

// ---------------------------------------------------------------- 저장 전 변경

const SUM_CELLS = [['scenario', '시나리오명'], ['order', '순서'], ['revision', '리비전명'], ['blocked', '막힘']]

// 더블클릭의 둘째 누름은 첫 op 의 회차가 돌아오기 전에 닿는다 — 같은 op 가 남아 있으면 보내지 않는다.
function sendRevert(S, op) {
  if (hasPendingOp(S.box, op)) return
  queue(S, op)
  flush(S)
}

// 칸 전체를 다시 지어도 키보드 초점이 문서로 빠지지 않게 든 자리를 잡아 둔다 — 되돌린 줄은 사라지므로 차례도 함께 든다.
function heldChange(S) {
  const active = activeIn(S.host)
  if (!active || !S.host.contains(active) || !active.dataset || !active.dataset.fk) return null
  return { key: active.dataset.fk, at: Array.from(S.host.querySelectorAll('[data-fk]')).indexOf(active) }
}

function restoreChange(root, held) {
  if (!held) return
  const marks = Array.from(root.querySelectorAll('[data-fk]'))
  const node = marks.find((mark) => mark.dataset.fk === held.key) || marks[Math.min(held.at, marks.length - 1)] || root
  node.focus({ preventScroll: true })
}

function paintChanges(S) {
  const held = heldChange(S)
  const root = changesRoot(S)
  emptyHost(S)
  S.built = S.mode
  S.host.appendChild(root)
  restoreChange(root, held)
}

function changesRoot(S) {
  const data = S.data
  const root = el('div', 'sgl-root sgl-changes')
  root.tabIndex = -1
  const counts = data.counts || {}
  const sum = el('div', 'emg-sum')
  for (const [key, label] of SUM_CELLS) {
    const cell = el('div', key === 'blocked' ? 'is-error' : null)
    cell.appendChild(el('b', null, Number(counts[key] || 0).toLocaleString()))
    cell.appendChild(el('span', 'emg-muted', label))
    sum.appendChild(cell)
  }
  root.appendChild(sum)
  const groups = Array.isArray(data.groups) ? data.groups : []
  const order = data.order || {}
  if (!groups.length && !order.moved && !order.problem) {
    root.appendChild(el('p', 'emg-side-empty', '아직 고친 것이 없습니다.'))
    return root
  }
  for (const group of groups) {
    const box = el('div', 'emg-unit')
    const head = el('div', 'emg-unit-head')
    const open = button('emg-link', group.name || '(빈 이름)', () => {
      queue(S, { op: 'open', id: group.id, detail: true })
      flush(S)
    })
    open.dataset.fk = 'open-' + group.id
    head.appendChild(open)
    box.appendChild(head)
    for (const line of group.lines || []) box.appendChild(changeLine(S, line))
    root.appendChild(box)
  }
  if (order.moved || order.problem) {
    const box = el('div', 'emg-unit')
    const head = el('div', 'emg-unit-head')
    head.appendChild(el('b', null, '목록 차례'))
    box.appendChild(head)
    const line = el('div', 'emg-line')
    line.appendChild(el('span', 'emg-muted', '순서'))
    line.appendChild(el('span', 'emg-value', Number(order.moved || 0).toLocaleString() + '줄 자리 바뀜'))
    const undo = icon('undo', '순서 되돌리기', () => sendRevert(S, { op: 'revert', kind: 'order' }))
    undo.dataset.fk = 'undo-order'
    line.appendChild(undo)
    if (order.problem) line.appendChild(el('span', 'sgl-problem', '! ' + order.problem))
    box.appendChild(line)
    root.appendChild(box)
  }
  return root
}

function changeLine(S, item) {
  const line = el('div', 'emg-line')
  const label = el('span', 'emg-muted', item.label)
  if (item.mark) {
    const mark = el('span', 'sgl-mark', item.mark)
    if (item.note) mark.title = item.note
    label.appendChild(mark)
  }
  line.appendChild(label)
  const value = el('span', 'emg-value')
  value.appendChild(el('span', 'emg-from', item.before || '(빈 이름)'))
  value.appendChild(el('span', null, ' → '))
  value.appendChild(el('b', null, item.after || '(빈 이름)'))
  line.appendChild(value)
  const undo = icon('undo', item.label + ' 되돌리기', () => sendRevert(S, { op: 'revert', kind: item.kind, id: item.id }))
  undo.dataset.fk = 'undo-' + item.kind + '-' + item.id
  line.appendChild(undo)
  if (item.problem) line.appendChild(el('span', 'sgl-problem', '! ' + item.problem))
  return line
}

// ---------------------------------------------------------------- 마운트

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const host = parentElement.querySelector('.sgl')
  if (!host || !data) return
  const S = host.__sgl || (host.__sgl = freshState())
  S.host = host
  S.setState = setStateValue
  const palette = data.palette || {}
  const paletteKey = JSON.stringify(palette)
  if (S.paletteKey !== paletteKey) {
    S.paletteKey = paletteKey
    for (const [name, value] of Object.entries(palette)) host.style.setProperty('--emg-' + name, String(value))
  }
  host.dataset.mode = String(data.mode || '')
  if (!S.bound) {
    S.bound = true
    // 부품 밖으로 초점이 나가거나(「변경 저장」 누름 포함) 창이 숨으면 기다리지 않고 보낸다.
    listen(S, host, 'focusout', (event) => {
      if (!event.relatedTarget || !host.contains(event.relatedTarget)) flush(S)
    })
    // 줄이든 되돌리기 아이콘이든 누르면 그 뒤 온 회차는 손을 뗄 때까지 미룬다(세 마운트 모두).
    listen(S, host, 'pointerdown', () => {
      S.pressing = true
    })
    listen(S, document, 'visibilitychange', () => flush(S))
    listen(S, document, 'pointerup', () => onPointerEnd(S, false))
    listen(S, document, 'pointercancel', () => onPointerEnd(S, true))
    // 끄는 중 Esc 는 취소다 — 칸의 키가 문서로 올라오지 않으므로(`stopKeys`) 잡는 단계에서 받는다.
    listen(S, document, 'keydown', (event) => {
      if (S.drag && event.key === 'Escape') {
        event.stopPropagation()
        onPointerEnd(S, true)
      }
    }, true)
  }
  accept(S, data)
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    commitEdit(S, null, false)
    flush(S)
    for (const [target, type, handler, options] of S.listeners) target.removeEventListener(type, handler, options)
    S.listeners = []
    if (S.timer) clearTimeout(S.timer)
    if (S.settleTimer) clearTimeout(S.settleTimer)
    S.timer = 0
    S.settleTimer = 0
    S.bound = false
    S.built = null
  }
}
