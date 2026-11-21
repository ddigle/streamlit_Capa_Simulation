# Purpose: Shared Core Data preparation path for CSV and internal database providers.

"""Shared Core Data preparation path for CSV and internal database providers."""

from __future__ import annotations

import logging
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
from capa_simulation.services.reference_conflicts import (
    CONFLICT_CAUSE_COLUMN,
    OTHER_CONFLICT_CAUSE,
    conflict_resolution,
)
from capa_simulation.services.reference_transformer import (
    build_reference_tables_with_conflicts,
)

_LOGGER = logging.getLogger(__name__)

CONFLICT_SUMMARY_COLUMNS = [
    "RQ테이블",
    "충돌 업무키 그룹수",
    "키밖 갈림 그룹수",
    "그 밖 갈림 그룹수",
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

    합치기가 예외로 끝나면(검사가 엄해졌거나 원천 꼴이 바뀌어 규칙 밖 값이 닿음) 판 없이 BDQ 만으로
    등록하고 로그와 메모 조각(「부대공정 판 n · 합치지 못함」)을 남긴다 — 판을 끌 때까지 등록 · 자동
    갱신 공식 지정이 멈추지 않게(설계 D10 「맞물리지 않는 부대공정만 빼고 나머지는 등록」).
    """
    if extra is None:
        return RegistrationDataset(prepared)
    try:
        result = merge_extra_processes(prepared.reference_tables, extra, check=check)
    except Exception as exc:  # noqa: BLE001 — 판 탓의 어떤 예외도 BDQ 등록을 막지 않는다(위 설명).
        _LOGGER.exception(
            "부대공정 판(%s)을 합치지 못해 BDQ 만으로 등록합니다(%s).",
            extra.version.version_no,
            type(exc).__name__,
        )
        return RegistrationDataset(
            prepared, ExtraMergeReport(version=extra.version, failed=type(exc).__name__)
        )
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
    """RQ 표마다 업무 키 충돌을 센다 — 업무 키 밖 구분 칸으로 갈린 그룹(「키밖」)과 그 밖을 나눈다.

    「키밖구분」 칸이 없는 옛 꼴 보고서도 받는다 — 그때 두 칸은 빈 값이다(원인을 모른다).
    """
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
    other_counts, out_of_key_counts = conflict_cause_counts(conflicts)
    summary["키밖 갈림 그룹수"] = summary["RQ테이블"].map(out_of_key_counts).astype("Int64")
    summary["그 밖 갈림 그룹수"] = summary["RQ테이블"].map(other_counts).astype("Int64")
    summary["임시처리"] = summary["RQ테이블"].map(conflict_resolution)
    return summary[CONFLICT_SUMMARY_COLUMNS]


def conflict_cause_counts(conflicts: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """RQ 표마다 (「그 밖」 그룹 수, 키밖 그룹 수). 「키밖구분」 칸이 없으면 둘 다 빈 Series 다."""
    if CONFLICT_CAUSE_COLUMN not in conflicts.columns:
        empty = pd.Series(dtype="Int64")
        return empty, empty
    other = conflicts[CONFLICT_CAUSE_COLUMN].astype("string").eq(OTHER_CONFLICT_CAUSE)
    tables = conflicts["RQ테이블"]
    return (
        other.groupby(tables, sort=False).sum().astype("Int64"),
        (~other).groupby(tables, sort=False).sum().astype("Int64"),
    )


def reference_conflict_memo(conflicts: pd.DataFrame) -> str:
    """리비전 · 실행 기록 메모에 붙이는 충돌 조각 — 「업무 키 충돌 n그룹(키밖 a · 그 밖 b)」.

    충돌이 없으면 빈 글이고, 원인 칸이 없는 옛 꼴 보고서면 괄호를 붙이지 않는다.
    """
    if conflicts.empty:
        return ""
    memo = f"업무 키 충돌 {len(conflicts):,}그룹"
    other, out_of_key = conflict_cause_counts(conflicts)
    if other.empty and out_of_key.empty:
        return memo
    return f"{memo}(키밖 {int(out_of_key.sum()):,} · 그 밖 {int(other.sum()):,})"


def reference_conflicts_to_csv(conflicts: pd.DataFrame) -> bytes:
    """Encode the complete conflict report for direct Excel-compatible download."""
    return conflicts.to_csv(index=False).encode("utf-8-sig")
