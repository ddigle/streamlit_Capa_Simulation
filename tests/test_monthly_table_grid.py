# Purpose: 월별 표 두 종류가 공유하는 테두리·헤더선·월 경계선이 같은 도형인지 고정한다.

import plotly.graph_objects as go

from capa_simulation.components import grouped_monthly_table as grouped
from capa_simulation.components import hierarchical_monthly_table as hierarchical
from capa_simulation.components.monthly_table_base import (
    BORDER_COLOR,
    GRID_LINE_WIDTH_PX,
    GROUP_BORDER_COLOR,
    OUTER_BORDER_WIDTH_PX,
    add_classification_boundaries,
    add_month_boundaries,
    add_outer_border,
)

MONTHS = ["202601", "202602", "202603", "202604", "202605", "202606", "202607"]
WIDTHS = [120, 160, 90, 110]


def _shapes(figure: go.Figure) -> list[dict[str, object]]:
    return [shape.to_plotly_json() for shape in figure.layout.shapes]


def _grid_pair() -> tuple[tuple[go.Figure, go.Figure], tuple[go.Figure, go.Figure]]:
    grouped_label, grouped_month = go.Figure(), go.Figure()
    grouped._add_table_grid(
        label_figure=grouped_label,
        month_figure=grouped_month,
        classification_widths=WIDTHS,
        month_columns=MONTHS,
        product_total_rows=[2, 5],
        production_total_rows=[6],
        grand_total_row=7,
        row_count=8,
    )
    hier_label, hier_month = go.Figure(), go.Figure()
    hierarchical._add_table_grid(
        label_figure=hier_label,
        month_figure=hier_month,
        display=hierarchical._HierarchicalDisplay(
            classification_values=[
                ["A", "A", "B"],
                ["x", "y", "z"],
                ["1", "2", "3"],
                ["p", "q", "r"],
            ],
            top_group_indices=[0, 2],
            group_boundaries=[(1, 2), (2, 0), (3, 1)],
        ),
        classification_widths=WIDTHS,
        month_columns=MONTHS,
        row_count=8,
    )
    return (grouped_label, grouped_month), (hier_label, hier_month)


def test_outer_border_draws_only_lines() -> None:
    """바깥 테두리는 선 3~4개다.

    `grouped` 는 전에 폭 1.8 rect 를 하나 더 그렸는데 뒤이어 그리는 폭 3.6 선이 네 변을
    모두 덮어 화면에 나타나지 않았다. rect 가 다시 생기면 여기서 걸린다.
    """
    label, month = go.Figure(), go.Figure()
    add_outer_border(label, include_left=True)
    add_outer_border(month, include_left=False)

    assert [shape["type"] for shape in _shapes(label)] == ["line"] * 4
    assert [shape["type"] for shape in _shapes(month)] == ["line"] * 3
    for shape in _shapes(label) + _shapes(month):
        assert shape["line"] == {
            "color": GROUP_BORDER_COLOR,
            "width": OUTER_BORDER_WIDTH_PX * 2,
        }


def test_month_boundaries_emphasize_quarter_change() -> None:
    """분기가 바뀌는 자리만 굵고 진하게 긋는다."""
    figure = go.Figure()
    add_month_boundaries(figure, MONTHS)

    widths = [shape["line"]["width"] for shape in _shapes(figure)]
    # 202601~202607 사이 경계 6개 중 3|4 월과 6|7 월 두 곳이 분기 경계다.
    assert widths == [
        GRID_LINE_WIDTH_PX,
        GRID_LINE_WIDTH_PX,
        OUTER_BORDER_WIDTH_PX,
        GRID_LINE_WIDTH_PX,
        GRID_LINE_WIDTH_PX,
        OUTER_BORDER_WIDTH_PX,
    ]


def test_both_tables_share_outer_border_and_month_grid() -> None:
    """두 표가 같은 껍데기를 그리는지 확인한다. 갈라지면 여기서 걸린다."""
    (grouped_label, grouped_month), (hier_label, hier_month) = _grid_pair()

    expected_label, expected_month = go.Figure(), go.Figure()
    add_outer_border(expected_label, include_left=True)
    add_outer_border(expected_month, include_left=False)
    add_month_boundaries(expected_month, MONTHS)

    border_count = len(_shapes(expected_label))
    assert _shapes(grouped_label)[:border_count] == _shapes(hier_label)[:border_count]
    assert _shapes(grouped_label)[:border_count] == _shapes(expected_label)

    # 월 경계선은 표를 세로로 가로지르되 좌우 끝(테두리)이 아닌 선이다.
    def month_grid(figure: go.Figure) -> list[dict[str, object]]:
        return [
            shape
            for shape in _shapes(figure)
            if shape["x0"] == shape["x1"] and shape["x0"] not in (0, 1)
        ]

    assert month_grid(grouped_month) == month_grid(expected_month)
    assert month_grid(hier_month) == month_grid(expected_month)


def test_classification_boundaries_cover_every_column_gap() -> None:
    """분류 컬럼 사이마다 선을 긋는다.

    `grouped` 는 전에 첫 경계 하나만 그어서, 분류 컬럼을 3~4개 넘기는 부하량 환산 표에서
    제품과 Stack 사이에 구분선이 없었다.
    """
    figure = go.Figure()
    add_classification_boundaries(figure, WIDTHS)

    total = sum(WIDTHS)
    assert [shape["x0"] for shape in _shapes(figure)] == [
        WIDTHS[0] / total,
        sum(WIDTHS[:2]) / total,
        sum(WIDTHS[:3]) / total,
    ]
    for shape in _shapes(figure):
        assert shape["x0"] == shape["x1"]
        assert (shape["y0"], shape["y1"]) == (0, 1)
        assert shape["line"] == {"color": BORDER_COLOR, "width": GRID_LINE_WIDTH_PX}


def test_both_tables_draw_the_same_classification_boundaries() -> None:
    (grouped_label, _), (hier_label, _) = _grid_pair()

    expected = go.Figure()
    add_classification_boundaries(expected, WIDTHS)

    def dividers(figure: go.Figure) -> list[dict[str, object]]:
        return [
            shape
            for shape in _shapes(figure)
            if shape["x0"] == shape["x1"]
            and shape["x0"] not in (0, 1)
            and shape["line"]["color"] == BORDER_COLOR
        ]

    assert dividers(grouped_label) == _shapes(expected)
    assert dividers(hier_label) == _shapes(expected)
