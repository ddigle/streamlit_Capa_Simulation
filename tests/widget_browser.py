# Purpose: AppTest 위에서 브라우저가 선택 상자 글자·편집표 편집을 들고 있다 되보내는 것을 흉내 낸다.

"""선택 상자 하나의 **브라우저 쪽 글자**를 들고 다니는 테스트 대역.

Streamlit 1.63 의 selectbox·multiselect·radio 는 브라우저와 값을 보이는 글자
(`format_func` 의 결과)로 주고받는다. 브라우저는 마지막으로 받은 글자(서버가 `set_value` 로
보낸 것) 또는 사용자가 고른 글자를 들고 있다가 다음 조작마다 **그대로** 되보낸다. 일반
`AppTest.run()` 은 그러지 않고 회차마다 세션의 값을 지금 `format_func` 로 다시 글자로 만들어
보낸다 — 그래서 선택지의 글자가 바뀌는 회차에 브라우저가 옛 글자로 다른 값을 되살리는
결함(2026-10-10 재검증)을 보지 못한다. 이 대역은 목표 상자 하나의 글자를 들고 있다가 `run()`
마다 그 글자를 끼워 보낸다. 다른 위젯은 `AppTest` 와 같이 보낸다. 편집표의 칸 편집은
`BrowserTables` 가 같은 방식으로 들고 다닌다.
"""

from __future__ import annotations

import json
from typing import Literal

from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Multiselect, Radio, Selectbox, get_widget_state

ChoiceKind = Literal["selectbox", "multiselect", "radio"]


class BrowserChoice:
    """선택 상자 하나(`kind`·`key`)를 브라우저처럼 다룬다."""

    def __init__(self, app: AppTest, kind: ChoiceKind, key: str) -> None:
        self.app = app
        self.kind = kind
        self.key = key
        self.wire: list[str] | str | None = None
        self.widget_id: str | None = None
        self.last_set_value = False

    def element(self) -> Selectbox[object] | Multiselect[object] | Radio[object]:
        if self.kind == "multiselect":
            return self.app.multiselect(key=self.key)
        if self.kind == "radio":
            return self.app.radio(key=self.key)
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


class BrowserTables:
    """편집표(`st.data_editor`)들의 **브라우저 쪽 칸 편집**을 들고 다니는 대역.

    브라우저는 편집표마다(위젯 id) 고친 칸을 행 위치로 들고 있다가 조작마다 통째로 되보낸다 — 고른
    줄 체크·이름 칸 편집이 그렇다. 위젯 id 가 바뀌면(key 세대·행 차례 지문이 바뀌어 새 위젯이 섬)
    그 편집은 사라진다. 일반 `AppTest.run()` 은 편집표 상태를 보내지 않으므로 `on_change`·초안
    접기를 잴 수 없다. 이 대역은 `edit` 로 칸을 고치고 `run()` 마다 편집표 상태를 JSON 글로 끼워
    보낸다(Streamlit 1.63 프런트엔드와 같은 `string_value`). 다른 위젯은 `AppTest` 와 같이 보낸다.

    `forms=True` 면 브라우저처럼 **폼 안 편집표**(`form_id` 가 있는 것)의 편집은 그 폼을
    제출하는 회차(`run(submit=폼 id)`)에만 보낸다 — 폼 안 편집이 제출 전에는 서버에 오지 않는 것을
    잰다. 기본은 옛 시험과 같이 폼을 보지 않고 늘 보낸다.
    """

    def __init__(self, app: AppTest, *, forms: bool = False) -> None:
        self.app = app
        self.forms = forms
        self.submit: str | None = None
        self.edits: dict[str, dict[int, dict[str, object]]] = {}
        self.added: dict[str, list[dict[str, object]]] = {}

    def widget_id(self, widget_key: str) -> str:
        """그 위젯 key 로 그려진 편집표의 위젯 id(「$$ID-…-<key>」)."""
        for node in self.app._tree:
            proto_id = getattr(getattr(node, "proto", None), "id", "")
            if isinstance(proto_id, str) and proto_id.endswith(f"-{widget_key}"):
                return proto_id
        raise AssertionError(f"편집표가 없습니다: {widget_key}")

    def edit(self, widget_key: str, position: int, column: str, value: object) -> None:
        """그 편집표 `position` 번째 행의 `column` 칸을 고친다(다음 `run()` 에 보낸다)."""
        rows = self.edits.setdefault(self.widget_id(widget_key), {})
        rows.setdefault(position, {})[column] = value

    def add(self, widget_key: str, row: dict[str, object]) -> None:
        """그 편집표 끝에 행 하나를 더한다(칸 이름 → 값, 다음 `run()` 에 보낸다) — 브라우저의
        행 추가 「+」."""
        self.added.setdefault(self.widget_id(widget_key), []).append(row)

    def _states(self) -> WidgetStates:
        states = WidgetStates()
        mounted: set[str] = set()
        for node in self.app._tree:
            proto_id = getattr(getattr(node, "proto", None), "id", "")
            form_id = getattr(getattr(node, "proto", None), "form_id", "")
            held = self.forms and bool(form_id) and form_id != self.submit
            if (
                isinstance(proto_id, str)
                and not held
                and (proto_id in self.edits or proto_id in self.added)
            ):
                mounted.add(proto_id)
                state = states.widgets.add()
                state.id = proto_id
                state.string_value = json.dumps(
                    {
                        "edited_rows": {
                            str(position): change
                            for position, change in self.edits.get(proto_id, {}).items()
                        },
                        "added_rows": self.added.get(proto_id, []),
                        "deleted_rows": [],
                    }
                )
                continue
            other = get_widget_state(node)
            if other is not None:
                states.widgets.append(other)
        return states

    def run(self, *, submit: str | None = None) -> AppTest:
        """브라우저 조작 하나로 생기는 회차. 그 뒤 화면에 없는 편집표의 편집은 버린다(새 위젯).
        `submit` 은 이 회차에 제출하는 폼 id 다(`forms=True` 일 때만 뜻이 있다)."""
        self.submit = submit
        try:
            self.app._run(self._states())
        finally:
            self.submit = None
        present = {
            proto_id
            for node in self.app._tree
            if isinstance(proto_id := getattr(getattr(node, "proto", None), "id", ""), str)
        }
        self.edits = {
            widget_id: rows for widget_id, rows in self.edits.items() if widget_id in present
        }
        self.added = {
            widget_id: rows for widget_id, rows in self.added.items() if widget_id in present
        }
        return self.app
