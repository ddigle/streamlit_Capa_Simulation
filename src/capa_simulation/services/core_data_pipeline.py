# Purpose: Shared Core Data preparation path for CSV and internal database providers.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

"""Shared Core Data preparation path for CSV and internal database providers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    CoreDataProvider,
    normalize_core_data,
)
from capa_simulation.services.reference_transformer import (
    TEMPORARY_CONFLICT_RESOLUTION,
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
    """One normalized source snapshot and its 16 derived reference tables."""

    batch: CoreDataBatch
    source_data: pd.DataFrame
    reference_tables: dict[str, pd.DataFrame]
    reference_conflicts: pd.DataFrame


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
    required = ["RQ테이블", "충돌행수", "임시제외행수"]
    missing = [column for column in required if column not in conflicts.columns]
    if missing:
        raise ValueError(f"RQ 충돌 보고서 필수 컬럼이 없습니다: {', '.join(missing)}")
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
