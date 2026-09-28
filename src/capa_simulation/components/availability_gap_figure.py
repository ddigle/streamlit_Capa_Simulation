# Purpose: Static 가용대수와 Dynamic 가용대수의 월별 비교 그림과 분해 표를 그린다.

"""Static 대 Dynamic 가용대수 비교.

**그림은 비교를, 표가 분해를 맡는다.** 분류가 열이라 열 가지 색을 쓰면 서로 구분되지
않는다 — 색으로 정체를 가르는 것은 여덟 계열이 한계이고, 그 위는 색이 아니라 자리로
갈라야 한다. 그래서 그림에는 가용 소계를 이루는 둘(`기존보유`·`가용`)만 쌓고 Static 을
옆에 세워 차이를 보이며, 열 가지 분해는 아래 표가 월을 열로 펼친다.

GAP 은 막대 위에 숫자로 적는다. 부호만 보고 색을 고른다 — 좋고 나쁨이 아니라 방향이다.

**화면 라벨은 「일할」이다.** 코드와 문서는 계속 「안분」이라 적지만 범례·설명은 사용자가
고른 말을 쓴다 — 같은 뜻이다(날짜 비율로 나눠 세는 것).

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


# 쌓인 두 조각 사이를 가르는 흰 테두리 굵기.
_STACK_OUTLINE_WIDTH_PX = 2.0
# 월 수와 막대 폭을 잇는 실측값. 넉 달일 때 막대 하나가 118px 이었다(1600px 창, 그림 폭
# 1265px). 폭은 월 수에 반비례하므로 막대 폭 ≈ 472 / 월 수 다 — 12개월이면 약 39px, 30개월이면
# 약 16px. 창이 좁으면 모두 같은 비율로 줄 뿐이라 등급의 경계만 조금 앞당겨진다.
_BAR_SPAN_PX = 472.0


def _corner_radius(month_count: int) -> int:
    """막대 굵기 등급을 월 수로 고른다. 등급 경계는 `tokens.bar_corner_radius` 한 곳이 정한다."""
    return tokens.bar_corner_radius(_BAR_SPAN_PX / max(month_count, 1))


def _stack_outline(values: list[float]) -> list[float]:
    """점마다 테두리 굵기. 높이 0 인 조각은 0 이다 — 둥근 머리 위에 납작한 뚜껑을 그리지 않게."""
    return [0.0 if value == 0 else _STACK_OUTLINE_WIDTH_PX for value in values]


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
    corner_radius = _corner_radius(len(months))
    baseline = _row(matrix, BASELINE_CATEGORY.name, months)
    available = _row(matrix, _AVAILABLE_CATEGORY, months)
    static = _row(matrix, STATIC_ROW, months)
    dynamic = _row(matrix, DYNAMIC_SUBTOTAL_ROW, months)
    gaps = _row(matrix, GAP_ROW, months)

    # Dynamic 은 두 조각을 쌓고, Static 은 그 옆에 따로 세운다. `offsetgroup` 이 달라야
    # 쌓기와 나란히 놓기가 한 그림에서 같이 산다.
    #
    # 머리는 둥글다. 막대 폭이 조회 월 수로 바뀌므로 반경 등급도 월 수로 고른다
    # (`_corner_radius`). 쌓인 막대는 Plotly 가 가장 바깥의 0 아닌 조각만 둥글린다 — 그래서
    # **높이 0 조각은 테두리를 긋지 않는다.** 그 조각은 둥근 머리 바로 위에 앉아 흰 테두리만
    # 납작한 뚜껑처럼 남는다. 범례 아이콘이 서로 맞도록 반경은 세 계열에 모두 준다.
    figure.add_bar(
        x=labels,
        y=baseline,
        name="기존보유",
        marker={
            "color": tokens.BORDER_STRONG,
            "line": {"color": tokens.SURFACE, "width": _stack_outline(baseline)},
            "cornerradius": corner_radius,
        },
        offsetgroup="dynamic",
        legendgroup="dynamic",
        hovertemplate="기존보유 %{y:.2f}대<extra></extra>",
    )
    figure.add_bar(
        x=labels,
        y=available,
        name="가용(일할)",
        marker={
            "color": tokens.ACCENT,
            "line": {"color": tokens.SURFACE, "width": _stack_outline(available)},
            "cornerradius": corner_radius,
        },
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
            "cornerradius": corner_radius,
        },
        offsetgroup="static",
        legendgroup="static",
        hovertemplate="Static %{y:.2f}대<extra></extra>",
    )

    top = max([*dynamic, *static, 0.0]) or 1.0
    annotations = [
        {
            "x": index,
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
        for index, (gap, dynamic_value, static_value) in enumerate(
            zip(gaps, dynamic, static, strict=True)
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
    # 월 라벨을 수로 추론하면 26.10이 26.1로 줄고 연도 경계의 간격도 달라진다.
    figure.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=labels,
        fixedrange=True,
        showgrid=False,
        linecolor=tokens.BORDER,
    )
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
