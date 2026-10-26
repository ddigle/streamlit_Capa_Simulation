# Purpose: 제약 시뮬레이션 「개조 일정」 모드의 모드 전환·조건 세션 키·기본값·버튼 값을 UI 없이
# 선언한다.

"""「제약 영향 | 개조 일정」 모드 전환과 개조 일정 모드의 세션 계약(2026-10-26 사용자 결정 3).

제약 모드 계약(`constraint_simulation_state.py`)과 나눠 둔다 — 두 모드는 같은 페이지·같은 공정
칸(`CONSTRAINT_PROCESS_KEY`)·같은 기준 확보율 정본(`CONSTRAINT_GENERAL_KEY`)을 나누지만, 개조 일정
모드만의 칸은 여기 있다. 세션 키는 모두 `constraint_sim_` 접두(모드 전환)·`constraint_sim_sched_`
접두다(`tests/test_session_key_collisions.py`). **저장하지 않는다**(C13).

- **위젯 칸**(`persist_state="session"`) — 모드 전환(본문 `segmented_control`), 개조 대수 숫자 칸,
  시작·기한 상자, 「달 맞춤 창」 토글, 목적(`segmented_control`).
- **정본 칸**(위젯 아님) — 개조 기간(정수 일)·동시 개조 상한(`None` = 없음, 아니면 정수 대)·안전
  여유(%p 실수). 버튼과 직접 입력 칸 둘이 한 정본을 나눠 쓴다(`components/preset_number_field.py`).
- **결과 memo**(세션 칸 LRU — Streamlit 캐시가 아니다) — 「가장 고르게」 는 이분 탐색이라 수백 ms
  까지 가므로 조건 값으로 한 번만 푼다.

시작·기한 상자는 정수 선택지라(0 = 「내일」·「없음」) `settle_choice` 가 위젯 앞에서 매 회차 잡는다
— 칸이 없거나 선택지 밖이면 0 을 적고, 바뀐 칸만 적는다(pop 하지 않는다 — AGENTS 9장).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import streamlit as st

__all__ = [
    "CONSTRAINT_MODE",
    "CONSTRAINT_MODE_KEY",
    "DEFAULT_CONCURRENT",
    "DEFAULT_MARGIN_POINTS",
    "DEFAULT_SCHEDULE_DAYS",
    "DEFAULT_SCHEDULE_UNITS",
    "MARGIN_PRESETS",
    "MODE_LABELS",
    "MODES",
    "NO_CHOICE",
    "OBJECTIVE_LABELS",
    "SCHEDULE_ALIGNED_KEY",
    "SCHEDULE_CHART_KEY",
    "SCHEDULE_CONCURRENT_INPUT_KEY",
    "SCHEDULE_CONCURRENT_KEY",
    "SCHEDULE_CONCURRENT_PILLS_KEY",
    "SCHEDULE_DAYS_INPUT_KEY",
    "SCHEDULE_DAYS_KEY",
    "SCHEDULE_DAYS_PILLS_KEY",
    "SCHEDULE_DEADLINE_KEY",
    "SCHEDULE_FIGURE_MEMO_KEY",
    "SCHEDULE_MARGIN_INPUT_KEY",
    "SCHEDULE_MARGIN_KEY",
    "SCHEDULE_MARGIN_PILLS_KEY",
    "SCHEDULE_MODE",
    "SCHEDULE_OBJECTIVE_KEY",
    "SCHEDULE_RESULT_MEMO_KEY",
    "SCHEDULE_START_KEY",
    "SCHEDULE_UNITS_KEY",
    "CONCURRENT_PRESETS",
    "settle_choice",
    "settle_mode",
    "settle_objective",
    "settle_units",
]

# ------------------------------------------------------------------ 모드 전환(본문)
CONSTRAINT_MODE_KEY: Final = "constraint_sim_mode"
CONSTRAINT_MODE: Final = "constraint"
SCHEDULE_MODE: Final = "schedule"
MODES: Final = (CONSTRAINT_MODE, SCHEDULE_MODE)
MODE_LABELS: Final = {CONSTRAINT_MODE: "제약 영향", SCHEDULE_MODE: "개조 일정"}

# ------------------------------------------------------------------ 위젯 칸
SCHEDULE_UNITS_KEY: Final = "constraint_sim_sched_units"
SCHEDULE_START_KEY: Final = "constraint_sim_sched_start"
SCHEDULE_DEADLINE_KEY: Final = "constraint_sim_sched_deadline"
SCHEDULE_ALIGNED_KEY: Final = "constraint_sim_sched_aligned"
SCHEDULE_OBJECTIVE_KEY: Final = "constraint_sim_sched_objective"

# ------------------------------------------------------------------ 정본 칸(위젯 아님)과 그 위젯 둘
SCHEDULE_DAYS_KEY: Final = "constraint_sim_sched_days"
SCHEDULE_DAYS_PILLS_KEY: Final = "constraint_sim_sched_days_pills"
SCHEDULE_DAYS_INPUT_KEY: Final = "constraint_sim_sched_days_input"
# `None` 이면 동시 개조 상한 없음.
SCHEDULE_CONCURRENT_KEY: Final = "constraint_sim_sched_concurrent"
SCHEDULE_CONCURRENT_PILLS_KEY: Final = "constraint_sim_sched_concurrent_pills"
SCHEDULE_CONCURRENT_INPUT_KEY: Final = "constraint_sim_sched_concurrent_input"
SCHEDULE_MARGIN_KEY: Final = "constraint_sim_sched_margin"
SCHEDULE_MARGIN_PILLS_KEY: Final = "constraint_sim_sched_margin_pills"
SCHEDULE_MARGIN_INPUT_KEY: Final = "constraint_sim_sched_margin_input"

# ------------------------------------------------------------------ 본문
SCHEDULE_CHART_KEY: Final = "constraint_sim_sched_chart"
SCHEDULE_RESULT_MEMO_KEY: Final = "constraint_sim_sched_result_memo"
SCHEDULE_FIGURE_MEMO_KEY: Final = "constraint_sim_sched_figure_memo"

# ------------------------------------------------------------------ 버튼 값·기본값
NO_CHOICE: Final = 0
"""시작 「내일」·기한 「없음」 의 상자 값."""

CONCURRENT_PRESETS: Final[tuple[int | None, ...]] = (None, 1, 2, 3, 4, 5)
MARGIN_PRESETS: Final = (0, 1, 2, 3, 5)
DEFAULT_SCHEDULE_UNITS: Final = 4
DEFAULT_SCHEDULE_DAYS: Final = 30
DEFAULT_CONCURRENT: Final = None
DEFAULT_MARGIN_POINTS: Final = 0
OBJECTIVE_LABELS: Final = {"earliest": "가장 빨리", "even": "가장 고르게"}


def _write_if_changed(key: str, value: object) -> None:
    if st.session_state.get(key) != value:
        st.session_state[key] = value


def settle_mode() -> str:
    """모드 칸을 위젯 앞에서 잡는다 — 없거나 모르는 값이면 제약 모드."""
    held = st.session_state.get(CONSTRAINT_MODE_KEY)
    value = held if held in MODES else CONSTRAINT_MODE
    _write_if_changed(CONSTRAINT_MODE_KEY, value)
    return str(value)


def settle_units(minimum: int, maximum: int) -> int:
    """개조 대수 칸 — 없거나 범위 밖이면 기본값(범위 안으로)."""
    held = st.session_state.get(SCHEDULE_UNITS_KEY)
    if isinstance(held, bool) or not isinstance(held, int) or not minimum <= held <= maximum:
        held = min(max(DEFAULT_SCHEDULE_UNITS, minimum), maximum)
    _write_if_changed(SCHEDULE_UNITS_KEY, held)
    return int(held)


def settle_choice(key: str, options: Sequence[int]) -> int:
    """시작·기한 상자 칸 — 선택지 밖이면 `NO_CHOICE`(조회기간·Cut-off 가 바뀌어 달이 빠졌을 때)."""
    held = st.session_state.get(key)
    value = (
        held
        if isinstance(held, int) and not isinstance(held, bool) and held in options
        else NO_CHOICE
    )
    _write_if_changed(key, value)
    return int(value)


def settle_objective(*, has_deadline: bool) -> str:
    """목적 칸 — 기한이 없으면 「가장 빨리」 로 적는다(「가장 고르게」 는 기한이 있어야 한다)."""
    held = st.session_state.get(SCHEDULE_OBJECTIVE_KEY)
    value = held if held in OBJECTIVE_LABELS and has_deadline else "earliest"
    _write_if_changed(SCHEDULE_OBJECTIVE_KEY, value)
    return str(value)
