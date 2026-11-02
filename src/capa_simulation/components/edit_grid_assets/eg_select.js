// 범용 편집 그리드 — 고르기(SELECT): 끌어 고르기(pointer capture + rAF 자동 스크롤)·Shift+클릭·Shift 확장(화살표·Ctrl+화살표·
// PageUp/Down·Alt+PageUp/Down·Home/End·Ctrl+Home/End)·Ctrl+A/Shift+Space/Ctrl+Space·Ctrl+C(동기 copy 이벤트 — 엑셀 따옴표 TSV)·
// Delete(고른 범위 비우기 — 분류 칸은 건너뜀)·기준 칸 붙여넣기(여러 칸 덩어리)·Ctrl+X 안내·복사 점선·범위 표지·머리 칸 표지.
// 순수 구획 `// <eg-rect>`·`// <eg-clip>` 은 node 시험이 떼어 돌린다. 갈고리는 `feature({ name: 'select', ... })` 하나로 단다
// (eg_pure.js 의 FEATURES — 차례 select → fill → toolbar).
//
// 다른 기능 파일이 쓰는 것(이름을 바꾸지 않는다 — test_edit_grid_select_js 가 본다):
// - `selDrag(S, event, { move(S, cell), end(S, cell, cancelled) })` — pointer capture + rAF 자동 스크롤 끌기. move 는 손 밑 칸이
//   바뀔 때마다(보기 좌표, 표 밖이면 끝 칸), end 는 놓거나(cancelled false) 끌기가 끊길 때(true). 채우기 손잡이가 쓴다.
// - 갈고리 `paste(S, matrix, event)` — 붙여넣은 글을 칸 판(parseClipboard)으로 받아 먼저 가져간다. true 를 돌려주면 이 파일의
//   기준 칸 붙여넣기를 건너뛴다(FILL 의 planPaste — 값 하나 → 고른 범위·정수 배 되풀이).
// - 순수: `rectNorm`·`rectSize`·`rectHas`·`rectEdges`·`rectSpan`·`dragScrollStep`·`quoteCell`·`toTsv`·`parseClipboard`·`pasteAtAnchor`.
// - `selCopied(S)` — 지금 복사 점선 범위(없거나 낡았으면 null), `selDropCopy(S)` — 점선 지우기.

// <eg-rect>
// 고른 범위는 보기 좌표다(c 는 열쇠 칸을 포함한 전체 칸 번호). anchor 가 지금 칸, focus 가 맞은편 모서리다.
function rectNorm(a, b) {
  return { r0: Math.min(a.r, b.r), r1: Math.max(a.r, b.r), c0: Math.min(a.c, b.c), c1: Math.max(a.c, b.c) }
}

function rectSize(rect) {
  const h = rect.r1 - rect.r0 + 1
  const w = rect.c1 - rect.c0 + 1
  return { h, w, cells: h * w }
}

function rectHas(rect, r, c) {
  return r >= rect.r0 && r <= rect.r1 && c >= rect.c0 && c <= rect.c1
}

// 칸이 범위 둘레의 어느 변에 닿는가 — 1 위 · 2 아래 · 4 왼쪽 · 8 오른쪽(범위 밖이면 0).
function rectEdges(rect, r, c) {
  if (!rectHas(rect, r, c)) return 0
  return (r === rect.r0 ? 1 : 0) | (r === rect.r1 ? 2 : 0) | (c === rect.c0 ? 4 : 0) | (c === rect.c1 ? 8 : 0)
}

// 큰 고름 — 'all'(Ctrl+A) 표 전체, 'row'(Shift+Space) 고른 줄들의 모든 칸, 'col'(Ctrl+Space) 고른 칸들의 모든 줄. 지금 칸(anchor)은
// 그 줄·칸을 지키고 맞은편 모서리만 끝으로 민다(표 전체는 왼쪽 위가 지금 칸). 표가 비면 null.
function rectSpan(kind, anchor, focus, rows, cols) {
  if (rows <= 0 || cols <= 0) return null
  if (kind === 'all') return { anchor: { r: 0, c: 0 }, focus: { r: rows - 1, c: cols - 1 } }
  if (kind === 'row') return { anchor: { r: anchor.r, c: 0 }, focus: { r: focus.r, c: cols - 1 } }
  if (kind === 'col') return { anchor: { r: 0, c: anchor.c }, focus: { r: rows - 1, c: focus.c } }
  return null
}

// 끌기 자동 스크롤 한 프레임 — 손(x, y)이 표 창 밖이면 멀수록 빨리 min(4 + 거리 × 0.5, 80)px. view = {left, top, width, height,
// headH, frozenWidth, scrollLeft}(창 = 스크롤 칸 안쪽, 머리 줄 아래부터 본문). 위는 머리 줄에 닿으면 굴린다. 왼쪽은 표 왼쪽 끝 밖,
// 또는 끌기가 고정 칸 밖에서 시작했고(leftOverFrozen) 아직 왼쪽으로 굴릴 것이 있을 때 고정 칸 위(엑셀 틀 고정과 같다).
function dragScrollStep(x, y, view, leftOverFrozen) {
  const speed = (distance) => Math.min(4 + distance * 0.5, 80)
  let dx = 0
  let dy = 0
  const bodyTop = view.top + view.headH
  const bottom = view.top + view.height
  if (y < bodyTop) dy = -speed(bodyTop - y)
  else if (y > bottom) dy = speed(y - bottom)
  const right = view.left + view.width
  const leftEdge = view.left + (leftOverFrozen && view.scrollLeft > 0 ? view.frozenWidth : 0)
  if (x > right) dx = speed(x - right)
  else if (x < leftEdge) dx = -speed(leftEdge - x)
  return { dx: Math.round(dx), dy: Math.round(dy) }
}
// </eg-rect>

// <eg-clip>
// 엑셀 호환 TSV — 칸에 탭·줄바꿈·따옴표가 있으면 따옴표로 감싸고 안의 따옴표를 겹친다(`""`). 줄 사이는 CRLF 다. 마지막 줄이 빈
// 글(빈칸 하나)이면 끝에 CRLF 를 하나 더 붙인다 — 붙여넣기가 끝 줄바꿈 하나를 떼므로 그 빈 줄이 살아 돌아온다(엑셀은 늘 붙인다).
function quoteCell(value) {
  const text = value === null || value === undefined ? '' : String(value)
  return /[\t\r\n"]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text
}

function toTsv(matrix) {
  const lines = matrix.map((line) => line.map(quoteCell).join('\t'))
  const text = lines.join('\r\n')
  return lines.length && lines[lines.length - 1] === '' ? text + '\r\n' : text
}

// 붙인 글 → 칸 판(글의 2차원 배열, 늘 한 줄 한 칸 이상 — 줄마다 칸 수가 다를 수 있다). CRLF·CR 은 LF 로 보고 끝 줄바꿈 하나는
// 뗀다. `"` 로 시작해 `"` + 탭·줄바꿈·끝으로 닫히는 칸은 엑셀 따옴표 칸이다(안의 탭·줄바꿈 그대로, `""` → `"`). 닫히지 않거나 닫는
// 따옴표 뒤에 글이 더 있으면 따옴표 칸이 아니다 — 다음 탭·줄바꿈까지 글자 그대로(설비 마스터 표 `<grid-paste>` 와 같은 규칙).
function parseClipboard(text) {
  const body = String(text === null || text === undefined ? '' : text).replace(/\r\n?/g, '\n').replace(/\n$/, '')
  const rows = [[]]
  let at = 0
  for (;;) {
    const quoted = body[at] === '"' ? clipQuoted(body, at) : null
    let end = at
    if (quoted) end = quoted.end
    else while (end < body.length && body[end] !== '\t' && body[end] !== '\n') end += 1
    rows[rows.length - 1].push(quoted ? quoted.value : body.slice(at, end))
    if (end >= body.length) return rows
    if (body[end] === '\n') rows.push([])
    at = end + 1
  }
}

// `start` 의 `"` 로 연 칸 — 값과 닫는 따옴표 다음 자리. 따옴표 칸이 아니면 null.
function clipQuoted(body, start) {
  let value = ''
  for (let at = start + 1; at < body.length; at += 1) {
    if (body[at] !== '"') value += body[at]
    else if (body[at + 1] === '"') {
      value += '"'
      at += 1
    } else {
      const next = at + 1
      return next === body.length || body[next] === '\t' || body[next] === '\n' ? { value, end: next } : null
    }
  }
  return null
}

// 기준 칸(보기 좌표 r0, c0)부터 덩어리를 그대로 편다. 표 끝(rows 줄 · cols 칸)을 넘은 칸은 버리고(clipped), 분류 칸(c < keyCount)에
// 걸린 칸은 건너뛴다(skipped). 돌려주는 값 칸 범위 {r0, r1, c0, c1}(c0 은 첫 값 칸 — 값 칸이 없으면 c0 > c1)와 values(그 범위의
// 줄 × 칸 글 | null — null 은 덩어리가 모자라 그 칸을 그대로 둔다), 쓸 칸 수 cells, 붙인 자리 전체 span(분류 칸 포함 — 붙인 뒤
// 고를 범위).
function pasteAtAnchor(r0, c0, matrix, rows, cols, keyCount) {
  const width = matrix.reduce((most, line) => Math.max(most, line.length), 0)
  const r1 = Math.min(r0 + matrix.length, rows) - 1
  const cEnd = Math.min(c0 + width, cols) - 1
  const v0 = Math.max(c0, keyCount)
  let clipped = 0
  let skipped = 0
  let cells = 0
  const values = []
  matrix.forEach((line, i) => {
    const r = r0 + i
    line.forEach((value, j) => {
      const c = c0 + j
      if (r >= rows || c >= cols) clipped += 1
      else if (c < keyCount) skipped += 1
      else cells += 1
    })
    if (r > r1 || v0 > cEnd) return
    const out = []
    for (let c = v0; c <= cEnd; c += 1) {
      const value = line[c - c0]
      out.push(value === undefined ? null : value)
    }
    values.push(out)
  })
  return { r0, r1, c0: v0, c1: cEnd, values, cells, clipped, skipped, span: { r0, r1, c0, c1: cEnd } }
}
// </eg-clip>

// ---------------------------------------------------------------- 상태·글

const SEL_MOVE_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown', 'Home', 'End'])
// 칸 표지 — 표지 비트 차례로 클래스 하나씩(그린 칸에 비트 묶음을 기억해 바뀐 것만 고친다).
const SEL_CLASSES = ['sel-t', 'sel-b', 'sel-l', 'sel-r', 'in-rng', 'is-sel', 'is-cp', 'cp-t', 'cp-b', 'cp-l', 'cp-r']
const SEL_FALLBACK_PASTE_LIMIT = 15000

function selText(S, name, fallback, n) {
  const value = S.texts && typeof S.texts[name] === 'string' ? S.texts[name] : fallback
  return n === undefined ? value : value.replace('{n}', Number(n).toLocaleString('ko-KR'))
}

function selListen(S, target, type, handler) {
  target.addEventListener(type, handler)
  S.sel.listeners.push([target, type, handler])
}

function selClearPageSelection() {
  const selection = document.getSelection ? document.getSelection() : null
  if (selection && selection.rangeCount) selection.removeAllRanges()
}

// 지금 복사 점선 범위 — 칸 편집을 시작했거나 보기(정렬·필터·표)가 바뀌었으면 지우고 null.
function selCopied(S) {
  const copied = S.sel && S.sel.copied
  if (!copied) return null
  if (S.edit || !S.model || copied.order !== S.view.order || copied.table !== S.model.table) {
    S.sel.copied = null
    return null
  }
  return copied
}

function selDropCopy(S) {
  if (!S.sel || !S.sel.copied) return
  S.sel.copied = null
  selMarkAll(S)
}

// 칸 표지 셈 — 지금 칸·맞은편 모서리·복사 범위가 같으면 앞 셈을 그대로 쓴다(보이는 칸마다 불린다).
function selMarks(S) {
  const sel = S.sel
  const a = S.anchor
  const f = S.focus
  const copied = selCopied(S)
  const last = sel.marks
  if (last && last.ar === a.r && last.ac === a.c && last.fr === f.r && last.fc === f.c && last.copied === copied) return last
  const rect = rectNorm(a, f)
  sel.marks = { ar: a.r, ac: a.c, fr: f.r, fc: f.c, copied, rect, multi: rectSize(rect).cells > 1 }
  return sel.marks
}

function selPaintCell(S, el, r, c) {
  if (!S.sel) return
  const marks = selMarks(S)
  let mask = 0
  if (marks.multi && rectHas(marks.rect, r, c)) {
    mask = rectEdges(marks.rect, r, c) | 16
    if (r !== S.anchor.r || c !== S.anchor.c) mask |= 32
  }
  if (marks.copied && rectHas(marks.copied, r, c)) mask |= 64 | (rectEdges(marks.copied, r, c) << 7)
  // core 가 새로 지은 칸에는 이 표지가 하나도 없다(기억 없음 = 0).
  const before = el.__egSel || 0
  el.__egSel = mask
  const diff = before ^ mask
  if (!diff) return
  for (let bit = 0; bit < SEL_CLASSES.length; bit += 1) {
    const flag = 1 << bit
    if (diff & flag) el.classList.toggle(SEL_CLASSES[bit], Boolean(mask & flag))
  }
}

// 그려 둔 칸 전부의 표지만 다시(복사 점선이 서거나 지워질 때 — 고름은 그대로라 core 를 부르지 않는다).
function selMarkAll(S) {
  if (!S.dom || !S.model) return
  for (const line of S.dom.body.children) {
    const r = Number(line.dataset.r)
    for (const cell of line.children) selPaintCell(S, cell, r, Number(cell.dataset.c))
  }
}

// 머리 칸 표지 — 고른 범위의 칸 머리 밑줄(엑셀 칸 머리 강조).
function selPaintHead(S) {
  if (!S.dom || !S.model || !S.sel) return
  const rect = selMarks(S).rect
  for (const cell of S.dom.head.children) {
    const c = Number(cell.dataset.c)
    cell.classList.toggle('is-sel-col', c >= rect.c0 && c <= rect.c1)
  }
}

// ---------------------------------------------------------------- 끌기·자동 스크롤

// 끌기를 시작한다 — 스크롤 칸이 손을 붙들고(pointer capture) 프레임마다 손이 창 밖이면 굴린다. 손 밑 칸이 바뀌면 move(S, cell).
function selDrag(S, event, handlers) {
  if (!S.sel || !S.dom) return
  selDragEnd(S, true)
  const start = cellAtPoint(S, event.clientX, event.clientY, true)
  const drag = {
    id: event.pointerId, x: event.clientX, y: event.clientY, handlers: handlers || {}, frame: 0, last: null, scrolled: 0,
    leftOverFrozen: Boolean(start && start.c >= S.frozen),
  }
  S.sel.drag = drag
  const scroller = S.dom.scroller
  if (event.pointerId !== undefined && typeof scroller.setPointerCapture === 'function') {
    try {
      scroller.setPointerCapture(event.pointerId)
    } catch (error) {
      drag.capture = false
    }
  }
  drag.frame = requestAnimationFrame(() => selDragTick(S))
}

function selDragTick(S) {
  const drag = S.sel && S.sel.drag
  if (!drag || !S.dom || !S.model) return
  const scroller = S.dom.scroller
  const box = scroller.getBoundingClientRect()
  const view = {
    left: box.left + (scroller.clientLeft || 0), top: box.top + (scroller.clientTop || 0), width: scroller.clientWidth,
    height: scroller.clientHeight, headH: S.headH, frozenWidth: S.frozenWidth, scrollLeft: scroller.scrollLeft,
  }
  const step = dragScrollStep(drag.x, drag.y, view, drag.leftOverFrozen)
  if (step.dx || step.dy) {
    const top = scroller.scrollTop
    const left = scroller.scrollLeft
    if (step.dy) scroller.scrollTop = top + step.dy
    if (step.dx) scroller.scrollLeft = Math.max(left + step.dx, 0)
    if (scroller.scrollTop !== top || scroller.scrollLeft !== left) drag.scrolled += 1
  }
  selDragUpdate(S)
  if (S.sel && S.sel.drag === drag) drag.frame = requestAnimationFrame(() => selDragTick(S))
}

// 손 밑 칸(표 밖이면 끝 칸). 고정 칸 위에서 왼쪽으로 굴리는 동안은 고정 칸이 아니라 보이는 첫 굴림 칸이다.
function selDragCell(S, drag) {
  const cell = cellAtPoint(S, drag.x, drag.y, true)
  if (!cell) return null
  const scrollLeft = S.dom.scroller.scrollLeft
  if (drag.leftOverFrozen && cell.c < S.frozen && scrollLeft > 0) {
    return { r: cell.r, c: Math.min(Math.max(colAtX(S.lefts, S.frozenWidth + scrollLeft), S.frozen), S.model.colCount - 1) }
  }
  return cell
}

function selDragUpdate(S) {
  const drag = S.sel && S.sel.drag
  if (!drag) return
  const cell = selDragCell(S, drag)
  if (!cell || (drag.last && drag.last.r === cell.r && drag.last.c === cell.c)) return
  drag.last = cell
  if (drag.handlers.move) drag.handlers.move(S, cell)
}

function selDragEnd(S, cancelled) {
  const drag = S.sel && S.sel.drag
  if (!drag) return
  S.sel.drag = null
  if (drag.frame) cancelAnimationFrame(drag.frame)
  const scroller = S.dom && S.dom.scroller
  if (scroller && drag.id !== undefined && typeof scroller.releasePointerCapture === 'function') {
    try {
      scroller.releasePointerCapture(drag.id)
    } catch (error) {
      drag.capture = false
    }
  }
  S.sel.lastDrag = { scrolled: drag.scrolled, cell: drag.last }
  if (drag.handlers.end) drag.handlers.end(S, drag.last, Boolean(cancelled))
}

function selOnPointerMove(S, event) {
  const drag = S.sel && S.sel.drag
  if (!drag || (drag.id !== undefined && event.pointerId !== undefined && event.pointerId !== drag.id)) return
  drag.x = event.clientX
  drag.y = event.clientY
  selDragUpdate(S)
}

function selOnPointerUp(S, event, cancelled) {
  const drag = S.sel && S.sel.drag
  if (!drag || (drag.id !== undefined && event.pointerId !== undefined && event.pointerId !== drag.id)) return
  if (!cancelled && event.clientX !== undefined) {
    drag.x = event.clientX
    drag.y = event.clientY
    selDragUpdate(S)
  }
  selDragEnd(S, cancelled)
}

// ---------------------------------------------------------------- 복사·비우기·붙여넣기

// 고른 범위의 복사 글 — 보기 차례(정렬·필터 뒤) 그대로, 수 칸은 원값(rawText), 분류 칸은 표시명.
function selCopyText(S, rect) {
  const lines = []
  for (let r = rect.r0; r <= rect.r1; r += 1) {
    const line = []
    for (let c = rect.c0; c <= rect.c1; c += 1) line.push(rawText(S, r, c))
    lines.push(line)
  }
  return toTsv(lines)
}

// 동기 copy 이벤트(Ctrl+C·브라우저 메뉴) — 칸 편집기 안이면 브라우저 기본 복사에 맡긴다.
function selOnCopy(S, event) {
  if (!S.model || S.edit || event.target === S.dom.editor || !S.view.order.length || !event.clipboardData) return
  const began = performance.now()
  const rect = S.range()
  const text = selCopyText(S, rect)
  event.clipboardData.setData('text/plain', text)
  event.preventDefault()
  const cells = rectSize(rect).cells
  S.sel.copied = Object.assign({}, rect, { order: S.view.order, table: S.model.table })
  S.sel.lastCopy = { cells, chars: text.length, ms: performance.now() - began }
  selMarkAll(S)
  setStatus(S, selText(S, 'copied', '{n}칸 복사함', cells))
}

function selOnCut(S, event) {
  if (!S.model || S.edit || event.target === S.dom.editor) return
  event.preventDefault()
  setStatus(S, selText(S, 'cut', ''))
}

// Delete — 고른 범위 비우기(clear op 하나, 분류 칸은 빼고 값 칸만).
function selClear(S) {
  const rect = S.range()
  const cols = colNames(S, rect.c0, rect.c1)
  selDropCopy(S)
  if (!cols.length) {
    setStatus(S, selText(S, 'locked', ''))
    return
  }
  const keys = rowKeys(S, rect.r0, rect.r1)
  if (queueOp(S, { op: 'clear', rows: keys, cols })) setStatus(S, selText(S, 'cleared', '{n}칸 비움', keys.length * cols.length))
}

function selOnPaste(S, event) {
  if (event.defaultPrevented || !S.model || S.edit || event.target === S.dom.editor || !S.view.order.length) return
  event.preventDefault()
  const text = (event.clipboardData && event.clipboardData.getData('text/plain')) || ''
  if (!text) return
  const matrix = parseClipboard(text)
  for (const item of FEATURES) if (item.name !== 'select' && item.paste && item.paste(S, matrix, event) === true) return
  selPaste(S, matrix)
}

// 기준 칸 붙여넣기 — 고른 범위 왼쪽 위부터 덩어리 그대로(write op 하나). 붙인 자리를 고른다.
function selPaste(S, matrix) {
  const m = S.model
  const rect = S.range()
  const plan = pasteAtAnchor(rect.r0, rect.c0, matrix, S.view.order.length, m.colCount, m.keyCount)
  const limit = Number(S.limits && S.limits.paste) || SEL_FALLBACK_PASTE_LIMIT
  if (!plan.cells) {
    setStatus(S, selText(S, plan.skipped ? 'locked' : 'clipped', '', plan.clipped))
    return
  }
  if (plan.cells > limit) {
    setStatus(S, selText(S, 'pasteLimit', ''))
    return
  }
  const op = { op: 'write', rows: rowKeys(S, plan.r0, plan.r1), cols: colNames(S, plan.c0, plan.c1), values: plan.values }
  if (!queueOp(S, op)) return
  setRange(S, { r: plan.span.r0, c: plan.span.c0 }, { r: plan.span.r1, c: plan.span.c1 })
  const notes = [selText(S, 'pasted', '{n}칸 붙여넣음', plan.cells)]
  if (plan.skipped) notes.push(selText(S, 'pasteSkipped', '분류 칸 {n}칸은 건너뛰었습니다', plan.skipped))
  if (plan.clipped) notes.push(selText(S, 'clipped', '', plan.clipped))
  setStatus(S, notes.filter(Boolean).join(' · '))
}

// ---------------------------------------------------------------- 키

function selIsBlank(S, r, c) {
  const value = valueAt(S, r, c)
  return value === null || value === ''
}

function selPageCols(S) {
  const room = S.dom.scroller.clientWidth - S.frozenWidth
  const widths = S.widths.slice(S.frozen)
  const typical = widths.length ? widths.reduce((sum, width) => sum + width, 0) / widths.length : 80
  return Math.max(Math.floor(room / Math.max(typical, 1)), 1)
}

function selSpan(S, kind) {
  const span = rectSpan(kind, S.anchor, S.focus, S.view.order.length, S.model.colCount)
  if (span) setRange(S, span.anchor, span.focus)
}

function selKey(S, event) {
  if (S.edit || !S.model) return false
  const ctrl = event.ctrlKey || event.metaKey
  const key = event.key
  const lower = key.length === 1 ? key.toLowerCase() : key
  if (key === 'Escape') {
    if (!selCopied(S)) return false
    event.preventDefault()
    selDropCopy(S)
    return true
  }
  if (!S.view.order.length) return false
  const plainCtrl = ctrl && !event.altKey && !event.shiftKey
  if (plainCtrl && lower === 'c') {
    // 막지 않는다 — 브라우저가 초점 칸(스크롤 칸)에 copy 이벤트를 쏜다. 페이지 글이 골라져 있으면 그 글이 가므로 먼저 지운다.
    selClearPageSelection()
    return true
  }
  if (plainCtrl && lower === 'x') {
    event.preventDefault()
    setStatus(S, selText(S, 'cut', ''))
    return true
  }
  if (plainCtrl && lower === 'a') {
    event.preventDefault()
    selSpan(S, 'all')
    return true
  }
  if (key === ' ' && !event.altKey && (ctrl || event.shiftKey)) {
    event.preventDefault()
    selSpan(S, ctrl && event.shiftKey ? 'all' : ctrl ? 'col' : 'row')
    return true
  }
  if (event.shiftKey && SEL_MOVE_KEYS.has(key)) {
    const m = S.model
    const moved = moveCell(S.focus, key, { ctrl, alt: event.altKey }, S.view.order.length, m.colCount, visibleRowCount(S), selPageCols(S), (r, c) => selIsBlank(S, r, c))
    if (!moved) return false
    event.preventDefault()
    setRange(S, S.anchor, moved)
    scrollToCell(S, moved.r, moved.c)
    return true
  }
  if (key === 'Delete' && !ctrl && !event.altKey) {
    event.preventDefault()
    selClear(S)
    return true
  }
  return false
}

// 칸 누름 = 그 칸, Shift+누름 = 지금 칸에서 그 칸까지, 끌기 = 네모 범위(Shift 와 함께면 지금 칸에서).
function selPointerDown(S, event, hit) {
  if (hit.kind !== 'cell') return false
  event.preventDefault()
  if (S.edit) commitEdit(S, null, false)
  selClearPageSelection()
  focusGrid(S)
  const cell = { r: hit.r, c: hit.c }
  setRange(S, event.shiftKey ? S.anchor : cell, cell)
  selDrag(S, event, {
    move(state, at) {
      if (at.r !== state.focus.r || at.c !== state.focus.c) setRange(state, state.anchor, at)
    },
  })
  return true
}

function selInit(S) {
  S.sel = { listeners: [], drag: null, copied: null, marks: null, lastCopy: null, lastDrag: null }
  const scroller = S.dom.scroller
  selListen(S, scroller, 'pointermove', (event) => selOnPointerMove(S, event))
  selListen(S, scroller, 'pointerup', (event) => selOnPointerUp(S, event, false))
  selListen(S, scroller, 'pointercancel', (event) => selOnPointerUp(S, event, true))
  selListen(S, scroller, 'lostpointercapture', (event) => selOnPointerUp(S, event, false))
  selListen(S, scroller, 'copy', (event) => selOnCopy(S, event))
  selListen(S, scroller, 'cut', (event) => selOnCut(S, event))
  selListen(S, scroller, 'paste', (event) => selOnPaste(S, event))
}

function selCleanup(S) {
  if (!S.sel) return
  selDragEnd(S, true)
  for (const [target, type, handler] of S.sel.listeners) target.removeEventListener(type, handler)
  S.sel.listeners = []
}

feature({ name: 'select', init: selInit, keydown: selKey, pointerdown: selPointerDown, paintCell: selPaintCell, paintOverlay: selPaintHead, cleanup: selCleanup })
