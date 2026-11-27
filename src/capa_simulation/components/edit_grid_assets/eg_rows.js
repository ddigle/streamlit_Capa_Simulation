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

// 고르기 목록 거름 — 항목 [{label, value}] 가운데 친 글(앞뒤 공백 걷음)이 보이는 글 · 넣을 글에 든 것만, 대소문자 무시, 앞머리가
// 맞는 항목이 앞(그 안은 항목 차례). 글이 null(칸을 막 연 때) · 빈 글이면 전부.
function listFilter(items, query) {
  const q = query === null ? '' : query.replace(STRIP_EDGES, '').toLowerCase()
  if (!q) return items.slice()
  const head = []
  const rest = []
  for (const item of items) {
    const label = item.label.toLowerCase()
    const value = item.value.toLowerCase()
    if (label.startsWith(q) || value.startsWith(q)) head.push(item)
    else if (label.includes(q) || value.includes(q)) rest.push(item)
  }
  return head.concat(rest)
}

// 글과 같은 항목의 차례(넣을 글 먼저, 다음 보이는 글 — 앞뒤 공백만 걷고 대소문자 그대로), 없으면 -1. 강조는 이것과 ↑ ↓ 뿐이다.
function listMatch(items, text) {
  const body = text.replace(STRIP_EDGES, '')
  if (!body) return -1
  const at = items.findIndex((item) => item.value === body)
  return at >= 0 ? at : items.findIndex((item) => item.label === body)
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
  const R = (S.rows = { listeners: [], button: null, list: null, key: '', pick: null, drawn: null, drawnOn: null })
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
  // 목록 누름은 칸 누름이 아니다 — 목록이 칸 위에 떠 있어 뿌리 pointerdown 이 그 자리 칸을 골라(select 갈래가 먼저) 편집을
  // 닫고 목록을 걷어 click 이 항목에 닿지 않았다. 여기서 멈춰 mousedown(초점 유지) → click(확정)으로 간다.
  listen(list, 'pointerdown', (event) => event.stopPropagation())
  listen(list, 'mousedown', (event) => event.preventDefault())
  listen(list, 'click', (event) => {
    const item = event.target && event.target.closest ? event.target.closest('.eg-choice') : null
    const P = R.pick
    if (!item || !S.edit || !P || P.edit !== S.edit || !P.shown[Number(item.dataset.at)]) return
    S.dom.editor.value = P.shown[Number(item.dataset.at)].value
    commitEdit(S, null)
  })
  // 친 글로 거른다 — 한글 조합 중에도 input 이 오고(값에 조합 글이 든다), 조합 끝(compositionend)에도 다시 본다.
  listen(S.dom.editor, 'input', () => rowsTyped(S))
  listen(S.dom.editor, 'compositionend', () => rowsTyped(S))
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
  queueOp(S, { op: plan.restore ? 'restore' : 'remove', rows: plan.keys }, true)
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

// 편집 중 칸의 목록 상태 {edit, src, all, query, shown, on} — 목록 칸(고르기)이 아니면 null. 칸을 연 때는 전부(지금 값 강조),
// 친 뒤(rowsTyped — 글자로 연 칸은 처음부터)는 그 글로 거른다. 글자로 열지 않은 목록 칸은 글 전체를 골라 둔다 — 치면 갈아 쓴다(한글은
// 글자로 칸을 열지 못해 Enter · F2 · 두 번 누름으로 연다).
function rowsPick(S) {
  const R = S.rows
  const m = S.model
  if (!S.edit || !m) return (R.pick = null)
  const f = fmtOf(m, S.edit.c - m.keyCount)
  if (f.kind !== 'choice') return (R.pick = null)
  const P = R.pick
  if (P && P.edit === S.edit && P.src === f) return P
  const editor = S.dom.editor
  const fresh = !P || P.edit !== S.edit
  const all = (f.options || []).map((label) => ({ label: String(label), value: String(label) }))
  const query = fresh ? (S.edit.typed ? editor.value : null) : P.query
  const shown = listFilter(all, query)
  R.pick = { edit: S.edit, src: f, all, query, shown, on: listMatch(shown, editor.value) }
  if (fresh && !S.edit.typed && all.length) editor.setSelectionRange(0, editor.value.length)
  return R.pick
}

// 칸 편집기에 친 글(input · compositionend) — 그 글로 거르고 강조는 같은 항목만.
function rowsTyped(S) {
  const P = S.rows.pick
  if (!S.edit || !P || P.edit !== S.edit) return
  P.query = S.dom.editor.value
  P.shown = listFilter(P.all, P.query)
  P.on = listMatch(P.shown, P.query)
  rowsChoices(S)
}

// 고르기 칸을 고치는 동안 칸 아래에 항목 목록(높이 상한 안에서 굴림) — 누르면 그 항목으로 확정, 칸 편집기의 ↑ ↓ 가 강조를 옮긴다.
// 목록은 거른 결과가 바뀐 때만 다시 짓고, 강조가 바뀐 때만 강조를 보이는 자리로 굴린다(그 밖의 그리기 · 굴림은 자리만 고친다 — 굴림
// 막대를 끄는 중에 되돌리지 않게).
function rowsChoices(S) {
  const R = S.rows
  const m = S.model
  const list = R.list
  const f = S.edit && m ? fmtOf(m, S.edit.c - m.keyCount) : null
  S.dom.editor.classList.toggle('is-text', Boolean(f && KINDS[f.kind]))
  const P = rowsPick(S)
  if (!P || !P.shown.length) {
    if (!list.hidden) {
      list.hidden = true
      list.textContent = ''
    }
    R.drawn = null
    return
  }
  list.hidden = false
  if (R.drawn !== P.shown) {
    list.textContent = ''
    P.shown.forEach((item, k) => {
      const node = egEl('div', 'eg-choice', item.label)
      node.setAttribute('role', 'option')
      node.dataset.at = String(k)
      list.appendChild(node)
    })
    list.scrollTop = 0
    R.drawn = P.shown
    R.drawnOn = null
  }
  if (R.drawnOn !== P.on) {
    R.drawnOn = P.on
    for (let k = 0; k < list.children.length; k += 1) {
      list.children[k].classList.toggle('is-on', k === P.on)
      list.children[k].setAttribute('aria-selected', k === P.on ? 'true' : 'false')
    }
    const node = list.children[P.on]
    if (node) {
      const h = node.offsetHeight || S.rowH
      const top = typeof node.offsetTop === 'number' ? node.offsetTop : P.on * h
      if (top < list.scrollTop) list.scrollTop = top
      else if (top + h > list.scrollTop + list.clientHeight) list.scrollTop = top + h - list.clientHeight
    }
  }
  list.style.left = S.lefts[S.edit.c] + 'px'
  list.style.minWidth = S.widths[S.edit.c] + 'px'
  // 칸 아래가 보이는 창 밖이면 칸 위로 — 아래 줄을 고칠 때 목록이 표 끝에 잘리지 않게.
  const scroller = S.dom.scroller
  const height = list.offsetHeight || P.shown.length * S.rowH
  const below = S.headH + (S.edit.r + 1) * S.rowH
  const above = S.headH + S.edit.r * S.rowH - height
  const room = scroller.scrollTop + scroller.clientHeight
  list.style.top = (below + height > room && above >= scroller.scrollTop + S.headH ? above : below) + 'px'
}

// 목록이 선 칸 편집기의 키 — ↑ ↓ 는 거른 목록 안에서 강조를 옮기고(끝에서 돌아감, 강조가 없으면 ↓ 첫 · ↑ 끝), Enter · Tab 은
// 강조한 항목을 넣은 뒤 core 의 확정 · 옮김으로 넘긴다(강조가 없으면 친 글 그대로). 칸을 떠나는 blur 는 친 글 그대로다(core).
function rowsKey(S, event) {
  const P = S.edit ? S.rows.pick : null
  if (!P || P.edit !== S.edit || !P.shown.length) return false
  const key = event.key
  if (key === 'ArrowDown' || key === 'ArrowUp') {
    event.preventDefault()
    const n = P.shown.length
    const step = key === 'ArrowDown' ? 1 : n - 1
    P.on = P.on < 0 ? (step === 1 ? 0 : n - 1) : (P.on + step) % n
    rowsChoices(S)
    return true
  }
  if ((key === 'Enter' || key === 'Tab') && P.on >= 0) S.dom.editor.value = P.shown[P.on].value
  return false
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
  name: 'rows', init: rowsInit, keydown: rowsKey, paintCell: rowsPaintCell,
  paintOverlay: (S) => {
    rowsSync(S)
    rowsChoices(S)
  },
  onFeed: rowsSync, onSelect: rowsSync, pasteGuard: rowsPasteGuard, cleanup: rowsCleanup,
})
