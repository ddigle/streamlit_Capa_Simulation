# Purpose: 0039 가 여덟 표에 CUSTOM 칸을 더하고 옛 행을 표지로 채운 뒤 DEFAULT 를 걷는지 지킨다.

"""시뮬레이션 마이그레이션 0039 — CUSTOM 칸.

`0039` 를 적용된 것으로 미리 적어 두고 초기화하면 그 전 스키마에 머문다. 옛 행을 심은 뒤 그 기록을
지우고 러너로 `0039` 만 건다(0033 시험과 같은 꼴). 고정 DuckDB 판이 `ADD COLUMN … DEFAULT` 와
`ALTER COLUMN … DROP DEFAULT` 를 한 마이그레이션에서 받는지도 여기서 본다.

끝 시험은 저장소로 저장한 실제 리비전(시드 · 원천 0행 복제 · 원천 CUSTOM 이 상수인 데이터셋)을
열여섯 표의 CUSTOM 을 걷어 0039 전으로 되감은 뒤 `0039` 만 다시 건다. 다시 읽어 계산한 값이
되감기 전과 같고, 모든 행이 표지이며, 원천 상수로 되채우지 않았는지 본다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from importlib import resources
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from custom_key_tables import PART_A, custom_keyed_tables

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence import DuckDBScenarioRepository, ScenarioCreate
from capa_simulation.persistence.migration_runner import apply_migrations, load_migrations
from capa_simulation.persistence.repository import REFERENCE_TABLES
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK

CUSTOM_VERSION = 39
CUSTOM_TABLES = (
    "rq_pkg_plan",
    "rq_yld",
    "rq_chip_qty",
    "rq_chip_eq",
    "rq_upeh",
    "rq_lot_ratio",
    "rq_wf_ratio",
    "rq_reqb",
)
OWNERS = {"rev_data": "revision_id", "ref_data": "dataset_id"}


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect()
    migration = next(item for item in load_migrations() if item.version == CUSTOM_VERSION)
    con.execute("CREATE SCHEMA IF NOT EXISTS app_meta")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta.schema_migration (
            version INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    con.execute(
        "INSERT INTO app_meta.schema_migration (version, name, checksum) VALUES (?, ?, ?)",
        [migration.version, migration.name, migration.checksum],
    )
    apply_migrations(con)
    yield con
    con.close()


def _plant_old_rows(con: duckdb.DuckDBPyConnection) -> None:
    for schema, owner in OWNERS.items():
        for table in CUSTOM_TABLES:
            con.execute(
                f'INSERT INTO {schema}.{table} ({owner}, source_row_no, "제품정보") '
                "VALUES ('old', 1, 'DEMO_P1'), ('old', 2, NULL)"
            )


def _apply_custom(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DELETE FROM app_meta.schema_migration WHERE version = ?", [CUSTOM_VERSION])
    assert apply_migrations(con).applied == (CUSTOM_VERSION,)


def test_the_held_back_schema_has_no_custom(connection: duckdb.DuckDBPyConnection) -> None:
    """되감은 템플릿은 정말 0039 전 스키마다 — 그래야 아래 시험이 0039 를 잰다."""
    rows = connection.execute(
        "SELECT count(*) FROM information_schema.columns WHERE column_name = 'CUSTOM' "
        "AND table_schema IN ('rev_data', 'ref_data')"
    ).fetchone()
    assert rows == (0,)


def test_old_rows_become_the_blank_marker(connection: duckdb.DuckDBPyConnection) -> None:
    """옛 행은 모두 빈 값 표지이고 다른 값 · 행 수는 그대로다."""
    _plant_old_rows(connection)

    _apply_custom(connection)

    for schema, owner in OWNERS.items():
        for table in CUSTOM_TABLES:
            rows = connection.execute(
                f'SELECT {owner}, source_row_no, "제품정보", "CUSTOM" FROM {schema}.{table} '
                "ORDER BY source_row_no"
            ).fetchall()
            assert rows == [
                ("old", 1, "DEMO_P1", CUSTOM_BLANK),
                ("old", 2, None, CUSTOM_BLANK),
            ], f"{schema}.{table}"


def test_no_default_is_left_behind(connection: duckdb.DuckDBPyConnection) -> None:
    """DEFAULT 를 걷어 CUSTOM 을 빠뜨린 저장이 조용히 표지로 채워지지 않는다."""
    _apply_custom(connection)

    defaults = connection.execute(
        "SELECT table_schema, table_name, column_default FROM information_schema.columns "
        "WHERE column_name = 'CUSTOM' AND table_schema IN ('rev_data', 'ref_data')"
    ).fetchall()
    assert sorted((schema, table) for schema, table, _ in defaults) == sorted(
        (schema, table) for schema in OWNERS for table in CUSTOM_TABLES
    )
    assert {default for _, _, default in defaults} == {None}
    connection.execute("INSERT INTO rev_data.rq_yld (revision_id, source_row_no) VALUES ('new', 1)")
    assert connection.execute(
        "SELECT \"CUSTOM\" FROM rev_data.rq_yld WHERE revision_id = 'new'"
    ).fetchall() == [(None,)]


def test_custom_is_the_last_column(connection: duckdb.DuckDBPyConnection) -> None:
    """칸은 표 끝에 붙는다 — 변환이 칸 목록 끝에 CUSTOM 을 두는 까닭이다."""
    _apply_custom(connection)

    for schema in OWNERS:
        for table in CUSTOM_TABLES:
            last = connection.execute(
                "SELECT column_name FROM duckdb_columns() WHERE schema_name = ? "
                "AND table_name = ? ORDER BY column_index DESC LIMIT 1",
                [schema, table],
            ).fetchone()
            assert last == ("CUSTOM",), f"{schema}.{table}"


def test_the_sql_marker_is_the_code_constant() -> None:
    """SQL 은 고칠 수 없어 표지 글자가 영구다 — 코드 상수와 같아야 한다."""
    sql = (
        resources.files("capa_simulation.persistence.migrations")
        .joinpath("0039_custom_product_key.sql")
        .read_text(encoding="utf-8")
    )

    assert sql.count(f"DEFAULT '{CUSTOM_BLANK}'") == 2 * len(CUSTOM_TABLES)
    assert sql.count("DROP DEFAULT") == 2 * len(CUSTOM_TABLES)


def _migration_sql() -> str:
    return (
        resources.files("capa_simulation.persistence.migrations")
        .joinpath("0039_custom_product_key.sql")
        .read_text(encoding="utf-8")
    )


def test_the_migrated_tables_are_the_contract_custom_tables() -> None:
    """⑥ 0039 가 칸을 더하는 표 = 계약상 CUSTOM 키 표의 리비전 · 데이터셋 짝 표다.

    계약에 CUSTOM 키 표가 늘었는데 마이그레이션이 그 표를 빠뜨리면 옛 리비전을 읽다 멈춘다."""
    added = set(re.findall(r'ALTER TABLE (\w+)\.(\w+) ADD COLUMN "CUSTOM"', _migration_sql()))
    expected = {
        (schema, REFERENCE_TABLES[name]) for schema in OWNERS for name in custom_keyed_tables()
    }

    assert added == expected
    assert {table for _, table in added} == set(CUSTOM_TABLES)


def _metadata(name: str, code: str) -> ScenarioCreate:
    return ScenarioCreate(
        scenario_name=name,
        source_simulation_code=code,
        source_simulation_name=name,
        source_type="TEST",
        pipeline_version="test-v1",
    )


def _with_custom(tables: Mapping[str, pd.DataFrame], value: str) -> dict[str, pd.DataFrame]:
    keyed = custom_keyed_tables()
    return {
        name: frame.assign(CUSTOM=value) if name in keyed else frame.copy()
        for name, frame in tables.items()
    }


def _calculated(repository: DuckDBScenarioRepository, revision_id: str) -> list[pd.DataFrame]:
    """저장 리비전의 전체 기간 대당 Capa · 소요대수(CUSTOM 칸 뺌)."""
    tables = repository.load_revision(revision_id).tables
    outcome = sc.full_capacity_outcome(tables, tables)
    assert outcome.error is None, outcome.error
    assert outcome.unit_capacity is not None and outcome.required_equipment is not None
    return [
        frame.drop(columns=["CUSTOM"]).reset_index(drop=True)
        for frame in (outcome.unit_capacity, outcome.required_equipment)
    ]


def _rewind_custom(path: Path) -> None:
    """열여섯 표의 CUSTOM 을 걷고 0039 기록을 지운 뒤 러너로 0039 만 다시 건다."""
    with duckdb.connect(str(path)) as con:
        for schema in OWNERS:
            for table in CUSTOM_TABLES:
                con.execute(f'ALTER TABLE {schema}.{table} DROP COLUMN "CUSTOM"')
        _apply_custom(con)


def test_old_revisions_calculate_the_same_after_the_migration(tmp_path: Path) -> None:
    """⑦ 옛 리비전은 0039 전후 계산이 같고, 모든 행이 표지이며, 원천 상수로 되채우지 않는다.

    셋을 저장한다 — 내장 시드, 원천 없이 복제한 시나리오(원천 0행), 원천 CUSTOM 이 한 상수인
    데이터셋(옛 조회문 상수 꼴 — 리비전에도 그 상수가 실려 있다).
    """
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    seed = repository.load_revision(release.revision_id, apply_global_display_order=False)
    clone = repository.create_scenario(_metadata("복제", "SIM-CLONE"), seed.tables, seed.preset)
    source = build_builtin_seed_dataset().source_data.assign(CUSTOM=PART_A)
    constant = repository.create_scenario(
        _metadata("원천 상수", "SIM-CONSTANT"),
        _with_custom(seed.tables, PART_A),
        seed.preset,
        source_data=source,
    )
    revisions = [
        seed.revision.revision_id,
        clone.revision.revision_id,
        constant.revision.revision_id,
    ]
    before = {revision: _calculated(repository, revision) for revision in revisions}
    assert set(repository.load_revision(revisions[2]).tables["RQ_PKG_PLAN"]["CUSTOM"]) == {PART_A}

    _rewind_custom(path)

    reopened = DuckDBScenarioRepository(path)
    assert reopened.initialize() == ()
    for revision in revisions:
        for old, new in zip(before[revision], _calculated(reopened, revision), strict=True):
            pd.testing.assert_frame_equal(new, old)
    with duckdb.connect(str(path), read_only=True) as con:
        for table in CUSTOM_TABLES:
            values = con.execute(f'SELECT DISTINCT "CUSTOM" FROM rev_data.{table}').fetchall()
            assert values == [(CUSTOM_BLANK,)], table
        kept = con.execute(
            'SELECT DISTINCT "CUSTOM" FROM raw_data.core_data WHERE dataset_id = ?',
            [constant.scenario.dataset_id],
        ).fetchall()
    assert kept == [(PART_A,)]
