"""Streamlit cache boundary for the shared DuckDB repository configuration."""

from pathlib import Path

import streamlit as st

from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository


@st.cache_resource
def get_scenario_repository(database_path: str) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    return repository


@st.cache_data(show_spinner=False)
def load_scenario_snapshot(database_path: str, revision_id: str) -> ScenarioSnapshot:
    """Share one immutable revision snapshot across browser sessions."""
    return get_scenario_repository(database_path).load_revision(revision_id)


def clear_scenario_repository() -> None:
    load_scenario_snapshot.clear()
    get_scenario_repository.clear()
