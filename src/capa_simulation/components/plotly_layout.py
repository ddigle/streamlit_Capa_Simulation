# Purpose: Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다.

"""Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다."""

from __future__ import annotations

import html
from collections.abc import Sequence
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


# Figure 에 붙여 두는 누적함. 이름은 Plotly 속성과 겹치지 않아야 한다.
_PENDING_LAYOUT_ITEMS = "_capa_pending_layout_items"


def _pending_layout_items(figure: go.Figure) -> dict[str, list[dict[str, Any]]]:
    """그 Figure 의 누적함. 처음 열 때 이미 들어 있던 항목을 평범한 dict 로 옮겨 온다."""
    pending = getattr(figure, _PENDING_LAYOUT_ITEMS, None)
    if pending is None:
        pending = {
            "shapes": [item.to_plotly_json() for item in (figure.layout.shapes or ())],
            "annotations": [item.to_plotly_json() for item in (figure.layout.annotations or ())],
        }
        setattr(figure, _PENDING_LAYOUT_ITEMS, pending)
    return pending


def append_layout_items(
    figure: go.Figure,
    *,
    shapes: list[dict[str, Any]] | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> None:
    """레이아웃 항목을 모아만 둔다. 실제 반영은 `flush_layout_items` 가 한 번에 한다.

    부를 때마다 `update_layout` 하면 Plotly 가 **그때까지 쌓인 항목 전부를 다시 검증**한다.
    항목이 수백 개인 화면에서 그 재검증이 O(n²) 로 불어나 Figure 하나에 7 초가 들었다.
    같은 항목을 마지막에 한 번만 넣으면 0.1 초다.

    그래서 Figure 를 돌려주는 쪽이 **반드시 `flush_layout_items` 를 불러야 한다.** 잊으면
    테두리·격자·라벨이 통째로 사라져 화면에서 바로 드러난다.
    """
    pending = _pending_layout_items(figure)
    if shapes:
        pending["shapes"].extend(shapes)
    if annotations:
        pending["annotations"].extend(annotations)


def flush_layout_items(*figures: go.Figure) -> None:
    """모아 둔 항목을 Figure 마다 한 번에 반영한다. 여러 번 불러도 결과가 같다."""
    for figure in figures:
        pending = getattr(figure, _PENDING_LAYOUT_ITEMS, None)
        if pending is None:
            continue
        figure.update_layout(
            shapes=pending["shapes"],
            annotations=pending["annotations"],
        )


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
    # 월 축에는 `YY.MM` 이 아닌 칸도 섞인다(연간 Total). 분기를 셀 수 없으므로 그 칸은
    # 자기만의 칸으로 두어 양옆에 경계가 서게 한다 — 합계 칸이 분기에 묻히면 안 된다.
    quarter_keys: list[tuple[int, int] | str] = []
    for month in month_labels:
        year, _, month_number = month.partition(".")
        if month_number.isdigit() and year.isdigit():
            quarter_keys.append((int(year), (int(month_number) - 1) // 3))
        else:
            quarter_keys.append(month)
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


# GAP 을 함께 적을 때 값 글자를 줄이는 정도와 줄을 벌리는 거리. 행 높이는 그대로 두고
# 이 둘만 조인다. 행마다 높이가 달라지면 왼쪽 라벨 칸과 월 칸의 행이 어긋난다.
#
# 위·아래 GAP 이 함께 붙으면 한 칸이 세 줄이 된다. 그때만 값을 한 단계 더 줄이고 간격을
# 넓혀 36px 안에 들어가게 한다.
GAP_VALUE_FONT_SCALE = 0.85
GAP_VALUE_FONT_SCALE_BOTH = 0.65
GAP_FONT_SCALE = 0.6
GAP_LINE_SHIFT_PX = 9
GAP_LINE_SHIFT_PX_BOTH = 12


def _gap_texts(gaps: list[str] | None, count: int) -> list[str]:
    if gaps is None:
        return [""] * count
    if len(gaps) != count:
        raise ValueError("GAP 개수가 값 개수와 다릅니다.")
    return list(gaps)


def delta_color(text: str) -> str:
    """증감 문구의 색. 부호만 본다 — 좋고 나쁨이 아니라 방향이다."""
    return tokens.DELTA_DECREASE if text.strip().startswith("-") else tokens.DELTA_INCREASE


def add_fixed_table_row(
    figure: go.Figure,
    *,
    domain: tuple[float, float],
    values: list[str],
    fill_color: str | Sequence[str],
    font_size: int,
    bold: bool,
    gaps: list[str] | None = None,
    lower_gaps: list[str] | None = None,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer.

    `gaps` 는 값 **위**, `lower_gaps` 는 값 **아래**에 작게 적을 증감 문구다. 빈 문자열이면
    그 칸에는 아무것도 적지 않고 값도 원래 크기·위치 그대로 둔다 — 변화가 없는 칸까지
    글자를 줄이면 같은 행 안에서 숫자 크기가 들쭉날쭉해진다.
    """
    value_count = max(len(values), 1)
    upper_texts = _gap_texts(gaps, len(values))
    lower_texts = _gap_texts(lower_gaps, len(values))
    middle = (domain[0] + domain[1]) / 2
    annotations = []
    for value_index, (value, upper, lower) in enumerate(
        zip(values, upper_texts, lower_texts, strict=True)
    ):
        escaped_value = html.escape(value)
        position = (value_index + 0.5) / value_count
        both = bool(upper) and bool(lower)
        shift = GAP_LINE_SHIFT_PX_BOTH if both else GAP_LINE_SHIFT_PX
        if both:
            value_size = round(font_size * GAP_VALUE_FONT_SCALE_BOTH)
        elif upper or lower:
            value_size = round(font_size * GAP_VALUE_FONT_SCALE)
        else:
            value_size = font_size
        # 한쪽에만 붙으면 값이 반대쪽으로 밀려 칸 가운데를 유지한다. 양쪽이면 그대로 둔다.
        value_shift = 0 if both else (-shift if upper else (shift if lower else 0))
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
                "yshift": value_shift,
                "font": {
                    "color": tokens.TEXT,
                    "size": value_size,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
        for gap_text, gap_shift in ((upper, shift), (lower, -shift)):
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
                    "yshift": gap_shift,
                    "font": {
                        "color": delta_color(gap_text),
                        "size": round(font_size * GAP_FONT_SCALE),
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
    # 칸마다 다른 면색을 받으면 칸 단위로 사각형을 그린다. 연간 Total 열만 살짝 어둡게
    # 하려고 행 전체를 다시 그리지 않는다.
    if isinstance(fill_color, str) or len(set(fill_color)) <= 1:
        single = fill_color if isinstance(fill_color, str) else next(iter(fill_color), "")
        fills = [{"x0": 0.0, "x1": 1.0, "color": single}]
    else:
        if len(fill_color) != len(values):
            raise ValueError("면색 개수가 값 개수와 다릅니다.")
        fills = [
            {
                "x0": index / value_count,
                "x1": (index + 1) / value_count,
                "color": color,
            }
            for index, color in enumerate(fill_color)
        ]
    append_layout_items(
        figure,
        shapes=[
            {
                "type": "rect",
                "x0": fill["x0"],
                "x1": fill["x1"],
                "y0": domain[0],
                "y1": domain[1],
                "xref": "paper",
                "yref": "paper",
                "fillcolor": fill["color"],
                "line": {"width": 0},
                "layer": "below",
            }
            for fill in fills
        ],
        annotations=annotations,
    )
