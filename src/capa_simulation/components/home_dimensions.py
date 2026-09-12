# Purpose: HOME 대시보드 LOB 표·차트의 픽셀 치수를 정의한다.

"""HOME 대시보드 LOB 표·차트의 픽셀 치수를 정의한다."""

from __future__ import annotations

import math

from capa_simulation.design import tokens

# 값 글자와 증감(+-) 줄을 나란히 놓기 위한 세로 지표.
#
# 글자는 글리프가 아니라 **줄 상자** 기준으로 놓인다. 줄 상자에는 글리프 아래로 내림선
# 자리가 더 있어서, 두 글자의 상자 가운데를 같은 간격으로 벌려도 위쪽 틈이 아래쪽보다
# 넓어 보인다. 그래서 상자가 아니라 **글리프 가운데**를 기준으로 계산하고, 상자 기준으로만
# 놓을 수 있는 Plotly 에는 그 차이를 `yshift` 로 돌려준다.
#
# 아래 네 비율은 Chrome 의 `TextMetrics` 로 두 서체를 재어 얻은 값이다(글자 크기 대비).
# `INK_HEIGHT` 는 숫자 글리프가 실제로 칠해지는 높이, `INK_OFFSET` 은 줄 상자 가운데보다
# 글리프 가운데가 아래로 내려앉는 거리다.
TEXT_INK_HEIGHT_RATIO = 0.80
TEXT_INK_OFFSET_RATIO = 0.125
NUMERIC_INK_HEIGHT_RATIO = 0.65
NUMERIC_INK_OFFSET_RATIO = 0.025

# Plotly 표 칸의 세로 치수. **칸 높이를 글자보다 작게 주면 Plotly 는 칸을 늘려 버린다.**
# 그러면 Figure 높이 계산과 실제 그림이 어긋나 표가 아래 구획을 덮는다. 그래서 필요한
# 높이를 여기서 미리 낸다.
#
# `LINE_BOX_RATIO` 는 한 줄이 차지하는 상자 높이, `TABLE_CELL_PADDING_PX` 는 Plotly 가
# 글자 위아래에 두는 여백의 합, `TABLE_TEXT_TOP_PAD_PX` 는 그 여백 중 **위쪽 몫**이다.
# 여백은 반씩 나뉘지 않는다 — 한 줄짜리 칸의 글자는 위에 붙어 그려진다. 셋 다 Chrome 에서
# 그려 본 값이다.
LINE_BOX_RATIO = 1.45
TABLE_CELL_PADDING_PX = 16
TABLE_TEXT_TOP_PAD_PX = 2.5

# 값과 증감 글리프 사이의 틈. 겹치지 않는 최소치라 더 줄이면 글자가 맞닿는다.
DELTA_GUTTER_PX = 2

# 행 경계선과 글자 사이의 틈. 0 이면 글자가 경계선에 붙어 읽힌다.
ROW_EDGE_PADDING_PX = 3


def delta_line_shift_px(value_font_size: int) -> float:
    """값 글리프 가운데에서 증감 글리프 가운데까지의 거리."""
    half_glyphs = (
        value_font_size * TEXT_INK_HEIGHT_RATIO
        + tokens.DELTA_FONT_SIZE_PX * NUMERIC_INK_HEIGHT_RATIO
    ) / 2
    return half_glyphs + DELTA_GUTTER_PX


def value_ink_yshift_px(value_font_size: int) -> float:
    """값 글리프 가운데를 칸 한가운데에 맞추는 `yshift`."""
    return value_font_size * TEXT_INK_OFFSET_RATIO


def delta_ink_yshift_px() -> float:
    """증감 글리프 가운데를 목표 자리에 맞추는 `yshift` 보정."""
    return tokens.DELTA_FONT_SIZE_PX * NUMERIC_INK_OFFSET_RATIO


def row_height_with_deltas(value_font_size: int) -> int:
    """증감 줄을 위·아래에 얹어도 값이 움직이지 않는 최소 행 높이.

    **증감이 있든 없든 이 높이를 쓴다.** 있을 때만 늘리면 토글을 누를 때마다 표가
    출렁이고, 값 글자를 줄여 끼워 넣으면 같은 행 안에서 숫자 크기가 들쭉날쭉해진다.
    둘 다 하지 않으려면 자리를 미리 비워 두는 수밖에 없다.
    """
    half = (
        delta_line_shift_px(value_font_size)
        + tokens.DELTA_FONT_SIZE_PX * NUMERIC_INK_HEIGHT_RATIO / 2
        + ROW_EDGE_PADDING_PX
    )
    return math.ceil(2 * half)


def table_row_height(value_font_size: int) -> int:
    """값 한 줄만 있는 표 칸의 높이."""
    return math.ceil(value_font_size * LINE_BOX_RATIO + TABLE_CELL_PADDING_PX)


def lower_delta_yshift_px(value_font_size: int) -> float:
    """표 칸 **위 모서리** 기준으로 값 아래 증감 줄을 놓는 `yshift`.

    Plotly 표는 한 줄짜리 칸의 글자를 가운데가 아니라 **위에 붙여** 놓는다(`valign` 은
    두 줄 이상일 때만 듣는다). 그래서 기준을 칸 한가운데로 잡으면 행 높이를 바꿀 때마다
    증감이 값에서 멀어진다. 위 모서리에서 재면 행 높이와 무관하게 같은 거리를 지킨다.
    """
    value_box_center = TABLE_TEXT_TOP_PAD_PX + value_font_size * LINE_BOX_RATIO / 2
    return -(
        value_box_center
        + value_ink_yshift_px(value_font_size)
        + delta_line_shift_px(value_font_size)
        - delta_ink_yshift_px()
    )


def lower_delta_row_height(value_font_size: int) -> int:
    """값 한 줄과 그 아래 증감 한 줄이 들어가는 표 칸의 높이.

    증감이 없어도 이 높이를 쓴다. 있을 때만 늘리면 토글 하나에 표 전체가 출렁인다.

    증감을 `<br>` 다음 줄로 적으면 Plotly 가 **줄 상자 두 개에 고정 여백 16px** 을 더한
    높이를 요구해 52px 아래로 내려가지 않는다. 값을 한 줄로 두고 증감을 주석으로 얹으면
    그 바닥이 사라지고, 남는 것은 한 줄짜리 칸의 최소 높이뿐이다.
    """
    needed = (
        -lower_delta_yshift_px(value_font_size)
        + tokens.DELTA_FONT_SIZE_PX * NUMERIC_INK_HEIGHT_RATIO / 2
        + ROW_EDGE_PADDING_PX
    )
    return max(math.ceil(needed), table_row_height(value_font_size))


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

# Wafer Capa 는 증감을 적지 않지만 높이는 같이 맞춘다. 세 행의 띠 높이가 다르면 증감과
# 무관하게 표가 한쪽만 눌린 것처럼 보인다.
LOB_WAFER_CAPA_ROW_HEIGHT_PX = LOB_DENSITY_ROW_HEIGHT_PX

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

# Plotly 가 좌표 1.0 을 재는 기준 높이. paper 좌표는 **여백을 뺀 그림 영역** 기준이라
# 그림 전체 높이로 나누면 어긋난다.
LOB_PLOT_AREA_HEIGHT_PX = LOB_FIGURE_HEIGHT_PX - LOB_TOP_MARGIN_PX - LOB_BOTTOM_MARGIN_PX

# 패널 아래 테두리·세로 격자가 내려오는 paper 좌표. 아래 여백까지 감싸야 B/N Top 5 의
# 축 글자가 테두리 안에 들어오므로 0 이 아니라 그림의 맨 아랫줄이다.
#
# **비율을 손으로 적지 않는다.** 행 높이를 한 번 올리면 그림 영역이 함께 커져서 같은
# 비율이 캔버스 밖으로 밀려나고, 아래 테두리가 그려지기는 하되 잘려서 통째로 사라진다.
LOB_PANEL_BOTTOM_Y = -LOB_BOTTOM_MARGIN_PX / LOB_PLOT_AREA_HEIGHT_PX
