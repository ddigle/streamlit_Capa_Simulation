# Purpose: Space 층 상세의 배치 편집기가 편집본·대기분에 적용하고 한 번에 저장하는 흐름을 검사한다.

"""브라우저 편집기(JS)는 AppTest 가 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어
두고, 세션에 넣어 둔 적용값을 돌려준다 — 그 뒤의 검증·반영·저장은 실제 코드가 돈다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

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


def _open_editor(tmp_path: Path) -> tuple[AppTest, Path]:
    database = tmp_path / "space_edit.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
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
    panel = app.get("markdown")
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
    assert saved.equipment.set_index("호기").loc["EQ-01", "X좌표"] == 40.0
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["D1"]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.get("markdown"))
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
    assert not any("저장 안 한 배치 변경" in item.value for item in app.get("markdown"))
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
    broken.loc[broken["호기"].eq("EQ-01"), "X좌표"] = 40.0
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
    브라우저가 옛 목록을 쥔 채 「이 편집기에 없는 호기」로 적용 전체가 거부된다."""
    equipment = _equipment()
    equipment.loc[equipment["호기"].eq("EQ-02"), "반출일정"] = "2026-11-15"
    monkeypatch.setattr(
        "test_space_layout_editor_page._equipment", lambda: equipment.copy(), raising=True
    )
    app, _ = _open_editor(tmp_path)
    app.sidebar.date_input(key="space_status_as_of").set_value(date(2026, 10, 1)).run()
    before = editor_calls[-1]
    app.sidebar.date_input(key="space_status_as_of").set_value(date(2026, 12, 1)).run()
    after = editor_calls[-1]

    assert not app.exception
    assert [item["id"] for item in before["items"]] == ["EQ-01", "EQ-02"]
    assert [item["id"] for item in after["items"]] == ["EQ-01"]
    assert after["epoch"] != before["epoch"]
    clear_equipment_repository()


def test_a_save_error_is_shown_once_even_without_pending_changes(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, _ = _open_editor(tmp_path)
    app.session_state["space_layout_save_error"] = (
        "다른 사용자가 먼저 r2을 저장해 저장하지 않았습니다."
    )
    app.run()
    assert any("배치를 저장하지 못했습니다" in item.value for item in app.error)

    app.run()
    assert not any("배치를 저장하지 못했습니다" in item.value for item in app.error)
    clear_equipment_repository()
