# Purpose: Streamlit cache boundary for the standalone equipment repository.

"""Streamlit cache boundary for the standalone equipment repository."""

from dataclasses import fields
from pathlib import Path
from typing import Any, TypedDict

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


def load_latest_equipment_snapshot(database_path: str) -> EquipmentSnapshot | None:
    """Resolve the current id cheaply and cache only the immutable snapshot body."""
    revision_id = get_equipment_repository(database_path).latest_revision_id()
    if revision_id is None:
        return None
    return load_equipment_snapshot(database_path, revision_id)


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
    """저장 리비전 하나의 세 표 CSV 바이트(호기 마스터·기존 보유대수·비가동 일정 차례).

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
def _load_floor_layout_summaries_payload(database_path: str) -> list[dict[str, Any]]:
    return [
        _payload(summary, FloorLayoutCanvas)
        for summary in get_equipment_repository(database_path).load_floor_layout_summaries()
    ]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_floor_layout_profile_payload(
    database_path: str,
    building: str,
    floor: str,
) -> dict[str, Any] | None:
    profile = get_equipment_repository(database_path).load_floor_layout_profile(building, floor)
    if profile is None:
        return None
    return _payload(profile, FloorLayoutProfile)


@st.cache_data(show_spinner=False, max_entries=8)
def _load_floor_layout_marks_payload(
    database_path: str,
    building: str,
    floor: str,
) -> list[dict[str, Any]]:
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
        for payload in _load_floor_layout_marks_payload(database_path, building, floor)
    )


def load_floor_layout_summaries(database_path: str) -> tuple[FloorLayoutCanvas, ...]:
    """Load every stored floor canvas without the drawing bytes."""
    return tuple(
        FloorLayoutCanvas(**payload)
        for payload in _load_floor_layout_summaries_payload(database_path)
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
    payload = _load_floor_layout_profile_payload(database_path, building, floor)
    if payload is None:
        return None
    return FloorLayoutProfile(**payload)


class _FabLayoutPayload(TypedDict):
    profile: dict[str, Any] | None
    marks: list[dict[str, Any]]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_fab_layout_payload(database_path: str) -> _FabLayoutPayload:
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
    payload = _load_fab_layout_payload(database_path)
    profile = payload["profile"]
    return (
        FabLayoutProfile(**profile) if profile is not None else None,
        tuple(FabLayoutMark(**mark) for mark in payload["marks"]),
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_shortening_filter_payload(database_path: str) -> dict[str, Any]:
    profile = get_equipment_repository(database_path).load_shortening_filter_profile()
    return _payload(profile, ShorteningFilterProfile)


def load_shortening_filter_profile(database_path: str) -> ShorteningFilterProfile:
    """필요단축일정 공용 조회 조건. 탭이 열린 회차마다 부르므로 캐시한다 — 저장하는 쪽(그 탭의
    `on_change` 콜백)이 쓴 뒤 `clear_shortening_filter_cache` 로 비운다. 설비 리비전과 무관하다."""
    return ShorteningFilterProfile(**_load_shortening_filter_payload(database_path))


def clear_shortening_filter_cache() -> None:
    _load_shortening_filter_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_shortening_baselines_payload(database_path: str) -> list[dict[str, Any]]:
    return [
        _payload(summary, ShorteningBaselineSummary)
        for summary in get_equipment_repository(database_path).list_shortening_baselines()
    ]


def load_shortening_baselines(database_path: str) -> tuple[ShorteningBaselineSummary, ...]:
    """필요단축일정 기준선 목록(0021, 최근 저장이 위). 탭이 열린 회차마다 「진척 비교」 선택지로
    부르므로 캐시한다 — 저장·지우기 쪽이 `clear_shortening_baseline_cache` 로 비운다."""
    return tuple(
        ShorteningBaselineSummary(**payload)
        for payload in _load_shortening_baselines_payload(database_path)
    )


class _ShorteningBaselinePayload(TypedDict):
    summary: dict[str, Any]
    processes: tuple[str, ...]
    cutoff_days: dict[str, int]
    units: pd.DataFrame


@st.cache_data(show_spinner=False, max_entries=8)
def _load_shortening_baseline_payload(
    database_path: str, baseline_id: str
) -> _ShorteningBaselinePayload:
    baseline = get_equipment_repository(database_path).load_shortening_baseline(baseline_id)
    return {
        "summary": _payload(baseline.summary, ShorteningBaselineSummary),
        "processes": baseline.processes,
        "cutoff_days": dict(baseline.cutoff_days),
        "units": baseline.units,
    }


def load_shortening_baseline(database_path: str, baseline_id: str) -> ShorteningBaseline:
    """기준선 한 벌. **기준선은 고칠 수 없어** id 만으로 내용이 정해진다 — 키는 id 다. 없으면
    `ValueError`(캐시에 남지 않는다)."""
    payload = _load_shortening_baseline_payload(database_path, baseline_id)
    return ShorteningBaseline(
        summary=ShorteningBaselineSummary(**payload["summary"]),
        processes=payload["processes"],
        cutoff_days=payload["cutoff_days"],
        units=payload["units"],
    )


def clear_shortening_baseline_cache() -> None:
    """기준선 목록과 본문 캐시를 비운다. 저장은 목록만 바꾸지만 지우기와 한 함수로 둔다 — 본문은
    id 로만 닿아 비워도 다음에 고른 한 벌만 다시 읽는다."""
    _load_shortening_baselines_payload.clear()
    _load_shortening_baseline_payload.clear()


def clear_floor_layout_cache() -> None:
    """층·FAB 도면·캔버스·도면 요소 캐시를 비운다. 도면만 바꾼 저장(팝업)은 설비 리비전과 무관하므로
    스냅샷 캐시는 비우지 않는다 — 리비전과 캔버스·요소를 함께 쓴 저장은 부른 쪽이 둘 다 비운다."""
    _load_floor_layout_summaries_payload.clear()
    _load_floor_layout_profile_payload.clear()
    _load_floor_layout_marks_payload.clear()
    _load_fab_layout_payload.clear()


def clear_equipment_snapshot_cache() -> None:
    _load_equipment_snapshot_payload.clear()
    _load_revision_summaries_payload.clear()
    load_equipment_csv_payloads.clear()


def clear_equipment_repository() -> None:
    clear_equipment_snapshot_cache()
    clear_floor_layout_cache()
    clear_shortening_filter_cache()
    clear_shortening_baseline_cache()
    get_equipment_repository.clear()
