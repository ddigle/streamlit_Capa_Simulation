# Purpose: scenario preset state 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.scenario_preset_state import (
    MONTH_PICKER_KEY,
    MONTH_RANGE_KEY,
    PENDING_PRESET_KEY,
    PROCESS_SELECTION_KEY,
    SECURE_THRESHOLD_KEY,
    STANDARD_TARGET_DETAIL_LEVEL_KEY,
    STANDARD_TARGET_END_DATE_KEY,
    STANDARD_TARGET_OUTPUT_METRIC_KEY,
    STANDARD_TARGET_PROCESS_DEFAULT_KEY,
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
    STANDARD_TARGET_SHOW_DETAIL_KEY,
    STANDARD_TARGET_START_DATE_KEY,
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


def test_pending_preset_restores_standard_target_view_settings() -> None:
    test_script = """
import streamlit as st

from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

st.write(f"applied={apply_pending_scenario_preset()}")
"""
    app = AppTest.from_string(test_script)
    app.session_state[PENDING_PRESET_KEY] = ScenarioPreset(
        202608,
        202608,
        ("Process-A",),
        standard_target_start_date=date(2026, 8, 10),
        standard_target_end_date=date(2026, 8, 20),
        standard_target_show_detail=True,
        standard_target_detail_level="Stack",
        standard_target_output_metric="가용대수",
    )

    app.run()

    assert not app.exception
    assert app.session_state[STANDARD_TARGET_START_DATE_KEY] == date(2026, 8, 10)
    assert app.session_state[STANDARD_TARGET_END_DATE_KEY] == date(2026, 8, 20)
    assert app.session_state[STANDARD_TARGET_SHOW_DETAIL_KEY] is True
    assert app.session_state[STANDARD_TARGET_DETAIL_LEVEL_KEY] == "Stack"
    assert app.session_state[STANDARD_TARGET_OUTPUT_METRIC_KEY] == "가용대수"


def test_pending_preset_without_saved_dates_clears_the_session_dates() -> None:
    """날짜를 저장하지 않은 리비전은 페이지가 조회기간에서 기본값을 다시 뽑게 둔다."""
    test_script = """
import streamlit as st

from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

st.write(f"applied={apply_pending_scenario_preset()}")
"""
    app = AppTest.from_string(test_script)
    app.session_state[STANDARD_TARGET_START_DATE_KEY] = date(2025, 1, 1)
    app.session_state[STANDARD_TARGET_END_DATE_KEY] = date(2025, 1, 31)
    app.session_state[PENDING_PRESET_KEY] = ScenarioPreset(202608, 202608, ("Process-A",))

    app.run()

    assert not app.exception
    assert STANDARD_TARGET_START_DATE_KEY not in app.session_state
    assert STANDARD_TARGET_END_DATE_KEY not in app.session_state


def test_current_view_settings_are_captured_for_next_revision_only() -> None:
    """세션에서 바꾼 조회·집계 설정은 다음 리비전을 저장할 때 캡처된다(불변조건 12).

    프리셋 객체 자체는 저장 전까지 그대로이고, 계산 캐시 키인 `content_token` 도
    조회 설정 변경으로는 재발급되지 않는다.
    """
    test_script = """
import pandas as pd
import streamlit as st

from capa_simulation.scenario_preset_state import (
    STANDARD_TARGET_DETAIL_LEVEL_KEY,
    STANDARD_TARGET_END_DATE_KEY,
    STANDARD_TARGET_OUTPUT_METRIC_KEY,
    STANDARD_TARGET_SHOW_DETAIL_KEY,
    STANDARD_TARGET_START_DATE_KEY,
    apply_pending_scenario_preset,
    capture_scenario_preset,
)
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY

applied = apply_pending_scenario_preset()
restored = capture_scenario_preset({"RQ_REQB": pd.DataFrame({"공정": ["Process-A"]})})

import datetime

st.session_state[STANDARD_TARGET_START_DATE_KEY] = datetime.date(2026, 8, 11)
st.session_state[STANDARD_TARGET_END_DATE_KEY] = datetime.date(2026, 8, 21)
st.session_state[STANDARD_TARGET_SHOW_DETAIL_KEY] = False
st.session_state[STANDARD_TARGET_DETAIL_LEVEL_KEY] = "WF 구분"
st.session_state[STANDARD_TARGET_OUTPUT_METRIC_KEY] = "대당 일 Capa"

st.session_state["restored_preset"] = restored
st.session_state["captured_preset"] = capture_scenario_preset(
    {"RQ_REQB": pd.DataFrame({"공정": ["Process-A"]})}
)
st.session_state["observed_token"] = st.session_state[ACTIVE_SCENARIO_KEY]["content_token"]
"""
    app = AppTest.from_string(test_script)
    app.session_state[MONTH_RANGE_KEY] = ("2026-08", "2026-08")
    app.session_state["active_scenario"] = {
        "reference_version": 1,
        "revision": 1,
        "content_token": "token-1",
        "tables": {},
    }
    app.session_state[PENDING_PRESET_KEY] = ScenarioPreset(
        202608,
        202608,
        ("Process-A",),
        standard_target_start_date=date(2026, 8, 10),
        standard_target_end_date=date(2026, 8, 20),
        standard_target_show_detail=True,
        standard_target_detail_level="Stack",
        standard_target_output_metric="가용대수",
    )

    app.run()

    assert not app.exception
    restored_preset = app.session_state["restored_preset"]
    assert restored_preset.standard_target_start_date == date(2026, 8, 10)
    assert restored_preset.standard_target_detail_level == "Stack"
    assert restored_preset.standard_target_output_metric == "가용대수"
    captured = app.session_state["captured_preset"]
    assert captured.standard_target_start_date == date(2026, 8, 11)
    assert captured.standard_target_end_date == date(2026, 8, 21)
    assert captured.standard_target_show_detail is False
    # 상세 토글이 꺼져 위젯이 화면에 없어도 마지막 분류 수준 선택을 그대로 보존한다.
    assert captured.standard_target_detail_level == "WF 구분"
    assert captured.standard_target_output_metric == "대당 일 Capa"
    assert app.session_state["observed_token"] == "token-1"


def test_new_dataset_preset_clears_standard_target_view_settings() -> None:
    test_script = """
import pandas as pd
import streamlit as st

from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset

st.session_state["captured_preset"] = capture_full_data_scenario_preset(
    {
        "RQ_REQB": pd.DataFrame(
            {"생산계획년월": [202608], "공정": ["Process-A"]}
        )
    }
)
"""
    app = AppTest.from_string(test_script)
    app.session_state[MONTH_RANGE_KEY] = ("2026-08", "2026-08")
    app.session_state[STANDARD_TARGET_START_DATE_KEY] = date(2026, 8, 10)
    app.session_state[STANDARD_TARGET_END_DATE_KEY] = date(2026, 8, 20)
    app.session_state[STANDARD_TARGET_SHOW_DETAIL_KEY] = True
    app.session_state[STANDARD_TARGET_DETAIL_LEVEL_KEY] = "Stack"
    app.session_state[STANDARD_TARGET_OUTPUT_METRIC_KEY] = "가용대수"

    app.run()

    assert not app.exception
    preset = app.session_state["captured_preset"]
    assert preset.standard_target_start_date is None
    assert preset.standard_target_end_date is None
    assert preset.standard_target_show_detail is False
    assert preset.standard_target_detail_level == "제품정보"
    assert preset.standard_target_output_metric == "일 표준 가능량"


def test_cache_payload_round_trip_keeps_every_preset_field() -> None:
    """캐시는 프리셋을 dict 로 풀었다 되세운다.

    필드 하나가 빠져도 dataclass 는 조용히 기본값으로 채우므로 왕복으로만 잡힌다.
    """
    from datetime import date, datetime

    import pandas as pd

    from capa_simulation.persistence.cache import _snapshot_from_payload, _snapshot_to_payload
    from capa_simulation.persistence.models import (
        RevisionSummary,
        ScenarioPreset,
        ScenarioSnapshot,
        ScenarioSummary,
    )

    now = datetime(2026, 9, 11, 8, 0, 0)
    preset = ScenarioPreset(
        start_month=202608,
        end_month=202610,
        included_processes=("Process-A",),
        standard_target_processes=("Process-B",),
        standard_target_start_date=date(2026, 8, 5),
        standard_target_end_date=date(2026, 10, 20),
        standard_target_show_detail=True,
        standard_target_detail_level="Stack",
        standard_target_output_metric="가용대수",
    )
    snapshot = ScenarioSnapshot(
        scenario=ScenarioSummary(
            scenario_id="s1",
            dataset_id="d1",
            scenario_name="시나리오",
            source_simulation_code="C1",
            source_simulation_name="원천",
            source_type="builtin",
            status="active",
            active_revision_id="r1",
            active_revision_no=1,
            created_at=now,
            updated_at=now,
        ),
        revision=RevisionSummary(
            revision_id="r1",
            scenario_id="s1",
            revision_no=1,
            revision_name="리비전 1",
            parent_revision_id=None,
            note=None,
            reference_hash="h",
            created_at=now,
        ),
        preset=preset,
        tables={"RQ_PKG_PLAN": pd.DataFrame()},
    )

    restored = _snapshot_from_payload(_snapshot_to_payload(snapshot))

    assert restored.preset == preset


def test_threshold_defaults_are_seeded_only_when_the_session_is_empty(monkeypatch) -> None:
    """HOME 과 Static Capa 가 같은 칸을 쓴다. 나중에 연 화면이 앞의 선택을 덮으면 안 된다."""
    from capa_simulation import scenario_preset_state

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    state: dict[str, object] = {}
    monkeypatch.setattr(scenario_preset_state, "st", _FakeStreamlit(state))
    scenario_preset_state.seed_threshold_defaults()
    assert state[SECURE_THRESHOLD_KEY] == scenario_preset_state.DEFAULT_SECURE_THRESHOLD_PERCENT
    assert state[WARNING_THRESHOLD_KEY] == scenario_preset_state.DEFAULT_WARNING_THRESHOLD_PERCENT

    state[SECURE_THRESHOLD_KEY] = 101.0
    scenario_preset_state.seed_threshold_defaults()
    assert state[SECURE_THRESHOLD_KEY] == 101.0


def test_session_threshold_falls_back_instead_of_raising(monkeypatch) -> None:
    """결과를 읽어서 그리기만 하는 화면이 기준 한 칸 때문에 멈추면 안 된다."""
    from capa_simulation import scenario_preset_state

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    state: dict[str, object] = {}
    monkeypatch.setattr(scenario_preset_state, "st", _FakeStreamlit(state))
    assert scenario_preset_state.session_threshold(SECURE_THRESHOLD_KEY, 109.5) == 1.095

    state[SECURE_THRESHOLD_KEY] = 120.0
    assert scenario_preset_state.session_threshold(SECURE_THRESHOLD_KEY, 109.5) == 1.2

    state[SECURE_THRESHOLD_KEY] = "잘못된 값"
    assert scenario_preset_state.session_threshold(SECURE_THRESHOLD_KEY, 109.5) == 1.095
