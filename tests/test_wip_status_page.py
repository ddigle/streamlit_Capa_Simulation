# Purpose: wip status page 관련 정상·예외·회귀 동작을 검증한다.

from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import capa_simulation
import capa_simulation.components.wip_status_dashboard as dashboard
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar


today = date.today()
start_date = today - timedelta(days=7)
end_date = today + timedelta(days=3)
calendar = build_iso_week_calendar(start_date, end_date)
months = calendar["생산계획년월"].drop_duplicates().astype(int).tolist()

display_order = pd.DataFrame(
    {
        "페이지 구분": ["표준 목표 Capa", "표준 목표 Capa"],
        "탭 구분": ["목표 Capa", "목표 Capa"],
        "정렬우선순위": [1, 1],
        "분류컬럼": ["제품정보", "제품정보"],
        "정렬방식": ["사용자지정", "사용자지정"],
        "분류값": ["Product-B", "Product-A"],
        "값표시순서": [1, 2],
        "활성여부": ["Y", "Y"],
    }
)
scenario_tables = {
    name: pd.DataFrame()
    for name in (
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
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
scenario_tables["RQ_RUN_DAY"] = pd.DataFrame(
    {
        "생산계획년월": months * 2,
        "공정": ["P-Process"] * len(months) + ["T-Process"] * len(months),
        "RUN_DAY": [30.0] * (len(months) * 2),
    }
)
active = {
    "reference_version": 1,
    "revision": 1,
    # 계산 캐시 키. 프로세스 전역 캐시라 다른 테스트 파일의 가짜 active 와 겹치면 안 된다.
    "content_token": "test-wip-status-page",
    "tables": scenario_tables,
}
reference_tables = {
    "RQ_MODULE": pd.DataFrame(),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": display_order,
}
required_equipment = pd.DataFrame(
    {
        "공정": ["T-Process", "P-Process", "T-Process", "P-Process"],
        "STEP_SEQ": ["T100", "P100", "T100", "P100"],
        "제품정보": ["Product-B", "Product-B", "Product-A", "Product-A"],
        "소요기준": ["WF", "CHIP", "WF", "CHIP"],
        "양산구분": ["양산"] * 4,
        "WF 구분": ["Core"] * 4,
    }
)
weekly_rows = []
for week in calendar.to_dict("records"):
    for process, basis in (("P-Process", "CHIP"), ("T-Process", "WF")):
        for product in ("Product-A", "Product-B"):
            weekly_rows.append(
                {
                    **week,
                    "공정": process,
                    "소요기준": basis,
                    "양산구분": "양산",
                    "제품정보": product,
                    "원수요_부하량": 100.0,
                    "STEP_소요대수": 1.0,
                    "공정 유효 Capa": 100.0,
                    "RUN_DAY": 30.0,
                    "대당 일 Capa": 100.0 / 30.0,
                    "가용대수": 2.0,
                    "일 표준 가능량": 200.0 / 30.0,
                }
            )
weekly_standard = pd.DataFrame(weekly_rows)

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_equipment_repository = equipment_cache.get_equipment_repository
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_month_table = scenario_state.scenario_month_table
original_capacity_and_demand = simulation_cache.get_scenario_capacity_and_demand
original_weekly_standard = simulation_cache.get_weekly_standard_target_capacity
original_figure_builder = dashboard.build_wip_status_grid_figure


# 설비 DB 가 채워진 정상 경로. 빈 표는 EMPTY_AVAILABILITY_SCRIPT 가 따로 검사한다.
availability = pd.DataFrame(
    [
        {"공정": process, "Weeknum": week["Weeknum"], "가용대수": 2.0}
        for week in calendar.to_dict("records")
        for process in ("P-Process", "T-Process")
    ]
)


class FakeEquipmentRepository:
    def load_standard_target_availability(self):
        return availability.copy()


reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
equipment_cache.get_equipment_repository = lambda _path: FakeEquipmentRepository()
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_month_table = (
    lambda scenario, name, _start, _end: scenario["tables"][name].copy()
)
simulation_cache.get_scenario_capacity_and_demand = lambda *_args, **_kwargs: (
    pd.DataFrame(),
    required_equipment.copy(),
)
simulation_cache.get_weekly_standard_target_capacity = (
    lambda **_kwargs: weekly_standard.copy()
)


def capture_figure(data, routes, products, _start_date, _end_date):
    st.session_state["captured_wip_products"] = products
    st.session_state["captured_wip_steps"] = (
        routes["STEP_SEQ"].drop_duplicates().astype(str).tolist()
    )
    st.session_state["captured_wip_days"] = data["일자"].nunique()
    return go.Figure()


dashboard.build_wip_status_grid_figure = capture_figure

try:
    PAGE_NAME = "wip_status.py"
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages" / PAGE_NAME
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    equipment_cache.get_equipment_repository = original_equipment_repository
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_month_table = original_scenario_month_table
    simulation_cache.get_scenario_capacity_and_demand = original_capacity_and_demand
    simulation_cache.get_weekly_standard_target_capacity = original_weekly_standard
    dashboard.build_wip_status_grid_figure = original_figure_builder
"""

EMPTY_AVAILABILITY_SCRIPT = TEST_SCRIPT.replace(
    "return availability.copy()",
    'return pd.DataFrame(columns=["공정", "Weeknum", "가용대수"])',
)
assert EMPTY_AVAILABILITY_SCRIPT != TEST_SCRIPT


def test_wip_status_page_renders_filtered_step_product_grid() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    # 공통 헤더가 `(구현중)` 을 제목에서 떼어 배지로 보여준다.
    assert app.title[0].value == "표준 대비 재공 현황"
    assert any("구현중" in element.value for element in app.markdown)
    assert [widget.label for widget in app.multiselect] == ["공정", "제품"]
    assert app.multiselect[0].options == ["P-Process", "T-Process"]
    assert app.multiselect[1].options == ["Product-B", "Product-A"]
    assert app.session_state["captured_wip_products"] == ["Product-B", "Product-A"]
    assert app.session_state["captured_wip_steps"] == ["P100", "T100"]
    assert app.session_state["captured_wip_days"] == 11
    assert any(button.label.endswith("조건 적용") for button in app.button)
    assert [metric.label for metric in app.metric] == [
        "선택 경로",
        "오늘 표준 충족",
        "오늘 Flow 부족",
        "표준 미설정",
    ]


def test_wip_status_page_explains_an_empty_equipment_db_instead_of_erroring() -> None:
    """설비 DB 가 비면 입력 표가 없는 이 화면에 "입력 표에 행이 없습니다" 오류가 떴다."""
    app = AppTest.from_string(EMPTY_AVAILABILITY_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert not app.error
    assert any("주차별 가용대수가 없어" in element.value for element in app.info)
    # 안내 뒤에 멈추므로 조회 조건과 지표는 그리지 않는다.
    assert not app.multiselect
    assert not app.metric
