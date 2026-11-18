# Purpose: Shared Core Data preparation path for CSV and internal database providers.

"""Shared Core Data preparation path for CSV and internal database providers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    CoreDataProvider,
    normalize_core_data,
)
from capa_simulation.services.core_data_derivation import BlankCsDrop
from capa_simulation.services.extra_process_merge import (
    ActiveExtraPack,
    CapacityCheck,
    ExtraMergeReport,
    capacity_stop,
    merge_extra_processes,
)
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.reference_conflicts import conflict_resolution
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


@dataclass(frozen=True)
class RegistrationDataset:
    """등록에 쓸 원천 한 벌 — 부대공정 판을 합친 16표(`prepared`)와 그 합치기 보고(`extra`)."""

    prepared: PreparedCoreDataset
    extra: ExtraMergeReport = field(default_factory=ExtraMergeReport)


def merge_registration_dataset(
    prepared: PreparedCoreDataset,
    extra: ActiveExtraPack | None,
    *,
    check: CapacityCheck = capacity_stop,
) -> RegistrationDataset:
    """변환을 마친 원천 16표에 DB 의 활성 부대공정 판을 합친다(등록 이음매 — ② 뒤 · ③ 앞).

    원천(`source_data`)과 원천 해시는 그대로이고 기준정보 표에만 더한다. 등록 점검(R-07 —
    소요대수 · 확보율까지)도 이 안에서 프리셋보다 앞에 돈다 — 부르는 쪽은 돌려준 표로 프리셋을
    만든다(설계 D21). 판이 없으면 표를 그대로 둔다.
    """
    if extra is None:
        return RegistrationDataset(prepared)
    result = merge_extra_processes(prepared.reference_tables, extra, check=check)
    return RegistrationDataset(replace(prepared, reference_tables=result.tables), result.report)


def fetch_registration_dataset(
    provider: CoreDataProvider,
    simulation_code: str,
    display_order: pd.DataFrame,
    extra: ActiveExtraPack | None,
) -> RegistrationDataset:
    """화면 등록과 공식버전 자동 갱신이 함께 부르는 등록 원천 — 조회 · 변환 뒤 부대공정 판을 합친다.

    `extra` 는 DB 에 적용된 활성 판이다 — S3 를 읽지 않는다(자동 갱신 결과가 그날의 S3 상태에
    따라 조용히 바뀌지 않게, 설계 3-4).
    """
    prepared = fetch_core_data_dataset(provider, simulation_code, display_order)
    return merge_registration_dataset(prepared, extra)


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
    summary["임시처리"] = summary["RQ테이블"].map(conflict_resolution)
    return summary[CONFLICT_SUMMARY_COLUMNS]


def reference_conflicts_to_csv(conflicts: pd.DataFrame) -> bytes:
    """Encode the complete conflict report for direct Excel-compatible download."""
    return conflicts.to_csv(index=False).encode("utf-8-sig")
