# Purpose: Plotly matrix for daily WIP and flow against standard target Capa.

"""Plotly matrix for daily WIP and flow against standard target Capa."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from capa_simulation.components.plotly_layout import chart_canvas_layout
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import theme, tokens
from capa_simulation.services.wip_status import (
    WIP_HISTORY_COLUMNS,
    build_wip_route_scope,
)

WIP_GRID_CELL_WIDTH_PX = 340
# 칸 하나(축 영역)의 높이.
WIP_GRID_CELL_HEIGHT_PX = 300
# 줄 사이 틈. 아래 줄 칸의 두 줄 제목(12px 서체, 약 31px)과 위 줄 칸의 -45° 날짜 눈금(9px 서체,
# 축에서 띄운 자리까지 약 30px)이 함께 들어가고, 눈금과 제목 사이가 약 18px 떠 제목이 위 칸이 아니라
# 아래 칸 것으로 읽힌다(64px 이면 브라우저에서 2px 만 떴다). 그림 폭·높이가 px 고정이라 창 크기와
# 상관없이 이 틈이 선다.
WIP_GRID_ROW_GAP_PX = 80
# 위 여백은 범례와 첫 줄 제목, 아래 여백은 마지막 줄 날짜 눈금 자리다.
_GRID_MARGIN_TOP_PX = 92
_GRID_MARGIN_BOTTOM_PX = 50
# 범례 아래 끝을 첫 줄 칸 위 끝에서 띄우는 높이. 첫 줄 칸의 두 줄 제목(12px 서체, 약 33px) 위로 약
# 16px 떠 범례가 제목과 겹치지 않고, 범례(11px 서체 한 줄, 약 29px)와 plotly 자동 여백의 띄움
# (12px)이 위 여백 안에 든다 — 넘으면 plotly 가 위 여백을 늘려 칸이 그만큼 낮아진다(1.055 였던 3줄은
# 58px 라 약 7px 늘었다). 범례 y 는 축 영역 비율이라 비율로 고정하면 떠오르는 높이가 줄 수를 따라
# 바뀐다 — 1.055 는 1줄이면 약 16px 라 범례가 첫 줄 제목과 겹쳤다(2026-10-27 E2E).
_GRID_LEGEND_LIFT_PX = 50
# 직전 회차에 만든 격자 Figure 한 벌과 그 입력 사본(세션 칸). `remembered_wip_status_grid_figure`.
WIP_GRID_FIGURE_MEMO_KEY = "wip_status_grid_figure_memo"


def wip_grid_height_px(rows: int) -> int:
    """격자 그림 높이 — 위·아래 여백 + 줄마다 칸 높이 + 줄 사이마다 `WIP_GRID_ROW_GAP_PX`."""
    return max(
        420,
        _GRID_MARGIN_TOP_PX
        + _GRID_MARGIN_BOTTOM_PX
        + rows * WIP_GRID_CELL_HEIGHT_PX
        + max(rows - 1, 0) * WIP_GRID_ROW_GAP_PX,
    )


def _grid_plot_height_px(rows: int) -> int:
    """축 영역 높이 — 그림 높이 − 위·아래 여백. 줄 사이·범례 자리의 비율은 이 높이에 대한 것이다."""
    return wip_grid_height_px(rows) - _GRID_MARGIN_TOP_PX - _GRID_MARGIN_BOTTOM_PX


def wip_grid_vertical_spacing(rows: int) -> float:
    """`make_subplots` 의 줄 사이 비율. 축 영역(그림 높이 − 위·아래 여백)에 대한 줄 사이 틈이다.

    비율을 격자 높이에 고정 px 를 나눈 값으로 두면 틈이 약 27px 라, 두 줄 제목과 위 칸의 기울인
    날짜 눈금이 겹쳤다(2026-10-26 E2E — 3줄 × 5칸에서 제목 10개).
    """
    return WIP_GRID_ROW_GAP_PX / _grid_plot_height_px(rows)


def wip_grid_legend_y(rows: int) -> float:
    """범례 아래 끝의 y(축 영역 비율 — 1 이 첫 줄 칸 위 끝). 줄 수와 상관없이 첫 줄 칸 위로
    `_GRID_LEGEND_LIFT_PX` 다(2026-10-27 E2E — 1줄 격자에서 범례가 첫 줄 제목과 겹쳤다)."""
    return 1 + _GRID_LEGEND_LIFT_PX / _grid_plot_height_px(rows)


def remembered_wip_status_grid_figure(
    data: pd.DataFrame,
    routes: pd.DataFrame,
    products: list[str],
    start_date: date,
    end_date: date,
    process_labels: ProcessLabels | None = None,
) -> go.Figure:
    """`build_wip_status_grid_figure` 를 세션에 한 벌 기억한다. 입력이 같으면 직전 Figure 를 그대로
    돌려준다 — 사이드바 팝업 열기·닫기처럼 그림과 무관한 rerun 마다 격자 전체를 다시 만들지 않는다.

    「같다」는 그림이 읽는 것 **전부의 내용**이다. 재공·경로 표는 직전 입력 사본과
    `DataFrame.equals`(칸 형까지)로 견주고 지문을 쓰지 않는다 — 해시 지문은 object 칸의 `1` 과
    `'1'` 을 같게 본다. 나머지는 제품 차례·조회 구간·공정 표시명 지도·**테마**(토큰 색이 테마마다
    다르다)다. 오늘 날짜는 재공 표의 일자·시점 칸으로 들어온다. 리비전 번호는 쓰지 않는다.
    꺼낸 Figure 는 고치지 않는다(`st.plotly_chart` 도 고치지 않는다). 만들다 실패하면 기억하지
    않는다.
    """
    labels = process_labels or ProcessLabels()
    conditions: tuple[Any, ...] = (
        theme.current_mode(),
        tuple(products),
        start_date,
        end_date,
        tuple(sorted(labels.labels.items())),
    )
    memo = st.session_state.get(WIP_GRID_FIGURE_MEMO_KEY)
    if (
        isinstance(memo, tuple)
        and len(memo) == 4
        and memo[0] == conditions
        and isinstance(memo[1], pd.DataFrame)
        and isinstance(memo[2], pd.DataFrame)
        and isinstance(memo[3], go.Figure)
        and memo[1].equals(data)
        and memo[2].equals(routes)
    ):
        return memo[3]
    figure = build_wip_status_grid_figure(
        data, routes, products, start_date, end_date, process_labels=labels
    )
    st.session_state[WIP_GRID_FIGURE_MEMO_KEY] = (conditions, data.copy(), routes.copy(), figure)
    return figure


def build_wip_status_grid_figure(
    data: pd.DataFrame,
    routes: pd.DataFrame,
    products: list[str],
    start_date: date,
    end_date: date,
    process_labels: ProcessLabels | None = None,
) -> go.Figure:
    """Build a fixed-cell matrix ordered by product rows and STEP columns.

    `process_labels` 는 subplot 제목에만 쓴다. 아래 셀 대조는 원본 `lane.공정` 을 그대로
    써야 한다 — 라벨로 대조하면 모든 칸이 `경로 없음` 이 된다.
    """
    labels = process_labels or ProcessLabels()
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
        f"<b>{lane.STEP_SEQ}</b> · {labels.label(lane.공정)}<br>{product}"
        for product in ordered_products
        for lane in lanes.itertuples(index=False)
    ]
    figure = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=titles,
        horizontal_spacing=min(0.045, 18 / max(cols * WIP_GRID_CELL_WIDTH_PX, 1)),
        vertical_spacing=wip_grid_vertical_spacing(rows),
    )
    legend_seen: set[str] = set()
    all_dates = [timestamp.date() for timestamp in pd.date_range(start_date, end_date, freq="D")]
    tick_text = [value.strftime("%m.%d") for value in all_dates]
    # 칸마다 `update_xaxes(row=, col=)` 를 부르면 부를 때마다 모든 축을 훑어 칸 수의 제곱으로
    # 느려진다. 칸의 축 이름(`get_subplot`)으로 설정을 모았다가 루프 뒤에 한 번에 준다 — 같은
    # 병합(update)이라 결과 Figure 는 같다.
    axis_layout: dict[str, dict[str, Any]] = {}

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
                    font={"color": tokens.TEXT_MUTED, "size": 12},
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
            subplot = figure.get_subplot(row_index, column_index)
            axis_layout[subplot.xaxis.plotly_name] = {
                "range": [
                    pd.Timestamp(start_date) - pd.Timedelta(hours=12),
                    pd.Timestamp(end_date) + pd.Timedelta(hours=12),
                ],
                "tickmode": "array",
                "tickvals": all_dates,
                "ticktext": tick_text,
                "tickangle": -45,
                "tickfont": {"size": 9, "color": tokens.TEXT_MUTED},
                "title": None,
                "showgrid": False,
                "zeroline": False,
                "linecolor": tokens.HEADER_BACKGROUND,
            }
            axis_layout[subplot.yaxis.plotly_name] = {
                "rangemode": "tozero",
                "title": {"text": unit, "font": {"size": 10, "color": tokens.TEXT_MUTED}},
                "tickfont": {"size": 9, "color": tokens.TEXT_MUTED},
                "gridcolor": tokens.HEADER_BACKGROUND,
                "zeroline": False,
                "linecolor": tokens.HEADER_BACKGROUND,
            }

    figure.update_layout(axis_layout)
    figure_width = max(430, cols * WIP_GRID_CELL_WIDTH_PX + 90)
    figure_height = wip_grid_height_px(rows)
    figure.update_layout(
        width=figure_width,
        height=figure_height,
        barmode="group",
        bargap=0.18,
        bargroupgap=0.05,
        **chart_canvas_layout(font_size=11),
        hoverlabel={"font": {"family": tokens.FONT_FAMILY}},
        hovermode="closest",
        margin={"l": 54, "r": 24, "t": _GRID_MARGIN_TOP_PX, "b": _GRID_MARGIN_BOTTOM_PX},
        legend={
            "orientation": "h",
            "x": 0,
            "y": wip_grid_legend_y(rows),
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 11},
        },
    )
    for annotation in figure.layout.annotations:
        annotation.font = {"family": tokens.FONT_FAMILY, "size": 12, "color": tokens.TEXT}
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
        color=tokens.WIP_HELD,
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
        color=tokens.WIP_INFLOW,
        offsetgroup="inflow",
        row=row,
        col=col,
        legend_seen=legend_seen,
    )

    for status, name, color in (
        ("충족", "Flow 충족", tokens.WIP_FLOW_MET),
        ("부족", "Flow 부족", tokens.WIP_FLOW_SHORT),
        ("표준 미설정", "Flow (표준 미설정)", tokens.WIP_FLOW_UNSET),
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
                line={"color": tokens.TEXT, "width": 2, "dash": "dot"},
                marker={"size": 5, "color": tokens.TEXT},
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
