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
    """상자 콜백이 `on_box_toggle` 그 자체다. 직전 실행 표지는 테스트가 세션에 넣는다."""
    import streamlit as st

    from capa_simulation.sidebar_status import on_box_toggle

    box_key = "sidebar_box_toggle_test_box"
    st.checkbox("상자", key=box_key, on_change=on_box_toggle, args=(box_key, "상자"))
    st.text_input("다른 입력", key="sidebar_box_toggle_test_other")


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
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY, remembered_box_key

    app = AppTest.from_function(_callback_script).run()
    assert APP_RUN_STATE_KEY not in app.session_state

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
    assert app.session_state[remembered_box_key(BOX_KEY)] == (True, "상자")


def test_the_callback_does_not_rerun_the_fragment_while_a_run_is_incomplete(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

    app = AppTest.from_function(_callback_script).run()
    app.session_state[APP_RUN_STATE_KEY] = {"complete": False}

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []


def test_the_callback_reruns_only_the_fragment_after_a_completed_run(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    """양성 대조 — 이것이 없으면 아무것도 하지 않는 콜백도 위 두 검사를 통과한다."""
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY, SIDEBAR_TOGGLE_FRAGMENT_KEY

    app = AppTest.from_function(_callback_script).run()
    app.session_state[APP_RUN_STATE_KEY] = {"complete": True}

    app.checkbox(key=BOX_KEY).check().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == [(SIDEBAR_TOGGLE_FRAGMENT_KEY,)]


def test_the_callback_falls_back_when_another_widget_changed_too(
    rerun_calls: list[tuple[object, ...]],
) -> None:
    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

    app = AppTest.from_function(_callback_script).run()
    app.session_state[APP_RUN_STATE_KEY] = {"complete": True}

    app.checkbox(key=BOX_KEY).check()
    app.text_input(key=OTHER_KEY).input("값")
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
