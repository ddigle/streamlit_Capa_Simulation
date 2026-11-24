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


def test_only_the_compared_months_count() -> None:
    """견줄 달(`months`)만 더한다. 과거 구간 달은 현재 쪽에만 공용 프로필 값이 병합돼 있어 함께
    더하면 과거 입력 전액이 거짓 차이로 잡혔다(2026-10-08 사용자 결정 — 표의 GAP 과 같은 규칙)."""
    current = pd.DataFrame({"제품정보": ["A", "B"], "26.01": [40.0, 10.0], "26.07": [100.0, 50.0]})
    comparison = pd.DataFrame({"제품정보": ["A", "B"], "26.07": [100.0, 30.0]})

    figure = build_plan_comparison_dumbbell(
        current, comparison, dimensions=DIMENSIONS, months={"26.07"}
    )
    every_month = build_plan_comparison_dumbbell(current, comparison, dimensions=DIMENSIONS)

    assert figure is not None
    # 26.07 만 보면 A 는 같고 B 만 20 늘었다.
    assert list(figure.data[0].y) == ["B"]
    assert every_month is not None and "A" in list(every_month.data[0].y)


PART_DIMENSIONS = ["제품정보", "CUSTOM", "Stack"]


def _part_detail(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """(제품정보, CUSTOM, 값) — Stack 은 모두 8H."""
    return pd.DataFrame(
        {
            "제품정보": [row[0] for row in rows],
            "CUSTOM": [row[1] for row in rows],
            "Stack": ["8H"] * len(rows),
            "26.01": [row[2] for row in rows],
        }
    )


def test_a_split_product_names_each_part_like_the_detail_table() -> None:
    """부품을 가르는 제품의 줄 이름은 세부수량 표와 같은 이름표(「제품 (부품) · Stack」)이고 부품을
    칸으로 잇지 않는다. 접힌 제품은 지금처럼 제품 이름이다. 짝을 못 찾은 비교 행은 「제품 (-)」 줄의
    − 로, 부품 줄은 + 로 갈려 보이고 제품 합은 맞는다."""
    figure = build_plan_comparison_dumbbell(
        _part_detail(
            [
                ("DEMO_A", "DEMO_CUSTOM_A", 60.0),
                ("DEMO_A", "DEMO_CUSTOM_B", 40.0),
                ("DEMO_B", "", 30.0),
            ]
        ),
        _part_detail([("DEMO_A", "-", 100.0), ("DEMO_B", "", 20.0)]),
        dimensions=PART_DIMENSIONS,
    )

    assert figure is not None
    names = list(figure.data[0].y)
    assert set(names) == {
        "DEMO_A (DEMO_CUSTOM_A) · 8H",
        "DEMO_A (DEMO_CUSTOM_B) · 8H",
        "DEMO_A (-) · 8H",
        "DEMO_B · 8H",
    }
    differences = dict(zip(names, figure.data[1].text, strict=True))
    assert differences["DEMO_A (-) · 8H"] == "-100"
    assert differences["DEMO_A (DEMO_CUSTOM_A) · 8H"] == "+60"
    assert differences["DEMO_B · 8H"] == "+10"


def test_a_folded_frame_draws_the_same_dumbbell_as_the_frame_without_parts() -> None:
    """부품이 하나뿐인 제품만 있으면(접힌 값) 부품 칸이 없는 표와 같은 그림이다."""
    current = _part_detail([("DEMO_A", "", 100.0), ("DEMO_B", "", 30.0)])
    comparison = _part_detail([("DEMO_A", "", 80.0), ("DEMO_B", "", 50.0)])

    with_parts = build_plan_comparison_dumbbell(current, comparison, dimensions=PART_DIMENSIONS)
    without = build_plan_comparison_dumbbell(
        current.drop(columns=["CUSTOM"]),
        comparison.drop(columns=["CUSTOM"]),
        dimensions=["제품정보", "Stack"],
    )

    assert with_parts is not None and without is not None
    assert with_parts.to_json() == without.to_json()
