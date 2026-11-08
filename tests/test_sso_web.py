# Purpose: 통합인증 경로 다섯의 쿠키 속성·PRG·거절 사유·화면 이스케이프를 검증한다.

from __future__ import annotations

import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
from asgi_driver import AsgiResponse, http
from sso_support import (
    AUTHORIZE_URL,
    CLIENT_ID,
    LOGINID,
    PUBLIC_URL,
    id_token_claims,
    make_id_token,
    sso_secret,
    use_config,
)
from starlette.applications import Starlette

from capa_simulation.auth import names, runtime, web
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity, IdentityProblem, identity_from_cookies
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import (
    SESSION_LEEWAY,
    decode_session,
    issue_session,
    issue_state,
    verify_session,
    verify_state,
)

FORM = {"content-type": "application/x-www-form-urlencoded"}


def routes_app() -> Starlette:
    return Starlette(routes=sso_routes())


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


class Login:
    """로그인 시작 한 번의 결과 — 콜백에 다시 쓸 state · nonce · 상태 쿠키."""

    def __init__(self, response: AsgiResponse, cfg: SsoConfig) -> None:
        self.response = response
        location = response.header("location") or ""
        query = parse_qs(urlsplit(location).query)
        self.query = {key: values[0] for key, values in query.items()}
        self.state = self.query["state"]
        self.nonce = self.query["nonce"]
        cookie = response.cookie(cfg.state_cookie(self.state))
        assert cookie is not None
        self.cookie_name = cookie.name
        self.cookie_value = cookie.value


def begin(app: Starlette, cfg: SsoConfig, next_path: str = "/") -> Login:
    response = http(app, "GET", f"{names.LOGIN_PATH}?next={quote(next_path, safe='')}")
    assert response.status == 302, response.text
    return Login(response, cfg)


def post_callback(
    app: Starlette, form: dict[str, str], cookies: dict[str, str] | None = None
) -> AsgiResponse:
    headers = dict(FORM)
    if cookies:
        headers["cookie"] = cookie_header(cookies)
    return http(app, "POST", names.CALLBACK_PATH, headers=headers, body=urlencode(form).encode())


def complete(app: Starlette, cfg: SsoConfig, next_path: str = "/") -> tuple[Login, AsgiResponse]:
    login = begin(app, cfg, next_path)
    token = make_id_token(id_token_claims(login.nonce))
    response = post_callback(
        app,
        {"id_token": token, "state": login.state},
        {login.cookie_name: login.cookie_value},
    )
    return login, response


def error_code_of(response: AsgiResponse) -> str:
    assert response.status == 303, response.text
    location = response.header("location") or ""
    assert location.startswith(f"{PUBLIC_URL}{names.ERROR_PATH}?")
    return parse_qs(urlsplit(location).query)["code"][0]


def follow_error(app: Starlette, response: AsgiResponse) -> AsgiResponse:
    location = response.header("location") or ""
    parts = urlsplit(location)
    return http(app, "GET", f"{parts.path}?{parts.query}")


# --- 로그인 시작 ---------------------------------------------------------------------------


def test_login_start_redirects_to_the_idp_with_seven_parameters() -> None:
    cfg = use_config()

    login = begin(routes_app(), cfg)

    location = login.response.header("location") or ""
    assert location.startswith(AUTHORIZE_URL + "?")
    assert login.query == {
        "client_id": CLIENT_ID,
        "response_type": "id_token",
        "response_mode": "form_post",
        "redirect_uri": f"{PUBLIC_URL}/auth/callback",
        "scope": "openid",
        "nonce": login.nonce,
        "state": login.state,
    }
    assert login.state != login.nonce and len(login.state) >= 40
    assert login.response.header("cache-control") == "no-store"


def test_state_cookie_attributes() -> None:
    cfg = use_config()

    login = begin(routes_app(), cfg)

    cookie = login.response.cookie(login.cookie_name)
    assert cookie is not None
    assert cookie.name.startswith("__Host-capa_sso_state_")
    assert cookie.has("httponly") and cookie.has("secure")
    assert cookie.get("samesite") == "none"
    assert cookie.get("path") == "/"
    assert cookie.get("max-age") == "600"
    assert not cookie.has("domain")
    attempt = login.response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.value == "1"
    assert attempt.get("max-age") == "120" and attempt.has("secure")
    assert attempt.get("samesite") == "none"


def test_state_cookie_carries_next_but_not_in_the_url() -> None:
    cfg = use_config()

    login = begin(routes_app(), cfg, "/?theme=dark&process=A")

    claims = verify_state(login.cookie_value, cfg, now=int(time.time()))
    assert claims.next_path == "/?theme=dark&process=A"
    assert "theme" not in (login.response.header("location") or "")


def test_location_ignores_host_and_forwarded_headers() -> None:
    cfg = use_config({names.ENV_PUBLIC_URL: "https://capa.example.invalid:8581"})

    response = http(
        routes_app(),
        "GET",
        names.LOGIN_PATH,
        headers={
            "host": "attacker.example.invalid",
            "x-forwarded-host": "attacker.example.invalid",
            "x-forwarded-proto": "http",
        },
    )

    query = parse_qs(urlsplit(response.header("location") or "").query)
    assert query["redirect_uri"] == ["https://capa.example.invalid:8581/auth/callback"]
    assert cfg.redirect_uri == query["redirect_uri"][0]


def test_authorize_query_is_merged_and_resource_added() -> None:
    use_config(
        {
            names.ENV_AUTHORIZE_URL: AUTHORIZE_URL + "?tenant=t1&client_id=wrong",
            names.ENV_RESOURCE: "urn:example:capa",
        }
    )

    response = http(routes_app(), "GET", names.LOGIN_PATH)

    query = parse_qs(urlsplit(response.header("location") or "").query)
    assert query["tenant"] == ["t1"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["resource"] == ["urn:example:capa"]
    assert "prompt" not in query and "login_hint" not in query


def test_third_attempt_shows_the_loop_page_instead_of_the_idp() -> None:
    cfg = use_config()

    response = http(
        routes_app(),
        "GET",
        names.LOGIN_PATH,
        headers={"cookie": f"{cfg.attempt_cookie}=3"},
    )

    assert response.status == 200
    assert "로그인이 되풀이됩니다" in response.text
    assert response.header("location") is None
    assert not any(
        cookie.name.startswith(cfg.state_cookie_prefix) for cookie in response.set_cookies
    )
    assert runtime.recent_events()[0].value("reason") == "login_loop"


def test_old_state_cookies_beyond_five_are_dropped_oldest_first() -> None:
    cfg = use_config()
    now = int(time.time())
    existing = {}
    for index in range(5):
        state = f"{index:02d}" + "s" * 41
        existing[cfg.state_cookie(state)] = issue_state(
            cfg, state=state, nonce="n" * 43, next_path="/", now=now - 500 + index * 10
        )

    response = http(
        routes_app(), "GET", names.LOGIN_PATH, headers={"cookie": cookie_header(existing)}
    )

    deleted = [cookie.name for cookie in response.set_cookies if cookie.deleted]
    assert deleted == [cfg.state_cookie("00" + "s" * 41)]


def test_already_signed_in_login_goes_straight_to_next() -> None:
    cfg = use_config()
    token, _ = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))

    response = http(
        routes_app(),
        "GET",
        f"{names.LOGIN_PATH}?next={quote('/?theme=dark', safe='')}",
        headers={"cookie": f"{cfg.session_cookie}={token}"},
    )

    assert response.status == 303
    assert response.header("location") == f"{PUBLIC_URL}/?theme=dark"


# --- 콜백 ------------------------------------------------------------------------------------


def test_callback_success_sets_the_session_cookie_and_clears_the_rest() -> None:
    cfg = use_config()

    login, response = complete(routes_app(), cfg, "/?theme=dark&process=A")

    assert response.status == 303
    assert response.header("location") == f"{PUBLIC_URL}/?theme=dark&process=A"
    assert response.header("referrer-policy") == "no-referrer"
    assert response.header("cache-control") == "no-store"
    session = response.cookie("__Host-capa_session")
    assert session is not None
    assert session.has("httponly") and session.has("secure")
    assert session.get("samesite") == "lax"
    assert session.get("path") == "/"
    assert session.get("max-age") == str(6 * 3600 + SESSION_LEEWAY)
    assert not session.has("domain")
    claims = verify_session(session.value, cfg, now=int(time.time()))
    assert claims.loginid == LOGINID and claims.name == "개발 사용자"
    decoded = decode_session(session.value, cfg, now=int(time.time()))
    assert decoded.sid == claims.sid and len(decoded.sid) >= 16
    assert decoded.auth_time == decoded.iat
    state = response.cookie(login.cookie_name)
    assert state is not None and state.deleted and state.has("secure")
    assert state.get("samesite") == "none" and state.get("path") == "/"
    attempt = response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.deleted and attempt.has("secure")
    login_ok = runtime.recent_events()[0]
    assert login_ok.event == "login_ok"
    assert login_ok.value("loginid") == LOGINID
    assert (login_ok.value("hours"), login_ok.value("max_hours")) == ("6", "24")
    assert login_ok.value("sid") == claims.sid[:8] and login_ok.value("jti") == claims.jti[:8]


def test_callback_get_goes_back_to_the_app() -> None:
    use_config()

    response = http(routes_app(), "GET", names.CALLBACK_PATH)

    assert response.status == 303
    assert response.header("location") == f"{PUBLIC_URL}/"


def test_callback_refuses_other_content_types() -> None:
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers={"content-type": "application/json"},
        body=b"{}",
    )

    assert response.status == 415
    assert "bad_content_type" in response.text


def test_callback_refuses_a_declared_large_body() -> None:
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers={**FORM, "content-length": str(64 * 1024 + 1)},
        body=b"a=1",
    )

    assert response.status == 413


def test_callback_counts_the_streamed_body() -> None:
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers=FORM,
        chunks=[b"a=" + b"x" * 40_000, b"y" * 40_000],
    )

    assert response.status == 413
    assert "body_too_large" in response.text


def test_duplicate_fields_are_a_bad_form() -> None:
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers=FORM,
        body=b"state=a&state=b&id_token=x",
    )

    assert error_code_of(response) == "bad_form"


def test_too_many_fields_are_a_bad_form() -> None:
    use_config()
    body = "&".join(f"f{index}=1" for index in range(25)).encode()

    response = http(routes_app(), "POST", names.CALLBACK_PATH, headers=FORM, body=body)

    assert error_code_of(response) == "bad_form"


def test_idp_error_is_shown_by_code_and_its_description_stays_out() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)

    response = post_callback(
        app,
        {
            "error": "access_denied",
            "error_description": "<b>secret detail</b>",
            "state": login.state,
        },
        {login.cookie_name: login.cookie_value},
    )

    assert error_code_of(response) == "idp_error:access_denied"
    cleared = response.cookie(login.cookie_name)
    assert cleared is not None and cleared.deleted
    page = follow_error(app, response)
    assert page.status == 400
    assert "access_denied" in page.text
    assert "secret detail" not in page.text


def test_unknown_idp_error_text_is_not_echoed() -> None:
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers=FORM,
        body=urlencode({"error": "<script>x</script>", "state": "s" * 43}).encode(),
    )

    assert error_code_of(response) == "idp_error:other"
    (event,) = [item for item in runtime.recent_events() if item.event == "idp_error"]
    assert event.value("error") == "unknown"


def test_a_nonstandard_idp_error_is_kept_for_the_admin_but_not_shown() -> None:
    """콜백은 누구나 보낸다 — 표준이 아닌 오류 이름은 사유 코드에 싣지 않고 사건 기록에만 남긴다."""
    use_config()

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers=FORM,
        body=urlencode({"error": "call_the_it_desk_now", "state": "s" * 43}).encode(),
    )

    assert error_code_of(response) == "idp_error:other"
    assert "call_the_it_desk_now" not in (response.header("location") or "")
    (event,) = [item for item in runtime.recent_events() if item.event == "idp_error"]
    assert event.value("error") == "call_the_it_desk_now"


def test_missing_state_cookie_is_state_missing() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)

    response = post_callback(
        app, {"id_token": make_id_token(id_token_claims(login.nonce)), "state": login.state}
    )

    assert error_code_of(response) == "state_missing"


def test_missing_state_with_a_valid_session_quietly_returns_to_the_app() -> None:
    cfg = use_config()
    token, _ = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))

    response = post_callback(
        routes_app(),
        {"id_token": "x", "state": "s" * 43},
        {cfg.session_cookie: token},
    )

    assert response.status == 303
    assert response.header("location") == f"{PUBLIC_URL}/"


def test_tampered_state_cookie_is_state_invalid() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)

    response = post_callback(
        app,
        {"id_token": make_id_token(id_token_claims(login.nonce)), "state": login.state},
        {login.cookie_name: login.cookie_value[:-2] + "xx"},
    )

    assert error_code_of(response) == "state_invalid"


def test_state_cookie_for_another_state_is_a_mismatch() -> None:
    cfg = use_config()
    now = int(time.time())
    posted = "p" * 16 + "A" * 27
    stored = "p" * 16 + "B" * 27
    cookie = issue_state(cfg, state=stored, nonce="n" * 43, next_path="/", now=now)

    response = post_callback(
        routes_app(),
        {"id_token": "x", "state": posted},
        {cfg.state_cookie(posted): cookie},
    )

    assert error_code_of(response) == "state_mismatch"


def test_a_state_can_be_used_once() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)
    form = {"id_token": make_id_token(id_token_claims(login.nonce)), "state": login.state}
    cookies = {login.cookie_name: login.cookie_value}

    first = post_callback(app, form, cookies)
    replay = post_callback(app, form, cookies)

    assert first.status == 303 and first.cookie("__Host-capa_session") is not None
    assert error_code_of(replay) == "state_reused"


def test_token_failure_goes_through_prg_to_an_error_page_with_diagnostics() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)
    token = make_id_token(id_token_claims(login.nonce, aud="someone-else"))

    response = post_callback(
        app, {"id_token": token, "state": login.state}, {login.cookie_name: login.cookie_value}
    )

    assert error_code_of(response) == "aud_mismatch"
    assert response.cookie("__Host-capa_session") is None
    location = response.header("location") or ""
    for value in (token, login.state, login.nonce):
        assert value not in location
    page = follow_error(app, response)
    assert page.status == 400
    assert "aud_mismatch" in page.text
    assert "someone-else" in page.text and CLIENT_ID in page.text
    for value in (token, login.state, login.nonce, sso_secret(), "개발 사용자", "개발부서"):
        assert value not in page.text
    event = runtime.recent_events()[0]
    assert event.event == "login_fail" and event.value("reason") == "aud_mismatch"
    assert event.value("loginid") == LOGINID


def test_error_page_escapes_and_sends_security_headers() -> None:
    cfg = use_config()
    app = routes_app()
    login = begin(app, cfg)
    claims = id_token_claims(login.nonce)
    claims["<script>alert(1)</script>"] = "x"
    token = make_id_token(claims, drop=["loginid"])

    response = post_callback(
        app, {"id_token": token, "state": login.state}, {login.cookie_name: login.cookie_value}
    )
    page = follow_error(app, response)

    assert error_code_of(response) == "claim_missing:loginid"
    assert "<script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert page.header("content-type") == "text/html; charset=utf-8"
    assert page.header("cache-control") == "no-store"
    assert page.header("content-security-policy") == (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
    )
    assert page.header("x-content-type-options") == "nosniff"
    assert page.header("referrer-policy") == "no-referrer"


def test_error_page_without_a_kept_diagnostic_shows_the_code_only() -> None:
    use_config()

    known = http(routes_app(), "GET", f"{names.ERROR_PATH}?id=unknown-id-123&code=state_missing")
    odd = http(routes_app(), "GET", f"{names.ERROR_PATH}?code=%3Cb%3E")

    assert known.status == 400 and "state_missing" in known.text
    assert odd.status == 400 and "unknown" in odd.text and "<b>" not in odd.text


@pytest.mark.parametrize(
    "code",
    [
        "claim_missing:SESSION_LOCKED.Call_IT_desk_and_read_your_AD_password_to_the_agent",
        "phishing_notice:Call_the_IT_desk",
        "idp_error:read_your_password_to_the_agent",
        "claim_invalid:another_claim",
        "state_missing:extra",
    ],
)
def test_error_page_does_not_show_a_made_up_code(code: str) -> None:
    """로그인 없이 여는 오류 주소의 질의 글을 그대로 실으면 앱 화면에 남이 고른 문장이 선다."""
    use_config()

    page = http(routes_app(), "GET", f"{names.ERROR_PATH}?{urlencode({'code': code})}")

    assert page.status == 400
    assert "사유 코드 <code>unknown</code>" in page.text
    assert code.split(":", 1)[-1] not in page.text


@pytest.mark.parametrize(
    "code",
    ["state_missing", "idp_error:access_denied", "idp_error:other", "claim_missing:loginid"],
)
def test_error_page_shows_the_codes_this_server_makes(code: str) -> None:
    use_config()

    page = http(routes_app(), "GET", f"{names.ERROR_PATH}?{urlencode({'code': code})}")

    assert f"사유 코드 <code>{code}</code>" in page.text


def test_session_cookie_too_large_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = use_config()
    monkeypatch.setattr(web, "MAX_SESSION_COOKIE_BYTES", 100)

    _, response = complete(routes_app(), cfg)

    assert error_code_of(response) == "session_cookie_too_large"
    assert response.cookie("__Host-capa_session") is None


def test_development_http_loopback_uses_plain_cookie_names() -> None:
    cfg = use_config({names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://localhost:8581"})

    login, response = complete(routes_app(), cfg)

    session = response.cookie("capa_session")
    assert session is not None and not session.has("secure")
    assert session.get("samesite") == "lax"
    # 상태 쿠키는 늘 Secure + SameSite=None(교차 사이트 form_post 에 실려야 한다).
    state_cookie = login.response.cookie(login.cookie_name)
    assert state_cookie is not None and state_cookie.has("secure")
    assert login.cookie_name.startswith("capa_sso_state_")


# --- 돌아갈 자리 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/", "/"),
        ("/?theme=dark&process=A%20B", "/?theme=dark&process=A%20B"),
        ("/page_two?x=1", "/page_two?x=1"),
        ("//evil.example.invalid/x", "/"),
        ("/\\evil.example.invalid", "/"),
        ("/%09/evil.example.invalid", "/"),
        ("/%2F%2Fevil.example.invalid", "/"),
        ("/%5Cevil", "/"),
        ("https:evil", "/"),
        ("https://evil.example.invalid/", "/"),
        ("evil", "/"),
        ("/a\x00b", "/"),
        ("/a\nb", "/"),
        ("/" + "a" * 2048, "/"),
        ("/auth/sso/login", "/"),
        ("/auth/callback", "/"),
        ("/authority", "/authority"),
        ("/한글", "/"),
        ("/./auth/sso/logout", "/"),
        ("/%2e/auth/sso/logout", "/"),
        ("/x/../auth/callback", "/"),
        ("/%2E%2E/8511/", "/"),
        ("/.%2e/8511/", "/"),
        ("/page/..", "/"),
        ("/.well-known", "/.well-known"),
        ("/a..b", "/a..b"),
        ("/?q=/../x", "/?q=/../x"),
    ],
)
def test_sanitize_next(raw: str | None, expected: str) -> None:
    assert web.sanitize_next(raw) == expected


def test_next_from_scope_keeps_the_query() -> None:
    assert web.next_from_scope("/x", b"/x", b"theme=dark") == "/x?theme=dark"
    assert web.next_from_scope("/x", None, b"") == "/x"
    assert web.next_from_scope("//x", b"//x", b"") == "/"


# --- 로그아웃 ---------------------------------------------------------------------------------


def test_logout_clears_three_cookies_and_revokes_the_session() -> None:
    cfg = use_config()
    now = int(time.time())
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=now)
    runtime.note_renewal(issued.sid, issued.exp, now=now)
    state_name = cfg.state_cookie("q" * 43)
    cookies = {cfg.session_cookie: token, cfg.attempt_cookie: "1", state_name: "x"}

    response = http(
        routes_app(), "GET", names.LOGOUT_PATH, headers={"cookie": cookie_header(cookies)}
    )

    assert response.status == 200
    assert "로그아웃했습니다" in response.text
    session = response.cookie(cfg.session_cookie)
    assert session is not None and session.deleted and session.has("secure")
    assert session.get("samesite") == "lax" and session.get("path") == "/"
    attempt = response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.deleted and attempt.has("secure")
    state = response.cookie(state_name)
    assert state is not None and state.deleted
    assert runtime.session_revoked(issued.sid)
    assert runtime.renewed_exp(issued.sid) is None, "로그아웃한 sid 는 갱신 표에서 빠진다"
    assert identity_from_cookies({cfg.session_cookie: token}, cfg, now) is IdentityProblem.REVOKED
    assert runtime.recent_events()[0].event == "logout"
    assert runtime.recent_events()[0].value("sid") == issued.sid[:8]


def test_logout_page_links_idp_logout_only_when_configured() -> None:
    use_config({names.ENV_LOGOUT_URL: "https://idp.example.invalid/adfs/oauth2/logout"})

    response = http(routes_app(), "GET", names.LOGOUT_PATH)

    assert "통합인증에서도 로그아웃" in response.text
    assert "https://idp.example.invalid/adfs/oauth2/logout" in response.text
    assert response.header("location") is None


def _first_paragraph(page: AsgiResponse) -> str:
    body = page.text.split("<main>", 1)[1]
    return body.split("<p>", 1)[1].split("</p>", 1)[0]


def test_outer_pages_do_not_repeat_their_title_as_the_first_sentence() -> None:
    """바깥 화면(앱 밖 · 규칙 예외)의 설명 문장은 남기되 제목을 거듭하는 첫 문장은 걷고, 단추 이름은
    「 」 로 감싼다(2026-11-08 사용자 답 b1). 모르는 사유 코드는 제목과 사유 코드만이다."""
    cfg = use_config()

    logout = http(routes_app(), "GET", names.LOGOUT_PATH)
    loop = http(
        routes_app(), "GET", names.LOGIN_PATH, headers={"cookie": f"{cfg.attempt_cookie}=3"}
    )
    unknown = http(routes_app(), "GET", f"{names.ERROR_PATH}?code=zzz")

    assert _first_paragraph(logout).startswith("이 앱의 로그인만 끝냈습니다")
    assert "「다시 들어가기」" in logout.text and "[다시 들어가기]" not in logout.text
    assert "로그아웃했습니다. " not in logout.text
    assert _first_paragraph(loop).startswith("로그인 쿠키가 저장되지 않는 것 같습니다")
    assert "되풀이되고 있습니다" not in loop.text
    assert "사유 코드 <code>unknown</code>" in unknown.text
    assert "<p>로그인하지 못했습니다.</p>" not in unknown.text
    for page in (logout, loop, unknown):
        assert "[" not in page.text.split("<main>", 1)[1]


def test_plain_links_on_the_outer_pages_take_the_accent_token() -> None:
    """바깥 화면의 보조 링크(「통합인증에서도 로그아웃」 등)는 브라우저 기본 파랑 · 보라가 아니라
    두 팔레트의 강조 토큰이다 — 단추 꼴 링크(`a.button`)는 선택자가 더 구체적이라 제 글자색을
    지킨다."""
    css = web.page_css()

    assert "\na { color: var(--accent); }\n" in css
    assert "--accent: #" in css.split("@media (prefers-color-scheme: dark)")[0]
    assert "--accent: #" in css.split("@media (prefers-color-scheme: dark)")[1]
    assert "color: var(--accent-text)" in css.split("a.button", 1)[1]


def test_identity_survives_until_logout() -> None:
    cfg = use_config()
    token, _ = issue_session(cfg, loginid=LOGINID, name="이름", dept="부서", now=int(time.time()))

    identity = identity_from_cookies({cfg.session_cookie: token}, cfg, int(time.time()))

    assert isinstance(identity, Identity)
    assert identity.display_name == "이름"


# --- 모드 --------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", names.SSO_PATHS)
def test_routes_are_404_while_off(path: str) -> None:
    runtime.reset()

    method = "POST" if path in (names.CALLBACK_PATH, names.REFRESH_PATH) else "GET"
    response = http(routes_app(), method, path, headers=FORM, body=b"a=1")

    assert response.status == 404


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_refresh_read_methods_are_404_while_off_too(method: str) -> None:
    """갱신 경로를 POST 로만 붙이면 꺼짐(문지기가 모두 넘김)의 GET 이 Streamlit 정적 마운트로 가 앱
    껍데기(200)가 섰다 — 「꺼짐이면 경로 다섯은 404」 를 GET · HEAD 에도 지킨다."""
    runtime.reset()

    response = http(routes_app(), method, names.REFRESH_PATH)

    assert response.status == 404


@pytest.mark.parametrize("path", names.SSO_PATHS)
def test_routes_show_the_setup_page_while_broken(path: str) -> None:
    use_config(drop=[names.ENV_ISSUER, names.ENV_SIGNING_CERT])

    method = "POST" if path in (names.CALLBACK_PATH, names.REFRESH_PATH) else "GET"
    response = http(routes_app(), method, path, headers=FORM, body=b"a=1")

    assert response.status == 503
    assert "통합인증 설정을 마치지 못했습니다" in response.text
    assert names.ENV_ISSUER in response.text and names.ENV_SIGNING_CERT in response.text
    assert sso_secret() not in response.text
    assert CLIENT_ID not in response.text
    assert f"{PUBLIC_URL}/auth/callback" in response.text
    assert "https://idp.example.invalid/adfs" in response.text  # 이슈어 후보
