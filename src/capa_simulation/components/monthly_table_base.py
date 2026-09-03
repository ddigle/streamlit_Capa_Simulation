# Purpose: 월별 Plotly 표 두 종류가 공유하는 색·치수·텍스트 계산과 스크롤 셸을 제공한다.

"""Shared pieces of the two monthly Plotly tables.

`grouped_monthly_table`(부분합 있는 환산 결과)과 `hierarchical_monthly_table`(합계 없는
상세 결과)은 서로 다른 표지만 고정 분류 영역 + 가로 스크롤 월 영역이라는 껍데기와 텍스트
폭 계산은 같다. 그 공통분만 여기 둔다.

격자·테두리 그리기(`_add_table_grid`, `_add_outer_border`)는 두 모듈에서 이미 동작이
갈라져 있어 합치지 않았다. 합치려면 어느 쪽 동작이 옳은지 먼저 정해야 한다.
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
CLASSIFICATION_MIN_WIDTH_PX = tokens.CLASSIFICATION_MIN_WIDTH_PX
CLASSIFICATION_MAX_WIDTH_PX = tokens.CLASSIFICATION_MAX_WIDTH_PX
CLASSIFICATION_TEXT_UNIT_PX = tokens.CLASSIFICATION_TEXT_UNIT_PX
CLASSIFICATION_HORIZONTAL_PADDING_PX = tokens.CLASSIFICATION_HORIZONTAL_PADDING_PX
MONTH_COLUMN_WIDTH_PX = tokens.MONTH_COLUMN_WIDTH_PX
MONTH_SCROLL_THRESHOLD = tokens.TABLE_MONTH_SCROLL_THRESHOLD
SCROLLBAR_HEIGHT_PX = tokens.SCROLLBAR_HEIGHT_PX
HEADER_HEIGHT_PX = tokens.TABLE_HEADER_HEIGHT_PX
ROW_HEIGHT_PX = tokens.TABLE_ROW_HEIGHT_PX


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
        month_figure_width = month_count * MONTH_COLUMN_WIDTH_PX
        st.html(
            f"""
            <style>
            .st-key-{key}_month_scroll {{
                overflow-x: auto;
                overflow-y: hidden;
                scrollbar-width: none !important;
                -ms-overflow-style: none;
            }}
            .st-key-{key}_month_scroll::-webkit-scrollbar {{
                width: 0 !important;
                height: 0 !important;
                display: none !important;
            }}
            .st-key-{key}_month_canvas {{
                width: {month_figure_width}px !important;
                min-width: {month_figure_width}px !important;
                max-width: none !important;
            }}
            </style>
            """
        )
        with st.container(key=f"{key}_month_region", gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{key}_month_scroll",
                height=SCROLLBAR_HEIGHT_PX,
                key=f"{key}_scrollbar",
            )
            with st.container(key=f"{key}_month_scroll"):
                with st.container(key=f"{key}_month_canvas"):
                    st.plotly_chart(
                        month_figure,
                        key=f"{key}_months",
                        width="stretch",
                        config={"displayModeBar": False, "staticPlot": True},
                    )
