# Purpose: 로그인 최대 시간 10분 전 사건 알림(AD-20)이 그 끝에만 · 한 번 · 고정 id 로 담기는지 본다.

"""`components/sso_expiry.py`(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-expiry).

최대 시간이 정한 끝 10분 안의 첫 회차에 `AD-20` 을 한 번 담는다. 유휴 끝(쓰는 동안 늘어난다)에는
담지 않는다. 같은 세션의 다음 회차는 세션 칸이, 같은 탭의 새 세션은 고정 id 가 막는다.
"""

from __future__ import annotations

import json

import pytest
from alert_marks import alert_notes
from sso_support import renewed_session, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.auth.identity import Identity
from capa_simulation.components import sso_expiry

LOGIN_AT = 1_000_000


def _capped_identity() -> tuple[Identity, int]:
    """쓰는 동안 갱신해 끝이 최대 시간(처음 로그인 + 최대)에 닿은 신원과 그 끝."""
    cfg = use_config()
    cap = LOGIN_AT + cfg.session_max_seconds
    renewed_at = cap - cfg.session_seconds + 600
    _token, claims = renewed_session(cfg, login_at=LOGIN_AT, renew_at=[renewed_at])
    identity = Identity.from_claims(claims)
    assert identity.exp == cap, "갱신이 상한에서 멈췄다"
    return identity, cap


def test_only_the_maximum_end_within_ten_minutes_counts() -> None:
    """최대 시간이 정한 끝 10분 안에서만 남은 분(올림)이다 — 그 밖 · 지난 끝은 `None`."""
    identity, cap = _capped_identity()
    cfg = use_config()

    assert sso_expiry.minutes_to_cap(identity, cfg, cap - 11 * 60) is None
    assert sso_expiry.minutes_to_cap(identity, cfg, cap - 10 * 60) == 10
    assert sso_expiry.minutes_to_cap(identity, cfg, cap - 3 * 60 + 1) == 3
    assert sso_expiry.minutes_to_cap(identity, cfg, cap - 1) == 1
    assert sso_expiry.minutes_to_cap(identity, cfg, cap) is None


def test_an_idle_end_does_not_alert() -> None:
    """쓰지 않아 끝나는 끝은 쓰는 동안 늘어난다 — 10분 안이어도 알리지 않는다."""
    cfg = use_config()
    _token, claims = renewed_session(cfg, login_at=LOGIN_AT, renew_at=[])
    identity = Identity.from_claims(claims)

    assert sso_expiry.minutes_to_cap(identity, cfg, identity.exp - 5 * 60) is None


def test_the_period_follows_the_maximum_hours() -> None:
    assert sso_expiry._period(use_config()) == "하루 한 번"
    assert sso_expiry._period(use_config({"CAPA_SSO_SESSION_MAX_HOURS": "48"})) == "48시간에 한 번"


# 한 회차에 알림을 담고 표지 자리 하나로 보낸다 — 앱의 알림 칸 대신.
SCRIPT = """
import json
import os

from capa_simulation import alerts
from capa_simulation.auth.identity import Identity
from capa_simulation.components import sso_expiry

fields = json.loads(os.environ["SSO_EXPIRY_IDENTITY"])
# 앞 회차의 화면 — `app.py` 는 이 알림을 담은 뒤에야 이번 회차의 화면을 적는다.
alerts.note_page("HOME", "home")
sso_expiry.note_expiry_alert(Identity(**fields), now=int(os.environ["SSO_EXPIRY_NOW"]))
alerts.flush()
"""


def _run(at: AppTest) -> list[dict[str, object]]:
    return [note for note in alert_notes(at.run()) if note.get("code") == sso_expiry.ALERT_CODE]


def test_the_alert_is_queued_once_with_a_fixed_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """첫 회차에 한 번 담고 같은 세션의 다음 회차에는 다시 담지 않는다. 새 세션(새로고침)이 다시
    담아도 id 가 같아 같은 브라우저 탭은 한 번만 띄운다."""
    identity, cap = _capped_identity()
    monkeypatch.setenv("SSO_EXPIRY_IDENTITY", json.dumps(identity.__dict__))
    monkeypatch.setenv("SSO_EXPIRY_NOW", str(cap - 7 * 60 - 30))

    at = AppTest.from_string(SCRIPT)
    [first] = _run(at)
    again = _run(at)
    [fresh] = _run(AppTest.from_string(SCRIPT))

    assert first["short"] == "로그인 최대 시간까지 8분 — 저장해 두세요"
    assert first["full"] == (
        "하루 한 번 통합인증을 다시 확인합니다. 끝나면 다시 로그인해야 하고 저장하지 않은 편집은 "
        "사라집니다."
    )
    assert (first["kind"], first["level"]) == ("event", "action")
    assert first["id"] == sso_expiry.expiry_alert_id(identity)
    # 어느 화면의 일도 아니다 — 앞 회차의 화면(이동 회차면 떠나온 화면)을 달지 않는다.
    assert "page" not in first and "href" not in first
    assert again == [], "같은 세션은 한 번"
    assert fresh["id"] == first["id"], "새 세션이 다시 담아도 브라우저 탭은 id 로 한 번만 띄운다"


def test_nothing_is_queued_outside_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    identity, cap = _capped_identity()
    monkeypatch.setenv("SSO_EXPIRY_IDENTITY", json.dumps(identity.__dict__))
    monkeypatch.setenv("SSO_EXPIRY_NOW", str(cap - 20 * 60))

    assert _run(AppTest.from_string(SCRIPT)) == []


def test_the_code_is_a_registered_action_event() -> None:
    spec = alerts.spec(sso_expiry.ALERT_CODE)
    assert (spec.level, spec.kind) == ("action", "event")
    assert len(sso_expiry.SHORT_TEXT.format(minutes=10)) <= alerts.SHORT_LIMIT
