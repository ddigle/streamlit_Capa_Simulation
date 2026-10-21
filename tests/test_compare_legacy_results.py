# Purpose: 기존 결과 대조 스크립트가 기본으로 원천 행이 있는 데이터셋을 골라 대조하는지 본다.

"""`scripts/compare_legacy_results.py` 는 데이터셋의 원천 행과 그 시나리오의 리비전 1 을 맞춰 본다.

복제·월 병합·연도 이동은 원천 행을 남기지 않는다. 그것이 가장 최근이어도 기본 실행은 원천에서 온
데이터셋을 골라야 한다 — 그렇지 않으면 복제가 흔한 사외 DB 에서 기본 명령이 늘 「원천 행이
없습니다」로 끝난다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import compare_legacy_results as compare  # noqa: E402


@pytest.fixture(scope="module")
def seeded_with_clone(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """내장 시드 + 그보다 나중에 만든 복제 하나. 시드 데이터셋 id 를 함께 돌려준다."""
    path = tmp_path_factory.mktemp("legacy") / "capa_simulation.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    seed = repository.load_revision(release.revision_id, apply_global_display_order=False)
    repository.create_scenario(
        ScenarioCreate(
            scenario_name="clone",
            source_simulation_code="CODE-clone",
            source_simulation_name="clone",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="test",
        ),
        seed.tables,
        seed.preset,
        source_data=None,
        revision_tables=seed.tables,
    )
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT dataset_id, scenario_id, source_type FROM app_meta.dataset "
            "ORDER BY imported_at DESC"
        ).fetchall()
    # 복제가 더 최근이어야 이 시험이 뜻을 갖는다.
    assert [row[2] for row in rows][0] == "DUCKDB_SCENARIO_CLONE"
    seed_dataset = next(str(row[0]) for row in rows if row[1] == seed.scenario.scenario_id)
    return path, seed_dataset


def _run(monkeypatch: pytest.MonkeyPatch, database: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["compare_legacy_results.py", "--database", str(database)])
    return compare.main()


def test_a_newer_clone_dataset_is_not_taken_by_default(
    seeded_with_clone: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, seed_dataset = seeded_with_clone

    code = _run(monkeypatch, path)

    assert code == 0
    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line.startswith(f"데이터셋 {seed_dataset} · 리비전 1 ")


def test_without_a_source_dataset_it_says_so(
    seeded_with_clone: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = seeded_with_clone
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(source.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute("DELETE FROM raw_data.core_data")

    with pytest.raises(SystemExit, match="원천에서 온 데이터셋이 없습니다"):
        _run(monkeypatch, path)
