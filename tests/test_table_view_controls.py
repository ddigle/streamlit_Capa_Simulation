# Purpose: 편집표의 보기 설정이 저장 대상 행을 잃지 않고 필터 표시명이 값을 바꾸지 않는지 검사한다.

from __future__ import annotations

import pandas as pd

from capa_simulation.components.table_view_controls import TableView, merge_edited_rows


def _fleet() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "설비명": ["E1", "E2", "E3", "E4"],
            "공정소분류": ["가", "나", "가", "나"],
            "비고": ["", "", "", ""],
        }
    )


def test_an_unfiltered_edit_is_the_whole_table() -> None:
    """필터가 없으면 편집표가 곧 전체 표다 — 행 추가·삭제가 살아 있어야 한다."""
    original = _fleet()
    edited = original.drop(index=1).copy()  # 사용자가 한 행을 지웠다
    edited.index = pd.RangeIndex(len(edited))

    merged = merge_edited_rows(original, edited, filtered=False)

    assert len(merged) == 3
    assert "E2" not in merged["설비명"].tolist()


def test_a_filtered_edit_never_drops_the_hidden_rows() -> None:
    """**이 검사가 이 모듈의 존재 이유다.**

    편집 결과가 곧 다음 불변 리비전의 전부다. 거른 편집표를 그대로 저장하면 걸러진 행이
    되돌릴 수 없이 사라진다.
    """
    original = _fleet()
    # 「가」만 보이게 거른다. `.loc` 라 원본 인덱스가 그대로 남는다.
    visible = original.loc[original["공정소분류"] == "가"]
    assert visible.index.tolist() == [0, 2]

    edited = visible.copy()
    edited.loc[0, "비고"] = "점검"

    merged = merge_edited_rows(original, edited, filtered=True)

    assert len(merged) == len(original)
    assert merged["설비명"].tolist() == ["E1", "E2", "E3", "E4"]
    assert merged.loc[0, "비고"] == "점검"
    # 보이지 않던 행은 글자 하나도 달라지지 않는다.
    pd.testing.assert_frame_equal(merged.loc[[1, 3]], original.loc[[1, 3]])


def test_editing_a_key_column_keeps_its_place() -> None:
    """키 컬럼을 고쳐도 자리를 잃지 않는다 — 인덱스로 맞추기 때문이다."""
    original = _fleet()
    visible = original.loc[[1]]
    edited = visible.copy()
    edited.loc[1, "설비명"] = "E2-renamed"

    merged = merge_edited_rows(original, edited, filtered=True)

    assert merged["설비명"].tolist() == ["E1", "E2-renamed", "E3", "E4"]


def test_a_filtered_view_locks_row_addition() -> None:
    """부분만 보이는 상태에서 「삭제」는 「지운다」와 「안 보인다」를 가를 수 없다."""
    assert TableView(_fleet(), filtered=True).row_mode == "fixed"
    assert TableView(_fleet(), filtered=False).row_mode == "dynamic"


def test_hidden_columns_become_a_column_config_of_none() -> None:
    """`column_config={컬럼: None}` 이 감추는 방법이다. 값은 반환 프레임에 그대로 남는다."""
    view = TableView(_fleet(), hidden_columns=("비고",), column_config={"비고": None})

    assert view.column_config == {"비고": None}


def _view_app() -> None:
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.editor_state import editor_widget_key
    from capa_simulation.components.table_view_controls import render_table_view_controls

    fleet = pd.DataFrame({"설비명": ["E1", "E2", "E3"], "공정소분류": ["가", "나", "가"]})
    render_table_view_controls(
        fleet, key_prefix="view_test", editor_key="view_test_editor", filter_columns=["공정소분류"]
    )
    st.session_state["seen_editor_key"] = editor_widget_key("view_test_editor")


def test_changing_the_visible_rows_rebuilds_the_editor_but_the_first_render_does_not() -> None:
    """보이는 행이 바뀌면 편집표를 **새 위젯으로** 세운다 — 세션 칸만 지우면 브라우저가 옛 편집을
    행 위치 그대로 다시 보내 다른 행에 붙는다(2026-09-29 2차 리뷰). 처음 그리는 회차에는 버릴
    것이 없어 그대로다.
    """
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_view_app).run()
    assert not app.exception
    assert app.session_state["seen_editor_key"] == "view_test_editor"

    app.run()
    assert app.session_state["seen_editor_key"] == "view_test_editor"

    app.multiselect(key="view_test_filter_공정소분류").set_value(["가"]).run()
    assert not app.exception
    assert app.session_state["seen_editor_key"] == "view_test_editor__g1"


def _labelled_filter_app() -> None:
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.table_view_controls import render_table_view_controls

    data = pd.DataFrame({"공정": ["DA", "DA2", "WB"], "Cutoff일수": [1.0, 2.0, 3.0]})
    if st.session_state.get("without_da", False):
        data = data.loc[data["공정"] != "DA"]
    view = render_table_view_controls(
        data,
        key_prefix="labelled_view",
        editor_key="labelled_view_editor",
        filter_columns=["공정"],
        locked_columns=["공정", "Cutoff일수"],
        # `DA2` 의 표시명이 다른 공정의 원본 `DA` 와 같다.
        value_labels={"공정": {"DA2": "DA"}},
    )
    st.session_state["visible_processes"] = list(view.frame["공정"])


def test_a_colliding_filter_label_still_filters_the_chosen_process() -> None:
    """Streamlit 1.63 multiselect 는 같은 글자 둘 중 첫째로 돌아온다 — `DA2` 를 골라도 `DA` 로
    걸렀다(병합 전 리뷰 재현). 겹친 선택지는 「표시명 (원본)」 으로 갈라 보인다."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_labelled_filter_app).run()
    assert not app.exception
    picker = app.multiselect(key="labelled_view_filter_공정")
    assert picker.options == ["DA", "DA (DA2)", "WB"]

    picker.set_value(["DA2"]).run()
    assert not app.exception
    assert app.session_state["labelled_view_filter_공정"] == ["DA2"]
    assert app.session_state["visible_processes"] == ["DA2"]


def test_a_held_filter_value_keeps_its_value_when_its_text_changes_in_the_browser() -> None:
    """원본 DA 가 없을 때 「DA」(= DA2)를 고른 뒤 DA 가 생기면 글자가 「DA (DA2)」 로 바뀐다 —
    매 회차 세션에 다시 적지 않으면 브라우저가 옛 글자로 DA 를 되살렸다(2026-10-10 재검증)."""
    from streamlit.testing.v1 import AppTest
    from widget_browser import BrowserChoice

    app = AppTest.from_function(_labelled_filter_app)
    app.session_state["without_da"] = True
    browser = BrowserChoice(app, "multiselect", "labelled_view_filter_공정")
    browser.start()
    browser.pick(["DA"])
    browser.run()
    assert app.session_state["labelled_view_filter_공정"] == ["DA2"]

    app.session_state["without_da"] = False
    for _ in range(3):
        browser.run()
        assert not app.exception
        assert app.session_state["labelled_view_filter_공정"] == ["DA2"]
        assert app.session_state["visible_processes"] == ["DA2"]
    assert browser.wire == ["DA (DA2)"]
