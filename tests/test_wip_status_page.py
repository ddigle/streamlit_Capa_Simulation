# Purpose: wip status page 관련 정상·예외·회귀 동작을 검증한다.

import pytest
from alert_marks import data_error_marks, events
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Expander, Status

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.navigation import STANDARD_TARGET_CAPA
from capa_simulation.page_tabs_state import tab_label

PROCESS_FILTER_KEY = "wip_status_process_filter"

TEST_SCRIPT = r"""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import capa_simulation
import capa_simulation.components.process_labels as process_labels_module
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
        "페이지 구분": ["표준 목표", "표준 목표"],
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
original_get_process_labels = process_labels_module.get_process_labels


# 설비 DB 가 채워진 정상 경로. 빈 표는 EMPTY_AVAILABILITY_SCRIPT 가 따로 검사한다.
availability = pd.DataFrame(
    [
        {"공정": process, "Weeknum": week["Weeknum"], "가용대수": 2.0}
        for week in calendar.to_dict("records")
        for process in ("P-Process", "T-Process")
    ]
)


class FakeEquipmentRepository:
    schema_ahead = None

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


def capture_figure(data, routes, products, _start_date, _end_date, process_labels=None):
    # 공정 표시명은 subplot 제목 라벨일 뿐이라 이 테스트가 보는 값에는 영향이 없다.
    st.session_state["captured_wip_labels"] = process_labels
    st.session_state["captured_wip_products"] = products
    st.session_state["captured_wip_steps"] = (
        routes["STEP_SEQ"].drop_duplicates().astype(str).tolist()
    )
    st.session_state["captured_wip_days"] = data["일자"].nunique()
    return go.Figure()


dashboard.build_wip_status_grid_figure = capture_figure
# 공정 표시명도 조회 경계다. 기본 매핑을 주입해 로컬 시뮬레이션 DB에 접근하지 않는다.
process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels()

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
    process_labels_module.get_process_labels = original_get_process_labels
"""

EMPTY_AVAILABILITY_SCRIPT = TEST_SCRIPT.replace(
    "return availability.copy()",
    'return pd.DataFrame(columns=["공정", "Weeknum", "가용대수"])',
)
assert EMPTY_AVAILABILITY_SCRIPT != TEST_SCRIPT


def test_wip_status_page_renders_filtered_step_product_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_profile_load(*args: object, **kwargs: object) -> None:
        raise AssertionError("화면 테스트는 로컬 공정 표시명 DB를 조회하면 안 됩니다.")

    monkeypatch.setattr(
        process_labels_module, "load_global_process_rename", unexpected_profile_load
    )
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    # 큰 제목은 「(구현중)」 을 뗀 이름이고(화면에서는 숨는다) 머리에 배지 줄이 없다 — 구현 중
    # 표지는 화면 탭 이름 곁이다(2026-11-09 보드 T8).
    assert app.title[0].value == "표준 대비 재공 현황"
    assert not any("-badge[" in str(element.value) for element in app.main.markdown)
    # 공정 · 제품과 「조건 적용」 은 사이드바 「재공 현황 조건」 카드의 폼이다(설계 규칙 UI-LAY-02 ·
    # UI-INP-04) — 본문에는 고르는 칸이 없다.
    assert not app.main.multiselect
    assert [widget.label for widget in app.sidebar.multiselect] == ["공정", "제품"]
    # 카드는 처음 펼친 채다 — 본문에 있을 때처럼 조건이 첫 화면에 보인다(2026-11-10 보드 Q-7).
    (card,) = [
        item
        for item in app.sidebar
        if isinstance(item, (Status, Expander)) and item.label == "재공 현황 조건"
    ]
    assert card.proto.expanded
    assert any(button.label.endswith("조건 적용") for button in app.sidebar.button)
    assert [widget.label for widget in app.multiselect] == ["공정", "제품"]
    # 카드의 두 칸은 이름 줄 + 고른 값 한 줄 팝오버이고 다중 선택 칸은 그 안이다 — 300px 카드에서
    # 칩이 한 줄에 하나씩 쌓여 칸 높이 상한에 잘리고 「조건 적용」 이 첫 화면 밖으로 밀린다(설계
    # 규칙 UI-LAY-06). 한 줄 글은 「첫 이름 외 n개」, 풍선은 전체 목록이다(UI-CON-04).
    popovers = app.sidebar.get("popover")
    # 글자는 마크다운 자리라 막아 둔 그대로다(`literal_markdown`).
    process_a, process_b, product_a, product_b = (
        literal_markdown(name) for name in ("P-Process", "T-Process", "Product-B", "Product-A")
    )
    assert [popover.proto.popover.label for popover in popovers] == [
        f"{process_a} 외 1개",
        f"{product_a} 외 1개",
    ]
    assert [popover.proto.popover.help for popover in popovers] == [
        f"{process_a} · {process_b}",
        f"{product_a} · {product_b}",
    ]
    assert [[widget.key for widget in popover.multiselect] for popover in popovers] == [
        [PROCESS_FILTER_KEY],
        ["wip_status_product_filter"],
    ]
    assert app.multiselect[0].options == ["P-Process", "T-Process"]
    assert app.multiselect[1].options == ["Product-B", "Product-A"]
    assert app.session_state["captured_wip_products"] == ["Product-B", "Product-A"]
    assert app.session_state["captured_wip_steps"] == ["P100", "T100"]
    # 표시명 매핑을 넘기는 배선이 사라지면 subplot 제목이 조용히 원본으로 돌아간다.
    assert app.session_state["captured_wip_labels"] is not None
    assert app.session_state["captured_wip_days"] == 11
    assert any(button.label.endswith("조건 적용") for button in app.button)
    assert [metric.label for metric in app.metric] == [
        "선택 경로",
        "오늘 표준 충족",
        "오늘 Flow 부족",
        "표준 미설정",
    ]
    # 격자를 읽는 법은 늘 서는 캡션이 아니라 구획 제목 풍선이다(설계 규칙 UI-TXT-01 · UI-TXT-02).
    (grid_heading,) = [item for item in app.markdown if "일별 재공·Flow" in str(item.value)]
    assert "Flow 막대는 표준 이상이면 초록색" in str(grid_heading.proto.help)
    assert "11일" in str(grid_heading.proto.help)
    assert not any("Flow 막대" in str(caption.value) for caption in app.caption)
    # 연결 계약 메모는 할 일 문서 몫이다 — 접힌 칸으로도 화면에 두지 않는다(UI-TXT-01).
    assert not [item.label for item in app.expander if "경계" in item.label]


@pytest.mark.parametrize("sample", [True, False])
def test_the_head_has_no_badge_line_on_either_side_of_the_switch(sample: bool) -> None:
    """머리에는 배지 줄(「구현중 · 인터랙티브 프로토타입 · … 미연결」)이 없다 — 구현 중 표지는 화면
    탭 이름 곁, 합성 샘플 표지는 머리 띠다(2026-11-09 보드 T8). 「샘플 데이터」 는 사이드바 줄이고
    끄면 자리 표지 「… 연결 대기」 가 무엇을 기다리는지 말한다."""
    from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY

    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state[SAMPLE_TOGGLE_KEY] = sample
    app.run()

    assert not app.exception
    assert not [
        str(item.value)
        for item in app.main.markdown
        if any(mark in str(item.value) for mark in ("인터랙티브 프로토타입", "미연결", "-badge["))
    ]
    assert app.toggle(key=SAMPLE_TOGGLE_KEY) in list(app.sidebar.toggle)
    pending = [item for item in app.get("html") if "연결 대기</strong>" in item.proto.body]
    assert bool(pending) is not sample


def test_wip_status_page_without_a_choice_stops_on_one_plain_line() -> None:
    """공정이나 제품을 다 비우면 그릴 것이 없어 멈춘다 — 파란 안내 상자 · 하는 법 없이 회색 평문
    한 줄이다(설계 규칙 UI-TXT-04)."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception

    app.multiselect(key=PROCESS_FILTER_KEY).set_value([])
    next(button for button in app.button if button.label.endswith("조건 적용")).click()
    app.run()

    assert not app.exception
    assert not app.info
    assert "고른 공정 또는 제품이 없습니다." in [str(caption.value) for caption in app.caption]
    assert not app.metric
    # 비운 칸의 한 줄 글은 고르라는 자리 글이고 풍선이 없다.
    process_popover = app.sidebar.get("popover")[0]
    assert process_popover.proto.popover.label == "표시할 공정 선택"
    assert not process_popover.proto.popover.help


def test_an_empty_equipment_db_stops_with_the_mark_and_the_alarm_opens_the_target() -> None:
    """설비 DB 가 비면 입력 표가 없는 이 화면에 "입력 표에 행이 없습니다" 오류가 떴다. 채울 입력이
    빠진 멈춤은 「데이터 Error」 마크다 — 자리에 노란 상자 · 「표준 목표 열기」 링크가 없고 글은
    알림이며, 그 줄의 「그 화면으로」 가 표준 목표를 연다."""
    app = AppTest.from_string(EMPTY_AVAILABILITY_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert not app.error and not app.warning
    # 네비게이션 없는 시험에서 링크는 캡션 글로 물러선다 — 그 글도 없다.
    assert not any("표준 목표" in str(item.value) for item in app.caption)
    assert data_error_marks(app) == 1
    (note,) = events(app, "WIP-01")
    assert note["short"] == "재공 현황을 그리지 못했습니다 — 주차별 가용대수 없음"
    assert "주차별 가용대수가 없어" in note["full"] and "`" not in note["full"]
    assert (note["page"], note["href"]) == (
        tab_label(STANDARD_TARGET_CAPA),
        STANDARD_TARGET_CAPA.href,
    )
    # 줄의 화면 칸이 표준 목표다 — 어느 화면이 멈췄는지는 전문이 말하고, 「여기」 라고 쓰지 않는다.
    assert note["full"].startswith("재공 현황 — "), note["full"]
    assert "여기" not in note["full"], note["full"]
    # 마크 뒤에 멈추므로 조회 조건과 지표는 그리지 않는다.
    assert not app.multiselect
    assert not app.metric
