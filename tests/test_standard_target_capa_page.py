# Purpose: standard target capa page 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.scenario_preset_state import (
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
    STANDARD_TARGET_SHOW_DETAIL_KEY,
)

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.month_filter import filter_month_range


display_order = pd.DataFrame(
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
scenario_tables = {
    name: pd.DataFrame()
    for name in (
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_REQB",
        # RQ_CHIP_QTY·RQ_CHIP_EQ 는 가상 제품 복제 등록을 위해 시나리오 소유로 승격됐다.
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
    )
}
scenario_tables["RQ_UPEH"] = pd.DataFrame({"생산계획년월": [202608]})
scenario_tables["RQ_RUN_DAY"] = pd.DataFrame(
    {"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}
)
scenario_tables["RQ_PKG_PLAN"] = pd.DataFrame(
    {
        "생산계획년월": [202608],
        "양산구분": ["양산"],
        "제품정보": ["Product-A"],
        "Stack": ["8H"],
        "Capa Code": ["CAPA-A"],
        "Customer": ["Customer-A"],
        "CS": ["MP"],
        "생산수량": [50.0],
    }
)
scenario_tables["RQ_REQB"] = pd.DataFrame(
    {"공정": ["Process-A", "Process-B"], "양산구분": ["양산", "양산"]}
)
active = {
    "reference_version": 1,
    "revision": 1,
    # 계산 캐시 키. 프로세스 전역 캐시라 다른 테스트 파일의 가짜 active 와 겹치면 안 된다.
    "content_token": "test-standard-target-capa-page",
    "tables": scenario_tables,
}
reference_tables = {
    "RQ_MODULE": pd.DataFrame(),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": display_order,
}
required_equipment = pd.DataFrame(
    {
        "생산계획년월": [202608],
        "공정": ["Process-A"],
        "소요기준": ["WF"],
        "양산구분": ["양산"],
        "제품정보": ["Product-A"],
        "Stack": ["8H"],
        "Capa Code": ["CAPA-A"],
        "Customer": ["Customer-A"],
        "CS": ["MP"],
        "WF 구분": ["Core"],
        "부하량": [100.0],
        "소요대수": [1.0],
    }
)
availability = pd.DataFrame(
    {
        "공정": ["Process-A"] * 5,
        "Weeknum": ["26-W32", "26-W33", "26-W34", "26-W35", "26-W36"],
        "가용대수": [2.0] * 5,
    }
)
# 한 주만 지우면 `누락 공정·주차 확인` 안내가 뜬다. 기본은 꺼 두어 다른 테스트의 화면을
# 건드리지 않는다.
DROP_ONE_WEEK = False
if DROP_ONE_WEEK:
    availability = availability.loc[availability["Weeknum"].ne("26-W33")].reset_index(drop=True)

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_equipment_repository = equipment_cache.get_equipment_repository
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_table = scenario_state.scenario_table
original_scenario_month_table = scenario_state.scenario_month_table
original_capacity_and_demand = simulation_cache.get_scenario_capacity_and_demand
original_hierarchical_render = hierarchical_table.render_hierarchical_monthly_table


class FakeEquipmentRepository:
    def load_standard_target_availability(self):
        return availability.copy()

    def save_standard_target_availability(self, data):
        # 붙여넣기 팝업이 저장소에 무엇을 넘겼는지 보려고 잡아 둔다.
        st.session_state["captured_saved_availability"] = data.copy()
        return data.copy()

    def clear_standard_target_availability(self):
        return None

reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
equipment_cache.get_equipment_repository = lambda _path: FakeEquipmentRepository()
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_table = lambda scenario, name: scenario["tables"][name].copy()
# 월 인자를 버리면 화면이 어떤 달을 요청하든 결과가 같아진다. 월 슬라이스가 곧 어떤 주차가
# 살아남는지를 정하므로(월 경계 주차는 조회일의 달 바깥에 귀속될 수 있다) 운영과 같은
# 함수로 실제로 자른다. `tests/test_e2e_boundary_week.py` 가 그 경계를 따로 고정한다.
scenario_state.scenario_month_table = lambda scenario, name, start, end: filter_month_range(
    scenario["tables"][name], start, end, name
)
# 운영에서는 이 래퍼 안에서 월 슬라이스를 한다. 키의 뒤 두 칸이 화면이 계산한 시작·종료 월이다.
simulation_cache.get_scenario_capacity_and_demand = lambda cache_key, **_kwargs: (
    pd.DataFrame(),
    filter_month_range(required_equipment, cache_key[2], cache_key[3], "소요대수 상세"),
)


def capture_table(data, **kwargs):
    st.session_state["captured_week_columns"] = [
        column for column in data.columns if str(column).startswith("26-W")
    ]
    st.session_state["captured_classification_columns"] = kwargs["classification_columns"]
    week_columns = [column for column in data.columns if str(column).startswith("26-W")]
    if week_columns and not data.empty:
        st.session_state["captured_first_week_value"] = float(data.iloc[0][week_columns[0]])


hierarchical_table.render_hierarchical_monthly_table = capture_table

original_download_button = st.download_button


def record_download_button(label, *args, **kwargs):
    # 내보낸 바이트는 위젯 proto 에 실리지 않는다. 파일이 원본 공정명인지 보려면 여기서
    # 잡아 두는 수밖에 없다.
    captured = st.session_state.setdefault("captured_download_data", {})
    captured[kwargs.get("key")] = kwargs.get("data")
    return original_download_button(label, *args, **kwargs)


# 화면 표기만 표시명으로 바꾼다. 페이지는 exec 로 새로 읽히므로 모듈 속성을 갈아끼우면
# 페이지의 `from ... import get_process_labels` 가 이 가짜를 집는다.
APPLY_RENAME = False
original_get_process_labels = process_labels_module.get_process_labels
# **표시명이 없는 경우에도 반드시 갈아끼운다.** 진짜 `get_process_labels` 는
# `settings.DUCKDB_PATH` 의 **공용 프로필**을 읽는데, 그것은 시나리오가 아니라 그 PC 의 DB 에
# 딸린 상태다. 갈아끼우지 않으면 이 테스트는 「이 PC 에는 표시명이 없다」에 기대게 되고,
# 표시명을 실제로 쓰는 환경에서는 같은 코드에서 실패한다 — 사내 실데이터에서 그렇게 됐다.
if APPLY_RENAME:
    rename_rules = pd.DataFrame(
        [("Process-A", "가공"), ("Pre B/D", "선다이싱")],
        columns=["공정", "표시명"],
    )
    rename_version = 7
else:
    rename_rules = pd.DataFrame(columns=["공정", "표시명"])
    rename_version = 0
process_profile = process_labels_module.process_labels_from_rules(rename_rules, rename_version)
process_labels_module.get_process_labels = lambda: process_profile

try:
    st.download_button = record_download_button
    st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")
    PAGE_NAME = "standard_target_capa.py"
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages" / PAGE_NAME
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    equipment_cache.get_equipment_repository = original_equipment_repository
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_table = original_scenario_table
    scenario_state.scenario_month_table = original_scenario_month_table
    simulation_cache.get_scenario_capacity_and_demand = original_capacity_and_demand
    hierarchical_table.render_hierarchical_monthly_table = original_hierarchical_render
    process_labels_module.get_process_labels = original_get_process_labels
    st.download_button = original_download_button
"""

RENAMED_TEST_SCRIPT = TEST_SCRIPT.replace("APPLY_RENAME = False", "APPLY_RENAME = True")
RENAMED_MISSING_WEEK_SCRIPT = RENAMED_TEST_SCRIPT.replace(
    "DROP_ONE_WEEK = False", "DROP_ONE_WEEK = True"
)


def test_standard_target_page_renders_weeknum_plotly_table() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    # 26-W36(8/31~9/6)은 9월 일수가 6일이라 202609 로 귀속된다. 이 시나리오에는 202608
    # 데이터만 있어 그 주는 빠지는 것이 맞다(2026-09-05 월 경계 규칙 변경).
    assert app.session_state["captured_week_columns"] == [
        "26-W32",
        "26-W33",
        "26-W34",
        "26-W35",
    ]
    assert app.session_state["captured_classification_columns"] == ["공정", "소요기준"]
    # 조회·집계 설정은 사이드바 조건 카드다(2026-09-29 사용자 결정).
    assert any(widget.label == "공정 필터" for widget in app.sidebar.multiselect)
    assert any(widget.label == "PKG 기준" for widget in app.sidebar.toggle)
    assert not app.main.multiselect and not app.main.toggle
    # 무엇을 볼지(`표시 항목`)는 결과를 통째로 바꾸는 하위 보기라 본문 결과 상자다 — 카드가 접혀
    # 있어도 지금 어느 결과인지 보인다(2026-09-29 사용자 결정).
    assert [widget.key for widget in app.main.segmented_control] == [
        "standard_target_output_metric"
    ]
    assert not app.sidebar.segmented_control
    assert "예외 처리 공정" in [expandable.label for expandable in app.expander]
    # 가용설비 입력은 결과 상자 위 작업 줄의 팝업이다. 닫혀 있는 동안 본문에 붙여넣기 칸이 없다.
    assert not app.text_area
    app.button(key="open_standard_target_availability_paste").click().run()
    assert not app.exception
    assert any(widget.label == "가용설비 표 붙여넣기" for widget in app.text_area)

    process_filter = app.multiselect(key=STANDARD_TARGET_PROCESS_SELECTION_KEY)
    assert process_filter.value == []
    app = process_filter.set_value(["Process-A"]).run()

    assert not app.exception
    restore_button = app.button(key="restore_standard_target_process_default")
    app = restore_button.click().run()

    assert not app.exception
    process_filter = app.multiselect(key=STANDARD_TARGET_PROCESS_SELECTION_KEY)
    assert process_filter.value == []

    detail_toggle = app.toggle(key=STANDARD_TARGET_SHOW_DETAIL_KEY)
    app = detail_toggle.set_value(True).run()

    assert not app.exception
    assert app.session_state["captured_classification_columns"] == [
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
    ]


def test_standard_target_page_toggles_pkg_equivalent_output() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert app.session_state["captured_first_week_value"] == pytest.approx(200.0 / 31.0)
    pkg_toggle = app.toggle(key="standard_target_pkg_basis")
    app = pkg_toggle.set_value(True).run()

    assert not app.exception
    assert app.session_state["captured_first_week_value"] == pytest.approx(100.0 / 31.0)
    assert "주차별 일 표준 가능량 (PKG Kea)" in [element.value for element in app.subheader]


def test_standard_target_page_analyzes_one_selected_process_week() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    output_selector = app.segmented_control(key="standard_target_output_metric")
    app = output_selector.set_value("로직 분석").run()

    assert not app.exception
    assert [widget.label for widget in app.selectbox] == [
        "Weeknum",
        "공정",
        "소요기준",
        "양산",
        "제품",
        "Stack",
        "WF 속성",
    ]
    app = app.selectbox(key="standard_target_logic_weeknum").set_value("26-W32").run()
    app = app.selectbox(key="standard_target_logic_process").set_value("Process-A").run()
    app = app.selectbox(key="standard_target_logic_basis").set_value("WF").run()
    app = app.selectbox(key="standard_target_logic_production_type").set_value("양산").run()
    app = app.selectbox(key="standard_target_logic_product").set_value("Product-A").run()
    app = app.selectbox(key="standard_target_logic_stack").set_value("8H").run()
    app = app.selectbox(key="standard_target_logic_wf_type").set_value("Core").run()

    assert not app.exception
    assert "일 표준 가능량 로직 분석" in [element.value for element in app.subheader]
    assert "일 표준 가능량 (매)" in [element.label for element in app.metric]
    assert len(app.dataframe) == 2


def test_saved_view_date_outside_the_current_period_is_clamped_with_a_notice() -> None:
    """조회기간을 바꾼 뒤 과거 리비전을 열어도 페이지가 죽지 않고 범위 안으로 맞춘다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["standard_target_start_date"] = date(2026, 6, 15)
    app.session_state["standard_target_end_date"] = date(2027, 3, 20)
    app = app.run()

    assert not app.exception
    assert app.session_state["standard_target_start_date"] == date(2026, 8, 1)
    assert app.session_state["standard_target_end_date"] == date(2026, 8, 31)
    assert any("조정됨" in element.value for element in app.caption)


def test_saved_view_dates_in_reverse_order_are_corrected() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["standard_target_start_date"] = date(2026, 8, 25)
    app.session_state["standard_target_end_date"] = date(2026, 8, 5)
    app = app.run()

    assert not app.exception
    assert app.session_state["standard_target_end_date"] == date(2026, 8, 25)
    # 두 조정 원인은 문구가 다르다. 한 깃발로 합치면 기간 안인 날짜에도 범위 문구가 뜬다.
    captions = [element.value for element in app.caption]
    assert any("시작일이 종료일보다 늦어" in caption for caption in captions)
    assert not any("조회기간 밖이라" in caption for caption in captions)


def test_fallback_constants_exist_in_the_page_option_lists() -> None:
    """폴백 상수는 persistence 가, 옵션 목록은 화면이 소유한다. 갈라지면 위젯이 죽는다."""
    from capa_simulation.persistence.models import (
        DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
        DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
    )

    page = (Path(__file__).resolve().parents[1] / "app_pages/standard_target_capa.py").read_text(
        encoding="utf-8"
    )

    assert f'"{DEFAULT_STANDARD_TARGET_DETAIL_LEVEL}"' in page
    assert f'"{DEFAULT_STANDARD_TARGET_OUTPUT_METRIC}"' in page


def test_saved_view_settings_outside_the_current_options_fall_back() -> None:
    """옵션 문자열이 바뀌어도 저장된 값 때문에 위젯 생성이 실패하지 않는다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["standard_target_output_metric"] = "일 최대 투입 가능량"
    app.session_state["standard_target_detail_level"] = "없어진 분류 수준"
    app.session_state["standard_target_show_detail"] = True
    app = app.run()

    assert not app.exception
    assert app.session_state["standard_target_output_metric"] == "일 표준 가능량"
    assert app.session_state["standard_target_detail_level"] == "제품정보"
    assert app.session_state["captured_classification_columns"] == [
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
    ]


# ------------------------------------------- 화면은 표시명, 파일은 원본


def _frame_with_value(app: AppTest, column: str, value: str):
    for frame in app.dataframe:
        data = frame.value
        if column in getattr(data, "columns", []) and value in set(data[column]):
            return data
    raise AssertionError(f"`{column}` 에 `{value}` 가 든 표가 없습니다.")


def test_exception_process_notice_shows_the_display_name() -> None:
    """`예외 처리 공정` 안내는 CSV 출구가 없는 순수 표시 상수 표다."""
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert _frame_with_value(app, "공정", "선다이싱") is not None


def test_exception_process_notice_stays_original_without_a_rename_profile() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert _frame_with_value(app, "공정", "Pre B/D") is not None


def test_weekly_availability_template_keeps_the_original_process_name() -> None:
    """양식 CSV 는 그대로 되붙는 왕복이다. 표시명이 새면 파서가 공정을 찾지 못한다."""
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    template = pd.read_csv(
        BytesIO(
            bytes(
                app.session_state["captured_download_data"][
                    "download_standard_target_availability_template"
                ]
            )
        ),
        encoding="utf-8-sig",
        dtype="object",
    )

    assert set(template["공정"]) == {"Process-A", "Process-B"}


def test_weekly_availability_template_carries_saved_counts_and_blanks_the_rest() -> None:
    """작업 줄 양식은 저장된 가용대수를 싣고, 저장값이 없는 공정·주차는 빈칸이다.

    예전에는 모든 칸이 0.0 이라, 한 공정만 고쳐 통째로 되붙이면 다른 공정이 0 대로 덮였다
    (2026-09-29 버그 보고). 가짜 저장소는 Process-A 의 26-W32~W36 만 2 대를 갖고 있다.
    """
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    template = pd.read_csv(
        BytesIO(
            bytes(
                app.session_state["captured_download_data"][
                    "download_standard_target_availability_template"
                ]
            )
        ),
        encoding="utf-8-sig",
        dtype="object",
    )
    saved_weeks = {"26-W32", "26-W33", "26-W34", "26-W35", "26-W36"}
    saved_cells = template["공정"].eq("Process-A") & template["Weeknum"].isin(saved_weeks)
    assert saved_cells.sum() == len(saved_weeks)
    assert template.loc[saved_cells, "가용대수"].eq("2.0").all()
    # 저장값이 없는 칸(Process-B 전부, 조회 범위에 걸친 저장 밖 주차)은 0 이 아니라 빈칸이다.
    assert template["공정"].eq("Process-B").any()
    assert template.loc[~saved_cells, "가용대수"].isna().all()


def test_availability_paste_keeps_blank_cells_and_says_so_before_applying() -> None:
    """팝업은 빈칸이 「그대로 둠」이라고 먼저 알리고, 빈칸 행은 저장소로 넘기지 않는다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    app.button(key="open_standard_target_availability_paste").click().run()

    assert not app.exception
    assert any("비운 칸은 저장된 값" in caption.value for caption in app.caption)
    app.text_area(key="standard_target_availability_clipboard_text").set_value(
        "공정\tWeeknum\t가용대수\nProcess-A\t26-W32\t\nProcess-B\t26-W32\t3\n"
    )
    next(button for button in app.button if button.label == "붙여넣기 적용").click().run()

    assert not app.exception
    assert not app.error
    saved = app.session_state["captured_saved_availability"]
    assert saved.to_dict("records") == [{"공정": "Process-B", "Weeknum": "26-W32", "가용대수": 3.0}]


def test_missing_availability_table_shows_the_display_name_with_a_source_notice() -> None:
    """누락 안내 표는 화면이라 표시명이고, 붙여넣을 원본이 어디 있는지 함께 알린다."""
    app = AppTest.from_string(RENAMED_MISSING_WEEK_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "누락 공정·주차 확인" in {expander.label for expander in app.expander}
    missing = _frame_with_value(app, "공정", "가공")
    assert missing["Weeknum"].tolist() == ["26-W33"]
    assert any("CSV 양식 다운로드" in caption.value for caption in app.caption)


def test_clearing_the_availability_asks_first() -> None:
    """입력 초기화는 되돌릴 수 없다. 팝업에서 확인해야 버튼이 눌린다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    app.button(key="open_standard_target_availability_clear").click().run()

    assert not app.exception
    assert app.button(key="clear_standard_target_availability").disabled
    app.checkbox(key="standard_target_clear_confirm").check().run()
    assert not app.exception
    assert not app.button(key="clear_standard_target_availability").disabled


def test_standard_target_guide_carries_what_left_the_body() -> None:
    from capa_simulation.components.page_guide import load_guide

    guide = load_guide("standard_target_capa")
    for text in (
        "대당 일 Capa** = 월간 공정별 대당 Capa ÷ `RUN_DAY`",
        "일 표준 가능량** = 대당 일 Capa × 주차별 가용대수",
        "PKG 환산",
        "ER 은 항상 제외",
        "월 경계 주차",
        "조화가중",
        "지금 사용자 세션에만",
        "설비 DuckDB",
        "예외 처리 공정",
    ):
        assert text in guide, text
