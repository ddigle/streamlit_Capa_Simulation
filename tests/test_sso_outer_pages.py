# Purpose: 앱 밖 화면(로그인 실패·되풀이·로그아웃·설정 막힘)의 글·갈래·쿠키·next·누계를 지킨다.

"""「앱 대신 뜨는 화면」 보드 카드 p1-login-fail · p1-logout · p2-config · work-next 1 ·
critic-missing 1 · 5(2026-11-14 답 「좋음」).

화면은 공통 틀(`auth/page_frame.py`)이다 — 위는 누구나 읽는 글(표지 · 제목 · 까닭 · 단추 · 문의 줄),
바닥에 「참고 사유 코드 · 시각(· 진단 번호)」, 아래 접힌 「개발자용 진단」. 값 · 토큰은 싣지 않는다.
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
from asgi_driver import AsgiResponse, http
from sso_support import (
    CLIENT_ID,
    PUBLIC_URL,
    expiring_signing,
    id_token_claims,
    make_id_token,
    sso_secret,
    use_config,
)
from starlette.applications import Starlette

from capa_simulation.audit import read as audit_read
from capa_simulation.auth import names, page_frame, runtime, web
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.gate import SsoGate
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import STATE_TTL, issue_state
from capa_simulation.components import sso_identity, sso_reconnect, sso_status
from capa_simulation.components.diagnostic_copy import ADMIN_DIAGNOSTIC_LABEL
from capa_simulation.settings import APP_CONTACT_EMAIL_ENV

FORM = {"content-type": "application/x-www-form-urlencoded"}
# 브라우저가 주소창 · 링크로 연 문서 탐색의 머리(로그인 시작 누계가 세는 요청).
BROWSER = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none"}
# 쿠키 꾸러미 안에 함께 드는 마지막 state(쿠키가 아니다 — 콜백에 보내지 않는다).
STATE_KEY = "~state"
CONTACT_EMAIL = "help@example.com"
# KST 2026-11-14 14:30:20 — 「○시 ○분」 올림을 보는 고정 시각.
FIXED_NOW = int(datetime(2026, 11, 14, 14, 30, 20, tzinfo=page_frame.KST).timestamp())


@pytest.fixture(autouse=True)
def _contact(monkeypatch: pytest.MonkeyPatch) -> None:
    """문의 메일이 있는 서버가 기본이다(「문의처」 글이 그대로 선다)."""
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, CONTACT_EMAIL)


def routes_app() -> Starlette:
    return Starlette(routes=sso_routes())


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def begin(app: Starlette, cfg: SsoConfig, jar: dict[str, str], next_path: str = "/") -> str:
    """브라우저의 로그인 시작 — 받은 쿠키를 `jar` 에 담고 (state, nonce) 가운데 nonce 를
    돌려준다."""
    cookies = {name: value for name, value in jar.items() if name != STATE_KEY}
    headers = {**BROWSER, "cookie": cookie_header(cookies)} if cookies else dict(BROWSER)
    response = http(
        app, "GET", f"{names.LOGIN_PATH}?next={quote(next_path, safe='')}", headers=headers
    )
    assert response.status == 302, response.text
    apply(jar, response)
    query = parse_qs(urlsplit(response.header("location") or "").query)
    jar[STATE_KEY] = query["state"][0]
    return query["nonce"][0]


def apply(jar: dict[str, str], response: AsgiResponse) -> None:
    for cookie in response.set_cookies:
        if cookie.deleted:
            jar.pop(cookie.name, None)
        else:
            jar[cookie.name] = cookie.value


def callback(app: Starlette, jar: dict[str, str], token: str) -> AsgiResponse:
    state = jar[STATE_KEY]
    cookies = {name: value for name, value in jar.items() if name != STATE_KEY}
    headers = {**FORM, "cookie": cookie_header(cookies)} if cookies else dict(FORM)
    body = urlencode({"id_token": token, "state": state}).encode()
    response = http(app, "POST", names.CALLBACK_PATH, headers=headers, body=body)
    apply(jar, response)
    return response


def follow(app: Starlette, response: AsgiResponse) -> AsgiResponse:
    assert response.status == 303, response.text
    parts = urlsplit(response.header("location") or "")
    return http(app, "GET", f"{parts.path}?{parts.query}")


def query_of(response: AsgiResponse) -> dict[str, str]:
    location = response.header("location") or ""
    return {key: values[0] for key, values in parse_qs(urlsplit(location).query).items()}


def main_part(page: AsgiResponse) -> str:
    """머리 · 본문 · 단추 · 참고 줄 — 접힌 진단 앞까지."""
    body = page.text.split("<main>", 1)[1]
    return body.split(f"<details><summary>{page_frame.DIAGNOSTIC_LABEL}", 1)[0]


def admin_part(page: AsgiResponse) -> str:
    """접힌 「개발자용 진단」 안."""
    marker = f"<details><summary>{page_frame.DIAGNOSTIC_LABEL}</summary>"
    assert marker in page.text, "접힌 개발자용 진단이 있다"
    return page.text.split(marker, 1)[1]


def hrefs(page: AsgiResponse, label: str) -> list[str]:
    return [
        html.unescape(found)
        for found in re.findall(rf'href="([^"]*)">{re.escape(label)}</a>', page.text)
    ]


def button_hrefs(page: AsgiResponse) -> list[str]:
    return [
        html.unescape(found) for found in re.findall(r'<a class="button" href="([^"]*)"', page.text)
    ]


def next_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["next"][0]


# --- 갈래 ---------------------------------------------------------------------------------


def test_every_failure_code_this_server_makes_has_a_kind() -> None:
    """이 서버가 내는 로그인 실패 사유 코드는 모두 잠시 · 설정 · 쿠키 없음 가운데 하나다 — 「모름」
    은 주소에 넣은 다른 글뿐이다. 거절 갈래 · 포털 거절은 오류 화면이 아니다."""
    cfg = use_config()
    failures = web.allowed_reason_codes(cfg) - {*web.DENIED_CODES, web.PORTAL_REFUSED}

    kinds = {code: web.failure_kind(code) for code in failures}

    assert web.KIND_UNKNOWN not in kinds.values(), kinds
    assert kinds[web.NO_COOKIES] == web.KIND_NO_COOKIES
    assert {kinds[code] for code in ("state_missing", "state_invalid", "state_reused")} == {
        web.KIND_RETRY
    }
    for code in ("aud_mismatch", "signature_invalid", "token_expired", "claim_missing:loginid"):
        assert kinds[code] == web.KIND_SETUP, code
    assert kinds["idp_error:temporarily_unavailable"] == web.KIND_RETRY
    assert kinds["idp_error:invalid_client"] == web.KIND_SETUP
    assert web.failure_kind(web.UNKNOWN) == web.KIND_UNKNOWN
    assert web.failure_kind("zzz") == web.KIND_UNKNOWN


def test_a_setup_failure_reads_maintenance_and_folds_the_reason_and_the_table() -> None:
    """설정 문제(다른 앱 등록 번호 — aud): 표지 「점검 중」 · 「로그인 설정에 문제가 있습니다」,
    「다시 시도」 는 보조 링크(주 단추 없음). 사유 한 줄 · 진단 표는 접힌 진단 안, 바닥에 「참고
    사유 코드 · 시각 · 진단 번호」. 시도 쿠키를 지운다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    nonce = begin(app, cfg, jar, "/space?theme=dark")
    token = make_id_token(id_token_claims(nonce, aud="someone-else"))

    response = callback(app, jar, token)
    page = follow(app, response)

    query = query_of(response)
    assert query["code"] == "aud_mismatch" and query["next"] == "/space?theme=dark"
    attempt = response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.deleted, "고쳐지지 않는 실패 — 되풀이를 세지 않는다"
    assert page.status == 400
    top = main_part(page)
    assert f">{page_frame.CHIP_WORDS['maintenance']}</span>" in top
    assert f"<h1>{web.LOGIN_SETUP_TITLE}</h1>" in top
    assert f"<p>{web.LOGIN_SETUP_TEXT}</p>" in top
    assert button_hrefs(page) == [], "다시 시도는 보조 링크다"
    [retry] = hrefs(page, web.RETRY_LABEL)
    assert next_of(retry) == "/space?theme=dark", "처음 가려던 화면으로"
    assert "참고 aud_mismatch · " in top and f" · 진단 {query['id']}</span>" in top
    for word in (web.reason_text("aud_mismatch"), "someone-else", CLIENT_ID, "<table>"):
        assert word not in top, f"위층에는 운영 낱말 · 값이 없다 — {word}"
    folded = admin_part(page)
    assert web.reason_text("aud_mismatch") in folded
    assert "<table>" in folded and "someone-else" in folded and CLIENT_ID in folded
    for value in (token, sso_secret(), "개발 사용자", "개발부서"):
        assert value not in page.text


def test_a_temporary_failure_keeps_counting_and_retries_to_the_first_screen() -> None:
    """잠시 문제(짝이 다른 토큰 — 다른 탭의 로그인): 표지 「다시 시도」 · 「로그인을 마치지
    못했습니다」 · 주 단추 「다시 시도」(처음 가려던 화면). 시도 쿠키는 그대로 센다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    begin(app, cfg, jar, "/process_detail?process=P1")

    response = callback(app, jar, make_id_token(id_token_claims("another-tab-nonce")))
    page = follow(app, response)

    assert query_of(response)["code"] == "nonce_mismatch"
    assert response.cookie(cfg.attempt_cookie) is None, "잠시 문제는 시도 쿠키를 건드리지 않는다"
    top = main_part(page)
    assert f">{page_frame.CHIP_WORDS['retry']}</span>" in top
    assert f"<h1>{web.LOGIN_FAILED_TITLE}</h1>" in top
    assert f"<p>{web.LOGIN_RETRY_TEXT}</p>" in top
    [button] = button_hrefs(page)
    assert button.startswith(f"{PUBLIC_URL}{names.LOGIN_PATH}?")
    assert next_of(button) == "/process_detail?process=P1"


def test_no_cookie_at_all_is_its_own_case() -> None:
    """콜백에 이 앱의 쿠키가 하나도 오지 않음(다른 주소로 시작 · 쿠키 막힘) — 시작 정보 없음과
    가르고 주소창 주소 · 쿠키 설정을 보라고 한다. 개발자용 진단은 10분 넘게 머문 때와 가르지 못함을
    말한다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    nonce = begin(app, cfg, jar)
    jar = {STATE_KEY: jar[STATE_KEY]}

    response = callback(app, jar, make_id_token(id_token_claims(nonce)))
    page = follow(app, response)

    assert query_of(response)["code"] == web.NO_COOKIES
    top = main_part(page)
    assert f"<h1>{web.LOGIN_FAILED_TITLE}</h1>" in top
    assert f"<p>{web.NO_COOKIES_TEXT}</p>" in top
    assert button_hrefs(page), "다시 시도(공개 주소로 다시 시작하면 다른 주소 문제는 풀린다)"
    assert "10분" in admin_part(page)
    attempt = response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.deleted, "고쳐지지 않는 실패 — 되풀이를 세지 않는다"
    [event] = [item for item in runtime.recent_events() if item.value("reason") == web.NO_COOKIES]
    assert event.event == "login_fail"


def test_lingering_on_the_portal_reads_as_time_passed_not_as_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """통합인증 화면에 10분 넘게 머문 뒤 로그인 — 시도 쿠키(2분)는 사라졌지만 상태 쿠키는 토큰보다
    오래 살아(1시간) 실려 온다. 쿠키 설정 탓으로 말하지 않고 「시간이 지남」(잠시 문제)이며,
    늦은 토큰으로 로그인되지 않는다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    nonce = begin(app, cfg, jar, "/space")
    token = make_id_token(id_token_claims(nonce))
    later = int(time.time()) + STATE_TTL + 60
    assert STATE_TTL + 60 < web.STATE_COOKIE_TTL, "상태 쿠키는 아직 산다"
    jar.pop(cfg.attempt_cookie)
    monkeypatch.setattr(web, "_now", lambda: later)

    response = callback(app, jar, token)
    page = follow(app, response)

    assert query_of(response)["code"] == "state_invalid"
    assert web.failure_kind("state_invalid") == web.KIND_RETRY
    assert cfg.session_cookie not in jar, "늦은 토큰으로는 들어오지 않는다"
    assert f"<p>{web.LOGIN_RETRY_TEXT}</p>" in main_part(page)
    assert web.NO_COOKIES_TEXT not in page.text


def test_a_failure_event_carries_the_diagnostic_reference_for_the_admin() -> None:
    """바닥 참고 줄의 「진단 <번호>」 를 받은 관리자가 Admin 「통합인증 점검」 의 사건 줄(통합인증이
    켜진 서버는 펼침의 「복사」 글)에서 같은 번호를 찾는다 — 사건에는 앞 여덟 글자만(번호 전체는
    10분 동안 진단을 다시 여는 주소 값)."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    begin(app, cfg, jar)

    response = callback(app, {STATE_KEY: jar[STATE_KEY]}, "x")
    page = follow(app, response)

    full = query_of(response)["id"]
    assert len(full) > web.DIAGNOSTIC_REF_LENGTH == 8
    assert f" · 진단 {full}</span>" in main_part(page)
    [event] = runtime.recent_events(anonymous=True)
    assert event.value("diag") == full[:8]
    assert full not in str(event.fields)
    rows = sso_status.recent_event_table(anonymous=True)
    assert list(rows["사유 코드"]) == [f"{web.NO_COOKIES} · 진단 {full[:8]}"]
    copied = sso_status.status_text("통합인증 점검", cfg, now=datetime.now(timezone.utc))
    assert f"\t{web.NO_COOKIES} · 진단 {full[:8]}\t" in copied, (
        "감사 기록이 켜진 서버는 복사 글에서 찾는다"
    )
    assert full not in copied


@pytest.mark.parametrize(
    ("headers", "body", "code", "status"),
    [
        ({"content-type": "text/plain"}, b"x=1", "bad_content_type", 415),
        ({**FORM, "content-length": str(64 * 1024 + 1)}, b"a=1", "body_too_large", 413),
        (FORM, b"a=1&a=2", "bad_form", 303),
    ],
)
def test_a_malformed_callback_stops_counting_attempts(
    headers: dict[str, str], body: bytes, code: str, status: int
) -> None:
    """콜백 꼴이 틀림(설정 문제 — 다시 해도 같음) — 시도 쿠키를 지운다."""
    cfg = use_config()
    cookies = {cfg.attempt_cookie: web.attempt_value(2, int(time.time()))}

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers={**headers, "cookie": cookie_header(cookies)},
        body=body,
    )

    assert response.status == status
    assert web.failure_kind(code) == web.KIND_SETUP
    assert (query_of(response).get("code") if status == 303 else code) == code
    if status != 303:
        assert code in response.text
    attempt = response.cookie(cfg.attempt_cookie)
    assert attempt is not None and attempt.deleted


@pytest.mark.parametrize("stored", ["forged", "expired", "other_state"])
def test_an_idp_error_with_an_unusable_state_cookie_goes_back_to_the_first_screen(
    stored: str,
) -> None:
    """IdP 오류의 「다시 시도」 는 그 상태 쿠키의 next 를 쓴다 — 쿠키가 위조 · 만료 · 다른 state 의
    것이면 `/` 이고, 이 앱이 시작한 로그인으로 세지 않는다(돌아옴 누계 그대로)."""
    cfg = use_config()
    state = "S" * 43
    now = int(time.time())
    values = {
        "forged": issue_state(cfg, state=state, nonce="n" * 43, next_path="/space", now=now)[:-4]
        + "AAAA",
        "expired": issue_state(
            cfg, state=state, nonce="n" * 43, next_path="/space", now=now - STATE_TTL - 10
        ),
        "other_state": issue_state(
            cfg, state="T" * 43, nonce="n" * 43, next_path="/space", now=now
        ),
    }

    response = http(
        routes_app(),
        "POST",
        names.CALLBACK_PATH,
        headers={**FORM, "cookie": cookie_header({cfg.state_cookie(state): values[stored]})},
        body=urlencode({"error": "access_denied", "state": state}).encode(),
    )

    assert "next" not in query_of(response), "처음 가려던 화면은 / (주소에 싣지 않음)"
    assert runtime.login_flow_counts() == (0, 0)


def test_a_used_state_is_remembered_until_its_end_and_not_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """쓴 state 는 그 상태 토큰의 끝까지(그 초 포함) 재사용으로 읽고, 그 뒤에는 잊는다."""
    runtime.reset()
    moment = [1_000_000]
    monkeypatch.setattr(runtime, "_now", lambda: moment[0])
    assert runtime.remember_used_state("d" * 64, 1_000_600)

    assert runtime.state_used("d" * 64)
    assert not runtime.remember_used_state("d" * 64, 1_000_600), "끝 전에는 재사용"
    moment[0] = 1_000_600
    assert runtime.state_used("d" * 64), "끝 그 초까지"
    moment[0] = 1_000_601
    assert not runtime.state_used("d" * 64)
    assert runtime.remember_used_state("d" * 64, 1_001_201), "끝난 뒤에는 처음처럼"


def test_back_after_a_login_is_a_reuse_not_a_cookie_problem() -> None:
    """로그인을 마친 뒤 브라우저 「뒤로」 — IdP 화면이 같은 state 를 쿠키 없이 다시 보낸다(성공이
    상태 · 시도 쿠키를 지우고 세션 쿠키는 교차 사이트 POST 에 실리지 않는다). 쿠키 문제로 말하지
    않고 재사용 (잠시 문제)이다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    nonce = begin(app, cfg, jar, "/voc")
    token = make_id_token(id_token_claims(nonce))
    assert callback(app, jar, token).status == 303
    assert cfg.session_cookie in jar

    replay = callback(app, {STATE_KEY: jar[STATE_KEY]}, token)

    assert query_of(replay)["code"] == "state_reused"
    assert web.failure_kind("state_reused") == web.KIND_RETRY
    page = follow(app, replay)
    assert f"<p>{web.LOGIN_RETRY_TEXT}</p>" in main_part(page)
    assert web.NO_COOKIES_TEXT not in page.text


def test_retrying_a_setup_failure_never_reaches_the_loop_page() -> None:
    """고쳐지지 않는 실패에서 「다시 시도」 를 몇 번 눌러도 되풀이 화면으로 잘못 가지 않는다 —
    실패가 시도 쿠키를 지운다(그 쿠키는 「마지막 시작 뒤 2분 안에 또 시작」 을 센다)."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}

    for _ in range(5):
        nonce = begin(app, cfg, jar)
        assert web.attempt_record(jar[cfg.attempt_cookie])[0] == 1
        response = callback(app, jar, make_id_token(id_token_claims(nonce, aud="other-app")))
        assert query_of(response)["code"] == "aud_mismatch"
        assert cfg.attempt_cookie not in jar


def test_repeated_temporary_failures_reach_the_loop_page_with_a_time_and_a_button() -> None:
    """잠시 문제를 2분 안에 되풀이하면 넷째 시작이 되풀이 화면이다 — 표지 「다시 시도」 · 까닭(여러
    탭 · 되풀이) · 「○시 ○분 뒤에 「다시 시도」 를 누르세요」(KST, 지금 + 2분을 분 올림) · 주 단추
    「다시 시도」(처음 가려던 화면). IdP 로 보내지 않는다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    for _ in range(web.MAX_LOGIN_ATTEMPTS):
        begin(app, cfg, jar, "/space")
        callback(app, jar, make_id_token(id_token_claims("another-tab-nonce")))
    count, last_start = web.attempt_record(jar[cfg.attempt_cookie])
    assert count == web.MAX_LOGIN_ATTEMPTS and last_start is not None
    third = web.attempt_value(count, FIXED_NOW)

    page = web.start_login(cfg, {cfg.attempt_cookie: third}, "/space", FIXED_NOW, browser=True)

    text = bytes(page.body).decode("utf-8")
    assert page.status_code == 200 and page.headers.get("location") is None
    assert f"<h1>{web.LOOP_TITLE}</h1>" in text
    assert f"<p>{web.LOOP_TEXT}</p>" in text
    assert "<p>14시 33분 뒤에 「다시 시도」 를 누르세요.</p>" in text
    [button] = re.findall(r'<a class="button" href="([^"]*)">다시 시도</a>', text)
    assert next_of(html.unescape(button)) == "/space"
    assert "참고 login_loop · " in text
    assert "쿠키" not in text.split("<details>", 1)[0], "원인을 쿠키로 단정하지 않는다"
    assert not any(
        cookie.startswith(cfg.state_cookie_prefix) for cookie in page.headers.getlist("set-cookie")
    )


@pytest.mark.parametrize(
    ("value", "seen_at", "clock"),
    [
        (f"3.{FIXED_NOW - 30}", FIXED_NOW, "14시 32분"),
        (f"3.{FIXED_NOW - 30}", FIXED_NOW + 50, "14시 32분"),
        ("3", FIXED_NOW, "14시 33분"),
        ("3.0", FIXED_NOW, "14시 31분"),
        (f"3.{FIXED_NOW + 9999}", FIXED_NOW, "14시 33분"),
    ],
)
def test_the_loop_clock_is_when_the_attempt_cookie_ends_and_does_not_move(
    value: str, seen_at: int, clock: str
) -> None:
    """기다릴 시각은 마지막 시작 + 2분(시도 쿠키가 사라지는 때)이라 화면을 다시 봐도 밀리지 않는다.
    시각이 없는 옛 꼴은 지금 + 2분, 서명하지 않은 값이라 지금 ~ 지금 + 2분으로 좁힌다(14:30:20)."""
    cfg = use_config()

    page = web.start_login(cfg, {cfg.attempt_cookie: value}, "/", seen_at)

    text = bytes(page.body).decode("utf-8")
    assert f"<p>{clock} 뒤에 「다시 시도」 를 누르세요.</p>" in text
    assert not page.headers.getlist("set-cookie"), "되풀이 화면은 시도 쿠키를 다시 심지 않는다"


def test_the_loop_code_on_the_error_path_shows_the_loop_page() -> None:
    use_config()

    page = http(routes_app(), "GET", f"{names.ERROR_PATH}?code=login_loop&next=%2Fspace")

    assert page.status == 200 and f"<h1>{web.LOOP_TITLE}</h1>" in page.text
    assert next_of(button_hrefs(page)[0]) == "/space"


def test_the_clock_is_korean_time_and_rounds_up() -> None:
    assert page_frame.KST.utcoffset(None) == audit_read.KST.utcoffset(None)
    exact = int(datetime(2026, 11, 14, 9, 5, 0, tzinfo=page_frame.KST).timestamp())
    assert page_frame.clock_text(exact) == "9시 5분"
    assert page_frame.clock_text(exact, round_up=True) == "9시 5분"
    assert page_frame.clock_text(exact + 1, round_up=True) == "9시 6분"
    late = int(datetime(2026, 11, 14, 23, 59, 30, tzinfo=page_frame.KST).timestamp())
    assert page_frame.clock_text(late, round_up=True) == "0시 0분"


# --- 처음 가려던 화면 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("/space?theme=dark", "/space?theme=dark"),
        ("//evil.example.invalid/x", "/"),
        ("https://evil.example.invalid/", "/"),
        ("/auth/sso/logout", "/"),
        ("/%2e%2e/x", "/"),
    ],
)
def test_the_error_page_keeps_next_only_inside_the_app(raw: str, kept: str) -> None:
    """오류 주소의 `next` 는 로그인 없이 바꿀 수 있다 — 단추에 싣기 전에 다시 정화한다(같은 출처의
    앱 경로만, 열린 리다이렉트 없음). 화면 글로는 싣지 않는다."""
    use_config()

    page = http(
        routes_app(),
        "GET",
        f"{names.ERROR_PATH}?{urlencode({'code': 'state_missing', 'next': raw})}",
    )

    [button] = button_hrefs(page)
    assert button.startswith(f"{PUBLIC_URL}{names.LOGIN_PATH}?")
    assert next_of(button) == kept
    assert "evil" not in page.text


def test_the_portal_refusal_retry_keeps_the_first_screen() -> None:
    """IdP 오류는 상태 검증 전에 실패한다 — 그 상태 쿠키의 next 를 꺼내 「다시 시도」 에 싣는다."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    begin(app, cfg, jar, "/space")
    cookies = {name: value for name, value in jar.items() if name != STATE_KEY}

    response = http(
        app,
        "POST",
        names.CALLBACK_PATH,
        headers={**FORM, "cookie": cookie_header(cookies)},
        body=urlencode({"error": "access_denied", "state": jar[STATE_KEY]}).encode(),
    )
    page = follow(app, response)

    assert query_of(response)["next"] == "/space"
    assert page.status == 403 and web.PORTAL_TITLE in page.text
    [retry] = hrefs(page, web.RETRY_LABEL)
    assert next_of(retry) == "/space"


@pytest.mark.parametrize("logout_url", ["", "https://idp.example.invalid/adfs/oauth2/logout"])
def test_the_portal_refusal_main_button_is_another_account_only_with_a_logout_address(
    logout_url: str,
) -> None:
    """포털 거절은 다시 해도 같다 — 통합인증 로그아웃 주소가 있으면 주 단추가 「다른 계정으로
    로그인」 이고 「다시 시도」 는 보조 링크다. 없는 서버는 다른 계정으로 갈 길이 없어 「다시
    시도」 가 주 단추다(2026-11-14 보드 decided 4 · 공통 틀 「주 단추는 늘 있다」)."""
    cfg = use_config({names.ENV_LOGOUT_URL: logout_url} if logout_url else None)
    app = routes_app()
    jar: dict[str, str] = {}
    begin(app, cfg, jar, "/space")
    cookies = {name: value for name, value in jar.items() if name != STATE_KEY}

    page = follow(
        app,
        http(
            app,
            "POST",
            names.CALLBACK_PATH,
            headers={**FORM, "cookie": cookie_header(cookies)},
            body=urlencode({"error": "access_denied", "state": jar[STATE_KEY]}).encode(),
        ),
    )

    assert page.status == 403 and web.PORTAL_TITLE in page.text
    [main_button] = button_hrefs(page)
    [retry] = hrefs(page, web.RETRY_LABEL)
    assert next_of(retry) == "/space"
    if logout_url:
        assert main_button == logout_url
        assert hrefs(page, web.OTHER_ACCOUNT_LABEL) == [logout_url]
        assert f'<a class="button" href="{html.escape(retry)}">' not in page.text
    else:
        assert main_button == retry
        assert web.OTHER_ACCOUNT_LABEL not in page.text


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("/space?theme=dark", "/space?theme=dark"),
        ("//evil.example.invalid", "/"),
        ("javascript:alert(1)", "/"),
        ("", "/"),
    ],
)
def test_logout_goes_back_to_the_screen_before_logout(raw: str, kept: str) -> None:
    """「로그아웃했습니다」 — 표지 없음 · 본문 카드 글 · 「다시 들어가기」 가 로그아웃 전에 보던
    화면 (정화한 `next`)으로 · 문의 줄. 통합인증 로그아웃 주소가 없으면 보조 링크도 없다."""
    use_config()

    page = http(routes_app(), "GET", f"{names.LOGOUT_PATH}?{urlencode({'next': raw})}")

    top = main_part(page)
    assert '<span class="chip"' not in top
    assert f"<h1>{web.LOGOUT_TITLE}</h1>" in top and f"<p>{web.LOGOUT_TEXT}</p>" in top
    assert button_hrefs(page) == [f"{PUBLIC_URL}{kept}"]
    assert f'href="mailto:{CONTACT_EMAIL}"' in top
    assert web.OTHER_ACCOUNT_LABEL not in page.text
    assert "evil" not in page.text and "javascript" not in page.text


def test_the_logout_text_names_the_band_the_other_tabs_show() -> None:
    """다른 탭은 저절로 로그인 화면으로 가지 않는다 — 다음 누름에 띠가 서고 사람이 그 띠의
    「다시 로그인」 을 누른다. 로그아웃 화면 글은 그 띠의 링크 이름을 그대로 쓰고, 통합인증까지
    끝내는 법은 Guide · 안내 문서에만 둔다(2026-11-14 보드 logout · UI-CON-02)."""
    use_config()

    page = http(routes_app(), "GET", names.LOGOUT_PATH)

    band = sso_reconnect.band_texts()[names.REASON_OTHER]["label"]
    assert band == sso_identity.LOGIN_AGAIN_LABEL
    assert f"「{band}」" in web.LOGOUT_TEXT
    assert f"<p>{web.LOGOUT_TEXT}</p>" in main_part(page)
    assert "로그인 화면으로 갑니다" not in page.text
    assert "통합인증" not in web.LOGOUT_TEXT


# --- 설정 막힘 ----------------------------------------------------------------------------


def test_the_setup_page_says_maintenance_first_and_folds_the_admin_list_on_top() -> None:
    """관리자 목록이 빠진 운영 서버(첫 배포에서 가장 흔한 실수) — 위는 누구나 읽는 「점검 중 ·
    지금은 앱을 열 수 없습니다」 + 「다시 열기」(지금 문서) · 문의 줄 · 참고 번호. 접힌 진단 맨 위가
    「고칠 것 n개」 이고 첫 줄이 관리자 목록 카드 글이며, 그 아래 다시 접힌 「환경변수 전체(n)」 에
    표 · 계산한 주소 · 인증서. 값은 없다."""
    use_config(drop=[names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS])

    page = http(routes_app(), "GET", names.LOGIN_PATH)

    assert page.status == 503
    top = main_part(page)
    assert f">{page_frame.CHIP_WORDS['maintenance']}</span>" in top
    assert f"<h1>{web.CONFIG_TITLE}</h1>" in top and f"<p>{web.CONFIG_TEXT}</p>" in top
    assert '<a class="button" href="">다시 열기</a>' in top
    assert "참고 config_broken · " in top and f'href="mailto:{CONTACT_EMAIL}"' in top
    assert names.ENV_ACCESS_ADMINS not in top, "환경변수 이름은 접힌 진단 안에만"
    folded = admin_part(page)
    outer = folded.split("<details>", 1)[0]
    assert outer.startswith("<p>통합인증 설정을 마치지 못했습니다 — 고칠 것 1개</p><ul>")
    items = re.findall(r"<li>(.*?)</li>", outer)
    assert items == [html.escape(web.CONFIG_ADMINS_TEXT)], "「1개」 아래 글머리는 하나"
    assert html.escape(web.CONFIG_HOW_TO) not in outer
    fold = folded.split("<details>", 1)[1]
    total = len(names.SSO_ENVIRONMENT)
    assert fold.startswith(f"<summary>환경변수 전체({total})</summary><table>")
    for name in names.SSO_ENVIRONMENT:
        assert f"<td><code>{name.replace('_', '_<wbr>')}</code></td>" in fold
    facts = fold.split("</table>", 1)[1]
    redirect = f"<td>계산한 redirect_uri</td><td><code>{PUBLIC_URL}/auth/callback</code></td>"
    assert redirect in facts and "<td>서명 인증서 x5t</td><td><code>" in facts
    assert "<td>서명 인증서 SHA-256</td><td><code>" in facts and "<wbr>" not in facts
    assert re.search(r"<td>서명 인증서 만료</td><td><code>\d{4}-\d{2}-\d{2}</code></td>", facts)
    assert "<td>서명 인증서 키</td><td><code>RSA 2048비트</code></td>" in facts
    lines = re.findall(r"<li>(.*?)</li>", facts)
    assert lines == [html.escape(web.CONFIG_REDIRECT_NOTE), html.escape(web.CONFIG_HOW_TO)]
    assert sso_secret() not in page.text and CLIENT_ID not in page.text


def test_the_setup_page_counts_each_variable_to_fix_once() -> None:
    use_config(drop=[names.ENV_ISSUER, names.ENV_SIGNING_CERT])

    page = http(routes_app(), "GET", names.LOGIN_PATH)

    outer = admin_part(page).split("<details>", 1)[0]
    assert outer.startswith("<p>통합인증 설정을 마치지 못했습니다 — 고칠 것 2개</p><ul>")
    items = re.findall(r"<li>(.*?)</li>", outer)
    assert len(items) == 2
    assert any(item.startswith(names.ENV_ISSUER) for item in items)
    assert any(item.startswith(names.ENV_SIGNING_CERT) for item in items)
    assert web.CONFIG_ADMINS_TEXT not in page.text
    facts = admin_part(page).split("<details>", 1)[1].split("</table>", 1)[1]
    assert f"<td>{names.ENV_ISSUER} 후보</td><td><code>" in facts
    assert html.escape(web.CONFIG_ISSUER_NOTE) in facts


def test_the_setup_page_puts_a_notice_beside_its_variable() -> None:
    """막지 않는 알림(서명 인증서 만료가 30일 안)은 Admin 「통합인증 점검」 표처럼 그 환경변수 줄의
    까닭 칸에 붙는다 — 이름은 그 줄에서 글자 그대로다."""
    use_config(
        {names.ENV_SIGNING_CERT: expiring_signing().der_b64},
        drop=[names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS],
    )

    page = http(routes_app(), "GET", names.LOGIN_PATH)

    fold = admin_part(page).split("<details>", 1)[1]
    name = names.ENV_SIGNING_CERT.replace("_", "_<wbr>")
    [row] = re.findall(rf"<tr><td><code>{re.escape(name)}</code></td>(.*?)</tr>", fold)
    assert row.startswith("<td>있음</td><td>") and "30일" in row
    assert "알림 · " not in fold


def test_without_any_contact_the_contact_sentences_point_at_the_app_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """문의 줄이 서지 않는 서버(두 칸 모두 빔)는 「문의처」 를 가리키지 않는다 — 앱 관리자에게."""
    monkeypatch.delenv(APP_CONTACT_EMAIL_ENV, raising=False)
    use_config(drop=[names.ENV_ACCESS_ADMINS, names.ENV_ACCESS_USERS])
    config = http(routes_app(), "GET", names.LOGIN_PATH)
    use_config()
    setup = http(routes_app(), "GET", f"{names.ERROR_PATH}?code=aud_mismatch")

    for page, text in ((config, web.CONFIG_TEXT), (setup, web.LOGIN_SETUP_TEXT)):
        assert text not in page.text
        assert web.NO_CONTACT_TEXT[text] in page.text
        assert "문의처" not in main_part(page)
        assert f'<p class="muted">{page_frame.CONTACT_LABEL} ' not in page.text, "문의 줄이 없다"


# --- 누계 ---------------------------------------------------------------------------------


def test_login_starts_and_returns_are_counted_since_boot() -> None:
    """「로그인 시작 n · 돌아옴 n」 — 시작은 브라우저의 문서 탐색을 IdP 로 보낸 것만(되풀이로 막은
    시작 · 비브라우저 · 그림 요청은 빼고), 돌아옴은 이 앱이 시작한 로그인이 검증한 상태 쿠키와
    처음 돌아온 것만(실패 · 거절 · IdP 오류 포함 — 꼴이 틀린 POST · 모르는 state · 다시 보냄 ·
    GET 은 빼고). 재시작하면 0."""
    cfg = use_config()
    app = routes_app()
    jar: dict[str, str] = {}
    assert runtime.login_flow_counts() == (0, 0)

    nonce = begin(app, cfg, jar)
    assert runtime.login_flow_counts() == (1, 0)
    callback(app, jar, make_id_token(id_token_claims(nonce, aud="other-app")))
    assert runtime.login_flow_counts() == (1, 1)

    assert http(app, "GET", names.LOGIN_PATH).status == 302
    image = {"sec-fetch-mode": "no-cors", "sec-fetch-dest": "image", "sec-fetch-site": "cross-site"}
    assert http(app, "HEAD", names.LOGIN_PATH, headers=image).status == 302
    http(app, "POST", names.CALLBACK_PATH, headers={"content-type": "text/plain"}, body=b"x")
    forged = urlencode({"state": "A" * 43, "id_token": "x"}).encode()
    http(app, "POST", names.CALLBACK_PATH, headers=FORM, body=forged)
    http(app, "GET", names.CALLBACK_PATH)
    assert runtime.login_flow_counts() == (1, 1), "사람 아닌 요청 · 꼴이 틀린 POST 는 세지 않는다"

    nonce = begin(app, cfg, jar)
    token = make_id_token(id_token_claims(nonce))
    assert callback(app, jar, token).status == 303 and cfg.session_cookie in jar
    replay = callback(app, {STATE_KEY: jar[STATE_KEY]}, token)
    assert query_of(replay)["code"] == "state_reused"
    assert runtime.login_flow_counts() == (2, 2), "같은 로그인의 다시 보냄은 한 번"

    jar = {}
    begin(app, cfg, jar)
    cookies = {name: value for name, value in jar.items() if name != STATE_KEY}
    refused = urlencode({"error": "access_denied", "state": jar[STATE_KEY]}).encode()
    headers = {**FORM, "cookie": cookie_header(cookies)}
    http(app, "POST", names.CALLBACK_PATH, headers=headers, body=refused)
    web.start_login(cfg, {cfg.attempt_cookie: "3"}, "/", int(time.time()), browser=True)

    assert runtime.login_flow_counts() == (3, 3)
    runtime.reset()
    assert runtime.login_flow_counts() == (0, 0)


def test_the_gate_counts_only_browser_navigations_as_login_starts() -> None:
    """문지기는 쿠키 없는 GET · HEAD 를 모두 로그인으로 보내지만(비브라우저도) 시작 누계는
    브라우저의 문서 탐색만 센다 — 링크 미리보기 · 감시 요청이 「ADFS 화면에서 멈춤」 처럼 읽히지
    않게."""
    use_config()
    gate = SsoGate(routes_app())

    assert http(gate, "GET", "/").status == 302
    assert http(gate, "HEAD", "/space").status == 302
    assert runtime.login_flow_counts() == (0, 0)
    assert http(gate, "GET", "/space", headers=BROWSER).status == 302
    assert runtime.login_flow_counts() == (1, 0)


# --- 틀 -----------------------------------------------------------------------------------


def test_the_outer_diagnostic_fold_has_the_same_name_as_the_in_app_one() -> None:
    """「개발자용 진단」 은 앱 밖 틀(설정 막힘 · 로그인 실패)과 앱 안 판(문지기 없이 뜬 앱 · 오류
    카드)이 같은 이름이다(UI-CON-02) — 두 상수를 맞댄다."""
    assert page_frame.DIAGNOSTIC_LABEL == ADMIN_DIAGNOSTIC_LABEL


def test_the_frame_folds_a_table_and_a_second_fold_and_escapes_them() -> None:
    frame = page_frame.Frame(
        title="제목",
        chip="maintenance",
        lead=(),
        primary=None,
        secondary=(page_frame.Link("다시 시도", "/x"),),
        reference="code",
        reference_id="abc<i>",
        diagnostic_head="<em>머리</em>",
        diagnostics=("<b>줄</b>",),
        diagnostic_table=page_frame.Table(rows=(("이름", "<script>"),), code_columns=(1,)),
        diagnostic_fold=page_frame.Fold(
            "<u>접힘</u>",
            table=page_frame.Table(
                rows=(("A_B<x>", "B"),), head=("<h>", "칸"), code_columns=(0,), break_columns=(0,)
            ),
            facts=page_frame.Table(rows=(("값_이름", "<v>_1"),), code_columns=(1,)),
            lines=("<s>끝</s>",),
        ),
    )

    text = page_frame.render(frame, now=FIXED_NOW)

    for raw in ("<script>", "<b>줄", "<u>", "<s>", "<h>", "<i>", "<em>", "<x>", "<v>"):
        assert raw not in text, raw
    assert "<td><code>&lt;script&gt;</code></td>" in text
    assert "<summary>개발자용 진단</summary><p>&lt;em&gt;머리&lt;/em&gt;</p><ul>" in text
    assert "<td><code>A_<wbr>B&lt;x&gt;</code></td>" in text, "이름 칸만 `_` 뒤에서 끊는다"
    assert "<td>값_이름</td><td><code>&lt;v&gt;_1</code></td>" in text, "값 칸은 글자 그대로"
    assert text.index("A_<wbr>B") < text.index("값_이름") < text.index("&lt;s&gt;끝")
    assert "참고 code · 2026-11-14 05:30 UTC · 진단 abc&lt;i&gt;" in text
    assert 'class="button"' not in text, "주 단추 없음 — 보조 링크만"
    outer = text.split(f"<details><summary>{page_frame.DIAGNOSTIC_LABEL}</summary>", 1)[1]
    assert "<details><summary>&lt;u&gt;접힘&lt;/u&gt;</summary><table><thead>" in outer
    with pytest.raises(ValueError):
        page_frame.Frame(title="막다른", chip=None, lead=(), primary=None)


def test_the_frame_tables_wrap_inside_a_narrow_window() -> None:
    """좁은 창(390)에서 표 · 긴 이름이 가로로 넘치지 않는다 — 칸 안에서 줄을 바꾸고 판의 안쪽 여백을
    줄인다(양옆 16px 는 그대로)."""
    text = page_frame.render(
        page_frame.Frame(title="t", chip=None, lead=(), primary=page_frame.Link("a", "/")),
        now=FIXED_NOW,
    )
    css = text.split("<style>", 1)[1].split("</style>", 1)[0]

    assert "table-layout: fixed" in css and "overflow-wrap: anywhere" in css
    assert "@media (max-width: 480px)" in css
    assert "body { margin: 0; padding: 0 16px;" in css
