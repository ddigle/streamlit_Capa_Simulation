# Purpose: hierarchical monthly table 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

import pandas as pd
import plotly.graph_objects as go
import pytest

from capa_simulation.components.hierarchical_monthly_table import (
    _HEADER_HEIGHT_PX,
    _OUTER_BORDER_WIDTH_PX,
    _ROW_HEIGHT_PX,
    _add_table_grid,
    _build_hierarchical_display,
    _formatted_month_values,
    build_hierarchical_monthly_export,
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

    table_height = _HEADER_HEIGHT_PX + len(data) * _ROW_HEIGHT_PX
    group_y_values = [
        1 - (_HEADER_HEIGHT_PX + row_index * _ROW_HEIGHT_PX) / table_height
        for row_index in (1, 2, 3)
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
        [_OUTER_BORDER_WIDTH_PX, 0.8]
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
