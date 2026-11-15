# Purpose: 앱 안 멈춤 판 셋(앱 시작 실패 · 접속 멈춤 · 한 화면 오류)이 한 꼴 차례로 서는지 시험한다.

"""앱 안 멈춤 판의 한 꼴(`components/stop_panel.py` — 2026-11-14 보드 stop-panels 「한 꼴로
맞춘다」).

세 판 모두 「경고 띠 → 주 단추 하나 → 문의 줄 → 참고 줄 → 접힌 「관리자용 진단」」 차례이고, 참고
줄은 「참고 <사유 낱말> · <YYYY-MM-DD HH:MM> UTC」(+ 「 · <오류 종류>」) 한 꼴이다. 접힌 진단은
관리자 몫(`admin_view.admin_notes_visible`)에만 선다 — 통합인증이 꺼진 운영 아닌 서버(시험)는
누구나, 로그인이 끝난 접속 멈춤은 검증된 신원이 없어 아무에게도.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable
from typing import Any

import pytest
from sso_support import LOGINID, OTHER_LOGINID, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation import page_failures
from capa_simulation.auth import runtime
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity, stop_panel
from capa_simulation.design import theme, tokens
from capa_simulation.settings import APP_CONTACT_EMAIL_ENV

pytestmark = pytest.mark.page_failure_card

CONTACT = "demo@example.com"
REFERENCE = re.compile(
    r"참고 (?P<code>[0-9A-Za-z_]+) · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC(?: · (?P<kind>\w+))?"
)

BOOT_SCRIPT = """
import duckdb

from capa_simulation.components.boot_stop import render_boot_stop

render_boot_stop(
    duckdb.IOException(
        'IO Error: Could not set lock on file "/srv/demo/capa_simulation.duckdb": '
        "Conflicting lock is held in /usr/bin/python3 (PID 424242) by user demo."
    )
)
"""

ACCESS_SCRIPT = """
from capa_simulation.components import sso_identity

sso_identity.require_signed_in()
"""


def _screen_page() -> None:
    from capa_simulation.components.page_failure_card import run_core_page

    def body() -> None:
        raise AttributeError("DEMO 값 없음")

    run_core_page(body, page="공정 Capa 상세", href="process_capa_detail")


def _glyphs(markup: str) -> str:
    """원문 HTML 캡션의 보이는 글자 — 태그를 걷고 HTML 이스케이프를 푼다."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def _shape(node: Any) -> list[str]:
    """판의 차례 — 띠 · 주 단추(단추 · 같은 탭 링크) · 문의 줄 · 참고 줄 · 접힌 진단. 스타일만 든
    칸(`st.html`)은 자리를 먹지 않아 뺀다. 펼침 안은 보지 않는다."""
    shape: list[str] = []
    for child in node.children.values():
        kind = type(child).__name__
        if kind in ("Error", "Warning"):
            shape.append("band")
        elif kind == "Button":
            shape.append("primary")
        elif kind == "Markdown" and 'target="_self"' in str(child.value):
            shape.append("primary")
        elif kind == "Caption":
            value = _glyphs(str(child.value))
            if value.startswith(f"{stop_panel.CONTACT_PREFIX} "):
                shape.append("contact")
            elif value.startswith(f"{stop_panel.REFERENCE_PREFIX} "):
                shape.append("reference")
            else:
                shape.append(f"caption:{value}")
        elif kind == "Expander":
            shape.append("fold")
        elif hasattr(child, "children"):
            shape.extend(_shape(child))
    return shape


def _reference(app: AppTest) -> re.Match[str]:
    [line] = [
        str(item.value)
        for item in app.caption
        if str(item.value).startswith(f"{stop_panel.REFERENCE_PREFIX} ")
    ]
    found = REFERENCE.fullmatch(line)
    assert found is not None, line
    return found


def _signed_out(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """만료된 세션 쿠키를 든 열린 탭(`capa_server.py` 로 뜬 서버)."""
    cfg = use_config()
    runtime.mark_gate_installed()
    long_ago = int(time.time()) - cfg.session_seconds - 600
    token, _ = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=long_ago)
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})
    monkeypatch.setattr(sso_identity, "current_page_url", lambda: None)
    return AppTest.from_string(ACCESS_SCRIPT).run()


def _account_changed(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """같은 세션이 다른 계정의 쿠키로 이어진 탭."""
    cfg = use_config()
    runtime.mark_gate_installed()
    now = int(time.time())
    jar: dict[str, str] = {}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)
    monkeypatch.setattr(sso_identity, "current_page_url", lambda: None)
    at = AppTest.from_string(ACCESS_SCRIPT)
    for loginid in (LOGINID, OTHER_LOGINID):
        token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=now)
        jar[cfg.session_cookie] = token
        at.run()
    return at


PANELS: dict[str, tuple[Callable[[pytest.MonkeyPatch], AppTest], list[str], str, str | None]] = {
    "boot": (
        lambda _: AppTest.from_string(BOOT_SCRIPT, default_timeout=30).run(),
        ["band", "primary", "contact", "reference", "fold"],
        "db_locked",
        "IOException",
    ),
    "access": (
        _signed_out,
        ["band", "primary", "contact", "reference"],
        "sso_expired",
        None,
    ),
    "account": (
        _account_changed,
        ["band", "primary", "contact", "reference"],
        sso_identity.ACCOUNT_CHANGED_REFERENCE,
        None,
    ),
    "screen": (
        lambda _: AppTest.from_function(_screen_page).run(),
        ["band", "primary", "contact", "reference", "fold"],
        "",
        "AttributeError",
    ),
}


@pytest.mark.parametrize("panel", list(PANELS))
def test_every_stop_panel_stands_in_one_order(panel: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """띠 → 주 단추 하나 → 문의 줄 → 참고 줄 → 접힌 진단(관리자 몫일 때) — 판마다 같은 차례이고 참고
    줄은 「참고 <사유 낱말> · <UTC 분>」(+ 오류 종류) 한 꼴이다. 한 화면 오류의 사유 낱말 자리는
    참고 번호(8자 — 관리자 알림 `AD-22` · 서버 로그와 같은 번호)다."""
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, CONTACT)
    run, shape, code, kind = PANELS[panel]

    app = run(monkeypatch)

    assert not list(app.exception), [item.message for item in app.exception]
    assert _shape(app.main) == shape
    found = _reference(app)
    if panel == "screen":
        [failure] = page_failures.recent_failures()
        code = failure.ref
    assert (found["code"], found["kind"]) == (code, kind)
    retry = [str(item.label) for item in app.button]
    assert retry in ([], [stop_panel.RETRY_LABEL])
    # 문의 줄 메일은 그 회차 테마의 강조색 링크다(원문 HTML 캡션 — 아래 시험).
    [contact] = [
        item
        for item in app.caption
        if _glyphs(str(item.value)).startswith(f"{stop_panel.CONTACT_PREFIX} ")
    ]
    assert contact.allow_html
    assert f'style="{stop_panel.contact_link_style()}">{CONTACT}</a>' in str(contact.value)


@pytest.mark.parametrize("panel", list(PANELS))
def test_the_footer_lines_do_not_fade(panel: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """문의 · 참고 줄은 열쇠 붙은 칸(`STOP_FOOTER_KEY`) 안에 서고, 그 칸의 캡션은 흐림을 걷고
    `TEXT_MUTED` 글자다 — 사이드바 앱 정보 카드와 같은 꼴. Streamlit 캡션 흐림(0.6)이 남으면 강조색
    메일 링크가 밝게에서 2.5:1 로 흐려진다."""
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, CONTACT)
    run = PANELS[panel][0]

    app = run(monkeypatch)

    assert not list(app.exception), [item.message for item in app.exception]
    footer = _find_key(app.main, stop_panel.STOP_FOOTER_KEY)
    assert footer is not None, "문의 · 참고 줄을 감싼 칸이 없다"
    captions = [str(item.value) for item in footer.caption]
    assert any(_glyphs(text).startswith(f"{stop_panel.CONTACT_PREFIX} ") for text in captions)
    assert any(text.startswith(f"{stop_panel.REFERENCE_PREFIX} ") for text in captions)
    style = stop_panel.footer_style()
    assert "opacity: 1" in style and f"color: {tokens.TEXT_MUTED}" in style
    assert f".st-key-{stop_panel.STOP_FOOTER_KEY}" in style


def _find_key(node: Any, key: str) -> Any:
    for child in getattr(node, "children", {}).values():
        if key in str(getattr(child, "key", "") or ""):
            return child
        found = _find_key(child, key)
        if found is not None:
            return found
    return None


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_contact_mail_link_takes_the_accent_of_the_run_theme(
    mode: theme.Mode, monkeypatch: pytest.MonkeyPatch
) -> None:
    """문의 줄 메일은 그 회차 테마의 강조색(`ACCENT`) 링크다 — 사이드바 앱 정보 카드 · 앱 밖 화면의
    문의처와 같은 색(design_system 「문의처는 메일 링크라 ACCENT」). Streamlit 기본 링크색은 어두운
    테마에서 둘레 캡션 글과 같은 색이라 링크로 보이지 않는다.

    줄은 원문 HTML 문단 하나(`<p>…</p>`)다 — 마크다운 줄 안에 `<a>` 를 끼우면 GFM 자동 링크가 안의
    메일 글을 한 번 더 링크로 감싸, 서식을 든 링크는 비고 기본색 링크만 보인다. 그래서 창구 글은
    마크다운이 아니라 HTML 로 막고, 문단을 끊는 빈 줄이 없게 공백을 하나로 접는다. 보이는 글자는
    평문 문의 줄(`contact_caption` — 시작 임시 화면과 맞댄다)과 같다."""
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, CONTACT)
    window = "데모 창구 <b>*내선*</b> & \n\n 0000"

    with theme.pinned_mode(mode):
        markup = stop_panel.contact_markup(window)

    assert markup is not None
    assert markup.startswith("<p>") and markup.endswith("</p>") and "\n" not in markup
    accent = tokens.palette_value(mode, "ACCENT")
    assert re.findall(r"<a\b[^>]*>", markup) == [
        f'<a href="mailto:{CONTACT}" style="color:{accent};text-decoration:underline">'
    ]
    assert "<b>" not in markup and "&lt;b&gt;*내선*&lt;/b&gt; &amp; 0000" in markup
    assert _glyphs(markup) == stop_panel.contact_caption(window)
    assert stop_panel.contact_caption(window) == f"문의 {CONTACT} · 데모 창구 <b>*내선*</b> & 0000"
    monkeypatch.delenv(APP_CONTACT_EMAIL_ENV)
    assert stop_panel.contact_markup("데모 창구") == "<p>문의 데모 창구</p>"
    assert stop_panel.contact_markup() is None and stop_panel.contact_caption() is None
