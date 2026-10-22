# Purpose: 필요 단축 일정 강조 공정·보드 줄 고르기·상세 링크 인자·기한 임박 표 빈칸을 검사한다.

"""`components/shortening_board.py` 의 세션·주소 계약.

AppTest 는 `st.dataframe` 의 줄 고르기를 재현하지 못한다 — 콜백(`_pick_board_row`)이 읽는 선택
상태를 세션에 넣고 부른다. 화면 전체는 `test_required_shortening_tab.py` 가 본다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_shortening_watch import TODAY, _level

from capa_simulation.components.shortening_board import (
    HIGHLIGHT_FROM_BOARD,
    HIGHLIGHT_FROM_DETAIL,
    SHORTENING_HIGHLIGHT_KEY,
    ShorteningHighlight,
    detail_link_params,
    highlight_badge,
    highlight_first,
)


def _highlight_app() -> None:
    import streamlit as st

    from capa_simulation.components.shortening_board import (
        _pick_board_row,
        clear_highlight,
        current_highlight,
    )

    action = st.session_state.pop("test_action", None)
    if action == "pick":
        st.session_state["test_board"] = {"selection": {"rows": [1], "columns": []}}
        _pick_board_row(("DEMO_A", "DEMO_B"), "test_board")
    elif action == "pick-outside":
        st.session_state["test_board"] = {"selection": {"rows": [7], "columns": []}}
        _pick_board_row(("DEMO_A",), "test_board")
    elif action == "clear":
        clear_highlight()
    st.session_state["test_highlight"] = current_highlight()


def test_a_board_pick_highlights_that_process_and_renews_the_table_key() -> None:
    app = AppTest.from_function(_highlight_app).run()
    assert app.session_state["test_highlight"] is None

    app.session_state["test_action"] = "pick"
    app.run()
    assert not app.exception
    assert app.session_state[SHORTENING_HIGHLIGHT_KEY] == ("DEMO_B", HIGHLIGHT_FROM_BOARD)
    assert app.session_state["test_highlight"] == ShorteningHighlight(
        "DEMO_B", HIGHLIGHT_FROM_BOARD
    )
    assert app.session_state["equipment_shortening_board_generation"] == 1

    # 범위 밖 줄은 강조를 바꾸지 않는다(세대만 오른다).
    app.session_state["test_action"] = "pick-outside"
    app.run()
    assert app.session_state[SHORTENING_HIGHLIGHT_KEY] == ("DEMO_B", HIGHLIGHT_FROM_BOARD)
    assert app.session_state["equipment_shortening_board_generation"] == 2

    app.session_state["test_action"] = "clear"
    app.run()
    assert SHORTENING_HIGHLIGHT_KEY not in app.session_state
    assert app.session_state["test_highlight"] is None


def test_a_malformed_highlight_is_ignored() -> None:
    app = AppTest.from_function(_highlight_app)
    app.session_state[SHORTENING_HIGHLIGHT_KEY] = ("DEMO_A", "어딘가")
    app.run()
    assert app.session_state["test_highlight"] is None
    app.session_state[SHORTENING_HIGHLIGHT_KEY] = "DEMO_A"
    app.run()
    assert app.session_state["test_highlight"] is None


def test_the_highlight_goes_first_and_names_where_it_came_from() -> None:
    detail = ShorteningHighlight("DEMO_C", HIGHLIGHT_FROM_DETAIL)
    assert highlight_first(["DEMO_A", "DEMO_C", "DEMO_B"], detail) == ["DEMO_C", "DEMO_A", "DEMO_B"]
    # 목록에 없어도 맨 앞에 선다(보이는 범위 밖 공정).
    assert highlight_first(["DEMO_A"], detail) == ["DEMO_C", "DEMO_A"]
    assert highlight_first(["DEMO_A"], None) == ["DEMO_A"]
    assert highlight_badge(detail) == "공정 Capa 상세에서 연 공정"
    assert highlight_badge(ShorteningHighlight("DEMO_C", HIGHLIGHT_FROM_BOARD)) == (
        "진척 보드에서 고른 공정"
    )


def test_the_detail_link_carries_the_card_first_shortage_month_target_period_and_counts() -> None:
    params = detail_link_params(
        _level(), "DEMO_A", level=1.1, months=[202605, 202606, 202607], theme=None
    )
    assert params == {
        "process": "DEMO_A",
        "month": "202606",
        "from": "shortening",
        "target": "1.1",
        "period": "202605-202607",
        "shortened": "2",
        "new": "1",
    }
    # 모자란 달이 없으면 달을 싣지 않는다.
    satisfied = detail_link_params(_level(), "DEMO_C", level=1.1, months=[202605], theme="dark")
    assert "month" not in satisfied and satisfied["theme"] == "dark"
    assert TODAY < date(2026, 6, 1)


def _imminent_app() -> None:
    from test_shortening_watch import TODAY, _level

    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.components.shortening_board import _render_imminent

    _render_imminent(
        _level(),
        ["DEMO_A", "DEMO_B"],
        today=TODAY,
        days=60,
        labels=ProcessLabels(),
        managers={"DEMO-A2": "DEMO 담당"},
    )


def test_the_imminent_table_draws_empty_cells_as_a_dash_like_the_delayed_table() -> None:
    """신규(추가N) 줄의 단축일수·담당자 없는 칸은 「None」 글자가 아니라 「—」 다(이행 지연 표와
    같다).

    Streamlit 1.63 `st.dataframe` 은 `placeholder` 를 주지 않으면 결측 칸에 「None」 을 그린다.
    """
    app = AppTest.from_function(_imminent_app).run()

    assert not app.exception, [item.message for item in app.exception]
    # 고름이 없는 `st.dataframe` 은 key 를 요소 id 에 싣지 않는다 — 이 앱의 표는 하나다.
    (table,) = app.dataframe
    assert table.proto.HasField("placeholder") and table.proto.placeholder == "—"
    frame = table.value
    assert isinstance(frame, pd.DataFrame)
    new = frame.loc[frame["호기"].eq("추가1")]
    assert len(new) == 1 and pd.isna(new["단축일수"].iloc[0])
    managers = frame.set_index("호기")["담당자"]
    assert managers["DEMO-A2"] == "DEMO 담당" and pd.isna(managers["DEMO-B1"])
