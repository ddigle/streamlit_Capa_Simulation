# Purpose: 설비 DB 0034(Space 겹친 순서 빈 표)의 스키마와 0033 DB 위의 적용을 검증한다.

"""설비 DB 마이그레이션 `0034_floor_layout_stack`.

빈 설비 DB 와, 0033 까지 적용하고 옛 저장 셋을 넣은 DB 둘에 건다. 0034 는 아무것도 옮기지 않는다 —
표 하나를 만들 뿐이고 다른 표의 행은 그대로다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_migration_0029_floor_state import _apply_through, _table_counts

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 34
NEW_TABLE = "floor_layout_stack"


def _columns(path: Path) -> list[tuple[str, str, bool, str | None]]:
    with duckdb.connect(str(path), read_only=True) as connection:
        return [
            (str(name), str(kind), bool(nullable), None if default is None else str(default))
            for name, kind, nullable, default in connection.execute(
                """
                SELECT column_name, data_type, is_nullable = 'YES', column_default
                FROM information_schema.columns
                WHERE table_schema = 'equipment_ops' AND table_name = ?
                ORDER BY ordinal_position
                """,
                [NEW_TABLE],
            ).fetchall()
        ]


def test_a_new_database_gets_an_empty_stack_table(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    assert _table_counts(path)[NEW_TABLE] == 0
    columns = _columns(path)
    assert [(name, kind, nullable) for name, kind, nullable, _ in columns] == [
        ("building", "VARCHAR", False),
        ("floor_name", "VARCHAR", False),
        ("item_kind", "VARCHAR", False),
        ("item_ref", "VARCHAR", False),
        ("stack_no", "INTEGER", False),
        ("updated_at", "TIMESTAMP", False),
    ]
    assert columns[-1][3] is not None
    # 층 단위 전체 교체라 PK 가 없다 — 같은 키를 두 번 넣을 수 있다(유일은 서비스 검증 몫).
    with duckdb.connect(str(path)) as connection:
        keys = connection.execute(
            """
            SELECT count(*) FROM duckdb_constraints()
            WHERE schema_name = 'equipment_ops' AND table_name = ?
              AND constraint_type = 'PRIMARY KEY'
            """,
            [NEW_TABLE],
        ).fetchone()
        assert keys == (0,)
        for _ in range(2):
            connection.execute(
                "INSERT INTO equipment_ops.floor_layout_stack "
                "(building, floor_name, item_kind, item_ref, stack_no) "
                "VALUES ('C1', '1F', 'unit', 'u-1', 1)"
            )


def test_a_database_at_0033_keeps_every_other_row_and_gets_an_empty_table(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, 33)
    before = _table_counts(path)
    assert NEW_TABLE not in before

    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION, 35, 36, 37)

    after = _table_counts(path)
    assert after[NEW_TABLE] == 0
    # 뒤 번호 0036(누적 진척 빈 표 둘) · 0037(넣기 스냅숏 빈 표 셋)도 함께 걸린다 — 이 번호의 표가
    # 아니라 셈에서 뺀다.
    later = (
        "shortening_progress_log",
        "shortening_progress_goal",
        "shortening_progress_snapshot",
        "shortening_progress_snapshot_process",
        "shortening_progress_snapshot_unit",
    )
    assert {table: after[table] for table in later} == dict.fromkeys(later, 0)
    assert {
        table: count for table, count in after.items() if table != NEW_TABLE and table not in later
    } == before
    assert DuckDBEquipmentRepository(path).initialize() == ()
