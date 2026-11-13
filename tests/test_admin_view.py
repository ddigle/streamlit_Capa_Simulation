# Purpose: 관리자 몫 보기 판정이 통합인증 꺼짐에서 누구나, 켜짐에서 관리자만 참인지 시험한다.

"""관리자 몫 보기(`components/admin_view.py` — 2026-11-14 「앱 대신 뜨는 화면」 보드 카드
p1-not-canonical · p2-sync 리뷰 반영 「통합인증이 꺼진 서버는 지금처럼 누구에게나」)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import admin_view, sso_identity


@pytest.mark.parametrize("mode", [SsoMode.OFF, SsoMode.BROKEN])
def test_a_server_without_sign_in_shows_admin_notes_to_everyone(
    monkeypatch: pytest.MonkeyPatch, mode: SsoMode
) -> None:
    monkeypatch.setattr(runtime, "config", lambda: SimpleNamespace(mode=mode))
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: False)

    assert admin_view.admin_notes_visible() is True


@pytest.mark.parametrize("admin", [True, False])
def test_a_signed_in_server_shows_admin_notes_to_the_admin_only(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    monkeypatch.setattr(runtime, "config", lambda: SimpleNamespace(mode=SsoMode.ON))
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: admin)

    assert admin_view.admin_notes_visible() is admin
