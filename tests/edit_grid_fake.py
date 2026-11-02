# Purpose: 범용 편집 그리드 대역 — 두 등록이 받은 data 를 적고 넣어 둔 출납을 콜백으로 보낸다.

"""AppTest 에서 범용 편집 그리드(`components/edit_grid`)를 흉내 내는 대역.

AppTest 는 그 JS 를 못 돌린다. 대역은 두 등록(`_GRID` 껍데기·`_FEED` feed)이 받은 (key, data)를
차례대로 목록에 적고, 세션 칸(`FAKE_EVENT_KEY`)에 넣어 둔 (호스트, 출납)을 그 마운트의 상태 값으로
적은 뒤 받은 `on_outbox_change` 콜백을 부른다. 진짜는 콜백이 회차 맨 앞에서 돌지만 대역은 그리는
자리에서 돈다 — `send_ops` 가 한 번 더 돌려 반영한 결과(feed 의 초안·ack)를 그린다. 출납 값은
진짜처럼 세션에 남는다(같은 출납이 다시 와도 seq 기억으로 한 번만 반영한다).
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import edit_grid

FAKE_EVENT_KEY = "test_fake_edit_grid_event"
Calls = list[tuple[str, dict[str, Any]]]
_SEQ = itertools.count(1)


def install_fake_edit_grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """두 등록을 대역으로 바꾸고 받은 (key, data) 목록을 돌려준다(그린 차례 그대로)."""
    calls: Calls = []

    def _grid(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        key = kwargs["key"]
        calls.append((key, kwargs["data"]))
        event = st.session_state.get(FAKE_EVENT_KEY)
        if isinstance(event, tuple) and event[0] == key:
            st.session_state.pop(FAKE_EVENT_KEY, None)
            st.session_state[key] = SimpleNamespace(outbox=event[1])
            callback = kwargs.get("on_outbox_change")
            if callback is not None:
                callback()
        return SimpleNamespace(outbox=None)

    def _feed(**kwargs: Any) -> None:
        calls.append((kwargs["key"], kwargs["data"]))

    monkeypatch.setattr(edit_grid, "_GRID", _grid)
    monkeypatch.setattr(edit_grid, "_FEED", _feed)
    return calls


def last(calls: Calls, key: str) -> dict[str, Any]:
    """그 key 가 마지막으로 받은 data."""
    return next(data for name, data in reversed(calls) if name == key)


def outbox(
    calls: Calls,
    *ops: dict[str, Any],
    host: str,
    table: str | None = None,
    gen: str | None = None,
    mount: str = "m-test",
) -> dict[str, Any]:
    """그 호스트의 마지막 feed 의 표·`gen` 으로 op 들을 출납 꼴로 묶는다(seq·at 은 늘 오른다)."""
    feed = last(calls, edit_grid.feed_key(host))
    numbered = []
    for op in ops:
        seq = next(_SEQ)
        numbered.append(
            {
                "seq": seq,
                "at": seq,
                "table": table if table is not None else feed["table"],
                "gen": gen if gen is not None else feed["gen"],
                **op,
            }
        )
    return {"mount": mount, "ops": numbered}


def send_outbox(app: AppTest, host: str, value: object) -> AppTest:
    """그 마운트에 출납 하나를 보내고(콜백) 반영한 결과를 그린 회차까지 돌린다."""
    app.session_state[FAKE_EVENT_KEY] = (host, value)
    app.run()
    assert not app.exception, app.exception
    return app.run()


def send_ops(
    app: AppTest,
    calls: Calls,
    *ops: dict[str, Any],
    host: str,
    table: str | None = None,
    gen: str | None = None,
    mount: str = "m-test",
) -> AppTest:
    """op 들을 그 호스트의 출납으로 보낸다(표·gen 은 마지막 feed 의 것 — 주면 그 값)."""
    return send_outbox(app, host, outbox(calls, *ops, host=host, table=table, gen=gen, mount=mount))
