# Purpose: AppTest 에서 공정 고르기 판(Components v2)의 data 를 읽고 「적용」 트리거를 보낸다.

"""공정 고르기 판(`process_field.mount_process_board`)은 Components v2 라 AppTest 가 누르지 못한다.

`live_board` 가 판을 AppTest 회차 **안에서** 등록하게 갈아 끼운다(모듈을 읽을 때 등록한 것은 AppTest
실행 밖이라 「미등록」 이고, 그래서 `conftest` 는 판을 아무것도 보내지 않는 대역으로 둔다). 판
요소(`bidi_component` — 위젯 id 가 `-<key>` 로 끝남)를 트리에서 찾아 그 data(JSON)를 읽고, 누름은
위젯 상태에 상태 칸(바뀌지 않음)과 트리거 모음 칸(Streamlit `_make_trigger_id(<판 id>, "events")`)을
더해 돌린다 — 탭 줄 시험(`test_page_tabs._press_strip`)과 같은 길이라 판 콜백(`on_apply`)이 진짜로
회차 앞에서 돈다.

여기서 넣는 트리거는 판 JS 를 거치지 않는다 — 판이 보낼 값(누른 차례 · 모두 켬)과 「적용」 잠금은
`tests/test_process_field.py` 의 마운트 시험(가짜 DOM 에서 판 JS 를 그 data 로 돌림)이 본다.
그래서 판이 잠가 보내지 않을 트리거(같은 값의 늦은 「적용」 · 선택지 밖 값)도 서버 쪽 시험으로
넣을 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from capa_simulation.components import process_field


def live_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """공정 고르기 판을 그 회차 안에서 등록해 진짜 트리거 칸을 세운다(모듈 설명)."""

    def live(**kwargs: Any) -> Any:
        component = st.components.v2.component(
            "capa_process_picker",
            html=process_field.PROCESS_FIELD_HTML,
            css=process_field.PROCESS_FIELD_CSS,
            js=process_field.PROCESS_FIELD_JS,
            isolate_styles=False,
        )
        return component(**kwargs)

    monkeypatch.setattr(process_field, "_PROCESS_PICKER", live)


def _nodes(node: Any) -> Iterator[Any]:
    yield node
    for child in getattr(node, "children", {}).values():
        yield from _nodes(child)


def board_element(app: AppTest, key: str) -> Any:
    """이 회차에 그린 판 요소 하나 — 없거나 둘이면 시험이 멈춘다."""
    found = [
        node
        for node in _nodes(app._tree)
        if getattr(node, "type", None) == "bidi_component"
        and str(node.proto.id).endswith(f"-{key}")
    ]
    assert len(found) == 1, f"판 {key} 이 {len(found)}개입니다"
    return found[0]


def board_drawn(app: AppTest, key: str) -> bool:
    """이 회차에 판을 그렸나."""
    return any(
        getattr(node, "type", None) == "bidi_component" and str(node.proto.id).endswith(f"-{key}")
        for node in _nodes(app._tree)
    )


def board_data(app: AppTest, key: str) -> dict[str, Any]:
    """판에 보낸 data(선택지 · 지금 값 · 그 칸의 셋)."""
    data = json.loads(board_element(app, key).proto.json)
    assert isinstance(data, dict)
    return data


def board_options(app: AppTest, key: str) -> list[str]:
    """판 선택지의 값(원본) — 판 차례."""
    return [str(option["value"]) for option in board_data(app, key)["options"]]


def board_labels(app: AppTest, key: str) -> list[str]:
    """판 선택지의 보이는 글자 — 판 차례."""
    return [str(option["label"]) for option in board_data(app, key)["options"]]


def press_board(app: AppTest, key: str, value: dict[str, Any]) -> AppTest:
    """판 「적용」 트리거 하나(`value` — `{"values": [...]}` · `{"clear": True}`)를 보낸 회차."""
    from streamlit.components.v2.bidi_component.main import _make_trigger_id
    from streamlit.proto.WidgetStates_pb2 import WidgetState

    board_id = str(board_element(app, key).proto.id)
    states = app._tree.get_widget_states()
    states.widgets.append(WidgetState(id=board_id, json_value="{}"))
    states.widgets.append(
        WidgetState(
            id=_make_trigger_id(board_id, "events"),
            json_trigger_value=json.dumps([{"event": "apply", "value": value}]),
        )
    )
    app._run(states)
    return app


def apply_board(app: AppTest, key: str, values: Sequence[str]) -> AppTest:
    """판에서 `values` 를 (그 차례로) 고르고 「적용」 을 누른 회차."""
    return press_board(app, key, {"values": list(values)})


def clear_board(app: AppTest, key: str) -> AppTest:
    """판의 고른 것 비우기(공용 판 「전체」 자리) 누름 회차."""
    return press_board(app, key, {"clear": True})
