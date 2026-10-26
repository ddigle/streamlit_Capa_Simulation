# Purpose: 제약 시뮬레이션 「개조 일정」 모드의 모드 전환·조건 카드·설비 일정 확인·계산과 본문(요약
# 넷· 그래프·차수·대안)을 그린다.

"""개조 일정 모드 — 「N대 × D일 개조를 기준 확보율을 지키며 언제 할까」(2026-10-26 사용자 결정 3).

제약 시뮬레이션 화면(`app_pages/constraint_simulation.py`)의 둘째 모드다. 페이지는 공통 진입(판정
기준·시나리오 키·달·공정 선택지)과 설비 세션까지만 내고 모드 전환(`render_mode_switch` — 본문 맨 위
`segmented_control`)이 「개조 일정」 이면 `render_schedule_mode` 하나를 부른 뒤 멈춘다. 그 뒤는 모두
여기다 — 제약 모드의 카드·본문은 그리지 않는다(1판은 두 모드를 함께 쓰지 않는다, C14).

- **모드 전환은 본문이다**(하위 보기 전환 규칙). 다만 카드에 무엇이 설지를 바꾸므로 프래그먼트가
  아닌 앱 전체 회차로 돈다(AGENTS 9장 「본문 프래그먼트」).
- **조건 카드**(제약 모드와 같은 카드 이름·자리) — 대상(공정 — 제약 모드와 같은 칸) / 이 세션만 /
  개조(대수 · 기간 버튼 + 직접 · 동시 상한 버튼 + 직접) / 일정(시작 · 기한 · 달 맞춤 창) / 기준(기준
  확보율 — 제약 모드와 **한 정본** · 안전 여유 %p · 목적) / Cut-off 읽기만.
- **계획** — 공정 Capa 상세 ②·제약 모드와 같은 칸을 **같은 키**로 받는다(`_plan` — 페이지의 계획
  블록과 같은 인자 차례). 계산 함수는 부를 때 `simulation_cache` 모듈에서 찾는다(페이지 시험이 그
  속성을 바꾼다).
- **계산** — 순수 서비스 `services/modification_schedule.py`. 「가장 고르게」 는 이분 탐색이라 수백
  ms 까지 가므로 결과를 조건 값으로 세션에 몇 벌 기억한다(`remembered_result` — Streamlit 캐시가
  아니다, CLAUDE.md 캐시 경계). 그림도 같다(`remembered_figure` — 테마가 키에 든다).
- **본문** — 머리 한 줄 · 「저장하지 않음」 · 출처 띠 · 「아직 일정에 넣지 않은 개조만」 → 요약 넷 →
  (못 맞추면) 대안 셋 → 월별 확보율 그래프(개조 전·뒤 · 기준선 · 차수 막대) → 개조 일정(차수 목록).

저장하지 않는다 — 조건은 세션 칸뿐이고 어느 DB 에도 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Final, NamedTuple, Protocol

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

# 이름이 아니라 모듈을 잡는다 — 페이지 시험이 계획 함수를 바꿔 끼운다.
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.constraint_simulation_figures import (
    chart_min_width_px,
    rate_text,
    signed_points,
)
from capa_simulation.components.equipment_scenario_status import equipment_basis_label
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.modification_schedule_figures import (
    SCHEDULE_FIGURE_SCHEMA_VERSION,
    ScheduleLabels,
    batch_line,
    general_text,
    relief_text,
    schedule_figure,
    shortfall_lines,
)
from capa_simulation.components.plotly_layout import hover_chart_config
from capa_simulation.components.preset_number_field import render_preset_number_field
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.scroll_shell import (
    min_width_scroll_canvas,
    min_width_scroll_rules,
)
from capa_simulation.components.status_metric import (
    MetricTone,
    metric_row,
    render_status_metric,
)
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_GENERAL_INPUT_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
    CONSTRAINT_PROCESS_KEY,
    GENERAL_PRESETS,
    MOD_DAY_PRESETS,
    seed_toggle,
)
from capa_simulation.design import theme
from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.modification_schedule_state import (
    CONCURRENT_PRESETS,
    CONSTRAINT_MODE,
    CONSTRAINT_MODE_KEY,
    DEFAULT_CONCURRENT,
    DEFAULT_MARGIN_POINTS,
    DEFAULT_SCHEDULE_DAYS,
    MARGIN_PRESETS,
    MODE_LABELS,
    MODES,
    NO_CHOICE,
    OBJECTIVE_LABELS,
    SCHEDULE_ALIGNED_KEY,
    SCHEDULE_CHART_KEY,
    SCHEDULE_CONCURRENT_INPUT_KEY,
    SCHEDULE_CONCURRENT_KEY,
    SCHEDULE_CONCURRENT_PILLS_KEY,
    SCHEDULE_DAYS_INPUT_KEY,
    SCHEDULE_DAYS_KEY,
    SCHEDULE_DAYS_PILLS_KEY,
    SCHEDULE_DEADLINE_KEY,
    SCHEDULE_FIGURE_MEMO_KEY,
    SCHEDULE_MARGIN_INPUT_KEY,
    SCHEDULE_MARGIN_KEY,
    SCHEDULE_MARGIN_PILLS_KEY,
    SCHEDULE_OBJECTIVE_KEY,
    SCHEDULE_RESULT_MEMO_KEY,
    SCHEDULE_START_KEY,
    SCHEDULE_UNITS_KEY,
    settle_choice,
    settle_mode,
    settle_objective,
    settle_units,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    ProcessPageInputs,
    bootstrap_error_message,
)
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.scenario_activation import active_scenario_label
from capa_simulation.services.constraint_simulation import (
    GENERAL_INPUT_RANGE,
    MODIFICATION_DAYS_RANGE,
)
from capa_simulation.services.modification_schedule import (
    CONCURRENT_RANGE,
    MARGIN_RANGE,
    UNITS_RANGE,
    Objective,
    ScheduleConditions,
    ScheduleMonth,
    ScheduleMonthInput,
    ScheduleResult,
    plan_modification_schedule,
    schedule_month_inputs,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_equipment_timeline import (
    DynamicReadiness,
    dynamic_readiness,
)
from capa_simulation.services.required_shortening import (
    MonthlyTarget,
    ShorteningPlan,
    target_from_thresholds,
)
from capa_simulation.services.securement_threshold import (
    securement_threshold_caption,
)
from capa_simulation.services.wd_window import wd_window
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_DEFAULT_PERCENT,
    UPEH_ASSUMPTION_PERCENT_KEY,
)

__all__ = [
    "CHART_CARD_KEY",
    "DOUBLE_COUNT_NOTE",
    "KPI_ROW_KEY",
    "LIST_CARD_KEY",
    "FELL_BACK_LABEL",
    "SHORTFALL_CARD_KEY",
    "UNITS_HELP",
    "ReasonCard",
    "ScheduleChoice",
    "ScheduleModeContext",
    "deadline_day",
    "deadline_options",
    "earliest_day",
    "remembered_figure",
    "remembered_result",
    "render_mode_switch",
    "render_schedule_kpis",
    "render_schedule_mode",
    "start_options",
]

KPI_ROW_KEY: Final = "constraint_sim_sched_kpis"
CHART_CARD_KEY: Final = "constraint_sim_sched_chart_card"
# 그래프 카드 안 가로 스크롤 상자(`{접두}_scroll`)와 캔버스(`{접두}_canvas`) — 제약 모드 그래프와
# 같은 가장 좁은 폭(`chart_min_width_px`)을 받는다.
CHART_SCROLL_PREFIX: Final = "constraint_sim_sched_chart_box"
LIST_CARD_KEY: Final = "constraint_sim_sched_list"
SHORTFALL_CARD_KEY: Final = "constraint_sim_sched_shortfall"
_MEMO_LIMIT: Final = 4
# 결과 모양(서비스 dataclass)을 바꾸면 올린다 — 세션 memo 의 옛 결과를 쓰지 않게.
_RESULT_SCHEMA_VERSION: Final = 2
_EMPTY: Final = "—"

DOUBLE_COUNT_NOTE: Final = (
    ":material/info: **아직 일정에 넣지 않은 개조만** 넣으세요 — 설비 시나리오 비가동에 이미 든 "
    "개조는 가용에서 이미 빠져 있어 두 번 빠집니다."
)
CHART_NOTE: Final = (
    "아래 띠 = 차수별 개조 비가동(글 = 대수 — 글이 들지 않는 막대는 풍선에) · 옅은 빨강 칠 = 개조 "
    "없이도 기준(+ 안전 여유) 미달이라 넣지 않은 달 · 옅은 회색 칠 = 넣을 수 없는 달(시작 앞 · "
    "기한 뒤) · 막대는 W/D 구간 좌표라 달력 앞 달의 비가동이 Cut-off 만큼 앞선 다음 달 칸에 들 수 "
    "있습니다"
)
LIST_NOTE: Final = (
    "차수 = 같은 날 시작하는 묶음 · 날짜는 비가동 첫날 ~ 마지막 날(다음 날부터 일반 "
    "가용) · 끝은 걸친 W/D 달별 일수 · 대수는 환산 대수(호기는 고르지 않음)"
)
NO_BATCH_TEXT: Final = "넣을 수 있는 차수가 없습니다."
UNITS_HELP: Final = (
    "개조할 설비 대수(환산 대수) — 지금 있는 설비 가운데 **아직 개조하지 않은** 대수입니다. 이미 "
    "개조를 마쳤거나 제약 제품 전용으로 들고 있는 설비, 개조된 채 들어오는 신규 설비는 빼고 "
    "넣으세요. 어느 호기인지는 고르지 않습니다."
)
FELL_BACK_LABEL: Final = "가장 고르게 → 가장 빨리로 배치"


class ReasonCard(Protocol):
    """페이지의 까닭 카드 그리기(제목 · 풀이 · 가용설비 현황 링크)."""

    def __call__(self, title: str, detail: str, *, equipment_link: bool) -> None: ...


class ScheduleModeContext(NamedTuple):
    """페이지가 넘기는 것 — 공통 진입·설비 세션·카드 이름과 머리·까닭 카드 그리기."""

    page_inputs: ProcessPageInputs
    process_labels: ProcessLabels
    equipment_session: EquipmentSession | None
    snapshot: EquipmentSnapshot | None
    cutoff: pd.DataFrame
    equipment_error: str
    today: date
    card_label: str
    card_name: str
    card_icon: str
    header_slot: DeltaGenerator
    """머리 한 줄 자리(페이지의 `header_marks`) — 「저장하지 않음」 캡션을 제약 모드와 같은 자리에.
    """

    session_note: str
    render_header: Callable[[str, str], None]
    render_reason_card: ReasonCard


class ScheduleChoice(NamedTuple):
    """조건 카드가 고른 값."""

    units: int
    days: int
    concurrent: int | None
    start_month: int
    """`NO_CHOICE` 면 내일."""

    deadline_month: int
    """`NO_CHOICE` 면 기한 없음."""

    aligned: bool
    general_percent: float | None
    margin_points: float
    objective: Objective


# ================================================================== 모드 전환(본문)


def render_mode_switch() -> str:
    """본문 맨 위 「제약 영향 | 개조 일정」. 고른 모드를 돌려준다(`persist_state="session"`)."""
    settle_mode()
    mode = st.segmented_control(
        "시뮬레이션 모드",
        MODES,
        format_func=lambda value: MODE_LABELS.get(str(value), str(value)),
        key=CONSTRAINT_MODE_KEY,
        persist_state="session",
        required=True,
        label_visibility="collapsed",
        help=(
            "제약 영향 — 제약 제품 전용 설비가 생기면 기존 제품 확보율이 얼마나 주나. 개조 일정 — "
            "N대 × D일 개조를 모든 달 기준 확보율을 지키며 언제 할까."
        ),
    )
    return str(mode) if mode in MODES else CONSTRAINT_MODE


# ================================================================== 시작·기한 선택지(순수)


def earliest_day(start_month: int, *, cutoff_days: int | None, today: date) -> date:
    """가장 이른 시작 — 내일, 또는 고른 달 W/D 첫날(내일보다 앞이면 내일)."""
    tomorrow = today + timedelta(days=1)
    if start_month == NO_CHOICE or cutoff_days is None:
        return tomorrow
    return max(tomorrow, wd_window(start_month, cutoff_days).first_day)


def deadline_day(deadline_month: int, *, cutoff_days: int | None) -> date | None:
    """끝 날 상한 — 「X월 W/D 첫날 전」 = 그 첫날 − 1일. 없으면 None."""
    if deadline_month == NO_CHOICE or cutoff_days is None:
        return None
    return wd_window(deadline_month, cutoff_days).first_day - timedelta(days=1)


def start_options(months: Sequence[int], *, cutoff_days: int | None, today: date) -> list[int]:
    """시작 상자 선택지 — 「내일」 + W/D 첫날이 내일보다 뒤인 달(Cut-off 를 모르면 모든 달)."""
    tomorrow = today + timedelta(days=1)
    chosen = [
        int(month)
        for month in months
        if cutoff_days is None or wd_window(int(month), cutoff_days).first_day > tomorrow
    ]
    return [NO_CHOICE, *chosen]


def deadline_options(
    months: Sequence[int],
    *,
    cutoff_days: int | None,
    today: date,
    start_month: int = NO_CHOICE,
) -> list[int]:
    """기한 상자 선택지 — 「없음」 + 「X월 W/D 첫날 전」 이 고른 시작(내일 또는 그 달 W/D
    첫날) 이후인 달(Cut-off 를 모르면 모든 달). 시작보다 앞선 기한은 고를 수 없다."""
    first = earliest_day(start_month, cutoff_days=cutoff_days, today=today)
    chosen = [
        int(month)
        for month in months
        if cutoff_days is None
        or wd_window(int(month), cutoff_days).first_day - timedelta(days=1) >= first
    ]
    return [NO_CHOICE, *chosen]


def _start_label(month: int, *, cutoff_days: int | None, today: date) -> str:
    if month == NO_CHOICE:
        return f"내일({(today + timedelta(days=1)).isoformat()})부터"
    if cutoff_days is None:
        return f"{month_label(month)} W/D 첫날부터"
    first = wd_window(month, cutoff_days).first_day
    return f"{month_label(month)} W/D 첫날({first:%m-%d})부터"


def _deadline_label(month: int, *, cutoff_days: int | None) -> str:
    if month == NO_CHOICE:
        return "없음 — 조회기간 끝까지"
    if cutoff_days is None:
        return f"{month_label(month)} W/D 첫날 전까지"
    last = wd_window(month, cutoff_days).first_day - timedelta(days=1)
    return f"{month_label(month)} W/D 첫날 전({last:%m-%d}까지)"


# ================================================================== 조건 카드


def _render_conditions(
    page_inputs: ProcessPageInputs, *, today: date, cutoff_days: int | None
) -> ScheduleChoice:
    """카드의 「이 세션만」 · 개조 · 일정 · 기준 묶음(지금 컨테이너 — 조건 카드 안)."""
    months = list(page_inputs.months)
    thresholds = page_inputs.thresholds
    st.caption(":material/person: **이 세션만** — 저장하지 않습니다")
    st.caption("**개조**")
    settle_units(*UNITS_RANGE)
    units = st.number_input(
        "개조 대수",
        min_value=UNITS_RANGE[0],
        max_value=UNITS_RANGE[1],
        step=1,
        format="%d",
        key=SCHEDULE_UNITS_KEY,
        persist_state="session",
        help=UNITS_HELP,
    )
    units_value = int(units)
    days = render_preset_number_field(
        "개조 기간",
        value_key=SCHEDULE_DAYS_KEY,
        pills_key=SCHEDULE_DAYS_PILLS_KEY,
        input_key=SCHEDULE_DAYS_INPUT_KEY,
        presets=MOD_DAY_PRESETS,
        default=DEFAULT_SCHEDULE_DAYS,
        minimum=MODIFICATION_DAYS_RANGE[0],
        maximum=MODIFICATION_DAYS_RANGE[1],
        step=1,
        unit="일",
        number_format="%d",
        fallback=DEFAULT_SCHEDULE_DAYS,
        preset_label=lambda value: f"{value:g}일" if value is not None else "",
        help=(
            "한 대의 개조 일수(이어진 날, 그동안 완전 비가동). 끝나면 다음 날부터 일반 가용입니다."
        ),
    )
    concurrent = render_preset_number_field(
        "동시 개조 상한",
        value_key=SCHEDULE_CONCURRENT_KEY,
        pills_key=SCHEDULE_CONCURRENT_PILLS_KEY,
        input_key=SCHEDULE_CONCURRENT_INPUT_KEY,
        presets=CONCURRENT_PRESETS,
        default=DEFAULT_CONCURRENT,
        minimum=CONCURRENT_RANGE[0],
        maximum=CONCURRENT_RANGE[1],
        step=1,
        unit="대",
        number_format="%d",
        fallback=CONCURRENT_RANGE[0],
        preset_label=lambda value: "없음" if value is None else f"{value:g}대",
        help=(
            "같은 날 개조 중인 대수의 상한(인력·부품·업체). 「없음」 이면 칸이 비고 결과에 "
            "최대 동시 대수를 보입니다. 어느 쪽이든 같은 날 개조 대수는 그 달 가용(환산 대수 "
            "내림)을 넘지 않습니다."
        ),
        none_placeholder="없음",
    )

    st.caption("**일정**")
    starts = start_options(months, cutoff_days=cutoff_days, today=today)
    settle_choice(SCHEDULE_START_KEY, starts)
    start_month = st.selectbox(
        "시작",
        starts,
        key=SCHEDULE_START_KEY,
        persist_state="session",
        format_func=lambda month: _start_label(int(month), cutoff_days=cutoff_days, today=today),
        help="가장 이른 개조 시작. 이미 지난 W/D 구간에는 넣지 않습니다.",
    )
    deadlines = deadline_options(
        months, cutoff_days=cutoff_days, today=today, start_month=int(start_month)
    )
    settle_choice(SCHEDULE_DEADLINE_KEY, deadlines)
    deadline_month = st.selectbox(
        "기한",
        deadlines,
        key=SCHEDULE_DEADLINE_KEY,
        persist_state="session",
        format_func=lambda month: _deadline_label(int(month), cutoff_days=cutoff_days),
        help=(
            "모든 개조를 마칠 날 — 「X월 W/D 첫날 전」 이면 X월 생산부터 개조 비가동이 없습니다. "
            "고른 시작보다 뒤인 달만 나옵니다."
        ),
    )
    seed_toggle(SCHEDULE_ALIGNED_KEY, False)
    aligned = st.toggle(
        "달 맞춤 창",
        key=SCHEDULE_ALIGNED_KEY,
        persist_state="session",
        help=(
            "켜면 개조 창을 그 달 W/D 끝 날에 끝나도록 달마다 하나로만 놓습니다(제약 "
            "영향 모드의 창 꼴) — 차수가 적어 읽기 쉽지만 날 단위보다 늦게 끝날 수 있습니다."
        ),
    )

    st.caption("**기준**")
    home_percent = thresholds.default_secure * 100
    general = render_preset_number_field(
        "기준 확보율",
        value_key=CONSTRAINT_GENERAL_KEY,
        pills_key=CONSTRAINT_GENERAL_PILLS_KEY,
        input_key=CONSTRAINT_GENERAL_INPUT_KEY,
        presets=GENERAL_PRESETS,
        default=None,
        minimum=GENERAL_INPUT_RANGE[0] * 100,
        maximum=GENERAL_INPUT_RANGE[1] * 100,
        step=0.5,
        unit="%",
        number_format="%.1f",
        fallback=home_percent,
        preset_label=lambda value: "HOME 기준" if value is None else f"{value:g}%",
        help=(
            "개조 뒤 공정 확보율이 모든 달 이 값 이상이어야 합니다. 「HOME 기준」 은 HOME → "
            "Preference 공용 판정 기준(기본 + 월별 예외)을 달마다 씁니다. 제약 영향 모드와 한 값을 "
            "나눕니다."
        ),
    )
    st.caption(
        "HOME · "
        + securement_threshold_caption(
            thresholds, start_month=page_inputs.effective_start, end_month=page_inputs.effective_end
        )
    )
    margin = render_preset_number_field(
        "안전 여유",
        value_key=SCHEDULE_MARGIN_KEY,
        pills_key=SCHEDULE_MARGIN_PILLS_KEY,
        input_key=SCHEDULE_MARGIN_INPUT_KEY,
        presets=MARGIN_PRESETS,
        default=DEFAULT_MARGIN_POINTS,
        minimum=MARGIN_RANGE[0] * 100,
        maximum=MARGIN_RANGE[1] * 100,
        step=0.5,
        unit="%p",
        number_format="%.1f",
        fallback=DEFAULT_MARGIN_POINTS,
        preset_label=lambda value: f"{value:g}%p" if value is not None else "",
        help=(
            "기준 확보율에 더해 띄울 여유. 「가장 빨리」 는 기준에 딱 붙기 쉬워 계획이 조금만 "
            "늘어도 미달이 됩니다 — 여유를 넣으면 같은 계산이 그만큼 띄웁니다."
        ),
    )
    has_deadline = int(deadline_month) != NO_CHOICE
    settle_objective(has_deadline=has_deadline)
    objective = st.segmented_control(
        "목적",
        tuple(OBJECTIVE_LABELS),
        format_func=lambda value: OBJECTIVE_LABELS.get(str(value), str(value)),
        key=SCHEDULE_OBJECTIVE_KEY,
        persist_state="session",
        required=True,
        disabled=not has_deadline,
        help=(
            "가장 빨리 — 모든 달 기준을 지키며 가장 이른 달에 끝냅니다. 가장 고르게(기한이 "
            "있을 때만) — 기한 안에서 개조가 든 달의 기준 대비 여유(확보율 − 그 달 기준) 가운데 "
            "가장 작은 것을 가장 크게 둡니다. 여유만으로도 기한을 못 맞추면 가장 빨리로 배치합니다."
        ),
    )
    chosen: Objective = "even" if objective == "even" and has_deadline else "earliest"
    return ScheduleChoice(
        units=units_value,
        days=int(round(days if days is not None else DEFAULT_SCHEDULE_DAYS)),
        concurrent=None if concurrent is None else int(round(concurrent)),
        start_month=int(start_month),
        deadline_month=int(deadline_month),
        aligned=bool(aligned),
        general_percent=None if general is None else float(general),
        margin_points=float(margin if margin is not None else DEFAULT_MARGIN_POINTS),
        objective=chosen,
    )


# ================================================================== 계산 memo


def remembered_result(
    inputs: Sequence[ScheduleMonthInput], conditions: ScheduleConditions
) -> ScheduleResult:
    """결과를 조건 값으로 세션에 몇 벌 기억한다. 계산이 실패하면 기억하지 않는다."""
    key = (_RESULT_SCHEMA_VERSION, tuple(inputs), conditions)
    memo = st.session_state.get(SCHEDULE_RESULT_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], ScheduleResult]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key:
            return stored
    result = plan_modification_schedule(inputs, conditions)
    entries = [entry for entry in entries if entry[0] != key][-(_MEMO_LIMIT - 1) :]
    st.session_state[SCHEDULE_RESULT_MEMO_KEY] = [*entries, (key, result)]
    return result


def remembered_figure(result: ScheduleResult, labels: ScheduleLabels) -> go.Figure:
    """그래프를 세션에 몇 벌 기억한다(키 = 그림 모양 버전 · 테마 · 결과 · 화면 글자). 꺼낸 그림은
    고치지 않는다."""
    key = (SCHEDULE_FIGURE_SCHEMA_VERSION, theme.current_mode(), result, labels)
    memo = st.session_state.get(SCHEDULE_FIGURE_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], go.Figure]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key:
            return stored
    figure = schedule_figure(result, labels)
    entries = [entry for entry in entries if entry[0] != key][-(_MEMO_LIMIT - 1) :]
    st.session_state[SCHEDULE_FIGURE_MEMO_KEY] = [*entries, (key, figure)]
    return figure


# ================================================================== 설비 일정·계획


def _readiness(context: ScheduleModeContext, process: str | None) -> DynamicReadiness | None:
    """설비 일정을 세울 수 있는가 — 설비 DB 를 못 읽었으면 None(페이지와 같은 판정)."""
    if context.equipment_error or process is None:
        return None
    snapshot = context.snapshot
    return dynamic_readiness(
        snapshot.calculation_frames()[1] if snapshot is not None else None,
        snapshot.baseline if snapshot is not None else None,
        context.cutoff,
        process=str(process),
    )


def _plan(
    context: ScheduleModeContext, snapshot: EquipmentSnapshot
) -> tuple[ShorteningPlan, MonthlyTarget]:
    """공정 Capa 상세 ②·제약 모드와 같은 계획 칸을 같은 키로(목표는 키 맞춤용 HOME 확보기준)."""
    page_inputs = context.page_inputs
    months = list(page_inputs.months)
    active_scenario = page_inputs.context.active_scenario
    baseline, equipment, downtime = snapshot.calculation_frames()
    target_level = target_from_thresholds(page_inputs.thresholds, months)
    shortening_key = simulation_cache.required_shortening_cache_key(
        page_inputs.capacity_cache_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=context.cutoff,
        months=tuple(months),
        today=context.today,
    )
    plan = simulation_cache.load_required_shortening_for_target(
        simulation_cache.required_shortening_target_cache_key(shortening_key, target_level),
        equipment,
        downtime,
        baseline,
        context.cutoff,
        required_equipment=simulation_cache.scenario_required_equipment(
            page_inputs.capacity_cache_key,
            scenario_tables=active_scenario["tables"],
            reference_tables=page_inputs.context.reference_tables,
        ),
    )
    return plan, target_level


# ================================================================== 모드 한 회차


def render_schedule_mode(context: ScheduleModeContext) -> None:
    """조건 카드 → 설비 일정 확인 → 계획 → 계산 → 본문. 멈출 갈래는 까닭을 그리고 돌아온다."""
    page_inputs = context.page_inputs
    months = list(page_inputs.months)
    options = page_inputs.process_options
    process_labels = context.process_labels
    with condition_card(context.card_label, name=context.card_name, icon=context.card_icon):
        st.caption("**대상**")
        selected = st.selectbox(
            "공정",
            options,
            key=CONSTRAINT_PROCESS_KEY,
            persist_state="session",
            disabled=not options,
            format_func=process_labels.unique_format_func(options),
        )
        readiness = _readiness(context, None if selected is None else str(selected))
        cutoff_days = readiness.cutoff_days if readiness is not None and readiness.ready else None
        choice = _render_conditions(page_inputs, today=context.today, cutoff_days=cutoff_days)
        st.caption(
            f"Cut-off {readiness.cutoff_days}일 — 가용설비 현황 「설정」 팝업의 공정별 "
            "값(모든 설비 시나리오 공용)"
            if readiness is not None and readiness.cutoff_days is not None
            else "Cut-off 미기재"
        )

    if selected is None or not months:
        st.info("조회기간에 확보율을 낼 공정이 없습니다.", icon=":material/info:")
        return
    process = str(selected)
    process_label = process_labels.label(process)
    bold = f"**{literal_markdown(process_label)}**"
    if readiness is None:
        context.render_header(process, f"{bold} :blue-badge[설비 일정 없음: 설비 DB 오류]")
        context.render_reason_card(
            "설비 일정 없음: 설비 DB 를 읽지 못했습니다",
            context.equipment_error or "설비 DB 를 열지 못했습니다.",
            equipment_link=False,
        )
        return
    snapshot = context.snapshot
    if not readiness.ready or readiness.cutoff_days is None or snapshot is None:
        context.render_header(process, f"{bold} :blue-badge[{readiness.badge}]")
        context.render_reason_card(
            readiness.badge,
            f"{readiness.detail} 개조 일정은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 값)으로 "
            "계산하므로 설비 DB 에 저장본이 있고 이름이 같으며 Cut-off 가 적힌 공정에만 섭니다.",
            equipment_link=True,
        )
        return
    try:
        plan, target_level = _plan(context, snapshot)
    except BOOTSTRAP_ERRORS as exc:
        context.render_header(process, f"{bold} :blue-badge[설비 일정 없음: 계산 오류]")
        st.error(
            "설비 일정을 계산하지 못했습니다 — "
            + bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH))
        )
        return
    if process not in plan.processes:
        missing_cutoff = process in plan.missing_cutoff
        context.render_header(process, f"{bold} :blue-badge[설비 일정 없음]")
        context.render_reason_card(
            "설비 일정 없음: Cut-off 미기재"
            if missing_cutoff
            else "설비 일정 없음: 계획에 공정 없음",
            (
                "가용설비 현황의 공정별 Cut-off 에 이 공정이 없습니다."
                if missing_cutoff
                else "설비 일정 기준 가용에 이 공정이 없습니다 — 설비 마스터 공정소분류·기존보유 "
                "공정 이름이 시나리오 공정과 완전히 같아야 맞댑니다."
            ),
            equipment_link=True,
        )
        return

    thresholds = page_inputs.thresholds

    def general_target(month: int) -> float:
        if choice.general_percent is None:
            return float(thresholds.secure_for(month))
        return choice.general_percent / 100

    cutoff = int(readiness.cutoff_days)
    try:
        inputs = schedule_month_inputs(
            plan.at(target_level).process_months,
            process=process,
            months=months,
            general_target=general_target,
        )
        conditions = ScheduleConditions(
            units=choice.units,
            days=choice.days,
            cutoff_days=cutoff,
            earliest=earliest_day(choice.start_month, cutoff_days=cutoff, today=context.today),
            deadline=deadline_day(choice.deadline_month, cutoff_days=cutoff),
            concurrent=choice.concurrent,
            margin=choice.margin_points / 100,
            objective=choice.objective,
            aligned=choice.aligned,
        )
        result = remembered_result(inputs, conditions)
    except (KeyError, ValueError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        context.render_header(process, bold)
        st.error(f"개조 일정을 찾지 못했습니다 — {message}")
        return

    labels = ScheduleLabels(process_label=process_label, general_percent=choice.general_percent)
    context.render_header(process, _header_line(bold, result, labels))
    _render_source_band(context, process_label)
    render_schedule_kpis(result, labels)
    _render_body(result, labels)


def _header_line(bold: str, result: ScheduleResult, labels: ScheduleLabels) -> str:
    conditions = result.conditions
    parts = [
        bold,
        f"개조 {conditions.units}대 × {conditions.days}일",
        f"기준 {literal_markdown(general_text(labels, result))}"
        + (f" +{conditions.margin * 100:g}%p" if conditions.margin > 0 else ""),
        FELL_BACK_LABEL if result.fell_back else OBJECTIVE_LABELS[conditions.objective],
        "동시 상한 없음"
        if conditions.concurrent is None
        else f"동시 {conditions.concurrent}대까지",
    ]
    if conditions.aligned:
        parts.append("달 맞춤 창")
    return " · ".join(parts)


def _render_source_band(context: ScheduleModeContext, process_label: str) -> None:
    """「저장하지 않음」(머리 자리) · 출처 띠 · 「아직 일정에 넣지 않은 개조만」."""
    with context.header_slot:
        st.caption(context.session_note)
    scenario_label = active_scenario_label()
    scenario_text = (
        f"「{literal_markdown(scenario_label.scenario_name)} r{scenario_label.revision_no}」"
        if scenario_label is not None
        else "활성 시나리오"
    )
    session = context.equipment_session
    equipment_text = equipment_basis_label(session) if session is not None else None
    band = (
        f":material/database: 소요 = 활성 시나리오 {scenario_text} "
        f"{literal_markdown(process_label)} 공정 소요 · 가용 = 설비 일정 기준"
        + (f"({literal_markdown(equipment_text)}, 단축 전)" if equipment_text else "(단축 전)")
        + " · 대수는 환산 대수 — HOME·Static 확보율(기준정보 가용)과 다를 수 있음"
    )
    upeh_percent = st.session_state.get(
        UPEH_ASSUMPTION_PERCENT_KEY, UPEH_ASSUMPTION_DEFAULT_PERCENT
    )
    if isinstance(upeh_percent, int) and upeh_percent != UPEH_ASSUMPTION_DEFAULT_PERCENT:
        band += " · UPEH 가정은 이 화면에 걸리지 않습니다(공식 소요)"
    st.caption(band)
    st.caption(DOUBLE_COUNT_NOTE)


# ================================================================== 요약 넷


def render_schedule_kpis(result: ScheduleResult, labels: ScheduleLabels) -> None:
    """요약 넷 — 개조 완료 · 최대 동시 개조 · 개조 달 최저 확보율 · 기한."""
    conditions = result.conditions
    with metric_row(key=KPI_ROW_KEY):
        if result.complete and result.finish_day is not None:
            tone1: MetricTone = "good"
            value1 = result.finish_day.isoformat()
            caption1 = (
                f"{month_label(result.finish_month)} W/D 안 · {len(result.batches)}차수"
                if result.finish_month is not None
                else f"{len(result.batches)}차수"
            )
        else:
            tone1 = "critical"
            value1 = f"{result.placed} / {conditions.units}대"
            caption1 = (
                "기한까지 넣을 수 있는 대수"
                if conditions.deadline is not None
                and result.shortfall is not None
                and result.shortfall.by_deadline
                else "조회기간 끝까지 넣을 수 있는 대수"
            )
        render_status_metric(
            "개조 완료",
            value1,
            key="constraint_sim_sched_kpi_finish",
            tone=tone1,
            caption=caption1,
            help=(
                "마지막 차수의 비가동 마지막 날과 그 날이 든 W/D 달입니다. 확보율이 W/D 월평균이라 "
                "「몇 월에 끝나나」 가 답이고, 날은 이 배치의 끝 날입니다."
            ),
        )
        render_status_metric(
            "최대 동시 개조",
            f"{result.max_concurrent}대",
            key="constraint_sim_sched_kpi_concurrent",
            caption=(
                "상한 없음" if conditions.concurrent is None else f"상한 {conditions.concurrent}대"
            ),
            help=(
                "같은 날 개조 중인 가장 많은 대수(환산)입니다 — 인력·부품이 받쳐 주는지 "
                "보세요. 같은 날 개조 대수는 그 달 가용(환산 대수 내림)을 넘지 않게 배치합니다."
            ),
        )
        tightest = (
            result.month(result.tightest_month) if result.tightest_month is not None else None
        )
        render_status_metric(
            "개조 달 최저 여유",
            signed_points(result.tightest_margin) if tightest is not None else _EMPTY,
            key="constraint_sim_sched_kpi_lowest",
            tone="neutral" if tightest is None or tightest.secure_after else "critical",
            caption=_tightest_caption(result, tightest),
            help=(
                "개조 비가동이 든 달 가운데 기준 대비 여유(개조 뒤 확보율 − 그 달 기준)가 "
                f"가장 작은 달입니다(기준 {general_text(labels, result)}). 「가장 고르게」 는 이 "
                "값을 가장 크게 둡니다. 기준을 지키는 것은 늘 보장합니다 — 0.0%p 이상입니다."
            ),
        )
        tone4: MetricTone
        if conditions.deadline is None:
            tone4, value4 = "neutral", "없음"
            caption4 = f"조회기간 끝 {result.last_day.isoformat()} 까지"
        elif result.complete:
            tone4, value4 = "good", "맞춤"
            caption4 = f"{conditions.deadline.isoformat()} 까지" + (
                " · 가장 빨리로 배치"
                if result.fell_back
                else f" · 가장 고르게 기준 {signed_points(result.applied_margin)}"
                if conditions.objective == "even"
                else ""
            )
        else:
            tone4, value4 = "critical", "못 맞춤"
            shortfall = result.shortfall
            caption4 = (
                f"{result.remaining}대 남음"
                + (" · 가장 빨리로 배치" if result.fell_back else "")
                + (
                    f" · {relief_text(shortfall.relief)}"
                    if shortfall is not None and shortfall.relief is not None
                    else ""
                )
            )
        render_status_metric(
            "기한",
            value4,
            key="constraint_sim_sched_kpi_deadline",
            tone=tone4,
            caption=caption4,
            help=(
                "기한(「X월 W/D 첫날 전」)까지 모든 개조를 마치는가입니다. 못 맞추면 남은 대수와, "
                "기한(없으면 조회기간 끝) 안에 다 넣으려면 기준을 얼마나 낮춰야 하는지(「기준 n%p "
                "낮추기」 — 0.01%p 올림이라 적힌 만큼 낮추면 들어갑니다)를 적습니다."
            ),
        )


def _tightest_caption(result: ScheduleResult, tightest: ScheduleMonth | None) -> str:
    if tightest is not None:
        return f"{month_label(tightest.month)} · 확보율 {rate_text(result.tightest_rate)}"
    if any(row.downtime_unit_days > 0 for row in result.months):
        return "개조가 든 달이 모두 소요 0 입니다"
    return "개조 비가동이 든 달이 없습니다"


# ================================================================== 본문


def _render_body(result: ScheduleResult, labels: ScheduleLabels) -> None:
    """(못 맞추면) 대안 셋 → 그래프 → 차수 목록.

    생겼다 사라지는 알림은 늘 서 있는 칸 안에 그린다.
    """
    with st.container():
        lines = shortfall_lines(result)
        if lines:
            with st.container(border=True, key=SHORTFALL_CARD_KEY):
                st.markdown(":material/warning: **다 넣지 못했습니다 — 대안**")
                for line in lines:
                    st.markdown(f"- {line}")
    st.html(
        "<style>"
        + min_width_scroll_rules(
            CHART_SCROLL_PREFIX, min_width_px=chart_min_width_px(len(result.months))
        )
        + "</style>"
    )
    with st.container(border=True, key=CHART_CARD_KEY):
        st.markdown("**월별 확보율 — 개조 전 · 뒤**")
        st.caption(CHART_NOTE)
        with min_width_scroll_canvas(key=CHART_SCROLL_PREFIX):
            st.plotly_chart(
                remembered_figure(result, labels),
                width="stretch",
                key=SCHEDULE_CHART_KEY,
                config=hover_chart_config(),
            )
    with st.container(border=True, key=LIST_CARD_KEY):
        st.markdown("**개조 일정**")
        with st.container():
            if not result.batches:
                st.caption(NO_BATCH_TEXT)
            for number, batch in enumerate(result.batches, start=1):
                st.markdown(batch_line(number, batch))
        st.caption(LIST_NOTE)
