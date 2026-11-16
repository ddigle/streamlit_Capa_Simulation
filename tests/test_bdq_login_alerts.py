# Purpose: BDQ 자동 로그인 멈춤 알림 · 계정 없는 서버의 AD-10 가리킴 · AD-11 해소를 본다.

"""BigDataQuery 토큰 관리자 알림 셋(`container_start_check.render_token_alert`)과 자동 로그인.

결과 파일이 있는 C-DEP 서버는 회차마다 이벤트 칸 세 자리(`AD-10` · `AD-11` · `AD-23`)를 쓴다.
자동 로그인 상태는 S3 에 묻지 않고 읽는다 — 이 프로세스가 기억한 저장 객체(`bdq_login_store`)와
프로세스 안 멈춤, 아직 읽지 않았으면 이번 시작 기록(결과 파일의 `bdq_login` 칸). 값은 모두 합성이다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alert_marks import active_state, states
from bdq_login_support import ACCOUNT, PASSWORD, new_key
from streamlit.testing.v1 import AppTest
from test_bdq_token import fake_jwt
from test_token_failure_alert import _query

from capa_simulation import alerts
from capa_simulation import settings as app_settings
from capa_simulation.components import bdq_token_admin, container_start_check, sso_identity
from capa_simulation.io import bdq_login, bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.bdq_login_store import LoginSecret, StoredLogin
from capa_simulation.io.object_storage import MODE_ENV
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

SCRIPT = """
from capa_simulation.components.container_start_check import render_token_alert

render_token_alert()
"""
STOP = container_start_check.LOGIN_STOP_ALERT_CODE
FAILURE = container_start_check.TOKEN_ALERT_CODE
EXPIRY = bdq_token_admin.EXPIRY_ALERT_CODE
ENV_USER = "demo_env_user"


def _server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cell: Mapping[str, object] | None = None
) -> Path:
    """C-DEP 서버 꼴 — 결과 파일(자동 로그인 칸 `cell`) · `managed` + 키 · tmp 토큰 폴더 ·
    관리자."""
    path = tmp_path / "container_start.json"
    steps = {name: {"status": "ok", "reason": "정상"} for name in report_contract.STEPS}
    data: dict[str, object] = {"version": 1, "written_at": "", "steps": steps}
    if cell is not None:
        data["bdq_login"] = dict(cell)
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(app_settings, "CONTAINER_START_REPORT_PATH", path)
    monkeypatch.setenv(MODE_ENV, "managed")
    monkeypatch.setenv(report_contract.BDQ_SECRET_KEY_ENV, new_key())
    monkeypatch.setenv(report_contract.BDQ_USER_NAME_ENV, ENV_USER)
    folder = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", folder)
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: True)
    return folder


def _stored(state: store.StoredState = store.STATE_OK, reason: str | None = None) -> StoredLogin:
    return StoredLogin(
        secret=LoginSecret(ACCOUNT, PASSWORD),
        cipher="demo-cipher",
        entered_by="de",
        entered_at="2026-11-16T09:00:00+09:00",
        state=state,
        stop_reason=reason,
        stopped_at="2026-11-16T10:00:00+09:00" if reason else None,
    )


def _secret_free(note: Mapping[str, object]) -> None:
    text = json.dumps(note, ensure_ascii=False)
    assert ACCOUNT not in text and PASSWORD not in text


def test_the_stop_alert_is_registered_as_an_action_state() -> None:
    spec = alerts.REGISTRY[STOP]
    assert (spec.level, spec.kind) == ("action", "state")


def test_a_stored_stop_tells_the_administrator_to_enter_the_account_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기억한 저장 객체가 멈춤이면 관리자에게 — 까닭 낱말과 Admin Area 「BDQ 자동 로그인」 을
    가리킨다. 계정 · 비밀번호는 없다. 토큰 알림 셋이 한 자리씩 선다."""
    _server(tmp_path, monkeypatch)
    store.remember(_stored(store.STATE_STOPPED, "token_unchanged"))

    app = AppTest.from_string(SCRIPT).run()

    note = active_state(app, STOP)
    assert note is not None
    assert note["short"] == "BigDataQuery 자동 로그인 멈춤 — 계정을 다시 넣으세요"
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    assert "토큰이 바뀌지 않음" in note["full"] and "「BDQ 자동 로그인」" in note["full"]
    assert "`" not in note["full"]
    assert (note["page"], note["href"]) == (tab_label(ADMIN_AREA), ADMIN_AREA.href)
    _secret_free(note)
    for code in (FAILURE, EXPIRY, STOP):
        assert len(states(app, code)) == 1, code

    # 관리자가 다시 넣어 성공하면(기억이 `ok`) 해소로 닫힌다.
    store.remember(_stored())
    app.run()
    assert active_state(app, STOP) is None


def test_a_stop_found_at_start_tells_the_administrator_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 프로세스가 아직 저장 객체를 읽지 않았으면(또는 S3 를 못 읽었으면) 이번 시작 기록으로
    가른다 — 시작의 거절은 멈춤이다."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})

    note = active_state(AppTest.from_string(SCRIPT).run(), STOP)

    assert note is not None and "로그인 예외" in note["full"]


def test_an_in_process_stop_also_tells_the_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회 중 거절로 멈춤 표시를 객체에 쓰지 못했어도(프로세스 안 멈춤) 알린다."""
    _server(tmp_path, monkeypatch)
    stored = _stored()
    store.remember(stored)
    monkeypatch.setattr(bdq_login, "_STATE", bdq_login._Process(stopped_cipher=stored.cipher))

    assert active_state(AppTest.from_string(SCRIPT).run(), STOP) is not None


@pytest.mark.parametrize("admin", [False, True], ids=["관리자 아님", "멈춤 아님"])
def test_the_stop_alert_stays_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    _server(tmp_path, monkeypatch)
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: admin)
    store.remember(_stored() if admin else _stored(store.STATE_STOPPED, "token_unchanged"))

    app = AppTest.from_string(SCRIPT).run()

    assert active_state(app, STOP) is None
    assert [item["active"] for item in states(app, STOP)] == [False]


def test_a_server_without_the_key_never_raises_the_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """키가 없으면 기능이 없다 — 시작 기록 · 기억이 무엇이든 멈춤 알림은 해소다."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})
    monkeypatch.delenv(report_contract.BDQ_SECRET_KEY_ENV)

    assert active_state(AppTest.from_string(SCRIPT).run(), STOP) is None


def test_a_token_failure_without_a_stored_account_points_at_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`managed` + 키인데 저장된 계정이 없으면 조회 토큰 실패(`AD-10`)의 할 일은 Admin Area 「BDQ
    자동 로그인」 에 계정 넣기다. 키가 없으면 지금처럼 「토큰 넣기」 다."""
    _server(tmp_path, monkeypatch)
    store.remember(None)
    _query(monkeypatch, ConnectionError("500 invalid token"))

    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None
    assert bdq_token_admin.AUTO_LOGIN_FIX in note["full"]
    assert "「토큰 넣기」" not in note["full"] and "`" not in note["full"]

    monkeypatch.delenv(report_contract.BDQ_SECRET_KEY_ENV)
    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None
    assert "「토큰 넣기」 로 새 토큰을 넣으면" in note["full"]
    assert bdq_token_admin.AUTO_LOGIN_FIX not in note["full"]


def test_the_expiry_alert_rests_while_the_auto_login_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """만료 1시간 전(`AD-11`)은 자동 로그인이 서 있는 동안 내지 않는다 — 토큰 파일은 저장된 계정
    이름이다(계정 하나의 원천). 계정이 없으면(기억 「없음」) 지금처럼 선다."""
    folder = _server(tmp_path, monkeypatch)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0)
    folder.mkdir(parents=True)
    (folder / f"bigdataquery.token.{ACCOUNT}").write_text(fake_jwt(expires), encoding="utf-8")
    (folder / f"bigdataquery.token.{ENV_USER}").write_text(fake_jwt(expires), encoding="utf-8")

    store.remember(_stored())
    app = AppTest.from_string(SCRIPT).run()
    assert active_state(app, EXPIRY) is None
    assert [item["active"] for item in states(app, EXPIRY)] == [False]

    store.remember(None)
    assert active_state(app.run(), EXPIRY) is not None


def test_a_view_that_cannot_be_read_falls_back_to_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """상태를 읽다 무엇이 나도 모든 화면 회차의 알림 자리는 해소로 물러선다(`login_view`)."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})

    def explode(_start: object = None) -> bdq_login.LoginView:
        raise RuntimeError("view")

    monkeypatch.setattr(bdq_login, "current_view", explode)
    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert [item["active"] for item in states(app, STOP)] == [False]
