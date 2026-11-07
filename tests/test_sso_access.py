# Purpose: 접속 명단의 목록 해석·모드 전이·콜백 거절·명단 밖 쿠키의 모든 길·값이 새지 않음을 지킨다.

"""`auth/access.py` 와 그 판정 자리.

판정은 `identity.session_check` 한 곳이고 거절은 콜백 한 곳에서 낸다. 그래서 여기서는 명단 밖의
유효한 쿠키가 지날 수 있는 길을 하나씩 다 밟는다 — 문지기 http(탐색 · fetch · 업로드) · 새
핸드셰이크 · 열린 연결의 메시지 · 갱신 경로 · 로그인 경로 · `app.py`. 값은 모두 합성(`demo.*`)이다.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
from asgi_driver import App, AsgiResponse, http, websocket_connect, websocket_talk
from sso_support import (
    AUTHORIZE_URL,
    PUBLIC_URL,
    environ_from_lines,
    hidden_field,
    id_token_claims,
    make_id_token,
    refresh_headers,
    sso_environ,
    sso_secret,
    use_config,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime, web
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    LOGINID_PATTERN,
    build_access_list,
    parse_entries,
)
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem, load_config
from capa_simulation.auth.gate import SsoGate
from capa_simulation.auth.identity import Identity, IdentityProblem, session_check
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import SESSION_LEEWAY, issue_session
from capa_simulation.components import sso_identity, sso_status
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.sso_reconnect import RECONNECT_NOTICE

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sso_mock_idp import MockOptions, build_app, env_lines, make_signing_identity  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN = "demo.admin"
USER = "demo.user"
GONE = "demo.gone"
CONTACT = "CAPA 담당 창구"
NAVIGATE = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none"}
FETCH = {"sec-fetch-mode": "cors", "sec-fetch-dest": "empty", "sec-fetch-site": "same-origin"}
ORIGIN = {"origin": PUBLIC_URL}
DENIED_LOCATION = f"{PUBLIC_URL}{names.ERROR_PATH}?code=not_on_list"
ECHO_DISCONNECTS: list[int] = []


def listed_config(extra: Mapping[str, str] | None = None) -> SsoConfig:
    """운영 · 켜짐 · 관리자 하나 · 사용자 하나."""
    return use_config(
        {names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER, **(extra or {})}
    )


def dev_environ(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """개발(http 루프백) · 켜짐 · 두 목록 없음."""
    base = {names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://localhost:8581"}
    return sso_environ(
        {**base, **(overrides or {})},
        drop=[
            name
            for name in (names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS)
            if name not in (overrides or {})
        ],
    )


async def _inner(request: Request) -> Response:
    return PlainTextResponse(f"inner {request.url.path}")


async def _echo(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_bytes(b"echo:" + data)
    except WebSocketDisconnect as exc:
        ECHO_DISCONNECTS.append(exc.code)


def gated_app() -> App:
    """문지기 + 우리 경로 다섯 + 앱 자리(모든 http 경로 · 메아리 websocket)."""
    inner = Starlette(
        routes=[
            *sso_routes(),
            WebSocketRoute("/_stcore/stream", _echo),
            Route("/{rest:path}", _inner, methods=["GET", "HEAD", "POST"]),
        ]
    )
    return SsoGate(inner)


def passed(response: AsgiResponse) -> bool:
    return response.status == 200 and response.text.startswith("inner ")


def session_token(cfg: SsoConfig, loginid: str) -> str:
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    return token


def cookie_of(cfg: SsoConfig, loginid: str) -> dict[str, str]:
    """서명이 맞는 세션 쿠키 머리 — 명단에서 빠진 사람은 재시작 전에 받은 이 쿠키를 그대로 든다."""
    return {"cookie": f"{cfg.session_cookie}={session_token(cfg, loginid)}"}


def cookie_header(jar: Mapping[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in jar.items())


def apply_cookies(jar: dict[str, str], response: AsgiResponse) -> None:
    """브라우저처럼 Set-Cookie 를 따른다."""
    for item in response.set_cookies:
        if item.deleted:
            jar.pop(item.name, None)
        else:
            jar[item.name] = item.value


def start_login(app: App, jar: dict[str, str], next_path: str = "/") -> tuple[str, str]:
    """로그인 시작 → IdP 로 가는 302 를 따라 쿠키를 받고 (state, nonce) 를 돌려준다."""
    headers = dict(NAVIGATE)
    if jar:
        headers["cookie"] = cookie_header(jar)
    target = f"{names.LOGIN_PATH}?next={quote(next_path, safe='')}"
    response = http(app, "GET", target, headers=headers)
    assert response.status == 302, response.text
    apply_cookies(jar, response)
    query = parse_qs(urlsplit(response.header("location") or "").query)
    return query["state"][0], query["nonce"][0]


def post_form(app: App, jar: Mapping[str, str], token: str, state: str) -> AsgiResponse:
    headers = {"content-type": "application/x-www-form-urlencoded", "cookie": cookie_header(jar)}
    body = urlencode({"id_token": token, "state": state}).encode()
    return http(app, "POST", names.CALLBACK_PATH, headers=headers, body=body)


def sign_in(app: App, jar: dict[str, str], loginid: str, **claims: Any) -> AsgiResponse:
    state, nonce = start_login(app, jar)
    token = make_id_token(id_token_claims(nonce, loginid=loginid, **claims))
    return post_form(app, jar, token, state)


def has_live_session(cfg: SsoConfig, response: AsgiResponse) -> bool:
    cookie = response.cookie(cfg.session_cookie)
    return cookie is not None and not cookie.deleted


def error_code_of(response: AsgiResponse) -> str:
    assert response.status == 303, response.text
    query = parse_qs(urlsplit(response.header("location") or "").query)
    return query["code"][0]


def events_named(event: str) -> list[runtime.SsoEvent]:
    return [item for item in runtime.recent_events() if item.event == event]


def assert_absent(text: str, *values: str) -> None:
    """값이 글자 그대로도, 마크다운으로 막은 꼴로도 없다."""
    for value in values:
        assert value not in text, value
        assert literal_markdown(value) not in text, value


# --- 목록 해석 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "demo.a,demo.b",
        "demo.a;demo.b",
        "demo.a demo.b",
        "  demo.a ,\tdemo.b ; ",
        "demo.a,,;  demo.b\n",
    ],
)
def test_entries_split_on_commas_semicolons_and_spaces(raw: str) -> None:
    assert parse_entries(raw) == (("demo.a", "demo.b"), 0)


def test_matching_ignores_case_and_outer_spaces() -> None:
    access = build_access_list("Demo.Admin", " DEMO.USER ", enforced=True)

    assert access.allows("demo.admin") and access.allows("  DEMO.ADMIN ")
    assert access.allows("demo.USER")
    assert not access.allows("demo.other")


def test_duplicates_count_once_and_an_admin_on_both_lists_stays_admin() -> None:
    access = build_access_list("demo.a,DEMO.A", "demo.a,demo.b,Demo.B", enforced=True)

    assert access.grade_of("demo.a") == GRADE_ADMIN
    assert access.grade_of("demo.b") == GRADE_USER
    assert access.grade_of("demo.c") is None
    assert (access.admin_count, access.user_count) == (1, 1)


def test_entries_of_another_shape_are_dropped_and_only_counted() -> None:
    """도메인 접두 · 글자 집합 밖 · 너무 긴 값은 버리고 개수만 센다 — 값은 어디에도 남지 않는다."""
    too_long = "a" * 65
    access = build_access_list(
        rf"DOMAIN\demo.a,demo.b,bad!name,{too_long}", "데모,demo.c", enforced=True
    )

    assert (access.unreadable_admins, access.unreadable_users) == (3, 1)
    assert access.unreadable_count == 4
    assert sorted(access.grades) == ["demo.b", "demo.c"]
    assert not access.allows("demo.a") and not access.allows(r"DOMAIN\demo.a")
    assert not access.allows(too_long)


def test_a_lookalike_character_never_folds_onto_a_listed_id() -> None:
    """켈빈 기호(U+212A)는 접으면 `k` 다 — 꼴을 접기 전에 봐야 다른 사람의 loginid 로 읽히지
    않는다."""
    kelvin = "\u212a"
    assert kelvin.casefold() == "k"

    listed = build_access_list("demo.kim", "", enforced=True)
    assert not listed.allows(f"demo.{kelvin}im")

    written = build_access_list(f"demo.{kelvin}im", "", enforced=True)
    assert written.unreadable_admins == 1
    assert not written.allows("demo.kim")


@pytest.mark.parametrize("value", ["-", ".", "@", "_", "-.@_"])
def test_an_entry_without_a_letter_or_digit_is_not_a_person(value: str) -> None:
    """표가 빈 값을 받지 않아 넣은 자리표가 관리자 한 명으로 세어지면 막힘을 비껴가 전원이
    잠긴다."""
    assert parse_entries(value) == ((), 1)
    assert parse_entries(f"demo.a,{value}") == (("demo.a",), 1)

    cfg = load_config(sso_environ({names.ENV_ACCESS_ADMINS: value}))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "no_valid_entry"),)
    assert cfg.notices == (SsoProblem(names.ENV_ACCESS_ADMINS, "entries_unreadable"),)


def test_not_enforced_lets_everyone_in() -> None:
    access = build_access_list("", "", enforced=False)

    assert access.allows("anyone")
    assert access.grade_of("anyone") is None
    assert (access.admin_count, access.user_count, access.unreadable_count) == (0, 0, 0)


def test_the_token_pattern_is_the_shared_one() -> None:
    """ID · 세션 토큰이 같은 꼴을 쓴다 — 명단에 적을 수 있는 값과 로그인할 수 있는 값이 어긋나지
    않게."""
    from capa_simulation.auth import tokens

    assert vars(tokens)["LOGINID_PATTERN"] is LOGINID_PATTERN
    assert not LOGINID_PATTERN.match(r"DOMAIN\demo.user")


# --- 모드 전이 --------------------------------------------------------------------------------


def test_production_without_the_admin_list_is_blocked() -> None:
    cfg = load_config(sso_environ(drop=[names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS]))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)
    assert cfg.access.enforced


def test_production_with_users_but_no_admin_is_blocked() -> None:
    cfg = load_config(sso_environ({names.ENV_ACCESS_USERS: USER}, drop=[names.ENV_ACCESS_ADMINS]))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


def test_a_blank_admin_value_counts_as_missing() -> None:
    cfg = load_config(sso_environ({names.ENV_ACCESS_ADMINS: "   "}))

    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


@pytest.mark.parametrize(
    ("value", "notices"),
    [
        (rf"DOMAIN\{ADMIN}", (SsoProblem(names.ENV_ACCESS_ADMINS, "entries_unreadable"),)),
        (" , ; ", ()),
    ],
)
def test_a_value_with_nothing_readable_is_blocked(
    value: str, notices: tuple[SsoProblem, ...]
) -> None:
    cfg = load_config(sso_environ({names.ENV_ACCESS_ADMINS: value}))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "no_valid_entry"),)
    assert cfg.notices == notices


def test_development_without_lists_admits_everyone() -> None:
    cfg = load_config(dev_environ())

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert not cfg.access.enforced
    assert cfg.access.allows(GONE)


@pytest.mark.parametrize("app_env", [None, "", "   ", "dev", "local", "test"])
@pytest.mark.parametrize("flag", [None, "auto", "required"])
def test_a_server_beyond_loopback_needs_the_list_whatever_app_env_says(
    app_env: str | None, flag: str | None
) -> None:
    """`APP_ENV` 를 빠뜨렸거나 개발 값이어도 공개 주소가 이 PC 밖이면 ADFS 를 지난 사람 전부를 받지
    않는다 — 목록이 없으면 막힘이다."""
    overrides = {} if app_env is None else {names.ENV_APP_ENV: app_env}
    if flag is not None:
        overrides[names.ENV_SSO] = flag
    drop = [names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS]
    if app_env is None:
        drop.append(names.ENV_APP_ENV)

    cfg = load_config(sso_environ(overrides, drop=drop))

    assert not cfg.prod
    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)
    assert cfg.access.enforced
    assert not cfg.access.allows(GONE)


def test_a_person_off_the_list_cannot_enter_a_server_without_app_env() -> None:
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN}, drop=[names.ENV_APP_ENV])
    assert cfg.enabled and not cfg.prod
    app = gated_app()

    assert not has_live_session(cfg, sign_in(app, {}, GONE))
    assert has_live_session(cfg, sign_in(app, {}, ADMIN))


def test_a_locked_server_needs_the_list_even_on_loopback() -> None:
    cfg = load_config(dev_environ({names.ENV_SSO: "required"}))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


def test_off_beyond_loopback_shows_the_list_as_a_problem_when_switched_on() -> None:
    cfg = load_config(
        sso_environ(
            {names.ENV_APP_ENV: "dev"},
            drop=[names.ENV_CLIENT_ID, names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS],
        )
    )

    assert cfg.mode is SsoMode.OFF
    assert cfg.readiness == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


def test_development_with_a_list_enforces_it() -> None:
    cfg = load_config(dev_environ({names.ENV_ACCESS_ADMINS: ADMIN}))

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert cfg.access.enforced
    assert cfg.access.allows(ADMIN) and not cfg.access.allows(GONE)


def test_development_with_users_only_is_blocked_too() -> None:
    """목록을 하나라도 넣었으면 명단을 쓰려는 것이다 — 관리자가 없으면 개발에서도 막힌다."""
    cfg = load_config(dev_environ({names.ENV_ACCESS_USERS: USER}))

    assert cfg.mode is SsoMode.BROKEN
    assert cfg.problems == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


def test_off_in_production_reports_it_as_a_problem_when_switched_on() -> None:
    cfg = load_config(
        sso_environ(drop=[names.ENV_CLIENT_ID, names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS])
    )

    assert cfg.mode is SsoMode.OFF
    assert cfg.problems == ()
    assert cfg.readiness == (SsoProblem(names.ENV_ACCESS_ADMINS, "missing"),)


def test_off_in_development_has_no_list_problem() -> None:
    cfg = load_config({})

    assert cfg.mode is SsoMode.OFF
    assert not cfg.access.enforced
    assert names.ENV_ACCESS_ADMINS not in [problem.env for problem in cfg.readiness]


def test_unreadable_entries_warn_without_blocking() -> None:
    cfg = load_config(
        sso_environ(
            {
                names.ENV_ACCESS_ADMINS: rf"{ADMIN},DOMAIN\demo.x",
                names.ENV_ACCESS_USERS: f"bad!name,{USER}",
            }
        )
    )

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert SsoProblem(names.ENV_ACCESS_ADMINS, "entries_unreadable") in cfg.notices
    assert SsoProblem(names.ENV_ACCESS_USERS, "entries_unreadable") in cfg.notices
    assert cfg.access.allows(ADMIN) and cfg.access.allows(USER)
    for notice in cfg.notices:
        assert "demo" not in notice.reason and "bad" not in notice.reason


@pytest.mark.parametrize(
    ("value", "code"), [("x" * 501, "too_long"), ("줄\x01바꿈", "control_chars")]
)
def test_a_bad_contact_warns_without_blocking(value: str, code: str) -> None:
    cfg = load_config(sso_environ({names.ENV_ACCESS_CONTACT: value}))

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert SsoProblem(names.ENV_ACCESS_CONTACT, code) in cfg.notices
    assert cfg.access.contact == ""


def test_the_three_names_are_read_and_reported_by_presence_only() -> None:
    cfg = load_config(sso_environ({names.ENV_ACCESS_CONTACT: CONTACT}))

    for name in (names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS, names.ENV_ACCESS_CONTACT):
        assert name in names.SSO_ENVIRONMENT
        assert cfg.env_presence[name] is True


# --- 판정 한 곳 -------------------------------------------------------------------------------


def _identity(cfg: SsoConfig, loginid: str) -> Identity:
    _, claims = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    return Identity.from_claims(claims)


def test_session_check_looks_at_revocation_then_the_list_then_the_end() -> None:
    cfg = listed_config()
    now = int(time.time())
    listed = _identity(cfg, USER)
    dropped = _identity(cfg, GONE)
    past_end = listed.exp + SESSION_LEEWAY + 1

    assert session_check(listed, cfg, now)[0] is None
    assert session_check(listed, cfg, past_end)[0] is IdentityProblem.EXPIRED
    assert session_check(dropped, cfg, now)[0] is IdentityProblem.DENIED
    assert session_check(dropped, cfg, past_end)[0] is IdentityProblem.DENIED
    runtime.revoke_session(dropped.sid, until=past_end + 100, now=now)
    assert session_check(dropped, cfg, now)[0] is IdentityProblem.REVOKED


def test_a_cookie_issued_in_another_case_is_still_the_same_person() -> None:
    cfg = listed_config()

    assert session_check(_identity(cfg, "DEMO.USER"), cfg, int(time.time()))[0] is None


def test_every_identity_problem_has_a_stop_notice() -> None:
    assert set(sso_identity._PROBLEM_NOTICES) == set(IdentityProblem)


def test_the_reconnect_banner_names_the_list_too() -> None:
    assert "접속 명단에서 빠졌거나" in RECONNECT_NOTICE


# --- 콜백 -------------------------------------------------------------------------------------


@pytest.mark.parametrize("loginid", [ADMIN, USER, "DEMO.USER"])
def test_a_listed_person_gets_a_session(loginid: str) -> None:
    cfg = listed_config()
    app = gated_app()
    jar: dict[str, str] = {}

    response = sign_in(app, jar, loginid)

    assert response.status == 303
    assert response.header("location") == f"{PUBLIC_URL}/"
    assert has_live_session(cfg, response)
    assert [item.value("loginid") for item in events_named("login_ok")] == [loginid]
    assert runtime.denied_total() == 0
    apply_cookies(jar, response)
    assert passed(http(app, "GET", "/", headers={**NAVIGATE, "cookie": cookie_header(jar)}))


def test_a_person_off_the_list_gets_no_session_and_a_redirect() -> None:
    cfg = listed_config()
    app = gated_app()
    jar: dict[str, str] = {}
    state, nonce = start_login(app, jar)
    assert cfg.attempt_cookie in jar and cfg.state_cookie(state) in jar
    token = make_id_token(id_token_claims(nonce, loginid=GONE))

    response = post_form(app, jar, token, state)

    assert response.status == 303
    assert response.header("location") == DENIED_LOCATION
    assert response.header("referrer-policy") == "no-referrer"
    assert not has_live_session(cfg, response)
    state_cookie = response.cookie(cfg.state_cookie(state))
    attempt_cookie = response.cookie(cfg.attempt_cookie)
    assert state_cookie is not None and state_cookie.deleted
    assert attempt_cookie is not None and attempt_cookie.deleted
    assert not events_named("login_ok")
    assert not events_named("login_denied"), "거절은 최근 사건 고리에 두지 않는다"
    assert not runtime.recent_events(anonymous=True), "서명이 통과한 뒤다 — 무인증 고리도 아니다"
    [denied] = runtime.denied_accounts()
    assert (denied.loginid, denied.count) == (GONE, 1)
    assert runtime.denied_total() == 1


def test_a_leftover_session_cookie_is_cleared_when_denied() -> None:
    """명단에서 빠지기 전에 받은 쿠키를 든 채 다시 로그인하면 그 쿠키도 지운다."""
    cfg = listed_config()
    app = gated_app()
    jar = {cfg.session_cookie: session_token(cfg, GONE)}

    response = sign_in(app, jar, GONE)

    leftover = response.cookie(cfg.session_cookie)
    assert leftover is not None and leftover.deleted


def test_resubmitting_a_denied_form_never_gets_a_session() -> None:
    cfg = listed_config()
    app = gated_app()
    jar: dict[str, str] = {}
    state, nonce = start_login(app, jar)
    token = make_id_token(id_token_claims(nonce, loginid=GONE))
    with_state_cookie = dict(jar)

    first = post_form(app, jar, token, state)
    again = post_form(app, with_state_cookie, token, state)
    apply_cookies(jar, first)
    after_back = post_form(app, jar, token, state)

    assert not has_live_session(cfg, first)
    assert not has_live_session(cfg, again)
    assert error_code_of(again) == "state_reused"
    assert not has_live_session(cfg, after_back)
    assert error_code_of(after_back) == "state_missing"


def test_pressing_check_again_many_times_never_shows_the_loop_page() -> None:
    """거절이 시도 쿠키를 지운다 — 남으면 세 번째에 「로그인이 되풀이됩니다」 가 잘못 뜬다."""
    cfg = listed_config()
    app = gated_app()
    jar: dict[str, str] = {}

    for _ in range(5):
        response = sign_in(app, jar, GONE)  # start_login 이 302 가 아니면 멈춘다
        assert response.header("location") == DENIED_LOCATION
        apply_cookies(jar, response)
        assert cfg.attempt_cookie not in jar

    assert not jar, "거절 뒤 브라우저에 남는 쿠키가 없다"


def test_once_listed_the_same_link_lets_the_person_in() -> None:
    """「다시 확인」 은 로그인 경로다 — 명단에 넣고 다시 띄운 뒤 누르면 그대로 들어온다."""
    listed_config()
    app = gated_app()
    jar: dict[str, str] = {}
    apply_cookies(jar, sign_in(app, jar, GONE))

    cfg = listed_config({names.ENV_ACCESS_USERS: f"{USER},{GONE}"})

    assert has_live_session(cfg, sign_in(gated_app(), jar, GONE))


def test_not_enforced_the_callback_admits_any_verified_person() -> None:
    runtime.reset()
    cfg = runtime.start(dev_environ())
    assert cfg.enabled and not cfg.access.enforced

    assert has_live_session(cfg, sign_in(gated_app(), {}, GONE))


def test_repeated_denials_cannot_push_out_the_audit_events() -> None:
    """들어오지 못하는 사람이 「다시 확인」 을 되풀이해도 설정 · 로그인 기록이 밀려나지 않는다 —
    C-DEP 에는 로그 창구가 없어 이 고리가 유일한 감사 창이다."""
    listed_config()
    app = gated_app()
    sign_in(app, {}, USER)
    before = runtime.recent_events()
    assert {item.event for item in before} == {"config", "login_ok"}

    for _ in range(runtime.MAX_EVENTS + 5):
        sign_in(app, {}, GONE)

    assert runtime.recent_events() == before
    assert runtime.denied_total() == runtime.MAX_EVENTS + 5


def test_one_person_repeating_cannot_push_another_denied_person_out() -> None:
    """계정마다 한 칸이다 — 누가 막혔는지가 한 사람의 되풀이로 사라지지 않는다. 대소문자만 다르면
    같은 사람이다."""
    listed_config()
    app = gated_app()
    sign_in(app, {}, "demo.first")
    for _ in range(runtime.MAX_EVENTS + 5):
        sign_in(app, {}, GONE)
    sign_in(app, {}, GONE.upper())

    accounts = runtime.denied_accounts()

    assert [(item.loginid.casefold(), item.count) for item in accounts] == [
        (GONE, runtime.MAX_EVENTS + 6),
        ("demo.first", 1),
    ]
    assert accounts[0].last_at >= accounts[1].last_at


def test_denied_accounts_are_capped_and_the_total_keeps_counting() -> None:
    """계정 수만큼 메모리가 늘지 않는다 — 가장 오래 전에 막힌 계정이 빠지고 누계는 남는다."""
    extra = 3
    for index in range(runtime.MAX_DENIED_ACCOUNTS + extra):
        runtime.record_event("login_denied", reason="not_on_list", loginid=f"demo.p{index}")

    accounts = runtime.denied_accounts()

    assert len(accounts) == runtime.MAX_DENIED_ACCOUNTS
    assert accounts[0].loginid == f"demo.p{runtime.MAX_DENIED_ACCOUNTS + extra - 1}"
    assert accounts[-1].loginid == f"demo.p{extra}"
    assert runtime.denied_total() == runtime.MAX_DENIED_ACCOUNTS + extra


def test_reset_forgets_the_denied_accounts() -> None:
    runtime.record_event("login_denied", reason="not_on_list", loginid=GONE)

    runtime.reset()

    assert runtime.denied_accounts() == []
    assert runtime.denied_total() == 0


def test_the_mock_idp_runs_both_the_allowed_and_the_denied_path() -> None:
    """가짜 IdP 로 끝까지 — 문서 8장의 두 갈래(`--loginid` 만 다르다)."""
    identity = make_signing_identity()
    results: dict[str, bool] = {}
    for loginid in (USER, GONE):
        options = MockOptions(port=8591, app_url=PUBLIC_URL, loginid=loginid)
        environ = environ_from_lines(env_lines(options, identity, sso_secret()))
        environ[names.ENV_ACCESS_ADMINS] = ADMIN
        environ[names.ENV_ACCESS_USERS] = USER
        runtime.reset()
        cfg = runtime.start(environ)
        assert cfg.enabled, cfg.problems
        app = gated_app()
        first = http(app, "GET", "/", headers=NAVIGATE)
        authorize = urlsplit(first.header("location") or "")
        page = http(build_app(options, identity), "GET", f"{authorize.path}?{authorize.query}")
        state = hidden_field(page.text, "state")
        state_cookie = first.cookie(cfg.state_cookie(state))
        assert state_cookie is not None
        callback = post_form(
            app,
            {state_cookie.name: state_cookie.value},
            hidden_field(page.text, "id_token"),
            state,
        )
        results[loginid] = has_live_session(cfg, callback)
        if loginid == GONE:
            assert callback.header("location") == DENIED_LOCATION

    assert results == {USER: True, GONE: False}


# --- 명단에서 빠진 유효한 쿠키 ------------------------------------------------------------------


def test_navigation_with_a_dropped_cookie_goes_to_the_idp() -> None:
    cfg = listed_config()

    response = http(gated_app(), "GET", "/", headers={**NAVIGATE, **cookie_of(cfg, GONE)})

    assert response.status == 302
    assert (response.header("location") or "").startswith(AUTHORIZE_URL)


def test_fetch_with_a_dropped_cookie_is_401() -> None:
    cfg = listed_config()

    response = http(
        gated_app(), "GET", "/_stcore/host-config", headers={**FETCH, **cookie_of(cfg, GONE)}
    )

    assert response.status == 401
    assert "<html" not in response.text


def test_upload_with_a_dropped_cookie_is_401() -> None:
    cfg = listed_config()
    headers = {**FETCH, **cookie_of(cfg, GONE), "content-type": "multipart/form-data; boundary=x"}

    response = http(gated_app(), "POST", "/_stcore/upload_file/a/b", headers=headers, body=b"x")

    assert response.status == 401


def test_a_new_handshake_with_a_dropped_cookie_is_closed_before_accept() -> None:
    cfg = listed_config()
    headers = {**ORIGIN, **cookie_of(cfg, GONE)}

    assert websocket_connect(gated_app(), "/_stcore/stream", headers=headers) == ("closed", 1008)


def test_a_listed_cookie_still_passes_everything() -> None:
    cfg = listed_config()
    app = gated_app()
    cookie = cookie_of(cfg, USER)

    assert passed(http(app, "GET", "/", headers={**NAVIGATE, **cookie}))
    assert passed(http(app, "GET", "/_stcore/host-config", headers={**FETCH, **cookie}))
    assert websocket_connect(app, "/_stcore/stream", headers={**ORIGIN, **cookie}) == "accepted"


def test_an_open_connection_stops_at_the_next_message_off_the_list() -> None:
    """환경변수 명단은 연 뒤에 바뀌지 않지만 메시지마다 같은 판정을 지나므로(`session_check` 한
    곳) 설정을 그 자리에서 바꿔 그 길이 막히는지 본다 — 앱이 프레임을 받지 않는다. S3 명단에서 지운
    사람은 `test_sso_access_s3.py` 가 같은 길을 밟는다."""
    cfg = listed_config()
    ECHO_DISCONNECTS.clear()

    def drop_from_the_list(index: int) -> None:
        if index == 1:
            object.__setattr__(cfg, "access", build_access_list(ADMIN, "", enforced=True))

    sent = websocket_talk(
        gated_app(),
        "/_stcore/stream",
        headers={**ORIGIN, **cookie_of(cfg, USER)},
        frames=[b"before", b"after"],
        before_frame=drop_from_the_list,
    )

    echoed = [message["bytes"] for message in sent if message["type"] == "websocket.send"]
    assert echoed == [b"echo:before"]
    assert sent[-1]["type"] == "websocket.close" and sent[-1]["code"] == 1008
    assert ECHO_DISCONNECTS == [1008]
    closed = events_named("session_closed")
    assert [(item.value("reason"), item.value("loginid")) for item in closed] == [("denied", USER)]


def test_refresh_with_a_dropped_cookie_is_401_and_issues_nothing() -> None:
    cfg = listed_config()
    token, claims = issue_session(
        cfg, loginid=GONE, name=None, dept=None, now=int(time.time()) - 120
    )

    response = http(gated_app(), "POST", names.REFRESH_PATH, headers=refresh_headers(cfg, token))

    assert response.status == 401
    assert not response.set_cookies
    assert runtime.refresh_counts()["unauthorized"] == 1
    assert runtime.renewed_exp(claims.sid) is None


def test_refresh_for_a_listed_person_still_renews() -> None:
    cfg = listed_config()
    token, _ = issue_session(cfg, loginid=USER, name=None, dept=None, now=int(time.time()) - 120)

    response = http(gated_app(), "POST", names.REFRESH_PATH, headers=refresh_headers(cfg, token))

    assert response.status == 204
    assert has_live_session(cfg, response)


def test_the_login_path_sends_a_dropped_cookie_to_the_idp_not_to_next() -> None:
    cfg = listed_config()

    response = http(
        gated_app(),
        "GET",
        f"{names.LOGIN_PATH}?next=%2Fspace",
        headers={**NAVIGATE, **cookie_of(cfg, GONE)},
    )

    assert response.status == 302
    assert (response.header("location") or "").startswith(AUTHORIZE_URL)


def test_a_dropped_tab_goes_from_the_probe_through_the_banner_to_the_denied_page() -> None:
    """다시 붙기 스크립트의 탐침 401 → 띠의 「다시 로그인」 → IdP → 콜백 → 거절 화면. 끝에
    브라우저에 쿠키가 남지 않고, 거절은 콜백 한 곳에서 한 번 기록된다."""
    cfg = listed_config()
    app = gated_app()
    jar = {cfg.session_cookie: session_token(cfg, GONE)}

    probe = http(
        app, "GET", "/_stcore/host-config", headers={**FETCH, "cookie": cookie_header(jar)}
    )
    assert probe.status == 401, "이 답에만 띠가 선다(`sso_reconnect`)"
    assert runtime.denied_total() == 0, "탐침은 기록하지 않는다"

    state, nonce = start_login(app, jar, "/space?theme=dark")
    token = make_id_token(id_token_claims(nonce, loginid=GONE))
    callback = post_form(app, jar, token, state)
    assert callback.header("location") == DENIED_LOCATION
    apply_cookies(jar, callback)
    assert not jar

    location = urlsplit(callback.header("location") or "")
    page = http(app, "GET", f"{location.path}?{location.query}", headers=NAVIGATE)
    assert page.status == 403
    assert web.NOT_ON_LIST_TITLE in page.text
    assert runtime.denied_total() == 1


def _stop_script_app() -> AppTest:
    return AppTest.from_string(
        """
import streamlit as st

from capa_simulation.components import sso_identity

sso_identity.require_signed_in()
st.text("끝까지 돌았다")
"""
    )


def test_the_script_wall_stops_a_dropped_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = listed_config()
    runtime.mark_gate_installed()
    token = session_token(cfg, GONE)
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})
    monkeypatch.setattr(sso_identity, "current_page_url", lambda: None)

    app = _stop_script_app().run()

    assert not list(app.exception)
    assert [warning.value for warning in app.warning] == [web.NOT_ON_LIST_TEXT]
    assert not [element for element in app.text if element.value == "끝까지 돌았다"]
    assert f"{PUBLIC_URL}{names.LOGIN_PATH}?next=" in app.markdown[0].value
    assert_absent(app.markdown[0].value, GONE)


def test_the_real_app_stops_a_dropped_cookie_before_any_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    cfg = listed_config()
    runtime.mark_gate_installed()
    token = session_token(cfg, GONE)
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})

    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert [warning.value for warning in app.warning] == [web.NOT_ON_LIST_TEXT]
    assert "Capa LOB Summary" not in [element.value for element in app.title]
    assert not list(tmp_path.iterdir()), "멈춘 회차에는 DB 를 만들지 않는다"


# --- 거절 화면 --------------------------------------------------------------------------------


def _denied_page(target: str = f"{names.ERROR_PATH}?code=not_on_list") -> AsgiResponse:
    return http(gated_app(), "GET", target, headers=NAVIGATE)


def test_the_denied_page_opens_directly_and_says_only_the_fixed_text() -> None:
    listed_config()

    page = _denied_page()

    assert page.status == 403
    assert not page.set_cookies
    assert page.header("cache-control") == "no-store"
    assert web.NOT_ON_LIST_TITLE in page.text and web.NOT_ON_LIST_TEXT in page.text
    assert "요청:" not in page.text, "창구 글이 없으면 그 줄이 없다"
    assert f"{PUBLIC_URL}{names.LOGIN_PATH}?next=%2F" in page.text
    assert "다시 확인" in page.text
    assert "통합인증에서도 로그아웃" not in page.text


def test_the_denied_page_after_a_real_denial_carries_no_claim_value() -> None:
    listed_config()
    app = gated_app()
    jar: dict[str, str] = {}
    callback = sign_in(app, jar, GONE, username="데모 이름", deptname="데모 부서")

    location = urlsplit(callback.header("location") or "")
    page = http(app, "GET", f"{location.path}?{location.query}", headers=NAVIGATE)

    for value in (GONE, "데모 이름", "데모 부서", ADMIN, USER):
        assert value not in page.text, value
    assert "id" not in parse_qs(location.query), "진단을 보관하지 않는다"


def test_the_contact_is_escaped() -> None:
    listed_config({names.ENV_ACCESS_CONTACT: '<script>alert(1)</script> & "담당"'})

    page = _denied_page()

    assert "<script>" not in page.text
    assert "요청: &lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;담당&quot;" in page.text


def test_the_logout_link_appears_when_set() -> None:
    logout = "https://idp.example.invalid/adfs/oauth2/logout"
    listed_config({names.ENV_LOGOUT_URL: logout})

    page = _denied_page()

    assert f'href="{logout}"' in page.text and "통합인증에서도 로그아웃" in page.text


def test_the_reason_codes_stay_apart() -> None:
    """포털이 거절한 `access_denied` 는 오류 화면(400) 그대로, 명단은 `not_on_list` 하나다."""
    cfg = listed_config()

    assert "not_on_list" in web.allowed_reason_codes(cfg)
    portal = _denied_page(f"{names.ERROR_PATH}?code=idp_error:access_denied")
    assert portal.status == 400 and web.NOT_ON_LIST_TITLE not in portal.text
    made_up = _denied_page(f"{names.ERROR_PATH}?code=not_on_list2")
    assert made_up.status == 400 and "<code>unknown</code>" in made_up.text


def test_the_page_stays_when_the_list_is_not_enforced() -> None:
    """옛 링크로 열어도 500 이 나지 않는다 — 고정 글뿐이다."""
    environ = dev_environ()
    runtime.reset()
    runtime.start(environ)

    assert _denied_page().status == 403


# --- 값이 새지 않음 ---------------------------------------------------------------------------

STATUS_SCRIPT = """
from capa_simulation.components.sso_status import render_sso_status

render_sso_status()
"""


def _status_text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.warning]
    parts += [str(element.value) for element in app.error]
    parts += [frame.value.to_csv() for frame in app.dataframe]
    parts += [item.label for item in app.status] + [item.label for item in app.expander]
    return "\n".join(parts)


def test_repr_carries_no_list_value() -> None:
    cfg = listed_config({names.ENV_ACCESS_CONTACT: CONTACT})

    for text in (repr(cfg), repr(cfg.access), str(cfg.access)):
        for value in (ADMIN, USER, CONTACT):
            assert value not in text, value
    assert "AccessList(enforced=True" in repr(cfg)


def test_the_startup_events_and_log_carry_no_list_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime.reset()

    runtime.start(sso_environ({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER}))

    logged = capsys.readouterr().out
    assert "sso event=config" in logged, "진입 파일로 뜰 때의 stdout 로그를 본다"
    fields = " ".join(str(item.fields) for item in runtime.recent_events())
    assert_absent(logged + fields, ADMIN, USER)


def test_list_values_leave_the_environment_after_start() -> None:
    """앱이 띄우는 하위 프로세스(aws 등)와 `os.environ` 을 읽는 코드에 명단이 남지 않는다. 창구 글은
    공개 글이라 남아도 된다."""
    runtime.reset()
    environ = sso_environ(
        {
            names.ENV_ACCESS_ADMINS: ADMIN,
            names.ENV_ACCESS_USERS: USER,
            names.ENV_ACCESS_CONTACT: CONTACT,
        }
    )

    cfg = runtime.start(environ)

    assert names.ENV_SECRET not in environ
    assert names.ENV_ACCESS_ADMINS not in environ
    assert names.ENV_ACCESS_USERS not in environ
    assert environ[names.ENV_ACCESS_CONTACT] == CONTACT
    assert cfg.env_presence[names.ENV_ACCESS_ADMINS] and cfg.env_presence[names.ENV_ACCESS_USERS]
    assert cfg.access.allows(ADMIN) and cfg.access.allows(USER)
    assert runtime.start(environ) is cfg, "두 번째 부름은 처음 읽은 설정 그대로다"


def test_a_broken_setup_names_the_variable_without_any_value() -> None:
    cfg = use_config({names.ENV_ACCESS_ADMINS: rf"DOMAIN\{ADMIN}", names.ENV_ACCESS_USERS: USER})
    assert cfg.mode is SsoMode.BROKEN

    page = http(gated_app(), "GET", "/", headers=NAVIGATE)

    assert page.status == 200
    assert names.ENV_ACCESS_ADMINS in page.text
    assert "읽을 수 있는 loginid 가 하나도 없음" in page.text
    assert ADMIN not in page.text and USER not in page.text and "DOMAIN" not in page.text
    [event] = events_named("config")
    assert event.value("problems") == f"{names.ENV_ACCESS_ADMINS}:no_valid_entry"


def test_the_status_shows_counts_only() -> None:
    """Admin 점검 — 사실 줄은 개수, 표는 있음/없음, 사건은 앞 두 글자. 명단 값은 어디에도 없다."""
    cfg = use_config(
        {
            names.ENV_ACCESS_ADMINS: f"{ADMIN},demo.boss",
            names.ENV_ACCESS_USERS: rf"{USER},DOMAIN\demo.x",
            names.ENV_ACCESS_CONTACT: CONTACT,
        }
    )
    runtime.mark_gate_installed()
    gate_app = gated_app()
    denied = sign_in(gate_app, {}, GONE)
    assert not has_live_session(cfg, denied)

    app = AppTest.from_string(STATUS_SCRIPT).run()

    assert not list(app.exception)
    text = _status_text(app)
    assert_absent(text, ADMIN, "demo.boss", USER, "demo.x", GONE, CONTACT, "DOMAIN")
    assert "**접속 명단** · 켜짐 · 관리자 2 · 사용자 1 · 읽지 못함 1" in text
    environment = app.dataframe[0].value.set_index("환경변수")
    for name in (names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS, names.ENV_ACCESS_CONTACT):
        assert environment.loc[name, "상태"] == "있음"
    assert environment.loc[names.ENV_ACCESS_USERS, "까닭"] == "loginid 꼴이 아닌 항목이 있어 뺌"
    assert "login_denied" not in app.dataframe[1].value["사건"].tolist()
    assert "명단 밖 로그인(기동 뒤 누계 1 · 계정 1)" in text
    denied_table = app.dataframe[2].value
    assert denied_table["계정"].tolist() == ["de***"]
    assert denied_table["횟수"].tolist() == [1]


def test_the_status_has_no_denied_table_until_someone_is_denied() -> None:
    listed_config()
    runtime.mark_gate_installed()

    app = AppTest.from_string(STATUS_SCRIPT).run()

    assert not list(app.exception)
    assert sso_status.denied_account_line() is None
    assert "명단 밖 로그인" not in _status_text(app)
    assert len(app.dataframe) == 2, "환경변수 표 · 최근 사건 표만"


def test_the_on_caption_says_who_gets_in() -> None:
    """캡션과 바로 아래 사실 줄 「접속 명단」 이 어긋나지 않는다."""
    listed_config()
    runtime.mark_gate_installed()
    listed = _status_text(AppTest.from_string(STATUS_SCRIPT).run())
    assert "로그인하고 접속 명단에 있는 사람만 앱에 들어옵니다" in listed
    assert "**접속 명단** · 켜짐" in listed

    runtime.reset()
    runtime.start(dev_environ())
    runtime.mark_gate_installed()
    open_to_all = _status_text(AppTest.from_string(STATUS_SCRIPT).run())
    assert "접속 명단이 꺼져 있어 로그인한 사람은 모두 들어옵니다" in open_to_all
    assert "**접속 명단** · 꺼짐(인증된 사람 전부)" in open_to_all


def test_the_status_says_how_the_list_stands_in_each_mode() -> None:
    assert (
        sso_status.access_line(load_config(dev_environ()))
        == "**접속 명단** · 꺼짐(인증된 사람 전부)"
    )
    off_in_production = load_config(sso_environ(drop=[names.ENV_CLIENT_ID]))
    assert off_in_production.mode is SsoMode.OFF
    assert sso_status.access_line(off_in_production).startswith(
        "**접속 명단** · 통합인증이 켜지면 적용 · 관리자 1 · 사용자 1 · 읽지 못함 0"
    )
    blocked = load_config(sso_environ(drop=[names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS]))
    assert sso_status.access_line(blocked).startswith(
        "**접속 명단** · 통합인증이 켜지면 적용 · 관리자 0"
    )


def test_the_status_keeps_the_last_claim_names_without_values() -> None:
    """검증을 지난 마지막 로그인(거절 포함)의 이름만 — 그룹 클레임이 오는지 여기서 본다."""
    listed_config()
    runtime.mark_gate_installed()
    assert sso_status.last_claims_line().endswith("아직 없음")

    sign_in(gated_app(), {}, GONE, groups=["demo.group"], username="데모 이름")

    assert "groups" in runtime.last_login_claims()
    assert "loginid" in runtime.last_login_claims()
    line = sso_status.last_claims_line()
    assert "groups" in line
    assert_absent(line, "demo.group", GONE, "데모 이름")

    app = AppTest.from_string(STATUS_SCRIPT).run()

    assert not list(app.exception)
    assert line in _status_text(app)
    assert_absent(_status_text(app), "demo.group")


def test_a_failed_token_does_not_touch_the_last_claim_names() -> None:
    listed_config()
    app = gated_app()
    jar: dict[str, str] = {}
    state, nonce = start_login(app, jar)
    token = make_id_token(id_token_claims(nonce, loginid=USER), drop=["iss"])

    assert error_code_of(post_form(app, jar, token, state)) == "iss_mismatch"
    assert runtime.last_login_claims() == ()


def test_reset_forgets_the_last_claim_names() -> None:
    runtime.note_login_claims(("a", "b"))
    assert runtime.last_login_claims() == ("a", "b")

    runtime.reset()

    assert runtime.last_login_claims() == ()
