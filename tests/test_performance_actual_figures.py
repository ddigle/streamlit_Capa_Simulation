# Purpose: 실적 Gap 화면의 우선순위 막대 라벨 자리와 추이 축 눈금 형식을 고정한다.

import pytest

from capa_simulation.components.performance_actual_screen import (
    _priority_figure,
    _trend_figure,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.performance_actuals import (
    UPEH_METRIC,
    YIELD_METRIC,
    build_monthly_actual_demo,
    build_monthly_trend,
    build_priority_table,
)


@pytest.mark.parametrize("metric", [UPEH_METRIC, YIELD_METRIC], ids=["upeh", "yield"])
def test_the_longest_bar_label_stays_inside_the_axis(metric) -> None:
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
def test_trend_ticks_use_the_kpi_format(metric, tick: str) -> None:
    """수율 축이 `0.9924·0.992` 처럼 자릿수를 섞은 비율로 적혀 99.21% 인 KPI 와 맞지 않았다."""
    trend = build_monthly_trend(build_monthly_actual_demo(), metric)

    figure = _trend_figure(trend, metric)

    assert figure.layout.yaxis.tickformat == tick
    assert all(f"%{{y:{tick}}}" in trace.hovertemplate for trace in figure.data[-2:])
