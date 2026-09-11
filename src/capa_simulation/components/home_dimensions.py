# Purpose: HOME 대시보드 LOB 표·차트의 픽셀 치수를 정의한다.

"""HOME 대시보드 LOB 표·차트의 픽셀 치수를 정의한다."""

from __future__ import annotations

import math

from capa_simulation.design import tokens

# 값 글자와 증감(+-) 줄이 겹치지 않게 하는 최소 치수.
#
# 숫자 글리프는 글자 크기의 약 0.75 배만 세로를 쓴다. 줄 상자 전체(약 1.2 배)로 잡으면
# 필요 없는 여백까지 행에 얹혀 표가 두꺼워진다.
GLYPH_HEIGHT_RATIO = 0.75

# 값과 증감 글자 사이의 틈. 겹치지 않는 최소치라 더 줄이면 글자가 맞닿는다.
DELTA_GUTTER_PX = 2

# 행 경계선과 글자 사이의 틈. 0 이면 글자가 경계선에 붙어 읽힌다.
ROW_EDGE_PADDING_PX = 3


def delta_line_shift_px(value_font_size: int) -> float:
    """값 중심에서 증감 줄 중심까지의 거리."""
    half_glyphs = (value_font_size + tokens.DELTA_FONT_SIZE_PX) * GLYPH_HEIGHT_RATIO / 2
    return half_glyphs + DELTA_GUTTER_PX


def row_height_with_deltas(value_font_size: int) -> int:
    """증감 줄을 위·아래에 얹어도 값이 움직이지 않는 최소 행 높이.

    **증감이 있든 없든 이 높이를 쓴다.** 있을 때만 늘리면 토글을 누를 때마다 표가
    출렁이고, 값 글자를 줄여 끼워 넣으면 같은 행 안에서 숫자 크기가 들쭉날쭉해진다.
    둘 다 하지 않으려면 자리를 미리 비워 두는 수밖에 없다.
    """
    half = (
        delta_line_shift_px(value_font_size)
        + tokens.DELTA_FONT_SIZE_PX * GLYPH_HEIGHT_RATIO / 2
        + ROW_EDGE_PADDING_PX
    )
    return math.ceil(2 * half)


def stacked_row_height(value_font_size: int) -> int:
    """값 아래 한 줄만 증감을 놓는 칸의 최소 높이. 값은 언제나 위쪽 줄에 선다."""
    body = (value_font_size + tokens.DELTA_FONT_SIZE_PX) * GLYPH_HEIGHT_RATIO + DELTA_GUTTER_PX
    return math.ceil(body + 2 * ROW_EDGE_PADDING_PX)


DASHBOARD_SCROLLBAR_HEIGHT_PX = 15

# 왼쪽 구분·분류 컬럼의 폭. 구획 제목("Capa LOB 현황")과 가장 긴 행 이름
# ("Density (억Gb)")이 함께 들어가는 값이다. 비율로 두면 창 폭과 조회 월 수에 따라
# 149px~618px 사이를 오가며 제목이 잘리거나 빈 여백이 생겼다.
DASHBOARD_LABEL_COLUMN_WIDTH_PX = 260

DASHBOARD_SECTION_GAP_PX = 16

DASHBOARD_TITLE_HEIGHT_PX = 44

# 상세 B/N 공정 시트. 한 칸에는 가로막대 한 줄과 그 위의 공정명만 들어가고, 순위 20행이
# 한 화면에 담기는 행 높이다. 세 값은 Figure 높이·표 높이·행 경계 계산이 함께 보므로
# 한 곳에서만 정의한다.
BOTTLENECK_DETAIL_HEADER_HEIGHT_PX = 36

BOTTLENECK_DETAIL_ROW_HEIGHT_PX = 29

BOTTLENECK_DETAIL_BAR_HEIGHT_PX = 22

LOB_TABLE_HEADER_HEIGHT_PX = 45

# 값 글자 크기. 세 행이 같고, 행 높이 계산이 이 값을 본다.
LOB_VALUE_FONT_SIZE_PX = 20

# Density·Wafer 계획만 증감을 얹는다(선행은 위, 비교 GAP 은 아래). 두 줄 자리를 미리
# 비워 두어야 토글을 눌러도 숫자가 그대로 있다.
LOB_DENSITY_ROW_HEIGHT_PX = row_height_with_deltas(LOB_VALUE_FONT_SIZE_PX)

LOB_WAFER_PLAN_ROW_HEIGHT_PX = LOB_DENSITY_ROW_HEIGHT_PX

# Wafer Capa 는 증감을 적지 않는다 — 설비가 늘어난 것이 아니므로 비교할 것이 없다.
# 자리를 비워 둘 이유가 없어 예전 높이 그대로다.
LOB_WAFER_CAPA_ROW_HEIGHT_PX = 36

LOB_TABLE_ROW_HEIGHTS_PX = (
    LOB_TABLE_HEADER_HEIGHT_PX,
    LOB_DENSITY_ROW_HEIGHT_PX,
    LOB_WAFER_PLAN_ROW_HEIGHT_PX,
    LOB_WAFER_CAPA_ROW_HEIGHT_PX,
)

LOB_TABLE_HEIGHT_PX = sum(LOB_TABLE_ROW_HEIGHTS_PX)

LOB_CHART_HEIGHT_PX = 150

LOB_TOP5_HEIGHT_PX = 150

LOB_BOTTOM_MARGIN_PX = 130

# LOB 두 Figure 만 제목 자리를 쓰지 않는다. `Capa LOB 현황` 은 Plotly 주석이 아니라
# Streamlit 이 그려서 그 옆에 「선행」 토글을 둔다. 여백을 남겨 두면 표 위에 빈 띠가 생긴다.
LOB_TOP_MARGIN_PX = 0

LOB_FIGURE_HEIGHT_PX = (
    LOB_TOP_MARGIN_PX
    + LOB_TABLE_HEIGHT_PX
    + LOB_CHART_HEIGHT_PX
    + LOB_TOP5_HEIGHT_PX
    + LOB_BOTTOM_MARGIN_PX
)
