# Purpose: Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다.

"""Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다."""

from __future__ import annotations

import html
from typing import Any

import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import (
    DASHBOARD_TITLE_GAP_PX,
)
from capa_simulation.design import tokens

TRANSPARENT_COLOR = "rgba(0, 0, 0, 0)"


def dashboard_title_annotation(text: str) -> dict[str, Any]:
    return {
        "x": 0,
        "y": 1,
        "xref": "paper",
        "yref": "paper",
        "text": text,
        "showarrow": False,
        "xanchor": "left",
        "yanchor": "bottom",
        "yshift": DASHBOARD_TITLE_GAP_PX,
        "font": {"size": 20, "color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }


def append_layout_items(
    figure: go.Figure,
    *,
    shapes: list[dict[str, Any]] | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> None:
    """Append Plotly layout collections with one validation pass per collection."""
    updates: dict[str, Any] = {}
    if shapes:
        updates["shapes"] = [*list(figure.layout.shapes or ()), *shapes]
    if annotations:
        updates["annotations"] = [*list(figure.layout.annotations or ()), *annotations]
    if updates:
        figure.update_layout(**updates)


def add_figure_outer_border(
    figure: go.Figure,
    *,
    y0: float = 0.0,
    emphasize_left: bool = True,
    emphasize_bottom: bool = False,
    compensate_bottom: bool = True,
) -> None:
    shapes: list[dict[str, Any]] = []
    if emphasize_left:
        shapes.append(
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "fillcolor": TRANSPARENT_COLOR,
                "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
                "layer": "above",
            }
        )
    else:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": 1,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
                "layer": "above",
            }
        )
    if emphasize_left:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 0,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {
                    "color": tokens.BORDER_STRONG,
                    "width": tokens.OUTER_BORDER_WIDTH_PX * 2,
                },
                "layer": "above",
            }
        )
    shapes.append(
        {
            "type": "line",
            "x0": 1,
            "x1": 1,
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX * 2},
            "layer": "above",
        }
    )
    if emphasize_bottom:
        bottom_width = tokens.OUTER_BORDER_WIDTH_PX * (2 if compensate_bottom else 1)
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": y0,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER_STRONG, "width": bottom_width},
                "layer": "above",
            }
        )
    append_layout_items(figure, shapes=shapes)


def add_quarter_boundaries(
    figure: go.Figure,
    month_labels: list[str],
    *,
    y0: float = 0.0,
) -> None:
    quarter_keys = [
        (int(month.split(".")[0]), (int(month.split(".")[1]) - 1) // 3) for month in month_labels
    ]
    shapes = [
        {
            "type": "line",
            "x0": month_index / len(quarter_keys),
            "x1": month_index / len(quarter_keys),
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for month_index in range(1, len(quarter_keys))
        if quarter_keys[month_index] != quarter_keys[month_index - 1]
    ]
    append_layout_items(figure, shapes=shapes)


def fixed_row_domains(
    domain_bottom: float,
    domain_top: float,
    row_heights: tuple[int, ...],
) -> list[tuple[float, float]]:
    total_height = sum(row_heights)
    current_top = domain_top
    domains: list[tuple[float, float]] = []
    for row_height in row_heights:
        row_bottom = current_top - (row_height / total_height * (domain_top - domain_bottom))
        domains.append((row_bottom, current_top))
        current_top = row_bottom
    return domains


def add_fixed_table_row(
    figure: go.Figure,
    *,
    domain: tuple[float, float],
    values: list[str],
    fill_color: str,
    font_size: int,
    bold: bool,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer."""
    value_count = max(len(values), 1)
    annotations = []
    for value_index, value in enumerate(values):
        escaped_value = html.escape(value)
        annotations.append(
            {
                "x": (value_index + 0.5) / value_count,
                "y": (domain[0] + domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": f"<b>{escaped_value}</b>" if bold else escaped_value,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {
                    "color": tokens.TEXT,
                    "size": font_size,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
    append_layout_items(
        figure,
        shapes=[
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": domain[0],
                "y1": domain[1],
                "xref": "paper",
                "yref": "paper",
                "fillcolor": fill_color,
                "line": {"width": 0},
                "layer": "below",
            }
        ],
        annotations=annotations,
    )
