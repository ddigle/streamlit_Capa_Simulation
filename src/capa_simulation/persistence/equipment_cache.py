"""Streamlit cache boundary for the standalone equipment repository."""

from pathlib import Path

import streamlit as st

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


@st.cache_resource
def get_equipment_repository(database_path: str) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(Path(database_path))
    repository.initialize()
    return repository


def clear_equipment_repository() -> None:
    get_equipment_repository.clear()
