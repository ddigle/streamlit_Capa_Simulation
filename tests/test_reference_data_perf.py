# Purpose: 기준 정보가 닫힌 탭의 표를 건너뛰어도 같은 값을 보이고 내용이 바뀌면 다시 만드는지 본다.

"""기준 정보 rerun 비용 줄이기의 회귀 검사.

닫힌 탭의 표(STEP 경로표·편집 기간 조각·설비대수 블록)를 건너뛰어도 **보이는 값은 고치기 전과
같아야** 하고, 적용·리비전 전환으로 내용이 바뀌면 **다시 만들어야** 한다. 화면 픽스처는
`test_reference_data_page` 의 것을 그대로 쓰고, 그 위에 무엇을 몇 번 만들었는지 적는 탐침만 얹는다.
"""

from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    EQP_TAB,
    REAL_APPLY_TEST_SCRIPT,
    REF_TAB,
    TEST_SCRIPT,
    TWO_PROCESS_TEST_SCRIPT,
    _add_step,
    _edit_and_apply,
    _frame_with_column,
    _real_apply,
    editor_widget_key_in,
)

from capa_simulation.services import display_order_scopes as scopes
from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    build_reference_edit_table,
)
from capa_simulation.services.display_order import apply_display_order, prepare_display_order
from capa_simulation.services.equipment_count import (
    build_equipment_count_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.month_filter import filter_month_range
from capa_simulation.services.route_step_editor import route_step_tables

DIALOG_KEY = "reference_data_open_dialog"
STEP_SUMMARY_COLUMNS = {
    "생산계획년월": "월",
    "Area_Name": "Area",
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
}

# 회차마다 페이지가 자른 표 이름, STEP 경로표를 부른 횟수와 실제로 쓴 입력, 편집기에 넘긴 양식을
# 세션에 적는다. 페이지는 이 함수들을 exec 때 모듈에서 집으므로 모듈 속성을 갈아끼우면 탐침을
# 집는다.
# 활성 시나리오 표도 적어 두어, 테스트가 같은 표로 **직접** 계산한 값과 견준다.
_PROBE = """
import capa_simulation.components.month_editor as _probe_month_editor
import capa_simulation.scenario_state as _probe_state
import capa_simulation.services.equipment_count as _probe_equipment

st.session_state.setdefault("test_slice_log", []).append([])
st.session_state["test_editor_templates"] = {}
st.session_state["test_equipment_builds"] = []
st.session_state["test_active_tables"] = {
    _name: _frame.copy()
    for _name, _frame in scenario_state.ensure_active_scenario(None, None)["tables"].items()
}
_probe_original_month_table = _probe_state.scenario_month_table
_probe_original_route_tables = simulation_cache.get_route_step_tables
_probe_original_render_month_editor = _probe_month_editor.render_month_editor
_probe_original_count_table = _probe_equipment.build_equipment_count_table
_probe_original_count_edit = _probe_equipment.equipment_count_to_edit_table


def _probe_count_table(own, lent, available, *, detailed):
    st.session_state["test_equipment_builds"].append(("현황", detailed))
    return _probe_original_count_table(own, lent, available, detailed=detailed)


def _probe_count_edit(data, category, value_column):
    st.session_state["test_equipment_builds"].append(("양식", category))
    return _probe_original_count_edit(data, category, value_column)


_probe_original_change_count = _probe_month_editor.count_month_changes
st.session_state["test_change_counts"] = []


def _probe_change_count(default_table, merged, month_columns):
    counted = _probe_original_change_count(default_table, merged, month_columns)
    st.session_state["test_change_counts"].append(counted)
    return counted


def _probe_month_table(scenario, table_name, start, end):
    st.session_state["test_slice_log"][-1].append(table_name)
    return _probe_original_month_table(scenario, table_name, start, end)


def _probe_route_tables(cache_key, *, _upeh, _reqb):
    st.session_state["test_route_step_calls"] = (
        st.session_state.get("test_route_step_calls", 0) + 1
    )
    st.session_state["test_route_step_key"] = cache_key
    frames = st.session_state.setdefault("test_route_step_frames", {})

    def _recording(name, source):
        if not callable(source):
            frames.setdefault(cache_key, {})[name] = source.copy()
            return source

        def load():
            frame = source()
            frames.setdefault(cache_key, {})[name] = frame.copy()
            return frame

        return load

    return _probe_original_route_tables(
        cache_key, _upeh=_recording("upeh", _upeh), _reqb=_recording("reqb", _reqb)
    )


def _probe_render_month_editor(tab, default_table, dimensions, editor_key, *args, **kwargs):
    st.session_state["test_editor_templates"][editor_key] = default_table.copy()
    return _probe_original_render_month_editor(
        tab, default_table, dimensions, editor_key, *args, **kwargs
    )


_probe_state.scenario_month_table = _probe_month_table
simulation_cache.get_route_step_tables = _probe_route_tables
_probe_month_editor.render_month_editor = _probe_render_month_editor
_probe_equipment.build_equipment_count_table = _probe_count_table
_probe_equipment.equipment_count_to_edit_table = _probe_count_edit
_probe_month_editor.count_month_changes = _probe_change_count
"""
_PROBE_RESTORE = (
    "    _probe_state.scenario_month_table = _probe_original_month_table\n"
    "    simulation_cache.get_route_step_tables = _probe_original_route_tables\n"
    "    _probe_month_editor.render_month_editor = _probe_original_render_month_editor\n"
    "    _probe_equipment.build_equipment_count_table = _probe_original_count_table\n"
    "    _probe_equipment.equipment_count_to_edit_table = _probe_original_count_edit\n"
    "    _probe_month_editor.count_month_changes = _probe_original_change_count\n"
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


def _sliced(app: AppTest, back: int = 1) -> list[str]:
    """뒤에서 `back` 번째 회차(1 = 마지막)에 자른 표 이름."""
    return list(app.session_state["test_slice_log"][-back])


def _open_tab(app: AppTest, name: str) -> AppTest:
    app.session_state["reference_data_active_tab"] = REF_TAB[name]
    app.run()
    assert not app.exception
    return app


def _displayed_summary(app: AppTest) -> pd.DataFrame:
    return _frame_with_column(app, "STEP 수").reset_index(drop=True)


def _route_key(app: AppTest) -> tuple[int, str, int, int]:
    key: tuple[int, str, int, int] = app.session_state["test_route_step_key"]
    return key


def _route_inputs(app: AppTest) -> dict[str, pd.DataFrame]:
    """이 회차 키로 경로표를 만들 때 실제로 넘어간 조각(캐시가 빗나간 회차에 적힌다)."""
    inputs: dict[str, pd.DataFrame] = app.session_state["test_route_step_frames"][_route_key(app)]
    return inputs


def _expected_summary(app: AppTest) -> pd.DataFrame:
    """이 회차 키의 조각으로 경로표를 **새로** 계산해 화면 표 꼴로 바꾼다."""
    inputs = _route_inputs(app)
    summary, _catalog = route_step_tables(inputs["upeh"], inputs["reqb"])
    return summary.rename(columns=STEP_SUMMARY_COLUMNS).reset_index(drop=True)


RATIO_DIMENSIONS = [
    "공정",
    "Area_Name",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
]


def _empty_display_order() -> pd.DataFrame:
    """픽스처(`TEST_SCRIPT`)의 빈 공용 표시순서와 같은 표."""
    return pd.DataFrame(
        columns=[
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ]
    )


def _month_slice(app: AppTest, table_name: str) -> pd.DataFrame:
    """이 회차 활성 시나리오 표를 적용 기간(2026-08)으로 **직접** 자른 조각."""
    table: pd.DataFrame = app.session_state["test_active_tables"][table_name]
    return filter_month_range(table, 202608, 202608, table_name)


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
    # 조각은 이 회차 활성 시나리오를 적용 기간(2026-08)으로 자른 것이다.
    inputs = _route_inputs(app)
    for name, table in (("reqb", "RQ_REQB"), ("upeh", "RQ_UPEH")):
        pd.testing.assert_frame_equal(inputs[name], _month_slice(app, table))
    assert _route_key(app)[1] == "test-ref-perf-step-same"


def test_a_step_change_rebuilds_the_route_tables_with_the_new_token() -> None:
    """STEP 을 더하면 내용 토큰이 바뀌고, STEP 탭은 새 토큰으로 다시 만든 경로표를 보인다."""
    app = AppTest.from_string(
        _probed(REAL_APPLY_TEST_SCRIPT, "test-ref-perf-step-rebuild"), default_timeout=60
    ).run()
    app = _open_tab(app, "STEP 구성")
    first_key = _route_key(app)
    assert _displayed_summary(app)["STEP 수"].tolist() == [1]

    app = _add_step(app, "2A", "P200")
    app.run()
    assert not app.exception
    new_key = _route_key(app)
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


# ---------------------------------------------------------------- R2 편집 기간 조각

# (RQ, 분류 컬럼, 값 컬럼, 표시순서 화면 범위) — 페이지의 편집표 여섯 개와 같은 인자다.
EDIT_TABLES: dict[str, tuple[str, list[str], str | None, str]] = {
    "UPEH": ("RQ_UPEH", PERFORMANCE_EDITOR_DIMENSIONS, None, scopes.TAB_UPEH),
    "효율": ("RQ_RUN_RATE", ["공정", "양산구분"], "CAPA_RUN_RATE", scopes.TAB_RUN_RATE),
    "여유율": ("RQ_VITAL", ["공정", "양산구분"], "편중률", scopes.TAB_VITAL),
    "일수": ("RQ_RUN_DAY", ["공정"], "RUN_DAY", scopes.TAB_RUN_DAY),
    "Lot측정률": ("RQ_LOT_RATIO", RATIO_DIMENSIONS, "Lot 측정률", scopes.TAB_LOT_RATIO),
    "WF측정률": ("RQ_WF_RATIO", RATIO_DIMENSIONS, "WF측정률", scopes.TAB_WF_RATIO),
}
EDITOR_OF = {
    "UPEH": "capa_upeh_editor",
    "효율": "capa_run_rate_editor",
    "여유율": "capa_vital_editor",
    "일수": "capa_run_day_editor",
    "Lot측정률": "capa_lot_ratio_editor",
    "WF측정률": "capa_wf_ratio_editor",
}
UNUSED_HERE = {"RQ_PKG_PLAN", "RQ_YLD"}


def test_only_the_slices_a_run_uses_are_cut() -> None:
    """이 화면은 RQ_PKG_PLAN·RQ_YLD 를 쓰지 않는다. 편집표 조각은 열린 탭 것만 빗나갈 때 자른다."""
    app = AppTest.from_string(_probed(TEST_SCRIPT, "test-ref-perf-slices"), default_timeout=60)
    app.run()
    assert not app.exception
    first = set(_sliced(app))
    assert "RQ_UPEH" in first
    closed = {"RQ_RUN_RATE", "RQ_VITAL", "RQ_RUN_DAY", "RQ_LOT_RATIO", "RQ_WF_RATIO", "RQ_REQB"}
    assert not first & (UNUSED_HERE | closed)

    # 같은 토큰으로 다시 돌면 편집표가 캐시에서 나와 조각을 자르지 않는다.
    app.run()
    assert "RQ_UPEH" not in _sliced(app)

    app = _open_tab(app, "효율")
    assert "RQ_RUN_RATE" in _sliced(app)
    assert not set(_sliced(app)) & (UNUSED_HERE | {"RQ_UPEH"})


@pytest.mark.parametrize("tab_name", list(EDIT_TABLES))
def test_each_edit_table_equals_the_direct_build_of_this_runs_slice(tab_name: str) -> None:
    """편집표는 캐시가 빗나간 회차든 적중한 회차든, 이 회차 조각으로 직접 만든 표와 값이 같다."""
    table_name, dimensions, value_column, scope_tab = EDIT_TABLES[tab_name]
    editor_key = EDITOR_OF[tab_name]
    app = AppTest.from_string(
        _probed(TEST_SCRIPT, f"test-ref-perf-same-{table_name}"), default_timeout=60
    )
    for _ in range(2):  # 빗나간 회차, 적중한 회차
        app = _open_tab(app, tab_name)
        expected = build_reference_edit_table(
            _month_slice(app, table_name),
            table_name=table_name,
            dimensions=dimensions,
            value_column=value_column,
            display_order=prepare_display_order(_empty_display_order()),
            page=scopes.PAGE_REFERENCE,
            tab=scope_tab,
        )
        template = app.session_state["test_editor_templates"][editor_key]
        pd.testing.assert_frame_equal(template, expected)


def test_an_unapplied_edit_left_in_a_closed_tab_applies_the_edited_row_only() -> None:
    """효율 칸을 고친 채 다른 탭으로 갔다가 돌아와 적용해도, 그 칸만 바뀌고 나머지 행은 원본이다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-closed-pending"), default_timeout=60
    )
    app = _open_tab(app, "효율")
    key = editor_widget_key_in(app, "capa_run_rate_editor")
    edit = {"edited_rows": {0: {"202608": 0.5}}, "added_rows": [], "deleted_rows": []}
    app.session_state[key] = edit
    app.session_state["reference_data_active_tab"] = REF_TAB["UPEH"]
    app.run()
    assert not app.exception
    # 닫힌 탭이어도 적용하지 않은 편집이 남은 편집표는 그린다.
    assert "capa_run_rate_editor_apply" in {button.key for button in app.button}

    app.session_state[key] = edit
    app = _open_tab(app, "효율")
    app.session_state[key] = edit
    next(button for button in app.button if button.key == "capa_run_rate_editor_apply").click()
    app.run()

    assert not app.exception
    assert [error.value for error in app.error] == []
    saved = app.session_state["test_month_updates"]["RQ_RUN_RATE"]
    assert dict(zip(saved["공정"], saved["CAPA_RUN_RATE"], strict=True)) == {
        "Process-A": 0.5,
        "Process-B": 0.9,
    }


_BAD_RUN_RATE_MONTH = (
    'tables["RQ_RUN_RATE"] = tables["RQ_RUN_RATE"].assign(생산계획년월=[2026081])\n'
)


def test_a_bad_month_shows_the_message_where_that_table_is_used() -> None:
    """월 형식이 틀린 표는 그 표를 쓰는 탭에서 traceback 이 아니라 오류 문구로 멈춘다."""
    script = TEST_SCRIPT.replace("\nactive = {", "\n" + _BAD_RUN_RATE_MONTH + "active = {", 1)
    app = AppTest.from_string(_probed(script, "test-ref-perf-bad-month"), default_timeout=60)
    app = _open_tab(app, "효율")
    assert any(
        "RQ_RUN_RATE의 생산계획년월은 YYYYMM 형식이어야 합니다" in error.value
        for error in app.error
    )
    # 그 표를 쓰지 않는 탭은 연다.
    app = _open_tab(app, "UPEH")
    assert [error.value for error in app.error] == []
    assert "capa_upeh_editor_apply" in {button.key for button in app.button}


# ---------------------------------------------------------------- R3 설비대수 블록

EQUIPMENT_EDITORS = {
    "보유": ("RQ_EQP_OWN", "설비보유", "capa_eqp_own_editor"),
    "대여": ("RQ_EQP_LENT", "설비대여평가", "capa_eqp_lent_editor"),
    "가용": ("RQ_EQP_AVBL", "가용대수", "capa_eqp_avbl_editor"),
}


def _builds(app: AppTest) -> list[tuple[str, object]]:
    """이 회차에 만든 설비대수 표 — ("양식", 구분) 또는 ("현황", 상세)."""
    return list(app.session_state["test_equipment_builds"])


def _open_equipment(app: AppTest, sub_tab: str) -> AppTest:
    app.session_state["reference_data_active_tab"] = REF_TAB["설비대수"]
    app.session_state["equipment_count_active_tab"] = EQP_TAB[sub_tab]
    app.run()
    assert not app.exception
    return app


def _expected_overview(app: AppTest, *, detailed: bool) -> pd.DataFrame:
    """현황 표를 이 회차 활성 시나리오 조각으로 **직접** 만든다(0 은 빈칸, 표시순서는 빈 프로필)."""
    own, lent, available = (
        _month_slice(app, table_name) for table_name, _, _ in EQUIPMENT_EDITORS.values()
    )
    table = apply_display_order(
        build_equipment_count_table(own, lent, available, detailed=detailed),
        prepare_display_order(_empty_display_order()),
        scopes.PAGE_REFERENCE,
        scopes.TAB_EQUIPMENT_COUNT,
    )
    months = [column for column in table.columns if column not in ("공정", "구분")]
    table[months] = table[months].mask(table[months].eq(0))
    return table.reset_index(drop=True)


def test_the_equipment_block_builds_only_what_the_open_tabs_draw() -> None:
    """설비대수 탭이 닫히면 아무것도 만들지 않고, 열리면 보이는 안쪽 탭 하나의 표만 만든다."""
    app = AppTest.from_string(_probed(TEST_SCRIPT, "test-ref-perf-equipment"), default_timeout=60)
    app.run()
    assert not app.exception
    assert _builds(app) == []
    assert not {name for name in _sliced(app) if name.startswith("RQ_EQP")}

    for sub_tab in ("보유", "대여", "가용"):
        app = _open_equipment(app, sub_tab)
        assert _builds(app) == [("양식", sub_tab)]
        assert {name for name in _sliced(app) if name.startswith("RQ_EQP")} == {
            EQUIPMENT_EDITORS[sub_tab][0]
        }

    app = _open_equipment(app, "현황")
    assert _builds(app) == [("현황", False)]
    app = app.sidebar.toggle(key="equipment_count_detail").set_value(True).run()
    assert not app.exception
    assert _builds(app) == [("현황", True)]


@pytest.mark.parametrize("detailed", [False, True], ids=["summary", "detailed"])
def test_the_equipment_overview_equals_the_direct_build(detailed: bool) -> None:
    """현황 표는 「상세」 값에 맞는 한 벌만 만들어도 직접 만든 표와 값이 같다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, f"test-ref-perf-overview-{detailed}"), default_timeout=60
    )
    app.session_state["equipment_count_detail"] = detailed
    app = _open_equipment(app, "현황")
    displayed = _frame_with_column(app, "공정").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        displayed, _expected_overview(app, detailed=detailed), check_dtype=False
    )


@pytest.mark.parametrize("sub_tab", list(EQUIPMENT_EDITORS))
def test_each_equipment_form_equals_the_direct_build(sub_tab: str) -> None:
    table_name, value_column, editor_key = EQUIPMENT_EDITORS[sub_tab]
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, f"test-ref-perf-form-{table_name}"), default_timeout=60
    )
    app = _open_equipment(app, sub_tab)
    expected = equipment_count_to_edit_table(_month_slice(app, table_name), sub_tab, value_column)
    pd.testing.assert_frame_equal(app.session_state["test_editor_templates"][editor_key], expected)


def test_a_pending_equipment_edit_keeps_its_form_and_lands_on_its_row() -> None:
    """보유 칸을 고친 채 다른 탭으로 옮겨도 보유 양식을 만들고, 돌아와 적용하면 그 행에 든다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-equipment-pending"), default_timeout=60
    )
    app = _open_equipment(app, "보유")
    key = editor_widget_key_in(app, "capa_eqp_own_editor")
    edit = {"edited_rows": {1: {"202608": 7.0}}, "added_rows": [], "deleted_rows": []}

    app.session_state[key] = edit
    app = _open_equipment(app, "대여")
    assert sorted(_builds(app)) == [("양식", "대여"), ("양식", "보유")]

    app.session_state[key] = edit
    app = _open_tab(app, "UPEH")
    assert _builds(app) == [("양식", "보유")]
    assert "capa_eqp_own_editor_apply" in {button.key for button in app.button}

    app.session_state[key] = edit
    app = _open_equipment(app, "보유")
    app.session_state[key] = edit
    next(button for button in app.button if button.key == "capa_eqp_own_editor_apply").click()
    app.run()

    assert not app.exception
    assert [error.value for error in app.error] == []
    saved = app.session_state["test_month_updates"]["RQ_EQP_OWN"]
    assert dict(zip(saved["공정"], saved["설비보유"], strict=True)) == {
        "Process-A": 2.0,
        "Process-B": 7.0,
    }


def test_an_equipment_apply_shows_in_the_overview() -> None:
    """보유를 적용하면(새 토큰) 현황 상세가 그 값으로 다시 만들어진다."""
    script = _real_apply(
        TWO_PROCESS_TEST_SCRIPT, "test-capacity-two-process-page", "test-capacity-two-process-page"
    )
    app = AppTest.from_string(_probed(script, "test-ref-perf-equipment-apply"), default_timeout=60)
    app.session_state["equipment_count_detail"] = True
    app = _open_equipment(app, "현황")
    before = _frame_with_column(app, "공정")
    own_a = before.loc[(before["공정"] == "Process-A") & (before["구분"] == "보유"), "202608"]
    assert own_a.tolist() == [2.0]

    app = _open_equipment(app, "보유")
    app = _edit_and_apply(app, "capa_eqp_own_editor", "202608", 7.0)
    assert not app.exception
    app = _open_equipment(app, "현황")
    after = _frame_with_column(app, "공정")
    own_a = after.loc[(after["공정"] == "Process-A") & (after["구분"] == "보유"), "202608"]
    assert own_a.tolist() == [7.0]
    pd.testing.assert_frame_equal(
        after.reset_index(drop=True), _expected_overview(app, detailed=True), check_dtype=False
    )


# ---------------------------------------------------------------- R7 현황 표 고정 uuid


def _overview_proto(app: AppTest) -> bytes:
    """설비대수 현황 표 메시지 바이트 — 브라우저가 다시 받을지는 이 바이트의 해시로 정해진다."""
    for element in app.dataframe:
        if "공정" in element.value.columns:
            data: bytes = element.proto.SerializeToString()
            return data
    raise AssertionError("현황 표가 없습니다.")


def test_the_overview_message_is_identical_across_reruns() -> None:
    """내용이 같으면 회차가 바뀌어도 현황 표 메시지가 같다(무작위 Styler uuid 가 없다)."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-overview-uuid"), default_timeout=60
    )
    app = _open_equipment(app, "현황")
    first = _overview_proto(app)
    app.run()
    assert _overview_proto(app) == first

    app = app.sidebar.toggle(key="equipment_count_detail").set_value(True).run()
    detailed = _overview_proto(app)
    assert detailed != first
    app.run()
    assert _overview_proto(app) == detailed
    # 두 꼴은 서로 다른 고정 uuid 다 — 같은 화면에 섞여도 CSS 이름이 겹치지 않는다.
    assert b"equipment_count_detail" in detailed
    assert b"equipment_count" in first and b"equipment_count_detail" not in first


# ---------------------------------------------------------------- R8 변경 개수


def _change_counts(app: AppTest) -> list[tuple[int, int]]:
    counts: list[tuple[int, int]] = list(app.session_state["test_change_counts"])
    return counts


def _change_lines(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown if "변경사항 확인" in str(item.value)]


def test_the_change_count_runs_only_with_unapplied_edits() -> None:
    """편집이 없으면 셀 수를 세지 않고(줄도 없다), 고치면 예전과 같은 줄이 선다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-change-count"), default_timeout=60
    )
    app = _open_tab(app, "일수")
    assert _change_counts(app) == []
    assert _change_lines(app) == []

    key = editor_widget_key_in(app, "capa_run_day_editor")
    app.session_state[key] = {
        "edited_rows": {0: {"202608": 20.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()
    assert not app.exception
    assert _change_counts(app) == [(1, 1)]
    assert _change_lines(app) == ["**변경사항 확인** &nbsp;1개 값 · 1개 행"]

    # 같은 값으로 고친 칸은 편집이 남아도 바뀐 것이 없다 — 세지만 줄은 서지 않는다.
    app.session_state[key] = {
        "edited_rows": {0: {"202608": 31.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()
    assert _change_counts(app) == [(0, 0)]
    assert _change_lines(app) == []
