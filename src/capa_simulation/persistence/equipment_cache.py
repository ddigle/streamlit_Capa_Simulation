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


def clear_equipment_snapshot_cache() -> None:
    _load_equipment_snapshot_payload.clear()


def clear_equipment_repository() -> None:
    clear_equipment_snapshot_cache()
    get_equipment_repository.clear()
