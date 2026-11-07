# Purpose: 저장한 메모 칸 비우기가 칸을 갈지 않고 저장한 글에만, 제출 아닌 회차에만 닿게 고정한다.

"""AppTest 는 두 요청을 겹칠 수 없어 겹친 둘째 누름은 표지를 직접 세워 본다. 초점(Enter 저장 뒤 칸에
남음)과 재시작 뒤 앞 세션 탭의 칸은 브라우저로 본다 — 여기서는 그 둘의 뿌리인 위젯 id 를
붙잡는다."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

KEY = "demo_note"
FIRST_PRESS_START = 7


def _form() -> None:
    import streamlit as st

    from capa_simulation.components.saved_note import (
        mark_note_saved,
        mark_note_saved_again,
        ready_note_field,
    )

    with st.form("demo_form"):
        submitted = st.form_submit_button("저장")
        ready_note_field("demo_note", submitted=submitted, start=st.session_state.get("start"))
        note = st.text_input("변경 메모", key="demo_note")
    if submitted:
        st.session_state["submitted_notes"] = [*st.session_state.get("submitted_notes", []), note]
        outcome = st.session_state.get("outcome", "saved")
        if outcome == "saved":
            mark_note_saved("demo_note", note)
            st.rerun()
        if outcome == "again":
            mark_note_saved_again("demo_note", note)
            st.rerun()


def _app(start: int | None = None) -> AppTest:
    app = AppTest.from_function(_form)
    if start is not None:
        app.session_state["start"] = start
    return app.run()


def _press(app: AppTest, note: str, outcome: str = "saved") -> AppTest:
    app.text_input(key=KEY).set_value(note)
    app.session_state["outcome"] = outcome
    app.button[0].click()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def test_a_saved_note_empties_the_same_widget() -> None:
    """칸을 갈아 끼우지 않는다 — 위젯 id 가 같아 Enter 저장의 초점이 칸에 남고 재시작 뒤 새 세션의
    칸도 같은 위젯이다. 그 회차의 제출 값은 적은 글 그대로다."""
    app = _app()
    widget = app.text_input(key=KEY).proto.id
    app = _press(app, "첫 메모")
    assert app.text_input(key=KEY).value == ""
    assert app.text_input(key=KEY).proto.id == widget
    assert app.session_state["submitted_notes"] == ["첫 메모"]


def test_a_refused_save_leaves_the_field_alone() -> None:
    app = _press(_app(), "거절될 메모", outcome="refused")
    app.run()
    assert app.text_input(key=KEY).value == "거절될 메모"


def test_a_second_press_keeps_its_input_and_the_next_run_empties_the_field() -> None:
    """같은 글의 둘째 누름 회차는 칸을 비우지 않는다 — 비우면 그 회차의 입력이 바뀌어 같은 입력의
    거름(`save_once`)을 지나 한 번 더 쓴다. 뒤따르는 회차가 비운다."""
    app = _app()
    app.session_state[f"{KEY}__note_saved"] = "첫 메모"
    app = _press(app, "첫 메모", outcome="again")
    assert app.session_state["submitted_notes"] == ["첫 메모"]
    assert app.text_input(key=KEY).value == ""


def test_a_field_holding_another_text_is_not_emptied() -> None:
    """앞 회차가 끝나기 전에 온 다른 글 — 표지만 걷고 칸은 지킨다."""
    app = _app()
    app.text_input(key=KEY).set_value("둘째 메모")
    app.session_state[f"{KEY}__note_saved"] = "첫 메모"
    app.run()
    assert app.text_input(key=KEY).value == "둘째 메모"
    assert f"{KEY}__note_saved" not in app.session_state
    app.run()
    assert app.text_input(key=KEY).value == "둘째 메모"


def test_another_text_sent_right_after_the_field_was_emptied_is_written_back() -> None:
    """앞 회차의 빈 값이 둘째 누름을 보낸 뒤에 브라우저에 닿으면 칸은 비고 그 글은 서버에만 남는다 —
    제출 회차가 글을 다시 실어 보낸다. 다음 제출부터는 다시 적지 않는다."""
    app = _press(_app(), "첫 메모")
    app = _press(app, "둘째 메모", outcome="refused")
    assert app.text_input(key=KEY).value == "둘째 메모"
    assert app.text_input(key=KEY).proto.set_value

    app = _press(app, "둘째 메모", outcome="refused")
    assert not app.text_input(key=KEY).proto.set_value


def test_the_same_text_of_a_double_press_is_not_written_back() -> None:
    """같은 글의 둘째 누름은 첫 누름이 쓴 글이다 — 다시 적으면 비운 메모가 칸에 되살아나 다음 저장의
    기록에 실린다."""
    app = _press(_app(), "첫 메모")
    app = _press(app, "첫 메모", outcome="refused")
    assert not app.text_input(key=KEY).proto.set_value


def test_the_second_press_empties_only_the_note_of_the_first_press() -> None:
    """끊긴 첫 회차가 표지를 남기지 못한 자리 — 첫 누름의 글이면 비우고, 다른 글이면 쓰이지 않은
    글이라 남긴다."""
    app = _app(FIRST_PRESS_START)
    app = _press(app, "첫 메모", outcome="refused")
    app = _press(app, "둘째 메모", outcome="again")
    assert app.text_input(key=KEY).value == "둘째 메모"
    app = _press(app, "첫 메모", outcome="again")
    assert app.text_input(key=KEY).value == ""


def test_the_first_press_is_counted_per_start_and_only_for_version_checked_saves() -> None:
    """출발점이 옮겨 간 누름은 새 묶음이다. 대조가 없는 저장(`start` 없음)은 첫 글을 적지 않는다 —
    `mark_note_saved_again` 을 부르지 않는다."""
    app = _app(FIRST_PRESS_START)
    app = _press(app, "앞 메모", outcome="refused")
    app.session_state["start"] = FIRST_PRESS_START + 1
    app = _press(app, "뒤 메모", outcome="refused")
    assert app.session_state[f"{KEY}__note_first_press"] == (FIRST_PRESS_START + 1, "뒤 메모")

    app = _app()
    app = _press(app, "메모", outcome="refused")
    assert f"{KEY}__note_first_press" not in app.session_state


def test_an_empty_note_leaves_no_mark() -> None:
    app = _press(_app(), "")
    assert f"{KEY}__note_saved" not in app.session_state
