# Purpose: 통합인증 경로 여섯(갱신 · 스스로 등록 포함)·로그인 시작·쿠키·돌아갈 자리 정화·HTML 화면.

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
  싣되 이 서버가 내는 사유 코드(`allowed_reason_codes`)일 때만이다. 거절 갈래(`DENIED_CODES` —
  `not_on_list` · `list_unread` · `registered` · `register_failed`)는 코드가 갈래만 고르고 **어느
  꼴인지는 지금 상태**(명단을 읽었나 · 그 브라우저의 거절 표 · 그 계정이 지금 명단에 드나)가 정한다
  —
  로그인 없이 열리는 주소라 코드만 넣어 연 사람에게 「등록했습니다」 를 보이지 않는다. 포털 거절
  (`idp_error:access_denied`)은 오류 화면이 아니라 같은 틀의 거절 꼴이다(403).
- `POST /auth/sso/refresh` — 앱 화면에서 사람이 쓰는 동안 세션 쿠키를 다시 발급한다(204). 같은
  출처 · 갱신 머리 · 본문 없음 · 접속 명단 안의 유효한 세션 쿠키가 있어야 하고, 사건 고리에 적지
  않고 누계만 센다.
- `POST /auth/sso/register` — 거절 화면의 「접속 권한 신청」. 같은 출처 · 작은 폼 · 거절 표 · 표에
묶인
  숨은 표지가 있어야 하고, 신원은 거절 표에서만 꺼낸다(폼 칸의 계정 · 등급은 보지 않는다). 스레드
  풀에서 S3 명단에 넣은 뒤 303(PRG — 새로고침해도 다시 가지 않는다). GET 은 거절 화면으로 303.

**거절 표**(`tokens.issue_denied` — 15분 · HttpOnly · SameSite=Lax)는 콜백이 명단 밖일 때만 심는다.
거절 화면은 그 표가 있는 브라우저에만 본인 계정을 보인다(2026-11-13 보드 D2 답) — 주소만 연 사람 ·
15분 지난 사람은 값 없이 「로그인하고 신청」 이다. 로그인 성공 · 로그아웃이 표를 지운다.

모든 주소(Location · 링크)의 바탕은 `CAPA_PUBLIC_URL` 이다 — 요청의 Host · `X-Forwarded-*` 는 보지
않는다(앞단을 거치며 포트가 사라지는 일을 막는다). 화면에 싣는 값은 모두 `html.escape` 하고, 토큰 ·
state · nonce · 쿠키 값 · 비밀값 · 클레임 값(이름 · 부서 포함) · IdP 의 `error_description` 원문은
싣지 않는다 — 예외는 거절 표가 있는 그 브라우저의 거절 갈래 화면에 보이는 본인 계정 · 이름 하나다.
거절 갈래 · 포털 거절 화면은 공통 틀(`auth/page_frame.py`)로 그린다.
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

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from capa_simulation import settings
from capa_simulation.auth import access_store, names, page_frame, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem, url_origin
from capa_simulation.auth.identity import Identity, identity_from_cookies
from capa_simulation.auth.page_frame import Form, Frame, Link
from capa_simulation.auth.tokens import (
    DENIED_TTL,
    SESSION_LEEWAY,
    STATE_TTL,
    DeniedClaims,
    SsoReject,
    VerifiedLogin,
    clean_text,
    decode_session,
    denied_form_mark,
    issue_denied,
    issue_session,
    issue_state,
    renew_session,
    verify_denied,
    verify_id_token,
    verify_session,
    verify_state,
)
from capa_simulation.io.s3_small import S3Failure

MAX_BODY_BYTES = 64 * 1024
MAX_FORM_FIELDS = 20
MAX_NEXT_LENGTH = 2048
MAX_LOGIN_ATTEMPTS = 3
ATTEMPT_TTL = 120
MAX_STATE_COOKIES = 5
MAX_SESSION_COOKIE_BYTES = 3584
# 「접속 권한 신청」 폼 본문의 끝 — 숨은 표지 하나뿐이다.
MAX_REGISTER_BODY_BYTES = 4096
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

NO_STORE = {"Cache-Control": "no-store"}
# 갱신 경로의 거절 글(짧은 text — 브라우저 스크립트는 상태만 본다).
REFRESH_HEADER_REFUSAL = "refresh header required"
REFRESH_ORIGIN_REFUSAL = "cross-origin refresh refused"
REGISTER_ORIGIN_REFUSAL = "cross-origin request refused"
REGISTER_FORM_REFUSAL = "form refused"
REFRESH_BODY_REFUSAL = "no body expected"
LOGIN_REQUIRED = "login required"
# 접속 명단 밖 — IdP 의 `access_denied`(포털이 거절)와 섞이지 않게 따로 둔 사유 코드와 화면 글.
NOT_ON_LIST = "not_on_list"
NOT_ON_LIST_TITLE = "접속 권한이 없습니다"
NOT_ON_LIST_TEXT = "이 앱을 쓸 수 있는 명단에 없습니다."
# S3 명단을 아직 한 번도 읽지 못해(관리자만 들어옴) 명단에 있는지 확인하지 못한 거절의 사유 코드와
# 화면 글. 사람이 명단에 있는지는 말하지 않는다 — 읽지 못했으니 모른다.
LIST_UNREAD = "list_unread"
LIST_UNREAD_TITLE = "접속 권한을 확인하지 못했습니다"
LIST_UNREAD_TEXT = "접속 명단을 읽지 못했습니다 — 잠시 뒤 다시 확인하세요."
# 「접속 권한 신청」 의 결과 — 등록함(이미 있음 포함) · 저장 실패. 거절 갈래의 넷이다.
REGISTERED = "registered"
REGISTER_FAILED = "register_failed"
DENIED_CODES = (NOT_ON_LIST, LIST_UNREAD, REGISTERED, REGISTER_FAILED)
# 포털(통합인증)이 앱 사용을 막은 IdP 오류 — 오류 화면이 아니라 거절 꼴 화면이다.
PORTAL_REFUSED = "idp_error:access_denied"

# 거절 갈래 · 포털 거절 화면의 글(공통 틀 — 「다음에 할 일」 문장은 앱 밖 화면 예외, 6-11 b1 ·
# 2026-11-13 보드 D8 「넷까지」). `{account}` 는 거절 표가 있는 브라우저에만 서는 본인 계정이다.
REGISTER_LABEL = "접속 권한 신청"
CHECK_AGAIN_LABEL = "다시 확인"
SIGN_IN_TO_APPLY_LABEL = "로그인하고 신청"
OTHER_ACCOUNT_LABEL = "다른 계정으로 로그인"
RECONNECT_LABEL = "다시 접속"
RETRY_LABEL = "다시 시도"
DENIED_ACCOUNT_TEXT = "계정 {account} 은 이 앱의 접속 명단에 없습니다."
DENIED_REGISTER_STEP = "「접속 권한 신청」 을 누르면 바로 명단에 등록됩니다."
DENIED_OTHER_STEP = "다른 계정으로 들어가려면 「다른 계정으로 로그인」 을 누르세요."
DENIED_NO_TICKET_TEXT = "신청하려면 먼저 로그인해 계정을 확인합니다."
SEND_NOTE_STEP = "아래 글을 문의처로 보내 주세요."
NOTE_LABEL = "문의처로 보낼 글 — 한 번 누르면 통째로 골라집니다"
ADMIN_TYPO_DIAGNOSTIC = (
    "모두가 이 화면을 본다면 관리자 목록 칸(CAPA_ACCESS_ADMINS)에 위 계정이 철자 그대로 들었는지 "
    "확인합니다."
)
REGISTERED_TITLE = "등록했습니다"
REGISTERED_TEXT = (
    "계정 {account} 을 접속 명단에 넣었습니다. 다시 접속하면 처음 가려던 화면으로 들어갑니다."
)
REGISTER_FAILED_TITLE = "접속 명단에 넣지 못했습니다"
REGISTER_FAILED_TEXT = "계정 {account} 을 명단에 넣는 중 서버가 저장하지 못했습니다."
LIST_UNREAD_WAIT_TEXT = (
    "서버가 접속 명단을 읽지 못해 지금은 확인할 수 없습니다. 권한 문제가 아닙니다."
)
LIST_UNREAD_WAIT_STEP = "1분 뒤 「다시 확인」 을 누르세요. 계속되면 문의처에 알려 주세요."
LIST_UNREAD_ADMIN_TEXT = "관리자가 서버 설정을 고쳐야 열립니다. 권한 문제가 아닙니다."
LIST_UNREAD_ADMIN_STEP = "문의처에 알려 주세요."
PORTAL_TITLE = "통합인증이 이 앱 사용을 막았습니다"
PORTAL_TEXT = (
    "앱의 접속 명단보다 앞 단계에서 통합인증(포털)이 이 계정의 앱 사용을 허락하지 않았습니다. "
    "앱 관리자가 아니라 포털 권한 담당에게 신청해야 합니다."
)
PORTAL_STEPS = (
    "포털 권한 담당에게 이 앱의 사용 권한을 신청하세요.",
    "모르겠으면 문의처에 아래 참고 번호를 알려 주세요.",
)
PORTAL_DIAGNOSTIC = "통합인증이 보낸 거절 글 원문은 Admin 「통합인증 점검」 최근 사건에 있습니다."

HTML_HEADERS = {
    "Cache-Control": "no-store",
    # 폼 POST 는 같은 출처로만(`form-action` 은 `default-src` 를 물려받지 않는다).
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
# 폼이 있는 거절 화면 — `no-referrer` 면 브라우저가 폼 POST 의 Origin 을 `null` 로 보낸다(그
# 주소에는
# 사유 코드만 있어 새는 값이 없다).
FORM_REFERRER_POLICY = "same-origin"

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
# 오류 화면 제목. 모르는 사유 코드는 본문에 이 말을 다시 적지 않고 제목과 사유 코드만 둔다.
ERROR_PAGE_TITLE = "로그인하지 못했습니다"
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
    LIST_UNREAD: LIST_UNREAD_TEXT,
    REGISTERED: REGISTERED_TITLE,
    REGISTER_FAILED: REGISTER_FAILED_TITLE,
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
a { color: var(--accent); }
a.button { display: inline-block; margin-top: 12px; padding: 8px 16px; border-radius: 8px;
  background: var(--accent); color: var(--accent-text); text-decoration: none; }
"""


@functools.cache
def page_css() -> str:
    """밝은 · 어두운 팔레트 변수(공통 틀과 한 벌 — `page_frame.palette_css`) + 본문 규칙."""
    return f"{page_frame.palette_css()}{_CSS_BODY}"


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


def clear_denied_cookie(response: Response, cfg: SsoConfig) -> None:
    clear_cookie(response, cfg.denied_cookie, secure=cfg.secure_cookies, samesite="lax")


def read_denied(cfg: SsoConfig, cookies: Mapping[str, str], now: int) -> DeniedClaims | None:
    """그 브라우저의 거절 표 — 없거나 위조 · 만료 · 다른 쓰임 토큰이면 `None`(값 없는 화면이
    된다)."""
    token = cookies.get(cfg.denied_cookie)
    if not token:
        return None
    try:
        return verify_denied(token, cfg, now=now)
    except SsoReject:
        return None


def set_denied_cookie(
    response: Response, cfg: SsoConfig, login: VerifiedLogin, next_path: str, now: int
) -> None:
    """거절 표를 심는다(15분). 쿠키가 브라우저 한도에 걸리면 돌아갈 자리를 `/` 로, 그래도 넘치면
    이름 · 부서를 빼고 다시 만든다 — 브라우저가 큰 쿠키를 말없이 버리면 표가 없는 꼴이 된다."""
    attempts = (
        (next_path, login.name, login.dept),
        ("/", login.name, login.dept),
        ("/", None, None),
    )
    token = ""
    for path, name, dept in attempts:
        token, _ = issue_denied(
            cfg, loginid=login.loginid, name=name, dept=dept, next_path=path, now=now
        )
        if len(cfg.denied_cookie) + len(token) <= MAX_SESSION_COOKIE_BYTES:
            break
    set_cookie(
        response,
        cfg.denied_cookie,
        token,
        max_age=DENIED_TTL,
        secure=cfg.secure_cookies,
        samesite="lax",
    )


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
    """사유 코드의 한 줄 설명. 모르는 코드는 빈 글이다 — 화면 제목(`ERROR_PAGE_TITLE`)을 본문에서
    거듭하지 않는다."""
    if code.startswith("idp_error:"):
        detail = code.split(":", 1)[1]
        if detail == "access_denied":
            return "통합인증이 거절했습니다 — 포털에서 이 앱의 사용 권한을 확인하세요."
        return "통합인증이 거절했습니다."
    if code.startswith(("claim_missing:", "claim_invalid:")):
        return "필요한 클레임이 없거나 꼴이 다릅니다 — 아래 받은 클레임 이름 목록을 보세요."
    return REASON_TEXT.get(code, "")


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
    body = [f"<p>사유 코드 <code>{_esc(code)}</code></p>"]
    reason = reason_text(code)
    if reason:
        body.append(f"<p>{_esc(reason)}</p>")
    if rows:
        body.append(f"<table><tbody>{rows}</tbody></table>")
    retry = public_link(cfg, f"{names.LOGIN_PATH}?{urlencode({'next': '/'})}")
    body.append(f'<a class="button" href="{_esc(retry)}">다시 시도</a>')
    return html_page(ERROR_PAGE_TITLE, "".join(body), status=status)


def frame_response(frame: Frame, *, status: int, now: int) -> HTMLResponse:
    """공통 틀 화면 하나. 폼이 있는 화면만 Referrer-Policy 를 같은 출처로
    둔다(`FORM_REFERRER_POLICY`)."""
    response = HTMLResponse(
        page_frame.render(frame, now=now), status_code=status, headers=HTML_HEADERS
    )
    if isinstance(frame.primary, Form):
        response.headers["Referrer-Policy"] = FORM_REFERRER_POLICY
    return response


def _login_link(cfg: SsoConfig, label: str, next_path: str = "/") -> Link:
    return Link(
        label,
        public_link(cfg, f"{names.LOGIN_PATH}?{urlencode({'next': sanitize_next(next_path)})}"),
    )


def _contact_email() -> str:
    """문의 줄의 메일 — 앱 정보 카드와 같은 칸(보드 D7 「기존 두 칸」). 창구 글은
    `cfg.access.contact`."""
    return settings.app_contact_email()


def _other_account(cfg: SsoConfig) -> tuple[Link, ...]:
    return (Link(OTHER_ACCOUNT_LABEL, cfg.logout_url),) if cfg.logout_url else ()


def _note(ticket: DeniedClaims, code: str, now: int) -> str:
    return page_frame.request_note(account=ticket.loginid, name=ticket.name, code=code, now=now)


def not_on_list_frame(cfg: SsoConfig, ticket: DeniedClaims | None, now: int) -> Frame:
    """명단 밖 — 표가 있으면 본인 계정과 「접속 권한 신청」(넣지 못하는 서버면 신청 글), 없으면
    값 없이 「로그인하고 신청」."""
    if ticket is None:
        return Frame(
            title=NOT_ON_LIST_TITLE,
            chip="denied",
            lead=(NOT_ON_LIST_TEXT, DENIED_NO_TICKET_TEXT),
            primary=_login_link(cfg, SIGN_IN_TO_APPLY_LABEL),
            secondary=_other_account(cfg),
            reference=NOT_ON_LIST,
            contact_email=_contact_email(),
            contact_text=cfg.access.contact,
        )
    other = _other_account(cfg)
    if access_store.can_register(cfg):
        steps = (DENIED_REGISTER_STEP, *((DENIED_OTHER_STEP,) if other else ()))
        primary: Link | Form = Form(
            REGISTER_LABEL,
            public_link(cfg, names.REGISTER_PATH),
            (("t", denied_form_mark(cfg, ticket.jti)),),
        )
        note = ""
    else:
        steps = (SEND_NOTE_STEP, *((DENIED_OTHER_STEP,) if other else ()))
        primary = _login_link(cfg, CHECK_AGAIN_LABEL, ticket.next_path)
        note = _note(ticket, NOT_ON_LIST, now)
    secondary = (
        other
        if isinstance(primary, Link)
        else (
            _login_link(cfg, CHECK_AGAIN_LABEL, ticket.next_path),
            *other,
        )
    )
    return Frame(
        title=NOT_ON_LIST_TITLE,
        chip="denied",
        lead=(DENIED_ACCOUNT_TEXT,),
        steps=steps,
        primary=primary,
        secondary=secondary,
        note_label=NOTE_LABEL if note else "",
        note_text=note,
        reference=NOT_ON_LIST,
        diagnostics=(ADMIN_TYPO_DIAGNOSTIC,),
        account=ticket.loginid,
        contact_email=_contact_email(),
        contact_text=cfg.access.contact,
    )


def list_unread_frame(cfg: SsoConfig, ticket: DeniedClaims | None, now: int) -> Frame:
    """명단을 한 번도 읽지 못함 — 권한 문제가 아니다. 잠시 뒤 풀리는 때와 관리자가 고칠 때를
    가른다."""
    needs_admin = access_store.unread_needs_admin(cfg)
    text, step = (
        (LIST_UNREAD_ADMIN_TEXT, LIST_UNREAD_ADMIN_STEP)
        if needs_admin
        else (LIST_UNREAD_WAIT_TEXT, LIST_UNREAD_WAIT_STEP)
    )
    note = "" if ticket is None else _note(ticket, LIST_UNREAD, now)
    return Frame(
        title=LIST_UNREAD_TITLE,
        chip="maintenance",
        lead=(text,),
        steps=(step,),
        primary=_login_link(cfg, CHECK_AGAIN_LABEL, "/" if ticket is None else ticket.next_path),
        secondary=_other_account(cfg),
        note_label=NOTE_LABEL if note else "",
        note_text=note,
        reference=LIST_UNREAD,
        account="" if ticket is None else ticket.loginid,
        contact_email=_contact_email(),
        contact_text=cfg.access.contact,
    )


def registered_frame(cfg: SsoConfig, ticket: DeniedClaims) -> Frame:
    """「등록했습니다」 — 「다시 접속」 이 처음 가려던 화면으로 간다(재시작 없음)."""
    return Frame(
        title=REGISTERED_TITLE,
        chip="registered",
        lead=(REGISTERED_TEXT,),
        primary=_login_link(cfg, RECONNECT_LABEL, ticket.next_path),
        reference=REGISTERED,
        account=ticket.loginid,
        contact_email=_contact_email(),
        contact_text=cfg.access.contact,
    )


def register_failed_frame(cfg: SsoConfig, ticket: DeniedClaims, now: int) -> Frame:
    """저장 실패 — 단추 대신 미리 채운 신청 글과 문의 줄(보드 D6)."""
    return Frame(
        title=REGISTER_FAILED_TITLE,
        chip="retry",
        lead=(REGISTER_FAILED_TEXT,),
        steps=(SEND_NOTE_STEP,),
        primary=_login_link(cfg, CHECK_AGAIN_LABEL, ticket.next_path),
        secondary=_other_account(cfg),
        note_label=NOTE_LABEL,
        note_text=_note(ticket, REGISTER_FAILED, now),
        reference=REGISTER_FAILED,
        account=ticket.loginid,
        contact_email=_contact_email(),
        contact_text=cfg.access.contact,
    )


def denied_family_page(
    cfg: SsoConfig, code: str, cookies: Mapping[str, str], *, now: int | None = None
) -> HTMLResponse:
    """거절 갈래 화면. 코드는 갈래만 고르고 꼴은 지금 상태가 정한다(모듈 설명).

    `registered` 는 표가 있고 그 계정이 지금 명단에 들 때만, `register_failed` 는 표가 있고 아직
    명단
    밖일 때만 그 꼴이다. 그 밖은 명단을 읽었으면 명단 밖 꼴, 못 읽었으면 확인 못 함 꼴이다.
    """
    moment = _now() if now is None else now
    ticket = read_denied(cfg, cookies, moment)
    allowed = ticket is not None and runtime.current_access(cfg).allows(ticket.loginid)
    if ticket is not None and code == REGISTERED and allowed:
        return frame_response(registered_frame(cfg, ticket), status=200, now=moment)
    if ticket is not None and code == REGISTER_FAILED and not allowed:
        return frame_response(register_failed_frame(cfg, ticket, moment), status=403, now=moment)
    if access_store.is_unread(cfg):
        return frame_response(list_unread_frame(cfg, ticket, moment), status=403, now=moment)
    return frame_response(not_on_list_frame(cfg, ticket, moment), status=403, now=moment)


def portal_refused_page(cfg: SsoConfig, *, now: int | None = None) -> HTMLResponse:
    """통합인증(포털)이 앱 사용을 막음 — 신청 칸 없음(서명 전 실패라 누구인지 모른다)."""
    moment = _now() if now is None else now
    retry = _login_link(cfg, RETRY_LABEL)
    other = _other_account(cfg)
    frame = Frame(
        title=PORTAL_TITLE,
        chip="denied",
        lead=(PORTAL_TEXT,),
        steps=PORTAL_STEPS,
        primary=other[0] if other else retry,
        secondary=(retry,) if other else (),
        reference=PORTAL_REFUSED,
        diagnostics=(PORTAL_DIAGNOSTIC,),
        contact_email=_contact_email(),
        contact_text=cfg.access.contact,
    )
    return frame_response(frame, status=403, now=moment)


def logout_page(cfg: SsoConfig) -> HTMLResponse:
    """로그아웃 안내 화면. 앱 밖 화면이라 Guide 가 없어 하는 법을 문장으로 둔다(설계 규칙 예외 —
    2026-11-08 사용자 답 b1) — 제목을 거듭하는 첫 문장은 두지 않는다."""
    again = public_link(cfg, "/")
    body = [
        "<p>이 앱의 로그인만 끝냈습니다 — 브라우저의 통합인증(AD) 로그인은 "
        "남아 있어 「다시 들어가기」 를 누르면 묻지 않고 다시 들어갑니다.</p>",
        f'<a class="button" href="{_esc(again)}">다시 들어가기</a>',
    ]
    if cfg.logout_url:
        body.append(
            f'<p class="muted"><a href="{_esc(cfg.logout_url)}">통합인증에서도 로그아웃</a></p>'
        )
    return html_page("로그아웃했습니다", "".join(body), status=200)


def loop_page(cfg: SsoConfig) -> HTMLResponse:
    """로그인 되풀이 화면 — 로그아웃 안내와 같은 예외 꼴(제목을 거듭하는 첫 문장 없음)."""
    body = (
        "<p>로그인 쿠키가 저장되지 않는 것 같습니다 — "
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
    if code == PORTAL_REFUSED:
        # 다시 해도 같은 실패 — 시도 쿠키가 남으면 「다시 시도」 를 되풀이한 사람이 쿠키 탓의 되풀이
        # 화면으로 잘못 간다.
        clear_attempt_cookie(response, cfg)
    runtime.record_event("login_fail", level=logging.WARNING, reason=code, loginid=loginid or "-")
    return response


def _deny(
    cfg: SsoConfig, state_cookie: str, login: VerifiedLogin, next_path: str, now: int
) -> Response:
    """토큰은 맞는데 접속 명단 밖 — 세션 없이 거절 표를 심고 303 → 거절 화면(PRG).

    진단을 보관하지 않는다 — 그 화면은 로그인 없이 열리고, 본인 계정은 이 브라우저의 거절 표가 있을
    때만 선다. 상태 쿠키 · 시도 쿠키 · 남아 있는 세션 쿠키를 지운다(시도 쿠키가 남으면 「다시
    확인」 을
    몇 번 누른 사람에게 「로그인이 되풀이됩니다」 가 잘못 뜬다). S3 명단을 아직 못 읽었으면 사유
    코드가 `list_unread` 다 — 명단에 든 사람도 막히는 동안이라 「명단에 없습니다」 라고 하지 않는다.
    """
    code = LIST_UNREAD if access_store.is_unread(cfg) else NOT_ON_LIST
    response = _denied_redirect(cfg, code)
    clear_state_cookie(response, state_cookie)
    clear_attempt_cookie(response, cfg)
    clear_session_cookie(response, cfg)
    set_denied_cookie(response, cfg, login, sanitize_next(next_path), now)
    runtime.record_event(
        runtime.DENIED_EVENT, level=logging.WARNING, reason=code, loginid=login.loginid
    )
    return response


def _denied_redirect(cfg: SsoConfig, code: str) -> Response:
    response = redirect(cfg, f"{names.ERROR_PATH}?{urlencode({'code': code})}", 303)
    response.headers["Referrer-Policy"] = "no-referrer"
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
    if not runtime.current_access(cfg).allows(login.loginid) and access_store.is_unread(cfg):
        # S3 명단을 아직 못 읽었으면 거절하기 직전에 다시 읽어 본다(60초에 한 번까지) — 네트워크라
        # 이벤트 루프에서 부르지 않는다.
        await run_in_threadpool(access_store.retry_unread, cfg)
    if not runtime.current_access(cfg).allows(login.loginid):
        return _deny(cfg, state_cookie, login, claims.next_path, now)

    token, session = issue_session(
        cfg, loginid=login.loginid, name=login.name, dept=login.dept, now=now
    )
    response = redirect(cfg, sanitize_next(claims.next_path), 303)
    set_session_cookie(response, cfg, token, end=session.exp, now=now)
    if len(response.raw_headers[-1][1]) > MAX_SESSION_COOKIE_BYTES:
        return _fail(cfg, "session_cookie_too_large", state=state, now=now, loginid=login.loginid)
    clear_state_cookie(response, state_cookie)
    clear_attempt_cookie(response, cfg)
    if cfg.denied_cookie in request.cookies:
        clear_denied_cookie(response, cfg)
    response.headers["Referrer-Policy"] = "no-referrer"
    runtime.record_event(
        "login_ok",
        loginid=login.loginid,
        hours=str(cfg.session_hours),
        max_hours=str(cfg.session_max_hours),
        sid=session.sid[:8],
        jti=session.jti[:8],
        audit={"name": login.name or ""},
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
    clear_denied_cookie(response, cfg)
    for name in _state_cookie_names(cfg, request.cookies):
        clear_state_cookie(response, name)
    return response


async def error(request: Request) -> Response:
    """`GET /auth/sso/error?id=` — 보관한 진단으로 오류 화면. id 가 없거나 지났으면 사유 코드만.

    거절 갈래(`DENIED_CODES`)는 공통 틀의 거절 화면이다 — 콜백 · 등록 경로가 진단 없이 이 코드로
    보내고, 꼴은 지금 상태가 정한다(`denied_family_page`). 포털 거절(`idp_error:access_denied`)도
    같은
    틀의 거절 꼴이다(403).
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
        if code in DENIED_CODES:
            return denied_family_page(cfg, code, request.cookies)
        if code not in allowed_reason_codes(cfg):
            code = "unknown"
    if code == PORTAL_REFUSED:
        return portal_refused_page(cfg)
    return error_page(cfg, code, record, status=400)


def register_request_problem(headers: Mapping[str, str], cfg: SsoConfig) -> str | None:
    """「접속 권한 신청」 요청의 출처 판정 — 거절 글 또는 `None`(통과).

    `Sec-Fetch-Site` 가 있으면 `same-origin` 이어야 하고, `Origin` 이 있으면 공개 주소 출처여야 한다
    (`null` 은 거절 — 거절 화면이 `Referrer-Policy: same-origin` 이라 정상 폼은 출처를 싣는다). 거절
    표가 `SameSite=Lax` 라 교차 사이트 POST 에는 표가 실리지 않고, 폼의 숨은 표지가 그 표에 묶여
    있다(두 겹).
    """
    site = headers.get("sec-fetch-site")
    if site is not None and site != "same-origin":
        return REGISTER_ORIGIN_REFUSAL
    origin = headers.get("origin")
    if origin is not None and not origin_allowed(origin, cfg):
        return REGISTER_ORIGIN_REFUSAL
    return None


async def register(request: Request) -> Response:
    """`POST /auth/sso/register` — 거절 표의 본인을 S3 접속 명단에 넣고 303(PRG).

    차례는 모드 → 메서드(GET 은 거절 화면으로 303) → 출처(403) → 폼 꼴(415 · 413 · 400) → 거절
    표(없거나
    만료면 표 없는 거절 화면으로) → 숨은 표지(403) → 이미 명단에 들었으면 쓰지 않고
    「등록했습니다」 →
    스레드 풀에서 `access_store.register_self` 다. 성공 · 이미 있음은 `registered`, 저장 실패는
    `register_failed` 로 보낸다. 폼의 다른 칸(계정 · 등급)은 읽지 않는다 — 신원은 거절 표뿐이다.
    """
    cfg = runtime.config()
    guarded = mode_guard(cfg)
    if guarded is not None:
        return guarded
    if request.method != "POST":
        return _denied_redirect(cfg, NOT_ON_LIST)
    refusal = register_request_problem(request.headers, cfg)
    if refusal is not None:
        return text_response(refusal, 403)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != FORM_CONTENT_TYPE:
        return text_response(REGISTER_FORM_REFUSAL, 415)
    body = await _read_body(request, limit=MAX_REGISTER_BODY_BYTES)
    if body is None:
        return text_response(REGISTER_FORM_REFUSAL, 413)
    form = _parse_form(body)
    if form is None:
        return text_response(REGISTER_FORM_REFUSAL, 400)
    now = _now()
    ticket = read_denied(cfg, request.cookies, now)
    if ticket is None:
        return _denied_redirect(cfg, NOT_ON_LIST)
    mark = form.get("t", "")
    if not hmac.compare_digest(mark.encode("utf-8"), denied_form_mark(cfg, ticket.jti).encode()):
        return text_response(REGISTER_FORM_REFUSAL, 403)
    if not access_store.is_unread(cfg) and runtime.current_access(cfg).allows(ticket.loginid):
        return _denied_redirect(cfg, REGISTERED)
    try:
        await run_in_threadpool(
            access_store.register_self,
            cfg,
            ticket.loginid,
            name=ticket.name,
            dept=ticket.dept,
            now=now,
        )
    except (S3Failure, access_store.StoreUnreadError, access_store.RegisterRefusedError):
        return _denied_redirect(cfg, REGISTER_FAILED)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 신청 글 화면으로(앱을 멈추지 않는다)
        runtime.record_event(
            "access_save_failed", level=logging.WARNING, loginid="-", reason=type(exc).__name__
        )
        return _denied_redirect(cfg, REGISTER_FAILED)
    return _denied_redirect(cfg, REGISTERED)


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
        or not runtime.current_access(cfg).allows(claims.loginid)
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
