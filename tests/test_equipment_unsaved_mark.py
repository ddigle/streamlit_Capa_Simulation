# Purpose: 설비 편집본이 저장본으로 돌아오면 미저장 표시가 걷히고 되돌리면 다시 서는지 본다.

"""머리 「변경 n」 칩 · 사이드바 「미저장 변경」 · 탭 점이 함께 보는 판정
(`has_unsaved_equipment_edits`).

새 호기를 넣었다 지우면 편집본은 저장본과 같은데 세대만 올라 표시가 남았다(2026-11-06 사용자 답).
저장할 내용이 없으면 표시가 없어야 하고, 되돌리기로 되살리면 다시 서야 하며, 저장본 호기를 지웠거나
다른 편집이 함께 있으면 그대로 남아야 한다. 표 대역(`tests/grid_fake.py`)이 브라우저가 보낼 출납을
보낸다. 판정은 회차 끝에 실제 함수로 읽어 세션 칸에 적는다 — 칩(`session_changes`)도 같이 적는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from grid_fake import Calls, grid_results, install_fake_grid, last, outbox, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    EQUIPMENT_DRAFT_KEY,
    GRID_LOADED_KEY,
    GRID_OVERLAY_KEY,
    NEW_UNIT_DRAFT_KEY,
    PENDING_CANVASES_KEY,
    PENDING_RENAMES_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_KEY,
    UNDO_BUTTON_KEY,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import equipment_grid as eg

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
OPERATIONS = "operations"
NEW_KEY = emg.side_key("new")
DETAIL_KEY = emg.side_key("detail")
UNSAVED = "test_unsaved_mark"
CHIPS = "test_change_chips"
CHIP_TOP = "설비 미저장"
# 회차 끝에 실제 판정을 적는다 — 세션 값으로 판정을 다시 쓰면 시험이 판정과 갈라진다.
_READ_MARKS = f"""
import streamlit as st
from capa_simulation.components.change_summary import session_changes
from capa_simulation.components.equipment_data_workspace import has_unsaved_equipment_edits

st.session_state[{UNSAVED!r}] = has_unsaved_equipment_edits()
st.session_state[{CHIPS!r}] = [item["top"] for item in session_changes(None, hrefs={{}})]
"""


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _page(repository: DuckDBEquipmentRepository, scenario_id: str = OPERATIONS) -> AppTest:
    clear_equipment_repository()
    app = AppTest.from_string(
        _page_script(PAGE, repository.database_path) + _READ_MARKS, default_timeout=90
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": scenario_id, "schedule_revision_id": None}
    return _ok(app.run())


def _assert_marked(app: AppTest, marked: bool) -> None:
    """표시 — 판정과 머리 칩이 함께 서고 함께 걷힌다."""
    assert app.session_state[UNSAVED] is marked
    assert (CHIP_TOP in app.session_state[CHIPS]) is marked


def _new_unit(name: str = "EQ-09") -> list[str]:
    values = eg.blank_draft()
    for column, text in (("설비명", name), ("공정소분류", "Process-A")):
        values[eg.COLUMN_INDEX[column]] = text
    return values


def _add(app: AppTest, grid: Calls, name: str = "EQ-09") -> None:
    """「+ 새 호기」 로 칸을 열고 「호기 추가」 — 초안 번호는 브라우저처럼 세션 초안 번호다."""
    _ok(send(app, emg.LOADER_KEY, "new", {}))
    session = (
        app.session_state[NEW_UNIT_DRAFT_KEY] if NEW_UNIT_DRAFT_KEY in app.session_state else {}
    )
    seq = max(5, int(session.get("seq", 0)))
    _ok(send_ops(app, grid, {"op": "add", "draftSeq": seq, "draft": _new_unit(name)}, key=NEW_KEY))


def _delete_from_detail(app: AppTest, grid: Calls, name: str = "EQ-09") -> None:
    """상세 칸 「이 호기 지우기」 — 결과는 알림창으로 간다."""
    delete = outbox(grid, {"op": "delete", "ids": [f"n:{name}"]}, mount="m-detail")
    _ok(send(app, DETAIL_KEY, "outbox", delete))
    assert grid_results(app)[-1] == "새 호기 1대 뺌"


def _undo(app: AppTest) -> None:
    """「저장 전 변경」 의 「한 단계 되돌리기」 를 누르고 상세 칸으로 돌아온다."""
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    _ok(app.button(key=UNDO_BUTTON_KEY).click().run())
    app.session_state[SIDE_KEY] = SIDE_DETAIL
    _ok(app.run())


def test_a_new_unit_added_then_deleted_leaves_no_mark_and_undo_brings_it_back(
    tmp_path: Path, grid: Calls
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    _assert_marked(app, False)

    _add(app, grid)
    _assert_marked(app, True)

    _delete_from_detail(app, grid)
    assert app.session_state[BUFFER_KEY][1].equals(app.session_state[EQUIPMENT_DRAFT_KEY])
    _assert_marked(app, False)

    _undo(app)
    assert app.session_state[GRID_LOADED_KEY][0] == "n:EQ-09"
    _assert_marked(app, True)

    _delete_from_detail(app, grid)
    _assert_marked(app, False)


def test_the_same_holds_in_an_assumption_scenario(tmp_path: Path, grid: Calls) -> None:
    """가정 설비 시나리오의 세션 저장본(공통 + 일정 합침)에서도 내용 대조가 맞는다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    _assert_marked(app, False)

    _add(app, grid)
    _assert_marked(app, True)
    _delete_from_detail(app, grid)
    _assert_marked(app, False)
    _undo(app)
    _assert_marked(app, True)


def test_undoing_the_add_itself_also_clears_the_mark(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    _add(app, grid)

    _undo(app)

    _assert_marked(app, False)


def test_clearing_the_mark_keeps_the_base_so_an_op_already_on_its_way_still_lands(
    tmp_path: Path, grid: Calls
) -> None:
    """표시만 걷는다 — 편집본 출발점(`base`)이 그대로라 표시가 걷히기 전에 보낸 op 를 버리지 않는다.

    `base` 는 남의 저장·내 저장·모두 버리기·시나리오 불러오기 때만 바뀌는 잣대다(`buffer_base`).
    「새 호기 뺌」 바로 뒤의 고침은 옛 화면의 `base` 를 들고 올 수 있다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    base = last(grid, emg.GRID_KEY)["base"]
    _add(app, grid)
    delete = outbox(grid, {"op": "delete", "ids": ["n:EQ-09"]}, mount="m-grid")
    _ok(send(app, emg.GRID_KEY, "outbox", delete))
    _assert_marked(app, False)
    assert last(grid, emg.GRID_KEY)["base"] == base

    late = {"seq": 10_000, "at": 10_000, "base": base, "op": "undo"}
    _ok(send(app, emg.GRID_KEY, "outbox", {"mount": "m-late", "ops": [late]}))

    assert "n:EQ-09" in [row["id"] for row in last(grid, emg.GRID_KEY)["rows"]]
    assert not [text for text in grid_results(app) if "반영하지 않았습니다" in text]
    _assert_marked(app, True)


def test_an_outbox_from_the_session_before_changes_nothing_and_says_nothing(
    tmp_path: Path, grid: Calls
) -> None:
    """끊긴 사이 낸 고침은 브라우저 출납에만 남아 새 세션에 닿는다. 저장본과 세대가 같아도 세션
    표지가 달라 편집본에 들어가지 않고, 그 손실은 재시작 · 세션 만료 알림이 이미 알렸으므로 또 세지
    않는다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    base = last(grid, emg.GRID_KEY)["base"]
    session, rest = base.split(":", 1)
    assert session and rest
    old = {"seq": 1, "at": 1, "base": f"앞세션:{rest}", "op": "undo"}
    _ok(send(app, emg.GRID_KEY, "outbox", {"mount": "m-before", "ops": [old]}))

    table = last(grid, emg.GRID_KEY)
    assert table["base"] == base
    assert table["ack"] == {"mount": "m-before", "seq": 1}
    assert not grid_results(app)
    _assert_marked(app, False)


def test_a_deleted_saved_unit_keeps_the_mark_until_it_comes_back(
    tmp_path: Path, grid: Calls
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    app.session_state[GRID_LOADED_KEY] = ("s:EQ-01",)
    _ok(send_ops(app, grid, {"op": "delete", "ids": ["s:EQ-01"]}))
    _assert_marked(app, True)

    # 저장본 호기를 지운 채 새 호기를 넣었다 지워도 지운 호기가 남아 있다.
    _add(app, grid)
    _delete_from_detail(app, grid)
    _assert_marked(app, True)

    _ok(send_ops(app, grid, {"op": "restore", "ids": ["s:EQ-01"]}))
    assert app.session_state[BUFFER_KEY][1].equals(app.session_state[EQUIPMENT_DRAFT_KEY])
    _assert_marked(app, False)


@pytest.mark.parametrize(
    ("other", "state_key"),
    (
        ({"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "담당Z"}, None),
        ({"op": "cell", "id": "s:EQ-01", "col": "Qual일정", "text": "언젠가"}, GRID_OVERLAY_KEY),
        ({"op": "cell", "id": "s:EQ-01", "col": "설비명", "text": "EQ-77"}, PENDING_RENAMES_KEY),
    ),
    ids=("고친 칸", "못 읽은 칸 초안", "이름 바꿈"),
)
def test_another_edit_keeps_the_mark_when_a_new_unit_goes_back_out(
    tmp_path: Path, grid: Calls, other: dict[str, Any], state_key: str | None
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    _ok(send_ops(app, grid, other))
    if state_key is not None:
        assert state_key in app.session_state

    _add(app, grid)
    _delete_from_detail(app, grid)

    _assert_marked(app, True)


def test_a_pending_floor_layout_keeps_the_mark_when_a_new_unit_goes_back_out(
    tmp_path: Path, grid: Calls
) -> None:
    """층 대기분은 편집본 표 밖이라 표만 대면 저장본과 같아 보인다 — 저장할 것이 남아 있다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    app.session_state[PENDING_CANVASES_KEY] = {("C1", "1F"): (120.0, 80.0)}
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    _ok(app.run())
    _assert_marked(app, True)

    _add(app, grid)
    _delete_from_detail(app, grid)

    _assert_marked(app, True)


@pytest.mark.parametrize(
    "back",
    ({"op": "undo"}, {"op": "revert", "id": "s:EQ-01", "col": "담당자"}),
    ids=("한 단계 되돌리기", "칸 되돌리기"),
)
def test_an_edit_taken_back_clears_the_mark(
    tmp_path: Path, grid: Calls, back: dict[str, Any]
) -> None:
    """새 호기만이 아니다 — 고친 칸을 되돌려 저장할 내용이 없어져도 표시가 걷힌다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository)
    _ok(send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "담당Z"}))
    _assert_marked(app, True)

    _ok(send_ops(app, grid, back))

    _assert_marked(app, False)


def _rename_and_back(database: str) -> None:
    """Space 적용의 차례(편집본 → 이름 지도) — 이름을 바꿨다가 옛 이름으로 되돌린다."""
    from pathlib import Path as _Path

    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        has_unsaved_equipment_edits,
        replace_equipment_buffer,
        stage_unit_renames,
    )
    from capa_simulation.persistence.equipment_repository import (
        DuckDBEquipmentRepository as _Repository,
    )
    from capa_simulation.services.space_layout_edit import PendingRenames

    repository = _Repository(_Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    frames = ensure_equipment_drafts(latest)
    step = st.session_state.get("step", 0)
    st.session_state["step"] = step + 1
    st.session_state.setdefault("marks", []).append(has_unsaved_equipment_edits())
    if step == 0:
        renamed = frames[1].copy()
        renamed.loc[renamed["설비명"].eq("EQ-01"), "설비명"] = "EQ-77"
        replace_equipment_buffer((frames[0], renamed, frames[2]))
        stage_unit_renames(PendingRenames(units={"EQ-77": "EQ-01"}))
    elif step == 1:
        replace_equipment_buffer((frames[0], latest.equipment.copy(), frames[2]))
        stage_unit_renames(PendingRenames())


def test_a_rename_taken_back_after_the_buffer_clears_the_mark(tmp_path: Path) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _rename_and_back, args=(str(repository.database_path),), default_timeout=60
    )
    _ok(app.run())
    _ok(app.run())
    _ok(app.run())

    assert app.session_state["marks"] == [False, True, False]


def _small_paths(database: str) -> None:
    """표 밖의 길(Space 적용 · 작은 편집표 · 엑셀 넣기) — 고쳤다가 저장본 값으로 다시 넣는다."""
    from pathlib import Path as _Path

    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        has_unsaved_equipment_edits,
        replace_equipment_buffer,
    )
    from capa_simulation.persistence.equipment_repository import (
        DuckDBEquipmentRepository as _Repository,
    )

    repository = _Repository(_Path(database))
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    frames = ensure_equipment_drafts(latest)
    step = st.session_state.get("step", 0)
    st.session_state["step"] = step + 1
    st.session_state.setdefault("marks", []).append(has_unsaved_equipment_edits())
    if step == 0:
        moved = frames[1].copy()
        moved.loc[moved["설비명"].eq("EQ-01"), "X좌표"] = 55.0
        replace_equipment_buffer((frames[0], moved, frames[2]))
    elif step == 1:
        replace_equipment_buffer((frames[0], latest.equipment.copy(), frames[2]))


def test_another_path_that_puts_the_saved_values_back_clears_the_mark(tmp_path: Path) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _small_paths, args=(str(repository.database_path),), default_timeout=60
    )
    _ok(app.run())
    _ok(app.run())
    _ok(app.run())

    assert app.session_state["marks"] == [False, True, False]
