# Purpose: 상단 띠에 적용 중인 시나리오를 싣고 ⋮ 메뉴 감춤·인쇄 규칙을 껍데기 스타일로 보낸다.

"""The scenario this session is looking at, pinned to the top bar.

Streamlit 은 헤더(`stHeader`)에 위젯을 넣는 공식 API 를 주지 않는다. 대신 그 요소의
가상요소 두 개에 글을 얹는다. 헤더는 `position: absolute` 라 자기 자신이 포함 블록이고
왼쪽 끝이 사이드바 오른쪽에 붙어 있으므로, 사이드바를 접거나 폭을 끌어 바꿔도 글이 따라
움직인다 — 좌표를 손으로 계산하는 `position: fixed` 배너와 갈리는 지점이다.

**무엇을 싣는가**(2026-10-06 사용자 결정). 이 세션에 **적용 중인 시나리오**다(`header_lines`).
- 위 줄(굵게): `{시나리오명} · r{N} {리비전명} · {상태}` — 상태는 `공식 v{N}`(최신
  공식버전)·`저장된 리비전`·`미저장 변경`(적용했지만 저장하지 않은 편집 — 사이드바 시나리오
  상자의 「미저장 변경」과 같은 판정 `has_unsaved_scenario_changes`).
- 아래 줄(옅게): `{시뮬레이션 코드} · 적용 {YY.MM}–{YY.MM} · {원천} {YY.MM.DD} 등록`. 시나리오
  기간은 생산계획에 있는 첫 달·끝 달이고 조회기간이 아니다(조회기간은 사이드바 조건 카드에 이미
  있다). 공식버전이 아니면 등록일 대신 리비전 저장일(`{YY.MM.DD} 저장`)이다.
- 값이 없으면(활성 시나리오가 없는 저장소 등) 앱 이름 한 줄로 물러난다.

**HOME 을 무겁게 하지 않는다**(2026-10-03 사용자 원칙). 이 글은 회차마다 DB 를 보지 않는다 —
시나리오 이름표는 활성화할 때 세션에 떠 둔 값(`scenario_activation.active_scenario_label`),
최신 공식버전은 입장 화면 요약이 `RECHECK_SECONDS` 에 한 번 확인해 세션에 둔 값
(`intro_summary.latest_official_revision`), 미저장 여부는 세션 판정이다.

대가는 가상요소의 한계다. 줄마다 글 한 덩어리와 스타일 하나뿐이라 한 줄 안에서 굵기나
색을 섞지 못하고, 링크·버튼처럼 누를 수 있는 것도 못 넣는다. 그래서 상태는 칩이 아니라 위 줄 끝의
글자다. 칩을 그리려면 툴바 단추처럼 스크립트가 실제 요소를 넣어야 하는데, 그 iframe 은 회차마다
내용이 같아야 해서(`theme_toggle`) 회차마다 바뀌는 값을 실을 길이 따로 필요하다 — 글자로 충분해
가벼운 쪽을 골랐다. 시나리오명 등 사용자 글은 CSS 문자열로 이스케이프한다(`css_string`).

사이드바 머리칸(`stSidebarHeader`)에는 글을 얹지 않는다. 그 자리는 `S.PKG CAPA` 라벨(누르면
Summary — `intro_summary.summary_label_script`)이다. 앱 이름·버전·개발자·인증 정보는 Admin Area
맨 아래(`components/app_credits.py`)로 옮겼다.

Streamlit 의 ⋮ 메뉴(`stMainMenu`)도 여기서 통째로 감춘다(2026-10-05 사용자 결정). 사용자에게
남길 메뉴 항목은 인쇄와 테마뿐이고, 둘 다 툴바 단추(`print_button`·`theme_toggle`)가 맡는다. 최소
모드(`client.toolbarMode = "minimal"`)는 테마 항목을 남겨 메뉴가 사라지지 않으므로 쓰지 않는다 —
Deploy 단추와 우리 단추가 앉는 툴바 슬롯은 그대로다. 인쇄 규칙(`@media print`)도 같은 스타일에
싣는다(2026-10-05 사용자 요청 — 화면에 펼쳐 둔 사이드바도 인쇄에서는 늘 뺀다). 이 둘을 담은 앞선
껍데기 스타일(`SHELL_STYLE`, `render_shell_style`)만은 머리 띠 CSS 와 따로 **부트스트랩보다 앞에서**
보낸다. 머리 띠는 부트스트랩·요약 뒤에야 나가서,
거기에 두면 부트스트랩 오류 화면(`st.stop()`)에는 메뉴가 그대로 남고, 새로 읽을 때마다 부트스트랩이
끝날 때까지 메뉴가 보였다 사라지며 툴바 단추가 옆으로 밀린다. 인쇄 규칙도 앞에 있어야 오류 화면을
인쇄할 때 사이드바가 빠진다. 메뉴는 Streamlit 의 정적 껍데기라 첫 delta 가 닿기 전 아주 잠깐은 보일
수 있다 — 파이썬이 그보다 앞설 길은 없다.

띠의 면은 페이지 바탕보다 한 단계만 눌러(`tokens.HEADER_BAR`) 앱 머리와 본문을 나눈다.
글자색은 본문과 같다 — 면이 밝아 뒤집을 이유가 없다.

`data-testid` 는 emotion 클래스와 달리 판올림 사이에 비교적 안정적이지만 어디까지나
비공식 경로다. Streamlit 을 올린 뒤에는 글이 헤더에 남아 있는지 눈으로 확인한다.
"""

from datetime import datetime

import streamlit as st

from capa_simulation.components.intro_summary import latest_official_revision
from capa_simulation.design import tokens
from capa_simulation.scenario_activation import (
    ActiveScenarioLabel,
    active_scenario_label,
    has_unsaved_scenario_changes,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.settings import APP_NAME

# 원천 유형(`app_meta.dataset.source_type`)을 머리 띠에 적는 이름. 목록에 없는 유형은 값
# 그대로 적는다.
SOURCE_TYPE_LABELS = {
    "BIGDATAQUERY": "BigDataQuery",
    "BUILTIN_SYNTHETIC_SEED": "내장 시드",
    "DUCKDB_SCENARIO_CLONE": "복제",
    "SCENARIO_MONTH_MERGE": "월 병합",
    "SCENARIO_YEAR_SHIFT": "연도 이동",
}
# `CSV_CORE_DATA_INITIAL_BOOTSTRAP` 처럼 Core_Data.csv 에서 온 유형은 모두 「CSV」다.
_CSV_SOURCE_PREFIX = "CSV_CORE_DATA"
STATUS_OFFICIAL = "공식 v{release_no}"
STATUS_SAVED = "저장된 리비전"
STATUS_UNSAVED = "미저장 변경"

# 부트스트랩 앞에서 보내는 껍데기 스타일. 색을 쓰지 않아 테마와 무관한 고정 문자열이다.
#
# 첫 규칙은 Streamlit 의 ⋮ 메뉴다. 인쇄·테마는 툴바 단추가 맡으므로 단추째 감춘다. 감추는 것은 이
# 요소 하나다 — Deploy 와 툴바 슬롯(`stToolbarActions`)은 형제라 영향이 없다.
#
# 나머지는 인쇄 규칙 한 덩어리다. 화면에는 아무것도 바꾸지 않는다. 선택자는 모두 1.63 번들에서
# `data-testid` 로 확인한 것이다 — 판올림 뒤 인쇄 미리보기로 다시 본다.
# - 사이드바는 펼쳐 있어도 뺀다. Streamlit 은 인쇄에서 `display: 접힘 ? none : initial` 로 펼친
#   사이드바를 그대로 찍으므로 `!important` 로 덮는다. 사이드바와 본문(`stMain`)은 가로 flex 의
#   형제라, 사이드바가 빠지면 본문이 왼쪽 끝부터 종이 폭을 다 쓴다. 사이드바 머리 띠(`::before`)와
#   접기 버튼도 함께 빠진다.
# - 머리 띠는 요소째 뺀다. Streamlit 은 헤더의 자식만 감춰 우리 면·`::before`/`::after` 글이 남는다.
#   툴바 단추(Guide·테마·Print)와 Deploy 도 이 안에 있다.
# - 입장 화면·Summary 덮개(`#capa-intro-host`, `document.body` 에 붙은 호스트)는 열려 있어도 뺀다.
# - 본문 폭 상한은 풀어 둔다(`layout="wide"` 가 이미 풀지만 못박는다).
# - 색은 화면 그대로 찍는다. Streamlit 이 `html` 에 걸어 둔 것을 앱 뿌리에도 건다(물려받는 속성이라
#   상태색·차트색·표 바탕이 함께 남는다).
# - Vega 차트·CCv2 칸(Space 배치 보기 등)·지표 카드는 쪽 사이에서 자르지 않는다. 긴 표
#   (`stDataFrame`·`stTable`)에는 걸지 않는다 — 한 쪽보다 길면 통째로 다음 쪽으로 밀려 빈 쪽이
#   생긴다. **Plotly(`stPlotlyChart`)에도 걸지 않는다.** 이 앱의 월별 표(`monthly_table_base`·HOME
#   대시보드)가 Plotly 라 긴 표와 같은 꼴이 되고, 행 이름 열만 다음 쪽으로 밀리면 옆의 월 열(가로
#   스크롤 칸 — 인쇄에서 쪼개지지 않는다)과 어긋나 값이 잘려 나간다. Plotly 표와 차트를 가를
#   `data-testid` 는 없다. 테두리 상자(`st.container(border=True)`)는 테두리가 emotion 스타일에만
#   있고 DOM 에 표지가 없어 `data-testid` 로 고를 수 없으므로 걸지 않는다.
# - 용지 방향은 브라우저 인쇄 창에 맡긴다(`@page` 에 `size` 를 두지 않는다). 여백만 정한다.
SHELL_STYLE = """<style>
[data-testid="stMainMenu"] { display: none !important; }
@media print {
  @page { margin: 10mm; }
  [data-testid="stSidebar"],
  [data-testid="stHeader"],
  #capa-intro-host {
    display: none !important;
  }
  [data-testid="stMainBlockContainer"] {
    max-width: none !important;
  }
  [data-testid="stApp"] {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  [data-testid="stVegaLiteChart"],
  [data-testid="stBidiComponentIsolated"],
  [data-testid="stBidiComponentRegular"],
  [data-testid="stMetric"] {
    break-inside: avoid;
  }
}
</style>"""

# CSS 는 중괄호가 많아 f-string 으로 두면 전부 이스케이프해야 한다. 색·글자 자리에
# 센티넬을 두고 **그릴 때마다** 치환한다.
#
# **모듈 로드 시점에 치환하면 안 된다.** 토큰은 실행마다 그때의 팔레트를 보는데, 여기서
# 받아 두면 프로세스가 처음 이 모듈을 읽은 순간의 테마로 굳는다. Streamlit 은 프로세스를
# 유지하므로 사용자가 테마를 바꿔도 헤더만 옛 색으로 남는다.
_HEADER_TEMPLATE = """
/* 헤더 글자는 가상요소뿐이라 한 줄 안에서 굵기·색을 섞을 수 없다. 그래서 「머리」를
   만드는 길은 글자 구성이 아니라 **면**이다. 위가 밝고 아래로 내려앉는 2단 면에 머리
   2px ACCENT 실선 하나. 아래 사이드바 띠와 **같은 값**을 쓴다 — 부모가 다른 두 요소를
   같은 색으로 이어 붙여 하나의 띠처럼 보이게 한 것이라, 한쪽만 고치면 화면 중간에
   이음매가 생긴다. 그라디언트 높이도 `background-size` 로 못박아 두 요소의 높이가 달라도
   같은 자리에서 같은 색이 되게 한다. */
[data-testid="stHeader"] {
  background:
    linear-gradient(180deg, __SURFACE__ 0, __BAR__ 100%) top left / 100% 3.75rem no-repeat,
    __BAR__ !important;
  border-bottom: 1px solid __BAR_BORDER__;
  box-shadow: inset 0 2px 0 __ACCENT__;
}

/* `stHeader` 는 본문 너비만 덮는다. 사이드바 위쪽에도 같은 띠를 이어 붙이지 않으면 색이
   화면 중간에서 끊겨, 같은 줄에 놓인 두 글이 서로 다른 면 위에 앉는다. 띠는 스크롤하지
   않는 사이드바 겉면에 붙여 사이드바를 내려도 제자리에 남기고, 내용은 그 아래로 지나간다. */
[data-testid="stSidebar"]::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3.75rem;
  background:
    linear-gradient(180deg, __SURFACE__ 0, __BAR__ 100%) top left / 100% 3.75rem no-repeat,
    __BAR__;
  border-bottom: 1px solid __BAR_BORDER__;
  box-shadow: inset 0 2px 0 __ACCENT__;
  z-index: 10;
}

[data-testid="stHeader"]::before,
[data-testid="stHeader"]::after {
  position: absolute;
  line-height: 1.1rem;
  left: 1.5rem;
  /* 오른쪽 툴바(Guide·테마·Print·Deploy)가 쓰는 폭은 비워 둔다. 창이 좁아지면 글자를 밀어내지
     않고 말줄임으로 끊는다 — 두 줄이 따로 줄어 짧은 위 줄이 먼저 다 보인다. 28rem 은 툴바에
     Summary 가 있던 때 1100px 창 실측 355px 에 글자 시작 21px 과 틈 12px 를 더한 값이다. 1400px
     보다 좁은 창은 지금 툴바 실측으로 다시 잡는다(`_NARROW_HEADER_RULES`). 16rem 일 때는 글자가
     툴바 밑으로 들어갔다(2026-10-05 E2E). */
  max-width: calc(100% - 28rem);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  padding-left: 0.55rem;
  border-left: 3px solid __ACCENT__;
  font-family: __FONT_FAMILY__;
  /* 헤더 위에 얹히므로 툴바 클릭을 가로채지 않게 한다. */
  pointer-events: none;
}

/* 두 줄의 줄높이를 같게 두면 묶음 높이가 정확히 2.2rem 이고, 윗줄을 가운데에서 한 줄
   위로 올리고 아랫줄을 가운데에 두는 것만으로 띠 한가운데에 정렬된다. 띠 높이가 바뀌어도
   따라간다 — 위에서부터 잰 고정값은 띠 높이를 바꾸는 순간 어긋난다. */
[data-testid="stHeader"]::before {
  content: "__TOP_LINE__";
  top: __TOP_OFFSET__;
  font-size: 0.78rem;
  font-weight: 600;
  color: __TEXT__;
}

[data-testid="stHeader"]::after {
  content: "__BOTTOM_LINE__";
  top: 50%;
  font-size: 0.72rem;
  color: __TEXT_MUTED__;
}

/* 본문 글 속 인라인 코드. Streamlit 기본(0.75em)은 고정폭 글꼴에 없는 한글이 대체 글꼴로 그려져
   알림 안에서 10.5px·캡션 안에서 9.2px 로 작아 읽히지 않았다(2026-10-05 E2E). 본문 크기에
   가깝게 올린다. 코드 블록(`pre`)은 건드리지 않는다. */
[data-testid="stMarkdownContainer"] :not(pre) > code,
[data-testid="stCaptionContainer"] :not(pre) > code {
  font-size: 0.9em;
}

/* 사이드바 머리칸. `S.PKG CAPA` 라벨(`intro_summary.summary_label_script`)이 맨 앞에 선다.
   `relative` 로 두면 사이드바 내용과 함께 스크롤돼 라벨이 위로 사라진다(앱 이름 글일 때 실제로
   그랬다). `sticky` 는 스크롤 영역 맨 위에 붙어 있는다 — 본문 헤더와 같이 고정으로 읽힌다.
   접기 버튼은 흐름 배치라 이 지정에 움직이지 않는다. */
[data-testid="stSidebarHeader"] {
  position: sticky;
  top: 0;
  /* 띠 위로 올린다. 띠에 가리면 라벨도 접기 버튼도 묻힌다. */
  z-index: 11;
  align-items: center;
}

/* 접기 버튼(<<)은 Streamlit 이 사이드바에 마우스를 올렸을 때만 `visibility: visible` 로 띄운다.
   있는 줄 모르고 지나치지 않게 늘 보이게 둔다. 인쇄에서 숨기는 Streamlit 규칙은 남기려고
   화면 매체에만 건다. */
@media screen {
  [data-testid="stSidebarCollapseButton"] {
    visibility: visible !important;
  }
}

/* 사이드바를 접으면 헤더 왼쪽 끝에 펼침 버튼이 나타나 첫 글자와 겹친다. 그 자리만큼 민다.
   민 만큼(2.5rem) 최대 폭도 줄여야 오른쪽 끝이 툴바 쪽으로 밀려 들어가지 않는다.
   사이드바와 헤더는 부모가 달라 형제 선택자가 닿지 않으므로 접힘 상태를 `:has()` 로 본다.
   `:has()` 를 모르는 브라우저는 이 규칙만 버리고 접었을 때만 겹친다. */
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
  [data-testid="stHeader"]::before,
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
  [data-testid="stHeader"]::after {
  left: 4rem;
  max-width: calc(100% - 30.5rem);
}
"""

# 1400px 보다 좁은 창에서만 오른쪽 비움 폭을 지금 툴바의 실측에 맞춘다(2026-10-07). 위의 28rem 은
# 툴바에 Summary 가 있던 때 값이라, 1100px 창(사이드바 300px)에서 글자 폭이 408px 뿐이어서 긴
# 시나리오명·코드가 말줄임으로 잘렸다. 그 창의 실측(1rem = 14px): 툴바 단추 묶음은 Guide·테마·Print
# 와 개발 모드의 Deploy 까지 850px 부터(머리 띠 오른쪽 끝까지 250px), Deploy 가 없으면 903px 부터
# (197px)다. 여기에 글자 시작 21px, 왼쪽 띠 안쪽 여백·선 11px(최대 폭은 글자 칸에만 걸린다),
# 틈 12px, 테마 단추 글자가 `Light` 일 때 넓어지는 2px 를 더하면 296px·243px 라 21.5rem·17.5rem
# 으로 둔다(글자 칸 499px·555px — 위 28rem 일 때는 408px). Deploy 는 Streamlit 이 localhost
# 접속에서만 세우므로 사내 WebIDE 에서는 보통 없는 쪽이다 — 그 여부를 `:has()` 로 가른다.
# 사이드바를 접은 경우는 위 규칙과 같이 2.5rem 을 더 뺀다. 1400px 이상은 그대로 둔다.
#
# 말줄임이 끝내 남는 아주 긴 이름에 전체 글을 띄우는 풍선은 두지 않는다. 글은 가상요소라 `title`
# 을 달 자리가 없고(`pointer-events: none`), 풍선을 달려면 스크립트로 실제 요소를 넣어야 한다 —
# 이 모듈이 HOME 을 무겁게 하지 않으려고 피한 길이다. 전체 이름은 사이드바 시나리오 상자에 있다.
_NARROW_HEADER_RULES = """
@media (max-width: 1399.98px) {
  [data-testid="stHeader"]::before,
  [data-testid="stHeader"]::after {
    max-width: calc(100% - 21.5rem);
  }
  [data-testid="stHeader"]:not(:has([data-testid="stAppDeployButton"]))::before,
  [data-testid="stHeader"]:not(:has([data-testid="stAppDeployButton"]))::after {
    max-width: calc(100% - 17.5rem);
  }
  [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
    [data-testid="stHeader"]::before,
  [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
    [data-testid="stHeader"]::after {
    max-width: calc(100% - 24rem);
  }
  [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
    [data-testid="stHeader"]:not(:has([data-testid="stAppDeployButton"]))::before,
  [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
    [data-testid="stHeader"]:not(:has([data-testid="stAppDeployButton"]))::after {
    max-width: calc(100% - 20rem);
  }
}
"""


def source_type_label(source_type: str) -> str:
    """원천 유형을 머리 띠에 적는 이름."""
    if source_type.startswith(_CSV_SOURCE_PREFIX):
        return "CSV"
    return SOURCE_TYPE_LABELS.get(source_type, source_type)


def _day(value: datetime) -> str:
    return value.strftime("%y.%m.%d")


def header_lines(
    label: ActiveScenarioLabel | None,
    *,
    official: tuple[str, int] | None,
    unsaved: bool,
) -> tuple[str, str]:
    """머리 띠 두 줄(위·아래). 이름표가 없으면 앱 이름 한 줄이다(아래 줄은 빈 문자열).

    `official` 은 최신 공식버전의 (리비전 id, 번호)다. 올라와 있는 리비전이 그것이면 공식버전이다.
    미저장 변경이 있으면 상태는 그것이 먼저다 — 사이드바 시나리오 상자의 배지와 같은 차례다.
    """
    if label is None:
        return APP_NAME, ""
    is_official = official is not None and official[0] == label.revision_id
    if unsaved:
        status = STATUS_UNSAVED
    elif official is not None and is_official:
        status = STATUS_OFFICIAL.format(release_no=official[1])
    else:
        status = STATUS_SAVED
    top = f"{label.scenario_name} · r{label.revision_no} {label.revision_name} · {status}"
    parts = [label.simulation_code]
    if label.first_month is not None and label.last_month is not None:
        parts.append(f"적용 {month_label(label.first_month)}–{month_label(label.last_month)}")
    if is_official:
        parts.append(f"{source_type_label(label.source_type)} {_day(label.registered_at)} 등록")
    else:
        parts.append(f"{_day(label.saved_at)} 저장")
    return top, " · ".join(parts)


def css_string(text: str) -> str:
    """CSS 문자열(`content: "..."`) 안에 넣을 수 있게 바꾼다.

    역슬래시·큰따옴표는 앞에 역슬래시를, 줄바꿈 등 제어 문자는 빈칸으로 바꾼다(한 줄 띠다).
    `<`·`>`·`&` 는 CSS 코드 포인트 이스케이프로 적는다 — 시나리오명에 `</style>` 이 들어 있어도
    스타일 요소를 끝내지 못한다.
    """
    out: list[str] = []
    for char in text:
        if char in '\\"':
            out.append("\\" + char)
        elif char in "<>&":
            out.append(f"\\{ord(char):x} ")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def _header_css(top: str = APP_NAME, bottom: str = "") -> str:
    """이 실행의 팔레트와 두 줄로 헤더 CSS 를 만든다. 아래 줄이 비면 위 줄이 띠 가운데에 선다.

    사용자 글이 든 두 줄은 **맨 마지막에** 넣는다 — 시나리오명에 센티넬 글자(`__TEXT__` 등)가 들어
    있어도 다른 치환이 그것을 건드리지 못한다.
    """
    return (
        _HEADER_TEMPLATE.replace("__ACCENT__", tokens.ACCENT)
        .replace("__SURFACE__", tokens.SURFACE)
        .replace("__BAR_BORDER__", tokens.BORDER)
        .replace("__BAR__", tokens.HEADER_BAR)
        .replace("__FONT_FAMILY__", tokens.FONT_FAMILY)
        .replace("__TEXT_MUTED__", tokens.TEXT_MUTED)
        .replace("__TEXT__", tokens.TEXT)
        .replace("__TOP_OFFSET__", "calc(50% - 1.1rem)" if bottom else "calc(50% - 0.55rem)")
        .replace("__BOTTOM_LINE__", css_string(bottom))
        .replace("__TOP_LINE__", css_string(top))
    ) + _NARROW_HEADER_RULES


def render_app_header() -> None:
    """헤더 글을 그린다. 페이지마다 부르지 말고 `app.py` 에서 한 번만 부른다.

    `render_intro_summary` **뒤**여야 한다 — 최신 공식버전은 그 회차에 요약이 확인한 값이다.
    """
    top, bottom = header_lines(
        active_scenario_label(),
        official=latest_official_revision(),
        unsaved=has_unsaved_scenario_changes(),
    )
    st.html(f"<style>{_header_css(top, bottom)}</style>")


def render_shell_style() -> None:
    """⋮ 메뉴 감춤과 인쇄 규칙을 보낸다. `app.py` 가 부트스트랩보다 앞에서 매 회차 한 번 부른다.

    스타일만 든 `st.html` 이라 본문 자리를 먹지 않는다.
    """
    st.html(SHELL_STYLE)
