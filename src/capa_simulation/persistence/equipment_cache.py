# Purpose: 설비 DB 저장소의 Streamlit 캐시 경계 — 불변 리비전 쌍 본문·바뀔 수 있는 목록·현행값 읽기.

"""설비 DB 저장소의 Streamlit 캐시 경계.

- **리비전 내용은 불변이다.** 화면이 쓰는 한 벌은 (공통 대장 리비전, 설비 시나리오 일정 리비전) 쌍을
  합친 것이고 그 본문은 쌍 키로만 캐시한다(`load_merged_equipment_snapshot`) — 쓰기 세대가 없다.
  되돌리기 확인 재료(`load_schedule_restore_preview`)도 불변 리비전 id 셋이 키다.
- **바뀔 수 있는 것**(시나리오 이름·일정 리비전의 리비전명·공식 발행·각 시나리오 최신·옛 배포 흔적,
  공통 최신 id, 현행값 — Cut-off·주차별 가용대수·층 사용 상태 등)은 DB·WAL stat·쓰기 세대·TTL 을
  키에 둔 목록 캐시로 뺀다. 리비전명은 이름표라 고칠 수 있어(E7) 불변 본문에 싣지 않는다 — 본문의
  `schedule.revision_name` 은 늘 None 이고 이름은 리비전 목록
  (`load_equipment_schedule_revisions`)에서 읽는다.
- **어느 캐시도 저장소의 호환 래퍼(`save_snapshot`·`save_space_layout`·`load_snapshot`)를 부르지
  않는다.** 래퍼 `load_snapshot` 은 공식 발행에 따라 값이 바뀌는 뜻이라 공통 id 하나를 키로 실으면
  발행 뒤 낡은 값을 낸다(시험이 이 파일을 훑는다).
"""

import threading
from dataclasses import fields
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentRevisionSummary,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    EquipmentSnapshot,
    LegacyTraceReview,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_bytes,
    downtime_csv_bytes,
    equipment_csv_bytes,
)
from capa_simulation.services.equipment_scenario import ScheduleRestorePreview
from capa_simulation.services.fab_layout import FabLayoutMark, FabLayoutProfile
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import (
    FloorLayoutCanvas,
    FloorLayoutProfile,
)
from capa_simulation.services.floor_state import FloorStates
from capa_simulation.services.shortening_baseline import (
    ShorteningBaseline,
    ShorteningBaselineSummary,
)
from capa_simulation.services.shortening_filter_profile import ShorteningFilterProfile


class _MergedSnapshotPayload(TypedDict):
    """합친 본문 한 벌 — 평범한 dict·DataFrame·쌍 튜플·frozenset 만 싣는다(pickle 이 된다)."""

    revision: dict[str, Any]
    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame
    schedule: dict[str, Any] | None
    unit_key_pairs: tuple[tuple[str, str], ...]
    unscheduled_units: frozenset[str]
    orphan_rows: int


class _CatalogPayload(TypedDict):
    scenarios: list[dict[str, Any]]
    latest_release: dict[str, Any] | None
    legacy_trace_count: int


def _payload(model: object, cls: type[Any]) -> dict[str, Any]:
    """모델 하나를 캐시에 실을 수 있는 평범한 dict 으로 옮긴다.

    필드 목록은 **이 모듈이 지금 import 한 클래스**에서 얻고 값은 인스턴스에서 `getattr`
    로 읽는다. 핫리로드 뒤 옛 클래스의 인스턴스가 들어와도 그 클래스를 묻지 않으므로
    캐시에 옛 클래스가 실리지 않는다. 시뮬레이션 쪽 캐시 경계와 같은 세 줄을 따로 두는
    이유는 설비 모듈이 시나리오 Repository 를 import 하지 않기 위해서다.
    """
    return {field.name: getattr(model, field.name) for field in fields(cls) if field.init}


@st.cache_resource
def get_equipment_repository(database_path: str) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(Path(database_path))
    repository.initialize()
    return repository


# 합친 본문 칸 수. 세션 하나가 보는 쌍은 공식(= 공통 최신 + 공식 발행)과 고른 시나리오 하나라
# 둘이고, 이력 「그때 그대로」 조회가 한 칸 더 쓴다. 공통 최신이 바뀌면 모든 쌍이 새 키로 가므로
# 살아 있는 칸은 「세션들이 고른 시나리오 수 + 1」 안팎이다 — 시나리오 2~3개 운영에 넉넉하다.
MERGED_SNAPSHOT_CACHE_ENTRIES = 16


@st.cache_data(show_spinner=False, max_entries=MERGED_SNAPSHOT_CACHE_ENTRIES)
def _load_merged_payload(
    database_path: str,
    common_revision_id: str,
    schedule_revision_id: str | None,
) -> _MergedSnapshotPayload:
    """(공통, 일정) 쌍 하나의 합친 본문. 두 리비전 내용은 불변이라 쓰기 세대를 두지 않는다.

    합칠 수 없는 쌍(`EquipmentScenarioIncompatible`)은 예외라 캐시에 남지 않는다. 일정 리비전 요약의
    리비전명(이름표)은 고칠 수 있는 값이라 싣지 않는다(None) — 실으면 이름을 바꾼 뒤에도 이 쌍 키가
    옛 이름을 낸다(AGENTS 5장 8).
    """
    snapshot = get_equipment_repository(database_path).load_merged_snapshot(
        common_revision_id, schedule_revision_id
    )
    return {
        "revision": _payload(snapshot.revision, EquipmentRevisionSummary),
        "baseline": snapshot.baseline,
        "equipment": snapshot.equipment,
        "downtime": snapshot.downtime,
        "schedule": (
            {**_payload(snapshot.schedule, EquipmentScheduleRevisionSummary), "revision_name": None}
            if snapshot.schedule is not None
            else None
        ),
        "unit_key_pairs": tuple(snapshot.unit_key_pairs),
        "unscheduled_units": frozenset(snapshot.unscheduled_units),
        "orphan_rows": int(snapshot.orphan_rows),
    }


def load_merged_equipment_snapshot(
    database_path: str, common_revision_id: str, schedule_revision_id: str | None
) -> EquipmentSnapshot:
    """(공통 대장 리비전, 설비 시나리오 일정 리비전) 쌍의 합친 스냅샷 — 쌍 키 본문 캐시.

    모델은 꺼낼 때 **지금 import 한 클래스**로 다시 만든다(핫리로드 뒤 옛 클래스가 실리지 않게).
    `schedule.revision_name` 은 늘 None 이다 — 리비전명은 리비전 목록에서 읽는다.
    """
    payload = _load_merged_payload(database_path, common_revision_id, schedule_revision_id)
    schedule = payload["schedule"]
    return EquipmentSnapshot(
        revision=EquipmentRevisionSummary(**payload["revision"]),
        baseline=payload["baseline"],
        equipment=payload["equipment"],
        downtime=payload["downtime"],
        schedule=EquipmentScheduleRevisionSummary(**schedule) if schedule is not None else None,
        unit_key_pairs=payload["unit_key_pairs"],
        unscheduled_units=payload["unscheduled_units"],
        orphan_rows=payload["orphan_rows"],
    )


# 설비 DB 파일과 WAL 의 (inode, mtime_ns, 크기). 파일이 없으면 None.
DatabaseStamp = tuple[tuple[int, int, int] | None, tuple[int, int, int] | None]
# 「지금 무엇이 저장돼 있나」 읽기(최신 리비전 id·Cut-off·주차별 가용대수)를 stat 이 그대로여도 다시
# 읽는 간격(초).
CURRENT_READ_TTL_SECONDS = 15
# 이 프로세스의 쓰기 세대 — (모듈을 읽은 회차, 비운 횟수). 비울 때마다 오른다. 덮어쓰거나 지울 수
# 있는 값을 담는 캐시(공통 최신 id·설비 시나리오 목록·시나리오 리비전 목록·Cut-off·주차별
# 가용대수·층/FAB 도면·층 사용 상태·필요 단축 일정 조건·기준선)는 모두 이 세대를 키에 둔다. 고칠
# 수도 지울 수도 없는 리비전 id 키의 캐시(합친 본문·공통 이력·CSV)는 겹쳐도 같은 값이라 두지 않는다.
WriteGeneration = tuple[str, int]
_MODULE_EPOCH = uuid4().hex
_GENERATION_LOCK = threading.Lock()
_write_generations = {
    "revision": 0,
    "equipment_scenario": 0,
    "cutoff": 0,
    "standard_target": 0,
    "floor_layout": 0,
    "shortening_filter": 0,
    "shortening_baseline": 0,
    "floor_state": 0,
}


def _write_generation(kind: str) -> WriteGeneration:
    with _GENERATION_LOCK:
        return _MODULE_EPOCH, _write_generations[kind]


def _bump_write_generation(kind: str) -> None:
    """비울 때 부른다. `.clear()` 는 **이미 진행 중인 캐시 미스**를 막지 못한다 — 저장 직전에 옛
    값을 읽기 시작한 다른 세션의 계산이 비운 뒤에 옛 값을 다시 심는다. 세대를 키에 넣고 비울 때
    올리면 그 계산은 옛 세대 키 아래에만 값을 남기고, 비운 뒤의 읽기는 새 세대 키로 다시 읽는다.
    모듈을 다시 읽으면(핫리로드) 회차 값이 바뀌어 옛 세대 키와 겹치지 않는다."""
    with _GENERATION_LOCK:
        _write_generations[kind] += 1


def database_stamp(database_path: str) -> DatabaseStamp:
    """DB 파일과 `.wal` 의 (inode, mtime_ns, 크기).

    DuckDB 는 커밋마다 WAL 에 덧붙이고(크기가 는다) 마지막 연결이 닫힐 때 본 파일에 체크포인트한다
    (본 파일 mtime 이 바뀌고 WAL 이 사라진다). 파일을 갈아 끼우면 inode 가 바뀐다. 읽기만 하는
    열기·닫기는 셋 다 바꾸지 않는다(Linux 사본에서 확인).
    """
    stamps: list[tuple[int, int, int] | None] = []
    for path in (Path(database_path), Path(f"{database_path}.wal")):
        try:
            stat = path.stat()
        except OSError:
            stamps.append(None)
        else:
            stamps.append((stat.st_ino, stat.st_mtime_ns, stat.st_size))
    return stamps[0], stamps[1]


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _latest_revision_id(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> str | None:
    del stamp, generation
    return get_equipment_repository(database_path).latest_revision_id()


def latest_equipment_revision_id(database_path: str) -> str | None:
    """가장 최근 **공통 대장** 리비전 id(없으면 None).

    가용설비 현황·Space 는 위젯 하나에도 페이지 전체가 다시 돌아, 캐시가 없으면 이 읽기 하나 때문에
    회차마다 설비 DB 를 연다. **비우는 것이 1차 장치다** — 이 앱의 모든 리비전 쓰기(설비 마스터
    저장·입력 저장·일괄 삭제 저장·Space 배치 저장·설비 시나리오 팝업 저장)는 `save_equipment_buffer`
    를 지나 `clear_equipment_snapshot_cache` 로 이 캐시를 비우고 쓰기 세대를 올린다(같은 프로세스의
    다른 세션 저장도 그렇다). 세대가 키에 있어 저장 직전에 시작된 다른 세션의 읽기가 비운 뒤에 옛
    id 를 심어도 비운 뒤의 읽기에는 닿지 않는다. 키의 DB·WAL stat 은 이 프로세스 밖의 쓰기를
    알아채는 2차 장치이고, `CURRENT_READ_TTL_SECONDS` 가 stat 이 못 잡은 경우의 한도다(같은 DB 를
    두 앱 프로세스가 함께 여는 배치에서는 남의 저장을 그만큼 늦게 볼 수 있다). 저장 충돌 검사(출발
    공통·일정 리비전)는 저장소가 쓰기 잠금 안에서 그대로 한다.
    """
    return _latest_revision_id(
        database_path, database_stamp(database_path), _write_generation("revision")
    )


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _load_scenario_catalog_payload(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> _CatalogPayload:
    del stamp, generation
    catalog = get_equipment_repository(database_path).load_scenario_catalog()
    return {
        "scenarios": [_payload(summary, EquipmentScenarioSummary) for summary in catalog.scenarios],
        "latest_release": (
            _payload(catalog.latest_release, EquipmentRelease)
            if catalog.latest_release is not None
            else None
        ),
        "legacy_trace_count": int(catalog.legacy_trace_count),
    }


def load_equipment_scenario_catalog(database_path: str) -> EquipmentScenarioCatalog:
    """설비 시나리오 목록(이름·상태·각 최신 id·번호·리비전 수)·최신 공식 발행·옛 배포 흔적 수.

    바뀔 수 있는 값이라 공통 최신 id 와 같은 세 장치로 지킨다 — 이 앱의 쓰기(저장·복제·이름·발행·
    이어 쓰기)가 비우고 세대(`"equipment_scenario"`)를 올리는 것이 1차, DB·WAL stat 이 2차,
    `CURRENT_READ_TTL_SECONDS` 가 한도다. 발행만 바뀌어도 여기서 새 쌍이 나와 다른 본문 키로 간다.
    """
    payload = _load_scenario_catalog_payload(
        database_path, database_stamp(database_path), _write_generation("equipment_scenario")
    )
    release = payload["latest_release"]
    return EquipmentScenarioCatalog(
        scenarios=tuple(EquipmentScenarioSummary(**item) for item in payload["scenarios"]),
        latest_release=EquipmentRelease(**release) if release is not None else None,
        legacy_trace_count=payload["legacy_trace_count"],
    )


@st.cache_data(show_spinner=False, max_entries=4, ttl=CURRENT_READ_TTL_SECONDS)
def _load_legacy_trace_review_payload(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> dict[str, Any]:
    del stamp, generation
    return _payload(
        get_equipment_repository(database_path).legacy_trace_review(), LegacyTraceReview
    )


def load_legacy_trace_review(database_path: str) -> LegacyTraceReview:
    """「이대로 이어 쓰기」 확인 재료(흔적 수·빠지는 호기 수·합쳐지지 않는 까닭).

    흔적이 있을 때 시나리오 관리 「설비 시나리오」 구획이 그리는 회차에만 부른다. 시나리오마다 합쳐
    읽어 보므로 목록과 같은 세 장치(세대 `"equipment_scenario"`·stat·TTL)로 지킨다.
    """
    return LegacyTraceReview(
        **_load_legacy_trace_review_payload(
            database_path, database_stamp(database_path), _write_generation("equipment_scenario")
        )
    )


# 시나리오 리비전 목록 한 번에 읽는 줄 수(팝업 라디오·시나리오 관리 「설비 시나리오」 구획 표).
SCHEDULE_REVISION_LIST_LIMIT = 50


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _load_schedule_revisions_payload(
    database_path: str,
    equipment_scenario_id: str,
    stamp: DatabaseStamp,
    generation: WriteGeneration,
) -> list[dict[str, Any]]:
    del stamp, generation
    return [
        _payload(summary, EquipmentScheduleRevisionSummary)
        for summary in get_equipment_repository(database_path).list_schedule_revisions(
            equipment_scenario_id, limit=SCHEDULE_REVISION_LIST_LIMIT
        )
    ]


def load_equipment_schedule_revisions(
    database_path: str, equipment_scenario_id: str
) -> tuple[EquipmentScheduleRevisionSummary, ...]:
    """한 설비 시나리오의 일정 리비전(번호 큰 것부터, 최근 `SCHEDULE_REVISION_LIST_LIMIT` 개).

    남의 저장(함께 넣기 포함)으로 늘 수 있어 목록과 같은 세대·stat·TTL 로 지킨다.
    """
    return tuple(
        EquipmentScheduleRevisionSummary(**item)
        for item in _load_schedule_revisions_payload(
            database_path,
            equipment_scenario_id,
            database_stamp(database_path),
            _write_generation("equipment_scenario"),
        )
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _load_schedule_restore_preview_payload(
    database_path: str,
    common_revision_id: str,
    current_schedule_revision_id: str | None,
    schedule_revision_id: str,
) -> dict[str, Any]:
    return _payload(
        get_equipment_repository(database_path).preview_schedule_restore(
            schedule_revision_id,
            common_revision_id=common_revision_id,
            current_schedule_revision_id=current_schedule_revision_id,
        ),
        ScheduleRestorePreview,
    )


def load_schedule_restore_preview(
    database_path: str,
    common_revision_id: str,
    current_schedule_revision_id: str | None,
    schedule_revision_id: str,
) -> ScheduleRestorePreview:
    """「이 리비전으로 되돌리기」·「여기서 새 시나리오」 확인 재료(E7) — 바뀌는 호기 수·일정 없음.

    결과는 세 리비전(지금 공통 대장·그 시나리오 지금 최신·고른 리비전)의 **내용**만으로 정해지고 셋
    다 불변이라 쓰기 세대 없이 id 셋을 키로 둔다. 누가 저장해 최신이 바뀌면 화면이 새 id 로 부르므로
    다른 칸으로 간다. 고른 리비전을 지금 공통 대장과 합칠 수 없으면 예외라 캐시에 남지 않는다.
    """
    return ScheduleRestorePreview(
        **_load_schedule_restore_preview_payload(
            database_path,
            common_revision_id,
            current_schedule_revision_id,
            schedule_revision_id,
        )
    )


def load_official_equipment_snapshot(database_path: str) -> EquipmentSnapshot | None:
    """공식 스냅샷 = 공통 최신 + 최신 공식 발행 일정 리비전(발행이 없으면 일정 없음).

    두 값은 각자의 목록 캐시에서 받고 본문은 쌍 키 캐시에서 꺼낸다 — 세션이 공식 발행 쌍이면 같은
    칸을 쓴다. 공통 리비전이 없으면 None.
    """
    common_id = latest_equipment_revision_id(database_path)
    if common_id is None:
        return None
    release = load_equipment_scenario_catalog(database_path).latest_release
    return load_merged_equipment_snapshot(
        database_path, common_id, release.schedule_revision_id if release is not None else None
    )


def clear_equipment_scenario_cache() -> None:
    """설비 시나리오 목록·시나리오 리비전 목록을 비우고 세대를 올린다.

    이름·리비전명·발행·복제·되돌리기·이어 쓰기 뒤에는 이것만 부르면 된다(리비전 본문은 불변이고
    리비전명은 본문에 싣지 않는다 — 목록만 이름을 싣는다). 설비 마스터 저장은
    `clear_equipment_snapshot_cache` 가 이것까지 부른다 — 저장마다 일정 리비전·발행이 생길 수 있다.
    """
    _bump_write_generation("equipment_scenario")
    _load_scenario_catalog_payload.clear()
    _load_schedule_revisions_payload.clear()
    _load_legacy_trace_review_payload.clear()


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _load_process_cutoff(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> pd.DataFrame:
    del stamp, generation
    return get_equipment_repository(database_path).load_process_cutoff()


def load_process_cutoff(database_path: str) -> pd.DataFrame:
    """저장된 공정별 Cut-off(`0009`, 리비전 없는 현행값).

    가용설비 현황 Static 대비 일정·필요 단축 일정이 회차마다 읽는다(고치는 곳은 가용설비 현황
    「설정」 팝업). 최신 리비전 id 와 같은 방식이다 — 이 앱의 저장(`cutoff_management`)이 성공한
    직후 `clear_process_cutoff_cache` 로 비우고 쓰기 세대를 올리며, DB·WAL stat 과 TTL 이 프로세스
    밖의 쓰기를 맡는다.
    """
    return _load_process_cutoff(
        database_path, database_stamp(database_path), _write_generation("cutoff")
    )


def clear_process_cutoff_cache() -> None:
    _bump_write_generation("cutoff")
    _load_process_cutoff.clear()


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _load_standard_target_availability(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> pd.DataFrame:
    del stamp, generation
    return get_equipment_repository(database_path).load_standard_target_availability()


def load_standard_target_availability(database_path: str) -> pd.DataFrame:
    """저장된 주차별 가용대수(`0005`, 리비전 없는 현행값).

    표준 목표·표준 대비 재공 현황은 위젯 하나에도 다시 돌고, 그 회차에 설비 DB 를 여는 곳이 이 읽기
    하나다 — 캐시가 없으면 회차마다 설비 DB 인스턴스를 새로 만든다. Cut-off 와 같은 방식이다 — 이
    앱의 쓰기(표준 목표의 가용설비 붙여넣기·입력 초기화)가 성공한 직후
    `clear_standard_target_availability_cache` 로 비우고 쓰기 세대를 올리며, DB·WAL stat 과 TTL 이
    프로세스 밖의 쓰기를 맡는다.
    """
    return _load_standard_target_availability(
        database_path, database_stamp(database_path), _write_generation("standard_target")
    )


def clear_standard_target_availability_cache() -> None:
    _bump_write_generation("standard_target")
    _load_standard_target_availability.clear()


@st.cache_data(show_spinner=False, max_entries=8)
def _load_revision_summaries_payload(
    database_path: str,
    latest_revision_id: str,
) -> list[dict[str, Any]]:
    del latest_revision_id
    return [
        _payload(summary, EquipmentRevisionSummary)
        for summary in get_equipment_repository(database_path).list_revisions()
    ]


def load_equipment_revision_summaries(
    database_path: str,
    latest_revision_id: str | None,
) -> tuple[EquipmentRevisionSummary, ...]:
    """설비 마스터 탭 `저장 이력` 의 리비전 목록(최신 50개). 저장본이 없으면 빈 튜플.

    가용설비 현황은 위젯 하나에도 페이지 전체가 다시 돌고 이 탭은 숨어 있어도 그려지므로, DB 를
    rerun 마다 읽고 있었다. **리비전은 고치지 않고 덧붙이기만 한다** — 그래서 최신 리비전 id 가
    같으면 목록도 같다. 키는 그 id 이고, 페이지가 이미 읽은 최신 저장본에서 받으므로 DB 를 더 열지
    않는다.
    """
    if latest_revision_id is None:
        return ()
    return tuple(
        EquipmentRevisionSummary(**payload)
        for payload in _load_revision_summaries_payload(database_path, latest_revision_id)
    )


@st.cache_data(show_spinner=False, max_entries=8)
def load_equipment_csv_payloads(
    database_path: str, common_revision_id: str, schedule_revision_id: str | None
) -> tuple[bytes, bytes, bytes]:
    """저장된 (공통, 일정) 쌍 하나의 세 표 CSV 바이트(설비 마스터·기존 보유대수·비가동 일정 차례).

    설비 마스터 탭 「현재 데이터」 내려받기는 편집본이 저장본과 같을 때 이 바이트를 그대로 쓴다 — 두
    리비전은 고칠 수 없고 직렬화는 결정적이라 같은 쌍이면 같은 파일이다. 그래서 rerun 마다 세 표(와
    저장본과 견주려는 세 표)를 다시 직렬화하지 않는다. 본문은 합친 본문 캐시에서 받는다.
    """
    snapshot = load_merged_equipment_snapshot(
        database_path, common_revision_id, schedule_revision_id
    )
    return (
        equipment_csv_bytes(snapshot.equipment),
        baseline_csv_bytes(snapshot.baseline),
        downtime_csv_bytes(snapshot.downtime),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _load_floor_layout_summaries_payload(
    database_path: str, generation: WriteGeneration
) -> list[dict[str, Any]]:
    del generation
    return [
        _payload(summary, FloorLayoutCanvas)
        for summary in get_equipment_repository(database_path).load_floor_layout_summaries()
    ]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_floor_layout_profile_payload(
    database_path: str,
    building: str,
    floor: str,
    generation: WriteGeneration,
) -> dict[str, Any] | None:
    del generation
    profile = get_equipment_repository(database_path).load_floor_layout_profile(building, floor)
    if profile is None:
        return None
    return _payload(profile, FloorLayoutProfile)


@st.cache_data(show_spinner=False, max_entries=8)
def _load_floor_layout_marks_payload(
    database_path: str,
    building: str,
    floor: str,
    generation: WriteGeneration,
) -> list[dict[str, Any]]:
    del generation
    return [
        _payload(mark, FloorLayoutMark)
        for mark in get_equipment_repository(database_path).load_floor_layout_marks(building, floor)
    ]


def load_floor_layout_marks(
    database_path: str,
    building: str,
    floor: str,
) -> tuple[FloorLayoutMark, ...]:
    """Load one floor's non-equipment drawing marks in drawing order."""
    return tuple(
        FloorLayoutMark(**payload)
        for payload in _load_floor_layout_marks_payload(
            database_path, building, floor, _write_generation("floor_layout")
        )
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _load_floor_group_labels_payload(
    database_path: str,
    building: str,
    floor: str,
    generation: WriteGeneration,
) -> dict[str, str]:
    del generation
    return get_equipment_repository(database_path).load_floor_group_labels(building, floor)


def load_floor_group_labels(database_path: str, building: str, floor: str) -> dict[str, str]:
    """한 층의 저장된 Main 설비명 위치(Main 설비 → 가운데·위·아래, 고른 적이 없는 묶음은 빠짐)."""
    return dict(
        _load_floor_group_labels_payload(
            database_path, building, floor, _write_generation("floor_layout")
        )
    )


def load_floor_layout_summaries(database_path: str) -> tuple[FloorLayoutCanvas, ...]:
    """Load every stored floor canvas without the drawing bytes."""
    return tuple(
        FloorLayoutCanvas(**payload)
        for payload in _load_floor_layout_summaries_payload(
            database_path, _write_generation("floor_layout")
        )
    )


def load_floor_layout_canvases(database_path: str) -> dict[tuple[str, str], tuple[float, float]]:
    """Map (동, 층) to its canvas size for coordinate checks and figure ranges."""
    return {
        (summary.building, summary.floor): summary.canvas_size
        for summary in load_floor_layout_summaries(database_path)
    }


def load_floor_layout_profile(
    database_path: str,
    building: str,
    floor: str,
) -> FloorLayoutProfile | None:
    """Load one floor's canvas and drawing data URI through the payload cache."""
    payload = _load_floor_layout_profile_payload(
        database_path, building, floor, _write_generation("floor_layout")
    )
    if payload is None:
        return None
    return FloorLayoutProfile(**payload)


class _FabLayoutPayload(TypedDict):
    profile: dict[str, Any] | None
    marks: list[dict[str, Any]]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_fab_layout_payload(database_path: str, generation: WriteGeneration) -> _FabLayoutPayload:
    del generation
    repository = get_equipment_repository(database_path)
    profile = repository.load_fab_layout_profile()
    return {
        "profile": _payload(profile, FabLayoutProfile) if profile is not None else None,
        "marks": [_payload(mark, FabLayoutMark) for mark in repository.load_fab_layout_marks()],
    }


def load_fab_layout(
    database_path: str,
) -> tuple[FabLayoutProfile | None, tuple[FabLayoutMark, ...]]:
    """저장된 FAB 전체 도면 — (캔버스·배경 도면 행 | None, 요소). 요소가 없으면 빈 튜플이고 화면이
    기본 배치를 그린다(`services/fab_layout.effective_fab_layout`). 층 도면 캐시와 함께 비운다."""
    payload = _load_fab_layout_payload(database_path, _write_generation("floor_layout"))
    profile = payload["profile"]
    return (
        FabLayoutProfile(**profile) if profile is not None else None,
        tuple(FabLayoutMark(**mark) for mark in payload["marks"]),
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_shortening_filter_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_equipment_repository(database_path).load_shortening_filter_profile()
    return _payload(profile, ShorteningFilterProfile)


def load_shortening_filter_profile(database_path: str) -> ShorteningFilterProfile:
    """필요 단축 일정 공용 조회 조건. 탭이 열린 회차마다 부르므로 캐시한다 — 저장하는 쪽(그 탭의
    `on_change` 콜백)이 쓴 뒤 `clear_shortening_filter_cache` 로 비운다. 설비 리비전과 무관하다."""
    return ShorteningFilterProfile(
        **_load_shortening_filter_payload(database_path, _write_generation("shortening_filter"))
    )


def clear_shortening_filter_cache() -> None:
    _bump_write_generation("shortening_filter")
    _load_shortening_filter_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_shortening_baselines_payload(
    database_path: str, generation: WriteGeneration
) -> list[dict[str, Any]]:
    del generation
    return [
        _payload(summary, ShorteningBaselineSummary)
        for summary in get_equipment_repository(database_path).list_shortening_baselines()
    ]


def load_shortening_baselines(database_path: str) -> tuple[ShorteningBaselineSummary, ...]:
    """필요 단축 일정 기준선 목록(0021, 최근 저장이 위). 탭이 열린 회차마다 「진척 비교」 선택지로
    부르므로 캐시한다 — 저장·지우기 쪽이 `clear_shortening_baseline_cache` 로 비운다."""
    return tuple(
        ShorteningBaselineSummary(**payload)
        for payload in _load_shortening_baselines_payload(
            database_path, _write_generation("shortening_baseline")
        )
    )


class _ShorteningBaselinePayload(TypedDict):
    summary: dict[str, Any]
    processes: tuple[str, ...]
    cutoff_days: dict[str, int]
    units: pd.DataFrame


@st.cache_data(show_spinner=False, max_entries=8)
def _load_shortening_baseline_payload(
    database_path: str, baseline_id: str, generation: WriteGeneration
) -> _ShorteningBaselinePayload:
    del generation
    baseline = get_equipment_repository(database_path).load_shortening_baseline(baseline_id)
    return {
        "summary": _payload(baseline.summary, ShorteningBaselineSummary),
        "processes": baseline.processes,
        "cutoff_days": dict(baseline.cutoff_days),
        "units": baseline.units,
    }


def load_shortening_baseline(database_path: str, baseline_id: str) -> ShorteningBaseline:
    """기준선 한 벌. **기준선은 고칠 수 없어** id 만으로 내용이 정해진다 — 키는 id 와, 지우기와 겹친
    읽기가 지운 한 벌을 되살리지 않게 쓰기 세대다. 없으면 `ValueError`(캐시에 남지 않는다)."""
    payload = _load_shortening_baseline_payload(
        database_path, baseline_id, _write_generation("shortening_baseline")
    )
    return ShorteningBaseline(
        summary=ShorteningBaselineSummary(**payload["summary"]),
        processes=payload["processes"],
        cutoff_days=payload["cutoff_days"],
        units=payload["units"],
    )


def clear_shortening_baseline_cache() -> None:
    """기준선 목록과 본문 캐시를 비운다. 저장은 목록만 바꾸지만 지우기와 한 함수로 둔다 — 본문은
    id 로만 닿아 비워도 다음에 고른 한 벌만 다시 읽는다."""
    _bump_write_generation("shortening_baseline")
    _load_shortening_baselines_payload.clear()
    _load_shortening_baseline_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4, ttl=CURRENT_READ_TTL_SECONDS)
def _load_floor_states_payload(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> dict[str, Any]:
    del stamp, generation
    return _payload(get_equipment_repository(database_path).load_floor_states(), FloorStates)


def load_floor_states(database_path: str) -> FloorStates:
    """Space 동·층 사용 상태(`0029`, 리비전 없는 공용 현행값).

    Space(회차마다)와 가용설비 현황 설비 마스터 탭(편집표를 그리는 회차마다)이 읽는다. Cut-off 와
    같은 방식이다 — 이 앱의 저장(`space_floor_list` 의 저장 콜백)이 성공한 직후
    `clear_floor_state_cache` 로 비우고 쓰기 세대를 올리며, DB·WAL stat 과 TTL 이 프로세스 밖의
    쓰기(다른 PC·동기화로 받은 DB)를 맡는다. 도면 캐시(`floor_layout` 세대)와 묶지 않는다 — 층 사용
    저장이 배경 도면까지 비울 까닭이 없다.
    """
    return FloorStates(
        **_load_floor_states_payload(
            database_path, database_stamp(database_path), _write_generation("floor_state")
        )
    )


def clear_floor_state_cache() -> None:
    _bump_write_generation("floor_state")
    _load_floor_states_payload.clear()


def clear_floor_layout_cache() -> None:
    """층·FAB 도면·캔버스·도면 요소·Main 설비명 위치 캐시를 비운다. 도면만 바꾼 저장(팝업)은 설비
    리비전과 무관하므로 스냅샷 캐시는 비우지 않는다 — 리비전과 캔버스·요소를 함께 쓴 저장은 부른
    쪽이 둘 다 비운다."""
    _bump_write_generation("floor_layout")
    _load_floor_layout_summaries_payload.clear()
    _load_floor_layout_profile_payload.clear()
    _load_floor_layout_marks_payload.clear()
    _load_floor_group_labels_payload.clear()
    _load_fab_layout_payload.clear()


def clear_equipment_snapshot_cache() -> None:
    """설비 마스터를 저장한 뒤 부른다 — 공통 최신 id·설비 시나리오 목록도 함께 비우고(두 쓰기 세대를
    올린다) 다음 회차가 새 리비전·새 발행을 읽는다. 합친 본문·CSV 는 쌍 키라 겹쳐도 같은 값이지만
    지난 쌍이 칸을 차지하지 않게 함께 비운다."""
    _bump_write_generation("revision")
    _latest_revision_id.clear()
    _load_merged_payload.clear()
    _load_revision_summaries_payload.clear()
    load_equipment_csv_payloads.clear()
    _load_schedule_restore_preview_payload.clear()
    clear_equipment_scenario_cache()


def clear_equipment_repository() -> None:
    clear_equipment_snapshot_cache()
    clear_process_cutoff_cache()
    clear_standard_target_availability_cache()
    clear_floor_layout_cache()
    clear_shortening_filter_cache()
    clear_shortening_baseline_cache()
    clear_floor_state_cache()
    get_equipment_repository.clear()
