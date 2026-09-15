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

# ------------------------------------------------------------- 연간 Total 열 면색
# 월 칸과 같은 표 안에 있지만 성격이 다르다는 것을 색으로만 알린다. 테두리를 더하면
# 월 칸 격자와 경쟁해 표가 시끄러워진다. 면색 대비는 월 칸 대비 1.05:1 로 얕게 둔다 —
# 짙게 하면 합계 열이 본문보다 먼저 읽힌다.
SURFACE_YEAR_TOTAL: Final = "#EFF1F3"
SURFACE_CLASSIFICATION_YEAR_TOTAL: Final = "#E3E6E9"

# ------------------------------------------------------------------ 과거 구간 면색
# Past Data 로 채운 달의 열 바탕. 그 열의 값은 DB 계산 결과가 아니라 입력해 둔 지난
# 이력이라 GAP 도 적지 않는다 — 면색이 그 경계를 말한다.
#
# **한 단계 눌러 만든 짝이다.** 월 칸은 줄무늬(SURFACE·SURFACE_SUBTLE)와 연간 Total 로
# 이미 세 가지 면을 쓰므로, 과거 전용 색 하나를 덧칠하면 그 안의 위계가 사라진다. 각
# 바탕색마다 대응하는 어두운 짝을 두어 줄무늬와 합계 칸이 과거 구간에서도 그대로 읽힌다.
# 흰 면 대비 1.23:1 로 띠의 경계가 보이면서 본문 글자와는 12:1 이 넘어 값 가독성은 그대로다.
SURFACE_PAST: Final = "#E3E8EF"
SURFACE_PAST_SUBTLE: Final = "#DEE3EB"
SURFACE_PAST_YEAR_TOTAL: Final = "#D3D9E2"

# ------------------------------------------------------------------ 증감 표기색
# 선행 반영 전후의 차이를 값 위에 작게 적을 때 쓴다. 좋고 나쁨이 아니라 방향 표시라
# 상태색(확보·경고·부족)을 재사용하지 않는다 — 재사용하면 계획이 늘어난 달이 그대로
# "부족" 으로 읽힌다. 둘 다 흰 면에서 검은 글자 대비 기준을 넘긴다.
DELTA_INCREASE: Final = "#B45309"
DELTA_DECREASE: Final = "#1D4ED8"

# --------------------------------------------------------------- 실행 증감 면색
# 실행 Capa 반영으로 확보율이 줄거나 늘어난 **구간 자체**를 칠하는 면색이다. 위의
# `DELTA_*` 는 값 위에 작게 적는 **글자색**이라 역할이 다르고, 면색으로 쓰면 막대 안에서
# 글자보다 무거워진다. 두 이름을 나눠 두는 이유가 그것이다.
#
# 이 면들은 막대 트랙(BAR_TRACK) 위에 얹히므로 거기서 먼저 떨어져야 한다.
#   감소 pink-300  : 트랙 1.43:1 · 부족막대 2.02:1 · 검은 글자 9.77:1
#   증가 lime-500  : 트랙 1.56:1 · 확보막대 1.34:1 · 검은 글자 8.97:1
# 더 밝은 lime-400(#A3E635)은 「밝은 연두」에 가깝지만 휘도가 `STATUS_SECURE` 와 1.02:1 로
# 사실상 같다 — 확보 상태 막대 옆에 붙으면 흑백·색각이상에서 경계가 사라진다.
# 상태색 3종의 휘도 단조 검사와는 무관하다(그 검사는 `STATUS_*` 셋만 본다).
DELTA_AREA_DECREASE: Final = "#F9A8D4"
DELTA_AREA_INCREASE: Final = "#84CC16"

# 가로막대의 바탕 트랙. 막대 길이 눈금(80~150%)의 전체 구간을 보여준다. 표 머리글·
# 스크롤바 트랙과 값이 비슷하지만 역할이 다르므로 별도 토큰이다.
# 트랙이 먼저 셀 면(SURFACE)에서 분리돼야 눈금 구간이 보인다: 대비 1.27:1.
# 그 위의 "확보" 막대(STATUS_SECURE)와는 1.17:1 뿐이라 면색만으로는 부족하고,
# 막대 테두리(LINE, 트랙 대비 8.25:1)가 BAR_OUTLINE_WIDTH_PX 굵기로 경계를 만든다.
BAR_TRACK: Final = "#E1E5EA"

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


# 사이드바 네비게이션의 "지금 여기" 표시. 이 앱에서 그림자를 쓰는 유일한 자리다 —
# 화면 어디에도 융기가 없기 때문에 사이드바에서만 쓰면 그 자체가 신호가 된다.
# 링은 ACCENT 라 색이고, 그림자는 TEXT 라 깊이다. 둘을 한 토큰으로 합치지 않는다.
# HOME 은 사이드바의 귀환점이라 누르지 않았을 때도 보여야 한다. 옅은 틴트 + ACCENT
# 테두리로 윤곽선 버튼을 만들고, 지금 HOME 에 있으면 융기 규칙이 그 위에 얹혀 채워진
# 모양이 된다 — 윤곽선에서 채움으로 가는 흔한 단계다.
NAV_HOME_TINT: Final = _with_alpha(ACCENT, 0.07)
NAV_ACTIVE_RING: Final = _with_alpha(ACCENT, 0.14)
NAV_SHADOW: Final = _with_alpha(TEXT, 0.10)

# 기준선과 실적선 사이를 칠하는 옅은 면. 위의 `DELTA_AREA_*` 는 막대 트랙 위에 얹혀
# 트랙과 구분돼야 하지만, 이 면은 선 두 개 사이를 채우기만 하면 되므로 같은 세기로 칠하면
# 정작 읽어야 할 선이 면에 묻힌다.
GAP_AREA_SHORTFALL: Final = _with_alpha(DELTA_AREA_DECREASE, 0.35)

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
FONT_FAMILY: Final = "Noto Sans KR, Malgun Gothic, 'Apple SD Gothic Neo', sans-serif"
FONT_FAMILY_NUMERIC: Final = "Calibri, " + FONT_FAMILY

# 증감(+-) 표기는 화면 어디에서나 이 한 크기를 쓴다. 표 칸 12, 막대 13, 세부수량 10 으로
# 갈려 있던 탓에 같은 뜻의 글자가 자리마다 달라 보였다.
DELTA_FONT_SIZE_PX: Final = 12

# --------------------------------------------------------------------- 표 치수
TABLE_HEADER_HEIGHT_PX: Final = 36
TABLE_ROW_HEIGHT_PX: Final = 27
MONTH_COLUMN_WIDTH_PX: Final = 100
SCROLLBAR_HEIGHT_PX: Final = 10
OUTER_BORDER_WIDTH_PX: Final = 1.8
# 셀 사이를 나누는 얇은 격자선. 바깥 테두리·분기 경계보다 가늘어야 위계가 읽힌다.
GRID_LINE_WIDTH_PX: Final = 0.8
# 묶음(제품 그룹·구획)을 가르는 선. 격자선보다는 굵고 바깥 테두리보다는 가늘다.
GROUP_BORDER_WIDTH_PX: Final = 1.4
# 트랙 위에 얹히는 가로막대의 테두리. 면색만으로는 "확보" 막대와 트랙의 대비가
# 1.17:1 뿐이라 막대의 끝이 어디인지 이 선이 정한다. 격자선보다 굵어야 셀 안에서
# 막대가 격자에 묻히지 않는다.
BAR_OUTLINE_WIDTH_PX: Final = 1.0
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
