from streamlit.testing.v1 import AppTest

from capa_simulation.components.scenario_selector_demo import (
    ACTIVE_REVISION_KEY,
    ACTIVE_SCENARIO_KEY,
    CANDIDATE_REVISION_KEY,
    CANDIDATE_SCENARIO_KEY,
)


def test_demo_selector_changes_only_demo_session_state() -> None:
    test_script = """
import streamlit as st

from capa_simulation.components.scenario_selector_demo import render_scenario_selector_demo

render_scenario_selector_demo()
"""
    app = AppTest.from_string(test_script)

    app.run()

    assert not app.exception
    assert len(app.selectbox) == 2
    assert app.session_state[ACTIVE_SCENARIO_KEY] == "demo-operations"
    assert app.session_state[ACTIVE_REVISION_KEY] == "demo-operations-r3"
    assert app.button[0].disabled

    app.selectbox[0].select("demo-expansion").run()

    assert app.session_state[CANDIDATE_SCENARIO_KEY] == "demo-expansion"
    assert app.session_state[CANDIDATE_REVISION_KEY] == "demo-expansion-r2"
    assert not app.button[0].disabled

    app.selectbox[1].select("demo-expansion-r1").run()
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state[ACTIVE_SCENARIO_KEY] == "demo-expansion"
    assert app.session_state[ACTIVE_REVISION_KEY] == "demo-expansion-r1"
    assert "active_scenario" not in app.session_state
    assert "active_persisted_scenario_id" not in app.session_state
    assert "active_persisted_revision_id" not in app.session_state
