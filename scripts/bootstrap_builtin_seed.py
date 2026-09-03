# Purpose: Create the built-in synthetic scenario in an empty DuckDB store.

"""Create the built-in synthetic scenario in an empty DuckDB store."""

from __future__ import annotations

import argparse
from pathlib import Path

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.settings import DUCKDB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DUCKDB_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = DuckDBScenarioRepository(args.database.resolve())
    applied = repository.initialize()
    result = ensure_initial_scenario(repository)
    if applied:
        print(f"Applied migrations: {applied}")
    if result.release is None:
        raise RuntimeError(
            "공식버전 없는 기존 시나리오가 있어 내장 시드를 생성하지 않았습니다. "
            "기존 리비전을 공식 발행하거나 별도 빈 DB 경로를 사용하세요."
        )
    print(
        f"Bootstrap status: {result.status}; official v{result.release.release_no}; "
        f"{result.release.scenario_name} r{result.release.revision_no}"
    )


if __name__ == "__main__":
    main()
