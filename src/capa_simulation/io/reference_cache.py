"""Shared server cache for workbook reference tables."""

from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables


@st.cache_data(
    show_spinner="Excel 기준정보를 서버 캐시에 저장하는 중입니다.",
    max_entries=2,
)
def get_reference_tables(workbook_path: str) -> dict[str, pd.DataFrame]:
    """Read the workbook once per server process and return cached table copies."""
    return load_reference_tables(Path(workbook_path))


@st.cache_resource
def _reference_cache_state() -> dict[str, int]:
    return {"version": 0}


def get_reference_cache_version() -> int:
    """Return the server-wide explicit refresh generation."""
    return _reference_cache_state()["version"]


def clear_reference_tables() -> int:
    """Clear the workbook cache and increment its server-wide generation."""
    get_reference_tables.clear()
    state = _reference_cache_state()
    state["version"] += 1
    return state["version"]
