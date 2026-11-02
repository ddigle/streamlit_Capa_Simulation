# Purpose: 앱 화면에서 사람이 입력하면 통합인증 로그인을 늘리는 갱신 요청 스크립트를 만든다.

"""쓰는 동안 로그인을 늘리는 갱신 요청.

통합인증 로그인은 **마지막 사용 뒤** 유지 시간(`CAPA_SSO_SESSION_HOURS`, 기본 6시간)이 지나면
끝나고, 계속 써도 처음 로그인에서 최대 시간(`CAPA_SSO_SESSION_MAX_HOURS`, 기본 24시간)을 넘지
못한다. 「사용」 을 서버가 알려면 브라우저가 알려야 한다 — websocket 은 핸드셰이크 때 쿠키만 알고,
쿠키를 늘릴 HTTP 응답이 열린 세션에는 거의 없다. 그래서 이 스크립트가 앱 문서(부모 창)의 **사람
입력**(`pointerdown` · `keydown` · `wheel` · `touchstart` — capture · passive, `isTrusted` 인
것만)을 듣고, 다음 차례가 됐을 때만 같은 출처 `POST /auth/sso/refresh` 를 보낸다(사용자 정의 머리
`X-Capa-Sso-Refresh: 1` · 본문 없음 · 쿠키 실음). 서버가 쿠키를 다시 발급하고(204 + Set-Cookie) 열린
연결이 볼 갱신 표를 늘린다(`auth/web.py:refresh`).

- **차례**: 서버가 판정한 답(2xx 다시 발급 · 건너뜀, 4xx 로그인 없음 · 거절) 뒤
  `REFRESH_GAP_MS`(5분), 닿지 못함(망 끊김 · 되돌림 — fetch 거절)과 5xx 뒤 `RETRY_GAP_MS`(30초).
  거절(403)을 짧게 되풀이해도 나아지지 않는다. 보낸 뒤 `STALE_SEND_MS` 안이면 답을 기다리고, 그보다
  오래 답이 없으면(옛 iframe 렐름의 promise 후속이 돌지 않을 때) 낡은 것으로 보고 다시 보낼 수 있다.
- **타이머 없음** — `setInterval` · `setTimeout` · `requestAnimationFrame` 을 쓰지 않는다. 사람이
  쓰지 않으면 유지 시간 뒤 끝난다(사용자 결정). `run_every` 프래그먼트 · 자동 회차는 사람 입력이
  아니다.
- **로그아웃 링크 위 입력은 세지 않는다** — 그 누름이 갱신을 보내 응답이 로그아웃 응답보다 늦게
  닿으면 폐기된 세션 묶음의 쿠키가 브라우저에 다시 선다.
- **차례 상태는 부모 창에**(`STATE_NAME`) 두어 테마 단추 iframe 이 다시 만들어져도 이어진다.
  새로고침은 새 문서라 비고 첫 입력이 바로 보낸다 — 서버의 60초 규칙(`tokens.RENEW_MIN_INTERVAL`)이
  받아 준다. 듣개도 부모 창에 남긴 이름(`HANDLER_NAME`)으로 옛 것을 떼고 새로 단다(옛 iframe 렐름의
  함수는 브라우저가 부르지 않는다 — `cell_press_guard` 와 같은 꼴).
- 요청은 부모 창의 `fetch` · `Date` 로 보낸다 — 요청이 앱 문서에 속해 iframe 이 다시 만들어져도
  끊기지 않고, 브라우저 확인의 가짜 시계가 앱과 같은 시계다. `redirect: "error"` 라 무엇이 와도
  IdP 로 따라가지 않는다. 주소는 지금 창의 출처에 `CAPA_PUBLIC_URL` 의 경로 접두(WebIDE
  `/proxy/<포트>`)와 갱신 경로를 붙인 것이다(서버는 `Origin` 이 `CAPA_PUBLIC_URL` 출처인지 본다).

「다시 로그인」 띠(`sso_reconnect`)와 서로 부르지 않는다 — 이것은 쓰는 동안 늘리기, 띠는 끝난 뒤
알리기다. 테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). 꺼짐이면 싣지 않는다 — iframe 내용 · 요소 순번이 지금과 같다. 켜짐이면 내용이
프로세스 안에서 늘 같다(공개 주소 · 경로 · 상수만 — 회차마다 바뀌면 iframe 이 다시 그려진다).
판정(`// <sso-refresh-rule>`)은 DOM 을 모르는 순수 구획이라 node 시험이 떼어 돌린다
(`tests/test_sso_refresh.py`).
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.components.sso_reconnect import script_literal

# 부모 창에 남기는 지금 듣개 — iframe 이 다시 만들어지면 옛 것을 뗀다.
HANDLER_NAME = "__capaSsoRefresh"
# 부모 창에 남기는 차례 상태 — iframe 이 다시 만들어져도 이어진다.
STATE_NAME = "__capaSsoRefreshState"
# 서버가 판정한 답(2xx · 4xx — 다시 발급 · 건너뜀 · 401 · 403 · 400) 뒤 다음 차례.
REFRESH_GAP_MS = 5 * 60 * 1000
# 닿지 못함(망 끊김 · 되돌림 — fetch 거절) · 5xx 뒤 다음 차례.
RETRY_GAP_MS = 30 * 1000
# 보낸 뒤 이만큼 답이 없으면 「보내는 중」 을 낡은 것으로 본다.
STALE_SEND_MS = 30 * 1000
USE_EVENTS: tuple[str, ...] = ("pointerdown", "keydown", "wheel", "touchstart")
LOGOUT_SELECTOR = f'a[href*="{names.LOGOUT_PATH}"]'

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var events = %(events)s;

// <sso-refresh-rule>
// 이 입력이 「앱을 쓰는 것」 인가 — 사람이 낸 사건(isTrusted)이고 로그아웃 링크 위가 아니다.
function countsAsUse(trusted, onLogoutLink) {
  return trusted === true && !onLogoutLink;
}
// 지금 갱신을 보낼 때인가. 보낸 지 staleMs 안이면(답을 기다림) 아니다. 다음 차례(nextAt)가 없거나
// 됐으면 그렇다. 시계가 gap 보다 더 뒤로 갔으면(nextAt 이 지금보다 gap 넘게 앞) 기다리지 않는다.
function refreshDue(nextAt, sentAt, now, gapMs, staleMs) {
  if (sentAt !== null && now - sentAt >= 0 && now - sentAt < staleMs) return false;
  if (nextAt === null) return true;
  if (nextAt - now > gapMs) return true;
  return now >= nextAt;
}
// 답을 받은 뒤 다음 차례 — 서버가 판정한 답(2xx 다시 발급 · 건너뜀, 4xx 로그인 없음 · 거절)은
// gap 뒤, 닿지 못함(0 — 망 끊김 · 되돌림)과 5xx 는 retry 뒤. 거절(403)을 30초마다 되풀이해도
// 나아지지 않는다.
function nextRefreshAt(status, now, gapMs, retryMs) {
  if (status >= 200 && status < 500) return now + gapMs;
  return now + retryMs;
}
// </sso-refresh-rule>

  var state = parentWindow[%(state)s];
  if (!state || typeof state !== "object") {
    state = { nextAt: null, sentAt: null };
    parentWindow[%(state)s] = state;
  }
  var url = parentWindow.location.origin + %(prefix)s + %(path)s;
  function now() { return parentWindow.Date.now(); }
  function finish(status) {
    state.sentAt = null;
    state.nextAt = nextRefreshAt(status, now(), %(gap_ms)d, %(retry_ms)d);
  }
  function send() {
    state.sentAt = now();
    var headers = {};
    headers[%(header)s] = %(header_value)s;
    try {
      parentWindow.fetch(url, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: headers
      }).then(function (response) { finish(response.status); }, function () { finish(0); });
    } catch (error) {
      finish(0);
    }
  }
  function onUse(event) {
    var target = event.target;
    var onLogout = !!(target && typeof target.closest === "function" && target.closest(%(logout)s));
    if (!countsAsUse(event.isTrusted, onLogout)) return;
    if (!refreshDue(state.nextAt, state.sentAt, now(), %(gap_ms)d, %(stale_ms)d)) return;
    send();
  }
  var previous = parentWindow[%(handler)s];
  var index;
  if (typeof previous === "function") {
    for (index = 0; index < events.length; index += 1) {
      doc.removeEventListener(events[index], previous, true);
    }
  }
  parentWindow[%(handler)s] = onUse;
  for (index = 0; index < events.length; index += 1) {
    doc.addEventListener(events[index], onUse, { capture: true, passive: true });
  }
})();
"""


def refresh_script(cfg: SsoConfig) -> str:
    """사람 입력으로 로그인을 늘리는 스크립트(경로 접두 · 경로 · 머리 · 상수만이라 늘 같다)."""
    prefix = urlsplit(cfg.public_url).path.rstrip("/")
    return _SCRIPT % {
        "events": json.dumps(list(USE_EVENTS)),
        "state": script_literal(STATE_NAME),
        "handler": script_literal(HANDLER_NAME),
        "prefix": script_literal(prefix),
        "path": script_literal(names.REFRESH_PATH),
        "header": script_literal(names.REFRESH_HEADER),
        "header_value": script_literal(names.REFRESH_HEADER_VALUE),
        "logout": script_literal(LOGOUT_SELECTOR),
        "gap_ms": REFRESH_GAP_MS,
        "retry_ms": RETRY_GAP_MS,
        "stale_ms": STALE_SEND_MS,
    }


def sso_refresh_scripts(identity: Identity | None) -> tuple[str, ...]:
    """테마 버튼 iframe 에 덧붙일 스크립트. 꺼짐(신원 없음)이면 빈 튜플 — iframe 내용이 그대로다."""
    if identity is None:
        return ()
    return (refresh_script(runtime.config()),)
