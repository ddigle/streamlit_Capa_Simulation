# Purpose: 시나리오 목록 표 컴포넌트 대역 — 받은 data 를 적고 넣어 둔 출납을 콜백으로 보낸다.

"""AppTest 에서 목록 표(`components/scenario_list_grid`)를 흉내 내는 대역.

AppTest 는 그 JS 를 못 돌린다. 대역은 마운트마다 받은 (key, data)를 목록에 적고, 세션
칸(`FAKE_EVENT_KEY`)에 넣어 둔 (key, 출납)을 그 마운트의 상태 값으로 적은 뒤 받은
`on_outbox_change` 콜백을 부른다. 출납 값은 진짜처럼 세션에 남는다(같은 출납이 다시 와도 seq
기억으로 한 번만 반영한다).

- **기본** — 그리는 자리에서 부른다. 진짜는 콜백이 회차 맨 앞에서 돈다 — `send_ops` 가 한 번 더 돌려
  반영한 결과를 그린다.
- **`early=True`** — 진짜처럼 회차 맨 앞(대본 전)에서 부른다. 페이지 앞 표지(탭 점)와 맨 위 알림을
  잰다.

`ListBrowser.prepared` 는 콜백 없이 상태 값만 적는다 — 단추 누름과 같은 메시지의 출납이거나, 콜백이
끊긴 꼴이다(본문 머리 접기가 잇는다).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest

from capa_simulation.components import scenario_list_grid as grid
from capa_simulation.services.scenario_list_edits import order_token

FAKE_EVENT_KEY = "test_fake_scenario_list_event"
Calls = list[tuple[str, dict[str, Any]]]
_SEQ = itertools.count(1)


def _deliver(key: str, value: object, callback: Callable[[], None] | None) -> None:
    st.session_state.pop(FAKE_EVENT_KEY, None)
    st.session_state[key] = SimpleNamespace(outbox=value)
    if callback is not None:
        callback()


def install_fake_list_grid(monkeypatch: pytest.MonkeyPatch, *, early: bool = False) -> Calls:
    """표 컴포넌트를 대역으로 바꾸고 받은 (key, data) 목록을 돌려준다(그린 차례 그대로)."""
    calls: Calls = []
    callbacks: dict[str, Callable[[], None]] = {}

    def _fake(**kwargs: Any) -> SimpleNamespace:
        key = kwargs["key"]
        calls.append((key, kwargs["data"]))
        callback = kwargs.get("on_outbox_change")
        if callback is not None:
            callbacks[key] = callback
        event = st.session_state.get(FAKE_EVENT_KEY)
        if not early and isinstance(event, tuple) and event[0] == key:
            _deliver(key, event[1], callback)
        return SimpleNamespace(outbox=None)

    monkeypatch.setattr(grid, "_GRID", _fake)
    if early:
        original = SafeSessionState.on_script_will_rerun

        def _before_script(self: SafeSessionState, *args: Any, **kwargs: Any) -> None:
            original(self, *args, **kwargs)
            event = st.session_state.get(FAKE_EVENT_KEY)
            if isinstance(event, tuple) and event[0] in callbacks:
                _deliver(event[0], event[1], callbacks[event[0]])

        monkeypatch.setattr(SafeSessionState, "on_script_will_rerun", _before_script)
    return calls


def last(calls: Calls, key: str) -> dict[str, Any]:
    """그 마운트가 마지막으로 받은 data."""
    return next(data for name, data in reversed(calls) if name == key)


def drawn(calls: Calls, key: str) -> bool:
    return any(name == key for name, _ in calls)


class ListBrowser:
    """브라우저 쪽 — 마운트마다 mount id · 세대를 들고 op 를 번호 매겨 보낸다."""

    def __init__(self, app: AppTest, calls: Calls) -> None:
        self.app = app
        self.calls = calls

    def run(self) -> AppTest:
        self.app.run()
        assert not self.app.exception, self.app.exception
        return self.app

    def outbox(self, key: str, *ops: dict[str, Any]) -> dict[str, Any]:
        base = last(self.calls, key)["base"]
        numbered = []
        for op in ops:
            seq = next(_SEQ)
            numbered.append({"seq": seq, "at": seq, "base": base, **op})
        return {"mount": f"m-{key}", "ops": numbered}

    def send(self, key: str, *ops: dict[str, Any]) -> AppTest:
        """그 마운트에서 op 들을 보내고(콜백) 결과를 그린 회차까지 돌린다."""
        self.app.session_state[FAKE_EVENT_KEY] = (key, self.outbox(key, *ops))
        self.run()
        return self.run()

    def deliver(self, key: str, *ops: dict[str, Any]) -> AppTest:
        """보낸 회차 하나만 돌린다(`early=True` 와 함께 — 그 회차의 표지를 본다)."""
        self.app.session_state[FAKE_EVENT_KEY] = (key, self.outbox(key, *ops))
        return self.run()

    def prepared(self, key: str, *ops: dict[str, Any]) -> None:
        """다음 회차에 함께 닿을 출납을 세션에만 넣는다(단추 누름과 같은 메시지의 출납)."""
        self.app.session_state[key] = SimpleNamespace(outbox=self.outbox(key, *ops))

    def rename_scenario(self, row_id: str, text: str, *, seen: str | None = None) -> AppTest:
        row = next(row for row in last(self.calls, grid.TABLE_KEY)["rows"] if row["id"] == row_id)
        shown = seen if seen is not None else str(row.get("saved", row["name"]))
        return self.send(
            grid.TABLE_KEY,
            {"op": "name", "kind": "scenario", "id": row_id, "text": text, "seen": shown},
        )

    def rename_revision(self, revision_id: str, text: str, *, seen: str | None = None) -> AppTest:
        rows = last(self.calls, grid.REVISIONS_KEY)["rows"]
        row = next(row for row in rows if row["id"] == revision_id)
        shown = seen if seen is not None else str(row.get("saved", row["name"]))
        return self.send(
            grid.REVISIONS_KEY,
            {"op": "name", "kind": "revision", "id": revision_id, "text": text, "seen": shown},
        )

    def move(self, row_id: str, before: str | None, *, order: tuple[str, ...]) -> AppTest:
        return self.send(
            grid.TABLE_KEY,
            {"op": "move", "id": row_id, "before": before, "token": order_token(order)},
        )

    def open(self, row_id: str, *, detail: bool = False) -> AppTest:
        op: dict[str, Any] = {"op": "open", "id": row_id}
        if detail:
            op["detail"] = True
        return self.send(grid.TABLE_KEY, op)

    def pick(self, owner: str, revision_id: str) -> AppTest:
        return self.send(grid.REVISIONS_KEY, {"op": "pick", "owner": owner, "id": revision_id})


def table_names(calls: Calls) -> list[str]:
    """목록 표가 마지막으로 그린 이름 — 표의 차례 그대로."""
    return [str(row["name"]) for row in last(calls, grid.TABLE_KEY)["rows"]]


def table_ids(calls: Calls) -> list[str]:
    return [str(row["id"]) for row in last(calls, grid.TABLE_KEY)["rows"]]


def table_row(calls: Calls, row_id: str) -> dict[str, Any]:
    return next(row for row in last(calls, grid.TABLE_KEY)["rows"] if row["id"] == row_id)
