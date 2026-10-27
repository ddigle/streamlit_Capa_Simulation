# Purpose: 입력 비가동 대수의 저장 왕복·범위 쓰기·버전 거부·이력·캐시 비우기를 검증한다.

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence import equipment_cache, sync_state
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

A, B = "Wafer Mount", "Final Test"
MONTHS = (202607, 202608)


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_cells_round_trip_with_saver_note_and_history(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    empty = repository.load_manual_downtime()
    assert (empty.rows, empty.version, empty.updated_at) == ((), 0, None)
    assert repository.load_manual_downtime_saves() == ()

    version = repository.save_manual_downtime(
        {(A, 202607): 1.5, (A, 202608): None, (B, 202607): "0.25", (B, 202608): 0},
        processes=(A, B),
        months=MONTHS,
        expected_version=0,
        saved_by=" 홍길동 ",
        note="26.07 PM",
    )
    assert version == 1
    first = repository.load_manual_downtime()
    # 공정 이름 차례(Final Test < Wafer Mount)다.
    assert first.rows == ((B, 202607, 0.25), (A, 202607, 1.5))
    assert (first.version, first.saved_by, first.note) == (1, "홍길동", "26.07 PM")
    assert first.updated_at is not None

    assert (
        repository.save_manual_downtime(
            {(A, 202607): 2.0, (A, 202608): 1.0, (B, 202607): None, (B, 202608): None},
            processes=(A, B),
            months=MONTHS,
            expected_version=1,
        )
        == 2
    )
    second = repository.load_manual_downtime()
    assert second.rows == ((A, 202607, 2.0), (A, 202608, 1.0))
    assert (second.version, second.saved_by, second.note) == (2, "", "")

    saves = repository.load_manual_downtime_saves()
    assert [(save.version, save.changed_cells, save.filled_cells) for save in saves] == [
        (2, 3, 2),
        (1, 2, 2),
    ]
    assert [save.total_units for save in saves] == [3.0, 1.75]
    assert (saves[1].saved_by, saves[1].note) == ("홍길동", "26.07 PM")


def test_cells_outside_the_visible_range_are_kept(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_manual_downtime(
        {(A, 202606): 3.0, (B, 202607): 1.0},
        processes=(A, B),
        months=(202606, 202607),
        expected_version=0,
    )
    # 다음 화면은 202607·202608 만, 공정은 A 만 보였다 — 202606 과 B 는 그대로 남는다.
    repository.save_manual_downtime(
        {(A, 202607): 0.5, (A, 202608): None},
        processes=(A,),
        months=MONTHS,
        expected_version=1,
    )
    assert repository.load_manual_downtime().rows == (
        (B, 202607, 1.0),
        (A, 202606, 3.0),
        (A, 202607, 0.5),
    )


def test_a_stale_version_is_refused_without_writing(tmp_path: Path) -> None:
    """두 세션이 v0 에서 편집을 시작했다 — 먼저 저장한 쪽이 이기고 늦은 쪽은 거부된다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_manual_downtime(
        {(A, 202607): 1.0}, processes=(A,), months=MONTHS, expected_version=0
    )

    with pytest.raises(ProfileVersionConflict) as caught:
        repository.save_manual_downtime(
            {(A, 202607): 9.0}, processes=(A,), months=MONTHS, expected_version=0
        )
    assert (caught.value.expected, caught.value.stored) == (0, 1)
    assert "입력 비가동 대수" in str(caught.value)
    profile = repository.load_manual_downtime()
    assert (profile.rows, profile.version) == (((A, 202607, 1.0),), 1)
    assert len(repository.load_manual_downtime_saves()) == 1


def test_the_same_content_writes_nothing_and_does_not_mark_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_manual_downtime(
        {(A, 202607): 1.0}, processes=(A,), months=MONTHS, expected_version=0
    )
    dirty: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", dirty.append)

    assert (
        repository.save_manual_downtime(
            {(A, 202607): "1.0", (A, 202608): None},
            processes=(A,),
            months=MONTHS,
            expected_version=1,
        )
        is None
    )
    assert repository.load_manual_downtime().version == 1
    assert dirty == []


def test_a_bad_cell_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    with pytest.raises(ValueError, match="0 이상"):
        repository.save_manual_downtime(
            {(A, 202607): 1.0, (B, 202607): -1.0},
            processes=(A, B),
            months=MONTHS,
            expected_version=0,
        )
    assert repository.load_manual_downtime().version == 0


def test_only_changed_cells_are_touched(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_manual_downtime(
        {(A, 202607): 1.0, (B, 202607): 2.0}, processes=(A, B), months=MONTHS, expected_version=0
    )
    with duckdb.connect(str(path), read_only=True) as connection:
        before = dict(
            connection.execute(
                "SELECT process_name, updated_at FROM equipment_ops.manual_downtime"
            ).fetchall()
        )
    repository.save_manual_downtime(
        {(A, 202607): 1.5, (B, 202607): 2.0}, processes=(A, B), months=MONTHS, expected_version=1
    )
    with duckdb.connect(str(path), read_only=True) as connection:
        after = dict(
            connection.execute(
                "SELECT process_name, updated_at FROM equipment_ops.manual_downtime"
            ).fetchall()
        )
    assert after[B] == before[B]


def test_the_cached_profile_is_refreshed_by_clearing(tmp_path: Path) -> None:
    """앱의 저장은 `clear_manual_downtime_cache` 로 비우고 세대를 올린다 — 다음 읽기가 새 값이다."""
    path = tmp_path / "equipment.duckdb"
    database = str(path)
    equipment_cache.clear_equipment_repository()
    try:
        assert equipment_cache.load_manual_downtime(database).version == 0
        equipment_cache.get_equipment_repository(database).save_manual_downtime(
            {(A, 202607): 1.0}, processes=(A,), months=MONTHS, expected_version=0
        )
        equipment_cache.clear_manual_downtime_cache()
        profile = equipment_cache.load_manual_downtime(database)
        assert (profile.version, profile.rows) == (1, ((A, 202607, 1.0),))
        assert [save.version for save in equipment_cache.load_manual_downtime_saves(database)] == [
            1
        ]
    finally:
        equipment_cache.clear_equipment_repository()
