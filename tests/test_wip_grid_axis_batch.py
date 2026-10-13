# Purpose: 재공 격자의 축 설정을 한 번에 주는 생성이 칸마다 축을 고치던 생성과 같은 그림인지 본다.

"""칸마다 `update_xaxes(row=, col=)` 를 부르던 옛 생성을 그대로 옮긴 참조와 지금 생성의 `to_json()`
을 여러 격자 크기에서 견준다. 축 이름 대응을 잘못 짜면 단위(매/Kea)·범위가 다른 칸에 붙는다."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from capa_simulation.components.plotly_layout import chart_canvas_layout
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.wip_status_dashboard import (
    WIP_GRID_CELL_HEIGHT_PX,
    WIP_GRID_CELL_WIDTH_PX,
    _add_cell_traces,
    build_wip_status_grid_figure,
)
from capa_simulation.design import tokens
from capa_simulation.services.wip_status import build_wip_history_demo, build_wip_route_scope

START = date(2026, 9, 1)
END = date(2026, 9, 11)


def _per_cell_axis_reference(
    data: pd.DataFrame,
    routes: pd.DataFrame,
    products: list[str],
    start_date: date,
    end_date: date,
    process_labels: ProcessLabels | None = None,
) -> go.Figure:
    """옛 생성(칸마다 `update_xaxes`·`update_yaxes`) 그대로. 검증 분기는 뺐다."""
    labels = process_labels or ProcessLabels()
    ordered_products = list(dict.fromkeys(str(product).strip() for product in products))
    route_scope = build_wip_route_scope(routes)
    lanes = route_scope[["STEP_SEQ", "공정", "소요기준"]].drop_duplicates().reset_index(drop=True)
    prepared = data.copy()
    prepared["일자"] = pd.to_datetime(prepared["일자"], errors="coerce").dt.date
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
        vertical_spacing=min(0.07, 28 / max(rows * WIP_GRID_CELL_HEIGHT_PX, 1)),
    )
    legend_seen: set[str] = set()
    all_dates = [timestamp.date() for timestamp in pd.date_range(start_date, end_date, freq="D")]
    tick_text = [value.strftime("%m.%d") for value in all_dates]
    for row_index, product in enumerate(ordered_products, start=1):
        for column_index, lane in enumerate(lanes.itertuples(index=False), start=1):
            cell = prepared.loc[
                prepared["제품정보"].astype(str).eq(product)
                & prepared["공정"].astype(str).eq(str(lane.공정))
                & prepared["STEP_SEQ"].astype(str).eq(str(lane.STEP_SEQ))
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
                    figure, cell, row=row_index, col=column_index, legend_seen=legend_seen
                )
            unit = "매" if str(lane.소요기준) == "WF" else "Kea"
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
                tickfont={"size": 9, "color": tokens.TEXT_MUTED},
                title=None,
                showgrid=False,
                zeroline=False,
                linecolor=tokens.HEADER_BACKGROUND,
            )
            figure.update_yaxes(
                row=row_index,
                col=column_index,
                rangemode="tozero",
                title={"text": unit, "font": {"size": 10, "color": tokens.TEXT_MUTED}},
                tickfont={"size": 9, "color": tokens.TEXT_MUTED},
                gridcolor=tokens.HEADER_BACKGROUND,
                zeroline=False,
                linecolor=tokens.HEADER_BACKGROUND,
            )
    figure.update_layout(
        width=max(430, cols * WIP_GRID_CELL_WIDTH_PX + 90),
        height=max(420, rows * WIP_GRID_CELL_HEIGHT_PX + 110),
        barmode="group",
        bargap=0.18,
        bargroupgap=0.05,
        **chart_canvas_layout(font_size=11),
        hoverlabel={"font": {"family": tokens.FONT_FAMILY}},
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
        annotation.font = {"family": tokens.FONT_FAMILY, "size": 12, "color": tokens.TEXT}
    return figure


def _grid(product_count: int, lane_count: int, *, skip: int = 0) -> dict[str, Any]:
    """제품 × (P·T 를 섞은 STEP) 격자. `skip` 개 칸은 경로가 없다(제품 하나가 그 STEP 을 안 탐)."""
    products = [f"Product-{index:02d}" for index in range(product_count)]
    lanes = [
        (
            f"{'P' if index % 2 == 0 else 'T'}{100 + index * 10}",
            f"Process-{index:02d}",
            "WF" if index % 3 == 0 else "CHIP",
        )
        for index in range(lane_count)
    ]
    route_rows = [
        {"공정": process, "STEP_SEQ": step, "제품정보": product, "소요기준": basis}
        for product_index, product in enumerate(products)
        for lane_index, (step, process, basis) in enumerate(lanes)
        if not (product_index == product_count - 1 and lane_index < skip)
    ]
    routes = pd.DataFrame(route_rows)
    standard = pd.DataFrame(
        [
            {
                "일자": current,
                "공정": process,
                "소요기준": basis,
                "제품정보": product,
                # 일부 칸은 표준이 없어 `표준 미설정` 막대가 선다.
                "일 표준 가능량": None if (lane_index + product_index) % 4 == 3 else 120.0,
            }
            for current in pd.date_range(START, END, freq="D")
            for lane_index, (_, process, basis) in enumerate(lanes)
            for product_index, product in enumerate(products)
        ]
    )
    history = build_wip_history_demo(routes, standard, START, END, today=date(2026, 9, 8))
    # 화면 선택 차례(제품명 앞뒤 공백도 그대로 받는다 — 생성이 strip 한다).
    return {
        "data": history,
        "routes": routes,
        "products": [
            f" {product} " if index == 0 else product for index, product in enumerate(products)
        ],
        "start_date": START,
        "end_date": END,
        "process_labels": ProcessLabels(labels={"Process-00": "공정 영"}),
    }


@pytest.mark.parametrize(
    ("product_count", "lane_count", "skip"),
    [
        pytest.param(1, 1, 0, id="1x1"),
        pytest.param(3, 5, 0, id="3x5"),
        pytest.param(3, 5, 2, id="3x5-no-route"),
        pytest.param(4, 15, 3, id="4x15"),
        pytest.param(4, 60, 5, id="4x60"),
    ],
)
def test_batched_axes_give_the_same_figure_as_per_cell_updates(
    product_count: int, lane_count: int, skip: int
) -> None:
    inputs = _grid(product_count, lane_count, skip=skip)

    figure = build_wip_status_grid_figure(**inputs)
    reference = _per_cell_axis_reference(**inputs)

    assert figure.to_json() == reference.to_json()
    if skip:
        assert sum(item.text == "경로 없음" for item in figure.layout.annotations) == skip


def test_each_cell_keeps_its_own_unit() -> None:
    """칸 단위(매/Kea)가 그 칸의 소요기준을 따른다 — 축 이름 대응이 어긋나면 옆 칸 단위가 붙는다."""
    inputs = _grid(2, 4)
    figure = build_wip_status_grid_figure(**inputs)

    units = [
        figure.layout[figure.get_subplot(row, col).yaxis.plotly_name].title.text
        for row in (1, 2)
        for col in (1, 2, 3, 4)
    ]
    assert units == ["매", "Kea", "Kea", "매"] * 2
