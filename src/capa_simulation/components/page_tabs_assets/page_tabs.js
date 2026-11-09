// 머리 띠 아래 화면 탭 줄. 파이썬(`components/page_tabs.py`)이 연 탭·지금 탭·점·고정을 data 로 주고, 누름은
// 트리거(`select`·`close`·`pin`·`move`) 한 번으로만 돌려준다 — 남는 상태 값은 보내지 않는다(보내면 앱 전체가 다시 돈다).
// 화면을 옮기지 않는 누름(고정·끌어서 차례 바꾸기·다른 탭 닫기)은 누르자마자 서버와 같은 규칙으로 탭 줄을 고쳐 그리고
// (`<tabs-order>`) 그 차례를 트리거에 싣는다 — 서버는 같은 차례면 페이지를 다시 돌리지 않는다(`page_tabs._settle_drawn`).
// 고정하지 않은 탭은 끌어서(`<tabs-drag>`) 또는 `Ctrl+Shift+←/→` 로 차례를 바꾼다. 차례 바꾸기는 누를 때마다 보내지 않는다 —
// 곧바로 다시 그리고, 연달아 옮긴 마지막 그림만 쉼 뒤 앱이 돌지 않을 때 한 번 보낸다(`<tabs-batch>`). 고정·닫기·고르기는 지금
// 그림을 함께 실어 아직 보내지 않은 차례를 데려간다.
// 이 함수는 data·테마가 바뀔 때마다 다시 불린다. 뼈대는 처음 한 번 세우고, 다시 불리면 탭 id 로 맞춰 고친다.
// 탭은 `<nav>` 안의 목록과 단추다. 탭 패널이 없는 이동 목록이라 탭 역할(ARIA)을 쓰지 않는다 — 배포 화면 확인
// 스크립트가 그 역할로 본문 탭을 찾는다.
// 탭이 상한이면 사이드바·본문 화면 링크로 열린 탭이 아닌 화면에 가는 누름을 옮기기 전에 막는다 — 이 모듈은 iframe 이
// 아니라 본 문서에서 돌아 문서 capture 단계에서 Streamlit(React 뿌리)보다 먼저 받는다. 서버가 옮긴 뒤 되돌리면 두
// 화면이 브라우저 기록에 쌓여 뒤로가기가 그 화면에 갇힌다(`page_tabs_state.switch_to_queued_tab` 은 마지막 안전망이다).
// 앞서 지나 보낸 링크가 연 탭은 그 탭이 탭 줄 data 에 올 때까지 열린 탭으로 센다(`<tabs-links>`).
// 뒤로·앞으로가기는 막지 못한다 — Streamlit 의 `popstate` 처리기가 이 모듈보다 먼저 걸려 먼저 돈다(1.63 브라우저 확인).
// 브라우저 기록은 문서 하나에서 지킨다 — 서버가 주소 인자를 바꿀 때 Streamlit 프런트가 쌓는 칸은 늘 칸 바꾸기다
// (`<tabs-history>`, 탭 줄 누름뿐 아니라 본문 단추·HOME 칸·링크 인자를 받아 지우는 화면 모두). 탭으로 화면을 옮기는
// 누름(다른 탭 고르기·지금 탭 닫기)은 하나를 더 지킨다 — 한 번에 하나. 옮기는 동안 누른 탭은 옮긴 화면의 탭 줄이 오고
// 그 회차가 끝나거나 잠깐 지날 때까지 기다렸다 마지막 것만 보낸다(`<tabs-queue>`). 아래 `// <tabs-…>` 구획은 DOM 을
// 모르는 순수 함수라 node 시험이 떼어 돌린다(`tests/test_page_tabs_assets.py`). 지킴이를 거는 `<tabs-history-install>` 만
// 창을 만지고, 입장 화면 JS 가 `<tabs-history>` 와 함께 떼어 싣는다(`components/history_guard.py`).
// 목록이 옆으로 넘치면(좁은 창·탭이 많을 때) 더 있는 쪽 가장자리를 흐리고 화살표 표지를 단다(`<tabs-edges>`).
// 키보드 초점은 탭 줄 안에 남긴다(`<tabs-focus>`) — 키보드 초점이 있던 탭을 닫으면 이웃 탭으로 옮기고, 키보드로 화면을 옮긴
// 뒤 초점이 body 로 빠졌으면 지금 탭으로 돌려준다.
// 떠나기 확인은 앞 회차 data 의 `leave` 로 정한다. 편집표 칸을 쓰는 중이거나 막 적용(Enter)한 직후에 누르면 그 편집을 실은
// 회차가 아직 돌아오지 않아 `leave` 가 비어 있었다 — 확인 없이 옮기고 편집이 말없이 사라졌다(E2E 결함). 그래서 편집표에서
// 막 손을 뗀 누름은 그 회차가 돌아올 때까지 잠깐 붙들었다가 새 `leave` 로 묻는다(`<tabs-hold>`). 탭 줄 밖의 떠나기인 테마
// 단추도 같은 붙들기를 지난다(`window.__capaLeaveGate`). 사이드바 화면 링크도 같다 — 터치 톡은 초점이 빠지며 나간 표의 출납
// 회차와 거의 함께 닿아, 그 회차가 지금 화면 주소로 돌며 링크 이동을 덮는다. 붙들었다가 같은 링크를 다시 누른다.
// 닫기·고정은 누르자마자 목록을 움직이므로, 그 뒤 같은 자리로 온 더블클릭의 둘째 누름이 다른 탭에 닿으면 버린다(`<tabs-press>`).
// 테마 단추·새로고침은 새 세션이라 세션이 든 설비 시나리오가 공식으로 돌아간다. 문서를 떠날 때 띠 CSS 변수(테마 단추면 공식
// 발행 쌍이 아니던 설비 시나리오, 새로고침이면 가정 설비 시나리오의 이름)를 이 탭의 `sessionStorage` 에 적고, 새로 읽은
// 문서에서 한 번 알린다(`<tabs-return>`).
// 알림(상한 · 공식 복귀)은 탭 줄 칸이 아니라 같은 문서의 알림 칸(`components/alert_center.py` — 오른쪽 아래 알림창 한 꼴 ·
// Alarm 기록)에 낸다(`raiseAlert` — `window.__capaAlerts.raise`, 칸이 아직 서지 않았으면 `window.__capaAlertQueue`). 알림 칸
// 「그 화면으로」 는 `capa-open-page` 사건으로 오고, 탭 줄이 제 이동 길(열린 탭이면 고르기 — 떠나기 확인 · 한 번에 하나,
// 아니면 그 화면 링크 누름 — 상한 거름)로 옮긴다.
// 새로고침·브라우저 탭 닫기처럼 문서 자체를 떠날 때는 저장하지 않은 편집이 있으면 브라우저 확인 창을 띄운다 — 표지는 테마
// 단추가 읽는 것과 같은 CSS 변수다(`<tabs-unload>`). 앱이 스스로 새로 읽는 것(테마 단추 — 이미 물었다)은 묻지 않는다.
const ICON_FONT = 'Material Symbols Rounded'
const PAGE_LINK = 'a[data-testid="stPageLink-NavLink"]'
const BUSY_MS = 10000
// 알림 칸 「그 화면으로」 사건(`alert_center.js` 의 `OPEN_PAGE_EVENT`).
const OPEN_PAGE_EVENT = 'capa-open-page'
// 알림 칸이 회차 끝에 공정 값 칸 표지를 읽어 지금 탭의 공정 표지를 바로잡는 사건(`alert_center.js` 의 `PROCESS_EVENT`) —
// {href, tab: {miss, title} | null}. 탭 줄은 페이지보다 먼저 그려져 그 회차에 처음 그린 화면 · 바뀐 선택지를 모른다.
const PROCESS_EVENT = 'capa-process-here'
// 공정 표지 깔때기 — 사이드바 공정 값 칸 아이콘(Material `filter_alt`)과 같은 선 꼴(속이 빈 깔때기 + 대)이다. 칠한 세모는 12px 에서
// 탭 펼침 꺾쇠(▾)로 읽혔다. 알림 칸 공정 칩 · 판과 같은 상수다(`alert_center.js` — 그물 `tests/test_page_tabs_assets.py`).
const FUNNEL_PATH = 'M11 20q-.425 0-.713-.288T10 19v-6L4.2 5.6q-.375-.5-.113-1.05T5 4h14q.65 0 .913.55t-.113 1.05L14 13v6q0 .425-.288.713T13 20zm1-7.7L16.95 6H7.05z'
// 알림창 짧은 글의 글자 수(파이썬 `alerts.SHORT_LIMIT` — data `alerts.short_limit`).
const SHORT_LIMIT = 60
// 보낸 이동이 끝났는지 다시 보는 간격 — 옮긴 화면 회차가 다 돌았는지는 Streamlit 뿌리의 회차 표지로 본다.
const SETTLE_POLL_MS = 100
// 옮긴 화면의 탭 줄이 온 뒤 이만큼 지나면 그 회차가 아직 돌아도 기다리던 누름을 보낸다(`<tabs-queue>`). 가벼운 화면은
// 이 안에 회차가 끝나 전처럼 회차 끝에 보낸다(사외 사본 약 0.7초).
const MOVED_GRACE_MS = 1000
const APP_ROOT = '[data-testid="stApp"]'
// 편집표(glide 격자)와 그 칸 편집기. 편집기는 격자 밖 포털에 뜰 수 있어 그 틀(`gdg-clip-region`)도 본다. 그림자 DOM
// Components v2 편집 칸(설비 마스터 표 등)은 data 의 `grids` 로 더한다(`<tabs-grid>`).
const GRID = '[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"], .gdg-clip-region'
// 편집표에서 손을 뗀 뒤 이만큼 안의 누름은 붙든다(쓰는 중이면 시간과 상관없이 붙든다).
const EDIT_MS = 5000
// 붙든 누름은 적어도 이만큼은 편집 회차를 기다린다 — 편집이 보낸 회차 요청에 서버가 답해 뿌리 표지가 「돈다」로 바뀌기 전.
const HOLD_MS = 400
// 닫기·고정 누름 뒤 같은 자리의 둘째 누름을 더블클릭의 꼬리로 보는 창(`<tabs-press>`) — Windows 기본 더블클릭 시간과
// 손떨림 너비.
const DOUBLE_PRESS_MS = 500
const DOUBLE_PRESS_PX = 8
// 끌기(`<tabs-drag>`) — 마우스·펜이 끌기로 넘어가는 가로 움직임, 터치 길게 누르기, 가장자리에서 한 프레임에 굴리는 최대 px,
// 끈 뒤 누름을 버리는 창. 키보드 대안은 `MOVE_KEYS` 다(단추의 `aria-keyshortcuts`).
const DRAG_SLOP_PX = 5
const TOUCH_HOLD_MS = 350
const DRAG_EDGE_SPEED_PX = 12
const DRAG_CLICK_MS = 400
// Esc·새 data 로 접은 끌기의 포인터를 놓을 때까지 지켜보는 창 사건(`heldRelease`).
const RELEASE_EVENTS = ['pointerup', 'pointerdown', 'pointercancel']
const MOVE_KEYS = 'Control+Shift+ArrowLeft Control+Shift+ArrowRight'
// 차례 바꾸기를 서버에 보내기 전 쉼(`<tabs-batch>`) — 이 안에 또 옮기면 다시 잰다. 키를 누르고 있거나(자동 반복 약 30ms)
// 0.1~0.2초 간격으로 거듭 누르는 동안은 보내지 않고, 손을 뗀 뒤 한 번 보낸다. 그때 앱이 돌고 있으면 끝날 때까지(길어야
// `BUSY_MS`) 더 기다린다 — 도는 페이지 회차를 끊어 다시 돌리지 않는다.
const MOVE_SEND_MS = 400
// 보낸 그림의 번호가 이만큼 지나 온 data 에도 없으면 서버가 받지 못한 것이다 — 다시 담아 보낸다(`dataArrived`).
const MOVE_LOST_MS = 2000
// 넘친 목록 가장자리 흐림 폭(`page_tabs.css` 의 2rem). 지금 탭을 보이게 굴릴 때도 이만큼 띄워 흐림 밖에 둔다.
const EDGE_PX = 32
// 새로 읽으면 공식으로 돌아갈 설비 시나리오(띠 CSS 변수 둘 — 파이썬 `app_header.EQUIPMENT_RETURN_VARIABLE` 은 테마 단추
// 몫으로 공식 발행 쌍이 아니면 모두, `EQUIPMENT_RELOAD_RETURN_VARIABLE` 은 새로고침 몫으로 가정 설비 시나리오만)와, 문서를
// 떠날 때 그 값을 적는 이 탭의 `sessionStorage` 칸. 테마 단추는 새로 읽기 직전에 `THEME_SWITCH_KEY`(파이썬
// `theme_toggle.THEME_SWITCH_STORAGE_KEY`)를 남겨 읽을 변수와 알림 글을 가른다.
const RETURN_VARIABLE = '--capa-equipment-return'
const RELOAD_RETURN_VARIABLE = '--capa-equipment-return-reload'
const RETURN_KEY = 'capa-equipment-return'
const THEME_SWITCH_KEY = 'capa-theme-switch'
// 알린 칸을 지우기까지. 이 안에 문서가 떠나면(테마 키를 맞추는 새로고침) 다음 문서가 다시 알린다.
const RETURN_KEEP_MS = 3000

// 같은 문서의 알림 칸에 낸다. 칸이 아직 서지 않았으면(탭 줄이 먼저 그려진다) 담아 두고 칸이 설 때 꺼낸다.
function raiseAlert(note) {
  const center = window.__capaAlerts
  if (center && typeof center.raise === 'function') center.raise(note)
  else (window.__capaAlertQueue = window.__capaAlertQueue || []).push(note)
}

// <tabs-history>
// 화면 이동 한 번이 브라우저 기록을 한 칸만 쌓게 한다. Streamlit 1.63 프런트는 서버가 주소 인자를 바꿀 때마다
// (`page_info_changed` — `st.query_params` 쓰기·지우기, `st.switch_page` 의 인자 다시 적기) **지금 경로**로 한 칸
// 쌓는다(`pushState`). 그래서 (1) `st.switch_page` 는 떠나는 화면 경로로 한 칸 먼저 쌓고 옮긴 화면을 또 쌓아 뒤로가기
// 한 번이 제자리였고, (2) 링크 인자를 받아 지우는 화면(공정 Capa 상세 `?process=`·Space `?layer=`·제약 시뮬레이션)은
// 인자 달린 칸 뒤에 인자 없는 칸을 또 쌓아, 뒤로가기로 인자 달린 칸에 닿으면 화면이 그 인자를 다시 지우며 또 쌓아 —
// 앞쪽 기록이 잘려 — 그 화면을 떠나지 못했다(E2E 결함). 지금 경로와 같은 경로로 쌓는 것은 늘 그 칸 바꾸기
// (`replaceState`)로 돌린다 — 화면을 옮기는 쌓기(다른 경로)만 칸을 더한다. 처리기는 문서에 하나다(`history` 의
// `pushState` 를 한 번 감싼다).
// `st.switch_page` 의 첫 쌓기는 떠나는 칸 주소를 옮길 화면 인자로 바꾼다(HOME 칸 → `/?process=…&from=home`). 그대로
// 두면 뒤로가기로 돌아온 그 칸이 남의 인자를 달고, 거기서 사이드바로 옮기면 그 인자가 따라가 링크처럼 적용됐다. 그래서
// 인자를 지우지 않은(더하거나 바꾸기만 한) 칸 바꾸기 뒤 `ms` 안에 같은 인자로 다른 경로를 쌓으면 — 그 쌓기가
// `switch_page` 의 옮긴 화면이다 — 떠나는 칸을 원래 주소로 되돌리고 쌓는다. 인자를 지운 칸 바꾸기(링크 인자를 받아
// 지운 화면)는 되돌리지 않는다.
function guardHistory(history, href, clock, ms) {
  const push = history.pushState
  const at = (url) => new URL(String(url), href())
  let covered = null
  history.pushState = function (state, title, url) {
    if (url === undefined || url === null) return push.apply(this, arguments)
    const here = at(href())
    const next = at(url)
    if (next.pathname === here.pathname) {
      const kept = [...here.searchParams.keys()].every((name) => next.searchParams.has(name))
      covered = kept
        ? { url: here.pathname + here.search + here.hash, state: history.state, search: next.search, at: clock() }
        : null
      return history.replaceState(state, title, url)
    }
    const prior = covered
    covered = null
    if (prior !== null && clock() - prior.at < ms && next.search === prior.search) {
      history.replaceState(prior.state, '', prior.url)
    }
    return push.apply(this, arguments)
  }
  return history
}
// </tabs-history>

// <tabs-history-install>
// 기록 지킴이는 문서에 하나다 — 먼저 도는 쪽이 걸고 다른 쪽은 지나간다. 입장 화면 JS(`intro_overlay`)가 모듈을 읽는
// 순간 이 구획을 부른다 — 회차 맨 앞(부트스트랩 전)에 그리는 요소라 링크 인자를 받는 화면이 첫 회차에 인자를 지우기
// 전이다. 탭 줄은 페이지 바로 앞에 그려 그 지우기보다 늦게 마운트돼, 새 브라우저 탭으로 연 링크가 지킴이 없이 기록을 한
// 칸 더 쌓았다(E2E 결함 — 뒤로가기 첫 번이 화면은 그대로 둔 채 주소의 인자만 되살렸다). 탭 줄도 부른다(안전망).
// `st.switch_page` 가 떠나는 칸에 적은 옮길 화면 인자를 되돌리는 기다림 — 그 바로 뒤 옮긴 화면 쌓기가 이 안에 온다.
const LEAVE_MS = 1000
function installHistoryGuard() {
  if (!window.__capaHistoryGuard) {
    window.__capaHistoryGuard = guardHistory(window.history, () => window.location.href, Date.now, LEAVE_MS)
  }
}
// </tabs-history-install>

// <tabs-hold>
// 편집표에서 막 손을 뗀 누름을 붙든다. `editPending` — 누르는 순간 포커스가 편집표(칸 편집기 포함)에 있었거나 마지막 편집표
// 입력에서 `ms` 가 지나지 않았다. `holdVerdict` 는 붙든 누름({at, data, path})을 'wait'(더 기다린다)·'go'(지금 data 로
// 묻고 보낸다)·'drop'(버린다)으로 가른다 — 앱 회차가 돌면 기다리고, 돌지 않아도 새 data 가 오지 않았으면 `minMs` 까지는
// 기다린다(편집 회차 요청이 아직 서버에 닿지 않았을 수 있다). `maxMs` 가 지나면 그대로 보낸다. 누른 뒤 주소(`path`)가
// 바뀌었으면 사용자가 다른 길로 옮긴 것이다(뒤로가기·본문 단추 이동은 붙듦을 비우지 않는다) — 다시 보내면 그 화면을 덮는다.
function editPending(now, editAt, focused, ms) {
  return Boolean(focused) || now - editAt < ms
}
function holdVerdict(hold, now, running, data, minMs, maxMs, path) {
  if (hold.path !== path) return 'drop'
  const elapsed = now - hold.at
  if (elapsed >= maxMs) return 'go'
  if (running) return 'wait'
  if (elapsed < minMs && data === hold.data) return 'wait'
  return 'go'
}
// </tabs-hold>

// <tabs-grid>
// 붙들기가 편집표로 보는 자리의 선택자 — glide 격자와 칸 편집기 틀(`base`)에 data 의 Components v2 편집 칸 key
// (`keys` — 파이썬 `page_tabs.EDIT_HOST_KEYS`, 가용설비 현황 설비 마스터 표·오른쪽 칸)를 바깥 key 칸(`.st-key-<key>`)으로
// 더한다. 그 칸은 그림자 DOM 이라 문서 capture 단계에서 보면 칸 편집기의 focusin·keydown 대상이 그림자 호스트로 바뀐다 —
// 안쪽 클래스로는 맞지 않는다. 더하지 않으면 설비 마스터 칸에 쓰는 중(Enter 전)에 누른 테마 단추를 붙들지 않아, 누름이 그
// 편집을 실은 회차보다 짧으면(마우스 누름 70ms 이하·터치 톡) 저장 안 함 표지가 서기 전이라 확인 없이 새로 읽어 친 글이
// 사라졌다(E2E 결함 — 칸 편집기는 초점이 표 밖으로 나가는 순간 곧바로 보낸다). key 꼴이 아닌 값은 버린다.
function gridSelector(base, keys) {
  const hosts = (Array.isArray(keys) ? keys : []).filter((key) => typeof key === 'string' && /^[\w-]+$/.test(key))
  return [base, ...hosts.map((key) => '.st-key-' + key)].join(', ')
}
// </tabs-grid>

// <tabs-queue>
// 옮기는 동안 누른 탭은 보내지 않고 기다린다 — 마지막 누름 하나만. 보낸 고르기는 옮긴 화면의 탭 줄(지금 탭이 바뀐
// data)이 오고 **그 화면 회차가 다 돌았거나**(`busy` 거짓) **탭 줄이 온 뒤 `graceMs` 가 지나면** 끝난다(아니면 `ms`).
// 탭 줄이 오기 전에 보낸 누름은 프런트가 아직 떠나는 화면에 있다고 믿고 그 화면 주소로 회차를 청한다. 탭 줄이 온 즉시
// 보낸 누름은 0.1~0.2초 간격 두 누름에서 사라졌는데, 그 까닭은 부품 그리기 **안**에서 트리거를 보낸 것이었다(부르는
// 쪽이 그리기 밖으로 미룬다 — 함수 끝). `graceMs` 는 그 위의 여유다. 회차 끝까지만 기다리면 옮긴 화면이 오래 돌 때(HOME
// 첫 계산) 누른 탭이 그 계산과 브라우저 그리기가 끝날 때까지 묶였다(사내 리뷰 202610271800 발견 3 — HOME 로딩 끝 + 약
// 2초). 서버는 회차가 도는 중에 온 누름도 곧바로 새 회차로 받는다(`runner.fastReruns` — 돌던 회차는 다음 메시지·세션 칸
// 자리에서 멈춘다). `press` 는 'send'(지금 보낸다)·'wait'(기다린다)·'none'(지금 탭이라 할 일 없음)을 돌려주고, 'send'
// 면 부르는 쪽이 보내기 전에 `sent` 를 부른다(떠나기 확인을 취소하면 부르지 않는다). `settle` 은 끝났으면 기다리던 누름의
// id(열린 탭이고 지금 탭이 아닐 때만)를, 아니면 null 을 돌려준다. 지금 탭 닫기(옮겨 갈 이웃은 서버가 정한다)도
// `sent(queue, null, …)` 로 같은 기다림을 건다.
function createSelectQueue() {
  return { flight: null, waiting: null }
}
function pressSelect(queue, id, active, now, ms) {
  if (queue.flight !== null && now - queue.flight.at < ms) {
    queue.waiting = id
    return 'wait'
  }
  queue.flight = null
  queue.waiting = null
  return id === active ? 'none' : 'send'
}
function sentSelect(queue, id, active, now) {
  queue.flight = { id, from: active, at: now, arrived: null }
  queue.waiting = null
}
function settleSelect(queue, active, now, ms, ids, busy, graceMs) {
  const flight = queue.flight
  if (flight === null) return null
  // 옮긴 화면의 탭 줄을 처음 본 때. 그 뒤로 지금 탭이 다시 바뀌어도 그대로 둔다.
  if (active !== flight.from && flight.arrived === null) flight.arrived = now
  const moved = flight.arrived !== null && (!busy || now - flight.arrived >= graceMs)
  if (!moved && now - flight.at < ms) return null
  queue.flight = null
  const next = queue.waiting
  queue.waiting = null
  if (next === null || next === active || !ids.includes(next)) return null
  return next
}
// </tabs-queue>

// <tabs-press>
// 닫기·고정 누름은 곧 목록을 바꾼다 — 닫은 탭은 누르자마자 숨겨 이웃이 그 자리로 당겨 오고, 고정한 탭은 다음 data 에서
// 왼쪽으로 옮긴다. 그래서 × 더블클릭(·0.3초 간격 두 번 누름)의 둘째 누름이 포인터 아래로 밀려 온 이웃 탭에 닿아 그 탭을
// 닫거나 고정했다 — 같은 프레임의 두 'close' 는 마지막 것만 서버에 닿아 누른 탭은 남고 이웃이 닫혔다(E2E 결함).
// `strayPress` 는 앞 닫기·고정 누름(`last` — {id, at, x, y})에서 `ms` 안에 `px` 안의 같은 자리로 온 누름이 **다른 탭**에
// 닿았는가다 — 참이면 그 누름은 버린다. 같은 탭의 둘째 누름(핀 두 번 — 고정했다 푼다)과 자리를 옮긴 누름은 그대로다.
function strayPress(last, id, now, x, y, ms, px) {
  if (last === null || id === last.id || now - last.at >= ms) return false
  return Math.abs(x - last.x) <= px && Math.abs(y - last.y) <= px
}
// </tabs-press>

// <tabs-order>
// 고정·끌기·닫기는 누르자마자 탭 줄을 고쳐 그린다 — 서버(`page_tabs_state`)와 **같은 규칙**으로. 그래서 서버는 페이지를 다시
// 돌리지 않고 목록만 받는다(2026-11-02 사용자 요청 — 핀 고정에 페이지 로딩이 떴다). `ids` 는 보이는 차례, `pinned` 는 그 가운데
// 고정한 탭이다. 돌려주는 `{ids, pinned}` 는 고정 탭을 왼쪽에 모은 차례다(`normalized`). `pinnedOrder` 는 `pinned_to` 와 같다 —
// 고정하면 고정 묶음의 끝, 풀면 나머지 묶음의 앞. `movedOrder` 는 `moved` 와 같다 — 고정하지 않은 탭을 `before` 앞(없거나
// 모르면 끝)으로, 고정 탭·없는 탭은 그대로. `closableIds` 는 `TabStrip.closable` 이다(고정 탭·마지막 하나는 닫지 않는다).
// `keyboardMove` 는 `Ctrl+Shift+←/→` 한 칸 — 고정 묶음을 넘지 않고, 옮길 수 없으면 null, 옮기면 `{before}`. `mergedOrder` 는
// `arranged` 와 같다 — 그린 차례(`want`)를 목록 `ids` 에 입힌다(모르는 탭은 버리고, `want` 에 없는 탭은 원래 차례로 뒤에, 고정은
// `pinned` 그대로).
function normalizedOrder(ids, marks) {
  const seen = []
  for (const id of ids) if (!seen.includes(id)) seen.push(id)
  const pinned = seen.filter((id) => marks.includes(id))
  return { ids: [...pinned, ...seen.filter((id) => !marks.includes(id))], pinned }
}
function pinnedOrder(ids, pinned, id, pin) {
  if (!ids.includes(id)) return normalizedOrder(ids, pinned)
  const marks = pinned.filter((other) => other !== id)
  return normalizedOrder(ids, pin ? [...marks, id] : marks)
}
function movedOrder(ids, pinned, id, before) {
  if (!ids.includes(id) || pinned.includes(id) || id === before) return normalizedOrder(ids, pinned)
  const rest = ids.filter((other) => other !== id)
  const at = before !== null && rest.includes(before) ? rest.indexOf(before) : rest.length
  rest.splice(at, 0, id)
  return normalizedOrder(rest, pinned)
}
function closableIds(ids, pinned) {
  return ids.length > 1 ? ids.filter((id) => !pinned.includes(id)) : []
}
function mergedOrder(ids, pinned, want) {
  const head = []
  for (const id of want) if (ids.includes(id) && !head.includes(id)) head.push(id)
  return normalizedOrder([...head, ...ids.filter((id) => !head.includes(id))], pinned)
}
function keyboardMove(ids, pinned, id, step) {
  const at = ids.indexOf(id)
  if (at < 0 || pinned.includes(id)) return null
  const to = at + step
  if (to < ids.filter((other) => pinned.includes(other)).length || to >= ids.length) return null
  const rest = ids.filter((other) => other !== id)
  return { before: to < rest.length ? rest[to] : null }
}
// </tabs-order>

// <tabs-batch>
// 차례 바꾸기 묶음(2026-11-03 사용자 검수 — 「몇 번 연속으로 좌우로 움직이는 경우 불필요한 로딩이 발생하거나 멈추는 경우」).
// 누를 때마다 보내면 누름마다 앱 전체 회차가 서고(콜백이 빈 프래그먼트로 바꾸기 전의 틈 — 그동안 프런트가 본문 전체를 흐림
// 표지로 둔다) 회차 끝 GC 가 두 번 돌아 서버가 누름을 따라가지 못했다(사본 50ms 간격 20번 — 회차 표지 1.4초, 끝난 뒤에도 1.3초
// 더 돌았다). 페이지가 도는 중의 누름은 그 회차를 끊고 앱 전체를 다시 돌렸다(HOME 진행 막대 2.7초). 그래서 그림은 곧바로 고치고
// 서버에는 마지막 그림만 한 번 보낸다. `due` 는 그렸지만 보내지 않은 그림({ids, pinned, at}), `sent` 는 보냈지만 data 가 아직
// 따라오지 않은 그림(`seq` — 서버가 받은 마지막 번호를 data 가 싣는다), `seq` 는 붙인 마지막 번호다. 서버가 아는 차례
// (`knownOrder` — 따라오지 않은 `sent`, 없으면 data)와 같으면 보내지 않는다(왼쪽 갔다 되돌아옴).
function createMoveBatch() {
  return { due: null, sent: null, seq: 0 }
}
function sameOrder(a, b) {
  return a != null && b != null && a.ids.join('\n') === b.ids.join('\n') && a.pinned.join('\n') === b.pinned.join('\n')
}
// 옮긴 그림을 담는다 — 쉼을 처음부터 다시 잰다.
function dueMove(batch, plan, now) {
  batch.due = { ids: plan.ids.slice(), pinned: plan.pinned.slice(), at: now }
}
function knownOrder(batch, data) {
  return batch.sent || data
}
// 담긴 그림을 어떻게 할까 — 'idle'(없음) · 'wait'(쉼 안, 또는 앱이 돈다 — 길어야 `maxMs`) · 'drop'(지금 그림 `drawn` 을 서버가 이미
// 안다) · 'send'.
function moveVerdict(batch, drawn, known, now, quietMs, busy, maxMs) {
  const due = batch.due
  if (due === null) return 'idle'
  const age = now - due.at
  if (age < quietMs || (busy && age < maxMs)) return 'wait'
  return sameOrder(drawn, known) ? 'drop' : 'send'
}
// 지금 그림을 보낸다(차례 묶음이든, 고정·닫기·고르기가 함께 싣는 그림이든) — 번호를 붙이고 담긴 그림을 비운다.
function claimOrder(batch, plan, now) {
  batch.seq += 1
  batch.sent = { ids: plan.ids.slice(), pinned: plan.pinned.slice(), seq: batch.seq, at: now }
  batch.due = null
  return batch.seq
}
// 새 data 가 왔다 — 서버가 받은 번호 `seq`. 보낸 그림을 서버가 받았으면 놓고, 받은 흔적 없이 `lostMs` 가 지났으면 곧 보내게
// 다시 담는다. 번호는 data 의 것 아래로 붙이지 않는다(같은 세션을 다시 잇는 문서).
function dataArrived(batch, seq, now, lostMs) {
  batch.seq = Math.max(batch.seq, seq)
  if (batch.sent !== null && seq >= batch.sent.seq) batch.sent = null
  if (batch.sent !== null && now - batch.sent.at >= lostMs) {
    if (batch.due === null) batch.due = { ids: batch.sent.ids, pinned: batch.sent.pinned, at: -Infinity }
    batch.sent = null
  }
}
// 서버 차례 `data`({ids, pinned}) 대신 보일 그림 — 담긴 그림, 없으면 보낸 그림의 차례를 data 목록에 입힌 것(`mergedOrder`),
// 둘 다 없으면 data 그대로.
function shownOrder(batch, data) {
  const want = batch.due || batch.sent
  return want === null ? data : mergedOrder(data.ids, data.pinned, want.ids)
}
// </tabs-batch>

// <tabs-drag>
// 고정하지 않은 탭을 끌어 차례를 바꾼다(2026-11-02 사용자 요청). HTML5 끌어 놓기가 아니라 포인터 이벤트다 — 가로로 넘치는
// 그림자 DOM 목록 안에서 축을 묶고, 고정 묶음 앞에서 멈추고, 끈 뒤의 누름을 버리고, 터치 길게 누르기를 직접 다룬다.
// `dragStarts` — 마우스·펜은 가로로 `slop` 를 넘게 움직이면 끌기다(그 전의 누름은 고르기·고정·× 그대로). 세로만 움직이면
// 끌지 않는다(세로로 끌어 떼어 내기는 떠 있는 창 몫으로 남긴다). 터치는 `holdMs` 길게 누른 뒤에야 끌기이고, 그 전에 움직이면
// 목록 굴리기라 그만둔다('cancel'). `dragLeft` — 포인터가 바라는 끄는 탭의 왼쪽(`want`)을 고정 묶음 뒤(`low`)와 목록
// 끝(`high`) 사이로 묶고 어느 끝에 닿았는지(`bound` — 'low'·'high'·null)를 함께 준다. `dropSlot` — 끝에 닿았으면 그 끝 자리
// (고정 묶음 바로 뒤·맨 끝)이고, 아니면 끄는 탭의 가운데(`x`)가 지난 다른 탭 가운데(`mids`, 보이는 차례) 수다. 고정 탭 수
// (`min`) 아래로 내려가지 않는다(고정 묶음 앞으로 못 간다). 가운데만 보면 끄는 탭이 이웃보다 넓거나 같을 때 끝 자리에 못
// 놓였다 — 넘친 줄은 탭이 같은 폭으로 줄어 맨 끝에 놓을 수 없었고(끝에서 둘째에 멈춤), 넘치지 않아도 긴 이름 탭을 짧은
// 이름 탭 앞(고정 묶음 바로 뒤)에 놓을 수 없었다(2026-11-02 반박 검토). `edgeSpeed` — 목록 가장자리 `edge` 안에서 끄는
// 동안 굴릴 한 프레임 px(왼쪽은 음수). `dragClick` — 끌기가 끝난 뒤 `ms` 안의 누름은 고르기로 보내지 않는다(끈 탭을 놓은
// 자리의 click). `heldRelease` — Esc·새 data 로 접은 끌기는 포인터가 아직 눌려 있다(`held` — 그 포인터 id, 없으면 null).
// 그 포인터를 놓는 순간(`pointerup`)부터 `dragClick` 창을 다시 연다 — 접은 시각부터만 세면 손을 떼기 전 작은 움직임 뒤
// 0.4초 넘어 놓은 click 이 고르기로 가 화면을 옮겼다(2026-11-02 반박 검토). 같은 포인터의 새 누름(놓음을 놓쳤다)·포인터
// 취소(click 이 없다)는 기다림만 거둔다. 돌려주는 `{held, endedAt}` 의 `endedAt` 은 새 창의 시작(없으면 null)이다.
function dragStarts(kind, dx, dy, held, slop, holdMs) {
  if (kind === 'touch') {
    if (held >= holdMs) return 'drag'
    return Math.hypot(dx, dy) > slop ? 'cancel' : 'wait'
  }
  return Math.abs(dx) > slop ? 'drag' : 'wait'
}
function dragLeft(want, low, high) {
  if (want <= low) return { left: low, bound: 'low' }
  if (want >= high) return { left: high, bound: 'high' }
  return { left: want, bound: null }
}
function dropSlot(mids, x, min, bound) {
  if (bound === 'low') return min
  if (bound === 'high') return Math.max(min, mids.length)
  let slot = 0
  while (slot < mids.length && mids[slot] < x) slot += 1
  return Math.max(min, slot)
}
function heldRelease(held, type, pointer, now) {
  if (held === null || pointer !== held) return { held, endedAt: null }
  return { held: null, endedAt: type === 'pointerup' ? now : null }
}
function edgeSpeed(x, left, right, edge, max) {
  if (x < left + edge) return -Math.ceil(max * Math.min(1, (left + edge - x) / edge))
  if (x > right - edge) return Math.ceil(max * Math.min(1, (x - right + edge) / edge))
  return 0
}
function dragClick(endedAt, now, ms) {
  return endedAt !== null && now - endedAt < ms
}
// </tabs-drag>
// <tabs-links>
// 상한에서 화면 링크 누름을 거른다. `open` 은 열린 탭 주소(닫는 중이라 숨긴 탭은 뺀다), `max` 는 상한, `pages` 는 아는
// 화면 주소 → 이름이다. 앞서 지나 보낸 링크 누름(`flight` — {href, at, epoch})의 화면은 그 누름이 연 탭이 아직 탭 줄 data
// 에 오지 않았으면(같은 `epoch` — 탭 목록이 바뀌면 서버가 epoch 를 올린다) `ms` 동안 열린 탭으로 센다(`linkOpening`).
// 세지 않으면 탭 9개에서 사이드바 링크 둘을 0.05~0.1초 간격으로 누를 때 둘째 누름이 앞 회차 data 의 탭 9개로 세어 거름을
// 지났고, 서버 되돌림(`switch_to_queued_tab`)이 두 화면을 기록에 쌓아 뒤로가기가 그 화면에 갇혔다(E2E 결함).
// `linkVerdict` 는 'refuse'(막고 알린다)·'open'(새 탭을 여는 누름 — 부르는 쪽이 `flight` 로 적는다)·'pass'(열린 탭·그
// 누름이 여는 탭·모르는 주소)를 돌려준다.
function linkOpening(flight, epoch, now, ms) {
  if (flight === null || flight.epoch !== epoch || now - flight.at >= ms) return null
  return flight.href
}
function linkVerdict(pages, open, max, href, opening) {
  if (!Object.prototype.hasOwnProperty.call(pages, href)) return 'pass'
  if (open.includes(href) || href === opening) return 'pass'
  const count = open.length + (opening !== null && !open.includes(opening) ? 1 : 0)
  return count >= Number(max) ? 'refuse' : 'open'
}
// </tabs-links>

// <tabs-edges>
// 가로로 넘친 목록의 어느 쪽에 탭이 더 있는가 — {start, end}. 넘치지 않으면 둘 다 거짓이다. 굴린 위치는 소수 px 일 수
// 있어 1px 안쪽은 끝으로 본다.
function overflowEdges(scrollLeft, scrollWidth, clientWidth) {
  const max = scrollWidth - clientWidth
  if (!(max > 1)) return { start: false, end: false }
  return { start: scrollLeft > 1, end: scrollLeft < max - 1 }
}
// 지금 탭(목록 안 `left`~`right`)이 가장자리 흐림(`edge`) 밖에 온전히 보이게 할 목록의 굴린 위치. 이미 보이면 지금
// 위치 그대로다 — 탭을 옮길 때와 목록 폭이 바뀔 때(사이드바 접기·펴기, 창 폭) 같은 계산을 쓴다.
function revealScroll(left, right, scrollLeft, clientWidth, edge) {
  if (left < scrollLeft + edge) return Math.max(0, left - edge)
  if (right > scrollLeft + clientWidth - edge) return right - clientWidth + edge
  return scrollLeft
}
// </tabs-edges>

// <tabs-wip>
// 탭 이름이 말줄임됐는가(`scrollWidth` > `clientWidth`). 소수 px 반올림은 넘침으로 보지 않는다 — 「구현중」 표지를 점으로 줄일지 가른다.
function wipTight(scrollWidth, clientWidth) {
  return scrollWidth - clientWidth > 0.5
}
// </tabs-wip>

// <tabs-focus>
// 초점이 있던 탭을 닫을 때 초점을 옮길 탭 — 서버가 지금 탭을 닫고 옮겨 가는 이웃과 같은 규칙(오른쪽 이웃, 없으면 왼쪽
// 이웃 — `page_tabs_state.closed`)이다. `ids` 는 닫기 전 보이는 탭 차례다. 닫는 탭이 없거나 남는 탭이 없으면 null.
function focusAfterClose(ids, closing) {
  const index = ids.indexOf(closing)
  if (index < 0) return null
  const rest = ids.filter((id) => id !== closing)
  if (rest.length === 0) return null
  return rest[Math.min(index, rest.length - 1)]
}
// 키보드로 옮긴 화면이 다 선 뒤 초점을 지금 탭에 돌려줄까 — 'focus'(돌려준다)·'wait'(다시 본다)·'drop'(그만둔다).
// 키보드 누름(`pressAt`)이 있었고 그 뒤 다른 입력(`inputAt` — 키·포인터)이 없을 때만 보고, 사용자가 이미 다른 자리로 옮긴
// 초점은 두지 않는다. 옮긴 화면 회차가 아직 돌면(`running`) 키보드 누름에서 `ms` 까지 기다린다 — 기다리던 누름은 그 회차가
// 끝나기 전에도 보내지만(`<tabs-queue>` 의 `graceMs`), 초점은 화면이 다 서야 제자리가 정해진다. 그 뒤 초점이 body 로
// 빠졌으면(`lost`) 돌려준다.
function refocusAfterMove(pressAt, inputAt, lost, running, now, ms) {
  if (pressAt === null || inputAt > pressAt) return 'drop'
  if (running && now - pressAt < ms) return 'wait'
  return lost ? 'focus' : 'drop'
}
// </tabs-focus>

// <tabs-return>
// 새로 읽은 문서의 「설비 시나리오가 공식으로 돌아왔습니다」. `returnMark` 는 띠 CSS 변수 값(따옴표 친 퍼센트 인코딩 글,
// 알릴 것이 없으면 `none`)을 이름 글로 푼다 — 못 읽으면 빈 글. `returnRecord` 는 문서를 떠날 때 적을 값이다 — 떠나는 까닭에
// 맞는 변수(테마 단추면 `theme` — 공식 발행 쌍이 아니던 모든 세션, 새로고침이면 `reload` — 가정 설비 시나리오였던 세션만)에
// 이름이 있으면 `{label, cause}`(테마 단추면 'theme', 아니면 'reload'), 없으면 null(적어 둔 것을 그대로 둔다 — 알리기 전에
// 떠난 문서의 몫을 지우지 않는다). `returnNotice` 는 적어 둔 값으로 알릴 글을 짓는다(`text.themed`·`text.returned` 의
// `{label}`).
function returnMark(raw) {
  const match = /^\s*(["'])(.*)\1\s*$/.exec(String(raw || ''))
  if (!match) return ''
  try {
    return decodeURIComponent(match[2])
  } catch (error) {
    return ''
  }
}
function returnRecord(theme, reload, themed) {
  const label = returnMark(themed ? theme : reload)
  return label ? JSON.stringify({ label, cause: themed ? 'theme' : 'reload' }) : null
}
function returnNotice(stored, text) {
  const record = returnParts(stored)
  if (record === null) return ''
  const template = String((record.cause === 'theme' ? text.themed : text.returned) || '')
  return template ? template.split('{label}').join(record.label) : ''
}
// 적어 둔 값의 {label, cause} — 못 읽으면 null. 알림 칸에 낼 때 까닭(테마 단추 · 새로고침)으로 코드와 짧은 글을 가른다.
function returnParts(stored) {
  let record = null
  try {
    record = JSON.parse(stored || 'null')
  } catch (error) {
    return null
  }
  if (!record || typeof record.label !== 'string' || !record.label) return null
  return { label: record.label, cause: record.cause === 'theme' ? 'theme' : 'reload' }
}
// </tabs-return>

// <tabs-unload>
// 새로고침·브라우저 탭 닫기·주소 바꾸기(문서를 떠남)에 브라우저 확인 창을 띄운다(개선 거리 I3). 새 문서는 새 Streamlit 세션이라
// 적용·저장하지 않은 편집이 말없이 사라졌다(E2E #101·#119 — 테마 단추는 묻는데 새로고침은 묻지 않았다). 묻는 표지는 테마 단추가
// 읽는 것과 같은 CSS 변수다(`UNSAVED_VARIABLE` — 파이썬 `theme_toggle.UNSAVED_EDITS_CSS_VARIABLE`, 값은 탭 점과 한 벌의 판정
// `unsaved_edits_marker`). 그 값이 '1' 일 때만 묻고 편집이 없으면 묻지 않는다. 앱이 스스로 새로 읽는 중이면 묻지 않는다 — 테마
// 단추는 제 확인 창으로 이미 물었고(`RELOAD_ASKED` — 파이썬 `theme_toggle.RELOAD_ASKED_FLAG`), 열릴 때 테마 키를 맞추는
// 새로고침(`__capaThemeReloading`)은 편집이 생기기 전이다. 앱 안의 화면 이동(탭·사이드바 링크)은 문서를 떠나지 않아 이 길이
// 아니다. 확인 창의 글은 브라우저가 정한다(사이트 글을 싣지 못한다). 표지는 떠나는 순간 읽는다 — 처리기는 문서에 하나다.
const UNSAVED_VARIABLE = '--capa-unsaved-edits'
const RELOAD_ASKED = '__capaReloadAsked'
function unloadAsks(unsaved, reloading) {
  return String(unsaved || '').trim() === '1' && !reloading
}
function installUnloadGuard(win, doc) {
  if (win.__capaUnloadGuard) return
  win.__capaUnloadGuard = true
  win.addEventListener('beforeunload', (event) => {
    let unsaved = ''
    try {
      unsaved = win.getComputedStyle(doc.documentElement).getPropertyValue(UNSAVED_VARIABLE)
    } catch (error) {
      return
    }
    if (!unloadAsks(unsaved, Boolean(win[RELOAD_ASKED] || win.__capaThemeReloading))) return
    event.preventDefault()
    // 옛 꼴의 브라우저는 `returnValue` 를 적어야 묻는다.
    event.returnValue = ''
  })
}
// </tabs-unload>
const SVG_NS = 'http://www.w3.org/2000/svg'
const CLOSE_PATH = 'M4 4 L12 12 M12 4 L4 12'
const PIN_PATH = 'M6 2 H10 L9.5 6 L12 8.5 V10 H8.75 V14.5 L8 15 L7.25 14.5 V10 H4 V8.5 L6.5 6 Z'

function icon(path, fillClass) {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 16 16')
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('focusable', 'false')
  const shape = document.createElementNS(SVG_NS, 'path')
  shape.setAttribute('d', path)
  shape.setAttribute('stroke', 'currentColor')
  shape.setAttribute('stroke-width', '1.5')
  shape.setAttribute('stroke-linecap', 'round')
  shape.setAttribute('stroke-linejoin', 'round')
  if (fillClass) shape.setAttribute('class', fillClass)
  else shape.setAttribute('fill', 'none')
  svg.append(shape)
  return svg
}

function fill(template, values) {
  return String(template || '').replace(/\{(\w+)\}/g, (_, name) => (name in values ? String(values[name]) : ''))
}

// 알림창 짧은 글 — 줄바꿈을 한 칸으로 접고 넘치면 말줄임(파이썬 `alerts.short_text` 와 같다).
function shortText(value) {
  const flat = String(value || '').split(/\s+/).filter(Boolean).join(' ')
  return flat.length <= SHORT_LIMIT ? flat : flat.slice(0, SHORT_LIMIT - 1).trimEnd() + '…'
}

// 화면 링크 `href` 의 주소(`url_path` — HOME 은 빈 글자). 앞 `/`·조회 인자·조각을 뗀다.
function linkPath(href) {
  let path = String(href || '').split(/[?#]/)[0]
  try {
    if (/^[a-z]+:/i.test(path)) path = new URL(path).pathname
  } catch (error) {
    return path
  }
  return path.replace(/^\/+/, '').split('/').pop() || ''
}

// 공용 공정 표지 — 풍선(`title`)을 다는 칸 안에 24 단위 깔때기를 칠한다(탭 줄의 다른 아이콘은 16 단위 선이다). 읽기
// 도구에는 숨은 글(`capa-tabs-sr`)로 풍선 글을 읽힌다 — 탭 단추 이름에 붙는다.
function funnelMark() {
  const mark = document.createElement('span')
  mark.className = 'capa-tabs-proc'
  mark.hidden = true
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('focusable', 'false')
  const shape = document.createElementNS(SVG_NS, 'path')
  shape.setAttribute('d', FUNNEL_PATH)
  svg.append(shape)
  const said = document.createElement('span')
  said.className = 'capa-tabs-sr'
  mark.append(svg, said)
  return mark
}

// 탭 이름 곁 공용 공정 표지 — `proc`({miss, title})가 없으면 숨기고, 그 화면에 없는 공용 공정이 있으면 주황이다.
function paintProcessMark(item, proc) {
  const mark = item.__parts.proc
  const shown = Boolean(proc) && typeof proc === 'object'
  mark.hidden = !shown
  item.classList.toggle('is-proc-miss', shown && Boolean(proc.miss))
  const title = shown ? String(proc.title || '') : null
  setAttr(mark, 'title', title)
  setText(mark.lastChild, title ? ` ${title}` : '')
}

// 「구현중」 표지 맞추기 — 탭이 좁아 이름이 말줄임되면 글 표지를 점으로 줄인다(`is-wip-tight` — 풍선 · 읽기 도구 글은 남는다,
// UI-ACC-02). 늘 글 표지로 되돌린 뒤 한 번에 재고 정한다 — 점으로 줄여 넓어진 자리로 다시 재면 넓히고 줄이기를 오락가락한다. 재기를
// 모두 마친 뒤 쓰므로 그리기 계산은 한 번이다.
function fitWip(items) {
  const marked = []
  for (const item of items) {
    item.classList.remove('is-wip-tight')
    if (!item.hidden && item.classList.contains('is-wip')) marked.push(item)
  }
  const tight = marked.filter((item) => wipTight(item.__parts.label.scrollWidth, item.__parts.label.clientWidth))
  for (const item of tight) item.classList.add('is-wip-tight')
}

function setAttr(element, name, value) {
  if (value === null || value === undefined) {
    if (element.hasAttribute(name)) element.removeAttribute(name)
  } else if (element.getAttribute(name) !== value) {
    element.setAttribute(name, value)
  }
}

function setText(element, value) {
  if (element.textContent !== value) element.textContent = value
}

function iconFontLoaded() {
  try {
    for (const face of document.fonts) {
      if (face.family.replace(/["']/g, '') === ICON_FONT && face.status === 'loaded') return true
    }
  } catch (error) {
    return false
  }
  return false
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const nav = parentElement.querySelector('.capa-tabs')
  if (!nav || !data) return
  const list = nav.querySelector('.capa-tabs-list')
  const drop = nav.querySelector('.capa-tabs-drop')
  const announcer = nav.querySelector('.capa-tabs-announce')
  const S = nav.__capaTabs || (nav.__capaTabs = {
    items: new Map(), noticeId: null, busyTimer: 0, lastActive: null, onFonts: null, onOpenPage: null,
    onLink: null, linkFlight: null, linkReplay: null, queue: createSelectQueue(), settleTimer: 0, lastPress: null,
    onEdit: null, editAt: -Infinity, gridFocused: false, pressFromGrid: false, hold: null, holdTimer: 0, gridSelector: GRID,
    onScroll: null, resizer: null, reveal: null, onInput: null, inputAt: -Infinity, keyPressAt: null, focusTimer: 0,
    drag: null, endDrag: null, dragEndAt: null, onTouchMove: null, heldPointer: null, onRelease: null,
    moves: createMoveBatch(), moveTimer: 0, dataOrder: null, dataSeen: null,
  })
  // 끄는 중에 새 data 가 왔다(다른 회차가 목록을 바꿨다) — 끌기를 접고 새 data 대로 그린다. 놓은 자리를 보내지 않는다. 포인터는
  // 아직 눌려 있다 — 놓을 때의 click 도 고르기가 아니다(`heldRelease`).
  if (S.drag && S.endDrag) S.endDrag(false, true)
  // 기록 지킴이는 문서에 하나다 — 탭 줄이 다시 마운트돼도 `pushState` 를 두 번 감싸지 않는다. 보통은 입장 화면 JS 가
  // 이미 걸었다(`<tabs-history-install>`). 이것은 그 JS 가 서지 못한 문서의 안전망이다.
  installHistoryGuard()
  // 처리기는 처음 한 번 단다. 지금 data·트리거 함수는 S 에서 읽는다 — 다시 불릴 때마다 새 값으로 바뀐다.
  S.data = data
  S.send = setTriggerValue
  S.gridSelector = gridSelector(GRID, data.grids)
  const text = data.text || {}

  setAttr(nav, 'aria-label', text.nav || '')
  const pending = (data.palette && data.palette.pending) || ''
  if (pending && nav.style.getPropertyValue('--capa-tabs-pending') !== pending) {
    nav.style.setProperty('--capa-tabs-pending', pending)
  }

  // 사이드바와 같은 Material 아이콘. 글꼴이 아직 없으면 아이콘을 빼고 글만 둔다(글꼴 이름 글자가 보이지 않게).
  nav.classList.toggle('has-icons', iconFontLoaded())
  if (!S.onFonts && document.fonts && document.fonts.addEventListener) {
    S.onFonts = () => {
      nav.classList.toggle('has-icons', iconFontLoaded())
      fitWip(S.items.values())
      if (S.onScroll) S.onScroll()
    }
    document.fonts.addEventListener('loadingdone', S.onFonts)
  }

  const build = (id) => {
    const item = document.createElement('li')
    item.className = 'capa-tabs-item'
    item.dataset.id = id
    const tab = document.createElement('button')
    tab.type = 'button'
    tab.className = 'capa-tabs-tab'
    const glyph = document.createElement('span')
    glyph.className = 'capa-tabs-icon'
    glyph.setAttribute('aria-hidden', 'true')
    const label = document.createElement('span')
    label.className = 'capa-tabs-label'
    // 공용 공정 표지(깔때기 — 그 화면이 공용 공정을 따라간다, 없는 공정이 있으면 주황)와 「구현중」 표지(2026-11-09 보드 C1 (라)
    // · T8). 둘 다 제 풍선(`title`)이 있다 — 탭 이름 풍선보다 안쪽이라 표지를 가리키면 표지 풍선이 뜬다.
    const proc = funnelMark()
    const wip = document.createElement('span')
    wip.className = 'capa-tabs-wip'
    const dot = document.createElement('span')
    dot.className = 'capa-tabs-dot'
    dot.setAttribute('aria-hidden', 'true')
    const sr = document.createElement('span')
    sr.className = 'capa-tabs-sr'
    tab.append(glyph, label, proc, wip, dot, sr)
    const pin = document.createElement('button')
    pin.type = 'button'
    pin.className = 'capa-tabs-pin'
    pin.append(icon(PIN_PATH, 'capa-tabs-pin-fill'))
    const close = document.createElement('button')
    close.type = 'button'
    close.className = 'capa-tabs-x'
    close.append(icon(CLOSE_PATH, ''))
    item.append(tab, pin, close)
    item.__parts = { tab, glyph, label, proc, wip, dot, sr, pin, close }
    S.items.set(id, item)
    return item
  }

  const paint = (item, tab) => {
    const P = item.__parts
    const label = String(tab.label || '')
    const active = tab.id === data.active
    item.hidden = false
    item.__href = String(tab.href || '')
    setText(P.label, label)
    setText(P.glyph, String(tab.icon || ''))
    setAttr(P.tab, 'title', String(tab.title || label))
    setAttr(P.tab, 'aria-current', active ? 'page' : null)
    item.classList.toggle('is-active', active)
    item.classList.toggle('is-dirty', Boolean(tab.dirty))
    setText(P.sr, tab.dirty ? ' ' + String(text.dirty || '') : '')
    paintProcessMark(item, tab.proc)
    const wip = typeof tab.wip === 'string' ? tab.wip : ''
    item.classList.toggle('is-wip', wip !== '')
    setText(P.wip, wip ? String(text.wip || '') : '')
    setAttr(P.wip, 'title', wip || null)
    const pinned = Boolean(tab.pinned)
    item.classList.toggle('is-pinned', pinned)
    // 이름은 하나(「… 고정」)이고 고정 여부는 `aria-pressed` 만 말한다 — 이름까지 바꾸면 읽기 도구가 상태를 두 번 읽는다.
    setAttr(P.pin, 'aria-pressed', pinned ? 'true' : 'false')
    setAttr(P.pin, 'aria-label', fill(text.pin, { label }))
    setAttr(P.pin, 'title', fill(text.pin, { label }))
    // 고정하지 않은 탭만 `Ctrl+Shift+←/→` 로 차례를 바꾼다(끌기의 키보드 대안).
    setAttr(P.tab, 'aria-keyshortcuts', pinned ? null : MOVE_KEYS)
    P.close.hidden = !tab.closable
    setAttr(P.close, 'aria-label', fill(text.close, { label }))
    setAttr(P.close, 'title', fill(text.close, { label }))
  }

  const tabs = Array.isArray(data.tabs) ? data.tabs.filter((tab) => tab && typeof tab.id === 'string') : []
  const keep = new Set(tabs.map((tab) => tab.id))
  for (const [id, item] of S.items) {
    if (!keep.has(id)) {
      item.remove()
      S.items.delete(id)
    }
  }
  // 서버 차례(data)와, 그 위에 다시 입힐 아직 보내지 않았거나 data 가 따라오지 않은 차례 그림(`<tabs-batch>` — 그 그림이 서버에
  // 닿으면 서버도 같은 규칙으로 입힌다). 새 data 일 때만 번호를 맞춘다 — 같은 data 로 다시 불린 때(테마)는 그림만 다시 입힌다.
  // 처음부터 입힌 차례로 놓아 옮기던 탭의 초점이 data 차례로 한 번 밀렸다 돌아오며 빠지지 않게 한다.
  const dataOrder = {
    ids: tabs.map((tab) => tab.id),
    pinned: tabs.filter((tab) => tab.pinned).map((tab) => tab.id),
  }
  if (S.dataSeen !== data) {
    S.dataSeen = data
    S.dataOrder = dataOrder
    dataArrived(S.moves, Number.isInteger(data.seq) ? data.seq : 0, Date.now(), MOVE_LOST_MS)
  }
  const byId = new Map(tabs.map((tab) => [tab.id, tab]))
  const placed = shownOrder(S.moves, dataOrder)
  placed.ids.forEach((id, index) => {
    const item = S.items.get(id) || build(id)
    paint(item, { ...byId.get(id), pinned: placed.pinned.includes(id) })
    const at = list.children[index]
    if (at !== item) list.insertBefore(item, at || null)
  })
  fitWip(S.items.values())
  // 새 data 가 왔으면 누른 뒤 기다리던 표지를 걷는다 — 아직 보내지 않고 기다리는 누름(`<tabs-queue>`·`<tabs-hold>`)의
  // 표지는 둔다.
  for (const [id, item] of S.items) {
    const waiting = id === S.queue.waiting || (S.hold !== null && S.hold.id === id)
    setAttr(item.__parts.tab, 'aria-busy', waiting ? 'true' : null)
  }

  // 지금 탭이 늘 보이게 목록의 가로 위치만 맞춘다 — `scrollIntoView` 는 본문 세로 스크롤까지 움직일 수 있다. 탭을
  // 옮길 때와 목록 폭이 바뀔 때(아래 `ResizeObserver`) 맞춘다 — 폭만 바뀌면 굴린 위치가 그대로라 사이드바를 접었다
  // 펴거나 창을 좁히면 지금 탭이 목록 밖에 남았다(2026-10-30 E2E). data 가 다시 올 뿐이면 사람이 굴려 둔 위치를 둔다.
  S.reveal = () => {
    const item = S.items.get(S.data.active)
    if (!item || item.hidden) return
    const left = item.offsetLeft
    const next = revealScroll(left, left + item.offsetWidth, list.scrollLeft, list.clientWidth, EDGE_PX)
    if (next !== list.scrollLeft) list.scrollLeft = next
  }
  if (S.items.has(data.active) && S.lastActive !== data.active) {
    S.lastActive = data.active
    S.reveal()
  }
  // 넘친 목록의 가장자리 표지(`<tabs-edges>`) — 굴릴 때·목록 폭이 바뀔 때·data 가 바뀔 때 다시 본다.
  if (!S.onScroll) {
    S.onScroll = () => {
      const more = overflowEdges(list.scrollLeft, list.scrollWidth, list.clientWidth)
      nav.classList.toggle('has-more-start', more.start)
      nav.classList.toggle('has-more-end', more.end)
    }
    list.addEventListener('scroll', S.onScroll, { passive: true })
    if (typeof ResizeObserver === 'function') {
      S.resizer = new ResizeObserver(() => {
        fitWip(S.items.values())
        if (S.reveal) S.reveal()
        if (S.onScroll) S.onScroll()
      })
      S.resizer.observe(list)
    }
  }
  S.onScroll()

  // 보이는 탭(닫는 중이라 숨긴 탭은 뺀다)과 그 차례·고정 — 서버 목록과 견줄 그림이다(`<tabs-order>`).
  const visibleItems = () => [...list.children].filter((item) => !item.hidden && S.items.get(item.dataset.id) === item)
  const visibleIds = () => visibleItems().map((item) => item.dataset.id)
  const pinnedIds = () => visibleItems().filter((item) => item.classList.contains('is-pinned')).map((item) => item.dataset.id)
  // × 와 키보드 차례 바꾸기 표지를 서버 규칙(`closableIds`)대로 맞춘다 — 다음 data 가 올 때까지의 그림이다.
  const syncControls = () => {
    const shown = visibleItems()
    const ids = shown.map((item) => item.dataset.id)
    const closable = closableIds(ids, pinnedIds())
    for (const item of shown) {
      item.__parts.close.hidden = !closable.includes(item.dataset.id)
      setAttr(item.__parts.tab, 'aria-keyshortcuts', item.classList.contains('is-pinned') ? null : MOVE_KEYS)
    }
  }
  // 정한 차례(`{ids, pinned}`)대로 놓는다 — 자리가 다른 탭만 옮기고, 옮기며 빠진 초점은 같은 단추로 돌려준다.
  const arrange = (plan) => {
    const shadow = nav.getRootNode()
    const focused = shadow.activeElement
    let at = list.firstElementChild
    for (const id of plan.ids) {
      const item = S.items.get(id)
      if (!item) continue
      while (at && at !== item && at.hidden) at = at.nextElementSibling
      if (at === item) at = at.nextElementSibling
      else list.insertBefore(item, at)
    }
    for (const id of plan.ids) {
      const item = S.items.get(id)
      if (!item) continue
      const pinned = plan.pinned.includes(id)
      item.classList.toggle('is-pinned', pinned)
      setAttr(item.__parts.pin, 'aria-pressed', pinned ? 'true' : 'false')
    }
    syncControls()
    if (focused && focused.isConnected && shadow.activeElement !== focused) focused.focus({ preventScroll: true })
  }
  // 고정하지 않은 탭을 `before` 앞(null 이면 끝)으로 옮겨 그리고 그 그림을 묶음에 담는다(`<tabs-batch>` — 보내기는
  // `flushMove`). 차례가 그대로면 담지 않는다. 옮긴 탭이 목록 밖이면 보이게 굴리고, 읽기 도구에 몇 번째로 갔는지 알린다.
  function commitMove(item, before) {
    const id = item.dataset.id
    const ids = visibleIds()
    const plan = movedOrder(ids, pinnedIds(), id, before)
    if (plan.ids.join('\n') === ids.join('\n')) return false
    arrange(plan)
    dueMove(S.moves, plan, Date.now())
    clearTimeout(S.moveTimer)
    S.moveTimer = setTimeout(() => flushMove(), MOVE_SEND_MS)
    const left = item.offsetLeft
    const scroll = revealScroll(left, left + item.offsetWidth, list.scrollLeft, list.clientWidth, EDGE_PX)
    if (scroll !== list.scrollLeft) list.scrollLeft = scroll
    setText(announcer, fill(text.moved, { label: item.__parts.label.textContent, index: plan.ids.indexOf(id) + 1 }))
    return true
  }
  // 지금 그림(보이는 차례·고정).
  const drawnOrder = () => ({ ids: visibleIds(), pinned: pinnedIds() })
  // 쉼이 지났고 앱이 돌지 않으면 담긴 차례를 한 번 보낸다(`<tabs-batch>`). 화면을 옮기는 누름이 날아가는 중·붙든 누름·끄는
  // 중에도 기다린다 — 옮기는 동안 보낸 트리거는 프런트가 떠나는 화면 주소로 회차를 청한다(`<tabs-queue>`).
  function flushMove() {
    clearTimeout(S.moveTimer)
    const busy = appRunning() || S.queue.flight !== null || S.hold !== null || Boolean(S.drag && S.drag.on)
    const drawn = drawnOrder()
    const verdict = moveVerdict(S.moves, drawn, knownOrder(S.moves, S.dataOrder), Date.now(), MOVE_SEND_MS, busy, BUSY_MS)
    if (verdict === 'wait') {
      S.moveTimer = setTimeout(() => flushMove(), SETTLE_POLL_MS)
      return
    }
    if (verdict === 'drop') S.moves.due = null
    if (verdict !== 'send') return
    const seq = claimOrder(S.moves, drawn, Date.now())
    S.send('move', { order: drawn.ids, pins: drawn.pinned, seq, epoch: S.data.epoch })
  }
  // 고정·닫기·고르기가 싣는 지금 그림과 번호 — 담긴 차례가 있으면 그것을 데려가 따로 보내지 않는다.
  const claimDrawn = () => {
    clearTimeout(S.moveTimer)
    const drawn = drawnOrder()
    return { order: drawn.ids, pins: drawn.pinned, seq: claimOrder(S.moves, drawn, Date.now()) }
  }
  const leaveOk = () => !S.data.leave || window.confirm(fill(text.leave, { list: S.data.leave }))
  const busy = (item) => {
    setAttr(item.__parts.tab, 'aria-busy', 'true')
    clearTimeout(S.busyTimer)
    S.busyTimer = setTimeout(() => setAttr(item.__parts.tab, 'aria-busy', null), BUSY_MS)
  }
  // 화면을 옮기는 누름을 보내기 직전 — 한 번에 하나(`<tabs-queue>`)를 건다. 기록 한 칸은 늘 걸린 지킴이가 맡는다.
  const moving = (id) => {
    sentSelect(S.queue, id, S.data.active, Date.now())
    clearTimeout(S.settleTimer)
    S.settleTimer = setTimeout(() => settle(), SETTLE_POLL_MS)
  }
  const sendSelect = (item) => {
    // 지금 화면에 적용하지 않은 편집표 편집이 있으면 묻는다 — 화면을 떠나면 Streamlit 이 그 편집을 버린다.
    if (!leaveOk()) return
    busy(item)
    moving(item.dataset.id)
    const carried = S.moves.due !== null ? claimDrawn() : {}
    S.send('select', { id: item.dataset.id, epoch: S.data.epoch, ...carried })
  }
  // 보낸 이동이 끝났으면(옮긴 화면의 data 가 왔고 그 회차가 다 돌았거나 잠깐 지났다, 아니면 기다림이 다 됐다) 기다리던 누름을
  // 보낸다. 끝나기 전에는 짧은 간격으로 다시 본다 — 회차가 끝났다는 알림은 컴포넌트에 오지 않는다.
  function settle() {
    clearTimeout(S.settleTimer)
    const open = []
    for (const [id, item] of S.items) if (!item.hidden) open.push(id)
    const root = document.querySelector(APP_ROOT)
    const run = root ? root.getAttribute('data-test-script-state') : null
    const running = run === 'running' || run === 'rerunRequested'
    const next = settleSelect(S.queue, S.data.active, Date.now(), BUSY_MS, open, running, MOVED_GRACE_MS)
    if (S.queue.flight !== null) {
      S.settleTimer = setTimeout(() => settle(), SETTLE_POLL_MS)
      return
    }
    const item = next === null ? null : S.items.get(next)
    if (item) sendSelect(item)
    else restoreFocus()
  }
  const appRunning = () => {
    const root = document.querySelector(APP_ROOT)
    const run = root ? root.getAttribute('data-test-script-state') : null
    return run === 'running' || run === 'rerunRequested'
  }
  // 키보드로 옮긴 이동이 끝났다 — 그 화면 회차가 다 선 뒤 초점이 body 로 빠졌으면 지금 탭으로 돌려준다(`<tabs-focus>`).
  function restoreFocus() {
    clearTimeout(S.focusTimer)
    if (S.keyPressAt === null) return
    const focused = document.activeElement
    const lost = !focused || focused === document.body
    const verdict = refocusAfterMove(S.keyPressAt, S.inputAt, lost, appRunning(), Date.now(), BUSY_MS)
    if (verdict === 'wait') {
      S.focusTimer = setTimeout(() => restoreFocus(), SETTLE_POLL_MS)
      return
    }
    S.keyPressAt = null
    if (verdict !== 'focus') return
    const item = S.items.get(S.data.active)
    if (item && !item.hidden) item.__parts.tab.focus({ preventScroll: true })
  }
  // 떠나는 누름을 편집표 편집 회차가 돌아올 때까지 붙든다(`<tabs-hold>`). 붙든 동안 또 누르면 마지막 누름만 남는다.
  const holding = (item, go) => {
    busy(item)
    S.hold = { id: item.dataset.id, at: Date.now(), data: S.data, path: window.location.pathname, go }
    clearTimeout(S.holdTimer)
    S.holdTimer = setTimeout(() => release(), SETTLE_POLL_MS)
  }
  function release() {
    clearTimeout(S.holdTimer)
    const hold = S.hold
    if (!hold) return
    const verdict = holdVerdict(hold, Date.now(), appRunning(), S.data, HOLD_MS, BUSY_MS, window.location.pathname)
    if (verdict === 'wait') {
      S.holdTimer = setTimeout(() => release(), SETTLE_POLL_MS)
      return
    }
    S.hold = null
    // 붙든 표지는 걷는다 — 보내면 `sendSelect` 가 다시 단다(떠나기를 취소하면 표지 없이 남는다).
    const held = S.items.get(hold.id)
    if (held) setAttr(held.__parts.tab, 'aria-busy', null)
    if (verdict === 'go') hold.go()
  }
  // 이 누름이 편집표에서 막 손을 뗀 누름이 아닌가 — 아니면 곧바로 묻고 보낸다.
  const fresh = () => {
    const pending = editPending(Date.now(), S.editAt, S.pressFromGrid, EDIT_MS)
    S.pressFromGrid = false
    return !pending
  }
  const select = (item) => {
    const verdict = pressSelect(S.queue, item.dataset.id, S.data.active, Date.now(), BUSY_MS)
    if (verdict === 'wait') busy(item)
    if (verdict !== 'send') return
    if (fresh()) {
      S.hold = null
      sendSelect(item)
      return
    }
    const id = item.dataset.id
    holding(item, () => {
      const target = S.items.get(id)
      if (target && !target.hidden && id !== S.data.active) sendSelect(target)
      else if (target) setAttr(target.__parts.tab, 'aria-busy', null)
    })
  }
  const close = (item) => {
    const id = item.dataset.id
    if (item.__parts.close.hidden) return
    if (id === S.data.active && !fresh()) {
      holding(item, () => {
        const target = S.items.get(id)
        if (target && !target.hidden) closeNow(target)
      })
      return
    }
    S.hold = null
    closeNow(item)
  }
  const closeNow = (item) => {
    const id = item.dataset.id
    if (item.__parts.close.hidden) return
    const leaving = id === S.data.active
    if (leaving && !leaveOk()) return
    // 키보드 초점이 그 탭(× 등)에 있었으면 숨기기 전에 이웃 탭으로 옮긴다 — 숨긴 단추의 초점은 body 로 빠졌다(E2E). 이웃은
    // 보이는 차례(목록 DOM)로 고른다 — `S.items` 는 만든 차례라 고정해 왼쪽으로 옮긴 탭과 어긋난다. 마우스로 누른 × 도
    // 초점을 받지만(`:focus-visible` 아님) 옮기지 않는다 — 옮기면 이웃 탭의 숨은 핀이 `:focus-within` 으로 드러나 남았다.
    const shadow = nav.getRootNode()
    const focused = shadow.activeElement
    if (focused && item.contains(focused) && focused.matches(':focus-visible')) {
      const open = [...list.children].filter((other) => !other.hidden).map((other) => other.dataset.id)
      const next = S.items.get(focusAfterClose(open, id))
      if (next) next.__parts.tab.focus({ preventScroll: true })
    }
    // 숨기기 전에 지금 그림을 담는다 — 닫는 탭이 제자리에 있어야 서버가 담긴 차례를 먼저 입힌 뒤 보이는 이웃으로 옮긴다
    // (`_on_close`). 숨긴 뒤에 담으면 닫는 탭이 그림에서 빠져 서버 목록 끝으로 밀리고 이웃이 엇갈린다.
    const carried = claimDrawn()
    // 곧바로 숨긴다 — 다음 회차가 목록에서 뺄 때까지 기다림이 보이지 않게. 남은 탭의 × 도 서버 규칙대로 맞춘다(마지막
    // 하나는 닫지 않는다) — 지금 탭이 아닌 탭을 닫으면 서버는 페이지를 다시 돌리지 않아 다음 data 가 곧 오지 않는다.
    item.hidden = true
    syncControls()
    // 지금 탭을 닫으면 서버가 이웃으로 옮긴다 — 그 이동도 기록 한 칸·한 번에 하나다.
    if (leaving) moving(null)
    S.send('close', { id, epoch: S.data.epoch, ...carried })
  }
  // 탭 줄 밖의 떠나기 — 머리 툴바의 테마 단추는 화면을 새로 읽어 세션을 바꾼다. 편집표에서 막 손을 뗀 누름이면 그 편집
  // 회차가 돌아와 저장 안 함 표지가 설 때까지 붙든 뒤(`<tabs-hold>`) 부른 쪽의 확인·새로고침(`fn`)을 잇는다. 단추가 누를
  // 때(`press` — 포커스가 단추로 옮기기 전의 pointerdown) 편집표 포커스를 적는다. 그릴 때마다 이 그리기의 처리로 건다.
  // 붙든 동안 탭을 누르면 마지막 누름만 남는다 — 테마 누름은 버려지고 단추가 제 기다림 표지를 걷는다.
  const gate = {
    press: () => { S.pressFromGrid = S.gridFocused },
    // 막 손을 뗀 누름이면 붙들고 참을 돌려준다 — 거짓이면 붙들지 않았으니 부른 쪽이 그대로 잇는다.
    hold: (fn) => {
      if (fresh()) {
        S.hold = null
        return false
      }
      S.hold = { id: null, at: Date.now(), data: S.data, path: window.location.pathname, go: fn }
      clearTimeout(S.holdTimer)
      S.holdTimer = setTimeout(() => release(), SETTLE_POLL_MS)
      return true
    },
    go: (fn) => {
      if (!gate.hold(fn)) fn()
    },
  }
  window.__capaLeaveGate = gate
  // ---- 끌어서 차례 바꾸기(`<tabs-drag>`). DOM 차례는 놓을 때 한 번만 바꾼다 — 끄는 동안은 끄는 탭이 포인터를 따라가고
  // (`translateX`) 놓을 자리에 세로 막대(`.capa-tabs-drop`)가 선다. 놓으면 서버와 같은 규칙(`movedOrder`)으로 차례를 고치고
  // `move` 를 보낸다. 고정 탭은 끌지 않고, 고정 묶음 앞에는 놓지 않는다. Esc·포인터 취소는 제자리로 돌린다.
  const beginDrag = () => {
    const d = S.drag
    d.others = visibleItems().filter((other) => other !== d.item)
    d.pinned = d.others.filter((other) => other.classList.contains('is-pinned')).length
    const lastPinned = d.pinned > 0 ? d.others[d.pinned - 1] : null
    d.low = lastPinned ? lastPinned.offsetLeft + lastPinned.offsetWidth : 0
    d.left0 = d.item.offsetLeft
    d.width = d.item.offsetWidth
    d.grab = d.x0 - d.item.getBoundingClientRect().left
    d.gap = parseFloat(window.getComputedStyle(list).columnGap) || 0
    d.on = true
    nav.classList.add('is-dragging')
    d.item.classList.add('is-dragging')
    try {
      list.setPointerCapture(d.pointer)
    } catch (error) { /* 포인터가 이미 떠났다 — 창 처리기가 받는다 */ }
    placeDrag()
  }
  // 끄는 탭을 포인터 자리로 옮기고 놓을 자리(`slot`)와 막대를 정한다. 목록 가장자리면 목록을 굴린다.
  function placeDrag() {
    const d = S.drag
    if (!d || !d.on) return
    const box = list.getBoundingClientRect()
    const high = Math.max(d.low, list.scrollWidth - d.width)
    const { left, bound } = dragLeft(d.x - box.left + list.scrollLeft - d.grab, d.low, high)
    d.item.style.transform = `translateX(${left - d.left0}px)`
    const mids = d.others.map((other) => other.offsetLeft + other.offsetWidth / 2)
    d.slot = dropSlot(mids, left + d.width / 2, d.pinned, bound)
    const next = d.others[d.slot]
    const last = d.others[d.others.length - 1]
    const edge = next ? next.offsetLeft - d.gap / 2 : last ? last.offsetLeft + last.offsetWidth + d.gap / 2 : 0
    const x = Math.min(list.offsetLeft + list.clientWidth, Math.max(list.offsetLeft, list.offsetLeft + edge - list.scrollLeft))
    drop.style.left = `${x}px`
    drop.hidden = false
    cancelAnimationFrame(d.frame)
    const speed = list.scrollWidth > list.clientWidth ? edgeSpeed(d.x, box.left, box.right, EDGE_PX, DRAG_EDGE_SPEED_PX) : 0
    if (speed !== 0) {
      d.frame = requestAnimationFrame(() => {
        const was = list.scrollLeft
        list.scrollLeft = was + speed
        if (list.scrollLeft !== was) placeDrag()
      })
    }
  }
  const advanceDrag = () => {
    const d = S.drag
    if (!d) return
    if (d.on) {
      placeDrag()
      return
    }
    const verdict = dragStarts(d.kind, d.x - d.x0, d.y - d.y0, Date.now() - d.at, DRAG_SLOP_PX, TOUCH_HOLD_MS)
    if (verdict === 'cancel') endDrag(false)
    else if (verdict === 'drag') beginDrag()
  }
  // 접은 끌기의 포인터를 놓을 때까지 지켜본다(`heldRelease`) — 놓는 순간부터 `dragClick` 창을 다시 연다. 창 처리기는 그동안만
  // 단다(놓음·같은 포인터의 새 누름·포인터 취소에 뗀다).
  const stopRelease = () => {
    if (S.onRelease) for (const type of RELEASE_EVENTS) window.removeEventListener(type, S.onRelease, true)
    S.onRelease = null
    S.heldPointer = null
  }
  const watchRelease = (pointer) => {
    stopRelease()
    S.heldPointer = pointer
    S.onRelease = (event) => {
      const next = heldRelease(S.heldPointer, event.type, event.pointerId, Date.now())
      if (next.endedAt !== null) S.dragEndAt = next.endedAt
      if (next.held === null) stopRelease()
    }
    for (const type of RELEASE_EVENTS) window.addEventListener(type, S.onRelease, true)
  }
  // 끌기를 끝낸다. `commit` 이면 놓은 자리로 옮긴다. `pressed` 면 포인터가 아직 눌려 있다(Esc·새 data 로 접었다) — 그 포인터를
  // 놓을 때 뒤따르는 click 도 버린다. 끄는 중이 아니었으면(문턱 전) 아무것도 바꾸지 않는다 — 그 누름은 평소의 고르기다.
  const endDrag = (commit, pressed = false) => {
    const d = S.drag
    if (!d) return
    S.drag = null
    clearTimeout(d.holdTimer)
    cancelAnimationFrame(d.frame)
    for (const [type, fn] of d.listeners) window.removeEventListener(type, fn, true)
    try {
      if (list.hasPointerCapture(d.pointer)) list.releasePointerCapture(d.pointer)
    } catch (error) { /* 이미 풀렸다 */ }
    if (!d.on) return
    S.dragEndAt = Date.now()
    if (pressed) watchRelease(d.pointer)
    nav.classList.remove('is-dragging')
    d.item.classList.remove('is-dragging')
    d.item.style.transform = ''
    drop.hidden = true
    if (!commit || !d.item.isConnected || d.item.hidden) return
    const next = d.others[d.slot]
    commitMove(d.item, next ? next.dataset.id : null)
  }
  S.endDrag = endDrag
  // 누름이 끌기가 될 수 있는가 — 왼쪽 단추(터치·펜은 첫 손가락)로 고정하지 않은 보이는 탭의 이름 칸을 눌렀고, 옮길 자리가 있다
  // (고정하지 않은 탭이 둘 이상). 핀·× 를 누른 것은 그 단추의 누름이다.
  const startDrag = (event) => {
    if (event.button !== 0 || event.isPrimary === false) return
    // 문턱을 넘지 않은 채 남은 앞 누름(놓는 사건을 놓쳤다)은 접는다 — 남겨 두면 다음 끌기가 시작되지 않는다.
    if (S.drag) {
      if (S.drag.on) return
      endDrag(false)
    }
    const target = event.target
    const button = target && target.closest ? target.closest('button') : null
    if (button && !button.classList.contains('capa-tabs-tab')) return
    const item = target && target.closest ? target.closest('.capa-tabs-item') : null
    if (!item || !list.contains(item) || item.hidden || item.classList.contains('is-pinned')) return
    if (visibleItems().filter((other) => !other.classList.contains('is-pinned')).length < 2) return
    const d = {
      item, pointer: event.pointerId, kind: event.pointerType || 'mouse', x0: event.clientX, y0: event.clientY,
      x: event.clientX, y: event.clientY, at: Date.now(), on: false, slot: 0, frame: 0, holdTimer: 0, listeners: [],
    }
    S.drag = d
    const own = (other) => other.pointerId === d.pointer && S.drag === d
    d.listeners = [
      ['pointermove', (move) => {
        if (!own(move)) return
        d.x = move.clientX
        d.y = move.clientY
        advanceDrag()
      }],
      ['pointerup', (up) => { if (own(up)) endDrag(true) }],
      ['pointercancel', (cancel) => { if (own(cancel)) endDrag(false) }],
      ['keydown', (key) => {
        if (key.key !== 'Escape' || S.drag !== d) return
        key.preventDefault()
        key.stopPropagation()
        endDrag(false, true)
      }],
    ]
    for (const [type, fn] of d.listeners) window.addEventListener(type, fn, true)
    if (d.kind === 'touch') d.holdTimer = setTimeout(advanceDrag, TOUCH_HOLD_MS)
  }
  // 끌기를 시작한 터치는 목록 굴리기·길게 누르기 메뉴로 넘기지 않는다. 처리기는 처음 한 번 단다(수동이 아니어야 막는다).
  if (!S.onTouchMove) {
    S.onTouchMove = (event) => {
      if (S.drag && S.drag.on) event.preventDefault()
    }
    list.addEventListener('touchmove', S.onTouchMove, { passive: false })
  }
  list.oncontextmenu = (event) => {
    if (S.drag && S.drag.kind === 'touch') event.preventDefault()
  }
  // 끌기의 키보드 대안 — 고정하지 않은 탭 단추에 초점이 있을 때 `Ctrl+Shift+←/→` 로 한 칸(고정 묶음은 넘지 않는다). 초점은
  // 옮긴 탭에 남는다. 다른 조합은 브라우저·OS 가 먼저 가져간다(Ctrl+Shift+PageUp/Down — 브라우저 탭 옮기기, Alt+← — 뒤로가기,
  // Alt+Shift — 입력 언어 바꾸기).
  list.onkeydown = (event) => {
    if (!event.ctrlKey || !event.shiftKey || event.altKey || event.metaKey) return
    const step = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    const tab = step && event.target && event.target.closest ? event.target.closest('.capa-tabs-tab') : null
    const item = tab ? tab.closest('.capa-tabs-item') : null
    if (!item || !list.contains(item)) return
    event.preventDefault()
    const plan = keyboardMove(visibleIds(), pinnedIds(), item.dataset.id, step)
    if (plan === null) return
    commitMove(item, plan.before)
    tab.focus({ preventScroll: true })
  }
  // 누르는 순간(포커스가 탭으로 옮기기 전) 편집표에 포커스가 있었는지 적는다 — 칸 편집기는 바깥 누름에 편집을 적용하고 닫는다.
  list.onpointerdown = (event) => {
    S.pressFromGrid = S.gridFocused
    startDrag(event)
  }
  // 닫기·고정 누름 뒤 포인터 아래로 밀려 온 다른 탭에 닿은 둘째 누름인가(`<tabs-press>`). 포인터 누름(`detail` > 0)만
  // 본다 — 키보드로 누른 단추는 좌표가 없다.
  const stray = (event, item) =>
    event.detail > 0 &&
    strayPress(S.lastPress, item.dataset.id, Date.now(), event.clientX, event.clientY, DOUBLE_PRESS_MS, DOUBLE_PRESS_PX)
  const pressed = (event, item) => {
    S.lastPress = event.detail > 0
      ? { id: item.dataset.id, at: Date.now(), x: event.clientX, y: event.clientY }
      : null
  }
  list.onclick = (event) => {
    // 끌기를 놓은 자리의 누름은 고르기가 아니다(`<tabs-drag>`).
    if (dragClick(S.dragEndAt, Date.now(), DRAG_CLICK_MS)) {
      S.dragEndAt = null
      event.stopPropagation()
      return
    }
    const button = event.target.closest('button')
    const item = button && button.closest('.capa-tabs-item')
    if (!item || !list.contains(item)) return
    const closing = button.classList.contains('capa-tabs-x')
    const pinning = button.classList.contains('capa-tabs-pin')
    if (closing || pinning) event.stopPropagation()
    if (stray(event, item)) return
    // 키보드(Enter·Space)로 누른 단추는 `detail` 이 0 이다 — 옮긴 화면이 다 선 뒤 초점을 돌려줄지 볼 때 쓴다.
    if (event.detail === 0) S.keyPressAt = Date.now()
    if (closing) {
      pressed(event, item)
      close(item)
    } else if (pinning) {
      pressed(event, item)
      // 서버와 같은 규칙으로 곧바로 옮겨 그리고(`<tabs-order>`) 그 차례를 싣는다 — 서버는 페이지를 다시 돌리지 않는다.
      const id = item.dataset.id
      const plan = pinnedOrder(visibleIds(), pinnedIds(), id, !item.classList.contains('is-pinned'))
      arrange(plan)
      S.send('pin', { id, pinned: plan.pinned.includes(id), epoch: S.data.epoch, ...claimDrawn() })
    } else {
      select(item)
    }
  }
  // 가운데 단추 누름도 닫는다(브라우저 탭과 같다). 누르는 순간의 자동 스크롤은 막는다.
  list.onmousedown = (event) => {
    if (event.button === 1) event.preventDefault()
  }
  list.onauxclick = (event) => {
    if (event.button !== 1) return
    const item = event.target.closest('.capa-tabs-item')
    if (!item || !list.contains(item)) return
    event.preventDefault()
    if (stray(event, item)) return
    pressed(event, item)
    close(item)
  }

  // 알림 칸에 낸다 — 코드 · 단계는 파이썬 등록부(`alerts.REGISTRY` — data `alerts`), 화면은 지금 탭이다.
  const flash = (kind, message, short) => {
    const codes = (S.data && S.data.alerts) || {}
    const spec = codes[kind] || {}
    const full = String(message || '')
    const active = S.items.get(S.data.active)
    raiseAlert({
      code: spec.code || '',
      level: spec.level || 'info',
      full,
      short: shortText(short || full),
      page: active ? active.__parts.label.textContent : '',
      href: active ? active.__href : null,
    })
  }
  // 서버가 남긴 상한 알림은 새 일련번호가 올 때 한 번 낸다.
  const message = data.notice
  if (message && typeof message.id === 'number' && message.id !== S.noticeId) {
    S.noticeId = message.id
    flash('limit', message.text)
  }

  // 새로 읽은 문서 — 앞 문서가 적어 둔 설비 시나리오(테마 단추면 공식 발행 쌍이 아니던 것, 새로고침이면 가정이던 것)를
  // 한 번 알린다(`<tabs-return>`). 문서에 한 번이다(탭 줄이 다시 마운트돼도). 알린 칸은 잠시 뒤 지운다 — 그 전에 문서가
  // 떠나면 다음 문서가 다시 알린다.
  if (!window.__capaReturnChecked) {
    window.__capaReturnChecked = true
    let stored = null
    try {
      stored = window.sessionStorage.getItem(RETURN_KEY)
      // 앞 문서가 떠날 때 읽지 못한 테마 표지(탭 줄이 서지 않은 화면 — 부트스트랩 오류 — 에서 누른 테마 단추)는 낡았다.
      // 남겨 두면 이 문서의 다음 새로고침을 테마 전환으로 알린다.
      window.sessionStorage.removeItem(THEME_SWITCH_KEY)
    } catch (error) {
      stored = null
    }
    const message = returnNotice(stored, text)
    const parts = returnParts(stored)
    if (message && parts) {
      const theme = parts.cause === 'theme'
      flash(theme ? 'themed' : 'returned', message, fill(theme ? text.themed_short : text.returned_short, { label: parts.label }))
    }
    if (stored !== null) {
      setTimeout(() => {
        try {
          if (window.sessionStorage.getItem(RETURN_KEY) === stored) window.sessionStorage.removeItem(RETURN_KEY)
        } catch (error) { /* 저장소를 못 쓰면 그대로 둔다 */ }
      }, message ? RETURN_KEEP_MS : 0)
    }
  }
  // 문서를 떠날 때(새로고침·테마 단추·탭 닫기) 띠 CSS 변수를 적는다. 처리기는 문서에 하나이고 걸고 풀지 않는다.
  if (!window.__capaReturnWatch) {
    window.__capaReturnWatch = true
    window.addEventListener('pagehide', () => {
      try {
        const storage = window.sessionStorage
        const themed = storage.getItem(THEME_SWITCH_KEY) !== null
        storage.removeItem(THEME_SWITCH_KEY)
        const style = window.getComputedStyle(document.documentElement)
        const record = returnRecord(
          style.getPropertyValue(RETURN_VARIABLE),
          style.getPropertyValue(RELOAD_RETURN_VARIABLE),
          themed,
        )
        if (record !== null) storage.setItem(RETURN_KEY, record)
      } catch (error) { /* 저장소를 못 쓰면 알리지 않는다 */ }
    })
  }
  // 문서를 떠날 때 저장하지 않은 편집이 있으면 브라우저 확인 창(`<tabs-unload>`). 문서에 하나이고 걸고 풀지 않는다.
  installUnloadGuard(window, document)

  // 탭 상한에 걸리는 주소(`url_path`, HOME 은 빈 글자)인가 — 아는 화면이고, 열린 탭(닫는 중이라 숨긴 탭은 뺀다)과
  // 앞서 지나 보낸 링크가 여는 탭(`<tabs-links>`)에 없고, 그 둘을 합쳐 이미 상한이다. 걸리면 알림 글을, 아니면 빈 글자를
  // 돌려준다. 새 탭을 여는 누름이면 지나 보내며 그 누름을 적는다 — 그 탭이 data 에 오기 전의 다음 누름이 함께 센다.
  const refusal = (href) => {
    const D = S.data
    const pages = (D && D.pages) || {}
    const open = []
    for (const item of S.items.values()) if (!item.hidden) open.push(item.__href)
    const now = Date.now()
    const verdict = linkVerdict(pages, open, D.max, href, linkOpening(S.linkFlight, D.epoch, now, BUSY_MS))
    if (verdict === 'open') S.linkFlight = { href, at: now, epoch: D.epoch }
    if (verdict !== 'refuse') return ''
    // 글 틀은 파이썬 상수(`TEXT`)라 처리기를 단 회차의 것을 그대로 쓴다.
    return fill(text.limit, { max: D.max, label: pages[href] })
  }
  if (!S.onEdit) {
    // 편집표에서 손을 뗀 때와 포커스가 편집표에 있는지를 문서 capture 단계에서 적는다(DOM 이 아니라 시각·참거짓만).
    // 편집표는 glide 격자와 data 의 Components v2 편집 칸이다(`<tabs-grid>` — 그림자 호스트는 바깥 key 칸으로 본다).
    const inGrid = (node) => Boolean(node && node.closest && node.closest(S.gridSelector))
    S.onEdit = (event) => {
      if (event.type === 'focusin') S.gridFocused = inGrid(event.target)
      if (inGrid(event.target)) S.editAt = Date.now()
    }
    for (const type of ['focusin', 'keydown', 'paste', 'cut', 'input']) document.addEventListener(type, S.onEdit, true)
  }
  if (!S.onInput) {
    // 키·포인터 입력 시각 — 키보드로 옮긴 뒤 사용자가 스스로 초점을 옮겼는지 본다(`<tabs-focus>`).
    S.onInput = (event) => {
      S.inputAt = Date.now()
      // 사이드바 링크의 click 때는 초점이 이미 표를 떠났다 — 누르는 순간을 적는다(`S.onLink` 의 붙들기).
      const target = event.type === 'pointerdown' ? event.target : null
      if (target && target.closest && target.closest(PAGE_LINK)) S.pressFromGrid = S.gridFocused
    }
    for (const type of ['keydown', 'pointerdown']) document.addEventListener(type, S.onInput, true)
  }
  if (!S.onLink) {
    // 붙든 링크를 다시 누른다 — 그 사이 다시 지어졌을 수 있어 주소로 찾는다.
    const replayLink = (href) => {
      const link = [...document.querySelectorAll(PAGE_LINK)].find((anchor) => anchor.getAttribute('href') === href)
      if (!link) return
      S.linkReplay = href
      link.click()
    }
    // 왼쪽 단추 누름만 본다 — Streamlit 은 보조 키를 눌러도 같은 창에서 옮긴다. 가운데 단추(새 브라우저 탭)는
    // 새 접속이라 막지 않는다. 새 창으로 여는 바깥 링크도 그대로다. 상한 거름은 열기 표지를 적으므로 붙들기 뒤에 한 번만 돈다.
    S.onLink = (event) => {
      if (event.defaultPrevented || event.button !== 0) return
      const link = event.target && event.target.closest ? event.target.closest(PAGE_LINK) : null
      if (!link || link.target === '_blank') return
      const href = link.getAttribute('href') || ''
      if (S.linkReplay === href) {
        S.linkReplay = null
      } else {
        const gate = window.__capaLeaveGate
        if (gate && gate.hold(() => replayLink(href))) {
          event.preventDefault()
          event.stopPropagation()
          return
        }
      }
      const why = refusal(href.split(/[?#]/)[0])
      if (!why) return
      event.preventDefault()
      event.stopPropagation()
      flash('limit', why)
    }
    document.addEventListener('click', S.onLink, true)
  }
  if (!S.onProcess) {
    // 알림 칸이 읽은 지금 화면의 공정 표지(`capa-process-here`) — 그 주소의 탭 표지만 고친다. 다음 data 는 같은 기록으로 같은 표지를 싣는다.
    S.onProcess = (event) => {
      const detail = event && event.detail
      if (!detail || typeof detail.href !== 'string') return
      for (const item of S.items.values()) {
        if (!item.hidden && item.__href === detail.href) paintProcessMark(item, detail.tab)
      }
      fitWip(S.items.values())
    }
    window.addEventListener(PROCESS_EVENT, S.onProcess)
  }
  if (!S.onOpenPage) {
    // 알림 칸 「그 화면으로」(`capa-open-page` — {href}). 열린 탭이면 탭 고르기와 같은 길(떠나기 확인 · 한 번에 하나), 아니면
    // 그 화면 링크를 누른다 — 상한 거름(`S.onLink`)이 같은 누름으로 받는다. 지금 화면이면 아무것도 하지 않는다.
    S.onOpenPage = (event) => {
      const detail = event && event.detail
      if (!detail || typeof detail.href !== 'string') return
      const href = detail.href
      for (const item of S.items.values()) {
        if (item.hidden || item.__href !== href) continue
        if (item.dataset.id !== S.data.active) select(item)
        return
      }
      const link = [...document.querySelectorAll(PAGE_LINK)].find(
        (anchor) => linkPath(anchor.getAttribute('href') || '') === href,
      )
      if (link) link.click()
    }
    window.addEventListener(OPEN_PAGE_EVENT, S.onOpenPage)
  }

  // 담긴 차례(또는 받지 못해 다시 담은 차례)가 있으면 보내기를 다시 잰다 — 이 함수 밖에서 본다(아래와 같은 까닭).
  if (S.moves.due !== null) {
    clearTimeout(S.moveTimer)
    S.moveTimer = setTimeout(() => flushMove(), Math.max(0, MOVE_SEND_MS - (Date.now() - S.moves.due.at)))
  }
  // 새 data 가 왔다 — 보낸 이동이 끝났는지 본다(지금 탭이 바뀐 data 와 그 회차의 끝이 표지다). 붙든 누름이 있으면 새
  // data 로 다시 본다. 둘 다 이 함수(부품 그리기) 밖에서 본다 — 그리기 안에서 트리거를 보내면 Streamlit 프런트가 그 값을
  // 회차 요청에 싣지 않아 누름이 사라졌다(사외 사본: 탭 줄이 온 즉시 그리기 안에서 보낸 둘째 누름 30번 중 4번이 탭 줄 칸
  // 없는 요청으로 갔다. 그리기 밖으로 미루니 30번 모두 닿았다).
  if (S.queue.flight !== null) {
    clearTimeout(S.settleTimer)
    S.settleTimer = setTimeout(() => settle(), 0)
  }
  if (S.hold) {
    clearTimeout(S.holdTimer)
    S.holdTimer = setTimeout(() => release(), 0)
  }

  return () => {
    if (S.drag && S.endDrag) S.endDrag(false)
    stopRelease()
    if (S.onTouchMove) list.removeEventListener('touchmove', S.onTouchMove)
    S.onTouchMove = null
    clearTimeout(S.busyTimer)
    clearTimeout(S.settleTimer)
    clearTimeout(S.holdTimer)
    clearTimeout(S.focusTimer)
    clearTimeout(S.moveTimer)
    if (S.onEdit) {
      for (const type of ['focusin', 'keydown', 'paste', 'cut', 'input']) document.removeEventListener(type, S.onEdit, true)
    }
    S.onEdit = null
    if (S.onFonts && document.fonts && document.fonts.removeEventListener) {
      document.fonts.removeEventListener('loadingdone', S.onFonts)
    }
    S.onFonts = null
    if (S.onLink) document.removeEventListener('click', S.onLink, true)
    S.onLink = null
    if (S.onOpenPage) window.removeEventListener(OPEN_PAGE_EVENT, S.onOpenPage)
    S.onOpenPage = null
    if (S.onProcess) window.removeEventListener(PROCESS_EVENT, S.onProcess)
    S.onProcess = null
    if (S.onInput) {
      for (const type of ['keydown', 'pointerdown']) document.removeEventListener(type, S.onInput, true)
    }
    S.onInput = null
    if (S.onScroll) list.removeEventListener('scroll', S.onScroll)
    S.onScroll = null
    if (S.resizer) S.resizer.disconnect()
    S.resizer = null
    S.reveal = null
    if (window.__capaLeaveGate === gate) delete window.__capaLeaveGate
  }
}
