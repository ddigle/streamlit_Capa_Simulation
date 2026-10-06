# Purpose: 막대의 둥근 머리가 값 막대에만 스칼라 반경으로 걸리고 실행 조정 달은 네모인지 고정한다.

"""막대의 값 쪽 끝을 둥글린다(2026-09-28 차트 안 1). 지킬 것이 셋이다.

1. 반경은 **스칼라**다. plotly.py 는 점마다 다른 배열도 받아 주지만 plotly.js 3.7 은 그
   배열을 조용히 버리고 직각으로 그린다(제안서 실측). 검사로만 잡힌다.
2. `layout.barcornerradius` 를 쓰지 않는다. 그림 전체의 기본값이 되어 hover 표적·증감
   조각·표 칸 막대까지 둥글어진다.
3. 실행 조정 달의 값 막대는 **네모**다. overlay 에서 값 막대 윗끝이 결과 윤곽보다 반경만큼
   낮지 않으면 모서리가 파인다(통합 실측 LOB |증감| < 8px, Top5 < 3px). 반경은 막대마다
   줄 수 없어 조정이 있을 때만 값 trace 를 둘로 나눈다. 조정이 없으면 trace 하나다.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.availability_gap_figure import build_availability_gap_figure
from capa_simulation.components.dynamic_capacity_dashboard import build_process_comparison_figure
from capa_simulation.components.home_dimensions import LOB_BAR_WIDTH
from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.design import tokens
from capa_simulation.services.availability_gap import DYNAMIC_SUBTOTAL_ROW, GAP_ROW, STATIC_ROW
from capa_simulation.services.monthly_equipment_availability import BASELINE_CATEGORY
from capa_simulation.services.securement_threshold import SecurementThresholds

MONTHS = [202601, 202602, 202603]
LABELS = ["26.01", "26.02", "26.03"]
LOB_VALUE_TRACE = "B/N 공정"
TOP5_VALUE_TRACE = "B/N Capa Top 5"
# 둘째 달은 줄고(1.2 배였던 것이 결과), 셋째 달은 늘었다(0.8 배였던 것이 결과).
ADJUSTED = {MONTHS[1]: 1.2, MONTHS[2]: 0.8}


def _frames(*, adjusted: dict[int, float], with_execution_columns: bool) -> dict[str, Any]:
    """세 달짜리 LOB 요약 입력. `adjusted` 는 달마다 **조정 전 값 / 조정 후 값** 비율이다.

    1 보다 크면 실행 반영으로 줄어든 달, 작으면 늘어난 달이다. 늘어난 달에는 결과 윤곽 trace 가
    하나 더 선다.
    """
    rates = [1.20, 1.05, 0.90]
    capa = [1.2, 1.3, 1.1]
    bottleneck = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "공정": ["SAW"] * 3,
            "확보율": rates,
            "B/N Capa": capa,
        }
    )
    top5 = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "순위": [1, 1, 1],
            "공정": ["SAW"] * 3,
            "확보율": rates,
            "Wafer Capa": [9_500.0, 11_000.0, 12_000.0],
            "B/N Capa": capa,
        }
    )
    if with_execution_columns:
        base_capa = list(capa)
        base_rates = list(rates)
        deltas = [0.0, 0.0, 0.0]
        for month, ratio in adjusted.items():
            index = MONTHS.index(month)
            base_capa[index] = capa[index] * ratio
            base_rates[index] = rates[index] * ratio
            deltas[index] = round((1 / ratio - 1) * 100, 1)
        # 숫자 열과 글자 열이 섞여 값 타입을 하나로 좁힐 수 없다.
        execution: dict[str, list[Any]] = {"확보율 증감": deltas, "실행 비고": [""] * 3}
        bottleneck = bottleneck.assign(**{"기준 B/N Capa": base_capa}, **execution)
        top5 = top5.assign(**{"기준 확보율": base_rates}, **execution)
    return {
        "monthly_density": pd.DataFrame(
            {"생산계획년월": MONTHS, "년월": LABELS, "부하량": [1.0, 1.1, 1.2]}
        ),
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": MONTHS,
                "년월": LABELS,
                "부하량": [1.0, 1.1, 1.2],
                "Wafer 부하량": [9_000.0, 10_000.0, 11_000.0],
                "Wafer Capa": [9_500.0, 11_000.0, 12_000.0],
            }
        ),
        "bottleneck_capacity": bottleneck,
        "monthly_top5": top5,
    }


def _month_figure(*, adjusted: dict[int, float], with_execution_columns: bool) -> go.Figure:
    _, month_figure = build_lob_summary_figures(
        **_frames(adjusted=adjusted, with_execution_columns=with_execution_columns),
        month_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
    )
    return month_figure


def _bars(figure: go.Figure) -> list[go.Bar]:
    return [trace for trace in figure.data if isinstance(trace, go.Bar)]


def _is_scalar_radius(value: object) -> bool:
    """숫자 하나이거나 `"15%"` 같은 문자열 하나. 배열은 plotly.js 가 버린다."""
    return isinstance(value, Real) or (isinstance(value, str) and value.endswith("%"))


def test_only_the_value_bars_round_and_the_radius_is_a_scalar() -> None:
    figure = _month_figure(adjusted=ADJUSTED, with_execution_columns=True)

    assert figure.layout.barcornerradius is None
    for trace in _bars(figure):
        radius = trace.marker.cornerradius
        if trace.name in (LOB_VALUE_TRACE, TOP5_VALUE_TRACE):
            assert _is_scalar_radius(radius), (trace.name, radius)
        else:
            # 증감 조각과 늘어난 결과 윤곽은 반경을 받지 않는다. 머리는 값 막대의 것이다.
            assert radius in (None, 0), (trace.name, radius)


def test_value_bars_use_the_width_grades() -> None:
    """굵은 LOB 막대는 8px, 가는 Top5 막대는 3px. 굵기에 맞춰 등급을 고른다."""
    figure = _month_figure(adjusted={}, with_execution_columns=False)
    radii = {trace.name: trace.marker.cornerradius for trace in _bars(figure)}

    assert radii[LOB_VALUE_TRACE] == tokens.BAR_CORNER_RADIUS_WIDE_PX
    assert radii[TOP5_VALUE_TRACE] == tokens.BAR_CORNER_RADIUS_NARROW_PX


def test_no_adjustment_leaves_the_figure_as_it_was() -> None:
    """조정 컬럼이 있어도 조정이 0건이면 Figure 가 조정 컬럼 없을 때와 **같다**."""
    plain = _month_figure(adjusted={}, with_execution_columns=False)
    zero = _month_figure(adjusted={}, with_execution_columns=True)

    assert zero.to_json() == plain.to_json()


def test_adjusted_months_keep_a_square_head() -> None:
    """조정한 달만 반경 0 인 둘째 값 trace 로 간다. 점마다 딸린 배열도 같이 갈라진다."""
    figure = _month_figure(adjusted=ADJUSTED, with_execution_columns=True)

    for name, radius in (
        (LOB_VALUE_TRACE, tokens.BAR_CORNER_RADIUS_WIDE_PX),
        (TOP5_VALUE_TRACE, tokens.BAR_CORNER_RADIUS_NARROW_PX),
    ):
        rounded, square = [trace for trace in _bars(figure) if trace.name == name]
        assert rounded.marker.cornerradius == radius
        assert square.marker.cornerradius == 0
        assert square.showlegend is False
        assert rounded.legendgroup == square.legendgroup == name
        # 첫 달만 조정이 없다. 자리(x)는 Top5 가 순위 칸만큼 비켜 서므로 차례로 본다.
        assert len(rounded.x) == 1 and len(square.x) == 2
        assert max(rounded.x) < min(square.x)
        for trace in (rounded, square):
            points = len(trace.x)
            assert len(trace.y) == points
            assert len(trace.customdata) == points
            assert len(trace.marker.color) == points


def test_the_lob_bar_is_wide_enough_for_a_level_rate_label() -> None:
    """LOB 막대 안의 확보율 글자는 폭 56px 아래에서 눕는다(제안서 실측 — `202%` 잉크 49.5px).

    누우면 Density 값과 겹친다. 폭을 줄이려면 글자 크기를 먼저 정한다.
    """
    assert LOB_BAR_WIDTH * tokens.MONTH_COLUMN_WIDTH_PX >= 56


def test_dynamic_capacity_bars_round_their_ends() -> None:
    """Dynamic Capa 공정별 비교는 가로 group 막대(25px)라 중간 등급이다."""
    summary = pd.DataFrame(
        {
            "공정": ["A", "B"],
            "설비 성능 실현률": [0.9, 0.8],
            "Capa 실현률": [0.85, 1.1],
            "상태": ["정상", "관찰"],
        }
    )
    figure = build_process_comparison_figure(summary)

    assert figure.layout.barcornerradius is None
    assert [trace.marker.cornerradius for trace in figure.data] == [
        tokens.BAR_CORNER_RADIUS_MEDIUM_PX
    ] * 2


def _gap_figure(month_count: int, *, empty_available_month: int | None = None) -> go.Figure:
    months = [str(202601 + index) for index in range(month_count)]
    available = [0.0 if index == empty_available_month else 1.0 for index in range(month_count)]
    matrix = pd.DataFrame(
        [
            [3.0] * month_count,
            available,
            [3.0 + value for value in available],
            [4.0] * month_count,
            [value - 1.0 for value in available],
        ],
        index=[BASELINE_CATEGORY.name, "가용", DYNAMIC_SUBTOTAL_ROW, STATIC_ROW, GAP_ROW],
        columns=months,
    )
    return build_availability_gap_figure(matrix)


def test_the_availability_gap_bars_grade_their_heads_by_month_count() -> None:
    """가용설비 Static/Dynamic 비교는 막대 폭이 조회 월 수로 바뀐다(실측 넉 달 118px).

    반경 등급을 월 수로 고른다 — 넉 달이면 넓음, 열두 달이면 중간, 서른 달이면 좁음. 범례
    아이콘이 맞도록 세 계열 모두 같은 반경이다. 폭의 비율 반경은 넓은 막대에서 18px 까지
    커져 쓰지 않는다.
    """
    for month_count, radius in (
        (4, tokens.BAR_CORNER_RADIUS_WIDE_PX),
        (12, tokens.BAR_CORNER_RADIUS_MEDIUM_PX),
        (30, tokens.BAR_CORNER_RADIUS_NARROW_PX),
    ):
        figure = _gap_figure(month_count)
        assert figure.layout.barcornerradius is None
        assert [trace.marker.cornerradius for trace in figure.data] == [radius] * 3, month_count


def test_an_empty_stack_segment_draws_no_flat_cap() -> None:
    """쌓인 막대에서 높이 0 조각은 테두리를 긋지 않는다.

    Plotly 는 가장 바깥의 0 아닌 조각을 둥글린다. 높이 0 조각은 그 둥근 머리 바로 위에 앉아
    흰 테두리만 납작한 뚜껑처럼 남는다.
    """
    baseline, available, _static = _gap_figure(2, empty_available_month=1).data

    assert list(available.marker.line.width) == [2.0, 0.0]
    assert list(baseline.marker.line.width) == [2.0, 2.0]


def test_width_grades_have_one_home() -> None:
    """폭이 기간으로 바뀌는 막대(가용설비 두 차트)는 한 함수로 등급을 고른다."""
    assert tokens.bar_corner_radius(118) == tokens.BAR_CORNER_RADIUS_WIDE_PX
    assert tokens.bar_corner_radius(40) == tokens.BAR_CORNER_RADIUS_WIDE_PX
    assert tokens.bar_corner_radius(39) == tokens.BAR_CORNER_RADIUS_MEDIUM_PX
    assert tokens.bar_corner_radius(20) == tokens.BAR_CORNER_RADIUS_MEDIUM_PX
    assert tokens.bar_corner_radius(17) == tokens.BAR_CORNER_RADIUS_NARROW_PX
