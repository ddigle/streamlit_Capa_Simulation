# Purpose: Capture and restore revision-owned Streamlit sidebar presets.

"""Capture and restore revision-owned Streamlit sidebar presets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pandas as pd
import streamlit as st

from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.services.month_filter import MONTH_COLUMN, available_month_range
from capa_simulation.settings import MONTH_SELECTION_END, MONTH_SELECTION_START, format_month

PENDING_PRESET_KEY = "pending_scenario_preset"
MONTH_RANGE_KEY = "production_month_range_v2"
MONTH_PICKER_KEY = "production_month_picker"
PROCESS_SELECTION_KEY = "dashboard_bottleneck_process_selection"
SECURE_THRESHOLD_KEY = "dashboard_secure_threshold_percent"
WARNING_THRESHOLD_KEY = "dashboard_warning_threshold_percent"
STANDARD_TARGET_PROCESS_SELECTION_KEY = "standard_target_process_filter"
STANDARD_TARGET_PROCESS_DEFAULT_KEY = "standard_target_process_default"


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
    secure_percent = _session_number(SECURE_THRESHOLD_KEY, 109.5)
    warning_percent = _session_number(WARNING_THRESHOLD_KEY, 99.5)
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
