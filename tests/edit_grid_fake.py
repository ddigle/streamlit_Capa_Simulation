# Purpose: 범용 편집 그리드 대역 — 두 등록이 받은 data 를 적고 넣어 둔 출납을 콜백으로 보낸다.

"""AppTest 에서 범용 편집 그리드(`components/edit_grid`)를 흉내 내는 대역.

AppTest 는 그 JS 를 못 돌린다. 대역은 두 등록(`_GRID` 껍데기·`_FEED` feed)이 받은 (key, data)를
차례대로 목록에 적고, 세션 칸(`FAKE_EVENT_KEY`)에 넣어 둔 (호스트, 출납)을 그 마운트의 상태 값으로
적은 뒤 받은 `on_outbox_change` 콜백을 부른다. 출납 값은 진짜처럼 세션에 남는다(같은 출납이 다시
와도 seq 기억으로 한 번만 반영한다).

콜백을 부르는 때는 둘이다.

- **기본** — 그리는 자리에서 부른다. 진짜는 콜백이 회차 맨 앞에서 돈다 — `send_ops` 가 한 번 더
  돌려 반영한 결과(feed 의 초안·ack)를 그린다.
- **`early=True`** — 진짜처럼 회차 맨 앞(대본 전)에서 부른다. Streamlit 이 위젯 콜백을 부르는 자리
  (`SafeSessionState.on_script_will_rerun`) 바로 뒤에, 앞 회차에 그 key 로 그려진 그리드가 받은
  콜백을 부른다. 그 회차에 페이지 **앞**에서 잰 세션 값이 진짜 회차의 사이드바·화면 탭 점 자리다
  (`app.py` 는 페이지보다 먼저 그린다) — 「페이지 앞에서 그린 표지가 한 회차 늦는다」 를 본다.
  보낼 때는 `deliver_ops`(한 회차)를 쓴다.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import streamlit as st
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest

from capa_simulation.components import edit_grid
from capa_simulation.services.edit_grid import DUPLICATE_SEPARATOR, KEY_SEPARATOR
from capa_simulation.services.edit_grid_payload import CODE_ALPHABET

FAKE_EVENT_KEY = "test_fake_edit_grid_event"
Calls = list[tuple[str, dict[str, Any]]]
_SEQ = itertools.count(1)


def _deliver(key: str, value: object, callback: Callable[[], None] | None) -> None:
    """출납을 그 마운트의 상태 값으로 적고 콜백을 부른다."""
    st.session_state.pop(FAKE_EVENT_KEY, None)
    st.session_state[key] = SimpleNamespace(outbox=value)
    if callback is not None:
        callback()


def install_fake_edit_grid(monkeypatch: pytest.MonkeyPatch, *, early: bool = False) -> Calls:
    """두 등록을 대역으로 바꾸고 받은 (key, data) 목록을 돌려준다(그린 차례 그대로).

    `early` 면 출납 콜백을 회차 맨 앞에서 부른다(모듈 설명)."""
    calls: Calls = []
    callbacks: dict[str, Callable[[], None]] = {}

    def _grid(**kwargs: Any) -> SimpleNamespace:
        key = kwargs["key"]
        calls.append((key, kwargs["data"]))
        callback = kwargs.get("on_outbox_change")
        if callback is not None:
            callbacks[key] = callback
        event = st.session_state.get(FAKE_EVENT_KEY)
        if not early and isinstance(event, tuple) and event[0] == key:
            _deliver(key, event[1], callback)
        return SimpleNamespace(outbox=None)

    def _feed(**kwargs: Any) -> None:
        calls.append((kwargs["key"], kwargs["data"]))

    monkeypatch.setattr(edit_grid, "_GRID", _grid)
    monkeypatch.setattr(edit_grid, "_FEED", _feed)
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


def deliver_ops(
    app: AppTest,
    calls: Calls,
    *ops: dict[str, Any],
    host: str,
    table: str | None = None,
    gen: str | None = None,
    mount: str = "m-test",
) -> AppTest:
    """`early=True` 대역에서 op 들을 보내고 **그 한 회차**만 돌린다 — 진짜처럼 콜백이 회차 맨 앞에서
    돌고 같은 회차 본문이 반영한다(본문이 `st.rerun()` 하면 AppTest 가 그 회차까지 이어 돈다). 표·
    gen 은 마지막 feed 의 것 — 주면 그 값."""
    value = outbox(calls, *ops, host=host, table=table, gen=gen, mount=mount)
    app.session_state[FAKE_EVENT_KEY] = (host, value)
    app.run()
    assert not app.exception, app.exception
    return app


def _decoded(text: str, width: int) -> list[int]:
    """고정 폭 64 진 글자 → 번호 목록(`edit_grid_payload.encode_codes` 의 거꾸로)."""
    base = len(CODE_ALPHABET)
    numbers = []
    for start in range(0, len(text), width):
        number = 0
        for char in text[start : start + width]:
            number = number * base + CODE_ALPHABET.index(char)
        numbers.append(number)
    return numbers


def shell_frame(shell: dict[str, Any]) -> pd.DataFrame:
    """껍데기 본문을 표로 푼다 — 분류 칸(원값) + 값 칸(빈칸 None). 줄 차례는 그리드 차례다."""
    columns: dict[str, list[Any]] = {}
    for position, column in enumerate(shell["keyCols"]):
        codes = _decoded(shell["codes"][position], shell["codeWidths"][position])
        columns[str(column["name"])] = [shell["dims"][position][code] for code in codes]
    width = int(shell["valWidth"])
    rows: list[list[Any]] = []
    for runs in shell["runs"]:
        line: list[Any] = []
        for start in range(0, len(runs), width + 1):
            code = _decoded(runs[start : start + width], width)[0]
            length = CODE_ALPHABET.index(runs[start + width])
            line.extend([shell["vals"][code]] * length)
        rows.append(line)
    values = pd.DataFrame(rows, columns=list(shell["valueCols"]), dtype=object)
    return pd.concat([pd.DataFrame(columns), values], axis=1)


def shell_key(shell: dict[str, Any], row: int) -> str:
    """그 줄의 업무 키(분류 원값을 `KEY_SEPARATOR` 로 잇고 같은 키 둘째부터 꼬리표 —
    `services.edit_grid.row_keys` 와 같다)."""
    frame = shell_frame(shell)
    names = [str(column["name"]) for column in shell["keyCols"]]
    key = KEY_SEPARATOR.join(str(frame.iloc[row][name]) for name in names)
    for at, count in shell.get("dupes", []):
        if at == row:
            key = f"{key}{DUPLICATE_SEPARATOR}{count}"
    return key
