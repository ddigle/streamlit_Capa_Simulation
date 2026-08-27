import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.scenario_preset_state import (
    MONTH_PICKER_KEY,
    MONTH_RANGE_KEY,
    PENDING_PRESET_KEY,
    PROCESS_SELECTION_KEY,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)


def test_pending_preset_is_applied_before_shared_widgets() -> None:
    test_script = """
import streamlit as st

from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

applied = apply_pending_scenario_preset()
st.write(f"applied={applied}")
"""
    app = AppTest.from_string(test_script)
    app.session_state[PENDING_PRESET_KEY] = ScenarioPreset(
        202608,
        202712,
        ("Process-A", "Process-B"),
        secure_threshold=1.12,
        warning_threshold=0.97,
    )
    app.session_state[MONTH_PICKER_KEY] = {"start": "stale", "end": "stale"}

    app.run()

    assert not app.exception
    assert app.session_state[MONTH_RANGE_KEY] == ("2026-08", "2027-12")
    assert app.session_state[PROCESS_SELECTION_KEY] == ["Process-A", "Process-B"]
    assert app.session_state[SECURE_THRESHOLD_KEY] == pytest.approx(112.0)
    assert app.session_state[WARNING_THRESHOLD_KEY] == pytest.approx(97.0)
    assert PENDING_PRESET_KEY not in app.session_state
    assert MONTH_PICKER_KEY not in app.session_state
