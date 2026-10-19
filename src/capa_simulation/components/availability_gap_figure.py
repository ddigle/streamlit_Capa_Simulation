# Purpose: Static 가용대수와 설비 일정 기준 가용대수(환산)의 월별 비교 그림을 그린다.

"""Static 대 설비 일정 기준 가용대수 비교.

**그림은 비교를, 시트가 분해를 맡는다.** 그림에는 설비 일정 기준 가용을 이루는 둘
(`기존보유`·`가용`)만 쌓고 Static 가용을 옆에 세워 차이를 보이며, 보유·대여(비가동)·가용 분해는
`분류별 내역` 의 9행 시트가 월을 열로 펼친다.

**축은 환산이다**(2026-10-17 사용자 결정). 설비 일정 기준 가용 = 기존보유 + 「가용」 호기의
환산대수(`SheetView` 의 `sched:available`)이고, Static 가용과 GAP 가용은 시트의 그 칸과 같은
값이다 — 확보율 교차검증·필요 단축 일정·공정 Capa 상세 ② 와도 같다. 대수(몇 대) 축은 「호기 목록」의
`대수` 칸이다.

GAP 은 막대 위에 숫자로 적는다. 글자와 색은 시트의 GAP 가용 칸과 같은 함수로 만든다
(`sheet_value_text`·`gap_text_color` — 마이너스 U+2212, 2자리로 0 이 되는 0 아닌 값은 3자리, 0 으로
적히면 흐린 글자). 부호만 보고 색을 고른다 — 좋고 나쁨이 아니라 방향이다. 맞댈 수 없는
달(「—」)은 GAP 글자를 적지 않는다.

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

import plotly.graph_objects as go

from capa_simulation.components.availability_sheet_canvas import (
    gap_text_color,
    sheet_value_text,
)
from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    chart_canvas_layout,
    flush_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.availability_sheet import (
    ROW_GAP_AVAILABLE,
    ROW_SCHEDULE_AVAILABLE,
    ROW_STATIC_AVAILABLE,
    SheetView,
)
from capa_simulation.services.month_columns import month_label

__all__ = ["build_availability_gap_figure"]

_BAR_FONT_SIZE = 12
_CHART_HEIGHT_PX = 360


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


def build_availability_gap_figure(view: SheetView) -> go.Figure:
    """월을 가로축에 둔 비교 그림.

    `view` 는 비교 시트의 9행(`services/availability_sheet.sheet_view`)이다 — 반사실 없이 만든
    시트여도 된다(가용만 읽는다). 「—」 칸(NaN)은 막대 높이 0 이고 GAP 글자를 적지 않는다.
    """
    figure = go.Figure()
    months = list(view.months)
    if not months:
        figure.update_layout(**chart_canvas_layout(font_size=_BAR_FONT_SIZE))
        flush_layout_items(figure)
        return figure

    labels = [month_label(int(month)) for month in months]
    corner_radius = _corner_radius(len(months))
    dynamic = [view.value(ROW_SCHEDULE_AVAILABLE, month) or 0.0 for month in months]
    baseline = [_number(view.baseline.get(month)) for month in months]
    available = [total - base for total, base in zip(dynamic, baseline, strict=True)]
    static = [view.value(ROW_STATIC_AVAILABLE, month) or 0.0 for month in months]
    gaps = [view.value(ROW_GAP_AVAILABLE, month) for month in months]

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
        hovertemplate="기존보유 %{y:.2f}<extra></extra>",
    )
    figure.add_bar(
        x=labels,
        y=available,
        name="가용(일할·환산)",
        marker={
            "color": tokens.ACCENT,
            "line": {"color": tokens.SURFACE, "width": _stack_outline(available)},
            "cornerradius": corner_radius,
        },
        offsetgroup="dynamic",
        legendgroup="dynamic",
        hovertemplate="가용 %{y:.2f} (환산대수)<extra></extra>",
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
            "text": sheet_value_text(ROW_GAP_AVAILABLE, gap),
            "showarrow": False,
            "xanchor": "center",
            "yanchor": "bottom",
            "yshift": 6,
            "font": {
                "color": gap_text_color(gap),
                "size": _BAR_FONT_SIZE,
                "family": tokens.FONT_FAMILY_NUMERIC,
            },
        }
        for index, (gap, dynamic_value, static_value) in enumerate(
            zip(gaps, dynamic, static, strict=True)
        )
        if gap is not None
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
        title_text="가용대수 (설비 일정은 환산)",
        gridcolor=tokens.BORDER,
        zerolinecolor=tokens.BORDER_STRONG,
        rangemode="tozero",
        range=[0, top * 1.22],
    )
    add_figure_outer_border(figure, emphasize_bottom=True)
    flush_layout_items(figure)
    return figure


def _number(value: object) -> float:
    """기존보유 한 칸. 「—」(NaN·없음)이면 0 이다."""
    if value is None:
        return 0.0
    number = float(value)  # type: ignore[arg-type]
    return 0.0 if number != number else number
