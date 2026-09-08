# Purpose: 동기화 사이드카 상태와 변경 표시의 정상·예외 동작을 검증한다.

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from capa_simulation.persistence import sync_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_registry() -> object:
    sync_state.clear_all()
    yield
    sync_state.clear_all()


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(b"not a real duckdb, this module never opens it")
    return path


def test_marking_does_nothing_until_enabled(database: Path) -> None:
    """개발 PC·CI 에서 파일을 하나도 만들지 않아야 한다. 지금 동작이 그대로여야 한다."""
    sync_state.mark_dirty(database)
    sync_state.record_error(database, "무시되어야 한다")

    assert not sync_state.sidecar_path(database).exists()
    assert sync_state.is_enabled(database) is False


def test_mark_dirty_writes_only_for_registered_paths(database: Path, tmp_path: Path) -> None:
    other = tmp_path / "equipment_availability.duckdb"
    other.write_bytes(b"x")
    sync_state.enable({database: "simulation"})

    sync_state.mark_dirty(database)
    sync_state.mark_dirty(other)

    assert sync_state.read_state(database) is not None
    assert not sync_state.sidecar_path(other).exists()


def test_state_round_trips(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    state = sync_state.read_state(database)

    assert state is not None
    assert state.dataset == "simulation"
    assert state.dirty is True


def test_sidecar_path_is_gitignored() -> None:
    """사이드카가 커밋되면 남의 세대가 배포본에 실려 나간다."""
    result = subprocess.run(
        ["git", "check-ignore", "data/capa_simulation.duckdb.sync.json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def test_write_state_leaves_no_half_written_file(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    leftovers = [
        item
        for item in database.parent.iterdir()
        if item.name.startswith(sync_state.sidecar_path(database).name)
        and item != sync_state.sidecar_path(database)
    ]

    assert leftovers == []


def test_missing_or_broken_sidecar_is_treated_as_dirty(database: Path) -> None:
    """모르면 올리는 쪽이 안전하다. 모르면 건너뛰면 저장이 조용히 사라진다."""
    assert sync_state.treat_as_dirty(database) is True

    sync_state.enable({database: "simulation"})
    sync_state.sidecar_path(database).write_text("{ 깨진 JSON", encoding="utf-8")

    assert sync_state.read_state(database) is None
    assert sync_state.treat_as_dirty(database) is True


def test_unknown_sidecar_schema_is_not_guessed(database: Path) -> None:
    sync_state.sidecar_path(database).write_text(
        '{"schema": 99, "dataset": "simulation"}', encoding="utf-8"
    )

    assert sync_state.read_state(database) is None


def test_clear_dirty_records_the_generation_and_clears_unpublished(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)
    sync_state.mark_unpublished(database, snapshot_key="k", sha256="s", reason="포인터 거부")

    sync_state.clear_dirty(database, seq=42, sha256="abc", snapshot_key="simulation/snapshots/x")

    state = sync_state.read_state(database)
    assert state is not None
    assert state.dirty is False
    assert state.base_seq == 42
    assert state.base_sha256 == "abc"
    assert state.unpublished_snapshot_key is None
    assert sync_state.treat_as_dirty(database) is False


def test_unpublished_snapshot_keeps_the_dataset_dirty(database: Path) -> None:
    """게시하지 못한 스냅샷이 남아 있으면 아직 끝난 게 아니다."""
    sync_state.enable({database: "simulation"})
    sync_state.mark_unpublished(database, snapshot_key="k", sha256="s", reason="부모 불일치")

    assert sync_state.treat_as_dirty(database) is True

    sync_state.clear_unpublished(database)

    assert sync_state.treat_as_dirty(database) is False


def test_heartbeat_is_throttled(database: Path) -> None:
    sync_state.enable({database: "simulation"})

    sync_state.touch_heartbeat(database, instance_id="first")
    sync_state.touch_heartbeat(database, instance_id="second")

    state = sync_state.read_state(database)
    assert state is not None
    # 10초 안의 두 번째 호출은 쓰지 않는다.
    assert state.instance_id == "first"


def test_live_instance_ignores_a_stale_heartbeat(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.touch_heartbeat(database, instance_id="ghost")
    state = sync_state.read_state(database)
    assert state is not None
    sync_state.write_state(
        database, type(state)(**{**state.__dict__, "heartbeat_utc": "2020-01-01T00:00:00Z"})
    )

    assert sync_state.live_instance(database) is None


def test_live_instance_reports_another_running_process(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.touch_heartbeat(database, instance_id="other")

    assert sync_state.live_instance(database) == "other"
    assert sync_state.live_instance(database, exclude="other") is None


def test_adopt_generation_writes_even_without_enable(database: Path) -> None:
    """스크립트는 앱 밖에서 돈다. init·adopt 는 등록 없이도 세대를 남겨야 한다."""
    sync_state.adopt_generation(
        database,
        dataset="simulation",
        seq=1,
        sha256="abc",
        snapshot_key="simulation/snapshots/x",
    )

    state = sync_state.read_state(database)
    assert state is not None
    assert state.base_seq == 1
    assert state.dirty is False


def test_two_databases_are_marked_independently(tmp_path: Path) -> None:
    simulation = tmp_path / "capa_simulation.duckdb"
    equipment = tmp_path / "equipment_availability.duckdb"
    simulation.write_bytes(b"x")
    equipment.write_bytes(b"y")
    sync_state.enable({simulation: "simulation", equipment: "equipment"})

    sync_state.mark_dirty(simulation)

    assert sync_state.treat_as_dirty(simulation) is True
    equipment_state = sync_state.read_state(equipment)
    assert equipment_state is None or equipment_state.dirty is False
