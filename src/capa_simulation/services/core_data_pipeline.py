# Purpose: Shared Core Data preparation path for CSV and internal database providers.

"""Shared Core Data preparation path for CSV and internal database providers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    CoreDataProvider,
    normalize_core_data,
)
from capa_simulation.services.core_data_derivation import BlankCsDrop
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.reference_conflicts import TEMPORARY_CONFLICT_RESOLUTION
from capa_simulation.services.reference_transformer import (
    build_reference_tables_with_conflicts,
)

CONFLICT_SUMMARY_COLUMNS = [
    "RQ테이블",
    "충돌 업무키 그룹수",
    "충돌 원천행수",
    "임시 제외행수",
    "임시처리",
]


@dataclass(frozen=True)
class PreparedCoreDataset:
    """정규화한 원천 스냅샷 하나와 그 16개 파생 기준정보 표.

    `source_data` 는 받은 행 그대로이고, `blank_cs` 는 CS 가 비어 표에서만 뺀 행 수다 — 등록
    경로가 결과 알림과 리비전 메모에 싣는다.
    """

    batch: CoreDataBatch
    source_data: pd.DataFrame
    reference_tables: dict[str, pd.DataFrame]
    reference_conflicts: pd.DataFrame
    blank_cs: BlankCsDrop = field(default_factory=BlankCsDrop)


def prepare_core_data_dataset(
    batch: CoreDataBatch,
    display_order: pd.DataFrame,
) -> PreparedCoreDataset:
    """Normalize, validate, and transform a provider result without CSV coupling."""
    normalized = normalize_core_data(batch.frame)
    build_result = build_reference_tables_with_conflicts(normalized, display_order)
    return PreparedCoreDataset(
        batch=batch,
        source_data=normalized,
        reference_tables=build_result.tables,
        reference_conflicts=build_result.conflicts,
        blank_cs=build_result.blank_cs,
    )


def fetch_core_data_dataset(
    provider: CoreDataProvider,
    simulation_code: str,
    display_order: pd.DataFrame,
) -> PreparedCoreDataset:
    """Fetch a simulation code and send it through the common preparation path."""
    return prepare_core_data_dataset(provider.fetch(simulation_code), display_order)


def summarize_reference_conflicts(conflicts: pd.DataFrame) -> pd.DataFrame:
    """Summarize temporary business-key conflict resolution by RQ table."""
    if conflicts.empty:
        return pd.DataFrame(columns=CONFLICT_SUMMARY_COLUMNS)
    require_columns(conflicts, ["RQ테이블", "충돌행수", "임시제외행수"], "RQ 충돌 보고서")
    summary = (
        conflicts.groupby("RQ테이블", sort=False, as_index=False)
        .agg(
            **{
                "충돌 업무키 그룹수": ("충돌그룹", "size"),
                "충돌 원천행수": ("충돌행수", "sum"),
                "임시 제외행수": ("임시제외행수", "sum"),
            }
        )
        .reset_index(drop=True)
    )
    summary["임시처리"] = TEMPORARY_CONFLICT_RESOLUTION
    return summary[CONFLICT_SUMMARY_COLUMNS]


def reference_conflicts_to_csv(conflicts: pd.DataFrame) -> bytes:
    """Encode the complete conflict report for direct Excel-compatible download."""
    return conflicts.to_csv(index=False).encode("utf-8-sig")
