# Purpose: HOME 의 분류별 계획 세부수량 표 Figure 한 쌍을 만든다.

"""계획 세부수량 Figure.

왼쪽 분류 칸과 오른쪽 월 칸을 두 `go.Table` 로 나눠 돌려준다. 비교 시나리오를 주면 값
아래에 증감을 주석으로 얹는다 — 칸 안에 두 줄을 담으면 행 높이가 부푼다.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import (
    lower_delta_row_height,
    lower_delta_yshift_px,
    table_row_height,
)
from capa_simulation.components.home_figure_common import (
    _paper_hrule,
    _paper_month_lines,
    _past_surface,
)
from capa_simulation.components.plotly_layout import (
    TRANSPARENT_COLOR,
    add_figure_outer_border,
    add_quarter_boundaries,
    append_layout_items,
    delta_color,
    flush_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.dashboard import (
    DETAIL_DIMENSION_HEADERS,
    DETAIL_DIMENSION_WIDTHS,
    PRODUCTION_DETAIL_DIMENSIONS,
)

# 계획 세부수량 칸의 값 글자. 분류 칸과 월 칸이 같아야 두 칸의 글자가 같은 눈높이에 선다.
DETAIL_VALUE_FONT_SIZE_PX = 14

# 계획 세부수량 머리글. 칸 높이가 이 크기에서 나온다.
DETAIL_HEADER_FONT_SIZE_PX = 15


def _detail_month_cell_values(
    displayed_detail: pd.DataFrame,
    month: str,
    gap_amounts: Sequence[float] | None = None,
) -> tuple[list[str], list[str]]:
    """한 달의 세부수량 값과 그 아래 증감을 따로 돌려준다. 없는 달은 빈 칸이다.

    증감을 값과 한 칸에 담지 않는 이유는 두 가지다. 칸 안에서 `<br>` 로 줄을 더하면 값이
    칸 가운데 정렬 탓에 위로 올라가 왼쪽 분류 칸과 눈높이가 어긋나고, Plotly 가 줄 상자
    두 개에 고정 여백을 더한 높이를 요구해 행이 필요 이상으로 두꺼워진다. 값은 한 줄로
    두고 증감은 주석으로 얹는다.
    """
    if month not in displayed_detail.columns:
        return [""] * len(displayed_detail), [""] * len(displayed_detail)
    values = [
        "" if pd.isna(value) or float(value) == 0 else f"{float(value):,.0f}K"
        for value in displayed_detail[month]
    ]
    if gap_amounts is None:
        return values, [""] * len(values)
    gaps: list[str] = []
    for value, difference in zip(values, gap_amounts, strict=True):
        if not value or abs(difference) < 0.5:
            gaps.append("")
            continue
        gaps.append(f"{difference:+,.0f}K")
    return values, gaps


def _detail_gap_amounts(
    displayed_detail: pd.DataFrame,
    comparison_detail: pd.DataFrame,
    month: str,
    *,
    gap_month_labels: Collection[str] | None,
    year_total_labels: Sequence[str],
) -> list[float] | None:
    """그 칸에 적을 행별 증감. `None` 이면 증감 줄을 아예 비운다.

    **과거 구간에는 증감을 적지 않는다.** 과거는 시나리오와 분리된 공용 프로필
    (`app_meta.global_past_*`)에서 오므로 현재와 비교 시나리오가 같은 값을 받는다. 그런데
    비교 프레임에는 과거가 병합되지 않아 그 달 컬럼이 아예 없고, 아래 「없는 쪽을 0 으로
    본다」 규칙이 그대로 걸리면 **과거 입력 전액이 거짓 증감**으로 찍힌다.

    연간 Total 도 같은 이유로 DB 계산 구간의 달만 더한다. 그러지 않으면 비교 쪽에 Total
    컬럼이 없어 그 해 합계 전체가 증감이 된다.
    """

    def amounts(frame: pd.DataFrame, column: str) -> list[float]:
        if column not in frame.columns:
            # 한쪽에만 있는 조합은 없는 쪽을 0 으로 본다. 비교의 목적이 사라지거나 새로
            # 생긴 제품을 보이게 하는 것이라 그 전액이 증감이어야 한다.
            return [0.0] * len(displayed_detail)
        numeric = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        return [float(value) for value in numeric]

    def difference(column: str) -> list[float]:
        return [
            current - before
            for current, before in zip(
                amounts(displayed_detail, column),
                amounts(comparison_detail, column),
                strict=True,
            )
        ]

    if month in year_total_labels:
        members = _gap_months_of_year(
            month,
            displayed_detail.columns,
            gap_month_labels=gap_month_labels,
        )
        if not members:
            return None
        totals = [0.0] * len(displayed_detail)
        for label in members:
            totals = [total + value for total, value in zip(totals, difference(label), strict=True)]
        return totals
    if gap_month_labels is not None and month not in gap_month_labels:
        return None
    return difference(month)


def _gap_months_of_year(
    total_label: str,
    columns: Iterable[object],
    *,
    gap_month_labels: Collection[str] | None,
) -> list[str]:
    """연간 Total 칸이 더할 달. 월 라벨은 `26.07` 이고 Total 라벨은 `26년` 이다."""
    prefix = f"{total_label[:2]}."
    source: Iterable[object] = columns if gap_month_labels is None else gap_month_labels
    return [str(label) for label in source if isinstance(label, str) and label.startswith(prefix)]


def _centered_cell_text(value: str) -> str:
    """표 칸 한가운데에 서는 한 줄.

    `go.Table` 은 **한 줄짜리 칸의 글자를 칸 위에 붙여** 그리고, 여러 줄일 때만 가운데에
    세운다. 칸의 세로 정렬을 직접 지정할 방법은 없다 — `table.Cells` 에 `valign` 이 없다.

    빈 줄 하나를 뒤에 붙이면 Plotly 가 여러 줄로 보아 가운데에 세우는데, 그 빈 줄은 높이를
    더하지 않아 행이 두꺼워지지 않는다. 증감이 오지 않는 칸에 이것을 쓴다 — 분류 칸은 늘,
    월 칸은 GAP 이 꺼져 있을 때다.

    빈 칸은 그대로 둔다 — 붙이면 없는 값 자리에 빈 줄만 생긴다.
    """
    return f"{value}<br>" if value else ""


def build_plan_detail_figures(
    *,
    production_detail: pd.DataFrame,
    month_labels: list[str],
    detail_dimensions: list[str] | None = None,
    comparison_detail: pd.DataFrame | None = None,
    year_total_labels: Sequence[str] = (),
    gap_month_labels: Collection[str] | None = None,
    past_month_labels: Collection[str] | None = None,
) -> tuple[go.Figure, go.Figure]:
    """분류별 계획 세부수량 Figure 한 쌍을 만든다.

    `detail_dimensions` 는 왼쪽 분류 칸을 정한다. 기본은 제품·Stack 이고 `상세` 를 켜면
    거래선이 더해진다. 머리글과 칸 폭은 컬럼 이름에서 끌어오므로 분류가 늘어도 여기서
    다시 적을 것이 없다.
    """
    dimensions = list(detail_dimensions or PRODUCTION_DETAIL_DIMENSIONS)
    detail_dimension_widths = [DETAIL_DIMENSION_WIDTHS.get(column, 1.0) for column in dimensions]
    # 제품 칸이 끝나는 자리(paper 0~1). **폭에서 계산한다** — `상세` 를 켜면 거래선이
    # 붙어 분모가 2.0 에서 3.0 으로 바뀌는데, 숫자를 박아 두면 그때 선이 엉뚱한 칸
    # 경계로 밀린다. 실제로 그렇게 밀려 있었다.
    detail_product_boundary = detail_dimension_widths[0] / sum(detail_dimension_widths)
    # 조회 범위의 모든 달을 컬럼으로 유지한다. 세부 데이터에 없는 달을 빼면 컬럼 수가
    # 줄어드는데 Figure 폭은 `len(month_labels)` 로 잡으므로, 컬럼 폭이 100px 그리드보다
    # 넓어져 헤더가 뒤로 갈수록 밀린다. 요약표와 월이 세로로 어긋나기도 한다.
    detail_month_columns = list(month_labels)
    displayed_detail = production_detail.copy()
    detail_dimension_values = [
        ["" if pd.isna(value) else str(value) for value in displayed_detail[column]]
        for column in dimensions
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
    # 같은 제품 **안**에서 Stack 이 바뀌는 자리. 제품 경계와 겹치지 않는다 — 제품이 바뀌면
    # 굵은 선이 이미 서므로 여기에 얇은 선을 겹쳐 그으면 두 선이 붙어 지저분해진다.
    detail_stack_starts: list[int] = []
    previous_product: str | None = None
    previous_stack: str | None = None
    group_index = -1
    product_values = detail_dimension_values[0] if detail_dimension_values else []
    stack_values = detail_dimension_values[1] if len(detail_dimension_values) > 1 else []
    for row_index, product in enumerate(product_values):
        stack = stack_values[row_index] if stack_values else None
        if row_index == 0 or product != previous_product:
            group_index += 1
            if row_index > 0:
                detail_group_starts.append(row_index)
        elif stack_values and stack != previous_stack:
            detail_stack_starts.append(row_index)
        detail_group_indices.append(group_index)
        previous_product = product
        previous_stack = stack

    grouped_dimension_values = [
        [_centered_cell_text(value) for value in values] for values in grouped_dimension_values
    ]

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
    # 값 한 줄과 그 아래 증감 한 줄이 온전히 들어가는 높이. 증감이 없어도 같은 높이를 쓴다.
    detail_row_height = lower_delta_row_height(DETAIL_VALUE_FONT_SIZE_PX)
    detail_header_height = table_row_height(DETAIL_HEADER_FONT_SIZE_PX)
    # 제목 자리를 Figure 가 갖지 않는다. `계획 세부수량` 은 Plotly 주석이 아니라 Streamlit
    # 이 그려서 그 옆에 「상세」 토글을 둔다. 두 칸 모두 같은 높이의 줄을 끼우므로 여백을
    # 남겨 두면 표 위에 빈 띠만 생긴다.
    detail_figure_height = detail_header_height + max(len(displayed_detail), 1) * detail_row_height
    detail_label_figure = go.Figure(
        go.Table(
            columnwidth=detail_dimension_widths,
            header={
                "values": [
                    f"<b>{DETAIL_DIMENSION_HEADERS.get(column, column)}</b>"
                    for column in dimensions
                ],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_HEADER_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": grouped_dimension_values,
                "align": "center",
                "fill_color": [detail_label_row_colors for _ in dimensions],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_VALUE_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_month_cells = [
        _detail_month_cell_values(
            displayed_detail,
            month,
            None
            if comparison_detail is None
            else _detail_gap_amounts(
                displayed_detail,
                comparison_detail,
                month,
                gap_month_labels=gap_month_labels,
                year_total_labels=year_total_labels,
            ),
        )
        for month in detail_month_columns
    ]
    # GAP 이 꺼져 있으면 월 칸에도 증감이 오지 않으므로 값을 분류 칸처럼 한가운데에 세운다.
    # 켜면 값이 위로 붙고 그 아래가 증감 주석 자리다. 행 높이는 어느 쪽이든 같아서 토글에
    # 표 높이가 출렁이지는 않는다 — 움직이는 것은 칸 안의 글자뿐이다.
    reserves_gap_line = comparison_detail is not None
    detail_month_values = [
        values if reserves_gap_line else [_centered_cell_text(value) for value in values]
        for values, _ in detail_month_cells
    ]

    def _detail_month_column_fills(month: str) -> list[str]:
        """한 월 열의 행별 바탕색. 제품 그룹 줄무늬를 과거 구간에서도 유지한다."""
        base = (
            [tokens.SURFACE_YEAR_TOTAL] * len(detail_month_row_colors)
            if month in year_total_labels
            else detail_month_row_colors
        )
        if past_month_labels is not None and month in past_month_labels:
            return [_past_surface(surface) for surface in base]
        return base

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
                    "size": DETAIL_HEADER_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": detail_month_values,
                "align": "center",
                "fill_color": [_detail_month_column_fills(month) for month in detail_month_columns],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_VALUE_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_layout = {
        "height": detail_figure_height,
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    detail_label_figure.update_layout(**detail_layout)
    detail_month_figure.update_layout(
        **detail_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    # 경계선 비율의 분모는 Figure 높이와 **같은 수**여야만 맞는다. 이름을 둘로 두면 한쪽
    # 행 높이만 고쳤을 때 머리글 밑줄과 그룹 경계가 조용히 어긋난다.
    detail_header_boundary_y = 1 - detail_header_height / detail_figure_height
    add_figure_outer_border(detail_label_figure, emphasize_bottom=True)
    add_figure_outer_border(
        detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    detail_header_shape = _paper_hrule(
        detail_header_boundary_y,
        color=tokens.BORDER_STRONG,
        width=tokens.OUTER_BORDER_WIDTH_PX,
    )
    append_layout_items(
        detail_label_figure,
        shapes=[
            detail_header_shape,
            {
                "type": "line",
                "x0": detail_product_boundary,
                "x1": detail_product_boundary,
                "y0": 0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                "layer": "above",
            },
        ],
    )
    append_layout_items(
        detail_month_figure,
        shapes=[
            detail_header_shape,
            *_paper_month_lines(len(detail_month_columns), y0=0, layer="above"),
        ],
    )
    add_quarter_boundaries(detail_month_figure, detail_month_columns)
    # 증감은 칸 안의 둘째 줄이 아니라 값 아래에 얹는 주석이다. 칸이 값 한 줄만 담으므로
    # 행 높이가 한 줄짜리 칸의 최소 높이로 줄고, 증감이 붙든 말든 값은 같은 자리에 선다.
    # 기준점은 행의 **위 모서리**다 — Plotly 가 한 줄짜리 칸의 글자를 위에 붙여 그린다.
    detail_delta_yshift = lower_delta_yshift_px(DETAIL_VALUE_FONT_SIZE_PX)
    append_layout_items(
        detail_month_figure,
        annotations=[
            {
                "x": (month_index + 0.5) / len(detail_month_columns),
                "y": 1
                - (detail_header_height + row_index * detail_row_height) / detail_figure_height,
                "xref": "paper",
                "yref": "paper",
                "text": gap,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "yshift": detail_delta_yshift,
                "font": {
                    "color": delta_color(gap),
                    "size": tokens.DELTA_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY_NUMERIC,
                },
            }
            for month_index, (_, gaps) in enumerate(detail_month_cells)
            for row_index, gap in enumerate(gaps)
            if gap
        ],
    )

    def _detail_row_rule(
        row_start: int, color: str, width: float, *, x0: float = 0.0
    ) -> dict[str, Any]:
        """행 `row_start` 의 위 모서리에 놓는 가로 선."""
        y = 1 - (detail_header_height + row_start * detail_row_height) / detail_figure_height
        return _paper_hrule(y, color=color, width=width, x0=x0)

    def _detail_group_shapes(stack_x0: float) -> list[dict[str, Any]]:
        """얇은 선을 **먼저** 넣는다. 제품 경계의 굵은 선이 뒤에 와야 겹칠 때 위로 올라온다."""
        return [
            *(
                _detail_row_rule(stack_start, tokens.BORDER, tokens.GRID_LINE_WIDTH_PX, x0=stack_x0)
                for stack_start in detail_stack_starts
            ),
            *(
                _detail_row_rule(group_start, tokens.BORDER_STRONG, tokens.GROUP_BORDER_WIDTH_PX)
                for group_start in detail_group_starts
            ),
        ]

    # **두 Figure 가 다른 선을 받는다.** 제품 경계(굵은 선)는 둘 다 전폭이지만, Stack
    # 경계(얇은 선)는 분류 칸에서 제품 칸을 비우고 그 오른쪽부터 긋는다. 제품이 바뀌지
    # 않았는데 제품 칸까지 선이 지나가면 그 제품 묶음이 끊겨 보인다 — 굵은 선과 얇은 선이
    # 같은 굵기로 읽혀 계층이 사라진다. 월 칸에는 나눌 분류가 없으므로 전폭이다.
    append_layout_items(detail_label_figure, shapes=_detail_group_shapes(detail_product_boundary))
    append_layout_items(detail_month_figure, shapes=_detail_group_shapes(0.0))
    flush_layout_items(detail_label_figure, detail_month_figure)
    return detail_label_figure, detail_month_figure
