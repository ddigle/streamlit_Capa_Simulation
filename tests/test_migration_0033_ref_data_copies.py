# Purpose: 0033 이 리비전 1 과 같은 `ref_data` 옛 사본만 지우는지 러너 경로로 고정한다.

"""**지워도 되는 사본만 지우는가**를 본다.

2026-10-06 결정(B3) 전에는 시나리오를 만들 때 리비전 표 14개를 데이터셋(`ref_data`)과
리비전 1(`rev_data`)에 똑같이 적었다. 지금 `create_scenario` 는 리비전 1 에만 적으므로 여기서는
옛 방식을 흉내 내 리비전 1 의 행을 `ref_data` 에 그대로 옮겨 심은 뒤 `0033` 만 되감아 다시 건다.

러너(`apply_migrations`)를 그대로 지나간다. 파일이 TEMP VIEW 를 만들고 표를 다시 만들기
때문에 SQL 만 떼어 돌리면 실제 적용 경로를 증명하지 못한다.

지우는 단위는 (데이터셋, 표)이고 기준은 **그 시나리오의 리비전 1** 하나다. 한 행이라도
리비전 1 에 없으면 그 표 사본은 통째로 남는다. 마이그레이션은 표를 다시 만들어 지우므로
스키마(열 이름·순서·형식·NOT NULL·기본키)가 전후 같은지도 본다.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence import DuckDBScenarioRepository, ScenarioCreate
from capa_simulation.persistence.migration_runner import apply_migrations
from capa_simulation.persistence.repository import DATASET_TABLES, REVISION_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import audit_top_remigration  # noqa: E402
import inspect_real_data_checks  # noqa: E402
import inspect_top_remigration  # noqa: E402
import inspect_wf_division  # noqa: E402

CLEANUP_VERSION = 33
# 값을 바꿔 볼 표. 행이 많고 NULL 이 될 수 있는 키 열(`WF 구분`)과 값 열(`UPEH`)이 함께 있다.
PROBE_TABLE = "rq_upeh"
COVERAGE_SCRIPTS = (inspect_top_remigration, audit_top_remigration, inspect_wf_division)


@dataclass(frozen=True)
class Template:
    """시나리오 둘을 담은 DB 원본. 테스트마다 파일을 복사해 쓴다."""

    path: Path
    seed_dataset: str
    seed_first_revision: str
    clone_dataset: str
    clone_first_revision: str
    clone_second_revision: str


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Template:
    """내장 시드 시나리오와, 그것을 복제하고 리비전 2 에서 `RQ_YLD` 를 고친 시나리오."""
    path = tmp_path_factory.mktemp("ref_copies") / "template.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    seed = repository.load_revision(release.revision_id, apply_global_display_order=False)
    clone = repository.create_scenario(
        ScenarioCreate(
            scenario_name="복제 시나리오",
            source_simulation_code="SIM-CLONE",
            source_simulation_name="복제",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        seed.tables,
        seed.preset,
    )
    edited = {name: clone.tables[name].copy() for name in REVISION_TABLES}
    yld = edited["RQ_YLD"]
    yld.loc[yld.index[0], "EDS_수율"] = 0.4321
    second = repository.save_revision(
        clone.scenario.scenario_id, edited, clone.preset, revision_name="둘째"
    )
    return Template(
        path=path,
        seed_dataset=seed.scenario.dataset_id,
        seed_first_revision=seed.revision.revision_id,
        clone_dataset=clone.scenario.dataset_id,
        clone_first_revision=clone.revision.revision_id,
        clone_second_revision=second.revision.revision_id,
    )


@pytest.fixture
def database(template: Template, tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    shutil.copyfile(template.path, path)
    wal = template.path.with_name(template.path.name + ".wal")
    if wal.exists():
        shutil.copyfile(wal, path.with_name(path.name + ".wal"))
    return path


@pytest.fixture
def connection(database: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(str(database))
    yield con
    con.close()


def _plant_copy(
    con: duckdb.DuckDBPyConnection, table: str, dataset_id: str, revision_id: str
) -> None:
    """B3 전 `create_scenario` 처럼 리비전의 행을 데이터셋 사본으로 그대로 옮겨 적는다."""
    con.execute(
        f"INSERT INTO ref_data.{table} BY NAME "
        "SELECT CAST(? AS VARCHAR) AS dataset_id, * EXCLUDE (revision_id) "
        f"FROM rev_data.{table} WHERE revision_id = ?",
        [dataset_id, revision_id],
    )


def _plant_all(con: duckdb.DuckDBPyConnection, dataset_id: str, revision_id: str) -> None:
    for table in REVISION_TABLES.values():
        _plant_copy(con, table, dataset_id, revision_id)


def _rewind_and_apply(con: duckdb.DuckDBPyConnection) -> None:
    """`0033` 만 되감아 다시 적용한다. 사본을 심은 뒤 그 파일만 돌리는 방법이다."""
    con.execute("DELETE FROM app_meta.schema_migration WHERE version = ?", [CLEANUP_VERSION])
    assert apply_migrations(con).applied == (CLEANUP_VERSION,)


def _copy_rows(con: duckdb.DuckDBPyConnection, table: str, dataset_id: str) -> int:
    row = con.execute(
        f"SELECT count(*) FROM ref_data.{table} WHERE dataset_id = ?", [dataset_id]
    ).fetchone()
    assert row is not None
    return int(row[0])


def _all_rows(con: duckdb.DuckDBPyConnection, schema: str, tables: list[str]) -> dict[str, Any]:
    return {
        table: con.execute(f"SELECT * FROM {schema}.{table} ORDER BY ALL").fetchall()
        for table in tables
    }


def _ref_data_schema(con: duckdb.DuckDBPyConnection) -> tuple[list[Any], list[Any]]:
    columns = con.execute(
        "SELECT table_name, column_name, column_index, data_type, is_nullable "
        "FROM duckdb_columns() WHERE schema_name = 'ref_data' ORDER BY ALL"
    ).fetchall()
    constraints = con.execute(
        "SELECT table_name, constraint_type, constraint_text "
        "FROM duckdb_constraints() WHERE schema_name = 'ref_data' ORDER BY ALL"
    ).fetchall()
    return columns, constraints


def _first_row_no(con: duckdb.DuckDBPyConnection, dataset_id: str) -> int:
    row = con.execute(
        f"SELECT min(source_row_no) FROM ref_data.{PROBE_TABLE} WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    assert row is not None and row[0] is not None
    return int(row[0])


def test_copies_that_match_revision_one_go_and_nothing_else_changes(
    template: Template, database: Path
) -> None:
    """두 데이터셋의 14표 사본이 모두 리비전 1 과 같다 — 사본만 사라지고 나머지는 그대로다."""
    repository = DuckDBScenarioRepository(database)
    before_snapshots = {
        revision_id: repository.load_revision(revision_id, apply_global_display_order=False)
        for revision_id in (template.seed_first_revision, template.clone_first_revision)
    }
    with duckdb.connect(str(database)) as con:
        _plant_all(con, template.seed_dataset, template.seed_first_revision)
        _plant_all(con, template.clone_dataset, template.clone_first_revision)
        revision_rows = _all_rows(con, "rev_data", [*REVISION_TABLES.values(), "rq_display_order"])
        dataset_rows = _all_rows(con, "ref_data", list(DATASET_TABLES.values()))
        assert dataset_rows["rq_display_order"] and dataset_rows["rq_module"]

        _rewind_and_apply(con)

        for table in REVISION_TABLES.values():
            assert _copy_rows(con, table, template.seed_dataset) == 0, table
            assert _copy_rows(con, table, template.clone_dataset) == 0, table
        rows_after = _all_rows(con, "rev_data", [*REVISION_TABLES.values(), "rq_display_order"])
        assert rows_after == revision_rows
        assert _all_rows(con, "ref_data", list(DATASET_TABLES.values())) == dataset_rows
        assert inspect_real_data_checks._ref_data_copies(con) == (0, 0)

    for revision_id, before in before_snapshots.items():
        after = repository.load_revision(revision_id, apply_global_display_order=False)
        assert set(after.tables) == set(before.tables)
        for name, frame in before.tables.items():
            pd.testing.assert_frame_equal(after.tables[name], frame, obj=name)


@pytest.mark.parametrize(
    ("mutations", "kept"),
    [
        pytest.param(
            [f'UPDATE ref_data.{PROBE_TABLE} SET "UPEH" = "UPEH" + 1 {{where}}'],
            True,
            id="값 하나가 다르다",
        ),
        pytest.param(
            [
                f"INSERT INTO ref_data.{PROBE_TABLE} BY NAME "
                "SELECT * REPLACE (source_row_no + 1000000 AS source_row_no) "
                f"FROM ref_data.{PROBE_TABLE} {{where}}"
            ],
            True,
            id="사본에 행이 더 있다",
        ),
        pytest.param(
            [
                f"UPDATE ref_data.{PROBE_TABLE} "
                "SET source_row_no = source_row_no + 1000000 {where}"
            ],
            True,
            id="값은 같고 행 번호가 다르다",
        ),
        pytest.param(
            [f'UPDATE ref_data.{PROBE_TABLE} SET "WF 구분" = NULL {{where}}'],
            True,
            id="사본만 NULL",
        ),
        pytest.param(
            [f"DELETE FROM ref_data.{PROBE_TABLE} {{where}}"],
            False,
            id="사본이 리비전 1 보다 적다",
        ),
        pytest.param(
            [
                f'UPDATE ref_data.{PROBE_TABLE} SET "WF 구분" = NULL {{where}}',
                f'UPDATE rev_data.{PROBE_TABLE} SET "WF 구분" = NULL {{revision_where}}',
            ],
            False,
            id="둘 다 NULL",
        ),
    ],
)
def test_each_copy_is_judged_whole_against_revision_one(
    template: Template,
    connection: duckdb.DuckDBPyConnection,
    mutations: list[str],
    kept: bool,
) -> None:
    """한 행이라도 리비전 1 에 없으면 그 표 사본은 통째로 남는다. 다른 표·다른 데이터셋은 지운다.

    NULL 은 NULL 과 같다고 본다(집합 연산) — 둘 다 NULL 이면 같은 행이다.
    """
    _plant_all(connection, template.seed_dataset, template.seed_first_revision)
    _plant_all(connection, template.clone_dataset, template.clone_first_revision)
    row_no = _first_row_no(connection, template.seed_dataset)
    where = f"WHERE dataset_id = '{template.seed_dataset}' AND source_row_no = {row_no}"
    revision_where = (
        f"WHERE revision_id = '{template.seed_first_revision}' AND source_row_no = {row_no}"
    )
    for mutation in mutations:
        connection.execute(mutation.format(where=where, revision_where=revision_where))
    planted = _copy_rows(connection, PROBE_TABLE, template.seed_dataset)
    probe_rows = connection.execute(
        f"SELECT * FROM ref_data.{PROBE_TABLE} WHERE dataset_id = ? ORDER BY ALL",
        [template.seed_dataset],
    ).fetchall()

    _rewind_and_apply(connection)

    if kept:
        assert _copy_rows(connection, PROBE_TABLE, template.seed_dataset) == planted
        assert (
            connection.execute(
                f"SELECT * FROM ref_data.{PROBE_TABLE} WHERE dataset_id = ? ORDER BY ALL",
                [template.seed_dataset],
            ).fetchall()
            == probe_rows
        )
    else:
        assert _copy_rows(connection, PROBE_TABLE, template.seed_dataset) == 0
    for table in REVISION_TABLES.values():
        assert _copy_rows(connection, table, template.clone_dataset) == 0, table
        if table != PROBE_TABLE:
            assert _copy_rows(connection, table, template.seed_dataset) == 0, table


def test_only_revision_one_is_the_baseline(
    template: Template, connection: duckdb.DuckDBPyConnection
) -> None:
    """리비전 2 와 같아도 리비전 1 과 다르면 남는다. 사본은 리비전 1 과 함께 적혔다."""
    for table in REVISION_TABLES.values():
        source = (
            template.clone_second_revision if table == "rq_yld" else template.clone_first_revision
        )
        _plant_copy(connection, table, template.clone_dataset, source)
    planted = _copy_rows(connection, "rq_yld", template.clone_dataset)
    assert planted > 0

    _rewind_and_apply(connection)

    assert _copy_rows(connection, "rq_yld", template.clone_dataset) == planted
    for table in REVISION_TABLES.values():
        if table != "rq_yld":
            assert _copy_rows(connection, table, template.clone_dataset) == 0, table


def test_copies_without_a_first_revision_stay(
    template: Template, connection: duckdb.DuckDBPyConnection
) -> None:
    """`app_meta.dataset` 에 없는 데이터셋의 사본은 맞댈 리비전 1 이 없다 — 하나도 지우지 않는다."""
    _plant_all(connection, "ghost-dataset", template.seed_first_revision)
    planted = {
        table: _copy_rows(connection, table, "ghost-dataset") for table in REVISION_TABLES.values()
    }

    _rewind_and_apply(connection)

    for table, count in planted.items():
        assert _copy_rows(connection, table, "ghost-dataset") == count, table


def test_rebuilt_tables_keep_the_schema_and_a_second_run_changes_nothing(
    template: Template, database: Path
) -> None:
    """표를 다시 만들어도 열·형식·NOT NULL·기본키가 같고, 두 번째 적용은 아무것도 바꾸지 않는다.

    다시 만든 표도 시나리오 소유로 잡혀 시나리오를 지우면 함께 지워진다.
    """
    with duckdb.connect(str(database)) as con:
        schema_before = _ref_data_schema(con)
        _plant_all(con, template.seed_dataset, template.seed_first_revision)
        _plant_all(con, template.clone_dataset, template.clone_first_revision)
        con.execute(
            f'UPDATE ref_data.{PROBE_TABLE} SET "UPEH" = "UPEH" + 1 WHERE dataset_id = ?',
            [template.clone_dataset],
        )

        _rewind_and_apply(con)
        first_rows = _all_rows(con, "ref_data", list(REVISION_TABLES.values()))
        assert _ref_data_schema(con) == schema_before
        leftovers = con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE table_name LIKE '%\\_kept' ESCAPE '\\'"
        ).fetchall()
        assert leftovers == []
        views = con.execute(
            "SELECT view_name FROM duckdb_views() WHERE view_name = '_ref_copy_first_revision'"
        ).fetchall()
        assert views == []
        assert _copy_rows(con, PROBE_TABLE, template.clone_dataset) > 0

        _rewind_and_apply(con)
        assert _all_rows(con, "ref_data", list(REVISION_TABLES.values())) == first_rows
        assert _ref_data_schema(con) == schema_before

    repository = DuckDBScenarioRepository(database)
    clone_scenario = next(
        scenario
        for scenario in repository.list_scenarios()
        if scenario.dataset_id == template.clone_dataset
    )
    repository.delete_scenario(clone_scenario.scenario_id)
    with duckdb.connect(str(database), read_only=True) as con:
        assert _copy_rows(con, PROBE_TABLE, template.clone_dataset) == 0


def test_diagnostic_scripts_count_the_copies_that_remain(
    template: Template,
    connection: duckdb.DuckDBPyConnection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """진단 스크립트 첫머리의 「사본이 있는 데이터셋 수」는 남은 사본을 표마다 센다.

    `0033` 은 표마다 따로 지운다. 여기서는 복제 시나리오의 `rq_upeh` 사본만 남는다 — `rq_pkg_plan`
    하나만 세면 0 으로 보여 남은 사본을 놓친다.
    """
    _plant_all(connection, template.seed_dataset, template.seed_first_revision)
    _plant_all(connection, template.clone_dataset, template.clone_first_revision)
    connection.execute(
        f'UPDATE ref_data.{PROBE_TABLE} SET "UPEH" = "UPEH" + 1 WHERE dataset_id = ?',
        [template.clone_dataset],
    )
    for script in COVERAGE_SCRIPTS:
        script._ref_data_coverage(connection)
    before = capsys.readouterr().out
    assert before.count("사본이 있는 데이터셋 2 / 전체 2") == len(COVERAGE_SCRIPTS)

    _rewind_and_apply(connection)

    for script in COVERAGE_SCRIPTS:
        script._ref_data_coverage(connection)
    after = capsys.readouterr().out
    assert after.count("사본이 있는 데이터셋 1 / 전체 2") == len(COVERAGE_SCRIPTS)
    kept = _copy_rows(connection, PROBE_TABLE, template.clone_dataset)
    assert inspect_real_data_checks._ref_data_copies(connection) == (1, kept)

    connection.execute(f"DELETE FROM ref_data.{PROBE_TABLE}")
    for script in COVERAGE_SCRIPTS:
        script._ref_data_coverage(connection)
    cleared = capsys.readouterr().out
    assert cleared.count("사본이 있는 데이터셋 0 / 전체 2") == len(COVERAGE_SCRIPTS)
    assert inspect_real_data_checks._ref_data_copies(connection) == (0, 0)
