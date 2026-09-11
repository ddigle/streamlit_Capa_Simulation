# Purpose: Streamlit cache boundary for the shared DuckDB repository configuration.

"""Streamlit cache boundary for the shared DuckDB repository configuration."""

from datetime import date, datetime
from pathlib import Path
from typing import TypedDict

import pandas as pd
import streamlit as st

from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalDisplayOrder,
    GlobalProcessRename,
    RevisionSummary,
    ScenarioPreset,
    ScenarioSnapshot,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository


class _ScenarioSummaryPayload(TypedDict):
    scenario_id: str
    dataset_id: str
    scenario_name: str
    source_simulation_code: str
    source_simulation_name: str
    source_type: str
    status: str
    active_revision_id: str
    active_revision_no: int
    created_at: datetime
    updated_at: datetime


class _RevisionSummaryPayload(TypedDict):
    revision_id: str
    scenario_id: str
    revision_no: int
    revision_name: str
    parent_revision_id: str | None
    note: str | None
    reference_hash: str
    created_at: datetime


class _ScenarioPresetPayload(TypedDict):
    start_month: int
    end_month: int
    included_processes: tuple[str, ...]
    secure_threshold: float
    warning_threshold: float
    schema_version: int
    standard_target_processes: tuple[str, ...]
    standard_target_start_date: date | None
    standard_target_end_date: date | None
    standard_target_show_detail: bool
    standard_target_detail_level: str
    standard_target_output_metric: str


class _ScenarioSnapshotPayload(TypedDict):
    scenario: _ScenarioSummaryPayload
    revision: _RevisionSummaryPayload
    preset: _ScenarioPresetPayload
    tables: dict[str, pd.DataFrame]


class _GlobalDisplayOrderPayload(TypedDict):
    version: int
    source: str
    updated_at: datetime
    rules: pd.DataFrame


class _GlobalProcessRenamePayload(TypedDict):
    version: int
    source: str
    updated_at: datetime | None
    rules: pd.DataFrame


class _GlobalAdvanceLoadPayload(TypedDict):
    version: int
    source: str
    updated_at: datetime | None
    rows: pd.DataFrame


@st.cache_resource
def get_scenario_repository(database_path: str) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    repository.initialize_global_display_order(load_builtin_display_order())
    return repository


def _snapshot_to_payload(snapshot: ScenarioSnapshot) -> _ScenarioSnapshotPayload:
    """Detach cache data from reload-sensitive application model instances."""
    scenario = snapshot.scenario
    revision = snapshot.revision
    preset = snapshot.preset
    return {
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "dataset_id": scenario.dataset_id,
            "scenario_name": scenario.scenario_name,
            "source_simulation_code": scenario.source_simulation_code,
            "source_simulation_name": scenario.source_simulation_name,
            "source_type": scenario.source_type,
            "status": scenario.status,
            "active_revision_id": scenario.active_revision_id,
            "active_revision_no": scenario.active_revision_no,
            "created_at": scenario.created_at,
            "updated_at": scenario.updated_at,
        },
        "revision": {
            "revision_id": revision.revision_id,
            "scenario_id": revision.scenario_id,
            "revision_no": revision.revision_no,
            "revision_name": revision.revision_name,
            "parent_revision_id": revision.parent_revision_id,
            "note": revision.note,
            "reference_hash": revision.reference_hash,
            "created_at": revision.created_at,
        },
        "preset": {
            "start_month": preset.start_month,
            "end_month": preset.end_month,
            "included_processes": preset.included_processes,
            "secure_threshold": preset.secure_threshold,
            "warning_threshold": preset.warning_threshold,
            "schema_version": preset.schema_version,
            "standard_target_processes": preset.standard_target_processes,
            "standard_target_start_date": preset.standard_target_start_date,
            "standard_target_end_date": preset.standard_target_end_date,
            "standard_target_show_detail": preset.standard_target_show_detail,
            "standard_target_detail_level": preset.standard_target_detail_level,
            "standard_target_output_metric": preset.standard_target_output_metric,
        },
        "tables": dict(snapshot.tables),
    }


def _snapshot_from_payload(payload: _ScenarioSnapshotPayload) -> ScenarioSnapshot:
    return ScenarioSnapshot(
        scenario=ScenarioSummary(**payload["scenario"]),
        revision=RevisionSummary(**payload["revision"]),
        preset=ScenarioPreset(**payload["preset"]),
        tables=payload["tables"],
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _load_scenario_snapshot_payload(
    database_path: str,
    revision_id: str,
) -> _ScenarioSnapshotPayload:
    snapshot = get_scenario_repository(database_path).load_revision(revision_id)
    return _snapshot_to_payload(snapshot)


def load_scenario_snapshot(database_path: str, revision_id: str) -> ScenarioSnapshot:
    """Share an immutable revision without caching its reload-sensitive model class."""
    return _snapshot_from_payload(_load_scenario_snapshot_payload(database_path, revision_id))


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_display_order_payload(database_path: str) -> _GlobalDisplayOrderPayload:
    profile = get_scenario_repository(database_path).load_global_display_order()
    return {
        "version": profile.version,
        "source": profile.source,
        "updated_at": profile.updated_at,
        "rules": profile.rules,
    }


def load_global_display_order(database_path: str) -> GlobalDisplayOrder:
    """Share the display order without caching its reload-sensitive model class."""
    payload = _load_global_display_order_payload(database_path)
    return GlobalDisplayOrder(
        version=payload["version"],
        source=payload["source"],
        updated_at=payload["updated_at"],
        rules=payload["rules"],
    )


def clear_global_display_order_cache() -> None:
    _load_global_display_order_payload.clear()
    _load_scenario_snapshot_payload.clear()


def clear_scenario_snapshot_cache() -> None:
    """지운 리비전의 스냅샷이 캐시에 남아 되살아나지 않게 한다."""
    _load_scenario_snapshot_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_process_rename_payload(database_path: str) -> _GlobalProcessRenamePayload:
    profile = get_scenario_repository(database_path).load_global_process_rename()
    return {
        "version": profile.version,
        "source": profile.source,
        "updated_at": profile.updated_at,
        "rules": profile.rules,
    }


def load_global_process_rename(database_path: str) -> GlobalProcessRename:
    """Share the process display-name profile without caching its model class."""
    payload = _load_global_process_rename_payload(database_path)
    return GlobalProcessRename(
        version=payload["version"],
        source=payload["source"],
        updated_at=payload["updated_at"],
        rules=payload["rules"],
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_advance_load_payload(database_path: str) -> _GlobalAdvanceLoadPayload:
    profile = get_scenario_repository(database_path).load_global_advance_load()
    return {
        "version": profile.version,
        "source": profile.source,
        "updated_at": profile.updated_at,
        "rows": profile.rows,
    }


def load_global_advance_load(database_path: str) -> GlobalAdvanceLoad:
    """Share the advance-load profile without caching its model class."""
    payload = _load_global_advance_load_payload(database_path)
    return GlobalAdvanceLoad(
        version=payload["version"],
        source=payload["source"],
        updated_at=payload["updated_at"],
        rows=payload["rows"],
    )


def clear_global_advance_load_cache() -> None:
    """선행 물량 프로필만 비운다.

    표시명과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 선행 물량은 어떤 `RQ_*`
    표에도 오버레이되지 않고 화면 산출 직전에만 곱해진다.
    """
    _load_global_advance_load_payload.clear()


def clear_global_process_rename_cache() -> None:
    """표시명 프로필만 비운다.

    표시순서와 달리 어떤 `RQ_*` 표에도 오버레이되지 않으므로 리비전 스냅샷 캐시는
    건드리지 않는다. 같이 비우면 저장할 때마다 16표 재적재가 딸려온다.
    """
    _load_global_process_rename_payload.clear()


def clear_scenario_repository() -> None:
    _load_global_advance_load_payload.clear()
    _load_global_display_order_payload.clear()
    _load_global_process_rename_payload.clear()
    _load_scenario_snapshot_payload.clear()
    get_scenario_repository.clear()
