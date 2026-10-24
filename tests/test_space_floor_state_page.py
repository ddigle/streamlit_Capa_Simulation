# Purpose: Space 층 목록의 사용 칸·비활성 층 접힘·사용 편집(동 머리·확인·충돌·샘플 잠금)을 검사한다.

"""Space FAB 전체의 층 목록 표와 `사용 편집`(2026-10-24 사용자 결정 S1~S6).

`AppTest.run()` 은 편집표 상태를 보내지 않는다 — 칸 편집은 `widget_browser.BrowserTables` 로
브라우저처럼 보낸다. 도면 편집기(JS)는 대역이다(`_EDITOR`). 저장은 tmp 설비 DB 에 실제로 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import get_widget_state
from test_equipment_availability import _baseline, _downtime
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import _master
from widget_browser import BrowserTables

from capa_simulation.components import space_layout_editor
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.space_floor_list import (
    BASE_KEY,
    CANCEL_BUTTON_KEY,
    CONFIRM_BUTTON_KEY,
    CONFIRM_KEY,
    DRAFT_KEY,
    EDIT_TOGGLE_KEY,
    EDITOR_KEY,
    FLOOR_TABLE_KEY,
    GENERATION_KEY,
    INACTIVE_TABLE_KEY,
    REVERT_BUTTON_KEY,
    SAVE_BUTTON_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import FLOOR_KEYS

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
JUMP_FAB_KEY = "space_status_floor_jump_fab"


@pytest.fixture(autouse=True)
def _stub_editor(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs["data"])
        return SimpleNamespace(apply=None, navigate=None, pick=None, asOf=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _fleet() -> pd.DataFrame:
    """C1 1F — EQ-01·EQ-02 와 Main 설비 MOD-1 모듈 넷(설비 3대). 다른 층은 비었다."""
    module = {"Main 설비": "MOD-1", "Xsize": 6, "Ysize": 4}
    return _master(
        {**module, "설비명": "MOD-1A", "X좌표": 60.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1B", "X좌표": 66.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1C", "X좌표": 60.0, "Y좌표": 14.0},
        {**module, "설비명": "MOD-1D", "X좌표": 66.0, "Y좌표": 14.0},
    )


def _database(tmp_path: Path, inactive: dict[tuple[str, str], str] | None = None) -> Path:
    database = tmp_path / "space_floor_state.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _fleet(), _downtime(), note="r1")
    if inactive:
        repository.save_floor_states(inactive, expected_version=0, source="test")
    clear_equipment_repository()
    return database


def _app(database: Path, *, sample: bool = False, **query: str) -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=90)
    app.session_state[SAMPLE_TOGGLE_KEY] = sample
    for name, value in query.items():
        app.query_params[name] = value
    return app


def _states(database: Path) -> dict[tuple[str, str], str]:
    return DuckDBEquipmentRepository(database).load_floor_states().inactive


def _version(database: Path) -> int:
    return DuckDBEquipmentRepository(database).load_floor_states().version


def _position(building: str, floor: str) -> int:
    return FLOOR_KEYS.index((building, floor))


def _editor_key(app: AppTest) -> str:
    generation = int(app.session_state[f"{EDITOR_KEY}__generation"])
    return EDITOR_KEY if not generation else f"{EDITOR_KEY}__g{generation}"


def _floor_tables(app: AppTest) -> list[pd.DataFrame]:
    return [table.value for table in app.dataframe if "미배치대수" in table.value.columns]


def _ok(app: AppTest) -> None:
    assert not app.exception, [item.message for item in app.exception]


def _start_editing(database: Path) -> tuple[AppTest, BrowserTables]:
    app = _app(database)
    tables = BrowserTables(app)
    tables.run()
    _ok(app)
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    tables.run()
    _ok(app)
    return app, tables


def _press(app: AppTest, tables: BrowserTables, key: str) -> None:
    app.button(key=key).click()
    tables.run()
    _ok(app)


def test_every_floor_is_in_use_by_default(tmp_path: Path) -> None:
    app = _app(_database(tmp_path)).run()
    _ok(app)

    (table,) = _floor_tables(app)
    assert len(table) == len(FLOOR_KEYS)
    assert list(table.columns[:3]) == ["동", "층", "사용"]
    assert table["사용"].all()
    assert not [expander for expander in app.expander if "비활성 층" in expander.label]
    assert len(app.selectbox(key=JUMP_FAB_KEY).options) == len(FLOOR_KEYS)
    assert not app.toggle(key=EDIT_TOGGLE_KEY).value
    assert not app.toggle(key=EDIT_TOGGLE_KEY).disabled
    clear_equipment_repository()


def test_turning_one_floor_off_saves_it_and_moves_it_to_the_folded_table(tmp_path: Path) -> None:
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "3F"), "사용", False)
    tables.run()
    _ok(app)
    # 사유를 비운 채 끈 칸은 「사용 안 함」 으로 채운다(D16).
    assert app.session_state[DRAFT_KEY] == {"C1 3F": "UNUSED"}
    assert any("바뀐 층 1개" in caption.value for caption in app.caption)

    _press(app, tables, SAVE_BUTTON_KEY)

    assert _states(database) == {("C1", "3F"): "UNUSED"}
    assert any("비활성 1개(사용 안 함 1)" in item.value for item in app.success)
    assert not app.toggle(key=EDIT_TOGGLE_KEY).value
    assert DRAFT_KEY not in app.session_state and BASE_KEY not in app.session_state
    active, inactive = _floor_tables(app)
    assert len(active) == len(FLOOR_KEYS) - 1 and ("C1", "3F") not in set(
        zip(active["동"], active["층"], strict=True)
    )
    assert inactive[["동", "층", "사용", "사유"]].values.tolist() == [
        ["C1", "3F", False, "사용 안 함"]
    ]
    assert [expander.label for expander in app.expander if "비활성 층" in expander.label] == [
        "비활성 층 1개"
    ]
    assert "C1 3F" not in app.selectbox(key=JUMP_FAB_KEY).options
    assert len(app.selectbox(key=JUMP_FAB_KEY).options) == len(FLOOR_KEYS) - 1
    clear_equipment_repository()


def test_a_building_head_turns_its_six_floors_off_at_once(tmp_path: Path) -> None:
    database = _database(tmp_path)
    app, tables = _start_editing(database)

    app.segmented_control(key="space_floor_state_bulk_C5").set_value("NOT_LINE")
    tables.run()
    _ok(app)
    assert {label: code for label, code in app.session_state[DRAFT_KEY].items()} == {
        f"C5 {floor}": "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")
    }
    editor = next(table for table in app.dataframe if "호기" in table.value.columns).value
    c5 = editor.loc[editor["동"].eq("C5")]
    assert not c5["사용"].any() and c5["사유"].eq("생산라인 아님(사무·창고 등)").all()

    _press(app, tables, SAVE_BUTTON_KEY)

    assert _states(database) == {
        ("C5", floor): "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")
    }
    clear_equipment_repository()


def test_a_cell_edit_turns_the_building_head_to_mixed_on_the_next_run(tmp_path: Path) -> None:
    """세대를 올리지 않는 칸 편집 뒤에도 동 머리가 맞는다 — 회차마다 세션에 적는다(검토 고침 10)."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    head = app.segmented_control(key="space_floor_state_bulk_C2")
    assert head.value == "ACTIVE" and head.label == "C2"

    tables.edit(_editor_key(app), _position("C2", "3F"), "사유", "생산라인 아님(사무·창고 등)")
    tables.run()
    _ok(app)

    head = app.segmented_control(key="space_floor_state_bulk_C2")
    assert head.value is None
    assert head.label == "C2 · 사용 5/6"
    # 사용 층의 사유를 고른 뜻은 끄기다.
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "NOT_LINE"}
    clear_equipment_repository()


def test_turning_off_a_floor_with_units_asks_first(tmp_path: Path) -> None:
    """C1 1F 에는 단일 둘 + 모듈 묶음 넷 = 설비 3대. 막지 않고 확인한다(S4)."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "1F"), "사용", False)
    tables.run()
    editor = next(table for table in app.dataframe if "호기" in table.value.columns).value
    assert editor["호기"].tolist()[_position("C1", "1F")] == 3

    _press(app, tables, SAVE_BUTTON_KEY)
    assert _version(database) == 0
    assert any("호기 3대" in item.value for item in app.warning)
    assert any("설비 마스터의 동·층 값은 바뀌지 않습니다" in item.value for item in app.caption)

    _press(app, tables, CANCEL_BUTTON_KEY)
    assert not any("호기 3대" in item.value for item in app.warning)
    assert _version(database) == 0

    _press(app, tables, SAVE_BUTTON_KEY)
    assert any("호기 3대" in item.value for item in app.warning)
    _press(app, tables, CONFIRM_BUTTON_KEY)

    assert _states(database) == {("C1", "1F"): "UNUSED"}
    assert CONFIRM_KEY not in app.session_state
    assert any("층 사용 설정을 저장했습니다" in item.value for item in app.success)
    # 설비 마스터의 동·층은 그대로다.
    master = DuckDBEquipmentRepository(database).load_official_snapshot()
    assert master is not None
    assert master.equipment.loc[master.equipment["설비명"].eq("EQ-01"), "층"].tolist() == ["1F"]
    clear_equipment_repository()


def test_changing_only_the_reason_does_not_ask(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED"})
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "1F"), "사유", "생산라인 아님(사무·창고 등)")
    tables.run()

    _press(app, tables, SAVE_BUTTON_KEY)

    assert not any("호기" in item.value for item in app.warning)
    assert _states(database) == {("C1", "1F"): "NOT_LINE"}
    assert _version(database) == 2
    clear_equipment_repository()


def test_a_save_after_someone_else_saved_is_refused_and_the_draft_is_rebuilt(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    DuckDBEquipmentRepository(database).save_floor_states(
        {("C4", "6F"): "NOT_LINE"}, expected_version=0, source="남"
    )
    tables.edit(_editor_key(app), _position("C2", "2F"), "사용", False)
    tables.run()

    _press(app, tables, SAVE_BUTTON_KEY)

    assert _states(database) == {("C4", "6F"): "NOT_LINE"}
    assert not app.success
    assert any("다른 사용자가 먼저 층 사용 설정을 저장해" in item.value for item in app.warning)
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    assert app.session_state[DRAFT_KEY] == {"C4 6F": "NOT_LINE"}
    assert app.session_state[BASE_KEY][0] == 1

    # 다시 고치면 최신 위에 저장된다.
    tables.edit(_editor_key(app), _position("C2", "2F"), "사용", False)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)
    assert _states(database) == {("C2", "2F"): "UNUSED", ("C4", "6F"): "NOT_LINE"}
    clear_equipment_repository()


def test_saving_without_changes_says_so_and_writes_nothing(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C3", "2F"): "UNUSED"})
    app, tables = _start_editing(database)

    _press(app, tables, SAVE_BUTTON_KEY)

    assert any("바뀐 층이 없습니다" in item.value for item in app.info)
    assert not app.success
    assert _version(database) == 1
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    clear_equipment_repository()


def test_revert_brings_back_the_saved_states(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C3", "2F"): "UNUSED"})
    app, tables = _start_editing(database)
    app.segmented_control(key="space_floor_state_bulk_C3").set_value("NOT_LINE")
    tables.run()
    assert len(app.session_state[DRAFT_KEY]) == 6

    _press(app, tables, REVERT_BUTTON_KEY)

    assert app.session_state[DRAFT_KEY] == {"C3 2F": "UNUSED"}
    assert app.segmented_control(key="space_floor_state_bulk_C3").value is None
    clear_equipment_repository()


def test_opening_a_floor_while_editing_drops_the_draft(tmp_path: Path) -> None:
    """토글은 FAB 화면을 그리지 않는 회차에 위젯 상태가 버려진다 — 돌아오면 꺼져 있고 초안도 없다
    (테마 전환 표지가 거짓 「저장 안 함」 을 말하지 않는다)."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C2", "2F"), "사용", False)
    tables.run()
    assert app.session_state[DRAFT_KEY] == {"C2 2F": "UNUSED"}

    app.selectbox(key=JUMP_FAB_KEY).set_value("C2 1F")
    tables.run()
    _ok(app)
    app.button(key="space_status_fab_breadcrumb").click()
    tables.run()
    _ok(app)

    assert not app.toggle(key=EDIT_TOGGLE_KEY).value
    assert DRAFT_KEY not in app.session_state and BASE_KEY not in app.session_state
    assert _version(database) == 0
    clear_equipment_repository()


def test_the_sample_fleet_locks_the_switch_and_turns_it_off(tmp_path: Path) -> None:
    database = tmp_path / "empty.duckdb"
    app = _app(database, sample=True)
    app.session_state[EDIT_TOGGLE_KEY] = True
    app.run()
    _ok(app)

    toggle = app.toggle(key=EDIT_TOGGLE_KEY)
    assert toggle.disabled and not toggle.value
    assert not any("호기" in table.value.columns for table in app.dataframe)
    clear_equipment_repository()


def test_a_press_drawn_in_an_older_generation_does_nothing(tmp_path: Path) -> None:
    """빠른 두 번 누름 — 그린 회차의 세대가 지금과 다르면 쓰지도 알리지도 않는다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C2", "2F"), "사용", False)
    tables.run()
    app.session_state[GENERATION_KEY] = int(app.session_state[GENERATION_KEY]) + 5

    _press(app, tables, SAVE_BUTTON_KEY)

    assert _version(database) == 0
    assert not app.success and not app.info
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    clear_equipment_repository()


def _select_row(app: AppTest, table_key: str, row: int) -> None:
    """`st.dataframe(on_select=…)` 의 행 고르기를 브라우저처럼 보낸다(다른 위젯은 AppTest
    그대로)."""
    states = WidgetStates()
    for node in app._tree:
        proto_id = getattr(getattr(node, "proto", None), "id", "")
        if isinstance(proto_id, str) and proto_id.endswith(f"-{table_key}"):
            state = states.widgets.add()
            state.id = proto_id
            state.string_value = json.dumps(
                {"selection": {"rows": [row], "columns": [], "cells": []}}
            )
            continue
        other = get_widget_state(node)
        if other is not None:
            states.widgets.append(other)
    app._run(states)


def test_a_row_of_the_inactive_table_opens_that_floor_with_a_banner(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED", ("C2", "1F"): "NOT_LINE"})
    app = _app(database).run()
    _ok(app)

    _select_row(app, INACTIVE_TABLE_KEY, 0)
    _ok(app)

    assert app.session_state["space_status_selected_building"] == "C1"
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert app.query_params["floor"] == ["C1-1F"]
    assert any("이 층은 비활성(사용 안 함)입니다" in item.value for item in app.info)
    jump = app.selectbox(key="space_status_floor_jump_C1-1F")
    assert jump.value == "C1 1F"
    assert "C1 1F" in jump.options and "C2 1F" not in jump.options
    clear_equipment_repository()


def test_the_active_table_still_opens_its_floor(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED"})
    app = _app(database).run()
    (active, _inactive) = _floor_tables(app)
    first = (str(active.iloc[0]["동"]), str(active.iloc[0]["층"]))

    _select_row(app, FLOOR_TABLE_KEY, 0)
    _ok(app)

    assert (
        app.session_state["space_status_selected_building"],
        app.session_state["space_status_selected_floor"],
    ) == first
    assert not any("이 층은 비활성" in item.value for item in app.info)
    clear_equipment_repository()


def test_the_address_of_an_inactive_floor_opens_it_with_the_banner(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "3F"): "UNUSED", ("C2", "1F"): "NOT_LINE"})
    app = _app(database, floor="C1-3F").run()
    _ok(app)

    assert app.session_state["space_status_selected_floor"] == "3F"
    assert any("이 층은 비활성(사용 안 함)입니다" in item.value for item in app.info)
    jump = app.selectbox(key="space_status_floor_jump_C1-3F")
    assert jump.value == "C1 3F"
    assert "C1 3F" in jump.options and "C2 1F" not in jump.options
    clear_equipment_repository()


def test_the_fab_summary_tells_how_many_units_sit_on_inactive_floors(
    tmp_path: Path, _stub_editor: list[dict[str, Any]]
) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED"})
    app = _app(database).run()
    _ok(app)

    fab = [data for data in _stub_editor if data.get("scope") == "fab"][-1]
    assert str(fab["summary"]).endswith(" · 비활성 층 3대")
    assert fab["linkStats"]["C1 1F"]["inactive"] == "사용 안 함"
    clear_equipment_repository()
