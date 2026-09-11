# Purpose: 레이아웃 항목을 모았다가 한 번에 반영하는 계약을 고정한다.

import plotly.graph_objects as go

from capa_simulation.components.plotly_layout import (
    add_fixed_table_row,
    append_layout_items,
    flush_layout_items,
)


def _shape(index: int) -> dict[str, object]:
    return {
        "type": "rect",
        "x0": index,
        "x1": index + 1,
        "y0": 0,
        "y1": 1,
        "xref": "paper",
        "yref": "paper",
    }


def test_appended_items_reach_the_figure_only_after_a_flush() -> None:
    """부를 때마다 반영하면 Plotly 가 쌓인 항목 전부를 다시 검증해 O(n²) 로 불어난다.

    그래서 모았다가 한 번에 넣는다. Figure 를 돌려주는 쪽이 flush 를 잊으면 테두리·격자·
    라벨이 통째로 빠지므로 화면에서 바로 드러난다.
    """
    figure = go.Figure()

    append_layout_items(figure, shapes=[_shape(0)])
    append_layout_items(figure, shapes=[_shape(1)])

    assert len(figure.layout.shapes or ()) == 0

    flush_layout_items(figure)

    assert len(figure.layout.shapes) == 2


def test_flushing_twice_changes_nothing() -> None:
    figure = go.Figure()
    append_layout_items(figure, annotations=[{"text": "a", "showarrow": False}])

    flush_layout_items(figure)
    flush_layout_items(figure)

    assert len(figure.layout.annotations) == 1


def test_a_flush_keeps_items_the_figure_already_had() -> None:
    """빌더가 `update_layout` 으로 먼저 넣어 둔 항목을 누적함이 덮어써서는 안 된다."""
    figure = go.Figure()
    figure.update_layout(shapes=[_shape(9)])

    append_layout_items(figure, shapes=[_shape(0)])
    flush_layout_items(figure)

    assert [shape.x0 for shape in figure.layout.shapes] == [9, 0]


def test_one_fill_color_draws_one_rectangle_not_one_per_cell() -> None:
    """면색이 모두 같으면 칸마다 사각형을 그릴 이유가 없다. 도형 수가 그대로 비용이다."""
    figure = go.Figure()

    add_fixed_table_row(
        figure,
        domain=(0.0, 0.5),
        values=["a", "b", "c"],
        fill_color=["#FFFFFF", "#FFFFFF", "#FFFFFF"],
        font_size=12,
        bold=False,
    )
    flush_layout_items(figure)

    assert len(figure.layout.shapes) == 1


def test_a_differing_fill_color_splits_the_row_per_cell() -> None:
    figure = go.Figure()

    add_fixed_table_row(
        figure,
        domain=(0.0, 0.5),
        values=["a", "b", "c"],
        fill_color=["#FFFFFF", "#EEEEEE", "#FFFFFF"],
        font_size=12,
        bold=False,
    )
    flush_layout_items(figure)

    assert len(figure.layout.shapes) == 3
