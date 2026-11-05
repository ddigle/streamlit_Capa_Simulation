// 알림 칸(`components/alert_center.py`, 2026-11-03 결정 보드 D1 ~ D5). 파이썬이 페이지 앞에서 매 앱 전체 회차 data 로
// 등록 글 · 팔레트 · 이 세션의 변경(`changes`) · 콜백이 담은 사건 알림(`events`)을 주고, 이 JS 가 문서에 하나 있는 알림 칸을
// 세우거나 고친다(`window.__capaAlertCenter` — 다시 마운트돼도 하나다).
// - 알림창 한 꼴: 오른쪽 아래, 최대 3칸, 새 칸이 구석, 단계 이름 글자 + 단계 색 테두리. 누름을 받지 않는다(`pointer-events:
//   none`). 층은 Streamlit 대화상자 위다. 알림 8초 · 나머지 15초 뒤 걷는다.
// - 표지 훑기: 알림을 내는 자리(`alerts.state` · `alerts.flush` · `flash.render_flash`)가 스타일만 든 `st.html` 표지
//   (`style[data-capa-alerts]` — JSON, 팝업 본문 안에서는 칸 안의 숨은 `span`)를 그린다. 앱 뿌리의 회차 표지
//   (`data-test-script-state`)가 바뀔 때마다 문서를 **한 번** 훑는다 — 상시 MutationObserver 는 쓰지 않는다(큰 표 화면의 DOM 변화가 많다). 회차 시작에도 훑어 끊긴 회차의 표지를 놓치지
//   않는다. 같은 표지를 또 봐도 사건은 id, 상태는 지문으로 한 번만 띄운다.
// - 상태 알림(`kind: "state"`)은 「코드 + 범위 → 마지막 지문」 표로 바뀔 때만 띄운다. 같은 코드의 다른 범위가 오면 앞 범위는
//   「범위가 바뀜」 으로 해소, `active: false` 가 오면 「조건이 사라짐」 으로 해소한다.
// - 같은 사건 알림(코드 + 짧은 글)이 앞 알림창이 떠 있거나 사라진 지 반복 창(60초) 안에 다시 나면 새 칸을 쌓지 않고 앞 칸을
//   구석으로 옮겨 「×n」 을 붙이고 창 가장자리 테두리가 그 칸으로 모인다(D4 A — 한 겹 · 450ms · easeOutQuad · 한 번만). 움직임
//   줄이기에서는 움직이지 않는 윤곽만 1.6초 선다.
// - 기록(L1)은 이 브라우저 탭의 `sessionStorage` 다(D1 (가) — 200줄 · 12시간). 새로고침 · 테마 전환(새 세션)에도 남고 탭을 닫으면
//   사라진다. 읽기 · 쓰기는 모두 try/catch — 막힌 브라우저에서는 이 문서 안에만 쌓인다. 서버에는 아무것도 보내지 않는다(L2 는
//   usage-log 와 함께 — D6).
// - 머리 툴바: Guide 오른쪽에 `Alarm`(안 읽음 수 배지 · 패널), Guide 왼쪽에 바뀐 것이 있을 때만 서는 변경 칩(D5 (가) · 판). 차례는
//   파이썬 `theme_toggle.TOOLBAR_BUTTON_ORDER` 한 벌이다(다른 툴바 단추와 같은 규칙 — `capaToolbar.place`). 패널은 브라우저
//   안에서만 열고 닫아 파이썬 회차가 돌지 않는다.
// - 툴바 실제 폭을 재어 `--capa-toolbar-width`(px)와 `data-capa-toolbar` 를 문서 뿌리에 단다 — 머리 띠 두 줄 · 진행 막대
//   자리 규칙이 그 값으로 오른쪽을 비운다(`app_header`). 단추가 늘거나 줄어도 다시 잴 필요가 없다.
// - 화면 탭 줄 JS(`page_tabs.js`)는 같은 문서의 `window.__capaAlerts.raise(...)` 로 알린다(알림 칸이 아직 서지 않았으면
//   `window.__capaAlertQueue` 에 담아 두고 칸이 설 때 꺼낸다). 「그 화면으로」 는 탭 줄의 화면 이동(상한 · 떠나기 확인)에
//   `capa-open-page` 사건으로 맡긴다. 줄에 화면 안 탭(`tab`)이 있으면 그 화면에 닿은 회차가 끝난 뒤 이름이 맞는 탭 단추를
//   누른다(`stateful_tabs` — 보통 누름과 같다).
// - 알림에 딸린 표(`tables` — 본문에서 뺀 목록, 한 줄에 여럿일 수 있다)는 줄의 「… 보기」 단추가 표마다 펼치고 CSV 는 브라우저
//   안에서 만든다(서버를 부르지 않는다). 칸 머리 풍선(`help`)은 `title` 이다. 표는 코드마다 가장 새 줄에만 남기고, 탭 저장소가
//   넘치면 저장본에서 오래된 줄의 표부터 뺀다 — 줄은 남고, 그 화면이 다시 보내면 표가 다시 붙는다.
// - 「로그」 펼침의 「복사」 는 그 줄의 로그 전문(코드 · 단계 · 처음 · 마지막 · 화면 · 계기 · 범위 · 해소 · 원본 오류 · 전문)을
//   평문으로 클립보드에 넣는다(`navigator.clipboard`). 막히면(보안 연결이 아님 · DRM) 글을 고른 채 펼침 안에 두고 Ctrl+C 를
//   청한다 — `execCommand('copy')` 는 쓰지 않는다(막힌 클립보드에서도 참을 돌려 「복사했습니다」 가 거짓이 된다). 딸린 표는
//   복사에 넣지 않고 표 이름 · 행 수만 적는다(최대 2000행 — 표는 「CSV 내려받기」 가 맡는다).
// `// <alerts-…>` 구획은 DOM 을 모르는 순수 함수라 node 시험이 떼어 돌린다(`tests/test_alert_center_assets.py`).
const HOST_ID = 'capa-alert-host'
const APP_ROOT = '[data-testid="stApp"]'
const RUN_STATE = 'data-test-script-state'
const OPEN_PAGE_EVENT = 'capa-open-page'
const TOOLBAR_ATTRIBUTE = 'data-capa-toolbar'
const TOOLBAR_VARIABLE = '--capa-toolbar-width'
// 본 사건 id 를 이만큼까지 적는다(다시 보낸 표지를 또 띄우지 않는다).
const SEEN_LIMIT = 400
// 상태 표(코드 + 범위)를 이만큼까지 둔다 — 해소된 것부터 걷는다.
const STATE_LIMIT = 300
// 움직임 줄이기의 윤곽 · 도착 강조가 서 있는 시간과 도착 뒤 테두리를 걷는 시간.
const STILL_MS = 1600
const HIT_MS = 900
const FADE_MS = 160
// 툴바 슬롯이 늦게 그려지면 이 간격으로 이 횟수까지 다시 본다.
const PLACE_RETRY_MS = 200
const PLACE_RETRIES = 40
// 「그 화면으로」 의 탭 고르기를 이만큼 기다린다(그 화면 회차가 끝나기를).
const PENDING_TAB_MS = 20000
// 「복사했습니다」 가 서 있는 시간.
const COPIED_MS = 1800
const TAB_BUTTON = '[data-testid="stTabs"] [role="tab"]'

// <alerts-rows>
// 사건 알림의 「같은 알림」 열쇠 — 코드 + 짧은 글.
function eventKey(note) {
  return String(note.code || '') + '\u0000' + String(note.short || '')
}
// 자리에 마크만 남은 오류(`keep`)는 Alarm 줄이 전문의 유일한 자리다. 본 적 있는 글이어도 그 줄이
// 없으면(보관 끝 · 같은 짧은 글의 다른 오류가 덮음) 다시 세운다. 알림창은 띄우지 않는다.
function keptRowMissing(rows, note) {
  if (!note.keep) return false
  const key = eventKey(note)
  return !rows.some((row) => row.kind === 'event' && eventKey(row) === key && row.noteId === note.id)
}
// 상태 알림의 표 열쇠 — 코드 + 범위(파이썬이 해시해 보낸다).
function stateKey(note) {
  return String(note.code || '') + '|' + String(note.scope || '')
}
// 보관 — `maxMs` 보다 오래된 줄을 걷고 최신순 `maxRows` 줄만 남긴다.
function pruneRows(rows, now, maxRows, maxMs) {
  const kept = (Array.isArray(rows) ? rows : []).filter(
    (row) => row && typeof row.last === 'number' && now - row.last <= maxMs,
  )
  kept.sort((a, b) => b.last - a.last)
  return kept.slice(0, Math.max(0, maxRows))
}
// 상태 표 한 칸(`entry` — {fp, active})과 새 표지로 할 일: 'new'(처음 · 해소 뒤 다시) · 'change'(지문이 바뀜) · 'same' ·
// 'resolved'(있던 조건이 사라짐) · 'none'(없던 조건이 여전히 없음).
function stateVerdict(entry, note) {
  if (note.active) {
    if (!entry || !entry.active) return 'new'
    return entry.fp === note.fp ? 'same' : 'change'
  }
  return entry && entry.active ? 'resolved' : 'none'
}
// 같은 사건 알림이 반복 창 안인가 — 앞 알림창이 떠 있거나 사라진 지 `windowMs` 안.
function isRepeat(live, now, windowMs) {
  if (!live) return false
  if (live.visible) return true
  return typeof live.goneAt === 'number' && now - live.goneAt <= windowMs
}
const LEVEL_RANK = { info: 0, check: 1, action: 2, error: 3 }
// 안 읽은 줄 수와 그 가운데 가장 무거운 단계(배지 색). 99 를 넘으면 「99+」.
function badgeOf(rows) {
  let count = 0
  let level = null
  for (const row of rows) {
    if (!row || !row.unread) continue
    count += 1
    if (level === null || (LEVEL_RANK[row.level] || 0) > (LEVEL_RANK[level] || 0)) level = row.level
  }
  return { count, level, label: count > 99 ? '99+' : String(count) }
}
// 변경 칩 — 수와 맨 위 한 줄(파이썬이 차례대로 준다), 가정 묶음만 있는가(회색 점).
function chipOf(items) {
  const list = Array.isArray(items) ? items : []
  return {
    count: list.length,
    top: list.length ? String(list[0].top || '') : '',
    onlyAssume: list.length > 0 && list.every((item) => item.group === 'assume'),
  }
}
// 패널에 보일 줄 — 단계 · 화면 거르기와 「해소된 것 숨김」, 최신순(마지막 시각).
function visibleRows(rows, filter) {
  return rows
    .filter(
      (row) =>
        (filter.level === 'all' || row.level === filter.level) &&
        (!filter.page || row.page === filter.page) &&
        !(filter.hideResolved && row.state === 'resolved'),
    )
    .sort((a, b) => b.last - a.last)
}
// 알림에 딸린 표의 CSV — 머리 줄 + 행(원본 값). 쉼표 · 따옴표 · 줄바꿈이 든 칸은 따옴표로 감싼다(BOM 은 내려받을 때 붙인다).
function tableCsv(table) {
  const cell = (value) => {
    if (value === null || value === undefined) return ''
    const text = String(value)
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const columns = table && Array.isArray(table.columns) ? table.columns : []
  const rows = table && Array.isArray(table.rows) ? table.rows : []
  return [columns, ...rows].map((row) => (Array.isArray(row) ? row : []).map(cell).join(',')).join('\r\n')
}
// 표 칸에 보일 글 — 화면 표시명(`shown`)이 있으면 그것, 수는 끝자리를 넷까지만.
function tableCell(table, column, value) {
  if (value === null || value === undefined) return ''
  const shown = table && table.shown && table.shown[column]
  if (shown && Object.prototype.hasOwnProperty.call(shown, String(value))) return String(shown[String(value)])
  if (typeof value === 'number' && !Number.isInteger(value)) return String(Number(value.toFixed(4)))
  return String(value)
}
// 표지 · 줄의 딸린 표들 — 행이 든 것만.
function validTables(value) {
  return Array.isArray(value) ? value.filter((table) => table && typeof table === 'object' && Array.isArray(table.rows)) : []
}
// 같은 사건 줄에 새 표지를 합친다 — 글 · 자리 · 계기는 새 표지의 것이고, 표지에 표가 들었으면 표도 새 것이다(코드 + 짧은 글이
// 같아도 표는 다를 수 있다 — 같은 수의 BigDataQuery 등록 충돌 `SC-04`).
function freshenEventRow(row, fresh) {
  for (const name of ['noteId', 'full', 'page', 'href', 'tab', 'cause', 'detail', 'origin', 'level']) row[name] = fresh[name]
  if (validTables(fresh.tables).length) row.tables = fresh.tables
  return row
}
// 표는 코드마다 가장 새 줄(마지막 시각)에만 둔다 — 옛 범위 줄의 표까지 이 탭 저장소에 쌓지 않는다.
function keepNewestTables(rows) {
  const kept = new Set()
  for (const row of [...rows].sort((a, b) => b.last - a.last)) {
    if (!row || !validTables(row.tables).length) continue
    if (kept.has(row.code)) delete row.tables
    else kept.add(row.code)
  }
  return rows
}
// 저장본에서 뺄 다음 표 — 표가 든 가장 오래된 줄만 표 없이 복사한 새 목록. 뺄 표가 없으면 null(원본 줄은 건드리지 않는다).
function withoutOldestTables(rows) {
  const tabled = rows.filter((row) => row && validTables(row.tables).length)
  if (!tabled.length) return null
  const oldest = tabled.reduce((a, b) => (b.last < a.last ? b : a))
  return rows.map((row) => {
    if (row !== oldest) return row
    const { tables, ...rest } = row
    return rest
  })
}
// 탭 단추 글이 고른 탭인가 — 단추 글 앞에는 아이콘 이름 글자가 붙어 있어 끝으로 견준다.
function tabMatches(text, label) {
  const plain = String(text || '').replace(/\s+/g, ' ').trim()
  const want = String(label || '').replace(/\s+/g, ' ').trim()
  return want !== '' && plain.endsWith(want)
}

// 탭 안 탭(가용설비 현황 「Summary › Static 대비 일정」)은 `tab` 에 바깥 → 안 차례로 이 글로 잇는다.
const TAB_PATH = ' › '

// 탭 길(`바깥 › 안`)을 첫 칸과 나머지로 가른다. 나머지가 없으면 빈 글이다.
function tabStep(path) {
  const parts = String(path || '').split(TAB_PATH).map((part) => part.trim()).filter(Boolean)
  return [parts[0] || '', parts.slice(1).join(TAB_PATH)]
}
// 툴바 자리 — `order` 에서 자기보다 뒤 차례인 단추 중 이미 선 첫 단추 앞, 없으면 끝(`theme_toggle.capaToolbar` 와 같다).
// 돌려주는 것은 앞에 설 형제 id(끝이면 null).
function toolbarBefore(order, id, present) {
  const rank = order.indexOf(id)
  const start = rank < 0 ? order.length : rank + 1
  for (let index = start; index < order.length; index += 1) {
    if (present.includes(order[index])) return order[index]
  }
  return null
}
// 로그 복사 글 — (이름, 값) 짝을 「이름: 값」 줄로. 빈 값은 빼고, 여러 줄 값은 다음 줄부터 두 칸 들여 잇는다.
function copyText(pairs) {
  const lines = []
  for (const pair of Array.isArray(pairs) ? pairs : []) {
    const name = String((pair && pair[0]) || '')
    const value = pair && pair[1] !== null && pair[1] !== undefined ? String(pair[1]).replace(/\r\n?/g, '\n').trim() : ''
    if (!name || !value) continue
    lines.push(value.includes('\n') ? `${name}:\n  ${value.split('\n').join('\n  ')}` : `${name}: ${value}`)
  }
  return lines.join('\n')
}
// </alerts-rows>

function storageGet(key, fallback) {
  try {
    const raw = window.sessionStorage.getItem(key)
    if (raw === null) return fallback
    const value = JSON.parse(raw)
    return value === null || value === undefined ? fallback : value
  } catch (error) {
    return fallback
  }
}

function storageSet(key, value) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value))
    return true
  } catch (error) {
    /* 막힌 브라우저 · 넘침 — 이 문서 안에만 쌓는다 */
    return false
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined && text !== null) node.textContent = String(text)
  return node
}

function fill(template, values) {
  return String(template || '').replace(/\{(\w+)\}/g, (_, name) => (name in values ? String(values[name]) : ''))
}

function two(value) {
  return String(value).padStart(2, '0')
}

function hm(ms) {
  const date = new Date(ms)
  return `${two(date.getHours())}:${two(date.getMinutes())}`
}

function hms(ms) {
  const date = new Date(ms)
  return `${hm(ms)}:${two(date.getSeconds())}`
}

// 복사 글의 시각 — 다른 곳에 붙여 넣으므로 날짜까지 적는다.
function stamp(ms) {
  const date = new Date(ms)
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())} ${hms(ms)}`
}

function reducedMotion() {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch (error) {
    return false
  }
}

function createCenter(data) {
  const storage = data.storage || {}
  const limits = data.limits || {}
  const C = {
    data,
    rows: [],
    states: {},
    seen: [],
    seenSet: new Set(),
    live: new Map(),
    filter: { level: 'all', page: '', hideResolved: false },
    open: null,
    openLogs: new Set(),
    openTables: new Set(),
    // 클립보드가 막혀 손 복사 칸을 연 줄 id — 판을 다시 그려도 그 칸을 남긴다.
    manualCopy: null,
    pendingTab: null,
    runRoot: null,
    runObserver: null,
    scanTimer: 0,
    placeTries: 0,
    placeTimer: 0,
    resizer: null,
    resizedSlot: null,
  }
  const now = Date.now()
  C.rows = pruneRows(storageGet(storage.log, []), now, limits.rows || 200, (limits.hours || 12) * 3600000)
  const states = storageGet(storage.states, {})
  C.states = states && typeof states === 'object' && !Array.isArray(states) ? states : {}
  const seen = storageGet(storage.seen, [])
  C.seen = Array.isArray(seen) ? seen.filter((id) => typeof id === 'string').slice(-SEEN_LIMIT) : []
  C.seenSet = new Set(C.seen)

  // 본문 호스트 — 알림창 · 판 · 시선 끌기 테두리. 컴포넌트 칸 안에 그리면 머리말 · 사이드바 · 대화상자의 쌓임 맥락 밑에 깔린다.
  let host = document.getElementById(HOST_ID)
  if (host) host.remove()
  host = el('div')
  host.id = HOST_ID
  const shadow = host.attachShadow({ mode: 'open' })
  shadow.innerHTML = `<style>${ALERT_CSS}</style>`
  C.host = host
  C.shadow = shadow
  C.stack = el('div', 'stack')
  C.stack.setAttribute('role', 'status')
  C.stack.setAttribute('aria-live', 'polite')
  shadow.append(C.stack)
  C.panel = buildAlarmPanel(C)
  C.changesPanel = buildChangesPanel(C)
  shadow.append(C.panel, C.changesPanel)
  document.body.appendChild(host)

  // 탭 줄 JS 의 알림 길. 칸이 서기 전에 담긴 알림을 꺼낸다.
  window.__capaAlerts = {
    raise: (note) => raiseLocal(C, note),
    scan: () => scan(C),
  }
  const queued = Array.isArray(window.__capaAlertQueue) ? window.__capaAlertQueue.splice(0) : []
  for (const note of queued) raiseLocal(C, note, false)

  // 판 밖 누름 · Esc 로 닫는다(모달이 아니다). 처리기는 문서에 하나다.
  document.addEventListener(
    'pointerdown',
    (event) => {
      if (!C.open) return
      const path = event.composedPath ? event.composedPath() : []
      const panel = C.open === 'alarms' ? C.panel : C.changesPanel
      const button = C.open === 'alarms' ? C.alarmHost : C.chipHost
      if (path.includes(panel) || (button && path.includes(button))) return
      closePanel(C, false)
    },
    true,
  )
  document.addEventListener(
    'keydown',
    (event) => {
      if (event.key === 'Escape' && C.open) {
        event.stopPropagation()
        closePanel(C, true)
      }
    },
    true,
  )
  window.addEventListener('resize', () => measureToolbar(C))
  return C
}

function palette(C, element) {
  const colors = (C.data && C.data.palette) || {}
  const vars = {
    '--ac-surface': colors.surface,
    '--ac-page': colors.page,
    '--ac-sub': colors.sub,
    '--ac-text': colors.text,
    '--ac-muted': colors.muted,
    '--ac-border': colors.border,
    '--ac-accent': colors.accent,
    '--ac-accent-text': colors.accent_text,
    '--ac-pending': colors.pending,
    '--ac-badge-ink': colors.badge_ink,
    '--ac-info': colors.info,
    '--ac-check': colors.check,
    '--ac-action': colors.action,
    '--ac-error': colors.error,
    '--ac-font': (C.data && C.data.font) || 'sans-serif',
  }
  for (const [name, value] of Object.entries(vars)) {
    if (value && element.style.getPropertyValue(name) !== value) element.style.setProperty(name, value)
  }
}

function text(C) {
  return (C.data && C.data.text) || {}
}

function levelLabel(C, level) {
  const found = ((C.data && C.data.levels) || []).find((item) => item.id === level)
  return found ? found.label : String(level || '')
}

function levelMs(C, level) {
  const found = ((C.data && C.data.levels) || []).find((item) => item.id === level)
  return found && found.ms ? Number(found.ms) : 15000
}

function persist(C) {
  const storage = C.data.storage || {}
  const limits = C.data.limits || {}
  C.rows = keepNewestTables(pruneRows(C.rows, Date.now(), limits.rows || 200, (limits.hours || 12) * 3600000))
  const alive = new Set(C.rows.map((row) => row.id))
  const keys = Object.keys(C.states)
  if (keys.length > STATE_LIMIT) {
    for (const key of keys) {
      const entry = C.states[key]
      if (!entry.active || !alive.has(entry.row)) delete C.states[key]
      if (Object.keys(C.states).length <= STATE_LIMIT) break
    }
  }
  // 지문 · 본 사건을 먼저 쓴다 — 표가 저장소를 채워 이것들이 못 들어가면 새로고침에 알림창이 다시 뜬다.
  storageSet(storage.states, C.states)
  storageSet(storage.seen, C.seen)
  let saving = C.rows
  while (saving && !storageSet(storage.log, saving)) saving = withoutOldestTables(saving)
}

function rowFor(note, now) {
  return {
    id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    noteId: typeof note.id === 'string' ? note.id : '',
    code: String(note.code || ''),
    level: String(note.level || 'info'),
    kind: note.kind === 'state' ? 'state' : 'event',
    short: String(note.short || ''),
    full: String(note.full || note.short || ''),
    page: String(note.page || ''),
    href: typeof note.href === 'string' ? note.href : null,
    tab: String(note.tab || ''),
    tables: validTables(note.tables),
    scopeLabel: String(note.scope_label || ''),
    cause: String(note.cause || ''),
    detail: String(note.detail || ''),
    origin: String(note.origin || ''),
    first: now,
    last: now,
    n: 1,
    unread: true,
    state: note.kind === 'state' ? 'open' : null,
    resolvedAt: null,
    resolvedWhy: '',
  }
}

function remember(C, id) {
  C.seenSet.add(id)
  C.seen.push(id)
  if (C.seen.length > SEEN_LIMIT) {
    for (const old of C.seen.splice(0, C.seen.length - SEEN_LIMIT)) C.seenSet.delete(old)
  }
}

function handle(C, note) {
  if (!note || typeof note !== 'object' || !note.code) return false
  return note.kind === 'state' ? handleState(C, note) : handleEvent(C, note)
}

// 줄 하나를 쓴다 — 같은 알림(코드 + 짧은 글)의 줄이 있으면 그 줄에 합치고 없으면 새 줄이다.
function writeEventRow(C, note, now) {
  const key = eventKey(note)
  const row = C.rows.find((item) => item.kind === 'event' && eventKey(item) === key)
  if (!row) {
    C.rows.unshift(rowFor(note, now))
    return
  }
  row.n += 1
  row.last = now
  row.unread = true
  freshenEventRow(row, rowFor(note, now))
}

function handleEvent(C, note) {
  if (typeof note.id !== 'string' || !note.id) return false
  const now = Date.now()
  if (C.seenSet.has(note.id)) {
    if (!keptRowMissing(C.rows, note)) return false
    writeEventRow(C, note, now)
    return true
  }
  remember(C, note.id)
  const key = eventKey(note)
  const repeat = isRepeat(C.live.get(key), now, (C.data.limits || {}).repeat_ms || 60000)
  writeEventRow(C, note, now)
  showPopup(C, key, note, repeat)
  return true
}

function resolveRow(C, rowId, now, why) {
  const row = C.rows.find((item) => item.id === rowId)
  if (!row || row.state !== 'open') return
  row.state = 'resolved'
  row.resolvedAt = now
  row.resolvedWhy = why
}

function handleState(C, note) {
  const now = Date.now()
  const key = stateKey(note)
  let changed = false
  // 같은 코드의 다른 범위(시나리오 · 조회기간을 바꿈)는 지금 범위가 아니다 — 「범위가 바뀜」 으로 해소한다.
  for (const [other, entry] of Object.entries(C.states)) {
    if (other !== key && entry && entry.code === note.code && entry.active) {
      resolveRow(C, entry.row, now, 'scope')
      entry.active = false
      changed = true
    }
  }
  const entry = C.states[key]
  const verdict = stateVerdict(entry, note)
  if (verdict === 'new' || verdict === 'change') {
    if (verdict === 'change' && entry) resolveRow(C, entry.row, now, 'changed')
    const row = rowFor(note, now)
    if (!row.cause) row.cause = verdict === 'new' ? text(C).cause_new || '' : text(C).cause_change || ''
    C.rows.unshift(row)
    C.states[key] = { code: String(note.code), fp: String(note.fp || ''), active: true, row: row.id }
    showPopup(C, `state:${key}`, note, false)
    return true
  }
  if (verdict === 'resolved') {
    resolveRow(C, entry.row, now, 'gone')
    entry.active = false
    return true
  }
  if (verdict === 'same') {
    // 같은 지문인데 줄에 표가 없으면(더 새 같은 코드 줄이 표를 가져갔다가 걷힘 · 저장소가 넘쳐 빠짐) 다시 붙인다.
    const row = C.rows.find((item) => item.id === entry.row)
    const tables = validTables(note.tables)
    if (row && tables.length && !validTables(row.tables).length) {
      row.tables = tables
      return true
    }
  }
  return changed
}

function raiseLocal(C, note, paint = true) {
  if (!note || !note.code) return
  const event = { ...note, kind: 'event', id: `js-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}` }
  if (!event.short) event.short = String(event.full || '')
  if (!event.full) event.full = event.short
  if (handleEvent(C, event)) {
    persist(C)
    if (paint) paintAll(C)
  }
}

function scan(C) {
  const marker = C.data.marker || 'data-capa-alerts'
  let changed = false
  for (const node of document.querySelectorAll(`[${marker}]`)) {
    let notes = null
    try {
      notes = JSON.parse(node.getAttribute(marker) || '[]')
    } catch (error) {
      continue
    }
    if (!Array.isArray(notes)) continue
    for (const note of notes) if (handle(C, note)) changed = true
  }
  if (changed) persist(C)
  ensureToolbar(C)
  paintAll(C)
  measureToolbar(C)
  settleTab(C)
}

function scanSoon(C) {
  clearTimeout(C.scanTimer)
  C.scanTimer = setTimeout(() => scan(C), 0)
}

function watchRuns(C) {
  const root = document.querySelector(APP_ROOT)
  if (!root || (C.runRoot === root && C.runObserver)) return
  if (C.runObserver) C.runObserver.disconnect()
  C.runRoot = root
  C.runObserver = new MutationObserver(() => scanSoon(C))
  C.runObserver.observe(root, { attributes: true, attributeFilter: [RUN_STATE] })
}

// ------------------------------------------------------------------------------------------- 알림창

function popupNode(C, note, burst) {
  const node = el('p', 'pop')
  node.dataset.level = String(note.level || 'info')
  node.append(el('b', 'lv', levelLabel(C, note.level)), el('span', 'tx', note.short || note.full || ''))
  const times = el('span', 'times', burst > 1 ? `×${burst}` : '')
  node.append(times)
  return node
}

function showPopup(C, key, note, repeat) {
  const limits = C.data.limits || {}
  let live = C.live.get(key)
  if (repeat && live) {
    live.burst = (live.burst || 1) + 1
    const node = popupNode(C, note, live.burst)
    if (live.el && live.el.isConnected) live.el.replaceWith(node)
    live.el = node
  } else {
    if (live && live.el && live.el.isConnected) live.el.remove()
    live = { el: popupNode(C, note, 1), burst: 1 }
    C.live.set(key, live)
  }
  // 새 칸 · 다시 난 칸은 구석(맨 아래)에 선다.
  C.stack.append(live.el)
  live.visible = true
  live.level = String(note.level || 'info')
  clearTimeout(live.timer)
  live.timer = setTimeout(() => hidePopup(C, key), levelMs(C, note.level))
  while (C.stack.children.length > (limits.popups || 3)) {
    const oldest = C.stack.firstElementChild
    const owner = [...C.live.entries()].find(([, item]) => item.el === oldest)
    if (owner) hidePopup(C, owner[0])
    else oldest.remove()
  }
  if (repeat) {
    const node = live.el
    requestAnimationFrame(() => requestAnimationFrame(() => attract(C, node, live.level)))
  }
}

function hidePopup(C, key) {
  const live = C.live.get(key)
  if (!live) return
  clearTimeout(live.timer)
  if (live.el && live.el.isConnected) live.el.remove()
  live.visible = false
  live.goneAt = Date.now()
}

// 같은 알림 시선 끌기(D4 A) — 창 가장자리(4px 안쪽, 둥글기 14px) 테두리가 알림창 둘레(5px 밖, 둥글기 9px)로 모인다. 앞
// 12% 에서 불투명해지고, 도착하면 걷히며 알림창 테두리가 단계 색 100% + 빛 고리로 잠깐 선다. 돌던 중 또 나면 처음부터.
function attract(C, node, level) {
  if (!node.isConnected) return
  if (reducedMotion() || typeof node.animate !== 'function') {
    node.classList.add('is-still')
    setTimeout(() => node.classList.remove('is-still'), STILL_MS)
    return
  }
  if (C.frame) C.frame.remove()
  const limits = C.data.limits || {}
  const box = node.getBoundingClientRect()
  const pad = 5
  const edge = 4
  const frame = el('div', 'frame')
  frame.dataset.level = level
  frame.setAttribute('aria-hidden', 'true')
  C.shadow.append(frame)
  C.frame = frame
  const width = window.innerWidth
  const height = window.innerHeight
  const motion = frame.animate(
    [
      { left: `${edge}px`, top: `${edge}px`, width: `${width - 2 * edge}px`, height: `${height - 2 * edge}px`, borderRadius: '14px', opacity: 0, offset: 0 },
      { opacity: 1, offset: 0.12 },
      { left: `${box.left - pad}px`, top: `${box.top - pad}px`, width: `${box.width + 2 * pad}px`, height: `${box.height + 2 * pad}px`, borderRadius: '9px', opacity: 1, offset: 1 },
    ],
    { duration: limits.attention_ms || 450, easing: limits.easing || 'ease-out', fill: 'both' },
  )
  motion.finished
    .then(() => {
      node.classList.add('is-hit')
      setTimeout(() => node.classList.remove('is-hit'), HIT_MS)
      return frame.animate([{ opacity: 1 }, { opacity: 0 }], { duration: FADE_MS, fill: 'forwards' }).finished
    })
    .then(() => {
      frame.remove()
      if (C.frame === frame) C.frame = null
    })
    .catch(() => frame.remove())
}

// ------------------------------------------------------------------------------------------- 툴바

function toolbarHost(C, id, extra) {
  let host = document.getElementById(id)
  if (!host || !host.shadowRoot) {
    if (host) host.remove()
    host = el('span', `capa-alert-toolbar ${extra}`)
    host.id = id
    const shadow = host.attachShadow({ mode: 'open' })
    shadow.innerHTML = `<style>${ALERT_CSS}</style>`
  }
  palette(C, host)
  return host
}

function placeHost(C, slot, host) {
  const order = (C.data.toolbar && C.data.toolbar.order) || []
  const present = [...slot.children].map((child) => child.id).filter((id) => id && id !== host.id)
  const before = toolbarBefore(order, host.id, present)
  const anchor = before ? document.getElementById(before) : null
  if (anchor && anchor.parentNode === slot) {
    if (host.nextSibling !== anchor) slot.insertBefore(host, anchor)
  } else if (host.parentNode !== slot) {
    slot.appendChild(host)
  }
}

function ensureToolbar(C) {
  const toolbar = C.data.toolbar || {}
  const slot = document.querySelector(toolbar.slot || '')
  if (!slot) {
    clearTimeout(C.placeTimer)
    if (C.placeTries < PLACE_RETRIES) {
      C.placeTries += 1
      C.placeTimer = setTimeout(() => ensureToolbar(C), PLACE_RETRY_MS)
    }
    return
  }
  C.placeTries = 0
  const t = text(C)
  if (!C.alarmHost || !C.alarmHost.isConnected) {
    const host = toolbarHost(C, toolbar.alarm, 'capa-alert-alarm')
    const shadow = host.shadowRoot
    let button = shadow.querySelector('.alarm')
    if (!button) {
      button = el('button', 'tb alarm', t.alarm || 'Alarm')
      button.type = 'button'
      button.setAttribute('aria-haspopup', 'dialog')
      button.setAttribute('aria-expanded', 'false')
      button.title = t.alarm_title || ''
      const badge = el('span', 'badge')
      badge.hidden = true
      badge.setAttribute('aria-hidden', 'true')
      const dot = el('span', 'dot')
      dot.setAttribute('aria-hidden', 'true')
      button.append(badge, dot)
      button.addEventListener('click', () => togglePanel(C, 'alarms'))
      shadow.append(button)
    }
    C.alarmHost = host
    C.alarmButton = button
  }
  if (!C.chipHost || !C.chipHost.isConnected) {
    const host = toolbarHost(C, toolbar.chip, 'capa-alert-chip')
    const shadow = host.shadowRoot
    let chip = shadow.querySelector('.chip')
    if (!chip) {
      chip = el('button', 'chip')
      chip.type = 'button'
      chip.setAttribute('aria-haspopup', 'dialog')
      chip.setAttribute('aria-expanded', 'false')
      chip.title = t.changes_title || ''
      const mark = el('span', 'mark')
      mark.setAttribute('aria-hidden', 'true')
      chip.append(mark, el('span', 'word', t.changes_word || ''), el('b', 'count'), el('span', 'sep', '·'), el('span', 'top'))
      chip.addEventListener('click', () => togglePanel(C, 'changes'))
      shadow.append(chip)
    }
    C.chipHost = host
    C.chip = chip
  }
  palette(C, C.alarmHost)
  palette(C, C.chipHost)
  placeHost(C, slot, C.chipHost)
  placeHost(C, slot, C.alarmHost)
  watchSlot(C, slot)
}

function watchSlot(C, slot) {
  if (C.resizedSlot === slot || typeof ResizeObserver !== 'function') return
  if (C.resizer) C.resizer.disconnect()
  C.resizedSlot = slot
  C.resizer = new ResizeObserver(() => measureToolbar(C))
  C.resizer.observe(slot)
}

// 툴바 단추 묶음이 머리 띠 오른쪽 끝에서 차지하는 폭(px)을 문서 뿌리에 단다 — 띠 글 · 진행 막대 자리 규칙이 읽는다.
function measureToolbar(C) {
  const toolbar = (C.data && C.data.toolbar) || {}
  const header = document.querySelector(toolbar.header || '')
  const slot = document.querySelector(toolbar.slot || '')
  const root = document.documentElement
  let left = Infinity
  if (header && slot) {
    for (const child of slot.children) {
      const box = child.getBoundingClientRect()
      if (box.width > 0 && box.height > 0) left = Math.min(left, box.left)
    }
  }
  if (!header || !Number.isFinite(left)) {
    root.removeAttribute(TOOLBAR_ATTRIBUTE)
    root.style.removeProperty(TOOLBAR_VARIABLE)
    return
  }
  const width = `${Math.max(0, Math.round(header.getBoundingClientRect().right - left))}px`
  if (root.style.getPropertyValue(TOOLBAR_VARIABLE) !== width) root.style.setProperty(TOOLBAR_VARIABLE, width)
  if (!root.hasAttribute(TOOLBAR_ATTRIBUTE)) root.setAttribute(TOOLBAR_ATTRIBUTE, '')
}

// ------------------------------------------------------------------------------------------- 판

function buildAlarmPanel(C) {
  const t = text(C)
  const panel = el('section', 'panel alarms')
  panel.hidden = true
  panel.tabIndex = -1
  panel.setAttribute('role', 'dialog')
  panel.setAttribute('aria-label', t.panel || '')
  const head = el('div', 'head')
  const title = el('h2', '', t.panel || '')
  const sum = el('span', 'sum')
  const readAll = el('button', 'link', t.read_all || '')
  readAll.type = 'button'
  readAll.addEventListener('click', () => {
    for (const row of C.rows) row.unread = false
    persist(C)
    paintAll(C)
  })
  const close = el('button', 'x', '×')
  close.type = 'button'
  close.setAttribute('aria-label', t.close || '')
  close.addEventListener('click', () => closePanel(C, true))
  head.append(title, sum, el('span', 'grow'), readAll, close)
  const here = el('div', 'here')
  const filters = el('div', 'filters')
  const seg = el('div', 'seg')
  seg.setAttribute('role', 'group')
  seg.setAttribute('aria-label', t.level_filter || '')
  for (const level of ['all', ...((C.data.levels || []).map((item) => item.id))]) {
    const button = el('button', '', level === 'all' ? t.all || '' : levelLabel(C, level))
    button.type = 'button'
    button.dataset.value = level
    button.addEventListener('click', () => {
      C.filter.level = level
      paintList(C)
    })
    seg.append(button)
  }
  const pages = el('select')
  pages.setAttribute('aria-label', t.page_filter || '')
  pages.addEventListener('change', () => {
    C.filter.page = pages.value
    paintList(C)
  })
  const hide = el('label')
  const box = el('input')
  box.type = 'checkbox'
  box.addEventListener('change', () => {
    C.filter.hideResolved = box.checked
    paintList(C)
  })
  hide.append(box, document.createTextNode(` ${t.hide_resolved || ''}`))
  filters.append(seg, pages, hide)
  const list = el('ul', 'list')
  panel.append(head, here, filters, list)
  C.parts = { sum, seg, pages, box, list, here, title }
  return panel
}

function buildChangesPanel(C) {
  const t = text(C)
  const panel = el('section', 'panel changes')
  panel.hidden = true
  panel.tabIndex = -1
  panel.setAttribute('role', 'dialog')
  panel.setAttribute('aria-label', t.changes || '')
  const head = el('div', 'head')
  const sum = el('span', 'sum')
  const close = el('button', 'x', '×')
  close.type = 'button'
  close.setAttribute('aria-label', t.close || '')
  close.addEventListener('click', () => closePanel(C, true))
  head.append(el('h2', '', t.changes || ''), sum, el('span', 'grow'), close)
  const body = el('div', 'cbody')
  panel.append(head, body)
  C.changesParts = { sum, body }
  return panel
}

function goTo(C, href, tab) {
  closePanel(C, false)
  C.pendingTab = tab ? { href, tab, until: Date.now() + PENDING_TAB_MS } : null
  window.dispatchEvent(new CustomEvent(OPEN_PAGE_EVENT, { detail: { href } }))
  settleTab(C)
}

function running() {
  const root = document.querySelector(APP_ROOT)
  return Boolean(root) && root.getAttribute(RUN_STATE) === 'running'
}

// 「그 화면으로」 가 맡긴 탭 고르기 — 그 화면(`here`)에 닿고 회차가 끝났으면 이름이 맞는 탭 단추를 누른다. 이미 열린 탭이면
// 누르지 않는다. 탭 안 탭이면 바깥 탭부터 한 칸씩 연다 — 누른 칸은 그 회차가 끝난 뒤 다음 칸을, 이미 열린 칸은 곧바로 다음 칸을
// 본다. 기다리는 시간이 지나면 버린다.
function settleTab(C) {
  while (C.pendingTab) {
    const pending = C.pendingTab
    if (Date.now() > pending.until) {
      C.pendingTab = null
      return
    }
    if (C.data.here !== pending.href || running()) return
    const [first, rest] = tabStep(pending.tab)
    C.pendingTab = rest ? { ...pending, tab: rest } : null
    const button = [...document.querySelectorAll(TAB_BUTTON)].find((item) => tabMatches(item.textContent, first))
    if (button && button.getAttribute('aria-selected') !== 'true') {
      button.click()
      return
    }
    if (!button) {
      C.pendingTab = null
      return
    }
  }
}

function downloadTable(table) {
  const blob = new Blob(['\ufeff' + tableCsv(table)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = String(table.file || 'table.csv')
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function tableBox(C, table) {
  const t = text(C)
  const columns = Array.isArray(table.columns) ? table.columns : []
  const box = el('div', 'tablebox')
  const head = el('div', 'thead')
  const csv = el('button', 'link', t.table_csv || '')
  csv.type = 'button'
  csv.addEventListener('click', () => downloadTable(table))
  head.append(
    el('b', '', table.title || ''),
    el('span', 'count', fill(t.table_rows, { n: Number(table.total || table.rows.length).toLocaleString() })),
    el('span', 'grow'),
    csv,
  )
  const scroller = el('div', 'tscroll')
  scroller.tabIndex = 0
  const grid = el('table')
  const header = el('tr')
  const helps = table.help && typeof table.help === 'object' ? table.help : {}
  for (const column of columns) {
    const help = Object.prototype.hasOwnProperty.call(helps, column) ? String(helps[column]) : ''
    const cell = el('th', help ? 'hint' : '', column)
    if (help) cell.title = help
    header.append(cell)
  }
  const thead = el('thead')
  thead.append(header)
  const tbody = el('tbody')
  for (const values of table.rows) {
    const line = el('tr')
    columns.forEach((column, index) => {
      const value = Array.isArray(values) ? values[index] : null
      line.append(el('td', typeof value === 'number' ? 'num' : '', tableCell(table, column, value)))
    })
    tbody.append(line)
  }
  grid.append(thead, tbody)
  scroller.append(grid)
  box.append(head, scroller)
  return box
}

function changeLines(C, target) {
  const t = text(C)
  const groups = (C.data && C.data.groups) || []
  const items = (C.data && C.data.changes) || []
  target.replaceChildren()
  for (const group of groups) {
    const members = items.filter((item) => item.group === group.id)
    if (!members.length) continue
    target.append(el('div', 'cg', group.label))
    for (const item of members) {
      const line = el('div', 'cline')
      line.append(el('span', `d${item.group === 'assume' ? ' assume' : ''}`), el('span', 'pg', item.page))
      const what = el('span', 'what', item.text)
      what.title = item.text
      line.append(what)
      if (typeof item.href === 'string') {
        const go = el('button', 'link go', t.go || '')
        go.type = 'button'
        go.addEventListener('click', () => goTo(C, item.href, item.tab))
        line.append(go)
      }
      target.append(line)
    }
  }
}

function paintChanges(C) {
  const t = text(C)
  const chip = chipOf(C.data.changes)
  if (C.chipHost) {
    C.chipHost.toggleAttribute('data-empty', chip.count === 0)
    C.chip.classList.toggle('only-assume', chip.onlyAssume)
    C.chip.querySelector('.count').textContent = String(chip.count)
    C.chip.querySelector('.top').textContent = chip.top
    C.chip.setAttribute('aria-label', fill(t.changes_aria, { n: chip.count, top: chip.top }))
  }
  if (C.alarmHost) C.alarmHost.toggleAttribute('data-changes', chip.count > 0)
  C.panel.toggleAttribute('data-changes', chip.count > 0)
  C.changesParts.sum.textContent = fill(t.changes_sum, { n: chip.count })
  changeLines(C, C.changesParts.body)
  changeLines(C, C.parts.here)
  if (chip.count === 0 && C.open === 'changes') closePanel(C, false)
}

function paintBadge(C) {
  if (!C.alarmButton) return
  const t = text(C)
  const badge = badgeOf(C.rows)
  const node = C.alarmButton.querySelector('.badge')
  node.hidden = badge.count === 0
  node.textContent = badge.label
  if (badge.level) node.dataset.level = badge.level
  C.alarmButton.setAttribute('aria-label', fill(t.alarm_aria, { n: badge.count }))
}

// 줄의 화면 칸 — 화면 안 탭이 있으면 「화면 › 탭」.
function pageLabel(row) {
  return row.page && row.tab ? `${row.page} › ${row.tab}` : row.page
}

// 로그 칸 짝. 복사(`forCopy`)는 시각에 날짜를 붙이고 끝에 전문 · 딸린 표(이름 · 행 수만)를 더한다.
function logPairs(C, row, forCopy) {
  const t = text(C)
  const why = { gone: t.resolved_gone, changed: t.resolved_changed, scope: t.resolved_scope }
  const time = forCopy ? stamp : hms
  const pairs = [
    [t.log_code, `${row.code} · ${levelLabel(C, row.level)} · ${row.kind === 'state' ? t.kind_state : t.kind_event}`],
    [t.log_first, time(row.first)],
    [t.log_last, time(row.last) + (row.n > 1 ? ` (${fill(t.log_times, { n: row.n })})` : '')],
    [t.log_page, pageLabel(row) || '—'],
    [t.log_cause, row.cause || (row.kind === 'state' ? t.cause_new : t.cause_event) || '—'],
  ]
  if (row.scopeLabel) pairs.push([t.log_scope, row.scopeLabel])
  if (row.kind === 'state') {
    pairs.push([
      t.log_resolved,
      row.state === 'resolved' ? `${(forCopy ? stamp : hm)(row.resolvedAt)} — ${why[row.resolvedWhy] || ''}` : t.not_yet,
    ])
  }
  if (row.detail) pairs.push([t.log_detail, row.detail])
  if (forCopy) {
    pairs.push([t.log_full, row.full])
    for (const table of validTables(row.tables)) {
      const count = Number(table.total || table.rows.length)
      pairs.push([t.log_table, fill(t.log_table_value, { title: table.title || '', n: count.toLocaleString() })])
    }
  }
  return pairs
}

function logRows(C, row) {
  const t = text(C)
  const box = el('div', 'logbox')
  const list = el('dl')
  for (const [name, value] of logPairs(C, row, false)) list.append(el('dt', '', name), el('dd', '', value))
  const acts = el('div', 'logacts')
  const copy = el('button', 'link copy', t.log_copy || '')
  copy.type = 'button'
  copy.title = t.log_copy_title || ''
  const state = el('span', 'copystate')
  state.setAttribute('role', 'status')
  state.setAttribute('aria-live', 'polite')
  acts.append(copy, state)
  const area = el('textarea', 'copyarea')
  area.readOnly = true
  area.rows = 6
  area.setAttribute('aria-label', t.log_copy_title || '')
  area.hidden = true
  copy.addEventListener('click', () => copyLog(C, row, area, state))
  // 판을 다시 그려도(회차 끝 훑기) 손 복사 칸은 남긴다 — 초점은 옮기지 않는다.
  if (C.manualCopy === row.id) showManualCopy(C, row, area, state, false)
  box.append(list, acts, area)
  return box
}

function showManualCopy(C, row, area, state, focus) {
  C.manualCopy = row.id
  area.value = copyText(logPairs(C, row, true))
  area.hidden = false
  state.textContent = text(C).log_copy_manual || ''
  if (focus) {
    area.focus({ preventScroll: true })
    area.select()
  }
}

// 「복사」 — 클립보드에 넣으면 「복사했습니다」 를 잠깐 보이고, 막히면 글을 고른 채 두고 Ctrl+C 를 청한다.
function copyLog(C, row, area, state) {
  const t = text(C)
  const content = copyText(logPairs(C, row, true))
  const done = () => {
    if (C.manualCopy === row.id) C.manualCopy = null
    area.hidden = true
    state.textContent = t.log_copied || ''
    clearTimeout(state.__capaCopied)
    state.__capaCopied = setTimeout(() => {
      if (state.textContent === (t.log_copied || '')) state.textContent = ''
    }, COPIED_MS)
  }
  const manual = () => showManualCopy(C, row, area, state, true)
  let clip = null
  try {
    clip = window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === 'function' ? navigator.clipboard : null
  } catch (error) {
    clip = null
  }
  if (!clip) {
    manual()
    return
  }
  try {
    clip.writeText(content).then(done, manual)
  } catch (error) {
    manual()
  }
}

function paintList(C) {
  const t = text(C)
  const parts = C.parts
  for (const button of parts.seg.children) button.setAttribute('aria-pressed', String(button.dataset.value === C.filter.level))
  const pages = [...new Set(C.rows.map((row) => row.page).filter(Boolean))]
  const keep = C.filter.page
  parts.pages.replaceChildren(el('option', '', t.all_pages || ''))
  parts.pages.firstChild.value = ''
  for (const page of pages) {
    const option = el('option', '', page)
    option.value = page
    parts.pages.append(option)
  }
  C.filter.page = pages.includes(keep) ? keep : ''
  parts.pages.value = C.filter.page
  parts.box.checked = C.filter.hideResolved
  const unread = C.rows.filter((row) => row.unread).length
  parts.sum.textContent = fill(t.summary, { unread, total: C.rows.length })
  const shown = visibleRows(C.rows, C.filter)
  parts.list.replaceChildren()
  if (!shown.length) {
    parts.list.append(el('li', 'empty', C.rows.length ? t.empty : t.none))
    return shown
  }
  for (const row of shown) {
    const item = el('li', `item${row.unread ? ' unread' : ''}`)
    item.dataset.level = row.level
    const line = el('div', 'line')
    const body = el('span', 'tx', row.full)
    body.title = row.full
    line.append(el('span', 'lv', levelLabel(C, row.level)), body)
    const meta = el('div', 'meta')
    if (row.page) meta.append(el('span', '', pageLabel(row)))
    meta.append(el('span', '', hm(row.last) + (row.n > 1 ? ` · ×${row.n}` : '')))
    if (row.kind === 'state') {
      meta.append(
        el('span', `state${row.state === 'open' ? ' open' : ''}`, row.state === 'open' ? t.open : fill(t.resolved, { time: hm(row.resolvedAt) })),
      )
    }
    const acts = el('span', 'acts')
    if (typeof row.href === 'string') {
      const go = el('button', 'link', t.go || '')
      go.type = 'button'
      go.addEventListener('click', () => goTo(C, row.href, row.tab))
      acts.append(go)
    }
    const tableHolders = []
    validTables(row.tables).forEach((table, index) => {
      const opened = `${row.id}:${index}`
      const toggle = el('button', 'link', fill(t.table_open, { title: table.title || '' }))
      toggle.type = 'button'
      const shownTable = C.openTables.has(opened)
      toggle.setAttribute('aria-expanded', String(shownTable))
      const tableHolder = el('div', 'tableholder')
      if (shownTable) tableHolder.append(tableBox(C, table))
      toggle.addEventListener('click', () => {
        const now = !C.openTables.has(opened)
        if (now) C.openTables.add(opened)
        else C.openTables.delete(opened)
        toggle.setAttribute('aria-expanded', String(now))
        tableHolder.replaceChildren(...(now ? [tableBox(C, table)] : []))
      })
      acts.append(toggle)
      tableHolders.push(tableHolder)
    })
    let box = null
    if (row.level !== 'info') {
      const log = el('button', 'link', t.log || '')
      log.type = 'button'
      const opened = C.openLogs.has(row.id)
      log.setAttribute('aria-expanded', String(opened))
      // 펼치면 그 줄 글을 끝까지 보인다 — 자리에 마크만 남은 오류는 여기가 글을 읽는 자리다.
      item.classList.toggle('logopen', opened)
      log.addEventListener('click', () => {
        const now = !C.openLogs.has(row.id)
        if (now) C.openLogs.add(row.id)
        else C.openLogs.delete(row.id)
        log.setAttribute('aria-expanded', String(now))
        item.classList.toggle('logopen', now)
        box.hidden = !now
      })
      acts.append(log)
      box = logRows(C, row)
      box.hidden = !opened
    }
    meta.append(acts)
    item.append(line, meta)
    if (box) item.append(box)
    item.append(...tableHolders)
    parts.list.append(item)
  }
  return shown
}

function paintAll(C) {
  paintChanges(C)
  paintBadge(C)
  if (C.open === 'alarms') {
    paintList(C)
    markRead(C)
  }
}

// 패널을 열면 그때 보인 줄을 읽음으로 바꾼다. 줄의 띠는 다음에 열 때까지 남는다.
function markRead(C) {
  const shown = visibleRows(C.rows, C.filter)
  let changed = false
  for (const row of shown) {
    if (row.unread) {
      row.unread = false
      changed = true
    }
  }
  if (changed) {
    persist(C)
    paintBadge(C)
  }
}

function togglePanel(C, which) {
  if (C.open === which) {
    closePanel(C, true)
    return
  }
  if (C.open) closePanel(C, false)
  C.open = which
  const panel = which === 'alarms' ? C.panel : C.changesPanel
  const button = which === 'alarms' ? C.alarmButton : C.chip
  panel.hidden = false
  if (button) button.setAttribute('aria-expanded', 'true')
  if (which === 'alarms') {
    paintList(C)
    markRead(C)
  } else {
    paintChanges(C)
  }
  panel.focus({ preventScroll: true })
}

function closePanel(C, refocus) {
  if (!C.open) return
  const panel = C.open === 'alarms' ? C.panel : C.changesPanel
  const button = C.open === 'alarms' ? C.alarmButton : C.chip
  panel.hidden = true
  if (button) button.setAttribute('aria-expanded', 'false')
  C.open = null
  if (C.panel.hidden) {
    // 읽은 줄의 띠는 패널을 닫을 때 걷는다(연 동안에는 무엇이 새것이었는지 보인다).
    for (const item of C.parts.list.querySelectorAll('.item.unread')) item.classList.remove('unread')
  }
  if (refocus && button) button.focus({ preventScroll: true })
}

export default function (component) {
  const { data } = component
  if (!data) return undefined
  let C = window.__capaAlertCenter
  if (!C || !C.host || !C.host.isConnected) {
    C = createCenter(data)
    window.__capaAlertCenter = C
  }
  C.data = data
  palette(C, C.host)
  watchRuns(C)
  let changed = false
  for (const note of Array.isArray(data.events) ? data.events : []) if (handle(C, note)) changed = true
  if (changed) persist(C)
  scan(C)
  return undefined
}
