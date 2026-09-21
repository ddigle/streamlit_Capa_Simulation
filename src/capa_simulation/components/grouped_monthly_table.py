# Purpose: 부분합과 계층 그룹을 포함한 고정 분류·스크롤 월별 Plotly 표를 생성한다.

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.monthly_table_base import (
    HEADER_HEIGHT_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
    add_classification_boundaries,
    add_header_rule,
    add_month_boundaries,
    add_outer_border,
    build_split_table_figures,
    classification_cell_text,
    classification_widths,
    header_boundary_ratio,
    header_label,
    month_label,
    render_split_scroll_table,
    restore_cell_text,
    table_height_px,
)
from capa_simulation.components.plotly_layout import append_layout_items, flush_layout_items
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

# 기존 33px에서 약 1/8 축소한 데이터 행 높이다.

_RowType = Literal["detail", "product_total", "production_total", "grand_total"]


@dataclass(frozen=True)
class _DisplayRows:
    classification_values: list[list[str]]
    month_values: list[list[float]]
    row_types: list[_RowType]
    product_group_indices: list[int]
    production_group_indices: list[int]
    product_total_rows: list[int]
    production_total_rows: list[int]
    grand_total_row: int


def _grouped_values(
    data: pd.DataFrame,
    columns: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[list[list[str]], list[int], list[int]]:
    column_value_labels = value_labels or {}
    dimension_values = [
        [classification_cell_text(value, column_value_labels.get(column)) for value in data[column]]
        for column in columns
    ]
    displayed_values = [values.copy() for values in dimension_values]
    for dimension_index, values in enumerate(displayed_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(len(data)):
            current_prefix = tuple(
                dimension_values[prefix_index][row_index]
                for prefix_index in range(dimension_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix

    group_depth = columns.index("제품정보") if "제품정보" in columns else 0
    product_group_indices: list[int] = []
    previous_product_group: tuple[str, ...] | None = None
    product_group_index = -1
    for row_index in range(len(data)):
        current_product_group = tuple(
            dimension_values[column_index][row_index] for column_index in range(group_depth + 1)
        )
        if row_index == 0 or current_product_group != previous_product_group:
            product_group_index += 1
        product_group_indices.append(product_group_index)
        previous_product_group = current_product_group

    production_group_indices: list[int] = []
    previous_production_group: str | None = None
    production_group_index = -1
    for row_index, current_production_group in enumerate(dimension_values[0]):
        if row_index == 0 or current_production_group != previous_production_group:
            production_group_index += 1
        production_group_indices.append(production_group_index)
        previous_production_group = current_production_group

    return displayed_values, product_group_indices, production_group_indices


def _build_display_rows(
    data: pd.DataFrame,
    classification_columns: list[str],
    month_columns: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> _DisplayRows:
    column_value_labels = value_labels or {}
    grouped_values, product_group_indices, production_group_indices = _grouped_values(
        data, classification_columns, column_value_labels
    )
    product_column_index = (
        classification_columns.index("제품정보") if "제품정보" in classification_columns else 0
    )
    numeric_months = data[month_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    classification_values: list[list[str]] = [[] for _ in classification_columns]
    month_values: list[list[float]] = []
    row_types: list[_RowType] = []
    displayed_product_indices: list[int] = []
    displayed_production_indices: list[int] = []
    product_total_rows: list[int] = []
    production_total_rows: list[int] = []
    product_totals = [0.0 for _ in month_columns]
    production_totals = [0.0 for _ in month_columns]
    grand_totals = [float(value) for value in numeric_months.sum(axis=0).tolist()]

    def append_row(
        labels: list[str],
        values: list[float],
        row_type: _RowType,
        product_group_index: int,
        production_group_index: int,
    ) -> None:
        for column_index, label in enumerate(labels):
            classification_values[column_index].append(label)
        month_values.append(values.copy())
        row_types.append(row_type)
        displayed_product_indices.append(product_group_index)
        displayed_production_indices.append(production_group_index)

    grand_total_labels = ["" for _ in classification_columns]
    grand_total_labels[0] = "전체\u00a0합계"
    append_row(grand_total_labels, grand_totals, "grand_total", -1, -1)

    for row_index in range(len(data)):
        current_month_values = [float(value) for value in numeric_months.iloc[row_index].tolist()]
        append_row(
            [values[row_index] for values in grouped_values],
            current_month_values,
            "detail",
            product_group_indices[row_index],
            production_group_indices[row_index],
        )
        for month_index, value in enumerate(current_month_values):
            product_totals[month_index] += value
            production_totals[month_index] += value

        product_ends = (
            row_index == len(data) - 1
            or product_group_indices[row_index + 1] != product_group_indices[row_index]
        )
        production_ends = (
            row_index == len(data) - 1
            or production_group_indices[row_index + 1] != production_group_indices[row_index]
        )
        if product_ends:
            subtotal_labels = ["" for _ in classification_columns]
            subtotal_labels[product_column_index] = "Total"
            append_row(
                subtotal_labels,
                product_totals,
                "product_total",
                product_group_indices[row_index],
                production_group_indices[row_index],
            )
            product_total_rows.append(len(row_types) - 1)
            product_totals = [0.0 for _ in month_columns]

        if production_ends:
            production_label = classification_cell_text(
                data.iloc[row_index][classification_columns[0]],
                column_value_labels.get(classification_columns[0]),
            )
            subtotal_labels = ["" for _ in classification_columns]
            subtotal_labels[0] = f"{production_label}\u00a0Total"
            append_row(
                subtotal_labels,
                production_totals,
                "production_total",
                product_group_indices[row_index],
                production_group_indices[row_index],
            )
            production_total_rows.append(len(row_types) - 1)
            production_totals = [0.0 for _ in month_columns]

    return _DisplayRows(
        classification_values=classification_values,
        month_values=month_values,
        row_types=row_types,
        product_group_indices=displayed_product_indices,
        production_group_indices=displayed_production_indices,
        product_total_rows=product_total_rows,
        production_total_rows=production_total_rows,
        grand_total_row=0,
    )


def _add_table_grid(
    *,
    label_figure: go.Figure,
    month_figure: go.Figure,
    classification_widths: list[int],
    month_columns: list[str],
    product_total_rows: list[int],
    production_total_rows: list[int],
    grand_total_row: int,
    row_count: int,
) -> None:
    table_height = table_height_px(row_count)
    add_outer_border(label_figure, include_left=True)
    add_outer_border(month_figure, include_left=False)
    for target_figure in (label_figure, month_figure):
        add_header_rule(target_figure, boundary_y=header_boundary_ratio(row_count))

    total_classification_width = sum(classification_widths)
    # 생산 소계 가로선이 시작하는 지점이기도 하다. 아래에서 다시 쓴다.
    production_boundary_x = classification_widths[0] / total_classification_width
    add_classification_boundaries(label_figure, classification_widths)

    add_month_boundaries(month_figure, month_columns)

    # `add_shape` 는 부를 때마다 지금까지 쌓인 shape 전부를 다시 검증한다. 행마다 부르면
    # 행 수 제곱으로 늘어 STEP 별 대당 Capa(1,140행)는 300초 안에 끝나지 않았다. 행 루프는
    # dict 를 모아 두었다가 한 번에 주입한다. 순서는 그대로다(테두리·머리선·경계 → 행 경계).
    def _rule(x0: float, y: float, width: float) -> dict[str, Any]:
        return {
            "type": "line",
            "x0": x0,
            "x1": 1,
            "y0": y,
            "y1": y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": width},
            "layer": "above",
        }

    def _boundary_y(total_row: int) -> float:
        return 1 - (HEADER_HEIGHT_PX + (total_row + 1) * ROW_HEIGHT_PX) / table_height

    label_shapes: list[dict[str, Any]] = []
    month_shapes: list[dict[str, Any]] = []
    for total_row in product_total_rows:
        label_shapes.append(_rule(production_boundary_x, _boundary_y(total_row), 1.0))
        month_shapes.append(_rule(0, _boundary_y(total_row), 1.0))
    for total_row in production_total_rows:
        label_shapes.append(_rule(0, _boundary_y(total_row), 1.4))
        month_shapes.append(_rule(0, _boundary_y(total_row), 1.4))
    label_shapes.append(_rule(0, _boundary_y(grand_total_row), OUTER_BORDER_WIDTH_PX))
    month_shapes.append(_rule(0, _boundary_y(grand_total_row), OUTER_BORDER_WIDTH_PX))
    append_layout_items(label_figure, shapes=label_shapes)
    append_layout_items(month_figure, shapes=month_shapes)
    flush_layout_items(label_figure, month_figure)


def _classification_fill_colors(
    display: _DisplayRows,
    classification_columns: list[str],
) -> list[list[str]]:
    colors: list[list[str]] = []
    for column_index in range(len(classification_columns)):
        column_colors: list[str] = []
        for row_index, row_type in enumerate(display.row_types):
            if row_type == "product_total" and column_index == 0:
                color = (
                    tokens.SURFACE_CLASSIFICATION
                    if display.production_group_indices[row_index] % 2 == 0
                    else tokens.SURFACE_CLASSIFICATION_GROUP
                )
            elif row_type == "product_total":
                color = tokens.CLASSIFICATION_PRODUCT_TOTAL
            elif row_type == "production_total":
                color = tokens.CLASSIFICATION_PRODUCTION_TOTAL
            elif row_type == "grand_total":
                color = tokens.CLASSIFICATION_GRAND_TOTAL
            elif column_index == 0:
                color = (
                    tokens.SURFACE_CLASSIFICATION
                    if display.production_group_indices[row_index] % 2 == 0
                    else tokens.SURFACE_CLASSIFICATION_GROUP
                )
            else:
                color = (
                    tokens.SURFACE_CLASSIFICATION
                    if display.product_group_indices[row_index] % 2 == 0
                    else tokens.SURFACE_CLASSIFICATION_GROUP
                )
            column_colors.append(color)
        colors.append(column_colors)
    return colors


def _month_fill_colors(display: _DisplayRows) -> list[str]:
    colors: list[str] = []
    for row_index, row_type in enumerate(display.row_types):
        if row_type == "product_total":
            color = tokens.SURFACE_PRODUCT_TOTAL
        elif row_type == "production_total":
            color = tokens.SURFACE_PRODUCTION_TOTAL
        elif row_type == "grand_total":
            color = tokens.SURFACE_GRAND_TOTAL
        else:
            color = (
                tokens.SURFACE
                if display.product_group_indices[row_index] % 2 == 0
                else tokens.SURFACE_SUBTLE
            )
        colors.append(color)
    return colors


def _formatted_month_values(
    display: _DisplayRows,
    month_count: int,
    decimal_places: int,
) -> list[list[str]]:
    value_format = f",.{decimal_places}f"
    formatted_columns: list[list[str]] = []
    for month_index in range(month_count):
        formatted_month: list[str] = []
        for row_index, _row_type in enumerate(display.row_types):
            value = display.month_values[row_index][month_index]
            text = "" if value == 0 else format(value, value_format)
            formatted_month.append(text)
        formatted_columns.append(formatted_month)
    return formatted_columns


def build_grouped_monthly_export(
    data: pd.DataFrame,
    *,
    classification_columns: list[str],
    column_labels: Mapping[str, str],
) -> pd.DataFrame:
    """Build a CSV-friendly table that matches the grouped monthly display."""
    month_columns = [column for column in data.columns if column not in classification_columns]
    output_columns = [
        *[column_labels.get(column, column) for column in classification_columns],
        *[month_label(month) for month in month_columns],
    ]
    if data.empty or not month_columns:
        return pd.DataFrame(columns=output_columns)

    display = _build_display_rows(data, classification_columns, month_columns)
    output: dict[str, list[object]] = {
        # 화면은 줄바꿈을 막으려고 U+00A0 을 쓰지만 CSV 는 진짜 공백이어야 한다. 그대로 두면
        # PKG PLAN CSV 의 제품명과 글자가 달라 Excel VLOOKUP·필터가 조용히 어긋난다.
        column_labels.get(column, column): [
            restore_cell_text(value) for value in display.classification_values[column_index]
        ]
        for column_index, column in enumerate(classification_columns)
    }
    for month_index, month in enumerate(month_columns):
        output[month_label(month)] = [
            float("nan") if value == 0 else value
            for value in (row[month_index] for row in display.month_values)
        ]
    return pd.DataFrame(output, columns=output_columns)


def render_grouped_monthly_table(
    data: pd.DataFrame,
    *,
    classification_columns: list[str],
    column_labels: Mapping[str, str],
    decimal_places: int,
    key: str,
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
    owner_tab: OpenTab | None = None,
) -> None:
    """Render fixed grouped classifications and horizontally scrolling month columns.

    `owner_tab` 은 이 표가 놓인 탭이다. 닫힌 탭에서는 그리지 않는다. 이유는
    `render_split_scroll_table` 의 설명을 보라.
    """
    if data.empty:
        st.info("표시할 환산 데이터가 없습니다.")
        return
    month_columns = [column for column in data.columns if column not in classification_columns]
    if not month_columns:
        st.info("표시할 월별 환산 데이터가 없습니다.")
        return

    # 닫힌 탭이면 그림 준비는 여기서 접는다. 아래 `render_split_scroll_table` 도 막지만 그 전에
    # 소계·격자를 만들고 버리고 있었다. 이 함수는 앞에서 위젯을 그리지 않으므로 상태 유실이 없다.
    if tab_is_hidden(owner_tab):
        return
    display = _build_display_rows(data, classification_columns, month_columns, value_labels)
    column_widths = classification_widths(
        display.classification_values,
        classification_columns,
        column_labels,
    )
    classification_fill_colors = _classification_fill_colors(display, classification_columns)
    month_row_colors = _month_fill_colors(display)
    month_values = _formatted_month_values(display, len(month_columns), decimal_places)
    label_figure, month_figure = build_split_table_figures(
        classification_headers=[
            header_label(column_labels.get(column, column)) for column in classification_columns
        ],
        classification_values=display.classification_values,
        classification_fill_colors=classification_fill_colors,
        column_widths=column_widths,
        month_headers=[header_label(month_label(month)) for month in month_columns],
        month_values=month_values,
        month_row_colors=month_row_colors,
        row_count=len(display.row_types),
    )
    _add_table_grid(
        label_figure=label_figure,
        month_figure=month_figure,
        classification_widths=column_widths,
        month_columns=month_columns,
        product_total_rows=display.product_total_rows,
        production_total_rows=display.production_total_rows,
        grand_total_row=display.grand_total_row,
        row_count=len(display.row_types),
    )

    render_split_scroll_table(
        key=key,
        label_figure=label_figure,
        month_figure=month_figure,
        classification_widths=column_widths,
        month_count=len(month_columns),
        owner_tab=owner_tab,
    )
