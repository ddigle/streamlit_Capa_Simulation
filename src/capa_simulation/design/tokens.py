# Purpose: 화면 색·서체·표 치수를 역할 이름으로 단일 정의한다.

"""Role-named design tokens shared by every page, table, and chart.

`.streamlit/config.toml`의 `[theme]`가 선언한 값이 이 모듈의 근거다. 파이썬 코드에 색
리터럴을 직접 쓰면 두 곳이 조용히 갈라지므로(실제로 갈라져 있었다) 화면 코드는 여기의
토큰만 참조한다.

토큰 이름은 **역할**이다. 값이 같아도 역할이 다르면 다른 이름을 쓴다. 예를 들어
`BORDER`와 `STATUS_SECURE`는 현재 둘 다 zinc-300이지만, 확보 상태색을 조정할 때
표 테두리가 함께 바뀌어서는 안 된다.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------- 면과 텍스트
# config.toml [theme] 와 1:1 대응한다.
# 페이지 바탕을 살짝 눌러(`#F7F8FA`) 표와 카드의 흰 면이 떠 보이게 한다. 밀도 높은
# 화면에서 어디까지가 한 덩어리인지 테두리에만 의존하지 않고 읽히게 하려는 것이다.
SURFACE: Final = "#FFFFFF"  # 표·카드 면. secondaryBackgroundColor
SURFACE_PAGE: Final = "#F7F8FA"  # backgroundColor. 카드가 뜨는 바탕
SURFACE_SUBTLE: Final = "#FAFAFB"
SURFACE_CLASSIFICATION: Final = "#F1F3F6"
SURFACE_CLASSIFICATION_GROUP: Final = "#E5E8EC"
HEADER_BACKGROUND: Final = "#E4E7EB"  # dataframeHeaderBackgroundColor
# 화면 맨 위 띠의 면. 페이지 바탕보다 한 단계만 눌러 앱 머리와 본문을 나눈다. 표 머리글
# (HEADER_BACKGROUND)보다는 밝아야 표의 위계를 침범하지 않는다.
HEADER_BAR: Final = "#EFF1F5"
# Plotly Figure 의 paper·plot 바탕. 모든 Figure 는 배경이 투명한 `st.container(border=True)`
# 안에 놓여 페이지 바탕 위에 그려지므로, 흰 면(SURFACE)을 쓰면 Figure 만 흰 사각형으로 뜬다.
CHART_CANVAS: Final = SURFACE_PAGE

BORDER: Final = "#DDE0E5"  # borderColor
BORDER_STRONG: Final = "#A3A9B2"
TEXT: Final = "#18181B"  # textColor
TEXT_MUTED: Final = "#646973"  # grayColor
LINE: Final = "#3F3F46"  # 표 격자·계열선. 강조색과 역할이 다르다
ACCENT: Final = "#0F766E"  # primaryColor. 버튼·포커스 등 상호작용 표시

# ------------------------------------------------------------------- 부분합 면
# 환산 결과표의 제품 Total → 양산구분 Total → 전체 합계로 갈수록 짙어진다.
SURFACE_PRODUCT_TOTAL: Final = "#F0F1F2"
CLASSIFICATION_PRODUCT_TOTAL: Final = "#DDE0E3"
SURFACE_PRODUCTION_TOTAL: Final = "#E2E4E7"
CLASSIFICATION_PRODUCTION_TOTAL: Final = "#CCD0D4"
SURFACE_GRAND_TOTAL: Final = "#D2D5D9"
CLASSIFICATION_GRAND_TOTAL: Final = "#B9BEC4"

# --------------------------------------------------------------------- 상태색
# 확보 → 경고 → 부족 순으로 **휘도가 단조 감소**해야 한다. 그래야 흑백 출력과 색각
# 이상에서도 심각도 순서가 읽힌다. 이전 팔레트는 경고(0.793)가 확보(0.660)보다 밝아
# 순서가 거꾸로 읽혔다. 현재 값의 휘도는 0.660 → 0.414 → 0.236이고 세 색 모두 검은
# 글자와 4.8:1 이상의 대비를 갖는다.
STATUS_SECURE: Final = "#D4D4D8"
STATUS_WARNING: Final = "#FB923C"
STATUS_SHORTAGE: Final = "#F43F5E"

# --------------------------------------------------------- Dynamic Capa 계열색
# 표준 → 실효 → 실적으로 갈수록 밝아지는 단계 비교용이며 상태 판정과는 무관하다.
SERIES_STANDARD: Final = "#3F3F46"
SERIES_EFFECTIVE: Final = "#A1A1AA"
SERIES_ACTUAL: Final = "#71717A"

# ------------------------------------------------------------------ 재공 격자색
WIP_HELD: Final = "#A1A1AA"
WIP_INFLOW: Final = "#60A5FA"
WIP_FLOW_MET: Final = "#34D399"
WIP_FLOW_SHORT: Final = "#FB7185"
WIP_FLOW_UNSET: Final = "#A78BFA"

# ----------------------------------------------------------- 설비 생애주기 상태
# `EQUIPMENT_STATUSES` 9종 전부에 색을 준다. 명시 scale 없이 Altair 에 넘기면
# config.toml 의 chartCategoricalColors 4색을 순환해 5~9번째 상태가 앞의 것과 같은
# 색으로 그려진다. 앞 7개는 기존 Space 배치도 색을 그대로 유지하고, 종료된 두 상태는
# 무채색으로 눌러 진행 중인 상태와 구분한다.
EQUIPMENT_STAGE_COLORS: Final[dict[str, str]] = {
    "입고 예정": "#93C5FD",
    "셋업 진행중": "#FDBA74",
    "가용": "#86EFAC",
    "반출 예정": "#FDE68A",
    "이설 예정": "#C4B5FD",
    "보관 설비": "#CBD5E1",
    "운영 비가동": "#FCA5A5",
    "반출 완료": "#A1A1AA",
    "이설 완료": "#71717A",
}
EQUIPMENT_STAGE_FALLBACK: Final = "#E5E7EB"

# Qual 실행관리 상태. 계획 → 확정 → 완료로 갈수록 짙어지고 지연만 경고색이다.
QUAL_CONFIRMATION_COLORS: Final[dict[str, str]] = {
    "계획": "#CBD5E1",
    "확정": "#93C5FD",
    "완료": "#86EFAC",
    "지연": STATUS_WARNING,
}

# 실행관리 일정 상태. 재공 격자의 충족·유입색과 같은 값을 써서 시각 언어를 맞춘다.
SCHEDULE_DONE: Final = WIP_FLOW_MET
SCHEDULE_PLANNED: Final = WIP_INFLOW

# ------------------------------------------------------------- Space 배치도 전용
# FAB 도면은 zinc 계열이 아니라 자체 blue-grey 를 쓴다. 도면 관례에 맞춘 의도적인
# 하위 팔레트이며 표·차트와 섞어 쓰지 않는다.
SPACE_CANVAS: Final = "#F7F8FA"


def _with_alpha(hex_color: str, alpha: float) -> str:
    """`#RRGGBB` 토큰에서 반투명 rgba 를 만든다. 손으로 옮겨 적으면 원 토큰과 갈라진다."""
    red, green, blue = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"


# 배경 도면 위에 캔버스를 덮을 때. SPACE_CANVAS 를 바꾸면 함께 바뀐다.
SPACE_CANVAS_OVERLAY: Final = _with_alpha(SPACE_CANVAS, 0.18)
SPACE_BORDER: Final = "#59636E"
SPACE_TEXT: Final = "#20262E"
SPACE_LABEL_TEXT: Final = "#69727C"
SPACE_GRID: Final = "#E5E8EB"
SPACE_BUILDING_FILLS: Final[tuple[str, ...]] = (
    "#E7EDF2",
    "#F3F5F7",
    "#E9EDF1",
    "#F3F5F7",
    "#E9EDF1",
)

# ------------------------------------------------------------------ 스크롤바 색
SCROLLBAR_TRACK: Final = "#ECEEF1"
SCROLLBAR_THUMB: Final = "#8F9399"
SCROLLBAR_THUMB_HOVER: Final = "#686D73"
SCROLLBAR_THUMB_ACTIVE: Final = "#52565C"

# ------------------------------------------------------------------ 기술 상수
# 색이 아니라 "보이지 않게" 하는 값이다. 여기 두면 화면 코드의 rgba 리터럴 검사에 예외를
# 둘 필요가 없고, 같은 값을 손으로 다시 적다가 갈라지는 일도 없다.
TRANSPARENT: Final = "rgba(0, 0, 0, 0)"  # 격자·테두리 선을 지울 때
# Space 도면 위에 깔아 클릭·호버 표적으로 쓰는 마커. 눈에 띄지 않을 만큼만 칠한다.
# 알파를 바꾸면 Space 화면에서 동·층 클릭과 설비 호버가 살아 있는지 확인한다.
HIT_TARGET: Final = "rgba(255,255,255,0.01)"

# ----------------------------------------------------------------------- 서체
# Windows 전용 서체 하나만 지정하면 비Windows 클라이언트에서 서체와 컬럼 폭이 함께
# 깨진다. 폴백 스택을 반드시 함께 넘긴다.
FONT_FAMILY: Final = "Malgun Gothic, Pretendard, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"
FONT_FAMILY_NUMERIC: Final = "Calibri, " + FONT_FAMILY

# --------------------------------------------------------------------- 표 치수
TABLE_HEADER_HEIGHT_PX: Final = 36
TABLE_ROW_HEIGHT_PX: Final = 27
MONTH_COLUMN_WIDTH_PX: Final = 100
SCROLLBAR_HEIGHT_PX: Final = 10
OUTER_BORDER_WIDTH_PX: Final = 1.8
# 셀 사이를 나누는 얇은 격자선. 바깥 테두리·분기 경계보다 가늘어야 위계가 읽힌다.
GRID_LINE_WIDTH_PX: Final = 0.8
CLASSIFICATION_MIN_WIDTH_PX: Final = 84
CLASSIFICATION_MAX_WIDTH_PX: Final = 220
CLASSIFICATION_TEXT_UNIT_PX: Final = 15
CLASSIFICATION_HORIZONTAL_PADDING_PX: Final = 36

# BigDataQuery 시뮬레이션 코드 목록 전용 치수. 위의 월별표 치수를 재사용하지 않는다 —
# 그쪽은 Plotly 표 밀도에 묶여 있어 월별표 행 높이를 조정하면 이 목록까지 함께 움직인다.
# 고정 px 높이여야 표 '안에서' 세로 스크롤이 생긴다. 높이를 주지 않으면 행 수만큼
# 페이지가 길어져 목록이 수천 행일 때 화면을 못 쓴다.
CATALOG_LIST_ROW_HEIGHT_PX: Final = 30
CATALOG_LIST_VISIBLE_ROWS: Final = 12

# 가로 스크롤이 시작되는 월 수. 상세표와 HOME 대시보드가 서로 다른 값을 쓴다.
# 두 화면의 밀도가 달라 지금은 유지하되, 같은 개념이므로 여기서 함께 보이게 둔다.
TABLE_MONTH_SCROLL_THRESHOLD: Final = 8
DASHBOARD_MONTH_SCROLL_THRESHOLD: Final = 10
