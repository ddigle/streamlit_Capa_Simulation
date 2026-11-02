# Purpose: 만료·로그아웃으로 다시 붙지 못한 탭에 「다시 로그인」 띠를 띄우는 스크립트를 만든다.

"""다시 붙지 못한 탭의 「다시 로그인」 띠.

문지기(`auth/gate.py`)는 세션이 만료됐거나 로그아웃한(폐기 목록) 탭의 websocket 을 다음 메시지에서
닫고, 다시 붙으려는 핸드셰이크와 `/_stcore/host-config` 를 거절한다(403 · 401). 쿠키는 HttpOnly
이고 만료 시각에 브라우저가 지우며, 로그아웃은 쿠키를 지운다 — 그래서 다시 붙지 못한다. Streamlit
프런트는 그때 머리 띠의 「CONNECTING」 과 영어 창 「Connection failed with status 401.」 만 보이고,
화면에는 만료 전 내용이 남는다. 사람에게는 다음 할 일이 보이지 않는다(검토 실측 — 모달을 닫아도
CONNECTING 이 이어진다).

이 스크립트가 그 빈자리를 메운다. 앱 루트(`stApp`)의 연결 상태 표지(`data-test-connection-state`)를
1초마다 읽어, 붙어 있지 않은 채 `PROBE_WAIT_MS` 가 지나면 같은 출처의 `/_stcore/host-config` 에
쿠키를 실어 묻는다(`PROBE_GAP_MS` 마다 한 번). **401 이면** 로그인이 끝난 것이므로 화면 맨 위에
한국어 띠와 「다시 로그인」 링크를 세운다. 그 밖(망 끊김 · 서버 재시작 — 200 이나 연결 실패)은
Streamlit 이 스스로 다시 붙으므로 아무것도 하지 않는다. 다시 붙으면(다른 탭에서 다시 로그인한 뒤
등) 띠를 걷는다.

**자동으로 IdP 로 보내지 않는다.** 로그아웃은 이 브라우저의 앱 로그인을 끝내는 일이다 — 열어 둔
다른 탭이 `run_every` 프래그먼트 회차나 클릭 하나로 저절로 다시 로그인하면 로그아웃이 조용히
되돌려진다. 사람이 띠를 읽고 「다시 로그인」 을 누른다(만료 멈춤 화면과 같은 안내 — 다시 로그인하면
저장하지 않은 편집은 사라진다). 띠는 Streamlit 의 연결 오류 창보다 위에 선다(창의 배경이 누름을
막지 않게).

링크는 `CAPA_PUBLIC_URL` 바탕의 `/auth/sso/login?next=<지금 경로 + 질의>` 다 — 경로에서 공개 주소의
경로 접두(WebIDE `/proxy/<포트>`)를 떼는 것은 `sso_identity.return_path` 와 같은 규칙이고, 서버가
`next` 를 다시 정화한다. 물음은 지금 창의 출처로 보낸다(공개 주소가 다른 출처면 쿠키가 실리지
않는다).

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). 꺼짐이면 싣지 않는다 — iframe 내용 · 요소 순번이 지금과 같다. 켜짐이면 내용이
프로세스 안에서 늘 같다(공개 주소 · 문구가 고정). 타이머는 iframe 창의 것이라 iframe 이 사라지면
같이 멈춘다. 판정(`// <sso-reconnect-rule>`)은 DOM 을 모르는 순수 구획이라 node 시험이 떼어
돌린다(`tests/test_sso_reconnect.py`).

**비공식 경로다.** Streamlit 1.63 프런트의 연결 상태 표지에 기댄다. 판올림으로 표지가 사라지면 띠가
서지 않을 뿐 나머지는 그대로다 — 올릴 때 만료 · 로그아웃 뒤 다시 붙기를 브라우저로 한 번 본다.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.components.sso_identity import LOGIN_AGAIN_LABEL
from capa_simulation.design import tokens

BANNER_ID = "capa-sso-reconnect"
# 붙어 있지 않은 채 이만큼 지나야 묻는다 — 잠깐의 끊김(재실행 · 망 흔들림)에는 묻지 않는다.
PROBE_WAIT_MS = 3_000
# 묻는 사이 — 끊긴 동안 이만큼마다 한 번.
PROBE_GAP_MS = 10_000
TICK_MS = 1_000
HOST_CONFIG_PATH = "/_stcore/host-config"
RECONNECT_NOTICE = (
    "통합인증 로그인이 끝나 이 탭이 서버에 다시 붙지 못합니다(로그인 시간이 지났거나 "
    "이 브라우저에서 로그아웃했습니다). 다시 로그인하면 이 탭에서 저장하지 않은 편집은 사라집니다."
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
// 다시 로그인 주소 — 공개 주소 + 로그인 경로 + next(지금 경로에서 공개 주소의 경로 접두를 뗀
// 것 + 질의).
function loginHref(base, prefix, loginPath, pathname, search) {
  var path = pathname || "/";
  if (prefix && (path === prefix || path.indexOf(prefix + "/") === 0)) {
    path = path.slice(prefix.length) || "/";
  }
  return base + loginPath + "?next=" + encodeURIComponent(path + (search || ""));
}
// </sso-reconnect-rule>

  var since = null;
  var lastProbe = null;
  var probing = false;
  function hideBanner() {
    var box = doc.getElementById(%(banner_id)s);
    if (box) box.remove();
  }
  function showBanner() {
    if (doc.getElementById(%(banner_id)s)) return;
    var box = doc.createElement("div");
    box.id = %(banner_id)s;
    box.setAttribute("role", "alert");
    box.style.cssText = %(box_style)s;
    var text = doc.createElement("span");
    text.textContent = %(notice)s;
    var link = doc.createElement("a");
    link.textContent = %(label)s;
    link.target = "_self";
    link.href = loginHref(
      %(base)s, %(prefix)s, %(login_path)s,
      parentWindow.location.pathname, parentWindow.location.search
    );
    link.style.cssText = %(link_style)s;
    box.appendChild(text);
    box.appendChild(link);
    doc.body.appendChild(box);
  }
  function tick() {
    var root = doc.querySelector('[data-testid="stApp"]');
    var state = root ? root.getAttribute("data-test-connection-state") : null;
    var now = Date.now();
    if (!disconnected(state)) {
      since = null;
      lastProbe = null;
      hideBanner();
      return;
    }
    if (since === null) since = now;
    if (probing || !probeDue(since, lastProbe, now, %(wait_ms)d, %(gap_ms)d)) return;
    probing = true;
    lastProbe = now;
    var probe = parentWindow.location.origin + %(prefix)s + %(host_config)s;
    fetch(probe, { credentials: "same-origin", cache: "no-store" })
      .then(function (response) {
        if (response.status === 401) showBanner();
      })
      .catch(function () {})
      .then(function () {
        probing = false;
      });
  }
  window.setInterval(tick, %(tick_ms)d);
})();
"""


def _js(value: str) -> str:
    """스크립트에 끼우는 글 — JSON 문자열에 `<` 를 막아 `</script>` 로 끊기지 않게."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def reconnect_script(cfg: SsoConfig) -> str:
    """다시 붙지 못한 탭에 「다시 로그인」 띠를 세우는 스크립트(공개 주소 · 문구가 고정)."""
    prefix = urlsplit(cfg.public_url).path.rstrip("/")
    fill = tokens.palette_value("light", "ACCENT")
    ink = tokens.palette_value("light", "ACCENT_TEXT")
    box_style = (
        "position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;"
        "max-width:min(720px,calc(100vw - 24px));box-sizing:border-box;padding:12px 16px;"
        f"border-radius:8px;background:{fill};color:{ink};font-family:{tokens.FONT_FAMILY};"
        "font-size:14px;line-height:1.5;box-shadow:0 6px 24px rgba(0,0,0,.28);"
    )
    link_style = (
        f"margin-left:10px;color:{ink};font-weight:700;text-decoration:underline;"
        "white-space:nowrap;"
    )
    return _SCRIPT % {
        "banner_id": _js(BANNER_ID),
        "box_style": _js(box_style),
        "link_style": _js(link_style),
        "notice": _js(RECONNECT_NOTICE),
        "label": _js(LOGIN_AGAIN_LABEL),
        "base": _js(cfg.public_url),
        "prefix": _js(prefix),
        "login_path": _js(names.LOGIN_PATH),
        "host_config": _js(HOST_CONFIG_PATH),
        "wait_ms": PROBE_WAIT_MS,
        "gap_ms": PROBE_GAP_MS,
        "tick_ms": TICK_MS,
    }


def sso_reconnect_scripts(identity: Identity | None) -> tuple[str, ...]:
    """테마 버튼 iframe 에 덧붙일 스크립트. 꺼짐(신원 없음)이면 빈 튜플 — iframe 내용이 그대로다."""
    if identity is None:
        return ()
    return (reconnect_script(runtime.config()),)
