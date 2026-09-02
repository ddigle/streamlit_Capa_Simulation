"""Session activation boundary for immutable DuckDB reference snapshots."""

import pandas as pd
import streamlit as st

SESSION_REFERENCE_TABLES_KEY = "persisted_reference_tables"
SESSION_REFERENCE_VERSION_KEY = "persisted_reference_version"
SESSION_DISPLAY_ORDER_VERSION_KEY = "global_display_order_version"


def get_effective_reference_tables() -> dict[str, pd.DataFrame]:
    """Return the DuckDB revision activated in this browser session."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if (
        isinstance(saved, dict)
        and saved
        and all(isinstance(frame, pd.DataFrame) for frame in saved.values())
    ):
        return saved
    raise RuntimeError(
        "활성 DuckDB 시나리오가 없습니다. 시나리오 페이지에서 공식버전을 지정하거나 "
        "저장된 리비전을 불러오세요."
    )


def get_effective_reference_version() -> int:
    saved = st.session_state.get(SESSION_REFERENCE_VERSION_KEY)
    if isinstance(saved, int) and not isinstance(saved, bool):
        return saved
    raise RuntimeError("활성 DuckDB 리비전 버전이 없습니다.")


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


def apply_global_display_order(display_order: pd.DataFrame, version: int) -> None:
    """Replace only the shared UI order in the current session without resetting edits."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if not isinstance(saved, dict) or not saved:
        raise RuntimeError("공용 표시순서를 적용할 활성 시나리오가 없습니다.")
    revised = dict(saved)
    revised["RQ_DISPLAY_ORDER"] = display_order.copy(deep=True)
    st.session_state[SESSION_REFERENCE_TABLES_KEY] = revised
    st.session_state[SESSION_DISPLAY_ORDER_VERSION_KEY] = int(version)
    st.session_state.pop("home_dashboard_figure_cache", None)


def clear_persisted_reference_tables() -> None:
    st.session_state.pop(SESSION_REFERENCE_TABLES_KEY, None)
    st.session_state.pop(SESSION_REFERENCE_VERSION_KEY, None)
    st.session_state.pop(SESSION_DISPLAY_ORDER_VERSION_KEY, None)
