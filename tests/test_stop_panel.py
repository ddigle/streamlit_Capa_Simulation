# Purpose: 앱 안 멈춤 판 셋(앱 시작 실패 · 접속 멈춤 · 한 화면 오류)이 한 꼴 차례로 서는지 시험한다.

"""앱 안 멈춤 판의 한 꼴(`components/stop_panel.py` — 2026-11-14 보드 stop-panels 「한 꼴로
맞춘다」).

세 판 모두 「경고 띠 → 주 단추 하나 → 문의 줄 → 참고 줄 → 접힌 「관리자용 진단」」 차례이고, 참고
줄은 「참고 <사유 낱말> · <YYYY-MM-DD HH:MM> UTC」(+ 「 · <오류 종류>」) 한 꼴이다. 접힌 진단은
관리자 몫(`admin_view.admin_notes_visible`)에만 선다 — 통합인증이 꺼진 운영 아닌 서버(시험)는
누구나, 로그인이 끝난 접속 멈춤은 검증된 신원이 없어 아무에게도.
"""

from __future__ import annotations

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
            value = str(child.value)
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
