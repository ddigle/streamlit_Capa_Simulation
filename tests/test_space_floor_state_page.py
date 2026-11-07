# Purpose: Space 층 목록의 사용 칸·비활성 층 접힘·사용 편집(사유 글·동 머리·확인·잠금)을 검사한다.

"""Space FAB 전체의 층 목록 표와 `사용 편집`(2026-10-24 사용자 결정 S1~S6).

`AppTest.run()` 은 편집표 상태를 보내지 않는다 — 칸 편집은 `widget_browser.BrowserTables` 로
브라우저처럼 보낸다. 도면 편집기(JS)는 대역이다(`_EDITOR`). 저장은 tmp 설비 DB 에 실제로 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pandas as pd
import pytest
from alert_marks import infos, successes
from source_sites import ends_as_sentence
from streamlit.proto.GapSize_pb2 import GapSize
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block, Dataframe, get_widget_state
from test_equipment_availability import _baseline, _downtime
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import _master
from widget_browser import BrowserTables

from capa_simulation.components import space_floor_list, space_layout_editor, write_guard
from capa_simulation.components.literal_markdown import literal_markdown, quoted
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
from capa_simulation.components.table_toolbar import TABLE_TOOLBAR_CLEARANCE
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
    assert any("비활성 1개(사용 안 함 1)" in item.value for item in successes(app))
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
    # 옛 코드는 그 글로 보인다(직접 적는 칸 — 2026-10-26 결정).
    assert not c5["사용"].any() and c5["사유"].eq("생산라인 아님").all()

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

    tables.edit(_editor_key(app), _position("C2", "3F"), "사유", "생산라인 아님")
    tables.run()
    _ok(app)

    head = app.segmented_control(key="space_floor_state_bulk_C2")
    assert head.value is None
    assert head.label == "C2 · 사용 5/6"
    # 사용 층에 사유를 적은 뜻은 끄기다. 옛 코드의 글을 그대로 적으면 그 코드다.
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "NOT_LINE"}
    clear_equipment_repository()


def test_cell_edits_keep_the_same_editor_widget_so_the_view_stays_put(tmp_path: Path) -> None:
    """끄기·켜기·사용 층의 사유 고르기는 편집표를 새 위젯으로 세우지 않는다 — 보던 스크롤·초점이
    남는다(리뷰 결함 1). 위젯 id 가 바뀌면 `BrowserTables` 가 든 편집도 사라진다(브라우저와
    같다)."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    key = _editor_key(app)
    widget = tables.widget_id(key)
    last = _position("C5", "6F")

    # 모든 층이 사용인 데서 맨 아래 줄을 끈다 — `사유` 칸이 처음 찬다(모두 비었던 칸).
    tables.edit(key, last, "사용", False)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C5 6F": "UNUSED"}
    assert _editor_key(app) == key and tables.widget_id(key) == widget
    editor = next(table for table in app.dataframe if "호기" in table.value.columns).value
    assert editor["사유"].tolist()[last] == "사용 안 함"

    # 사용 층에 사유를 적으면 그 사유로 끈다 — 이것도 같은 위젯. 앞뒤 공백은 뗀다.
    tables.edit(key, _position("C2", "3F"), "사유", " 생산라인 아님(사무·창고 등) ")
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {
        "C2 3F": "생산라인 아님(사무·창고 등)",
        "C5 6F": "UNUSED",
    }
    assert _editor_key(app) == key and tables.widget_id(key) == widget

    # 다시 켠다 — 같은 위젯이고 남은 편집을 다시 접어도 같다.
    tables.edit(key, last, "사용", True)
    tables.run()
    _ok(app)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "생산라인 아님(사무·창고 등)"}
    assert _editor_key(app) == key and tables.widget_id(key) == widget
    assert any("바뀐 층 1개" in caption.value for caption in app.caption)

    # 비활성 층의 사유를 지우면 보이는 칸(빈 사유)이 접은 값(사용 안 함)과 달라 그때만 다시 세운다.
    tables.edit(key, _position("C2", "3F"), "사유", None)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "UNUSED"}
    assert _editor_key(app) != key
    clear_equipment_repository()


def _asked(app: AppTest) -> list[str]:
    """끄기 확인 칸의 값 줄."""
    return [item.value for item in app.caption if item.value.startswith("호기 남은 층 ")]


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
    assert _asked(app) == ["호기 남은 층 C1 1F · 공식 배치 호기 3대"]

    _press(app, tables, CANCEL_BUTTON_KEY)
    assert not _asked(app)
    assert _version(database) == 0

    _press(app, tables, SAVE_BUTTON_KEY)
    assert _asked(app) == ["호기 남은 층 C1 1F · 공식 배치 호기 3대"]
    _press(app, tables, CONFIRM_BUTTON_KEY)

    assert _states(database) == {("C1", "1F"): "UNUSED"}
    assert CONFIRM_KEY not in app.session_state
    assert any("층 사용 설정을 저장했습니다" in item.value for item in successes(app))
    # 설비 마스터의 동·층은 그대로다.
    master = DuckDBEquipmentRepository(database).load_official_snapshot()
    assert master is not None
    assert master.equipment.loc[master.equipment["설비명"].eq("EQ-01"), "층"].tolist() == ["1F"]
    clear_equipment_repository()


def test_the_off_confirm_stands_a_value_line_and_keeps_its_words_in_the_button_balloon(
    tmp_path: Path,
) -> None:
    """확인 칸은 값 줄과 단추뿐이고 경고 상자 · 설명 문장을 늘어놓지 않는다 — 뜻은 `끄고 저장`
    풍선이다(설계 규칙 UI-NTF-09, 그림 검수표 equip-41 과 같은 꼴)."""
    app, tables = _start_editing(_database(tmp_path))
    tables.edit(_editor_key(app), _position("C1", "1F"), "사용", False)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)

    assert not list(app.warning)
    assert all(not ends_as_sentence(text) for text in _asked(app))
    assert not [item.value for item in app.caption if "바뀌지 않습니다" in item.value]
    balloon = str(app.button(key=CONFIRM_BUTTON_KEY).help)
    for word in (
        "호기는 그대로 남고 목록·도면에서만 숨습니다",
        "그 시나리오 목록·도면에서 숨습니다",
        "설비 마스터의 동·층 값은 바뀌지 않고 다시 켜면 그대로 보입니다",
    ):
        assert word in balloon
    clear_equipment_repository()


def test_the_off_confirm_lines_sum_floors_and_stand_one_line_per_assumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """여러 층은 합 + 층마다의 수 한 줄이고, 가정 배치 덧줄은 층마다가 아니라 시나리오마다 한
    줄이다 — 끄는 층이 늘어도 줄이 불어나지 않는다."""

    def _counts(_database_path: str, building: str, floor: str) -> tuple[tuple[str, int], ...]:
        assert building == "C3"
        return {"1F": (("셋업 실무", 4), ("가정 B", 2)), "2F": (("셋업 실무", 1),)}[floor]

    monkeypatch.setattr(space_floor_list, "load_layout_overlay_floor_counts", _counts)
    shown = (("C3 1F", 83), ("C3 2F", 55))

    assert space_floor_list._risky_line(shown) == (
        "호기 남은 층 2개 · 공식 배치 호기 138대 · C3 1F 83 · C3 2F 55"
    )
    assert space_floor_list._overlay_lines("ignored", shown) == [
        "가정 배치 「셋업 실무」 · 호기 5대 · C3 1F 4 · C3 2F 1",
        "가정 배치 「가정 B」 · C3 1F · 호기 2대",
    ]


def test_the_off_confirm_names_only_floors_with_units_and_counts_the_official_layout(
    tmp_path: Path,
) -> None:
    """값 줄은 끄는 층 전부가 아니라 호기가 남아 묻는 층만 적는다 — 호기 없는 층을 함께 꺼도 「끄는
    층」 이라 말해 그 층이 어디에도 없었다. 수는 공식 배치 기준이라고 밝힌다 — 가정 배치에만 호기가
    있는 층의 「호기 0대」 가 호기가 있어 묻는 확인과 어긋나 보였다."""
    app, tables = _start_editing(_database(tmp_path))
    tables.edit(_editor_key(app), _position("C1", "1F"), "사용", False)
    tables.edit(_editor_key(app), _position("C3", "3F"), "사용", False)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)

    assert any(item.value == "바뀐 층 2개" for item in app.caption)
    assert _asked(app) == ["호기 남은 층 C1 1F · 공식 배치 호기 3대"]
    assert "적지 않은 층도 함께 꺼집니다" in str(app.button(key=CONFIRM_BUTTON_KEY).help)
    assert space_floor_list._risky_line((("C4 1F", 0),)) == (
        "호기 남은 층 C4 1F · 공식 배치 호기 0대"
    )
    clear_equipment_repository()


def test_changing_only_the_reason_does_not_ask(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED"})
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "1F"), "사유", "창고(임시)")
    tables.run()

    _press(app, tables, SAVE_BUTTON_KEY)

    assert not _asked(app)
    assert _states(database) == {("C1", "1F"): "창고(임시)"}
    assert _version(database) == 2
    clear_equipment_repository()


def test_a_save_after_someone_else_saved_is_refused_and_the_draft_is_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    assert not successes(app)
    assert any("다른 사용자가 먼저 층 사용 설정을 저장해" in item.value for item in app.warning)
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    assert app.session_state[DRAFT_KEY] == {"C4 6F": "NOT_LINE"}
    assert app.session_state[BASE_KEY][0] == 1

    # 거부 표지 창(`write_guard.TRAILING_PRESS_SECONDS`)이 지난 뒤 다시 고치면 최신 위에 저장된다 —
    # 창 안의 저장은 거부된 누름의 둘째 누름으로 본다(아래 빠른 두 번 누름 시험).
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    tables.edit(_editor_key(app), _position("C2", "2F"), "사용", False)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)
    assert _states(database) == {("C2", "2F"): "UNUSED", ("C4", "6F"): "NOT_LINE"}
    clear_equipment_repository()


_C1 = {("C1", floor): "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")}


def _refusals(app: AppTest) -> list[str]:
    return [item.value for item in app.warning if "다른 사용자가 먼저 층 사용 설정을" in item.value]


@pytest.mark.parametrize("other_saves_first", [True, False], ids=["before-save", "during-confirm"])
def test_a_fast_second_press_after_another_save_keeps_the_refusal_and_the_latest_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, other_saves_first: bool
) -> None:
    """남이 C1 을 「생산라인 아님」 으로 저장하고, 옛 화면에서 C1 동 머리를 「사용 안 함」 으로 바꾼
    저장 누름이 빠르게 두 번 간다(2026-10-26 E2E 5회차). 남이 「저장」 전에 저장했으면 끄기 확인을
    건너뛰고 「저장」 누름이 곧장 거부되고(I73), 확인을 띄운 뒤에 저장했으면 「끄고 저장」 누름이
    거부된다. 둘째 누름은 옛 화면의 위젯 값을 그대로 보낸다 — 동 머리 값(내 옛 변경)이 거부 회차가
    올린 새 세대로 다시 얹히고, 거부 알림은 둘째 회차가 다시 그리며 사라져, 다음 저장이 남의 저장을
    말없이 덮었다. 거부는 남고 초안은 최신 그대로다."""
    # 둘째 회차가 거부 표지 창(`TRAILING_PRESS_SECONDS`) 안에 들게 — AppTest 회차는 브라우저보다
    # 느리다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 600.0)
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    repository = DuckDBEquipmentRepository(database)
    if other_saves_first:
        repository.save_floor_states(_C1, expected_version=0, source="남")
    app.segmented_control(key="space_floor_state_bulk_C1").set_value("UNUSED")
    tables.run()
    _ok(app)
    if other_saves_first:
        app.button(key=SAVE_BUTTON_KEY).click()
    else:
        _press(app, tables, SAVE_BUTTON_KEY)
        assert _asked(app) == ["호기 남은 층 C1 1F · 공식 배치 호기 3대"]
        repository.save_floor_states(_C1, expected_version=0, source="남")
        app.button(key=CONFIRM_BUTTON_KEY).click()
    pressed = tables._states()

    app._run(widget_state=pressed)
    _ok(app)
    assert len(_refusals(app)) == 1
    app._run(widget_state=pressed)
    _ok(app)

    assert len(_refusals(app)) == 1, [item.value for item in app.warning]
    assert not _asked(app)
    assert app.session_state[DRAFT_KEY] == {f"C1 {floor}": "NOT_LINE" for _, floor in _C1}
    assert app.session_state[BASE_KEY][0] == 1
    assert any("바뀐 층 0개" in item.value for item in app.caption)
    # 창 안의 저장도 옛 화면의 누름으로 보고 쓰지 않는다 — 거부를 다시 알린다.
    _press(app, tables, SAVE_BUTTON_KEY)
    assert len(_refusals(app)) == 1 and _version(database) == 1
    # 창이 지나면 새 화면을 보고 누른 저장이다 — 바뀐 것이 없어 남의 저장이 그대로다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _press(app, tables, SAVE_BUTTON_KEY)
    assert any("바뀐 층이 없습니다" in item.value for item in infos(app))
    assert _states(database) == _C1 and _version(database) == 1


def test_turning_off_a_floor_with_units_after_someone_else_saved_skips_the_confirm(
    tmp_path: Path,
) -> None:
    """남이 먼저 저장한 뒤 호기가 남은 층을 끄고 「저장」 하면 끄기 확인을 먼저 받고, 「끄고 저장」
    뒤에야 「다른 사용자가 먼저 … 반영하지 않았습니다」 가 떴다(E2E r3). 결국 반영되지 않을 확인을
    건너뛰고 곧장 거부를 알린다 — 초안은 최신 저장본으로 다시 선다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    DuckDBEquipmentRepository(database).save_floor_states(
        {("C4", "6F"): "NOT_LINE"}, expected_version=0, source="남"
    )
    tables.edit(_editor_key(app), _position("C1", "1F"), "사용", False)
    tables.run()

    _press(app, tables, SAVE_BUTTON_KEY)

    assert CONFIRM_KEY not in app.session_state
    assert not _asked(app)
    assert any("다른 사용자가 먼저 층 사용 설정을 저장해" in item.value for item in app.warning)
    assert _states(database) == {("C4", "6F"): "NOT_LINE"}
    assert app.session_state[BASE_KEY][0] == 1
    clear_equipment_repository()


def test_saving_without_changes_says_so_and_writes_nothing(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C3", "2F"): "UNUSED"})
    app, tables = _start_editing(database)

    _press(app, tables, SAVE_BUTTON_KEY)

    assert any("바뀐 층이 없습니다" in item.value for item in infos(app))
    assert not successes(app)
    assert _version(database) == 1
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    clear_equipment_repository()


def test_a_hand_written_blank_reason_floor_stays_inactive_in_the_editor(
    tmp_path: Path, _stub_editor: list[dict[str, Any]]
) -> None:
    """손으로 넣은 빈 사유 비활성 행(앱으로는 못 만든다)은 도면·목록·편집표가 같은 「사용 안
    함」 이고, 편집을 켠 것만으로 바뀐 층이 생기지 않는다 — 편집표가 그 층을 「사용」 으로 그리고
    「바뀐 층 1개」 로 세던 것(2026-10-27 표적 E2E). 그대로 저장해도 그 층은 사용으로 돌아가지
    않는다."""
    database = _database(tmp_path)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.floor_state (building, floor_name, reason) "
            "VALUES ('C1', '3F', '')"
        )
    clear_equipment_repository()
    _, inactive = _floor_tables(_app(database).run())
    assert inactive[["동", "층", "사유"]].values.tolist() == [["C1", "3F", "사용 안 함"]]
    fab = [data for data in _stub_editor if data.get("scope") == "fab"][-1]
    assert fab["linkStats"]["C1 3F"]["inactive"] == "사용 안 함"

    app, tables = _start_editing(database)
    frame = _editor_frame(app)
    position = _position("C1", "3F")
    assert not frame["사용"].tolist()[position]
    assert frame["사유"].tolist()[position] == "사용 안 함"
    assert any("바뀐 층 0개" in caption.value for caption in app.caption)

    _press(app, tables, SAVE_BUTTON_KEY)
    assert any("바뀐 층이 없습니다" in item.value for item in infos(app))
    assert _states(database) == {("C1", "3F"): "UNUSED"}
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
    assert not successes(app) and not infos(app)
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


# 비활성 층을 연 회차의 표지 앞머리(「… **비활성 층** · 사유」). 빠지는 곳 · 다시 켜는 곳은 그
# 풍선이다.
INACTIVE_MARK = ":material/block: **비활성 층** · "


def _inactive_marks(app: AppTest) -> list[str]:
    """층 상세 위 비활성 층 표지(본문 캡션)의 글 — 풍선이 다시 켜는 곳을 말하는지도 본다."""
    marks = [item for item in app.main.caption if item.value.startswith(INACTIVE_MARK)]
    assert all("「사용 편집」에서 다시 켭니다" in item.proto.help for item in marks)
    return [item.value for item in marks]


def test_inactive_floors_stand_one_head_and_their_words_sit_in_the_list_balloon(
    tmp_path: Path,
) -> None:
    """펼침 머리 「비활성 층 n개」 곁에 같은 이름의 표지를 또 세우지 않고, 표지의 몫이던 풍선 글은
    「층 목록」 풍선 뒤에 잇는다(설계 규칙 UI-TXT-07)."""
    app = _app(_database(tmp_path, {("C1", "6F"): "UNUSED"})).run()
    _ok(app)

    assert [item.label for item in app.expander if "비활성 층" in item.label] == ["비활성 층 1개"]
    assert not [item.value for item in app.main.caption if "비활성 층" in item.value]
    head = next(item for item in app.main.caption if item.value == "층 목록")
    assert "행을 고르면 그 층이 열립니다" in head.proto.help
    assert "회색 빗금으로 흐리고 눌러도 열리지 않습니다" in head.proto.help
    clear_equipment_repository()


def test_a_row_of_the_inactive_table_opens_that_floor_with_a_banner(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "1F"): "UNUSED", ("C2", "1F"): "NOT_LINE"})
    app = _app(database).run()
    _ok(app)

    _select_row(app, INACTIVE_TABLE_KEY, 0)
    _ok(app)

    assert app.session_state["space_status_selected_building"] == "C1"
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert app.query_params["floor"] == ["C1-1F"]
    assert _inactive_marks(app) == [f"{INACTIVE_MARK}사용 안 함"]
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
    assert not _inactive_marks(app)
    clear_equipment_repository()


def test_the_address_of_an_inactive_floor_opens_it_with_the_banner(tmp_path: Path) -> None:
    database = _database(tmp_path, {("C1", "3F"): "UNUSED", ("C2", "1F"): "NOT_LINE"})
    app = _app(database, floor="C1-3F").run()
    _ok(app)

    assert app.session_state["space_status_selected_floor"] == "3F"
    assert _inactive_marks(app) == [f"{INACTIVE_MARK}사용 안 함"]
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


# 마크다운으로 읽히면 지움선·기울임·링크·수식이 되는 글자를 담은 사유(20자 안).
REASON_WITH_MARKS = "A~B~C *굵* [x](y)$1$"


def _editor_frame(app: AppTest) -> pd.DataFrame:
    return next(table for table in app.dataframe if "호기" in table.value.columns).value


def test_the_reason_column_takes_free_text_up_to_twenty_characters(tmp_path: Path) -> None:
    """사유 칸은 직접 적는 글 칸이다(2026-10-26 결정) — 20자, 도움말에 예시 두 문구, `string`
    고정."""
    app, _ = _start_editing(_database(tmp_path))
    editor = next(table for table in app.dataframe if "호기" in table.value.columns)
    config = json.loads(editor.proto.columns)["사유"]
    assert config["type_config"] == {"type": "text", "max_chars": 20}
    # 풍선은 마크다운이라 예시 글의 괄호를 막아 싣는다(보이는 글은 괄호 그대로).
    assert f"{quoted('사용 안 함')} · {quoted('생산라인 아님(사무·창고 등)')}" in config["help"]
    assert "생산라인 아님\\(사무·창고 등\\)" in config["help"]
    assert str(editor.value["사유"].dtype) == "string"
    clear_equipment_repository()


def test_a_typed_reason_is_saved_and_shown_as_written_after_reloading(
    tmp_path: Path, _stub_editor: list[dict[str, Any]]
) -> None:
    """적기 → 저장 → 다시 열기. 앞뒤 공백만 떼고 목록 표·도면 블록·편집표가 적은 글 그대로다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C2", "3F"), "사유", "  설비 반입 대기  ")
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "설비 반입 대기"}
    assert app.segmented_control(key="space_floor_state_bulk_C2").label == "C2 · 사용 5/6"

    _press(app, tables, SAVE_BUTTON_KEY)

    assert _states(database) == {("C2", "3F"): "설비 반입 대기"}
    assert any("비활성 1개(설비 반입 대기 1)" in item.value for item in successes(app))

    clear_equipment_repository()
    reloaded, tables = _start_editing(database)
    _, inactive = _floor_tables(_app(database).run())
    assert inactive[["동", "층", "사유"]].values.tolist() == [["C2", "3F", "설비 반입 대기"]]
    fab = [data for data in _stub_editor if data.get("scope") == "fab"][-1]
    assert fab["linkStats"]["C2 3F"]["inactive"] == "설비 반입 대기"
    assert _editor_frame(reloaded)["사유"].tolist()[_position("C2", "3F")] == "설비 반입 대기"

    # 같은 글을 다시 적어도(공백만 다름) 바뀐 층이 아니다.
    tables.edit(_editor_key(reloaded), _position("C2", "3F"), "사유", "설비 반입 대기 ")
    tables.run()
    _press(reloaded, tables, SAVE_BUTTON_KEY)
    assert any("바뀐 층이 없습니다" in item.value for item in infos(reloaded))
    assert _version(database) == 1
    clear_equipment_repository()


def test_legacy_codes_keep_their_labels_and_retyping_a_label_changes_nothing(
    tmp_path: Path,
) -> None:
    """옛 코드 `UNUSED`·`NOT_LINE` 는 지금 글 그대로 보이고, 그 글을 그대로 적으면 그 코드다."""
    database = _database(tmp_path, {("C1", "2F"): "UNUSED", ("C4", "1F"): "NOT_LINE"})
    _, inactive = _floor_tables(_app(database).run())
    assert inactive["사유"].tolist() == ["사용 안 함", "생산라인 아님"]

    app, tables = _start_editing(database)
    reasons = _editor_frame(app)["사유"].tolist()
    assert reasons[_position("C1", "2F")] == "사용 안 함"
    assert reasons[_position("C4", "1F")] == "생산라인 아님"
    tables.edit(_editor_key(app), _position("C4", "1F"), "사유", "생산라인 아님")
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C1 2F": "UNUSED", "C4 1F": "NOT_LINE"}
    assert any("바뀐 층 0개" in caption.value for caption in app.caption)

    _press(app, tables, SAVE_BUTTON_KEY)
    assert any("바뀐 층이 없습니다" in item.value for item in infos(app))
    assert _states(database) == {("C1", "2F"): "UNUSED", ("C4", "1F"): "NOT_LINE"}
    clear_equipment_repository()


@pytest.mark.parametrize(
    ("typed", "refusal"),
    [
        ("가" * 21, "C2 3F 사유는 20자까지입니다(지금 21자)"),
        ("창\n고", "C2 3F 사유에 줄바꿈·탭 같은 제어 문자는 넣을 수 없습니다"),
    ],
    ids=["21자", "줄바꿈"],
)
def test_a_reason_that_cannot_be_stored_is_refused_on_save(
    tmp_path: Path, typed: str, refusal: str
) -> None:
    """브라우저 칸은 UTF-16 20단위에서 끊지만(붙여넣기도) 저장 입구가 한 번 더 본다 — 거절은 알림
    칸이고 쓰지 않으며 편집은 남는다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C2", "3F"), "사유", typed)
    tables.run()
    _ok(app)

    _press(app, tables, SAVE_BUTTON_KEY)

    assert any(refusal in item.value for item in app.error)
    assert _version(database) == 0
    assert app.toggle(key=EDIT_TOGGLE_KEY).value
    assert app.session_state[DRAFT_KEY] == {"C2 3F": typed}
    clear_equipment_repository()


def test_a_refused_reason_stays_visible_in_its_cell_after_the_editor_is_rebuilt(
    tmp_path: Path,
) -> None:
    """거절된 글은 편집표를 새로 세운 뒤에도 칸에 그대로다 — 도면·배너처럼 줄바꿈을 빈칸으로 그리면
    보이는 글로는 무엇을 고칠지 알 수 없다(2026-10-26 리뷰). 칸을 다시 적으면 저장된다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "5F"), "사유", "가나\n다라")
    tables.run()
    _ok(app)
    _press(app, tables, SAVE_BUTTON_KEY)
    assert any("C1 5F 사유에 줄바꿈·탭 같은 제어 문자는" in item.value for item in app.error)
    assert any("그 칸을 지우고 다시 적으세요" in item.value for item in app.error)

    # 다른 동 머리로 편집표를 새로 세운다(끄고 다시 켬).
    key = _editor_key(app)
    for value in ("UNUSED", "ACTIVE"):
        app.segmented_control(key="space_floor_state_bulk_C3").set_value(value)
        tables.run()
        _ok(app)
    assert _editor_key(app) != key
    assert app.session_state[DRAFT_KEY] == {"C1 5F": "가나\n다라"}
    assert _editor_frame(app)["사유"].tolist()[_position("C1", "5F")] == "가나\n다라"

    tables.edit(_editor_key(app), _position("C1", "5F"), "사유", "가나 다라")
    tables.run()
    _ok(app)
    _press(app, tables, SAVE_BUTTON_KEY)
    assert _states(database) == {("C1", "5F"): "가나 다라"}
    clear_equipment_repository()


def test_an_emoji_cut_in_half_at_the_twenty_unit_limit_is_dropped(tmp_path: Path) -> None:
    """브라우저 글 칸의 `max_chars` 는 UTF-16 단위로 자른다 — 「가」×19 + 이모지(2단위)는 이모지
    반쪽(짝 없는 서로게이트)으로 온다. 그 반쪽은 Arrow·DuckDB 가 UTF-8 로 싣지 못해 편집표가 깨지고
    저장은 DB 를 무효로 만든다 — 접을 때 떼고, 반쪽이 남은 칸은 새로 세운다(2026-10-26 리뷰)."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    key = _editor_key(app)
    cut = ("가" * 19 + "\U0001f600").encode("utf-16-le", "surrogatepass")[:40]
    typed = cut.decode("utf-16-le", "surrogatepass")
    assert typed == "가" * 19 + "\ud83d"
    tables.edit(key, _position("C2", "3F"), "사유", typed)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C2 3F": "가" * 19}
    assert _editor_key(app) != key
    assert _editor_frame(app)["사유"].tolist()[_position("C2", "3F")] == "가" * 19

    _press(app, tables, SAVE_BUTTON_KEY)
    assert _states(database) == {("C2", "3F"): "가" * 19}
    clear_equipment_repository()


def test_typing_a_legacy_code_shows_its_label_at_once(tmp_path: Path) -> None:
    """옛 코드 글자 「UNUSED」·「NOT_LINE」 을 그대로 적으면 그 코드다 — 저장된 글로는 옛 코드와
    가를 수 없다. 칸은 곧바로 그 글(「생산라인 아님」)로 새로 세워 저장 뒤와 같게 보인다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    key = _editor_key(app)
    tables.edit(key, _position("C4", "2F"), "사유", "NOT_LINE")
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C4 2F": "NOT_LINE"}
    assert _editor_key(app) != key
    assert _editor_frame(app)["사유"].tolist()[_position("C4", "2F")] == "생산라인 아님"
    clear_equipment_repository()


def test_a_reason_with_markdown_characters_is_drawn_as_written(
    tmp_path: Path, _stub_editor: list[dict[str, Any]]
) -> None:
    """사유는 마크다운으로 읽지 않는다 — 배너·성공 알림은 `literal_markdown` 으로 막고, 표·도면 블록
    (JS 가 textContent 로 싣는다)에는 적은 글 그대로다."""
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "3F"), "사유", REASON_WITH_MARKS)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)

    assert _states(database) == {("C1", "3F"): REASON_WITH_MARKS}
    (saved,) = [item.value for item in successes(app)]
    assert f"비활성 1개({literal_markdown(REASON_WITH_MARKS)} 1)" in saved
    assert REASON_WITH_MARKS not in saved
    _, inactive = _floor_tables(app)
    assert inactive["사유"].tolist() == [REASON_WITH_MARKS]
    fab = [data for data in _stub_editor if data.get("scope") == "fab"][-1]
    assert fab["linkStats"]["C1 3F"]["inactive"] == REASON_WITH_MARKS

    clear_equipment_repository()
    opened = _app(database, floor="C1-3F").run()
    _ok(opened)
    (banner,) = _inactive_marks(opened)
    assert banner == f"{INACTIVE_MARK}{literal_markdown(REASON_WITH_MARKS)}"
    assert REASON_WITH_MARKS not in banner
    clear_equipment_repository()


def test_the_theme_marker_sees_a_typed_reason(tmp_path: Path) -> None:
    """적은 사유도 탭 점·떠나기 확인·테마 표지가 페이지보다 먼저 센다 — 저장본과 같은 글로 되적으면
    내린다."""
    database = _database(tmp_path, {("C1", "3F"): "창고"})
    app = AppTest.from_string(_marker_first_script(database), default_timeout=90)
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    tables = BrowserTables(app)
    tables.run()
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    tables.run()
    _ok(app)
    assert app.session_state["marker_before_page"] is False

    tables.edit(_editor_key(app), _position("C1", "3F"), "사유", "창고 2")
    tables.run()
    _ok(app)
    assert app.session_state["marker_before_page"] is True

    tables.edit(_editor_key(app), _position("C1", "3F"), "사유", " 창고 ")
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C1 3F": "창고"}
    assert app.session_state["marker_before_page"] is False
    clear_equipment_repository()


def _marker_first_script(database: Path) -> str:
    """`app.py` 처럼 테마 표지를 페이지보다 **먼저** 세어 세션에 적고 페이지를 돌린다."""
    return (
        "import streamlit as st\n"
        "from capa_simulation.components.space_floor_list import floor_state_draft_pending\n"
        "st.session_state['marker_before_page'] = floor_state_draft_pending()\n"
    ) + _page_script(PAGE, database)


def test_the_theme_marker_sees_a_cell_edit_on_its_own_run(tmp_path: Path) -> None:
    """`app.py` 의 표지는 페이지(초안 접기)보다 먼저 돈다 — 칸 하나를 고친 그 회차에 벌써 서야 첫
    편집 직후 테마를 바꿔도 묻는다(리뷰 결함 2). 끈 칸을 다시 켜 저장본과 같아지면 내린다."""
    database = _database(tmp_path)
    app = AppTest.from_string(_marker_first_script(database), default_timeout=90)
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    tables = BrowserTables(app)
    tables.run()
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    tables.run()
    _ok(app)
    assert app.session_state["marker_before_page"] is False

    tables.edit(_editor_key(app), _position("C1", "3F"), "사용", False)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {"C1 3F": "UNUSED"}
    assert app.session_state["marker_before_page"] is True

    tables.edit(_editor_key(app), _position("C1", "3F"), "사용", True)
    tables.run()
    _ok(app)
    assert app.session_state[DRAFT_KEY] == {}
    assert app.session_state["marker_before_page"] is False
    clear_equipment_repository()


def test_opening_a_floor_drops_the_draft_on_that_run_so_the_marker_is_down(tmp_path: Path) -> None:
    """층을 여는 콜백이 초안과 토글을 함께 버린다 — 페이지보다 먼저 도는 `app.py` 의 탭 점·떠나기
    확인·테마 단추 확인이 층을 연 그 회차에 벌써 내려가야 한다(이미 버린 초안을 묻지 않는다)."""
    database = _database(tmp_path)
    app = AppTest.from_string(_marker_first_script(database), default_timeout=90)
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    tables = BrowserTables(app)
    tables.run()
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    tables.run()
    tables.edit(_editor_key(app), _position("C3", "1F"), "사용", False)
    tables.run()
    _ok(app)
    assert app.session_state["marker_before_page"] is True

    app.selectbox(key=JUMP_FAB_KEY).set_value("C2 1F")
    tables.run()
    _ok(app)

    assert app.session_state["space_status_selected_floor"] == "1F"
    assert app.session_state["marker_before_page"] is False
    assert DRAFT_KEY not in app.session_state and BASE_KEY not in app.session_state
    clear_equipment_repository()


def _holds(node: Any, found: Any) -> bool:
    if found(node):
        return True
    return isinstance(node, Block) and any(_holds(child, found) for child in node.children.values())


def _children(block: Any) -> list[Any]:
    return [child for _, child in sorted(block.children.items())]


def _before_table(app: AppTest, table: Any) -> list[Any]:
    """`table` 을 바로 품은 칸에서 표 앞의 형제들(차례대로)."""
    stack: list[Any] = [app.main]
    while stack:
        children = _children(stack.pop())
        tables = [index for index, child in enumerate(children) if table(child)]
        if tables:
            return children[: tables[0]]
        stack.extend(child for child in children if isinstance(child, Block))
    raise AssertionError("표가 없다")


def _is_space(node: Any) -> bool:
    return getattr(node, "type", "") == "space"


def _toolbar_clearance_is_last(between: list[Any]) -> None:
    """표 바로 앞 형제가 띄움 하나다 — 표 도구 막대(표 위 37px 까지 솟는다)가 머리 줄 오른쪽 끝을
    덮지 않게(AGENTS 9장 「표 도구 막대」)."""
    spaces = [node for node in between if _is_space(node)]
    assert len(spaces) == 1
    assert between[-1] is spaces[0]
    assert TABLE_TOOLBAR_CLEARANCE >= 20


def test_the_floor_list_table_keeps_its_toolbar_off_the_edit_switch(tmp_path: Path) -> None:
    """표에서 머리 줄 오른쪽 끝 `사용 편집` 으로 옮긴 누름을 표 도구 막대가 가로챘다(2026-10-26
    E2E). 그 띄움은 남기되 빈 알림 칸은 표 앞에 틈을 더하지 않는다 — 머리 칸이 `gap=None` 이고 위
    구획과는 구획 사이만큼 떨어져 제목이 표의 머리로 읽힌다(설계 규칙 UI-CON-05)."""
    app = _app(_database(tmp_path)).run()
    _ok(app)

    before = _before_table(
        app, lambda node: isinstance(node, Dataframe) and "미배치대수" in node.value.columns
    )
    lead = before[-1]
    assert lead.proto.flex_container.gap_config.gap_size == GapSize.NONE
    inside = _children(lead)
    assert _holds(
        inside[0],
        lambda node: (
            getattr(node, "type", "") == "toggle" and getattr(node, "key", None) == EDIT_TOGGLE_KEY
        ),
    )
    _toolbar_clearance_is_last(inside[1:])
    assert _is_space(before[-2])
    assert not [node for node in _children(inside[1]) if _is_space(node)]
    clear_equipment_repository()


def _view_notices(app: AppTest) -> list[Any]:
    """보기 모드 머리 칸 안 알림 칸의 자식들(차례대로)."""
    lead = _before_table(
        app, lambda node: isinstance(node, Dataframe) and "미배치대수" in node.value.columns
    )[-1]
    return _children(_children(lead)[1])


def test_a_warning_in_the_view_notices_stands_off_the_head_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """머리 칸이 `gap=None` 이라 보기 모드 알림 칸의 경고가 머리 줄에 틈 없이 붙었다 — 남의 저장에
    거부된 직후 스위치를 끈 회차다. 경고가 서는 회차에만 칸이 틈을 든다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 600.0)
    database = _database(tmp_path)
    app, tables = _start_editing(database)
    DuckDBEquipmentRepository(database).save_floor_states(_C1, expected_version=0, source="남")
    tables.edit(_editor_key(app), _position("C2", "3F"), "사용", False)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)
    assert len(_refusals(app)) == 1

    app.toggle(key=EDIT_TOGGLE_KEY).set_value(False)
    tables.run()
    _ok(app)

    assert len(_refusals(app)) == 1
    notices = _view_notices(app)
    assert _is_space(notices[0])
    assert any(
        _holds(node, lambda found: getattr(found, "type", "") == "warning") for node in notices
    )
    clear_equipment_repository()


@pytest.mark.parametrize(("kind", "stands"), [("warning", True), ("error", True), ("info", False)])
def test_only_what_stands_in_the_view_notices_adds_the_gap(
    tmp_path: Path, kind: str, stands: bool
) -> None:
    """담아 둔 알림도 칸에 서는 경고 · 오류만 틈을 든다 — 안내는 알림창으로만 간다."""
    app = _app(_database(tmp_path)).run()
    _ok(app)
    app.session_state[space_floor_list.NOTICE_KEY] = (kind, "알림")
    app.run()

    assert bool([node for node in _view_notices(app) if _is_space(node)]) is stands
    assert len([*app.warning, *app.error]) == int(stands)
    clear_equipment_repository()


def test_a_save_success_adds_no_gap_to_the_view_notices(tmp_path: Path) -> None:
    """성공은 알림창으로만 가 칸에 서지 않는다 — 저장 뒤 표가 틈만큼 밀렸다 돌아오지 않는다."""
    database = _database(tmp_path, {("C1", "1F"): "UNUSED"})
    app, tables = _start_editing(database)
    tables.edit(_editor_key(app), _position("C1", "1F"), "사용", True)
    tables.run()
    _press(app, tables, SAVE_BUTTON_KEY)

    assert any("층 사용 설정을 저장했습니다" in item.value for item in successes(app))
    assert not [node for node in _view_notices(app) if _is_space(node)]
    clear_equipment_repository()


def test_the_floor_detail_has_no_table_below_the_drawing(tmp_path: Path) -> None:
    """층 상세 아래 호기 표와 그 머리 줄 「층 전체 보기」 는 도면 위 「호기 정보」 창으로 옮겼다
    (2026-11-03 사용자 요청) — 표 도구 막대가 가로챌 머리 줄 단추도, 본문 표도 없다."""
    app = _app(_database(tmp_path), floor="C1-1F").run()
    _ok(app)
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert not list(app.dataframe)
    assert not [b for b in app.button if getattr(b, "label", None) == "층 전체 보기"]
    clear_equipment_repository()


def _pending_script() -> None:
    import streamlit as st

    from capa_simulation.components.space_floor_list import floor_state_draft_pending

    st.session_state["pending_result"] = floor_state_draft_pending()


@pytest.mark.parametrize(
    ("toggle", "draft", "expected"),
    [
        (True, {"C1 3F": "UNUSED"}, True),
        (True, {}, False),
        (False, {"C1 3F": "UNUSED"}, False),
    ],
    ids=["켜짐·다름", "켜짐·같음", "꺼짐·남은 초안"],
)
def test_the_theme_marker_counts_only_a_live_changed_draft(
    toggle: bool, draft: dict[str, str], expected: bool
) -> None:
    """테마 전환 미저장 표지(`app.py`)는 세션만 읽는다 — 토글이 켜져 있고 초안이 편집 시작 저장본과
    다를 때만 참이다."""
    app = AppTest.from_function(_pending_script)
    app.session_state[EDIT_TOGGLE_KEY] = toggle
    app.session_state[DRAFT_KEY] = draft
    app.session_state[BASE_KEY] = (0, ())
    app.run()
    assert app.session_state["pending_result"] is expected
