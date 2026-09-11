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

TRANSPARENT_COLOR = tokens.TRANSPARENT


def dashboard_title_annotation(text: str) -> dict[str, Any]:
    """대시보드 구획 제목을 만든다. 앞의 강조색 막대가 구획의 시작을 알린다.

    예전에는 손 이모지(☝️✌️👌)로 순서를 표시했다. 플랫폼마다 다르게 그려지고 화면
    톤과도 맞지 않아 강조색 막대로 바꿨다.
    """
    return {
        "x": 0,
        "y": 1,
        "xref": "paper",
        "yref": "paper",
        "text": f'<span style="color:{tokens.ACCENT}">▍</span>{text}',
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


# GAP 을 함께 적을 때 값 글자를 줄이는 정도와 두 줄을 벌리는 거리. 행 높이는 그대로
# 두고 이 둘만 조인다. 행마다 높이가 달라지면 왼쪽 라벨 칸과 월 칸의 행이 어긋난다.
GAP_VALUE_FONT_SCALE = 0.85
GAP_FONT_SCALE = 0.6
GAP_LINE_SHIFT_PX = 9


def delta_color(text: str) -> str:
    """증감 문구의 색. 부호만 본다 — 좋고 나쁨이 아니라 방향이다."""
    return tokens.DELTA_DECREASE if text.strip().startswith("-") else tokens.DELTA_INCREASE


def add_fixed_table_row(
    figure: go.Figure,
    *,
    domain: tuple[float, float],
    values: list[str],
    fill_color: str,
    font_size: int,
    bold: bool,
    gaps: list[str] | None = None,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer.

    `gaps` 는 칸마다 값 위에 작게 적을 증감 문구다. 빈 문자열이면 그 칸에는 아무것도
    적지 않고 값도 원래 크기·위치 그대로 둔다 — 변화가 없는 칸까지 글자를 줄이면 같은
    행 안에서 숫자 크기가 들쭉날쭉해진다.
    """
    value_count = max(len(values), 1)
    gap_texts = list(gaps) if gaps is not None else [""] * len(values)
    if len(gap_texts) != len(values):
        raise ValueError("GAP 개수가 값 개수와 다릅니다.")
    middle = (domain[0] + domain[1]) / 2
    annotations = []
    for value_index, (value, gap_text) in enumerate(zip(values, gap_texts, strict=True)):
        escaped_value = html.escape(value)
        position = (value_index + 0.5) / value_count
        annotations.append(
            {
                "x": position,
                "y": middle,
                "xref": "paper",
                "yref": "paper",
                "text": f"<b>{escaped_value}</b>" if bold else escaped_value,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "yshift": -GAP_LINE_SHIFT_PX if gap_text else 0,
                "font": {
                    "color": tokens.TEXT,
                    "size": round(font_size * GAP_VALUE_FONT_SCALE) if gap_text else font_size,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
        if not gap_text:
            continue
        annotations.append(
            {
                "x": position,
                "y": middle,
                "xref": "paper",
                "yref": "paper",
                "text": html.escape(gap_text),
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "yshift": GAP_LINE_SHIFT_PX,
                "font": {
                    "color": delta_color(gap_text),
                    "size": round(font_size * GAP_FONT_SCALE),
                    "family": tokens.FONT_FAMILY_NUMERIC,
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
