# Purpose: Plotly table with grouped classifications and horizontally scrolling months.

"""Plotly table with grouped classifications and horizontally scrolling months."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import accumulate
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.monthly_table_base import (
    HEADER_HEIGHT_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
    add_table_frame,
    build_split_table_figures,
    classification_cell_text,
    classification_widths,
    header_label,
    month_label,
    render_split_scroll_table,
    restore_cell_text,
    table_height_px,
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


def _build_hierarchical_display(
    data: pd.DataFrame,
    classification_columns: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> _HierarchicalDisplay:
    labels = value_labels or {}
    raw_values = [
        [classification_cell_text(value, labels.get(column)) for value in data[column]]
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
            restore_cell_text(value) for value in display.classification_values[column_index]
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
    add_table_frame(
        label_figure,
        month_figure,
        classification_widths=classification_widths,
        month_columns=month_columns,
        row_count=row_count,
    )

    total_classification_width = sum(classification_widths)
    cumulative_widths = [0, *accumulate(classification_widths)]
    # `add_shape` 는 부를 때마다 지금까지 쌓인 shape 전부를 다시 검증한다. 행마다 부르면
    # 행 수 제곱으로 늘어 STEP 별 대당 Capa(1,140행)는 300초 안에 끝나지 않는다. 그래서 위의
    # 격자 도우미와 아래 행 루프가 모두 dict 를 누적함에 모으고 끝에서 한 번에 주입한다.
    # 순서는 그대로다(테두리·머리선·분류·월 경계 → 행 경계).
    label_shapes: list[dict[str, Any]] = []
    month_shapes: list[dict[str, Any]] = []
    for row_index, changed_column in display.group_boundaries:
        boundary_y = 1 - (HEADER_HEIGHT_PX + row_index * ROW_HEIGHT_PX) / table_height
        label_start_x = cumulative_widths[changed_column] / total_classification_width
        # 최상위 그룹선은 바깥 테두리와 같은 굵기로 시작해 계층이 깊어질수록 가늘어진다.
        boundary_width = max(1.0, OUTER_BORDER_WIDTH_PX - changed_column * 0.16)
        line = {"color": tokens.BORDER_STRONG, "width": boundary_width}
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


def _refit_range_on_new_total(page_key: str, total_rows: int, page_count: int) -> None:
    """행 수가 바뀐 회차에 「표시 범위」 칸 값을 새 쪽 수 안으로 다시 적는다.

    칸의 값 글에 전체 행 수가 들어, 필터로 행 수가 바뀌면 브라우저가 쥔 옛 글이 새 보기에 없다.
    칸을 그대로 두면 옛 행 수가 적힌 글이 칸에 남는 회차가 생긴다(샘플 관측). 칸 값을 적으면 새 글이
    함께 간다. 고른 차례는 그대로 두고 새 쪽 수를 넘을 때만 끝 범위로 자른다.

    앞 회차가 새 글을 보내기 전에 떠난 다음 회차는 옛 글을 싣고 온다 — 새 보기에 없는 글은 풀리지
    않은 글자로 남고 위젯이 첫 범위로 되돌린다(사이드바 필터 뒤, 샘플 관측). 그때는 마지막으로 그린
    차례(`_shown`, 위젯 뒤에 적는다)로 다시 적는다.
    """
    shown_total, shown_index = st.session_state.get(f"{page_key}_shown", (None, 0))
    picked = st.session_state.get(page_key, 0)
    if shown_total == total_rows and isinstance(picked, int):
        return
    if not isinstance(picked, int):
        picked = shown_index
    st.session_state[page_key] = min(picked, page_count - 1)


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
    page_slot: DeltaGenerator | None = None,
    owner_tab: OpenTab | None = None,
) -> None:
    """Render a grouped fixed-label table with scrolling month columns.

    `owner_tab` 은 이 표가 놓인 탭이다. 닫힌 탭에서는 그리지 않는다. 이유는
    `render_split_scroll_table` 의 설명을 보라.

    `page_slot` 은 행이 `page_size` 를 넘을 때 「표시 범위」 칸이 들어갈 자리다. 부르는 쪽이 표 제목
    줄(`table_toolbar.table_heading_row`)의 `with` 안에 만들어 넘긴다 — 제목 줄과 표 사이에 줄을
    더 세우지 않는다.
    """
    if data.empty:
        st.caption("표시할 월별 데이터가 없습니다.")
        return
    month_columns = [column for column in data.columns if column not in classification_columns]
    if not month_columns:
        st.caption("표시할 월별 데이터가 없습니다.")
        return

    # 「표시 범위」 칸은 행 수가 `page_size` 를 넘을 때만 생긴다. 늘 서 있는 이 한 칸 안에 그려 아래
    # 표의 자리를 고정한다 — 밀리면 가로 스크롤 컴포넌트가 다시 마운트되어 스크롤 위치를 잃는다.
    # 비어 있으면 화면에 아무것도 남지 않는다(테두리·높이 없음).
    page_box = st.container() if page_slot is None else page_slot
    if page_size is not None and page_size > 0 and len(data) > page_size:
        total_rows = len(data)
        page_count = (total_rows + page_size - 1) // page_size
        page_key = f"{key}_page"
        _refit_range_on_new_total(page_key, total_rows, page_count)
        with page_box:
            page_index = st.selectbox(
                "표시 범위",
                list(range(page_count)),
                format_func=lambda index: (
                    f"{index * page_size + 1:,}–{min((index + 1) * page_size, total_rows):,}행"
                    f" / {total_rows:,}행"
                ),
                key=page_key,
                persist_state="session",
                label_visibility="collapsed",
                width=180,
            )
        st.session_state[f"{page_key}_shown"] = (total_rows, page_index)
        start_row = page_index * page_size
        data = data.iloc[start_row : start_row + page_size].copy()

    # 위젯(표시 범위)은 그렸으니 상태가 유지된다. 닫힌 탭이면 그림 준비는 여기서 접는다 —
    # 아래 `render_split_scroll_table` 도 막지만 그 전에 격자 1~2초를 만들고 버리고 있었다.
    if tab_is_hidden(owner_tab):
        return
    display = _build_hierarchical_display(data, classification_columns, value_labels)
    column_widths = classification_widths(
        display.classification_values,
        classification_columns,
        column_labels,
    )
    classification_colors = [
        [
            tokens.SURFACE_CLASSIFICATION
            if group_index % 2 == 0
            else tokens.SURFACE_CLASSIFICATION_GROUP
            for group_index in display.top_group_indices
        ]
        for _column in classification_columns
    ]
    month_row_colors = [
        tokens.SURFACE if group_index % 2 == 0 else tokens.SURFACE_SUBTLE
        for group_index in display.top_group_indices
    ]
    month_values = _formatted_month_values(
        data,
        month_columns,
        decimal_places,
        value_format,
    )
    label_figure, month_figure = build_split_table_figures(
        classification_headers=[
            header_label(column_labels.get(column, column)) for column in classification_columns
        ],
        classification_values=display.classification_values,
        classification_fill_colors=classification_colors,
        column_widths=column_widths,
        month_headers=[header_label(month_label(month)) for month in month_columns],
        month_values=month_values,
        month_row_colors=month_row_colors,
        row_count=len(data),
    )
    _add_table_grid(
        label_figure=label_figure,
        month_figure=month_figure,
        display=display,
        classification_widths=column_widths,
        month_columns=month_columns,
        row_count=len(data),
    )

    render_split_scroll_table(
        key=key,
        label_figure=label_figure,
        month_figure=month_figure,
        classification_widths=column_widths,
        month_count=len(month_columns),
        owner_tab=owner_tab,
    )
