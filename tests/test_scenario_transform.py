# Purpose: 파생 입력의 16표 계약과 저장 표시순서 조회가 기존 공용 조회와 독립인지 검증한다.

from pathlib import Path

import pandas as pd
import pytest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.persistence import DuckDBScenarioRepository, ScenarioPreset
from capa_simulation.persistence.cache import clear_scenario_repository, load_scenario_snapshot
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    NON_MONTHLY_TABLES,
    copy_scenario_tables,
    validate_month_axes,
)


def test_table_partition_matches_data_contract() -> None:
    keys = load_core_data_contract().derived_keys
    assert set(MONTHLY_TABLES) == {
        name for name, columns in keys.items() if "생산계획년월" in columns
    }
    assert set(NON_MONTHLY_TABLES) == set(keys) - set(MONTHLY_TABLES)


def test_copy_normalizes_without_mutating_and_requires_all_tables() -> None:
    tables = _reference_tables()
    tables["RQ_PKG_PLAN"]["생산계획년월"] = "202608"
    copied = copy_scenario_tables(tables)
    assert copied["RQ_PKG_PLAN"]["생산계획년월"].tolist() == [202608]
    assert tables["RQ_PKG_PLAN"]["생산계획년월"].tolist() == ["202608"]
    del tables["RQ_MODULE"]
    with pytest.raises(ValueError, match="RQ_MODULE"):
        copy_scenario_tables(tables)


def test_axes_reject_empty_and_middle_missing_month() -> None:
    tables = _reference_tables()
    for name in MONTHLY_TABLES:
        tables[name] = pd.concat(
            [tables[name].assign(생산계획년월=month) for month in (202601, 202602, 202603)]
        )
    tables["RQ_UPEH"] = tables["RQ_UPEH"].iloc[[0, 2]]
    with pytest.raises(ValueError, match="RQ_UPEH: 누락 1개월 \\(2026-02\\)"):
        validate_month_axes(tables)
    for name in MONTHLY_TABLES:
        tables[name] = tables[name].iloc[:0]
    with pytest.raises(ValueError, match="월 데이터가 없습니다"):
        validate_month_axes(tables)


def test_saved_display_order_and_global_cache_do_not_alias(tmp_path: Path) -> None:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    tables = _reference_tables()
    snapshot = repository.create_scenario(
        _metadata(), tables, ScenarioPreset(202608, 202608, ("Process-A",))
    )
    global_rules = tables["RQ_DISPLAY_ORDER"].assign(분류값="Global")
    repository.replace_global_display_order(global_rules, source="테스트")
    try:
        normal = load_scenario_snapshot(str(path), snapshot.revision.revision_id)
        original = load_scenario_snapshot(
            str(path), snapshot.revision.revision_id, apply_global_display_order=False
        )
        assert normal.tables["RQ_DISPLAY_ORDER"]["분류값"].tolist() == ["Global"]
        assert original.tables["RQ_DISPLAY_ORDER"]["분류값"].tolist() == ["Product-A"]
        normal_again = repository.load_revision(snapshot.revision.revision_id)
        pd.testing.assert_frame_equal(
            normal_again.tables["RQ_DISPLAY_ORDER"], normal.tables["RQ_DISPLAY_ORDER"]
        )
    finally:
        clear_scenario_repository()
