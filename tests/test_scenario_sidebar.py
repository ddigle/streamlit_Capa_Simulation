# Purpose: scenario sidebar 관련 정상·예외·회귀 동작을 검증한다.

from streamlit.testing.v1 import AppTest

from capa_simulation.components.scenario_status import (
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
)

TEST_SCRIPT = """
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import capa_simulation.components.scenario_status as target


def scenario(scenario_id, name, code, revision_id, revision_no):
    return SimpleNamespace(
        scenario_id=scenario_id,
        scenario_name=name,
        source_simulation_code=code,
        source_simulation_name=name,
        active_revision_id=revision_id,
        active_revision_no=revision_no,
    )


def revision(revision_id, scenario_id, revision_no, name):
    return SimpleNamespace(
        revision_id=revision_id,
        scenario_id=scenario_id,
        revision_no=revision_no,
        revision_name=name,
    )


SCENARIOS = [
    scenario("scenario-1", "기준안", "SIM-001", "revision-1", 1),
    scenario("scenario-2", "증산안", "SIM-002", "revision-2", 1),
]
REVISIONS = {
    "scenario-1": [revision("revision-1", "scenario-1", 1, "초기")],
    "scenario-2": [revision("revision-2", "scenario-2", 1, "초기")],
}


class FakeRepository:
    def list_scenarios(self):
        return SCENARIOS

    def list_revisions(self, scenario_id):
        return REVISIONS[scenario_id]

    def latest_official_release(self):
        return None

    def save_revision(self, scenario_id, tables, preset, **kwargs):
        st.session_state["test_saved_revision_name"] = kwargs["revision_name"]
        return SimpleNamespace(
            scenario=SCENARIOS[0],
            revision=revision("revision-3", scenario_id, 2, kwargs["revision_name"]),
            preset=preset,
            tables=tables,
        )


def load_snapshot(_database_path, revision_id):
    selected = next(
        item
        for revisions in REVISIONS.values()
        for item in revisions
        if item.revision_id == revision_id
    )
    selected_scenario = next(
        item for item in SCENARIOS if item.scenario_id == selected.scenario_id
    )
    return SimpleNamespace(
        scenario=selected_scenario,
        revision=selected,
        preset=SimpleNamespace(),
        tables={},
    )


target.get_scenario_repository = lambda _path: FakeRepository()
target.load_scenario_snapshot = load_snapshot
target.active_persisted_scenario_id = lambda: "scenario-1"
target.active_persisted_revision_id = lambda: "revision-1"
target.has_unsaved_scenario_changes = lambda: False
target.activate_persisted_snapshot = lambda snapshot: st.session_state.__setitem__(
    "test_activated_revision", snapshot.revision.revision_id
)
target.get_effective_reference_version = lambda: 1
target.get_effective_reference_tables = lambda: {
    "RQ_REQB": pd.DataFrame({"공정": ["공정 A"]}),
    "RQ_DISPLAY_ORDER": pd.DataFrame(),
}
target.ensure_active_scenario = lambda _tables, _version: {
    "reference_version": 1,
    "revision": 1,
    "tables": {},
}
target.revision_tables_for_save = lambda _active, tables: {
    "RQ_REQB": tables["RQ_REQB"].copy()
}
target.capture_scenario_preset = lambda _tables: SimpleNamespace()

target.render_scenario_controls(Path("unused.duckdb"))
"""


def test_sidebar_selects_and_loads_another_revision() -> None:
    app = AppTest.from_string(TEST_SCRIPT).run()

    assert not app.exception
    assert [widget.label for widget in app.selectbox] == ["시나리오", "리비전"]

    app = app.selectbox(key=SIDEBAR_SCENARIO_KEY).select("scenario-2").run()
    assert app.selectbox(key=SIDEBAR_REVISION_KEY).value == "revision-2"

    load_button = next(button for button in app.button if button.label == "선택 리비전 불러오기")
    app = load_button.click().run()

    assert not app.exception
    assert app.session_state["test_activated_revision"] == "revision-2"


def test_sidebar_saves_current_state_as_a_new_revision() -> None:
    app = AppTest.from_string(TEST_SCRIPT).run()

    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("사이드바 저장안").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    app = save_button.click().run()

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "사이드바 저장안"
    assert app.session_state["test_activated_revision"] == "revision-3"
