# Purpose: 앱 스크립트 쪽 통합인증 — 매 회차 쿠키 재검증·멈춤 화면·카드 셋째 줄을 AppTest 로 지킨다.

"""`components/sso_identity.py` · `app_credits` 셋째 줄 · 진짜 `app.py` 배선.

쿠키는 `st.context.cookies` 대신 `sso_identity.session_cookies` 를 바꿔 끼워 넣는다(AppTest 에는
websocket 핸드셰이크가 없다). 설정은 `sso_support.use_config` 로 기동한 것처럼 세우고, 문지기 표지는
`runtime.mark_gate_installed()` 로 세운다 — `capa_server.py` 로 뜬 서버와 같은 상태다.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from sso_support import PUBLIC_URL, renewed_session, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime, web
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import admin_view, sso_identity, stop_panel
from capa_simulation.components.app_credits import credit_lines
from capa_simulation.components.app_header import SHELL_STYLE
from capa_simulation.components.diagnostic_copy import ADMIN_DIAGNOSTIC_LABEL
from capa_simulation.components.intro_overlay import SUMMARY_LABEL_ID
from capa_simulation.components.sso_reconnect import BANNER_ID, reconnect_script, restart_script
from capa_simulation.components.sso_refresh import LOGOUT_SELECTOR, refresh_script
from capa_simulation.components.theme_toggle import (
    ALARM_BUTTON_ID,
    CANON_MARK_ID,
    CHANGES_CHIP_ID,
    GUIDE_BUTTON_ID,
    NOTICE_CHIP_ID,
    PRINT_BUTTON_ID,
    PROCESS_CHIP_ID,
    SAMPLE_MARK_ID,
    THEME_BUTTON_ID,
    TOOLBAR_BUTTON_ORDER,
)
from capa_simulation.settings import APP_CONTACT_EMAIL_ENV

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
    return token, Identity.from_claims(claims)


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


_REFERENCE = re.compile(r"참고 (?P<code>\S+) · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")


def _reference_code(app: AppTest) -> str:
    """멈춤 판 맨 아래 캡션이 참고 줄이고 그 사유 낱말을 돌려준다."""
    found = _REFERENCE.fullmatch(str(app.caption[-1].value))
    assert found is not None, app.caption[-1].value
    return found["code"]


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
    """마지막 사용 뒤 유지 시간이 정한 끝(= 토큰 exp) 30분 전부터 남은 분을 붙인다."""
    cfg = use_config()
    _token, identity = _session(cfg, now=1_000_000)

    later = identity.exp - 25 * 60
    line = sso_identity.sso_credit_line(identity, now=later)
    assert line is not None
    assert line.endswith(sso_identity.IDLE_WARNING_SUFFIX.format(minutes=25))
    assert line.endswith(" · 로그인 25분 남음"), "하는 법(「저장해 두세요」)은 Guide 가 말한다"
    earlier = identity.exp - 31 * 60
    line = sso_identity.sso_credit_line(identity, now=earlier)
    assert line is not None and "남음" not in line and "최대" not in line
    assert sso_identity.sso_credit_line(None) is None


def test_the_card_warns_before_the_maximum_in_its_own_words() -> None:
    """쓰는 동안 갱신해도 최대 시간은 못 넘는다 — 그 끝이 가까우면 「최대 시간까지」 로 말한다."""
    cfg = use_config()
    login_at = 1_000_000
    cap = login_at + cfg.session_max_seconds
    renewed_at = cap - cfg.session_seconds + 600
    _token, claims = renewed_session(cfg, login_at=login_at, renew_at=[renewed_at])
    identity = Identity.from_claims(claims)
    assert identity.exp == cap, "갱신이 상한에서 멈췄다"

    line = sso_identity.sso_credit_line(identity, now=cap - 25 * 60)

    assert line is not None
    assert line.endswith(sso_identity.CAP_WARNING_SUFFIX.format(minutes=25))
    assert line.endswith(" · 로그인 최대 시간까지 25분")
    assert "남음" not in line
    line = sso_identity.sso_credit_line(identity, now=cap - 31 * 60)
    assert line is not None and "최대" not in line


def test_the_card_counts_down_to_the_renewed_end_of_an_open_tab() -> None:
    """열린 탭의 신원은 핸드셰이크 때 토큰이다 — 남은 시간은 갱신 표가 늘린 실제 끝으로 잰다."""
    cfg = use_config()
    now = 2_000_000
    _token, identity = _session(cfg, now=now - cfg.session_seconds + 20 * 60)
    assert identity.exp - now == 20 * 60
    line = sso_identity.sso_credit_line(identity, now=now)
    assert line is not None and line.endswith(sso_identity.IDLE_WARNING_SUFFIX.format(minutes=20))

    runtime.note_renewal(identity.sid, now + cfg.session_seconds, now=now)

    line = sso_identity.sso_credit_line(identity, now=now)
    assert line is not None and "남음" not in line and "최대" not in line
    line = sso_identity.sso_credit_line(identity, now=now + cfg.session_seconds - 10 * 60)
    assert line is not None and line.endswith(sso_identity.IDLE_WARNING_SUFFIX.format(minutes=10))


@pytest.mark.parametrize(
    ("make_cookie", "notice", "reference"),
    [
        ("expired", sso_identity.EXPIRED_NOTICE, "sso_expired"),
        ("revoked", sso_identity.REVOKED_NOTICE, "sso_revoked"),
        ("missing", sso_identity.MISSING_NOTICE, "sso_missing"),
        ("forged", sso_identity.MISSING_NOTICE, "sso_missing"),
    ],
)
def test_a_session_without_a_valid_cookie_stops_with_a_login_again_link(
    cookies: dict[str, str],
    page_url: Callable[[str | None], None],
    make_cookie: str,
    notice: str,
    reference: str,
) -> None:
    """만료 · 다른 탭 로그아웃 · 쿠키 없음 · 위조는 멈춤 화면이다 — 입장 화면 · DB 에 안 닿는다. 앱
    안 멈춤 판의 한 꼴로 참고 줄 「참고 <사유 낱말> · <UTC 분>」 이 단추 아래 선다(쿠키 없음 ·
    위조는 글이 같아 한 낱말). 이 회차에는 검증된 신원이 없어 접힌 진단은 없다."""
    cfg = use_config()
    runtime.mark_gate_installed()
    if make_cookie == "expired":
        token, _ = _session(cfg, now=int(time.time()) - cfg.session_seconds - 600)
        cookies[cfg.session_cookie] = token
    elif make_cookie == "revoked":
        token, identity = _session(cfg)
        runtime.revoke_session(identity.sid, until=identity.auth_time + cfg.session_max_seconds)
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
    # 글 링크가 아니라 앱 주 단추 꼴이다(강조색 면 — 카드 p1-tab-ended). 역할은 링크 그대로다 —
    # 단추 역할을 달면 낭독기는 단추로 읽는데 Space 로 열리지 않는다.
    assert "background:" in link and "role=" not in link
    assert web.REGISTER_LABEL not in link
    assert app.warning[0].icon == ":material/lock_clock:"
    assert _reference_code(app) == reference
    assert list(app.expander) == []


def test_the_stop_panel_names_the_contact_under_its_button(
    cookies: dict[str, str], page_url: Callable[[str | None], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 카드가 서지 않는 멈춤 화면이라 문의처를 단추 아래 캡션으로 싣는다(값만) — 앱 밖
    화면의 문의 줄과 같은 차례로 메일, 그 뒤에 접속 요청 창구 글. 둘 다 비면 줄이 없다."""
    window = "데모 접속 창구 *내선* 0000"
    page_url(f"{PUBLIC_URL}/")
    monkeypatch.delenv(APP_CONTACT_EMAIL_ENV, raising=False)

    use_config()
    runtime.mark_gate_installed()
    bare = AppTest.from_string(SCRIPT).run()
    use_config({names.ENV_ACCESS_CONTACT: window})
    runtime.mark_gate_installed()
    window_only = AppTest.from_string(SCRIPT).run()
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, "help@example.com")
    both = AppTest.from_string(SCRIPT).run()
    use_config()
    runtime.mark_gate_installed()
    mail_only = AppTest.from_string(SCRIPT).run()

    # 문의 줄 뒤는 늘 참고 줄이다(앱 안 멈춤 판의 한 꼴).
    for app in (bare, window_only, both, mail_only):
        assert _reference_code(app) == "sso_missing"
    assert _caption_values(bare)[:-1] == []
    # 문의 줄은 원문 HTML 캡션이다(메일은 강조색 링크 — `tests/test_stop_panel.py`). 창구 글은
    # HTML 로 막아 마크다운이 풀지 않는다 — 별표가 글자 그대로 보인다.
    assert _caption_values(window_only)[:-1] == ["<p>문의 데모 접속 창구 *내선* 0000</p>"]
    assert _caption_values(both)[:-1] == [stop_panel.contact_markup(window)]
    assert stop_panel.contact_caption(window) == (
        "문의 help@example.com · 데모 접속 창구 *내선* 0000"
    )
    assert _caption_values(mail_only)[:-1] == [stop_panel.contact_markup()]
    assert stop_panel.contact_caption() == "문의 help@example.com"


def test_a_dropped_account_is_offered_the_access_request(
    cookies: dict[str, str], page_url: Callable[[str | None], None]
) -> None:
    """명단에서 빠진 열린 탭의 단추는 「접속 권한 신청」 이다 — 같은 로그인 경로라 통합인증을 거쳐
    콜백의 거절 화면(신청은 그 화면이 받는다)으로 간다."""
    cfg = use_config({names.ENV_ACCESS_ADMINS: "demo.admin", names.ENV_ACCESS_USERS: "demo.user"})
    runtime.mark_gate_installed()
    token, _ = _session(cfg, loginid="demo.gone")
    cookies[cfg.session_cookie] = token
    page_url(f"{PUBLIC_URL}/space_status")

    app = AppTest.from_string(SCRIPT).run()

    assert [warning.value for warning in app.warning] == [web.NOT_ON_LIST_TEXT]
    [link] = [str(item.value) for item in app.markdown]
    assert web.REGISTER_LABEL in link
    href = link.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    assert href.startswith(f"{PUBLIC_URL}{names.LOGIN_PATH}?next=")
    assert parse_qs(urlsplit(href).query)["next"] == ["/space_status"]
    # 참고 줄의 사유 낱말은 거절 화면의 바닥 참고 줄과 같다.
    assert _reference_code(app) == web.NOT_ON_LIST


def _ended_session(cfg: SsoConfig) -> tuple[str, Identity, int]:
    """핸드셰이크 때 찍힌 쿠키가 이미 끝난 탭 — (토큰, 신원, 지금)."""
    now = int(time.time())
    token, identity = _session(cfg, now=now - cfg.session_seconds - 120)
    return token, identity, now


def test_an_open_tab_keeps_working_past_the_handshake_token_when_renewed(
    cookies: dict[str, str],
) -> None:
    """열린 탭의 쿠키는 핸드셰이크 때 것이다 — 그 뒤 갱신 경로가 늘린 끝(갱신 표)까지 산다."""
    cfg = use_config()
    runtime.mark_gate_installed()
    token, identity, now = _ended_session(cfg)
    cookies[cfg.session_cookie] = token
    runtime.note_renewal(identity.sid, now + 3600, now=now)

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert not list(app.warning)
    assert _texts(app) == ["끝까지 돌았다"]
    [caption] = _caption_values(app)
    assert caption.split("  \n")[2].startswith("개발 사용자 · 개발부서 · <a href=")
    assert "남음" not in caption


def test_an_open_tab_stops_when_the_renewal_ran_out_too(cookies: dict[str, str]) -> None:
    cfg = use_config()
    runtime.mark_gate_installed()
    token, identity, now = _ended_session(cfg)
    cookies[cfg.session_cookie] = token
    runtime.note_renewal(identity.sid, now - 60, now=now - 120)

    app = AppTest.from_string(SCRIPT).run()

    assert [warning.value for warning in app.warning] == [sso_identity.EXPIRED_NOTICE]
    assert _texts(app) == []


def test_a_new_account_in_the_same_session_stops(
    cookies: dict[str, str], page_url: Callable[[str | None], None]
) -> None:
    """같은 Streamlit 세션이 다른 계정의 쿠키로 이어지면 새 계정 이름과 주 단추 「새로고침」 으로
    멈춘다. 단추는 같은 탭 새 문서(지금 경로 + 질의)라 새 세션이 새 계정으로 선다 — 앞 계정의 세션
    상태를 이어 쓰지 않는다. 풍선이 저장하지 않은 편집이 사라진다고 먼저 말한다(UI-NTF-09)."""
    cfg, _ = _on(cookies)
    page_url(f"{PUBLIC_URL}/space_status")
    at = AppTest.from_string(SCRIPT)
    at.query_params["theme"] = "dark"
    at.run()
    other, _ = _session(cfg, loginid="other.user", name="다른*사람")
    cookies[cfg.session_cookie] = other

    app = at.run()

    assert [warning.value for warning in app.warning] == [
        sso_identity.account_changed_notice("다른*사람")
    ]
    assert app.warning[0].value == "「다른\\*사람」 계정으로 바뀌었습니다"
    assert _texts(app) == []
    [link] = [str(item.value) for item in app.markdown]
    href = link.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    assert href == f"{PUBLIC_URL}/space_status?theme=dark"
    assert 'target="_self"' in link and sso_identity.REFRESH_LABEL in link
    assert f'title="{sso_identity.REFRESH_TIP}"' in link
    assert _reference_code(app) == sso_identity.ACCOUNT_CHANGED_REFERENCE
    assert st_session_loginid(at) == "dev.user", "멈춘 세션은 앞 계정 표지를 바꾸지 않는다"


def test_an_enabled_setting_without_the_gate_stops(cookies: dict[str, str]) -> None:
    """켜진 설정인데 `streamlit run app.py` 로 떴으면(문지기 표지 없음) 쿠키가 맞아도 멈춘다. 그
    쿠키가 관리자(`LOGINID`)면 접힌 진단이 선다 — 관리자 몫 한 판정(`admin_view`)."""
    cfg = use_config()
    token, _ = _session(cfg)
    cookies[cfg.session_cookie] = token

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert _texts(app) == []
    [fold] = app.expander
    assert fold.label == ADMIN_DIAGNOSTIC_LABEL
    assert str(fold.caption[0].value) == sso_identity.NO_GATE_DIAGNOSTIC


def test_a_broken_setting_without_the_gate_names_the_problems(cookies: dict[str, str]) -> None:
    """운영이 아닌 서버가 반쯤 설정(막힘)으로 문지기 없이 뜨면 이름 목록도 보인다(관리자 몫 — 꺼짐 ·
    막힘의 운영 아닌 서버는 누구나) — 값은 보이지 않는다."""
    use_config({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_ISSUER])

    app = AppTest.from_string(SCRIPT).run()

    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    captions = "\n".join(_caption_values(app))
    assert f"`{names.ENV_ISSUER}`" in captions
    assert "idp.example.invalid" not in captions


def _every_value(app: AppTest) -> list[str]:
    """화면에 선 글 전부 — 경고 · 캡션 · 마크다운 · 코드 · 글 · 펼침 이름."""
    elements = (*app.error, *app.warning, *app.caption, *app.markdown, *app.code, *app.text)
    return [str(element.value) for element in elements] + [str(fold.label) for fold in app.expander]


# 관리자 몫이 아닌 회차에 어느 칸에도 없어야 하는 낱말 — 실행 명령 · 환경변수 이름 · 문서 경로.
_GATE_LESS_ADMIN_WORDS = (
    "streamlit",
    "capa_server",
    names.ENV_CLIENT_ID,
    names.ENV_ISSUER,
    names.SETUP_DOC,
    sso_identity.NO_GATE_PROBLEMS_CAPTION,
    ADMIN_DIAGNOSTIC_LABEL,
)


@pytest.mark.parametrize(
    ("overrides", "drop", "loginid"),
    [
        pytest.param({}, [names.ENV_ISSUER], None, id="broken-prod"),
        pytest.param({}, [], None, id="on-prod-no-cookie"),
        pytest.param({}, [], "other.user", id="on-prod-user"),
        pytest.param(
            {names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://127.0.0.1:8080"},
            [],
            None,
            id="on-dev-no-cookie",
        ),
    ],
)
def test_the_gate_less_stop_keeps_the_fold_from_people_outside_the_admin_audience(
    cookies: dict[str, str],
    overrides: dict[str, str],
    drop: list[str],
    loginid: str | None,
) -> None:
    """관리자 몫(`admin_view.admin_notes_visible`)이 아닌 회차 — 막힌 운영 서버의 누구나, 켜진
    설정의 일반 사용자 · 쿠키 없는 사람 — 에는 접힌 진단이 서지 않고 실행 명령 · 환경변수 이름 ·
    안내 문서가 어느 칸에도 없다. 경고 한 줄 · 참고 줄(사유 낱말)은 그대로다."""
    cfg = use_config(overrides, drop=drop)
    if loginid is not None:
        token, _ = _session(cfg, loginid=loginid)
        cookies[cfg.session_cookie] = token

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert list(app.expander) == []
    values = _every_value(app)
    for word in _GATE_LESS_ADMIN_WORDS:
        assert not [value for value in values if word in value], word
    assert any(
        value.startswith(f"참고 {sso_identity.NO_GATE_REFERENCE} · ")
        for value in _caption_values(app)
    )
    assert _texts(app) == []


def test_a_failing_admin_check_leaves_the_gate_less_stop_without_the_fold(
    cookies: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """판정이 예외를 내면 접힌 진단 없음으로 물러선다 — 이 판이 마지막 자리라 판은 그대로 선다(운영
    아닌 막힘이라 판정이 섰다면 누구에게나 보였을 회차)."""

    def broken() -> bool:
        raise RuntimeError("판정 실패")

    monkeypatch.setattr(admin_view, "admin_notes_visible", broken)
    use_config({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_ISSUER])

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert [error.value for error in app.error] == [sso_identity.NO_GATE_NOTICE]
    assert list(app.expander) == []
    assert not [value for value in _every_value(app) if names.ENV_ISSUER in value]
    assert _texts(app) == []


def test_the_gate_less_stop_says_little_and_folds_the_admin_text(
    cookies: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """문지기 없이 뜬 앱(카드 p2-config) — 누구나 읽는 경고 한 줄(실행 명령 · 환경변수 이름 없음) ·
    문의 캡션 · 참고 줄. 지금까지의 글(까닭 · 실행 명령 · 설정 문제 이름 · 안내 문서)은 앱 안 판의
    접힌 「관리자용 진단」(`diagnostic_copy.ADMIN_DIAGNOSTIC_LABEL`)에 있고 다시 열어도 같아 주
    단추가 없다. 접힌 진단이 서는 관리자 몫 회차 — 운영이 아닌 막힌 서버(누구나)에서 본다."""
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, "help@example.com")
    use_config({names.ENV_APP_ENV: "dev"}, drop=[names.ENV_ISSUER])

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    [error] = app.error
    assert error.value == sso_identity.NO_GATE_NOTICE
    for word in ("streamlit", "ADFS", "docs/", "문지기"):
        assert word not in error.value
    [fold] = app.expander
    assert fold.label == ADMIN_DIAGNOSTIC_LABEL
    folded = [str(item.value) for item in fold.caption]
    assert folded[0] == sso_identity.NO_GATE_DIAGNOSTIC
    assert any(f"`{names.ENV_ISSUER}`" in line for line in folded)
    assert folded[-1] == f"안내 문서 `{names.SETUP_DOC}`"
    outside = [value for value in _caption_values(app) if value not in folded]
    assert outside[0] == stop_panel.contact_markup()
    assert stop_panel.contact_caption() == "문의 help@example.com"
    assert re.fullmatch(
        rf"참고 {sso_identity.NO_GATE_REFERENCE} · \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}} UTC",
        outside[1],
    )
    assert list(app.button) == [] and not [item for item in app.markdown if "href" in item.value]


def test_the_logout_link_carries_the_screen_before_logout(
    cookies: dict[str, str], page_url: Callable[[str | None], None]
) -> None:
    """앱 정보 카드의 「로그아웃」 은 지금 화면 · 질의를 `next` 로 싣는다 — 로그아웃 화면의 「다시
    들어가기」 가 그리로 간다(카드 p1-logout). 첫 화면이면 싣지 않는다."""
    _on(cookies)
    page_url(f"{PUBLIC_URL}/space_status")
    at = AppTest.from_string(SCRIPT)
    at.query_params["theme"] = "dark"

    app = at.run()

    [caption] = _caption_values(app)
    line = caption.split("  \n")[2]
    href = line.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    assert href.startswith(f"{PUBLIC_URL}{names.LOGOUT_PATH}?next=")
    assert parse_qs(urlsplit(href).query)["next"] == ["/space_status?theme=dark"]
    assert _attribute_selector_matches(LOGOUT_SELECTOR, href), (
        "갱신 스크립트는 질의가 붙은 이 링크도 로그아웃으로 알아본다"
    )


def _attribute_selector_matches(selector: str, href: str) -> bool:
    """`a[href<연산자>="값"]` 꼴 선택자가 그 href 에 맞는가 — CSS 속성 선택자의 뜻 그대로."""
    found = re.fullmatch(r'a\[href([*^$~|]?)="([^"]*)"\]', selector)
    assert found is not None, f"속성 선택자 하나여야 한다 — {selector}"
    operator, value = found.groups()
    if operator == "*":
        return value in href
    if operator == "^":
        return href.startswith(value)
    if operator == "$":
        return href.endswith(value)
    if operator == "~":
        return value in href.split()
    if operator == "|":
        return href == value or href.startswith(f"{value}-")
    return href == value


def test_the_selector_reader_knows_each_operator() -> None:
    """위 판정이 연산자마다 다르게 답한다 — `$=` · `=` 로 바뀐 선택자는 질의 붙은 링크를 놓친다."""
    href = f"{PUBLIC_URL}{names.LOGOUT_PATH}?next=%2Fspace"
    assert _attribute_selector_matches(f'a[href*="{names.LOGOUT_PATH}"]', href)
    assert _attribute_selector_matches(f'a[href^="{PUBLIC_URL}"]', href)
    assert not _attribute_selector_matches(f'a[href$="{names.LOGOUT_PATH}"]', href)
    assert not _attribute_selector_matches(f'a[href="{names.LOGOUT_PATH}"]', href)


def st_session_loginid(at: AppTest) -> object:
    return at.session_state[sso_identity.SSO_LOGINID_KEY]


def _styles(app: AppTest) -> list[str]:
    return [str(element.proto.body) for element in app.get("html")]


@pytest.mark.parametrize("stop", ["signed_out", "account_changed", "without_gate"])
def test_every_stop_screen_hides_the_framework_menu_and_the_dead_toolbar(
    cookies: dict[str, str], stop: str
) -> None:
    """멈춤은 `app.py` 가 껍데기 스타일을 보내기 전이다 — 멈춤 화면 셋이 스스로 ⋮ 메뉴 · Deploy
    감춤을 보내고, 앞 회차의 툴바 iframe 이 남긴 Guide · Print · 테마(눌러도 아무 일도 하지
    않는다)를 감춘다. 알림 칸이 세운 변경 칩 · Alarm 은 듣개가 살아 판이 열리므로 감추지 않는다 —
    새로고침하면 비는 이 세션의 변경 목록을 볼 마지막 자리다. 정상 회차는 그 감춤을 보내지
    않는다(요소 순번 그대로)."""
    cfg = use_config()
    if stop != "without_gate":
        runtime.mark_gate_installed()
    token, _ = _session(cfg)
    if stop != "signed_out":
        cookies[cfg.session_cookie] = token
    at = AppTest.from_string(SCRIPT)
    if stop == "account_changed":
        first = at.run()
        assert _texts(first) == ["끝까지 돌았다"]
        assert sso_identity._STOP_TOOLBAR_STYLE not in _styles(first)
        assert SHELL_STYLE not in _styles(first)
        other, _ = _session(cfg, loginid="other.user")
        cookies[cfg.session_cookie] = other

    app = at.run()

    assert _texts(app) == [], "멈춘 뒤로는 아무것도 그리지 않는다"
    assert [*app.warning, *app.error], "멈춤 화면이다"
    styles = _styles(app)
    assert SHELL_STYLE in styles
    assert sso_identity._STOP_TOOLBAR_STYLE in styles
    hidden = {
        button_id
        for button_id in TOOLBAR_BUTTON_ORDER
        if f"#{button_id}" in sso_identity._STOP_TOOLBAR_STYLE
    }
    # 알림 칸의 공정 칩 · 합성 샘플 · 「정본 아님」 표지 · 공지 칩도 감춘다 — 멈춤 화면에는 걸
    # 공정도 볼 샘플도 저장할 것도 없고, 공지는 앱 안의 사람에게 보낸 글이다.
    assert hidden == {
        GUIDE_BUTTON_ID,
        PRINT_BUTTON_ID,
        THEME_BUTTON_ID,
        PROCESS_CHIP_ID,
        SAMPLE_MARK_ID,
        CANON_MARK_ID,
        NOTICE_CHIP_ID,
    }
    # 같은 iframe 이 세운 사이드바 앱 이름 라벨도 죽은 단추다 — 함께 감춘다(사용자 답 b6).
    assert f"#{SUMMARY_LABEL_ID}" in sso_identity._STOP_TOOLBAR_STYLE
    assert CHANGES_CHIP_ID not in sso_identity._STOP_TOOLBAR_STYLE
    assert ALARM_BUTTON_ID not in sso_identity._STOP_TOOLBAR_STYLE
    assert '[data-testid="stAppDeployButton"]' in SHELL_STYLE


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


def _record_toolbar_scripts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """`app.py` 가 테마 버튼 iframe 에 싣는 덧붙임 스크립트를 회차마다 받아 둔다."""
    import capa_simulation.components.theme_toggle as theme_toggle

    seen: list[tuple[str, ...]] = []
    original = theme_toggle.render_theme_toggle

    def record(extra_scripts: tuple[str, ...] = ()) -> None:
        seen.append(tuple(extra_scripts))
        original(extra_scripts)

    monkeypatch.setattr(theme_toggle, "render_theme_toggle", record)
    return seen


def test_the_real_app_opens_home_with_the_name_on_the_card(
    real_app: AppTest, cookies: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """켜짐 + 문지기 + 유효 쿠키 → HOME 이 서고 앱 정보 카드 셋째 줄에 이름 · 부서가 있다. 툴바
    iframe 에는 다시 붙지 못한 탭의 「다시 로그인」 띠(문지기가 있어 공지 물음 갈래까지)와 쓰는 동안
    로그인을 늘리는 갱신 스크립트가 실린다."""
    cfg, _ = _on(cookies)
    toolbar = _record_toolbar_scripts(monkeypatch)

    app = real_app.run()

    assert toolbar and toolbar[-1][-2:] == (reconnect_script(cfg), refresh_script(cfg))
    assert f'ask("{names.NOTICE_PATH}", true)' in toolbar[-1][-2]

    assert not list(app.exception), [element.message for element in app.exception]
    stops = set(sso_identity._PROBLEM_NOTICES.values())
    assert not [warning.value for warning in app.warning if warning.value in stops]
    assert not [
        warning.value
        for warning in app.warning
        if str(warning.value).endswith(sso_identity.ACCOUNT_CHANGED_TAIL)
    ]
    credit = [str(c.value) for c in app.sidebar.caption if "개발 사용자 · 개발부서" in str(c.value)]
    assert len(credit) == 1
    assert credit[0].split("  \n")[:2] == list(credit_lines())
    assert "Capa LOB Summary" in [element.value for element in app.title], "HOME 이 섰다"


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


def test_the_real_app_off_keeps_the_toolbar_scripts(
    real_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """꺼짐(`ADFS_CLIENT_ID` 없음)이면 툴바 iframe 에 갱신 스크립트를 싣지 않고, 띠 스크립트는
    서버 재시작 띠만 실린다(카드 p1-restart-tab — 재시작은 통합인증과 상관없다)."""
    use_config(drop=[names.ENV_CLIENT_ID])
    toolbar = _record_toolbar_scripts(monkeypatch)

    app = real_app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert toolbar
    assert [script for script in toolbar[-1] if BANNER_ID in script] == [restart_script()]
    assert not [script for script in toolbar[-1] if names.REFRESH_PATH in script]
    # `app.py` 로 띄운 서버(문지기 없음)에는 공지 물음이 실리지 않는다 — 공지는 앱 전체 회차로만.
    assert not [script for script in toolbar[-1] if names.NOTICE_PATH in script]
