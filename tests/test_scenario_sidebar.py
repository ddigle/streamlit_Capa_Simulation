# Purpose: scenario sidebar 관련 정상·예외·회귀 동작을 검증한다.

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.scenario_status as target
from capa_simulation.components.capacity_gate import GateVerdict
from capa_simulation.components.scenario_status import (
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
)


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
    selected_scenario = next(item for item in SCENARIOS if item.scenario_id == selected.scenario_id)
    return SimpleNamespace(
        scenario=selected_scenario,
        revision=selected,
        preset=SimpleNamespace(),
        tables={},
    )


TEST_SCRIPT = """
from pathlib import Path

import capa_simulation.components.scenario_status as target
target.render_scenario_controls(Path("unused.duckdb"))
"""


@pytest.fixture
def sidebar_app() -> Iterator[AppTest]:
    """callback은 스크립트보다 먼저 실행되므로 모든 rerun을 같은 patch로 감싼다."""
    replacements = {
        "get_scenario_repository": lambda _path: FakeRepository(),
        "load_scenario_snapshot": load_snapshot,
        "active_persisted_scenario_id": lambda: "scenario-1",
        "active_persisted_revision_id": lambda: "revision-1",
        "has_unsaved_scenario_changes": lambda: bool(st.session_state.get("test_unsaved", False)),
        "reset_active_scenario": lambda _tables, version: st.session_state.__setitem__(
            "test_reset_to_version", version
        ),
        "activate_persisted_snapshot": lambda snapshot: st.session_state.__setitem__(
            "test_activated_revision", snapshot.revision.revision_id
        ),
        "get_effective_reference_version": lambda: 1,
        "get_effective_reference_tables": lambda: {
            "RQ_REQB": pd.DataFrame({"공정": ["공정 A"]}),
            "RQ_DISPLAY_ORDER": pd.DataFrame(),
        },
        "ensure_active_scenario": lambda _tables, _version: {
            "reference_version": 1,
            "revision": 1,
            "tables": {},
        },
        "revision_tables_for_save": lambda _active, tables: {"RQ_REQB": tables["RQ_REQB"].copy()},
        "capture_scenario_preset": lambda _tables: SimpleNamespace(),
        # 저장 검사는 따로 검증한다(`test_capacity_gate.py`). 여기서는 판정을 세션에서 읽어
        # 화면이 그 판정대로 움직이는지만 본다.
        "revision_save_verdict": lambda *_args: st.session_state.get(
            "test_save_verdict", GateVerdict(True)
        ),
    }
    originals = {name: getattr(target, name) for name in replacements}
    try:
        with patch.multiple(target, **replacements):
            yield AppTest.from_string(TEST_SCRIPT)
    finally:
        # 테스트 실패와 st.rerun 모두 원본 복원을 건너뛰어 다음 AppTest를 오염시키면 안 된다.
        for name, original in originals.items():
            assert getattr(target, name) is original, name


def test_sidebar_selects_and_loads_another_revision(sidebar_app: AppTest) -> None:
    app = sidebar_app.run()

    assert not app.exception
    assert [widget.label for widget in app.selectbox] == ["시나리오", "리비전"]

    app = app.selectbox(key=SIDEBAR_SCENARIO_KEY).select("scenario-2").run()
    assert app.selectbox(key=SIDEBAR_REVISION_KEY).value == "revision-2"

    # 라벨이 짧다. 무엇을 불러오는지는 바로 위 두 선택 상자가 말하고, 이 버튼은 「저장」
    # 과 한 줄에 반씩 서므로 긴 라벨이 들어가지 않는다.
    load_button = next(button for button in app.button if button.label == "불러오기")
    app = load_button.click().run()

    assert not app.exception
    assert app.session_state["test_activated_revision"] == "revision-2"


def test_sidebar_saves_current_state_as_a_new_revision(sidebar_app: AppTest) -> None:
    app = sidebar_app.run()

    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("사이드바 저장안").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    app = save_button.click().run()

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "사이드바 저장안"
    assert app.session_state["test_activated_revision"] == "revision-3"


def test_discarding_edits_lives_in_the_scenario_box_only_when_there_are_edits(
    sidebar_app: AppTest,
) -> None:
    """「편집 되돌리기」는 모든 화면의 편집을 버리는 시나리오 단위 동작이다.

    본문 맨 위의 「활성 시나리오 · 수정본 N · 전체 입력 원본으로 초기화」 줄을 없애고 이
    상자로 옮겼다(2026-09-29 사용자 결정). 버릴 것이 없으면 서지 않는다.
    """
    app = sidebar_app.run()
    assert "sidebar_reset_active_scenario" not in {button.key for button in app.button}

    app.session_state["test_unsaved"] = True
    app.run()
    app.button(key="sidebar_reset_active_scenario").click().run()

    assert not app.exception
    assert app.session_state["test_reset_to_version"] == 1
    assert "저장하지 않은 편집을 버렸습니다." in {item.value for item in app.success}


def _save(app: AppTest, name: str) -> AppTest:
    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value(name).run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    return save_button.click().run()


def test_a_save_the_gate_refuses_writes_nothing(sidebar_app: AppTest) -> None:
    """편집이 계산을 깨뜨렸으면 저장하지 않고 그 이유를 그 자리에서 말한다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _save(app.run(), "깨진 저장안")

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    assert any("이번 편집이 깨뜨린" in error.value for error in app.error)


def test_a_save_with_an_old_error_is_kept_and_warned(sidebar_app: AppTest) -> None:
    """편집 전부터 있던 오류는 저장을 막지 않는다. 대신 발행이 막힌다고 저장 뒤에 알린다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(True, "공식버전으로 지정할 수 없습니다")
    app = _save(app.run(), "고치는 중")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "고치는 중"
    assert any("공식버전으로 지정할 수 없습니다" in warning.value for warning in app.warning)
