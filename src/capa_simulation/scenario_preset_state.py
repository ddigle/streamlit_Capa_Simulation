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

PENDING_PRESET_KEY = "pending_scenario_preset"
MONTH_RANGE_KEY = "production_month_range_v2"
MONTH_PICKER_KEY = "production_month_picker"
PROCESS_SELECTION_KEY = "dashboard_bottleneck_process_selection"
SECURE_THRESHOLD_KEY = "dashboard_secure_threshold_percent"
WARNING_THRESHOLD_KEY = "dashboard_warning_threshold_percent"
# 위 두 키는 **레거시**다(2026-10-06 사용자 결정). 판정 기준은 이제 HOME → Preference 의 공용
# 프로필(`services/securement_threshold`)이 정하고, 리비전 프리셋의 `secure_threshold`·
# `warning_threshold` 는 판정에 쓰지 않는다. 저장 구조를 바꾸지 않으려고 프리셋 값만 세션을 거쳐
# 그대로 다음 리비전에 실어 보낸다 — 화면 위젯은 없다. 세션이 비어 있으면 아래 기본값을 싣는다.
DEFAULT_SECURE_THRESHOLD_PERCENT = 109.5
DEFAULT_WARNING_THRESHOLD_PERCENT = 99.5
STANDARD_TARGET_PROCESS_SELECTION_KEY = "standard_target_process_filter"
STANDARD_TARGET_PROCESS_DEFAULT_KEY = "standard_target_process_default"
# 표준 목표 Capa 「조회·집계 설정」도 리비전 프리셋이 소유하므로 세션 키를 여기서 선언한다.
STANDARD_TARGET_START_DATE_KEY = "standard_target_start_date"
STANDARD_TARGET_END_DATE_KEY = "standard_target_end_date"
STANDARD_TARGET_SHOW_DETAIL_KEY = "standard_target_show_detail"
STANDARD_TARGET_DETAIL_LEVEL_KEY = "standard_target_detail_level"
STANDARD_TARGET_OUTPUT_METRIC_KEY = "standard_target_output_metric"


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
