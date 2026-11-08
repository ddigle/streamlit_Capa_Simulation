# Purpose: 제약 시뮬레이션 본문(보기 전환·월별 그래프·계산표·모자란 달)과 요약 넷을 그린다.

"""제약 시뮬레이션 — 본문 프래그먼트(`constraint_sim_view`)와 그 둘레(요약 넷).

페이지(`app_pages/constraint_simulation.py`)가 앱 전체 회차에서 조건·계획·계산을 모두 정해
`ConstraintView` 하나로 넘기면, 여기서는 **고른 달과 비중 토글**에 닿는 것만 그린다 — 달 누름(그래프
칸· 계산표 칸)과 비중 토글은 카드에 설 위젯을 바꾸지 않는 본문 조작이라 이 프래그먼트만 다시
돈다(AGENTS 9장 「본문 프래그먼트」). 프래그먼트 회차는 직전 앱 전체 회차의 인자(계산 결과·화면
글자)를 쓴다.

- **보기 줄** — 「소요 비중대로 나눴을 때 함께 보기」 토글(`persist_state="session"` — 보기 조건).
- **월별 확보율 그래프**(`CONSTRAINT_CHART_KEY`) — 온 폭 카드. 그래프는 가장 좁은
  폭(`chart_min_width_px`)을 받고 카드가 그보다 좁으면(390px 창) 카드 안에서 가로로 스크롤한다 —
  세운 달 눈금 30개가 포개지지 않게(`chart_style`).
- **월별 계산표** — 그 아래 온 폭(라벨 Figure + 가로로 스크롤되는 월 Figure `CONSTRAINT_SHEET_KEY`).
  계산표는 컬럼 안에 넣지 않는다 — 두 컬럼 폭 규칙(`split_scroll_columns_style` 의 `:has()`)이
  바깥 컬럼에도 걸린다. 칸 색 · 글자색 · 머리 칠의 읽는 법은 Guide 이고(2026-11-08 사용자 그림 메모
  g12), 표 앞에서 시작하는 개조 · 대기만 칸 머리 표지 + 풍선이다.
- **달 고르기** — 칸을 누르면 `on_select` **콜백**이 고른 달을 적고 그래프의 띠와 계산표의 열
  테두리가 그 달을 짚는다 — 회차마다 두 그림의 선택 상태를 읽으면 브라우저에 남은 다른 그림의 옛
  선택이 마지막 누름을 덮는다. 세대 번호는 두 그림이 한 칸을 나눠 써 누를 때마다 둘 다 새 요소가
  된다(AGENTS 9장 「칸 선택 Plotly」). 고른 달의 계산 풀이 카드와 「이 조건의 개조 창」 카드는
  걷었다(2026-11-08 사용자 그림 메모 g12) — 식은 계산표 칸 풍선, 개조 창은 그래프 아래 띠 · 막대
  풍선 · 계산표 「개조」 구획, 읽는 법은 Guide 다.
- **맨 아래** — 가용이 모자란 달. 생겼다 사라지는 알림은 늘 서 있는 `st.container()` 칸 안에
  그린다(AGENTS 9장 「자리는 고정한다」).

**이벤트 칸 수는 갈래마다 같다** — 이 프래그먼트가 이벤트 칸에 쓰는 것은 스타일만 든 `st.html`
넷(그래프 가장 좁은 폭 · 계산표 두 컬럼 폭 · 라벨 칸 위 여백 · 스크롤 상자 — 뒤 셋은 공정 Capa
상세와 같은 틀)이고 어느 갈래(비중 켬·끔, 개조 켬·끔, 고른 달)에서도 넷 그대로다.

그림은 세션에 몇 벌 기억한다(`remembered_figures`, 공정 Capa 상세 `remembered_canvas` 꼴 — Streamlit
캐시가 아니다). 키는 그림 모양 버전·테마·계산 결과(값으로 같다)·화면 글자·고른 달·비중 토글·세대다.

요약 넷(`render_constraint_kpis`)은 고른 달·보기와 무관해 프래그먼트 밖에서 페이지가 그린다. 보유
제약 설비·「신규 설비는 개조 없이」 가 걸리면(`ConstraintConditions.splits_dedicated`) 「개조 대수」
값은 실제로 개조하는 대수, 회색 줄은 전용 최대의 구성(`FILL_ORDER` 차례 — 지금 「신규 · 보유 ·
개조」)이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Final, NamedTuple

import plotly.graph_objects as go
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.constraint_simulation_figures import (
    ABOVE_MARK,
    CONSTRAINT_FIGURE_SCHEMA_VERSION,
    ConstraintLabels,
    SheetCanvas,
    build_sheet_canvas,
    chart_min_width_px,
    chart_point_month,
    free_parts,
    general_label,
    rate_axis,
    rate_figure,
    rate_text,
    units_text,
)
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    NARROW_LABEL_COLUMN_WIDTH_PX,
    NARROW_VIEWPORT_MAX_PX,
)
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
from capa_simulation.services.constraint_simulation import ConstraintMonth, ConstraintResult
from capa_simulation.services.month_columns import month_label
from capa_simulation.sidebar_status import rerun_app_unless_alone

__all__ = [
    "BEFORE_RANGE_MARK",
    "CHART_CARD_KEY",
    "CHART_HELP",
    "KPI_ROW_KEY",
    "SHEET_HELP",
    "SHORT_INLINE_LIMIT",
    "SHORT_MONTHS_EXPANDER_KEY",
    "SHORT_REASON_TEXT",
    "WAIT_BEFORE_RANGE_MARK",
    "ConstraintView",
    "chart_style",
    "default_month",
    "overdrawn_lines",
    "pick_chart_month",
    "pick_sheet_month",
    "remembered_figures",
    "render_constraint_kpis",
    "render_constraint_view",
    "settle_selected_month",
    "short_lines",
    "short_month_lines",
]

KPI_ROW_KEY: Final = "constraint_sim_kpis"
_FIGURE_MEMO_LIMIT: Final = 4
_SHEET_LABEL_CANVAS_KEY: Final = "constraint_sim_sheet_label_canvas"
_SHEET_LABEL_CHART_KEY: Final = "constraint_sim_sheet_labels"
_SHEET_MONTH_REGION_KEY: Final = "constraint_sim_sheet_month_region"
_SHEET_SCROLL_KEY: Final = "constraint_sim_sheet"
_SHEET_SCROLLBAR_KEY: Final = "constraint_sim_sheet_scrollbar"
CHART_CARD_KEY: Final = "constraint_sim_chart_card"
# 그래프 카드 안의 가로 스크롤 상자(`{접두}_scroll`)와 그 안 캔버스(`{접두}_canvas` — 가장 좁은 폭
# `chart_min_width_px`). `scroll_shell.min_width_scroll_canvas` 가 이 접두로 key 를 붙인다.
CHART_SCROLL_PREFIX: Final = "constraint_sim_chart"
_EMPTY: Final = "—"
# 그래프 · 계산표를 누르는 법은 제목 풍선이다 — 범례만 자리에 둔다(설계 규칙 UI-TXT-01). 누른 달은
# 그래프의 띠와 계산표의 열 테두리로 함께 짚는다.
CHART_HELP: Final = "달 칸을 누르면 계산표에서도 그 달을 짚습니다."
SHEET_HELP: Final = "칸을 누르면 그래프에서도 그 달을 짚습니다."
# 표 앞에서 시작하는 개조 · 대기 — 숨은 데이터라 표지 + 풍선이다(설계 규칙 UI-TXT-04).
BEFORE_RANGE_MARK: Final = ":material/info: 첫 개조 비가동 — 표 첫 달 앞에서 시작"
BEFORE_RANGE_TEXT: Final = (
    "첫 개조 비가동이 표의 첫 달보다 앞에서 시작합니다 — 그 앞 달의 감소는 표에 없습니다."
)
WAIT_BEFORE_RANGE_MARK: Final = ":material/info: 첫 신규 대기 — 표 첫 달 앞에서 시작"
WAIT_BEFORE_RANGE_TEXT: Final = (
    "첫 신규 대기가 표의 첫 달보다 앞에서 시작합니다 — 그 앞 달의 감소는 표에 없습니다."
)
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
    for index, (stored_key, stored) in enumerate(entries):
        if stored_key == key:
            # 꺼낸 벌을 맨 뒤로 — 마지막 벌이 늘 지금 보이는 그림이다(오래 안 쓴 벌부터 버린다).
            if index != len(entries) - 1:
                st.session_state[CONSTRAINT_FIGURE_MEMO_KEY] = [
                    *entries[:index],
                    *entries[index + 1 :],
                    (stored_key, stored),
                ]
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


def _short_month_text(row: ConstraintMonth) -> str:
    """모자란 달 하나 — 「27.06: 전용 6대 중 5대만 배정」. 값은 그 달 필요(need)가 아니라 떼어 줄
    전용 대수(dedicated)다 — 소요가 0 인 달도 이미 개조한 전용을 유지한다."""
    return f"{month_label(row.month)}: 전용 {row.dedicated}대 중 {row.allocated}대만 배정"


def short_lines(result: ConstraintResult) -> str:
    """가용이 모자란 달 한 줄(값). 없으면 빈 글자. 까닭(`SHORT_REASON_TEXT`)은 구획 제목 풍선이다.

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
    return head


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
        f"{units_text(row.available)}대보다 많습니다 — 이 공정 설비로는 이 개조 창이 "
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
            # 한 줄 알약이라 카드 넷이 한 줄에 서게 짧게 둔다 — 창 수·첫 비가동은 개조 창 카드가
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
    """보기 줄 → 월별 확보율 그래프(온 폭) → 월별 계산표(온 폭) → 가용이 모자란 달(있을 때만)."""
    result = view.result
    months = tuple(row.month for row in result.months)
    seed_toggle(CONSTRAINT_PROPORTIONAL_KEY, DEFAULT_PROPORTIONAL)
    show_proportional = st.toggle(
        "소요 비중대로 나눴을 때 함께 보기",
        key=CONSTRAINT_PROPORTIONAL_KEY,
        persist_state="session",
        help=(
            "개조 비가동 없이 가용을 소요 비중대로 정수(사사오입)로 나눴을 때의 기존 제품 확보율을 "
            "그래프·계산표에 함께 둡니다."
        ),
    )
    month = _viewed_month(result)
    generation_value = st.session_state.get(CONSTRAINT_SELECT_GENERATION_KEY, 0)
    generation = generation_value if isinstance(generation_value, int) else 0
    chart, sheet = remembered_figures(
        view, month=month, show_proportional=bool(show_proportional), generation=generation
    )
    st.html(chart_style(len(months)))
    with st.container(border=True, key=CHART_CARD_KEY):
        st.markdown("**월별 확보율**", help=CHART_HELP)
        above = rate_axis(
            result, view.labels, show_proportional=bool(show_proportional)
        ).above_months
        st.caption(
            "옅은 칠 = 제약 기간"
            + (f" · {ABOVE_MARK} = 그래프 위로 넘친 제약 제품 확보율(값은 풍선)" if above else "")
        )
        # 좁은 카드에서는 이 상자 안에서 가로로 스크롤한다(`chart_style`). 그림 위 터치 스와이프는
        # `app.py` 의 터치 스크롤 막이가 브라우저 스크롤로 넘긴다.
        with min_width_scroll_canvas(key=CHART_SCROLL_PREFIX):
            st.plotly_chart(
                chart,
                width="stretch",
                key=CONSTRAINT_CHART_KEY,
                config=hover_chart_config(),
                on_select=partial(pick_chart_month, months),
                selection_mode="points",
            )
    with st.container(border=True):
        # 칸 색 · 글자색 · 머리 칠의 읽는 법은 Guide 다(2026-11-08 사용자 그림 메모 g12).
        st.markdown("**월별 계산표**", help=SHEET_HELP)
        # 표 앞에서 시작하는 개조 · 대기 — 표에 보이지 않는 감소라 칸 머리 표지 + 풍선이다(설계 규칙
        # UI-TXT-04). 있을 때만 서는 표지라 늘 서 있는 칸 안에 그린다.
        with st.container():
            if result.starts_before_range:
                st.caption(BEFORE_RANGE_MARK, help=BEFORE_RANGE_TEXT)
            if result.waits_before_range:
                st.caption(WAIT_BEFORE_RANGE_MARK, help=WAIT_BEFORE_RANGE_TEXT)
        _render_sheet(sheet, months)
    # 가용이 모자란 달 — 있을 때만 서는 알림이라 늘 서 있는 칸 안에 그린다.
    with st.container():
        shortage = short_lines(result)
        shortage_months = short_month_lines(result)
        overdrawn = overdrawn_lines(result)
        if shortage or overdrawn:
            with st.container(border=True):
                st.markdown("**가용이 모자란 달**", help=SHORT_REASON_TEXT)
                if shortage:
                    st.caption(shortage)
                if shortage_months:
                    with st.expander("달마다 보기", key=SHORT_MONTHS_EXPANDER_KEY):
                        st.caption("  \n".join(shortage_months))
                for line in overdrawn:
                    st.caption(f":material/warning: {line}")


def chart_style(month_count: int) -> str:
    """그래프 카드 서식 — 그래프는 달 수만큼의 가장 좁은 폭을 받고 카드가 그보다 좁으면 스크롤 상자
    안에서 가로로 민다. 그래프 캔버스는 폭을 고정하지 않고(`width="stretch"` 가 카드를 채운다) 가장
    좁은 폭만 건다 — 넓은 창의 그림은 그대로다."""
    return (
        "<style>"
        + min_width_scroll_rules(CHART_SCROLL_PREFIX, min_width_px=chart_min_width_px(month_count))
        + "</style>"
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
