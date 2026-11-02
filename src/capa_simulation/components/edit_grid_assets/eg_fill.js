// 범용 편집 그리드 — 붙여넣기·채우기(FILL): paste 갈고리(값 하나 → 고른 범위 전체, 고른 범위가 덩어리의 정수 배면 되풀이, 아니면
// 기준 칸부터 — 잠긴 분류 칸은 건너뛰고 수를 알림)·채우기 손잡이 끌기(세로·가로 가운데 더 멀리 끈 쪽 하나로 늘이고 원본 덩어리를
// 되풀이 — 수열 외삽 없음, 네 방향)·Ctrl+D/Ctrl+R(범위 첫 줄·첫 칸으로, 한 줄·한 칸이면 바로 위·왼쪽에서)·편집 중 Ctrl+Enter(고른
// 범위 전체에 그 값). 순수 구획 `// <eg-paste>`·`// <eg-fill>` 은 node 시험이 떼어 돌린다(`<eg-paste>` 는 eg_select 의
// `pasteAtAnchor` 를 쓴다). 갈고리는 `feature({ name: 'fill', ... })` 하나로 단다.
//
// 채우기는 값을 싣지 않는다 — `fill` op(채울 줄·칸 + 원본 줄·칸 + 방향)를 보내고 서버가 지금 원본 칸 값(초안 ∪ 양식)에서
// 되풀이한다(`services/edit_grid._new_states`). 붙여넣기 되풀이는 덩어리 한 벌만 싣는다 — 서버 `write` 가 (i mod h, j mod w) 로
// 되풀이하므로, 고른 범위가 분류 칸에서 시작하면 덩어리 칸을 첫 값 칸의 자리만큼 돌려 싣는다.

// <eg-paste>
// 붙여넣기 판. rect = 고른 범위(보기 좌표), matrix = 칸 판(parseClipboard), rows·cols = 보기 줄 수·전체 칸 수, keyCount = 앞의 잠긴
// 분류 칸 수. 고른 범위가 덩어리(h×w)보다 크고 그 정수 배면 되풀이(tiled) — values 는 덩어리 한 벌(h × w, 모자란 칸은 null =
// 그대로)이고 c0 은 첫 값 칸이다. 아니면 기준 칸(고른 범위 왼쪽 위)부터 덩어리 그대로(pasteAtAnchor). valueCells 는 싣는 값 칸
// 수(서버 상한 `PASTE_CELL_LIMIT` 과 견준다), cells 는 실제로 쓰는 칸 수.
function planPaste(rect, matrix, rows, cols, keyCount) {
  const bh = matrix.length
  const bw = matrix.reduce((most, line) => Math.max(most, line.length), 0)
  const h = rect.r1 - rect.r0 + 1
  const w = rect.c1 - rect.c0 + 1
  const tiled = bh > 0 && bw > 0 && (h > bh || w > bw) && h % bh === 0 && w % bw === 0
  if (!tiled) {
    const plan = pasteAtAnchor(rect.r0, rect.c0, matrix, rows, cols, keyCount)
    return Object.assign(plan, { tiled: false, valueCells: plan.values.reduce((sum, line) => sum + line.length, 0) })
  }
  const v0 = Math.max(rect.c0, keyCount)
  const span = { r0: rect.r0, r1: rect.r1, c0: rect.c0, c1: rect.c1 }
  const skipped = h * (Math.min(v0, rect.c1 + 1) - rect.c0)
  if (v0 > rect.c1) return { tiled: true, r0: rect.r0, r1: rect.r1, c0: v0, c1: rect.c1, values: [], cells: 0, valueCells: 0, clipped: 0, skipped, span }
  const shift = (v0 - rect.c0) % bw
  const values = matrix.map((line) => {
    const out = []
    for (let j = 0; j < bw; j += 1) {
      const value = line[(j + shift) % bw]
      out.push(value === undefined ? null : value)
    }
    return out
  })
  let cells = 0
  for (let i = 0; i < h; i += 1) {
    const line = values[i % bh]
    for (let c = v0; c <= rect.c1; c += 1) if (line[(c - v0) % bw] !== null) cells += 1
  }
  return { tiled: true, r0: rect.r0, r1: rect.r1, c0: v0, c1: rect.c1, values, cells, valueCells: bh * bw, clipped: 0, skipped, span }
}
// </eg-paste>

// <eg-fill>
// 채우기 판 — 원본 덩어리를 한 방향으로 되풀이한다(수열 외삽 없음). 보기 좌표다(c < keyCount 는 잠긴 분류 칸). 판 = {dir, rows,
// cols, srcRows, srcCols, cells, skipped, span}: rows·cols 는 채울 줄·값 칸을 원본에서 멀어지는 차례로(아래·오른쪽은 오름, 위·왼쪽은
// 내림 — 서버 `fill` op 의 k 차례), srcRows·srcCols 는 원본 줄·값 칸(오름), cells 는 채울 칸 수, skipped 는 건너뛴 분류 칸 수, span
// 은 원본 ∪ 채울 범위. 원본에 값 칸이 없거나 채울 값 칸이 없으면 {error: 'locked'}, 원본 자리가 없으면 {error: 'noSource'}.
function fillSpan(a, b, descending) {
  const out = []
  if (descending) for (let k = b; k >= a; k -= 1) out.push(k)
  else for (let k = a; k <= b; k += 1) out.push(k)
  return out
}

// src = 원본 범위(분류 칸이 섞일 수 있다 — 값 칸만 원본이 된다), ext = 채울 범위(원본 바깥 한 방향).
function fillPlan(src, dir, ext, keyCount) {
  const v0 = Math.max(src.c0, keyCount)
  if (v0 > src.c1) return { error: 'locked' }
  const back = dir === 'up' || dir === 'left'
  const srcRows = fillSpan(src.r0, src.r1, false)
  const srcCols = fillSpan(v0, src.c1, false)
  const span = { r0: Math.min(src.r0, ext.r0), r1: Math.max(src.r1, ext.r1), c0: Math.min(src.c0, ext.c0), c1: Math.max(src.c1, ext.c1) }
  if (dir === 'down' || dir === 'up') {
    const rows = fillSpan(ext.r0, ext.r1, back)
    return { dir, rows, cols: srcCols, srcRows, srcCols, cells: rows.length * srcCols.length, skipped: rows.length * (v0 - src.c0), span }
  }
  const all = fillSpan(ext.c0, ext.c1, back)
  const cols = all.filter((c) => c >= keyCount)
  if (!cols.length) return { error: 'locked' }
  return { dir, rows: srcRows, cols, srcRows, srcCols, cells: srcRows.length * cols.length, skipped: srcRows.length * (all.length - cols.length), span }
}

// 손잡이를 끈 칸 → 판. 고른 범위 밖으로 세로·가로 가운데 더 멀리(칸 수) 나간 쪽 하나로만 늘린다 — 같으면 세로(엑셀). 범위 안(되끌기)
// 이면 null(1차에 무시).
function fillByHandle(rect, cell, keyCount) {
  const down = cell.r - rect.r1
  const up = rect.r0 - cell.r
  const right = cell.c - rect.c1
  const left = rect.c0 - cell.c
  const vertical = Math.max(down, up, 0)
  const horizontal = Math.max(right, left, 0)
  if (!vertical && !horizontal) return null
  const ext = Object.assign({}, rect)
  let dir
  if (vertical >= horizontal) {
    dir = down > 0 ? 'down' : 'up'
    if (dir === 'down') Object.assign(ext, { r0: rect.r1 + 1, r1: cell.r })
    else Object.assign(ext, { r0: cell.r, r1: rect.r0 - 1 })
  } else {
    dir = right > 0 ? 'right' : 'left'
    if (dir === 'right') Object.assign(ext, { c0: rect.c1 + 1, c1: cell.c })
    else Object.assign(ext, { c0: cell.c, c1: rect.c0 - 1 })
  }
  return fillPlan(rect, dir, ext, keyCount)
}

// Ctrl+D(axis 'down') · Ctrl+R('right') → 판. 여러 줄이면 첫 줄이 원본·나머지가 채울 줄, 한 줄이면 보기에서 바로 위 줄이 원본. 칸도
// 같되 분류 칸은 건너뛴다 — 고른 범위의 첫 값 칸이 원본이고(한 값 칸뿐이면 바로 왼쪽 값 칸), 범위 안 분류 칸은 skipped 로 센다.
function fillByKey(rect, axis, keyCount) {
  if (axis === 'down') {
    if (rect.r0 === rect.r1) {
      if (rect.r0 <= 0) return { error: 'noSource' }
      return fillPlan(Object.assign({}, rect, { r0: rect.r0 - 1, r1: rect.r0 - 1 }), 'down', rect, keyCount)
    }
    return fillPlan(Object.assign({}, rect, { r1: rect.r0 }), 'down', Object.assign({}, rect, { r0: rect.r0 + 1 }), keyCount)
  }
  const v0 = Math.max(rect.c0, keyCount)
  if (v0 > rect.c1) return { error: 'locked' }
  const single = v0 === rect.c1
  if (single && v0 - 1 < keyCount) return { error: 'noSource' }
  const src = Object.assign({}, rect, single ? { c0: v0 - 1, c1: v0 - 1 } : { c0: v0, c1: v0 })
  const plan = fillPlan(src, 'right', Object.assign({}, rect, { c0: single ? v0 : v0 + 1 }), keyCount)
  if (!plan.error) plan.skipped += (rect.r1 - rect.r0 + 1) * (v0 - rect.c0)
  return plan
}
// </eg-fill>

// ---------------------------------------------------------------- 알림

const FILL_HANDLE_PX = 7

function fillNotes(S, main, skipped, clipped, extra) {
  const notes = [main]
  if (extra) notes.push(extra)
  if (skipped) notes.push(selText(S, 'pasteSkipped', '분류 칸 {n}칸은 건너뛰었습니다', skipped))
  if (clipped) notes.push(selText(S, 'clipped', '표 끝을 넘은 {n}칸은 버렸습니다', clipped))
  const text = notes.filter(Boolean).join(' · ')
  setStatus(S, text)
  // 건너뛰거나 버린 칸이 있으면 그리드 토스트로도 — 상태 줄 글은 4초 뒤 사라져 놓치기 쉽다.
  if (skipped || clipped) toast(S, text)
}

function fillError(S, code) {
  if (code === 'noSource') setStatus(S, selText(S, 'fillNoSource', '채울 원본이 없습니다'))
  else setStatus(S, selText(S, 'locked', '분류 칸은 고칠 수 없습니다'))
}

// ---------------------------------------------------------------- 붙여넣기

// select 의 paste 이벤트가 넘긴 칸 판을 먼저 가져간다(true — select 의 기준 칸 붙여넣기를 건너뜀).
function fillPaste(S, matrix) {
  const m = S.model
  const plan = planPaste(S.range(), matrix, S.view.order.length, m.colCount, m.keyCount)
  const limit = Number(S.limits && S.limits.paste) || SEL_FALLBACK_PASTE_LIMIT
  if (!plan.cells) {
    setStatus(S, selText(S, plan.skipped ? 'locked' : 'clipped', '', plan.clipped))
    return true
  }
  if (plan.valueCells > limit) {
    setStatus(S, selText(S, 'pasteLimit', ''))
    return true
  }
  const op = { op: 'write', rows: rowKeys(S, plan.r0, plan.r1), cols: colNames(S, plan.c0, plan.c1), values: plan.values }
  if (!queueOp(S, op)) return true
  if (!plan.tiled) setRange(S, { r: plan.span.r0, c: plan.span.c0 }, { r: plan.span.r1, c: plan.span.c1 })
  fillNotes(S, selText(S, 'pasted', '{n}칸 붙여넣음', plan.cells), plan.skipped, plan.clipped, plan.tiled ? selText(S, 'pasteTiled', '') : '')
  return true
}

// ---------------------------------------------------------------- 채우기 보내기

// 보기 줄 목록(임의 차례) → 업무 키, 값 칸 목록 → 월 이름.
function fillRowKeys(S, list) {
  if (!list.length) return []
  const lo = list.reduce((low, r) => Math.min(low, r), list[0])
  const hi = list.reduce((high, r) => Math.max(high, r), list[0])
  const keys = rowKeys(S, lo, hi)
  return list.map((r) => keys[r - lo])
}

function fillColNames(S, list) {
  if (!list.length) return []
  const lo = list.reduce((low, c) => Math.min(low, c), list[0])
  const hi = list.reduce((high, c) => Math.max(high, c), list[0])
  const names = colNames(S, lo, hi)
  return list.map((c) => names[c - lo])
}

// 채운 범위를 고른다 — 지금 칸이 그 범위의 모서리면 그대로 두고 맞은편을 민다(엑셀).
function fillSelect(S, span) {
  const a = S.anchor
  const corner = (a.r === span.r0 || a.r === span.r1) && (a.c === span.c0 || a.c === span.c1)
  const anchor = corner ? a : { r: span.r0, c: span.c0 }
  setRange(S, anchor, { r: anchor.r === span.r0 ? span.r1 : span.r0, c: anchor.c === span.c0 ? span.c1 : span.c0 })
}

function fillSend(S, plan, select) {
  if (!plan) return
  if (plan.error) {
    fillError(S, plan.error)
    return
  }
  const op = {
    op: 'fill', dir: plan.dir, rows: fillRowKeys(S, plan.rows), cols: fillColNames(S, plan.cols),
    src: { rows: fillRowKeys(S, plan.srcRows), cols: fillColNames(S, plan.srcCols) },
  }
  if (!queueOp(S, op)) return
  if (select) fillSelect(S, plan.span)
  fillNotes(S, selText(S, 'filled', '{n}칸 채움', plan.cells), plan.skipped, 0, '')
}

// 편집 중 Ctrl+Enter — 고른 범위 전체에 칸 편집기의 글(write 1×1 을 서버가 되풀이). 한 칸이고 글이 처음과 같으면 보내지 않는다.
function fillEnterAll(S) {
  const edit = S.edit
  const text = S.dom.editor.value
  const rect = S.range()
  cancelEdit(S)
  if (rect.r0 === rect.r1 && rect.c0 === rect.c1 && text === edit.original) return
  const cols = colNames(S, rect.c0, rect.c1)
  if (!cols.length) {
    fillError(S, 'locked')
    return
  }
  const rows = rowKeys(S, rect.r0, rect.r1)
  if (!queueOp(S, { op: 'write', rows, cols, values: [[text]] })) return
  fillNotes(S, selText(S, 'filledAll', '{n}칸에 같은 값', rows.length * cols.length), rows.length * (rect.c1 - rect.c0 + 1 - cols.length), 0, '')
}

// ---------------------------------------------------------------- 손잡이·덮개

// 칸 왼쪽 끝의 캔버스 x — 고정 칸은 sticky 라 가로 스크롤만큼 밀려 보인다.
function fillColX(S, c) {
  return S.lefts[c] + (c < S.frozen ? S.dom.scroller.scrollLeft : 0)
}

function fillPlace(el, left, top, width, height) {
  el.style.left = left + 'px'
  el.style.top = top + 'px'
  if (width === undefined) return
  el.style.width = width + 'px'
  el.style.height = height + 'px'
}

// 손잡이(고른 범위 오른쪽 아래 7×7)와 끄는 동안 채울 범위 점선 테. 칸 편집 중·표가 비었을 때·고른 범위에 값 칸이 없을 때는 손잡이를
// 숨긴다. 고정 칸은 분류 칸뿐이라 손잡이 칸(값 칸)은 늘 함께 구르고, 점선 테 왼쪽 끝만 고정 칸에 설 수 있다.
function fillPaintOverlay(S) {
  const fill = S.fill
  if (!fill || !S.dom) return
  const m = S.model
  const n = m ? S.view.order.length : 0
  const rect = n ? S.range() : null
  const show = Boolean(rect && !S.edit && rect.c1 >= m.keyCount)
  fill.handle.hidden = !show
  if (show) {
    const right = fillColX(S, rect.c1) + S.widths[rect.c1]
    const bottom = S.headH + (rect.r1 + 1) * S.rowH
    fillPlace(fill.handle, Math.max(Math.min(right - 4, S.total - FILL_HANDLE_PX), 0), Math.min(bottom - 4, S.headH + n * S.rowH - FILL_HANDLE_PX))
    const title = selText(S, 'fillHandle', '')
    if (title && fill.handle.title !== title) fill.handle.title = title
  }
  const plan = fill.drag && fill.drag.plan && !fill.drag.plan.error ? fill.drag.plan : null
  fill.box.hidden = !plan
  if (!plan) return
  const span = plan.span
  const left = fillColX(S, span.c0)
  const right = fillColX(S, span.c1) + S.widths[span.c1]
  fillPlace(fill.box, left, S.headH + span.r0 * S.rowH, Math.max(right - left, 0), (span.r1 - span.r0 + 1) * S.rowH)
}

function fillPointerDown(S, event, hit) {
  if (hit.kind !== 'handle' || !S.view.order.length) return false
  event.preventDefault()
  if (S.edit) commitEdit(S, null, false)
  selClearPageSelection()
  focusGrid(S)
  S.fill.drag = { src: S.range(), plan: null }
  S.dom.scroller.classList.add('is-filling')
  selDrag(S, event, {
    move(state, cell) {
      const drag = state.fill.drag
      if (!drag) return
      drag.plan = fillByHandle(drag.src, cell, state.model.keyCount)
      fillPaintOverlay(state)
    },
    end(state, cell, cancelled) {
      const drag = state.fill.drag
      state.fill.drag = null
      if (state.dom) state.dom.scroller.classList.remove('is-filling')
      fillPaintOverlay(state)
      if (!cancelled && drag && drag.plan && state.model) fillSend(state, drag.plan, true)
    },
  })
  fillPaintOverlay(S)
  return true
}

// ---------------------------------------------------------------- 키

function fillKey(S, event) {
  const ctrl = event.ctrlKey || event.metaKey
  if (S.edit) {
    if (event.key !== 'Enter' || !ctrl || event.altKey || event.shiftKey) return false
    event.preventDefault()
    fillEnterAll(S)
    return true
  }
  if (!S.model || !S.view.order.length) return false
  if (event.key === 'Escape' && S.fill && S.fill.drag) {
    event.preventDefault()
    selDragEnd(S, true)
    return true
  }
  if (!ctrl || event.altKey || event.shiftKey) return false
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key
  // 한글 입력 상태에서는 key 가 「ㅇ」·「ㄱ」 로 온다 — 라틴 글자가 아니면 자판 자리(code)로 본다.
  const latin = /^[a-z]$/.test(key)
  const axis = key === 'd' || (!latin && event.code === 'KeyD') ? 'down' : key === 'r' || (!latin && event.code === 'KeyR') ? 'right' : ''
  if (!axis) return false
  // 브라우저 기본(Ctrl+D 책갈피·Ctrl+R 새로 읽기)을 막는다.
  event.preventDefault()
  fillSend(S, fillByKey(S.range(), axis, S.model.keyCount), false)
  return true
}

// ---------------------------------------------------------------- 마운트

function fillInit(S) {
  const handle = document.createElement('div')
  handle.className = 'eg-handle'
  handle.hidden = true
  const box = document.createElement('div')
  box.className = 'eg-fill-box'
  box.hidden = true
  S.dom.overlay.appendChild(box)
  S.dom.overlay.appendChild(handle)
  S.fill = { handle, box, drag: null }
}

function fillCleanup(S) {
  if (!S.fill) return
  S.fill.drag = null
  if (S.dom) S.dom.scroller.classList.remove('is-filling')
}

feature({ name: 'fill', init: fillInit, keydown: fillKey, pointerdown: fillPointerDown, paintOverlay: fillPaintOverlay, paste: fillPaste, cleanup: fillCleanup })
