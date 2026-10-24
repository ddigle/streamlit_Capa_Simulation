# Purpose: 공정 Capa 상세의 세션·주소 인자 계약과 HOME 칸 클릭으로 그 화면을 여는 전달을 맡는다.

"""공정 Capa 상세로 들어오는 길과 그 화면의 보는 상태.

HOME `주요공정 확보율`·`상세 B/N 공정` 칸을 누르면 그 공정·그 달로 이 화면이 열린다(2026-10-15
사용자 결정). `Capa LOB 현황` 그림의 생산계획 LOB B/N 막대·B/N Top 5 막대도 같다(2026-10-18 사용자
요청). 넘기는 길은 둘이다.

- **전달 칸**(`PROCESS_DETAIL_REQUEST_KEY`) — 같은 세션 안의 1차 길. 위젯이 아닌 세션 칸이다. HOME
  이 상세 화면의 **위젯 키**에 바로 적으면 페이지를 옮긴 첫 회차에 `persist_state` 경로와 엇갈린다
  (`shared_widget_state`). 상세 화면이 위젯을 만들기 전에 이 칸을 꺼내 위젯 키에 적는다. 누른 칸의
  HOME 표시값·원 확보율·보정 증감과 그때의 HOME 보기 조건(선행 B/O·확보율 보정·EDP)을 함께 싣는다
  — 상세 화면의 출처 띠가 「HOME 표시값 = 원 확보율 + …」를 이것으로 적는다. 칸은 상세 화면이
  **맨 앞에서**(부트스트랩보다 먼저) 꺼낸다(`take_process_detail_request`) — 그 회차가 오류로 멈춰도
  칸이 남아 나중에 사이드바로 들어온 방문을 「HOME 에서 온 것」으로 읽지 않는다. 옮기지 못한
  클릭(`StreamlitPageNotFoundError`)도 칸을 남기지 않는다.
- **주소 인자**(`process`·`month`·`from`) — 링크를 나눌 때의 보조 길. `from` 은 들어온
  길이다 — `home`·`gap`(가용설비 현황 `Static 대비 일정` 의 「④ 에서 비가동 화살표로
  보기」)·`shortening`(필요 단축 일정 공정 카드의 「공정 Capa 상세에서 근거 보기」). 들어온 회차에는
  그 길이 가리키는 구획을 다시 편다(`ProcessDetailEntry.source`). 필요 단축 일정 카드는 그 카드의
  목표·기간·단축/신규 대수(`target`·`period`·`shortened`·`new`)도 싣는다 — 상세는 **이 주소 인자만**
  읽어 출처 띠를 낸다(`ShorteningOrigin`, `shortening_band_text`). 필요 단축 일정의 세션 칸·공용
  프로필은 읽지 않는다. `st.switch_page` 는 주소를 **통째로** 바꾸므로 테마
  인자(`theme`)는 지금 값을 함께 싣는다. 받는 쪽은 읽은 키만 지운다 —
  `st.query_params.clear()` 는 테마 인자까지 지워 테마 스크립트가 첫 방문으로 보고 다시 새로고침한다
  (Space `?floor=` 와 같은 규칙). 지우는 것은 한 번의 갱신이다(`from_dict` 에 남길 인자를 다시
  싣는다) — 키마다 지우면 브라우저 기록이 키마다 쌓여 뒤로가 헛돈다. 한 번 적용한 인자 묶음은
  `PROCESS_DETAIL_QUERY_SEEN_KEY` 에 남겨, 지운 것이 브라우저에 닿기 전에 옛 주소가 되돌아와도
  사용자가 그 뒤 고른 공정을 덮지 않는다. 인자가 걷힌 회차에 그 칸을 비우므로 같은 링크로 다시
  들어오면 다시 적용한다.

HOME 그림은 표적 막대(trace 0)의 `customdata` **끝**에 이동 정보 일곱 칸(`HOME_CELL_LINK_FIELDS`)을
싣는다 — `Capa LOB 현황` 은 값 막대와 그 위 증감 조각이 표적이다. hover 칸 차례는 그대로이고, 과거
실적 칸은 공정 자리를 비워(`None`) 콜백이 무시한다 — 과거 구간·연간 Total 달은 이 화면의 달 축
(조회기간 ∩ 소요 달)에 없다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.home_state import (
    ADVANCE_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    HOME_TOGGLE_DEFAULTS,
)
from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.page_bootstrap import prune_choice
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_picker import ProcessPickerItem
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

# 사이드바 `공정 상세 조건` 카드의 공정 선택 상자(원본 공정명).
PROCESS_DETAIL_PROCESS_KEY = "process_detail_process"
# 지금 보는 달(정수 `YYYYMM`). 위젯이 아니라 세션 칸이다 — 요약 표 칸·이전/다음 단추·HOME 진입이
# 모두 이 칸 하나를 적는다.
PROCESS_DETAIL_MONTH_KEY = "process_detail_month"
# 표 도구 줄의 「제품별 소요대수」 펼침과 펼쳤을 때의 「분류」, 카드의 제품 거르기(펼친 행에만
# 걸린다).
PROCESS_DETAIL_EXPAND_KEY = "process_detail_expand_products"
PROCESS_DETAIL_SPLIT_KEY = "process_detail_product_split"
PROCESS_DETAIL_PRODUCT_FILTER_KEY = "process_detail_product_filter"
# 표 도구 줄의 「구획」 칩(고른 것 = 펼친 구획 id, 세션 값). 칸이 없으면 넷 모두 펼침으로 심는다.
PROCESS_DETAIL_SECTIONS_KEY = "process_detail_sections"
# 머리 공정명 옆 ◀▶(확보기준 미달 공정을 최저 확보율이 낮은 차례로 넘긴다) 단추와, 그 차례를 낼
# 공정별 요약을 세션에 한 벌 기억하는 칸 — 키는 시나리오 키·표시순서 지문·판정 기준 지문이다.
PROCESS_DETAIL_PREVIOUS_PROCESS_KEY = "process_detail_previous_process"
PROCESS_DETAIL_NEXT_PROCESS_KEY = "process_detail_next_process"
PROCESS_DETAIL_PICKER_MEMO_KEY = "process_detail_picker_memo"
# 본문 프래그먼트(표 도구 줄·결합 캔버스·근거 패널)의 key 와 칸 선택을 켠 월 그림의 key. 칸을 누르면
# 콜백이 지금 보는 달을 적고 이 프래그먼트만 다시 돌린다(`rerun_fragment_if_alone`). 선택을 켠
# 그림은 그 위 터치 스크롤이 막히므로 `app.py` 가 이 그림 key 를 터치 스크롤
# 막이(`plotly_touch_scroll`)에 넘긴다.
PROCESS_DETAIL_VIEW_FRAGMENT_KEY = "process_detail_view"
PROCESS_DETAIL_CANVAS_CHART_KEY = "process_detail_summary_months"
# HOME 이 적고 상세 화면이 첫 회차에 꺼내(`pop`) 쓰는 전달 칸.
PROCESS_DETAIL_REQUEST_KEY = "process_detail_request"
# HOME 칸 클릭 콜백이 적는 이동 대기 칸. 같은 회차의 HOME 프래그먼트 본문 첫 줄이 꺼내
# (`switch_to_queued_process_detail`) 전달 칸에 옮겨 적고 화면을 옮긴다.
PROCESS_DETAIL_QUEUED_KEY = "process_detail_queued"
# 출처 띠가 읽는 HOME 칸 스냅숏. 전달 칸을 꺼낸 회차에 옮겨 두고, 공정을 바꾸거나 다른 화면에
# 다녀오면 걷는다.
PROCESS_DETAIL_ORIGIN_KEY = "process_detail_origin"
# 마지막으로 적용한 주소 인자 묶음.
PROCESS_DETAIL_QUERY_SEEN_KEY = "process_detail_query_seen"
# 결합 캔버스의 스크롤 시작 달 — (공정, 달). 새 방문·밖에서 들어옴(전달 칸·주소)·공정을 바꾼
# 회차에만 지금 달로 다시 정한다. 칸을 눌러 달을 옮긴 뒤 다른 조건으로 앱 전체가 돌아도 이 값은
# 그대로라 가로 스크롤바가 사용자가 옮겨 둔 위치를 그 달로 되돌리지 않는다.
PROCESS_DETAIL_SCROLL_ANCHOR_KEY = "process_detail_scroll_anchor"

# 필요 단축 일정 카드에서 들어온 방문의 출처 띠가 읽는 그 카드의 값(`ShorteningOrigin`). 그 공정을
# 보는 동안만 있다 — HOME 출처(`PROCESS_DETAIL_ORIGIN_KEY`)와 같은 규칙.
PROCESS_DETAIL_SHORTENING_ORIGIN_KEY = "process_detail_shortening_origin"
# 이 방문의 설비 시나리오 기준. HOME 칸으로 들어온 방문은 `"official"`(E5 — HOME 칸은 공식) — ◀▶
# 로 공정을 넘겨도 그 방문 동안 남는다(출처 띠와 달리 공정이 바뀌어도 걷지 않는다). 새 방문·다른
# 길(사이드바·카드·주소)로 들어오면 걷어 세션의 설비 시나리오를 따른다.
PROCESS_DETAIL_EQUIPMENT_BASIS_KEY = "process_detail_equipment_basis"
EQUIPMENT_BASIS_OFFICIAL = "official"

PROCESS_PARAM = "process"
MONTH_PARAM = "month"
FROM_PARAM = "from"
# 필요 단축 일정 카드가 함께 싣는 그 카드의 목표(비율, 1.1)·기간(`YYYYMM-YYYYMM`)·단축/신규 대수.
TARGET_PARAM = "target"
PERIOD_PARAM = "period"
SHORTENED_PARAM = "shortened"
NEW_PARAM = "new"
# 그 카드가 본 설비 시나리오 한 마디(「셋업 실무 r4」·「공식 v3」) — 표시용이다. 받은 화면의 기준과
# 다르면 출처 띠가 그 사실을 적는다(새 탭으로 연 경우 등). 이 화면의 설비 기준은 바꾸지 않는다.
EQUIPMENT_PARAM = "eq"
DETAIL_QUERY_PARAMS = (
    PROCESS_PARAM,
    MONTH_PARAM,
    FROM_PARAM,
    TARGET_PARAM,
    PERIOD_PARAM,
    SHORTENED_PARAM,
    NEW_PARAM,
    EQUIPMENT_PARAM,
)
FROM_HOME = "home"
# 가용설비 현황 `Static 대비 일정` 의 「④ 에서 비가동 화살표로 보기」 링크와 필요 단축 일정 공정
# 카드 링크가 싣는 `from` 값.
FROM_GAP = "gap"
FROM_SHORTENING = "shortening"

# 출처 띠가 부르는 HOME 구획 이름. HOME 의 구획 제목과 같은 글자다.
HOME_KEY_PROCESS_SECTION = "주요공정 확보율"
HOME_BOTTLENECK_SECTION = "상세 B/N 공정"
# `Capa LOB 현황` 그림(생산계획 LOB 의 B/N 막대 · B/N Top 5 막대)은 한 그림이라 구획 제목 대신 그림
# 제목을 쓴다.
HOME_LOB_SECTION = "Capa LOB 현황"

# 표적 막대 `customdata` 끝의 이동 정보 차례. 그림(`home_cell_link_values`)과 콜백
# (`parse_home_cell_link`)이 이 한 벌을 본다 — 앞의 hover 칸 수와 무관하게 끝에서 센다.
HOME_CELL_LINK_FIELDS = (
    "process",
    "month",
    "displayed_rate",
    "raw_rate",
    "available",
    "required",
    "execution_delta",
)


@dataclass(frozen=True)
class HomeCellLink:
    """HOME 칸 하나가 싣는 이동 정보. 확보율은 비율(1.05 = 105%), 보정 증감은 퍼센트포인트다."""

    process: str
    month: int
    displayed_rate: float | None
    # 가용대수 ÷ 소요대수 — 확보율 보정·선행 B/O 를 얹기 전의 값.
    raw_rate: float | None
    available: float | None
    required: float | None
    execution_delta: float


@dataclass(frozen=True)
class ProcessDetailRequest:
    """전달 칸 하나 — 어느 공정·달을 열지와, HOME 에서 왔으면 누른 칸과 그때의 보기 조건."""

    process: str
    month: int | None
    # 주소 `from` 값. HOME 에서 열면 `FROM_HOME`.
    source: str = FROM_HOME
    section: str = ""
    displayed_rate: float | None = None
    raw_rate: float | None = None
    available: float | None = None
    required: float | None = None
    execution_delta: float = 0.0
    show_advance: bool = False
    show_execution: bool = False
    include_edp: bool = False


@dataclass(frozen=True)
class ShorteningOrigin:
    """필요 단축 일정 공정 카드에서 들어온 방문 — **주소 인자로 받은** 그 카드의 값만 든다.

    목표는 비율(1.1 = 110%), 기간은 그 카드의 조회 달(시작·끝 `YYYYMM`), 대수는 그 카드의 단축 호기·
    신규(추가N) 대수다. 인자가 없거나 읽을 수 없는 칸은 None 이고 띠에서 뺀다.
    """

    process: str
    target: float | None = None
    start_month: int | None = None
    end_month: int | None = None
    shortened: int | None = None
    new: int | None = None
    # 그 카드가 본 설비 시나리오 한 마디(`EQUIPMENT_PARAM`). 표시용이다.
    equipment: str | None = None


@dataclass(frozen=True)
class ProcessDetailEntry:
    """페이지 첫머리에서 정한 공정·달과 출처."""

    process: str | None
    month: int | None
    # 출처 띠의 근거. HOME 에서 넘겨받은 방문 동안, 그 공정을 보는 동안만 있다.
    origin: ProcessDetailRequest | None = None
    # 넘겨받은 공정이 지금 공정 목록에 없어 기본 공정을 연 경우 그 공정.
    missing_process: str | None = None
    # 넘겨받은 달이 이 화면의 달 축 밖이라 다른 달을 연 경우 그 달.
    month_outside: int | None = None
    # 결합 캔버스의 스크롤 시작 달(`PROCESS_DETAIL_SCROLL_ANCHOR_KEY`). 회차마다 바뀌지 않는다.
    scroll_month: int | None = None
    # 밖에서 들어온 회차(전달 칸·주소)의 길 — HOME 전달 칸이면 `FROM_HOME`, 주소면 `from` 값(없으면
    # 빈 글자). 들어온 회차가 아니면 None 이다. 페이지가 그 길이 가리키는 구획을 다시 편다.
    source: str | None = None
    # 필요 단축 일정 카드 출처 띠의 근거. 그 카드 링크로 들어온 방문 동안, 그 공정을 보는 동안만
    # 있다.
    shortening_origin: ShorteningOrigin | None = None
    # 이 방문의 설비 시나리오 기준 — `EQUIPMENT_BASIS_OFFICIAL`(HOME 칸 방문) 또는 None(세션).
    equipment_basis: str | None = None


def _finite(value: object) -> float | None:
    """유한한 숫자면 float, 아니면(결측·NaN·무한대·글자) None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _month(value: object) -> int | None:
    """정수 `YYYYMM` 으로 읽는다. 여섯 자리가 아니거나 달이 1~12 가 아니면 None."""
    number = _finite(value)
    if number is None or not number.is_integer():
        return None
    month = int(number)
    return month if 100_001 <= month <= 999_912 and 1 <= month % 100 <= 12 else None


def home_cell_link_values(
    *,
    process: object,
    month: object,
    displayed_rate: object,
    available: object,
    required: object,
    execution_delta: object,
    linked: bool = True,
) -> list[object]:
    """표적 막대 칸 하나의 `customdata` 꼬리(`HOME_CELL_LINK_FIELDS` 차례).

    `linked=False`(과거 실적 칸)는 일곱 칸 모두 `None` 이다 — 콜백은 공정 자리가 비면 그 점을
    무시한다. 원 확보율은 가용대수 ÷ 소요대수로 다시 낸다: HOME 의 `확보율`·`기준 확보율` 은
    선행 B/O 를 켜면 변동률이 함께 곱해져 원 값이 남지 않는다.
    """
    if not linked:
        return [None] * len(HOME_CELL_LINK_FIELDS)
    parsed_month = _month(month)
    available_count = _finite(available)
    required_count = _finite(required)
    raw_rate = (
        available_count / required_count
        if available_count is not None and required_count is not None and required_count > 0
        else None
    )
    return [
        str(process).strip() or None,
        parsed_month,
        _finite(displayed_rate),
        raw_rate,
        available_count,
        required_count,
        _finite(execution_delta) or 0.0,
    ]


def parse_home_cell_link(customdata: object) -> HomeCellLink | None:
    """선택된 점의 `customdata` 꼬리를 읽는다. 공정·달이 없으면(과거 실적 칸 등) None."""
    if not isinstance(customdata, Sequence) or isinstance(customdata, str):
        return None
    width = len(HOME_CELL_LINK_FIELDS)
    if len(customdata) < width:
        return None
    process, month, displayed, raw, available, required, delta = customdata[-width:]
    if not isinstance(process, str) or not process.strip():
        return None
    parsed_month = _month(month)
    if parsed_month is None:
        return None
    return HomeCellLink(
        process=process.strip(),
        month=parsed_month,
        displayed_rate=_finite(displayed),
        raw_rate=_finite(raw),
        available=_finite(available),
        required=_finite(required),
        execution_delta=_finite(delta) or 0.0,
    )


def first_home_cell_link(selection_state: object) -> HomeCellLink | None:
    """`st.plotly_chart` 선택 상태(`{"selection": {"points": [...]}}`)에서 이동할 첫 칸.

    빈 선택(같은 칸을 다시 누르거나 더블클릭하면 빈 선택이 온다)과 공정 없는 점은 None 이다.
    """
    if not isinstance(selection_state, Mapping):
        return None
    selection = selection_state.get("selection")
    if not isinstance(selection, Mapping):
        return None
    points = selection.get("points")
    if not isinstance(points, Sequence) or isinstance(points, str):
        return None
    for point in points:
        if isinstance(point, Mapping):
            link = parse_home_cell_link(point.get("customdata"))
            if link is not None:
                return link
    return None


def home_cell_request(link: HomeCellLink, *, section: str) -> ProcessDetailRequest:
    """누른 칸과 **지금** HOME 보기 조건으로 전달 칸 값을 만든다.

    토글은 위젯 키(`home_state`)를 그대로 읽는다. 토글을 바꾸면 HOME 이 앱 전체로 다시 돌아 그림이
    바뀌므로 누른 그림과 이 값은 늘 같은 조건이다.
    """

    def toggle(key: str) -> bool:
        return bool(st.session_state.get(key, HOME_TOGGLE_DEFAULTS[key]))

    return ProcessDetailRequest(
        process=link.process,
        month=link.month,
        source=FROM_HOME,
        section=section,
        displayed_rate=link.displayed_rate,
        raw_rate=link.raw_rate,
        available=link.available,
        required=link.required,
        execution_delta=link.execution_delta,
        show_advance=toggle(ADVANCE_TOGGLE_KEY),
        show_execution=toggle(EXECUTION_TOGGLE_KEY),
        include_edp=toggle(EDP_TOGGLE_KEY),
    )


def request_query_params(request: ProcessDetailRequest, *, theme: str | None) -> dict[str, str]:
    """`st.switch_page` 에 넘길 주소 인자. 달이 없으면 공정·출처만, 테마는 값이 있을 때만 싣는다."""
    params = {PROCESS_PARAM: request.process}
    if request.month is not None:
        params[MONTH_PARAM] = str(request.month)
    if request.source:
        params[FROM_PARAM] = request.source
    if theme:
        params[THEME_QUERY_PARAM] = theme
    return params


def _count(value: object) -> int | None:
    """0 이상의 정수 글. 아니면 None."""
    number = _finite(value)
    if number is None or not number.is_integer() or number < 0:
        return None
    return int(number)


def _target(value: object) -> float | None:
    """목표 비율 글(`1.1`). 0 보다 크고 5 이하만 받는다 — 아니면 None."""
    number = _finite(value)
    return number if number is not None and 0 < number <= 5 else None


def _period(value: object) -> tuple[int | None, int | None]:
    """`YYYYMM-YYYYMM` 글. 읽을 수 없거나 차례가 거꾸로면 (None, None)."""
    if not isinstance(value, str) or "-" not in value:
        return None, None
    start, end = (_month(part.strip()) for part in value.split("-", 1))
    if start is None or end is None or start > end:
        return None, None
    return start, end


def shortening_card_query_params(
    *,
    process: str,
    month: int | None,
    target: float,
    start_month: int,
    end_month: int,
    shortened: int,
    new: int,
    theme: str | None,
    equipment: str | None = None,
) -> dict[str, str]:
    """필요 단축 일정 공정 카드의 「공정 Capa 상세에서 근거 보기」 링크 주소 인자.

    `equipment` 는 그 카드가 본 설비 시나리오 한 마디(「셋업 실무 r4」)다 — 표시용 `eq` 인자로만
    싣는다(값이 있을 때만).

    달은 그 카드의 첫 부족 달(없으면 싣지 않는다 — 상세가 그 공정의 기본 달을 연다), 목표는 비율
    글, 기간은 `YYYYMM-YYYYMM` 이다. 테마는 값이 있을 때만 싣는다(`request_query_params` 와 같은
    까닭 — 링크는 주소를 통째로 바꾼다).
    """
    params = {PROCESS_PARAM: str(process)}
    if month is not None:
        params[MONTH_PARAM] = str(int(month))
    params[FROM_PARAM] = FROM_SHORTENING
    params[TARGET_PARAM] = f"{float(target):g}"
    params[PERIOD_PARAM] = f"{int(start_month)}-{int(end_month)}"
    params[SHORTENED_PARAM] = str(int(shortened))
    params[NEW_PARAM] = str(int(new))
    if equipment:
        params[EQUIPMENT_PARAM] = str(equipment)
    if theme:
        params[THEME_QUERY_PARAM] = theme
    return params


def _shortening_origin(process: str, values: Mapping[str, str]) -> ShorteningOrigin:
    start, end = _period(values.get(PERIOD_PARAM))
    return ShorteningOrigin(
        process=process,
        target=_target(values.get(TARGET_PARAM)),
        start_month=start,
        end_month=end,
        shortened=_count(values.get(SHORTENED_PARAM)),
        new=_count(values.get(NEW_PARAM)),
        equipment=(values.get(EQUIPMENT_PARAM) or "").strip() or None,
    )


def open_process_detail(request: ProcessDetailRequest) -> None:
    """전달 칸을 적고 공정 Capa 상세로 옮긴다. **위젯 콜백이 아니라 회차 본문에서** 부른다.

    Streamlit 1.63 의 `st.switch_page` 는 회차를 끊으려고 끝에 `st.empty()` 를 그린다. 프래그먼트
    콜백 안에서 부르면 그 그리기가 「A fragment rerun was triggered with a callback that displays
    one or more elements」 경고를 서버 로그에 남긴다(사내 리뷰 202610182227 — 화면 해는 없다).
    본문에서 부르면 그 `st.empty()` 는 보내지기 전에 이동 요청이 회차를 끊는다. 갈 곳이
    없으면(내비게이션이 없는 단독 실행 — AppTest 는 등록된 페이지가 없다) 옮기지 않고 적은 전달 칸도
    거둔다. 남겨 두면 나중에 사이드바로 들어온 방문이 이 클릭의 출처 띠를 단다.
    """
    st.session_state[PROCESS_DETAIL_REQUEST_KEY] = request
    theme = st.query_params.get(THEME_QUERY_PARAM)
    try:
        st.switch_page(
            PROCESS_CAPA_DETAIL.path,
            query_params=request_query_params(request, theme=theme),
        )
    except StreamlitPageNotFoundError:
        st.session_state.pop(PROCESS_DETAIL_REQUEST_KEY, None)


def queue_home_cell(selection_state: object, *, section: str) -> bool:
    """HOME 그림의 선택 상태를 이동 대기 칸에 적는다. **위젯 콜백에서** 부른다.

    열 칸이 없으면(빈 선택·과거 칸) 아무것도 않는다. 옮기는 것은 같은 회차의 HOME 프래그먼트 본문
    첫 줄이다(`switch_to_queued_process_detail`). 토글은 지금 값을 읽어 여기서 굳힌다.
    """
    link = first_home_cell_link(selection_state)
    if link is None:
        return False
    st.session_state[PROCESS_DETAIL_QUEUED_KEY] = home_cell_request(link, section=section)
    return True


def switch_to_queued_process_detail() -> None:
    """이동 대기 칸이 있으면 꺼내 공정 Capa 상세로 옮긴다. HOME 프래그먼트 본문 **첫 줄**에서
    부른다.

    숨은 탭·그림 없는 회차에서 일찍 돌아가기 전이어야 한다 — 클릭이 앱 전체 회차로 묶여 Main 이
    숨은 채 돌아도 HOME 은 이 프래그먼트를 늘 부르므로 대기 칸이 다음 HOME 방문까지 남지 않는다.
    """
    request = st.session_state.pop(PROCESS_DETAIL_QUEUED_KEY, None)
    if isinstance(request, ProcessDetailRequest):
        open_process_detail(request)


def lowest_rate_process(items: Sequence[ProcessPickerItem]) -> str | None:
    """기본 공정 — 조회기간 최저 확보율이 가장 낮은 공정. 같으면 목록 차례가 앞선 공정이다.

    판정할 확보율이 하나도 없으면(모든 공정이 `unavailable`) 목록 첫 공정, 목록이 비면 None.
    공정 선택 팝업의 요약(`services/process_picker.build_process_picker_summary`)을 그대로 읽는다.
    """
    rated = [item for item in items if item.minimum_rate is not None]
    if rated:
        return min(rated, key=lambda item: cast(float, item.minimum_rate)).process
    return items[0].process if items else None


def first_shortfall_month(
    rates: Iterable[tuple[object, object]], thresholds: SecurementThresholds
) -> int | None:
    """기본 달 — 달 차례로 그 달 확보기준에 못 미친 첫 달. 없으면 None(부르는 쪽이 첫 달을 연다).

    `rates` 는 (정수 `YYYYMM`, 확보율) 짝이다. 판정은 HOME·Static Capa 와 같은 `thresholds.status`
    한 길이다 — 「확보」가 아니면(경고·부족) 미달이다. 확보율이 없는 달은 건너뛴다.
    """
    judged = sorted(
        (month, rate)
        for month, rate in ((_month(month), _finite(rate)) for month, rate in rates)
        if month is not None and rate is not None
    )
    for month, rate in judged:
        if thresholds.status(rate, month) != "secure":
            return month
    return None


def take_process_detail_request() -> ProcessDetailRequest | None:
    """전달 칸을 꺼낸다(`pop`). 상세 화면이 **맨 앞에서**, 부트스트랩·계산보다 먼저 부른다.

    꺼낸 값은 지역 변수로 들고 있다가 `resolve_process_and_month(request=…)` 에 넘긴다. 칸을
    공정·달을 정하는 자리에서야 꺼내면, 그 앞에서 부트스트랩·계산 오류로 멈춘 회차가 칸을 남기고 —
    나중에 사이드바로 들어온 방문이 그 칸을 「HOME 에서 온 것」으로 읽는다. 꺼낸 뒤 사용자 조작으로
    끊긴 회차는 출처 띠만 잃는다 — 주소 인자(`process`·`month`)는 정하는 자리에서야 지우므로 다음
    회차가 같은 공정·달을 연다.
    """
    request = st.session_state.pop(PROCESS_DETAIL_REQUEST_KEY, None)
    return request if isinstance(request, ProcessDetailRequest) else None


def _read_detail_query() -> tuple[tuple[str, str], ...]:
    """주소에 있는 이 화면의 인자만 (이름, 값) 차례로. 다른 인자(`theme` 등)는 보지 않는다."""
    found: list[tuple[str, str]] = []
    for name in DETAIL_QUERY_PARAMS:
        if name in st.query_params:
            found.append((name, str(st.query_params.get(name, ""))))
    return tuple(found)


def _continues_this_page() -> bool:
    """직전에 끝까지 돈 실행도 이 페이지였나. 판정하지 못하면 False — 새 방문으로 본다.

    `app.py` 맨 위의 실행 표지(`sidebar_status.begin_app_run`)는 실행이 끝까지 돌았을 때 그 페이지를
    적는다. 이번 실행 도중에 읽으면 직전에 끝까지 돈 실행의 페이지다(`complete` 는 이번 실행이 이미
    내려 두었으므로 보지 않는다). 표지가 없는 단독 실행(페이지만 띄운 시험)은 늘 새 방문이다.
    """
    state = st.session_state.get(APP_RUN_STATE_KEY)
    ctx = get_script_run_ctx(suppress_warning=True)
    return isinstance(state, dict) and ctx is not None and state.get("page") == ctx.page_script_hash


def resolve_process_and_month(
    processes: Sequence[str],
    months: Sequence[int],
    *,
    request: ProcessDetailRequest | None,
    default_process: Callable[[], str | None] | str | None,
    default_month: Callable[[str | None], int | None] | int | None = None,
) -> ProcessDetailEntry:
    """페이지 첫머리, **공정 선택 상자를 만들기 전에** 부른다. 공정·달을 정해 세션에 적는다.

    차례:
    1. 페이지가 맨 앞에서 꺼낸 전달 칸(`request` — `take_process_detail_request`). HOME 이 적은 값이
       있으면 그것이 답이다.
    2. 없으면 주소 인자가 마지막으로 적용한 묶음(`PROCESS_DETAIL_QUERY_SEEN_KEY`)과 다를 때만
       적용한다. 읽은 인자는 그 키만 지운다.
    3. 둘 다 없으면 세션 값(지난번에 보던 공정·달)이다. 공정을 바꿔도 보던 달은 그대로다.
    4. 세션도 비었으면 기본값 — 공정은 `default_process`, 달은 `default_month`. 둘 다 함수일 수
       있고(공정은 인자 없이, 달은 공정을 받아 — 그 공정의 첫 확보기준 미달 달 같은 것), 함수는
       **기본값이 필요한 회차에만** 부른다. 세션·전달 칸·주소로 공정이 정해진 회차는 기본 공정
       요약을 만들지 않는다.
    5. 지금 목록에 맞춘다(`prune_choice`). 넘겨받은 공정이 목록에 없으면 기본 공정을 열고
       `missing_process` 로, 달이 축 밖이면 기본 달을 열고 `month_outside` 로 알린다.

    밖에서 들어온(1·2) 공정에 달이 없으면 지난번 달이 아니라 그 공정의 기본 달을 연다.

    스크롤 시작 달(`scroll_month`)은 새 방문·밖에서 들어온 회차·공정을 바꾼 회차(그리고 그 달이 축을
    벗어난 회차)에만 지금 달로 다시 정한다 — 칸을 눌러 달을 옮긴 뒤의 앱 전체 회차(제품 거르기 등)는
    그 값을 그대로 넘겨 보던 가로 위치를 되돌리지 않는다.
    """
    options = [str(process) for process in processes]
    month_options = [int(month) for month in months]

    query = _read_detail_query()
    wanted_process: str | None = None
    wanted_month: int | None = None
    entered = False
    source: str | None = None
    arrived_from_card: ShorteningOrigin | None = None
    if request is not None:
        wanted_process, wanted_month, entered = request.process, request.month, True
        source = request.source
    elif query and query != st.session_state.get(PROCESS_DETAIL_QUERY_SEEN_KEY):
        values = dict(query)
        wanted_process = values.get(PROCESS_PARAM, "").strip() or None
        wanted_month = _month(values.get(MONTH_PARAM))
        entered = wanted_process is not None or wanted_month is not None
        if entered:
            source = values.get(FROM_PARAM, "").strip()
        if source == FROM_SHORTENING and wanted_process is not None:
            arrived_from_card = _shortening_origin(wanted_process, values)
    if query:
        st.session_state[PROCESS_DETAIL_QUERY_SEEN_KEY] = query
        # 키마다 지우면 주소 메시지가 키 수만큼 가고, 브라우저가 메시지마다 기록을 하나씩 쌓아
        # 뒤로를 눌러도 같은 화면이 그만큼 이어진다 — 남길 인자를 다시 실어 한 번에 바꾼다.
        read = {name for name, _ in query}
        st.query_params.from_dict(
            {name: st.query_params.get_all(name) for name in st.query_params if name not in read}
        )
    else:
        # 주소에서 인자가 걷힌 뒤의 회차다. 같은 링크로 다시 들어오면 그때는 다시 적용한다.
        st.session_state.pop(PROCESS_DETAIL_QUERY_SEEN_KEY, None)

    fallback_memo: list[str | None] = []

    def fallback_process() -> str | None:
        # 기본 공정은 비쌀 수 있다(공정별 요약). 필요한 회차에 한 번만 낸다.
        if not fallback_memo:
            chosen = default_process() if callable(default_process) else default_process
            fallback_memo.append(chosen if chosen in options else (options[0] if options else None))
        return fallback_memo[0]

    missing_process: str | None = None
    if wanted_process is not None:
        if wanted_process in options:
            st.session_state[PROCESS_DETAIL_PROCESS_KEY] = wanted_process
        else:
            missing_process = wanted_process
            st.session_state[PROCESS_DETAIL_PROCESS_KEY] = fallback_process()
    saved_process = st.session_state.get(PROCESS_DETAIL_PROCESS_KEY)
    keeps_saved = saved_process is not None and str(saved_process) in set(options)
    process = prune_choice(
        PROCESS_DETAIL_PROCESS_KEY,
        options,
        default=None if keeps_saved else fallback_process(),
    )

    def default_month_of(chosen: str | None) -> int | None:
        value = default_month(chosen) if callable(default_month) else default_month
        if value in month_options:
            return value
        return month_options[0] if month_options else None

    month_outside: int | None = None
    if wanted_month is not None and wanted_month in month_options:
        month: int | None = wanted_month
    elif wanted_month is not None or entered:
        month_outside = wanted_month
        month = default_month_of(process)
    else:
        saved = st.session_state.get(PROCESS_DETAIL_MONTH_KEY)
        month = saved if isinstance(saved, int) and saved in month_options else None
        if month is None:
            month = default_month_of(process)
    st.session_state[PROCESS_DETAIL_MONTH_KEY] = month

    continues = _continues_this_page()
    anchor = st.session_state.get(PROCESS_DETAIL_SCROLL_ANCHOR_KEY)
    if (
        entered
        or not continues
        or not isinstance(anchor, tuple)
        or len(anchor) != 2
        or anchor[0] != process
        or anchor[1] not in month_options
    ):
        anchor = (process, month)
        st.session_state[PROCESS_DETAIL_SCROLL_ANCHOR_KEY] = anchor
    scroll_month = anchor[1] if isinstance(anchor[1], int) else None

    if request is not None and request.source == FROM_HOME:
        st.session_state[PROCESS_DETAIL_ORIGIN_KEY] = request
    elif not continues or entered:
        st.session_state.pop(PROCESS_DETAIL_ORIGIN_KEY, None)
    origin = st.session_state.get(PROCESS_DETAIL_ORIGIN_KEY)
    if not isinstance(origin, ProcessDetailRequest) or origin.process != process:
        st.session_state.pop(PROCESS_DETAIL_ORIGIN_KEY, None)
        origin = None
    # 필요 단축 일정 카드 출처도 같은 규칙 — 그 링크로 들어온 회차에 적고, 새 방문·다른 길로 들어옴·
    # 다른 공정이면 걷는다.
    if arrived_from_card is not None:
        st.session_state[PROCESS_DETAIL_SHORTENING_ORIGIN_KEY] = arrived_from_card
    elif not continues or entered:
        st.session_state.pop(PROCESS_DETAIL_SHORTENING_ORIGIN_KEY, None)
    card_origin = st.session_state.get(PROCESS_DETAIL_SHORTENING_ORIGIN_KEY)
    if not isinstance(card_origin, ShorteningOrigin) or card_origin.process != process:
        st.session_state.pop(PROCESS_DETAIL_SHORTENING_ORIGIN_KEY, None)
        card_origin = None
    # 설비 시나리오 기준 — HOME 칸으로 들어온 방문은 공식(E5). 출처 띠와 달리 ◀▶ 로 공정을 넘겨도
    # 그 방문 동안 남는다(같은 화면에서 설비 기준이 말없이 바뀌지 않게). 새 방문·다른 길이면 걷는다.
    if request is not None and request.source == FROM_HOME:
        st.session_state[PROCESS_DETAIL_EQUIPMENT_BASIS_KEY] = EQUIPMENT_BASIS_OFFICIAL
    elif not continues or entered:
        st.session_state.pop(PROCESS_DETAIL_EQUIPMENT_BASIS_KEY, None)
    basis = st.session_state.get(PROCESS_DETAIL_EQUIPMENT_BASIS_KEY)
    return ProcessDetailEntry(
        process=process,
        month=month,
        origin=origin,
        missing_process=missing_process,
        month_outside=month_outside,
        scroll_month=scroll_month,
        source=source,
        shortening_origin=card_origin,
        equipment_basis=basis if basis == EQUIPMENT_BASIS_OFFICIAL else None,
    )


# ------------------------------------------------------------------ 공정 넘기기(◀▶)


def remembered_picker_summary(
    key: object, build: Callable[[], Sequence[ProcessPickerItem]]
) -> tuple[ProcessPickerItem, ...]:
    """공정별 요약(`build_process_picker_summary`)을 세션에 한 벌 기억한다.

    기본 공정(최저 확보율 공정)과 ◀▶ 차례가 함께 읽는다. `key` 는 그 요약을 바꾸는 입력 전부
    — 시나리오 키(내용 토큰·기간)·표시순서 지문·판정 기준 지문 — 다. 새 `st.cache_data` 를 두지
    않는다.
    """
    memo = st.session_state.get(PROCESS_DETAIL_PICKER_MEMO_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == key:
        return cast(tuple[ProcessPickerItem, ...], memo[1])
    items = tuple(build())
    st.session_state[PROCESS_DETAIL_PICKER_MEMO_KEY] = (key, items)
    return items


@dataclass(frozen=True)
class ProcessStep:
    """◀▶ 한 쪽이 옮겨 갈 공정. `month` 는 그 공정의 첫 확보기준 미달 달(없으면 None)."""

    process: str
    minimum_rate: float | None
    month: int | None


@dataclass(frozen=True)
class ProcessSteps:
    """지금 공정에서 본 ◀▶ — 확보기준 미달 공정 차례(최저 확보율이 낮은 차례)의 앞·뒤."""

    previous: ProcessStep | None
    following: ProcessStep | None
    position: int | None
    """지금 공정의 차례(1부터). 미달 공정이 아니면 None — ▶ 가 첫 미달 공정이다."""

    total: int


def process_steps(
    order: Sequence[ProcessPickerItem],
    current: str,
    *,
    month_of: Callable[[str], int | None],
) -> ProcessSteps:
    """미달 공정 차례(`process_picker.shortfall_order`)에서 지금 공정의 앞·뒤를 낸다.

    지금 공정이 차례에 없으면(확보 공정) ◀ 는 없고 ▶ 는 가장 낮은 미달 공정이다. 달은 옮겨 갈 두
    공정에만 묻는다(`month_of` — 그 공정의 첫 확보기준 미달 달).
    """
    processes = [item.process for item in order]

    def step(index: int) -> ProcessStep | None:
        if not 0 <= index < len(order):
            return None
        item = order[index]
        return ProcessStep(item.process, item.minimum_rate, month_of(item.process))

    if current in processes:
        index = processes.index(current)
        return ProcessSteps(step(index - 1), step(index + 1), index + 1, len(order))
    return ProcessSteps(None, step(0), None, len(order))


def step_to_process(process: str, month: int | None) -> None:
    """◀▶ 콜백 — 공정 상자 값과 보는 달(그 공정의 첫 미달 달)을 적는다. 앱 전체 회차로 다시 돈다.

    상자보다 먼저 공정·달을 정하는 `resolve_process_and_month` 가 다음 회차에 세션 값으로 읽는다 —
    공정이 바뀌었으므로 스크롤 시작 달도 그 달로 다시 선다. 달이 없으면(미달 달을 못 낸 공정) 보던
    달을 둔다.
    """
    st.session_state[PROCESS_DETAIL_PROCESS_KEY] = process
    if month is not None:
        st.session_state[PROCESS_DETAIL_MONTH_KEY] = int(month)


# 출처 띠 앞 아이콘. 띠는 알림 상자가 아니라 캡션 한 줄이다 — 알림 상자 세 색은 뜻으로 가르고
# (`docs/design_system.md` 2-3) 출처는 그 어느 뜻도 아니다.
ORIGIN_BAND_ICON = ":material/call_received:"


def _percent(rate: float) -> str:
    return f"{rate:.0%}"


def origin_band_text(origin: ProcessDetailRequest, *, month_text: str) -> str:
    """출처 띠 한 줄. HOME 표시값이 원 확보율과 어떻게 갈리는지 적는다.

    HOME 확보율 = (원 확보율 + 확보율 보정 %p) × 선행 B/O 변동률이다(`execution_capacity`·
    `advance_load`). 이 화면의 표는 원 확보율이므로 차이를 먼저 밝힌다. 예: 「HOME 주요공정 확보율 ·
    26.03 칸에서 열었습니다 · 표시 103% = 원 확보율 98% + 확보율 보정 +5.0%p · 아래는 원 확보율」.
    """
    place = f"{origin.section} · {month_text}" if origin.section else month_text
    head = f"HOME {place} 칸에서 열었습니다"
    displayed, raw = origin.displayed_rate, origin.raw_rate
    if displayed is None or raw is None:
        return head
    adjusted = bool(origin.execution_delta) or (origin.show_advance and displayed != raw)
    if not adjusted:
        return f"{head} · 표시 {_percent(displayed)} = 원 확보율(아래 표와 같은 값)"
    formula = f"표시 {_percent(displayed)} = 원 확보율 {_percent(raw)}"
    if origin.execution_delta:
        formula += f" + 확보율 보정 {origin.execution_delta:+.1f}%p"
    if origin.show_advance:
        formula += " (선행 B/O 반영)"
    return f"{head} · {formula} · 아래는 원 확보율"


def _target_text(target: float) -> str:
    return f"{round(target * 100)}%({target:.2f})"


def shortening_band_text(origin: ShorteningOrigin) -> str:
    """필요 단축 일정 카드 출처 띠 한 줄 — 주소 인자로 받은 그 카드의 값만 적는다.

    두 화면의 단축 정의는 다르다(이 화면은 HOME 확보기준 월별·`RQ_REQB` 기간, 필요 단축 일정은 그
    카드의 목표 스칼라·조건 카드 기간 — 2026-10-22 맞추지 않기로). 그래서 그 카드의 대수를 그대로
    옮겨 적고 이 화면의 대수와 다를 수 있다고 먼저 밝힌다. 예: 「필요 단축 일정 카드(목표 110%(1.10)
    · 기간 26.01–26.12)에서 열었습니다 · 이 화면은 확보기준·RQ_REQB 기간 기준이라 대수가 다를 수
    있습니다 · 그 카드: 단축 3대 · 신규 1대」.
    """
    card: list[str] = []
    if origin.target is not None:
        card.append(f"목표 {_target_text(origin.target)}")
    if origin.start_month is not None and origin.end_month is not None:
        card.append(f"기간 {month_label(origin.start_month)}–{month_label(origin.end_month)}")
    head = "필요 단축 일정 카드" + (f"({' · '.join(card)})" if card else "") + "에서 열었습니다"
    parts = [head, "이 화면은 확보기준·RQ_REQB 기간 기준이라 대수가 다를 수 있습니다"]
    if origin.shortened is not None and origin.new is not None:
        parts.append(f"그 카드: 단축 {origin.shortened}대 · 신규 {origin.new}대")
    return " · ".join(parts)


def equipment_band_tail(card: str | None, here: str | None) -> str | None:
    """출처 띠 끝 — 카드가 본 설비 시나리오(`eq`)가 이 화면의 기준과 다를 때만 그 사실 한 마디.

    예: 「카드는 「셋업 실무 r4」 기준 — 이 화면은 공식 v3」. 같거나 어느 한쪽을 모르면 None.
    """
    if not card or not here or card == here:
        return None
    return f"카드는 「{card}」 기준 — 이 화면은 {here}"
