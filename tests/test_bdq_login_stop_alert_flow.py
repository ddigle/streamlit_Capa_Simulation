# Purpose: 자동 로그인이 멈춘 C-DEP 의 실제 개발자 회차에 AD-23 · AD-10 이 서는지 본다.

"""자동 로그인 멈춤 알림 — 흉내를 줄인 끝까지 길.

장면: 시작 로그인은 성공(결과 파일 칸 `ok`), 만료 뒤 조회가 토큰 갈래로 실패 → 조회 중 자동
로그인의 하위 프로세스가 표지 없이 끝남(`no_marker` — 멈춤). 개발자 판정은 바꿔 끼우지 않는다 —
운영 + 통합인증 켜짐의 개발자 쿠키(`grade_support`)로 `sso_identity.viewer_is_developer` 를 그대로
지난다.

토큰 알림은 `app.py` 가 화면 **앞**에서 낸다. 멈춤 · 조회 실패는 화면 본문(DB 등록 조회 단추)에서
생기므로 그 회차의 앞 표지는 해소다 — 화면이 끝까지 돈 회차는 끝에서 한 번 더 내어
(`render_token_alert_late`) 같은 회차의 마지막 표지가 지금 상태가 되게 한다. 알림 칸 JS 는 한 번
훑을 때 같은 상태 칸의 마지막 표지만 받는다(`latestStateNotes`). 값은 모두 합성이다.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from alert_marks import active_state, states
from bdq_login_support import ACCOUNT, PASSWORD, measured_token_failure, new_key
from grade_support import DEMO_DEVELOPER, as_grade
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation import settings as app_settings
from capa_simulation.auth import grades
from capa_simulation.components import container_start_check
from capa_simulation.io import bdq_login, bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.container_start_report import ChildDiag
from capa_simulation.io.object_storage import MODE_ENV

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
ALERTS_ONLY = """
from capa_simulation.components.container_start_check import render_token_alert

render_token_alert()
"""
# `app.py` 의 차례 — 화면 앞 토큰 알림 → 화면 본문(조회 단추) → 끝까지 돈 회차의 끝.
IN_RUN = """
from types import SimpleNamespace

import streamlit as st

from capa_simulation.components.container_start_check import (
    render_token_alert,
    render_token_alert_late,
)
from capa_simulation.io import company_bigdataquery_adapter as adapter

seen = render_token_alert()
if st.session_state.get("query_now"):
    st.session_state["query_now"] = False

    def expired(**_kwargs):
        raise adapter_failure()

    from bdq_login_support import measured_token_failure as adapter_failure

    try:
        adapter.call_get_data(SimpleNamespace(getData=expired), "SELECT 1")
    except adapter.BigDataQueryCallError:
        st.error("조회 실패")
render_token_alert_late(seen)
"""
STOP = container_start_check.LOGIN_STOP_ALERT_CODE
FAILURE = container_start_check.TOKEN_ALERT_CODE
KILLED = ChildDiag(
    exit_code=-9,
    signal="SIGKILL",
    seconds=2.9,
    stage="import",
    stderr_kind="",
    bigdataquery="2.5.0",
    getpass_asterisk="1.0.1",
)


def _cdep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cell: dict[str, object]) -> bytes:
    """C-DEP 꼴 — 운영 + 켜짐의 실제 개발자 쿠키, 결과 파일(자동 로그인 칸 `cell`), `managed` + 키,
    tmp 토큰 폴더. 키 바이트를 돌려준다."""
    as_grade(monkeypatch, grades.DEVELOPER)
    path = tmp_path / "container_start.json"
    steps = {name: {"status": "ok", "reason": "정상"} for name in report_contract.STEPS}
    data: dict[str, object] = {"version": 1, "written_at": "", "steps": steps, "bdq_login": cell}
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(app_settings, "CONTAINER_START_REPORT_PATH", path)
    monkeypatch.setenv(MODE_ENV, "managed")
    key = new_key()
    monkeypatch.setenv(report_contract.BDQ_SECRET_KEY_ENV, key)
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", tmp_path / "credential")
    return key.encode("ascii")


def _save_login(key: bytes) -> None:
    target = store.app_target()
    assert target is not None, "운영 S3 자리가 서야 저장된 계정이 있다"
    assert store.save_login(target, key, LoginSecret(ACCOUNT, PASSWORD), DEMO_DEVELOPER).ok


def _killed_child(*_args: object, **_kwargs: object) -> bdq_login.LoginResult:
    """하위 프로세스가 import 단계에서 바깥 SIGKILL 로 끝난 꼴(표지 없음)."""
    return bdq_login.LoginResult(
        bdq_login.OUTCOME_REJECTED, bdq_login.REASON_NO_MARKER, diag=KILLED
    )


def _last_state(app: AppTest, code: str) -> dict[str, Any] | None:
    """알림 칸 JS 가 한 번 훑을 때 받는 그 코드의 표지 — 문서 차례의 마지막 것."""
    found = states(app, code)
    return found[-1] if found else None


def test_a_stop_during_a_query_raises_the_stop_and_the_token_alert_for_the_developer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 프로세스 안 — 시작 로그인 성공 → 만료 뒤 조회 → 조회 중 자동 로그인이 표지 없이 끝남.
    그다음 회차의 앞 표지가 둘 다 선다."""
    key = _cdep(tmp_path, monkeypatch, {"status": "ok", "reason": "", "minutes": 479})
    _save_login(key)
    monkeypatch.setattr(bdq_login, "attempt_login", _killed_child)

    def expired() -> object:
        raise measured_token_failure()

    with pytest.raises(ConnectionError):
        bdq_login.run_with_relogin(expired)
    adapter._note_token_failure(True)
    assert bdq_login.status().state == "stopped"

    app = AppTest.from_string(ALERTS_ONLY).run()

    stop = active_state(app, STOP)
    assert stop is not None
    assert stop["short"] == "BigDataQuery 자동 로그인 멈춤 — 로그인 확인 못 함"
    assert active_state(app, FAILURE) is not None


def test_a_stop_found_after_a_restart_raises_the_stop_alert_for_the_developer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다시 뜬 프로세스 — 저장 객체가 멈춤(`no_marker`)이고 시작은 로그인하지 않았다(`stopped`)."""
    key = _cdep(tmp_path, monkeypatch, {"status": "stopped", "reason": "no_marker"})
    _save_login(key)
    target = store.app_target()
    assert target is not None
    stored = store.current()
    assert stored is not None
    assert store.mark_stopped(target, bdq_login.REASON_NO_MARKER, cipher=stored.cipher).ok
    bdq_login.forget_state()
    bdq_login.start_in_app({report_contract.BDQ_SECRET_KEY_ENV: key.decode("ascii")})

    assert active_state(AppTest.from_string(ALERTS_ONLY).run(), STOP) is not None


def test_a_stop_made_by_this_runs_query_ends_the_run_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면 본문의 조회가 멈춤 · 토큰 실패를 만든 그 회차 — 앞 표지는 해소지만 같은 회차의 마지막
    표지는 선다(개발자가 실패를 본 그 자리에서 Alarm 을 열어도 있다). 다음 회차의 앞 표지도 같은
    지문으로 서고 끝 칸은 빈 자리다(이벤트 칸 한 자리)."""
    key = _cdep(tmp_path, monkeypatch, {"status": "ok", "reason": "", "minutes": 479})
    _save_login(key)
    monkeypatch.setattr(bdq_login, "attempt_login", _killed_child)
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "demo_env_user")

    app = AppTest.from_string(IN_RUN)
    app.session_state["query_now"] = True
    app.run()

    assert not list(app.exception)
    assert [note["active"] for note in states(app, STOP)] == [False, True]
    raised: dict[str, str] = {}
    for code in (STOP, FAILURE):
        last = _last_state(app, code)
        assert last is not None and last["active"], code
        raised[code] = last["fp"]

    app.run()

    for code in (STOP, FAILURE):
        notes = states(app, code)
        assert [note["active"] for note in notes] == [True], code
        assert notes[0]["fp"] == raised[code], code


def test_the_late_alert_slot_is_one_empty_place_when_nothing_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회가 없는 회차 — 끝 칸은 빈 스타일 한 자리다(갈래와 상관없이 늘 한 자리)."""
    key = _cdep(tmp_path, monkeypatch, {"status": "ok", "reason": "", "minutes": 479})
    _save_login(key)

    app = AppTest.from_string(IN_RUN).run()

    assert [note["active"] for note in states(app, STOP)] == [False]
    bodies = [str(element.proto.body) for element in app._tree.get("html")]
    assert bodies[-1] == "<style></style>"


def test_the_late_alert_is_off_the_cd_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """결과 파일이 없는 서버(개발 · 사내 PC · 시험) — 앞 · 끝 모두 Streamlit 호출이 없다."""
    assert container_start_check.render_token_alert() is None
    calls: list[object] = []
    monkeypatch.setattr(alerts, "emit", lambda *args, **_kwargs: calls.append(args))
    container_start_check.render_token_alert_late(None)
    assert calls == []


def test_app_ends_a_finished_run_with_the_late_token_alert() -> None:
    """`app.py` — 화면 앞에서 토큰 알림의 표지를 받아 두고, 화면이 끝까지 돈 회차(멈춤 예외 밖)의
    끝에서 `render_token_alert_late` 에 넘긴다."""
    source = APP_PATH.read_text(encoding="utf-8")
    lines: defaultdict[str, list[int]] = defaultdict(list)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            lines[node.func.id].append(node.lineno)
    assert len(lines["render_token_alert"]) == 1 and len(lines["render_token_alert_late"]) == 1
    assert "token_alerts = render_token_alert()" in source
    assert "render_token_alert_late(token_alerts)" in source
    (top,) = lines["render_token_alert"]
    (late,) = lines["render_token_alert_late"]
    assert top < min(lines["run_core_page"]) < late < max(lines["note_run_end"])
    stop_branch = source.index("except StopException as stop:")
    late_at = source.index("render_token_alert_late(token_alerts)")
    assert stop_branch < late_at < source.index("app_run.finish()\n", stop_branch)


def test_the_late_alert_names_the_runs_it_does_not_cover() -> None:
    """끝 표지가 덮지 못하는 회차 둘(멈춘 회차 · 프래그먼트 · 팝업 본문만 다시 도는 회차)을
    설명이 말하고, 운영 문서에 「다음 회차부터」 만 말하던 옛 글이 없다 — AppTest 는 프래그먼트만
    다시 돌리지 못해 그 회차는 문서로만 묶는다(다음 전체 회차의 앞 표지는 위 첫 시험이 본다)."""
    doc = container_start_check.render_token_alert_late.__doc__ or ""
    assert "st.stop()" in doc and "프래그먼트 · 팝업 본문만 다시 도는 회차" in doc
    setup = (APP_PATH.parent / "docs" / "bigdataquery_webide_setup.md").read_text(encoding="utf-8")
    assert "페이지 안이면 알림은 다음 회차부터 선다" not in " ".join(setup.split())
