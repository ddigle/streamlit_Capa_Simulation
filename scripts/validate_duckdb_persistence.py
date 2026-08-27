"""Validate Core Data transformations and a temporary DuckDB round trip."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pandas as pd

from capa_simulation.io.core_data_source import read_core_data_csv
from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.persistence import (
    DuckDBScenarioRepository,
    ScenarioCreate,
    ScenarioPreset,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.reference_transformer import build_reference_tables
from capa_simulation.settings import INPUT_DIR, PROJECT_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workbook",
        type=Path,
        default=PROJECT_ROOT / "templates" / "structure_template.xlsb",
    )
    parser.add_argument(
        "--core-data",
        type=Path,
        default=INPUT_DIR / "Core_Data.csv",
    )
    return parser.parse_args()


def assert_frame_values_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    """Compare values after canonicalizing pandas' interchangeable null sentinels."""
    normalized: list[pd.DataFrame] = []
    for frame in (actual, expected):
        comparable = frame.astype(object)
        comparable[comparable.isna()] = None
        normalized.append(comparable)
    pd.testing.assert_frame_equal(normalized[0], normalized[1], check_dtype=False)


def main() -> None:
    args = parse_args()
    xlsb_tables = load_reference_tables(args.workbook.resolve())
    core_data = read_core_data_csv(args.core_data.resolve())
    source = build_reference_tables(core_data, xlsb_tables["RQ_DISPLAY_ORDER"])
    for name, expected in xlsb_tables.items():
        actual = source[name]
        assert_frame_values_equal(actual, expected)
        print(f"{name}: Power Query match ({len(actual):,} rows)")

    start_month, end_month = available_month_range(source["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    processes = tuple(
        sorted(source["RQ_REQB"]["공정"].astype("string").str.strip().dropna().unique())
    )
    preset = ScenarioPreset(start_month, end_month, processes)

    with tempfile.TemporaryDirectory(prefix="capa-duckdb-validation-") as directory:
        repository = DuckDBScenarioRepository(Path(directory) / "validation.duckdb")
        repository.initialize()
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name="Persistence validation",
                source_simulation_code="VALIDATION-CORE-DATA",
                source_simulation_name="Core Data validation snapshot",
                source_type="CSV_CORE_DATA",
                pipeline_version="core-data-pandas-v1",
            ),
            source,
            preset,
            source_data=core_data,
        )

        for name, expected in source.items():
            actual = snapshot.tables[name]
            assert_frame_values_equal(actual, expected)
            print(f"{name}: DuckDB round trip ({len(actual):,} rows)")
        stored_core_data = repository.load_source_data(snapshot.scenario.scenario_id)
        assert_frame_values_equal(stored_core_data, core_data)
        stored_profile = repository.load_source_profile(snapshot.scenario.scenario_id)
        if len(stored_profile) != len(core_data.columns):
            raise AssertionError("Core Data 컬럼 프로파일 행 수가 일치하지 않습니다.")
        if snapshot.preset != preset:
            raise AssertionError("시나리오 프리셋 round-trip이 일치하지 않습니다.")
        print(f"Core Data: DuckDB round trip ({len(stored_core_data):,} rows, 78 columns)")
        print("Core Data transformation and DuckDB persistence validation passed")


if __name__ == "__main__":
    main()
