# Purpose: Plotly table with grouped classifications and horizontally scrolling months.

"""Plotly table with grouped classifications and horizontally scrolling months."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import accumulate
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.monthly_table_base import (
    CANVAS_COLOR,
    CLASSIFICATION_COLOR,
    CLASSIFICATION_GROUP_COLOR,
    CLASSIFICATION_HORIZONTAL_PADDING_PX,
    CLASSIFICATION_MAX_WIDTH_PX,
    CLASSIFICATION_MIN_WIDTH_PX,
    CLASSIFICATION_TEXT_UNIT_PX,
    GROUP_BORDER_COLOR,
    GROUP_SURFACE_COLOR,
    HEADER_COLOR,
    HEADER_HEIGHT_PX,
    MONTH_COLUMN_WIDTH_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
    SURFACE_COLOR,
    TEXT_COLOR,
    TRANSPARENT_COLOR,
    add_classification_boundaries,
    add_header_rule,
    add_month_boundaries,
    add_outer_border,
    display_value_text,
    header_boundary_ratio,
    header_label,
    month_label,
    render_split_scroll_table,
    table_height_px,
    text_width_units,
)
from capa_simulation.components.plotly_layout import append_layout_items, flush_layout_items
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

_ValueFormat = Literal["number", "percent"]


@dataclass(frozen=True)
class _HierarchicalDisplay:
    classification_values: list[list[str]]
    top_group_indices: list[int]
    group_boundaries: list[tuple[int, int]]


def _classification_widths(
    values: list[list[str]],
    columns: list[str],
    labels: Mapping[str, str],
) -> list[int]:
    widths: list[int] = []
    for column_index, column in enumerate(columns):
        texts = [labels.get(column, column), *values[column_index]]
        max_units = max((text_width_units(text) for text in texts), default=4.0)
        widths.append(
            max(
                CLASSIFICATION_MIN_WIDTH_PX,
                min(
                    CLASSIFICATION_MAX_WIDTH_PX,
                    round(
                        max_units * CLASSIFICATION_TEXT_UNIT_PX
                        + CLASSIFICATION_HORIZONTAL_PADDING_PX
                    ),
                ),
            )
        )
    return widths


def _build_hierarchical_display(
    data: pd.DataFrame,
    classification_columns: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> _HierarchicalDisplay:
    labels = value_labels or {}
    raw_values = [
        [
            display_value_text(value, labels.get(column)).replace(" ", "\u00a0")
            for value in data[column]
        ]
        for column in classification_columns
    ]
    displayed_values = [values.copy() for values in raw_values]
    for column_index, values in enumerate(displayed_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(len(data)):
            current_prefix = tuple(
                raw_values[prefix_index][row_index] for prefix_index in range(column_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix

    top_group_indices: list[int] = []
    top_group_index = -1
    previous_top_value: str | None = None
    for row_index, top_value in enumerate(raw_values[0]):
        if row_index == 0 or top_value != previous_top_value:
            top_group_index += 1
        top_group_indices.append(top_group_index)
        previous_top_value = top_value

    group_boundaries: list[tuple[int, int]] = []
    for row_index in range(1, len(data)):
        changed_column = next(
            (
                column_index
                for column_index, values in enumerate(raw_values)
                if values[row_index] != values[row_index - 1]
            ),
            len(classification_columns) - 1,
        )
        group_boundaries.append((row_index, changed_column))

    return _HierarchicalDisplay(
        classification_values=displayed_values,
        top_group_indices=top_group_indices,
        group_boundaries=group_boundaries,
    )


def _formatted_month_values(
    data: pd.DataFrame,
    month_columns: list[str],
    decimal_places: int,
    value_format: _ValueFormat = "number",
) -> list[list[str]]:
    format_spec = f".{decimal_places}%" if value_format == "percent" else f",.{decimal_places}f"
    numeric = data[month_columns].apply(pd.to_numeric, errors="coerce")
    return [
        [
            "" if pd.isna(value) or float(value) == 0 else format(float(value), format_spec)
            for value in numeric[month]
        ]
        for month in month_columns
    ]


def build_hierarchical_monthly_export(
    data: pd.DataFrame,
    *,
    classification_columns: list[str],
    column_labels: Mapping[str, str],
    decimal_places: int,
    value_format: _ValueFormat = "number",
) -> pd.DataFrame:
    """Build a CSV-friendly table matching the hierarchical display."""
    month_columns = [column for column in data.columns if column not in classification_columns]
    output_columns = [
        *[column_labels.get(column, column) for column in classification_columns],
        *[month_label(month) for month in month_columns],
    ]
    if data.empty or not month_columns:
        return pd.DataFrame(columns=output_columns)

    display = _build_hierarchical_display(data, classification_columns)
    output: dict[str, list[object]] = {
        column_labels.get(column, column): [
            value.replace("\u00a0", " ") for value in display.classification_values[column_index]
        ]
        for column_index, column in enumerate(classification_columns)
    }
    numeric = data[month_columns].apply(pd.to_numeric, errors="coerce")
    for month in month_columns:
        if value_format == "percent":
            output[month_label(month)] = [
                ""
                if pd.isna(value) or float(value) == 0
                else format(float(value), f".{decimal_places}%")
                for value in numeric[month]
            ]
        else:
            output[month_label(month)] = [
                float("nan") if pd.isna(value) or float(value) == 0 else float(value)
                for value in numeric[month]
            ]
    return pd.DataFrame(output, columns=output_columns)


def _add_table_grid(
    *,
    label_figure: go.Figure,
    month_figure: go.Figure,
    display: _HierarchicalDisplay,
    classification_widths: list[int],
    month_columns: list[str],
    row_count: int,
) -> None:
    table_height = table_height_px(row_count)
    add_outer_border(label_figure, include_left=True)
    add_outer_border(month_figure, include_left=False)
    for figure in (label_figure, month_figure):
        add_header_rule(figure, boundary_y=header_boundary_ratio(row_count))

    total_classification_width = sum(classification_widths)
    add_classification_boundaries(label_figure, classification_widths)

    add_month_boundaries(month_figure, month_columns)

    cumulative_widths = [0, *accumulate(classification_widths)]
    # `add_shape` 는 부를 때마다 지금까지 쌓인 shape 전부를 다시 검증한다. 행마다 부르면
    # 행 수 제곱으로 늘어 STEP 별 대당 Capa(1,140행)는 300초 안에 끝나지 않았다. 행 루프는
    # dict 를 모아 두었다가 한 번에 주입한다. 순서는 그대로다(테두리·머리선·경계 → 행 경계).
    label_shapes: list[dict[str, Any]] = []
    month_shapes: list[dict[str, Any]] = []
    for row_index, changed_column in display.group_boundaries:
        boundary_y = 1 - (HEADER_HEIGHT_PX + row_index * ROW_HEIGHT_PX) / table_height
        label_start_x = cumulative_widths[changed_column] / total_classification_width
        # 최상위 그룹선은 바깥 테두리와 같은 굵기로 시작해 계층이 깊어질수록 가늘어진다.
        boundary_width = max(1.0, OUTER_BORDER_WIDTH_PX - changed_column * 0.16)
        line = {"color": GROUP_BORDER_COLOR, "width": boundary_width}
        label_shapes.append(
            {
                "type": "line",
                "x0": label_start_x,
                "x1": 1,
                "y0": boundary_y,
                "y1": boundary_y,
                "xref": "paper",
                "yref": "paper",
                "line": line,
                "layer": "above",
            }
        )
        month_shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": boundary_y,
                "y1": boundary_y,
                "xref": "paper",
                "yref": "paper",
                "line": line,
                "layer": "above",
            }
        )
    append_layout_items(label_figure, shapes=label_shapes)
    append_layout_items(month_figure, shapes=month_shapes)
    flush_layout_items(label_figure, month_figure)


def render_hierarchical_monthly_table(
    data: pd.DataFrame,
    *,
    classification_columns: list[str],
    column_labels: Mapping[str, str],
    decimal_places: int,
    key: str,
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
    value_format: _ValueFormat = "number",
    page_size: int | None = None,
    owner_tab: OpenTab | None = None,
) -> None:
    """Render a grouped fixed-label table with scrolling month columns.

    `owner_tab` 은 이 표가 놓인 탭이다. 닫힌 탭에서는 그리지 않는다. 이유는
    `render_split_scroll_table` 의 설명을 보라.
    """
    if data.empty:
        st.info("표시할 월별 데이터가 없습니다.")
        return
    month_columns = [column for column in data.columns if column not in classification_columns]
    if not month_columns:
        st.info("표시할 월별 데이터가 없습니다.")
        return

    if page_size is not None and page_size > 0 and len(data) > page_size:
        total_rows = len(data)
        page_count = (total_rows + page_size - 1) // page_size
        page_index = st.selectbox(
            "표시 범위",
            list(range(page_count)),
            format_func=lambda index: (
                f"{index * page_size + 1:,}–{min((index + 1) * page_size, total_rows):,}행"
            ),
            key=f"{key}_page",
            width=180,
        )
        start_row = page_index * page_size
        data = data.iloc[start_row : start_row + page_size].copy()
        st.caption(f"전체 {total_rows:,}행 · {page_index + 1:,}/{page_count:,} 페이지")

    # 위젯(표시 범위)은 그렸으니 상태가 유지된다. 닫힌 탭이면 그림 준비는 여기서 접는다 —
    # 아래 `render_split_scroll_table` 도 막지만 그 전에 격자 1~2초를 만들고 버리고 있었다.
    if tab_is_hidden(owner_tab):
        return
    display = _build_hierarchical_display(data, classification_columns, value_labels)
    classification_widths = _classification_widths(
        display.classification_values,
        classification_columns,
        column_labels,
    )
    classification_colors = [
        [
            CLASSIFICATION_COLOR if group_index % 2 == 0 else CLASSIFICATION_GROUP_COLOR
            for group_index in display.top_group_indices
        ]
        for _column in classification_columns
    ]
    month_row_colors = [
        SURFACE_COLOR if group_index % 2 == 0 else GROUP_SURFACE_COLOR
        for group_index in display.top_group_indices
    ]
    month_values = _formatted_month_values(
        data,
        month_columns,
        decimal_places,
        value_format,
    )
    figure_height = HEADER_HEIGHT_PX + max(len(data), 1) * ROW_HEIGHT_PX
    common_layout = {
        "height": figure_height,
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": CANVAS_COLOR,
        "font": {"color": TEXT_COLOR, "family": tokens.FONT_FAMILY},
    }
    label_figure = go.Figure(
        go.Table(
            columnwidth=classification_widths,
            header={
                "values": [
                    header_label(column_labels.get(column, column))
                    for column in classification_columns
                ],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": TRANSPARENT_COLOR,
                "font": {"color": TEXT_COLOR, "size": 14, "family": tokens.FONT_FAMILY},
                "height": HEADER_HEIGHT_PX,
            },
            cells={
                "values": display.classification_values,
                "align": "center",
                "fill_color": classification_colors,
                "line_color": TRANSPARENT_COLOR,
                "font": {"color": TEXT_COLOR, "size": 13, "family": tokens.FONT_FAMILY},
                "height": ROW_HEIGHT_PX,
            },
        )
    )
    month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(month_columns),
            header={
                "values": [header_label(month_label(month)) for month in month_columns],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": TRANSPARENT_COLOR,
                "font": {"color": TEXT_COLOR, "size": 14, "family": tokens.FONT_FAMILY},
                "height": HEADER_HEIGHT_PX,
            },
            cells={
                "values": month_values,
                "align": "center",
                "fill_color": [month_row_colors for _month in month_columns],
                "line_color": TRANSPARENT_COLOR,
                "font": {"color": TEXT_COLOR, "size": 13, "family": tokens.FONT_FAMILY},
                "height": ROW_HEIGHT_PX,
            },
        )
    )
    label_figure.update_layout(**common_layout)
    month_figure_width = len(month_columns) * MONTH_COLUMN_WIDTH_PX
    month_figure.update_layout(**common_layout, width=month_figure_width, autosize=False)
    _add_table_grid(
        label_figure=label_figure,
        month_figure=month_figure,
        display=display,
        classification_widths=classification_widths,
        month_columns=month_columns,
        row_count=len(data),
    )

    render_split_scroll_table(
        key=key,
        label_figure=label_figure,
        month_figure=month_figure,
        classification_widths=classification_widths,
        month_count=len(month_columns),
        owner_tab=owner_tab,
    )
