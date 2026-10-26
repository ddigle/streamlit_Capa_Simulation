# Purpose: 설비 DB 층 사용 상태의 저장 왕복·바뀐 층만 쓰기·버전 대조·읽기 관용을 검증한다.

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def _row_times(path: Path) -> dict[tuple[str, str], object]:
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT building, floor_name, updated_at FROM equipment_ops.floor_state"
        ).fetchall()
    return {(str(row[0]), str(row[1])): row[2] for row in rows}


def test_saved_states_round_trip_and_raise_the_version(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    empty = repository.load_floor_states()
    assert (empty.rows, empty.version, empty.updated_at) == ((), 0, None)

    assert repository.save_floor_states(
        {("C5", "1F"): "NOT_LINE", ("C1", "3F"): "UNUSED"}, expected_version=0, source="t"
    )
    first = repository.load_floor_states()
    assert first.rows == (("C1", "3F", "UNUSED"), ("C5", "1F", "NOT_LINE"))
    assert (first.version, first.source) == (1, "t")
    assert first.updated_at is not None

    assert repository.save_floor_states({("C1", "3F"): "UNUSED"}, expected_version=1, source="t2")
    second = repository.load_floor_states()
    assert (second.rows, second.version, second.source) == ((("C1", "3F", "UNUSED"),), 2, "t2")


def test_the_same_content_writes_nothing_and_does_not_mark_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_states({("C1", "3F"): "UNUSED"}, expected_version=0, source="t")
    dirty: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", dirty.append)

    assert not repository.save_floor_states(
        {("C1", "3F"): "UNUSED", ("C2", "1F"): None}, expected_version=1, source="t"
    )
    assert repository.load_floor_states().version == 1
    assert dirty == []

    assert repository.save_floor_states({}, expected_version=1, source="t")
    assert dirty == [repository.database_path]


def test_one_save_mixing_on_reason_change_and_off_touches_only_those_floors(
    tmp_path: Path,
) -> None:
    """DuckDB 1.5.5 가 PK 표에서 한 트랜잭션의 DELETE·키 아닌 칸 UPDATE·INSERT 섞임을 받는지 —
    0029 가 PK 를 둔 근거다. 바뀌지 않은 층 행의 `updated_at` 은 그대로다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_floor_states(
        {("C1", "1F"): "UNUSED", ("C1", "2F"): "UNUSED", ("C2", "3F"): "NOT_LINE"},
        expected_version=0,
        source="t",
    )
    before = _row_times(path)
    time.sleep(0.01)

    assert repository.save_floor_states(
        {("C1", "2F"): "NOT_LINE", ("C2", "3F"): "NOT_LINE", ("C3", "4F"): "UNUSED"},
        expected_version=1,
        source="t",
    )

    states = repository.load_floor_states()
    assert states.rows == (
        ("C1", "2F", "NOT_LINE"),
        ("C2", "3F", "NOT_LINE"),
        ("C3", "4F", "UNUSED"),
    )
    after = _row_times(path)
    assert after[("C2", "3F")] == before[("C2", "3F")]
    assert after[("C1", "2F")] != before[("C1", "2F")]
    assert ("C1", "1F") not in after

    # 지운 층을 다음 저장에서 다시 끈다 — 다른 트랜잭션이라 같은 키 INSERT 가 된다.
    assert repository.save_floor_states(
        {("C1", "1F"): "UNUSED", ("C1", "2F"): "NOT_LINE"}, expected_version=2, source="t"
    )
    assert repository.load_floor_states().inactive == {
        ("C1", "1F"): "UNUSED",
        ("C1", "2F"): "NOT_LINE",
    }


def test_turning_every_floor_back_on_leaves_no_rows_and_raises_the_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_floor_states({("C1", "1F"): "UNUSED"}, expected_version=0, source="t")

    assert repository.save_floor_states({}, expected_version=1, source="t")

    states = repository.load_floor_states()
    assert (states.rows, states.version) == ((), 2)
    assert _row_times(path) == {}


def test_a_stale_version_is_refused_without_writing(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_states({("C1", "1F"): "UNUSED"}, expected_version=0, source="남")

    with pytest.raises(
        ProfileVersionConflict, match="층 사용 설정을 저장해.*편집 시작 v0 · 지금 v1"
    ):
        repository.save_floor_states({("C2", "1F"): "UNUSED"}, expected_version=0, source="나")
    # 내용이 같아도 version 이 다르면 충돌이다 — 대조가 먼저다.
    with pytest.raises(ProfileVersionConflict):
        repository.save_floor_states({("C1", "1F"): "UNUSED"}, expected_version=0, source="나")
    states = repository.load_floor_states()
    assert (states.rows, states.version, states.source) == ((("C1", "1F", "UNUSED"),), 1, "남")

    # None 은 대조하지 않는다(시험·스크립트).
    assert repository.save_floor_states({("C2", "1F"): "UNUSED"}, expected_version=None, source="s")
    assert repository.load_floor_states().version == 2


def test_invalid_values_are_refused_before_any_write(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    with pytest.raises(ValueError, match="FAB 의 층이 아닙니다"):
        repository.save_floor_states({("C9", "1F"): "UNUSED"}, expected_version=0, source="t")
    with pytest.raises(ValueError, match="사유는 20자까지입니다"):
        repository.save_floor_states({("C1", "1F"): "가" * 21}, expected_version=0, source="t")
    with pytest.raises(ValueError, match="제어 문자"):
        repository.save_floor_states({("C1", "1F"): "창\r\n고"}, expected_version=0, source="t")
    assert repository.load_floor_states().version == 0


def test_free_text_reasons_round_trip_as_written(tmp_path: Path) -> None:
    """직접 적은 사유(2026-10-26 결정)는 앞뒤 공백만 떼고 `reason` 칸에 그대로 — 마크다운 글자도
    그대로 읽힌다. 옛 코드의 글을 적으면 코드로, 같은 사유를 다시 적으면 쓰지 않는다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    written = "A~B~C *굵* [x](y)$1$"
    assert repository.save_floor_states(
        {("C1", "1F"): f"  {written} ", ("C2", "3F"): "생산라인 아님", ("C3", "4F"): "창고"},
        expected_version=0,
        source="t",
    )
    states = repository.load_floor_states()
    assert states.rows == (
        ("C1", "1F", written),
        ("C2", "3F", "NOT_LINE"),
        ("C3", "4F", "창고"),
    )
    assert (
        repository.save_floor_states(
            {("C1", "1F"): written, ("C2", "3F"): "NOT_LINE", ("C3", "4F"): " 창고 "},
            expected_version=1,
            source="t",
        )
        is None
    )
    # 사유만 바꾼 층은 그 행만 고친다.
    assert (
        repository.save_floor_states(
            {("C1", "1F"): written, ("C2", "3F"): "사무동 연결 통로", ("C3", "4F"): "창고"},
            expected_version=1,
            source="t",
        )
        == 2
    )
    assert repository.load_floor_states().inactive == {
        ("C1", "1F"): written,
        ("C2", "3F"): "사무동 연결 통로",
        ("C3", "4F"): "창고",
    }


def test_floor_states_do_not_touch_equipment_revisions_or_scenarios(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    saved = repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    assert saved is not None and saved.schedule is not None
    latest = repository.latest_revision_id()
    release = repository.latest_equipment_release()
    catalog = repository.load_scenario_catalog()

    repository.save_floor_states({("C1", "3F"): "UNUSED"}, expected_version=0, source="t")
    clone = repository.clone_equipment_scenario(
        saved.schedule.schedule_revision_id, name="가정 A", created_by=None
    )

    assert repository.latest_revision_id() == latest
    assert repository.latest_equipment_release() == release
    assert len(repository.load_scenario_catalog().scenarios) == len(catalog.scenarios) + 1
    assert clone.latest_revision_no == 1
    # 설비 시나리오가 둘이어도 층 사용 상태는 한 벌이다.
    assert repository.load_floor_states().inactive == {("C1", "3F"): "UNUSED"}


def test_reads_tolerate_hand_written_rows_and_the_key_blocks_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.floor_state (building, floor_name, reason) VALUES
                ('C9', '1F', 'UNUSED'), ('C2', '2F', 'FUTURE'), ('C1', '1F', 'UNUSED')
            """
        )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.floor_state (building, floor_name, reason) "
                "VALUES ('C1', '1F', 'NOT_LINE')"
            )

    states = repository.load_floor_states()
    # 머리 없이 층 행만 있다 — version 0 으로 읽고 30개 층 밖 행은 버린다. 모르는 사유는 그대로다.
    assert states.version == 0
    assert states.rows == (("C1", "1F", "UNUSED"), ("C2", "2F", "FUTURE"))

    # 화면은 늘 30개 층 전체 초안을 넘긴다 — 모르는 사유 층을 켜면 그 행이 지워지고 머리가 선다.
    assert repository.save_floor_states({("C1", "1F"): "UNUSED"}, expected_version=0, source="t")
    after = repository.load_floor_states()
    assert (after.rows, after.version) == ((("C1", "1F", "UNUSED"),), 1)
