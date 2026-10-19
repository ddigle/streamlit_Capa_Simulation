# Purpose: 필요 단축 일정 본문 프래그먼트의 이벤트 칸 자리 수와 기준선 알림이 설 자리를 검사한다.

"""필요 단축 일정 머리·본문 프래그먼트(`_render_view`)가 이벤트 칸(본문 밖 최상위 칸)에 쓰는 것.

프래그먼트만 도는 회차는 이벤트 칸 쓰기 위치를 앱 전체 회차에서 그 프래그먼트를 부른
자리로 되돌리고, 브라우저는 받은 자리의 요소만 갈아 끼운다(남은 자리는 그대로 둔다).
그래서 이 프래그먼트는 갈래(일반 보기·진척 비교·알림 있음/없음)와 상관없이 **같은
자리만** 쓴다 — 서식은 본문 `st.html` 에 싣고, 알림은 `_NOTICE_SLOTS` 자리를 늘 쓴다.

브라우저(Streamlit 1.63)는 토스트를 그 자리(`delta_path`)로 가려, 같은 자리의 토스트가
아직 떠 있으면 새 토스트를 띄우지 않는다. 그래서 잇단 알림은 다른 자리에 서야 한다.
그리기 전에 콜백이 둘 돌면 두 알림을 한 토스트에 모두 적는다(같은 폼·같은 기준선의 두 번 누름은
콜백이 먼저 거르고, 이것은 그 밖의 조합을 위한 예비다).

진짜 프래그먼트 회차는 `tests/fragment_browser.py` 대역으로 돌린다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from fragment_browser import FragmentBrowser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_shortening_progress_tab import _name_input, _save_button, _saved_database
from test_shortening_view_fragment import _fragment_of, _install, _open, _run, _runner

import capa_simulation.components.shortening_progress_panel as progress
from capa_simulation.components.required_shortening_panel import SHORTENING_LEVEL_KEY
from capa_simulation.components.shortening_progress_panel import SHORTENING_COMPARE_KEY
from capa_simulation.navigation import EQUIPMENT_MAIN_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


def _event_slots(messages: Sequence[ForwardMsg], fragment_id: str) -> dict[int, tuple[str, str]]:
    """그 프래그먼트가 이벤트 칸 최상위의 몇째 자리에 무엇을 썼나 — `(종류, 글)`."""
    slots: dict[int, tuple[str, str]] = {}
    for message in messages:
        if message.WhichOneof("type") != "delta" or message.delta.fragment_id != fragment_id:
            continue
        path = list(message.metadata.delta_path)
        if len(path) != 2 or path[0] != RootContainer.EVENT:
            continue
        element = message.delta.new_element
        kind = str(element.WhichOneof("type"))
        if kind == "toast":
            body = element.toast.body
        elif kind == "html":
            body = element.html.body
        else:
            body = ""
        slots[path[1]] = (kind, body)
    return slots


def _toast_slots(slots: dict[int, tuple[str, str]]) -> list[int]:
    return [index for index, (kind, _) in slots.items() if kind == "toast"]


def _view(runner: FragmentBrowser) -> str:
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    assert view, "목표 확보율은 프래그먼트 안이다"
    return view


def test_the_view_writes_the_same_event_slots_in_every_branch(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 전체 회차·목표·저장 성공·같은 이름 거절·진척 비교 어느 회차든 같은 이벤트 칸
    자리를 쓰고, 잇단 알림 토스트는 다른 자리에 선다."""
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    view = _view(runner)
    full = _event_slots(runner.messages, view)
    assert full and all(slot == ("html", "<style></style>") for slot in full.values()), full

    runner.fragment_queue = [view]
    _run(app, world, lambda app: app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(0.9))
    assert runner.started == [[view]]
    assert _event_slots(runner.messages, view) == full

    # 저장 성공 — 프래그먼트 회차가 앱 전체 회차로 바뀌고 알림 토스트가 한 자리에 선다.
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view], []]
    saved = _event_slots(runner.messages, view)
    assert set(saved) == set(full)
    (first,) = _toast_slots(saved)
    assert "기준선을 저장했습니다" in saved[first][1]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    # 곧바로 같은 이름 — 거절 알림은 프래그먼트 회차에서 **다른 자리**에 선다(앞 토스트가
    # 떠 있어도 보인다).
    view = _view(runner)
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _name_input(app).set_value(stored.name))
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view]]
    rejected = _event_slots(runner.messages, view)
    assert set(rejected) == set(full)
    (second,) = _toast_slots(rejected)
    assert second != first and "같은 이름" in rejected[second][1]

    # 진척 비교(서식이 둘인 갈래)도 같은 자리만 쓴다 — 서식은 본문 `st.html` 에 실린다.
    runner.fragment_queue = [view]
    _run(
        app,
        world,
        lambda app: app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id),
    )
    assert runner.started == [[view]]
    assert _event_slots(runner.messages, view) == full
    bodies = [str(element.proto.body) for element in app.get("html")]
    assert any(".shk-prog-summary" in body and "진척 비교 요약" in body for body in bodies)
    clear_equipment_repository()


def test_two_callbacks_before_one_draw_report_both_notices() -> None:
    """그리기 전에 콜백이 둘 돌아 알림 둘을 남기면 한 토스트에 모두 적는다 — 한 칸에 덮어
    적으면 앞 알림(저장 성공)은 사라지고 뒤 알림만 보인다."""

    def script() -> None:
        from capa_simulation.components import shortening_progress_panel as progress

        progress._notice("success", "기준선을 저장했습니다 — 「A」.")
        progress._notice("warning", "기준선을 저장하지 않았습니다 — 같은 이름: A")
        progress.render_baseline_notice()

    app = AppTest.from_function(script).run()
    assert not list(app.exception), [element.message for element in app.exception]
    (toast,) = app.toast
    assert "저장했습니다" in str(toast.value) and "같은 이름" in str(toast.value)


def _written_event_slots(messages: Sequence[ForwardMsg]) -> set[int]:
    """그 회차가 이벤트 칸 최상위에 쓴 자리 — 어느 프래그먼트 것이든."""
    return {
        message.metadata.delta_path[1]
        for message in messages
        if message.WhichOneof("type") == "delta"
        and len(message.metadata.delta_path) == 2
        and message.metadata.delta_path[0] == RootContainer.EVENT
    }


def test_a_full_run_with_the_tab_hidden_still_fills_the_notice_slots(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 탭을 연 앱 전체 회차도 알림 자리를 모두 쓴다 — 비워 두면 브라우저가 그 자리의
    자리표시자는 지우고 토스트는 남겨, 둘째·셋째 자리의 토스트가 앞으로 당겨져 다시 뜬다."""
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    slots = set(_event_slots(runner.messages, _view(runner)))
    assert len(slots) == progress._NOTICE_SLOTS

    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MAIN_TAB
    _run(app, world)
    assert runner.started == [[]]
    assert slots <= _written_event_slots(runner.messages)
    clear_equipment_repository()


def test_a_notice_takes_the_first_slot_unless_its_toast_is_still_showing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """알림은 첫 자리에 서고, 앞 토스트가 떠 있는 동안에만 다음 자리로 비킨다. 셋 다 떠 있으면
    가장 오래된 자리를 쓴다(그 토스트가 떠 있는 동안이면 브라우저가 버린다 — 셋까지가 한계)."""
    now = [100.0]
    monkeypatch.setattr(progress, "_clock", lambda: now[0])

    def script() -> None:
        import streamlit as st

        from capa_simulation.components import shortening_progress_panel as panel

        message = st.session_state.get("next_notice")
        if isinstance(message, str):
            panel._notice("success", message)
        panel.render_baseline_notice()

    app = AppTest.from_function(script)

    def toast_slot(message: str, at: float) -> int:
        now[0] = at
        app.session_state["next_notice"] = message
        app.run()
        assert not app.exception
        event = app._tree.children[RootContainer.EVENT]
        assert len(event.children) == progress._NOTICE_SLOTS
        (slot,) = [index for index, node in event.children.items() if node.type == "toast"]
        return int(slot)

    assert toast_slot("A", 100.0) == 0
    assert toast_slot("B", 101.0) == 1
    assert toast_slot("C", 102.0) == 2
    assert toast_slot("D", 103.0) == 0
    assert toast_slot("E", 103.0 + progress._TOAST_VISIBLE_SECONDS) == 0
    assert toast_slot("F", 110.0 + progress._TOAST_VISIBLE_SECONDS) == 0
