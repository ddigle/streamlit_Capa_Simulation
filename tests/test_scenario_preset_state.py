# Purpose: scenario preset state 관련 정상·예외·회귀 동작을 검증한다.

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.scenario_preset_state import (
    MONTH_PICKER_KEY,
    MONTH_RANGE_KEY,
    PENDING_PRESET_KEY,
    PROCESS_SELECTION_KEY,
    SECURE_THRESHOLD_KEY,
    STANDARD_TARGET_PROCESS_DEFAULT_KEY,
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
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
        standard_target_processes=("Process-B",),
    )
    app.session_state[MONTH_PICKER_KEY] = {"start": "stale", "end": "stale"}

    app.run()

    assert not app.exception
    assert app.session_state[MONTH_RANGE_KEY] == ("2026-08", "2027-12")
    assert app.session_state[PROCESS_SELECTION_KEY] == ["Process-A", "Process-B"]
    assert app.session_state[SECURE_THRESHOLD_KEY] == pytest.approx(112.0)
    assert app.session_state[WARNING_THRESHOLD_KEY] == pytest.approx(97.0)
    assert app.session_state[STANDARD_TARGET_PROCESS_DEFAULT_KEY] == ["Process-B"]
    assert app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] == ["Process-B"]
    assert PENDING_PRESET_KEY not in app.session_state
    assert MONTH_PICKER_KEY not in app.session_state


def test_current_standard_target_filter_is_captured_for_next_revision() -> None:
    test_script = """
import pandas as pd
import streamlit as st

from capa_simulation.scenario_preset_state import capture_scenario_preset

st.session_state["captured_preset"] = capture_scenario_preset(
    {"RQ_REQB": pd.DataFrame({"공정": ["Process-A", "Process-B"]})}
)
"""
    app = AppTest.from_string(test_script)
    app.session_state[MONTH_RANGE_KEY] = ("2026-08", "2027-12")
    app.session_state[PROCESS_SELECTION_KEY] = ["Process-A", "Process-B"]
    app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] = ["Process-B"]

    app.run()

    assert not app.exception
    assert app.session_state["captured_preset"].standard_target_processes == ("Process-B",)


def test_new_dataset_preset_activates_every_month_and_process() -> None:
    test_script = """
import pandas as pd
import streamlit as st

from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset

st.session_state["captured_preset"] = capture_full_data_scenario_preset(
    {
        "RQ_PKG_PLAN": pd.DataFrame({"생산계획년월": [202607, 202612]}),
        "RQ_REQB": pd.DataFrame(
            {
                "생산계획년월": [202608, 202712, 202712],
                "공정": ["Process-B", "Process-A", "Process-B"],
            }
        ),
    }
)
"""
    app = AppTest.from_string(test_script)
    app.session_state[MONTH_RANGE_KEY] = ("2026-08", "2026-12")
    app.session_state[PROCESS_SELECTION_KEY] = []
    app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] = ["Process-B"]

    app.run()

    assert not app.exception
    preset = app.session_state["captured_preset"]
    assert (preset.start_month, preset.end_month) == (202607, 202712)
    assert preset.included_processes == ("Process-A", "Process-B")
    assert preset.standard_target_processes == ()


def test_threshold_keys_and_defaults_have_one_definition() -> None:
    """판정 기준 키와 기본값이 페이지마다 다시 선언되지 않는지 지킨다.

    HOME 사이드바와 Static Capa 본문의 컨트롤은 같은 세션 키를 공유한다. 어느 한쪽이
    문자열이나 기본값을 따로 적어 두면 상수를 바꿔도 그쪽만 조용히 옛 값에 남는다.
    """
    from pathlib import Path

    from capa_simulation.scenario_preset_state import (
        DEFAULT_SECURE_THRESHOLD_PERCENT,
        DEFAULT_WARNING_THRESHOLD_PERCENT,
        SECURE_THRESHOLD_KEY,
        WARNING_THRESHOLD_KEY,
    )

    owner = Path(__file__).resolve().parents[1] / "src/capa_simulation/scenario_preset_state.py"
    literals = (
        f'"{SECURE_THRESHOLD_KEY}"',
        f'"{WARNING_THRESHOLD_KEY}"',
        str(DEFAULT_SECURE_THRESHOLD_PERCENT),
        str(DEFAULT_WARNING_THRESHOLD_PERCENT),
    )
    pages = sorted((Path(__file__).resolve().parents[1] / "app_pages").glob("*.py"))
    offenders = [
        f"{page.name}: {literal}"
        for page in pages
        for literal in literals
        if literal in page.read_text(encoding="utf-8")
    ]

    assert not offenders, f"{owner.name} 의 상수를 import 하세요: {offenders}"
