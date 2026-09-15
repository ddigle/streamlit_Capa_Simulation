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


# 왼쪽 구분·분류 컬럼의 폭. 구획 제목("Capa LOB 현황")과 가장 긴 행 이름
# ("Density (억Gb)")이 함께 들어가는 값이다. 비율로 두면 창 폭과 조회 월 수에 따라
# 149px~618px 사이를 오가며 제목이 잘리거나 빈 여백이 생겼다.
DASHBOARD_LABEL_COLUMN_WIDTH_PX = 260

# 생산계획 LOB 의 B/N 막대 폭과 그 근거가 되는 `bargap`.
# Plotly 는 폭을 안 주면 `1 - bargap`(= 0.84) 으로 그린다. 그보다 좁게 두려면 값을 명시해야
# 하고, 증감 영역 trace 도 **같은 값**을 써야 한다 — overlay 모드에서는 trace 마다 제 x
# 위치만 보고 폭을 정하므로, 조정된 달이 흩어져 있으면 자동 폭이 몇 배로 튄다.
LOB_BARGAP = 0.16
LOB_BAR_WIDTH = (1 - LOB_BARGAP) * 0.75

# Top5 세로 막대의 폭과 테두리. overlay 모드에서 증감 trace 가 같은 폭을 **명시**해야
# 조정된 달이 흩어져 있을 때 폭이 제각각으로 튀지 않는다. 두 곳에 따로 적으면 조용히 갈린다.
TOP5_BAR_WIDTH = 0.15

# B/N Top 5 축의 위쪽 여유. 세워 둔 확보율 라벨이 들어갈 자리만 비우고 **남는 높이는
# 전부 막대가 쓴다.**
#
# 예전에는 `봉우리 × 1.8` 이라는 비율이었다. 비율은 행 높이를 바꿀 때마다 위쪽 공백이
# 같이 변하고, 확보율 구간을 200% 에서 잘라 여러 달이 같은 높이에 서면 라벨 위로 쓰지
# 않는 띠가 눈에 띄게 남는다. 그래서 **라벨이 실제로 먹는 픽셀**로 적는다.
#
# 잉크 길이는 회전한 글자의 **세로** 길이라 글자 수에 비례한다. 한 글자당 값은 브라우저
# 실측이다 — 15px 볼드 숫자 `228%` 네 글자가 34px 이었다.
#
# **글자 수를 상수로 박지 않는다.** 라벨은 밴드로 자르기 전의 원 확보율이라 상한을 200% 로
# 두어도 `1250%` 같은 긴 글자가 뜬다. 네 글자를 가정하고 고정값을 쓰면 그 순간 라벨이 행
# 밖으로 나가 위 구획을 침범한다. 그래서 축 여유는 그 화면에서 가장 긴 라벨에서 낸다.
TOP5_RATE_LABEL_GAP_PX = 10.0
TOP5_RATE_LABEL_CHAR_PX = 8.6
# 라벨 위에 남길 빈 자리. **실측으로 맞춘 값**이다 — Plotly 가 세운 주석을 `yshift` 보다
# 2.1px 더 띄우고 글자 상자도 `TOP5_RATE_LABEL_CHAR_PX` 추정보다 조금 좁아서, 이 상수에서
# 약 1.5px 를 뺀 만큼이 화면에 남는다. 4.5 → 브라우저에서 잰 빈 자리 3px.
TOP5_RATE_LABEL_MARGIN_PX = 4.5
# 라벨이 하나도 없을 때 쓰는 글자 수. `100%` 네 글자다.
TOP5_RATE_LABEL_MIN_CHARS = 4


def top5_axis_headroom_px(longest_label_chars: int) -> float:
    """Top5 축 위에 비워 둘 픽셀. 막대 끝에서 띄우는 틈 + 라벨 잉크 + 숨 쉴 틈."""
    chars = max(int(longest_label_chars), TOP5_RATE_LABEL_MIN_CHARS)
    return TOP5_RATE_LABEL_GAP_PX + chars * TOP5_RATE_LABEL_CHAR_PX + TOP5_RATE_LABEL_MARGIN_PX


# B/N Top5 의 `Wafer Capa` 레이블만 받는 가로 보정. 같은 x 를 쓰는 확보율 레이블은 `<b>`
# 굵은 글자라 글꼴 상자 폭이 달라, 보정을 공유하면 한쪽이 치우친다.
TOP5_WAFER_LABEL_XSHIFT_PX = -1.0
TOP5_BAR_OUTLINE_WIDTH_PX = 0.8

# LOB 세로 막대의 테두리 굵기. 상세 B/N 의 가로막대(BAR_OUTLINE_WIDTH_PX)보다 조금 굵다 —
# 막대가 크고 면색이 진해 같은 굵기면 테두리가 묻힌다.
LOB_BAR_OUTLINE_WIDTH_PX = 1.2

DASHBOARD_SECTION_GAP_PX = 16

DASHBOARD_TITLE_HEIGHT_PX = 44

# 테두리 상자가 `Capa LOB 현황` 제목 줄과 두 칸을 함께 감쌀 때 그 사이 간격.
# 라벨 캔버스는 월 칸 스크롤바 높이만큼 `padding-top` 으로 이미 내려와 있다. 제목 아래
# 간격이 다른 두 구획과 같은 `DASHBOARD_SECTION_GAP_PX` 로 보이려면 그만큼 뺀 값만
# 상자 gap 으로 준다. 손으로 적지 않고 두 값의 차로 둬야 한쪽을 고칠 때 따라 움직인다.
DASHBOARD_PANEL_TITLE_GAP_PX = DASHBOARD_SECTION_GAP_PX - tokens.SCROLLBAR_HEIGHT_PX

# 상세 B/N 공정 시트. 한 칸에는 가로막대 한 줄과 그 위의 공정명만 들어가고, 순위 20행이
# 한 화면에 담기는 행 높이다. 세 값은 Figure 높이·표 높이·행 경계 계산이 함께 보므로
# 한 곳에서만 정의한다.
BOTTLENECK_DETAIL_HEADER_HEIGHT_PX = 36

BOTTLENECK_DETAIL_ROW_HEIGHT_PX = 29

BOTTLENECK_DETAIL_BAR_HEIGHT_PX = 22

# 주요공정 확보율 히트맵 시트. 상세 B/N 과 **같은** 머리글·행 높이를 쓴다 — 두 구획이
# 세로로 나란히 서므로 행 리듬이 다르면 한쪽만 눌린 표로 읽힌다.
# `components/securement_heatmap.py` 의 20px 는 66공정을 한 화면에 넣으려는 **다른 화면**
# 의 값이라 여기 가져오지 않는다.
KEY_PROCESS_HEADER_HEIGHT_PX = BOTTLENECK_DETAIL_HEADER_HEIGHT_PX

KEY_PROCESS_ROW_HEIGHT_PX = BOTTLENECK_DETAIL_ROW_HEIGHT_PX

# 칸을 행보다 낮게 그린다. 위아래에 드러나는 띠가 연간 Total·과거 구간의 면색을 보여
# 주는 자리다 — 칸이 행을 꽉 채우면 그 열이 눌린 색이라는 것이 안 보인다.
KEY_PROCESS_CELL_HEIGHT_PX = BOTTLENECK_DETAIL_BAR_HEIGHT_PX

# 월 열 안에서 칸이 비우는 좌우 여백 비율. 세로 월 경계선이 칸에 가려지지 않게 한다.
KEY_PROCESS_CELL_SIDE_INSET_RATIO = 0.02

# 칸 안 확보율 글자와 왼쪽 공정명 글자. 색만으로 뜻을 나르지 않으려면 칸마다 숫자가
# 있어야 한다(색각이상·흑백 인쇄).
KEY_PROCESS_RATE_FONT_SIZE_PX = 13
KEY_PROCESS_NAME_FONT_SIZE_PX = 13

# 라벨 칸에서 공정명이 시작하는 왼쪽 여백.
KEY_PROCESS_NAME_INSET_PX = 10

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
