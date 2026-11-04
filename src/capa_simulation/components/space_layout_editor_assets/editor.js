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
    // 층 상세 보기: 겹쳐 숨긴 반입 예정 호기(id → 설비지분, `paintUnit`)와 필요 단축 칸에 고른 호기 — 파이썬이 쥔 값
    // (`data.picked`, 받은 그대로 `pickData`)과 브라우저가 보낸 값(`pickSent`).
    covered: new Map(), pickData: undefined, pickSent: null,
    // 두 옆 칸의 폭·접힘(보기 상태 — 범위·모드별, `capa.space.panels.v1` 에서 처음 읽음)과 좁은 화면 겹침 서랍의 열린 칸
    // (`narrowOpen` — 'left'|'right'|null, 기억하지 않는다), 마지막에 폭을 끈 칸. 스크롤 고정(`lock` — 마운트에만 둔다).
    panels: null, narrowOpen: null, panelLast: null, lock: false, lockH: null,
    // 서식 복사·붙여넣기 — 든 붓(`paint` = {clip, sticky}), 담은 서식(`formatClip` — 회차마다 저장소에서 다시 읽음), 붙일 것 체크.
    paint: null, formatClip: null, formatParts: null,
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
  // 색 기준 「필요 단축」 을 켠 층 보기 — 파이썬이 `asOfPinned`(고정 줄 뒷글)를 실을 때만이다. 기준일은 오늘로
  // 고정이라 페이더 자리에 배치 편집과 같은 꼴의 고정 줄이 서고, 표시된 호기(`layer`)는 겹쳐 숨기지 않으며, 모든 호기의
  // 지연·보관 면을 칠하지 않는다(결정 D12 — 풍선 글로만). 배지(`shortBadges`)도 이때만 그린다. 끈 동안 data 에 두 칸이
  // 없다. 같은 epoch 안에서 고정 ↔ 페이더가 오가도 `adoptAsOf` 가 받은 날을 따른다(고정 동안 FADER 가 거짓).
  const ASOF_PINNED = VIEW && !FAB && typeof data.asOfPinned === 'string' && data.asOfPinned !== ''
  host.classList.toggle('is-pinned', ASOF_PINNED)
  const SHORT_BADGES = ASOF_PINNED && Array.isArray(data.shortBadges) ? data.shortBadges : []
  const SHORT_LAYERS = new Set(['s', 'm', 'l', 'x'])
  const FADER = VIEW && !FAB && !ASOF_PINNED && Boolean(TODAY && RANGE.min && RANGE.max && RANGE.min <= TODAY && TODAY <= RANGE.max)
  const PINNED = (!VIEW && !FAB) || ASOF_PINNED
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
  // 「호기 정보」 목록 줄을 누르면 그 호기로 옮기며 이 배율까지만 확대한다 — 둘레 호기·영역과 함께 보이게(2026-11-04 Space 결정
  // 보드 답 「300%」). 「고른 곳 보기」 는 그대로 최대(MAX_ZOOM)다.
  const LIST_ROW_ZOOM = 3
  const ZOOM_STEP = 1.25
  const DRAG_THRESHOLD_PX = 3
  const HANDLE_PX = 9
  // 보기 화면 덧표시(화면 px) — 선택 후광의 띄움, 「!」·운영 비가동 표식의 반지름, 겹침 꼭지 삼각의 변.
  const HALO_GAP_PX = 3
  // 키보드 초점 테(호기·편집의 도면 요소)의 띄움(화면 px). 보기의 선택 후광(HALO_GAP_PX)보다 밖이라 둘이 겹쳐도 따로 보인다.
  // CSS outline 은 SVG 안에서 도면 배율로 커져(확대하면 수십 px) 쓰지 않는다.
  const FOCUS_GAP_PX = 5
  const BADGE_PX = 7
  const CORNER_PX = 11
  const GROUP_PAD = 0.6
  // 좁은 화면 겹침 서랍이 무대 가장자리에서 들어앉은 거리(CSS `.sle.is-narrow .sle-side` 의 8px). 놓은 호기를 서랍 왼쪽으로
  // 이만큼 더 꺼낸다.
  const DRAWER_INSET_PX = 8
  // 편집 영역 둘레의 여백(영역 긴 변의 비율). 전체 보기는 영역+여백이 다 보이는 크기다.
  const VIEW_MARGIN = 0.03
  // 무대 높이(px). 기본은 화면에 맞추고(MIN_DEFAULT_H 이상), 손잡이로는 MIN_DRAG_H ~ 화면 높이의 MAX_H_RATIO 배.
  const MIN_DEFAULT_H = 320
  const MIN_DRAG_H = 280
  const MAX_H_RATIO = 1.5
  // 무대 위·아래에 서는 것(앱 머리·화면 탭 줄·페이지 제목·알림 칸·도구 줄, 아래 손잡이·상태 줄·여유)의 몫. 무대의 실제
  // 위치로 재지 않는다 — 위 알림 칸(저장 안 한 배치 등)이 서고 사라질 때마다 도면 높이가 바뀌면 안 된다. 레이아웃 위 경로
  // 줄·머리 줄·테두리 상자를 사이드바로 옮겨(2026-11-03 사용자 요청) 그 몫을 줄였다. 층 보기는 맨 위에 기준일 페이더 줄
  // (DATE_ROW_PX)과 그 아래 틈(8px, `.sle` gap)이 더 서고, 층 편집은 그 줄이 도구 줄 칩이라 없다. FAB 에도 없다.
  const VIEW_CHROME_PX = 215
  const DATE_ROW_PX = 36
  // 편집 화면은 무대 아래에 상태 줄(한 줄 + 틈)이 더 선다.
  const STATUS_ROW_PX = 26
  const CHROME_PX = VIEW_CHROME_PX + (FAB || !VIEW ? 0 : DATE_ROW_PX + 8) + (VIEW ? 0 : STATUS_ROW_PX)
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
    // 베이 화살표(U자 — 2026-11-03 사용자 요청). 0° 는 여는 쪽이 왼쪽인 ⊃ 꼴이고 머리는 아래 팔 끝에서 왼쪽을 향한다. 가운데 글은
    // 「B<번호>」 — 이름표 칸에는 번호만 둔다(`bayNumber`). 층 도면에만 있다(FAB 에는 넣지 않는다 — 사양 D7).
    bay: { name: '베이', size: [10, 4], label: '', rotatable: true },
    // 도형(2026-11-03 사용자 요청 — 엑셀 도형처럼). 프리셋 아홉은 look.shape(`SHAPE_PRESETS` — 넣는 크기도 프리셋마다)이고 층·FAB
    // 둘 다다. 꾸밈이라 막는 요소가 아니고 호기 아래 층에 그린다. 돌리기는 비대칭 꼴(ㄴ·ㄷ·삼각·블록 화살표)에만 켜진다.
    shape: { name: '도형', size: [8, 6], label: '', rotatable: true },
    // FAB 층 블록. 연결(link, 「C1 1F」)이 필수다. 색은 사용자가 고르는 자리 구분 색이고 빈 값은 Space 기본 면이다.
    block: { name: '층 블록', size: [16, 6], label: '', rotatable: false },
  }
  // 이 범위에서 그리는 종류. 층 블록은 FAB 에만, 베이는 층에만 있다 — 다른 범위에 오면 그리지 않고 그대로 돌려보낸다.
  const drawable = (kind) => Boolean(MARK_KINDS[kind]) && (kind !== 'block' || FAB) && (kind !== 'bay' || !FAB)
  const ZONE_COLOR_NAMES = { blue: '파랑', green: '초록', violet: '보라', sky: '하늘', rose: '분홍', gray: '회색' }
  // 요소 이름표의 글자 기준 크기·색. 크기 null 은 「자동」(글자 요소는 상자에 맞추고 나머지는 LABEL_PX), 색 '' 은 기본
  // 글자색(--sle-mark-ink)이다. 색 키는 영역 색과 같고 실제 색은 팔레트의 mark-text-<키> 다. 기준 크기는 도면 1칸이 화면
  // TEXT_REF_PPU px 일 때의 화면 px 이고 배율을 따라 커지고 작아진다(`// <text-scale>`).
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
  // 「필요 단축」 배지(층 보기)의 화면 px — 윗줄·아랫줄 글자, 안 여백, 상자와의 틈(`badgeSpot`).
  const BADGE_MAIN_PX = 11
  const BADGE_SUB_PX = 9.5
  const BADGE_PAD_PX = 5
  const BADGE_GAP_PX = 3
  // 호기 이름표의 가장 작은 크기(화면 px) — 이보다 작으면 숨긴다(밀집 층, 확대하면 다시 보인다).
  const UNIT_LABEL_MIN_PX = 7
  const fontInk = (item) => (item.fontColor && markColors[item.fontColor] ? `var(--sle-mark-text-${item.fontColor})` : '')
  // 동선·베이의 선 색(look.line) → CSS 색. accent 는 강조색, ink 는 도면 글자색, 영역 색 키는 글자 색과 같은 mark-text-<키>(밝게·
  // 어둡게 모두 테마 토큰).
  const lineInk = (key) => (key === 'accent' ? 'var(--sle-accent)' : key === 'ink' ? 'var(--sle-mark-ink)'
    : markColors[key] ? `var(--sle-mark-text-${key})` : '')
  // 도형 채우기 색(요소 color) → CSS 색. 영역 색 키는 영역과 같은 범주 팔레트, ink 는 도면 글자색, surface 는 바탕 면(밝게 흰색)이다
  // — 모두 테마 토큰이라 어둡게를 따른다.
  const shapeFillInk = (key) => (key === 'ink' ? 'var(--sle-mark-ink)' : key === 'surface' ? 'var(--sle-surface)'
    : markColors[key] || markColors.blue || 'gray')
  // 도형 선 색(look.line) → CSS 색('' 은 선 없음). auto 는 채우기 색을 따른다 — 영역 색 키는 글자 색과 같은 진한 쪽(mark-text-<키>),
  // ink 는 도면 글자색, 바탕(surface)은 흰 면에 묻히지 않게 상자 테 색(frame)이다.
  const shapeLineInk = (key, fill) => {
    if (key === 'none') return ''
    const base = key === 'auto' ? fill : key
    if (key === 'auto' && base === 'surface') return 'var(--sle-frame)'
    if (base === 'ink') return 'var(--sle-mark-ink)'
    return markColors[base] ? `var(--sle-mark-text-${base})` : 'var(--sle-mark-ink)'
  }
  // 베이 가운데 글 — 늘 「B」 를 앞에 붙인다(번호가 비면 「B」 만).
  const bayCaption = (item) => `B${item.label || ''}`
  // 요소의 풍선·선택 칸 이름 — 「종류 · 이름표」(베이는 「베이 · B80」, 도형은 「도형(ㄴ자 박스) · 창고」).
  const markKindName = (item) => (item.kind === 'shape' ? `도형(${SHAPE_PRESETS[shapeOf(item.look)].name})` : MARK_KINDS[item.kind].name)
  const markTitle = (item) => {
    const shown = item.kind === 'bay' ? bayCaption(item) : item.label
    return `${markKindName(item)}${shown ? ` · ${shown}` : ''}`
  }
  // 편집 안내 첫 문단(왼쪽 칸 「도움말」 — 도면 위에는 캡션을 두지 않는다, 2026-11-03 사용자 요청).
  const GUIDE = FAB
    ? '층 블록·영역·글자를 끌어 놓아 고치고 「적용」 을 누르면 이 세션에 들어갑니다(저장 전). 층 블록을 고르면 선택 칸에서 연결 층·색을 바꾸고 [열기] 로 그 층을 엽니다. S.PKG 가 아닌 자리는 블록 대신 색을 고른 영역과 글자로 그립니다.'
    : '끌어 놓아 자리·크기를 고치고 「적용」 을 누르면 이 세션의 편집본에 들어갑니다(저장 전). 조건 카드의 공정소분류 필터와 상관없이 이 층의 도면 대상 호기를 모두 보입니다. 층이 정해지지 않은 미배치 호기는 오른쪽 미배치 칸에 함께 뜹니다. 기준일은 편집하는 동안 고정입니다(도구 줄 칩) — 바꾸려면 배치 편집을 끄고 도면 위 페이더를 씁니다. 도면의 호기를 오른쪽 칸에 끌어 놓으면 미배치로 돌아갑니다.'
  // 두 옆 칸(2026-11-03 사용자 요청 — 왼쪽 도구 칸 · 오른쪽 미배치 칸, 폭 끌기·접기·기억). 칸 폭 한계는 `panelBounds`(아래
  // 순수 구획), 기억은 `capa.space.panels.v1`(범위·모드별 {left, right: {w, min}}). 편집기 폭이 NARROW_PX 아래면 두 칸이
  // 무대 위 겹침 서랍이 된다. 무대는 STAGE_MIN_PX 아래로 줄지 않는다.
  const PANELS_STORE_KEY = 'capa.space.panels.v1'
  const SECTIONS_STORE_KEY = 'capa.space.sections.v1'
  const PANEL_STRIP_PX = 28
  const PANEL_SPLIT_PX = 6
  const STAGE_MIN_PX = 360
  const NARROW_PX = 900
  // 칸 폭 꼴 — 기본 = clamp(defLo, 편집기 폭 × defShare, defHi), 최소 lo, 최대 min(hi, 편집기 폭 × hiShare).
  const PANEL_SPECS = {
    edit: { lo: 200, defLo: 220, defShare: 0.18, defHi: 300, hi: 480, hiShare: 0.4 },
    view: { lo: 160, defLo: 200, defShare: 0, defHi: 200, hi: 360, hiShare: 0.3 },
  }
  const PANEL_MODE = `${SCOPE}.${VIEW ? 'view' : 'edit'}`
  // 왼쪽 칸은 FAB 보기에만 없다(범례가 없다). 오른쪽 미배치 칸은 층 편집에만 있다.
  const HAS_LEFT = !(VIEW && FAB)
  const HAS_RIGHT = !VIEW && !FAB
  // 스크롤 고정이 `<html>` 에 다는 속성(그 속성을 읽는 규칙은 페이지 서식 — 파이썬 `space_lock_style`).
  const LOCK_ATTR = 'data-space-lock'
  const HINT = FAB
    ? '층 블록·영역·글자를 끌어 옮기고 손잡이로 크기를 바꿉니다. 층 블록의 연결 층·색은 왼쪽 칸 「선택」 에서 고릅니다 · 끌면 다른 것의 변·가운데 선에 붙습니다(Alt 누른 채면 안 붙음) · 빈 곳을 끌거나 Shift/Ctrl+클릭으로 여러 개 · Tab 으로 가서 Enter 로 고르기(Ctrl+Enter 더하기·빼기) · Ctrl+C/V 복사·붙여넣기 · Alt+Shift+C/V 서식 복사·붙여넣기(Ctrl+Shift+C/V 도 됨 — 크기·색·선·글자, 왼쪽 칸 「서식」 붓은 두 번 누르면 잠금, Esc 끝. 입력 언어가 바뀌면 Ctrl+Shift+C/V 나 붓 단추를 쓰세요) · 도형은 노란 손잡이로 꼴 바꾸기·Shift+모서리로 비율 유지 · Shift+H/V 좌우·상하 뒤집기(비대칭 도형) · Ctrl+휠 확대 · Space+끌기 화면 이동 · 방향키 이동 · Ctrl+Z 실행 취소'
    : '호기·요소를 끌어 옮기고, 고른 것의 모서리·변 손잡이로 크기를 바꿉니다. Main 설비 모듈 묶음은 묶음 범위만 옮기고 키웁니다(안은 바둑판 자동 배치). 끌면 다른 것의 변·가운데 선에 붙습니다(Alt 누른 채면 안 붙음) · 빈 곳을 끌거나 Shift/Ctrl+클릭으로 여러 개 · Tab 으로 가서 Enter 로 고르기(Ctrl+Enter 더하기·빼기) · Ctrl+A 전체 · 호기를 두 번 누르면 「호기 정보」 창(고른 호기의 칸 · 칸 필터로 찾은 호기 도면 강조) · Ctrl+C/V 도면 요소 복사·붙여넣기 · Alt+Shift+C/V 서식 복사·붙여넣기(Ctrl+Shift+C/V 도 됨 — 크기·색·선·글자, 왼쪽 칸 「서식」 붓은 두 번 누르면 잠금, Esc 끝. 입력 언어가 바뀌면 Ctrl+Shift+C/V 나 붓 단추를 쓰세요) · 도형은 노란 손잡이로 꼴 바꾸기·Shift+모서리로 비율 유지 · Shift+H/V 좌우·상하 뒤집기(베이·비대칭 도형) · Ctrl+휠 확대 · Space+끌기 화면 이동 · 방향키 이동 · Ctrl+방향키 크기 · Ctrl+Z 실행 취소'

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
  const compareLayer = svg.querySelector('.sle-compare')
  const badgesLayer = svg.querySelector('.sle-short-badges')
  const overlay = svg.querySelector('.sle-overlay')
  const guidesLayer = svg.querySelector('.sle-guides')
  const stage = q('.sle-stage')
  const resizeHandle = q('.sle-resize')
  const bodyBox = q('.sle-body')
  const leftSide = q('.sle-side.is-left')
  const leftSplit = q('.sle-split.is-left')
  const rightSplit = q('.sle-split.is-right')
  const legendSection = q('.sle-sec[data-sec="legend"]')
  const legendBox = q('.sle-legend')
  const helpBox = q('.sle-help')
  const lockButton = q('.sle-lock')
  const pinChipDate = q('.sle-pinchip-date')
  // 오른쪽 미배치 칸(이름 `drawer*` 는 이 칸을 가리킨다). 접힌 띠가 `drawerTab`, 칸 상자가 `trayBox`, 그 안 굴리는 칸이 `trayScroll`.
  const drawer = q('.sle-side.is-right')
  const drawerTab = q('.sle-drawer-tab')
  const drawerCount = q('.sle-drawer-count')
  const trayBox = q('.sle-tray')
  const trayScroll = q('.sle-tray-scroll')
  const trayInfo = q('.sle-tray-info')
  const trayHint = q('.sle-tray-hint')
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
  // 돌리기·뒤집기 한 줄(이름표 칸 밑) — 90° 돌리기는 요소 하나, 뒤집기는 고른 것 가운데 베이·비대칭 도형 모두.
  const turnsRow = q('.sle-turns')
  const markRotate = q('.sle-mark-rotate')
  const flipButtons = [...host.querySelectorAll('.sle-flip')]
  const markNameWord = q('.sle-mark-name-word')
  const bayPrefix = q('.sle-bay-prefix')
  // 동선·베이의 선·머리(여럿 골라도 — 고른 것 가운데 동선·베이 모두에 건다).
  const lineProps = q('.sle-lineprops')
  const headToggle = q('.sle-head-toggle')
  const headNow = q('.sle-head-now')
  const headWord = q('.sle-head-word')
  const headGallery = q('.sle-head-gallery')
  const lineColor = q('.sle-line-color')
  const lineWidth = q('.sle-line-width')
  const lineStyle = q('.sle-line-style')
  // 도형 서식(여럿 골라도 — 고른 것 가운데 도형 모두에 건다)과 도면 요소 칸의 도형 넣기 갤러리.
  const shapeProps = q('.sle-shapeprops')
  const shapeSwap = q('.sle-shape-swap')
  const shapeNow = q('.sle-shape-now')
  const shapeWord = q('.sle-shape-word')
  const shapeGallery = q('.sle-shape-gallery')
  const shapeAdjRows = [...host.querySelectorAll('.sle-shape-adj-row')]
  const shapeAdjInputs = [...host.querySelectorAll('.sle-shape-adj')]
  const shapeFill = q('.sle-shape-fill')
  const shapeClear = q('.sle-shape-clear')
  const shapeLine = q('.sle-shape-line')
  const shapeWidth = q('.sle-shape-width')
  const shapeStyle = q('.sle-shape-style')
  const shapeHatch = q('.sle-shape-hatch')
  const shapeToggle = q('.sle-shape-toggle')
  const shapePalette = q('.sle-shape-palette')
  const zoneOnly = [...host.querySelectorAll('.sle-zone-only')]
  // 왼쪽 칸 「서식」(서식 붓·붙이기·붙일 것 체크·담은 서식 한 줄).
  const paintButton = q('.sle-paint')
  const paintPaste = q('.sle-paint-paste')
  const paintParts = [...host.querySelectorAll('.sle-paint-part')]
  const paintNow = q('.sle-paint-now')
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
    : '호기를 누르면 정보가 여기 뜨고 「호기 정보」 창에 그 설비 칸이 보입니다(호기를 두 번 누르면 창이 열림) · Tab 으로 호기를 고르고 Enter · Ctrl+휠 확대 · 끌어서 이동 · 빈 곳을 두 번 누르면 확대/전체 보기'
  // 「호기 정보」 창(층 보기·편집 — 2026-11-03 사용자 요청: 고른 호기의 칸을 도면 위 창에, 거꾸로 칸 필터 → 맞는 호기
  // 목록 → 도면 강조). 표 재료는 data `sheet`(epoch 밖 — 파이썬 `services/space_unit_sheet`), 거르기는 `// <unit-sheet>` 구획이다.
  // 창 자리·크기·접힘은 localStorage(`SHEET_WIN_KEY`), 열림·탭·필터·강조는 sessionStorage(`SHEET_STATE_KEY` — 탭 안 기억, 층·편집을
  // 오가도 남는다)이고 파이썬으로 보내지 않는다. FAB 에는 없다.
  const SHEET = !FAB && data.sheet && Array.isArray(data.sheet.columns) && Array.isArray(data.sheet.rows) ? data.sheet : null
  const SHEET_WIN_KEY = 'capa.space.sheet.win.v1'
  const SHEET_STATE_KEY = 'capa.space.sheet.state.v1'
  // 창 최소 크기·처음 크기(px)와 접힌 창 높이. 창은 편집기 몸(`.sle-body`) 안에 묶인다.
  const SHEET_MIN_W = 360
  const SHEET_MIN_H = 200
  const SHEET_DEF_W = 720
  const SHEET_DEF_H = 320
  const SHEET_HEAD_PX = 34
  // 「도면」 칸 이름과 그 값(파이썬 `space_unit_sheet.PLACE_*` 와 같은 글).
  const SHEET_PLACE = '도면'
  // 필터에 맞는 호기 테의 띄움(화면 px) — 선택 후광(HALO_GAP_PX ± 1)보다 바깥이다.
  const FILTER_GAP_PX = 5
  const sheetBox = q('.sle-sheet')
  const sheetToggle = q('.sle-sheet-toggle')
  const sheetHead = q('.sle-sheet-head')
  const sheetTabs = [...host.querySelectorAll('.sle-sheet-tab')]
  const sheetMin = q('.sle-sheet-min')
  // 「CSV」 단추와 두 줄 펼침(도면에 선 호기 · 보이는 줄 — 2026-11-04 Space 결정 보드 답, 옛 도면 아래 내려받기를 창 안으로).
  const sheetCsvButton = q('.sle-sheet-csv')
  const sheetCsvMenu = q('.sle-sheet-csvmenu')
  const sheetCsvAll = q('.sle-sheet-csv-all')
  const sheetCsvShown = q('.sle-sheet-csv-shown')
  const sheetClose = q('.sle-sheet-close')
  const sheetChips = q('.sle-sheet-chips')
  const sheetClear = q('.sle-sheet-clear')
  const sheetHl = q('.sle-sheet-hl-box')
  const sheetCount = q('.sle-sheet-count')
  const sheetScroll = q('.sle-sheet-scroll')
  const sheetHeadRow = q('.sle-sheet-table thead')
  const sheetBodyRows = q('.sle-sheet-table tbody')
  const sheetEmpty = q('.sle-sheet-empty')
  const sheetCut = q('.sle-sheet-cut')
  const sheetNote = q('.sle-sheet-note')
  const sheetMenu = q('.sle-sheet-menu')
  const sheetMenuName = q('.sle-sheet-menu-name')
  const sheetMenuFind = q('.sle-sheet-menu-find')
  const sheetMenuList = q('.sle-sheet-menu-list')
  const sheetMenuRange = q('.sle-sheet-menu-range')
  const sheetMenuFrom = q('.sle-sheet-menu-from')
  const sheetMenuTo = q('.sle-sheet-menu-to')
  const sheetGrip = q('.sle-sheet-grip')
  const trayHits = q('.sle-tray-hits')
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

  // ---------------------------------------------------------------- 값 뒤 조사(순수 함수)
  // 파이썬 `services/korean_particle.py` 와 같은 표다 — 한글 음절은 종성, 숫자는 한국어로 읽은 끝 글자, `%` 는
  // 받침 없음, 고정 어휘의 영문 끝(층 이름의 F·DB·size·Capa·Kea)은 읽기 표, 그 밖의 영문 끝이 한 글자이거나 대문자
  // 두세 글자면 알파벳 이름(엘·엠·엔·알만 받침), 감싼 따옴표·괄호·굵게·백슬래시는 건너뛰고, 읽지 못하는 끝(그 밖의
  // 영문 낱말)은 `을(를)` 꼴이다.
  // `tests/test_particle_sites.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌려 파이썬과 대조한다. 한쪽을 고치면 다른 쪽도 고친다.
  // <josa>
  const JOSA_KNOWN_FINAL = { 0: 21, 1: 8, 2: 0, 3: 16, 4: 0, 5: 0, 6: 1, 7: 8, 8: 8, 9: 0, '%': 0 }
  const JOSA_LATIN_TAIL_FINAL = [['F', 0], ['DB', 0], ['size', 0], ['Capa', 0], ['Kea', 0]]
  // 알파벳 이름의 종성(엘·엠·엔·알만 받침이 있다)과 대문자 끝을 글자로 읽는 가장 긴 길이.
  const JOSA_LETTER_NAME_FINAL = { L: 8, M: 16, N: 4, R: 8 }
  const JOSA_SPELLED_CAPITALS = 3
  const JOSA_SKIPPED_TAIL = '"\'`)]」』*\\'
  // 조사 종류 → [받침 있을 때, 없을 때, 읽지 못할 때].
  const JOSA_FORMS = {
    을: ['을', '를', '을(를)'],
    은: ['은', '는', '은(는)'],
    이: ['이', '가', '이(가)'],
    으로: ['으로', '로', '(으)로'],
  }
  function josaFinal(word) {
    const chars = Array.from(String(word).trim())
    let end = chars.length
    while (end && (/\s/u.test(chars[end - 1]) || JOSA_SKIPPED_TAIL.includes(chars[end - 1]))) end -= 1
    if (!end) return null
    const char = chars[end - 1]
    const code = char.codePointAt(0)
    if (code >= 0xac00 && code <= 0xd7a3) return (code - 0xac00) % 28
    if (Object.prototype.hasOwnProperty.call(JOSA_KNOWN_FINAL, char)) return JOSA_KNOWN_FINAL[char]
    const head = chars.slice(0, end).join('')
    const known = JOSA_LATIN_TAIL_FINAL.find(([tail]) => head.endsWith(tail))
    if (known) return known[1]
    const letters = (head.match(/[A-Za-z]+$/) || [''])[0]
    if (!letters) return null
    if (letters.length === 1 || (letters.length <= JOSA_SPELLED_CAPITALS && letters === letters.toUpperCase())) {
      return JOSA_LETTER_NAME_FINAL[letters.slice(-1).toUpperCase()] || 0
    }
    return null
  }
  // `word` 와 그 끝소리에 맞는 `kind`(을·은·이·으로) 조사를 붙여 돌려준다. `으로` 는 받침이 없거나 ㄹ 이면 `로` 다.
  function withJosa(word, kind) {
    const text = String(word)
    const final = josaFinal(text)
    const [closed, open, unknown] = JOSA_FORMS[kind]
    if (final === null) return text + unknown
    if (kind === '으로') return text + (final === 0 || final === 8 ? open : closed)
    return text + (final ? closed : open)
  }
  // </josa>
  // 조사만 — 괄호처럼 낱말과 조사 사이에 다른 글이 설 때(「샘플1 (14×8)이」 — 괄호 뒤 조사는 괄호 앞 낱말에
  // 붙는다, 파이썬 `subject_particle` 꼴).
  const josaOf = (word, kind) => withJosa(word, kind).slice(String(word).length)

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

  // ---------------------------------------------------------------- 배율에 따른 글자 크기(순수 함수)
  // 도면에 붙은 글자(요소 이름표·글자 요소·층 블록 글·호기 이름표 상한·Main 설비명·베이 글)는 배율을 따라 커지고 작아진다
  // (2026-11-03 사용자 요청 — 전체 보기에서 글자가 도면보다 커 보였다). 화면 글자 px = 기준 크기 × s, s = 도면 1칸당 화면 px
  // (ppu)을 TEXT_REF_PPU 로 나눈 값이고 위는 TEXT_SCALE_MAX 배까지다. TEXT_MIN_PX 아래면 숨긴다(지금 글자 요소 자동의 6px) — 호기
  // 이름표·Main 설비명은 UNIT_LABEL_MIN_PX(7px) 아래에서 숨는다.
  // 표지(필요 단축 배지·견주기 꼬리표)는 s 를 CALLOUT_SCALE 범위로 묶고 크기로는 숨기지 않는다. 손잡이·초점 테·「!」 같은 UI
  // 표지와 선 굵기는 화면 px 그대로다. `tests/test_space_mark_look_js.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다.
  // <text-scale>
  const TEXT_REF_PPU = 8
  const TEXT_SCALE_MAX = 2
  const TEXT_MIN_PX = 6
  const CALLOUT_SCALE = [0.75, 1.25]
  // ppu(화면 px / 도면 1칸)에서 글자 배율 s. 재지 못한 값(0·숫자 아님)이면 1 이다.
  function textScale(ppu) {
    if (!(ppu > 0) || !Number.isFinite(ppu)) return 1
    return Math.min(ppu / TEXT_REF_PPU, TEXT_SCALE_MAX)
  }
  // 표지 배율 — s 를 CALLOUT_SCALE 안으로.
  function calloutScale(s) {
    return Math.min(Math.max(s, CALLOUT_SCALE[0]), CALLOUT_SCALE[1])
  }
  // 기준 크기 base(화면 px)의 글자가 배율 s 에서 서는가 — {px, shown}.
  function scaledText(base, s) {
    const px = base * s
    return { px, shown: px >= TEXT_MIN_PX }
  }
  // </text-scale>

  // ---------------------------------------------------------------- 동선·베이 화살표·도형 모양 값(순수 함수)
  // 요소 모양 값(look — 2026-11-03 사용자 요청)의 받는 키·처음 값은 파이썬 `services/floor_layout_mark.LOOK_KEYS`·
  // `LOOK_DEFAULTS` 와 같다(처음 값인 키는 빼고, 정규 글은 키 차례 JSON — node 시험이 파이썬과 대조한다). 머리 크기는 엑셀의
  // 3×3(「너비·길이」 두 글자, 각 S·M·L)이고 동선의 MM 이 지금 그림이다. 도형(shape)은 프리셋 키 look.shape 하나로 아홉 꼴을
  // 가르고 모양 조절 값 look.adj 의 처음 값은 프리셋마다 다르다(`SHAPE_PRESETS` — 파이썬 `SHAPE_ADJUST`). 그리기는 돌리기 전
  // 제자리 좌표(lw×lh, y 아래로)다. `tests/test_space_mark_look_js.py`·`tests/test_space_shape_js.py` 가 아래 두 표시 줄 사이를
  // 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <mark-look>
  const LOOK_KEYS = {
    arrow: ['head', 'line', 'lineWidth', 'lineStyle'],
    bay: ['head', 'line', 'lineWidth', 'lineStyle', 'flip'],
    shape: ['shape', 'adj', 'fillAlpha', 'line', 'lineWidth', 'lineStyle', 'flip'],
  }
  const LOOK_DEFAULTS = {
    arrow: { head: 'MM', line: 'accent', lineStyle: 'dashed' },
    bay: { head: 'MM', line: 'ink', lineWidth: 2, lineStyle: 'solid', flip: false },
    shape: { shape: 'rect', fillAlpha: 20, line: 'auto', lineWidth: 1.5, lineStyle: 'solid', flip: false },
  }
  const HEAD_SIZES = ['S', 'M', 'L']
  const ARROW_HEADS = HEAD_SIZES.flatMap((w) => HEAD_SIZES.map((l) => w + l))
  const LINE_COLORS = ['accent', 'ink', 'blue', 'rose', 'green', 'violet', 'sky', 'gray']
  const LINE_WIDTHS = [0.75, 1, 1.5, 2, 3, 4.5, 6]
  const LINE_STYLES = ['solid', 'dashed', 'dotted']
  // 도형 프리셋 아홉(2026-11-03 사용자 요청 — 엑셀 도형처럼). adj 는 모양 조절 값마다 [하한, 상한, 처음 값](0.01 단위 비율 —
  // 파이썬 `SHAPE_ADJUST`), base 는 그 값이 무엇의 비율인가(파이썬 `SHAPE_ADJUST_BASE`), words 는 그 값의 이름(선택 칸·손잡이
  // 풍선), size 는 넣을 때의 크기, turn 은 돌리기·뒤집기에 뜻이 있는 꼴인가(대칭 꼴은 그 단추가 숨는다). 두께·둥글기·머리 길이는
  // 엑셀처럼 **짧은 변**(min(폭, 높이)) 기준이다(2026-11-04 Space 결정 보드 답 — 한쪽 팔만 늘이기) — base 'min' 은 상한이 그대로,
  // 'min-w'·'min-h' 는 상한이 그 축(폭·높이) 길이까지다(엑셀처럼 — 넓은 ㄴ자의 굵은 세로 팔 · 긴 블록 화살표의 긴 머리. 저장 상한은
  // 상한 × `SHAPE_STRETCH_MAX`, 그릴 때 상자의 상한으로 묶는다 — `fitAdj`). 손잡이·칸으로 비율 없이 크기를 바꾸면 그린 두께를 지킨다
  // (`resizedAdj` — 짧은 쪽 팔을 늘여도 두 팔 두께 그대로). 'w' 는 폭(삼각형 꼭짓점 자리), 'h' 는 높이(블록 화살표 몸통 — 머리
  // 너비에 대한 두께) 기준이다.
  const SHAPE_PRESETS = {
    rect: { name: '사각형', size: [8, 6], adj: [[0, 1, 0]], base: ['min'], words: ['모서리 둥글기'], turn: false },
    ellipse: { name: '원', size: [6, 6], adj: [], base: [], words: [], turn: false },
    lbox: { name: 'ㄴ자 박스', size: [8, 8], adj: [[0.05, 0.95, 0.35], [0.05, 0.95, 0.35]], base: ['min-w', 'min-h'], words: ['세로 팔 두께', '가로 팔 두께'], turn: true },
    cbox: { name: 'ㄷ자 박스', size: [8, 8], adj: [[0.05, 0.95, 0.3], [0.05, 0.49, 0.3]], base: ['min-w', 'min-h'], words: ['등 두께', '팔 두께'], turn: true },
    frame: { name: '테', size: [10, 8], adj: [[0.02, 0.49, 0.12]], base: ['min'], words: ['테 두께'], turn: false },
    triangle: { name: '삼각형', size: [8, 7], adj: [[0, 1, 0.5]], base: ['w'], words: ['꼭짓점 자리'], turn: true },
    diamond: { name: '마름모', size: [8, 8], adj: [], base: [], words: [], turn: false },
    cross: { name: '십자', size: [8, 8], adj: [[0.05, 0.95, 0.34]], base: ['min'], words: ['팔 두께'], turn: false },
    arrowblock: { name: '블록 화살표', size: [10, 5], adj: [[0.05, 1, 0.5], [0.05, 0.95, 0.7]], base: ['h', 'min-w'], words: ['몸통 두께', '머리 길이'], turn: true },
  }
  const SHAPE_KEYS = Object.keys(SHAPE_PRESETS)
  // 'min-w'·'min-h' 모양 조절 값의 저장 상한 배수 — 상한 × 100(긴 변이 짧은 변의 100배인 상자의 축 길이)까지 받는다(파이썬
  // `SHAPE_STRETCH_MAX`). 그릴 때는 그 상자의 상한(`adjCap`)으로 묶는다.
  const SHAPE_STRETCH_MAX = 100
  // 프리셋 preset 의 모양 조절 값 k 가 상한이 축 길이까지 느는 값('min-w'·'min-h')인가.
  function adjStretches(preset, k) {
    const base = (SHAPE_PRESETS[presetOf(preset)].base || [])[k]
    return base === 'min-w' || base === 'min-h'
  }
  // 도형 채우기 색(요소 color — 영역 색 여섯 + ink 진하게 + surface 바탕)과 선 색(auto 채우기 색을 따름 · none 선 없음 · ink · 영역 색
  // 여섯). 파이썬 `SHAPE_FILL_KEYS`·`SHAPE_LINE_KEYS`.
  const SHAPE_FILLS = ['blue', 'rose', 'green', 'violet', 'sky', 'gray', 'ink', 'surface']
  const SHAPE_LINES = ['auto', 'none', 'ink', 'blue', 'rose', 'green', 'violet', 'sky', 'gray']
  const FILL_ALPHA_STEP = 5
  // 머리 너비·길이(동선 × 상자 높이 lh · 베이 × 팔 사이 lh/2)와 동선 머리 길이의 상한(× 상자 폭 lw).
  const HEAD_W = { S: 0.45, M: 0.7, L: 1.0 }
  const HEAD_L = { S: 0.7, M: 1.1, L: 1.6 }
  const HEAD_CAP = { S: 0.25, M: 0.35, L: 0.45 }
  const BAY_NUMBER_MAX = 10
  // 모양 값 하나가 그 종류(kind)의 그 키의 값인가. 도형의 선 색은 auto·none 이 있고 강조색이 없다.
  function lookAllowed(key, value, kind) {
    if (key === 'head') return ARROW_HEADS.includes(value)
    if (key === 'line') return (kind === 'shape' ? SHAPE_LINES : LINE_COLORS).includes(value)
    if (key === 'lineWidth') return typeof value === 'number' && LINE_WIDTHS.includes(value)
    if (key === 'lineStyle') return LINE_STYLES.includes(value)
    if (key === 'flip') return typeof value === 'boolean'
    if (key === 'shape') return SHAPE_KEYS.includes(value)
    if (key === 'fillAlpha') return Number.isInteger(value) && value >= 0 && value <= 100 && value % FILL_ALPHA_STEP === 0
    return false
  }
  // 도형 프리셋 키 — 모르는 값이면 사각형.
  function presetOf(value) {
    return SHAPE_KEYS.includes(value) ? value : 'rect'
  }
  // 도형 모양 조절 값 — 프리셋 preset 의 개수·저장 범위(하한 ~ 상한, 'min-w'·'min-h' 는 상한 × `SHAPE_STRETCH_MAX`) 안의 숫자
  // 목록이면 0.01 단위로 맞춘 것, 아니면 null.
  function adjOf(raw, preset) {
    const spec = SHAPE_PRESETS[presetOf(preset)].adj
    if (!Array.isArray(raw) || raw.length !== spec.length) return null
    const out = []
    for (let k = 0; k < spec.length; k += 1) {
      const value = raw[k]
      if (typeof value !== 'number' || !Number.isFinite(value)) return null
      const rounded = Math.round(value * 100) / 100
      const top = spec[k][1] * (adjStretches(preset, k) ? SHAPE_STRETCH_MAX : 1)
      if (rounded < spec[k][0] - 1e-9 || rounded > top + 1e-9) return null
      out.push(rounded)
    }
    return out
  }
  // 받은 모양 값을 그 종류의 정규 꼴로 — 받는 키의 맞는 값 가운데 처음 값이 아닌 것만 남긴다(모르는 키·틀린 값은 뺀다 —
  // 파이썬은 거부하지만 편집기는 그릴 수 있는 것만 쥔다). 모양 값이 없는 종류는 빈 값이다. 도형의 모양 조절 값은 프리셋(없으면
  // 사각형)의 개수·범위에 맞을 때만, 그 프리셋의 처음 값과 모두 같으면 뺀다.
  function cleanLook(raw, kind) {
    const keys = LOOK_KEYS[kind]
    const out = {}
    if (!keys || !raw || typeof raw !== 'object' || Array.isArray(raw)) return out
    const defaults = LOOK_DEFAULTS[kind]
    const preset = presetOf(raw.shape)
    for (const key of keys) {
      const value = raw[key]
      if (value === undefined || value === null) continue
      if (key === 'adj') {
        const adj = adjOf(value, preset)
        if (adj && adj.some((v, k) => Math.abs(v - SHAPE_PRESETS[preset].adj[k][2]) > 1e-9)) out.adj = adj
        continue
      }
      if (!lookAllowed(key, value, kind)) continue
      if (key in defaults && defaults[key] === value) continue
      out[key] = value
    }
    return out
  }
  // 모양 값 고치기 — patch 의 null 은 그 키를 처음 값으로(뺌), 나머지는 덮어쓴다. 결과는 `cleanLook` 을 거친 새 객체다
  // (도형 바꾸기 `{ shape, adj: null }` 는 프리셋만 바꾸고 모양 조절은 새 프리셋의 처음 값 — 채우기·선·뒤집기는 그대로).
  function patchLook(look, patch, kind) {
    const merged = { ...(look || {}) }
    for (const [key, value] of Object.entries(patch || {})) {
      if (value === null) delete merged[key]
      else merged[key] = value
    }
    return cleanLook(merged, kind)
  }
  // 그릴 도형 프리셋과 모양 조절 값(고른 값, 없으면 그 프리셋의 처음 값).
  function shapeOf(look) {
    return presetOf(look ? look.shape : undefined)
  }
  function shapeAdj(look) {
    const preset = shapeOf(look)
    return adjOf(look ? look.adj : undefined, preset) || SHAPE_PRESETS[preset].adj.map((spec) => spec[2])
  }
  // 도형 채우기 색 키 — 모르는 값이면 파랑(파이썬 `shape_fill` 의 처음 값).
  function shapeFillOf(color) {
    return SHAPE_FILLS.includes(color) ? color : 'blue'
  }
  // 정규 글(키 차례 JSON) — 바뀜 판정·견주기에 쓴다. 파이썬 `json.dumps(sort_keys=True, separators=(",", ":"))` 와 같다.
  function lookText(look) {
    const keys = Object.keys(look || {}).sort()
    return keys.length ? JSON.stringify(Object.fromEntries(keys.map((key) => [key, look[key]]))) : ''
  }
  // 그릴 값 — 고른 값, 없으면 처음 값(처음 값이 없는 키는 undefined).
  function lookValue(look, kind, key) {
    const value = look ? look[key] : undefined
    if (value !== undefined) return value
    return (LOOK_DEFAULTS[kind] || {})[key]
  }
  // 머리 크기 두 글자 → {w, l}. 틀린 값은 MM.
  function headParts(head) {
    const text = ARROW_HEADS.includes(head) ? head : 'MM'
    return { w: text[0], l: text[1] }
  }
  // 동선(곧은 화살표, 0° 는 왼쪽 → 오른쪽) — 몸통 선 {x1, y1, x2, y2}, 머리 세 점, 머리 길이 hl. MM 이 지금 그림이다(머리 길이
  // min(lh × 1.1, lw × 0.35), 머리 y = lh × 0.15 … lh × 0.85, 몸통 끝 = lw − 머리 길이 × 0.9).
  function arrowShape(lw, lh, head) {
    const { w, l } = headParts(head)
    const hw = HEAD_W[w] * lh
    const hl = Math.min(HEAD_L[l] * lh, HEAD_CAP[l] * lw)
    return {
      shaft: { x1: lh * 0.3, y1: lh / 2, x2: lw - hl * 0.9, y2: lh / 2 },
      head: [[lw - hl, lh / 2 - hw / 2], [lw, lh / 2], [lw - hl, lh / 2 + hw / 2]],
      hl,
    }
  }
  // 베이(U자, 0° = ⊃ — 굽은 곳 오른쪽, 두 팔이 왼쪽으로 열림). 팔은 y = lh/4 · 3lh/4, 굽은 곳 반지름 rx = min(lh/4, lw/2)·ry = lh/4,
  // 머리는 아래 팔 왼쪽 끝에서 왼쪽을 향한다 — 너비 HEAD_W × lh/2, 길이 min(HEAD_L × lh/2, (lw − rx) × 0.45). 선 경로 d, 머리 세 점,
  // 가운데 글 자리(두 팔 사이 — 머리를 비킨 틈의 가운데)와 틈의 폭·높이(gapW·gapH)를 낸다.
  function bayShape(lw, lh, head) {
    const { w, l } = headParts(head)
    const rx = Math.min(lh / 4, lw / 2)
    const ry = lh / 4
    const top = lh / 4
    const bottom = (3 * lh) / 4
    const bend = lw - rx
    const hw = HEAD_W[w] * (lh / 2)
    const hl = Math.max(0, Math.min(HEAD_L[l] * (lh / 2), bend * 0.45))
    return {
      d: `M 0 ${top} H ${bend} A ${rx} ${ry} 0 0 1 ${bend} ${bottom} H ${hl}`,
      head: [[hl, bottom - hw / 2], [0, bottom], [hl, bottom + hw / 2]],
      text: { x: (hl + bend) / 2, y: lh / 2 },
      gapW: Math.max(0, bend - hl),
      gapH: lh / 2,
      hl,
    }
  }
  // 제자리 좌표의 점 (x, y) 가 화면(SVG — y 아래로)에서 상자 가운데로부터 어디인가 — 좌우 뒤집기(flip, 가운데 축)를 먼저, 그다음
  // 가운데를 축으로 rot° 돌림. 그리는 쪽의 `translate(c) rotate(rot) scale(flip) translate(−l/2)` 과 같다.
  function placeLocal(x, y, lw, lh, rot, flip) {
    let dx = x - lw / 2
    const dy = y - lh / 2
    if (flip) dx = -dx
    const r = (((rot || 0) % 360) + 360) % 360
    if (r === 90) return { x: -dy, y: dx }
    if (r === 180) return { x: -dx, y: -dy }
    if (r === 270) return { x: dy, y: -dx }
    return { x: dx, y: dy }
  }
  // 베이 가운데 글 자동 크기(도면 단위) — 틈에 맞춘다. 0°·180° 는 틈이 화면에서 가로, 90°·270° 는 세로로 선다(글자는 늘 가로).
  function bayAutoSize(shape, rot, em) {
    const width = Math.max(em, 1)
    if ((rot || 0) % 180) return Math.min(shape.gapW * 0.75, (shape.gapH * 0.9) / width)
    return Math.min(shape.gapH * 0.75, (shape.gapW * 0.9) / width)
  }
  // 베이 번호 — 앞의 B·b 와 그 뒤 빈칸을 모두 떼고(「BB80」 도 「80」 — 다시 거쳐도 같은 값) BAY_NUMBER_MAX 자까지(파이썬
  // `bay_label` 과 같다 — 넘으면 파이썬은 거부, 편집기는 자른다).
  function bayNumber(text) {
    return String(text ?? '').trim().replace(/^(?:[Bb]\s*)+/, '').slice(0, BAY_NUMBER_MAX)
  }
  // 선 모양 → 점선 무늬(화면 px 굵기 w 기준). 실선은 빈 글.
  function lineDash(style, w) {
    if (style === 'dashed') return `${w * 3} ${w * 2}`
    if (style === 'dotted') return `0.01 ${w * 2}`
    return ''
  }
  // </mark-look>

  // ---------------------------------------------------------------- 도형 경로·모양 조절 손잡이(순수 함수)
  // 도형 아홉 프리셋의 그리기 경로(돌리기 전 제자리 lw×lh, y 아래로)와 노란 모양 조절 손잡이(엑셀처럼 — 2026-11-03 사용자 요청)의
  // 자리·값 되돌림, Shift 모서리 끌기의 가로세로 비율 유지다. 손잡이 자리 → 값(`handleValue`)은 자리(`shapeHandles`)의 거꾸로라
  // 손잡이를 놓은 자리에서 같은 값이 나온다(돌림·뒤집기는 `placeLocal`·`unplaceLocal` 로 오간다). `tests/test_space_shape_js.py`
  // 가 `// <mark-look>` 과 함께 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <shape-geometry>
  const shapeNum = (v) => Math.round(v * 1e4) / 1e4 + 0
  const polyPath = (pts) => `M ${pts.map(([x, y]) => `${shapeNum(x)} ${shapeNum(y)}`).join(' L ')} Z`
  // 프리셋 key 의 모양 조절 값 k 가 이 상자(lw×lh)에서 가질 수 있는 상한 — 'min-w'·'min-h' 는 그 축 길이까지(상한 × 축 ÷ 짧은 변,
  // 저장 상한 안 — ㄴ자 세로 팔은 폭의 0.95 까지), 나머지는 프리셋 상한이다. 늘 프리셋 상한 이상이다.
  function adjCap(key, k, lw, lh) {
    const preset = SHAPE_PRESETS[key]
    const spec = preset ? preset.adj[k] : null
    if (!spec) return 0
    const base = (preset.base || [])[k]
    const least = Math.min(lw, lh)
    if ((base !== 'min-w' && base !== 'min-h') || !(least > 0)) return spec[1]
    return Math.min((spec[1] * (base === 'min-w' ? lw : lh)) / least, spec[1] * SHAPE_STRETCH_MAX)
  }
  // `adjCap` 을 0.01 단위로 내림(손잡이·칸이 쓰는 값이 상한을 넘지 않게).
  const adjTop = (key, k, lw, lh) => Math.floor(adjCap(key, k, lw, lh) * 100 + 1e-9) / 100
  // 그릴 모양 조절 값 — 값마다 하한 ~ 이 상자의 상한으로 묶는다(엑셀처럼 저장 값은 그대로 두고 그릴 때만 — 칸으로 상자를 좁혀
  // 상한이 줄어도 늘 상자 안이다). 빠지거나 틀린 값은 처음 값이다.
  function fitAdj(key, adj, lw, lh) {
    const spec = (SHAPE_PRESETS[key] || {}).adj || []
    const raw = Array.isArray(adj) ? adj : []
    return spec.map((s, k) => {
      const value = typeof raw[k] === 'number' && Number.isFinite(raw[k]) ? raw[k] : s[2]
      return Math.min(Math.max(value, s[0]), adjCap(key, k, lw, lh))
    })
  }
  // 프리셋 key 의 경로 {d, rule, pts} — rule 은 채우기 규칙(테만 evenodd — 가운데가 빈다), pts 는 꼭짓점·호 끝점(시험이 상자 안인지
  // 본다). 두께·자리는 모양 조절 값 adj(`fitAdj` 로 묶은 것)에서 낸다(min = min(lw, lh) — 짧은 변) — 사각형 모서리 반지름
  // r = a·min/2, ㄴ자 세로 팔 a1·min·가로 팔 a2·min, ㄷ자 등 a1·min·위아래 팔 a2·min, 테 a·min, 삼각형 꼭짓점 x = a·lw, 십자 팔
  // a·min, 블록 화살표 몸통 a1·lh·머리 길이 a2·min. 상한(`adjCap` — 짧은 변 또는 그 축의 0.95 · 0.49)으로 묶어 늘 상자 안이다.
  function shapePath(key, lw, lh, adj) {
    const a = fitAdj(key, adj, lw, lh)
    const least = Math.min(lw, lh)
    if (key === 'ellipse') {
      const rx = lw / 2
      const ry = lh / 2
      return {
        d: `M 0 ${shapeNum(ry)} A ${shapeNum(rx)} ${shapeNum(ry)} 0 1 0 ${shapeNum(lw)} ${shapeNum(ry)} A ${shapeNum(rx)} ${shapeNum(ry)} 0 1 0 0 ${shapeNum(ry)} Z`,
        rule: 'nonzero',
        pts: [[0, ry], [lw, ry], [rx, 0], [rx, lh]],
      }
    }
    if (key === 'lbox') {
      const t1 = a[0] * least
      const t2 = a[1] * least
      const pts = [[0, 0], [t1, 0], [t1, lh - t2], [lw, lh - t2], [lw, lh], [0, lh]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    if (key === 'cbox') {
      const t1 = a[0] * least
      const t2 = a[1] * least
      const pts = [[0, 0], [lw, 0], [lw, t2], [t1, t2], [t1, lh - t2], [lw, lh - t2], [lw, lh], [0, lh]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    if (key === 'frame') {
      const t = a[0] * least
      const outer = [[0, 0], [lw, 0], [lw, lh], [0, lh]]
      const inner = [[t, t], [t, lh - t], [lw - t, lh - t], [lw - t, t]]
      return { d: `${polyPath(outer)} ${polyPath(inner)}`, rule: 'evenodd', pts: [...outer, ...inner] }
    }
    if (key === 'triangle') {
      const pts = [[a[0] * lw, 0], [lw, lh], [0, lh]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    if (key === 'diamond') {
      const pts = [[lw / 2, 0], [lw, lh / 2], [lw / 2, lh], [0, lh / 2]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    if (key === 'cross') {
      const t = a[0] * least
      const x0 = (lw - t) / 2
      const x1 = (lw + t) / 2
      const y0 = (lh - t) / 2
      const y1 = (lh + t) / 2
      const pts = [[x0, 0], [x1, 0], [x1, y0], [lw, y0], [lw, y1], [x1, y1], [x1, lh], [x0, lh], [x0, y1], [0, y1], [0, y0], [x0, y0]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    if (key === 'arrowblock') {
      const body = a[0] * lh
      const hl = a[1] * least
      const pts = [[0, (lh - body) / 2], [lw - hl, (lh - body) / 2], [lw - hl, 0], [lw, lh / 2], [lw - hl, lh], [lw - hl, (lh + body) / 2], [0, (lh + body) / 2]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    // 사각형(처음 값·모르는 키) — 둥글기가 있으면 네 귀를 반지름 r 의 호로.
    const r = Math.max(0, Math.min((a[0] || 0) * least / 2, least / 2))
    if (r <= 1e-9) {
      const pts = [[0, 0], [lw, 0], [lw, lh], [0, lh]]
      return { d: polyPath(pts), rule: 'nonzero', pts }
    }
    const n = shapeNum
    const arc = (x, y) => `A ${n(r)} ${n(r)} 0 0 1 ${n(x)} ${n(y)}`
    return {
      d: `M ${n(r)} 0 H ${n(lw - r)} ${arc(lw, r)} V ${n(lh - r)} ${arc(lw - r, lh)} H ${n(r)} ${arc(0, lh - r)} V ${n(r)} ${arc(r, 0)} Z`,
      rule: 'nonzero',
      pts: [[r, 0], [lw - r, 0], [lw, r], [lw, lh - r], [lw - r, lh], [r, lh], [0, lh - r], [0, r]],
      r,
    }
  }
  // 프리셋 key 의 노란 손잡이 [{x, y, axis, index}](제자리 좌표). axis 는 손잡이가 값을 읽는 축('x' 가로 · 'y' 세로).
  function shapeHandles(key, lw, lh, adj) {
    const a = fitAdj(key, adj, lw, lh)
    const least = Math.min(lw, lh)
    if (key === 'rect') return [{ x: (a[0] || 0) * least / 2, y: 0, axis: 'x', index: 0 }]
    if (key === 'lbox') return [{ x: a[0] * least, y: 0, axis: 'x', index: 0 }, { x: lw, y: lh - a[1] * least, axis: 'y', index: 1 }]
    if (key === 'cbox') return [{ x: a[0] * least, y: lh / 2, axis: 'x', index: 0 }, { x: lw, y: a[1] * least, axis: 'y', index: 1 }]
    if (key === 'frame') return [{ x: a[0] * least, y: a[0] * least, axis: 'y', index: 0 }]
    if (key === 'triangle') return [{ x: a[0] * lw, y: 0, axis: 'x', index: 0 }]
    if (key === 'cross') {
      const t = a[0] * least
      return [{ x: (lw + t) / 2, y: (lh - t) / 4, axis: 'x', index: 0 }]
    }
    if (key === 'arrowblock') {
      const body = a[0] * lh
      const hl = a[1] * least
      return [{ x: (lw - hl) / 2, y: (lh - body) / 2, axis: 'y', index: 0 }, { x: lw - hl, y: 0, axis: 'x', index: 1 }]
    }
    return []
  }
  // 손잡이 index 를 제자리 점 (x, y) 에 놓았을 때의 모양 조절 값 — 그 축만 읽어 하한 ~ 이 상자의 상한(`adjTop`)으로 묶고 0.01
  // 단위로 맞춘다. 손잡이가 없는 프리셋·번호면 null.
  function handleValue(key, index, x, y, lw, lh) {
    const spec = (SHAPE_PRESETS[key] || {}).adj || []
    if (!spec[index]) return null
    const least = Math.min(lw, lh)
    const ratio = (num, den) => (den > 0 ? num / den : spec[index][2])
    let v = spec[index][2]
    if (key === 'rect') v = ratio(x, least / 2)
    else if (key === 'lbox') v = index === 0 ? ratio(x, least) : ratio(lh - y, least)
    else if (key === 'cbox') v = index === 0 ? ratio(x, least) : ratio(y, least)
    else if (key === 'frame') v = ratio(y, least)
    else if (key === 'triangle') v = ratio(x, lw)
    else if (key === 'cross') v = ratio(2 * x - lw, least)
    else if (key === 'arrowblock') v = index === 0 ? ratio(lh - 2 * y, lh) : ratio(lw - x, least)
    if (!Number.isFinite(v)) v = spec[index][2]
    return Math.min(Math.max(Math.round(v * 100) / 100, spec[index][0]), adjTop(key, index, lw, lh))
  }
  // 비율 없이 크기를 바꾼 도형(제자리 lw0×lh0 → lw1×lh1)의 모양 조절 값 — 짧은 변 기준 값('min'·'min-w'·'min-h')은 그린 두께
  // (옛 상자에서 묶은 값 × 옛 짧은 변)를 새 짧은 변으로 다시 나눠 지킨다(하한 ~ 새 상자 상한, 0.01 단위). 그래서 짧은 쪽 팔을
  // 늘여도 두 팔 두께 · 둥글기 · 머리 길이가 그대로다(2026-11-04 Space 결정 보드 답 — 그 팔 길이만 늘이기). 짧은 변이 그대로면
  // 받은 값 그대로(같은 배열)이고, 폭·높이 기준 값('w'·'h')은 비율이라 그대로다.
  function resizedAdj(key, adj, lw0, lh0, lw1, lh1) {
    const preset = SHAPE_PRESETS[key]
    const before = Math.min(lw0, lh0)
    const after = Math.min(lw1, lh1)
    if (!preset || !Array.isArray(adj) || !(before > 0) || !(after > 0) || Math.abs(before - after) < 1e-9) return adj
    const drawn = fitAdj(key, adj, lw0, lh0)
    return adj.map((value, k) => {
      const base = (preset.base || [])[k]
      if (base !== 'min' && base !== 'min-w' && base !== 'min-h') return value
      const kept = Math.round(((drawn[k] * before) / after) * 100) / 100
      return Math.min(Math.max(kept, preset.adj[k][0]), adjTop(key, k, lw1, lh1))
    })
  }
  // 화면(SVG — y 아래로)에서 상자 가운데로부터의 자리 (px, py) 를 제자리 좌표로 — `placeLocal` 의 거꾸로(돌림을 풀고 좌우 뒤집기를
  // 푼다).
  function unplaceLocal(px, py, lw, lh, rot, flip) {
    const r = (((rot || 0) % 360) + 360) % 360
    let dx = px
    let dy = py
    if (r === 90) { dx = py; dy = -px }
    else if (r === 180) { dx = -px; dy = -py }
    else if (r === 270) { dx = -py; dy = px }
    if (flip) dx = -dx
    return { x: dx + lw / 2, y: dy + lh / 2 }
  }
  // Shift 를 누른 채 모서리 손잡이로 키운 상자 — 처음 상자 b(데이터 좌표 {x, y, w, h}, Y 위로)의 가로세로 비율을 지키고 끈
  // 모서리의 맞은편 귀를 붙박는다. 배율은 손이 더 많이 움직인 축(1 에서 더 먼 쪽)을 따르고, 영역(maxW×maxH)을 넘지 않게·가장 짧은
  // 변이 minS 아래로 줄지 않게 묶은 뒤 눈금(scale)에 맞춘다. r 은 비율 없이 끈 상자(`resizedBox`), dir 은 모서리(nw·ne·sw·se).
  function keepAspect(b, r, dir, maxW, maxH, minS, scale) {
    const east = dir.includes('e')
    const north = dir.includes('n')
    const ax = east ? b.x : b.x + b.w
    const ay = north ? b.y : b.y + b.h
    const kw = r.w / b.w
    const kh = r.h / b.h
    let k = Math.abs(kw - 1) >= Math.abs(kh - 1) ? kw : kh
    k = Math.min(k, (east ? maxW - ax : ax) / b.w, (north ? maxH - ay : ay) / b.h)
    k = Math.max(k, minS / Math.min(b.w, b.h))
    const tick = (v) => Math.round(v * scale) / scale + 0
    const w = tick(b.w * k)
    const h = tick(b.h * k)
    return { x: tick(east ? ax : ax - w), y: tick(north ? ay : ay - h), w, h }
  }
  // 노란 손잡이 그릴 자리 — 크기 손잡이(centers [{x, y}])와 gap 보다 가까우면 값을 읽는 축(axis 'x'·'y')을 따라 gap 만큼 비킨다. 두
  // 쪽 가운데 크기 손잡이에서 더 먼 쪽(같으면 상자 가운데 center 쪽)이다. 가깝지 않으면 그 자리 그대로. 끌 때는 잡은 자리에서 손이
  // 움직인 만큼으로 값을 읽어(`drag.grab`) 비켜 그려도 값이 튀지 않는다 — 둥글기 0 인 사각형의 손잡이가 모서리 손잡이를 덮지 않게.
  function nudgeHandle(pt, axis, centers, gap, center) {
    const far = (q) => Math.min(...centers.map((c) => Math.hypot(c.x - q.x, c.y - q.y)))
    if (!centers.length || far(pt) >= gap) return pt
    const step = (sign) => (axis === 'x' ? { x: pt.x + sign * gap, y: pt.y } : { x: pt.x, y: pt.y + sign * gap })
    const inward = (axis === 'x' ? center.x - pt.x : center.y - pt.y) >= 0 ? 1 : -1
    const near = step(inward)
    const away = step(-inward)
    return far(away) > far(near) + 1e-9 ? away : near
  }
  // </shape-geometry>

  // ---------------------------------------------------------------- 서식 복사·붙여넣기(순수 함수)
  // 엑셀 서식 붓처럼 고른 것 하나의 서식을 담아 다른 것에 붙인다(2026-11-03 사용자 요청). 서식은 세 묶음(「붙일 것」 체크)이다 —
  // 크기(같은 종류끼리만: 요소는 같은 kind, 호기는 낱 호기끼리·Main 설비 모듈 묶음끼리 — 묶음은 범위 크기. 크기는 상자 자기 방향의
  // 길이·두께라 돌린 요소에는 돌린 대로 붙는다), 색·선(면 색은 영역·도형·층 블록 사이 — 받는 쪽에 없는 값은 그 칸만 건너뛴다,
  // 채우기 투명도는 도형끼리, 선 색·굵기·모양은 도형·동선·베이 사이, 영역 테두리 모양 ↔ 선 모양, 머리 크기는 동선·베이 사이,
  // 빗금은 영역·도형 사이), 글자(크기·색은 모든 도면 요소, 이름표 정렬은 영역끼리). 자리·이름표 글·회전·뒤집기·도형 꼴·모양 조절
  // 값·설비 금지·연결 층은 넣지 않는다(엑셀 붓도 꼴·회전은 옮기지 않는다). 호기의 면 색은 계산 값이라 호기에는 크기만 붙는다.
  // 담는 값은 그 종류가 지금 그리는 값(처음 값 포함)이다. `tests/test_space_format_paint_js.py` 가 `// <mark-look>` 과 함께
  // 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <format-paint>
  const FORMAT_PARTS = ['size', 'paint', 'text']
  // 영역 색 키(파이썬 `MARK_COLOR_KEYS` — 글자 색 키도 같다), 영역 테두리 모양·이름표 정렬(`ZONE_BORDER_STYLES`·`ZONE_LABEL_ALIGNS`).
  const FORMAT_COLORS = ['blue', 'rose', 'green', 'violet', 'sky', 'gray']
  const FORMAT_BORDERS = ['dashed', 'solid']
  const FORMAT_ALIGNS = ['left', 'center', 'right']
  const FORMAT_LINED = ['arrow', 'bay', 'shape']
  const FORMAT_HEADED = ['arrow', 'bay']
  const FORMAT_HATCHED = ['zone', 'shape']
  // 그 종류가 면 색으로 받는 값 — 영역은 색 여섯, 도형은 채우기 여덟(진하게·바탕 포함), 층 블록은 빈 값(Space 기본 면) + 여섯. 그 밖의
  // 종류는 면 색이 없다(null).
  function formatColors(kind) {
    if (kind === 'zone') return FORMAT_COLORS
    if (kind === 'shape') return SHAPE_FILLS
    if (kind === 'block') return ['', ...FORMAT_COLORS]
    return null
  }
  // 90°·270° 로 돌린 상자인가(폭·높이가 자기 방향의 두께·길이와 바뀐다).
  function formatTurned(rot) {
    return Boolean(((((Number(rot) || 0) % 180) + 180) % 180))
  }
  // 서식 — item 은 {kind, module(호기만 — Main 설비 모듈 묶음인가), w, h(묶음은 범위), rot, color, hatch, fontSize, fontColor,
  // borderStyle, labelAlign, look}. {kind, module, size: {w, h}(자기 방향, 크기가 없으면 null), paint: {color?, fillAlpha?, line?,
  // lineWidth?(동선 자동은 null), lineStyle?(영역은 테두리 모양), head?, hatch?} | null, text: {fontSize, fontColor, labelAlign?} | null}.
  // 호기는 paint·text 가 null 이다.
  function formatOf(item) {
    const kind = String(item.kind)
    const unit = kind === 'unit'
    const sized = Number.isFinite(item.w) && item.w > 0 && Number.isFinite(item.h) && item.h > 0
    const turned = !unit && formatTurned(item.rot)
    const fmt = {
      kind,
      module: unit && Boolean(item.module),
      size: sized ? { w: turned ? item.h : item.w, h: turned ? item.w : item.h } : null,
      paint: null,
      text: null,
    }
    if (unit) return fmt
    const paint = {}
    if (formatColors(kind)) paint.color = String(item.color || '')
    if (kind === 'shape') paint.fillAlpha = lookValue(item.look, kind, 'fillAlpha')
    if (FORMAT_LINED.includes(kind)) {
      paint.line = lookValue(item.look, kind, 'line')
      const width = lookValue(item.look, kind, 'lineWidth')
      paint.lineWidth = width === undefined ? null : width
      paint.lineStyle = lookValue(item.look, kind, 'lineStyle')
    }
    if (kind === 'zone') paint.lineStyle = FORMAT_BORDERS.includes(item.borderStyle) ? item.borderStyle : FORMAT_BORDERS[0]
    if (FORMAT_HEADED.includes(kind)) paint.head = lookValue(item.look, kind, 'head')
    if (FORMAT_HATCHED.includes(kind)) paint.hatch = Boolean(item.hatch)
    fmt.paint = paint
    fmt.text = { fontSize: item.fontSize ?? null, fontColor: String(item.fontColor || '') }
    if (kind === 'zone') fmt.text.labelAlign = FORMAT_ALIGNS.includes(item.labelAlign) ? item.labelAlign : FORMAT_ALIGNS[0]
    return fmt
  }
  // 받는 쪽 target(formatOf 와 같은 꼴)에 서식 fmt 의 켠 묶음(parts {size, paint, text} — 없거나 거짓이 아니면 켬)을 붙일 값 —
  // {size: {w, h}(받는 쪽 방향) | null, fields: {요소 칸}, look: {모양 값 — null 은 처음 값으로}}. 받는 쪽이 갖지 않는 칸·값은
  // 빠진다. 붙일 것이 하나도 없으면 null.
  function formatPatch(target, fmt, parts) {
    const kind = String(target.kind)
    const on = (part) => !parts || parts[part] !== false
    const out = { size: null, fields: {}, look: {} }
    const sameKind = fmt.kind === kind && (kind !== 'unit' || Boolean(fmt.module) === Boolean(target.module))
    if (on('size') && fmt.size && sameKind) {
      const turned = kind !== 'unit' && formatTurned(target.rot)
      out.size = { w: turned ? fmt.size.h : fmt.size.w, h: turned ? fmt.size.w : fmt.size.h }
    }
    const p = fmt.paint
    if (kind !== 'unit' && p && on('paint')) {
      const colors = formatColors(kind)
      if (colors && typeof p.color === 'string' && colors.includes(p.color)) out.fields.color = p.color
      if (kind === 'shape' && lookAllowed('fillAlpha', p.fillAlpha, kind)) out.look.fillAlpha = p.fillAlpha
      if (FORMAT_LINED.includes(kind)) {
        if (lookAllowed('line', p.line, kind)) out.look.line = p.line
        // 동선의 자동 굵기(상자 높이를 따름)는 동선에만 있다 — 도형·베이는 그 칸을 건너뛴다.
        if (p.lineWidth === null && kind === 'arrow') out.look.lineWidth = null
        else if (lookAllowed('lineWidth', p.lineWidth, kind)) out.look.lineWidth = p.lineWidth
        if (lookAllowed('lineStyle', p.lineStyle, kind)) out.look.lineStyle = p.lineStyle
      }
      if (kind === 'zone' && FORMAT_BORDERS.includes(p.lineStyle)) out.fields.borderStyle = p.lineStyle
      if (FORMAT_HEADED.includes(kind) && lookAllowed('head', p.head, kind)) out.look.head = p.head
      if (FORMAT_HATCHED.includes(kind) && typeof p.hatch === 'boolean') out.fields.hatch = p.hatch
    }
    const t = fmt.text
    if (kind !== 'unit' && t && on('text')) {
      if (t.fontSize === null || (Number.isInteger(t.fontSize) && t.fontSize > 0)) out.fields.fontSize = t.fontSize
      if (t.fontColor === '' || FORMAT_COLORS.includes(t.fontColor)) out.fields.fontColor = t.fontColor
      if (kind === 'zone' && FORMAT_ALIGNS.includes(t.labelAlign)) out.fields.labelAlign = t.labelAlign
    }
    const empty = !out.size && !Object.keys(out.fields).length && !Object.keys(out.look).length
    return empty ? null : out
  }
  // 모양 값 look 에 patch(값 null 은 처음 값으로)를 얹은 그 종류의 정규 꼴.
  function patchedLook(look, patch, kind) {
    const merged = { ...(look || {}) }
    for (const [key, value] of Object.entries(patch || {})) {
      if (value === null) delete merged[key]
      else merged[key] = value
    }
    return cleanLook(merged, kind)
  }
  // 저장소에서 읽은 서식 — 꼴이 맞으면 그 서식(모르는 칸은 버림), 아니면 null. 크기는 양수만, 글자 크기는 고를 수 있는 것
  // (sizes)만 남긴다.
  function formatFrom(raw, sizes) {
    if (!raw || typeof raw !== 'object' || typeof raw.kind !== 'string' || !raw.kind) return null
    const size = raw.size && typeof raw.size === 'object' ? { w: Number(raw.size.w), h: Number(raw.size.h) } : null
    const fmt = {
      kind: raw.kind,
      module: raw.kind === 'unit' && raw.module === true,
      size: size && [size.w, size.h].every((v) => Number.isFinite(v) && v > 0) ? size : null,
      paint: null,
      text: null,
    }
    if (raw.kind === 'unit') return fmt
    if (raw.paint && typeof raw.paint === 'object') {
      const keep = ['color', 'fillAlpha', 'line', 'lineWidth', 'lineStyle', 'head', 'hatch']
      fmt.paint = Object.fromEntries(keep.filter((key) => key in raw.paint).map((key) => [key, raw.paint[key]]))
    }
    if (raw.text && typeof raw.text === 'object') {
      const fs = raw.text.fontSize
      fmt.text = {
        fontSize: fs === null || sizes.includes(fs) ? fs : undefined,
        fontColor: raw.text.fontColor === '' || FORMAT_COLORS.includes(raw.text.fontColor) ? raw.text.fontColor : undefined,
      }
      if (FORMAT_ALIGNS.includes(raw.text.labelAlign)) fmt.text.labelAlign = raw.text.labelAlign
    }
    return fmt
  }
  // </format-paint>

  // ---------------------------------------------------------------- 서식 복사·붙여넣기 키(순수 함수)
  // 기본 키는 Alt+Shift+C/V(macOS ⌥+⇧)다 — Ctrl(⌘)+Shift+C 는 실제 Chrome·Firefox 에서 개발자 도구 「검사」 가 먼저 가져갈 수
  // 있다(사양 D3 — 2026-11-04 사용자 「권장대로」). Ctrl(⌘)+Shift+C/V 도 브라우저가 페이지에 넘겨주면 그대로 받는다(둘 다). Alt 조합의
  // `key` 는 자판·OS 따라 다른 글자(macOS ⌥+⇧+C 는 「Ç」)라 글쇠 자리 `code`(KeyC·KeyV)로 보고, 다른 글쇠 자리일 때만 `key` 를 본다
  // (요소 복사 Ctrl+C/V 와 같은 꼴 — 한글 자판의 「ㅊ」 도 자리로 잡힌다). Shift 가 없는 것, Ctrl(⌘)과 Alt 를 함께 누른 것(Windows
  // AltGr 포함), IME 조합 중(`isComposing`)인 것은 서식 키가 아니다. `tests/test_space_format_paint_js.py` 가 아래 두 표시 줄
  // 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <format-key>
  // 키보드 이벤트({key, code, ctrlKey, metaKey, altKey, shiftKey, isComposing})가 서식 키면 'c'(담기)·'v'(붙이기), 아니면 null.
  function formatKeyOf(event) {
    if (event.isComposing || !event.shiftKey) return null
    if (Boolean(event.ctrlKey || event.metaKey) === Boolean(event.altKey)) return null
    const letter = event.code === 'KeyC' ? 'c' : event.code === 'KeyV' ? 'v' : String(event.key || '').toLowerCase()
    return letter === 'c' || letter === 'v' ? letter : null
  }
  // </format-key>

  // ---------------------------------------------------------------- 뒤집기 키(순수 함수)
  // Shift+H 좌우 · Shift+V 상하 뒤집기(2026-11-04 Space 결정 보드 답 — 고른 베이·비대칭 도형 모두, 되돌리기 한 번). Ctrl(⌘)·Alt 가
  // 함께면 아니다(Alt+Shift+V · Ctrl+Shift+V 는 서식 붙여넣기 — `formatKeyOf` 와 겹치지 않는다). 글쇠 자리 `code`(KeyH·KeyV)로 보고
  // 다른 자리일 때만 `key` 를 본다(한글 자판의 「ㅗ」·「ㅍ」 도 자리로 잡힌다). IME 조합 중은 비킨다. `tests/test_space_flip_js.py`
  // 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <flip-key>
  // 키보드 이벤트({key, code, ctrlKey, metaKey, altKey, shiftKey, isComposing})가 뒤집기 키면 'h'(좌우)·'v'(상하), 아니면 null.
  function flipKeyOf(event) {
    if (event.isComposing || !event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return null
    const letter = event.code === 'KeyH' ? 'h' : event.code === 'KeyV' ? 'v' : String(event.key || '').toLowerCase()
    return letter === 'h' || letter === 'v' ? letter : null
  }
  // </flip-key>

  // ---------------------------------------------------------------- 「필요 단축」 배지 자리(순수 함수)
  // `tests/test_space_short_badges_js.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름은 화면 px 상수 넷만 쓴다.
  // <short-badge>
  // 배지 상자 {x(가운데), y(가운데, 데이터 좌표 — Y 위로), w, h, mainSize, subSize, mainY, subY}. rects 는 그 호기의 보이는 모듈
  // 상자들([{x, y, w, h}]), upp 는 화면 px 당 데이터 단위, labelAbove 면 Main 설비 이름표(위)만큼 더 비킨다. em 은 두 줄 글자
  // 폭(em), canvasH 는 영역 높이 — 위 끝을 넘으면 묶음 안쪽 위 띠로 뒤집는다. 크기는 화면 px 에 표지 배율 k(배율을 따라
  // 0.75~1.25 배 — `calloutScale`)를 곱한 것이고, nameK 는 Main 설비명 글자 배율(이름표 위로 비킬 높이)이다.
  function badgeSpot(rects, upp, labelAbove, em, canvasH, k = 1, nameK = 1) {
    const x0 = Math.min(...rects.map((r) => r.x))
    const x1 = Math.max(...rects.map((r) => r.x + r.w))
    const y1 = Math.max(...rects.map((r) => r.y + r.h))
    const mainSize = BADGE_MAIN_PX * k * upp
    const subSize = BADGE_SUB_PX * k * upp
    const pad = BADGE_PAD_PX * k * upp
    const gap = BADGE_GAP_PX * k * upp
    const w = Math.max((em.main || 1) * mainSize, (em.sub || 1) * subSize) + pad * 2
    const h = mainSize * 1.2 + subSize * 1.2 + pad
    const lift = gap + (labelAbove ? (GROUP_NAME_PX * nameK * 1.6 + 2) * upp : 0)
    let y = y1 + lift + h / 2
    if (y + h / 2 > canvasH) y = y1 - gap - h / 2
    return {
      x: (x0 + x1) / 2, y, w, h, mainSize, subSize,
      mainY: pad / 2 + mainSize * 0.6, subY: pad / 2 + mainSize * 1.2 + subSize * 0.6,
    }
  }
  // 배지끼리 겹치지 않게 자리를 고른다 — 배지는 화면 px 고정이라 좁은 화면의 맞춤 배율에서 이웃 배지를 덮는다(390px 리뷰).
  // spots 는 목록 차례(기한 지남 → 남은 날 짧은 순)라 앞 배지가 먼저 자리를 잡는다. 후보는 제자리 → 한 칸 위(배지 높이 + 틈)
  // 이고 영역 위 끝을 넘는 후보는 버린다. 둘 다 겹치면 null — 그 배지는 이 배율에서 숨고(확대하면 다시 선다) 상자 구간 색과
  // 「이 층에서 단축할 호기」 표가 남는다.
  function settleBadges(spots, upp, canvasH, k = 1) {
    const placed = []
    const hits = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2
    return spots.map((spot) => {
      for (const dy of [0, spot.h + BADGE_GAP_PX * k * upp]) {
        const at = { ...spot, y: spot.y + dy }
        if (dy && at.y + at.h / 2 > canvasH) continue
        if (!placed.some((other) => hits(other, at))) {
          placed.push(at)
          return at
        }
      }
      return null
    })
  }
  // </short-badge>

  // ---------------------------------------------------------------- FAB 층 블록 글자 줄(순수 함수)
  // `tests/test_space_block_text_js.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다(글자 폭은 인자).
  // <block-text>
  // 층 블록 가운데 글자 줄 — [{text, size, role}] 를 위에서 아래 차례로 돌려준다(role 'head'·'sub'·'short'). main 은 이름 줄과
  // 그 아래 줄(배치·미배치 대수, 비활성 층은 사유), short 는 색 기준 「필요 단축」 의 단축 줄(없으면 빈 글), lw·lh 는 블록 크기
  // (데이터 단위), upp 는 화면 px 당 데이터 단위, em 은 글자 폭(em) 함수다. 크기는 블록에 맞추되 화면 maxPx(처음 13 — 그리는
  // 쪽이 배율 글자 배율을 곱해 넘긴다, `// <text-scale>`)를 넘지 않는다.
  // - 단축 줄은 다른 줄의 크기를 끌어내리지 않는다 — 긴 단축 줄(「단축 5대 · 최대 −197일 · 추가 28」)에 맞추느라 이름까지 반으로
  //   줄어 강조하려는 층 이름이 6~7px 이 됐다(E2E r1). 위 줄은 제 폭으로 맞추고(높이는 단축 줄 몫도 나눈다), 단축 줄만 제 폭에
  //   맞춰 더 작아진다. 한 줄로 많이 줄면(위 줄의 0.75 배 아래) 「 · 」 경계에서 두 줄로 나눠 본다 — 나눈 줄이 1.15 배 넘게
  //   커지고 위 줄이 0.9 배 밑으로 줄지 않을 때만 나눈다(낮은 블록에서는 줄을 늘리면 이름이 작아진다).
  // - 위 줄이 둘 이상인데 화면 7px 아래면 단축 줄부터 뺀다 — 단축 줄 없이 위 줄이 7px 이상이면 이름·대수 두 줄을 남기고
  //   (단축 줄 몫을 나눈 크기로 판정해 대수 줄까지 빼던 것 — 2026-11-02 E2E), 그래도 7px 아래면 이름 줄만 남긴다(풍선에
  //   남는다). 비활성 층(`off`)이면 이름 앞에 「⊘」 를 달아 사유 줄이 빠진 좁은 화면에서도 사용 층과 가른다(390px — E2E r1).
  // - 단축 줄이 화면 6px 아래면 그 줄만 숨긴다. 이름 줄이 6px 아래면 부르는 쪽이 숨긴다.
  function blockTextLayout(main, short, off, lw, lh, upp, em, maxPx = 13) {
    const fit = (rows, count) => Math.min((lh * 0.8) / (count * 1.3), (lw * 0.9) / Math.max(...rows.map(em), 1), maxPx * upp)
    const widthFit = (rows) => (lw * 0.9) / Math.max(...rows.map(em), 1)
    const splitTwo = (text) => {
      const parts = text.split(' · ')
      if (parts.length < 2) return null
      let best = null
      for (let k = 1; k < parts.length; k += 1) {
        const rows = [parts.slice(0, k).join(' · '), parts.slice(k).join(' · ')]
        const widest = Math.max(...rows.map(em))
        if (!best || widest < best.widest) best = { rows, widest }
      }
      return best.rows
    }
    const lay = (head, shortRows) => {
      const size = fit(head, head.length + shortRows.length)
      const shortSize = shortRows.length ? Math.min(size, widthFit(shortRows)) : 0
      return { head, shortRows, size, shortSize }
    }
    let pick = lay(main, [])
    if (short) {
      const one = lay(main, [short])
      const two = splitTwo(short)
      const split = two ? lay(main, two) : null
      const better = split && split.shortSize > one.shortSize * 1.15 && split.size >= one.size * 0.9 && split.size / upp >= 7
      pick = better && one.shortSize < one.size * 0.75 ? split : one
    }
    if (main.length > 1 && pick.size / upp < 7 && pick.shortRows.length) {
      const bare = lay(main, [])
      if (bare.size / upp >= 7) pick = bare
    }
    if (main.length > 1 && pick.size / upp < 7) {
      const head = off ? `⊘ ${main[0]}` : main[0]
      return [{ text: head, size: fit([head], 1), role: 'head' }]
    }
    if (pick.shortRows.length && pick.shortSize / upp < 6) pick = lay(pick.head, [])
    return [
      ...pick.head.map((text, k) => ({ text, size: pick.size, role: k === 0 ? 'head' : 'sub' })),
      ...pick.shortRows.map((text) => ({ text, size: pick.shortSize, role: 'short' })),
    ]
  }
  // </block-text>

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
    // 색 기준 「필요 단축」 에 표시된 호기는 숨기지 않는다 — 단축 후보는 대개 기존 설비 자리에 들어올 반입 전 신규 호기다.
    if (item.layer) return false
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

  // ---------------------------------------------------------------- 공식과 견주기(층 상세 보기, 순수 함수)
  // 파이썬 `services/layout_overlay.layout_compare` 가 낸 재료(`data.compare` — epoch 밖)를 그릴 꼴로 바꾼다(설계 8-3). 점선 상자
  // (`ghosts` — 기준 쪽 자리)는 꼬리표가 없으면 지금 상자(boxOf)와 가운데끼리 가는 선으로 잇고, 꼬리표가 있으면 상자 왼쪽 위에
  // 꼬리표를 단다. 들어온 호기(`arrivals`)는 지금 상자 왼쪽 위에 꼬리표다. 좌표는 데이터(왼쪽 아래 원점) → SVG(위 원점, canvasH)로
  // 뒤집고, 꼬리표 글자 크기 fs 는 화면 px 를 데이터 단위로 바꾼 값이다. `tests/test_space_layout_compare.py` 가 아래 두 표시 줄
  // 사이를 떼어 node 로 돌린다 — 바깥 이름을 쓰지 않는다.
  // <view-compare>
  function compareShapes(compare, boxOf, canvasH, fs) {
    const shapes = []
    // 빈 값(null·빈 글)은 0 이 아니라 숫자 아님이다.
    const n = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v))
    const finite = (b) => Boolean(b) && [b.x, b.y, b.w, b.h].every((v) => typeof v === 'number' && Number.isFinite(v))
    const tagAt = (b, text) => ({ kind: 'tag', x: b.x, y: canvasH - (b.y + b.h) - fs * 0.35, text: String(text) })
    for (const ghost of (compare && compare.ghosts) || []) {
      const box = { x: n(ghost.x), y: n(ghost.y), w: n(ghost.w), h: n(ghost.h) }
      if (!finite(box)) continue
      shapes.push({ kind: 'box', x: box.x, y: canvasH - (box.y + box.h), w: box.w, h: box.h })
      if (ghost.tag) {
        shapes.push(tagAt(box, ghost.tag))
        continue
      }
      const now = boxOf(String(ghost.id))
      if (!finite(now)) continue
      shapes.push({
        kind: 'line',
        x1: box.x + box.w / 2, y1: canvasH - (box.y + box.h / 2),
        x2: now.x + now.w / 2, y2: canvasH - (now.y + now.h / 2),
      })
    }
    for (const arrival of (compare && compare.arrivals) || []) {
      const now = boxOf(String(arrival.id))
      if (finite(now) && arrival.tag) shapes.push(tagAt(now, arrival.tag))
    }
    // 이웃한 차이 호기의 꼬리표가 서로 덮지 않게, 앞 꼬리표와 겹치는 꼬리표는 한 줄씩 위로(캔버스 위로 넘치면 아래로) 옮긴다 —
    // 가까운 줄부터 위·아래 차례로 비는 줄을 찾는다(글자 폭은 어림 — 한글·화살표 1em, 그 밖 0.62em). 못 찾으면 제자리다.
    const wide = (code) => code >= 0x2190 || (code >= 0x1100 && code <= 0x11ff)
    const tagWidth = (text) => [...text].reduce((sum, ch) => sum + (wide(ch.codePointAt(0)) ? 1 : 0.62), 0) * fs
    const lineH = fs * 1.25
    const placed = []
    const span = (shape, y) => ({ x0: shape.x, x1: shape.x + tagWidth(shape.text), y0: y - fs, y1: y + fs * 0.25 })
    const hits = (a) => placed.some((b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1)
    for (const shape of shapes) {
      if (shape.kind !== 'tag') continue
      let y = shape.y
      if (hits(span(shape, y))) {
        const tries = []
        for (let k = 1; k <= 8; k += 1) tries.push(shape.y - k * lineH, shape.y + k * lineH)
        const free = tries.find((candidate) => candidate - fs >= 0 && candidate <= canvasH && !hits(span(shape, candidate)))
        if (free !== undefined) y = free
      }
      shape.y = y
      placed.push(span(shape, y))
    }
    return shapes
  }
  // </view-compare>

  // 두 옆 칸·스크롤 고정의 판정(순수 함수). `tests/test_space_editor_panels_js.py` 가 아래 두 표시 줄 사이를 떼어 node 로
  // 돌린다 — 바깥 이름을 쓰지 않는다.
  // <side-panels>
  // 칸 폭 한계 — 최소 lo, 최대 min(hi, 편집기 폭 × hiShare)(최소보다 작지 않게), 기본 clamp(defLo, 편집기 폭 × defShare,
  // defHi)(한계 안으로).
  function panelBounds(editorW, spec) {
    const width = Math.max(0, Number(editorW) || 0)
    const hi = Math.max(spec.lo, Math.min(spec.hi, width * spec.hiShare))
    const def = Math.max(spec.defLo, Math.min(spec.defHi, width * spec.defShare))
    return { lo: spec.lo, hi, def: Math.max(spec.lo, Math.min(hi, def)) }
  }
  // 칸 폭을 한계 안으로(정수 px). 값이 없거나(null) 수가 아니면 기본 폭 — 끄는 동안 0 아래로 간 값은 최소다.
  function clampPanel(px, bounds) {
    const n = Number(px)
    const value = px !== null && px !== undefined && px !== '' && Number.isFinite(n) ? n : bounds.def
    return Math.round(Math.max(bounds.lo, Math.min(bounds.hi, value)))
  }
  // 저장값 읽기 — {'<범위>.<모드>': {left|right: {w, min}}}. 꼴이 다른 칸은 버린다(폭은 0 초과 4000 이하의 수, 접힘은 참일 때만).
  function storedPanels(raw) {
    let value = null
    try {
      value = JSON.parse(raw || 'null')
    } catch {
      value = null
    }
    const out = {}
    if (!value || typeof value !== 'object' || Array.isArray(value)) return out
    for (const [mode, sides] of Object.entries(value)) {
      if (!/^(floor|fab)\.(edit|view)$/.test(mode) || !sides || typeof sides !== 'object') continue
      const kept = {}
      for (const side of ['left', 'right']) {
        const state = sides[side]
        if (!state || typeof state !== 'object') continue
        const w = typeof state.w === 'number' && Number.isFinite(state.w) && state.w > 0 && state.w <= 4000 ? Math.round(state.w) : null
        kept[side] = { w, min: state.min === true }
      }
      out[mode] = kept
    }
    return out
  }
  // 칸막이 키 — 왼쪽 칸은 → 가, 오른쪽 칸은 ← 가 넓힌다(한 걸음 16px, Shift 64px). Home 최대 · End 최소 · Enter 접기. 그 밖의
  // 키는 null(놓아 둔다).
  function splitKey(key, shift, side, now, bounds) {
    const step = shift ? 64 : 16
    const grow = side === 'left' ? 'ArrowRight' : 'ArrowLeft'
    const shrink = side === 'left' ? 'ArrowLeft' : 'ArrowRight'
    if (key === grow) return { width: now + step }
    if (key === shrink) return { width: now - step }
    if (key === 'Home') return { width: bounds.hi }
    if (key === 'End') return { width: bounds.lo }
    if (key === 'Enter') return { fold: true }
    return null
  }
  // 두 칸을 다 넓혀 무대가 stageMin 아래로 가면 마지막에 끈 칸(last)부터, 그래도 모자라면 다른 칸을 줄인다(칸마다 그 최소
  // `lo` 까지 — 접힌 띠는 lo = 폭이라 줄지 않는다). 칸막이는 펼친 칸에만 있다(split).
  function fitPanels(editorW, left, right, last, stageMin, split) {
    let l = left.w
    let r = right.w
    const room = () => editorW - l - r - (left.open ? split : 0) - (right.open ? split : 0)
    let over = stageMin - room()
    for (const side of last === 'left' ? ['left', 'right'] : ['right', 'left']) {
      if (over <= 0) break
      if (side === 'left') {
        const cut = Math.min(over, Math.max(0, l - left.lo))
        l -= cut
        over -= cut
      } else {
        const cut = Math.min(over, Math.max(0, r - right.lo))
        r -= cut
        over -= cut
      }
    }
    return { left: Math.round(l), right: Math.round(r) }
  }
  // 끄는 칸의 최대 폭 — 다른 칸과 칸막이 둘을 빼고 무대 stageMin 을 남긴 만큼(그 칸 최소보다 작지 않게).
  function dragLimit(editorW, otherW, splits, stageMin, lo) {
    return Math.max(lo, Math.floor(editorW - otherW - splits - stageMin))
  }
  // 스크롤 고정 무대 높이 — 창 높이에서 무대 위 끝과 아래 몫(상태 줄 높이 + 12px)을 뺀 만큼, 최소 minH.
  function lockHeight(viewportH, stageTop, statusH, minH) {
    const below = Math.max(0, Number(statusH) || 0) + 12
    return Math.max(minH, Math.floor(Number(viewportH) - Number(stageTop) - below))
  }
  // 스크롤 고정 때 편집기 맨 위가 설 자리(창 위에서 px) — 가림 끝(화면 탭 줄 아래 끝, 없으면 머리 띠 72) + 8.
  function lockTop(coverBottom) {
    return Math.round(Math.max(72, Number(coverBottom) || 0)) + 8
  }
  // 점(x, y)이 상자 안인가(경계 포함, 넓이 없는 상자는 아님) — 도면의 호기를 오른쪽 칸에 끌어 놓으면 미배치로.
  function insideRect(rect, x, y) {
    return Boolean(rect) && rect.width > 0 && rect.height > 0
      && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
  }
  // </side-panels>
  // 「호기 정보」 창의 표 판정(순수 함수, 2026-11-03 사용자 요청 — 고른 호기의 칸과, 칸마다 엑셀 자동 필터 꼴로 거른 호기
  // 목록·도면 강조). 표 재료는 파이썬 `services/space_unit_sheet.unit_sheet`(칸 [{name, type}], 줄 [{id, group, cells}])다.
  // `tests/test_space_unit_sheet_js.py` 가 아래 두 표시 줄 사이를 `// <module-tiling>` 구획(자연 정렬 `naturalCompare`)과 함께
  // 떼어 node 로 돌린다 — 그 밖의 바깥 이름을 쓰지 않는다. 필터 꼴: {칸 이름: {values?: [열쇠], from?, to?}} — values 가 있으면
  // 그 값 가운데 하나(칸 안 OR), from·to 는 날짜·숫자 칸의 범위(양 끝 포함, 빈 끝은 열림)이고 칸끼리는 AND 다.
  // <unit-sheet>
  // 칸 값의 비교 열쇠 — 빈 값(null·빈 글)은 ''(「(빈칸)」 한 항목), 글은 앞뒤 공백을 걷고 소문자(엑셀 자동 필터처럼 대소문자를
  // 가리지 않는다), 수는 수 글이다.
  function sheetKey(value) {
    if (value === null || value === undefined) return ''
    if (typeof value === 'number') return Number.isFinite(value) ? String(value) : ''
    return String(value).trim().toLowerCase()
  }
  // 칸 값의 보이는 글 — 수는 소수 둘째 자리까지, 빈 값은 ''.
  function sheetText(value) {
    if (value === null || value === undefined) return ''
    if (typeof value === 'number') return Number.isFinite(value) ? String(Math.round(value * 100) / 100) : ''
    return String(value).trim()
  }
  const rangeEnd = (value) => (value === null || value === undefined ? '' : String(value).trim())
  // 범위가 걸렸는가(한 끝이라도 있으면).
  function sheetRangeOn(rule) {
    return Boolean(rule) && (rangeEnd(rule.from) !== '' || rangeEnd(rule.to) !== '')
  }
  // 값이 범위 안인가 — 날짜는 「YYYY-MM-DD」 글로, 숫자는 수로 견준다. 범위가 없으면 늘 참, 있으면 빈 값·꼴이 다른 값은 거짓.
  function inRange(value, rule, type) {
    if (!sheetRangeOn(rule)) return true
    const from = rangeEnd(rule.from)
    const to = rangeEnd(rule.to)
    if (type === 'number') {
      if (typeof value !== 'number' || !Number.isFinite(value)) return false
      const lo = from === '' ? -Infinity : Number(from)
      const hi = to === '' ? Infinity : Number(to)
      if (Number.isNaN(lo) || Number.isNaN(hi)) return false
      return value >= lo && value <= hi
    }
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
    return (from === '' || value >= from) && (to === '' || value <= to)
  }
  // 칸 하나의 필터가 걸렸는가 — 값 고르기(빈 목록이어도 — 아무것도 고르지 않음)나 범위.
  const sheetRuleOn = (rule) => Boolean(rule) && (Array.isArray(rule.values) || sheetRangeOn(rule))
  // 걸린 칸 이름(이 표에 있는 칸만, 칸 차례).
  function sheetActive(columns, filters) {
    return (columns || []).map((column) => column.name).filter((name) => sheetRuleOn((filters || {})[name]))
  }
  // 필터에 맞는 줄(받은 차례). `skip` 칸의 필터는 보지 않는다(그 칸 값 목록은 다른 칸 필터만 지난 줄에서 — 엑셀처럼).
  function sheetMatch(rows, columns, filters, skip) {
    const rules = []
    for (const [index, column] of (columns || []).entries()) {
      const rule = (filters || {})[column.name]
      if (column.name === skip || !sheetRuleOn(rule)) continue
      rules.push({ index, type: column.type, rule, keys: Array.isArray(rule.values) ? new Set(rule.values.map(String)) : null })
    }
    if (!rules.length) return [...(rows || [])]
    return (rows || []).filter((row) => rules.every(({ index, type, rule, keys }) => {
      const value = row.cells[index]
      if (keys && !keys.has(sheetKey(value))) return false
      return inRange(value, rule, type)
    }))
  }
  // 칸 값 목록 — [{key, text, count}]. 대소문자만 다른 글은 한 항목(처음 만난 꼴로 보인다), 빈 값은 「(빈칸)」 으로 맨 뒤.
  // 차례는 숫자 칸이면 수, 그 밖은 설비명 자연 정렬(`naturalCompare` — 날짜 글은 글 차례가 날짜 차례다).
  function distinctValues(rows, index, type) {
    const seen = new Map()
    for (const row of rows || []) {
      const value = row.cells[index]
      const key = sheetKey(value)
      const found = seen.get(key)
      if (found) found.count += 1
      else seen.set(key, { key, text: key === '' ? '(빈칸)' : sheetText(value), count: 1, value })
    }
    const list = [...seen.values()]
    list.sort((a, b) => {
      if ((a.key === '') !== (b.key === '')) return a.key === '' ? 1 : -1
      const na = typeof a.value === 'number'
      const nb = typeof b.value === 'number'
      if (type === 'number' && na && nb) return a.value - b.value
      if (na !== nb) return na ? -1 : 1
      return naturalCompare(a.text, b.text)
    })
    return list.map(({ key, text, count }) => ({ key, text, count }))
  }
  // 고른 호기의 줄 — 파이썬 `space_layout.picked_unit_rows` 와 같은 규칙: 그 설비 줄, Main 설비 모듈이면 같은 Main 설비 줄
  // 전부이고 누른 것이 첫 줄, 나머지는 설비명 자연 정렬(같으면 받은 차례). 없는 설비면 빈 목록.
  function pickedRows(rows, id) {
    const list = rows || []
    const first = list.find((row) => row.id === id)
    if (!first) return []
    const parent = first.group
    return list
      .map((row, index) => [row, index])
      .filter(([row]) => row.id === id || (parent && row.group === parent))
      .sort((a, b) => (Number(a[0].id !== id) - Number(b[0].id !== id)) || naturalCompare(a[0].id, b[0].id) || a[1] - b[1])
      .map(([row]) => row)
  }
  // 여럿 고른 호기(배치 편집)의 줄 — 고른 차례로 `pickedRows` 를 잇고 같은 줄은 한 번만.
  function pickedRowsMany(rows, ids) {
    const out = []
    const seen = new Set()
    for (const id of ids || []) {
      for (const row of pickedRows(rows, id)) {
        if (seen.has(row.id)) continue
        seen.add(row.id)
        out.push(row)
      }
    }
    return out
  }
  // 도면에서 강조할 호기 — 필터가 하나라도 걸렸으면 맞는 줄의 id 묶음, 아니면 null(강조 없음).
  function sheetHits(rows, columns, filters) {
    if (!sheetActive(columns, filters).length) return null
    return new Set(sheetMatch(rows, columns, filters).map((row) => row.id))
  }
  // 칸 값 글 → 줄 수(「도면」 칸 — 배치·미배치·…), 처음 만난 차례.
  function countBy(rows, index) {
    const out = new Map()
    for (const row of rows || []) {
      const text = sheetText(row.cells[index])
      out.set(text, (out.get(text) || 0) + 1)
    }
    return out
  }
  // 창 자리·크기를 편집기 몸(bodyW × bodyH) 안으로 — 폭·높이는 최소(minW·minH, 몸보다 크면 몸)와 몸 사이, 자리는 창 전체가
  // 몸 안에 들게(접힌 창은 제목 줄 높이 headH 만큼). 값이 수가 아니면 기본(def)이다.
  function clampSheet(win, def, bodyW, bodyH, minW, minH, headH) {
    const pick = (value, fallback) => (typeof value === 'number' && Number.isFinite(value) ? value : fallback)
    const width = Math.max(0, Number(bodyW) || 0)
    const height = Math.max(0, Number(bodyH) || 0)
    const w = Math.round(Math.max(Math.min(minW, width), Math.min(width, pick(win && win.w, def.w))))
    const h = Math.round(Math.max(Math.min(minH, height), Math.min(height, pick(win && win.h, def.h))))
    const tall = win && win.min ? Math.min(h, headH) : h
    const x = Math.round(Math.max(0, Math.min(width - w, pick(win && win.x, def.x))))
    const y = Math.round(Math.max(0, Math.min(height - tall, pick(win && win.y, def.y))))
    return { x, y, w, h }
  }
  // 창이 무대를 덮을 때 고른 호기가 창 밑에 들면 옮길 거리(화면 px, 양수면 화면을 그쪽으로 민다) — 무대에서 창이 덮지 않은
  // 띠(위·아래·왼쪽·오른쪽) 가운데 가장 넓은 띠의 가운데로. 창이 무대와 겹치지 않거나 호기가 창과 겹치지 않으면 null. 사각형은
  // {left, top, right, bottom}.
  function clearOfSheet(stage, win, rect) {
    const meet = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
    if (!stage || !win || !rect || !meet(stage, win) || !meet(win, rect)) return null
    const bands = [
      { left: stage.left, right: stage.right, top: stage.top, bottom: Math.max(stage.top, win.top) },
      { left: stage.left, right: stage.right, top: Math.min(stage.bottom, win.bottom), bottom: stage.bottom },
      { left: stage.left, right: Math.max(stage.left, win.left), top: stage.top, bottom: stage.bottom },
      { left: Math.min(stage.right, win.right), right: stage.right, top: stage.top, bottom: stage.bottom },
    ]
    const area = (b) => Math.max(0, b.right - b.left) * Math.max(0, b.bottom - b.top)
    const best = bands.reduce((a, b) => (area(b) > area(a) ? b : a))
    if (!area(best)) return null
    return {
      dx: (rect.left + rect.right) / 2 - (best.left + best.right) / 2,
      dy: (rect.top + rect.bottom) / 2 - (best.top + best.bottom) / 2,
    }
  }
  // 저장값 읽기 — 창 {x, y, w, h, min}(수는 유한한 것만), 상태 {open, tab, hl, filters}(필터는 글 칸 이름 → 값 열쇠 글
  // 목록·범위 글만). 꼴이 다르면 기본.
  function storedSheetWin(raw) {
    let value = null
    try {
      value = JSON.parse(raw || 'null')
    } catch {
      value = null
    }
    const num = (n) => (typeof n === 'number' && Number.isFinite(n) ? n : null)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { x: null, y: null, w: null, h: null, min: false }
    return { x: num(value.x), y: num(value.y), w: num(value.w), h: num(value.h), min: value.min === true }
  }
  function storedSheetState(raw) {
    let value = null
    try {
      value = JSON.parse(raw || 'null')
    } catch {
      value = null
    }
    const out = { open: false, tab: 'picked', hl: true, filters: {} }
    if (!value || typeof value !== 'object' || Array.isArray(value)) return out
    out.open = value.open === true
    out.tab = value.tab === 'filter' ? 'filter' : 'picked'
    out.hl = value.hl !== false
    const filters = value.filters && typeof value.filters === 'object' && !Array.isArray(value.filters) ? value.filters : {}
    for (const [name, rule] of Object.entries(filters)) {
      if (!rule || typeof rule !== 'object') continue
      const kept = {}
      if (Array.isArray(rule.values)) kept.values = rule.values.filter((key) => typeof key === 'string')
      if (typeof rule.from === 'string' && rule.from.trim()) kept.from = rule.from.trim()
      if (typeof rule.to === 'string' && rule.to.trim()) kept.to = rule.to.trim()
      if (sheetRuleOn(kept)) out.filters[name] = kept
    }
    return out
  }
  // 창의 칸·줄 → CSV 글(BOM 없음 — 내려받을 때 붙인다). 값은 창이 받은 그대로(날짜 「YYYY-MM-DD」 글, 수는 수 글, 빈 값은 빈칸)이고
  // 쉼표·큰따옴표·줄바꿈이 든 칸은 큰따옴표로 싸고 안의 큰따옴표는 둘로 적는다(파이썬 `csv` 의 QUOTE_MINIMAL 과 같다). 줄 끝은
  // LF 이고 마지막 줄 뒤에도 붙는다(pandas `to_csv` 와 같은 꼴).
  function sheetCsv(columns, rows) {
    const cell = (value) => {
      const text = value === null || value === undefined ? '' : typeof value === 'number' ? (Number.isFinite(value) ? String(value) : '') : String(value)
      return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
    }
    const lines = [columns.map((column) => cell(column.name)).join(',')]
    for (const row of rows) lines.push(row.cells.map(cell).join(','))
    return `${lines.join('\n')}\n`
  }
  // </unit-sheet>
  // 채우기·글자: 「필요 단축」 구간(표시된 호기) → 지연(빨강) → 보관(검정) → 파이썬이 색 기준·체크로 정한 면(체크한
  // 그룹색, 아니면 기본 회색). 「필요 단축」 을 켠 동안(ASOF_PINNED)은 지연·보관 면을 칠하지 않는다(결정 D12).
  function unitColors(item, st) {
    if (item.layer) return { fill: `var(--sle-short-${item.layer}-fill)`, ink: `var(--sle-short-${item.layer}-ink)` }
    if (st.delay && !ASOF_PINNED) return { fill: 'var(--sle-unit-delay-fill)', ink: 'var(--sle-unit-delay-ink)' }
    if (st.storage && !ASOF_PINNED) return { fill: 'var(--sle-unit-storage-fill)', ink: 'var(--sle-unit-storage-ink)' }
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
    // 모양 값은 바꿀 때마다 새 객체로 갈아 끼운다(제자리에서 고치지 않는다) — 기록이 같은 객체를 쥐어도 된다.
    look: item.look,
  })
  // 층 블록 글자: 첫 줄은 이름(없으면 연결 층), 다음 줄은 배치·미배치 대수. 풍선에는 점유율까지.
  const blockHead = (item) => item.label || item.link || '연결 없음'
  // 비활성 층을 가리키는 블록의 사유 글. 연결 층의 `linkStats.inactive` 에서 온다 — 사람이 직접 적은 글(20자까지, 옛 코드는
  // 「사용 안 함」·「생산라인 아님」)이라 늘 textContent·title 로만 싣는다(HTML 로 읽지 않는다). 회색 빗금으로 그리고 보기에서
  // 눌러도 열지 않는다(그 층은 층 목록 표 「비활성 층」에서 연다). 사용 층이면 빈 글.
  const blockOff = (item) => (item && item.kind === 'block' && item.link && LINK_STATS[item.link] && LINK_STATS[item.link].inactive) || ''
  // 블록 안 사유 줄은 BLOCK_OFF_CHARS 글자까지 — 넘으면 앞을 남기고 「…」 로 줄인다(글자 맞춤이 긴 줄 하나에 끌려 작아지지 않게).
  // 자른 끝의 빈칸은 뗀다. 풍선·선택 줄에는 다 보인다. 글자는 코드 포인트로 센다(이모지 반쪽이 남지 않게).
  const BLOCK_OFF_CHARS = 8
  const clipOff = (text) => {
    const chars = Array.from(String(text))
    return chars.length > BLOCK_OFF_CHARS ? `${chars.slice(0, BLOCK_OFF_CHARS - 1).join('').trimEnd()}…` : String(text)
  }
  // 블록 글자의 위 줄(이름·대수 — 비활성 블록은 이름·사유)과 단축 줄. 비활성 블록은 대수 줄 대신 사유다(대수는 풍선에
  // 남는다). 「필요 단축」 을 켠 동안은 대수 줄 뒤에 단축 줄(`short` — 「단축 3대 · 최대 −18일」, 비활성 층에는 오지 않는다)이
  // 붙는다 — 크기는 따로 맞춘다(`blockTextLayout`).
  const blockLines = (item) => {
    const stats = LINK_STATS[item.link] || {}
    if (blockOff(item)) return { main: [String(blockHead(item)), clipOff(blockOff(item))], short: '' }
    return { main: [blockHead(item), stats.placed, stats.unplaced].filter(Boolean).map(String), short: stats.short ? String(stats.short) : '' }
  }
  const opensFloor = (item) => Boolean(VIEW && FAB && item && item.kind === 'block' && item.link && !blockOff(item))
  const blockTip = (item) => {
    const stats = LINK_STATS[item.link] || {}
    // 「공식과 견주기」 를 켠 회차에는 공식과 자리가 다른 설비 수 한 줄(`stats.layout` — 「가정 배치 n대 다름」)이, 「필요 단축」 을
    // 켠 동안은 단축 줄(`stats.short` — 비활성 층에는 오지 않는다)이 붙는다.
    if (blockOff(item)) return [blockHead(item), '비활성', blockOff(item), stats.placed, stats.unplaced, stats.layout].filter(Boolean).join(' · ')
    const parts = [blockHead(item), stats.placed, stats.unplaced, stats.occupancy, stats.short, stats.layout].filter(Boolean)
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
    const ts = textScale(1 / upp)
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
      const fs = groupNameSize(range, position, labelEm(name), GROUP_NAME_PX * ts, upp, UNIT_LABEL_MIN_PX, bare)
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
    // 배지는 Main 설비 이름표가 「위」면 그 위로 비킨다 — 이름표가 다시 설 때마다 배지도 다시 선다.
    drawShortBadges()
  }

  // ---------------------------------------------------------------- 「필요 단축」 배지(층 보기)
  // 단축 호기(모듈 묶음은 Main 설비 하나)마다 상자(묶음은 그 층에 그린 모듈 전체의 바깥 상자) 위 가운데에 말풍선 하나 —
  // 윗줄 「−12일」, 아랫줄 「D-5」·「오늘」·「기한 지남」. 구간 색이고 임박은 굵은 테다. 표지라 화면 px 크기에 배율을 따른
  // 0.75~1.25 배만 곱한다(`calloutScale`). 누르면 그 호기를 누른 것과 같다(`pick`). 기준일에 숨은 모듈은 바깥 상자에서 뺀다.
  function drawShortBadges() {
    if (!badgesLayer) return
    // 다시 그리면 배지 노드가 모두 새로 선다 — 초점을 가진 배지(키보드로 고른 것)는 같은 key 의 새 배지로 돌려준다.
    // 돌려주지 않으면 Enter 로 고를 때마다 초점이 문서 처음으로 빠져 처음부터 다시 Tab 해야 한다(리뷰).
    const root = svg.getRootNode()
    const focused = root && root.activeElement
    const focusKey = focused && badgesLayer.contains(focused) ? focused.dataset.key : null
    badgesLayer.replaceChildren()
    if (!ASOF_PINNED || !SHORT_BADGES.length) return
    const upp = unitsPerPx()
    // 배지는 표지라 배율을 따라 0.75~1.25 배로만 바뀐다(`calloutScale`) — Main 설비명(위)만큼 비킬 높이는 글자 배율 그대로다.
    const ts = textScale(1 / upp)
    const k = calloutScale(ts)
    const counts = groupCounts()
    const drawn = []
    for (const badge of SHORT_BADGES) {
      const ids = (Array.isArray(badge.ids) ? badge.ids : []).map(String)
      const mods = ids.map((id) => S.items.get(id)).filter((m) => m && isUnit(m) && onCanvas(m))
      const seen = mods.filter((m) => S.groups.get(m.id)?.__visible !== false)
      if (!seen.length) continue
      const lead = seen[0]
      const key = lead.group ? groupKeyOf(lead) : null
      const size = key ? counts.get(key) || 0 : 0
      const above = Boolean(key && size >= 2 && groupLabelOf(key, size) === 'top'
        && namesLayer.querySelector(`.sle-group-name-tag.is-top[data-group="${CSS.escape(key)}"]`))
      const main = String(badge.main || '')
      const sub = String(badge.sub || '')
      const spot = badgeSpot(seen.map((m) => ({ x: m.x, y: m.y, w: m.w, h: m.h })), upp, above,
        { main: labelEm(main), sub: labelEm(sub) }, H(), k, ts)
      drawn.push({ badge, ids, main, sub, spot })
    }
    const settled = settleBadges(drawn.map((entry) => entry.spot), upp, H(), k)
    drawn.forEach((entry, index) => {
      const spot = settled[index]
      if (spot) drawBadge(entry, spot, focusKey)
    })
  }

  // 배지 하나를 고른 자리에 그린다. 초점을 쥐었던 배지(같은 key)면 새 노드에 초점을 돌려준다.
  function drawBadge({ badge, ids, main, sub }, spot, focusKey) {
    const bucket = SHORT_LAYERS.has(badge.bucket) ? badge.bucket : 's'
    const node = el('g', { class: `sle-short-badge is-${bucket}`, tabindex: 0, role: 'button' })
    node.classList.toggle('is-imminent', Boolean(badge.imminent))
    node.classList.toggle('is-dim', Boolean(badge.dim))
    node.dataset.pick = ids[0]
    node.dataset.key = String(badge.key || ids[0])
    node.setAttribute('aria-label', String(badge.aria || `${badge.key || ''} ${main} ${sub}`))
    const top = H() - (spot.y + spot.h / 2)
    node.append(el('rect', {
      class: 'sle-short-badge-pill', x: spot.x - spot.w / 2, y: top, width: spot.w, height: spot.h, rx: spot.h * 0.3,
    }))
    const mainText = el('text', { class: 'sle-short-badge-main', x: spot.x, y: top + spot.mainY, 'font-size': spot.mainSize })
    mainText.textContent = main
    const subText = el('text', { class: 'sle-short-badge-sub', x: spot.x, y: top + spot.subY, 'font-size': spot.subSize })
    subText.textContent = sub
    const tip = el('title')
    tip.textContent = String(badge.tip || '')
    node.append(mainText, subText, tip)
    const pick = ids.find((id) => S.items.has(id)) || ids[0]
    node.onkeydown = (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      event.preventDefault()
      event.stopPropagation()
      select(pick)
      notePick()
    }
    badgesLayer.append(node)
    if (focusKey !== null && node.dataset.key === focusKey) node.focus({ preventScroll: true })
  }

  // 공식과 견주기 그리기(층 상세 보기만 — 편집기·FAB 에는 그리지 않는다). 배율이 바뀌면 꼬리표 글자 크기를 다시 맞추므로
  // Main 설비명과 같이 `drawSelectionBox` 가 부른다. 꼬리표는 표지라 배율을 따라 0.75~1.25 배로만 바뀐다(`calloutScale`).
  // 재료가 없으면 층을 비운다.
  const COMPARE_TAG_PX = 11
  const COMPARE = VIEW && !FAB && data.compare && typeof data.compare === 'object' ? data.compare : null
  function drawCompare() {
    if (!compareLayer) return
    compareLayer.replaceChildren()
    if (!COMPARE) return
    const upp = unitsPerPx()
    const fs = COMPARE_TAG_PX * calloutScale(textScale(1 / upp)) * upp
    const boxOf = (id) => {
      const item = S.items.get(id)
      return item && isUnit(item) && onCanvas(item) && hasSize(item) ? item : null
    }
    for (const shape of compareShapes(COMPARE, boxOf, H(), fs)) {
      if (shape.kind === 'box') {
        compareLayer.append(el('rect', { class: 'sle-compare-box', x: shape.x, y: shape.y, width: shape.w, height: shape.h }))
      } else if (shape.kind === 'line') {
        compareLayer.append(el('line', { class: 'sle-compare-line', x1: shape.x1, y1: shape.y1, x2: shape.x2, y2: shape.y2 }))
      } else {
        const text = el('text', { class: 'sle-compare-tag', x: shape.x, y: shape.y, 'font-size': fs })
        text.textContent = shape.text
        compareLayer.append(text)
      }
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
  // 화면 옮기기는 영역+여백 안에서만. 보이는 폭이 그보다 넓은 축은 영역 가운데에 둔다. 단 좁은 화면(겹침 서랍)에서 편집의
  // 미배치 서랍이 열려 있으면 그 폭(데이터 단위)만큼 오른쪽으로 더 옮길 수 있다 — 서랍 아래에 놓인 것을 꺼내 보이는 자리다.
  // 서랍을 접으면 0 이 되어 화면이 제자리로 돌아온다. 넓은 화면의 오른쪽 칸은 도면을 덮지 않아 늘 0 이다.
  function trayReserve() {
    if (VIEW || FAB || !host.classList.contains('is-narrow') || !S.drawerOpen || trayBox.hidden || !S.port || S.port.w < 1) return 0
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
  // 상자 box 가 화면에 맞는 배율로(cap 까지 — 처음 MAX_ZOOM) 그 가운데를 보인다.
  function zoomToBox(box, cap = MAX_ZOOM) {
    const pad = 3
    const base = baseBox()
    const z = clamp(Math.min(base.w / (box.maxR - box.minX + pad * 2), base.h / (box.maxT - box.minY + pad * 2)), 1, Math.min(cap, MAX_ZOOM))
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
  // 편집은 영역 비율로 줄이지 않는다 — 두 옆 칸(도구·미배치)이 무대 높이를 함께 쓰고, 옆 칸만큼 무대가 좁아져 비율
  // 높이가 너무 낮아진다(2026-11-03).
  function defaultHeight() {
    const width = stage.clientWidth || host.clientWidth || 0
    const pad = margin()
    const fitted = width > 0 && VIEW ? (width * (H() + pad * 2)) / (W() + pad * 2) : Infinity
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
    // 스크롤 고정 중에는 창 높이에 맞춘 높이(`alignLock` 이 잰 값)다 — 고른 높이·기억은 건드리지 않는다.
    if (S.lock && S.lockH) {
      setStageHeight(S.lockH)
      return measurePort()
    }
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
    const ring = group.querySelector('.sle-focus-ring')
    if (ring) {
      const gap = FOCUS_GAP_PX * unitsPerPx()
      setBox(ring, item.x - gap, top - gap, item.w + gap * 2, item.h + gap * 2)
    }
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
      // 글자는 사각형 폭에 맞춰 줄이고 화면에서 14px × 글자 배율(`textScale`)을 넘지 않게 한다. 7px 아래면 숨긴다(밀집 층) —
      // 확대하면 다시 보인다. 이름은 선택하면 상태줄·옆 칸에, 올려 두면 풍선에 나온다. 폭은 잰 글자 폭이라
      // 이름이 상자 밖으로 넘치지 않는다.
      const upp = unitsPerPx()
      const fontSize = unitLabelSize(item, upp)
      label.setAttribute('font-size', fontSize)
      label.style.display = fontSize / upp < UNIT_LABEL_MIN_PX ? 'none' : ''
      positionUnitMarks(group, item, top)
      const ring = group.querySelector('.sle-filter-ring')
      if (ring) {
        const gap = FILTER_GAP_PX * upp
        setBox(ring, item.x - gap, top - gap, item.w + gap * 2, item.h + gap * 2)
      }
    } else {
      drawMark(group, item, top)
    }
    positionHandles(group, item, top)
    group.classList.toggle('is-changed', isChanged(item) || isRenamed(item))
  }
  // 호기 이름표 글자 크기(데이터 단위) — 상자 높이의 0.32 배·잰 글자 폭으로 상자 폭에 맞춘 크기·화면 14px × 글자 배율 가운데
  // 가장 작은 것(배율 상한만 바뀐다 — 축소하면 상자 맞춤보다 먼저 작아져 이웃 상자를 덮지 않는다).
  function unitLabelSize(item, upp) {
    const fitFont = (item.w * 0.94) / Math.max(labelEm(item.label), 1)
    return Math.min(item.h * 0.32, fitFont, 14 * textScale(1 / upp) * upp)
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
    // 베이·도형은 좌우 뒤집기(look.flip)를 돌리기 앞에 건다 — 가운데 축 거울. 글자는 뒤집지도 돌리지도 않는다.
    const flip = (item.kind === 'bay' || item.kind === 'shape') && lookValue(item.look, item.kind, 'flip') === true
    const inner = el('g', { transform: `translate(${cx} ${cy}) rotate(${rot})${flip ? ' scale(-1 1)' : ''} translate(${-lw / 2} ${-lh / 2})` })
    const upp = unitsPerPx()
    // 이름표 글자는 기준 크기(고른 크기, 없으면 LABEL_PX)에 배율 글자 배율을 곱한 화면 px 다 — 확대하면 커지고 축소하면
    // 작아지며(위 TEXT_SCALE_MAX 배), TEXT_MIN_PX 아래면 이름표를 숨긴다(`// <text-scale>`).
    const ts = textScale(1 / upp)
    const caption = scaledText(item.fontSize || LABEL_PX, ts)
    const fs = caption.px * upp
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
      const name = (item.label || '영역') + (item.keepOut ? ' · 설비 금지' : '')
      const tagW = Math.min(lw, emWidth(name) * fs + fs * 0.9)
      const tagX = zoneTagX(lw, tagW, item.labelAlign)
      // 작아서 숨기는 배율에서는 꼬리표 상자도 걷는다(영역은 테두리로 잡힌다).
      if (caption.shown) {
        const tag = el('rect', { class: 'sle-zone-tag', x: tagX, y: 0, width: tagW, height: fs * 1.6, rx: 0.3 })
        inner.append(tag, text(name, tagX + fs * 0.45, fs * 0.8, fs, 'start'))
      }
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
      // 않는다). 글자는 자동이면 11, 고르면 그 기준 크기(배율을 따름)이고 기둥보다 길면 넘쳐 그린다(면색 테가 둘러 읽힌다).
      inner.append(el('rect', { class: 'sle-column', x: 0, y: 0, width: lw, height: lh }))
      if (!item.label) {
        inner.append(el('line', { class: 'sle-column-cross', x1: 0, y1: 0, x2: lw, y2: lh }))
        inner.append(el('line', { class: 'sle-column-cross', x1: lw, y1: 0, x2: 0, y2: lh }))
      }
    } else if (item.kind === 'text') {
      // 자동이면 상자에 맞추고, 크기를 골랐으면 그 기준 크기의 배율 크기로 쓴다(상자를 넘어도 그린다). 어느 쪽이든 화면
      // TEXT_MIN_PX 아래면 숨긴다.
      const value = item.label || '글자'
      const size = item.fontSize ? fs : Math.min(lh * 0.7, (lw * 0.95) / Math.max(emWidth(value), 1))
      const node = text(value, lw / 2, lh / 2, size)
      node.style.display = size / upp < TEXT_MIN_PX ? 'none' : ''
      inner.append(node)
    } else if (item.kind === 'arrow') {
      // 동선: 왼쪽에서 오른쪽으로(0°). 머리 크기는 look.head(처음 MM — 지금 그림). 선은 고르지 않으면 지금 모습(강조색 · 상자
      // 높이를 따르는 굵기 · 도면 단위 점선), 굵기를 고르면 화면 px(`is-px`)이고 선 모양도 화면 px 무늬다.
      const geo = arrowShape(lw, lh, lookValue(item.look, 'arrow', 'head'))
      const shaft = el('line', { class: 'sle-flow', ...geo.shaft })
      const width = lookValue(item.look, 'arrow', 'lineWidth')
      const style = lookValue(item.look, 'arrow', 'lineStyle')
      const color = lineInk(lookValue(item.look, 'arrow', 'line'))
      if (width) {
        shaft.classList.add('is-px')
        shaft.style.strokeWidth = String(width)
        shaft.style.strokeDasharray = lineDash(style, width) || 'none'
      } else {
        shaft.style.strokeWidth = String(Math.min(lh * 0.2, 5 * upp))
        if (style !== 'dashed') shaft.style.strokeDasharray = style === 'dotted' ? `0.01 ${Math.min(lh * 0.2, 5 * upp) * 2}` : 'none'
      }
      const point = el('polygon', { class: 'sle-flow-head', points: geo.head.map((pt) => pt.join(',')).join(' ') })
      if (color) { shaft.style.stroke = color; point.style.fill = color }
      inner.append(shaft, point)
    } else if (item.kind === 'bay') {
      // 베이(U자): 0° 는 ⊃ — 위 팔에서 굽은 곳을 돌아 아래 팔 왼쪽 끝 머리(왼쪽을 향함). 선은 화면 px 굵기(처음 2px)·모양(처음
      // 실선)·색(처음 도면 글자색), 머리는 선 색으로 채운다. 상자 전체가 잡힌다(동선과 같다).
      const geo = bayShape(lw, lh, lookValue(item.look, 'bay', 'head'))
      const width = lookValue(item.look, 'bay', 'lineWidth')
      const line = el('path', { class: 'sle-bay-line', d: geo.d })
      line.style.strokeWidth = String(width)
      const dash = lineDash(lookValue(item.look, 'bay', 'lineStyle'), width)
      if (dash) line.style.strokeDasharray = dash
      const point = el('polygon', { class: 'sle-bay-head', points: geo.head.map((pt) => pt.join(',')).join(' ') })
      const color = lineInk(lookValue(item.look, 'bay', 'line'))
      if (color) { line.style.stroke = color; point.style.fill = color }
      inner.append(line, point)
      // 가운데 글 「B<번호>」 — 두 팔 사이(머리를 비킨 틈의 가운데)를 돌린 뒤의 화면 자리에 가로로. 자동이면 틈에 맞추되 고를 수
      // 있는 가장 큰 크기(24)의 배율 크기를 넘지 않고(확대 끝에서 끝없이 커지지 않게), 고르면 기준 크기의 배율 크기. 화면
      // TEXT_MIN_PX 아래면 숨긴다.
      const number = bayCaption(item)
      const size = item.fontSize ? fs : Math.min(bayAutoSize(geo, rot, emWidth(number)), Math.max(...FONT_SIZES) * ts * upp)
      const spot = placeLocal(geo.text.x, geo.text.y, lw, lh, rot, flip)
      const node = text(number, cx + spot.x, cy + spot.y, size)
      node.classList.add('is-bay')
      node.style.display = size / upp < TEXT_MIN_PX ? 'none' : ''
      group.__flatText = node
    } else if (item.kind === 'shape') {
      // 도형(엑셀 도형처럼): 프리셋 경로(`shapePath`)를 채우기(색 · 불투명 look.fillAlpha — 0 은 채우기 없음)와 선(색 · 화면 px 굵기 ·
      // 모양)으로 그리고, 빗금을 켜면 같은 경로에 영역 빗금을 얹는다. 잡기는 경로 그대로(`sle-shape-hit` — 채우기·빗금이 없으면 테두리
      // 12px 띠만, 빈 안쪽을 끌면 고르기 사각형)이고 상자의 빈 귀는 잡히지 않는다. 이름표는 가운데에 돌리지 않고 가로로 — 자동이면
      // 상자에 맞추되 고를 수 있는 가장 큰 크기(24)의 배율 크기까지, 화면 TEXT_MIN_PX 아래면 숨긴다.
      const preset = shapeOf(item.look)
      const adj = shapeAdj(item.look)
      const geo = shapePath(preset, lw, lh, adj)
      const alpha = lookValue(item.look, 'shape', 'fillAlpha')
      const body = el('path', { class: 'sle-shape-body', d: geo.d, 'fill-rule': geo.rule })
      body.style.fill = shapeFillInk(shapeFillOf(item.color))
      body.style.fillOpacity = String(alpha / 100)
      const stroke = shapeLineInk(lookValue(item.look, 'shape', 'line'), shapeFillOf(item.color))
      if (stroke) {
        const width = lookValue(item.look, 'shape', 'lineWidth')
        body.style.stroke = stroke
        body.style.strokeWidth = String(width)
        const dash = lineDash(lookValue(item.look, 'shape', 'lineStyle'), width)
        if (dash) body.style.strokeDasharray = dash
      } else body.style.stroke = 'none'
      inner.append(body)
      if (item.hatch) inner.append(el('path', { class: 'sle-shape-hatch', d: geo.d, 'fill-rule': geo.rule, fill: 'url(#sle-hatch)' }))
      inner.append(el('path', { class: alpha > 0 || item.hatch ? 'sle-shape-hit' : 'sle-shape-hit is-hollow', d: geo.d, 'fill-rule': geo.rule }))
      if (item.label) {
        const size = item.fontSize ? fs
          : Math.min(item.h * 0.45, (item.w * 0.9) / Math.max(emWidth(item.label), 1), Math.max(...FONT_SIZES) * ts * upp)
        const node = text(item.label, cx, cy, size)
        node.classList.add('is-grab')
        node.style.display = size / upp < TEXT_MIN_PX ? 'none' : ''
        group.__flatText = node
      }
      drawAdjusts(group, item, preset, adj, { lw, lh, rot, flip, cx, cy, upp })
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
      // 글자 크기를 골랐으면 모든 줄을 그 크기로 쓴다(맞추거나 숨기지 않는다). 아니면 줄마다 블록에 맞춘다
      // (`blockTextLayout` — 단축 줄은 따로 작아지거나 두 줄로 나뉜다).
      const { main, short } = blockLines(item)
      const rows = item.fontSize
        ? [...main, ...(short ? [short] : [])].map((value, k) => ({ text: value, size: fs, role: k === 0 ? 'head' : (k < main.length ? 'sub' : 'short') }))
        : blockTextLayout(main, short, Boolean(off), lw, lh, upp, emWidth, 13 * ts)
      const total = rows.reduce((sum, row) => sum + row.size * 1.3, 0)
      let y = lh / 2 - total / 2
      for (const row of rows) {
        const node = text(row.text, lw / 2, y + (row.size * 1.3) / 2, row.size)
        y += row.size * 1.3
        node.classList.add(row.role === 'head' ? 'is-head' : 'is-sub')
        if (row.role === 'short') node.classList.add('is-short')
        node.style.display = row.size / upp < TEXT_MIN_PX ? 'none' : ''
        inner.append(node)
      }
    }
    shape.append(inner)
    // 돌리지 않는 가운데 글(베이 「B<번호>」·도형 이름표) — 돌리는 그룹 밖에 가로로.
    if (group.__flatText) {
      shape.append(group.__flatText)
      group.__flatText = null
    }
    if (item.kind === 'column' && item.label && caption.shown) shape.append(text(item.label, cx, cy, fs))
    // 반입구·문·동선의 이름표는 돌리지 않는다(세로 글자가 되지 않게). 상자 바깥, 방 쪽(반입구·문)이나
    // 옆(동선)에 가로로 쓴다. 0° 일 때 방은 위쪽이다(아래 변이 벽).
    if (item.label && caption.shown && (item.kind === 'shutter' || item.kind === 'door' || item.kind === 'arrow')) {
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
    if (tip) tip.textContent = markTitle(item)
  }

  // 도형의 노란 모양 조절 손잡이(`sle-adjust` — 화면 HANDLE_PX 동그라미, 하나만 고른 도형에서만 보인다 — CSS). 제자리 손잡이
  // 자리(`shapeHandles`)를 뒤집기·돌림으로 화면 자리에 옮기고(`placeLocal` — 참 자리는 data-tx·ty), 크기 손잡이와 겹치면 비켜
  // 그린다(`nudgeHandle`). 커서는 돌린 뒤 값을 읽는 축이다.
  function drawAdjusts(group, item, preset, adj, at) {
    const box = group.querySelector('.sle-adjusts')
    if (!box) return
    const radius = (HANDLE_PX / 2) * at.upp
    const hs = HANDLE_PX * at.upp
    const top = at.cy - item.h / 2
    const centers = []
    for (const [hx, hy] of [[0, 0], [0.5, 0], [1, 0], [1, 0.5], [1, 1], [0.5, 1], [0, 1], [0, 0.5]]) {
      // 작은 상자에서 감춘 변 가운데 손잡이(`positionHandles`)는 비킬 까닭이 없다.
      if ((hx === 0.5 && item.w < hs * 3) || (hy === 0.5 && item.h < hs * 3)) continue
      centers.push({ x: item.x + item.w * hx, y: top + item.h * hy })
    }
    box.replaceChildren(...shapeHandles(preset, at.lw, at.lh, adj).map((handle) => {
      const spot = placeLocal(handle.x, handle.y, at.lw, at.lh, at.rot, at.flip)
      const across = (at.rot || 0) % 180 ? (handle.axis === 'x' ? 'y' : 'x') : handle.axis
      const truth = { x: at.cx + spot.x, y: at.cy + spot.y }
      const drawn = nudgeHandle(truth, across, centers, hs * 1.3, { x: at.cx, y: at.cy })
      const node = el('circle', { class: 'sle-adjust', cx: drawn.x, cy: drawn.y, r: radius })
      node.dataset.index = String(handle.index)
      node.dataset.tx = String(truth.x)
      node.dataset.ty = String(truth.y)
      node.style.cursor = across === 'x' ? 'ew-resize' : 'ns-resize'
      const tip = el('title')
      tip.textContent = `모양 조절 — ${SHAPE_PRESETS[preset].words[handle.index]}`
      node.append(tip)
      return node
    }))
  }

  function appendHandles(group) {
    // 키보드 초점 테 — 상자 밖으로 띄운 강조색 테이고 초점이 있을 때만 보인다(CSS). 손잡이 아래에 깐다.
    group.append(el('rect', { class: 'sle-focus-ring', rx: 0.6 }))
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
    // 「호기 정보」 창 필터에 맞는 호기의 테 — 보기·편집 모두(필터는 읽기만이다). 보일지는 class(`paintFilter`)와 CSS 가 정한다.
    group.append(el('rect', { class: 'sle-filter-ring', rx: 0.8 }))
    // 호기는 키보드로도 고른다 — Tab 이 상자마다 서고 Enter·Space 가 누르기와 같다(`host.onkeydown`). 이름은 풍선 글
    // (<title>)이다. 보기에서 기준일에 숨은 상자(visibility)는 초점도 받지 않는다.
    group.setAttribute('tabindex', '0')
    group.setAttribute('role', 'button')
    appendHandles(group)
    paintUnit(group, item)
    position(group, item)
    group.__tipAt = `${S.asOf}|${S.dataAsOf}`
    S.groups.set(item.id, group)
    paintFilter(group, item.id)
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
    const code = `${look.fill}|${look.ink}|${+st.visible}${+st.real}${+st.exitPlan}${+st.stopped}${+st.flag}${+st.offline}${+covered}|${item.layer || ''}${+Boolean(item.dim)}`
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
    // 「필요 단축」 — 표시된 호기·흐릴 호기(파이썬이 정해 보낸다 — 공정 칩 논리는 JS 에 없다).
    group.classList.toggle('is-layer', Boolean(item.layer))
    group.classList.toggle('is-dim', Boolean(item.dim))
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
    } else if (!VIEW) {
      // 편집에서는 도면 요소도 호기처럼 Tab 으로 가서 Enter·Space 로 고른다(`host.onkeydown`).
      group.setAttribute('tabindex', '0')
      group.setAttribute('role', 'button')
    }
    appendHandles(group)
    // 도형의 노란 모양 조절 손잡이는 크기 손잡이 위에 깐다(겹치면 이것이 잡힌다). 편집에만 있다.
    if (item.kind === 'shape' && !VIEW) group.append(el('g', { class: 'sle-adjusts' }))
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
    // 칩은 키보드로도 놓고 고른다 — 이름이 단추다(칩 전체가 단추면 「×」 단추가 단추 안에 든다). Enter 는 끌어 놓기와 같다 —
    // 지금 보이는 도면 가운데에 놓는다(고른 칩 여럿 가운데 하나면 함께, Alt 는 정렬선에 붙이지 않음). Space 는 누르기와 같다 —
    // 그 칩 하나를 고르고 Ctrl(⌘)은 더하거나 빼고 Shift 는 범위다.
    text.tabIndex = 0
    text.setAttribute('role', 'button')
    text.setAttribute('aria-label', [
      lead.group ? `Main 설비 ${lead.group}` : lead.label, size.textContent, lead.floorless ? '층 미정' : '',
      list.some((m) => m.isNew) ? '신규' : '',
    ].filter(Boolean).join(' · ') + ' — Enter 도면에 놓기 · Space 고르기')
    text.onkeydown = (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      event.preventDefault()
      event.stopPropagation()
      if (event.repeat || S.drag) return
      if (event.key === ' ') pickChip(lead, list, { ctrl: event.ctrlKey || event.metaKey, shift: event.shiftKey })
      else placeChipByKey(lead, list, event.altKey)
    }
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
      // 낭독기에는 글자 「×」 가 아니라 할 일과 그 호기 이름이다.
      remove.setAttribute('aria-label', `${lead.group || lead.label} 추가 취소`)
      remove.onpointerdown = (event) => event.stopPropagation()
      remove.onclick = () => removeItems([lead])
      chip.append(remove)
    }
    paintChipFilter(chip)
    return chip
  }

  // 다시 그리면 상자·칩이 새 노드라 초점을 쥐었던 노드가 사라진다(초점이 BODY 로 빠진다). 그리기 전에 초점이 어디였는지
  // 적어 두고(`focusSpot`) 그린 뒤 같은 것(같은 id)의 새 노드에 돌려준다(`restoreFocus`) — 키보드로 고르고 옮기고 놓는 동안
  // 초점을 잃지 않게.
  function focusSpot() {
    const node = host.getRootNode().activeElement
    if (!node || node === svg || !host.contains(node)) return null
    const item = canvasItemOf(node)
    if (item) return { kind: 'item', id: item.dataset.id }
    const chip = node.closest ? node.closest('.sle-chip') : null
    if (!chip || chip.parentNode !== trayList) return null
    const shown = [...trayList.children].filter((c) => !c.hidden)
    return { kind: node.classList.contains('sle-chip-remove') ? 'remove' : 'chip', id: chip.dataset.id, index: shown.indexOf(chip) }
  }
  function restoreFocus(spot) {
    if (!spot) return
    const now = host.getRootNode().activeElement
    if (now && now !== svg && host.contains(now)) return
    const focus = (node) => node.focus({ preventScroll: true })
    if (spot.kind === 'item') {
      // 트레이로 뺐거나 지운 것이면 도면에 둔다(Delete 를 이어 누를 수 있다).
      const group = S.groups.get(spot.id)
      focus(group && group.hasAttribute('tabindex') ? group : svg)
      return
    }
    const shown = [...trayList.children].filter((c) => !c.hidden)
    const chip = shown.find((c) => c.dataset.id === spot.id)
    if (chip) {
      focus((spot.kind === 'remove' && chip.querySelector('.sle-chip-remove')) || chip.querySelector('.sle-chip-name'))
      return
    }
    // 그 칩이 서랍에서 사라졌으면(「×」 로 추가를 취소했다) 같은 자리의 이웃 칩(뒤 칩, 없으면 앞 칩 — 이름 단추가 초점을
    // 받지 않는 칩은 건너뛴다), 칩이 없으면 검색 칸에 둔다 — 초점이 BODY 로 빠지면 Tab 이 문서 처음부터 다시 돈다.
    const names = shown.map((c) => c.querySelector('.sle-chip-name'))
    const at = Math.max(spot.index, 0)
    const able = (i) => Boolean(names[i] && names[i].hasAttribute('tabindex'))
    let pick = -1
    for (let i = at; i < names.length && pick < 0; i += 1) if (able(i)) pick = i
    for (let i = Math.min(at, names.length) - 1; i >= 0 && pick < 0; i -= 1) if (able(i)) pick = i
    if (pick >= 0) focus(names[pick])
    else focus(trayBox.hidden ? svg : traySearch)
  }

  // 호기 아래 층(`sle-zones`)에 그리는 요소 — 영역과 도형(방·벽을 그려도 호기를 덮지 않는다).
  const onZoneLayer = (item) => item.kind === 'zone' || item.kind === 'shape'
  function renderItems() {
    // 서랍 목록을 비웠다 다시 채우는 동안 목록 높이가 줄어 브라우저가 서랍 스크롤을 맨 위로 잘라 낸다. 놓은 뒤에도
    // 보던 자리에서 이어 놓게 그 자리를 기억했다 되돌린다(2026-10-08 사용자 요청).
    const trayTop = trayScroll.scrollTop
    const focused = focusSpot()
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
      } else (onZoneLayer(item) ? zonesLayer : marksLayer).append(buildMark(item))
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
    trayScroll.scrollTop = trayTop
    // 보기 화면은 기준일이 바뀌어도 바뀐 호기만 칠하도록 경계 날짜 목록을 새로 만든다.
    if (VIEW && !FAB) buildEvents()
    markSelection()
    markOverlaps()
    showSummary()
    restoreFocus(focused)
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
    else if (flipped.length && ASOF_PINNED) drawShortBadges()
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
    && (o.layer || '') === (n.layer || '') && Boolean(o.dim) === Boolean(n.dim)
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
        || lookText(o.look) !== lookText(item.look)
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
    // Main 설비명도 범위를 따라간다 — 자리·크기·배율이 바뀌는 길이 모두 여기를 지난다. 견주기 꼬리표도 같다.
    drawGroupNames()
    drawCompare()
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
    } else if (!VIEW && chosen.length === 1 && isMark(chosen[0]) && onZoneLayer(chosen[0])) {
      proxyHandles(chosen[0])
    }
    const rect = S.drag && S.drag.mode === 'marquee' ? S.drag.rect : null
    if (rect) overlay.append(el('rect', { class: 'sle-marquee', x: rect.x0, y: rect.t0, width: rect.x1 - rect.x0, height: rect.t1 - rect.t0 }))
  }

  // 호기 아래 층(영역·도형)에서 하나만 고른 것의 손잡이(크기 여덟 · 도형 노란 모양 조절)를 맨 위 층(`sle-overlay`)에 다시 세운다 —
  // 호기가 덮은 귀·변의 손잡이도 잡힌다(엑셀처럼 고른 것의 손잡이는 늘 위). 제 그룹 안의 손잡이는 CSS 가 감추고, 자리·크기·풍선은
  // 그 손잡이(`positionHandles`·`drawAdjusts`)를 그대로 옮긴다. 누르면 data-for 의 요소 손잡이를 누른 것과 같다(`onpointerdown`).
  function proxyHandles(item) {
    const group = S.groups.get(item.id)
    if (!group) return
    for (const handle of group.querySelectorAll('.sle-handle, .sle-adjust')) {
      if (handle.style.display === 'none') continue
      const proxy = handle.cloneNode(true)
      proxy.classList.add(handle.classList.contains('sle-adjust') ? 'sle-proxy-adjust' : 'sle-proxy-handle')
      proxy.dataset.for = item.id
      overlay.append(proxy)
    }
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
      // 키보드로 고르는 상자(초점을 받는 호기·요소)는 골라졌는지를 낭독기에도 알린다. FAB 보기의 층 블록은 여는 단추다.
      if (!(VIEW && FAB) && group.hasAttribute('tabindex')) setAttr(group, 'aria-pressed', String(selected || together.has(id)))
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
    // 좁은 FAB 도구 줄에서는 요약도 말줄임으로 줄 수 있다(`fitToolbar`) — 풍선에 온 글.
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
      look: cleanLook(m.look, m.kind),
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
      inspectorName.textContent = markTitle(single)
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
      markFontSize.replaceChildren(new Option('자동', ''), ...FONT_SIZES.map((size) => new Option(String(size), String(size))))
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
    syncTurns(chosen, mark)
    syncLineProps(chosen)
    syncShapeProps(chosen)
    if (mark) {
      // 베이는 이름 칸이 「번호」 이고 칸 앞에 고정 글 「B」 가 선다(그릴 때 늘 붙는다 — 칸에는 번호만).
      const bay = mark.kind === 'bay'
      setText(markNameWord, bay ? '번호' : '이름')
      bayPrefix.hidden = !bay
      markLabel.maxLength = bay ? 12 : 40
      setAttr(markLabel, 'aria-label', bay ? '베이 번호 — 앞에 B 가 붙습니다' : '요소 이름')
      if (!isFocused(markLabel)) markLabel.value = mark.label || ''
      markFontSize.value = mark.fontSize ? String(mark.fontSize) : ''
      markFontColor.value = mark.fontColor || ''
      for (const node of zoneOnly) node.hidden = mark.kind !== 'zone'
      markColor.value = mark.color || 'gray'
      markBorder.value = pickOr(mark.borderStyle, BORDER_STYLES)
      markAlign.value = pickOr(mark.labelAlign, LABEL_ALIGNS)
      markHatch.checked = Boolean(mark.hatch)
      markKeepOut.checked = Boolean(mark.keepOut)
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
            : `${withJosa(mark.link || '연결 층', '을')} 엽니다`
      }
    }
  }
  // ---------------------------------------------------------------- 동선·베이의 선·머리(선택 칸)
  // 고른 것 가운데 동선·베이(`lined`)가 있으면 선택 칸에 「머리 크기」(3×3 갤러리)·선 색·굵기·선 모양과 베이의 좌우·상하
  // 뒤집기가 선다(2026-11-03 사용자 요청 — 엑셀처럼). 여럿이면 모두에 걸고 되돌리기 한 번이다. 값이 서로 다르면 「여러 값」.
  const MIXED = '__mixed'
  const HEAD_WIDTH_WORDS = { S: '좁게', M: '보통', L: '넓게' }
  const HEAD_LENGTH_WORDS = { S: '짧게', M: '보통', L: '길게' }
  const LINE_COLOR_NAMES = { accent: '강조색', ink: '진하게', ...ZONE_COLOR_NAMES }
  const isLined = (m) => isMark(m) && (m.kind === 'arrow' || m.kind === 'bay')
  const headAria = (head) => `너비 ${HEAD_WIDTH_WORDS[head[0]]} · 길이 ${HEAD_LENGTH_WORDS[head[1]]}`
  const headShort = (head) => (head === 'MM' ? '보통' : `${HEAD_WIDTH_WORDS[head[0]]}·${HEAD_LENGTH_WORDS[head[1]]}`)
  // 갤러리·단추의 작은 동선 그림(24×12 — 몸통은 실선, 머리는 그 크기의 꼴).
  function drawHeadIcon(svgNode, head) {
    const geo = arrowShape(22, 6, head)
    const shaft = el('line', { class: 'ico-line', x1: 1 + geo.shaft.x1, y1: 6, x2: 1 + geo.shaft.x2, y2: 6 })
    const tip = el('polygon', { class: 'ico-fill', points: geo.head.map(([x, y]) => `${1 + x},${3 + y}`).join(' ') })
    svgNode.replaceChildren(shaft, tip)
  }
  function fillLineOptions() {
    if (lineColor.options.length) return
    const mixed = () => {
      const option = new Option('여러 값', MIXED)
      option.disabled = true
      option.hidden = true
      return option
    }
    lineColor.replaceChildren(mixed(), ...LINE_COLORS.map((key) => new Option(LINE_COLOR_NAMES[key] || key, key)))
    lineWidth.replaceChildren(mixed(), new Option('기본', ''), ...LINE_WIDTHS.map((w) => new Option(`${w}px`, String(w))))
    lineStyle.prepend(mixed())
    headGallery.replaceChildren(...ARROW_HEADS.map((head) => {
      const cell = el('svg', { viewBox: '0 0 24 12', 'aria-hidden': 'true' })
      drawHeadIcon(cell, head)
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'sle-head-cell'
      button.dataset.head = head
      button.setAttribute('aria-label', headAria(head))
      button.title = headAria(head)
      button.append(cell)
      return button
    }))
  }
  // 고른 동선·베이가 모두 같은 값이면 그 값, 다르면 null. 처음 값이 없는 키(동선 굵기 「기본」)는 ''.
  const sharedLook = (lined, key) => {
    const values = new Set(lined.map((m) => {
      const value = lookValue(m.look, m.kind, key)
      return value === undefined ? '' : value
    }))
    return values.size === 1 ? [...values][0] : null
  }
  function syncLineProps(chosen) {
    const lined = chosen.filter(isLined)
    lineProps.hidden = !lined.length
    if (!lined.length) {
      headGallery.hidden = true
      headToggle.setAttribute('aria-expanded', 'false')
      return
    }
    fillLineOptions()
    const head = sharedLook(lined, 'head')
    drawHeadIcon(headNow, head || 'MM')
    setText(headWord, head ? headShort(head) : '여러 값')
    setAttr(headToggle, 'aria-label', `머리 크기 — ${head ? headAria(head) : '여러 값'}`)
    for (const cell of headGallery.children) setAttr(cell, 'aria-pressed', String(cell.dataset.head === head))
    const color = sharedLook(lined, 'line')
    lineColor.value = color === null ? MIXED : color
    const width = sharedLook(lined, 'lineWidth')
    lineWidth.value = width === null ? MIXED : String(width)
    const style = sharedLook(lined, 'lineStyle')
    lineStyle.value = style === null ? MIXED : style
  }
  // 고른 동선·베이 모두의 모양 값을 바꾼다(patch 의 null 은 처음 값으로). 그 종류가 받지 않는 키는 빠진다(`cleanLook`).
  // 바뀐 것이 있으면 되돌리기 한 번.
  function setLooks(patch, only) {
    const lined = selectedItems().filter((m) => isLined(m) && (!only || only(m)))
    const ops = []
    for (const m of lined) {
      const next = patchLook(m.look, patch, m.kind)
      if (lookText(next) === lookText(m.look)) continue
      ops.push({ op: 'set', id: m.id, before: snapshot(m) })
      m.look = next
    }
    if (!ops.length) { syncInspector(); return }
    pushUndo(ops)
    for (const op of ops) position(S.groups.get(op.id), S.items.get(op.id))
    drawSelectionBox()
    updateStatus()
  }
  // 고른 것 가운데 뒤집을 수 있는 것(베이 · 비대칭 도형 — `canFlip`)을 모두 뒤집는다 — 좌우(h)는 look.flip 만, 상하(v)는 180° 돌림
  // + 좌우 뒤집기(같은 상자). 되돌리기 한 번. 뒤집은 것이 있으면 참(단축키가 키를 막을지 가른다). 뒤집기는 서식이 아니다(서식 붓이
  // 옮기지 않는다 — `// <format-paint>`).
  const isBay = (m) => isMark(m) && m.kind === 'bay'
  const isShape = (m) => isMark(m) && m.kind === 'shape'
  const turnsShape = (m) => isShape(m) && SHAPE_PRESETS[shapeOf(m.look)].turn
  const canFlip = (m) => onCanvas(m) && (isBay(m) || turnsShape(m))
  function flipMarks(axis) {
    const list = selectedItems().filter(canFlip)
    if (!list.length) return false
    const ops = list.map((m) => ({ op: 'set', id: m.id, before: snapshot(m) }))
    for (const m of list) {
      m.look = cleanLook({ ...(m.look || {}), flip: lookValue(m.look, m.kind, 'flip') !== true }, m.kind)
      if (axis === 'v') m.rot = ((m.rot || 0) + 180) % 360
    }
    pushUndo(ops)
    for (const m of list) position(S.groups.get(m.id), m)
    drawSelectionBox()
    updateStatus()
    return true
  }
  // 돌리기·뒤집기 줄 — 90° 돌리기는 돌릴 수 있는 요소 하나를 골랐을 때(대칭 도형은 돌려도 같아 숨긴다), 뒤집기 둘은 고른 것 가운데
  // 뒤집을 것이 하나라도 있을 때 선다(대칭 도형만이면 숨긴다 — 2026-11-04 Space 결정 보드 답, 찾기 쉽게 이름표 칸 바로 밑).
  function syncTurns(chosen, mark) {
    const rotates = Boolean(mark && MARK_KINDS[mark.kind].rotatable && (!isShape(mark) || turnsShape(mark)))
    markRotate.hidden = !rotates
    const flips = chosen.some(canFlip)
    for (const button of flipButtons) button.hidden = !flips
    turnsRow.hidden = !rotates && !flips
  }

  // ---------------------------------------------------------------- 도형 서식(선택 칸)
  // 고른 것 가운데 도형이 있으면 선택 칸에 「도형」(바꾸기 갤러리)·모양 조절(한 프리셋일 때 — 숫자 %)·채우기 색·투명도(엑셀처럼 100 −
  // 불투명)·선 색·굵기·선 모양·빗금·뒤집기가 선다(2026-11-03 사용자 요청). 여럿이면 모두에 걸고 되돌리기 한 번이다. 값이 서로
  // 다르면 「여러 값」.
  const SHAPE_FILL_NAMES = { ...ZONE_COLOR_NAMES, ink: '진하게', surface: '바탕' }
  const SHAPE_LINE_NAMES = { auto: '자동', none: '없음', ink: '진하게', ...ZONE_COLOR_NAMES }
  const sharedOf = (list, read) => {
    const values = new Set(list.map(read))
    return values.size === 1 ? [...values][0] : null
  }
  // 갤러리·단추의 작은 도형 그림(16×16, 처음 모양 조절 값).
  function drawShapeIcon(svgNode, key) {
    const geo = shapePath(key, 14, 12, SHAPE_PRESETS[key].adj.map((spec) => spec[2]))
    svgNode.replaceChildren(el('path', { class: 'ico-shape', d: geo.d, 'fill-rule': geo.rule, transform: 'translate(1 2)' }))
  }
  function shapeCells(onCell) {
    return SHAPE_KEYS.map((key) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'sle-shape-cell'
      button.dataset.shape = key
      button.title = SHAPE_PRESETS[key].name
      const icon = el('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true' })
      drawShapeIcon(icon, key)
      const word = document.createElement('span')
      word.textContent = SHAPE_PRESETS[key].name
      button.append(icon, word)
      onCell(button, key)
      return button
    })
  }
  function fillShapeOptions() {
    if (shapeFill.options.length) return
    const mixed = () => {
      const option = new Option('여러 값', MIXED)
      option.disabled = true
      option.hidden = true
      return option
    }
    shapeFill.replaceChildren(mixed(), ...SHAPE_FILLS.map((key) => new Option(SHAPE_FILL_NAMES[key] || key, key)))
    shapeLine.replaceChildren(mixed(), ...SHAPE_LINES.map((key) => new Option(SHAPE_LINE_NAMES[key] || key, key)))
    shapeWidth.replaceChildren(mixed(), ...LINE_WIDTHS.map((w) => new Option(`${w}px`, String(w))))
    shapeStyle.prepend(mixed())
    shapeGallery.replaceChildren(...shapeCells((button, key) => {
      button.setAttribute('aria-label', `도형 바꾸기 — ${SHAPE_PRESETS[key].name}`)
    }))
  }
  function closeShapeGallery() {
    shapeGallery.hidden = true
    shapeSwap.setAttribute('aria-expanded', 'false')
  }
  function syncShapeProps(chosen) {
    const shapes = chosen.filter(isShape)
    shapeProps.hidden = !shapes.length
    if (!shapes.length) { closeShapeGallery(); return }
    fillShapeOptions()
    const preset = sharedOf(shapes, (m) => shapeOf(m.look))
    drawShapeIcon(shapeNow, preset || 'rect')
    setText(shapeWord, preset ? SHAPE_PRESETS[preset].name : '여러 값')
    setAttr(shapeSwap, 'aria-label', `도형 — ${preset ? SHAPE_PRESETS[preset].name : '여러 값'} · 눌러서 바꾸기`)
    for (const cell of shapeGallery.children) setAttr(cell, 'aria-pressed', String(cell.dataset.shape === preset))
    // 모양 조절 — 고른 도형이 모두 같은 프리셋일 때만(값의 뜻이 프리셋마다 다르다).
    const specs = preset ? SHAPE_PRESETS[preset].adj : []
    shapeAdjRows.forEach((row, k) => {
      row.hidden = k >= specs.length
      if (row.hidden) return
      setText(row.querySelector('.sle-shape-adj-word'), SHAPE_PRESETS[preset].words[k])
      const input = shapeAdjInputs[k]
      input.min = String(Math.round(specs[k][0] * 100))
      // 상한은 고른 도형 상자 가운데 가장 낮은 것, 값은 그린 값(`fitAdj` — 칸으로 상자를 좁혀 상한이 줄었으면 묶인 값)이다.
      input.max = String(Math.round(Math.min(...shapes.map((m) => adjTop(preset, k, ...shapeBox(m)))) * 100))
      if (isFocused(input)) return
      const value = sharedOf(shapes, (m) => fitAdj(preset, shapeAdj(m.look), ...shapeBox(m))[k])
      input.value = value === null ? '' : String(Math.round(value * 100))
      input.placeholder = value === null ? '여러 값' : ''
    })
    const fill = sharedOf(shapes, (m) => shapeFillOf(m.color))
    shapeFill.value = fill === null ? MIXED : fill
    if (!isFocused(shapeClear)) {
      const alpha = sharedOf(shapes, (m) => lookValue(m.look, 'shape', 'fillAlpha'))
      shapeClear.value = alpha === null ? '' : String(100 - alpha)
      shapeClear.placeholder = alpha === null ? '여러 값' : ''
    }
    const line = sharedOf(shapes, (m) => lookValue(m.look, 'shape', 'line'))
    shapeLine.value = line === null ? MIXED : line
    const width = sharedOf(shapes, (m) => lookValue(m.look, 'shape', 'lineWidth'))
    shapeWidth.value = width === null ? MIXED : String(width)
    const style = sharedOf(shapes, (m) => lookValue(m.look, 'shape', 'lineStyle'))
    shapeStyle.value = style === null ? MIXED : style
    const hatch = sharedOf(shapes, (m) => Boolean(m.hatch))
    shapeHatch.checked = hatch === true
    shapeHatch.indeterminate = hatch === null
  }
  // 고른 도형 모두의 모양 값(patch — 값 null 은 처음 값으로, 함수면 도형마다)과 요소 칸(fields — 채우기 색·빗금)을 바꾼다. 바뀐 것이
  // 있으면 되돌리기 한 번.
  function setShapes(patch, fields = {}) {
    const ops = []
    for (const m of selectedItems().filter(isShape)) {
      const next = patchLook(m.look, typeof patch === 'function' ? patch(m) : patch, 'shape')
      const moved = Object.entries(fields).some(([key, value]) => m[key] !== value)
      if (lookText(next) === lookText(m.look) && !moved) continue
      ops.push({ op: 'set', id: m.id, before: snapshot(m) })
      m.look = next
      Object.assign(m, fields)
    }
    if (!ops.length) { syncInspector(); return }
    pushUndo(ops)
    for (const op of ops) position(S.groups.get(op.id), S.items.get(op.id))
    drawSelectionBox()
    updateStatus()
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
    if (isMark(item)) return `선택 ${MARK_KINDS[item.kind] ? markTitle(item) : item.kind}`
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
      renderSheet()
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
    // 스크롤 고정 중이면 위 「저장 안 한 배치」 상자가 화면 밖이다 — 맨 앞에 한 줄.
    if (lockNote()) add(lockNote())
    // 든 서식 붓(한 번 · 잠금).
    if (S.paint) {
      add(S.paint.sticky
        ? '서식 붓 잠금 — 누를 때마다 붙입니다(빈 곳을 끌면 그 안 전부) · Esc·붓 단추로 끝'
        : '서식 붓 — 붙일 것을 누르세요(빈 곳을 끌면 그 안 전부) · Esc 끝')
    }
    // 방금 한 일의 한 줄(복사·붙여넣기) — 다음 고르기·편집에서 지운다.
    if (S.flash) add(S.flash)
    if (chosen.length > 1) {
      add('선택 ', `${chosen.length}개`)
      add(`${expanded(chosen).length}개가 함께 움직입니다 — Shift/Ctrl+클릭으로 더하거나 빼기 · Esc 선택 풀기`)
      const sized = sizeNote(expanded(chosen))
      if (sized) add(sized)
    } else if (item && isMark(item)) {
      add('선택 ', `${markKindName(item)}${item.kind === 'bay' ? ` ${bayCaption(item)}` : item.label ? ` ${item.label}` : ''}`)
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
      if (hidden.length) add(`숨은 모듈(레이아웃표시 N·도면 이탈) ${withJosa(hidden.join(', '), '은')} 그리지 않고 제 칸(점선)을 비워 둡니다 — 묶음과 함께 옮겨집니다`)
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
      // 단축키 전부는 왼쪽 칸 「도움말」 이다(상태 줄이 여러 줄로 늘어 도면이 밀리지 않게).
      add(FAB
        ? '층 블록·영역·글자를 끌어 옮기고 손잡이로 크기를 바꿉니다 · 단축키는 왼쪽 칸 「도움말」'
        : '호기·요소를 끌어 옮기고 손잡이로 크기를 바꿉니다 · 빈 곳을 끌면 여러 개 · 단축키는 왼쪽 칸 「도움말」')
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
    areaNote.textContent = S.note || (data.canvasEditable === false ? (data.canvasLock || '') : '')
    syncInspector()
    syncFormatPanel()
    renderSheet()
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

  // Shift/Ctrl+클릭·Ctrl+Enter 는 고른 것에 더하거나 뺀다. 모듈 묶음은 묶음째 — 그 묶음이 골라져 있으면 뺀다.
  function toggleSelected(item) {
    const ids = new Set(S.selection)
    const bundle = (moduleMembers(item) || [item]).map((m) => m.id)
    const had = bundle.some((id) => ids.has(id))
    for (const id of bundle) ids.delete(id)
    if (!had) ids.add(item.id)
    setSelection([...ids], had ? null : item.id)
  }

  // 키 눌림·초점을 받은 노드가 도면의 호기·요소 상자(초점을 받는 `.sle-item`)면 그 상자. 첫 그리기(`renderItems`)보다 뒤에
  // 적혀 있어 끌어올려지는 함수 선언이다.
  function canvasItemOf(node) {
    const group = node && node !== svg && node.closest ? node.closest('.sle-item') : null
    return group && svg.contains(group) && group.hasAttribute('tabindex') ? group : null
  }

  // 오른쪽 미배치 칸을 펴고 접는다(`setPanelOpen` — 넓은 화면은 기억, 좁은 화면 겹침 서랍은 한 번에 하나). 좁은 화면에서
  // 접으면 서랍 몫으로 옮긴 화면을 제자리로 돌린다.
  function setDrawer(open) {
    setPanelOpen('right', open)
  }

  // 좁은 화면 겹침 서랍에서 놓은 호기가 서랍 아래에 들었으면 화면을 옮겨 꺼내 보인다(서랍은 열어 둔다 — 이어서 놓을 수
  // 있게). 옮길 수 있는 만큼만 옮긴다(trayReserve). 위아래로 서랍과 겹치지 않으면 그대로 둔다. 넓은 화면의 오른쪽 칸은
  // 도면을 덮지 않아 할 일이 없다.
  function revealFromTray(list) {
    if (!host.classList.contains('is-narrow') || !S.drawerOpen || trayBox.hidden) return
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
    // 층 캔버스를 고치지 않는 편집기(가정 설비 시나리오 — 공용 값). 칸은 꺼져 있지만 옛 단축키·되돌리기
    // 길도 막는다. 서버도 적용의 캔버스 값을 거부한다(두 겹).
    if (data.canvasEditable === false) { areaW.value = W(); areaH.value = H(); return }
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
    const fromTray = Boolean(source.closest && source.closest('.sle-tray')) && host.classList.contains('is-narrow')
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

  // 칩에서 Enter — 끌어 놓기의 키보드 길. 놓는 점은 지금 보이는 도면 가운데(열린 서랍이 덮은 오른쪽은 빼고)이고, 고른 칩
  // 여럿 가운데 하나면 끌 때처럼 함께 놓는다. 놓았으면 초점을 놓은 호기로 옮긴다 — 이어서 방향키로 자리를 다듬는다.
  // 못 놓았으면(편집 영역보다 큼 — 까닭은 편집 영역 칸 알림) 초점은 칩에 남는다.
  function placeChipByKey(lead, list, free) {
    const picked = pickedTrayEntries()
    const together = picked.length > 1 && picked.some((entry) => entry.lead.id === lead.id)
    const p = { x: S.view.x + Math.max(viewW() - trayReserve(), 0) / 2, top: S.view.top + viewH() / 2 }
    if (together) placeManyFromTray(lead, picked, p, free)
    else placeFromTray(lead, list, p, undefined, free)
    if (!onCanvas(lead) && !list.some(onCanvas)) return
    const group = S.groups.get(S.selected) || [...S.selection].map((id) => S.groups.get(id)).find(Boolean)
    if (group) group.focus({ preventScroll: true })
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
      const who = name || lead.group || lead.label
      S.note = `${who} (${footprint.w}×${footprint.h})${josaOf(who, '이')} 편집 영역 ${W()}×${H()} 보다 커서 놓지 않았습니다 — 영역을 넓힌 뒤 놓으세요`
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
  function addMark(kind, at, free, preset) {
    const spec = MARK_KINDS[kind]
    if (!spec) return
    // 도형은 프리셋마다 넣는 크기가 다르다(`SHAPE_PRESETS`).
    const shape = kind === 'shape' ? presetOf(preset) : null
    const [w, h] = shape ? SHAPE_PRESETS[shape].size : spec.size
    S.seq += 1
    const id = `MK-${Date.now().toString(36)}-${S.seq}`
    const center = at || { x: S.view.x + viewW() / 2, top: S.view.top + viewH() / 2 }
    const spot = at ? dropSpot(at, w, h, free) : { x: snapDelta(center.x - w / 2), y: snapDelta(H() - center.top - h / 2) }
    // 새 층 블록은 아직 블록이 없는 첫 층을 가리킨다(모두 있으면 첫 층). 선택 칸에서 바꾼다 — 블록은 연결이 필수다.
    const link = kind === 'block' ? freeLinks(1, linkedFloors(), LINK_TARGETS)[0] : ''
    const item = {
      id, kind, label: spec.label, stage: '', group: null, placed: true, moveTo: null, isNew: false, arrived: false,
      x: spot.x, y: spot.y, w, h, rot: 0,
      color: kind === 'zone' || shape ? 'blue' : '', hatch: false, keepOut: false, link, fontSize: null, fontColor: '',
      borderStyle: BORDER_STYLES[0], labelAlign: LABEL_ALIGNS[0], look: shape ? cleanLook({ shape }, 'shape') : {},
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
    look: cleanLook(m.look, m.kind),
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

  // ---------------------------------------------------------------- 서식 복사·붙여넣기(엑셀 서식 붓)
  // 2026-11-03 사용자 요청 — 크기·색 같은 서식을 담아 다른 것에 붙인다. Alt+Shift+C 는 고른 것 가운데 기준(마지막으로 누른 것
  // `S.selected`) 하나의 서식을 담고, Alt+Shift+V 는 지금 고른 것 모두(담은 원본 하나는 빼고)에 붙인다(Ctrl+Shift+C/V 도 — 키는
  // `// <format-key>`, 엑셀은 붓뿐이다). 왼쪽 칸 「서식」 의 붓은 엑셀과 같다 — 한 번 누르면 담고 붓을 들어 다음에 누른 것 하나(묶음은 묶음째)에
  // 붙이고 내린다. 두 번 누르면 잠가 누를 때마다 붙이고 Esc·붓 단추·편집기 다시 서기(새 epoch)에 내린다. 붓을 든 채 빈 곳을 끌면
  // 사각형 안 전부에 붙는다(옮기기는 일어나지 않는다). 무엇이 어디에 붙는지는 순수 판정 `// <format-paint>` 이고, 붙일 것(크기·
  // 색·선·글자)은 체크로 고른다(`capa.space.formatPaint.v1` 에 기억). 담은 서식은 sessionStorage(층·FAB 공용 — 같은 브라우저
  // 탭에서 층을 바꿔도 남는다) + 페이지 안 쪽지(저장소가 막힌 창)다. 한 번 붙이기(여럿 포함)가 되돌리기 한 번이고, 붙인 것은 지금
  // 바뀜 판정·적용값·저장으로 그대로 간다.
  const FORMAT_CLIP_KEY = 'capa.space.formatClip.v1'
  const FORMAT_PARTS_KEY = 'capa.space.formatPaint.v1'
  const formatMemo = window.__capaSpaceFormat || (window.__capaSpaceFormat = {})
  const LINE_STYLE_WORDS = { solid: '실선', dashed: '점선', dotted: '점' }
  // 담은 원본의 표지(범위·층·id) — 붙여넣기가 그 하나를 뺀다.
  const formatOrigin = (item) => `${SCOPE}:${FLOOR}:${item.id}`
  // 서식으로 견줄 꼴 — 도면 요소는 그대로, 호기는 낱 호기(그 크기)와 Main 설비 모듈 묶음(범위 크기 — 도면에 없으면 크기 없음).
  function formatShell(item) {
    if (!isUnit(item)) return item
    const mods = moduleMembers(item)
    if (!mods) return { kind: 'unit', module: false, w: item.w, h: item.h }
    const range = groupRange(mods)
    return { kind: 'unit', module: true, w: range ? range.w : NaN, h: range ? range.h : NaN }
  }
  // 담은 서식 한 줄 — 「영역 · 20×12 · 파랑 · 점선 · 글자 13」.
  function formatWords(fmt) {
    const kind = fmt.kind === 'unit' ? (fmt.module ? 'Main 설비 묶음' : '호기')
      : MARK_KINDS[fmt.kind] ? MARK_KINDS[fmt.kind].name : fmt.kind
    const words = [kind]
    if (fmt.size) words.push(`${fmt.size.w}×${fmt.size.h}`)
    const paint = fmt.paint || {}
    if (typeof paint.color === 'string') words.push(paint.color ? SHAPE_FILL_NAMES[paint.color] || paint.color : '기본 색')
    if (LINE_STYLE_WORDS[paint.lineStyle]) words.push(LINE_STYLE_WORDS[paint.lineStyle])
    if (ARROW_HEADS.includes(paint.head)) words.push(`머리 ${headShort(paint.head)}`)
    if (fmt.text) words.push(fmt.text.fontSize ? `글자 ${fmt.text.fontSize}` : '글자 자동')
    return words.join(' · ')
  }
  // 붙일 것 체크(크기·색·선·글자) — 처음엔 모두 켬, 브라우저에 기억(이 편집기 안에서만 쓰는 보기 상태).
  function formatParts() {
    if (!S.formatParts) {
      let stored = null
      try {
        stored = JSON.parse(window.localStorage.getItem(FORMAT_PARTS_KEY) || 'null')
      } catch {
        stored = null
      }
      S.formatParts = Object.fromEntries(FORMAT_PARTS.map((part) => [part, !(stored && stored[part] === false)]))
    }
    return S.formatParts
  }
  function storeFormatParts() {
    try {
      window.localStorage.setItem(FORMAT_PARTS_KEY, JSON.stringify(formatParts()))
    } catch {
      // 이 마운트 안에서만 기억한다.
    }
  }
  function writeFormat(clip) {
    formatMemo.clip = clip
    try {
      window.sessionStorage.setItem(FORMAT_CLIP_KEY, JSON.stringify(clip))
    } catch {
      // 저장소가 막힌 창 — 이 페이지 안 쪽지로 붙인다.
    }
  }
  // 담은 서식 {at, fmt, origin} — 저장소와 쪽지 가운데 나중 것(꼴이 맞을 때만, `formatFrom`). 없으면 null.
  function readFormat() {
    let stored = null
    try {
      stored = JSON.parse(window.sessionStorage.getItem(FORMAT_CLIP_KEY) || 'null')
    } catch {
      stored = null
    }
    const clip = [stored, formatMemo.clip || null]
      .filter((c) => c && typeof c === 'object')
      .sort((a, b) => (Number(b.at) || 0) - (Number(a.at) || 0))[0]
    const fmt = clip ? formatFrom(clip.fmt, FONT_SIZES) : null
    return fmt ? { at: Number(clip.at) || 0, fmt, origin: String(clip.origin || '') } : null
  }
  // 회차마다 한 번 읽어 둔다(상태 줄·서식 칸이 끌기 중에도 자주 본다) — 담을 때 바꾼다.
  S.formatClip = readFormat()
  // 고른 것의 기준 하나의 서식을 담는다. 고른 것이 없으면 알리고 null.
  function copyFormat() {
    const item = S.selected ? S.items.get(S.selected) : null
    if (!item) {
      S.flash = '서식을 담을 것을 먼저 고르세요 — 호기·도면 요소를 누른 뒤 Alt+Shift+C'
      updateStatus()
      return null
    }
    const clip = { at: Date.now(), fmt: formatOf(formatShell(item)), origin: formatOrigin(item) }
    writeFormat(clip)
    S.formatClip = readFormat() || clip
    S.flash = `서식 복사 — ${formatWords(clip.fmt)}`
    updateStatus()
    return S.formatClip
  }
  // 서식 clip 을 targets 에 붙인다 — 받는 쪽마다 켠 묶음의 `formatPatch` 로 요소 칸·모양 값을 바꾸고 크기는 `sizeEntries`(모듈 묶음은
  // 범위째 바둑판)로 바꾼다. 바뀐 것 모두를 되돌리기 한 번에 담고 상태 줄 한 줄(`S.flash`)을 남긴다. 붙은 대상 수를 돌려준다.
  function applyFormat(targets, clip) {
    const parts = formatParts()
    const befores = new Map()
    const keep = (id, before) => { if (!befores.has(id)) befores.set(id, before) }
    const seen = new Set()
    const hits = []
    let matched = 0
    let units = 0
    for (const item of targets) {
      const mods = moduleMembers(item)
      const key = mods ? `g:${groupKeyOf(item)}` : `i:${item.id}`
      if (seen.has(key)) continue
      seen.add(key)
      if (isUnit(item)) units += 1
      const patch = formatPatch(formatShell(item), clip.fmt, parts)
      if (!patch) continue
      matched += 1
      if (Object.keys(patch.fields).length || Object.keys(patch.look).length) {
        keep(item.id, snapshot(item))
        Object.assign(item, patch.fields)
        if (Object.keys(patch.look).length) item.look = patchedLook(item.look, patch.look, item.kind)
      }
      if (patch.size) for (const e of sizeEntries([item], () => ({ ...patch.size })).entries) keep(e.id, e.before)
      hits.push(mods ? mods.map((m) => m.id) : [item.id])
    }
    const same = (before, item) => JSON.stringify({ ...before, look: lookText(before.look) })
      === JSON.stringify({ ...snapshot(item), look: lookText(item.look) })
    const changed = [...befores].filter(([id, before]) => !same(before, itemOf(id)))
    const changedIds = new Set(changed.map(([id]) => id))
    const count = hits.filter((ids) => ids.some((id) => changedIds.has(id))).length
    if (changed.length) {
      pushUndo(changed.map(([id, before]) => ({ op: 'set', id, before })))
      redraw(changed.map(([id]) => itemOf(id)))
    }
    const unitOnly = clip.fmt.kind === 'unit' || units > 0
    if (count) {
      const left = seen.size - matched
      S.flash = `서식을 ${count}개에 붙였습니다${left ? ` · 맞는 칸이 없는 ${left}개는 그대로${unitOnly ? '(호기에는 같은 호기의 크기만 붙습니다)' : ''}` : ''}`
    } else if (!FORMAT_PARTS.some((part) => parts[part])) {
      S.flash = '붙일 것(크기·색·선·글자)이 모두 꺼져 있습니다 — 왼쪽 칸 「서식」 체크'
    } else if (matched) {
      S.flash = '이미 같은 서식입니다'
    } else if (unitOnly) {
      S.flash = '호기에는 같은 호기의 크기만 붙습니다'
    } else {
      S.flash = '붙일 서식이 없습니다 — 크기는 같은 종류끼리만 붙습니다'
    }
    return count
  }
  // Alt+Shift+V(Ctrl+Shift+V)·「붙이기」 — 담은 서식을 지금 고른 것 모두(도면에 선 것, 담은 원본 하나는 빼고)에 붙인다.
  function pasteFormat() {
    const clip = S.formatClip
    if (!clip) {
      S.flash = '담은 서식이 없습니다 — 고른 것에서 Alt+Shift+C 또는 「서식 복사」'
      updateStatus()
      return
    }
    const targets = selectedItems().filter((m) => onCanvas(m) && formatOrigin(m) !== clip.origin)
    if (!targets.length) {
      S.flash = '서식을 붙일 것을 고르세요 — 담은 원본 하나는 빼고 고른 것 모두에 붙입니다'
      updateStatus()
      return
    }
    applyFormat(targets, clip)
    updateStatus()
  }
  // 서식 붓 — S.paint = {clip, sticky}(든 동안) 또는 null.
  function setBrush(next) {
    S.paint = next
    updateStatus()
  }
  // 붓에 담을 서식 — 고른 것이 있으면 그것을 새로 담고, 없으면 앞서 담은 서식(다른 층에서 담은 것 포함). 둘 다 없으면 알리고 null.
  function brushClip() {
    if (S.selected && S.items.has(S.selected)) return copyFormat()
    if (!S.formatClip) {
      S.flash = '서식을 담을 것을 먼저 고르세요 — 호기·도면 요소를 누른 뒤 붓을 누릅니다'
      updateStatus()
    }
    return S.formatClip
  }
  // 붓을 든 채 누른(또는 사각형으로 고른) 것에 붙인다. 한 번 붓이면 내린다. 붙인 것이 골라진다.
  function paintOnto(targets) {
    const brush = S.paint
    if (!brush || !targets.length) return
    applyFormat(targets, brush.clip)
    const flash = S.flash
    if (!brush.sticky) S.paint = null
    const ids = targets.map((m) => m.id)
    setSelection(ids, ids[ids.length - 1])
    S.flash = flash
    updateStatus()
  }
  // 붓을 든 채 누른 자리의 받을 것 — 호기·요소(맨 위 층에 다시 세운 손잡이는 그 요소), 고른 모듈 묶음의 범위 손잡이·범위 안 빈
  // 칸은 그 묶음. 빈 곳이면 null.
  function paintTargetAt(node, p) {
    const proxyFor = node.dataset ? node.dataset.for : undefined
    const group = proxyFor ? S.groups.get(proxyFor) || null : node.closest ? node.closest('.sle-item') : null
    if (group) return S.items.get(group.dataset.id) || null
    const picked = selectedItems()
    if (node.classList && node.classList.contains('sle-range-handle')) return picked.find((m) => moduleMembers(m)) || null
    return pickedRangeAt(picked, p)
  }
  // 왼쪽 칸 「서식」 — 붓 단추 눌림·잠금, 붙이기 단추, 붙일 것 체크, 담은 서식 한 줄. 상태 줄과 함께 고친다.
  function syncFormatPanel() {
    const clip = S.formatClip
    setAttr(paintButton, 'aria-pressed', String(Boolean(S.paint)))
    paintButton.classList.toggle('is-sticky', Boolean(S.paint && S.paint.sticky))
    svg.classList.toggle('is-painting', Boolean(S.paint))
    paintPaste.disabled = !clip || !selectedItems().some((m) => onCanvas(m) && formatOrigin(m) !== clip.origin)
    const parts = formatParts()
    for (const box of paintParts) box.checked = parts[box.dataset.part] !== false
    setText(paintNow, clip ? `담은 서식 — ${formatWords(clip.fmt)}` : '담은 서식 없음 — 고른 것에서 「서식 복사」(Alt+Shift+C)')
  }
  // 붓 단추 — 한 번 누르면(키보드 Enter·Space 포함) 담고 들기 / 든 붓 내리기, 두 번 누르면 잠금(엑셀처럼). 두 번 누름의 첫 누름이
  // 이미 붓을 들었으면 그 붓을 잠근다.
  paintButton.onclick = (event) => {
    if (event.detail >= 2) {
      const clip = S.paint ? S.paint.clip : brushClip()
      if (clip) setBrush({ clip, sticky: true })
      return
    }
    if (S.paint) { setBrush(null); return }
    const clip = brushClip()
    if (clip) setBrush({ clip, sticky: false })
  }
  paintPaste.onclick = () => pasteFormat()
  for (const box of paintParts) {
    box.onchange = () => {
      formatParts()[box.dataset.part] = box.checked
      storeFormatParts()
      updateStatus()
    }
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
    const { entries, touched } = sizeEntries(list, patchOf)
    if (!entries.length) { syncInspector(); return }
    commit(entries)
    redraw(touched)
    updateStatus()
  }
  // `setSizes` 의 크기 바꾸기 — 바꾸기만 하고 기록하지 않는다. 바뀐 것의 처음 값({id, before})과 다시 그릴 것을 돌려준다(서식
  // 붙여넣기가 다른 칸 바꿈과 함께 한 기록으로 모은다).
  function sizeEntries(list, patchOf) {
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
      // 도형은 두께 · 둥글기 · 머리 길이를 지킨다(손잡이 끌기와 같다 — `sizedLook`).
      if (item.kind === 'shape') item.look = sizedLook(before, item)
      if (!sameGeometry(item, before)) {
        item.sizeGuessed = false
        entries.push({ id: item.id, before })
        touched.push(item)
      }
    }
    return { entries, touched }
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
      S.note = `돌리면 ${item.h}×${withJosa(item.w, '이')} 되어 편집 영역 ${W()}×${withJosa(H(), '을')} 넘어 돌리지 않았습니다`
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

  // 노란 손잡이 index 를 화면 점 p({x, top})에 끌었을 때 도형 item 의 새 모양 값 — 같은 값이면 null.
  function adjustedLook(item, index, p) {
    const rot = item.rot || 0
    const lw = rot % 180 ? item.h : item.w
    const lh = rot % 180 ? item.w : item.h
    const flip = lookValue(item.look, 'shape', 'flip') === true
    const local = unplaceLocal(p.x - (item.x + item.w / 2), p.top - (svgTop(item) + item.h / 2), lw, lh, rot, flip)
    const preset = shapeOf(item.look)
    const value = handleValue(preset, index, local.x, local.y, lw, lh)
    if (value === null) return null
    const adj = shapeAdj(item.look).slice()
    adj[index] = value
    const next = cleanLook({ ...(item.look || {}), adj }, 'shape')
    return lookText(next) === lookText(item.look) ? null : next
  }

  // 도형(또는 그 처음 상태) box 의 제자리 상자 [lw, lh] — 90°·270° 돌린 것은 폭·높이가 바뀐다.
  function shapeBox(box) {
    return (box.rot || 0) % 180 ? [box.h, box.w] : [box.w, box.h]
  }
  // 비율 없이 크기를 바꾼 도형 item 의 모양 값 — 처음 상태 before(크기·돌림·모양 값)에서 그린 두께 · 둥글기 · 머리 길이를 지킨
  // 것(`resizedAdj`). 짧은 변이 그대로이거나 바뀐 값이 없으면 before.look 그대로다. 손잡이 끌기 · 폭·높이 칸 · Ctrl+방향키 ·
  // 서식 붙이기의 크기가 쓰고, Shift 비율 유지는 쓰지 않는다(모두 같은 배율이라 비율 값 그대로가 맞는 그림이다).
  function sizedLook(before, item) {
    const [lw0, lh0] = shapeBox(before)
    const [lw1, lh1] = shapeBox(item)
    const adj = shapeAdj(before.look)
    const next = resizedAdj(shapeOf(before.look), adj, lw0, lh0, lw1, lh1)
    if (next === adj || next.every((value, k) => value === adj[k])) return before.look
    return cleanLook({ ...(before.look || {}), adj: next }, 'shape')
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
    drawer.classList.remove('is-drop-target')
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
    layer: SHORT_LAYERS.has(raw.layer) ? raw.layer : '', dim: raw.dim === true,
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
    // 모양 값(동선·베이의 머리 크기·선·뒤집기, 도형의 프리셋·모양 조절·채우기·선)은 처음 값이 아닌 것만 쥔다. 베이 이름표는
    // 번호다(앞 B 를 뗀다). 도형의 채우기 색은 모르는 값이면 파랑이다.
    look: cleanLook(raw.look, String(raw.kind)),
    ...(String(raw.kind) === 'bay' ? { label: bayNumber(raw.label) } : {}),
    ...(String(raw.kind) === 'shape' ? { color: shapeFillOf(raw.color) } : {}),
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
    // 편집기가 다시 서면 든 서식 붓을 내린다(담은 서식은 남는다).
    S.paint = null
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
    let previous = adoptAsOf(AS_OF)
    // 「필요 단축」 을 켜고 끈 회차는 모든 호기의 지연·보관 면이 바뀐다(결정 D12) — 다 다시 본다(바뀐 상자만 칠한다).
    if (VIEW && !FAB && S.lastPinned !== undefined && S.lastPinned !== ASOF_PINNED) previous = '*'
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
  // 견주기는 epoch 밖이다 — 토글을 켜고 끄거나 기준일·필터만 바뀐 회차에도 다시 마운트하지 않고 이 층만 다시 그린다.
  drawCompare()
  S.lastPinned = ASOF_PINNED
  // 배지만 바뀐 회차(목표를 바꿔 일수 글만 바뀜·임박 날수만 바뀜)는 호기 값이 그대로라 위 길이 다시 그리지 않는다 — 배지
  // 지문으로 가른다(팔레트와 같은 꼴).
  const badgeKey = ASOF_PINNED ? JSON.stringify(SHORT_BADGES) : ''
  if (S.badgeKey !== badgeKey) {
    S.badgeKey = badgeKey
    drawShortBadges()
  }

  // ------------------------------------------------------------- 필요 단축 칸에 고른 호기(층 상세 보기)
  // 층 상세 보기에서 호기를 누르면(끌지 않고) 그 호기를 `pick` 으로 알린다(2026-10-23 사용자 요청 3). 받는 쪽 파이썬
  // `on_pick_change` 콜백이 필요 단축 칸의 누른 호기 상세를 세운다 — 블록 열기(`navigate`)와 같은 꼴이고 epoch 가 다른 옛 값은
  // 버린다. 호기가 아닌 것(도면 요소)을 누르거나 빈 곳을 누르거나 Esc 로 풀면 고른 호기가 없다는 값(id null)을 보낸다. 같은 값은
  // 다시 보내지 않는다. 필요 단축 칸의 표에서 파이썬이 고르면 `data.picked` 로 도면의 고르기도 따라간다. 보내는 것은 그 보기를 켠
  // 동안뿐이다(`data.pickToServer` — 사양 D11, 누를 때마다 앱 전체가 돌지 않게. 고른 호기의 칸은 「호기 정보」 창이 브라우저 안에서
  // 보인다). 배치 편집기와 FAB 는 보내지 않는다.
  const PICKS = VIEW && !FAB && data.pickToServer !== false
  function notePick() {
    if (!PICKS) return
    const item = S.selected ? S.items.get(S.selected) : null
    const id = item && isUnit(item) ? item.id : null
    if (id === S.pickSent) return
    S.pickSent = id
    setTriggerValue('pick', { epoch: S.epoch, id })
  }
  // 파이썬이 쥔 고른 호기가 지난 회차와 다르면(누른 회차·필요 단축 칸의 표·새로 선 도면) 도면의 고르기를 그것에 맞춘다. 보내지
  // 않는 동안은 파이썬 값을 잊는다(파이썬도 그 동안 풀어 둔다) — 다시 보내기 시작한 회차에 브라우저가 이미 호기를 골라 두었으면
  // 그 호기를 한 번 보낸다(그린 뒤에 — 받은 data 로 불린 함수 안에서는 보내지 않는다).
  function syncPick() {
    if (!PICKS) {
      S.pickData = undefined
      S.pickSent = null
      return
    }
    const picked = typeof data.picked === 'string' && data.picked ? data.picked : null
    if (picked === S.pickData) return
    const resumed = S.pickData === undefined
    S.pickData = picked
    S.pickSent = picked
    if (picked && S.items.has(picked)) {
      if (S.selected !== picked || S.selection.size !== 1) select(picked)
    } else if (!picked && S.selected && isUnit(S.items.get(S.selected) || {})) {
      if (resumed) (typeof queueMicrotask === 'function' ? queueMicrotask : setTimeout)(notePick)
      else select(null)
    }
  }
  syncPick()

  // ------------------------------------------------------------- 끌기(속성 대입이라 겹쳐 쌓이지 않는다)
  svg.onmousedown = (event) => { if (event.button === 1) event.preventDefault() }
  // 고른 것 가운데 도면 점 p(화면 좌표 {x, top})를 범위 안에 품은 모듈 묶음(그 고른 호기 — 없으면 null).
  function pickedRangeAt(picked, p) {
    const y = H() - p.top
    return picked.find((item) => {
      const mods = moduleMembers(item)
      const range = mods && groupRange(mods)
      return Boolean(range) && p.x >= range.x && p.x <= range.x + range.w && y >= range.y && y <= range.y + range.h
    }) || null
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
      // 「필요 단축」 배지를 누르면 그 호기(묶음은 첫 모듈)를 누른 것과 같다.
      const badge = event.target.closest ? event.target.closest('.sle-short-badge') : null
      const target = badge || (event.target.closest ? event.target.closest('.sle-item') : null)
      S.drag = {
        mode: 'view', pointerId: event.pointerId, startClientX: event.clientX, startClientY: event.clientY,
        view: { ...S.view }, upp: unitsPerPx(), id: target ? (badge ? badge.dataset.pick : target.dataset.id) : null,
        moved: false,
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
    if (S.paint) {
      // 서식 붓을 든 채 — 누른 호기·요소(손잡이·고른 묶음 범위 안 빈 칸도 그것)에 붙이고 끌지 않는다. 빈 곳은 사각형 고르기이고
      // 놓을 때 그 안 전부에 붙인다(`paintOnto`).
      const target = paintTargetAt(event.target, p)
      if (target) { paintOnto([target]); return }
      S.drag = { ...start, mode: 'marquee', paint: true, additive: false, before: new Set(S.selection), beforePrimary: S.selected, rect: null }
      svg.setPointerCapture(event.pointerId)
      return
    }
    const rangeDir =event.target.classList && event.target.classList.contains('sle-range-handle') ? event.target.dataset.dir : null
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
    // 맨 위 층에 다시 세운 손잡이(`proxyHandles`)는 그 요소의 손잡이다.
    const proxyFor = event.target.dataset ? event.target.dataset.for : undefined
    const group = proxyFor ? S.groups.get(proxyFor) || null : (event.target.closest ? event.target.closest('.sle-item') : null)
    const additive = event.shiftKey || event.ctrlKey || event.metaKey
    if (!group && !additive && pickedRangeAt(picked, p)) {
      // 고른 모듈 묶음의 범위 안 빈 칸(모듈 셋·다섯 묶음의 남는 칸, 숨은 모듈 칸)도 묶음이다 — 누르면 그 묶음을 끈다.
      const plan = movePlan(picked)
      S.drag = {
        ...start, id: S.selected, mode: 'move', dir: null, loose: plan.loose, groups: plan.groups, hasUnit: true,
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
    // 손잡이(크기·도형 모양 조절)는 고른 것 하나에만 서고, Shift 를 누른 채 잡아도 끈다 — 도형 모서리의 Shift 는 가로세로 비율
    // 유지다(엑셀처럼).
    const grip = event.target.classList && (event.target.classList.contains('sle-handle') || event.target.classList.contains('sle-adjust'))
    if (additive && !grip) {
      // Shift/Ctrl+클릭은 고른 것에 더하거나 뺀다(끌지 않는다).
      toggleSelected(item)
      return
    }
    const chosen = selectedItems()
    const inSelection = expanded(chosen).some((m) => m.id === item.id)
    const onlyThis = chosen.length === 1 && S.selected === item.id
    if (onlyThis && item.kind === 'shape' && event.target.classList.contains('sle-adjust')) {
      // 도형 하나를 고른 채 노란 손잡이를 잡았다 — 모양 조절 값을 끈다(놓을 때 바뀌었으면 되돌리기 한 번).
      // 잡은 자리와 손잡이 참 자리의 차이(grab)를 지켜 끈다 — 비켜 그린 손잡이·한가운데가 아닌 곳을 잡아도 값이 튀지 않는다.
      const tx = Number(event.target.dataset.tx)
      const ty = Number(event.target.dataset.ty)
      S.drag = {
        ...start, id: item.id, mode: 'adjust', index: Number(event.target.dataset.index) || 0, ids: [item.id],
        befores: new Map([[item.id, snapshot(item)]]), loose: [], groups: [], box: null, collapse: false,
        grab: { x: Number.isFinite(tx) ? tx - p.x : 0, top: Number.isFinite(ty) ? ty - p.top : 0 },
      }
      svg.setPointerCapture(event.pointerId)
      return
    }
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
      ...start, id: item.id, mode, dir, loose: plan.loose, groups: plan.groups, hasUnit: list.some((m) => isUnit(m) && !m.ghost),
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
    if (drag.mode === 'adjust') {
      // 노란 손잡이 끌기 — 포인터를 도형 제자리 좌표로 되돌려 그 손잡이의 값을 낸다(격자·정렬선에 붙이지 않는다).
      drag.moved = true
      const item = S.items.get(drag.id)
      const next = item ? adjustedLook(item, drag.index, { x: p.x + drag.grab.x, top: p.top + drag.grab.top }) : null
      if (next) {
        item.look = next
        position(S.groups.get(item.id), item)
        drawSelectionBox()
        syncInspector()
      }
      return
    }
    // 이동량은 격자에 맞추되, 정렬선에 닿는 축은 그 선에 붙인 이동량이 이긴다(Alt 를 누른 채면 붙이지 않는다).
    const aligned = alignDrag(drag, p.x - drag.startX, p.top - drag.startTop, event.altKey)
    const dx = aligned.dx ?? snapDelta(p.x - drag.startX)
    const dTop = aligned.dTop ?? snapDelta(p.top - drag.startTop)
    if (drag.mode === 'move') {
      // 도면의 호기를 오른쪽 미배치 칸(접힌 띠 포함) 위로 끌면 놓을 때 미배치로 돌아간다(2026-11-03 사용자 요청 — 미배치
      // 슬롯 이동성). 칸에 「여기 놓으면 미배치로」 테가 선다. 호기가 든 끌기만이다(도면 요소만이면 칸이 받지 않는다).
      const toTray = HAS_RIGHT && drag.hasUnit && insideRect(drawer.getBoundingClientRect(), event.clientX, event.clientY)
      if (toTray !== Boolean(drag.toTray)) {
        drag.toTray = toTray
        drawer.classList.toggle('is-drop-target', toTray)
      }
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
      const item = S.items.get(drag.id)
      const before = drag.befores.get(drag.id)
      resizeTo(item, before, drag.dir, dx, dTop)
      // 도형의 모서리 손잡이를 Shift 를 누른 채 끌면 가로세로 비율을 지킨다(원은 원으로 — 엑셀처럼). 모양 값은 처음 값 그대로다.
      // 비율 없이 끌면 두께 · 둥글기 · 머리 길이를 지킨다(`sizedLook` — 늘 처음 상태에서 다시 셈해 끄는 동안 쌓이지 않는다).
      if (item.kind === 'shape') {
        const aspect = event.shiftKey && drag.dir.length === 2
        if (aspect) {
          Object.assign(item, keepAspect(before, item, drag.dir, W(), H(), minSize(), SCALE))
          fit(item)
        }
        item.look = aspect ? before.look : sizedLook(before, item)
      }
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
      // 문턱을 넘은 끌기는 누르기가 아니다(전체 보기에서 화면이 움직이지 않아도) — 고르지도 알리지도 않는다.
      if (drag.travelled) return
      select(drag.id)
      notePick()
      return
    }
    if (drag.mode === 'marquee') {
      // 서식 붓의 사각형 — 그 안 전부에 붙인다. 누르기만 했거나 안에 든 것이 없으면 고른 것을 그대로 두고 붓도 든 채다.
      if (drag.paint && drag.moved && S.selection.size) { paintOnto(selectedItems()); return }
      if (drag.paint) {
        S.selection = new Set(drag.before)
        S.selected = drag.beforePrimary
        markSelection()
        updateStatus()
        return
      }
      // 끌지 않고 빈 곳을 누르기만 했으면 선택을 푼다(Shift/Ctrl 이면 그대로 둔다).
      if (!drag.moved && !drag.additive) clearSelection()
      markSelection()
      updateStatus()
      return
    }
    if (drag.mode === 'adjust') {
      const before = drag.befores.get(drag.id)
      const item = S.items.get(drag.id)
      if (item && lookText(before.look) !== lookText(item.look)) pushUndo([{ op: 'set', id: item.id, before }])
      updateStatus()
      return
    }
    clearDragOverlap()
    if (drag.toTray) {
      // 오른쪽 칸에 놓았다 — 끈 자리를 처음으로 돌린 뒤 고른 호기만 빼기·지우기와 같은 길로 미배치(도면 요소는 제자리,
      // 모듈 묶음은 묶음째). 되돌리기 한 번에 돌아온다.
      drawer.classList.remove('is-drop-target')
      for (const [id, before] of drag.befores) Object.assign(itemOf(id), before)
      const units = drag.ids.map(itemOf).filter((m) => m && isUnit(m) && !m.ghost && onCanvas(m))
      const count = expanded(units).filter(onCanvas).length
      removeItems(units)
      S.flash = `미배치로 ${count}대 — 실행 취소로 되돌립니다`
      updateStatus()
      return
    }
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
  // Ctrl+휠(터치패드 오므리기 포함)은 마우스 자리를 축으로 확대·축소한다. 스크롤 고정 중이면 맨 휠은 도면 이동이다.
  // 고정이 아니면 맨 휠은 확대 중에도 도면을 옮기지 않고 페이지로 보낸다 — 확대한 도면이 먼저 굴러가다 끝에 닿아야 페이지가 굴러가면, 도면
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
    if (S.lock) {
      // 스크롤 고정 중 — 페이지는 굴러가지 않으니 맨 휠은 도면을 옮긴다(세로, Shift 는 가로, 터치패드 옆 밀기는 가로).
      // 전체 보기(확대 1)에서는 옮길 데가 없어 아무 일도 없다.
      event.preventDefault()
      const upp = unitsPerPx()
      panBy((event.shiftKey ? event.deltaY : event.deltaX) * unit * upp, (event.shiftKey ? 0 : event.deltaY) * unit * upp)
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
    if (VIEW && (S.lastViewDragMoved || S.lastViewOnBlock)) return
    // 호기를 두 번 누르면 「호기 정보」 창의 「고른 호기」 를 연다(층 보기·편집). 그 밖의 곳은 보기에서 확대/전체 보기다.
    const unit = SHEET && !S.drag ? unitAt(toUser(event)) : null
    if (unit) {
      event.preventDefault()
      openSheet('picked')
      return
    }
    if (!VIEW) return
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
      // 층 보기의 호기에 초점이 있으면 Enter·Space 가 누르기와 같다 — 그 호기 정보 한 줄·「호기 정보」 창과 `pick`.
      const unitNode = FAB ? null : canvasItemOf(event.target)
      if (unitNode && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault()
        if (!S.items.has(unitNode.dataset.id)) return
        select(unitNode.dataset.id)
        notePick()
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
    // 든 서식 붓은 Esc 가 먼저 내린다(고른 것은 그대로).
    if (event.key === 'Escape' && S.paint) { event.preventDefault(); setBrush(null); return }
    const typing = event.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)
    const ctrl = event.ctrlKey || event.metaKey
    if (ctrl && event.key.toLowerCase() === 'z' && !typing) { event.preventDefault(); undo(); return }
    if (typing) return
    // Tab 으로 초점이 온 호기·요소는 Enter·Space 가 누르기와 같다 — 그것 하나를 고르고, Ctrl(⌘)·Shift 는 고른 것에 더하거나
    // 뺀다(Shift/Ctrl+클릭). 고른 뒤의 방향키(옮기기)·Ctrl+방향키(크기)·Delete(빼기·지우기)는 도면에서와 같다.
    const focusedItem = canvasItemOf(event.target)
    if (focusedItem && (event.key === 'Enter' || event.key === ' ') && !event.altKey) {
      event.preventDefault()
      const item = S.items.get(focusedItem.dataset.id)
      if (!item || S.drag) return
      if (ctrl || event.shiftKey) toggleSelected(item)
      else select(item.id)
      return
    }
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
    // 서식 복사·붙여넣기 — Alt+Shift+C/V(macOS ⌥+⇧, 기본)와 Ctrl(⌘)+Shift+C/V(브라우저가 넘겨주면) 둘 다(`formatKeyOf` — 글쇠
    // 자리 code, IME 조합 중은 비킴). 요소 복사 갈래보다 먼저 보고, 요소 복사는 Shift 가 없을 때만이라 서로 겹치지 않는다. 글 칸의
    // 키(Ctrl+Shift+V 서식 없이 붙여넣기, macOS ⌥+⇧ 글자)는 위에서 비켜 그대로 브라우저 것이다.
    const formatKey = formatKeyOf(event)
    if (formatKey === 'c') { event.preventDefault(); copyFormat(); return }
    if (formatKey === 'v') { event.preventDefault(); pasteFormat(); return }
    // 뒤집기 — Shift+H 좌우 · Shift+V 상하(`flipKeyOf` — 수정 키는 Shift 하나만). 뒤집을 것이 없으면 키를 막지 않는다.
    const flipKey = flipKeyOf(event)
    if (flipKey) { if (flipMarks(flipKey)) event.preventDefault(); return }
    // 도면 요소 복사·붙여넣기(호기는 복사하지 않는다). 한글 자판에서도 듣게 글쇠 자리(code)도 본다. 글 칸에서는 위에서 비켰다.
    const letter = event.code === 'KeyC' ? 'c' : event.code === 'KeyV' ? 'v' : event.key.toLowerCase()
    if (ctrl && !event.shiftKey && letter === 'c') { if (copyMarks()) event.preventDefault(); return }
    if (ctrl && !event.shiftKey && letter === 'v') { if (pasteMarks(event.altKey)) event.preventDefault(); return }
    const chosen = selectedItems()
    const standing = chosen.filter(onCanvas)
    // 지우기는 도면(또는 도면의 호기·요소)에 포커스가 있을 때만 — 툴바 단추를 누른 뒤 Backspace 가 고른 것을 지우지 않게.
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (!chosen.length || (event.target !== svg && !focusedItem)) return
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
    // 베이는 번호만 쥔다 — 「80」·「B80」·「b 80」 모두 「80」(그릴 때 「B80」).
    const value = mark && mark.kind === 'bay' ? bayNumber(markLabel.value) : markLabel.value.trim().slice(0, 40)
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
  headToggle.onclick = () => {
    const open = headGallery.hidden
    headGallery.hidden = !open
    headToggle.setAttribute('aria-expanded', String(open))
    if (open) (headGallery.querySelector('[aria-pressed="true"]') || headGallery.firstElementChild)?.focus()
  }
  headGallery.onclick = (event) => {
    const cell = event.target.closest('.sle-head-cell')
    if (!cell) return
    headGallery.hidden = true
    headToggle.setAttribute('aria-expanded', 'false')
    setLooks({ head: cell.dataset.head })
    headToggle.focus()
  }
  headGallery.onkeydown = (event) => {
    if (event.key !== 'Escape') return
    event.preventDefault()
    event.stopPropagation()
    headGallery.hidden = true
    headToggle.setAttribute('aria-expanded', 'false')
    headToggle.focus()
  }
  lineColor.onchange = () => { if (lineColor.value !== MIXED) setLooks({ line: lineColor.value }) }
  lineWidth.onchange = () => { if (lineWidth.value !== MIXED) setLooks({ lineWidth: lineWidth.value === '' ? null : Number(lineWidth.value) }) }
  lineStyle.onchange = () => { if (lineStyle.value !== MIXED) setLooks({ lineStyle: lineStyle.value }) }
  for (const button of flipButtons) button.onclick = () => flipMarks(button.dataset.flip)
  shapeSwap.onclick = () => {
    const open = shapeGallery.hidden
    shapeGallery.hidden = !open
    shapeSwap.setAttribute('aria-expanded', String(open))
    if (open) (shapeGallery.querySelector('[aria-pressed="true"]') || shapeGallery.firstElementChild)?.focus()
  }
  // 바꾸기 갤러리 칸은 한 번만 만들어 두므로 누르기는 회차마다 다시 다는 위임이다(지난 회차의 닫힘을 쥐지 않게).
  shapeGallery.onclick = (event) => {
    const cell = event.target.closest('.sle-shape-cell')
    if (!cell) return
    closeShapeGallery()
    setShapes({ shape: cell.dataset.shape, adj: null })
    shapeSwap.focus()
  }
  shapeGallery.onkeydown = (event) => {
    if (event.key !== 'Escape') return
    event.preventDefault()
    event.stopPropagation()
    closeShapeGallery()
    shapeSwap.focus()
  }
  shapeAdjInputs.forEach((input, k) => {
    input.onchange = () => {
      const value = Number(input.value)
      if (input.value === '' || !Number.isFinite(value)) { syncInspector(); return }
      setShapes((m) => {
        const preset = shapeOf(m.look)
        const spec = SHAPE_PRESETS[preset].adj[k]
        if (!spec) return {}
        // 상한은 그 도형 상자의 것이다(`adjTop` — ㄴ자 세로 팔은 폭까지).
        const [lw, lh] = shapeBox(m)
        const adj = shapeAdj(m.look).slice()
        adj[k] = Math.min(Math.max(Math.round(value) / 100, spec[0]), adjTop(preset, k, lw, lh))
        return { adj }
      })
    }
    input.onkeydown = (event) => { if (event.key === 'Enter') input.blur() }
  })
  shapeFill.onchange = () => { if (shapeFill.value !== MIXED) setShapes({}, { color: shapeFill.value }) }
  // 투명도는 엑셀처럼 「0% 불투명 · 100% 채우기 없음」 이다 — 저장 값은 불투명도(look.fillAlpha = 100 − 투명도, 5 단위).
  shapeClear.onchange = () => {
    const value = Number(shapeClear.value)
    if (shapeClear.value === '' || !Number.isFinite(value)) { syncInspector(); return }
    const clear = Math.min(Math.max(Math.round(value / FILL_ALPHA_STEP) * FILL_ALPHA_STEP, 0), 100)
    setShapes({ fillAlpha: 100 - clear })
  }
  shapeClear.onkeydown = (event) => { if (event.key === 'Enter') shapeClear.blur() }
  shapeLine.onchange = () => { if (shapeLine.value !== MIXED) setShapes({ line: shapeLine.value }) }
  shapeWidth.onchange = () => { if (shapeWidth.value !== MIXED) setShapes({ lineWidth: Number(shapeWidth.value) }) }
  shapeStyle.onchange = () => { if (shapeStyle.value !== MIXED) setShapes({ lineStyle: shapeStyle.value }) }
  shapeHatch.onchange = () => setShapes({}, { hatch: shapeHatch.checked })
  // 도면 요소 칸 「도형 ▾」 — 펼친 갤러리의 칸을 누르면 보이는 화면 가운데에, 끌면 놓은 자리에 그 프리셋을 넣는다(크기는 프리셋마다).
  // 키보드(Enter·Space 의 click)로도 넣는다.
  shapeToggle.onclick = () => {
    const open = shapePalette.hidden
    shapePalette.hidden = !open
    shapeToggle.setAttribute('aria-expanded', String(open))
  }
  shapePalette.replaceChildren(...shapeCells((button, key) => {
    const [w, h] = SHAPE_PRESETS[key].size
    button.title = `${SHAPE_PRESETS[key].name} — 눌러서 넣거나 도면으로 끌어 놓기`
    button.onpointerdown = (event) => ghostDrag(event, `도형 · ${SHAPE_PRESETS[key].name}`, (p, free) => addMark('shape', p, free, key), () => addMark('shape', null, false, key), () => ({ w, h }))
    button.onclick = (event) => { if (event.detail === 0) addMark('shape', null, false, key) }
  }))
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
  // 새 호기 폼을 끈 편집(그 시나리오에 더 새 리비전이 있는 세션·찍힌 역할이 바뀐 세션 등 — 일정이 생기는
  // 새 호기는 저장에서 막힌다). 단추를 끄고 까닭을 풍선으로 보인다. 다른 편집은 그대로다. 회차마다 받은 값대로
  // 다시 켜고 끈다 — 편집기 key 는 설비 시나리오가 바뀌어도 같아 같은 DOM 이 남는다.
  lockNewUnitToggle(addToggle, addForm, NEW_UNIT.disabled)
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
    else if (clash) error = `${withJosa(id, '은')} 이미 있는 이름입니다(${clash}).`
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

  // ---------------------------------------------------------------- 잠금(회차마다)
  // 칸 잠금은 받은 값대로 켜고 끈다. 처음 본 풍선 글은 `data-base-title` 에 두었다가 풀 때 되돌린다.
  function lockCanvasControls(controls, locked, reason) {
    for (const control of controls) {
      if (control.dataset.baseTitle === undefined) control.dataset.baseTitle = control.title || ''
      control.disabled = locked
      control.title = locked ? reason : control.dataset.baseTitle
    }
  }
  // 새 호기 단추 — `reason` 이 있으면 끄고 폼을 닫는다. 없으면 다시 켠다(풍선은 비운다).
  function lockNewUnitToggle(toggle, form, reason) {
    toggle.disabled = Boolean(reason)
    toggle.title = reason ? String(reason) : ''
    if (reason) {
      form.hidden = true
      toggle.setAttribute('aria-expanded', 'false')
    }
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
  // 편집 영역 칸을 끄면 까닭을 풍선·알림 칸에 둔다(보기는 그대로 — 폭·높이 값은 지금 캔버스). 회차마다 받은
  // 값대로 켜고 끈다 — 가정 세션에서 끈 칸이 공식 세션으로 돌아와도(편집기 key·DOM 이 같다) 꺼진 채 남지 않게.
  const canvasLocked = data.canvasEditable === false
  lockCanvasControls(
    q('.sle-area').querySelectorAll('input, button'),
    canvasLocked,
    data.canvasLock || '이 편집기에서는 편집 영역을 바꾸지 않습니다',
  )
  if (canvasLocked) areaNote.textContent = data.canvasLock || ''
  else if (!S.note) areaNote.textContent = ''
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

  // ---------------------------------------------------------------- 두 옆 칸 — 폭·접힘·기억(브라우저 안에서만)
  // 칸 폭·접힘은 파이썬으로 보내지 않고 epoch 에 넣지 않는다(무대 높이 `capa.space.viewerHeight.<범위>` 와 같은 꼴 — AGENTS 9장
  // 「브라우저 전용 보기 상태」). 저장소가 막힌 브라우저에서는 이 마운트 안에서만 기억한다(S.panels).
  const panelSpec = (side) => (side === 'left' && VIEW ? PANEL_SPECS.view : PANEL_SPECS.edit)
  const sideEl = (side) => (side === 'left' ? leftSide : drawer)
  const splitEl = (side) => (side === 'left' ? leftSplit : rightSplit)
  const hasSide = (side) => (side === 'left' ? HAS_LEFT : HAS_RIGHT)
  const isNarrow = () => host.classList.contains('is-narrow')
  function readPanelStore() {
    try {
      return storedPanels(window.localStorage.getItem(PANELS_STORE_KEY))
    } catch {
      return null
    }
  }
  function panelState(side) {
    if (!S.panels) S.panels = {}
    if (!S.panels[PANEL_MODE]) {
      const all = readPanelStore()
      S.panels[PANEL_MODE] = { ...((all && all[PANEL_MODE]) || {}) }
    }
    const mode = S.panels[PANEL_MODE]
    if (!mode[side]) mode[side] = { w: null, min: false }
    return mode[side]
  }
  function storePanel(side) {
    const state = panelState(side)
    const all = readPanelStore()
    if (!all) return
    all[PANEL_MODE] = { ...(all[PANEL_MODE] || {}), [side]: { w: state.w, min: state.min } }
    try {
      window.localStorage.setItem(PANELS_STORE_KEY, JSON.stringify(all))
    } catch {
      // 기억하지 못해도 이 마운트는 S.panels 로 그대로 쓴다.
    }
  }
  // 칸이 펼쳐져 있는가 — 넓은 화면은 기억한 접힘, 좁은 화면 겹침 서랍은 지금 열린 하나.
  function panelOpen(side) {
    if (!hasSide(side)) return false
    return isNarrow() ? S.narrowOpen === side : !panelState(side).min
  }
  function setPanelOpen(side, open) {
    if (!hasSide(side)) return
    if (isNarrow()) {
      if (open) S.narrowOpen = side
      else if (S.narrowOpen === side) S.narrowOpen = null
    } else {
      panelState(side).min = !open
      storePanel(side)
    }
    layoutPanels()
    // 좁은 화면 서랍을 접으면 서랍 몫(`trayReserve`)으로 옮긴 화면을 제자리로.
    if (!open) applyView({ reposition: false })
  }
  // 칸 폭을 정해 몸의 가로 칸(grid)에 건다. 넓은 화면은 칸마다 기억 폭(없으면 기본, 접혔으면 28px 띠)을 한계 안으로 맞추고
  // 무대가 STAGE_MIN_PX 아래로 가면 마지막에 끈 칸부터 줄인다. 좁은 화면은 두 칸이 무대 위 겹침 서랍이라 칸 폭은 0 이고
  // 서랍 폭(`--side-panel-w`)만 준다. 무대 폭이 바뀌면 무대 관찰자(S.ro)가 viewBox 를 다시 맞춘다.
  function layoutPanels() {
    const width = host.clientWidth || 0
    leftSide.hidden = !HAS_LEFT
    leftSplit.hidden = !HAS_LEFT
    if (!width) return
    const narrow = width < NARROW_PX
    if (!narrow) S.narrowOpen = null
    host.classList.toggle('is-narrow', narrow)
    const info = {}
    for (const side of ['left', 'right']) {
      if (!hasSide(side)) continue
      const bounds = panelBounds(width, panelSpec(side))
      const open = panelOpen(side)
      sideEl(side).classList.toggle('is-min', !open)
      info[side] = { bounds, open, w: open ? clampPanel(panelState(side).w, bounds) : PANEL_STRIP_PX }
    }
    if (narrow) {
      bodyBox.style.gridTemplateColumns = '0px 0px minmax(0, 1fr) 0px 0px'
      for (const side of Object.keys(info)) {
        const w = Math.max(160, Math.min(info[side].w, width - 48))
        sideEl(side).style.setProperty('--side-panel-w', `${Math.round(w)}px`)
      }
      S.panelWidths = { left: 0, right: 0 }
    } else {
      const part = (side) => (info[side]
        ? { w: info[side].w, lo: info[side].open ? info[side].bounds.lo : info[side].w, open: info[side].open }
        : { w: 0, lo: 0, open: false })
      const left = part('left')
      const right = part('right')
      const fitted = fitPanels(width, left, right, S.panelLast, STAGE_MIN_PX, PANEL_SPLIT_PX)
      const splitL = left.open ? PANEL_SPLIT_PX : 0
      const splitR = right.open ? PANEL_SPLIT_PX : 0
      bodyBox.style.gridTemplateColumns = `${fitted.left}px ${splitL}px minmax(0, 1fr) ${splitR}px ${fitted.right}px`
      for (const side of Object.keys(info)) sideEl(side).style.removeProperty('--side-panel-w')
      S.panelWidths = { left: fitted.left, right: fitted.right }
    }
    for (const side of ['left', 'right']) {
      const split = splitEl(side)
      const on = Boolean(info[side] && info[side].open && !narrow)
      split.classList.toggle('is-off', !on)
      split.tabIndex = on ? 0 : -1
      if (!info[side]) continue
      split.setAttribute('aria-valuemin', String(Math.round(info[side].bounds.lo)))
      split.setAttribute('aria-valuemax', String(Math.round(info[side].bounds.hi)))
      split.setAttribute('aria-valuenow', String(Math.round(S.panelWidths[side] || info[side].w)))
      sideEl(side).querySelector('.sle-side-strip').setAttribute('aria-expanded', String(info[side].open))
    }
    // 오른쪽 미배치 칸이 펼쳐져 있는가(`S.drawerOpen` — 서랍 몫·초점 되돌림·화면 확인이 본다).
    S.drawerOpen = panelOpen('right')
    trayBox.hidden = !S.drawerOpen
  }
  // 칸 폭을 바꾼다 — 한계 안, 무대 STAGE_MIN_PX 를 남기는 만큼까지. 끄는 동안은 S 에만, 놓을 때(`store`) 기억한다.
  function resizePanel(side, px, store) {
    const width = host.clientWidth || 0
    const bounds = panelBounds(width, panelSpec(side))
    const other = side === 'left' ? 'right' : 'left'
    const otherW = hasSide(other) ? (S.panelWidths && S.panelWidths[other]) || 0 : 0
    const splits = (panelOpen('left') ? PANEL_SPLIT_PX : 0) + (panelOpen('right') ? PANEL_SPLIT_PX : 0)
    const limit = dragLimit(width, otherW, splits, STAGE_MIN_PX, bounds.lo)
    panelState(side).w = Math.min(clampPanel(px, bounds), limit)
    S.panelLast = side
    layoutPanels()
    if (store) storePanel(side)
  }
  // 칸막이 — 끌기(포인터 캡처), 두 번 누르기 = 기본 폭, 키 ←/→(Shift 크게)·Home 최대·End 최소·Enter 접기. 키는 도면
  // 단축키(호기 옮기기)로 새지 않게 여기서 멈춘다. 설비 마스터 오른쪽 칸 칸막이와 같은 꼴이다.
  function bindSplit(side) {
    const split = splitEl(side)
    if (!split) return
    split.onpointerdown = (event) => {
      if (event.button !== 0 || isNarrow() || !panelOpen(side)) return
      event.preventDefault()
      split.setPointerCapture(event.pointerId)
      S.splitDrag = { side, pointerId: event.pointerId, startX: event.clientX, startW: sideEl(side).getBoundingClientRect().width, moved: false }
    }
    split.onpointermove = (event) => {
      const drag = S.splitDrag
      if (!drag || drag.side !== side || event.pointerId !== drag.pointerId) return
      const dx = event.clientX - drag.startX
      if (!drag.moved && Math.abs(dx) < DRAG_THRESHOLD_PX) return
      drag.moved = true
      split.classList.add('is-dragging')
      resizePanel(side, side === 'left' ? drag.startW + dx : drag.startW - dx, false)
    }
    split.onpointerup = split.onpointercancel = (event) => {
      const drag = S.splitDrag
      if (!drag || drag.side !== side || (event && event.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
      S.splitDrag = null
      split.classList.remove('is-dragging')
      if (drag.moved) storePanel(side)
    }
    split.onlostpointercapture = (event) => { if (S.splitDrag && S.splitDrag.side === side) split.onpointerup(event) }
    split.ondblclick = (event) => {
      event.preventDefault()
      panelState(side).w = null
      S.panelLast = side
      storePanel(side)
      layoutPanels()
    }
    split.onkeydown = (event) => {
      const bounds = panelBounds(host.clientWidth || 0, panelSpec(side))
      const now = (S.panelWidths && S.panelWidths[side]) || sideEl(side).getBoundingClientRect().width
      const action = splitKey(event.key, event.shiftKey, side, now, bounds)
      if (!action) return
      event.preventDefault()
      event.stopPropagation()
      if (action.fold) {
        setPanelOpen(side, false)
        sideEl(side).querySelector('.sle-side-strip').focus({ preventScroll: true })
        return
      }
      resizePanel(side, action.width, true)
    }
  }

  // ---------------------------------------------------------------- 왼쪽 칸 묶음 접힘(브라우저 안에서만)
  // 묶음(범례·도면 요소·선택·서식·격자·편집 영역·도움말)과 미배치 칸 도움말의 접힘 — `capa.space.sections.v1` = {이름: 접힘}. 처음엔
  // 도움말 둘만 접힘. 층 보기(범례 하나)는 묶음 머리가 없어 늘 펼침이다.
  function sectionFolded(name, fallback) {
    if (!S.sections) {
      try {
        const value = JSON.parse(window.localStorage.getItem(SECTIONS_STORE_KEY) || 'null')
        S.sections = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
      } catch {
        S.sections = {}
      }
    }
    return typeof S.sections[name] === 'boolean' ? S.sections[name] : fallback
  }
  function storeSection(name, folded) {
    sectionFolded(name, folded)
    S.sections[name] = Boolean(folded)
    try {
      window.localStorage.setItem(SECTIONS_STORE_KEY, JSON.stringify(S.sections))
    } catch {
      // 이 마운트 안에서만 기억한다.
    }
  }
  function applySections() {
    for (const section of host.querySelectorAll('.sle-sec')) {
      const name = section.dataset.sec
      const head = section.querySelector('.sle-sec-head')
      const folded = !VIEW && sectionFolded(name, name === 'help')
      section.classList.toggle('is-folded', folded)
      head.setAttribute('aria-expanded', String(!folded))
      head.onclick = () => {
        const next = !section.classList.contains('is-folded')
        storeSection(name, next)
        section.classList.toggle('is-folded', next)
        head.setAttribute('aria-expanded', String(!next))
      }
    }
  }

  // ---------------------------------------------------------------- 범례·도움말(왼쪽 칸)
  // 범례 칸은 파이썬이 보낸 꼴(`data.legend` — 견본 꼴 `css`·안 글자 `inner`·글 `label`, 끝 줄 `asOf`)이다. 견본 꼴은
  // `style.cssText`, 글은 `textContent` 로만 단다(HTML 로 읽지 않는다). epoch 밖이라 기준일·체크가 바뀐 회차마다 온다 — 같은
  // 값이면 다시 쓰지 않는다. 범례가 없으면(FAB) 묶음째 숨긴다.
  function drawLegend() {
    const legend = data.legend && Array.isArray(data.legend.entries) ? data.legend : null
    legendSection.hidden = !legend
    const key = legend ? JSON.stringify(legend) : ''
    if (S.legendKey === key) return
    S.legendKey = key
    if (!legend) { legendBox.replaceChildren(); return }
    const nodes = legend.entries.map((entry) => {
      const row = document.createElement('div')
      row.className = 'sle-legend-item'
      const swatch = document.createElement('span')
      swatch.setAttribute('aria-hidden', 'true')
      swatch.style.cssText = String(entry.css || '')
      swatch.textContent = String(entry.inner || '')
      const text = document.createElement('span')
      text.textContent = String(entry.label || '')
      row.append(swatch, text)
      return row
    })
    if (legend.asOf) {
      const day = document.createElement('div')
      day.className = 'sle-legend-asof'
      day.textContent = String(legend.asOf)
      nodes.push(day)
    }
    legendBox.replaceChildren(...nodes)
  }
  // 도움말 — 편집 안내 문단(`GUIDE`)과 단축키 목록(`HINT`). 마운트마다 한 번 쓴다.
  function buildHelp() {
    if (VIEW || helpBox.childElementCount) return
    const lead = document.createElement('p')
    lead.textContent = GUIDE
    const list = document.createElement('ul')
    list.className = 'sle-help-keys'
    for (const part of HINT.split(' · ')) {
      const li = document.createElement('li')
      li.textContent = part
      list.append(li)
    }
    helpBox.replaceChildren(lead, list)
  }

  // ---------------------------------------------------------------- 스크롤 고정(도구 줄 「고정」)
  // 켜면 본문 스크롤 칸을 굴려 편집기 맨 위를 가림 끝(화면 탭 줄 아래) + 8px 에 맞추고, `<html data-space-lock="1">` 을 달아
  // 페이지 서식(파이썬 `space_lock_style`)이 본문 스크롤을 막게 한다 — 다른 화면으로 가면 그 서식이 사라져 정리 함수가 돌지
  // 않아도 풀린다. 무대는 창 높이에 맞춘다(고른 높이·기억은 그대로). 고정은 이 마운트에만 둔다 — 다시 마운트되면(층·FAB 바꾸기,
  // 배치 편집 켜고 끄기) 풀린 채다. Streamlit DOM 에 기대는 곳(1.63 — 판올림에서 다시 본다): 본문 스크롤 칸
  // `section[data-testid="stMain"]`, 화면 탭 줄 `.st-key-page_tabs_strip`(sticky), 본문 내용 상자
  // `[data-testid="stMainBlockContainer"]`, 컴포넌트가 같은 문서라 `document` 를 본다.
  const docEl = document.documentElement
  if (!S.lockReady) {
    S.lockReady = true
    if (!S.lock) docEl.removeAttribute(LOCK_ATTR)
  }
  const mainScroller = () => document.querySelector('[data-testid="stMain"]')
  // 가림 끝(창 위에서 px) — 화면 탭 줄이 sticky 면 붙었을 때의 아래 끝(본문 칸 위 + 붙는 top + 높이), 아니면 지금 아래 끝.
  function coverBottom() {
    const strip = document.querySelector('.st-key-page_tabs_strip')
    if (!strip) return 0
    const rect = strip.getBoundingClientRect()
    const style = typeof window.getComputedStyle === 'function' ? window.getComputedStyle(strip) : null
    const stuck = style && style.position === 'sticky' ? parseFloat(style.top) : NaN
    if (!Number.isFinite(stuck)) return rect.bottom
    const main = mainScroller()
    return (main ? main.getBoundingClientRect().top : 0) + stuck + rect.height
  }
  function lockNote() {
    return S.lock && data.pendingSave ? '저장 안 한 배치가 있습니다 — 고정을 풀고 위 상자에서 저장하세요' : ''
  }
  function showLockNote() {
    if (VIEW) setText(statusBox, lockNote())
    else updateStatus()
  }
  function alignLock() {
    if (!S.lock) return
    const main = mainScroller()
    const top = lockTop(coverBottom())
    const offset = stage.getBoundingClientRect().top - host.getBoundingClientRect().top
    S.lockH = lockHeight(window.innerHeight, top + offset, statusBox.getBoundingClientRect().height, MIN_DRAG_H)
    setStageHeight(S.lockH)
    if (main) {
      const delta = host.getBoundingClientRect().top - top
      if (Math.abs(delta) >= 1) main.scrollTop += delta
    }
    if (measurePort()) applyView()
  }
  // 고정 중 위 칸(저장 안 한 배치 상자 등)이 서거나 사라져 편집기가 밀리면 다시 맞춘다 — 본문 내용 상자의 크기 관찰.
  function watchMain(on) {
    if (S.mainRo) S.mainRo.disconnect()
    S.mainRo = null
    if (!on || typeof ResizeObserver !== 'function') return
    const box = document.querySelector('[data-testid="stMainBlockContainer"]')
    if (!box) return
    S.mainRo = new ResizeObserver(() => {
      if (S.lockFrame) return
      S.lockFrame = requestAnimationFrame(() => {
        S.lockFrame = 0
        if (S.lock && S.relock) S.relock()
      })
    })
    S.mainRo.observe(box)
  }
  function setLock(on) {
    S.lock = Boolean(on)
    host.classList.toggle('is-locked', S.lock)
    lockButton.setAttribute('aria-pressed', String(S.lock))
    if (S.lock) {
      docEl.setAttribute(LOCK_ATTR, '1')
      alignLock()
    } else {
      docEl.removeAttribute(LOCK_ATTR)
      S.lockH = null
      if (fitStage()) applyView()
    }
    watchMain(S.lock)
    showLockNote()
  }

  // ---------------------------------------------------------------- 두 옆 칸(왼쪽 도구 · 오른쪽 미배치)
  // 접힌 띠를 누르면 펴고 칸 머리 끝 단추로 접는다. 초점은 짝 단추로 옮긴다. 좁은 화면 겹침 서랍은 Esc 로도 접는다(넓은 화면의
  // 고정 칸은 Esc 가 검색어·선택 풀기다).
  for (const [side, box] of [['left', leftSide], ['right', drawer]]) {
    if (!box) continue
    const strip = box.querySelector('.sle-side-strip')
    const fold = box.querySelector('.sle-side-fold')
    strip.onclick = () => {
      setPanelOpen(side, true)
      fold.focus({ preventScroll: true })
    }
    fold.onclick = () => {
      setPanelOpen(side, false)
      strip.focus({ preventScroll: true })
    }
    box.onkeydown = (event) => {
      if (event.key !== 'Escape' || !isNarrow() || !panelOpen(side) || S.drag) return
      event.preventDefault()
      event.stopPropagation()
      setPanelOpen(side, false)
      strip.focus({ preventScroll: true })
    }
  }
  bindSplit('left')
  bindSplit('right')
  // 미배치 칸 도움말(「i」) — 칩 목록 자리를 먹지 않게 처음엔 접힘, 펴고 접은 것은 기억한다(묶음 접힘과 같은 칸).
  const trayHintOpen = sectionFolded('trayHint', true) === false
  trayHint.hidden = !trayHintOpen
  trayInfo.setAttribute('aria-expanded', String(trayHintOpen))
  trayInfo.onclick = () => {
    const open = trayHint.hidden
    trayHint.hidden = !open
    trayInfo.setAttribute('aria-expanded', String(open))
    storeSection('trayHint', !open)
  }
  applySections()
  drawLegend()
  buildHelp()
  // 왼쪽 칸 이름 — 층 보기는 범례 하나라 「범례」, 편집은 「도구」.
  const leftName = VIEW ? '범례' : '도구'
  setText(q('.sle-side.is-left .sle-side-title'), leftName)
  setText(q('.sle-side.is-left .sle-side-strip-text'), leftName)
  setAttr(leftSide, 'aria-label', VIEW ? '범례 칸' : '도구 칸')
  setAttr(leftSplit, 'aria-label', VIEW ? '왼쪽 범례 칸 폭' : '왼쪽 도구 칸 폭')
  lockButton.onclick = () => setLock(!S.lock)
  host.classList.toggle('is-locked', S.lock)
  lockButton.setAttribute('aria-pressed', String(Boolean(S.lock)))
  S.relock = alignLock
  traySearch.value = S.trayQuery || ''
  traySearch.oninput = () => {
    S.trayQuery = traySearch.value
    applyTrayFilter()
    trayScroll.scrollTop = 0
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
  layoutPanels()

  // ---------------------------------------------------------------- 「호기 정보」 창(층 보기·편집 — 브라우저 안에서만)
  // 도면 위에 겹친 창(`.sle-sheet` — 편집기 몸 안에 묶임)이다. 「고른 호기」 는 도면에서 고른 호기의 칸(21칸 —
  // 모듈이면 같은 Main 설비 줄 전부, 편집에서 여럿 고르면 여러 줄), 「필터」 는 칸 머리 ▾ 로 거른(엑셀 자동 필터 꼴 — 칸 안 OR,
  // 칸끼리 AND, 날짜·숫자 칸은 범위도) 호기 목록이다. 필터가 걸린 동안 맞는 호기에 테(`is-filter-hit`)를 두르고 나머지를
  // 흐린다(`is-filter-out` — 필요 단축 흐림과 곱해진다). 편집에서는 오른쪽 미배치 칸 칩도 테를 두르고 칸 머리에 맞는 수를 단다.
  // 창을 닫으면 강조를 끄고 필터는 남긴다(다시 열면 돌아온다), 접으면 강조는 남는다. 목록 줄을 누르면 그 호기를 고르고 화면을
  // 그리로 옮긴다(보기는 필요 단축 칸으로도 알린다 — `notePick`). 읽기만이라 편집 권한과 상관없이 같다.
  function sheetLoad() {
    if (!S.sheetState) {
      let raw = null
      try {
        raw = window.sessionStorage.getItem(SHEET_STATE_KEY)
      } catch {
        raw = null
      }
      S.sheetState = storedSheetState(raw)
    }
    if (!S.sheetWin) {
      let raw = null
      try {
        raw = window.localStorage.getItem(SHEET_WIN_KEY)
      } catch {
        raw = null
      }
      S.sheetWin = storedSheetWin(raw)
    }
  }
  function sheetSaveState() {
    try {
      window.sessionStorage.setItem(SHEET_STATE_KEY, JSON.stringify(S.sheetState))
    } catch {
      // 이 마운트 안에서만 기억한다.
    }
  }
  function sheetSaveWin() {
    try {
      window.localStorage.setItem(SHEET_WIN_KEY, JSON.stringify(S.sheetWin))
    } catch {
      // 이 마운트 안에서만 기억한다.
    }
  }
  // data `sheet` 를 받는다 — 같은 값이면 그대로(회차마다 오지만 기준일·필터·편집본이 바뀐 회차에만 다르다).
  function adoptSheet() {
    const key = SHEET ? JSON.stringify(SHEET) : ''
    if (S.sheetDataKey === key) return
    S.sheetDataKey = key
    S.sheetView = ''
    S.sheetChipKey = ''
    S.sheet = SHEET
      ? {
          columns: SHEET.columns,
          rows: SHEET.rows,
          cut: Number(SHEET.cut) || 0,
          placeIdx: SHEET.columns.findIndex((column) => column.name === SHEET_PLACE),
          // 도면에 선 호기 CSV(파이썬이 지은 글 그대로 — 옛 도면 아래 내려받기와 같은 칸·줄). 없으면 그 줄이 꺼진다.
          csv: SHEET.csv && typeof SHEET.csv.text === 'string' && typeof SHEET.csv.file === 'string' ? SHEET.csv : null,
        }
      : null
  }
  // 창의 줄 — 배치 편집에서는 「도면」 칸을 브라우저가 쥔 편집으로 덮어 쓴다(트레이로 뺀 호기는 미배치, 다른 층으로 보낸 호기는
  // 「→ 그 층」). 보기는 받은 그대로다.
  function sheetRows() {
    const sheet = S.sheet
    if (!sheet) return []
    if (VIEW || sheet.placeIdx < 0) return sheet.rows
    return sheet.rows.map((row) => {
      const item = S.items.get(row.id)
      if (!item || !isUnit(item)) return row
      const place = item.moveTo ? `→ ${item.moveTo}` : onCanvas(item) ? '배치' : '미배치'
      if (row.cells[sheet.placeIdx] === place) return row
      const cells = row.cells.slice()
      cells[sheet.placeIdx] = place
      return { ...row, cells }
    })
  }
  // 고른 호기 id(고른 차례) — 보기는 하나, 편집은 여럿(모듈 묶음은 묶음에 하나 — 줄은 형제까지 `pickedRows` 가 붙인다).
  function pickedUnitIds() {
    const ids = [...S.selection].filter((id) => isUnit(S.items.get(id) || {}))
    if (S.selected && ids.includes(S.selected)) return [S.selected, ...ids.filter((id) => id !== S.selected)]
    return ids
  }
  // 도면 강조 — 창이 열려 있고(접힘 포함) 「도면에서 강조」 가 켜졌고 필터가 걸렸을 때 맞는 호기 id 묶음, 아니면 null.
  function currentHits() {
    const state = S.sheetState
    if (!S.sheet || !state || !state.open || !state.hl) return null
    return sheetHits(sheetRows(), S.sheet.columns, state.filters)
  }
  function paintFilter(group, id) {
    const item = S.items.get(id)
    if (!group || !item || !isUnit(item)) return
    const hits = S.filterHits
    const state = !hits ? '' : hits.has(id) ? 'hit' : 'out'
    if (group.__filter === state) return
    group.__filter = state
    group.classList.toggle('is-filter-hit', state === 'hit')
    group.classList.toggle('is-filter-out', state === 'out')
  }
  function paintChipFilter(chip) {
    const hits = S.filterHits
    const hit = Boolean(hits && chip.__ids && chip.__ids.some((id) => hits.has(id)))
    chip.classList.toggle('is-filter-hit', hit)
  }
  function refreshHits() {
    S.filterHits = currentHits()
    for (const [id, group] of S.groups) paintFilter(group, id)
    let inTray = 0
    for (const chip of trayList.children) {
      paintChipFilter(chip)
      if (chip.classList.contains('is-filter-hit')) inTray += chip.__ids.filter((id) => S.filterHits.has(id)).length
    }
    trayHits.hidden = !S.filterHits
    setText(trayHits, S.filterHits ? `· 필터 맞음 ${inTray}` : '')
  }
  // 창 처음 자리·크기 — 무대 왼쪽 아래, 720×320(무대·몸이 작으면 줄인다).
  function sheetDefault() {
    const bodyH = bodyBox.clientHeight || 0
    const w = Math.min(SHEET_DEF_W, Math.max(SHEET_MIN_W, (stage.clientWidth || 0) - 16))
    const h = Math.min(SHEET_DEF_H, Math.max(SHEET_MIN_H, bodyH - 16))
    return { x: (stage.offsetLeft || 0) + 8, y: bodyH - h - 8, w, h }
  }
  function layoutSheet() {
    if (!sheetBox || sheetBox.hidden) return
    const head = sheetHead.offsetHeight || SHEET_HEAD_PX
    const geom = clampSheet(S.sheetWin, sheetDefault(), bodyBox.clientWidth || 0, bodyBox.clientHeight || 0, SHEET_MIN_W, SHEET_MIN_H, head)
    S.sheetGeom = geom
    sheetBox.classList.toggle('is-min', Boolean(S.sheetWin.min))
    sheetMin.setAttribute('aria-expanded', String(!S.sheetWin.min))
    sheetMin.setAttribute('aria-label', S.sheetWin.min ? '호기 정보 창 펴기' : '호기 정보 창 접기')
    sheetMin.textContent = S.sheetWin.min ? '□' : '–'
    sheetBox.style.left = `${geom.x}px`
    sheetBox.style.top = `${geom.y}px`
    sheetBox.style.width = `${geom.w}px`
    sheetBox.style.height = S.sheetWin.min ? '' : `${geom.h}px`
    if (S.sheetMenu) placeMenu()
  }
  function setSheetNote(text) {
    setText(sheetNote, text || '')
  }
  // 창을 그린다. 같은 그림(탭·줄·필터·칸 값)이면 표를 다시 만들지 않고 고른 줄 표시만 고친다. 끄는 동안은 쉰다(놓으면
  // 상태 줄과 함께 다시 부른다).
  function renderSheet() {
    if (!sheetBox) return
    sheetLoad()
    const state = S.sheetState
    const open = Boolean(S.sheet && state.open)
    sheetToggle.hidden = !S.sheet
    sheetToggle.setAttribute('aria-pressed', String(open))
    if (sheetBox.hidden === open) {
      sheetBox.hidden = !open
      if (open) layoutSheet()
    }
    if (!open) {
      closeMenu()
      closeCsvMenu()
      refreshHits()
      return
    }
    if (S.drag) return
    const rows = sheetRows()
    const columns = S.sheet.columns
    const ids = pickedUnitIds()
    const picked = VIEW ? pickedRows(rows, ids[0]) : pickedRowsMany(rows, ids)
    const active = sheetActive(columns, state.filters)
    const matched = active.length ? sheetMatch(rows, columns, state.filters) : rows
    const filterTab = state.tab === 'filter'
    sheetBox.dataset.tab = state.tab
    for (const tab of sheetTabs) {
      const on = tab.dataset.tab === state.tab
      tab.setAttribute('aria-selected', String(on))
      tab.tabIndex = on ? 0 : -1
      const n = tab.dataset.tab === 'filter' ? (active.length ? matched.length : '') : picked.length || ''
      setText(tab.querySelector('.sle-sheet-tab-n'), String(n))
    }
    // 위 줄 — 필터: 걸린 칸 칩(누르면 그 칸 필터를 지움)·모두 지우기·강조 체크·맞는 수, 고른 호기: 고른 수.
    const shown = filterTab ? matched : picked
    // 「CSV」 의 「보이는 줄」 은 지금 탭에 보이는 줄이다.
    S.sheetShown = shown
    if (filterTab) {
      const counts = S.sheet.placeIdx >= 0 ? countBy(matched, S.sheet.placeIdx) : new Map()
      const parts = [`${active.length ? '맞음' : '전체'} ${matched.length}줄`]
      for (const [place, n] of counts) parts.push(`${place || '자리 모름'} ${n}`)
      setText(sheetCount, parts.join(' · '))
    } else setText(sheetCount, picked.length ? `고른 호기 ${ids.length}개 · ${picked.length}줄` : '')
    const chipKey = JSON.stringify(active.map((name) => [name, state.filters[name]]))
    if (S.sheetChipKey !== chipKey) {
      S.sheetChipKey = chipKey
      sheetChips.replaceChildren(...active.map((name) => {
        const rule = state.filters[name]
        const chip = document.createElement('button')
        chip.type = 'button'
        chip.className = 'sle-sheet-chip'
        chip.dataset.col = name
        // 값은 열쇠(소문자)가 아니라 이 층에서 처음 만난 꼴로 보인다(이 층에 없는 값은 열쇠 그대로).
        const index = columns.findIndex((column) => column.name === name)
        const shownAs = new Map(index >= 0 ? distinctValues(rows, index, columns[index].type).map((value) => [value.key, value.text]) : [])
        const words = []
        if (Array.isArray(rule.values)) words.push(rule.values.length ? rule.values.map((key) => shownAs.get(key) || (key === '' ? '(빈칸)' : key)).join(', ') : '없음')
        if (sheetRangeOn(rule)) words.push(`${rule.from || ''}~${rule.to || ''}`)
        chip.textContent = `${name}: ${words.join(' · ')} ×`
        chip.title = `${name} 필터 지우기`
        return chip
      }))
    }
    sheetClear.disabled = !active.length
    sheetHl.checked = Boolean(state.hl)
    // 표 — 같은 그림이면 고른 줄 표시만 고친다(받은 표가 바뀌면 `adoptSheet` 가 그림 열쇠를 지운다).
    const placeSig = !VIEW && S.sheet.placeIdx >= 0 ? rows.map((row) => row.cells[S.sheet.placeIdx]).join('|') : ''
    const viewKey = JSON.stringify([state.tab, filterTab ? state.filters : ids, placeSig])
    if (S.sheetView !== viewKey) {
      S.sheetView = viewKey
      drawSheetTable(columns, shown, filterTab)
      sheetEmpty.hidden = shown.length > 0
      setText(sheetEmpty, filterTab
        ? (rows.length ? '맞는 호기가 없습니다 — 칸 머리 ▾ 에서 필터를 바꾸세요.' : '이 층에 호기가 없습니다.')
        : '도면에서 호기를 누르세요(편집에서는 Shift/Ctrl+클릭으로 여럿).')
      sheetCut.hidden = !S.sheet.cut
      setText(sheetCut, S.sheet.cut ? `${S.sheet.cut}줄 더 있습니다 — 「CSV」 의 도면에 선 호기로 보세요.` : '')
    }
    const current = new Set(ids)
    for (const tr of sheetBodyRows.children) tr.classList.toggle('is-current', current.has(tr.dataset.id))
    if (S.sheetMenu) renderMenu()
    refreshHits()
  }
  function drawSheetTable(columns, rows, menus) {
    const filters = S.sheetState.filters
    const head = document.createElement('tr')
    for (const [index, column] of columns.entries()) {
      const th = document.createElement('th')
      th.scope = 'col'
      const name = document.createElement('span')
      name.textContent = column.name
      th.append(name)
      if (menus) {
        const on = sheetRuleOn(filters[column.name])
        const button = document.createElement('button')
        button.type = 'button'
        button.className = on ? 'sle-sheet-funnel is-on' : 'sle-sheet-funnel'
        button.dataset.col = String(index)
        button.setAttribute('aria-haspopup', 'dialog')
        button.setAttribute('aria-label', `${column.name} 필터${on ? ' — 걸림' : ''}`)
        button.title = on ? `${column.name} 필터가 걸렸습니다 — 눌러서 바꾸기` : `${column.name} 필터`
        button.textContent = on ? '▼' : '▾'
        th.append(button)
        if (on) th.classList.add('is-filtered')
      }
      head.append(th)
    }
    sheetHeadRow.replaceChildren(head)
    const body = document.createDocumentFragment()
    for (const row of rows) {
      const tr = document.createElement('tr')
      tr.dataset.id = row.id
      tr.tabIndex = 0
      for (const value of row.cells) {
        const td = document.createElement('td')
        const text = sheetText(value)
        td.textContent = text
        if (text.length > 18) td.title = text
        if (typeof value === 'number') td.className = 'is-num'
        tr.append(td)
      }
      body.append(tr)
    }
    sheetBodyRows.replaceChildren(body)
  }
  function openSheet(tab) {
    sheetLoad()
    if (!S.sheet) return
    S.sheetState.open = true
    if (tab) S.sheetState.tab = tab
    if (S.sheetWin.min && tab) {
      S.sheetWin.min = false
      sheetSaveWin()
    }
    sheetSaveState()
    S.sheetView = ''
    renderSheet()
    layoutSheet()
  }
  function closeSheet() {
    sheetLoad()
    S.sheetState.open = false
    sheetSaveState()
    setSheetNote('')
    renderSheet()
  }
  // 도면 점 p(화면 좌표 {x, top})에 선 호기(겹치면 위에 그린 것) — 두 번 누르기가 호기 위였는가(포인터 캡처로 dblclick 의
  // target 은 캔버스다). 보기에서 기준일에 숨은 호기는 건너뛴다.
  function unitAt(p) {
    if (!p) return null
    const y = H() - p.top
    let found = null
    for (const item of S.items.values()) {
      if (!isUnit(item) || !onCanvas(item)) continue
      const group = S.groups.get(item.id)
      if (VIEW && group && group.__visible === false) continue
      if (p.x >= item.x && p.x <= item.x + item.w && y >= item.y && y <= item.y + item.h) found = item
    }
    return found
  }
  // 목록 줄 → 그 호기. 도면에 선 호기는 고르고 화면을 그리로(「고른 곳 보기」 와 같은 여백, 배율은 LIST_ROW_ZOOM 까지),
  // 편집의 미배치 호기는 오른쪽 칸 그 칩으로, 그 밖은 창 아래 한 줄로 알린다.
  function goToUnit(id) {
    const item = S.items.get(id)
    const row = S.sheet ? sheetRows().find((one) => one.id === id) : null
    const place = row && S.sheet.placeIdx >= 0 ? sheetText(row.cells[S.sheet.placeIdx]) : ''
    setSheetNote('')
    if (item && isUnit(item) && onCanvas(item)) {
      const group = S.groups.get(id)
      if (VIEW && group && group.__visible === false) {
        setSheetNote(`${id} — 이 기준일에는 도면에 보이지 않습니다(반입 전 겹침·도면 이탈)`)
        return
      }
      select(id)
      if (VIEW) notePick()
      zoomToBox(bbox(VIEW ? [item] : expanded([item])), LIST_ROW_ZOOM)
      // 창이 그 호기를 덮으면 창이 덮지 않은 띠로 화면을 민다(옮길 수 있는 만큼).
      const rect = group && group.querySelector('.sle-rect').getBoundingClientRect()
      const shift = rect && !S.sheetWin.min ? clearOfSheet(stage.getBoundingClientRect(), sheetBox.getBoundingClientRect(), rect) : null
      if (shift) panBy(shift.dx * unitsPerPx(), shift.dy * unitsPerPx())
      return
    }
    if (item && isUnit(item) && !VIEW && !item.moveTo) {
      select(id)
      setPanelOpen('right', true)
      const chip = [...trayList.children].find((one) => one.__ids && one.__ids.includes(id))
      if (chip) {
        if (chip.hidden && traySearch.value) {
          traySearch.value = ''
          S.trayQuery = ''
          applyTrayFilter()
        }
        const top = chip.offsetTop - trayScroll.offsetTop
        if (top < trayScroll.scrollTop || top + chip.offsetHeight > trayScroll.scrollTop + trayScroll.clientHeight) {
          trayScroll.scrollTop = Math.max(0, top - trayScroll.clientHeight / 3)
        }
        chip.classList.remove('is-flash')
        void chip.offsetWidth
        chip.classList.add('is-flash')
      }
      setSheetNote(`${id} — 오른쪽 미배치 칸에 있습니다`)
      return
    }
    setSheetNote(`${id} — 도면에 없음(${place || '미배치'})`)
  }
  function setRule(name, rule) {
    const kept = {}
    if (Array.isArray(rule.values)) kept.values = rule.values
    if (rangeEnd(rule.from)) kept.from = rangeEnd(rule.from)
    if (rangeEnd(rule.to)) kept.to = rangeEnd(rule.to)
    if (sheetRuleOn(kept)) S.sheetState.filters[name] = kept
    else delete S.sheetState.filters[name]
    sheetSaveState()
    renderSheet()
  }
  // ---- 칸 필터 펼침(엑셀 자동 필터 꼴) — 값 목록 체크(개수·찾기), 날짜·숫자 칸은 「부터·까지」 범위. 값 목록은 다른 칸 필터만 지난
  // 줄에서 센다. 모든 값을 고르면 그 칸 값 필터는 풀린다.
  function menuColumn() {
    return S.sheetMenu && S.sheet ? S.sheet.columns[S.sheetMenu.index] || null : null
  }
  function menuValues() {
    const column = menuColumn()
    if (!column) return []
    const base = sheetMatch(sheetRows(), S.sheet.columns, S.sheetState.filters, column.name)
    return distinctValues(base, S.sheetMenu.index, column.type)
  }
  function openMenu(index, anchor) {
    S.sheetMenu = { index, anchor: Number(index), find: '' }
    sheetMenuFind.value = ''
    sheetMenu.hidden = false
    renderMenu()
    placeMenu()
    sheetMenuFind.focus({ preventScroll: true })
  }
  function placeMenu() {
    if (!S.sheetMenu || sheetMenu.hidden) return
    const button = sheetHeadRow.querySelector(`.sle-sheet-funnel[data-col="${S.sheetMenu.index}"]`)
    const box = sheetBox.getBoundingClientRect()
    const at = button ? button.getBoundingClientRect() : box
    const width = Math.min(260, Math.max(200, box.width - 12))
    const left = Math.max(6, Math.min(box.width - width - 6, at.right - box.left - width))
    const top = Math.max(6, at.bottom - box.top + 2)
    sheetMenu.style.left = `${Math.round(left)}px`
    sheetMenu.style.top = `${Math.round(top)}px`
    sheetMenu.style.width = `${Math.round(width)}px`
    sheetMenu.style.maxHeight = `${Math.max(120, Math.round(box.height - top - 6))}px`
  }
  function closeMenu(focusBack) {
    if (!S.sheetMenu) return
    const index = S.sheetMenu.index
    S.sheetMenu = null
    sheetMenu.hidden = true
    if (focusBack) {
      const button = sheetHeadRow.querySelector(`.sle-sheet-funnel[data-col="${index}"]`)
      if (button) button.focus({ preventScroll: true })
    }
  }
  function renderMenu() {
    const column = menuColumn()
    if (!column) { closeMenu(); return }
    const rule = S.sheetState.filters[column.name] || {}
    setText(sheetMenuName, column.name)
    const chosen = Array.isArray(rule.values) ? new Set(rule.values) : null
    const find = S.sheetMenu.find.trim().toLowerCase()
    const nodes = []
    for (const value of menuValues()) {
      if (find && !value.text.toLowerCase().includes(find)) continue
      const label = document.createElement('label')
      label.className = 'sle-sheet-menu-item'
      const box = document.createElement('input')
      box.type = 'checkbox'
      box.dataset.key = value.key
      box.checked = !chosen || chosen.has(value.key)
      const text = document.createElement('span')
      text.textContent = value.text
      const count = document.createElement('span')
      count.className = 'sle-sheet-menu-n'
      count.textContent = String(value.count)
      label.append(box, text, count)
      nodes.push(label)
    }
    if (!nodes.length) {
      const none = document.createElement('p')
      none.className = 'sle-sheet-empty'
      none.textContent = '찾는 값이 없습니다.'
      nodes.push(none)
    }
    const active = host.getRootNode().activeElement
    const focusedKey = active && sheetMenuList.contains(active) ? active.dataset.key : undefined
    sheetMenuList.replaceChildren(...nodes)
    if (focusedKey !== undefined) {
      const again = [...sheetMenuList.querySelectorAll('input')].find((box) => box.dataset.key === focusedKey)
      if (again) again.focus({ preventScroll: true })
    }
    const ranged = column.type === 'date' || column.type === 'number'
    sheetMenuRange.hidden = !ranged
    if (ranged) {
      const kind = column.type === 'date' ? 'date' : 'number'
      for (const [input, end] of [[sheetMenuFrom, rule.from], [sheetMenuTo, rule.to]]) {
        if (input.type !== kind) input.type = kind
        if (!isFocused(input)) input.value = end || ''
      }
    }
  }
  // 고른 값 묶음 → 그 칸 규칙. 지금 목록 값을 모두 고르면 값 필터를 푼다.
  function setMenuValues(keys) {
    const column = menuColumn()
    if (!column) return
    const all = menuValues().map((value) => value.key)
    const rule = { ...(S.sheetState.filters[column.name] || {}) }
    const every = all.every((key) => keys.has(key))
    if (every) delete rule.values
    else rule.values = all.filter((key) => keys.has(key))
    setRule(column.name, rule)
  }
  function menuChosen() {
    const column = menuColumn()
    const rule = column ? S.sheetState.filters[column.name] || {} : {}
    return Array.isArray(rule.values) ? new Set(rule.values) : new Set(menuValues().map((value) => value.key))
  }
  function visibleMenuKeys() {
    return [...sheetMenuList.querySelectorAll('input')].map((box) => box.dataset.key)
  }
  // ---- 「CSV」 — 도면에 선 호기(파이썬이 지은 글, 모든 칸)와 보이는 줄(창의 칸 — `sheetCsv`). 파일은 브라우저 안에서 만든다(BOM + UTF-8 —
  // 엑셀에서 한글이 깨지지 않게). 접힌 창에서 누르면 창을 편다(펼침이 제목 줄 밑에 선다).
  function closeCsvMenu(focusBack) {
    if (!sheetCsvMenu || sheetCsvMenu.hidden) return
    sheetCsvMenu.hidden = true
    sheetCsvButton.setAttribute('aria-expanded', 'false')
    if (focusBack) sheetCsvButton.focus({ preventScroll: true })
  }
  function openCsvMenu() {
    closeMenu()
    if (S.sheetWin.min) {
      S.sheetWin.min = false
      sheetSaveWin()
      layoutSheet()
      renderSheet()
    }
    const shown = Array.isArray(S.sheetShown) ? S.sheetShown.length : 0
    sheetCsvAll.disabled = !(S.sheet && S.sheet.csv)
    sheetCsvShown.disabled = !shown
    setText(sheetCsvShown, `보이는 줄 ${shown}줄 · 창의 칸`)
    sheetCsvMenu.hidden = false
    // 펼침 오른쪽 끝을 CSV 단추 오른쪽 끝에 맞춘다(제목 줄 꼴 — 보기 · 편집 · 좁은 창 — 과 상관없이 단추 바로 밑).
    const frame = sheetBox.getBoundingClientRect()
    const anchor = sheetCsvButton.getBoundingClientRect()
    const inner = frame.left + sheetBox.clientLeft + sheetBox.clientWidth
    sheetCsvMenu.style.right = `${Math.max(0, Math.round(inner - anchor.right))}px`
    sheetCsvButton.setAttribute('aria-expanded', 'true')
    const first = [sheetCsvAll, sheetCsvShown].find((button) => !button.disabled)
    if (first) first.focus({ preventScroll: true })
  }
  function saveCsv(text, file) {
    const blob = new Blob([`\ufeff${text}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file
    link.hidden = true
    sheetBox.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
  function downloadCsv(which) {
    const sheet = S.sheet
    if (!sheet) return
    if (which === 'all' && sheet.csv) saveCsv(sheet.csv.text, sheet.csv.file)
    else if (which === 'shown' && Array.isArray(S.sheetShown) && S.sheetShown.length) {
      const base = sheet.csv ? sheet.csv.file.replace(/\.csv$/i, '') : 'space'
      saveCsv(sheetCsv(sheet.columns, S.sheetShown), `${base}_보이는줄.csv`)
    }
    closeCsvMenu(true)
  }
  if (sheetBox) {
    sheetToggle.onclick = () => (S.sheetState && S.sheetState.open ? closeSheet() : openSheet())
    sheetClose.onclick = () => {
      closeSheet()
      sheetToggle.focus({ preventScroll: true })
    }
    sheetMin.onclick = () => {
      sheetLoad()
      S.sheetWin.min = !S.sheetWin.min
      sheetSaveWin()
      closeMenu()
      closeCsvMenu()
      layoutSheet()
    }
    sheetCsvButton.onclick = () => (sheetCsvMenu.hidden ? openCsvMenu() : closeCsvMenu(true))
    sheetCsvMenu.onclick = (event) => {
      const button = event.target.closest ? event.target.closest('[data-csv]') : null
      if (button && !button.disabled) downloadCsv(button.dataset.csv)
    }
    for (const tab of sheetTabs) {
      tab.onclick = () => {
        sheetLoad()
        S.sheetState.tab = tab.dataset.tab === 'filter' ? 'filter' : 'picked'
        sheetSaveState()
        closeMenu()
        closeCsvMenu()
        if (S.sheetWin.min) {
          S.sheetWin.min = false
          sheetSaveWin()
          layoutSheet()
        }
        renderSheet()
      }
    }
    sheetClear.onclick = () => {
      S.sheetState.filters = {}
      sheetSaveState()
      closeMenu()
      renderSheet()
    }
    sheetHl.onchange = () => {
      S.sheetState.hl = sheetHl.checked
      sheetSaveState()
      renderSheet()
    }
    sheetChips.onclick = (event) => {
      const chip = event.target.closest ? event.target.closest('.sle-sheet-chip') : null
      if (!chip) return
      closeMenu()
      setRule(chip.dataset.col, {})
    }
    sheetHeadRow.onclick = (event) => {
      const button = event.target.closest ? event.target.closest('.sle-sheet-funnel') : null
      if (!button) return
      const index = Number(button.dataset.col)
      if (S.sheetMenu && S.sheetMenu.index === index) closeMenu()
      else openMenu(index, button)
    }
    sheetBodyRows.onclick = (event) => {
      const row = event.target.closest ? event.target.closest('tr[data-id]') : null
      if (row) goToUnit(row.dataset.id)
    }
    sheetBodyRows.onkeydown = (event) => {
      const row = event.target.closest ? event.target.closest('tr[data-id]') : null
      if (!row) return
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        goToUnit(row.dataset.id)
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        const next = event.key === 'ArrowDown' ? row.nextElementSibling : row.previousElementSibling
        if (next) next.focus({ preventScroll: false })
      }
    }
    sheetMenuFind.oninput = () => {
      if (!S.sheetMenu) return
      S.sheetMenu.find = sheetMenuFind.value
      renderMenu()
    }
    sheetMenuList.onchange = (event) => {
      const box = event.target
      if (!box || box.type !== 'checkbox') return
      const keys = menuChosen()
      if (box.checked) keys.add(box.dataset.key)
      else keys.delete(box.dataset.key)
      setMenuValues(keys)
    }
    q('.sle-sheet-menu-every').onclick = () => {
      const keys = menuChosen()
      for (const key of visibleMenuKeys()) keys.add(key)
      setMenuValues(keys)
    }
    q('.sle-sheet-menu-none').onclick = () => {
      const keys = menuChosen()
      for (const key of visibleMenuKeys()) keys.delete(key)
      setMenuValues(keys)
    }
    for (const [input, end] of [[sheetMenuFrom, 'from'], [sheetMenuTo, 'to']]) {
      input.onchange = () => {
        const column = menuColumn()
        if (!column) return
        setRule(column.name, { ...(S.sheetState.filters[column.name] || {}), [end]: input.value })
      }
    }
    q('.sle-sheet-menu-reset').onclick = () => {
      const column = menuColumn()
      if (!column) return
      setRule(column.name, {})
      sheetMenuFind.value = ''
      if (S.sheetMenu) S.sheetMenu.find = ''
      renderMenu()
    }
    q('.sle-sheet-menu-done').onclick = () => closeMenu(true)
    // 창 안의 키는 도면 단축키(호기 옮기기·지우기·실행 취소 …)로 새지 않는다. Esc 는 펼침을 먼저, 그다음 창을 닫는다.
    sheetBox.onkeydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (!sheetCsvMenu.hidden) closeCsvMenu(true)
        else if (S.sheetMenu) closeMenu(true)
        else {
          closeSheet()
          sheetToggle.focus({ preventScroll: true })
        }
      }
      event.stopPropagation()
    }
    // 펼침 밖을 누르면 펼침을 닫는다(창 안에서).
    sheetBox.onpointerdown = (event) => {
      if (S.sheetMenu && !sheetMenu.contains(event.target) && !(event.target.closest && event.target.closest('.sle-sheet-funnel'))) closeMenu()
      if (!sheetCsvMenu.hidden && !sheetCsvMenu.contains(event.target) && event.target !== sheetCsvButton) closeCsvMenu()
    }
    // 창 옮기기(제목 줄 끌기)·크기 바꾸기(오른쪽 아래 손잡이) — 편집기 몸 안으로 묶고 놓을 때 기억한다.
    const startSheetDrag = (kind) => (event) => {
      if (event.button !== 0) return
      if (kind === 'move' && event.target.closest && event.target.closest('button')) return
      event.preventDefault()
      const handle = kind === 'move' ? sheetHead : sheetGrip
      handle.setPointerCapture(event.pointerId)
      const geom = S.sheetGeom || sheetDefault()
      S.sheetDrag = { kind, pointerId: event.pointerId, x: event.clientX, y: event.clientY, geom: { ...geom } }
      sheetBox.classList.add(kind === 'move' ? 'is-moving' : 'is-sizing')
    }
    const moveSheetDrag = (event) => {
      const drag = S.sheetDrag
      if (!drag || event.pointerId !== drag.pointerId) return
      const dx = event.clientX - drag.x
      const dy = event.clientY - drag.y
      if (drag.kind === 'move') {
        S.sheetWin.x = drag.geom.x + dx
        S.sheetWin.y = drag.geom.y + dy
        S.sheetWin.w = drag.geom.w
        S.sheetWin.h = drag.geom.h
      } else {
        S.sheetWin.x = drag.geom.x
        S.sheetWin.y = drag.geom.y
        S.sheetWin.w = Math.min(drag.geom.w + dx, (bodyBox.clientWidth || 0) - drag.geom.x)
        S.sheetWin.h = Math.min(drag.geom.h + dy, (bodyBox.clientHeight || 0) - drag.geom.y)
      }
      layoutSheet()
    }
    const endSheetDrag = (event) => {
      const drag = S.sheetDrag
      if (!drag || (event && event.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
      S.sheetDrag = null
      sheetBox.classList.remove('is-moving', 'is-sizing')
      if (S.sheetGeom) Object.assign(S.sheetWin, S.sheetGeom)
      sheetSaveWin()
    }
    sheetHead.onpointerdown = startSheetDrag('move')
    sheetGrip.onpointerdown = startSheetDrag('size')
    for (const handle of [sheetHead, sheetGrip]) {
      handle.onpointermove = moveSheetDrag
      handle.onpointerup = handle.onpointercancel = endSheetDrag
      handle.onlostpointercapture = endSheetDrag
    }
    // 제목 줄을 두 번 누르면 접기·펴기(엑셀 창처럼).
    sheetHead.ondblclick = (event) => {
      if (event.target.closest && event.target.closest('button')) return
      sheetMin.onclick()
    }
  }
  adoptSheet()
  renderSheet()

  // ---------------------------------------------------------------- 기준일 줄(층 도면)·FAB 기준일
  // 층 상세 보기의 맨 위 줄은 페이더다(오늘 ±12개월, 하루 단위, 가운데 오늘). 끄는 동안 서버 회차는 없다 — 프레임마다
  // (requestAnimationFrame) 판정 부호가 바뀐 상자만 칠하고(`paintAsOf`), 손을 떼면(키는 멈춘 뒤) `setStateValue` 로
  // 기준일을 **한 번** 보낸다. 그 회차에 파이썬이 세션 기준일을 바꿔 범례·요약·「호기 정보」 창을 맞춘다. 배치 편집(층) 중에는
  // 같은 자리·같은 높이에 「기준일 … · 편집 중 고정」 줄이 선다. FAB 전체에는 페이더 없이 도구 줄에 기준일·「오늘로」·
  // 미확인 대수가 선다.
  const faderInput = q('.sle-fader-input')
  const faderTicks = q('.sle-fader-ticks')
  const faderDate = q('.sle-fader-date')
  const faderRel = q('.sle-fader-rel')
  const faderNote = q('.sle-fader-note')
  const faderToday = q('.sle-fader-today')
  const pinnedDate = q('.sle-pinned-date')
  const pinnedNote = q('.sle-pinned-note')
  // 고정 줄 뒷글 — 편집기는 HTML 글(「· 편집 중 고정 …」) 그대로, 「필요 단축」 보기는 `data.asOfPinned`.
  if (S.pinnedNoteDefault === undefined) S.pinnedNoteDefault = pinnedNote ? pinnedNote.textContent : ''
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
      if (text) {
        node.textContent = text
        // 글자를 트랙 폭에 맞춰 솎을 때(`fitFaderTicks`) 그 자리를 다시 셈한다.
        node.dataset.day = String(n)
      }
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

  // 눈금 글자 솎기(순수 함수). `tests/test_space_fader_ticks_js.py` 가 아래 두 표시 줄 사이를 떼어 node 로 돌린다 — 바깥
  // 이름을 쓰지 않는다.
  // <fader-ticks>
  // 숨길 눈금 글자(`spots` 차례의 참·거짓). 글자마다 {at: 트랙 위 가운데(px), w: 글자 폭(px), today: 「오늘」 글자인가},
  // width 는 트랙 폭(px), gap 은 글자 사이 최소 틈(px)이다. 「오늘」 을 먼저 세우고, 나머지는 왼쪽부터 트랙 안(양 끝)에 들고
  // 이미 세운 글자와 gap 안으로 붙지 않을 때만 세운다. 좁은 트랙(390px 창)에서 분기 글자가 서로 겹쳐 「26.0126.04…」 로
  // 뭉개졌다(E2E 결함). 넓은 트랙에서는 날짜 거리로 이미 뺀 글자(`buildFader`)뿐이라 하나도 숨기지 않는다.
  function crowdedTicks(spots, width, gap) {
    const hidden = spots.map(() => true)
    const kept = []
    const apart = (a, b) => a.at + a.w / 2 + gap <= b.at - b.w / 2 || b.at + b.w / 2 + gap <= a.at - a.w / 2
    const inside = (s) => s.at - s.w / 2 >= 0 && s.at + s.w / 2 <= width
    const order = spots.map((_, index) => index)
      .sort((a, b) => Number(Boolean(spots[b].today)) - Number(Boolean(spots[a].today)) || spots[a].at - spots[b].at)
    for (const index of order) {
      const spot = spots[index]
      if (!spot.today && !(inside(spot) && kept.every((other) => apart(spot, other)))) continue
      kept.push(spot)
      hidden[index] = false
    }
    return hidden
  }
  // </fader-ticks>

  // 눈금 글자 사이 최소 틈(px).
  const FADER_TICK_GAP_PX = 2
  // 눈금 글자를 지금 트랙 폭에 맞춰 솎는다(`crowdedTicks` — 숨긴 글자는 자리를 지킨 채 `is-crowded`). 회차마다 페이더를 그린
  // 뒤와 크기가 바뀔 때(`S.onResize`) 다시 잰다. 트랙이 그려지지 않았으면(고정 줄·편집) 그대로 둔다.
  function fitFaderTicks() {
    if (!FADER) return
    const width = faderTicks.clientWidth
    if (!width) return
    const labels = [...faderTicks.querySelectorAll('.sle-tick-label')]
    const lo = lowDay()
    const span = Math.max(highDay() - lo, 1)
    const spots = labels.map((node) => ({
      at: THUMB_PX / 2 + ((Number(node.dataset.day) - lo) / span) * (width - THUMB_PX),
      w: node.offsetWidth,
      today: node.classList.contains('is-today'),
    }))
    crowdedTicks(spots, width, FADER_TICK_GAP_PX).forEach((hide, index) => {
      labels[index].classList.toggle('is-crowded', hide)
    })
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
    fitFaderTicks()
  }
  if (PINNED) setText(pinnedDate, `기준일 ${S.asOf || '—'}`)
  // 층 편집 도구 줄 칩 「YYYY-MM-DD 고정」(핀 아이콘 — 결정 D12, 풍선이 「기준일은 편집하는 동안 고정」 을 말한다).
  if (!VIEW && !FAB) setText(pinChipDate, S.asOf || '—')
  if (pinnedNote) setText(pinnedNote, ASOF_PINNED ? ` · ${data.asOfPinned}` : S.pinnedNoteDefault)
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
  // 도구 줄이 넘치면 접는 차례를 하나씩 더한다. FAB 보기는 `is-fit1`~`is-fit6`(CSS 「FAB 도구 줄」) — 요약은 마지막에야
  // 준다(읽히는 앞머리까지만 줄이고, 그래도 넘치면 둘째 줄로 내린다). 층 보기는 접을 것이 요약뿐이라 넘치면 곧장 둘째
  // 줄(⑥)이다 — 390px 에서 확대 묶음 뒤 「배치 n대 · 미배치 · 점유율」 이 줄 밖으로 밀려 보이지 않았다(E2E r1). 편집은
  // `is-efit1`(「호기 정보」·「고정」 은 아이콘만, 기준일 칩은 날짜만 — 낭독기용 글은 남김) 다음 ⑥(빈 칸 뒤 「호기 정보」·
  // 「고정」·「적용」 을 둘째 줄로)이다 — 사이드바를 연 1100px 창의 층 편집에서 「고정」 이 줄 밖으로 밀려 스크롤 고정을
  // 켤 길이 없었다(도구 줄은 굴림 막대를 숨겨 옆으로 밀 수도 없다). 크기가 바뀔 때(`S.onResize` — 무대 높이를 재기 전)
  // 다시 잰다.
  const toolbar = q('.sle-toolbar')
  const FIT_STEPS = ['is-fit1', 'is-fit2', 'is-fit3', 'is-fit4', 'is-fit5', 'is-fit6']
  const EDIT_FIT_STEPS = ['is-efit1', 'is-fit6']
  function fitToolbar() {
    toolbar.classList.remove(...FIT_STEPS, ...EDIT_FIT_STEPS)
    if (!toolbar.clientWidth) return
    const steps = !VIEW ? EDIT_FIT_STEPS : FAB ? FIT_STEPS : FIT_STEPS.slice(-1)
    for (const step of steps) {
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
    // 도구 줄을 먼저 접는다 — 둘째 줄로 내리면 무대가 내려가 고정 높이(`alignLock`)가 달라진다.
    fitToolbar()
    layoutPanels()
    layoutSheet()
    if (S.lock) alignLock()
    else {
      const changed = S.heightDrag ? measurePort() : fitStage()
      if (changed) applyView()
    }
    fitFaderTicks()
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
  // 이번 실행에서 무대 크기가 달라졌으면(첫 실행·열 폭 변화) 바로 맞춘다. 고정 중이면 위 칸이 바뀌었을 수 있어 다시 맞춘다.
  S.onResize()
  updateStatus()
  if (VIEW) showLockNote()
  // Streamlit 은 마지막 실행이 돌려준 정리 함수를 컴포넌트를 내릴 때 부른다.
  return () => {
    if (S.ro) S.ro.disconnect()
    if (S.onWindowResize) window.removeEventListener('resize', S.onWindowResize)
    if (S.resizeFrame) cancelAnimationFrame(S.resizeFrame)
    S.ro = null
    S.onWindowResize = null
    S.resizeFrame = 0
    // 스크롤 고정은 이 마운트에만 — 내려가면 풀린다(속성을 걷지 못해도 페이지 서식이 사라지면 막지 않는다).
    if (S.lock) document.documentElement.removeAttribute(LOCK_ATTR)
    S.lock = false
    if (S.mainRo) S.mainRo.disconnect()
    S.mainRo = null
    if (S.lockFrame) cancelAnimationFrame(S.lockFrame)
    S.lockFrame = 0
  }
}
