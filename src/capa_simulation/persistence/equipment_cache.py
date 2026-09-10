# Purpose: Streamlit cache boundary for the standalone equipment repository.

"""Streamlit cache boundary for the standalone equipment repository."""

from datetime import datetime
from pathlib import Path
from typing import TypedDict

import pandas as pd
import streamlit as st

from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRevisionSummary,
    EquipmentSnapshot,
)
from capa_simulation.services.floor_layout_profile import (
    FloorLayoutCanvas,
    FloorLayoutProfile,
)


class _FloorLayoutCanvasPayload(TypedDict):
    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    image_name: str | None
    image_byte_count: int
    updated_at: datetime


class _FloorLayoutProfilePayload(TypedDict):
    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    image_data_uri: str | None
    image_name: str | None
    image_byte_count: int
    updated_at: datetime


class _EquipmentRevisionPayload(TypedDict):
    revision_id: str
    revision_no: int
    note: str | None
    baseline_row_count: int
    equipment_row_count: int
    downtime_row_count: int
    created_at: datetime


class _EquipmentSnapshotPayload(TypedDict):
    revision: _EquipmentRevisionPayload
    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame


@st.cache_resource
def get_equipment_repository(database_path: str) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(Path(database_path))
    repository.initialize()
    return repository


@st.cache_data(show_spinner=False, max_entries=16)
def _load_equipment_snapshot_payload(
    database_path: str,
    revision_id: str,
) -> _EquipmentSnapshotPayload:
    snapshot = get_equipment_repository(database_path).load_snapshot(revision_id)
    revision = snapshot.revision
    return {
        "revision": {
            "revision_id": revision.revision_id,
            "revision_no": revision.revision_no,
            "note": revision.note,
            "baseline_row_count": revision.baseline_row_count,
            "equipment_row_count": revision.equipment_row_count,
            "downtime_row_count": revision.downtime_row_count,
            "created_at": revision.created_at,
        },
        "baseline": snapshot.baseline,
        "equipment": snapshot.equipment,
        "downtime": snapshot.downtime,
    }


def load_equipment_snapshot(database_path: str, revision_id: str) -> EquipmentSnapshot:
    """Load one immutable revision through a hot-reload-safe payload cache."""
    payload = _load_equipment_snapshot_payload(database_path, revision_id)
    revision = payload["revision"]
    return EquipmentSnapshot(
        revision=EquipmentRevisionSummary(
            revision_id=revision["revision_id"],
            revision_no=revision["revision_no"],
            note=revision["note"],
            baseline_row_count=revision["baseline_row_count"],
            equipment_row_count=revision["equipment_row_count"],
            downtime_row_count=revision["downtime_row_count"],
            created_at=revision["created_at"],
        ),
        baseline=payload["baseline"],
        equipment=payload["equipment"],
        downtime=payload["downtime"],
    )


def load_latest_equipment_snapshot(database_path: str) -> EquipmentSnapshot | None:
    """Resolve the current id cheaply and cache only the immutable snapshot body."""
    revision_id = get_equipment_repository(database_path).latest_revision_id()
    if revision_id is None:
        return None
    return load_equipment_snapshot(database_path, revision_id)


@st.cache_data(show_spinner=False, max_entries=8)
def _load_floor_layout_summaries_payload(database_path: str) -> list[_FloorLayoutCanvasPayload]:
    return [
        {
            "building": summary.building,
            "floor": summary.floor,
            "canvas_width": summary.canvas_width,
            "canvas_height": summary.canvas_height,
            "image_name": summary.image_name,
            "image_byte_count": summary.image_byte_count,
            "updated_at": summary.updated_at,
        }
        for summary in get_equipment_repository(database_path).load_floor_layout_summaries()
    ]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_floor_layout_profile_payload(
    database_path: str,
    building: str,
    floor: str,
) -> _FloorLayoutProfilePayload | None:
    profile = get_equipment_repository(database_path).load_floor_layout_profile(building, floor)
    if profile is None:
        return None
    return {
        "building": profile.building,
        "floor": profile.floor,
        "canvas_width": profile.canvas_width,
        "canvas_height": profile.canvas_height,
        "image_data_uri": profile.image_data_uri,
        "image_name": profile.image_name,
        "image_byte_count": profile.image_byte_count,
        "updated_at": profile.updated_at,
    }


def load_floor_layout_summaries(database_path: str) -> tuple[FloorLayoutCanvas, ...]:
    """Load every stored floor canvas without the drawing bytes."""
    return tuple(
        FloorLayoutCanvas(**payload)
        for payload in _load_floor_layout_summaries_payload(database_path)
    )


def load_floor_layout_canvases(database_path: str) -> dict[tuple[str, str], tuple[float, float]]:
    """Map (동, 층) to its canvas size for coordinate checks and figure ranges."""
    return {
        (summary.building, summary.floor): summary.canvas_size
        for summary in load_floor_layout_summaries(database_path)
    }


def load_floor_layout_profile(
    database_path: str,
    building: str,
    floor: str,
) -> FloorLayoutProfile | None:
    """Load one floor's canvas and drawing data URI through the payload cache."""
    payload = _load_floor_layout_profile_payload(database_path, building, floor)
    if payload is None:
        return None
    return FloorLayoutProfile(**payload)


def clear_floor_layout_cache() -> None:
    """도면은 설비 리비전과 무관하므로 스냅샷 캐시는 함께 비우지 않는다."""
    _load_floor_layout_summaries_payload.clear()
    _load_floor_layout_profile_payload.clear()


def clear_equipment_snapshot_cache() -> None:
    _load_equipment_snapshot_payload.clear()


def clear_equipment_repository() -> None:
    clear_equipment_snapshot_cache()
    clear_floor_layout_cache()
    get_equipment_repository.clear()
