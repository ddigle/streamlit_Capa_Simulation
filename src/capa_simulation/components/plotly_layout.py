# Purpose: Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다.

"""Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다."""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any

import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import (
    CORNER_NOTE_RIGHT_PADDING_PX,
    delta_ink_yshift_px,
    delta_line_shift_px,
    value_ink_yshift_px,
)
from capa_simulation.design import tokens

TRANSPARENT_COLOR = tokens.TRANSPARENT


# Figure 에 붙여 두는 누적함. 이름은 Plotly 속성과 겹치지 않아야 한다.
_PENDING_LAYOUT_ITEMS = "_capa_pending_layout_items"


def static_chart_config() -> dict[str, Any]:
    """조작이 없는 그림의 `st.plotly_chart` config. 결과표·라벨 Figure 가 쓴다.

    부를 때마다 새 dict 를 만든다. 모듈 상수 하나를 돌려주면 호출부가 그것을 고칠 때
    다른 화면까지 같이 바뀐다.
    """
    return {"displayModeBar": False, "staticPlot": True}


def hover_chart_config() -> dict[str, Any]:
    """hover 는 살리고 나머지 조작만 끄는 config.

    `staticPlot` 은 hover 까지 함께 끈다. 빼면 `displayModeBar` 기본값이 "hover" 로,
    `doubleClick`·`showAxisDragHandles` 는 켜짐으로 돌아가므로 셋을 직접 끈다. 드래그
    확대는 Figure 축의 `fixedrange` 가 막는다.
    """
    return {"displayModeBar": False, "doubleClick": False, "showAxisDragHandles": False}


def chart_canvas_layout(*, font_size: int) -> dict[str, Any]:
    """캔버스 두 배경색과 기본 서체. **토큰은 부를 때 읽는다.**

    모듈 상수나 기본 인자로 굳히면 그 값만 프로세스가 처음 읽은 테마에 남는다
    (`tests/test_theme_tokens_follow_the_run.py`).
    """
    return {
        "paper_bgcolor": tokens.CHART_CANVAS,
        "plot_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": font_size},
    }


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
    # 위 테두리. paper y=1 은 캔버스의 맨 윗줄이라 획의 절반이 밖으로 나가 잘린다. 좌·우·
    # 아래와 같이 두 배로 그려 보이는 굵기를 맞춘다 — 그렇지 않으면 위만 절반으로 얇다.
    shapes.append(
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": 1,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX * 2},
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
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": y0,
                "xref": "paper",
                "yref": "paper",
                "line": {
                    "color": tokens.BORDER_STRONG,
                    "width": tokens.OUTER_BORDER_WIDTH_PX * 2,
                },
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
    corner_notes: Sequence[tuple[str, str]] | None = None,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer.

    `gaps` 는 값 **위**, `lower_gaps` 는 값 **아래**에 적을 증감 문구다. 빈 문자열이면 그
    칸에는 아무것도 적지 않는다.

    `corner_notes` 는 칸 **오른쪽 위**에 적을 `(글자, hover 글자)` 다(선행 입고 실적). 값 위 증감과
    같은 높이에 서되 오른쪽 끝(`CORNER_NOTE_RIGHT_PADDING_PX`)에 붙는다 — 값·증감·칸 경계 어느
    것도 움직이거나 줄이지 않고 남은 자리에 놓는다. 색은 증감과 갈리는 `ADVANCE_SHIPMENT_TEXT`,
    크기는 증감과 같은 `DELTA_FONT_SIZE_PX` 다. hover 글자는 그 주석에 직접 단다(trace 를 더하지
    않는다).

    **값은 증감이 있든 없든 같은 크기로 칸 한가운데에 선다.** 증감을 끼우려고 값을 줄이거나
    밀면 토글 하나에 표 전체의 숫자가 흔들린다. 두 줄이 들어갈 자리는 행 높이가 미리 비워
    두며(`row_height_with_deltas`), 여기서는 그 자리에 놓기만 한다.
    """
    value_count = max(len(values), 1)
    upper_texts = _gap_texts(gaps, len(values))
    lower_texts = _gap_texts(lower_gaps, len(values))
    if corner_notes is not None and len(corner_notes) != len(values):
        raise ValueError("칸 오른쪽 위 글자 개수가 값 개수와 다릅니다.")
    middle = (domain[0] + domain[1]) / 2
    # 세 글자를 **글리프 가운데** 기준으로 고르게 벌린다. 상자 기준으로 놓으면 같은 거리를
    # 주어도 위쪽 틈이 아래쪽보다 넓어 보인다.
    shift = delta_line_shift_px(font_size)
    value_shift = value_ink_yshift_px(font_size)
    delta_shift = delta_ink_yshift_px()
    annotations = []
    for value_index, (value, upper, lower) in enumerate(
        zip(values, upper_texts, lower_texts, strict=True)
    ):
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
                "yshift": value_shift,
                "font": {
                    "color": tokens.TEXT,
                    "size": font_size,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
        for gap_text, gap_shift in (
            (upper, shift + delta_shift),
            (lower, -shift + delta_shift),
        ):
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
                        "size": tokens.DELTA_FONT_SIZE_PX,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        note, note_hover = corner_notes[value_index] if corner_notes is not None else ("", "")
        if note:
            annotations.append(
                {
                    "x": (value_index + 1) / value_count,
                    "y": middle,
                    "xref": "paper",
                    "yref": "paper",
                    "text": html.escape(note),
                    "hovertext": html.escape(note_hover),
                    "showarrow": False,
                    "xanchor": "right",
                    "yanchor": "middle",
                    "xshift": -CORNER_NOTE_RIGHT_PADDING_PX,
                    # 값 위 증감과 **같은 높이**다. 그 띠는 값 글리프와 `DELTA_GUTTER_PX`, 행 위
                    # 경계와 `ROW_EDGE_PADDING_PX` 만큼 떨어져 있어 위아래로 겹칠 것이 없다.
                    "yshift": shift + delta_shift,
                    "font": {
                        "color": tokens.ADVANCE_SHIPMENT_TEXT,
                        "size": tokens.DELTA_FONT_SIZE_PX,
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
