export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const host = parentElement.querySelector('.sle')
  if (!host || !data) return
  const NS = 'http://www.w3.org/2000/svg'
  const S = host.__sle || (host.__sle = {
    epoch: null, items: new Map(), original: new Map(), originalMarkIds: new Set(), groups: new Map(), undo: [],
    selected: null, selection: new Set(), step: 0.5, drag: null, overlapPairs: 0, blocked: 0,
    canvas: null, originalCanvas: null, note: '', view: { z: 1, x: 0, top: 0 }, spaceDown: false, seq: 0,
    passthrough: [], bgImage: null,
  })
  const palette = data.palette || {}
  for (const [name, value] of Object.entries(palette)) host.style.setProperty('--sle-' + name, String(value))
  const DECIMALS = Number.isInteger(data.decimals) ? data.decimals : 1
  const SCALE = 10 ** DECIMALS
  const MIN_EXTENT = Number(data.canvasLimits?.min) || 10
  const MAX_EXTENT = Number(data.canvasLimits?.max) || 400
  // 편집기에 안 나오지만 이 층에 좌표가 있는 호기가 차지한 범위. 영역은 이보다 줄지 않는다.
  const RESERVED = { right: Number(data.canvasLimits?.reservedW) || 0, top: Number(data.canvasLimits?.reservedH) || 0 }
  const FLOOR = String(data.floor || '')
  const OTHER_FLOORS = (Array.isArray(data.floors) ? data.floors : []).map(String).filter((f) => f !== FLOOR)
  const stageColors = data.stageColors || {}
  const markColors = data.markColors || {}
  const defaultSize = data.defaultSize || { w: 12, h: 7 }
  const NEW_UNIT = data.newUnit || {}
  const EXISTING_IDS = new Set((NEW_UNIT.existingIds || []).map(String))
  const MAX_ZOOM = 8
  const ZOOM_STEP = 1.25
  const DRAG_THRESHOLD_PX = 3
  const HANDLE_PX = 9
  const GROUP_PAD = 0.6
  // 크기 손잡이 여덟 개. 글자는 움직이는 변 — e 오른쪽, w 왼쪽, n 위(데이터의 Y+Ysize), s 아래(데이터의 Y).
  const HANDLE_DIRS = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
  const HANDLE_CURSORS = { nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize' }
  // 설비가 아닌 도면 요소. 반입구·문·기둥·설비 금지 영역은 호기가 덮으면 경고한다(겹침처럼 저장은 막지 않는다).
  const MARK_KINDS = {
    zone: { name: '영역', size: [20, 12], label: '영역', rotatable: false },
    shutter: { name: '반입구', size: [12, 5], label: '반입구', rotatable: true },
    door: { name: '문', size: [4, 4], label: '', rotatable: true },
    column: { name: '기둥', size: [1.5, 1.5], label: '', rotatable: false },
    text: { name: '글자', size: [14, 3], label: '메모', rotatable: true },
    arrow: { name: '동선', size: [16, 3], label: '', rotatable: true },
  }
  const ZONE_COLOR_NAMES = { blue: '파랑', green: '초록', violet: '보라', sky: '하늘', rose: '분홍', gray: '회색' }
  const HINT = '호기·요소를 끌어 옮기고, 고른 것의 모서리·변 손잡이로 크기를 바꿉니다. 빈 곳을 끌거나 Shift/Ctrl+클릭으로 여러 개 · Ctrl+A 전체 · Ctrl+휠 확대 · Space+끌기 화면 이동 · 방향키 이동 · Ctrl+방향키 크기 · Ctrl+Z 실행 취소'

  const q = (selector) => host.querySelector(selector)
  const svg = q('.sle-canvas')
  const bg = svg.querySelector('.sle-bg')
  const grid = svg.querySelector('.sle-grid')
  const zonesLayer = svg.querySelector('.sle-zones')
  const layer = svg.querySelector('.sle-items')
  const marksLayer = svg.querySelector('.sle-marks')
  const overlay = svg.querySelector('.sle-overlay')
  const trayList = q('.sle-tray-list')
  const trayCount = q('.sle-tray-count')
  const leavingBox = q('.sle-leaving')
  const leavingList = q('.sle-leaving-list')
  const statusBox = q('.sle-status')
  const applyButton = q('.sle-apply')
  const undoButton = q('.sle-undo')
  const unplaceButton = q('.sle-unplace')
  const areaW = q('.sle-area-w')
  const areaH = q('.sle-area-h')
  const areaNote = q('.sle-area-note')
  const inspector = q('.sle-inspector')
  const inspectorName = q('.sle-inspector-name')
  const fieldInputs = [...host.querySelectorAll('.sle-fields input')]
  const sendBox = q('.sle-sendto')
  const moveSelect = q('.sle-move-floor')
  const moveButton = q('.sle-move')
  const markProps = q('.sle-markprops')
  const markLabel = q('.sle-mark-label')
  const markColor = q('.sle-mark-color')
  const markHatch = q('.sle-mark-hatch')
  const markKeepOut = q('.sle-mark-keepout')
  const markRotate = q('.sle-mark-rotate')
  const zoneOnly = [...host.querySelectorAll('.sle-zone-only')]
  const zoomOut = q('.sle-zoom-out')
  const zoomIn = q('.sle-zoom-in')
  const zoomLabel = q('.sle-zoom-label')
  const zoomFit = q('.sle-zoom-fit')
  const zoomSel = q('.sle-zoom-sel')
  const addToggle = q('.sle-addunit-toggle')
  const addForm = q('.sle-addunit-form')
  const newId = q('.sle-new-id')
  const newProcess = q('.sle-new-process')
  const newLine = q('.sle-new-line')
  const newUse = q('.sle-new-use')
  const newW = q('.sle-new-w')
  const newH = q('.sle-new-h')
  const newError = q('.sle-new-error')
  const newKind = q('.sle-new-kind')
  const newDates = q('.sle-new-dates')
  const newArrival = q('.sle-new-arrival')
  const newQual = q('.sle-new-qual')
  const newConfirm = q('.sle-new-confirm')
  q('.sle-title').textContent = data.title || ''

  const num = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v))
  const roundTo = (v) => Math.round(v * SCALE) / SCALE
  // 상한은 바깥으로 넘지 않게 내린다 — 반올림이 캔버스 밖으로 0.05 를 밀어내면 저장 검사가 마스터 전체를 막는다.
  const floorTo = (v) => Math.floor(v * SCALE + 1e-9) / SCALE
  const ceilTo = (v) => Math.ceil(v * SCALE - 1e-9) / SCALE
  const snapDelta = (d) => Math.round(d / S.step) * S.step
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi))
  // 가장 작은 크기는 저장 정밀도 한 칸이다. 격자 간격에 묶으면 격자 2 에서 1.5 기둥이 건드리기만 해도 커진다.
  const minSize = () => 1 / SCALE
  const isUnit = (m) => m.kind === 'unit'
  const isMark = (m) => m.kind !== 'unit'
  const blocks = (m) => (m.kind === 'zone' && m.keepOut) || m.kind === 'shutter' || m.kind === 'door' || m.kind === 'column'
  const color = (item) => stageColors[item.stage] || palette.fallback || 'gray'
  const zoneColor = (m) => (m.keepOut ? 'var(--sle-danger)' : markColors[m.color] || markColors.gray || 'gray')
  const W = () => S.canvas.w
  const H = () => S.canvas.h
  const viewW = () => W() / S.view.z
  const viewH = () => H() / S.view.z
  // 데이터는 왼쪽 아래가 원점(Y 위로), SVG 는 왼쪽 위가 원점이다.
  const svgTop = (item) => H() - (item.y + item.h)
  const el = (tag, attrs) => {
    const node = document.createElementNS(NS, tag)
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v))
    return node
  }
  const isFocused = (node) => node.getRootNode().activeElement === node
  const toUser = (event) => {
    const matrix = svg.getScreenCTM()
    if (!matrix) return null
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    const p = point.matrixTransform(matrix.inverse())
    return { x: p.x, top: p.y }
  }
  const unitsPerPx = () => {
    const matrix = svg.getScreenCTM()
    return matrix && matrix.a ? 1 / matrix.a : 0.1
  }
  // 글자 폭 어림(em). 한글은 1, 나머지는 0.6.
  const emWidth = (text) => [...text].reduce((sum, ch) => sum + (ch.charCodeAt(0) >= 0x1100 ? 1 : 0.6), 0)
  const snapshot = (item) => ({
    x: item.x, y: item.y, w: item.w, h: item.h, placed: item.placed, moveTo: item.moveTo, sizeGuessed: item.sizeGuessed,
    rot: item.rot, label: item.label, color: item.color, hatch: item.hatch, keepOut: item.keepOut,
  })
  const hasSize = (item) => Number.isFinite(item.w) && item.w > 0 && Number.isFinite(item.h) && item.h > 0
  const unitTip = (item) => `${item.label} · ${item.stage || ''}${item.group ? ` · 모체 ${item.group}` : ''}${item.arrived ? ' · 다른 층에서 옴' : ''}`
  const sameGeometry = (a, b) => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h
  const sameNumber = (p, q) => p === q || (Number.isNaN(p) && Number.isNaN(q))
  const sameSize = (a, b) => sameNumber(a.w, b.w) && sameNumber(a.h, b.h)
  // 이 층 도면에 서 있는가. 다른 층으로 보낸 호기는 좌표를 지닌 채 이 층에서만 빠진다.
  const onCanvas = (m) => m.placed && !m.moveTo
  // 모체호기로 묶은 모듈 행은 한 덩어리다. 묶음이 없으면 자기 하나.
  const members = (item) => (item.group ? [...S.items.values()].filter((m) => m.group === item.group) : [item])
  const placedMembers = (item) => members(item).filter(onCanvas)
  // 고른 것들. S.selected 는 그중 기준(마지막으로 누른) 것이다.
  const selectedItems = () => [...S.selection].map((id) => S.items.get(id)).filter(Boolean)
  // 함께 움직일 것: 고른 것과 그 모듈 묶음 전체(이 층 도면에 선 것만).
  const expanded = (list) => {
    const out = new Map()
    for (const item of list) for (const m of placedMembers(item)) out.set(m.id, m)
    return [...out.values()]
  }
  const bbox = (list) => {
    const box = { minX: Infinity, minY: Infinity, maxR: -Infinity, maxT: -Infinity }
    for (const m of list) {
      box.minX = Math.min(box.minX, m.x)
      box.minY = Math.min(box.minY, m.y)
      box.maxR = Math.max(box.maxR, m.x + m.w)
      box.maxT = Math.max(box.maxT, m.y + m.h)
    }
    return box
  }
  // 좌표를 캔버스 안·정밀도 안으로 맞춘다. 크기 먼저, 그다음 위치(위치 상한이 크기에 달려 있다).
  const fit = (item) => {
    item.w = floorTo(clamp(roundTo(item.w), Math.min(minSize(), W()), W()))
    item.h = floorTo(clamp(roundTo(item.h), Math.min(minSize(), H()), H()))
    item.x = clamp(roundTo(item.x), 0, floorTo(W() - item.w))
    item.y = clamp(roundTo(item.y), 0, floorTo(H() - item.h))
  }
  // 묶음 전체가 영역 안에 남도록 이동량을 자른다. 묶음 모양은 그대로다.
  const clampShift = (box, dx, dy) => ({
    dx: clamp(dx, -box.minX, W() - box.maxR),
    dy: clamp(dy, -box.minY, H() - box.maxT),
  })
  // 놓인 호기·요소가 차지한 가장 먼 오른쪽·위. 편집 영역은 이보다 작게 줄일 수 없다.
  const extents = () => {
    let right = RESERVED.right
    let top = RESERVED.top
    for (const item of S.items.values()) {
      if (!onCanvas(item)) continue
      right = Math.max(right, item.x + item.w)
      top = Math.max(top, item.y + item.h)
    }
    return { right: ceilTo(right), top: ceilTo(top) }
  }

  // ---------------------------------------------------------------- 확대·축소
  // viewBox 를 캔버스의 일부로 좁혀 확대한다. 좌표 변환은 getScreenCTM 이 viewBox 를 품어 끌기·손잡이가 그대로 맞는다.
  function clampView() {
    S.view.z = clamp(S.view.z, 1, MAX_ZOOM)
    S.view.x = clamp(S.view.x, 0, W() - viewW())
    S.view.top = clamp(S.view.top, 0, H() - viewH())
  }
  function applyView({ reposition = true } = {}) {
    clampView()
    svg.setAttribute('viewBox', `${S.view.x} ${S.view.top} ${viewW()} ${viewH()}`)
    zoomLabel.textContent = `${Math.round(S.view.z * 100)}%`
    zoomOut.disabled = S.view.z <= 1
    zoomIn.disabled = S.view.z >= MAX_ZOOM
    svg.classList.toggle('is-zoomed', S.view.z > 1)
    // 손잡이 크기·글자 숨김은 화면 px 로 정하므로 배율이 바뀌면 다시 맞춘다.
    if (!reposition) return
    for (const [id, group] of S.groups) position(group, S.items.get(id))
    drawSelectionBox()
  }
  function zoomAt(z, anchor) {
    const a = anchor || { x: S.view.x + viewW() / 2, top: S.view.top + viewH() / 2 }
    const fx = (a.x - S.view.x) / viewW()
    const ft = (a.top - S.view.top) / viewH()
    S.view.z = clamp(z, 1, MAX_ZOOM)
    S.view.x = a.x - fx * viewW()
    S.view.top = a.top - ft * viewH()
    applyView()
  }
  function zoomToBox(box) {
    const pad = 3
    const z = clamp(Math.min(W() / (box.maxR - box.minX + pad * 2), H() / (box.maxT - box.minY + pad * 2)), 1, MAX_ZOOM)
    S.view.z = z
    S.view.x = (box.minX + box.maxR) / 2 - viewW() / 2
    S.view.top = H() - (box.minY + box.maxT) / 2 - viewH() / 2
    applyView()
  }
  function panBy(dx, dTop) {
    const before = { x: S.view.x, top: S.view.top }
    S.view.x += dx
    S.view.top += dTop
    clampView()
    const moved = S.view.x !== before.x || S.view.top !== before.top
    if (moved) applyView({ reposition: false })
    return moved
  }

  function drawStatic() {
    // 세로로 긴 영역은 화면 높이(78vh)에서 멈춘다. 폭도 같은 비율로 줄여 SVG 상자가 도면과 꼭 맞게 한다.
    svg.style.maxWidth = `calc(78vh * ${W() / H()})`
    bg.replaceChildren()
    if (data.backgroundImage) {
      bg.append(el('image', { href: data.backgroundImage, x: 0, y: 0, width: W(), height: H(), preserveAspectRatio: 'none', class: 'sle-bg-image' }))
    }
    bg.append(el('rect', { class: data.backgroundImage ? 'sle-canvas-bg has-image' : 'sle-canvas-bg', x: 0, y: 0, width: W(), height: H() }))
    grid.replaceChildren()
    // 격자는 데이터 좌표로 긋는다 — 캔버스 높이가 소수여도 선이 스냅 자리와 맞는다. 굵은 선은 10칸마다.
    for (let k = 1; k < W(); k += 1) {
      grid.append(el('line', { class: k % 10 === 0 ? 'sle-grid-major' : 'sle-grid-minor', x1: k, y1: 0, x2: k, y2: H() }))
    }
    for (let k = 1; k < H(); k += 1) {
      const y = H() - k
      grid.append(el('line', { class: k % 10 === 0 ? 'sle-grid-major' : 'sle-grid-minor', x1: 0, y1: y, x2: W(), y2: y }))
    }
    if (!isFocused(areaW)) areaW.value = W()
    if (!isFocused(areaH)) areaH.value = H()
    areaW.min = MIN_EXTENT
    areaW.max = MAX_EXTENT
    areaH.min = MIN_EXTENT
    areaH.max = MAX_EXTENT
    applyView({ reposition: false })
  }

  function positionHandles(group, item, top) {
    // 손잡이는 화면 px 로 크기를 정해 작은 호기에서도 잡힌다. 모서리·변의 가운데에 걸친다.
    const hs = HANDLE_PX * unitsPerPx()
    const xs = { w: item.x, c: item.x + item.w / 2, e: item.x + item.w }
    const ys = { n: top, c: top + item.h / 2, s: top + item.h }
    for (const handle of group.querySelectorAll('.sle-handle')) {
      const dir = handle.dataset.dir
      const hx = dir.includes('w') ? xs.w : dir.includes('e') ? xs.e : xs.c
      const hy = dir.includes('n') ? ys.n : dir.includes('s') ? ys.s : ys.c
      handle.setAttribute('x', hx - hs / 2)
      handle.setAttribute('y', hy - hs / 2)
      handle.setAttribute('width', hs)
      handle.setAttribute('height', hs)
      // 작은 것은 변 가운데 손잡이가 모서리 손잡이와 겹친다 — 그때는 변 손잡이를 감춘다.
      const edge = dir.length === 1
      const tooSmall = (dir === 'n' || dir === 's') ? item.w < hs * 3 : item.h < hs * 3
      handle.style.display = edge && tooSmall ? 'none' : ''
    }
  }

  function position(group, item) {
    if (!group || !item) return
    const top = svgTop(item)
    const rect = group.querySelector('.sle-rect')
    rect.setAttribute('x', item.x)
    rect.setAttribute('y', top)
    rect.setAttribute('width', item.w)
    rect.setAttribute('height', item.h)
    if (isUnit(item)) {
      const label = group.querySelector('.sle-label')
      label.setAttribute('x', item.x + item.w / 2)
      label.setAttribute('y', top + item.h / 2)
      // 글자는 사각형 폭에 맞춰 줄이고 화면에서 14px 를 넘지 않게 한다. 7px 아래면 숨긴다(밀집 층) —
      // 확대하면 다시 보인다. 이름은 선택하면 상태줄·옆 칸에, 올려 두면 풍선에 나온다.
      const upp = unitsPerPx()
      const fitFont = (item.w * 0.94) / Math.max(item.label.length * 0.62, 1)
      const fontSize = Math.min(item.h * 0.32, fitFont, 14 * upp)
      label.setAttribute('font-size', fontSize)
      label.style.display = fontSize / upp < 7 ? 'none' : ''
    } else {
      drawMark(group, item, top)
    }
    positionHandles(group, item, top)
    group.classList.toggle('is-changed', isChanged(item))
  }

  // 요소는 돌리기 전 크기(lw×lh)의 제자리 좌표로 그린 뒤 가운데를 축으로 돌린다. 0° 일 때 아래 변이 벽이다.
  function drawMark(group, item, top) {
    const shape = group.querySelector('.sle-mark-shape')
    shape.replaceChildren()
    const rot = item.rot || 0
    const lw = rot % 180 ? item.h : item.w
    const lh = rot % 180 ? item.w : item.h
    const cx = item.x + item.w / 2
    const cy = top + item.h / 2
    const inner = el('g', { transform: `translate(${cx} ${cy}) rotate(${rot}) translate(${-lw / 2} ${-lh / 2})` })
    const upp = unitsPerPx()
    const fs = 11 * upp
    const text = (value, x, y, size, anchor) => {
      const node = el('text', { class: 'sle-mark-text', x, y, 'font-size': size, 'text-anchor': anchor || 'middle', 'dominant-baseline': 'central' })
      node.textContent = value
      return node
    }
    if (item.kind === 'zone') {
      const c = zoneColor(item)
      const fill = el('rect', { class: 'sle-zone-fill', x: 0, y: 0, width: lw, height: lh, rx: 0.4 })
      fill.style.fill = c
      inner.append(fill)
      if (item.hatch) inner.append(el('rect', { x: 0, y: 0, width: lw, height: lh, fill: 'url(#sle-hatch)' }))
      const border = el('rect', { class: 'sle-zone-border', x: 0, y: 0, width: lw, height: lh, rx: 0.4 })
      border.style.stroke = c
      inner.append(border)
      const caption = (item.label || '영역') + (item.keepOut ? ' · 설비 금지' : '')
      const tagW = Math.min(lw, emWidth(caption) * fs + fs * 0.9)
      const tag = el('rect', { class: 'sle-zone-tag', x: 0, y: 0, width: tagW, height: fs * 1.6, rx: 0.3 })
      inner.append(tag, text(caption, fs * 0.45, fs * 0.8, fs, 'start'))
    } else if (item.kind === 'shutter') {
      // 반입구: 아래 변에 굵은 셔터, 안쪽(위)으로 들어오는 화살표. 상자 전체가 비워 둘 앞 공간이다.
      // 셔터 선은 캔버스 테두리에 묻히지 않게 벽 안쪽으로 조금 들인다.
      const wall = lh - 2.5 * upp
      inner.append(el('rect', { class: 'sle-clear', x: 0, y: 0, width: lw, height: lh }))
      inner.append(el('line', { class: 'sle-shutter-bar', x1: 0, y1: wall, x2: lw, y2: wall }))
      for (let k = 1; k < 6; k += 1) inner.append(el('line', { class: 'sle-shutter-slat', x1: (lw * k) / 6, y1: wall - 2 * upp, x2: (lw * k) / 6, y2: wall + 2 * upp }))
      const head = Math.min(lw, lh) * 0.22
      inner.append(el('line', { class: 'sle-mark-line is-thick', x1: lw / 2, y1: lh * 0.75, x2: lw / 2, y2: lh * 0.12 + head }))
      inner.append(el('polygon', { class: 'sle-mark-head', points: `${lw / 2 - head},${lh * 0.12 + head} ${lw / 2},${lh * 0.12} ${lw / 2 + head},${lh * 0.12 + head}` }))
    } else if (item.kind === 'door') {
      // 여닫이문: 아래 변이 벽, 왼쪽 아래가 경첩. 문짝과 열리는 궤적(사분원) 안이 비워 둘 자리다.
      inner.append(el('path', { class: 'sle-clear', d: `M 0 ${lh} L 0 0 A ${lw} ${lh} 0 0 1 ${lw} ${lh} Z` }))
      inner.append(el('line', { class: 'sle-mark-line is-thick', x1: 0, y1: lh, x2: 0, y2: 0 }))
      inner.append(el('path', { class: 'sle-mark-line is-dashed', d: `M 0 0 A ${lw} ${lh} 0 0 1 ${lw} ${lh}` }))
    } else if (item.kind === 'column') {
      inner.append(el('rect', { class: 'sle-column', x: 0, y: 0, width: lw, height: lh }))
      inner.append(el('line', { class: 'sle-column-cross', x1: 0, y1: 0, x2: lw, y2: lh }))
      inner.append(el('line', { class: 'sle-column-cross', x1: lw, y1: 0, x2: 0, y2: lh }))
    } else if (item.kind === 'text') {
      const value = item.label || '글자'
      const size = Math.min(lh * 0.7, (lw * 0.95) / Math.max(emWidth(value), 1))
      const node = text(value, lw / 2, lh / 2, size)
      node.style.display = size / upp < 6 ? 'none' : ''
      inner.append(node)
    } else if (item.kind === 'arrow') {
      // 동선: 왼쪽에서 오른쪽으로(0°). 굵기는 상자 높이를 따른다.
      const head = Math.min(lh * 1.1, lw * 0.35)
      const shaft = el('line', { class: 'sle-flow', x1: lh * 0.3, y1: lh / 2, x2: lw - head * 0.9, y2: lh / 2 })
      shaft.style.strokeWidth = String(Math.min(lh * 0.2, 5 * upp))
      inner.append(shaft, el('polygon', { class: 'sle-flow-head', points: `${lw - head},${lh * 0.15} ${lw},${lh / 2} ${lw - head},${lh * 0.85}` }))
    }
    shape.append(inner)
    // 반입구·문·동선의 이름표는 돌리지 않는다(세로 글자가 되지 않게). 상자 바깥, 방 쪽(반입구·문)이나
    // 옆(동선)에 가로로 쓴다. 0° 일 때 방은 위쪽이다(아래 변이 벽).
    if (item.label && (item.kind === 'shutter' || item.kind === 'door' || item.kind === 'arrow')) {
      const gap = fs * 0.4
      const sides = item.kind === 'arrow'
        ? (rot % 180 ? 'right' : 'up')
        : ({ 0: 'up', 90: 'right', 180: 'down', 270: 'left' })[rot] || 'up'
      const left = item.x
      const right = item.x + item.w
      const placement = {
        up: [cx, top - gap - fs * 0.5, 'middle'],
        down: [cx, top + item.h + gap + fs * 0.5, 'middle'],
        right: [right + gap, cy, 'start'],
        left: [left - gap, cy, 'end'],
      }[sides]
      shape.append(text(item.label, placement[0], placement[1], fs, placement[2]))
    }
    const tip = group.querySelector('title')
    if (tip) tip.textContent = `${MARK_KINDS[item.kind].name}${item.label ? ` · ${item.label}` : ''}`
  }

  function appendHandles(group) {
    for (const dir of HANDLE_DIRS) {
      const handle = el('rect', { class: 'sle-handle' })
      handle.dataset.dir = dir
      handle.style.cursor = HANDLE_CURSORS[dir]
      group.append(handle)
    }
  }

  function buildGroup(item) {
    const group = el('g', { class: item.arrived ? 'sle-item sle-unit is-arrived' : 'sle-item sle-unit' })
    group.dataset.id = item.id
    const rect = el('rect', { class: 'sle-rect', rx: 0.4 })
    rect.style.fill = color(item)
    const label = el('text', { class: 'sle-label' })
    label.textContent = item.label
    const tip = el('title')
    tip.textContent = unitTip(item)
    group.append(rect, label, tip)
    appendHandles(group)
    position(group, item)
    S.groups.set(item.id, group)
    return group
  }

  function buildMark(item) {
    const group = el('g', { class: `sle-item sle-mark mark-${item.kind}` })
    group.dataset.id = item.id
    group.append(el('g', { class: 'sle-mark-shape' }), el('rect', { class: 'sle-rect sle-mark-box' }), el('title'))
    appendHandles(group)
    position(group, item)
    // 영역은 이름표로도 잡는다(안쪽은 비워 둔다) — 이름표만 눌림을 받게 한다.
    S.groups.set(item.id, group)
    return group
  }

  // 트레이 칩. 묶음은 칩 하나다(대표 = 처음 만난 모듈).
  function trayEntries(keep) {
    const seen = new Set()
    const out = []
    for (const item of S.items.values()) {
      if (!isUnit(item) || !keep(item) || seen.has(item.id)) continue
      const list = item.group ? members(item).filter(keep) : [item]
      for (const m of list) seen.add(m.id)
      out.push({ lead: item, list })
    }
    return out
  }

  function buildChip({ lead, list }, leaving) {
    const chip = document.createElement('div')
    chip.className = 'sle-chip'
    chip.dataset.id = lead.id
    chip.__ids = list.map((m) => m.id)
    const swatch = document.createElement('span')
    swatch.className = 'sle-chip-swatch'
    swatch.style.background = color(lead)
    const text = document.createElement('span')
    text.className = 'sle-chip-name'
    text.textContent = lead.group || lead.label
    const size = document.createElement('span')
    size.className = 'sle-chip-size'
    if (leaving) size.textContent = `→ ${lead.moveTo}${list.some((m) => m.placed) ? ' (같은 자리)' : ''}`
    else if (lead.group) size.textContent = `모듈 ${list.length}`
    else size.textContent = hasSize(lead) ? `${lead.w}×${lead.h}` : '크기 없음'
    if (list.some((m) => m.isNew)) chip.classList.add('is-new')
    if (lead.group) chip.classList.add('is-group')
    chip.append(swatch, text)
    if (!leaving && lead.floorless) {
      const tag = document.createElement('span')
      tag.className = 'sle-chip-tag'
      tag.textContent = '층 미정'
      chip.append(tag)
    }
    chip.append(size)
    if (leaving) {
      chip.classList.add('is-leaving')
      chip.title = '적용하면 그 층으로 갑니다. 놓여 있던 호기는 같은 좌표·크기로, 미배치였던 호기는 그 층 트레이로. 되돌리려면 실행 취소.'
      return chip
    }
    chip.title = lead.group ? `${list.map((m) => m.label).join(', ')} — 함께 놓입니다` : lead.label
    chip.onpointerdown = (event) => ghostDrag(
      event,
      lead.group ? `${lead.group} (모듈 ${list.length})` : lead.label,
      (p) => placeFromTray(lead, list, p),
      () => select(lead.id),
    )
    if (lead.created) {
      // 편집기에서 방금 넣은 호기는 적용 전이라 여기서 바로 뺄 수 있다.
      const remove = document.createElement('button')
      remove.type = 'button'
      remove.className = 'sle-chip-remove'
      remove.textContent = '×'
      remove.title = '추가 취소'
      remove.onpointerdown = (event) => event.stopPropagation()
      remove.onclick = () => removeItems([lead])
      chip.append(remove)
    }
    return chip
  }

  function renderItems() {
    layer.replaceChildren()
    zonesLayer.replaceChildren()
    marksLayer.replaceChildren()
    trayList.replaceChildren()
    leavingList.replaceChildren()
    S.groups = new Map()
    for (const item of S.items.values()) {
      if (!onCanvas(item)) continue
      if (isUnit(item)) layer.append(buildGroup(item))
      else (item.kind === 'zone' ? zonesLayer : marksLayer).append(buildMark(item))
    }
    let trayN = 0
    for (const entry of trayEntries((m) => !m.placed && !m.moveTo)) {
      trayN += entry.list.length
      trayList.append(buildChip(entry, false))
    }
    const leaving = trayEntries((m) => Boolean(m.moveTo))
    for (const entry of leaving) leavingList.append(buildChip(entry, true))
    leavingBox.hidden = leaving.length === 0
    trayCount.textContent = `${trayN}대`
    markSelection()
    markOverlaps()
  }

  // 단계·라벨은 같은 epoch 안에서도 바뀐다(테마 전환·기준일). 기하는 그대로 두고 칠·글자만 다시 쓴다.
  function repaint() {
    for (const [id, group] of S.groups) {
      const item = S.items.get(id)
      if (!item) continue
      if (isUnit(item)) {
        group.querySelector('.sle-rect').style.fill = color(item)
        group.querySelector('.sle-label').textContent = item.label
        group.querySelector('title').textContent = unitTip(item)
      }
      position(group, item)
    }
    for (const chip of host.querySelectorAll('.sle-chip')) {
      const item = S.items.get(chip.dataset.id)
      if (!item) continue
      chip.querySelector('.sle-chip-swatch').style.background = color(item)
      chip.querySelector('.sle-chip-name').textContent = item.group || item.label
    }
  }

  function isChanged(item) {
    const o = S.original.get(item.id)
    if (!o) return true
    if (isMark(item)) {
      return !sameGeometry(o, item) || o.rot !== item.rot || o.label !== item.label
        || o.color !== item.color || o.hatch !== item.hatch || o.keepOut !== item.keepOut
    }
    if ((o.moveTo || null) !== (item.moveTo || null)) return true
    if (o.placed !== item.placed) return true
    // 미배치끼리는 크기만 견준다 — 놓고 키운 뒤 다시 빼면 새 크기가 남는데, 그것도 보내야 한다.
    // 추정 크기로 놓았다 그냥 뺀 호기는 NaN 으로 돌아가므로 NaN 끼리는 같다고 본다.
    if (!item.placed) return !sameSize(o, item)
    return !sameGeometry(o, item)
  }
  const canvasChanged = () => S.canvas.w !== S.originalCanvas.w || S.canvas.h !== S.originalCanvas.h
  // 도면 요소의 변경 건수 = 새로 넣은 것 + 바뀐 것 + 지운 것.
  function markChangeCount() {
    let count = 0
    const present = new Set()
    for (const m of S.items.values()) {
      if (!isMark(m)) continue
      present.add(m.id)
      if (isChanged(m)) count += 1
    }
    for (const id of S.originalMarkIds) if (!present.has(id)) count += 1
    return count
  }

  // 함께 움직일 범위(모듈 묶음·여러 개 선택)를 점선 상자로 둘러 보인다. 사각형으로 고르는 중이면 그 사각형도.
  function drawSelectionBox() {
    overlay.replaceChildren()
    const list = expanded(selectedItems())
    if (list.length >= 2) {
      const box = bbox(list)
      overlay.append(el('rect', {
        class: 'sle-group-box', rx: 0.6,
        x: box.minX - GROUP_PAD, y: H() - box.maxT - GROUP_PAD,
        width: box.maxR - box.minX + GROUP_PAD * 2, height: box.maxT - box.minY + GROUP_PAD * 2,
      }))
    }
    const rect = S.drag && S.drag.mode === 'marquee' ? S.drag.rect : null
    if (rect) overlay.append(el('rect', { class: 'sle-marquee', x: rect.x0, y: rect.t0, width: rect.x1 - rect.x0, height: rect.t1 - rect.t0 }))
  }

  function markSelection() {
    const together = new Set(expanded(selectedItems()).map((m) => m.id))
    for (const [id, group] of S.groups) {
      group.classList.toggle('is-selected', S.selection.has(id))
      group.classList.toggle('is-grouped', together.has(id) && !S.selection.has(id))
    }
    // 여러 개를 고르면 크기 손잡이를 감춘다(크기는 숫자 칸·Ctrl+방향키로 함께 바꾼다).
    svg.classList.toggle('is-multi', S.selection.size > 1)
    for (const chip of trayList.children) chip.classList.toggle('is-selected', Boolean(chip.__ids?.some((id) => S.selection.has(id))))
    drawSelectionBox()
  }

  const overlaps = (p, q2) => p.x < roundTo(q2.x + q2.w) && q2.x < roundTo(p.x + p.w)
    && p.y < roundTo(q2.y + q2.h) && q2.y < roundTo(p.y + p.h)

  // 겹침은 막지 않고 알린다(저장도 된다). 호기끼리, 그리고 호기와 반입구·문·기둥·설비 금지 영역.
  function markOverlaps() {
    const units = [...S.items.values()].filter((i) => isUnit(i) && onCanvas(i))
    const blockers = [...S.items.values()].filter((m) => isMark(m) && onCanvas(m) && blocks(m))
    const hit = new Set()
    let pairs = 0
    for (let a = 0; a < units.length; a += 1) {
      for (let b = a + 1; b < units.length; b += 1) {
        if (overlaps(units[a], units[b])) { hit.add(units[a].id); hit.add(units[b].id); pairs += 1 }
      }
    }
    const blocked = new Set()
    const violated = new Set()
    for (const unit of units) {
      for (const mark of blockers) {
        if (overlaps(unit, mark)) { blocked.add(unit.id); violated.add(mark.id) }
      }
    }
    for (const [id, group] of S.groups) {
      group.classList.toggle('is-overlap', hit.has(id))
      group.classList.toggle('is-blocked', blocked.has(id))
      group.classList.toggle('is-violated', violated.has(id))
    }
    S.overlapPairs = pairs
    S.blocked = blocked.size
  }

  // 끄는 동안에는 움직이는 것만 나머지와 견준다(O(n·k)).
  function markDragOverlap(moving) {
    const movers = [...moving].map((id) => S.items.get(id))
    const hit = new Set()
    for (const other of S.items.values()) {
      if (!onCanvas(other) || moving.has(other.id)) continue
      for (const m of movers) {
        const clash = (isUnit(m) && (isUnit(other) || blocks(other))) || (blocks(m) && isUnit(other))
        if (clash && overlaps(m, other)) { hit.add(other.id); hit.add(m.id) }
      }
    }
    for (const [id, group] of S.groups) group.classList.toggle('is-overlap-live', hit.has(id))
  }

  function clearDragOverlap() {
    for (const group of S.groups.values()) group.classList.remove('is-overlap-live')
  }

  // 호기 변경. 놓인 호기는 좌표·크기를, 트레이로 뺀 호기는 크기를 들고 간다(크기는 실제 설비 치수다).
  function changes() {
    const out = []
    for (const item of S.items.values()) {
      if (!isUnit(item) || !isChanged(item)) continue
      const change = { id: item.id, placed: item.placed }
      if (item.created) change.created = item.created
      if (item.moveTo) change.moveTo = item.moveTo
      if (Number.isFinite(item.w) && Number.isFinite(item.h)) Object.assign(change, { w: item.w, h: item.h })
      if (item.placed) Object.assign(change, { x: item.x, y: item.y })
      out.push(change)
    }
    return out
  }

  // 그리지 못한 요소(모르는 종류·숫자 아님)도 그대로 돌려보낸다 — 층 단위 교체라 빼면 지워진다.
  const marksPayload = () => [
    ...[...S.items.values()].filter(isMark).map((m) => ({
      id: m.id, kind: m.kind, x: m.x, y: m.y, w: m.w, h: m.h, rot: m.rot || 0,
      label: m.label || '', color: m.color || '', hatch: Boolean(m.hatch), keepOut: Boolean(m.keepOut),
    })),
    ...S.passthrough,
  ]

  function syncInspector() {
    const chosen = selectedItems()
    const multi = chosen.length > 1
    const standing = chosen.filter(onCanvas)
    const editable = chosen.length > 0 && standing.length === chosen.length
    const single = chosen.length === 1 ? chosen[0] : null
    inspector.classList.toggle('is-empty', chosen.length === 0)
    if (!chosen.length) {
      inspectorName.textContent = '— 도면이나 트레이에서 고르세요(빈 곳을 끌면 여러 개)'
    } else if (multi) {
      const together = expanded(chosen).length
      inspectorName.textContent = `${chosen.length}개${together > chosen.length ? ` (모듈 묶음까지 ${together}개)` : ''}`
    } else if (isMark(single)) {
      inspectorName.textContent = `${MARK_KINDS[single.kind].name}${single.label ? ` · ${single.label}` : ''}`
    } else if (single.group) {
      inspectorName.textContent = `${single.label} · 모체 ${single.group} (모듈 ${members(single).length})`
    } else {
      inspectorName.textContent = single.label
    }
    const box = editable ? bbox(expanded(standing)) : null
    for (const input of fieldInputs) {
      input.disabled = !editable
      input.step = String(S.step)
      input.placeholder = ''
      if (!editable) { input.value = ''; continue }
      if (isFocused(input)) continue
      const field = input.dataset.field
      if (!multi) { input.value = String(single[field]); continue }
      // 여러 개: X·Y 는 함께 움직일 범위의 왼쪽 아래, 폭·높이는 모두 같을 때만 값을 보인다.
      if (field === 'x') { input.value = String(roundTo(box.minX)); continue }
      if (field === 'y') { input.value = String(roundTo(box.minY)); continue }
      const values = new Set(standing.map((m) => m[field]))
      input.value = values.size === 1 ? String([...values][0]) : ''
      input.placeholder = values.size === 1 ? '' : '여러 값'
    }
    const known = [...moveSelect.options].map((o) => o.value).join('|')
    if (known !== OTHER_FLOORS.join('|')) {
      moveSelect.replaceChildren(...OTHER_FLOORS.map((floor) => new Option(floor, floor)))
    }
    const units = chosen.filter(isUnit)
    sendBox.hidden = chosen.length > 0 && units.length === 0
    const canSend = units.length > 0 && units.every((m) => !m.moveTo) && OTHER_FLOORS.length > 0
    moveSelect.disabled = !canSend
    moveButton.disabled = !canSend
    const mark = single && isMark(single) ? single : null
    markProps.hidden = !mark
    if (mark) {
      if (!isFocused(markLabel)) markLabel.value = mark.label || ''
      for (const node of zoneOnly) node.hidden = mark.kind !== 'zone'
      if (!markColor.options.length) {
        markColor.replaceChildren(...Object.keys(markColors).map((key) => new Option(ZONE_COLOR_NAMES[key] || key, key)))
      }
      markColor.value = mark.color || 'gray'
      markHatch.checked = Boolean(mark.hatch)
      markKeepOut.checked = Boolean(mark.keepOut)
      markRotate.hidden = !MARK_KINDS[mark.kind].rotatable
    }
  }

  function updateStatus() {
    const chosen = selectedItems()
    const item = chosen.length === 1 ? chosen[0] : null
    const changed = changes().length + markChangeCount() + (canvasChanged() ? 1 : 0)
    statusBox.replaceChildren()
    const add = (text, strong) => {
      if (statusBox.childNodes.length) statusBox.append(document.createTextNode(' · '))
      statusBox.append(document.createTextNode(text))
      if (strong === undefined) return
      const b = document.createElement('b')
      b.textContent = strong
      statusBox.append(b)
    }
    if (chosen.length > 1) {
      add('선택 ', `${chosen.length}개`)
      add(`${expanded(chosen).length}개가 함께 움직입니다 — Shift/Ctrl+클릭으로 더하거나 빼기 · Esc 선택 풀기`)
    } else if (item && isMark(item)) {
      add('선택 ', `${MARK_KINDS[item.kind].name}${item.label ? ` ${item.label}` : ''}`)
      add(`X ${item.x} · Y ${item.y} · 크기 ${item.w}×${item.h}${item.rot ? ` · ${item.rot}°` : ''}`)
    } else if (item) {
      add('선택 ', item.label)
      if (onCanvas(item)) add(`X ${item.x} · Y ${item.y} · 크기 ${item.w}×${item.h}`)
      else add('트레이(미배치) — 위 칸에서 다른 층으로 보낼 수 있습니다')
      if (item.group) add(`모듈 ${members(item).length}대가 함께 움직입니다 — 하나만 옮기려면 Alt+끌기`)
    } else {
      add(HINT)
    }
    add('적용 안 한 변경 ', `${changed}건`)
    if (canvasChanged()) add('편집 영역 ', `${S.originalCanvas.w}×${S.originalCanvas.h} → ${W()}×${H()}`)
    if (S.passthrough.length) add('그리지 못한 도면 요소(그대로 둡니다) ', `${S.passthrough.length}개`)
    if (S.overlapPairs) add('겹침(저장은 됨) ', `${S.overlapPairs}쌍`)
    if (S.blocked) add('반입구·문·기둥·설비 금지 영역을 덮은 호기(저장은 됨) ', `${S.blocked}대`)
    applyButton.disabled = changed === 0
    applyButton.classList.toggle('is-pending', changed > 0)
    undoButton.disabled = S.undo.length === 0
    unplaceButton.disabled = !chosen.some((m) => onCanvas(m) || m.created)
    zoomSel.disabled = !chosen.some(onCanvas)
    for (const b of host.querySelectorAll('.sle-steps button')) b.setAttribute('aria-pressed', String(Number(b.dataset.step) === S.step))
    areaNote.textContent = S.note
    syncInspector()
  }

  function setSelection(ids, primary) {
    S.selection = new Set(ids.filter((id) => S.items.has(id)))
    S.selected = primary && S.selection.has(primary) ? primary : ([...S.selection].pop() ?? null)
    markSelection()
    updateStatus()
  }

  function select(id) {
    setSelection(id ? [id] : [], id)
  }

  function clearSelection() {
    S.selection = new Set()
    S.selected = null
  }

  // 사라졌거나 다른 층으로 보낸 것은 선택에서 뺀다.
  function pruneSelection() {
    for (const id of [...S.selection]) {
      const item = S.items.get(id)
      if (!item || item.moveTo) S.selection.delete(id)
    }
    if (!S.selection.has(S.selected)) S.selected = [...S.selection].pop() ?? null
  }

  // 실행 취소 기록. set = 값 되돌리기, create = 새로 만든 것 지우기, delete = 지운 것 되살리기.
  function pushUndo(ops) {
    if (!ops.length) return
    S.undo.push({ kind: 'ops', ops })
    if (S.undo.length > 200) S.undo.shift()
  }
  const commit = (entries) => pushUndo(entries.map((e) => ({ op: 'set', id: e.id, before: e.before })))

  // ---------------------------------------------------------------- 편집 영역(캔버스) 크기
  function setCanvas(requestedW, requestedH, { record = true } = {}) {
    const ext = extents()
    const minW = Math.max(MIN_EXTENT, ext.right)
    const minH = Math.max(MIN_EXTENT, ext.top)
    let w = roundTo(Number.isFinite(requestedW) ? requestedW : W())
    let h = roundTo(Number.isFinite(requestedH) ? requestedH : H())
    const notes = []
    if (w < minW) { notes.push(`폭은 ${minW} 아래로 줄일 수 없습니다(${ext.right > MIN_EXTENT ? '호기·요소가 거기까지 놓여 있습니다' : `최소 ${MIN_EXTENT}`})`); w = minW }
    if (h < minH) { notes.push(`높이는 ${minH} 아래로 줄일 수 없습니다(${ext.top > MIN_EXTENT ? '호기·요소가 거기까지 놓여 있습니다' : `최소 ${MIN_EXTENT}`})`); h = minH }
    if (w > MAX_EXTENT) { notes.push(`폭은 최대 ${MAX_EXTENT} 입니다`); w = MAX_EXTENT }
    if (h > MAX_EXTENT) { notes.push(`높이는 최대 ${MAX_EXTENT} 입니다`); h = MAX_EXTENT }
    S.note = notes.join(' · ')
    if (w === W() && h === H()) { areaW.value = W(); areaH.value = H(); updateStatus(); return }
    if (record) {
      S.undo.push({ kind: 'canvas', before: { ...S.canvas } })
      if (S.undo.length > 200) S.undo.shift()
    }
    S.canvas = { w, h }
    areaW.value = w
    areaH.value = h
    drawStatic()
    renderItems()
    updateStatus()
  }

  // 트레이 칩·팔레트에서 끌어 도면에 놓는다. 끌지 않고 누르기만 하면 onClick.
  function ghostDrag(event, label, onDrop, onClick) {
    if (event.button !== 0) return
    event.preventDefault()
    const source = event.currentTarget
    source.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const startY = event.clientY
    const ghost = document.createElement('div')
    ghost.className = 'sle-ghost'
    ghost.textContent = label
    const move = (e) => { ghost.style.left = `${e.clientX + 8}px`; ghost.style.top = `${e.clientY + 8}px` }
    let shown = false
    const finish = (e, dropped) => {
      source.onpointermove = null
      source.onpointerup = source.onpointercancel = source.onlostpointercapture = null
      ghost.remove()
      if (!dropped) return
      const still = Math.hypot(e.clientX - startX, e.clientY - startY) < DRAG_THRESHOLD_PX
      if (still) { onClick(); return }
      const box = svg.getBoundingClientRect()
      const inside = e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom
      const p = inside ? toUser(e) : null
      if (p) onDrop(p)
    }
    source.onpointermove = (e) => {
      if (!shown && Math.hypot(e.clientX - startX, e.clientY - startY) >= DRAG_THRESHOLD_PX) { host.append(ghost); shown = true }
      move(e)
    }
    source.onpointerup = (e) => finish(e, true)
    source.onpointercancel = (e) => finish(e, false)
    source.onlostpointercapture = (e) => { if (source.onpointerup) finish(e, false) }
  }

  function placeFromTray(lead, list, p) {
    // 크기는 실제 설비 치수라 영역에 맞춰 자르지 않는다. 없을 때만 추정 크기(같은 공정의 가운데 크기)를 쓰고
    // 그 사실을 기억한다 — 다시 트레이로 빼면 추정 크기를 버려 「크기 없음」으로 돌아간다.
    const sizes = list.map((m) => ({
      w: roundTo(hasSize(m) ? m.w : defaultSize.w),
      h: roundTo(hasSize(m) ? m.h : defaultSize.h),
      guessed: !hasSize(m),
    }))
    // 묶음은 거의 정사각 격자로 붙여 놓는다(모듈 넷 → 2×2, 첫 모듈이 왼쪽 위). 한 대면 놓은 자리가 가운데.
    const cols = Math.ceil(Math.sqrt(list.length))
    const rows = Math.ceil(list.length / cols)
    const cellW = Math.max(...sizes.map((size) => size.w))
    const cellH = Math.max(...sizes.map((size) => size.h))
    if (cols * cellW > W() || rows * cellH > H()) {
      S.note = `${lead.group || lead.label} (${roundTo(cols * cellW)}×${roundTo(rows * cellH)}) 가 편집 영역 ${W()}×${H()} 보다 커서 놓지 않았습니다 — 영역을 넓힌 뒤 놓으세요`
      updateStatus()
      return
    }
    S.note = ''
    const entries = list.map((m) => ({ id: m.id, before: snapshot(m) }))
    list.forEach((m, i) => {
      m.w = sizes[i].w
      m.h = sizes[i].h
      m.sizeGuessed = sizes[i].guessed
    })
    const left = snapDelta(p.x - (cols * cellW) / 2)
    const bottom = snapDelta(H() - p.top - (rows * cellH) / 2)
    list.forEach((m, i) => {
      m.x = roundTo(left + (i % cols) * cellW)
      m.y = roundTo(bottom + (rows - 1 - Math.floor(i / cols)) * cellH)
      m.placed = true
    })
    const shift = clampShift(bbox(list), 0, 0)
    for (const m of list) {
      m.x = roundTo(m.x + shift.dx)
      m.y = roundTo(m.y + shift.dy)
      fit(m)
    }
    commit(entries)
    S.selection = new Set([lead.id])
    S.selected = lead.id
    renderItems()
    updateStatus()
    svg.focus({ preventScroll: true })
  }

  // 도면 요소를 넣는다. 자리를 주지 않으면 지금 보이는 화면의 가운데.
  function addMark(kind, at) {
    const spec = MARK_KINDS[kind]
    if (!spec) return
    const [w, h] = spec.size
    S.seq += 1
    const id = `MK-${Date.now().toString(36)}-${S.seq}`
    const center = at || { x: S.view.x + viewW() / 2, top: S.view.top + viewH() / 2 }
    const item = {
      id, kind, label: spec.label, stage: '', group: null, placed: true, moveTo: null, isNew: false, arrived: false,
      x: snapDelta(center.x - w / 2), y: snapDelta(H() - center.top - h / 2), w, h, rot: 0,
      color: kind === 'zone' ? 'blue' : '', hatch: false, keepOut: false,
    }
    fit(item)
    S.items.set(id, item)
    pushUndo([{ op: 'create', id }])
    renderItems()
    setSelection([id], id)
    svg.focus({ preventScroll: true })
  }

  // 방향키·숫자 칸의 X·Y 는 고른 것 전부(모듈 묶음 포함)를 함께 옮긴다. 묶음 모양은 그대로다.
  function moveItems(list, dx, dy) {
    if (!list.length) return
    const entries = list.map((m) => ({ id: m.id, before: snapshot(m) }))
    const shift = clampShift(bbox(list), dx, dy)
    for (const m of list) {
      m.x = roundTo(m.x + shift.dx)
      m.y = roundTo(m.y + shift.dy)
    }
    const moved = entries.filter((e) => !sameGeometry(e.before, S.items.get(e.id)))
    if (!moved.length) { syncInspector(); return }
    commit(moved)
    for (const m of list) position(S.groups.get(m.id), m)
    drawSelectionBox()
    markOverlaps()
    updateStatus()
  }

  // 크기는 고른 것 하나하나에 적용한다(묶음의 다른 모듈은 그대로). 폭은 오른쪽으로, 높이는 위로 자란다.
  function setSizes(list, patchOf) {
    const entries = []
    for (const item of list) {
      const before = snapshot(item)
      Object.assign(item, patchOf(item))
      fit(item)
      if (!sameGeometry(item, before)) {
        item.sizeGuessed = false
        entries.push({ id: item.id, before })
      }
    }
    if (!entries.length) { syncInspector(); return }
    commit(entries)
    for (const e of entries) position(S.groups.get(e.id), S.items.get(e.id))
    drawSelectionBox()
    markOverlaps()
    updateStatus()
  }

  function setMarkProps(item, patch) {
    const before = snapshot(item)
    Object.assign(item, patch)
    fit(item)
    pushUndo([{ op: 'set', id: item.id, before }])
    position(S.groups.get(item.id), item)
    drawSelectionBox()
    markOverlaps()
    updateStatus()
  }

  // 가운데를 축으로 90° 돌린다(상자 폭·높이가 바뀐다).
  function rotateMark(item) {
    if (item.h > W() || item.w > H()) {
      S.note = `돌리면 ${item.h}×${item.w} 이 되어 편집 영역 ${W()}×${H()} 를 넘어 돌리지 않았습니다`
      updateStatus()
      return
    }
    const cx = item.x + item.w / 2
    const cy = item.y + item.h / 2
    setMarkProps(item, { rot: ((item.rot || 0) + 90) % 360, w: item.h, h: item.w, x: cx - item.h / 2, y: cy - item.w / 2 })
  }

  // 빼기·지우기: 호기는 트레이로(크기는 남는다), 도면 요소와 방금 넣은 호기는 지운다. 한 번에 되돌린다.
  function removeItems(list) {
    const fresh = list.filter((m) => isUnit(m) && m.created)
    const units = expanded(list.filter((m) => isUnit(m) && !m.created))
    const marks = list.filter(isMark)
    const ops = []
    for (const m of units) {
      ops.push({ op: 'set', id: m.id, before: snapshot(m) })
      m.placed = false
      if (m.sizeGuessed) {
        m.w = NaN
        m.h = NaN
        m.sizeGuessed = false
      }
    }
    for (const m of [...marks, ...fresh]) {
      ops.push({ op: 'delete', item: { ...m } })
      S.items.delete(m.id)
    }
    if (!ops.length) return
    pushUndo(ops)
    clearSelection()
    renderItems()
    updateStatus()
  }

  // 다른 층으로 보낸다. 묶음은 함께 간다(모듈 행은 동·층이 같아야 한다). 놓여 있던 호기는 같은 좌표·크기로
  // 그 층에 서고(파이썬이 그 층 영역 안으로 맞춘다), 미배치였던 호기는 그 층 트레이로 간다.
  function sendItems(list, floor) {
    if (!floor || floor === FLOOR || !OTHER_FLOORS.includes(floor)) return
    const targets = new Map()
    for (const item of list.filter(isUnit)) for (const m of members(item)) if (!m.moveTo) targets.set(m.id, m)
    if (!targets.size) return
    commit([...targets.values()].map((m) => ({ id: m.id, before: snapshot(m) })))
    for (const m of targets.values()) m.moveTo = floor
    clearSelection()
    renderItems()
    updateStatus()
  }

  function undo() {
    const last = S.undo.pop()
    if (!last) return
    if (last.kind === 'canvas') {
      S.canvas = { ...last.before }
      S.note = ''
      drawStatic()
    } else {
      let applied = 0
      for (const op of [...last.ops].reverse()) {
        if (op.op === 'set') {
          // 추가를 취소해 사라진 것의 기록은 건너뛴다.
          const item = S.items.get(op.id)
          if (!item) continue
          Object.assign(item, op.before)
          applied += 1
        } else if (op.op === 'create') {
          if (S.items.delete(op.id)) applied += 1
        } else if (op.op === 'delete') {
          S.items.set(op.item.id, { ...op.item })
          applied += 1
        }
      }
      if (!applied) { undo(); return }
    }
    pruneSelection()
    renderItems()
    updateStatus()
  }

  function cancelDrag() {
    const drag = S.drag
    if (!drag) return
    S.drag = null
    svg.classList.remove('is-panning')
    if (drag.mode === 'pan') return
    if (drag.mode === 'marquee') {
      S.selection = new Set(drag.before)
      S.selected = drag.beforePrimary
      markSelection()
      updateStatus()
      return
    }
    for (const [id, before] of drag.befores) {
      const item = S.items.get(id)
      Object.assign(item, before)
      position(S.groups.get(id), item)
    }
    drawSelectionBox()
    clearDragOverlap()
    updateStatus()
  }

  // 오른쪽·왼쪽·위·아래 변 가운데 움직이는 것만 옮긴다. 반대쪽 변은 그대로다.
  function resizeTo(item, b, dir, dx, dTop) {
    const m = minSize()
    let left = b.x
    let right = b.x + b.w
    let bottom = b.y
    let top = b.y + b.h
    if (dir.includes('e')) right = clamp(right + dx, left + m, W())
    if (dir.includes('w')) left = clamp(left + dx, 0, right - m)
    if (dir.includes('n')) top = clamp(top - dTop, bottom + m, H())
    if (dir.includes('s')) bottom = clamp(bottom - dTop, 0, top - m)
    item.x = roundTo(left)
    item.y = roundTo(bottom)
    item.w = roundTo(Math.min(roundTo(right), floorTo(W())) - item.x)
    item.h = roundTo(Math.min(roundTo(top), floorTo(H())) - item.y)
    item.sizeGuessed = false
  }

  const readUnit = (raw) => ({
    id: String(raw.id), kind: 'unit', label: String(raw.label ?? raw.id), stage: String(raw.stage || ''),
    group: raw.group ? String(raw.group) : null, x: num(raw.x), y: num(raw.y), w: num(raw.w), h: num(raw.h),
    isNew: Boolean(raw.isNew), arrived: Boolean(raw.arrived), floorless: Boolean(raw.floorless), moveTo: null, created: null,
    sizeGuessed: false,
  })
  const readMark = (raw) => ({
    id: String(raw.id), kind: String(raw.kind), label: String(raw.label || ''), stage: '', group: null,
    x: num(raw.x), y: num(raw.y), w: num(raw.w), h: num(raw.h), rot: Number(raw.rot) || 0,
    color: String(raw.color || ''), hatch: Boolean(raw.hatch), keepOut: Boolean(raw.keepOut),
    placed: true, moveTo: null, isNew: false, arrived: false,
  })

  function initFromData() {
    S.items = new Map()
    S.original = new Map()
    S.originalMarkIds = new Set()
    S.passthrough = []
    for (const raw of data.items || []) {
      const item = readUnit(raw)
      item.placed = Boolean(raw.placed) && [item.x, item.y, item.w, item.h].every(Number.isFinite)
      S.items.set(item.id, item)
      S.original.set(item.id, snapshot(item))
    }
    for (const raw of data.marks || []) {
      const mark = readMark(raw)
      if (!MARK_KINDS[mark.kind] || ![mark.x, mark.y, mark.w, mark.h].every(Number.isFinite)) {
        S.passthrough.push(raw)
        continue
      }
      S.items.set(mark.id, mark)
      S.original.set(mark.id, snapshot(mark))
      S.originalMarkIds.add(mark.id)
    }
  }

  // ------------------------------------------------------------- 회차마다
  if (S.epoch !== data.epoch) {
    S.epoch = data.epoch
    S.undo = []
    clearSelection()
    S.drag = null
    S.note = ''
    const cw = clamp(roundTo(Number(data.canvas?.width) || 100), MIN_EXTENT, MAX_EXTENT)
    const ch = clamp(roundTo(Number(data.canvas?.height) || 60), MIN_EXTENT, MAX_EXTENT)
    S.canvas = { w: cw, h: ch }
    S.originalCanvas = { w: cw, h: ch }
    // 층이 바뀌면 전체 보기로. 같은 층의 다시 맞춤(적용 뒤)은 보던 배율을 지킨다.
    if (String(S.viewFloor) !== FLOOR) S.view = { z: 1, x: 0, top: 0 }
    S.viewFloor = FLOOR
    initFromData()
    S.bgImage = data.backgroundImage || null
    drawStatic()
    renderItems()
  } else {
    // 같은 epoch: 기하는 브라우저가 쥔 것을 지키고, 단계·라벨처럼 보기만 바뀐 것은 합친다.
    for (const raw of data.items || []) {
      const item = S.items.get(String(raw.id))
      if (!item) continue
      item.stage = String(raw.stage || '')
      item.label = String(raw.label ?? raw.id)
    }
    if ((data.backgroundImage || null) !== S.bgImage) {
      S.bgImage = data.backgroundImage || null
      drawStatic()
    }
    repaint()
  }

  // ------------------------------------------------------------- 끌기(속성 대입이라 겹쳐 쌓이지 않는다)
  svg.onmousedown = (event) => { if (event.button === 1) event.preventDefault() }
  svg.onpointerdown = (event) => {
    if (event.button !== 0 && event.button !== 1) return
    const p = toUser(event)
    if (!p) return
    event.preventDefault()
    svg.focus({ preventScroll: true })
    const start = { pointerId: event.pointerId, startX: p.x, startTop: p.top, startClientX: event.clientX, startClientY: event.clientY, moved: false }
    if (event.button === 1 || S.spaceDown) {
      // 화면 옮기기: 가운데 버튼 끌기, 또는 Space 를 누른 채 끌기.
      S.drag = { ...start, mode: 'pan', view: { ...S.view }, upp: unitsPerPx() }
      svg.classList.add('is-panning')
      svg.setPointerCapture(event.pointerId)
      return
    }
    const group = event.target.closest ? event.target.closest('.sle-item') : null
    const additive = event.shiftKey || event.ctrlKey || event.metaKey
    if (!group) {
      // 빈 곳을 끌면 사각형 안에 다 들어온 것을 고른다. Shift/Ctrl 이면 지금 고른 것에 더한다.
      S.drag = { ...start, mode: 'marquee', additive, before: new Set(S.selection), beforePrimary: S.selected, rect: null }
      svg.setPointerCapture(event.pointerId)
      return
    }
    const item = S.items.get(group.dataset.id)
    if (!item) return
    if (additive) {
      // Shift/Ctrl+클릭은 고른 묶음에 더하거나 뺀다(끌지 않는다).
      const ids = new Set(S.selection)
      if (ids.has(item.id)) ids.delete(item.id)
      else ids.add(item.id)
      setSelection([...ids], ids.has(item.id) ? item.id : null)
      return
    }
    const chosen = selectedItems()
    const inSelection = expanded(chosen).some((m) => m.id === item.id)
    const onlyThis = chosen.length === 1 && S.selected === item.id
    if (!inSelection) select(item.id)
    else if (S.selection.has(item.id)) { S.selected = item.id; markSelection(); updateStatus() }
    const dir = event.target.classList.contains('sle-handle') ? event.target.dataset.dir : null
    // 손잡이는 이미 하나만 고른 것에서만 듣는다 — 처음 누른 모서리가 크기를 바꾸지 않게.
    const mode = onlyThis && dir ? 'resize' : 'move'
    // 옮기기는 고른 것 전부와 그 모듈 묶음. Alt 를 누른 채 끌면 누른 것 하나만.
    const list = mode === 'move' && !event.altKey ? expanded(selectedItems()) : [item]
    // 끄는 것이 맨 위에 그려지도록 제 층(호기·영역·요소)의 맨 뒤로 옮긴다.
    for (const m of list) {
      const g = S.groups.get(m.id)
      if (g && g.parentNode) g.parentNode.append(g)
    }
    S.drag = {
      ...start, id: item.id, mode, dir,
      ids: list.map((m) => m.id), befores: new Map(list.map((m) => [m.id, snapshot(m)])), box: bbox(list),
      // 여러 개를 고른 채 하나를 눌렀다 떼기만 하면 그 하나만 고른 상태로 좁힌다.
      collapse: inSelection && (S.selection.size > 1 || !S.selection.has(item.id)),
    }
    svg.setPointerCapture(event.pointerId)
  }
  svg.onpointermove = (event) => {
    const drag = S.drag
    if (!drag || event.pointerId !== drag.pointerId) return
    if (drag.mode === 'pan') {
      S.view.x = drag.view.x - (event.clientX - drag.startClientX) * drag.upp
      S.view.top = drag.view.top - (event.clientY - drag.startClientY) * drag.upp
      applyView({ reposition: false })
      drag.moved = true
      return
    }
    if (event.buttons === 0) { svg.onpointerup(event); return }
    if (!drag.moved && Math.hypot(event.clientX - drag.startClientX, event.clientY - drag.startClientY) < DRAG_THRESHOLD_PX) return
    const p = toUser(event)
    if (!p) return
    if (drag.mode === 'marquee') {
      drag.moved = true
      const x0 = clamp(Math.min(drag.startX, p.x), 0, W())
      const x1 = clamp(Math.max(drag.startX, p.x), 0, W())
      const t0 = clamp(Math.min(drag.startTop, p.top), 0, H())
      const t1 = clamp(Math.max(drag.startTop, p.top), 0, H())
      drag.rect = { x0, x1, t0, t1 }
      // 화면 사각형을 데이터 좌표(Y 위로)로 바꿔, 사각형 안에 다 들어온 것만 고른다.
      const y0 = H() - t1
      const y1 = H() - t0
      const inside = [...S.items.values()]
        .filter((m) => onCanvas(m) && m.x >= x0 && m.x + m.w <= x1 && m.y >= y0 && m.y + m.h <= y1)
        .map((m) => m.id)
      S.selection = new Set(drag.additive ? [...drag.before, ...inside] : inside)
      S.selected = inside.length ? inside[inside.length - 1] : (drag.additive ? drag.beforePrimary : null)
      markSelection()
      updateStatus()
      return
    }
    const dx = snapDelta(p.x - drag.startX)
    const dTop = snapDelta(p.top - drag.startTop)
    if (drag.mode === 'move') {
      // 이동량을 격자에 맞춘다(제자리 좌표를 격자로 끌어당기지 않는다). 화면에서 아래로 끌면 Y 는 준다.
      const shift = clampShift(drag.box, dx, -dTop)
      for (const id of drag.ids) {
        const m = S.items.get(id)
        const b = drag.befores.get(id)
        m.x = roundTo(b.x + shift.dx)
        m.y = roundTo(b.y + shift.dy)
        position(S.groups.get(id), m)
      }
    } else {
      const item = S.items.get(drag.id)
      resizeTo(item, drag.befores.get(drag.id), drag.dir, dx, dTop)
      position(S.groups.get(drag.id), item)
    }
    drag.moved = true
    drawSelectionBox()
    markDragOverlap(new Set(drag.ids))
    updateStatus()
  }
  svg.onpointerup = svg.onpointercancel = (event) => {
    const drag = S.drag
    if (!drag || (event && event.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
    S.drag = null
    if (drag.mode === 'pan') { svg.classList.remove('is-panning'); return }
    if (drag.mode === 'marquee') {
      // 끌지 않고 빈 곳을 누르기만 했으면 선택을 푼다(Shift/Ctrl 이면 그대로 둔다).
      if (!drag.moved && !drag.additive) clearSelection()
      markSelection()
      updateStatus()
      return
    }
    clearDragOverlap()
    const entries = drag.ids
      .map((id) => ({ id, before: drag.befores.get(id) }))
      .filter((e) => !sameGeometry(e.before, S.items.get(e.id)))
    if (drag.moved && entries.length) {
      commit(entries)
      markOverlaps()
    } else if (!drag.moved && drag.collapse) {
      select(drag.id)
      return
    }
    updateStatus()
  }
  svg.onlostpointercapture = () => { if (S.drag) svg.onpointerup({ pointerId: S.drag.pointerId }) }
  // Ctrl+휠(터치패드 오므리기 포함)은 마우스 자리를 축으로 확대·축소. 확대 중에는 휠로 화면을 옮기고,
  // 끝에 닿으면 페이지가 굴러가게 둔다. 전체 보기에서는 휠을 건드리지 않는다.
  svg.onwheel = (event) => {
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()
      zoomAt(S.view.z * Math.exp(-event.deltaY * unit * 0.002), toUser(event))
      return
    }
    if (S.view.z <= 1) return
    const upp = unitsPerPx()
    const dx = (event.shiftKey ? event.deltaY : event.deltaX) * unit * upp
    const dTop = (event.shiftKey ? 0 : event.deltaY) * unit * upp
    if (panBy(dx, dTop)) event.preventDefault()
  }
  svg.onblur = () => { S.spaceDown = false; svg.classList.remove('is-pan-ready') }
  // 단축키는 편집기 어디에 포커스가 있어도 듣는다(툴바 단추를 누른 뒤에도). 입력 칸에서는 비킨다.
  host.onkeyup = (event) => {
    if (event.key === ' ') { S.spaceDown = false; svg.classList.remove('is-pan-ready') }
  }
  host.onkeydown = (event) => {
    if (event.key === 'Escape' && S.drag) { event.preventDefault(); cancelDrag(); return }
    const typing = event.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)
    const ctrl = event.ctrlKey || event.metaKey
    if (ctrl && event.key.toLowerCase() === 'z' && !typing) { event.preventDefault(); undo(); return }
    if (typing) return
    if (event.key === ' ' && event.target === svg) {
      event.preventDefault()
      S.spaceDown = true
      svg.classList.add('is-pan-ready')
      return
    }
    if (ctrl && event.key.toLowerCase() === 'a') {
      // 이 층 도면의 것을 모두 고른다(편집기 안에 포커스가 있을 때만 — 페이지 전체 선택을 막지 않는다).
      event.preventDefault()
      const all = [...S.items.values()].filter(onCanvas).map((m) => m.id)
      setSelection(all, all[all.length - 1])
      return
    }
    if (!ctrl && (event.key === '+' || event.key === '=')) { event.preventDefault(); zoomAt(S.view.z * ZOOM_STEP); return }
    if (!ctrl && event.key === '-') { event.preventDefault(); zoomAt(S.view.z / ZOOM_STEP); return }
    if (!ctrl && event.key === '0') { event.preventDefault(); zoomAt(1); return }
    if (event.key === 'Escape' && S.selection.size) { event.preventDefault(); select(null); return }
    if (S.drag) return
    const chosen = selectedItems()
    const standing = chosen.filter(onCanvas)
    // 지우기는 도면에 포커스가 있을 때만 — 툴바 단추를 누른 뒤 Backspace 가 고른 것을 지우지 않게.
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (!chosen.length || event.target !== svg) return
      event.preventDefault()
      removeItems(chosen)
      return
    }
    if (!standing.length) return
    const unit = S.step * (event.shiftKey ? 5 : 1)
    const arrows = { ArrowLeft: [-unit, 0], ArrowRight: [unit, 0], ArrowUp: [0, unit], ArrowDown: [0, -unit] }
    if (arrows[event.key]) {
      event.preventDefault()
      const [ax, ay] = arrows[event.key]
      // Ctrl+방향키는 크기 — 고른 것마다 오른쪽 폭, 위 높이(왼쪽 아래 모서리는 그대로).
      if (ctrl) setSizes(standing, (m) => ({ w: m.w + ax, h: m.h + ay }))
      else moveItems(expanded(standing), ax, ay)
    }
  }

  for (const input of fieldInputs) {
    input.onchange = () => {
      const chosen = selectedItems()
      const standing = chosen.filter(onCanvas)
      const value = Number(input.value)
      if (!standing.length || standing.length !== chosen.length || input.value === '' || !Number.isFinite(value)) {
        syncInspector()
        return
      }
      const field = input.dataset.field
      const together = expanded(standing)
      const box = bbox(together)
      const single = standing.length === 1 ? standing[0] : null
      if (field === 'x') moveItems(together, value - (single ? single.x : box.minX), 0)
      else if (field === 'y') moveItems(together, 0, value - (single ? single.y : box.minY))
      else setSizes(standing, () => ({ [field]: value }))
    }
    input.onkeydown = (event) => { if (event.key === 'Enter') input.blur() }
  }
  const selectedMark = () => {
    const chosen = selectedItems()
    return chosen.length === 1 && isMark(chosen[0]) ? chosen[0] : null
  }
  markLabel.onchange = () => {
    const mark = selectedMark()
    const value = markLabel.value.trim().slice(0, 40)
    if (mark && value !== (mark.label || '')) setMarkProps(mark, { label: value })
  }
  markLabel.onkeydown = (event) => { if (event.key === 'Enter') markLabel.blur() }
  markColor.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { color: markColor.value }) }
  markHatch.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { hatch: markHatch.checked }) }
  markKeepOut.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { keepOut: markKeepOut.checked }) }
  markRotate.onclick = () => { const mark = selectedMark(); if (mark) rotateMark(mark) }
  for (const button of host.querySelectorAll('.sle-palette [data-kind]')) {
    const kind = button.dataset.kind
    button.onpointerdown = (event) => ghostDrag(event, MARK_KINDS[kind].name, (p) => addMark(kind, p), () => addMark(kind))
  }

  // ---------------------------------------------------------------- 편집기에서 호기 추가
  // 적용 전까지는 이 편집기 안에만 있다(층 미정·미배치). 호기 마스터가 꼭 요구하는 값만 받는다 — 공정·라인·
  // 활용·크기, 그리고 신규 설비면 입고·Qual 일정과 확정상태(기존 설비는 일정이 없어도 된다). 다른 호기의
  // 일정·확정상태를 베끼지 않는다. 마스터의 나머지 칸은 가용설비에서 채운다.
  const fillSelect = (node, values, blank) => {
    const wanted = [blank === undefined ? null : blank, ...values].filter((v) => v !== null)
    if ([...node.options].map((o) => o.value).join('|') === wanted.join('|')) return
    node.replaceChildren(...wanted.map((v) => new Option(v === '' ? '(비움)' : v, v)))
  }
  fillSelect(newProcess, (NEW_UNIT.processes || []).map(String))
  fillSelect(newLine, (NEW_UNIT.lines || []).map(String), '')
  fillSelect(newUse, (NEW_UNIT.uses || []).map(String), '')
  fillSelect(newConfirm, (NEW_UNIT.confirmations || ['계획']).map(String))
  newKind.onchange = () => { newDates.hidden = newKind.value === 'existing' }
  newDates.hidden = newKind.value === 'existing'
  const sizeHint = () => {
    const hint = (NEW_UNIT.sizeHints || {})[newProcess.value]
    return Array.isArray(hint) && hint.length === 2 ? hint : [defaultSize.w, defaultSize.h]
  }
  const showHint = () => { const [w, h] = sizeHint(); newW.placeholder = String(w); newH.placeholder = String(h) }
  showHint()
  newProcess.onchange = showHint
  addToggle.onclick = () => {
    addForm.hidden = !addForm.hidden
    addToggle.setAttribute('aria-expanded', String(!addForm.hidden))
    if (!addForm.hidden) newId.focus()
  }
  q('.sle-addunit-close').onclick = () => { addForm.hidden = true; addToggle.setAttribute('aria-expanded', 'false') }
  addForm.onsubmit = (event) => {
    event.preventDefault()
    const id = newId.value.replace(/[\u0000-\u001f\u007f-\u009f\u00a0\u1680\u2000-\u200f\u2028-\u202f\u205f\u3000\ufeff]/g, ' ').replace(/ {2,}/g, ' ').trim()
    const [hintW, hintH] = sizeHint()
    const w = newW.value === '' ? hintW : roundTo(Number(newW.value))
    const h = newH.value === '' ? hintH : roundTo(Number(newH.value))
    let error = ''
    if (!id) error = '호기를 적어 주세요.'
    else if (EXISTING_IDS.has(id) || S.items.has(id)) error = `${id} 는 이미 있는 호기입니다.`
    else if (!newProcess.value) error = '공정을 골라 주세요.'
    else if (!(w > 0 && h > 0 && w <= MAX_EXTENT && h <= MAX_EXTENT)) error = `크기는 0 보다 크고 ${MAX_EXTENT} 이하여야 합니다.`
    const existing = newKind.value === 'existing'
    if (!error && !existing && (!newArrival.value || !newQual.value)) error = '신규 설비는 입고일정과 Qual일정이 필요합니다(기존 설비는 없어도 됩니다).'
    else if (!error && !existing && newQual.value < newArrival.value) error = 'Qual일정은 입고일정보다 빠를 수 없습니다.'
    newError.textContent = error
    if (error) return
    const item = {
      id, kind: 'unit', label: id, stage: existing ? '가용' : '입고 예정', group: null, x: NaN, y: NaN, w, h,
      placed: false, moveTo: null, isNew: true, arrived: false, floorless: true, sizeGuessed: false,
      created: {
        process: newProcess.value, line: newLine.value, use: newUse.value, existing,
        arrival: existing ? '' : newArrival.value, qual: existing ? '' : newQual.value, confirm: existing ? '' : newConfirm.value,
      },
    }
    S.items.set(id, item)
    pushUndo([{ op: 'create', id }])
    newId.value = ''
    newW.value = ''
    newH.value = ''
    renderItems()
    setSelection([id], id)
  }

  // ---------------------------------------------------------------- 단추
  moveButton.onclick = () => sendItems(selectedItems(), moveSelect.value)
  const areaValue = (input, current) => {
    const value = input.value === '' ? NaN : Number(input.value)
    if (!Number.isFinite(value)) { input.value = current; return null }
    return value
  }
  areaW.onchange = () => { const v = areaValue(areaW, W()); if (v !== null) setCanvas(v, H()) }
  areaH.onchange = () => { const v = areaValue(areaH, H()); if (v !== null) setCanvas(W(), v) }
  // Enter 로 바로 반영한다(숫자 칸은 Enter 만으로는 change 가 안 나는 경우가 있다).
  for (const input of [areaW, areaH]) input.onkeydown = (event) => { if (event.key === 'Enter') input.blur() }
  for (const button of host.querySelectorAll('[data-area]')) {
    button.onclick = () => {
      const [axis, delta] = [button.dataset.area[0], Number(button.dataset.area.slice(1))]
      if (axis === 'w') setCanvas(W() + delta, H())
      else setCanvas(W(), H() + delta)
    }
  }
  q('.sle-area-fit').onclick = () => {
    const ext = extents()
    setCanvas(Math.ceil(ext.right), Math.ceil(ext.top))
  }
  zoomOut.onclick = () => zoomAt(S.view.z / ZOOM_STEP)
  zoomIn.onclick = () => zoomAt(S.view.z * ZOOM_STEP)
  zoomFit.onclick = () => zoomAt(1)
  zoomSel.onclick = () => {
    const list = expanded(selectedItems())
    if (list.length) zoomToBox(bbox(list))
  }
  undoButton.onclick = undo
  unplaceButton.onclick = () => removeItems(selectedItems())
  q('.sle-reset').onclick = () => {
    initFromData()
    S.canvas = { ...S.originalCanvas }
    S.undo = []
    clearSelection()
    S.note = ''
    drawStatic()
    renderItems()
    updateStatus()
  }
  for (const button of host.querySelectorAll('.sle-steps button')) {
    button.onclick = () => { S.step = Number(button.dataset.step); updateStatus() }
  }
  applyButton.onclick = () => {
    const unitChanges = changes()
    const marksChanged = markChangeCount() > 0
    if (!unitChanges.length && !marksChanged && !canvasChanged()) return
    setTriggerValue('apply', {
      epoch: S.epoch,
      changes: unitChanges,
      canvas: canvasChanged() ? { width: W(), height: H() } : null,
      marks: marksChanged ? marksPayload() : null,
    })
  }
  updateStatus()
}
