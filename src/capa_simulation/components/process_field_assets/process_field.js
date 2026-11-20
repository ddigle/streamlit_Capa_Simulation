// 공용 공정 팝업의 고르기 판 — 찾기 · 「전체」 · 「적용」 · 공정 타일.
//
// 여러 개 고름(`multi`)은 타일을 누를 때마다 초안에서 켜고 끈다. 초안은 서버에 가지 않는다(브라우저 안 —
// 누를 때마다 앱이 돌지 않는다). 「적용」 이 초안을 트리거(`apply`) 하나로 보낸다 — 초안이 지금 값과 같으면
// 잠긴다(설명 글 대신 단추 상태가 말한다). 모두 켠 초안은 고르지 않은 것(이 화면 몫은 전체)과 같다 — 서버도
// 그렇게 적는다(`shared_process.apply_from_screen`). 「전체」 는 같은 트리거에 `clear` 를 실어 공용 값을
// 지우고, 지울 값이 없으면 잠긴다. 하나 고름(`single`)은 다른 타일을 누르면 곧바로 그 공정을
// 보낸다(`apply` — 값 하나). 트리거는 `apply` 하나뿐이다 — 결과 객체가 dict 라 `clear` 같은 이름은
// 메서드와 겹친다.
//
// 키보드: Tab 차례는 찾기 → 「전체」 → 「적용」 → 타일 판(판은 한 자리 — 나머지 타일은 -1). 「적용」 이 판
// 바로 앞이라 판에서 Shift+Tab 한 번이 「적용」 이다 — 공용 값을 지우는 「전체」 에 먼저 닿지 않는다. 판 안에서
// ←→↑↓ · Home/End 로 옮기고 Enter · Space 가 누름이다(단추의 기본 누름). 누른 뒤에도 초점은 그 타일에 남는다
// — 타일을 다시 만들지 않고 표지만 바꾼다. Ctrl(⌘)+Enter 는 어디서나 「적용」 이다. 찾기 칸의 Enter · ↓ 는
// 보이는 첫 타일로 간다. 찾기 칸에 글이 있을 때 Esc 는 글만 지운다(판을 둔 팝업 · 팝오버는 그대로) — 팝오버
// (`st.popover`)는 열린 동안 문서의 keydown 을 capture 단계에서 받아 닫으므로, 그보다 앞인 창의 capture
// 단계에서 받는다(`clearSearchOnEscape` — 창마다 한 번 단다). 찾기 칸에서 한글을 치는 중의 Esc 는 입력기가
// 조합을 끝내는 몫이라 지우지 않고 팝업 · 팝오버에도 보내지 않는다.
//
// 컴포넌트 요소는 회차에 바뀌지 않으므로 회차를 넘는 초안은 뿌리 요소에 단다. 서버가 보낸 선택지 · 지금
// 값이 바뀐 회차에만 초안과 타일을 다시 세운다.
//
// 판을 쓰는 다른 칸(필요 단축 일정 조건 카드 「공정」 — 팝오버 안)은 data 로 넷을 바꾼다. 넷 다 주지 않으면
// 공용 공정 팝업 그대로다.
// - `wholeIsAll: false` — 모두 켠 초안을 고르지 않은 것과 같이 보지 않는다(그 칸은 「미선택 = 목표 미달
//   공정 전체」 라 모두 켬과 뜻이 다르다).
// - `pickOrder: true` — 초안을 선택지 차례가 아니라 누른 차례로 쌓는다(그 칸의 한 줄 글은 처음 고른 공정이
//   앞이다). 지금 값(`selected`)의 차례가 첫 초안이고, 차례만 바뀐 초안도 「적용」 할 수 있다.
// - `clearDraft: true` — 「전체」 자리 단추가 공용 값을 지우는 트리거(`clear`)를 보내지 않고 판의 초안만
//   비운다(켠 타일이 있을 때만 켜진다). 비운 초안도 「적용」 이 보낸다 — 고르기는 판에서, 바꾸기는 「적용」
//   하나다. 누른 단추가 잠기므로 초점은 찾기 칸으로 간다 — 「적용」 으로 옮기면 누르고 있던 Enter 의 되풀이가
//   곧바로 공용 설정을 쓴다.
// - `clearLabel` — 「전체」 단추 글. 그 칸에서는 고른 것을 비우는 단추라 「전체」 가 「모든 공정」 으로
//   읽히지 않게 이름을 준다.

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

// 누른 차례로 쌓는 초안 — 켜면 끝에 붙이고 끄면 뺀다(`pickOrder`).
function togglePicked(draft, value) {
  return draft.includes(value) ? draft.filter((item) => item !== value) : [...draft, value]
}

// 두 고름이 같은가 — `ordered` 면 차례까지 본다(누른 차례를 지키는 판).
function sameSelection(left, right, ordered = false) {
  if (left.length !== right.length) return false
  if (ordered) return left.every((item, index) => item === right[index])
  const held = new Set(left)
  return right.every((item) => held.has(item))
}

// 머리 값 — 여러 개 고름은 「선택 n / N」, 하나 고름은 「N개 공정」.
function countLabel(mode, draftCount, total) {
  return mode === 'multi' ? '선택 ' + draftCount + ' / ' + total : total + '개 공정'
}

// 「적용」 상태 — 하나 고름에는 「적용」 이 없다(`none`). 초안이 지금 값 그대로면 `same`. `total` 은 이 화면
// 공정 수다 — 모두 켠 쪽은 고르지 않은 쪽과 같이 본다(이 화면 몫은 전체). `ordered` 면 차례만 바뀐 초안도
// 지금 값과 다르다(`pickOrder` 판).
function applyState(mode, draft, applied, total, ordered = false) {
  if (mode !== 'multi') return 'none'
  const whole = (picked) => (total > 0 && picked.length >= total ? [] : picked)
  return sameSelection(whole(draft), whole(applied), ordered) ? 'same' : 'ready'
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

// 창의 keydown(capture) — 판 찾기 칸에 글이 있을 때 Esc 는 글만 지우고 더 나아가지 않는다(판을 둔 팝업 ·
// 팝오버가 닫히지 않는다). 한글을 치는 중이면 지우지 않고 더 나아가지만 않는다 — 조합을 끝내는 것은
// 입력기 몫이다. 글이 없으면 손대지 않는다(팝업 · 팝오버가 닫힌다). 지우기는 그 판이 단 `clearSearch` 가
// 한다.
function clearSearchOnEscape(event) {
  if (event.key !== 'Escape') return
  const search = event.target
  if (!search || typeof search.closest !== 'function') return
  const root = search.closest('.capa-proc-root')
  if (!root || root.querySelector('.capa-proc-search') !== search) return
  if (event.isComposing) {
    event.stopPropagation()
    return
  }
  const clear = root.__capaProc?.clearSearch
  if (!search.value || typeof clear !== 'function') return
  event.preventDefault()
  event.stopPropagation()
  clear()
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
  const wholeIsAll = data?.wholeIsAll !== false
  const pickOrder = data?.pickOrder === true
  const clearDraft = data?.clearDraft === true
  const clearLabel = typeof data?.clearLabel === 'string' && data.clearLabel ? data.clearLabel : '전체'
  // 모두 켠 초안을 고르지 않은 것과 같이 볼 공정 수 — 0 이면 그렇게 보지 않는다(`applyState`).
  const wholeCount = wholeIsAll ? order.length : 0

  if (!window.__capaProcEscape) {
    window.__capaProcEscape = true
    window.addEventListener('keydown', clearSearchOnEscape, true)
  }

  const state = root.__capaProc || (root.__capaProc = { seen: '', focused: false })
  const signature = JSON.stringify([
    mode,
    options,
    applied,
    hasShared,
    wholeIsAll,
    pickOrder,
    clearDraft,
    clearLabel,
  ])
  if (state.seen !== signature) {
    state.seen = signature
    state.draft = applied.slice()
    state.needle = ''
    state.focus = applied.length ? Math.max(order.indexOf(applied[0]), 0) : 0
    search.value = ''
    const clearText = Array.from(clearAll.childNodes).find((node) => node.nodeType === Node.TEXT_NODE)
    if (clearText) clearText.nodeValue = clearLabel
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
    const status = applyState(mode, state.draft, applied, wholeCount, pickOrder)
    apply.disabled = status !== 'ready'
    clearAll.disabled = clearDraft ? state.draft.length === 0 : !hasShared
    root.dataset.state = status
  }

  const focusTile = (tile) => {
    if (!tile) return
    state.focus = tileIndex(tile)
    render()
    tile.focus()
  }

  const applyDraft = () => {
    if (applyState(mode, state.draft, applied, wholeCount, pickOrder) !== 'ready') return
    setTriggerValue('apply', { values: state.draft.slice() })
  }

  // 초안 비우기(`clearDraft`) — 서버에 가지 않는다. 누른 단추가 잠기므로 초점은 찾기 칸으로 옮긴다(머리
  // 설명 — 「적용」 이 아니다).
  const emptyDraft = () => {
    if (!state.draft.length) return
    state.draft = []
    render()
    search.focus()
  }

  state.clearSearch = () => {
    search.value = ''
    state.needle = ''
    render()
  }

  const press = (tile) => {
    const option = options[tileIndex(tile)]
    if (!option) return
    if (mode === 'single') {
      // 지금 공정을 다시 누르면 바뀌는 것이 없다 — 보내지 않는다(닫기는 X · Esc).
      if (applied[0] !== option.value) setTriggerValue('apply', { values: [option.value] })
      return
    }
    state.draft = pickOrder ? togglePicked(state.draft, option.value) : toggleDraft(state.draft, option.value, order)
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
    if (!event.target.closest('.capa-proc-all')) return
    if (clearDraft) emptyDraft()
    else if (hasShared) setTriggerValue('apply', { clear: true })
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
      // Esc 는 창의 capture 처리기(`clearSearchOnEscape`)가 먼저 받는다.
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
  // 팝업을 연 첫 그림에서 찾기 칸에 초점 — 치면 좁혀지고, Tab 이 「전체」 · 「적용」 · 판으로 간다. 보이지 않는
  // 자리(닫힌 팝오버 안에 미리 선 판)에서는 초점을 가져가지 않는다 — 화면의 다른 칸에서 초점을 뺏지 않게.
  if (!state.focused) {
    requestAnimationFrame(() => {
      if (state.focused || !root.getClientRects().length) return
      state.focused = true
      search.focus()
    })
  }
}
