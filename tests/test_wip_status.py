# Purpose: wip status 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.wip_status import (
    aggregate_weekly_product_standard,
    build_wip_history_demo,
    build_wip_route_scope,
    expand_weekly_product_standard_to_daily,
    processes_in_step_order,
    step_sort_key,
)


def _routes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["T-Process", "P-Process", "P-Process", "P-Process"],
            "STEP_SEQ": ["T010", "P010-002", "P002", "P010"],
            "제품정보": ["Product-A", "Product-A", "Product-A", "Product-B"],
            "소요기준": ["WF", "CHIP", "CHIP", "CHIP"],
        }
    )


def test_step_sort_orders_prefix_and_numeric_segments() -> None:
    values = ["T002", "P010-010", "P010", "P002", "T001-020", "T001", "X100"]

    assert sorted(values, key=step_sort_key) == [
        "P002",
        "P010",
        "P010-010",
        "T001",
        "T001-020",
        "T002",
        "X100",
    ]
    assert step_sort_key("DEMO-P100") < step_sort_key("DEMO-T001")


def test_wip_route_scope_and_process_options_follow_step_order() -> None:
    routes = build_wip_route_scope(_routes())

    assert routes["STEP_SEQ"].tolist() == ["P002", "P010", "P010-002", "T010"]
    assert processes_in_step_order(routes) == ["P-Process", "T-Process"]


def test_product_standard_recomputes_effective_capacity_across_production_types() -> None:
    weekly = pd.DataFrame(
        {
            "Weeknum": ["26-W36", "26-W36"],
            "주차시작일": [date(2026, 8, 31)] * 2,
            "주차종료일": [date(2026, 9, 6)] * 2,
            "생산계획년월": [202608, 202608],
            "공정": ["Process-A", "Process-A"],
            "소요기준": ["WF", "WF"],
            "양산구분": ["양산", "개발"],
            "제품정보": ["Product-A", "Product-A"],
            "원수요_부하량": [100.0, 200.0],
            "STEP_소요대수": [2.0, 2.0],
            "공정 유효 Capa": [50.0, 100.0],
            "RUN_DAY": [30.0, 30.0],
            "대당 일 Capa": [50.0 / 30.0, 100.0 / 30.0],
            "가용대수": [3.0, 3.0],
            "일 표준 가능량": [5.0, 10.0],
        }
    )

    product_weekly = aggregate_weekly_product_standard(weekly)
    daily = expand_weekly_product_standard_to_daily(
        weekly,
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    assert len(product_weekly) == 1
    assert product_weekly.loc[0, "공정 유효 Capa"] == pytest.approx(75.0)
    assert product_weekly.loc[0, "일 표준 가능량"] == pytest.approx(7.5)
    assert daily["일자"].tolist() == [date(2026, 9, 1), date(2026, 9, 2)]
    assert daily["일 표준 가능량"].tolist() == pytest.approx([7.5, 7.5])


def test_wip_demo_is_deterministic_and_marks_flow_against_standard() -> None:
    routes = pd.DataFrame(
        {
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "제품정보": ["Product-A"],
            "소요기준": ["WF"],
        }
    )
    dates = pd.date_range("2026-09-01", "2026-09-04", freq="D")
    daily_standard = pd.DataFrame(
        {
            "일자": dates,
            "공정": ["Process-A"] * len(dates),
            "소요기준": ["WF"] * len(dates),
            "제품정보": ["Product-A"] * len(dates),
            "일 표준 가능량": [100.0] * len(dates),
        }
    )

    first = build_wip_history_demo(
        routes,
        daily_standard,
        date(2026, 9, 1),
        date(2026, 9, 4),
        today=date(2026, 9, 2),
    )
    second = build_wip_history_demo(
        routes,
        daily_standard,
        date(2026, 9, 1),
        date(2026, 9, 4),
        today=date(2026, 9, 2),
    )

    pd.testing.assert_frame_equal(first, second)
    expected_status = first["Flow량"].ge(first["일 표준 가능량"]).map({True: "충족", False: "부족"})
    assert first["상태"].tolist() == expected_status.tolist()
    assert first["시점"].tolist() == ["실적 샘플", "실적 샘플", "전망 샘플", "전망 샘플"]


def test_wip_demo_marks_missing_standard_without_inventing_a_target() -> None:
    routes = pd.DataFrame(
        {
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "제품정보": ["Product-A"],
            "소요기준": ["WF"],
        }
    )
    empty_standard = pd.DataFrame(
        columns=["일자", "공정", "소요기준", "제품정보", "일 표준 가능량"]
    )

    result = build_wip_history_demo(
        routes,
        empty_standard,
        date(2026, 9, 1),
        date(2026, 9, 1),
    )

    assert pd.isna(result.loc[0, "일 표준 가능량"])
    assert result.loc[0, "상태"] == "표준 미설정"
