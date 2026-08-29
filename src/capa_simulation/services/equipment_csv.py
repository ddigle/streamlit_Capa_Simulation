"""CSV templates, parsing, and ID-based merge for equipment operations."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from capa_simulation.services.equipment_availability import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_master,
    prepare_downtime_schedule,
    prepare_equipment_master,
)


def equipment_csv_template() -> bytes:
    return _to_csv_bytes(empty_equipment_master())


def downtime_csv_template() -> bytes:
    return _to_csv_bytes(empty_downtime_schedule())


def read_equipment_csv(payload: bytes) -> pd.DataFrame:
    return prepare_equipment_master(_read_csv(payload, EQUIPMENT_COLUMNS, "호기 마스터"))


def read_downtime_csv(payload: bytes, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _read_csv(payload, DOWNTIME_COLUMNS, "비가동 일정"),
        equipment=equipment,
    )


def merge_equipment_rows(current: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    return prepare_equipment_master(_merge_by_key(current, incoming, "호기"))


def merge_downtime_rows(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    equipment: pd.DataFrame,
) -> pd.DataFrame:
    merged = _merge_by_key(current, incoming, "비가동ID")
    return prepare_downtime_schedule(merged, equipment=equipment)


def _read_csv(payload: bytes, columns: tuple[str, ...], label: str) -> pd.DataFrame:
    if not payload:
        raise ValueError(f"{label} CSV 파일이 비어 있습니다.")
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            frame = pd.read_csv(BytesIO(payload), encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"{label} CSV 인코딩은 UTF-8 또는 CP949여야 합니다.") from last_error
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} CSV 필수 컬럼이 없습니다: {', '.join(missing)}")
    return frame.loc[:, columns]


def _merge_by_key(current: pd.DataFrame, incoming: pd.DataFrame, key: str) -> pd.DataFrame:
    if incoming.empty:
        return current.copy().reset_index(drop=True)
    current_without_updates = current.loc[~current[key].isin(incoming[key])]
    return pd.concat([current_without_updates, incoming], ignore_index=True)


def _to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")
