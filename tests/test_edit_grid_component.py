# Purpose: 범용 편집 그리드 래퍼를 시험 앱(대역)으로 돌려 출납 반영·ack·되돌리기·표 바꿈을 본다.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from edit_grid_fake import (
    FAKE_EVENT_KEY,
    Calls,
    install_fake_edit_grid,
    last,
    outbox,
    send_ops,
    send_outbox,
)
from streamlit.testing.v1 import AppTest

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg

DEMO = str(Path(__file__).with_name("edit_grid_demo_app.py"))
HOST = "demo_grid"
FEED = edit_grid.feed_key(HOST)
SMALL_CELLS = "demo_grid_cells__DEMO_SMALL"
SMALL_HISTORY = "demo_grid_history__DEMO_SMALL"
KEY_ONE = "DEMO_P01\x1f양산"


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, Calls]:
    calls = install_fake_edit_grid(monkeypatch)
    app = AppTest.from_file(DEMO, default_timeout=60).run()
    assert not app.exception, app.exception
    return app, calls


def _write(value: Any, *, row: str = KEY_ONE, month: str = "202701") -> dict[str, Any]:
    return {"op": "write", "rows": [row], "cols": [month], "values": [[value]]}


def test_the_feed_and_the_grid_mount_in_a_fixed_order_with_fixed_keys(
    started: tuple[AppTest, Calls],
) -> None:
    app, calls = started
    assert [key for key, _ in calls] == [FEED, HOST]
    shell = last(calls, HOST)
    feed = last(calls, FEED)
    assert shell["table"] == "DEMO_SMALL" and shell["host"] == HOST
    assert shell["baseKey"] == feed["baseKey"] and feed["table"] == "DEMO_SMALL"
    assert feed["gen"] and feed["acks"] == {} and feed["drows"] == []
    assert shell["palette"] == edit_grid.palette()
    assert shell["texts"]["changes"] == "적용 전 변경"
    assert edit_grid.hide_feed_style(HOST) == "<style>.st-key-demo_grid__feed{display:none}</style>"


def test_an_outbox_edit_lands_in_the_draft_and_comes_back_with_its_ack(
    started: tuple[AppTest, Calls],
) -> None:
    app, calls = started
    value = outbox(calls, _write("50%"), host=HOST)
    seq = value["ops"][0]["seq"]
    send_outbox(app, HOST, value)
    feed = last(calls, FEED)
    assert feed["acks"] == {"m-test": seq}
    assert feed["counts"] == {"cells": 1, "rows": 1, "errors": 0}
    assert feed["undo"] == 1 and feed["dvals"] == [0.5]
    assert app.session_state[SMALL_CELLS] == {"cells": {KEY_ONE: {"202701": 0.5}}, "bad": {}}
    assert not app.button(key="demo_apply").disabled
    # 같은 출납이 다시 와도(가장 새 값 상태가 다음 회차에 또 실림) seq 기억으로 한 번만 반영한다.
    send_outbox(app, HOST, value)
    assert last(calls, FEED)["undo"] == 1


def test_an_error_stays_in_its_cell_and_reaches_the_feed(started: tuple[AppTest, Calls]) -> None:
    app, calls = started
    send_ops(app, calls, _write("85"), host=HOST)
    feed = last(calls, FEED)
    assert feed["bad"] == [[0, 0, "85", "max"]] and feed["badCount"] == 1
    assert feed["counts"]["errors"] == 1
    assert "85% 는 0.85" in last(calls, HOST)["texts"]["errors"]["max"]


def test_an_op_from_an_old_generation_is_dropped_and_told(started: tuple[AppTest, Calls]) -> None:
    app, calls = started
    send_ops(app, calls, _write("50%"), host=HOST, gen="old-gen")
    feed = last(calls, FEED)
    assert feed["drows"] == [] and feed["acks"]
    assert feed["toast"] == {"id": 1, "text": eg.DROPPED_TOAST.format(n="1")}
    send_ops(app, calls, {"op": "undo"}, host=HOST)
    assert last(calls, FEED)["toast"] == {"id": 2, "text": eg.UNDO_EMPTY_TOAST}


def test_undo_and_redo_travel_through_the_outbox(started: tuple[AppTest, Calls]) -> None:
    app, calls = started
    send_ops(app, calls, _write("50%"), _write("60%", month="202702"), host=HOST)
    assert last(calls, FEED)["counts"]["cells"] == 2
    send_ops(app, calls, {"op": "undo"}, host=HOST)
    feed = last(calls, FEED)
    assert feed["counts"]["cells"] == 1 and feed["undo"] == 1 and feed["redo"] == 1
    send_ops(app, calls, {"op": "redo"}, host=HOST)
    assert last(calls, FEED)["counts"]["cells"] == 2


def test_switching_tables_keeps_the_mount_and_each_tables_draft(
    started: tuple[AppTest, Calls],
) -> None:
    """표를 바꿔도 그리드 key·자리가 같고(다시 마운트되지 않는다) 표마다 초안이 남는다. 지금 그리지
    않는 표의 op 도 op 의 `table` 로 그 표 초안에 쓴다."""
    app, calls = started
    send_ops(app, calls, _write("50%"), host=HOST)
    gen_small = last(calls, FEED)["gen"]
    app.segmented_control(key="demo_table").set_value("DEMO_BIG").run()
    assert not app.exception, app.exception
    shell = last(calls, HOST)
    assert shell["table"] == "DEMO_BIG" and shell["valueHelp"]
    assert [key for key, _ in calls[-2:]] == [FEED, HOST]
    assert last(calls, FEED)["drows"] == []
    send_ops(
        app, calls, _write("40%", month="202703"), host=HOST, table="DEMO_SMALL", gen=gen_small
    )
    cells = app.session_state[SMALL_CELLS]["cells"]
    assert cells[KEY_ONE] == {"202701": 0.5, "202703": 0.4}
    app.segmented_control(key="demo_table").set_value("DEMO_SMALL").run()
    feed = last(calls, FEED)
    assert feed["table"] == "DEMO_SMALL" and feed["counts"]["cells"] == 2


def test_applying_merges_the_draft_and_starts_a_new_generation(
    started: tuple[AppTest, Calls],
) -> None:
    app, calls = started
    send_ops(app, calls, _write("50%"), host=HOST)
    before = last(calls, HOST)["baseKey"]
    old_gen = last(calls, FEED)["gen"]
    app.button(key="demo_apply").click().run()
    assert not app.exception, app.exception
    assert SMALL_CELLS not in app.session_state
    feed = last(calls, FEED)
    assert feed["gen"] != old_gen and feed["counts"]["cells"] == 0
    assert last(calls, HOST)["baseKey"] != before
    # 적용 전에 보낸 옛 세대 op 는 버려진다.
    send_ops(app, calls, _write("70%"), host=HOST, gen=old_gen)
    assert last(calls, FEED)["counts"]["cells"] == 0


def test_the_callback_only_queues_and_the_body_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """콜백은 inbox 에 쌓기만 하고(무거운 일 없음) 반영은 본문 — 대역은 그리는 자리에서 콜백을
    부르므로
    그 회차의 feed 에는 아직 없고 다음 회차에 실린다."""
    calls = install_fake_edit_grid(monkeypatch)
    app = AppTest.from_file(DEMO, default_timeout=60).run()
    app.session_state[FAKE_EVENT_KEY] = (HOST, outbox(calls, _write("50%"), host=HOST))
    app.run()
    assert len(app.session_state["demo_grid_inbox"]) == 1
    assert last(calls, FEED)["counts"]["cells"] == 0
    app.run()
    assert "demo_grid_inbox" not in app.session_state
    assert last(calls, FEED)["counts"]["cells"] == 1
