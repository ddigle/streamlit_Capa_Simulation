"""Shared server cache for workbook reference tables."""

from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables

SESSION_REFERENCE_TABLES_KEY = "persisted_reference_tables"
SESSION_REFERENCE_VERSION_KEY = "persisted_reference_version"


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


def get_effective_reference_tables(workbook_path: str) -> dict[str, pd.DataFrame]:
    """Return a loaded DuckDB scenario snapshot or fall back to the cached workbook."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if (
        isinstance(saved, dict)
        and saved
        and all(isinstance(frame, pd.DataFrame) for frame in saved.values())
    ):
        return saved
    return get_reference_tables(workbook_path)


def get_effective_reference_version() -> int:
    saved = st.session_state.get(SESSION_REFERENCE_VERSION_KEY)
    if isinstance(saved, int) and not isinstance(saved, bool):
        return saved
    return get_reference_cache_version()


def has_persisted_reference_tables() -> bool:
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    return (
        isinstance(saved, dict)
        and bool(saved)
        and all(isinstance(frame, pd.DataFrame) for frame in saved.values())
    )


def activate_persisted_reference_tables(
    reference_tables: dict[str, pd.DataFrame],
    revision_id: str,
) -> int:
    """Publish one immutable DB snapshot as this browser session's reference source."""
    if not reference_tables or not all(
        isinstance(frame, pd.DataFrame) for frame in reference_tables.values()
    ):
        raise ValueError("활성화할 DuckDB 기준정보가 올바르지 않습니다.")
    version = int(revision_id.replace("-", "")[:15], 16)
    st.session_state[SESSION_REFERENCE_TABLES_KEY] = reference_tables
    st.session_state[SESSION_REFERENCE_VERSION_KEY] = version
    return version


def clear_persisted_reference_tables() -> None:
    st.session_state.pop(SESSION_REFERENCE_TABLES_KEY, None)
    st.session_state.pop(SESSION_REFERENCE_VERSION_KEY, None)


def clear_reference_tables() -> int:
    """Clear the workbook cache and increment its server-wide generation."""
    get_reference_tables.clear()
    clear_persisted_reference_tables()
    state = _reference_cache_state()
    state["version"] += 1
    return state["version"]
