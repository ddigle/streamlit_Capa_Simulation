# Purpose: 실적 Gap 화면의 우선순위 막대 라벨 자리·공정 줄과 추이 축 눈금 형식을 고정한다.

from typing import Any

import pytest

from capa_simulation.components.performance_actual_screen import (
    _gap_matrix_figure,
    _priority_figure,
    _trend_figure,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.performance_actuals import (
    EFFICIENCY_METRIC,
    UPEH_METRIC,
    YIELD_METRIC,
    MetricSpec,
    build_monthly_actual_demo,
    build_monthly_trend,
    build_priority_table,
)


@pytest.mark.parametrize("metric", [UPEH_METRIC, YIELD_METRIC], ids=["upeh", "yield"])
def test_the_longest_bar_label_stays_inside_the_axis(metric: MetricSpec) -> None:
    """가장 긴 음수 막대의 바깥 라벨이 왼쪽 공정 이름 위에 겹쳤다(`TC Bonding.4%`, 2026-10-05
    E2E). 라벨이 나가는 쪽에 자리를 남긴 범위를 준다."""
    priority = build_priority_table(build_monthly_actual_demo(), metric, ["공정"])

    figure = _priority_figure(priority, metric, ProcessLabels())

    low, high = figure.layout.xaxis.range
    gaps = priority["Gap"].astype(float)
    assert low < gaps.min() - 0.3 * (max(0.0, gaps.max()) - min(0.0, gaps.min()))
    assert high >= max(0.0, gaps.max())


@pytest.mark.parametrize(
    ("metric", "tick"), [(UPEH_METRIC, ",.0f"), (YIELD_METRIC, ".2%")], ids=["upeh", "yield"]
)
def test_trend_ticks_use_the_kpi_format(metric: MetricSpec, tick: str) -> None:
    """수율 축이 `0.9924·0.992` 처럼 자릿수를 섞은 비율로 적혀 99.21% 인 KPI 와 맞지 않았다."""
    trend = build_monthly_trend(build_monthly_actual_demo(), metric)

    figure = _trend_figure(trend, metric)

    assert figure.layout.yaxis.tickformat == tick
    assert all(f"%{{y:{tick}}}" in trace.hovertemplate for trace in figure.data[-2:])


def _colliding_labels() -> tuple[ProcessLabels, list[str]]:
    """둘째 공정의 표시명이 첫째 공정의 원본과 같은 표시명 묶음과 데모 공정 목록."""
    processes = sorted(build_monthly_actual_demo()["공정"].astype(str).unique().tolist())
    return ProcessLabels(version=1, labels={processes[1]: processes[0]}), processes


def _shown_rows(figure: Any) -> list[str]:
    """범주 축 눈금에 보이는 글자(trace 의 범주 값 차례)."""
    axis = figure.layout.yaxis
    shown = dict(zip(axis.tickvals, axis.ticktext, strict=True))
    return [shown[str(value)] for value in figure.data[0].y]


@pytest.mark.parametrize(
    "metric", [EFFICIENCY_METRIC, UPEH_METRIC, YIELD_METRIC], ids=["efficiency", "upeh", "yield"]
)
def test_a_colliding_display_name_keeps_its_own_priority_bar(metric: MetricSpec) -> None:
    """표시명이 다른 공정의 원본과 같아도 막대가 공정마다 한 줄이다(2026-10-25 E2E).

    표시명을 범주 값으로 쓰면 Plotly 가 같은 글자를 한 줄로 합쳐 두 막대가 겹치고 한쪽 값
    글자가 사라졌다. 범주 값은 원본이고 눈금·hover 글자만 표시명이다.
    """
    labels, processes = _colliding_labels()
    priority = build_priority_table(build_monthly_actual_demo(), metric, ["공정"])

    figure = _priority_figure(priority, metric, labels)

    rows = [str(value) for value in figure.data[0].y]
    assert len(set(rows)) == len(priority)
    assert _shown_rows(figure).count(processes[0]) == 2
    assert [row[0] for row in figure.data[0].customdata] == _shown_rows(figure)


def test_a_colliding_display_name_keeps_its_own_gap_matrix_row() -> None:
    labels, processes = _colliding_labels()

    figure = _gap_matrix_figure(build_monthly_actual_demo(), UPEH_METRIC, labels)

    rows = [str(value) for value in figure.data[0].y]
    assert len(set(rows)) == len(processes)
    assert _shown_rows(figure).count(processes[0]) == 2
    assert [row[0] for row in figure.data[0].customdata] == _shown_rows(figure)
