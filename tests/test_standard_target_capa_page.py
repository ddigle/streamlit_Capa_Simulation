from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache


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
    )
}
scenario_tables["RQ_UPEH"] = pd.DataFrame({"생산계획년월": [202608]})
scenario_tables["RQ_RUN_DAY"] = pd.DataFrame(
    {"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}
)
scenario_tables["RQ_REQB"] = pd.DataFrame(
    {"공정": ["Process-A", "Process-B"], "양산구분": ["양산", "양산"]}
)
active = {"reference_version": 1, "revision": 1, "tables": scenario_tables}
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

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_equipment_repository = equipment_cache.get_equipment_repository
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_table = scenario_state.scenario_table
original_scenario_month_table = scenario_state.scenario_month_table
original_unit_capacity = simulation_cache.get_unit_capacity
original_required_equipment = simulation_cache.get_required_equipment
original_hierarchical_render = hierarchical_table.render_hierarchical_monthly_table


class FakeEquipmentRepository:
    def load_standard_target_availability(self):
        return availability.copy()

    def save_standard_target_availability(self, data):
        return data.copy()

    def clear_standard_target_availability(self):
        return None

reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
equipment_cache.get_equipment_repository = lambda _path: FakeEquipmentRepository()
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_table = lambda scenario, name: scenario["tables"][name].copy()
scenario_state.scenario_month_table = (
    lambda scenario, name, _start, _end: scenario["tables"][name].copy()
)
simulation_cache.get_unit_capacity = lambda **_kwargs: pd.DataFrame()
simulation_cache.get_required_equipment = lambda **_kwargs: required_equipment.copy()


def capture_table(data, **kwargs):
    st.session_state["captured_week_columns"] = [
        column for column in data.columns if str(column).startswith("26-W")
    ]
    st.session_state["captured_classification_columns"] = kwargs["classification_columns"]


hierarchical_table.render_hierarchical_monthly_table = capture_table

try:
    st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")
    page = Path("app_pages/standard_target_capa.py")
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    equipment_cache.get_equipment_repository = original_equipment_repository
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_table = original_scenario_table
    scenario_state.scenario_month_table = original_scenario_month_table
    simulation_cache.get_unit_capacity = original_unit_capacity
    simulation_cache.get_required_equipment = original_required_equipment
    hierarchical_table.render_hierarchical_monthly_table = original_hierarchical_render
"""


def test_standard_target_page_renders_weeknum_plotly_table() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert app.session_state["captured_week_columns"] == [
        "26-W32",
        "26-W33",
        "26-W34",
        "26-W35",
        "26-W36",
    ]
    assert app.session_state["captured_classification_columns"] == ["공정", "소요기준"]
    assert any(widget.label == "공정 필터" for widget in app.multiselect)
    assert any(widget.label == "가용설비 CSV 선택" for widget in app.file_uploader)
    subheaders = [element.value for element in app.subheader]
    assert subheaders.index("주차별 일 표준 가능량") < subheaders.index("주차별 가용설비 CSV")

    process_filter = next(widget for widget in app.multiselect if widget.label == "공정 필터")
    assert process_filter.value == []
    app = process_filter.set_value(["Process-A"]).run()

    assert not app.exception
    restore_button = next(button for button in app.button if button.label == "공용 기본값으로 복원")
    app = restore_button.click().run()

    assert not app.exception
    process_filter = next(widget for widget in app.multiselect if widget.label == "공정 필터")
    assert process_filter.value == []

    detail_toggle = next(widget for widget in app.toggle if widget.label == "상세")
    app = detail_toggle.set_value(True).run()

    assert not app.exception
    assert app.session_state["captured_classification_columns"] == [
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
    ]
