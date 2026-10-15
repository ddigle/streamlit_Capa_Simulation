# Purpose: 공정 Capa 상세의 표 도구 줄·결합 월 캔버스·범례·근거 패널을 키 붙은 프래그먼트로 그린다.

"""공정 Capa 상세 — 본문 프래그먼트(`process_detail_view`)와 그 둘레.

페이지(`app_pages/process_capa_detail.py`)가 앱 전체 회차에서 공정·축·요약·설비 일정을 모두
정해 `ProcessDetailView` 하나로 넘기면, 여기서는 **지금 보는 달**에 닿는 것만 그린다.

- **표 도구 줄** — 「제품별 소요대수」 펼침(`st.toggle`)과 펼쳤을 때의 「분류」
  (`st.segmented_control`), 그리고 단축 목표 표시(고르는 위젯 없음 — 2026-10-15 사용자 결정
  2). 펼침·분류는 조건 카드가 아니라 본문이다 — 2026-09-29 「상세는 카드」 규칙의 예외다(같은
  날 사용자 결정 4 — 목업 그대로).
- **결합 월 캔버스** — HOME 틀 그대로 라벨 Figure(260px, `staticPlot`) + 월 Figure(달마다
  100px, hover)를 스크롤 상자 하나에 둔다. 월 Figure 의 칸을 누르면 `on_select` 콜백이 세션
  달을 적고 이 프래그먼트만 다시 돈다 — 프래그먼트 안 위젯이라 기본이 이 프래그먼트 회차이고,
  콜백 끝의 `rerun_app_unless_alone` 이 `rerun_fragment_if_alone` 과 같은 판정으로 프래그먼트만
  돌면 안 될 때(끊긴 전체 실행·다른 위젯도 바뀜)만 앱 전체로 올린다. 빈 선택(같은 칸 다시
  누르기·더블클릭)은 보던 달을 둔다. 그림은 세션에 몇 벌 기억한다(`remembered_canvas`, 재공
  현황 꼴) — 새 `st.cache_data` 를 두지 않는다.
- **범례**(HTML 한 줄)·**「더 보기」 토글 둘**(③·④ 30줄 상한)·**설비 일정 없음 카드**(까닭
  + 가용설비 현황 링크).
- **산출 근거 패널** — ① 소요 ② 가용 ③ 판정·원인 ④ 단축 근거(설비 일정 공정·그 달이 충족이
  아닐 때)와 ◀▶ 달 이동, 닫힌 「경로별 인자」(`st.dataframe` 만 — Plotly 를 넣지 않는다).

**이벤트 칸 수는 갈래마다 같다**(AGENTS 「본문 프래그먼트」). 이 프래그먼트가 이벤트 칸에 쓰는
것은 스타일만 든 `st.html` 셋 — 두 컬럼 폭(`split_scroll_columns_style`)·라벨 칸 위 여백·스크롤
상자(`horizontal_scroll_canvas`) — 이고 어느 갈래(펼침·분류·설비 일정 유무·고른 달)에서도 셋
그대로다. 범례·근거 카드의 서식은 그 표시 HTML 과 한 `st.html` 에 실어 본문 칸으로 보낸다.
토스트·팝업은 없다.

**프래그먼트 회차는 직전 앱 전체 회차의 인자를 쓴다** — 오늘·판정 기준·설비 일정·표시명이
그렇다. 공정·조회기간·제품 거르기(조건 카드)는 앱 전체 회차다.

정리 줄(알림·「이 공정 단축 일정 CSV」·필요단축일정 탭 링크)과 KPI 넷은 달에 닿지 않아
프래그먼트 밖에서 페이지가 그린다 — 그 그리기 함수도 여기 있다.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from functools import partial
from typing import Final, NamedTuple

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.plotly_layout import hover_chart_config, static_chart_config
from capa_simulation.components.process_capa_canvas import (
    DynamicCanvasInput,
    ProcessCapaCanvas,
    build_process_capa_canvas,
    canvas_point,
)
from capa_simulation.components.required_shortening_panel import SHORTENING_PROCESS_KEY
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.shortening_timeline import month_day
from capa_simulation.components.status_metric import (
    MetricTone,
    metric_row,
    render_status_metric,
)
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import theme, tokens
from capa_simulation.navigation import EQUIPMENT_SHORTENING_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.process_detail_state import (
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    PROCESS_DETAIL_EXPAND_KEY,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_SPLIT_KEY,
    PROCESS_DETAIL_VIEW_FRAGMENT_KEY,
)
from capa_simulation.services.display_order import PreparedDisplayOrder
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import (
    CAUSE_AVAILABILITY_MISMATCH,
    DEFAULT_PRODUCT_SPLIT,
    LENT_COLUMN,
    MISMATCH_COLUMN,
    PRODUCT_DEMAND_SPLITS,
    ROUTE_COLUMNS,
    ProcessCapaKpis,
    ProcessMonthTrace,
)
from capa_simulation.services.process_equipment_timeline import (
    ROW_SHORTENED,
    ROW_VIRTUAL,
    DynamicReadiness,
    production_position,
)
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    STATUS_EXPIRED,
    STATUS_MET,
    STATUS_NEW_LIMIT,
    MonthlyTarget,
    TargetLevel,
)
from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    CAUSE_OWNED_SHORT,
    CAUSE_RENTAL,
    OWNED_COLUMN,
    STATUS_COLUMN,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import ScenarioCacheKey
from capa_simulation.services.threshold_label import threshold_percent_label
from capa_simulation.services.wd_window import wd_window
from capa_simulation.sidebar_status import remembered_expander, rerun_app_unless_alone

MONTH: Final = "생산계획년월"

# ------------------------------------------------------------------ 위젯·칸 키
# ③·④ 의 30줄 상한(`ROW_LIMIT`)을 넘긴 줄을 모두 그리는 토글. 그림 캐시 키에 든다.
SHOW_ALL_UNITS_KEY: Final = "process_detail_show_all_units"
SHOW_ALL_ARROWS_KEY: Final = "process_detail_show_all_arrows"
# 근거 패널의 ◀▶ 달 이동.
PREVIOUS_MONTH_KEY: Final = "process_detail_previous_month"
NEXT_MONTH_KEY: Final = "process_detail_next_month"
# 닫힌 「경로별 인자」 상자(편 상태를 기억한다).
ROUTE_FACTORS_EXPANDER_KEY: Final = "process_detail_route_factors"
# 정리 줄의 CSV·탭 링크 단추.
UNITS_CSV_KEY: Final = "process_detail_units_csv"
SHORTENING_TAB_LINK_KEY: Final = "process_detail_open_shortening_tab"
# 라벨 칸·월 칸·스크롤 상자 컨테이너 key — CSS 가 이 이름으로 폭과 여백을 못박는다.
LABEL_CANVAS_KEY: Final = "process_detail_label_canvas"
MONTH_REGION_KEY: Final = "process_detail_month_region"
SCROLL_KEY: Final = "process_detail_canvas"
SCROLLBAR_KEY: Final = "process_detail_scrollbar"
LABEL_CHART_KEY: Final = "process_detail_summary_labels"
EVIDENCE_PANEL_KEY: Final = "process_detail_evidence"
DYNAMIC_ABSENT_KEY: Final = "process_detail_dynamic_absent"
KPI_ROW_KEY: Final = "process_detail_kpis"

# KPI 줄의 값 글자 크기(rem). 다른 화면의 큰 숫자보다 한 단계 작다 — 값에 글이 섞인다.
KPI_VALUE_FONT_REM: Final = 1.55
# 부족 원인 KPI 의 짧은 이름과 그 풍선.
SCHEDULE_CAUSE: Final = "일정"
CAUSE_SHORT_NAMES: Final[Mapping[str, str]] = {
    CAUSE_OWNED_SHORT: "보유",
    CAUSE_RENTAL: "대여",
    CAUSE_AVAILABILITY_MISMATCH: "불일치",
    SCHEDULE_CAUSE: "일정",
}
CAUSE_HELP: Final = (
    "달 수입니다. 보유 = 보유로도 부족(총보유 ÷ 소요도 확보기준 미달 — 단축으로 못 메우는 투자 "
    "검토), 대여 = 대여 영향(총보유로는 확보, 대여를 빼면 미달), 불일치 = 가용 불일치(가용대수가 "
    "보유 − 대여와 다름), 일정 = 설비 일정 기준 가용이 단축 목표 미달(참고 — 단축 대상)."
)
# 직전에 만든 캔버스 몇 벌(세션 칸). 칸을 오가며 누를 때 같은 달 그림을 다시 만들지 않는다.
CANVAS_MEMO_KEY: Final = "process_detail_canvas_memo"
CANVAS_MEMO_LIMIT: Final = 6
# 그림 모양이 바뀌면 올린다 — 같은 조건의 옛 그림이 세션에 남아 있어도 다시 만든다.
CANVAS_SCHEMA_VERSION: Final = 1

# 가용설비 현황(설비 일정 원천·필요단축일정 탭이 사는 화면).
AVAILABLE_EQUIPMENT_PAGE: Final = "app_pages/available_equipment_status.py"
# 표 도구 줄에 적는 단축 목표의 출처.
TARGET_SOURCE_TEXT: Final = "HOME Preference 확보기준(월별)"

_MINUS: Final = "−"
_EMPTY: Final = "—"
_STATUS_NAMES: Final[Mapping[str, str]] = {"secure": "확보", "warning": "경고", "shortage": "부족"}
_SHORT_STATUSES: Final = frozenset({"warning", "shortage"})


# ================================================================== 넘겨받는 묶음


@dataclass(frozen=True, eq=False)
class DynamicView:
    """설비 일정(②~④)이 설 때 패널·KPI 가 함께 읽는 것. 캔버스 재료는 `canvas` 다."""

    canvas: DynamicCanvasInput
    units: pd.DataFrame
    """`plan.at(목표).units` 를 이 공정으로 거른 것(단축·추가N)."""

    memo_key: tuple[object, ...]
    """그림 캐시 키에 넣는 설비 일정 입력 — 계획 키(오늘·목표 포함)와 설비 일정 키, 일정 미정 글."""


@dataclass(frozen=True, eq=False)
class ProcessDetailView:
    """프래그먼트 인자 — 앱 전체 회차가 정한 공정·축·요약·설비 일정.

    표들은 키 전용 캐시 래퍼(`get_process_product_demand`·`get_process_month_trace`)에 `_` 인자로만
    넘긴다. 키는 `scenario_key`(시나리오 내용·기간)·`display_order_key` 다.
    """

    process: str
    process_label: str
    months: tuple[int, ...]
    summary: pd.DataFrame
    thresholds: SecurementThresholds
    scenario_key: ScenarioCacheKey
    display_order_key: str
    scenario_tables: Mapping[str, pd.DataFrame]
    reference_tables: Mapping[str, pd.DataFrame]
    display_order: PreparedDisplayOrder | None
    products: tuple[str, ...] = ()
    """조건 카드의 제품 거르기(펼친 행에만 걸린다). 비면 거르지 않는다."""

    splits: tuple[str, ...] = tuple(PRODUCT_DEMAND_SPLITS)
    """「분류」 선택지. 공정 안에서 늘 한 값인 분류(소요기준)는 페이지가 뺀다."""

    home_rates: Mapping[int, float | None] | None = None
    dynamic: DynamicView | None = None
    readiness: DynamicReadiness | None = None
    """설비 일정 판정. None 이면 설비 DB 를 읽지 못한 것이다(`dynamic_error`)."""

    dynamic_error: str = ""
    initial_month: int | None = None
    """화면을 연 회차의 달 — 스크롤 시작 위치(처음 한 번만 걸린다)."""


# ================================================================== 프래그먼트


@st.fragment(key=PROCESS_DETAIL_VIEW_FRAGMENT_KEY)
def render_process_detail_view(view: ProcessDetailView) -> None:
    """표 도구 줄 → 결합 캔버스 → 범례·더 보기 → (설비 일정 없음 카드) → 산출 근거 패널."""
    month = viewed_month(view.months)
    expanded, split = _render_tool_row(view)
    product_demand = (
        simulation_cache.get_process_product_demand(
            view.scenario_key,
            view.display_order_key,
            view.process,
            split,
            view.months,
            _scenario_tables=view.scenario_tables,
            _reference_tables=view.reference_tables,
            _display_order=view.display_order,
            products=view.products,
        )
        if expanded
        else None
    )
    show_all_units = bool(st.session_state.get(SHOW_ALL_UNITS_KEY, False))
    show_all_arrows = bool(st.session_state.get(SHOW_ALL_ARROWS_KEY, False))
    canvas = remembered_canvas(
        view,
        month=month,
        expanded=expanded,
        split=split,
        product_demand=product_demand,
        show_all_units=show_all_units,
        show_all_arrows=show_all_arrows,
    )
    _render_canvas(view, canvas)
    _render_more_toggles(canvas, show_all_units=show_all_units, show_all_arrows=show_all_arrows)
    st.html(
        canvas_legend_html(view.dynamic.canvas if view.dynamic is not None else None, view.months)
    )
    if view.dynamic is None:
        _render_dynamic_absent(view)
    _render_evidence_panel(view, month)


def viewed_month(months: Sequence[int]) -> int:
    """지금 보는 달 — 세션 달이 축 안이면 그 달, 아니면 첫 달(그 값을 세션에 적는다)."""
    saved = st.session_state.get(PROCESS_DETAIL_MONTH_KEY)
    if isinstance(saved, int) and saved in months:
        return saved
    st.session_state[PROCESS_DETAIL_MONTH_KEY] = int(months[0])
    return int(months[0])


def _render_tool_row(view: ProcessDetailView) -> tuple[bool, str]:
    """「제품별 소요대수」 펼침 · 「분류」(펼쳤을 때) · 단축 목표 표시."""
    options = list(view.splits) or [DEFAULT_PRODUCT_SPLIT]
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        expanded = st.toggle(
            "제품별 소요대수",
            key=PROCESS_DETAIL_EXPAND_KEY,
            persist_state="session",
            help=(
                "켜면 소요대수 아래에 분류별 행이 펼쳐집니다. 사이드바 제품 거르기는 이 행에만 "
                "걸립니다."
            ),
        )
        split = DEFAULT_PRODUCT_SPLIT
        if expanded:
            # 선택지에 없는 값(공정이 바뀌어 빠진 「소요기준」 등)은 지우지 않고 기본값을 적는다.
            if st.session_state.get(PROCESS_DETAIL_SPLIT_KEY) not in options:
                st.session_state[PROCESS_DETAIL_SPLIT_KEY] = (
                    DEFAULT_PRODUCT_SPLIT if DEFAULT_PRODUCT_SPLIT in options else options[0]
                )
            st.caption("분류", width="content")
            chosen = st.segmented_control(
                "분류",
                options,
                key=PROCESS_DETAIL_SPLIT_KEY,
                persist_state="session",
                label_visibility="collapsed",
            )
            split = str(chosen) if chosen in options else options[0]
        if view.dynamic is not None:
            st.caption(
                f"단축 목표 = {target_text(view.dynamic.canvas.target, view.months)}",
                width="content",
            )
    return bool(expanded), split


def target_text(target: TargetLevel, months: Sequence[int]) -> str:
    """단축 목표 표기 — 「HOME Preference 확보기준(월별)」, 달마다 같으면 그 값(소수 그대로)도."""
    values = {_target_for(target, month) for month in months}
    if len(values) == 1:
        value = next(iter(values))
        return f"{TARGET_SOURCE_TEXT} {threshold_percent_label(value)} ({value:g})"
    return f"{TARGET_SOURCE_TEXT} — 달마다 다름"


def _target_for(target: TargetLevel, month: int) -> float:
    return target.for_month(month) if isinstance(target, MonthlyTarget) else float(target)


# ================================================================== 캔버스


def canvas_memo_key(
    view: ProcessDetailView,
    *,
    month: int,
    expanded: bool,
    split: str,
    show_all_units: bool,
    show_all_arrows: bool,
) -> tuple[object, ...]:
    """그림을 바꾸는 조건 전부. 지금 보는 달·오늘(설비 일정 키 안)·목표가 그림에 구워지므로 든다."""
    home = tuple(sorted(view.home_rates.items())) if view.home_rates is not None else None
    return (
        CANVAS_SCHEMA_VERSION,
        theme.current_mode(),
        view.scenario_key,
        view.display_order_key,
        view.months,
        view.process,
        view.process_label,
        view.thresholds.digest,
        bool(expanded),
        split if expanded else "",
        view.products if expanded else (),
        int(month),
        home,
        view.dynamic.memo_key if view.dynamic is not None else None,
        bool(show_all_units),
        bool(show_all_arrows),
    )


def remembered_canvas(
    view: ProcessDetailView,
    *,
    month: int,
    expanded: bool,
    split: str,
    product_demand: pd.DataFrame | None,
    show_all_units: bool,
    show_all_arrows: bool,
) -> ProcessCapaCanvas:
    """결합 캔버스를 세션에 몇 벌 기억한다(`CANVAS_MEMO_LIMIT`). 꺼낸 그림은 고치지 않는다.

    키(`canvas_memo_key`)는 그림을 바꾸는 조건 전부다 — 테마·시나리오 키·표시순서
    지문·축·공정·표시명· 판정 기준 지문·펼침/분류/거르기·지금 보는 달·HOME 표시 확보율·설비 일정
    키(오늘·목표·네 표 지문)· 더 보기 둘·그림 모양 버전. 만들다 실패하면 기억하지 않는다.
    """
    key = canvas_memo_key(
        view,
        month=month,
        expanded=expanded,
        split=split,
        show_all_units=show_all_units,
        show_all_arrows=show_all_arrows,
    )
    memo = st.session_state.get(CANVAS_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], ProcessCapaCanvas]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key and isinstance(stored, ProcessCapaCanvas):
            return stored
    dynamic = (
        replace(
            view.dynamic.canvas,
            show_all_units=show_all_units,
            show_all_arrows=show_all_arrows,
        )
        if view.dynamic is not None
        else None
    )
    canvas = build_process_capa_canvas(
        process_label=view.process_label,
        months=view.months,
        summary=view.summary,
        thresholds=view.thresholds,
        selected_month=month,
        product_demand=product_demand,
        home_rates=view.home_rates,
        dynamic=dynamic,
    )
    entries = [entry for entry in entries if entry[0] != key][-(CANVAS_MEMO_LIMIT - 1) :]
    st.session_state[CANVAS_MEMO_KEY] = [*entries, (key, canvas)]
    return canvas


def pick_canvas_month(months: Sequence[int]) -> None:
    """월 그림의 칸 선택 콜백 — 누른 칸의 달을 세션에 적는다. 이 프래그먼트 회차로 다시 그린다.

    빈 선택(같은 칸을 다시 누르거나 더블클릭)과 축 밖의 점은 무시한다 — 보던 달 그대로다. ③·④ 줄을
    눌러도 그 열의 달이다(표적 막대가 그 줄까지 덮는다).
    """
    point = canvas_point(st.session_state.get(PROCESS_DETAIL_CANVAS_CHART_KEY))
    if point is not None and point[0] in set(int(month) for month in months):
        st.session_state[PROCESS_DETAIL_MONTH_KEY] = int(point[0])
    rerun_app_unless_alone(PROCESS_DETAIL_CANVAS_CHART_KEY)


def _render_canvas(view: ProcessDetailView, canvas: ProcessCapaCanvas) -> None:
    """HOME 틀 — 라벨 칸 260px(px 로 못박음) + 월 칸(스크롤 상자 하나, 위에 가로 스크롤바)."""
    count = len(view.months)
    visible = min(max(count, 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)
    st.html(
        split_scroll_columns_style(
            label_key=LABEL_CANVAS_KEY,
            month_key=MONTH_REGION_KEY,
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
        )
    )
    label_column, month_column = st.columns(
        [DASHBOARD_LABEL_COLUMN_WIDTH_PX, visible * tokens.MONTH_COLUMN_WIDTH_PX], gap=None
    )
    with label_column:
        with st.container(key=LABEL_CANVAS_KEY, gap=None):
            st.plotly_chart(
                canvas.labels,
                width="stretch",
                key=LABEL_CHART_KEY,
                config=static_chart_config(),
            )
    with month_column:
        # 라벨 칸은 월 칸 위에 얹힌 스크롤바 높이만큼 내려야 행이 맞는다(HOME 과 같은 값).
        st.html(
            f"<style>.st-key-{LABEL_CANVAS_KEY} {{ padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px; }}"
            "</style>"
        )
        with st.container(key=MONTH_REGION_KEY, gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{SCROLL_KEY}_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key=SCROLLBAR_KEY,
                initial_offset_px=initial_scroll_px(view.months, view.initial_month),
            )
            with horizontal_scroll_canvas(
                key=SCROLL_KEY,
                content_width_px=count * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=None,
            ):
                # hover 로 칸 풍선을 읽고, 칸을 누르면 그 달이 아래 근거 패널의 달이 된다 — 선택은
                # 점 하나(`points`)다. 선택을 켜면 그림 위 터치 스크롤이 막히므로 이 key 는 `app.py`
                # 의 터치 스크롤 막이 묶음에 들어 있다.
                st.plotly_chart(
                    canvas.months,
                    width="stretch",
                    key=PROCESS_DETAIL_CANVAS_CHART_KEY,
                    config=hover_chart_config(),
                    on_select=partial(pick_canvas_month, view.months),
                    selection_mode="points",
                )


def initial_scroll_px(months: Sequence[int], month: int | None) -> float:
    """화면을 연 달이 왼쪽에서 둘째 칸쯤 서게 하는 시작 위치(px). 첫 두 달이면 0."""
    if month is None or month not in months:
        return 0.0
    return float(max(0, list(months).index(month) - 1) * tokens.MONTH_COLUMN_WIDTH_PX)


def _render_more_toggles(
    canvas: ProcessCapaCanvas, *, show_all_units: bool, show_all_arrows: bool
) -> None:
    """30줄 상한을 넘긴 ③·④ 를 모두 그리는 토글. 넘긴 줄이 있거나 켜 둔 동안만 선다."""
    wanted = [
        (canvas.hidden_units > 0 or show_all_units, "더 보기 — 신규 설비 모두", SHOW_ALL_UNITS_KEY),
        (
            canvas.hidden_arrow_units > 0 or show_all_arrows,
            "더 보기 — 비가동 호기 모두",
            SHOW_ALL_ARROWS_KEY,
        ),
    ]
    shown = [(label, key) for wanted_here, label, key in wanted if wanted_here]
    if not shown:
        return
    with st.container(horizontal=True, gap="medium"):
        for label, key in shown:
            st.toggle(label, key=key, persist_state="session")


# ================================================================== 범례


def canvas_legend_html(dynamic: DynamicCanvasInput | None, months: Sequence[int]) -> str:
    """캔버스 아래 범례 한 줄(서식 포함). 설비 일정이 서면 ②~④ 표지와 생산월 규칙을 더한다."""
    band = tokens.SHORTAGE_MONTH_BAND
    swatch = "display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px"
    items = [
        f'<span style="{swatch};background:{band};border:1px solid '
        f'{tokens.STATUS_SHORTAGE}"></span>공식 확보기준 미달 달',
        f'<span style="{swatch};border:2px solid {tokens.ACCENT}"></span>지금 보는 달',
        "".join(
            f'<span style="{swatch};background:{color}"></span>'
            for color in (tokens.STATUS_SECURE, tokens.STATUS_WARNING, tokens.STATUS_SHORTAGE)
        )
        + "확보율·과부족 칸 = 판정(확보 · 경고 · 부족)",
        f'<span style="color:{tokens.TEXT_MUTED}">기준 확보율 줄은 참고(달마다 확보기준)</span>',
    ]
    if dynamic is not None:
        qual = tokens.QUAL_CONFIRMATION_COLORS
        dot = (
            "display:inline-block;width:11px;height:11px;border-radius:50%;vertical-align:-2px;"
            f"border:1px solid {tokens.TEXT}"
        )
        items += [
            f'<span style="color:{tokens.TEXT_MUTED};font-size:13px">◆</span>반입',
            "".join(
                f'<span style="{dot};background:{qual[name]}"></span>'
                for name in ("계획", "확정", "완료")
            )
            + "기여 시작(Qual 다음 날) · 계획/확정/완료",
            f'<span style="color:{tokens.TEXT}">◀━</span>단축 목표 기여 시작 · −N일',
            f'<span style="{dot};background:{tokens.STATUS_SHORTAGE};border-style:dotted"></span>'
            "추가N(신규 필요)",
            f'<span style="color:{tokens.EQUIPMENT_STAGE_COLORS["운영 비가동"]};font-weight:700">'
            "━▶</span>가용을 깎은 비가동",
            f'<span style="color:{tokens.TEXT_MUTED}">┄┄</span>영향 없는 비가동(셋업·보관 등)',
            html.escape(production_month_example(dynamic.cutoff_days, months)),
            "Qual·비가동 끝은 다음 날부터, 반출·이설은 당일부터 셉니다 · "
            "비가동유형 「이설」 ≠ 이설일정",
        ]
    spans = "".join(f'<span class="pcd-legend-item">{item}</span>' for item in items)
    return (
        "<style>"
        f".pcd-legend{{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;"
        f"color:{tokens.TEXT_MUTED};font-family:{tokens.FONT_FAMILY};padding:2px 0}}"
        ".pcd-legend-item{display:inline-flex;align-items:center;gap:5px}"
        "</style>"
        f'<div class="pcd-legend">{spans}</div>'
    )


def production_month_example(cutoff_days: int, months: Sequence[int]) -> str:
    """「칸 = 생산월」 예 — 첫 달 25일 Qual 이 어느 달 칸에 서는가(다음 날 + Cut-off)."""
    first = int(months[0])
    qual = date(first // 100, first % 100, 25)
    position = production_position(qual + timedelta(days=1), cutoff_days, months)
    return (
        f"칸 = 생산월 — Cut-off {cutoff_days}일이면 {qual:%m.%d} Qual 은 "
        f"{position.month % 100}월 칸에 섭니다"
    )


def _render_dynamic_absent(view: ProcessDetailView) -> None:
    """설비 일정(②~④) 대신 서는 카드 한 장 — 까닭과 가용설비 현황 링크."""
    with st.container(border=True, key=DYNAMIC_ABSENT_KEY):
        if view.readiness is None:
            st.markdown(":material/event_busy: **설비 일정 없음: 설비 DB 를 읽지 못했습니다**")
            st.caption(view.dynamic_error or "설비 DB 를 열지 못했습니다.")
        else:
            st.markdown(f":material/event_busy: **{view.readiness.badge}**")
            detail = view.dynamic_error or view.readiness.detail
            st.caption(
                f"{detail} 설비 일정 기준 가용·신규 설비·비가동(②~④)은 설비 DB 에 저장본이 "
                "있고 이름이 같으며 Cut-off 가 적힌 공정에만 섭니다. 위 공식 기준 표는 "
                "그대로입니다."
            )
        render_page_link(
            AVAILABLE_EQUIPMENT_PAGE,
            label="가용설비 현황에서 설비·Cut-off 보기",
            icon=":material/precision_manufacturing:",
        )


# ================================================================== 산출 근거 패널


class EvidenceCard(NamedTuple):
    """근거 카드 하나 — 제목, 숫자를 넣은 식(여러 줄), 회색 메모."""

    title: str
    formula: str
    notes: tuple[str, ...] = ()
    reference: bool = False
    """참고(설비 일정 기준) 카드 — 점선 테두리."""


def _render_evidence_panel(view: ProcessDetailView, month: int) -> None:
    months = list(view.months)
    index = months.index(month)
    previous = months[index - 1] if index > 0 else None
    following = months[index + 1] if index + 1 < len(months) else None
    trace: ProcessMonthTrace | None
    try:
        trace = simulation_cache.get_process_month_trace(
            view.scenario_key,
            view.process,
            month,
            _scenario_tables=view.scenario_tables,
            _reference_tables=view.reference_tables,
        )
    except (KeyError, ValueError):
        trace = None
    with st.container(border=True, key=EVIDENCE_PANEL_KEY):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"**산출 근거 · {month_label(month)} · {view.process_label}**")
            st.space("stretch")
            st.button(
                f"◀ {month_label(previous)}" if previous is not None else "◀ 첫 달",
                key=PREVIOUS_MONTH_KEY,
                type="tertiary",
                on_click=step_month,
                args=(view.months, -1, PREVIOUS_MONTH_KEY),
            )
            st.button(
                f"{month_label(following)} ▶" if following is not None else "끝 달 ▶",
                key=NEXT_MONTH_KEY,
                type="tertiary",
                on_click=step_month,
                args=(view.months, 1, NEXT_MONTH_KEY),
            )
        cards = evidence_cards(view, month, trace)
        st.html(evidence_cards_html(cards))
        st.caption(
            "Qual 을 당기면 바뀌는 것은 설비 일정 기준 가용입니다 — 공식 확보율은 Core Data 의 "
            "보유·대여가 갱신될 때 바뀝니다. 왜 이렇게 계산하는지는 Guide 에 있습니다."
            if view.dynamic is not None
            else "왜 이렇게 계산하는지는 Guide 에 있습니다."
        )
        with remembered_expander(
            "경로별 인자 — 반영 UPEH·환산 UPEH·측정률과 공통 인자",
            key=ROUTE_FACTORS_EXPANDER_KEY,
            icon=":material/table_rows:",
        ):
            _render_route_factors(trace)


def step_month(months: Sequence[int], step: int, widget_key: str) -> None:
    """◀▶ 콜백 — 보던 달에서 한 칸 옮긴다. 축 끝이면 그대로다. 이 프래그먼트 회차로 다시 그린다."""
    axis = [int(month) for month in months]
    current = st.session_state.get(PROCESS_DETAIL_MONTH_KEY)
    position = axis.index(current) if current in axis else 0
    target = position + step
    if 0 <= target < len(axis):
        st.session_state[PROCESS_DETAIL_MONTH_KEY] = axis[target]
    rerun_app_unless_alone(widget_key)


def evidence_cards(
    view: ProcessDetailView, month: int, trace: ProcessMonthTrace | None
) -> list[EvidenceCard]:
    """고른 달의 근거 카드 — ① 소요 ② 가용 ③ 판정 (+ ④ 단축 근거)."""
    record = _summary_record(view.summary, month)
    bridge = _month_record(view.dynamic.canvas.bridge, month) if view.dynamic is not None else None
    cards = [
        demand_card(trace, record),
        availability_card(record, bridge),
        judgement_card(record, view.thresholds, month),
    ]
    if view.dynamic is not None:
        card = shortening_card(view.dynamic, month)
        if card is not None:
            cards.append(card)
    return cards


def demand_card(trace: ProcessMonthTrace | None, record: Mapping[str, object]) -> EvidenceCard:
    """① 소요 — Σ 경로 부하량 ÷ 대당 Capa 와 경로 수·제외 경로, 상위 제품."""
    required = _number(record.get("소요대수"))
    if trace is None:
        return EvidenceCard(
            "① 소요",
            f"Σ 경로 부하량 ÷ 대당 Capa\n= {_one(required)} 대",
            ("경로 인자를 읽지 못했습니다 — 산출 결과 화면에서 확인합니다.",),
        )
    evidence = trace.evidence
    head = f"경로 {evidence.route_count} · 제외 {evidence.excluded_route_count}"
    formula = f"Σ 경로 부하량 ÷ 대당 Capa\n= {_one(evidence.required)} 대  ({head})"
    notes: list[str] = []
    if evidence.effective_capacity is not None:
        notes.append(
            f"원수요 부하량 {evidence.unique_demand_load:,.0f} ÷ 실효 대당 Capa "
            f"{evidence.effective_capacity:,.1f}"
        )
    top = evidence.top_products
    if not top.empty:
        parts = [
            f"{name} {value:,.1f}"
            for name, value in zip(top["제품정보"], top["소요대수"], strict=True)
        ]
        rest = evidence.product_count - len(parts)
        notes.append(" · ".join(parts) + (f" · 그 밖 {rest}개" if rest > 0 else ""))
    if evidence.rule_excluded_route_count:
        notes.append(f"규칙상 제외 {evidence.rule_excluded_route_count}경로(PKG 의 Buffer 아닌 행)")
    if evidence.assumed_ratio_routes:
        notes.append(f"측정률 행 없음 → 1.0 가정 {evidence.assumed_ratio_routes}경로")
    if evidence.blank_ratio_routes:
        notes.append(f"측정률 빈칸·0 → 1.0 {evidence.blank_ratio_routes}경로")
    return EvidenceCard("① 소요", formula, tuple(notes))


def availability_card(
    record: Mapping[str, object], bridge: Mapping[str, object] | None
) -> EvidenceCard:
    """② 가용 — 보유 − 대여 = 가용(공식). 설비 일정이 서면 기존보유 + 호기 가용(참고)."""
    owned = _number(record.get(OWNED_COLUMN))
    lent = _number(record.get(LENT_COLUMN))
    available = _number(record.get("가용대수"))
    derived = None if owned is None else owned - (lent or 0.0)
    formula = (
        f"보유 {_one(owned)} − 대여 {_one(lent)} = {_one(derived)}\n"
        f"가용대수 {_one(available)} (공식)"
    )
    notes: list[str] = []
    if bool(record.get(MISMATCH_COLUMN, False)):
        notes.append("⚠ 가용대수가 보유 − 대여와 다릅니다 — 기준정보 표를 따로 고쳤습니다.")
    if bridge is not None:
        baseline = _number(bridge.get("기존보유"))
        units = _number(bridge.get("호기 가용"))
        total = _number(bridge.get("가용대수"))
        notes.append(
            f"설비 일정 기준(참고): 기존보유 {_one(baseline)} + 호기 {_one(units)} = "
            f"{_one(total)} (환산)"
        )
    return EvidenceCard("② 가용", formula, tuple(notes))


def judgement_card(
    record: Mapping[str, object], thresholds: SecurementThresholds, month: int
) -> EvidenceCard:
    """③ 판정 — 확보율 식·과부족 식(그 달 확보기준)과 원인."""
    secure, warning = thresholds.for_month(month)
    available = _number(record.get("가용대수"))
    required = _number(record.get("소요대수"))
    owned = _number(record.get(OWNED_COLUMN))
    lent = _number(record.get(LENT_COLUMN))
    status = record.get(STATUS_COLUMN)
    bases = (
        f"확보기준 {threshold_percent_label(secure)} ({secure:g}) · 경고기준 "
        f"{threshold_percent_label(warning)} ({warning:g})"
    )
    if required is None or required <= 0 or available is None:
        return EvidenceCard("③ 판정", "소요 없음 — 판정하지 않습니다", (bases,))
    rate = available / required
    name = _STATUS_NAMES.get(str(status), _EMPTY)
    balance = _whole(record.get(BALANCE_COLUMN))
    raw = available - required * secure
    formula = (
        f"확보율 = {_one(available)} ÷ {_one(required)} = {rate:.1%} → {name}\n"
        f"과부족 = {_one(available)} − {_one(required)}×{secure:g} = {_signed_two(raw)}"
        f" → {_signed_int(balance) if balance is not None else _EMPTY}"
    )
    notes = [bases]
    cause = "" if record.get(CAUSE_COLUMN) is None else str(record.get(CAUSE_COLUMN))
    if cause == CAUSE_OWNED_SHORT and owned is not None:
        notes.append(
            f"원인: {cause} — 총보유 {_one(owned)} ÷ 소요 {_one(required)} = "
            f"{owned / required:.1%} 도 확보기준 미달(투자 검토)"
        )
    elif cause == CAUSE_RENTAL:
        notes.append(f"원인: {cause} — 총보유로는 확보, 대여 {_one(lent)} 대를 빼면 미달")
    elif cause == CAUSE_AVAILABILITY_MISMATCH:
        notes.append(f"원인: {cause} — 보유 − 대여로는 확보인데 가용대수가 따로 낮습니다")
    elif cause:
        notes.append(f"원인: {cause}")
    if str(status) in _SHORT_STATUSES and balance == 0:
        notes.append("잡음 경계 — 확보율이 기준에 아주 조금 못 미쳐 칠했지만 과부족은 0 입니다")
    return EvidenceCard("③ 판정", formula, tuple(notes))


def shortening_card(dynamic: DynamicView, month: int) -> EvidenceCard | None:
    """④ 단축 근거 — 그 달 설비 일정 상태가 충족이 아닐 때만. 목표·구간·바닥·당긴 호기·단축 후."""
    record = _month_record(dynamic.canvas.process_months, month)
    if record is None:
        return None
    state = "" if record.get("상태") is None else str(record.get("상태"))
    if not state or state == STATUS_MET:
        return None
    canvas = dynamic.canvas
    target = _target_for(canvas.target, month)
    required = _number(record.get("소요대수"))
    target_units = _number(record.get("목표대수"))
    before = _number(record.get("가용대수"))
    after = _number(record.get("단축후가용대수"))
    gap = _number(record.get("과부족"))
    gap_after = _number(record.get("단축후과부족"))
    window = wd_window(month, canvas.cutoff_days)
    floor = max(window.first_day, canvas.today)
    lines = [
        f"목표 {_two(target_units)} = 소요 {_one(required)} × {target:g}",
        f"가용 {_two(before)} − 목표 {_two(target_units)} = {_signed_two(gap)}",
        f"구간 {_day(window.first_day, canvas.today)}~{_day(window.boundary_end, canvas.today)}"
        f" · 바닥 {_day(floor, canvas.today)}(구간 시작·오늘 중 늦은 날)",
    ]
    for unit in contributing_units(dynamic.canvas.unit_events, month, today=canvas.today):
        lines.append(unit)
    lines.append(f"→ 단축 후 {_two(after)} ({_signed_two(gap_after)})")
    notes = [f"상태: {state}"]
    today_month = production_position(canvas.today, canvas.cutoff_days, [month]).month
    if month < today_month:
        notes.append("기한 지남 — 지난 달은 단축으로 바꿀 수 없습니다")
    elif month == today_month:
        notes.append("오늘이 든 달 — 남은 날만 셉니다(추가N 이 크게 나올 수 있음)")
    if state in (STATUS_EXPIRED, STATUS_NEW_LIMIT):
        notes.append("단축·신규로도 이 달을 다 채우지 못했습니다")
    return EvidenceCard(
        f"④ 단축 근거 (설비 일정 · 목표 {threshold_percent_label(target)})",
        "\n".join(lines),
        tuple(notes),
        reference=True,
    )


def contributing_units(unit_events: pd.DataFrame, month: int, *, today: date) -> list[str]:
    """그 달을 메운 호기 줄 — 대상 월이 그 달이거나 해소 기여 월에 그 달이 든 단축·추가N."""
    if unit_events.empty:
        return []
    lines: list[str] = []
    for record in unit_events.to_dict("records"):
        kind = str(record.get("줄"))
        if kind not in (ROW_SHORTENED, ROW_VIRTUAL):
            continue
        target_month = _whole(record.get("대상 월"))
        resolved = _month_tuple(record.get("해소 기여 월"))
        if target_month != month and month not in resolved:
            continue
        unit = str(record.get("호기"))
        gain = _number(record.get("늘어난 환산대수"))
        gain_text = f"+{gain:,.2f}" if gain is not None else _EMPTY
        target = _as_date(record.get("목표 Qual"))
        if kind == ROW_VIRTUAL:
            lines.append(f"→ {unit} 신규 필요 Qual {_day(target, today)} ({gain_text})")
            continue
        original = _as_date(record.get("Qual일정"))
        days = _whole(record.get("단축일수")) or 0
        lines.append(
            f"→ {unit} {_day(original, today)}→{_day(target, today)} "
            f"({_MINUS}{days}일, {gain_text})"
            + (" · 반입 전" if bool(record.get("반입 전")) else "")
        )
    return lines


def evidence_cards_html(cards: Sequence[EvidenceCard]) -> str:
    """근거 카드 묶음(서식 포함) — 넓으면 한 줄에 넷, 좁으면 접힌다."""
    body = "".join(
        f'<div class="pcd-card{" ref" if card.reference else ""}">'
        f"<h5>{html.escape(card.title)}</h5>"
        f'<div class="pcd-f">{html.escape(card.formula)}</div>'
        + "".join(f'<div class="pcd-m">{html.escape(note)}</div>' for note in card.notes)
        + "</div>"
        for card in cards
    )
    return (
        "<style>"
        ".pcd-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}"
        f".pcd-card{{border:1px solid {tokens.BORDER};border-radius:8px;padding:8px 10px;"
        f"background:{tokens.SURFACE};display:grid;gap:4px;align-content:start;min-width:0}}"
        ".pcd-card.ref{border-style:dashed}"
        f".pcd-card h5{{margin:0;padding:0;font-size:13px;font-weight:700;color:{tokens.TEXT};"
        f"font-family:{tokens.FONT_FAMILY}}}"
        f".pcd-f{{font-family:{tokens.FONT_FAMILY_NUMERIC};font-size:12.5px;line-height:1.6;"
        f"white-space:pre-wrap;color:{tokens.TEXT};font-variant-numeric:tabular-nums}}"
        f".pcd-m{{font-size:12px;color:{tokens.TEXT_MUTED};font-family:{tokens.FONT_FAMILY}}}"
        "</style>"
        f'<div class="pcd-cards">{body}</div>'
    )


def _render_route_factors(trace: ProcessMonthTrace | None) -> None:
    """경로마다 인자·근거 칸, 공통 인자(양산구분별 효율·여유율, 일수·모듈수), 제외 경로."""
    if trace is None:
        st.caption("경로 인자를 읽지 못했습니다.")
        return
    routes = trace.routes.reindex(columns=ROUTE_COLUMNS)
    if routes.empty:
        st.caption("이 달 이 공정의 경로가 없습니다.")
    else:
        st.dataframe(routes, hide_index=True, width="stretch", key="process_detail_routes")
    common = trace.common_factors
    parts = []
    if common.run_day is not None:
        parts.append(f"RUN_DAY {common.run_day:g}")
    if common.module_count is not None:
        parts.append(f"모듈수 {common.module_count:g}")
    for row in common.by_class.to_dict("records"):
        run_rate = _number(row.get("CAPA_RUN_RATE"))
        vital = _number(row.get("편중률"))
        parts.append(
            f"{row.get('양산구분')} 효율 {_ratio_text(run_rate)} · "
            f"여유율(편중률) {_ratio_text(vital)}"
        )
    if parts:
        st.caption("공통 인자 — " + " · ".join(parts))
    if not trace.excluded.empty:
        st.caption(f"제외 경로 {len(trace.excluded)}행(규칙상 제외 포함)")
        st.dataframe(
            trace.excluded, hide_index=True, width="stretch", key="process_detail_excluded"
        )


# ================================================================== KPI · 정리 줄


class Prescription(NamedTuple):
    """처방 — 이 공정의 단축 호기 수·추가N 수와 설비 일정 기준으로 남은 미달 달 수."""

    shortened: int
    new: int
    unresolved_months: int
    dynamic_short_months: int


def prescription(dynamic: DynamicView) -> Prescription:
    """설비 일정 계획을 이 공정으로 센다 — 단축(구분 「단축」)·신규(「신규」 = 추가N)·못 채운 달."""
    units = dynamic.units
    kinds = units["구분"].astype("string") if "구분" in units.columns else pd.Series(dtype="string")
    months = dynamic.canvas.process_months
    gaps = (
        pd.to_numeric(months["과부족"], errors="coerce").round(9)
        if "과부족" in months.columns
        else pd.Series(dtype="float64")
    )
    states = (
        months["상태"].astype("string") if "상태" in months.columns else pd.Series(dtype="string")
    )
    return Prescription(
        shortened=int(kinds.eq(KIND_SHORTENED).sum()),
        new=int(kinds.eq(KIND_NEW).sum()),
        unresolved_months=int(states.isin([STATUS_EXPIRED, STATUS_NEW_LIMIT]).sum()),
        dynamic_short_months=int(gaps.lt(0).sum()),
    )


def render_process_kpis(
    kpis: ProcessCapaKpis,
    *,
    thresholds: SecurementThresholds,
    dynamic: DynamicView | None,
    absent_reason: str,
) -> None:
    """KPI 넷 — 최저 확보율, 확보기준 미달 달·월 최대 부족, 부족 원인, 처방(설비 일정 기준).

    값 글자를 짧게 둔다(카드 폭에 한 줄). 뜻풀이는 값 아래 회색 한 줄과 `?` 풍선이다.
    """
    lowest_tone: MetricTone = "neutral"
    if kpis.lowest_rate is not None and kpis.lowest_rate_month is not None:
        status = thresholds.status(kpis.lowest_rate, kpis.lowest_rate_month)
        if status == "shortage":
            lowest_tone = "critical"
        elif status == "warning":
            lowest_tone = "attention"
    plan = prescription(dynamic) if dynamic is not None else None
    # 이 줄의 값은 글이 섞여 다른 화면의 큰 숫자보다 길다 — 한 단계 작게 둔다.
    st.html(
        f'<style>.st-key-{KPI_ROW_KEY} [data-testid="stMetricValue"] '
        f"{{font-size:{KPI_VALUE_FONT_REM}rem}}</style>"
    )
    with metric_row(key=KPI_ROW_KEY):
        render_status_metric(
            "최저 확보율",
            f"{kpis.lowest_rate:.1%}" if kpis.lowest_rate is not None else _EMPTY,
            key="process_detail_kpi_lowest",
            tone=lowest_tone,
            caption=(
                month_label(kpis.lowest_rate_month) if kpis.lowest_rate_month is not None else None
            ),
        )
        render_status_metric(
            "확보기준 미달",
            f"{kpis.shortage_months}개월" if kpis.shortage_months else "없음",
            key="process_detail_kpi_shortage",
            tone="attention" if kpis.shortage_months else "neutral",
            caption=(
                f"월 최대 {_MINUS}{kpis.max_shortage}대 · 기간 합 아님"
                if kpis.shortage_months
                else "월별 확보기준"
            ),
            help=(
                "판정이 확보가 아닌 달 수와, 그 달들 가운데 확보기준까지 모자란 대수의 "
                "최댓값입니다."
            ),
        )
        render_status_metric(
            "부족 원인",
            cause_summary(kpis, plan),
            key="process_detail_kpi_cause",
            caption="달 수 · 공식 기준" + (" · 일정은 설비 일정" if plan is not None else ""),
            help=CAUSE_HELP,
        )
        render_status_metric(
            "처방",
            prescription_text(plan),
            key="process_detail_kpi_prescription",
            caption=(
                "설비 일정 기준 · 목표 "
                + short_target_text(dynamic.canvas.target, _plan_months(dynamic))
                if dynamic is not None
                else absent_reason
            ),
            help=(
                "필요단축일정과 같은 계산을 이 공정 하나로 본 것입니다 — 단축은 Qual 을 당길 호기, "
                "신규는 당겨도 모자라 더 들여야 하는 추가N 입니다."
            ),
        )


def _plan_months(dynamic: DynamicView) -> list[int]:
    frame = dynamic.canvas.process_months
    if frame.empty or MONTH not in frame.columns:
        return [0]
    return [int(month) for month in frame[MONTH]]


def cause_summary(kpis: ProcessCapaKpis, plan: Prescription | None) -> str:
    """「보유 a · 대여 b · 불일치 m · 일정 c」(달 수) — 0 인 갈래는 뺀다. 모두 0 이면 「없음」."""
    parts = [
        (CAUSE_SHORT_NAMES[CAUSE_OWNED_SHORT], kpis.owned_short_months),
        (CAUSE_SHORT_NAMES[CAUSE_RENTAL], kpis.rental_months),
        (CAUSE_SHORT_NAMES[CAUSE_AVAILABILITY_MISMATCH], kpis.mismatch_months),
        (CAUSE_SHORT_NAMES[SCHEDULE_CAUSE], plan.dynamic_short_months if plan is not None else 0),
    ]
    shown = [f"{name} {count}" for name, count in parts if count]
    return " · ".join(shown) if shown else "없음"


def short_target_text(target: TargetLevel, months: Sequence[int]) -> str:
    """처방 카드의 목표 — 달마다 같으면 「110%」, 다르면 「달마다 확보기준」."""
    values = {_target_for(target, month) for month in months}
    if len(values) == 1:
        return threshold_percent_label(next(iter(values)))
    return "달마다 확보기준"


def prescription_text(plan: Prescription | None) -> str:
    """처방 글 — 「단축 n대 · 신규 m대」, 할 것이 없으면 「목표 충족」, 설비 일정이 없으면
    「일정 없음」(까닭은 회색 줄)."""
    if plan is None:
        return "일정 없음"
    if plan.shortened == 0 and plan.new == 0:
        return "목표 충족" if plan.unresolved_months == 0 else "기한 지남"
    return f"단축 {plan.shortened}대 · 신규 {plan.new}대"


def render_closing_row(
    *,
    process: str,
    notices: Sequence[str],
    csv_bytes: bytes | None,
    csv_file_name: str,
) -> None:
    """정리 줄 — 알림(0 이면 생략), 「이 공정 단축 일정 CSV」, 필요단축일정 탭 링크."""
    for notice in notices:
        st.caption(notice)
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        if csv_bytes is not None:
            render_csv_download(
                data=csv_bytes,
                file_name=csv_file_name,
                key=UNITS_CSV_KEY,
                label="이 공정 단축 일정 CSV",
            )
        st.button(
            "필요단축일정에서 전체 공정·진척 비교 보기",
            key=SHORTENING_TAB_LINK_KEY,
            icon=":material/arrow_forward:",
            type="tertiary",
            on_click=open_shortening_tab,
            args=(process,),
        )


def open_shortening_tab(process: str) -> None:
    """필요단축일정 탭을 이 공정으로 연다 — **세션 키만 심는다**(콜백).

    탭(`EQUIPMENT_TAB_KEY` 와 그 기억 칸)과 공정 상자(`SHORTENING_PROCESS_KEY=[공정]`)만 적는다. 그
    탭의 공용 조회 조건(설비 DB `0019`)·기준선(`0021`)은 읽지도 쓰지도 않는다 — 공용 쓰기는 그 탭
    위젯의 `on_change` 에서만 일어나므로 세션 값을 심는 것만으로는 쓰이지 않는다. 갈 곳이
    없으면(내비게이션이 없는 단독 실행) 옮기지 않는다.
    """
    st.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SHORTENING_TAB
    st.session_state[remembered_tab_key(EQUIPMENT_TAB_KEY)] = EQUIPMENT_SHORTENING_TAB
    st.session_state[SHORTENING_PROCESS_KEY] = [str(process)]
    try:
        st.switch_page(AVAILABLE_EQUIPMENT_PAGE)
    except StreamlitPageNotFoundError:
        return


# ================================================================== 값 다루기


def _summary_record(summary: pd.DataFrame, month: int) -> dict[str, object]:
    record = _month_record(summary, month)
    return record if record is not None else {}


def _month_record(frame: pd.DataFrame, month: int) -> dict[str, object] | None:
    if frame.empty or MONTH not in frame.columns:
        return None
    rows = frame.loc[pd.to_numeric(frame[MONTH], errors="coerce").eq(int(month))]
    if rows.empty:
        return None
    return {str(key): value for key, value in rows.iloc[0].items()}


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _whole(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    return None


def _month_tuple(value: object) -> tuple[int, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(int(item) for item in value if _whole(item) is not None)
    if isinstance(value, str):
        return tuple(int(part) for part in value.replace(" ", "").split(",") if part.isdigit())
    return ()


def _day(day: date | None, today: date) -> str:
    """호기 줄과 같은 날짜 글 — 올해면 `MM.DD`, 해가 다르면 `YY.MM.DD`."""
    return "미정" if day is None else month_day(day, today=today)


def _one(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:,.1f}"


def _two(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:,.2f}"


def _signed_two(value: float | None) -> str:
    if value is None:
        return _EMPTY
    rounded = round(value, 2) + 0.0
    if rounded > 0:
        return f"+{rounded:,.2f}"
    if rounded < 0:
        return f"{_MINUS}{abs(rounded):,.2f}"
    return "0.00"


def _signed_int(value: int) -> str:
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{_MINUS}{abs(value):,}"
    return "0"


def _ratio_text(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:g}"
