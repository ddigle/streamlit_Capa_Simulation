# Purpose: Space 층 상세의 배치 편집기가 편집본·대기분에 적용하고 한 번에 저장하는 흐름을 검사한다.

"""브라우저 편집기(JS)는 AppTest 가 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어
두고, 세션에 넣어 둔 적용값을 돌려준다 — 그 뒤의 검증·반영·저장은 실제 코드가 돈다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import _master

from capa_simulation.components import space_layout_editor
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_floor_layout_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.floor_layout_mark import floor_layout_fingerprint

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
FAKE_APPLY_KEY = "test_fake_editor_apply"


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _open_editor(tmp_path: Path, equipment: pd.DataFrame | None = None) -> tuple[AppTest, Path]:
    database = tmp_path / "space_edit.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(
        _baseline(), _equipment() if equipment is None else equipment, _downtime(), note="r1"
    )
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    return app, database


def test_the_editor_receives_the_floor_from_the_shared_draft(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, _ = _open_editor(tmp_path)

    assert not app.exception
    data = editor_calls[-1]
    assert [(item["id"], item["placed"]) for item in data["items"]] == [
        ("EQ-01", True),
        ("EQ-02", True),
    ]
    assert data["floor"] == "C1 1F" and "C2 2F" in data["floors"]
    assert data["canvas"] == {"width": 100.0, "height": 60.0}
    # 편집을 켜기 전 회차는 보기 전용 뷰어였고, 켠 뒤에는 뷰어를 부르지 않는다(도면 자리에 편집기).
    assert editor_calls[0]["mode"] == "view"
    assert data.get("mode") != "view"
    # 뷰어와 편집기는 같은 범위라 브라우저가 기억하는 도면 높이를 함께 쓴다(보기·편집에서 상자
    # 크기가 같다). 높이는 브라우저 몫이라 data 에 실리지 않는다.
    assert editor_calls[0]["scope"] == data["scope"] == "floor"
    assert not {key for key in data if "height" in key.lower()}
    clear_equipment_repository()


def test_an_apply_lands_in_the_draft_and_one_save_writes_master_and_marks(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, database = _open_editor(tmp_path)
    epoch = editor_calls[-1]["epoch"]

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": epoch,
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": [{"id": "D1", "kind": "door", "x": 80, "y": 0, "w": 4, "h": 4}],
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("편집본에 적용했습니다" in item.value for item in app.success)
    panel = app.markdown
    assert any("호기 배치 1건 · 도면 요소 1개 층" in item.value for item in panel)
    # 설비 리비전이 생기는 저장이라 메모 칸이 선다(FAB 만 바뀐 저장에서만 숨긴다).
    assert [item for item in app.text_input if item.label == "변경 메모"]
    # 적용 뒤 epoch 가 바뀌어 브라우저가 새 값으로 다시 선다.
    assert editor_calls[-1]["epoch"] != epoch
    moved = next(item for item in editor_calls[-1]["items"] if item["id"] == "EQ-01")
    assert (moved["x"], moved["y"]) == (40.0, 20.0)
    # 저장 전에는 DB 가 그대로다.
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("r2" in item.value for item in app.success)
    saved = repository.load_snapshot(str(repository.latest_revision_id()))
    assert saved.equipment.set_index("설비명").loc["EQ-01", "X좌표"] == 40.0
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["D1"]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    # 저장은 콜백이라 회차를 끊지 않는다 — 아래의 `배치 편집` 토글이 꺼지지 않고 편집기가 새
    # 저장본으로 다시 선다(본문에서 저장하고 st.rerun() 하면 안 그린 토글 상태가 버려졌다).
    assert app.toggle(key="space_layout_edit_mode").value is True
    calls_after_save = len(editor_calls)
    assert editor_calls[-1]["epoch"].split("|")[2] == str(repository.latest_revision_id())
    assert calls_after_save > 0
    clear_equipment_repository()


def test_a_marks_only_save_writes_no_revision(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, database = _open_editor(tmp_path)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [],
        "canvas": {"width": 120, "height": 60},
        "marks": [{"id": "Z1", "kind": "zone", "x": 101, "y": 0, "w": 10, "h": 10}],
    }
    app.run()
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("새 리비전 없이" in item.value for item in app.success)
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (120.0, 60.0)
    clear_equipment_repository()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"changes": [{"id": "EQ-01", "placed": True, "x": 95, "y": 0, "w": 12, "h": 7}]},
            "벗어났습니다",
        ),
        (
            {
                "changes": [],
                "marks": [{"id": "Q", "kind": "window", "x": 0, "y": 0, "w": 1, "h": 1}],
            },
            "종류를 알 수 없습니다",
        ),
    ],
)
def test_a_bad_apply_is_refused_with_its_reason_and_leaves_the_draft(
    tmp_path: Path,
    editor_calls: list[dict[str, Any]],
    payload: dict[str, Any],
    message: str,
) -> None:
    app, _ = _open_editor(tmp_path)
    epoch = editor_calls[-1]["epoch"]
    app.session_state[FAKE_APPLY_KEY] = {"epoch": epoch, **payload}
    app.run()

    assert not app.exception
    assert any(message in item.value for item in app.error)
    assert editor_calls[-1]["epoch"] == epoch
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_a_module_group_apply_is_tiled_and_carries_its_hidden_module(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """페이지 적용 경로가 모듈 묶음 정규화(`editor_items`)와 숨은 모듈(`editor_ghosts`)을 넘긴다 —
    한 눈금 어긋난 브라우저 값은 칸 값으로 바로잡혀 편집본에 들어가고, 묶음과 함께 옮겨진 숨은
    모듈(레이아웃표시 N)도 제 칸으로 가며 N 은 그대로다."""
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    master = _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0, "레이아웃표시": "N"},
        {**module, "설비명": "G1-C", "X좌표": 50.0, "Y좌표": 30.0},
        {**module, "설비명": "G1-D", "X좌표": 60.0, "Y좌표": 30.0},
    )
    app, _ = _open_editor(tmp_path, master)
    data = editor_calls[-1]
    assert data["ghosts"] == [
        {"id": "G1-B", "group": "GRP-1", "x": 60.0, "y": 37.0, "w": 10.0, "h": 7.0}
    ]
    assert "G1-B" not in {item["id"] for item in data["items"]}

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [
            {"id": "G1-A", "placed": True, "x": 52, "y": 37, "w": 10, "h": 7},
            {"id": "G1-C", "placed": True, "x": 52, "y": 30, "w": 10, "h": 7},
            {"id": "G1-D", "placed": True, "x": 61.9, "y": 30, "w": 10, "h": 7},
        ],
        "ghosts": [{"id": "G1-B", "x": 62, "y": 37, "w": 10, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert any("편집본에 적용했습니다" in item.value for item in app.success)
    after = editor_calls[-1]
    assert {
        item["id"]: (item["x"], item["y"], item["w"], item["h"])
        for item in after["items"]
        if item["group"] == "GRP-1"
    } == {
        "G1-A": (52.0, 37.0, 10.0, 7.0),
        "G1-C": (52.0, 30.0, 10.0, 7.0),
        "G1-D": (62.0, 30.0, 10.0, 7.0),
    }
    assert after["ghosts"] == [
        {"id": "G1-B", "group": "GRP-1", "x": 62.0, "y": 37.0, "w": 10.0, "h": 7.0}
    ]
    clear_equipment_repository()


def test_a_group_label_apply_saves_without_a_revision_and_follows_a_rename(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """Main 설비명 위치(2026-10-23 사용자 요청)는 적용 → 대기분 → 「배치 저장」 한 번에 층
    현행값으로 쓰이고 설비 리비전을 만들지 않는다. 뷰어도 같은 위치를 받는다. Main 설비 이름을
    바꾸면 위치가 새 이름으로 따라간다. 모듈 둘(한 줄 묶음)은 처음 위치가 위라 가운데를 고르면
    가운데 행이 선다."""
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    master = _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0},
    )
    app, database = _open_editor(tmp_path, master)
    assert editor_calls[-1]["groupLabels"] == {}

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [],
        "marks": None,
        "canvas": None,
        "groupLabels": [{"group": "GRP-1", "position": "center"}],
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert any("Main 설비명 위치 1개 층" in item.value for item in app.markdown)
    assert editor_calls[-1]["groupLabels"] == {"GRP-1": "center"}
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_floor_group_labels("C1", "1F") == {}

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    # 알림은 실제로 저장한 것만 말한다(위치만 바꿨으면 「Main 설비명 위치만」).
    assert any(
        "새 리비전 없이 Main 설비명 위치만 저장했습니다" in item.value for item in app.success
    ), [item.value for item in app.success]
    assert len(repository.list_revisions()) == 1
    assert repository.load_floor_group_labels("C1", "1F") == {"GRP-1": "center"}
    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    viewer = editor_calls[-1]
    assert viewer["mode"] == "view" and viewer["groupLabels"] == {"GRP-1": "center"}

    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [],
        "marks": None,
        "canvas": None,
        "renames": [{"kind": "group", "from": "GRP-1", "to": "GRP-X"}],
        "groupLabels": [{"group": "GRP-1", "position": "bottom"}],
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert editor_calls[-1]["groupLabels"] == {"GRP-X": "bottom"}
    app.button(key="space_layout_save").click().run()
    assert repository.load_floor_group_labels("C1", "1F") == {"GRP-X": "bottom"}
    clear_equipment_repository()


def _label_master() -> pd.DataFrame:
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    return _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0},
    )


def _apply_label(app: AppTest, calls: list[dict[str, Any]], position: str) -> None:
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": calls[-1]["epoch"],
        "changes": [],
        "marks": None,
        "canvas": None,
        "groupLabels": [{"group": "GRP-1", "position": position}],
    }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]


def _save_labels_elsewhere(database: Path, master: pd.DataFrame, labels: dict[str, str]) -> None:
    """다른 세션이 같은 층 위치만 저장한다(그 세션이 본 저장값 위에서 — 리비전은 만들지 않는다).
    같은 프로세스의 저장처럼 층 캐시를 비운다."""
    repository = DuckDBEquipmentRepository(database)
    seen = floor_layout_fingerprint(
        repository.load_floor_layout_marks("C1", "1F"),
        repository.load_floor_group_labels("C1", "1F"),
    )
    saved = repository.save_space_layout(
        _baseline(),
        master,
        _downtime(),
        floor_group_labels={("C1", "1F"): labels},
        floor_layout_bases={("C1", "1F"): (None, seen)},
    )
    assert saved is None
    clear_floor_layout_cache()


def test_a_label_only_apply_keeps_its_base_and_does_not_overwrite_a_newer_save(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """위치만 적용한 대기분도 편집을 시작할 때 본 저장값(`FloorLayoutBase`)을 쥔다. 그 사이 다른
    세션이 같은 층 위치를 저장했으면 「배치 저장」 이 거부되고 남의 위치가 남는다."""
    master = _label_master()
    app, database = _open_editor(tmp_path, master)
    _apply_label(app, editor_calls, "center")
    assert ("C1", "1F") in app.session_state["equipment_pending_floor_bases_v1"]

    _save_labels_elsewhere(database, master, {"GRP-1": "bottom"})
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("다른 사용자가 먼저 바꿔" in item.value for item in app.error), [
        item.value for item in app.error
    ]
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_floor_group_labels("C1", "1F") == {"GRP-1": "bottom"}
    assert len(repository.list_revisions()) == 1
    clear_equipment_repository()


def test_returning_a_label_to_its_saved_position_drops_the_pending_label(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """위치를 저장값으로 되돌려 적용하면 그 층 위치 대기분과 본 저장값이 빠지고 「저장 안 한 배치」
    줄에서도 사라진다. 모듈 둘(한 줄 묶음)의 저장값은 행이 없는 처음 위치(위)다."""
    app, _ = _open_editor(tmp_path, _label_master())
    _apply_label(app, editor_calls, "bottom")
    assert any("Main 설비명 위치 1개 층" in item.value for item in app.markdown)

    _apply_label(app, editor_calls, "top")

    assert ("C1", "1F") not in app.session_state["equipment_pending_floor_group_labels_v1"]
    assert ("C1", "1F") not in app.session_state["equipment_pending_floor_bases_v1"]
    assert not any("Main 설비명 위치" in item.value for item in app.markdown)
    assert editor_calls[-1]["groupLabels"] == {}
    clear_equipment_repository()


def test_the_editor_and_viewer_redraw_when_only_positions_are_saved_elsewhere(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """편집기·뷰어 epoch 는 요소와 위치를 함께 본 지문이다 — 다른 세션이 위치만 저장해도 새 값으로
    다시 선다(요소 지문만 보면 옛 위치를 쥔 채 남는다)."""
    master = _label_master()
    app, database = _open_editor(tmp_path, master)
    before = editor_calls[-1]

    _save_labels_elsewhere(database, master, {"GRP-1": "top"})
    app.run()

    after = editor_calls[-1]
    assert after.get("mode") != "view" and after["groupLabels"] == {"GRP-1": "top"}
    assert after["epoch"] != before["epoch"]

    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    viewer = editor_calls[-1]
    assert viewer["mode"] == "view" and viewer["groupLabels"] == {"GRP-1": "top"}
    _save_labels_elsewhere(database, master, {"GRP-1": "bottom"})
    app.run()

    redrawn = editor_calls[-1]
    assert redrawn["mode"] == "view" and redrawn["groupLabels"] == {"GRP-1": "bottom"}
    assert redrawn["epoch"] != viewer["epoch"]
    clear_equipment_repository()


def test_an_apply_from_an_old_editor_is_not_applied(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, _ = _open_editor(tmp_path)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": "old",
        "changes": [{"id": "EQ-01", "placed": False, "w": 12, "h": 7}],
    }
    app.run()

    assert not app.exception
    assert any("다시 서는 사이" in item.value for item in app.warning)
    assert all(item["placed"] for item in editor_calls[-1]["items"])
    clear_equipment_repository()


def test_the_drawing_popup_will_not_cut_off_saved_marks(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """도면 요소는 캔버스 밖에 둘 수 없다. 팝업이 누르기 전에 말하고 저장·삭제 단추를 막는다."""
    database = tmp_path / "space_popup.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_canvases={("C1", "1F"): (130.0, 60.0)},
        floor_marks={
            ("C1", "1F"): [{"id": "C", "kind": "column", "x": 120, "y": 0, "w": 2, "h": 2}]
        },
    )
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.button(key="space_floor_layout_open_C1_1F").click().run()

    assert not app.exception
    # 지우면 기본 100 × 60 으로 돌아가 기둥(오른쪽 122)이 밖으로 나간다.
    assert app.button(key="space_floor_layout_delete_C1_1F").disabled
    app.checkbox(key="space_floor_layout_auto_C1_1F").uncheck().run()
    next(widget for widget in app.number_input if widget.label == "캔버스 폭").set_value(100).run()

    assert not app.exception
    assert any("도면 요소가 범위를 벗어나" in item.value for item in app.warning)
    assert app.button(key="space_floor_layout_save_C1_1F").disabled
    clear_equipment_repository()


def test_an_invalid_rawdata_draft_does_not_take_the_space_page_down(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """RawData 의 검증 실패 편집이 편집본에 남아도 Space 는 열린다 — 상자는 경고만 건너뛴다."""
    app, _ = _open_editor(tmp_path)
    baseline, master, downtime = app.session_state["equipment_workspace_buffers_v1"]
    broken = master.copy()
    broken.loc[broken["설비명"].eq("EQ-01"), "X좌표"] = 40.0
    broken = pd.concat([broken, broken.iloc[[1]]], ignore_index=True)  # 호기 중복
    app.session_state["equipment_workspace_buffers_v1"] = (baseline, broken, downtime)
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("겹침 경고를 계산하지 못했습니다" in item.value for item in app.caption)
    assert any("배치 편집기를 열 수 없습니다" in item.value for item in app.error)
    clear_equipment_repository()


def test_a_new_as_of_that_changes_the_roster_resets_the_editor(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """기준일로 편집 대상이 바뀌면(반출을 마친 호기가 빠진다) epoch 도 바뀌어야 한다. 그대로면
    브라우저가 옛 목록을 쥔 채 「이 편집기에 없는 호기」로 적용 전체가 거부된다. 편집 중에는
    기준일이 고정이지만(페이더는 보기에만) 세션 기준일은 편집 사이사이에 바뀔 수 있다 — 세션 값으로
    바꿔 본다."""
    today = date.today()
    equipment = _equipment()
    equipment.loc[equipment["설비명"].eq("EQ-02"), "정지일정"] = (
        today + timedelta(days=30)
    ).isoformat()
    monkeypatch.setattr(
        "test_space_layout_editor_page._equipment", lambda: equipment.copy(), raising=True
    )
    app, _ = _open_editor(tmp_path)
    app.session_state["space_status_as_of"] = today + timedelta(days=10)
    app.run()
    before = editor_calls[-1]
    app.session_state["space_status_as_of"] = today + timedelta(days=60)
    app.run()
    after = editor_calls[-1]

    assert not app.exception
    assert [item["id"] for item in before["items"]] == ["EQ-01", "EQ-02"]
    assert [item["id"] for item in after["items"]] == ["EQ-01"]
    assert after["epoch"] != before["epoch"]
    clear_equipment_repository()


def test_the_pinned_date_caption_picks_its_particle_by_the_date(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """배치 편집 안내의 「기준일은 편집하는 동안 … 고정입니다」 는 날짜 끝소리로 조사를 고른다
    — 끝자리 0·3·6(영·삼·육)은 「으로」, 그 밖은 「로」. 「2026-10-26 로」 처럼 못박아 두면 그런
    날마다 틀렸다(2026-10-26 E2E)."""
    app, _ = _open_editor(tmp_path)
    today = date.today()
    days = [today + timedelta(days=offset) for offset in range(1, 20)]
    eu = next(day for day in days if day.isoformat()[-1] in "036")
    ro = next(day for day in days if day.isoformat()[-1] in "1245789")

    for day, particle in ((eu, "으로"), (ro, "로")):
        app.session_state["space_status_as_of"] = day
        app.run()

        assert not app.exception, [item.message for item in app.exception]
        caption = next(item.value for item in app.caption if "고정입니다" in item.value)
        assert f"{day.isoformat()}{particle} 고정입니다" in caption, caption
        assert f"{day.isoformat()} 로" not in caption
    clear_equipment_repository()


def test_a_save_error_is_shown_once_even_without_pending_changes(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, _ = _open_editor(tmp_path)
    app.session_state["space_layout_save_error"] = (
        "다른 사용자가 먼저 r2를 저장해 저장하지 않았습니다."
    )
    app.run()
    assert any("배치를 저장하지 못했습니다" in item.value for item in app.error)

    app.run()
    assert not any("배치를 저장하지 못했습니다" in item.value for item in app.error)
    clear_equipment_repository()


def _top_level(app: AppTest) -> list[tuple[str, str]]:
    """본문 맨 윗단의 순서 — (요소 종류, key). Streamlit 은 요소를 key 가 아니라 이 순번으로 갈아
    끼운다. 층 상세 상자(key 없음)는 그 안의 `배치 편집` 토글로 가린다."""
    layout: list[tuple[str, str]] = []
    for node in app.main.children.values():
        block_id = str(getattr(getattr(node, "proto", None), "id", "") or "")
        name = block_id.split("-", 2)[-1] if block_id.startswith("$$ID-") else ""
        if isinstance(node, Block) and any(
            toggle.key == "space_layout_edit_mode" for toggle in node.get("toggle")
        ):
            name = "층 상세"
        layout.append((type(node).__name__, name))
    return layout


def test_the_floor_detail_keeps_its_place_while_the_unsaved_panel_comes_and_goes(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """저장 안 한 배치 상자는 첫 적용에 서고 저장·버리기로 사라진다. 그 자리가 늘 서 있지
    않으면 아래 층 상세의 순번이 밀려 브라우저가 편집기를 새로 마운트한다 — 본문 높이가
    무너져 스크롤이 맨 위로 튀고 서랍·배율을 잃었다(2026-10-08 브라우저 확인). 맨 윗단 순서는
    상자 유무와 상관없이 같아야 한다."""
    app, _ = _open_editor(tmp_path)
    layout = _top_level(app)
    assert ("Block", "space_unsaved_layout_slot") in layout
    assert layout.index(("Block", "space_unsaved_layout_slot")) < layout.index(("Block", "층 상세"))
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)

    def apply_one_move(x: float) -> None:
        app.session_state[FAKE_APPLY_KEY] = {
            "epoch": editor_calls[-1]["epoch"],
            "changes": [{"id": "EQ-01", "placed": True, "x": x, "y": 20, "w": 12, "h": 7}],
            "canvas": None,
            "marks": None,
        }
        app.run()
        assert not app.exception, [item.message for item in app.exception]
        assert any("저장 안 한 배치 변경" in item.value for item in app.markdown)

    apply_one_move(40)
    assert _top_level(app) == layout

    app.button(key="space_layout_save").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    assert _top_level(app) == layout

    apply_one_move(50)
    app.button(key="space_layout_discard").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    assert _top_level(app) == layout
    clear_equipment_repository()


def _count_status_builds(monkeypatch: pytest.MonkeyPatch) -> tuple[list[date], list[int]]:
    """기준일 판정(`build_space_equipment_status_from_prepared`)을 실제로 돌린 기준일과 설비
    마스터 검증(`prepare_equipment_master`)을 돌린 행 수를 센다. 캐시는 비우고 시작한다 — 키가 내용
    지문이라 앞 테스트가 같은 표로 채운 칸이 남는다."""
    from capa_simulation.services import simulation_cache
    from capa_simulation.services.equipment_availability import (
        build_space_equipment_status_from_prepared,
    )
    from capa_simulation.services.equipment_validation import prepare_equipment_master

    builds: list[date] = []
    prepares: list[int] = []

    def counting(
        prepared: pd.DataFrame, prepared_downtime: pd.DataFrame, *, as_of: date
    ) -> pd.DataFrame:
        builds.append(as_of)
        return build_space_equipment_status_from_prepared(prepared, prepared_downtime, as_of=as_of)

    def counting_prepare(equipment: pd.DataFrame) -> pd.DataFrame:
        prepares.append(len(equipment))
        return prepare_equipment_master(equipment)

    monkeypatch.setattr(simulation_cache, "build_space_equipment_status_from_prepared", counting)
    monkeypatch.setattr(simulation_cache, "prepare_equipment_master", counting_prepare)
    simulation_cache._cached_space_equipment_status.clear()
    simulation_cache._cached_prepared_space_inputs.clear()
    return builds, prepares


def test_the_space_status_wrapper_builds_once_per_content_and_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from capa_simulation.services.equipment_availability import build_space_equipment_status
    from capa_simulation.services.simulation_cache import (
        frame_digest,
        get_space_equipment_status,
        space_status_cache_key,
    )

    builds, prepares = _count_status_builds(monkeypatch)
    master, downtime = _equipment(), _downtime()
    as_of = date(2026, 10, 1)
    expected = build_space_equipment_status(master, downtime, as_of=as_of)
    # 키는 입력의 내용 지문과 기준일뿐이다 — 사용기준 규칙 같은 코드 상수는 넣지 않는다(키 방침).
    assert space_status_cache_key(master, downtime, as_of=as_of) == (
        frame_digest(master),
        frame_digest(downtime),
        as_of.isoformat(),
    )

    first = get_space_equipment_status(master, downtime, as_of=as_of)
    pd.testing.assert_frame_equal(first, expected)
    # 받은 쪽이 고쳐 써도 캐시는 그대로다(부를 때마다 새 사본).
    first.loc[:, "상태"] = "고친 값"
    again = get_space_equipment_status(master.copy(), downtime.copy(), as_of=as_of)
    pd.testing.assert_frame_equal(again, expected)
    assert builds == [as_of]

    # 기준일이나 표 내용이 바뀌면 다시 판정한다.
    later = date(2026, 12, 1)
    pd.testing.assert_frame_equal(
        get_space_equipment_status(master, downtime, as_of=later),
        build_space_equipment_status(master, downtime, as_of=later),
    )
    moved = master.copy()
    moved.loc[moved["설비명"].eq("EQ-01"), "X좌표"] = 40.0
    pd.testing.assert_frame_equal(
        get_space_equipment_status(moved, downtime, as_of=as_of),
        build_space_equipment_status(moved, downtime, as_of=as_of),
    )
    assert builds == [as_of, later, as_of]
    # 검증은 기준일과 상관없어 내용마다 한 번이다 — 기준일만 바뀐 회차(페이더)는 검증하지 않는다.
    assert prepares == [len(master), len(moved)]


def test_editing_and_applying_judge_each_table_content_once(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """배치 편집은 한 회차에 저장본(조건 카드·요약)과 편집본(편집기·겹침 경고)을 따로 판정하고,
    적용은 `st.rerun()` 으로 두 회차를 돈다. 같은 내용은 한 번만 판정한다 — 캐시가 없을 때는
    편집을 켜면 2번, 적용 한 번에 5~6번 같은 판정을 했다(2026-10-08 계측)."""
    builds, _ = _count_status_builds(monkeypatch)
    app, _ = _open_editor(tmp_path)
    # 보기 회차에 저장본을 한 번 판정한다. 편집을 켠 회차의 편집본은 저장본과 내용이 같아 다시 쓴다.
    assert len(builds) == 1

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    # 새 편집본 한 번 — 겹침 경고와 편집기가 함께 쓴다.
    assert len(builds) == 2
    app.run()
    assert len(builds) == 2
    clear_equipment_repository()


def test_the_space_boundary_wrapper_keys_on_master_columns_and_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """층 상세의 경계 날짜는 기준일과 상관없다 — 키는 경계 날짜가 읽는 설비 마스터 칸의 내용 지문·
    비가동 일정·오늘이고, 기준일 상태 칸(`상태`·지분 …)만 다른 표는 같은 키다. 결과는
    `unit_boundaries` 그대로이고 받은 쪽이 고쳐 써도 캐시는 그대로다."""
    from capa_simulation.services import simulation_cache
    from capa_simulation.services.equipment_availability import build_space_equipment_status
    from capa_simulation.services.simulation_cache import (
        get_space_unit_boundaries,
        space_boundary_cache_key,
    )
    from capa_simulation.services.space_unit_state import unit_boundaries

    calls: list[str] = []

    def counting(rows: pd.DataFrame, downtime: pd.DataFrame, *, today: date) -> pd.DataFrame:
        calls.append(today.isoformat())
        return unit_boundaries(rows, downtime, today=today)

    monkeypatch.setattr(simulation_cache, "unit_boundaries", counting)
    simulation_cache._cached_space_unit_boundaries.clear()
    master, downtime = _equipment(), _downtime()
    today = date(2026, 10, 1)
    early = build_space_equipment_status(master, downtime, as_of=date(2026, 8, 5))
    late = build_space_equipment_status(master, downtime, as_of=date(2026, 12, 1))
    assert not early["상태"].equals(late["상태"])
    assert space_boundary_cache_key(early, downtime, today=today) == space_boundary_cache_key(
        late, downtime, today=today
    )

    first = get_space_unit_boundaries(early, downtime, today=today)
    pd.testing.assert_frame_equal(first, unit_boundaries(early, downtime, today=today))
    first.loc[:, "보관"] = True
    again = get_space_unit_boundaries(late, downtime, today=today)
    pd.testing.assert_frame_equal(again, unit_boundaries(late, downtime, today=today))
    assert calls == [today.isoformat()]
    # 경계 날짜가 읽는 칸·오늘이 바뀌면 다시 구한다.
    moved = early.copy()
    moved.loc[moved["설비명"].eq("EQ-02"), "반입일정"] = pd.Timestamp("2026-09-01")
    get_space_unit_boundaries(moved, downtime, today=today)
    get_space_unit_boundaries(early, downtime, today=date(2026, 10, 2))
    assert calls == [today.isoformat(), today.isoformat(), "2026-10-02"]


def test_send_to_another_floor_lists_active_floors_and_an_old_send_is_kept_with_a_note(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """「다른 층으로 보내기」 목록은 사용 층(과 지금 층)이다 — 비활성 층은 빠진다. 목록이 줄기 전에
    보낸 적용은 받고(저장 검사 그대로, S5) 적용 flash 끝에 알린다."""
    from capa_simulation.persistence.equipment_cache import clear_floor_state_cache

    database = tmp_path / "space_edit.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_floor_states(
        {("C2", "3F"): "UNUSED", ("C1", "1F"): "NOT_LINE"}, expected_version=0, source="test"
    )
    app, _ = _open_editor(tmp_path)
    data = editor_calls[-1]
    assert not app.exception
    # 지금 층(C1 1F)은 비활성이어도 남는다(편집기가 자기 층은 뺀다). 다른 비활성 층은 빠진다.
    assert "C1 1F" in data["floors"] and "C2 3F" not in data["floors"]
    assert "C2 2F" in data["floors"]
    assert any("이 층은 비활성(생산라인 아님)입니다" in item.value for item in app.info)

    # 그 사이 다른 층이 꺼졌어도 이미 단 `moveTo` 는 받는다 — 적용 검사는 30개 층이다.
    repository.save_floor_states(
        {("C2", "3F"): "UNUSED", ("C1", "1F"): "NOT_LINE", ("C2", "2F"): "UNUSED"},
        expected_version=1,
        source="남",
    )
    clear_floor_state_cache()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [{"id": "EQ-01", "placed": False, "w": 12, "h": 7, "moveTo": "C2 2F"}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    (flash,) = [item.value for item in app.success if "편집본에 적용했습니다" in item.value]
    assert "보낸 층 C2 2F는 비활성 층입니다" in flash
    assert "C2 2F" not in editor_calls[-1]["floors"]
    clear_equipment_repository()
