# Purpose: Typed values exchanged with the DuckDB scenario repository.

"""Typed values exchanged with the DuckDB scenario repository."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from capa_simulation.persistence._sql_helpers import required_text

# 표준 목표 Capa 조회·집계 설정의 저장 기본값. 화면 옵션 목록은 페이지가 소유하고,
# 값이 비었을 때 되돌아갈 기본값만 프리셋과 함께 여기에 둔다.
DEFAULT_STANDARD_TARGET_DETAIL_LEVEL = "제품정보"
DEFAULT_STANDARD_TARGET_OUTPUT_METRIC = "일 표준 가능량"


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


@dataclass(frozen=True)
class GlobalComparisonScenario:
    """Scenario-independent choice of the GAP comparison target.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 두 식별자가 `None` 이다.

    비교 **토글**은 여기 담지 않는다. 켜고 끄는 것은 지금 보는 사람의 상태이고, 시나리오를
    바꾸면 꺼지는 값이라 공용으로 남기면 남의 화면까지 켜진다.
    """

    version: int
    source: str
    updated_at: datetime | None
    scenario_id: str | None
    revision_id: str | None


@dataclass(frozen=True)
class GlobalAdvanceLoad:
    """Scenario-independent advance-load profile in 억Gb per plan month.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 행 0건이다.
    """

    version: int
    source: str
    updated_at: datetime | None
    rows: pd.DataFrame


@dataclass(frozen=True)
class GlobalTop5Band:
    """Scenario-independent securement band for the B/N Top 5 bar heights.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 그리고 서비스 기본값(50%~200%)이다.
    """

    version: int
    source: str
    updated_at: datetime | None
    min_rate: float
    max_rate: float

    @property
    def band(self) -> tuple[float, float]:
        return self.min_rate, self.max_rate


@dataclass(frozen=True)
class GlobalKeyProcess:
    """Scenario-independent list of key processes for the HOME securement heatmap.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 빈 목록이다.

    **빈 목록은 「하나도 안 고름」이라는 결정**이라 미저장과 화면은 같지만 저장 쪽은
    누가 언제 비웠는지 보여 줄 수 있어야 한다. 그래서 0건도 version 이 올라간다.

    `rows: pd.DataFrame` 이 아니라 tuple 인 것은 이 값이 그대로 Figure 캐시 키의 원소가
    되기 때문이다. 프레임으로 두면 rerun 마다 tuple 로 되만드는 코드가 호출부에 흩어진다.
    """

    version: int
    source: str
    updated_at: datetime | None
    processes: tuple[str, ...]


@dataclass(frozen=True)
class GlobalSummaryNote:
    """Scenario-independent notice shown at the top of HOME.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 빈 문자열이다.

    **빈 문자열과 미저장을 구분한다.** 빈 문자열은 「공지를 내렸다」는 결정이고 미저장은
    아직 아무도 손대지 않은 상태다. 화면은 둘 다 아무것도 띄우지 않지만, 저장 화면은
    마지막에 누가 언제 내렸는지를 보여 줄 수 있어야 한다.
    """

    version: int
    source: str
    updated_at: datetime | None
    note: str

    @property
    def is_visible(self) -> bool:
        """화면에 띄울 내용이 있는지. 공백뿐인 글은 띄우지 않는다."""
        return bool(self.note.strip())


@dataclass(frozen=True)
class GlobalExecutionCapacity:
    """Scenario-independent execution-capacity profile in percentage points.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 행 0건이다.

    `rows` 의 `증감 확보율` 단위는 **퍼센트포인트**다(105% 에 -10 이면 95%).
    """

    version: int
    source: str
    updated_at: datetime | None
    rows: pd.DataFrame


@dataclass(frozen=True)
class GlobalPastData:
    """Scenario-independent past-period profile: monthly totals, plan detail, rates.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 세 표 모두 0건이다.
    """

    version: int
    source: str
    updated_at: datetime | None
    monthly: pd.DataFrame
    plan_detail: pd.DataFrame
    securement: pd.DataFrame


def _optional_date(value: date | None) -> date | None:
    """Normalize one optional stored date without rejecting a persisted revision."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError("표준 목표 Capa 조회일은 date 값이어야 합니다.")


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass(frozen=True)
class ScenarioPreset:
    """Reproducible sidebar filters stored with one immutable revision."""

    start_month: int
    end_month: int
    included_processes: tuple[str, ...]
    secure_threshold: float = 1.095
    warning_threshold: float = 0.995
    schema_version: int = 3
    standard_target_processes: tuple[str, ...] = ()
    # 표준 목표 Capa 「조회·집계 설정」. 날짜는 사이드바 조회기간에서 파생되므로
    # "저장값 없음"(None)과 특정 날짜를 구분한다.
    standard_target_start_date: date | None = None
    standard_target_end_date: date | None = None
    standard_target_show_detail: bool = False
    standard_target_detail_level: str = DEFAULT_STANDARD_TARGET_DETAIL_LEVEL
    standard_target_output_metric: str = DEFAULT_STANDARD_TARGET_OUTPUT_METRIC

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

        for field_name in ("standard_target_start_date", "standard_target_end_date"):
            object.__setattr__(self, field_name, _optional_date(getattr(self, field_name)))
        # 저장 시점에 유효했던 값이라 읽기가 실패하면 리비전을 영영 열 수 없다.
        # 앞뒤가 뒤집힌 조회일은 예외 대신 종료일을 시작일에 맞춰 바로잡는다.
        if (
            self.standard_target_start_date is not None
            and self.standard_target_end_date is not None
            and self.standard_target_start_date > self.standard_target_end_date
        ):
            object.__setattr__(self, "standard_target_end_date", self.standard_target_start_date)
        object.__setattr__(
            self,
            "standard_target_detail_level",
            str(self.standard_target_detail_level).strip() or DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
        )
        object.__setattr__(
            self,
            "standard_target_output_metric",
            str(self.standard_target_output_metric).strip()
            or DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
        )
        object.__setattr__(
            self, "standard_target_show_detail", bool(self.standard_target_show_detail)
        )

    def digest(self) -> str:
        payload = {
            "end_month": self.end_month,
            "included_processes": self.included_processes,
            "schema_version": self.schema_version,
            "secure_threshold": self.secure_threshold,
            "standard_target_detail_level": self.standard_target_detail_level,
            "standard_target_end_date": _date_text(self.standard_target_end_date),
            "standard_target_output_metric": self.standard_target_output_metric,
            "standard_target_processes": self.standard_target_processes,
            "standard_target_show_detail": self.standard_target_show_detail,
            "standard_target_start_date": _date_text(self.standard_target_start_date),
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
            object.__setattr__(self, field_name, required_text(getattr(self, field_name), label))
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
