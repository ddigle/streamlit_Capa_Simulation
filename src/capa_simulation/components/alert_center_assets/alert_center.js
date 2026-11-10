// 알림 칸(`components/alert_center.py`, 2026-11-03 결정 보드 D1 ~ D5). 파이썬이 페이지 앞에서 매 앱 전체 회차 data 로
// 등록 글 · 팔레트 · 이 세션의 변경(`changes`) · 콜백이 담은 사건 알림(`events`)을 주고, 이 JS 가 문서에 하나 있는 알림 칸을
// 세우거나 고친다(`window.__capaAlertCenter` — 다시 마운트돼도 하나다).
// - 알림창 한 꼴: 오른쪽 아래, 최대 3칸(넘치면 단계가 가장 낮은 칸부터, 같은 단계면 먼저 선 칸부터 걷는다 — `overflowVictim`),
//   새 칸이 구석, 단계 이름 글자 + 단계 색 테두리. 누름을 받지 않는다(`pointer-events: none`). 층은 Streamlit 대화상자 위다.
//   알림 8초 · 나머지 15초 뒤 걷는다. 방금 세운 칸이 넘침으로 곧바로 걷히면 보인 적이 없어 반복 창을 열지 않는다(`hidePopup`
//   의 `seen`).
// - 표지 훑기: 알림을 내는 자리(`alerts.state` · `alerts.flush` · `flash.render_flash`)가 스타일만 든 `st.html` 표지
//   (`style[data-capa-alerts]` — JSON, 팝업 본문 안에서는 칸 안의 숨은 `span`)를 그린다. 앱 뿌리의 회차 표지
//   (`data-test-script-state`)가 바뀔 때마다 문서를 **한 번** 훑는다 — 상시 MutationObserver 는 쓰지 않는다(큰 표 화면의 DOM 변화가 많다). 회차 시작에도 훑어 끊긴 회차의 표지를 놓치지
//   않는다. 같은 표지를 또 봐도 사건은 id, 상태는 지문으로 한 번만 띄운다.
// - 상태 알림(`kind: "state"`)은 「코드 + 범위 → 마지막 지문」 표로 바뀔 때만 띄운다. 같은 코드의 다른 범위가 오면 앞 범위는
//   「범위가 바뀜」 으로 닫고, `active: false` 가 오면 「조건이 사라짐」 으로 해소한다. 범위 교체로 닫힌 줄은 Alarm 에 「해소」
//   대신 「범위 바뀜」 이라 적는다(2026-11-08 사용자 답 a3 — 리비전이 오르면 조건이 그대로여도 앞 줄이 풀린 것처럼 읽혔다). 같은
//   범위에서 내용(건수 · 목록)만 바뀌어 새 줄로 넘어간 앞 줄도 「해소」 가 아니라 「내용 바뀜」 이다(지난 보드 a-content-changed).
// - 같은 사건 알림(코드 + 짧은 글)이 앞 알림창이 떠 있거나 사라진 지 반복 창(60초) 안에 다시 나면 새 칸을 쌓지 않고 앞 칸을
//   구석으로 옮겨 「×n」 을 붙이고 창 가장자리 테두리가 그 칸으로 모인다(D4 A — 한 겹 · 450ms · easeOutQuad · 한 번만). 움직임
//   줄이기에서는 움직이지 않는 윤곽만 1.6초 선다.
// - 기록(L1)은 이 브라우저 탭의 `sessionStorage` 다(D1 (가) — 200줄 · 12시간). 새로고침 · 테마 전환(새 세션)에도 남고 탭을 닫으면
//   사라진다. 읽기 · 쓰기는 모두 try/catch — 막힌 브라우저에서는 이 문서 안에만 쌓인다. 서버에는 아무것도 보내지 않는다(L2 는
//   usage-log 와 함께 — D6).
// - 다시 붙은 탭(2026-11-07 2차 보드 R1 (가)): 프런트는 마지막 회차가 앱 전체였던 탭에 다시 붙어도 회차를 요청하지 않고, 새 세션은 모르는
//   프래그먼트의 요청을 회차 없이 버린다 — 그 탭의 첫 프래그먼트 · 대화상자 저장이 조용히 버려졌다. 앱 뿌리의 연결 표지(`data-test-connection-state`)가
//   붙음으로 돌아오면 본 스레드가 `RECONNECT_WAIT_MS` + 왕복 시간(`reconnectWait`) 조용해지기를 기다리고, 그 사이 프런트가 스스로 돈 회차가 없으면 트리거로 앱 전체 회차를
//   한 번 부른다. 기다리는 동안 사람 손이 닿으면 그 누름의 회차가 돌아오기를 더 기다린다 — 표지는 왕복해야 움직이므로 그 사이 부르면 누름의 회차를 끊어 누름이 사라진다.
//   이 JS 가 파이썬을 부르는 자리는 이것과 공정 판 「모든 화면에서 해제」(`process_clear`) 둘이다. 연결 표지와 회차 표지는 관찰자 하나가
//   본다(`watchRoot` — 칸이 다시 그려져도 늘지 않는다).
// - 서버 재시작(2026-11-07 통합 검수 D4 (가) · 2차 보드 R3 (가)): 재시작 뒤 세션은 새것이라 파이썬은 첫 접속과 가르지 못한다. data 의 부트
//   표지(`boot.mark`)를 이 탭에 적어 둔 앞 표지와 견주어 앞 표지가 있고 다를 때만 함께 실린 알림(`boot.notice` — `GL-07`)을 띄우고
//   어느 경우든 지금 표지로 고쳐 적는다.
// - 세션만 사라진 탭(2차 보드 R2 (가)): 서버는 그대로이고 세션만 끊긴 지 오래돼 사라진 탭이다. data 의 세션 표지(`session.mark`)를 이 문서
//   메모리의 앞 data 와 견주고, 앞 data 의 변경 목록이 있었거나 끊길 때 대화상자가 열려 있었으면 함께 실린 알림(`session.notice` — `GL-08`)을
//   띄운다. 새 문서(새로고침 · 테마 전환 · 새 탭 · 복제한 탭 · 첫 접속)에는 앞 data 가 없어 뜨지 않고, 잃은 것이 없는 탭은 덮개를 여닫아도 뜨지 않는다.
// - 머리 툴바: Guide 오른쪽에 `Alarm`(안 읽음 수 배지 · 패널), Guide 왼쪽에 바뀐 것이 있을 때만 서는 변경 칩(D5 (가) · 판), 맨 왼쪽에
//   공용 공정 값이 있을 때만 서는 공정 칩(2026-11-09 보드 C1 (라) · 판)과 그 오른쪽 합성 샘플 표지(T8 — 구현 중 화면에서 샘플을 켠
//   동안). 차례는 파이썬 `theme_toggle.TOOLBAR_BUTTON_ORDER` 한 벌이다(다른 툴바 단추와 같은 규칙 — `capaToolbar.place`). 패널 ·
//   판은 브라우저 안에서만 열고 닫아 파이썬 회차가 돌지 않는다.
// - 공정 칩: 이 화면에 대한 값은 파이썬 짐작(`process.here` — 세션 기록)으로 그리고, 회차 표지를 훑을 때 공정 값 칸이 남긴 표지
//   (`process.marker` 속성의 JSON — 이 화면 주소 · 공용 값 판 · 걸리나 · 없는 공정 · 지금 탭 표지)로 바로잡는다. 회차가 끝났는데 이 화면
//   표지가 없으면 이 화면은 공정 칸을 그리지 않은 것이라 흐린 칩이다. 지금 탭 표지는 문서 사건(`PROCESS_EVENT`)으로 탭 줄에 알린다.
// - 툴바 실제 폭을 재어 `--capa-toolbar-width`(px)와 `data-capa-toolbar` 를 문서 뿌리에 단다 — 머리 띠 두 줄 · 진행 막대
//   자리 규칙이 그 값으로 오른쪽을 비운다(`app_header`). 단추가 늘거나 줄어도 다시 잴 필요가 없다.
// - 화면 탭 줄 JS(`page_tabs.js`)는 같은 문서의 `window.__capaAlerts.raise(...)` 로 알린다(알림 칸이 아직 서지 않았으면
//   `window.__capaAlertQueue` 에 담아 두고 칸이 설 때 꺼낸다). 「그 화면으로」 는 탭 줄의 화면 이동(상한 · 떠나기 확인)에
//   `capa-open-page` 사건으로 맡긴다. 줄에 화면 안 탭(`tab`)이 있으면 그 화면에 닿은 회차가 끝난 뒤 이름이 맞는 탭 단추를
//   누른다(`stateful_tabs` — 보통 누름과 같다).
// - 알림에 딸린 표(`tables` — 본문에서 뺀 목록, 한 줄에 여럿일 수 있다)는 줄의 「… 보기」 단추가 표마다 펼치고 CSV 는 브라우저
//   안에서 만든다(서버를 부르지 않는다). 칸 머리 풍선(`help`)은 `title` 이다. 표는 코드마다 가장 새 줄에만 남기고, 탭 저장소가
//   넘치면 저장본에서 오래된 줄의 표부터 뺀다 — 줄은 남고, 그 화면이 다시 보내면 표가 다시 붙는다.
// - 「로그」 펼침의 「복사」 는 그 줄의 로그 전문(코드 · 단계 · 처음 · 마지막 · 화면 · 계기 · 범위 · 해소(내용 바뀜 · 범위 바뀜) · 원본 오류 · 전문)을
//   평문으로 클립보드에 넣는다(`navigator.clipboard`). 막히면(보안 연결이 아님 · DRM) 글을 고른 채 펼침 안에 두고 Ctrl+C 를
//   청한다 — `execCommand('copy')` 는 쓰지 않는다(막힌 클립보드에서도 참을 돌려 「복사했습니다」 가 거짓이 된다). 딸린 표는
//   복사에 넣지 않고 표 이름 · 행 수만 적는다(최대 2000행 — 표는 「CSV 내려받기」 가 맡는다).
// - 초점 껍데기(`installFocusShell`): 앱 전체 꼴이라 화면마다 고치지 않고 이 칸이 문서에 처리기를 둔다. 회차를 돌리지 않는다.
//   ① 꺼진 단추는 Tab 이 건너뛰므로 감싼 풍선 칸(`stTooltipHoverTarget`)이 탭 자리를 맡는다(설계 규칙 UI-INP-07). 상시 훑지 않고 Tab
//   키를 누른 순간 한 번 맞추고, 열린 팝오버 단추에서는 본문으로 들여보낸다 — 회차 없이 열리는 팝오버 안 단추까지 든다. ② Streamlit 풍선은
//   초점이 칸 안에 있으면 마우스가 떠나도 닫지 않아 마우스로 누른 단추 · 대화상자를 닫은 뒤 돌아온 초점의 풍선이 남는다 — 키보드 초점이
//   아니면 마우스가 떠날 때 · 마우스 없이 초점이 왔을 때 닫는다. ③ 대화상자의 Esc 는 그 안의 키 사건으로만
//   듣는데 고른 탭이 회차 중 `tabindex` 를 잠깐 잃으면 초점이 문서로 빠진다 — 열린 대화상자 안으로 되돌린다.
// `// <alerts-…>` 구획은 DOM 을 모르는 순수 함수라 node 시험이 떼어 돌린다(`tests/test_alert_center_assets.py`).
const HOST_ID = 'capa-alert-host'
const APP_ROOT = '[data-testid="stApp"]'
const RUN_STATE = 'data-test-script-state'
const CONNECTION_STATE = 'data-test-connection-state'
const DIALOG = '[data-testid="stDialog"]'
const OPEN_PAGE_EVENT = 'capa-open-page'
// 지금 화면 탭의 공정 표지를 바로잡는 사건(`page_tabs.js` 가 듣는다) — {href, tab: {miss, title} | null}.
const PROCESS_EVENT = 'capa-process-here'
const SVG_NS = 'http://www.w3.org/2000/svg'
// 깔때기(공정 거름)와 플라스크(합성 샘플) 아이콘 — 24 단위 path 하나. 깔때기는 사이드바 공정 값 칸 아이콘(Material `filter_alt`)과
// 같은 선 꼴이고 화면 탭 표지와 같은 상수다(`page_tabs.js`).
const FUNNEL_PATH = 'M11 20q-.425 0-.713-.288T10 19v-6L4.2 5.6q-.375-.5-.113-1.05T5 4h14q.65 0 .913.55t-.113 1.05L14 13v6q0 .425-.288.713T13 20zm1-7.7L16.95 6H7.05z'
const FLASK_PATH =
  'M19.8 18.4 14 10.67V6.5l1.35-1.69c.26-.33.03-.81-.39-.81H9.04c-.42 0-.65.48-.39.81L10 6.5v4.17L4.2 18.4c-.49.66-.02 1.6.8 1.6h14c.82 0 1.29-.94.8-1.6z'
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
// 탭이 아닌 전환 단추(기준 정보 종류 — `st.segmented_control`). 같은 글의 탭이 있으면 탭이 먼저다.
const SEGMENT_BUTTON = '[data-testid="stMain"] [data-testid="stButtonGroup"] [role="radio"]'
// 빠진 초점을 되돌리기 전에 기다리는 시간 — 고른 탭은 회차 중 `tabindex` 를 잠깐 잃어 그동안 초점을 받지 못한다(되찾기까지 50ms 안쪽).
const FOCUS_RETURN_MS = 120

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
// 상태 알림 줄의 표지 — 'open'(지금도 있음) · 'scope'(범위가 바뀌어 닫힘 — 조건은 새 범위 줄에 그대로일 수 있다) ·
// 'changed'(같은 범위에서 내용이 바뀌어 닫힘 — 조건은 새 줄에 이어진다) · 'resolved'(조건이 사라짐). 사건 알림 줄은 null.
// 닫힌 셋은 줄 상태(`row.state`)가 모두 'resolved' 라 「닫힌 것 숨김」 이 함께 감춘다.
function stateMark(row) {
  if (!row || row.kind !== 'state') return null
  if (row.state === 'open') return 'open'
  if (row.resolvedWhy === 'scope') return 'scope'
  return row.resolvedWhy === 'changed' ? 'changed' : 'resolved'
}
// 같은 사건 알림이 반복 창 안인가 — 앞 알림창이 떠 있거나 사라진 지 `windowMs` 안.
function isRepeat(live, now, windowMs) {
  if (!live) return false
  if (live.visible) return true
  return typeof live.goneAt === 'number' && now - live.goneAt <= windowMs
}
const LEVEL_RANK = { info: 0, check: 1, action: 2, error: 3 }
// 알림창이 넘칠 때 걷을 칸 — 단계가 가장 낮은 칸, 같은 단계면 가장 오래된(먼저 선) 칸. `levels` 는 쌓인 차례(오래된 것
// 먼저)의 단계다. 낮은 단계 알림 여럿이 함께 떠도 더 높은 단계(조치 필요 · 오류) 칸을 밀어내지 않는다.
function overflowVictim(levels) {
  let pick = -1
  for (let index = 0; index < levels.length; index += 1) {
    if (pick < 0 || (LEVEL_RANK[levels[index]] || 0) < (LEVEL_RANK[levels[pick]] || 0)) pick = index
  }
  return pick
}
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
// 머리 공정 칩 — 공용 값(`process` — 파이썬 `process_field.header_chip`)과 이 화면에 대한 값. 이 화면 주소(`here`) · 같은 판의 회차
// 표지(`live`)가 있으면 그것이, 아니면 파이썬 짐작(`process.here`)이 이 화면 값이다. 없는 공정은 이 화면이 따르는 꼴일 때만 센다.
// 따르는 화면이면 줄 차례를 이 화면 선택지 차례(`inside` — 걸린 공정 먼저, 없는 공정 뒤 — 파이썬 `screen_order`)로 세우고 첫
// 이름(`top`)도 그 차례로 적는다(`rest` — 파이썬 `process_field.REST_TEXT`, 없으면 파이썬이 적은 `top`). 사이드바 값 칸 · 탭 풍선과
// 첫 이름이 같아진다. 값이 없으면 null(칩을 세우지 않는다).
function processChipOf(process, live, here, rest) {
  if (!process || !Array.isArray(process.values) || !process.values.length) return null
  const values = process.values.map(String)
  const labels = values.map((value, index) => String((Array.isArray(process.labels) && process.labels[index]) || value))
  const fresh = Boolean(live) && live.page === here && live.version === process.version
  const mark = (fresh ? live.here : process.here) || null
  const follows = Boolean(mark && mark.follows)
  const gone = new Set(follows && Array.isArray(mark.missing) ? mark.missing.map(String) : [])
  const first = follows && Array.isArray(mark.inside) ? mark.inside.map(String).filter((value) => values.includes(value)) : []
  const ranked = [...first, ...values.filter((value) => !first.includes(value))]
  const labelOf = new Map(values.map((value, index) => [value, labels[index]]))
  const rows = ranked.map((value) => ({ value, label: labelOf.get(value), absent: gone.has(value) }))
  const many = (_, name) => (name === 'first' ? rows[0].label : String(rows.length - 1))
  const top =
    typeof rest === 'string' && rest
      ? rows.length > 1
        ? rest.replace(/\{(first|n)\}/g, many)
        : rows[0].label
      : String(process.top || labels[0])
  return {
    count: values.length,
    top,
    origin: String(process.origin || ''),
    on: Boolean(mark && mark.on),
    follows,
    absent: rows.filter((row) => row.absent).length,
    rows,
  }
}
// 문서에서 읽은 공정 표지들(`marks`)로 이 화면의 회차 표지를 정한다 — 이 화면 주소의 마지막 표지. 회차가 끝났는데(`settled`) 표지가
// 없으면 이 화면은 공정 칸을 그리지 않은 것이다(`here: null` — 흐린 칩). 도는 동안 표지가 없으면 null(앞 값을 둔다).
function processLiveOf(marks, here, version, settled) {
  const mine = (Array.isArray(marks) ? marks : []).filter((mark) => mark && typeof mark === 'object' && mark.page === here)
  if (mine.length) return mine[mine.length - 1]
  return settled ? { page: here, version, here: null, tab: null, drawn: false } : null
}
// 패널에 보일 줄 — 단계 · 화면 거르기와 「닫힌 것 숨김」(해소 · 내용 바뀜 · 범위 바뀜 줄), 최신순(마지막 시각).
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
// 앞부분만 실은 표인가(`alert_table(clip=True)`) — CSV 는 그 화면 단추 몫이고 표 머리는 「앞 n건 · 전체 m건」 이다.
function tableClipped(table) {
  return Number(table.total || 0) > table.rows.length
}
// 표지 · 줄의 딸린 표들 — 행이 든 것만.
function validTables(value) {
  return Array.isArray(value) ? value.filter((table) => table && typeof table === 'object' && Array.isArray(table.rows)) : []
}
// 같은 사건 줄에 새 표지를 합친다 — 글 · 자리 · 계기는 새 표지의 것이고, 표지에 표가 들었으면 표도 새 것이다(코드 + 짧은 글이
// 같아도 표는 다를 수 있다 — 같은 수의 DB 등록 충돌 `SC-04`).
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

// 이미 고른 단추인가 — 탭은 `aria-selected`, 전환 단추는 `aria-checked` 다.
function tabChosen(button) {
  return ['aria-selected', 'aria-checked'].some((name) => button.getAttribute(name) === 'true')
}

// 줄에 「그 화면으로」 를 세우는가 — 지금 화면을 가리키는 줄은 열 탭이 있을 때만 할 일이 있다.
function showsGo(href, tab, here) {
  return typeof href === 'string' && (href !== here || Boolean(tab))
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

// <alerts-focus>
const TIP_HOST = '[data-testid="stTooltipHoverTarget"]'
const FOCUS_DIALOG = '[role="dialog"]'
const BUTTON_LABEL = '[data-testid="stMarkdownContainer"]'
const POPOVER_BUTTON = 'stPopoverButton'
const POPOVER_BODY = '[data-testid="stPopoverBody"]'
const TABBABLE = 'button:enabled, input:enabled, textarea:enabled, a[href], [tabindex="0"]'
// 머리 띠 판 안 탭 자리 — Alarm 판의 화면 거르기 칸이 `select` 다.
const PANEL_TABBABLE = `${TABBABLE}, select:enabled`

function buttonName(button) {
  const label = button.getAttribute('aria-label') || (button.querySelector(BUTTON_LABEL) || button).textContent
  return String(label || '').trim()
}

// 칸의 `tabindex` 는 Streamlit 이 쓰지 않는 자리라 이 함수가 단 것만 있다 — 단추가 풀린 칸은 도로 걷어 탭 자리가 둘이 되지 않게 한다.
function syncLockedTips(doc) {
  for (const host of doc.querySelectorAll(TIP_HOST)) {
    const locked = host.querySelector('button:disabled')
    if (locked) {
      host.setAttribute('tabindex', '0')
      host.setAttribute('aria-label', buttonName(locked))
    } else if (host.hasAttribute('tabindex')) {
      const live = host.querySelector('button')
      if (live && doc.activeElement === host) live.focus({ preventScroll: true })
      host.removeAttribute('tabindex')
      host.removeAttribute('aria-label')
    }
  }
}

// Streamlit 팝오버 본문은 문서 끝 포털이라 Tab 이 단추 다음 칸으로 건너뛴다 — 열린 단추에서 Tab 을 누르면 본문 첫 탭 자리로 들어간다.
function enterOpenPopover(doc, event) {
  const active = doc.activeElement
  if (event.shiftKey || !active || active.getAttribute('data-testid') !== POPOVER_BUTTON) return false
  if (active.getAttribute('aria-expanded') !== 'true') return false
  const body = doc.querySelector(POPOVER_BODY)
  for (const stop of body ? body.querySelectorAll(TABBABLE) : []) {
    // 제목의 숨은 고리처럼 초점을 받지 못하는 칸은 건너뛴다.
    stop.focus({ preventScroll: true })
    if (doc.activeElement !== stop) continue
    event.preventDefault()
    return true
  }
  return false
}

// 풍선을 닫는 길은 칸의 초점 나감뿐이다 — 초점은 옮기지 않고 그 사건만 칸에 보낸다.
function releaseHeldTip(doc, event) {
  const held = doc.activeElement
  const host = held && held.closest ? held.closest(TIP_HOST) : null
  if (!host || !host.contains(event.target) || host.contains(event.relatedTarget)) return false
  if (held.matches(':focus-visible')) return false
  held.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }))
  return true
}

function returnDialogFocus(doc, dialog, left) {
  const active = doc.activeElement
  if (!dialog.isConnected || (active && active !== doc.body)) return false
  if (left.isConnected) left.focus({ preventScroll: true })
  if (!doc.activeElement || doc.activeElement === doc.body) dialog.focus({ preventScroll: true })
  return true
}

// 머리 띠 판(Alarm · 변경 · 공정) 안 Tab 이 판 끝을 넘는가 — `count` 는 판 안 탭 자리 수, `at` 은 초점 칸의 차례(-1 = 판 자체 ·
// 탭 자리가 아닌 칸). 'next' = 마지막 칸 다음 Tab(판을 닫고 연 단추 다음 차례로), 'back' = 첫 칸 · 판 자체 앞 Shift+Tab(판을 닫고
// 연 단추로), null = 판 안에서 브라우저가 옮긴다.
function panelTabExit(count, at, shift) {
  if (shift) return at <= 0 ? 'back' : null
  if (count === 0) return 'next'
  return at === count - 1 ? 'next' : null
}
// </alerts-focus>

// <alerts-storage>
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

// 서버가 다시 시작됐나 — 이 탭에 적어 둔 앞 부트 표지(`key`)와 지금 표지(`mark`)를 견주고 지금 표지로 고쳐 적는다. 앞 표지가
// 있고 다를 때만 참이다 — 첫 접속 · 새 탭(앞 표지 없음)과 같은 프로세스의 새 세션(표지 같음)은 거짓이고, 저장소가 막힌
// 브라우저는 앞 표지를 읽지 못해 거짓이다. 프로세스의 표지라 세션만 사라진 탭도 거짓이다 — 그 탭은 `sessionLost` 가 맡는다.
function bootChanged(key, mark) {
  if (!key || !mark) return false
  const before = storageGet(key, null)
  if (before === mark) return false
  storageSet(key, mark)
  return typeof before === 'string' && before !== ''
}
// </alerts-storage>

// <alerts-reconnect>
const CONNECTED = 'CONNECTED'
const CONNECTING = 'CONNECTING'
// 다시 붙은 뒤 앱 전체 회차를 부르기 전에 본 스레드가 조용해야 하는 시간. 시계로만 기다리지 않는다 — 무거운 화면은 다시 그리느라 1초 남짓
// 바빠, 프런트가 스스로 돈 회차의 표지가 메시지 큐에 묶인 채 시계가 먼저 끝나 회차가 겹친다. 끝없이 기다리지는 않는다(가려진 탭은 타이머가
// 늘 늦어 조용한 것으로 세지 못한다).
const RECONNECT_WAIT_MS = 300
const RECONNECT_TICK_MS = 50
const RECONNECT_LIMIT_MS = 5000
// 사람 손이 닿으면 그 누름의 회차 표지가 돌아오기를 이만큼 더 기다린다. 표지가 끝내 움직이지 않으면(회차가 없는 누름) 그때 부른다.
const RECONNECT_TOUCH_MS = 700
const TOUCH_EVENTS = ['pointerdown', 'click', 'keydown']
// 조용해야 하는 시간 — 회차 표지는 망을 한 번 왕복해야 닿으므로 왕복 시간을 더한다. 왕복은 소켓이 붙는 데 걸린 시간(`handshake`)으로 어림한다.
function reconnectWait(handshake) {
  return RECONNECT_WAIT_MS + Math.min(Math.max(handshake, 0), RECONNECT_LIMIT_MS)
}
// 다시 붙었나 — 붙어 있지 않다가 붙음으로 돌아온 순간만 참이다. 앞 상태를 모르면(처음 본 순간) 거짓이다.
function cameBack(before, now) {
  return now === CONNECTED && typeof before === 'string' && before !== CONNECTED
}
// 틱 사이 간격(`gap`)을 조용한 시간에 더한다. 제때 깨지 못했으면 본 스레드가 바빴던 것이라 처음부터 센다.
function quietAfter(quiet, gap) {
  return gap > RECONNECT_TICK_MS * 2 ? 0 : quiet + gap
}
// 다시 붙은 뒤 틱마다 할 일 — 'stop'(다시 끊겼거나 회차가 보였거나 돌고 있다 — 프런트가 스스로 돈 회차다), 'wait'(아직 바쁘다 · 사람 손이 막
// 닿았다), 'ask'(앱 전체 회차를 부른다). `touched` 는 마지막으로 손이 닿은 뒤 지난 시간이다 — 손이 닿은 동안은 상한에서도 부르지 않는다.
function reconnectStep(connection, runState, moves, quiet, waited, need = RECONNECT_WAIT_MS, touched = Infinity) {
  if (connection !== CONNECTED || moves > 0 || runState === 'running' || runState === 'rerunRequested') return 'stop'
  if (touched < need + RECONNECT_TOUCH_MS) return 'wait'
  return quiet >= need || waited >= RECONNECT_LIMIT_MS ? 'ask' : 'wait'
}
// 세션만 사라졌나 — 같은 문서의 앞 data(`before`)와 세션 표지가 다른데 부트 표지는 같고, 잃은 것이 있었을 때만 참이다. 부트 표지가 다르면
// 재시작이라 `GL-07` 이 맡고, 앞 data 가 없는 새 문서는 표지가 없어 거짓이다.
function sessionLost(before, after, dialogOpen) {
  const session = (data) => ((data || {}).session || {}).mark
  const boot = (data) => ((data || {}).boot || {}).mark
  if (!session(before) || !session(after) || session(before) === session(after)) return false
  if (boot(before) !== boot(after)) return false
  const changes = before.changes
  return Boolean(dialogOpen) || (Array.isArray(changes) && changes.length > 0)
}
// </alerts-reconnect>

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

function installFocusShell() {
  if (window.__capaFocusShell) return
  window.__capaFocusShell = true
  document.addEventListener(
    'keydown',
    (event) => {
      if (event.key !== 'Tab') return
      syncLockedTips(document)
      enterOpenPopover(document, event)
    },
    true,
  )
  document.addEventListener('pointerout', (event) => releaseHeldTip(document, event), true)
  // 대화상자를 마우스로 닫으면 초점이 여는 단추로 돌아와 마우스 없이 풍선이 선다 — React 가 연 뒤(거품 단계) 닫는다.
  document.addEventListener('focusin', (event) => {
    const host = event.target.closest ? event.target.closest(TIP_HOST) : null
    if (host && !host.matches(':hover')) releaseHeldTip(document, event)
  })
  document.addEventListener(
    'focusout',
    (event) => {
      const left = event.target
      const dialog = !event.relatedTarget && left.closest ? left.closest(FOCUS_DIALOG) : null
      if (dialog) setTimeout(() => returnDialogFocus(document, dialog, left), FOCUS_RETURN_MS)
    },
    true,
  )
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
    // 회차가 보인 수(표지가 움직임 · data 가 닿음) — 다시 붙은 뒤 기다리는 사이 회차가 돌았는지 본다.
    runMoves: 0,
    connection: null,
    connectingAt: 0,
    // 마지막으로 끊길 때 대화상자가 열려 있었나.
    dialogAtCut: false,
    reconnectTimer: 0,
    // 다시 붙은 뒤 기다리는 동안만 사람 손을 보는 듣기(`connectionMoved`)의 끊개.
    reconnectTouch: null,
    // 앱 전체 회차를 부르는 트리거 — 그림마다 새것으로 고쳐 쥔다.
    ask: null,
    scanTimer: 0,
    placeTries: 0,
    placeTimer: 0,
    resizer: null,
    resizedSlot: null,
    // 이 화면의 공정 회차 표지(`processLiveOf`) — 같은 화면 · 같은 판이면 다음 회차의 짐작보다 이긴다.
    procLive: null,
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
  C.processPanel = buildProcessPanel(C)
  shadow.append(C.panel, C.changesPanel, C.processPanel)
  document.body.appendChild(host)

  // 탭 줄 JS 의 알림 길. 칸이 서기 전에 담긴 알림을 꺼낸다.
  window.__capaAlerts = {
    raise: (note) => raiseLocal(C, note),
    scan: () => scan(C),
  }
  const queued = Array.isArray(window.__capaAlertQueue) ? window.__capaAlertQueue.splice(0) : []
  for (const note of queued) raiseLocal(C, note, false)

  // 판 밖 누름 · Esc 로 닫는다(모달이 아니다). 판 끝을 넘는 Tab 도 판을 닫고 연 단추 차례로 돌아간다(`leavePanelByTab`). 처리기는
  // 문서에 하나다.
  document.addEventListener(
    'pointerdown',
    (event) => {
      if (!C.open) return
      const path = event.composedPath ? event.composedPath() : []
      const { panel, host } = panelOf(C, C.open)
      if (path.includes(panel) || (host && path.includes(host))) return
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
      } else if (event.key === 'Tab' && C.open && !event.altKey && !event.ctrlKey && !event.metaKey) {
        leavePanelByTab(C, event)
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
  // 같은 코드의 다른 범위(시나리오 · 조회기간 · 리비전을 바꿈)는 지금 범위가 아니다 — 「범위가 바뀜」(`scope`)으로 닫는다.
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
  readProcessMark(C)
  ensureToolbar(C)
  paintAll(C)
  measureToolbar(C)
  settleTab(C)
}

function scanSoon(C) {
  clearTimeout(C.scanTimer)
  C.scanTimer = setTimeout(() => scan(C), 0)
}

// 앱 뿌리의 회차 표지 · 연결 표지를 관찰자 하나로 본다. 칸이 다시 그려져도 뿌리가 같으면 늘지 않는다.
function watchRoot(C) {
  const root = document.querySelector(APP_ROOT)
  if (!root || (C.runRoot === root && C.runObserver)) return
  if (C.runObserver) C.runObserver.disconnect()
  C.runRoot = root
  C.connection = root.getAttribute(CONNECTION_STATE)
  C.runObserver = new MutationObserver((records) => {
    if (records.some((record) => record.attributeName === CONNECTION_STATE)) connectionMoved(C, root)
    if (records.some((record) => record.attributeName === RUN_STATE)) {
      C.runMoves += 1
      scanSoon(C)
    }
  })
  C.runObserver.observe(root, { attributes: true, attributeFilter: [RUN_STATE, CONNECTION_STATE] })
}

function connectionMoved(C, root) {
  const before = C.connection
  const now = root.getAttribute(CONNECTION_STATE)
  if (now === before) return
  C.connection = now
  endReconnectWait(C)
  // 끊기는 순간에 본다 — 다시 붙은 뒤에는 새 회차가 대화상자를 걷고 있을 수 있다.
  if (before === CONNECTED) C.dialogAtCut = Boolean(document.querySelector(DIALOG))
  if (now === CONNECTING) C.connectingAt = performance.now()
  if (!cameBack(before, now)) return
  const movesAtBack = C.runMoves
  const begun = performance.now()
  const need = reconnectWait(before === CONNECTING ? begun - C.connectingAt : 0)
  let last = begun
  let quiet = 0
  let touchedAt = -Infinity
  C.reconnectTouch = new AbortController()
  const touched = () => {
    touchedAt = performance.now()
  }
  for (const type of TOUCH_EVENTS) {
    document.addEventListener(type, touched, { capture: true, passive: true, signal: C.reconnectTouch.signal })
  }
  const tick = () => {
    const at = performance.now()
    quiet = quietAfter(quiet, at - last)
    last = at
    const step = reconnectStep(C.connection, root.getAttribute(RUN_STATE), C.runMoves - movesAtBack, quiet, at - begun, need, at - touchedAt)
    if (step === 'wait') {
      C.reconnectTimer = setTimeout(tick, RECONNECT_TICK_MS)
      return
    }
    endReconnectWait(C)
    if (step === 'ask' && C.ask) C.ask('reconnected', Date.now())
  }
  C.reconnectTimer = setTimeout(tick, RECONNECT_TICK_MS)
}

function endReconnectWait(C) {
  clearTimeout(C.reconnectTimer)
  if (C.reconnectTouch) C.reconnectTouch.abort()
  C.reconnectTouch = null
}

function retireCenter(C) {
  if (C.runObserver) C.runObserver.disconnect()
  endReconnectWait(C)
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
    const shown = [...C.stack.children]
    const victim = shown[overflowVictim(shown.map((node) => node.dataset.level))]
    const owner = [...C.live.entries()].find(([, item]) => item.el === victim)
    if (owner) hidePopup(C, owner[0], owner[0] !== key)
    else victim.remove()
  }
  if (repeat) {
    const node = live.el
    requestAnimationFrame(() => requestAnimationFrame(() => attract(C, node, live.level)))
  }
}

// `seen` 이 거짓이면 방금 세운 칸이 넘침으로 곧바로 걷힌 것이다 — 보인 적이 없으니 반복 창(`goneAt`)을 이 회로 열지 않는다.
// 처음 난 알림은 다음에 나도 「×n」 · 시선 끌기 없이 새 칸으로 서고, 앞에 보였던 알림은 그때 연 창이 그대로다.
function hidePopup(C, key, seen = true) {
  const live = C.live.get(key)
  if (!live) return
  clearTimeout(live.timer)
  if (live.el && live.el.isConnected) live.el.remove()
  live.visible = false
  if (seen) live.goneAt = Date.now()
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
  if (!C.procHost || !C.procHost.isConnected) {
    const host = toolbarHost(C, toolbar.process, 'capa-alert-proc')
    const shadow = host.shadowRoot
    let chip = shadow.querySelector('.proc')
    if (!chip) {
      chip = el('button', 'chip proc')
      chip.type = 'button'
      chip.setAttribute('aria-haspopup', 'dialog')
      chip.setAttribute('aria-expanded', 'false')
      const dot = el('span', 'mdot')
      dot.setAttribute('aria-hidden', 'true')
      chip.append(
        icon(FUNNEL_PATH, 'funnel'),
        el('span', 'word', t.process_word || ''),
        el('b', 'count'),
        el('span', 'sep', '·'),
        el('span', 'top'),
        el('span', 'msep', '·'),
        el('span', 'miss'),
        dot,
      )
      chip.addEventListener('click', () => togglePanel(C, 'process'))
      shadow.append(chip)
    }
    host.toggleAttribute('data-empty', true)
    C.procHost = host
    C.procChip = chip
  }
  if (!C.sampleHost || !C.sampleHost.isConnected) {
    const host = toolbarHost(C, toolbar.sample, 'capa-alert-sample')
    const shadow = host.shadowRoot
    let mark = shadow.querySelector('.sample')
    if (!mark) {
      mark = el('span', 'sample')
      mark.tabIndex = 0
      mark.setAttribute('role', 'note')
      mark.title = t.sample_title || ''
      mark.setAttribute('aria-label', t.sample_title || '')
      mark.append(icon(FLASK_PATH, 'flask'), el('span', 'word', t.sample || ''))
      shadow.append(mark)
    }
    host.toggleAttribute('data-empty', true)
    C.sampleHost = host
  }
  palette(C, C.alarmHost)
  palette(C, C.chipHost)
  palette(C, C.procHost)
  palette(C, C.sampleHost)
  placeHost(C, slot, C.procHost)
  placeHost(C, slot, C.sampleHost)
  placeHost(C, slot, C.chipHost)
  placeHost(C, slot, C.alarmHost)
  watchSlot(C, slot)
}

// 툴바 · 판 아이콘 하나(24 단위 path, 글자 색).
function icon(path, className) {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('class', className)
  const shape = document.createElementNS(SVG_NS, 'path')
  shape.setAttribute('d', path)
  svg.append(shape)
  return svg
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

function buildProcessPanel(C) {
  const t = text(C)
  const panel = el('section', 'panel process')
  panel.hidden = true
  panel.tabIndex = -1
  panel.setAttribute('role', 'dialog')
  const head = el('div', 'head')
  const title = el('h2')
  const sum = el('span', 'sum')
  const close = el('button', 'x', '×')
  close.type = 'button'
  close.setAttribute('aria-label', t.close || '')
  close.addEventListener('click', () => closePanel(C, true))
  head.append(title, el('span', 'grow'), sum, close)
  const list = el('ul', 'plist')
  const acts = el('div', 'pacts')
  const pick = el('button', 'pbtn', t.process_pick || '')
  pick.type = 'button'
  pick.addEventListener('click', () => {
    const field = processField(C)
    closePanel(C, false)
    if (field) field.click()
  })
  const clear = el('button', 'pbtn', t.process_clear || '')
  clear.type = 'button'
  clear.addEventListener('click', () => {
    closePanel(C, false)
    if (C.ask) C.ask('process_clear', Date.now())
  })
  acts.append(pick, clear)
  panel.append(head, list, acts)
  C.processParts = { title, sum, list, pick }
  return panel
}

// 이 화면 사이드바 「공정」 값 칸 단추 — 판 「공정 고르기」 가 눌러 그 칸의 팝업을 연다. 칸이 없거나 잠겼으면 null.
function processField(C) {
  const key = C.data.process && C.data.process.field
  if (!key) return null
  const button = document.querySelector(`[data-testid="stSidebar"] .st-key-${key} button`)
  return button && !button.disabled ? button : null
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

// 「그 화면으로」 가 맡긴 탭 고르기 — 그 화면(`here`)에 닿고 회차가 끝났으면 이름이 맞는 탭 · 전환 단추를 누른다. 이미 열린 탭이면
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
    const buttons = [...document.querySelectorAll(TAB_BUTTON), ...document.querySelectorAll(SEGMENT_BUTTON)]
    const button = buttons.find((item) => tabMatches(item.textContent, first))
    if (button && !tabChosen(button)) {
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
  const total = Number(table.total || table.rows.length).toLocaleString()
  const clipped = tableClipped(table)
  head.append(
    el('b', '', table.title || ''),
    el('span', 'count', clipped ? fill(t.table_rows_clipped, { n: table.rows.length.toLocaleString(), total }) : fill(t.table_rows, { n: total })),
    el('span', 'grow'),
  )
  if (!clipped) head.append(csv)
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
      if (showsGo(item.href, item.tab, C.data.here)) {
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
  const why = { gone: t.resolved_gone }
  const time = forCopy ? stamp : hms
  const pairs = [
    [t.log_code, `${row.code} · ${levelLabel(C, row.level)} · ${row.kind === 'state' ? t.kind_state : t.kind_event}`],
    [t.log_first, time(row.first)],
    [t.log_last, time(row.last) + (row.n > 1 ? ` (${fill(t.log_times, { n: row.n })})` : '')],
    [t.log_page, pageLabel(row) || '—'],
    [t.log_cause, row.cause || (row.kind === 'state' ? t.cause_new : t.cause_event) || '—'],
  ]
  if (row.scopeLabel) pairs.push([t.log_scope, row.scopeLabel])
  const mark = stateMark(row)
  if (mark === 'scope') {
    pairs.push([t.log_scope_moved, (forCopy ? stamp : hm)(row.resolvedAt)])
  } else if (mark === 'changed') {
    pairs.push([t.log_content_moved, (forCopy ? stamp : hm)(row.resolvedAt)])
  } else if (mark) {
    pairs.push([
      t.log_resolved,
      mark === 'resolved' ? `${(forCopy ? stamp : hm)(row.resolvedAt)} — ${why[row.resolvedWhy] || ''}` : t.not_yet,
    ])
  }
  if (row.detail) pairs.push([t.log_detail, row.detail])
  if (forCopy) {
    pairs.push([t.log_full, row.full])
    for (const table of validTables(row.tables)) {
      const count = Number(table.total || table.rows.length)
      const value = tableClipped(table)
        ? fill(t.log_table_value_clipped, { title: table.title || '', n: table.rows.length.toLocaleString(), total: count.toLocaleString() })
        : fill(t.log_table_value, { title: table.title || '', n: count.toLocaleString() })
      pairs.push([t.log_table, value])
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
    const mark = stateMark(row)
    if (mark) {
      const closed = mark === 'scope' ? t.scope_moved : mark === 'changed' ? t.content_moved : t.resolved
      const label = mark === 'open' ? t.open : fill(closed, { time: hm(row.resolvedAt) })
      meta.append(el('span', `state${mark === 'open' ? ' open' : ''}`, label))
    }
    const acts = el('span', 'acts')
    if (showsGo(row.href, row.tab, C.data.here)) {
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

// 공정 칩 · 판 — 값이 없으면 칩을 숨기고 열린 판을 닫는다. 이 화면에 걸리면 강조색, 아니면 흐린 테두리(풍선에 「이 화면엔 안 걸림」).
function paintProcess(C) {
  if (!C.procHost) return
  const t = text(C)
  const chip = processChipOf(C.data.process, C.procLive, C.data.here, t.process_rest)
  C.procHost.toggleAttribute('data-empty', !chip)
  if (!chip) {
    if (C.open === 'process') closePanel(C, false)
    return
  }
  const button = C.procChip
  button.classList.toggle('on', chip.on)
  button.classList.toggle('has-miss', chip.absent > 0)
  button.querySelector('.count').textContent = String(chip.count)
  button.querySelector('.top').textContent = chip.top
  button.querySelector('.miss').textContent = chip.absent ? fill(t.process_absent, { n: chip.absent }) : ''
  const names = fill(t.process_names, { names: chip.rows.map((row) => row.label).join(' · ') })
  const parts = [chip.origin ? `${names} — ${fill(t.process_from, { origin: chip.origin })}` : names]
  if (chip.absent) parts.push(fill(t.process_absent, { n: chip.absent }))
  if (!chip.on) parts.push(t.process_off || '')
  const title = parts.join(' · ')
  if (button.title !== title) button.title = title
  button.setAttribute('aria-label', `${fill(t.process_aria, { n: chip.count })} — ${title}`)
  const P = C.processParts
  P.title.textContent = fill(t.process_panel, { n: chip.count })
  C.processPanel.setAttribute('aria-label', P.title.textContent)
  P.sum.textContent = chip.origin ? fill(t.process_from, { origin: chip.origin }) : ''
  P.list.replaceChildren()
  for (const row of chip.rows) {
    const line = el('li', `prow${row.absent ? ' absent' : ''}`)
    const mark = el('span', 'pm', chip.follows ? (row.absent ? '–' : '✓') : '·')
    mark.setAttribute('aria-hidden', 'true')
    line.append(mark, el('span', 'pn', row.label))
    if (row.absent) line.append(el('span', 'pa', t.process_absent_row || ''))
    P.list.append(line)
  }
  P.pick.hidden = !processField(C)
}

function paintSample(C) {
  if (C.sampleHost) C.sampleHost.toggleAttribute('data-empty', !C.data.sample)
}

// 회차 표지를 훑을 때 이 화면의 공정 표지를 읽는다. 지금 탭 표지가 실렸으면 탭 줄에 알린다(그 회차의 탭 줄은 페이지보다 먼저 그려져
// 처음 그린 화면 · 바뀐 선택지를 모른다).
function readProcessMark(C) {
  const process = C.data.process
  if (!process || !process.marker) return
  const marks = []
  for (const node of document.querySelectorAll(`[${process.marker}]`)) {
    try {
      marks.push(JSON.parse(node.getAttribute(process.marker) || 'null'))
    } catch (error) {
      /* 깨진 표지는 건너뛴다 */
    }
  }
  const root = document.querySelector(APP_ROOT)
  const settled = Boolean(root) && root.getAttribute(RUN_STATE) === 'notRunning'
  const live = processLiveOf(marks, C.data.here, process.version, settled)
  if (!live) return
  C.procLive = live
  if (live.drawn !== false) {
    window.dispatchEvent(new CustomEvent(PROCESS_EVENT, { detail: { href: live.page, tab: live.tab || null } }))
  }
}

function paintAll(C) {
  paintProcess(C)
  paintSample(C)
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

// 떠 있는 판 셋(Alarm 패널 · 변경 판 · 공정 판)과 그 여는 단추 · 툴바 호스트.
function panelOf(C, which) {
  if (which === 'alarms') return { panel: C.panel, button: C.alarmButton, host: C.alarmHost }
  if (which === 'process') return { panel: C.processPanel, button: C.procChip, host: C.procHost }
  return { panel: C.changesPanel, button: C.chip, host: C.chipHost }
}

// 공정 판은 칩 바로 아래, 칩 왼쪽 끝에 맞춘다(창 오른쪽을 넘지 않게).
function placeProcessPanel(C) {
  if (!C.procHost) return
  const box = C.procHost.getBoundingClientRect()
  const width = C.processPanel.offsetWidth || 336
  const left = Math.max(12, Math.min(box.left, window.innerWidth - width - 12))
  C.processPanel.style.left = `${Math.round(left)}px`
  C.processPanel.style.right = 'auto'
}

function togglePanel(C, which) {
  if (C.open === which) {
    closePanel(C, true)
    return
  }
  if (C.open) closePanel(C, false)
  C.open = which
  const { panel, button } = panelOf(C, which)
  panel.hidden = false
  if (button) button.setAttribute('aria-expanded', 'true')
  if (which === 'alarms') {
    paintList(C)
    markRead(C)
  } else if (which === 'process') {
    paintProcess(C)
    placeProcessPanel(C)
  } else {
    paintChanges(C)
  }
  panel.focus({ preventScroll: true })
}

// 판 안 Tab 의 끝 — 판은 body 끝 호스트에 붙어 문서 차례로 맨 뒤라 마지막 칸 다음 Tab 이 문서 밖(body)으로 빠졌다. 가두지
// 않는다(모달이 아니다 — 판 밖 누름 · Esc 로 닫는 것과 같다): 마지막 칸 다음 Tab 은 판을 닫고 초점을 연 단추에 돌린 뒤 막지 않아
// 브라우저 기본 Tab 이 그 단추 다음 툴바 차례로 넘기고, 첫 칸 · 판 자체 앞 Shift+Tab 은 판을 닫고 연 단추에 선다(`panelTabExit`).
function leavePanelByTab(C, event) {
  const { panel, button } = panelOf(C, C.open)
  const path = event.composedPath ? event.composedPath() : []
  if (!button || !path.includes(panel)) return
  const stops = [...panel.querySelectorAll(PANEL_TABBABLE)].filter((stop) => stop.getClientRects().length > 0)
  const exit = panelTabExit(stops.length, stops.indexOf(path[0]), event.shiftKey)
  if (!exit) return
  closePanel(C, true)
  if (exit === 'back') event.preventDefault()
}

function closePanel(C, refocus) {
  if (!C.open) return
  const { panel, button } = panelOf(C, C.open)
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
  const { data, setTriggerValue } = component
  if (!data) return undefined
  installFocusShell()
  let C = window.__capaAlertCenter
  if (!C || !C.host || !C.host.isConnected) {
    if (C) retireCenter(C)
    C = createCenter(data)
    window.__capaAlertCenter = C
  }
  const before = C.data
  C.data = data
  C.ask = setTriggerValue
  // data 가 닿았으면 앱 전체 회차가 돈 것이다. 표지만으로는 놓친다 — 본 스레드가 묶인 사이 끝난 회차는 메시지가 한꺼번에 처리돼 표지가 움직이지 않는다.
  C.runMoves += 1
  palette(C, C.host)
  watchRoot(C)
  let changed = false
  for (const note of Array.isArray(data.events) ? data.events : []) if (handle(C, note)) changed = true
  const boot = data.boot || {}
  if (bootChanged((data.storage || {}).boot, boot.mark) && handle(C, boot.notice)) changed = true
  if (sessionLost(before, data, C.dialogAtCut) && handle(C, data.session.notice)) changed = true
  if (changed) persist(C)
  scan(C)
  return undefined
}
