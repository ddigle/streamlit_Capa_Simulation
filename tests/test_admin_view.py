# Purpose: 관리자 몫 보기가 설정 × 보는 사람마다 맞고 Admin Area 잠금과 어긋나지 않는지 시험한다.

"""관리자 몫 보기(`components/admin_view.py` — 2026-11-14 「앱 대신 뜨는 화면」 보드 카드
p1-not-canonical · p2-sync 리뷰 반영 · 카드 p1-boot · d12 (가)).

관리자면 늘, 아니면 통합인증이 켜짐이 아니고 운영 서버가 아닐 때만 누구에게나 보인다. 운영 서버
판정은 Admin Area 잠금과 한 뿌리(`SsoConfig.operational`)라, 보이는 회차에는 Admin Area 가 늘 열려
있다(「그 화면으로」 가 잠긴 화면을 가리키지 않는다). 설정은 진짜 기동(`runtime.start`)으로, 보는
사람은 진짜 세션 쿠키로 세운다 — 값은 모두 합성(`demo.*`)이다.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from sso_support import sso_environ

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import admin_view, sso_identity

ADMIN = "demo.admin"
USER = "demo.user"
LOOPBACK_URL = "http://localhost:8581"


def _start(environ: dict[str, str]) -> None:
    runtime.reset()
    runtime.start(environ)


def _dev_off() -> None:
    """개발 `app.py` · 사내 WebIDE · 사내 PC — 통합인증 환경변수가 하나도 없다."""
    _start({})


def _dev_off_with_public_url() -> None:
    """꺼진 개발 서버에 공개 주소 · 발급자 값만 미리 넣어 둠(켜기 전 단계) — 운영이 아니다."""
    _start(sso_environ({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_CLIENT_ID, names.ENV_SECRET]))


def _prod_off() -> None:
    """운영(`APP_ENV=prod`)인데 통합인증이 꺼짐(`AD-02`)."""
    _start(sso_environ(drop=[names.ENV_CLIENT_ID]))


def _dev_broken() -> None:
    _start(sso_environ({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_ISSUER]))


def _prod_broken() -> None:
    _start(sso_environ(drop=[names.ENV_ISSUER]))


def _prod_on() -> None:
    _start(sso_environ({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER}))


def _loopback_on() -> None:
    """루프백 개발 서버에서 통합인증을 켬 — 운영이 아니라 Admin Area 는 누구에게나 열린다."""
    _start(
        sso_environ(
            {
                names.ENV_APP_ENV: "dev",
                names.ENV_PUBLIC_URL: LOOPBACK_URL,
                names.ENV_ACCESS_ADMINS: ADMIN,
                names.ENV_ACCESS_USERS: USER,
            }
        )
    )


def _as(monkeypatch: pytest.MonkeyPatch, loginid: str | None) -> None:
    """이 회차의 쿠키를 그 사람의 세션으로(없으면 쿠키 없음). 꺼짐 · 막힘은 쿠키를 보지 않는다."""
    cfg = runtime.config()
    jar: dict[str, str] = {}
    if loginid is not None and cfg.mode is SsoMode.ON:
        token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
        jar[cfg.session_cookie] = token
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)


# (설정, 보는 사람, 관리자 몫이 보이나, 그 설정의 통합인증 모드, 운영 서버인가)
CASES: list[tuple[Callable[[], None], str | None, bool, SsoMode, bool]] = [
    (_dev_off, None, True, SsoMode.OFF, False),
    (_dev_off_with_public_url, None, True, SsoMode.OFF, False),
    (_prod_off, None, False, SsoMode.OFF, True),
    (_dev_broken, None, True, SsoMode.BROKEN, False),
    (_prod_broken, None, False, SsoMode.BROKEN, True),
    (_prod_on, ADMIN, True, SsoMode.ON, True),
    (_prod_on, USER, False, SsoMode.ON, True),
    (_prod_on, None, False, SsoMode.ON, True),
    (_loopback_on, ADMIN, True, SsoMode.ON, False),
    (_loopback_on, USER, False, SsoMode.ON, False),
]


@pytest.mark.parametrize(
    ("setup", "viewer", "visible", "mode", "operational"),
    CASES,
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_admin_notes_follow_the_admin_and_the_operational_server(
    monkeypatch: pytest.MonkeyPatch,
    setup: Callable[[], None],
    viewer: str | None,
    visible: bool,
    mode: SsoMode,
    operational: bool,
) -> None:
    """관리자면 늘, 아니면 통합인증이 켜짐이 아니고 운영 서버가 아닐 때만 — 운영 서버에서 통합인증이
    꺼진 동안(`AD-02`)은 아무에게도 서지 않는다."""
    setup()
    cfg = runtime.config()
    assert (cfg.mode, cfg.operational) == (mode, operational)
    _as(monkeypatch, viewer)

    assert admin_view.admin_notes_visible() is visible


@pytest.mark.parametrize(
    ("setup", "viewer"),
    [(setup, viewer) for setup, viewer, *_ in CASES],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_admin_notes_never_point_at_a_locked_admin_area(
    monkeypatch: pytest.MonkeyPatch, setup: Callable[[], None], viewer: str | None
) -> None:
    """보이는 회차에는 Admin Area 가 열려 있다 — 관리자 몫 알림의 「그 화면으로」 가 잠긴 화면을
    가리키지 않는다(두 판정이 같은 운영 서버 판정을 쓴다)."""
    setup()
    _as(monkeypatch, viewer)

    if admin_view.admin_notes_visible():
        assert not sso_identity.admin_area_locked()
