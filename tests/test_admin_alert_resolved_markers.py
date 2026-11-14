# Purpose: 관리자 몫 상태 알림의 해소 표지가 일반 · 익명 회차에 관리자 글을 싣지 않는지 지킨다.

"""관리자 몫 상태 알림(조건이 있어도 관리자 회차에만 서는 것)의 해소 표지.

일반 사용자 · 익명 회차는 같은 알림을 해소(`active` 거짓)로 부른다 — 회차마다 이벤트 칸 자리 수가
같아야 해서다. 그 해소 표지는 숨은 DOM(`[data-capa-alerts]`)에 실리므로 짧은 글 · 전문을 싣지 않는다
(등록부 이름으로 떨어진다 — `alerts._base`). 싣으면 일반 사용자 회차에 운영 낱말(환경변수 이름 ·
Admin 의 할 일 · 명단 등록 수)이 실린다(`sso_refresh_alert` 와 같은 꼴).

조건을 모두 켠 채 관리자 회차에서 서는 알림을 먼저 확인하고(헛통과 막기), 같은 조건의 일반 · 익명
회차에서 그 알림 표지가 하나씩 · 해소이고 · 글이 등록부 이름뿐인지 본다.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from alert_marks import alert_notes, states
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts, sync_boot
from capa_simulation.audit import recorder
from capa_simulation.audit import shipper as audit_shipper
from capa_simulation.auth import access_store, names, runtime
from capa_simulation.auth.access import SourceProblem
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import sso_identity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

ADMIN = "demo.admin"
USER = "demo.user"
SCRIPT = """
from capa_simulation.components.app_credits import render_app_credits
from capa_simulation.components.object_sync_status import render_object_sync_alerts

render_app_credits()
render_object_sync_alerts()
"""
# 조건이 있어도 관리자 회차에만 서는 상태 알림 — 접속 명단 셋 · 감사 둘 · 로그인 갱신 거절 ·
# 정본 점검 못 함.
ADMIN_ONLY = ("AD-08", "AD-09", "AD-19", "AD-12", "AD-13", "AD-21", "SY-06")


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    mock, endpoint = start_mock(store)
    yield store, endpoint
    mock.shutdown()
    mock.server_close()


def _every_admin_condition(
    store: MockStore, endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> SsoConfig:
    """S3 명단 · 감사 기록 · 동기화 알림이 서는 켜진 운영 서버에서 일곱 알림의 조건을 모두 켠다."""
    cfg = use_config(
        {
            names.ENV_ACCESS_ADMINS: ADMIN,
            names.ENV_ACCESS_USERS: USER,
            names.ENV_S3_ACCESS_KEY: store.access_key,
            names.ENV_S3_SECRET_KEY: store.secret_key,
            names.ENV_S3_ENDPOINT: endpoint,
            names.ENV_S3_BUCKET: store.bucket,
            names.ENV_S3_REGION: store.region,
        }
    )
    access_store.read_at_start(cfg)
    access_store.register_self(cfg, "demo.first")
    source = runtime.access_source()
    assert source is not None
    # 읽어 둔 뒤의 실패(AD-08) · 환경변수 첫 판(AD-09) · 최근 스스로 등록(AD-19)을 한 벌에.
    runtime.publish_access_source(
        replace(source, problem=SourceProblem("unreachable"), seeded=True)
    )
    recorder.start(env="cdep", version="test", inst="0a0b0c0d0e0f")
    monkeypatch.setattr(audit_shipper, "chain_problems", lambda: ("2026-10-01",))
    runtime.count_refresh("forbidden")
    monkeypatch.setattr(sync_boot, "sync_alerts_possible", lambda: True)
    monkeypatch.setattr(sync_boot, "head_unchecked", lambda: ("CAPA_S3_PROFILE",))
    return cfg


def _run_as(cfg: SsoConfig, loginid: str | None, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    cookies: dict[str, str] = {}
    if loginid is not None:
        token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
        cookies[cfg.session_cookie] = token
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: cookies)
    app = AppTest.from_string(SCRIPT, default_timeout=30).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _registry_fallback(code: str) -> tuple[str, str]:
    """글을 주지 않은 표지의 (짧은 글, 전문) — 등록부 이름(`alerts._base` 의 떨어지는 자리)."""
    entry = alerts.spec(code)
    full = entry.full or entry.short or entry.title
    return alerts.short_text(entry.short or full), full


def _raw(app: AppTest) -> str:
    return json.dumps(alert_notes(app), ensure_ascii=False)


def test_resolved_admin_alerts_carry_no_admin_text_for_users_and_anonymous(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = _every_admin_condition(store, endpoint, monkeypatch)

    admin = _run_as(cfg, ADMIN, monkeypatch)
    admin_texts: list[str] = []
    for code in ADMIN_ONLY:
        [note] = states(admin, code)
        assert note["active"], code
        admin_texts += [str(note["short"]), str(note["full"])]

    for who in (USER, None):
        app = _run_as(cfg, who, monkeypatch)
        for code in ADMIN_ONLY:
            [note] = states(app, code)
            assert not note["active"], (who, code)
            carried: tuple[Any, Any] = (note["short"], note["full"])
            assert carried == _registry_fallback(code), (who, code)
        raw = _raw(app)
        assert [text for text in admin_texts if text in raw] == [], who
