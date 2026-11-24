# Purpose: 신규 시나리오의 가상제품 이력과 16표 동시 저장 및 실패 시 전체 롤백을 검증한다.

from dataclasses import asdict
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from custom_key_tables import (
    PART_A,
    PART_B,
    TWO_PART_PRODUCT,
    custom_keyed_tables,
    two_part_tables,
)
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence._sql_helpers import connect, quote
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import BUILTIN_SEED_MONTHS, builtin_seed_processes
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    clone_product,
    records_to_frame,
)


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
        counts: dict[str, int] = {}
        for schema, table in tables:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {quote(schema)}.{quote(table)}"
            ).fetchone()
            assert row is not None
            counts[f"{schema}.{table}"] = row[0]
        return counts


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
    tmp_path: Path, invalid_record: dict[str, str | None], exception: type[Exception]
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
            virtual_products=[_record("Product-B"), invalid_record],  # type: ignore[list-item]
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


def test_a_two_part_product_clone_is_stored_with_both_parts(tmp_path: Path) -> None:
    """두 부품 제품을 복제해 새 시나리오로 저장하면 다시 읽은 여덟 표에 두 부품이 모두 있다.

    이력은 제품 키(제품정보 · Stack) 한 줄이다 — 부품은 복제 단위가 아니다."""
    tables = two_part_tables()
    plan = tables["RQ_PKG_PLAN"]
    stack = str(plan.loc[plan["제품정보"].eq(TWO_PART_PRODUCT), "Stack"].iloc[0])
    request = VirtualProductRequest(TWO_PART_PRODUCT, stack, "DEMO_NEW_PARTS", stack)
    cloned = {**tables, **clone_product(tables, request)}
    record = VirtualProductRecord.from_request(request)
    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(
        min(BUILTIN_SEED_MONTHS), max(BUILTIN_SEED_MONTHS), builtin_seed_processes()
    )

    created = repository.create_scenario(
        _metadata("두 부품 복제"), cloned, preset, virtual_products=[asdict(record)]
    )

    reloaded = DuckDBScenarioRepository(tmp_path / "scenario.duckdb").load_revision(
        created.revision.revision_id, apply_global_display_order=False
    )
    for name in custom_keyed_tables():
        frame = reloaded.tables[name]
        new_rows = frame.loc[frame["제품정보"].eq("DEMO_NEW_PARTS")]
        source_rows = frame.loc[frame["제품정보"].eq(TWO_PART_PRODUCT)]
        assert sorted(set(new_rows["CUSTOM"])) == [PART_A, PART_B], name
        assert len(new_rows) == len(source_rows), name
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(created.revision.revision_id),
        records_to_frame((record,)),
    )
