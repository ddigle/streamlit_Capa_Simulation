# Purpose: 통합인증 경로 다섯(로그인 갱신 포함)·로그인 시작·쿠키·돌아갈 자리 정화·작은 HTML 화면.

"""통합인증 웹 쪽.

경로(`server.sso_routes` 가 붙인다):

- `POST /auth/callback` — IdP 의 form_post. state 쿠키 · id_token 을 검증하고 우리 세션 쿠키를 심어
  303 으로 앱에 들여보낸다. 실패는 진단을 보관하고 **303 → 오류 화면**(PRG — 새로고침해도 폼이 다시
  가지 않는다). 토큰이 맞아도 접속 명단 밖이면 세션을 발급하지 않고 **303 → 거절 화면**이다 — 그
  화면은 로그인 없이 열리므로 진단을 보관하지 않고 사유 코드만 싣는다.
- `GET /auth/sso/login?next=` — 이미 로그인이면 next 로, 아니면 IdP 로(302).
- `GET /auth/sso/logout` — 쿠키를 지우고 세션 묶음(sid)을 폐기 목록에 넣은 뒤 안내 화면. IdP 로
  자동으로 보내지 않는다.
- `GET /auth/sso/error?id=` — 보관한 진단으로 오류 화면. 진단이 없거나 지났으면 질의 `code` 를
  싣되 이 서버가 내는 사유 코드(`allowed_reason_codes`)일 때만이다. `code=not_on_list` 는 거절 화면
  (403)이다.
- `POST /auth/sso/refresh` — 앱 화면에서 사람이 쓰는 동안 세션 쿠키를 다시 발급한다(204). 같은
  출처 · 갱신 머리 · 본문 없음 · 접속 명단 안의 유효한 세션 쿠키가 있어야 하고, 사건 고리에 적지
  않고 누계만 센다.

모든 주소(Location · 링크)의 바탕은 `CAPA_PUBLIC_URL` 이다 — 요청의 Host · `X-Forwarded-*` 는 보지
않는다(앞단을 거치며 포트가 사라지는 일을 막는다). 화면에 싣는 값은 모두 `html.escape` 하고, 토큰 ·
state · nonce · 쿠키 값 · 비밀값 · 클레임 값(이름 · 부서 포함) · IdP 의 `error_description` 원문은
싣지 않는다.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import html
import logging
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem, url_origin
from capa_simulation.auth.identity import Identity, identity_from_cookies
from capa_simulation.auth.tokens import (
    SESSION_LEEWAY,
    STATE_TTL,
    SsoReject,
    clean_text,
    decode_session,
    issue_session,
    issue_state,
    renew_session,
    verify_id_token,
    verify_session,
    verify_state,
)

MAX_BODY_BYTES = 64 * 1024
MAX_FORM_FIELDS = 20
MAX_NEXT_LENGTH = 2048
MAX_LOGIN_ATTEMPTS = 3
ATTEMPT_TTL = 120
MAX_STATE_COOKIES = 5
MAX_SESSION_COOKIE_BYTES = 3584
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

NO_STORE = {"Cache-Control": "no-store"}
# 갱신 경로의 거절 글(짧은 text — 브라우저 스크립트는 상태만 본다).
REFRESH_HEADER_REFUSAL = "refresh header required"
REFRESH_ORIGIN_REFUSAL = "cross-origin refresh refused"
REFRESH_BODY_REFUSAL = "no body expected"
LOGIN_REQUIRED = "login required"
# 접속 명단 밖 — IdP 의 `access_denied`(포털이 거절)와 섞이지 않게 따로 둔 사유 코드와 화면 글.
NOT_ON_LIST = "not_on_list"
NOT_ON_LIST_TITLE = "접속 권한이 없습니다"
NOT_ON_LIST_TEXT = "이 앱을 쓸 수 있는 명단에 없습니다."
HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

_STATE_VALUE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_DIAGNOSTIC_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_IDP_ERROR = re.compile(r"^[a-z_]{1,40}$")
# IdP 가 form_post 로 보낼 수 있는 오류 코드(OAuth 2.0 · OpenID Connect 의 인가 응답 오류). 화면 ·
# 오류 주소의 사유 코드에는 이 이름만 싣고, 그 밖은 `other` 다 — 콜백은 누구나 보낼 수 있어 아무
# 글이나 앱 화면에 띄우는 길이 된다. 받은 원문(꼴이 맞을 때)은 관리자만 보는 사건 기록에 남긴다.
IDP_ERROR_CODES = frozenset(
    {
        "invalid_request",
        "unauthorized_client",
        "access_denied",
        "unsupported_response_type",
        "invalid_scope",
        "server_error",
        "temporarily_unavailable",
        "interaction_required",
        "login_required",
        "account_selection_required",
        "consent_required",
        "invalid_request_uri",
        "invalid_request_object",
        "request_not_supported",
        "request_uri_not_supported",
        "registration_not_supported",
        "invalid_client",
        "invalid_grant",
        "unsupported_grant_type",
    }
)
IDP_ERROR_OTHER = "other"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

SameSite = Literal["lax", "strict", "none"]

_RETRY_REASON = (
    "로그인 시작 정보가 없거나 맞지 않습니다(10분이 지났거나 다른 탭에서 시작) — 다시 시도하세요."
)
_FORM_REASON = "콜백 요청 꼴이 맞지 않습니다."
_TOKEN_REASON = "토큰 꼴이 맞지 않습니다."
_KEY_REASON = "서명 인증서가 맞지 않습니다 — 인증서 교체가 의심됩니다. 아래 지문을 비교하세요."
_TIME_REASON = "시각이 맞지 않습니다(서버 시계가 어긋났거나 오래된 토큰을 다시 보냄)."
_NONCE_REASON = "다른 로그인의 토큰입니다."
_COOKIE_REASON = "로그인 쿠키를 저장하지 못했습니다."
REASON_TEXT: Mapping[str, str] = {
    "bad_content_type": _FORM_REASON,
    "body_too_large": _FORM_REASON,
    "bad_form": _FORM_REASON,
    "state_missing": _RETRY_REASON,
    "state_invalid": _RETRY_REASON,
    "state_mismatch": _RETRY_REASON,
    "state_reused": _RETRY_REASON,
    "token_missing": _TOKEN_REASON,
    "token_malformed": _TOKEN_REASON,
    "alg_not_allowed": _TOKEN_REASON,
    "signing_key_unknown": _KEY_REASON,
    "signature_invalid": _KEY_REASON,
    "aud_mismatch": f"토큰의 aud 가 설정값({names.ENV_CLIENT_ID})과 다릅니다 — 아래 두 값을 보세요",
    "iss_mismatch": f"토큰의 iss 가 설정값({names.ENV_ISSUER})과 다릅니다 — 아래 두 값을 보세요",
    "token_expired": _TIME_REASON,
    "token_not_yet_valid": _TIME_REASON,
    "token_stale": _TIME_REASON,
    "nonce_missing": _NONCE_REASON,
    "nonce_mismatch": _NONCE_REASON,
    "session_cookie_too_large": _COOKIE_REASON,
    "login_loop": _COOKIE_REASON,
    "config_broken": "통합인증 설정을 마치지 못했습니다.",
    NOT_ON_LIST: NOT_ON_LIST_TEXT,
}
# 진단에서 화면에 보여도 되는 칸(비밀 아님)과 그 이름표. 이 목록 밖의 칸은 보이지 않는다.
DIAGNOSTIC_LABELS: tuple[tuple[str, str], ...] = (
    ("expected_iss", "기대한 iss"),
    ("got_iss", "받은 iss"),
    ("expected_aud", "기대한 aud"),
    ("got_aud", "받은 aud"),
    ("iat", "토큰 iat"),
    ("exp", "토큰 exp"),
    ("server_time", "서버 시각"),
    ("claim_names", "받은 클레임 이름"),
    ("alg", "토큰 alg"),
    ("token_x5t", "토큰 x5t"),
    ("token_kid", "토큰 kid"),
    ("configured_x5t", "설정 인증서 x5t"),
    ("at", "기록 시각"),
)

# 화면 다섯의 색 · 서체는 design/tokens 의 두 팔레트에서 온다(손으로 적은 색을 두지 않는다).
# 지금 실행의 테마가 아니라 밝은 · 어두운 팔레트를 둘 다 실어 `prefers-color-scheme` 로 고른다 —
# 이 화면은 Streamlit 바깥이라 앱 테마를 모른다.
_PALETTE_ROLES = (
    ("fg", "TEXT"),
    ("muted", "TEXT_MUTED"),
    ("bg", "SURFACE_PAGE"),
    ("card", "SURFACE"),
    ("line", "BORDER"),
    ("accent", "ACCENT"),
    ("accent-text", "ACCENT_TEXT"),
)
_CSS_BODY = """
body { margin: 0; background: var(--bg); color: var(--fg); line-height: 1.6;
  font-family: var(--font); }
main { max-width: 760px; margin: 48px auto; padding: 28px 32px; background: var(--card);
  border: 1px solid var(--line); border-radius: 12px; }
h1 { font-size: 1.35rem; margin: 0 0 12px; }
p { margin: 8px 0; }
code { font-family: ui-monospace, Consolas, monospace; font-size: .92em; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: .93rem; }
th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left;
  vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
.muted { color: var(--muted); font-size: .9rem; }
a.button { display: inline-block; margin-top: 12px; padding: 8px 16px; border-radius: 8px;
  background: var(--accent); color: var(--accent-text); text-decoration: none; }
"""


@functools.cache
def page_css() -> str:
    """밝은 · 어두운 팔레트 변수 + 본문 규칙.

    tokens 는 여기서만 불러온다 — `auth` 꾸러미가 import 때 Streamlit(테마 모듈이 딸려 온다)을
    끌고 오지 않게. `palette_value` 는 실행 문맥을 보지 않는다.
    """
    from capa_simulation.design import tokens

    def variables(mode: str) -> str:
        return " ".join(
            f"--{name}: {tokens.palette_value(mode, role)};" for name, role in _PALETTE_ROLES
        )

    font = f"--font: {tokens.FONT_FAMILY};"
    return (
        f":root {{ color-scheme: light dark; {variables('light')} {font} }}\n"
        f"@media (prefers-color-scheme: dark) {{ :root {{ {variables('dark')} }} }}"
        f"{_CSS_BODY}"
    )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _utc_now_text(now: int) -> str:
    moment = datetime.fromtimestamp(now, tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def _now() -> int:
    return int(time.time())


def html_page(title: str, body: str, *, status: int) -> HTMLResponse:
    """바깥 자원 없는 작은 한 파일 화면. `body` 는 이미 이스케이프한 HTML 이어야 한다."""
    document = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{page_css()}</style></head>"
        f"<body><main><h1>{_esc(title)}</h1>{body}</main></body></html>"
    )
    return HTMLResponse(document, status_code=status, headers=HTML_HEADERS)


def text_response(text: str, status: int) -> PlainTextResponse:
    return PlainTextResponse(text, status_code=status, headers=NO_STORE)


def method_not_allowed() -> PlainTextResponse:
    """갱신 경로의 POST 밖 메서드 — 405 `Allow: POST`(켜짐은 문지기, 그 밖은 처리기가 답한다)."""
    response = text_response("Method Not Allowed", 405)
    response.headers["Allow"] = "POST"
    return response


def public_link(cfg: SsoConfig, path: str) -> str:
    """앱 안 경로 → 브라우저가 여는 절대 주소. 바탕은 늘 `CAPA_PUBLIC_URL`."""
    return f"{cfg.public_url}{path}"


def redirect(cfg: SsoConfig, path: str, status: int) -> RedirectResponse:
    return RedirectResponse(public_link(cfg, path), status_code=status, headers=NO_STORE)


# --- 출처 ------------------------------------------------------------------------------------


def origin_allowed(origin: str | None, cfg: SsoConfig) -> bool:
    """요청의 Origin 이 `CAPA_PUBLIC_URL` 의 출처와 같은가(websocket · 갱신 경로).

    Streamlit 자체는 localhost · 기계 IP 출처도 받는다 — 운영 출처 하나로 좁힌다. `null` 은 꼴이
    아니라 늘 거절이다.
    """
    expected = cfg.public_origin
    return bool(origin) and bool(expected) and url_origin(origin or "") == expected


def refresh_request_problem(headers: Mapping[str, str], cfg: SsoConfig) -> str | None:
    """갱신 요청의 머리 · 출처 판정 — 거절 글 또는 `None`(통과). 머리 이름은 대소문자를 가리지
    않는다(Starlette `Headers`).

    사용자 정의 머리는 같은 출처 fetch 만 실을 수 있고(폼은 못 싣고 교차 출처는 사전 요청에서
    막힌다), Origin 은 공개 주소 출처여야 하며 `Sec-Fetch-Site` 가 있으면 `same-origin` 이어야 한다.
    """
    if headers.get(names.REFRESH_HEADER.lower()) != names.REFRESH_HEADER_VALUE:
        return REFRESH_HEADER_REFUSAL
    if not origin_allowed(headers.get("origin"), cfg):
        return REFRESH_ORIGIN_REFUSAL
    site = headers.get("sec-fetch-site")
    if site is not None and site != "same-origin":
        return REFRESH_ORIGIN_REFUSAL
    return None


# --- 돌아갈 자리 ------------------------------------------------------------------------------


def _next_is_safe(text: str) -> bool:
    if not text.startswith("/") or text[1:2] in ("/", "\\") or "\\" in text:
        return False
    if _CONTROL.search(text):
        return False
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        return False
    # 점 구획(`/./` · `/../`)은 브라우저가 풀어 `/auth/…` 나 공개 주소의 경로 접두 밖으로 닿는다.
    if any(segment in (".", "..") for segment in parts.path.split("/")):
        return False
    return not (text == "/auth" or text.startswith("/auth/"))


def sanitize_next(raw: str | None) -> str:
    """돌아갈 자리를 앱 안 경로로만 좁힌다. 어기면 `/`.

    규칙: `/` 로 시작 · 둘째 글자가 `/` · `\\` 아님 · `\\` 와 제어문자 없음 · scheme · host 없음 · 2
    KiB 이하 · `/auth/…` 아님 · 경로에 점 구획(`.` · `..`) 없음 · ASCII 만. 퍼센트 인코딩을 한 번 푼
    글에도 같은 규칙을 건다(`/%09/x` · `/%2F%2Fx` · `/%2e%2e/x`). 정상 질의 인자(테마 · 공정 같은 앱
    인자)는 그대로 지킨다.
    """
    if not raw or len(raw) > MAX_NEXT_LENGTH or not raw.isascii():
        return "/"
    if not _next_is_safe(raw) or not _next_is_safe(unquote(raw)):
        return "/"
    return raw


def next_from_scope(path: str, raw_path: bytes | None, query_string: bytes | None) -> str:
    """문지기가 가로챈 요청의 경로 + 질의(퍼센트 인코딩 그대로) → 정화한 돌아갈 자리."""
    try:
        base = (raw_path or path.encode("utf-8")).decode("ascii")
    except UnicodeDecodeError:
        return "/"
    query = (query_string or b"").decode("latin-1")
    return sanitize_next(base + (f"?{query}" if query else ""))


# --- 쿠키 ------------------------------------------------------------------------------------


def set_cookie(
    response: Response, name: str, value: str, *, max_age: int, secure: bool, samesite: SameSite
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite=samesite,
    )


def clear_cookie(response: Response, name: str, *, secure: bool, samesite: SameSite) -> None:
    """심을 때와 같은 이름 · Path · Secure 로 지운다.

    `__Host-` 쿠키는 지울 때도 Secure 여야 지워진다(Starlette 의 기본값은 Secure 없음).
    """
    response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite=samesite)


def set_session_cookie(
    response: Response, cfg: SsoConfig, token: str, *, end: int, now: int
) -> None:
    """세션 쿠키를 심는다. Max-Age 는 세션의 끝 − 지금 + 여유(30초)다 — 서버가 끝 + 여유까지 받는
    동안 브라우저가 쿠키를 먼저 버리지 않게(끝 직후 여유 안의 갱신 요청에도 쿠키가 실린다)."""
    set_cookie(
        response,
        cfg.session_cookie,
        token,
        max_age=max(0, end - now) + SESSION_LEEWAY,
        secure=cfg.secure_cookies,
        samesite="lax",
    )


def clear_session_cookie(response: Response, cfg: SsoConfig) -> None:
    clear_cookie(response, cfg.session_cookie, secure=cfg.secure_cookies, samesite="lax")


def clear_state_cookie(response: Response, name: str) -> None:
    clear_cookie(response, name, secure=True, samesite="none")


def clear_attempt_cookie(response: Response, cfg: SsoConfig) -> None:
    clear_cookie(response, cfg.attempt_cookie, secure=True, samesite="none")


def _attempts(raw: str | None) -> int:
    if raw is None or not raw.isascii() or not raw.isdigit() or len(raw) > 2:
        return 0
    return int(raw)


def _state_cookie_age_order(
    cfg: SsoConfig, cookies: Mapping[str, str], now: int
) -> list[tuple[int, str]]:
    """남은 상태 쿠키(이름, 발급 시각) — 읽지 못하는 것은 가장 오래된 것으로 본다."""
    found: list[tuple[int, str]] = []
    for name, value in cookies.items():
        if not name.startswith(cfg.state_cookie_prefix):
            continue
        try:
            issued = verify_state(value, cfg, now=now).iat
        except SsoReject:
            issued = 0
        found.append((issued, name))
    return sorted(found)


# --- 로그인 시작 -----------------------------------------------------------------------------


def authorize_url(cfg: SsoConfig, *, state: str, nonce: str) -> str:
    """IdP authorize 주소. `urllib.parse` 로 만들고(이어 붙이지 않음) 설정 주소의 질의는 지킨다."""
    parts = urlsplit(cfg.authorize_url)
    ours: dict[str, str] = {
        "client_id": cfg.client_id,
        "response_type": "id_token",
        "response_mode": "form_post",
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope,
        "nonce": nonce,
        "state": state,
    }
    if cfg.resource:
        ours["resource"] = cfg.resource
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in ours
    ]
    query = urlencode([*kept, *ours.items()])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def start_login(cfg: SsoConfig, cookies: Mapping[str, str], next_path: str, now: int) -> Response:
    """IdP 로 보낸다(302) — 상태 쿠키 · 시도 쿠키를 심는다.

    같은 브라우저에서 2분에 3번째면 IdP 로 보내지 않고 되돌이 화면을 낸다.
    """
    attempts = _attempts(cookies.get(cfg.attempt_cookie))
    if attempts >= MAX_LOGIN_ATTEMPTS:
        runtime.record_event("login_fail", level=logging.WARNING, reason="login_loop", loginid="-")
        return loop_page(cfg)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    value = issue_state(cfg, state=state, nonce=nonce, next_path=sanitize_next(next_path), now=now)
    response = RedirectResponse(
        authorize_url(cfg, state=state, nonce=nonce), status_code=302, headers=NO_STORE
    )
    existing = _state_cookie_age_order(cfg, cookies, now)
    surplus = len(existing) + 1 - MAX_STATE_COOKIES
    for _, name in existing[: max(0, surplus)]:
        clear_state_cookie(response, name)
    set_cookie(
        response, cfg.state_cookie(state), value, max_age=STATE_TTL, secure=True, samesite="none"
    )
    set_cookie(
        response,
        cfg.attempt_cookie,
        str(attempts + 1),
        max_age=ATTEMPT_TTL,
        secure=True,
        samesite="none",
    )
    return response


# --- 화면 ------------------------------------------------------------------------------------


def _env_rows(cfg: SsoConfig) -> str:
    problems: dict[str, list[SsoProblem]] = {}
    for problem in cfg.problems:
        problems.setdefault(problem.env, []).append(problem)
    rows: list[str] = []
    for name in names.SSO_ENVIRONMENT:
        present = cfg.env_presence.get(name, False)
        found = problems.pop(name, [])
        if found:
            status = "틀림" if present else "없음"
            reason = " · ".join(problem.reason for problem in found)
        else:
            status = "있음" if present else "없음(선택)"
            reason = ""
        rows.append(
            f"<tr><td><code>{_esc(name)}</code></td><td>{_esc(status)}</td>"
            f"<td>{_esc(reason)}</td></tr>"
        )
    for env, found in problems.items():
        reason = " · ".join(problem.reason for problem in found)
        rows.append(
            f"<tr><td><code>{_esc(env)}</code></td><td>틀림</td><td>{_esc(reason)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>환경변수</th><th>상태</th><th>까닭</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _cert_lines(cfg: SsoConfig) -> str:
    if not cfg.signing_certs:
        return ""
    items = "".join(
        f"<li>x5t <code>{_esc(cert.x5t)}</code> · SHA-256 <code>{_esc(cert.sha256[:16])}…</code>"
        f" · 만료 {_esc(cert.not_after.strftime('%Y-%m-%d'))} · RSA {cert.key_bits}비트</li>"
        for cert in cfg.signing_certs
    )
    return f"<p>서명 인증서</p><ul>{items}</ul>"


def config_page(cfg: SsoConfig, *, status: int, now: int | None = None) -> HTMLResponse:
    """막힘 모드의 설정 화면 — 환경변수 이름 · 상태 · 까닭과 계산한 사실. 값은 보이지 않는다."""
    moment = now if now is not None else _now()
    parts = [
        "<p>이 서버는 통합인증(SSO)을 켜도록 설정됐지만 값이 빠지거나 틀려 앱을 열지 않았습니다. "
        "관리자는 C-DEP 배포 설정의 환경변수 표를 고친 뒤 CI/CD 를 다시 돌리세요.</p>",
        _env_rows(cfg),
    ]
    if cfg.notices:
        notes = "".join(
            f"<li><code>{_esc(item.env)}</code> — {_esc(item.reason)}</li>" for item in cfg.notices
        )
        parts.append(f"<p>알림</p><ul>{notes}</ul>")
    if cfg.redirect_uri:
        parts.append(
            f"<p>계산한 redirect_uri: <code>{_esc(cfg.redirect_uri)}</code><br>"
            '<span class="muted">포털의 Endpoint URL 과 한 글자도 같아야 합니다.</span></p>'
        )
    parts.append(_cert_lines(cfg))
    if any(item.env == names.ENV_ISSUER for item in cfg.problems) and cfg.issuer_candidate:
        parts.append(
            f"<p>{_esc(names.ENV_ISSUER)} 후보(관례일 뿐 — 그대로 넣지 말고 첫 로그인 오류 화면의 "
            f"받은 iss 로 확인): <code>{_esc(cfg.issuer_candidate)}</code></p>"
        )
    parts.append(
        f'<p class="muted">서버 시각 {_esc(_utc_now_text(moment))} · 안내 문서 '
        f"<code>{_esc(names.SETUP_DOC)}</code></p>"
    )
    return html_page("통합인증 설정을 마치지 못했습니다", "".join(parts), status=status)


def reason_text(code: str) -> str:
    if code.startswith("idp_error:"):
        detail = code.split(":", 1)[1]
        if detail == "access_denied":
            return "통합인증이 거절했습니다 — 포털에서 이 앱의 사용 권한을 확인하세요."
        return "통합인증이 거절했습니다."
    if code.startswith(("claim_missing:", "claim_invalid:")):
        return "필요한 클레임이 없거나 꼴이 다릅니다 — 아래 받은 클레임 이름 목록을 보세요."
    return REASON_TEXT.get(code, "로그인하지 못했습니다.")


def allowed_reason_codes(cfg: SsoConfig) -> frozenset[str]:
    """오류 주소의 질의 `code` 로 받아 화면에 실을 수 있는 사유 코드 — 이 서버가 내는 것뿐이다.

    `GET /auth/sso/error?code=` 는 로그인 없이 열리고 링크로 보낼 수 있다. 질의 글을 그대로 실으면
    앱의 출처 · 「로그인하지 못했습니다」 제목 아래 남이 고른 문장(피싱 안내)이 선다. 그래서 정해
    둔 이름(`REASON_TEXT` · IdP 오류 코드 · 설정한 loginid 클레임 이름의 빠짐/꼴)만 받고 그 밖은
    `unknown`.
    """
    return frozenset(
        {
            *REASON_TEXT,
            *(f"idp_error:{code}" for code in (*IDP_ERROR_CODES, IDP_ERROR_OTHER)),
            f"claim_missing:{cfg.claim_loginid}",
            f"claim_invalid:{cfg.claim_loginid}",
        }
    )


def error_page(
    cfg: SsoConfig, code: str, details: Mapping[str, str] | None, *, status: int
) -> HTMLResponse:
    rows = "".join(
        f"<tr><th>{_esc(label)}</th><td><code>{_esc(details[key])}</code></td></tr>"
        for key, label in DIAGNOSTIC_LABELS
        if details and details.get(key)
    )
    body = [
        f"<p>사유 코드 <code>{_esc(code)}</code></p>",
        f"<p>{_esc(reason_text(code))}</p>",
    ]
    if rows:
        body.append(f"<table><tbody>{rows}</tbody></table>")
    retry = public_link(cfg, f"{names.LOGIN_PATH}?{urlencode({'next': '/'})}")
    body.append(f'<a class="button" href="{_esc(retry)}">다시 시도</a>')
    return html_page("로그인하지 못했습니다", "".join(body), status=status)


def denied_page(cfg: SsoConfig, *, status: int) -> HTMLResponse:
    """접속 명단 밖의 거절 화면. 로그인 없이 열리는 주소라 loginid · 이름 · 클레임을 싣지 않는다.

    「다시 확인」 은 로그인 경로다 — 명단에 들어간 뒤 누르면 그대로 들어온다. 통합인증 로그아웃은
    다른 계정으로 바꾸는 길이다(브라우저의 통합인증 로그인이 남아 있으면 IdP 가 묻지 않고 같은
    계정을 준다).
    """
    again = public_link(cfg, f"{names.LOGIN_PATH}?{urlencode({'next': '/'})}")
    body = [f"<p>{_esc(NOT_ON_LIST_TEXT)}</p>"]
    if cfg.access.contact:
        body.append(f"<p>요청: {_esc(cfg.access.contact)}</p>")
    body.append(f'<a class="button" href="{_esc(again)}">다시 확인</a>')
    if cfg.logout_url:
        body.append(
            f'<p class="muted"><a href="{_esc(cfg.logout_url)}">통합인증에서도 로그아웃</a></p>'
        )
    return html_page(NOT_ON_LIST_TITLE, "".join(body), status=status)


def logout_page(cfg: SsoConfig) -> HTMLResponse:
    again = public_link(cfg, "/")
    body = [
        "<p>로그아웃했습니다. 이 앱의 로그인만 끝냈습니다 — 브라우저의 통합인증(AD) 로그인은 "
        "남아 있어 [다시 들어가기]를 누르면 묻지 않고 다시 들어갑니다.</p>",
        f'<a class="button" href="{_esc(again)}">다시 들어가기</a>',
    ]
    if cfg.logout_url:
        body.append(
            f'<p class="muted"><a href="{_esc(cfg.logout_url)}">통합인증에서도 로그아웃</a></p>'
        )
    return html_page("로그아웃했습니다", "".join(body), status=200)


def loop_page(cfg: SsoConfig) -> HTMLResponse:
    body = (
        "<p>로그인이 되풀이되고 있습니다. 로그인 쿠키가 저장되지 않는 것 같습니다 — "
        "주소가 https 인지, 브라우저가 이 사이트의 쿠키를 막지 않는지 확인하세요. 관리자는 실제 "
        f"접속 주소가 설정값(<code>{_esc(names.ENV_PUBLIC_URL)}</code>)과 같은지 봅니다.</p>"
        '<p class="muted">사유 코드 <code>login_loop</code> · 2분 뒤 다시 시도할 수 있습니다.</p>'
    )
    return html_page("로그인이 되풀이됩니다", body, status=200)


# --- 경로 처리기 ------------------------------------------------------------------------------


def mode_guard(cfg: SsoConfig) -> Response | None:
    """꺼짐이면 404(경로가 없는 것처럼), 막힘이면 503 설정 화면. 켜짐이면 None."""
    if cfg.mode is SsoMode.OFF:
        return text_response("Not Found", 404)
    if cfg.mode is SsoMode.BROKEN:
        return config_page(cfg, status=503)
    return None


def _fail(
    cfg: SsoConfig,
    code: str,
    *,
    state: str | None,
    now: int,
    diagnostic: Mapping[str, str] | None = None,
    loginid: str | None = None,
) -> Response:
    """콜백 실패 — 진단을 보관하고 303 → 오류 화면(PRG). 그 상태 쿠키는 지운다."""
    record = {"code": code, "at": _utc_now_text(now)}
    if diagnostic:
        record.update({key: value for key, value in diagnostic.items() if key != "code"})
    diagnostic_id = runtime.keep_diagnostic(record)
    location = f"{names.ERROR_PATH}?{urlencode({'id': diagnostic_id, 'code': code})}"
    response = redirect(cfg, location, 303)
    response.headers["Referrer-Policy"] = "no-referrer"
    if state and _STATE_VALUE.match(state):
        clear_state_cookie(response, cfg.state_cookie(state))
    runtime.record_event("login_fail", level=logging.WARNING, reason=code, loginid=loginid or "-")
    return response


def _deny(cfg: SsoConfig, state_cookie: str, loginid: str) -> Response:
    """토큰은 맞는데 접속 명단 밖 — 세션 없이 303 → 거절 화면(PRG).

    진단을 보관하지 않는다 — 그 화면은 로그인 없이 열리고 loginid · 이름을 싣지 않는다. 상태 쿠키 ·
    시도 쿠키 · 남아 있는 세션 쿠키를 지운다(시도 쿠키가 남으면 「다시 확인」 을 몇 번 누른 사람에게
    「로그인이 되풀이됩니다」 가 잘못 뜬다).
    """
    response = redirect(cfg, f"{names.ERROR_PATH}?{urlencode({'code': NOT_ON_LIST})}", 303)
    response.headers["Referrer-Policy"] = "no-referrer"
    clear_state_cookie(response, state_cookie)
    clear_attempt_cookie(response, cfg)
    clear_session_cookie(response, cfg)
    runtime.record_event("login_denied", level=logging.WARNING, reason=NOT_ON_LIST, loginid=loginid)
    return response


def _fail_now(cfg: SsoConfig, code: str, status: int) -> Response:
    """본문을 읽기 전 실패(415 · 413) — 상태를 모르니 바로 답한다."""
    runtime.record_event("login_fail", level=logging.WARNING, reason=code, loginid="-")
    return error_page(cfg, code, None, status=status)


async def _read_body(request: Request, *, limit: int = MAX_BODY_BYTES) -> bytes | None:
    """본문을 `limit` 바이트(기본 64 KiB)까지만 읽는다. 선언 길이가 넘거나 흐름이 넘치면 None —
    uvicorn 에는 본문 크기 제한이 없다."""
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isdigit() or int(declared) > limit:
            return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            return None
    return bytes(body)


def _parse_form(body: bytes) -> dict[str, str] | None:
    try:
        text = body.decode("utf-8")
        pairs = parse_qsl(text, keep_blank_values=True, max_num_fields=MAX_FORM_FIELDS)
    except (UnicodeDecodeError, ValueError):
        return None
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        return None
    return dict(pairs)


async def callback(request: Request) -> Response:
    """`POST /auth/callback` — IdP form_post 를 받아 세션 쿠키를 심는다."""
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    if request.method != "POST":
        # 즐겨찾기 · 뒤로 가기로 GET 이 오면 앱 첫 화면으로.
        return redirect(cfg, "/", 303)
    now = _now()
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != FORM_CONTENT_TYPE:
        return _fail_now(cfg, "bad_content_type", 415)
    body = await _read_body(request)
    if body is None:
        return _fail_now(cfg, "body_too_large", 413)
    form = _parse_form(body)
    if form is None:
        return _fail(cfg, "bad_form", state=None, now=now)
    state = form.get("state", "")

    idp_error = form.get("error")
    if idp_error is not None:
        received = idp_error if _IDP_ERROR.match(idp_error) else "unknown"
        detail = idp_error if idp_error in IDP_ERROR_CODES else IDP_ERROR_OTHER
        description = clean_text(form.get("error_description", ""), 200)
        runtime.record_event(
            "idp_error", level=logging.WARNING, error=received, description=description
        )
        return _fail(cfg, f"idp_error:{detail}", state=state, now=now)

    state_cookie = cfg.state_cookie(state) if _STATE_VALUE.match(state) else ""
    stored = request.cookies.get(state_cookie) if state_cookie else None
    if stored is None:
        # 뒤로 가기 · 폼 재전송 — 이미 로그인한 브라우저면 조용히 앱으로.
        if isinstance(identity_from_cookies(request.cookies, cfg, now), Identity):
            return redirect(cfg, "/", 303)
        return _fail(cfg, "state_missing", state=state, now=now)
    try:
        claims = verify_state(stored, cfg, now=now)
    except SsoReject:
        return _fail(cfg, "state_invalid", state=state, now=now)
    if not hmac.compare_digest(claims.state.encode("utf-8"), state.encode("utf-8")):
        return _fail(cfg, "state_mismatch", state=state, now=now)
    digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    if not runtime.remember_used_state(digest, claims.exp):
        return _fail(cfg, "state_reused", state=state, now=now)

    try:
        login = verify_id_token(form.get("id_token", ""), cfg, expected_nonce=claims.nonce, now=now)
    except SsoReject as exc:
        return _fail(
            cfg, exc.code, state=state, now=now, diagnostic=exc.diagnostic, loginid=exc.loginid
        )
    runtime.note_login_claims(login.claim_names)
    if not cfg.access.allows(login.loginid):
        return _deny(cfg, state_cookie, login.loginid)

    token, session = issue_session(
        cfg, loginid=login.loginid, name=login.name, dept=login.dept, now=now
    )
    response = redirect(cfg, sanitize_next(claims.next_path), 303)
    set_session_cookie(response, cfg, token, end=session.exp, now=now)
    if len(response.raw_headers[-1][1]) > MAX_SESSION_COOKIE_BYTES:
        return _fail(cfg, "session_cookie_too_large", state=state, now=now, loginid=login.loginid)
    clear_state_cookie(response, state_cookie)
    clear_attempt_cookie(response, cfg)
    response.headers["Referrer-Policy"] = "no-referrer"
    runtime.record_event(
        "login_ok",
        loginid=login.loginid,
        hours=str(cfg.session_hours),
        max_hours=str(cfg.session_max_hours),
        sid=session.sid[:8],
        jti=session.jti[:8],
    )
    if login.name is None:
        runtime.record_event("username_missing", loginid=login.loginid)
    return response


async def login(request: Request) -> Response:
    """`GET /auth/sso/login?next=` — 이미 로그인이면 next 로, 아니면 로그인 시작.

    이미 로그인이면 `auth_time` 을 새로 만들지 않는다 — 새 `auth_time` 은 ADFS 콜백(nonce · state
    검증)에서만 난다(최대 시간 우회를 막는다).
    """
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    now = _now()
    next_path = sanitize_next(request.query_params.get("next"))
    if isinstance(identity_from_cookies(request.cookies, cfg, now), Identity):
        return redirect(cfg, next_path, 303)
    return start_login(cfg, request.cookies, next_path, now)


def _state_cookie_names(cfg: SsoConfig, cookies: Mapping[str, str]) -> Sequence[str]:
    return [name for name in cookies if name.startswith(cfg.state_cookie_prefix)]


async def logout(request: Request) -> Response:
    """`GET /auth/sso/logout` — 쿠키 셋을 지우고 세션 묶음(sid)을 폐기 목록에. IdP 로 보내지 않는다.

    쿠키는 서명 · 꼴만 본다(`decode_session` — 끝 시각은 안 봄). 막 끝난 쿠키로 눌러도 같은 sid 의
    다른 탭 열린 연결 · 옛 토큰을 멈추게. 폐기는 그 묶음의 상한(`auth_time + 최대`) + 여유까지다.
    """
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    now = _now()
    token = request.cookies.get(cfg.session_cookie, "")
    try:
        claims = decode_session(token, cfg, now=now) if token else None
    except SsoReject:
        claims = None
    if claims is not None:
        until = claims.auth_time + cfg.session_max_seconds + SESSION_LEEWAY
        runtime.revoke_session(claims.sid, until=until, now=now)
        runtime.forget_renewal(claims.sid)
        runtime.record_event("logout", loginid=claims.loginid, sid=claims.sid[:8])
    response = logout_page(cfg)
    clear_session_cookie(response, cfg)
    clear_attempt_cookie(response, cfg)
    for name in _state_cookie_names(cfg, request.cookies):
        clear_state_cookie(response, name)
    return response


async def error(request: Request) -> Response:
    """`GET /auth/sso/error?id=` — 보관한 진단으로 오류 화면. id 가 없거나 지났으면 사유 코드만.

    사유 코드가 `not_on_list` 면 거절 화면(403)이다 — 콜백이 진단 없이 이 코드로 보낸다.
    """
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    diagnostic_id = request.query_params.get("id", "")
    record = runtime.get_diagnostic(diagnostic_id) if _DIAGNOSTIC_ID.match(diagnostic_id) else None
    if record is not None:
        code = record.get("code", "unknown")
    else:
        code = request.query_params.get("code", "")
        if code == NOT_ON_LIST:
            return denied_page(cfg, status=403)
        if code not in allowed_reason_codes(cfg):
            code = "unknown"
    return error_page(cfg, code, record, status=400)


async def refresh(request: Request) -> Response:
    """`POST /auth/sso/refresh` — 앱 화면에서 사람이 쓰는 동안 세션 쿠키를 다시 발급한다.

    판정 차례는 모드(꺼짐 404 · 막힘 503) → 메서드(POST 밖은 405 — 꺼짐의 GET 도 다른 경로처럼
    404 이게 GET 을 받아 여기서 답한다) → 머리 · 출처(403) → 본문(400) → 세션 쿠키(401 — 엄격,
    끝은 갱신 표를 보지 않음 · sid 폐기 · 접속 명단도) → 다시 발급이다. 교차 출처 시도가 세션 유효
    여부를 응답 차이로 알아낼 길을 막고, 쿠키 검증(HMAC)보다 싼 것을 먼저 본다. 그 sid 의 직전
    발급(보낸 토큰의 `iat` 와 갱신 표의 발급 시각 가운데 늦은 것)에서 60초 안이거나 상한이라 늘 것이
    없으면 204(쿠키 없음) — 같은 옛 쿠키를 되풀이해 보내도 다시 서명하지 않는다. 다시 발급하면 204 +
    새 세션 쿠키와 갱신 표. 거절은 쿠키를 건드리지 않는다. 사건 고리에도 서버 로그에도 적지 않고
    누계(`runtime.count_refresh`)만 센다 — 5분마다 사람마다 한 줄은 소음이다.
    """
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    if request.method != "POST":
        return method_not_allowed()
    now = _now()
    refusal = refresh_request_problem(request.headers, cfg)
    if refusal is not None:
        runtime.count_refresh("forbidden")
        return text_response(refusal, 403)
    if await _read_body(request, limit=0) is None:
        runtime.count_refresh("bad_request")
        return text_response(REFRESH_BODY_REFUSAL, 400)
    try:
        claims = verify_session(request.cookies.get(cfg.session_cookie, ""), cfg, now=now)
    except SsoReject:
        claims = None
    if (
        claims is None
        or runtime.session_revoked(claims.sid, now=now)
        or not cfg.access.allows(claims.loginid)
    ):
        runtime.count_refresh("unauthorized")
        return text_response(LOGIN_REQUIRED, 401)
    last_issued = runtime.last_renewal_at(claims.sid, now=now)
    renewed = renew_session(cfg, claims, now=now, last_issued=last_issued)
    response = Response(status_code=204, headers=NO_STORE)
    if renewed is None:
        runtime.count_refresh("skipped")
        return response
    token, fresh = renewed
    set_session_cookie(response, cfg, token, end=fresh.exp, now=now)
    runtime.note_renewal(fresh.sid, fresh.exp, now=now)
    runtime.count_refresh("renewed")
    return response
