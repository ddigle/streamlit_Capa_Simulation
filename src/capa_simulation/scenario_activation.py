# Purpose: Atomically activate a persisted scenario revision in the current browser session.

"""Atomically activate a persisted scenario revision in the current browser session."""

from __future__ import annotations

from typing import cast

import streamlit as st

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.io.reference_cache import (
    activate_persisted_reference_tables,
    clear_persisted_reference_tables,
)
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.scenario_preset_state import queue_scenario_preset
from capa_simulation.scenario_state import (
    ACTIVE_SCENARIO_KEY,
    ActiveScenario,
    activate_scenario_tables,
    clear_active_scenario,
)

ACTIVE_PERSISTED_SCENARIO_ID_KEY = "active_persisted_scenario_id"
ACTIVE_PERSISTED_REVISION_ID_KEY = "active_persisted_revision_id"
ACTIVE_PERSISTED_SESSION_REVISION_KEY = "active_persisted_session_revision"
OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY = "official_scenario_bootstrap_attempted"

_STALE_UI_KEYS = (
    "load_conversion_inputs",
    "unit_capacity_result",
    "capacity_standards_inputs",
    "load_conversion_source_token",
    "capacity_standards_source_token",
    "home_dashboard_figure_cache",
)


def activate_persisted_snapshot(snapshot: ScenarioSnapshot) -> ActiveScenario:
    """Publish tables and queue the preset before the next app-level widget render."""
    version = activate_persisted_reference_tables(
        snapshot.tables,
        snapshot.revision.revision_id,
    )
    active = activate_scenario_tables(
        snapshot.tables,
        reference_version=version,
        revision=snapshot.revision.revision_no,
    )
    st.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = snapshot.scenario.scenario_id
    st.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = snapshot.revision.revision_id
    st.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = active["revision"]
    for key in _STALE_UI_KEYS:
        st.session_state.pop(key, None)
    queue_scenario_preset(snapshot.preset)
    return active


def bootstrap_latest_official_scenario(database_path: str) -> bool:
    """Activate the latest official revision once for a new browser session."""
    if active_persisted_revision_id() is not None:
        return False
    if st.session_state.get(OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY) is True:
        return False
    repository = get_scenario_repository(database_path)
    bootstrap = ensure_initial_scenario(repository)
    release = bootstrap.release
    if release is None:
        st.session_state[OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY] = True
        return False
    snapshot = load_scenario_snapshot(database_path, release.revision_id)
    activate_persisted_snapshot(snapshot)
    st.session_state[OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY] = True
    return True


def clear_persisted_scenario_activation() -> None:
    clear_persisted_reference_tables()
    clear_active_scenario()
    for key in (
        ACTIVE_PERSISTED_SCENARIO_ID_KEY,
        ACTIVE_PERSISTED_REVISION_ID_KEY,
        ACTIVE_PERSISTED_SESSION_REVISION_KEY,
        OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY,
        *_STALE_UI_KEYS,
    ):
        st.session_state.pop(key, None)


def active_persisted_scenario_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_SCENARIO_ID_KEY)
    return value if isinstance(value, str) else None


def active_persisted_revision_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_REVISION_ID_KEY)
    return value if isinstance(value, str) else None


def has_unsaved_scenario_changes() -> bool:
    saved_revision = st.session_state.get(ACTIVE_PERSISTED_SESSION_REVISION_KEY)
    current = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if not isinstance(saved_revision, int) or not isinstance(current, dict):
        return False
    scenario = cast(ActiveScenario, current)
    return scenario["revision"] != saved_revision
