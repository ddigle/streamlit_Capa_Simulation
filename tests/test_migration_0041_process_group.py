# Purpose: 0041 이 공용 공정 그룹 두 표를 칸 · CHECK · 열쇠대로 만들고 옛 DB 의 다른 표를 건드리지
# 않는지 지킨다.

"""시뮬레이션 마이그레이션 0041 — 공용 공정 그룹(머리 + 행).

새 DB 에 두 표의 칸 · 형 · NOT NULL · CHECK · 열쇠가 설계대로 섰는지 보고, 소유 칸이 없어 시나리오
삭제의 자동 발견(`_owned_tables`)에 들지 않는지 본다. 저장소로 시드까지 저장한 DB 를 0041 전으로
되감은 뒤(두 표를 걷고 기록을 지움) 러너를 다시 걸어 0041 하나만 돌고 다른 표의 행이 그대로인지
본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence import DuckDBScenarioRepository
from capa_simulation.persistence.migration_runner import apply_migrations, load_migrations
from capa_simulation.persistence.process_group_store import (
    PROCESS_GROUP_HEADER_TABLE,
    PROCESS_GROUP_ITEM_TABLE,
    PROCESS_GROUP_MIGRATION,
)
from capa_simulation.persistence.repository import _owned_tables

HEADER = f"app_meta.{PROCESS_GROUP_HEADER_TABLE}"
ITEM = f"app_meta.{PROCESS_GROUP_ITEM_TABLE}"


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect()
    apply_migrations(con)
    yield con
    con.close()


def _columns(connection: duckdb.DuckDBPyConnection, table: str) -> list[tuple[Any, ...]]:
    return connection.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'app_meta' AND table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()


def test_the_migration_file_is_number_forty_one() -> None:
    migration = next(item for item in load_migrations() if item.version == PROCESS_GROUP_MIGRATION)

    assert migration.name == "0041_global_process_group.sql"
    assert migration.sql.splitlines()[0].startswith("-- Purpose: ")


def test_the_two_tables_have_the_designed_columns_and_start_empty(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    assert _columns(connection, PROCESS_GROUP_HEADER_TABLE) == [
        ("profile_id", "INTEGER", "NO"),
        ("version", "INTEGER", "NO"),
        ("source", "VARCHAR", "NO"),
        ("updated_at", "TIMESTAMP", "NO"),
    ]
    assert _columns(connection, PROCESS_GROUP_ITEM_TABLE) == [
        ("profile_id", "INTEGER", "NO"),
        ("공정", "VARCHAR", "NO"),
        ("공정그룹", "VARCHAR", "NO"),
    ]
    assert connection.execute(f"SELECT count(*) FROM {HEADER}").fetchone() == (0,)
    assert connection.execute(f"SELECT count(*) FROM {ITEM}").fetchone() == (0,)


def _insert_item(connection: duckdb.DuckDBPyConnection, *values: Any) -> None:
    connection.execute(
        f'INSERT INTO {ITEM} (profile_id, "공정", "공정그룹") VALUES (?, ?, ?)', list(values)
    )


def test_a_header_and_assignments_fit_the_checks(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(f"INSERT INTO {HEADER} (profile_id, version, source) VALUES (1, 1, 'TEST')")
    _insert_item(connection, 1, "DEMO_DA", "FRONT")
    _insert_item(connection, 1, "DEMO_MOLD", "PKG")

    header = connection.execute(f"SELECT version, updated_at IS NOT NULL FROM {HEADER}").fetchall()
    rows = connection.execute(f'SELECT "공정", "공정그룹" FROM {ITEM} ORDER BY 1').fetchall()
    assert header == [(1, True)]
    assert rows == [("DEMO_DA", "FRONT"), ("DEMO_MOLD", "PKG")]


@pytest.mark.parametrize(
    "values",
    [
        (1, "", "FRONT"),
        (1, "DEMO_DA", ""),
        (2, "DEMO_DA", "FRONT"),
    ],
    ids=["empty-process", "empty-group", "second-profile"],
)
def test_the_item_checks_refuse_a_row_out_of_shape(
    connection: duckdb.DuckDBPyConnection, values: tuple[Any, ...]
) -> None:
    with pytest.raises(duckdb.ConstraintException):
        _insert_item(connection, *values)


@pytest.mark.parametrize(
    ("profile_id", "version"), [(2, 1), (1, 0)], ids=["second-profile", "version-zero"]
)
def test_the_header_checks_refuse_a_row_out_of_shape(
    connection: duckdb.DuckDBPyConnection, profile_id: int, version: int
) -> None:
    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            f"INSERT INTO {HEADER} (profile_id, version, source) VALUES (?, ?, 'TEST')",
            [profile_id, version],
        )


def test_one_process_belongs_to_one_group_only(connection: duckdb.DuckDBPyConnection) -> None:
    _insert_item(connection, 1, "DEMO_DA", "FRONT")

    with pytest.raises(duckdb.ConstraintException):
        _insert_item(connection, 1, "DEMO_DA", "PKG")


def test_processes_differing_only_in_case_are_separate_keys(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """맞대기는 대소문자를 가린다(공정 표시명과 같은 규칙) — 표도 두 공정을 따로 받는다."""
    _insert_item(connection, 1, "DEMO_DA", "FRONT")
    _insert_item(connection, 1, "demo_da", "PKG")

    assert connection.execute(f"SELECT count(*) FROM {ITEM}").fetchone() == (2,)


def test_the_tables_carry_no_owner_column_so_scenario_deletion_skips_them(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    owned = {(schema, table) for schema, table, _ in _owned_tables(connection)}

    assert ("app_meta", PROCESS_GROUP_HEADER_TABLE) not in owned
    assert ("app_meta", PROCESS_GROUP_ITEM_TABLE) not in owned


def _contents(connection: duckdb.DuckDBPyConnection) -> dict[str, list[tuple[Any, ...]]]:
    """표마다 모든 행(정렬) — 마이그레이션 기록은 걸 때마다 시각이 달라 뺀다."""
    tables = connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' ORDER BY 1, 2"
    ).fetchall()
    found: dict[str, list[tuple[Any, ...]]] = {}
    for schema, table in tables:
        if (schema, table) == ("app_meta", "schema_migration"):
            continue
        rows = connection.execute(f'SELECT * FROM "{schema}"."{table}"').fetchall()
        found[f"{schema}.{table}"] = sorted(rows, key=repr)
    return found


def test_an_old_database_gains_only_the_two_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    assert ensure_initial_scenario(repository).release is not None
    with duckdb.connect(str(path)) as con:
        con.execute(f"DROP TABLE {ITEM}")
        con.execute(f"DROP TABLE {HEADER}")
        con.execute(
            "DELETE FROM app_meta.schema_migration WHERE version = ?", [PROCESS_GROUP_MIGRATION]
        )
        before = _contents(con)
        assert HEADER not in before and ITEM not in before and before

        outcome = apply_migrations(con)

        after = _contents(con)
    assert outcome.applied == (PROCESS_GROUP_MIGRATION,)
    assert after.pop(HEADER) == []
    assert after.pop(ITEM) == []
    assert after == before
