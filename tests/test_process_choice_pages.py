# Purpose: 다른 화면의 공정 선택 상자가 겹친 표시명을 가르고 글자가 바뀌어도 원본을 지키는지 본다.

"""산출 결과·표준 목표(공정 필터·로직 분석)·표준 대비 재공·Dynamic Capa 상위·실적 화면의 공정 상자.

Streamlit 1.63 의 selectbox·multiselect 는 브라우저와 값을 **보이는 글자**(`format_func` 결과)로
주고받는다. 표시명이 다른 공정의 원본 이름과 같으면 고른 것과 다른 공정이 세션에 들었고, 글자가
회차마다 바뀌면(겹침이 생기거나 Admin 에서 표시명을 바꿈) 브라우저가 옛 글자를 되보내 다음 조작에
조용히 다른 값이 됐다. 상자마다 `ProcessLabels.unique_format_func` 로 글자를 가르고 위젯 앞에서 매
회차 잡은 값을 다시 적는다(2026-10-10 다른 화면 후속, 가용설비 현황과 같은 처방). 일반
`AppTest.run()` 은 회차마다 세션 값으로 글자를 다시 만들어 보내 글자가 바뀌는 결함을 못 보므로
글자를 들고 다니는 `BrowserChoice` 로 잰다.

표시명은 테스트마다 세션 칸(`test_rename_rules` 등)으로 바꾼다 — Admin `Proc Rename` 저장처럼 회차
사이에 프로필이 바뀌는 길이다.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest
from test_reference_data_page import RENAMED_TWO_PROCESS_RESULT_SCRIPT
from test_reference_integrity_page import RENAMED_TEST_SCRIPT as INTEGRITY_RENAMED_SCRIPT
from test_standard_target_capa_page import RENAMED_TEST_SCRIPT as STANDARD_RENAMED_SCRIPT
from test_wip_status_page import TEST_SCRIPT as WIP_SCRIPT
from widget_browser import BrowserChoice

from capa_simulation.scenario_preset_state import STANDARD_TARGET_PROCESS_SELECTION_KEY


def _swap(script: str, old: str, new: str) -> str:
    assert old in script, old
    return script.replace(old, new, 1)


# ------------------------------------------------------------------ 산출 결과 · 대당 Capa 공정 필터
CALC_SCRIPT = _swap(
    RENAMED_TWO_PROCESS_RESULT_SCRIPT,
    'rename_rules = pd.DataFrame([("Process-A", "가공")], columns=["공정", "표시명"])',
    "rename_rules = pd.DataFrame(\n"
    '        st.session_state.get("test_rename_rules", [("Process-A", "가공")]),\n'
    '        columns=["공정", "표시명"],\n'
    "    )",
)
CALC_FILTER_KEY = "unit_capacity_process_filter"


def test_calculation_result_filter_splits_a_colliding_display_name() -> None:
    """Process-A 의 표시명이 원본 Process-B 와 같다 — 「Process-B (Process-A)」 로 가른다."""
    app = AppTest.from_string(CALC_SCRIPT, default_timeout=60)
    app.session_state["test_rename_rules"] = [("Process-A", "Process-B")]
    browser = BrowserChoice(app, "multiselect", CALC_FILTER_KEY)
    browser.start()
    assert not app.exception
    # 차례는 표시순서 그대로다(이 상자에는 「보이는 글자순」 규칙이 없었다).
    assert browser.options() == ["Process-B (Process-A)", "Process-B"]

    browser.pick(["Process-B (Process-A)"])
    browser.run()

    assert not app.exception
    assert app.session_state[CALC_FILTER_KEY] == ["Process-A"]


def test_calculation_result_filter_keeps_its_value_when_the_display_name_changes() -> None:
    """「가공」(= Process-A)을 고른 뒤 Admin 이 표시명을 Process-B 로 바꾸면 글자가 바뀐다 — 잡은
    값은 Process-A 그대로이고 브라우저는 새 글자를 받는다."""
    app = AppTest.from_string(CALC_SCRIPT, default_timeout=60)
    browser = BrowserChoice(app, "multiselect", CALC_FILTER_KEY)
    browser.start()
    browser.pick(["가공"])
    browser.run()
    assert app.session_state[CALC_FILTER_KEY] == ["Process-A"]

    app.session_state["test_rename_rules"] = [("Process-A", "Process-B")]
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[CALC_FILTER_KEY] == ["Process-A"]
    assert browser.wire == ["Process-B (Process-A)"]


# ------------------------------------------------------- 표준 목표 · 공정 필터 · 로직 분석
STANDARD_SCRIPT = _swap(
    STANDARD_RENAMED_SCRIPT,
    '        [("Process-A", "가공"), ("Pre B/D", "선다이싱")],\n',
    '        st.session_state.get("test_rename_rules", [("Process-A", "가공")]),\n',
)
LOGIC_PROCESS_KEY = "standard_target_logic_process"


def test_standard_target_filter_splits_a_colliding_display_name() -> None:
    app = AppTest.from_string(STANDARD_SCRIPT, default_timeout=60)
    app.session_state["test_rename_rules"] = [("Process-A", "Process-B")]
    browser = BrowserChoice(app, "multiselect", STANDARD_TARGET_PROCESS_SELECTION_KEY)
    browser.start()
    assert not app.exception
    assert browser.options() == ["Process-B (Process-A)", "Process-B"]

    browser.pick(["Process-B (Process-A)"])
    browser.run()

    assert not app.exception
    assert app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] == ["Process-A"]


def test_standard_target_filter_keeps_its_value_when_the_display_name_changes() -> None:
    app = AppTest.from_string(STANDARD_SCRIPT, default_timeout=60)
    browser = BrowserChoice(app, "multiselect", STANDARD_TARGET_PROCESS_SELECTION_KEY)
    browser.start()
    browser.pick(["가공"])
    browser.run()
    assert app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] == ["Process-A"]

    app.session_state["test_rename_rules"] = [("Process-A", "Process-B")]
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] == ["Process-A"]
    assert browser.wire == ["Process-B (Process-A)"]


def _logic_analysis(rules: list[tuple[str, str]]) -> tuple[AppTest, BrowserChoice]:
    """로직 분석을 열고 26-W32 를 고른 화면. 공정 상자를 브라우저처럼 든다."""
    app = AppTest.from_string(STANDARD_SCRIPT, default_timeout=60)
    app.session_state["test_rename_rules"] = rules
    app.run()
    app.segmented_control(key="standard_target_output_metric").set_value("로직 분석").run()
    app.selectbox(key="standard_target_logic_weeknum").set_value("26-W32").run()
    assert not app.exception
    browser = BrowserChoice(app, "selectbox", LOGIC_PROCESS_KEY)
    browser.sync()
    return app, browser


def test_logic_analysis_process_splits_a_colliding_display_name() -> None:
    """이 주의 선택지는 Process-A 하나지만 글자는 공정 전체로 가른다 — 주차를 옮겨도 덜 흔들린다."""
    app, browser = _logic_analysis([("Process-A", "Process-B")])
    assert browser.options() == ["Process-B (Process-A)"]

    browser.pick("Process-B (Process-A)")
    browser.run()

    assert not app.exception
    assert app.session_state[LOGIC_PROCESS_KEY] == "Process-A"


def test_logic_analysis_process_keeps_its_value_when_the_display_name_changes() -> None:
    """고른 「가공」 이 Admin 저장으로 「Process-B (Process-A)」 가 돼도 Process-A 그대로다 — 매
    회차 다시 적지 않으면 브라우저의 옛 글자가 선택지에 없어 선택이 빠졌다."""
    app, browser = _logic_analysis([("Process-A", "가공")])
    browser.pick("가공")
    browser.run()
    assert app.session_state[LOGIC_PROCESS_KEY] == "Process-A"

    app.session_state["test_rename_rules"] = [("Process-A", "Process-B")]
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[LOGIC_PROCESS_KEY] == "Process-A"
    assert browser.wire == "Process-B (Process-A)"


# ------------------------------------------------------------------ 표준 대비 재공 · 공정(폼 안)
WIP_SCRIPT_WITH_LABELS = _swap(
    WIP_SCRIPT,
    "process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels()",
    "process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels(\n"
    '    version=1, labels=st.session_state.get("test_labels", {})\n'
    ")",
)
WIP_FILTER_KEY = "wip_status_process_filter"


def _submit_wip(app: AppTest) -> None:
    """폼의 「조건 적용」 을 누른다 — 폼 안 상자의 글자는 제출할 때 브라우저가 보낸다."""
    next(button for button in app.button if button.label.endswith("조건 적용")).click()


def test_wip_status_filter_splits_a_colliding_display_name() -> None:
    app = AppTest.from_string(WIP_SCRIPT_WITH_LABELS, default_timeout=60)
    app.session_state["test_labels"] = {"T-Process": "P-Process"}
    browser = BrowserChoice(app, "multiselect", WIP_FILTER_KEY)
    browser.start()
    assert not app.exception
    assert browser.options() == ["P-Process", "P-Process (T-Process)"]

    browser.pick(["P-Process (T-Process)"])
    _submit_wip(app)
    browser.run()

    assert not app.exception
    assert app.session_state[WIP_FILTER_KEY] == ["T-Process"]


def test_wip_status_filter_keeps_its_value_when_the_display_name_changes() -> None:
    app = AppTest.from_string(WIP_SCRIPT_WITH_LABELS, default_timeout=60)
    browser = BrowserChoice(app, "multiselect", WIP_FILTER_KEY)
    browser.start()
    browser.pick(["T-Process"])
    _submit_wip(app)
    browser.run()
    assert app.session_state[WIP_FILTER_KEY] == ["T-Process"]

    app.session_state["test_labels"] = {"T-Process": "P-Process"}
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[WIP_FILTER_KEY] == ["T-Process"]
    assert browser.wire == ["P-Process (T-Process)"]


# ------------------------------------------------------------------ Dynamic Capa 상위 · 공정
INTEGRITY_SCRIPT = _swap(
    INTEGRITY_RENAMED_SCRIPT,
    'pd.DataFrame([(demo_processes[0], "표시공정")], columns=["공정", "표시명"]), 5',
    "pd.DataFrame(\n"
    '            [(demo_processes[1], st.session_state.get("test_label_target", "표시공정"))],\n'
    '            columns=["공정", "표시명"],\n'
    "        ),\n"
    "        5,",
)
INTEGRITY_FILTER_KEY = "dynamic_capacity_process_filter"


def test_dynamic_capacity_process_splits_a_colliding_display_name() -> None:
    """둘째 공정의 표시명이 첫째 공정의 원본과 같다 — 「첫째 (둘째)」 로 갈라 고른 공정이 든다."""
    app = AppTest.from_string(INTEGRITY_SCRIPT, default_timeout=60)
    app.session_state["test_label_target"] = "__FIRST__"
    # 표본 공정명은 리터럴로 고정하지 않는다 — 한 번 돌려 첫째 이름을 읽고 그 글자를 표시명으로
    # 준다.
    app.run()
    first = app.session_state["renamed_source"]
    second = app.session_state["untouched_source"]
    app.session_state["test_label_target"] = first
    browser = BrowserChoice(app, "selectbox", INTEGRITY_FILTER_KEY)
    browser.start()
    assert not app.exception
    assert f"{first} ({second})" in browser.options()
    assert first in browser.options()

    browser.pick(f"{first} ({second})")
    browser.run()

    assert not app.exception
    assert app.session_state[INTEGRITY_FILTER_KEY] == second


def test_dynamic_capacity_process_keeps_its_value_when_the_display_name_changes() -> None:
    app = AppTest.from_string(INTEGRITY_SCRIPT, default_timeout=60)
    browser = BrowserChoice(app, "selectbox", INTEGRITY_FILTER_KEY)
    browser.start()
    first = app.session_state["renamed_source"]
    second = app.session_state["untouched_source"]
    browser.pick("표시공정")
    browser.run()
    assert app.session_state[INTEGRITY_FILTER_KEY] == second

    app.session_state["test_label_target"] = first
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[INTEGRITY_FILTER_KEY] == second
    assert browser.wire == f"{first} ({second})"


def test_dynamic_capacity_process_defaults_to_the_worst_process() -> None:
    """기본값(가장 나쁜 공정)은 위젯 `index=` 가 아니라 세션에 심는다 — 둘을 함께 주면 Streamlit 이
    경고한다. 표시명이 없으면 글자·차례가 예전 그대로다(원본 가나다순)."""
    from test_reference_integrity_page import TEST_SCRIPT as PLAIN_SCRIPT

    app = AppTest.from_string(PLAIN_SCRIPT, default_timeout=60).run()

    assert not app.exception
    picker = app.selectbox(key=INTEGRITY_FILTER_KEY)
    assert picker.options == sorted(picker.options)
    assert app.session_state[INTEGRITY_FILTER_KEY] == picker.value


# ------------------------------------------------------- 실적 화면(효율·UPEH·수율) · 공정
def _performance_app() -> None:
    import streamlit as st

    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC,
        key_prefix="label_test",
        process_labels=ProcessLabels(version=1, labels=st.session_state.get("test_labels", {})),
    )


PERFORMANCE_FILTER_KEY = "label_test_process_filter"


def _demo_processes() -> list[str]:
    from capa_simulation.services.performance_actuals import build_monthly_actual_demo

    return sorted(build_monthly_actual_demo()["공정"].astype(str).unique().tolist())


def test_performance_filter_splits_a_colliding_display_name() -> None:
    first, second = _demo_processes()[:2]
    app = AppTest.from_function(_performance_app)
    app.session_state["test_labels"] = {second: first}
    browser = BrowserChoice(app, "multiselect", PERFORMANCE_FILTER_KEY)
    browser.start()
    assert not app.exception
    assert browser.options()[:2] == [first, f"{first} ({second})"]

    browser.pick([f"{first} ({second})"])
    browser.run()

    assert not app.exception
    assert app.session_state[PERFORMANCE_FILTER_KEY] == [second]


def test_performance_filter_keeps_its_value_when_the_display_name_changes() -> None:
    first, second = _demo_processes()[:2]
    app = AppTest.from_function(_performance_app)
    app.session_state["test_labels"] = {second: "가공"}
    browser = BrowserChoice(app, "multiselect", PERFORMANCE_FILTER_KEY)
    browser.start()
    browser.pick(["가공"])
    browser.run()
    assert app.session_state[PERFORMANCE_FILTER_KEY] == [second]

    app.session_state["test_labels"] = {second: first}
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[PERFORMANCE_FILTER_KEY] == [second]
    assert browser.wire == [f"{first} ({second})"]


def test_performance_filter_without_display_names_keeps_its_texts() -> None:
    app = AppTest.from_function(_performance_app).run()

    assert not app.exception
    assert app.multiselect(key=PERFORMANCE_FILTER_KEY).options == _demo_processes()
