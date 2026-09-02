"""Streamlit cache boundary for the shared DuckDB repository configuration."""

from pathlib import Path

import streamlit as st

from capa_simulation.persistence.models import GlobalDisplayOrder, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository


@st.cache_resource
def get_scenario_repository(database_path: str) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    repository.initialize_global_display_order(load_builtin_display_order())
    return repository


@st.cache_data(show_spinner=False, max_entries=32)
def load_scenario_snapshot(database_path: str, revision_id: str) -> ScenarioSnapshot:
    """Share one immutable revision with the current global display-order profile."""
    return get_scenario_repository(database_path).load_revision(revision_id)


@st.cache_data(show_spinner=False, max_entries=4)
def load_global_display_order(database_path: str) -> GlobalDisplayOrder:
    """Share the current global display-order profile across browser sessions."""
    return get_scenario_repository(database_path).load_global_display_order()


def clear_global_display_order_cache() -> None:
    load_global_display_order.clear()
    load_scenario_snapshot.clear()


def clear_scenario_repository() -> None:
    load_global_display_order.clear()
    load_scenario_snapshot.clear()
    get_scenario_repository.clear()
