# Purpose: Plotly figures for the Dynamic Capa analysis prototype.

"""Plotly figures for the Dynamic Capa analysis prototype."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.plotly_layout import apply_axis_text_color, chart_canvas_layout
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import tokens
from capa_simulation.services.dynamic_capacity import aggregate_dynamic_capacity


def build_process_comparison_figure(
    process_summary: pd.DataFrame,
    *,
    process_labels: ProcessLabels | None = None,
) -> go.Figure:
    """Compare equipment performance and Capa realization for every process.

    `process_labels` 는 y축 눈금과 hover 의 공정 글자에만 쓴다. 정렬·색·값은 원본 프레임
    그대로이고, 범주 값은 원본 공정이라 표시명이 다른 공정의 원본과 같아도 두 줄로 갈린다
    (`ProcessLabels.category_axis`). 곁 「관리 우선순위」 표처럼 나쁜 공정이 맨 위다.
    """
    prepared = process_summary.sort_values("Capa 실현률", ascending=True, kind="stable")
    axis = (process_labels or ProcessLabels()).category_axis(prepared["공정"])
    colors = prepared["상태"].map(
        {
            "정상": tokens.STATUS_SECURE,
            "관찰": tokens.STATUS_WARNING,
            "개선 필요": tokens.STATUS_SHORTAGE,
        }
    )
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            name="설비 성능 실현률",
            y=axis.values,
            customdata=axis.texts,
            x=prepared["설비 성능 실현률"],
            orientation="h",
            # 막대 굵기 25px 라 중간 등급이다. 가로 막대라 값 쪽인 오른쪽 끝이 둥글다.
            marker={
                "color": tokens.SERIES_EFFECTIVE,
                "cornerradius": tokens.BAR_CORNER_RADIUS_MEDIUM_PX,
            },
            text=prepared["설비 성능 실현률"],
            texttemplate="%{text:.1%}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{customdata}<br>설비 성능 실현률 %{x:.1%}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            name="Capa 실현률",
            y=axis.values,
            customdata=axis.texts,
            x=prepared["Capa 실현률"],
            orientation="h",
            marker={
                "color": colors,
                "line": {"color": tokens.SERIES_STANDARD, "width": 1},
                "cornerradius": tokens.BAR_CORNER_RADIUS_MEDIUM_PX,
            },
            text=prepared["Capa 실현률"],
            texttemplate="<b>%{text:.1%}</b>",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{customdata}<br>Capa 실현률 %{x:.1%}<extra></extra>",
        )
    )
    _apply_common_layout(figure)
    figure.update_layout(
        barmode="group",
        height=max(310, 56 * len(prepared) + 110),
        margin={"l": 8, "r": 68, "t": 20, "b": 30},
        legend={"orientation": "h", "x": 0, "y": 1.12, "xanchor": "left"},
    )
    upper_bound = max(1.05, float(prepared["설비 성능 실현률"].max()) * 1.12)
    figure.update_xaxes(tickformat=".0%", range=[0, upper_bound], title=None)
    # 막대 축은 첫 범주를 맨 아래에 놓는다 — 뒤집어 실현률이 낮은 공정을 맨 위로 올린다.
    figure.update_yaxes(title=None, autorange="reversed", **axis.layout())
    return figure


def build_capacity_waterfall_figure(summary: pd.Series) -> go.Figure:
    """Show the sequential bridge from standard Capa to production actual."""
    # 손실 칸은 수량이고 이름은 「손실을 파고드는 화면」 카드와 같다 — 「효율 Gap」 · 「UPEH
    # Gap」 은 공정 상세 표의 비율 차이 이름이다(설계 규칙 UI-CON-02).
    labels = ["표준 Capa", "효율 손실", "UPEH 손실", "재공부족 미활용", "기타 Gap", "실제 실적"]
    values = [
        float(summary["표준 Capa"]),
        -float(summary["효율 손실 Capa"]),
        -float(summary["UPEH 손실 Capa"]),
        -float(summary["재공부족 미활용 Capa"]),
        -float(summary["기타 정합성 Gap"]),
        float(summary["실적수량"]),
    ]
    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=["absolute", "relative", "relative", "relative", "relative", "total"],
            text=[f"{value:,.0f}" for value in values],
            textposition="outside",
            customdata=labels,
            connector={"line": {"color": tokens.HEADER_BACKGROUND, "width": 1}},
            increasing={"marker": {"color": tokens.STATUS_SECURE}},
            decreasing={"marker": {"color": tokens.STATUS_SHORTAGE}},
            totals={"marker": {"color": tokens.SERIES_ACTUAL}},
            # 값은 막대 글과 같은 그 칸의 증감이다 — `%{y}` 는 그 칸까지의 누계라 손실 이름에 누계가
            # 붙는다. 이름은 `customdata` 다 — `%{x}` 는 아래 접은 눈금 글자를 낸다.
            hovertemplate="%{customdata}<br>%{delta:,.1f}<extra></extra>",
        )
    )
    _apply_common_layout(figure)
    figure.update_layout(height=380, margin={"l": 20, "r": 20, "t": 20, "b": 30})
    # 자동 각도는 칸이 눈금 글자보다 좁으면 눈금을 30도 · 90도로 눕히고, 어느 쪽인지가 창 폭과 앞
    # 그림 상태에 달려 이웃과 겹치기도 한다. 눕히지 않게 각도를 못 박고, 좁은 칸에 들도록 이름을
    # 모두 두 줄로 접는다.
    figure.update_xaxes(
        tickmode="array",
        tickvals=labels,
        ticktext=[label.replace(" ", "<br>") for label in labels],
        tickangle=0,
    )
    figure.update_yaxes(title=None, rangemode="tozero")
    return figure


def build_capacity_trend_figure(detail: pd.DataFrame) -> go.Figure:
    """Show daily standard, effective, and production actual capacity."""
    daily = aggregate_dynamic_capacity(detail, ["일자"]).sort_values("일자", kind="stable")
    figure = go.Figure()
    # 세 계열은 색이 아니라 **선 모양**으로 갈린다. `SERIES_EFFECTIVE` 와 `SERIES_ACTUAL`
    # 은 서로 대비가 1.89:1 뿐이고 둘 다 무채색이라 색각이상 시뮬레이션 뒤에도 그대로다 —
    # 명도만으로는 두 선이 겹치는 구간에서 갈리지 않는다. 실적만 실선으로 남기는 것은
    # "실제로 일어난 것" 이라는 뜻과 맞춘 것이다.
    for column, label, color, dash in (
        ("표준 Capa", "표준 Capa", tokens.SERIES_STANDARD, "dash"),
        ("실효 Capa", "실효 Capa", tokens.SERIES_EFFECTIVE, "dot"),
        ("실적수량", "실제 실적", tokens.SERIES_ACTUAL, "solid"),
    ):
        figure.add_trace(
            go.Scatter(
                name=label,
                x=daily["일자"],
                y=daily[column],
                mode="lines+markers",
                line={"color": color, "width": 2.4, "dash": dash},
                marker={"size": 6},
                hovertemplate=f"%{{x|%m.%d}}<br>{label} %{{y:,.1f}}<extra></extra>",
            )
        )
    _apply_common_layout(figure)
    figure.update_layout(
        height=380,
        margin={"l": 20, "r": 20, "t": 20, "b": 30},
        legend={"orientation": "h", "x": 0, "y": 1.12, "xanchor": "left"},
        hovermode="x unified",
    )
    figure.update_xaxes(title=None, tickformat="%m.%d")
    figure.update_yaxes(title=None, rangemode="tozero")
    return figure


def _apply_common_layout(figure: go.Figure) -> None:
    figure.update_layout(
        **chart_canvas_layout(font_size=13),
        hoverlabel={"font": {"family": tokens.FONT_FAMILY}},
    )
    figure.update_xaxes(
        gridcolor=tokens.HEADER_BACKGROUND, zeroline=False, linecolor=tokens.HEADER_BACKGROUND
    )
    figure.update_yaxes(
        gridcolor=tokens.HEADER_BACKGROUND, zeroline=False, linecolor=tokens.HEADER_BACKGROUND
    )
    apply_axis_text_color(figure)
