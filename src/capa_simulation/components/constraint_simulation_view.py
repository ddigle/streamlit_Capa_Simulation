# Purpose: 제약 시뮬레이션 본문(보기 전환·월별 그래프·계산표·고른 달 계산·개조 일정·모자란 달)을
# 프래그먼트로 그린다.

"""제약 시뮬레이션 — 본문 프래그먼트(`constraint_sim_view`)와 그 둘레(요약 넷).

페이지(`app_pages/constraint_simulation.py`)가 앱 전체 회차에서 조건·계획·계산을 모두 정해
`ConstraintView` 하나로 넘기면, 여기서는 **고른 달과 비중 토글**에 닿는 것만 그린다 — 달 누름(그래프
칸· 계산표 칸)과 비중 토글은 카드에 설 위젯을 바꾸지 않는 본문 조작이라 이 프래그먼트만 다시
돈다(AGENTS 9장 「본문 프래그먼트」). 프래그먼트 회차는 직전 앱 전체 회차의 인자(계산 결과·오늘·화면
글자)를 쓴다.

- **보기 줄** — 「소요 비중대로 나눴을 때 함께 보기」 토글(`persist_state="session"` — 보기 조건).
- **위 줄** — 월별 확보율 그래프(`CONSTRAINT_CHART_KEY`)와 그 옆 고른 달의 계산 다섯
  단계(`month_steps` — 순수 함수)·결과 상자. 가로 컨테이너 하나(3 : 2)이고 줄 폭이
  `TOP_ROW_STACK_BELOW_PX` 보다 좁으면 위아래로 쌓는다(`top_row_style` — 컨테이너 질의, 필요
  단축 일정 「Qual 마감 계산기」 팝업과 같은 꼴). 그래프는 가장 좁은 폭(`chart_min_width_px`)을 받고
  카드가 그보다 좁으면(390px 창) 카드 안에서 가로로 스크롤한다 — 세운 달 눈금 30개가 포개지지 않게
  (같은 스타일 칸이라 이벤트 칸이 늘지 않는다). **그 아래 온 폭** — 월별 계산표(라벨
  Figure + 가로로 스크롤되는 월 Figure `CONSTRAINT_SHEET_KEY`). 계산표는 컬럼 안에 넣지
  않는다 — 두 컬럼 폭 규칙(`split_scroll_columns_style` 의 `:has()`)이 바깥 컬럼에도
  걸린다. 칸을 누르면 `on_select` **콜백**이 고른 달을 적는다 — 회차마다 두 그림의 선택
  상태를 읽으면 브라우저에 남은 다른 그림의 옛 선택이 마지막 누름을 덮는다. 세대 번호는
  두 그림이 한 칸을 나눠 써 누를 때마다 둘 다 새 요소가 된다(AGENTS 9장 「칸 선택 Plotly」).
- **맨 아래** — 개조 일정 · 가용이 모자란 달. 생겼다 사라지는 알림은 늘 서 있는 `st.container()` 칸
  안에 그린다(AGENTS 9장 「자리는 고정한다」).

**이벤트 칸 수는 갈래마다 같다** — 이 프래그먼트가 이벤트 칸에 쓰는 것은 스타일만 든 `st.html` 넷(위
줄 배치 · 계산표 두 컬럼 폭 · 라벨 칸 위 여백 · 스크롤 상자 — 뒤 셋은 공정 Capa 상세와 같은 틀)이고
어느 갈래(비중 켬·끔, 개조 켬·끔, 고른 달)에서도 넷 그대로다.

그림은 세션에 몇 벌 기억한다(`remembered_figures`, 공정 Capa 상세 `remembered_canvas` 꼴 — Streamlit
캐시가 아니다). 키는 그림 모양 버전·테마·계산 결과(값으로 같다)·화면 글자·고른 달·비중 토글·세대다.

요약 넷(`render_constraint_kpis`)은 고른 달·보기와 무관해 프래그먼트 밖에서 페이지가 그린다.

보유 제약 설비·「신규 설비는 개조 없이」 가 걸리면(`ConstraintConditions.splits_dedicated`) 전용
대수를 `FILL_ORDER` 차례(지금 「신규 · 보유 · 개조」)로 나눠 적는다 — 2·3단계 회색 줄, 요약 넷
「개조 대수」(값 = 실제로 개조하는 대수, 회색 줄 = 전용 최대의 구성), 개조 일정 카드 머리 한
줄(`free_units_line`). 신규 대기는 3단계(개조 중 비가동 옆)·4단계 식·개조 일정 카드의 「신규 대기」
줄(`waiting_lines`)과 일반 설비가 된 신규 한 줄(`ordinary_line`)에 선다. 걸리지 않으면 1판 글
그대로다. 보유의 출처와 크기(고른 호기 · 입력 칸 · 그 달 W/D 첫날 보유가 바뀌는 달)는 개조 일정 카드
머리 한 줄에 적고(`holdings_text`, 2026-11-01 결정 B3), 남은 보유가 남은 증가를 다 덮어 신규를
붙이지 않은 호기가 있으면 그 카드가 한 줄로 말한다(`new_stopped_line` — 결정 B1, 증가마다: 첫
증가부터면 `NEW_SKIPPED_TEXT`, 뒤 증가부터면 그 달). 일반 설비가 된 신규의 까닭은 호기마다
가른다(`held_back_from`). 묶음 신규의 모듈 몫은 「HB-07(HB-07B)」 처럼 모듈을 붙여 적는다
(`NewUnitAssignment.label`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from typing import Final, NamedTuple

import plotly.graph_objects as go
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.constraint_simulation_figures import (
    ABOVE_MARK,
    CONSTRAINT_FIGURE_SCHEMA_VERSION,
    MINIMUM_UNIT_WORDS,
    ConstraintLabels,
    SheetCanvas,
    build_sheet_canvas,
    chart_min_width_px,
    chart_point_month,
    dedicated_split_text,
    free_parts,
    general_label,
    held_back_from,
    minimum_rate,
    minimum_unit,
    month_name,
    rate_axis,
    rate_figure,
    rate_text,
    signed_points,
    units_text,
    waiting_text,
)
from capa_simulation.components.formula_text import digits_within, operand_text, shared_digits
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    NARROW_LABEL_COLUMN_WIDTH_PX,
    NARROW_VIEWPORT_MAX_PX,
)
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.month_sheet_canvas import canvas_point
from capa_simulation.components.plotly_layout import hover_chart_config, static_chart_config
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    min_width_scroll_canvas,
    min_width_scroll_rules,
    split_scroll_columns_style,
)
from capa_simulation.components.status_metric import (
    MetricTone,
    metric_row,
    render_status_metric,
)
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_CHART_KEY,
    CONSTRAINT_FIGURE_MEMO_KEY,
    CONSTRAINT_MONTH_KEY,
    CONSTRAINT_MONTH_PICKED_KEY,
    CONSTRAINT_PROPORTIONAL_KEY,
    CONSTRAINT_SELECT_GENERATION_KEY,
    CONSTRAINT_SHEET_KEY,
    CONSTRAINT_VIEW_FRAGMENT_KEY,
    DEFAULT_PROPORTIONAL,
    seed_toggle,
)
from capa_simulation.design import theme, tokens
from capa_simulation.services.constraint_simulation import (
    ConstraintConditions,
    ConstraintMonth,
    ConstraintResult,
    ModificationWindow,
    NewUnit,
    NewUnitAssignment,
)
from capa_simulation.services.korean_particle import with_object_particle, with_topic_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.threshold_label import threshold_percent_label
from capa_simulation.sidebar_status import rerun_app_unless_alone

__all__ = [
    "KPI_ROW_KEY",
    "NEW_SKIPPED_TEXT",
    "SCHEDULE_CARD_KEY",
    "SHORT_INLINE_LIMIT",
    "SHORT_MONTHS_EXPANDER_KEY",
    "STEPS_CARD_KEY",
    "ConstraintView",
    "MonthStep",
    "MonthSteps",
    "default_month",
    "free_units_line",
    "holdings_text",
    "month_steps",
    "new_stopped_line",
    "ordinary_line",
    "overdrawn_lines",
    "pick_chart_month",
    "pick_sheet_month",
    "remembered_figures",
    "render_constraint_kpis",
    "render_constraint_view",
    "schedule_lines",
    "settle_selected_month",
    "short_lines",
    "short_month_lines",
    "top_row_style",
    "waiting_lines",
]

KPI_ROW_KEY: Final = "constraint_sim_kpis"
_FIGURE_MEMO_LIMIT: Final = 4
_SHEET_LABEL_CANVAS_KEY: Final = "constraint_sim_sheet_label_canvas"
_SHEET_LABEL_CHART_KEY: Final = "constraint_sim_sheet_labels"
_SHEET_MONTH_REGION_KEY: Final = "constraint_sim_sheet_month_region"
_SHEET_SCROLL_KEY: Final = "constraint_sim_sheet"
_SHEET_SCROLLBAR_KEY: Final = "constraint_sim_sheet_scrollbar"
STEPS_CARD_KEY: Final = "constraint_sim_steps"
SCHEDULE_CARD_KEY: Final = "constraint_sim_schedule"
# 위 줄(그래프 카드 + 고른 달 계산 카드) 가로 컨테이너와 그래프 카드.
TOP_ROW_KEY: Final = "constraint_sim_top_row"
CHART_CARD_KEY: Final = "constraint_sim_chart_card"
# 그래프 카드 안의 가로 스크롤 상자(`{접두}_scroll`)와 그 안 캔버스(`{접두}_canvas` — 가장 좁은 폭
# `chart_min_width_px`). `scroll_shell.min_width_scroll_canvas` 가 이 접두로 key 를 붙인다.
CHART_SCROLL_PREFIX: Final = "constraint_sim_chart"
_TOP_ROW_CONTAINER_NAME: Final = "capa-constraint-top"
# 위 줄이 이보다 좁으면 그래프 위·계산 아래로 쌓는다. 3 : 2 로 두면 사이드바를 편 900px 창에서
# 그래프 그림 칸이 169 × 130px(달 한 칸 14px)로 줄어 칸 누름(D9)이 어려웠다(2026-10-25 리뷰, 사본
# 앱). 이 폭이면 그래프 카드가 약 530px 아래로 내려가지 않는다(1280px 창 · 사이드바 펼침은 나란히
# 선다).
TOP_ROW_STACK_BELOW_PX: Final = 900
_EMPTY: Final = "—"
SCHEDULE_DEFINITION: Final = (
    "개조 비가동은 그 달 W/D 첫날(그 달 1일 − Cut-off)을 끝으로, 개조 기간만큼 앞서 "
    "잡습니다. 그동안 그 대수는 공정 전체 가용대수에서 빠집니다(달마다 W/D 일수 비율)."
)
NO_WINDOWS_TEXT: Final = "개조가 필요한 달이 없습니다."
FREE_ONLY_TEXT: Final = "늘어난 전용 대수를 모두 보유·신규 설비로 채워 개조가 없습니다."
NEW_SKIPPED_TEXT: Final = (
    "보유 제약 설비만으로 제약 기간 끝까지 늘어난 전용을 다 채워 신규 설비는 붙이지 않았습니다 — "
    "신규는 기존 제품 몫입니다(신규 대기 없음)."
)
SKIPPED_REASON: Final = "보유 제약 설비로 제약 기간을 다 덮어"
MODIFY_OFF_TEXT: Final = "개조를 켜면 제약 제품에 떼어 줄 대수만큼 개조 비가동이 잡힙니다."
BEFORE_RANGE_TEXT: Final = (
    "첫 개조 비가동이 표의 첫 달보다 앞에서 시작합니다 — 그 앞 달의 감소는 표에 없습니다."
)
WAIT_BEFORE_RANGE_TEXT: Final = (
    "첫 신규 대기가 표의 첫 달보다 앞에서 시작합니다 — 그 앞 달의 감소는 표에 없습니다."
)
WAITING_DEFINITION: Final = (
    "신규 대기는 셋업 때부터 제약용으로 붙인 신규 설비가 그 달 W/D 첫날까지 기다리는 동안입니다 — "
    "기존 제품이 못 써 개조 비가동처럼 공정 전체 가용대수에서 빠집니다(개조 기간보다 짧습니다)."
)
LATE_SUFFIX: Final = " — 이미 지난 날짜(개조를 이미 시작했어야 합니다)"
WAIT_LATE_SUFFIX: Final = " — 이미 지난 날짜(셋업 때 이미 제약용으로 붙였어야 합니다)"
# 가용이 모자란 달을 한 줄에 달마다 적는 상한 — 넘으면 달 수만 적고 달마다 값은 접는다(30개월이 캡션
# 한 줄로 늘어졌다, 2026-10-25 E2E).
SHORT_INLINE_LIMIT: Final = 3
SHORT_REASON_TEXT: Final = "제약 제품을 먼저 채우고 남는 것이 없어 기존 제품이 0 에 가깝습니다."
# 「달마다 보기」 펼침 — 모자란 달이 많을 때만 선다.
SHORT_MONTHS_EXPANDER_KEY: Final = "constraint_sim_short_months"


class ConstraintView(NamedTuple):
    """본문 프래그먼트 인자 — 직전 앱 전체 회차의 결과."""

    result: ConstraintResult
    labels: ConstraintLabels
    today: date


class MonthStep(NamedTuple):
    body: str
    """마크다운 한 줄(제품·공정 이름은 escape 했다)."""

    note: str
    """회색 줄(마크다운)."""


class MonthSteps(NamedTuple):
    """고른 달의 계산 다섯 단계와 결과 상자."""

    title: str
    steps: tuple[MonthStep, ...]
    verdict: str
    """결과 상자 글. 기존 확보율이 없으면 빈 글자."""

    verdict_secure: bool | None
    """기존 제품이 기준 이상인가(상자 색). 확보율이 없으면 None."""

    proportional: str
    """「비중대로만 나눴다면 …」 한 줄. 토글 끔·기간 밖이면 빈 글자."""


# ================================================================== 고른 달


def default_month(result: ConstraintResult) -> int:
    """기본 고른 달 — 영향 시작 달 → 없으면 기간 시작 달(보이는 달) → 없으면 첫 달."""
    months = [row.month for row in result.months]
    impact = result.kpis.first_impact_month
    if impact is not None and impact in months:
        return impact
    in_period = [row.month for row in result.months if row.in_period]
    if in_period:
        return in_period[0]
    return months[0]


def settle_selected_month(result: ConstraintResult) -> int:
    """앱 전체 회차마다 고른 달 칸을 잡는다.

    사용자가 달 칸을 눌러 고른 적이 있고(`CONSTRAINT_MONTH_PICKED_KEY`) 그 달이 보이면 그대로다.
    아니면 기본 달(`default_month`)을 **다를 때만** 적는다 — 누르기 전에는 조건이 바뀔 때마다 그
    조건의 영향 시작 달로 다시 선다(기간 밖 달 계산이 남지 않게). 누른 달이 보이는 달 밖으로 나가면
    표지를 내려 다시 기본 달을 따른다."""
    months = {row.month for row in result.months}
    held = st.session_state.get(CONSTRAINT_MONTH_KEY)
    visible = isinstance(held, int) and not isinstance(held, bool) and held in months
    if st.session_state.get(CONSTRAINT_MONTH_PICKED_KEY) is True:
        if visible and isinstance(held, int):
            return held
        st.session_state[CONSTRAINT_MONTH_PICKED_KEY] = False
    chosen = default_month(result)
    if held != chosen:
        st.session_state[CONSTRAINT_MONTH_KEY] = chosen
    return chosen


def _viewed_month(result: ConstraintResult) -> int:
    held = st.session_state.get(CONSTRAINT_MONTH_KEY)
    months = [row.month for row in result.months]
    if isinstance(held, int) and not isinstance(held, bool) and held in months:
        return held
    return default_month(result)


def _apply_pick(month: int | None, months: Sequence[int], widget_key: str) -> None:
    if month is not None and month in set(int(value) for value in months):
        st.session_state[CONSTRAINT_MONTH_KEY] = int(month)
        st.session_state[CONSTRAINT_MONTH_PICKED_KEY] = True
    generation = st.session_state.get(CONSTRAINT_SELECT_GENERATION_KEY, 0)
    st.session_state[CONSTRAINT_SELECT_GENERATION_KEY] = (
        int(generation) + 1 if isinstance(generation, int) else 1
    )
    rerun_app_unless_alone(widget_key)


def pick_chart_month(months: Sequence[int]) -> None:
    """그래프 칸 누름 콜백 — 누른 칸의 달을 적고 세대를 올린다. 빈 선택은 보던 달 그대로다."""
    _apply_pick(
        chart_point_month(st.session_state.get(CONSTRAINT_CHART_KEY)), months, CONSTRAINT_CHART_KEY
    )


def pick_sheet_month(months: Sequence[int]) -> None:
    """계산표 칸 누름 콜백 — 누른 칸의 달(행과 상관없이 그 열)을 적고 세대를 올린다."""
    point = canvas_point(st.session_state.get(CONSTRAINT_SHEET_KEY))
    _apply_pick(point[0] if point is not None else None, months, CONSTRAINT_SHEET_KEY)


# ================================================================== 그림 memo


def remembered_figures(
    view: ConstraintView, *, month: int, show_proportional: bool, generation: int
) -> tuple[go.Figure, SheetCanvas]:
    """(그래프, 계산표) 를 세션에 몇 벌 기억한다. 꺼낸 그림은 고치지 않는다.

    키는 그림 모양 버전·테마·계산 결과(조건·달·값 — 값으로 같다)·화면 글자·고른 달·비중 토글·세대다.
    만들다 실패하면 기억하지 않는다. 새 `st.cache_data` 를 두지 않는다(CLAUDE.md 캐시 경계).
    """
    key = (
        CONSTRAINT_FIGURE_SCHEMA_VERSION,
        theme.current_mode(),
        view.result,
        view.labels,
        int(month),
        bool(show_proportional),
        int(generation),
    )
    memo = st.session_state.get(CONSTRAINT_FIGURE_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], tuple[go.Figure, SheetCanvas]]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key:
            return stored
    chart = rate_figure(
        view.result,
        view.labels,
        selected_month=month,
        show_proportional=show_proportional,
        generation=generation,
    )
    sheet = build_sheet_canvas(
        view.result,
        view.labels,
        selected_month=month,
        show_proportional=show_proportional,
        generation=generation,
    )
    entries = [entry for entry in entries if entry[0] != key][-(_FIGURE_MEMO_LIMIT - 1) :]
    st.session_state[CONSTRAINT_FIGURE_MEMO_KEY] = [*entries, (key, (chart, sheet))]
    return chart, sheet


# ================================================================== 고른 달 계산(순수)


def _target_percent_text(value: float) -> str:
    return threshold_percent_label(value)


def month_steps(
    row: ConstraintMonth,
    result: ConstraintResult,
    labels: ConstraintLabels,
    *,
    show_proportional: bool,
) -> MonthSteps:
    """고른 달의 계산 다섯 단계 — 순수 함수(세션·그림을 보지 않는다).

    단계 식(1·2·4·5단계)은 적힌 수로 다시 셈해도 적힌 결과가 나와야 한다 — 대수는 둘째
    자리(`units_text`)로 적고, 깎은 인수로 어긋날 때만 인수를 한 자리씩 더 적는다
    (`formula_text.operand_text` — 「0.02 × 120% = 0.03」 이 아니라 「0.021 × 120% = 0.03」).
    늘리는 자릿수는 **카드에 한 벌**이다 — 네 식이 함께 맞는 가장 적은 자릿수(`shared_digits`)로
    모든 식의 인수를 적어 여러 식의 인수로 서는 같은 수(1·5단계의 기존 소요, 1·2단계의 제약
    소요)가 「1.96」·「1.9637」 두 꼴로 보이지 않게 한다. 그런 자릿수가 없을 때만
    식마다 고르고(`digits_within` → `consistent_digits`), 그 식이 어느 자릿수로도 못 맞추면 둘째
    자리와 「≈」 다. 굵은 결과(소요·3단계 비가동·신규 대기·기존 가용·확보율)는 늘 화면 자릿수라,
    자리를 늘린 카드에서는 굵은 수와 같은 값의 인수가 자릿수만 다르게 설 수 있다(1단계 「소요
    **1.96대** = 기존 1.9637 + 0」, 3단계 「−0.46대」 와 4단계 「3.4567 − 0.4567」)."""
    product = literal_markdown(labels.product)
    process = literal_markdown(labels.process_label)
    modifies = result.conditions.modifies
    target = labels.target_percent

    title = f"{month_label(row.month)} · {process}" + (" · 제약 기간" if row.in_period else "")
    required_shown = units_text(row.required)

    def split_sum(digits: int) -> str:
        return units_text(
            round(row.existing_demand, digits) + round(row.constrained_demand, digits)
        )

    def demand_product(digits: int) -> str:
        return f"{round(row.constrained_demand, digits) * target / 100:.2f}"

    def usable_rest(digits: int) -> str:
        # 적힌 수로 「공정 가용 − 개조 중 − 신규 대기 − 제약 배정」 을 다시 셈한다 — 비가동이
        # 가용보다 많으면 쓸 수 있는 가용을 0 으로 두는 것까지 서비스(`simulate_constraint`)와 같은
        # 차례다.
        return units_text(
            max(
                0.0,
                round(row.available, digits)
                - round(row.downtime, digits)
                - round(row.waiting, digits),
            )
            - row.allocated
        )

    def existing_ratio(digits: int) -> str:
        demand = round(row.existing_demand, digits)
        return rate_text(round(row.existing_available, digits) / demand) if demand else ""

    has_need = row.in_period and row.constrained_demand > 0
    product_text = f"{row.constrained_demand * target / 100:.2f}"
    available_shown = units_text(row.existing_available)
    has_subtraction = row.downtime > 0 or row.waiting > 0 or row.allocated > 0
    rate_shown = rate_text(row.existing_rate)
    # 이 카드에 서는 식들(1단계는 늘, 나머지는 그 식이 설 때만).
    card_formulas: list[tuple[Callable[[int], str], str]] = [(split_sum, required_shown)]
    if has_need:
        card_formulas.append((demand_product, product_text))
    if has_subtraction:
        card_formulas.append((usable_rest, available_shown))
    if row.existing_rate is not None:
        card_formulas.append((existing_ratio, rate_shown))
    card_digits = shared_digits(card_formulas)

    split_digits, split_sign = digits_within(card_digits, split_sum, required_shown)
    step1 = MonthStep(
        f"소요 **{required_shown}대** {split_sign} 기존 "
        f"{operand_text(row.existing_demand, split_digits, units_text)} + "
        f"{product} {operand_text(row.constrained_demand, split_digits, units_text)}",
        "제약 기간이라 공정 소요를 두 갈래로 나눕니다(합하면 원래 소요와 같습니다)."
        if row.in_period
        else f"제약 기간 밖이라 {product} 도 기존 제품에 함께 셉니다.",
    )

    if has_need:
        demand_digits, demand_sign = digits_within(card_digits, demand_product, product_text)
        demand_text = operand_text(row.constrained_demand, demand_digits, units_text)
        body2 = (
            f"{product} 필요 대수 = {demand_text} × {target}% {demand_sign} {product_text} → "
            f"**{row.need}대**" + ("(최소)" if minimum_unit(row) else "")
        )
    elif row.in_period and row.dedicated > 0:
        body2 = f"{product} 소요 없음 — 전용 **{row.dedicated}대** 유지"
    else:
        body2 = "제약 제품에 따로 떼는 대수 없음"
    conditions = result.conditions
    # 구성 글은 수와 정해진 낱말뿐이라 escape 하지 않는다(「=」 가 「\=」 로 보이지 않게).
    split = dedicated_split_text(row, conditions) if row.in_period else ""
    if row.in_period and modifies and row.dedicated > row.need:
        note2 = (
            f"전용 {row.dedicated}대는 기간 안에서 그대로 남습니다(줄여도 되돌리지 않음)."
            if split
            else f"이미 개조한 {row.dedicated}대는 전용으로 남습니다(줄여도 되돌리지 않음)."
        )
    elif minimum_rate(row):
        note2 = (
            "소요가 1대 미만이어도 정수로 올려 최소 1대를 뗍니다 — 제약 제품 확보율이 아주 크게 "
            "나오는 까닭입니다."
        )
    elif row.in_period and row.constrained_demand > 0:
        note2 = "제약 확보율을 먼저 맞추도록 정수로 올립니다."
    else:
        note2 = ""
    if split:
        note2 = f"{split} · {note2}" if note2 else split
    step2 = MonthStep(body2, note2)

    if not modifies:
        step3 = MonthStep("개조 없음 — 비가동 없이 나누기만 합니다", "")
    else:
        step3 = _modification_step(row, result)

    available_digits, available_sign = digits_within(card_digits, usable_rest, available_shown)
    usable = [operand_text(row.available, available_digits, units_text)]
    note_pieces = ["공정 가용"]
    if row.downtime > 0:
        usable.append(operand_text(row.downtime, available_digits, units_text))
        note_pieces.append("개조 중")
    if row.waiting > 0:
        usable.append(operand_text(row.waiting, available_digits, units_text))
        note_pieces.append("신규 대기")
    # 비가동이 가용보다 많으면 쓸 수 있는 가용을 0 으로 둔다 — 「9 − 16.45 = 0」 이 아니라 식에
    # 「max(0, 9 − 16.45)」 로 보인다(2026-10-25 E2E #110).
    usable_text = " − ".join(usable)
    pieces = [f"max(0, {usable_text})" if row.overdrawn else usable_text]
    if row.allocated > 0:
        pieces.append(str(row.allocated))
        note_pieces.append("제약 배정")
    note4 = " − ".join(note_pieces)
    if row.short:
        note4 += f" (가용이 모자라 제약 배정이 {row.dedicated}대에 못 미침)"
    if row.overdrawn:
        note4 += " · 비가동이 가용보다 많아 쓸 수 있는 가용을 0 으로 둡니다"
    body4 = (
        f"기존 가용 = {' − '.join(pieces)} {available_sign} **{available_shown}대**"
        if has_subtraction
        else f"기존 가용 = 공정 가용 **{available_shown}대**"
    )
    step4 = MonthStep(body4, note4)

    if row.existing_rate is None:
        step5 = MonthStep("기존 제품 소요가 없어 기존 확보율이 없습니다", "")
    else:
        note5 = f"제약 없을 때 {rate_text(row.baseline_rate)}"
        if row.baseline_rate is not None:
            note5 += f" · {signed_points(row.existing_rate - row.baseline_rate)}"
        rate_digits, rate_sign = digits_within(card_digits, existing_ratio, rate_shown)
        available_text = operand_text(row.existing_available, rate_digits, units_text)
        demand_text = operand_text(row.existing_demand, rate_digits, units_text)
        step5 = MonthStep(
            f"기존 확보율 = {available_text} ÷ {demand_text} {rate_sign} **{rate_shown}**",
            note5,
        )

    general_text = (
        f"{labels.general_percent:g}%"
        if labels.general_percent is not None
        else _target_percent_text(row.general_target)
    )
    if row.existing_rate is None:
        verdict = ""
    else:
        verdict = (
            f"기존 제품이 기준 {with_object_particle(general_text)} 지킵니다"
            if row.existing_secure
            else f"기존 제품이 기준 {general_text} 에 못 미칩니다"
        )
        if row.constrained_rate is not None:
            met = "충족" if row.met else "미달"
            minimum = f" · 소요 1대 미만에 {MINIMUM_UNIT_WORDS}" if minimum_rate(row) else ""
            verdict += (
                f" · 제약 제품 {rate_text(row.constrained_rate)} (제약 {target}% {met}{minimum})"
            )

    proportional = ""
    if show_proportional and row.in_period:
        proportional = (
            f"비중대로만 나눴다면: 제약 {row.proportional_constrained}대"
            f"({rate_text(row.proportional_constrained_rate)}) · 기존 "
            f"{units_text(row.proportional_existing)}대({rate_text(row.proportional_existing_rate)})"
            " — 개조 비가동 없이 가용을 소요 비중대로 정수로 나눈 경우입니다."
        )
    return MonthSteps(
        title=title,
        steps=(step1, step2, step3, step4, step5),
        verdict=verdict,
        verdict_secure=row.existing_secure,
        proportional=proportional,
    )


def _modification_step(row: ConstraintMonth, result: ConstraintResult) -> MonthStep:
    """3단계(개조 켬) — 개조 중 비가동과 신규 대기, 회색 줄은 그 몫들과 늘어난 전용의 갈림."""
    conditions = result.conditions
    takes_new = conditions.uses_new_units
    shown = [
        f"{label} **−{units_text(value)}대**"
        for label, value in (("개조 중 비가동", row.downtime), ("신규 대기", row.waiting))
        if value > 0
    ]
    if shown:
        body = " · ".join(shown)
    else:
        body = "이 달 개조 비가동·신규 대기 없음" if takes_new else "이 달 개조 비가동 없음"
    notes = [
        f"{month_name(share.source_month)} 몫 {share.units}대가 이 달 {share.days}일 개조 중 "
        f"→ {units_text(share.equivalent)}대"
        for share in row.downtime_shares
    ]
    if not notes and row.increment > 0:
        notes.append(f"이 달 몫 {row.increment}대는 앞 달에 개조를 마칩니다.")
    notes += [
        f"신규 {literal_markdown(share.label)} {units_text(share.units)}대가 이 달 {share.days}일 "
        f"대기({month_name(share.source_month)} 몫) → {units_text(share.equivalent)}대"
        for share in row.waiting_shares
    ]
    notes += [
        f"이 달 몫 신규 {literal_markdown(item.label)} {units_text(item.units)}대 — "
        f"{_markdown_waiting(item)}"
        for item in result.assignments
        if item.month == row.month
    ]
    if row.overdrawn:
        notes.append("비가동이 가용보다 많아 쓸 수 있는 가용은 0 입니다.")
    growth_note = _growth_note(row, conditions)
    if growth_note:
        notes.insert(0, growth_note)
    if takes_new:
        ordinary = [
            unit for unit in result.units_starting_in(row.month) if result.left_units(unit) > 0
        ]
        for reason, members in _by_reason(ordinary, result):
            names = ", ".join(_ordinary_name(unit, result) for unit in members)
            notes.append(
                f"이 달 들어온 신규 {names} — {reason} 기존 제품 몫입니다(나중에 제약에 쓰려면 "
                "개조)."
            )
    return MonthStep(body, " · ".join(notes))


def _growth_note(row: ConstraintMonth, conditions: ConstraintConditions) -> str:
    """3단계 회색 줄 머리 — 「이 달 늘어난 전용 6대 — 신규 설비 1대 · 보유 제약 설비 4대는 개조
    없이, 개조 1대」(`FILL_ORDER` 차례). 나눠 보이지 않거나 늘어난 대수가 없으면 빈 글자."""
    if not conditions.splits_dedicated or row.growth <= 0:
        return ""
    free = free_parts(
        conditions, f"보유 제약 설비 {row.owned_increment}대", f"신규 설비 {row.new_increment}대"
    )
    joined = with_topic_particle(" · ".join(free))
    return f"이 달 늘어난 전용 {row.growth}대 — {joined} 개조 없이, 개조 {row.increment}대"


def holdings_text(result: ConstraintResult) -> str:
    """보유의 출처와 크기 — 「입력 4대」(목록에 없는 보유 칸만), 「고른 호기 3대 · 보유 2.50대」,
    「고른 호기 2대 · 입력 1대 · 보유 3대 · 27년 7월부터 2대」(그 달 W/D 첫날 보유가 기간 안에서
    바뀌면 바뀐 달 둘까지, 그 뒤는 「외 n번」). 보유가 걸리지 않으면 빈 글자."""
    conditions = result.conditions
    if not conditions.uses_owned_units:
        return ""
    if not conditions.held_units:
        return f"입력 {conditions.owned_units}대"
    source = f"고른 호기 {len(conditions.held_units)}대"
    if conditions.owned_units:
        source = f"{source} · 입력 {conditions.owned_units}대"
    steps: list[tuple[int, float]] = []
    for row in result.months:
        if row.in_period and (not steps or abs(row.holdings - steps[-1][1]) > 1e-9):
            steps.append((row.month, row.holdings))
    if not steps:
        return source
    text = f"{source} · 보유 {units_text(steps[0][1])}대"
    changes = steps[1:]
    text += "".join(
        f" · {month_name(month)}부터 {units_text(value)}대" for month, value in changes[:2]
    )
    if len(changes) > 2:
        text += f" 외 {len(changes) - 2}번"
    return text


def free_units_line(result: ConstraintResult) -> str:
    """개조 일정 카드 머리 한 줄 — 개조 없이 쓰는 전용(`FILL_ORDER` 차례). 나눠 보이지 않으면 빈
    글자."""
    conditions = result.conditions
    if not conditions.splits_dedicated:
        return ""
    kpis = result.kpis
    since = conditions.new_unit_since.isoformat() if conditions.new_unit_since else "—"
    parts = free_parts(
        conditions,
        f"보유 제약 설비 {kpis.owned_used}대({holdings_text(result)} 중)",
        f"신규 설비 {kpis.new_used}대(기준일 {since} 이후 기여 시작 · 개조 "
        f"{conditions.modification_days}일 안에 늘어날 전용에 붙임)",
    )
    return "개조 없이 쓰는 전용 — " + " · ".join(parts)


def waiting_lines(assignments: Sequence[NewUnitAssignment], *, today: date) -> list[str]:
    """신규 대기 줄 — 「27년 7월 몫 · 신규 HB-07 · 2027-06-10 ~ 2027-06-23 대기 14일 · **1대**」.
    대기 첫날이 오늘보다 앞이면 꼬리."""
    lines: list[str] = []
    for item in assignments:
        line = (
            f"{month_name(item.month)} 몫 · 신규 {literal_markdown(item.label)} · "
            f"{_markdown_waiting(item)} · **{units_text(item.units)}대**"
        )
        if item.days > 0 and item.start < today:
            line += WAIT_LATE_SUFFIX
        lines.append(line)
    return lines


def _markdown_waiting(item: NewUnitAssignment) -> str:
    """마크다운에 싣는 대기 날짜 글 — 물결표만 막는다(두 줄의 「~」 가 취소선이 되지 않게)."""
    return markdown_safe_tildes(waiting_text(item))


def _ordinary_name(unit: NewUnit, result: ConstraintResult) -> str:
    """일반 설비가 된 신규의 이름 — 일부만 붙은 호기(환산비가 1 이 아님)는 「C 남는 0.5대」 로
    남는 몫을 붙인다(같은 호기를 「붙음」 과 「기존 제품 몫」 으로 함께 적지 않게)."""
    name = literal_markdown(unit.name)
    if result.assigned_units(unit) > 0:
        return f"{name} 남는 {units_text(result.left_units(unit))}대"
    return name


def _ordinary_reason(unit: NewUnit, result: ConstraintResult) -> str:
    """일반 설비가 된 신규의 까닭 — 이음 꼴(뒤에 「기존 제품 몫」 이 붙는다). 결정 B1 로 붙지 않은
    호기(`held_back_from`)는 첫 증가부터 덮였으면 `SKIPPED_REASON`, 뒤 증가부터면 「27년 7월
    증가부터 보유 제약 설비로 다 덮어」(2026-11-01 — 증가마다), 창 안에 증가가 없던 호기는 「개조
    30일 안에 늘어날 전용이 없어」. 풍선 꼴(`new_unit_fate`)과 같은 갈래다."""
    stopped = held_back_from(unit, result)
    if stopped is None:
        return f"개조 {result.conditions.modification_days}일 안에 늘어날 전용이 없어"
    if result.new_units_skipped:
        return SKIPPED_REASON
    return f"{month_name(stopped)} 증가부터 보유 제약 설비로 다 덮어"


def _by_reason(
    units: Sequence[NewUnit], result: ConstraintResult
) -> list[tuple[str, list[NewUnit]]]:
    """까닭이 같은 호기끼리 묶는다 — 처음 나온 차례 그대로(까닭이 하나면 한 묶음)."""
    groups: dict[str, list[NewUnit]] = {}
    for unit in units:
        groups.setdefault(_ordinary_reason(unit, result), []).append(unit)
    return list(groups.items())


def ordinary_line(result: ConstraintResult) -> str:
    """일반 설비가 된 신규 한 줄 — 까닭(`_ordinary_reason`)마다 이름과 「기존 제품 몫」, 묶음 사이는
    「 / 」. 대수는 남는 몫의 환산 합이다(`left_units` — 일부만 붙은 호기는 남는 몫만). 이름은 까닭
    묶음마다 넷까지(「외 n호기」). 없으면 빈 글자."""
    units = result.ordinary_units
    if not units:
        return ""
    total = sum(result.left_units(unit) for unit in units)
    parts: list[str] = []
    for reason, members in _by_reason(units, result):
        names = ", ".join(_ordinary_name(unit, result) for unit in members[:4])
        more = f" 외 {len(members) - 4}호기" if len(members) > 4 else ""
        parts.append(f"{names}{more} · {reason} 기존 제품 몫")
    return f"일반 설비가 된 신규 {units_text(total)}대 — {' / '.join(parts)}(제약에 쓰려면 개조)"


def new_stopped_line(result: ConstraintResult) -> str:
    """결정 B1 로 신규를 붙이지 않은 한 줄 — 붙지 않은 호기(`held_back_units`)가 있을 때만. 첫
    증가부터 덮였으면 `NEW_SKIPPED_TEXT`, 뒤 증가부터면 그 달을 적는다(2026-11-01 — 증가마다).
    창 안에 증가가 없어 어차피 붙지 않았을 신규뿐이면 빈 글자다."""
    stopped = result.new_units_stopped_month
    if stopped is None or not result.held_back_units:
        return ""
    if result.new_units_skipped:
        return NEW_SKIPPED_TEXT
    return (
        f"{month_name(stopped)} 증가부터는 남은 보유 제약 설비만으로 제약 기간 끝까지 늘어난 "
        "전용을 다 채워 신규 설비를 더 붙이지 않았습니다 — 그 뒤 신규는 기존 제품 몫입니다."
    )


def schedule_lines(windows: Sequence[ModificationWindow], *, today: date) -> list[str]:
    """개조 일정 줄 — 「27년 6월 몫 · 2027-04-25 ~ 2027-05-24 비가동 · **6대**」. 첫날이 오늘보다
    앞이면 꼬리."""
    lines: list[str] = []
    for window in windows:
        line = (
            f"{month_name(window.month)} 몫 · {window.start.isoformat()} \\~ "
            f"{window.last_day.isoformat()} 비가동 · **{window.units}대**"
        )
        if window.start < today:
            line += LATE_SUFFIX
        lines.append(line)
    return lines


def _short_month_text(row: ConstraintMonth) -> str:
    """모자란 달 하나 — 「27.06: 전용 6대 중 5대만 배정」. 값은 그 달 필요(need)가 아니라 떼어 줄
    전용 대수(dedicated)다 — 소요가 0 인 달도 이미 개조한 전용을 유지한다."""
    return f"{month_label(row.month)}: 전용 {row.dedicated}대 중 {row.allocated}대만 배정"


def short_lines(result: ConstraintResult) -> str:
    """가용이 모자란 달 한 줄. 없으면 빈 글자.

    달이 `SHORT_INLINE_LIMIT` 개 이하면 달마다 값을 한 줄에 적고, 그보다 많으면 달 수와 첫·끝 달만
    적는다 — 달마다 값은 접힌 「달마다 보기」(`short_month_lines`)가 든다(30개월이 한 줄로 늘어지지
    않게)."""
    rows = [row for row in result.months if row.short]
    if not rows:
        return ""
    if len(rows) <= SHORT_INLINE_LIMIT:
        head = " · ".join(_short_month_text(row) for row in rows)
    else:
        head = (
            f"전용 대수를 다 배정하지 못한 달 {len(rows)}개월"
            f"({month_label(rows[0].month)}–{month_label(rows[-1].month)} 사이)"
        )
    return f"{head} — {SHORT_REASON_TEXT}"


def short_month_lines(result: ConstraintResult) -> list[str]:
    """접힌 「달마다 보기」 의 줄 — 모자란 달이 `SHORT_INLINE_LIMIT` 개보다 많을 때만. 아니면 빈
    목록(한 줄 `short_lines` 가 이미 달마다 값을 적는다)."""
    rows = [row for row in result.months if row.short]
    if len(rows) <= SHORT_INLINE_LIMIT:
        return []
    return [_short_month_text(row) for row in rows]


def overdrawn_lines(result: ConstraintResult) -> list[str]:
    """개조 비가동이 그 달 가용보다 많은 달마다 한 줄."""
    return [
        f"{month_label(row.month)}: 개조 비가동 {units_text(row.downtime)}대가 가용 "
        f"{units_text(row.available)}대보다 많습니다 — 이 공정 설비로는 이 개조 일정이 "
        "서지 않습니다."
        for row in result.months
        if row.overdrawn
    ]


# ================================================================== 요약 넷(프래그먼트 밖)


def render_constraint_kpis(result: ConstraintResult, labels: ConstraintLabels) -> None:
    """요약 넷 — 제약 확보율 충족 · 기존 최저 확보율 · 기준 미달 달 · 개조 대수."""
    kpis = result.kpis
    target = labels.target_percent
    with metric_row(key=KPI_ROW_KEY):
        count = kpis.constrained_months
        met = kpis.constrained_met_months
        tone1: MetricTone = "neutral" if count == 0 else ("good" if met == count else "critical")
        if count == 0:
            caption1 = "제약 기간에 제약 제품 소요가 없습니다"
        elif met == count:
            caption1 = f"제약 기간 모든 달에서 {target}% 를 맞춥니다"
        else:
            caption1 = "가용이 모자란 달이 있습니다 — 아래 「가용이 모자란 달」"
        render_status_metric(
            "제약 제품 확보율 충족",
            f"{met} / {count}개월" if count else _EMPTY,
            key="constraint_sim_kpi_met",
            tone=tone1,
            caption=caption1,
            help=(
                "제약 기간 안이고 제약 제품 소요가 있는 달 가운데, 필요 대수"
                f"(소요 × {target}% 올림)를 다 배정한 달 수입니다."
            ),
        )

        lowest = (
            result.month(kpis.lowest_existing_month)
            if kpis.lowest_existing_month is not None
            else None
        )
        tone2: MetricTone = (
            "critical" if lowest is not None and lowest.existing_secure is False else "neutral"
        )
        render_status_metric(
            "기존 제품 최저 확보율",
            rate_text(kpis.lowest_existing_rate) if lowest is not None else _EMPTY,
            key="constraint_sim_kpi_lowest",
            tone=tone2,
            caption=(
                f"{month_label(lowest.month)} · 제약 없을 때 {rate_text(kpis.lowest_baseline_rate)}"
                if lowest is not None
                else None
            ),
            help="제약 제품에 먼저 떼어 준 뒤 기존 제품 몫으로 낸 확보율의 최솟값과 그 달입니다.",
        )

        below = len(kpis.below_months)
        newly = len(kpis.newly_below_months)
        tone3: MetricTone = "critical" if newly else ("attention" if below else "neutral")
        impact = (
            month_label(kpis.first_impact_month) if kpis.first_impact_month is not None else "없음"
        )
        render_status_metric(
            "기준 미달 달 (기존 제품)",
            f"{below}개월" if below else "없음",
            key="constraint_sim_kpi_below",
            tone=tone3,
            caption=f"그중 제약 때문에 새로 미달 {newly}개월 · 영향 시작 {impact}",
            help=(
                f"기존 제품 확보율이 그 달 기준({general_label(labels, result)})에 못 미친 달 "
                "수입니다. 「새로 미달」 은 제약이 없었다면 기준 이상이던 달, 「영향 시작」 은 "
                "기존 확보율이 제약 없을 때보다 낮아진 첫 달입니다."
            ),
        )

        splits = result.conditions.splits_dedicated
        if kpis.max_dedicated is None:
            value4, caption4 = _EMPTY, "개조를 끄면 비가동 없이 배정만 바꿉니다"
        elif splits and kpis.max_dedicated > 0:
            # 값은 실제로 개조하는(비가동을 만드는) 대수, 회색 줄은 전용 최대의 구성이다. 회색 줄은
            # 한 줄 알약이라 카드 넷이 한 줄에 서게 짧게 둔다 — 창 수·첫 비가동은 개조 일정 카드가
            # 말한다(2026-10-26 사본 앱 1440px: 긴 줄이면 넷째 카드가 아래 줄로 내려갔다).
            modified = kpis.modified_units or 0
            pieces = free_parts(
                result.conditions, f"보유 {kpis.owned_used}", f"신규 {kpis.new_used}"
            )
            pieces.append(f"개조 {modified}")
            value4 = f"{modified}대"
            caption4 = f"전용 최대 {kpis.max_dedicated}대 = {' · '.join(pieces)}"
        elif kpis.window_count == 0:
            # 제약 기간에 제약 제품 소요가 없으면 떼어 줄 대수도 개조 창도 없다 — 「0번에 나눠
            # 개조」 가 아니라 그 뜻을 바로 적는다(값 「0대」 는 명세 2-6 「max pool 대」 그대로).
            value4, caption4 = f"{kpis.max_dedicated}대", "개조할 대수가 없습니다"
        else:
            value4 = f"{kpis.max_dedicated}대"
            caption4 = f"{kpis.window_count}번에 나눠 개조" + (
                f" · 첫 비가동 {kpis.first_downtime_day.isoformat()}"
                if kpis.first_downtime_day is not None
                else ""
            )
        render_status_metric(
            "개조 대수",
            value4,
            key="constraint_sim_kpi_modification",
            caption=caption4,
            help=(
                "제약 기간 안에서 제약 제품 전용으로 개조하는 가장 큰 대수(환산 대수)입니다 — "
                "늘어나는 달마다 늘어난 대수만 그 달 앞에 새로 개조하고, 기간 안에서는 줄이지 "
                "않습니다."
                + (
                    " 보유 제약 설비와, 늘어날 전용이 개조 기간 안에 오는 신규 설비는 개조 "
                    "없이 먼저 쓰고(신규는 그 사이 「신규 대기」) 남는 몫만 개조합니다 — 값은 "
                    "실제로 개조하는 대수, 회색 줄은 전용 최대의 구성입니다."
                    if splits
                    else ""
                )
            ),
        )


# ================================================================== 본문 프래그먼트


@st.fragment(key=CONSTRAINT_VIEW_FRAGMENT_KEY)
def render_constraint_view(view: ConstraintView) -> None:
    """보기 줄 → 위 줄(그래프 · 고른 달 계산) → 계산표(온 폭) → 개조 일정 · 모자란 달."""
    result = view.result
    months = tuple(row.month for row in result.months)
    seed_toggle(CONSTRAINT_PROPORTIONAL_KEY, DEFAULT_PROPORTIONAL)
    show_proportional = st.toggle(
        "소요 비중대로 나눴을 때 함께 보기",
        key=CONSTRAINT_PROPORTIONAL_KEY,
        persist_state="session",
        help=(
            "개조 비가동 없이 가용을 소요 비중대로 정수(사사오입)로 나눴을 때의 기존 제품 확보율을 "
            "그래프·계산표·고른 달 계산에 함께 둡니다."
        ),
    )
    month = _viewed_month(result)
    generation_value = st.session_state.get(CONSTRAINT_SELECT_GENERATION_KEY, 0)
    generation = generation_value if isinstance(generation_value, int) else 0
    chart, sheet = remembered_figures(
        view, month=month, show_proportional=bool(show_proportional), generation=generation
    )
    # 그래프와 고른 달 계산을 한 줄에(달을 누르면 바로 옆이 바뀐다 — 좁으면 위아래). 계산표는 그
    # 아래 온 폭이다 — 계산표의 두 컬럼 폭 규칙(`split_scroll_columns_style`, `:has()` 선택자)이
    # 바깥 컬럼에도 걸리므로 컬럼 안에 넣지 않는다(2026-10-25 브라우저 — 바깥 왼쪽 컬럼이 260px 로
    # 눌렸다).
    st.html(top_row_style(len(months)))
    with st.container(horizontal=True, gap="medium", key=TOP_ROW_KEY):
        with st.container(border=True, key=CHART_CARD_KEY):
            st.markdown("**월별 확보율**")
            above = rate_axis(
                result, view.labels, show_proportional=bool(show_proportional)
            ).above_months
            st.caption(
                "달 칸을 누르면 그 달의 계산이 나옵니다 · 옅은 칠 = 제약 기간"
                + (
                    f" · {ABOVE_MARK} = 그래프 위로 넘친 제약 제품 확보율(값은 풍선)"
                    if above
                    else ""
                )
            )
            # 좁은 카드에서는 이 상자 안에서 가로로 스크롤한다(`top_row_style`). 그림 위 터치
            # 스와이프는 `app.py` 의 터치 스크롤 막이가 브라우저 스크롤로 넘긴다.
            with min_width_scroll_canvas(key=CHART_SCROLL_PREFIX):
                st.plotly_chart(
                    chart,
                    width="stretch",
                    key=CONSTRAINT_CHART_KEY,
                    config=hover_chart_config(),
                    on_select=partial(pick_chart_month, months),
                    selection_mode="points",
                )
        _render_month_steps(view, month, show_proportional=bool(show_proportional))
    with st.container(border=True):
        st.markdown("**월별 계산표**")
        st.caption(
            "칸을 누르면 그 달을 고릅니다 · 머리 옅은 칠 = 제약 기간 · 부족색 칸 = 기준(제약 칸은 "
            "제약 목표)에 못 미침 · 파란 글자 = 줄어든 값 · 대수는 환산 대수"
        )
        _render_sheet(sheet, months)
    schedule_column, shortage_column = st.columns(2, gap="medium")
    with schedule_column:
        _render_schedule(view)
    with shortage_column:
        # 가용이 모자란 달 — 있을 때만 서는 알림이라 늘 서 있는 칸 안에 그린다.
        with st.container():
            shortage = short_lines(result)
            shortage_months = short_month_lines(result)
            overdrawn = overdrawn_lines(result)
            if shortage or overdrawn:
                with st.container(border=True):
                    st.markdown("**가용이 모자란 달**")
                    if shortage:
                        st.caption(shortage)
                    if shortage_months:
                        with st.expander("달마다 보기", key=SHORT_MONTHS_EXPANDER_KEY):
                            st.caption("  \n".join(shortage_months))
                    for line in overdrawn:
                        st.caption(f":material/warning: {line}")


def top_row_style(month_count: int) -> str:
    """위 줄 배치 CSS — 넓으면 그래프 카드 3 : 계산 카드 2, 줄이 `TOP_ROW_STACK_BELOW_PX` 보다
    좁으면 두 카드 모두 한 줄씩(위아래). 그래프는 달 수만큼의 가장 좁은 폭을 받고 카드가 그보다
    좁으면 스크롤 상자 안에서 가로로 민다.

    가로 컨테이너의 flex 항목은 키 붙은 칸이 아니라 그것을 한 번 감싼 `stLayoutWrapper` 다(1.63 —
    `qual_deadline_calculator.layout_style` 와 같은 꼴). 컨테이너 질의라 사이드바를 여닫아 본문 폭만
    바뀌어도 따라간다. 그래프 캔버스는 폭을 고정하지 않고(`width="stretch"` 가 카드를 채운다) 가장
    좁은 폭만 건다 — 넓은 창의 그림은 그대로다.
    """
    chart = f'[data-testid="stLayoutWrapper"]:has(> .st-key-{CHART_CARD_KEY})'
    steps = f'[data-testid="stLayoutWrapper"]:has(> .st-key-{STEPS_CARD_KEY})'
    return "\n".join(
        [
            "<style>",
            f".st-key-{TOP_ROW_KEY} {{ container: {_TOP_ROW_CONTAINER_NAME} / inline-size; }}",
            f"{chart} {{ flex: 3 1 0 !important; min-width: 0 !important; }}",
            f"{steps} {{ flex: 2 1 0 !important; min-width: 0 !important; }}",
            f"@container {_TOP_ROW_CONTAINER_NAME} (width < {TOP_ROW_STACK_BELOW_PX}px) {{",
            f"  {chart}, {steps} {{ flex: 1 1 100% !important; }}",
            "}",
            min_width_scroll_rules(
                CHART_SCROLL_PREFIX, min_width_px=chart_min_width_px(month_count)
            ),
            "</style>",
        ]
    )


def _render_sheet(sheet: SheetCanvas, months: tuple[int, ...]) -> None:
    """라벨 칸 260px + 월 칸(스크롤 상자 하나, 위에 가로 스크롤바) — 공정 Capa 상세와 같은 틀."""
    count = len(months)
    visible = min(max(count, 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)
    st.html(
        split_scroll_columns_style(
            label_key=_SHEET_LABEL_CANVAS_KEY,
            month_key=_SHEET_MONTH_REGION_KEY,
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
            narrow_label_width_px=NARROW_LABEL_COLUMN_WIDTH_PX,
            narrow_viewport_max_px=NARROW_VIEWPORT_MAX_PX,
        )
    )
    label_column, month_column = st.columns(
        [DASHBOARD_LABEL_COLUMN_WIDTH_PX, visible * tokens.MONTH_COLUMN_WIDTH_PX], gap=None
    )
    with label_column:
        with st.container(key=_SHEET_LABEL_CANVAS_KEY, gap=None):
            st.plotly_chart(
                sheet.labels,
                width="stretch",
                key=_SHEET_LABEL_CHART_KEY,
                config=static_chart_config(),
            )
    with month_column:
        st.html(
            f"<style>.st-key-{_SHEET_LABEL_CANVAS_KEY} "
            f"{{ padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px; }}</style>"
        )
        with st.container(key=_SHEET_MONTH_REGION_KEY, gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{_SHEET_SCROLL_KEY}_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key=_SHEET_SCROLLBAR_KEY,
            )
            with horizontal_scroll_canvas(
                key=_SHEET_SCROLL_KEY,
                content_width_px=count * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=None,
            ):
                # 선택을 켜면 그림 위 터치 스크롤이 막히므로 이 key 는 `app.py` 의 터치 스크롤 막이
                # 묶음에 들어 있다.
                st.plotly_chart(
                    sheet.months,
                    width="stretch",
                    key=CONSTRAINT_SHEET_KEY,
                    config=hover_chart_config(),
                    on_select=partial(pick_sheet_month, months),
                    selection_mode="points",
                )


def _render_month_steps(view: ConstraintView, month: int, *, show_proportional: bool) -> None:
    row = view.result.month(month)
    steps = month_steps(row, view.result, view.labels, show_proportional=show_proportional)
    with st.container(border=True, key=STEPS_CARD_KEY):
        st.markdown(f"**{steps.title}**")
        for number, step in enumerate(steps.steps, start=1):
            st.markdown(f"**{number}** · {step.body}")
            if step.note:
                st.caption(step.note)
        # 결과 상자는 확보율이 있을 때만 선다 — 늘 서 있는 칸 안에 그린다.
        with st.container():
            if steps.verdict:
                if steps.verdict_secure:
                    st.success(steps.verdict, icon=":material/check_circle:")
                else:
                    st.warning(steps.verdict, icon=":material/warning:")
            if steps.proportional:
                st.caption(steps.proportional)


def _render_schedule(view: ConstraintView) -> None:
    result = view.result
    with st.container(border=True, key=SCHEDULE_CARD_KEY):
        st.markdown("**개조 일정**")
        with st.container():
            free_line = free_units_line(result)
            if free_line:
                st.caption(free_line)
            if not result.conditions.modifies:
                st.caption(MODIFY_OFF_TEXT)
            elif not result.windows:
                freed = result.kpis.owned_used + result.kpis.new_used
                st.caption(FREE_ONLY_TEXT if free_line and freed > 0 else NO_WINDOWS_TEXT)
            stopped_line = new_stopped_line(result)
            if stopped_line:
                st.caption(stopped_line)
            for line in schedule_lines(result.windows, today=view.today):
                st.markdown(line)
            if result.starts_before_range:
                st.caption(f":material/info: {BEFORE_RANGE_TEXT}")
            if result.assignments:
                st.caption("**신규 대기** — 셋업 때부터 제약용으로 붙인 신규 설비")
                for line in waiting_lines(result.assignments, today=view.today):
                    st.markdown(line)
                if result.waits_before_range:
                    st.caption(f":material/info: {WAIT_BEFORE_RANGE_TEXT}")
            ordinary = ordinary_line(result)
            if ordinary:
                st.caption(ordinary)
        st.caption(SCHEDULE_DEFINITION)
        if result.conditions.uses_new_units:
            st.caption(WAITING_DEFINITION)
