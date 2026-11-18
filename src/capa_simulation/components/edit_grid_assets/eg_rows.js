// 범용 편집 그리드 — 줄 규칙을 쓰는 표의 갈래(글 · 고르기 칸, 줄 규칙 잠금, 줄 지우기 · 되살리기, 고르기 목록). 이 파일은
// 줄 규칙 표의 등록(`components/edit_grid.ROWS_JS_PARTS` — 접속 명단)에만 실린다. 순수 구획 `// <eg-kinds>` 는 node 시험이
// 떼어 돌린다(eg_pure 의 `// <eg-format>` 뒤에 — KINDS · STRIP_EDGES · numberText 를 쓴다). 갈고리는 `feature({ name: 'rows', ... })`
// 하나다(eg_pure.js 의 FEATURES — 차례 select → fill → toolbar → rows).

// <eg-kinds>
// 글 · 고르기 칸 다듬기와 표시(Python `_coerce_text` · `_coerce_choice` · `format_value` 와 같은 규칙 — 쌍둥이 시험).
const KIND_CONTROL = /[\x00-\x1f\x7f]/
const KIND_BLANK = { value: null, error: null, text: null }

KINDS.text = {
  parse(raw, fmt, template) {
    if (raw === null || raw === undefined) return KIND_BLANK
    let text
    let body
    if (typeof raw === 'number') {
      text = Number.isFinite(raw) ? numberText(raw) : String(raw)
      body = text
    } else if (typeof raw === 'string') {
      text = raw
      body = raw.replace(STRIP_EDGES, '')
    } else return { value: null, error: 'text', text: String(raw) }
    if (!body) return KIND_BLANK
    if (template !== null && template !== undefined && body === template) return { value: body, error: null, text: null }
    if (KIND_CONTROL.test(body)) return { value: null, error: 'text', text }
    if (fmt.maxLength && Array.from(body).length > fmt.maxLength) return { value: null, error: 'len', text }
    if (fmt.pattern && !new RegExp('^(?:' + fmt.pattern + ')$').test(body)) return { value: null, error: 'pattern', text }
    return { value: body, error: null, text: null }
  },
  format(value) {
    return typeof value === 'number' ? numberText(value) : String(value)
  },
}

KINDS.choice = {
  parse(raw, fmt) {
    const options = fmt.options || []
    if (raw === null || raw === undefined) return KIND_BLANK
    if (typeof raw === 'number') {
      if (Number.isFinite(raw) && raw === Math.floor(raw) && raw >= 0 && raw < options.length) return { value: raw + 0, error: null, text: null }
      return { value: null, error: 'choice', text: Number.isFinite(raw) ? numberText(raw) : String(raw) }
    }
    if (typeof raw !== 'string') return { value: null, error: 'choice', text: String(raw) }
    const body = raw.replace(STRIP_EDGES, '')
    if (!body) return KIND_BLANK
    const at = options.indexOf(body)
    return at >= 0 ? { value: at, error: null, text: null } : { value: null, error: 'choice', text: raw }
  },
  format(value, fmt) {
    const options = fmt.options || []
    return typeof value === 'number' && value === Math.floor(value) && value >= 0 && value < options.length ? String(options[value]) : ''
  },
}

// 줄 규칙(껍데기 locks — {kinds: [{cols, reason, remove, fresh}], rows: [규칙 번호 | -1]})에서 원본 줄의 규칙.
function rowRule(locks, row) {
  if (!locks) return null
  const at = (locks.rows || [])[row]
  return at >= 0 ? (locks.kinds || [])[at] || null : null
}

// 고른 줄 → 줄 지우기 판 {keys, restore, why}. 지울 수 없는 줄은 빼고 그 까닭을 남긴다. 고른 줄이 모두 지운 줄이면 되살리기다
// (빈 새 줄은 지운 줄이 되지 않는다 — 지우기가 칸을 비운다).
function rowPlan(rows, keys, locks, removed) {
  const plan = { keys: [], restore: true, why: '' }
  for (const row of rows) {
    const rule = rowRule(locks, row)
    if (rule && rule.remove) {
      plan.why = String(rule.remove)
      continue
    }
    plan.keys.push(keys[row])
    if (!removed.has(row)) plan.restore = false
  }
  if (!plan.keys.length) plan.restore = false
  return plan
}
// </eg-kinds>

// 원본 줄 · 값 칸을 고칠 수 없는 까닭(core 의 S.lockAt) — 지운 줄은 모든 칸, 그 밖은 줄 규칙이 잠근 칸.
function rowsLockAt(S, row, vc) {
  const m = S.model
  if (!m) return ''
  if (m.removed.has(row)) return egText(S, 'removedRow', '')
  const rule = rowRule(m.locks, row)
  return rule && (rule.cols || []).indexOf(vc) >= 0 ? String(rule.reason || '') : ''
}

function rowsPicked(S) {
  const m = S.model
  const rect = S.range()
  const rows = []
  for (let r = rect.r0; r <= Math.min(rect.r1, S.view.order.length - 1); r += 1) rows.push(S.view.order[r])
  return rowPlan(rows, m.keys, m.locks, m.removed)
}

function rowsInit(S) {
  const R = (S.rows = { listeners: [], button: null, list: null, key: '' })
  S.lockAt = rowsLockAt
  const button = tbButton('eg-tb-rows', '')
  button.hidden = true
  const fit = S.tb && S.tb.dom ? S.tb.dom.fit : null
  if (fit) S.dom.toolbar.insertBefore(button, fit)
  else S.dom.toolbar.appendChild(button)
  const list = egEl('div', 'eg-choices')
  list.setAttribute('role', 'listbox')
  list.hidden = true
  S.dom.canvas.appendChild(list)
  R.button = button
  R.list = list
  const listen = (target, type, handler) => {
    target.addEventListener(type, handler)
    R.listeners.push([target, type, handler])
  }
  listen(button, 'click', (event) => tbGridCommand(S, event, () => rowsRemove(S)))
  listen(list, 'mousedown', (event) => event.preventDefault())
  listen(list, 'click', (event) => {
    const item = event.target && event.target.closest ? event.target.closest('.eg-choice') : null
    if (!item || !S.edit) return
    S.dom.editor.value = item.textContent
    commitEdit(S, null)
  })
}

// 줄 지우기 단추 · 손짓 — 고른 줄을 지운다(모두 지운 줄이면 되살린다). 지울 수 있는 줄이 없으면 까닭 한 줄.
function rowsRemove(S) {
  const m = S.model
  if (!m || !m.rowOps || S.edit || !S.view.order.length) return false
  const plan = rowsPicked(S)
  if (!plan.keys.length) {
    setStatus(S, plan.why)
    return false
  }
  queueOp(S, { op: plan.restore ? 'restore' : 'remove', rows: plan.keys })
  announce(S, egText(S, plan.restore ? 'rowRestore' : 'rowRemove', ''))
  return true
}

// 단추 글 · 잠김 · 풍선을 지금 고름에 맞춘다(바뀐 것만).
function rowsSync(S) {
  const R = S.rows
  const m = S.model
  const button = R.button
  const on = Boolean(m && m.rowOps)
  if (button.hidden === on) button.hidden = !on
  if (!on) return
  const plan = rowsPicked(S)
  const label = egText(S, plan.restore ? 'rowRestore' : 'rowRemove', '')
  const tip = plan.keys.length ? egText(S, plan.restore ? 'rowRestoreHint' : 'rowRemoveHint', '') : plan.why
  const key = [label, tip, plan.keys.length > 0].join('|')
  if (key === R.key) return
  R.key = key
  button.textContent = label
  button.title = tip
  button.setAttribute('aria-disabled', plan.keys.length ? 'false' : 'true')
  button.classList.toggle('is-off', !plan.keys.length)
}

// 칸 표지 — 지운 줄(지움선) · 잠긴 칸(분류 칸 바탕 + 까닭 풍선) · 글 · 고르기 칸(왼쪽 맞춤).
function rowsPaintCell(S, cell, r, c) {
  const m = S.model
  if (!m || (!m.locks && !m.fmts)) return
  const row = S.view.order[r]
  cell.classList.toggle('is-removed', m.removed.has(row))
  if (c < m.keyCount) return
  const vc = c - m.keyCount
  const why = rowsLockAt(S, row, vc)
  cell.classList.toggle('is-locked', !m.removed.has(row) && Boolean(why))
  cell.classList.toggle('is-text', Boolean(KINDS[fmtOf(m, vc).kind]))
  if (why || cell.title) cell.title = why
}

// 고르기 칸을 고치는 동안 칸 아래에 항목 목록 — 누르면 그 항목으로 확정, 칸 편집기의 ↑ ↓ 가 항목을 옮긴다.
function rowsChoices(S) {
  const R = S.rows
  const m = S.model
  const list = R.list
  const f = S.edit && m ? fmtOf(m, S.edit.c - m.keyCount) : null
  S.dom.editor.classList.toggle('is-text', Boolean(f && KINDS[f.kind]))
  if (!f || f.kind !== 'choice') {
    if (!list.hidden) {
      list.hidden = true
      list.textContent = ''
    }
    return
  }
  const value = S.dom.editor.value.replace(STRIP_EDGES, '')
  list.textContent = ''
  for (const label of f.options || []) {
    const item = egEl('div', 'eg-choice' + (label === value ? ' is-on' : ''), label)
    item.setAttribute('role', 'option')
    item.setAttribute('aria-selected', label === value ? 'true' : 'false')
    list.appendChild(item)
  }
  list.style.left = S.lefts[S.edit.c] + 'px'
  list.style.minWidth = S.widths[S.edit.c] + 'px'
  list.hidden = false
  // 칸 아래가 보이는 창 밖이면 칸 위로 — 아래 줄을 고칠 때 목록이 표 끝에 잘리지 않게.
  const scroller = S.dom.scroller
  const height = list.offsetHeight || (f.options || []).length * S.rowH
  const below = S.headH + (S.edit.r + 1) * S.rowH
  const above = S.headH + S.edit.r * S.rowH - height
  const room = scroller.scrollTop + scroller.clientHeight
  list.style.top = (below + height > room && above >= scroller.scrollTop + S.headH ? above : below) + 'px'
}

function rowsKey(S, event) {
  const m = S.model
  if (!S.edit || !m || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return false
  const f = fmtOf(m, S.edit.c - m.keyCount)
  const options = f.kind === 'choice' ? f.options || [] : []
  if (!options.length) return false
  event.preventDefault()
  const at = options.indexOf(S.dom.editor.value.replace(STRIP_EDGES, ''))
  const step = event.key === 'ArrowDown' ? 1 : -1
  S.dom.editor.value = options[at < 0 ? (step > 0 ? 0 : options.length - 1) : (at + step + options.length) % options.length]
  rowsChoices(S)
  return true
}

function rowsPointerDown(S, event) {
  return Boolean(event.target && event.target.closest && event.target.closest('.eg-choices'))
}

// 붙일 덩어리가 표 끝(빈 새 줄)을 넘으면 거절 글 — 여러 사람을 붙여 앞 몇 줄만 들어가고 나머지가 조용히 잘리지 않게(select 의
// pasteGuard 갈고리). 고른 범위 안에서 되풀이하는 붙여넣기는 표 끝을 넘지 않는다.
function rowsPasteGuard(S, matrix) {
  const short = S.range().r0 + matrix.length - S.view.order.length
  return short > 0 ? selText(S, 'freshShort', '새 줄이 {n}줄 모자라 붙이지 않았습니다', short) : ''
}

function rowsCleanup(S) {
  const R = S.rows
  if (!R) return
  for (const [target, type, handler] of R.listeners) target.removeEventListener(type, handler)
  R.listeners = []
  S.lockAt = null
}

feature({
  name: 'rows', init: rowsInit, keydown: rowsKey, pointerdown: rowsPointerDown, paintCell: rowsPaintCell,
  paintOverlay: (S) => {
    rowsSync(S)
    rowsChoices(S)
  },
  onFeed: rowsSync, onSelect: rowsSync, pasteGuard: rowsPasteGuard, cleanup: rowsCleanup,
})
