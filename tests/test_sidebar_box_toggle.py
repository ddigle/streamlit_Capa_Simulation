# Purpose: 사이드바 상자 여닫기 콜백의 프래그먼트 재실행·앱 전체 물러남 판정을 검증한다.

"""**판정이 틀리면 본문이 빈 채 남거나, 여닫을 때마다 본문이 다시 돈다.**

`on_box_toggle` 은 끝까지 돈 실행 뒤에, 이번 상호작용에서 그 상자만 바뀌었을 때만
`st.rerun(SIDEBAR_TOGGLE_FRAGMENT_KEY)` 를 부른다. 둘째 조건은 Streamlit 세션 상태 내부를 읽는
`_only_this_widget_changed` 가 답한다 — 내부가 바뀌면 말없이 `False`(앱 전체 재실행)로 물러나므로
다른 테스트로는 그 물러남을 알아챌 수 없다.

AppTest 는 실행마다 프래그먼트 저장소가 새로 생겨 실제 프래그먼트 재실행은 볼 수 없다. 그래서
`st.rerun` 을 기록기로 바꿔 **부르는가·무엇으로 부르는가**만 본다. 여닫는 동작 자체는
브라우저로 잰다.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

BOX_KEY = "sidebar_box_toggle_test_box"
OTHER_KEY = "sidebar_box_toggle_test_other"
PROBE_KEY = "sidebar_box_toggle_test_probe"
END_KEY = "sidebar_box_toggle_test_end"


def _judgement_script() -> None:
    """상자 콜백이 `_only_this_widget_changed` 의 답을 세션에 적는다."""
    import streamlit as st

    from capa_simulation.sidebar_status import _only_this_widget_changed

    box_key = "sidebar_box_toggle_test_box"

    def record() -> None:
        st.session_state["sidebar_box_toggle_test_probe"] = _only_this_widget_changed(box_key)

    st.checkbox("상자", key=box_key, on_change=record)
    st.text_input("다른 입력", key="sidebar_box_toggle_test_other")


def _callback_script() -> None:
    """상자 콜백이 `on_box_toggle` 그 자체다. 실행 표지는 `app.py` 처럼 맨 앞에서 세우고 끝에서
    닫는다.

    `sidebar_box_toggle_test_end` 가 실행을 어떻게 끝낼지 고른다 — `finish`(끝까지 돎, 기본),
    `open`(닫지 않음 — 아직 도는 실행), `page_stop`(페이지의 `st.stop()`), `cut`(새 상호작용이 끊은
    실행 — 같은 멈춤 예외를 `st.stop()` 밖에서 던진다).
    """
    import streamlit as st
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException

    from capa_simulation.sidebar_status import begin_app_run, on_box_toggle

    run = begin_app_run()
    box_key = "sidebar_box_toggle_test_box"
    st.checkbox("상자", key=box_key, on_change=on_box_toggle, args=(box_key, "상자"))
    st.text_input("다른 입력", key="sidebar_box_toggle_test_other")
    end = st.session_state.get("sidebar_box_toggle_test_end", "finish")
    if end == "finish":
        run.finish()
    elif end in ("page_stop", "cut"):
        try:
            if end == "page_stop":
                st.stop()
            raise StopException()
        except StopException as stop:
            run.finish_stopped(stop)
            raise


@pytest.fixture
def rerun_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    """`st.rerun` 을 부른 인자를 모은다. 실제로 다시 돌리지는 않는다."""
    import streamlit

    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: calls.append(args))
    return calls


def test_only_the_box_changed_is_detected() -> None:
    app = AppTest.from_function(_judgement_script).run()

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[PROBE_KEY] is True


def test_the_box_and_another_widget_changed_together_is_not_only_the_box() -> None:
    """입력칸에 쓰다 상자를 누르면 둘이 한 상호작용으로 온다 — 그때는 앱 전체를 돌려야 한다."""
    app = AppTest.from_function(_judgement_script).run()
    app.checkbox(key=BOX_KEY).check().run()

    app.checkbox(key=BOX_KEY).uncheck()
    app.text_input(key=OTHER_KEY).input("값")
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[PROBE_KEY] is False


def test_the_callback_does_not_rerun_the_fragment_before_a_completed_run(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    """직전 실행이 끝났다는 표지가 없으면 물러난다. 기억 칸은 그래도 적는다."""
    from capa_simulation.sidebar_status import remembered_box_key

    app = AppTest.from_function(_callback_script)
    app.session_state[END_KEY] = "open"
    app.run()

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
    assert app.session_state[remembered_box_key(BOX_KEY)] == (True, "상자")


def test_the_callback_does_not_rerun_the_fragment_while_a_run_is_incomplete(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    """끝까지 돈 실행 뒤에 새 실행이 시작했으면(아직 도는 실행) 물러난다."""
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

    app = AppTest.from_function(_callback_script).run()
    state = dict(app.session_state[APP_RUN_STATE_KEY])
    assert state["complete"] is True
    app.session_state[APP_RUN_STATE_KEY] = {**state, "complete": False}

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []


def test_the_callback_reruns_only_the_fragment_after_a_completed_run(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    """양성 대조 — 이것이 없으면 아무것도 하지 않는 콜백도 위 두 검사를 통과한다."""
    from capa_simulation.sidebar_status import SIDEBAR_TOGGLE_FRAGMENT_KEY

    app = AppTest.from_function(_callback_script).run()

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == [(SIDEBAR_TOGGLE_FRAGMENT_KEY,)]


def test_the_callback_falls_back_when_another_widget_changed_too(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    app = AppTest.from_function(_callback_script).run()

    app.checkbox(key=BOX_KEY).check()
    app.text_input(key=OTHER_KEY).input("값")
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []


@pytest.mark.parametrize(("end", "reruns_fragment"), [("page_stop", True), ("cut", False)])
def test_only_a_run_the_page_stopped_itself_lets_the_box_skip_the_body(
    rerun_calls: list[tuple[object, ...]], end: str, reruns_fragment: bool
) -> None:
    """페이지가 `st.stop()` 으로 멈춘 실행 뒤에는 프래그먼트만 돈다. 새 상호작용이 끊은 실행 뒤에는
    물러난다 — 끊긴 실행은 본문이 반쯤 그려진 채라, 프래그먼트만 돌리면 그대로 남는다(2026-10-14
    브라우저 확인)."""
    from capa_simulation.sidebar_status import SIDEBAR_TOGGLE_FRAGMENT_KEY

    app = AppTest.from_function(_callback_script)
    app.session_state[END_KEY] = end
    app.run()

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == ([(SIDEBAR_TOGGLE_FRAGMENT_KEY,)] if reruns_fragment else [])


def test_a_run_that_began_later_keeps_an_older_run_from_marking_complete() -> None:
    """같은 세션의 실행은 겹칠 수 있다(Streamlit 이 새 상호작용 때 돌던 실행에 멈춤만 걸고 새 실행을
    따로 띄운다). 늦게 끝난 옛 실행이 새 실행의 「아직 안 끝남」을 덮어쓰지 않는다."""

    def script() -> None:
        import streamlit as st

        from capa_simulation.sidebar_status import APP_RUN_STATE_KEY, begin_app_run

        older = begin_app_run()
        newer = begin_app_run()
        older.finish()
        st.session_state["probe_after_older"] = bool(
            st.session_state[APP_RUN_STATE_KEY]["complete"]
        )
        newer.finish()
        st.session_state["probe_after_newer"] = bool(
            st.session_state[APP_RUN_STATE_KEY]["complete"]
        )

    app = AppTest.from_function(script).run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["probe_after_older"] is False
    assert app.session_state["probe_after_newer"] is True


def test_the_callback_falls_back_when_the_page_differs_from_the_completed_run(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    """끝까지 돈 실행과 이번 실행의 페이지가 다르면(페이지를 옮기는 실행이 본문 전에 끊긴 경우)
    물러난다."""
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

    app = AppTest.from_function(_callback_script).run()
    state = dict(app.session_state[APP_RUN_STATE_KEY])
    assert state["complete"] is True
    app.session_state[APP_RUN_STATE_KEY] = {**state, "page": "다른 페이지"}

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
