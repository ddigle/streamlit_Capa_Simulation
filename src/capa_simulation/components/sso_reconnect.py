# Purpose: 툴바 iframe 연결 틱 스크립트 — 끊긴 탭의 「다시 로그인」·재시작 띠와 공지 물음을 만든다.

"""다시 붙지 못한 탭의 「다시 로그인」 띠.

문지기(`auth/gate.py`)는 세션이 만료됐거나 로그아웃한(폐기 목록) 탭의 websocket 을 다음 메시지에서
닫고, 다시 붙으려는 핸드셰이크와 `/_stcore/host-config` 를 거절한다(403 · 401). 쿠키는 HttpOnly
이고 만료 시각에 브라우저가 지우며, 로그아웃은 쿠키를 지운다 — 그래서 다시 붙지 못한다. 접속
명단에서 빠지면(명단은 재시작 때 읽으므로 재시작 뒤 다시 붙는 탭) 쿠키가 남아 있어도 같은 401 이고
「다시 로그인」 은 콜백의 거절 화면으로 간다. Streamlit
프런트는 그때 머리 띠의 「CONNECTING」 과 영어 창 「Connection failed with status 401.」 만 보이고,
화면에는 만료 전 내용이 남는다. 사람에게는 다음 할 일이 보이지 않는다(검토 실측 — 모달을 닫아도
CONNECTING 이 이어진다).

이 스크립트가 그 빈자리를 메운다. 앱 루트(`stApp`)의 연결 상태 표지(`data-test-connection-state`)를
1초마다 읽어, 붙어 있지 않은 채 `PROBE_WAIT_MS` 가 지나면 같은 출처의 `/_stcore/host-config` 에
쿠키를 실어 묻는다(`PROBE_GAP_MS` 마다 한 번). **401 이면** 로그인이 끝난 것이므로 화면 맨 위에
한국어 띠와 링크를 세운다. 그 밖의 답은 아래 「서버 재시작 띠」 가 가른다 — 시작 임시 응답 · 답
없음이면 재시작 띠를 세우고, 서버가 떠 있으면(200 등) Streamlit 이 스스로 다시 붙으므로 띠를
걷는다. 다시 붙으면(다른 탭에서 다시 로그인한 뒤 등) 띠를 걷는다.

**띠는 까닭 셋으로 가른다**(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-tab-ended). 문지기가 그
401 에 까닭 낱말 머리(`names.REASON_HEADER` — `gate.ended_reason`)를 단다. 로그아웃은 쿠키를 지우고
끝난 쿠키는 브라우저가 버리므로 물을 때 쿠키가 남아 있는 갈래는 명단에서 빠짐 · 명단 못 읽음뿐이다 —
넷으로 가르지 않는다.

- `other`(대부분 — 쓰지 않아 끝남 · 최대 시간 지남 · 로그아웃): `OTHER_NOTICE` + 「다시 로그인」.
- `denied`(명단에서 빠짐): `DENIED_NOTICE` + 「접속 권한 신청」 — 같은 로그인 경로라 통합인증을 거쳐
  콜백의 거절 화면으로 간다(신청은 그 화면이 받는다).
- `unread`(서버가 S3 명단을 아직 못 읽음): `UNREAD_NOTICE` + 「다시 로그인」.
- 머리가 없으면(앞단이 뗐거나 옛 서버) 넷을 다 적은 옛 글(`RECONNECT_NOTICE`)로 떨어진다.

끊긴 동안 물음은 이어지므로 까닭이 바뀌면(명단을 읽은 뒤 빠짐이 드러남 등) 띠 글을 바꾼다.

**자동으로 IdP 로 보내지 않는다.** 로그아웃은 이 브라우저의 앱 로그인을 끝내는 일이다 — 열어 둔
다른 탭이 `run_every` 프래그먼트 회차나 클릭 하나로 저절로 다시 로그인하면 로그아웃이 조용히
되돌려진다. 사람이 띠를 읽고 「다시 로그인」 을 누른다(만료 멈춤 화면과 같은 안내 — 다시 로그인하면
저장하지 않은 편집은 사라진다). 띠는 Streamlit 의 연결 오류 창보다 위에 선다(z-index). 그 창은
react-aria 모달이라 열리는 동안 바깥 요소를 `inert` 로 만든다 — 그러면 띠가 보여도 누름이 창으로
떨어진다(브라우저 실측). react-aria 가 비워 두는 표지 `data-react-aria-top-layer` 를 띠에 달아 그
대상에서 뺀다.

**띠가 선 동안 그 영어 창(「Connection failed with status 401.」)은 감춘다**(2026-11-08 사용자 답
b2). 띠가 창 제목과 닫기 X 를 덮고 본문 줄만 삐져나와 같은 일을 두 번(그것도 영어로) 말했다. 창은
띠보다 늦게 뜰 때가 있어 띠가 선 동안 화면 바뀜을 지켜보아 뜨는 그 순간 감추고, 매 틱 한 번 더
찾는다. 가르는 표는 창 글(`connectionDialog` — 판정 구획)이다 — 같은 꼴의 앱 팝업(`st.dialog`)은
건드리지 않는다. 머리의 Streamlit 상태 글(`STATUS_WIDGET_SELECTOR` — 「CONNECTING」)도 같은
표지 · 같은 지켜보기로 띠가 선 동안 감춘다 — 띠가 같은 일을 한국어로 말하는데 넓은 창에서는 띠 옆에
그대로 보였다(E2E — 보드 답 english=band 와 같은 뜻). 띠가 선 동안은 끊긴 때라 그 자리는 연결 상태
글뿐이고, 전환 뒤 새 요소로 다시 서도 지켜보기가 그리기 전에 감춘다. 띠를 걷으면 지켜보기를 끝내고
감춘 창 · 상태 글을 되돌린다(띠가 없을 때의 창 · 상태 글 — 잠깐의 끊김 · 평소의 실행 표시 — 은
그대로다).

링크는 `CAPA_PUBLIC_URL` 바탕의 `/auth/sso/login?next=<지금 경로 + 질의>` 다 — 경로에서 공개 주소의
경로 접두(WebIDE `/proxy/<포트>`)를 떼는 것은 `sso_identity.return_path` 와 같은 규칙이고, 서버가
`next` 를 다시 정화한다. 물음은 지금 창의 출처로 보낸다(공개 주소가 다른 출처면 쿠키가 실리지
않는다).

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). 내용은 프로세스 안에서 늘 같다(공개 주소 · 문구가 고정). 그래서 띠 색은
지금 실행의 테마가 아니라 밝은 · 어두운 팔레트를 둘 다 싣고, 띠를 세우는 순간 테마 버튼과 같은
키 규칙(같은 iframe 맨 앞의 `capaTheme`)으로 앱 테마를 읽어 고른다(Guide · Print 단추와 같은 길).
타이머는 iframe 창의 것이라 iframe 이 사라지면 같이 멈춘다. 판정(`// <sso-reconnect-rule>`)은 DOM
을 모르는 순수 구획이라 node 시험이 떼어 돌린다(`tests/test_sso_reconnect.py`).

**서버 재시작 띠도 같은 스크립트다**(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-restart-tab ·
리뷰 critic-design — 같은 연결 상태를 1초마다 읽는 스크립트를 둘로 두지 않는다). 같은 틱 · 같은
물음의 답으로 가른다(`probeKind`): 401 이면 위 「다시 로그인」 띠, 503 + `X-Capa-Stage`(시작 임시
응답 — `scripts/container_stage.py`)면 그 상태 줄(`/_capa_stage` 셋째 줄의 짧은 글)을 실은
재시작 띠 「서버를 다시 시작하는 중입니다 — <데이터 받는 중 · 2번째 받기>. 끝나면 이 탭이 저절로
다시 붙습니다. 이 탭에서 저장하지 않은 편집은 사라집니다.」, 답이 아예 없는 동안(연결 실패 ·
`PROBE_TIMEOUT_MS` 넘김)은 「서버 응답을 기다리는 중입니다」, 답 없음이 `UNREACHABLE_AFTER_MS` 를
넘게 이어지면 「서버에 닿지 않습니다 — 다시 붙는 중」. 표 없는 5xx 는 같은 뿌리의 health 를
한 번 더 묻는다(시작 임시 화면의 쪽 JS 와 같은 판정 — 표 없는 2xx 면 앱의 답). health 도 앱 답이
아니면(앞단 502 · 504 · Streamlit 준비 전) 기다림이다. 앱의 답이면 host-config 를 한 번 더 묻고,
그래도 표 없는 5xx 면 앱이 떠서 이 탭을 거절하는 것이다(통합인증 설정 막힘의 503 — 기다려도 붙지
않고 새로 열면 설정 화면). 그때는 같은 자리에 설정 막힘 띠(`BLOCKED_NOTICE` — 설정 막힘 화면과
같은 낱말)와 지금 문서를 다시 여는 「새로고침」 링크(풍선 — 저장하지 않은 편집은 사라짐)를
세운다(2026-11-14 보드 english). 다시 물을 때 앱이 답하면 넘김 틈의 앞단 5xx 였으므로 띠를 걷는다.
그 밖의 답(서버가 떠 있음)도 띠를 걷는다 — Streamlit 이 스스로 다시 붙는다. 재시작 띠는 링크가
없고(기다리면 붙는다) 재시작 자리의 띠는 로그인 띠가 서 있으면 서지 않는다. 띠가 선 동안 영어 연결
창(`CONNECTION_DIALOG_TEXTS` — 401 · 5xx · 시간 넘김 · not responding · localhost 의 still
running)을 감춘다(같은 길). 다시 붙으면 띠를 걷고 서버 재시작 알림(`GL-07`)이 이어 알린다.

**통합인증이 꺼진 서버에도 싣는다** — 재시작은 통합인증과 상관없다. 꺼짐이면 로그인 띠 없이 재시작
갈래만 돌고(`restart_script`), 물음은 지금 주소 기준 상대 경로(`<지금 경로의 폴더>/_stcore/…`)로
보낸다 — 공개 주소 설정이 없어서다(WebIDE `/proxy/<포트>/` 처럼 앞단이 붙인 접두도 그대로 따른다).
그래서 꺼짐의 툴바 iframe 에도 스크립트 하나가 더 실린다(내용은 프로세스 안에서 늘 같다).

**운영 서버의 공지 물음도 같은 틱이다**(2026-11-17 공지 보드 답 q-speed — 같은 연결 상태를 1초마다
읽는 스크립트를 둘로 두지 않는다). 문지기가 있는 서버(`runtime.gate_installed()` — `capa_server.py`
로 뜸, 통합인증 켜짐 · 꺼짐 모두)에만 그 갈래(`_NOTICE_POLL`)를 싣고, `app.py` 로 띄운 개발 ·
WebIDE · 시험에는 싣지 않는다(그때 공지는 앱 전체 회차의 알림 칸 data 로만 닿는다). 표지는 문지기가
서는 첫 요청 때 한 번 서므로 프로세스 안에서 글이 늘 같다.

- 연결 표지가 붙음(`CONNECTED`)인 동안만 묻는다 — 붙은 때(또는 지난 물음)에서
  `NOTICE_POLL_MS`(10초)마다 같은 출처 `GET /capa/notice`(`names.NOTICE_PATH` — 뿌리는 위 물음과
  같은 `appRoot`, 쿠키 실음 · `no-store` · 물음 상한 `PROBE_TIMEOUT_MS`). 첫 물음은 붙은 지 10초
  뒤다 — 막 붙은 탭은 그 회차의 알림 칸 data 가 같은 꼴을 이미 실었다. 끊긴 동안 · 처음 · 표지
  없음(판올림)은 묻지 않는다.
- 답(`noticeStep`): **401 이면 멈춘다** — 만료 · 로그아웃한 탭이 10초마다 문지기를 두드리지
  않게(문지기는 http 401 을 기록하지 않고 이 물음은 로그인을 늘리지 않는다). 끊겼다가 다시
  붙으면(문지기가 쿠키를 다시 본 핸드셰이크) 멈춤을 푼다. 2xx 는 읽고, 그 밖(5xx · 시작 임시 응답 ·
  앞단 거절 · 답 없음)은 다음 차례다.
- 읽은 글(`noticeRead`)은 JSON 이고 프로세스 표지(`mark`) · 판(`rev`)이 있어야 받는다(앞단이 낸 HTML
  은 버림). 표지 + 판이 지난번 넘긴 것과 다를 때만 부모 문서의 `window.__capaAlerts.notice(payload)`
  에 넘긴다 — 알림 칸이 data 와 같은 길(`applyNotice` — 판이 오른 것만)로 받는다. 칸이 아직 서지
  않았으면 그 꼴을 쥐고 있다가 다음 틱에 넘긴다(사건 알림 대기열 `__capaAlertQueue` 는 `raise`
  꼴이라 쓰지 않는다). 끊기면 쥔 꼴을 버린다 — 다시 붙은 회차의 알림 칸 data 가 정본이다.

**비공식 경로다.** Streamlit 1.63 프런트의 연결 상태 표지에 기댄다. 판올림으로 표지가 사라지면 띠가
서지 않고 공지 물음이 돌지 않을 뿐 나머지는 그대로다(공지는 앱 전체 회차로 닿는다) — 올릴 때 만료 ·
로그아웃 뒤 다시 붙기를 브라우저로 한 번 본다(머리 상태 글의 표가 바뀌면 그 글이 띠 곁에 다시 보일
뿐이다).
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.auth.web import CONFIG_TITLE, REGISTER_LABEL
from capa_simulation.components.sso_identity import LOGIN_AGAIN_LABEL, REFRESH_LABEL, REFRESH_TIP
from capa_simulation.design import tokens

BANNER_ID = "capa-sso-reconnect"
# 띠에 단 까닭 표지 — 까닭이 바뀌면 띠를 다시 세운다(브라우저 확인 · 시험이 읽는다).
KIND_ATTRIBUTE = "data-capa-sso-reason"
# 붙어 있지 않은 채 이만큼 지나야 묻는다 — 잠깐의 끊김(재실행 · 망 흔들림)에는 묻지 않는다.
PROBE_WAIT_MS = 3_000
# 묻는 사이 — 끊긴 동안 이만큼마다 한 번.
PROBE_GAP_MS = 10_000
TICK_MS = 1_000
HOST_CONFIG_PATH = "/_stcore/host-config"
# 붙어 있는 동안 공지를 묻는 사이(운영 서버 — 2026-11-17 공지 보드 답 q-speed 「10초」).
NOTICE_POLL_MS = 10_000
NOTICE_PATH = names.NOTICE_PATH
# 띠가 선 동안 감추는 Streamlit 연결 오류 창의 글 — 401 이라 띠가 선 그 창만 고른다(Streamlit 1.63
# 프런트 글, 비공식 — 판올림으로 글이 바뀌면 창이 남을 뿐 띠는 그대로다).
CONNECTION_DIALOG_TEXT = "Connection failed with status 401"
# 재시작 자리의 띠가 선 동안 함께 감추는 창 글 — 임시 응답의 503 · 막힘의 503 · 앞단의 502 · 504,
# 핑 시간 넘김(앞단이 요청을 붙듦), 답이 없는 틈(localhost 로 연 탭은 글이 다르다 — 같은 프런트 글).
# 띠가 선 동안만 감추므로 앱 팝업은 건드리지 않는다.
CONNECTION_DIALOG_TEXTS = (
    CONNECTION_DIALOG_TEXT,
    "Connection failed with status 5",
    "Streamlit server is not responding",
    "Connection timed out.",
    "Is Streamlit still running?",
)
# 띠가 선 동안 함께 감추는 Streamlit 머리 상태 글(「CONNECTING」 · 실행 표시가 서는 자리 —
# Streamlit 1.63 프런트 표, 비공식). 끊긴 동안 그 자리는 연결 상태 글뿐이다.
STATUS_WIDGET_SELECTOR = '[data-testid="stStatusWidget"]'
RESTART_BANNER_ID = "capa-restart-band"
STAGE_HEADER = "X-Capa-Stage"
STAGE_STATUS_PATH = "/_capa_stage"
# 표 없는 5xx 뒤 한 번 더 묻는 곳 — 앱이 떠 있으면 문지기가 막힘에서도 앱으로 넘긴다.
HEALTH_PATH = names.HEALTH_PATH
# 물음 하나의 시간 상한 — 앞단이 요청을 붙들어도 다음 물음이 막히지 않게 묻는 사이보다 짧다. 넘기면
# 답 없음으로 센다.
PROBE_TIMEOUT_MS = 8_000
# 답이 아예 없는 물음이 이만큼 이어지면 「닿지 않습니다」 로 바꾼다(답이 한 번 오면 다시 센다).
UNREACHABLE_AFTER_MS = 20_000
RESTART_LEAD = "서버를 다시 시작하는 중입니다"
RESTART_TAIL = "끝나면 이 탭이 저절로 다시 붙습니다. 이 탭에서 저장하지 않은 편집은 사라집니다."
WAITING_NOTICE = "서버 응답을 기다리는 중입니다"
UNREACHABLE_NOTICE = "서버에 닿지 않습니다 — 다시 붙는 중"
# 앱이 떠서 이 탭을 거절함(통합인증 설정 막힘) — 설정 막힘 화면(`auth/web.CONFIG_TITLE` ·
# `CONFIG_TEXT` 첫 문장)과 같은 낱말이고 링크는 지금 문서를 다시 여는 「새로고침」 이다. 문의처는
# 새로 연 설정 화면의 문의 줄이 말한다(띠에는 문의 줄이 없다).
BLOCKED_NOTICE = (
    f"{CONFIG_TITLE} — 서버 설정을 고치는 중입니다. 잠시 뒤 「{REFRESH_LABEL}」 을 누르세요."
)
# 재시작 자리에 선 띠가 설정 막힘 띠임을 가르는 표지 — 재시작 띠 글로 바뀔 때 링크째 다시 세운다.
BLOCKED_MARK = "data-capa-blocked"
# 열린 탭이 끝나면 사용자가 실제로 보는 것은 이 띠다 — 문지기가 앱 스크립트의 만료 화면보다 먼저
# 연결을 닫는다. 까닭 머리가 오면 셋으로 가른 글, 오지 않으면(앞단이 뗌 · 옛 서버) 까닭 넷을 다 적은
# 옛 글이다.
OTHER_NOTICE = (
    "로그인이 끝나 이 탭이 서버에 다시 붙지 못합니다(오래 쓰지 않았거나, 로그인 최대 시간이 "
    "지났거나, 로그아웃했습니다). 다시 로그인하면 이 탭에서 저장하지 않은 편집은 사라집니다."
)
DENIED_NOTICE = (
    "이 계정은 접속 명단에서 빠져 이 탭을 이어 쓸 수 없습니다. 저장하지 않은 편집은 사라집니다."
)
UNREAD_NOTICE = (
    f"서버가 접속 명단을 읽지 못해 다시 붙지 못합니다 — 1분 뒤 「{LOGIN_AGAIN_LABEL}」 을 누르세요."
)
RECONNECT_NOTICE = (
    "통합인증 로그인이 끝나 이 탭이 서버에 다시 붙지 못합니다(오래 쓰지 않았거나 로그인 최대 "
    "시간이 지났거나 접속 명단에서 빠졌거나 이 브라우저에서 로그아웃했습니다). 다시 로그인하면 이 "
    "탭에서 저장하지 않은 편집은 사라집니다."
)

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

// <sso-reconnect-rule>
// 연결 상태 표지가 「붙어 있지 않음」 인가 — 붙음 · 정적 붙음 · 처음 · 표지 없음(판올림)은 아니다.
function disconnected(state) {
  if (typeof state !== "string" || state === "") return false;
  return state !== "CONNECTED" && state !== "STATIC_CONNECTED" && state !== "INITIAL";
}
// 지금 서버에 물을 때인가 — 끊긴 지 waitMs 가 지났고 지난 물음에서 gapMs 가 지났다.
function probeDue(since, lastProbe, now, waitMs, gapMs) {
  if (since === null || now - since < waitMs) return false;
  return lastProbe === null || now - lastProbe >= gapMs;
}
// 띠가 대신 말하는 Streamlit 연결 오류 창인가 — 그 창의 글로 가른다(앱 팝업은 아니다).
function connectionDialog(text) {
  if (typeof text !== "string") return false;
  var marks = %(dialog_texts)s;
  for (var i = 0; i < marks.length; i++) if (text.indexOf(marks[i]) !== -1) return true;
  return false;
}
// 문지기가 401 에 단 까닭 낱말 → 띠 갈래. 모르는 낱말 · 머리 없음(앞단이 뗌 · 옛 서버)은 옛 글.
function bandKind(reason) {
  if (reason === "denied" || reason === "unread" || reason === "other") return reason;
  return "legacy";
}
// health 답이 앱의 것인가 — 표 없는 2xx(시작 임시 응답의 health 는 표가 있다).
function appAnswers(status, staged) {
  return typeof status === "number" && status >= 200 && status < 300 && !staged;
}
// health 가 앱의 답일 때 다시 물은 host-config 의 답이 아직 표 없는 5xx 인가 — 그러면 앱이 떠서
// 이 탭을 거절하는 것이다(통합인증 설정 막힘). 다시 물을 때 앱이 답하면 넘김 틈의 앞단 5xx 였다.
function stillRefused(status, staged) {
  return typeof status === "number" && status >= 500 && !staged;
}
// 물음의 답 → 띠 갈래. `status` 가 null 이면 답이 없었다(연결 실패 · 시간 넘김). `staged` 는 시작
// 임시 응답의 표(`X-Capa-Stage`), `appUp` 은 표 없는 5xx 뒤 health 가 앱의 답이었는가, `downMs` 는
// 답 없음이 이어진 시간, `refused` 는 그 뒤 다시 물은 host-config 도 표 없는 5xx 였는가(앱이 떠서
// 거절 — 막힘)다.
function probeKind(status, staged, appUp, downMs, unreachableMs, refused) {
  if (status === 401) return "login";
  if (status === null) return downMs >= unreachableMs ? "unreachable" : "waiting";
  if (staged) return "stage";
  if (status >= 500) return !appUp ? "waiting" : refused ? "blocked" : "none";
  return "none";
}
// 재시작 띠 글 — 임시 응답 상태 줄(`/_capa_stage`)의 셋째 줄(JSON) 짧은 글. 없으면(옛 임시 응답)
// 첫 줄, 그것도 없으면 상태 없이.
function restartNotice(statusText, lead, tail) {
  var lines = typeof statusText === "string" ? statusText.split("\\n") : [];
  var phrase = "";
  try {
    var info = JSON.parse(lines[2] || "");
    if (info && typeof info.band === "string") phrase = info.band;
  } catch (error) {
    phrase = "";
  }
  if (!phrase) phrase = lines[0] || "";
  return lead + (phrase ? " — " + phrase : "") + ". " + tail;
}
// 물음을 보낼 앱 뿌리 — 켜짐은 공개 주소의 경로 접두, 꺼짐은 지금 경로의 폴더.
function probeRoot(loginOn, origin, prefix, href) {
  if (loginOn) return origin + prefix;
  return new URL(".", href).href.replace(/\\/$/, "");
}
// 다시 로그인 주소 — 공개 주소 + 로그인 경로 + next(지금 경로에서 공개 주소의 경로 접두를 뗀
// 것 + 질의).
function loginHref(base, prefix, loginPath, pathname, search) {
  var path = pathname || "/";
  if (prefix && (path === prefix || path.indexOf(prefix + "/") === 0)) {
    path = path.slice(prefix.length) || "/";
  }
  return base + loginPath + "?next=" + encodeURIComponent(path + (search || ""));
}
// 공지를 물어도 되는 연결 상태인가 — 붙어 있을 때만(끊김 · 처음 · 표지 없음은 묻지 않는다).
function noticeConnected(state) {
  return state === "CONNECTED";
}
// 지금 공지를 물을 때인가 — 붙은 때 · 지난 물음(since)에서 gapMs 가 지났고, 401 로 멈추지 않았고,
// 묻는 중이 아니다.
function noticeDue(since, stopped, asking, now, gapMs) {
  if (stopped || asking || since === null) return false;
  return now - since >= gapMs;
}
// 공지 물음 답의 상태 → 할 일. 401 은 멈춤(만료 탭이 문지기를 두드리지 않게), 2xx 는 읽음,
// 그 밖(5xx · 시작 임시 응답 · 앞단 거절)은 다음 차례.
function noticeStep(status) {
  if (status === 401) return "stop";
  if (typeof status === "number" && status >= 200 && status < 300) return "read";
  return "next";
}
// 공지 물음 답 글 → {key, payload}. 열쇠는 프로세스 표지 + 판이다. JSON 이 아니거나(앞단이 낸
// HTML 등) 표지 · 판이 없으면 null — 받지 않는다.
function noticeRead(text) {
  var payload = null;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    return null;
  }
  if (!payload || typeof payload !== "object" || typeof payload.mark !== "string") return null;
  if (typeof payload.rev !== "number" || !isFinite(payload.rev)) return null;
  return { key: payload.mark + ":" + payload.rev, payload: payload };
}
// </sso-reconnect-rule>

  var since = null;
  var lastProbe = null;
  // 답이 아예 없기 시작한 때 — 답이 한 번이라도 오면 지운다(임시 응답이 몇 분 답한 뒤 포트를 넘기는
  // 틈은 「닿지 않습니다」 가 아니다).
  var silentSince = null;
  var probing = false;
  // 앱 테마는 테마 버튼과 같은 키 규칙(같은 iframe 맨 앞의 `capaTheme`)으로 읽는다.
  function dark() {
    return typeof capaTheme !== "undefined" && capaTheme.resolve(parentWindow).choice === "Dark";
  }
  // 띠가 선 동안 감춘 연결 오류 창 · 머리 상태 글 표지 — 띠를 걷을 때 이 표지가 있는 것만 되돌린다.
  var HIDDEN_MARK = "data-capa-sso-hidden";
  function hideConnectionDialogs() {
    var boxes = doc.querySelectorAll('[data-testid="stDialog"]');
    for (var i = 0; i < boxes.length; i++) {
      var dialog = boxes[i];
      if (dialog.hasAttribute(HIDDEN_MARK) || !connectionDialog(dialog.textContent)) continue;
      dialog.setAttribute(HIDDEN_MARK, "");
      dialog.style.setProperty("display", "none", "important");
    }
    // 머리 상태 글(「CONNECTING」)도 띠가 대신 말한다 — 띠가 선 동안만 부르므로 끊긴 때의 글뿐이다.
    var widgets = doc.querySelectorAll(%(status_widget)s);
    for (var j = 0; j < widgets.length; j++) {
      var widget = widgets[j];
      if (widget.hasAttribute(HIDDEN_MARK)) continue;
      widget.setAttribute(HIDDEN_MARK, "");
      widget.style.setProperty("display", "none", "important");
    }
  }
  // 띠가 선 동안 뒤늦게 뜨는 연결 오류 창 · 새 요소로 다시 선 머리 상태 글은 뜨는 그 순간 감춘다 —
  // 틱만 기다리면 창이 한 틱 동안 띠 곁에 보였다. 지켜보기는 띠가 선 동안만 한다(평소 회차의 화면
  // 바뀜을 지켜보지 않는다).
  var watcher = null;
  function watchConnectionDialogs() {
    var Observer = parentWindow.MutationObserver || window.MutationObserver;
    if (watcher || !Observer) return;
    watcher = new Observer(function () {
      if (doc.getElementById(%(banner_id)s) || doc.getElementById(%(restart_id)s)) {
        hideConnectionDialogs();
      }
    });
    watcher.observe(doc.body, { childList: true, subtree: true, characterData: true });
  }
  function restoreConnectionDialogs() {
    if (watcher) {
      watcher.disconnect();
      watcher = null;
    }
    var boxes = doc.querySelectorAll("[" + HIDDEN_MARK + "]");
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].removeAttribute(HIDDEN_MARK);
      boxes[i].style.removeProperty("display");
    }
  }
  function hideBanner() {
    var box = doc.getElementById(%(banner_id)s);
    if (box) box.remove();
    restoreConnectionDialogs();
  }
  // 재시작 띠 — 링크 없는 한 줄. 로그인 띠가 서 있으면 세우지 않는다(로그인이 먼저다). 같은 자리에
  // 설정 막힘 띠(링크 있음 — `showBlocked`)가 서 있었으면 걷고 새로 세운다.
  function hideRestart() {
    var box = doc.getElementById(%(restart_id)s);
    if (!box) return;
    box.remove();
    if (!doc.getElementById(%(banner_id)s)) restoreConnectionDialogs();
  }
  function showRestart(notice) {
    if (doc.getElementById(%(banner_id)s)) return;
    var box = doc.getElementById(%(restart_id)s);
    if (box && box.hasAttribute(%(blocked_mark)s)) {
      box.remove();
      box = null;
    }
    if (!box) {
      box = doc.createElement("div");
      box.id = %(restart_id)s;
      box.setAttribute("role", "status");
      box.setAttribute("data-react-aria-top-layer", "");
      box.style.cssText = dark() ? %(dark_box_style)s : %(light_box_style)s;
      doc.body.appendChild(box);
    }
    if (box.textContent !== notice) box.textContent = notice;
    hideConnectionDialogs();
    watchConnectionDialogs();
  }
  // 묻는 한 번 — 상한 안에 답이 없으면 끊고 답 없음(거절)으로 센다. 답은 상태 · 표 · (원하면) 글.
  function ask(path, withText) {
    var stop = new AbortController();
    var timer = window.setTimeout(function () {
      stop.abort();
    }, %(timeout_ms)d);
    return fetch(appRoot() + path, {
      credentials: "same-origin",
      cache: "no-store",
      signal: stop.signal,
    })
      .then(function (response) {
        var answer = {
          status: response.status,
          staged: response.headers.has(%(stage_header)s),
          reason: response.headers.get(%(reason_header)s),
        };
        if (!withText) return answer;
        return response.text().then(function (text) {
          answer.text = text;
          return answer;
        });
      })
      .finally(function () {
        window.clearTimeout(timer);
      });
  }
  function answered(status, staged, appUp, downMs, refused) {
    var kind = probeKind(status, staged, appUp, downMs, %(unreachable_ms)d, refused);
    if (kind === "login" || kind === "none") return Promise.resolve(hideRestart());
    if (kind === "blocked") return Promise.resolve(showBlocked());
    if (kind === "waiting") return Promise.resolve(showRestart(%(waiting)s));
    if (kind === "unreachable") return Promise.resolve(showRestart(%(unreachable)s));
    return ask(%(stage_path)s, true)
      .then(function (answer) {
        return answer.staged ? answer.text : "";
      })
      .catch(function () {
        return "";
      })
      .then(function (text) {
        showRestart(restartNotice(text, %(restart_lead)s, %(restart_tail)s));
      });
  }
  // 표 없는 5xx — 앱이 떠서 거절하는지 health 를 한 번 더 묻는다. 앱의 답이면 host-config 를 다시
  // 물어 그래도 표 없는 5xx 인지 본다(넘김 틈의 앞단 5xx 는 다시 물을 때 앱이 답한다).
  function answeredServerError(status) {
    return ask(%(health_path)s, false).then(
      function (health) {
        if (!appAnswers(health.status, health.staged)) return answered(status, false, false, 0);
        return ask(%(host_config)s, false).then(
          function (again) {
            return answered(status, false, true, 0, stillRefused(again.status, again.staged));
          },
          function () {
            return answered(status, false, true, 0, false);
          }
        );
      },
      function () {
        return answered(status, false, false, 0);
      }
    );
  }
  // 설정 막힘 띠 — 앱이 떠서 이 탭을 거절한다(기다려도 붙지 않는다). 재시작 띠와 같은 자리 · 같은
  // 꼴에 지금 문서를 다시 여는 「새로고침」 링크(풍선 — 저장하지 않은 편집은 사라짐)를 단다. 로그인
  // 띠가 서 있으면 세우지 않는다.
  function showBlocked() {
    if (doc.getElementById(%(banner_id)s)) return;
    var box = doc.getElementById(%(restart_id)s);
    if (box && !box.hasAttribute(%(blocked_mark)s)) {
      box.remove();
      box = null;
    }
    if (!box) {
      var isDark = dark();
      box = doc.createElement("div");
      box.id = %(restart_id)s;
      box.setAttribute(%(blocked_mark)s, "");
      box.setAttribute("role", "alert");
      box.setAttribute("data-react-aria-top-layer", "");
      box.style.cssText = isDark ? %(dark_box_style)s : %(light_box_style)s;
      var text = doc.createElement("span");
      text.textContent = %(blocked)s;
      var link = doc.createElement("a");
      link.textContent = %(refresh_label)s;
      link.title = %(refresh_tip)s;
      link.target = "_self";
      link.href = parentWindow.location.href;
      link.style.cssText = isDark ? %(dark_link_style)s : %(light_link_style)s;
      box.appendChild(text);
      box.appendChild(link);
      doc.body.appendChild(box);
    }
    hideConnectionDialogs();
    watchConnectionDialogs();
  }
  // 이름이 `tick` 의 `root`(앱 루트 요소)와 겹치지 않게 한다 — 겹치면 그 안에서 함수가 가려진다.
  function appRoot() {
    var here = parentWindow.location;
    return probeRoot(%(login_on)s, here.origin, %(prefix)s, here.href);
  }
  var bands = %(bands)s;
  // 공지 물음 — 문지기 있는 서버면 아래 갈래가 채운다(`_NOTICE_POLL`). 틱마다 연결 상태를 넘긴다.
  var noticeTick = null;
%(notice_poll)s
  function showBanner(kind) {
    var band = bands[kind] || bands.legacy;
    var shown = doc.getElementById(%(banner_id)s);
    if (shown) {
      if (shown.getAttribute(%(kind_attr)s) === kind) return;
      shown.remove();
    }
    var isDark = dark();
    var box = doc.createElement("div");
    box.id = %(banner_id)s;
    box.setAttribute(%(kind_attr)s, kind);
    box.setAttribute("role", "alert");
    // 연결 오류 창(react-aria 모달)이 바깥을 inert 로 만들 때 이 띠는 빼게 한다.
    box.setAttribute("data-react-aria-top-layer", "");
    box.style.cssText = isDark ? %(dark_box_style)s : %(light_box_style)s;
    var text = doc.createElement("span");
    text.textContent = band.notice;
    var link = doc.createElement("a");
    link.textContent = band.label;
    link.target = "_self";
    link.href = loginHref(
      %(base)s, %(prefix)s, %(login_path)s,
      parentWindow.location.pathname, parentWindow.location.search
    );
    link.style.cssText = isDark ? %(dark_link_style)s : %(light_link_style)s;
    box.appendChild(text);
    box.appendChild(link);
    doc.body.appendChild(box);
    hideConnectionDialogs();
    watchConnectionDialogs();
  }
  function tick() {
    var root = doc.querySelector('[data-testid="stApp"]');
    var state = root ? root.getAttribute("data-test-connection-state") : null;
    var now = Date.now();
    if (noticeTick) noticeTick(state, now);
    if (!disconnected(state)) {
      since = null;
      lastProbe = null;
      silentSince = null;
      hideBanner();
      hideRestart();
      return;
    }
    if (since === null) since = now;
    // 창이 띠보다 늦게 떠도 띠가 선 동안은 감춘다.
    if (doc.getElementById(%(banner_id)s) || doc.getElementById(%(restart_id)s)) {
      hideConnectionDialogs();
    }
    if (probing || !probeDue(since, lastProbe, now, %(wait_ms)d, %(gap_ms)d)) return;
    probing = true;
    lastProbe = now;
    ask(%(host_config)s, false)
      .then(
        function (answer) {
          if (answer.status === 401 && %(login_on)s) showBanner(bandKind(answer.reason));
          silentSince = null;
          if (answer.status >= 500 && !answer.staged) return answeredServerError(answer.status);
          return answered(answer.status, answer.staged, false, 0);
        },
        function () {
          if (silentSince === null) silentSince = now;
          return answered(null, false, false, now - silentSince);
        }
      )
      .catch(function () {})
      .then(function () {
        probing = false;
      });
  }
  window.setInterval(tick, %(tick_ms)d);
})();
"""


# 공지 물음 갈래 — 문지기 있는 서버의 스크립트에만 끼운다(`_script`). 위 IIFE 안의 `ask` ·
# `parentWindow` 를 쓴다.
_NOTICE_POLL = """
  var noticeSince = null;
  var noticeStopped = false;
  var noticeAsking = false;
  // 마지막으로 알림 칸에 넘긴 꼴의 열쇠(표지 + 판)와 아직 넘기지 못한 꼴.
  var noticeSeen = null;
  var noticePending = null;
  // 받은 꼴을 부모 문서의 알림 칸 입구에 넘긴다. 칸이 아직 서지 않았으면 쥐고 있다가 다음 틱에.
  function handNotice() {
    if (noticePending === null) return;
    var center = parentWindow.__capaAlerts;
    if (!center || typeof center.notice !== "function") return;
    var held = noticePending;
    noticePending = null;
    noticeSeen = held.key;
    try {
      center.notice(held.payload);
    } catch (error) {
      // 알림 칸의 오류가 물음을 멈추지 않게 한다.
    }
  }
  noticeTick = function (state, now) {
    if (!noticeConnected(state)) {
      // 끊긴 동안은 묻지 않는다. 다시 붙은 것은 문지기가 쿠키를 다시 본 핸드셰이크라 401 멈춤도
      // 푼다. 쥐고 있던 꼴도 버린다 — 다시 붙은 회차의 알림 칸 data 가 정본이다(재시작 뒤 옛
      // 표지의 꼴은 알림 칸도 받지 않는다 — data 와 표지가 다른 물음 꼴은 버린다).
      noticeSince = null;
      noticeStopped = false;
      noticePending = null;
      return;
    }
    handNotice();
    if (noticeSince === null) noticeSince = now;
    if (!noticeDue(noticeSince, noticeStopped, noticeAsking, now, %(gap_ms)d)) return;
    noticeSince = now;
    noticeAsking = true;
    ask(%(path)s, true)
      .then(function (answer) {
        var step = noticeStep(answer.status);
        if (step === "stop") noticeStopped = true;
        if (step !== "read") return;
        var read = noticeRead(answer.text);
        if (read === null || read.key === noticeSeen) return;
        noticePending = read;
        handNotice();
      })
      .catch(function () {})
      .then(function () {
        noticeAsking = false;
      });
  };
"""


def notice_poll_part() -> str:
    """공지 물음 갈래(경로 · 간격이 고정) — 문지기 있는 서버의 스크립트에만 끼운다."""
    return _NOTICE_POLL % {"path": script_literal(NOTICE_PATH), "gap_ms": NOTICE_POLL_MS}


def script_literal(value: str) -> str:
    """스크립트에 끼우는 글 — JSON 문자열에 `<` 를 막아 `</script>` 로 끊기지 않게.

    `sso_refresh` 도 같은 규칙으로 끼운다.
    """
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def band_styles(mode: str) -> tuple[str, str]:
    """`mode` 팔레트의 띠 · 링크 서식(강조색 바탕 + 그 위 글자색)."""
    fill = tokens.palette_value(mode, "ACCENT")
    ink = tokens.palette_value(mode, "ACCENT_TEXT")
    shade = tokens.palette_value(mode, "NAV_SHADOW")
    # 양옆 12px 안에서 내용 폭으로 서고 가운데 놓인다 — `left:50%` 로 밀면 내용 맞춤 폭의 상한이
    # 남은 절반이 되어 좁은 창에서 띠가 창의 절반 폭으로 접힌다. 글은 띄어쓰기에서만 줄을 바꿔
    # 한국어 낱말을 가운데서 가르지 않고, 띄어쓰기 없는 긴 글만 아무 데서나 접는다(UI-ACC-02).
    box_style = (
        "position:fixed;top:12px;left:12px;right:12px;margin-inline:auto;width:fit-content;"
        "z-index:2147483647;"
        "max-width:min(720px,calc(100vw - 24px));box-sizing:border-box;padding:12px 16px;"
        f"border-radius:8px;background:{fill};color:{ink};font-family:{tokens.FONT_FAMILY};"
        f"font-size:14px;line-height:1.5;box-shadow:0 6px 24px {shade};"
        "word-break:keep-all;overflow-wrap:anywhere;"
    )
    link_style = (
        f"margin-left:10px;color:{ink};font-weight:700;text-decoration:underline;"
        "white-space:nowrap;"
    )
    return box_style, link_style


def band_texts() -> dict[str, dict[str, str]]:
    """띠 갈래 → (글, 링크 이름). 갈래는 문지기의 까닭 낱말 셋과 머리 없음(`legacy`)이다."""
    return {
        names.REASON_OTHER: {"notice": OTHER_NOTICE, "label": LOGIN_AGAIN_LABEL},
        names.REASON_DENIED: {"notice": DENIED_NOTICE, "label": REGISTER_LABEL},
        names.REASON_UNREAD: {"notice": UNREAD_NOTICE, "label": LOGIN_AGAIN_LABEL},
        "legacy": {"notice": RECONNECT_NOTICE, "label": LOGIN_AGAIN_LABEL},
    }


def _script(cfg: SsoConfig | None) -> str:
    """띠 스크립트 하나 — `cfg` 가 없으면(꺼짐) 로그인 띠 없이 재시작 갈래만 돈다. 문지기가 있는
    서버(`capa_server.py`)면 켜짐 · 꺼짐 모두 공지 물음 갈래를 끼운다(표지는 프로세스에 한 번
    선다)."""
    light_box, light_link = band_styles("light")
    dark_box, dark_link = band_styles("dark")
    prefix = "" if cfg is None else urlsplit(cfg.public_url).path.rstrip("/")
    return _SCRIPT % {
        "banner_id": script_literal(BANNER_ID),
        "restart_id": script_literal(RESTART_BANNER_ID),
        "light_box_style": script_literal(light_box),
        "dark_box_style": script_literal(dark_box),
        "light_link_style": script_literal(light_link),
        "dark_link_style": script_literal(dark_link),
        "bands": json.dumps(band_texts(), ensure_ascii=False).replace("<", "\\u003c"),
        "kind_attr": script_literal(KIND_ATTRIBUTE),
        "reason_header": script_literal(names.REASON_HEADER),
        "base": script_literal("" if cfg is None else cfg.public_url),
        "prefix": script_literal(prefix),
        "login_path": script_literal(names.LOGIN_PATH),
        "login_on": "true" if cfg is not None else "false",
        "host_config": script_literal(HOST_CONFIG_PATH),
        "stage_path": script_literal(STAGE_STATUS_PATH),
        "health_path": script_literal(HEALTH_PATH),
        "timeout_ms": PROBE_TIMEOUT_MS,
        "stage_header": script_literal(STAGE_HEADER),
        "dialog_texts": json.dumps(list(CONNECTION_DIALOG_TEXTS)).replace("<", "\\u003c"),
        "status_widget": script_literal(STATUS_WIDGET_SELECTOR),
        "restart_lead": script_literal(RESTART_LEAD),
        "restart_tail": script_literal(RESTART_TAIL),
        "waiting": script_literal(WAITING_NOTICE),
        "unreachable": script_literal(UNREACHABLE_NOTICE),
        "blocked": script_literal(BLOCKED_NOTICE),
        "blocked_mark": script_literal(BLOCKED_MARK),
        "refresh_label": script_literal(REFRESH_LABEL),
        "refresh_tip": script_literal(REFRESH_TIP),
        "unreachable_ms": UNREACHABLE_AFTER_MS,
        "wait_ms": PROBE_WAIT_MS,
        "gap_ms": PROBE_GAP_MS,
        "tick_ms": TICK_MS,
        "notice_poll": notice_poll_part() if runtime.gate_installed() else "",
    }


def reconnect_script(cfg: SsoConfig) -> str:
    """켜짐 — 다시 붙지 못한 탭의 「다시 로그인」 띠와 서버 재시작 띠(주소 · 문구 · 두 팔레트가
    고정), 문지기가 있으면 공지 물음."""
    return _script(cfg)


def restart_script() -> str:
    """꺼짐 — 서버 재시작 띠(고정 문자열), 문지기가 있으면(`capa_server.py` 로 뜬 꺼짐 서버) 공지
    물음."""
    return _script(None)


def sso_reconnect_scripts(identity: Identity | None) -> tuple[str, ...]:
    """테마 버튼 iframe 에 덧붙일 스크립트 하나. 꺼짐(신원 없음)이면 재시작 띠만이다."""
    if identity is None:
        return (restart_script(),)
    return (reconnect_script(runtime.config()),)
