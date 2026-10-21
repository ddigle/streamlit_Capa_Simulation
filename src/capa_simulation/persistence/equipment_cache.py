# Purpose: Streamlit cache boundary for the standalone equipment repository.

"""Streamlit cache boundary for the standalone equipment repository."""

import threading
from dataclasses import fields
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRevisionSummary,
    EquipmentSnapshot,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_bytes,
    downtime_csv_bytes,
    equipment_csv_bytes,
)
from capa_simulation.services.fab_layout import FabLayoutMark, FabLayoutProfile
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import (
    FloorLayoutCanvas,
    FloorLayoutProfile,
)
from capa_simulation.services.shortening_baseline import (
    ShorteningBaseline,
    ShorteningBaselineSummary,
)
from capa_simulation.services.shortening_filter_profile import ShorteningFilterProfile


class _EquipmentSnapshotPayload(TypedDict):
    revision: dict[str, Any]
    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame


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


@st.cache_data(show_spinner=False, max_entries=16)
def _load_equipment_snapshot_payload(
    database_path: str,
    revision_id: str,
) -> _EquipmentSnapshotPayload:
    snapshot = get_equipment_repository(database_path).load_snapshot(revision_id)
    return {
        "revision": _payload(snapshot.revision, EquipmentRevisionSummary),
        "baseline": snapshot.baseline,
        "equipment": snapshot.equipment,
        "downtime": snapshot.downtime,
    }


def load_equipment_snapshot(database_path: str, revision_id: str) -> EquipmentSnapshot:
    """Load one immutable revision through a hot-reload-safe payload cache."""
    payload = _load_equipment_snapshot_payload(database_path, revision_id)
    return EquipmentSnapshot(
        revision=EquipmentRevisionSummary(**payload["revision"]),
        baseline=payload["baseline"],
        equipment=payload["equipment"],
        downtime=payload["downtime"],
    )


# 설비 DB 파일과 WAL 의 (inode, mtime_ns, 크기). 파일이 없으면 None.
DatabaseStamp = tuple[tuple[int, int, int] | None, tuple[int, int, int] | None]
# 「지금 무엇이 저장돼 있나」 읽기(최신 리비전 id·Cut-off)를 stat 이 그대로여도 다시 읽는 간격(초).
CURRENT_READ_TTL_SECONDS = 15
# 이 프로세스의 쓰기 세대 — (모듈을 읽은 회차, 비운 횟수). 비울 때마다 오른다. 덮어쓰거나 지울 수
# 있는 값을 담는 캐시(최신 리비전 id·Cut-off·층/FAB 도면·필요 단축 일정 조건·기준선)는 모두 이
# 세대를 키에 둔다. 고칠 수도 지울 수도 없는 설비 리비전 id 키의 캐시(스냅샷·이력·CSV)는 겹쳐도
# 같은 값이라 두지 않는다.
WriteGeneration = tuple[str, int]
_MODULE_EPOCH = uuid4().hex
_GENERATION_LOCK = threading.Lock()
_write_generations = {
    "revision": 0,
    "cutoff": 0,
    "floor_layout": 0,
    "shortening_filter": 0,
    "shortening_baseline": 0,
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
    """가장 최근 설비 리비전 id(없으면 None).

    가용설비 현황·Space 는 위젯 하나에도 페이지 전체가 다시 돌아, 캐시가 없으면 이 읽기 하나 때문에
    회차마다 설비 DB 를 연다. **비우는 것이 1차 장치다** — 이 앱의 모든 리비전 쓰기(RawData
    저장·입력 저장·일괄 삭제 저장·Space 배치 저장)는 `save_equipment_buffer` 를 지나
    `clear_equipment_snapshot_cache` 로 이 캐시를 비우고 쓰기 세대를 올린다(같은 프로세스의 다른
    세션 저장도 그렇다). 세대가 키에 있어 저장 직전에 시작된 다른 세션의 읽기가 비운 뒤에 옛 id 를
    심어도 비운 뒤의 읽기에는 닿지 않는다. 키의 DB·WAL stat 은 이 프로세스 밖의 쓰기를 알아채는 2차
    장치이고, `CURRENT_READ_TTL_SECONDS` 가 stat 이 못 잡은 경우의 한도다(같은 DB 를 두 앱
    프로세스가 함께 여는 배치에서는 남의 저장을 그만큼 늦게 볼 수 있다). 저장 충돌
    검사(`base_revision_id`)는 저장소가 쓰기 잠금 안에서 그대로 한다.
    """
    return _latest_revision_id(
        database_path, database_stamp(database_path), _write_generation("revision")
    )


def load_latest_equipment_snapshot(database_path: str) -> EquipmentSnapshot | None:
    """Resolve the current id cheaply and cache only the immutable snapshot body."""
    revision_id = latest_equipment_revision_id(database_path)
    if revision_id is None:
        return None
    return load_equipment_snapshot(database_path, revision_id)


@st.cache_data(show_spinner=False, max_entries=8, ttl=CURRENT_READ_TTL_SECONDS)
def _load_process_cutoff(
    database_path: str, stamp: DatabaseStamp, generation: WriteGeneration
) -> pd.DataFrame:
    del stamp, generation
    return get_equipment_repository(database_path).load_process_cutoff()


def load_process_cutoff(database_path: str) -> pd.DataFrame:
    """저장된 공정별 Cut-off(`0009`, 리비전 없는 현행값).

    Preference 탭이 숨어 있어도 회차마다 읽어 Static 대비 일정·필요 단축 일정에 넘긴다. 최신 리비전
    id 와 같은 방식이다 — 이 앱의 저장(`cutoff_management`)이 성공한 직후
    `clear_process_cutoff_cache` 로 비우고 쓰기 세대를 올리며, DB·WAL stat 과 TTL 이 프로세스 밖의
    쓰기를 맡는다.
    """
    return _load_process_cutoff(
        database_path, database_stamp(database_path), _write_generation("cutoff")
    )


def clear_process_cutoff_cache() -> None:
    _bump_write_generation("cutoff")
    _load_process_cutoff.clear()


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
    """RawData `저장 이력` 의 리비전 목록(최신 50개). 저장본이 없으면 빈 튜플.

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
def load_equipment_csv_payloads(database_path: str, revision_id: str) -> tuple[bytes, bytes, bytes]:
    """저장 리비전 하나의 세 표 CSV 바이트(설비 마스터·기존 보유대수·비가동 일정 차례).

    RawData 「현재 데이터」 내려받기는 편집본이 저장본과 같을 때 이 바이트를 그대로 쓴다 — 리비전은
    고칠 수 없고 직렬화는 결정적이라 같은 리비전이면 같은 파일이다. 그래서 rerun 마다 세 표(와
    저장본과 견주려는 세 표)를 다시 직렬화하지 않는다.
    """
    snapshot = load_equipment_snapshot(database_path, revision_id)
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


def clear_floor_layout_cache() -> None:
    """층·FAB 도면·캔버스·도면 요소 캐시를 비운다. 도면만 바꾼 저장(팝업)은 설비 리비전과 무관하므로
    스냅샷 캐시는 비우지 않는다 — 리비전과 캔버스·요소를 함께 쓴 저장은 부른 쪽이 둘 다 비운다."""
    _bump_write_generation("floor_layout")
    _load_floor_layout_summaries_payload.clear()
    _load_floor_layout_profile_payload.clear()
    _load_floor_layout_marks_payload.clear()
    _load_fab_layout_payload.clear()


def clear_equipment_snapshot_cache() -> None:
    """리비전을 쓴 뒤 부른다 — 최신 리비전 id 도 함께 비우고(쓰기 세대도 올린다) 다음 회차가 새
    리비전을 읽는다."""
    _bump_write_generation("revision")
    _latest_revision_id.clear()
    _load_equipment_snapshot_payload.clear()
    _load_revision_summaries_payload.clear()
    load_equipment_csv_payloads.clear()


def clear_equipment_repository() -> None:
    clear_equipment_snapshot_cache()
    clear_process_cutoff_cache()
    clear_floor_layout_cache()
    clear_shortening_filter_cache()
    clear_shortening_baseline_cache()
    get_equipment_repository.clear()
