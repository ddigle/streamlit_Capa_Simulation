# Purpose: 설비 편집본·FAB 배치 저장의 더블클릭이 제 저장을 남의 저장으로 알리지 않는지 본다.

"""설비 마스터 「리비전 저장」·Space 「배치 저장」 의 더블클릭(2026-10-26 E2E).

Streamlit 1.63 은 둘째 누름이 닿으면(`runner.fastReruns`) 돌던 회차에 멈춤을 걸고 새 회차를
세운다. 첫 콜백은 DB 에 쓴 뒤 다음 세션 칸 접근에서 끊겨 편집본을 비우지 못하고, 둘째 콜백은 옛
출발점으로 다시 저장하다 저장소에 거부되어 「다른 사용자가 먼저 … 저장해 저장하지 않았습니다」 를
알렸다(리비전은 한 건이었다). 같은 출발점의 둘째 누름은 저장하지 않고 첫 결과로 뒷정리·알림을
잇는다(`write_guard.save_once`). 시험은 첫 콜백이 쓴 바로 뒤에 둘째 회차를 다른 스레드에서
세운다 — `tests/test_voc_page.py` 의 `_race` 와 같은 모양이다.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from grid_fake import Calls, install_fake_grid, send_ops
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.runtime.state import session_state_proxy
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import _app as _master_app
from test_equipment_master_tab import _import, _rows
from test_space_layout_editor_page import _open_editor
from test_space_module_group_save import _edit_rawdata

from capa_simulation.components.equipment_data_workspace import BUFFER_KEY
from capa_simulation.components.equipment_master_tab import SAVE_BUTTON_KEY, SIDE_CHANGES, SIDE_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _race_save(app: AppTest, monkeypatch: pytest.MonkeyPatch, *, callback: str) -> None:
    """누른 화면의 같은 저장 누름 둘이 두 회차에서 겹쳐 온다 — 첫 콜백(`callback` 이름의 위젯
    콜백)이 저장소에 **쓴 바로 뒤** 둘째 누름이 닿는다. 첫 회차에 멈춤을 걸고 둘째 회차
    (`app._run`)를 다른 스레드에서 세워 1초 기다린 뒤 첫 콜백을 잇는다 — 멈춤을 받은 첫 콜백은 다음
    세션 칸 접근에서 `StopException` 으로 끊긴다(브라우저에서 잰 모양 그대로)."""
    pressed = app._tree.get_widget_states()
    shared = app.session_state._state
    metadata = next(
        meta
        for meta in shared._new_widget_state.widget_metadata.values()
        if getattr(meta.callback, "__name__", None) == callback
    )
    pressed_callback = metadata.callback
    assert pressed_callback is not None
    stopped = threading.Event()

    def first_yield() -> None:
        if stopped.is_set():
            raise StopException()

    first_state = SafeSessionState(shared, first_yield)
    local = threading.local()
    original_state = session_state_proxy.get_session_state

    def thread_state() -> SafeSessionState:
        state = getattr(local, "state", None)
        return state if isinstance(state, SafeSessionState) else original_state()

    monkeypatch.setattr(session_state_proxy, "get_session_state", thread_state)
    second = threading.Thread(target=lambda: app._run(widget_state=pressed))
    original_save = DuckDBEquipmentRepository.save_equipment
    arrived: list[int] = []

    def racing(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        result = original_save(self, *args, **kwargs)
        if not arrived:
            arrived.append(1)
            stopped.set()
            second.start()
            second.join(timeout=1.0)
        return result

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_equipment", racing)
    local.state = first_state
    try:
        pressed_callback(*(metadata.callback_args or ()), **(metadata.callback_kwargs or {}))
    except StopException:
        pass
    finally:
        del local.state
    second.join(timeout=60)
    assert arrived and not second.is_alive()


def _texts(app: AppTest) -> list[str]:
    alerts = (*app.error, *app.warning, *app.info, *app.success)
    return [str(item.value) for item in alerts]


def test_a_double_click_on_the_revision_save_reports_its_own_save(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _master_app(database)
    _import(app, _rows("DA-01", "DA-02"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1
    send_ops(app, grid, {"op": "cell", "id": "s:DA-01", "col": "메모1", "text": "더블클릭"})
    app.button(key=SAVE_BUTTON_KEY).click()

    _race_save(app, monkeypatch, callback="_save_revision")

    assert not app.exception, [item.message for item in app.exception]
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    saved = repository.load_snapshot(revisions[0].revision_id).equipment
    assert saved.loc[saved["설비명"].eq("DA-01"), "메모1"].tolist() == ["더블클릭"]
    texts = _texts(app)
    assert not [text for text in texts if "다른 사용자" in text], texts
    assert any("설비 데이터를 저장했습니다" in text for text in texts), texts
    master = app.session_state[BUFFER_KEY][1]
    assert master.loc[master["설비명"].eq("DA-01"), "메모1"].tolist() == ["더블클릭"]


def test_a_double_click_on_the_space_layout_save_reports_its_own_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, database = _open_editor(tmp_path)
    master = app.session_state[BUFFER_KEY][1].copy()
    master.loc[master["설비명"].eq("EQ-01"), "X좌표"] = 21.0
    _edit_rawdata(app, master)
    app.button(key="space_layout_save").click()

    _race_save(app, monkeypatch, callback="_save_space_layout")

    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    saved = repository.load_snapshot(revisions[0].revision_id).equipment
    assert saved.loc[saved["설비명"].eq("EQ-01"), "X좌표"].tolist() == [21.0]
    texts = _texts(app)
    assert not [text for text in texts if "다른 사용자" in text or "저장하지 못" in text], texts
    assert any("설비 데이터를 저장했습니다" in text for text in texts), texts


def _fab_saved_twice_from_the_same_pending(database: str) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        PENDING_FAB_KEY,
        save_pending_fab_layout,
        stage_fab_layout,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.fab_layout import fab_marks_fingerprint, prepare_fab_layout_marks

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    stage_fab_layout(
        None,
        prepare_fab_layout_marks(
            [{"id": "B", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}],
            (101.0, 62.0),
        ),
        base=(None, fab_marks_fingerprint(())),
    )
    pending = st.session_state[PENDING_FAB_KEY]
    first = save_pending_fab_layout(repository)
    # 첫 콜백이 쓴 뒤 대기분을 비우기 전에 끊겼다 — 둘째 누름은 같은 대기분을 다시 본다.
    st.session_state[PENDING_FAB_KEY] = pending
    try:
        st.session_state["second"] = save_pending_fab_layout(repository)
    except ValueError as exc:
        st.session_state["second"] = str(exc)
    st.session_state["first"] = first
    st.session_state["pending_left"] = PENDING_FAB_KEY in st.session_state


def test_a_second_press_of_the_same_fab_pending_does_not_report_a_conflict(
    tmp_path: Path,
) -> None:
    """FAB 전체 배치도 같은 꼴이다 — 첫 콜백이 쓴 뒤 대기분을 비우기 전에 끊기면 둘째 누름이 옛 본
    저장값으로 다시 써 「다른 사용자가 먼저」 로 거부되었다. 같은 대기분은 다시 쓰지 않는다."""
    database = tmp_path / "fab_twice.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    app = AppTest.from_function(
        _fab_saved_twice_from_the_same_pending, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["first"] is True
    assert app.session_state["second"] is True
    assert app.session_state["pending_left"] is False
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["B"]


def _press_again_from_the_old_screen(
    app: AppTest, monkeypatch: pytest.MonkeyPatch, *, callback: str
) -> None:
    """누른 화면의 같은 저장 누름 둘 — 첫 콜백(`callback` 이름의 위젯 콜백)이 **끝까지** 돈 뒤(쓰기·
    뒷정리·알림 담기) 둘째 누름이 옛 화면의 단추로 닿는다. 첫 콜백 뒤 회차가 화면을 다 그리기 전에
    닿은 누름이라 그 단추의 콜백 인자는 옛 화면 것이다(0.15~0.5초 간격, 2026-10-27 E2E). 첫 콜백을
    회차 밖에서 부르고, 둘째 누름의 회차(`app._run`)가 콜백을 다시 부른 뒤 화면을 그린다."""
    pressed = app._tree.get_widget_states()
    shared = app.session_state._state
    metadata = next(
        meta
        for meta in shared._new_widget_state.widget_metadata.values()
        if getattr(meta.callback, "__name__", None) == callback
    )
    pressed_callback = metadata.callback
    assert pressed_callback is not None
    first_state = SafeSessionState(shared, lambda: None)
    with monkeypatch.context() as patch:
        patch.setattr(session_state_proxy, "get_session_state", lambda: first_state)
        pressed_callback(*(metadata.callback_args or ()), **(metadata.callback_kwargs or {}))
    app._run(widget_state=pressed)


def test_a_space_layout_save_pressed_again_from_the_old_screen_keeps_its_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 콜백이 저장·뒷정리를 마친 뒤 옛 화면의 「배치 저장」 이 한 번 더 닿아도 다시 저장하지 않고
    성공 알림만 남는다 — 그린 회차의 저장 세대(변경 메모 칸 번호)가 지금과 다르면 옛 화면의 누름이다
    (AGENTS 9장 쓰기 단추 세대)."""
    app, database = _open_editor(tmp_path)
    master = app.session_state[BUFFER_KEY][1].copy()
    master.loc[master["설비명"].eq("EQ-01"), "X좌표"] = 21.0
    _edit_rawdata(app, master)
    app.button(key="space_layout_save").click()

    _press_again_from_the_old_screen(app, monkeypatch, callback="_save_space_layout")

    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 2
    texts = _texts(app)
    assert not [text for text in texts if "저장하지 못" in text or "바뀐 내용이 없어" in text], (
        texts
    )
    assert any("설비 데이터를 저장했습니다" in text for text in texts), texts


def _fab_saved_then_pressed_again(database: str) -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        save_equipment_buffer,
        stage_fab_layout,
    )
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.fab_layout import fab_marks_fingerprint, prepare_fab_layout_marks

    repository = DuckDBEquipmentRepository(__import__("pathlib").Path(database))
    stage_fab_layout(
        None,
        prepare_fab_layout_marks(
            [{"id": "B", "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}],
            (101.0, 62.0),
        ),
        base=(None, fab_marks_fingerprint(())),
    )
    # 설비 저장본이 없는 화면(`frames` None)의 저장 — 첫 누름이 끝까지 돌아 대기분을 비운 뒤
    # 둘째 누름.
    st.session_state["first"] = save_equipment_buffer(repository, None, "")
    st.session_state["second"] = save_equipment_buffer(repository, None, "")


def test_a_fab_save_pressed_again_after_it_finished_repeats_its_success(tmp_path: Path) -> None:
    """FAB 대기분만 저장한 첫 누름이 대기분을 비운 뒤 닿은 둘째 누름은 「바뀐 내용이 없어 …」 로 첫
    성공 알림을 덮었다(2026-10-27 E2E). 창(`TRAILING_PRESS_SECONDS`) 안이면 첫 성공을 다시 낸다 —
    설비 마스터 탭·사이드바 팝업 저장도 같은 함수를 지난다."""
    from capa_simulation.components.equipment_data_workspace import FAB_SAVED_MESSAGE

    database = tmp_path / "fab_again.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    app = AppTest.from_function(
        _fab_saved_then_pressed_again, args=(str(database),), default_timeout=30
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["first"] == FAB_SAVED_MESSAGE
    assert app.session_state["second"] == FAB_SAVED_MESSAGE
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["B"]
