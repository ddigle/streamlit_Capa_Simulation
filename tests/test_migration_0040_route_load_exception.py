# Purpose: 0040 이 부하 예외 선언 판 이력 표를 칸 · CHECK 대로 만들고 옛 DB 의 다른 표를
# 건드리지 않는지 지킨다.

"""시뮬레이션 마이그레이션 0040 — 부하 예외 선언 판 이력 표.

새 DB 에 칸 · 형 · NOT NULL · CHECK 가 설계대로 섰는지 보고, 저장소로 시드까지 저장한 DB 를
0040 전으로 되감은 뒤(표를 걷고 기록을 지움) 러너를 다시 걸어 0040 하나만 돌고 다른 표의 행이
그대로인지 본다.
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
from capa_simulation.persistence.route_load_exception_store import (
    ROUTE_LOAD_EXCEPTION_MIGRATION,
    ROUTE_LOAD_EXCEPTION_SCHEMA,
    ROUTE_LOAD_EXCEPTION_TABLE,
)

TABLE = f"{ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE}"


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect()
    apply_migrations(con)
    yield con
    con.close()


def test_the_migration_file_is_number_forty() -> None:
    migration = next(
        item for item in load_migrations() if item.version == ROUTE_LOAD_EXCEPTION_MIGRATION
    )

    assert migration.name == "0040_route_load_exception.sql"
    assert migration.sql.splitlines()[0].startswith("-- Purpose: ")


def test_the_table_has_the_designed_columns(connection: duckdb.DuckDBPyConnection) -> None:
    columns = connection.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
        [ROUTE_LOAD_EXCEPTION_SCHEMA, ROUTE_LOAD_EXCEPTION_TABLE],
    ).fetchall()

    assert columns == [
        ("seq", "INTEGER", "NO"),
        ("created_at", "TIMESTAMP", "NO"),
        ("applied_by", "VARCHAR", "YES"),
        ("source_place", "VARCHAR", "YES"),
        ("entries_json", "VARCHAR", "NO"),
        ("entry_count", "INTEGER", "NO"),
        ("digest", "VARCHAR", "NO"),
    ]
    assert connection.execute(f"SELECT count(*) FROM {TABLE}").fetchone() == (0,)


def _insert(connection: duckdb.DuckDBPyConnection, *values: Any) -> None:
    connection.execute(
        f"INSERT INTO {TABLE} (seq, entries_json, entry_count, digest) VALUES (?, ?, ?, ?)",
        list(values),
    )


def test_a_clear_and_a_declaration_fit_the_checks(connection: duckdb.DuckDBPyConnection) -> None:
    _insert(connection, 1, "{}", 0, "")
    _insert(connection, 2, '{"DEMO-P1":"buffer_x_core_chip"}', 1, "f" * 64)

    rows = connection.execute(f"SELECT seq, created_at IS NOT NULL FROM {TABLE}").fetchall()
    assert rows == [(1, True), (2, True)]


@pytest.mark.parametrize(
    "values",
    [
        (0, "{}", 0, ""),
        (1, "{}", -1, ""),
        (1, "{}", 0, "f" * 64),
        (1, '{"DEMO-P1":"buffer_x_core_chip"}', 1, ""),
    ],
    ids=["seq-zero", "negative-count", "clear-with-digest", "entries-without-digest"],
)
def test_the_checks_refuse_a_row_out_of_shape(
    connection: duckdb.DuckDBPyConnection, values: tuple[Any, ...]
) -> None:
    with pytest.raises(duckdb.ConstraintException):
        _insert(connection, *values)


def test_a_duplicate_version_is_refused(connection: duckdb.DuckDBPyConnection) -> None:
    _insert(connection, 1, "{}", 0, "")

    with pytest.raises(duckdb.ConstraintException):
        _insert(connection, 1, "{}", 0, "")


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


def test_an_old_database_gains_only_the_empty_table(tmp_path: Path) -> None:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    assert ensure_initial_scenario(repository).release is not None
    with duckdb.connect(str(path)) as con:
        con.execute(f"DROP TABLE {TABLE}")
        con.execute(
            "DELETE FROM app_meta.schema_migration WHERE version = ?",
            [ROUTE_LOAD_EXCEPTION_MIGRATION],
        )
        before = _contents(con)
        assert TABLE not in before and before

        outcome = apply_migrations(con)

        after = _contents(con)
    assert outcome.applied == (ROUTE_LOAD_EXCEPTION_MIGRATION,)
    assert after.pop(TABLE) == []
    assert after == before
