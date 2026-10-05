# Purpose: 월 경계 주차가 표준 목표 Capa·재공 현황에서 사라지지 않는지 끝에서 끝까지 고정한다.

"""월 경계 주차 회귀 고정 (E2E).

달력 주가 두 달에 걸치면 그 주의 귀속 달은 **일수가 더 많은 달** 하나뿐이고, 정본은
`services/iso_week_calendar.owning_month` 다. 폐기된 규칙 둘이 각자 다시 구현되어 있던 동안
경계 주차는 **오류 없이 사라졌다** — 행 자체가 없으니 결측 검사에도 걸리지 않는다.

- 「조회일이 속한 달」로 월 슬라이스를 만들던 자리(표준 목표 Capa 화면). 사용자가 요청한
  날이 든 주가 inner 조인에서 통째로 빠진다.
- 「월요일이 속한 달」을 다시 만들던 자리(재공 일 단위 확장·로직 분석). 그 주 7일이 통째로
  버려져 화면은 `표준 미설정` 을 보여 주고 원인을 가용대수로 오지목한다.

두 규칙은 서로 다른 주에서 어긋나므로 경계 주차를 **둘** 고정한다. 아래 상수의 주석에 그
날짜가 왜 경계인지(= `owning_month` 가 무엇을 돌려주는지) 계산 근거를 적어 둔다.
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.services.iso_week_calendar import owning_month
from capa_simulation.services.standard_target_capacity import (
    build_weekly_standard_target_capacity,
)
from capa_simulation.services.standard_target_logic import (
    build_standard_target_logic_analysis,
)
from capa_simulation.services.wip_status import (
    build_wip_history_demo,
    expand_weekly_product_standard_to_daily,
)

# 26-W05 = 2026-01-26(월) ~ 2026-02-01(일). 1월 6일 · 2월 1일이므로 `owning_month` 는 202601.
# 조회 시작일 2026-02-01 은 2월인데 **그 날이 든 주는 1월 것**이라, 「조회일이 속한 달」로
# 월을 자르면 사용자가 콕 집어 요청한 날의 주가 빠진다.
BOUNDARY_START_DATE = date(2026, 2, 1)
QUERY_START_WEEK = "26-W05"
QUERY_START_WEEK_MONTH = 202601

# 26-W14 = 2026-03-30(월) ~ 2026-04-05(일). 3월 2일 · 4월 5일이므로 `owning_month` 는 202604.
# 월요일은 3월인데 **그 주는 4월 것**이라, 「월요일이 속한 달」로 월을 만들면 어긋난다.
# 26-W05 는 월요일도 1월이라 이 규칙에서는 어긋나지 않는다 — 그래서 주차를 둘 쓴다.
BOUNDARY_WEEK = "26-W14"
BOUNDARY_WEEK_MONDAY = date(2026, 3, 30)
BOUNDARY_WEEK_SUNDAY = date(2026, 4, 5)
BOUNDARY_WEEK_MONTH = 202604

# 조회기간은 2026-02 ~ 2026-03 이지만 그 안의 주차는 202601 · 202604 에도 귀속된다.
QUERY_END_DATE = date(2026, 3, 31)
SLICE_MONTHS = [202601, 202602, 202603, 202604]
QUERY_WEEKS = [f"26-W{number:02d}" for number in range(5, 15)]

# 부하량 100 ÷ 소요대수 2 = 대당 Capa 50, ÷ RUN_DAY 30 = 대당 일 Capa, × 가용대수 3 = 5.0.
RUN_DAY = 30.0
AVAILABLE_UNITS = 3.0
DAILY_STANDARD = 100.0 / 2.0 / RUN_DAY * AVAILABLE_UNITS


def _required_equipment(months: list[int]) -> pd.DataFrame:
    """월마다 한 줄인 소요대수 상세. 경계 주차가 붙는 달이 있는지만 가른다."""
    return pd.DataFrame(
        {
            "생산계획년월": months,
            "공정": ["Process-A"] * len(months),
            "소요기준": ["WF"] * len(months),
            "양산구분": ["양산"] * len(months),
            "제품정보": ["Product-A"] * len(months),
            "Stack": ["8H"] * len(months),
            "Capa Code": ["CAPA-A"] * len(months),
            "Customer": ["Customer-A"] * len(months),
            "CS": ["MP"] * len(months),
            "WF 구분": ["Core"] * len(months),
            "부하량": [100.0] * len(months),
            "소요대수": [2.0] * len(months),
        }
    )


def _run_day(months: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": months,
            "공정": ["Process-A"] * len(months),
            "RUN_DAY": [RUN_DAY] * len(months),
        }
    )


def _availability(weeks: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-A"] * len(weeks),
            "Weeknum": weeks,
            "가용대수": [AVAILABLE_UNITS] * len(weeks),
        }
    )


# --------------------------------------------------------------- 경계라는 전제부터 고정한다


def test_the_hardcoded_dates_are_really_month_boundary_weeks() -> None:
    """연중 어느 주가 경계인지는 해마다 다르다. 위 상수가 여전히 경계인지 먼저 확인한다.

    아래 두 `!=` 가 이 파일 전체의 판별력이다. 둘이 같아지면(= 귀속 규칙이 바뀌면) 나머지
    테스트는 통과하면서도 아무것도 가르지 못하는 빈 검사가 된다.
    """
    week_start = BOUNDARY_START_DATE - timedelta(days=BOUNDARY_START_DATE.weekday())
    assert owning_month(week_start) == QUERY_START_WEEK_MONTH
    # 폐기된 「조회일이 속한 달」 규칙과 갈린다.
    assert QUERY_START_WEEK_MONTH != BOUNDARY_START_DATE.year * 100 + BOUNDARY_START_DATE.month

    assert owning_month(BOUNDARY_WEEK_MONDAY) == BOUNDARY_WEEK_MONTH
    # 폐기된 「월요일이 속한 달」 규칙과 갈린다.
    assert BOUNDARY_WEEK_MONTH != BOUNDARY_WEEK_MONDAY.year * 100 + BOUNDARY_WEEK_MONDAY.month


def test_the_query_month_slice_alone_would_drop_both_boundary_weeks() -> None:
    """화면이 조회일의 달로만 잘랐을 때 무엇이 사라지는지 계산으로 보여 준다.

    이 테스트는 결함이 아니라 **판별기**다. 아래 화면 테스트가 26-W05 를 찾아내는 것이
    당연해서가 아니라 월 슬라이스를 주차 귀속 달로 넓혔기 때문임을 여기서 못박는다.
    """
    naive_months = [202602, 202603]
    weekly = build_weekly_standard_target_capacity(
        required_equipment=_required_equipment(naive_months),
        run_day=_run_day(naive_months),
        weekly_availability=_availability(QUERY_WEEKS),
        start_date=BOUNDARY_START_DATE,
        end_date=QUERY_END_DATE,
        detail_level="공정",
    )

    produced = set(weekly["Weeknum"])
    assert QUERY_START_WEEK not in produced
    assert BOUNDARY_WEEK not in produced

    widened = build_weekly_standard_target_capacity(
        required_equipment=_required_equipment(SLICE_MONTHS),
        run_day=_run_day(SLICE_MONTHS),
        weekly_availability=_availability(QUERY_WEEKS),
        start_date=BOUNDARY_START_DATE,
        end_date=QUERY_END_DATE,
        detail_level="공정",
    )

    assert set(widened["Weeknum"]) == set(QUERY_WEEKS)


# ------------------------------------------------------------------------- 표준 목표 Capa 화면

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

MONTHS = [202601, 202602, 202603, 202604]
WEEKS = [f"26-W{number:02d}" for number in range(5, 15)]
PROCESSES = ["Process-A"]

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
# 계산 캐시와 시나리오 표 두 경계를 아래에서 갈아끼우므로 화면이 실제로 손대는 표만 둔다.
# RQ_UPEH 는 조회기간 교집합, RQ_RUN_DAY·RQ_PKG_PLAN 은 월 슬라이스, RQ_REQB 는 공정 목록.
scenario_tables = {
    # 조회기간을 2026-02 ~ 2026-03 으로 확정한다. 화면 기본 조회일이 2/1 ~ 3/31 이 된다.
    "RQ_UPEH": pd.DataFrame({"생산계획년월": [202602, 202603]}),
    "RQ_RUN_DAY": pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": PROCESSES * len(MONTHS),
            "RUN_DAY": [30.0] * len(MONTHS),
        }
    ),
    "RQ_PKG_PLAN": pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "양산구분": ["양산"] * len(MONTHS),
            "제품정보": ["Product-A"] * len(MONTHS),
            "Stack": ["8H"] * len(MONTHS),
            "Capa Code": ["CAPA-A"] * len(MONTHS),
            "Customer": ["Customer-A"] * len(MONTHS),
            "CS": ["MP"] * len(MONTHS),
            "생산수량": [50.0] * len(MONTHS),
        }
    ),
    "RQ_REQB": pd.DataFrame({"공정": PROCESSES, "양산구분": ["양산"]}),
}
active = {
    "reference_version": 1,
    "revision": 1,
    # 계산 캐시 키. 프로세스 전역 캐시라 다른 테스트 파일의 가짜 active 와 겹치면 안 된다.
    "content_token": "test-e2e-boundary-week",
    "tables": scenario_tables,
}
reference_tables = {
    "RQ_MODULE": pd.DataFrame(),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": display_order,
}
required_equipment = pd.DataFrame(
    {
        "생산계획년월": MONTHS,
        "공정": PROCESSES * len(MONTHS),
        "소요기준": ["WF"] * len(MONTHS),
        "양산구분": ["양산"] * len(MONTHS),
        "제품정보": ["Product-A"] * len(MONTHS),
        "Stack": ["8H"] * len(MONTHS),
        "Capa Code": ["CAPA-A"] * len(MONTHS),
        "Customer": ["Customer-A"] * len(MONTHS),
        "CS": ["MP"] * len(MONTHS),
        "WF 구분": ["Core"] * len(MONTHS),
        "부하량": [100.0] * len(MONTHS),
        "소요대수": [2.0] * len(MONTHS),
    }
)
availability = pd.DataFrame(
    {
        "공정": PROCESSES * len(WEEKS),
        "Weeknum": WEEKS,
        "가용대수": [3.0] * len(WEEKS),
    }
)

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_equipment_repository = equipment_cache.get_equipment_repository
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_month_table = scenario_state.scenario_month_table
original_capacity_and_demand = simulation_cache.get_scenario_capacity_and_demand
original_hierarchical_render = hierarchical_table.render_hierarchical_monthly_table
original_get_process_labels = process_labels_module.get_process_labels


class FakeEquipmentRepository:
    schema_ahead = None

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
# **월 인자를 반드시 쓴다.** 그냥 통째로 돌려주면 화면이 아무 달이나 요청해도 결과가 같아져
# 이 파일이 고정하려는 월 슬라이스 자체가 검사에서 빠진다. 운영과 같은 함수로 자른다.
scenario_state.scenario_month_table = lambda scenario, name, start, end: filter_month_range(
    scenario["tables"][name], start, end, name
)
# 운영에서는 이 래퍼 안에서 월 슬라이스를 한다(services/simulation_cache.py). 키의 뒤 두 칸이
# 화면이 계산한 시작·종료 월이고, 여기서 그대로 잘라야 경계 주차의 달이 빠진 것이 드러난다.
simulation_cache.get_scenario_capacity_and_demand = lambda cache_key, **_kwargs: (
    pd.DataFrame(),
    filter_month_range(required_equipment, cache_key[2], cache_key[3], "소요대수 상세"),
)


def capture_table(data, **kwargs):
    st.session_state["captured_week_columns"] = [
        column for column in data.columns if str(column).startswith("26-W")
    ]
    week_columns = [column for column in data.columns if str(column).startswith("26-W")]
    if week_columns and not data.empty:
        st.session_state["captured_first_week_value"] = float(data.iloc[0][week_columns[0]])


hierarchical_table.render_hierarchical_monthly_table = capture_table
# 공정 표시명도 조회 경계다. 기본 매핑을 주입해 로컬 시뮬레이션 DB에 접근하지 않는다.
process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels()

try:
    st.session_state["production_month_range_v2"] = ("2026-02", "2026-03")
    PAGE_NAME = "standard_target_capa.py"
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages" / PAGE_NAME
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    equipment_cache.get_equipment_repository = original_equipment_repository
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_month_table = original_scenario_month_table
    simulation_cache.get_scenario_capacity_and_demand = original_capacity_and_demand
    hierarchical_table.render_hierarchical_monthly_table = original_hierarchical_render
    process_labels_module.get_process_labels = original_get_process_labels
"""


def _page_errors(app: AppTest) -> list[str]:
    """화면의 실패는 예외가 아니라 `st.error` + `st.stop` 이다. 먼저 이것부터 읽는다."""
    return [element.value for element in app.error]


def test_the_page_keeps_the_week_that_holds_the_requested_start_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """조회 시작일 2026-02-01 이 든 26-W05 는 1월 귀속이다. 그래도 결과표에 나와야 한다.

    화면 기본 조회일은 2026-02-01 ~ 2026-03-31 이고 조회기간은 2026-02 ~ 2026-03 이다.
    월 슬라이스를 조회일의 달로만 만들면 26-W05(202601)·26-W14(202604) 가 inner 조인에서
    통째로 빠지는데, 빈칸이 아니라 **열 자체가 없다**. 경고도 남지 않는다.
    """

    def unexpected_profile_load(*args: object, **kwargs: object) -> None:
        raise AssertionError("화면 테스트는 로컬 공정 표시명 DB를 조회하면 안 됩니다.")

    monkeypatch.setattr(
        process_labels_module, "load_global_process_rename", unexpected_profile_load
    )
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=90).run()

    assert not app.exception
    assert _page_errors(app) == []
    assert QUERY_START_WEEK in app.session_state["captured_week_columns"]
    assert BOUNDARY_WEEK in app.session_state["captured_week_columns"]
    assert app.session_state["captured_week_columns"] == QUERY_WEEKS
    # 열만 있고 값이 비면 사용자에게는 사라진 것과 같다. 첫 열이 곧 경계 주차다.
    assert app.session_state["captured_first_week_value"] == pytest.approx(DAILY_STANDARD)
    # 가용대수는 열 달 전부 채웠다. 경계 주차 누락이 가용대수 탓으로 오지목되지 않는지 본다.
    assert not any("가용대수가 없어" in warning.value for warning in app.warning)


def test_the_page_logic_analysis_runs_on_a_month_boundary_week() -> None:
    """화면이 스스로 제시한 선택지를 다 고르면 결과가 나와야 한다.

    로직 분석은 Weeknum 선택지를 소요대수 상세에 있는 달로 거른다. 화면이 26-W14 를
    제시한다는 것은 그 주의 귀속 달(202604)이 슬라이스에 들어왔다는 뜻이고, 서비스가
    같은 규칙으로 달을 정해야 "해당하는 데이터가 없습니다" 로 끝나지 않는다.
    """
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=90).run()
    app = app.segmented_control(key="standard_target_output_metric").set_value("로직 분석").run()

    assert _page_errors(app) == []
    weeknum_selector = app.selectbox(key="standard_target_logic_weeknum")
    assert BOUNDARY_WEEK in weeknum_selector.options

    app = weeknum_selector.set_value(BOUNDARY_WEEK).run()
    for key, value in (
        ("standard_target_logic_process", "Process-A"),
        ("standard_target_logic_basis", "WF"),
        ("standard_target_logic_production_type", "양산"),
        ("standard_target_logic_product", "Product-A"),
        ("standard_target_logic_stack", "8H"),
        ("standard_target_logic_wf_type", "Core"),
    ):
        app = app.selectbox(key=key).set_value(value).run()
        assert not app.exception
        assert _page_errors(app) == []

    metrics = {element.label: element.value for element in app.metric}
    assert "일 표준 가능량 (매)" in metrics
    assert metrics["일 표준 가능량 (매)"] == f"{DAILY_STANDARD:,.2f}"


# ------------------------------------------------------------------------------- 재공 현황 쪽


def test_the_wip_daily_standard_keeps_every_day_of_a_boundary_week() -> None:
    """26-W14 는 월요일이 3월, 나머지 5일이 4월이라 4월 귀속이다. 7일이 다 나와야 한다.

    표준 목표 Capa 가 만든 주차 표를 재공 화면이 그대로 일 단위로 편다. 여기서 달을 다시
    만들면 정본과 갈리고 INNER 조인이 그 주를 통째로 버린다 — 7일이 `표준 미설정` 이 되고
    화면은 원인을 가용대수로 오지목한다. 가용대수는 멀쩡하다.
    """
    weekly = build_weekly_standard_target_capacity(
        required_equipment=_required_equipment([BOUNDARY_WEEK_MONTH]),
        run_day=_run_day([BOUNDARY_WEEK_MONTH]),
        weekly_availability=_availability([BOUNDARY_WEEK]),
        start_date=BOUNDARY_WEEK_MONDAY,
        end_date=BOUNDARY_WEEK_SUNDAY,
        # 재공 화면이 쓰는 집계 수준. 제품까지 내려야 재공 경로와 붙는다.
        detail_level="제품정보",
    )

    assert weekly["Weeknum"].tolist() == [BOUNDARY_WEEK]
    assert weekly["생산계획년월"].tolist() == [BOUNDARY_WEEK_MONTH]

    daily = expand_weekly_product_standard_to_daily(
        weekly,
        BOUNDARY_WEEK_MONDAY,
        BOUNDARY_WEEK_SUNDAY,
    )

    assert len(daily) == 7
    assert daily["일자"].tolist()[0] == BOUNDARY_WEEK_MONDAY
    assert daily["일자"].tolist()[-1] == BOUNDARY_WEEK_SUNDAY
    # 3월 이틀과 4월 닷새가 같은 값을 받는다. 한쪽만 나오면 주차가 반으로 잘린 것이다.
    assert daily["일 표준 가능량"].tolist() == pytest.approx([DAILY_STANDARD] * 7)


def test_the_wip_screen_does_not_blame_availability_on_a_boundary_week() -> None:
    """사용자가 실제로 보는 것은 `상태` 칸이다. 경계 주차에 `표준 미설정` 이 남으면 안 된다."""
    weekly = build_weekly_standard_target_capacity(
        required_equipment=_required_equipment([BOUNDARY_WEEK_MONTH]),
        run_day=_run_day([BOUNDARY_WEEK_MONTH]),
        weekly_availability=_availability([BOUNDARY_WEEK]),
        start_date=BOUNDARY_WEEK_MONDAY,
        end_date=BOUNDARY_WEEK_SUNDAY,
        detail_level="제품정보",
    )
    daily = expand_weekly_product_standard_to_daily(
        weekly,
        BOUNDARY_WEEK_MONDAY,
        BOUNDARY_WEEK_SUNDAY,
    )
    routes = pd.DataFrame(
        {
            "공정": ["Process-A"],
            "STEP_SEQ": ["P010"],
            "제품정보": ["Product-A"],
            "소요기준": ["WF"],
        }
    )

    history = build_wip_history_demo(
        routes,
        daily,
        BOUNDARY_WEEK_MONDAY,
        BOUNDARY_WEEK_SUNDAY,
        # 합성 데모는 오늘을 기준으로 실적·전망을 가른다. 고정하지 않으면 날마다 달라진다.
        today=BOUNDARY_WEEK_SUNDAY,
    )

    assert len(history) == 7
    assert "표준 미설정" not in set(history["상태"])
    assert history["일 표준 가능량"].tolist() == pytest.approx([round(DAILY_STANDARD, 2)] * 7)


# ------------------------------------------------------------------------------------ 로직 분석


def test_logic_analysis_resolves_a_boundary_week_to_its_owning_month() -> None:
    """로직 분석은 주차 코드 하나로 달을 되찾는다. 그 달이 `owning_month` 여야 한다.

    소요대수 상세에는 네 달이 다 들어 있다. 월요일의 달(202603)을 보면 그 달 행으로 계산을
    시작하지만 주차 캘린더는 202604 라서 조인이 비고, 화면은 필터를 다 고른 사용자에게
    "데이터가 없습니다" 를 돌려준다. 데이터는 있고 딴 달을 본 것이다.
    """
    target, contributions = build_standard_target_logic_analysis(
        required_equipment=_required_equipment(SLICE_MONTHS),
        run_day=_run_day(SLICE_MONTHS),
        weekly_availability=_availability([BOUNDARY_WEEK]),
        weeknum=BOUNDARY_WEEK,
        process="Process-A",
        demand_basis="WF",
    )

    assert len(target) == 1
    assert target.at[0, "Weeknum"] == BOUNDARY_WEEK
    assert int(target.at[0, "생산계획년월"]) == BOUNDARY_WEEK_MONTH
    assert float(target.at[0, "일 표준 가능량"]) == pytest.approx(DAILY_STANDARD)
    # Mix 근거 표도 같은 달의 행으로만 채워져야 한다.
    assert contributions["생산계획년월"].astype("int64").tolist() == [BOUNDARY_WEEK_MONTH]
