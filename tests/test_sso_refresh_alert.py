# Purpose: 로그인 갱신 거절 알림(AD-21)이 켜진 서버 · 관리자 회차 · 거절만 있을 때만 서는지 지킨다.

"""`components/sso_refresh_alert.py`(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p2-rare 한 조각).

기동 뒤 갱신이 출처 · 머리 검사에서만 거절됐으면(「다시 발급」 0) 관리자 회차에 상태 알림 `AD-21` 이
서고 「그 화면으로」 는 Admin Area 다. 다른 회차는 해소로 부르고, 켜진 서버는 회차마다 이벤트 칸 한
자리로 같다. 꺼진 서버는 아무것도 부르지 않는다.
"""

from __future__ import annotations

import time

import pytest
from alert_marks import active_state, states
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity, sso_refresh_alert

ADMIN = "demo.admin"
USER = "demo.user"
SCRIPT = """
from capa_simulation.components.sso_refresh_alert import render_refresh_alert

render_refresh_alert()
"""


def _config() -> SsoConfig:
    return use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})


def _as(cfg: SsoConfig, loginid: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    cookies: dict[str, str] = {}
    if loginid is not None:
        token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
        cookies[cfg.session_cookie] = token
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: cookies)


def _count(**outcomes: int) -> None:
    for outcome, times in outcomes.items():
        for _ in range(times):
            runtime.count_refresh(outcome)


def test_only_an_admin_sees_refusals_without_any_renewal(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config()
    _count(forbidden=3, unauthorized=1)

    for who, expected in ((ADMIN, True), (USER, False), (None, False)):
        _as(cfg, who, monkeypatch)
        app = AppTest.from_string(SCRIPT, default_timeout=30).run()
        assert not list(app.exception), who
        assert len(app._tree.get("html")) == 1, "회차마다 이벤트 칸 한 자리"
        assert len(states(app, sso_refresh_alert.ALERT_CODE)) == 1, who
        note = active_state(app, sso_refresh_alert.ALERT_CODE)
        assert (note is not None) is expected, who
        if not expected:
            # 해소 표지에는 운영 낱말(접속 주소 환경변수 · 갱신 머리 이름)을 싣지 않는다.
            [resolved] = states(app, sso_refresh_alert.ALERT_CODE)
            carried = f"{resolved.get('short', '')} {resolved.get('full', '')}"
            assert names.ENV_PUBLIC_URL not in carried, who
            assert names.REFRESH_HEADER not in carried, who
            assert sso_refresh_alert.SHORT_TEXT not in carried, who
    _as(cfg, ADMIN, monkeypatch)
    note = active_state(AppTest.from_string(SCRIPT, default_timeout=30).run(), "AD-21")
    assert note is not None
    assert note["short"] == "로그인 갱신이 거절됨 — 접속 주소 · 앞단 머리 확인"
    assert "처음 로그인 6시간 뒤 끊깁니다" in note["full"]
    assert names.ENV_PUBLIC_URL in note["full"] and names.REFRESH_HEADER in note["full"]
    assert (note["page"], note["href"]) == ("Admin Area", "admin_area")


@pytest.mark.parametrize(
    "outcomes",
    [{}, {"forbidden": 2, "renewed": 1}, {"forbidden": 2, "skipped": 1}, {"unauthorized": 4}],
)
def test_no_alert_once_a_renewal_went_through_or_nothing_was_refused(
    outcomes: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """한 번이라도 다시 발급했거나 건너뛰었으면(둘 다 출처 · 머리 검사를 지났다) 길은 열렸다 — 한
    사람의 다른 주소 접속 같은 잡음으로 세우지 않는다. 로그인 없음(401)은 끝난 세션이라 이 알림의
    일이 아니다."""
    cfg = _config()
    _count(**outcomes)
    _as(cfg, ADMIN, monkeypatch)

    app = AppTest.from_string(SCRIPT, default_timeout=30).run()

    assert active_state(app, "AD-21") is None
    assert [item["active"] for item in states(app, "AD-21")] == [False]


def test_the_fingerprint_does_not_move_with_each_new_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """내용은 고정 값이다 — 거절이 늘 때마다 알림창이 다시 뜨지 않는다."""
    cfg = _config()
    _as(cfg, ADMIN, monkeypatch)
    _count(forbidden=1)
    first = active_state(AppTest.from_string(SCRIPT, default_timeout=30).run(), "AD-21")
    _count(forbidden=5)
    later = active_state(AppTest.from_string(SCRIPT, default_timeout=30).run(), "AD-21")

    assert first is not None and later is not None
    assert first["fp"] == later["fp"]


def test_an_off_server_draws_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = use_config(drop=[names.ENV_CLIENT_ID])
    _count(forbidden=3)
    _as(cfg, None, monkeypatch)

    app = AppTest.from_string(SCRIPT, default_timeout=30).run()

    assert app._tree.get("html") == []


def test_the_code_is_a_registered_admin_state() -> None:
    spec = alerts.spec(sso_refresh_alert.ALERT_CODE)
    assert (spec.level, spec.kind) == ("action", "state")
    assert len(sso_refresh_alert.SHORT_TEXT) <= alerts.SHORT_LIMIT
