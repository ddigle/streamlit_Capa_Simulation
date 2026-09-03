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
SURFACE: Final = "#FFFFFF"  # backgroundColor
SURFACE_SUBTLE: Final = "#FAFAFA"
SURFACE_CLASSIFICATION: Final = "#F4F4F5"  # secondaryBackgroundColor
SURFACE_CLASSIFICATION_GROUP: Final = "#EAEBED"
HEADER_BACKGROUND: Final = "#E4E4E7"  # dataframeHeaderBackgroundColor
BORDER: Final = "#D4D4D8"  # borderColor
BORDER_STRONG: Final = "#A1A1AA"
TEXT: Final = "#18181B"  # textColor
TEXT_MUTED: Final = "#71717A"  # grayColor
LINE: Final = "#3F3F46"  # primaryColor

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
CLASSIFICATION_MIN_WIDTH_PX: Final = 84
CLASSIFICATION_MAX_WIDTH_PX: Final = 220
CLASSIFICATION_TEXT_UNIT_PX: Final = 15
CLASSIFICATION_HORIZONTAL_PADDING_PX: Final = 36

# 가로 스크롤이 시작되는 월 수. 상세표와 HOME 대시보드가 서로 다른 값을 쓴다.
# 두 화면의 밀도가 달라 지금은 유지하되, 같은 개념이므로 여기서 함께 보이게 둔다.
TABLE_MONTH_SCROLL_THRESHOLD: Final = 8
DASHBOARD_MONTH_SCROLL_THRESHOLD: Final = 10
