# Purpose: hierarchical monthly table 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1.element_tree import Block, Node

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.hierarchical_monthly_table import (
    _add_table_grid,
    _build_hierarchical_display,
    _formatted_month_values,
    build_hierarchical_monthly_export,
)
from capa_simulation.components.monthly_table_base import (
    HEADER_HEIGHT_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
)


def test_hierarchical_display_omits_repeated_prefix_values() -> None:
    classifications = ["공정", "소요기준", "양산구분", "제품정보", "Stack", "WF 구분"]
    data = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A", "Process-A", "Process-B"],
            "소요기준": ["WF", "WF", "WF", "CHIP"],
            "양산구분": ["양산", "양산", "양산", "양산"],
            "제품정보": ["Product-A", "Product-A", "Product-B", "Product-A"],
            "Stack": ["12H", "12H", "12H", "12H"],
            "WF 구분": ["Core", "Top", "Core", "Core"],
        }
    )

    display = _build_hierarchical_display(data, classifications)

    assert display.classification_values[0] == ["Process-A", "", "", "Process-B"]
    assert display.classification_values[1] == ["WF", "", "", "CHIP"]
    assert display.classification_values[3] == ["Product-A", "", "Product-B", "Product-A"]
    assert display.group_boundaries == [(1, 5), (2, 3), (3, 0)]
    assert display.top_group_indices == [0, 0, 0, 1]


def test_hierarchical_grid_draws_group_and_quarter_boundaries() -> None:
    classifications = ["공정", "소요기준", "양산구분", "제품정보", "Stack", "WF 구분"]
    data = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A", "Process-A", "Process-B"],
            "소요기준": ["WF", "WF", "WF", "CHIP"],
            "양산구분": ["양산", "양산", "양산", "양산"],
            "제품정보": ["Product-A", "Product-A", "Product-B", "Product-A"],
            "Stack": ["12H", "12H", "12H", "12H"],
            "WF 구분": ["Core", "Top", "Core", "Core"],
        }
    )
    display = _build_hierarchical_display(data, classifications)
    label_figure = go.Figure()
    month_figure = go.Figure()

    _add_table_grid(
        label_figure=label_figure,
        month_figure=month_figure,
        display=display,
        classification_widths=[100] * len(classifications),
        month_columns=["202603", "202604", "202605"],
        row_count=len(data),
    )

    table_height = HEADER_HEIGHT_PX + len(data) * ROW_HEIGHT_PX
    group_y_values = [
        1 - (HEADER_HEIGHT_PX + row_index * ROW_HEIGHT_PX) / table_height for row_index in (1, 2, 3)
    ]
    label_group_shapes = [
        shape
        for shape in label_figure.layout.shapes
        if shape.type == "line"
        and any(abs(float(shape.y0) - expected) < 1e-9 for expected in group_y_values)
    ]
    assert [float(shape.x0) for shape in label_group_shapes] == pytest.approx([5 / 6, 3 / 6, 0])

    vertical_month_shapes = [
        shape
        for shape in month_figure.layout.shapes
        if shape.type == "line"
        and shape.x0 == shape.x1
        and shape.y0 == 0
        and shape.y1 == 1
        and 0 < float(shape.x0) < 1
    ]
    assert [float(shape.x0) for shape in vertical_month_shapes] == pytest.approx([1 / 3, 2 / 3])
    assert [float(shape.line.width) for shape in vertical_month_shapes] == pytest.approx(
        [OUTER_BORDER_WIDTH_PX, 0.8]
    )


def test_hierarchical_month_values_render_zero_and_missing_as_blank() -> None:
    data = pd.DataFrame({"202608": [100.25, 0.0, None]})

    values = _formatted_month_values(data, ["202608"], decimal_places=1)

    assert values == [["100.2", "", ""]]


def test_hierarchical_month_values_support_percent_format() -> None:
    data = pd.DataFrame({"202608": [1.095, 0.995, None]})

    values = _formatted_month_values(
        data,
        ["202608"],
        decimal_places=2,
        value_format="percent",
    )

    assert values == [["109.50%", "99.50%", ""]]


def test_hierarchical_export_matches_grouping_labels_and_percent_display() -> None:
    data = pd.DataFrame(
        {
            "공정": ["Process A", "Process A", "Process B"],
            "WF 구분": ["Core", "Top", "Core"],
            "202608": [1.095, 0.0, None],
        }
    )

    result = build_hierarchical_monthly_export(
        data,
        classification_columns=["공정", "WF 구분"],
        column_labels={"WF 구분": "속성"},
        decimal_places=2,
        value_format="percent",
    )

    assert result.columns.tolist() == ["공정", "속성", "26.08"]
    assert result["공정"].tolist() == ["Process A", "", "Process B"]
    assert result["속성"].tolist() == ["Core", "Top", "Core"]
    assert result["26.08"].tolist() == ["109.50%", "", ""]


def _paged_table_app() -> None:
    import pandas as pd
    import streamlit as st

    from capa_simulation.components.hierarchical_monthly_table import (
        render_hierarchical_monthly_table,
    )

    rows = int(st.session_state.get("paged_table_rows", 2))
    data = pd.DataFrame(
        {
            "공정": [f"Process-{index}" for index in range(rows)],
            "202608": [float(index) for index in range(rows)],
            "202609": [float(index + 1) for index in range(rows)],
        }
    )
    render_hierarchical_monthly_table(
        data,
        classification_columns=["공정"],
        column_labels={},
        decimal_places=0,
        key="paged_table",
        page_size=2,
    )


def _first_path(node: Block | Node, element_type: str) -> tuple[int, ...] | None:
    if not isinstance(node, Block):
        return () if node.type == element_type else None
    for index, child in node.children.items():
        found = _first_path(child, element_type)
        if found is not None:
            return (index, *found)
    return None


def test_the_row_pager_does_not_move_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """행 페이지 줄(「표시 범위」·쪽수)은 행이 `page_size` 를 넘을 때만 생긴다. 생겨도 표의 자리는
    같아야 한다 — 밀리면 가로 스크롤 컴포넌트가 다시 마운트되어 스크롤 위치를 잃는다."""
    from streamlit.testing.v1 import AppTest

    # AppTest 에는 Components v2 등록이 없다. 스크롤바는 빼고 표의 자리만 본다.
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    app = AppTest.from_function(_paged_table_app).run()
    assert not app.exception
    assert not app.selectbox
    without_pager = _first_path(app.main, "plotly_chart")

    app.session_state["paged_table_rows"] = 3
    app.run()
    assert not app.exception
    assert [widget.label for widget in app.selectbox] == ["표시 범위"]
    with_pager = _first_path(app.main, "plotly_chart")

    assert without_pager is not None
    assert with_pager == without_pager
