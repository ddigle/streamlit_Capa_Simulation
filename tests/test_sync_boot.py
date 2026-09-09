# Purpose: managed 모드에서만 동기화 등록이 켜지는지 검증한다.

from __future__ import annotations

import pytest

from capa_simulation import sync_boot
from capa_simulation.io import object_storage
from capa_simulation.persistence import sync_state
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH


@pytest.fixture(autouse=True)
def _isolated_registry() -> object:
    sync_state.clear_all()
    yield
    sync_state.clear_all()


def _settings(mode: str) -> object_storage.StorageSettings:
    return object_storage.StorageSettings(
        mode=mode,  # type: ignore[arg-type]
        endpoint_url="http://example.invalid:9020",
        bucket="bucket",
        profile="profile",
        region="us-east-1",
        capabilities={},
    )


def test_local_mode_registers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """개발 PC 의 기본값이다. 등록이 없으면 사이드카 파일도 생기지 않는다."""
    monkeypatch.setattr(sync_boot, "load_settings", lambda: _settings("local"))

    assert sync_boot.enable_sync_state_if_managed() is False
    assert sync_state.is_enabled(DUCKDB_PATH) is False


def test_managed_mode_registers_both_databases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_boot, "load_settings", lambda: _settings("managed"))

    assert sync_boot.enable_sync_state_if_managed() is True
    assert sync_state.is_enabled(DUCKDB_PATH) is True
    assert sync_state.is_enabled(EQUIPMENT_DUCKDB_PATH) is True


def test_unreadable_settings_do_not_block_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """설정이 깨져도 앱은 떠야 한다. 동기화는 꺼진 채로 둔다."""

    def _raise() -> object_storage.StorageSettings:
        raise ValueError("CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다")

    monkeypatch.setattr(sync_boot, "load_settings", _raise)

    assert sync_boot.enable_sync_state_if_managed() is False
    assert sync_state.is_enabled(DUCKDB_PATH) is False
