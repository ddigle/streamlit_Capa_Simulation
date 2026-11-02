# Purpose: 통합인증 로그인 갱신 — 갱신 경로 · 갱신 표 · sid 폐기 · 끝 시각 규칙을 검증한다.

"""로그인 유지(마지막 사용 뒤 6시간 · 쓰면 갱신 · 최대 24시간)의 서버 쪽.

시각은 `now` 인자로 쥔다 — 갱신 표 · 폐기 표 함수는 `now` 를 받는다. 경로 처리기는 `web._now` 를
바꿔 끼운다.
"""

from __future__ import annotations

import time

import pytest
from asgi_driver import http
from sso_support import LOGINID, renewed_session, use_config
from starlette.applications import Starlette

from capa_simulation.auth import names, runtime
from capa_simulation.auth.identity import IdentityProblem, identity_from_cookies
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import SESSION_LEEWAY, issue_session, renew_session

HOUR = 3600


def routes_app() -> Starlette:
    return Starlette(routes=sso_routes())


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
