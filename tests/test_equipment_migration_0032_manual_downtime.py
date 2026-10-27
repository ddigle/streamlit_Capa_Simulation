# Purpose: 설비 DB 0032(입력 비가동 빈 표 셋)의 스키마·제약과 0031 DB 위의 적용을 검증한다.

"""설비 DB 마이그레이션 `0032_manual_downtime`.

빈 설비 DB 와, 0031 까지 적용하고 옛 저장 셋을 넣은 DB 둘에 건다. 0032 는 아무것도 옮기지 않는다 —
세 표를 만들 뿐이고 다른 표의 행은 그대로다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_migration_0029_floor_state import _apply_through, _table_counts

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 32
NEW_TABLES = ("manual_downtime_profile", "manual_downtime", "manual_downtime_save")


def test_a_new_database_gets_three_empty_tables_with_their_constraints(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    counts = _table_counts(path)
    assert {table: counts[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    with duckdb.connect(str(path)) as connection:
        # 머리는 profile_id 1 한 행, version 은 1 부터다.
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.manual_downtime_profile (profile_id, version) "
                "VALUES (2, 1)"
            )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.manual_downtime_profile (profile_id, version) "
                "VALUES (1, 0)"
            )
        connection.execute(
            "INSERT INTO equipment_ops.manual_downtime (process_name, production_month, units) "
            "VALUES ('Final Test', 202607, 1.5)"
        )
        # 같은 (공정, 달) 두 행은 PK 가 막는다.
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.manual_downtime "
                "(process_name, production_month, units) VALUES ('Final Test', 202607, 2.0)"
            )
        # 음수 대수·빈 공정·13월은 DDL 이 막는다.
        for values in (
            ("'Final Test'", "202608", "-0.5"),
            ("''", "202608", "1"),
            ("'Final Test'", "202613", "1"),
        ):
            with pytest.raises(duckdb.ConstraintException):
                connection.execute(
                    "INSERT INTO equipment_ops.manual_downtime "
                    f"(process_name, production_month, units) VALUES ({', '.join(values)})"
                )
        keys = connection.execute(
            """
            SELECT constraint_column_names FROM duckdb_constraints()
            WHERE schema_name = 'equipment_ops' AND table_name = 'manual_downtime'
              AND constraint_type = 'PRIMARY KEY'
            """
        ).fetchall()
        assert keys == [(["process_name", "production_month"],)]
        # 이력 version 은 저장 한 번에 한 행이다.
        connection.execute(
            "INSERT INTO equipment_ops.manual_downtime_save "
            "(version, changed_cells, filled_cells, total_units) VALUES (1, 1, 1, 1.5)"
        )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.manual_downtime_save "
                "(version, changed_cells, filled_cells, total_units) VALUES (1, 0, 0, 0)"
            )


def test_a_database_at_0031_keeps_every_other_row_and_gets_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, 31)
    before = _table_counts(path)
    assert not set(NEW_TABLES) & set(before)

    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION,)

    after = _table_counts(path)
    assert {table: after[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    assert {table: count for table, count in after.items() if table not in NEW_TABLES} == before
    # 한 번도 저장하지 않은 프로필은 version 0 의 빈 값이다 — 계산은 전과 같다.
    profile = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (profile.version, profile.rows) == (0, ())
    assert DuckDBEquipmentRepository(path).initialize() == ()
