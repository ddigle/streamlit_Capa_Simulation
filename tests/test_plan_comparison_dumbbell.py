# Purpose: 시나리오 비교 덤벨의 차이 계산·정렬·한쪽 결손 처리를 검증한다.

import pandas as pd

from capa_simulation.components.plan_comparison_dumbbell import (
    build_plan_comparison_dumbbell,
)
from capa_simulation.design import tokens

DIMENSIONS = ["제품정보"]


def _detail(rows: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame({"제품정보": list(rows), "26.01": [values[0] for values in rows.values()]})


def test_rows_are_ordered_by_the_size_of_the_change() -> None:
    """큰 차이가 위다. 위에서 아래로 읽었을 때 순위가 곧 크기여야 한다."""
    figure = build_plan_comparison_dumbbell(
        _detail({"A": [100.0], "B": [500.0], "C": [210.0]}),
        _detail({"A": [110.0], "B": [100.0], "C": [200.0]}),
        dimensions=DIMENSIONS,
    )

    assert figure is not None
    # Plotly 의 y 는 아래에서 위로 쌓이므로 그리는 차례는 뒤집혀 있다.
    assert list(figure.data[0].y) == ["C", "A", "B"]


def test_a_class_missing_from_one_scenario_counts_as_zero() -> None:
    """빠진 계획이 길이로 드러나야 한다. 결측으로 두면 줄 자체가 사라진다."""
    figure = build_plan_comparison_dumbbell(
        _detail({"A": [100.0]}),
        _detail({"A": [100.0], "사라진제품": [300.0]}),
        dimensions=DIMENSIONS,
    )

    assert figure is not None
    assert list(figure.data[0].y) == ["사라진제품"]
    assert list(figure.data[1].x) == [0.0]
    assert list(figure.data[0].x) == [300.0]


def test_connector_color_shows_the_direction_not_a_status() -> None:
    """늘고 주는 것은 좋고 나쁨이 아니다. 상태색을 쓰면 늘어난 달이 `부족` 으로 읽힌다."""
    figure = build_plan_comparison_dumbbell(
        _detail({"늘었다": [300.0], "줄었다": [100.0]}),
        _detail({"늘었다": [100.0], "줄었다": [400.0]}),
        dimensions=DIMENSIONS,
    )

    assert figure is not None
    colors = {shape.y0: shape.line.color for shape in figure.layout.shapes}
    assert colors == {
        "늘었다": tokens.DELTA_INCREASE,
        "줄었다": tokens.DELTA_DECREASE,
    }


def test_identical_plans_draw_nothing() -> None:
    assert (
        build_plan_comparison_dumbbell(
            _detail({"A": [100.0]}), _detail({"A": [100.0]}), dimensions=DIMENSIONS
        )
        is None
    )


def test_top_n_limits_the_rows() -> None:
    rows = {f"P{index:02d}": [float(index)] for index in range(1, 21)}
    figure = build_plan_comparison_dumbbell(
        _detail(rows), _detail({name: [0.0] for name in rows}), dimensions=DIMENSIONS, top_n=5
    )

    assert figure is not None
    assert list(figure.data[0].y) == ["P16", "P17", "P18", "P19", "P20"]
