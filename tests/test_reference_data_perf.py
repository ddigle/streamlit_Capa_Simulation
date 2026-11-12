# Purpose: 기준 정보가 고르지 않은 종류의 표를 건너뛰어도 같은 값이고 바뀌면 다시 만드는지 본다.

"""기준 정보 rerun 비용 줄이기의 회귀 검사.

고르지 않은 종류의 표(STEP 경로표·편집 기간 조각·설비대수 블록)를 건너뛰어도 **보이는 값은 고치기
전과 같아야** 하고, 적용·리비전 전환으로 내용이 바뀌면 **다시 만들어야** 한다. 화면 픽스처는
`test_reference_data_page` 의 것을 그대로 쓰고, 그 위에 무엇을 몇 번 만들었는지 적는 탐침만 얹는다.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from alert_marks import data_error_texts, place_errors, successes
from edit_grid_fake import Calls, install_fake_edit_grid, last
from streamlit.dataframe import lazy_df_source
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    DATASET,
    REAL_APPLY_TEST_SCRIPT,
    TEST_SCRIPT,
    TWO_PROCESS_TEST_SCRIPT,
    _add_step,
    _edit_and_apply,
    _frame_with_column,
    _grid_write,
    _real_apply,
    _visible_keys,
)

from capa_simulation.components.edit_grid import feed_key
from capa_simulation.reference_grid_keys import DATASET_KEY, GRID_HOST
from capa_simulation.services import display_order_scopes as scopes
from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    build_reference_edit_table,
)
from capa_simulation.services.display_order import apply_display_order, prepare_display_order
from capa_simulation.services.equipment_count import equipment_count_to_edit_table
from capa_simulation.services.month_filter import filter_month_range
from capa_simulation.services.route_step_editor import route_step_tables

REFERENCE_DATA_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "reference_data.py"


@pytest.fixture
def grid_calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """기준 정보 편집 그리드 대역 — 받은 (key, data) 를 적는다(`tests/edit_grid_fake.py`)."""
    return install_fake_edit_grid(monkeypatch)


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
import capa_simulation.components.reference_grid as _probe_reference_grid
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
_probe_original_count_edit = _probe_equipment.equipment_count_to_edit_table


def _probe_count_edit(data, category, value_column):
    st.session_state["test_equipment_builds"].append(("양식", category))
    return _probe_original_count_edit(data, category, value_column)


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


_probe_original_build_grid_table = _probe_reference_grid.build_grid_table


def _probe_build_grid_table(table, title, editor_key, template, *args, **kwargs):
    st.session_state["test_editor_templates"][editor_key] = template.copy()
    return _probe_original_build_grid_table(table, title, editor_key, template, *args, **kwargs)


_probe_state.scenario_month_table = _probe_month_table
simulation_cache.get_route_step_tables = _probe_route_tables
_probe_reference_grid.build_grid_table = _probe_build_grid_table
_probe_equipment.equipment_count_to_edit_table = _probe_count_edit
"""
_PROBE_RESTORE = (
    "    _probe_state.scenario_month_table = _probe_original_month_table\n"
    "    simulation_cache.get_route_step_tables = _probe_original_route_tables\n"
    "    _probe_reference_grid.build_grid_table = _probe_original_build_grid_table\n"
    "    _probe_equipment.equipment_count_to_edit_table = _probe_original_count_edit\n"
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
    app.session_state[DATASET_KEY] = DATASET[name]
    app.run()
    assert not app.exception
    return app


def _sent_summary(app: AppTest) -> pd.DataFrame:
    """화면에 보낸 STEP 요약 그대로(dtype 포함)."""
    return _frame_with_column(app, "STEP 수").reset_index(drop=True)


def _displayed_summary(app: AppTest) -> pd.DataFrame:
    """화면 STEP 요약의 **값**. 화면 사본은 보내는 바이트를 줄이려 글자 열을 category 로 싣는다 —
    값과 차례만 견주도록 원래 글자 열로 되돌린다(정수 폭은 `check_dtype=False` 가 덮는다)."""
    summary = _sent_summary(app)
    return summary.astype({column: object for column in summary.select_dtypes("category").columns})


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


def test_the_step_summary_is_sent_with_compact_dtypes() -> None:
    """STEP 요약은 월 × 경로 그룹의 긴 표다. 화면 사본은 경로 글자 열을 category 로, 월·개수를
    좁은 정수로 보낸다 — 행마다 되풀이되는 글자와 8바이트 정수가 전송량 대부분이었다. 값은 위
    검사가 본다."""
    app = AppTest.from_string(
        _probed(TEST_SCRIPT, "test-ref-perf-step-compact"), default_timeout=60
    )
    app = _open_tab(app, "STEP 구성")

    sent = _sent_summary(app)
    number_columns = ["월", "STEP 수", "수요 변형 수"]
    text_columns = [column for column in sent.columns if column not in number_columns]
    assert text_columns == ["Area", "공정", "양산", "제품", "Stack", "속성", "소요기준"]
    assert all(isinstance(sent[column].dtype, pd.CategoricalDtype) for column in text_columns)
    for column in number_columns:
        dtype = sent[column].dtype
        assert isinstance(dtype, np.dtype)
        assert dtype.kind == "i"
        assert dtype.itemsize < 8
    # category 글자 열은 글자 칸으로 못 박는다 — 두지 않으면 화면이 선택 칸 꼴로 그린다.
    element = next(frame for frame in app.dataframe if "STEP 수" in frame.value.columns)
    column_config = json.loads(element.proto.columns)
    assert all(column_config[column]["type_config"]["type"] == "text" for column in text_columns)


def test_the_eager_step_summary_limit_follows_streamlit_auto_lazy_threshold() -> None:
    """줄인 사본을 보내는 행 수의 끝은 Streamlit 이 스스로 lazy 로 바꾸는 행 수와 같아야 한다.

    둘이 어긋나면 그 사이 길이의 표가 category 열로 lazy 정렬에 들어가 「Failed to load data」 가
    되거나(끝이 더 크면), `lazy=False` 로 못 박혀 정렬 단추를 잃는다(끝이 더 작으면). 페이지
    모듈은 import 하면 화면이 통째로 돌므로 AST 로 읽는다.
    """
    tree = ast.parse(REFERENCE_DATA_PAGE.read_text(encoding="utf-8"))
    limits = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "STEP_SUMMARY_EAGER_MAX_ROWS"
            for target in node.targets
        )
    ]

    assert limits == [lazy_df_source.AUTO_LAZY_ROW_THRESHOLD]


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


def test_an_apply_on_another_tab_is_seen_when_the_step_tab_opens(grid_calls: Calls) -> None:
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
    app = _edit_and_apply(app, grid_calls, "capa_upeh_editor", "202608", None)
    assert not app.exception
    assert place_errors(app) == []
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
    assert any("STEP을 추가했습니다" in item.value for item in successes(app))
    assert not any("STEP을 추가했습니다" in item.value for item in app.success)
    app.run()
    assert not any("STEP을 추가했습니다" in item.value for item in successes(app))


def test_an_open_step_popup_builds_the_route_tables_while_its_tab_is_hidden() -> None:
    """STEP 팝업이 열린 회차는 STEP 탭이 숨어 있어도 경로표를 만들어 팝업의 경로 상자를 채운다."""
    app = AppTest.from_string(
        _probed(TEST_SCRIPT, "test-ref-perf-step-popup-hidden"), default_timeout=60
    )
    app = _open_tab(app, "UPEH")
    assert _route_calls(app) == 0

    app.session_state[DIALOG_KEY] = "step"
    app.run()
    assert not app.exception
    assert _route_calls(app) == 1
    assert "RQ_REQB" in _sliced(app)
    assert _route_processes(app) == ["Process-A"]


def test_a_step_flash_left_while_the_step_tab_is_hidden_is_not_shown_later() -> None:
    """알림은 매 회차 꺼낸다 — STEP 탭이 숨은 회차에 남은 알림이 나중에 STEP 탭에서 뜨지 않는다."""
    app = AppTest.from_string(
        _probed(TEST_SCRIPT, "test-ref-perf-step-stale-flash"), default_timeout=60
    )
    app = _open_tab(app, "UPEH")
    app.session_state["capacity_step_flash"] = "STEP을 추가했습니다: 옛 알림"
    app.run()
    assert not app.exception
    assert "capacity_step_flash" not in app.session_state

    app = _open_tab(app, "STEP 구성")
    assert not any("STEP을 추가했습니다" in item.value for item in successes(app))


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


def test_an_unapplied_edit_left_in_a_closed_tab_applies_the_edited_row_only(
    grid_calls: Calls,
) -> None:
    """효율 칸을 고친 채 다른 표로 갔다가 돌아와 적용해도, 그 칸만 바뀌고 나머지 행은 원본이다.
    다른 표를 보는 동안 효율 양식은 만들지 않는다 — 초안은 세션 칸(업무 키)이라 양식 없이 남는다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-closed-pending"), default_timeout=60
    )
    app = _open_tab(app, "효율")
    app = _grid_write(app, grid_calls, "Process-A\x1f양산", "202608", "0.5")
    app = _open_tab(app, "UPEH")
    assert "capa_run_rate_editor" not in app.session_state["test_editor_templates"]
    assert "capa_run_rate_editor_apply" not in {button.key for button in app.button}

    app = _open_tab(app, "효율")
    app.button(key="capa_run_rate_editor_apply").click().run()

    assert not app.exception
    assert place_errors(app) == []
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
        "RQ_RUN_RATE의 생산계획년월은 YYYYMM 형식이어야 합니다" in text
        for text in data_error_texts(app)
    )
    # 그 표를 쓰지 않는 탭은 연다.
    app = _open_tab(app, "UPEH")
    assert place_errors(app) == []
    assert "capa_upeh_editor_apply" in {button.key for button in app.button}


def _with_bad_month(table_name: str) -> str:
    """`table_name` 의 생산계획년월이 모두 틀린 형식(7자리)인 픽스처."""
    bad = f'tables["{table_name}"] = tables["{table_name}"].assign(생산계획년월=2026081)\n'
    return TEST_SCRIPT.replace("\nactive = {", "\n" + bad + "active = {", 1)


def _shows_bad_month(app: AppTest, table_name: str) -> bool:
    message = f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다"
    return any(message in text for text in data_error_texts(app))


def test_a_bad_equipment_month_shows_the_message_in_the_equipment_tabs() -> None:
    """설비대수 양식은 페이지 앞 `try` 밖에서 자른다(`_template_or_stop`). 그래도 문구로 멈춘다."""
    app = AppTest.from_string(
        _probed(_with_bad_month("RQ_EQP_OWN"), "test-ref-perf-bad-eqp-month"), default_timeout=60
    )
    app = _open_equipment(app, "보유")
    assert _shows_bad_month(app, "RQ_EQP_OWN")
    # 그 표를 쓰지 않는 탭은 연다.
    app = _open_tab(app, "UPEH")
    assert place_errors(app) == []
    assert "capa_upeh_editor_apply" in {button.key for button in app.button}


def test_a_bad_ratio_month_stops_the_step_submit_with_the_message() -> None:
    """STEP 제출은 측정률 조각을 팝업 안(`try` 밖)에서 자른다. 틀린 월은 traceback 이 아니다."""
    app = AppTest.from_string(
        _probed(_with_bad_month("RQ_LOT_RATIO"), "test-ref-perf-bad-ratio-month"),
        default_timeout=60,
    )
    app = _open_tab(app, "STEP 구성")
    assert place_errors(app) == []
    app = _add_step(app, "2A", "P200")
    assert _shows_bad_month(app, "RQ_LOT_RATIO")
    assert "test_month_updates" not in app.session_state


# ---------------------------------------------------------------- R3 설비대수 블록

EQUIPMENT_EDITORS = {
    "보유": ("RQ_EQP_OWN", "설비보유", "capa_eqp_own_editor"),
    "대여": ("RQ_EQP_LENT", "설비대여평가", "capa_eqp_lent_editor"),
    "가용": ("RQ_EQP_AVBL", "가용대수", "capa_eqp_avbl_editor"),
}


def _builds(app: AppTest) -> list[tuple[str, object]]:
    """이 회차에 만든 설비대수 양식 — ("양식", 구분)."""
    return list(app.session_state["test_equipment_builds"])


def _open_equipment(app: AppTest, sub_tab: str) -> AppTest:
    app.session_state[DATASET_KEY] = DATASET[f"{sub_tab}대수"]
    app.run()
    assert not app.exception
    return app


def test_the_equipment_block_builds_only_what_the_open_tabs_draw() -> None:
    """설비대수 표를 고르지 않으면 아무것도 만들지 않고, 고르면 그 표 하나의 양식만 만든다."""
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


# 설비대수 표시순서 범위에 `공정` 내림차순 규칙 하나 — 빈 프로필로는 정렬이 빠지거나 다른 범위로
# 정렬돼도 차례가 같아 보인다. 픽스처와 기대값이 같은 표를 쓴다.
EQUIPMENT_DESCENDING_ORDER = pd.DataFrame(
    [
        {
            "페이지 구분": scopes.PAGE_REFERENCE,
            "탭 구분": scopes.TAB_EQUIPMENT_COUNT,
            "정렬우선순위": 1,
            "분류컬럼": "공정",
            "정렬방식": "내림차순",
            "분류값": "",
            "값표시순서": None,
            "활성여부": "Y",
        }
    ]
)
_EQUIPMENT_DESCENDING = (
    "\nfrom capa_simulation.services import display_order_scopes as _scopes\n"
    'tables["RQ_DISPLAY_ORDER"] = pd.DataFrame([{\n'
    '    "페이지 구분": _scopes.PAGE_REFERENCE,\n'
    '    "탭 구분": _scopes.TAB_EQUIPMENT_COUNT,\n'
    '    "정렬우선순위": 1,\n'
    '    "분류컬럼": "공정",\n'
    '    "정렬방식": "내림차순",\n'
    '    "분류값": "",\n'
    '    "값표시순서": None,\n'
    '    "활성여부": "Y",\n'
    "}])\n"
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


def _descending_equipment_script() -> str:
    """설비대수 범위에 `공정` 내림차순 규칙 하나를 넣은 두 공정 픽스처."""
    return TWO_PROCESS_TEST_SCRIPT.replace(
        "\nactive = {", _EQUIPMENT_DESCENDING + "\nactive = {", 1
    )


@pytest.mark.parametrize("sub_tab", list(EQUIPMENT_EDITORS))
def test_each_equipment_form_follows_the_display_order(sub_tab: str) -> None:
    """보유·대여·가용 편집 양식도 다른 편집 표처럼 표시순서 범위(기준 정보 › 설비대수)로 줄을
    세운다."""
    table_name, value_column, editor_key = EQUIPMENT_EDITORS[sub_tab]
    app = AppTest.from_string(
        _probed(_descending_equipment_script(), f"test-ref-perf-form-order-{table_name}"),
        default_timeout=60,
    )
    app = _open_equipment(app, sub_tab)
    template = app.session_state["test_editor_templates"][editor_key]
    assert template["공정"].tolist() == ["Process-B", "Process-A"]
    expected = apply_display_order(
        equipment_count_to_edit_table(_month_slice(app, table_name), sub_tab, value_column),
        prepare_display_order(EQUIPMENT_DESCENDING_ORDER),
        scopes.PAGE_REFERENCE,
        scopes.TAB_EQUIPMENT_COUNT,
    )
    pd.testing.assert_frame_equal(template, expected)


def test_an_equipment_edit_in_display_order_lands_on_its_process(grid_calls: Calls) -> None:
    """표시순서로 줄이 바뀐 보유 그리드에서 첫 줄을 고쳐 적용하면 그 줄의 공정에 든다."""
    app = AppTest.from_string(
        _probed(_descending_equipment_script(), "test-ref-perf-equipment-order-apply"),
        default_timeout=60,
    )
    app = _open_equipment(app, "보유")
    assert _visible_keys(grid_calls) == ["Process-B", "Process-A"]
    app = _edit_and_apply(app, grid_calls, "capa_eqp_own_editor", "202608", 7.0)

    assert not app.exception
    assert place_errors(app) == []
    saved = app.session_state["test_month_updates"]["RQ_EQP_OWN"]
    assert dict(zip(saved["공정"], saved["설비보유"], strict=True)) == {
        "Process-A": 2.0,
        "Process-B": 7.0,
    }


def test_a_pending_equipment_edit_keeps_its_draft_and_lands_on_its_row(grid_calls: Calls) -> None:
    """보유 칸을 고친 채 다른 표로 옮기면 보유 양식은 만들지 않고(초안은 세션 칸 — 업무 키) 그 표의
    양식만 만든다. 돌아와 적용하면 그 행에 든다."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-equipment-pending"), default_timeout=60
    )
    app = _open_equipment(app, "보유")
    app = _grid_write(app, grid_calls, "Process-B", "202608", "7")

    app = _open_equipment(app, "대여")
    assert _builds(app) == [("양식", "대여")]
    app = _open_tab(app, "UPEH")
    assert _builds(app) == []
    assert "capa_eqp_own_editor_apply" not in {button.key for button in app.button}

    app = _open_equipment(app, "보유")
    app.button(key="capa_eqp_own_editor_apply").click().run()

    assert not app.exception
    assert place_errors(app) == []
    saved = app.session_state["test_month_updates"]["RQ_EQP_OWN"]
    assert dict(zip(saved["공정"], saved["설비보유"], strict=True)) == {
        "Process-A": 2.0,
        "Process-B": 7.0,
    }


# ---------------------------------------------------------------- R8 변경 개수


def _change_count(calls: Calls) -> int:
    """표 도구 막대 「적용 전 변경 (n)」 의 수(그리드 feed)."""
    return int(last(calls, feed_key(GRID_HOST))["counts"]["cells"])


def _action_row_lines(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown if "개 값" in str(item.value)]


def test_the_change_count_lives_only_in_the_grid_toolbar(grid_calls: Calls) -> None:
    """고친 수는 도구 막대 「적용 전 변경 (n)」 하나가 말하고 작업 줄은 거듭 적지 않는다(UI-TXT-07).
    양식과 같은 값으로 되돌린 칸은 초안에서 빠져 수도 0 이다(같은 값 적용으로 리비전만 오르는 일을
    막는 규칙과 같은 뜻)."""
    app = AppTest.from_string(
        _probed(TWO_PROCESS_TEST_SCRIPT, "test-ref-perf-change-count"), default_timeout=60
    )
    app = _open_tab(app, "효율")
    assert _change_count(grid_calls) == 0
    assert app.button(key="capa_run_rate_editor_apply").disabled

    app = _grid_write(app, grid_calls, "Process-A\x1f양산", "202608", "0.5")
    assert _change_count(grid_calls) == 1
    assert _action_row_lines(app) == []
    assert not app.button(key="capa_run_rate_editor_apply").disabled

    app = _grid_write(app, grid_calls, "Process-A\x1f양산", "202608", "0.9")
    assert _change_count(grid_calls) == 0
    assert app.button(key="capa_run_rate_editor_apply").disabled
