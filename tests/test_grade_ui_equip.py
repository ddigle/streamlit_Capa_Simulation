# Purpose: 설비 화면(가용설비 · Space · 설비 시나리오)의 등급 넷마다 단추 · 값만 · 내려받기 유무.

"""등급 넷마다 설비 화면(2026-11-18 접속 등급 — equip 갈래).

설비 · Space 저장과 설비 화면 내려받기 · 설비 시나리오 단추 · 설비 공식 지정 · Cut-off 는
관리자부터, 열람 · 실무자는 같은 화면을 값만 본다. 예외(2차 답 「다」) — 실무자는 설비 마스터
「비가동 일정」 표를 고치고 · 저장하고 · 내려받고, Preference 「입력 비가동」 을 고치고 · 저장한다.
「옛 배포 흔적」 이어 쓰기는 개발자만이다.

모든 등급 시험은 「운영 + 통합인증 켜짐」 판정을 거친다(`grade_support.as_grade` — 가짜 버킷에
명단 · 등급 파일을 올려 넷 계정의 등급을 단언한다). 운영 아님 · 통합인증 꺼진 운영은 지금 화면
그대로다(관리자까지 — 이어 쓰기만 숨음). 값은 모두 합성이다.
설계 규칙: UI-INP-07(예외 — 등급 밖 기능은 숨김) · UI-NTF-03 · UI-NTF-05 · UI-STA-05 · UI-LAY-12.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alert_marks import active_state, flashed
from grade_support import (
    GRADE_PARAMS,
    as_grade,
    assert_refusals_caught,
    grade_page_script,
    judge_spy,
    operational_sso_off,
    unrestricted,
    visible_labels,
)
from grid_fake import Calls, install_fake_grid, last
from streamlit.testing.v1 import AppTest
from test_availability_gap_panel import _panel_app, _select_view
from test_equipment_pages import _open_settings, _page_script
from test_equipment_scenario_publish_guard import _add_trace
from test_equipment_scenario_repository import _clone, _seeded

from capa_simulation.auth import grades
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import grade_ui, space_layout_editor, sso_identity
from capa_simulation.components.availability_sheet_keys import GAP_SHEET_MENU_KEY
from capa_simulation.components.equipment_data_workspace import GRID_LOADED_KEY
from capa_simulation.components.equipment_master_tab import (
    DATA_MENU_LABEL,
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
    SIDE_NEW,
    TABLE_KEY,
)
from capa_simulation.components.equipment_scenario_management import (
    CONTINUE_BUTTON_KEY,
    PUBLISH_BUTTON_KEY,
    SCENARIO_KEY,
)
from capa_simulation.components.equipment_settings_dialog import (
    EQUIPMENT_DIALOG_KEY,
    SETTINGS_DIALOG,
)
from capa_simulation.components.manual_downtime_tab import (
    MANUAL_HISTORY_TOOLS_KEY,
    MANUAL_SAVE_BUTTON,
    MANUAL_TOOLS_KEY,
)
from capa_simulation.navigation import (
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_PREFERENCE_TAB,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services.equipment_bulk_delete import BASELINE_TARGET, DOWNTIME_TARGET

ROOT = Path(__file__).resolve().parents[1]
AVAILABLE = ROOT / "app_pages" / "available_equipment_status.py"
SPACE = ROOT / "app_pages" / "space_status.py"
COVERED_ACTIONS = frozenset(
    {
        "equipment.save",
        "equipment.downtime",
        "equipment.manual_downtime",
        "equipment.export",
        "equipment.scenario",
        "equipment.publish",
        "equipment.cutoff",
        "equipment.legacy_ack",
    }
)
# 이 갈래가 받는 자리를 다는 뿌리 파일(장부 쓰기에 이르는 콜백 · 팝업 · 프래그먼트).
ROOT_FILES = (
    "app_pages/available_equipment_status.py",
    "app_pages/space_status.py",
    "src/capa_simulation/components/equipment_master_tab.py",
    "src/capa_simulation/components/equipment_data_workspace.py",
    "src/capa_simulation/components/equipment_import_dialog.py",
    "src/capa_simulation/components/equipment_scenario_status.py",
    "src/capa_simulation/components/equipment_scenario_management.py",
    "src/capa_simulation/components/equipment_settings_dialog.py",
    "src/capa_simulation/components/cutoff_management.py",
    "src/capa_simulation/components/manual_downtime_tab.py",
    "src/capa_simulation/components/space_floor_list.py",
)
SCENARIO_BUTTONS = (
    "시나리오 이름 바꾸기",
    "이 리비전으로 되돌리기",
    "여기서 새 시나리오",
    "리비전명",
)


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


def _at_least(grade: str, need: str) -> bool:
    return grades.at_least(grade, need)


def _block_keys(app: AppTest) -> set[str]:
    """본문 · 사이드바 · 팝업(이벤트 칸)의 key 있는 칸(`st.container` · 팝오버 · 펼침) 전부."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        key = getattr(node, "key", None)
        if isinstance(key, str) and getattr(node, "children", None) is not None:
            found.add(key)
        for child in getattr(node, "children", {}).values():
            walk(child)

    walk(app._tree)
    return found


def _hidden(app: AppTest, key: str) -> bool:
    """`grade_ui.toolbar_scope` 칸이 표 도구 막대를 감춘 꼴인가(감춤 접두가 붙은 key)."""
    keys = _block_keys(app)
    assert key in keys or f"{grade_ui.HIDDEN_TOOLS_PREFIX}{key}" in keys, (key, sorted(keys))
    return f"{grade_ui.HIDDEN_TOOLS_PREFIX}{key}" in keys


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def test_the_equipment_roots_catch_refusals() -> None:
    assert_refusals_caught(ROOT_FILES)


# ------------------------------------------------------------------ 가용설비 현황 › 설비 마스터
def _master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str) -> tuple[AppTest, Calls]:
    grid = install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(_page_script(AVAILABLE, repository.database_path)), default_timeout=60
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[GRID_LOADED_KEY] = ("s:EQ-01", "s:EQ-02")
    return _ok(app.run()), grid


@GRADE_PARAMS
def test_the_master_grid_is_values_only_below_the_save_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    app, grid = _master(tmp_path, monkeypatch, grade)
    editable = _at_least(grade, grades.MANAGER)

    table = last(grid, emg.GRID_KEY)
    locked = all(emg.GRADE_LOCK in row.get("locks", []) for row in table["rows"])
    assert locked is not editable
    assert (table["deleteLock"] == grades.refusal_text("equipment.save")) is not editable
    assert last(grid, emg.LOADER_KEY)["newEnabled"] is editable, "「+ 새 호기」"
    side = app.segmented_control(key=SIDE_KEY)
    assert (SIDE_NEW in side.options) is editable, "오른쪽 「새 호기」 칸"
    detail = last(grid, emg.side_key("detail"))
    assert detail["newRowsLocked"] is True or editable


@GRADE_PARAMS
def test_the_data_menu_items_follow_the_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    app, _ = _master(tmp_path, monkeypatch, grade)

    downloads = [str(getattr(button, "label", "")) for button in app.get("download_button")]
    if grade == grades.VIEWER:
        assert DATA_MENU_LABEL not in visible_labels(app)
        assert downloads == []
    elif grade == grades.EDITOR:
        assert DATA_MENU_LABEL in visible_labels(app)
        assert len(downloads) == 2, downloads
        assert all("비가동 일정" in label for label in downloads), downloads
    else:
        assert len(downloads) == 6, downloads


@GRADE_PARAMS
def test_the_save_section_and_small_editors_follow_the_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    app, _ = _master(tmp_path, monkeypatch, grade)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    saves = [button for button in app.button if button.key == SAVE_BUTTON_KEY]
    assert bool(saves) is _at_least(grade, grades.EDITOR), "「리비전 저장」 은 실무자부터"

    for target, slug, need in (
        (DOWNTIME_TARGET, "downtime", grades.EDITOR),
        (BASELINE_TARGET, "baseline", grades.MANAGER),
    ):
        app.session_state[TABLE_KEY] = target
        _ok(app.run())
        applies = [b for b in app.button if b.key == f"equipment_{slug}_apply_v1"]
        assert bool(applies) is _at_least(grade, need), (target, "「편집본에 적용」")
        tools = "equipment.export" if target == BASELINE_TARGET else "equipment.downtime"
        hidden = _hidden(app, f"equipment_small_{slug}_tools_v1")
        assert hidden is not _at_least(grade, grades.need_of(tools)), (target, "표 도구 막대")


# ------------------------------------------------------------------ 사이드바 「설비 데이터 저장」
SIDEBAR_SCRIPT = """
import streamlit as st
from pathlib import Path

import capa_simulation.settings as settings
from capa_simulation.components.equipment_data_workspace import ensure_equipment_drafts
from capa_simulation.components.equipment_scenario_status import show_equipment_scenario_dialog
from capa_simulation.equipment_scenario_activation import resolve_equipment_session

settings.EQUIPMENT_DUCKDB_PATH = Path({database!r})
ensure_equipment_drafts(resolve_equipment_session({database!r}).snapshot)
show_equipment_scenario_dialog("available_equipment_status.py")
"""


@GRADE_PARAMS
def test_the_sidebar_save_mode_stands_from_the_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        SAVE_MODE,
    )
    from capa_simulation.components.equipment_scenario_status import (
        SAVE_BUTTON_KEY as SIDEBAR_SAVE_KEY,
    )

    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(SIDEBAR_SCRIPT.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    _ok(app.run())

    modes = [control for control in app.segmented_control if SAVE_MODE in control.options]
    assert bool(modes) is _at_least(grade, grades.EDITOR)
    saves = [button for button in app.button if button.key == SIDEBAR_SAVE_KEY]
    assert bool(saves) is _at_least(grade, grades.EDITOR)


# ------------------------------------------------------------------ Preference · Cut-off
@GRADE_PARAMS
def test_the_manual_downtime_save_stands_from_the_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(_page_script(AVAILABLE, repository.database_path)), default_timeout=60
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_PREFERENCE_TAB
    _ok(app.run())

    submits = [button for button in app.button if button.label == MANUAL_SAVE_BUTTON]
    assert bool(submits) is _at_least(grade, grades.EDITOR)
    assert _hidden(app, MANUAL_TOOLS_KEY) is (grade == grades.VIEWER)
    assert _hidden(app, MANUAL_HISTORY_TOOLS_KEY) is not _at_least(grade, grades.MANAGER)


@GRADE_PARAMS
def test_the_cutoff_save_and_csv_stand_from_the_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(_page_script(AVAILABLE, repository.database_path)), default_timeout=60
    )
    _ok(app.run())
    _ok(_open_settings(app))
    assert app.session_state[EQUIPMENT_DIALOG_KEY] == SETTINGS_DIALOG

    manager = _at_least(grade, grades.MANAGER)
    assert any(button.label == "Cut-off 저장" for button in app.button) is manager
    assert bool([b for b in app.get("download_button") if b.key == "equipment_cutoff_csv_v1"]) is (
        manager
    )
    if not manager:
        # 값만 보이는 읽기 표 — 그 표 위 작은 단추 줄도 감춘다(관리자의 편집표는 늘 막대가 선다).
        assert _hidden(app, "equipment_cutoff_tools_v1")


# ------------------------------------------------------------------ Summary
@GRADE_PARAMS
def test_the_gap_sheet_download_menu_stands_from_the_manager(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar

    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    as_grade(monkeypatch, grade)
    app = _ok(AppTest.from_function(_panel_app, default_timeout=30).run())
    _select_view(app, "분류별 내역")

    menus = [block for block in app.get("popover") if block.key == GAP_SHEET_MENU_KEY]
    assert bool(menus) is _at_least(grade, grades.MANAGER)


ALARM_SCRIPT = """
from test_equipment_availability import _equipment

from capa_simulation.components.equipment_explorer import report_unit_notices

equipment = _equipment()
equipment.loc[equipment["설비명"].eq("EQ-02"), ["반입일정", "Qual일정"]] = None
report_unit_notices(equipment, scope=None)
"""


@GRADE_PARAMS
def test_an_equipment_alarm_table_keeps_its_rows_but_drops_csv_below_the_manager(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    app = _ok(AppTest.from_string(grade_page_script(ALARM_SCRIPT), default_timeout=30).run())

    note = active_state(app, "EQ-20")
    assert note is not None, "일정 미정 알림"
    (table,) = note["tables"]
    assert table["rows"], "표는 보인다"
    assert (table.get("csv", True) is False) is not _at_least(grade, grades.MANAGER)


# ------------------------------------------------------------------ Space 현황
def _space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> tuple[AppTest, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs["data"])
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(_page_script(SPACE, repository.database_path)), default_timeout=60
    )
    return app, calls


@GRADE_PARAMS
def test_space_editing_and_floor_use_stand_from_the_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    app, _ = _space(tmp_path, monkeypatch, grade)
    _ok(app.run())
    manager = _at_least(grade, grades.MANAGER)

    toggles = {str(toggle.label) for toggle in app.toggle}
    assert ("배치 편집" in toggles) is manager, "FAB 배치 편집"
    assert ("사용 편집" in toggles) is manager, "층 목록 사용 편집"
    assert _hidden(app, "space_floor_list_tools_v1") is not manager


@GRADE_PARAMS
def test_the_unit_sheet_csv_stands_from_the_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    app, calls = _space(tmp_path, monkeypatch, grade)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    _ok(app.run())
    manager = _at_least(grade, grades.MANAGER)

    toggles = {str(toggle.label) for toggle in app.toggle}
    assert ("배치 편집" in toggles) is manager, "층 배치 편집"
    sheet = next(call["sheet"] for call in reversed(calls) if call.get("sheet"))
    assert bool(sheet.get("csvHidden")) is not manager
    assert ("csv" in sheet) is manager, "「모든 칸」 글은 아예 싣지 않는다"


# ------------------------------------------------------------------ 시나리오 관리 › 설비 시나리오
SCENARIO_TAB = """
from capa_simulation.components.equipment_scenario_management import (
    render_equipment_scenario_management,
)
from capa_simulation.equipment_scenario_activation import resolve_equipment_session

session = resolve_equipment_session({database!r})
render_equipment_scenario_management({database!r}, session)
"""


@GRADE_PARAMS
def test_the_equipment_scenario_buttons_follow_the_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    repository = _seeded(tmp_path)
    _clone(repository)
    _add_trace(repository.database_path, "old-deploy", 2)
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(
        grade_page_script(SCENARIO_TAB.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    _ok(app.run())
    labels = visible_labels(app)
    manager = _at_least(grade, grades.MANAGER)

    for label in SCENARIO_BUTTONS:
        assert (label in labels) is manager, label
    assert ("공식으로 지정" in labels) is manager
    assert "이 리비전 불러오기" in labels, "고르기 · 불러오기는 모든 등급"
    continues = [button for button in app.button if button.key == CONTINUE_BUTTON_KEY]
    assert bool(continues) is (grade == grades.DEVELOPER), "「이대로 이어 쓰기」 는 개발자만"
    assert _hidden(app, "equipment_scenario_table_tools_v1") is not manager


@pytest.mark.page_failure_card
def test_a_publish_pressed_on_a_screen_drawn_before_losing_the_grade_is_refused_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 시나리오 「공식으로 지정」 — 관리자로 그린 화면(단추가 선 옛 화면)에서 실무자로 내려
    누르면 쓰는 순간의 벽이 막는다. 본문 누름이라 받는 자리는 화면 감싸기(`run_core_page`)다 —
    오류 카드 없이 거절 알림 한 번, 공식 번호 그대로."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    as_grade(monkeypatch, grades.MANAGER)
    app = AppTest.from_string(
        grade_page_script(SCENARIO_TAB.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    _ok(app.run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup.equipment_scenario_id)
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None

    as_grade(monkeypatch, grades.EDITOR)
    # 누른 회차의 화면 판정은 옛 화면 그대로(단추가 선 채) — 벽만 실제 등급을 본다.
    monkeypatch.setattr(sso_identity, "viewer_can", lambda _action: True)
    with judge_spy() as seen:
        app.button(key=PUBLISH_BUTTON_KEY).click().run()

    _ok(app)
    assert not list(app.error), "오류 카드(AD-22)가 서지 않는다"
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("equipment.publish")
    ]
    after = repository.latest_equipment_release()
    assert after is not None and after.release_no == release.release_no
    assert ("equipment.publish", grades.EDITOR) in seen


# ------------------------------------------------------------------ 운영 아님 · 통합인증 꺼짐
@pytest.mark.parametrize("place", ["unrestricted", "operational_sso_off"])
def test_off_the_signed_in_operational_server_the_equipment_screens_stay_as_they_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, place: str
) -> None:
    grid = install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    _add_trace(repository.database_path, "old-deploy", 2)
    if place == "unrestricted":
        unrestricted(monkeypatch)
    else:
        operational_sso_off(monkeypatch)
    app = AppTest.from_string(
        grade_page_script(_page_script(AVAILABLE, repository.database_path)), default_timeout=60
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[GRID_LOADED_KEY] = ("s:EQ-01",)
    _ok(app.run())
    assert not any(
        emg.GRADE_LOCK in row.get("locks", []) for row in last(grid, emg.GRID_KEY)["rows"]
    )
    assert len(list(app.get("download_button"))) == 6

    tab = AppTest.from_string(
        grade_page_script(SCENARIO_TAB.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    _ok(tab.run())
    labels = visible_labels(tab)
    assert all(label in labels for label in SCENARIO_BUTTONS)
    continues = [button for button in tab.button if button.key == CONTINUE_BUTTON_KEY]
    assert bool(continues) is (place == "unrestricted"), "통합인증 꺼진 운영은 관리자까지"
