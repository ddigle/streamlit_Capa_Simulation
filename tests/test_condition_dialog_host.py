# Purpose: 조건 패널 값 칸의 여는 콜백이 팝업 호스트 프래그먼트만 다시 돌리는 판정을 검증한다.

"""**판정이 틀리면 페이지가 낡은 채 남거나, 팝업을 열 때마다 페이지 계산까지 다시 돈다.**

시나리오·조회기간 값 칸의 여는 콜백(`open_scenario_dialog`·`open_period_dialog`)은 다른 팝업
칸을 비우고 초안·열림 키를 적은 **뒤 마지막 줄에서만** `sidebar_status.rerun_fragment_if_alone` 을
거쳐 `st.rerun(CONDITION_DIALOG_FRAGMENT_KEY)` 를 부른다 — 재실행 예외가 콜백을 그 자리에서 끊기
때문이다. 직전 전체 실행이 끝까지 돌지 않았거나, 페이지가 다르거나, 다른 위젯도 바뀌었으면 부르지
않고 앱 전체 재실행으로 물러난다.

AppTest 는 프래그먼트만 다시 돌리지 못한다(실행마다 프래그먼트 저장소가 새로 생긴다). 그래서
`st.rerun` 을 기록기로 바꿔 **부르는가·무엇으로 부르는가·부르는 순간 세션이 어떤가**만 본다.
프래그먼트 회차의 화면은 브라우저로 잰다.
"""

from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.period_field import PERIOD_DIALOG_KEY, PERIOD_FIELD_KEY
from capa_simulation.components.scenario_status import (
    LOAD_MODE,
    SCENARIO_DIALOG_KEY,
    SCENARIO_DIALOG_MODE_KEY,
    SCENARIO_FIELD_KEY,
)
from capa_simulation.scenario_preset_state import MONTH_PICKER_KEY
from capa_simulation.sidebar_status import APP_RUN_STATE_KEY, CONDITION_DIALOG_FRAGMENT_KEY

OTHER_KEY = "condition_dialog_test_other"
END_KEY = "condition_dialog_test_end"
# 페이지 팝업 열림 칸(HOME Past Data 붙여넣기 같은 것). 여는 콜백이 먼저 비워야 한다.
PAGE_DIALOG_KEY = "home_open_dialog"

FIELDS = [
    pytest.param(SCENARIO_FIELD_KEY, SCENARIO_DIALOG_KEY, PERIOD_DIALOG_KEY, id="scenario"),
    pytest.param(PERIOD_FIELD_KEY, PERIOD_DIALOG_KEY, SCENARIO_DIALOG_KEY, id="period"),
]


def _fields_script() -> None:
    """`app.py` 처럼 실행 표지를 맨 앞에서 세우고 두 값 칸을 그린 뒤 닫는다.

    `condition_dialog_test_end` 가 `open` 이면 닫지 않는다(끝까지 돌지 않은 실행).
    """
    import streamlit as st

    from capa_simulation.components.period_field import render_period_field
    from capa_simulation.components.scenario_status import render_scenario_field
    from capa_simulation.sidebar_status import begin_app_run

    run = begin_app_run()
    render_scenario_field()
    render_period_field()
    st.text_input("다른 입력", key="condition_dialog_test_other")
    if st.session_state.get("condition_dialog_test_end", "finish") == "finish":
        run.finish()


@pytest.fixture
def rerun_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`st.rerun` 을 부른 인자와 **그 순간의** 세션을 모은다. 실제로 다시 돌리지는 않는다."""
    import streamlit

    calls: list[dict[str, Any]] = []

    def record(*args: object, **kwargs: object) -> None:
        state = streamlit.session_state
        calls.append(
            {
                "args": args,
                "present": {
                    key: key in state
                    for key in (SCENARIO_DIALOG_KEY, PERIOD_DIALOG_KEY, PAGE_DIALOG_KEY)
                },
                "mode": state.get(SCENARIO_DIALOG_MODE_KEY),
                "picker_draft": MONTH_PICKER_KEY in state,
            }
        )

    monkeypatch.setattr(streamlit, "rerun", record)
    return calls


def _seed_stale_dialogs(app: AppTest, other_dialog_key: str) -> None:
    """다른 팝업 칸들과 고르다 만 월 초안을 남겨 둔다 — 여는 콜백이 비워야 할 것들."""
    app.session_state[PAGE_DIALOG_KEY] = "월별"
    app.session_state[other_dialog_key] = True
    app.session_state[MONTH_PICKER_KEY] = {"apply": None}


@pytest.mark.parametrize(("field_key", "dialog_key", "other_dialog_key"), FIELDS)
def test_the_opener_reruns_only_the_dialog_host_after_doing_all_its_work(
    rerun_calls: list[dict[str, Any]], field_key: str, dialog_key: str, other_dialog_key: str
) -> None:
    """끝까지 돈 실행 뒤 값 칸만 누르면 호스트 프래그먼트만 다시 돈다. 그 순간 열림 키·초안은 이미
    적혀 있고 다른 팝업 칸은 비어 있다(한 실행에 팝업 하나) — 콜백의 마지막 줄이라는 뜻이다."""
    app = AppTest.from_function(_fields_script).run()
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True
    _seed_stale_dialogs(app, other_dialog_key)

    app.button(key=field_key).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert [call["args"] for call in rerun_calls] == [(CONDITION_DIALOG_FRAGMENT_KEY,)]
    (call,) = rerun_calls
    assert call["present"] == {
        dialog_key: True,
        other_dialog_key: False,
        PAGE_DIALOG_KEY: False,
    }
    if field_key == SCENARIO_FIELD_KEY:
        assert call["mode"] == LOAD_MODE
    else:
        # 고르다 만 월 초안은 버린다 — 다시 열면 지금 조회기간에서 시작한다.
        assert call["picker_draft"] is False


@pytest.mark.parametrize(("field_key", "dialog_key", "other_dialog_key"), FIELDS)
def test_the_opener_falls_back_after_a_run_that_did_not_finish(
    rerun_calls: list[dict[str, Any]], field_key: str, dialog_key: str, other_dialog_key: str
) -> None:
    """직전 실행이 끝까지 돌지 않았으면(끊겼거나 아직 도는 실행) 호스트만 돌리지 않는다 — 앱 전체가
    돌아 페이지를 끝까지 그린다. 팝업은 그 전체 실행이 연다(열림 키는 그대로 적힌다)."""
    app = AppTest.from_function(_fields_script)
    app.session_state[END_KEY] = "open"
    app.run()
    _seed_stale_dialogs(app, other_dialog_key)

    app.button(key=field_key).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
    assert app.session_state[dialog_key] is True
    assert other_dialog_key not in app.session_state
    assert PAGE_DIALOG_KEY not in app.session_state


@pytest.mark.parametrize(("field_key", "dialog_key", "other_dialog_key"), FIELDS)
def test_the_opener_falls_back_when_another_widget_changed_too(
    rerun_calls: list[dict[str, Any]], field_key: str, dialog_key: str, other_dialog_key: str
) -> None:
    """입력칸에 쓰다 값 칸을 누르면 둘이 한 상호작용으로 온다 — 그 입력은 페이지가 다시 돌아야
    보인다."""
    del other_dialog_key
    app = AppTest.from_function(_fields_script).run()

    app.button(key=field_key).click()
    app.text_input(key=OTHER_KEY).input("값")
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
    assert app.session_state[dialog_key] is True


@pytest.mark.parametrize(("field_key", "dialog_key", "other_dialog_key"), FIELDS)
def test_the_opener_falls_back_when_the_page_differs_from_the_completed_run(
    rerun_calls: list[dict[str, Any]], field_key: str, dialog_key: str, other_dialog_key: str
) -> None:
    """끝까지 돈 실행과 이번 실행의 페이지가 다르면(페이지를 옮기는 실행이 본문 전에 끊긴 경우) 직전
    실행의 인자로 호스트만 돌리면 옛 페이지의 팝업이 된다 — 물러난다."""
    del other_dialog_key
    app = AppTest.from_function(_fields_script).run()
    state = dict(app.session_state[APP_RUN_STATE_KEY])
    app.session_state[APP_RUN_STATE_KEY] = {**state, "page": "다른 페이지"}

    app.button(key=field_key).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert rerun_calls == []
    assert app.session_state[dialog_key] is True
