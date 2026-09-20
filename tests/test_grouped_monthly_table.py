# Purpose: grouped monthly table 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import plotly.graph_objects as go
import pytest

from capa_simulation.components.grouped_monthly_table import (
    _add_table_grid,
    _build_display_rows,
    _classification_fill_colors,
    _formatted_month_values,
    build_grouped_monthly_export,
)
from capa_simulation.components.monthly_table_base import (
    HEADER_HEIGHT_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
)
from capa_simulation.design import tokens
from capa_simulation.design.tokens import CLASSIFICATION_PRODUCT_TOTAL


def test_display_rows_insert_product_production_and_grand_totals() -> None:
    data = pd.DataFrame(
        {
            "양산구분": ["양산", "양산", "양산", "ER"],
            "제품정보": ["제품A", "제품A", "제품B", "제품A"],
            "Stack": ["8H", "12H", "8H", "8H"],
            "202608": [10.0, 30.0, 5.0, 2.0],
            "202609": [20.0, 40.0, 0.0, 3.0],
        }
    )

    display = _build_display_rows(
        data,
        ["양산구분", "제품정보", "Stack"],
        ["202608", "202609"],
    )

    assert display.row_types == [
        "grand_total",
        "detail",
        "detail",
        "product_total",
        "detail",
        "product_total",
        "production_total",
        "detail",
        "product_total",
        "production_total",
    ]
    assert display.product_total_rows == [3, 5, 8]
    assert display.production_total_rows == [6, 9]
    assert display.grand_total_row == 0
    assert display.classification_values[0][0] == "전체\u00a0합계"
    assert display.classification_values[1][3] == "Total"
    assert display.classification_values[0][6] == "양산\u00a0Total"
    assert display.classification_values[0][9] == "ER\u00a0Total"
    assert display.month_values[0] == [47.0, 63.0]
    assert display.month_values[3] == [40.0, 60.0]
    assert display.month_values[6] == [45.0, 60.0]
    assert display.month_values[9] == [2.0, 3.0]

    formatted = _formatted_month_values(display, month_count=2, decimal_places=0)
    assert formatted[0][0] == "47"
    assert formatted[0][3] == "40"
    assert formatted[1][5] == ""

    export = build_grouped_monthly_export(
        data,
        classification_columns=["양산구분", "제품정보", "Stack"],
        column_labels={"양산구분": "양산", "제품정보": "제품"},
    )
    assert export.columns.tolist() == ["양산", "제품", "Stack", "26.08", "26.09"]
    assert export.loc[0, "양산"] == "전체 합계"
    assert export.loc[3, "제품"] == "Total"
    assert export.loc[6, "양산"] == "양산 Total"
    assert export.loc[0, "26.08"] == 47.0
    assert pd.isna(export.loc[5, "26.09"])

    fill_colors = _classification_fill_colors(
        display,
        ["양산구분", "제품정보", "Stack"],
    )
    assert fill_colors[0][3] == tokens.SURFACE_CLASSIFICATION
    assert fill_colors[0][8] == tokens.SURFACE_CLASSIFICATION_GROUP
    assert fill_colors[1][3] == CLASSIFICATION_PRODUCT_TOTAL


def test_group_boundaries_are_drawn_after_total_rows() -> None:
    label_figure = go.Figure()
    month_figure = go.Figure()
    product_total_rows = [3, 5, 8]
    production_total_rows = [6, 9]
    row_count = 10

    _add_table_grid(
        label_figure=label_figure,
        month_figure=month_figure,
        classification_widths=[100, 100, 100],
        month_columns=["202601"],
        product_total_rows=product_total_rows,
        production_total_rows=production_total_rows,
        grand_total_row=0,
        row_count=row_count,
    )

    table_height = HEADER_HEIGHT_PX + row_count * ROW_HEIGHT_PX
    product_boundaries = [
        float(shape.y0)
        for shape in label_figure.layout.shapes
        if shape.type == "line" and shape.y0 == shape.y1 and shape.line.width == 1.0
    ]
    production_boundaries = [
        float(shape.y0)
        for shape in label_figure.layout.shapes
        if shape.type == "line" and shape.y0 == shape.y1 and shape.line.width == 1.4
    ]
    emphasized_boundaries = [
        float(shape.y0)
        for shape in label_figure.layout.shapes
        if shape.type == "line" and shape.y0 == shape.y1 and shape.line.width == 1.8
    ]
    month_emphasized_boundaries = [
        float(shape.y0)
        for shape in month_figure.layout.shapes
        if shape.type == "line" and shape.y0 == shape.y1 and shape.line.width == 1.8
    ]

    # 바깥 테두리는 두 Figure 모두 폭 OUTER_BORDER_WIDTH_PX * 2 인 선이다. 분류 영역에만
    # 있던 폭 1.8 rect 는 뒤이어 그리는 폭 3.6 선이 네 변을 모두 덮어 화면에 나타나지
    # 않았으므로 제거했다. 상세 검증은 tests/test_monthly_table_grid.py 에 있다.
    for figure in (label_figure, month_figure):
        assert figure.layout.shapes[0].type == "line"
        assert figure.layout.shapes[0].line.width == OUTER_BORDER_WIDTH_PX * 2
    assert not [shape for shape in label_figure.layout.shapes if shape.type == "rect"]

    assert product_boundaries == pytest.approx(
        [
            1 - (HEADER_HEIGHT_PX + (row + 1) * ROW_HEIGHT_PX) / table_height
            for row in product_total_rows
        ]
    )
    assert production_boundaries == pytest.approx(
        [
            1 - (HEADER_HEIGHT_PX + (row + 1) * ROW_HEIGHT_PX) / table_height
            for row in production_total_rows
        ]
    )
    assert emphasized_boundaries == pytest.approx(
        [
            1 - HEADER_HEIGHT_PX / table_height,
            1 - (HEADER_HEIGHT_PX + ROW_HEIGHT_PX) / table_height,
        ]
    )
    assert month_emphasized_boundaries == pytest.approx(emphasized_boundaries)
