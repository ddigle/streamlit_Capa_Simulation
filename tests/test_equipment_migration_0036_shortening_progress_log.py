# Purpose: 설비 DB 0036(누적 진척 기록 · 최종 목표 빈 표 둘)의 스키마 · 제약 · 0034 위 적용을 본다.

"""설비 DB 마이그레이션 `0036_shortening_progress_log`.

빈 설비 DB 와, 0034 까지 적용하고 옛 저장 셋을 넣은 DB 둘에 건다. 0036 은 아무것도 옮기지 않는다 —
표 둘을 만들 뿐이고 다른 표의 행은 그대로다. 0035 는 비어 있다(같은 때 다른 갈래 몫 — 카탈로그).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_migration_0029_floor_state import _apply_through, _table_counts

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 36
LOG_TABLE = "shortening_progress_log"
GOAL_TABLE = "shortening_progress_goal"


def _columns(path: Path, table: str) -> list[tuple[str, str, bool]]:
    with duckdb.connect(str(path), read_only=True) as connection:
        return [
            (str(name), str(kind), bool(nullable))
            for name, kind, nullable in connection.execute(
                """
                SELECT column_name, data_type, is_nullable = 'YES'
                FROM information_schema.columns
                WHERE table_schema = 'equipment_ops' AND table_name = ?
                ORDER BY ordinal_position
                """,
                [table],
            ).fetchall()
        ]


def test_a_new_database_gets_two_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    counts = _table_counts(path)
    assert (counts[LOG_TABLE], counts[GOAL_TABLE]) == (0, 0)
    assert _columns(path, LOG_TABLE) == [
        ("iso_year", "INTEGER", False),
        ("iso_week", "INTEGER", False),
        ("shortening_days", "INTEGER", False),
        ("recorded_by", "VARCHAR", True),
        ("updated_at", "TIMESTAMP", False),
    ]
    assert _columns(path, GOAL_TABLE) == [
        ("profile_id", "INTEGER", False),
        ("goal_days", "INTEGER", True),
        ("goal_year", "INTEGER", True),
        ("goal_week", "INTEGER", True),
        ("version", "INTEGER", False),
        ("saved_by", "VARCHAR", True),
        ("updated_at", "TIMESTAMP", False),
    ]


@pytest.mark.parametrize(
    "statement",
    [
        # 같은 (해, 주) 두 줄 — PK.
        "INSERT INTO equipment_ops.shortening_progress_log (iso_year, iso_week, shortening_days) "
        "VALUES (2026, 47, 96)",
        # 음수 일수.
        "INSERT INTO equipment_ops.shortening_progress_log (iso_year, iso_week, shortening_days) "
        "VALUES (2026, 48, -1)",
        # 54주차.
        "INSERT INTO equipment_ops.shortening_progress_log (iso_year, iso_week, shortening_days) "
        "VALUES (2026, 54, 1)",
        # 목표 일수만 있고 주차가 없음.
        "INSERT INTO equipment_ops.shortening_progress_goal (profile_id, goal_days, version) "
        "VALUES (1, 30, 1)",
        # 머리는 한 행.
        "INSERT INTO equipment_ops.shortening_progress_goal (profile_id, version) VALUES (2, 1)",
    ],
)
def test_the_tables_refuse_rows_outside_their_rules(tmp_path: Path, statement: str) -> None:
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.shortening_progress_log "
            "(iso_year, iso_week, shortening_days) VALUES (2026, 47, 100)"
        )
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(statement)


def test_a_database_before_0036_keeps_every_other_row_and_gets_two_empty_tables(
    tmp_path: Path,
) -> None:
    """0035 아래 번호를 모두 건 DB(0035 가 있으면 그것까지) 위에 0036 하나만 선다."""
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, MIGRATION_VERSION - 1)
    before = _table_counts(path)
    assert LOG_TABLE not in before and GOAL_TABLE not in before

    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION,)

    after = _table_counts(path)
    assert (after[LOG_TABLE], after[GOAL_TABLE]) == (0, 0)
    assert {
        table: count for table, count in after.items() if table not in (LOG_TABLE, GOAL_TABLE)
    } == before
    assert DuckDBEquipmentRepository(path).initialize() == ()
