# Purpose: Capture and restore revision-owned Streamlit sidebar presets.

"""Capture and restore revision-owned Streamlit sidebar presets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime

import pandas as pd
import streamlit as st

from capa_simulation.persistence.models import (
    DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
    DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
    ScenarioPreset,
)
from capa_simulation.services.month_filter import MONTH_COLUMN, available_month_range
from capa_simulation.settings import MONTH_SELECTION_END, MONTH_SELECTION_START, format_month
from capa_simulation.shared_widget_state import carry_shared_widget_value

PENDING_PRESET_KEY = "pending_scenario_preset"
MONTH_RANGE_KEY = "production_month_range_v2"
MONTH_PICKER_KEY = "production_month_picker"
PROCESS_SELECTION_KEY = "dashboard_bottleneck_process_selection"
SECURE_THRESHOLD_KEY = "dashboard_secure_threshold_percent"
WARNING_THRESHOLD_KEY = "dashboard_warning_threshold_percent"
# 판정 기준은 리비전 프리셋이 소유하므로 기본값도 키 옆에 둔다. HOME 과 Static Capa 가
# 같은 세션 키를 쓰는데 기본값을 따로 적어 두면 한쪽만 바뀌어도 드러나지 않는다.
DEFAULT_SECURE_THRESHOLD_PERCENT = 109.5
DEFAULT_WARNING_THRESHOLD_PERCENT = 99.5
# 마지막으로 판정에 쓴 바른 (확보, 경고) 짝. 경고가 확보보다 큰 짝을 적용했을 때 대신 쓴다.
LAST_VALID_THRESHOLDS_KEY = "dashboard_threshold_last_valid"
STANDARD_TARGET_PROCESS_SELECTION_KEY = "standard_target_process_filter"
STANDARD_TARGET_PROCESS_DEFAULT_KEY = "standard_target_process_default"
# 표준 목표 Capa 「조회·집계 설정」도 리비전 프리셋이 소유하므로 세션 키를 여기서 선언한다.
STANDARD_TARGET_START_DATE_KEY = "standard_target_start_date"
STANDARD_TARGET_END_DATE_KEY = "standard_target_end_date"
STANDARD_TARGET_SHOW_DETAIL_KEY = "standard_target_show_detail"
STANDARD_TARGET_DETAIL_LEVEL_KEY = "standard_target_detail_level"
STANDARD_TARGET_OUTPUT_METRIC_KEY = "standard_target_output_metric"


def seed_threshold_defaults(*, owner: str) -> None:
    """판정 기준 두 칸을 위젯보다 먼저 세션에 세운다. `owner` 는 그리는 페이지의 이름이다.

    HOME 과 Static Capa 가 같은 세션 키를 공유한다. 어느 쪽을 먼저 열든 같은 값에서
    출발해야 하므로 심는 절차도 키·기본값 옆인 여기 한 곳에 둔다. 비어 있으면 기본값을
    심고, **다른 페이지에서 넘어온 회차에는 지금 값을 다시 적는다** — 그러지 않으면 넘어온
    첫 회차의 위젯이 `min_value`(0)로 서서 세션 내내 0% 로 판정한다
    (`shared_widget_state` 모듈 설명).
    """
    carry_shared_widget_value(
        SECURE_THRESHOLD_KEY, default=DEFAULT_SECURE_THRESHOLD_PERCENT, owner=owner
    )
    carry_shared_widget_value(
        WARNING_THRESHOLD_KEY, default=DEFAULT_WARNING_THRESHOLD_PERCENT, owner=owner
    )


def applied_threshold_pair(secure_percent: float, warning_percent: float) -> tuple[float, float]:
    """판정에 쓸 (확보, 경고) 짝(%). 경고가 확보보다 크면 **직전에 쓴 바른 짝**을 돌려준다.

    바른 짝이면 그것을 기억해 두고 그대로 돌려준다. 기억이 없으면 기본값이다. 기억 칸은
    위젯이 아니라 세션 칸이라 페이지를 옮겨도 남는다.
    """
    if warning_percent <= secure_percent:
        st.session_state[LAST_VALID_THRESHOLDS_KEY] = (secure_percent, warning_percent)
        return secure_percent, warning_percent
    remembered = st.session_state.get(LAST_VALID_THRESHOLDS_KEY)
    if (
        isinstance(remembered, tuple)
        and len(remembered) == 2
        and all(isinstance(value, int | float) for value in remembered)
        and remembered[1] <= remembered[0]
    ):
        return float(remembered[0]), float(remembered[1])
    return DEFAULT_SECURE_THRESHOLD_PERCENT, DEFAULT_WARNING_THRESHOLD_PERCENT


def session_threshold(key: str, default_percent: float) -> float:
    """세션의 판정 기준(%)을 비율로 바꾼다. 아직 아무도 위젯을 그리지 않았으면 기본값이다.

    `_session_number` 와 달리 값이 이상해도 예외를 던지지 않는다. 저장을 막아야 하는
    자리와 달리, 결과를 **읽어서 그리기만 하는** 화면이 기준 한 칸 때문에 멈추면 안 된다.
    """
    value = st.session_state.get(key, default_percent)
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return default_percent / 100.0


def capture_scenario_preset(reference_tables: Mapping[str, pd.DataFrame]) -> ScenarioPreset:
    """Build a validated persistent preset from the current user session."""
    start_month, end_month = _current_month_range()
    process_options = _available_processes(reference_tables)
    saved_processes = st.session_state.get(PROCESS_SELECTION_KEY)
    included_processes = (
        tuple(str(process) for process in saved_processes)
        if isinstance(saved_processes, list)
        else tuple(process_options)
    )
    secure_percent = _session_number(SECURE_THRESHOLD_KEY, DEFAULT_SECURE_THRESHOLD_PERCENT)
    warning_percent = _session_number(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD_PERCENT)
    standard_target_saved = st.session_state.get(STANDARD_TARGET_PROCESS_SELECTION_KEY)
    standard_target_processes = (
        tuple(str(process) for process in standard_target_saved)
        if isinstance(standard_target_saved, list)
        else ()
    )
    return ScenarioPreset(
        start_month=start_month,
        end_month=end_month,
        included_processes=included_processes,
        secure_threshold=secure_percent / 100.0,
        warning_threshold=warning_percent / 100.0,
        standard_target_processes=standard_target_processes,
        standard_target_start_date=_session_date(STANDARD_TARGET_START_DATE_KEY),
        standard_target_end_date=_session_date(STANDARD_TARGET_END_DATE_KEY),
        standard_target_show_detail=bool(st.session_state.get(STANDARD_TARGET_SHOW_DETAIL_KEY)),
        # 상세 토글이 꺼지면 분류 수준 위젯이 화면에 없다. 마지막 선택을 그대로 보존한다.
        standard_target_detail_level=_session_text(
            STANDARD_TARGET_DETAIL_LEVEL_KEY,
            DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
        ),
        standard_target_output_metric=_session_text(
            STANDARD_TARGET_OUTPUT_METRIC_KEY,
            DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
        ),
    )


def capture_full_data_scenario_preset(
    reference_tables: Mapping[str, pd.DataFrame],
) -> ScenarioPreset:
    """Use every available month and process for a newly downloaded dataset."""
    preset = capture_scenario_preset(reference_tables)
    start_month, end_month = _full_data_month_range(reference_tables)
    return replace(
        preset,
        start_month=start_month,
        end_month=end_month,
        included_processes=tuple(_available_processes(reference_tables)),
        standard_target_processes=(),
        standard_target_start_date=None,
        standard_target_end_date=None,
        standard_target_show_detail=False,
        standard_target_detail_level=DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
        standard_target_output_metric=DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
    )


def queue_scenario_preset(preset: ScenarioPreset) -> None:
    """Defer widget-state replacement until the next run starts before widget creation."""
    st.session_state[PENDING_PRESET_KEY] = preset


def apply_pending_scenario_preset() -> bool:
    """Apply one queued preset before shared widgets are constructed in app.py."""
    value = st.session_state.pop(PENDING_PRESET_KEY, None)
    if not isinstance(value, ScenarioPreset):
        return False
    st.session_state[MONTH_RANGE_KEY] = (
        format_month(value.start_month),
        format_month(value.end_month),
    )
    st.session_state.pop(MONTH_PICKER_KEY, None)
    st.session_state[PROCESS_SELECTION_KEY] = list(value.included_processes)
    st.session_state[SECURE_THRESHOLD_KEY] = value.secure_threshold * 100.0
    st.session_state[WARNING_THRESHOLD_KEY] = value.warning_threshold * 100.0
    standard_target_processes = list(value.standard_target_processes)
    st.session_state[STANDARD_TARGET_PROCESS_DEFAULT_KEY] = standard_target_processes
    st.session_state[STANDARD_TARGET_PROCESS_SELECTION_KEY] = standard_target_processes.copy()
    # 페이지를 한 번도 열지 않은 세션이 리비전을 저장해도 직전 설정이 날아가지 않도록
    # 조회·집계 설정도 여기서 반드시 세션에 쓴다. 저장된 날짜가 없으면 페이지 기본값을 쓴다.
    for key, saved_date in (
        (STANDARD_TARGET_START_DATE_KEY, value.standard_target_start_date),
        (STANDARD_TARGET_END_DATE_KEY, value.standard_target_end_date),
    ):
        if saved_date is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = saved_date
    st.session_state[STANDARD_TARGET_SHOW_DETAIL_KEY] = value.standard_target_show_detail
    st.session_state[STANDARD_TARGET_DETAIL_LEVEL_KEY] = value.standard_target_detail_level
    st.session_state[STANDARD_TARGET_OUTPUT_METRIC_KEY] = value.standard_target_output_metric
    return True


def _current_month_range() -> tuple[int, int]:
    default = (format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END))
    value = st.session_state.get(MONTH_RANGE_KEY, default)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        value = default
    try:
        start_month = int(str(value[0]).replace("-", ""))
        end_month = int(str(value[1]).replace("-", ""))
    except ValueError as exc:
        raise ValueError("조회기간은 YYYY-MM 형식이어야 합니다.") from exc
    return start_month, end_month


def _session_number(key: str, default: float) -> float:
    value = st.session_state.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"시나리오 프리셋 숫자 설정이 잘못되었습니다: {key}")
    return float(value)


def _session_date(key: str) -> date | None:
    value = st.session_state.get(key)
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _session_text(key: str, default: str) -> str:
    value = st.session_state.get(key)
    if not isinstance(value, str):
        return default
    return value.strip() or default


def _available_processes(reference_tables: Mapping[str, pd.DataFrame]) -> list[str]:
    reqb = reference_tables.get("RQ_REQB")
    if not isinstance(reqb, pd.DataFrame) or "공정" not in reqb.columns:
        raise ValueError("시나리오 프리셋을 저장할 RQ_REQB 공정 정보가 없습니다.")
    return sorted(reqb["공정"].astype("string").str.strip().dropna().unique().tolist())


def _full_data_month_range(
    reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[int, int]:
    ranges = [
        available_month_range(table, table_name)
        for table_name, table in reference_tables.items()
        if isinstance(table, pd.DataFrame) and MONTH_COLUMN in table.columns and not table.empty
    ]
    if not ranges:
        raise ValueError("신규 시나리오의 전체 조회기간을 정할 생산계획년월이 없습니다.")
    return min(start for start, _ in ranges), max(end for _, end in ranges)
