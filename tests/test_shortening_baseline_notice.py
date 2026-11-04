# Purpose: 필요 단축 일정 본문 프래그먼트의 이벤트 칸 자리 수와 기준선 결과 알림 표지를 검사한다.

"""필요 단축 일정 머리·본문 프래그먼트(`_render_view`)가 이벤트 칸(본문 밖 최상위 칸)에 쓰는 것.

프래그먼트만 도는 회차는 이벤트 칸 쓰기 위치를 앱 전체 회차에서 그 프래그먼트를 부른
자리로 되돌리고, 브라우저는 받은 자리의 요소만 갈아 끼운다(남은 자리는 그대로 둔다).
그래서 이 프래그먼트는 갈래(일반 보기·진척 비교·알림 있음/없음)와 상관없이 **같은
자리만** 쓴다 — 서식은 본문 `st.html` 에 싣고, 기준선 저장 · 지우기 결과는 알림 표지
(`flash.render_flash`) 한 자리에 싣는다.

결과 알림은 오른쪽 아래 알림창 · Alarm 한 꼴이다(앱의 다른 동작 결과와 같은 길 — Streamlit
토스트를 쓰지 않는다). 잇단 알림은 같은 표지 자리에 다른 id 로 실리고 알림창이 id 마다 한 번
띄운다. 그리기 전에 콜백이 둘 돌면 두 알림을 모두 싣는다(같은 폼·같은 기준선의 두 번 누름은
콜백이 먼저 거르고, 이것은 그 밖의 조합을 위한 예비다).

진짜 프래그먼트 회차는 `tests/fragment_browser.py` 대역으로 돌린다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from alert_marks import flashed
from fragment_browser import FragmentBrowser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_shortening_progress_tab import _name_input, _save_button, _saved_database
from test_shortening_view_fragment import _fragment_of, _install, _open, _run, _runner

from capa_simulation.alerts import MARKER_ATTRIBUTE, marker_notes
from capa_simulation.components.required_shortening_panel import SHORTENING_LEVEL_KEY
from capa_simulation.components.shortening_progress_panel import SHORTENING_COMPARE_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

_EMPTY = ("html", "<style></style>")


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
        body = element.html.body if kind == "html" else ""
        slots[path[1]] = (kind, body)
    return slots


def _sent(slots: dict[int, tuple[str, str]]) -> list[dict[str, Any]]:
    """표지 자리에 실린 결과 알림(다시 보낸 `again` 은 뺀다 — 알림창이 다시 띄우지 않는다)."""
    return [
        note
        for _, body in slots.values()
        if MARKER_ATTRIBUTE in body
        for note in marker_notes(body)
        if "flash" in note and not note.get("again")
    ]


def _view(runner: FragmentBrowser) -> str:
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    assert view, "목표 확보율은 프래그먼트 안이다"
    return view


def test_the_view_writes_the_same_event_slots_in_every_branch(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 전체 회차·목표·저장 성공·같은 이름 거절·진척 비교 어느 회차든 같은 이벤트 칸
    자리를 쓰고, 결과 알림은 그 한 자리의 표지에 실린다(토스트가 아니다)."""
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    view = _view(runner)
    full = _event_slots(runner.messages, view)
    assert full and all(slot == _EMPTY for slot in full.values()), full

    runner.fragment_queue = [view]
    _run(app, world, lambda app: app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(0.9))
    assert runner.started == [[view]]
    assert _event_slots(runner.messages, view) == full

    # 저장 성공 — 프래그먼트 회차가 앱 전체 회차로 바뀌고 알림이 표지 자리에 실린다.
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view], []]
    saved = _event_slots(runner.messages, view)
    assert set(saved) == set(full)
    assert all(kind == "html" for kind, _ in saved.values())
    (first,) = _sent(saved)
    assert first["flash"] == "success" and "기준선을 저장했습니다" in first["markdown"]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    # 곧바로 같은 이름 — 거절 알림은 프래그먼트 회차의 같은 자리에 새 id 로 실린다(알림창이 앞
    # 알림과 따로 띄운다). 머리 밑 자리에 경고 상자를 세우지 않는다.
    view = _view(runner)
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _name_input(app).set_value(stored.name))
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view]]
    rejected = _event_slots(runner.messages, view)
    assert set(rejected) == set(full)
    (second,) = _sent(rejected)
    assert second["flash"] == "warning" and "같은 이름" in second["markdown"]
    assert second["id"] != first["id"]
    assert not any("같은 이름" in str(item.value) for item in app.warning)

    # 진척 비교(서식이 둘인 갈래)도 같은 자리만 쓴다 — 서식은 본문 `st.html` 에 실린다.
    runner.fragment_queue = [view]
    _run(
        app,
        world,
        lambda app: app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id),
    )
    assert runner.started == [[view]]
    assert set(_event_slots(runner.messages, view)) == set(full)
    assert not _sent(_event_slots(runner.messages, view))
    bodies = [str(element.proto.body) for element in app.get("html")]
    assert any(".shk-prog-summary" in body and "진척 비교 요약" in body for body in bodies)
    clear_equipment_repository()


def test_two_callbacks_before_one_draw_report_both_notices() -> None:
    """그리기 전에 콜백이 둘 돌아 알림 둘을 남기면 둘 다 싣는다 — 한 칸에 덮어 적으면 앞
    알림(저장 성공)은 사라지고 뒤 알림만 보인다. 거절은 알림창으로만 낸다(자리 상자 없음)."""

    def script() -> None:
        from capa_simulation.components import shortening_progress_panel as progress

        progress._notice("success", "기준선을 저장했습니다 — 「A」.")
        progress._notice("warning", "기준선을 저장하지 않았습니다 — 같은 이름: A")
        progress.render_baseline_notice()

    app = AppTest.from_function(script).run()
    assert not list(app.exception), [element.message for element in app.exception]
    notes = flashed(app)
    assert [note.code for note in notes] == ["FL-01", "FL-03"]
    assert "저장했습니다" in notes[0].value and "같은 이름" in notes[1].value
    assert not app.warning and not app.toast


def test_a_fourth_notice_before_a_draw_replaces_only_the_last_one() -> None:
    """칸은 셋이다 — 빈 칸부터 차례로 담고, 다 차면 마지막 칸만 바꾼다(앞 알림은 남는다). 몇
    개를 담든 이벤트 칸에는 정확히 한 자리를 쓴다."""

    def script() -> None:
        from capa_simulation.components import shortening_progress_panel as progress

        for name in ("A", "B", "C", "D"):
            progress._notice("success", f"기준선을 저장했습니다 — 「{name}」.")
        progress.render_baseline_notice()

    app = AppTest.from_function(script).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert [note.value[-4:] for note in flashed(app)] == ["「A」.", "「B」.", "「D」."]
    assert len(app._tree.children[RootContainer.EVENT].children) == 1
