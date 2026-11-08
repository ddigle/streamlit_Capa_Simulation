# Purpose: 화면 팝업 호스트가 여닫기를 호스트 회차로 좁히고 이벤트 칸 한 자리를 지키는지 본다.

"""`components/dialog_host.py` — 진짜 프래그먼트 회차(`tests/fragment_browser.py`)로 본다.

AppTest 는 `run()` 마다 프래그먼트 저장소를 새로 만들어 여는 콜백의 `st.rerun(<호스트 key>)` 가 늘
앱 전체 회차로 물러난다. 그래서 대역이 저장소를 쥐고 브라우저처럼 프래그먼트 회차를 청한다. 시험
화면은 `app.py` 처럼 실행 표지(`begin_app_run` · `finish`)를 단다 — 표지가 없으면 판정이 늘
거짓이다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fragment_browser import FragmentBrowser, install_fragment_browser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest

from capa_simulation.components.dialog_host import IDLE_MARKUP, WIDGET_KEYS_SUFFIX, DialogHost

HOST_KEY = "demo_dialog_host"
OPEN_KEY = "demo_open_dialog"

SCRIPT = r"""
from functools import partial

import streamlit as st

from capa_simulation.components.dialog_host import DialogHost
from capa_simulation.sidebar_status import begin_app_run, keeps_app_run_open

run = begin_app_run()
st.session_state["page_runs"] = st.session_state.get("page_runs", 0) + 1
HOST = DialogHost("demo_dialog_host", "demo_open_dialog")
PICKER = False
IDLE = False


@st.dialog("붙여넣기", on_dismiss=HOST.close)
@keeps_app_run_open
def paste_dialog(label: str = "기본") -> None:
    st.session_state["dialog_runs"] = st.session_state.get("dialog_runs", 0) + 1
    # 여는 알림(`paste_form.announce_on_open`)과 같은 판정 — 입력 칸 값이 세션에 없으면 방금 열렸다.
    st.caption(f"방금 열림 {'demo_paste_text' not in st.session_state}")
    st.text_input("붙여넣을 글", key="demo_paste_text")
    confirmed = st.checkbox("확인합니다", key="demo_confirm")
    st.caption(f"인자 {label}")
    st.button("지우기", key="demo_delete", disabled=not confirmed)
    if st.button("적용", key="demo_apply"):
        st.session_state["applied"] = st.session_state.get("demo_paste_text", "")
        HOST.finish()
    st.button("앱으로 닫기", key="demo_close_to_app", on_click=HOST.close_to_app)


@st.dialog("다른 팝업", on_dismiss=HOST.close)
def other_dialog() -> None:
    st.caption("다른 팝업")


st.button(
    "붙여넣기 열기", key="demo_open_paste", on_click=HOST.open, args=("paste", "demo_open_paste")
)
st.button("상자에서 열기", key="demo_open_box", on_click=HOST.opener("paste", "demo_open_box"))
st.button(
    "다른 팝업 열기", key="demo_open_other", on_click=HOST.open, args=("other", "demo_open_other")
)
st.caption("뒤 본문")
if PICKER:
    HOST.render(
        lambda value: partial(paste_dialog, label=value[1]) if isinstance(value, tuple) else None,
        widget_keys=lambda value: ("demo_paste_text", f"demo_confirm_{value[1]}"),
        idle=(lambda: st.html("<style>/* 닫힘 표지 */</style>")) if IDLE else None,
    )
else:
    HOST.render(
        {"paste": paste_dialog, "other": other_dialog},
        widget_keys={"paste": ("demo_paste_text", "demo_confirm"), "other": ()},
    )
# 호스트 뒤의 페이지 이벤트 칸 요소 — 팝업이 이 자리를 덮으면 안 된다.
st.html("<style>.page-rule{display:block}</style>")
run.finish()
"""


def _event_slots(messages: Sequence[ForwardMsg]) -> dict[int, tuple[str, str, str]]:
    """메시지가 이벤트 칸(본문 밖 최상위 칸)의 몇째 자리에 무엇을 썼나 — (종류, html 본문,
    프래그먼트 id)."""
    slots: dict[int, tuple[str, str, str]] = {}
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) != 2 or path[0] != RootContainer.EVENT:
            continue
        delta = message.delta
        if delta.WhichOneof("type") == "add_block":
            kind, body = str(delta.add_block.WhichOneof("type")), ""
        else:
            kind = str(delta.new_element.WhichOneof("type"))
            body = delta.new_element.html.body if kind == "html" else ""
        slots[path[1]] = (kind, body, delta.fragment_id)
    return slots


def _only_fragment_deltas(browser: FragmentBrowser) -> bool:
    return all(
        message.delta.fragment_id
        for message in browser.messages
        if message.WhichOneof("type") == "delta"
    )


def _start(
    monkeypatch: pytest.MonkeyPatch, script: str = SCRIPT
) -> tuple[AppTest, FragmentBrowser]:
    browser = install_fragment_browser(monkeypatch)
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    return app, browser


def test_the_host_writes_one_idle_slot_before_the_page_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """닫힌 갈래의 호스트는 이벤트 칸에 빈 스타일 한 자리를 쓰고, 페이지의 이벤트 요소는 그 뒤에
    선다."""
    _, browser = _start(monkeypatch)
    host = browser.fragment_keyed(HOST_KEY)
    slots = _event_slots(browser.messages)
    own = [index for index, slot in slots.items() if slot[2] == host]
    assert len(own) == 1
    (host_slot,) = own
    assert slots[host_slot][:2] == ("html", IDLE_MARKUP)
    assert any(index > host_slot and ".page-rule" in body for index, (_, body, _) in slots.items())


def test_opening_and_closing_run_only_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """여는 콜백은 콜백만 도는 회차와 호스트만 도는 회차를 부른다 — 페이지는 다시 돌지 않는다.
    팝업은
    호스트 자리 하나에 서고, 닫기(`on_dismiss`)도 호스트만 돌아 같은 자리를 빈 스타일로 되돌린다."""
    app, browser = _start(monkeypatch)
    host = browser.fragment_keyed(HOST_KEY)
    page_slots = _event_slots(browser.messages)
    (host_slot,) = [index for index, slot in page_slots.items() if slot[2] == host]

    app.button(key="demo_open_paste").click().run()
    assert not app.exception
    assert browser.started == [[], [host]]
    assert _only_fragment_deltas(browser)
    assert app.session_state["page_runs"] == 1
    opened = _event_slots(browser.messages)
    assert list(opened) == [host_slot]
    assert opened[host_slot][0] == "dialog"
    assert app.session_state[OPEN_KEY] == "paste"
    assert any(caption.value == "인자 기본" for caption in app.caption)

    # 닫기(X · 바깥 · Esc). AppTest 는 닫기를 흉내 내지 못해 `on_dismiss` 의 일(열림 칸 지우기)을
    # 하고 호스트만 다시 돌린다.
    browser.fragment_queue = [host]
    del app.session_state[OPEN_KEY]
    app.run()
    assert not app.exception
    assert browser.started == [[host]]
    assert app.session_state["page_runs"] == 1
    assert _event_slots(browser.messages) == {host_slot: page_slots[host_slot]}


def test_dismissing_drops_the_dialog_inputs_so_a_reopened_dialog_starts_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """닫기(`on_dismiss`)는 호스트만 돌아 Streamlit 이 팝업 프래그먼트의 위젯을 거두지 않는다 —
    닫기가 `render(widget_keys=)` 로 받은 그 팝업의 입력 위젯 값을 지운다(지키는 것 5). 앱 전체 회차
    없이 다시 열어도 서버 판정이 기본값을 그린 화면과 같다 — 여는 알림이 다시 뜨고(방금 열림), 확인
    체크로 잠근 단추가 잠긴 채 선다. 닫기 요청은 브라우저처럼 그려진 팝업 위젯 값과 닫기 트리거를
    함께 싣는다."""
    app, browser = _start(monkeypatch)
    host = browser.fragment_keyed(HOST_KEY)
    open_id = app.button(key="demo_open_paste").id

    browser.send_trigger(app, open_id, [])
    assert not app.exception
    assert browser.started == [[], [host]]
    assert any(caption.value == "방금 열림 True" for caption in app.caption)
    assert app.session_state[f"{HOST_KEY}{WIDGET_KEYS_SUFFIX}"] == (
        "demo_paste_text",
        "demo_confirm",
    )
    dialog_id = browser.dialog_widget_id()
    dialog = browser.fragment_of("demo_paste_text")

    app.text_input(key="demo_paste_text").set_value("남은 글")
    app.checkbox(key="demo_confirm").check()
    browser.fragment_queue = [dialog]
    app.run()
    assert not app.exception
    assert browser.started == [[dialog]]
    assert app.button(key="demo_delete").disabled is False

    browser.send_trigger(app, dialog_id, [host])
    assert not app.exception
    assert browser.started == [[host]]
    assert app.session_state["page_runs"] == 1
    assert OPEN_KEY not in app.session_state
    for key in ("demo_paste_text", "demo_confirm", f"{HOST_KEY}{WIDGET_KEYS_SUFFIX}"):
        assert key not in app.session_state, key

    # 다시 열기. AppTest 는 `run()` 마다 러너를 새로 만들어 요청에 없는 위젯 값을 페이지 바뀜으로
    # 거두므로 이 회차만으로는 남은 값을 가리지 못한다(위 단언이 가린다) — 지운 key 가 기본값으로
    # 다시 서는지를 본다.
    browser.send_trigger(app, open_id, [])
    assert not app.exception
    assert browser.started == [[], [host]]
    assert app.session_state["page_runs"] == 1
    assert any(caption.value == "방금 열림 True" for caption in app.caption)
    assert app.text_input(key="demo_paste_text").value == ""
    assert app.checkbox(key="demo_confirm").value is False
    assert app.button(key="demo_delete").disabled is True


def test_finishing_drops_the_dialog_inputs_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """`finish` 도 닫기를 거쳐 열림 칸과 함께 입력 위젯 값 · 그 key 칸을 지운다."""
    app, browser = _start(monkeypatch)
    app.button(key="demo_open_paste").click().run()
    dialog = browser.fragment_of("demo_apply")

    app.text_input(key="demo_paste_text").set_value("붙인 글")
    app.button(key="demo_apply").click()
    browser.fragment_queue = [dialog]
    app.run()
    assert not app.exception
    assert app.session_state["applied"] == "붙인 글"
    for key in ("demo_paste_text", "demo_confirm", f"{HOST_KEY}{WIDGET_KEYS_SUFFIX}"):
        assert key not in app.session_state, key


def test_a_sidebar_box_opener_takes_no_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """인자를 따로 받지 못하는 자리(사이드바 설정 상자)는 `opener` 를 넘긴다 — 같은 호스트
    회차다."""
    app, browser = _start(monkeypatch)
    host = browser.fragment_keyed(HOST_KEY)

    app.button(key="demo_open_box").click().run()
    assert not app.exception
    assert browser.started == [[], [host]]
    assert app.session_state[OPEN_KEY] == "paste"


def test_applying_inside_the_dialog_reruns_the_whole_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """원본을 바꾸는 동작은 팝업 본문이 열림 칸을 지우고 앱 전체를 다시 돌린다(`finish`)."""
    app, browser = _start(monkeypatch)
    app.button(key="demo_open_paste").click().run()
    dialog = browser.fragment_of("demo_apply")

    app.text_input(key="demo_paste_text").set_value("붙인 글")
    app.button(key="demo_apply").click()
    browser.fragment_queue = [dialog]
    app.run()
    assert not app.exception
    assert browser.started[0] == [dialog]
    assert browser.started[-1] == []
    assert app.session_state["applied"] == "붙인 글"
    assert OPEN_KEY not in app.session_state
    assert app.session_state["page_runs"] == 2
    assert not any(slot[0] == "dialog" for slot in _event_slots(browser.messages).values())


def test_close_to_app_turns_the_closing_round_into_a_whole_app_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """닫는 회차에 페이지가 할 일이 있는 팝업(HOME 설정)은 `close_to_app` 이다 — 콜백의 `st.rerun()`
    이 그 상호작용을 앱 전체 회차로 바꾼다."""
    app, browser = _start(monkeypatch)
    app.button(key="demo_open_paste").click().run()
    dialog = browser.fragment_of("demo_close_to_app")

    app.button(key="demo_close_to_app").click()
    browser.fragment_queue = [dialog]
    app.run()
    assert not app.exception
    assert browser.started[-1] == []
    assert OPEN_KEY not in app.session_state
    assert app.session_state["page_runs"] == 2


def test_without_a_finished_app_run_the_opener_falls_back_to_the_whole_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """직전 앱 전체 회차가 끝나지 않았으면(실행 표지 없음) 호스트만 돌리지 않고 앱 전체로
    물러난다."""
    app, browser = _start(monkeypatch, SCRIPT.replace("run.finish()\n", ""))

    app.button(key="demo_open_paste").click().run()
    assert not app.exception
    assert browser.started == [[]]
    assert app.session_state["page_runs"] == 2
    assert any(slot[0] == "dialog" for slot in _event_slots(browser.messages).values())


def test_opening_over_a_value_already_in_the_slot_reruns_the_whole_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이 열림 칸에 이미 값이 있었으면(같은 칸을 쓰는 다른 팝업) 그 팝업을 걷는 앱 전체 회차다. 다른
    열림 칸은 비운다 — 한 실행에 팝업은 하나다."""
    app, browser = _start(monkeypatch)
    app.session_state[OPEN_KEY] = "other"
    app.session_state["sidebar_scenario_open_dialog"] = True

    app.button(key="demo_open_paste").click().run()
    assert not app.exception
    assert browser.started == [[]]
    assert app.session_state[OPEN_KEY] == "paste"
    assert "sidebar_scenario_open_dialog" not in app.session_state


def test_the_host_leaves_a_value_it_does_not_know_and_writes_its_idle_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """같은 칸을 쓰되 호스트 밖에서 그리는 팝업의 값은 지우지 않는다 — 호스트는 빈 자리만 쓴다."""
    app, browser = _start(monkeypatch)
    app.session_state[OPEN_KEY] = "drawn_by_the_page"
    app.run()
    assert not app.exception
    host = browser.fragment_keyed(HOST_KEY)
    own = [slot for slot in _event_slots(browser.messages).values() if slot[2] == host]
    assert own == [("html", IDLE_MARKUP, host)]
    assert app.session_state[OPEN_KEY] == "drawn_by_the_page"


def test_a_picker_passes_the_value_to_the_dialog_and_an_idle_marker_fills_the_closed_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """인자를 싣는 열림 값(튜플)은 고르는 함수가 팝업 인자로 묶는다. 닫힌 갈래의 자리를 다른 표지가
    채워야 하면 `idle` 이 그 한 자리를 쓴다."""
    script = SCRIPT.replace("PICKER = False", "PICKER = True").replace(
        "IDLE = False", "IDLE = True"
    )
    app, browser = _start(monkeypatch, script)
    host = browser.fragment_keyed(HOST_KEY)
    own = [slot for slot in _event_slots(browser.messages).values() if slot[2] == host]
    assert own == [("html", "<style>/* 닫힘 표지 */</style>", host)]

    app.session_state[OPEN_KEY] = ("scenario", "r7")
    app.run()
    assert not app.exception
    assert any(caption.value == "인자 r7" for caption in app.caption)
    # key 가 열림 값에 달린 팝업은 `widget_keys` 도 함수다 — 그 값의 key 를 닫기가 볼 칸에 적는다.
    assert app.session_state[f"{HOST_KEY}{WIDGET_KEYS_SUFFIX}"] == (
        "demo_paste_text",
        "demo_confirm_r7",
    )


def test_the_open_slot_must_be_a_page_dialog_slot() -> None:
    """열림 칸은 `<페이지>_open_dialog` 다 — 페이지를 옮기면 `app.py` 가 버리는 칸이어야 한다."""
    with pytest.raises(ValueError, match="_open_dialog"):
        DialogHost(HOST_KEY, "demo_dialog")
