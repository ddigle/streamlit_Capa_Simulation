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
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 테스트가 스크롤바를 갈아끼울 수 있도록 이름이 아니라 모듈을 잡는다. 이름을 직접
# import 하면 여기서 잡은 바인딩이 교체를 무시한다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.process_labels import apply_process_label
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

# 색과 치수는 design/tokens.py 가 단일 근거다. 여기서는 표 문맥의 이름만 붙인다.
TRANSPARENT_COLOR = tokens.TRANSPARENT

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


def header_label(value: str) -> str:
    """표 머리글에 넣을 문자열을 만든다.

    `<b>` 를 붙이면 plotly 의 table trace 가 "일단 그린 다음 DOM 을 재서 가운데로 옮기는"
    경로(`needsConvertToTspans`)로 내려간다. 그 경로는 잰 폭으로만 가로 위치를 잡으므로
    잴 수 없는 상황에서 폭이 0 이면 글자가 셀 중앙에서 글자 폭의 절반만큼 밀린다. 그런데
    이 경로는 **세로로는 셀 높이에 맞춰 가운데** 놓는다. `<b>` 를 빼면 측정이 필요 없는
    경로로 내려가 가로는 언제나 정확하지만, 세로가 셀 위쪽에 고정되어 36px 머리글 밴드에서
    글자가 4.5px 위로 붙는다(실측). 밴드를 낮추지 않는 한 둘을 같이 얻을 수 없어, 보기에
    나은 쪽인 `<b>` 를 유지하고 가로 어긋남은 **숨겨진 채로 그리지 않는 것**으로 막는다.
    `components/tab_state.py` 가 그 규칙을 갖고 있다.

    공백은 줄바꿈 없는 공백으로 바꾼다. 공백이 있으면 plotly 가 한 겹 더 나쁜 줄바꿈
    경로로 내려가 숨겨진 상태에서 글자가 통째로 비기도 한다. 분류 셀 값은 이미 같은
    치환을 하고 있어 머리글만 규칙이 달랐다. 화면에 보이는 모양은 같다.
    """
    return f"<b>{value.replace(' ', chr(0xA0))}</b>"


def display_text(value: object) -> str:
    """Plotly 셀에 넣을 표시 문자열로 바꾼다. 결측은 빈 칸으로 둔다."""
    return "" if bool(pd.isna(cast(Any, value))) else str(value)


def display_value_text(value: object, labels: Mapping[str, str] | None) -> str:
    """분류 셀의 표시 문자열. 표시명 매핑이 있으면 그 컬럼에만 적용한다.

    치환은 여기(렌더 계층)에서만 한다. 프레임 값은 그대로 두므로 정렬·그룹 판정과 CSV
    내보내기가 쓰는 원본은 바뀌지 않는다.
    """
    text = display_text(value)
    if not labels or not text:
        return text
    return apply_process_label(value, labels)


# Plotly `go.Table` 은 칸 글자에 `&`·`<`·`>` 가 하나라도 있으면 HTML 해석 경로로 넘어가
# **그 행만** 높이 바닥을 올린다. 브라우저 실측으로 27px → 35px 였다. 격자와 그룹 경계선은
# 행 높이가 균일하다는 전제로 paper 좌표에 그리므로, 그런 행 하나가 그 아래 전부를 8px 씩
# 밀어낸다. 공정 표시명에 `&` 가 둘 있으면 반 칸이 밀리고 그 상태가 표 끝까지 유지된다.
#
# `&amp;` 로 이스케이프해도 같은 경로를 탄다(실측). 그래서 **글자 자체를 전각으로 바꾼다** —
# 전각 셋은 높이를 올리지 않는 것까지 확인했다. 공백을 U+00A0 으로 바꾸는 것과 같은 자리·
# 같은 이유다: 치환은 렌더 계층에서만 하고 프레임 값은 건드리지 않는다.
CELL_TEXT_SUBSTITUTIONS: Final[tuple[tuple[str, str], ...]] = (
    (" ", " "),
    ("&", "＆"),
    ("<", "＜"),
    (">", "＞"),
)


def classification_cell_text(value: object, labels: Mapping[str, str] | None) -> str:
    """분류 셀에 그대로 넣을 글자. 행 높이를 흔드는 문자를 렌더 계층에서만 바꾼다."""
    text = display_value_text(value, labels)
    for source, target in CELL_TEXT_SUBSTITUTIONS:
        text = text.replace(source, target)
    return text


def restore_cell_text(text: str) -> str:
    """`classification_cell_text` 의 치환을 되돌린다. CSV 는 원본 글자여야 한다.

    원본에 전각 `＆` 가 들어 있으면 반각으로 바뀐다. U+00A0 치환이 이미 같은 성질을 갖고
    있고(진짜 NBSP 도 공백이 된다), 화면 글자를 그대로 내보내 Excel VLOOKUP 이 어긋나는
    쪽이 더 나쁘다고 보아 같은 선택을 유지한다.
    """
    for source, target in CELL_TEXT_SUBSTITUTIONS:
        text = text.replace(target, source)
    return text


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
            line={"color": tokens.BORDER_STRONG, "width": OUTER_BORDER_WIDTH_PX * 2},
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
        line={"color": tokens.BORDER_STRONG, "width": OUTER_BORDER_WIDTH_PX},
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
            line={"color": tokens.BORDER, "width": GRID_LINE_WIDTH_PX},
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
                "color": tokens.BORDER_STRONG if is_quarter_boundary else tokens.BORDER,
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
    owner_tab: OpenTab | None = None,
) -> None:
    """고정 분류 영역과 가로 스크롤 월 영역을 나란히 렌더링한다.

    월 영역의 네이티브 스크롤바는 숨기고 `horizontal_scrollbar` 컴포넌트로 대체한다.
    두 Figure 의 행 높이가 같아야 좌우가 어긋나지 않는다.

    `owner_tab` 이 닫혀 있으면 아무것도 그리지 않는다. 숨겨진 요소 안에서는 SVG 글자 폭
    측정이 0 이라 `go.Table` 이 헤더를 셀 가운데에 놓지 못하고, `staticPlot` 이라 나중에
    보이게 되어도 다시 그리지 않아 어긋난 채로 남는다. 탭이 열리면 rerun 이 돌아 그때
    보이는 상태로 그린다.
    """
    if tab_is_hidden(owner_tab):
        return
    visible_month_count = min(max(month_count, 1), MONTH_SCROLL_THRESHOLD)
    classification_width = sum(classification_widths)
    # 분류 폭은 px 로 계산한 값이다. 비율로만 넘기면 창이 좁을 때 함께 줄어 분류 이름이
    # 잘리므로 CSS 로 px 를 못박는다. 비율은 CSS 가 적용되기 전 첫 그리기용이다.
    st.html(
        split_scroll_columns_style(
            label_key=f"{key}_label_canvas",
            month_key=f"{key}_month_region",
            label_width_px=classification_width,
        )
    )
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
