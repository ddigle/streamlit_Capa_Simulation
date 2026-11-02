# Purpose: 앱 스크립트 쪽 통합인증 — 매 회차 쿠키 재검증·멈춤 화면·카드 셋째 줄을 AppTest 로 지킨다.

"""`components/sso_identity.py` · `app_credits` 셋째 줄 · 진짜 `app.py` 배선.

쿠키는 `st.context.cookies` 대신 `sso_identity.session_cookies` 를 바꿔 끼워 넣는다(AppTest 에는
websocket 핸드셰이크가 없다). 설정은 `sso_support.use_config` 로 기동한 것처럼 세우고, 문지기 표지는
`runtime.mark_gate_installed()` 로 세운다 — `capa_server.py` 로 뜬 서버와 같은 상태다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from sso_support import PUBLIC_URL, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity
from capa_simulation.components.app_credits import credit_lines

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"

# 쿠키를 읽은 뒤 신원을 카드 줄에 싣고, 멈추지 않았으면 끝 표지를 남기는 작은 앱.
SCRIPT = """
import streamlit as st

from capa_simulation.components import sso_identity
from capa_simulation.components.app_credits import render_app_credits

identity = sso_identity.require_signed_in()
render_app_credits(sso_identity.sso_credit_line(identity))
st.text("끝까지 돌았다")
"""


@pytest.fixture
def cookies(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """이 세션의 쿠키(바꿔 끼운 `st.context.cookies`)."""
    jar: dict[str, str] = {}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)
    return jar


@pytest.fixture
def page_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str | None], None]]:
    holder: dict[str, str | None] = {"url": None}
    monkeypatch.setattr(sso_identity, "current_page_url", lambda: holder["url"])

    def set_url(url: str | None) -> None:
        holder["url"] = url

    yield set_url


def _session(
    cfg: SsoConfig,
    *,
    loginid: str = "dev.user",
    name: str | None = "개발 사용자",
    dept: str | None = "개발부서",
    now: int | None = None,
) -> tuple[str, Identity]:
    moment = int(time.time()) if now is None else now
    token, claims = issue_session(cfg, loginid=loginid, name=name, dept=dept, now=moment)
    identity = Identity(
        loginid=claims.loginid,
        name=claims.name,
        dept=claims.dept,
        iat=claims.iat,
        exp=claims.exp,
        jti=claims.jti,
    )
    return token, identity


def _on(
    cookies: dict[str, str],
    *,
    name: str | None = "개발 사용자",
    dept: str | None = "개발부서",
) -> tuple[SsoConfig, Identity]:
    """켜짐 설정 + 문지기 표지 + 유효한 세션 쿠키 — `capa_server.py` 로 뜬 서버에 로그인한 탭."""
    cfg = use_config()
    runtime.mark_gate_installed()
    token, identity = _session(cfg, name=name, dept=dept)
    cookies[cfg.session_cookie] = token
    return cfg, identity


def _texts(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.text]


def _caption_values(app: AppTest) -> list[str]:
    return [str(caption.value) for caption in app.caption]


def test_off_draws_nothing_and_keeps_the_two_line_card(cookies: dict[str, str]) -> None:
    """꺼짐(`ADFS_CLIENT_ID` 없음)이면 Streamlit 호출이 하나도 없다 — 카드는 두 줄 그대로다."""
    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _texts(app) == ["끝까지 돌았다"]
    assert not list(app.warning) and not list(app.error) and not list(app.markdown)
    assert _caption_values(app) == ["  \n".join(credit_lines())]
    assert sso_identity.SSO_LOGINID_KEY not in app.session_state


def test_a_valid_cookie_adds_name_dept_and_a_same_tab_logout(cookies: dict[str, str]) -> None:
    cfg, _identity = _on(cookies)

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _texts(app) == ["끝까지 돌았다"]
    [caption] = _caption_values(app)
    lines = caption.split("  \n")
    assert lines[:2] == list(credit_lines())
    logout = f"{PUBLIC_URL}{names.LOGOUT_PATH}"
    assert lines[2] == f'개발 사용자 · 개발부서 · <a href="{logout}" target="_self">로그아웃</a>'
    assert app.session_state[sso_identity.SSO_LOGINID_KEY] == "dev.user"
    # 카드 key 는 그대로다 — 사이드바 CSS 가 이 key 로 바닥에 고정한다.
    assert cfg.session_cookie == f"{names.HOST_PREFIX}{names.SESSION_COOKIE}"


def test_without_a_name_the_loginid_stands_and_a_missing_dept_is_left_out(
    cookies: dict[str, str],
) -> None:
    _on(cookies, name=None, dept=None)

    app = AppTest.from_string(SCRIPT).run()

    [caption] = _caption_values(app)
    assert caption.split("  \n")[2].startswith("dev\\.user · <a href=")


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("**굵게**", "\\*\\*굵게\\*\\*"),
        ("[a](javascript:alert(1))", "\\[a\\]\\(javascript\\:alert\\(1\\)\\)"),
        ("<script>x</script>", "\\<script\\>x\\<\\/script\\>"),
    ],
)
def test_the_name_and_dept_are_escaped(cookies: dict[str, str], name: str, shown: str) -> None:
    """이름 · 부서는 IdP 가 준 사람 글이다 — 마크다운 꾸밈도 원문 HTML 도 되지 않게 막는다
    (백슬래시로 막은 `<` 는 원문 HTML 이 되지 않는다)."""
    _on(cookies, name=name, dept=name)

    app = AppTest.from_string(SCRIPT).run()

    [caption] = _caption_values(app)
    line = caption.split("  \n")[2]
    assert line.startswith(f"{shown} · {shown} · <a href=")
    assert "<script>" not in line


def test_the_card_warns_thirty_minutes_before_the_end() -> None:
    cfg = use_config()
    _token, identity = _session(cfg, now=1_000_000)

    later = identity.exp - 25 * 60
    line = sso_identity.sso_credit_line(identity, now=later)
    assert line is not None and line.endswith(" · 로그인 25분 남음 — 저장해 두세요")
    earlier = identity.exp - 31 * 60
    line = sso_identity.sso_credit_line(identity, now=earlier)
    assert line is not None and "남음" not in line
    assert sso_identity.sso_credit_line(None) is None


@pytest.mark.parametrize(
    ("make_cookie", "notice"),
    [
        ("expired", sso_identity.EXPIRED_NOTICE),
        ("revoked", sso_identity.REVOKED_NOTICE),
        ("missing", sso_identity.MISSING_NOTICE),
        ("forged", sso_identity.MISSING_NOTICE),
    ],
)
def test_a_session_without_a_valid_cookie_stops_with_a_login_again_link(
    cookies: dict[str, str],
    page_url: Callable[[str | None], None],
    make_cookie: str,
    notice: str,
) -> None:
    """만료 · 다른 탭 로그아웃 · 쿠키 없음 · 위조는 멈춤 화면이다 — 입장 화면 · DB 에 안 닿는다."""
    cfg = use_config()
    runtime.mark_gate_installed()
    if make_cookie == "expired":
        token, _ = _session(cfg, now=int(time.time()) - cfg.session_seconds - 600)
        cookies[cfg.session_cookie] = token
    elif make_cookie == "revoked":
        token, identity = _session(cfg)
        runtime.revoke(identity.jti, identity.exp)
        cookies[cfg.session_cookie] = token
    elif make_cookie == "forged":
        cookies[cfg.session_cookie] = "x.y.z"
    page_url(f"{PUBLIC_URL}/process_detail")

    at = AppTest.from_string(SCRIPT)
    at.query_params["theme"] = "dark"
    app = at.run()

    assert not list(app.exception)
    assert [warning.value for warning in app.warning] == [notice]
    assert _texts(app) == [], "멈춘 뒤로는 아무것도 그리지 않는다"
    [link] = [str(item.value) for item in app.markdown]
    href = link.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    assert href.startswith(f"{PUBLIC_URL}{names.LOGIN_PATH}?next=")
    assert parse_qs(urlsplit(href).query)["next"] == ["/process_detail?theme=dark"]
    assert 'target="_self"' in link and sso_identity.LOGIN_AGAIN_LABEL in link


def test_a_new_account_in_the_same_session_stops(cookies: dict[str, str]) -> None:
    """같은 Streamlit 세션이 다른 계정의 쿠키로 이어지면 새로고침하라고 멈춘다."""
    cfg, _ = _on(cookies)
    at = AppTest.from_string(SCRIPT)
    at.run()
    other, _ = _session(cfg, loginid="other.user")
    cookies[cfg.session_cookie] = other

    app = at.run()

    assert [warning.value for warning in app.warning] == [sso_identity.ACCOUNT_CHANGED_NOTICE]
    assert _texts(app) == []


def test_an_enabled_setting_without_the_gate_stops(cookies: dict[str, str]) -> None:
    """켜진 설정인데 `streamlit run app.py` 로 떴으면(문지기 표지 없음) 쿠키가 맞아도 멈춘다."""
    cfg = use_config()
    token, _ = _session(cfg)
    cookies[cfg.session_cookie] = token

    app = AppTest.from_string(SCRIPT).run()

    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert _texts(app) == []


def test_a_broken_setting_without_the_gate_names_the_problems(cookies: dict[str, str]) -> None:
    """반쯤 설정(막힘)으로 문지기 없이 뜨면 이름 목록도 보인다 — 값은 보이지 않는다."""
    use_config(drop=[names.ENV_ISSUER])

    app = AppTest.from_string(SCRIPT).run()

    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    captions = "\n".join(_caption_values(app))
    assert f"`{names.ENV_ISSUER}`" in captions
    assert "idp.example.invalid" not in captions


def test_the_return_path_drops_the_public_url_prefix(
    page_url: Callable[[str | None], None],
) -> None:
    """WebIDE 처럼 공개 URL 에 경로 접두가 있으면 돌아올 자리는 그 접두 뒤다(콜백이 다시 붙인다)."""
    cfg = use_config({names.ENV_PUBLIC_URL: "https://ide.example.invalid/proxy/8510"})

    def run(url: str | None) -> str:
        page_url(url)
        script = (
            "import streamlit as st\n"
            "from capa_simulation.auth import runtime\n"
            "from capa_simulation.components import sso_identity\n"
            "st.text(sso_identity.return_path(runtime.config()))\n"
        )
        return _texts(AppTest.from_string(script).run())[0]

    assert cfg.public_url.endswith("/proxy/8510")
    assert run("https://ide.example.invalid/proxy/8510/space_status") == "/space_status"
    assert run("https://ide.example.invalid/proxy/8510") == "/"
    assert run(None) == "/"


# --- 진짜 app.py -----------------------------------------------------------------------------


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`(내장 시드). 브라우저로 보내는 컴포넌트만 바꿔 끼운다."""
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
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def test_the_real_app_opens_home_with_the_name_on_the_card(
    real_app: AppTest, cookies: dict[str, str]
) -> None:
    """켜짐 + 문지기 + 유효 쿠키 → HOME 이 서고 앱 정보 카드 셋째 줄에 이름 · 부서가 있다."""
    _on(cookies)

    app = real_app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    stops = {*sso_identity._PROBLEM_NOTICES.values(), sso_identity.ACCOUNT_CHANGED_NOTICE}
    assert not [warning.value for warning in app.warning if warning.value in stops]
    credit = [str(c.value) for c in app.sidebar.caption if "개발 사용자 · 개발부서" in str(c.value)]
    assert len(credit) == 1
    assert credit[0].split("  \n")[:2] == list(credit_lines())
    assert any(tab for tab in app.main.tabs), "HOME 본문 탭이 섰다"


def test_the_real_app_stops_when_started_without_the_gate(
    real_app: AppTest, cookies: dict[str, str]
) -> None:
    """켜진 설정을 `streamlit run app.py` 로 띄우면 HOME 대신 멈춤 화면이다(DB 를 열지 않는다)."""
    cfg = use_config()
    token, _ = _session(cfg)
    cookies[cfg.session_cookie] = token

    app = real_app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert not list(app.main.tabs)
