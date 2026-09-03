# Purpose: Plotly matrix for daily WIP and flow against standard target Capa.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

"""Plotly matrix for daily WIP and flow against standard target Capa."""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from capa_simulation.services.wip_status import (
    WIP_HISTORY_COLUMNS,
    build_wip_route_scope,
)

WIP_GRID_CELL_WIDTH_PX = 340
WIP_GRID_CELL_HEIGHT_PX = 330

_TEXT_COLOR = "#27272A"
_MUTED_TEXT_COLOR = "#71717A"
_GRID_COLOR = "#E4E4E7"
_SURFACE_COLOR = "#FFFFFF"
_HELD_COLOR = "#A1A1AA"
_INFLOW_COLOR = "#60A5FA"
_FLOW_MET_COLOR = "#34D399"
_FLOW_SHORT_COLOR = "#FB7185"
_FLOW_UNSET_COLOR = "#A78BFA"
_STANDARD_COLOR = "#18181B"


def build_wip_status_grid_figure(
    data: pd.DataFrame,
    routes: pd.DataFrame,
    products: list[str],
    start_date: date,
    end_date: date,
) -> go.Figure:
    """Build a fixed-cell matrix ordered by product rows and STEP columns."""
    missing = [column for column in WIP_HISTORY_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"재공 현황 차트 필수 컬럼이 없습니다: {', '.join(missing)}")
    if start_date > end_date:
        raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")
    ordered_products = list(dict.fromkeys(str(product).strip() for product in products))
    if not ordered_products or any(not product for product in ordered_products):
        raise ValueError("재공 현황 차트에 표시할 제품을 선택해야 합니다.")

    route_scope = build_wip_route_scope(routes)
    lanes = route_scope[["STEP_SEQ", "공정", "소요기준"]].drop_duplicates().reset_index(drop=True)
    if lanes.empty:
        raise ValueError("재공 현황 차트에 표시할 공정·STEP 경로가 없습니다.")

    prepared = data.copy()
    parsed_dates = pd.to_datetime(prepared["일자"], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("재공 현황 차트의 일자는 유효한 날짜여야 합니다.")
    prepared["일자"] = parsed_dates.dt.date
    rows = len(ordered_products)
    cols = len(lanes)
    titles = [
        f"<b>{lane.STEP_SEQ}</b> · {lane.공정}<br>{product}"
        for product in ordered_products
        for lane in lanes.itertuples(index=False)
    ]
    figure = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=titles,
        horizontal_spacing=min(0.045, 18 / max(cols * WIP_GRID_CELL_WIDTH_PX, 1)),
        vertical_spacing=min(0.07, 28 / max(rows * WIP_GRID_CELL_HEIGHT_PX, 1)),
    )
    legend_seen: set[str] = set()
    all_dates = [timestamp.date() for timestamp in pd.date_range(start_date, end_date, freq="D")]
    tick_text = [value.strftime("%m.%d") for value in all_dates]

    for row_index, product in enumerate(ordered_products, start=1):
        for column_index, lane in enumerate(lanes.itertuples(index=False), start=1):
            process = str(lane.공정)
            step = str(lane.STEP_SEQ)
            basis = str(lane.소요기준)
            cell = prepared.loc[
                prepared["제품정보"].astype(str).eq(product)
                & prepared["공정"].astype(str).eq(process)
                & prepared["STEP_SEQ"].astype(str).eq(step)
            ].sort_values("일자", kind="stable")
            if cell.empty:
                figure.add_annotation(
                    text="경로 없음",
                    x=0.5,
                    y=0.5,
                    xref="x domain",
                    yref="y domain",
                    showarrow=False,
                    font={"color": _MUTED_TEXT_COLOR, "size": 12},
                    row=row_index,
                    col=column_index,
                )
            else:
                _add_cell_traces(
                    figure,
                    cell,
                    row=row_index,
                    col=column_index,
                    legend_seen=legend_seen,
                )
            unit = "매" if basis == "WF" else "Kea"
            figure.update_xaxes(
                row=row_index,
                col=column_index,
                range=[
                    pd.Timestamp(start_date) - pd.Timedelta(hours=12),
                    pd.Timestamp(end_date) + pd.Timedelta(hours=12),
                ],
                tickmode="array",
                tickvals=all_dates,
                ticktext=tick_text,
                tickangle=-45,
                tickfont={"size": 9, "color": _MUTED_TEXT_COLOR},
                title=None,
                showgrid=False,
                zeroline=False,
                linecolor=_GRID_COLOR,
            )
            figure.update_yaxes(
                row=row_index,
                col=column_index,
                rangemode="tozero",
                title={"text": unit, "font": {"size": 10, "color": _MUTED_TEXT_COLOR}},
                tickfont={"size": 9, "color": _MUTED_TEXT_COLOR},
                gridcolor=_GRID_COLOR,
                zeroline=False,
                linecolor=_GRID_COLOR,
            )

    figure_width = max(430, cols * WIP_GRID_CELL_WIDTH_PX + 90)
    figure_height = max(420, rows * WIP_GRID_CELL_HEIGHT_PX + 110)
    figure.update_layout(
        width=figure_width,
        height=figure_height,
        barmode="group",
        bargap=0.18,
        bargroupgap=0.05,
        plot_bgcolor=_SURFACE_COLOR,
        paper_bgcolor=_SURFACE_COLOR,
        font={"family": "Malgun Gothic", "color": _TEXT_COLOR, "size": 11},
        hoverlabel={"font": {"family": "Malgun Gothic"}},
        hovermode="closest",
        margin={"l": 54, "r": 24, "t": 92, "b": 50},
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.055,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 11},
        },
    )
    for annotation in figure.layout.annotations:
        annotation.font = {"family": "Malgun Gothic", "size": 12, "color": _TEXT_COLOR}
    return figure


def _add_cell_traces(
    figure: go.Figure,
    cell: pd.DataFrame,
    *,
    row: int,
    col: int,
    legend_seen: set[str],
) -> None:
    x_values = cell["일자"].tolist()
    periods = cell["시점"].astype(str).tolist()
    _add_bar(
        figure,
        name="보유 재공",
        x=x_values,
        y=cell["보유 재공"].tolist(),
        periods=periods,
        color=_HELD_COLOR,
        offsetgroup="held",
        row=row,
        col=col,
        legend_seen=legend_seen,
    )
    _add_bar(
        figure,
        name="유입",
        x=x_values,
        y=cell["유입량"].tolist(),
        periods=periods,
        color=_INFLOW_COLOR,
        offsetgroup="inflow",
        row=row,
        col=col,
        legend_seen=legend_seen,
    )

    for status, name, color in (
        ("충족", "Flow 충족", _FLOW_MET_COLOR),
        ("부족", "Flow 부족", _FLOW_SHORT_COLOR),
        ("표준 미설정", "Flow (표준 미설정)", _FLOW_UNSET_COLOR),
    ):
        mask = cell["상태"].astype(str).eq(status)
        if not mask.any():
            continue
        customdata = cell.loc[
            mask,
            ["일 표준 가능량", "표준 대비 Gap", "Flow 충족률", "시점"],
        ].to_numpy()
        showlegend = name not in legend_seen
        legend_seen.add(name)
        figure.add_trace(
            go.Bar(
                name=name,
                x=cell.loc[mask, "일자"],
                y=cell.loc[mask, "Flow량"],
                marker={"color": color},
                offsetgroup="flow",
                customdata=customdata,
                hovertemplate=(
                    "%{x|%m.%d}<br>Flow %{y:,.1f}<br>표준 %{customdata[0]:,.1f}"
                    "<br>Gap %{customdata[1]:+,.1f}<br>충족률 %{customdata[2]:.1%}"
                    "<br>%{customdata[3]}<extra></extra>"
                ),
                showlegend=showlegend,
            ),
            row=row,
            col=col,
        )

    standard = pd.to_numeric(cell["일 표준 가능량"], errors="coerce")
    if standard.notna().any():
        name = "표준 가능량"
        showlegend = name not in legend_seen
        legend_seen.add(name)
        figure.add_trace(
            go.Scatter(
                name=name,
                x=cell["일자"],
                y=standard,
                mode="lines+markers",
                line={"color": _STANDARD_COLOR, "width": 2, "dash": "dot"},
                marker={"size": 5, "color": _STANDARD_COLOR},
                hovertemplate="%{x|%m.%d}<br>표준 가능량 %{y:,.1f}<extra></extra>",
                showlegend=showlegend,
            ),
            row=row,
            col=col,
        )


def _add_bar(
    figure: go.Figure,
    *,
    name: str,
    x: list[object],
    y: list[object],
    periods: list[str],
    color: str,
    offsetgroup: str,
    row: int,
    col: int,
    legend_seen: set[str],
) -> None:
    showlegend = name not in legend_seen
    legend_seen.add(name)
    figure.add_trace(
        go.Bar(
            name=name,
            x=x,
            y=y,
            marker={"color": color},
            offsetgroup=offsetgroup,
            customdata=cast(list[list[str]], [[period] for period in periods]),
            hovertemplate=(
                f"%{{x|%m.%d}}<br>{name} %{{y:,.1f}}<br>%{{customdata[0]}}<extra></extra>"
            ),
            showlegend=showlegend,
        ),
        row=row,
        col=col,
    )
