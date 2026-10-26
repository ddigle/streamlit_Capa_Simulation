# Purpose: 실적·Dynamic Capa 그림의 축 눈금 글자색이 두 테마 캔버스 위 4.5:1 이상인지 고정한다.

"""축 눈금 글자색은 그림이 **직접** 준다.

`chart_canvas_layout` 은 `layout.font.color` 만 준다. `st.plotly_chart` 의 기본
`theme="streamlit"` 은 축 `tickfont`·`title.font` 색을 테마 회색(밝은 테마 `#808495`)으로 따로
채우므로, 그림이 축 글자색을 비워 두면 캔버스(`#F7F8FA`) 위 대비가 3.50:1 이 된다(2026-10-26 E2E —
효율·UPEH·수율 실적 요약 그림과 Dynamic Capa 공정별 Capa 실현 수준 그림). 비워 둔 색은 Python
Figure 에서 `None` 으로 남으므로 그것을 잡는다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import plotly.graph_objects as go
import pytest

from capa_simulation.components.dynamic_capacity_dashboard import (
    build_capacity_trend_figure,
    build_capacity_waterfall_figure,
    build_process_comparison_figure,
)
from capa_simulation.components.performance_actual_screen import (
    _gap_matrix_figure,
    _priority_figure,
    _trend_figure,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import theme, tokens
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
)
from capa_simulation.services.performance_actuals import (
    ALL_METRICS,
    build_monthly_actual_demo,
    build_monthly_trend,
    build_priority_table,
)

# 본문 글자 대비(WCAG AA). `docs/design_system.md` 의 면·글자 짝 기준이다.
TEXT_CONTRAST_MINIMUM = 4.5


def _linear(color: str) -> list[float]:
    channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]


def _contrast(one: str, other: str) -> float:
    def luminance(color: str) -> float:
        red, green, blue = _linear(color)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _performance_figures() -> Iterator[tuple[str, go.Figure]]:
    monthly = build_monthly_actual_demo()
    for metric in ALL_METRICS:
        priority = build_priority_table(monthly, metric, ["공정"])
        yield f"{metric.name} 추이", _trend_figure(build_monthly_trend(monthly, metric), metric)
        yield f"{metric.name} 우선순위", _priority_figure(priority, metric, ProcessLabels())
        yield f"{metric.name} Gap 격자", _gap_matrix_figure(monthly, metric, ProcessLabels())


def _dynamic_figures() -> Iterator[tuple[str, go.Figure]]:
    demo = build_dynamic_capacity_demo()
    summary = aggregate_dynamic_capacity(demo, ["공정"])
    process = str(summary["공정"].iloc[0])
    detail = demo.loc[demo["공정"].astype(str).eq(process)]
    yield "공정별 Capa 실현 수준", build_process_comparison_figure(summary)
    yield (
        "Capa 손실 구조",
        build_capacity_waterfall_figure(aggregate_dynamic_capacity(detail, ["공정"]).iloc[0]),
    )
    yield "일별 Capa 추이", build_capacity_trend_figure(detail)


def _axes(figure: go.Figure) -> Iterator[tuple[str, go.layout.XAxis | go.layout.YAxis]]:
    for name in ("xaxis", "yaxis"):
        for key in figure.layout:
            if key == name or (key.startswith(name) and key[len(name) :].isdigit()):
                yield key, figure.layout[key]


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize(
    "figures", [_performance_figures, _dynamic_figures], ids=["performance", "dynamic"]
)
def test_axis_tick_text_is_readable_on_the_chart_canvas(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    figures: Callable[[], Iterator[tuple[str, go.Figure]]],
) -> None:
    """모든 축의 눈금 글자색을 그림이 주고, 그 색이 그 테마의 캔버스 위에서 4.5:1 이상이다."""
    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    canvas = tokens.CHART_CANVAS
    problems = []
    for title, figure in figures():
        for key, axis in _axes(figure):
            color = axis.tickfont.color
            if color is None:
                problems.append(f"{title} {key}: 눈금 글자색 없음(테마 회색이 채운다)")
            elif _contrast(str(color), canvas) < TEXT_CONTRAST_MINIMUM:
                problems.append(
                    f"{title} {key}: {color} / {canvas} = {_contrast(color, canvas):.2f}"
                )
    assert not problems, problems
