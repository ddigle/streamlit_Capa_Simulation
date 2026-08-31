"""Bootstrap or safely replace the development Core Data initial scenario."""

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
PIPELINE_VERSION = "core-data-pandas-v3"


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
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help=(
            "현재 변환 계약으로 대체 시나리오를 생성·공식 발행한 뒤 "
            "같은 원천 코드의 기존 활성 시나리오를 보관"
        ),
    )
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
    if existing and not args.replace_existing:
        active = [scenario for scenario in existing if scenario.status == "ACTIVE"]
        scenario = active[0] if active else existing[0]
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
    if existing:
        display_source = next(
            (scenario for scenario in existing if scenario.status == "ACTIVE"),
            existing[0],
        )
        display_order = repository.load_revision(display_source.active_revision_id).tables[
            "RQ_DISPLAY_ORDER"
        ]
    else:
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
            source_type=(
                "CSV_CORE_DATA_INITIAL_REFRESH" if existing else "CSV_CORE_DATA_INITIAL_BOOTSTRAP"
            ),
            pipeline_version=PIPELINE_VERSION,
        ),
        reference_tables,
        ScenarioPreset(start_month, end_month, processes),
        source_data=core_data,
        revision_name=args.revision_name,
        note=(
            "Core_Data.csv를 현재 RQ 경로 키 계약으로 재생성"
            if existing
            else "Core_Data.csv와 XLSB 표시순서의 일회성 DuckDB 초기 이관"
        ),
    )
    release = repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=args.release_name,
        note=(
            "Area·STEP·MCP 경로 키 계약을 적용한 초기 공식버전"
            if existing
            else "DuckDB 전용 런타임 전환을 위한 초기 공식버전"
        ),
    )
    archived_count = 0
    for previous in existing:
        if previous.status == "ACTIVE" and previous.scenario_id != snapshot.scenario.scenario_id:
            repository.archive_scenario(previous.scenario_id)
            archived_count += 1
    print(
        f"Created {snapshot.scenario.scenario_name}: "
        f"{len(core_data):,} raw rows, {len(reference_tables['RQ_DISPLAY_ORDER']):,} "
        f"display-order rows, official v{release.release_no}, "
        f"archived {archived_count} previous scenario(s)"
    )


if __name__ == "__main__":
    main()
