# Purpose: 분류 컬럼 필터가 겹친 공정 표시명을 가르고 글자가 바뀌어도 잡은 원본 값을 지키는지 본다.

"""`components/column_filter.py` 의 공정 필터.

산출 결과 소요대수·확보율, 기준 정보 설비대수, 월별 편집기 필터가 이 한 벌을 쓴다. Streamlit 1.63
multiselect 는 브라우저와 값을 **보이는 글자**로 주고받는다. 표시명이 다른 공정의 원본 이름과
같으면(DA2 → 「DA」) 고른 것과 다른 공정이 걸렸고, 글자가 회차마다 바뀌면 브라우저가 옛 글자를
되보내 잡은 선택이 바뀌거나 빠졌다. 일반 `AppTest.run()` 은 회차마다 세션 값으로 글자를 다시
만들어 보내므로 글자를 들고 다니는 `BrowserChoice` 로 잰다(2026-10-10 다른 화면 후속).
"""

from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest
from widget_browser import BrowserChoice

FILTER_KEY = "labelled_filter_공정"


def _filter_app() -> None:
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.column_filter import render_column_filter_controls

    data = pd.DataFrame(
        {
            "공정": ["DA", "DA2", "WB"],
            "Area_Name": ["Main", "Main", "MI"],
            "202608": [1.0, 2.0, 3.0],
        }
    )
    if st.session_state.get("without_da", False):
        data = data.loc[data["공정"] != "DA"]
    labels = st.session_state.get("labels", {"DA2": "DA"})
    filtered = render_column_filter_controls(
        data,
        ["공정", "Area_Name"],
        key_prefix="labelled_filter",
        value_labels={"공정": labels} if labels else None,
    )
    st.session_state["visible_processes"] = list(filtered["공정"])
    st.session_state["visible_index"] = filtered.index


def test_without_display_names_the_filter_keeps_its_texts_and_order() -> None:
    """표시명이 없으면 글자·차례가 예전 그대로다(데이터 차례)."""
    app = AppTest.from_function(_filter_app)
    app.session_state["labels"] = {}
    app.run()

    assert not app.exception
    assert app.multiselect(key=FILTER_KEY).options == ["DA", "DA2", "WB"]
    assert app.multiselect(key="labelled_filter_Area_Name").options == ["Main", "MI"]


def test_a_colliding_display_name_is_split_and_filters_the_chosen_process() -> None:
    """DA2 의 표시명이 원본 DA 와 같다 — 「DA (DA2)」 로 갈라 보이고 그 글자를 고르면 DA2 다."""
    app = AppTest.from_function(_filter_app)
    browser = BrowserChoice(app, "multiselect", FILTER_KEY)
    browser.start()
    assert not app.exception
    # 차례는 데이터 차례 그대로다(이 상자에는 「보이는 글자순」 규칙이 없었다).
    assert browser.options() == ["DA", "DA (DA2)", "WB"]

    browser.pick(["DA (DA2)"])
    browser.run()

    assert not app.exception
    assert app.session_state[FILTER_KEY] == ["DA2"]
    assert app.session_state["visible_processes"] == ["DA2"]


def test_a_held_filter_keeps_its_value_when_its_text_changes() -> None:
    """DA 가 없을 때 「DA」(= DA2)를 고른 뒤 DA 가 생기면 글자가 「DA (DA2)」 로 바뀐다 — 매 회차
    다시 적지 않으면 브라우저가 옛 글자 「DA」 로 원본 DA 를 되살렸다."""
    app = AppTest.from_function(_filter_app)
    app.session_state["without_da"] = True
    browser = BrowserChoice(app, "multiselect", FILTER_KEY)
    browser.start()
    browser.pick(["DA"])
    browser.run()
    assert app.session_state[FILTER_KEY] == ["DA2"]

    app.session_state["without_da"] = False
    for _ in range(3):
        browser.run()
        assert not app.exception
        assert app.session_state[FILTER_KEY] == ["DA2"]
        assert app.session_state["visible_processes"] == ["DA2"]
    assert browser.wire == ["DA (DA2)"]


def test_a_held_filter_survives_when_every_display_name_is_removed() -> None:
    """Admin 이 표시명을 모두 지우면 그 회차에 이 칸은 표시명이 없는 칸이 된다 — 그래도 잡은 값을
    다시 적어야 브라우저의 옛 글자 「가공」 이 걷혀 선택이 빠지지 않는다."""
    app = AppTest.from_function(_filter_app)
    app.session_state["labels"] = {"DA2": "가공"}
    browser = BrowserChoice(app, "multiselect", FILTER_KEY)
    browser.start()
    browser.pick(["가공"])
    browser.run()
    assert app.session_state[FILTER_KEY] == ["DA2"]

    app.session_state["labels"] = {}
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[FILTER_KEY] == ["DA2"]
        assert app.session_state["visible_processes"] == ["DA2"]
    assert browser.wire == ["DA2"]


def _apply_app() -> None:
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.column_filter import apply_column_filters

    data = pd.DataFrame({"공정": ["DA", "DA2", "WB"], "202608": [1.0, 2.0, 3.0]})
    filtered = apply_column_filters(data, ["공정"], key_prefix="labelled_filter")
    st.session_state["visible_processes"] = list(filtered["공정"])
    st.session_state["visible_index"] = filtered.index


def test_a_filter_that_keeps_every_row_returns_the_table_with_its_range_index() -> None:
    """모든 값을 고르면(「Select all」 로 다 담은 중간 상태) 원본 표 그대로다. `.loc` 로 거르면
    `RangeIndex` 가 일반 `Index` 로 바뀌어 숨은 인덱스 열이 더 실리고, 편집표는 인덱스 꼴이 위젯
    신원이라 새 위젯으로 서서 표 전체를 다시 보냈다. 하나라도 빼면 예전처럼 걸러진 행 번호다."""
    for app_function in (_filter_app, _apply_app):
        app = AppTest.from_function(app_function)
        app.session_state["labels"] = {}
        app.session_state[FILTER_KEY] = ["DA", "DA2", "WB"]
        app.run()

        assert not app.exception
        assert app.session_state["visible_processes"] == ["DA", "DA2", "WB"]
        assert isinstance(app.session_state["visible_index"], pd.RangeIndex)

        app.session_state[FILTER_KEY] = ["DA", "WB"]
        app.run()

        assert not app.exception
        assert app.session_state["visible_processes"] == ["DA", "WB"]
        assert app.session_state["visible_index"].tolist() == [0, 2]
