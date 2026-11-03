// 조회기간 팝업의 달 고르기 — 연도 넘김 · 열두 달 격자 · 빠른 선택 · 「적용」.
//
// 격자에서 시작 달 → 끝 달을 차례로 누르면 범위가 띠로 칠해진다(먼저 누른 달이 늦으면 둘을 바꿔 잇는다 — 같은
// 달을 두 번 누르면 그 한 달). 고르는 동안의 값은 초안이라 서버에 가지 않는다. 「적용」 은 초안 범위를 트리거
// (`apply`) 하나로 보낸다 — 값과 누름이 한 회차에 가므로 고친 직후 눌러도 그 값이다. 초안이 지금 기간과 같거나 끝
// 달을 아직 고르지 않았으면 「적용」 은 잠긴다(설명 글 대신 단추 상태와 아래 「지금 …」 줄이 말한다).
// 고를 수 없는 달(`minMonth`·`maxMonth` 밖)은 흐리게 잠그고, 그 밖의 해로는 넘기지 않는다.
//
// 키보드: 격자는 한 칸만 Tab 자리다(나머지는 -1). ←→ 한 달 · ↑↓ 한 분기(세 달) · PageUp/PageDown 한 해 ·
// Home/End 그 해 1월/12월, Enter · Space 가 누름이다(단추의 기본 누름). 해를 넘는 이동은 격자의 해도 넘긴다.
// 범위를 고른 그 자리(띠의 시작 · 끝 칸, 또는 그 범위를 놓은 빠른 선택 칩)에서 Enter 를 한 번 더 누르면 「적용」
// 이다(`enterApplies` — 적용할 수 있을 때만). Space 는 그대로 누름이라 그 달에서 새 범위를 시작한다.
//
// 컴포넌트 요소는 회차에 바뀌지 않으므로(실측) 회차를 넘는 초안은 뿌리 요소에 단다. 서버가 보낸 지금 기간 ·
// 고를 수 있는 범위가 바뀐 회차에만 초안을 그 값으로 다시 세운다.

// <month-range-core>
const MONTH_PATTERN = /^([0-9]{4})-(0[1-9]|1[0-2])$/
const GRID_COLUMNS = 3

function monthIndex(text) {
  const found = MONTH_PATTERN.exec(String(text ?? ''))
  return found ? Number(found[1]) * 12 + Number(found[2]) - 1 : null
}

function monthText(index) {
  const year = Math.floor(index / 12)
  const month = index - year * 12 + 1
  return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0')
}

function shortMonth(text) {
  const index = monthIndex(text)
  if (index === null) return ''
  const year = Math.floor(index / 12)
  return String(year % 100).padStart(2, '0') + '.' + String(index - year * 12 + 1).padStart(2, '0')
}

function yearOf(text) {
  const index = monthIndex(text)
  return index === null ? null : Math.floor(index / 12)
}

function monthSpan(start, end) {
  const from = monthIndex(start)
  const to = monthIndex(end)
  return from === null || to === null || from > to ? 0 : to - from + 1
}

function within(text, minMonth, maxMonth) {
  const index = monthIndex(text)
  return index !== null && index >= monthIndex(minMonth) && index <= monthIndex(maxMonth)
}

// 누름 하나. 끝을 기다리지 않으면 그 달에서 새로 시작하고(그 한 달 범위 + 기다림), 기다리면 먼저 누른 달과 이어
// 범위를 닫는다.
function pickMonth(draft, month) {
  if (!draft.anchor) return { start: month, end: month, anchor: month }
  return monthIndex(draft.anchor) <= monthIndex(month)
    ? { start: draft.anchor, end: month, anchor: null }
    : { start: month, end: draft.anchor, anchor: null }
}

// 칠할 범위 — 끝을 기다리는 동안은 먼저 누른 달과 지금 가리킨 달 사이(미리 보기)다.
function shownRange(draft, pointed) {
  if (draft.anchor && pointed) {
    const forward = monthIndex(draft.anchor) <= monthIndex(pointed)
    return {
      start: forward ? draft.anchor : pointed,
      end: forward ? pointed : draft.anchor,
      preview: true,
    }
  }
  return { start: draft.start, end: draft.end, preview: Boolean(draft.anchor) }
}

// 빠른 선택. `this` — 이번 달부터, `last` — 지난달부터 `length` 개월, `all` — 고를 수 있는 범위 전부. 범위 끝에
// 걸리면 그 끝에서 자르고(개월 수는 아래 줄이 말한다), 남는 달이 없으면 null(단추가 잠긴다).
function quickRange(kind, length, thisMonth, minMonth, maxMonth) {
  const low = monthIndex(minMonth)
  const high = monthIndex(maxMonth)
  if (low === null || high === null || low > high) return null
  if (kind === 'all') return { start: minMonth, end: maxMonth }
  const now = monthIndex(thisMonth)
  const count = Number(length)
  if (now === null || !Number.isInteger(count) || count < 1) return null
  const first = kind === 'last' ? now - 1 : now
  const start = Math.max(first, low)
  const end = Math.min(first + count - 1, high)
  return start > end ? null : { start: monthText(start), end: monthText(end) }
}

// 방향키 한 번의 새 달. 다루지 않는 키는 null, 범위 끝에서는 그 끝에 멈춘다.
function stepMonth(month, key, minMonth, maxMonth) {
  const index = monthIndex(month)
  if (index === null) return null
  const year = Math.floor(index / 12)
  const moves = {
    ArrowLeft: index - 1,
    ArrowRight: index + 1,
    ArrowUp: index - GRID_COLUMNS,
    ArrowDown: index + GRID_COLUMNS,
    PageUp: index - 12,
    PageDown: index + 12,
    Home: year * 12,
    End: year * 12 + 11,
  }
  if (!(key in moves)) return null
  const low = monthIndex(minMonth)
  const high = monthIndex(maxMonth)
  return monthText(Math.min(Math.max(moves[key], low), high))
}

// 「적용」 의 상태 — `pending`(끝 달을 기다림) · `invalid`(고를 수 없는 달) · `same`(지금 기간 그대로) · `ready`.
function applyState(draft, applied, minMonth, maxMonth) {
  if (draft.anchor) return 'pending'
  if (
    !within(draft.start, minMonth, maxMonth) ||
    !within(draft.end, minMonth, maxMonth) ||
    monthIndex(draft.start) > monthIndex(draft.end)
  ) {
    return 'invalid'
  }
  if (draft.start === applied.start && draft.end === applied.end) return 'same'
  return 'ready'
}

// 키보드 Enter 가 「적용」 인가 — 초안이 적용할 수 있는 범위(`ready`)이고 초점이 그 범위를 고른 자리일 때다.
// `target` 은 격자 칸이면 `{ month }`(띠의 시작 · 끝 칸 — 거꾸로 고르면 닫은 칸이 시작이다), 빠른 선택 칩이면
// `{ range }`(그 칩이 놓는 범위 — 초안과 같아야 한다). 그 밖의 칸에서 Enter 는 늘 누름이다.
function enterApplies(draft, applied, target, minMonth, maxMonth) {
  if (applyState(draft, applied, minMonth, maxMonth) !== 'ready') return false
  if (target && target.month) return target.month === draft.start || target.month === draft.end
  const range = target ? target.range : null
  return Boolean(range) && range.start === draft.start && range.end === draft.end
}

// 해 넘김 단추가 설 수 있는가 — 그 해에 고를 수 있는 달이 하나라도 있어야 한다.
function yearHasMonths(year, minMonth, maxMonth) {
  return year * 12 + 11 >= monthIndex(minMonth) && year * 12 <= monthIndex(maxMonth)
}
// </month-range-core>

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector('.capa-month-root')
  if (!root) return
  const yearLabel = root.querySelector('.capa-month-year')
  const steps = Array.from(root.querySelectorAll('.capa-month-step'))
  const cells = Array.from(root.querySelectorAll('.capa-month-cell'))
  const chips = Array.from(root.querySelectorAll('.capa-month-chip'))
  const draftRange = root.querySelector('.capa-month-draft-range')
  const draftNow = root.querySelector('.capa-month-draft-now')
  const apply = root.querySelector('.capa-month-apply')
  if (!yearLabel || cells.length !== 12 || !draftRange || !draftNow || !apply) return

  const minMonth = String(data?.minMonth || '')
  const maxMonth = String(data?.maxMonth || '')
  if (monthIndex(minMonth) === null || monthIndex(maxMonth) === null) return
  const applied = {
    start: String(data?.start || minMonth),
    end: String(data?.end || maxMonth),
  }
  const thisMonth = String(data?.thisMonth || '')

  const state = root.__capaMonth || (root.__capaMonth = { seen: '' })
  const signature = [applied.start, applied.end, minMonth, maxMonth].join('|')
  if (state.seen !== signature) {
    state.seen = signature
    state.draft = { start: applied.start, end: applied.end, anchor: null }
    state.view = yearOf(applied.start) ?? yearOf(minMonth)
    state.focus = applied.start
    state.pointed = null
  }

  const cellMonth = (cell) => monthText(state.view * 12 + Number(cell.dataset.month) - 1)

  const render = () => {
    yearLabel.textContent = state.view + '년'
    steps.forEach((step) => {
      step.disabled = !yearHasMonths(state.view + Number(step.dataset.step), minMonth, maxMonth)
    })
    const shown = shownRange(state.draft, state.pointed)
    const low = monthIndex(shown.start)
    const high = monthIndex(shown.end)
    // 격자의 Tab 자리 — 초점 달이 이 해에 없으면 이 해의 고를 수 있는 첫 달.
    let tabMonth = yearOf(state.focus) === state.view ? state.focus : null
    for (const cell of cells) {
      const month = cellMonth(cell)
      const index = monthIndex(month)
      const open = within(month, minMonth, maxMonth)
      if (!tabMonth && open) tabMonth = month
      cell.disabled = !open
      cell.classList.toggle('is-band', index >= low && index <= high)
      cell.classList.toggle('is-preview', shown.preview && index >= low && index <= high)
      cell.classList.toggle('is-start', index === low)
      cell.classList.toggle('is-end', index === high)
      cell.classList.toggle('is-now', month === thisMonth)
      cell.setAttribute('aria-label', state.view + '년 ' + cell.dataset.month + '월')
      cell.setAttribute('aria-pressed', String(index === low || index === high))
    }
    for (const cell of cells) cell.tabIndex = cellMonth(cell) === tabMonth ? 0 : -1
    const waiting = Boolean(state.draft.anchor)
    for (const chip of chips) {
      const range = quickRange(chip.dataset.quick, chip.dataset.length, thisMonth, minMonth, maxMonth)
      chip.disabled = range === null
      chip.setAttribute(
        'aria-pressed',
        String(!waiting && !!range && range.start === state.draft.start && range.end === state.draft.end)
      )
    }
    const status = applyState(state.draft, applied, minMonth, maxMonth)
    draftRange.replaceChildren()
    if (waiting) {
      draftRange.append(shortMonth(state.draft.anchor) + ' → ')
      const wait = document.createElement('span')
      wait.className = 'capa-month-draft-wait'
      wait.textContent = '끝 달'
      draftRange.append(wait)
    } else {
      draftRange.append(shortMonth(state.draft.start) + ' → ' + shortMonth(state.draft.end))
      const count = document.createElement('span')
      count.className = 'capa-month-draft-count'
      count.textContent = monthSpan(state.draft.start, state.draft.end) + '개월'
      draftRange.append(count)
    }
    draftNow.textContent =
      status === 'same' ? '' : '지금 ' + shortMonth(applied.start) + ' → ' + shortMonth(applied.end)
    apply.disabled = status !== 'ready'
    root.dataset.state = status
  }

  const focusMonth = (month) => {
    state.focus = month
    const year = yearOf(month)
    if (year !== null && year !== state.view) state.view = year
    if (state.draft.anchor) state.pointed = month
    render()
    const target = cells.find((cell) => cellMonth(cell) === month)
    if (target && !target.disabled) target.focus()
  }

  const pick = (month) => {
    state.draft = pickMonth(state.draft, month)
    state.focus = month
    state.pointed = null
    render()
  }

  root.onclick = (event) => {
    const step = event.target.closest('.capa-month-step')
    if (step && !step.disabled) {
      state.view += Number(step.dataset.step)
      render()
      return
    }
    const cell = event.target.closest('.capa-month-cell')
    if (cell && !cell.disabled) {
      pick(cellMonth(cell))
      return
    }
    const chip = event.target.closest('.capa-month-chip')
    if (chip && !chip.disabled) {
      const range = quickRange(chip.dataset.quick, chip.dataset.length, thisMonth, minMonth, maxMonth)
      if (!range) return
      state.draft = { start: range.start, end: range.end, anchor: null }
      state.view = yearOf(range.start)
      state.focus = range.start
      state.pointed = null
      render()
      return
    }
    if (event.target.closest('.capa-month-apply')) applyDraft()
  }

  const applyDraft = () => {
    if (applyState(state.draft, applied, minMonth, maxMonth) !== 'ready') return
    setTriggerValue('apply', { start: state.draft.start, end: state.draft.end })
  }

  root.onkeydown = (event) => {
    const cell = event.target.closest('.capa-month-cell')
    const chip = event.target.closest('.capa-month-chip')
    if (event.key === 'Enter' && !event.repeat && !event.isComposing && (cell || chip)) {
      const target = cell
        ? { month: cellMonth(cell) }
        : { range: quickRange(chip.dataset.quick, chip.dataset.length, thisMonth, minMonth, maxMonth) }
      if (enterApplies(state.draft, applied, target, minMonth, maxMonth)) {
        // 고른 자리에서 한 번 더 누른 Enter — 단추의 기본 누름(그 달에서 새 범위 시작)을 막고 적용한다.
        event.preventDefault()
        applyDraft()
        return
      }
    }
    if (!cell) return
    // Enter · Space 는 단추의 기본 누름(click)이 맡는다 — 여기서 또 고르면 한 번에 두 번 누른다.
    const next = stepMonth(cellMonth(cell), event.key, minMonth, maxMonth)
    if (next === null) return
    event.preventDefault()
    focusMonth(next)
  }

  // 끝 달을 기다리는 동안 가리킨 달까지 미리 칠한다(마우스 · 키보드 초점).
  root.onpointerover = (event) => {
    if (!state.draft.anchor) return
    const cell = event.target.closest('.capa-month-cell')
    const month = cell && !cell.disabled ? cellMonth(cell) : null
    if (month && month !== state.pointed) {
      state.pointed = month
      render()
    }
  }
  root.onpointerleave = () => {
    if (state.pointed && state.draft.anchor) {
      state.pointed = null
      render()
    }
  }
  root.onfocusin = (event) => {
    const cell = event.target.closest('.capa-month-cell')
    if (!cell || cell.disabled) return
    state.focus = cellMonth(cell)
    if (state.draft.anchor && state.pointed !== state.focus) {
      state.pointed = state.focus
      render()
    }
  }

  render()
}
