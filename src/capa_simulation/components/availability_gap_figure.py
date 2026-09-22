# Purpose: Static 가용대수와 Dynamic 가용대수의 월별 비교 그림과 분해 표를 그린다.

"""Static 대 Dynamic 가용대수 비교.

**그림은 비교를, 표가 분해를 맡는다.** 분류가 열이라 열 가지 색을 쓰면 서로 구분되지
않는다 — 색으로 정체를 가르는 것은 여덟 계열이 한계이고, 그 위는 색이 아니라 자리로
갈라야 한다. 그래서 그림에는 가용 소계를 이루는 둘(`기존보유`·`가용`)만 쌓고 Static 을
옆에 세워 차이를 보이며, 열 가지 분해는 아래 표가 월을 열로 펼친다.

GAP 은 막대 위에 숫자로 적는다. 부호만 보고 색을 고른다 — 좋고 나쁨이 아니라 방향이다.

## 색은 재서 골랐다

쌓이는 두 조각(`기존보유` 회색 · `가용` 강조색)이 **서로 붙어 있는 유일한 쌍**이라
그 둘만 분리가 필요하다. OKLab 으로 재면 색각 이상에서 ΔE 19.5, 일반 시야에서 23.7 로
기준(8 / 15)을 크게 넘는다.

Static 막대는 자리가 달라 색으로 가를 필요가 없고, 바탕과의 대비는 1.4:1 로 낮다.
그래서 **어두운 테두리와 아래 숫자 표**가 그 몫을 대신한다 — 낮은 대비는 라벨이나 표로
받쳐야 넘어갈 수 있는 종류다. 면색만 보고 읽게 두지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    chart_canvas_layout,
    delta_color,
    flush_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    GAP_ROW,
    STATIC_ROW,
)
from capa_simulation.services.monthly_equipment_availability import BASELINE_CATEGORY

__all__ = ["build_availability_gap_figure", "month_label"]

_AVAILABLE_CATEGORY = "가용"
_BAR_FONT_SIZE = 12
_CHART_HEIGHT_PX = 360


def month_label(year_month: int) -> str:
    """`202610` → `26.10`. 다른 화면의 월 라벨과 같은 표기다."""
    text = str(int(year_month))
    return f"{text[2:4]}.{text[4:6]}"


def build_availability_gap_figure(matrix: pd.DataFrame) -> go.Figure:
    """월을 가로축에 둔 비교 그림.

    `matrix` 는 `services/availability_gap.gap_matrix` 의 결과(행이 분류, 열이 월)다.
    없는 행은 0 으로 본다 — 어느 달에 그 분류가 아예 없을 수 있다.
    """
    figure = go.Figure()
    months = list(matrix.columns) if not matrix.empty else []
    if not months:
        figure.update_layout(**chart_canvas_layout(font_size=_BAR_FONT_SIZE))
        flush_layout_items(figure)
        return figure

    labels = [month_label(int(month)) for month in months]
    baseline = _row(matrix, BASELINE_CATEGORY.name, months)
    available = _row(matrix, _AVAILABLE_CATEGORY, months)
    static = _row(matrix, STATIC_ROW, months)
    dynamic = _row(matrix, DYNAMIC_SUBTOTAL_ROW, months)
    gaps = _row(matrix, GAP_ROW, months)

    # Dynamic 은 두 조각을 쌓고, Static 은 그 옆에 따로 세운다. `offsetgroup` 이 달라야
    # 쌓기와 나란히 놓기가 한 그림에서 같이 산다.
    figure.add_bar(
        x=labels,
        y=baseline,
        name="기존보유",
        marker={"color": tokens.BORDER_STRONG, "line": {"color": tokens.SURFACE, "width": 2}},
        offsetgroup="dynamic",
        legendgroup="dynamic",
        hovertemplate="기존보유 %{y:.2f}대<extra></extra>",
    )
    figure.add_bar(
        x=labels,
        y=available,
        name="가용(안분)",
        marker={"color": tokens.ACCENT, "line": {"color": tokens.SURFACE, "width": 2}},
        offsetgroup="dynamic",
        legendgroup="dynamic",
        hovertemplate="가용 %{y:.2f}대<extra></extra>",
    )
    figure.add_bar(
        x=labels,
        y=static,
        name="Static(기준정보)",
        marker={
            "color": tokens.SURFACE_GRAND_TOTAL,
            "line": {"color": tokens.TEXT, "width": 1.5},
        },
        offsetgroup="static",
        legendgroup="static",
        hovertemplate="Static %{y:.2f}대<extra></extra>",
    )

    top = max([*dynamic, *static, 0.0]) or 1.0
    annotations = [
        {
            "x": label,
            "y": max(dynamic_value, static_value),
            "text": f"{gap:+.2f}",
            "showarrow": False,
            "xanchor": "center",
            "yanchor": "bottom",
            "yshift": 6,
            "font": {
                "color": delta_color(f"{gap:+.2f}"),
                "size": _BAR_FONT_SIZE,
                "family": tokens.FONT_FAMILY_NUMERIC,
            },
        }
        for label, gap, dynamic_value, static_value in zip(
            labels, gaps, dynamic, static, strict=True
        )
    ]

    figure.update_layout(
        **chart_canvas_layout(font_size=_BAR_FONT_SIZE),
        barmode="stack",
        height=_CHART_HEIGHT_PX,
        margin={"l": 48, "r": 16, "t": 48, "b": 36},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        annotations=annotations,
    )
    figure.update_xaxes(fixedrange=True, showgrid=False, linecolor=tokens.BORDER)
    figure.update_yaxes(
        fixedrange=True,
        title_text="대수",
        gridcolor=tokens.BORDER,
        zerolinecolor=tokens.BORDER_STRONG,
        rangemode="tozero",
        range=[0, top * 1.22],
    )
    add_figure_outer_border(figure, emphasize_bottom=True)
    flush_layout_items(figure)
    return figure


def _row(matrix: pd.DataFrame, name: str, months: Sequence[object]) -> list[float]:
    """행 하나를 월 차례대로. 그 행이 없으면 전부 0 이다."""
    if name not in list(matrix.index):
        return [0.0] * len(months)
    series = matrix.loc[name]
    return [float(series.get(month, 0.0)) for month in months]
