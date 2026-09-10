# Purpose: Typed values exchanged with the DuckDB scenario repository.

"""Typed values exchanged with the DuckDB scenario repository."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class GlobalDisplayOrder:
    """Scenario-independent display-order profile shared by every revision."""

    version: int
    source: str
    updated_at: datetime
    rules: pd.DataFrame


@dataclass(frozen=True)
class GlobalProcessRename:
    """Scenario-independent process display-name profile used by the render layer only.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 규칙 0건이다.
    """

    version: int
    source: str
    updated_at: datetime | None
    rules: pd.DataFrame


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
    return normalized


@dataclass(frozen=True)
class ScenarioPreset:
    """Reproducible sidebar filters stored with one immutable revision."""

    start_month: int
    end_month: int
    included_processes: tuple[str, ...]
    secure_threshold: float = 1.095
    warning_threshold: float = 0.995
    schema_version: int = 2
    standard_target_processes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, label in ((self.start_month, "조회 시작월"), (self.end_month, "조회 종료월")):
            if value <= 0 or value % 100 not in range(1, 13):
                raise ValueError(f"{label}은 YYYYMM 형식이어야 합니다.")
        if self.start_month > self.end_month:
            raise ValueError("조회 시작월은 종료월보다 늦을 수 없습니다.")
        if self.warning_threshold < 0:
            raise ValueError("경고 기준은 0 이상이어야 합니다.")
        if self.secure_threshold < self.warning_threshold:
            raise ValueError("확보 기준은 경고 기준보다 작을 수 없습니다.")
        if self.schema_version <= 0:
            raise ValueError("프리셋 스키마 버전은 1 이상이어야 합니다.")

        for field_name, label in (
            ("included_processes", "B/N 포함 공정"),
            ("standard_target_processes", "표준 목표 Capa 공정"),
        ):
            normalized = tuple(process.strip() for process in getattr(self, field_name))
            if any(not process for process in normalized):
                raise ValueError(f"{label}에는 빈 이름을 저장할 수 없습니다.")
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{label}에는 중복값을 저장할 수 없습니다.")
            object.__setattr__(self, field_name, normalized)

    def digest(self) -> str:
        payload = {
            "end_month": self.end_month,
            "included_processes": self.included_processes,
            "schema_version": self.schema_version,
            "secure_threshold": self.secure_threshold,
            "standard_target_processes": self.standard_target_processes,
            "start_month": self.start_month,
            "warning_threshold": self.warning_threshold,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ScenarioCreate:
    """Metadata required to register one immutable source dataset."""

    scenario_name: str
    source_simulation_code: str
    source_simulation_name: str
    source_type: str
    pipeline_version: str
    source_registered_at: datetime | None = None
    source_row_count: int = 0
    source_schema_hash: str | None = None
    source_data_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name, label in (
            ("scenario_name", "시나리오명"),
            ("source_simulation_code", "원천 시뮬레이션 코드"),
            ("source_simulation_name", "원천 시뮬레이션명"),
            ("source_type", "원천 유형"),
            ("pipeline_version", "파이프라인 버전"),
        ):
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), label))
        if self.source_row_count < 0:
            raise ValueError("원천 행 수는 0 이상이어야 합니다.")


@dataclass(frozen=True)
class ScenarioSummary:
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


@dataclass(frozen=True)
class RevisionSummary:
    revision_id: str
    scenario_id: str
    revision_no: int
    revision_name: str
    parent_revision_id: str | None
    note: str | None
    reference_hash: str
    created_at: datetime


@dataclass(frozen=True)
class OfficialReleaseSummary:
    official_release_id: str
    release_no: int
    scenario_id: str
    revision_id: str
    release_name: str
    note: str | None
    scenario_name: str
    source_simulation_code: str
    revision_no: int
    revision_name: str
    published_at: datetime


@dataclass(frozen=True)
class ScenarioSnapshot:
    scenario: ScenarioSummary
    revision: RevisionSummary
    preset: ScenarioPreset
    tables: dict[str, pd.DataFrame]
