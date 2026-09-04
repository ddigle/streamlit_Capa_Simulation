# Purpose: HOME 대시보드의 요약·계획 상세·B/N 상세 Plotly Figure 를 생성한다.

"""Plotly figures for the HOME dashboard.

각 함수는 고정 분류 영역과 스크롤 월 영역 두 Figure 를 한 쌍으로 돌려준다. 페이지는
이 결과를 캐시하고 렌더링만 담당한다.
"""

from __future__ import annotations

import html
import unicodedata
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from capa_simulation.components.home_dimensions import (
    DASHBOARD_TITLE_HEIGHT_PX,
    LOB_BOTTOM_MARGIN_PX,
    LOB_CHART_HEIGHT_PX,
    LOB_FIGURE_HEIGHT_PX,
    LOB_TABLE_HEIGHT_PX,
    LOB_TABLE_ROW_HEIGHTS_PX,
    LOB_TOP5_HEIGHT_PX,
)
from capa_simulation.components.plotly_layout import (
    TRANSPARENT_COLOR,
    add_figure_outer_border,
    add_fixed_table_row,
    add_quarter_boundaries,
    append_layout_items,
    dashboard_title_annotation,
    fixed_row_domains,
)
from capa_simulation.design import tokens
from capa_simulation.services.dashboard import PRODUCTION_DETAIL_DIMENSIONS


def _capacity_color(rate: float, *, secure_threshold: float, warning_threshold: float) -> str:
    """확보율을 확보·경고·부족 상태색으로 바꾼다."""
    if rate > secure_threshold:
        return tokens.STATUS_SECURE
    if rate >= warning_threshold:
        return tokens.STATUS_WARNING
    return tokens.STATUS_SHORTAGE


def build_lob_summary_figures(
    *,
    monthly_density: pd.DataFrame,
    monthly_top5: pd.DataFrame,
    bottleneck_capacity: pd.DataFrame,
    lob_summary: pd.DataFrame,
    month_labels: list[str],
    secure_threshold: float,
    warning_threshold: float,
) -> tuple[go.Figure, go.Figure]:
    """생산계획·Wafer Capa·Bottleneck 요약 Figure 한 쌍을 만든다."""
    month_positions = list(range(len(month_labels)))
    month_position_by_value = dict(
        zip(monthly_density["생산계획년월"], month_positions, strict=True)
    )
    subplot_options = {
        "rows": 3,
        "cols": 1,
        "specs": [[{"type": "table"}], [{"type": "xy"}], [{"type": "xy"}]],
        "shared_xaxes": False,
        "vertical_spacing": 0,
        "row_heights": [
            LOB_TABLE_HEIGHT_PX,
            LOB_CHART_HEIGHT_PX,
            LOB_TOP5_HEIGHT_PX,
        ],
    }
    label_figure = make_subplots(**subplot_options)
    month_figure = make_subplots(**subplot_options)
    label_table_rows = (
        ("구분", tokens.HEADER_BACKGROUND, 21, True),
        ("Density (억Gb)", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer 계획", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer Capa", tokens.SURFACE_CLASSIFICATION, 20, True),
    )
    month_table_rows = (
        ([f"{month}" for month in month_labels], tokens.HEADER_BACKGROUND, 21, True),
        (
            [f"{row['부하량']:,.2f}" for _, row in lob_summary.iterrows()],
            tokens.SURFACE,
            20,
            False,
        ),
        (
            [f"{row['Wafer 부하량'] / 1_000:,.0f}K" for _, row in lob_summary.iterrows()],
            tokens.SURFACE,
            20,
            False,
        ),
        (
            [
                "" if pd.isna(row["Wafer Capa"]) else f"{row['Wafer Capa'] / 1_000:,.0f}K"
                for _, row in lob_summary.iterrows()
            ],
            tokens.SURFACE,
            20,
            False,
        ),
    )
    lob_chart_domain = cast(Any, month_figure.layout.yaxis).domain
    full_table_domain = (float(lob_chart_domain[1]), 1.0)
    lob_table_domains = fixed_row_domains(
        float(full_table_domain[0]),
        float(full_table_domain[1]),
        LOB_TABLE_ROW_HEIGHTS_PX,
    )
    for row_domain, (value, fill_color, font_size, bold) in zip(
        lob_table_domains,
        label_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            label_figure,
            domain=row_domain,
            values=[value],
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    for row_domain, (values, fill_color, font_size, bold) in zip(
        lob_table_domains,
        month_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            month_figure,
            domain=row_domain,
            values=values,
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    if bottleneck_capacity["B/N Capa"].notna().any():
        month_figure.add_trace(
            go.Bar(
                name="B/N 공정",
                x=[month_position_by_value[month] for month in bottleneck_capacity["생산계획년월"]],
                y=bottleneck_capacity["B/N Capa"],
                customdata=bottleneck_capacity[["년월", "확보율", "공정"]],
                text=bottleneck_capacity["확보율"],
                texttemplate="<b>%{text:.0%}</b>",
                textposition="inside",
                insidetextanchor="start",
                textfont={"color": tokens.TEXT, "size": 22, "family": tokens.FONT_FAMILY_NUMERIC},
                marker={
                    "color": [
                        _capacity_color(
                            rate,
                            secure_threshold=secure_threshold,
                            warning_threshold=warning_threshold,
                        )
                        for rate in bottleneck_capacity["확보율"]
                    ],
                    "line": {"color": tokens.LINE, "width": 1.2},
                },
                hovertemplate=(
                    "%{customdata[0]} · B/N %{customdata[2]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[1]:.1%}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )
    month_figure.add_trace(
        go.Scatter(
            name="Density",
            x=month_positions,
            y=monthly_density["부하량"],
            customdata=monthly_density["년월"],
            mode="lines+markers+text",
            text=monthly_density["부하량"],
            texttemplate="<b>%{text:,.2f}</b>",
            textposition="top center",
            textfont={"size": 20, "color": tokens.TEXT, "family": tokens.FONT_FAMILY_NUMERIC},
            line={"color": tokens.LINE, "width": 3},
            marker={
                "color": tokens.SURFACE,
                "size": 8,
                "line": {"color": tokens.LINE, "width": 2.0},
            },
            cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:,.2f} 억Gb<extra></extra>",
        ),
        row=2,
        col=1,
    )
    top5_annotations: list[dict[str, Any]] = []
    if not monthly_top5.empty:
        top5_axis_max = max(float(monthly_top5["B/N Capa"].max()) * 1.8, 1.0)
        wafer_capa_label_y = top5_axis_max * 0.04
        slot_offsets = {1: -0.36, 2: -0.18, 3: 0.0, 4: 0.18, 5: 0.36}
        top5_positions = [
            month_position_by_value[month] + slot_offsets[int(rank)]
            for month, rank in zip(monthly_top5["생산계획년월"], monthly_top5["순위"], strict=True)
        ]
        month_figure.add_trace(
            go.Bar(
                name="B/N Capa Top 5",
                x=top5_positions,
                y=monthly_top5["B/N Capa"],
                width=0.15,
                customdata=monthly_top5[["년월", "공정", "확보율", "Wafer Capa"]],
                marker={
                    "color": [
                        _capacity_color(
                            rate,
                            secure_threshold=secure_threshold,
                            warning_threshold=warning_threshold,
                        )
                        for rate in monthly_top5["확보율"]
                    ],
                    "line": {"color": tokens.LINE, "width": 0.8},
                },
                hovertemplate=(
                    "%{customdata[0]} · %{customdata[1]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[2]:.1%}"
                    "<br>Wafer Capa %{customdata[3]:,.0f} 매"
                    "<extra></extra>"
                ),
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        for x_position, capa, rate in zip(
            top5_positions,
            monthly_top5["B/N Capa"],
            monthly_top5["확보율"],
            strict=True,
        ):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": capa,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"<b>{rate:.0%}</b>",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": 10.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        for x_position, wafer_capa in zip(top5_positions, monthly_top5["Wafer Capa"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": wafer_capa_label_y,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"{wafer_capa / 1_000:,.0f}K",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": -6.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        for x_position, process in zip(top5_positions, monthly_top5["공정"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": 0,
                    "xref": "x2",
                    "yref": "y2",
                    "text": str(process),
                    "textangle": 270,
                    "xanchor": "right",
                    "yanchor": "top",
                    "xshift": 11.0,
                    "yshift": -8.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT_MUTED,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
    common_layout = {
        "height": LOB_FIGURE_HEIGHT_PX,
        "margin": {
            "l": 0,
            "r": 0,
            "t": DASHBOARD_TITLE_HEIGHT_PX,
            "b": LOB_BOTTOM_MARGIN_PX,
        },
        "barmode": "overlay",
        "bargap": 0.16,
        "plot_bgcolor": tokens.SURFACE,
        "paper_bgcolor": tokens.SURFACE,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    label_figure.update_layout(**common_layout, showlegend=False)
    month_figure.update_layout(
        **common_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"color": tokens.TEXT_MUTED, "size": 13},
        },
    )
    append_layout_items(month_figure, annotations=top5_annotations)
    lob_axis_max = max(
        (
            float(value)
            for value in (
                monthly_density["부하량"].max(),
                bottleneck_capacity["B/N Capa"].max(),
            )
            if pd.notna(value)
        ),
        default=1.0,
    )
    lob_axis_max = max(lob_axis_max, 1.0)
    for target_figure in (label_figure, month_figure):
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[0, lob_axis_max * 1.35],
            row=2,
            col=1,
        )
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[
                0,
                top5_axis_max if not monthly_top5.empty else 1.0,
            ],
            row=3,
            col=1,
        )
    for row_number in (2, 3):
        month_figure.update_xaxes(
            tickmode="array",
            tickvals=month_positions,
            ticktext=month_labels,
            showticklabels=False,
            title=None,
            showgrid=False,
            range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
            domain=[0.0, 1.0],
            row=row_number,
            col=1,
        )
        label_figure.update_xaxes(
            showticklabels=False,
            title=None,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            row=row_number,
            col=1,
        )
    panel_bottom = -0.28
    lob_y_domain = month_figure.layout.yaxis.domain
    top5_y_domain = month_figure.layout.yaxis2.domain
    table_y_domain = (lob_table_domains[-1][0], lob_table_domains[0][1])
    append_layout_items(
        label_figure,
        annotations=[
            dashboard_title_annotation("☝️<b>Capa LOB 현황</b>"),
            {
                "x": 0.5,
                "y": (lob_y_domain[0] + lob_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>생산계획 LOB</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": tokens.TEXT_MUTED,
                    "family": tokens.FONT_FAMILY,
                },
            },
            {
                "x": 0.5,
                "y": (top5_y_domain[0] + top5_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>B/N Top 5</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": tokens.TEXT_MUTED,
                    "family": tokens.FONT_FAMILY,
                },
            },
        ],
    )
    horizontal_boundaries = [
        panel_bottom,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    horizontal_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": y_boundary,
            "y1": y_boundary,
            "xref": "paper",
            "yref": "paper",
            "line": {
                "color": tokens.BORDER_STRONG if boundary_index in {1, 2} else tokens.BORDER,
                "width": tokens.OUTER_BORDER_WIDTH_PX if boundary_index in {1, 2} else 0.8,
            },
            "layer": "above" if boundary_index in {1, 2} else "below",
        }
        for boundary_index, y_boundary in enumerate(horizontal_boundaries)
    ]
    append_layout_items(
        label_figure,
        shapes=[
            *[
                {
                    "type": "rect",
                    "x0": 0,
                    "x1": 1,
                    "y0": y0,
                    "y1": y1,
                    "xref": "paper",
                    "yref": "paper",
                    "fillcolor": tokens.SURFACE_CLASSIFICATION,
                    "line": {"width": 0},
                    "layer": "below",
                }
                for y0, y1 in (
                    (horizontal_boundaries[0], horizontal_boundaries[1]),
                    (horizontal_boundaries[1], horizontal_boundaries[2]),
                )
            ],
            *[
                {
                    "type": "line",
                    "x0": x_boundary,
                    "x1": x_boundary,
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": 0.8},
                    "layer": "below",
                }
                for x_boundary in (0.0, 1.0)
            ],
            *horizontal_shapes,
        ],
    )
    append_layout_items(
        month_figure,
        shapes=[
            *[
                {
                    "type": "line",
                    "x0": index / len(month_labels),
                    "x1": index / len(month_labels),
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": 0.8},
                    "layer": "below",
                }
                for index in range(1, len(month_labels))
            ],
            *horizontal_shapes,
        ],
    )
    add_figure_outer_border(
        label_figure,
        y0=panel_bottom,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    add_figure_outer_border(
        month_figure,
        y0=panel_bottom,
        emphasize_left=False,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    lob_row_boundaries = (
        (lob_table_domains[0][0], tokens.OUTER_BORDER_WIDTH_PX, tokens.BORDER_STRONG),
        (lob_table_domains[1][0], 0.8, tokens.BORDER),
        (lob_table_domains[2][0], 0.8, tokens.BORDER),
    )
    lob_row_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": boundary_y,
            "y1": boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": boundary_color, "width": boundary_width},
            "layer": "above",
        }
        for boundary_y, boundary_width, boundary_color in lob_row_boundaries
    ]
    append_layout_items(label_figure, shapes=lob_row_shapes)
    append_layout_items(month_figure, shapes=lob_row_shapes)
    add_quarter_boundaries(month_figure, month_labels, y0=panel_bottom)
    return label_figure, month_figure


def _detail_month_cell_values(displayed_detail: pd.DataFrame, month: str) -> list[str]:
    """한 달의 세부수량 셀 값을 만든다. 데이터에 없는 달은 빈 칸으로 채운다."""
    if month not in displayed_detail.columns:
        return [""] * len(displayed_detail)
    return [
        "" if pd.isna(value) or float(value) == 0 else f"{float(value):,.0f}K"
        for value in displayed_detail[month]
    ]


def build_plan_detail_figures(
    *,
    production_detail: pd.DataFrame,
    month_labels: list[str],
) -> tuple[go.Figure, go.Figure]:
    """제품·Stack별 계획 세부수량 Figure 한 쌍을 만든다."""
    # 조회 범위의 모든 달을 컬럼으로 유지한다. 세부 데이터에 없는 달을 빼면 컬럼 수가
    # 줄어드는데 Figure 폭은 `len(month_labels)` 로 잡으므로, 컬럼 폭이 100px 그리드보다
    # 넓어져 헤더가 뒤로 갈수록 밀린다. 요약표와 월이 세로로 어긋나기도 한다.
    detail_month_columns = list(month_labels)
    displayed_detail = production_detail.copy()
    detail_dimension_values = [
        ["" if pd.isna(value) else str(value) for value in displayed_detail[column]]
        for column in PRODUCTION_DETAIL_DIMENSIONS
    ]
    grouped_dimension_values = [values.copy() for values in detail_dimension_values]
    for dimension_index, values in enumerate(grouped_dimension_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(len(displayed_detail)):
            current_prefix = tuple(
                detail_dimension_values[prefix_index][row_index]
                for prefix_index in range(dimension_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix

    detail_group_indices: list[int] = []
    detail_group_starts: list[int] = []
    previous_product: str | None = None
    group_index = -1
    product_values = detail_dimension_values[0] if detail_dimension_values else []
    for row_index, product in enumerate(product_values):
        if row_index == 0 or product != previous_product:
            group_index += 1
            if row_index > 0:
                detail_group_starts.append(row_index)
        detail_group_indices.append(group_index)
        previous_product = product

    detail_label_row_colors = [
        tokens.SURFACE_CLASSIFICATION
        if group_number % 2 == 0
        else tokens.SURFACE_CLASSIFICATION_GROUP
        for group_number in detail_group_indices
    ]
    detail_month_row_colors = [
        tokens.SURFACE if group_number % 2 == 0 else tokens.SURFACE_SUBTLE
        for group_number in detail_group_indices
    ]
    detail_row_height = 27
    detail_header_height = 36
    detail_figure_height = (
        DASHBOARD_TITLE_HEIGHT_PX
        + detail_header_height
        + max(len(displayed_detail), 1) * detail_row_height
    )
    detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[1.4, 0.6],
            header={
                "values": ["<b>제품</b>", "<b>Stack</b>"],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": 15,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": grouped_dimension_values,
                "align": "center",
                "fill_color": [detail_label_row_colors for _ in PRODUCTION_DETAIL_DIMENSIONS],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": 14,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(detail_month_columns),
            header={
                "values": [f"<b>{month}</b>" for month in detail_month_columns],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": 15,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": [
                    _detail_month_cell_values(displayed_detail, month)
                    for month in detail_month_columns
                ],
                "align": "center",
                "fill_color": [detail_month_row_colors for _ in detail_month_columns],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": 14,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_layout = {
        "height": detail_figure_height,
        "margin": {"l": 0, "r": 0, "t": DASHBOARD_TITLE_HEIGHT_PX, "b": 0},
        "paper_bgcolor": tokens.SURFACE,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    detail_label_figure.update_layout(**detail_layout)
    append_layout_items(
        detail_label_figure,
        annotations=[dashboard_title_annotation("✌️<b>계획 세부수량</b>")],
    )
    detail_month_figure.update_layout(
        **detail_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    detail_table_height = detail_header_height + max(len(displayed_detail), 1) * detail_row_height
    detail_header_boundary_y = 1 - detail_header_height / detail_table_height
    add_figure_outer_border(detail_label_figure, emphasize_bottom=True)
    add_figure_outer_border(
        detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    detail_header_shape = {
        "type": "line",
        "x0": 0,
        "x1": 1,
        "y0": detail_header_boundary_y,
        "y1": detail_header_boundary_y,
        "xref": "paper",
        "yref": "paper",
        "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
        "layer": "above",
    }
    append_layout_items(
        detail_label_figure,
        shapes=[
            detail_header_shape,
            {
                "type": "line",
                "x0": 1.4 / 2.0,
                "x1": 1.4 / 2.0,
                "y0": 0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER, "width": 0.8},
                "layer": "above",
            },
        ],
    )
    append_layout_items(
        detail_month_figure,
        shapes=[
            detail_header_shape,
            *[
                {
                    "type": "line",
                    "x0": month_index / len(detail_month_columns),
                    "x1": month_index / len(detail_month_columns),
                    "y0": 0,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": 0.8},
                    "layer": "above",
                }
                for month_index in range(1, len(detail_month_columns))
            ],
        ],
    )
    add_quarter_boundaries(detail_month_figure, detail_month_columns)
    detail_group_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": 1
            - (detail_header_height + group_start * detail_row_height) / detail_table_height,
            "y1": 1
            - (detail_header_height + group_start * detail_row_height) / detail_table_height,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": 1.4},
            "layer": "above",
        }
        for group_start in detail_group_starts
    ]
    append_layout_items(detail_label_figure, shapes=detail_group_shapes)
    append_layout_items(detail_month_figure, shapes=detail_group_shapes)
    return detail_label_figure, detail_month_figure


def build_bottleneck_detail_figures(
    *,
    monthly_density: pd.DataFrame,
    monthly_top10_details: pd.DataFrame,
    month_labels: list[str],
) -> tuple[go.Figure, go.Figure]:
    """월별 B/N 상위 10개 공정 상세 Figure 한 쌍을 만든다."""
    bottleneck_detail_ranks = list(range(1, 11))
    bottleneck_detail_labels = "확보율<br>공정명<br>가용대수<br>필요대수<br>Wafer Capa"
    bottleneck_detail_lookup = {
        (int(row["생산계획년월"]), int(row["순위"])): row
        for _, row in monthly_top10_details.iterrows()
    }

    def format_equipment_count(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return ""
        return f"{float(cast(Any, value)):,.1f}대"

    def format_process_name(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return ""
        process = str(value)
        width_units = sum(
            1.0 if unicodedata.east_asian_width(character) in {"F", "W"} else 0.6
            for character in process
        )
        process_font_size = max(8, min(13, round(88 / max(width_units, 1.0))))
        return f'<span style="font-size:{process_font_size}px">{html.escape(process)}</span>'

    def format_bottleneck_detail(month: int, rank: int) -> str:
        row = bottleneck_detail_lookup.get((month, rank))
        if row is None:
            return "<br><br><br><br>"
        rate = "" if pd.isna(row["확보율"]) else f"{float(row['확보율']):.1%}"
        process = format_process_name(row["공정"])
        available = format_equipment_count(row["가용대수"])
        required = format_equipment_count(row["소요대수"])
        wafer_capa = (
            "" if pd.isna(row["Wafer Capa"]) else f"{float(row['Wafer Capa']) / 1_000:,.0f}K"
        )
        return "<br>".join((rate, process, available, required, wafer_capa))

    bottleneck_detail_row_height = 110
    bottleneck_detail_header_height = 36
    bottleneck_detail_figure_height = (
        DASHBOARD_TITLE_HEIGHT_PX
        + bottleneck_detail_header_height
        + len(bottleneck_detail_ranks) * bottleneck_detail_row_height
    )
    bottleneck_detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[0.65, 1.35],
            header={
                "values": ["<b>B/N</b>", "<b>구분</b>"],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": 15,
                    "family": tokens.FONT_FAMILY,
                },
                "height": bottleneck_detail_header_height,
            },
            cells={
                "values": [
                    [f"<br><br>{rank}<br><br>" for rank in bottleneck_detail_ranks],
                    [bottleneck_detail_labels] * len(bottleneck_detail_ranks),
                ],
                "align": "center",
                "fill_color": tokens.SURFACE_CLASSIFICATION,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": [20, 13],
                    "family": tokens.FONT_FAMILY,
                },
                "height": bottleneck_detail_row_height,
            },
        )
    )
    bottleneck_detail_month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(month_labels),
            header={
                "values": [f"<b>{month}</b>" for month in month_labels],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": 15,
                    "family": tokens.FONT_FAMILY,
                },
                "height": bottleneck_detail_header_height,
            },
            cells={
                "values": [
                    [format_bottleneck_detail(int(month), rank) for rank in bottleneck_detail_ranks]
                    for month in monthly_density["생산계획년월"]
                ],
                "align": "center",
                "fill_color": tokens.SURFACE,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": 13,
                    "family": tokens.FONT_FAMILY,
                },
                "height": bottleneck_detail_row_height,
            },
        )
    )
    bottleneck_detail_layout = {
        "height": bottleneck_detail_figure_height,
        "margin": {
            "l": 0,
            "r": 0,
            "t": DASHBOARD_TITLE_HEIGHT_PX,
            "b": 0,
        },
        "paper_bgcolor": tokens.SURFACE,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    bottleneck_detail_label_figure.update_layout(**bottleneck_detail_layout)
    append_layout_items(
        bottleneck_detail_label_figure,
        annotations=[dashboard_title_annotation("👌<b>상세 B/N 공정</b>")],
    )
    bottleneck_detail_month_figure.update_layout(
        **bottleneck_detail_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    bottleneck_detail_table_height = (
        bottleneck_detail_header_height
        + len(bottleneck_detail_ranks) * bottleneck_detail_row_height
    )
    bottleneck_detail_boundaries = [
        1 - bottleneck_detail_header_height / bottleneck_detail_table_height,
        *[
            1
            - (bottleneck_detail_header_height + rank_index * bottleneck_detail_row_height)
            / bottleneck_detail_table_height
            for rank_index in range(1, len(bottleneck_detail_ranks))
        ],
    ]
    add_figure_outer_border(
        bottleneck_detail_label_figure,
        emphasize_bottom=True,
    )
    add_figure_outer_border(
        bottleneck_detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    bottleneck_boundary_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": boundary_y,
            "y1": boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for boundary_y in bottleneck_detail_boundaries
    ]
    append_layout_items(bottleneck_detail_label_figure, shapes=bottleneck_boundary_shapes)
    append_layout_items(bottleneck_detail_month_figure, shapes=bottleneck_boundary_shapes)
    add_quarter_boundaries(bottleneck_detail_month_figure, month_labels)
    return bottleneck_detail_label_figure, bottleneck_detail_month_figure
