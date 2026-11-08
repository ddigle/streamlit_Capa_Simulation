// 공용 공정 팝업의 고르기 판 — 찾기 · 「적용」 · 「전체」 · 공정 타일.
//
// 여러 개 고름(`multi`)은 타일을 누를 때마다 초안에서 켜고 끈다. 초안은 서버에 가지 않는다(브라우저 안 —
// 누를 때마다 앱이 돌지 않는다). 「적용」 이 초안을 트리거(`apply`) 하나로 보낸다 — 초안이 지금 값과 같으면
// 잠긴다(설명 글 대신 단추 상태가 말한다). 「전체」 는 같은 트리거에 `clear` 를 실어 공용 값을 지우고, 지울 값이
// 없으면 잠긴다. 하나 고름(`single`)은 다른 타일을 누르면 곧바로 그 공정을 보낸다(`apply` — 값 하나). 트리거는
// `apply` 하나뿐이다 — 결과 객체가 dict 라 `clear` 같은 이름은 메서드와 겹친다.
//
// 키보드: Tab 차례는 찾기 → 「적용」 → 「전체」 → 타일 판(판은 한 자리 — 나머지 타일은 -1). 판 안에서
// ←→↑↓ · Home/End 로 옮기고 Enter · Space 가 누름이다(단추의 기본 누름). 누른 뒤에도 초점은 그 타일에 남는다
// — 타일을 다시 만들지 않고 표지만 바꾼다. Ctrl(⌘)+Enter 는 어디서나 「적용」 이다. 찾기 칸의 Enter · ↓ 는
// 보이는 첫 타일로 간다. 찾기 칸에 글이 있을 때 Esc 는 글만 지운다(팝업은 그대로).
//
// 컴포넌트 요소는 회차에 바뀌지 않으므로 회차를 넘는 초안은 뿌리 요소에 단다. 서버가 보낸 선택지 · 지금
// 값이 바뀐 회차에만 초안과 타일을 다시 세운다.

// <process-picker-core>
function normalizeText(text) {
  return String(text ?? '')
    .normalize('NFC')
    .trim()
    .toLowerCase()
}

// 찾는 글이 보이는 글자나 원본 이름에 들면 보인다. 빈 찾기는 모두 보인다.
function matchesNeedle(option, needle) {
  const want = normalizeText(needle)
  if (!want) return true
  return normalizeText(option.label).includes(want) || normalizeText(option.value).includes(want)
}

// 누른 공정을 초안에서 켜고 끈다. 돌려주는 차례는 선택지 차례다.
function toggleDraft(draft, value, order) {
  const held = new Set(draft)
  if (held.has(value)) held.delete(value)
  else held.add(value)
  return order.filter((item) => held.has(item))
}

function sameSelection(left, right) {
  if (left.length !== right.length) return false
  const held = new Set(left)
  return right.every((item) => held.has(item))
}

// 머리 값 — 여러 개 고름은 「선택 n / N」, 하나 고름은 「N개 공정」.
function countLabel(mode, draftCount, total) {
  return mode === 'multi' ? '선택 ' + draftCount + ' / ' + total : total + '개 공정'
}

// 「적용」 상태 — 하나 고름에는 「적용」 이 없다(`none`). 초안이 지금 값 그대로면 `same`.
function applyState(mode, draft, applied) {
  if (mode !== 'multi') return 'none'
  return sameSelection(draft, applied) ? 'same' : 'ready'
}

// 방향키 한 번의 새 자리(보이는 타일 안 순번). `perRow` 는 화면에서 잰 한 줄 타일 수다. 다루지 않는 키는
// null, 끝에서는 그 끝에 멈춘다.
function stepIndex(index, key, count, perRow) {
  if (count <= 0) return null
  const row = Math.max(1, perRow)
  const moves = {
    ArrowLeft: index - 1,
    ArrowRight: index + 1,
    ArrowUp: index - row,
    ArrowDown: index + row,
    Home: 0,
    End: count - 1,
  }
  if (!(key in moves)) return null
  return Math.min(Math.max(moves[key], 0), count - 1)
}

// 받은 선택지를 다듬는다 — 값이 빈 것 · 겹친 것을 빼고 글자가 없으면 값 그대로.
function cleanOptions(raw) {
  const seen = new Set()
  const options = []
  for (const item of Array.isArray(raw) ? raw : []) {
    const value = String(item?.value ?? '')
    if (!value || seen.has(value)) continue
    seen.add(value)
    options.push({ value, label: String(item?.label ?? '') || value })
  }
  return options
}
// </process-picker-core>

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector('.capa-proc-root')
  if (!root) return
  const count = root.querySelector('.capa-proc-count')
  const search = root.querySelector('.capa-proc-search')
  const actions = root.querySelector('.capa-proc-actions')
  const apply = root.querySelector('.capa-proc-apply')
  const clearAll = root.querySelector('.capa-proc-all')
  const grid = root.querySelector('.capa-proc-grid')
  const empty = root.querySelector('.capa-proc-empty')
  if (!count || !search || !actions || !apply || !clearAll || !grid || !empty) return

  const mode = data?.mode === 'single' ? 'single' : 'multi'
  const options = cleanOptions(data?.options)
  const order = options.map((option) => option.value)
  const valid = new Set(order)
  const applied = (Array.isArray(data?.selected) ? data.selected : [])
    .map((value) => String(value))
    .filter((value) => valid.has(value))
  const hasShared = Boolean(data?.hasShared)

  const state = root.__capaProc || (root.__capaProc = { seen: '', focused: false })
  const signature = JSON.stringify([mode, options, applied, hasShared])
  if (state.seen !== signature) {
    state.seen = signature
    state.draft = applied.slice()
    state.needle = ''
    state.focus = applied.length ? Math.max(order.indexOf(applied[0]), 0) : 0
    search.value = ''
    grid.replaceChildren()
    grid.setAttribute('aria-multiselectable', String(mode === 'multi'))
    options.forEach((option, index) => {
      const tile = document.createElement('button')
      tile.type = 'button'
      tile.className = 'capa-proc-tile'
      tile.setAttribute('role', 'option')
      tile.dataset.index = String(index)
      tile.title = option.label === option.value ? option.label : option.label + '\n원본 공정: ' + option.value
      const mark = document.createElement('span')
      mark.className = 'capa-proc-mark'
      mark.setAttribute('aria-hidden', 'true')
      const name = document.createElement('span')
      name.className = 'capa-proc-name'
      name.textContent = option.label
      tile.append(mark, name)
      grid.append(tile)
    })
  }
  const tiles = Array.from(grid.querySelectorAll('.capa-proc-tile'))
  const shownTiles = () => tiles.filter((tile) => !tile.hidden)
  const tileIndex = (tile) => Number(tile.dataset.index)

  const render = () => {
    const held = new Set(state.draft)
    for (const tile of tiles) {
      const option = options[tileIndex(tile)]
      const on = held.has(option.value)
      tile.hidden = !matchesNeedle(option, state.needle)
      tile.setAttribute('aria-selected', String(on))
      const mark = tile.querySelector('.capa-proc-mark')
      if (mark) mark.textContent = on ? 'check' : 'remove'
    }
    const shown = shownTiles()
    let tabTile = tiles[state.focus]
    if (!tabTile || tabTile.hidden) tabTile = shown[0]
    for (const tile of tiles) tile.tabIndex = tile === tabTile ? 0 : -1
    empty.hidden = shown.length > 0
    count.textContent = countLabel(mode, state.draft.length, options.length)
    actions.hidden = mode !== 'multi'
    const status = applyState(mode, state.draft, applied)
    apply.disabled = status !== 'ready'
    clearAll.disabled = !hasShared
    root.dataset.state = status
  }

  const focusTile = (tile) => {
    if (!tile) return
    state.focus = tileIndex(tile)
    render()
    tile.focus()
  }

  const applyDraft = () => {
    if (applyState(mode, state.draft, applied) !== 'ready') return
    setTriggerValue('apply', { values: state.draft.slice() })
  }

  const press = (tile) => {
    const option = options[tileIndex(tile)]
    if (!option) return
    if (mode === 'single') {
      // 지금 공정을 다시 누르면 바뀌는 것이 없다 — 보내지 않는다(닫기는 X · Esc).
      if (applied[0] !== option.value) setTriggerValue('apply', { values: [option.value] })
      return
    }
    state.draft = toggleDraft(state.draft, option.value, order)
    focusTile(tile)
  }

  root.onclick = (event) => {
    const tile = event.target.closest('.capa-proc-tile')
    if (tile) {
      press(tile)
      return
    }
    if (event.target.closest('.capa-proc-apply')) {
      applyDraft()
      return
    }
    if (event.target.closest('.capa-proc-all') && hasShared) setTriggerValue('apply', { clear: true })
  }

  root.oninput = (event) => {
    if (event.target !== search) return
    state.needle = search.value
    render()
  }

  // 한 줄 타일 수 — 보이는 첫 타일과 윗선이 같은 타일 수.
  const perRow = (shown) => {
    if (!shown.length) return 1
    const top = shown[0].offsetTop
    const row = shown.filter((tile) => tile.offsetTop === top).length
    return Math.max(row, 1)
  }

  root.onkeydown = (event) => {
    if (event.isComposing) return
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      applyDraft()
      return
    }
    if (event.target === search) {
      if (event.key === 'Escape' && search.value) {
        event.preventDefault()
        event.stopPropagation()
        search.value = ''
        state.needle = ''
        render()
        return
      }
      if (event.key === 'Enter' || event.key === 'ArrowDown') {
        event.preventDefault()
        focusTile(shownTiles()[0])
      }
      return
    }
    const tile = event.target.closest('.capa-proc-tile')
    if (!tile) return
    // Enter · Space 는 단추의 기본 누름(click)이 맡는다 — 여기서 또 누르면 한 번에 두 번 누른다.
    const shown = shownTiles()
    const next = stepIndex(shown.indexOf(tile), event.key, shown.length, perRow(shown))
    if (next === null) return
    event.preventDefault()
    focusTile(shown[next])
  }

  root.onfocusin = (event) => {
    const tile = event.target.closest('.capa-proc-tile')
    if (tile) state.focus = tileIndex(tile)
  }

  render()
  // 팝업을 연 첫 그림에서 찾기 칸에 초점 — 치면 좁혀지고, Tab 이 「적용」 · 판으로 간다.
  if (!state.focused) {
    state.focused = true
    requestAnimationFrame(() => search.focus())
  }
}
