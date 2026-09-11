# Purpose: application bootstrap 관련 정상·예외·회귀 동작을 검증한다.

from pathlib import Path

from streamlit.testing.v1 import AppTest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import (
    BUILTIN_SEED_MONTHS,
    BUILTIN_SEED_SOURCE_CODE,
    build_builtin_seed_dataset,
    builtin_seed_processes,
)
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.unit_capacity import calculate_unit_capacity


def test_builtin_seed_uses_exact_contract_and_builds_all_reference_tables() -> None:
    prepared = build_builtin_seed_dataset()
    expected_columns = [column.name for column in load_core_data_contract().columns]

    assert list(prepared.source_data.columns) == expected_columns
    assert len(expected_columns) == 78
    assert set(prepared.reference_tables) == {
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
        "RQ_DISPLAY_ORDER",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_MODULE",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
    }
    assert all(not table.empty for table in prepared.reference_tables.values())
    assert set(prepared.reference_tables["RQ_PKG_PLAN"]["생산계획년월"]) == set(BUILTIN_SEED_MONTHS)
    assert prepared.source_data["제품정보"].dropna().str.startswith("DEMO_").all()


def test_builtin_seed_runs_the_capacity_calculation_chain() -> None:
    tables = build_builtin_seed_dataset().reference_tables

    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required_equipment = calculate_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required_equipment)

    assert not unit_capacity.empty
    assert not required_equipment.empty
    assert not securement.empty
    assert set(securement["공정"]) == set(builtin_seed_processes())


def test_empty_store_is_seeded_published_and_idempotent(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    created = ensure_initial_scenario(repository)
    repeated = ensure_initial_scenario(repository)

    assert created.status == "created_builtin_seed"
    assert created.release is not None
    assert repeated.status == "existing_official"
    assert repeated.release == created.release
    scenarios = repository.list_scenarios()
    assert len(scenarios) == 1
    assert scenarios[0].source_simulation_code == BUILTIN_SEED_SOURCE_CODE
    assert len(repository.load_source_data(scenarios[0].scenario_id).columns) == 78


def test_streamlit_session_activates_seed_on_first_start(tmp_path: Path) -> None:
    database_path = tmp_path / "streamlit-bootstrap.duckdb"
    script = f"""
import streamlit as st

from capa_simulation.scenario_activation import (
    ACTIVE_PERSISTED_REVISION_ID_KEY,
    bootstrap_latest_official_scenario,
)

st.write(bootstrap_latest_official_scenario({str(database_path)!r}))
st.write(st.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY])
"""

    app = AppTest.from_string(script).run(timeout=30)

    assert not app.exception
    assert app.markdown[0].value == "`True`"
    assert app.session_state["active_persisted_revision_id"]
    repository = DuckDBScenarioRepository(database_path)
    assert repository.latest_official_release() is not None


def test_existing_unpublished_store_is_not_overwritten(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    prepared = build_builtin_seed_dataset()
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="사용자 시나리오",
            source_simulation_code="USER-SCENARIO-001",
            source_simulation_name="사용자 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS),
            max(BUILTIN_SEED_MONTHS),
            builtin_seed_processes(),
        ),
        source_data=prepared.source_data,
    )

    result = ensure_initial_scenario(repository)

    assert result.status == "existing_without_official"
    assert result.release is None
    scenarios = repository.list_scenarios()
    assert [scenario.scenario_id for scenario in scenarios] == [snapshot.scenario.scenario_id]
