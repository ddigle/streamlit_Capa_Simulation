# Purpose: Plotly figures for the Dynamic Capa analysis prototype.

"""Plotly figures for the Dynamic Capa analysis prototype."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.services.dynamic_capacity import aggregate_dynamic_capacity

_TEXT_COLOR = "#27272A"
_MUTED_TEXT_COLOR = "#71717A"
_GRID_COLOR = "#E4E4E7"
_SURFACE_COLOR = "#FFFFFF"
_STANDARD_COLOR = "#3F3F46"
_EFFECTIVE_COLOR = "#A1A1AA"
_ACTUAL_COLOR = "#52525B"
_NORMAL_COLOR = "#D4D4D8"
_WATCH_COLOR = "#FDE68A"
_IMPROVEMENT_COLOR = "#FDA4AF"


def build_process_comparison_figure(process_summary: pd.DataFrame) -> go.Figure:
    """Compare equipment performance and Capa realization for every process."""
    prepared = process_summary.sort_values("Capa 실현률", ascending=True, kind="stable")
    colors = prepared["상태"].map(
        {"정상": _NORMAL_COLOR, "관찰": _WATCH_COLOR, "개선 필요": _IMPROVEMENT_COLOR}
    )
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            name="설비 성능 실현률",
            y=prepared["공정"],
            x=prepared["설비 성능 실현률"],
            orientation="h",
            marker={"color": _EFFECTIVE_COLOR},
            text=prepared["설비 성능 실현률"],
            texttemplate="%{text:.1%}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>설비 성능 실현률 %{x:.1%}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            name="Capa 실현률",
            y=prepared["공정"],
            x=prepared["Capa 실현률"],
            orientation="h",
            marker={"color": colors, "line": {"color": _STANDARD_COLOR, "width": 1}},
            text=prepared["Capa 실현률"],
            texttemplate="<b>%{text:.1%}</b>",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>Capa 실현률 %{x:.1%}<extra></extra>",
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
    figure.update_yaxes(title=None, autorange=True)
    return figure


def build_capacity_waterfall_figure(summary: pd.Series) -> go.Figure:
    """Show the sequential bridge from standard Capa to production actual."""
    labels = ["표준 Capa", "효율 Gap", "UPEH Gap", "Rundown", "기타 Gap", "실제 실적"]
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
            connector={"line": {"color": _GRID_COLOR, "width": 1}},
            increasing={"marker": {"color": _NORMAL_COLOR}},
            decreasing={"marker": {"color": _IMPROVEMENT_COLOR}},
            totals={"marker": {"color": _ACTUAL_COLOR}},
            hovertemplate="%{x}<br>%{y:,.1f}<extra></extra>",
        )
    )
    _apply_common_layout(figure)
    figure.update_layout(height=380, margin={"l": 20, "r": 20, "t": 20, "b": 30})
    figure.update_yaxes(title=None, rangemode="tozero")
    return figure


def build_capacity_trend_figure(detail: pd.DataFrame) -> go.Figure:
    """Show daily standard, effective, and production actual capacity."""
    daily = aggregate_dynamic_capacity(detail, ["일자"]).sort_values("일자", kind="stable")
    figure = go.Figure()
    for column, label, color, dash in (
        ("표준 Capa", "표준 Capa", _STANDARD_COLOR, "dash"),
        ("실효 Capa", "실효 Capa", _EFFECTIVE_COLOR, "solid"),
        ("실적수량", "실제 실적", _ACTUAL_COLOR, "solid"),
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
        plot_bgcolor=_SURFACE_COLOR,
        paper_bgcolor=_SURFACE_COLOR,
        font={"family": "Malgun Gothic", "color": _TEXT_COLOR, "size": 13},
        hoverlabel={"font": {"family": "Malgun Gothic"}},
    )
    figure.update_xaxes(gridcolor=_GRID_COLOR, zeroline=False, linecolor=_GRID_COLOR)
    figure.update_yaxes(gridcolor=_GRID_COLOR, zeroline=False, linecolor=_GRID_COLOR)
