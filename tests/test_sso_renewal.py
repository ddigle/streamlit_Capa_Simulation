# Purpose: 통합인증 로그인 갱신 — 갱신 경로 · 갱신 표 · sid 폐기 · 끝 시각 규칙을 검증한다.

"""로그인 유지(마지막 사용 뒤 6시간 · 쓰면 갱신 · 최대 24시간)의 서버 쪽.

시각은 `now` 인자로 쥔다 — 갱신 표 · 폐기 표 함수는 `now` 를 받는다. 경로 처리기는 `web._now` 를
바꿔 끼운다.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import jwt
import pytest
from asgi_driver import AsgiResponse, http
from sso_support import LOGINID, PUBLIC_URL, refresh_headers, renewed_session, use_config
from starlette.applications import Starlette

from capa_simulation.auth import names, runtime, web
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import IdentityProblem, identity_from_cookies
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import (
    ISSUER,
    SESSION_AUDIENCE,
    SESSION_LEEWAY,
    decode_session,
    issue_session,
    issue_state,
    renew_session,
    session_key,
)

HOUR = 3600
NOW = 1_800_000_000


def routes_app() -> Starlette:
    return Starlette(routes=sso_routes())


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], None]:
    """경로 처리기의 시계(`web._now`)를 쥔다. 처음은 `NOW`."""

    def set_now(moment: int) -> None:
        monkeypatch.setattr(web, "_now", lambda: moment)

    set_now(NOW)
    return set_now


def post_refresh(cfg: SsoConfig, token: str | None, **overrides: str | None) -> AsgiResponse:
    return http(
        routes_app(), "POST", names.REFRESH_PATH, headers=refresh_headers(cfg, token, **overrides)
    )


def _signed_in(cfg: SsoConfig, *, at: int) -> str:
    token, _ = issue_session(cfg, loginid=LOGINID, name="이름", dept="부서", now=at)
    return token


def _counts(**expected: int) -> dict[str, int]:
    return {outcome: expected.get(outcome, 0) for outcome in runtime.REFRESH_OUTCOMES}


# --- 갱신 경로 --------------------------------------------------------------------------------


def test_refresh_renews_the_cookie_and_keeps_the_session(clock: Callable[[int], None]) -> None:
    cfg = use_config()
    token, issued = issue_session(cfg, loginid=LOGINID, name="이름", dept="부서", now=NOW - 120)

    response = post_refresh(cfg, token)

    assert response.status == 204 and response.body == b""
    assert response.header("cache-control") == "no-store"
    assert len(response.all_headers("set-cookie")) == 1
    [cookie] = response.set_cookies
    assert cookie.name == cfg.session_cookie == f"{names.HOST_PREFIX}{names.SESSION_COOKIE}"
    assert cookie.has("httponly") and cookie.has("secure")
    assert cookie.get("samesite") == "lax" and cookie.get("path") == "/"
    assert not cookie.has("domain")
    assert cookie.get("max-age") == str(6 * HOUR + SESSION_LEEWAY)
    fresh = decode_session(cookie.value, cfg, now=NOW)
    assert (fresh.sid, fresh.auth_time) == (issued.sid, issued.auth_time)
    assert (fresh.loginid, fresh.name, fresh.dept) == (LOGINID, "이름", "부서")
    assert fresh.jti != issued.jti
    assert (fresh.iat, fresh.exp) == (NOW, NOW + 6 * HOUR)
    assert runtime.renewed_exp(issued.sid, now=NOW) == fresh.exp
    assert runtime.refresh_counts() == _counts(renewed=1)


def test_refresh_within_a_minute_does_not_reissue(clock: Callable[[int], None]) -> None:
    cfg = use_config()

    response = post_refresh(cfg, _signed_in(cfg, at=NOW - 10))

    assert response.status == 204
    assert response.all_headers("set-cookie") == []
    assert response.header("cache-control") == "no-store"
    assert runtime.refresh_counts() == _counts(skipped=1)


def test_refresh_at_the_maximum_does_not_reissue(clock: Callable[[int], None]) -> None:
    """처음 로그인 + 24시간에 닿은 토큰은 더 늘지 않는다 — 다시 로그인(ADFS 재확인)만 남는다."""
    cfg = use_config()
    login_at = NOW - 23 * HOUR
    token, claims = renewed_session(
        cfg, login_at=login_at, renew_at=[login_at + hour * HOUR for hour in (5, 10, 15, 20)]
    )
    assert claims.exp == login_at + 24 * HOUR

    response = post_refresh(cfg, token)

    assert response.status == 204
    assert response.all_headers("set-cookie") == []
    assert runtime.refresh_counts() == _counts(skipped=1)
    assert runtime.renewed_exp(claims.sid, now=NOW) is None


def _v1_token(cfg: SsoConfig) -> str:
    payload = {
        "iss": ISSUER,
        "aud": SESSION_AUDIENCE,
        "sub": LOGINID,
        "iat": NOW - 120,
        "exp": NOW + HOUR,
        "jti": "j" * 22,
        "v": 1,
    }
    return jwt.encode(payload, session_key(cfg), algorithm="HS256")


def _bad_cookie(kind: str, cfg: SsoConfig) -> str | None:
    if kind == "none":
        return None
    if kind == "forged":
        return "eyJhbGciOiJIUzI1NiJ9.e30.x"
    if kind == "ended":
        return _signed_in(cfg, at=NOW - cfg.session_seconds - SESSION_LEEWAY - 1)
    if kind == "revoked":
        token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=NOW - 120)
        runtime.revoke_session(issued.sid, until=NOW + HOUR, now=NOW)
        return token
    if kind == "v1":
        return _v1_token(cfg)
    assert kind == "state"
    return issue_state(cfg, state="s" * 43, nonce="n" * 43, next_path="/", now=NOW)


@pytest.mark.parametrize("kind", ["none", "forged", "ended", "revoked", "v1", "state"])
def test_refresh_without_a_valid_session_is_401_and_leaves_cookies_alone(
    clock: Callable[[int], None], kind: str
) -> None:
    cfg = use_config()

    response = post_refresh(cfg, _bad_cookie(kind, cfg))

    assert (response.status, response.text) == (401, "login required")
    assert response.all_headers("set-cookie") == []
    assert response.header("cache-control") == "no-store"
    assert runtime.refresh_counts() == _counts(unauthorized=1)


def test_refresh_ignores_the_renewal_table_for_the_cookie_it_carries(
    clock: Callable[[int], None],
) -> None:
    """갱신 경로도 새 요청이다 — 끝난 옛 토큰은 갱신 표에 그 sid 의 앞날 끝이 있어도 401."""
    cfg = use_config()
    token, issued = issue_session(
        cfg, loginid=LOGINID, name=None, dept=None, now=NOW - cfg.session_seconds - 120
    )
    runtime.note_renewal(issued.sid, NOW + 3 * HOUR, now=NOW)

    assert post_refresh(cfg, token).status == 401


@pytest.mark.parametrize("value", [None, "0", "true"])
def test_refresh_needs_the_header(clock: Callable[[int], None], value: str | None) -> None:
    cfg = use_config()

    response = post_refresh(cfg, _signed_in(cfg, at=NOW - 120), x_capa_sso_refresh=value)

    assert (response.status, response.text) == (403, web.REFRESH_HEADER_REFUSAL)
    assert response.all_headers("set-cookie") == []
    assert runtime.refresh_counts() == _counts(forbidden=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"origin": None},
        {"origin": "null"},
        {"origin": "https://other.example.invalid"},
        {"origin": f"{PUBLIC_URL}:8443"},
        {"sec_fetch_site": "same-site"},
        {"sec_fetch_site": "cross-site"},
    ],
)
def test_refresh_refuses_other_origins(
    clock: Callable[[int], None], overrides: dict[str, str | None]
) -> None:
    cfg = use_config()

    response = post_refresh(cfg, _signed_in(cfg, at=NOW - 120), **overrides)

    assert (response.status, response.text) == (403, web.REFRESH_ORIGIN_REFUSAL)
    assert response.all_headers("set-cookie") == []
    assert runtime.refresh_counts() == _counts(forbidden=1)


def test_refresh_without_fetch_metadata_but_the_right_origin_passes(
    clock: Callable[[int], None],
) -> None:
    cfg = use_config()

    response = post_refresh(cfg, _signed_in(cfg, at=NOW - 120), sec_fetch_site=None)

    assert response.status == 204 and len(response.all_headers("set-cookie")) == 1


def test_refresh_refuses_a_body(clock: Callable[[int], None]) -> None:
    cfg = use_config()
    headers = refresh_headers(cfg, _signed_in(cfg, at=NOW - 120))

    declared = http(
        routes_app(),
        "POST",
        names.REFRESH_PATH,
        headers={**headers, "content-length": "3"},
        body=b"a=1",
    )
    streamed = http(routes_app(), "POST", names.REFRESH_PATH, headers=headers, chunks=[b"a", b"b"])
    empty = http(
        routes_app(), "POST", names.REFRESH_PATH, headers={**headers, "content-length": "0"}
    )

    for response in (declared, streamed):
        assert (response.status, response.text) == (400, web.REFRESH_BODY_REFUSAL)
        assert response.all_headers("set-cookie") == []
    assert empty.status == 204
    assert runtime.refresh_counts() == _counts(bad_request=2, renewed=1)


@pytest.mark.parametrize("method", ["GET", "OPTIONS", "PUT"])
def test_refresh_is_post_only(clock: Callable[[int], None], method: str) -> None:
    cfg = use_config()

    response = http(
        routes_app(),
        method,
        names.REFRESH_PATH,
        headers=refresh_headers(cfg, _signed_in(cfg, at=NOW - 120)),
    )

    assert response.status == 405
    assert response.all_headers("set-cookie") == []


def test_refresh_writes_no_events(clock: Callable[[int], None]) -> None:
    """갱신은 사건 고리에 적지 않는다(무인증 고리 · 누계도) — 5분마다 사람마다 한 줄은 소음이다."""
    cfg = use_config()
    before = runtime.recent_events()
    token = _signed_in(cfg, at=NOW - 120)

    post_refresh(cfg, token)
    post_refresh(cfg, token)
    post_refresh(cfg, None)
    post_refresh(cfg, token, origin="https://other.example.invalid")
    post_refresh(cfg, token, x_capa_sso_refresh=None)

    assert runtime.recent_events() == before
    assert runtime.recent_events(anonymous=True) == []
    assert runtime.anonymous_failure_counts() == {}
    assert runtime.refresh_counts() == _counts(renewed=2, unauthorized=1, forbidden=2)


def test_refresh_after_logout_is_401(clock: Callable[[int], None]) -> None:
    """로그아웃은 sid 를 폐기한다 — 같은 묶음의 옛 토큰 · 갱신한 새 토큰 모두 401."""
    cfg = use_config()
    old = _signed_in(cfg, at=NOW - 600)
    renewed = post_refresh(cfg, old)
    fresh = renewed.cookie(cfg.session_cookie)
    assert renewed.status == 204 and fresh is not None

    http(routes_app(), "GET", names.LOGOUT_PATH, headers={"cookie": f"{fresh.name}={fresh.value}"})
    clock(NOW + 120)

    assert post_refresh(cfg, old).status == 401
    assert post_refresh(cfg, fresh.value).status == 401
    assert runtime.renewed_exp(decode_session(old, cfg, now=NOW).sid, now=NOW) is None


# --- 로그아웃 · sid 폐기 ----------------------------------------------------------------------


def test_logout_revokes_every_token_of_the_session() -> None:
    """옛 토큰 A 와 갱신한 B 는 같은 sid 다 — B 로 로그아웃하면 A 도 막히고 표에서도 빠진다."""
    cfg = use_config()
    now = int(time.time())
    first, first_claims = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=now - 600)
    renewed = renew_session(cfg, first_claims, now=now - 300)
    assert renewed is not None
    second, second_claims = renewed
    runtime.note_renewal(second_claims.sid, second_claims.exp, now=now)
    other, _ = renewed_session(cfg, login_at=now - 600, renew_at=[now - 300])
    assert second_claims.sid == first_claims.sid and second_claims.jti != first_claims.jti

    response = http(
        routes_app(),
        "GET",
        names.LOGOUT_PATH,
        headers={"cookie": f"{cfg.session_cookie}={second}"},
    )

    assert response.status == 200
    for token in (first, second):
        jar = {cfg.session_cookie: token}
        assert identity_from_cookies(jar, cfg, now) is IdentityProblem.REVOKED
        assert identity_from_cookies(jar, cfg, now, renewals=True) is IdentityProblem.REVOKED
    assert runtime.renewed_exp(first_claims.sid, now=now) is None
    found = identity_from_cookies({cfg.session_cookie: other}, cfg, now)
    assert not isinstance(found, IdentityProblem), "다른 로그인(다른 sid)은 그대로다"


def test_logout_with_an_ended_cookie_still_revokes_the_session() -> None:
    """끝 + 1분 지난 쿠키로 로그아웃해도 그 sid 를 폐기한다 — 같은 sid 의 다른 탭 연결이 멈춘다."""
    cfg = use_config()
    now = int(time.time())
    token, issued = issue_session(
        cfg, loginid=LOGINID, name=None, dept=None, now=now - cfg.session_seconds - 60
    )
    assert identity_from_cookies({cfg.session_cookie: token}, cfg, now) is IdentityProblem.EXPIRED

    http(
        routes_app(), "GET", names.LOGOUT_PATH, headers={"cookie": f"{cfg.session_cookie}={token}"}
    )

    assert runtime.session_revoked(issued.sid)
    assert runtime.recent_events()[0].event == "logout"


def test_logout_past_the_maximum_has_nothing_to_revoke() -> None:
    """상한 + 여유를 지난 쿠키는 어디서도 통과하지 못하니 폐기 목록에 남기지 않는다."""
    cfg = use_config()
    now = int(time.time())
    token, issued = issue_session(
        cfg,
        loginid=LOGINID,
        name=None,
        dept=None,
        now=now - cfg.session_max_seconds - SESSION_LEEWAY - 60,
    )

    http(
        routes_app(), "GET", names.LOGOUT_PATH, headers={"cookie": f"{cfg.session_cookie}={token}"}
    )

    assert not runtime.session_revoked(issued.sid)


def test_revocation_lasts_until_the_given_time() -> None:
    use_config()

    runtime.revoke_session("s" * 22, until=1_000, now=900)

    assert runtime.session_revoked("s" * 22, now=1_000)
    assert not runtime.session_revoked("s" * 22, now=1_001)
    assert not runtime.session_revoked("s" * 22, now=900), "지난 항목은 지운다"


# --- 갱신 표 · 누계 ----------------------------------------------------------------------------


def test_renewal_table_keeps_the_latest_and_forgets_the_ended() -> None:
    use_config()
    sid = "a" * 22

    runtime.note_renewal(sid, 10_000, now=1_000)
    runtime.note_renewal(sid, 9_000, now=1_000)

    assert runtime.renewed_exp(sid, now=1_000) == 10_000, "늦은 값을 지킨다"
    assert runtime.renewed_exp(sid, now=10_000 + SESSION_LEEWAY) == 10_000
    assert runtime.renewed_exp(sid, now=10_000 + SESSION_LEEWAY + 1) is None
    assert runtime.renewed_exp(sid, now=1_000) is None, "지난 항목은 그 자리에서 지운다"
    runtime.note_renewal(sid, 2_000, now=5_000)
    assert runtime.renewed_exp(sid, now=1_000) is None, "이미 끝난 값은 적지 않는다"


def test_renewal_table_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    use_config()
    monkeypatch.setattr(runtime, "MAX_RENEWALS", 3)

    for index, exp in enumerate((5_000, 3_000, 4_000)):
        runtime.note_renewal(f"sid-{index:020d}", exp, now=1_000)
    runtime.note_renewal(f"sid-{3:020d}", 6_000, now=1_000)

    assert runtime.renewed_exp(f"sid-{1:020d}", now=1_000) is None, "exp 가 가장 이른 것이 빠진다"
    for index in (0, 2, 3):
        assert runtime.renewed_exp(f"sid-{index:020d}", now=1_000) is not None
    runtime.note_renewal(f"sid-{0:020d}", 7_000, now=1_000)
    assert runtime.renewed_exp(f"sid-{2:020d}", now=1_000) == 4_000, "있는 sid 를 늘리면 안 뺀다"


def test_forget_renewal_drops_the_entry() -> None:
    use_config()

    runtime.note_renewal("b" * 22, 9_000, now=1_000)
    runtime.forget_renewal("b" * 22)
    runtime.forget_renewal("never-seen-sid-000000")

    assert runtime.renewed_exp("b" * 22, now=1_000) is None


def test_reset_clears_renewals_revocations_and_counts() -> None:
    use_config()
    runtime.note_renewal("c" * 22, 9_000, now=1_000)
    runtime.revoke_session("d" * 22, until=9_000, now=1_000)
    runtime.count_refresh("renewed")

    runtime.reset()

    assert runtime.renewed_exp("c" * 22, now=1_000) is None
    assert not runtime.session_revoked("d" * 22, now=1_000)
    assert runtime.refresh_counts() == dict.fromkeys(runtime.REFRESH_OUTCOMES, 0)


def test_count_refresh_refuses_unknown_outcomes() -> None:
    use_config()

    runtime.count_refresh("skipped")
    runtime.count_refresh("skipped")
    with pytest.raises(ValueError):
        runtime.count_refresh("renewd")

    counts = runtime.refresh_counts()
    assert list(counts) == list(runtime.REFRESH_OUTCOMES)
    assert counts["skipped"] == 2 and sum(counts.values()) == 2
