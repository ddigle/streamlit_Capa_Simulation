# Purpose: 설비 마스터 표 컴포넌트의 팔레트 싣기와 받은 트리거·출납 거르기를 검증한다.

"""`components/equipment_master_grid` 의 그리기·받기(개편 명세 6-2·6-4·6-7).

AppTest 는 JS 를 돌리지 못한다. 대역이 받은 data 를 적고, 세션 칸(`test_fake_grid_event`)에 넣어 둔
(key, 이름, 값)을 `st.session_state[key]` 에 적은 뒤 받은 `on_<이름>_change` 콜백을 부른다 — 진짜는
콜백이 회차 맨 앞에서 돌지만 여기서는 그리는 자리에서 돈다(같은 처리 함수를 지난다)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import equipment_master_grid as emg

FAKE_EVENT_KEY = "test_fake_grid_event"


@pytest.fixture
def grid_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        key = kwargs["key"]
        calls.append((key, kwargs["data"]))
        event = st.session_state.get(FAKE_EVENT_KEY)
        if isinstance(event, tuple) and event[0] == key:
            _, name, value = event
            st.session_state[key] = SimpleNamespace(**{name: value})
            callback = kwargs.get(f"on_{name}_change")
            if callback is not None:
                callback()
        return SimpleNamespace(outbox=None)

    monkeypatch.setattr(emg, "_GRID", _fake)
    return calls


def _script() -> None:
    import streamlit as st

    from capa_simulation.components import equipment_master_grid as emg

    seen = st.session_state.setdefault("seen", [])

    def note(*item: object) -> None:
        seen.append(item)

    emg.render_grid_loader(
        {"mode": "loader", "names": ["A"]},
        on_load=lambda request: note("load", request),
        on_clear=lambda: note("clear"),
        on_dialog=lambda name: note("dialog", name),
    )
    emg.render_grid_table(
        {"mode": "grid", "view": "v1"},
        on_outbox=lambda: note("outbox", emg.outbox_value(emg.GRID_KEY)),
        on_open=lambda row_id: note("open", row_id),
        on_unload=lambda ids: note("unload", ids),
    )
    emg.render_grid_side(
        "detail",
        {"mode": "side", "panel": "detail"},
        on_outbox=lambda: note("side-outbox"),
        on_open=lambda row_id: note("side-open", row_id),
        on_goto=lambda table, unit: note("goto", table, unit),
    )


def _run(event: tuple[str, str, object] | None) -> list[tuple[object, ...]]:
    app = AppTest.from_function(_script, default_timeout=30)
    if event is not None:
        app.session_state[FAKE_EVENT_KEY] = event
    app.run()
    assert not app.exception, app.exception
    seen: list[tuple[object, ...]] = app.session_state["seen"]
    return seen


def test_each_mount_gets_its_key_its_data_and_the_palette(
    grid_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    assert _run(None) == []
    keys = [key for key, _ in grid_calls]
    assert keys == [emg.LOADER_KEY, emg.GRID_KEY, emg.side_key("detail")]
    for _, data in grid_calls:
        assert set(data["palette"]) == set(emg._palette())
    assert grid_calls[0][1]["names"] == ["A"]


def test_a_load_is_filtered_and_trimmed(grid_calls: list[tuple[str, dict[str, Any]]]) -> None:
    seen = _run(
        (
            emg.LOADER_KEY,
            "load",
            {
                "kind": "names",
                "ids": ["s:A", " ", 3, "n:B"],
                "missing": [f"X{k}" for k in range(80)],
                "label": "  「A」 ",
            },
        )
    )
    assert len(seen) == 1 and seen[0][0] == "load"
    request = seen[0][1]
    assert isinstance(request, emg.LoadRequest)
    assert request.ids == ("s:A", "n:B") and len(request.missing) == 50
    assert request.label == "「A」"
    assert _run((emg.LOADER_KEY, "load", {"kind": "drop table", "ids": []})) == []


def test_dialog_clear_and_unknown_names(grid_calls: list[tuple[str, dict[str, Any]]]) -> None:
    assert _run((emg.LOADER_KEY, "dialog", {"name": "import"})) == [("dialog", "import")]
    assert _run((emg.LOADER_KEY, "dialog", {"name": "settings"})) == []
    assert _run((emg.LOADER_KEY, "clear", {})) == [("clear",)]


def test_table_triggers_from_an_old_view_are_dropped(
    grid_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    assert _run((emg.GRID_KEY, "open", {"view": "v1", "id": " s:A "})) == [("open", "s:A")]
    assert _run((emg.GRID_KEY, "open", {"view": "v0", "id": "s:A"})) == []
    assert _run((emg.GRID_KEY, "unload", {"view": "v1", "ids": ["s:A"]})) == [("unload", ["s:A"])]
    assert _run((emg.GRID_KEY, "unload", {"view": "v0", "ids": ["s:A"]})) == []


def test_the_outbox_reaches_its_handler_and_is_read_from_the_mount(
    grid_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    outbox = {"mount": "m-1", "ops": [{"seq": 1, "op": "undo"}]}
    seen = _run((emg.GRID_KEY, "outbox", outbox))
    assert seen == [("outbox", outbox)]
    assert emg.outbox_mount(outbox) == "m-1" and emg.outbox_mount({"mount": 3}) is None


def test_side_open_needs_no_view_and_goto_names_a_known_table(
    grid_calls: list[tuple[str, dict[str, Any]]],
) -> None:
    side = emg.side_key("detail")
    assert _run((side, "open", {"id": "s:A"})) == [("side-open", "s:A")]
    assert _run((side, "goto", {"table": "비가동 일정", "unit": " WBA-09 "})) == [
        ("goto", "비가동 일정", "WBA-09")
    ]
    assert _run((side, "goto", {"table": "설비 마스터", "unit": "x"})) == []
