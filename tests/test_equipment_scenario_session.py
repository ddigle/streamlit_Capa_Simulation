# Purpose: 설비 시나리오 세션(새 세션 공식·고르기·낡음·합칠 수 없음·판정)과 사이드바 줄을 검증한다.

"""설비 시나리오 세션(`equipment_scenario_activation`)과 그 화면 조각.

세션은 (시나리오, 일정 리비전) 하나를 고정해 든다 — 새 세션은 최신 공식 발행, 남이 내 시나리오에
저장해도 그대로(「낡음」 — 일정 칸 잠금), 남이 공통을 고쳐 고정 쌍이 합쳐지지 않으면 그 시나리오
최신으로 옮기고 알린다. 사이드바 줄은 페이지가 그 회차 목록으로 그리고 `app.py` 는 설비 DB 를 열지
않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.proto.Dataframe_pb2 import Dataframe
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _request,
    _seeded,
    _session,
    _set,
)

from capa_simulation.components.equipment_data_workspace import (
    SCENARIO_COLUMN_LEGEND,
    save_result_message,
    scenario_column_help,
)
from capa_simulation.components.equipment_save_fields import (
    DEFAULT_PROPAGATE_NEW_DOWNTIME,
    DEFAULT_PROPAGATE_NEW_UNITS,
    DEFAULT_PUBLISH_OFFICIAL,
    EquipmentSaveBasis,
)
from capa_simulation.components.equipment_scenario_status import (
    EQUIPMENT_SCENARIO_FIELD_KEY,
    equipment_status_badge,
    equipment_value_label,
)
from capa_simulation.equipment_scenario_activation import (
    SELECTION_KEY,
    EquipmentSession,
)
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_TAB_KEY,
    PROCESS_CAPA_DETAIL,
    REQUIRED_SHORTENING,
    SPACE_STATUS,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentRevisionSummary,
    EquipmentSaveResult,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    PropagatedRevision,
)
from capa_simulation.services.equipment_contract import SCENARIO_SCHEDULE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    """캐시는 프로세스에 하나라 시험마다 비운다(다른 DB 경로라도 칸 수를 차지한다)."""
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _resolving(database: str) -> None:
    """한 회차: 세션을 세우고 판정·라벨을 세션 칸에 적는다(시험이 읽는다)."""
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import ensure_equipment_drafts
    from capa_simulation.equipment_scenario_activation import (
        resolve_equipment_session,
        space_editing_allowed,
    )

    session = resolve_equipment_session(database)
    ensure_equipment_drafts(session.snapshot)
    st.session_state["seen"] = {
        "scenario": session.scenario_id,
        "name": session.scenario_name,
        "revision_no": session.revision_no,
        "latest_no": session.latest_revision_no,
        "release_no": session.release_no,
        "official_scenario": session.is_official_scenario,
        "official_pair": session.is_official_pair,
        "assumption": session.is_assumption,
        "stale": session.stale,
        "space": space_editing_allowed(session),
        "notice": session.notice,
        "token": session.snapshot.token if session.snapshot is not None else None,
    }


def _app(repository: DuckDBEquipmentRepository) -> AppTest:
    return AppTest.from_function(
        _resolving, args=(str(repository.database_path),), default_timeout=60
    )


def _seen(app: AppTest) -> dict[str, Any]:
    assert not app.exception, [item.message for item in app.exception]
    seen = app.session_state["seen"]
    assert isinstance(seen, dict)
    return seen


def _select(app: AppTest, scenario_id: str, schedule_revision_id: str | None) -> None:
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }


def test_a_new_session_opens_the_latest_official_release(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    _clone(repository)
    release = repository.latest_equipment_release()
    assert release is not None

    seen = _seen(_app(repository).run())

    assert seen["scenario"] == OPERATIONS and seen["name"] == "운영 일정"
    assert (seen["revision_no"], seen["latest_no"], seen["release_no"]) == (1, 1, 1)
    assert seen["official_scenario"] and seen["official_pair"] and seen["space"]
    assert not seen["assumption"] and not seen["stale"]
    assert seen["token"] == _session(repository).token


def test_a_new_session_on_an_unpublished_newer_revision_opens_stale(tmp_path: Path) -> None:
    """공식 시나리오에 발행하지 않은 더 새 리비전이 있으면 새 세션은 공식 발행 그대로 연다 —
    낡음."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )

    seen = _seen(_app(repository).run())

    assert (seen["revision_no"], seen["latest_no"], seen["release_no"]) == (1, 2, 1)
    assert seen["official_pair"] and seen["stale"]


def test_another_scenario_is_an_assumption_and_locks_space_editing(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    clone = _clone(repository)
    app = _app(repository)
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)

    seen = _seen(app.run())

    assert seen["name"] == "셋업 실무" and seen["revision_no"] == 1
    assert seen["assumption"] and not seen["official_scenario"] and not seen["official_pair"]
    assert not seen["space"] and not seen["stale"]


def test_someone_elses_save_into_my_scenario_keeps_my_pin_and_marks_it_stale(
    tmp_path: Path,
) -> None:
    """남이 내 시나리오에 일정을 저장하면 세션은 고른 리비전 그대로다(고정) — 「최신 r2 있음」."""
    repository = _seeded(tmp_path)
    clone = _clone(repository)
    app = _app(repository)
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    before = _seen(app.run())

    theirs = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            theirs,
            clone.equipment_scenario_id,
            equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"),
        )
    )
    after = _seen(app.run())

    assert before["token"] == after["token"]
    assert (after["revision_no"], after["latest_no"]) == (1, 2)
    assert after["stale"] and not after["official_pair"]


def test_a_pinned_pair_that_no_longer_merges_moves_to_the_latest_with_a_notice(
    tmp_path: Path,
) -> None:
    """r1 에만 Qual일정이 있는 호기의 Qual상태를 남이 비우면(교차 검증은 최신·공식만 지킨다) r1 을
    든 세션은 다음 회차에 그 시나리오 최신으로 옮기고 한 번 알린다(검토 2-12)."""
    repository = _seeded(tmp_path)
    app = _app(repository)
    pinned = _seen(app.run())
    first = _session(repository)
    repository.save_equipment(
        _request(first, equipment=_set(first.equipment, "EQ-02", "Qual일정", None))
    )
    second = _session(repository)
    repository.save_equipment(
        _request(second, equipment=_set(second.equipment, "EQ-02", "Qual상태", None))
    )

    moved = _seen(app.run())

    assert pinned["revision_no"] == 1
    assert moved["revision_no"] == 2 and not moved["stale"]
    assert moved["notice"] is not None
    assert "「운영 일정」 r1" in moved["notice"] and "r2" in moved["notice"]
    assert "합칠 수 없어" in moved["notice"]
    # 다음 회차에는 다시 알리지 않는다.
    assert _seen(app.run())["notice"] is None


def _switching(database: str) -> None:
    """한 회차씩: 0 = 편집 + FAB 대기 → 버리기 확인 없이 고르기, 1 = 확인하고 고르기, 2 = 다시
    세움."""
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_KEY,
        ensure_equipment_drafts,
        pending_fab_layout,
        pop_discarded_notice,
        pop_drafts_replaced,
        replace_equipment_buffer,
        stage_fab_layout,
    )
    from capa_simulation.equipment_scenario_activation import (
        current_selection,
        resolve_equipment_session,
        select_equipment_scenario,
    )
    from capa_simulation.persistence.equipment_cache import load_equipment_scenario_catalog
    from capa_simulation.services.fab_layout import fab_marks_fingerprint, prepare_fab_layout_marks

    step = int(st.session_state.get("step", 0))
    st.session_state["step"] = step + 1
    session = resolve_equipment_session(database)
    frames = ensure_equipment_drafts(session.snapshot)
    target = next(
        item
        for item in load_equipment_scenario_catalog(database).scenarios
        if item.scenario_name == "셋업 실무"
    )
    if step == 0:
        edited = frames[1].copy()
        edited.loc[edited.index[0], "담당자"] = "미저장 편집"
        replace_equipment_buffer((frames[0], edited, frames[2]))
        stage_fab_layout(
            None,
            prepare_fab_layout_marks(
                [{"id": "B", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}],
                (101.0, 62.0),
            ),
            base=(None, fab_marks_fingerprint(())),
        )
        st.session_state["refusal"] = select_equipment_scenario(
            database,
            target.equipment_scenario_id,
            target.latest_schedule_revision_id,
            discard=False,
        )
        st.session_state["after_refusal"] = current_selection()
    elif step == 1:
        st.session_state["accepted"] = select_equipment_scenario(
            database,
            target.equipment_scenario_id,
            target.latest_schedule_revision_id,
            discard=True,
        )
        st.session_state["buffer_after"] = BUFFER_KEY in st.session_state
        st.session_state["fab_kept"] = pending_fab_layout() is not None
    else:
        st.session_state["replaced"] = pop_drafts_replaced()
        st.session_state["discarded"] = pop_discarded_notice()
        st.session_state["now"] = (session.scenario_name, session.revision_no)


def test_switching_with_unsaved_edits_needs_the_discard_check_and_keeps_the_fab(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    _clone(repository)
    app = AppTest.from_function(
        _switching, args=(str(repository.database_path),), default_timeout=60
    )
    app.run()
    app.run()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert "변경을 버리고 불러오기" in app.session_state["refusal"]
    assert app.session_state["after_refusal"][0] == OPERATIONS
    assert app.session_state["accepted"] is None
    assert app.session_state["buffer_after"] is False
    assert app.session_state["fab_kept"] is True
    # 고르기는 편집본을 비운 뒤라 「처음 세움」 이다 — 「다른 사용자가 저장」 알림이 없다.
    assert app.session_state["replaced"] is False
    assert app.session_state["discarded"] is None
    assert app.session_state["now"] == ("셋업 실무", 1)


def _own_save(database: str, change: str) -> None:
    """0 = 세움, 1 = 이 세션이 저장(일정 또는 공통), 2 = 다음 회차."""
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        save_equipment_buffer,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session
    from capa_simulation.persistence.equipment_cache import get_equipment_repository

    step = int(st.session_state.get("step", 0))
    st.session_state["step"] = step + 1
    session = resolve_equipment_session(database)
    frames = ensure_equipment_drafts(session.snapshot)
    st.session_state.setdefault("revisions", []).append(session.revision_no)
    if step == 1:
        edited = frames[1].copy()
        if change == "schedule":
            edited.loc[edited["설비명"].eq("EQ-02"), "Qual일정"] = pd.Timestamp("2026-08-25")
        else:
            edited.loc[edited.index[0], "담당자"] = "새 담당"
        st.session_state["message"] = save_equipment_buffer(
            get_equipment_repository(database),
            (frames[0], edited, frames[2]),
            "이 세션 저장",
            basis=session.save_basis(),
        )


@pytest.mark.parametrize(("change", "revisions"), [("schedule", [1, 1, 2]), ("common", [1, 1, 1])])
def test_an_own_schedule_save_moves_the_selection_and_a_common_save_keeps_it(
    tmp_path: Path, change: str, revisions: list[int]
) -> None:
    repository = _seeded(tmp_path)
    app = AppTest.from_function(
        _own_save, args=(str(repository.database_path), change), default_timeout=60
    )
    app.run()
    app.run()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["revisions"] == revisions
    message = app.session_state["message"]
    if change == "schedule":
        assert "「운영 일정」 r2" in message and "공식 v2" in message
    else:
        assert "공통 대장 r2" in message and "「운영 일정」" not in message


def _stale_workspace(database: str) -> None:
    """낡은 세션의 RawData — 일정 일곱 칸·비가동 표 잠김, 행 추가 막음, 잠금 알림."""
    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        render_equipment_data_workspace,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session
    from capa_simulation.persistence.equipment_cache import get_equipment_repository

    session = resolve_equipment_session(database)
    ensure_equipment_drafts(session.snapshot)
    snapshot = session.snapshot
    assert snapshot is not None
    render_equipment_data_workspace(
        repository=get_equipment_repository(database),
        latest_snapshot=snapshot,
        baseline=snapshot.baseline,
        equipment=snapshot.equipment,
        downtime=snapshot.downtime,
        floor_canvases={},
        max_extent=(100.0, 60.0),
        basis=session.save_basis(),
    )


def _all_nodes(app: AppTest) -> list[Any]:
    stack = list(app.main.children.values())
    nodes: list[Any] = []
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(getattr(node, "children", {}).values())
    return nodes


def _dataframes(app: AppTest) -> list[Any]:
    return [node.proto for node in _all_nodes(app) if getattr(node, "type", None) == "dataframe"]


@pytest.mark.parametrize("stale", [False, True])
def test_a_stale_session_locks_the_schedule_cells_and_row_adds_but_not_common_cells(
    tmp_path: Path, stale: bool
) -> None:
    repository = _seeded(tmp_path)
    if stale:
        session = _session(repository)
        repository.save_equipment(
            _request(
                session,
                equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
                publish_official=False,
            )
        )
    app = AppTest.from_function(
        _stale_workspace, args=(str(repository.database_path),), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    editors = [proto for proto in _dataframes(app) if proto.editing_mode != Dataframe.READ_ONLY]
    master = next(proto for proto in editors if "Qual일정" in json.loads(proto.columns or "{}"))
    columns = json.loads(master.columns)
    locked = {name for name, config in columns.items() if config.get("disabled")}
    if stale:
        assert locked == set(SCENARIO_SCHEDULE_COLUMNS)
        assert master.editing_mode == Dataframe.FIXED
        assert any("가 더 새롭습니다" in item.value for item in app.warning)
    else:
        assert not locked
        assert master.editing_mode == Dataframe.DYNAMIC
        assert not any("가 더 새롭습니다" in item.value for item in app.warning)
    # 낡은 세션에서 호기·비가동을 지우면 그 시나리오 일정도 바뀌어 저장이 늘 거부된다 — 「선택 행
    # 삭제」 를 끄고 까닭을 풍선으로 보인다. 기존 보유대수는 공통이라 그대로 지운다.
    deletes = {
        slug: next(
            button for button in app.button if button.key == f"equipment_{slug}_delete_selected_v1"
        )
        for slug in ("master", "baseline", "downtime")
    }
    assert deletes["master"].disabled is stale and deletes["downtime"].disabled is stale
    assert not deletes["baseline"].disabled
    if stale:
        assert "최신 r2 를 불러온 뒤 지우세요" in str(deletes["master"].help)
    # 칸 도움말 첫 마디가 어느 쪽인지 말한다.
    assert columns["Qual일정"]["help"].startswith("시나리오 — 「운영 일정」 에만 저장")
    assert columns["담당자"]["help"].startswith("공통 — 모든 설비 시나리오에 같은 값")
    assert columns["Qual상태"]["help"].startswith("공통 — 공식 일정 기준")
    assert any(SCENARIO_COLUMN_LEGEND == item.value for item in app.caption)


def test_a_stale_common_save_goes_through_and_a_schedule_save_is_refused(tmp_path: Path) -> None:
    """낡은 세션도 공통 칸은 저장된다. 일정을 고친 저장은 「「운영 일정」 r2」 충돌로 막힌다."""
    from capa_simulation.persistence.equipment_repository import EquipmentRevisionConflict

    repository = _seeded(tmp_path)
    pinned = _session(repository)
    repository.save_equipment(
        _request(
            pinned,
            equipment=_set(pinned.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    common = repository.latest_revision_id()
    assert common is not None and pinned.schedule is not None
    stale = repository.load_merged_snapshot(common, pinned.schedule.schedule_revision_id)

    result = repository.save_equipment(
        _request(stale, equipment=_set(stale.equipment, "EQ-01", "담당자", "공통만"))
    )
    assert result.common is not None and result.schedule is None
    fresh = repository.load_merged_snapshot(
        str(repository.latest_revision_id()), pinned.schedule.schedule_revision_id
    )
    with pytest.raises(EquipmentRevisionConflict, match="「운영 일정」 r2"):
        repository.save_equipment(
            _request(fresh, equipment=_set(fresh.equipment, "EQ-02", "Qual일정", "2026-09-30"))
        )


def test_a_stale_paste_that_changes_the_schedule_side_is_refused_before_preview(
    tmp_path: Path,
) -> None:
    from capa_simulation.components.equipment_data_workspace import (
        ImportReview,
        stale_paste_refusal,
    )

    saved = _session(_seeded(tmp_path))
    master = saved.equipment
    current = (saved.baseline, master, saved.downtime.iloc[0:0])
    basis = EquipmentSaveBasis(
        "operations", "운영 일정", release_no=1, stale=True, revision_no=1, latest_revision_no=2
    )

    def review(target: str, candidate: pd.DataFrame, downtime: pd.DataFrame) -> ImportReview:
        return ImportReview(
            target=target,
            payload="",
            source=current,
            candidate=(current[0], candidate, downtime),
            changes=pd.DataFrame(),
        )

    common_only = _set(master, "EQ-01", "담당자", "공통만")
    assert (
        stale_paste_refusal(review("설비 마스터", common_only, current[2]), current, basis) is None
    )
    dated = _set(master, "EQ-02", "Qual일정", "2026-09-30")
    refusal = stale_paste_refusal(review("설비 마스터", dated, current[2]), current, basis)
    assert refusal is not None and "호기 1대" in refusal and "최신 r2" in refusal
    added = pd.concat([master, master.iloc[[0]].assign(설비명="EQ-NEW")], ignore_index=True)
    refusal = stale_paste_refusal(review("설비 마스터", added, current[2]), current, basis)
    assert refusal is not None and "새 호기 1행" in refusal
    downtime = pd.DataFrame(
        {
            "설비명": ["EQ-01"],
            "비가동유형": ["PM"],
            "시작일": [pd.Timestamp("2026-09-01")],
            "종료일": [pd.NaT],
            "상세사유": [None],
            "비고": [None],
        }
    )
    refusal = stale_paste_refusal(review("비가동 일정", master, downtime), current, basis)
    assert refusal is not None and "비가동 일정" in refusal


def test_the_save_fields_defaults_are_the_recommended_answers() -> None:
    """질문 1(공식 발행)·F6(새 호기 함께 넣기)·F2(새 비가동 모든 시나리오)는 기본 켬 — 한 곳."""
    assert DEFAULT_PUBLISH_OFFICIAL and DEFAULT_PROPAGATE_NEW_UNITS
    assert DEFAULT_PROPAGATE_NEW_DOWNTIME


def test_the_save_result_names_both_sides_the_propagation_the_release_and_removed_units() -> None:
    from datetime import datetime

    common = EquipmentRevisionSummary("c3", 3, None, 0, 2, 0, datetime(2026, 10, 24))
    schedule = EquipmentScheduleRevisionSummary(
        "s5", "operations", 5, "save", datetime(2026, 10, 24)
    )
    result = EquipmentSaveResult(
        common=common,
        schedule=schedule,
        propagated=(
            PropagatedRevision(
                "setup", "셋업 실무", 4, 2, downtime=(("EQ-NEW", "PM", "2026-09-01"),), skipped=1
            ),
        ),
        release_no=3,
        new_units=("EQ-NEW",),
        removed_units=("EQ-OLD",),
    )

    message = save_result_message(result, scenario_name="운영 일정")

    assert "공통 대장 r3 · 「운영 일정」 r5" in message
    assert "「셋업 실무」 r4(호기 2대 · 비가동 1건)" in message
    assert "비가동 1건은" in message
    assert "공식 v3으로 발행했습니다" in message
    assert "지운 호기 1대는 모든 설비 시나리오에서 빠졌습니다" in message
    assert "Space 편집기 「이름 바꾸기」" in message

    withheld = save_result_message(
        EquipmentSaveResult(common=None, schedule=schedule, release_withheld=True),
        scenario_name="운영 일정",
    )
    assert "공식 발행은 하지 않았습니다" in withheld and "「설비 시나리오」 탭" in withheld


def test_column_help_says_common_status_or_scenario() -> None:
    assert scenario_column_help("Qual일정", "셋업 실무") == "시나리오 — 「셋업 실무」 에만 저장"
    assert scenario_column_help("시나리오 메모", None) == "시나리오 — 지금 설비 시나리오에만 저장"
    assert scenario_column_help("반입상태", None) == "공통 — 공식 일정 기준"
    assert scenario_column_help("Maker", None) == "공통 — 모든 설비 시나리오에 같은 값"


def _catalog(*, release_rev: str | None, latest: str, latest_no: int) -> EquipmentScenarioCatalog:
    from datetime import datetime

    return EquipmentScenarioCatalog(
        scenarios=(
            EquipmentScenarioSummary(
                "operations",
                "운영 일정",
                "ACTIVE",
                list_order=1,
                latest_schedule_revision_id=latest,
                latest_revision_no=latest_no,
                revision_count=latest_no,
            ),
        ),
        latest_release=(
            EquipmentRelease(3, "operations", release_rev, datetime(2026, 10, 24))
            if release_rev is not None
            else None
        ),
    )


def test_the_row_label_and_badge_follow_the_three_judgements() -> None:
    catalog = _catalog(release_rev="s12", latest="s12", latest_no=12)
    official = EquipmentSession(catalog, catalog.scenarios[0], "s12")
    assert equipment_value_label(official) == "운영 일정 · r12"
    assert equipment_status_badge(official, unsaved=False) == ":green-badge[공식 v3]"
    assert equipment_status_badge(official, unsaved=True) == ":orange-badge[미저장 변경]"

    newer = _catalog(release_rev="s12", latest="s14", latest_no=14)
    stale = EquipmentSession(newer, newer.scenarios[0], "s12")
    assert stale.stale and stale.is_official_pair
    # 공식 발행 쌍이면 낡아도 「공식 v3」 이 먼저다 — 낡음은 본문 배너와 잠근 칸이 말한다.
    assert equipment_status_badge(stale, unsaved=False) == ":green-badge[공식 v3]"
    older = EquipmentSession(newer, newer.scenarios[0], "s11")
    assert equipment_status_badge(older, unsaved=False) == ":orange-badge[최신 r14 있음]"
    unpublished = _catalog(release_rev="s12", latest="s14", latest_no=14)
    latest = EquipmentSession(unpublished, unpublished.scenarios[0], "s14")
    assert equipment_status_badge(latest, unsaved=False) == ":gray-badge[저장된 리비전]"


# ── app.py 와 함께 ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def _shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 시나리오 DB(내장 시드) + 래퍼로 한 번 저장한 설비 DB 를 보는 `app.py`."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    _seeded(tmp_path)
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def _field(app: AppTest) -> Any:
    return next(
        (button for button in app.sidebar.button if button.key == EQUIPMENT_SCENARIO_FIELD_KEY),
        None,
    )


def _sidebar_captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.sidebar.caption]


def test_the_row_stands_on_the_equipment_screens_with_this_runs_label(_shell: AppTest) -> None:
    app = _shell.run()
    assert _field(app) is None  # HOME 은 설비 시나리오를 읽지 않는다

    for spec in (AVAILABLE_EQUIPMENT_STATUS, REQUIRED_SHORTENING, PROCESS_CAPA_DETAIL):
        app.switch_page(spec.path).run()
        assert not app.exception, [item.message for item in app.exception]
        field = _field(app)
        assert field is not None, spec.path
        assert field.label == "운영 일정 · r1" and not field.disabled
        assert ":green-badge[공식 v1]" in _sidebar_captions(app)

    app.switch_page(SPACE_STATUS.path).run()
    assert not app.exception, [item.message for item in app.exception]
    field = _field(app)
    assert field is not None and field.disabled
    assert field.label == "운영 일정 · r1 (고정)"


def test_every_equipment_tab_has_the_equipment_row(_shell: AppTest) -> None:
    """설비 데이터를 읽지 않던 Qual 마감 계산기 탭은 필요 단축 일정 팝업으로 옮겼다(2026-10-24) —
    가용설비 현황에는 줄을 빼는 탭이 없다."""
    assert AVAILABLE_EQUIPMENT_STATUS.equipment_scenario_tabs is None
    app = _shell.run()
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run()
    assert _field(app) is not None
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_GAP_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert _field(app) is not None


def test_the_badge_turns_when_someone_else_publishes_in_the_same_run(
    _shell: AppTest, tmp_path: Path
) -> None:
    """공식이 바뀌면 고정한 세션 줄은 그 회차에 「최신 r2 있음」 으로 바뀐다 — 줄을 페이지가 그
    회차 목록으로 그리므로 한 회차 늦지 않는다."""
    app = _shell.run()
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run()
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    field = _field(app)
    assert field is not None and field.label == "운영 일정 · r1"
    assert ":orange-badge[최신 r2 있음]" in _sidebar_captions(app)


def test_the_shell_never_opens_the_equipment_repository_and_a_warm_page_run_does_not_either(
    _shell: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`app.py` 는 설비 DB 를 열지 않는다(HOME 회차에 저장소 호출 0). 설비 화면도 바뀐 것 없는
    회차는 목록·공통 최신·합친 본문을 캐시에서 받아 저장소를 부르지 않는다."""
    calls: list[str] = []
    for name, value in list(vars(DuckDBEquipmentRepository).items()):
        if name.startswith("__") or not callable(value):
            continue

        def counted(*args: object, __name: str = name, __func: Any = value, **kw: object) -> Any:
            calls.append(__name)
            return __func(*args, **kw)

        monkeypatch.setattr(DuckDBEquipmentRepository, name, counted)

    app = _shell.run()
    assert not app.exception, [item.message for item in app.exception]
    assert calls == []

    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run()
    assert not app.exception, [item.message for item in app.exception]
    assert calls  # 첫 진입은 읽는다
    calls.clear()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert calls == []


# ── 팝업 ─────────────────────────────────────────────────────────────────────────────


def _popup(database: str, page_file: str) -> None:
    """설비 화면 한 회차 + 팝업 본문(호스트 프래그먼트 없이 본문만). `edit` 이면 처음 한 번 공통 칸
    하나를 고친다."""
    from pathlib import Path

    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        replace_equipment_buffer,
    )
    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    session = resolve_equipment_session(database)
    frames = ensure_equipment_drafts(session.snapshot)
    if st.session_state.get("edit") and not st.session_state.get("edited"):
        edited = frames[1].copy()
        edited.loc[edited.index[0], "담당자"] = "팝업 저장"
        replace_equipment_buffer((frames[0], edited, frames[2]))
        st.session_state["edited"] = True
    st.session_state["now"] = (session.scenario_name, session.revision_no)
    render_equipment_scenario_dialog_body(Path(database), page_file=page_file)


def test_the_popup_loads_another_scenario_and_says_so(tmp_path: Path) -> None:
    from capa_simulation.components.equipment_scenario_status import (
        DIALOG_REVISION_KEY,
        DIALOG_SCENARIO_KEY,
        FLASH_KEY,
        LOAD_BUTTON_KEY,
    )

    repository = _seeded(tmp_path)
    clone = _clone(repository)
    app = AppTest.from_function(
        _popup,
        args=(str(repository.database_path), Path(AVAILABLE_EQUIPMENT_STATUS.path).name),
        default_timeout=60,
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["now"] == ("운영 일정", 1)

    app.selectbox(key=DIALOG_SCENARIO_KEY).set_value(clone.equipment_scenario_id).run()
    assert app.session_state[DIALOG_REVISION_KEY] == clone.latest_schedule_revision_id
    app.button(key=LOAD_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["now"] == ("셋업 실무", 1)
    assert app.session_state[FLASH_KEY] == "설비 시나리오 「셋업 실무」 r1 을 불러왔습니다."


@pytest.mark.parametrize(
    ("page", "modes"),
    [
        (AVAILABLE_EQUIPMENT_STATUS.path, ["불러오기", "저장"]),
        (REQUIRED_SHORTENING.path, ["불러오기", "저장"]),
        (PROCESS_CAPA_DETAIL.path, None),
    ],
)
def test_the_save_section_stands_only_on_the_screens_that_build_the_draft(
    tmp_path: Path, page: str, modes: list[str] | None
) -> None:
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
    )

    repository = _seeded(tmp_path)
    app = AppTest.from_function(
        _popup, args=(str(repository.database_path), Path(page).name), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    controls = [
        widget
        for widget in app.get("button_group")
        if getattr(widget, "key", None) == EQUIPMENT_SCENARIO_DIALOG_MODE_KEY
    ]
    if modes is None:
        assert controls == []
    else:
        assert [list(getattr(widget, "options", ())) for widget in controls] == [modes]


def test_the_popup_save_writes_the_edit_into_the_session_scenario(tmp_path: Path) -> None:
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        FLASH_KEY,
        SAVE_BUTTON_KEY,
        SAVE_MODE,
    )

    repository = _seeded(tmp_path)
    app = AppTest.from_function(
        _popup,
        args=(str(repository.database_path), Path(AVAILABLE_EQUIPMENT_STATUS.path).name),
        default_timeout=60,
    )
    app.session_state["edit"] = True
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.button(key=SAVE_BUTTON_KEY).disabled
    app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert "공통 대장 r2" in app.session_state[FLASH_KEY]
    assert repository.list_revisions()[0].revision_no == 2
