# Purpose: Typed values exchanged with the DuckDB scenario repository.

"""Typed values exchanged with the DuckDB scenario repository."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType

import pandas as pd

from capa_simulation.persistence._sql_helpers import required_text
from capa_simulation.services.auto_official_update import (
    AutoUpdateConfig,
    ExclusionKind,
    RunStatus,
    TriggerKind,
)
from capa_simulation.services.korean_particle import with_topic_particle
from capa_simulation.services.securement_threshold import (
    SecurementThresholds,
    build_securement_thresholds,
)

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
class GlobalMainCases:
    """HOME 주요 Case(Case1·Case2)로 지정한 시나리오·리비전 짝 둘(마이그레이션 0036).

    슬롯은 셋으로 고정이고 슬롯 1 은 늘 지금 최신 공식버전이라 여기 담지 않는다 — 공식 지정은
    시나리오 관리 한 곳이다. 프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 네 식별자가 `None` 이다. 리비전만 있고 시나리오가 없는 짝은 저장하지 않는다.
    """

    version: int
    source: str
    updated_at: datetime | None
    case1_scenario_id: str | None = None
    case1_revision_id: str | None = None
    case2_scenario_id: str | None = None
    case2_revision_id: str | None = None

    def case(self, case_no: int) -> tuple[str | None, str | None]:
        """Case 번호(1·2)의 (시나리오 id, 리비전 id)."""
        if case_no == 1:
            return self.case1_scenario_id, self.case1_revision_id
        if case_no == 2:
            return self.case2_scenario_id, self.case2_revision_id
        raise ValueError(f"주요 Case 번호는 1·2 뿐입니다: {case_no}")


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
class GlobalAdvanceShipment:
    """Scenario-independent 선행 입고 실적 profile in 억Gb per plan month (display only).

    선행 B/O(`GlobalAdvanceLoad`)와 같은 모양이다. 생산계획에 이미 든 물량이라 계산에 들어가지
    않고 HOME `Capa LOB 현황` Density 칸에 값만 적는다. 프로필이 한 번도 저장되지 않은 상태가
    정상이다. 그때는 `version=0`, `updated_at=None`, 행 0건이다.
    """

    version: int
    source: str
    updated_at: datetime | None
    rows: pd.DataFrame


@dataclass(frozen=True)
class GlobalSecurementThreshold:
    """Scenario-independent securement thresholds: a default pair plus monthly overrides.

    값은 비율이다(110% 는 1.1). 판정은 사사오입 정수 % 기준으로 읽는다 — 옛 저장값 1.095 도
    110% 다(`thresholds` 가 맞춘다, `securement_threshold.normalize_threshold`). `rows` 는
    `생산계획년월`·`확보 기준`·`경고 기준` 이고 빈 칸은 그 달 그 항목이 기본값을 따른다는 뜻이다.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`, `updated_at=None`,
    행 0건이고 기본값은 **최신 공식버전 리비전 프리셋의 값**(그것도 없으면 코드 기본값)이다 —
    `fallback` 이 그 출처를 말한다. 저장하기 전에는 DB 에 쓰지 않는다.
    """

    version: int
    source: str
    updated_at: datetime | None
    default_secure: float
    default_warning: float
    rows: pd.DataFrame
    fallback: str = ""

    @property
    def thresholds(self) -> SecurementThresholds:
        """판정에 넘길 해시 가능한 값. 달마다의 실효 기준은 `for_month` 가 답한다."""
        return build_securement_thresholds(self.default_secure, self.default_warning, self.rows)


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
    """Scenario-independent key-process presets for the HOME securement heatmap.

    **이름 붙은 프리셋 여럿**이다(2026-09-29 사용자 요청 — 「A 그룹은 A·B·C·D, B 그룹은
    D·E·F·G」). `presets` 는 `(이름, 공정들)` 의 차례 있는 묶음이고 **첫 프리셋이 기본**이다 —
    HOME 사이드바에서 아직 고르지 않은 세션이 그것을 본다. 한 공정이 여러 프리셋에 들 수 있다.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`, `updated_at=None`,
    빈 묶음이다. 프리셋을 모두 지운 저장도 version 이 오른다 — 캐시가 version 을 본다.

    `rows: pd.DataFrame` 이 아니라 tuple 인 것은 이 값이 그대로 Figure 캐시 키의 원소가
    되기 때문이다. 프레임으로 두면 rerun 마다 tuple 로 되만드는 코드가 호출부에 흩어진다.
    """

    version: int
    source: str
    updated_at: datetime | None
    presets: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def preset_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.presets)

    def processes_of(self, name: str | None) -> tuple[str, ...]:
        """그 프리셋의 공정. 없는 이름이면 빈 묶음이다."""
        return next((processes for preset, processes in self.presets if preset == name), ())


@dataclass(frozen=True)
class GlobalProcessGroup:
    """HOME 공정 필터 그룹 단추가 쓰는 공정 → 공정 그룹 대응(시나리오 독립 공용 프로필, 계산 밖).

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`, `updated_at=None`, 빈
    대응이다. 대응을 모두 비운 저장도 version 이 오른다 — 캐시가 version 을 본다.

    주요공정 프리셋과 같은 까닭으로 프레임이 아니라 tuple 이다 — 해시되는 값이고 화면이 프레임을
    다시 만들 일이 없다.
    """

    version: int
    source: str
    updated_at: datetime | None
    # (원본 공정, 공정 그룹) — 저장 차례는 공정 글자순. 한 공정은 한 번만 나온다.
    assignments: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class GlobalSummaryNote:
    """Scenario-independent notice shown at the top of HOME.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`,
    `updated_at=None`, 빈 문자열이다.

    **빈 문자열과 미저장을 구분한다.** 빈 문자열은 「Capa 요약을 내렸다」는 결정이고 미저장은
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


@dataclass(frozen=True)
class AutoOfficialUpdateSettings:
    """Scenario-independent settings of the automatic official-version update.

    프로필이 한 번도 저장되지 않은 상태가 정상이다. 그때는 `version=0`, `updated_at=None`, 설정은
    코드 기본값(꺼짐 · 07:00 · `PSM` · 80%)이다. 저장하기 전에는 DB 에 쓰지 않는다.
    """

    version: int
    source: str
    updated_at: datetime | None
    config: AutoUpdateConfig


@dataclass(frozen=True)
class AutoOfficialUpdateSettingChange:
    """설정 변경 한 건 — 언제·무엇을, 바꾼 사람 이름(선택)."""

    version: int
    changed_at: datetime
    changed_by: str | None
    change_text: str


@dataclass(frozen=True)
class AutoOfficialUpdateRun:
    """자동 갱신 한 회차의 기록. 단계가 진행될 때마다 같은 행이 채워진다.

    `created_scenario_id`·`base_revision_id`(리비전 1)·`filtered_revision_id`(리비전 2)·
    `official_release_id` 는 가리키기만 한다 — 그 시나리오를 지워도 기록은 남는다.
    """

    run_id: str
    run_key: str
    trigger_kind: TriggerKind
    run_date: date
    status: RunStatus
    stage: str
    started_at: datetime
    finished_at: datetime | None
    keyword: str
    threshold: float
    settings_version: int
    baseline_release_no: int | None = None
    baseline_week: int | None = None
    candidate_count: int | None = None
    simulation_code: str | None = None
    simulation_name: str | None = None
    simulation_week: int | None = None
    source_registered_at: datetime | None = None
    detail_window: str | None = None
    created_scenario_id: str | None = None
    created_scenario_name: str | None = None
    base_revision_id: str | None = None
    filtered_revision_id: str | None = None
    official_release_id: str | None = None
    official_release_no: int | None = None
    auto_off_count: int | None = None
    inherited_off_count: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AutoOfficialUpdateExclusion:
    """한 회차가 공정 필터에서 뺀 공정 하나.

    `AUTO` 는 확보율로 판정해 뺀 것(최저 확보율·그 달이 있다), `INHERITED` 는 직전 공식버전에서
    사람이 손으로 뺀 것을 이어받은 것이다(판정할 달이 없었으면 최저 확보율이 비어 있다).
    """

    run_id: str
    filtered_revision_id: str | None
    process: str
    kind: ExclusionKind
    min_rate: float | None
    min_month: int | None


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
    secure_threshold: float = 1.10
    warning_threshold: float = 1.00
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
                raise ValueError(f"{with_topic_particle(label)} YYYYMM 형식이어야 합니다.")
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
    # 원천이 사내 DB 에 등록된 시각(BigDataQuery 등록시점). 내장 시드·CSV·복제처럼 원천 등록시점이
    # 없는 시나리오는 비어 있다.
    source_registered_at: datetime | None = None


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
class MainCaseTargets:
    """주요 Case 프로필과 그것이 가리키는 시나리오·리비전 — HOME 제목 줄 칩의 재료.

    `scenarios` 는 Case 가 가리키는 시나리오 가운데 목록(보관본 빼고)에 있는 것만, `revisions` 는 그
    시나리오들의 리비전 전부다. 가리키는 것이 목록에 없으면 슬롯이 「사라짐」으로 읽는다
    (`services/main_cases.main_case_slots`). 캐시 경계는 `persistence/cache.load_main_case_targets`.
    """

    profile: GlobalMainCases
    scenarios: tuple[ScenarioSummary, ...]
    revisions: tuple[RevisionSummary, ...]


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


# 부대공정 판 이력의 갈래(마이그레이션 0037 — `app_meta.extra_process_version.kind`).
# 「적용」 은 가져와 적용한 판, 「끄기」 는 활성 판을 비우는 빈 줄, 「다시 켜기」 는 마지막
# 내용 판을 파일 없이 되살린 줄, 「새 판」 은 리비전 값으로 만든 판(2단계)이다.
EXTRA_KIND_APPLY = "APPLY"
EXTRA_KIND_OFF = "OFF"
EXTRA_KIND_RESUME = "RESUME"
EXTRA_KIND_REVISION = "REVISION"
# 「새 판」 줄의 원천 자리(판 이력 `source_place`) — 파일이 아니라 저장 리비전에서 왔다.
EXTRA_REVISION_PLACE = "리비전"
EXTRA_KIND_LABELS: dict[str, str] = {
    EXTRA_KIND_APPLY: "적용",
    EXTRA_KIND_OFF: "끄기",
    EXTRA_KIND_RESUME: "다시 켜기",
    EXTRA_KIND_REVISION: "새 판",
}


@dataclass(frozen=True)
class ExtraProcessVersion:
    """부대공정 판 이력 한 줄(append-only). `OFF` 줄은 판 번호 · sha 가 없다."""

    seq: int
    kind: str
    version_no: int | None
    sha256: str | None
    created_at: datetime
    applied_by: str | None = None
    process_count: int | None = None
    row_counts: str | None = None
    source_place: str | None = None
    s3_key: str | None = None
    s3_etag: str | None = None
    s3_last_modified: datetime | None = None
    byte_size: int | None = None
    base_scenario_ref: str | None = None
    base_revision_ref: str | None = None
    s3_write_result: str | None = None

    @property
    def kind_label(self) -> str:
        return EXTRA_KIND_LABELS.get(self.kind, self.kind)


# 부대공정 판을 S3 Drive 파일로 다시 쓴 결과(마이그레이션 0038 —
# `app_meta.extra_process_s3_write.result`). 「씀」 은 덮어 쓴 것(PUT 이 돌려준 ETag 가 있다),
# 「덮지 않음」 은 쓰기 직전 HEAD 의 ETag 가 기준과 달라(적용하지 않은 사람 파일) 쓰지 않은 것,
# 「실패」 는 HEAD · PUT 이 실패한 것이다.
EXTRA_WRITE_WRITTEN = "WRITTEN"
EXTRA_WRITE_KEPT = "KEPT"
EXTRA_WRITE_FAILED = "FAILED"
EXTRA_WRITE_LABELS: dict[str, str] = {
    EXTRA_WRITE_WRITTEN: "앱이 덮음",
    EXTRA_WRITE_KEPT: "덮지 않음",
    EXTRA_WRITE_FAILED: "실패",
}
# 「씀」 줄 가운데 앱이 쓴 것이 아니라, 「새 판으로」 판을 사람이 S3 Drive 에 놓아 가져와 보니 활성
# 판과 같았던 것(설계 「가져오기를 붙이는 날」 — 판 어긋남 알림 `EP-06` 이 풀리고 그 파일의 ETag 가
# 기준이 된다). 「씀」 결과 그대로 넣고(마이그레이션 없이) 까닭 칸의 이 낱말로 가른다.
EXTRA_WRITE_PLACED_REASON = "놓인 파일 같음"


@dataclass(frozen=True)
class ExtraProcessS3Write:
    """S3 Drive 파일 쓰기 한 번(넣기만). `version_seq` 는 쓴 판의 이력 차례다."""

    seq: int
    version_seq: int
    result: str
    created_at: datetime
    etag: str | None = None
    seen_etag: str | None = None
    stage: str | None = None
    reason: str | None = None
    written_by: str | None = None

    @property
    def placed(self) -> bool:
        """사람이 놓은 같은 파일을 적은 줄인가(앱이 쓴 줄이 아니다)."""
        return self.result == EXTRA_WRITE_WRITTEN and self.reason == EXTRA_WRITE_PLACED_REASON

    @property
    def result_label(self) -> str:
        if self.placed:
            return EXTRA_WRITE_PLACED_REASON
        return EXTRA_WRITE_LABELS.get(self.result, self.result)


@dataclass(frozen=True)
class ExtraProcessState:
    """판 이력 전체(오래된 차례)와 S3 Drive 쓰기 기록. 판 이력의 마지막 줄이 지금 상태다."""

    history: tuple[ExtraProcessVersion, ...] = ()
    writes: tuple[ExtraProcessS3Write, ...] = ()

    def last_write(self, version_seq: int) -> ExtraProcessS3Write | None:
        """그 판의 마지막 S3 쓰기 기록 — 없으면 None."""
        found = [item for item in self.writes if item.version_seq == version_seq]
        return found[-1] if found else None

    @property
    def baseline(self) -> tuple[str | None, int | None]:
        """S3 쓰기의 기준 ETag 와 그 ETag 를 가진 판 차례 — (None, None) 이면 기준이 없다.

        앱이 적용했거나(가져와 적용 · 가져와 다시 켬 — 판 이력 줄의 ETag) 앱이 쓴(쓰기 기록 「씀」)
        마지막 파일의 ETag 다. 「새 판으로」 가 아직 쓰지 못한 동안은 앞 판의 것을 잇는다 — S3 에는
        아직 그 파일이 있다. 쓰기는 늘 그때의 활성 판에 하므로 차례는 (판 차례, 판 줄 → 그 판의
        쓰기 줄)이다. 가져와 검사만 한 파일 · 거절된 파일의 ETag 는 기준이 되지 않는다.
        """
        events: list[tuple[tuple[int, int, int], str, int]] = []
        for item in self.history:
            if item.s3_etag and item.kind != EXTRA_KIND_OFF:
                events.append(((item.seq, 0, 0), item.s3_etag, item.seq))
        for write in self.writes:
            if write.result == EXTRA_WRITE_WRITTEN and write.etag:
                events.append(((write.version_seq, 1, write.seq), write.etag, write.version_seq))
        if not events:
            return None, None
        _, etag, owner = max(events, key=lambda event: event[0])
        return etag, owner

    @property
    def last_seq(self) -> int:
        """마지막 줄의 차례 — 쓰기가 「편집을 시작할 때 본 상태」 로 대조한다(없으면 0)."""
        return self.history[-1].seq if self.history else 0

    @property
    def off(self) -> bool:
        """끈 동안인가 — 마지막 줄이 「끄기」 다."""
        return bool(self.history) and self.history[-1].kind == EXTRA_KIND_OFF

    @property
    def active(self) -> ExtraProcessVersion | None:
        """활성 판 — 마지막 줄이 내용 판이면 그 줄. 끈 동안 · 이력이 없으면 None."""
        if not self.history or self.off:
            return None
        return self.history[-1]

    @property
    def latest_content(self) -> ExtraProcessVersion | None:
        """적용한 내용 판 가운데 판 번호가 가장 큰 줄(P · S). 「끄기」 줄은 들지 않는다."""
        contents = [item for item in self.history if item.version_no is not None]
        if not contents:
            return None
        return max(contents, key=lambda item: (item.version_no or 0, item.seq))


@dataclass(frozen=True)
class ExtraProcessProvenance:
    """데이터셋 출처 한 줄 — 어느 판의 어느 공정을 합쳤나 · 뺐나와 그 까닭 · 표별 행 수(JSON).

    `outcome` 낱말은 합치기 결과(`services/extra_process_merge.OUTCOME_*`)와 같다.
    """

    process_name: str
    version_seq: int
    version_no: int
    sha256: str
    outcome: str
    rule: str | None = None
    reason: str | None = None
    row_counts: str | None = None
    note: str | None = None


# 부하 예외 선언 항목 — (원본 공정명, 산식 id) 의 차례 있는 묶음. 공용 프로필 캐시에 그대로 실을
# 수 있게(AGENTS 5장 21 — 피클 · 해시) 사상이 아니라 튜플로 두고, 계산에 넘길 사상은
# `declaration` 이다.
RouteLoadExceptionEntries = tuple[tuple[str, str], ...]


def _route_load_declaration(entries: RouteLoadExceptionEntries) -> Mapping[str, str]:
    return MappingProxyType(dict(entries))


@dataclass(frozen=True)
class RouteLoadExceptionVersion:
    """부하 예외 선언 판 이력 한 줄(넣기만 — 마이그레이션 0040). 비움 판은 항목이 없고 지문이 빈
    글이다. 공정명은 원본 표기 그대로이고 견줌은 계산 쪽 대조 키가 한다."""

    seq: int
    created_at: datetime
    entries: RouteLoadExceptionEntries
    digest: str
    applied_by: str | None = None
    source_place: str | None = None

    @property
    def declaration(self) -> Mapping[str, str]:
        """계산에 넘길 선언(원본 공정명 → 산식 id)."""
        return _route_load_declaration(self.entries)

    @property
    def process_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class RouteLoadExceptionProfile:
    """지금 부하 예외 선언 — 공용 프로필 캐시가 싣는 꼴(`persistence/cache.py`).

    한 번도 저장하지 않은 상태가 정상이다. 그때는 판 0 · `created_at=None` · 항목 없음 · 빈
    지문이고, 비움 판(모두 뺀 저장)도 항목 없음 · 빈 지문이다 — 둘 다 계산에 아무것도 걸지 않는다.
    """

    seq: int
    created_at: datetime | None
    applied_by: str | None
    entries: RouteLoadExceptionEntries
    digest: str

    @property
    def declaration(self) -> Mapping[str, str]:
        """계산에 넘길 선언(원본 공정명 → 산식 id)."""
        return _route_load_declaration(self.entries)

    @property
    def process_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class RouteLoadExceptionState:
    """부하 예외 선언 판 이력 전체(오래된 차례). 마지막 줄이 지금 선언이다."""

    history: tuple[RouteLoadExceptionVersion, ...] = ()

    @property
    def current(self) -> RouteLoadExceptionVersion | None:
        """마지막 판 — 이력이 없으면 None."""
        return self.history[-1] if self.history else None

    @property
    def seq(self) -> int:
        """마지막 판의 차례 — 쓰기가 「화면이 본 판」 으로 대조한다(없으면 0)."""
        current = self.current
        return 0 if current is None else current.seq

    @property
    def entries(self) -> RouteLoadExceptionEntries:
        current = self.current
        return () if current is None else current.entries

    @property
    def declaration(self) -> Mapping[str, str]:
        """지금 선언(원본 공정명 → 산식 id) — 이력이 없으면 빈 사상."""
        return _route_load_declaration(self.entries)

    @property
    def digest(self) -> str:
        current = self.current
        return "" if current is None else current.digest

    @property
    def profile(self) -> RouteLoadExceptionProfile:
        """지금 선언을 공용 프로필 꼴로."""
        current = self.current
        if current is None:
            return RouteLoadExceptionProfile(
                seq=0, created_at=None, applied_by=None, entries=(), digest=""
            )
        return RouteLoadExceptionProfile(
            seq=current.seq,
            created_at=current.created_at,
            applied_by=current.applied_by,
            entries=current.entries,
            digest=current.digest,
        )
