from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation.components.grouped_monthly_table as grouped_table
import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache


def empty_display_order():
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


tables = {
    "RQ_UPEH": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "소요기준": ["PKG"],
            "UPEH": [100.0],
            "ST": [None],
        }
    ),
    "RQ_RUN_RATE": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "CAPA_RUN_RATE": [0.9],
        }
    ),
    "RQ_VITAL": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "편중률": [1.0],
        }
    ),
    "RQ_RUN_DAY": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}
    ),
    "RQ_LOT_RATIO": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "Lot 측정률": [1.0],
        }
    ),
    "RQ_WF_RATIO": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "WF측정률": [1.0],
        }
    ),
    "RQ_PKG_PLAN": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "CS": ["MP"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "생산수량": [100.0],
        }
    ),
    "RQ_YLD": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "EDS_수율": [1.0],
            "BE_수율": [1.0],
        }
    ),
    "RQ_REQB": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["PKG"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "소요기준": ["PKG"],
        }
    ),
    "RQ_MODULE": pd.DataFrame({"공정": ["Process-A"], "모듈수": [1.0]}),
    "RQ_EQP_OWN": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "설비보유": [2.0]}
    ),
    "RQ_EQP_LENT": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "설비대여평가": [0.0]}
    ),
    "RQ_EQP_AVBL": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "가용대수": [2.0]}
    ),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_CHIP_EQ": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": empty_display_order(),
}

active = {
    "reference_version": 1,
    "revision": 1,
    "tables": {
        name: frame.copy()
        for name, frame in tables.items()
        if name in scenario_state.EDITABLE_SCENARIO_TABLES
    },
}

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_table = scenario_state.scenario_table
original_apply_month_updates = scenario_state.apply_month_updates
original_hierarchical_render = hierarchical_table.render_hierarchical_monthly_table
original_grouped_render = grouped_table.render_grouped_monthly_table
original_unit_capacity = simulation_cache.get_unit_capacity
original_required_equipment = simulation_cache.get_required_equipment
original_securement_rate = simulation_cache.get_securement_rate

reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: tables
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_table = lambda scenario, name: scenario["tables"][name].copy()


def capture_month_updates(_scenario, replacements, _start, _end):
    st.session_state["test_step_reqb_rows"] = len(replacements["RQ_REQB"])
    return _scenario


scenario_state.apply_month_updates = capture_month_updates
hierarchical_table.render_hierarchical_monthly_table = lambda *_args, **_kwargs: None
grouped_table.render_grouped_monthly_table = lambda *_args, **_kwargs: None

simulation_cache.get_unit_capacity = lambda **_kwargs: pd.DataFrame()
simulation_cache.get_required_equipment = lambda **_kwargs: pd.DataFrame(
    {
        "생산계획년월": [202608],
        "Area_Name": ["Main"],
        "공정": ["Process-A"],
        "양산구분": ["양산"],
        "제품정보": ["Product-A"],
        "Stack": ["8H"],
        "Capa Code": ["CAPA-A"],
        "Customer": ["Customer-A"],
        "CS": ["MP"],
        "WF 구분": ["PKG"],
        "STEP_SEQ": ["P100"],
        "MCP_SEQ": ["1A"],
        "소요기준": ["PKG"],
        "부하량": [100.0],
        "대당 Capa": [100.0],
        "소요대수": [1.0],
    }
)
simulation_cache.get_securement_rate = lambda *_args: pd.DataFrame(
    {
        "생산계획년월": [202608],
        "공정": ["Process-A"],
        "가용대수": [2.0],
        "소요대수": [1.0],
        "확보율": [2.0],
    }
)

try:
    st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")
    page = Path("app_pages/capacity_standards.py")
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_table = original_scenario_table
    scenario_state.apply_month_updates = original_apply_month_updates
    hierarchical_table.render_hierarchical_monthly_table = original_hierarchical_render
    grouped_table.render_grouped_monthly_table = original_grouped_render
    simulation_cache.get_unit_capacity = original_unit_capacity
    simulation_cache.get_required_equipment = original_required_equipment
    simulation_cache.get_securement_rate = original_securement_rate
"""

PROCESS_TEST_SCRIPT = TEST_SCRIPT.replace(
    "app_pages/capacity_standards.py",
    "app_pages/process_securement.py",
)
LOAD_TEST_SCRIPT = TEST_SCRIPT.replace(
    "app_pages/capacity_standards.py",
    "app_pages/load_conversion.py",
)


def test_capacity_editors_show_route_keys_without_exceptions() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert len(app.dataframe) == 7
    upeh_columns = list(app.dataframe[1].value.columns)
    lot_ratio_columns = list(app.dataframe[4].value.columns)
    wf_ratio_columns = list(app.dataframe[5].value.columns)
    assert upeh_columns[:4] == ["공정", "STEP_SEQ", "MCP_SEQ", "Area_Name"]
    assert lot_ratio_columns[:4] == ["공정", "STEP_SEQ", "MCP_SEQ", "Area_Name"]
    assert wf_ratio_columns[:4] == ["공정", "STEP_SEQ", "MCP_SEQ", "Area_Name"]
    assert {uploader.label for uploader in app.file_uploader}.issuperset(
        {
            "RQ_UPEH CSV 선택",
            "RQ_RUN_RATE CSV 선택",
            "RQ_VITAL CSV 선택",
            "RQ_LOT_RATIO CSV 선택",
            "RQ_WF_RATIO CSV 선택",
            "RQ_RUN_DAY CSV 선택",
        }
    )


def test_load_input_tabs_expose_plan_and_yield_csv_round_trip() -> None:
    app = AppTest.from_string(LOAD_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert {uploader.label for uploader in app.file_uploader}.issuperset(
        {"RQ_PKG_PLAN CSV 선택", "RQ_YLD CSV 선택"}
    )


def test_equipment_tab_exposes_three_rq_csv_inputs() -> None:
    app = AppTest.from_string(PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert {uploader.label for uploader in app.file_uploader}.issuperset(
        {
            "RQ_EQP_OWN CSV 선택",
            "RQ_EQP_LENT CSV 선택",
            "RQ_EQP_AVBL CSV 선택",
        }
    )


def test_required_equipment_detail_exposes_route_filters() -> None:
    app = AppTest.from_string(PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    required_detail = next(toggle for toggle in app.toggle if toggle.label == "상세")
    app = required_detail.set_value(True).run()

    assert not app.exception
    filter_labels = [widget.label for widget in app.multiselect]
    assert "Step" in filter_labels
    assert "MCP" in filter_labels


def test_step_editor_clones_the_selected_route_in_one_submit() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    new_mcp = next(widget for widget in app.text_input if widget.label == "신규 MCP_SEQ")
    app = new_mcp.set_value("2A").run()
    new_step = next(widget for widget in app.text_input if widget.label == "신규 STEP_SEQ")
    app = new_step.set_value("P200").run()
    add_button = next(button for button in app.button if button.label == "STEP 일괄 추가")
    app = add_button.click().run()

    assert not app.exception
    assert app.session_state["test_step_reqb_rows"] == 2
