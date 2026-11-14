# Purpose: 접속 사건이 감사 줄이 되는지 — 로그인 · 무인증 홍수 · 세션 닫힘 · 기동 · 등급.

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
from asgi_driver import AsgiResponse, http
from sso_support import (
    LOGINID,
    expiring_signing,
    id_token_claims,
    later_expiring_signing,
    make_id_token,
    signing,
    sso_environ,
    use_config,
)
from starlette.applications import Starlette
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import boot, recorder, spool
from capa_simulation.auth import access_store, names, runtime, server
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

FORM = {"content-type": "application/x-www-form-urlencoded"}
INST = "0a0b0c0d0e0f"


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment


@pytest.fixture()
def clock(tmp_path: Path) -> Iterator[Clock]:
    ticking = Clock()
    spool.configure(tmp_path)
    recorder.start(env="cdep", version="test", inst=INST, clock=ticking)
    yield ticking


def _routes() -> Starlette:
    return Starlette(routes=sso_routes())


def _login(app: Starlette, cfg: SsoConfig) -> AsgiResponse:
    started = http(app, "GET", f"{names.LOGIN_PATH}?next={quote('/', safe='')}")
    query = {
        key: values[0]
        for key, values in parse_qs(urlsplit(started.header("location") or "").query).items()
    }
    cookie = started.cookie(cfg.state_cookie(query["state"]))
    assert cookie is not None
    token = make_id_token(id_token_claims(query["nonce"]))
    return http(
        app,
        "POST",
        names.CALLBACK_PATH,
        headers={**FORM, "cookie": f"{cookie.name}={cookie.value}"},
        body=urlencode({"id_token": token, "state": query["state"]}).encode(),
    )


def _payload(lines: list[dict[str, Any]]) -> str:
    return json.dumps(lines, ensure_ascii=False)


def test_a_login_through_the_routes_is_one_line_with_the_name_only(clock: Clock) -> None:
    cfg = use_config()
    recorder.set_grader(boot.grader(cfg))

    response = _login(_routes(), cfg)

    assert response.status == 303
    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == ["authn_login_success"]
    (line,) = lines
    assert (line["actor"], line["verified"], line["grade"]) == (LOGINID, True, "admin")
    assert line["name"] == "개발 사용자"
    assert line["det"] == {"hours": 6, "max_hours": 24}
    assert len(line["sid8"]) == 8
    payload = _payload(lines)
    assert "개발부서" not in payload and "jti" not in payload
    session = response.cookie(cfg.session_cookie)
    assert session is not None and session.value not in payload


def test_an_unauthenticated_flood_is_one_summary_line_per_hour(clock: Clock) -> None:
    use_config()
    app = _routes()
    for _ in range(30):
        http(app, "POST", names.CALLBACK_PATH, headers=FORM, body=b"state=x&id_token=y")

    assert recorder.take_pending() == []
    clock.moment += timedelta(hours=1)
    (line,) = recorder.take_pending()
    assert line["ev"] == "authn_login_fail_summary"
    assert line["det"]["total"] == 30
    assert line["actor"] == ""


def test_logout_and_closed_sessions_become_session_lines(clock: Clock) -> None:
    cfg = use_config()
    now = int(time.time())
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=now)
    http(_routes(), "GET", names.LOGOUT_PATH, headers={"cookie": f"{cfg.session_cookie}={token}"})
    runtime.record_event("session_closed", reason="expired", loginid=LOGINID, end="idle")
    runtime.record_event("session_closed", reason="denied", loginid=LOGINID)
    runtime.record_event("session_closed", reason="missing", loginid="-")

    lines = recorder.take_pending()
    assert [(line["ev"], line["out"]) for line in lines] == [
        ("session_logout", "success"),
        ("session_expired", "success"),
        ("authz_fail_session", "denied"),
    ]
    assert lines[0]["sid8"] == issued.sid[:8]
    assert lines[1]["det"] == {"end": "idle"}


def test_renewals_fold_into_one_line_per_hour(clock: Clock) -> None:
    for outcome in ("renewed", "renewed", "skipped", "unauthorized"):
        runtime.count_refresh(outcome)

    assert recorder.take_pending() == []
    clock.moment += timedelta(hours=1)
    (line,) = recorder.take_pending()
    assert line["ev"] == "session_renew_summary"
    assert line["det"]["counts"] == {"renewed": 2, "skipped": 1, "unauthorized": 1}


def test_boot_turns_the_recorder_on_only_for_an_enabled_sso(tmp_path: Path) -> None:
    spool.configure(tmp_path)
    off = use_config(drop=[names.ENV_CLIENT_ID])

    assert boot.start(off) is False
    assert not recorder.enabled()

    cfg = use_config()
    assert boot.start(cfg) is True
    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == ["sys_startup", "authz_admin_config"]
    assert set(lines[0]["det"]) == {"env", "sso", "sync", "spool"}
    assert (lines[0]["det"]["env"], lines[0]["det"]["sso"]) == ("cdep", "on")
    assert set(lines[1]["det"]) == {"admins", "admin_fp"}
    assert lines[1]["det"]["admins"] == 1
    assert len(lines[1]["det"]["admin_fp"]) == 8
    assert LOGINID not in _payload(lines)
    assert all(line["actor"] == "system:app" and line["grade"] == "system" for line in lines)


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    mock, endpoint = start_mock(store)
    yield store, endpoint
    mock.shutdown()
    mock.server_close()


def _boot_like_the_entry(
    store: MockStore, endpoint: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> SsoConfig:
    """`capa_server.py` 의 차례 그대로 — `start_sso()`(설정 · 기동 명단 읽기) 뒤 `boot.start`."""
    spool.configure(tmp_path)
    runtime.reset()
    environ = sso_environ(
        {
            names.ENV_S3_ACCESS_KEY: store.access_key,
            names.ENV_S3_SECRET_KEY: store.secret_key,
            names.ENV_S3_ENDPOINT: endpoint,
            names.ENV_S3_BUCKET: store.bucket,
            names.ENV_S3_REGION: store.region,
        }
    )
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    cfg = server.start_sso()
    assert boot.start(cfg) is True
    return cfg


def test_a_list_read_failure_at_boot_is_one_audit_line_after_the_recorder_is_on(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """기동 명단 읽기는 진입 파일에서 기록기보다 먼저 돈다(`start_sso` → `start_audit`). 그 실패도
    「접속 명단 읽기 실패」 한 줄로 남는다(시작 줄 뒤). 뒤따르는 자가 회복 실패는 누계만 센다 —
    들어오지 못하는 사람이 되풀이해 남길 수 있다(`runtime.ACCESS_RETRY_FAILED_EVENT`)."""
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")

    cfg = _boot_like_the_entry(store, endpoint, monkeypatch, tmp_path)

    assert access_store.is_unread(cfg)
    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == [
        "sys_startup",
        "authz_admin_config",
        "sys_access_read_fail",
    ]
    failed = lines[-1]
    assert (failed["out"], failed["actor"], failed["grade"]) == ("fail", "system:sso", "system")
    problem = runtime.access_source()
    assert problem is not None and problem.problem is not None
    assert failed["why"] == problem.problem.kind
    assert failed["det"] == {"reason": problem.problem.kind, "status": "503"}

    access_store.retry_unread(cfg, now=int(time.time()) + access_store.RETRY_SECONDS + 1)

    assert runtime.access_retry_failures() == 1
    assert recorder.take_pending() == []


def test_a_good_list_read_at_boot_leaves_no_failure_line(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, endpoint = mock_s3

    cfg = _boot_like_the_entry(store, endpoint, monkeypatch, tmp_path)

    assert not access_store.is_unread(cfg)
    assert [line["ev"] for line in recorder.take_pending()] == [
        "sys_startup",
        "authz_admin_config",
    ]


def test_expiring_signing_certs_at_boot_are_one_audit_line_each(tmp_path: Path) -> None:
    """서명 인증서 만료 임박(`cert_expiring`)은 설정을 읽는 `runtime.start` 에서만 나고, 그때는 감사
    기록기가 켜지기 전이다. 기록기를 켠 자리에서 만료가 30일 안인 인증서마다 「서명 인증서 만료
    임박」 한 줄이 선다(시작 줄 뒤 · 인증서 차례). S3 명단이 없는 서버에서도 선다 — 명단 읽기
    따라잡기와 따로다. 남은 날은 서버 로그의 `cert_expiring` 과 같은 셈(내림)이다."""
    spool.configure(tmp_path)
    cfg = use_config(
        {
            names.ENV_SIGNING_CERT: ",".join(
                (
                    expiring_signing().der_b64,
                    signing().der_b64,
                    later_expiring_signing().der_b64,
                )
            )
        }
    )
    assert not access_store.is_on(cfg)
    announced = [
        event.value("days")
        for event in reversed(runtime.recent_events(anonymous=False))
        if event.event == "cert_expiring"
    ]
    assert announced == ["9", "19"]

    assert boot.start(cfg) is True

    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == [
        "sys_startup",
        "authz_admin_config",
        "sys_cert_expiring",
        "sys_cert_expiring",
    ]
    for line in lines[2:]:
        assert (line["out"], line["actor"], line["grade"]) == ("success", "system:sso", "system")
    assert [line["det"] for line in lines[2:]] == [{"days": 9}, {"days": 19}]


def test_the_deploy_version_falls_back_to_the_app_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """기동 줄의 판 글은 적용 기록의 stamp(`deploy_stamp`)이고, 기록이 없거나 읽기가 터져도 앱 판
    글로 선다 — 판 글 하나로 감사 기동이 멈추지 않는다."""
    import capa_simulation.deploy_stamp as deploy_stamp
    import capa_simulation.settings as settings

    def broken() -> str | None:
        raise OSError("stamp")

    monkeypatch.setattr(deploy_stamp, "deployed_stamp", lambda: None)
    assert boot.deploy_version() == settings.APP_VERSION
    monkeypatch.setattr(deploy_stamp, "deployed_stamp", lambda: "202611140000")
    assert boot.deploy_version() == "202611140000"
    monkeypatch.setattr(deploy_stamp, "deployed_stamp", broken)
    assert boot.deploy_version() == settings.APP_VERSION


def test_the_grader_knows_only_admins_and_users() -> None:
    """기록을 보는 사람은 관리자뿐이다 — 판정기의 등급은 관리자 · 사용자 둘이다."""
    cfg = use_config()

    grade = boot.grader(cfg)
    assert (grade(LOGINID), grade(LOGINID.upper()), grade("other.user")) == (
        "admin",
        "admin",
        "user",
    )


SESSION_SCRIPT = """
from capa_simulation.audit import recorder
from capa_simulation.components import audit_actor, sso_identity

identity = sso_identity.require_signed_in()
audit_actor.note_session(identity)
recorder.note_work("data_scenario_delete", tgt={"type": "scenario", "id": "s-1"})
audit_actor.drain()
"""


def test_the_session_line_is_once_per_session_and_work_takes_the_cookie_actor(
    clock: Clock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from capa_simulation.components import audit_actor

    cfg = use_config()
    runtime.mark_gate_installed()
    recorder.set_grader(boot.grader(cfg))
    audit_actor.install()
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})

    app = AppTest.from_string(SESSION_SCRIPT).run()
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    assert [line["ev"] for line in lines] == [
        "session_created",
        "data_scenario_delete",
        "data_scenario_delete",
    ]
    created = lines[0]
    assert created["sid8"] == issued.sid[:8]
    assert len(created["tab8"]) == 8 and created["ip"] == ""
    assert all((line["actor"], line["verified"]) == (LOGINID, True) for line in lines)
    assert lines[1]["grade"] == "admin"
