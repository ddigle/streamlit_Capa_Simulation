# Purpose: Space FAB 배치 편집(토글·적용·대기·같은 저장 단추·팝업·열기)과 저장 조건을 검사한다.

"""AppTest 는 편집기 JS 를 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어 두고, 세션에
넣어 둔 적용값(`apply`)·열기값(`navigate`)을 돌려준다 — 그 뒤의 검증·대기·저장은 실제 코드가 돈다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alert_marks import active_state, flashed, infos, successes
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor, write_guard
from capa_simulation.components.equipment_data_workspace import BUFFER_KEY
from capa_simulation.components.sample_data import NO_UNITS_MARK, SAMPLE_TOGGLE_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import (
    FAB_CANVAS,
    FLOOR_KEYS,
    default_fab_layout,
    fab_marks_fingerprint,
    floor_label,
)
from capa_simulation.services.floor_layout_mark import marks_extent

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
FAB_EDIT_KEY = "space_fab_edit_mode"
FAKE_APPLY_KEY = "test_fake_fab_apply"
FAKE_NAVIGATE_KEY = "test_fake_fab_open"


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        data = kwargs["data"]
        calls.append(data)
        editing_fab = data.get("scope") == "fab" and data.get("mode") != "view"
        navigate = st.session_state.pop(FAKE_NAVIGATE_KEY, None) if editing_fab else None
        if navigate is not None:
            st.session_state[kwargs["key"]] = {"navigate": navigate}
            kwargs["on_navigate_change"]()
        apply = st.session_state.pop(FAKE_APPLY_KEY, None) if editing_fab else None
        return SimpleNamespace(apply=apply, navigate=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _fab_calls(calls: list[dict[str, Any]], *, editing: bool) -> list[dict[str, Any]]:
    return [
        data
        for data in calls
        if data.get("scope") == "fab" and (data.get("mode") != "view") is editing
    ]


def _app(database: Path, *, saved_fleet: bool, sample: bool = True) -> AppTest:
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    if saved_fleet:
        repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.session_state[SAMPLE_TOGGLE_KEY] = sample
    return app


def _edited_marks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """기본 배치에서 C1 1F 블록을 옮기고 색을 칠하고, S.PKG 가 아닌 자리를 영역+글자로 더한다."""
    marks = [dict(mark) for mark in data["marks"]]
    block = next(mark for mark in marks if mark["link"] == "C1 1F")
    block.update(color="violet", x=block["x"] + 1)
    marks.append({"id": "Z-OUT", "kind": "zone", "x": 1, "y": 52, "w": 12, "h": 6, "color": "rose"})
    marks.append({"id": "T-OUT", "kind": "text", "x": 1, "y": 59, "w": 12, "h": 2})
    return marks


def test_fab_edit_applies_to_the_session_and_the_same_save_button_writes_it(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    database = tmp_path / "fab_edit.duckdb"
    app = _app(database, saved_fleet=True).run()
    assert not app.exception
    assert not app.toggle(key=FAB_EDIT_KEY).disabled

    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()

    assert not app.exception
    data = _fab_calls(editor_calls, editing=True)[-1]
    # 저장본이 없으니 기본 배치가 편집 시작점이다. 연결 대상은 30개 층, 팔레트·트레이는 JS 몫이다.
    assert data["linkTargets"] == [floor_label(key) for key in FLOOR_KEYS]
    assert data["items"] == [] and data["canvas"] == {
        "width": FAB_CANVAS[0],
        "height": FAB_CANVAS[1],
    }
    assert len(data["marks"]) == len(default_fab_layout()[1])
    assert set(data["linkStats"]) == {floor_label(key) for key in FLOOR_KEYS}

    edited = _edited_marks(data)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": edited,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("이 세션에 적용했습니다" in item.value for item in successes(app))
    assert any("S.PKG FAB 전체 배치" in item.value for item in app.markdown)
    # FAB 만 바뀐 저장은 리비전을 만들지 않아 메모가 남을 곳이 없다 — 칸을 세우지 않는다.
    assert not [item for item in app.text_input if item.label == "변경 메모"]
    after = _fab_calls(editor_calls, editing=True)[-1]
    assert after["epoch"] != data["epoch"] and len(after["marks"]) == len(edited)
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_fab_layout_marks() == ()

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("FAB 전체 배치를 저장했습니다" in item.value for item in successes(app))
    assert len(repository.list_revisions()) == 1
    stored = repository.load_fab_layout_marks()
    assert len(stored) == len(edited)
    c1 = next(mark for mark in stored if mark.link == ("C1", "1F"))
    assert c1.color == "violet"
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    # 저장은 콜백이라 FAB 편집 토글이 꺼지지 않는다.
    assert app.toggle(key=FAB_EDIT_KEY).value is True

    app.toggle(key=FAB_EDIT_KEY).set_value(False).run()
    viewer = _fab_calls(editor_calls, editing=False)[-1]
    assert {mark["id"] for mark in viewer["marks"]} >= {"Z-OUT", "T-OUT"}
    clear_equipment_repository()


def test_fab_edit_keeps_the_order_buttons_open_and_saves_an_order_only_change(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 편집기도 「순서」 단추 넷이 열린다(FAB 은 공식 설비 시나리오에서만 고친다 — 2026-11-12
    보드 7-5). 요소 차례만 바꾼 적용도 대기분이 서고 저장하면 그 차례로 남는다."""
    database = tmp_path / "fab_order.duckdb"
    app = _app(database, saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    assert data.get("orderEditable", True) is True
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": _edited_marks(data),
    }
    app.run()
    app.button(key="space_layout_save").click().run()
    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    saved = [mark.mark_id for mark in repository.load_fab_layout_marks()]

    data = _fab_calls(editor_calls, editing=True)[-1]
    assert [mark["id"] for mark in data["marks"]] == saved
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": list(reversed(data["marks"])),
    }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("이 세션에 적용했습니다" in item.value for item in successes(app))
    app.button(key="space_layout_save").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == saved[::-1]
    clear_equipment_repository()


def test_two_blocks_on_one_floor_go_to_a_state_alert_not_the_box(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """같은 층을 가리키는 FAB 블록은 막지 않는 상태다 — 상자 줄 · 적용 알림 꼬리에 적지 않고 상태
    알림 한 줄이다(설계 규칙 UI-NTF-02, 사외 점검 g6-04)."""
    app = _app(tmp_path / "fab_dup.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    marks = [dict(mark) for mark in data["marks"]]
    next(mark for mark in marks if mark["link"] == "C1 2F")["link"] = "C1 1F"
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": marks,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    note = active_state(app, "EQ-17")
    assert note is not None
    assert note["short"] == "같은 층을 가리키는 FAB 블록 1개 층(C1 1F) — 목록: Alarm › 이 줄"
    assert note["tables"][0]["rows"] == [["같은 층을 가리키는 FAB 블록", "C1 1F", "", ""]]
    assert not any("가리킵니다" in str(item.value) for item in app.caption)
    assert not any("같은 층을 가리키는" in item.value for item in successes(app))

    app.button(key="space_layout_discard").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert active_state(app, "EQ-17") is None


def test_fab_edit_and_save_work_without_any_saved_equipment(
    tmp_path: Path, editor_calls: list[dict[str, Any]], date_panels: dict[str, dict[str, Any]]
) -> None:
    """결정 2: FAB 는 설비 리비전과 무관한 현행값이라 설비 저장본이 없어도 고치고 저장한다(샘플을
    끈 빈 화면)."""
    database = tmp_path / "fab_empty.duckdb"
    app = _app(database, saved_fleet=False, sample=False).run()

    assert not app.exception
    assert any(str(item.value) == NO_UNITS_MARK for item in app.sidebar.caption)
    assert not date_panels
    assert _fab_calls(editor_calls, editing=False)
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": {"width": 120, "height": 70},
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("S.PKG FAB 전체 배치" in item.value for item in app.markdown)
    assert not [item for item in app.text_input if item.label == "변경 메모"]
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    profile = repository.load_fab_layout_profile()
    assert profile is not None and profile.canvas_size == (120.0, 70.0)
    # 캔버스만 바꿨으니 요소는 여전히 기본 배치다(요소 행이 없다).
    assert repository.load_fab_layout_marks() == ()
    assert repository.list_revisions() == []
    clear_equipment_repository()


def _fab_box_index(app: AppTest) -> int:
    """본문 맨 윗단에서 FAB 도면 칸(늘 서는 `space_fab_stage` — 편집기/뷰어가 그 안이다)의 순번.
    `배치 편집` 토글은 사이드바 「Space 도면」 상자에 있다(2026-11-03 사용자 요청)."""
    return next(
        index
        for index, node in enumerate(app.main.children.values())
        if isinstance(node, Block)
        and str(getattr(getattr(node, "proto", None), "id", "") or "").endswith("space_fab_stage")
    )


def test_the_fab_box_keeps_its_place_while_the_unsaved_panel_comes_and_goes(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """설비 저장본이 없는 화면은 FAB 대기분이 생겨야 저장 안 한 배치 상자가 선다. 그 자리가 늘 서
    있지 않으면 첫 적용·저장 때 FAB 상자의 순번이 밀려 브라우저가 편집기를 새로 마운트한다."""
    database = tmp_path / "fab_slot.duckdb"
    app = _app(database, saved_fleet=False, sample=False).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    before = _fab_box_index(app)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": _fab_calls(editor_calls, editing=True)[-1]["epoch"],
        "changes": [],
        "canvas": {"width": 120, "height": 70},
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("S.PKG FAB 전체 배치" in item.value for item in app.markdown)
    assert _fab_box_index(app) == before
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    assert _fab_box_index(app) == before
    clear_equipment_repository()


def test_fab_edit_is_off_while_viewing_the_sample_fleet(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app = _app(tmp_path / "fab_sample.duckdb", saved_fleet=False, sample=True)
    app.session_state[FAB_EDIT_KEY] = True
    app.run()

    assert not app.exception
    assert app.toggle(key=FAB_EDIT_KEY).disabled
    # 잠근 스위치는 꺼짐으로 보인다. 켜짐인데 보기 전용 도면이 그려지면 화면이 서로 다른 말을 한다.
    assert app.toggle(key=FAB_EDIT_KEY).value is False
    # 캔버스를 바꾸는 단추가 따로 없다 — FAB 캔버스는 FAB 「배치 편집」 왼쪽 칸 「캔버스」 다.
    assert not [button for button in app.button if str(button.key).startswith("space_floor_layout")]
    assert not _fab_calls(editor_calls, editing=True)
    assert _fab_calls(editor_calls, editing=False)
    clear_equipment_repository()


def test_a_fab_edit_applied_before_the_sample_is_turned_on_cannot_be_saved_but_can_be_discarded(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """결정 2: 샘플 화면에서는 FAB 편집이 꺼진다. 샘플을 끈 채 적용한 대기분은 남기되 저장은 막고
    (까닭을 말한다), 버리기는 된다."""
    database = tmp_path / "fab_sample_after_apply.duckdb"
    app = _app(database, saved_fleet=False, sample=False).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": {"width": 120, "height": 70},
        "marks": None,
    }
    app.run()
    assert not app.button(key="space_layout_save").disabled

    app.session_state[SAMPLE_TOGGLE_KEY] = True
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.toggle(key=FAB_EDIT_KEY).disabled
    # 대기분은 남고 저장만 꺼진다. 까닭은 꺼진 단추의 풍선이다(설계 규칙 UI-INP-07 — 자리 글 없음).
    assert any("S.PKG FAB 전체 배치" in item.value for item in app.markdown)
    save = app.button(key="space_layout_save")
    assert save.disabled and "샘플 스위치를 끄면 저장할 수 있습니다" in save.help
    assert not any("샘플 스위치를 끄면" in item.value for item in app.caption)
    repository = DuckDBEquipmentRepository(database)
    assert repository.load_fab_layout_profile() is None

    app.button(key="space_layout_discard").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    assert repository.load_fab_layout_profile() is None
    clear_equipment_repository()


@pytest.mark.parametrize(
    ("table", "column", "value", "label"),
    [(0, "기존보유대수", 5, "기존 보유대수"), (2, "상세사유", "다른 사유", "비가동 일정")],
)
def test_a_fab_save_with_an_unsaved_baseline_or_downtime_edit_keeps_the_memo(
    tmp_path: Path,
    editor_calls: list[dict[str, Any]],
    table: int,
    column: str,
    value: object,
    label: str,
) -> None:
    """저장은 세 표를 다 견준다. 설비 마스터 밖 RawData 편집이 남아 있으면 FAB 와 함께 저장해도 새
    리비전이 생기니, 메모 칸을 두고 그 편집을 상자 안내에 말하며 적은 메모가 리비전에 남는다."""
    database = tmp_path / f"fab_memo_{table}.duckdb"
    app = _app(database, saved_fleet=True).run()
    frames = [frame.copy() for frame in app.session_state[BUFFER_KEY]]
    frames[table].loc[frames[table].index[0], column] = value
    app.session_state[BUFFER_KEY] = tuple(frames)
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": _edited_marks(data),
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    # 함께 저장되는 곁표 편집은 상자 머리 줄의 값이고, 저장 범위는 `배치 저장` 풍선이다.
    assert any(
        f"{label} 표 편집" in item.value
        for item in app.markdown
        if "저장 안 한 배치 변경" in item.value
    )
    assert f"{label} 표 편집도 함께 저장됩니다" in (app.button(key="space_layout_save").help or "")
    memo = [item for item in app.text_input if item.label == "변경 메모"]
    assert len(memo) == 1
    memo[0].set_value("FAB 와 함께")
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    # 저장은 바뀐 쪽만 새 리비전이 된다 — 기존 보유대수는 공통 대장, 비가동 일정은 설비 시나리오
    # 일정 쪽이다. 메모는 새로 생긴 쪽에 남는다.
    if label == "비가동 일정":
        assert [(item.revision_no, item.note) for item in repository.list_revisions()] == [
            (1, "r1")
        ]
        written = [
            (item.revision_no, item.note)
            for item in repository.list_schedule_revisions("operations")
        ]
    else:
        written = [(item.revision_no, item.note) for item in repository.list_revisions()]
    assert written == [(2, "FAB 와 함께"), (1, "r1")]
    clear_equipment_repository()


def test_a_stale_fab_apply_says_the_drawing_was_reloaded(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app = _app(tmp_path / "fab_stale.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": "old",
        "changes": [],
        "marks": _edited_marks(data),
    }
    app.run()

    assert not app.exception
    assert any(
        "FAB 도면이 바뀌어" in item.value and "다시 고친 뒤 적용" in item.value
        for item in flashed(app, "warning")
    )
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_a_second_press_of_the_same_fab_apply_keeps_the_success_without_blaming_others(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAB 「적용」 을 0.2~0.25초 간격으로 두 번 누르면 둘째 누름이 옛 epoch 의 같은 적용을 보내
    「그 사이 FAB 도면이 바뀌어(예: 다른 화면에서 저장) … 다시 고친 뒤 적용하세요」 경고가 섰다 — 첫
    적용은 이미 들어가 있어 경고대로 다시 고치면 이동이 두 번 들어갔다(2026-10-27 E2E). 같은
    입력이면 경고하지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 30.0)
    app = _app(tmp_path / "fab_apply_twice.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    payload = {"epoch": data["epoch"], "changes": [], "canvas": None, "marks": _edited_marks(data)}
    app.session_state[FAKE_APPLY_KEY] = dict(payload)
    app.run()
    assert any("이 세션에 적용했습니다" in item.value for item in successes(app))
    applied = _fab_calls(editor_calls, editing=True)[-1]

    app.session_state[FAKE_APPLY_KEY] = dict(payload)
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not any("FAB 도면이 바뀌어" in item.value for item in app.warning)
    assert any("이 세션에 적용했습니다" in item.value for item in successes(app))
    assert _fab_calls(editor_calls, editing=True)[-1]["epoch"] == applied["epoch"]
    clear_equipment_repository()


def test_a_block_without_a_floor_is_refused(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app = _app(tmp_path / "fab_bad.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    marks = [dict(mark) for mark in data["marks"]]
    marks.append({"id": "B-NEW", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": ""})
    app.session_state[FAKE_APPLY_KEY] = {"epoch": data["epoch"], "changes": [], "marks": marks}
    app.run()

    assert not app.exception
    assert any("연결 층" in item.value for item in flashed(app, "error"))
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_a_fab_save_after_someone_else_saved_is_refused_and_can_be_discarded(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    database = tmp_path / "fab_conflict.duckdb"
    app = _app(database, saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "marks": _edited_marks(data),
    }
    app.run()
    # 다른 세션이 먼저 FAB 를 저장했다.
    DuckDBEquipmentRepository(database).save_fab_layout(
        canvas=None,
        marks=[{"id": "B", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C5 1F"}],
        base=(None, fab_marks_fingerprint(())),
    )

    app.button(key="space_layout_save").click().run()

    assert not app.exception
    assert any("다른 사용자가 먼저" in item.value for item in app.error)
    assert any("S.PKG FAB 전체 배치" in item.value for item in app.markdown)
    assert [
        mark.mark_id for mark in DuckDBEquipmentRepository(database).load_fab_layout_marks()
    ] == ["B"]

    # 빠져나갈 곳을 말하고, 설비·층 편집은 두고 FAB 대기분만 버리는 단추가 있다.
    assert any("FAB 배치만 버리기" in item.value for item in app.error)
    app.button(key="space_layout_discard_fab").click().run()
    assert not app.exception
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_emptying_the_fab_on_a_small_canvas_is_refused_at_apply(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """요소를 모두 지우면 기본 배치를 그린다 — 그것이 들어가지 않는 영역이면 적용부터 막는다."""
    app = _app(tmp_path / "fab_empty.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": {"width": 20, "height": 20},
        "marks": [],
    }
    app.run()

    assert not app.exception
    assert not app.error
    assert any("적용하지 못했습니다" in item.value for item in flashed(app, "error"))
    assert any("기본 배치" in item.value for item in flashed(app, "error"))
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_the_inspector_open_button_opens_the_block_floor(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """편집 모드에서 블록을 누르면 고르기이고, 선택 칸 [열기] 가 `navigate` 를 보낸다."""
    app = _app(tmp_path / "fab_open.duckdb", saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_NAVIGATE_KEY] = {"epoch": data["epoch"], "target": "C2 3F"}
    app.run()
    app.run()

    assert not app.exception
    assert editor_calls[-1]["scope"] == "floor" and editor_calls[-1]["floor"] == "C2 3F"
    assert app.query_params["floor"] == ["C2-3F"]
    clear_equipment_repository()


def test_the_fab_canvas_changes_in_the_editor_and_guards_the_blocks(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 캔버스는 FAB 「배치 편집」 의 「캔버스」 칸 → 적용 → 「배치 저장」 이다(2026-11-12
    Space 보드 답 1-4 — 「캔버스 편집」 팝업을 걷었다). 지금 그린 층 블록 · 요소보다 좁은 캔버스는
    적용에서 막는다."""
    database = tmp_path / "fab_canvas.duckdb"
    app = _app(database, saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    right, top = marks_extent(default_fab_layout()[1])
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": {"width": right - 5, "height": top},
        "marks": None,
    }
    app.run()

    assert not app.exception
    assert not app.error
    assert any("적용하지 못했습니다" in item.value for item in flashed(app, "error"))
    assert DuckDBEquipmentRepository(database).load_fab_layout_profile() is None

    data = _fab_calls(editor_calls, editing=True)[-1]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": {"width": 130, "height": data["canvas"]["height"]},
        "marks": None,
    }
    app.run()
    assert not app.exception and not app.error
    app.button(key="space_layout_save").click().run()

    assert not app.exception
    profile = DuckDBEquipmentRepository(database).load_fab_layout_profile()
    assert profile is not None and profile.canvas_size[0] == 130.0
    clear_equipment_repository()


def _fab_saved_even_if_equipment_save_fails(database: str) -> None:
    import streamlit as st
    from test_equipment_availability import _baseline, _downtime, _equipment

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        pending_fab_layout,
        save_equipment_buffer,
        stage_fab_layout,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.fab_layout import (
        fab_marks_fingerprint,
        prepare_fab_layout_marks,
    )

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    frames = ensure_equipment_drafts(latest)
    stage_fab_layout(
        None,
        prepare_fab_layout_marks(
            [{"id": "B", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}],
            (101.0, 62.0),
        ),
        base=(None, fab_marks_fingerprint(())),
    )
    # 그 사이 남이 새 설비 리비전을 저장했다 — 설비 쪽 저장은 거부된다.
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r2")
    try:
        save_equipment_buffer(repository, frames, "메모")
    except ValueError as exc:
        st.session_state["error"] = str(exc)
    st.session_state["pending_left"] = pending_fab_layout() is not None


def test_the_fab_is_written_before_the_equipment_save(tmp_path: Path) -> None:
    """FAB 는 설비 저장보다 먼저 따로 쓴다 — 설비 쪽이 막혀도 FAB 는 저장되고 그 사실을 말한다."""
    database = tmp_path / "fab_first.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    app = AppTest.from_function(
        _fab_saved_even_if_equipment_save_fails, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception
    assert "FAB 전체 배치는 저장했지만" in app.session_state["error"]
    assert "다른 사용자가 먼저" in app.session_state["error"]
    assert app.session_state["pending_left"] is False
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["B"]
    clear_equipment_repository()


def _equipment_saved_even_if_fab_is_refused(database: str) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        pending_fab_layout,
        replace_equipment_buffer,
        save_equipment_buffer,
        stage_fab_layout,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.fab_layout import (
        fab_marks_fingerprint,
        prepare_fab_layout_marks,
    )

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    baseline, equipment, downtime = ensure_equipment_drafts(latest)
    equipment = equipment.copy()
    equipment.loc[equipment.index[0], "담당자"] = "이 세션의 설비 편집"
    replace_equipment_buffer((baseline, equipment, downtime))
    base = (None, fab_marks_fingerprint(()))
    stage_fab_layout(
        None,
        prepare_fab_layout_marks(
            [{"id": "MINE", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}],
            (101.0, 62.0),
        ),
        base=base,
    )
    # 그 사이 남이 FAB 를 먼저 저장했다 — FAB 쪽만 거부된다.
    repository.save_fab_layout(
        canvas=None,
        marks=[{"id": "THEIRS", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C5 1F"}],
        base=base,
    )
    try:
        save_equipment_buffer(repository, (baseline, equipment, downtime), "메모")
    except ValueError as exc:
        st.session_state["error"] = str(exc)
    pending = pending_fab_layout()
    st.session_state["pending_base"] = pending.base if pending is not None else None
    st.session_state["pending_ids"] = (
        [mark.mark_id for mark in pending.marks or ()] if pending is not None else None
    )
    st.session_state["expected_base"] = base


def test_a_refused_fab_does_not_block_the_equipment_save(tmp_path: Path) -> None:
    """FAB 는 별도 쓰기다 — 남이 먼저 FAB 를 저장해 거부돼도 설비 편집은 저장되고, FAB 대기분은
    처음 본 값 그대로 남으며 문구가 두 결과와 빠져나갈 곳을 함께 말한다."""
    database = tmp_path / "fab_refused.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    app = AppTest.from_function(
        _equipment_saved_even_if_fab_is_refused, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    error = app.session_state["error"]
    assert "다른 사용자가 먼저" in error and "설비 쪽은 저장했습니다" in error
    assert "FAB 배치만 버리기" in error
    assert len(repository.list_revisions()) == 2
    assert app.session_state["pending_ids"] == ["MINE"]
    assert app.session_state["pending_base"] == app.session_state["expected_base"]
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["THEIRS"]
    clear_equipment_repository()


def test_a_floor_state_save_keeps_the_fab_editor_epoch_and_its_open_is_filtered(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남이 층 사용 상태를 저장해도 FAB 편집기 epoch 는 그대로다(적용 전 FAB 편집을 잃지 않는다) —
    블록 글자의 `inactive` 만 다음 회차에 바뀐다. 편집 [열기] 로 온 비활성 층은 서버도 거른다."""
    from capa_simulation.persistence.equipment_cache import clear_floor_state_cache

    database = tmp_path / "fab_edit.duckdb"
    app = _app(database, saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    before = _fab_calls(editor_calls, editing=True)[-1]
    assert "inactive" not in before["linkStats"]["C1 3F"]

    DuckDBEquipmentRepository(database).save_floor_states(
        {("C1", "3F"): "NOT_LINE"}, expected_version=0, source="남"
    )
    clear_floor_state_cache()
    app.run()

    after = _fab_calls(editor_calls, editing=True)[-1]
    assert not app.exception
    assert after["epoch"] == before["epoch"]
    assert after["linkStats"]["C1 3F"]["inactive"] == "생산라인 아님"

    app.session_state[FAKE_NAVIGATE_KEY] = {"epoch": after["epoch"], "target": "C1 3F"}
    app.run()
    app.run()
    assert not app.exception
    assert "space_status_selected_building" not in app.session_state
    clear_equipment_repository()


@pytest.mark.parametrize("finished", [True, False], ids=["첫 콜백 끝남", "첫 콜백 끊김"])
def test_a_fab_save_pressed_twice_keeps_its_success(
    tmp_path: Path,
    editor_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    finished: bool,
) -> None:
    """FAB 만 바뀐 「배치 저장」 을 0.15~0.5초 간격으로 두 번 누르면 첫 콜백이 FAB 를 쓰고
    대기분을 비운 뒤라 둘째 콜백이 「바뀐 내용이 없어 저장하지 않았습니다.」 로 첫 성공 알림을
    덮었다 — 실제로는 저장됐다(2026-10-27 E2E). 첫 콜백이 끝까지 돌았든 뒷정리 중에 끊겼든 성공
    알림이 남는다."""
    from test_equipment_save_double_press import _press_again_from_the_old_screen, _race_save

    database = tmp_path / "fab_double.duckdb"
    app = _app(database, saved_fleet=True).run()
    app.toggle(key=FAB_EDIT_KEY).set_value(True).run()
    data = _fab_calls(editor_calls, editing=True)[-1]
    edited = _edited_marks(data)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [],
        "canvas": None,
        "marks": edited,
    }
    app.run()
    app.button(key="space_layout_save").click()

    if finished:
        _press_again_from_the_old_screen(app, monkeypatch, callback="_save_space_layout")
    else:
        # 경합 틀은 첫 콜백을 설비 쪽 저장 안에서 1초 세워 둔다 — 둘째 콜백은 그동안 세션 잠금을
        # 기다린다(느린 설비 쪽 대조와 같은 꼴). 첫 FAB 알림은 둘째 누름이 저장에 들어올
        # 때 보므로 창(1초)을 넓히지 않아도 남는다.
        _race_save(app, monkeypatch, callback="_save_space_layout")

    assert not app.exception, [item.message for item in app.exception]
    texts = [str(item.value) for item in (*app.error, *app.warning, *infos(app), *successes(app))]
    assert any("FAB 전체 배치를 저장했습니다" in text for text in texts), texts
    assert not any("바뀐 내용이 없어" in text for text in texts), texts
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1
    assert len(repository.load_fab_layout_marks()) == len(edited)
    clear_equipment_repository()
