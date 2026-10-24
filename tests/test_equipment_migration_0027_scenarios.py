# Purpose: 설비 DB 0027 이관(운영 일정·공식 v1·경계·FK 없는 새 표)과 그 위의 읽기 셋을 검증한다.

"""설비 DB 마이그레이션 `0027_equipment_scenarios`.

옛 코드가 남긴 DB(계약 v2·v3 리비전이 섞이고, Qual 자리표 2262-04-11 과 레거시 비가동 중복이
든 DB)를 **0025 까지만 적용한 뒤 옛 저장과 같은 행을 SQL 로 넣어** 만들고, 지금 코드의
`initialize()` 로 0027 을 건다. 0027 은 옛 스냅샷 행을 옮기거나 고치지 않는다 — 리비전마다
「운영 일정」 머리 한 행만 넣는다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence._sql_helpers import copy_database, transaction
from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

MIGRATION_VERSION = 27

NEW_TABLES = (
    "equipment_scenario",
    "equipment_schedule_revision",
    "equipment_schedule_snapshot",
    "equipment_schedule_downtime_snapshot",
    "equipment_official_release",
    "equipment_legacy_boundary",
)
# `equipment_ops.revision` 을 FK 로 가리키는 옛 자식 여섯. 0027 은 이 FK 를 건드리지 않는다.
REVISION_CHILDREN = (
    "baseline_snapshot",
    "schedule_snapshot",
    "equipment_snapshot",
    "downtime_snapshot",
    "equipment_master_snapshot",
    "downtime_schedule_snapshot",
)
LEGACY_REVISIONS = ("r1", "r2", "r3")


def _database_before(path: Path, version: int) -> None:
    """`version` 까지의 설비 마이그레이션만 적용한 DB 를 만든다(옛 코드가 열어 둔 DB)."""
    before = [
        migration for migration in load_equipment_migrations() if migration.version <= version
    ]
    with duckdb.connect(str(path)) as connection:
        for migration in before:
            connection.execute(migration.sql)
            connection.execute(
                "INSERT INTO equipment_meta.schema_migration (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [migration.version, migration.name, migration.checksum],
            )


_MASTER_COLUMNS = (
    "revision_id",
    "source_row_no",
    "equipment_id",
    "process_large",
    "process_small",
    "classification_2",
    "building",
    "floor_name",
    "x_coordinate",
    "y_coordinate",
    "x_size",
    "y_size",
    "vibration_table_date",
    "arrival_date",
    "qual_date",
    "qual_confirmation_status",
    "removal_date",
    "long_term_storage_flag",
    "existing_equipment_flag",
    "layout_display_flag",
    "conversion_ratio",
    "memo_1",
)


def _master_row(
    revision_id: str,
    row_no: int,
    name: str,
    *,
    arrival: str | None = "2026-08-01",
    qual: str | None = "2026-08-05",
    status: str | None = "확정",
    existing: str = "N",
    ratio: float | None = 1.0,
    position: tuple[str, str, float, float] | None = None,
    removal: str | None = None,
    memo: str | None = None,
) -> tuple[object, ...]:
    building, floor, x, y = position if position is not None else (None, None, None, None)
    sized = position is not None
    return (
        revision_id,
        row_no,
        name,
        "B/N",
        "Process-A",
        "HBM",
        building,
        floor,
        x,
        y,
        6.0 if sized else None,
        7.0 if sized else None,
        None,
        arrival,
        qual,
        status,
        removal,
        "N",
        existing,
        "Y" if sized else "N",
        ratio,
        memo,
    )


def _insert_revision(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    revision_no: int,
    *,
    contract: int,
    note: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO equipment_ops.revision (
            revision_id, revision_no, note, baseline_hash, schedule_hash,
            equipment_hash, downtime_hash, equipment_contract_version, created_at
        ) VALUES (?, ?, ?, 'b', 's', 'e', 'd', ?, CAST(? AS TIMESTAMP))
        """,
        [revision_id, revision_no, note, contract, created_at],
    )
    connection.execute(
        "INSERT INTO equipment_ops.baseline_snapshot VALUES (?, 1, 'Process-A', '전체', ?, NULL)",
        [revision_id, float(revision_no)],
    )


def build_legacy_database(path: Path) -> None:
    """0025 까지 적용하고 옛 저장 셋을 넣는다.

    - r1 — 계약 v2(`equipment_snapshot`·`downtime_snapshot`). 같은 (설비, 유형, 시작일) 비가동이
      둘이다(옛 표는 `downtime_id` 로만 가려 겹칠 수 있었다 — 읽을 때 뒤의 것을 남긴다).
    - r2 — 계약 v3. 「설비01」 의 Qual일정이 옛 변환의 자리표 2262-04-11, 환산비 NULL.
    - r3 — 계약 v3 최신. 기존설비 Y 호기·좌표 호기·비가동 하나.
    """
    _database_before(path, 25)
    with duckdb.connect(str(path)) as connection:
        _insert_revision(
            connection, "r1", 1, contract=2, note="옛 v2", created_at="2026-01-05 09:00:00"
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_snapshot (
                revision_id, source_row_no, equipment_id, process_name, classification,
                building, floor_name, x_coordinate, y_coordinate, width_value,
                arrival_date, production_transition_date, note
            ) VALUES
                ('r1', 1, 'EQ-V2A', 'Process-A', '전체', 'C1', '1F', 10, 10, 12,
                 DATE '2026-08-01', DATE '2026-08-10', '옛 비고'),
                ('r1', 2, 'EQ-V2B', 'Process-A', '전체', NULL, NULL, NULL, NULL, NULL,
                 DATE '2026-08-03', NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.downtime_snapshot (
                revision_id, source_row_no, downtime_id, equipment_id, downtime_type,
                start_date, end_date, detail
            ) VALUES
                ('r1', 1, 'D-1', 'EQ-V2A', '고장', DATE '2026-08-11', DATE '2026-08-12', '앞'),
                ('r1', 2, 'D-2', 'EQ-V2A', '고장', DATE '2026-08-11', DATE '2026-08-13', '뒤')
            """
        )
        _insert_revision(
            connection, "r2", 2, contract=3, note="자리표", created_at="2026-02-05 09:00:00"
        )
        _insert_revision(
            connection, "r3", 3, contract=3, note="최신", created_at="2026-03-05 09:00:00"
        )
        rows = [
            _master_row("r2", 1, "설비01", qual="2262-04-11", status="계획", ratio=None),
            _master_row("r2", 2, "EQ-02", position=("C1", "2F", 10.0, 20.0)),
            _master_row("r3", 1, "설비01", qual="2026-08-20", ratio=1.5, memo="공통 메모"),
            _master_row("r3", 2, "EQ-02", position=("C1", "2F", 10.0, 20.0)),
            _master_row("r3", 3, "EQ-OLD", arrival=None, qual=None, status=None, existing="Y"),
            _master_row("r3", 4, "EQ-OUT", removal="2026-12-01"),
        ]
        placeholders = ", ".join("?" for _ in _MASTER_COLUMNS)
        connection.executemany(
            f"INSERT INTO equipment_ops.equipment_master_snapshot ({', '.join(_MASTER_COLUMNS)}) "
            f"VALUES ({placeholders})",
            [list(row) for row in rows],
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.downtime_schedule_snapshot (
                revision_id, source_row_no, equipment_id, downtime_type, start_date, end_date
            ) VALUES
                ('r2', 1, 'EQ-02', '공사', DATE '2026-09-01', DATE '2026-09-03'),
                ('r3', 1, '설비01', '고장', DATE '2026-09-10', NULL),
                ('r3', 2, 'EQ-02', '공사', DATE '2026-09-01', DATE '2026-09-03')
            """
        )


def _legacy_rows(path: Path) -> dict[str, list[tuple[object, ...]]]:
    """옛 표의 행 전부(0027 이 더한 칸은 뺀다) — 이관 전후가 같아야 한다."""
    queries = {
        "revision": "SELECT revision_id, revision_no, note, baseline_hash, schedule_hash, "
        "equipment_hash, downtime_hash, equipment_contract_version, created_at "
        "FROM equipment_ops.revision ORDER BY revision_no",
        "master": f"SELECT {', '.join(_MASTER_COLUMNS)} "
        "FROM equipment_ops.equipment_master_snapshot ORDER BY revision_id, source_row_no",
        "v3_downtime": "SELECT * FROM equipment_ops.downtime_schedule_snapshot "
        "ORDER BY revision_id, source_row_no",
        "v2_equipment": "SELECT * FROM equipment_ops.equipment_snapshot "
        "ORDER BY revision_id, source_row_no",
        "v2_downtime": "SELECT * FROM equipment_ops.downtime_snapshot "
        "ORDER BY revision_id, source_row_no",
        "baseline": "SELECT * FROM equipment_ops.baseline_snapshot "
        "ORDER BY revision_id, source_row_no",
    }
    with duckdb.connect(str(path), read_only=True) as connection:
        return {name: connection.execute(sql).fetchall() for name, sql in queries.items()}


@pytest.fixture
def migrated(tmp_path: Path) -> tuple[Path, dict[str, list[tuple[object, ...]]]]:
    """옛 DB 에 0027 을 건 경로와, 걸기 전 옛 표의 행."""
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    before = _legacy_rows(path)
    assert DuckDBEquipmentRepository(path).initialize() == (MIGRATION_VERSION,)
    return path, before


def test_every_revision_becomes_an_operations_revision_with_the_same_number_time_and_note(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    path, _ = migrated
    with duckdb.connect(str(path), read_only=True) as connection:
        scenarios = connection.execute(
            "SELECT equipment_scenario_id, scenario_name, status, list_order, "
            "source_schedule_revision_id FROM equipment_ops.equipment_scenario"
        ).fetchall()
        revisions = connection.execute(
            "SELECT revision_id, revision_no, note, created_at FROM equipment_ops.revision "
            "ORDER BY revision_no"
        ).fetchall()
        schedule = connection.execute(
            """
            SELECT schedule_revision_id, equipment_scenario_id, revision_no, note, created_at,
                   origin, common_revision_id, legacy_revision_id, revision_name, saved_by
            FROM equipment_ops.equipment_schedule_revision ORDER BY revision_no
            """
        ).fetchall()

    assert scenarios == [("operations", "운영 일정", "ACTIVE", 0, None)]
    assert len(schedule) == len(revisions) == len(LEGACY_REVISIONS)
    for (revision_id, number, note, created_at), row in zip(revisions, schedule, strict=True):
        assert row == (
            f"legacy-{revision_id}",
            "operations",
            number,
            note,
            created_at,
            "legacy",
            revision_id,
            revision_id,
            None,
            None,
        )


def test_the_latest_revision_is_official_v1_and_the_boundary_is_its_number(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    path, _ = migrated
    with duckdb.connect(str(path), read_only=True) as connection:
        releases = connection.execute(
            "SELECT release_id, release_no, equipment_scenario_id, schedule_revision_id, "
            "released_by, note FROM equipment_ops.equipment_official_release"
        ).fetchall()
        boundary = connection.execute(
            "SELECT boundary_no, through_revision_no, note "
            "FROM equipment_ops.equipment_legacy_boundary"
        ).fetchall()

    assert releases == [("release-1", 1, "operations", "legacy-r3", None, "이관 시점 최신 리비전")]
    assert boundary == [(1, 3, "0027 이관")]


def test_old_snapshot_rows_are_not_moved_or_changed(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    """가리키기 이관이다 — 옛 표의 행·칸은 그대로이고 새 칸(저장자·호기 키)은 모두 NULL 이다."""
    path, before = migrated

    assert _legacy_rows(path) == before
    with duckdb.connect(str(path), read_only=True) as connection:
        added = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM equipment_ops.revision WHERE saved_by IS NOT NULL),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot
                    WHERE unit_key IS NOT NULL),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_snapshot),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_downtime_snapshot)
            """
        ).fetchone()
        baseline_columns = {
            str(row[0])
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'equipment_ops' AND table_name = 'shortening_baseline'"
            ).fetchall()
        }

    assert added == (0, 0, 0, 0)
    assert {
        "equipment_schedule_revision_ref",
        "equipment_schedule_revision_no",
        "equipment_scenario_name",
        "equipment_release_no",
    } <= baseline_columns


def test_legacy_reads_still_apply_their_conversions_after_the_migration(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    """Qual 자리표 → 빈칸, 환산비 NULL → 1, 계약 v2 변환, 레거시 비가동 중복은 뒤의 것."""
    path, _ = migrated
    repository = DuckDBEquipmentRepository(path)

    r1 = repository.load_snapshot("r1")
    r2 = repository.load_snapshot("r2").equipment.set_index("설비명")

    assert r1.equipment["설비명"].tolist() == ["EQ-V2A", "EQ-V2B"]
    assert r1.downtime["상세사유"].tolist() == ["뒤"]
    assert r2["Qual일정"].isna().tolist() == [True, False]
    assert r2.loc["설비01", "환산비"] == 1.0
    assert r2["시나리오 메모"].isna().all()


def test_an_empty_database_gets_the_operations_scenario_without_revisions(tmp_path: Path) -> None:
    path = tmp_path / "empty.duckdb"
    DuckDBEquipmentRepository(path).initialize()

    with duckdb.connect(str(path), read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM equipment_ops.equipment_scenario),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_revision),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_official_release)
            """
        ).fetchone()
        boundary = connection.execute(
            "SELECT boundary_no, through_revision_no FROM equipment_ops.equipment_legacy_boundary"
        ).fetchall()

    assert counts == (1, 0, 0)
    assert boundary == [(1, 0)]


_EXPECTED_COLUMNS = {
    "equipment_scenario": [
        "equipment_scenario_id",
        "scenario_name",
        "status",
        "list_order",
        "source_schedule_revision_id",
        "created_by",
        "created_at",
        "updated_at",
    ],
    "equipment_schedule_revision": [
        "schedule_revision_id",
        "equipment_scenario_id",
        "revision_no",
        "revision_name",
        "note",
        "saved_by",
        "origin",
        "common_revision_id",
        "legacy_revision_id",
        "schedule_hash",
        "downtime_hash",
        "created_at",
    ],
    "equipment_schedule_snapshot": [
        "schedule_revision_id",
        "unit_key",
        "vibration_table_date",
        "logistics_date",
        "arrival_date",
        "qual_date",
        "removal_date",
        "relocation_date",
        "scenario_memo",
    ],
    "equipment_schedule_downtime_snapshot": [
        "schedule_revision_id",
        "source_row_no",
        "unit_key",
        "downtime_type",
        "start_date",
        "end_date",
        "detail",
        "note",
    ],
    "equipment_official_release": [
        "release_id",
        "release_no",
        "equipment_scenario_id",
        "schedule_revision_id",
        "released_by",
        "note",
        "released_at",
    ],
    "equipment_legacy_boundary": [
        "boundary_no",
        "through_revision_no",
        "note",
        "recorded_at",
    ],
}

_EXPECTED_KEYS = {
    "equipment_scenario": {("PRIMARY KEY", ("equipment_scenario_id",))},
    "equipment_schedule_revision": {
        ("PRIMARY KEY", ("schedule_revision_id",)),
        ("UNIQUE", ("equipment_scenario_id", "revision_no")),
    },
    "equipment_schedule_snapshot": {("PRIMARY KEY", ("schedule_revision_id", "unit_key"))},
    "equipment_schedule_downtime_snapshot": {
        ("PRIMARY KEY", ("schedule_revision_id", "source_row_no")),
        ("UNIQUE", ("schedule_revision_id", "unit_key", "downtime_type", "start_date")),
    },
    "equipment_official_release": {
        ("PRIMARY KEY", ("release_id",)),
        ("UNIQUE", ("release_no",)),
    },
    "equipment_legacy_boundary": {("PRIMARY KEY", ("boundary_no",))},
}


def _constraints(
    connection: duckdb.DuckDBPyConnection, table: str
) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (str(kind), tuple(str(column) for column in columns))
        for kind, columns in connection.execute(
            """
            SELECT constraint_type, constraint_column_names FROM duckdb_constraints()
            WHERE schema_name = 'equipment_ops' AND table_name = ?
              AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
            """,
            [table],
        ).fetchall()
    ]


def test_new_tables_have_their_columns_and_keys_and_no_foreign_key(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    """새 여섯 표에 FK 가 없다 — 한 트랜잭션 삭제와 UNIQUE 칸 UPDATE 를 DuckDB 1.5.5 가 막지 않게.
    옛 자식 여섯의 `revision` FK 는 그대로다."""
    path, _ = migrated
    with duckdb.connect(str(path), read_only=True) as connection:
        for table, columns in _EXPECTED_COLUMNS.items():
            found = [
                str(row[0])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'equipment_ops' AND table_name = ? "
                    "ORDER BY ordinal_position",
                    [table],
                ).fetchall()
            ]
            assert found == columns, table
            assert set(_constraints(connection, table)) == _EXPECTED_KEYS[table], table
        for child in REVISION_CHILDREN:
            foreign = [kind for kind, _ in _constraints(connection, child) if kind == "FOREIGN KEY"]
            assert foreign == ["FOREIGN KEY"], child
        all_foreign = connection.execute(
            "SELECT COUNT(*) FROM duckdb_constraints() WHERE constraint_type = 'FOREIGN KEY'"
        ).fetchone()

    assert all_foreign == (len(REVISION_CHILDREN),)


def _fill_new_tables(path: Path) -> None:
    """복제·발행이 남길 꼴의 행을 새 표마다 넣는다(복사·삭제 시험용)."""
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.equipment_scenario "
            "(equipment_scenario_id, scenario_name, list_order, source_schedule_revision_id) "
            "VALUES ('setup', '셋업 실무', 1, 'legacy-r3')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_revision "
            "(schedule_revision_id, equipment_scenario_id, revision_no, origin, "
            "common_revision_id) VALUES ('setup-1', 'setup', 1, 'clone', 'r3')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_snapshot "
            "(schedule_revision_id, unit_key, arrival_date, scenario_memo) "
            "VALUES ('setup-1', 'k1', DATE '2026-08-01', '메모')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_downtime_snapshot "
            "(schedule_revision_id, source_row_no, unit_key, downtime_type, start_date) "
            "VALUES ('setup-1', 1, 'k1', '공사', DATE '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_official_release "
            "(release_id, release_no, equipment_scenario_id, schedule_revision_id) "
            "VALUES ('release-2', 2, 'setup', 'setup-1')"
        )
        connection.execute(
            "INSERT INTO equipment_ops.equipment_legacy_boundary "
            "(boundary_no, through_revision_no) VALUES (2, 3)"
        )


def _row_counts(connection: duckdb.DuckDBPyConnection, catalog: str) -> dict[str, int]:
    tables = connection.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = ? ORDER BY 1, 2",
        [catalog],
    ).fetchall()
    counts: dict[str, int] = {}
    for schema, table in tables:
        row = connection.execute(
            f'SELECT COUNT(*) FROM "{catalog}"."{schema}"."{table}"'
        ).fetchone()
        counts[f"{schema}.{table}"] = int(row[0]) if row is not None else -1
    return counts


def test_copy_database_carries_the_new_tables_row_for_row(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]], tmp_path: Path
) -> None:
    """`compact_duckdb`·스냅샷 내보내기가 쓰는 `copy_database` — 새 표에 FK 가 없어 차례에 더할 것이
    없고, 표마다 행 수가 같다."""
    path, _ = migrated
    _fill_new_tables(path)
    target = tmp_path / "copied.duckdb"
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"ATTACH '{path}' AS source_db (READ_ONLY)")
        connection.execute(f"ATTACH '{target}' AS target_db")
        copy_database(connection, "source_db", "target_db")
        source = _row_counts(connection, "source_db")
        copied = _row_counts(connection, "target_db")

    assert copied == source
    assert all(source[f"equipment_ops.{table}"] > 0 for table in NEW_TABLES)


def test_a_scenario_is_deleted_children_first_and_renamed_in_one_transaction(
    migrated: tuple[Path, dict[str, list[tuple[object, ...]]]],
) -> None:
    """2단계 영구 삭제·이름 바꾸기가 기댈 두 가지 — FK 가 있으면 DuckDB 1.5.5 가 둘 다 막는다."""
    path, _ = migrated
    _fill_new_tables(path)
    with duckdb.connect(str(path)) as connection:
        with transaction(connection):
            connection.execute(
                "UPDATE equipment_ops.equipment_scenario "
                "SET scenario_name = '운영 일정(이름 바꿈)' "
                "WHERE equipment_scenario_id = 'operations'"
            )
            connection.execute(
                "UPDATE equipment_ops.equipment_schedule_revision SET revision_name = '이름' "
                "WHERE schedule_revision_id = 'legacy-r3'"
            )
        with transaction(connection):
            for table in (
                "equipment_schedule_downtime_snapshot",
                "equipment_schedule_snapshot",
            ):
                connection.execute(
                    f"DELETE FROM equipment_ops.{table} WHERE schedule_revision_id = 'setup-1'"
                )
            for table in ("equipment_schedule_revision", "equipment_official_release"):
                connection.execute(
                    f"DELETE FROM equipment_ops.{table} WHERE equipment_scenario_id = 'setup'"
                )
            connection.execute(
                "DELETE FROM equipment_ops.equipment_scenario WHERE equipment_scenario_id = 'setup'"
            )
        names = connection.execute(
            "SELECT scenario_name FROM equipment_ops.equipment_scenario"
        ).fetchall()
        left = connection.execute(
            "SELECT COUNT(*) FROM equipment_ops.equipment_schedule_revision "
            "WHERE equipment_scenario_id = 'setup'"
        ).fetchone()

    assert names == [("운영 일정(이름 바꿈)",)]
    assert left == (0,)
