# Purpose: 설비 DB 0031(가정 배치 차이 표 셋·지문 칸)의 스키마·제약·옮김 없음·복사를 검증한다.

"""설비 DB 마이그레이션 `0031_scenario_layout_overlay`.

빈 설비 DB 와, 옛 저장 셋을 넣고 0029 까지 적용한 DB 둘에 건다. 0031 은 아무것도 옮기지 않는다 —
표 셋과 빈칸 허용 칸 하나를 만들 뿐이고, 기존 리비전은 지문이 NULL 이라 배치 차이 없음으로 읽혀
화면이 그대로다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from pandas.testing import assert_frame_equal
from test_equipment_migration_0027_scenarios import (
    LEGACY_REVISIONS,
    _apply_up_to,
    build_legacy_database,
)

from capa_simulation.persistence._sql_helpers import copy_database
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    _read_legacy_snapshot,
    read_merged,
)

MIGRATION_VERSION = 31
NEW_TABLES = (
    "equipment_schedule_layout_unit",
    "equipment_schedule_layout_mark",
    "equipment_schedule_layout_label",
)
# 뒤 번호(설비 0032 — 입력 비가동 대수)가 함께 만드는 빈 표.
LATER_TABLES = ("manual_downtime_profile", "manual_downtime", "manual_downtime_save")
_EXPECTED_KEYS = {
    "equipment_schedule_layout_unit": ("schedule_revision_id", "unit_key"),
    "equipment_schedule_layout_mark": (
        "schedule_revision_id",
        "building",
        "floor_name",
        "mark_id",
    ),
    "equipment_schedule_layout_label": (
        "schedule_revision_id",
        "building",
        "floor_name",
        "parent_equipment_id",
    ),
}


def _table_counts(path: Path) -> dict[str, int]:
    with duckdb.connect(str(path), read_only=True) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'equipment_ops' AND table_type = 'BASE TABLE'"
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        for table in tables:
            row = connection.execute(f'SELECT COUNT(*) FROM equipment_ops."{table}"').fetchone()
            assert row is not None
            counts[table] = int(row[0])
        return counts


def _columns(connection: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'equipment_ops' AND table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
    ]


def test_a_new_database_gets_three_empty_tables_with_primary_keys_and_no_foreign_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    counts = _table_counts(path)
    assert {table: counts[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    with duckdb.connect(str(path), read_only=True) as connection:
        for table, key in _EXPECTED_KEYS.items():
            constraints = connection.execute(
                """
                SELECT constraint_type, constraint_column_names FROM duckdb_constraints()
                WHERE schema_name = 'equipment_ops' AND table_name = ?
                  AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
                """,
                [table],
            ).fetchall()
            assert [(str(kind), tuple(columns)) for kind, columns in constraints] == [
                ("PRIMARY KEY", key)
            ], table
        assert _columns(connection, "equipment_schedule_layout_unit") == [
            "schedule_revision_id",
            "unit_key",
            "parent_equipment_id",
            "building",
            "floor_name",
            "x_coordinate",
            "y_coordinate",
            "x_size",
            "y_size",
            "layout_display_flag",
        ]
        assert _columns(connection, "equipment_schedule_revision")[-1] == "layout_hash"
        foreign = connection.execute(
            "SELECT COUNT(*) FROM duckdb_constraints() WHERE constraint_type = 'FOREIGN KEY' "
            "AND table_name LIKE 'equipment_schedule_layout%'"
        ).fetchone()
    assert foreign == (0,)


def test_the_tables_take_one_row_per_key(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_unit "
            "(schedule_revision_id, unit_key, layout_display_flag) VALUES ('r', 'k', 'Y')"
        )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.equipment_schedule_layout_unit "
                "(schedule_revision_id, unit_key, layout_display_flag) VALUES ('r', 'k', 'N')"
            )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.equipment_schedule_layout_unit "
                "(schedule_revision_id, unit_key, layout_display_flag) VALUES ('r', 'k2', NULL)"
            )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_mark (schedule_revision_id, "
            "building, floor_name, mark_id, change_kind, source_row_no) "
            "VALUES ('r', 'C1', '1F', 'MK-1', 'drop', 1)"
        )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                "INSERT INTO equipment_ops.equipment_schedule_layout_mark (schedule_revision_id, "
                "building, floor_name, mark_id, change_kind, source_row_no) "
                "VALUES ('r', 'C1', '1F', 'MK-2', 'drop', 0)"
            )
        # 이름표 위치 NULL 은 「공식 행을 지움」 이다 — 빈칸을 받는다.
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_label (schedule_revision_id, "
            "building, floor_name, parent_equipment_id, label_position) "
            "VALUES ('r', 'C1', '1F', 'APW1', NULL)"
        )


def test_a_database_at_0029_moves_nothing_and_reads_the_same(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_up_to(path, 29)
    before = _table_counts(path)
    assert not set(NEW_TABLES) & set(before)

    # 뒤 번호 0032(입력 비가동 빈 표 셋)도 함께 걸린다 — 이 번호의 표가 아니라 셈에서 뺀다.
    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION, 32)

    after = _table_counts(path)
    assert {table: after[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    assert {table: after[table] for table in LATER_TABLES} == dict.fromkeys(LATER_TABLES, 0)
    assert {
        table: count
        for table, count in after.items()
        if table not in NEW_TABLES and table not in LATER_TABLES
    } == before
    with duckdb.connect(str(path), read_only=True) as connection:
        hashes = connection.execute(
            "SELECT DISTINCT layout_hash FROM equipment_ops.equipment_schedule_revision"
        ).fetchall()
        assert hashes == [(None,)]
        for revision_id in LEGACY_REVISIONS:
            merged = read_merged(connection, revision_id, f"legacy-{revision_id}")
            legacy = _read_legacy_snapshot(connection, revision_id)
            assert_frame_equal(merged.equipment, legacy.equipment)
            assert (merged.layout_official_places, merged.layout_orphans) == ((), 0)
            assert merged.schedule is not None
            assert (merged.schedule.layout_hash, merged.schedule.layout_unit_count) == (None, 0)


def test_copy_database_carries_the_three_tables_row_for_row(tmp_path: Path) -> None:
    """`compact_duckdb`·스냅샷 내보내기가 쓰는 `copy_database` — FK 가 없어 차례에 더할 것이
    없다."""
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_unit (schedule_revision_id, "
            "unit_key, parent_equipment_id, building, floor_name, x_coordinate, y_coordinate, "
            "x_size, y_size, layout_display_flag) "
            "VALUES ('r', 'k', 'APW1', 'C1', '2F', 10, 20, 6, 7, 'Y')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_mark (schedule_revision_id, "
            "building, floor_name, mark_id, change_kind, source_row_no, mark_kind, x_coordinate, "
            "y_coordinate, x_size, y_size, rotation_deg, hatch, keep_out) "
            "VALUES ('r', 'C1', '2F', 'MK-1', 'set', 1, 'column', 1, 1, 2, 2, 0, FALSE, FALSE)"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_layout_label (schedule_revision_id, "
            "building, floor_name, parent_equipment_id, label_position) "
            "VALUES ('r', 'C1', '2F', 'APW1', 'top')"
        )
    target = tmp_path / "copied.duckdb"
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"ATTACH '{path}' AS source_db (READ_ONLY)")
        connection.execute(f"ATTACH '{target}' AS target_db")
        copy_database(connection, "source_db", "target_db")
        copied = {
            table: connection.execute(f'SELECT * FROM target_db.equipment_ops."{table}"').fetchall()
            for table in NEW_TABLES
        }
        source = {
            table: connection.execute(f'SELECT * FROM source_db.equipment_ops."{table}"').fetchall()
            for table in NEW_TABLES
        }
    assert copied == source
    assert all(len(rows) == 1 for rows in copied.values())
