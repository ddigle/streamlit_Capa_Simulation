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
from alert_marks import active_state, data_error_marks, data_error_texts, place_errors, successes
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import _master

from capa_simulation.components import space_layout_editor, write_guard
from capa_simulation.components.equipment_data_workspace import BUFFER_GENERATION_KEY
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


def _two_process_fleet() -> pd.DataFrame:
    """C1 1F 는 Process-A 둘, C2 2F 는 Process-B 하나 — 공정 필터로 층 하나가 빈다."""
    fleet = _equipment()
    fleet.loc[1, ["공정소분류", "동", "층"]] = ["Process-B", "C2", "2F"]
    return fleet


def test_the_summary_says_a_process_filter_is_on_and_when_it_emptied_the_floor(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """필터로 층이 비면 빈 층과 같은 모습이었다 — 건 조건이 보이게 요약 끝에 표지를 잇는다
    (설계 규칙 UI-STA-03, 사외 점검 g6-02). 뜻은 공정소분류 칸 풍선이다."""
    app, _ = _open_editor(tmp_path, _two_process_fleet())
    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    assert "공정 필터" not in str(editor_calls[-1]["summary"])
    assert "「필터로 0대」" in str(app.multiselect(key="space_status_process_filter").help)

    # 이 층 호기가 남는 필터 — 건 수만 말한다.
    app.multiselect(key="space_status_process_filter").set_value(["Process-A"]).run()
    assert not app.exception, [item.message for item in app.exception]
    assert str(editor_calls[-1]["summary"]).endswith(" · 공정 필터 1개")

    # 이 층 호기가 모두 빠지는 필터 — 왜 비었는지 말한다.
    app.multiselect(key="space_status_process_filter").set_value(["Process-B"]).run()
    assert not app.exception, [item.message for item in app.exception]
    summary = str(editor_calls[-1]["summary"])
    assert summary.startswith("배치 0대 · 미배치 0대")
    assert summary.endswith(" · 공정 필터 1개 · 필터로 0대")

    # FAB 요약도 건 수를 말한다.
    app.button(key="space_status_fab_breadcrumb").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert str(editor_calls[-1]["summary"]).endswith(" · 공정 필터 1개")
    clear_equipment_repository()


def test_a_floor_with_nothing_on_it_is_not_blamed_on_the_filter(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """원래 빈 층은 필터를 걸어도 「필터로 0대」 라 하지 않는다 — 필터 때문이 아니다."""
    app, _ = _open_editor(tmp_path, _two_process_fleet())
    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    app.multiselect(key="space_status_process_filter").set_value(["Process-B"]).run()
    app.session_state["space_status_selected_building"] = "C3"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert str(editor_calls[-1]["summary"]).endswith(" · 공정 필터 1개")
    clear_equipment_repository()


def test_the_discard_button_says_what_goes_with_it(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """팝오버에 설명 문장을 세우지 않는다 — 다른 탭 편집까지 버려진다는 말은 누르기 전에 보이는
    단추 풍선이다(설계 규칙 UI-NTF-09, 사외 점검 g6-16)."""
    app, _ = _open_editor(tmp_path)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    told = str(app.button(key="space_layout_discard").help)
    assert "가용설비 설비 마스터 탭의 저장 안 한 편집과 FAB 전체 배치도 함께 버려집니다" in told
    assert not any("함께 버려집니다" in str(item.value) for item in app.caption)
    clear_equipment_repository()


def test_overlaps_in_a_pending_layout_go_to_a_state_alert_not_the_box(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """겹침은 조건이 남아 있는 동안의 상태다 — 저장 상자에 줄로 세우지 않고 건수 · 층과 Alarm 딸린
    표로 낸다(설계 규칙 UI-NTF-02, 사외 점검 g6-04). 저장은 경고 없이 같은 동작이다(UI-NTF-09)."""
    app, _ = _open_editor(tmp_path)
    assert active_state(app, "EQ-17") is None

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 34, "y": 15, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    note = active_state(app, "EQ-17")
    assert note is not None
    assert note["short"] == "겹친 호기 1건(C1 1F) — 목록: Alarm › 이 줄"
    assert note["full"].startswith("Space 저장 안 한 배치 · 겹친 호기 1건(C1 1F)")
    assert "저장은 막지 않습니다" in note["full"]
    (table,) = note["tables"]
    assert table["columns"] == ["종류", "층", "호기", "상대"]
    assert table["rows"] == [["겹친 호기", "C1 1F", "EQ-01", "EQ-02"]]
    assert not any("겹친 호기" in str(item.value) for item in app.caption)

    # 저장은 늘 같은 동작이다 — 저장한 뒤에는 저장 안 한 배치가 없어 조건도 해소된다.
    app.button(key="space_layout_save").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert active_state(app, "EQ-17") is None
    clear_equipment_repository()


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
    assert any("편집본에 적용했습니다" in item.value for item in successes(app))
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
    assert any("r2" in item.value for item in successes(app))
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
    assert any("새 리비전 없이" in item.value for item in successes(app))
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
    assert not place_errors(app), [item.value for item in app.error]
    assert any("편집본에 적용했습니다" in item.value for item in successes(app))
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
    assert not place_errors(app), [item.value for item in app.error]
    assert any("Main 설비명 위치 1개 층" in item.value for item in app.markdown)
    assert editor_calls[-1]["groupLabels"] == {"GRP-1": "center"}
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_floor_group_labels("C1", "1F") == {}

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    # 알림은 실제로 저장한 것만 말한다(위치만 바꿨으면 「Main 설비명 위치만」).
    assert any(
        "새 리비전 없이 Main 설비명 위치만 저장했습니다" in item.value for item in successes(app)
    ), [item.value for item in successes(app)]
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
    assert not place_errors(app), [item.value for item in app.error]
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
    assert not place_errors(app), [item.value for item in app.error]


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


def test_a_second_press_of_the_same_apply_keeps_the_success_and_applies_once(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """「적용」 을 사람 속도(0.45~0.6초)로 두 번 누르면 둘째 누름이 브라우저가 새 epoch 를 받기 전의
    같은 적용을 보낸다 — 「다시 서는 사이에 누른 적용이라 반영하지 않았습니다」 경고만 남고 첫
    적용의 성공 알림은 사라졌는데 자리는 적용됐다(2026-10-27 E2E). 같은 입력의 옛 epoch 제출은
    경고하지 않고 첫 성공 알림이 남는다. 입력이 다른 옛 epoch 제출은 전처럼 경고한다."""
    # 시험 회차는 브라우저보다 느리다 — 창(1초)을 넓혀 두 누름 사이 회차 시간을 맞춘다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 30.0)
    app, _ = _open_editor(tmp_path)
    epoch = editor_calls[-1]["epoch"]
    payload = {
        "epoch": epoch,
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.session_state[FAKE_APPLY_KEY] = dict(payload)
    app.run()
    assert any("편집본에 적용했습니다" in item.value for item in successes(app))
    generation = app.session_state[BUFFER_GENERATION_KEY]

    app.session_state[FAKE_APPLY_KEY] = dict(payload)
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not any("다시 서는 사이" in item.value for item in app.warning)
    assert any("편집본에 적용했습니다" in item.value for item in successes(app))
    # 둘째 누름은 얹지 않았다 — 편집본 세대가 그대로다.
    assert app.session_state[BUFFER_GENERATION_KEY] == generation
    moved = next(item for item in editor_calls[-1]["items"] if item["id"] == "EQ-01")
    assert (moved["x"], moved["y"]) == (40.0, 20.0)

    app.session_state[FAKE_APPLY_KEY] = {
        **payload,
        "changes": [{"id": "EQ-01", "placed": True, "x": 50, "y": 20, "w": 12, "h": 7}],
    }
    app.run()
    assert any("다시 서는 사이" in item.value for item in app.warning)
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
    next(widget for widget in app.number_input if widget.label == "캔버스 폭").set_value(100).run()

    assert not app.exception
    # 기둥(오른쪽 122)이 밖으로 나간다 — 잠긴 단추의 짧은 풍선과 알림창이 말한다.
    assert not app.warning
    note = active_state(app, "EQ-16")
    assert note is not None and "도면 요소가 범위를 벗어나" in note["full"]
    save = app.button(key="space_floor_layout_save_C1_1F")
    assert save.disabled and "필요한 크기 122" in str(save.help)
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
    # 고칠 입력이 다른 탭이라 자리에는 마크만, 글은 알림이다(설계 규칙 UI-NTF-08).
    assert not app.error
    assert not any("겹침 경고를 계산하지 못했습니다" in item.value for item in app.caption)
    texts = data_error_texts(app)
    assert any("겹침 경고를 계산하지 못했습니다" in text for text in texts)
    assert any("배치 편집기를 열 수 없습니다" in text for text in texts)
    assert data_error_marks(app) == 2
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


def test_the_pinned_date_rides_the_editor_toolbar_not_a_caption_above_it(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """배치 편집 위 두 줄 캡션(「끌어 놓아 …」·「기준일은 편집하는 동안 … 고정입니다」)은
    걷었다(2026-11-03 사용자 요청 — 도면을 올린다). 고정 기준일은 편집기 도구 줄 칩이 data 의 `asOf`
    로 말하고, 안내는 도구 줄 「단축키」 · Guide 다 — 본문에는 날짜 글자를 싣지 않아
    조사(「으로」·「로」, 2026-10-26 E2E)를 고를 자리가 없다."""
    app, _ = _open_editor(tmp_path)
    later = date.today() + timedelta(days=3)
    app.session_state["space_status_as_of"] = later
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    editor = editor_calls[-1]
    assert editor.get("mode") is None and editor["asOf"] == later.isoformat()
    assert not any("고정입니다" in str(item.value) for item in app.caption)
    assert not any("끌어 놓아 자리·크기를 고치고" in str(item.value) for item in app.caption)
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
    끼운다. 층 도면 칸은 늘 서는 `space_floor_stage` 다(`배치 편집` 토글은 사이드바 「Space 도면」
    상자)."""
    layout: list[tuple[str, str]] = []
    for node in app.main.children.values():
        block_id = str(getattr(getattr(node, "proto", None), "id", "") or "")
        name = block_id.split("-", 2)[-1] if block_id.startswith("$$ID-") else ""
        if name.endswith("space_floor_stage"):
            name = "층 상세"
        layout.append((type(node).__name__, name))
    return layout


def _save_row(app: AppTest) -> dict[str, bool]:
    """저장 상자 머리 줄의 단추 잠김 — 없으면 빈 칸이다."""
    save = [item for item in app.button if item.key == "space_layout_save"]
    return {"save_locked": bool(save[0].disabled)} if save else {}


def test_the_save_row_stands_while_editing_so_the_first_apply_does_not_push_the_drawing(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """첫 「적용」 에 저장 상자가 도면 위에 생겨 편집기가 220px 내려갔다(설계 규칙 UI-PRF-03, 사외
    점검 g6-03). 배치 편집 중에는 머리 줄이 늘 서고(변경이 없으면 잠긴 단추와 까닭 풍선 —
    UI-INP-07), 메모 · 바뀐 호기는 그 줄 안 「변경 내용」 팝오버다. 보기 회차에는 서지 않는다."""
    app, _ = _open_editor(tmp_path)

    assert _save_row(app) == {"save_locked": True}
    assert "적용한 변경이 없습니다" in str(app.button(key="space_layout_save").help)
    assert any(item.value == ":material/edit_note: 저장할 변경 없음" for item in app.caption)
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    idle = _popover_labels(app)
    assert idle == {"변경 내용": True, "버리기": True}
    assert not [item for item in app.text_input if item.label == "변경 메모"]

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert _save_row(app) == {"save_locked": False}
    assert _popover_labels(app) == {"변경 내용": False, "버리기": False}
    # 메모 · 저장자 칸과 바뀐 호기 표는 머리 줄 팝오버 안이다.
    inside = _popover_widgets(app, "변경 내용")
    assert {"변경 메모", "저장자(선택)"} <= inside
    assert any("바뀐 호기 1건" in item.label for item in app.expander)

    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]
    # 편집을 꺼도 저장할 변경은 남아 상자가 그대로 선다.
    assert _save_row(app) == {"save_locked": False}

    app.button(key="space_layout_discard").click().run()
    assert not app.exception, [item.message for item in app.exception]
    # 저장할 변경도 편집도 없는 보기 회차에는 줄이 없다.
    assert _save_row(app) == {}
    clear_equipment_repository()


def _popover_nodes(app: AppTest) -> list[Any]:
    found: list[Any] = []

    def walk(node: Any) -> None:
        proto = getattr(node, "proto", None)
        if isinstance(proto, BlockProto) and proto.HasField("popover"):
            found.append(node)
        for child in getattr(node, "children", {}).values():
            walk(child)

    walk(app.main)
    return found


def _popover_labels(app: AppTest) -> dict[str, bool]:
    """본문 팝오버 라벨 → 잠김."""
    return {node.proto.popover.label: node.proto.popover.disabled for node in _popover_nodes(app)}


def _popover_widgets(app: AppTest, label: str) -> set[str]:
    """그 팝오버 안 글 칸 라벨."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if getattr(node, "type", "") == "text_input":
            found.add(node.label)
        for child in getattr(node, "children", {}).values():
            walk(child)

    for node in _popover_nodes(app):
        if node.proto.popover.label == label:
            walk(node)
    return found


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
    assert any(
        item.value == ":material/block: **비활성 층** · 생산라인 아님" for item in app.main.caption
    )

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
    (flash,) = [item.value for item in successes(app) if "편집본에 적용했습니다" in item.value]
    assert "보낸 층 C2 2F는 비활성 층입니다" in flash
    assert "C2 2F" not in editor_calls[-1]["floors"]
    clear_equipment_repository()
