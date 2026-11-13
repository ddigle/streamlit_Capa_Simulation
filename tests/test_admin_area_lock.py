# Purpose: Admin Area 관리자 전용 — 운영 서버 잠금·개발 열림·명단 관리자 열림·사이드바 메뉴 빼기를
# 지킨다.

"""Admin Area 를 관리자에게만(2026-11-13 보드 D11 · 2026-11-14 답).

판정은 `sso_identity.admin_area_locked` 하나다 — 운영 서버(`SsoConfig.operational`)이고 관리자가
아니면
잠긴다. 화면은 단독 실행 스크립트로 돌리고(네비게이션 없음 — 「HOME 으로」 는 물러선 글), 사이드바
메뉴는
실제 `app.py` 로 본다. 값은 모두 합성(`demo.*`)이다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from sso_support import sso_environ, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    AccessSource,
    ListDocument,
    ListEntry,
    compose_access,
)
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages/admin_area.py"
ADMIN = "demo.admin"
USER = "demo.user"
LIST_ADMIN = "demo.listadmin"


def _page_script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

source = Path({str(PAGE)!r})
exec(
    compile(source.read_text(encoding="utf-8"), str(source), "exec"),
    {{"__name__": "__main__"}},
)
"""


def _as(monkeypatch: pytest.MonkeyPatch, loginid: str | None) -> None:
    """이 회차의 쿠키를 그 사람의 세션으로(없으면 쿠키 없음)."""
    cfg = runtime.config()
    jar: dict[str, str] = {}
    if loginid is not None:
        token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
        jar[cfg.session_cookie] = token
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)


def _run(tmp_path: Path) -> AppTest:
    return AppTest.from_string(_page_script(tmp_path / "scenario.duckdb")).run(timeout=120)


def _locked(app: AppTest) -> bool:
    return [warning.value for warning in app.warning] == [sso_identity.ADMIN_ONLY_NOTICE]


def _with_list_admin() -> None:
    """S3 명단을 읽어 둔 꼴 — `LIST_ADMIN` 은 명단의 관리자 등급, `USER` 는 일반."""
    cfg = runtime.config()
    document = ListDocument(
        revision=1, entries=(ListEntry(LIST_ADMIN, grade=GRADE_ADMIN), ListEntry(USER))
    )
    runtime.publish_access_source(
        AccessSource(access=compose_access(cfg.access, document), document=document)
    )


def test_a_plain_user_on_the_operational_server_is_locked_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    runtime.mark_gate_installed()
    _as(monkeypatch, USER)

    app = _run(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert _locked(app)
    assert [heading.value for heading in app.title] == ["Admin Area"]
    assert not list(app.main.tabs), "탭 · 저장 단추가 하나도 서지 않는다"
    assert not app.get("download_button")
    assert any(sso_identity.HOME_LINK_LABEL in caption.value for caption in app.caption)
    assert sso_identity.admin_area_locked()


def test_an_environment_admin_opens_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    runtime.mark_gate_installed()
    _as(monkeypatch, ADMIN)

    app = _run(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not _locked(app)
    assert len(app.main.tabs) >= 3


def test_a_list_admin_opens_it_and_a_plain_list_user_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: ""})
    runtime.mark_gate_installed()
    _with_list_admin()

    _as(monkeypatch, LIST_ADMIN)
    assert not sso_identity.admin_area_locked()
    _as(monkeypatch, USER)
    assert sso_identity.admin_area_locked()


def test_development_opens_it_as_before(tmp_path: Path) -> None:
    """통합인증 꺼짐 · 운영 아님(개발 `app.py` · WebIDE · 사내 PC) — 지금처럼 연다."""
    runtime.reset()

    app = _run(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not _locked(app)
    assert not runtime.config().operational


@pytest.mark.parametrize(
    ("overrides", "operational"),
    [
        ({names.ENV_APP_ENV: "prod"}, True),
        ({names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://localhost:8581"}, False),
        (
            {
                names.ENV_APP_ENV: "dev",
                names.ENV_PUBLIC_URL: "http://localhost:8581",
                names.ENV_SSO: "required",
            },
            True,
        ),
        ({names.ENV_APP_ENV: "dev"}, True),
    ],
)
def test_the_operational_server_is_decided_in_one_place(
    overrides: dict[str, str], operational: bool
) -> None:
    """운영 = `APP_ENV` 운영 · (켜짐이면) 잠금 · 루프백 밖 공개 주소 — 접속 명단이 필수가 되는
    판정."""
    cfg = use_config(overrides)

    assert cfg.operational is operational


def test_the_production_server_with_sso_off_is_locked_for_everyone() -> None:
    """운영인데 통합인증이 꺼짐 — 관리자 신원이 없으니 잠긴 채다(공개 주소를 넣은 개발 꺼짐은
    연다)."""
    runtime.reset()
    environ = sso_environ(drop=[names.ENV_CLIENT_ID])
    runtime.start(environ)
    assert runtime.config().mode.value == "off"

    assert sso_identity.admin_area_locked()

    runtime.reset()
    runtime.start(
        sso_environ({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_CLIENT_ID, names.ENV_SECRET])
    )
    assert not sso_identity.admin_area_locked()


def test_the_locked_page_of_a_production_server_with_sso_off_still_raises_the_alarm(
    tmp_path: Path,
) -> None:
    """운영인데 꺼짐 — 모두가 잠긴 화면만 보므로 `AD-02` 는 잠금 앞에서 낸다(펼침 안에만 두면
    어느 회차에서도 서지 않는 죽은 알림이다 — 리뷰 보안 렌즈 2)."""
    from alert_marks import active_state

    runtime.reset()
    runtime.start(sso_environ(drop=[names.ENV_CLIENT_ID]))

    app = _run(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert _locked(app)
    assert active_state(app, "AD-02") is not None


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], AppTest]:
    """빈 DuckDB 를 보는 `app.py` — 브라우저로 보내는 컴포넌트만 바꿔
    끼운다(`test_sso_streamlit`)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return lambda: AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300)


def _support_links(app: AppTest) -> list[str]:
    return [str(link.proto.label) for link in app.sidebar.get("page_link")]


def test_the_real_app_hides_the_menu_from_a_plain_user(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    runtime.mark_gate_installed()

    _as(monkeypatch, USER)
    plain = real_app().run()
    assert not list(plain.exception), [element.message for element in plain.exception]
    assert "Admin Area" not in _support_links(plain)
    assert "VOC" in _support_links(plain), "Support 상자의 VOC 는 그대로"

    _as(monkeypatch, ADMIN)
    admin = real_app().run()
    assert not list(admin.exception), [element.message for element in admin.exception]
    assert "Admin Area" in _support_links(admin)


def test_the_operational_server_without_the_gate_stays_locked(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    """통합인증을 켜는 설정인데 문지기 없이 뜬 운영 서버 — 화면이 서기 전에 멈춘다."""
    use_config({names.ENV_ACCESS_ADMINS: ADMIN})
    _as(monkeypatch, ADMIN)

    app = real_app().run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert "Admin Area" not in _support_links(app), "메뉴가 서지 않는다"
