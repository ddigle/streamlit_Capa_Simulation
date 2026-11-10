# Purpose: 월 표 두 종류의 공용 격자 머리 · 반복 접두 생략이 예전 두 벌과 같은 결과인지 고정한다.

"""두 월별 표가 각자 적던 격자 머리 여섯 호출과 반복 접두 생략 루프를 `monthly_table_base` 의
`add_table_frame` · `blank_repeated_prefixes` 로 올렸다. 예전 꼴을 여기 그대로 두고 새 길과
견준다.

격자는 Figure 를 `to_json()` 글자로 견준다 — `0` 과 `0.0` 은 dict 비교로는 같지만 JSON 바이트가
다르다(분류 Figure 의 생산 소계 선 `x0` 는 정수, 계층 표의 첫 칸 선 `x0` 는 나눗셈 실수다).
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import accumulate, product
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest

from capa_simulation.components import grouped_monthly_table as grouped
from capa_simulation.components import hierarchical_monthly_table as hierarchical
from capa_simulation.components.monthly_table_base import (
    HEADER_HEIGHT_PX,
    OUTER_BORDER_WIDTH_PX,
    ROW_HEIGHT_PX,
    add_classification_boundaries,
    add_header_rule,
    add_month_boundaries,
    add_outer_border,
    blank_repeated_prefixes,
    classification_cell_text,
    header_boundary_ratio,
    table_height_px,
)
from capa_simulation.components.plotly_layout import append_layout_items, flush_layout_items
from capa_simulation.design import tokens


def _legacy_blank(raw_values: list[list[str]]) -> list[list[str]]:
    """두 표가 각자 적던 예전 루프 그대로 — 줄마다 그 칸까지의 접두 튜플을 위 줄과 견준다."""
    row_count = len(raw_values[0]) if raw_values else 0
    displayed_values = [values.copy() for values in raw_values]
    for column_index, values in enumerate(displayed_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(row_count):
            current_prefix = tuple(
                raw_values[prefix_index][row_index] for prefix_index in range(column_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix
    return displayed_values


def _columns_from_rows(rows: Sequence[Sequence[str]]) -> list[list[str]]:
    return [list(column) for column in zip(*rows, strict=True)]


BLANK_CASES: dict[str, list[list[str]]] = {
    "빈 칸 목록": [],
    "줄 없음": [[], []],
    "한 줄": [["A"], ["x"], ["1"]],
    "한 칸": [["A", "A", "B", "B", "A"]],
    "앞 칸이 바뀌면 뒤 칸을 남긴다": [["A", "B", "B"], ["x", "x", "x"]],
    "빈 글자 값": [["", "", "A"], ["", "x", "x"]],
    "모든 세 칸 조합": _columns_from_rows(sorted(product("AB", "xy", "12"), key=lambda r: r[2])),
    "되풀이 조합": _columns_from_rows([("A", "x", "1")] * 3 + [("A", "y", "1"), ("B", "y", "1")]),
}


@pytest.mark.parametrize("case", list(BLANK_CASES))
def test_blank_repeated_prefixes_matches_the_old_loop(case: str) -> None:
    raw = BLANK_CASES[case]
    snapshot = [list(column) for column in raw]

    assert blank_repeated_prefixes(raw) == _legacy_blank(raw)
    assert raw == snapshot, "받은 목록을 고치면 안 된다 — 소계 줄 이름은 원래 값을 다시 읽는다"


def test_blank_repeated_prefixes_keeps_the_first_row_of_a_new_parent_group() -> None:
    assert blank_repeated_prefixes([["A", "A", "B", "B"], ["x", "x", "x", "y"]]) == [
        ["A", "", "B", ""],
        ["x", "", "x", "y"],
    ]


def _legacy_grouped_grid(
    *,
    label_figure: go.Figure,
    month_figure: go.Figure,
    classification_widths: list[int],
    month_columns: list[str],
    product_total_rows: list[int],
    production_total_rows: list[int],
    grand_total_row: int,
    row_count: int,
) -> None:
    """`grouped_monthly_table._add_table_grid` 의 예전 꼴 — 격자 머리 여섯 호출을 각자 적었다."""
    table_height = table_height_px(row_count)
    add_outer_border(label_figure, include_left=True)
    add_outer_border(month_figure, include_left=False)
    for target_figure in (label_figure, month_figure):
        add_header_rule(target_figure, boundary_y=header_boundary_ratio(row_count))

    total_classification_width = sum(classification_widths)
    production_boundary_x = classification_widths[0] / total_classification_width
    add_classification_boundaries(label_figure, classification_widths)

    add_month_boundaries(month_figure, month_columns)

    def _rule(x0: float, y: float, width: float) -> dict[str, Any]:
        return {
            "type": "line",
            "x0": x0,
            "x1": 1,
            "y0": y,
            "y1": y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": width},
            "layer": "above",
        }

    def _boundary_y(total_row: int) -> float:
        return 1 - (HEADER_HEIGHT_PX + (total_row + 1) * ROW_HEIGHT_PX) / table_height

    label_shapes: list[dict[str, Any]] = []
    month_shapes: list[dict[str, Any]] = []
    for total_row in product_total_rows:
        label_shapes.append(_rule(production_boundary_x, _boundary_y(total_row), 1.0))
        month_shapes.append(_rule(0, _boundary_y(total_row), 1.0))
    for total_row in production_total_rows:
        label_shapes.append(_rule(0, _boundary_y(total_row), 1.4))
        month_shapes.append(_rule(0, _boundary_y(total_row), 1.4))
    label_shapes.append(_rule(0, _boundary_y(grand_total_row), OUTER_BORDER_WIDTH_PX))
    month_shapes.append(_rule(0, _boundary_y(grand_total_row), OUTER_BORDER_WIDTH_PX))
    append_layout_items(label_figure, shapes=label_shapes)
    append_layout_items(month_figure, shapes=month_shapes)
    flush_layout_items(label_figure, month_figure)


def _legacy_hierarchical_grid(
    *,
    label_figure: go.Figure,
    month_figure: go.Figure,
    display: Any,
    classification_widths: list[int],
    month_columns: list[str],
    row_count: int,
) -> None:
    """`hierarchical_monthly_table._add_table_grid` 의 예전 꼴."""
    table_height = table_height_px(row_count)
    add_outer_border(label_figure, include_left=True)
    add_outer_border(month_figure, include_left=False)
    for figure in (label_figure, month_figure):
        add_header_rule(figure, boundary_y=header_boundary_ratio(row_count))

    total_classification_width = sum(classification_widths)
    add_classification_boundaries(label_figure, classification_widths)

    add_month_boundaries(month_figure, month_columns)

    cumulative_widths = [0, *accumulate(classification_widths)]
    label_shapes: list[dict[str, Any]] = []
    month_shapes: list[dict[str, Any]] = []
    for row_index, changed_column in display.group_boundaries:
        boundary_y = 1 - (HEADER_HEIGHT_PX + row_index * ROW_HEIGHT_PX) / table_height
        label_start_x = cumulative_widths[changed_column] / total_classification_width
        boundary_width = max(1.0, OUTER_BORDER_WIDTH_PX - changed_column * 0.16)
        line = {"color": tokens.BORDER_STRONG, "width": boundary_width}
        label_shapes.append(
            {
                "type": "line",
                "x0": label_start_x,
                "x1": 1,
                "y0": boundary_y,
                "y1": boundary_y,
                "xref": "paper",
                "yref": "paper",
                "line": line,
                "layer": "above",
            }
        )
        month_shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": boundary_y,
                "y1": boundary_y,
                "xref": "paper",
                "yref": "paper",
                "line": line,
                "layer": "above",
            }
        )
    append_layout_items(label_figure, shapes=label_shapes)
    append_layout_items(month_figure, shapes=month_shapes)
    flush_layout_items(label_figure, month_figure)


def _as_json(*figures: go.Figure) -> list[str]:
    return [figure.to_json() for figure in figures]


MONTHS = ["202511", "202512", "202601", "202602", "202603", "202604", "연간 Total"]
WEEKS = ["26-W01", "26-W02", "26-W03"]

GROUPED_DATA = pd.DataFrame(
    {
        "양산구분": ["양산", "양산", "양산", "ER", "ER", None],
        "제품정보": ["P&1", "P&1", "P2", "P2", "P3", "P3"],
        "Stack": ["8H", "12H", "8H", "8H", "8H", "8H"],
        "202512": [1.0, 2.0, 0.0, 4.0, None, 6.0],
        "202601": [0.5, 0.0, 3.0, 0.0, 1.0, 2.0],
    }
)


@pytest.mark.parametrize(
    ("columns", "months"),
    [
        (["양산구분", "제품정보", "Stack"], MONTHS),
        (["양산구분", "Stack"], WEEKS),
        (["제품정보", "Stack"], ["202601"]),
        (["양산구분"], MONTHS[:2]),
    ],
)
def test_grouped_display_and_grid_match_the_old_steps(
    columns: list[str], months: list[str]
) -> None:
    data = GROUPED_DATA[[*columns, "202512", "202601"]]
    display = grouped._build_display_rows(data, columns, ["202512", "202601"])
    raw = [[classification_cell_text(value, None) for value in data[column]] for column in columns]
    detail_rows = [
        index for index, row_type in enumerate(display.row_types) if row_type == "detail"
    ]
    assert [
        [values[index] for index in detail_rows] for values in display.classification_values
    ] == _legacy_blank(raw)

    widths = [96, 140, 72, 110][: len(columns)]
    arguments: dict[str, Any] = {
        "classification_widths": widths,
        "month_columns": months,
        "product_total_rows": display.product_total_rows,
        "production_total_rows": display.production_total_rows,
        "grand_total_row": display.grand_total_row,
        "row_count": len(display.row_types),
    }
    new_label, new_month = go.Figure(), go.Figure()
    grouped._add_table_grid(label_figure=new_label, month_figure=new_month, **arguments)
    old_label, old_month = go.Figure(), go.Figure()
    _legacy_grouped_grid(label_figure=old_label, month_figure=old_month, **arguments)

    assert _as_json(new_label, new_month) == _as_json(old_label, old_month)


HIERARCHICAL_DATA = pd.DataFrame(
    {
        "Area_Name": ["Main", "Main", "Main", "Sub", "Sub", None, None],
        "공정": ["WF", "WF", "Mold & Cure", "Mold & Cure", "Mold & Cure", "X", "X"],
        "소요기준": ["WF", "WF", "WF", "CHIP", "CHIP", "PKG", "PKG"],
        "WF 구분": ["Core", "Top", "Core", "Core", "Core", None, "Top"],
    }
)


@pytest.mark.parametrize(
    "columns",
    [
        ["Area_Name", "공정", "소요기준", "WF 구분"],
        ["공정", "WF 구분"],
        ["공정"],
    ],
)
@pytest.mark.parametrize("months", [MONTHS, WEEKS])
def test_hierarchical_display_and_grid_match_the_old_steps(
    columns: list[str], months: list[str]
) -> None:
    data = HIERARCHICAL_DATA[columns]
    labels = {"공정": {"WF": "웨이퍼"}}
    display = hierarchical._build_hierarchical_display(data, columns, labels)
    raw = [
        [classification_cell_text(value, labels.get(column)) for value in data[column]]
        for column in columns
    ]
    assert display.classification_values == _legacy_blank(raw)

    widths = [80, 132, 96, 101][: len(columns)]
    arguments: dict[str, Any] = {
        "display": display,
        "classification_widths": widths,
        "month_columns": months,
        "row_count": len(data),
    }
    new_label, new_month = go.Figure(), go.Figure()
    hierarchical._add_table_grid(label_figure=new_label, month_figure=new_month, **arguments)
    old_label, old_month = go.Figure(), go.Figure()
    _legacy_hierarchical_grid(label_figure=old_label, month_figure=old_month, **arguments)

    assert _as_json(new_label, new_month) == _as_json(old_label, old_month)
