# Purpose: 가용설비 현황 탭 ① 설비 마스터의 표 출납·불러오기·팝업 넣기·저장·작은 편집표를 검증한다.

"""탭 ① 「설비 마스터」(개편 명세 4장·11장 화면 묶음).

AppTest 는 표 컴포넌트 JS 를 못 돌린다 — 대역(`tests/grid_fake.py`)이 마운트마다 받은 data 를 적고
넣어 둔 출납·트리거를 받기 콜백으로 보낸다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _page_script
from widget_browser import BrowserTables

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    _NOTE_KEY as NOTE_KEY,
)
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CLIPBOARD_KEY,
    DOWNTIME_EDITOR_KEY,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    GRID_OVERLAY_KEY,
    PENDING_RENAMES_KEY,
    PREVIEW_BUTTON_KEY,
)
from capa_simulation.components.equipment_import_dialog import IMPORT_APPLY_BUTTON_KEY
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_HISTORY,
    SIDE_KEY,
    TABLE_KEY,
)
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.components.tab_marks import pending_tabs_style
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY, EQUIPMENT_TABS
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


# 페이지 뒤에 덧붙이는 시험용 꼬리 — 사이드바 팝업·Space 와 같은 저장 길(`save_equipment_buffer`)을
# 부르고(`FAKE_SAVE_KEY`), 화면 탭 줄이 물을 떠나기 확인 글(`page_tabs.leave_notice`)을 적는다.
FAKE_SAVE_KEY = "test_master_tab_fake_save"
FAKE_SAVE_RESULT_KEY = "test_master_tab_fake_save_result"
LEAVE_NOTICE_KEY = "test_master_tab_leave_notice"
_TAIL = f"""
import streamlit as st
from capa_simulation.components import page_tabs
from capa_simulation.components.equipment_data_workspace import BUFFER_KEY, save_equipment_buffer
from capa_simulation.persistence.equipment_cache import get_equipment_repository
import capa_simulation.settings as settings

st.session_state[{LEAVE_NOTICE_KEY!r}] = page_tabs.leave_notice("available_equipment_status.py")
if st.session_state.pop({FAKE_SAVE_KEY!r}, False):
    try:
        repository = get_equipment_repository(str(settings.EQUIPMENT_DUCKDB_PATH.resolve()))
        save_equipment_buffer(repository, st.session_state[BUFFER_KEY], "팝업 저장")
    except ValueError as exc:
        st.session_state[{FAKE_SAVE_RESULT_KEY!r}] = str(exc)
"""


def _app(path: Path) -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, path) + _TAIL, default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    return app.run()


def _import(app: AppTest, text: str) -> AppTest:
    """「엑셀·CSV로 한꺼번에」 팝업 — 미리보기 뒤 「편집본에 넣기」."""
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
    app.text_area(key=CLIPBOARD_KEY).set_value(text)
    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    return app


def _rows(*names: str) -> str:
    """전체 39칸 양식 꼴의 붙여넣기 글(새 호기는 모든 열이 있어야 한다)."""
    frame = pd.DataFrame("", index=range(len(names)), columns=list(EQUIPMENT_COLUMNS))
    frame["설비명"] = list(names)
    frame["공정소분류"] = "Die Attach"
    frame["보관유무"] = "N"
    frame["기존설비여부"] = "Y"
    frame["레이아웃표시"] = "N"
    return frame.to_csv(sep="\t", index=False)


def test_the_first_data_goes_through_the_import_dialog_and_one_revision_save(
    tmp_path: Path, grid: Calls
) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    assert not app.exception, app.exception
    loader = last(grid, emg.LOADER_KEY)
    assert loader["firstData"] is True
    _import(app, _rows("DA-01", "DA-02"))
    assert (
        app.session_state[EQUIPMENT_DIALOG_KEY]
        if EQUIPMENT_DIALOG_KEY in app.session_state
        else True
    )
    master = app.session_state[BUFFER_KEY][1]
    assert master["설비명"].tolist() == ["DA-01", "DA-02"]
    assert list(app.session_state[GRID_LOADED_KEY]) == ["n:DA-01", "n:DA-02"]
    repository = DuckDBEquipmentRepository(database)
    assert not repository.list_revisions()
    table = last(grid, emg.GRID_KEY)
    assert [row["id"] for row in table["rows"]] == ["n:DA-01", "n:DA-02"]
    assert table["toast"]["text"].startswith("붙여넣기로 2행을 편집본에 넣었습니다")
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    assert len(repository.list_revisions()) == 1
    assert any("설비 데이터를 저장했습니다" in item.value for item in app.success)
    # 저장 뒤 목록은 새 저장본 id 로 옮긴다(n:X → s:X).
    assert list(app.session_state[GRID_LOADED_KEY]) == ["s:DA-01", "s:DA-02"]


def test_a_cell_edit_from_the_grid_outbox_lands_in_the_buffer_and_marks_the_tab(
    tmp_path: Path, grid: Calls
) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01", "DA-02"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    base = last(grid, emg.GRID_KEY)["base"]
    outbox = {
        "mount": "m-test",
        "ops": [
            {
                "seq": 1,
                "at": 1,
                "base": base,
                "op": "cell",
                "id": "s:DA-01",
                "col": "담당자",
                "text": "홍길동",
            },
        ],
    }
    send(app, emg.GRID_KEY, "outbox", outbox)
    master = app.session_state[BUFFER_KEY][1]
    assert master.loc[master["설비명"].eq("DA-01"), "담당자"].tolist() == ["홍길동"]
    table = last(grid, emg.GRID_KEY)
    assert table["ack"] == {"mount": "m-test", "seq": 1}
    row = next(row for row in table["rows"] if row["id"] == "s:DA-01")
    assert row["changed"]
    # 같은 출납이 한 번 더 와도 한 번만 반영한다.
    send(app, emg.GRID_KEY, "outbox", outbox)
    assert int(app.session_state[BUFFER_KEY][1]["담당자"].eq("홍길동").sum()) == 1
    # 저장하지 않은 표 편집 — 탭 ① 이름 옆 점(`mark_pending_tabs` 와 같은 판정)과 저장 전 변경 수.
    dot = pending_tabs_style(EQUIPMENT_TAB_KEY, EQUIPMENT_TABS, {EQUIPMENT_MASTER_TAB}).strip()
    assert dot in [str(element.proto.body).strip() for element in app.get("html")]


def test_a_bad_date_stays_as_a_cell_draft_and_blocks_the_revision_save(
    tmp_path: Path, grid: Calls
) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01"))
    base = last(grid, emg.GRID_KEY)["base"]
    send(
        app,
        emg.GRID_KEY,
        "outbox",
        {
            "mount": "m-1",
            "ops": [
                {
                    "seq": 1,
                    "at": 1,
                    "base": base,
                    "op": "cell",
                    "id": "n:DA-01",
                    "col": "반입일정",
                    "text": "내일",
                }
            ],
        },
    )
    assert app.session_state[GRID_OVERLAY_KEY]
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not DuckDBEquipmentRepository(database).list_revisions()
    assert any("오류" in item.value for item in app.error)


def test_loading_by_name_and_opening_the_detail(tmp_path: Path, grid: Calls) -> None:
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01", "DA-02", "DA-03"))
    send(app, emg.LOADER_KEY, "clear", {})
    assert list(app.session_state[GRID_LOADED_KEY]) == []
    send(
        app,
        emg.LOADER_KEY,
        "load",
        {"kind": "names", "ids": ["n:DA-02"], "missing": ["X-9"], "label": "「DA-02」"},
    )
    assert list(app.session_state[GRID_LOADED_KEY]) == ["n:DA-02"]
    assert last(grid, emg.LOADER_KEY)["missing"] == ["X-9"]
    view = last(grid, emg.GRID_KEY)["view"]
    send(app, emg.GRID_KEY, "open", {"view": view, "id": "n:DA-02"})
    assert app.session_state[GRID_DETAIL_KEY] == "n:DA-02"
    detail = last(grid, emg.side_key("detail"))
    assert detail["unit"]["id"] == "n:DA-02"


def test_the_master_tab_is_not_drawn_while_summary_is_open(tmp_path: Path, grid: Calls) -> None:
    app = _app(tmp_path / "equipment.duckdb")
    assert any(key == emg.GRID_KEY for key, _ in grid)
    grid.clear()
    from capa_simulation.navigation import EQUIPMENT_SUMMARY_TAB

    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.run()
    assert not app.exception, app.exception
    assert not grid
    assert TABLE_KEY in app.session_state


def test_renaming_in_the_detail_is_the_same_unit_and_follows_the_save(
    tmp_path: Path, grid: Calls
) -> None:
    """상세 설비명 칸 확정 = 같은 호기 이름 바꿈(개편 명세 4-11 — 사용자 R2·G4). 저장 요청에 이름
    지도가 실려 호기 키를 잇고, 저장 뒤 목록·상세 id 가 새 이름 id 로 옮는다."""
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01", "DA-02"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    repository = DuckDBEquipmentRepository(database)
    keys_before = dict(
        repository.load_snapshot(repository.list_revisions()[0].revision_id).unit_key_pairs
    )
    send(app, emg.GRID_KEY, "open", {"view": last(grid, emg.GRID_KEY)["view"], "id": "s:DA-01"})
    send_ops(
        app,
        grid,
        {"op": "cell", "id": "s:DA-01", "col": "설비명", "text": "DA-11"},
        key=emg.side_key("detail"),
    )
    master = app.session_state[BUFFER_KEY][1]
    assert master["설비명"].tolist() == ["DA-11", "DA-02"]
    assert app.session_state[PENDING_RENAMES_KEY]["units"] == {"DA-11": "DA-01"}
    # 저장본 호기 id 는 이름을 바꿔도 그대로다(s: + 저장본 이름).
    assert app.session_state[GRID_DETAIL_KEY] == "s:DA-01"
    changes = None
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    changes = last(grid, emg.side_key("changes"))
    assert changes["counts"]["cells"] == 1
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    keys_after = dict(repository.load_snapshot(revisions[0].revision_id).unit_key_pairs)
    assert keys_after["DA-11"] == keys_before["DA-01"]
    assert list(app.session_state[GRID_LOADED_KEY]) == ["s:DA-11", "s:DA-02"]
    assert app.session_state[GRID_DETAIL_KEY] == "s:DA-11"


def test_the_saver_survives_a_trip_to_summary_and_the_note_does_not(
    tmp_path: Path, grid: Calls
) -> None:
    """탭 ① 은 숨은 회차에 그리지 않는다 — 저장자는 `persist_state` 로 남고 변경 메모(입력 초안)는
    버려진다(개편 명세 2-3)."""
    from capa_simulation.navigation import EQUIPMENT_SUMMARY_TAB

    app = _app(tmp_path / "equipment.duckdb")
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.text_input(key="equipment_workspace_save_saved_by").set_value("담당A")
    app.text_input(key=NOTE_KEY).set_value("메모 초안")
    app.run()
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.run()
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not app.exception, app.exception
    assert app.text_input(key="equipment_workspace_save_saved_by").value == "담당A"
    assert app.text_input(key=NOTE_KEY).value == ""


def test_the_history_and_downloads_render_in_the_tab(tmp_path: Path, grid: Calls) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    # 내려받기 팝오버 — 양식 셋 + 현재 데이터 셋.
    keys = {button.key for button in app.get("download_button")}
    assert {
        "equipment_master_template_download_v3",
        "equipment_baseline_template_download_v3",
        "equipment_downtime_template_download_v3",
        "equipment_master_current_download_v1",
        "equipment_baseline_current_download_v1",
        "equipment_downtime_current_download_v1",
    } <= keys
    app.session_state[SIDE_KEY] = SIDE_HISTORY
    app.run()
    assert not app.exception, app.exception
    assert app.selectbox(key="equipment_history_revision_id_v4").value is not None
    assert any("바로 다시 그립니다" in item.value for item in app.caption)


def test_a_cell_draft_blocks_every_save_path(tmp_path: Path, grid: Calls) -> None:
    """못 읽은 칸 초안은 편집본 밖이다 — 사이드바 팝업·Space 저장(`save_equipment_buffer`)도 막는다
    (개편 명세 5-3). 칸을 다시 고치면 초안이 걷히고 저장된다."""
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01"))
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "반입일정", "text": "모레"})
    assert app.session_state[GRID_OVERLAY_KEY]
    app.session_state[FAKE_SAVE_KEY] = True
    app.run()
    assert "못 읽은 값 1칸" in str(app.session_state[FAKE_SAVE_RESULT_KEY])
    assert not DuckDBEquipmentRepository(database).list_revisions()
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "반입일정", "text": "2026-11-09"})
    assert GRID_OVERLAY_KEY not in app.session_state


def test_small_editor_edits_mark_the_tab_and_the_leave_question(
    tmp_path: Path, grid: Calls
) -> None:
    """작은 편집표의 적용 전 편집 — 탭 ① 점, 화면 탭 줄 떠나기 확인(`page_tabs.leave_notice`)."""
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    app.session_state[TABLE_KEY] = "비가동 일정"
    app.run()
    tables = BrowserTables(app)
    generation_key = f"{DOWNTIME_EDITOR_KEY}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    tables.add(
        f"{DOWNTIME_EDITOR_KEY}__g{generation}" if generation else DOWNTIME_EDITOR_KEY,
        {"설비명": "DA-01", "비가동유형": "PM", "시작일": "2026-11-03"},
    )
    tables.run()
    assert not app.exception, app.exception
    dot = pending_tabs_style(EQUIPMENT_TAB_KEY, EQUIPMENT_TABS, {EQUIPMENT_MASTER_TAB}).strip()
    assert dot in [str(element.proto.body).strip() for element in app.get("html")]
    assert app.session_state[LEAVE_NOTICE_KEY] == "가용설비 현황 · 비가동 일정"
