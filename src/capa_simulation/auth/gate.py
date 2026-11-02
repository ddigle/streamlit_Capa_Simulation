# Purpose: 통합인증 문지기 — http·websocket 을 다 보는 순수 ASGI 미들웨어.

"""문지기 `SsoGate`.

`st.App(middleware=[Middleware(SsoGate)])` 로 Streamlit 미들웨어보다 **바깥**에 선다. 순수 ASGI 로
짠 것은 Starlette 의 `BaseHTTPMiddleware` 가 websocket 을 그냥 넘기기 때문이다(실측 — 쿠키 없이
`/_stcore/stream` 이 열렸다). 시험이 그 하위 클래스가 아님을 고정한다.

차례:

1. lifespan 등 http · websocket 이 아닌 것은 그대로 넘긴다.
2. 꺼짐이면 모두 넘긴다(Streamlit 자체 `/auth/*` 도 지금처럼).
3. Streamlit 자체 `st.login` 경로(`/auth/login` · `/auth/logout` · `/oauth2callback`)는 404,
   websocket 이면 닫는다.
4. 막힘이면 상태 검사만 넘기고 `GET /` 는 설정 화면 200(상태 검사가 `/` 를 봐도 재시작 고리가
   생기지 않게), 그 밖 http 는 503(탐색이면 설정 화면), websocket 은 수락 전 닫는다.
5. 켜짐: 공개 경로(정확 일치 — 상태 검사와 우리 경로 넷)는 넘기고, 나머지는 세션 쿠키를 검증한다.
   신원이 있으면(websocket 은 Origin 까지 맞으면) 넘기고, 없으면 websocket 은 수락 전 close 1008
   (→ HTTP 403), 최상위 탐색은 IdP 로 302, 그 밖(fetch · iframe · 업로드)은 401.

허용 목록은 정확 일치만 쓴다 — 끝 `/` · `//` 변형은 막힘 쪽으로 떨어진다. `/_stcore/` 를 접두로 열지
않는다.
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Receive, Scope, Send

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode, url_origin
from capa_simulation.auth.identity import Identity, identity_from_cookie_header, parse_cookie_header
from capa_simulation.auth.web import config_page, next_from_scope, start_login, text_response

POLICY_VIOLATION = 1008
_READ_METHODS = ("GET", "HEAD")


def request_headers(scope: Scope) -> dict[str, str]:
    """ASGI 머리 → 소문자 이름 맵. 같은 이름이 여럿이면 쿠키는 `; ` 로, 그 밖은 `, ` 로 잇는다."""
    merged: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1")
        if name in merged:
            joiner = "; " if name == "cookie" else ", "
            merged[name] = f"{merged[name]}{joiner}{value}"
        else:
            merged[name] = value
    return merged


def is_navigation(method: str, headers: dict[str, str]) -> bool:
    """최상위 탐색인가.

    브라우저(Sec-Fetch-* 가 있음)는 `navigate` + `document` 만, 비브라우저는 GET · HEAD 전부.
    """
    if method not in _READ_METHODS:
        return False
    fetch_headers = [name for name in headers if name.startswith("sec-fetch-")]
    if not fetch_headers:
        return True
    return (
        headers.get("sec-fetch-mode") == "navigate" and headers.get("sec-fetch-dest") == "document"
    )


def _is_public(path: str, method: str) -> bool:
    if path == names.HEALTH_PATH:
        return method in _READ_METHODS
    return path in names.SSO_PATHS


def origin_allowed(origin: str | None, cfg: SsoConfig) -> bool:
    """websocket 의 Origin 이 `CAPA_PUBLIC_URL` 의 출처와 같은가.

    Streamlit 자체는 localhost · 기계 IP 출처도 받는다 — 운영 출처 하나로 좁힌다.
    """
    expected = cfg.public_origin
    return bool(origin) and bool(expected) and url_origin(origin or "") == expected


class SsoGate:
    """순수 ASGI 문지기. 만들어지면 「문지기 있음」 표지를 세운다 — 앱 스크립트가 그것으로
    진입 파일 없이 뜬 서버(통합인증이 켜졌는데 문지기가 없음)를 알아챈다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        runtime.mark_gate_installed()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        cfg = runtime.config()
        if cfg.mode is SsoMode.OFF:
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET") if kind == "http" else "GET"
        if path in names.STREAMLIT_AUTH_PATHS:
            await self._refuse(kind, scope, receive, send, status=404, text="Not Found")
            return

        if cfg.mode is SsoMode.BROKEN:
            await self._broken(cfg, kind, path, method, scope, receive, send)
            return

        if kind == "http" and _is_public(path, method):
            await self.app(scope, receive, send)
            return
        headers = request_headers(scope)
        now = int(time.time())
        identity = identity_from_cookie_header(headers.get("cookie"), cfg, now)
        if isinstance(identity, Identity):
            if kind == "websocket" and not origin_allowed(headers.get("origin"), cfg):
                await self._close(send)
                return
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await self._close(send)
            return
        if is_navigation(method, headers):
            next_path = next_from_scope(path, scope.get("raw_path"), scope.get("query_string"))
            response = start_login(cfg, parse_cookie_header(headers.get("cookie")), next_path, now)
            await response(scope, receive, send)
            return
        await text_response("login required", 401)(scope, receive, send)

    async def _broken(
        self,
        cfg: SsoConfig,
        kind: str,
        path: str,
        method: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if kind == "websocket":
            await self._close(send)
            return
        if path == names.HEALTH_PATH and method in _READ_METHODS:
            await self.app(scope, receive, send)
            return
        if path == "/" and method in _READ_METHODS:
            await config_page(cfg, status=200)(scope, receive, send)
            return
        if is_navigation(method, request_headers(scope)):
            await config_page(cfg, status=503)(scope, receive, send)
            return
        await text_response("sso configuration incomplete", 503)(scope, receive, send)

    async def _refuse(
        self, kind: str, scope: Scope, receive: Receive, send: Send, *, status: int, text: str
    ) -> None:
        if kind == "websocket":
            await self._close(send)
            return
        await text_response(text, status)(scope, receive, send)

    @staticmethod
    async def _close(send: Send) -> None:
        """수락 전에 닫는다 — 서버가 핸드셰이크에 HTTP 403 으로 답한다."""
        await send({"type": "websocket.close", "code": POLICY_VIOLATION, "reason": ""})
