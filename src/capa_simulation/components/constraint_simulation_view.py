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
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from functools import partial
from typing import Final, NamedTuple

import plotly.graph_objects as go
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.constraint_simulation_figures import (
    CONSTRAINT_FIGURE_SCHEMA_VERSION,
    ConstraintLabels,
    SheetCanvas,
    build_sheet_canvas,
    chart_min_width_px,
    chart_point_month,
    general_label,
    month_name,
    rate_figure,
    rate_text,
    signed_points,
    units_text,
)
from capa_simulation.components.formula_text import consistent_digits, operand_text
from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.literal_markdown import literal_markdown
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
    CONSTRAINT_PROPORTIONAL_KEY,
    CONSTRAINT_SELECT_GENERATION_KEY,
    CONSTRAINT_SHEET_KEY,
    CONSTRAINT_VIEW_FRAGMENT_KEY,
    DEFAULT_PROPORTIONAL,
    seed_toggle,
)
from capa_simulation.design import theme, tokens
from capa_simulation.services.constraint_simulation import (
    ConstraintMonth,
    ConstraintResult,
    ModificationWindow,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.threshold_label import threshold_percent_label
from capa_simulation.sidebar_status import rerun_app_unless_alone

__all__ = [
    "KPI_ROW_KEY",
    "SCHEDULE_CARD_KEY",
    "STEPS_CARD_KEY",
    "ConstraintView",
    "MonthStep",
    "MonthSteps",
    "default_month",
    "month_steps",
    "overdrawn_lines",
    "pick_chart_month",
    "pick_sheet_month",
    "remembered_figures",
    "render_constraint_kpis",
    "render_constraint_view",
    "schedule_lines",
    "settle_selected_month",
    "short_lines",
    "top_row_style",
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
MODIFY_OFF_TEXT: Final = "개조를 켜면 제약 제품에 떼어 줄 대수만큼 개조 비가동이 잡힙니다."
BEFORE_RANGE_TEXT: Final = (
    "첫 개조 비가동이 표의 첫 달보다 앞에서 시작합니다 — 그 앞 달의 감소는 표에 없습니다."
)
LATE_SUFFIX: Final = " — 이미 지난 날짜(개조를 이미 시작했어야 합니다)"


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
    """앱 전체 회차마다 고른 달 칸을 잡는다 — 보이는 달 밖이거나 없으면 기본 달을 **적는다**."""
    months = {row.month for row in result.months}
    held = st.session_state.get(CONSTRAINT_MONTH_KEY)
    if isinstance(held, int) and not isinstance(held, bool) and held in months:
        return held
    chosen = default_month(result)
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
    자리(`units_text`)로 적고, 깎은 인수로 어긋날 때만 그 식의 인수를 한 자리씩 더 적는다
    (`formula_text.consistent_digits`·`operand_text` — 「0.02 × 120% = 0.03」 이 아니라
    「0.021 × 120% = 0.03」). 어느 자릿수로도 못 맞추면 둘째 자리와 「≈」 다."""
    product = literal_markdown(labels.product)
    process = literal_markdown(labels.process_label)
    modifies = result.conditions.modifies
    target = labels.target_percent

    title = f"{month_label(row.month)} · {process}" + (" · 제약 기간" if row.in_period else "")
    required_shown = units_text(row.required)
    split_digits, split_sign = consistent_digits(
        lambda digits: units_text(
            round(row.existing_demand, digits) + round(row.constrained_demand, digits)
        ),
        required_shown,
    )
    step1 = MonthStep(
        f"소요 **{required_shown}대** {split_sign} 기존 "
        f"{operand_text(row.existing_demand, split_digits, units_text)} + "
        f"{product} {operand_text(row.constrained_demand, split_digits, units_text)}",
        "제약 기간이라 공정 소요를 두 갈래로 나눕니다(합하면 원래 소요와 같습니다)."
        if row.in_period
        else f"제약 기간 밖이라 {product} 도 기존 제품에 함께 셉니다.",
    )

    if row.in_period and row.constrained_demand > 0:
        product_text = f"{row.constrained_demand * target / 100:.2f}"
        demand_digits, demand_sign = consistent_digits(
            lambda digits: f"{round(row.constrained_demand, digits) * target / 100:.2f}",
            product_text,
        )
        demand_text = operand_text(row.constrained_demand, demand_digits, units_text)
        body2 = (
            f"{product} 필요 대수 = {demand_text} × {target}% {demand_sign} {product_text} → "
            f"**{row.need}대**"
        )
    elif row.in_period and row.dedicated > 0:
        body2 = f"{product} 소요 없음 — 전용 **{row.dedicated}대** 유지"
    else:
        body2 = "제약 제품에 따로 떼는 대수 없음"
    if row.in_period and modifies and row.dedicated > row.need:
        note2 = f"이미 개조한 {row.dedicated}대는 전용으로 남습니다(줄여도 되돌리지 않음)."
    elif row.in_period and row.constrained_demand > 0:
        note2 = "제약 확보율을 먼저 맞추도록 정수로 올립니다."
    else:
        note2 = ""
    step2 = MonthStep(body2, note2)

    if not modifies:
        step3 = MonthStep("개조 없음 — 비가동 없이 나누기만 합니다", "")
    else:
        body3 = (
            f"개조 중 비가동 **−{units_text(row.downtime)}대**"
            if row.downtime > 0
            else "이 달 개조 비가동 없음"
        )
        notes = [
            f"{month_name(share.source_month)} 몫 {share.units}대가 이 달 {share.days}일 개조 중 "
            f"→ {units_text(share.equivalent)}대"
            for share in row.downtime_shares
        ]
        if not notes and row.increment > 0:
            notes.append(f"이 달 몫 {row.increment}대는 앞 달에 개조를 마칩니다.")
        if row.overdrawn:
            notes.append("비가동이 가용보다 많아 쓸 수 있는 가용은 0 입니다.")
        step3 = MonthStep(body3, " · ".join(notes))

    available_shown = units_text(row.existing_available)
    # 적힌 수로 「공정 가용 − 개조 중 − 제약 배정」 을 다시 셈한다 — 비가동이 가용보다 많으면 쓸 수
    # 있는 가용을 0 으로 두는 것까지 서비스(`simulate_constraint`)와 같은 차례다.
    available_digits, available_sign = consistent_digits(
        lambda digits: units_text(
            max(0.0, round(row.available, digits) - round(row.downtime, digits)) - row.allocated
        ),
        available_shown,
    )
    pieces = [operand_text(row.available, available_digits, units_text)]
    note_pieces = ["공정 가용"]
    if row.downtime > 0:
        pieces.append(operand_text(row.downtime, available_digits, units_text))
        note_pieces.append("개조 중")
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
        if len(pieces) > 1
        else f"기존 가용 = 공정 가용 **{available_shown}대**"
    )
    step4 = MonthStep(body4, note4)

    if row.existing_rate is None:
        step5 = MonthStep("기존 제품 소요가 없어 기존 확보율이 없습니다", "")
    else:
        note5 = f"제약 없을 때 {rate_text(row.baseline_rate)}"
        if row.baseline_rate is not None:
            note5 += f" · {signed_points(row.existing_rate - row.baseline_rate)}"
        rate_shown = rate_text(row.existing_rate)

        def recomputed(digits: int) -> str:
            demand = round(row.existing_demand, digits)
            return rate_text(round(row.existing_available, digits) / demand) if demand else ""

        rate_digits, rate_sign = consistent_digits(recomputed, rate_shown)
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
            f"기존 제품이 기준 {general_text} 를 지킵니다"
            if row.existing_secure
            else f"기존 제품이 기준 {general_text} 에 못 미칩니다"
        )
        if row.constrained_rate is not None:
            met = "충족" if row.met else "미달"
            verdict += f" · 제약 제품 {rate_text(row.constrained_rate)} (제약 {target}% {met})"

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


def short_lines(result: ConstraintResult) -> str:
    """가용이 모자란 달 한 줄. 없으면 빈 글자."""
    rows = [row for row in result.months if row.short]
    if not rows:
        return ""
    parts = " · ".join(
        f"{month_label(row.month)}: 필요 {row.dedicated}대 중 {row.allocated}대만 배정"
        for row in rows
    )
    return f"{parts} — 제약 제품을 먼저 채우고 남는 것이 없어 기존 제품이 0 에 가깝습니다."


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

        if kpis.max_dedicated is None:
            value4, caption4 = _EMPTY, "개조를 끄면 비가동 없이 배정만 바꿉니다"
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
            st.caption("달 칸을 누르면 그 달의 계산이 나옵니다 · 옅은 칠 = 제약 기간")
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
            overdrawn = overdrawn_lines(result)
            if shortage or overdrawn:
                with st.container(border=True):
                    st.markdown("**가용이 모자란 달**")
                    if shortage:
                        st.caption(shortage)
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
            if not result.conditions.modifies:
                st.caption(MODIFY_OFF_TEXT)
            elif not result.windows:
                st.caption(NO_WINDOWS_TEXT)
            for line in schedule_lines(result.windows, today=view.today):
                st.markdown(line)
            if result.starts_before_range:
                st.caption(f":material/info: {BEFORE_RANGE_TEXT}")
        st.caption(SCHEDULE_DEFINITION)
