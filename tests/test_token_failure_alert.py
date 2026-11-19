# Purpose: BigDataQuery 토큰 실패 관리자 알림(AD-10)이 C-DEP 관리자에게만 서고 풀리는지 검증한다.

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from alert_marks import active_state, states
from streamlit.testing.v1 import AppTest
from test_object_sync_admin import ADMIN, USER, _app_test, _real_viewer
from test_sso_access import session_token

from capa_simulation import alerts, sync_boot
from capa_simulation import settings as app_settings
from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import container_start_check, sso_identity
from capa_simulation.io import bdq_token
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

SCRIPT = """
from capa_simulation.components.container_start_check import render_token_alert

render_token_alert()
"""
CODE = container_start_check.TOKEN_ALERT_CODE


def _report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    token: tuple[str, str] = (report_contract.STATUS_OK, "토큰 파일을 씀"),
) -> None:
    """C-DEP 시작 스크립트가 남기는 결과 파일 — 있으면 C-DEP 서버다."""
    path = tmp_path / "container_start.json"
    steps = {name: (report_contract.STATUS_OK, "정상") for name in report_contract.STEPS}
    steps[report_contract.STEP_TOKEN] = token
    path.write_text(
        json.dumps(
            {
                "version": report_contract.REPORT_VERSION,
                "written_at": "2026-11-12T00:00:00+09:00",
                "steps": {
                    name: {"status": status, "reason": reason}
                    for name, (status, reason) in steps.items()
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_settings, "CONTAINER_START_REPORT_PATH", path)


def _admin(monkeypatch: pytest.MonkeyPatch, *, admin: bool = True) -> None:
    monkeypatch.setattr(sso_identity, "viewer_is_developer", lambda: admin)


def _query(monkeypatch: pytest.MonkeyPatch, error: BaseException | None) -> None:
    """어댑터 길(`call_get_data`)로 조회 한 번 — `error` 가 있으면 그 예외로 실패한다. 패키지 자리
    바꿔 끼우기는 그 조회 안에서만이다(뒤의 `app.py` 실행이 진짜 import 를 쓴다)."""

    def get_data(**_kwargs: object) -> pd.DataFrame:
        if error is not None:
            raise error
        return pd.DataFrame({"a": [1]})

    with monkeypatch.context() as patch:
        patch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
        patch.setattr(importlib, "import_module", lambda _: SimpleNamespace(getData=get_data))
        try:
            adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
        except adapter.BigDataQueryCallError:
            pass


def test_the_alert_is_registered_as_an_action_state() -> None:
    spec = alerts.REGISTRY[CODE]
    assert (spec.level, spec.kind) == ("action", "state")


def test_nothing_is_written_off_the_cd_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """결과 파일이 없는 서버(개발 · 사내 PC · WebIDE · 시험) — 조회가 토큰으로 실패해도 Streamlit
    호출이 없어 요소 순번이 그대로다."""
    _admin(monkeypatch)
    _query(monkeypatch, Exception("HTTP 500 invalid token"))
    assert adapter.last_query_failed_on_token() is True
    calls: list[str] = []
    monkeypatch.setattr(alerts, "state", lambda *args, **_kwargs: calls.append(args[0]))
    monkeypatch.setattr(alerts, "emit", lambda *_args, **_kwargs: calls.append("emit"))

    container_start_check.render_token_alert_late(container_start_check.render_token_alert())

    assert calls == []


def test_a_token_failure_asks_the_package_once_and_raises_the_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """토큰 갈래로 실패한 조회는 패키지(`getData`)를 한 번만 부르고 — 다시 묻지 않는다 — 프로세스
    표지(`AD-10`)를 세운다."""
    calls: list[str] = []

    def get_data(**_kwargs: object) -> pd.DataFrame:
        calls.append("getData")
        raise ConnectionError("500 invalid token")

    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: SimpleNamespace(getData=get_data))

    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert caught.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert calls == ["getData"]
    assert adapter.last_query_failed_on_token() is True


def test_a_failed_start_token_step_tells_the_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작 점검 토큰 줄이 「실패」 면 조회 전에도 관리자에게 — 고칠 자리는 Admin Area 다."""
    reason = (
        "CAPA_BDQ_TOKEN 을 푼 내용이 16바이트보다 짧음 — 토큰이 아닌 값으로 보고 파일을 쓰지 않음"
    )
    _report(tmp_path, monkeypatch, token=(report_contract.STATUS_FAILED, reason))
    _admin(monkeypatch)

    app = AppTest.from_string(SCRIPT).run()

    note = active_state(app, CODE)
    assert note is not None
    assert reason in note["full"] and "`" not in note["full"]
    assert "최근 BigDataQuery 조회" not in note["full"]
    # 시작 점검 실패의 까닭은 토큰 값만이 아니다 — 할 일은 그 까닭 고치기다.
    assert "그 까닭을 고치고 CI/CD" in note["full"] and "새 토큰" not in note["full"]
    assert (note["page"], note["href"]) == (tab_label(ADMIN_AREA), ADMIN_AREA.href)
    assert note["short"] == "BigDataQuery 로그인 토큰 실패 — 조회가 막힙니다"
    assert note["level"] == "action"


def test_a_token_failure_on_a_query_tells_the_administrator_until_a_query_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작 점검은 정상이어도 조회가 토큰 갈래로 실패하면 선다. 다른 실패는 표지를 그대로 두고,
    성공한 조회가 풀어 해소로 닫힌다."""
    _report(tmp_path, monkeypatch)
    _admin(monkeypatch)
    app = AppTest.from_string(SCRIPT).run()
    assert active_state(app, CODE) is None

    _query(monkeypatch, ConnectionError("500 invalid token"))
    note = active_state(app.run(), CODE)
    assert note is not None and "최근 BigDataQuery 조회가 토큰 갈래로 실패" in note["full"]
    # 할 일은 Admin 「토큰 넣기」 — 다시 띄우면 CD 환경변수 값으로 돌아가니 그 값도 바꿔 둔다.
    assert "「토큰 넣기」 로 새 토큰을 넣으면" in note["full"] and "`" not in note["full"]
    assert "CD 환경변수 CAPA_BDQ_TOKEN 값으로 돌아가니" in note["full"]

    _query(monkeypatch, Exception("Connection refused"))
    assert active_state(app.run(), CODE) is not None

    _query(monkeypatch, None)
    assert adapter.last_query_failed_on_token() is False
    assert active_state(app.run(), CODE) is None
    assert [item["active"] for item in states(app, CODE)] == [False]


def test_a_query_failure_with_the_package_environment_token_asks_to_change_that_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """패키지가 환경변수 `BIGDATAQUERY_LOGIN_TOKEN` 을 읽는 서버는 「토큰 넣기」 가 잠긴다 — 할 일은
    그 값 바꾸기 + CI/CD 이고 잠긴 단추를 가리키지 않는다. 값은 글에 없다."""
    _report(tmp_path, monkeypatch)
    _admin(monkeypatch)
    monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "FAKE-env-token-0000000000")
    _query(monkeypatch, ConnectionError("500 invalid token"))

    note = active_state(AppTest.from_string(SCRIPT).run(), CODE)

    assert note is not None
    full = note["full"]
    assert "최근 BigDataQuery 조회가 토큰 갈래로 실패" in full
    assert f"환경변수 {bdq_token.LOGIN_TOKEN_ENV} 의 토큰을 씁니다" in full
    assert "CI/CD" in full and "「토큰 넣기」" not in full
    assert "FAKE-env-token" not in full and "`" not in full


def test_a_failed_start_with_a_failed_query_asks_for_the_start_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작 점검이 실패면 토큰 파일이 없어 조회도 토큰으로 실패한다 — 둘 다 적고, 할 일은 시작
    점검 까닭대로 고치기 하나다."""
    _report(tmp_path, monkeypatch, token=(report_contract.STATUS_FAILED, "까닭"))
    _admin(monkeypatch)
    _query(monkeypatch, Exception("HTTP 500 invalid token"))

    note = active_state(AppTest.from_string(SCRIPT).run(), CODE)

    assert note is not None
    full = note["full"]
    assert "「로그인 토큰 파일」 줄이 실패입니다(까닭)" in full
    assert "최근 BigDataQuery 조회가 토큰 갈래로 실패" in full
    assert "그 까닭을 고치고 CI/CD" in full and "새 토큰" not in full
    assert "`" not in full


def test_a_skipped_start_token_step_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _report(tmp_path, monkeypatch, token=(report_contract.STATUS_SKIPPED, "CD 환경변수 없음"))
    _admin(monkeypatch)

    app = AppTest.from_string(SCRIPT).run()

    assert active_state(app, CODE) is None
    assert [item["active"] for item in states(app, CODE)] == [False]


def test_someone_who_is_not_an_administrator_gets_the_same_slot_without_the_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰은 공용 계정 하나라 고칠 사람이 관리자다 — 다른 사람의 회차는 해소로 부른다(이벤트 칸 한
    자리는 같다)."""
    _report(tmp_path, monkeypatch, token=(report_contract.STATUS_FAILED, "까닭"))
    _admin(monkeypatch, admin=False)

    app = AppTest.from_string(SCRIPT).run()

    assert active_state(app, CODE) is None
    assert [item["active"] for item in states(app, CODE)] == [False]


def test_the_app_raises_the_alert_on_every_screen_of_a_cd_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`app.py` 가 회차마다 부른다 — HOME 첫 화면에서도 관리자 Alarm 에 선다."""
    sync_boot.forget_boot_result()
    _report(tmp_path, monkeypatch)
    _admin(monkeypatch)
    _query(monkeypatch, Exception("HTTP 500 invalid token"))

    try:
        app = _app_test(tmp_path, monkeypatch).run()
    finally:
        sync_boot.forget_boot_result()

    assert not list(app.exception), [element.message for element in app.exception]
    note = active_state(app, CODE)
    assert note is not None and "최근 BigDataQuery 조회가 토큰 갈래로 실패" in note["full"]
    assert len(states(app, CODE)) == 1


def test_a_failure_made_during_the_page_is_raised_at_the_end_of_that_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """진짜 `app.py` — 화면 앞 표지를 낸 뒤 그 회차 화면의 조회가 토큰 갈래로 실패한 꼴(앞 짓기 뒤에
    표지를 세운다). 화면이 끝까지 돈 회차의 끝 칸(`render_token_alert_late`)이 같은 코드 · 범위로
    선 표지를 싣는다 — 같은 회차의 마지막 표지가 지금 상태다."""
    sync_boot.forget_boot_result()
    _report(tmp_path, monkeypatch)
    _admin(monkeypatch)
    built = container_start_check.token_alert_notes
    calls: list[int] = []

    def page_fails_between(*args: object, **kwargs: object) -> list[alerts.AlertNote]:
        calls.append(len(calls))
        if len(calls) == 2:
            adapter._note_token_failure(True)
        return built()

    monkeypatch.setattr(container_start_check, "token_alert_notes", page_fails_between)
    try:
        app = _app_test(tmp_path, monkeypatch).run()
    finally:
        sync_boot.forget_boot_result()

    assert not list(app.exception), [element.message for element in app.exception]
    assert calls == [0, 1]
    assert [item["active"] for item in states(app, CODE)] == [False, True]


@pytest.mark.parametrize(
    ("cookie", "expected"), [(ADMIN, True), (USER, False), (None, False)], ids=str
)
def test_the_administrator_is_judged_from_the_cookie(
    monkeypatch: pytest.MonkeyPatch, cookie: str | None, expected: bool
) -> None:
    """바꿔 끼우지 않은 판정 — 이 연결의 쿠키를 지금 검증한 신원이 명단 관리자인가."""
    _real_viewer(monkeypatch, cookie=cookie)

    assert sso_identity.viewer_is_developer() is expected


def test_nobody_gets_the_alert_with_sso_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """통합인증이 꺼진 C-DEP 에는 신원이 없어 관리자도 없다 — 관리자 쿠키가 남아 있어도 서지
    않는다."""
    cfg = _real_viewer(monkeypatch, cookie=ADMIN)
    token = session_token(cfg, ADMIN)
    runtime.reset()
    assert runtime.start({}).mode is not SsoMode.ON
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})
    _report(tmp_path, monkeypatch, token=(report_contract.STATUS_FAILED, "까닭"))

    assert sso_identity.viewer_is_developer() is False
    app = AppTest.from_string(SCRIPT).run()
    assert active_state(app, CODE) is None
    assert [item["active"] for item in states(app, CODE)] == [False]
