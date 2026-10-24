export default function (component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component
  const host = parentElement.querySelector('.sle')
  if (!host || !data) return
  const NS = 'http://www.w3.org/2000/svg'
  const S = host.__sle || (host.__sle = {
    epoch: null, items: new Map(), ghosts: new Map(), original: new Map(), originalMarkIds: new Set(), groups: new Map(), undo: [],
    selected: null, selection: new Set(), step: 0.5, drag: null, overlapPairs: 0, blocked: 0,
    canvas: null, originalCanvas: null, note: '', view: { z: 1, x: 0, top: 0 }, spaceDown: false, seq: 0,
    passthrough: [], bgImage: null,
    // 기준일. asOf = 지금 칠한 날, dataAsOf = 파이썬이 쥔 날(상태 이름·범례·요약의 날), sent = 보냈는데 아직 회차로
    // 돌아오지 않은 날들. 페이더를 끄는 동안(faderBusy)과 키 입력이 멈추기를 기다리는 동안(commitTimer)은 회차가
    // 와도 브라우저가 쥔 날을 지킨다.
    asOf: '', dataAsOf: '', sent: new Set(), lastSent: '', faderTarget: '', faderFrame: 0, faderBusy: false,
    commitTimer: 0, faderKey: '',
    // 서랍에서 놓은 호기 id(놓은 차례) — 크기 없는 호기가 같은 앞 3자리 설비의 크기를 빌릴 때 본다(`recentSizes`).
    // 서랍 Shift 범위의 기준 칩(`trayAnchor`), 도면 요소 붙여넣기의 비켜 놓기 차례(`pasteSerial`), 상태 줄 한 줄 알림(`flash`).
    placedLog: [], trayAnchor: null, pasteSerial: 0, flash: '', hover: null, guideTimer: 0,
    // Main 설비 모듈 묶음 이름표 위치(묶음 열쇠 `groupKeyOf` → 'center'·'top'·'bottom', 없으면 그 모양의 처음 위치)와 처음 값.
    groupLabels: new Map(), originalGroupLabels: new Map(),
    // 층 상세 보기: 겹쳐 숨긴 반입 예정 호기(id → 설비지분, `paintUnit`)와 아래 호기 표에 고른 호기 — 파이썬이 쥔 값
    // (`data.picked`, 받은 그대로 `pickData`)과 브라우저가 보낸 값(`pickSent`).
    covered: new Map(), pickData: undefined, pickSent: null,
  })
  // 보기 전용(Space 층 상세 뷰어). 같은 도면을 그리되 편집 도구를 숨기고, 끌기는 화면 이동,
  // 누르기는 그 호기의 정보 한 줄이다.
  const VIEW = data.mode === 'view'
  host.classList.toggle('is-view', VIEW)
  // 범위(층·FAB). 브라우저가 기억하는 뷰어 높이를 범위마다 따로 둔다.
  const SCOPE = data.scope === 'fab' ? 'fab' : 'floor'
  // FAB 전체 도면. 층 블록(kind 'block')은 이 범위에만 있고, 보기 전용에서 누르면 연결된 층이 열린다.
  const FAB = SCOPE === 'fab'
  host.classList.toggle('is-fab', FAB)
  // 블록 글자(배치·미배치 대수, 점유율). epoch 밖이라 같은 epoch 회차에도 새 값으로 다시 쓴다.
  const LINK_STATS = data.linkStats || {}
  const palette = data.palette || {}
  // 팔레트(테마)는 바뀐 회차에만 다시 단다 — 같은 값을 다시 달아도 도면 전체의 스타일 계산이 다시 돌 수 있다.
  const paletteKey = JSON.stringify(palette)
  if (S.paletteKey !== paletteKey) {
    S.paletteKey = paletteKey
    for (const [name, value] of Object.entries(palette)) host.style.setProperty('--sle-' + name, String(value))
  }
  const DECIMALS = Number.isInteger(data.decimals) ? data.decimals : 1
  const SCALE = 10 ** DECIMALS
  const MIN_EXTENT = Number(data.canvasLimits?.min) || 10
  const MAX_EXTENT = Number(data.canvasLimits?.max) || 400
  // 편집기에 안 나오지만 이 층에 좌표가 있는 호기가 차지한 범위. 영역은 이보다 줄지 않는다.
  const RESERVED = { right: Number(data.canvasLimits?.reservedW) || 0, top: Number(data.canvasLimits?.reservedH) || 0 }
  const FLOOR = String(data.floor || '')
  const OTHER_FLOORS = (Array.isArray(data.floors) ? data.floors : []).map(String).filter((f) => f !== FLOOR)
  // FAB 편집에서 층 블록이 가리킬 수 있는 층(「C1 1F」, 30개). 층 범위에는 없다.
  const LINK_TARGETS = (Array.isArray(data.linkTargets) ? data.linkTargets : []).map(String)
  const markColors = data.markColors || {}
  // 기준일(T, `YYYY-MM-DD`). 호기마다 받은 경계 날짜와 **글자로** 견주어 실물·반출/이설 예정·정지 중·지연·운영
  // 비가동을 정한다 — 파이썬 `services/space_unit_state.unit_states_at` 과 같은 판정이다(시험이 같은 식으로 대조한다).
  // 날짜는 epoch 에 넣지 않는다 — data 의 `asOf` 는 새 epoch 에서 쓰고, 같은 epoch 회차에는 `adoptAsOf` 가 가른다.
  const AS_OF = typeof data.asOf === 'string' ? data.asOf : ''
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/
  const dayOr = (value) => (typeof value === 'string' && ISO_DAY.test(value) ? value : null)
  const hexOr = (value) => (typeof value === 'string' && HEX_COLOR.test(value) ? value : '')
  const spansOf = (value) => (Array.isArray(value) ? value : [])
    .filter((span) => Array.isArray(span) && dayOr(span[0]))
    .map((span) => [span[0], dayOr(span[1])])
  // 기준일 페이더(층 상세 보기, 도면 상자 맨 위 줄)의 오늘·범위(양 끝 포함). 범위는 파이썬
  // `space_unit_state.as_of_range`(오늘 ±12개월)가 정해 보낸다. 배치 편집(층) 중에는 같은 자리에 「편집 중 고정」 줄이
  // 선다. FAB 전체에는 페이더가 없고 도구 줄에 기준일·「오늘로」가 선다.
  const TODAY = dayOr(data.today) || ''
  const RANGE = { min: dayOr(data.asOfMin) || '', max: dayOr(data.asOfMax) || '' }
  const FADER = VIEW && !FAB && Boolean(TODAY && RANGE.min && RANGE.max && RANGE.min <= TODAY && TODAY <= RANGE.max)
  const PINNED = !VIEW && !FAB
  // 키로 옮긴 기준일은 멈춘 뒤 이만큼 지나 한 번 보낸다(누를 때마다 회차를 돌리지 않게).
  const KEY_COMMIT_MS = 400
  // 페이더 손잡이 지름(px, CSS `.sle-fader-input` 의 thumb 와 같다). 눈금 자리를 손잡이 가운데와 맞춘다.
  const THUMB_PX = 14
  // 날은 UTC 자정의 날 번호(1970-01-01 = 0)로 센다. 글자 `YYYY-MM-DD` 와 서로 바꾼다.
  const DAY_MS = 864e5
  const dayNumber = (iso) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / DAY_MS
  const isoOf = (n) => new Date(n * DAY_MS).toISOString().slice(0, 10)
  // 달력 달 더하기 — 그 날이 없는 달이면 그달 말일(파이썬 `pd.DateOffset(months=…)` 과 같다).
  function addMonths(n, k) {
    const d = new Date(n * DAY_MS)
    const year = d.getUTCFullYear()
    const month = d.getUTCMonth() + k
    const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
    return Date.UTC(year, month, Math.min(d.getUTCDate(), last)) / DAY_MS
  }
  const defaultSize = data.defaultSize || { w: 12, h: 7 }
  const NEW_UNIT = data.newUnit || {}
  const EXISTING_IDS = new Set((NEW_UNIT.existingIds || []).map(String))
  // 앞 3자리 → 편집본에서 설비명 자연 정렬이 가장 뒤인 같은 앞 3자리 설비의 크기({unit|module: {앞 3자리: {name, w, h}}},
  // 파이썬 `prefix_sizes`). 서랍에서 크기 없는 호기를 놓을 때 빌린다(`borrowedSize`).
  const PREFIX_SIZES = NEW_UNIT.prefixSizes && typeof NEW_UNIT.prefixSizes === 'object' ? NEW_UNIT.prefixSizes : {}
  // 모듈 묶음의 Main 설비(편집본 전체에서 행이 둘 이상, 파이썬 `module_parents`) — 크기 불러오기의 종류(`sizeKind`).
  const MODULE_PARENTS = new Set((Array.isArray(NEW_UNIT.moduleParents) ? NEW_UNIT.moduleParents : []).map(String))
  const MAX_ZOOM = 8
  const ZOOM_STEP = 1.25
  const DRAG_THRESHOLD_PX = 3
  const HANDLE_PX = 9
  // 보기 화면 덧표시(화면 px) — 선택 후광의 띄움, 「!」·운영 비가동 표식의 반지름, 겹침 꼭지 삼각의 변.
  const HALO_GAP_PX = 3
  const BADGE_PX = 7
  const CORNER_PX = 11
  const GROUP_PAD = 0.6
  // 서랍이 무대 가장자리에서 들어앉은 거리(CSS `.sle-drawer` 의 8px). 놓은 호기를 서랍 왼쪽으로 이만큼 더 꺼낸다.
  const DRAWER_INSET_PX = 8
  // 편집 영역 둘레의 여백(영역 긴 변의 비율). 전체 보기는 영역+여백이 다 보이는 크기다.
  const VIEW_MARGIN = 0.03
  // 무대 높이(px). 기본은 화면에 맞추고(MIN_DEFAULT_H 이상), 손잡이로는 MIN_DRAG_H ~ 화면 높이의 MAX_H_RATIO 배.
  const MIN_DEFAULT_H = 320
  const MIN_DRAG_H = 280
  const MAX_H_RATIO = 1.5
  // 보기 화면에서 무대 위·아래에 서는 것(앱 머리·제목·경로·머리 줄·도구 줄, 아래 손잡이·여유)의 몫. 무대의 실제
  // 위치로 재지 않는다 — 편집 화면은 위에 도구가 더 서서 같은 식이면 보기보다 낮아지는데, 보기·편집의 도면
  // 상자 크기는 같아야 한다. 층 도면(보기·편집)은 맨 위에 기준일 줄(보기 페이더 · 편집 「편집 중 고정」, 같은 높이
  // DATE_ROW_PX)과 그 아래 틈(8px, `.sle` gap)이 더 서고, FAB 에는 없다.
  const VIEW_CHROME_PX = 320
  const DATE_ROW_PX = 36
  const CHROME_PX = VIEW_CHROME_PX + (FAB ? 0 : DATE_ROW_PX + 8)
  const HEIGHT_KEY_STEP = 20
  const HEIGHT_STORE_KEY = `capa.space.viewerHeight.${SCOPE}`
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
    // FAB 층 블록. 연결(link, 「C1 1F」)이 필수다. 색은 사용자가 고르는 자리 구분 색이고 빈 값은 Space 기본 면이다.
    block: { name: '층 블록', size: [16, 6], label: '', rotatable: false },
  }
  // 이 범위에서 그리는 종류. 층 블록은 FAB 에만 있다 — 층 도면에 오면 그리지 않고 그대로 돌려보낸다.
  const drawable = (kind) => Boolean(MARK_KINDS[kind]) && (kind !== 'block' || FAB)
  const ZONE_COLOR_NAMES = { blue: '파랑', green: '초록', violet: '보라', sky: '하늘', rose: '분홍', gray: '회색' }
  // 요소 이름표의 글자 크기(화면 px)·색. 크기 null 은 「자동」(글자 요소는 상자에 맞추고 나머지는 LABEL_PX),
  // 색 '' 은 기본 글자색(--sle-mark-ink)이다. 색 키는 영역 색과 같고 실제 색은 팔레트의 mark-text-<키> 다.
  const FONT_SIZES = (Array.isArray(data.fontSizes) ? data.fontSizes : [9, 11, 13, 16, 20, 24]).map(Number)
  const LABEL_PX = 11
  const fontSizeOf = (raw) => (raw === null || raw === undefined || raw === '' || !FONT_SIZES.includes(Number(raw)) ? null : Number(raw))
  // 영역 테두리 모양·이름표 정렬(2026-10-23 사용자 요청). 첫 값이 처음 값 — 지금 모습(점선, 왼쪽 위 꼬리표)이다. 파이썬
  // `floor_layout_mark.ZONE_BORDER_STYLES`·`ZONE_LABEL_ALIGNS` 와 같다.
  const BORDER_STYLES = ['dashed', 'solid']
  const LABEL_ALIGNS = ['left', 'center', 'right']
  const pickOr = (value, allowed) => (allowed.includes(value) ? value : allowed[0])
  // Main 설비 모듈 묶음 이름표 위치 — 범위 정가운데·범위 바깥 바로 위·아래(파이썬 `GROUP_LABEL_POSITIONS`). 고른 적이 없는
  // 묶음은 모양에 따라 가운데(두 줄 이상) 또는 위(한 줄 — 모듈 2·3)다(`groupLabelDefault`).
  const GROUP_LABEL_POSITIONS = ['center', 'top', 'bottom']
  // Main 설비명 글자의 가장 큰 크기(화면 px). 범위에 맞춰 줄고 UNIT_LABEL_MIN_PX 아래면 숨긴다(모듈 이름표와 같은 규칙 —
  // 다만 모듈 칸 이름표가 하나도 서 있지 않은 묶음의 가운데 이름은 그 크기로라도 선다, `groupNameSize`).
  const GROUP_NAME_PX = 12
  // 호기 이름표의 가장 작은 크기(화면 px) — 이보다 작으면 숨긴다(밀집 층, 확대하면 다시 보인다).
  const UNIT_LABEL_MIN_PX = 7
  const fontInk = (item) => (item.fontColor && markColors[item.fontColor] ? `var(--sle-mark-text-${item.fontColor})` : '')
  const HINT = FAB
    ? '층 블록·영역·글자를 끌어 옮기고 손잡이로 크기를 바꿉니다. 층 블록의 연결 층·색은 아래 선택 칸에서 고릅니다 · 끌면 다른 것의 변·가운데 선에 붙습니다(Alt 누른 채면 안 붙음) · 빈 곳을 끌거나 Shift/Ctrl+클릭으로 여러 개 · Ctrl+C/V 복사·붙여넣기 · Ctrl+휠 확대 · Space+끌기 화면 이동 · 방향키 이동 · Ctrl+Z 실행 취소'
    : '호기·요소를 끌어 옮기고, 고른 것의 모서리·변 손잡이로 크기를 바꿉니다. Main 설비 모듈 묶음은 묶음 범위만 옮기고 키웁니다(안은 바둑판 자동 배치). 끌면 다른 것의 변·가운데 선에 붙습니다(Alt 누른 채면 안 붙음) · 빈 곳을 끌거나 Shift/Ctrl+클릭으로 여러 개 · Ctrl+A 전체 · Ctrl+C/V 도면 요소 복사·붙여넣기 · Ctrl+휠 확대 · Space+끌기 화면 이동 · 방향키 이동 · Ctrl+방향키 크기 · Ctrl+Z 실행 취소'

  const q = (selector) => host.querySelector(selector)
  // 글자·속성은 바뀐 때만 쓴다 — 같은 값을 다시 써도 그 줄의 배치·칠이 다시 돈다(회차·페이더 프레임마다 부른다).
  const setText = (node, text) => { if (node.textContent !== text) node.textContent = text }
  const setAttr = (node, name, value) => { if (node.getAttribute(name) !== value) node.setAttribute(name, value) }
  const svg = q('.sle-canvas')
  const bg = svg.querySelector('.sle-bg')
  const grid = svg.querySelector('.sle-grid')
  const zonesLayer = svg.querySelector('.sle-zones')
  const layer = svg.querySelector('.sle-items')
  const marksLayer = svg.querySelector('.sle-marks')
  const namesLayer = svg.querySelector('.sle-group-names')
  const overlay = svg.querySelector('.sle-overlay')
  const guidesLayer = svg.querySelector('.sle-guides')
  const stage = q('.sle-stage')
  const resizeHandle = q('.sle-resize')
  const drawer = q('.sle-drawer')
  const drawerTab = q('.sle-drawer-tab')
  const drawerCount = q('.sle-drawer-count')
  const trayBox = q('.sle-tray')
  const trayList = q('.sle-tray-list')
  const trayCount = q('.sle-tray-count')
  const traySearch = q('.sle-tray-search')
  const trayEmpty = q('.sle-tray-empty')
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
  const unitLabel = q('.sle-unit-label')
  const moveSelect = q('.sle-move-floor')
  const moveButton = q('.sle-move')
  const moduleTile = q('.sle-module-tile')
  const groupNameBox = q('.sle-group-name')
  const groupNamePos = q('.sle-group-label-pos')
  const markProps = q('.sle-markprops')
  const markLabel = q('.sle-mark-label')
  const markFontSize = q('.sle-mark-font-size')
  const markFontColor = q('.sle-mark-font-color')
  const markColor = q('.sle-mark-color')
  const markBorder = q('.sle-mark-border')
  const markAlign = q('.sle-mark-align')
  const markHatch = q('.sle-mark-hatch')
  const markKeepOut = q('.sle-mark-keepout')
  const markRotate = q('.sle-mark-rotate')
  const zoneOnly = [...host.querySelectorAll('.sle-zone-only')]
  const blockProps = q('.sle-block-props')
  const blockLink = q('.sle-block-link')
  const blockColor = q('.sle-block-color')
  const blockOpen = q('.sle-block-open')
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
  const newConfirmRow = newConfirm.closest('.sle-form-row')
  setText(q('.sle-title'), data.title || '')
  const pickBox = q('.sle-pick')
  const pickHint = FAB
    ? '층 블록을 누르면 그 층이 열립니다 · Tab 으로 블록을 고르고 Enter · Ctrl+휠 확대 · 확대 뒤 끌어서 화면 옮기기'
    : '호기를 누르면 정보가 여기 뜨고 아래 표가 그 설비 줄만 보입니다 · Ctrl+휠 확대 · 끌어서 이동 · 더블클릭 확대/전체 보기'
  if (pickBox.dataset.hint !== pickHint) pickBox.dataset.hint = pickHint
  setAttr(svg, 'aria-label', !VIEW ? '층 배치 도면 편집기' : FAB ? 'S.PKG FAB 전체 배치도' : '층 배치 도면')

  const num = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v))
  const roundTo = (v) => Math.round(v * SCALE) / SCALE
  // 상한은 바깥으로 넘지 않게 내린다 — 반올림이 캔버스 밖으로 0.05 를 밀어내면 저장 검사가 마스터 전체를 막는다.
  const floorTo = (v) => Math.floor(v * SCALE + 1e-9) / SCALE
  const ceilTo = (v) => Math.ceil(v * SCALE - 1e-9) / SCALE
  const snapDelta = (d) => Math.round(d / S.step) * S.step
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi))
  // 가장 작은 크기는 저장 정밀도 한 칸이다. 격자 간격에 묶으면 격자 2 에서 1.5 기둥이 건드리기만 해도 커진다.
  const minSize = () => 1 / SCALE

  // ---------------------------------------------------------------- 모듈 묶음 바둑판(순수 함수)
  // 파이썬 `services/space_layout_edit` 의 `module_grid`·`natural_name_key`·`module_cells`·`tile_module_group`·
  // `assign_module_cells`·`module_tile_deviation`·`default_group_label` 과 같은 규칙이다 — `tests/test_space_module_group.py` 가 아래 두 표시 줄
  // 사이를 떼어 node 로 돌려 파이썬과 대조하고 칸 배정·다시 놓기 판단을 시험한다. 그래서 바깥 이름을 쓰지 않는다(정밀도
  // `scale` 도 인자다). 한쪽을 고치면 다른 쪽도 고친다.
  // <module-tiling>
  // 모듈 수 → [열, 행]. 셋까지는 가로 한 줄(열 n·행 1 — 둘이면 2×1, 셋이면 3×1), 넷부터는 거의 정사각 격자(열 = ⌈√n⌉,
  // 행 = ⌈n ÷ 열⌉ — 넷이면 2×2, 다섯이면 3×2).
  function moduleGrid(count) {
    if (count <= 3) return [Math.max(1, count), 1]
    const cols = Math.ceil(Math.sqrt(count))
    return [cols, Math.ceil(count / cols)]
  }
  // Main 설비명 위치를 고른 적이 없는 모듈 묶음의 위치 — 한 줄 묶음(행 1, 모듈 2·3)은 범위 바깥 위(가운데는 가운데 모듈
  // 이름표와 겹친다), 두 줄 이상은 범위 정가운데.
  const groupLabelDefault = (count) => (moduleGrid(count)[1] === 1 ? 'top' : 'center')
  // 글자를 코드 포인트로 견준다 — 파이썬 글자 비교와 같다(UTF-16 단위로 견주면 BMP 밖 글자에서 갈린다).
  function codeCompare(a, b) {
    const pa = Array.from(a)
    const pb = Array.from(b)
    for (let i = 0; i < Math.min(pa.length, pb.length); i += 1) {
      if (pa[i] !== pb[i]) return pa[i].codePointAt(0) - pb[i].codePointAt(0)
    }
    return pa.length - pb.length
  }
  // 설비명 자연 정렬(…12A, 12B, 12C, 12D). 숫자 덩이(0-9)는 수로, 나머지 덩이는 소문자로 견주고, 덩이가 같으면 짧은 쪽이
  // 앞, 그래도 같으면 글자 그대로 견준다.
  function naturalCompare(a, b) {
    const ta = a.match(/[0-9]+|[^0-9]+/g) || []
    const tb = b.match(/[0-9]+|[^0-9]+/g) || []
    for (let i = 0; i < Math.min(ta.length, tb.length); i += 1) {
      const da = ta[i][0] >= '0' && ta[i][0] <= '9'
      const db = tb[i][0] >= '0' && tb[i][0] <= '9'
      if (da !== db) return da ? -1 : 1
      if (da) {
        const na = ta[i].replace(/^0+/, '')
        const nb = tb[i].replace(/^0+/, '')
        if (na.length !== nb.length) return na.length - nb.length
        if (na !== nb) return na < nb ? -1 : 1
        continue
      }
      const la = ta[i].toLowerCase()
      const lb = tb[i].toLowerCase()
      if (la !== lb) return codeCompare(la, lb)
    }
    if (ta.length !== tb.length) return ta.length - tb.length
    return codeCompare(a, b)
  }
  // 저장 정밀도 눈금(정수). 반올림은 파이썬과 같은 ⌊v × scale + 0.5⌋ 다(`Math.round` 와 끝이 다를 수 있어 쓰지 않는다).
  const tickOf = (v, scale) => Math.floor(v * scale + 0.5)
  const boxTicks = (box, scale) => [tickOf(box.x, scale), tickOf(box.y, scale), tickOf(box.w, scale), tickOf(box.h, scale)]
  const tickBox = (t, scale) => ({ x: t[0] / scale, y: t[1] / scale, w: t[2] / scale, h: t[3] / scale })
  // 눈금 상자들의 바깥 상자 [왼쪽, 바닥, 폭, 높이].
  function outerTicks(list) {
    const left = Math.min(...list.map((t) => t[0]))
    const bottom = Math.min(...list.map((t) => t[1]))
    return [left, bottom, Math.max(...list.map((t) => t[0] + t[2])) - left, Math.max(...list.map((t) => t[1] + t[3])) - bottom]
  }
  // 눈금 범위를 count 칸 바둑판(열×행)으로 똑같이 나눈 칸 — 칸 번호 차례(왼→오, 위→아래)의 눈금 상자. 칸은 범위 ÷ 열(행)의
  // 내림이고 마지막 열(오른쪽)·마지막 행(맨 아래)이 나머지를 받아 틈·겹침이 없다. 범위가 칸마다 한 눈금보다 작으면 오른쪽·위로
  // 넓힌다. 칸 수는 열×행이라 count 보다 많을 수 있다(남는 칸은 빈다).
  function cellTicks(box, count) {
    const [cols, rows] = moduleGrid(count)
    const left = box[0]
    const bottom = box[1]
    const width = Math.max(box[2], cols)
    const height = Math.max(box[3], rows)
    const cellW = (width - (width % cols)) / cols
    const cellH = (height - (height % rows)) / rows
    const lastW = width - cellW * (cols - 1)
    const lastH = height - cellH * (rows - 1)
    const cells = []
    for (let row = 0; row < rows; row += 1) {
      const y = row === rows - 1 ? bottom : bottom + lastH + (rows - 2 - row) * cellH
      const h = row === rows - 1 ? lastH : cellH
      for (let col = 0; col < cols; col += 1) cells.push([left + col * cellW, y, col === cols - 1 ? lastW : cellW, h])
    }
    return cells
  }
  // 범위 box {x, y, w, h} 를 count 칸으로 나눈 칸 [{x, y, w, h}](칸 번호 차례).
  function moduleCells(box, count, scale) {
    return cellTicks(boxTicks(box, scale), count).map((t) => tickBox(t, scale))
  }
  // 묶음을 **새로** 놓을 때(서랍)의 자리 — 범위 box 의 칸에 자연 정렬 차례로 하나씩([{name, x, y, w, h}], 첫 모듈 왼쪽 위).
  function tileModuleGroup(box, names, scale) {
    if (!names.length) return []
    const cells = moduleCells(box, names.length, scale)
    return [...names].sort(naturalCompare).map((name, index) => ({ name, ...cells[index] }))
  }
  // 자연 정렬 칸 배정 Map(이름 → 칸 번호) — 새로 놓을 때.
  const naturalSlots = (names) => new Map([...names].sort(naturalCompare).map((name, index) => [name, index]))
  // 묶음 모듈의 칸 배정 Map(이름 → 칸 번호) — **지금 자리를 지킨다**. mods 는 [{name, x, y, w, h, placed}]. 상자가 있는
  // 모듈(placed)의 바깥 상자를 모듈 수 바둑판으로 나눠, 상자 중심과 칸 중심의 거리(눈금 제곱)가 가까운 짝부터 묶는다 — 같으면
  // 자연 정렬 앞 모듈·앞 칸이 먼저다. 이미 바둑판이면 모듈마다 제 칸이다(차례가 이름순이 아니어도). 상자 없는 모듈은 남은 칸을
  // 자연 정렬 차례로 받는다.
  function assignModuleCells(mods, scale) {
    const order = [...mods].sort((a, b) => naturalCompare(a.name, b.name))
    const boxed = order.filter((m) => m.placed)
    const used = new Set()
    const slots = new Map()
    if (boxed.length) {
      const boxes = boxed.map((m) => boxTicks(m, scale))
      const cells = cellTicks(outerTicks(boxes), order.length)
      const pairs = []
      boxes.forEach(([x, y, w, h], index) => {
        cells.forEach(([cx, cy, cw, ch], number) => {
          const dx = 2 * x + w - (2 * cx + cw)
          const dy = 2 * y + h - (2 * cy + ch)
          pairs.push([dx * dx + dy * dy, index, number])
        })
      })
      pairs.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2])
      for (const [, index, number] of pairs) {
        if (slots.has(boxed[index].name) || used.has(number)) continue
        slots.set(boxed[index].name, number)
        used.add(number)
      }
    }
    let free = 0
    for (const m of order) {
      if (slots.has(m.name)) continue
      while (used.has(free)) free += 1
      slots.set(m.name, free)
      used.add(free)
    }
    return slots
  }
  // 묶음이 바둑판에서 얼마나 벗어났나(눈금) — 모두 상자가 있을 때 바깥 상자를 모듈 수 바둑판으로 나눈 칸(지금 자리 배정)과의
  // 가장 큰 차. 0 이면 바둑판 그대로, 상자 없는 모듈이 있으면 Infinity(파이썬은 None).
  function tileDeviation(mods, scale) {
    if (!mods.length || mods.some((m) => !m.placed)) return Infinity
    const boxes = mods.map((m) => boxTicks(m, scale))
    const cells = cellTicks(outerTicks(boxes), mods.length)
    const slots = assignModuleCells(mods, scale)
    let worst = 0
    mods.forEach((m, index) => {
      const cell = cells[slots.get(m.name)]
      for (let k = 0; k < 4; k += 1) worst = Math.max(worst, Math.abs(boxes[index][k] - cell[k]))
    })
    return worst
  }
  // 두 범위가 눈금까지 같은가.
  function sameTicks(a, b, scale) {
    const p = boxTicks(a, scale)
    const q = boxTicks(b, scale)
    return p.every((v, k) => v === q[k])
  }
  // 범위 box 의 칸에 배정 slots 대로 선 자리 [{name, x, y, w, h}].
  function layModuleGroup(box, names, slots, scale) {
    const cells = moduleCells(box, names.length, scale)
    return names.map((name) => ({ name, ...cells[slots.get(name)] }))
  }
  // 묶음 범위를 from 에서 to 로 바꾼 자리. 범위가 눈금까지 그대로면 null — 다시 놓지 않는다(벽에 막힌 방향키·제자리에서 뗀
  // 끌기·같은 숫자처럼 옮기거나 키우지 않은 조작이 바둑판이 아닌 옛 묶음을 바꾸지 않게. 다시 놓기만 하는 길은 「범위에 맞춰
  // n등분」 하나다).
  function relaidGroup(names, slots, from, to, scale) {
    return sameTicks(from, to, scale) ? null : layModuleGroup(to, names, slots, scale)
  }
  // 서랍에서 놓는 모듈 묶음의 범위 크기 {w, h} — 열 × 가장 큰 모듈 폭, 행 × 가장 큰 모듈 높이(칸이 모듈 크기의 최댓값).
  function trayModuleRange(sizes, scale) {
    const [cols, rows] = moduleGrid(sizes.length)
    const cellW = Math.max(...sizes.map((size) => tickOf(size.w, scale)))
    const cellH = Math.max(...sizes.map((size) => tickOf(size.h, scale)))
    return { w: (cols * cellW) / scale, h: (rows * cellH) / scale }
  }
  // </module-tiling>

  // ---------------------------------------------------------------- 편집 도구 판정(순수 함수)
  // 정렬선 붙임·앞 3자리 크기 불러오기·서랍 Shift 범위·도면 요소 붙여넣기 자리(2026-10-23 사용자 요청)의 판정이다.
  // `tests/test_space_editor_tools.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌려 시험한다(앞 3자리는 파이썬
  // `space_layout_edit.name_prefix` 와 대조). 그래서 바깥 이름을 쓰지 않는다(정밀도 `scale` 도 인자다).
  // <edit-tools>
  // 상자 {x, y, w, h} 의 세로 정렬선(왼·가운데·오른 x)과 가로 정렬선(아래·가운데·위 y — 데이터 Y 는 위로 간다).
  function linesX(b) {
    return [b.x, b.x + b.w / 2, b.x + b.w]
  }
  function linesY(b) {
    return [b.y, b.y + b.h / 2, b.y + b.h]
  }
  // 움직이는 선들(moving) 가운데 하나를 목표 선(targets)의 하나에 붙이는 이동량 — 거리가 tol 이하인 짝 가운데 가장 가까운
  // 것(같으면 먼저 본 짝). 없으면 null.
  function nearestSnap(moving, targets, tol) {
    let best = null
    for (const m of moving) {
      for (const t of targets) {
        const d = t - m
        if (Math.abs(d) <= tol && (best === null || Math.abs(d) < Math.abs(best))) best = d
      }
    }
    return best
  }
  // 그릴 정렬선 — 상자 box 의 선(useX·useY 는 쓸 선 번호: 0 왼·아래, 1 가운데, 2 오른·위) 가운데 다른 상자(others)의 어느
  // 선과 eps 안에서 같은 것. 세로선은 {axis: 'x', at, from, to}(from·to 는 데이터 Y), 가로선은 {axis: 'y', at, from, to}(X)이고
  // 길이는 box 와 그 선을 함께 쓰는 상자들을 모두 잇는다.
  function guideSegments(box, others, eps, useX = [0, 1, 2], useY = [0, 1, 2]) {
    const out = []
    const scan = (axis, at, lines, span, own) => {
      let from = own[0]
      let to = own[1]
      let hit = false
      for (const o of others) {
        if (!lines(o).some((v) => Math.abs(v - at) <= eps)) continue
        const [lo, hi] = span(o)
        from = Math.min(from, lo)
        to = Math.max(to, hi)
        hit = true
      }
      if (hit) out.push({ axis, at, from, to })
    }
    const xs = linesX(box)
    const ys = linesY(box)
    for (const k of useX) scan('x', xs[k], linesX, (o) => [o.y, o.y + o.h], [box.y, box.y + box.h])
    for (const k of useY) scan('y', ys[k], linesY, (o) => [o.x, o.x + o.w], [box.x, box.x + box.w])
    return out
  }
  // 설비명 앞 3자리 — 앞뒤 공백을 걷은 첫 세 글자(대소문자 그대로, 글자는 코드 포인트). 세 글자보다 짧으면 ''(빌리지 않는다).
  // 공백은 파이썬 `str.strip` 의 것(`str.isspace`)이다 — JS `trim` 은 BOM(U+FEFF)을 걷고 U+001C~U+001F·U+0085 를 남겨
  // 파이썬 `prefix_sizes` 의 열쇠와 어긋난다.
  function namePrefix(name) {
    const space = '[\\t\\n\\v\\f\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]'
    const chars = Array.from(String(name ?? '').replace(new RegExp(`^${space}+|${space}+$`, 'g'), ''))
    return chars.length >= 3 ? chars.slice(0, 3).join('') : ''
  }
  // 크기 없는 호기(name, 종류 kind: 'unit' 호기 · 'module' Main 설비 모듈)가 빌릴 크기 {from, w, h}. 같은 앞 3자리·같은 종류
  // 가운데 이번 편집에서 마지막으로 놓은 것(recent [{name, kind, w, h}] — 뒤가 나중), 없으면 편집본(저장본 + 저장 안 한 편집)에서
  // 설비명 자연 정렬이 가장 뒤인 것(saved[kind][앞 3자리] = {name, w, h}, 파이썬 `prefix_sizes`). 둘 다 없으면 null — 지금
  // 규칙(이 층 가운데 크기)으로 놓는다.
  function borrowedSize(name, kind, recent, saved) {
    const prefix = namePrefix(name)
    if (!prefix) return null
    const usable = (w, h) => Number.isFinite(w) && w > 0 && Number.isFinite(h) && h > 0
    for (let k = recent.length - 1; k >= 0; k -= 1) {
      const r = recent[k]
      if (r.kind === kind && namePrefix(r.name) === prefix && usable(r.w, r.h)) return { from: String(r.name), w: r.w, h: r.h }
    }
    const table = saved && Object.prototype.hasOwnProperty.call(saved, kind) ? saved[kind] : null
    const s = table && Object.prototype.hasOwnProperty.call(table, prefix) ? table[prefix] : null
    if (s && usable(Number(s.w), Number(s.h))) return { from: String(s.name), w: Number(s.w), h: Number(s.h) }
    return null
  }
  // 서랍 Shift 범위 — 칩 차례 order([{id, visible, ids}], 서랍 그대로)에서 기준 칩 anchor 부터 누른 칩 target 까지(양 끝 포함)
  // 지금 보이는 칩의 호기 id(묶음 칩은 한 칸 — 그 모듈 id 모두). 기준 칩이나 누른 칩이 목록에 없으면 null.
  function trayRangeIds(order, anchor, target) {
    const a = order.findIndex((chip) => chip.id === anchor)
    const b = order.findIndex((chip) => chip.id === target)
    if (a < 0 || b < 0) return null
    const [lo, hi] = a < b ? [a, b] : [b, a]
    return order.slice(lo, hi + 1).filter((chip) => chip.visible || chip.id === target).flatMap((chip) => chip.ids)
  }
  // 붙여넣기 이동량 {dx, dy} — 복사한 도면 요소들(원본 자리 [{x, y, w, h}])을 모양 그대로 옮긴다. at({x, y}, 데이터 좌표)이
  // 있으면 그 자리가 묶음의 왼쪽 아래(마우스 자리 — 부르는 쪽이 격자·정렬선을 맞춘 자리), 없으면 원본에서 offset 만큼 오른쪽·
  // 아래로 비킨다. 영역 canvas {w, h} 안으로 밀고 눈금(scale)에 맞춘다. 비켜 붙일 때 영역 끝에 막혀 한 축의 이동량이 0 이 되면
  // 그 축은 반대쪽(왼쪽·위)으로 같은 거리만큼 비킨다 — 영역 끝에 닿은 요소의 사본이 원본 자리에 그대로 쌓이지 않게. 두 축 모두
  // 움직일 수 없으면(영역을 가득 채운 묶음) {dx: 0, dy: 0} 이다. 묶음이 영역보다 크면 null.
  function pasteShift(marks, canvas, at, offset, scale) {
    if (!marks.length) return null
    const left = Math.min(...marks.map((m) => m.x))
    const bottom = Math.min(...marks.map((m) => m.y))
    const right = Math.max(...marks.map((m) => m.x + m.w))
    const top = Math.max(...marks.map((m) => m.y + m.h))
    if (right - left > canvas.w + 1e-9 || top - bottom > canvas.h + 1e-9) return null
    const tick = (v) => Math.round(v * scale) / scale + 0
    const fit = (v, lo, hi) => tick(Math.min(Math.max(v, lo), hi))
    if (at) return { dx: fit(at.x - left, -left, canvas.w - right), dy: fit(at.y - bottom, -bottom, canvas.h - top) }
    const away = (want, lo, hi) => {
      const v = fit(want, lo, hi)
      return v !== 0 ? v : fit(-want, lo, hi)
    }
    return { dx: away(offset, -left, canvas.w - right), dy: away(-offset, -bottom, canvas.h - top) }
  }
  // 새 층 블록 count 개의 연결 — 새 요소 넣기처럼 아직 블록이 가리키지 않는 층(taken 밖의 targets)을 차례로, 다 찼으면 첫 층.
  function freeLinks(count, taken, targets) {
    const used = new Set(taken)
    const out = []
    for (let k = 0; k < count; k += 1) {
      const link = targets.find((target) => !used.has(target)) || targets[0] || ''
      used.add(link)
      out.push(link)
    }
    return out
  }
  // </edit-tools>

  // ---------------------------------------------------------------- 영역 이름표·Main 설비명 자리(순수 함수)
  // 영역 이름표 정렬과 Main 설비 모듈 묶음 이름표 위치(2026-10-23 사용자 요청)의 자리 계산이다. `tests/test_space_editor_tools.py`
  // 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <layout-look>
  // 영역 이름표 꼬리표의 왼쪽 x(영역 안 좌표) — 위 변의 왼쪽(처음 값)·가운데·오른쪽. 영역 폭 lw, 꼬리표 폭 tagW(영역보다
  // 넓으면 영역 폭으로 줄여 부른다).
  function zoneTagX(lw, tagW, align) {
    if (align === 'center') return (lw - tagW) / 2
    if (align === 'right') return lw - tagW
    return 0
  }
  // Main 설비명 글자 가운데 {x, y}(데이터 좌표, Y 는 위로) — 범위 r {x, y, w, h}, 위치 position, 글자 크기 fs·바깥 틈 gap(데이터
  // 단위), 영역 높이 canvasH. 가운데는 범위 정가운데(넷이면 모듈 꼭짓점이 만나는 자리), 위·아래는 범위 바깥에 테두리를
  // 띄워 붙인다 — 알약 바탕(높이 fs × 1.6)의 반만큼 더 비킨다. 바깥 알약이 영역 위·아래 끝을 넘으면(범위가 영역 끝에 닿은
  // 묶음 — 좁은 화면에서는 화면 밖으로 잘린다) 범위 안쪽 위·아래 띠로 뒤집는다.
  function groupNameSpot(r, position, fs, gap, canvasH) {
    const x = r.x + r.w / 2
    const half = fs * 0.8
    if (position === 'top') {
      const outside = r.y + r.h + gap + half
      return { x, y: outside + half <= canvasH + 1e-9 ? outside : r.y + r.h - gap - half }
    }
    if (position === 'bottom') {
      const outside = r.y - gap - half
      return { x, y: outside - half >= -1e-9 ? outside : r.y + gap + half }
    }
    return { x, y: r.y + r.h / 2 }
  }
  // Main 설비명 글자 크기(데이터 단위) — 화면 최대 maxSize px 에서 범위 폭(알약 여백 포함)에 맞춰 줄이고, 가운데면 범위 높이의
  // 0.16 배를 넘지 않게 한다(알약이 모듈 칸 이름표에 닿지 않게). em 은 글자 폭(em), upp 는 화면 px 당 데이터 단위. 화면
  // minSize px 아래로 줄면 그리지 않는다(null). 다만 가운데이고 모듈 칸 이름표가 하나도 서 있지 않은(bare) 묶음은 minSize 의
  // 알약이 범위 안에 들면 minSize 로 그린다 — 가릴 이름표가 없고, 묶음을 알아볼 글자가 하나는 남는다.
  function groupNameSize(r, position, em, maxSize, upp, minSize, bare) {
    const room = (r.w * 0.92) / (Math.max(em, 1) + 0.9)
    let fs = Math.min(maxSize * upp, room)
    if (position === 'center') fs = Math.min(fs, r.h * 0.16)
    if (fs / upp >= minSize) return fs
    const least = minSize * upp
    if (position === 'center' && bare && least <= room && least * 1.6 <= r.h) return least
    return null
  }
  // 보기 화면에서 Main 설비명을 세울 범위 — 기준일에 보이는 모듈 상자들(shown [{x, y, w, h}])의 바깥 상자. 일부 모듈만 보이는
  // 묶음(겹쳐 숨거나 빠진 모듈)은 이름이 숨은 모듈 자리 — 그 자리를 덮은 다른 설비 위 — 에 서지 않게 보이는 쪽으로 좁힌다.
  // 하나도 없으면 null.
  function shownRange(shown) {
    if (!shown.length) return null
    const x = Math.min(...shown.map((b) => b.x))
    const y = Math.min(...shown.map((b) => b.y))
    return { x, y, w: Math.max(...shown.map((b) => b.x + b.w)) - x, h: Math.max(...shown.map((b) => b.y + b.h)) - y }
  }
  // </layout-look>

  const isUnit = (m) => m.kind === 'unit'
  const isMark = (m) => m.kind !== 'unit'
  const blocks = (m) => (m.kind === 'zone' && m.keepOut) || m.kind === 'shutter' || m.kind === 'door' || m.kind === 'column'
  // 호기의 기준일 판정. 날짜는 모두 `YYYY-MM-DD` 글자라 글자 비교가 곧 날짜 비교다. 실물시작일 「처음부터」는
  // `0000-01-01` 로 온다(어느 날짜보다 앞선다). 기준일이 없으면(받지 못한 회차) 아무 표시도 하지 않는다.
  function unitState(item, T) {
    const exitOn = item.exitOn ?? null
    const storage = Boolean(item.storage)
    const flag = Boolean(item.flag)
    if (!T) return { visible: true, real: true, exitPlan: false, stopped: false, delay: false, offline: false, storage, flag }
    const realFrom = item.realFrom ?? null
    const stopOn = item.stopOn ?? null
    return {
      visible: exitOn === null || T < exitOn,
      real: realFrom !== null && realFrom <= T,
      exitPlan: exitOn !== null && T < exitOn,
      stopped: stopOn !== null && exitOn !== null && stopOn <= T && T < exitOn,
      delay: (item.delays || []).some(([from, until]) => from <= T && (until === null || T < until)),
      offline: (item.offline || []).some(([from, until]) => from <= T && (until === null || T <= until)),
      storage,
      flag,
    }
  }
  // ---------------------------------------------------------------- 겹친 반입 예정 숨기기(보기, 순수 함수)
  // 층 상세 보기에서 기준일에 반입 전(실물 없음)인 호기가 그날 보이는 다른 호기 — 반입됐고 아직 도면에서 빠지지 않은, 실선으로
  // 그리는 호기 — 와 넓이가 0 보다 크게 겹치면 그리지 않는다(2026-10-23 사용자 요청 8 · 결정). 기존 설비가 빠진 자리에 들어올
  // 설비는 기존 설비가 빠지는 날부터 반입 예정(점선)으로 보인다. 반입 전끼리만 겹치면 둘 다 보이고, 같은 Main 설비 묶음의
  // 모듈끼리의 겹침은 셈하지 않는다(모듈 상자마다 판정한다). 배치 편집기는 숨기지 않는다. `tests/test_space_viewer_pick.py` 가 아래
  // 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <view-cover>
  // item 의 판정 st(`unitState`)와 넓이가 겹치는 이웃 호기들 neighbours, 이웃의 판정을 내는 stateOf 로 숨길지 정한다.
  function coveredBy(item, st, neighbours, stateOf) {
    if (st.real || !st.visible) return false
    for (const other of neighbours) {
      if (item.group && other.group === item.group) continue
      const seen = stateOf(other)
      if (seen.visible && seen.real) return true
    }
    return false
  }
  // 대수 글자 — 파이썬 `equipment_units.format_unit_count` 처럼 소수 둘째 자리까지, 끝의 0 은 뗀다(1, 0.25, 1.5).
  function unitCountText(n) {
    const rounded = Math.round(n * 100) / 100 + 0
    return rounded.toLocaleString('ko-KR', { maximumFractionDigits: 2 })
  }
  // </view-cover>
  // 채우기·글자: 지연(빨강) → 보관(검정) → 파이썬이 색 기준·체크로 정한 면(체크한 그룹색, 아니면 기본 회색).
  function unitColors(item, st) {
    if (st.delay) return { fill: 'var(--sle-unit-delay-fill)', ink: 'var(--sle-unit-delay-ink)' }
    if (st.storage) return { fill: 'var(--sle-unit-storage-fill)', ink: 'var(--sle-unit-storage-ink)' }
    return { fill: item.fill || 'var(--sle-unit-default-fill)', ink: item.ink || 'var(--sle-unit-default-ink)' }
  }
  const color = (item) => unitColors(item, unitState(item, S.asOf)).fill
  // 풍선·선택 줄의 상태 이름과 판정 글자. 상태 이름(`stage`)은 일정 기준이고 판정(보기 화면만)은 기준일의
  // 실물(실적) 기준이라 따로 적되, 이름이 이미 말하는 뜻은 거듭 적지 않는다 — 이름이 「반출/이설 예정」이거나
  // 정지만 적힌 「정지 예정」이면 도면 이탈 날짜를 이름에 붙이고, 「정지」·「보관 설비」·「운영 비가동」이면
  // 정지 중·보관·운영 비가동 낱말을 뺀다. 상태 이름은 파이썬이 쥔 기준일(S.dataAsOf)의 것이다 — 페이더로 다른 날을
  // 보는 동안에는 이름 뒤에 「(그날 기준)」을 달고 이름으로 낱말을 빼지 않는다(판정 낱말은 지금 칠한 날의 것).
  function unitWords(item) {
    const named = item.stage || ''
    if (!VIEW) return { stage: named, words: '' }
    const current = !S.dataAsOf || S.dataAsOf === S.asOf
    const stage = current ? named : ''
    const st = unitState(item, S.asOf)
    const exitNamed = st.exitPlan && (stage === '반출/이설 예정' || (stage === '정지 예정' && !item.stopOn))
    const words = []
    if (!st.real) words.push('반입 전(실물 없음)')
    if (st.exitPlan && !exitNamed) words.push(`반출/이설 예정 ${item.exitOn}`)
    if (st.stopped && stage !== '정지') words.push('정지 중')
    if (st.delay) words.push('지연')
    if (st.storage && stage !== '보관 설비') words.push('보관')
    if (st.offline && stage !== '운영 비가동') words.push('운영 비가동')
    if (st.flag) words.push('미확인(오늘 기준)')
    const label = !current && named ? `${named}(${S.dataAsOf} 기준)` : exitNamed ? `${stage} ${item.exitOn}` : stage
    return { stage: label, words: words.join(' · ') }
  }
  const zoneColor = (m) => (m.keepOut ? 'var(--sle-danger)' : markColors[m.color] || markColors.gray || 'gray')
  const W = () => S.canvas.w
  const H = () => S.canvas.h
  const margin = () => Math.max(W(), H()) * VIEW_MARGIN
  // 전체 보기(z=1)의 viewBox: 영역+여백을 무대 px 비율로 넓힌 상자. 비율이 무대와 같아 SVG 안에 빈 띠가 없고,
  // getScreenCTM 의 배율이 가로·세로 같아 끌기·손잡이 좌표가 그대로 맞는다.
  const baseBox = () => {
    const pad = margin()
    let bw = W() + pad * 2
    let bh = H() + pad * 2
    const port = S.port
    if (port && port.w >= 1 && port.h >= 1) {
      const aspect = port.w / port.h
      if (bw / bh < aspect) bw = bh * aspect
      else bh = bw / aspect
    }
    return { w: bw, h: bh }
  }
  const viewW = () => baseBox().w / S.view.z
  const viewH = () => baseBox().h / S.view.z
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
  // 호기 이름표의 글자 폭(em). 이름표와 같은 서체·굵기(600, `.sle-label`)를 캔버스로 재고 이름마다 한 번
  // 기억한다 — 글자 수 어림은 한글·굵은 대문자를 덜 쳐서 이름이 상자를 넘어 옆 상자 이름과 붙어 보였다.
  // 재지 못하면 어림이다. 서체를 아직 받는 중에 잰 값은 기억하지 않는다(받은 뒤 다시 잰다).
  const labelEm = (text) => {
    const memo = S.labelEm || (S.labelEm = new Map())
    if (memo.has(text)) return memo.get(text)
    let em = emWidth(text)
    try {
      const ctx = S.measureCtx || (S.measureCtx = document.createElement('canvas').getContext('2d'))
      if (ctx) {
        ctx.font = `600 100px ${getComputedStyle(host).fontFamily}`
        const measured = ctx.measureText(text).width / 100
        if (measured > 0) em = measured
      }
    } catch (error) {
      em = emWidth(text)
    }
    if (!document.fonts || document.fonts.status === 'loaded') memo.set(text, em)
    return em
  }
  const snapshot = (item) => ({
    x: item.x, y: item.y, w: item.w, h: item.h, placed: item.placed, moveTo: item.moveTo, sizeGuessed: item.sizeGuessed,
    sizeFrom: item.sizeFrom, rot: item.rot, label: item.label, group: item.group, color: item.color, hatch: item.hatch, keepOut: item.keepOut,
    link: item.link, fontSize: item.fontSize, fontColor: item.fontColor, borderStyle: item.borderStyle, labelAlign: item.labelAlign,
  })
  // 층 블록 글자: 첫 줄은 이름(없으면 연결 층), 다음 줄은 배치·미배치 대수. 풍선에는 점유율까지.
  const blockHead = (item) => item.label || item.link || '연결 없음'
  // 비활성 층(사용 안 함·생산라인 아님)을 가리키는 블록의 사유 글. 연결 층의 `linkStats.inactive` 에서 온다 — 회색 빗금으로
  // 그리고 보기에서 눌러도 열지 않는다(그 층은 층 목록 표 「비활성 층」에서 연다). 사용 층이면 빈 글.
  const blockOff = (item) => (item && item.kind === 'block' && item.link && LINK_STATS[item.link] && LINK_STATS[item.link].inactive) || ''
  const blockLines = (item) => {
    const stats = LINK_STATS[item.link] || {}
    // 비활성 블록은 대수 줄 대신 사유다(대수는 풍선에 남는다).
    if (blockOff(item)) return [blockHead(item), blockOff(item)].map(String)
    return [blockHead(item), stats.placed, stats.unplaced].filter(Boolean).map(String)
  }
  const opensFloor = (item) => Boolean(VIEW && FAB && item && item.kind === 'block' && item.link && !blockOff(item))
  const blockTip = (item) => {
    const stats = LINK_STATS[item.link] || {}
    if (blockOff(item)) return [blockHead(item), '비활성', blockOff(item), stats.placed, stats.unplaced].filter(Boolean).join(' · ')
    const parts = [blockHead(item), stats.placed, stats.unplaced, stats.occupancy].filter(Boolean)
    return parts.join(' · ') + (opensFloor(item) ? ' · 누르면 열기' : '')
  }
  const hasSize = (item) => Number.isFinite(item.w) && item.w > 0 && Number.isFinite(item.h) && item.h > 0
  const unitTip = (item) => {
    const { stage, words } = unitWords(item)
    return `${item.label} · ${stage}${words ? ` · ${words}` : ''}${item.detail ? ` · ${item.detail}` : ''}${item.group ? ` · Main 설비 ${item.group}` : ''}${item.arrived ? ' · 다른 층에서 옴' : ''}`
  }
  const sameGeometry = (a, b) => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h
  const sameNumber = (p, q) => p === q || (Number.isNaN(p) && Number.isNaN(q))
  const sameSize = (a, b) => sameNumber(a.w, b.w) && sameNumber(a.h, b.h)
  // 이 층 도면에 서 있는가. 다른 층으로 보낸 호기는 좌표를 지닌 채 이 층에서만 빠진다.
  const onCanvas = (m) => m.placed && !m.moveTo
  // Main 설비로 묶은 모듈 행은 한 덩어리다. 묶음이 없으면 자기 하나.
  const members = (item) => (item.group ? [...S.items.values()].filter((m) => m.group === item.group) : [item])
  // 그 id 의 호기 — 편집기 호기, 아니면 숨은 모듈(`S.ghosts`). 되돌리기·끌기 취소가 둘을 함께 되돌린다.
  const itemOf = (id) => S.items.get(id) || S.ghosts.get(id)
  // 묶음 열쇠 — 처음 받은 Main 설비 이름. 묶음 이름을 바꿔도 숨은 모듈과 이어진다.
  const groupKeyOf = (m) => {
    const o = S.original.get(m.id)
    return (o && o.group) || m.group || null
  }
  // 묶음의 숨은 모듈 — 이 층에 상자가 있지만 도면 대상이 아닌 형제(레이아웃표시 N·도면 이탈 …). 그리지 않고 고르지 않지만
  // 바둑판의 제 칸을 차지하고 묶음과 함께 옮겨진다(파이썬 `EditorInputs.ghosts`).
  const ghostsOf = (item) => {
    const key = groupKeyOf(item)
    return key ? [...S.ghosts.values()].filter((g) => g.group === key) : []
  }
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
  // 자리·크기가 같은가. 미배치끼리는 크기만 견준다(좌표가 NaN 이다).
  const sameSpot = (a, b) => a.placed === b.placed && (a.placed ? sameGeometry(a, b) : sameSize(a, b))

  // Main 설비 **모듈 묶음** — 이 편집기의 모듈과 숨은 모듈을 합쳐 둘 이상인 묶음(2026-10-23 사용자 요청). 사람이 고치는 것은
  // 묶음 범위(이 층 도면에 선 모듈의 바깥 상자)뿐이고, 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 자동으로 선다. 칸
  // 자리는 지금 자리를 지킨다(`assignModuleCells` — 이미 바둑판이면 제 칸, 새로 놓을 때만 자연 정렬). 모듈 하나만 옮기거나
  // 키우는 길은 없다 — 고르기·끌기·방향키·숫자 칸·서랍·빼기·다른 층 보내기가 모두 묶음째다. 바둑판이 아닌 옛 묶음은 읽을 때
  // 바꾸지 않고, 처음 옮기거나 키울 때(범위가 실제로 바뀔 때) 그 범위로 다시 놓는다. 파이썬 `parse_editor_apply` 가 같은
  // 규칙으로 견준다(한 눈금 안이면 바로잡고, 더 다르면 거부한다). 돌려주는 목록에는 숨은 모듈(`ghost`)도 든다.
  const moduleMembers = (item) => {
    if (!item || !isUnit(item) || !item.group || item.ghost) return null
    const list = [...members(item), ...ghostsOf(item)]
    return list.length >= 2 ? list : null
  }
  // 묶음 열쇠 → 이 편집기의 모듈 수(숨은 모듈 포함, 한 번 훑어 센다 — 호기마다 `members` 를 부르지 않게).
  const groupCounts = () => {
    const counts = new Map()
    const add = (key) => counts.set(key, (counts.get(key) || 0) + 1)
    for (const m of S.items.values()) if (isUnit(m) && m.group) add(groupKeyOf(m))
    for (const g of S.ghosts.values()) add(g.group)
    return counts
  }
  // 범위를 정밀도·최소 크기(칸마다 최소 크기 한 칸 — 열·행 × 1 눈금)·영역 안으로 맞춘다. 크기 먼저, 그다음 위치.
  function fitRange(r, count) {
    const [cols, rows] = moduleGrid(count)
    const w = Math.min(Math.max(roundTo(r.w), cols / SCALE), floorTo(W()))
    const h = Math.min(Math.max(roundTo(r.h), rows / SCALE), floorTo(H()))
    return { x: clamp(roundTo(r.x), 0, floorTo(W() - w)), y: clamp(roundTo(r.y), 0, floorTo(H() - h)), w, h }
  }
  // 묶음 범위 — 이 층 도면에 선 모듈(숨은 모듈 포함)의 바깥 상자. 보이는 모듈이 도면에 하나도 없으면(서랍·다른 층) null.
  function groupRange(mods) {
    if (!mods.some((m) => !m.ghost && onCanvas(m))) return null
    const b = bbox(mods.filter(onCanvas))
    return fitRange({ x: b.minX, y: b.minY, w: b.maxR - b.minX, h: b.maxT - b.minY }, mods.length)
  }
  // 바둑판 순수 함수에 넘길 모양 {name, x, y, w, h, placed}.
  const slotView = (m) => ({ name: m.id, x: m.x, y: m.y, w: m.w, h: m.h, placed: onCanvas(m) })
  // 지금 자리를 지키는 칸 배정(`assignModuleCells`).
  const groupSlots = (mods) => assignModuleCells(mods.map(slotView), SCALE)
  const setSpots = (mods, spots) => {
    const at = new Map(spots.map((spot) => [spot.name, spot]))
    for (const m of mods) {
      const spot = at.get(m.id)
      m.x = spot.x
      m.y = spot.y
      m.w = spot.w
      m.h = spot.h
      m.placed = true
    }
  }
  // 범위 바둑판의 제 칸(slots — 없으면 지금 자리 배정)에 모듈을 모두 세운다(좌표 없던 형제·숨은 모듈도 이때 놓인다).
  function layModules(mods, range, slots = groupSlots(mods)) {
    setSpots(mods, layModuleGroup(range, mods.map((m) => m.id), slots, SCALE))
  }
  // 묶음 g {mods, range, slots} 를 새 범위 to 로 다시 놓는다. 범위가 눈금까지 그대로면 다시 놓지 않고 거짓이다 — befores 를
  // 주면(끌기) 처음 값으로 되돌린다(끌다 제자리로 돌아온 때).
  function relayGroup(g, to, befores) {
    const spots = relaidGroup(g.mods.map((m) => m.id), g.slots, g.range, to, SCALE)
    if (spots) { setSpots(g.mods, spots); return true }
    if (befores) for (const m of g.mods) Object.assign(m, befores.get(m.id))
    return false
  }
  // 바둑판 그대로인가 — 모듈이 모두 도면에 서 있고 바깥 상자를 나눈 칸(지금 자리 배정)과 눈금까지 같다. 이름 차례는 보지
  // 않는다(칸 모양만).
  function isTiled(mods) {
    return tileDeviation(mods.map(slotView), SCALE) === 0
  }
  // 움직일 단위. 모듈 묶음은 묶음 하나(모든 모듈과 범위), 나머지는 이 층 도면에 선 호기·요소 하나씩이다. `box` 는 모두를
  // 감싼 상자(묶음은 범위)다.
  function movePlan(list) {
    const groups = new Map()
    const loose = new Map()
    for (const item of list) {
      const mods = moduleMembers(item)
      if (!mods) {
        for (const m of placedMembers(item)) loose.set(m.id, m)
        continue
      }
      const key = groupKeyOf(item)
      if (groups.has(key)) continue
      const range = groupRange(mods)
      if (range) groups.set(key, { mods, range, slots: groupSlots(mods) })
    }
    const parts = [...groups.values()]
    const shells = [...loose.values(), ...parts.map((g) => g.range)]
    // items 에는 숨은 모듈도 든다(되돌리기·끌기 취소 기록). 그릴 것은 `redraw` 가 거른다.
    return {
      loose: [...loose.values()],
      groups: parts,
      items: [...loose.values(), ...parts.flatMap((g) => g.mods)],
      box: shells.length ? bbox(shells) : null,
    }
  }
  // 모듈 묶음은 선택에 한 대만 둔다 — 고르는 단위가 묶음이다(모듈 하나만 고르는 길이 없다). 앞에 온 것이 남는다.
  function onePerGroup(ids) {
    const seen = new Set()
    return ids.filter((id) => {
      const item = S.items.get(id)
      const key = item && isUnit(item) && item.group ? `g:${item.group}` : `i:${id}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }
  // 놓인 호기·요소가 차지한 가장 먼 오른쪽·위. 편집 영역은 이보다 작게 줄일 수 없다.
  const extents = () => {
    let right = RESERVED.right
    let top = RESERVED.top
    // 숨은 모듈은 묶음과 함께 옮겨지므로 지금 자리로 센다(처음 자리는 RESERVED 에 들어 있다).
    for (const item of [...S.items.values(), ...S.ghosts.values()]) {
      if (!onCanvas(item)) continue
      right = Math.max(right, item.x + item.w)
      top = Math.max(top, item.y + item.h)
    }
    return { right: ceilTo(right), top: ceilTo(top) }
  }

  // ---------------------------------------------------------------- Main 설비명(모듈 묶음 이름표)
  // 모듈 묶음(모듈 둘 이상)의 범위에 Main 설비명을 그린다(2026-10-23 사용자 요청). 고른 적이 없는 묶음은 그 모양의 처음
  // 위치(`groupLabelDefault` — 한 줄 묶음은 범위 바깥 위, 두 줄 이상은 범위 정가운데)이고, 묶음마다 가운데·범위 바깥 바로
  // 위·아래를 고른다(배치 편집 선택 칸). 고른 위치(저장된 행 포함)는 묶음 열쇠(`groupKeyOf` — 처음 Main 설비 이름)로
  // `S.groupLabels` 에 쥐고, 적용값 `groupLabels` 는 이 층에 남는 묶음마다 [{group: 열쇠, position}] 이다(파이썬
  // `next_group_labels` 가 이름 바꿈을 따라 층 위치 목록으로 합치고, 처음 위치는 행을 두지 않는다). 보기 화면은 기준일에
  // 묶음의 모듈이 하나도 보이지 않으면 이름도 숨긴다.
  const labelIn = (map, key, count) => (map.has(key) ? pickOr(map.get(key), GROUP_LABEL_POSITIONS) : groupLabelDefault(count))
  const groupLabelOf = (key, count = groupCounts().get(key) || 0) => labelIn(S.groupLabels, key, count)
  // 이 편집기의 모듈 묶음 — 열쇠 → 대표 호기(편집기 호기, 숨은 모듈 아님). 한 번 훑는다.
  function moduleGroups() {
    const out = new Map()
    const counts = groupCounts()
    for (const m of S.items.values()) {
      if (!isUnit(m) || !m.group) continue
      const key = groupKeyOf(m)
      if (!out.has(key) && (counts.get(key) || 0) >= 2) out.set(key, m)
    }
    return out
  }
  // 처음 값에서 바뀐 묶음 수.
  function groupLabelChangeCount() {
    const counts = groupCounts()
    let count = 0
    for (const key of moduleGroups().keys()) {
      const n = counts.get(key) || 0
      if (labelIn(S.groupLabels, key, n) !== labelIn(S.originalGroupLabels, key, n)) count += 1
    }
    return count
  }
  // 적용값 `groupLabels` — 이 층에 남는 모듈 묶음마다(다른 층으로 보낸 묶음은 빠진다 — 그 층에서는 처음 위치로 선다).
  function groupLabelsPayload() {
    const counts = groupCounts()
    const out = []
    for (const [key, lead] of moduleGroups()) {
      if (members(lead).every((m) => m.moveTo)) continue
      out.push({ group: key, position: groupLabelOf(key, counts.get(key) || 0) })
    }
    return out
  }
  // 묶음 하나의 위치를 바꾼다. 되돌리기 한 번이다.
  function setGroupLabel(key, value) {
    const before = groupLabelOf(key)
    const next = pickOr(value, GROUP_LABEL_POSITIONS)
    if (before === next) { syncInspector(); return }
    // 되돌리기는 고른 값이 없던 묶음을 다시 「고른 적 없음」(처음 위치)으로 돌린다.
    pushUndo([{ op: 'groupLabel', key, before: S.groupLabels.has(key) ? S.groupLabels.get(key) : null }])
    S.groupLabels.set(key, next)
    drawGroupNames()
    updateStatus()
  }
  // 보기 화면에서 묶음이 기준일에 보이는가 — 모듈 하나라도 보이면 보인다. 편집 화면은 늘 보인다(테·덧표시가 없다).
  const groupShown = (mods) => !VIEW || mods.some((m) => !m.ghost && S.groups.get(m.id)?.__visible !== false)
  // 도면에 서 있고 (보기 화면이면) 기준일에 보이는 모듈.
  const seenModule = (m) => onCanvas(m) && !m.ghost && (!VIEW || S.groups.get(m.id)?.__visible !== false)
  function drawGroupNames() {
    namesLayer.replaceChildren()
    if (FAB) return
    const upp = unitsPerPx()
    for (const [key, lead] of moduleGroups()) {
      const mods = moduleMembers(lead)
      const whole = mods ? groupRange(mods) : null
      if (!whole || !groupShown(mods)) continue
      // 보기 화면에서 일부 모듈만 보이면 보이는 모듈의 바깥 상자에 세운다(`shownRange`).
      const seen = mods.filter(seenModule)
      const range = VIEW && seen.length < mods.filter(onCanvas).length ? shownRange(seen) : whole
      if (!range) continue
      const name = String(lead.group)
      const position = groupLabelOf(key, mods.length)
      // 모듈 칸 이름표가 하나도 서 있지 않으면(밀집 층·작은 묶음) 가운데 이름은 가장 작은 크기로라도 선다.
      const bare = !seen.some((m) => unitLabelSize(m, upp) / upp >= UNIT_LABEL_MIN_PX)
      const fs = groupNameSize(range, position, labelEm(name), GROUP_NAME_PX, upp, UNIT_LABEL_MIN_PX, bare)
      if (fs === null) continue
      const spot = groupNameSpot(range, position, fs, 2 * upp, H())
      const cy = H() - spot.y
      const pillW = Math.min(range.w, labelEm(name) * fs + fs * 0.9)
      const node = el('g', { class: `sle-group-name-tag is-${position}` })
      node.dataset.group = key
      node.append(
        el('rect', { class: 'sle-group-name-pill', x: spot.x - pillW / 2, y: cy - fs * 0.8, width: pillW, height: fs * 1.6, rx: fs * 0.8 }),
      )
      const text = el('text', { class: 'sle-group-name-text', x: spot.x, y: cy, 'font-size': fs })
      text.textContent = name
      node.append(text)
      namesLayer.append(node)
    }
  }

  // ---------------------------------------------------------------- 정렬선(편집)
  // 끌어 옮기기·크기 바꾸기·서랍에서 놓기·새 도면 요소 놓기·붙여넣기 때(2026-10-23 사용자 요청), 움직이는 것의 왼·가운데·오른
  // x 와 아래·가운데·위 y 가 화면에 보이는 다른 호기·도면 요소(모듈 묶음은 범위)의 같은 선과 화면 GUIDE_PX 안이면 그 선에
  // 붙이고 정렬선을 그린다. 격자 붙임보다 먼저다. Alt 를 누른 채면 붙이지 않는다. 놓으면 선은 사라진다. 층·FAB 편집이 같다.
  const GUIDE_PX = 6
  const guideTol = () => GUIDE_PX * unitsPerPx()
  // 선이 맞닿았는가 — 눈금 반 칸 안(가운데 선은 눈금 반 칸 끝을 가질 수 있다).
  const GUIDE_EPS = 0.5 / SCALE
  // 정렬선을 줄 상자 — 이 층 도면에 서 있고 지금 화면(viewBox)에 걸친 호기·도면 요소. 모듈 묶음은 범위(도면에 선 모듈의 바깥
  // 상자) 하나다. exclude(움직이는 것의 id)는 빼고, 모듈 하나라도 빠지는 묶음은 통째로 뺀다. 숨은 모듈은 그 범위에만 든다.
  function guideTargets(exclude) {
    const view = { x0: S.view.x, x1: S.view.x + viewW(), y0: H() - (S.view.top + viewH()), y1: H() - S.view.top }
    const counts = groupCounts()
    const ranges = new Map()
    const boxes = []
    const keep = (b) => {
      if (b.x > view.x1 || b.x + b.w < view.x0 || b.y > view.y1 || b.y + b.h < view.y0) return
      boxes.push(b)
    }
    for (const m of [...S.items.values(), ...S.ghosts.values()]) {
      if (!onCanvas(m)) continue
      const key = isUnit(m) && m.group ? (m.ghost ? m.group : groupKeyOf(m)) : null
      if (key && (counts.get(key) || 0) >= 2) {
        const range = ranges.get(key) || { minX: Infinity, minY: Infinity, maxR: -Infinity, maxT: -Infinity, out: false, shown: false }
        range.minX = Math.min(range.minX, m.x)
        range.minY = Math.min(range.minY, m.y)
        range.maxR = Math.max(range.maxR, m.x + m.w)
        range.maxT = Math.max(range.maxT, m.y + m.h)
        if (exclude.has(m.id)) range.out = true
        if (!m.ghost) range.shown = true
        ranges.set(key, range)
        continue
      }
      if (m.ghost || exclude.has(m.id)) continue
      keep({ x: m.x, y: m.y, w: m.w, h: m.h })
    }
    for (const r of ranges.values()) {
      if (!r.out && r.shown) keep({ x: r.minX, y: r.minY, w: r.maxR - r.minX, h: r.maxT - r.minY })
    }
    return { boxes, xs: boxes.flatMap(linesX), ys: boxes.flatMap(linesY) }
  }
  // 정렬선(과 놓을 자리 미리 보기 preview {x, y, w, h})을 그린다. 맨 위 층이고 눌림을 받지 않는다.
  function drawGuides(segments, preview) {
    if (S.guideTimer) { clearTimeout(S.guideTimer); S.guideTimer = 0 }
    const nodes = segments.map((s) => (s.axis === 'x'
      ? el('line', { class: 'sle-guide', x1: s.at, x2: s.at, y1: H() - s.to, y2: H() - s.from })
      : el('line', { class: 'sle-guide', x1: s.from, x2: s.to, y1: H() - s.at, y2: H() - s.at })))
    if (preview) {
      nodes.unshift(el('rect', { class: 'sle-drop-preview', x: preview.x, y: H() - (preview.y + preview.h), width: preview.w, height: preview.h }))
    }
    guidesLayer.replaceChildren(...nodes)
  }
  function clearGuides() {
    if (S.guideTimer) { clearTimeout(S.guideTimer); S.guideTimer = 0 }
    if (guidesLayer.firstChild) guidesLayer.replaceChildren()
  }
  // 끌기 없이 붙인 것(붙여넣기)의 정렬선은 잠깐 보였다 사라진다.
  function flashGuides(segments) {
    if (!segments.length) return
    drawGuides(segments)
    S.guideTimer = setTimeout(clearGuides, 900)
  }
  // 상자 {minX, minY, maxR, maxT} → {x, y, w, h}.
  const boxRect = (b) => ({ x: b.minX, y: b.minY, w: b.maxR - b.minX, h: b.maxT - b.minY })
  // 끄는 것이 붙을 정렬선 상자 — 끄는 동안 한 번 구하고, 화면(배율·이동)·영역이 바뀌면 다시 구한다.
  function dragGuides(drag) {
    const key = `${S.view.x}|${S.view.top}|${S.view.z}|${W()}|${H()}`
    if (!drag.guides || drag.guides.key !== key) drag.guides = { key, ...guideTargets(new Set(drag.ids)) }
    return drag.guides
  }
  // 크기 손잡이 방향 → 움직이는 선 번호(세로선 x, 가로선 y). e 오른쪽(2)·w 왼쪽(0)·n 위(2)·s 아래(0).
  const edgeLines = (dir) => ({
    x: dir.includes('e') ? [2] : dir.includes('w') ? [0] : [],
    y: dir.includes('n') ? [2] : dir.includes('s') ? [0] : [],
  })
  // 끄는 중의 정렬선 붙임 — 손 그대로의 이동량(rawDx 오른쪽, rawDTop 화면 아래쪽)에서 정렬선에 닿는 축만 그 선에 붙인 이동량
  // {dx, dTop}(닿지 않은 축은 null — 격자 붙임). 옮기기는 함께 움직이는 범위(모듈 묶음은 범위)의 세 선씩, 크기 바꾸기는
  // 움직이는 변만 본다. free(Alt)면 붙이지 않는다.
  function alignDrag(drag, rawDx, rawDTop, free) {
    if (free || !['move', 'resize', 'range'].includes(drag.mode)) return { dx: null, dTop: null }
    const g = dragGuides(drag)
    const tol = guideTol()
    let sx = null
    let sy = null
    if (drag.mode === 'move') {
      if (!drag.box) return { dx: null, dTop: null }
      const raw = { ...boxRect(drag.box), x: drag.box.minX + rawDx, y: drag.box.minY - rawDTop }
      sx = nearestSnap(linesX(raw), g.xs, tol)
      sy = nearestSnap(linesY(raw), g.ys, tol)
    } else {
      const b = drag.mode === 'range' ? drag.groups[0].range : drag.befores.get(drag.id)
      const edges = edgeLines(drag.dir)
      // 손 그대로 옮긴 변의 자리 — 0 왼쪽·아래, 2 오른쪽·위.
      const xAt = { 0: b.x + rawDx, 2: b.x + b.w + rawDx }
      const yAt = { 0: b.y - rawDTop, 2: b.y + b.h - rawDTop }
      sx = nearestSnap(edges.x.map((k) => xAt[k]), g.xs, tol)
      sy = nearestSnap(edges.y.map((k) => yAt[k]), g.ys, tol)
    }
    return { dx: sx === null ? null : rawDx + sx, dTop: sy === null ? null : rawDTop - sy }
  }
  // 끈 뒤 자리의 정렬선을 그린다(free 면 지운다). 옮기기는 세 선씩, 크기 바꾸기는 움직이는 변만.
  function showDragGuides(drag, free) {
    if (free || !['move', 'resize', 'range'].includes(drag.mode)) { clearGuides(); return }
    const standing = drag.ids.map(itemOf).filter((m) => m && onCanvas(m))
    if (!standing.length) { clearGuides(); return }
    const edges = drag.mode === 'move' ? { x: [0, 1, 2], y: [0, 1, 2] } : edgeLines(drag.dir)
    drawGuides(guideSegments(boxRect(bbox(standing)), dragGuides(drag).boxes, GUIDE_EPS, edges.x, edges.y))
  }
  // 서랍·팔레트·붙여넣기로 놓을 자리(왼쪽 아래 {x, y, w, h, segments}) — 점 p(화면 좌표 {x, top})가 가운데인 w×h 상자를 격자에
  // 맞추고, 정렬선에 닿는 축은 그 선에 붙인다(free 면 붙이지 않는다). 영역 안으로 민다.
  function dropSpot(p, w, h, free) {
    const raw = { x: p.x - w / 2, y: H() - p.top - h / 2, w, h }
    let x = snapDelta(raw.x)
    let y = snapDelta(raw.y)
    const g = free ? null : guideTargets(new Set())
    if (g) {
      const sx = nearestSnap(linesX(raw), g.xs, guideTol())
      const sy = nearestSnap(linesY(raw), g.ys, guideTol())
      if (sx !== null) x = raw.x + sx
      if (sy !== null) y = raw.y + sy
    }
    const spot = { x: roundTo(clamp(x, 0, W() - w)), y: roundTo(clamp(y, 0, H() - h)), w, h }
    return { ...spot, segments: g ? guideSegments(spot, g.boxes, GUIDE_EPS) : [] }
  }

  // ---------------------------------------------------------------- 확대·축소
  // viewBox 를 캔버스의 일부로 좁혀 확대한다. 좌표 변환은 getScreenCTM 이 viewBox 를 품어 끌기·손잡이가 그대로 맞는다.
  // 화면 옮기기는 영역+여백 안에서만. 보이는 폭이 그보다 넓은 축은 영역 가운데에 둔다. 단 편집의 트레이 서랍이 열려
  // 있으면 그 폭(데이터 단위)만큼 오른쪽으로 더 옮길 수 있다 — 서랍 아래에 놓인 것을 꺼내 보이는 자리다. 서랍을
  // 접으면 0 이 되어 화면이 제자리로 돌아온다.
  function trayReserve() {
    if (VIEW || FAB || !S.drawerOpen || trayBox.hidden || !S.port || S.port.w < 1) return 0
    return (trayBox.getBoundingClientRect().width + DRAWER_INSET_PX * 2) * (viewW() / S.port.w)
  }
  function clampView() {
    S.view.z = clamp(S.view.z, 1, MAX_ZOOM)
    const pad = margin()
    const vw = viewW()
    const vh = viewH()
    const reserve = trayReserve()
    const center = (W() - vw) / 2
    S.view.x = vw >= W() + pad * 2
      ? clamp(S.view.x, center, center + reserve)
      : clamp(S.view.x, -pad, W() + pad + reserve - vw)
    S.view.top = vh >= H() + pad * 2 ? (H() - vh) / 2 : clamp(S.view.top, -pad, H() + pad - vh)
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
    const base = baseBox()
    const z = clamp(Math.min(base.w / (box.maxR - box.minX + pad * 2), base.h / (box.maxT - box.minY + pad * 2)), 1, MAX_ZOOM)
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

  // ---------------------------------------------------------------- 무대 높이(브라우저 안에서만)
  // 고른 높이는 브라우저(localStorage)에 범위별로 기억한다. 파이썬으로 보내지 않는다 — 보내면 페이지가 다시
  // 돈다. 사생활 창·막힌 저장소에서는 읽기·쓰기가 던지므로 이 편집기 안에서만 기억하고 기본 높이로 산다.
  function savedHeight() {
    try {
      const value = Number(window.localStorage.getItem(HEIGHT_STORE_KEY))
      return Number.isFinite(value) && value > 0 ? value : null
    } catch {
      return null
    }
  }
  function storeHeight(value) {
    try {
      if (value === null) window.localStorage.removeItem(HEIGHT_STORE_KEY)
      else window.localStorage.setItem(HEIGHT_STORE_KEY, String(Math.round(value)))
    } catch {
      // 기억하지 못해도 지금 화면은 S.chosenH 로 그대로 쓴다.
    }
  }
  const maxHeight = () => Math.max(MIN_DEFAULT_H, Math.round(window.innerHeight * MAX_H_RATIO))
  // 기본 높이 = 화면 높이에서 보기 화면의 머리·도구 몫을 뺀 만큼(스크롤·무대 위치와 무관). 단 영역+여백이 열
  // 폭을 꽉 채우는 높이를 넘지 않는다 — 넓적한 영역 위아래에 빈 띠를 만들지 않게.
  function defaultHeight() {
    const width = stage.clientWidth || host.clientWidth || 0
    const pad = margin()
    const fitted = width > 0 ? (width * (H() + pad * 2)) / (W() + pad * 2) : Infinity
    const room = window.innerHeight - CHROME_PX
    return Math.round(clamp(Math.min(room, fitted), MIN_DEFAULT_H, maxHeight()))
  }
  function setStageHeight(value) {
    const h = Math.round(value)
    if (stage.style.height !== `${h}px`) stage.style.height = `${h}px`
    S.stageH = h
    resizeHandle.setAttribute('aria-valuenow', String(h))
    resizeHandle.setAttribute('aria-valuemin', String(MIN_DRAG_H))
    resizeHandle.setAttribute('aria-valuemax', String(maxHeight()))
    resizeHandle.setAttribute('aria-valuetext', `높이 ${h}px`)
  }
  // 무대 px 크기를 S.port 에 적는다. 1px 미만 변화는 무시한다(스크롤 막대 들락날락에 흔들리지 않게). 바뀌었으면 true.
  function measurePort() {
    const w = stage.clientWidth
    const h = stage.clientHeight
    if (S.port && Math.abs(S.port.w - w) < 1 && Math.abs(S.port.h - h) < 1) return false
    S.port = { w, h }
    return true
  }
  // 무대 높이를 정한다 — 고른 값(이 편집기 → 브라우저 기억 순), 없으면 기본값.
  function fitStage() {
    const chosen = S.chosenH ?? savedHeight()
    setStageHeight(chosen === null ? defaultHeight() : clamp(chosen, MIN_DRAG_H, maxHeight()))
    return measurePort()
  }
  function chooseHeight(value) {
    const h = Math.round(clamp(value, MIN_DRAG_H, maxHeight()))
    S.chosenH = h
    setStageHeight(h)
    storeHeight(h)
    if (measurePort()) applyView()
  }
  function resetHeight() {
    S.chosenH = null
    storeHeight(null)
    if (fitStage()) applyView()
  }

  function drawStatic() {
    // 영역 비율이 바뀌면 기본 높이도 바뀐다(고른 높이가 없을 때만).
    fitStage()
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
      // 확대하면 다시 보인다. 이름은 선택하면 상태줄·옆 칸에, 올려 두면 풍선에 나온다. 폭은 잰 글자 폭이라
      // 이름이 상자 밖으로 넘치지 않는다.
      const upp = unitsPerPx()
      const fontSize = unitLabelSize(item, upp)
      label.setAttribute('font-size', fontSize)
      label.style.display = fontSize / upp < UNIT_LABEL_MIN_PX ? 'none' : ''
      positionUnitMarks(group, item, top)
    } else {
      drawMark(group, item, top)
    }
    positionHandles(group, item, top)
    group.classList.toggle('is-changed', isChanged(item) || isRenamed(item))
  }
  // 호기 이름표 글자 크기(데이터 단위) — 상자 높이의 0.32 배·잰 글자 폭으로 상자 폭에 맞춘 크기·화면 14px 가운데 가장 작은 것.
  function unitLabelSize(item, upp) {
    const fitFont = (item.w * 0.94) / Math.max(labelEm(item.label), 1)
    return Math.min(item.h * 0.32, fitFont, 14 * upp)
  }

  const setBox = (node, x, y, w, h) => {
    node.setAttribute('x', x)
    node.setAttribute('y', y)
    node.setAttribute('width', Math.max(w, 0))
    node.setAttribute('height', Math.max(h, 0))
  }
  // 보기 화면 호기의 덧표시 자리(2026-10-16 사용자 결정). 선택 후광은 상자 밖으로 띄우고, 테·빗금은 상자와 같은
  // 자리, 미확인 「!」는 오른쪽 위·운영 비가동 표식은 왼쪽 위·겹침 꼭지 삼각은 오른쪽 위 꼭지다. 표식은 화면 px 로
  // 정해(확대해도 같은 크기) 상자가 작으면 줄이고, 너무 작으면 숨긴다. 겹침 삼각이 서면 「!」를 그 옆으로 비킨다.
  function positionUnitMarks(group, item, top) {
    const parts = group.__parts
    if (!parts) return
    const upp = unitsPerPx()
    const gap = HALO_GAP_PX * upp
    setBox(parts.halo, item.x - gap, top - gap, item.w + gap * 2, item.h + gap * 2)
    for (const node of [parts.hatch, parts.ringOut, parts.ring]) setBox(node, item.x, top, item.w, item.h)
    const right = item.x + item.w
    const leg = Math.min(CORNER_PX * upp, item.w * 0.4, item.h * 0.4)
    parts.corner.setAttribute('points', `${right - leg},${top} ${right},${top} ${right},${top + leg}`)
    const r = Math.min(BADGE_PX * upp, item.w * 0.3, item.h * 0.3)
    const hidden = r / upp < 3 ? 'none' : ''
    const inset = 1.5 * upp
    const cy = top + inset + r
    const fx = right - inset - r - (group.classList.contains('is-overlap') ? leg : 0)
    parts.flagDot.setAttribute('cx', fx)
    parts.flagDot.setAttribute('cy', cy)
    parts.flagDot.setAttribute('r', r)
    parts.flagText.setAttribute('x', fx)
    parts.flagText.setAttribute('y', cy)
    parts.flagText.setAttribute('font-size', r * 1.5)
    parts.flag.style.display = hidden
    const ox = item.x + inset + r
    parts.offlineDot.setAttribute('cx', ox)
    parts.offlineDot.setAttribute('cy', cy)
    parts.offlineDot.setAttribute('r', r)
    parts.offlineBars.forEach((bar, k) => setBox(bar, ox + (k ? 0.18 : -0.46) * r, cy - 0.45 * r, 0.28 * r, 0.9 * r))
    parts.offline.style.display = hidden
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
    // 이름표 글자는 화면 px 로 정한다(확대해도 같은 크기). 고른 크기가 없으면 LABEL_PX.
    const fs = (item.fontSize || LABEL_PX) * upp
    // 비활성 층 블록은 고른 「글자 색」을 달지 않는다 — 인라인 색이 CSS 의 흐린 글자(muted)를 이긴다.
    const ink = blockOff(item) ? '' : fontInk(item)
    const text = (value, x, y, size, anchor) => {
      const node = el('text', { class: 'sle-mark-text', x, y, 'font-size': size, 'text-anchor': anchor || 'middle', 'dominant-baseline': 'central' })
      node.textContent = value
      if (ink) node.style.fill = ink
      return node
    }
    if (item.kind === 'zone') {
      const c = zoneColor(item)
      const fill = el('rect', { class: 'sle-zone-fill', x: 0, y: 0, width: lw, height: lh, rx: 0.4 })
      fill.style.fill = c
      inner.append(fill)
      if (item.hatch) inner.append(el('rect', { x: 0, y: 0, width: lw, height: lh, fill: 'url(#sle-hatch)' }))
      // 테두리는 고른 모양(점선 처음 값·실선)이다. 고른 영역의 강조는 바깥에 띄운 강조 테(`sle-zone-select`, CSS 가 고를 때만
      // 보인다)라 테두리 모양과 섞이지 않는다.
      const border = el('rect', { class: item.borderStyle === 'solid' ? 'sle-zone-border is-solid' : 'sle-zone-border', x: 0, y: 0, width: lw, height: lh, rx: 0.4 })
      border.style.stroke = c
      const pad = 3 * upp
      inner.append(border, el('rect', { class: 'sle-zone-select', x: -pad, y: -pad, width: lw + pad * 2, height: lh + pad * 2, rx: 0.6 }))
      // 이름표 꼬리표는 위 변의 왼쪽(처음 값)·가운데·오른쪽이다.
      const caption = (item.label || '영역') + (item.keepOut ? ' · 설비 금지' : '')
      const tagW = Math.min(lw, emWidth(caption) * fs + fs * 0.9)
      const tagX = zoneTagX(lw, tagW, item.labelAlign)
      const tag = el('rect', { class: 'sle-zone-tag', x: tagX, y: 0, width: tagW, height: fs * 1.6, rx: 0.3 })
      inner.append(tag, text(caption, tagX + fs * 0.45, fs * 0.8, fs, 'start'))
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
      // 기둥: 이름이 없으면 X 두 줄, 있으면 X 없이 이름을 기둥 가운데에 쓴다(2026-10-16 사용자 결정 — 돌리지
      // 않는다). 글자는 자동이면 11px, 고르면 그 크기이고 기둥보다 길면 넘쳐 그린다(면색 테가 둘러 읽힌다).
      inner.append(el('rect', { class: 'sle-column', x: 0, y: 0, width: lw, height: lh }))
      if (!item.label) {
        inner.append(el('line', { class: 'sle-column-cross', x1: 0, y1: 0, x2: lw, y2: lh }))
        inner.append(el('line', { class: 'sle-column-cross', x1: lw, y1: 0, x2: 0, y2: lh }))
      }
    } else if (item.kind === 'text') {
      // 자동이면 상자에 맞추고(작아지면 숨김), 크기를 골랐으면 그 화면 px 로 쓴다(상자를 넘어도 그린다).
      const value = item.label || '글자'
      const size = item.fontSize ? fs : Math.min(lh * 0.7, (lw * 0.95) / Math.max(emWidth(value), 1))
      const node = text(value, lw / 2, lh / 2, size)
      node.style.display = !item.fontSize && size / upp < 6 ? 'none' : ''
      inner.append(node)
    } else if (item.kind === 'arrow') {
      // 동선: 왼쪽에서 오른쪽으로(0°). 굵기는 상자 높이를 따른다.
      const head = Math.min(lh * 1.1, lw * 0.35)
      const shaft = el('line', { class: 'sle-flow', x1: lh * 0.3, y1: lh / 2, x2: lw - head * 0.9, y2: lh / 2 })
      shaft.style.strokeWidth = String(Math.min(lh * 0.2, 5 * upp))
      inner.append(shaft, el('polygon', { class: 'sle-flow-head', points: `${lw - head},${lh * 0.15} ${lw},${lh / 2} ${lw - head},${lh * 0.85}` }))
    } else if (item.kind === 'block') {
      // 층 블록: 면(고른 색 또는 Space 기본 면)·테두리·가운데 글자 줄. 글자는 블록에 맞춰 줄이고 화면에서 13px 를
      // 넘지 않는다. 줄이 다 안 들어가면 이름 줄만, 그것도 6px 아래면 숨긴다(풍선·초점 이름에는 남는다).
      const fill = el('rect', { class: 'sle-block-fill', x: 0, y: 0, width: lw, height: lh, rx: 0.4 })
      const off = blockOff(item)
      group.classList.toggle('is-inactive', Boolean(off))
      // 고른 색은 팔레트가 캔버스 위에 미리 섞어 둔 불투명 면이다(반투명이면 뒤의 도면·격자가 비친다). 비활성 층 블록은
      // 고른 색 대신 회색 면(`block-off`, CSS)과 영역 빗금 무늬다 — 인라인 색을 달지 않는다.
      if (item.color && markColors[item.color] && !off) fill.style.fill = `var(--sle-block-tint-${item.color})`
      inner.append(fill)
      if (off) inner.append(el('rect', { class: 'sle-block-hatch', x: 0, y: 0, width: lw, height: lh, rx: 0.4, fill: 'url(#sle-hatch)' }))
      inner.append(el('rect', { class: 'sle-block-border', x: 0, y: 0, width: lw, height: lh, rx: 0.4 }))
      // 보기 FAB 의 키보드 초점은 지금 상태를 따른다 — 비활성이면 Tab 이 건너뛰게 초점·역할을 걷는다. 새 epoch 의
      // `buildMark` 가 보통 다시 세우지만(뷰어 epoch 에 상태 지문) 두 겹이다.
      if (VIEW && FAB && !opensFloor(item)) {
        group.removeAttribute('tabindex')
        group.removeAttribute('role')
        group.removeAttribute('aria-label')
      }
      const fitLines = (lines) => {
        const longest = Math.max(...lines.map(emWidth), 1)
        return Math.min((lh * 0.8) / (lines.length * 1.3), (lw * 0.9) / longest, 13 * upp)
      }
      // 글자 크기를 골랐으면 모든 줄을 그 크기로 쓴다(맞추거나 숨기지 않는다).
      let lines = blockLines(item)
      let size = item.fontSize ? fs : fitLines(lines)
      if (!item.fontSize && lines.length > 1 && size / upp < 7) {
        lines = lines.slice(0, 1)
        size = fitLines(lines)
      }
      const step = size * 1.3
      lines.forEach((value, k) => {
        const node = text(value, lw / 2, lh / 2 + (k - (lines.length - 1) / 2) * step, size)
        node.classList.add(k === 0 ? 'is-head' : 'is-sub')
        node.style.display = !item.fontSize && size / upp < 6 ? 'none' : ''
        inner.append(node)
      })
    }
    shape.append(inner)
    if (item.kind === 'column' && item.label) shape.append(text(item.label, cx, cy, fs))
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
    if (item.kind === 'block') {
      const words = blockTip(item)
      if (tip) tip.textContent = words
      if (group.hasAttribute('tabindex')) group.setAttribute('aria-label', words)
      return
    }
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
    const label = el('text', { class: 'sle-label' })
    label.textContent = item.label
    const tip = el('title')
    tip.textContent = unitTip(item)
    if (VIEW) {
      // 보기 화면의 의미 표시 — 테(반입 전 주황 점선·반출/이설 예정 노랑 두 겹)·정지 중 빗금·미확인 「!」·운영 비가동
      // 표식·겹침 꼭지·선택 후광. 무엇이 보일지는 class(`paintUnit`)와 CSS 가 정한다. 편집 화면에는 만들지 않는다
      // (편집의 테는 선택·묶음·다른 층·겹침 전용).
      const parts = {
        halo: el('rect', { class: 'sle-halo', rx: 0.8 }),
        hatch: el('rect', { class: 'sle-hatch', rx: 0.4, fill: 'url(#sle-unit-hatch)' }),
        ringOut: el('rect', { class: 'sle-ring-out', rx: 0.4 }),
        ring: el('rect', { class: 'sle-ring', rx: 0.4 }),
        offline: el('g', { class: 'sle-offline' }),
        offlineDot: el('circle', { class: 'sle-offline-dot' }),
        offlineBars: [el('rect', { class: 'sle-offline-bar' }), el('rect', { class: 'sle-offline-bar' })],
        flag: el('g', { class: 'sle-flag' }),
        flagDot: el('circle', { class: 'sle-flag-dot' }),
        flagText: el('text', { class: 'sle-flag-text' }),
        corner: el('polygon', { class: 'sle-corner' }),
      }
      parts.flagText.textContent = '!'
      parts.offline.append(parts.offlineDot, ...parts.offlineBars)
      parts.flag.append(parts.flagDot, parts.flagText)
      group.__parts = parts
      group.append(parts.halo, rect, parts.hatch, parts.ringOut, parts.ring, label, parts.offline, parts.flag, parts.corner, tip)
    } else {
      group.append(rect, label, tip)
    }
    appendHandles(group)
    paintUnit(group, item)
    position(group, item)
    group.__tipAt = `${S.asOf}|${S.dataAsOf}`
    S.groups.set(item.id, group)
    return group
  }

  // 면·글자 색과 보기 화면의 의미 class 를 기준일로 다시 정한다. 의미 class 는 보기 화면에만 단다 — 편집 화면은
  // 채우기만 같은 규칙이고 테·덧표시를 그리지 않는다. 테는 실물 없음(is-pre)이 반출/이설 예정(is-exitplan)을 이긴다.
  // 판정·색을 한 글자 부호로 모아 지난 칠과 같으면 DOM 을 건드리지 않는다 — 페이더를 끄는 프레임마다 모든 호기를
  // 부르지만 실제로 바뀐 상자만 고친다.
  function paintUnit(group, item) {
    const st = unitState(item, S.asOf)
    const look = unitColors(item, st)
    // 층 상세 보기에서 그날 보이는 호기와 겹친 반입 예정 호기는 숨긴다(`coveredBy`). 숨긴 호기의 몫은 요약 줄에 센다.
    const covered = VIEW && !FAB && coveredAt(item, st)
    const code = `${look.fill}|${look.ink}|${+st.visible}${+st.real}${+st.exitPlan}${+st.stopped}${+st.flag}${+st.offline}${+covered}`
    group.__visible = st.visible && !covered
    if (covered) S.covered.set(item.id, item.share)
    else S.covered.delete(item.id)
    if (group.__paint === code) return
    group.__paint = code
    group.querySelector('.sle-rect').style.fill = look.fill
    group.querySelector('.sle-label').style.fill = look.ink
    if (!VIEW) return
    group.classList.toggle('is-gone', !st.visible)
    group.classList.toggle('is-covered', covered)
    group.classList.toggle('is-pre', !st.real)
    group.classList.toggle('is-exitplan', st.real && st.exitPlan)
    group.classList.toggle('is-stopped', st.stopped)
    group.classList.toggle('has-flag', st.flag)
    group.classList.toggle('is-offline', st.offline)
  }

  function buildMark(item) {
    const group = el('g', { class: `sle-item sle-mark mark-${item.kind}` })
    group.dataset.id = item.id
    group.append(el('g', { class: 'sle-mark-shape' }), el('rect', { class: 'sle-rect sle-mark-box' }), el('title'))
    if (opensFloor(item)) {
      // 보기 전용 FAB 의 층 블록은 키보드로도 연다 — Tab 초점, Enter/Space 로 열기. 초점이 오면 선택 줄에 알린다.
      group.setAttribute('tabindex', '0')
      group.setAttribute('role', 'button')
      group.onfocus = () => { if (S.showBlockHint) S.showBlockHint(group) }
      group.onblur = () => { if (S.showBlockHint) S.showBlockHint(null) }
    }
    appendHandles(group)
    position(group, item)
    // 영역은 이름표로도 잡는다(안쪽은 비워 둔다) — 이름표만 눌림을 받게 한다.
    S.groups.set(item.id, group)
    return group
  }

  // 트레이 칩. 묶음은 칩 하나다(대표 = 처음 만난 모듈).
  // 서랍 칩은 보이는 이름의 오름차순이다(2026-10-08 사용자 요청). 숫자는 수로 견준다 — `EQ2` 가 `EQ10` 앞.
  const TRAY_ORDER = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' })
  const chipName = (entry) => String(entry.lead.group || entry.lead.label || '')

  // 서랍에 뜰 호기 — 미배치이고 다른 층으로 보내지 않은 것. 도면에 선 모듈이 있는 묶음의 좌표 없는 모듈(상자를 한 모듈에만
  // 그린 옛 설비)은 따로 내놓지 않는다 — 그 묶음을 옮기거나 키우면 바둑판 제 칸에 함께 놓인다.
  function trayKeep() {
    const standing = new Set()
    for (const m of S.items.values()) if (isUnit(m) && m.group && onCanvas(m)) standing.add(m.group)
    return (m) => !m.placed && !m.moveTo && !(m.group && standing.has(m.group))
  }

  function trayEntries(keep) {
    const seen = new Set()
    const out = []
    for (const item of S.items.values()) {
      if (!isUnit(item) || !keep(item) || seen.has(item.id)) continue
      const list = item.group ? members(item).filter(keep) : [item]
      for (const m of list) seen.add(m.id)
      out.push({ lead: item, list })
    }
    return out.sort((a, b) => TRAY_ORDER.compare(chipName(a), chipName(b)))
  }

  // 서랍 검색 — 찾는 호기만 남겨 바로 끌어 놓게 한다(2026-10-08 사용자 요청). 묶음 이름·호기 이름 어느 쪽에
  // 들어 있어도 맞고 대소문자는 가리지 않는다. 검색어는 같은 편집기의 다음 실행에도 이어진다(S 에 둔다).
  function trayMatches(entry) {
    const query = String(S.trayQuery || '').trim().toLowerCase()
    if (!query) return true
    const names = [entry.lead.group, entry.lead.label, ...entry.list.map((m) => m.label)]
    return names.some((name) => String(name || '').toLowerCase().includes(query))
  }

  // 그려 둔 칩에 검색을 건다 — 목록을 다시 만들지 않고 칩만 감춘다. 수는 「보이는/전체」로 적는다.
  function applyTrayFilter() {
    let total = 0
    let shown = 0
    for (const chip of trayList.children) {
      const units = chip.__entry ? chip.__entry.list.length : 0
      const visible = !chip.__entry || trayMatches(chip.__entry)
      chip.hidden = !visible
      total += units
      if (visible) shown += units
    }
    const searching = Boolean(String(S.trayQuery || '').trim())
    trayCount.textContent = searching ? `${shown}/${total}대` : `${total}대`
    trayEmpty.hidden = !(searching && total > 0 && shown === 0)
  }

  function buildChip({ lead, list }, leaving) {
    const chip = document.createElement('div')
    chip.className = 'sle-chip'
    chip.dataset.id = lead.id
    chip.__ids = list.map((m) => m.id)
    chip.__entry = { lead, list }
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
    chip.title = lead.group ? `${list.map((m) => m.label).join(', ')} — 함께 놓입니다${list.length >= 2 ? '(범위 안 바둑판)' : ''}` : lead.label
    chip.onpointerdown = (event) => {
      // Ctrl(⌘)을 누른 채 누르면 서랍 안에서 한 대씩 더하거나 빼고, Shift 는 기준 칩(마지막으로 그냥·Ctrl 로 누른 칩)부터 그
      // 칩까지 지금 보이는 차례로 고른다(Ctrl+Shift 는 그 범위를 더한다). 고른 칩 하나를 끌면 고른 것이 모두 함께 놓인다.
      const keys = { ctrl: event.ctrlKey || event.metaKey, shift: event.shiftKey }
      const picked = pickedTrayEntries()
      const together = picked.length > 1 && picked.some((entry) => entry.lead.id === lead.id)
      const units = together ? picked.reduce((n, entry) => n + entry.list.length, 0) : 0
      const dropping = together ? picked.flatMap((entry) => entry.list) : list
      ghostDrag(
        event,
        together ? `${picked.length}개 함께 (${units}대)` : lead.group ? `${lead.group} (모듈 ${list.length})` : lead.label,
        (p, free) => (together ? placeManyFromTray(lead, picked, p, free) : placeFromTray(lead, list, p, undefined, free)),
        () => pickChip(lead, list, keys),
        () => trayPlan(dropping).footprint,
      )
    }
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
    // 서랍 목록을 비웠다 다시 채우는 동안 목록 높이가 줄어 브라우저가 서랍 스크롤을 맨 위로 잘라 낸다. 놓은 뒤에도
    // 보던 자리에서 이어 놓게 그 자리를 기억했다 되돌린다(2026-10-08 사용자 요청).
    const trayScroll = trayBox.scrollTop
    layer.replaceChildren()
    zonesLayer.replaceChildren()
    marksLayer.replaceChildren()
    trayList.replaceChildren()
    leavingList.replaceChildren()
    S.groups = new Map()
    // 보기 화면은 기준일이 바뀌어도 숨김이 바뀐 호기의 짝만 다시 보도록 겹침 짝을 새로 만든다(그린 호기·자리가 바뀌는 때는
    // 여기뿐이다). 상자를 칠하기(`paintUnit` — 겹친 반입 예정 숨김이 짝을 본다) 전에 비운다.
    S.adjacency = null
    S.covered = new Map()
    // 모듈 묶음의 모듈 상자에는 손잡이가 없다(`is-module` — 크기는 묶음 범위 테두리의 손잡이로 바꾼다).
    const counts = groupCounts()
    for (const item of S.items.values()) {
      if (!onCanvas(item)) continue
      if (isUnit(item)) {
        const group = buildGroup(item)
        group.classList.toggle('is-module', (counts.get(groupKeyOf(item)) || 0) >= 2)
        layer.append(group)
      } else (item.kind === 'zone' ? zonesLayer : marksLayer).append(buildMark(item))
    }
    let trayN = 0
    for (const entry of trayEntries(trayKeep())) {
      trayN += entry.list.length
      trayList.append(buildChip(entry, false))
    }
    const leaving = trayEntries((m) => Boolean(m.moveTo))
    let leavingN = 0
    for (const entry of leaving) {
      leavingN += entry.list.length
      leavingList.append(buildChip(entry, true))
    }
    leavingBox.hidden = leaving.length === 0
    applyTrayFilter()
    drawerCount.textContent = leavingN ? `${trayN} · 보냄 ${leavingN}` : String(trayN)
    trayBox.scrollTop = trayScroll
    // 보기 화면은 기준일이 바뀌어도 바뀐 호기만 칠하도록 경계 날짜 목록을 새로 만든다.
    if (VIEW && !FAB) buildEvents()
    markSelection()
    markOverlaps()
    showSummary()
  }

  // 단계·라벨은 같은 epoch 안에서도 바뀐다(테마 전환·기준일). 기하는 그대로 두고 칠·글자만 다시 쓴다.
  function repaint() {
    for (const [id, group] of S.groups) {
      const item = S.items.get(id)
      if (!item) continue
      if (isUnit(item)) {
        paintUnit(group, item)
        group.querySelector('.sle-label').textContent = item.label
        group.querySelector('title').textContent = unitTip(item)
      }
      position(group, item)
    }
    if (VIEW) markOverlaps()
    for (const chip of host.querySelectorAll('.sle-chip')) {
      const item = S.items.get(chip.dataset.id)
      if (!item) continue
      chip.querySelector('.sle-chip-swatch').style.background = color(item)
      chip.querySelector('.sle-chip-name').textContent = item.group || item.label
      // 서랍 칩의 풍선(호기 이름, 묶음은 모듈 이름 목록)도 이름 바꿈을 따라간다. 보낸 칩은 따로 적는다.
      if (!chip.classList.contains('is-leaving') && chip.__entry && !item.group) chip.title = item.label
    }
  }

  function redrawMarks() {
    for (const [id, group] of S.groups) {
      const item = S.items.get(id)
      if (item && isMark(item)) position(group, item)
    }
  }

  // 판정이 바뀌는 날(경계 날짜)의 목록 — [날, 호기] 를 날 차례로(보기 화면, 새 epoch·받은 값이 바뀐 회차마다). 두 기준일
  // 사이(앞날 < 날 ≤ 뒷날)에 날이 든 호기만 판정이 바뀐다. 운영 비가동은 끝날까지 포함이라 그 다음 날에 바뀐다.
  function buildEvents() {
    const events = []
    for (const item of S.items.values()) {
      if (!isUnit(item)) continue
      const add = (day) => { if (day) events.push([day, item.id]) }
      add(item.realFrom)
      add(item.exitOn)
      add(item.stopOn)
      for (const [from, until] of item.delays || []) { add(from); add(until) }
      for (const [from, until] of item.offline || []) { add(from); if (until) add(isoOf(dayNumber(until) + 1)) }
    }
    events.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    S.events = events
  }
  function changedBetween(a, b) {
    const lo = a < b ? a : b
    const hi = a < b ? b : a
    const events = S.events || []
    let low = 0
    let high = events.length
    while (low < high) {
      const mid = (low + high) >> 1
      if (events[mid][0] <= lo) low = mid + 1
      else high = mid
    }
    const ids = new Set()
    for (let k = low; k < events.length && events[k][0] <= hi; k += 1) ids.add(events[k][1])
    return ids
  }

  // 판정 부호를 견주어 바뀐 상자만 class·면·글자색을 고친다(`paintUnit`). `ids` 가 없으면 모든 호기다. 기하·이름표
  // 크기(`position`)는 건드리지 않는다. 숨김이 바뀐 때만 겹침을 다시 센다.
  function paintUnits(ids) {
    const flipped = []
    const paintOne = (id) => {
      const group = S.groups.get(id)
      const item = S.items.get(id)
      if (!group || !item || !isUnit(item)) return
      const was = group.__visible
      paintUnit(group, item)
      if (was !== group.__visible) flipped.push(id)
    }
    if (ids) {
      // 겹친 반입 예정 숨김은 이웃의 판정에도 달렸다 — 판정이 바뀐 호기와 넓이가 겹치는 이웃도 다시 본다.
      const near = new Set(ids)
      if (VIEW && !FAB) {
        const pairs = overlapPairs()
        for (const id of ids) for (const other of pairs.get(id) || []) near.add(other)
      }
      for (const id of near) paintOne(id)
    } else for (const id of S.groups.keys()) paintOne(id)
    if (flipped.length) markOverlaps(flipped)
    // 기준일에 묶음이 통째로 보이거나 숨으면 Main 설비명도 따라간다.
    if (flipped.some((id) => S.items.get(id)?.group)) drawGroupNames()
    if (S.selection.size) updateStatus()
    showSummary()
  }
  // 칠한 날이 `previous` 에서 S.asOf 로 옮겨 갔다(페이더 프레임·놓은 뒤 파이썬이 따로 바꾼 날) — 그 사이에 경계 날짜가
  // 든 호기만 다시 칠한다. 1천여 호기를 프레임마다 다 돌지 않는다.
  function paintAsOf(previous) {
    paintUnits(previous && S.events ? changedBetween(previous, S.asOf) : null)
  }

  // 풍선 글은 올려 둘 때 쓴다 — 페이더를 끄는 프레임마다 1천여 호기의 풍선을 다시 쓰지 않는다. 칠한 날·파이썬의 날이
  // 그대로이고 받은 값이 바뀌지 않았으면 그대로 둔다.
  function freshenTip(group) {
    const stamp = `${S.asOf}|${S.dataAsOf}`
    if (group.__tipAt === stamp) return
    const item = S.items.get(group.dataset.id)
    const tip = group.querySelector('title')
    if (!item || !isUnit(item) || !tip) return
    group.__tipAt = stamp
    tip.textContent = unitTip(item)
  }

  // 같은 epoch 회차에 받은 호기 값이 쥔 값과 같은가 — 단계·공정 글자·이름표·면·글자·경계 날짜·설비지분을 견준다.
  const sameSpans = (a, b) => a.length === b.length && a.every((span, k) => span[0] === b[k][0] && span[1] === b[k][1])
  const sameLook = (o, n) => o.stage === n.stage && o.detail === n.detail && o.label === n.label
    && o.fill === n.fill && o.ink === n.ink && Boolean(o.storage) === Boolean(n.storage) && Boolean(o.flag) === Boolean(n.flag)
    && o.realFrom === n.realFrom && o.exitOn === n.exitOn && o.stopOn === n.stopOn && o.share === n.share
    && sameSpans(o.delays || [], n.delays || []) && sameSpans(o.offline || [], n.offline || [])

  // 보기 화면의 같은 epoch 회차 — 받은 값이 바뀐 호기만 고친다. 이름표가 바뀐 호기만 자리·글자 크기를 다시 맞추고, 풍선은
  // 다음에 올려 둘 때 새로 쓴다. 칠한 날이 옮겨 갔으면(`previous` — 파이썬이 따로 바꾼 날) 그 사이 경계 날짜가 든 호기도
  // 다시 칠한다. 받은 경계 날짜가 바뀌었으면 날 목록을 다시 만든다.
  function refreshUnits(touched, previous) {
    for (const item of touched) {
      const group = S.groups.get(item.id)
      if (!group) continue
      group.__tipAt = null
      const label = group.querySelector('.sle-label')
      if (label && label.textContent !== item.label) {
        label.textContent = item.label
        position(group, item)
      }
    }
    if (touched.length) buildEvents()
    if (!touched.length && !previous) {
      if (S.selection.size) updateStatus()
      return
    }
    if (previous === '*') {
      paintUnits(null)
      return
    }
    const ids = previous ? changedBetween(previous, S.asOf) : new Set()
    for (const item of touched) ids.add(item.id)
    paintUnits(ids)
  }

  function isChanged(item) {
    const o = S.original.get(item.id)
    if (!o) return true
    if (isMark(item)) {
      return !sameGeometry(o, item) || o.rot !== item.rot || o.label !== item.label
        || o.color !== item.color || o.hatch !== item.hatch || o.keepOut !== item.keepOut
        || (o.link || '') !== (item.link || '')
        || (o.fontSize ?? null) !== (item.fontSize ?? null) || (o.fontColor || '') !== (item.fontColor || '')
        || pickOr(o.borderStyle, BORDER_STYLES) !== pickOr(item.borderStyle, BORDER_STYLES)
        || pickOr(o.labelAlign, LABEL_ALIGNS) !== pickOr(item.labelAlign, LABEL_ALIGNS)
    }
    if ((o.moveTo || null) !== (item.moveTo || null)) return true
    if (o.placed !== item.placed) return true
    // 미배치끼리는 크기만 견준다 — 놓고 키운 뒤 다시 빼면 새 크기가 남는데, 그것도 보내야 한다.
    // 추정 크기로 놓았다 그냥 뺀 호기는 NaN 으로 돌아가므로 NaN 끼리는 같다고 본다.
    if (!item.placed) return !sameSize(o, item)
    return !sameGeometry(o, item)
  }
  // 이름을 바꿨는가(설비명, 또는 모듈 묶음의 Main 설비). 배치 변경과 따로 보낸다 — 이름만 바꾼 호기는 `changes` 에
  // 넣지 않는다. 편집기에서 새로 넣은 호기는 이름을 고쳐도 그 이름의 새 호기다(바꿈이 아니다).
  function isRenamed(item) {
    if (!isUnit(item) || item.created) return false
    const o = S.original.get(item.id)
    return Boolean(o) && (o.label !== item.label || (o.group || null) !== (item.group || null))
  }
  // 적용값의 `renames`. 설비명은 호기마다, Main 설비는 묶음마다 한 항목이다. 자기 설비명을 Main 설비로 적은 한 행짜리
  // 묶음은 설비명 한 항목이다(파이썬이 Main 설비를 따라 바꾼다).
  function renames() {
    const out = []
    const groups = new Map()
    for (const item of S.items.values()) {
      if (!isRenamed(item)) continue
      const o = S.original.get(item.id)
      if (o.label !== item.label) out.push({ kind: 'unit', from: item.id, to: item.label })
      else if (o.group && !groups.has(o.group)) groups.set(o.group, item.group)
    }
    for (const [from, to] of groups) out.push({ kind: 'group', from, to })
    return out
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
    // Main 설비명도 범위를 따라간다 — 자리·크기·배율이 바뀌는 길이 모두 여기를 지난다.
    drawGroupNames()
    overlay.replaceChildren()
    const chosen = selectedItems()
    const list = expanded(chosen)
    const mods = !VIEW && chosen.length === 1 ? moduleMembers(chosen[0]) : null
    const range = mods ? groupRange(mods) : null
    if (range) {
      // 편집에서 고른 모듈 묶음 하나: 범위 테두리와 그 손잡이 여덟(모듈 상자에는 손잡이가 없다). 손잡이는 화면 px 로
      // 크기를 정하고, 작은 범위에서는 변 가운데 손잡이를 감춘다(호기 손잡이와 같은 규칙). 보기 화면은 그대로다.
      const top = H() - (range.y + range.h)
      overlay.append(el('rect', { class: 'sle-group-box is-range', x: range.x, y: top, width: range.w, height: range.h }))
      // 숨은 모듈이 차지한 칸은 점선으로만 보인다(그 모듈은 그리지 않는다).
      for (const g of mods.filter((m) => m.ghost && onCanvas(m))) {
        overlay.append(el('rect', { class: 'sle-ghost-cell', x: g.x, y: H() - (g.y + g.h), width: g.w, height: g.h }))
      }
      const hs = HANDLE_PX * unitsPerPx()
      for (const dir of HANDLE_DIRS) {
        const hx = dir.includes('w') ? range.x : dir.includes('e') ? range.x + range.w : range.x + range.w / 2
        const hy = dir.includes('n') ? top : dir.includes('s') ? top + range.h : top + range.h / 2
        const tooSmall = (dir === 'n' || dir === 's') ? range.w < hs * 3 : range.h < hs * 3
        if (dir.length === 1 && tooSmall) continue
        const handle = el('rect', { class: 'sle-handle sle-range-handle', x: hx - hs / 2, y: hy - hs / 2, width: hs, height: hs })
        handle.dataset.dir = dir
        handle.style.cursor = HANDLE_CURSORS[dir]
        overlay.append(handle)
      }
    } else if (list.length >= 2) {
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
    const chosen = selectedItems()
    const together = new Set(expanded(chosen).map((m) => m.id))
    // 편집에서 모듈 묶음은 모듈 하나를 골라도 묶음째 골라진 것이다 — 모듈 상자는 모두 「함께」 테만 두르고 손잡이는 범위
    // 테두리에 선다. 보기 화면은 누른 모듈이 골라진 것 그대로다(후광).
    const counts = VIEW ? new Map() : groupCounts()
    const bundles = new Set(chosen.filter((m) => isUnit(m) && m.group && counts.get(groupKeyOf(m)) >= 2).map((m) => m.group))
    for (const [id, group] of S.groups) {
      const item = S.items.get(id)
      const selected = S.selection.has(id) && !(item && item.group && bundles.has(item.group))
      group.classList.toggle('is-selected', selected)
      group.classList.toggle('is-grouped', together.has(id) && !selected)
    }
    // 여러 개를 고르면 크기 손잡이를 감춘다(크기는 숫자 칸·Ctrl+방향키로 함께 바꾼다).
    svg.classList.toggle('is-multi', S.selection.size > 1)
    for (const chip of trayList.children) chip.classList.toggle('is-selected', Boolean(chip.__ids?.some((id) => S.selection.has(id))))
    drawSelectionBox()
  }

  const overlaps = (p, q2) => p.x < roundTo(q2.x + q2.w) && q2.x < roundTo(p.x + p.w)
    && p.y < roundTo(q2.y + q2.h) && q2.y < roundTo(p.y + p.h)

  // 겹침은 막지 않고 알린다(저장도 된다). 호기끼리, 그리고 호기와 반입구·문·기둥·설비 금지 영역.
  function markOverlaps(flipped) {
    if (VIEW) {
      // 보기 전용: 호기끼리 겹친 것만 오른쪽 위 꼭지 삼각으로 알린다 — 완전히 겹치면 아래 호기가 보이지도
      // 눌리지도 않는데 범례·요약은 그것을 센다. 테는 실물·반출/이설 뜻을 싣으므로 겹침은 테가 아니다. 반입구·문
      // 가림과 개수 문구는 편집 화면의 몫이다. 기준일에 보이지 않는 호기는 견주지 않는다. 보기에서는 자리가 바뀌지 않으므로
      // 겹치는 짝은 한 번 구해 두고(`overlapPairs`), 기준일이 바뀌면 보이는 짝이 남았는지만 본다(O(n²)를 되풀이하지 않는다).
      const pairs = overlapPairs()
      const shown = (id) => {
        const group = S.groups.get(id)
        return Boolean(group) && group.__visible !== false
      }
      // 숨김이 바뀐 호기(`flipped`)가 있으면 그 호기와 짝만 다시 본다.
      let targets = S.groups.keys()
      if (flipped) {
        const near = new Set(flipped)
        for (const id of flipped) for (const other of pairs.get(id) || []) near.add(other)
        targets = near
      }
      for (const id of targets) {
        const group = S.groups.get(id)
        if (!group) continue
        const hit = shown(id) && (pairs.get(id) || []).some(shown)
        if (group.classList.contains('is-overlap') === hit) continue
        group.classList.toggle('is-overlap', hit)
        // 「!」는 겹침 삼각 옆으로 비킨다.
        const item = S.items.get(id)
        if (item && isUnit(item)) positionUnitMarks(group, item, svgTop(item))
      }
      S.overlapPairs = 0
      S.blocked = 0
      return
    }
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

  // 층 상세 보기에서 기준일 판정 st 의 호기를 겹친 반입 예정으로 숨기는가(`coveredBy`). 이웃은 넓이가 겹치는 호기(`overlapPairs`)다.
  function coveredAt(item, st) {
    const neighbours = (overlapPairs().get(item.id) || []).map((id) => S.items.get(id)).filter(Boolean)
    return coveredBy(item, st, neighbours, (other) => unitState(other, S.asOf))
  }
  // 도구 줄 오른쪽 한 줄 요약(파이썬 `summary` — 배치·미배치·점유율)에 겹쳐 숨긴 반입 예정 대수를 붙인다. 숨김은 기준일마다
  // 브라우저가 정하므로(페이더를 끄는 동안에도) 붙이는 것도 브라우저다. 범례 대수는 그대로다.
  function showSummary() {
    const base = String(data.summary || '')
    let hidden = 0
    for (const share of S.covered.values()) hidden += share
    const text = hidden > 0 ? `${base} · 겹쳐 숨긴 반입 예정 ${unitCountText(hidden)}대` : base
    const node = q('.sle-summary')
    setText(node, text)
    // 좁은 FAB 도구 줄에서는 요약도 말줄임으로 줄 수 있다(`fitFabBar`) — 풍선에 온 글.
    setAttr(node, 'title', text)
  }
  // 보기 화면의 호기 겹침 짝(호기 → 겹치는 호기들). 격자 칸에 나눠 담아 같은 칸끼리만 견준다. 그린 호기가 바뀔 때
  // (`renderItems`)만 다시 만든다.
  const OVERLAP_CELL = 8
  function overlapPairs() {
    if (S.adjacency) return S.adjacency
    const pairs = new Map()
    const cells = new Map()
    for (const unit of S.items.values()) {
      if (!isUnit(unit) || !onCanvas(unit)) continue
      pairs.set(unit.id, [])
      const seen = new Set()
      const x0 = Math.floor(unit.x / OVERLAP_CELL)
      const x1 = Math.floor((unit.x + unit.w) / OVERLAP_CELL)
      const y0 = Math.floor(unit.y / OVERLAP_CELL)
      const y1 = Math.floor((unit.y + unit.h) / OVERLAP_CELL)
      for (let gx = x0; gx <= x1; gx += 1) {
        for (let gy = y0; gy <= y1; gy += 1) {
          const key = `${gx},${gy}`
          const bucket = cells.get(key)
          if (!bucket) { cells.set(key, [unit]); continue }
          for (const other of bucket) {
            if (seen.has(other.id)) continue
            seen.add(other.id)
            if (overlaps(unit, other)) { pairs.get(unit.id).push(other.id); pairs.get(other.id).push(unit.id) }
          }
          bucket.push(unit)
        }
      }
    }
    S.adjacency = pairs
    return pairs
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
      // 새 호기는 지금 이름으로 만든다(적용 전에 이름을 고쳤을 수 있다). 있던 호기는 옛 설비명이다.
      const change = { id: item.created ? item.label : item.id, placed: item.placed }
      if (item.created) change.created = item.created
      if (item.moveTo) change.moveTo = item.moveTo
      if (Number.isFinite(item.w) && Number.isFinite(item.h)) Object.assign(change, { w: item.w, h: item.h })
      if (item.placed) Object.assign(change, { x: item.x, y: item.y })
      out.push(change)
    }
    return out
  }

  // 묶음과 함께 옮겨진 숨은 모듈의 새 자리(파이썬 `EditorApply.hidden_moves`).
  function ghostChanges() {
    const out = []
    for (const g of S.ghosts.values()) {
      const o = S.original.get(g.id)
      if (o && sameGeometry(o, g)) continue
      out.push({ id: g.id, x: g.x, y: g.y, w: g.w, h: g.h })
    }
    return out
  }

  // 그리지 못한 요소(모르는 종류·숫자 아님)도 그대로 돌려보낸다 — 층 단위 교체라 빼면 지워진다.
  const marksPayload = () => [
    ...[...S.items.values()].filter(isMark).map((m) => ({
      id: m.id, kind: m.kind, x: m.x, y: m.y, w: m.w, h: m.h, rot: m.rot || 0,
      label: m.label || '', color: m.color || '', hatch: Boolean(m.hatch), keepOut: Boolean(m.keepOut),
      fontSize: m.fontSize ?? null, fontColor: m.fontColor || '',
      borderStyle: pickOr(m.borderStyle, BORDER_STYLES), labelAlign: pickOr(m.labelAlign, LABEL_ALIGNS),
      ...(m.kind === 'block' ? { link: m.link || '' } : {}),
    })),
    ...S.passthrough,
  ]

  // 고른 모듈 묶음의 한 줄 — Main 설비·모듈 수·바둑판(옛 묶음이면 「n등분이 아님」).
  function moduleCaption(item) {
    const mods = moduleMembers(item)
    const [cols, rows] = moduleGrid(mods.length)
    const loose = untiledModules(item)
    const hidden = mods.filter((m) => m.ghost).length
    return `Main 설비 ${item.group} · 모듈 ${mods.length} (${cols}×${rows} 바둑판${hidden ? ` · 숨은 모듈 ${hidden}` : ''})`
      + (loose ? ` · ${mods.length}등분이 아님 — 옮기거나 크기를 바꾸면 범위 안에 다시 놓입니다` : '')
  }
  // 도면에 선 모듈 묶음인데 바둑판이 아니면 그 모듈들(옛 데이터 — 읽을 때 바꾸지 않는다), 아니면 null.
  function untiledModules(item) {
    const mods = moduleMembers(item)
    return mods && groupRange(mods) && !isTiled(mods) ? mods : null
  }

  function syncInspector() {
    const chosen = selectedItems()
    const multi = chosen.length > 1
    const standing = chosen.filter(onCanvas)
    const editable = chosen.length > 0 && standing.length === chosen.length
    const single = chosen.length === 1 ? chosen[0] : null
    inspector.classList.toggle('is-empty', chosen.length === 0)
    if (!chosen.length) {
      inspectorName.textContent = FAB ? '— 도면에서 고르세요(빈 곳을 끌면 여러 개)' : '— 도면이나 트레이에서 고르세요(빈 곳을 끌면 여러 개)'
    } else if (multi) {
      const together = expanded(chosen).length
      inspectorName.textContent = `${chosen.length}개${together > chosen.length ? ` (모듈 묶음까지 ${together}개)` : ''}`
    } else if (isMark(single)) {
      inspectorName.textContent = `${MARK_KINDS[single.kind].name}${single.label ? ` · ${single.label}` : ''}`
    } else if (moduleMembers(single)) {
      inspectorName.textContent = moduleCaption(single)
    } else if (single.group) {
      inspectorName.textContent = `${single.label} · Main 설비 ${single.group} (모듈 ${members(single).length})`
    } else {
      inspectorName.textContent = single.label
    }
    // 이름 줄은 한 줄 말줄임이다 — 다 못 보이는 글(모듈 묶음의 「n등분이 아님 …」)은 풍선으로.
    setAttr(inspectorName, 'title', inspectorName.textContent)
    const box = editable ? movePlan(standing).box : null
    // 모듈 묶음은 묶음 범위가 곧 그 위치·크기다(고치면 범위를 고친다 — 모듈 하나의 값은 보이지도 고치지도 않는다).
    const extent = (m) => {
      const mods = moduleMembers(m)
      return (mods && groupRange(mods)) || m
    }
    for (const input of fieldInputs) {
      input.disabled = !editable
      input.step = String(S.step)
      input.placeholder = ''
      if (!editable) { input.value = ''; continue }
      if (isFocused(input)) continue
      const field = input.dataset.field
      if (!multi) { input.value = String(extent(single)[field]); continue }
      // 여러 개: X·Y 는 함께 움직일 범위의 왼쪽 아래, 폭·높이는 모두 같을 때만 값을 보인다.
      if (field === 'x') { input.value = String(roundTo(box.minX)); continue }
      if (field === 'y') { input.value = String(roundTo(box.minY)); continue }
      const values = new Set(standing.map((m) => extent(m)[field]))
      input.value = values.size === 1 ? String([...values][0]) : ''
      input.placeholder = values.size === 1 ? '' : '여러 값'
    }
    const known = [...moveSelect.options].map((o) => o.value).join('|')
    if (known !== OTHER_FLOORS.join('|')) {
      moveSelect.replaceChildren(...OTHER_FLOORS.map((floor) => new Option(floor, floor)))
    }
    const units = chosen.filter(isUnit)
    sendBox.hidden = FAB || (chosen.length > 0 && units.length === 0)
    const canSend = units.length > 0 && units.every((m) => !m.moveTo) && OTHER_FLOORS.length > 0
    moveSelect.disabled = !canSend
    moveButton.disabled = !canSend
    // 바둑판이 아닌 옛 모듈 묶음 하나를 골랐으면 「범위에 맞춰 n등분」(옮기거나 키울 때와 같은 다시 놓기).
    const loose = single ? untiledModules(single) : null
    moduleTile.hidden = !loose
    moduleTile.disabled = !loose
    if (loose) setText(moduleTile, `범위에 맞춰 ${loose.length}등분`)
    // 모듈 묶음 하나를 골랐으면 「Main 설비명 위치」(가운데·위·아래). 다른 층으로 보낸 묶음은 이 층에 이름이 없다.
    const bundleItem = single && isUnit(single) && !single.moveTo && moduleMembers(single) ? single : null
    groupNameBox.hidden = !bundleItem
    groupNamePos.disabled = !bundleItem
    if (bundleItem) groupNamePos.value = groupLabelOf(groupKeyOf(bundleItem))
    // 이름: 호기 하나를 골랐을 때만. 모듈 묶음이면 그 Main 설비(묶음 이름)를 고친다.
    const named = single && isUnit(single) && !single.moveTo ? single : null
    unitLabel.disabled = !named
    if (!isFocused(unitLabel)) unitLabel.value = named ? renameTarget(named).name : ''
    unitLabel.title = !named
      ? '호기 하나를 고르면 이름을 바꿉니다'
      : (renameTarget(named).bundle
        ? '모듈 묶음의 Main 설비 이름입니다 — 묶음의 모든 모듈 행(편집기에 없는 형제 포함)에 적용됩니다.'
        : '설비명입니다 — 적용·저장하면 설비 마스터의 설비명이 바뀌고 비가동 일정이 따라갑니다.')
        + ' 설비 마스터 전체(다른 층·미배치 포함)의 설비명·Main 설비와 겹칠 수 없고, 대소문자·앞뒤 공백만 다른'
        + ' 이름도 같은 이름입니다. Enter·칸 밖 누르기로 바꾸고 Esc 로 되돌립니다'
    const mark = single && isMark(single) ? single : null
    markProps.hidden = !mark
    // 색 목록은 처음부터 채운다 — 숨긴 칸도 자리를 차지하니 처음 고를 때 넓어지면 칸 줄이 한 번 튄다.
    if (!markColor.options.length) {
      markColor.replaceChildren(...Object.keys(markColors).map((key) => new Option(ZONE_COLOR_NAMES[key] || key, key)))
    }
    // 글자 크기·색(모든 도면 요소). 같은 까닭으로 처음부터 채운다.
    if (!markFontSize.options.length) {
      markFontSize.replaceChildren(new Option('자동', ''), ...FONT_SIZES.map((size) => new Option(`${size}px`, String(size))))
      markFontColor.replaceChildren(
        new Option('기본', ''),
        ...Object.keys(markColors).map((key) => new Option(ZONE_COLOR_NAMES[key] || key, key)),
      )
    }
    // 층 블록(FAB): 연결 층·색(기본 + 영역과 같은 여섯 색)·[열기]. 목록은 처음부터 채운다(칸 폭이 튀지 않게).
    if (FAB && !blockLink.options.length) {
      blockLink.replaceChildren(...LINK_TARGETS.map((target) => new Option(target, target)))
      blockColor.replaceChildren(
        new Option('기본', ''),
        ...Object.keys(markColors).map((key) => new Option(ZONE_COLOR_NAMES[key] || key, key)),
      )
    }
    blockProps.hidden = !mark || mark.kind !== 'block'
    if (mark) {
      if (!isFocused(markLabel)) markLabel.value = mark.label || ''
      markFontSize.value = mark.fontSize ? String(mark.fontSize) : ''
      markFontColor.value = mark.fontColor || ''
      for (const node of zoneOnly) node.hidden = mark.kind !== 'zone'
      markColor.value = mark.color || 'gray'
      markBorder.value = pickOr(mark.borderStyle, BORDER_STYLES)
      markAlign.value = pickOr(mark.labelAlign, LABEL_ALIGNS)
      markHatch.checked = Boolean(mark.hatch)
      markKeepOut.checked = Boolean(mark.keepOut)
      markRotate.hidden = !MARK_KINDS[mark.kind].rotatable
      if (mark.kind === 'block') {
        blockLink.value = mark.link || ''
        blockColor.value = mark.color || ''
        // 적용하지 않은 FAB 편집이 있으면 열지 않는다 — 열면 이 편집기가 내려가 그 편집이 사라진다.
        const pending = hasPendingEdits()
        blockOpen.disabled = pending || !mark.link || Boolean(blockOff(mark))
        blockOpen.title = pending
          ? '먼저 적용하세요 — 적용하지 않은 FAB 편집이 있습니다'
          : blockOff(mark)
            ? '비활성 층 — 층 목록 표 「비활성 층」에서 엽니다'
            : `${mark.link || '연결 층'} 을 엽니다`
      }
    }
  }
  // 브라우저가 쥔 적용 전 편집(요소·편집 영역)이 있는가.
  function hasPendingEdits() {
    return markChangeCount() > 0 || canvasChanged()
  }

  // 층 블록 위에 올려 두거나 초점을 두면 선택 줄에 「C1 1F · 누르면 열기」. 떠나면 원래 줄로 돌린다.
  S.showBlockHint = (group) => {
    const item = group ? S.items.get(group.dataset.id) : null
    // 비활성 층 블록은 열지 않는다 — 어디서 여는지 알린다(초점은 오지 않는다 — tabindex 가 없다).
    if (VIEW && FAB && blockOff(item)) {
      pickBox.textContent = `${item.link} · 비활성(${blockOff(item)}) — 층 목록 표 아래 「비활성 층」에서 엽니다`
      pickBox.title = pickBox.textContent
      return
    }
    if (!opensFloor(item)) { updateStatus(); return }
    pickBox.textContent = `${item.link} · 누르면 열기`
    pickBox.title = pickBox.textContent
  }
  // FAB 편집의 선택 칸 [열기]: 고른 층 블록이고 적용하지 않은 편집이 없을 때만.
  const opensFromInspector = (item) => Boolean(!VIEW && FAB && item && item.kind === 'block' && item.link && !hasPendingEdits() && !blockOff(item))
  // 블록이 가리키는 층을 연다. 파이썬 `on_navigate_change` 콜백이 층을 바꿔 재실행 한 번으로 층 상세가 선다.
  // 보기 전용 FAB 의 블록 누르기·Enter, 그리고 FAB 편집 선택 칸의 [열기] 가 모두 여기로 온다.
  function openFloor(item, fromInspector = false) {
    if (!(opensFloor(item) || (fromInspector && opensFromInspector(item)))) return
    pickBox.textContent = `${item.link} 여는 중…`
    if (fromInspector) { S.note = `${item.link} 여는 중…`; updateStatus() }
    setTriggerValue('navigate', { epoch: S.epoch, target: item.link })
  }

  function pickText(item) {
    if (isMark(item)) return `선택 ${MARK_KINDS[item.kind]?.name || item.kind}${item.label ? ` · ${item.label}` : ''}`
    const { stage, words } = unitWords(item)
    return `선택 ${item.label} · ${stage || '-'}${words ? ` · ${words}` : ''}${item.detail ? ` · ${item.detail}` : ''}`
      + `${item.group ? ` · Main 설비 ${item.group}` : ''} · X ${item.x} · Y ${item.y} · ${item.w}×${item.h}`
  }

  // 서랍에서 크기 없이 놓은 호기의 한 줄 — 「크기를 SMP-DAF-11 에서 불러옴」(같은 앞 3자리 설비에서 빌림), 빌릴 곳이 없어 이 층
  // 가운데 크기로 어림했으면 그렇게. 그 크기는 트레이로 다시 빼면 버린다(`sizeGuessed`). 사람이 크기를 고치면 사라진다.
  function sizeNote(list) {
    const guessed = list.filter((m) => m && isUnit(m) && !m.ghost && m.sizeGuessed && onCanvas(m))
    if (!guessed.length) return ''
    const sources = [...new Set(guessed.map((m) => m.sizeFrom).filter(Boolean))]
    const parts = []
    if (sources.length) {
      const named = sources.length > 3 ? `${sources.slice(0, 3).join(', ')} 외 ${sources.length - 3}곳` : sources.join(', ')
      parts.push(`크기를 ${named} 에서 불러옴`)
    }
    if (guessed.some((m) => !m.sizeFrom)) parts.push('크기 없는 호기는 이 층 가운데 크기로 놓음')
    return `${parts.join(' · ')}(트레이로 다시 빼면 버림)`
  }

  function updateStatus() {
    if (VIEW) {
      const chosen = selectedItems()
      pickBox.textContent = chosen.length === 1 ? pickText(chosen[0]) : ''
      // 한 줄에서 잘리면 전체 문구는 풍선으로.
      pickBox.title = pickBox.textContent || pickBox.dataset.hint
      zoomSel.disabled = !chosen.some(onCanvas)
      return
    }
    const chosen = selectedItems()
    const item = chosen.length === 1 ? chosen[0] : null
    const changed = changes().length + renames().length + markChangeCount() + groupLabelChangeCount() + (canvasChanged() ? 1 : 0)
    statusBox.replaceChildren()
    const add = (text, strong) => {
      if (statusBox.childNodes.length) statusBox.append(document.createTextNode(' · '))
      statusBox.append(document.createTextNode(text))
      if (strong === undefined) return
      const b = document.createElement('b')
      b.textContent = strong
      statusBox.append(b)
    }
    // 방금 한 일의 한 줄(복사·붙여넣기) — 다음 고르기·편집에서 지운다.
    if (S.flash) add(S.flash)
    if (chosen.length > 1) {
      add('선택 ', `${chosen.length}개`)
      add(`${expanded(chosen).length}개가 함께 움직입니다 — Shift/Ctrl+클릭으로 더하거나 빼기 · Esc 선택 풀기`)
      const sized = sizeNote(expanded(chosen))
      if (sized) add(sized)
    } else if (item && isMark(item)) {
      add('선택 ', `${MARK_KINDS[item.kind].name}${item.label ? ` ${item.label}` : ''}`)
      add(`X ${item.x} · Y ${item.y} · 크기 ${item.w}×${item.h}${item.rot ? ` · ${item.rot}°` : ''}`)
    } else if (item && moduleMembers(item)) {
      const mods = moduleMembers(item)
      const range = groupRange(mods)
      const [cols, rows] = moduleGrid(mods.length)
      add('선택 ', `Main 설비 ${item.group}`)
      if (range) add(`범위 X ${range.x} · Y ${range.y} · 크기 ${range.w}×${range.h}`)
      else add('트레이(미배치) — 위 칸에서 다른 층으로 보낼 수 있습니다')
      add(`모듈 ${mods.length}대는 범위 안 ${cols}×${rows} 바둑판에 자동으로 섭니다 — 범위를 끌어 옮기고 테두리 손잡이로 키웁니다`)
      const hidden = mods.filter((m) => m.ghost).map((m) => m.id)
      if (hidden.length) add(`숨은 모듈 ${hidden.join(', ')}(레이아웃표시 N·도면 이탈)는 그리지 않고 제 칸(점선)을 비워 둡니다 — 묶음과 함께 옮겨집니다`)
      if (untiledModules(item)) add(`${mods.length}등분이 아님 — 옮기거나 크기를 바꾸면 범위 안에 다시 놓입니다`)
      const sized = sizeNote(mods)
      if (sized) add(sized)
    } else if (item) {
      add('선택 ', item.label)
      if (onCanvas(item)) add(`X ${item.x} · Y ${item.y} · 크기 ${item.w}×${item.h}`)
      else add('트레이(미배치) — 위 칸에서 다른 층으로 보낼 수 있습니다')
      if (item.group) add(`Main 설비 ${item.group}`)
      const sized = sizeNote([item])
      if (sized) add(sized)
    } else {
      add(HINT)
    }
    add('적용 안 한 변경 ', `${changed}건`)
    if (FAB) {
      // 두 블록이 같은 층을 가리키면 알린다(막지 않는다 — 누르면 둘 다 그 층을 연다).
      const seen = new Map()
      for (const m of S.items.values()) if (m.kind === 'block' && m.link) seen.set(m.link, (seen.get(m.link) || 0) + 1)
      const doubled = [...seen.values()].filter((n) => n > 1).length
      if (doubled) add('같은 층을 가리키는 블록(저장은 됨) ', `${doubled}개 층`)
    }
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

  // 이름 칸(호기 `이름`·요소 `이름`)에 적던 글자는 그 칸에 들어갈 때 고른 대상의 것이다. 고르는 것이 바뀌기 전에 칸을
  // 떠나 그 대상에 확정한다 — 서랍 칩·팔레트는 누를 때 기본 동작을 막아 초점이 칸에 남아, 그대로 두면 다음 Enter 가
  // 새로 고른 호기에 이름을 붙였다(2026-10-08 병합 전 리뷰). 확정 중에는 목록을 다시 만들지 않는다 — 누른 칩이 그
  // 자리에서 사라지면 끌기·누르기가 끊긴다(`S.committing`, `renameUnit`).
  function commitTyping() {
    for (const input of [unitLabel, markLabel]) {
      if (!isFocused(input)) continue
      S.committing = true
      try {
        input.blur()
      } finally {
        S.committing = false
      }
    }
  }

  function setSelection(ids, primary) {
    commitTyping()
    S.flash = ''
    const known = ids.filter((id) => S.items.has(id))
    S.selection = new Set(onePerGroup(primary && known.includes(primary) ? [primary, ...known] : known))
    S.selected = primary && S.selection.has(primary) ? primary : ([...S.selection].pop() ?? null)
    markSelection()
    updateStatus()
  }

  function select(id) {
    setSelection(id ? [id] : [], id)
  }

  // 서랍 열림은 같은 편집기의 다음 실행에도 이어진다(S 에 둔다). 접으면 서랍 몫으로 옮긴 화면을 제자리로 돌린다.
  function setDrawer(open) {
    const was = Boolean(S.drawerOpen)
    S.drawerOpen = Boolean(open)
    drawer.classList.toggle('is-open', S.drawerOpen)
    trayBox.hidden = !S.drawerOpen
    drawerTab.setAttribute('aria-expanded', String(S.drawerOpen))
    if (was && !S.drawerOpen) applyView({ reposition: false })
  }

  // 서랍에서 놓은 호기가 서랍 아래에 들었으면 화면을 옮겨 꺼내 보인다(서랍은 열어 둔다 — 이어서 놓을 수 있게).
  // 옮길 수 있는 만큼만 옮긴다(trayReserve). 위아래로 서랍과 겹치지 않으면 그대로 둔다.
  function revealFromTray(list) {
    if (!S.drawerOpen || trayBox.hidden) return
    const tray = trayBox.getBoundingClientRect()
    let right = -Infinity
    let top = Infinity
    let bottom = -Infinity
    for (const m of list) {
      const rect = S.groups.get(m.id)?.querySelector('.sle-rect')?.getBoundingClientRect()
      if (!rect) continue
      right = Math.max(right, rect.right)
      top = Math.min(top, rect.top)
      bottom = Math.max(bottom, rect.bottom)
    }
    const covered = right > tray.left && bottom > tray.top && top < tray.bottom
    if (covered) panBy((right - tray.left + DRAWER_INSET_PX * 2) * unitsPerPx(), 0)
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
    S.flash = ''
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

  // 트레이 칩·팔레트에서 끌어 도면에 놓는다. 끌지 않고 누르기만 하면 onClick. footprint()가 놓을 상자 크기 {w, h} 를 주면
  // 도면 위에서 놓일 자리(격자·정렬선에 맞춘 `dropSpot`)와 정렬선을 미리 보인다. onDrop(p, free) 의 free 는 Alt 다.
  function ghostDrag(event, label, onDrop, onClick, footprint) {
    if (event.button !== 0) return
    // 아래 preventDefault 가 초점 옮기기를 막는다 — 적던 이름은 지금 대상에 먼저 확정한다(`commitTyping`).
    commitTyping()
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
    // 서랍에서 끈 칩이 서랍 밖으로 나가면 서랍을 비치게 해 그 아래 도면에도 놓게 한다. 비치기 전의 서랍 위는
    // 도면이 아니다 — 거기 놓으면 서랍 아래에 숨은 채 배치된다.
    const fromTray = Boolean(source.closest && source.closest('.sle-tray'))
    let peek = false
    const overTray = (e) => {
      if (trayBox.hidden) return false
      const r = trayBox.getBoundingClientRect()
      return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom
    }
    // 놓을 수 있는 도면 위 점(화면 좌표 {x, top}) — 도면 밖이거나 비치기 전의 서랍 위면 null.
    const dropPoint = (e) => {
      const box = svg.getBoundingClientRect()
      const inside = e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom
        && !(overTray(e) && !peek)
      return inside ? toUser(e) : null
    }
    let size = null
    const preview = (e) => {
      const p = footprint ? dropPoint(e) : null
      if (p && !size) size = footprint()
      if (!p || !size) { clearGuides(); return }
      const spot = dropSpot(p, size.w, size.h, e.altKey)
      drawGuides(spot.segments, spot)
    }
    const finish = (e, dropped) => {
      source.onpointermove = null
      source.onpointerup = source.onpointercancel = source.onlostpointercapture = null
      ghost.remove()
      drawer.classList.remove('is-peek')
      clearGuides()
      if (!dropped) return
      const still = Math.hypot(e.clientX - startX, e.clientY - startY) < DRAG_THRESHOLD_PX
      if (still) { onClick(); return }
      const p = dropPoint(e)
      if (p) onDrop(p, e.altKey)
    }
    source.onpointermove = (e) => {
      if (!shown && Math.hypot(e.clientX - startX, e.clientY - startY) >= DRAG_THRESHOLD_PX) { host.append(ghost); shown = true }
      if (shown && fromTray && !peek && !overTray(e)) { peek = true; drawer.classList.add('is-peek') }
      move(e)
      if (shown) preview(e)
    }
    source.onpointerup = (e) => finish(e, true)
    source.onpointercancel = (e) => finish(e, false)
    source.onlostpointercapture = (e) => { if (source.onpointerup) finish(e, false) }
  }

  // 서랍에서 고른 칩들(미배치 호기 묶음 가운데 하나라도 골라진 것). 서랍 차례 그대로다.
  function pickedTrayEntries() {
    // 검색으로 가려진 칩은 고른 채여도 함께 놓지 않는다 — 보이는 것만 끌려간다.
    return trayEntries(trayKeep())
      .filter((entry) => trayMatches(entry) && entry.list.some((m) => S.selection.has(m.id)))
  }

  // 서랍 칩을 더하거나 뺀다. 도면 위 호기는 함께 고르지 않는다 — 서랍에서 고른 것만 함께 끌어 놓는다.
  function toggleTrayPick(list) {
    const tray = new Set(trayEntries(trayKeep()).flatMap((entry) => entry.list.map((m) => m.id)))
    const ids = new Set([...S.selection].filter((id) => tray.has(id)))
    // 모듈 묶음은 선택에 한 대만 남으므로(`onePerGroup`) 하나라도 골라져 있으면 고른 칩이다.
    const on = list.some((m) => ids.has(m.id))
    for (const m of list) on ? ids.delete(m.id) : ids.add(m.id)
    setSelection([...ids], on ? null : list[0].id)
  }

  // 서랍 칩 누르기(끌지 않음). 그냥 누르면 그 칩 하나, Ctrl 은 더하거나 빼기 — 둘 다 그 칩이 Shift 범위의 기준 칩이 된다. Shift 는
  // 기준 칩부터 누른 칩까지 지금 보이는 차례(검색 반영)로 고르고(기준 칩은 그대로), Ctrl+Shift 는 그 범위를 더한다. 묶음 칩은
  // 한 칸이다. 기준 칩이 서랍에 없으면(놓았거나 처음) 그냥 누른 것과 같다.
  function pickChip(lead, list, keys) {
    if (keys.shift) {
      const order = [...trayList.children]
        .filter((chip) => chip.__entry)
        .map((chip) => ({ id: chip.dataset.id, visible: !chip.hidden, ids: chip.__ids }))
      const range = trayRangeIds(order, S.trayAnchor, lead.id)
      if (range) {
        const tray = new Set(order.flatMap((chip) => chip.ids))
        const kept = keys.ctrl ? [...S.selection].filter((id) => tray.has(id)) : []
        setSelection([...kept, ...range], lead.id)
        return
      }
    }
    S.trayAnchor = lead.id
    if (keys.ctrl) toggleTrayPick(list)
    else select(lead.id)
  }

  // 고른 칩 여럿을 한 번에 놓는다 — 모두 한 격자로 붙여(`placeFromTray` 와 같은 배치) 놓은 자리가 가운데다.
  function placeManyFromTray(lead, picked, p, free) {
    const list = picked.flatMap((entry) => entry.list)
    placeFromTray(lead, list, p, `${picked.length}개(${list.length}대)`, free)
  }

  // 크기를 빌려 줄 종류 — Main 설비 모듈 묶음의 모듈('module')과 그 밖의 호기('unit')는 서로 빌리지 않는다(모듈 크기는 묶음
  // 범위의 한 칸이다). 모듈은 설비 마스터(편집본) 전체에서 Main 설비가 같은 행이 둘 이상인 행이다(파이썬 `prefix_sizes` 와 같은
  // 기준 — 형제가 이 편집기에 실리지 않은 모듈도 모듈이다). 이 편집기에서 묶음인 것도 모듈로 본다.
  const sizeKind = (m) => {
    const key = groupKeyOf(m)
    return (key && MODULE_PARENTS.has(key)) || moduleMembers(m) ? 'module' : 'unit'
  }
  // 이번 편집에서 서랍으로 놓은 호기(놓은 차례 — 뒤가 나중)의 지금 크기 [{name, kind, w, h}]. 아직 도면에 서 있고, 이 층 가운데
  // 크기로 어림한 것이 아닌(제 크기·사람이 고친 크기·다른 설비에서 불러온 크기) 호기만 크기를 빌려 준다(`borrowedSize`).
  function recentSizes() {
    return S.placedLog
      .map((id) => S.items.get(id))
      .filter((m) => m && isUnit(m) && onCanvas(m) && hasSize(m) && !(m.sizeGuessed && !m.sizeFrom))
      .map((m) => ({ name: m.label, kind: sizeKind(m), w: m.w, h: m.h }))
  }

  // 서랍에서 놓을 덩이와 그 격자. 크기는 실제 설비 치수라 영역에 맞춰 자르지 않는다. 크기(Xsize·Ysize)가 없는 호기만 같은 앞
  // 3자리·같은 종류 설비의 크기를 빌린다(2026-10-23 사용자 결정 — 이번 편집에서 마지막으로 놓은 것 → 편집본에서 설비명 자연 정렬이
  // 가장 뒤인 것 → 이 층 가운데 크기). 빌리거나 어림한 크기는 `sizeGuessed` 로 기억한다 — 다시 트레이로 빼면 버려 「크기
  // 없음」으로 돌아간다. 같이 놓는 호기 가운데 제 크기가 있는 것도 이번에 놓은 것으로 본다.
  function trayPlan(list) {
    const recent = recentSizes()
    for (const m of list) {
      for (const u of moduleMembers(m) || [m]) {
        if (!u.ghost && hasSize(u)) recent.push({ name: u.label, kind: sizeKind(u), w: u.w, h: u.h })
      }
    }
    const sizeOf = (m) => {
      if (hasSize(m)) return { w: roundTo(m.w), h: roundTo(m.h), guessed: false, from: '' }
      const borrowed = borrowedSize(m.label, sizeKind(m), recent, PREFIX_SIZES)
      const size = borrowed || defaultSize
      return { w: roundTo(size.w), h: roundTo(size.h), guessed: true, from: borrowed ? borrowed.from : '' }
    }
    // 놓을 덩이. 모듈 묶음은 묶음 하나다 — 범위는 열 × 가장 큰 모듈 폭, 행 × 가장 큰 모듈 높이(`trayModuleRange`)이고 안은
    // 그 범위를 똑같이 나눈 바둑판(새로 놓기라 자연 정렬 — 첫 모듈 왼쪽 위)이다. 숨은 모듈도 제 칸에 함께 놓인다. 그 밖의
    // 호기는 제 크기 하나씩이다.
    const pieces = []
    const seen = new Set()
    for (const m of list) {
      if (seen.has(m.id)) continue
      const mods = moduleMembers(m)
      const units = mods || [m]
      for (const u of units) seen.add(u.id)
      const sizes = units.map(sizeOf)
      const box = mods ? trayModuleRange(sizes, SCALE) : sizes[0]
      pieces.push({ units, sizes, mods, w: box.w, h: box.h })
    }
    // 덩이 여럿은 거의 정사각 격자로 붙여 놓는다(첫 덩이가 왼쪽 위 — 셋이면 2×2). 칸은 가장 큰 덩이 크기이고 덩이는 칸
    // 왼쪽 아래에 선다. 덩이 하나면 놓은 자리가 가운데다. 모듈 묶음 안 바둑판(`moduleGrid` — 셋까지 한 줄)과는 따로다.
    const cols = Math.max(1, Math.ceil(Math.sqrt(pieces.length)))
    const rows = Math.max(1, Math.ceil(pieces.length / cols))
    const cellW = Math.max(...pieces.map((piece) => piece.w))
    const cellH = Math.max(...pieces.map((piece) => piece.h))
    return { pieces, cols, rows, cellW, cellH, footprint: { w: roundTo(cols * cellW), h: roundTo(rows * cellH) } }
  }

  function placeFromTray(lead, list, p, name, free) {
    const { pieces, cols, rows, cellW, cellH, footprint } = trayPlan(list)
    if (footprint.w > W() || footprint.h > H()) {
      S.note = `${name || lead.group || lead.label} (${footprint.w}×${footprint.h}) 가 편집 영역 ${W()}×${H()} 보다 커서 놓지 않았습니다 — 영역을 넓힌 뒤 놓으세요`
      updateStatus()
      return
    }
    S.note = ''
    const placed = pieces.flatMap((piece) => piece.units)
    const entries = placed.map((m) => ({ id: m.id, before: snapshot(m) }))
    // 놓은 점이 가운데인 격자 상자를 격자·정렬선에 맞춘 자리(`dropSpot` — 끄는 동안 미리 보인 자리와 같다).
    const at = dropSpot(p, footprint.w, footprint.h, free)
    const spots = pieces.map((piece, i) => ({
      x: roundTo(at.x + (i % cols) * cellW),
      y: roundTo(at.y + (rows - 1 - Math.floor(i / cols)) * cellH),
      w: piece.w,
      h: piece.h,
    }))
    const shift = clampShift(bbox(spots), 0, 0)
    pieces.forEach((piece, i) => {
      piece.units.forEach((m, k) => {
        m.w = piece.sizes[k].w
        m.h = piece.sizes[k].h
        m.sizeGuessed = piece.sizes[k].guessed
        m.sizeFrom = piece.sizes[k].from
      })
      const spot = { ...spots[i], x: roundTo(spots[i].x + shift.dx), y: roundTo(spots[i].y + shift.dy) }
      if (piece.mods) {
        layModules(piece.mods, fitRange(spot, piece.mods.length), naturalSlots(piece.mods.map((m) => m.id)))
        return
      }
      const m = piece.units[0]
      m.x = spot.x
      m.y = spot.y
      m.placed = true
      fit(m)
    })
    commit(entries)
    // 여럿을 함께 놓았으면 놓은 것을 모두 고른 채로 둔다 — 그대로 끌어 자리를 옮길 수 있다(모듈 묶음은 한 대로). 숨은 모듈은
    // 고르지도 보이지도 않는다.
    const shown = placed.filter((m) => !m.ghost)
    S.placedLog.push(...shown.map((m) => m.id))
    S.selection = new Set(onePerGroup(name ? shown.map((m) => m.id) : [lead.id]))
    S.selected = lead.id
    renderItems()
    updateStatus()
    // 서랍은 열어 둔다(이어서 놓는다). 놓은 호기가 서랍 아래면 화면을 옮겨 보인다.
    revealFromTray(shown)
    svg.focus({ preventScroll: true })
  }

  // 이 도면의 층 블록이 가리키는 층.
  const linkedFloors = () => [...S.items.values()].filter((m) => m.kind === 'block').map((m) => m.link)
  // 도면 요소를 넣는다. 자리를 주지 않으면(누르기) 지금 보이는 화면의 가운데, 끌어 놓았으면 놓은 점이 가운데이고 격자·정렬선에
  // 맞춘다(`dropSpot`, free 면 정렬선에 붙이지 않는다).
  function addMark(kind, at, free) {
    const spec = MARK_KINDS[kind]
    if (!spec) return
    const [w, h] = spec.size
    S.seq += 1
    const id = `MK-${Date.now().toString(36)}-${S.seq}`
    const center = at || { x: S.view.x + viewW() / 2, top: S.view.top + viewH() / 2 }
    const spot = at ? dropSpot(at, w, h, free) : { x: snapDelta(center.x - w / 2), y: snapDelta(H() - center.top - h / 2) }
    // 새 층 블록은 아직 블록이 없는 첫 층을 가리킨다(모두 있으면 첫 층). 선택 칸에서 바꾼다 — 블록은 연결이 필수다.
    const link = kind === 'block' ? freeLinks(1, linkedFloors(), LINK_TARGETS)[0] : ''
    const item = {
      id, kind, label: spec.label, stage: '', group: null, placed: true, moveTo: null, isNew: false, arrived: false,
      x: spot.x, y: spot.y, w, h, rot: 0,
      color: kind === 'zone' ? 'blue' : '', hatch: false, keepOut: false, link, fontSize: null, fontColor: '',
      borderStyle: BORDER_STYLES[0], labelAlign: LABEL_ALIGNS[0],
    }
    fit(item)
    S.items.set(id, item)
    pushUndo([{ op: 'create', id }])
    renderItems()
    setSelection([id], id)
    svg.focus({ preventScroll: true })
  }

  // ---------------------------------------------------------------- 도면 요소 복사·붙여넣기
  // Ctrl+C 는 고른 것 가운데 도면 요소만 복사한다 — 호기는 복사하지 않는다(2026-10-23 사용자 요청). 클립보드는 시스템 클립보드가
  // 아니라 이 편집기의 것이다 — 같은 브라우저 탭에서 층을 바꿔도 남게 sessionStorage(범위마다 — 층끼리, FAB 은 FAB 끼리)에 두고,
  // 막힌 창에서는 이 페이지 안 쪽지(`window.__capaSpaceClipboard`)로 산다. Ctrl+V 는 마우스가 도면 위면 그 자리(묶음 가운데,
  // 모양 그대로 — 격자·정렬선에 맞춘다), 아니면 원본에서 격자 한 칸씩 비켜(거듭 붙이면 한 칸씩 더) 붙인다. 영역 안으로 밀고, 새
  // id 를 받고, 되돌리기 한 번이며, 붙인 것이 골라진다. 층 블록은 새로 넣을 때처럼 아직 블록이 없는 층을 가리킨다.
  const CLIP_KEY = `capa.space.clipboard.${SCOPE}`
  const clipMemo = window.__capaSpaceClipboard || (window.__capaSpaceClipboard = {})
  // 복사해 둘 도면 요소 값(자리·모양·글자 — id 는 붙일 때 새로 받는다).
  const clipOf = (m) => ({
    kind: m.kind, x: m.x, y: m.y, w: m.w, h: m.h, rot: m.rot || 0, label: m.label || '', color: m.color || '',
    hatch: Boolean(m.hatch), keepOut: Boolean(m.keepOut), link: m.link || '', fontSize: m.fontSize ?? null,
    fontColor: m.fontColor || '', borderStyle: pickOr(m.borderStyle, BORDER_STYLES), labelAlign: pickOr(m.labelAlign, LABEL_ALIGNS),
  })
  function writeClipboard(marks) {
    const clip = { at: Date.now(), marks }
    clipMemo[SCOPE] = clip
    try {
      window.sessionStorage.setItem(CLIP_KEY, JSON.stringify(clip))
    } catch {
      // 저장소가 막힌 창 — 이 페이지 안 쪽지로 붙인다.
    }
  }
  // 붙일 수 있는 클립보드(이 범위에서 그리는 종류이고 자리·크기가 숫자인 요소만) — 둘 가운데 나중 것. 없으면 null.
  function readClipboard() {
    let stored = null
    try {
      stored = JSON.parse(window.sessionStorage.getItem(CLIP_KEY) || 'null')
    } catch {
      stored = null
    }
    const memo = clipMemo[SCOPE] || null
    const clip = [stored, memo].filter((c) => c && Array.isArray(c.marks)).sort((a, b) => (Number(b.at) || 0) - (Number(a.at) || 0))[0]
    if (!clip) return null
    const marks = clip.marks
      .filter((m) => m && typeof m === 'object' && drawable(String(m.kind)))
      .map((m) => ({ ...m, kind: String(m.kind), x: num(m.x), y: num(m.y), w: num(m.w), h: num(m.h) }))
      .filter((m) => [m.x, m.y, m.w, m.h].every(Number.isFinite) && m.w > 0 && m.h > 0)
    return marks.length ? { at: Number(clip.at) || 0, marks } : null
  }
  function copyMarks() {
    const chosen = selectedItems()
    const marks = chosen.filter(isMark)
    const units = chosen.length - marks.length
    if (!marks.length) {
      if (!units) return false
      S.flash = '호기는 복사하지 않습니다 — 도면 요소(영역·글자·기둥 …)만 복사합니다'
      updateStatus()
      return true
    }
    writeClipboard(marks.map(clipOf))
    S.pasteSerial = 0
    S.flash = `도면 요소 ${marks.length}개 복사 — Ctrl+V 로 붙입니다${units ? ' · 호기는 복사하지 않습니다' : ''}`
    updateStatus()
    return true
  }
  // 이 이동량으로 붙인 사본 가운데 하나라도 지금 도면의 같은 종류 요소와 자리·크기까지 똑같이 겹치는가 — 그런 사본은 보이지
  // 않은 채 두 겹으로 저장된다(요소끼리 겹침은 경고하지 않는다).
  function stacksOnMarks(marks, shift) {
    const same = (a, b) => Math.abs(a - b) < 0.5 / SCALE
    const standing = [...S.items.values()].filter(isMark)
    return marks.some((c) => standing.some((m) => m.kind === c.kind && same(m.x, c.x + shift.dx)
      && same(m.y, c.y + shift.dy) && same(m.w, c.w) && same(m.h, c.h)))
  }
  function pasteMarks(free) {
    const clip = readClipboard()
    if (!clip) return false
    if (S.clipAt !== clip.at) { S.clipAt = clip.at; S.pasteSerial = 0 }
    const outer = boxRect(bbox(clip.marks))
    const canvas = { w: W(), h: H() }
    let shift = null
    let segments = []
    if (S.hover) {
      // 마우스 자리(묶음 가운데 — 격자·정렬선에 맞춘 자리). 그 자리가 원본 그대로면(고른 직후 마우스를 그대로 둔 채 Ctrl+C·V —
      // 정렬선이 원본 선에 도로 붙인다) 비켜 붙이기로 넘긴다.
      const spot = dropSpot(S.hover, outer.w, outer.h, free)
      shift = pasteShift(clip.marks, canvas, { x: spot.x, y: spot.y }, 0, SCALE)
      segments = spot.segments
      if (shift && stacksOnMarks(clip.marks, shift)) { shift = null; segments = [] }
    }
    if (!shift) {
      S.pasteSerial += 1
      shift = pasteShift(clip.marks, canvas, null, Math.max(S.step, 1) * S.pasteSerial, SCALE)
    }
    if (!shift) {
      S.note = `붙일 도면 요소(${roundTo(outer.w)}×${roundTo(outer.h)})가 편집 영역 ${W()}×${H()} 보다 커서 붙이지 않았습니다`
      updateStatus()
      return true
    }
    if (stacksOnMarks(clip.marks, shift)) {
      S.note = '붙일 자리가 같은 요소와 똑같이 겹쳐 붙이지 않았습니다 — 마우스를 비어 있는 자리에 두고 Ctrl+V 하거나 편집 영역을 넓히세요'
      updateStatus()
      return true
    }
    const links = freeLinks(clip.marks.filter((m) => m.kind === 'block').length, linkedFloors(), LINK_TARGETS)
    const ids = []
    for (const source of clip.marks) {
      S.seq += 1
      const id = `MK-${Date.now().toString(36)}-${S.seq}`
      const item = readMark({ ...source, id, x: source.x + shift.dx, y: source.y + shift.dy })
      if (item.kind === 'block') item.link = links.shift()
      fit(item)
      S.items.set(id, item)
      ids.push(id)
    }
    pushUndo(ids.map((id) => ({ op: 'create', id })))
    S.note = ''
    renderItems()
    setSelection(ids, ids[ids.length - 1])
    S.flash = `도면 요소 ${ids.length}개를 붙였습니다`
    updateStatus()
    flashGuides(segments)
    svg.focus({ preventScroll: true })
    return true
  }

  // 자리를 바꾼 것을 다시 그린다. 도면에 새로 서거나 빠진 것(좌표 없던 모듈이 바둑판에 놓임 등)이 있으면 목록째 다시 만든다.
  function redraw(list) {
    const shown = list.filter((m) => m && !m.ghost)
    if (shown.some((m) => onCanvas(m) !== S.groups.has(m.id))) { renderItems(); return }
    for (const m of shown) position(S.groups.get(m.id), m)
    drawSelectionBox()
    markOverlaps()
  }

  // 방향키·숫자 칸의 X·Y 는 고른 것 전부를 함께 옮긴다. 호기·요소는 모양 그대로, 모듈 묶음은 범위를 옮겨 바둑판으로 다시
  // 놓는다(옛 묶음은 이때 바둑판이 된다 — 벽에 막혀 이동량이 0 이면 다시 놓지 않는다). 되돌리기 한 번에 모두 돌아온다.
  function moveItems(list, dx, dy) {
    const plan = movePlan(list)
    if (!plan.items.length) return
    const entries = plan.items.map((m) => ({ id: m.id, before: snapshot(m) }))
    const shift = clampShift(plan.box, dx, dy)
    for (const m of plan.loose) {
      m.x = roundTo(m.x + shift.dx)
      m.y = roundTo(m.y + shift.dy)
    }
    for (const g of plan.groups) relayGroup(g, { ...g.range, x: roundTo(g.range.x + shift.dx), y: roundTo(g.range.y + shift.dy) })
    const moved = entries.filter((e) => !sameSpot(e.before, itemOf(e.id)))
    if (!moved.length) { syncInspector(); return }
    commit(moved)
    redraw(plan.items)
    updateStatus()
  }

  // 크기는 고른 것 하나하나에 적용한다 — 호기·요소는 그 하나, 모듈 묶음은 범위를 바꿔 바둑판으로 다시 놓는다(범위가 그대로면
  // 다시 놓지 않는다). 폭은 오른쪽으로, 높이는 위로 자란다.
  function setSizes(list, patchOf) {
    const entries = []
    const touched = []
    const done = new Set()
    for (const item of list) {
      const mods = moduleMembers(item)
      if (mods) {
        const key = groupKeyOf(item)
        const range = done.has(key) ? null : groupRange(mods)
        done.add(key)
        if (!range) continue
        const befores = mods.map((m) => ({ id: m.id, before: snapshot(m) }))
        if (!relayGroup({ mods, range, slots: groupSlots(mods) }, fitRange({ ...range, ...patchOf(range) }, mods.length))) continue
        for (const e of befores) {
          const m = itemOf(e.id)
          if (sameSpot(e.before, m)) continue
          m.sizeGuessed = false
          entries.push(e)
        }
        touched.push(...mods)
        continue
      }
      const before = snapshot(item)
      Object.assign(item, patchOf(item))
      fit(item)
      if (!sameGeometry(item, before)) {
        item.sizeGuessed = false
        entries.push({ id: item.id, before })
        touched.push(item)
      }
    }
    if (!entries.length) { syncInspector(); return }
    commit(entries)
    redraw(touched)
    updateStatus()
  }

  // 「범위에 맞춰 n등분」 — 바둑판이 아닌 옛 묶음을 지금 바깥 상자 안에 다시 놓는다(옮기거나 키울 때와 같다).
  function retileModules(item) {
    const mods = moduleMembers(item)
    const range = mods ? groupRange(mods) : null
    if (!range) return
    const entries = mods.map((m) => ({ id: m.id, before: snapshot(m) }))
    layModules(mods, range)
    const moved = entries.filter((e) => !sameSpot(e.before, itemOf(e.id)))
    if (!moved.length) { updateStatus(); return }
    commit(moved)
    redraw(mods)
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

  // 모듈 묶음이 이 층 도면에서 통째로 빠지면(빼기·Delete·다른 층 보내기) 그 묶음의 숨은 모듈을 처음(편집기에 실린) 자리로
  // 되돌린다 — 묶음을 옮기지 않고 바로 뺀 것과 같다. 숨은 모듈은 빼면 이 층 제자리에 남고, 보내면 파이썬이 층을 맞추며 X·Y 를
  // 비운다(`_harmonize_groups`). 따라 옮겨진 자리에 두면 적용값 `ghosts` 로 가서 파이썬이 「숨은 모듈만 옮겨 왔습니다」로
  // 적용 전체를 거부한다. 돌려주는 기록(set)은 빼기·보내기 기록에 함께 담는다 — 되돌리기 한 번에 같이 돌아온다.
  function restoreGhosts(units) {
    const keys = new Set(units.filter((m) => isUnit(m) && m.group).map(groupKeyOf))
    if (!keys.size) return []
    const standing = new Set([...S.items.values()].filter((m) => isUnit(m) && m.group && onCanvas(m)).map(groupKeyOf))
    const ops = []
    for (const g of S.ghosts.values()) {
      if (!keys.has(g.group) || standing.has(g.group)) continue
      const o = S.original.get(g.id)
      if (!o || sameGeometry(o, g)) continue
      ops.push({ op: 'set', id: g.id, before: snapshot(g) })
      Object.assign(g, { x: o.x, y: o.y, w: o.w, h: o.h })
    }
    return ops
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
        m.sizeFrom = ''
      }
    }
    ops.push(...restoreGhosts(units))
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
  // 그 층에 서고(파이썬이 그 층 영역 안으로 맞춘다), 미배치였던 호기는 그 층 트레이로 간다. 숨은 모듈은 처음 자리로
  // 돌아가고(`restoreGhosts`) 층은 파이썬이 묶음째 맞춘다.
  function sendItems(list, floor) {
    if (!floor || floor === FLOOR || !OTHER_FLOORS.includes(floor)) return
    const targets = new Map()
    for (const item of list.filter(isUnit)) for (const m of members(item)) if (!m.moveTo) targets.set(m.id, m)
    if (!targets.size) return
    const sent = [...targets.values()]
    const ops = sent.map((m) => ({ op: 'set', id: m.id, before: snapshot(m) }))
    for (const m of sent) m.moveTo = floor
    pushUndo([...ops, ...restoreGhosts(sent)])
    clearSelection()
    renderItems()
    updateStatus()
  }

  // ---------------------------------------------------------------- 이름 바꾸기
  // 표시 별칭이 아니라 설비 마스터의 설비명을 바꾼다(2026-10-08 사용자 결정). 모듈 묶음(Main 설비가 자기 설비명이
  // 아닌 호기)은 묶음 이름(Main 설비)을 바꾼다 — 모듈 행 하나의 설비명은 설비 마스터에서 고친다. 자기 설비명을 Main
  // 설비로 적은 한 행짜리 묶음은 설비명을 바꾸고 Main 설비가 따라간다. 적용 전까지는 이 편집기 안에만 있고 파이썬이
  // 적용 때 다시 검사한다(겹침 규칙이 같다).
  const renameTarget = (item) => {
    const bundle = Boolean(item.group && item.group !== item.label)
    return { bundle, name: bundle ? item.group : item.label }
  }
  // 이름 비교 열쇠 — 대소문자·앞뒤 공백만 다른 두 이름은 같은 이름이다(파이썬 `match_key`).
  const nameKey = (value) => String(value ?? '').trim().toLowerCase()
  // 설비명 글자 다듬기(호기 추가 폼과 같다): 제어 문자·특수 공백은 보통 공백으로, 겹친 공백은 하나로, 40자까지.
  const cleanName = (value) => String(value ?? '')
    .replace(/[\u0000-\u001f\u007f-\u009f\u00a0\u1680\u2000-\u200f\u2028-\u202f\u205f\u3000\ufeff]/g, ' ')
    .replace(/ {2,}/g, ' ')
    .trim()
    .slice(0, 40)
  // 이 이름을 이미 쓰는 것. 설비 마스터 전체(다른 층·미배치 포함)의 설비명·Main 설비에서, 이 편집기 호기·묶음은
  // 지금(바꾼) 이름으로 본다. 자기 자신(묶음이면 그 묶음 이름)은 빼고, 새로 넣은 호기는 이미 있던 이름 전체를 피한다.
  function nameClash(name, item, bundle) {
    const key = nameKey(name)
    const inside = new Set()
    for (const m of S.items.values()) {
      if (!isUnit(m)) continue
      const o = S.original.get(m.id)
      if (!o) continue
      inside.add(o.label)
      if (o.group) inside.add(o.group)
    }
    for (const other of EXISTING_IDS) {
      if ((item.created || !inside.has(other)) && nameKey(other) === key) return other
    }
    // 묶음 이름은 자기 모듈 행의 설비명과도 겹칠 수 없다. 호기 이름은 자기 이름(과 따라가는 자기 묶음)만 뺀다.
    const ownGroup = bundle || item.group === item.label ? item.group : null
    for (const m of S.items.values()) {
      if (!isUnit(m)) continue
      if ((bundle || m !== item) && nameKey(m.label) === key) return m.label
      if (m.group && m.group !== ownGroup && nameKey(m.group) === key) return m.group
    }
    return null
  }
  function renameUnit(item, raw) {
    const target = renameTarget(item)
    const name = cleanName(raw)
    if (!name || name === target.name) {
      S.note = name ? '' : '이름은 비울 수 없습니다'
      unitLabel.value = target.name
      updateStatus()
      return
    }
    const clash = nameClash(name, item, target.bundle)
    if (clash) {
      // 문구는 짧게 둔다(이 칸이 길어지면 칸 줄이 접혀 도면이 내려간다). 대소문자 규칙은 이름 칸 풍선이 말한다.
      S.note = `이름 ${name}: 이미 쓰는 이름(${clash})이라 바꾸지 않았습니다`
      unitLabel.value = target.name
      updateStatus()
      return
    }
    const list = target.bundle ? [...S.items.values()].filter((m) => isUnit(m) && m.group === item.group) : [item]
    pushUndo(list.map((m) => ({ op: 'set', id: m.id, before: snapshot(m) })))
    for (const m of list) {
      if (target.bundle) {
        m.group = name
        continue
      }
      // 자기 설비명을 Main 설비로 적은 한 행짜리 묶음은 Main 설비도 따라간다.
      if (m.group && m.group === m.label) m.group = name
      m.label = name
    }
    S.note = ''
    // 고르는 것을 바꾸는 중의 확정(`commitTyping`)이면 글자만 고친다 — 목록을 다시 만들면 방금 누른 칩·상자가 사라져
    // 그 누르기가 끊긴다. 서랍 차례는 다음 다시 그리기 때 맞춰진다.
    if (S.committing) repaint()
    else renderItems()
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
          // 추가를 취소해 사라진 것의 기록은 건너뛴다. 숨은 모듈도 같은 기록으로 돌아온다.
          const item = itemOf(op.id)
          if (!item) continue
          Object.assign(item, op.before)
          applied += 1
        } else if (op.op === 'create') {
          if (S.items.delete(op.id)) applied += 1
        } else if (op.op === 'delete') {
          S.items.set(op.item.id, { ...op.item })
          applied += 1
        } else if (op.op === 'groupLabel') {
          if (op.before === null) S.groupLabels.delete(op.key)
          else S.groupLabels.set(op.key, op.before)
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
    clearGuides()
    svg.classList.remove('is-panning')
    if (drag.mode === 'pan') return
    if (drag.mode === 'marquee') {
      S.selection = new Set(drag.before)
      S.selected = drag.beforePrimary
      markSelection()
      updateStatus()
      return
    }
    for (const [id, before] of drag.befores) Object.assign(itemOf(id), before)
    redraw([...drag.befores.keys()].map(itemOf))
    clearDragOverlap()
    updateStatus()
  }

  // 오른쪽·왼쪽·위·아래 변 가운데 움직이는 것만 옮긴다. 반대쪽 변은 그대로다. 폭·높이는 minW·minH 아래로 줄지 않는다.
  function resizedBox(b, dir, dx, dTop, minW, minH) {
    let left = b.x
    let right = b.x + b.w
    let bottom = b.y
    let top = b.y + b.h
    if (dir.includes('e')) right = clamp(right + dx, left + minW, W())
    if (dir.includes('w')) left = clamp(left + dx, 0, right - minW)
    if (dir.includes('n')) top = clamp(top - dTop, bottom + minH, H())
    if (dir.includes('s')) bottom = clamp(bottom - dTop, 0, top - minH)
    const x = roundTo(left)
    const y = roundTo(bottom)
    return { x, y, w: roundTo(Math.min(roundTo(right), floorTo(W())) - x), h: roundTo(Math.min(roundTo(top), floorTo(H())) - y) }
  }
  function resizeTo(item, b, dir, dx, dTop) {
    Object.assign(item, resizedBox(b, dir, dx, dTop, minSize(), minSize()))
    item.sizeGuessed = false
  }

  // 호기의 색 기준 면·글자와 경계 날짜(파이썬 `boundary_payload`). 같은 epoch 회차에도 이것만은 새로 받아 칠한다 —
  // 체크·색 기준·기준일만 바뀐 회차는 epoch 가 그대로라 배율·편집을 지킨 채 색·테만 바뀐다. 이름에 `group`(Main 설비
  // 묶음)·`arrived`(다른 층에서 옴)는 이미 쓰인다.
  // 설비지분(파이썬 기준일의 보유 지분 — 범례와 같은 칸, 일부 모듈만 반입한 Main 설비의 반입 전 모듈은 0) — 층 상세 보기
  // 요약의 「겹쳐 숨긴 반입 예정 n대」를 설비 대수로 센다. 0 이상의 수가 아니면 한 대.
  const shareOf = (value) => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 1)
  const unitLook = (raw) => ({
    fill: hexOr(raw.fill), ink: hexOr(raw.ink), storage: Boolean(raw.storage), flag: Boolean(raw.flag),
    realFrom: dayOr(raw.realFrom), exitOn: dayOr(raw.exitOn), stopOn: dayOr(raw.stopOn),
    delays: spansOf(raw.delays), offline: spansOf(raw.offline), share: shareOf(raw.share),
  })
  const readUnit = (raw) => ({
    id: String(raw.id), kind: 'unit', label: String(raw.label ?? raw.id), stage: String(raw.stage || ''),
    group: raw.group ? String(raw.group) : null, x: num(raw.x), y: num(raw.y), w: num(raw.w), h: num(raw.h),
    isNew: Boolean(raw.isNew), arrived: Boolean(raw.arrived), floorless: Boolean(raw.floorless), moveTo: null, created: null,
    sizeGuessed: false, detail: String(raw.detail || ''), ...unitLook(raw),
  })
  const readMark = (raw) => ({
    id: String(raw.id), kind: String(raw.kind), label: String(raw.label || ''), stage: '', group: null,
    x: num(raw.x), y: num(raw.y), w: num(raw.w), h: num(raw.h), rot: Number(raw.rot) || 0,
    color: String(raw.color || ''), hatch: Boolean(raw.hatch), keepOut: Boolean(raw.keepOut),
    link: String(raw.link || ''), placed: true, moveTo: null, isNew: false, arrived: false,
    fontSize: fontSizeOf(raw.fontSize), fontColor: String(raw.fontColor || ''),
    borderStyle: pickOr(raw.borderStyle, BORDER_STYLES), labelAlign: pickOr(raw.labelAlign, LABEL_ALIGNS),
  })

  function initFromData() {
    S.items = new Map()
    S.ghosts = new Map()
    S.original = new Map()
    S.originalMarkIds = new Set()
    S.passthrough = []
    for (const raw of data.items || []) {
      const item = readUnit(raw)
      item.placed = Boolean(raw.placed) && [item.x, item.y, item.w, item.h].every(Number.isFinite)
      S.items.set(item.id, item)
      S.original.set(item.id, snapshot(item))
    }
    // 숨은 모듈(파이썬 `EditorInputs.ghosts`) — 그리지 않고 묶음 바둑판의 칸만 차지한다. 처음 값은 S.original 에 둔다
    // (`ghostChanges` 가 견준다).
    for (const raw of data.ghosts || []) {
      const ghost = {
        id: String(raw.id), kind: 'unit', ghost: true, label: String(raw.id), group: raw.group ? String(raw.group) : null,
        x: num(raw.x), y: num(raw.y), w: num(raw.w), h: num(raw.h), placed: true, moveTo: null, sizeGuessed: false,
      }
      if (!ghost.group || S.items.has(ghost.id) || ![ghost.x, ghost.y, ghost.w, ghost.h].every(Number.isFinite)) continue
      S.ghosts.set(ghost.id, ghost)
      S.original.set(ghost.id, snapshot(ghost))
    }
    // Main 설비명 위치(처음 받은 Main 설비 이름 → 가운데·위·아래). 없는 묶음은 그 모양의 처음 위치다(`groupLabelDefault`).
    S.groupLabels = new Map()
    for (const [name, position] of Object.entries(data.groupLabels || {})) {
      if (GROUP_LABEL_POSITIONS.includes(position)) S.groupLabels.set(String(name), position)
    }
    S.originalGroupLabels = new Map(S.groupLabels)
    for (const raw of data.marks || []) {
      const mark = readMark(raw)
      if (!drawable(mark.kind) || ![mark.x, mark.y, mark.w, mark.h].every(Number.isFinite)) {
        S.passthrough.push(raw)
        continue
      }
      S.items.set(mark.id, mark)
      S.original.set(mark.id, snapshot(mark))
      S.originalMarkIds.add(mark.id)
    }
  }

  // 같은 epoch 회차의 기준일. 파이썬이 쥔 날(`incoming`)이 지난 회차와 같으면 브라우저가 칠한 날을 그대로 둔다 — 끄는
  // 중이거나, 보낸 날이 아직 돌아오지 않았거나, 다른 위젯이 돌린 회차다. 보낸 날이 돌아온 것이면 맞았다고 보고, 그 밖에
  // 파이썬이 따로 바꾼 날이면(범위 끝 맞춤 등) 따른다. 페이더가 없는 화면(편집·FAB)은 늘 받은 날이다. 칠한 날이
  // 바뀌었으면 그 앞의 날(앞의 날이 없었으면 '*'), 아니면 ''.
  function adoptAsOf(incoming) {
    const previous = S.asOf
    if (!FADER) {
      S.asOf = incoming
      S.dataAsOf = incoming
      return previous !== incoming ? previous || '*' : ''
    }
    if (incoming === S.dataAsOf) return ''
    S.dataAsOf = incoming
    if (S.sent.has(incoming)) {
      if (incoming === S.lastSent) S.sent.clear()
      return ''
    }
    if (S.faderBusy || S.commitTimer) return ''
    S.asOf = incoming
    S.faderTarget = incoming
    return previous !== incoming ? previous || '*' : ''
  }

  // ------------------------------------------------------------- 회차마다
  if (S.epoch !== data.epoch) {
    S.epoch = data.epoch
    S.undo = []
    clearSelection()
    S.drag = null
    S.note = ''
    // 복사·붙여넣기 알림은 그 도면의 것이다 — 적용 뒤·다른 층의 새 도면까지 상태 줄에 남기지 않는다.
    S.flash = ''
    // 새 epoch(층 이동·저장본·요소·그리는 호기가 바뀜)에서는 data 의 기준일을 그대로 쓴다.
    S.asOf = AS_OF
    S.dataAsOf = AS_OF
    S.faderTarget = AS_OF
    S.sent = new Set()
    S.lastSent = ''
    S.faderBusy = false
    if (S.commitTimer) clearTimeout(S.commitTimer)
    S.commitTimer = 0
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
    // 새로 선 도면은 파이썬이 쥔 고른 호기(`data.picked`)를 다시 고른다(아래 `syncPick`).
    S.pickData = undefined
  } else {
    // 같은 epoch: 기하는 브라우저가 쥔 것을 지키고, 단계·라벨·면·경계 날짜처럼 보기만 바뀐 것은 합친다. 받은 값이
    // 쥔 값과 같은 호기는 건드리지 않는다 — 페이더를 놓은 뒤 돌아온 회차처럼 기준일도 호기 값도 그대로면 아무것도
    // 다시 칠하지 않는다(1,289대 전체 다시 칠하기 `repaint` 는 70~100ms). 적용하지 않은 이름 바꿈은 브라우저가 쥔
    // 편집이다 — 다른 위젯을 건드린 회차가 그것을 옛 이름으로 되돌리지 않게 둔다.
    const previous = adoptAsOf(AS_OF)
    const touched = []
    for (const raw of data.items || []) {
      const item = S.items.get(String(raw.id))
      if (!item) continue
      const next = { stage: String(raw.stage || ''), detail: String(raw.detail || ''), ...unitLook(raw) }
      next.label = isRenamed(item) ? item.label : String(raw.label ?? raw.id)
      if (sameLook(item, next)) continue
      Object.assign(item, next)
      touched.push(item)
    }
    if ((data.backgroundImage || null) !== S.bgImage) {
      S.bgImage = data.backgroundImage || null
      drawStatic()
    }
    // 도면 요소는 적어(층마다 수십 개) 늘 다시 그린다 — 영역 색(테마)·층 블록 대수(`linkStats`)가 data 로 온다.
    if (VIEW && !FAB) {
      refreshUnits(touched, previous)
      redrawMarks()
    } else if (touched.length || previous) repaint()
    else redrawMarks()
  }
  showSummary()

  // ------------------------------------------------------------- 아래 호기 표에 고른 호기(층 상세 보기)
  // 층 상세 보기에서 호기를 누르면(끌지 않고) 그 호기를 `pick` 으로 알린다(2026-10-23 사용자 요청 3). 받는 쪽 파이썬
  // `on_pick_change` 콜백이 층 상세 아래 호기 표를 그 설비 줄만으로 좁힌다 — 블록 열기(`navigate`)와 같은 꼴이고 epoch 가 다른
  // 옛 값은 버린다. 호기가 아닌 것(도면 요소)을 누르거나 빈 곳을 누르거나 Esc 로 풀면 고른 호기가 없다는 값(id null)을 보내
  // 표가 층 전체로 돌아간다. 같은 값은 다시 보내지 않는다. 표 위 「층 전체 보기」 단추로 파이썬이 풀면 `data.picked` 가 비어
  // 도면의 고르기도 풀린다. 배치 편집기와 FAB 는 보내지 않는다.
  const PICKS = VIEW && !FAB
  function notePick() {
    if (!PICKS) return
    const item = S.selected ? S.items.get(S.selected) : null
    const id = item && isUnit(item) ? item.id : null
    if (id === S.pickSent) return
    S.pickSent = id
    setTriggerValue('pick', { epoch: S.epoch, id })
  }
  // 파이썬이 쥔 고른 호기가 지난 회차와 다르면(누른 회차·「층 전체 보기」·새로 선 도면) 도면의 고르기를 그것에 맞춘다.
  function syncPick() {
    if (!PICKS) return
    const picked = typeof data.picked === 'string' && data.picked ? data.picked : null
    if (picked === S.pickData) return
    S.pickData = picked
    S.pickSent = picked
    if (picked && S.items.has(picked)) {
      if (S.selected !== picked || S.selection.size !== 1) select(picked)
    } else if (!picked && S.selected && isUnit(S.items.get(S.selected) || {})) select(null)
  }
  syncPick()

  // ------------------------------------------------------------- 끌기(속성 대입이라 겹쳐 쌓이지 않는다)
  svg.onmousedown = (event) => { if (event.button === 1) event.preventDefault() }
  // 고른 것 가운데 도면 점 p(화면 좌표 {x, top})를 범위 안에 품은 모듈 묶음이 있는가.
  function pickedRangeAt(picked, p) {
    const y = H() - p.top
    return picked.some((item) => {
      const mods = moduleMembers(item)
      const range = mods && groupRange(mods)
      return Boolean(range) && p.x >= range.x && p.x <= range.x + range.w && y >= range.y && y <= range.y + range.h
    })
  }
  svg.onpointerdown = (event) => {
    if (event.button !== 0 && event.button !== 1) return
    const p = toUser(event)
    if (!p) return
    event.preventDefault()
    // 도면에 초점을 옮기기 전에 적던 이름을 확정한다 — 그 사이 누른 호기의 상자가 다시 만들어지지 않게.
    commitTyping()
    svg.focus({ preventScroll: true })
    if (VIEW) {
      // 보기 전용: 끌면 화면 이동(확대했을 때), 끌지 않고 떼면 누른 호기를 고른다.
      const target = event.target.closest ? event.target.closest('.sle-item') : null
      S.drag = {
        mode: 'view', pointerId: event.pointerId, startClientX: event.clientX, startClientY: event.clientY,
        view: { ...S.view }, upp: unitsPerPx(), id: target ? target.dataset.id : null, moved: false,
      }
      svg.setPointerCapture(event.pointerId)
      return
    }
    const start = { pointerId: event.pointerId, startX: p.x, startTop: p.top, startClientX: event.clientX, startClientY: event.clientY, moved: false }
    if (event.button === 1 || S.spaceDown) {
      // 화면 옮기기: 가운데 버튼 끌기, 또는 Space 를 누른 채 끌기.
      S.drag = { ...start, mode: 'pan', view: { ...S.view }, upp: unitsPerPx() }
      svg.classList.add('is-panning')
      svg.setPointerCapture(event.pointerId)
      return
    }
    const rangeDir = event.target.classList && event.target.classList.contains('sle-range-handle') ? event.target.dataset.dir : null
    const picked = selectedItems()
    if (rangeDir && picked.length === 1 && moduleMembers(picked[0])) {
      // 고른 모듈 묶음의 범위 테두리 손잡이 — 범위 크기를 바꾸면 안의 모듈이 바둑판으로 다시 선다.
      const plan = movePlan(picked)
      if (!plan.groups.length) return
      S.drag = {
        ...start, id: picked[0].id, mode: 'range', dir: rangeDir, loose: [], groups: plan.groups,
        ids: plan.items.map((m) => m.id), befores: new Map(plan.items.map((m) => [m.id, snapshot(m)])), box: plan.box,
        collapse: false,
      }
      svg.setPointerCapture(event.pointerId)
      return
    }
    const group = event.target.closest ? event.target.closest('.sle-item') : null
    const additive = event.shiftKey || event.ctrlKey || event.metaKey
    if (!group && !additive && pickedRangeAt(picked, p)) {
      // 고른 모듈 묶음의 범위 안 빈 칸(모듈 셋·다섯 묶음의 남는 칸, 숨은 모듈 칸)도 묶음이다 — 누르면 그 묶음을 끈다.
      const plan = movePlan(picked)
      S.drag = {
        ...start, id: S.selected, mode: 'move', dir: null, loose: plan.loose, groups: plan.groups,
        ids: plan.items.map((m) => m.id), befores: new Map(plan.items.map((m) => [m.id, snapshot(m)])), box: plan.box,
        collapse: false,
      }
      svg.setPointerCapture(event.pointerId)
      return
    }
    if (!group) {
      // 빈 곳을 끌면 사각형 안에 다 들어온 것을 고른다. Shift/Ctrl 이면 지금 고른 것에 더한다.
      S.drag = { ...start, mode: 'marquee', additive, before: new Set(S.selection), beforePrimary: S.selected, rect: null }
      svg.setPointerCapture(event.pointerId)
      return
    }
    const item = S.items.get(group.dataset.id)
    if (!item) return
    if (additive) {
      // Shift/Ctrl+클릭은 고른 것에 더하거나 뺀다(끌지 않는다). 모듈 묶음은 묶음째 — 그 묶음이 골라져 있으면 뺀다.
      const ids = new Set(S.selection)
      const bundle = (moduleMembers(item) || [item]).map((m) => m.id)
      const had = bundle.some((id) => ids.has(id))
      for (const id of bundle) ids.delete(id)
      if (!had) ids.add(item.id)
      setSelection([...ids], had ? null : item.id)
      return
    }
    const chosen = selectedItems()
    const inSelection = expanded(chosen).some((m) => m.id === item.id)
    const onlyThis = chosen.length === 1 && S.selected === item.id
    if (!inSelection) select(item.id)
    else if (S.selection.has(item.id)) { S.selected = item.id; markSelection(); updateStatus() }
    const dir = event.target.classList.contains('sle-handle') ? event.target.dataset.dir : null
    // 손잡이는 이미 하나만 고른 것에서만 듣는다 — 처음 누른 모서리가 크기를 바꾸지 않게. 모듈 상자의 크기는 고치지
    // 못한다(손잡이를 감추고, 눌려도 옮기기다 — 크기는 묶음 범위 테두리의 손잡이로).
    const mode = onlyThis && dir && !moduleMembers(item) ? 'resize' : 'move'
    // 옮기기는 고른 것 전부 — 모듈 묶음은 묶음째(범위를 옮겨 바둑판으로 다시 놓는다). 모듈 하나만 옮기는 길은 없다.
    const plan = mode === 'move' ? movePlan(selectedItems()) : { loose: [item], groups: [], items: [item], box: bbox([item]) }
    const list = plan.items
    // 끄는 것이 맨 위에 그려지도록 제 층(호기·영역·요소)의 맨 뒤로 옮긴다.
    for (const m of list) {
      const g = S.groups.get(m.id)
      if (g && g.parentNode) g.parentNode.append(g)
    }
    S.drag = {
      ...start, id: item.id, mode, dir, loose: plan.loose, groups: plan.groups,
      ids: list.map((m) => m.id), befores: new Map(list.map((m) => [m.id, snapshot(m)])), box: plan.box,
      // 여러 개를 고른 채 하나를 눌렀다 떼기만 하면 그 하나만 고른 상태로 좁힌다.
      collapse: inSelection && (S.selection.size > 1 || !S.selection.has(item.id)),
    }
    svg.setPointerCapture(event.pointerId)
  }
  svg.onpointermove = (event) => {
    // 붙여넣기 자리(마우스가 도면 위면 그 자리)로 마지막 포인터 자리를 기억한다 — 편집에서만.
    if (!VIEW) S.hover = toUser(event)
    const drag = S.drag
    if (!drag || event.pointerId !== drag.pointerId) return
    if (drag.mode === 'pan' || drag.mode === 'view') {
      const far = Math.hypot(event.clientX - drag.startClientX, event.clientY - drag.startClientY) >= DRAG_THRESHOLD_PX
      // 문턱을 넘은 끌기는 블록을 열지 않는다(전체 보기에서 화면이 움직이지 않아도).
      if (far) drag.travelled = true
      if (drag.mode === 'view' && S.view.z <= 1) return
      if (drag.mode === 'view' && !drag.moved && !far) return
      svg.classList.add('is-panning')
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
      // 모듈 묶음은 한 대만 남긴다(`onePerGroup`) — 묶음째 골라진다.
      S.selection = new Set(onePerGroup(drag.additive ? [...drag.before, ...inside] : inside))
      const last = inside.length ? inside[inside.length - 1] : (drag.additive ? drag.beforePrimary : null)
      S.selected = last && S.selection.has(last) ? last : ([...S.selection].pop() ?? null)
      markSelection()
      updateStatus()
      return
    }
    // 이동량은 격자에 맞추되, 정렬선에 닿는 축은 그 선에 붙인 이동량이 이긴다(Alt 를 누른 채면 붙이지 않는다).
    const aligned = alignDrag(drag, p.x - drag.startX, p.top - drag.startTop, event.altKey)
    const dx = aligned.dx ?? snapDelta(p.x - drag.startX)
    const dTop = aligned.dTop ?? snapDelta(p.top - drag.startTop)
    if (drag.mode === 'move') {
      // 이동량을 격자에 맞춘다(제자리 좌표를 격자로 끌어당기지 않는다). 화면에서 아래로 끌면 Y 는 준다. 모듈 묶음은
      // 범위를 옮겨 바둑판으로 다시 놓는다.
      const shift = clampShift(drag.box, dx, -dTop)
      for (const m of drag.loose) {
        const b = drag.befores.get(m.id)
        m.x = roundTo(b.x + shift.dx)
        m.y = roundTo(b.y + shift.dy)
      }
      // 이동량이 0 이면(제자리로 돌아옴) 묶음은 처음 값 그대로다(`relayGroup`).
      for (const g of drag.groups) {
        relayGroup(g, { ...g.range, x: roundTo(g.range.x + shift.dx), y: roundTo(g.range.y + shift.dy) }, drag.befores)
      }
    } else if (drag.mode === 'range') {
      // 모듈 묶음 범위 크기 — 칸마다 최소 크기 한 칸(열·행 × 1 눈금) 아래로 줄지 않는다. 범위가 그대로면 처음 값이다.
      const g = drag.groups[0]
      const [cols, rows] = moduleGrid(g.mods.length)
      if (relayGroup(g, resizedBox(g.range, drag.dir, dx, dTop, cols / SCALE, rows / SCALE), drag.befores)) {
        for (const m of g.mods) m.sizeGuessed = false
      }
    } else {
      resizeTo(S.items.get(drag.id), drag.befores.get(drag.id), drag.dir, dx, dTop)
    }
    // 숨은 모듈은 그리지 않는다.
    const dragged = drag.ids.map(itemOf).filter((m) => !m.ghost)
    // 좌표 없던 모듈이 처음 놓이면 상자가 아직 없다 — 그때 한 번 목록을 다시 만든다.
    if (dragged.some((m) => onCanvas(m) !== S.groups.has(m.id))) renderItems()
    else for (const m of dragged) position(S.groups.get(m.id), m)
    drag.moved = true
    drawSelectionBox()
    showDragGuides(drag, event.altKey)
    markDragOverlap(new Set(drag.ids))
    updateStatus()
  }
  svg.onpointerup = svg.onpointercancel = (event) => {
    const drag = S.drag
    if (!drag || (event && event.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
    S.drag = null
    clearGuides()
    if (drag.mode === 'pan') { svg.classList.remove('is-panning'); return }
    if (drag.mode === 'view') {
      svg.classList.remove('is-panning')
      // 끌어서 옮긴 직후의 더블클릭(누르고 곧바로 그 자리에서 끈 경우)은 확대·전체 보기가 아니다.
      S.lastViewDragMoved = drag.moved
      // 포인터 캡처 때문에 뒤따르는 click·dblclick 의 target 은 캔버스로 바뀐다. 블록 위를 눌렀는지는 여기서 기억한다.
      const item = drag.id ? S.items.get(drag.id) : null
      // 블록 위인지는 종류로 정한다 — 비활성·연결 없는 블록도 블록이라 고르지 않는다(보기 FAB 에는 고르기가 없다).
      // 열지 말지는 `openFloor` 가 거른다.
      S.lastViewOnBlock = Boolean(FAB && item && item.kind === 'block')
      if (drag.moved) return
      // FAB 의 층 블록은 누르면 그 층을 연다(끌었으면 열지 않는다). 나머지는 고르기다.
      if (S.lastViewOnBlock) {
        if (!drag.travelled) openFloor(item)
        return
      }
      // 문턱을 넘은 끌기는 누르기가 아니다(전체 보기에서 화면이 움직이지 않아도) — 고르지도 아래 표를 좁히지도 않는다.
      if (drag.travelled) return
      select(drag.id)
      notePick()
      return
    }
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
      .filter((e) => !sameSpot(e.before, itemOf(e.id)))
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
  svg.onpointerleave = () => { S.hover = null }
  // Ctrl+휠(터치패드 오므리기 포함)은 마우스 자리를 축으로 확대·축소한다. 맨 휠은 확대 중에도 도면을
  // 옮기지 않고 페이지로 보낸다 — 확대한 도면이 먼저 굴러가다 끝에 닿아야 페이지가 굴러가면, 도면
  // 위아래의 단추로 가려던 스크롤이 도면부터 옮겨 놓는다(2026-10-10 사용자 요청). 화면 이동은 끌기
  // (보기)·Space+끌기·가운데 버튼 끌기(편집)·방향키(보기)로 한다. 예외는 편집기에서 호기·요소를 끌어
  // 옮기거나 크기를 바꾸는 동안이다 — 단추를 누른 채라 페이지로 갈 일이 없고, 화면 밖 자리로 끌고 가려면
  // 휠로 도면을 옮겨야 한다.
  svg.onwheel = (event) => {
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()
      zoomAt(S.view.z * Math.exp(-event.deltaY * unit * 0.002), toUser(event))
      if (!VIEW) S.hover = toUser(event)
      return
    }
    const placing = S.drag && (S.drag.mode === 'move' || S.drag.mode === 'resize' || S.drag.mode === 'range')
    if (!placing || S.view.z <= 1) return
    const upp = unitsPerPx()
    const dx = (event.shiftKey ? event.deltaY : event.deltaX) * unit * upp
    const dTop = (event.shiftKey ? 0 : event.deltaY) * unit * upp
    if (panBy(dx, dTop)) event.preventDefault()
  }
  svg.onblur = () => { S.spaceDown = false; svg.classList.remove('is-pan-ready') }
  // 층 블록에 올려 두면 선택 줄에 열 층을 알리고, 블록을 떠나면 되돌린다(보기 전용 FAB 만). 층 보기에서는 올려 둔
  // 호기의 풍선 글을 지금 칠한 기준일로 새로 쓴다(`freshenTip`).
  svg.onpointerover = (event) => {
    if (VIEW && !FAB) {
      const unit = event.target.closest ? event.target.closest('.sle-unit') : null
      if (unit) freshenTip(unit)
      return
    }
    if (!(VIEW && FAB) || S.drag) return
    const group = event.target.closest ? event.target.closest('.mark-block') : null
    if (group) S.showBlockHint(group)
  }
  svg.onpointerout = (event) => {
    if (!(VIEW && FAB)) return
    const from = event.target.closest ? event.target.closest('.mark-block') : null
    const into = event.relatedTarget && event.relatedTarget.closest ? event.relatedTarget.closest('.mark-block') : null
    if (from && from !== into) S.showBlockHint(into)
  }
  // 보기 전용 더블클릭: 확대 중이면 전체 보기, 전체 보기면 그 자리를 2.5배로.
  svg.ondblclick = (event) => {
    // 블록 위에서는 확대하지 않는다 — 첫 누름이 이미 그 층을 열었다.
    if (!VIEW || S.lastViewDragMoved || S.lastViewOnBlock) return
    event.preventDefault()
    if (S.view.z > 1) zoomAt(1)
    else zoomAt(2.5, toUser(event))
  }
  // 단축키는 편집기 어디에 포커스가 있어도 듣는다(툴바 단추를 누른 뒤에도). 입력 칸에서는 비킨다.
  host.onkeyup = (event) => {
    if (event.key === ' ') { S.spaceDown = false; svg.classList.remove('is-pan-ready') }
  }
  host.onkeydown = (event) => {
    if (VIEW) {
      // 보기 전용 단축키: 확대·축소·전체 보기, 방향키 화면 이동, Esc 선택 풀기. 고치는 키는 없다.
      if (event.ctrlKey || event.metaKey || event.altKey) return
      // FAB 의 층 블록에 초점이 있으면 Enter·Space 로 그 층을 연다(Space 가 페이지를 굴리지 않게 막는다).
      const block = FAB && event.target && event.target.closest ? event.target.closest('.mark-block') : null
      if (block && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault()
        openFloor(S.items.get(block.dataset.id))
        return
      }
      const step = 0.1
      const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }
      if (event.key === '+' || event.key === '=') zoomAt(S.view.z * ZOOM_STEP)
      else if (event.key === '-') zoomAt(S.view.z / ZOOM_STEP)
      else if (event.key === '0') zoomAt(1)
      else if (event.key === 'Escape') { select(null); notePick() }
      else if (moves[event.key]) {
        if (!panBy(moves[event.key][0] * viewW(), moves[event.key][1] * viewH())) return
      } else return
      event.preventDefault()
      return
    }
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
    // 도면 요소 복사·붙여넣기(호기는 복사하지 않는다). 한글 자판에서도 듣게 글쇠 자리(code)도 본다. 글 칸에서는 위에서 비켰다.
    const letter = event.code === 'KeyC' ? 'c' : event.code === 'KeyV' ? 'v' : event.key.toLowerCase()
    if (ctrl && letter === 'c') { if (copyMarks()) event.preventDefault(); return }
    if (ctrl && letter === 'v') { if (pasteMarks(event.altKey)) event.preventDefault(); return }
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
      // Ctrl+방향키는 크기 — 고른 것마다 오른쪽 폭, 위 높이(왼쪽 아래 모서리는 그대로). 모듈 묶음은 범위다.
      if (ctrl) setSizes(standing, (m) => ({ w: m.w + ax, h: m.h + ay }))
      else moveItems(standing, ax, ay)
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
      // X·Y 의 기준은 함께 움직일 것의 왼쪽 아래(하나면 그 상자, 모듈 묶음이면 그 범위)다.
      const box = movePlan(standing).box
      if (field === 'x') moveItems(standing, value - box.minX, 0)
      else if (field === 'y') moveItems(standing, 0, value - box.minY)
      else setSizes(standing, () => ({ [field]: value }))
    }
    input.onkeydown = (event) => { if (event.key === 'Enter') input.blur() }
  }
  const selectedMark = () => {
    const chosen = selectedItems()
    return chosen.length === 1 && isMark(chosen[0]) ? chosen[0] : null
  }
  // 두 이름 칸은 들어갈 때 고른 대상에 묶는다(`S.markLabelFor`·`S.unitLabelFor`). change 는 칸을 떠날 때 나므로, 그
  // 사이 고른 것이 바뀌어도 적던 글자가 새로 고른 대상에 붙지 않는다(`commitTyping` 이 먼저 확정하지만 그것을 거치지
  // 않는 길까지 막는다).
  const singleSelected = () => {
    const chosen = selectedItems()
    return chosen.length === 1 ? chosen[0] : null
  }
  markLabel.onfocus = () => {
    const one = singleSelected()
    S.markLabelFor = one && isMark(one) ? one.id : null
  }
  markLabel.onblur = () => { S.markLabelFor = null }
  markLabel.onchange = () => {
    const mark = S.items.get(S.markLabelFor)
    const value = markLabel.value.trim().slice(0, 40)
    if (mark && isMark(mark) && value !== (mark.label || '')) setMarkProps(mark, { label: value })
    else syncInspector()
  }
  markLabel.onkeydown = (event) => { if (event.key === 'Enter') markLabel.blur() }
  unitLabel.onfocus = () => {
    const one = singleSelected()
    S.unitLabelFor = one && isUnit(one) && !one.moveTo ? one.id : null
  }
  unitLabel.onblur = () => { S.unitLabelFor = null }
  unitLabel.onchange = () => {
    const item = S.items.get(S.unitLabelFor)
    if (item && isUnit(item) && !item.moveTo) renameUnit(item, unitLabel.value)
    else syncInspector()
  }
  unitLabel.onkeydown = (event) => {
    if (event.key === 'Enter') unitLabel.blur()
    if (event.key !== 'Escape') return
    // Esc 는 고치던 글자를 버린다(지금 이름으로 되돌리고 칸을 떠난다 — 바뀐 것이 없으니 change 가 나지 않는다).
    event.preventDefault()
    event.stopPropagation()
    const item = S.items.get(S.unitLabelFor)
    unitLabel.value = item && isUnit(item) ? renameTarget(item).name : ''
    unitLabel.blur()
  }
  markColor.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { color: markColor.value }) }
  markBorder.onchange = () => { const mark = selectedMark(); if (mark && mark.kind === 'zone') setMarkProps(mark, { borderStyle: pickOr(markBorder.value, BORDER_STYLES) }) }
  markAlign.onchange = () => { const mark = selectedMark(); if (mark && mark.kind === 'zone') setMarkProps(mark, { labelAlign: pickOr(markAlign.value, LABEL_ALIGNS) }) }
  groupNamePos.onchange = () => {
    const one = singleSelected()
    if (one && isUnit(one) && moduleMembers(one)) setGroupLabel(groupKeyOf(one), groupNamePos.value)
    else syncInspector()
  }
  markFontSize.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { fontSize: fontSizeOf(markFontSize.value) }) }
  markFontColor.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { fontColor: markFontColor.value }) }
  markHatch.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { hatch: markHatch.checked }) }
  markKeepOut.onchange = () => { const mark = selectedMark(); if (mark) setMarkProps(mark, { keepOut: markKeepOut.checked }) }
  markRotate.onclick = () => { const mark = selectedMark(); if (mark) rotateMark(mark) }
  blockLink.onchange = () => { const mark = selectedMark(); if (mark && mark.kind === 'block' && blockLink.value) setMarkProps(mark, { link: blockLink.value }) }
  blockColor.onchange = () => { const mark = selectedMark(); if (mark && mark.kind === 'block') setMarkProps(mark, { color: blockColor.value }) }
  blockOpen.onclick = () => openFloor(selectedMark(), true)
  for (const button of host.querySelectorAll('.sle-palette [data-kind]')) {
    const kind = button.dataset.kind
    const [w, h] = MARK_KINDS[kind].size
    button.onpointerdown = (event) => ghostDrag(event, MARK_KINDS[kind].name, (p, free) => addMark(kind, p, free), () => addMark(kind), () => ({ w, h }))
  }

  // ---------------------------------------------------------------- 편집기에서 호기 추가
  // 적용 전까지는 이 편집기 안에만 있다(층 미정·미배치). 설비 마스터가 꼭 요구하는 값만 받는다 — 공정·공정구분·
  // 투자구분·크기. 신규 설비의 반입·Qual 일정은 비워도 되고(반입이 비면 입고 예정, Qual 이 비면 셋업 진행중으로
  // 남는다), Qual상태는 Qual 일정을 넣었을 때만 필요하다. 다른 호기의 일정·Qual상태를 베끼지 않는다. 마스터의
  // 나머지 칸은 가용설비에서 채운다.
  const fillSelect = (node, values, blank) => {
    const wanted = [blank === undefined ? null : blank, ...values].filter((v) => v !== null)
    if ([...node.options].map((o) => o.value).join('|') === wanted.join('|')) return
    node.replaceChildren(...wanted.map((v) => new Option(v === '' ? '(비움)' : v, v)))
  }
  fillSelect(newProcess, (NEW_UNIT.processes || []).map(String))
  fillSelect(newLine, (NEW_UNIT.lines || []).map(String), '')
  fillSelect(newUse, (NEW_UNIT.uses || []).map(String), '')
  fillSelect(newConfirm, (NEW_UNIT.confirmations || ['계획']).map(String), '')
  newKind.onchange = () => { newDates.hidden = newKind.value === 'existing' }
  newDates.hidden = newKind.value === 'existing'
  // Qual상태는 Qual 일정을 넣었을 때만 필요하다 — 그때만 필수로 표시한다(검사는 추가 단추에서).
  const markConfirmRequired = () => {
    const needed = Boolean(newQual.value)
    newConfirm.setAttribute('aria-required', String(needed))
    newConfirmRow.classList.toggle('is-required', needed)
  }
  newQual.oninput = newQual.onchange = markConfirmRequired
  markConfirmRequired()
  const sizeHint = () => {
    const hint = (NEW_UNIT.sizeHints || {})[newProcess.value]
    return Array.isArray(hint) && hint.length === 2 ? hint : [defaultSize.w, defaultSize.h]
  }
  const showHint = () => { const [w, h] = sizeHint(); newW.placeholder = String(w); newH.placeholder = String(h) }
  showHint()
  newProcess.onchange = showHint
  // 새 호기 폼을 끈 편집(공식 발행 쌍이지만 그 시나리오에 더 새 리비전이 있는 세션 — 일정이 생기는 새
  // 호기는 저장에서 막힌다). 단추를 끄고 까닭을 풍선으로 보인다. 다른 편집은 그대로다.
  if (NEW_UNIT.disabled) {
    addToggle.disabled = true
    addToggle.title = String(NEW_UNIT.disabled)
    addForm.hidden = true
  }
  addToggle.onclick = () => {
    if (NEW_UNIT.disabled) return
    addForm.hidden = !addForm.hidden
    addToggle.setAttribute('aria-expanded', String(!addForm.hidden))
    if (!addForm.hidden) newId.focus()
  }
  q('.sle-addunit-close').onclick = () => { addForm.hidden = true; addToggle.setAttribute('aria-expanded', 'false') }
  addForm.onsubmit = (event) => {
    event.preventDefault()
    const id = cleanName(newId.value)
    const [hintW, hintH] = sizeHint()
    const w = newW.value === '' ? hintW : roundTo(Number(newW.value))
    const h = newH.value === '' ? hintH : roundTo(Number(newH.value))
    // 이름 바꾸기와 같은 겹침 검사다 — 편집기 호기는 지금(바꾼) 이름으로 보고, 대소문자·앞뒤 공백만 다른 이름도
    // 같은 이름이다(파이썬 `_parse_created` 도 같다). 키(`S.items` 의 열쇠)는 옛 이름이라 이름 검사에 쓰지 않는다.
    const clash = id ? nameClash(id, { created: true, label: id, group: null }, false) : null
    let error = ''
    if (!id) error = '설비명을 적어 주세요.'
    else if (clash) error = `${id} 는 이미 있는 이름입니다(${clash}).`
    else if (!newProcess.value) error = '공정을 골라 주세요.'
    else if (!(w > 0 && h > 0 && w <= MAX_EXTENT && h <= MAX_EXTENT)) error = `크기는 0 보다 크고 ${MAX_EXTENT} 이하여야 합니다.`
    const existing = newKind.value === 'existing'
    if (!error && !existing && newArrival.value && newQual.value && newQual.value < newArrival.value) error = 'Qual일정은 반입일정보다 빠를 수 없습니다.'
    else if (!error && !existing && newQual.value && !newConfirm.value) error = 'Qual일정을 넣으면 Qual상태를 골라 주세요.'
    newError.textContent = error
    if (error) return
    // 열쇠는 편집기 안에서만 쓴다(적용값의 새 호기 이름은 `label`). 이름을 바꾼 새 호기가 이 이름을 열쇠로 쥐고
    // 있으면 다른 열쇠를 쓴다 — 같은 열쇠로 덮으면 그 호기가 사라진다.
    let key = id
    while (S.items.has(key)) { S.seq += 1; key = `${id}~${S.seq}` }
    const item = {
      id: key, kind: 'unit', label: id, stage: existing ? '가용' : '입고 예정', group: null, x: NaN, y: NaN, w, h,
      placed: false, moveTo: null, isNew: true, arrived: false, floorless: true, sizeGuessed: false, ...unitLook({}),
      created: {
        process: newProcess.value, line: newLine.value, use: newUse.value, existing,
        arrival: existing ? '' : newArrival.value, qual: existing ? '' : newQual.value, confirm: existing ? '' : newConfirm.value,
      },
    }
    S.items.set(key, item)
    pushUndo([{ op: 'create', id: key }])
    newId.value = ''
    newW.value = ''
    newH.value = ''
    renderItems()
    setSelection([key], key)
  }

  // ---------------------------------------------------------------- 단추
  moveButton.onclick = () => sendItems(selectedItems(), moveSelect.value)
  moduleTile.onclick = () => {
    const chosen = selectedItems()
    if (chosen.length === 1) retileModules(chosen[0])
  }
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
    const nameChanges = renames()
    const marksChanged = markChangeCount() > 0
    const labelsChanged = groupLabelChangeCount() > 0
    if (!unitChanges.length && !nameChanges.length && !marksChanged && !labelsChanged && !canvasChanged()) return
    setTriggerValue('apply', {
      epoch: S.epoch,
      changes: unitChanges,
      ghosts: ghostChanges(),
      renames: nameChanges,
      canvas: canvasChanged() ? { width: W(), height: H() } : null,
      marks: marksChanged ? marksPayload() : null,
      // 이 층에 남는 모듈 묶음의 Main 설비명 위치(늘 보낸다 — 다른 층으로 보낸 묶음이 빠지는 것도 여기서 안다).
      groupLabels: FAB ? null : groupLabelsPayload(),
    })
  }

  // ---------------------------------------------------------------- 트레이 서랍(편집)
  const drawerClose = q('.sle-drawer-close')
  drawerTab.onclick = () => {
    setDrawer(true)
    drawerClose.focus({ preventScroll: true })
  }
  drawerClose.onclick = () => {
    setDrawer(false)
    drawerTab.focus({ preventScroll: true })
  }
  drawer.onkeydown = (event) => {
    if (event.key !== 'Escape' || !S.drawerOpen || S.drag) return
    event.preventDefault()
    event.stopPropagation()
    setDrawer(false)
    drawerTab.focus({ preventScroll: true })
  }
  traySearch.value = S.trayQuery || ''
  traySearch.oninput = () => {
    S.trayQuery = traySearch.value
    applyTrayFilter()
    trayBox.scrollTop = 0
  }
  // 검색어가 있으면 Esc 는 서랍을 접기 전에 검색어부터 지운다.
  traySearch.onkeydown = (event) => {
    if (event.key !== 'Escape' || !traySearch.value) return
    event.preventDefault()
    event.stopPropagation()
    traySearch.value = ''
    S.trayQuery = ''
    applyTrayFilter()
  }
  setDrawer(S.drawerOpen)

  // ---------------------------------------------------------------- 기준일 줄(층 도면)·FAB 기준일
  // 층 상세 보기의 맨 위 줄은 페이더다(오늘 ±12개월, 하루 단위, 가운데 오늘). 끄는 동안 서버 회차는 없다 — 프레임마다
  // (requestAnimationFrame) 판정 부호가 바뀐 상자만 칠하고(`paintAsOf`), 손을 떼면(키는 멈춘 뒤) `setStateValue` 로
  // 기준일을 **한 번** 보낸다. 그 회차에 파이썬이 세션 기준일을 바꿔 범례·요약·호기 표를 맞춘다. 배치 편집(층) 중에는
  // 같은 자리·같은 높이에 「기준일 … · 편집 중 고정」 줄이 선다. FAB 전체에는 페이더 없이 도구 줄에 기준일·「오늘로」·
  // 미확인 대수가 선다.
  const faderInput = q('.sle-fader-input')
  const faderTicks = q('.sle-fader-ticks')
  const faderDate = q('.sle-fader-date')
  const faderRel = q('.sle-fader-rel')
  const faderNote = q('.sle-fader-note')
  const faderToday = q('.sle-fader-today')
  const pinnedDate = q('.sle-pinned-date')
  const fabAsOf = q('.sle-asof')
  const fabAsOfDate = q('.sle-asof-date')
  const fabToToday = q('.sle-totoday')
  const flagNote = q('.sle-flagnote')
  const flagCount = q('.sle-flagnote-count')
  // 오늘에서 얼마나 떨어졌나 — 「오늘」, 「+3개월 2주」, 「−1개월 3일」.
  function relText(T) {
    if (!T || T === TODAY) return '오늘'
    const t = dayNumber(T)
    const d = dayNumber(TODAY)
    const [a, b] = t < d ? [t, d] : [d, t]
    let months = 0
    while (addMonths(a, months + 1) <= b) months += 1
    const rest = b - addMonths(a, months)
    const parts = []
    if (months) parts.push(`${months}개월`)
    if (Math.floor(rest / 7)) parts.push(`${Math.floor(rest / 7)}주`)
    if (rest % 7) parts.push(`${rest % 7}일`)
    return `${t > d ? '+' : '−'}${parts.join(' ')}`
  }
  const lowDay = () => dayNumber(RANGE.min)
  const highDay = () => dayNumber(RANGE.max)
  // 트랙 위 자리(손잡이 가운데와 맞춘다 — 손잡이는 양 끝에서 반지름만큼 들어와 선다).
  const along = (n) => `calc(${THUMB_PX / 2}px + ${(n - lowDay()) / Math.max(highDay() - lowDay(), 1)} * (100% - ${THUMB_PX}px))`

  // 눈금 — 달마다 짧은 눈금, 분기(1·4·7·10월)는 조금 길게 「YY.MM」 글자, 가운데 오늘은 굵게 「오늘」. 범위·오늘이
  // 바뀔 때만(날이 지나면) 다시 그린다.
  function buildFader() {
    const key = `${RANGE.min}|${TODAY}|${RANGE.max}`
    if (S.faderKey === key && faderTicks.childElementCount) return
    S.faderKey = key
    const lo = lowDay()
    const hi = highDay()
    const today = dayNumber(TODAY)
    faderInput.min = '0'
    faderInput.max = String(hi - lo)
    const nodes = []
    const mark = (className, n, text) => {
      const node = document.createElement('span')
      node.className = className
      node.style.left = along(n)
      if (text) node.textContent = text
      nodes.push(node)
    }
    const start = new Date(lo * DAY_MS)
    for (let n = Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1) / DAY_MS; n <= hi; n = addMonths(n, 1)) {
      const d = new Date(n * DAY_MS)
      const quarter = d.getUTCMonth() % 3 === 0
      mark(quarter ? 'sle-tick is-quarter' : 'sle-tick', n)
      // 오늘 글자·트랙 양 끝과 겹치는 분기 글자는 뺀다.
      if (quarter && Math.abs(n - today) > 40 && n - lo > 20 && hi - n > 20) {
        mark('sle-tick-label', n, `${String(d.getUTCFullYear()).slice(2)}.${String(d.getUTCMonth() + 1).padStart(2, '0')}`)
      }
    }
    mark('sle-tick is-today', today)
    mark('sle-tick-label is-today', today, '오늘')
    faderTicks.replaceChildren(...nodes)
  }

  // 페이더 줄을 칠한 날에 맞춘다 — 손잡이 자리·오늘과 사이 구간·날짜 칩, 그리고 범례·요약이 아직 이전 날 값이면 그 날.
  function showFader() {
    if (!FADER) return
    const now = dayNumber(S.asOf || TODAY)
    const today = dayNumber(TODAY)
    const value = String(now - lowDay())
    if (faderInput.value !== value) faderInput.value = value
    faderInput.style.setProperty('--fd-a', along(Math.min(now, today)))
    faderInput.style.setProperty('--fd-b', along(Math.max(now, today)))
    const isToday = !S.asOf || S.asOf === TODAY
    setText(faderDate, S.asOf || TODAY)
    setText(faderRel, `· ${relText(S.asOf)}`)
    faderRel.classList.toggle('is-today', isToday)
    faderToday.disabled = isToday
    setAttr(faderInput, 'aria-valuetext', `${S.asOf || TODAY} (${relText(S.asOf)})`)
    setText(faderNote, !S.dataAsOf || S.asOf === S.dataAsOf
      ? ''
      : S.sent.size
        ? `범례·요약 맞추는 중 · 지금 ${S.dataAsOf}`
        : `범례·요약 ${S.dataAsOf} 기준 · 놓으면 맞춤`)
  }

  // 끄는 동안의 날 — 프레임마다 한 번만 칠한다(마지막 날만).
  function setAsOf(T) {
    S.faderTarget = T < RANGE.min ? RANGE.min : T > RANGE.max ? RANGE.max : T
    if (!S.faderFrame) S.faderFrame = requestAnimationFrame(flushAsOf)
  }
  function flushAsOf() {
    S.faderFrame = 0
    const T = S.faderTarget
    if (T && T !== S.asOf) {
      const previous = S.asOf
      S.asOf = T
      paintAsOf(previous)
    }
    showFader()
  }
  // 놓을 때 한 번 보낸다. 파이썬이 이미 쥐었거나 곧 쥘 날(보낸 날)과 같으면 보내지 않는다.
  function commitAsOf() {
    if (S.commitTimer) clearTimeout(S.commitTimer)
    S.commitTimer = 0
    if (S.faderFrame) {
      cancelAnimationFrame(S.faderFrame)
      flushAsOf()
    }
    S.faderBusy = false
    const T = S.asOf
    const expected = S.sent.size ? S.lastSent : S.dataAsOf
    if (T && T !== expected) {
      S.sent.add(T)
      S.lastSent = T
      setStateValue('asOf', T)
    }
    showFader()
  }
  const jumpTo = (T) => {
    setAsOf(T)
    commitAsOf()
  }

  if (FADER) {
    buildFader()
    faderInput.oninput = () => {
      S.faderBusy = true
      setAsOf(isoOf(lowDay() + Number(faderInput.value)))
    }
    faderInput.onchange = () => commitAsOf()
    // 바꾸지 않고 놓았거나(값 그대로라 change 가 없다) 키를 누른 채 초점을 옮겨도 남은 날을 보낸다.
    faderInput.onpointerup = faderInput.onpointercancel = faderInput.onblur = () => {
      if (S.faderBusy || S.commitTimer) commitAsOf()
    }
    faderInput.ondblclick = (event) => {
      event.preventDefault()
      jumpTo(TODAY)
    }
    // 오늘이 되면 이 단추가 꺼진다(disabled) — 키보드로 누른 초점이 문서 맨 앞으로 떨어지지 않게 먼저 페이더로
    // 옮긴다.
    faderToday.onclick = () => {
      if (faderToday.matches(':focus')) faderInput.focus({ preventScroll: true })
      jumpTo(TODAY)
    }
    // ←/→(↓/↑) 하루, PageDown/PageUp 한 달, Home/End 범위 끝. 도면 단축키(화면 이동·확대)로 새지 않게 여기서 멈춘다.
    faderInput.onkeydown = (event) => {
      if (event.key === 'Tab' || event.key === 'Escape') return
      event.stopPropagation()
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const now = dayNumber(S.faderTarget || S.asOf || TODAY)
      const next = {
        ArrowLeft: now - 1, ArrowDown: now - 1, ArrowRight: now + 1, ArrowUp: now + 1,
        PageDown: addMonths(now, -1), PageUp: addMonths(now, 1), Home: lowDay(), End: highDay(),
      }[event.key]
      if (next === undefined) return
      event.preventDefault()
      setAsOf(isoOf(next))
      if (S.commitTimer) clearTimeout(S.commitTimer)
      S.commitTimer = setTimeout(commitAsOf, KEY_COMMIT_MS)
    }
    showFader()
  }
  if (PINNED) setText(pinnedDate, `기준일 ${S.asOf || '—'}`)
  if (VIEW && FAB) {
    // 좁은 도구 줄에서는 「기준일」 말머리를 접고 날짜도 말줄임으로 줄 수 있어(CSS) 풍선에 온 글을 둔다.
    fabAsOf.hidden = !S.asOf
    setText(fabAsOfDate, S.asOf || '')
    setAttr(fabAsOf, 'title', S.asOf ? `블록 대수의 기준일 ${S.asOf} — 층 상세 도면 위 페이더로 바꿉니다` : '')
    fabToToday.hidden = !TODAY || !S.asOf || S.asOf === TODAY
    fabToToday.disabled = false
    fabToToday.onclick = () => {
      if (!TODAY || S.asOf === TODAY) return
      // 단추는 곧 꺼지고 다음 회차에 숨는다 — 초점을 먼저 도면으로 옮겨 키보드 초점을 잃지 않게 한다.
      if (fabToToday.matches(':focus')) svg.focus({ preventScroll: true })
      fabToToday.disabled = true
      setStateValue('asOf', TODAY)
    }
    const flagged = Math.max(Number(data.unconfirmed) || 0, 0)
    flagNote.hidden = flagged === 0
    setText(flagCount, `${flagged.toLocaleString('ko-KR')}대`)
    setAttr(flagNote, 'title', `미확인 ${flagged.toLocaleString('ko-KR')}대 — 오늘 기준으로 반입·Qual 일정이 지났는데 실적이 `
      + '비고 상태가 계획·확정인 설비입니다. 가용설비 현황 설비 마스터에서 고칩니다.')
  }
  // FAB 도구 줄이 넘치면 접는 차례(`is-fit1`~`is-fit5`, CSS 「FAB 도구 줄」)를 하나씩 더한다 — 요약은 마지막에야
  // 준다. 회차의 글자를 쓴 뒤와 크기가 바뀔 때(`S.onResize`) 다시 잰다. 층·편집 도구 줄은 건드리지 않는다.
  const toolbar = q('.sle-toolbar')
  const FIT_STEPS = ['is-fit1', 'is-fit2', 'is-fit3', 'is-fit4', 'is-fit5']
  function fitFabBar() {
    toolbar.classList.remove(...FIT_STEPS)
    if (!(VIEW && FAB) || !toolbar.clientWidth) return
    for (const step of FIT_STEPS) {
      if (toolbar.scrollWidth <= toolbar.clientWidth) return
      toolbar.classList.add(step)
    }
  }

  // ---------------------------------------------------------------- 높이 손잡이
  // 끌기·키는 브라우저 안에서만 무대 높이를 바꾼다(재실행 없음). 방향키는 편집기 단축키(화면 옮기기·호기 이동)로
  // 새지 않게 여기서 멈춘다.
  resizeHandle.onpointerdown = (event) => {
    if (event.button !== 0) return
    event.preventDefault()
    resizeHandle.setPointerCapture(event.pointerId)
    S.heightDrag = { pointerId: event.pointerId, startY: event.clientY, startH: S.stageH || stage.clientHeight, moved: false }
  }
  resizeHandle.onpointermove = (event) => {
    const drag = S.heightDrag
    if (!drag || event.pointerId !== drag.pointerId) return
    const dy = event.clientY - drag.startY
    if (!drag.moved && Math.abs(dy) < DRAG_THRESHOLD_PX) return
    drag.moved = true
    resizeHandle.classList.add('is-dragging')
    setStageHeight(clamp(drag.startH + dy, MIN_DRAG_H, maxHeight()))
  }
  resizeHandle.onpointerup = resizeHandle.onpointercancel = (event) => {
    const drag = S.heightDrag
    if (!drag || (event && event.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
    S.heightDrag = null
    resizeHandle.classList.remove('is-dragging')
    if (drag.moved) chooseHeight(S.stageH)
  }
  resizeHandle.onlostpointercapture = (event) => { if (S.heightDrag) resizeHandle.onpointerup(event) }
  resizeHandle.ondblclick = (event) => {
    event.preventDefault()
    resetHeight()
  }
  resizeHandle.onkeydown = (event) => {
    const step = HEIGHT_KEY_STEP * (event.shiftKey ? 4 : 1)
    if (event.key === 'ArrowUp') chooseHeight((S.stageH || stage.clientHeight) - step)
    else if (event.key === 'ArrowDown') chooseHeight((S.stageH || stage.clientHeight) + step)
    else if (event.key === 'Home' || event.key === 'Enter') resetHeight()
    else return
    event.preventDefault()
    event.stopPropagation()
  }

  // ---------------------------------------------------------------- 크기 바뀜
  // 관찰자는 한 번만 만든다(S.ro). 실행마다 새로 정의되는 S.onResize 를 부르므로 첫 실행의 낡은 값(데이터·
  // 팔레트·VIEW)을 쥐지 않는다. rAF 로 묶고, 바뀐 px 크기로 viewBox 비율과 화면 px 에 기대는 값(손잡이·글자
  // 크기)을 다시 맞춘다. 창 높이만 바뀌어도 기본 높이·상한이 바뀌므로 창 크기도 듣는다.
  S.onResize = () => {
    const changed = S.heightDrag ? measurePort() : fitStage()
    if (changed) applyView()
    fitFabBar()
  }
  if (!S.ro && typeof ResizeObserver === 'function') {
    const schedule = () => {
      if (S.resizeFrame) return
      S.resizeFrame = requestAnimationFrame(() => {
        S.resizeFrame = 0
        if (S.onResize) S.onResize()
      })
    }
    S.ro = new ResizeObserver(schedule)
    S.ro.observe(stage)
    S.onWindowResize = schedule
    window.addEventListener('resize', schedule)
  }
  // 이번 실행에서 무대 크기가 달라졌으면(첫 실행·열 폭 변화) 바로 맞춘다.
  S.onResize()
  updateStatus()
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    if (S.ro) S.ro.disconnect()
    if (S.onWindowResize) window.removeEventListener('resize', S.onWindowResize)
    if (S.resizeFrame) cancelAnimationFrame(S.resizeFrame)
    S.ro = null
    S.onWindowResize = null
    S.resizeFrame = 0
  }
}
