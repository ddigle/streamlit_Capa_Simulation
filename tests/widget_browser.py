# Purpose: AppTest 위에서 브라우저가 선택 상자의 보이는 글자를 들고 있다 되보내는 동작을 흉내 낸다.

"""선택 상자 하나의 **브라우저 쪽 글자**를 들고 다니는 테스트 대역.

Streamlit 1.63 의 selectbox·multiselect 는 브라우저와 값을 보이는 글자(`format_func` 의 결과)로
주고받는다. 브라우저는 마지막으로 받은 글자(서버가 `set_value` 로 보낸 것) 또는 사용자가 고른
글자를 들고 있다가 다음 조작마다 **그대로** 되보낸다. 일반 `AppTest.run()` 은 그러지 않고 회차마다
세션의 값을 지금 `format_func` 로 다시 글자로 만들어 보낸다 — 그래서 선택지의 글자가 바뀌는 회차에
브라우저가 옛 글자로 다른 값을 되살리는 결함(2026-10-10 재검증)을 보지 못한다. 이 대역은 목표 상자
하나의 글자를 들고 있다가 `run()` 마다 그 글자를 끼워 보낸다. 다른 위젯은 `AppTest` 와 같이 보낸다.
"""

from __future__ import annotations

from typing import Literal

from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Multiselect, Selectbox, get_widget_state

ChoiceKind = Literal["selectbox", "multiselect"]


class BrowserChoice:
    """선택 상자 하나(`kind`·`key`)를 브라우저처럼 다룬다."""

    def __init__(self, app: AppTest, kind: ChoiceKind, key: str) -> None:
        self.app = app
        self.kind = kind
        self.key = key
        self.wire: list[str] | str | None = None
        self.widget_id: str | None = None
        self.last_set_value = False

    def element(self) -> Selectbox[object] | Multiselect[object]:
        if self.kind == "multiselect":
            return self.app.multiselect(key=self.key)
        return self.app.selectbox(key=self.key)

    def sync(self) -> None:
        """방금 회차의 상자를 읽는다. 서버가 값을 적어 보냈으면(`set_value`) 그 글자로 바꿔 든다."""
        try:
            element = self.element()
        except (KeyError, IndexError):
            return
        proto = element.proto
        self.widget_id = element.id
        self.last_set_value = bool(proto.set_value)
        if isinstance(element, Multiselect):
            if proto.set_value:
                self.wire = list(element.proto.raw_values)
            elif self.wire is None:
                self.wire = [element.proto.options[index] for index in element.proto.default]
            return
        if proto.set_value:
            self.wire = element.proto.raw_value if element.proto.HasField("raw_value") else None
        elif self.wire is None and element.proto.HasField("default"):
            self.wire = element.proto.options[element.proto.default]

    def options(self) -> list[str]:
        """브라우저에 보이는 선택지 글자."""
        return list(self.element().proto.options)

    def pick(self, shown: list[str] | str) -> None:
        """사용자가 상자에서 **보이는 글자**를 고른다(다음 `run()` 에 보낸다)."""
        wanted = shown if isinstance(shown, list) else [shown]
        missing = [text for text in wanted if text not in self.options()]
        assert not missing, (missing, self.options())
        self.wire = shown

    def _states(self) -> WidgetStates:
        states = WidgetStates()
        for node in self.app._tree:
            if self.widget_id is not None and getattr(node, "id", None) == self.widget_id:
                state = states.widgets.add()
                state.id = self.widget_id
                if self.kind == "multiselect":
                    state.string_array_value.data[:] = list(self.wire or [])
                elif self.wire is not None:
                    state.string_value = str(self.wire)
                continue
            other = get_widget_state(node)
            if other is not None:
                states.widgets.append(other)
        return states

    def start(self) -> AppTest:
        """첫 회차. 상자의 처음 글자를 든다."""
        self.app.run()
        self.sync()
        return self.app

    def run(self) -> AppTest:
        """브라우저 조작 하나(어느 위젯이든)로 생기는 회차 — 목표 상자는 들고 있던 글자를 보낸다."""
        self.app._run(self._states())
        self.sync()
        return self.app
