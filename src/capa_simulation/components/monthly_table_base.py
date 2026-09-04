# Purpose: 월별 Plotly 표 두 종류가 공유하는 색·치수·텍스트 계산과 스크롤 셸을 제공한다.

"""Shared pieces of the two monthly Plotly tables.

`grouped_monthly_table`(부분합 있는 환산 결과)과 `hierarchical_monthly_table`(합계 없는
상세 결과)은 서로 다른 표지만 고정 분류 영역 + 가로 스크롤 월 영역이라는 껍데기와 텍스트
폭 계산은 같다. 그 공통분만 여기 둔다.

격자 그리기 중 바깥 테두리·헤더 밑줄·월 경계선·분류 컬럼 세로선은 두 표가 같은 도형을
그리므로 여기로 합쳤다. 행 그룹 가로선만 표 구조가 달라 각 모듈에 남긴다. `grouped` 는
부분합 3단(제품·생산·총계)을 고정 폭으로, `hierarchical` 은 계층 깊이에 따라 폭을
줄여 가며 긋는다.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 테스트가 스크롤바를 갈아끼울 수 있도록 이름이 아니라 모듈을 잡는다. 이름을 직접
# import 하면 여기서 잡은 바인딩이 교체를 무시한다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.scroll_shell import horizontal_scroll_canvas
from capa_simulation.design import tokens

# 색과 치수는 design/tokens.py 가 단일 근거다. 여기서는 표 문맥의 이름만 붙인다.
HEADER_COLOR = tokens.HEADER_BACKGROUND
CLASSIFICATION_COLOR = tokens.SURFACE_CLASSIFICATION
CLASSIFICATION_GROUP_COLOR = tokens.SURFACE_CLASSIFICATION_GROUP
SURFACE_COLOR = tokens.SURFACE
GROUP_SURFACE_COLOR = tokens.SURFACE_SUBTLE
BORDER_COLOR = tokens.BORDER
GROUP_BORDER_COLOR = tokens.BORDER_STRONG
TEXT_COLOR = tokens.TEXT
TRANSPARENT_COLOR = "rgba(0, 0, 0, 0)"

OUTER_BORDER_WIDTH_PX = tokens.OUTER_BORDER_WIDTH_PX
GRID_LINE_WIDTH_PX = tokens.GRID_LINE_WIDTH_PX
CLASSIFICATION_MIN_WIDTH_PX = tokens.CLASSIFICATION_MIN_WIDTH_PX
CLASSIFICATION_MAX_WIDTH_PX = tokens.CLASSIFICATION_MAX_WIDTH_PX
CLASSIFICATION_TEXT_UNIT_PX = tokens.CLASSIFICATION_TEXT_UNIT_PX
CLASSIFICATION_HORIZONTAL_PADDING_PX = tokens.CLASSIFICATION_HORIZONTAL_PADDING_PX
MONTH_COLUMN_WIDTH_PX = tokens.MONTH_COLUMN_WIDTH_PX
MONTH_SCROLL_THRESHOLD = tokens.TABLE_MONTH_SCROLL_THRESHOLD
SCROLLBAR_HEIGHT_PX = tokens.SCROLLBAR_HEIGHT_PX
HEADER_HEIGHT_PX = tokens.TABLE_HEADER_HEIGHT_PX
ROW_HEIGHT_PX = tokens.TABLE_ROW_HEIGHT_PX


# 표 머리글과 CSV 헤더에 쓰는 분류 컬럼 표시 이름이다. 폭을 아끼려고 줄여 쓴다.
# 전에는 페이지 4곳에 따로 있었다. 겹치는 값은 모두 같았고 `Capa Code` 는 정의한 두
# 페이지가 이미 `PKG Code` 를 쓰고 있어 그 이름으로 통일했다.
COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
    "Area_Name": "Area",
    "STEP_SEQ": "Step",
    "MCP_SEQ": "MCP",
    "Capa Code": "PKG Code",
    "Customer": "거래선",
    "수율 구분": "구분",
}


def display_text(value: object) -> str:
    """Plotly 셀에 넣을 표시 문자열로 바꾼다. 결측은 빈 칸으로 둔다."""
    return "" if bool(pd.isna(cast(Any, value))) else str(value)


def text_width_units(value: str) -> float:
    """전각 1.0, 반각 0.6으로 세어 분류 컬럼 폭 계산용 길이를 만든다."""
    return sum(
        1.0 if unicodedata.east_asian_width(character) in {"F", "W"} else 0.6 for character in value
    )


def month_label(month: str) -> str:
    """`YYYYMM`을 화면 표기 `YY.MM`으로 바꾼다."""
    normalized = str(month).strip()
    if len(normalized) == 6 and normalized.isdigit():
        return f"{normalized[2:4]}.{normalized[4:6]}"
    return normalized


def quarter_key(month: str) -> tuple[str, int] | None:
    """월 컬럼의 분기 경계를 그리기 위한 (연 2자리, 0-기준 분기) 키를 만든다."""
    year_month = month_label(month).split(".")
    if len(year_month) != 2 or not all(value.isdigit() for value in year_month):
        return None
    year, month_text = year_month
    month_number = int(month_text)
    if not 1 <= month_number <= 12:
        return None
    return year, (month_number - 1) // 3


def table_height_px(row_count: int) -> float:
    """헤더 + 본문 행으로 Figure 전체 높이를 계산한다."""
    return HEADER_HEIGHT_PX + max(row_count, 1) * ROW_HEIGHT_PX


def header_boundary_ratio(row_count: int) -> float:
    """헤더와 본문의 경계를 paper 좌표(0~1)로 돌려준다."""
    return 1 - HEADER_HEIGHT_PX / table_height_px(row_count)


def add_outer_border(figure: go.Figure, *, include_left: bool) -> None:
    """표 바깥 테두리를 그린다. 좌변은 분류 영역 Figure 에만 넣는다.

    월 영역 Figure 는 분류 영역 바로 오른쪽에 붙기 때문에 좌변을 그리면 경계가 두 겹으로
    보인다. 그래서 상·우·하 세 변만 공통이고 좌변은 선택이다.
    """
    edges = [(0, 1, 1, 1), (1, 1, 0, 1), (0, 1, 0, 0)]
    if include_left:
        edges.append((0, 0, 0, 1))
    for x0, x1, y0, y1 in edges:
        figure.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=y0,
            y1=y1,
            xref="paper",
            yref="paper",
            line={"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX * 2},
            layer="above",
        )


def add_header_rule(figure: go.Figure, *, boundary_y: float) -> None:
    """헤더와 본문을 가르는 가로선을 긋는다."""
    figure.add_shape(
        type="line",
        x0=0,
        x1=1,
        y0=boundary_y,
        y1=boundary_y,
        xref="paper",
        yref="paper",
        line={"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
        layer="above",
    )


def add_classification_boundaries(
    figure: go.Figure,
    classification_widths: Sequence[float],
) -> None:
    """분류 컬럼 사이마다 세로 격자선을 긋는다."""
    total_width = sum(classification_widths)
    for column_index in range(1, len(classification_widths)):
        boundary_x = sum(classification_widths[:column_index]) / total_width
        figure.add_shape(
            type="line",
            x0=boundary_x,
            x1=boundary_x,
            y0=0,
            y1=1,
            xref="paper",
            yref="paper",
            line={"color": BORDER_COLOR, "width": GRID_LINE_WIDTH_PX},
            layer="above",
        )


def add_month_boundaries(figure: go.Figure, month_columns: Sequence[str]) -> None:
    """월 컬럼 사이에 세로 격자선을 긋고 분기가 바뀌는 자리는 굵게 강조한다."""
    quarter_keys = [quarter_key(month) for month in month_columns]
    for month_index in range(1, len(month_columns)):
        is_quarter_boundary = (
            quarter_keys[month_index] is not None
            and quarter_keys[month_index - 1] is not None
            and quarter_keys[month_index] != quarter_keys[month_index - 1]
        )
        figure.add_shape(
            type="line",
            x0=month_index / len(month_columns),
            x1=month_index / len(month_columns),
            y0=0,
            y1=1,
            xref="paper",
            yref="paper",
            line={
                "color": GROUP_BORDER_COLOR if is_quarter_boundary else BORDER_COLOR,
                "width": OUTER_BORDER_WIDTH_PX if is_quarter_boundary else GRID_LINE_WIDTH_PX,
            },
            layer="above",
        )


def render_split_scroll_table(
    *,
    key: str,
    label_figure: go.Figure,
    month_figure: go.Figure,
    classification_widths: Sequence[float],
    month_count: int,
) -> None:
    """고정 분류 영역과 가로 스크롤 월 영역을 나란히 렌더링한다.

    월 영역의 네이티브 스크롤바는 숨기고 `horizontal_scrollbar` 컴포넌트로 대체한다.
    두 Figure 의 행 높이가 같아야 좌우가 어긋나지 않는다.
    """
    visible_month_count = min(max(month_count, 1), MONTH_SCROLL_THRESHOLD)
    classification_width = sum(classification_widths)
    label_column, month_column = st.columns(
        [classification_width, visible_month_count * MONTH_COLUMN_WIDTH_PX],
        gap=None,
    )
    with label_column:
        st.html(
            f"""
            <style>
            .st-key-{key}_label_canvas {{
                padding-top: {SCROLLBAR_HEIGHT_PX}px;
            }}
            </style>
            """
        )
        with st.container(key=f"{key}_label_canvas"):
            st.plotly_chart(
                label_figure,
                key=f"{key}_labels",
                width="stretch",
                config={"displayModeBar": False, "staticPlot": True},
            )
    with month_column:
        with st.container(key=f"{key}_month_region", gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{key}_month_scroll",
                height=SCROLLBAR_HEIGHT_PX,
                key=f"{key}_scrollbar",
            )
            with horizontal_scroll_canvas(
                key=f"{key}_month",
                content_width_px=month_count * MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
            ):
                st.plotly_chart(
                    month_figure,
                    key=f"{key}_months",
                    width="stretch",
                    config={"displayModeBar": False, "staticPlot": True},
                )
