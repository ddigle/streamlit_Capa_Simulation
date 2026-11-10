# Purpose: 월 표 공용 격자 머리 · 반복 접두 생략이 그 정의와 같은 결과인지 고정한다.

"""`monthly_table_base` 의 공용 단계 둘을 그 정의와 견준다.

- `add_table_frame` 은 바깥 테두리 둘 → 머리 밑줄 둘 → 분류 칸 세로선 → 월 경계선을 이 차례로
  부른 것과 Figure JSON 글자가 같다. 행 그룹 가로선은 표 모듈마다 이 뒤에 더하므로 여기서 다루지
  않는다 — `test_monthly_table_grid` · `test_grouped_monthly_table` ·
  `test_hierarchical_monthly_table` 이 맡는다.
- `blank_repeated_prefixes` 는 줄마다 그 칸까지의 접두 튜플이 바로 위 줄과 같으면 비운다는 판정과
  같다. 두 표 모듈이 분류 칸 값을 이 규칙으로 비우는지도 본다.

격자는 `to_json()` 글자로 견준다 — dict 비교로는 같은 `0` 과 `0.0` 도 JSON 바이트로는 다르다.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product

import pandas as pd
import plotly.graph_objects as go
import pytest

from capa_simulation.components import grouped_monthly_table as grouped
from capa_simulation.components import hierarchical_monthly_table as hierarchical
from capa_simulation.components.monthly_table_base import (
    add_classification_boundaries,
    add_header_rule,
    add_month_boundaries,
    add_outer_border,
    add_table_frame,
    blank_repeated_prefixes,
    classification_cell_text,
    header_boundary_ratio,
)
from capa_simulation.components.plotly_layout import flush_layout_items


def _prefix_tuple_blank(raw_values: list[list[str]]) -> list[list[str]]:
    """접두 생략 판정의 정의 — 줄마다 그 칸까지의 접두 튜플을 위 줄과 견준다."""
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
def test_blank_repeated_prefixes_follows_the_prefix_tuple_rule(case: str) -> None:
    raw = BLANK_CASES[case]
    snapshot = [list(column) for column in raw]

    assert blank_repeated_prefixes(raw) == _prefix_tuple_blank(raw)
    assert raw == snapshot, "받은 목록을 고치면 안 된다 — 소계 줄 이름은 원래 값을 다시 읽는다"


def test_blank_repeated_prefixes_keeps_the_first_row_of_a_new_parent_group() -> None:
    assert blank_repeated_prefixes([["A", "A", "B", "B"], ["x", "x", "x", "y"]]) == [
        ["A", "", "B", ""],
        ["x", "", "x", "y"],
    ]


MONTHS = ["202511", "202512", "202601", "202602", "202603", "202604", "연간 Total"]
WEEKS = ["26-W01", "26-W02", "26-W03"]


def _frame_by_helpers(
    label_figure: go.Figure,
    month_figure: go.Figure,
    *,
    classification_widths: list[int],
    month_columns: list[str],
    row_count: int,
) -> None:
    """격자 머리의 정의 — 네 도우미를 정해진 차례로 여섯 번 부른다."""
    add_outer_border(label_figure, include_left=True)
    add_outer_border(month_figure, include_left=False)
    add_header_rule(label_figure, boundary_y=header_boundary_ratio(row_count))
    add_header_rule(month_figure, boundary_y=header_boundary_ratio(row_count))
    add_classification_boundaries(label_figure, classification_widths)
    add_month_boundaries(month_figure, month_columns)


@pytest.mark.parametrize(
    ("classification_widths", "month_columns", "row_count"),
    [
        ([96, 140, 72, 110], MONTHS, 12),
        ([80, 132, 96], WEEKS, 7),
        ([96, 72], ["202601"], 1),
        ([140], MONTHS[:2], 40),
    ],
)
def test_table_frame_draws_the_helpers_in_order(
    classification_widths: list[int], month_columns: list[str], row_count: int
) -> None:
    frame_label, frame_month = go.Figure(), go.Figure()
    add_table_frame(
        frame_label,
        frame_month,
        classification_widths=classification_widths,
        month_columns=month_columns,
        row_count=row_count,
    )
    flush_layout_items(frame_label, frame_month)
    helper_label, helper_month = go.Figure(), go.Figure()
    _frame_by_helpers(
        helper_label,
        helper_month,
        classification_widths=classification_widths,
        month_columns=month_columns,
        row_count=row_count,
    )
    flush_layout_items(helper_label, helper_month)

    assert [figure.to_json() for figure in (frame_label, frame_month)] == [
        figure.to_json() for figure in (helper_label, helper_month)
    ]


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
    "columns",
    [
        ["양산구분", "제품정보", "Stack"],
        ["양산구분", "Stack"],
        ["제품정보", "Stack"],
        ["양산구분"],
    ],
)
def test_grouped_detail_rows_blank_repeated_prefixes(columns: list[str]) -> None:
    data = GROUPED_DATA[[*columns, "202512", "202601"]]
    display = grouped._build_display_rows(data, columns, ["202512", "202601"])
    raw = [[classification_cell_text(value, None) for value in data[column]] for column in columns]
    detail_rows = [
        index for index, row_type in enumerate(display.row_types) if row_type == "detail"
    ]

    assert [
        [values[index] for index in detail_rows] for values in display.classification_values
    ] == _prefix_tuple_blank(raw)


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
def test_hierarchical_rows_blank_repeated_prefixes(columns: list[str]) -> None:
    data = HIERARCHICAL_DATA[columns]
    labels = {"공정": {"WF": "웨이퍼"}}
    display = hierarchical._build_hierarchical_display(data, columns, labels)
    raw = [
        [classification_cell_text(value, labels.get(column)) for value in data[column]]
        for column in columns
    ]

    assert display.classification_values == _prefix_tuple_blank(raw)
