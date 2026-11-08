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
import streamlit as st
from alert_marks import alert_notes
from grid_fake import Calls, grid_results, install_fake_grid, last, outbox, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _request, _session, _set

from capa_simulation import alerts
from capa_simulation.components import equipment_data_workspace as workspace
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
    SAVE_BUTTON_KEY,
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


# ------------------------------------------------------------------ 남의 저장이 버린 편집과 앱 머리

HEAD = "test_head_marks"
RUNS = "test_head_runs"
SPACE_PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
EQUIPMENT_PAGE_FILE = "available_equipment_status.py"


def _head_probe(page_file: str) -> str:
    """앱 머리(변경 칩 · 화면 탭 점)처럼 페이지 본문보다 **먼저** 세는 자리 — 마지막 회차가 본 값과
    돈 회차 수를 적는다."""
    return f"""
import streamlit as st
from capa_simulation.components.change_summary import session_changes as _changes
from capa_simulation.components.page_tabs import page_unsaved_marks as _dots

st.session_state[{HEAD!r}] = (
    [item["top"] for item in _changes({page_file!r}, hrefs={{}})],
    sorted(_dots({page_file!r})),
)
st.session_state[{RUNS!r}] = st.session_state.get({RUNS!r}, 0) + 1
"""


def _head_page(repository: DuckDBEquipmentRepository) -> AppTest:
    """머리를 먼저 세는 가용설비 현황 탭 ① — 공식 「운영 일정」 세션, 「저장 전 변경」 칸."""
    clear_equipment_repository()
    app = AppTest.from_string(
        _head_probe(EQUIPMENT_PAGE_FILE)
        + _page_script(PAGE, repository.database_path)
        + _READ_MARKS,
        default_timeout=90,
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": OPERATIONS, "schedule_revision_id": None}
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    return _ok(app.run())


def _their_common_save(repository: DuckDBEquipmentRepository) -> None:
    """다른 세션이 공통 대장을 저장한다(EQ-02 담당자)."""
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "담당자", "남의 담당"))
    )
    clear_equipment_repository()


def _head_counts_my_edit(
    app: AppTest, grid: Calls, column: str = "담당자", text: str = "담당Z"
) -> None:
    _ok(send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": column, "text": text}))
    chips, dots = app.session_state[HEAD]
    assert CHIP_TOP in chips and dots, app.session_state[HEAD]


def _discard_warnings(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.warning if "버리고" in str(item.value)]


def _discard_events(app: AppTest) -> list[dict[str, Any]]:
    """마지막 회차 표지에 실린 버림 사건 알림(`EQ-05` — 다시 보낸 것 포함). 다시 돈 회차도 같은 id
    로 보내야 브라우저가 놓치지 않는다 — 다시 돌기 전 회차의 표지는 브라우저가 훑기 전에 다음
    회차가 덮을 수 있다(사본 앱 확인: 탭만 옮긴 회차에 알림창 · Alarm 에서 빠졌다)."""
    return [note for note in alert_notes(app, again=True) if note.get("code") == "EQ-05"]


def test_the_head_drops_an_edit_another_users_save_threw_away_in_the_same_run(
    tmp_path: Path, grid: Calls
) -> None:
    """남의 저장으로 본문이 편집본을 다시 세우며 내 편집을 버리면, 앱 머리는 이미 그 편집을 센 채
    그렸다 — 다음 조작을 기다리지 않고 그 회차에 한 번 다시 돌아 칩 · 탭 점을 걷는다(UI-DAT-11).
    버림 알림은 그대로 서고, 다시 돈 회차는 되풀이되지 않는다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _head_page(repository)
    _head_counts_my_edit(app, grid)
    _their_common_save(repository)
    runs = app.session_state[RUNS]

    _ok(app.run())

    _assert_marked(app, False)
    assert app.session_state[HEAD] == ([], [])
    assert app.session_state[RUNS] == runs + 2
    assert len(_discard_warnings(app)) == 1
    assert len(_discard_events(app)) == 1

    _ok(app.run())
    assert app.session_state[RUNS] == runs + 3
    assert not _discard_events(app)


def test_a_save_refused_by_another_users_common_save_keeps_its_refusal_after_the_head_run(
    tmp_path: Path, grid: Calls
) -> None:
    """「리비전 저장」 이 남의 공통 저장에 거부된 회차 — 본문이 편집을 버려 머리를 다시 그리려 한 번
    더 돈다. 그 회차가 거부 글을 꺼내 보낸 뒤 다시 돌면 곁 글이 사라지므로, 거부 글은 다시 돈 회차가
    한 번 그리고 한 번 보낸다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _head_page(repository)
    _head_counts_my_edit(app, grid)
    _their_common_save(repository)
    runs = app.session_state[RUNS]
    sent: list[str] = []
    remember_sent = alerts.remember_sent

    def spy(key: str, note: alerts.AlertNote) -> None:
        if "저장하지 않았습니다" in str(note.get("full")):
            sent.append(str(note.get("id")))
        remember_sent(key, note)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(alerts, "remember_sent", spy)
        app.button(key=SAVE_BUTTON_KEY).click()
        _ok(app.run())

    assert app.session_state[HEAD] == ([], [])
    assert app.session_state[RUNS] == runs + 2
    refusals = [str(item.value) for item in app.error if "저장하지 않았습니다" in str(item.value)]
    assert len(refusals) == 1, refusals
    # 편집이 모두 버려졌다 — 「남은 편집을 확인」 하라고 하지 않는다(있지도 않은 편집을 찾는다).
    assert "남은 편집" not in refusals[0]
    assert refusals[0].endswith("최신 저장본을 확인한 뒤 다시 고쳐 저장하세요."), refusals
    assert len(sent) == 1, sent
    assert len(_discard_warnings(app)) == 1
    assert len(_discard_events(app)) == 1


def test_a_refusal_survives_a_second_press_that_cuts_the_head_run_before_it_draws(
    tmp_path: Path, grid: Calls
) -> None:
    """거부된 「리비전 저장」 을 곧 한 번 더 누르면 둘째 누름이 다시 도는 회차를 거부를 그리기 전에
    끊을 수 있다 — 그 누름의 결과(「고친 것이 없습니다」)가 결과 칸에 담긴다. 비켜 둔 거부는 그 칸이
    아닌 곳으로 되돌려 둘째 누름의 회차가 결과와 함께 그리고 한 번 보낸다(사본 앱 두 세션 확인 —
    결과 칸으로 되돌리면 곁 글 · 알림창 · Alarm 어디에도 남지 않았다)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _head_page(repository)
    _head_counts_my_edit(app, grid)
    _their_common_save(repository)
    sent: list[str] = []
    remember_sent = alerts.remember_sent

    def spy(key: str, note: alerts.AlertNote) -> None:
        if "저장하지 않았습니다" in str(note.get("full")):
            sent.append(str(note.get("id")))
        remember_sent(key, note)

    def cut_before_drawing() -> None:
        # 다시 도는 회차가 칸을 그리기 전에 끊긴 꼴 — 표지만 걷고 비켜 둔 것을 되돌린다.
        if st.session_state.pop(workspace.HEAD_STALE_KEY, None) is True:
            workspace._release_head_hold()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(alerts, "remember_sent", spy)
        patch.setattr(workspace, "rerun_if_head_stale", cut_before_drawing)
        app.button(key=SAVE_BUTTON_KEY).click()
        _ok(app.run())
        app.button(key=SAVE_BUTTON_KEY).click()
        _ok(app.run())

    refusals = [str(item.value) for item in app.error if "저장하지 않았습니다" in str(item.value)]
    assert len(refusals) == 1, [str(item.value) for item in app.error]
    assert len(sent) == 1, sent
    flashes = [(note["code"], note["full"]) for note in alert_notes(app) if note.get("flash")]
    assert [code for code, _ in flashes] == [
        alerts.FLASH_CODES["error"],
        alerts.FLASH_CODES["info"],
    ]
    assert "저장하지 않았습니다" in flashes[0][1]
    assert flashes[1][1] == "고친 것이 없습니다"


def test_a_reopen_without_lost_edits_does_not_spend_one_more_run(
    tmp_path: Path, grid: Calls
) -> None:
    """버린 편집이 없으면 머리가 이미 맞다 — 남의 저장으로 다시 세운 회차도 한 번만 돈다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _head_page(repository)
    _their_common_save(repository)
    runs = app.session_state[RUNS]

    _ok(app.run())

    assert app.session_state[RUNS] == runs + 1
    assert app.session_state[HEAD] == ([], [])


_ROUTER = """
from pathlib import Path
import streamlit as st
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({database!r})
settings.DUCKDB_PATH = Path({simulation!r})
page = {space!r} if st.session_state.get("test_page") == "space" else {equipment!r}
exec(compile(Path(page).read_text(encoding="utf-8"), page, "exec"), {{"__name__": "__main__"}})
"""


def test_space_drops_the_head_marks_too_when_it_reopens_the_buffer(
    tmp_path: Path, grid: Calls
) -> None:
    """Space 현황도 같은 편집본을 세운다 — 설비 마스터에서 고친 뒤 남이 저장하고 Space 로 옮기면 그
    화면이 편집을 버리고, 머리를 다시 그리려 한 번 더 돈다."""
    repository, _ = _two_scenarios(tmp_path)
    database = repository.database_path
    clear_equipment_repository()
    app = AppTest.from_string(
        _head_probe("space_status.py")
        + _ROUTER.format(
            database=str(database),
            simulation=str(database.with_name(f"{database.stem}_simulation.duckdb")),
            space=str(SPACE_PAGE),
            equipment=str(PAGE),
        )
        + _READ_MARKS,
        default_timeout=90,
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": OPERATIONS, "schedule_revision_id": None}
    _ok(app.run())
    _head_counts_my_edit(app, grid)
    _their_common_save(repository)
    app.session_state["test_page"] = "space"
    runs = app.session_state[RUNS]

    _ok(app.run())

    _assert_marked(app, False)
    assert app.session_state[HEAD] == ([], [])
    assert app.session_state[RUNS] == runs + 2
    assert len(_discard_warnings(app)) == 1
    assert len(_discard_events(app)) == 1


def test_a_space_save_refused_by_another_users_common_save_keeps_its_refusal_after_the_head_run(
    tmp_path: Path, grid: Calls
) -> None:
    """Space 「배치 저장」 도 같다 — 남의 공통 저장에 거부되고 본문이 편집을 버려 한 번 더 돌면,
    거부 글은 다시 돈 회차가 그린다(앞 회차가 꺼내 그리면 다시 돈 회차에 사라진다)."""
    repository, _ = _two_scenarios(tmp_path)
    database = repository.database_path
    clear_equipment_repository()
    app = AppTest.from_string(
        _head_probe("space_status.py")
        + _ROUTER.format(
            database=str(database),
            simulation=str(database.with_name(f"{database.stem}_simulation.duckdb")),
            space=str(SPACE_PAGE),
            equipment=str(PAGE),
        )
        + _READ_MARKS,
        default_timeout=90,
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": OPERATIONS, "schedule_revision_id": None}
    _ok(app.run())
    # 공식 배치 편집 — 남의 공통 저장 뒤에 다시 얹지 않는다(가정 배치만 다시 얹는다).
    _head_counts_my_edit(app, grid, "X좌표", "55")
    app.session_state["test_page"] = "space"
    _ok(app.run())
    _their_common_save(repository)
    runs = app.session_state[RUNS]

    app.button(key="space_layout_save").click()
    _ok(app.run())

    assert app.session_state[HEAD] == ([], [])
    assert app.session_state[RUNS] == runs + 2
    refusals = [str(item.value) for item in app.error if "저장하지 않았습니다" in str(item.value)]
    assert len(refusals) == 1, [str(item.value) for item in app.error]
    assert len(_discard_events(app)) == 1
