# Purpose: 설비 마스터 표 컴포넌트 대역 — 받은 data 를 적고 넣어 둔 출납·트리거를 콜백으로 보낸다.

"""AppTest 에서 설비 마스터 표(`components/equipment_master_grid`)를 흉내 내는 대역.

AppTest 는 그 JS 를 못 돌린다. 대역은 마운트마다 받은 data 를 목록에 적고, 세션 칸
(`FAKE_EVENT_KEY`)에 넣어 둔 (key, 이름, 값)을 그 마운트 key 의 세션 값으로 적은 뒤 받은
`on_<이름>_change` 콜백을 부른다. 진짜는 콜백이 회차 맨 앞에서 돌지만 대역은 그리는 자리에서
돈다 — `send` 가 한 번 더 돌려 결과를 그린다. 출납 값은 진짜처럼 세션에 남는다(같은 출납이 다시
와도 seq 기억으로 한 번만 반영한다).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import equipment_master_grid as emg

FAKE_EVENT_KEY = "test_fake_grid_event"
Calls = list[tuple[str, dict[str, Any]]]
_SEQ = itertools.count(1)


def install_fake_grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """표 컴포넌트를 대역으로 바꾸고 받은 (key, data) 목록을 돌려준다."""
    calls: Calls = []

    def _fake(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        key = kwargs["key"]
        calls.append((key, kwargs["data"]))
        event = st.session_state.get(FAKE_EVENT_KEY)
        if isinstance(event, tuple) and event[0] == key:
            _, name, value = event
            st.session_state.pop(FAKE_EVENT_KEY, None)
            st.session_state[key] = SimpleNamespace(**{name: value})
            callback = kwargs.get(f"on_{name}_change")
            if callback is not None:
                callback()
        return SimpleNamespace(outbox=None)

    monkeypatch.setattr(emg, "_GRID", _fake)
    return calls


def last(calls: Calls, key: str) -> dict[str, Any]:
    """그 마운트가 마지막으로 받은 data."""
    return next(data for name, data in reversed(calls) if name == key)


def send(app: AppTest, key: str, name: str, value: object) -> AppTest:
    """그 마운트의 상태 값·트리거 하나를 보내고(콜백) 결과를 그린 회차까지 돌린다."""
    app.session_state[FAKE_EVENT_KEY] = (key, name, value)
    app.run()
    assert not app.exception, app.exception
    return app.run()


def outbox(calls: Calls, *ops: dict[str, Any], mount: str = "m-test") -> dict[str, Any]:
    """표가 마지막으로 받은 `base` 로 op 들을 출납 꼴로 묶는다(seq·at 은 늘 오른다)."""
    base = last(calls, emg.GRID_KEY)["base"]
    numbered = []
    for op in ops:
        seq = next(_SEQ)
        numbered.append({"seq": seq, "at": seq, "base": base, **op})
    return {"mount": mount, "ops": numbered}


def send_ops(app: AppTest, calls: Calls, *ops: dict[str, Any], key: str = emg.GRID_KEY) -> AppTest:
    """표(또는 오른쪽 칸 `key`)에서 op 들을 보낸다."""
    return send(app, key, "outbox", outbox(calls, *ops))


def load(app: AppTest, ids: Sequence[str], *, kind: str = "names", label: str = "") -> AppTest:
    """불러오기 트리거 — 브라우저가 찾은 행 id 를 보낸다."""
    return send(
        app, emg.LOADER_KEY, "load", {"kind": kind, "ids": list(ids), "missing": [], "label": label}
    )


def rows(calls: Calls) -> list[dict[str, Any]]:
    """표가 마지막으로 받은 줄(불러온 목록 차례)."""
    return list(last(calls, emg.GRID_KEY)["rows"])
