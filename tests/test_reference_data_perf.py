# Purpose: 기준 정보가 닫힌 탭의 표를 건너뛰어도 같은 값을 보이고 내용이 바뀌면 다시 만드는지 본다.

"""기준 정보 rerun 비용 줄이기의 회귀 검사.

닫힌 탭의 표(STEP 경로표·편집 기간 조각·설비대수 블록)를 건너뛰어도 **보이는 값은 고치기 전과
같아야** 하고, 적용·리비전 전환으로 내용이 바뀌면 **다시 만들어야** 한다. 화면 픽스처는
`test_reference_data_page` 의 것을 그대로 쓰고, 그 위에 무엇을 몇 번 만들었는지 적는 탐침만 얹는다.
"""

from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    REAL_APPLY_TEST_SCRIPT,
    REF_TAB,
    TEST_SCRIPT,
    TWO_PROCESS_TEST_SCRIPT,
    _add_step,
    _edit_and_apply,
    _frame_with_column,
    _real_apply,
)

from capa_simulation.services.route_step_editor import route_step_tables

DIALOG_KEY = "reference_data_open_dialog"
STEP_SUMMARY_COLUMNS = {
    "생산계획년월": "월",
    "Area_Name": "Area",
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
}

# 회차마다 페이지가 자른 표 이름과 STEP 경로표를 부른 횟수·입력을 세션에 적는다. 페이지는 두
# 함수를 exec 때 모듈에서 집으므로 모듈 속성을 갈아끼우면 탐침을 집는다.
_PROBE = """
import capa_simulation.scenario_state as _probe_state

st.session_state["test_sliced_tables"] = []
_probe_original_month_table = _probe_state.scenario_month_table
_probe_original_route_tables = simulation_cache.get_route_step_tables


def _probe_month_table(scenario, table_name, start, end):
    st.session_state["test_sliced_tables"].append(table_name)
    return _probe_original_month_table(scenario, table_name, start, end)


def _probe_route_tables(cache_key, *, _upeh, _reqb):
    st.session_state["test_route_step_calls"] = (
        st.session_state.get("test_route_step_calls", 0) + 1
    )
    st.session_state["test_route_step_inputs"] = (cache_key, _upeh.copy(), _reqb.copy())
    return _probe_original_route_tables(cache_key, _upeh=_upeh, _reqb=_reqb)


_probe_state.scenario_month_table = _probe_month_table
simulation_cache.get_route_step_tables = _probe_route_tables
"""
_PROBE_RESTORE = (
    "    _probe_state.scenario_month_table = _probe_original_month_table\n"
    "    simulation_cache.get_route_step_tables = _probe_original_route_tables\n"
)
_TRY_ANCHOR = "\ntry:\n    # `file_name`"
_FINALLY_ANCHOR = "    st.download_button = original_download_button\n"


def _probed(script: str, token: str) -> str:
    """탐침을 얹은 스크립트. 캐시는 프로세스 전역이라 내용 토큰도 테스트마다 가른다."""
    assert script.count(_TRY_ANCHOR) == 1
    assert script.count(_FINALLY_ANCHOR) == 1
    probed = script.replace(_TRY_ANCHOR, "\n" + _PROBE + _TRY_ANCHOR, 1).replace(
        _FINALLY_ANCHOR, _FINALLY_ANCHOR + _PROBE_RESTORE, 1
    )
    for old in (
        '"test-capacity-standards-page"',
        '"test-capacity-real-apply-page"',
        '"test-capacity-two-process-page"',
    ):
        probed = probed.replace(old, f'"{token}"')
    return probed


def _route_calls(app: AppTest) -> int:
    key = "test_route_step_calls"
    return int(app.session_state[key]) if key in app.session_state else 0


def _sliced(app: AppTest) -> list[str]:
    return list(app.session_state["test_sliced_tables"])


def _open_tab(app: AppTest, name: str) -> AppTest:
    app.session_state["reference_data_active_tab"] = REF_TAB[name]
    app.run()
    assert not app.exception
    return app


def _displayed_summary(app: AppTest) -> pd.DataFrame:
    return _frame_with_column(app, "STEP 수").reset_index(drop=True)


def _expected_summary(app: AppTest) -> pd.DataFrame:
    """페이지가 이 회차에 넘긴 조각으로 경로표를 **새로** 계산해 화면 표 꼴로 바꾼다."""
    _key, upeh, reqb = app.session_state["test_route_step_inputs"]
    summary, _catalog = route_step_tables(upeh, reqb)
    return summary.rename(columns=STEP_SUMMARY_COLUMNS).reset_index(drop=True)


def _route_processes(app: AppTest) -> list[str]:
    """STEP 팝업 경로 상자의 줄마다 공정(글자의 첫 칸)."""
    return [
        str(option).split(" · ")[0] for option in app.selectbox(key="capacity_step_route").options
    ]


# ---------------------------------------------------------------- R1 STEP 경로표


def test_step_route_tables_are_built_only_while_the_step_tab_or_popup_is_open() -> None:
    """STEP 경로표와 `RQ_REQB` 조각은 STEP 탭이 보이거나 STEP 팝업이 열린 회차에만 만든다."""
    app = AppTest.from_string(_probed(TEST_SCRIPT, "test-ref-perf-step-gate"), default_timeout=60)
    app.run()
    assert not app.exception
    assert _route_calls(app) == 0
    assert "RQ_REQB" not in _sliced(app)
    assert "open_capacity_step_dialog" not in {button.key for button in app.button}

    app = _open_tab(app, "효율")
    assert _route_calls(app) == 0
    assert "RQ_REQB" not in _sliced(app)

    app = _open_tab(app, "STEP 구성")
    assert _route_calls(app) == 1
    assert "RQ_REQB" in _sliced(app)
    assert "open_capacity_step_dialog" in {button.key for button in app.button}

    app.button(key="open_capacity_step_dialog").click().run()
    assert not app.exception
    assert _route_calls(app) == 2
    assert app.selectbox(key="capacity_step_route").options

    # 팝업을 닫고 다른 탭으로 가면 다시 만들지 않는다.
    del app.session_state[DIALOG_KEY]
    app = _open_tab(app, "UPEH")
    assert _route_calls(app) == 2
    assert "RQ_REQB" not in _sliced(app)


def test_the_step_summary_is_the_route_table_of_this_runs_slices() -> None:
    """화면의 STEP 요약은 이 회차 활성 시나리오 조각으로 새로 계산한 경로표와 값이 같다."""
    app = AppTest.from_string(_probed(TEST_SCRIPT, "test-ref-perf-step-same"), default_timeout=60)
    app = _open_tab(app, "STEP 구성")

    displayed = _displayed_summary(app)
    pd.testing.assert_frame_equal(displayed, _expected_summary(app), check_dtype=False)
    assert displayed["STEP 수"].tolist() == [1]
    # 조각은 적용 기간(2026-08)으로 자른 `RQ_REQB` 다.
    key, _upeh, reqb = app.session_state["test_route_step_inputs"]
    assert set(reqb["생산계획년월"]) == {202608}
    assert key[1] == "test-ref-perf-step-same"


def test_a_step_change_rebuilds_the_route_tables_with_the_new_token() -> None:
    """STEP 을 더하면 내용 토큰이 바뀌고, STEP 탭은 새 토큰으로 다시 만든 경로표를 보인다."""
    app = AppTest.from_string(
        _probed(REAL_APPLY_TEST_SCRIPT, "test-ref-perf-step-rebuild"), default_timeout=60
    ).run()
    app = _open_tab(app, "STEP 구성")
    first_key = app.session_state["test_route_step_inputs"][0]
    assert _displayed_summary(app)["STEP 수"].tolist() == [1]

    app = _add_step(app, "2A", "P200")
    app.run()
    assert not app.exception
    new_key = app.session_state["test_route_step_inputs"][0]
    assert new_key != first_key
    displayed = _displayed_summary(app)
    assert displayed["STEP 수"].tolist() == [2]
    pd.testing.assert_frame_equal(displayed, _expected_summary(app), check_dtype=False)


def test_an_apply_on_another_tab_is_seen_when_the_step_tab_opens() -> None:
    """STEP 탭이 닫힌 채 다른 탭에서 적용해도, 나중에 STEP 탭을 열면 새 내용으로 계산한다.

    Process-A 의 UPEH 칸을 비워 적용하면 그 달 경로가 없어진다 — 팝업의 경로 목록에서 빠져야 한다.
    """
    script = _real_apply(
        TWO_PROCESS_TEST_SCRIPT, "test-capacity-two-process-page", "test-capacity-two-process-page"
    )
    app = AppTest.from_string(
        _probed(script, "test-ref-perf-step-after-apply"), default_timeout=60
    ).run()
    app = _open_tab(app, "STEP 구성")
    app.button(key="open_capacity_step_dialog").click().run()
    assert _route_processes(app) == ["Process-A", "Process-B"]
    del app.session_state[DIALOG_KEY]
    calls_before = _route_calls(app)

    app = _open_tab(app, "UPEH")
    app = _edit_and_apply(app, "capa_upeh_editor", "202608", None)
    assert not app.exception
    assert [error.value for error in app.error] == []
    # 닫힌 STEP 탭의 경로표는 적용 회차에도 만들지 않는다.
    assert _route_calls(app) == calls_before

    app = _open_tab(app, "STEP 구성")
    assert _route_calls(app) == calls_before + 1
    pd.testing.assert_frame_equal(
        _displayed_summary(app), _expected_summary(app), check_dtype=False
    )
    app.button(key="open_capacity_step_dialog").click().run()
    assert not app.exception
    assert _route_processes(app) == ["Process-B"]


def test_the_step_flash_shows_once_in_the_step_tab() -> None:
    """STEP 추가 알림은 STEP 탭에 한 번 뜨고, 다음 회차에는 남지 않는다."""
    app = AppTest.from_string(
        _probed(REAL_APPLY_TEST_SCRIPT, "test-ref-perf-step-flash"), default_timeout=60
    ).run()
    app = _add_step(app, "2A", "P200")
    assert any("STEP을 추가했습니다" in item.value for item in app.success)
    app.run()
    assert not any("STEP을 추가했습니다" in item.value for item in app.success)
