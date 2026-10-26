# Purpose: 가용설비 현황 탭 ① 설비 마스터의 표 출납·불러오기·팝업 넣기·저장·작은 편집표를 검증한다.

"""탭 ① 「설비 마스터」(개편 명세 4장·11장 화면 묶음).

AppTest 는 표 컴포넌트 JS 를 못 돌린다 — 대역(`tests/grid_fake.py`)이 마운트마다 받은 data 를 적고
넣어 둔 출납·트리거를 받기 콜백으로 보낸다.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _page_script
from test_scenario_save_double_press import _first_callback, _press_again
from widget_browser import BrowserTables

import capa_simulation.components.write_guard as write_guard
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
    GRID_TOAST_KEY,
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
    UNDO_BUTTON_KEY,
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


def test_the_import_toast_counts_only_the_rows_that_changed(tmp_path: Path, grid: Calls) -> None:
    """「현재 데이터」 를 받아 한 칸만 고쳐 넣으면 토스트가 맞댄 줄 전부(「675행을 편집본에
    넣었습니다」)를 셌다 — 「저장 전 변경」 에는 고친 칸 하나뿐이었다(2026-10-27 E2E). 미리보기
    머리의 「바뀔 행」 처럼 실제로 바뀐 줄만 세고, 바뀐 줄이 없으면 편집본이 그대로라고 말한다."""
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01", "DA-02", "DA-03"))
    assert last(grid, emg.GRID_KEY)["toast"]["text"].startswith("붙여넣기로 3행을")

    master = app.session_state[BUFFER_KEY][1]
    edited = master.copy()
    edited.loc[edited["설비명"].eq("DA-02"), "메모1"] = "한 칸"
    _import(app, edited.to_csv(sep="\t", index=False))
    assert last(grid, emg.GRID_KEY)["toast"]["text"].startswith("붙여넣기로 1행을 편집본에")

    _import(app, app.session_state[BUFFER_KEY][1].to_csv(sep="\t", index=False))
    assert last(grid, emg.GRID_KEY)["toast"]["text"] == (
        "붙여넣기에 바뀌는 값이 없어 편집본은 그대로입니다"
    )


def test_the_loader_learns_each_close_of_the_import_dialog(tmp_path: Path, grid: Calls) -> None:
    """팝업이 닫힐 때마다(넣은 뒤·Esc·바깥 누름 — `_close_dialog`) 표 불러오기 data 의
    `dialogClosed` 가 오른다 — 그 회차에 표가 초점을 여는 단추로 돌린다(그림자 DOM 안 단추라
    Streamlit 이 돌려주지 못한다, 2026-10-26 E2E)."""
    app = _app(tmp_path / "equipment.duckdb")
    assert last(grid, emg.LOADER_KEY)["dialogClosed"] == 0
    _import(app, _rows("DA-01"))

    assert last(grid, emg.LOADER_KEY)["dialogClosed"] == 1


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


def _small_key(app: AppTest, key: str) -> str:
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return f"{key}__g{generation}" if generation else key


def test_small_editor_edits_mark_the_tab_and_the_leave_question(
    tmp_path: Path, grid: Calls
) -> None:
    """작은 편집표의 적용 전 편집 — 탭 ① 점, 화면 탭 줄 떠나기 확인(`page_tabs.leave_notice`).
    대역은 브라우저처럼 폼 안 편집을 제출 전에는 보내지 않는다(`forms=True`) — 편집표가 폼 안이면
    적용 전 편집이 서버에 오지 않아 점도 확인도 서지 않는다(리뷰 rs-b1y 재현)."""
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    app.session_state[TABLE_KEY] = "비가동 일정"
    app.run()
    tables = BrowserTables(app, forms=True)
    tables.add(
        _small_key(app, DOWNTIME_EDITOR_KEY),
        {"설비명": "DA-01", "비가동유형": "PM", "시작일": "2026-11-03"},
    )
    tables.run()
    assert not app.exception, app.exception
    dot = pending_tabs_style(EQUIPMENT_TAB_KEY, EQUIPMENT_TABS, {EQUIPMENT_MASTER_TAB}).strip()
    assert dot in [str(element.proto.body).strip() for element in app.get("html")]
    assert app.session_state[LEAVE_NOTICE_KEY] == "가용설비 현황 · 비가동 일정"
    # 다른 위젯 회차(오른쪽 칸 고르기)에도 편집은 남는다.
    app.session_state[SIDE_KEY] = SIDE_HISTORY
    tables.run()
    assert app.session_state[LEAVE_NOTICE_KEY] == "가용설비 현황 · 비가동 일정"
    # 「편집본에 적용」 — 편집본에 들고 편집표가 비어 떠나기 확인이 걷힌다.
    app.button(key="equipment_downtime_apply_v1").click()
    tables.run()
    assert not app.exception, app.exception
    assert app.session_state[BUFFER_KEY][2]["설비명"].tolist() == ["DA-01"]
    tables.run()
    assert app.session_state[LEAVE_NOTICE_KEY] == ""


# 페이지 앞에 덧붙이는 시험용 머리 — 화면 탭 줄처럼 **페이지보다 먼저** 떠나기 확인 글·점을 적는다.
LEAVE_BEFORE_KEY = "test_master_tab_leave_before"
MARKS_BEFORE_KEY = "test_master_tab_marks_before"
_HEAD = f"""
import streamlit as st
from capa_simulation.components import page_tabs

st.session_state[{LEAVE_BEFORE_KEY!r}] = page_tabs.leave_notice("available_equipment_status.py")
st.session_state[{MARKS_BEFORE_KEY!r}] = page_tabs.page_unsaved_marks(
    "available_equipment_status.py"
)
"""


@pytest.mark.parametrize("away", ["inner", "outer"])
def test_switching_away_from_a_small_editor_drops_its_marks_in_the_same_run(
    tmp_path: Path, grid: Calls, away: str
) -> None:
    """작은 편집표의 적용 전 편집은 표 고르기(안쪽)·바깥 탭을 바꾸면 묻지 않고 사라진다(그 표를
    그리지 않는다). 그 회차에 위젯 상태는 회차 끝까지 세션에 남아 — 페이지보다 먼저 그리는 탭 줄 점·
    떠나기 확인·테마 표지와 탭 ① 점이 이미 사라진 편집을 한 회차 동안 말했다(E2E 결함: 떠나기
    확인이 「사라집니다 — 떠날까요?」 를 거짓으로 물었다)."""
    from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS, EQUIPMENT_SUMMARY_TAB

    app = AppTest.from_string(
        _HEAD + _page_script(PAGE, tmp_path / "equipment.duckdb"), default_timeout=60
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    _import(app, _rows("DA-01"))
    # 편집본을 저장해 둔다 — 설비 편집본 점이 작은 편집표 점을 가리지 않게.
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    app.session_state[TABLE_KEY] = "비가동 일정"
    app.run()
    assert not app.exception, app.exception
    assert AVAILABLE_EQUIPMENT_STATUS.path not in app.session_state[MARKS_BEFORE_KEY]
    tables = BrowserTables(app)
    tables.add(
        _small_key(app, DOWNTIME_EDITOR_KEY),
        {"설비명": "DA-01", "비가동유형": "PM", "시작일": "2026-11-03"},
    )
    tables.run()
    assert not app.exception, app.exception
    tables.run()
    assert app.session_state[LEAVE_BEFORE_KEY] == "가용설비 현황 · 비가동 일정"
    marks = app.session_state[MARKS_BEFORE_KEY]
    assert marks[AVAILABLE_EQUIPMENT_STATUS.path] == "적용 전 편집: 가용설비 현황 · 비가동 일정"
    dot = pending_tabs_style(EQUIPMENT_TAB_KEY, EQUIPMENT_TABS, {EQUIPMENT_MASTER_TAB}).strip()
    assert dot in [str(element.proto.body).strip() for element in app.get("html")]

    if away == "inner":
        app.segmented_control(key=TABLE_KEY).set_value("설비 마스터")
    else:
        app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    tables.run()
    assert not app.exception, app.exception

    # 바꾼 그 회차에 걷힌다 — 다음 조작을 기다리지 않는다.
    assert app.session_state[LEAVE_BEFORE_KEY] == ""
    assert AVAILABLE_EQUIPMENT_STATUS.path not in app.session_state[MARKS_BEFORE_KEY]
    assert dot not in [str(element.proto.body).strip() for element in app.get("html")]


def test_the_small_editors_are_not_inside_a_form(tmp_path: Path, grid: Calls) -> None:
    """작은 편집표 둘은 폼 밖이다(D11 — 적용 전 편집이 회차마다 서버에 와야 점·떠나기 확인이
    선다)."""
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    for table, key in (
        ("기존 보유대수", "equipment_baseline_editor_v3"),
        ("비가동 일정", DOWNTIME_EDITOR_KEY),
    ):
        app.session_state[TABLE_KEY] = table
        app.run()
        assert not app.exception, app.exception
        widget = _small_key(app, key)
        nodes = [
            node
            for node in app._tree
            if str(getattr(getattr(node, "proto", None), "id", "")).endswith(f"-{widget}")
        ]
        assert nodes, widget
        assert all(not getattr(node.proto, "form_id", "") for node in nodes)
        assert not app.get("form")


def test_a_delivered_toast_does_not_come_back_when_its_mount_returns(
    tmp_path: Path, grid: Calls
) -> None:
    """토스트는 마운트에 실어 보낸 뒤 그 마운트가 사라지면 거둔다 — 브라우저의 닫은 번호는
    마운트마다 새로 시작해 표 고르기·바깥 탭을 다녀오면 닫은 토스트가 되살아났다(리뷰 rs-b1y).
    마운트가 숨은 동안 쌓인 토스트(작은 편집표 적용이 비운 되돌리기 알림)는 처음 마운트할 때
    보인다."""
    from capa_simulation.navigation import EQUIPMENT_SUMMARY_TAB

    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    assert last(grid, emg.GRID_KEY)["toast"]["text"].startswith("붙여넣기로 1행을")
    app.session_state[TABLE_KEY] = "기존 보유대수"
    app.run()
    app.session_state[TABLE_KEY] = "설비 마스터"
    app.run()
    assert not app.exception, app.exception
    assert last(grid, emg.GRID_KEY)["toast"] is None

    send(app, emg.LOADER_KEY, "clear", {})
    assert last(grid, emg.GRID_KEY)["toast"]["text"].startswith("목록을 비웠습니다")
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.run()
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert last(grid, emg.GRID_KEY)["toast"] is None

    # 넣기가 남긴 되돌리기 단계 — 작은 편집표 적용(표 밖 길)이 비우며 표 토스트를 둔다. 표가 숨은
    # 동안 쌓였으므로 돌아온 첫 마운트에 보인다.
    app.session_state[TABLE_KEY] = "비가동 일정"
    app.run()
    tables = BrowserTables(app, forms=True)
    tables.add(
        _small_key(app, DOWNTIME_EDITOR_KEY),
        {"설비명": "DA-01", "비가동유형": "PM", "시작일": "2026-11-03"},
    )
    tables.run()
    app.button(key="equipment_downtime_apply_v1").click()
    tables.run()
    assert not app.exception, app.exception
    app.session_state[TABLE_KEY] = "설비 마스터"
    app.run()
    assert last(grid, emg.GRID_KEY)["toast"]["text"].startswith("표 밖에서 편집본을 바꿔")


def test_an_out_of_range_location_rejection_keeps_its_tildes(tmp_path: Path, grid: Calls) -> None:
    """범위 밖 동·층 거부 문구는 `st.error` 가 마크다운으로 그린다 — 물결표 둘이 취소선이 되지
    않게 `\\~` 로 막혀 그려진다(문구 바이트 자체는 규칙 시험이 고정한다)."""
    app = _app(tmp_path / "equipment.duckdb")
    frame = pd.read_csv(io.StringIO(_rows("DA-01")), sep="\t", dtype=str, keep_default_na=False)
    frame["동"] = "C9"
    frame["층"] = "1F"
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
    app.text_area(key=CLIPBOARD_KEY).set_value(frame.to_csv(sep="\t", index=False))
    app.button(key=PREVIEW_BUTTON_KEY).click().run()

    assert not app.exception, app.exception
    assert app.error
    assert "동은 C1\\~C5, 층은 1F\\~6F 범위여야 합니다" in app.error[0].value


def test_the_floor_column_narrows_by_building_where_only_the_pair_is_inactive(
    tmp_path: Path, grid: Calls
) -> None:
    """Space 층 비활성의 짝 단위 거름(D6·R2) — 「C1 3F」 만 꺼지면 층 칸 단위 선택지에는 3F 가 남고
    (다른 동은 사용), 층 칸 정의의 `optionsBy` 가 C1 에서 3F 를 뺀다. JS 가 그 줄의 동으로
    고른다."""
    database = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    assert repository.save_floor_states({("C1", "3F"): "UNUSED"}, expected_version=0, source="t")
    app = _app(database)
    _import(app, _rows("DA-01"))

    columns = {column["name"]: column for column in last(grid, emg.GRID_KEY)["columns"]}
    assert "3F" in columns["층"]["options"]
    by_building = columns["층"]["optionsBy"]["동"]
    assert by_building["C1"] == ["1F", "2F", "4F", "5F", "6F"]
    assert by_building["C2"] == ["1F", "2F", "3F", "4F", "5F", "6F"]
    assert "optionsBy" not in columns["동"]


def _memos(app: AppTest, name: str) -> list[str]:
    master = app.session_state[BUFFER_KEY][1].set_index("설비명")
    values = [master.loc[name, f"메모{k}"] for k in (1, 2, 3)]
    return ["" if pd.isna(value) else str(value) for value in values]


def _three_memo_edits(tmp_path: Path, grid: Calls) -> AppTest:
    """새 호기 DA-01 의 메모1·2·3 을 차례로 고치고 「저장 전 변경」 을 연 화면."""
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    for k, text in ((1, "t-1"), (2, "t-2"), (3, "t-3")):
        send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": f"메모{k}", "text": text})
    assert _memos(app, "DA-01") == ["t-1", "t-2", "t-3"]
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    return app


def test_a_double_press_on_one_step_undo_takes_back_only_the_last_step(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """메모1·2·3 을 차례로 고친 뒤 「한 단계 되돌리기」 를 더블클릭(0.15초)하면 메모3·메모2 가 함께
    돌아가고 알림은 「되돌림: 메모2 고침」 뿐이었다(2026-10-27 E2E 3/3). 둘째 누름이 첫 회차가
    단추를 다시 그리기 전의 옛 화면에 닿으면 같은 누름 세대를 싣는다 — 되돌리지도 알리지도
    않는다. 창이 지난 뒤 다시 그린 단추를 누르면 한 단계 더 되돌린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _three_memo_edits(tmp_path, grid)
    app.button(key=UNDO_BUTTON_KEY).click()
    pressed = app._tree.get_widget_states()

    _first_callback(app, monkeypatch, "_undo_step")
    _press_again(app, pressed)

    assert _memos(app, "DA-01") == ["t-1", "t-2", ""]
    assert app.session_state[GRID_TOAST_KEY]["changes"]["text"] == "되돌림: 메모3 고침"

    app.button(key=UNDO_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    assert _memos(app, "DA-01") == ["t-1", "", ""]
    assert app.session_state[GRID_TOAST_KEY]["changes"]["text"] == "되돌림: 메모2 고침"


@pytest.mark.parametrize(
    ("window", "memos"), [(3600.0, ["t-1", "t-2", ""]), (0.0, ["t-1", "", ""])]
)
def test_a_double_press_landing_on_the_redrawn_undo_is_still_one_step(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch, window: float, memos: list[str]
) -> None:
    """첫 회차가 단추를 다시 그린 뒤 닿은 둘째 누름은 세대가 같아 세대만으로는 일부러 누른 다음
    단계와 가를 수 없다 — 브라우저에서 0.15초 더블클릭 셋 중 둘이 이 꼴이었다(2026-10-27 E2E 사본
    재확인). 첫 되돌리기의 창(`TRAILING_PRESS_SECONDS`) 안 누름은 같은 더블클릭으로 본다 — 창이 0
    이면 옛 동작(두 단계)이다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    app = _three_memo_edits(tmp_path, grid)

    app.button(key=UNDO_BUTTON_KEY).click().run()
    app.button(key=UNDO_BUTTON_KEY).click().run()

    assert not app.exception, app.exception
    assert _memos(app, "DA-01") == memos
    assert app.session_state[GRID_TOAST_KEY]["changes"]["text"] == (
        "되돌림: 메모3 고침" if window else "되돌림: 메모2 고침"
    )
