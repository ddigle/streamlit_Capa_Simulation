"""One-time bootstrap from the development Core Data CSV and XLSB display order."""

from __future__ import annotations

import argparse
from pathlib import Path

from capa_simulation.io.core_data_source import read_core_data_csv
from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.persistence import (
    DuckDBScenarioRepository,
    ScenarioCreate,
    ScenarioPreset,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.reference_transformer import build_reference_tables
from capa_simulation.settings import CORE_DATA_CSV_PATH, DUCKDB_PATH, PROJECT_ROOT

DEFAULT_SOURCE_CODE = "LOCAL-CORE-DATA-INITIAL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--core-data", type=Path, default=CORE_DATA_CSV_PATH)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=PROJECT_ROOT / "templates" / "structure_template.xlsb",
        help="초기 RQ_DISPLAY_ORDER를 한 번 읽는 이관 전용 XLSB",
    )
    parser.add_argument("--scenario-name", default="Core Data 초기 시나리오")
    parser.add_argument("--source-code", default=DEFAULT_SOURCE_CODE)
    parser.add_argument("--source-name", default="Core_Data.csv 개발 원천")
    parser.add_argument("--revision-name", default="초기 이관 리비전")
    parser.add_argument("--release-name", default="초기 공식버전")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = DuckDBScenarioRepository(args.database.resolve())
    applied = repository.initialize()
    if applied:
        print(f"Applied migrations: {applied}")

    existing = [
        scenario
        for scenario in repository.list_scenarios(include_archived=True)
        if scenario.source_simulation_code == args.source_code
    ]
    if existing:
        scenario = existing[0]
        if scenario.status != "ACTIVE":
            raise RuntimeError("초기 이관 시나리오가 이미 보관 상태입니다.")
        latest = repository.latest_official_release()
        if latest is not None and latest.revision_id == scenario.active_revision_id:
            print(
                f"Already bootstrapped: {scenario.scenario_name} "
                f"r{scenario.active_revision_no}, official v{latest.release_no}"
            )
            return
        release = repository.publish_official_revision(
            scenario.scenario_id,
            scenario.active_revision_id,
            release_name=args.release_name,
            note="기존 초기 이관 시나리오의 활성 리비전을 공식버전으로 지정",
        )
        print(f"Published existing scenario as official v{release.release_no}")
        return

    core_data = read_core_data_csv(args.core_data.resolve())
    display_order = load_reference_tables(args.workbook.resolve())["RQ_DISPLAY_ORDER"]
    reference_tables = build_reference_tables(core_data, display_order)
    start_month, end_month = available_month_range(
        reference_tables["RQ_PKG_PLAN"],
        "RQ_PKG_PLAN",
    )
    processes = tuple(
        sorted(
            reference_tables["RQ_REQB"]["공정"]
            .astype("string")
            .str.strip()
            .dropna()
            .unique()
            .tolist()
        )
    )
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name=args.scenario_name,
            source_simulation_code=args.source_code,
            source_simulation_name=args.source_name,
            source_type="CSV_CORE_DATA_INITIAL_BOOTSTRAP",
            pipeline_version="core-data-pandas-v2",
        ),
        reference_tables,
        ScenarioPreset(start_month, end_month, processes),
        source_data=core_data,
        revision_name=args.revision_name,
        note="Core_Data.csv와 XLSB 표시순서의 일회성 DuckDB 초기 이관",
    )
    release = repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=args.release_name,
        note="DuckDB 전용 런타임 전환을 위한 초기 공식버전",
    )
    print(
        f"Created {snapshot.scenario.scenario_name}: "
        f"{len(core_data):,} raw rows, {len(reference_tables['RQ_DISPLAY_ORDER']):,} "
        f"display-order rows, official v{release.release_no}"
    )


if __name__ == "__main__":
    main()
