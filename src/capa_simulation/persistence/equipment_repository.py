# Purpose: 설비 DB 의 불변 리비전(공통 호기 대장·설비 시나리오 일정)과 설비 현행값을 읽고 쓴다.

"""설비 DB 의 불변 리비전과 설비 현행값.

설비 마스터는 **공통 호기 대장 리비전**(`equipment_ops.revision` — 번호 전역)과 **설비 시나리오 일정
리비전**(시나리오마다 r1 부터)으로 나뉜다(설비 DB `0027`). 화면이 쓰는 한 벌은 두 리비전을 호기 키로
합친 `EquipmentSnapshot` 이다(`read_merged`). 계약 v3 이하 리비전은 마스터에 일정이 함께 든 옛
꼴이라 `_read_legacy_snapshot` 으로 읽고, 0027 이관 리비전의 일정 원천이 된다. 층·FAB 도면, 공정별
Cut-off, 주차별 가용대수, 필요 단축 일정 조건·기준선은 리비전이 아닌 현행값이다.

쓰기는 `save_equipment`(바뀐 쪽만 · 대조 · 함께 넣기 · 교차 검증 · 공식 발행 — 한 트랜잭션)와
설비 시나리오 복제(고른 리비전에서 — 「여기서 새 시나리오」)·이름·발행·옛 배포 흔적 이어 쓰기, 일정
리비전의 리비전명(이름표)·「이 리비전으로 되돌리기」(E7 — 새 리비전으로 다시 저장)다.
`save_snapshot`·`save_space_layout`·`load_snapshot` 은 시험·스크립트용 호환 래퍼다 — 화면·캐시는
부르지 않는다.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence import equipment_scenario_store as scenario_store
from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import (
    as_datetime,
    as_int,
    connect,
    hash_frame,
    insert_by_name,
    require_profile_version,
    transaction,
)
from capa_simulation.persistence.equipment_migration_runner import (
    SchemaAheadOfCode,
    apply_equipment_migrations,
)
from capa_simulation.persistence.floor_state_store import (
    read_floor_states,
    write_floor_states,
)
from capa_simulation.persistence.shortening_baseline_store import (
    baseline_name_exists,
    delete_baseline,
    insert_baseline,
    list_baselines,
    load_baseline,
)
from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_DATE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    BASELINE_COLUMNS,
    COMMON_MASTER_COLUMNS,
    DEFAULT_CONVERSION_RATIO,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_equipment_master,
)
from capa_simulation.services.equipment_scenario import (
    COMMON_FRAME_COLUMNS,
    SCHEDULE_DOWNTIME_COLUMNS,
    SCHEDULE_FRAME_COLUMNS,
    UNIT_KEY_COLUMN,
    ScheduleRestorePreview,
    assign_unit_keys,
    downtime_identities,
    legacy_unit_key,
    merge_equipment,
    new_downtime_rows,
    new_unit_keys,
    normalize_schedule_downtime,
    normalize_schedule_frame,
    restore_writes_nothing,
    schedule_restore_preview,
    select_schedule_rows,
    split_downtime,
    split_equipment,
)
from capa_simulation.services.equipment_scenario import (
    calculation_frames as scenario_calculation_frames,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.fab_layout import (
    FAB_CANVAS,
    FAB_LAYOUT_KEY,
    FabLayoutBase,
    FabLayoutMark,
    FabLayoutProfile,
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
    require_fab_layout_fits,
)
from capa_simulation.services.floor_layout_mark import (
    ZONE_BORDER_STYLES,
    ZONE_LABEL_ALIGNS,
    FloorLayoutMark,
    GroupLabels,
    floor_layout_fingerprint,
    marks_extent,
    prepare_floor_layout_marks,
    prepare_group_labels,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    CanvasSize,
    FloorKey,
    FloorLayoutCanvas,
    FloorLayoutProfile,
    canvas_from_pixel_size,
    image_pixel_size,
    normalize_canvas_size,
    normalize_image_upload,
    require_total_layout_budget,
    to_data_uri,
)
from capa_simulation.services.floor_state import FloorStates, prepare_floor_states
from capa_simulation.services.korean_particle import (
    object_particle,
    with_object_particle,
    with_topic_particle,
)
from capa_simulation.services.layout_overlay import (
    EMPTY_LAYOUT_DIGEST,
    LAYOUT_ROLES,
    SCHEDULE_REVISION_ORIGINS,
    LayoutBase,
    LayoutOverlay,
    LayoutRole,
    MarkChange,
    OfficialFloor,
    Place,
    PublishBlock,
    apply_unit_overlay,
    common_with_places,
    effective_floor_marks,
    effective_group_labels,
    label_changes,
    layout_base,
    layout_cells,
    layout_counts_words,
    layout_publish_blocked_words,
    make_layout_overlay,
    mark_changes,
    normalize_layout_overlay,
    overlay_unit_count,
    split_layout,
)
from capa_simulation.services.process_cutoff import (
    empty_process_cutoff,
    prepare_process_cutoff,
    process_cutoff_fingerprint,
)
from capa_simulation.services.shortening_baseline import (
    ShorteningBaseline,
    ShorteningBaselineDraft,
    ShorteningBaselineSummary,
)
from capa_simulation.services.shortening_filter_profile import (
    ShorteningFilterProfile,
    merge_filter_processes,
    normalize_filter_month,
    normalize_filter_processes,
)
from capa_simulation.services.weekly_availability_input import prepare_weekly_availability

_WRITE_LOCK = threading.RLock()
# 저장본이 하나도 없을 때의 출발 리비전 표시. 편집본이 「빈 저장소에서 나왔다」는 뜻이다.
EMPTY_REVISION_TOKEN = "empty"
# 한 층 편집을 시작할 때 본 저장값: (저장된 캔버스 — 없으면 None, 저장된 도면 요소·Main 설비명
# 위치의 지문 `floor_layout_fingerprint`).
FloorLayoutBase = tuple[CanvasSize | None, str]


class ProcessCutoffConflict(ValueError):
    """Cut-off 편집을 시작한 뒤 다른 세션이 먼저 저장했다. 저장하지 않고 알린다."""


@dataclass
class _WriteOutcome:
    """쓰기 트랜잭션이 실제로 무엇을 썼는가. 아무것도 안 썼으면 동기화 dirty 표시를 하지 않는다."""

    wrote: bool = True


@dataclass(frozen=True)
class EquipmentRevisionSummary:
    """공통 호기 대장 리비전(`equipment_ops.revision`) 한 줄. 번호는 전역 하나다(「공통 rN」).

    계약 v4(설비 시나리오 뒤의 저장)는 비가동 행 수가 늘 0 이다 — 비가동은 설비 시나리오 일정
    리비전에 있고 그 요약(`EquipmentScheduleRevisionSummary.downtime_row_count`)이 센다. 캐시에
    실리는 모델이라 새 필드는 기본값을 둔다.
    """

    revision_id: str
    revision_no: int
    note: str | None
    baseline_row_count: int
    equipment_row_count: int
    downtime_row_count: int
    created_at: datetime
    saved_by: str | None = None


@dataclass(frozen=True)
class EquipmentScheduleRevisionSummary:
    """설비 시나리오 일정 리비전 한 줄. 번호는 시나리오마다 r1 부터다(화면의 「rN」).

    `origin` 은 legacy·save·clone·propagate·restore 가운데 하나다 — legacy 는 0027 이관 리비전이고
    `legacy_revision_id` 의 옛 마스터·비가동이 그 원천이다. restore 는 「이 리비전으로
    되돌리기」(E7)가 옛 리비전의 일정을 새 번호로 다시 저장한 것이다. `common_revision_id` 는 저장
    때 함께 본 공통 리비전(이력 「그때 그대로」), `unit_row_count` 는 이 리비전에 일정 행이 있는
    호기 수다.

    `revision_name`(리비전명)은 **이름표**라 나중에 고칠 수 있다(E7 — 내용은 그대로). 그래서 불변
    본문을 쌍 키로 싣는 합친 본문 캐시에는 싣지 않는다(`equipment_cache` — 늘 None 으로 꺼낸다).
    이름표는 리비전 목록(쓰기 세대·stat·TTL 로 지키는 캐시)에서 읽는다.

    배치 차이(설비 0031 — 가정 설비 시나리오의 Space 배치 중 공식과 다른 것)는 원시 행 수 셋과 지문
    `layout_hash`(0031 뒤 코드가 늘 적는다 — NULL 은 이관·옛 코드 리비전)로 싣는다. 실효(공식과
    실제로 다른 것)는 그 리비전을 지금 공식과 견줘야 알 수 있어 여기 없다. `origin` 에는
    `layout_clear`(「배치 차이 모두 지우기」·공식 발행 정리)가 더해진다.
    """

    schedule_revision_id: str
    equipment_scenario_id: str
    revision_no: int
    origin: str
    created_at: datetime
    revision_name: str | None = None
    note: str | None = None
    saved_by: str | None = None
    common_revision_id: str | None = None
    legacy_revision_id: str | None = None
    unit_row_count: int = 0
    downtime_row_count: int = 0
    layout_hash: str | None = None
    layout_unit_count: int = 0
    layout_mark_count: int = 0
    layout_label_count: int = 0

    @property
    def layout_digest(self) -> str:
        """배치 차이 지문 — NULL(이관·옛 코드 리비전)은 빈 차이로 읽는다."""
        return self.layout_hash or EMPTY_LAYOUT_DIGEST


@dataclass(frozen=True)
class EquipmentScenarioSummary:
    """설비 시나리오 한 줄 — 각 최신은 칸이 아니라 `MAX(revision_no)` 로 낸다.

    배치 차이(0031):
    `latest_layout_unit_count`·`latest_layout_mark_count`·`latest_layout_label_count` 는 최신의
    **저장된** 호기·도면 요소·Main 설비명 위치 차이 행 수(실효 아님 — 목록 표의 「저장된 배치
    차이」), `latest_layout_hash` 는 최신의 배치 지문(배치 빨리 감기 판정), `layout_trace_count` 는
    옛 코드 흔적(차이가 있는 리비전 뒤에 지문 없이 저장된 리비전 수)이다.
    """

    equipment_scenario_id: str
    scenario_name: str
    status: str
    list_order: int | None = None
    latest_schedule_revision_id: str | None = None
    latest_revision_no: int | None = None
    revision_count: int = 0
    latest_layout_unit_count: int = 0
    latest_layout_hash: str | None = None
    layout_trace_count: int = 0
    latest_layout_mark_count: int = 0
    latest_layout_label_count: int = 0

    @property
    def latest_layout_rows(self) -> tuple[int, int, int]:
        """최신의 저장된 배치 차이 행 수 — (호기, 도면 요소, Main 설비명 위치)."""
        return (
            self.latest_layout_unit_count,
            self.latest_layout_mark_count,
            self.latest_layout_label_count,
        )


@dataclass(frozen=True)
class EquipmentRelease:
    """공식 발행 한 줄(append-only). 번호(「공식 vN」)는 전역 하나다."""

    release_no: int
    equipment_scenario_id: str
    schedule_revision_id: str
    released_at: datetime
    released_by: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class EquipmentScenarioCatalog:
    """설비 시나리오 목록 한 벌 — 바뀔 수 있는 것(이름·발행·각 최신·흔적)만 모은다.

    리비전 내용은 불변이라 본문 캐시는 (공통 id, 일정 id) 쌍 키로 두고, 이 목록은 쓰기 세대·파일
    stat·TTL 로 따로 캐시한다(`equipment_cache.load_equipment_scenario_catalog`). 캐시에 실리는
    모델이라 필드에 기본값을 둔다.
    """

    scenarios: tuple[EquipmentScenarioSummary, ...] = ()
    latest_release: EquipmentRelease | None = None
    legacy_trace_count: int = 0

    def scenario(self, equipment_scenario_id: str | None) -> EquipmentScenarioSummary | None:
        """id 로 시나리오 한 줄. 없으면 None."""
        return next(
            (
                summary
                for summary in self.scenarios
                if summary.equipment_scenario_id == equipment_scenario_id
            ),
            None,
        )

    @property
    def official_scenario_id(self) -> str | None:
        """최신 공식 발행의 시나리오. 발행이 없으면 None."""
        return self.latest_release.equipment_scenario_id if self.latest_release else None

    @property
    def effective_official_scenario_id(self) -> str | None:
        """공식으로 볼 설비 시나리오 — 저장소 `equipment_scenario_store.official_scenario_id` 와
        같은 규칙이다: 최신 발행의 시나리오, 발행이 없으면 「운영 일정」(있으면), 그것도 없으면 목록
        첫 시나리오. 시나리오가 없으면 None. 화면의 「공식」 판정과 저장의 역할 판정이 갈리지 않게
        세션·화면은 이것을 쓴다(목록 차례를 바꾼 빈 발행 DB 에서도 같다)."""
        if self.latest_release is not None:
            return self.latest_release.equipment_scenario_id
        ids = [summary.equipment_scenario_id for summary in self.scenarios]
        if scenario_store.OPERATIONS_SCENARIO_ID in ids:
            return scenario_store.OPERATIONS_SCENARIO_ID
        return ids[0] if ids else None

    @property
    def release_no(self) -> int | None:
        """최신 공식 번호(「공식 vN」). 발행이 없으면 None."""
        return self.latest_release.release_no if self.latest_release else None


@dataclass(frozen=True)
class EquipmentSnapshot:
    """화면이 쓰는 설비 데이터 한 벌 — 공통 대장 리비전 + 설비 시나리오 일정 리비전을 합친 것.

    - `equipment` 는 39칸 합친 마스터이고 **일정 없음 호기도 든다**(편집·설비 마스터 탭·CSV 용).
      계산에는 `calculation_frames()` 를 쓴다.
    - `schedule` 이 None 이면 일정 리비전 없이 읽은 것이다(옛 길 `_read_legacy_snapshot`, 또는
      발행이 없는 공통 리비전).
    - 호기 키는 (설비명, 키) 쌍 튜플로 든다 — 캐시 본문에 실리는 모델이라 `MappingProxyType` 처럼
      pickle 이 안 되는 값을 두지 않는다. 꺼낼 때 `unit_keys` 가 dict 를 만든다.
    - 시나리오명·공식 번호 같은 라벨은 싣지 않는다 — 바뀔 수 있는 값이라 목록에서 읽는다.
    - 가정 설비 시나리오면 `equipment` 의 배치 일곱 칸은 공식에 그 리비전의 **호기 배치 차이**를
      얹은 것이다(설비 0031). `layout_official_places` 는 얹은 값이 공식과 실제로 다른 호기의 공식
      일곱 칸(「공식과 견주기」 재료), `layout_orphans` 는 공통에서 지운 호기라 버린 차이 수,
      `layout_regrouped` 는 공식에서 모듈 구성이 바뀌어 가정 자리를 다시 맞춘 묶음이다. 도면 요소·
      Main 설비명 위치 차이는 층마다 따로 읽는다(`equipment_cache.load_schedule_layout_overlay`).
    """

    revision: EquipmentRevisionSummary
    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame
    schedule: EquipmentScheduleRevisionSummary | None = None
    unit_key_pairs: tuple[tuple[str, str], ...] = ()
    unscheduled_units: frozenset[str] = frozenset()
    orphan_rows: int = 0
    layout_official_places: tuple[tuple[str, Place], ...] = ()
    layout_orphans: int = 0
    layout_regrouped: tuple[str, ...] = ()

    @property
    def token(self) -> str:
        """(공통 리비전, 일정 리비전) 쌍 토큰. 두 리비전 내용은 불변이라 토큰이 같으면 값이 같다."""
        schedule_id = self.schedule.schedule_revision_id if self.schedule is not None else "-"
        return f"{self.revision.revision_id}|{schedule_id}"

    @property
    def unit_keys(self) -> dict[str, str]:
        """설비명 → 호기 키."""
        return dict(self.unit_key_pairs)

    @property
    def layout_overridden_keys(self) -> frozenset[str]:
        """얹은 배치가 공식과 실제로 다른 호기 키(실효)."""
        return frozenset(key for key, _ in self.layout_official_places)

    def calculation_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """계산에 넘길 (기존 보유대수, 설비 마스터, 비가동) — 일정 없음 호기와 그 비가동을 뺀다."""
        return scenario_calculation_frames(
            self.baseline, self.equipment, self.downtime, self.unscheduled_units
        )


@dataclass(frozen=True)
class CommonFrames:
    """공통 대장 리비전 하나 — 기존 보유대수와 공통 32칸 + 호기 키(`COMMON_FRAME_COLUMNS`). 일정
    칸은 아예 없다."""

    revision: EquipmentRevisionSummary
    contract_version: int
    baseline: pd.DataFrame
    equipment: pd.DataFrame


@dataclass(frozen=True)
class ScheduleFrames:
    """설비 시나리오 일정 리비전 하나 — 키별 일곱 칸(`SCHEDULE_FRAME_COLUMNS`)과 키별 비가동
    (`SCHEDULE_DOWNTIME_COLUMNS`)."""

    revision: EquipmentScheduleRevisionSummary
    schedule: pd.DataFrame
    downtime: pd.DataFrame


class EquipmentScenarioIncompatible(ValueError):
    """일정 리비전을 지금 공통 대장과 합치면 설비 마스터 검증을 통과하지 못한다.

    각 시나리오의 최신과 최신 공식 발행은 저장 때의 교차 검증이 늘 합쳐지게 지킨다. 그 밖의 옛
    리비전은 막힐 수 있다 — 화면은 불러오기 전에 막거나 시나리오 최신으로 옮긴다.
    """

    def __init__(self, scenario_name: str, revision_no: int, reason: str) -> None:
        subject = with_object_particle(f"「{scenario_name}」 r{revision_no}")
        super().__init__(f"{subject} 지금 공통 대장과 합칠 수 없습니다 — {reason}")
        self.scenario_name = scenario_name
        self.revision_no = revision_no
        self.reason = reason


class EquipmentRevisionConflict(ValueError):
    """편집을 시작한 뒤 다른 사용자가 먼저 공통 대장이나 이 설비 시나리오에 저장했다. 아무것도
    쓰지 않았다. `side` 는 "common"(공통 대장) 또는 "schedule"(설비 시나리오 일정)이다."""

    def __init__(self, side: str, newest: str) -> None:
        super().__init__(
            f"다른 사용자가 먼저 {with_object_particle(newest)} 저장해 저장하지 않았습니다. 화면을 "
            "다시 불러와 최신 저장본 위에서 고친 뒤 저장하세요."
        )
        self.side = side
        self.newest = newest


class EquipmentScenarioGuardError(ValueError):
    """이번 저장 결과를 어느 설비 시나리오 리비전과 합치면 설비 마스터 검증을 통과하지 못한다.

    공통 대장은 모든 시나리오가 함께 쓰므로 공통 칸 하나가 다른 시나리오의 일정과 부딪칠 수
    있다(예: 다른 시나리오에 Qual일정이 있는 호기의 Qual상태를 비움). 아무것도 쓰지 않았다 —
    문구에 어느 시나리오·리비전인지와 빠져나갈 길을 적는다.
    """

    def __init__(self, scenario_name: str, revision_no: int, reason: str, escape: str) -> None:
        subject = f"「{scenario_name}」 r{revision_no}"
        super().__init__(
            f"이번 저장 결과를 {subject}에 합치면 설비 마스터 검증을 통과하지 못해 저장하지 "
            f"않았습니다 — {reason} {escape}"
        )
        self.scenario_name = scenario_name
        self.revision_no = revision_no
        self.reason = reason
        self.escape = escape


class EquipmentReleaseMoved(ValueError):
    """발행하려는 사이 최신 공식 발행이 바뀌었다. 아무것도 쓰지 않았다(없던 것은 0)."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(
            f"그 사이 다른 공식 발행(지금 공식 v{current}, 본 것은 v{expected})이 있어 발행하지 "
            "않았습니다 — 설비 시나리오 목록을 다시 보고 발행하세요."
        )
        self.expected = expected
        self.current = current


class EquipmentLegacyTraceError(ValueError):
    """이관 경계 뒤에 옛 배포가 저장한 계약 v3 공통 리비전이 있다 — 설비 마스터 저장을 막는다.

    그 위로 저장이 쌓이면 나머지 호기가 모든 시나리오에서 고아가 된다. 빠져나가는 길은 런북 4-2 의
    백업 복원, 또는 시나리오 관리 › 설비 시나리오의 「이대로 이어 쓰기」
    (`acknowledge_legacy_trace`).
    """

    def __init__(self, count: int) -> None:
        super().__init__(legacy_trace_message(count))
        self.count = count


class EquipmentLegacyTraceUnmergeable(ValueError):
    """옛 배포가 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 「이대로 이어 쓰기」 를 하지
    않았다 — 이어 쓰면 그 시나리오(공식이면 공식)를 다시는 읽을 수 없다. 백업 복원만 남는다."""


@dataclass(frozen=True)
class LegacyTraceReview:
    """「이대로 이어 쓰기」 확인 재료(쓰기 전에 읽는다).

    - `count` — 이관 경계 뒤 계약 v3 이하 공통 리비전 수(0 이면 나머지는 뜻이 없다).
    - `trace_revision_no` — 이어 쓰면 공통 최신이 될 옛 배포 리비전 번호.
    - `dropped_units` — 흔적 앞 공통 대장(새 판이 마지막으로 쓴 것)에 있다가 옛 배포 리비전에는 없어
      이어 쓰면 **모든 설비 시나리오**에서 빠지는 호기 수(새 판에서 만든 호기는 늘 든다 — 옛 배포는
      그 키를 모른다).
    - `refusal` — 옛 배포 리비전이 어느 시나리오 최신·공식 발행과 합쳐지지 않으면 그 까닭(이어
      쓰기를 막는다). 합쳐지면 None.
    """

    count: int = 0
    trace_revision_no: int | None = None
    dropped_units: int = 0
    refusal: str | None = None


def legacy_trace_message(count: int) -> str:
    """옛 배포 흔적 경고 문구 — 저장 거부와 화면 맨 위 경고가 같은 글자를 쓴다."""
    return (
        f"옛 배포로 저장한 설비 리비전 {count}개가 있어 설비 저장을 막았습니다 — 런북 4-2 대로 "
        "백업을 복원하거나, 시나리오 관리 › 설비 시나리오의 「이대로 이어 쓰기」 를 쓰세요."
    )


class EquipmentScenarioNameMoved(ValueError):
    """설비 시나리오 이름을 바꾸려는 사이 다른 사용자가 먼저 바꿨다. 아무것도 쓰지 않았다."""

    def __init__(self, current: str) -> None:
        super().__init__(f"다른 사용자가 먼저 이름을 바꿨습니다(지금: {current}).")
        self.current = current


class EquipmentLayoutRoleChanged(ValueError):
    """배치 편집을 시작한 뒤(화면 판정과 저장 사이에) 공식 설비 시나리오가 바뀌어, 그 편집이 들어갈
    자리(공식 배치 ↔ 이 시나리오의 배치 차이)가 달라졌다. 아무것도 쓰지 않았다(설계 6-2)."""

    def __init__(self, expected: str, current: str) -> None:
        def words(role: str) -> str:
            return "공식 배치" if role == "official" else "이 설비 시나리오의 가정 배치"

        super().__init__(
            "그 사이 공식 설비 시나리오가 바뀌어 이 배치 변경"
            f"({words(expected)}에 들어갈 편집이었음)을 저장하지 않았습니다 — 지금은 "
            f"{words(current)}에 들어갑니다. 저장 안 한 배치 변경을 버리고 다시 고치세요."
        )
        self.expected = expected
        self.current = current


class EquipmentLayoutScopeError(ValueError):
    """이 저장 역할로는 고칠 수 없는 배치다 — 가정 설비 시나리오의 층 캔버스(공통), 가정 역할에서
    공식 층이 다른 호기를 한 묶음으로 묶기, 가정이던 때의 배치 차이가 있는 옛 리비전에서 공식 배치
    고치기. 아무것도 쓰지 않았다(설계 6-7)."""


class EquipmentLayoutOverflow(ValueError):
    """층 캔버스를 줄이면 어느 설비 시나리오(각 최신·최신 공식 발행)의 가정 배치 도면 요소가 캔버스
    밖에 남는다. 아무것도 쓰지 않았다(설계 6-4 — 가정 차이 호기는 막지 않는다)."""

    def __init__(self, scenario_name: str, key: FloorKey, count: int) -> None:
        super().__init__(
            f"「{scenario_name}」 의 가정 배치에서 {key[0]} {key[1]} 요소 {count}개가 새 캔버스 "
            "밖입니다 — 그 설비 시나리오에서 요소를 옮기거나 캔버스를 덜 줄이세요."
        )
        self.scenario_name = scenario_name
        self.key = key
        self.count = count


class EquipmentLayoutPublishBlocked(ValueError):
    """공식과 다른 배치(배치 차이)가 있는 리비전·시나리오는 공식으로 발행하지 않는다(LY5 「공식으로
    올리기」 전까지 — Q4). 수는 지금 공식과 견준 실효다. 아무것도 쓰지 않았다."""

    def __init__(
        self,
        scenario_name: str,
        revision_no: int,
        units: int,
        marks: int,
        labels: int,
        *,
        message: str | None = None,
    ) -> None:
        """`message` 를 주면 그 글이다 — 공식 발행 쓰기는 확인 팝업과 같은 막힘 글
        (`layout_publish_blocked_words`)을 넘긴다. 저장·되돌리기의 자동 발행(새 최신 리비전)은 그
        새 리비전의 실효 수로 아래 글을 쓴다."""
        counts = layout_counts_words(units, marks, labels) or "저장된 차이"
        default = (
            f"「{scenario_name}」 r{revision_no} 에는 공식과 다른 배치({counts})가 있어 공식으로 "
            "발행하지 않았습니다 — 배치를 공식으로 올리는 기능은 다음 단계입니다. 공식 설비 "
            "시나리오에서 같은 배치를 직접 옮기거나, 「배치 차이 모두 지우기」 로 이 시나리오를 "
            "공식 배치로 돌린 뒤 발행하세요. 배치안을 남기려면 먼저 「여기서 새 시나리오」 로 옮겨 "
            "두세요."
        )
        super().__init__(message or default)
        self.scenario_name = scenario_name
        self.revision_no = revision_no
        self.units = units
        self.marks = marks
        self.labels = labels


@dataclass(frozen=True)
class LayoutPublishPreview:
    """「공식으로 발행」 확인 팝업의 배치 판정(설계 6-5) — 발행 쓰기(`publish_equipment_release`)와
    **같은 판정**을 쓰지 않고 낸다(`_layout_publish_preview` 한 곳).

    - `action` — "publish"(저장된 차이가 없음 — 지금처럼 발행), "clean"(행은 있지만 지금 공식과
      같아져 차이를 비운 새 리비전으로 발행), "blocked"(공식과 다른 배치가 있어 발행하지 않음).
    - `stored_units`·`stored_marks`·`stored_labels` — 발행할 리비전의 저장된 차이 행 수(원시).
    - `newest_rows` — 그 시나리오 최신의 저장된 차이 행 수 합(발행할 리비전이 최신이면 같은 값).
    - `is_newest` — 발행할 리비전이 그 시나리오 최신인가(정리 발행·「배치 차이 모두 지우기」 는
      최신만이라 막힘 글의 빠져나갈 길이 갈린다).
    - `units`·`marks`·`labels` — 발행할 리비전의 실효 수(지금 공식으로 정규화한 뒤 — 호기는 설비
      단위). `newest_units`·`newest_marks`·`newest_labels` — 그 시나리오 최신의 실효 수(발행할
      리비전이 최신이면 같은 값). 막힘 글은 실제로 공식과 다른 쪽만 「실효」 로 적는다.
    - `orphan_units`·`newest_orphan_units` — 저장된 호기 차이 행 가운데 공통 대장에서 지운 호기의 행
      수(정규화가 버린다 — 설계 5-1). 정리·막힘 글이 그 행을 「공식과 같아진」 행으로 세지 않는다.
    """

    action: Literal["publish", "clean", "blocked"] = "publish"
    stored_units: int = 0
    stored_marks: int = 0
    stored_labels: int = 0
    newest_rows: int = 0
    is_newest: bool = True
    units: int = 0
    marks: int = 0
    labels: int = 0
    newest_units: int = 0
    newest_marks: int = 0
    newest_labels: int = 0
    orphan_units: int = 0
    newest_orphan_units: int = 0

    @property
    def stored_rows(self) -> int:
        """발행할 리비전의 저장된 차이 행 수 합."""
        return self.stored_units + self.stored_marks + self.stored_labels

    def block(
        self, scenario_name: str, revision_no: int, newest_revision_no: int, *, official: bool
    ) -> PublishBlock:
        """막힘 글 재료(`layout_publish_blocked_words`) — 확인 팝업과 발행 쓰기 거부가 같은 글을
        낸다."""
        return PublishBlock(
            scenario_name=scenario_name,
            revision_no=revision_no,
            newest_revision_no=revision_no if self.is_newest else newest_revision_no,
            stored_rows=self.stored_rows,
            newest_rows=self.newest_rows,
            effective=(self.units, self.marks, self.labels),
            newest_effective=(self.newest_units, self.newest_marks, self.newest_labels),
            official=official,
            orphan_rows=self.orphan_units,
            newest_orphan_rows=self.orphan_units if self.is_newest else self.newest_orphan_units,
        )


# 층 캔버스 팝업 미리 보임의 한 상자 — (X좌표, Y좌표, Xsize, Ysize).
UnitBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class LayoutOverlayExtent:
    """층 캔버스 팝업(도면·캔버스 저장·지우기)의 가정 배치 미리 보임(설계 6-4·7-2).

    캔버스를 바꾸는 저장이 보는 것과 같은 리비전 — ACTIVE 설비 시나리오 최신(배치 차이가 있는 것)과
    최신 공식 발행 — 마다 그 층의 차이 요소 `set` 이 차지한 가장 먼 오른쪽·위(`marks` — (시나리오
    이름, 오른쪽, 위))와 차이 호기 상자(`units` — (시나리오 이름, 상자들)). 요소는 캔버스 밖이면
    저장이 막히고(`EquipmentLayoutOverflow`), 호기는 막지 않고 그 시나리오의 다음 저장만 막힌다.
    """

    marks: tuple[tuple[str, float, float], ...] = ()
    units: tuple[tuple[str, tuple[UnitBox, ...]], ...] = ()

    def mark_extent(self) -> CanvasSize:
        """모든 시나리오의 차이 요소가 차지한 가장 먼 오른쪽·위."""
        return (
            max((right for _, right, _ in self.marks), default=0.0),
            max((top for _, _, top in self.marks), default=0.0),
        )

    def marks_outside(self, canvas: CanvasSize) -> tuple[str, ...]:
        """캔버스 밖에 차이 요소가 남는 시나리오 이름."""
        width, height = canvas
        return tuple(
            name for name, right, top in self.marks if right > width + 1e-9 or top > height + 1e-9
        )

    def units_outside(self, canvas: CanvasSize) -> tuple[tuple[str, int], ...]:
        """시나리오마다 캔버스를 벗어나는 차이 호기 수(0 인 시나리오는 뺀다)."""
        width, height = canvas
        result = []
        for name, boxes in self.units:
            count = sum(
                1
                for x, y, w, h in boxes
                if x < -1e-9 or y < -1e-9 or x + w > width + 1e-9 or y + h > height + 1e-9
            )
            if count:
                result.append((name, count))
        return tuple(result)


class EquipmentScheduleRevisionNameMoved(ValueError):
    """일정 리비전의 리비전명을 바꾸려는 사이 다른 사용자가 먼저 바꿨다(비교 후 쓰기). 아무것도 쓰지
    않았다. `current` 는 쓰기 잠금 안에서 읽은 지금 이름(없으면 None)이다."""

    def __init__(self, current: str | None) -> None:
        shown = current if current is not None else "이름 없음"
        super().__init__(f"다른 사용자가 먼저 리비전명을 바꿨습니다(지금: {shown}).")
        self.current = current


@dataclass(frozen=True)
class ScheduleRestoreResult:
    """「이 리비전으로 되돌리기」(`restore_schedule_revision`)가 실제로 쓴 것.

    - `schedule` 은 새로 만든 일정 리비전(`origin='restore'`). 고른 리비전의 일정이 그 시나리오
      최신과 같아 아무것도 쓰지 않았으면 None 이다(빈 리비전을 만들지 않는다).
    - `release_no`·`release_withheld` 는 저장과 같은 규칙의 공식 발행 결과다(공식 시나리오에서
      되돌렸을 때만 뜻이 있다 — `EquipmentSaveResult` 와 같다).
    - `preview` 는 쓰기 잠금 안에서 다시 잰 차이(확인 글과 같은 함수)다.
    """

    schedule: EquipmentScheduleRevisionSummary | None
    preview: ScheduleRestorePreview
    release_no: int | None = None
    release_withheld: bool = False


@dataclass(frozen=True)
class EquipmentSaveRequest:
    """설비 마스터 저장 한 번(`save_equipment`) — 편집본 세 표와 그 출발점.

    - `base_common_revision_id` 는 편집본이 나온 공통 대장 리비전(저장본이 없었으면
      `EMPTY_REVISION_TOKEN`), `base_schedule_revision_id` 는 편집본이 나온 이 시나리오의 일정
      리비전(없었으면 None)이다. 저장소는 이 두 리비전을 쓰기 잠금 안에서 다시 읽어 호기 키·일정
      없음·편집 전 비가동을 낸다 — 두 리비전은 불변이고 공통 대조가 잠금 안이라 화면이 든 값과
      같다.
    - `renames` 는 지금 이름 → 저장본 이름(Space 편집기의 이름 바꾸기). 이 지도로 이은 호기는
      다른 시나리오에서도 같은 호기다(`assign_unit_keys`). `group_renames` 는 Main 설비 쪽 같은
      지도다 — 저장이 층 현행값의 공식 Main 설비명 위치 행을 새 이름으로 옮긴다(설계 5-4, 어느
      역할이든).
    - `expected_layout_role` 은 배치 편집을 적용할 때 찍은 역할("official"·"overlay")이다. None 이면
      배치를 건드리지 않은 저장이라 대조하지 않는다. 쓰기 잠금 안의 역할과 다르면
      `EquipmentLayoutRoleChanged`(설계 6-2).
    - `expected_release_no` 는 화면이 본 최신 공식 번호(발행이 없었으면 0)다. None 이면 대조하지
      않는다. 이번 저장이 공식 발행을 할 때만 대조한다.
    - `propagate_units` 는 다른 설비 시나리오에도 같은 일정으로 넣을 **새 호기 이름**이다(개편
      명세 13장 D8 — 새 호기마다 고른다). None 이면 지금처럼 `propagate_new_units` 하나가 모든 새
      호기에 걸린다. 주면 `propagate_new_units` 는 보지 않고 그 이름의 새 호기만 넣는다(새 호기가
      아닌 이름은 무시한다 — 빈 집합이면 아무 호기도 넣지 않는다). 새 비가동은 늘
      `propagate_new_downtime` 이다.
    - 층 값(`floor_*`)은 지금 그대로 같은 트랜잭션에 쓰는 층 현행값이다.
    """

    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame
    equipment_scenario_id: str
    base_common_revision_id: str
    base_schedule_revision_id: str | None
    renames: Mapping[str, str] = MappingProxyType({})
    note: str | None = None
    saved_by: str | None = None
    propagate_new_units: bool = True
    propagate_new_downtime: bool = True
    publish_official: bool = True
    expected_release_no: int | None = None
    propagate_units: frozenset[str] | None = None
    floor_canvases: Mapping[FloorKey, CanvasSize] | None = None
    floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None = None
    floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None = None
    floor_group_labels: Mapping[FloorKey, Mapping[str, object]] | None = None
    group_renames: Mapping[str, str] = MappingProxyType({})
    expected_layout_role: str | None = None


@dataclass(frozen=True)
class PropagatedRevision:
    """함께 넣기로 다른 설비 시나리오에 생긴 일정 리비전 한 줄(결과 알림 재료).

    `downtime` 은 넣은 비가동 (설비명, 유형, 시작일 `YYYY-MM-DD`), `skipped` 는 건너뛴 비가동 수
    (그 시나리오에 그 호기 일정이 없거나 같은 비가동이 이미 있음)다.
    """

    equipment_scenario_id: str
    scenario_name: str
    revision_no: int | None
    unit_count: int
    downtime: tuple[tuple[str, str, str], ...] = ()
    skipped: int = 0


@dataclass(frozen=True)
class EquipmentSaveResult:
    """`save_equipment` 가 실제로 쓴 것.

    - `common`·`schedule` 은 새로 만든 공통 대장·이 시나리오 일정 리비전(안 만들었으면 None).
    - `propagated` 는 함께 넣기를 받은 다른 시나리오마다 한 줄 — 건너뛰기만 해 리비전이 없는
      시나리오도 `revision_no=None` 으로 적는다.
    - `release_no` 는 이번 저장이 낸 공식 발행 번호, `release_withheld` 는 공식 시나리오에 새
      리비전이 생겼지만 그 전에 발행 안 한 더 새 리비전이 있어 발행하지 않았다는 뜻이다(「공식
      발행은 시나리오 관리 › 설비 시나리오에서」).
    - `forced_common` 은 0027 뒤 첫 저장이라 공통이 그대로여도 v4 공통을 함께 썼다는 뜻이다.
    - `new_units`·`removed_units` 는 공통 대장에 새로 든·빠진 설비명(지운 호기는 모든 시나리오에서
      빠진다 — 설비 마스터 탭 설비명 고침도 지운 + 새 호기다).
    - `layout_overlay_written` 은 이 저장이 가정 설비 시나리오의 배치 차이를 바꾼 새 리비전을
      만들었는가, `layout_overlay_units` 는 그 리비전의 공식과 다른 호기 수(설비 단위)이고
      `layout_overlay_marks`·`layout_overlay_labels` 는 그 리비전의 도면 요소·Main 설비명 위치
      차이 수다(쓰기 때 정규화를 마친 값이라 공식과 실제로 다른 것만이다).
      `floor_values_written` 은 층 현행값(공식 캔버스·요소·Main 설비명 위치)을 실제로 썼는가다 —
      가정 역할의 층 편집은 층 현행값이 아니라 배치 차이로 간다.
    """

    common: EquipmentRevisionSummary | None
    schedule: EquipmentScheduleRevisionSummary | None
    propagated: tuple[PropagatedRevision, ...] = ()
    release_no: int | None = None
    release_withheld: bool = False
    forced_common: bool = False
    floor_values_written: bool = False
    new_units: tuple[str, ...] = ()
    removed_units: tuple[str, ...] = ()
    layout_overlay_written: bool = False
    layout_overlay_units: int = 0
    layout_overlay_marks: int = 0
    layout_overlay_labels: int = 0

    @property
    def wrote_revision(self) -> bool:
        """공통·일정 리비전을 하나라도 새로 만들었는가(층 값만 쓴 저장은 False)."""
        return (
            self.common is not None
            or self.schedule is not None
            or any(item.revision_no is not None for item in self.propagated)
        )


# 리비전 요약 한 줄을 만드는 투영. 계약 버전에 따라 표가 갈려 CASE 가 길고, 두 조회
# (스냅샷 하나 · 목록)가 **같은 열 순서**로 읽어야 모델 생성이 맞는다. 계약 v4(설비 시나리오 뒤의
# 공통 대장)는 마스터 표의 행을 세고 비가동은 0 이다 — 비가동은 설비 시나리오 일정 리비전에 있다.
_REVISION_SUMMARY_PROJECTION = """
                r.revision_id, r.revision_no, r.note,
                       (SELECT COUNT(*) FROM equipment_ops.baseline_snapshot b
                        WHERE b.revision_id = r.revision_id),
                       CASE
                           WHEN r.equipment_contract_version IN (3, 4)
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           WHEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id) > 0
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot s
                                 WHERE s.revision_id = r.revision_id)
                       END,
                       CASE
                           WHEN r.equipment_contract_version = 4 THEN 0
                           WHEN r.equipment_contract_version = 3
                           THEN (SELECT COUNT(*) FROM equipment_ops.downtime_schedule_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.downtime_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                       END,
                       r.created_at, r.saved_by
"""


# 설비 마스터 계약(한글) ↔ `equipment_master_snapshot` 컬럼(영문). 읽기 별칭과 쓰기 이름이 모두
# 이 표 하나에서 나온다 — 화면 이름을 바꿔도 이 표의 왼쪽만 바꾸면 기존 리비전이 그대로 이어진다.
# DB 컬럼 이름은 옛 화면 이름에서 온 것이 많다(`line_type` = 공정구분, `classification_1` = Area
# Code, `removal_date` = 정지일정, `relocation_date` = 반출/이설일정, `qual_confirmation_status` =
# Qual상태).
# `investment_basis`(옛 `투자기준`)는 계약에서 빠졌다. **값은 지우지 않고 읽지도 쓰지도 않는다**
# — 과거 리비전의 이력이라서다. 되살리지 않기로 확정했다(2026-10-07).
# `business_unit` 과 `classification_3`(옛 `설비가동현황`, 2026-10-16 사용자 결정으로 빠짐)도 같은
# 처지다 — 다음 실제 저장부터 새 리비전에는 NULL 이 들어간다.
EQUIPMENT_MASTER_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        AREA_CODE_COLUMN: "classification_1",
        "공정대분류": "process_large",
        "공정소분류": "process_small",
        "Maker": "maker",
        "Model": "model_name",
        EQUIPMENT_ID_COLUMN: "equipment_id",
        "공정구분": "line_type",
        "투자Capa": "investment_capa",
        "투자구분": "utilization_type",
        "사용기준": "classification_2",
        "동": "building",
        "층": "floor_name",
        "담당자": "manager_name",
        "X좌표": "x_coordinate",
        "Y좌표": "y_coordinate",
        "Xsize": "x_size",
        "Ysize": "y_size",
        "제진대일정": "vibration_table_date",
        "물류일정": "logistics_date",
        ARRIVAL_DATE_COLUMN: "arrival_date",
        ARRIVAL_ACTUAL_COLUMN: "arrival_actual_date",
        ARRIVAL_STATUS_COLUMN: "arrival_status",
        QUAL_DATE_COLUMN: "qual_date",
        QUAL_ACTUAL_COLUMN: "qual_actual_date",
        QUAL_STATUS_COLUMN: "qual_confirmation_status",
        STOP_DATE_COLUMN: "removal_date",
        RELOCATION_DATE_COLUMN: "relocation_date",
        "반입/Qual 이력": "arrival_qual_history",
        "호기이력": "equipment_history",
        "설비이력": "note",
        "보관유무": "long_term_storage_flag",
        "기존설비여부": "existing_equipment_flag",
        "레이아웃표시": "layout_display_flag",
        "환산비": "conversion_ratio",
        "Main 설비": "parent_equipment_id",
        "메모1": "memo_1",
        "메모2": "memo_2",
        "메모3": "memo_3",
    }
)

# 0008 이전 리비전은 환산비가 NULL 이다 — 기준 모델(1.0)로 읽는다.
# 반입·Qual 이 필수이던 때 옛 리비전 변환은 빈 Qual 을 먼 미래(`LEGACY_QUAL_PLACEHOLDER`)로
# 채웠고, 그 편집본을 다시 저장한 리비전에는 그 날짜가 남아 있다. 정확히 그 날만 빈 Qual 로
# 읽는다 — 상태는 같고(빈 Qual = 셋업 진행중) 일정 미정 알림에 잡힌다. 그 날짜는 그 변환만 만들었다.
LEGACY_QUAL_PLACEHOLDER = "2262-04-11"
_EQUIPMENT_MASTER_READ_EXPRESSIONS: Mapping[str, str] = MappingProxyType(
    {
        "conversion_ratio": f"COALESCE(conversion_ratio, {DEFAULT_CONVERSION_RATIO!r})",
        "qual_date": f"NULLIF(qual_date, DATE '{LEGACY_QUAL_PLACEHOLDER}')",
    }
)

_EQUIPMENT_MASTER_PROJECTION = ", ".join(
    f'{_EQUIPMENT_MASTER_READ_EXPRESSIONS.get(db_column, db_column)} AS "{column}"'
    for column, db_column in EQUIPMENT_MASTER_DB_COLUMNS.items()
)

# 계약 v4 공통 대장의 마스터 — 공통 32칸과 호기 키. 마스터 표의 일정 칸은 읽지 않는다(v4 는 NULL).
# 키가 NULL 인 행(옛 판에서 옮겨 온 행)은 `legacy_unit_key` 와 같은 `'n' || md5(설비명)` 이다.
_COMMON_MASTER_PROJECTION = ", ".join(
    [
        f'{_EQUIPMENT_MASTER_READ_EXPRESSIONS.get(db_column, db_column)} AS "{column}"'
        for column, db_column in EQUIPMENT_MASTER_DB_COLUMNS.items()
        if column in COMMON_MASTER_COLUMNS
    ]
    + [f"COALESCE(unit_key, 'n' || md5(equipment_id)) AS \"{UNIT_KEY_COLUMN}\""]
)

DOWNTIME_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        EQUIPMENT_ID_COLUMN: "equipment_id",
        "비가동유형": "downtime_type",
        "시작일": "start_date",
        "종료일": "end_date",
        "상세사유": "detail",
        "비고": "note",
    }
)

_DOWNTIME_PROJECTION = ", ".join(
    f'{db_column} AS "{column}"' for column, db_column in DOWNTIME_DB_COLUMNS.items()
)


class DuckDBEquipmentRepository:
    """Persist full equipment input snapshots without changing past revisions."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()
        self._schema_ahead: SchemaAheadOfCode | None = None

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def schema_ahead(self) -> SchemaAheadOfCode | None:
        """마지막 `initialize()` 가 본 「설비 DB 가 이 코드보다 새 것」. 아니면 None.

        저장소는 프로세스마다 한 번 만들어 캐시하므로(`equipment_cache`) 화면은 rerun 마다
        이 속성만 읽는다 — DB 를 다시 열지 않는다.
        """
        return self._schema_ahead

    def initialize(self) -> tuple[int, ...]:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, self._connect() as connection:
            outcome = apply_equipment_migrations(connection)
        self._schema_ahead = outcome.schema_ahead
        return outcome.applied

    def save_equipment(self, request: EquipmentSaveRequest) -> EquipmentSaveResult:
        """설비 마스터 편집본을 공통 대장·이 설비 시나리오 일정으로 나눠 **바뀐 쪽만** 저장한다.

        연결 하나·트랜잭션 하나에서 하고, 계산·검증을 모두 메모리에서 끝낸 뒤 쓴다.

        1. 막기 — 옛 배포 흔적(`EquipmentLegacyTraceError`), 공통 최신 ≠ 출발 공통
           (`EquipmentRevisionConflict`), 일정을 쓰는데 이 시나리오 최신 ≠ 출발 일정(같은 예외),
           층 값 대조.
        2. 편집본 전체 검증(층 캔버스·오늘 기준 실적 검사 포함).
        3. 호기 키(`assign_unit_keys`) → 공통 32칸 + 키와 일정 일곱 칸 + 비가동으로 나눠 저장본과
           내용 해시로 견준다. 0027 뒤 첫 저장(공통 최신이 계약 v3 이하)에 일정이 바뀌었으면 공통도
           v4 한 벌을 함께 쓴다(`forced_common`). 둘 다 그대로이고 층 값도 없으면 아무것도 쓰지
           않는다.
        4. 함께 넣기 — 새 호기(`propagate_new_units`, 또는 새 호기마다 고른 `propagate_units`)·새
           비가동(`propagate_new_downtime`)을 다른 ACTIVE 시나리오의 최신 위에 새
           리비전(`origin='propagate'`)으로. 고친 비가동은 퍼지지 않는다(`new_downtime_rows`).
        5. 교차 검증 — 공통을 쓰거나 함께 넣기가 있으면 모든 시나리오(자기 포함)의 이번 저장 뒤
           최신과 최신 공식 발행을 새 공통과 합쳐 읽기 검증한다(`EquipmentScenarioGuardError`).
        6. 쓰기 — 공통(v4) → 이 시나리오 일정 → 함께 넣은 리비전 → 공식 발행 → 층 값.

        공식 발행은 이번 저장이 공식 시나리오에 새 일정 리비전을 만들었고 저장 전 최신 발행이 그
        시나리오의 최신이었을 때만 한다(`publish_official`). 발행이 하나도 없으면 이 저장의 일정
        리비전이 공식 v1 이다.
        """
        return self._save_equipment(
            request, mode="changed", official_target=False, check_common=True, force_publish=False
        ).result

    def save_snapshot(
        self,
        baseline: pd.DataFrame,
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None = None,
        floor_canvases: Mapping[FloorKey, CanvasSize] | None = None,
        floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None = None,
        base_revision_id: str | None = None,
        floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None = None,
        floor_group_labels: Mapping[FloorKey, Mapping[str, object]] | None = None,
    ) -> EquipmentSnapshot:
        """호환 래퍼(시험·스크립트용 — 화면·캐시는 `save_equipment` 를 쓴다).

        공식 설비 시나리오(발행이 없으면 「운영 일정」)의 최신 위에 **늘 공통 v4 와 일정 리비전을
        함께** 쓰고(바뀐 것이 없어도) 같은 트랜잭션에서 공식으로 발행한다. 래퍼만 쓰면 공통 rN 과
        그 시나리오 rN 이 같은 번호로 함께 오른다. 함께 넣기·교차 검증은 `save_equipment` 기본값
        그대로다. `base_revision_id` 는 공통 대조(None 이면 대조하지 않는다)이고 이름 지도는 없다 —
        설비명이 같은 호기만 키를 잇는다. 돌려주는 값은 그 쌍의 합친 스냅샷이다.
        """
        saved = self._save_equipment(
            _wrapper_request(
                baseline,
                equipment,
                downtime,
                note=note,
                floor_canvases=floor_canvases,
                floor_marks=floor_marks,
                base_revision_id=base_revision_id,
                floor_layout_bases=floor_layout_bases,
                floor_group_labels=floor_group_labels,
            ),
            mode="always",
            official_target=True,
            check_common=base_revision_id is not None,
            force_publish=True,
        )
        assert saved.common_revision_id is not None
        return self.load_merged_snapshot(saved.common_revision_id, saved.schedule_revision_id)

    def save_space_layout(
        self,
        baseline: pd.DataFrame,
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None = None,
        floor_canvases: Mapping[FloorKey, CanvasSize] | None = None,
        floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None = None,
        base_revision_id: str | None = None,
        floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None = None,
        floor_group_labels: Mapping[FloorKey, Mapping[str, object]] | None = None,
    ) -> EquipmentSnapshot | None:
        """`save_snapshot` 과 같되, 세 표가 공식 시나리오 최신 쌍과 같으면 **리비전을 만들지 않고**
        캔버스·도면 요소·Main 설비명 위치만 쓴다. 하나라도 바뀌면 두 쪽을 함께 쓰고 발행한다.
        새 리비전을 만들었으면 그 쌍의 합친 스냅샷, 아니면 None."""
        saved = self._save_equipment(
            _wrapper_request(
                baseline,
                equipment,
                downtime,
                note=note,
                floor_canvases=floor_canvases,
                floor_marks=floor_marks,
                base_revision_id=base_revision_id,
                floor_layout_bases=floor_layout_bases,
                floor_group_labels=floor_group_labels,
            ),
            mode="if_any",
            official_target=True,
            check_common=base_revision_id is not None,
            force_publish=True,
        )
        if not saved.result.wrote_revision or saved.common_revision_id is None:
            return None
        return self.load_merged_snapshot(saved.common_revision_id, saved.schedule_revision_id)

    def _save_equipment(
        self,
        request: EquipmentSaveRequest,
        *,
        mode: _SaveMode,
        official_target: bool,
        check_common: bool,
        force_publish: bool,
    ) -> _SaveOutcome:
        """`save_equipment` 와 두 래퍼의 한 길.

        `mode` — "changed" 는 바뀐 쪽만, "if_any" 는 하나라도 바뀌면 두 쪽 다, "always" 는 늘 두 쪽
        다. `official_target` 이면 저장할 시나리오와 출발 일정을 쓰기 잠금 안에서 공식 시나리오의
        최신으로 정한다(래퍼). `force_publish` 면 공식 시나리오에 새 리비전이 생길 때 늘 발행한다.

        **배치는 역할로 가른다**(설계 6-1 — 설비 0031). 대상 시나리오가 공식이면 위치는 공통 대장에,
        도면 요소·Main 설비명 위치는 층 현행값에 쓴다(지금 그대로). 가정이면 셋 다 그 시나리오의 새
        일정 리비전의 배치 차이로 쓰고 공통·층 현행값의 배치는 건드리지 않는다(새 호기는 자리 없이
        — Q1). 가정 배치만 바꾼 저장은 그 시나리오 최신의 배치 지문이 출발과 같으면 낡아도 받는다
        (배치 빨리 감기), 가정 리비전을 쓴 저장은 커밋 전에 그 쌍을 다시 읽어 확인한다.
        """
        canvases: dict[FloorKey, CanvasSize] = {}
        for (building, floor), size in (request.floor_canvases or {}).items():
            _require_floor_key(building, floor)
            canvases[(building, floor)] = normalize_canvas_size(*size)
        for building, floor in request.floor_marks or {}:
            _require_floor_key(building, floor)
        prepared_labels: dict[FloorKey, dict[str, str]] = {}
        for (building, floor), labels in (request.floor_group_labels or {}).items():
            _require_floor_key(building, floor)
            prepared_labels[(building, floor)] = prepare_group_labels(labels)
        if (
            request.expected_layout_role is not None
            and request.expected_layout_role not in LAYOUT_ROLES
        ):
            raise ValueError(f"배치 역할을 알 수 없습니다: {request.expected_layout_role!r}")
        prepared_baseline = prepare_equipment_baseline(request.baseline)
        note = _clean_text(request.note)
        saved_by = _clean_text(request.saved_by)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            # 막기 — 모두 쓰기 잠금 안에서 읽는다. 밖에서 읽으면 그 사이 다른 세션의 저장을
            # 놓쳐 옛 편집본이 그것을 되돌린다.
            traces = legacy_trace_count(connection)
            if traces:
                raise EquipmentLegacyTraceError(traces)
            latest = _latest_revision(connection)
            if check_common:
                current = latest[0] if latest is not None else EMPTY_REVISION_TOKEN
                if current != request.base_common_revision_id:
                    newest = f"공통 대장 r{latest[1]}" if latest is not None else "다른 저장"
                    raise EquipmentRevisionConflict("common", newest)
            scenarios = {
                summary.equipment_scenario_id: summary
                for summary in map(_scenario_summary, scenario_store.scenario_rows(connection))
            }
            if official_target:
                target_id = scenario_store.official_scenario_id(connection)
                if target_id is None:
                    raise ValueError("설비 시나리오가 없어 설비 마스터를 저장할 수 없습니다.")
                base_schedule_id = scenarios[target_id].latest_schedule_revision_id
            else:
                target_id = request.equipment_scenario_id
                base_schedule_id = request.base_schedule_revision_id
            scenario = _require_active_scenario(scenarios, target_id)
            base_summary: EquipmentScheduleRevisionSummary | None = None
            if base_schedule_id is not None:
                base_summary = _require_schedule_revision(connection, base_schedule_id)
                if base_summary.equipment_scenario_id != target_id:
                    raise ValueError(
                        f"출발 일정 리비전이 「{scenario.scenario_name}」 의 것이 아닙니다: "
                        f"{base_schedule_id}"
                    )
            release_row = scenario_store.latest_release_row(connection)
            release = _release(release_row) if release_row is not None else None
            # 역할 — 공식 설비 시나리오면 공식 배치(공통·층 현행값)를, 가정이면 그 시나리오의 배치
            # 차이를 쓴다. 화면이 배치 편집에 찍은 역할과 다르면(사이에 발행이 끼어듦) 쓰지 않는다.
            role: LayoutRole = (
                "official"
                if official_target or target_id == scenario_store.official_scenario_id(connection)
                else "overlay"
            )
            if request.expected_layout_role is not None and request.expected_layout_role != role:
                raise EquipmentLayoutRoleChanged(request.expected_layout_role, role)
            if role == "overlay" and canvases:
                raise EquipmentLayoutScopeError(
                    "층 캔버스·배경 도면은 공식 설비 시나리오에서 고칩니다 — "
                    f"「{scenario.scenario_name}」 은 가정 설비 시나리오라 층 캔버스를 바꾸지 "
                    "않았습니다."
                )
            base_overlay = read_layout_overlay(connection, base_summary)
            stored_canvases = _stored_floor_canvases(connection)
            _require_floor_layout_bases(
                connection,
                stored_canvases,
                request.floor_layout_bases or {},
                changed={*canvases, *(request.floor_marks or {}), *prepared_labels},
                overlay=base_overlay,
            )
            if role == "official" and base_overlay:
                touched = {*(request.floor_marks or {}), *prepared_labels} & set(
                    base_overlay.floors
                )
                if touched:
                    raise EquipmentLayoutScopeError(
                        "이 리비전에는 이 설비 시나리오가 가정이던 때의 배치 차이가 있어 도면 요소·"
                        "Main 설비명 위치를 고치지 않았습니다 — 최신 리비전을 불러와 고치세요."
                    )
            # 저장 시점에만 층 캔버스 상한과 실적 날짜(오늘보다 늦음·반입실적 > Qual실적)를
            # 강제한다. 다시 읽을 때는 둘 다 넘기지 않아 이미 저장된 리비전이 계속 열린다.
            merged_canvases = {**stored_canvases, **canvases}
            prepared_equipment = prepare_equipment_master(
                request.equipment, floor_canvases=merged_canvases, today=date.today()
            )
            prepared_downtime = prepare_downtime_for_prepared_equipment(
                request.downtime, prepared_equipment
            )
            default_canvas = (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
            prepared_marks = {
                key: prepare_floor_layout_marks(marks, merged_canvases.get(key, default_canvas))
                for key, marks in (request.floor_marks or {}).items()
            }
            # 캔버스만 바꾸는 층의 **저장된** 요소도 새 캔버스 안이어야 한다. 가정 배치의 요소
            # (각 시나리오 최신·최신 공식 발행)도 본다 — 가정 차이 호기는 막지 않는다(설계 6-4).
            for key, size in canvases.items():
                if key not in prepared_marks:
                    _require_marks_fit(connection, key, size)
                _require_overlay_marks_fit(connection, key, size)

            base = _read_base_state(
                connection, latest[0] if latest is not None else None, base_schedule_id
            )
            edit = _split_edit(prepared_equipment, prepared_downtime, base, request.renames)
            edit_keys = [str(key) for key in edit.common[UNIT_KEY_COLUMN]]
            edited_base = layout_base(edit.common, edit_keys)
            split = split_layout(
                edited_base,
                official=base.layout,
                started=base.started_places,
                role=role,
                overlay_present=bool(base_overlay.units),
            )
            if split.refusal is not None:
                raise EquipmentLayoutScopeError(split.refusal)
            # 공통 쪽에 공식 값을 둘 때는 반올림한 견줄 값이 아니라 공통 대장의 원래 칸 값을 옮긴다
            # (가정 저장이 공식 좌표를 반올림해 공통 리비전을 만들지 않게).
            edit = replace(
                edit,
                common=common_with_places(
                    edit.common,
                    edit_keys,
                    split.common_places,
                    current=edited_base.places,
                    official=layout_cells(
                        base.official_common,
                        [str(key) for key in base.official_common[UNIT_KEY_COLUMN]],
                    ),
                ),
            )
            label_moves = _group_label_moves(request.group_renames, base.common, edit.common)
            official_floors = _OfficialFloors(
                connection,
                marks=prepared_marks if role == "official" else {},
                labels=prepared_labels if role == "official" else {},
                moves=label_moves,
            )
            after_base = edited_base.with_places(split.common_places)
            layout = LayoutOverlay()
            layout_changed = False
            if role == "overlay":
                layout = _overlay_after_edit(
                    base_overlay, split.units, prepared_marks, prepared_labels, official_floors
                )
                started_layout = normalize_layout_overlay(
                    base_overlay, after_base, official_floors.for_overlay(base_overlay)
                )
                layout_changed = layout.digest() != started_layout.digest()
            common_changed = _common_digest(prepared_baseline, edit.common) != _common_digest(
                base.baseline, base.official_common
            )
            schedule_changed = _schedule_digest(edit.schedule, edit.downtime) != (
                _schedule_digest(base.schedule, base.downtime)
            )
            forced_common = (
                mode == "changed"
                and schedule_changed
                and not common_changed
                and base.contract_version is not None
                and base.contract_version < 4
            )
            if mode == "changed":
                write_common = common_changed or forced_common
                write_schedule = schedule_changed or layout_changed
            elif mode == "if_any":
                write_common = write_schedule = common_changed or schedule_changed
            else:
                write_common = write_schedule = True
            schedule_rows, downtime_rows = edit.schedule, edit.downtime
            if write_schedule and scenario.latest_schedule_revision_id != base_schedule_id:
                # 배치 빨리 감기(설계 6-1) — 가정 배치만 바꾼 저장은 그 시나리오 최신의 배치 지문이
                # 출발과 같으면(남이 일정만 저장했거나 함께 넣기가 새 리비전을 만들었음) 최신의
                # 일정·비가동 위에 새 배치 차이로 받는다. 남이 배치를 바꿨으면 지금처럼 거부한다.
                newest_summary = (
                    _require_schedule_revision(connection, scenario.latest_schedule_revision_id)
                    if scenario.latest_schedule_revision_id is not None
                    else None
                )
                started_digest = (
                    base_summary.layout_digest if base_summary is not None else EMPTY_LAYOUT_DIGEST
                )
                if (
                    role != "overlay"
                    or schedule_changed
                    or newest_summary is None
                    or newest_summary.layout_digest != started_digest
                ):
                    raise EquipmentRevisionConflict(
                        "schedule", f"「{scenario.scenario_name}」 r{scenario.latest_revision_no}"
                    )
                frames = read_schedule(connection, newest_summary.schedule_revision_id)
                known = set(edit.unit_keys.values())
                schedule_rows = _rows_for(frames.schedule, known)
                downtime_rows = _rows_for(frames.downtime, known)

            propagations = (
                _plan_propagations(
                    connection,
                    request,
                    scenarios,
                    target=scenario,
                    base=base,
                    edit=edit,
                    layout_base=after_base,
                    official_floors=official_floors,
                )
                if write_schedule
                else []
            )
            publish = _plan_publish(
                scenarios,
                release,
                target=scenario,
                write_schedule=write_schedule,
                propagated_ids={
                    plan.scenario.equipment_scenario_id for plan in propagations if plan.writes
                },
                publish_official=request.publish_official,
                expected_release_no=request.expected_release_no,
                force_publish=force_publish,
            )
            if publish.scenario_id is not None:
                # 배치 차이가 있는 리비전은 공식으로 발행하지 않는다(Q4). 저장의 자동 발행은 공식
                # 시나리오에서만 일어나 실제로 걸리지 않는다 — 발행이 없는 DB 의 첫 저장을 지킨다.
                published = (
                    layout
                    if publish.scenario_id == scenario.equipment_scenario_id
                    else next(
                        (
                            plan.layout
                            for plan in propagations
                            if plan.scenario.equipment_scenario_id == publish.scenario_id
                        ),
                        LayoutOverlay(),
                    )
                )
                if published:
                    owner = scenarios[publish.scenario_id]
                    raise EquipmentLayoutPublishBlocked(
                        owner.scenario_name,
                        (owner.latest_revision_no or 0) + 1,
                        overlay_unit_count(published, after_base),
                        published.mark_count,
                        published.label_count,
                    )
            if write_common or any(plan.writes for plan in propagations):
                _cross_validate(
                    connection,
                    scenarios,
                    release,
                    common=edit.common if write_common else base.official_common,
                    target=scenario,
                    base_schedule_id=base_schedule_id,
                    write_schedule=write_schedule,
                    propagations=propagations,
                    publishing=publish.scenario_id is not None,
                )

            common_id = latest[0] if latest is not None else None
            if write_common:
                common_id = _insert_common_revision(
                    connection,
                    note=note,
                    saved_by=saved_by,
                    baseline=prepared_baseline,
                    common=edit.common,
                )
            labels_moved = _move_group_labels(connection, label_moves)
            schedule_id = base_schedule_id
            if write_schedule:
                schedule_id = _insert_schedule(
                    connection,
                    equipment_scenario_id=scenario.equipment_scenario_id,
                    origin="save",
                    common_revision_id=common_id,
                    note=note,
                    saved_by=saved_by,
                    schedule=schedule_rows,
                    downtime=downtime_rows,
                    layout=layout,
                )
            propagated: list[PropagatedRevision] = []
            created = {scenario.equipment_scenario_id: schedule_id} if write_schedule else {}
            for plan in propagations:
                revision_no: int | None = None
                if plan.writes:
                    plan_id = _insert_schedule(
                        connection,
                        equipment_scenario_id=plan.scenario.equipment_scenario_id,
                        origin="propagate",
                        common_revision_id=common_id,
                        note=_propagation_note(scenario.scenario_name, plan),
                        saved_by=saved_by,
                        schedule=plan.schedule,
                        downtime=plan.downtime,
                        layout=plan.layout,
                    )
                    created[plan.scenario.equipment_scenario_id] = plan_id
                    revision_no = _require_schedule_revision(connection, plan_id).revision_no
                propagated.append(
                    PropagatedRevision(
                        equipment_scenario_id=plan.scenario.equipment_scenario_id,
                        scenario_name=plan.scenario.scenario_name,
                        revision_no=revision_no,
                        unit_count=plan.unit_count,
                        downtime=plan.downtime_added,
                        skipped=plan.skipped,
                    )
                )
            release_no: int | None = None
            if publish.scenario_id is not None:
                released = created.get(publish.scenario_id)
                if released is not None:
                    release_no = scenario_store.insert_release(
                        connection,
                        equipment_scenario_id=publish.scenario_id,
                        schedule_revision_id=released,
                        released_by=saved_by,
                        note="설비 마스터 저장과 함께 발행",
                    )
            floors_written = labels_moved
            if role == "official":
                for (building, floor), (width, height) in canvases.items():
                    _upsert_floor_canvas(connection, building, floor, width, height)
                for (building, floor), marks in prepared_marks.items():
                    _replace_floor_marks(connection, building, floor, marks)
                for (building, floor), labels in prepared_labels.items():
                    _replace_group_labels(connection, building, floor, labels)
                floors_written = (
                    floors_written
                    or bool(canvases)
                    or bool(prepared_marks)
                    or bool(prepared_labels)
                )
            if role == "overlay" and write_schedule and schedule_id is not None:
                # 끝 확인(I4) — 깨진 가정 리비전이 남아 그 세션이 공식으로 밀리지 않게 커밋 전에
                # 다시 읽는다. 실패하면 이 트랜잭션 전체가 되돌아간다.
                _require_final_read(connection, scenario, common_id, schedule_id)
            result = EquipmentSaveResult(
                common=_revision_row(connection, common_id)[0]
                if write_common and common_id is not None
                else None,
                schedule=_require_schedule_revision(connection, schedule_id)
                if write_schedule and schedule_id is not None
                else None,
                propagated=tuple(propagated),
                release_no=release_no,
                release_withheld=publish.withheld,
                forced_common=forced_common,
                floor_values_written=floors_written,
                new_units=edit.new_units,
                removed_units=edit.removed_units,
                layout_overlay_written=role == "overlay" and write_schedule and layout_changed,
                layout_overlay_units=overlay_unit_count(layout, after_base),
                layout_overlay_marks=layout.mark_count,
                layout_overlay_labels=layout.label_count,
            )
            outcome.wrote = result.wrote_revision or floors_written or release_no is not None
        return _SaveOutcome(result, common_id, schedule_id)

    def latest_revision_id(self) -> str | None:
        """공통 대장 최신 리비전 id(프레임은 읽지 않는다). 없으면 None."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision_id FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def load_snapshot(self, revision_id: str) -> EquipmentSnapshot:
        """호환 래퍼(시험·스크립트용 — 화면·캐시는 부르지 않는다): 공통 리비전 하나와 그 짝.

        짝은 공식 설비 시나리오에서 저장 때 이 공통을 함께 본 일정 리비전 가운데 마지막 것이다
        (이관 리비전·래퍼 저장은 늘 짝이 있다 — 옛 리비전의 일정이 그대로 나온다). 짝이 없으면
        계약 v3 이하는 그 리비전에 든 일정 그대로, v4(화면 저장이 공통만 바꾼 리비전)는 최신 공식
        발행 일정과 합친다. 발행에 따라 값이 바뀔 수 있는 뜻이라 공통 id 하나를 키로 캐시하지
        않는다.
        """
        with self._connect() as connection:
            return _paired_snapshot(connection, revision_id)

    def clone_equipment_scenario(
        self, source_schedule_revision_id: str, *, name: str, created_by: str | None
    ) -> EquipmentScenarioSummary:
        """설비 시나리오를 복제로 만든다(E8 — 만들기는 복제로만). 새 시나리오 한 줄(최신 = r1)을
        돌려준다.

        출처는 그 시나리오의 **어느 일정 리비전이든** 된다(「여기서 새 시나리오」). 새 r1 은 SQL
        사본이 아니라 `read_merged` 로 읽은 출처(지금 공통 대장과 합친 것)의 일정 일곱
        칸·비가동이다 — 이관 리비전의 Qual 자리표·계약 v2 변환·레거시 비가동 중복 제거가 원본과
        같게 걸린다. 출처의 일정 없음 호기(그 리비전 뒤에 공통 대장에 든 호기 포함)는 복제본에서도
        일정 없음이다. 출처 리비전의 **배치 차이**(가정 배치안)도 지금 공식으로 정규화해 옮긴다
        (설계 6-6 — 그 사이 공통에서 지운 호기의 차이는 빠진다). 지금 공통 대장과 합칠 수 없는 옛
        리비전은 `EquipmentScenarioIncompatible` 로 막는다 — 최신·공식 발행은 저장 때 교차 검증이 늘
        합쳐지게 지키지만 그 밖은 아니다. 이름은 보관본까지 겹칠 수 없다.
        """
        clean_name = _required_scenario_name(name)
        creator = _clean_text(created_by)
        outcome = _WriteOutcome(wrote=False)
        new_id = uuid4().hex
        with self._write_transaction(outcome) as connection:
            if scenario_store.scenario_name_taken(connection, clean_name):
                raise ValueError(DUPLICATE_EQUIPMENT_SCENARIO_NAME_MESSAGE)
            source = _require_schedule_revision(connection, source_schedule_revision_id)
            scenarios = {
                summary.equipment_scenario_id: summary
                for summary in map(_scenario_summary, scenario_store.scenario_rows(connection))
            }
            origin = scenarios.get(source.equipment_scenario_id)
            if origin is None:
                raise ValueError(
                    "출처 리비전의 설비 시나리오를 찾을 수 없습니다: "
                    f"{source.equipment_scenario_id}"
                )
            latest = _latest_revision(connection)
            if latest is None:
                raise ValueError("공통 대장 리비전이 없어 설비 시나리오를 복제할 수 없습니다.")
            snapshot = read_merged(connection, latest[0], source.schedule_revision_id)
            schedule, downtime = _scheduled_frames(snapshot)
            overlay = read_layout_overlay(connection, source)
            layout = normalize_layout_overlay(
                overlay, _official_layout(snapshot), _stored_floors(connection, overlay.floors)
            )
            scenario_store.insert_scenario(
                connection,
                equipment_scenario_id=new_id,
                name=clean_name,
                source_schedule_revision_id=source.schedule_revision_id,
                created_by=creator,
            )
            _insert_schedule(
                connection,
                equipment_scenario_id=new_id,
                origin="clone",
                common_revision_id=latest[0],
                note=f"「{origin.scenario_name}」 r{source.revision_no}에서 복제",
                saved_by=creator,
                schedule=schedule,
                downtime=downtime,
                layout=layout,
            )
            outcome.wrote = True
            created = _require_scenario_summary(connection, new_id)
        return created

    def rename_equipment_scenario(
        self, equipment_scenario_id: str, *, name: str, expected_name: str
    ) -> EquipmentScenarioSummary:
        """설비 시나리오 이름을 바꾼다. 고치기 시작할 때 본 이름(`expected_name`)과 쓰기 잠금 안에서
        견줘 다르면 `EquipmentScenarioNameMoved`. 보관본까지 겹칠 수 없다. 같은 이름이면 쓰지
        않는다."""
        clean_name = _required_scenario_name(name)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            current = scenario_store.scenario_name(connection, equipment_scenario_id)
            if current is None:
                raise ValueError(f"설비 시나리오를 찾을 수 없습니다: {equipment_scenario_id}")
            if current != expected_name:
                raise EquipmentScenarioNameMoved(current)
            if clean_name != current:
                if scenario_store.scenario_name_taken(
                    connection, clean_name, except_scenario_id=equipment_scenario_id
                ):
                    raise ValueError(DUPLICATE_EQUIPMENT_SCENARIO_NAME_MESSAGE)
                scenario_store.rename_scenario(connection, equipment_scenario_id, clean_name)
                outcome.wrote = True
            renamed = _require_scenario_summary(connection, equipment_scenario_id)
        return renamed

    def publish_equipment_release(
        self,
        schedule_revision_id: str,
        *,
        released_by: str | None,
        note: str | None,
        expected_latest_release_no: int | None,
    ) -> EquipmentRelease:
        """일정 리비전 하나를 공식으로 발행한다(append-only — 발행 행은 고치지 않는다).

        `expected_latest_release_no` 는 화면이 본 최신 공식 번호(발행이 없었으면 None)다. 쓰기
        잠금 안의 지금 번호와 다르면 `EquipmentReleaseMoved`. ACTIVE 시나리오의 리비전만, 지금
        공통 대장과 합쳐 읽기 검증을 통과해야 한다(`EquipmentScenarioIncompatible`). 이미 최신
        공식인 리비전이면 쓰지 않고 그 발행을 돌려준다.

        **배치 차이가 있으면 발행하지 않는다**(LY5 「공식으로 올리기」 전까지 — Q4, 불변식 I2 는
        저장된 행 기준). 발행할 리비전과 그 시나리오 최신의 차이를 지금 공식으로 정규화해:
        - 저장된 행이 둘 다 없으면 지금처럼 발행한다.
        - 행은 있지만 정규화하면 비고(공식이 그 사이 같은 자리로 옮김) 발행할 리비전이 그 시나리오
          최신이면, 같은 트랜잭션에서 일정은 그대로·차이를 비운 새 리비전(`origin='layout_clear'`)을
          쓰고 **그것을** 발행한다(돌려준 발행의 `schedule_revision_id` 가 그 새 리비전이다).
        - 그 밖은 `EquipmentLayoutPublishBlocked`(수는 실효).
        """
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            release_row = scenario_store.latest_release_row(connection)
            current_no = (
                as_int(release_row["release_no"], "공식 발행 번호")
                if release_row is not None
                else 0
            )
            expected_no = expected_latest_release_no or 0
            if expected_no != current_no:
                raise EquipmentReleaseMoved(expected_no, current_no)
            target = _require_schedule_revision(connection, schedule_revision_id)
            scenarios = {
                summary.equipment_scenario_id: summary
                for summary in map(_scenario_summary, scenario_store.scenario_rows(connection))
            }
            _require_active_scenario(scenarios, target.equipment_scenario_id)
            if release_row is not None and (
                str(release_row["schedule_revision_id"]) == schedule_revision_id
            ):
                return _release(release_row)
            latest = _latest_revision(connection)
            if latest is None:
                raise ValueError("공통 대장 리비전이 없어 발행할 수 없습니다.")
            snapshot = read_merged(connection, latest[0], schedule_revision_id)
            publish_id = _layout_publishable(
                connection,
                scenarios[target.equipment_scenario_id],
                target,
                snapshot,
                common_revision_id=latest[0],
                saved_by=_clean_text(released_by),
            )
            scenario_store.insert_release(
                connection,
                equipment_scenario_id=target.equipment_scenario_id,
                schedule_revision_id=publish_id,
                released_by=_clean_text(released_by),
                note=_clean_text(note),
            )
            outcome.wrote = True
            published = scenario_store.latest_release_row(connection)
            assert published is not None
        return _release(published)

    def rename_schedule_revision(
        self,
        schedule_revision_id: str,
        *,
        name: str | None,
        expected_name: str | None,
    ) -> EquipmentScheduleRevisionSummary:
        """일정 리비전의 리비전명(이름표)만 고친다 — E7. 일정·비가동·번호·메모·저장자·저장 시각은
        그대로다(리비전 **내용**은 append-only — AGENTS 5장 8 의 이름표 예외).

        - 비우면(None·빈 글자) 이름이 지워진다. 같은 이름을 다른 리비전에도 허용한다(번호가 늘
          가른다). 앞뒤 공백을 뗀 뒤 `SCHEDULE_REVISION_NAME_MAX_CHARS` 자를 넘으면 쓰지 않고
          `ValueError`(화면 칸도 같은 한도다).
        - **비교 후 쓰기** — `expected_name` 은 부르는 쪽이 보고 고친 지금 이름(없으면 None)이다.
          쓰기 잠금 안의 이름과 다르면 `EquipmentScheduleRevisionNameMoved` 로 거절한다 — 옛 이름을
          든 화면이 남의 변경을 조용히 되돌리지 않게.
        - 보관한 시나리오의 리비전은 고치지 않는다. 같은 이름이면 쓰지 않는다(동기화 dirty 도 없다).
        - 공식 발행 행·합친 본문 캐시는 이름을 싣지 않아 계산·공식이 그대로다. 리비전 목록 캐시는
          호출부가 `clear_equipment_scenario_cache()` 로 비운다(쓰기 세대를 올린다).
        """
        label = _schedule_revision_label(name)
        expected = _clean_text(expected_name)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            target = _require_schedule_revision(connection, schedule_revision_id)
            _require_active_scenario(
                _scenario_map(connection), target.equipment_scenario_id, verb="리비전명을 바꿀"
            )
            if target.revision_name != expected:
                raise EquipmentScheduleRevisionNameMoved(target.revision_name)
            if label != target.revision_name:
                scenario_store.rename_schedule_revision(connection, schedule_revision_id, label)
                outcome.wrote = True
            renamed = _require_schedule_revision(connection, schedule_revision_id)
        return renamed

    def preview_schedule_restore(
        self,
        schedule_revision_id: str,
        *,
        common_revision_id: str,
        current_schedule_revision_id: str | None,
    ) -> ScheduleRestorePreview:
        """「이 리비전으로 되돌리기」·「여기서 새 시나리오」 확인 재료 — 읽기만 한다(E7).

        `common_revision_id` 는 지금 공통 대장, `current_schedule_revision_id` 는 그 시나리오의 지금
        최신이다. 세 id 가 결과를 다 정하고 세 리비전 내용은 불변이라 캐시가 이 셋을 키로 둔다
        (`equipment_cache.load_schedule_restore_preview`). 되돌리기 쓰기
        (`restore_schedule_revision`)가 쓰기 잠금 안에서 같은 함수로 다시 잰다. 고른 리비전을
        지금 공통 대장과 합칠 수 없으면 `EquipmentScenarioIncompatible`.
        """
        with self._connect() as connection:
            target = _require_schedule_revision(connection, schedule_revision_id)
            preview, _, _ = _restore_preview(
                connection, common_revision_id, current_schedule_revision_id, target
            )
        return preview

    def restore_schedule_revision(
        self,
        schedule_revision_id: str,
        *,
        expected_common_revision_id: str,
        expected_latest_schedule_revision_id: str | None,
        saved_by: str | None = None,
        note: str | None = None,
        revision_name: str | None = None,
        publish_official: bool = True,
        expected_release_no: int | None = None,
        expected_layout_role: str | None = None,
    ) -> ScheduleRestoreResult:
        """「이 리비전으로 되돌리기」(E7) — 고른 일정 리비전의 일정을 **같은 시나리오의 새 리비전**
        (`origin='restore'`)으로 다시 저장한다. 옛 리비전·사이 리비전·공통 대장은 그대로다.

        1. 막기 — 옛 배포 흔적(`EquipmentLegacyTraceError` — 설비 저장과 같다), 보관한 시나리오,
           확인을 보인 뒤 공통 최신이나 그 시나리오 최신이 바뀜(`EquipmentRevisionConflict` — 확인
           글의 수가 달라진다). 모든 설비 시나리오에서 되돌릴 수 있다(공식 시나리오도).
        2. 새 리비전의 일정(날짜 여섯·시나리오 메모·비가동) = 고른 리비전을 **지금 공통 대장**과
           합친 것(복제와 같은 길 — `read_merged`). 그 리비전 뒤에 공통 대장에 든 호기는 그 리비전에
           일정 행이 없어 「일정 없음」 이 된다(F4). 그 뒤 지운 호기의 옛 일정은 합칠 때 버려진다.
           합칠 수 없으면 `EquipmentScenarioIncompatible`.
        3. 새 리비전의 **배치 차이** = 고른 리비전의 차이를 지금 공통·층 현행값으로 정규화한 것
           (가정 배치안을 되살린다 — 설계 6-6). 그 시나리오가 공식이면 차이를 버린다(I2).
           `expected_layout_role`(확인 글을 보인 때의 역할 "official"·"overlay")이 쓰기 잠금 안의
           역할과 다르면 `EquipmentLayoutRoleChanged` — 확인 글과 실제 쓰기가 갈리지 않게.
        4. 쓸 것이 없으면 쓰지 않는다(`schedule=None` — 빈 리비전을 만들지 않는다). 판정은 확인
           화면과 같은 `restore_writes_nothing` 이다 — 공식 시나리오면 일정·비가동이 모두 같을 때,
           가정이면 저장된 배치 차이(원시 지문)까지 같을 때.
        5. 공식 발행은 설비 마스터 저장과 같은 규칙(`_plan_publish`)이다 — 공식 시나리오에서
           되돌렸고 `publish_official` 이며 저장 전 최신 발행이 그 시나리오 최신이었을 때만 새
           리비전을 발행한다(발행 안 한 더 새 리비전이 있었으면 `release_withheld`). 발행할 때만
           `expected_release_no` 를 대조한다.

        공통을 쓰지 않으므로 교차 검증이 없다 — 새 리비전은 지금 공통 대장과 합쳐 읽기 검증을 지난
        값이고 다른 시나리오는 건드리지 않는다. 메모는 「rK 일정으로 되돌림」 뒤에 적은 메모를
        붙인다. 새 리비전명은 `rename_schedule_revision` 과 같은 글자 수 한도다(넘으면 쓰기 전에
        `ValueError`). 캐시는 호출부가 `clear_equipment_scenario_cache()` 로 비운다.
        """
        label = _schedule_revision_label(revision_name)
        author = _clean_text(saved_by)
        user_note = _clean_text(note)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            traces = legacy_trace_count(connection)
            if traces:
                raise EquipmentLegacyTraceError(traces)
            target = _require_schedule_revision(connection, schedule_revision_id)
            scenarios = _scenario_map(connection)
            scenario = _require_active_scenario(
                scenarios, target.equipment_scenario_id, verb="되돌릴"
            )
            latest = _latest_revision(connection)
            if latest is None:
                raise ValueError("공통 대장 리비전이 없어 되돌릴 수 없습니다.")
            if latest[0] != expected_common_revision_id:
                raise EquipmentRevisionConflict("common", f"공통 대장 r{latest[1]}")
            if scenario.latest_schedule_revision_id != expected_latest_schedule_revision_id:
                raise EquipmentRevisionConflict(
                    "schedule", f"「{scenario.scenario_name}」 r{scenario.latest_revision_no}"
                )
            role: LayoutRole = (
                "official"
                if scenario.equipment_scenario_id == scenario_store.official_scenario_id(connection)
                else "overlay"
            )
            if expected_layout_role is not None and expected_layout_role != role:
                raise EquipmentLayoutRoleChanged(expected_layout_role, role)
            preview, restored, restored_layout = _restore_preview(
                connection, latest[0], scenario.latest_schedule_revision_id, target
            )
            # 「쓸 것 없음」 판정은 확인 화면과 같은 함수다(설계 6-6 — 확인 글과 실제 쓰기가 갈리지
            # 않게): 공식이면 차이를 버리니 일정·비가동만, 가정이면 쓸 차이(정규화)까지 본다.
            if restore_writes_nothing(preview, official_scenario=role == "official"):
                return ScheduleRestoreResult(schedule=None, preview=preview)
            official_layout = _official_layout(restored)
            layout = LayoutOverlay() if role == "official" else restored_layout
            release_row = scenario_store.latest_release_row(connection)
            publish = _plan_publish(
                scenarios,
                _release(release_row) if release_row is not None else None,
                target=scenario,
                write_schedule=True,
                propagated_ids=(),
                publish_official=publish_official,
                expected_release_no=expected_release_no,
                force_publish=False,
            )
            if publish.scenario_id is not None and layout:
                raise EquipmentLayoutPublishBlocked(
                    scenario.scenario_name,
                    (scenario.latest_revision_no or 0) + 1,
                    overlay_unit_count(layout, official_layout),
                    layout.mark_count,
                    layout.label_count,
                )
            schedule, downtime = _scheduled_frames(restored)
            system_note = f"r{target.revision_no} 일정으로 되돌림"
            new_id = _insert_schedule(
                connection,
                equipment_scenario_id=scenario.equipment_scenario_id,
                origin="restore",
                common_revision_id=latest[0],
                note=f"{system_note} — {user_note}" if user_note else system_note,
                saved_by=author,
                schedule=schedule,
                downtime=downtime,
                layout=layout,
                revision_name=label,
            )
            release_no: int | None = None
            if publish.scenario_id is not None:
                release_no = scenario_store.insert_release(
                    connection,
                    equipment_scenario_id=publish.scenario_id,
                    schedule_revision_id=new_id,
                    released_by=author,
                    note="되돌리기와 함께 발행",
                )
            outcome.wrote = True
            created = _require_schedule_revision(connection, new_id)
        return ScheduleRestoreResult(
            schedule=created,
            preview=preview,
            release_no=release_no,
            release_withheld=publish.withheld,
        )

    def clear_layout_overlay(
        self,
        equipment_scenario_id: str,
        *,
        expected_latest_schedule_revision_id: str | None,
        saved_by: str | None = None,
        note: str | None = None,
    ) -> EquipmentScheduleRevisionSummary | None:
        """「배치 차이 모두 지우기」(설계 6-6) — 그 시나리오 최신의 일정·비가동을 그대로 두고 배치
        차이만 비운 새 리비전(`origin='layout_clear'`, 메모 「배치 차이 모두 지움 — 공식 배치로」)을
        쓴다. 지울 차이가 없으면(공식 시나리오 포함) 쓰지 않고 None.

        막기는 저장과 같다 — 옛 배포 흔적, 보관한 시나리오, 확인을 보인 뒤 그 시나리오 최신이 바뀜
        (`EquipmentRevisionConflict`). 공통·층 현행값·발행은 건드리지 않는다. 캐시는 호출부가
        `clear_equipment_snapshot_cache()` 로 비운다.
        """
        author = _clean_text(saved_by)
        user_note = _clean_text(note)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            traces = legacy_trace_count(connection)
            if traces:
                raise EquipmentLegacyTraceError(traces)
            scenario = _require_active_scenario(
                _scenario_map(connection), equipment_scenario_id, verb="배치 차이를 지울"
            )
            if scenario.latest_schedule_revision_id != expected_latest_schedule_revision_id:
                raise EquipmentRevisionConflict(
                    "schedule", f"「{scenario.scenario_name}」 r{scenario.latest_revision_no}"
                )
            if scenario.latest_schedule_revision_id is None:
                return None
            newest = _require_schedule_revision(connection, scenario.latest_schedule_revision_id)
            if not read_layout_overlay(connection, newest):
                return None
            latest = _latest_revision(connection)
            if latest is None:
                raise ValueError("공통 대장 리비전이 없어 배치 차이를 지울 수 없습니다.")
            snapshot = read_merged(connection, latest[0], newest.schedule_revision_id)
            schedule, downtime = _scheduled_frames(snapshot)
            system_note = "배치 차이 모두 지움 — 공식 배치로"
            new_id = _insert_schedule(
                connection,
                equipment_scenario_id=scenario.equipment_scenario_id,
                origin="layout_clear",
                common_revision_id=latest[0],
                note=f"{system_note} — {user_note}" if user_note else system_note,
                saved_by=author,
                schedule=schedule,
                downtime=downtime,
                layout=LayoutOverlay(),
            )
            _require_final_read(connection, scenario, latest[0], new_id)
            outcome.wrote = True
            created = _require_schedule_revision(connection, new_id)
        return created

    def legacy_trace_review(self) -> LegacyTraceReview:
        """「이대로 이어 쓰기」 확인 재료 — 흔적 수, 빠지는 호기 수, 합쳐지지 않는 까닭(읽기만)."""
        with self._connect() as connection:
            return _legacy_trace_review(connection)

    def acknowledge_legacy_trace(self, *, expected_trace_count: int, note: str | None) -> int:
        """옛 배포 흔적을 확인하고 이어 쓴다 — 이관 경계 행 하나를 덧붙이고 그 번호를 돌려준다.

        흔적 수가 쓰기 잠금 안에서 `expected_trace_count` 와 같을 때만 `through_revision_no = 지금
        공통 최신 번호` 로 덧붙인다(다르면 `ValueError`). 흔적이 없으면 쓰지 않고 지금 마지막 경계
        번호를 돌려준다. 옛 판에서 고친 일정은 들어오지 않는다 — 계약 v3 공통의 일정 칸은 공통
        읽기가 버린다. 옛 배포 리비전이 어느 ACTIVE 시나리오 최신이나 최신 공식 발행과 합쳐지지
        않으면 쓰지 않고 `EquipmentLegacyTraceUnmergeable` 를 낸다 — 이어 쓰면 그 리비전이 공통
        최신으로 굳어 그 시나리오(공식이면 모든 설비 화면의 공식)를 다시 읽을 수 없다(「각 시나리오
        최신·공식은 늘 합쳐진다」 를 저장 교차 검증처럼 여기서도 지킨다).
        """
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            count = legacy_trace_count(connection)
            if count != expected_trace_count:
                raise ValueError(
                    f"그 사이 옛 배포 흔적 수가 바뀌었습니다(본 것 {expected_trace_count}개 · 지금 "
                    f"{count}개) — 다시 확인한 뒤 이어 쓰세요."
                )
            if count == 0:
                return scenario_store.latest_boundary_no(connection)
            latest = _latest_revision(connection)
            assert latest is not None
            refusal = _trace_merge_refusal(connection, latest[0])
            if refusal is not None:
                raise EquipmentLegacyTraceUnmergeable(_unmergeable_trace_message(refusal))
            boundary_no = scenario_store.insert_boundary(
                connection,
                through_revision_no=latest[1],
                note=_clean_text(note) or "이대로 이어 쓰기",
            )
            outcome.wrote = True
        return boundary_no

    def load_merged_snapshot(
        self, common_revision_id: str, schedule_revision_id: str | None
    ) -> EquipmentSnapshot:
        """공통 리비전 + 일정 리비전을 합친 스냅샷(`read_merged`). 두 리비전 내용은 불변이다."""
        with self._connect() as connection:
            return read_merged(connection, common_revision_id, schedule_revision_id)

    def load_layout_overlay(self, schedule_revision_id: str | None) -> LayoutOverlay:
        """일정 리비전 하나의 배치 차이(설비 0031 — 차이가 없으면 질의 없이 빈 값)."""
        with self._connect() as connection:
            return read_layout_overlay(connection, schedule_revision_id)

    def load_official_snapshot(self) -> EquipmentSnapshot | None:
        """공통 최신 + 최신 공식 발행 일정 리비전. 공통 리비전이 없으면 None."""
        with self._connect() as connection:
            pair = read_official_pair(connection)
            if pair is None:
                return None
            return read_merged(connection, *pair)

    def load_saved_pair(self, schedule_revision_id: str) -> EquipmentSnapshot:
        """이력 「그때 그대로」 — 그 일정 리비전 + 그 저장이 함께 본 공통 리비전.

        함께 본 공통(`common_revision_id`)이 비어 있으면(그런 저장은 없다) 공통 최신과 합친다.
        """
        with self._connect() as connection:
            schedule = _require_schedule_revision(connection, schedule_revision_id)
            common = schedule.common_revision_id
            if common is None:
                latest = _latest_revision(connection)
                if latest is None:
                    raise KeyError("공통 대장 리비전이 없습니다.")
                common = latest[0]
            return read_merged(connection, common, schedule_revision_id)

    def units_scheduled_elsewhere(
        self, equipment_scenario_id: str | None
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """다른 ACTIVE 설비 시나리오의 **최신** 리비전에 일정 행이 있는 호기 — (호기 키, 그 시나리오
        이름들) 키 차례. 설비 마스터 탭에서 호기를 지우는 저장의 확인 재료다(지우면 공통 대장에서
        빠져 그 시나리오들의 일정도 빠진다 — 설계 11-2 6단계). 배치 차이 행(설비 0031 — 가정
        배치)만 있는 호기도 든다. `equipment_scenario_id` 가 None 이면 모든 ACTIVE 시나리오를 본다.
        이관 리비전은 그 리비전의 모든 호기에 일정 행이 있다(`read_schedule`)."""
        found: dict[str, list[str]] = {}
        with self._connect() as connection:
            for summary in map(_scenario_summary, scenario_store.scenario_rows(connection)):
                if (
                    summary.status != "ACTIVE"
                    or summary.equipment_scenario_id == equipment_scenario_id
                    or summary.latest_schedule_revision_id is None
                ):
                    continue
                frames = read_schedule(connection, summary.latest_schedule_revision_id)
                keys = set(frames.schedule[UNIT_KEY_COLUMN].dropna().astype(str))
                keys |= read_layout_overlay(connection, frames.revision).unit_keys
                for key in sorted(keys):
                    found.setdefault(key, []).append(summary.scenario_name)
        return tuple((key, tuple(names)) for key, names in sorted(found.items()))

    def layout_overlay_floor_counts(self, building: str, floor: str) -> tuple[tuple[str, int], ...]:
        """ACTIVE **가정** 설비 시나리오(공식 시나리오 밖) 최신마다 그 리비전의 호기 배치 차이에서
        이 층에 놓인 호기 행 수 — (시나리오 이름, 수) 목록 차례, 0 인 시나리오는 뺀다. Space 층
        사용 끄기 확인의 덧줄 재료다(설계 13-2 — 층 사용은 공통이라 그 시나리오 목록·도면에서도
        숨는다). 차이가 없는 리비전은 질의하지 않는다(`read_layout_overlay`)."""
        found: list[tuple[str, int]] = []
        with self._connect() as connection:
            official = scenario_store.official_scenario_id(connection)
            for summary in map(_scenario_summary, scenario_store.scenario_rows(connection)):
                if (
                    summary.status != "ACTIVE"
                    or summary.equipment_scenario_id == official
                    or summary.latest_schedule_revision_id is None
                    or summary.latest_layout_unit_count == 0
                ):
                    continue
                overlay = read_layout_overlay(connection, summary.latest_schedule_revision_id)
                count = sum(
                    1 for _, _, place in overlay.units if (place[0], place[1]) == (building, floor)
                )
                if count:
                    found.append((summary.scenario_name, count))
        return tuple(found)

    def preview_layout_publish(
        self,
        schedule_revision_id: str,
        *,
        common_revision_id: str,
        newest_schedule_revision_id: str | None,
    ) -> LayoutPublishPreview:
        """「공식으로 발행」 확인 팝업의 배치 판정(읽기만 — 설계 6-5). 발행할 리비전을 공통
        `common_revision_id` 와 합쳐, 그 시나리오 최신 `newest_schedule_revision_id` 와 함께 발행
        쓰기와 같은 판정(`_layout_publish_preview`)에 태운다. 결과는 두 리비전 id·공통 id 와 층
        현행값으로만 정해진다(화면 캐시는 층 현행값 쓰기 세대를 키에 둔다)."""
        with self._connect() as connection:
            target = _require_schedule_revision(connection, schedule_revision_id)
            return _layout_publish_preview(
                connection,
                target,
                newest_schedule_revision_id=newest_schedule_revision_id,
                snapshot=lambda: read_merged(connection, common_revision_id, schedule_revision_id),
            )

    def layout_overlay_extent(self, building: str, floor: str) -> LayoutOverlayExtent:
        """층 캔버스 팝업의 가정 배치 미리 보임(설계 6-4) — 캔버스를 바꾸는 저장이 보는
        리비전(ACTIVE 시나리오 최신 가운데 차이가 있는 것·최신 공식 발행)마다 그 층의 차이 요소
        범위와 차이 호기 상자. 차이가 없는 리비전은 질의하지 않는다(`read_layout_overlay`)."""
        key = (building, floor)
        marks: list[tuple[str, float, float]] = []
        units: list[tuple[str, tuple[UnitBox, ...]]] = []
        with self._connect() as connection:
            for revision_id, name in _overlay_check_targets(connection).items():
                overlay = read_layout_overlay(connection, revision_id)
                drawn = [
                    change.mark
                    for change in overlay.marks_for(key)
                    if change.kind == "set" and change.mark is not None
                ]
                if drawn:
                    right, top = marks_extent(drawn)
                    marks.append((name, right, top))
                boxes = tuple(
                    (float(place[2]), float(place[3]), float(place[4]), float(place[5]))
                    for _, _, place in overlay.units
                    if (place[0], place[1]) == key
                    and place[2] is not None
                    and place[3] is not None
                    and place[4] is not None
                    and place[5] is not None
                )
                if boxes:
                    units.append((name, boxes))
        return LayoutOverlayExtent(marks=tuple(marks), units=tuple(units))

    def list_equipment_scenarios(self) -> list[EquipmentScenarioSummary]:
        """설비 시나리오 목록(`list_order` 다음 이름 차례) — 각 최신·리비전 수와 함께."""
        with self._connect() as connection:
            return [_scenario_summary(row) for row in scenario_store.scenario_rows(connection)]

    def list_schedule_revisions(
        self, equipment_scenario_id: str, *, limit: int = 50
    ) -> list[EquipmentScheduleRevisionSummary]:
        """한 설비 시나리오의 일정 리비전, 번호 큰 것부터."""
        if limit <= 0:
            raise ValueError("설비 시나리오 리비전 조회 건수는 1 이상이어야 합니다.")
        with self._connect() as connection:
            rows = scenario_store.schedule_revision_rows(
                connection, equipment_scenario_id, limit=limit
            )
        return [_schedule_revision_summary(row) for row in rows]

    def load_scenario_catalog(self) -> EquipmentScenarioCatalog:
        """설비 시나리오 목록·최신 공식 발행·옛 배포 흔적 수를 **연결 하나**로 읽는다(목록
        캐시용)."""
        with self._connect() as connection:
            release = scenario_store.latest_release_row(connection)
            return EquipmentScenarioCatalog(
                scenarios=tuple(
                    _scenario_summary(row) for row in scenario_store.scenario_rows(connection)
                ),
                latest_release=_release(release) if release is not None else None,
                legacy_trace_count=legacy_trace_count(connection),
            )

    def official_scenario_id(self) -> str | None:
        """공식 설비 시나리오 — 최신 발행의 시나리오, 발행이 없으면 「운영 일정」(없으면 목록 첫
        시나리오). 시나리오가 하나도 없으면 None."""
        with self._connect() as connection:
            return scenario_store.official_scenario_id(connection)

    def latest_equipment_release(self) -> EquipmentRelease | None:
        """최신 공식 발행. 발행이 없으면 None."""
        with self._connect() as connection:
            row = scenario_store.latest_release_row(connection)
        return _release(row) if row is not None else None

    def legacy_trace_count(self) -> int:
        """이관 경계 뒤 계약 v3 이하 공통 리비전 수(옛 배포로 저장한 흔적)."""
        with self._connect() as connection:
            return legacy_trace_count(connection)

    def list_revisions(self, *, limit: int = 50) -> list[EquipmentRevisionSummary]:
        if limit <= 0:
            raise ValueError("설비 이력 조회 건수는 1 이상이어야 합니다.")
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {_REVISION_SUMMARY_PROJECTION}
                FROM equipment_ops.revision r
                ORDER BY r.revision_no DESC LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [_revision_summary(row) for row in rows]

    def save_standard_target_availability(self, data: pd.DataFrame) -> pd.DataFrame:
        """Upsert the unversioned current weekly availability used by target Capa."""
        prepared = prepare_weekly_availability(data)
        incoming = prepared.rename(
            columns={
                "공정": "process_name",
                "Weeknum": "weeknum",
                "가용대수": "available_count",
            }
        )
        view_name = f"_incoming_{uuid4().hex}"
        with self._write_transaction() as connection:
            connection.register(view_name, incoming)
            try:
                connection.execute(
                    f"""
                    DELETE FROM equipment_ops.standard_target_weekly_availability AS target
                    USING {view_name} AS incoming
                    WHERE target.process_name = incoming.process_name
                      AND target.weeknum = incoming.weeknum
                    """
                )
                connection.execute(
                    f"""
                    INSERT INTO equipment_ops.standard_target_weekly_availability (
                        process_name, weeknum, available_count
                    )
                    SELECT process_name, weeknum, available_count
                    FROM {view_name}
                    """
                )
            finally:
                connection.unregister(view_name)
        return self.load_standard_target_availability()

    def load_standard_target_availability(self) -> pd.DataFrame:
        """Load the current non-versioned process-week availability."""
        with self._connect() as connection:
            result = connection.execute(
                """
                SELECT process_name AS "공정", weeknum AS "Weeknum",
                       available_count AS "가용대수"
                FROM equipment_ops.standard_target_weekly_availability
                ORDER BY process_name, weeknum
                """
            ).fetchdf()
        if result.empty:
            return pd.DataFrame(columns=["공정", "Weeknum", "가용대수"])
        return prepare_weekly_availability(result)

    def clear_standard_target_availability(self) -> None:
        """Delete the current weekly availability without creating a revision."""
        with self._write_transaction() as connection:
            connection.execute("DELETE FROM equipment_ops.standard_target_weekly_availability")

    def save_process_cutoff(
        self, data: pd.DataFrame, *, expected_fingerprint: str | None = None
    ) -> pd.DataFrame:
        """공정별 Cut-off 를 **통째로 갈아 끼운다.** 리비전을 만들지 않는다.

        0005 의 주차별 가용대수는 들어온 키만 지우고 다시 넣는 부분 upsert 인데, 여기는
        전체 삭제 후 삽입이다. **이 표는 목록 자체가 계약**이기 때문이다 — 행을 지우는
        것이 「그 공정을 산출에서 빼라」는 뜻이라 부분 upsert 로는 그 편집을 표현할
        방법이 없다.

        전체 교체라 옛 초안으로 덮으면 그 사이 다른 사람이 저장한 행이 지워진다. 그래서 화면은
        편집을 시작할 때 본 표의 지문(`process_cutoff_fingerprint`)을 `expected_fingerprint` 로
        넘기고, 쓰기 잠금 안에서 지금 저장본의 지문과 다르면 아무것도 쓰지 않고
        `ProcessCutoffConflict` 를 올린다. None 이면 대조하지 않는다(시드·스크립트).
        """
        prepared = prepare_process_cutoff(data)
        incoming = prepared.rename(
            columns={
                "공정": "process_name",
                "제품구분": "product_scope",
                "Cutoff일수": "cutoff_days",
                "비고": "note",
            }
        )
        with self._write_transaction() as connection:
            if expected_fingerprint is not None and expected_fingerprint != (
                process_cutoff_fingerprint(_stored_process_cutoff(connection))
            ):
                raise ProcessCutoffConflict(
                    "다른 사용자가 먼저 공정별 Cut-off 를 저장해 이번 저장은 반영하지 않았습니다 — "
                    "저장은 표 전체를 갈아 끼우므로 옛 초안으로 쓰면 그 사이 저장된 행이 "
                    "지워집니다."
                )
            connection.execute("DELETE FROM equipment_ops.process_cutoff")
            if not incoming.empty:
                insert_by_name(
                    connection,
                    schema="equipment_ops",
                    table_name="process_cutoff",
                    frame=incoming,
                )
        return self.load_process_cutoff()

    def load_process_cutoff(self) -> pd.DataFrame:
        """저장된 공정별 Cut-off. 한 번도 저장하지 않았으면 빈 계약 프레임."""
        with self._connect() as connection:
            return _stored_process_cutoff(connection)

    def load_shortening_filter_profile(self) -> ShorteningFilterProfile:
        """필요 단축 일정 공용 조회 조건(0019). 한 번도 저장하지 않았으면 `version` 0 의 빈 값."""
        with self._connect() as connection:
            return _read_shortening_filter(connection)

    def load_floor_states(self) -> FloorStates:
        """Space 동·층 사용 상태(0029). 저장한 적이 없으면 `version` 0 의 빈 값(모두 사용)."""
        with self._connect() as connection:
            return read_floor_states(connection)

    def save_floor_states(
        self,
        inactive: Mapping[FloorKey, object],
        *,
        expected_version: int | None,
        source: str,
    ) -> bool:
        """동·층 사용 상태를 갈아 쓴다(비활성 층 → 사유 코드, 30개 층 전체 초안). 썼으면 True.

        설비 리비전을 만들지 않는다 — 설비 시나리오·공식 발행과 무관한 공용 현행값이다(S6).
        `expected_version` 은 화면이 편집을 시작할 때 본 version 이다 — 쓰기 잠금 안에서 지금
        version 과 다르면 아무것도 쓰지 않고 `ProfileVersionConflict` 를 올린다(None 은 대조하지
        않는다 — 시험·스크립트). 대조가 먼저, 같은지 보기가 다음이다. 같은 내용이면 쓰지 않는다
        (version·동기화 dirty 그대로). 쓰는 것은 바뀐 층뿐이다(`floor_state_store`).
        """
        rows = prepare_floor_states(inactive)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            require_profile_version(
                connection,
                "floor_state_profile",
                expected_version,
                label="층 사용 설정",
                schema="equipment_ops",
            )
            current = read_floor_states(connection)
            if current.rows == rows:
                return False
            write_floor_states(connection, current, rows, source=source)
            outcome.wrote = True
        return True

    def save_shortening_filter_months(
        self, start_month: object, end_month: object, *, source: str
    ) -> bool:
        """공용 조회 조건의 **기간만** 갈아 쓴다. 공정은 그대로다. 썼으면 True.

        Cut-off 처럼 리비전 없는 현행값이라 그 자리에서 고친다. 저장된 값과 같으면 쓰지 않는다 —
        공용 행이라 쓸 때마다 `version` 이 오르고 DB 가 dirty 가 된다. 견주기와 쓰기를 한
        트랜잭션에서 한다(콜백 하나에 연결 하나).
        """
        start, end = normalize_filter_month(start_month), normalize_filter_month(end_month)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            current = _read_shortening_filter(connection)
            if (current.start_month, current.end_month) == (start, end):
                return False
            _write_shortening_filter_header(connection, current, start, end, source)
            outcome.wrote = True
        return True

    def save_shortening_filter_processes(
        self, selected: Sequence[object], *, visible: Sequence[str], source: str
    ) -> bool:
        """공용 조회 조건의 **공정만** 갈아 쓴다. 기간은 그대로다. 썼으면 True.

        `visible` 은 화면이 보여 준 선택지다 — 그 밖의 저장 공정은 남긴다
        (`services/shortening_filter_profile.merge_filter_processes`). 같으면 쓰지 않는다.
        """
        visible_set = set(normalize_filter_processes(visible))
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            current = _read_shortening_filter(connection)
            merged = merge_filter_processes(current.processes, selected, visible_set)
            if merged == current.processes:
                return False
            _write_shortening_filter_header(
                connection, current, current.start_month, current.end_month, source
            )
            connection.execute(
                "DELETE FROM equipment_ops.shortening_filter_process WHERE profile_id = 1"
            )
            if merged:
                insert_by_name(
                    connection,
                    schema="equipment_ops",
                    table_name="shortening_filter_process",
                    frame=pd.DataFrame(
                        {
                            "profile_id": 1,
                            "process_name": list(merged),
                            "sort_order": range(len(merged)),
                        }
                    ),
                )
            outcome.wrote = True
        return True

    def save_shortening_baseline(
        self, draft: ShorteningBaselineDraft, *, saved_at: datetime | None = None
    ) -> ShorteningBaselineSummary:
        """필요 단축 일정 기준선을 새로 저장한다(0021). 고칠 수 없는 공용 기록이다.

        같은 이름이 있으면 `ValueError` 로 거절한다 — 견주기와 넣기를 한 쓰기 잠금·트랜잭션에서
        해서 두 사람이 같은 이름을 동시에 저장해도 하나만 들어간다. 저장 시각은 이 PC 의 벽시계다
        (목록의 저장일이 사용자가 본 날과 같아야 한다).
        """
        baseline_id = uuid4().hex
        moment = (saved_at or datetime.now()).replace(microsecond=0)
        with self._write_transaction() as connection:
            if baseline_name_exists(connection, draft.name):
                raise ValueError(f"같은 이름의 기준선이 이미 있습니다: {draft.name}")
            insert_baseline(connection, baseline_id=baseline_id, draft=draft, saved_at=moment)
        source = draft.provenance
        return ShorteningBaselineSummary(
            baseline_id=baseline_id,
            name=draft.name,
            saved_at=moment,
            plan_today=draft.plan_today,
            start_month=draft.start_month,
            end_month=draft.end_month,
            saved_by=source.saved_by,
            equipment_revision_id=source.equipment_revision_id,
            equipment_revision_no=source.equipment_revision_no,
            reference_version=source.reference_version,
            scenario_id=source.scenario_id,
            scenario_name=source.scenario_name,
            scenario_revision_id=source.scenario_revision_id,
            scenario_revision_no=source.scenario_revision_no,
            scenario_content_token=source.scenario_content_token,
        )

    def list_shortening_baselines(self) -> tuple[ShorteningBaselineSummary, ...]:
        """모든 필요 단축 일정 기준선 머리. 최근에 저장한 것이 위다."""
        with self._connect() as connection:
            return tuple(list_baselines(connection))

    def load_shortening_baseline(self, baseline_id: str) -> ShorteningBaseline:
        """기준선 한 벌. 없으면(누가 지웠으면) `ValueError` 다."""
        with self._connect() as connection:
            baseline = load_baseline(connection, baseline_id)
        if baseline is None:
            raise ValueError(f"기준선을 찾지 못했습니다(지워졌을 수 있습니다): {baseline_id}")
        return baseline

    def delete_shortening_baseline(self, baseline_id: str) -> bool:
        """기준선 한 벌을 지운다. 없었으면 아무것도 쓰지 않고 False."""
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            outcome.wrote = delete_baseline(connection, baseline_id)
        return outcome.wrote

    def save_floor_layout_image(
        self,
        building: str,
        floor: str,
        file_name: str,
        payload: bytes,
        *,
        canvas_width: float | None = None,
        canvas_height: float | None = None,
    ) -> FloorLayoutProfile:
        """Upsert one floor's background drawing without creating a revision."""
        _require_floor_key(building, floor)
        normalized_name, mime = normalize_image_upload(file_name, payload)
        if canvas_width is None or canvas_height is None:
            pixel_size = image_pixel_size(payload)
            if pixel_size is None:
                raise ValueError(f"도면 파일 형식을 읽지 못했습니다: {normalized_name}")
            width, height = canvas_from_pixel_size(*pixel_size)
        else:
            width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_marks_fit(connection, (building, floor), (width, height))
            _require_overlay_marks_fit(connection, (building, floor), (width, height))
            require_total_layout_budget(
                _floor_layout_bytes(connection, excluding=(building, floor))
                + _fab_layout_bytes(connection),
                len(payload),
            )
            row_exists, stored_digest = _stored_image_digest(connection, building, floor)
            if not row_exists:
                _insert_floor_layout(
                    connection, building, floor, width, height, (mime, normalized_name, payload)
                )
            elif stored_digest == hashlib.sha256(payload).hexdigest():
                # 같은 도면을 다시 올렸다. BLOB 을 다시 쓰면 DuckDB 가 이전 페이지를
                # 회수하지 않아 파일만 커지므로 나머지 컬럼만 고친다.
                connection.execute(
                    """
                    UPDATE equipment_ops.floor_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        updated_at = current_timestamp
                    WHERE building = ? AND floor_name = ?
                    """,
                    [width, height, mime, normalized_name, building, floor],
                )
            else:
                connection.execute(
                    """
                    UPDATE equipment_ops.floor_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        image_payload = ?, updated_at = current_timestamp
                    WHERE building = ? AND floor_name = ?
                    """,
                    [width, height, mime, normalized_name, payload, building, floor],
                )
        return self._require_floor_layout_profile(building, floor)

    def save_floor_layout_canvas(
        self,
        building: str,
        floor: str,
        canvas_width: float,
        canvas_height: float,
    ) -> FloorLayoutProfile:
        """Upsert one floor's canvas size and keep the stored drawing as is."""
        _require_floor_key(building, floor)
        width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_marks_fit(connection, (building, floor), (width, height))
            _require_overlay_marks_fit(connection, (building, floor), (width, height))
            _upsert_floor_canvas(connection, building, floor, width, height)
        return self._require_floor_layout_profile(building, floor)

    def load_floor_layout_marks(self, building: str, floor: str) -> tuple[FloorLayoutMark, ...]:
        """한 층의 도면 요소를 그리는 순서(`source_row_no`)대로 읽는다."""
        with self._connect() as connection:
            return _stored_floor_marks(connection, building, floor)

    def load_floor_group_labels(self, building: str, floor: str) -> dict[str, str]:
        """한 층의 Main 설비명 위치(Main 설비 → 가운데·위·아래). 고른 적이 없는 묶음은 행이 없어
        빠진다(그 모양의 처음 위치로 선다 — `space_layout_edit.default_group_label`)."""
        with self._connect() as connection:
            return _stored_group_labels(connection, building, floor)

    def replace_floor_layout_marks(
        self,
        building: str,
        floor: str,
        marks: Sequence[Mapping[str, object]],
    ) -> tuple[FloorLayoutMark, ...]:
        """한 층의 도면 요소를 통째로 갈아 끼운다. 리비전을 만들지 않는다. 빈 목록은 모두 지운다."""
        _require_floor_key(building, floor)
        with self._write_transaction() as connection:
            stored = _stored_floor_canvases(connection)
            canvas = stored.get((building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))
            _replace_floor_marks(
                connection, building, floor, prepare_floor_layout_marks(marks, canvas)
            )
        return self.load_floor_layout_marks(building, floor)

    def delete_floor_layout_profile(self, building: str, floor: str) -> None:
        """층 배경 도면과 캔버스를 지운다(리비전 없음). 도면 요소는 남긴다 — 지우면 캔버스가 기본
        크기로 돌아가므로, 그 밖에 요소가 있으면 거부한다(요소가 캔버스 밖에 남으면 그 층 요소를
        다시 저장할 수 없다)."""
        _require_floor_key(building, floor)
        with self._write_transaction() as connection:
            _require_marks_fit(
                connection, (building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
            )
            _require_overlay_marks_fit(
                connection, (building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
            )
            connection.execute(
                """
                DELETE FROM equipment_ops.floor_layout_profile
                WHERE building = ? AND floor_name = ?
                """,
                [building, floor],
            )

    def load_floor_layout_summaries(self) -> tuple[FloorLayoutCanvas, ...]:
        """Load every floor's canvas size without reading the drawing bytes."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT building, floor_name, canvas_width, canvas_height, image_name,
                       COALESCE(octet_length(image_payload), 0), updated_at
                FROM equipment_ops.floor_layout_profile
                ORDER BY building, floor_name
                """
            ).fetchall()
        return tuple(
            FloorLayoutCanvas(
                building=str(row[0]),
                floor=str(row[1]),
                canvas_width=float(row[2]),
                canvas_height=float(row[3]),
                image_name=str(row[4]) if row[4] is not None else None,
                image_byte_count=int(row[5]),
                updated_at=as_datetime(row[6]),
            )
            for row in rows
        )

    def load_floor_layout_canvases(self) -> dict[FloorKey, CanvasSize]:
        """Map (동, 층) to its canvas size for coordinate validation."""
        return {
            (summary.building, summary.floor): summary.canvas_size
            for summary in self.load_floor_layout_summaries()
        }

    def load_floor_layout_profile(self, building: str, floor: str) -> FloorLayoutProfile | None:
        """Load one floor's canvas size and its drawing as a plotly data URI."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT canvas_width, canvas_height, image_mime, image_name, image_payload,
                       updated_at
                FROM equipment_ops.floor_layout_profile
                WHERE building = ? AND floor_name = ?
                """,
                [building, floor],
            ).fetchone()
        if row is None:
            return None
        payload = row[4]
        mime = str(row[2]) if row[2] is not None else None
        has_image = isinstance(payload, (bytes, bytearray)) and bool(payload) and mime is not None
        image_bytes = bytes(payload) if has_image else b""
        return FloorLayoutProfile(
            building=building,
            floor=floor,
            canvas_width=float(row[0]),
            canvas_height=float(row[1]),
            image_data_uri=to_data_uri(str(mime), image_bytes) if has_image else None,
            image_name=str(row[3]) if row[3] is not None else None,
            image_byte_count=len(image_bytes),
            updated_at=as_datetime(row[5]),
        )

    def load_fab_layout_profile(self) -> FabLayoutProfile | None:
        """FAB 전체 도면의 캔버스와 배경 도면(data URI). 저장한 적이 없으면 None."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT canvas_width, canvas_height, image_mime, image_name, image_payload,
                       updated_at
                FROM equipment_ops.fab_layout_profile
                WHERE layout_key = ?
                """,
                [FAB_LAYOUT_KEY],
            ).fetchone()
        if row is None:
            return None
        payload = row[4]
        mime = str(row[2]) if row[2] is not None else None
        has_image = isinstance(payload, (bytes, bytearray)) and bool(payload) and mime is not None
        image_bytes = bytes(payload) if has_image else b""
        return FabLayoutProfile(
            canvas_width=float(row[0]),
            canvas_height=float(row[1]),
            image_data_uri=to_data_uri(str(mime), image_bytes) if has_image else None,
            image_name=str(row[3]) if row[3] is not None else None,
            image_byte_count=len(image_bytes),
            updated_at=as_datetime(row[5]),
        )

    def load_fab_layout_marks(self) -> tuple[FabLayoutMark, ...]:
        """저장된 FAB 요소(그리는 순서대로). 하나도 없으면 빈 튜플 — 화면은 기본 배치를 그린다."""
        with self._connect() as connection:
            return _stored_fab_marks(connection)

    def save_fab_layout(
        self,
        *,
        canvas: CanvasSize | None,
        marks: Sequence[Mapping[str, object]] | None,
        base: FabLayoutBase | None,
    ) -> bool:
        """FAB 캔버스·요소를 쓴다. **설비 리비전을 만들지 않는다**(층 도면 요소처럼 현행값이다).

        `base` 는 편집을 시작할 때 본 저장값(캔버스|None, 요소 지문)이다. 쓰기 잠금 안에서 지금
        저장값과 견줘 다르면 거부한다 — 요소는 전체 교체라 옛 목록으로 덮으면 남이 먼저 저장한 FAB
        가 지워진다. 캔버스 행이 없으면(처음 저장) 그 행도 함께 쓴다. 쓴 것이 있으면 True."""
        size = normalize_canvas_size(*canvas) if canvas is not None else None
        if size is None and marks is None:
            return False
        with self._write_transaction() as connection:
            stored_canvas = _stored_fab_canvas(connection)
            if base is not None:
                _require_fab_layout_base(connection, stored_canvas, base)
            target = size or stored_canvas or FAB_CANVAS
            prepared: tuple[FabLayoutMark, ...] | None = None
            if marks is not None:
                prepared = prepare_fab_layout_marks(marks, target)
                # 빈 목록이면 기본 배치를 그린다 — 그 기본 배치도 캔버스 안이어야 한다.
                require_fab_layout_fits(target, prepared)
            else:
                # 캔버스만 바꾼다 — 지금 그리는 요소(저장된 것, 없으면 기본 배치)가 새 캔버스
                # 안이어야 한다.
                _require_fab_marks_fit(connection, target)
            if size is not None or stored_canvas is None:
                _upsert_fab_canvas(connection, *target)
            if prepared is not None:
                _replace_fab_marks(connection, prepared)
        return True

    def save_fab_layout_image(
        self,
        file_name: str,
        payload: bytes,
        *,
        canvas_width: float | None = None,
        canvas_height: float | None = None,
    ) -> FabLayoutProfile:
        """FAB 배경 도면을 올린다(리비전 없음). 층 도면과 같은 용량 규칙이고 합계는 전 층과 함께
        센다."""
        normalized_name, mime = normalize_image_upload(file_name, payload)
        if canvas_width is None or canvas_height is None:
            pixel_size = image_pixel_size(payload)
            if pixel_size is None:
                raise ValueError(f"도면 파일 형식을 읽지 못했습니다: {normalized_name}")
            width, height = canvas_from_pixel_size(*pixel_size)
        else:
            width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, (width, height))
            require_total_layout_budget(
                _floor_layout_bytes(connection), len(payload), subject="FAB 도면"
            )
            row = connection.execute(
                "SELECT sha256(image_payload) FROM equipment_ops.fab_layout_profile "
                "WHERE layout_key = ?",
                [FAB_LAYOUT_KEY],
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO equipment_ops.fab_layout_profile (
                        layout_key, canvas_width, canvas_height, image_mime, image_name,
                        image_payload
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [FAB_LAYOUT_KEY, width, height, mime, normalized_name, payload],
                )
            elif row[0] is not None and str(row[0]) == hashlib.sha256(payload).hexdigest():
                # 같은 도면을 다시 올렸다. BLOB 을 다시 쓰지 않는다(DuckDB 가 옛 페이지를 회수하지
                # 않는다).
                connection.execute(
                    """
                    UPDATE equipment_ops.fab_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        updated_at = current_timestamp
                    WHERE layout_key = ?
                    """,
                    [width, height, mime, normalized_name, FAB_LAYOUT_KEY],
                )
            else:
                connection.execute(
                    """
                    UPDATE equipment_ops.fab_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        image_payload = ?, updated_at = current_timestamp
                    WHERE layout_key = ?
                    """,
                    [width, height, mime, normalized_name, payload, FAB_LAYOUT_KEY],
                )
        return self._require_fab_layout_profile()

    def save_fab_layout_canvas(self, canvas_width: float, canvas_height: float) -> FabLayoutProfile:
        """FAB 캔버스 치수만 저장한다(도면은 그대로). 지금 그리는 요소가 새 캔버스 안이어야 한다."""
        width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, (width, height))
            _upsert_fab_canvas(connection, width, height)
        return self._require_fab_layout_profile()

    def delete_fab_layout_profile(self) -> None:
        """FAB 배경 도면과 캔버스를 지운다(리비전 없음). 캔버스는 기본 `FAB_CANVAS` 로 돌아가고
        요소는 남는다 — 그 밖에 요소가 있으면 거부한다."""
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, FAB_CANVAS)
            connection.execute(
                "DELETE FROM equipment_ops.fab_layout_profile WHERE layout_key = ?",
                [FAB_LAYOUT_KEY],
            )

    def _require_fab_layout_profile(self) -> FabLayoutProfile:
        profile = self.load_fab_layout_profile()
        if profile is None:
            raise RuntimeError("FAB 도면 프로필을 저장하지 못했습니다.")
        return profile

    def _require_floor_layout_profile(self, building: str, floor: str) -> FloorLayoutProfile:
        profile = self.load_floor_layout_profile(building, floor)
        if profile is None:
            raise RuntimeError(f"층 도면 프로필을 저장하지 못했습니다: {building} {floor}")
        return profile

    @contextmanager
    def _write_transaction(
        self, outcome: _WriteOutcome | None = None
    ) -> Iterator[duckdb.DuckDBPyConnection]:
        with _WRITE_LOCK, self._connect() as connection, transaction(connection):
            yield connection
        # COMMIT 이 끝나고 연결이 닫힌 뒤에만 표시한다. `sync_state` 는 등록되지 않은
        # 환경에서 아무 파일도 만들지 않으므로 개발 PC·CI 동작은 그대로다. 아무것도 쓰지 않은
        # 저장은 표시하지 않는다 — dirty 가 서면 다른 PC 의 새 세대를 받지 못한다.
        if outcome is None or outcome.wrote:
            sync_state.mark_dirty(self._database_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect(self._database_path)


def _require_floor_key(building: str, floor: str) -> None:
    if building not in VALID_BUILDINGS or floor not in VALID_FLOORS:
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {building} {floor}")


def _read_shortening_filter(connection: duckdb.DuckDBPyConnection) -> ShorteningFilterProfile:
    """열린 연결에서 필요 단축 일정 공용 조회 조건을 읽는다. 헤더가 없으면 빈 값(`version` 0)."""
    header = connection.execute(
        """
        SELECT start_month, end_month, version, source, updated_at
        FROM equipment_ops.shortening_filter_profile
        WHERE profile_id = 1
        """
    ).fetchone()
    if header is None:
        return ShorteningFilterProfile()
    processes = connection.execute(
        """
        SELECT process_name
        FROM equipment_ops.shortening_filter_process
        WHERE profile_id = 1
        ORDER BY sort_order, process_name
        """
    ).fetchall()
    return ShorteningFilterProfile(
        start_month=None if header[0] is None else int(header[0]),
        end_month=None if header[1] is None else int(header[1]),
        processes=tuple(str(row[0]) for row in processes),
        version=int(header[2]),
        source=str(header[3]),
        updated_at=header[4],
    )


def _write_shortening_filter_header(
    connection: duckdb.DuckDBPyConnection,
    current: ShorteningFilterProfile,
    start_month: int | None,
    end_month: int | None,
    source: str,
) -> None:
    """헤더 한 행을 다음 `version` 으로 쓴다. 쓰기 트랜잭션 안에서만 부른다.

    행이 있으면 키가 아닌 칸만 UPDATE 하고 없으면 넣는다 — 공정 자식 행은 건드리지 않는다.
    """
    values = [start_month, end_month, current.version + 1, source]
    if current.version == 0:
        connection.execute(
            """
            INSERT INTO equipment_ops.shortening_filter_profile (
                profile_id, start_month, end_month, version, source
            ) VALUES (1, ?, ?, ?, ?)
            """,
            values,
        )
        return
    connection.execute(
        """
        UPDATE equipment_ops.shortening_filter_profile
        SET start_month = ?, end_month = ?, version = ?, source = ?,
            updated_at = current_timestamp
        WHERE profile_id = 1
        """,
        values,
    )


def _latest_revision(connection: duckdb.DuckDBPyConnection) -> tuple[str, int] | None:
    """(최신 리비전 id, 번호). 리비전이 없으면 None."""
    row = connection.execute(
        """
        SELECT revision_id, revision_no FROM equipment_ops.revision
        ORDER BY revision_no DESC LIMIT 1
        """
    ).fetchone()
    return (str(row[0]), int(row[1])) if row is not None else None


def _revision_row(
    connection: duckdb.DuckDBPyConnection, revision_id: str
) -> tuple[EquipmentRevisionSummary, int]:
    """(공통 리비전 요약, 계약 버전). 없으면 `KeyError`."""
    row = connection.execute(
        f"""
        SELECT {_REVISION_SUMMARY_PROJECTION}, r.equipment_contract_version
        FROM equipment_ops.revision r
        WHERE r.revision_id = ?
        """,
        [revision_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"설비 이력을 찾을 수 없습니다: {revision_id}")
    contract_version = int(row[8]) if row[8] is not None else 2
    return _revision_summary(row), contract_version


def _read_legacy_snapshot(
    connection: duckdb.DuckDBPyConnection, revision_id: str
) -> EquipmentSnapshot:
    """계약 v3 이하 리비전 하나를 옛 길 그대로 읽는다 — 마스터에 일정 칸이 함께 든 리비전이다.

    설비 DB `0027` 이관 리비전의 일정 원천이기도 하다(「운영 일정」 rK 의 `legacy_revision_id`).
    계약 v4(공통 대장만 든 리비전 — 일정 칸 NULL, 비가동 없음)를 이 길로 읽으면 일정이 모두 빈
    마스터가 되므로 받지 않는다 — `read_merged` 로 읽는다. 일정 리비전을 모르므로 `schedule` 은
    None 이다.
    """
    summary, contract_version = _revision_row(connection, revision_id)
    return _legacy_snapshot(connection, revision_id, summary, contract_version)


def _legacy_snapshot(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    summary: EquipmentRevisionSummary,
    contract_version: int,
) -> EquipmentSnapshot:
    if contract_version >= 4:
        raise ValueError(
            f"공통 r{summary.revision_no} 은 설비 시나리오 뒤의 공통 대장 리비전(계약 "
            f"{contract_version})이라 옛 길로 읽지 않습니다 — 일정 리비전과 합쳐 읽으세요."
        )
    baseline = _load_baseline(connection, revision_id)
    if contract_version == 3:
        equipment = _load_equipment_master(connection, revision_id)
        downtime = _load_downtime_schedule(connection, revision_id)
    else:
        equipment = _load_legacy_equipment(connection, revision_id)
        if equipment.empty:
            equipment = _load_legacy_schedule(connection, revision_id)
        downtime = _load_legacy_downtime(connection, revision_id)
    prepared_equipment = prepare_equipment_master(equipment.reindex(columns=EQUIPMENT_COLUMNS))
    return EquipmentSnapshot(
        revision=summary,
        baseline=prepare_equipment_baseline(baseline.reindex(columns=BASELINE_COLUMNS)),
        equipment=prepared_equipment,
        downtime=prepare_downtime_for_prepared_equipment(
            downtime.reindex(columns=DOWNTIME_COLUMNS), prepared_equipment
        ),
    )


def _legacy_unit_keys(equipment: pd.DataFrame) -> dict[str, str]:
    """옛 리비전 호기의 키 — 설비명마다 `legacy_unit_key`(행 차례).

    옛 행의 `unit_key` 는 늘 NULL 이다 — 새 판은 계약 v4 로만 쓰고 옛 판은 그 칸을 모른다.
    """
    return {str(name): legacy_unit_key(str(name)) for name in equipment[EQUIPMENT_ID_COLUMN]}


def read_common(connection: duckdb.DuckDBPyConnection, common_revision_id: str) -> CommonFrames:
    """공통 대장 리비전 하나 — 기존 보유대수와 공통 32칸 + 호기 키. 일정 칸은 아예 없다.

    계약 v4 는 마스터 표에서 공통 칸과 `COALESCE(unit_key, 'n' || md5(equipment_id))` 만 고른다. v3
    이하는 `_read_legacy_snapshot` 의 결과(읽기 투영·옛 변환이 걸린 것)에서 일정 칸을 버린다. 둘 다
    읽기 검증을 지난 값이다.
    """
    summary, contract_version = _revision_row(connection, common_revision_id)
    return _common_frames(connection, common_revision_id, summary, contract_version, checked=True)


def _common_frames(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    summary: EquipmentRevisionSummary,
    contract_version: int,
    *,
    checked: bool,
) -> CommonFrames:
    """공통 쪽 프레임. `checked=False` 는 v4 마스터를 검증 없이 돌려준다(합친 뒤 한 번 검증)."""
    if contract_version < 4:
        legacy = _legacy_snapshot(connection, revision_id, summary, contract_version)
        common, _ = split_equipment(legacy.equipment, _legacy_unit_keys(legacy.equipment))
        return CommonFrames(summary, contract_version, legacy.baseline, common)
    baseline = prepare_equipment_baseline(
        _load_baseline(connection, revision_id).reindex(columns=BASELINE_COLUMNS)
    )
    master = connection.execute(
        f"""
        SELECT {_COMMON_MASTER_PROJECTION}
        FROM equipment_ops.equipment_master_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    master = master.reindex(columns=list(COMMON_FRAME_COLUMNS))
    if checked:
        keys = dict(
            zip(
                master[EQUIPMENT_ID_COLUMN].astype(str),
                master[UNIT_KEY_COLUMN].astype(str),
                strict=True,
            )
        )
        prepared = prepare_equipment_master(
            master.drop(columns=[UNIT_KEY_COLUMN]).reindex(columns=EQUIPMENT_COLUMNS)
        )
        master, _ = split_equipment(prepared, keys)
    return CommonFrames(summary, contract_version, baseline, master)


def read_schedule(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str
) -> ScheduleFrames:
    """설비 시나리오 일정 리비전 하나 — 키별 일곱 칸과 키별 비가동(계약 형으로 맞춘 것).

    이관 리비전(`legacy_revision_id`)은 `_read_legacy_snapshot` 의 일정 칸·비가동을 키로 바꿔 쓴다 —
    읽기 투영(Qual 자리표 → 빈칸)·계약 v2 변환·레거시 비가동 중복 제거가 그대로 걸린다. 이관
    리비전은 그 리비전의 모든 호기에 일정 행이 있다. 그 밖은 새 두 표에서 읽는다.
    """
    summary = _require_schedule_revision(connection, schedule_revision_id)
    return _schedule_frames(connection, summary)


def _require_schedule_revision(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str
) -> EquipmentScheduleRevisionSummary:
    row = scenario_store.schedule_revision_row(connection, schedule_revision_id)
    if row is None:
        raise KeyError(f"설비 시나리오 리비전을 찾을 수 없습니다: {schedule_revision_id}")
    return _schedule_revision_summary(row)


def _schedule_frames(
    connection: duckdb.DuckDBPyConnection, summary: EquipmentScheduleRevisionSummary
) -> ScheduleFrames:
    if summary.legacy_revision_id is not None:
        legacy = _read_legacy_snapshot(connection, summary.legacy_revision_id)
        keys = _legacy_unit_keys(legacy.equipment)
        _, schedule = split_equipment(legacy.equipment, keys)
        downtime = split_downtime(legacy.downtime, keys)
    else:
        schedule = scenario_store.schedule_frame(connection, summary.schedule_revision_id)
        downtime = scenario_store.schedule_downtime_frame(connection, summary.schedule_revision_id)
    return ScheduleFrames(
        revision=summary,
        schedule=normalize_schedule_frame(schedule),
        downtime=normalize_schedule_downtime(downtime),
    )


def read_layout_overlay(
    connection: duckdb.DuckDBPyConnection,
    schedule_revision: EquipmentScheduleRevisionSummary | str | None,
) -> LayoutOverlay:
    """일정 리비전 하나의 배치 차이(설비 0031). 리비전이 None·이관 리비전·지문이 NULL(0031 을 모르는
    코드가 쓴 리비전)이거나 빈 차이 지문이면 **질의 없이** 빈 차이다 — 흔한 경우(공식·이관)에 조회가
    하나 줄고, 옛 코드 리비전에 남의 행이 섞일 일이 없다. 사내 확인 스크립트도 이 함수를 쓴다."""
    if schedule_revision is None:
        return LayoutOverlay()
    summary = (
        _require_schedule_revision(connection, schedule_revision)
        if isinstance(schedule_revision, str)
        else schedule_revision
    )
    if summary.legacy_revision_id is not None or summary.layout_digest == EMPTY_LAYOUT_DIGEST:
        return LayoutOverlay()
    return scenario_store.layout_overlay(connection, summary.schedule_revision_id)


def read_merged(
    connection: duckdb.DuckDBPyConnection,
    common_revision_id: str,
    schedule_revision_id: str | None,
) -> EquipmentSnapshot:
    """공통 리비전 + 일정 리비전을 합친 스냅샷(39칸).

    - 공통과 일정이 **같은 레거시 리비전**이면(이관 직후의 공식) 레거시 읽기 한 번으로 둘 다 낸다 —
      그 리비전의 모든 호기에 일정 행이 있으므로 합친 결과가 레거시 읽기 그대로다.
    - 그 밖은 공통 행 차례대로 키로 붙인다(`merge_equipment`). 일정 행이 없는 호기는 일정 칸이 비고
      `unscheduled_units` 에 든다. 공통에 없는 키의 일정·비가동 행은 버리고 `orphan_rows` 에 센다.
      비가동의 설비명은 키로 지금 공통 이름을 붙인다.
    - 합친 **뒤, 읽기 검증 앞**에 그 리비전의 호기 배치 차이를 얹는다(`apply_unit_overlay` — 설비
      0031, 예외 없음). 이관 리비전은 차이가 없어 레거시 빠른 길 그대로다.
    - 끝에 읽기 검증(`prepare_equipment_master`·`prepare_downtime_for_prepared_equipment` —
      캔버스·오늘 없이)을 한다. 실패하면 `EquipmentScenarioIncompatible(시나리오명, rN, 까닭)`.
    - `schedule_revision_id` 가 None 이면 일정 리비전이 없는 것이다 — 모든 호기가 일정 없음이다.
    """
    summary, contract_version = _revision_row(connection, common_revision_id)
    schedule = (
        _require_schedule_revision(connection, schedule_revision_id)
        if schedule_revision_id is not None
        else None
    )
    if (
        schedule is not None
        and schedule.legacy_revision_id is not None
        and schedule.legacy_revision_id == common_revision_id
    ):
        legacy = _legacy_snapshot(connection, common_revision_id, summary, contract_version)
        return replace(
            legacy,
            schedule=schedule,
            unit_key_pairs=tuple(_legacy_unit_keys(legacy.equipment).items()),
        )
    common = _common_frames(
        connection, common_revision_id, summary, contract_version, checked=False
    )
    frames = _schedule_frames(connection, schedule) if schedule is not None else None
    return _merge_read(connection, common, frames)


def _merge_read(
    connection: duckdb.DuckDBPyConnection,
    common: CommonFrames,
    schedule: ScheduleFrames | None,
) -> EquipmentSnapshot:
    """읽어 둔 공통·일정을 합치고 그 리비전의 호기 배치 차이를 얹은 뒤 읽기 검증을 한다
    (`read_merged` 의 일반 길)."""
    merged = merge_equipment(
        common.equipment,
        schedule.schedule if schedule is not None else pd.DataFrame(columns=SCHEDULE_FRAME_COLUMNS),
        schedule.downtime
        if schedule is not None
        else pd.DataFrame(columns=SCHEDULE_DOWNTIME_COLUMNS),
    )
    overlay = read_layout_overlay(connection, schedule.revision if schedule is not None else None)
    applied = apply_unit_overlay(merged.equipment, merged.unit_key_pairs, overlay.units)
    try:
        equipment = prepare_equipment_master(applied.equipment)
        downtime = prepare_downtime_for_prepared_equipment(merged.downtime, equipment)
    except ValueError as error:
        if schedule is None:
            raise
        revision = schedule.revision
        name = scenario_store.scenario_name(connection, revision.equipment_scenario_id)
        reason = f"{error} (배치 차이를 얹은 뒤)" if overlay.units else str(error)
        raise EquipmentScenarioIncompatible(
            name or revision.equipment_scenario_id, revision.revision_no, reason
        ) from error
    return EquipmentSnapshot(
        revision=common.revision,
        baseline=common.baseline,
        equipment=equipment,
        downtime=downtime,
        schedule=schedule.revision if schedule is not None else None,
        unit_key_pairs=merged.unit_key_pairs,
        unscheduled_units=merged.unscheduled_units,
        orphan_rows=merged.orphan_rows,
        layout_official_places=applied.official_places,
        layout_orphans=applied.orphans,
        layout_regrouped=applied.regrouped,
    )


def _unmergeable_trace_message(refusal: str) -> str:
    return (
        f"옛 배포로 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 이어 쓰지 않았습니다 — "
        f"{refusal} 이어 쓰면 그 일정을 다시 읽을 수 없습니다. 런북 4-2 대로 백업을 복원하세요."
    )


def _trace_merge_refusal(connection: duckdb.DuckDBPyConnection, common_id: str) -> str | None:
    """공통 `common_id` 가 ACTIVE 시나리오마다의 최신·최신 공식 발행과 합쳐지는가. 첫 실패의 까닭
    (「「운영 일정」 r2 … 필수입니다」), 다 합쳐지면 None."""
    targets: list[str] = []
    for row in scenario_store.scenario_rows(connection):
        latest = row.get("latest_schedule_revision_id")
        if row.get("status") == "ACTIVE" and isinstance(latest, str):
            targets.append(latest)
    release = scenario_store.latest_release_row(connection)
    if release is not None and str(release["schedule_revision_id"]) not in targets:
        targets.append(str(release["schedule_revision_id"]))
    for schedule_id in targets:
        try:
            read_merged(connection, common_id, schedule_id)
        except EquipmentScenarioIncompatible as error:
            return f"「{error.scenario_name}」 r{error.revision_no} 일정과 합치면 {error.reason}"
    return None


def _pre_trace_revision_id(connection: duckdb.DuckDBPyConnection) -> str | None:
    """흔적 앞 공통 대장 — 흔적(경계 뒤 계약 v3 이하)이 아닌 리비전 가운데 번호가 가장 큰 것."""
    row = connection.execute(
        """
        SELECT r.revision_id
        FROM equipment_ops.revision r
        WHERE NOT (
            COALESCE(r.equipment_contract_version, 2) <= 3
            AND r.revision_no > COALESCE(
                (SELECT b.through_revision_no FROM equipment_ops.equipment_legacy_boundary b
                 ORDER BY b.boundary_no DESC LIMIT 1),
                0
            )
        )
        ORDER BY r.revision_no DESC LIMIT 1
        """
    ).fetchone()
    return str(row[0]) if row is not None else None


def _common_keys(connection: duckdb.DuckDBPyConnection, revision_id: str) -> set[str]:
    summary, contract_version = _revision_row(connection, revision_id)
    common = _common_frames(connection, revision_id, summary, contract_version, checked=False)
    return {str(key) for key in common.equipment[UNIT_KEY_COLUMN]}


def _legacy_trace_review(connection: duckdb.DuckDBPyConnection) -> LegacyTraceReview:
    count = legacy_trace_count(connection)
    if count == 0:
        return LegacyTraceReview()
    latest = _latest_revision(connection)
    assert latest is not None
    before = _pre_trace_revision_id(connection)
    dropped = (
        len(_common_keys(connection, before) - _common_keys(connection, latest[0]))
        if before is not None
        else 0
    )
    return LegacyTraceReview(
        count=count,
        trace_revision_no=latest[1],
        dropped_units=dropped,
        refusal=_trace_merge_refusal(connection, latest[0]),
    )


def read_official_pair(connection: duckdb.DuckDBPyConnection) -> tuple[str, str | None] | None:
    """(공통 최신, 최신 공식 발행의 일정 리비전).

    공통 리비전이 없으면 None, 발행이 없으면 둘째가 None 이다. 공통은 시나리오와 무관하게 늘
    최신이다(E2 — 실적·호기 정보는 공식이 옛 리비전이어도 최신으로 보인다).
    """
    latest = _latest_revision(connection)
    if latest is None:
        return None
    release = scenario_store.latest_release_row(connection)
    return latest[0], str(release["schedule_revision_id"]) if release is not None else None


def legacy_trace_count(connection: duckdb.DuckDBPyConnection) -> int:
    """이관 경계 뒤 계약 v3 이하 공통 리비전 수 — 옛 배포로 저장한 흔적이다(0 이 아니면 저장을
    막는다)."""
    return scenario_store.legacy_trace_count(connection)


# 설비 마스터 저장의 세 갈래 — `save_equipment` 는 바뀐 쪽만, 래퍼 `save_space_layout` 은 하나라도
# 바뀌면 두 쪽 다, 래퍼 `save_snapshot` 은 늘 두 쪽 다.
_SaveMode = Literal["changed", "if_any", "always"]

DUPLICATE_EQUIPMENT_SCENARIO_NAME_MESSAGE = (
    "같은 이름의 설비 시나리오가 이미 있습니다(보관본 포함). 이름을 바꿔 저장하세요."
)
# 일정 리비전 리비전명 글자 수 한도(선택지·표에서 리비전 번호가 밀려나지 않게) — 화면 칸도 이 수다.
SCHEDULE_REVISION_NAME_MAX_CHARS = 40


@dataclass(frozen=True)
class _SaveOutcome:
    """저장 한 번의 결과와 저장 뒤 (공통 최신, 이 시나리오 일정) 쌍 — 래퍼가 그 합친 스냅샷을
    읽는다."""

    result: EquipmentSaveResult
    common_revision_id: str | None
    schedule_revision_id: str | None


@dataclass(frozen=True)
class _BaseState:
    """저장 전 저장본 — 공통 최신과 출발 일정 리비전을 합쳐 **다시 정규화한** 것(편집본과 같은 꼴).

    `schedule` 은 일정 행이 있던 호기만(키 + 일곱 칸), `downtime` 은 키 + 다섯 칸이다.
    `contract_version` 이 None 이면 저장본이 없다. `common` 의 배치 일곱 칸은 출발 리비전의 배치
    차이를 얹은 **편집을 시작한 값**(설계 6-1 의 E0)이고, `official_common` 은 같은 행에 공통 최신의
    **공식 배치**(C)를 둔 것이다 — 공통이 바뀌었는지는 늘 공식 쪽과 견준다. `layout` 은 공식 배치
    (키·일곱 칸·Main 설비·묶음), `started_places` 는 E0 일곱 칸, `overlay` 는 출발 리비전의 배치
    차이(원시)다.
    """

    contract_version: int | None
    unit_keys: dict[str, str]
    scheduled_keys: frozenset[str]
    baseline: pd.DataFrame
    common: pd.DataFrame
    schedule: pd.DataFrame
    downtime: pd.DataFrame
    official_common: pd.DataFrame
    layout: LayoutBase
    started_places: Mapping[str, Place]
    overlay: LayoutOverlay


@dataclass(frozen=True)
class _EditFrames:
    """검증을 마친 편집본을 키로 나눈 것. `schedule` 은 이번 리비전에 쓸 일정 행이다."""

    unit_keys: dict[str, str]
    new_keys: frozenset[str]
    common: pd.DataFrame
    schedule: pd.DataFrame
    downtime: pd.DataFrame
    new_units: tuple[str, ...]
    removed_units: tuple[str, ...]


@dataclass(frozen=True)
class _PropagationPlan:
    """함께 넣기를 받을 시나리오 하나 — 그 최신 위에 새 호기·새 비가동을 더한 일정."""

    scenario: EquipmentScenarioSummary
    schedule: pd.DataFrame
    downtime: pd.DataFrame
    unit_count: int
    downtime_added: tuple[tuple[str, str, str], ...]
    skipped: int
    # 받는 시나리오 최신의 배치 차이를 이 저장 뒤의 공식으로 정규화한 것(새 리비전이 그대로 옮긴다).
    layout: LayoutOverlay = LayoutOverlay()

    @property
    def writes(self) -> bool:
        return self.unit_count > 0 or bool(self.downtime_added)


@dataclass(frozen=True)
class _PublishPlan:
    """이번 저장이 발행할 시나리오(없으면 None)와 발행을 미룬 사실."""

    scenario_id: str | None = None
    withheld: bool = False


def _wrapper_request(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    note: str | None,
    floor_canvases: Mapping[FloorKey, CanvasSize] | None,
    floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None,
    base_revision_id: str | None,
    floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None,
    floor_group_labels: Mapping[FloorKey, Mapping[str, object]] | None,
) -> EquipmentSaveRequest:
    """호환 래퍼의 저장 요청 — 시나리오와 출발 일정은 쓰기 잠금 안에서 공식으로 정한다."""
    return EquipmentSaveRequest(
        baseline=baseline,
        equipment=equipment,
        downtime=downtime,
        equipment_scenario_id="",
        base_common_revision_id=base_revision_id or EMPTY_REVISION_TOKEN,
        base_schedule_revision_id=None,
        note=note,
        floor_canvases=floor_canvases,
        floor_marks=floor_marks,
        floor_layout_bases=floor_layout_bases,
        floor_group_labels=floor_group_labels,
    )


def _clean_text(value: str | None) -> str | None:
    """앞뒤 공백을 뗀 글자. 비면 None."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def _schedule_revision_label(name: str | None) -> str | None:
    """리비전명 — 앞뒤 공백을 떼고 비면 None. `SCHEDULE_REVISION_NAME_MAX_CHARS` 자를 넘으면
    `ValueError`(자르지 않는다 — 적은 이름이 말없이 바뀌지 않게)."""
    label = _clean_text(name)
    if label is not None and len(label) > SCHEDULE_REVISION_NAME_MAX_CHARS:
        raise ValueError(
            f"리비전명은 {SCHEDULE_REVISION_NAME_MAX_CHARS}자까지입니다(지금 {len(label)}자)."
        )
    return label


def _required_scenario_name(name: str) -> str:
    text = name.strip()
    if not text:
        raise ValueError("설비 시나리오 이름을 적으세요.")
    return text


def _require_active_scenario(
    scenarios: Mapping[str, EquipmentScenarioSummary],
    equipment_scenario_id: str,
    *,
    verb: str = "저장·발행할",
) -> EquipmentScenarioSummary:
    """ACTIVE 시나리오 한 줄. 없거나 보관했으면 `ValueError`(`verb` 는 「저장·발행할」 따위)."""
    scenario = scenarios.get(equipment_scenario_id)
    if scenario is None:
        raise ValueError(f"설비 시나리오를 찾을 수 없습니다: {equipment_scenario_id}")
    if scenario.status != "ACTIVE":
        subject = with_topic_particle(f"「{scenario.scenario_name}」")
        raise ValueError(f"{subject} 보관한 설비 시나리오라 {verb} 수 없습니다.")
    return scenario


def _scenario_map(connection: duckdb.DuckDBPyConnection) -> dict[str, EquipmentScenarioSummary]:
    """설비 시나리오 id → 한 줄(각 최신·리비전 수와 함께)."""
    return {
        summary.equipment_scenario_id: summary
        for summary in map(_scenario_summary, scenario_store.scenario_rows(connection))
    }


def _require_scenario_summary(
    connection: duckdb.DuckDBPyConnection, equipment_scenario_id: str
) -> EquipmentScenarioSummary:
    for row in scenario_store.scenario_rows(connection):
        if str(row["equipment_scenario_id"]) == equipment_scenario_id:
            return _scenario_summary(row)
    raise ValueError(f"설비 시나리오를 찾을 수 없습니다: {equipment_scenario_id}")


def _rows_for(frame: pd.DataFrame, keys: Iterable[str]) -> pd.DataFrame:
    """키 칸이 `keys` 에 드는 행만(차례 그대로)."""
    wanted = frame[UNIT_KEY_COLUMN].astype("string").isin(list(keys)).fillna(False)
    return frame.loc[wanted.to_numpy(dtype=bool)].reset_index(drop=True)


def _stack(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """행을 이어 붙인다. 빈 표는 건너뛴다(빈 표가 칸 형을 흔들지 않게)."""
    filled = [frame for frame in frames if not frame.empty]
    if not filled:
        return frames[0].iloc[0:0].reset_index(drop=True)
    if len(filled) == 1:
        return filled[0].reset_index(drop=True)
    return pd.concat(filled, ignore_index=True)


def _scheduled_frames(snapshot: EquipmentSnapshot) -> tuple[pd.DataFrame, pd.DataFrame]:
    """합친 스냅샷을 다시 (일정 행이 있던 호기의 키 + 일곱 칸, 키 + 비가동) 로 나눈다."""
    keys = snapshot.unit_keys
    _, schedule = split_equipment(snapshot.equipment, keys)
    scheduled = {
        key for name, key in snapshot.unit_key_pairs if name not in snapshot.unscheduled_units
    }
    return _rows_for(schedule, scheduled), split_downtime(snapshot.downtime, keys)


def _restore_preview(
    connection: duckdb.DuckDBPyConnection,
    common_revision_id: str,
    current_schedule_revision_id: str | None,
    target: EquipmentScheduleRevisionSummary,
) -> tuple[ScheduleRestorePreview, EquipmentSnapshot, LayoutOverlay]:
    """(되돌리기 차이, 고른 리비전을 그 공통과 합친 한 벌, 가정 시나리오로 되돌릴 때 쓸 배치 차이).
    확인 글과 되돌리기 쓰기가 같이 쓴다.

    「그 리비전 뒤에 공통 대장에 든 호기」 는 그 리비전을 저장할 때 함께 본 공통
    대장(`common_revision_id`)에 키가 없는 호기다. 함께 본 공통이 비어 있으면(그런 저장은 없다) 그
    리비전에 일정이 있는 호기를 그때의 호기로 본다.

    쓸 배치 차이는 고른 리비전의 차이를 지금 공통·층 현행값으로 정규화한 것이다(그 뒤 지운 호기·
    공식과 같아진 행이 빠진다). 지금 최신의 차이도 같은 기준으로 정규화해 지문을 싣는다 —
    「쓸 것 없음」(`restore_writes_nothing`)과 확인 글이 실제로 쓸 차이를 보게(원시 지문만 보면 지운
    호기의 차이를 「되살립니다」 라 하고 바뀐 것이 없는 리비전을 만든다).
    """
    restored = read_merged(connection, common_revision_id, target.schedule_revision_id)
    current = (
        restored
        if current_schedule_revision_id == target.schedule_revision_id
        else read_merged(connection, common_revision_id, current_schedule_revision_id)
    )
    if target.common_revision_id is None:
        source_keys: Collection[str] = {
            key for name, key in restored.unit_key_pairs if name not in restored.unscheduled_units
        }
    elif target.common_revision_id == common_revision_id:
        source_keys = {key for _, key in restored.unit_key_pairs}
    else:
        source_keys = _common_keys(connection, target.common_revision_id)
    preview = schedule_restore_preview(current, restored, source_unit_keys=source_keys)
    current_summary = current.schedule
    selected = read_layout_overlay(connection, target)
    moved = 0
    if selected.units and target.common_revision_id not in (None, common_revision_id):
        assert target.common_revision_id is not None
        then = _common_places(connection, target.common_revision_id)
        now = _official_layout(restored).places
        moved = sum(
            1
            for key, place in now.items()
            if key in then and key not in selected.unit_keys and then[key] != place
        )

    def digest(summary: EquipmentScheduleRevisionSummary | None) -> str | None:
        value = summary.layout_digest if summary is not None else EMPTY_LAYOUT_DIGEST
        return None if value == EMPTY_LAYOUT_DIGEST else value

    def effective(overlay: LayoutOverlay) -> str | None:
        value = overlay.digest()
        return None if value == EMPTY_LAYOUT_DIGEST else value

    stored_now = read_layout_overlay(connection, current_summary)
    official_layout = _official_layout(restored)
    floors = _stored_floors(connection, (*selected.floors, *stored_now.floors))
    layout = normalize_layout_overlay(selected, official_layout, floors)
    effective_now = normalize_layout_overlay(stored_now, official_layout, floors)
    return (
        replace(
            preview,
            layout_unit_rows=target.layout_unit_count,
            layout_mark_rows=target.layout_mark_count,
            layout_label_rows=target.layout_label_count,
            current_layout_unit_rows=current_summary.layout_unit_count if current_summary else 0,
            current_layout_mark_rows=current_summary.layout_mark_count if current_summary else 0,
            current_layout_label_rows=current_summary.layout_label_count if current_summary else 0,
            layout_digest=digest(target),
            current_layout_digest=digest(current_summary),
            layout_moved_since=moved,
            restored_layout_unit_rows=len(layout.units),
            restored_layout_mark_rows=layout.mark_count,
            restored_layout_label_rows=layout.label_count,
            restored_layout_digest=effective(layout),
            current_effective_layout_digest=effective(effective_now),
        ),
        restored,
        layout,
    )


def _common_places(connection: duckdb.DuckDBPyConnection, revision_id: str) -> dict[str, Place]:
    """공통 리비전 하나의 배치 일곱 칸(호기 키마다) — 불변 리비전이라 확인 재료 캐시에 실을 수
    있다."""
    summary, contract_version = _revision_row(connection, revision_id)
    common = _common_frames(connection, revision_id, summary, contract_version, checked=False)
    keys = [str(key) for key in common.equipment[UNIT_KEY_COLUMN]]
    return dict(layout_base(common.equipment, keys).places)


def _layout_publish_preview(
    connection: duckdb.DuckDBPyConnection,
    target: EquipmentScheduleRevisionSummary,
    *,
    newest_schedule_revision_id: str | None,
    snapshot: Callable[[], EquipmentSnapshot],
) -> LayoutPublishPreview:
    """공식 발행의 배치 판정 한 곳(설계 6-5) — 발행 쓰기와 확인 팝업이 같이 쓴다.

    발행할 리비전과 그 시나리오 최신의 배치 차이를 지금 공식(공통 최신 + 층 현행값)으로 정규화해,
    저장된 행이 둘 다 없으면 "publish", 행은 있지만 정규화하면 비고 발행할 리비전이 최신이면
    "clean", 그 밖은 "blocked"(실효 수). `snapshot` 은 발행할 리비전을 공통 최신과 합친 한 벌을
    부를 때 읽는다 — 차이가 없으면 읽지 않는다.
    """
    selected = read_layout_overlay(connection, target)
    is_newest = newest_schedule_revision_id == target.schedule_revision_id
    newest = selected if is_newest else read_layout_overlay(connection, newest_schedule_revision_id)
    stored = LayoutPublishPreview(
        stored_units=len(selected.units),
        stored_marks=selected.mark_count,
        stored_labels=selected.label_count,
        newest_rows=len(newest.units) + newest.mark_count + newest.label_count,
        is_newest=is_newest,
    )
    if not selected and not newest:
        return stored
    official = _official_layout(snapshot())
    # 공통에서 지운 호기의 행은 정규화가 버린다 — 「공식과 같아진」 행과 따로 센다(정리·막힘 글).
    stored = replace(
        stored,
        orphan_units=_orphan_unit_rows(selected, official),
        newest_orphan_units=_orphan_unit_rows(newest, official),
    )
    floors = _stored_floors(connection, {*selected.floors, *newest.floors})
    normalized = normalize_layout_overlay(selected, official, floors)
    if is_newest and not normalized:
        return replace(stored, action="clean")
    # 발행할 리비전과 최신의 실효를 따로 센다 — 막힘 글이 실제로 다른 쪽만 「실효」 로 적는다.
    latest = normalized if is_newest else normalize_layout_overlay(newest, official, floors)
    return replace(
        stored,
        action="blocked",
        units=overlay_unit_count(normalized, official),
        marks=normalized.mark_count,
        labels=normalized.label_count,
        newest_units=overlay_unit_count(latest, official),
        newest_marks=latest.mark_count,
        newest_labels=latest.label_count,
    )


def _orphan_unit_rows(overlay: LayoutOverlay, official: LayoutBase) -> int:
    """저장된 호기 차이 행 가운데 지금 공통 대장에 없는 호기 키의 행 수(정규화 1 — 버리는 행)."""
    return sum(1 for key, _, _ in overlay.units if key not in official.places)


def _layout_publishable(
    connection: duckdb.DuckDBPyConnection,
    scenario: EquipmentScenarioSummary,
    target: EquipmentScheduleRevisionSummary,
    snapshot: EquipmentSnapshot,
    *,
    common_revision_id: str,
    saved_by: str | None,
) -> str:
    """공식 발행 막기·정리(설계 6-5) — 발행할 일정 리비전 id 를 돌려준다(정리 리비전을 썼으면
    그 id). 판정은 `_layout_publish_preview` 한 곳이다 — "clean" 이면 차이를 비운 `layout_clear`
    리비전을 써서 그것을, "blocked" 면 `EquipmentLayoutPublishBlocked`(실효 수)다.
    """
    preview = _layout_publish_preview(
        connection,
        target,
        newest_schedule_revision_id=scenario.latest_schedule_revision_id,
        snapshot=lambda: snapshot,
    )
    if preview.action == "publish":
        return target.schedule_revision_id
    if preview.action == "clean":
        schedule, downtime = _scheduled_frames(snapshot)
        return _insert_schedule(
            connection,
            equipment_scenario_id=scenario.equipment_scenario_id,
            origin="layout_clear",
            common_revision_id=common_revision_id,
            note="공식과 같아진 배치 차이 정리",
            saved_by=saved_by,
            schedule=schedule,
            downtime=downtime,
            layout=LayoutOverlay(),
        )
    release = scenario_store.latest_release_row(connection)
    official = release is not None and (
        str(release["equipment_scenario_id"]) == scenario.equipment_scenario_id
    )
    raise EquipmentLayoutPublishBlocked(
        scenario.scenario_name,
        target.revision_no,
        preview.units,
        preview.marks,
        preview.labels,
        message=layout_publish_blocked_words(
            preview.block(
                scenario.scenario_name,
                target.revision_no,
                scenario.latest_revision_no or target.revision_no,
                official=official,
            )
        ),
    )


def _read_base_state(
    connection: duckdb.DuckDBPyConnection,
    common_revision_id: str | None,
    schedule_revision_id: str | None,
) -> _BaseState:
    """저장 전 저장본(쓰기 잠금 안). 읽은 합친 스냅샷을 편집본과 같은 정규화에 다시 태운다 —
    저장 당시 감사 해시가 아니라 이 값과 내용 해시로 「그대로인가」 를 견준다."""
    if common_revision_id is None:
        common, schedule = split_equipment(empty_equipment_master(), {})
        empty = layout_base(common, [])
        return _BaseState(
            contract_version=None,
            unit_keys={},
            scheduled_keys=frozenset(),
            baseline=pd.DataFrame(columns=list(BASELINE_COLUMNS)),
            common=common,
            schedule=schedule,
            downtime=normalize_schedule_downtime(
                pd.DataFrame(columns=list(SCHEDULE_DOWNTIME_COLUMNS))
            ),
            official_common=common,
            layout=empty,
            started_places={},
            overlay=LayoutOverlay(),
        )
    contract_version = _revision_row(connection, common_revision_id)[1]
    snapshot = read_merged(connection, common_revision_id, schedule_revision_id)
    equipment = prepare_equipment_master(snapshot.equipment)
    downtime = prepare_downtime_for_prepared_equipment(snapshot.downtime, equipment)
    renormalized = replace(snapshot, equipment=equipment, downtime=downtime)
    schedule, events = _scheduled_frames(renormalized)
    common, _ = split_equipment(equipment, snapshot.unit_keys)
    keys = [str(key) for key in common[UNIT_KEY_COLUMN]]
    started = layout_base(common, keys)
    official = started.with_places(dict(snapshot.layout_official_places))
    official_common = common
    if snapshot.layout_official_places:
        # 차이를 얹은 호기의 공식 칸은 공통 대장 그 리비전의 **원래 값**으로 되돌린다 — 스냅샷이
        # 든 얹기 전 값(`layout_official_places`)은 견줄 꼴(반올림)이라 그대로 적으면 공통이
        # 바뀐 것으로 보여 다른 까닭의 공통 저장이 공식 좌표를 반올림해 쓴다.
        stored = read_common(connection, common_revision_id).equipment
        official_common = common_with_places(
            common,
            keys,
            official.places,
            current=started.places,
            official=layout_cells(stored, [str(key) for key in stored[UNIT_KEY_COLUMN]]),
        )
    return _BaseState(
        contract_version=contract_version,
        unit_keys=snapshot.unit_keys,
        scheduled_keys=frozenset(
            key for name, key in snapshot.unit_key_pairs if name not in snapshot.unscheduled_units
        ),
        baseline=prepare_equipment_baseline(snapshot.baseline),
        common=common,
        schedule=schedule,
        downtime=events,
        official_common=official_common,
        layout=official,
        started_places=started.places,
        overlay=read_layout_overlay(connection, snapshot.schedule),
    )


def _official_layout(snapshot: EquipmentSnapshot) -> LayoutBase:
    """합친 스냅샷의 공통에 깔린 **공식** 배치(얹은 차이를 공식 일곱 칸으로 되돌린 것)."""
    keys = snapshot.unit_keys
    names = [str(name) for name in snapshot.equipment[EQUIPMENT_ID_COLUMN]]
    started = layout_base(snapshot.equipment, [keys[name] for name in names])
    return started.with_places(dict(snapshot.layout_official_places))


def _stored_floors(
    connection: duckdb.DuckDBPyConnection, floors: Iterable[FloorKey]
) -> dict[FloorKey, OfficialFloor]:
    """층마다 저장된 공식 값(도면 요소, Main 설비명 위치)."""
    return {
        key: (_stored_floor_marks(connection, *key), _stored_group_labels(connection, *key))
        for key in sorted(set(floors))
    }


def _moved_labels(labels: Mapping[str, str], moves: Mapping[str, str]) -> dict[str, str]:
    """Main 설비 이름 바꿈(옛 → 새)을 따라간 이름표. 새 이름에 이미 행이 있으면 그 행이 남는다."""
    if not moves:
        return dict(labels)
    result = {name: spot for name, spot in labels.items() if name not in moves}
    for name, spot in labels.items():
        if name in moves:
            result.setdefault(moves[name], spot)
    return dict(sorted(result.items()))


class _OfficialFloors:
    """이 저장 뒤의 층 공식 값(요소·Main 설비명 위치) — 쓰기 전에 메모리에서 낸다. 공식 역할이면
    이 저장이 갈아 끼울 층은 그 값, 나머지는 저장값이고, Main 설비 이름 바꿈의 공식 이름표 키 옮기기
    (`moves` — 옛 → 새)를 따라간다. 가정 시나리오 배치 차이를 정규화하는 기준이다(설계 5-6)."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        marks: Mapping[FloorKey, tuple[FloorLayoutMark, ...]],
        labels: Mapping[FloorKey, Mapping[str, str]],
        moves: Mapping[str, str],
    ) -> None:
        self._connection = connection
        self._marks = marks
        self._labels = labels
        self._moves = moves
        self._floors: dict[FloorKey, OfficialFloor] = {}

    def floor(self, key: FloorKey) -> OfficialFloor:
        if key not in self._floors:
            marks = (
                self._marks[key]
                if key in self._marks
                else _stored_floor_marks(self._connection, *key)
            )
            labels = (
                dict(self._labels[key])
                if key in self._labels
                else _moved_labels(_stored_group_labels(self._connection, *key), self._moves)
            )
            self._floors[key] = (marks, labels)
        return self._floors[key]

    def for_overlay(self, overlay: LayoutOverlay) -> dict[FloorKey, OfficialFloor]:
        return {key: self.floor(key) for key in overlay.floors}


def _split_edit(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    base: _BaseState,
    renames: Mapping[str, str],
) -> _EditFrames:
    """검증한 편집본에 호기 키를 정하고(`assign_unit_keys`) 공통·일정·비가동으로 나눈다."""
    names = [str(name) for name in equipment[EQUIPMENT_ID_COLUMN]]
    keys = assign_unit_keys(names, base.unit_keys, renames)
    common, schedule_all = split_equipment(equipment, keys)
    events = split_downtime(downtime, keys)
    new_keys = new_unit_keys(keys.values(), base.unit_keys.values())
    schedule = select_schedule_rows(
        schedule_all,
        previously_scheduled=base.scheduled_keys,
        downtime_keys={str(key) for key in events[UNIT_KEY_COLUMN]},
        new_keys=new_keys,
    )
    kept = set(keys.values())
    return _EditFrames(
        unit_keys=keys,
        new_keys=new_keys,
        common=common,
        schedule=schedule,
        downtime=events,
        new_units=tuple(name for name in names if keys[name] in new_keys),
        removed_units=tuple(name for name, key in base.unit_keys.items() if key not in kept),
    )


def _common_digest(baseline: pd.DataFrame, common: pd.DataFrame) -> tuple[str, str]:
    """공통 쪽 내용 해시 — 기존 보유대수 + 공통 32칸·키(행 차례 그대로 — 차례도 공통 내용이다)."""
    return (
        _content_hash(baseline.reindex(columns=list(BASELINE_COLUMNS)).reset_index(drop=True)),
        _content_hash(common.reindex(columns=list(COMMON_FRAME_COLUMNS)).reset_index(drop=True)),
    )


def _schedule_digest(schedule: pd.DataFrame, downtime: pd.DataFrame) -> tuple[str, str]:
    """일정 쪽 내용 해시 — 키 차례로 정렬한 일정 행 + 비가동. 공통에서 행 차례만 바꾸거나 이름만
    바꾼 저장은 일정이 그대로다."""
    rows = (
        schedule.reindex(columns=list(SCHEDULE_FRAME_COLUMNS))
        .sort_values(UNIT_KEY_COLUMN, kind="stable")
        .reset_index(drop=True)
    )
    events = downtime.reindex(columns=list(SCHEDULE_DOWNTIME_COLUMNS)).reset_index(drop=True)
    return _content_hash(rows), _content_hash(events)


def _plan_propagations(
    connection: duckdb.DuckDBPyConnection,
    request: EquipmentSaveRequest,
    scenarios: Mapping[str, EquipmentScenarioSummary],
    *,
    target: EquipmentScenarioSummary,
    base: _BaseState,
    edit: _EditFrames,
    layout_base: LayoutBase,
    official_floors: _OfficialFloors,
) -> list[_PropagationPlan]:
    """함께 넣기(F6·F2 — 「넣을 때」 만) — 다른 ACTIVE 시나리오마다 그 최신 위에 더할 것.

    - 새 호기(키가 저장본 공통에 없던 호기)는 이 시나리오와 같은 일정 행·비가동으로 들어간다 —
      `request.propagate_units` 가 있으면 그 이름의 새 호기만(새 호기마다 고름, 개편 명세 D8),
      없으면 `propagate_new_units` 하나로 모두 또는 아무것도.
    - 새 비가동(`new_downtime_rows` — 고친 것은 빠진다)은 받는 시나리오에 그 호기 일정 행이 없거나
      같은 (호기, 유형, 시작일) 이 이미 있으면 건너뛴다(비가동만 들어가 호기가 들어가지 않게).
    - 받는 시나리오의 고아 행(지금 공통에 없는 키)은 새 리비전에 옮기지 않는다.
    - 받는 시나리오 최신의 배치 차이는 이 저장 뒤의 공식(`layout_base`·`official_floors`)으로
      정규화해 그대로 옮긴다(설계 6-4). 새 호기는 차이가 없다 — 공통의 자리(가정 대상에서 넣은 새
      호기는 자리 없음)로 들어간다.
    더할 것도 건너뛴 것도 없는 시나리오는 계획에 없다.
    """
    unit_keys = _propagated_unit_keys(request, edit)
    fresh = (
        new_downtime_rows(
            base.downtime,
            edit.downtime,
            exclude_keys=edit.new_keys,
            unit_keys=edit.unit_keys.values(),
        )
        if request.propagate_new_downtime
        else edit.downtime.iloc[0:0]
    )
    if not unit_keys and fresh.empty:
        return []
    unit_rows = _rows_for(edit.schedule, unit_keys)
    unit_events = _rows_for(edit.downtime, unit_keys)
    known = set(edit.unit_keys.values())
    name_by_key = {key: name for name, key in edit.unit_keys.items()}
    fresh_ids = downtime_identities(fresh)
    plans: list[_PropagationPlan] = []
    for other in scenarios.values():
        if other.equipment_scenario_id == target.equipment_scenario_id or other.status != "ACTIVE":
            continue
        overlay = LayoutOverlay()
        if other.latest_schedule_revision_id is not None:
            frames = read_schedule(connection, other.latest_schedule_revision_id)
            schedule, downtime = frames.schedule, frames.downtime
            overlay = read_layout_overlay(connection, frames.revision)
        else:
            schedule = normalize_schedule_frame(pd.DataFrame(columns=list(SCHEDULE_FRAME_COLUMNS)))
            downtime = normalize_schedule_downtime(
                pd.DataFrame(columns=list(SCHEDULE_DOWNTIME_COLUMNS))
            )
        schedule = _rows_for(schedule, known)
        downtime = _rows_for(downtime, known)
        present = {str(key) for key in schedule[UNIT_KEY_COLUMN]}
        added_rows = unit_rows.loc[
            ~unit_rows[UNIT_KEY_COLUMN].astype("string").isin(list(present)).to_numpy(dtype=bool)
        ]
        added_keys = {str(key) for key in added_rows[UNIT_KEY_COLUMN]}
        receiving = present | added_keys
        taken = set(downtime_identities(downtime))
        accepted: list[int] = []
        listed: list[tuple[str, str, str]] = []
        skipped = 0
        for position, identity in enumerate(fresh_ids):
            if identity[0] not in receiving or identity in taken:
                skipped += 1
                continue
            accepted.append(position)
            taken.add(identity)
            listed.append((name_by_key[identity[0]], identity[1], identity[2]))
        if added_rows.empty and not listed and not skipped:
            continue
        plans.append(
            _PropagationPlan(
                scenario=other,
                schedule=_stack([schedule, added_rows]),
                downtime=_stack(
                    [
                        downtime,
                        _rows_for(unit_events, added_keys),
                        fresh.iloc[accepted].reset_index(drop=True),
                    ]
                ),
                unit_count=len(added_rows),
                downtime_added=tuple(listed),
                skipped=skipped,
                layout=normalize_layout_overlay(
                    overlay, layout_base, official_floors.for_overlay(overlay)
                ),
            )
        )
    return plans


def _propagated_unit_keys(request: EquipmentSaveRequest, edit: _EditFrames) -> frozenset[str]:
    """다른 시나리오에 함께 넣을 새 호기 키 — 새 호기마다 고른 이름(`propagate_units`)이 있으면 그
    이름의 새 호기만, 없으면 `propagate_new_units` 하나로 모두 또는 아무것도. 이름은 검증을 마친
    편집본의 설비명(앞뒤 공백 뗀 것)으로 맞댄다."""
    if request.propagate_units is None:
        return edit.new_keys if request.propagate_new_units else frozenset()
    wanted = {name.strip() for name in request.propagate_units}
    return frozenset(
        key for name, key in edit.unit_keys.items() if key in edit.new_keys and name in wanted
    )


def _propagation_note(source_name: str, plan: _PropagationPlan) -> str:
    """함께 넣은 리비전의 메모 — 「「운영 일정」 저장에서 새 호기 2대·비가동 1건 함께 넣음」."""
    parts = []
    if plan.unit_count:
        parts.append(f"새 호기 {plan.unit_count}대")
    if plan.downtime_added:
        parts.append(f"비가동 {len(plan.downtime_added)}건")
    return f"「{source_name}」 저장에서 {'·'.join(parts)} 함께 넣음"


def _plan_publish(
    scenarios: Mapping[str, EquipmentScenarioSummary],
    release: EquipmentRelease | None,
    *,
    target: EquipmentScenarioSummary,
    write_schedule: bool,
    propagated_ids: Collection[str],
    publish_official: bool,
    expected_release_no: int | None,
    force_publish: bool,
) -> _PublishPlan:
    """이번 저장이 공식 발행을 하는가(쓰기 전에 정한다).

    공식 시나리오에 새 일정 리비전이 생기고(이 저장이든 함께 넣기든) 저장 전 최신 발행이 그
    시나리오의 최신이었을 때만 발행한다 — 남이 발행하지 않은 더 새 리비전을 함께 내지 않게. 그런
    리비전이 있으면 발행을 미룬다(`withheld`). 발행이 하나도 없으면 이 저장의 일정 리비전이 v1
    이다 — 「공식으로 발행」 을 꺼도 그렇다(끄는 것은 지금 공식을 남긴다는 뜻인데 남길 공식이 없다.
    발행 없는 상태로 두면 세션 판정은 그 시나리오 최신을 공식 자리로 보는데 공식 스냅샷은 일정 없이
    읽혀 둘이 갈라진다). 발행할 때만 `expected_release_no` 를 대조한다. 설비 마스터 저장과
    「이 리비전으로 되돌리기」(E7)가 이 한 규칙을 쓴다.
    """
    plan = _PublishPlan()
    if release is None:
        if write_schedule:
            plan = _PublishPlan(target.equipment_scenario_id)
    else:
        official = release.equipment_scenario_id
        creates = (
            official == target.equipment_scenario_id and write_schedule
        ) or official in propagated_ids
        if creates:
            official_scenario = scenarios.get(official)
            before = (
                official_scenario.latest_schedule_revision_id
                if official_scenario is not None
                else None
            )
            if force_publish or (publish_official and release.schedule_revision_id == before):
                plan = _PublishPlan(official)
            elif publish_official:
                plan = _PublishPlan(withheld=True)
    if plan.scenario_id is not None and expected_release_no is not None:
        current = release.release_no if release is not None else 0
        if expected_release_no != current:
            raise EquipmentReleaseMoved(expected_release_no, current)
    return plan


def _cross_validate(
    connection: duckdb.DuckDBPyConnection,
    scenarios: Mapping[str, EquipmentScenarioSummary],
    release: EquipmentRelease | None,
    *,
    common: pd.DataFrame,
    target: EquipmentScenarioSummary,
    base_schedule_id: str | None,
    write_schedule: bool,
    propagations: Sequence[_PropagationPlan],
    publishing: bool,
) -> None:
    """이번 저장 뒤의 공통을 모든 시나리오(자기 포함)의 이번 저장 뒤 최신과, 거기에 없으면 최신
    공식 발행 리비전과 합쳐 읽기 검증한다. 하나라도 실패하면 `EquipmentScenarioGuardError`.

    이 시나리오가 일정도 쓰면 그 짝은 편집본 검증이 이미 본 것이라 건너뛴다. 낡은 세션(rJ 를 보며
    공통만 저장)도 자기 시나리오의 최신 rM 을 지킨다. 이번 저장이 발행하면 옛 공식은 더 이상
    공식이 아니라 보지 않는다.

    합칠 때 각 리비전의 배치 차이(함께 넣기는 계획이 옮길 정규화한 차이)를 얹은 **뒤** 검증한다 —
    공통에서 지운 호기의 차이는 버려질 뿐 막지 않는다(설계 6-4).
    """
    planned = {plan.scenario.equipment_scenario_id: plan for plan in propagations if plan.writes}
    checked: set[str] = set()
    for scenario in scenarios.values():
        if scenario.status != "ACTIVE":
            continue
        latest_id = scenario.latest_schedule_revision_id
        subject = with_object_particle(f"「{scenario.scenario_name}」")
        if scenario.equipment_scenario_id == target.equipment_scenario_id:
            if write_schedule or latest_id is None:
                continue
            checked.add(latest_id)
            frames = read_schedule(connection, latest_id)
            overlay = read_layout_overlay(connection, frames.revision)
            escape = (
                f"최신 r{scenario.latest_revision_no}"
                f"{object_particle(str(scenario.latest_revision_no))} 불러와 그 일정을 맞춘 뒤 "
                "저장하거나, 바꾼 공통 칸을 되돌리세요."
                if latest_id != base_schedule_id
                else "그 호기의 일정을 고치거나, 바꾼 공통 칸을 되돌리세요."
            )
            _require_mergeable(
                common,
                frames.schedule,
                frames.downtime,
                overlay=overlay,
                scenario_name=scenario.scenario_name,
                revision_no=scenario.latest_revision_no or 0,
                escape=escape,
            )
        elif scenario.equipment_scenario_id in planned:
            plan = planned[scenario.equipment_scenario_id]
            _require_mergeable(
                common,
                plan.schedule,
                plan.downtime,
                overlay=plan.layout,
                scenario_name=scenario.scenario_name,
                revision_no=(scenario.latest_revision_no or 0) + 1,
                escape=f"{subject} 불러와 그 일정을 고친 뒤 저장하거나, 함께 넣기를 끄거나, "
                "바꾼 공통 칸을 되돌리세요.",
            )
        elif latest_id is not None:
            checked.add(latest_id)
            frames = read_schedule(connection, latest_id)
            _require_mergeable(
                common,
                frames.schedule,
                frames.downtime,
                overlay=read_layout_overlay(connection, frames.revision),
                scenario_name=scenario.scenario_name,
                revision_no=scenario.latest_revision_no or 0,
                escape=f"{subject} 불러와 그 일정을 고친 뒤 저장하거나, 바꾼 공통 칸을 되돌리세요.",
            )
    if release is None or publishing or release.schedule_revision_id in checked:
        return
    official = read_schedule(connection, release.schedule_revision_id)
    owner = scenarios.get(release.equipment_scenario_id)
    _require_mergeable(
        common,
        official.schedule,
        official.downtime,
        overlay=read_layout_overlay(connection, official.revision),
        scenario_name=owner.scenario_name if owner is not None else release.equipment_scenario_id,
        revision_no=official.revision.revision_no,
        escape="그 리비전은 공식 발행이라 지켜야 합니다 — 다른 리비전을 공식으로 발행한 뒤 "
        "저장하거나, 바꾼 공통 칸을 되돌리세요.",
    )


def _require_mergeable(
    common: pd.DataFrame,
    schedule: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    overlay: LayoutOverlay,
    scenario_name: str,
    revision_no: int,
    escape: str,
) -> None:
    """공통 + 일정 한 벌에 배치 차이(호기)를 얹은 것이 읽기 검증(캔버스·오늘 없이)을 통과하는가 —
    `read_merged` 와 같은 차례(합치기 → 배치 차이 → 검증)다."""
    merged = merge_equipment(common, schedule, downtime)
    applied = apply_unit_overlay(merged.equipment, merged.unit_key_pairs, overlay.units)
    try:
        equipment = prepare_equipment_master(applied.equipment)
        prepare_downtime_for_prepared_equipment(merged.downtime, equipment)
    except ValueError as error:
        reason = f"{error} (배치 차이를 얹은 뒤)" if overlay.units else str(error)
        raise EquipmentScenarioGuardError(scenario_name, revision_no, reason, escape) from error


def _require_final_read(
    connection: duckdb.DuckDBPyConnection,
    scenario: EquipmentScenarioSummary,
    common_id: str | None,
    schedule_id: str,
) -> None:
    """가정 리비전을 쓴 저장의 끝 확인(I4) — 같은 연결에서 새 쌍을 `read_merged` 로 다시 읽는다.
    실패하면 `EquipmentScenarioGuardError`(트랜잭션째 되돌아간다)."""
    if common_id is None:
        return
    try:
        read_merged(connection, common_id, schedule_id)
    except EquipmentScenarioIncompatible as error:
        raise EquipmentScenarioGuardError(
            scenario.scenario_name,
            error.revision_no,
            f"배치 차이를 얹으면 {error.reason}",
            "그 배치 편집을 되돌리거나 최신을 불러와 다시 고치세요.",
        ) from error


def _overlay_after_edit(
    started: LayoutOverlay,
    units: Sequence[tuple[str, str | None, Place]],
    prepared_marks: Mapping[FloorKey, Sequence[FloorLayoutMark]],
    prepared_labels: Mapping[FloorKey, Mapping[str, str]],
    official_floors: _OfficialFloors,
) -> LayoutOverlay:
    """가정 역할 저장의 새 배치 차이 — 호기는 `split_layout` 결과, 층은 편집기가 낸 **합친** 전체를
    그 층 공식과 견준 차이(바꾸지 않은 층은 출발 리비전의 차이를 지금 공식으로 정규화)."""
    marks: dict[FloorKey, tuple[MarkChange, ...]] = {}
    labels: dict[FloorKey, tuple[tuple[str, str | None], ...]] = {}
    for key in sorted({*started.floors, *prepared_marks, *prepared_labels}):
        official_marks, official_labels = official_floors.floor(key)
        if key in prepared_marks:
            marks[key] = mark_changes(prepared_marks[key], official_marks)
        elif started.marks_for(key):
            marks[key] = mark_changes(
                effective_floor_marks(official_marks, started.marks_for(key)), official_marks
            )
        if key in prepared_labels:
            labels[key] = label_changes(prepared_labels[key], official_labels)
        elif started.labels_for(key):
            labels[key] = label_changes(
                effective_group_labels(official_labels, started.labels_for(key)), official_labels
            )
    return make_layout_overlay(units, marks, labels)


def _parent_names(common: pd.DataFrame) -> set[str]:
    values = common[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
    return {str(value) for value in values.dropna() if str(value)}


def _group_label_moves(
    group_renames: Mapping[str, str], before: pd.DataFrame, after: pd.DataFrame
) -> dict[str, str]:
    """이 저장의 Main 설비 이름 바꿈(저장본 이름 → 새 이름) — 저장본에 있던 이름이 편집본에서
    사라지고 새 이름이 들어선 것만. `group_renames` 는 지금 이름 → 저장본 이름이다."""
    saved = _parent_names(before)
    edited = _parent_names(after)
    return {
        origin: now
        for now, origin in group_renames.items()
        if now != origin and origin in saved and origin not in edited and now in edited
    }


def _move_group_labels(connection: duckdb.DuckDBPyConnection, moves: Mapping[str, str]) -> bool:
    """공식 Main 설비명 위치(층 현행값)의 옛 이름 행을 새 이름으로 옮긴다 — 배치를 바꾸는 것이
    아니라 정체성을 따라가는 것이라 어느 역할이든 한다(설계 5-4, 그러지 않으면 공식 위치가 처음
    위치로 돌아간다). 옮긴 행이 있으면 True."""
    if not moves:
        return False
    placeholders = ", ".join(["?"] * len(moves))
    rows = connection.execute(
        f"""
        SELECT DISTINCT building, floor_name
        FROM equipment_ops.floor_layout_group_label
        WHERE parent_equipment_id IN ({placeholders})
        """,
        list(moves),
    ).fetchall()
    for building, floor in rows:
        key = (str(building), str(floor))
        _replace_group_labels(
            connection, *key, _moved_labels(_stored_group_labels(connection, *key), moves)
        )
    return bool(rows)


def _insert_schedule(
    connection: duckdb.DuckDBPyConnection,
    *,
    equipment_scenario_id: str,
    origin: str,
    common_revision_id: str | None,
    note: str | None,
    saved_by: str | None,
    schedule: pd.DataFrame,
    downtime: pd.DataFrame,
    layout: LayoutOverlay,
    revision_name: str | None = None,
) -> str:
    """일정 리비전 하나를 넣는다 — 일정 행은 키 차례, 감사 해시는 넣는 값 그대로.

    `layout` 은 **기본값 없는** 키워드다 — 빠뜨린 호출이 배치안을 말없이 버리지 않게 mypy 가 잡는다
    (설계 6-6). 부르는 곳은 모두 정규화한 값을 넘기고(공식 시나리오는 빈 것), 지문은 늘 적힌다.
    `origin` 은 `SCHEDULE_REVISION_ORIGINS` 가운데 하나여야 한다."""
    if origin not in SCHEDULE_REVISION_ORIGINS:
        raise ValueError(f"일정 리비전 출처를 알 수 없습니다: {origin!r}")
    rows = normalize_schedule_frame(
        schedule.reindex(columns=list(SCHEDULE_FRAME_COLUMNS)).sort_values(
            UNIT_KEY_COLUMN, kind="stable"
        )
    )
    events = normalize_schedule_downtime(downtime)
    return scenario_store.insert_schedule_revision(
        connection,
        equipment_scenario_id=equipment_scenario_id,
        origin=origin,
        common_revision_id=common_revision_id,
        note=note,
        saved_by=saved_by,
        schedule=rows,
        downtime=events,
        schedule_hash=hash_frame(rows),
        downtime_hash=hash_frame(events),
        layout=layout,
        revision_name=revision_name,
    )


def _paired_snapshot(
    connection: duckdb.DuckDBPyConnection, common_revision_id: str
) -> EquipmentSnapshot:
    """호환 래퍼 `load_snapshot` 의 뜻 — 공통 하나와, 공식 시나리오에서 그 공통을 함께 본 마지막
    일정 리비전."""
    summary, contract_version = _revision_row(connection, common_revision_id)
    official = scenario_store.official_scenario_id(connection)
    paired = (
        scenario_store.paired_schedule_revision_id(connection, official, common_revision_id)
        if official is not None
        else None
    )
    if paired is not None:
        return read_merged(connection, common_revision_id, paired)
    if contract_version < 4:
        legacy = _legacy_snapshot(connection, common_revision_id, summary, contract_version)
        return replace(legacy, unit_key_pairs=tuple(_legacy_unit_keys(legacy.equipment).items()))
    release = scenario_store.latest_release_row(connection)
    return read_merged(
        connection,
        common_revision_id,
        str(release["schedule_revision_id"]) if release is not None else None,
    )


def _schedule_revision_summary(row: Mapping[str, object]) -> EquipmentScheduleRevisionSummary:
    return EquipmentScheduleRevisionSummary(
        schedule_revision_id=str(row["schedule_revision_id"]),
        equipment_scenario_id=str(row["equipment_scenario_id"]),
        revision_no=as_int(row["revision_no"], "설비 시나리오 리비전 번호"),
        origin=str(row["origin"]),
        created_at=as_datetime(row["created_at"]),
        revision_name=_optional_str(row["revision_name"]),
        note=_optional_str(row["note"]),
        saved_by=_optional_str(row["saved_by"]),
        common_revision_id=_optional_str(row["common_revision_id"]),
        legacy_revision_id=_optional_str(row["legacy_revision_id"]),
        unit_row_count=as_int(row["unit_row_count"], "일정 행 수"),
        downtime_row_count=as_int(row["downtime_row_count"], "비가동 일정 행 수"),
        layout_hash=_optional_str(row["layout_hash"]),
        layout_unit_count=as_int(row["layout_unit_count"], "배치 차이 호기 행 수"),
        layout_mark_count=as_int(row["layout_mark_count"], "배치 차이 요소 행 수"),
        layout_label_count=as_int(row["layout_label_count"], "배치 차이 이름표 행 수"),
    )


def _scenario_summary(row: Mapping[str, object]) -> EquipmentScenarioSummary:
    return EquipmentScenarioSummary(
        equipment_scenario_id=str(row["equipment_scenario_id"]),
        scenario_name=str(row["scenario_name"]),
        status=str(row["status"]),
        list_order=None if row["list_order"] is None else as_int(row["list_order"], "목록 차례"),
        latest_schedule_revision_id=_optional_str(row["latest_schedule_revision_id"]),
        latest_revision_no=None
        if row["latest_revision_no"] is None
        else as_int(row["latest_revision_no"], "최신 리비전 번호"),
        revision_count=as_int(row["revision_count"], "리비전 수"),
        latest_layout_unit_count=as_int(row["latest_layout_unit_count"], "최신 배치 차이 행 수"),
        latest_layout_hash=_optional_str(row["latest_layout_hash"]),
        layout_trace_count=as_int(row["layout_trace_count"], "배치 옛 코드 흔적 수"),
        latest_layout_mark_count=as_int(row["latest_layout_mark_count"], "최신 배치 요소 차이 수"),
        latest_layout_label_count=as_int(
            row["latest_layout_label_count"], "최신 배치 이름표 차이 수"
        ),
    )


def _release(row: Mapping[str, object]) -> EquipmentRelease:
    return EquipmentRelease(
        release_no=as_int(row["release_no"], "공식 발행 번호"),
        equipment_scenario_id=str(row["equipment_scenario_id"]),
        schedule_revision_id=str(row["schedule_revision_id"]),
        released_at=as_datetime(row["released_at"]),
        released_by=_optional_str(row["released_by"]),
        note=_optional_str(row["note"]),
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _require_floor_layout_bases(
    connection: duckdb.DuckDBPyConnection,
    stored_canvases: Mapping[FloorKey, CanvasSize],
    bases: Mapping[FloorKey, FloorLayoutBase],
    *,
    changed: set[FloorKey],
    overlay: LayoutOverlay,
) -> None:
    """바꾸려는 층의 캔버스·요소·Main 설비명 위치가 편집을 시작할 때 본 값 그대로인가. 아니면
    다른 사람이 먼저 저장한 것이다 — 요소·위치는 층 전체 교체라 옛 목록으로 덮으면 그 사람의 것이
    지워진다. 기대 지문은 편집을 시작할 때 본 **합친** 값(공식 현행 ⊕ 출발 리비전의 배치 차이
    `overlay`)이다 — 공식 대상은 차이가 비어 지금과 같다(설계 6-1)."""
    for key in sorted(changed & set(bases)):
        expected_canvas, expected_marks = bases[key]
        stored_canvas = stored_canvases.get(key)
        if stored_canvas is None or expected_canvas is None:
            same_canvas = stored_canvas is None and expected_canvas is None
        else:
            same_canvas = all(
                abs(a - b) < 1e-9 for a, b in zip(stored_canvas, expected_canvas, strict=True)
            )
        same_marks = (
            floor_layout_fingerprint(
                effective_floor_marks(
                    _stored_floor_marks(connection, *key), overlay.marks_for(key)
                ),
                effective_group_labels(
                    _stored_group_labels(connection, *key), overlay.labels_for(key)
                ),
            )
            == expected_marks
        )
        if not (same_canvas and same_marks):
            raise ValueError(
                f"{key[0]} {key[1]} 의 캔버스·도면 요소·Main 설비명 위치를 다른 사용자가 먼저 "
                "바꿔 저장하지 않았습니다. 저장 안 한 배치를 버리고 다시 고치세요."
            )


def _stored_process_cutoff(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """열린 연결에서 저장된 공정별 Cut-off. 한 번도 저장하지 않았으면 빈 계약 프레임."""
    result = connection.execute(
        """
        SELECT process_name AS "공정", product_scope AS "제품구분",
               cutoff_days AS "Cutoff일수", note AS "비고"
        FROM equipment_ops.process_cutoff
        ORDER BY process_name, product_scope
        """
    ).fetchdf()
    if result.empty:
        return empty_process_cutoff()
    return prepare_process_cutoff(result)


def _require_marks_fit(
    connection: duckdb.DuckDBPyConnection, key: FloorKey, canvas: CanvasSize
) -> None:
    """그 층의 **저장된** 도면 요소가 새 캔버스 안인가. 캔버스를 바꾸는 모든 길이 지킨다 —
    요소가 캔버스 밖에 남으면 그 층 요소를 다시 저장할 때 손대지 않은 요소 때문에 막힌다."""
    width, height = canvas
    right, top = marks_extent(_stored_floor_marks(connection, *key))
    if right > width + 1e-9 or top > height + 1e-9:
        raise ValueError(
            f"{key[0]} {key[1]} 캔버스 {width:g} × {height:g} 밖에 도면 요소가 있습니다(필요한 "
            f"크기 {right:g} × {top:g}). Space 편집기에서 요소를 옮기거나 캔버스를 넓히세요."
        )


def _overlay_check_targets(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """캔버스 검사·미리 보임이 보는 가정 배치 리비전 — 일정 리비전 id → 그 시나리오 이름. ACTIVE
    설비 시나리오 최신 가운데 배치 차이가 있는 것과 최신 공식 발행(설계 6-4 — 옛 리비전은 보지
    않는다)."""
    targets: dict[str, str] = {}
    for summary in _scenario_map(connection).values():
        if (
            summary.status == "ACTIVE"
            and summary.latest_schedule_revision_id is not None
            and (summary.latest_layout_hash or EMPTY_LAYOUT_DIGEST) != EMPTY_LAYOUT_DIGEST
        ):
            targets[summary.latest_schedule_revision_id] = summary.scenario_name
    release = scenario_store.latest_release_row(connection)
    if release is not None:
        released = str(release["schedule_revision_id"])
        owner = scenario_store.scenario_name(connection, str(release["equipment_scenario_id"]))
        targets.setdefault(released, owner or str(release["equipment_scenario_id"]))
    return targets


def _require_overlay_marks_fit(
    connection: duckdb.DuckDBPyConnection, key: FloorKey, canvas: CanvasSize
) -> None:
    """그 층의 **가정 배치 요소**(각 ACTIVE 설비 시나리오 최신과 최신 공식 발행 리비전의 `set`)가 새
    캔버스 안인가. 밖이면 `EquipmentLayoutOverflow`. 캔버스를 바꾸는 네 진입점(설비 저장의 캔버스·
    캔버스 저장·도면 올리기·도면 지우기)이 공식 요소 검사(`_require_marks_fit`) 옆에서 부른다. 가정
    차이 호기는 막지 않는다 — 공식 호기처럼 그 시나리오의 다음 저장만 막힌다(설계 6-4). 옛
    리비전(최신·발행이 아닌)의 차이는 보지 않는다."""
    targets = _overlay_check_targets(connection)
    outside = scenario_store.layout_marks_outside(connection, list(targets), *key, *canvas)
    if outside:
        revision_id = min(outside)
        raise EquipmentLayoutOverflow(targets[revision_id], key, outside[revision_id])


def _content_hash(frame: pd.DataFrame) -> str:
    """값만 보는 해시. 모든 칸을 같은 글자 표기로 바꾼 뒤 잰다 — 같은 값이 정수로 들어왔는지
    DB 에서 실수로 읽혔는지, 날짜 단위가 ns 인지 us 인지로 「바뀌었다」고 하지 않게."""
    canonical = pd.DataFrame(index=range(len(frame)))
    for column in frame.columns:
        series = frame[column].reset_index(drop=True)
        if pd.api.types.is_bool_dtype(series):
            text = series.astype("string")
        elif pd.api.types.is_numeric_dtype(series):
            text = series.astype("float64").map(lambda value: "" if pd.isna(value) else repr(value))
        elif pd.api.types.is_datetime64_any_dtype(series):
            text = series.dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            text = series.astype("string")
        canonical[str(column)] = text.astype("string").fillna("")
    return hash_frame(canonical)


def _insert_common_revision(
    connection: duckdb.DuckDBPyConnection,
    *,
    note: str | None,
    saved_by: str | None,
    baseline: pd.DataFrame,
    common: pd.DataFrame,
) -> str:
    """검증을 마친 공통 대장(기존 보유대수 + 공통 32칸 + 호기 키)을 계약 v4 리비전으로 넣는다.

    마스터 표의 일정 칸은 NULL 이고 비가동 행은 없다 — 일정·비가동은 설비 시나리오 일정 리비전에
    있다. 번호는 전역 `MAX + 1` 이다(「공통 rN」).
    """
    revision_id = str(uuid4())
    row = connection.execute(
        "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM equipment_ops.revision"
    ).fetchone()
    if row is None:
        raise RuntimeError("설비 이력 번호를 생성하지 못했습니다.")
    master = common.loc[:, list(COMMON_MASTER_COLUMNS)].rename(
        columns={column: EQUIPMENT_MASTER_DB_COLUMNS[column] for column in COMMON_MASTER_COLUMNS}
    )
    master["unit_key"] = common[UNIT_KEY_COLUMN].astype("string").to_numpy()
    common_hash = hash_frame(common.loc[:, list(COMMON_FRAME_COLUMNS)].reset_index(drop=True))
    connection.execute(
        """
        INSERT INTO equipment_ops.revision (
            revision_id, revision_no, note, baseline_hash, schedule_hash,
            equipment_hash, downtime_hash, equipment_contract_version, saved_by
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 4, ?)
        """,
        [
            revision_id,
            int(row[0]),
            note,
            hash_frame(baseline),
            common_hash,
            common_hash,
            saved_by,
        ],
    )
    _insert_baseline(connection, revision_id, baseline)
    _insert_snapshot(
        connection,
        schema="equipment_ops",
        table_name="equipment_master_snapshot",
        revision_id=revision_id,
        frame=master.reset_index(drop=True),
    )
    return revision_id


def _stored_floor_canvases(connection: duckdb.DuckDBPyConnection) -> dict[FloorKey, CanvasSize]:
    """저장된 층 캔버스. 도면 바이트는 읽지 않는다."""
    rows = connection.execute(
        "SELECT building, floor_name, canvas_width, canvas_height "
        "FROM equipment_ops.floor_layout_profile"
    ).fetchall()
    return {(str(row[0]), str(row[1])): (float(row[2]), float(row[3])) for row in rows}


def _upsert_floor_canvas(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    width: float,
    height: float,
) -> None:
    # 행이 이미 있으면 숫자 두 개만 UPDATE 한다. DELETE+INSERT 로 행을 다시 쓰면
    # 도면 BLOB 이 통째로 다시 기록되고 DuckDB 는 지운 페이지를 회수하지 않는다.
    updated = connection.execute(
        """
        UPDATE equipment_ops.floor_layout_profile
        SET canvas_width = ?, canvas_height = ?, updated_at = current_timestamp
        WHERE building = ? AND floor_name = ?
        """,
        [width, height, building, floor],
    ).fetchone()
    if updated is None or int(updated[0]) == 0:
        _insert_floor_layout(connection, building, floor, width, height, None)


def _stored_floor_marks(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
) -> tuple[FloorLayoutMark, ...]:
    rows = connection.execute(
        """
        SELECT mark_id, mark_kind, x_coordinate, y_coordinate, x_size, y_size, rotation_deg,
               label, color_key, hatch, keep_out, font_size, font_color, border_style, label_align
        FROM equipment_ops.floor_layout_mark
        WHERE building = ? AND floor_name = ?
        ORDER BY source_row_no
        """,
        [building, floor],
    ).fetchall()
    return tuple(
        FloorLayoutMark(
            mark_id=str(row[0]),
            kind=str(row[1]),
            x=float(row[2]),
            y=float(row[3]),
            w=float(row[4]),
            h=float(row[5]),
            rotation=int(row[6]),
            label=str(row[7]) if row[7] is not None else "",
            color=str(row[8]) if row[8] is not None else "",
            hatch=bool(row[9]),
            keep_out=bool(row[10]),
            font_size=int(row[11]) if row[11] is not None else None,
            font_color=str(row[12]) if row[12] is not None else "",
            border_style=str(row[13]) if row[13] is not None else ZONE_BORDER_STYLES[0],
            label_align=str(row[14]) if row[14] is not None else ZONE_LABEL_ALIGNS[0],
        )
        for row in rows
    )


def _replace_floor_marks(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    marks: Sequence[FloorLayoutMark],
) -> None:
    """그 층 요소를 지우고 받은 순서대로 다시 넣는다(`source_row_no` 가 그리는 순서)."""
    connection.execute(
        "DELETE FROM equipment_ops.floor_layout_mark WHERE building = ? AND floor_name = ?",
        [building, floor],
    )
    if not marks:
        return
    frame = pd.DataFrame(
        [
            {
                "building": building,
                "floor_name": floor,
                "mark_id": mark.mark_id,
                "source_row_no": index,
                "mark_kind": mark.kind,
                "x_coordinate": mark.x,
                "y_coordinate": mark.y,
                "x_size": mark.w,
                "y_size": mark.h,
                "rotation_deg": mark.rotation,
                "label": mark.label or None,
                "color_key": mark.color or None,
                "hatch": mark.hatch,
                "keep_out": mark.keep_out,
                "font_size": mark.font_size,
                "font_color": mark.font_color or None,
                **_zone_look_columns(mark.kind, mark.border_style, mark.label_align),
            }
            for index, mark in enumerate(marks, start=1)
        ]
    )
    insert_by_name(
        connection,
        schema="equipment_ops",
        table_name="floor_layout_mark",
        frame=_with_font_size_type(frame),
    )


def _zone_look_columns(kind: str, border_style: str, label_align: str) -> dict[str, str | None]:
    """영역은 테두리 모양·이름표 정렬을 그대로 쓰고, 다른 요소는 NULL 이다(읽으면 처음 값)."""
    if kind != "zone":
        return {"border_style": None, "label_align": None}
    return {"border_style": border_style, "label_align": label_align}


def _stored_group_labels(
    connection: duckdb.DuckDBPyConnection, building: str, floor: str
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT parent_equipment_id, label_position
        FROM equipment_ops.floor_layout_group_label
        WHERE building = ? AND floor_name = ?
        ORDER BY parent_equipment_id
        """,
        [building, floor],
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _replace_group_labels(
    connection: duckdb.DuckDBPyConnection, building: str, floor: str, labels: GroupLabels
) -> None:
    """그 층의 Main 설비명 위치를 지우고 받은 것을 다시 넣는다."""
    connection.execute(
        "DELETE FROM equipment_ops.floor_layout_group_label WHERE building = ? AND floor_name = ?",
        [building, floor],
    )
    if not labels:
        return
    connection.executemany(
        "INSERT INTO equipment_ops.floor_layout_group_label "
        "(building, floor_name, parent_equipment_id, label_position) VALUES (?, ?, ?, ?)",
        [[building, floor, name, position] for name, position in sorted(labels.items())],
    )


def _stored_image_digest(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
) -> tuple[bool, str | None]:
    """(행이 있는지, 저장된 도면의 sha256) 을 돌려준다. BLOB 을 파이썬으로 읽지 않는다."""
    row = connection.execute(
        """
        SELECT sha256(image_payload)
        FROM equipment_ops.floor_layout_profile
        WHERE building = ? AND floor_name = ?
        """,
        [building, floor],
    ).fetchone()
    if row is None:
        return False, None
    return True, str(row[0]) if row[0] is not None else None


def _floor_layout_bytes(
    connection: duckdb.DuckDBPyConnection, *, excluding: FloorKey | None = None
) -> int:
    """층 도면의 바이트 합계(`excluding` 층은 뺀다 — 그 층 도면을 갈아 끼우는 중이다)."""
    building, floor = excluding if excluding is not None else ("", "")
    row = connection.execute(
        """
        SELECT COALESCE(SUM(octet_length(image_payload)), 0)
        FROM equipment_ops.floor_layout_profile
        WHERE NOT (building = ? AND floor_name = ?)
        """,
        [building, floor],
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _fab_layout_bytes(connection: duckdb.DuckDBPyConnection) -> int:
    """FAB 도면의 바이트. 층 도면을 올릴 때 30MB 합계에 함께 센다(FAB 를 올릴 때는 층 합계를
    센다)."""
    row = connection.execute(
        "SELECT COALESCE(SUM(octet_length(image_payload)), 0) FROM equipment_ops.fab_layout_profile"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _stored_fab_canvas(connection: duckdb.DuckDBPyConnection) -> CanvasSize | None:
    row = connection.execute(
        "SELECT canvas_width, canvas_height FROM equipment_ops.fab_layout_profile "
        "WHERE layout_key = ?",
        [FAB_LAYOUT_KEY],
    ).fetchone()
    return (float(row[0]), float(row[1])) if row is not None else None


def _stored_fab_marks(connection: duckdb.DuckDBPyConnection) -> tuple[FabLayoutMark, ...]:
    rows = connection.execute(
        """
        SELECT mark_id, mark_kind, x_coordinate, y_coordinate, x_size, y_size, rotation_deg,
               label, color_key, hatch, link_building, link_floor, font_size, font_color,
               border_style, label_align
        FROM equipment_ops.fab_layout_mark
        ORDER BY source_row_no
        """
    ).fetchall()
    return tuple(
        FabLayoutMark(
            mark_id=str(row[0]),
            kind=str(row[1]),
            x=float(row[2]),
            y=float(row[3]),
            w=float(row[4]),
            h=float(row[5]),
            rotation=int(row[6]),
            label=str(row[7]) if row[7] is not None else "",
            color=str(row[8]) if row[8] is not None else "",
            hatch=bool(row[9]),
            link=(str(row[10]), str(row[11]))
            if row[10] is not None and row[11] is not None
            else None,
            font_size=int(row[12]) if row[12] is not None else None,
            font_color=str(row[13]) if row[13] is not None else "",
            border_style=str(row[14]) if row[14] is not None else ZONE_BORDER_STYLES[0],
            label_align=str(row[15]) if row[15] is not None else ZONE_LABEL_ALIGNS[0],
        )
        for row in rows
    )


def _require_fab_layout_base(
    connection: duckdb.DuckDBPyConnection,
    stored_canvas: CanvasSize | None,
    base: FabLayoutBase,
) -> None:
    """FAB 캔버스·요소가 편집을 시작할 때 본 값 그대로인가. 아니면 다른 사람이 먼저 저장했다."""
    expected_canvas, expected_marks = base
    if stored_canvas is None or expected_canvas is None:
        same_canvas = stored_canvas is None and expected_canvas is None
    else:
        same_canvas = all(
            abs(a - b) < 1e-9 for a, b in zip(stored_canvas, expected_canvas, strict=True)
        )
    same_marks = fab_marks_fingerprint(_stored_fab_marks(connection)) == expected_marks
    if not (same_canvas and same_marks):
        raise ValueError(
            "S.PKG FAB 전체 배치를 다른 사용자가 먼저 바꿔 저장하지 않았습니다. 저장 안 한 FAB "
            "배치를 버리고 다시 고치세요."
        )


def _require_fab_marks_fit(connection: duckdb.DuckDBPyConnection, canvas: CanvasSize) -> None:
    """지금 그리는 FAB 요소(저장된 것, 하나도 없으면 기본 배치)가 새 캔버스 안인가."""
    require_fab_layout_fits(canvas, _stored_fab_marks(connection))


def _upsert_fab_canvas(connection: duckdb.DuckDBPyConnection, width: float, height: float) -> None:
    # 행이 있으면 숫자 두 개만 UPDATE 한다(도면 BLOB 을 다시 쓰지 않는다).
    updated = connection.execute(
        """
        UPDATE equipment_ops.fab_layout_profile
        SET canvas_width = ?, canvas_height = ?, updated_at = current_timestamp
        WHERE layout_key = ?
        """,
        [width, height, FAB_LAYOUT_KEY],
    ).fetchone()
    if updated is None or int(updated[0]) == 0:
        connection.execute(
            "INSERT INTO equipment_ops.fab_layout_profile (layout_key, canvas_width, "
            "canvas_height) VALUES (?, ?, ?)",
            [FAB_LAYOUT_KEY, width, height],
        )


def _replace_fab_marks(
    connection: duckdb.DuckDBPyConnection, marks: Sequence[FabLayoutMark]
) -> None:
    """FAB 요소를 모두 지우고 받은 순서대로 다시 넣는다(`source_row_no` 가 그리는 순서)."""
    connection.execute("DELETE FROM equipment_ops.fab_layout_mark")
    if not marks:
        return
    frame = pd.DataFrame(
        [
            {
                "mark_id": mark.mark_id,
                "source_row_no": index,
                "mark_kind": mark.kind,
                "x_coordinate": mark.x,
                "y_coordinate": mark.y,
                "x_size": mark.w,
                "y_size": mark.h,
                "rotation_deg": mark.rotation,
                "label": mark.label or None,
                "color_key": mark.color or None,
                "hatch": mark.hatch,
                "keep_out": False,
                "link_building": mark.link[0] if mark.link is not None else None,
                "link_floor": mark.link[1] if mark.link is not None else None,
                "font_size": mark.font_size,
                "font_color": mark.font_color or None,
                **_zone_look_columns(mark.kind, mark.border_style, mark.label_align),
            }
            for index, mark in enumerate(marks, start=1)
        ]
    )
    insert_by_name(
        connection,
        schema="equipment_ops",
        table_name="fab_layout_mark",
        frame=_with_font_size_type(frame),
    )


def _with_font_size_type(frame: pd.DataFrame) -> pd.DataFrame:
    """글자 크기 칸을 정수(빈 값 허용)로 맞춘다. 정수와 None 이 섞이면 pandas 가 실수(NaN)로,
    모두 None 이면 객체로 만든다 — 어느 쪽이든 INTEGER 칸에 넣기 전에 형을 고정한다."""
    return frame.assign(font_size=frame["font_size"].astype("Int64"))


def _insert_floor_layout(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    canvas_width: float,
    canvas_height: float,
    image: tuple[str, str, bytes] | None,
) -> None:
    mime, name, payload = image if image is not None else (None, None, None)
    connection.execute(
        """
        INSERT INTO equipment_ops.floor_layout_profile (
            building, floor_name, canvas_width, canvas_height,
            image_mime, image_name, image_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [building, floor, canvas_width, canvas_height, mime, name, payload],
    )


def _load_baseline(connection: duckdb.DuckDBPyConnection, revision_id: str) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT process_name AS "공정", classification AS "분류",
               base_count AS "기존보유대수", note AS "비고"
        FROM equipment_ops.baseline_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_equipment_master(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    return connection.execute(
        f"""
        SELECT {_EQUIPMENT_MASTER_PROJECTION}
        FROM equipment_ops.equipment_master_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_legacy_equipment(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        """
        SELECT equipment_id AS "설비명", process_name AS "공정",
               classification AS "분류", building AS "동", floor_name AS "층",
               x_coordinate AS "X", y_coordinate AS "Y", width_value AS "너비",
               infrastructure_complete_date AS "사전인프라완료일",
               arrival_date AS "입고일", hookup_complete_date AS "Hookup완료일",
               hardware_setup_complete_date AS "하드웨어셋업완료일",
               qual_complete_date AS "Qual완료일", tttm_complete_date AS "TTTM완료일",
               production_transition_date AS "양산전환일", note AS "비고"
        FROM equipment_ops.equipment_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    if legacy.empty:
        return empty_equipment_master()
    return _convert_legacy_equipment(legacy)


def _load_legacy_schedule(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        """
        SELECT equipment_id AS "설비명", process_name AS "공정",
               classification AS "분류", arrival_date AS "입고일",
               setup_start_date AS "하드웨어셋업완료일",
               setup_complete_date AS "양산전환일", note AS "비고"
        FROM equipment_ops.schedule_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    if legacy.empty:
        return empty_equipment_master()
    return _convert_legacy_equipment(legacy)


def _load_downtime_schedule(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    return connection.execute(
        f"""
        SELECT {_DOWNTIME_PROJECTION}
        FROM equipment_ops.downtime_schedule_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_legacy_downtime(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        f"""
        SELECT {_DOWNTIME_PROJECTION}
        FROM equipment_ops.downtime_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    return legacy.drop_duplicates(list(DOWNTIME_KEY_COLUMNS), keep="last")


def _convert_legacy_equipment(legacy: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=legacy.index, columns=EQUIPMENT_COLUMNS)
    result[EQUIPMENT_ID_COLUMN] = legacy[EQUIPMENT_ID_COLUMN]
    result["공정대분류"] = legacy["공정"]
    result["공정소분류"] = legacy["공정"]
    result[AREA_CODE_COLUMN] = legacy["분류"]
    result["동"] = legacy.get("동")
    result["층"] = legacy.get("층")
    result["X좌표"] = legacy.get("X")
    result["Y좌표"] = legacy.get("Y")
    result["Xsize"] = legacy.get("너비")
    has_coordinates = result[["X좌표", "Y좌표", "Xsize"]].notna().all(axis=1)
    result["Ysize"] = has_coordinates.map({True: 7.0, False: None})
    legacy_qual = legacy.get("양산전환일")
    legacy_arrival = legacy.get("입고일")
    if isinstance(legacy_arrival, pd.Series) and isinstance(legacy_qual, pd.Series):
        result[ARRIVAL_DATE_COLUMN] = legacy_arrival.fillna(legacy_qual)
    else:
        result[ARRIVAL_DATE_COLUMN] = legacy_arrival
    # 옛 양산전환일이 없으면 Qual일정도 비운다 — 신규 호기의 빈 Qual 은 「셋업 진행중」에 머문다.
    result[QUAL_DATE_COLUMN] = legacy_qual if isinstance(legacy_qual, pd.Series) else None
    result[STORAGE_FLAG_COLUMN] = "N"
    has_legacy_schedule = result[ARRIVAL_DATE_COLUMN].notna()
    result["기존설비여부"] = has_legacy_schedule.map({True: "N", False: "Y"})
    # Qual상태는 Qual 일정의 값이라 Qual일정이 있는 신규 호기에만 「계획」을 둔다.
    has_legacy_qual = has_legacy_schedule & result[QUAL_DATE_COLUMN].notna()
    result[QUAL_STATUS_COLUMN] = has_legacy_qual.map({True: "계획", False: None})
    result["설비이력"] = legacy.get("비고")
    result["레이아웃표시"] = has_coordinates.map({True: "Y", False: "N"})
    # 옛 리비전에는 모델별 생산성 구분이 없었다. 전부 기준 모델로 본다.
    result["환산비"] = DEFAULT_CONVERSION_RATIO
    return result


def _insert_baseline(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    incoming = frame.rename(
        columns={
            "공정": "process_name",
            "분류": "classification",
            "기존보유대수": "base_count",
            "비고": "note",
        }
    )
    _insert_snapshot(
        connection,
        schema="equipment_ops",
        table_name="baseline_snapshot",
        revision_id=revision_id,
        frame=incoming,
    )


def _insert_snapshot(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return
    incoming = frame.copy()
    incoming.insert(0, "source_row_no", range(1, len(incoming) + 1))
    incoming.insert(0, "revision_id", revision_id)
    insert_by_name(connection, schema=schema, table_name=table_name, frame=incoming)


def _revision_summary(row: Sequence[object]) -> EquipmentRevisionSummary:
    return EquipmentRevisionSummary(
        revision_id=str(row[0]),
        revision_no=as_int(row[1], "리비전 번호"),
        note=str(row[2]) if row[2] is not None else None,
        baseline_row_count=as_int(row[3], "기존 보유대수 행 수"),
        equipment_row_count=as_int(row[4], "설비 마스터 행 수"),
        downtime_row_count=as_int(row[5], "비가동 일정 행 수"),
        created_at=as_datetime(row[6]),
        saved_by=str(row[7]) if row[7] is not None else None,
    )
