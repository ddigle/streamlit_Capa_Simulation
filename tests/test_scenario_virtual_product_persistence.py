# Purpose: 신규 시나리오의 가상제품 이력과 16표 동시 저장 및 실패 시 전체 롤백을 검증한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence._sql_helpers import connect, quote
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository


def _record(product: str = "Product-A") -> dict[str, str]:
    return {
        "product": product,
        "stack": "8H",
        "source_product": "Original-A",
        "source_stack": "8H",
    }


def _repository(database: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    return repository


def _table_counts(database: Path) -> dict[str, int]:
    # 시나리오 헤더뿐 아니라 모든 기준정보·리비전·프리셋 행의 잔여물도 확인한다.
    with connect(database) as connection:
        tables = connection.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('app_meta', 'raw_data', 'ref_data', 'rev_data')
              AND table_type = 'BASE TABLE'
            """
        ).fetchall()
        return {
            f"{schema}.{table}": connection.execute(
                f"SELECT COUNT(*) FROM {quote(schema)}.{quote(table)}"
            ).fetchone()[0]
            for schema, table in tables
        }


def test_new_scenario_stores_initial_virtual_history_without_changing_source(
    tmp_path: Path,
) -> None:
    database = tmp_path / "scenario.duckdb"
    repository = _repository(database)
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    source = repository.create_scenario(
        _metadata("원본"), _reference_tables(), preset, virtual_products=[_record()]
    )
    history_before = repository.list_virtual_products(source.revision.revision_id)
    input_copies = {name: frame.copy(deep=True) for name, frame in source.tables.items()}
    records = [_record()]

    created = repository.create_scenario(
        _metadata("파생 시나리오"), source.tables, source.preset, virtual_products=records
    )

    reopened = DuckDBScenarioRepository(database)
    reloaded = reopened.load_revision(
        created.revision.revision_id, apply_global_display_order=False
    )
    assert reloaded.scenario.scenario_id != source.scenario.scenario_id
    assert reloaded.revision.revision_no == 1
    assert len(reloaded.tables) == 16
    assert reopened.list_virtual_products(reloaded.revision.revision_id).to_dict("records") == [
        {
            "제품정보": "Product-A",
            "Stack": "8H",
            "원본 제품정보": "Original-A",
            "원본 Stack": "8H",
        }
    ]
    assert records == [_record()]
    for name, frame in input_copies.items():
        pd.testing.assert_frame_equal(source.tables[name], frame)
        pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    source_reloaded = reopened.load_revision(
        source.revision.revision_id, apply_global_display_order=False
    )
    assert len(reopened.list_revisions(source.scenario.scenario_id)) == 1
    for name, frame in source.tables.items():
        pd.testing.assert_frame_equal(source_reloaded.tables[name], frame)
    pd.testing.assert_frame_equal(
        reopened.list_virtual_products(source.revision.revision_id), history_before
    )


@pytest.mark.parametrize(
    ("invalid_record", "exception"),
    [
        pytest.param(
            {"product": "Product-C", "stack": "8H", "source_product": "Original-A"},
            KeyError,
            id="missing-field",
        ),
        pytest.param(
            {**_record("Product-C"), "source_product": None},
            duckdb.ConstraintException,
            id="null-field",
        ),
        pytest.param(_record("Product-B"), duckdb.ConstraintException, id="duplicate-product"),
    ],
)
def test_failed_virtual_history_rolls_back_the_entire_new_scenario(
    tmp_path: Path, invalid_record, exception
) -> None:
    database = tmp_path / "scenario.duckdb"
    repository = _repository(database)
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    source = repository.create_scenario(
        _metadata("보존할 원본"), _reference_tables(), preset, virtual_products=[_record()]
    )
    history_before = repository.list_virtual_products(source.revision.revision_id)
    counts_before = _table_counts(database)

    # 첫 이력은 실제 삽입되고 두 번째에서 실패하므로 부분 저장도 남지 않아야 한다.
    with pytest.raises(exception):
        repository.create_scenario(
            _metadata("실패할 시나리오"),
            source.tables,
            source.preset,
            virtual_products=[_record("Product-B"), invalid_record],
        )

    assert _table_counts(database) == counts_before
    assert [item.scenario_id for item in repository.list_scenarios()] == [
        source.scenario.scenario_id
    ]
    reloaded = repository.load_revision(
        source.revision.revision_id, apply_global_display_order=False
    )
    assert len(repository.list_revisions(source.scenario.scenario_id)) == 1
    for name, frame in source.tables.items():
        pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(source.revision.revision_id), history_before
    )


def test_default_new_scenario_still_has_no_virtual_history(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    tables = _reference_tables()
    preset = ScenarioPreset(202608, 202608, ("Process-A",))

    default = repository.create_scenario(_metadata("기본 생성"), tables, preset)
    explicit_empty = repository.create_scenario(
        _metadata("빈 이력 생성"), tables, preset, virtual_products=()
    )

    assert len(repository.list_scenarios()) == 2
    for snapshot in (default, explicit_empty):
        assert snapshot.revision.revision_no == 1
        assert len(snapshot.tables) == 16
        assert repository.list_virtual_products(snapshot.revision.revision_id).empty
    for name in default.tables:
        pd.testing.assert_frame_equal(default.tables[name], explicit_empty.tables[name])
