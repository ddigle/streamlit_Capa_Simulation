# Purpose: 리비전명 변경의 저장소 비교 후 쓰기·세션 이름표·후속 처리와 리비전 글자를 고정한다.

"""리비전명은 리비전의 **이름표**다 — 내용(표·프리셋·가상 제품·해시·번호·부모·저장 시각)은 그대로다.

저장소는 그 한 칸만 비교 후 쓰기로 고치고(`rename_revision`), 화면 쪽 후속 처리
(`scenario_management.save_revision_name`)는 스냅샷 캐시·파생 원본 메모·이 세션의 머리 띠 이름표만
맞춘다. 시나리오 「최근 수정」은 오르지 않아 목록 차례가 그대로다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.components.revision_label import revision_label
from capa_simulation.persistence.cache import clear_scenario_snapshot_cache, load_scenario_snapshot
from capa_simulation.persistence.models import RevisionSummary, ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository, RevisionNameMoved


def _repository(database: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    return repository


def _two_revisions(
    repository: DuckDBScenarioRepository, name: str = "Scenario A"
) -> tuple[ScenarioSnapshot, ScenarioSnapshot]:
    first = repository.create_scenario(
        _metadata(name),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        revision_name="초기 리비전",
        note="상세 조회기간 2026-08-01~2026-08-31",
    )
    second = repository.save_revision(
        first.scenario.scenario_id,
        first.tables,
        first.preset,
        revision_name="probe save",
        parent_revision_id=first.revision.revision_id,
        note="사용자 메모",
    )
    return first, second


def _revision(repository: DuckDBScenarioRepository, revision_id: str) -> RevisionSummary:
    return repository.load_revision(revision_id).revision


def test_a_rename_changes_only_the_label(tmp_path: Path) -> None:
    """이름만 바뀐다. 해시·번호·부모·저장 시각·메모·표 내용과 시나리오 「최근 수정」·목록 차례는
    그대로다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    first, second = _two_revisions(repository)
    other = repository.create_scenario(
        _metadata("Scenario B"), _reference_tables(), ScenarioPreset(202608, 202608, ("Process-A",))
    )
    order_before = [item.scenario_id for item in repository.list_scenarios()]
    scenario_before = next(
        item
        for item in repository.list_scenarios()
        if item.scenario_id == first.scenario.scenario_id
    )
    before = _revision(repository, second.revision.revision_id)

    renamed = repository.rename_revision(
        second.revision.revision_id, "  필터 저장 v2  ", expected_name="probe save"
    )

    assert renamed == replace(before, revision_name="필터 저장 v2")
    after = repository.load_revision(second.revision.revision_id)
    assert after.revision == renamed
    for name, frame in second.tables.items():
        assert after.tables[name].equals(frame), name
    assert after.preset == second.preset
    # 다른 리비전은 그대로다.
    assert _revision(repository, first.revision.revision_id) == first.revision
    scenario_after = next(
        item
        for item in repository.list_scenarios()
        if item.scenario_id == first.scenario.scenario_id
    )
    assert scenario_after.updated_at == scenario_before.updated_at
    assert [item.scenario_id for item in repository.list_scenarios()] == order_before
    assert other.scenario.scenario_id in order_before


def test_an_empty_name_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    _first, second = _two_revisions(repository)

    with pytest.raises(ValueError, match="리비전명"):
        repository.rename_revision(second.revision.revision_id, "   ", expected_name="probe save")

    assert _revision(repository, second.revision.revision_id).revision_name == "probe save"


def test_an_unknown_revision_is_a_key_error(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    _two_revisions(repository)

    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.rename_revision("no-such-revision", "이름", expected_name="이름")


def test_a_name_changed_first_by_someone_else_is_not_overwritten(tmp_path: Path) -> None:
    """비교 후 쓰기 — 옛 이름을 든 화면이 남이 먼저 바꾼 이름을 되돌리지 않는다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    _first, second = _two_revisions(repository)
    revision_id = second.revision.revision_id
    repository.rename_revision(revision_id, "다른 사용자 이름", expected_name="probe save")

    with pytest.raises(
        RevisionNameMoved, match=r"다른 사용자가 먼저 이름을 바꿨습니다\(지금: "
    ) as caught:
        repository.rename_revision(revision_id, "내 이름", expected_name="probe save")

    assert caught.value.current == "다른 사용자 이름"
    assert _revision(repository, revision_id).revision_name == "다른 사용자 이름"


def test_duplicate_revision_names_are_allowed(tmp_path: Path) -> None:
    """번호가 늘 가르므로 같은 시나리오 안에서 리비전명이 겹쳐도 된다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    first, second = _two_revisions(repository)

    repository.rename_revision(
        second.revision.revision_id, "초기 리비전", expected_name="probe save"
    )

    names = [
        revision.revision_name for revision in repository.list_revisions(first.scenario.scenario_id)
    ]
    assert names == ["초기 리비전", "초기 리비전"]


def test_revisions_of_an_archived_scenario_are_not_renamed(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    _first, second = _two_revisions(repository)
    repository.archive_scenario(second.scenario.scenario_id)

    with pytest.raises(ValueError, match="보관된 시나리오의 리비전명은 바꿀 수 없습니다"):
        repository.rename_revision(
            second.revision.revision_id, "새 이름", expected_name="probe save"
        )

    assert _revision(repository, second.revision.revision_id).revision_name == "probe save"


def test_an_official_revision_keeps_its_release_name(tmp_path: Path) -> None:
    """공식으로 지정된 리비전도 고칠 수 있다. 공식버전명·번호·지정 시각·이력 행 수는 그대로다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    _first, second = _two_revisions(repository)
    release = repository.publish_official_revision(
        second.scenario.scenario_id, second.revision.revision_id, release_name="10월 공식안"
    )

    repository.rename_revision(second.revision.revision_id, "공식 필터", expected_name="probe save")

    latest = repository.latest_official_release()
    assert latest is not None
    assert latest.revision_name == "공식 필터"
    assert (latest.release_name, latest.release_no, latest.published_at) == (
        release.release_name,
        release.release_no,
        release.published_at,
    )
    assert len(repository.list_official_releases()) == 1


def test_the_revision_label_is_number_and_name() -> None:
    revision = SimpleNamespace(revision_no=3, revision_name="필터저장")
    assert revision_label(revision) == "r3 · 필터저장"  # type: ignore[arg-type]


def test_the_active_label_follows_only_its_own_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """올라와 있는 리비전의 이름표만 바뀐다. 다른 리비전 id 는 무시하고 시나리오명 등은 그대로다."""
    import capa_simulation.scenario_activation as activation

    state: dict[str, object] = {
        activation.ACTIVE_PERSISTED_REVISION_ID_KEY: "revision-2",
        activation.ACTIVE_SCENARIO_LABEL_KEY: {
            "scenario_id": "scenario-1",
            "revision_id": "revision-2",
            "scenario_name": "DEMO 시나리오",
            "simulation_code": "DEMO-CODE",
            "source_type": "BIGDATAQUERY",
            "registered_at": datetime(2026, 9, 28),
            "revision_no": 2,
            "revision_name": "보정",
            "saved_at": datetime(2026, 10, 5, 9, 0),
            "first_month": 202607,
            "last_month": 202607,
        },
    }
    monkeypatch.setattr(activation, "st", SimpleNamespace(session_state=state))

    activation.rename_active_revision_label("revision-other", "남의 이름")
    label = activation.active_scenario_label()
    assert label is not None and label.revision_name == "보정"

    activation.rename_active_revision_label("revision-2", "필터 저장")
    label = activation.active_scenario_label()
    assert label is not None
    assert (label.revision_name, label.scenario_name, label.revision_no) == (
        "필터 저장",
        "DEMO 시나리오",
        2,
    )


SAVE_SCRIPT = """
from dataclasses import replace

import streamlit as st

from capa_simulation.components.scenario_management import save_revision_name
from capa_simulation.persistence.cache import get_scenario_repository

database_path = st.session_state["database_path"]
revision = next(
    item
    for item in get_scenario_repository(database_path).list_revisions(
        st.session_state["scenario_id"]
    )
    if item.revision_id == st.session_state["revision_id"]
)
# 화면이 그 회차에 보인 이름(그 사이 다른 사용자가 바꾼 경우를 흉내 낸다).
if "test_shown_name" in st.session_state:
    revision = replace(revision, revision_name=st.session_state["test_shown_name"])
if "new_name" in st.session_state:
    try:
        renamed = save_revision_name(database_path, revision, st.session_state.pop("new_name"))
    except ValueError as exc:
        st.session_state["test_error"] = str(exc)
    else:
        st.session_state["test_renamed"] = renamed.revision_name if renamed else None
"""


def _active_label(snapshot: ScenarioSnapshot) -> dict[str, object]:
    return {
        "scenario_id": snapshot.scenario.scenario_id,
        "revision_id": snapshot.revision.revision_id,
        "scenario_name": snapshot.scenario.scenario_name,
        "simulation_code": snapshot.scenario.source_simulation_code,
        "source_type": snapshot.scenario.source_type,
        "registered_at": snapshot.scenario.created_at,
        "revision_no": snapshot.revision.revision_no,
        "revision_name": snapshot.revision.revision_name,
        "saved_at": snapshot.revision.created_at,
        "first_month": 202608,
        "last_month": 202608,
    }


def test_saving_a_name_refreshes_this_sessions_label_and_caches(tmp_path: Path) -> None:
    """후속 처리 — 스냅샷 캐시가 새 이름을 주고, 파생 원본 메모가 버려지고, 올라와 있는 리비전이면
    머리 띠 이름표가 바뀐다. 바뀐 것이 없으면 쓰지도 비우지도 않는다."""
    from capa_simulation.components.scenario_transform import SOURCE_MEMO_KEY
    from capa_simulation.scenario_activation import (
        ACTIVE_PERSISTED_REVISION_ID_KEY,
        ACTIVE_PERSISTED_SCENARIO_ID_KEY,
        ACTIVE_SCENARIO_LABEL_KEY,
    )

    database = tmp_path / "scenario.duckdb"
    repository = _repository(database)
    _first, second = _two_revisions(repository)
    clear_scenario_snapshot_cache()
    cached = load_scenario_snapshot(str(database), second.revision.revision_id)
    assert cached.revision.revision_name == "probe save"

    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["database_path"] = str(database)
    app.session_state["scenario_id"] = second.scenario.scenario_id
    app.session_state["revision_id"] = second.revision.revision_id
    app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = second.scenario.scenario_id
    app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = second.revision.revision_id
    app.session_state[ACTIVE_SCENARIO_LABEL_KEY] = _active_label(second)
    app.session_state[SOURCE_MEMO_KEY] = {"shift_source": ("남은 메모",)}

    # 같은 이름(앞뒤 공백만 다름)은 쓰지 않는다 — 메모도 캐시도 그대로다.
    app.session_state["new_name"] = " probe save "
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["test_renamed"] is None
    assert SOURCE_MEMO_KEY in app.session_state

    app.session_state["new_name"] = "필터 저장 v2"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["test_renamed"] == "필터 저장 v2"
    assert app.session_state[ACTIVE_SCENARIO_LABEL_KEY]["revision_name"] == "필터 저장 v2"
    assert app.session_state[ACTIVE_SCENARIO_LABEL_KEY]["scenario_name"] == "Scenario A"
    assert SOURCE_MEMO_KEY not in app.session_state
    refreshed = load_scenario_snapshot(str(database), second.revision.revision_id)
    assert refreshed.revision.revision_name == "필터 저장 v2"

    # 화면이 보인 이름(「필터 저장 v2」)과 DB 가 어긋나면 쓰지 않고 지금 이름을 알린다.
    repository.rename_revision(
        second.revision.revision_id, "다른 사용자 이름", expected_name="필터 저장 v2"
    )
    app.session_state["test_shown_name"] = "필터 저장 v2"
    app.session_state["new_name"] = "내 이름"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["test_error"] == (
        "다른 사용자가 먼저 이름을 바꿨습니다(지금: 다른 사용자 이름)."
    )
    assert _revision(repository, second.revision.revision_id).revision_name == "다른 사용자 이름"
    # 거절된 쓰기는 이 세션의 이름표를 바꾸지 않는다.
    assert app.session_state[ACTIVE_SCENARIO_LABEL_KEY]["revision_name"] == "필터 저장 v2"


def test_saving_a_name_refreshes_the_cached_main_cases(tmp_path: Path) -> None:
    """주요 Case 슬롯 글자는 리비전명을 싣는다 — 가리키는 리비전명을 바꾸면 캐시도 새 version 이다.

    캐시는 DB 경로 키라 저장소가 version 을 올려도 비지 않는다. 화면 후속 처리가 비우지 않으면 HOME
    슬롯이 옛 리비전명을 들고 있는다.
    """
    from capa_simulation.persistence.cache import (
        clear_global_main_cases_cache,
        load_global_main_cases,
    )

    database = tmp_path / "scenario.duckdb"
    repository = _repository(database)
    _first, second = _two_revisions(repository)
    repository.replace_global_main_case(
        1, second.scenario.scenario_id, second.revision.revision_id, source="테스트"
    )
    clear_global_main_cases_cache()
    seen = load_global_main_cases(str(database)).version

    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["database_path"] = str(database)
    app.session_state["scenario_id"] = second.scenario.scenario_id
    app.session_state["revision_id"] = second.revision.revision_id
    app.session_state["new_name"] = "주요 Case 리비전 새 이름"
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["test_renamed"] == "주요 Case 리비전 새 이름"
    assert load_global_main_cases(str(database)).version == seen + 1
