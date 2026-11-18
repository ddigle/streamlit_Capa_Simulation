# Purpose: 세션 칸 창구(`session_slot.SessionSlot`)의 읽기 · 쓰기 · 꼴 거르기 · 지우기를 잰다.

"""`capa_simulation.session_slot` — 새 코드가 세션 칸을 쓰는 한 창구(AGENTS.md 5장 42).

세션 상태는 실행 문맥이 있어야 하므로 작은 스크립트를 AppTest 로 돌려 본다.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st

from capa_simulation.session_slot import SessionSlot

COUNT = SessionSlot("demo_slot_count", int, lambda: 0)
BOX = SessionSlot("demo_slot_box", dict, dict)

st.session_state["demo_seen_before"] = COUNT.exists()
st.session_state["demo_read"] = COUNT.get()
st.session_state["demo_present_after_read"] = COUNT.exists()
if st.session_state.get("demo_step") == "set":
    COUNT.set(COUNT.get() + 2)
if st.session_state.get("demo_step") == "box":
    BOX.setdefault()["n"] = BOX.setdefault().get("n", 0) + 1
if st.session_state.get("demo_step") == "clear":
    COUNT.clear()
    COUNT.clear()
st.session_state["demo_after"] = COUNT.get()
"""


def _run(app: AppTest, step: str | None = None) -> AppTest:
    if step is not None:
        app.session_state["demo_step"] = step
    app.run()
    assert not app.exception
    return app


def test_an_empty_slot_reads_its_initial_value_without_writing_it() -> None:
    app = _run(AppTest.from_string(SCRIPT))
    assert app.session_state["demo_seen_before"] is False
    assert app.session_state["demo_read"] == 0
    assert app.session_state["demo_present_after_read"] is False
    assert "demo_slot_count" not in app.session_state


def test_set_and_clear_round_trip() -> None:
    app = _run(AppTest.from_string(SCRIPT), "set")
    assert app.session_state["demo_after"] == 2
    _run(app, "set")
    assert app.session_state["demo_after"] == 4
    assert app.session_state["demo_seen_before"] is True
    _run(app, "clear")
    assert "demo_slot_count" not in app.session_state
    assert app.session_state["demo_after"] == 0


def test_a_value_of_another_kind_reads_as_the_initial_value() -> None:
    """앞 판이 같은 이름에 다른 꼴을 남겼으면 처음 값으로 읽고, `setdefault` 는 갈아 넣는다."""
    app = AppTest.from_string(SCRIPT)
    app.session_state["demo_slot_count"] = "다른 꼴"
    app.session_state["demo_slot_box"] = ["다른 꼴"]
    _run(app)
    assert app.session_state["demo_read"] == 0
    assert app.session_state["demo_slot_count"] == "다른 꼴"
    _run(app, "box")
    assert app.session_state["demo_slot_box"] == {"n": 1}


def test_setdefault_hands_back_the_stored_container() -> None:
    """바뀌는 그릇은 칸에 든 것 그대로라 제자리에서 고친 것이 다음 회차에 남는다."""
    app = _run(AppTest.from_string(SCRIPT), "box")
    _run(app, "box")
    assert app.session_state["demo_slot_box"] == {"n": 2}
