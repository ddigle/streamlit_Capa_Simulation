# Purpose: 시나리오 스냅샷과 시나리오 독립 공용 프로필의 Streamlit 캐시 경계다.

"""시뮬레이션 DuckDB 읽기의 Streamlit 캐시 경계.

저장소 연결과 불변 리비전 스냅샷, 그리고 시나리오에 종속되지 않는 공용 프로필 열두 종
(표시순서·공정 표시명·비교 시나리오·주요 Case·선행 B/O·선행 입고 실적·Capa 요약·Top5 대역·
주요공정·확보율 보정·과거 구간·확보율 판정 기준)을 여기서만 캐시한다. 비교 시나리오 후보
목록과 비교 시나리오의 리비전 목록(HOME 이 회차마다 세션의 비교 짝을 대 보는 것)은 비교 대상
프로필과 한 세대를 쓴다.

DB 를 읽는 캐시는 모두 키에 쓰기 세대(`WriteGeneration`)를 둔다 — `clear_*` 가 비우기 전에 그 종류의
세대를 올린다(`_bump_write_generation`).

리비전 스냅샷은 잠근 프레임 한 벌을 프로세스에 두고, 시나리오를 여는 길에는 겉껍데기 사본을, 그 밖의
호출에는 깊은 사본을 넘긴다(AGENTS 5장 20).
"""

import threading
from dataclasses import fields
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation import settings
from capa_simulation.audit.recorder import as_system
from capa_simulation.frame_sharing import lock_frame, shared_view
from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalAdvanceShipment,
    GlobalComparisonScenario,
    GlobalDisplayOrder,
    GlobalExecutionCapacity,
    GlobalKeyProcess,
    GlobalMainCases,
    GlobalPastData,
    GlobalProcessRename,
    GlobalSecurementThreshold,
    GlobalSummaryNote,
    GlobalTop5Band,
    MainCaseTargets,
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


# 이 프로세스의 쓰기 세대 — (모듈을 읽은 회차, 그 종류를 비운 횟수). 비울 때마다 그 종류만 오른다.
# 종류는 공용 프로필마다 하나와, 리비전 스냅샷 두 칸이 함께 쓰는 "snapshot", 비교 계획 "plan" 이다.
# 설비 캐시 경계(`equipment_cache.py`)와 같은 장치를 따로 두는 것은 두 DB 모듈이 서로 import 하지
# 않기 위해서다.
WriteGeneration = tuple[str, int]
_MODULE_EPOCH = uuid4().hex
_GENERATION_LOCK = threading.Lock()
_write_generations: dict[str, int] = {
    kind: 0
    for kind in (
        "display_order",
        "process_rename",
        "comparison_scenario",
        "main_cases",
        "advance_load",
        "advance_shipment",
        "securement_threshold",
        "summary_note",
        "top5_band",
        "key_process",
        "execution_capacity",
        "past_data",
        "snapshot",
        "plan",
    )
}


def _write_generation(kind: str) -> WriteGeneration:
    with _GENERATION_LOCK:
        return _MODULE_EPOCH, _write_generations[kind]


def _bump_write_generation(*kinds: str) -> None:
    """비울 때 `.clear()` 앞에서 부른다.

    `.clear()` 는 **이미 진행 중인 캐시 미스**를 막지 못한다 — 저장 직전에 옛 값을 읽기 시작한 다른
    세션의 계산이 비운 뒤에 옛 값을 다시 심는다. 공용 프로필 캐시는 TTL 이 없어 그 옛 값이 다음
    저장·재시작까지 남는다. 세대를 키에 넣고 비울 때 올리면 그 계산은 옛 세대 키 아래에만 값을
    남기고(그 칸은 `max_entries`·TTL 로 밀려난다), 비운 뒤의 읽기는 새 세대 키로 다시 읽는다. 모듈을
    다시 읽으면(핫리로드) 회차 값이 바뀌어 옛 세대 키와 겹치지 않는다. 잠금 하나만 쓰므로 실행
    문맥이 없는 배경 스레드(공식버전 자동 갱신 예약)에서도 부를 수 있다.
    """
    with _GENERATION_LOCK:
        for kind in kinds:
            _write_generations[kind] += 1


@st.cache_resource
def get_scenario_repository(database_path: str) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    # 결과가 아니라 읽는 함수를 넘긴다 — 시드는 공용 프로필이 없을 때만 읽는다. 첫 판 · 보강은 앱
    # 자신의 쓰기다(`as_system`) — 보강은 Admin 몫 표지(공용 표시순서)를 지나므로 새 프로세스의 첫
    # 회차가 열람이어도 화면이 서야 한다(접속 등급 — `auth/grades.py`).
    with as_system("system:app"):
        repository.initialize_global_display_order(load_builtin_display_order)
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


# 살아 있는 프레임으로 쥐는 스냅샷 칸 수와 수명. 한 칸이 같은 스냅샷의 피클(합성 표본의 샘플 관측
# 20MB)보다 몇 배 크다 — 칸을 적게 두고, 쓰지 않는 리비전은 시간이 지나면 내려놓는다.
# 들어오는 것은 사실상 최신 공식 리비전(새 세션 부트스트랩·입장 Summary)과 방금 불러온 리비전이다.
SNAPSHOT_RESOURCE_MAX_ENTRIES = 4
SNAPSHOT_RESOURCE_TTL_SECONDS = 3600


def _private_copy(frame: pd.DataFrame) -> pd.DataFrame:
    """공유 프레임과 배열을 하나도 함께 쓰지 않는 사본. 데이터와 축을 모두 새로 만든다.

    `copy(deep=True)` 는 데이터 배열만 새로 만들고 축은 view 로 넘겨 열 이름 배열을 공유 프레임과
    함께 쓴다. 축까지 새로 만들어 사본은 어디를 고쳐도 공유 칸·다른 세션에 닿지 않고, 잠긴 배열도
    물려받지 않는다(열 이름 배열은 표마다 수십 칸이다). `RangeIndex` 는 배열이 없어 그대로 둔다.
    """
    copied = frame.copy(deep=True)
    copied.columns = frame.columns.copy(deep=True)
    if not isinstance(frame.index, pd.RangeIndex):
        copied.index = frame.index.copy(deep=True)
    return copied


@st.cache_resource(
    show_spinner=False,
    max_entries=SNAPSHOT_RESOURCE_MAX_ENTRIES,
    ttl=SNAPSHOT_RESOURCE_TTL_SECONDS,
)
def _load_scenario_snapshot_resource(
    database_path: str, revision_id: str, generation: WriteGeneration
) -> _ScenarioSnapshotPayload:
    """공용 표시순서를 얹은 리비전 스냅샷 한 벌을 프로세스에 둔다. **읽기만 한다.**

    `st.cache_data` 는 적중해도 저장된 피클을 매번 역직렬화하므로 새 세션·불러오기마다 그 비용을
    내고, 세션마다 같은 문자열을 새로 만들어 따로 쥔다. 여기 둔 프레임은 잠근 채
    (`frame_sharing.lock_frame`) 두 길로 넘긴다 — 시나리오를 여는 길
    (`load_scenario_snapshot_for_activation`)은 같은 배열을 함께 쓰는 겉껍데기 사본을, 그
    밖의 호출(`load_scenario_snapshot`)은 축까지 새로 만든 깊은 사본을 받는다. 프레임 객체
    자체는 넘기지 않는다(AGENTS 5장 20).
    """
    del generation
    snapshot = get_scenario_repository(database_path).load_revision(revision_id)
    payload = _snapshot_to_payload(snapshot)
    for frame in payload["tables"].values():
        lock_frame(frame)
    return payload


@st.cache_data(show_spinner=False, max_entries=8)
def _load_stored_order_snapshot_payload(
    database_path: str, revision_id: str, generation: WriteGeneration
) -> _ScenarioSnapshotPayload:
    """공용 표시순서를 얹지 않은 저장 원본(파생 시나리오 입력). 드물게 쓰여 피클로만 둔다.

    시나리오 관리의 월 머지·연도 Shift 가 원본을 고를 때만 부르고, 그 화면은 고른 원본을 세션에
    따로 둔다. 공유 칸(`_load_scenario_snapshot_resource`)에 올리면 칸 하나를 차지해 공식 리비전을
    밀어낼 수 있다.
    """
    del generation
    snapshot = get_scenario_repository(database_path).load_revision(
        revision_id, apply_global_display_order=False
    )
    return _snapshot_to_payload(snapshot)


def load_scenario_snapshot(
    database_path: str, revision_id: str, *, apply_global_display_order: bool = True
) -> ScenarioSnapshot:
    """불변 리비전 스냅샷. 부를 때마다 표마다 따로 된 깊은 사본을 받는다.

    받은 표는 마음대로 고쳐도 다른 호출·다른 세션·캐시에 보이지 않는다(검사 · 입장 Summary ·
    파생 시나리오 원본 등). 시나리오를 열어 세션에 올리는 길만
    `load_scenario_snapshot_for_activation` 이다. 모델 인스턴스는 캐시에 넣지 않고 기본형 dict
    에서 지금 클래스로 다시 만든다(핫리로드 뒤 옛 클래스가 실리지 않게).
    """
    generation = _write_generation("snapshot")
    if not apply_global_display_order:
        return _snapshot_from_payload(
            _load_stored_order_snapshot_payload(database_path, revision_id, generation)
        )
    shared = _load_scenario_snapshot_resource(database_path, revision_id, generation)
    return _snapshot_from_payload(
        {
            "scenario": shared["scenario"],
            "revision": shared["revision"],
            "preset": shared["preset"],
            "tables": {name: _private_copy(frame) for name, frame in shared["tables"].items()},
        }
    )


def load_scenario_snapshot_for_activation(database_path: str, revision_id: str) -> ScenarioSnapshot:
    """시나리오를 여는 길(부트스트랩 · 사이드바 불러오기 · 목록 열기)만 쓰는 스냅샷.

    공용 칸의 잠긴 프레임을 표마다 겉껍데기 사본(`frame_sharing.shared_view` — 같은 배열,
    프레임 · 축 객체만 새로)으로 넘긴다. 세션은 이 표를 그대로 원본으로 올리고 편집본도 같은
    배열을 함께 쓴다(`scenario_state._session_copy`) — 세션마다 깊은 사본 두 벌을 만들지
    않는다. 받은 표는 고치지 않고 편집은 표를 통째로 갈아 끼운다. 스위치
    (`settings.SHARE_SESSION_TABLES_ENV`)를 끈 서버는 `load_scenario_snapshot`(깊은 사본)과
    같다.
    """
    if not settings.share_session_tables_enabled():
        return load_scenario_snapshot(database_path, revision_id)
    generation = _write_generation("snapshot")
    shared = _load_scenario_snapshot_resource(database_path, revision_id, generation)
    return _snapshot_from_payload(
        {
            "scenario": shared["scenario"],
            "revision": shared["revision"],
            "preset": shared["preset"],
            "tables": {name: shared_view(frame) for name, frame in shared["tables"].items()},
        }
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _load_scenario_plan(
    database_path: str, revision_id: str, generation: WriteGeneration
) -> pd.DataFrame:
    del generation
    return get_scenario_repository(database_path).load_revision_table(revision_id, "RQ_PKG_PLAN")


def load_scenario_plan(database_path: str, revision_id: str) -> pd.DataFrame:
    """비교 GAP 이 쓰는 것은 계획 한 장뿐이다. 리비전 16표를 읽지도, 캐시에 올리지도 않는다.

    DB 에서는 그 리비전의 `RQ_PKG_PLAN` 만 읽고(`load_revision_table` — 스냅샷과 같은 경로),
    캐시에도 그 한 장만 둔다. 비교 리비전은 고를 때마다 바뀌므로 스냅샷 캐시에 올리면 계획 한
    장을 얻으려고 16표를 쥐게 된다. 지운 리비전은 `KeyError` 로 올라와 캐시에 남지 않는다.
    """
    return _load_scenario_plan(database_path, revision_id, _write_generation("plan"))


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_display_order_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_display_order()
    return _payload(profile, GlobalDisplayOrder)


def load_global_display_order(database_path: str) -> GlobalDisplayOrder:
    """Share the display order without caching its reload-sensitive model class."""
    return GlobalDisplayOrder(
        **_load_global_display_order_payload(database_path, _write_generation("display_order"))
    )


def clear_global_display_order_cache() -> None:
    _bump_write_generation("display_order")
    _load_global_display_order_payload.clear()
    _clear_snapshot_payloads()


def _clear_snapshot_payloads() -> None:
    _bump_write_generation("snapshot")
    _load_scenario_snapshot_resource.clear()
    _load_stored_order_snapshot_payload.clear()


def clear_scenario_snapshot_cache() -> None:
    """지운 리비전의 스냅샷이 캐시에 남아 되살아나지 않게 한다."""
    _clear_snapshot_payloads()
    _bump_write_generation("plan")
    _load_scenario_plan.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_process_rename_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_process_rename()
    return _payload(profile, GlobalProcessRename)


def load_global_process_rename(database_path: str) -> GlobalProcessRename:
    """Share the process display-name profile without caching its model class."""
    return GlobalProcessRename(
        **_load_global_process_rename_payload(database_path, _write_generation("process_rename"))
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_comparison_scenario_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_comparison_scenario()
    return _payload(profile, GlobalComparisonScenario)


def load_global_comparison_scenario(database_path: str) -> GlobalComparisonScenario:
    """Share the comparison-target profile without caching its model class."""
    return GlobalComparisonScenario(
        **_load_global_comparison_scenario_payload(
            database_path, _write_generation("comparison_scenario")
        )
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _listed_comparison_candidates_payload(
    database_path: str, generation: WriteGeneration
) -> tuple[str, ...]:
    del generation
    return tuple(
        scenario.scenario_id for scenario in get_scenario_repository(database_path).list_scenarios()
    )


def listed_comparison_candidates(database_path: str) -> frozenset[str]:
    """비교 시나리오로 고를 수 있는 시나리오 id(보관하지 않은 것) — HOME 이 회차마다 세션 값을
    대 본다.

    키는 비교 대상 프로필과 **같은 쓰기 세대**다. 세션 값을 무르게 하는 일은 보관·영구 삭제뿐이고
    (리비전 하나만 지우는 길은 저장소에 없다 — append-only), 그 둘은 저장소가 같은 트랜잭션에서
    프로필도 비우고 호출부(`scenario_management`)가
    `clear_global_comparison_scenario_cache()` 를 부른다. 그래서 HOME 회차는 보관·삭제 뒤 한 번만
    DB 를 읽는다. 새로 만든 시나리오는 세대를 올리지 않아 이 목록에 늦게 들 수 있다 — 목록에 없는
    세션 값은 부르는 쪽이 DB 로 한 번 더 확인한 뒤에만
    걷는다(`home_preference.forget_unlisted_comparison`).
    """
    return frozenset(
        _listed_comparison_candidates_payload(
            database_path, _write_generation("comparison_scenario")
        )
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _scenario_revision_ids_payload(
    database_path: str, scenario_id: str, generation: WriteGeneration
) -> tuple[str, ...]:
    del generation
    return tuple(
        revision.revision_id
        for revision in get_scenario_repository(database_path).list_revisions(scenario_id)
    )


def scenario_has_revision(database_path: str, scenario_id: str, revision_id: str) -> bool:
    """그 리비전이 그 시나리오 것인가 — HOME 이 GAP 을 켠 회차마다 세션의 비교 짝을 대 본다.

    리비전은 append-only 라(리비전 하나만 지우는 길이 저장소에 없다) 한 번 그 시나리오 목록에 든
    리비전은 시나리오를 보관 · 영구 삭제할 때까지 든다. 그래서 목록을 비교 대상 프로필과 **같은 쓰기
    세대**(`listed_comparison_candidates` 와 같은 까닭 — 보관 · 삭제가 그 세대를 올린다)로 캐시하고,
    목록에 있으면 DB 를 열지 않는다. 새로 저장한 리비전(사이드바 저장 · 공식버전 자동 갱신 · 다른
    세션)은 세대를 올리지 않아 캐시 목록에 늦게 든다 — 목록에 없으면 DB 로 한 번 더 보고 거기에도
    없을 때만 아니라고 한다(아니라는 답은 늘 지금 DB 의 답이다). 읽지 못하면 저장소 예외가 그대로
    올라간다.
    """
    listed = _scenario_revision_ids_payload(
        database_path, scenario_id, _write_generation("comparison_scenario")
    )
    if revision_id in listed:
        return True
    return any(
        revision.revision_id == revision_id
        for revision in get_scenario_repository(database_path).list_revisions(scenario_id)
    )


def clear_global_comparison_scenario_cache() -> None:
    """비교 대상 프로필과 비교 후보 목록을 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 비교 대상은 어떤
    `RQ_*` 표에도 오버레이되지 않고 비교 계획을 어디서 읽을지만 정한다.
    """
    _bump_write_generation("comparison_scenario")
    _load_global_comparison_scenario_payload.clear()
    _listed_comparison_candidates_payload.clear()
    _scenario_revision_ids_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_main_cases_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_main_cases()
    return _payload(profile, GlobalMainCases)


def load_global_main_cases(database_path: str) -> GlobalMainCases:
    """주요 Case(Case1·Case2) 공용 프로필. 모델 클래스는 캐시에 싣지 않는다.

    키는 DB 경로와 쓰기 세대다 — version 은 DB 를 읽어야 알 수 있어 키가 될 수 없다. 그래서 다른
    공용 프로필처럼 저장한 호출부가 `clear_global_main_cases_cache()` 로 비우고, 그 뒤의 읽기가 새
    version 을 받는다. 그 version 이 이 프로필을 쓰는 화면 캐시의 키다 — 지정 교체·비우기뿐 아니라
    가리키는 시나리오·리비전의 이름 바꾸기도 version 을 올린다(슬롯 글자가 둘 다 싣는다).
    """
    return GlobalMainCases(
        **_load_global_main_cases_payload(database_path, _write_generation("main_cases"))
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_main_case_targets_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    repository = get_scenario_repository(database_path)
    profile = repository.load_global_main_cases()
    wanted = {
        scenario_id for case_no in (1, 2) if (scenario_id := profile.case(case_no)[0]) is not None
    }
    scenarios = [
        scenario for scenario in repository.list_scenarios() if scenario.scenario_id in wanted
    ]
    revisions = [
        revision
        for scenario in scenarios
        for revision in repository.list_revisions(scenario.scenario_id)
    ]
    return {
        "profile": _payload(profile, GlobalMainCases),
        "scenarios": [_payload(scenario, ScenarioSummary) for scenario in scenarios],
        "revisions": [_payload(revision, RevisionSummary) for revision in revisions],
    }


def load_main_case_targets(database_path: str) -> MainCaseTargets:
    """주요 Case 프로필과 그것이 가리키는 시나리오·리비전 — HOME 제목 줄 칩이 회차마다 읽는다.

    키는 주요 Case 프로필과 **같은 쓰기 세대**다. 칩 글자·상태를 바꾸는 일은 모두 그 세대를 올린다 —
    지정 교체·비우기, 가리키는 시나리오 이름·리비전명 바꾸기(version 을 올린다), 가리키는 시나리오의
    보관·영구 삭제(그 Case 를 비운다). 리비전 하나만 지우는 길은 저장소에 없다(append-only). 그래서
    HOME 회차는 저장한 뒤 한 번만 DB 를 읽고 나머지는 캐시에서 꺼낸다(머리 띠처럼 회차마다 DB 를
    보지 않는다 — `app_header`). 칩 콜백도 누르는 순간 같은 캐시로 슬롯을 다시 푼다
    (`home_main_case_chips`). 모델 클래스는 캐시에 싣지 않는다.
    """
    payload = _load_main_case_targets_payload(database_path, _write_generation("main_cases"))
    return MainCaseTargets(
        profile=GlobalMainCases(**payload["profile"]),
        scenarios=tuple(ScenarioSummary(**item) for item in payload["scenarios"]),
        revisions=tuple(RevisionSummary(**item) for item in payload["revisions"]),
    )


def clear_global_main_cases_cache() -> None:
    """주요 Case 프로필과 칩 재료를 비운다. `RQ_*` 표에 얹히지 않아 리비전 스냅샷은 그대로다."""
    _bump_write_generation("main_cases")
    _load_global_main_cases_payload.clear()
    _load_main_case_targets_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_advance_load_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_advance_load()
    return _payload(profile, GlobalAdvanceLoad)


def load_global_advance_load(database_path: str) -> GlobalAdvanceLoad:
    """Share the advance-load profile without caching its model class."""
    return GlobalAdvanceLoad(
        **_load_global_advance_load_payload(database_path, _write_generation("advance_load"))
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_advance_shipment_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_advance_shipment()
    return _payload(profile, GlobalAdvanceShipment)


def load_global_advance_shipment(database_path: str) -> GlobalAdvanceShipment:
    """Share the 선행 입고 실적 profile without caching its model class."""
    return GlobalAdvanceShipment(
        **_load_global_advance_shipment_payload(
            database_path, _write_generation("advance_shipment")
        )
    )


def clear_global_advance_shipment_cache() -> None:
    """선행 입고 실적 프로필만 비운다.

    선행 B/O 와 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*` 표에도
    오버레이되지 않고 계산에도 들어가지 않는 화면 표시값이다.
    """
    _bump_write_generation("advance_shipment")
    _load_global_advance_shipment_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_securement_threshold_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_securement_threshold()
    return _payload(profile, GlobalSecurementThreshold)


def load_global_securement_threshold(database_path: str) -> GlobalSecurementThreshold:
    """Share the securement judgement thresholds without caching their model class."""
    return GlobalSecurementThreshold(
        **_load_global_securement_threshold_payload(
            database_path, _write_generation("securement_threshold")
        )
    )


def clear_global_securement_threshold_cache() -> None:
    """판정 기준 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*` 표에도
    오버레이되지 않고 확보율이 나온 뒤 판정할 때만 쓰인다. **공식버전을 새로 지정한 뒤에도
    부른다** — 프로필을 아직 저장하지 않았으면 기본값이 최신 공식버전 프리셋에서 오기 때문이다.
    """
    _bump_write_generation("securement_threshold")
    _load_global_securement_threshold_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_summary_note_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_summary_note()
    return _payload(profile, GlobalSummaryNote)


def load_global_summary_note(database_path: str) -> GlobalSummaryNote:
    """Share the HOME summary notice without caching its model class."""
    return GlobalSummaryNote(
        **_load_global_summary_note_payload(database_path, _write_generation("summary_note"))
    )


def clear_global_summary_note_cache() -> None:
    """Capa 요약 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 계산에도 들어가지 않는 화면 문구다.
    """
    _bump_write_generation("summary_note")
    _load_global_summary_note_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_top5_band_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_top5_band()
    return _payload(profile, GlobalTop5Band)


def load_global_top5_band(database_path: str) -> GlobalTop5Band:
    """Share the Top 5 band without caching its model class."""
    return GlobalTop5Band(
        **_load_global_top5_band_payload(database_path, _write_generation("top5_band"))
    )


def clear_global_top5_band_cache() -> None:
    """Top5 확보율 구간 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 막대 길이를 정할 때만 쓰인다.
    """
    _bump_write_generation("top5_band")
    _load_global_top5_band_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_key_process_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_key_process()
    return _payload(profile, GlobalKeyProcess)


def load_global_key_process(database_path: str) -> GlobalKeyProcess:
    """Share the key-process list without caching its model class."""
    return GlobalKeyProcess(
        **_load_global_key_process_payload(database_path, _write_generation("key_process"))
    )


def clear_global_key_process_cache() -> None:
    """주요공정 목록 프로필만 비운다.

    다른 공용 프로필과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다 — 어떤 `RQ_*`
    표에도 오버레이되지 않고 히트맵이 그릴 행만 정하는 화면 필터다.
    """
    _bump_write_generation("key_process")
    _load_global_key_process_payload.clear()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_execution_capacity_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_execution_capacity()
    return _payload(profile, GlobalExecutionCapacity)


def load_global_execution_capacity(database_path: str) -> GlobalExecutionCapacity:
    """Share the execution-capacity profile without caching its model class."""
    return GlobalExecutionCapacity(
        **_load_global_execution_capacity_payload(
            database_path, _write_generation("execution_capacity")
        )
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _load_global_past_data_payload(
    database_path: str, generation: WriteGeneration
) -> dict[str, Any]:
    del generation
    profile = get_scenario_repository(database_path).load_global_past_data()
    return _payload(profile, GlobalPastData)


def load_global_past_data(database_path: str) -> GlobalPastData:
    """Share the past-period profile without caching its model class."""
    return GlobalPastData(
        **_load_global_past_data_payload(database_path, _write_generation("past_data"))
    )


@st.cache_data(show_spinner=False, max_entries=8)
def past_table_csv(
    database_path: str,
    version: int,
    table_name: str,
    columns: tuple[str, ...],
    _frame: pd.DataFrame,
) -> bytes:
    """과거 구간 양식 CSV. 공용 버전이 같으면 결과도 같다.

    「HOME 설정」 팝업이 열린 회차마다(안쪽 `Past Data` 탭이 숨어 있어도) 본문을 그리므로 세 표의
    정규화·직렬화가 팝업 안 모든 rerun 에 실린다. 세 표는 한 버전을 공유하고 교체할 때마다
    version 이 오르므로 키에 version 과 표 이름만 있으면 된다.
    """
    del database_path, version, table_name
    return past_table_to_csv(_frame, columns)


def clear_global_past_data_cache() -> None:
    """과거 구간 프로필만 비운다. 어떤 `RQ_*` 표에도 오버레이되지 않는다."""
    _bump_write_generation("past_data")
    _load_global_past_data_payload.clear()
    past_table_csv.clear()


def clear_global_advance_load_cache() -> None:
    """선행 B/O 프로필만 비운다.

    표시명과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 선행 B/O 는 어떤 `RQ_*`
    표에도 오버레이되지 않고 화면 산출 직전에만 곱해진다.
    """
    _bump_write_generation("advance_load")
    _load_global_advance_load_payload.clear()


def clear_global_execution_capacity_cache() -> None:
    """확보율 보정 프로필만 비운다.

    선행 물량과 같은 이유로 리비전 스냅샷 캐시는 건드리지 않는다. 확보율 보정은 어떤 `RQ_*`
    표에도 오버레이되지 않고 확보율이 나온 뒤 화면 산출 직전에만 더해진다.
    """
    _bump_write_generation("execution_capacity")
    _load_global_execution_capacity_payload.clear()


def clear_global_process_rename_cache() -> None:
    """표시명 프로필만 비운다.

    표시순서와 달리 어떤 `RQ_*` 표에도 오버레이되지 않으므로 리비전 스냅샷 캐시는
    건드리지 않는다. 같이 비우면 저장할 때마다 16표 재적재가 딸려온다.
    """
    _bump_write_generation("process_rename")
    _load_global_process_rename_payload.clear()


def clear_scenario_repository() -> None:
    _bump_write_generation(*_write_generations)
    _load_global_advance_load_payload.clear()
    _load_global_advance_shipment_payload.clear()
    _load_global_securement_threshold_payload.clear()
    _load_global_comparison_scenario_payload.clear()
    _listed_comparison_candidates_payload.clear()
    _load_global_main_cases_payload.clear()
    _load_main_case_targets_payload.clear()
    _load_global_execution_capacity_payload.clear()
    _load_global_top5_band_payload.clear()
    _load_global_key_process_payload.clear()
    _load_global_summary_note_payload.clear()
    _load_global_past_data_payload.clear()
    past_table_csv.clear()
    _load_global_display_order_payload.clear()
    _load_global_process_rename_payload.clear()
    _clear_snapshot_payloads()
    _load_scenario_plan.clear()
    get_scenario_repository.clear()
