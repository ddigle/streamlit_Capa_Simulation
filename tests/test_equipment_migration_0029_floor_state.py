# Purpose: 설비 DB 0029(층 사용 상태 빈 표 둘)의 스키마·제약과 0027 DB 위의 적용을 검증한다.

"""설비 DB 마이그레이션 `0029_floor_state`.

빈 설비 DB 와, 0027(설비 시나리오)까지 적용하고 옛 저장 셋을 넣은 DB 둘에 건다. 0029 는 아무것도
옮기지 않는다 — 두 표를 만들 뿐이고 다른 표의 행은 그대로다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from test_equipment_migration_0027_scenarios import build_legacy_database

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 29
NEW_TABLES = ("floor_state_profile", "floor_state")
# 0029 뒤 번호가 만드는 빈 표(설비 0031 — 가정 배치 차이). 지금 코드의 `initialize()` 가 함께 건다.
LATER_TABLES = (
    "equipment_schedule_layout_unit",
    "equipment_schedule_layout_mark",
    "equipment_schedule_layout_label",
)


def _apply_through(path: Path, version: int) -> None:
    """이미 적용된 번호 다음부터 `version` 까지의 설비 마이그레이션을 SQL 그대로 건다(옛 코드)."""
    with duckdb.connect(str(path)) as connection:
        applied = {
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM equipment_meta.schema_migration"
            ).fetchall()
        }
        for migration in load_equipment_migrations():
            if migration.version in applied or migration.version > version:
                continue
            connection.execute(migration.sql)
            connection.execute(
                "INSERT INTO equipment_meta.schema_migration (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [migration.version, migration.name, migration.checksum],
            )


def _table_counts(path: Path) -> dict[str, int]:
    with duckdb.connect(str(path), read_only=True) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'equipment_ops' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        for table in tables:
            row = connection.execute(f'SELECT COUNT(*) FROM equipment_ops."{table}"').fetchone()
            assert row is not None
            counts[table] = int(row[0])
        return counts


def test_a_new_database_gets_two_empty_tables_with_their_constraints(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    counts = _table_counts(path)
    assert {table: counts[table] for table in NEW_TABLES} == {
        "floor_state_profile": 0,
        "floor_state": 0,
    }
    with duckdb.connect(str(path)) as connection:
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.floor_state_profile (profile_id, version, source) "
                "VALUES (2, 1, 't')"
            )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.floor_state_profile (profile_id, version, source) "
                "VALUES (1, 0, 't')"
            )
        connection.execute(
            "INSERT INTO equipment_ops.floor_state (building, floor_name, reason) "
            "VALUES ('C1', '3F', 'UNUSED')"
        )
        # 같은 층 두 행은 PK (동, 층)가 막는다.
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.floor_state (building, floor_name, reason) "
                "VALUES ('C1', '3F', 'NOT_LINE')"
            )
        keys = connection.execute(
            """
            SELECT constraint_column_names FROM duckdb_constraints()
            WHERE schema_name = 'equipment_ops' AND table_name = 'floor_state'
              AND constraint_type = 'PRIMARY KEY'
            """
        ).fetchall()
    assert keys == [(["building", "floor_name"],)]


def test_a_database_at_0027_keeps_every_other_row_and_gets_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, 27)
    before = _table_counts(path)
    assert not set(NEW_TABLES) & set(before)
    assert before["equipment_scenario"] == 1 and before["revision"] == 3

    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION, 31)

    after = _table_counts(path)
    assert {table: after[table] for table in NEW_TABLES} == {
        "floor_state_profile": 0,
        "floor_state": 0,
    }
    assert {table: after[table] for table in LATER_TABLES} == dict.fromkeys(LATER_TABLES, 0)
    assert {
        table: count
        for table, count in after.items()
        if table not in NEW_TABLES and table not in LATER_TABLES
    } == before
    repository = DuckDBEquipmentRepository(path)
    states = repository.load_floor_states()
    assert (states.rows, states.version) == ((), 0)


def test_running_the_sql_twice_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    (migration,) = [m for m in load_equipment_migrations() if m.version == MIGRATION_VERSION]
    with duckdb.connect(str(path)) as connection:
        connection.execute(migration.sql)
    assert DuckDBEquipmentRepository(path).initialize() == ()
    counts = _table_counts(path)
    assert (counts["floor_state_profile"], counts["floor_state"]) == (0, 0)
