# Purpose: 화면 색·서체·표 치수를 역할 이름으로 단일 정의하고, 테마에 맞는 값을 돌려준다.

"""Role-named design tokens shared by every page, table, and chart.

`.streamlit/config.toml`의 `[theme]`·`[theme.dark]`가 선언한 값이 이 모듈의 근거다. 파이썬
코드에 색 리터럴을 직접 쓰면 두 곳이 조용히 갈라지므로(실제로 갈라져 있었다) 화면 코드는
여기의 토큰만 참조한다.

토큰 이름은 **역할**이다. 값이 같아도 역할이 다르면 다른 이름을 쓴다. 예를 들어
`BORDER`와 `STATUS_SECURE`는 라이트에서 둘 다 zinc-300이지만, 확보 상태색을 조정할 때
표 테두리가 함께 바뀌어서는 안 된다.

테마에 따라 값이 갈린다
-----------------------
`tokens.SURFACE` 처럼 **쓰는 쪽은 한 글자도 바뀌지 않는다.** 이름이 모듈에 없으므로
파이썬이 `__getattr__` 을 부르고, 그때 지금 세션의 테마에 맞는 팔레트에서 꺼내 준다
(PEP 562). 호출부가 414 곳이라 그것을 전부 고치는 것은 답이 아니었다.

`if TYPE_CHECKING:` 블록이 이름과 타입을 알린다. 그 블록은 **실행되지 않으므로** 더미
값은 새지 않고, mypy 는 타입·오타·재대입을 그대로 잡는다(`.pyi` 스텁은 이 저장소의 mypy
`files` 설정에서 무시되어 쓸 수 없다 — 실측으로 확인했다).

테마 해석은 `design/theme.py` 가 **실행 한 번에 한 번만** 한다. 접근마다 읽으면
rerun 당 3.83ms 이고 한 번만 읽으면 0.05ms 다.

**면의 층은 다크에서 방향이 뒤집힌다.** 라이트는 안쪽·위 단계로 갈수록 어두워지고
다크는 밝아진다 — 어두운 바탕에서는 「위로 올라온 면이 빛을 더 받는다」가 깊이의 관례라,
같은 방향을 유지하면 합계 행이 배경에 가라앉는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from capa_simulation.design import theme


def _with_alpha(hex_color: str, alpha: float) -> str:
    """`#RRGGBB` 토큰에서 반투명 rgba 를 만든다. 손으로 옮겨 적으면 원 토큰과 갈라진다."""
    red, green, blue = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"


# 라이트 팔레트. 아래 주석이 값마다의 근거다.
_LIGHT: Final[dict[str, Any]] = {
    # ---------------------------------------------------------------- 면과 텍스트
    # config.toml [theme] 와 1:1 대응한다.
    # 페이지 바탕을 살짝 눌러(`#F7F8FA`) 표와 카드의 흰 면이 떠 보이게 한다. 밀도 높은
    # 화면에서 어디까지가 한 덩어리인지 테두리에만 의존하지 않고 읽히게 하려는 것이다.
    "SURFACE": "#FFFFFF",  # 표·카드 면. secondaryBackgroundColor
    "SURFACE_PAGE": "#F7F8FA",  # backgroundColor. 카드가 뜨는 바탕
    "SURFACE_SUBTLE": "#FAFAFB",
    "SURFACE_CLASSIFICATION": "#F1F3F6",
    "SURFACE_CLASSIFICATION_GROUP": "#E5E8EC",
    "HEADER_BACKGROUND": "#E4E7EB",  # dataframeHeaderBackgroundColor
    # 화면 맨 위 띠의 면. 페이지 바탕보다 한 단계만 눌러 앱 머리와 본문을 나눈다. 표 머리글
    # (HEADER_BACKGROUND)보다는 밝아야 표의 위계를 침범하지 않는다.
    "HEADER_BAR": "#EFF1F5",
    "BORDER": "#DDE0E5",  # borderColor
    "BORDER_STRONG": "#A3A9B2",
    "TEXT": "#18181B",  # textColor
    "TEXT_MUTED": "#646973",  # grayColor
    "LINE": "#3F3F46",  # 표 격자·계열선. 강조색과 역할이 다르다
    "ACCENT": "#0F766E",  # primaryColor. 버튼·포커스 등 상호작용 표시
    # ------------------------------------------------------------------- 부분합 면
    # 환산 결과표의 제품 Total → 양산구분 Total → 전체 합계로 갈수록 짙어진다.
    "SURFACE_PRODUCT_TOTAL": "#F0F1F2",
    "CLASSIFICATION_PRODUCT_TOTAL": "#DDE0E3",
    "SURFACE_PRODUCTION_TOTAL": "#E2E4E7",
    "CLASSIFICATION_PRODUCTION_TOTAL": "#CCD0D4",
    "SURFACE_GRAND_TOTAL": "#D2D5D9",
    "CLASSIFICATION_GRAND_TOTAL": "#B9BEC4",
    # --------------------------------------------------------------------- 상태색
    # 확보 → 경고 → 부족 순으로 **휘도가 단조 감소**해야 한다. 그래야 흑백 출력과 색각
    # 이상에서도 심각도 순서가 읽힌다. 이전 팔레트는 경고(0.793)가 확보(0.660)보다 밝아
    # 순서가 거꾸로 읽혔다. 현재 값의 휘도는 0.660 → 0.414 → 0.236이고 세 색 모두 검은
    # 글자와 4.8:1 이상의 대비를 갖는다.
    "STATUS_SECURE": "#D4D4D8",
    "STATUS_WARNING": "#FB923C",
    "STATUS_SHORTAGE": "#F43F5E",
    # ------------------------------------------------------------- 연간 Total 열 면색
    # 월 칸과 같은 표 안에 있지만 성격이 다르다는 것을 색으로만 알린다. 테두리를 더하면
    # 월 칸 격자와 경쟁해 표가 시끄러워진다. 면색 대비는 월 칸 대비 1.05:1 로 얕게 둔다 —
    # 짙게 하면 합계 열이 본문보다 먼저 읽힌다.
    "SURFACE_YEAR_TOTAL": "#EFF1F3",
    "SURFACE_CLASSIFICATION_YEAR_TOTAL": "#E3E6E9",
    # ------------------------------------------------------------------ 과거 구간 면색
    # Past Data 로 채운 달의 열 바탕. 그 열의 값은 DB 계산 결과가 아니라 입력해 둔 지난
    # 이력이라 GAP 도 적지 않는다 — 면색이 그 경계를 말한다.
    #
    # **한 단계 눌러 만든 짝이다.** 월 칸은 줄무늬(SURFACE·SURFACE_SUBTLE)와 연간 Total 로
    # 이미 세 가지 면을 쓰므로, 과거 전용 색 하나를 덧칠하면 그 안의 위계가 사라진다. 각
    # 바탕색마다 대응하는 어두운 짝을 두어 줄무늬와 합계 칸이 과거 구간에서도 그대로 읽힌다.
    # 흰 면 대비 1.23:1 로 띠의 경계가 보이면서 본문 글자와는 12:1 이 넘어 값 가독성은 그대로다.
    "SURFACE_PAST": "#E3E8EF",
    "SURFACE_PAST_SUBTLE": "#DEE3EB",
    "SURFACE_PAST_YEAR_TOTAL": "#D3D9E2",
    # ------------------------------------------------------------------ 증감 표기색
    # 선행 반영 전후의 차이를 값 위에 작게 적을 때 쓴다. 좋고 나쁨이 아니라 방향 표시라
    # 상태색(확보·경고·부족)을 재사용하지 않는다 — 재사용하면 계획이 늘어난 달이 그대로
    # "부족" 으로 읽힌다. 증감 글자는 12px 이라 4.5:1 이 기준이고, 흰 면뿐 아니라 가장
    # 어두운 면인 과거 연간 Total(#D3D9E2) 위에서도 넘겨야 한다 — 증가색을 #B45309 에서
    # 옮긴 것이 그래서다(그 면에서 3.54:1 이었다).
    "DELTA_INCREASE": "#A14100",
    "DELTA_DECREASE": "#1D4ED8",
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
    "DELTA_AREA_DECREASE": "#F9A8D4",
    "DELTA_AREA_INCREASE": "#84CC16",
    # 가로막대의 바탕 트랙. 막대 길이 눈금(80~150%)의 전체 구간을 보여준다. 표 머리글·
    # 스크롤바 트랙과 값이 비슷하지만 역할이 다르므로 별도 토큰이다.
    # 트랙이 먼저 셀 면(SURFACE)에서 분리돼야 눈금 구간이 보인다: 대비 1.27:1.
    # 그 위의 "확보" 막대(STATUS_SECURE)와는 1.17:1 뿐이라 면색만으로는 부족하고,
    # 막대 테두리(LINE, 트랙 대비 8.25:1)가 BAR_OUTLINE_WIDTH_PX 굵기로 경계를 만든다.
    "BAR_TRACK": "#E1E5EA",
    # --------------------------------------------------------- Dynamic Capa 계열색
    # 표준 → 실효 → 실적으로 갈수록 밝아지는 단계 비교용이며 상태 판정과는 무관하다.
    "SERIES_STANDARD": "#3F3F46",
    "SERIES_EFFECTIVE": "#A1A1AA",
    "SERIES_ACTUAL": "#71717A",
    # ------------------------------------------------------------------ 재공 격자색
    # 색상(계열)이 뜻을 나른다 — 무채색은 양, 파랑은 유입, 초록은 충족, 빨강은 부족,
    # 보라는 「알 수 없음」이다. 계열은 그대로 두고 **명도·채도만** 옮겼다.
    # 옛 값은 적록색약에서 `유입`(#60A5FA)과 `표준 미설정`(#A78BFA)이 ΔE 0.3 으로
    # 사실상 같은 색이었다 — 범례가 있어도 두 칸을 가를 수 없다.
    "WIP_HELD": "#A2A2A2",
    "WIP_INFLOW": "#68ABEE",
    "WIP_FLOW_MET": "#01D587",
    "WIP_FLOW_SHORT": "#F6636B",
    "WIP_FLOW_UNSET": "#9F78DD",
    # ----------------------------------------------------------- 설비 생애주기 상태
    # `EQUIPMENT_STATUSES` 9종 전부에 색을 준다. 명시 scale 없이 Altair 에 넘기면
    # config.toml 의 chartCategoricalColors 4색을 순환해 5~9번째 상태가 앞의 것과 같은
    # 색으로 그려진다. 종료된 두 상태는 무채색으로 눌러 진행 중인 상태와 구분한다.
    #
    # **계열은 뜻이고 명도·채도는 구분 수단이다.** 파랑=앞으로 올 것, 주황=하는 중,
    # 초록=쓸 수 있음, 노랑=나갈 것, 보라=옮길 것, 청록=세워 둔 것, 빨강=못 씀. 옛 값은
    # 파스텔이라 적록색약에서 `입고 예정`(#93C5FD)과 `이설 예정`(#C4B5FD)이 ΔE 0.5 로
    # 사실상 같은 색이었다. 파랑과 보라는 적록색약에서 같은 쪽으로 무너져 색상으로는 못
    # 가르므로 남는 지렛대는 명도뿐이다 — 계열을 지키면서 밝기를 벌렸다.
    #
    # **9종은 색만으로 완전히 가를 수 있는 수를 넘는다.** 색각이상 하한(ΔE 6)은 넘었지만
    # 정상 시야 권장선(15)에는 못 미친다. 범례와 라벨이 함께 있어야 뜻이 전해진다.
    # `tests/test_categorical_palettes.py` 가 이 거리를 고정한다.
    "EQUIPMENT_STAGE_COLORS": {
        "입고 예정": "#788EDD",
        "셋업 진행중": "#D88F4E",
        "가용": "#7BCA8A",
        "반출 예정": "#D4B122",
        "이설 예정": "#C0A2F5",
        "보관 설비": "#56B1C3",
        "운영 비가동": "#CA7055",
        "반출 완료": "#909090",
        "이설 완료": "#717171",
    },
    "EQUIPMENT_STAGE_FALLBACK": "#E5E7EB",
    # Qual 실행관리 상태. 계획 → 확정 → 완료로 갈수록 짙어지고 지연만 경고색이다.
    "QUAL_CONFIRMATION_COLORS": {
        "계획": "#CBD5E1",
        "확정": "#93C5FD",
        "완료": "#86EFAC",
    },
    # ------------------------------------------------------------- Space 배치도 전용
    # FAB 도면은 zinc 계열이 아니라 자체 blue-grey 를 쓴다. 도면 관례에 맞춘 의도적인
    # 하위 팔레트이며 표·차트와 섞어 쓰지 않는다.
    "SPACE_CANVAS": "#F7F8FA",
    "SPACE_BORDER": "#59636E",
    "SPACE_TEXT": "#20262E",
    "SPACE_LABEL_TEXT": "#69727C",
    "SPACE_GRID": "#E5E8EB",
    "SPACE_BUILDING_FILLS": (
        "#E7EDF2",
        "#F3F5F7",
        "#E9EDF1",
        "#F3F5F7",
        "#E9EDF1",
    ),
    # ------------------------------------------------------------------ 스크롤바 색
    "SCROLLBAR_TRACK": "#ECEEF1",
    "SCROLLBAR_THUMB": "#8F9399",
    "SCROLLBAR_THUMB_HOVER": "#686D73",
    "SCROLLBAR_THUMB_ACTIVE": "#52565C",
}

# 다크 팔레트. 이름은 라이트와 **정확히 같아야** 한다(검사가 고정한다).
_DARK: Final[dict[str, Any]] = {
    # 면. 페이지가 가장 어둡고 카드가 그 위에 뜬다 — **라이트와 방향이 반대다.**
    "SURFACE": "#1C1C21",
    "SURFACE_PAGE": "#131316",
    "SURFACE_SUBTLE": "#212127",
    "SURFACE_CLASSIFICATION": "#26262D",
    "SURFACE_CLASSIFICATION_GROUP": "#303039",
    "HEADER_BACKGROUND": "#2B2B33",
    "HEADER_BAR": "#191920",
    "BORDER": "#35353E",
    "BORDER_STRONG": "#6B6B78",
    "TEXT": "#E9E9EC",
    "TEXT_MUTED": "#9B9BA6",
    # 격자·막대 테두리. 면에서 떨어져야 하므로 **극이 반대가 된다**(어두운 선 → 밝은 선).
    "LINE": "#C6C6CE",
    # teal-700 은 어두운 면에서 3:1 을 못 넘는다. 한 단계 올린다.
    "ACCENT": "#2DD4BF",
    # 합계 3단도 위로 갈수록 밝다. 같은 방향을 유지하면 합계 행이 배경에 가라앉는다.
    "SURFACE_PRODUCT_TOTAL": "#26262C",
    "CLASSIFICATION_PRODUCT_TOTAL": "#33333C",
    "SURFACE_PRODUCTION_TOTAL": "#2F2F37",
    "CLASSIFICATION_PRODUCTION_TOTAL": "#3D3D47",
    "SURFACE_GRAND_TOTAL": "#3A3A44",
    "CLASSIFICATION_GRAND_TOTAL": "#4A4A56",
    # --------------------------------------------------------------------- 상태색
    # **칸을 채우고 그 위에 `TEXT`(거의 흰색)가 얹히는 색이다.** 그래서 밝은 테마의 짝을
    # 그대로 쓸 수 없다 — 면이 밝으면 흰 숫자가 사라진다. 세 색 모두 흰 글자와 4.5:1
    # 이상이어야 하고, 그 상한이 휘도를 좁은 띠 안에 가둔다.
    #
    # 그 띠 안에서 **채도가 유일하게 남은 채널**이다. 처음에 밝은 테마 색을 캔버스 쪽으로
    # 섞어 만들었더니 휘도와 채도를 한꺼번에 눌러, 세 색이 서로 구분되지 않았다 —
    # 경고↔부족의 색각이상 OKLab ΔE 가 4.3 으로 바닥(6.0)마저 밑돌았고 세 쌍 모두
    # 정상시야 바닥(15)에 못 미쳤다. 히트맵은 이 셋을 나란히 놓고 읽는 화면이라
    # 「면 대 바탕」이 아니라 **「면 대 면」**이 맞는 잣대다.
    #
    # 지금 값은 휘도를 유지한 채 채도만 끌어올려 다시 잡은 것이다(제약 안에서 전수 탐색):
    #   색각이상 ΔE 최악 9.8 (목표 8.0) · 정상시야 ΔE 최악 15.4 (바닥 15.0)
    #   흰 글자 대비 확보 4.52 · 경고 4.63 · 부족 7.73
    # 휘도 단조 감소(확보 > 경고 > 부족)는 그대로다. 숫자는 손으로 고치지 말고
    # `tests/test_design_tokens.py` 의 분리 검사를 다시 돌려 얻는다 — 그 검사는 두 팔레트를
    # 모두 본다.
    "STATUS_SECURE": "#69696B",
    "STATUS_WARNING": "#B04700",
    "STATUS_SHORTAGE": "#8F0040",
    "SURFACE_YEAR_TOTAL": "#232329",
    "SURFACE_CLASSIFICATION_YEAR_TOTAL": "#2D2D35",
    "SURFACE_PAST": "#242A34",
    "SURFACE_PAST_SUBTLE": "#282E39",
    "SURFACE_PAST_YEAR_TOTAL": "#2C333F",
    # 증감 글자색은 어두운 면에서 읽혀야 하므로 라이트보다 밝은 짝으로 간다.
    "DELTA_INCREASE": "#FBBF24",
    "DELTA_DECREASE": "#7DA8FF",
    "DELTA_AREA_DECREASE": "#F9A8D4",
    "DELTA_AREA_INCREASE": "#84CC16",
    "BAR_TRACK": "#31313A",
    # 계열색은 라이트에서 "짙을수록 기준" 이었다. 다크에서는 밝을수록 기준이 된다.
    "SERIES_STANDARD": "#D4D4D8",
    "SERIES_EFFECTIVE": "#71717A",
    "SERIES_ACTUAL": "#A1A1AA",
    "WIP_HELD": "#8C757B",
    "WIP_INFLOW": "#0063E2",
    "WIP_FLOW_MET": "#1FB252",
    "WIP_FLOW_SHORT": "#944126",
    "WIP_FLOW_UNSET": "#694B96",
    # 설비 상태 9종. 라이트와 같은 방법으로 골랐다 — 계열(뜻)은 고정하고 명도·채도만
    # 움직여 색각이상 하한을 넘기는 값 중 가장 덜 움직인 것. 다크 밴드가 좁아 라이트보다
    # 진하다. `tests/test_categorical_palettes.py` 가 거리를 고정한다.
    "EQUIPMENT_STAGE_COLORS": {
        "입고 예정": "#0856C0",
        "셋업 진행중": "#D37E07",
        "가용": "#0FAC4C",
        "반출 예정": "#947737",
        "이설 예정": "#694B96",
        "보관 설비": "#2C8B9E",
        "운영 비가동": "#894745",
        "반출 완료": "#747474",
        "이설 완료": "#959595",
    },
    "EQUIPMENT_STAGE_FALLBACK": "#3A3A42",
    "QUAL_CONFIRMATION_COLORS": {
        "계획": "#7C8899",
        "확정": "#5C9BE8",
        "완료": "#4FB980",
    },
    # FAB 도면. blue-grey 하위 팔레트를 어두운 쪽으로 옮긴다.
    "SPACE_CANVAS": "#141A21",
    "SPACE_BORDER": "#8C98A6",
    "SPACE_TEXT": "#DCE3EB",
    "SPACE_LABEL_TEXT": "#98A3B0",
    "SPACE_GRID": "#2A323C",
    "SPACE_BUILDING_FILLS": (
        "#1E2630",
        "#182028",
        "#1B232C",
        "#182028",
        "#1B232C",
    ),
    # 손잡이는 누를수록 또렷해진다 — 다크에서는 밝아지는 쪽이다.
    "SCROLLBAR_TRACK": "#22222A",
    "SCROLLBAR_THUMB": "#55555F",
    "SCROLLBAR_THUMB_HOVER": "#71717C",
    "SCROLLBAR_THUMB_ACTIVE": "#8C8C98",
}


def _complete(palette: dict[str, Any]) -> dict[str, Any]:
    """별칭과 계산값을 채운다. **손으로 옮겨 적지 않는다** — 원 토큰과 갈라진다."""
    filled = dict(palette)
    # 모든 Figure 는 배경이 투명한 `st.container(border=True)` 안에 놓여 페이지 바탕 위에
    # 그려진다. 흰 면(SURFACE)을 쓰면 Figure 만 흰 사각형으로 뜬다.
    filled["CHART_CANVAS"] = palette["SURFACE_PAGE"]
    # 실행관리 일정 상태. 재공 격자의 충족·유입색과 같은 값을 써서 시각 언어를 맞춘다.
    filled["SCHEDULE_DONE"] = palette["WIP_FLOW_MET"]
    filled["SCHEDULE_PLANNED"] = palette["WIP_INFLOW"]
    # 지연만 경고색이다. 상태색을 바꾸면 여기도 함께 움직여야 한다.
    filled["QUAL_CONFIRMATION_COLORS"] = {
        **palette["QUAL_CONFIRMATION_COLORS"],
        "지연": palette["STATUS_WARNING"],
    }
    # 사이드바 네비게이션의 "지금 여기" 표시. 이 앱에서 그림자를 쓰는 유일한 자리다 —
    # 화면 어디에도 융기가 없기 때문에 사이드바에서만 쓰면 그 자체가 신호가 된다.
    # 링은 ACCENT 라 색이고, 그림자는 TEXT 라 깊이다. 둘을 한 토큰으로 합치지 않는다.
    filled["NAV_HOME_TINT"] = _with_alpha(palette["ACCENT"], 0.07)
    filled["NAV_ACTIVE_RING"] = _with_alpha(palette["ACCENT"], 0.14)
    filled["NAV_SHADOW"] = _with_alpha(palette["TEXT"], 0.10)
    # HOME 버튼 그라디언트의 위쪽 끝. 아래는 `SURFACE` 로 빠진다 — 단색 틴트는 「누를 수
    # 있는 것」에서 멈추지만, 위가 진하고 아래가 밝으면 맨 위 칸이 「돌아오는 자리」로 읽힌다.
    filled["NAV_HOME_TINT_STRONG"] = _with_alpha(palette["ACCENT"], 0.16)
    # HOME 버튼 위를 한 번 지나는 광택 띠. 면색이 아니라 **빛**이라 SURFACE 를 흐린다.
    filled["NAV_HOME_SHEEN"] = _with_alpha(palette["SURFACE"], 0.85)
    # 기준선과 실적선 사이를 칠하는 옅은 면. `DELTA_AREA_*` 는 막대 트랙 위에 얹혀 트랙과
    # 구분돼야 하지만, 이 면은 선 두 개 사이를 채우기만 하면 되므로 같은 세기로 칠하면
    # 정작 읽어야 할 선이 면에 묻힌다.
    filled["GAP_AREA_SHORTFALL"] = _with_alpha(palette["DELTA_AREA_DECREASE"], 0.35)
    filled["GAP_AREA_SURPLUS"] = _with_alpha(palette["DELTA_AREA_INCREASE"], 0.35)
    # 배경 도면 위에 캔버스를 덮을 때. SPACE_CANVAS 를 바꾸면 함께 바뀐다.
    filled["SPACE_CANVAS_OVERLAY"] = _with_alpha(palette["SPACE_CANVAS"], 0.18)
    return filled


_PALETTES: Final[dict[str, dict[str, Any]]] = {
    "light": _complete(_LIGHT),
    "dark": _complete(_DARK),
}


def palette_value(mode: str, name: str) -> Any:
    """**지정한 테마**의 값. 지금 실행의 테마가 아니라 고른 테마를 본다.

    테마 전환 버튼처럼 **반대 테마의 옷을 입어야 하는 자리**가 쓴다 — 어두운 화면에서는
    흰 알약에 검은 글자, 밝은 화면에서는 검은 알약에 흰 글자여야 배경에 묻히지 않는다.
    그 대비의 근거를 손으로 적은 색이 아니라 팔레트에 두기 위한 창구다.
    """
    return _PALETTES[mode][name]


if TYPE_CHECKING:
    # **런타임에는 만들어지지 않는다.** 값은 위 팔레트가 갖고, 여기서는 이름과 타입만
    # 알린다. `Final` 은 값 없이 쓸 수 없어 더미를 주는데, 이 블록이 실행되지 않으므로
    # 그 더미는 화면에 새지 않는다. 이름이 모듈에 없어야 `__getattr__` 이 불린다.
    ACCENT: Final[str] = ""
    BAR_TRACK: Final[str] = ""
    BORDER: Final[str] = ""
    BORDER_STRONG: Final[str] = ""
    CHART_CANVAS: Final[str] = ""
    CLASSIFICATION_GRAND_TOTAL: Final[str] = ""
    CLASSIFICATION_PRODUCTION_TOTAL: Final[str] = ""
    CLASSIFICATION_PRODUCT_TOTAL: Final[str] = ""
    DELTA_AREA_DECREASE: Final[str] = ""
    DELTA_AREA_INCREASE: Final[str] = ""
    DELTA_DECREASE: Final[str] = ""
    DELTA_INCREASE: Final[str] = ""
    EQUIPMENT_STAGE_COLORS: Final[dict[str, str]] = {}
    EQUIPMENT_STAGE_FALLBACK: Final[str] = ""
    GAP_AREA_SHORTFALL: Final[str] = ""
    GAP_AREA_SURPLUS: Final[str] = ""
    HEADER_BACKGROUND: Final[str] = ""
    HEADER_BAR: Final[str] = ""
    LINE: Final[str] = ""
    NAV_ACTIVE_RING: Final[str] = ""
    NAV_HOME_SHEEN: Final[str] = ""
    NAV_HOME_TINT: Final[str] = ""
    NAV_HOME_TINT_STRONG: Final[str] = ""
    NAV_SHADOW: Final[str] = ""
    QUAL_CONFIRMATION_COLORS: Final[dict[str, str]] = {}
    SCHEDULE_DONE: Final[str] = ""
    SCHEDULE_PLANNED: Final[str] = ""
    SCROLLBAR_THUMB: Final[str] = ""
    SCROLLBAR_THUMB_ACTIVE: Final[str] = ""
    SCROLLBAR_THUMB_HOVER: Final[str] = ""
    SCROLLBAR_TRACK: Final[str] = ""
    SERIES_ACTUAL: Final[str] = ""
    SERIES_EFFECTIVE: Final[str] = ""
    SERIES_STANDARD: Final[str] = ""
    SPACE_BORDER: Final[str] = ""
    SPACE_BUILDING_FILLS: Final[tuple[str, ...]] = ()
    SPACE_CANVAS: Final[str] = ""
    SPACE_CANVAS_OVERLAY: Final[str] = ""
    SPACE_GRID: Final[str] = ""
    SPACE_LABEL_TEXT: Final[str] = ""
    SPACE_TEXT: Final[str] = ""
    STATUS_SECURE: Final[str] = ""
    STATUS_SHORTAGE: Final[str] = ""
    STATUS_WARNING: Final[str] = ""
    SURFACE: Final[str] = ""
    SURFACE_CLASSIFICATION: Final[str] = ""
    SURFACE_CLASSIFICATION_GROUP: Final[str] = ""
    SURFACE_CLASSIFICATION_YEAR_TOTAL: Final[str] = ""
    SURFACE_GRAND_TOTAL: Final[str] = ""
    SURFACE_PAGE: Final[str] = ""
    SURFACE_PAST: Final[str] = ""
    SURFACE_PAST_SUBTLE: Final[str] = ""
    SURFACE_PAST_YEAR_TOTAL: Final[str] = ""
    SURFACE_PRODUCTION_TOTAL: Final[str] = ""
    SURFACE_PRODUCT_TOTAL: Final[str] = ""
    SURFACE_SUBTLE: Final[str] = ""
    SURFACE_YEAR_TOTAL: Final[str] = ""
    TEXT: Final[str] = ""
    TEXT_MUTED: Final[str] = ""
    WIP_FLOW_MET: Final[str] = ""
    WIP_FLOW_SHORT: Final[str] = ""
    WIP_FLOW_UNSET: Final[str] = ""
    WIP_HELD: Final[str] = ""
    WIP_INFLOW: Final[str] = ""
else:

    def __getattr__(name: str) -> Any:
        """지금 세션의 테마에 맞는 값을 돌려준다(PEP 562).

        모듈에 없는 이름일 때만 불리므로, 위의 치수·서체 상수는 여기까지 오지 않는다.
        """
        try:
            return _PALETTES[theme.current_mode()][name]
        except KeyError:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


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
# `st.data_editor`·`st.dataframe` 이 그리는 월별 격자의 행 높이. 위의 Plotly 표 행(27)과
# 그리는 엔진이 달라 값을 합치지 않는다 — 한쪽 밀도를 건드리면 다른 쪽까지 따라 움직인다.
MONTH_GRID_ROW_HEIGHT_PX: Final = 25
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
