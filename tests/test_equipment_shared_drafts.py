# Purpose: RawData 와 Space 편집기가 같은 편집본·미저장 층 배치를 한 저장으로 끝내는지 검사한다.

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


def _seeded(path: Path) -> None:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")


def _space_first(database: str) -> None:
    """Space 가 먼저 열려 편집본을 세우고 호기 하나를 옮긴 뒤 RawData 가 열리는 회차를 흉내 낸다."""
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_KEY,
        EQUIPMENT_EDITOR_KEY,
        ensure_equipment_drafts,
        equipment_buffer_generation,
        replace_equipment_buffer,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    if "step" not in st.session_state:
        st.session_state["step"] = 0
    step = st.session_state["step"]
    st.session_state["step"] = step + 1
    frames = ensure_equipment_drafts(latest)
    if step == 0:
        st.session_state[f"{EQUIPMENT_EDITOR_KEY}_applied_view"] = "옛 보기"
        before = equipment_buffer_generation()
        moved = frames[1].copy()
        moved.loc[moved["호기"].eq("EQ-01"), "X좌표"] = 55.0
        replace_equipment_buffer((frames[0], moved, frames[2]))
        st.session_state["generation_bumped"] = equipment_buffer_generation() > before
        st.session_state["applied_view_dropped"] = (
            f"{EQUIPMENT_EDITOR_KEY}_applied_view" not in st.session_state
        )
    # 다음 회차에 RawData 쪽이 같은 helper 로 다시 세워도 Space 편집이 남아야 한다.
    buffer = st.session_state[BUFFER_KEY][1]
    st.session_state["x"] = float(buffer.loc[buffer["호기"].eq("EQ-01"), "X좌표"].iloc[0])


def test_an_edit_made_in_space_first_survives_when_rawdata_seeds_later(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(_space_first, args=(str(database),), default_timeout=30).run()
    app.run()

    assert not app.exception
    assert app.session_state["generation_bumped"] is True
    # 편집표가 옛 보기 프레임을 그리다 Space 편집을 되돌리지 않게 보기 칸을 버린다.
    assert app.session_state["applied_view_dropped"] is True
    assert app.session_state["x"] == 55.0


def _save_with_pending_layout(database: str, revision_optional: bool) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        PENDING_CANVASES_KEY,
        PENDING_MARKS_KEY,
        ensure_equipment_drafts,
        pending_floor_canvases,
        save_equipment_buffer,
        stage_floor_canvas,
        stage_floor_marks,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.floor_layout_mark import prepare_floor_layout_marks

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    frames = ensure_equipment_drafts(latest)
    master = frames[1].copy()
    if not revision_optional:
        # 넓힌 캔버스(130) 안에만 들어가는 자리. 저장된 캔버스(기본 100)로 검증하면 막힌다.
        master.loc[master["호기"].eq("EQ-01"), "X좌표"] = 110.0
    stage_floor_canvas(("C1", "1F"), (130.0, 60.0))
    stage_floor_marks(
        ("C1", "1F"),
        prepare_floor_layout_marks(
            [{"id": "MK-1", "kind": "column", "x": 1, "y": 1, "w": 1.5, "h": 1.5}], (130.0, 60.0)
        ),
    )
    st.session_state["staged"] = pending_floor_canvases()
    st.session_state["message"] = save_equipment_buffer(
        repository, (frames[0], master, frames[2]), "배치", revision_optional=revision_optional
    )
    st.session_state["cleared"] = (
        PENDING_CANVASES_KEY not in st.session_state and PENDING_MARKS_KEY not in st.session_state
    )


def test_rawdata_save_carries_the_canvas_space_enlarged(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(
        _save_with_pending_layout, args=(str(database), False), default_timeout=30
    ).run()

    assert not app.exception
    assert app.session_state["staged"] == {("C1", "1F"): (130.0, 60.0)}
    assert "r2" in app.session_state["message"] and "도면 요소" in app.session_state["message"]
    assert app.session_state["cleared"] is True
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (130.0, 60.0)
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["MK-1"]


def test_a_space_save_without_master_changes_makes_no_revision(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(
        _save_with_pending_layout, args=(str(database), True), default_timeout=30
    ).run()

    assert not app.exception
    assert "새 리비전 없이" in app.session_state["message"]
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1
    assert len(repository.load_floor_layout_marks("C1", "1F")) == 1


def _edit_then_someone_saves(database: str) -> None:
    """이 세션이 배치를 대기시킨 사이 다른 사람이 r2 를 저장하는 회차들을 흉내 낸다."""
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        pending_floor_marks,
        pop_discarded_notice,
        save_equipment_buffer,
        stage_floor_marks,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.floor_layout_mark import prepare_floor_layout_marks

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    step = st.session_state.get("step", 0)
    st.session_state["step"] = step + 1
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    frames = ensure_equipment_drafts(latest)
    if step == 0:
        stage_floor_marks(
            ("C1", "1F"),
            prepare_floor_layout_marks(
                [{"id": "MK-1", "kind": "door", "x": 1, "y": 1, "w": 2, "h": 2}], (100.0, 60.0)
            ),
        )
        other = frames[1].copy()
        other.loc[other["호기"].eq("EQ-02"), "담당자"] = "담당B"
        repository.save_snapshot(frames[0], other, frames[2], note="다른 사람")
        return
    st.session_state["notice"] = pop_discarded_notice()
    st.session_state["pending"] = pending_floor_marks()
    st.session_state["message"] = save_equipment_buffer(
        repository, frames, "", revision_optional=True
    )


def test_someone_elses_save_discards_pending_layouts_and_says_so(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(
        _edit_then_someone_saves, args=(str(database),), default_timeout=30
    ).run()
    app.run()

    assert not app.exception
    assert "r2" in app.session_state["notice"] and "버리고" in app.session_state["notice"]
    assert app.session_state["pending"] == {}
    # 대기분이 버려진 뒤의 저장은 쓴 것이 없다고 말한다(「저장했습니다」가 아니다).
    assert app.session_state["message"] == "바뀐 내용이 없어 저장하지 않았습니다."
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_floor_layout_marks("C1", "1F") == ()
    assert len(repository.list_revisions()) == 2


def _stage_before_seeding(database: str) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        pending_floor_canvases,
        stage_floor_canvas,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    # 콜백처럼 편집본이 서기 **전에** 대기시킨다. 처음 세우는 회차가 이것을 지우면 안 된다.
    stage_floor_canvas(("C1", "1F"), (130.0, 60.0))
    ensure_equipment_drafts(repository.load_snapshot(str(repository.latest_revision_id())))
    st.session_state["pending"] = pending_floor_canvases()


def test_a_layout_staged_before_the_first_seeding_survives(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(
        _stage_before_seeding, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception
    assert app.session_state["pending"] == {("C1", "1F"): (130.0, 60.0)}


def _popup_after_staging(database: str) -> None:
    """요소를 대기시킨 층의 캔버스를 같은 세션이 팝업으로 저장한 뒤 배치를 저장한다."""
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        rebase_floor_canvas,
        save_equipment_buffer,
        stage_floor_canvas,
        stage_floor_marks,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.floor_layout_mark import (
        marks_fingerprint,
        prepare_floor_layout_marks,
    )

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    frames = ensure_equipment_drafts(repository.load_snapshot(str(repository.latest_revision_id())))
    key = ("C1", "1F")
    base = (None, marks_fingerprint(repository.load_floor_layout_marks(*key)))
    stage_floor_marks(
        key,
        prepare_floor_layout_marks(
            [{"id": "D1", "kind": "door", "x": 1, "y": 1, "w": 2, "h": 2}], (100.0, 60.0)
        ),
        base=base,
    )
    # 팝업 저장과 같은 순서: 저장 → 대기분 기준 캔버스 갈기 → 대기 캔버스 버리기.
    repository.save_floor_layout_canvas(*key, 120, 60)
    rebase_floor_canvas(key, (120.0, 60.0))
    stage_floor_canvas(key, None)
    st.session_state["message"] = save_equipment_buffer(
        repository, frames, "", revision_optional=True
    )


def test_a_popup_canvas_save_does_not_lock_out_the_pending_marks(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(
        _popup_after_staging, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert "새 리비전 없이" in app.session_state["message"]
    repository = DuckDBEquipmentRepository(database)
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["D1"]


def _replaced_flag(database: str) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        equipment_buffer_generation,
        pop_drafts_replaced,
        replace_equipment_buffer,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    step = st.session_state.get("step", 0)
    st.session_state["step"] = step + 1
    frames = ensure_equipment_drafts(repository.load_snapshot(str(repository.latest_revision_id())))
    st.session_state.setdefault("flags", []).append(pop_drafts_replaced())
    if step == 0:
        before = equipment_buffer_generation()
        # 내용이 그대로인 제출은 세대를 올리지 않는다(버림 알림 오탐을 막는다).
        replace_equipment_buffer(tuple(frame.copy() for frame in frames))
        st.session_state["bumped"] = equipment_buffer_generation() > before
        other = frames[1].copy()
        other.loc[other["호기"].eq("EQ-02"), "담당자"] = "담당B"
        repository.save_snapshot(frames[0], other, frames[2], note="다른 사람")


def test_the_run_that_reseeds_after_someone_elses_save_is_flagged_once(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    _seeded(database)
    app = AppTest.from_function(_replaced_flag, args=(str(database),), default_timeout=30).run()
    app.run()
    app.run()

    assert not app.exception
    assert app.session_state["bumped"] is False
    # 다른 사람의 저장을 본 회차에만 참이다 — RawData 는 그 회차의 제출을 반영하지 않는다.
    assert app.session_state["flags"] == [False, True, False]
