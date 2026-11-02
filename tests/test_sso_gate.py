# Purpose: 통합인증 문지기가 모드·경로·탐색 종류·websocket 별로 넘기거나 막는지 검증한다.

from __future__ import annotations

import secrets
import sys
import time
from collections.abc import MutableMapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from asgi_driver import App, AsgiResponse, Message, http, websocket_connect, websocket_talk
from sso_support import LOGINID, PUBLIC_URL, environ_from_lines, hidden_field, use_config
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from capa_simulation.auth import gate, names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.gate import SsoGate, is_navigation, origin_allowed
from capa_simulation.auth.server import sso_middleware, sso_routes
from capa_simulation.auth.tokens import SESSION_LEEWAY, SessionClaims, issue_session, verify_state

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sso_mock_idp import MockOptions, build_app, env_lines, make_signing_identity  # noqa: E402

NAVIGATE = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none"}
ORIGIN = {"origin": PUBLIC_URL}


async def _inner(request: Request) -> Response:
    return PlainTextResponse(f"inner {request.url.path}")


async def _stream(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close()


# 메아리 websocket 이 받은 끊김 코드(앱 쪽에서 본 것). 시험마다 비운다.
ECHO_DISCONNECTS: list[int] = []


async def _echo(websocket: WebSocket) -> None:
    """받은 프레임마다 `echo:` 를 붙여 돌려준다 — Streamlit 의 BackMsg 고리 자리."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_bytes(b"echo:" + data)
    except WebSocketDisconnect as exc:
        ECHO_DISCONNECTS.append(exc.code)


def gated_app() -> App:
    """문지기 + 우리 경로 넷 + 앱 자리(모든 http 경로 · `/_stcore/stream` · 메아리 websocket)."""
    inner = Starlette(
        routes=[
            *sso_routes(),
            WebSocketRoute("/_stcore/stream", _stream),
            WebSocketRoute("/_stcore/echo", _echo),
            Route("/{rest:path}", _inner, methods=["GET", "HEAD", "POST"]),
        ]
    )
    return SsoGate(inner)


def session_cookie(cfg: SsoConfig, *, now: int | None = None) -> dict[str, str]:
    token, _ = issue_session(
        cfg, loginid=LOGINID, name=None, dept=None, now=now or int(time.time())
    )
    return {"cookie": f"{cfg.session_cookie}={token}"}


def passed(response: AsgiResponse) -> bool:
    return response.status == 200 and response.text.startswith("inner ")


# --- 켜짐 ------------------------------------------------------------------------------------


def test_health_passes_without_a_cookie() -> None:
    use_config()

    assert passed(http(gated_app(), "GET", "/_stcore/health"))
    assert passed(http(gated_app(), "HEAD", "/_stcore/health"))


@pytest.mark.parametrize("path", ["/_stcore/health/", "//_stcore/health", "/_stcore/health%2F"])
def test_health_lookalikes_are_not_public(path: str) -> None:
    use_config()

    response = http(gated_app(), "GET", path, headers={"sec-fetch-mode": "cors"})

    assert not passed(response)
    assert response.status == 401


def test_health_post_is_not_public() -> None:
    use_config()

    assert http(gated_app(), "POST", "/_stcore/health").status == 401


def test_top_level_navigation_goes_to_the_idp_and_remembers_the_place() -> None:
    cfg = use_config()

    response = http(gated_app(), "GET", "/?theme=dark&process=A%20B", headers=NAVIGATE)

    assert response.status == 302
    location = response.header("location") or ""
    assert location.startswith("https://idp.example.invalid/adfs/oauth2/authorize/?")
    state = parse_qs(urlsplit(location).query)["state"][0]
    cookie = response.cookie(cfg.state_cookie(state))
    assert cookie is not None
    claims = verify_state(cookie.value, cfg, now=int(time.time()))
    assert claims.next_path == "/?theme=dark&process=A%20B"


def test_page_paths_are_remembered_too() -> None:
    cfg = use_config()

    response = http(gated_app(), "GET", "/space_layout?floor=2", headers=NAVIGATE)

    state = parse_qs(urlsplit(response.header("location") or "").query)["state"][0]
    cookie = response.cookie(cfg.state_cookie(state))
    assert cookie is not None
    assert (
        verify_state(cookie.value, cfg, now=int(time.time())).next_path == "/space_layout?floor=2"
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"sec-fetch-mode": "cors", "sec-fetch-dest": "empty"},
        {"sec-fetch-mode": "navigate", "sec-fetch-dest": "iframe"},
        {"sec-fetch-mode": "no-cors", "sec-fetch-dest": "image"},
        {"sec-fetch-mode": "navigate"},
    ],
)
def test_fetch_iframe_and_subresources_get_401(headers: dict[str, str]) -> None:
    use_config()

    response = http(gated_app(), "GET", "/static/fonts/a.woff2", headers=headers)

    assert response.status == 401
    assert response.header("cache-control") == "no-store"
    assert response.header("location") is None


def test_non_browser_get_without_fetch_metadata_is_redirected() -> None:
    use_config()

    assert http(gated_app(), "GET", "/").status == 302
    assert http(gated_app(), "HEAD", "/").status == 302


def test_upload_without_a_cookie_is_401() -> None:
    use_config()

    response = http(
        gated_app(),
        "POST",
        "/_stcore/upload_file/session/file",
        headers={"content-type": "multipart/form-data; boundary=x"},
        body=b"--x--",
    )

    assert response.status == 401


@pytest.mark.parametrize(
    "path", ["/_stcore/host-config", "/_stcore/metrics", "/media/x.png", "/component/c/index.html"]
)
def test_streamlit_internals_need_the_cookie(path: str) -> None:
    cfg = use_config()

    assert http(gated_app(), "GET", path, headers={"sec-fetch-mode": "cors"}).status == 401
    assert passed(http(gated_app(), "GET", path, headers=session_cookie(cfg)))


def test_valid_cookie_passes_everything() -> None:
    cfg = use_config()

    response = http(gated_app(), "GET", "/?theme=dark", headers={**NAVIGATE, **session_cookie(cfg)})

    assert passed(response)


def test_expired_or_revoked_cookie_is_treated_as_missing() -> None:
    cfg = use_config()
    old = int(time.time()) - cfg.session_seconds - 120
    expired = session_cookie(cfg, now=old)
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))
    runtime.revoke(issued.jti, issued.exp)

    assert http(gated_app(), "GET", "/", headers={**NAVIGATE, **expired}).status == 302
    revoked = {"cookie": f"{cfg.session_cookie}={token}"}
    assert http(gated_app(), "GET", "/", headers={**NAVIGATE, **revoked}).status == 302


def test_sso_routes_stay_public() -> None:
    use_config()

    assert http(gated_app(), "GET", names.LOGIN_PATH).status == 302
    assert http(gated_app(), "GET", names.LOGOUT_PATH).status == 200
    assert http(gated_app(), "GET", f"{names.ERROR_PATH}?code=state_missing").status == 400
    assert http(gated_app(), "GET", names.CALLBACK_PATH).status == 303


@pytest.mark.parametrize("path", names.STREAMLIT_AUTH_PATHS)
def test_streamlit_own_auth_paths_are_closed_while_on(path: str) -> None:
    cfg = use_config()

    response = http(gated_app(), "GET", path, headers={**NAVIGATE, **session_cookie(cfg)})

    assert response.status == 404
    assert websocket_connect(gated_app(), path, headers=session_cookie(cfg)) == ("closed", 1008)


# --- websocket --------------------------------------------------------------------------------


def test_websocket_without_a_cookie_is_closed_before_accept() -> None:
    use_config()

    assert websocket_connect(gated_app(), "/_stcore/stream", headers=ORIGIN) == ("closed", 1008)


def test_websocket_with_a_valid_cookie_and_origin_is_accepted() -> None:
    cfg = use_config()

    result = websocket_connect(
        gated_app(), "/_stcore/stream", headers={**ORIGIN, **session_cookie(cfg)}
    )

    assert result == "accepted"


@pytest.mark.parametrize(
    "origin",
    [None, "https://other.example.invalid", "http://capa.example.invalid", "null"],
)
def test_websocket_from_another_origin_is_closed(origin: str | None) -> None:
    cfg = use_config()
    headers = dict(session_cookie(cfg))
    if origin is not None:
        headers["origin"] = origin

    assert websocket_connect(gated_app(), "/_stcore/stream", headers=headers) == ("closed", 1008)


def test_websocket_with_forged_expired_or_revoked_cookie_is_closed() -> None:
    cfg = use_config()
    forged = {"cookie": f"{cfg.session_cookie}=eyJhbGciOiJIUzI1NiJ9.e30.x", **ORIGIN}
    expired = {**session_cookie(cfg, now=int(time.time()) - cfg.session_seconds - 120), **ORIGIN}
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))
    runtime.revoke(issued.jti, issued.exp)
    revoked = {"cookie": f"{cfg.session_cookie}={token}", **ORIGIN}

    for headers in (forged, expired, revoked):
        assert websocket_connect(gated_app(), "/_stcore/stream", headers=headers) == (
            "closed",
            1008,
        )


def _signed_in(cfg: SsoConfig) -> tuple[dict[str, str], SessionClaims]:
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))
    return {"cookie": f"{cfg.session_cookie}={token}", **ORIGIN}, issued


def _kinds(sent: tuple[Message, ...]) -> list[str]:
    return [str(message["type"]) for message in sent]


def _echoed(sent: tuple[Message, ...]) -> list[bytes]:
    return [bytes(message["bytes"]) for message in sent if message["type"] == "websocket.send"]


def test_open_websocket_keeps_talking_while_the_session_is_valid() -> None:
    cfg = use_config()
    headers, _ = _signed_in(cfg)
    ECHO_DISCONNECTS.clear()

    sent = websocket_talk(
        gated_app(), "/_stcore/echo", headers=headers, frames=[b"one", b"two", b"three"]
    )

    assert _kinds(sent)[0] == "websocket.accept"
    assert _echoed(sent) == [b"echo:one", b"echo:two", b"echo:three"]
    assert "websocket.close" not in _kinds(sent)
    assert ECHO_DISCONNECTS == [1000]
    assert not [event for event in runtime.recent_events() if event.event == "session_closed"]


def test_open_websocket_is_closed_on_the_next_message_after_logout() -> None:
    """다른 탭에서 로그아웃하면 열린 탭의 다음 메시지(콜백 · 프래그먼트 회차 요청)는 앱에 닿지
    않는다. 핸드셰이크 때만 보면 폐기된 세션의 위젯 콜백이 DB 에 글을 쓴다(검토 실측)."""
    cfg = use_config()
    headers, issued = _signed_in(cfg)
    ECHO_DISCONNECTS.clear()

    def logout_elsewhere(index: int) -> None:
        if index == 1:
            runtime.revoke(issued.jti, issued.exp)

    sent = websocket_talk(
        gated_app(),
        "/_stcore/echo",
        headers=headers,
        frames=[b"before", b"after-logout", b"later"],
        before_frame=logout_elsewhere,
    )

    assert _echoed(sent) == [b"echo:before"]
    assert sent[-1]["type"] == "websocket.close" and sent[-1]["code"] == 1008
    assert ECHO_DISCONNECTS == [1008], "앱은 끊김을 받는다 — 그 메시지는 넘기지 않는다"
    closed = [event for event in runtime.recent_events() if event.event == "session_closed"]
    assert [(event.value("reason"), event.value("loginid")) for event in closed] == [
        ("revoked", LOGINID)
    ]


def test_open_websocket_is_closed_on_the_next_message_after_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = use_config()
    headers, issued = _signed_in(cfg)
    ECHO_DISCONNECTS.clear()
    later = float(issued.exp + SESSION_LEEWAY + 1)

    def clock_passes_expiry(index: int) -> None:
        if index == 1:
            monkeypatch.setattr(gate, "time", SimpleNamespace(time=lambda: later))

    sent = websocket_talk(
        gated_app(),
        "/_stcore/echo",
        headers=headers,
        frames=[b"before", b"after-expiry"],
        before_frame=clock_passes_expiry,
    )

    assert _echoed(sent) == [b"echo:before"]
    assert sent[-1]["type"] == "websocket.close" and sent[-1]["code"] == 1008
    assert ECHO_DISCONNECTS == [1008]
    closed = [event for event in runtime.recent_events() if event.event == "session_closed"]
    assert [event.value("reason") for event in closed] == ["expired"]


def test_expiry_leeway_matches_the_session_cookie_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """문지기의 연결 중 검사는 쿠키 검증(`verify_session`)과 같은 여유를 준다 — 경계에서 둘이 갈리지
    않는다."""
    cfg = use_config()
    headers, issued = _signed_in(cfg)
    ECHO_DISCONNECTS.clear()
    edge = float(issued.exp + SESSION_LEEWAY)

    def clock_at_the_edge(index: int) -> None:
        if index == 1:
            monkeypatch.setattr(gate, "time", SimpleNamespace(time=lambda: edge))

    sent = websocket_talk(
        gated_app(),
        "/_stcore/echo",
        headers=headers,
        frames=[b"before", b"at-edge"],
        before_frame=clock_at_the_edge,
    )

    assert _echoed(sent) == [b"echo:before", b"echo:at-edge"]


def test_origin_allowed_compares_normalised_origins() -> None:
    cfg = use_config({names.ENV_PUBLIC_URL: "https://capa.example.invalid:443/proxy/8581"})

    assert origin_allowed("https://capa.example.invalid", cfg)
    assert origin_allowed("https://CAPA.example.invalid:443", cfg)
    assert not origin_allowed("https://capa.example.invalid:8443", cfg)
    assert not origin_allowed("", cfg)


# --- 그 밖 ------------------------------------------------------------------------------------


def test_lifespan_passes_through() -> None:
    use_config()
    seen: list[str] = []

    async def app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    import asyncio

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: MutableMapping[str, Any]) -> None:
        return None

    asyncio.run(SsoGate(app)({"type": "lifespan"}, receive, send))

    assert seen == ["lifespan"]


def test_off_mode_lets_everything_through() -> None:
    runtime.reset()

    assert passed(http(gated_app(), "GET", "/", headers=NAVIGATE))
    assert passed(http(gated_app(), "GET", "/auth/login"))
    assert http(gated_app(), "GET", names.LOGIN_PATH).status == 404
    assert websocket_connect(gated_app(), "/_stcore/stream") == "accepted"


def test_broken_mode_keeps_health_and_shows_the_setup_page() -> None:
    use_config(drop=[names.ENV_ISSUER])
    app = gated_app()

    assert passed(http(app, "GET", "/_stcore/health"))
    root = http(app, "GET", "/")
    assert root.status == 200 and "통합인증 설정을 마치지 못했습니다" in root.text
    assert http(app, "HEAD", "/").status == 200
    page = http(app, "GET", "/space_layout", headers=NAVIGATE)
    assert page.status == 503 and "통합인증 설정을 마치지 못했습니다" in page.text
    fetch = http(app, "GET", "/_stcore/host-config", headers={"sec-fetch-mode": "cors"})
    assert fetch.status == 503 and "<html" not in fetch.text
    assert http(app, "POST", names.CALLBACK_PATH).status == 503
    assert http(app, "GET", "/auth/login").status == 404
    assert websocket_connect(app, "/_stcore/stream", headers=ORIGIN) == ("closed", 1008)


def test_gate_is_pure_asgi_and_marks_itself_installed() -> None:
    runtime.reset()
    assert not runtime.gate_installed()

    SsoGate(Starlette())

    assert runtime.gate_installed()
    assert not issubclass(SsoGate, BaseHTTPMiddleware)
    classes: list[object] = [item.cls for item in sso_middleware()]
    assert classes == [SsoGate]


def test_is_navigation_rules() -> None:
    assert is_navigation("GET", {})
    assert is_navigation("HEAD", {})
    assert not is_navigation("POST", {})
    assert is_navigation("GET", {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document"})
    assert not is_navigation("GET", {"sec-fetch-dest": "document"})
    assert not is_navigation("GET", {"sec-fetch-site": "same-origin"})


# --- 가짜 IdP 와 끝까지 -----------------------------------------------------------------------


def test_full_login_round_trip_with_the_mock_idp() -> None:
    """GET / → IdP → form_post 콜백(상태 쿠키) → 303 → 세션 쿠키로 앱 · websocket 통과."""
    identity = make_signing_identity()
    options = MockOptions(port=8591, app_url=PUBLIC_URL)
    environ = environ_from_lines(env_lines(options, identity, secrets.token_urlsafe(48)))
    runtime.reset()
    cfg = runtime.start(environ)
    assert cfg.enabled, cfg.problems
    app = gated_app()

    first = http(app, "GET", "/?theme=dark&process=A", headers=NAVIGATE)
    assert first.status == 302
    authorize = urlsplit(first.header("location") or "")
    assert f"{authorize.scheme}://{authorize.netloc}{authorize.path}" == options.authorize_url

    page = http(build_app(options, identity), "GET", f"{authorize.path}?{authorize.query}")
    assert page.status == 200, page.text
    token = hidden_field(page.text, "id_token")
    state = hidden_field(page.text, "state")
    state_cookie = first.cookie(cfg.state_cookie(state))
    assert state_cookie is not None

    callback = http(
        app,
        "POST",
        names.CALLBACK_PATH,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "cookie": f"{state_cookie.name}={state_cookie.value}",
            "origin": options.idp_url,
            "sec-fetch-site": "cross-site",
            "sec-fetch-mode": "navigate",
            "sec-fetch-dest": "document",
        },
        body=urlencode({"id_token": token, "state": state}).encode(),
    )
    assert callback.status == 303, callback.header("location")
    assert callback.header("location") == f"{PUBLIC_URL}/?theme=dark&process=A"
    session = callback.cookie(cfg.session_cookie)
    assert session is not None and not session.deleted

    signed_in = {"cookie": f"{session.name}={session.value}"}
    assert passed(http(app, "GET", "/?theme=dark&process=A", headers={**NAVIGATE, **signed_in}))
    stream = websocket_connect(app, "/_stcore/stream", headers={**ORIGIN, **signed_in})
    assert stream == "accepted"
    assert runtime.recent_events()[0].event == "login_ok"
