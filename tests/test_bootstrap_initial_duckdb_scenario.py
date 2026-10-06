# Purpose: 초기 이관 CLI 가 가상 제품이 든 리비전을 플래그 없이 공식버전으로 지정하지 않는지 본다.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import (
    BUILTIN_SEED_MONTHS,
    build_builtin_seed_dataset,
    builtin_seed_processes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "bootstrap_initial_duckdb_scenario.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_initial_duckdb_scenario", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _existing_scenario_with_virtual_product(
    database_path: Path, source_code: str
) -> DuckDBScenarioRepository:
    """같은 원천 코드의 미발행 시나리오. 활성 리비전에 가상 제품 하나가 들어 있다."""
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    prepared = build_builtin_seed_dataset()
    preset = ScenarioPreset(
        start_month=min(BUILTIN_SEED_MONTHS),
        end_month=max(BUILTIN_SEED_MONTHS),
        included_processes=builtin_seed_processes(),
    )
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="초기 이관 시나리오",
            source_simulation_code=source_code,
            source_simulation_name="합성 원천",
            source_type="CSV_CORE_DATA_INITIAL_BOOTSTRAP",
            pipeline_version="test",
        ),
        prepared.reference_tables,
        preset,
        source_data=prepared.source_data,
        revision_name="r1",
    )
    repository.save_revision(
        snapshot.scenario.scenario_id,
        prepared.reference_tables,
        preset,
        revision_name="가상 제품 포함",
        parent_revision_id=snapshot.revision.revision_id,
        virtual_products=[
            {
                "product": "DEMO_VIRTUAL",
                "stack": "8H",
                "source_product": "DEMO_SOURCE",
                "source_stack": "8H",
            }
        ],
    )
    return repository


def test_existing_scenario_with_virtual_products_is_not_published_without_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """화면은 가상 제품이 든 리비전을 확인 체크 뒤에야 공식버전으로 지정한다(2026-10-06).

    CLI 의 기존 시나리오 분기가 활성 리비전을 그대로 발행하면 그 확인을 비켜 간다. 플래그 없이는
    제품 · Stack 목록을 찍고 0 이 아닌 코드로 멈추며, 발행 이력은 비어 있어야 한다.
    """
    script = _load_script()
    database_path = tmp_path / "scenario.duckdb"
    repository = _existing_scenario_with_virtual_product(database_path, script.DEFAULT_SOURCE_CODE)
    argv = [str(SCRIPT_PATH), "--database", str(database_path)]

    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as stopped:
        script.main()
    assert stopped.value.code not in (0, None)
    error = capsys.readouterr().err
    assert "가상 제품 1건" in error
    assert "DEMO_VIRTUAL · 8H" in error
    assert "--allow-virtual-products" in error
    assert repository.latest_official_release() is None

    monkeypatch.setattr(sys, "argv", [*argv, "--allow-virtual-products"])
    script.main()
    release = repository.latest_official_release()
    assert release is not None
    scenario = repository.list_scenarios()[0]
    assert release.revision_id == scenario.active_revision_id
