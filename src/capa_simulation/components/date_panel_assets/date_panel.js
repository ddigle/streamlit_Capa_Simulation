// 날짜 칸과 기간 판 — 값 칸 · 달 넘김 · 일 격자 · 빠른 선택 · 「적용」(사이드바 조회기간 판과 같은 꼴).
//
// 값 칸을 누르면 판이 뜬다. 여닫기와 고르기는 브라우저 안에서 끝나 서버에 아무것도 보내지 않는다(회차 0) — 「적용」 만
// 트리거(`apply`) 하나로 초안을 보낸다. 범위(`range`)는 시작 날 → 끝 날 두 번 누름이 띠를 칠하고(먼저 누른 날이 늦으면
// 둘을 바꿔 잇는다 — 같은 날 두 번은 그 하루), 한 날(`single`)은 한 번 누름이 그 날이다. 초안이 지금 값과 같거나 끝
// 날을 아직 고르지 않았으면 「적용」 은 잠긴다. 고를 수 없는 날(`minDay` · `maxDay` 밖)은 흐리게 잠기고, 고를 날이
// 없는 달로는 넘기지 않는다. 닫으면(✕ · Esc · 판 밖 누름) 초안은 버린다.
//
// 키보드: 격자는 한 칸만 Tab 자리다. ←→ 하루 · ↑↓ 한 주 · PageUp/PageDown 한 달 · Shift+PageUp/PageDown 한 해 ·
// Home/End 그 달 첫날/끝날, Enter · Space 가 누름이다(단추의 기본 누름). 고른 그 자리(띠의 시작 · 끝 칸, 또는 그
// 값을 놓은 빠른 선택 칩)에서 Enter 를 한 번 더 누르면 「적용」 이다(`enterApplies` — 조회기간 판과 같다).
//
// 컴포넌트 요소는 회차에 바뀌지 않으므로 회차를 넘는 초안은 뿌리 요소에 단다. 서버가 보낸 지금 값 · 고를 수 있는
// 범위가 바뀐 회차에만 초안을 그 값으로 다시 세운다.

// <date-panel-core>
const DAY_PATTERN = /^([0-9]{4})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$/
const DAY_MS = 86400000
const WEEK_DAYS = 7
const MONTH_CELLS = 42

function dayIndex(text) {
  const found = DAY_PATTERN.exec(String(text ?? ''))
  if (!found) return null
  const month = Number(found[2]) - 1
  const day = Number(found[3])
  const stamp = new Date(0)
  stamp.setUTCFullYear(Number(found[1]), month, day)
  if (stamp.getUTCMonth() !== month || stamp.getUTCDate() !== day) return null
  return Math.round(stamp.getTime() / DAY_MS)
}

function dayText(index) {
  const stamp = new Date(index * DAY_MS)
  return (
    String(stamp.getUTCFullYear()).padStart(4, '0') +
    '-' +
    String(stamp.getUTCMonth() + 1).padStart(2, '0') +
    '-' +
    String(stamp.getUTCDate()).padStart(2, '0')
  )
}

function shortDay(text) {
  if (dayIndex(text) === null) return ''
  return text.slice(2, 4) + '.' + text.slice(5, 7) + '.' + text.slice(8, 10)
}

function daySpan(start, end) {
  const from = dayIndex(start)
  const to = dayIndex(end)
  return from === null || to === null || from > to ? 0 : to - from + 1
}

function within(text, minDay, maxDay) {
  const index = dayIndex(text)
  return index !== null && index >= dayIndex(minDay) && index <= dayIndex(maxDay)
}

// 달 번호 — 해 × 12 + 달(0 ~ 11). 판이 보는 달은 이 번호 하나다.
function viewOf(text) {
  if (dayIndex(text) === null) return null
  return Number(text.slice(0, 4)) * 12 + Number(text.slice(5, 7)) - 1
}

function viewFirstDay(view) {
  const year = Math.floor(view / 12)
  const month = view - year * 12 + 1
  return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0') + '-01'
}

function viewLastIndex(view) {
  return dayIndex(viewFirstDay(view + 1)) - 1
}

function viewLabel(view) {
  const year = Math.floor(view / 12)
  return year + '년 ' + (view - year * 12 + 1) + '월'
}

// 한 달의 격자 — 일요일에 시작하는 여섯 줄 일곱 칸(늘 42칸). 그 달 밖 칸은 null 이다.
function monthCells(view) {
  const first = dayIndex(viewFirstDay(view))
  const last = viewLastIndex(view)
  // 1970-01-01 이 목요일이다(일요일 0 기준 4).
  const lead = (((first + 4) % WEEK_DAYS) + WEEK_DAYS) % WEEK_DAYS
  const cells = []
  for (let slot = 0; slot < MONTH_CELLS; slot += 1) {
    const index = first + slot - lead
    cells.push(index < first || index > last ? null : dayText(index))
  }
  return cells
}

// 달 넘김 단추가 설 수 있는가 — 그 달에 고를 수 있는 날이 하루라도 있어야 한다.
function viewHasDays(view, minDay, maxDay) {
  return viewLastIndex(view) >= dayIndex(minDay) && dayIndex(viewFirstDay(view)) <= dayIndex(maxDay)
}

// 범위의 누름 하나. 끝을 기다리지 않으면 그 날에서 새로 시작하고, 기다리면 먼저 누른 날과 이어 닫는다.
function pickRange(draft, day) {
  if (!draft.anchor) return { start: day, end: day, anchor: day }
  return dayIndex(draft.anchor) <= dayIndex(day)
    ? { start: draft.anchor, end: day, anchor: null }
    : { start: day, end: draft.anchor, anchor: null }
}

function pickSingle(day) {
  return { start: day, end: day, anchor: null }
}

// 칠할 범위 — 끝을 기다리는 동안은 먼저 누른 날과 지금 가리킨 날 사이(미리 보기)다.
function shownRange(draft, pointed) {
  if (draft.anchor && pointed) {
    const forward = dayIndex(draft.anchor) <= dayIndex(pointed)
    return {
      start: forward ? draft.anchor : pointed,
      end: forward ? pointed : draft.anchor,
      preview: true,
    }
  }
  return { start: draft.start, end: draft.end, preview: Boolean(draft.anchor) }
}

// 범위의 빠른 선택. `ahead` — 오늘부터 n주, `back` — 오늘까지 n주, `month` — 이번 달, `all` — 고를 수 있는 범위 전부,
// `clear` — 비움. 범위 끝에 걸리면 그 끝에서 자르고(일수는 바닥 줄이 말한다), 남는 날이 없으면 null(단추가 잠긴다).
function quickRange(kind, length, today, minDay, maxDay) {
  if (kind === 'clear') return { start: null, end: null }
  const low = dayIndex(minDay)
  const high = dayIndex(maxDay)
  if (low === null || high === null || low > high) return null
  if (kind === 'all') return { start: minDay, end: maxDay }
  const now = dayIndex(today)
  if (now === null) return null
  let first = null
  let last = null
  if (kind === 'month') {
    const view = viewOf(today)
    first = dayIndex(viewFirstDay(view))
    last = viewLastIndex(view)
  } else {
    const count = Number(length)
    if (!Number.isInteger(count) || count < 1) return null
    first = kind === 'back' ? now - count * WEEK_DAYS + 1 : now
    last = kind === 'back' ? now : now + count * WEEK_DAYS - 1
  }
  const start = Math.max(first, low)
  const end = Math.min(last, high)
  return start > end ? null : { start: dayText(start), end: dayText(end) }
}

// 한 날의 빠른 선택. 고를 수 없는 날이면 null(단추가 잠긴다).
function quickDay(kind, today, minDay, maxDay) {
  if (kind === 'clear') return { start: null, end: null }
  const now = dayIndex(today)
  if (now === null) return null
  const view = viewOf(today)
  const index = {
    today: now,
    yesterday: now - 1,
    month_first: dayIndex(viewFirstDay(view)),
    next_month_first: dayIndex(viewFirstDay(view + 1)),
  }[kind]
  if (index === undefined) return null
  const day = dayText(index)
  return within(day, minDay, maxDay) ? { start: day, end: day } : null
}

// 방향키 한 번의 새 날. 다루지 않는 키는 null, 범위 끝에서는 그 끝에 멈춘다. 달 · 해 이동은 같은 날짜로 가고 그 달에
// 없는 날이면 그 달 끝날이다.
function stepDay(day, key, shift, minDay, maxDay) {
  const index = dayIndex(day)
  if (index === null) return null
  const view = viewOf(day)
  const shifted = (months) => {
    const target = view + months
    const wanted = dayIndex(viewFirstDay(target)) + Number(day.slice(8, 10)) - 1
    return Math.min(wanted, viewLastIndex(target))
  }
  const moves = {
    ArrowLeft: index - 1,
    ArrowRight: index + 1,
    ArrowUp: index - WEEK_DAYS,
    ArrowDown: index + WEEK_DAYS,
    PageUp: shifted(shift ? -12 : -1),
    PageDown: shifted(shift ? 12 : 1),
    Home: dayIndex(viewFirstDay(view)),
    End: viewLastIndex(view),
  }
  if (!(key in moves)) return null
  return dayText(Math.min(Math.max(moves[key], dayIndex(minDay)), dayIndex(maxDay)))
}

function isEmpty(range) {
  return range.start === null && range.end === null
}

// 「적용」 의 상태 — `pending`(끝 날을 기다림) · `invalid`(고를 수 없는 값) · `same`(지금 값 그대로) · `ready`.
function applyState(draft, applied, minDay, maxDay) {
  if (draft.anchor) return 'pending'
  if (!isEmpty(draft)) {
    if (
      !within(draft.start, minDay, maxDay) ||
      !within(draft.end, minDay, maxDay) ||
      dayIndex(draft.start) > dayIndex(draft.end)
    ) {
      return 'invalid'
    }
  }
  if (draft.start === applied.start && draft.end === applied.end) return 'same'
  return 'ready'
}

// 키보드 Enter 가 「적용」 인가 — 초안이 적용할 수 있고(`ready`) 초점이 그 값을 고른 자리일 때다. `target` 은 격자
// 칸이면 `{ day }`(띠의 시작 · 끝 칸), 빠른 선택 칩이면 `{ range }`(그 칩이 놓는 값 — 초안과 같아야 한다).
function enterApplies(draft, applied, target, minDay, maxDay) {
  if (applyState(draft, applied, minDay, maxDay) !== 'ready') return false
  if (target && target.day) return target.day === draft.start || target.day === draft.end
  const range = target ? target.range : null
  return Boolean(range) && range.start === draft.start && range.end === draft.end
}

// 값 칸 · 바닥 줄의 글 — 범위는 「26.11.02 → 27.03.31」, 한 날은 「26.11.02」, 비었으면 빈 글자.
function valueText(mode, start, end) {
  if (start === null && end === null) return ''
  if (mode === 'single') return shortDay(start)
  return (start ? shortDay(start) : '—') + ' → ' + (end ? shortDay(end) : '—')
}
// </date-panel-core>

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector('.capa-date-root')
  if (!root) return
  const label = root.querySelector('.capa-date-label')
  const helpButton = root.querySelector('.capa-date-help')
  const bubble = root.querySelector('.capa-date-bubble')
  const field = root.querySelector('.capa-date-field')
  const fieldText = root.querySelector('.capa-date-field-text')
  const dialog = root.querySelector('.capa-date-dialog')
  const titleText = root.querySelector('.capa-date-title-text')
  const yearLabel = root.querySelector('.capa-date-year')
  const steps = Array.from(root.querySelectorAll('.capa-date-step'))
  const grid = root.querySelector('.capa-date-days')
  const draftRange = root.querySelector('.capa-date-draft-range')
  const draftNow = root.querySelector('.capa-date-draft-now')
  const apply = root.querySelector('.capa-date-apply')
  if (!label || !field || !fieldText || !dialog || !grid || !yearLabel || !draftRange || !apply) return

  const mode = data?.mode === 'single' ? 'single' : 'range'
  const minDay = String(data?.minDay || '')
  const maxDay = String(data?.maxDay || '')
  if (dayIndex(minDay) === null || dayIndex(maxDay) === null) return
  const applied = { start: data?.start ?? null, end: data?.end ?? null }
  const today = String(data?.today || '')
  const emptyText = String(data?.emptyText || '')
  const clearable = Boolean(data?.clearable)
  const bounded = Boolean(data?.bounded)
  const name = String(data?.label || '')
  const help = String(data?.help || '')

  const homeDay = () => {
    const now = dayIndex(today)
    if (applied.start) return applied.start
    if (now === null) return minDay
    return dayText(Math.min(Math.max(now, dayIndex(minDay)), dayIndex(maxDay)))
  }

  const state = root.__capaDate || (root.__capaDate = { seen: '', sent: null })
  const resetDraft = () => {
    state.draft = { start: applied.start, end: applied.end, anchor: null }
    state.focus = homeDay()
    state.view = viewOf(state.focus)
    state.pointed = null
  }
  const signature = [mode, applied.start, applied.end, minDay, maxDay].join('|')
  if (state.seen !== signature) {
    state.seen = signature
    state.sent = null
    resetDraft()
  }

  if (!grid.children.length) {
    for (let slot = 0; slot < MONTH_CELLS; slot += 1) {
      const cell = document.createElement('button')
      cell.type = 'button'
      cell.className = 'capa-date-day'
      grid.append(cell)
    }
  }
  const cells = Array.from(grid.children)

  const quickGroups = Array.from(root.querySelectorAll('.capa-date-quick'))
  for (const group of quickGroups) group.hidden = group.dataset.mode !== mode
  const activeGroup = quickGroups.find((group) => group.dataset.mode === mode)
  const chips = activeGroup ? Array.from(activeGroup.querySelectorAll('.capa-date-chip')) : []
  for (const chip of chips) {
    // 이 칸에 아예 없는 기능만 숨긴다 — 끝이 없는 칸의 「전체」, 비울 수 없는 칸의 「비움」.
    chip.hidden =
      (chip.dataset.quick === 'all' && !bounded) || (chip.dataset.quick === 'clear' && !clearable)
  }
  const chipRange = (chip) =>
    mode === 'single'
      ? quickDay(chip.dataset.quick, today, minDay, maxDay)
      : quickRange(chip.dataset.quick, chip.dataset.length, today, minDay, maxDay)

  const renderField = () => {
    label.textContent = name
    titleText.textContent = name
    dialog.setAttribute('aria-label', name)
    const shown = state.sent || applied
    const text = valueText(mode, shown.start, shown.end)
    fieldText.textContent = text || emptyText
    field.classList.toggle('is-empty', !text)
    field.disabled = Boolean(data?.disabled)
    field.setAttribute('aria-label', name + ' ' + (text || emptyText))
    root.dataset.mode = mode
  }

  const render = () => {
    yearLabel.textContent = viewLabel(state.view)
    for (const step of steps) {
      step.disabled = !viewHasDays(state.view + Number(step.dataset.step), minDay, maxDay)
    }
    const shown = shownRange(state.draft, state.pointed)
    const low = dayIndex(shown.start)
    const high = dayIndex(shown.end)
    const hasBand = low !== null && high !== null
    const days = monthCells(state.view)
    let tabDay = viewOf(state.focus) === state.view && within(state.focus, minDay, maxDay) ? state.focus : null
    cells.forEach((cell, slot) => {
      const day = days[slot]
      const index = dayIndex(day)
      const open = day !== null && within(day, minDay, maxDay)
      if (!tabDay && open) tabDay = day
      cell.dataset.day = day || ''
      cell.textContent = day ? String(Number(day.slice(8, 10))) : ''
      cell.disabled = !open
      const inBand = hasBand && index !== null && index >= low && index <= high
      cell.classList.toggle('is-blank', day === null)
      cell.classList.toggle('is-band', inBand)
      cell.classList.toggle('is-preview', inBand && shown.preview)
      cell.classList.toggle('is-start', hasBand && index === low)
      cell.classList.toggle('is-end', hasBand && index === high)
      cell.classList.toggle('is-now', day !== null && day === today)
      if (day) {
        cell.setAttribute('aria-label', Number(day.slice(0, 4)) + '년 ' + Number(day.slice(5, 7)) + '월 ' + Number(day.slice(8, 10)) + '일')
        cell.setAttribute('aria-pressed', String(index === low || index === high))
      } else {
        cell.removeAttribute('aria-label')
        cell.removeAttribute('aria-pressed')
      }
    })
    for (const cell of cells) cell.tabIndex = cell.dataset.day && cell.dataset.day === tabDay ? 0 : -1
    const waiting = Boolean(state.draft.anchor)
    for (const chip of chips) {
      const range = chipRange(chip)
      chip.disabled = range === null
      chip.setAttribute(
        'aria-pressed',
        String(!waiting && !!range && range.start === state.draft.start && range.end === state.draft.end)
      )
    }
    const status = applyState(state.draft, applied, minDay, maxDay)
    draftRange.replaceChildren()
    if (waiting) {
      draftRange.append(shortDay(state.draft.anchor) + ' → ')
      const wait = document.createElement('span')
      wait.className = 'capa-date-draft-wait'
      wait.textContent = '끝 날'
      draftRange.append(wait)
    } else if (isEmpty(state.draft)) {
      draftRange.append(emptyText)
    } else {
      draftRange.append(valueText(mode, state.draft.start, state.draft.end))
      if (mode === 'range') {
        const count = document.createElement('span')
        count.className = 'capa-date-draft-count'
        count.textContent = daySpan(state.draft.start, state.draft.end) + '일'
        draftRange.append(count)
      }
    }
    draftNow.textContent =
      status === 'same' ? '' : '지금 ' + (valueText(mode, applied.start, applied.end) || emptyText)
    apply.disabled = status !== 'ready'
    root.dataset.state = status
  }

  const focusCell = (day) => {
    const target = cells.find((cell) => cell.dataset.day === day)
    if (target && !target.disabled) target.focus()
  }

  const open = () => {
    if (field.disabled || dialog.open) return
    state.sent = null
    resetDraft()
    render()
    renderField()
    const app = document.querySelector('.stApp')
    if (app) dialog.style.setProperty('--capa-date-sheet', getComputedStyle(app).backgroundColor)
    dialog.showModal()
    focusCell(state.focus)
  }

  const applyDraft = () => {
    if (applyState(state.draft, applied, minDay, maxDay) !== 'ready') return
    state.sent = { start: state.draft.start, end: state.draft.end }
    setTriggerValue('apply', state.sent)
    dialog.close()
    renderField()
  }

  const focusDay = (day) => {
    state.focus = day
    const view = viewOf(day)
    if (view !== null && view !== state.view) state.view = view
    if (state.draft.anchor) state.pointed = day
    render()
    focusCell(day)
  }

  const pick = (day) => {
    state.draft = mode === 'single' ? pickSingle(day) : pickRange(state.draft, day)
    state.focus = day
    state.pointed = null
    render()
  }

  root.onclick = (event) => {
    if (event.target === dialog) {
      // 판 밖(뒤 막) 누름 — 초안을 버리고 닫는다.
      dialog.close()
      return
    }
    if (event.target.closest('.capa-date-field')) {
      open()
      return
    }
    if (event.target.closest('.capa-date-close')) {
      dialog.close()
      return
    }
    const step = event.target.closest('.capa-date-step')
    if (step && !step.disabled) {
      state.view += Number(step.dataset.step)
      render()
      return
    }
    const cell = event.target.closest('.capa-date-day')
    if (cell && !cell.disabled && cell.dataset.day) {
      pick(cell.dataset.day)
      return
    }
    const chip = event.target.closest('.capa-date-chip')
    if (chip && !chip.disabled) {
      const range = chipRange(chip)
      if (!range) return
      state.draft = { start: range.start, end: range.end, anchor: null }
      if (range.start) {
        state.view = viewOf(range.start)
        state.focus = range.start
      }
      state.pointed = null
      render()
      return
    }
    if (event.target.closest('.capa-date-apply')) applyDraft()
  }

  root.onkeydown = (event) => {
    if (event.key === 'Escape' && dialog.open) {
      // 판만 닫는다 — 팝업(st.dialog) 안 칸이어도 그 팝업까지 닫히지 않게 위로 보내지 않는다.
      event.preventDefault()
      event.stopPropagation()
      dialog.close()
      return
    }
    const cell = event.target.closest('.capa-date-day')
    const chip = event.target.closest('.capa-date-chip')
    if (event.key === 'Enter' && !event.repeat && !event.isComposing && (cell || chip)) {
      const target = cell ? { day: cell.dataset.day } : { range: chipRange(chip) }
      if (enterApplies(state.draft, applied, target, minDay, maxDay)) {
        // 고른 자리에서 한 번 더 누른 Enter — 단추의 기본 누름(그 날에서 새 범위 시작)을 막고 적용한다.
        event.preventDefault()
        applyDraft()
        return
      }
    }
    if (!cell) return
    // Enter · Space 는 단추의 기본 누름(click)이 맡는다 — 여기서 또 고르면 한 번에 두 번 누른다.
    const next = stepDay(cell.dataset.day, event.key, event.shiftKey, minDay, maxDay)
    if (next === null) return
    event.preventDefault()
    focusDay(next)
  }

  // 끝 날을 기다리는 동안 가리킨 날까지 미리 칠한다(마우스 · 키보드 초점).
  grid.onpointerover = (event) => {
    if (!state.draft.anchor) return
    const cell = event.target.closest('.capa-date-day')
    const day = cell && !cell.disabled && cell.dataset.day ? cell.dataset.day : null
    if (day && day !== state.pointed) {
      state.pointed = day
      render()
    }
  }
  grid.onpointerleave = () => {
    if (state.pointed && state.draft.anchor) {
      state.pointed = null
      render()
    }
  }
  grid.onfocusin = (event) => {
    const cell = event.target.closest('.capa-date-day')
    if (!cell || cell.disabled || !cell.dataset.day) return
    state.focus = cell.dataset.day
    if (state.draft.anchor && state.pointed !== state.focus) {
      state.pointed = state.focus
      render()
    }
  }

  // 풍선 — 맨 위 층에 띄워 잘리지 않게 한다. popover 가 없는 브라우저는 title 로 물러난다.
  if (helpButton) {
    helpButton.hidden = !help
    helpButton.setAttribute('aria-label', help)
    const canFloat = Boolean(bubble && bubble.showPopover)
    if (bubble) bubble.textContent = help
    if (!canFloat) helpButton.title = help
    const hide = () => {
      if (canFloat && bubble.matches(':popover-open')) bubble.hidePopover()
    }
    const show = () => {
      if (!canFloat || !help || bubble.matches(':popover-open')) return
      bubble.showPopover()
      const anchor = helpButton.getBoundingClientRect()
      const box = bubble.getBoundingClientRect()
      const left = Math.min(Math.max(anchor.left, 8), window.innerWidth - box.width - 8)
      const above = anchor.top - box.height - 8
      bubble.style.position = 'fixed'
      bubble.style.left = left + 'px'
      bubble.style.top = (above >= 8 ? above : anchor.bottom + 8) + 'px'
    }
    helpButton.onpointerenter = show
    helpButton.onpointerleave = hide
    helpButton.onfocus = show
    helpButton.onblur = hide
  }

  renderField()
  render()
}
