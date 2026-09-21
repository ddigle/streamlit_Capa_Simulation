# Purpose: Streamlit cache boundary for the shared DuckDB repository configuration.

"""Streamlit cache boundary for the shared DuckDB repository configuration."""

from dataclasses import fields
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd
import streamlit as st

from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalComparisonScenario,
    GlobalDisplayOrder,
    GlobalExecutionCapacity,
    GlobalKeyProcess,
    GlobalPastData,
    GlobalProcessRename,
    GlobalSummaryNote,
    GlobalTop5Band,
    RevisionSummary,
    ScenarioPreset,
    ScenarioSnapshot,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.past_data import past_table_to_csv


class _ScenarioSnapshotPayload(TypedDict):
    scenario: dict[str, Any]
    revision: dict[str, Any]
    preset: dict[str, Any]
    tables: dict[str, pd.DataFrame]


def _payload(model: object, cls: type[Any]) -> dict[str, Any]:
    """모델 하나를 캐시에 실을 수 있는 평범한 dict 으로 옮긴다.

    필드 목록은 **이 모듈이 지금 import 한 클래스**에서 얻고 값은 인스턴스에서 `getattr`
    로 읽는다. 핫리로드 뒤 옛 클래스의 인스턴스가 들어와도 그 클래스를 묻지 않으므로
    캐시에 옛 클래스가 실리지 않는다. `asdict` 는 DataFrame 까지 깊은 복사하므로 쓰지
    않는다.
    """
    return {field.name: getattr(model, field.name) for field in fields(cls) if field.init}


@st.cache_resource
def get_scenario_repository(database_path: str) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    repository.initialize_global_display_order(load_builtin_display_order())
    return repository


def _snapshot_to_payload(snapshot: ScenarioSnapshot) -> _ScenarioSnapshotPayload:
    """Detach cache data from reload-sensitive application model instances."""
    return {
        "scenario": _payload(snapshot.scenario, ScenarioSummary),
        "revision": _payload(snapshot.revision, RevisionSummary),
        "preset": _payload(snapshot.preset, ScenarioPreset),
        "tables": dict(snapshot.tables),
    }


def _snapshot_from_payload(payload: _ScenarioSnapshotPayload) -> ScenarioSnapshot:
    return ScenarioSnapshot(
        scenario=ScenarioSummary(**payload["scenario"]),
        revision=RevisionSummary(**payload["revision"]),
        preset=ScenarioPreset(**payload["preset"]),
        tables=payload["tables"],
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _load_scenario_snapshot_payload(
    database_path: str,
    revision_id: str,
) -> _ScenarioSnapshotPayload:
    snapshot = get_scenario_repository(database_path).load_revision(revision_id)
    return _snapshot_to_payload(snapshot)


def load_scenario_snapshot(database_path: str, revision_id: str) -> ScenarioSnapshot:
    """Share an immutable revision without caching its reload-sensitive model class."""
    return _snapshot_from_payload(_load_scenario_snapshot_payload(database_path, revision_id))


@st.cache_data(show_spinner=False, max_entries=8)
def load_scenario_plan(database_path: str, revision_id: str) -> pd.DataFrame:
    """비교 GAP 이 쓰는 것은 계획 한 장뿐이다. 16표 전체를 rerun 마다 풀지 않는다.

    `st.cache_data` 는 적중해도 저장된 피클을 매번 역직렬화한다. 샘플 관측으로 스냅샷
    전체는 5.1MB·64.6ms 인데 그중 계획은 0.04MB·0.4ms 다.
    """
    return _load_scenario_snapshot_payload(database_path, revision_id)["tables"]["RQ_PKG_PLAN"]


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_display_order_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_display_order()
    return _payload(profile, GlobalDisplayOrder)


def load_global_display_order(database_path: str) -> GlobalDisplayOrder:
    """Share the display order without caching its reload-sensitive model class."""
    return GlobalDisplayOrder(**_load_global_display_order_payload(database_path))


def clear_global_display_order_cache() -> None:
    _load_global_display_order_payload.clear()
    _load_scenario_snapshot_payload.clear()


def clear_scenario_snapshot_cache() -> None:
    """지운 리비전의 스냅샷이 캐시에 남아 되살아나지 않게 한다."""
    _load_scenario_snapshot_payload.clear()
    load_scenario_plan.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_process_rename_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_process_rename()
    return _payload(profile, GlobalProcessRename)


def load_global_process_rename(database_path: str) -> GlobalProcessRename:
    """Share the process display-name profile without caching its model class."""
    return GlobalProcessRename(**_load_global_process_rename_payload(database_path))


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_comparison_scenario_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_comparison_scenario()
    return _payload(profile, GlobalComparisonScenario)


def load_global_comparison_scenario(database_path: str) -> GlobalComparisonScenario:
    """Share the comparison-target profile without caching its model class."""
    return GlobalComparisonScenario(**_load_global_comparison_scenario_payload(database_path))


def clear_global_comparison_scenario_cache() -> None:
    """비교 대상 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 비교 대상은 어떤
    `RQ_*` 표에도 오버레이되지 않고 비교 계획을 어디서 읽을지만 정한다.
    """
    _load_global_comparison_scenario_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_advance_load_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_advance_load()
    return _payload(profile, GlobalAdvanceLoad)


def load_global_advance_load(database_path: str) -> GlobalAdvanceLoad:
    """Share the advance-load profile without caching its model class."""
    return GlobalAdvanceLoad(**_load_global_advance_load_payload(database_path))


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_summary_note_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_summary_note()
    return _payload(profile, GlobalSummaryNote)


def load_global_summary_note(database_path: str) -> GlobalSummaryNote:
    """Share the HOME summary notice without caching its model class."""
    return GlobalSummaryNote(**_load_global_summary_note_payload(database_path))


def clear_global_summary_note_cache() -> None:
    """Summary 공지 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 계산에도 들어가지 않는 화면 문구다.
    """
    _load_global_summary_note_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_top5_band_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_top5_band()
    return _payload(profile, GlobalTop5Band)


def load_global_top5_band(database_path: str) -> GlobalTop5Band:
    """Share the Top 5 band without caching its model class."""
    return GlobalTop5Band(**_load_global_top5_band_payload(database_path))


def clear_global_top5_band_cache() -> None:
    """Top5 확보율 구간 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 막대 길이를 정할 때만 쓰인다.
    """
    _load_global_top5_band_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_key_process_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_key_process()
    return _payload(profile, GlobalKeyProcess)


def load_global_key_process(database_path: str) -> GlobalKeyProcess:
    """Share the key-process list without caching its model class."""
    return GlobalKeyProcess(**_load_global_key_process_payload(database_path))


def clear_global_key_process_cache() -> None:
    """주요공정 목록 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 히트맵이 그릴 행만 정하는 화면 필터다.
    """
    _load_global_key_process_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_execution_capacity_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_execution_capacity()
    return _payload(profile, GlobalExecutionCapacity)


def load_global_execution_capacity(database_path: str) -> GlobalExecutionCapacity:
    """Share the execution-capacity profile without caching its model class."""
    return GlobalExecutionCapacity(**_load_global_execution_capacity_payload(database_path))


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_past_data_payload(database_path: str) -> dict[str, Any]:
    profile = get_scenario_repository(database_path).load_global_past_data()
    return _payload(profile, GlobalPastData)


def load_global_past_data(database_path: str) -> GlobalPastData:
    """Share the past-period profile without caching its model class."""
    return GlobalPastData(**_load_global_past_data_payload(database_path))


@st.cache_data(show_spinner=False, max_entries=8)
def past_table_csv(
    database_path: str,
    version: int,
    table_name: str,
    columns: tuple[str, ...],
    _frame: pd.DataFrame,
) -> bytes:
    """과거 구간 양식 CSV. 공용 버전이 같으면 결과도 같다.

    Past Data 탭은 닫혀 있어도 본문을 그리므로 세 표의 정규화·직렬화가 HOME 의 모든
    rerun 에 실린다. 세 표는 한 버전을 공유하고 교체할 때마다 version 이 오르므로 키에
    version 과 표 이름만 있으면 된다.
    """
    del database_path, version, table_name
    return past_table_to_csv(_frame, columns)


def clear_global_past_data_cache() -> None:
    """과거 구간 프로필만 비운다. 어떤 `RQ_*` 표에도 오버레이되지 않는다."""
    _load_global_past_data_payload.clear()
    past_table_csv.clear()


def clear_global_advance_load_cache() -> None:
    """선행 물량 프로필만 비운다.

    표시명과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 선행 물량은 어떤 `RQ_*`
    표에도 오버레이되지 않고 화면 산출 직전에만 곱해진다.
    """
    _load_global_advance_load_payload.clear()


def clear_global_execution_capacity_cache() -> None:
    """실행 Capa 반영 프로필만 비운다.

    선행 물량과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 실행 조정은 어떤 `RQ_*`
    표에도 오버레이되지 않고 확보율이 나온 뒤 화면 산출 직전에만 더해진다.
    """
    _load_global_execution_capacity_payload.clear()


def clear_global_process_rename_cache() -> None:
    """표시명 프로필만 비운다.

    표시순서와 달리 어떤 `RQ_*` 표에도 오버레이되지 않으므로 리비전 스냅샷 캐시는
    건드리지 않는다. 같이 비우면 저장할 때마다 16표 재적재가 딸려온다.
    """
    _load_global_process_rename_payload.clear()


def clear_scenario_repository() -> None:
    _load_global_advance_load_payload.clear()
    _load_global_comparison_scenario_payload.clear()
    _load_global_execution_capacity_payload.clear()
    _load_global_top5_band_payload.clear()
    _load_global_key_process_payload.clear()
    _load_global_summary_note_payload.clear()
    _load_global_past_data_payload.clear()
    past_table_csv.clear()
    _load_global_display_order_payload.clear()
    _load_global_process_rename_payload.clear()
    _load_scenario_snapshot_payload.clear()
    load_scenario_plan.clear()
    get_scenario_repository.clear()
