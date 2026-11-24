# Purpose: 설비 DB 0037(누적 진척 넣기 스냅숏 빈 표 셋)의 스키마 · 제약 · 0036 위 적용을 본다.

"""설비 DB 마이그레이션 `0037_shortening_progress_snapshot`.

빈 설비 DB 와, 0036 까지 적용하고 옛 저장 셋을 넣은 DB 둘에 건다. 0037 은 아무것도 옮기지 않는다 —
표 셋(머리 · 범위 공정 · 호기)을 만들 뿐이고 다른 표의 행은 그대로다. 바로 앞 번호는 설비 0036(누적
진척 기록 · 최종 목표)이다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_migration_0029_floor_state import _apply_through, _table_counts
from test_equipment_migration_0036_shortening_progress_log import _columns

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 37
HEADER = "shortening_progress_snapshot"
PROCESS = "shortening_progress_snapshot_process"
UNIT = "shortening_progress_snapshot_unit"
NEW_TABLES = (HEADER, PROCESS, UNIT)

_HEADER_INSERT = (
    "INSERT INTO equipment_ops.shortening_progress_snapshot (iso_year, iso_week, snapshot_id, "
    "log_updated_at, snapshot_days, target_level, schedule_basis, scope_selected, plan_today, "
    "start_month, end_month, content_digest) VALUES "
)


def test_a_new_database_gets_three_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    counts = _table_counts(path)
    assert {table: counts[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    header = _columns(path, HEADER)
    assert header[:14] == [
        ("iso_year", "INTEGER", False),
        ("iso_week", "INTEGER", False),
        ("snapshot_id", "VARCHAR", False),
        ("log_updated_at", "TIMESTAMP", False),
        ("captured_at", "TIMESTAMP", False),
        ("captured_by", "VARCHAR", True),
        ("snapshot_days", "INTEGER", False),
        ("target_level", "INTEGER", False),
        ("schedule_basis", "VARCHAR", False),
        ("scope_selected", "BOOLEAN", False),
        ("plan_today", "DATE", False),
        ("start_month", "INTEGER", False),
        ("end_month", "INTEGER", False),
        ("content_digest", "VARCHAR", False),
    ]
    # 출처 칸은 기준선 머리(0021 · 0027)와 같은 이름이고 모두 비울 수 있다.
    assert [(name, nullable) for name, _, nullable in header[14:]] == [
        ("equipment_revision_id", True),
        ("equipment_revision_no", True),
        ("reference_version", True),
        ("scenario_id", True),
        ("scenario_name", True),
        ("scenario_revision_id", True),
        ("scenario_revision_no", True),
        ("scenario_content_token", True),
        ("equipment_schedule_revision_ref", True),
        ("equipment_schedule_revision_no", True),
        ("equipment_scenario_name", True),
        ("equipment_release_no", True),
    ]
    assert _columns(path, PROCESS) == [
        ("snapshot_id", "VARCHAR", False),
        ("process_name", "VARCHAR", False),
        ("sort_order", "INTEGER", False),
        ("cutoff_days", "INTEGER", True),
    ]
    assert _columns(path, UNIT) == [
        ("snapshot_id", "VARCHAR", False),
        ("sort_order", "INTEGER", False),
        ("process_name", "VARCHAR", False),
        ("unit_name", "VARCHAR", False),
        ("unit_kind", "VARCHAR", False),
        ("module_count", "INTEGER", False),
        ("original_qual", "DATE", True),
        ("target_qual", "DATE", False),
        ("shortening_days", "INTEGER", True),
    ]


@pytest.mark.parametrize(
    "statement",
    [
        # 같은 (해, 주) 두 머리 — PK.
        _HEADER_INSERT + "(2026, 47, 'b', TIMESTAMP '2026-11-20 09:00:00', 10, 100, 'Static', "
        "false, DATE '2026-11-20', 202701, 202703, 'd')",
        # 음수 일수.
        _HEADER_INSERT + "(2026, 48, 'c', TIMESTAMP '2026-11-20 09:00:00', -1, 100, 'Static', "
        "false, DATE '2026-11-20', 202701, 202703, 'd')",
        # 끝 달이 시작 달보다 앞.
        _HEADER_INSERT + "(2026, 48, 'c', TIMESTAMP '2026-11-20 09:00:00', 1, 100, 'Static', "
        "false, DATE '2026-11-20', 202703, 202701, 'd')",
        # 같은 스냅숏의 같은 공정 두 줄 — PK.
        "INSERT INTO equipment_ops.shortening_progress_snapshot_process "
        "(snapshot_id, process_name, sort_order) VALUES ('a', 'PRC-01', 1)",
        # 구분은 「단축」 · 「신규」 둘.
        "INSERT INTO equipment_ops.shortening_progress_snapshot_unit (snapshot_id, sort_order, "
        "process_name, unit_name, unit_kind, module_count, target_qual) "
        "VALUES ('a', 1, 'PRC-01', 'EQ-02', '기존', 1, DATE '2027-03-01')",
        # 필요 시점(목표 Qual)은 빌 수 없다.
        "INSERT INTO equipment_ops.shortening_progress_snapshot_unit (snapshot_id, sort_order, "
        "process_name, unit_name, unit_kind, module_count) "
        "VALUES ('a', 1, 'PRC-01', 'EQ-02', '단축', 1)",
    ],
)
def test_the_tables_refuse_rows_outside_their_rules(tmp_path: Path, statement: str) -> None:
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            _HEADER_INSERT + "(2026, 47, 'a', TIMESTAMP '2026-11-20 09:00:00', 10, 100, "
            "'Static', false, DATE '2026-11-20', 202701, 202703, 'd')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.shortening_progress_snapshot_process "
            "(snapshot_id, process_name, sort_order) VALUES ('a', 'PRC-01', 0)"
        )
        with pytest.raises((duckdb.ConstraintException, duckdb.ConversionException)):
            connection.execute(statement)


def test_a_database_before_0037_keeps_every_other_row_and_gets_three_empty_tables(
    tmp_path: Path,
) -> None:
    """0036 까지 모두 건 DB 위에 0037 하나만 선다."""
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, MIGRATION_VERSION - 1)
    before = _table_counts(path)
    assert not set(NEW_TABLES) & set(before)

    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION,)

    after = _table_counts(path)
    assert {table: after[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 0)
    assert {table: count for table, count in after.items() if table not in NEW_TABLES} == before
    assert DuckDBEquipmentRepository(path).initialize() == ()
