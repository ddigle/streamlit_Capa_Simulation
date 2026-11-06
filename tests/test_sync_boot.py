# Purpose: managed 에서만 동기화가 켜지고 설정 오류는 앱을 띄운 채 까닭을 남기는지 본다.

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from capa_simulation import settings as app_settings
from capa_simulation import sync_boot
from capa_simulation.io import object_storage
from capa_simulation.persistence import sync_state
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

BROKEN_MODE = "CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다: 'manged'"


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    sync_state.clear_all()
    sync_boot.forget_boot_result()
    yield
    sync_state.clear_all()
    sync_boot.forget_boot_result()


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
    """설정이 깨져도 앱은 떠야 한다. 동기화는 꺼진 채로 두고 그 까닭을 남긴다."""

    def _raise() -> object_storage.StorageSettings:
        raise ValueError("CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다")

    monkeypatch.setattr(sync_boot, "load_settings", _raise)

    assert sync_boot.enable_sync_state_if_managed() is False
    assert sync_state.is_enabled(DUCKDB_PATH) is False
    assert sync_boot.sync_disabled_reason() is not None


def test_a_storage_settings_error_turns_sync_off_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_settings` 의 실패는 `ObjectStorageError` 다. 안 잡으면 모든 화면이 트레이스백이다."""

    def _raise() -> object_storage.StorageSettings:
        raise object_storage.ObjectStorageError(BROKEN_MODE)

    monkeypatch.setattr(sync_boot, "load_settings", _raise)

    assert sync_boot.enable_sync_state_if_managed() is False
    assert sync_state.is_enabled(DUCKDB_PATH) is False
    reason = sync_boot.sync_disabled_reason()
    assert reason is not None and "CAPA_S3_SYNC_MODE" in reason


def test_local_mode_has_no_disabled_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_boot, "load_settings", lambda: _settings("local"))

    assert sync_boot.enable_sync_state_if_managed() is False
    assert sync_boot.sync_disabled_reason() is None


def test_settings_are_read_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """앱은 회차마다 이 판정을 부른다. 설정 파일을 회차마다 다시 읽을 까닭이 없다."""
    calls: list[str] = []

    def _count() -> object_storage.StorageSettings:
        calls.append("read")
        return _settings("managed")

    monkeypatch.setattr(sync_boot, "load_settings", _count)

    for _ in range(3):
        assert sync_boot.enable_sync_state_if_managed() is True
    assert sync_boot.sync_disabled_reason() is None

    assert calls == ["read"]


def test_a_long_reason_stays_one_short_line() -> None:
    reason = sync_boot.short_reason(ValueError("첫 줄 " + "가" * 300 + "\n둘째 줄"))

    assert len(reason) <= sync_boot.REASON_MAX_CHARS
    assert "둘째 줄" not in reason


def test_nothing_needs_alerts_on_a_plain_local_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """개발 PC · 시험 — 화면 쪽이 Streamlit 을 하나도 부르지 않는다."""
    monkeypatch.setattr(sync_boot, "load_settings", lambda: _settings("local"))

    assert sync_boot.sync_alerts_possible() is False
    assert sync_boot.handed_over_utc() is None


def test_a_handed_over_pc_needs_its_alert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`init` 한 PC 는 local 이어도 `SY-04` 가 선다."""
    monkeypatch.setattr(sync_boot, "load_settings", lambda: _settings("local"))
    database = tmp_path / "capa_simulation.duckdb"
    monkeypatch.setattr(sync_boot, "DUCKDB_PATH", database)
    sync_state.write_generation(
        sync_state.generation_path(database),
        sync_state.GenerationState(handed_over_utc="2026-11-07T00:00:00Z"),
    )

    assert sync_boot.handed_over_utc() == "2026-11-07T00:00:00Z"
    assert sync_boot.sync_alerts_possible() is True


def test_the_boot_record_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    record = sync_boot.BootRecord(
        action="downloaded",
        seq=4,
        previous_upload_utc=None,
        pull_seconds=2.5,
        finished_at_utc="2026-11-07T00:00:02Z",
        total_bytes=10,
    )

    assert sync_boot.read_boot_record() is None
    sync_boot.write_boot_record(record)
    assert sync_boot.read_boot_record() == record

    sync_boot.clear_boot_record()
    assert sync_boot.read_boot_record() is None


def test_a_broken_boot_record_reads_as_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    path = sync_boot.boot_record_path()
    path.parent.mkdir(parents=True)

    for text in ("{ 깨진", "[]", '{"action": "kept"}'):
        path.write_text(text, encoding="utf-8")
        assert sync_boot.read_boot_record() is None
