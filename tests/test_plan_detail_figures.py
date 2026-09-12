# Purpose: 계획 세부수량 두 칸의 세로 정렬이 GAP 유무에 따라 어떻게 갈리는지 고정한다.

"""계획 세부수량 칸의 세로 정렬 계약.

`go.Table` 은 한 줄짜리 칸의 글자를 칸 **위에 붙여** 그리고 여러 줄일 때만 가운데에 세운다.
칸의 세로 정렬을 지정할 방법은 없다 — `table.Cells` 에 `valign` 이 없다. 그래서 값 뒤에
빈 줄 하나를 붙이느냐로 자리가 갈린다.

증감이 오는 칸만 위에 붙어야 한다. 그 아래가 GAP 주석 자리이기 때문이다. 나머지는 가운데다.
"""

import pandas as pd
import pytest

from capa_simulation.components.home_figures import build_plan_detail_figures

MONTHS = ["202608", "202609"]
BLANK_LINE = "<br>"


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["A", "A", "B"],
            "Stack": ["12H", "8H", "4H"],
            "202608": [1000.0, 500.0, 0.0],
            "202609": [2000.0, 0.0, 300.0],
        }
    )


def _comparison() -> pd.DataFrame:
    compared = _detail()
    compared["202608"] = [900.0, 500.0, 0.0]
    compared["202609"] = [2500.0, 0.0, 100.0]
    return compared


def _filled(figure: object) -> list[str]:
    cells = figure.data[0].cells  # type: ignore[attr-defined]
    return [value for column in cells.values for value in column if value]


def test_both_columns_center_without_a_comparison() -> None:
    """GAP 이 없으면 두 칸 모두 가운데다. 한쪽만 가운데면 같은 행의 글자가 어긋나 보인다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(), month_labels=MONTHS
    )

    assert _filled(label_figure), "분류 칸이 비어 있다"
    assert _filled(month_figure), "월 칸이 비어 있다"
    assert all(value.endswith(BLANK_LINE) for value in _filled(label_figure))
    assert all(value.endswith(BLANK_LINE) for value in _filled(month_figure))


def test_the_month_column_yields_the_lower_line_to_the_gap() -> None:
    """GAP 이 오면 월 칸만 위로 붙는다. 분류 칸은 증감이 없으므로 가운데에 그대로 선다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison(),
    )

    assert all(value.endswith(BLANK_LINE) for value in _filled(label_figure))
    assert not any(value.endswith(BLANK_LINE) for value in _filled(month_figure))
    gaps = [annotation.text for annotation in month_figure.layout.annotations if annotation.text]
    assert sorted(gaps) == ["+100K", "+200K", "-500K"]


def test_the_row_height_does_not_move_with_the_toggle() -> None:
    """토글 하나에 표 높이가 출렁이면 아래 구획이 통째로 밀린다. 움직이는 것은 글자뿐이다."""
    plain = build_plan_detail_figures(production_detail=_detail(), month_labels=MONTHS)
    compared = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison(),
    )

    for without, with_gap in zip(plain, compared, strict=True):
        assert without.data[0].cells.height == with_gap.data[0].cells.height
        assert without.layout.height == with_gap.layout.height
    # 두 칸의 행이 어긋나면 표 전체가 틀어진다.
    assert plain[0].data[0].cells.height == plain[1].data[0].cells.height


@pytest.mark.parametrize("with_comparison", [False, True])
def test_an_empty_cell_never_gets_a_blank_line(with_comparison: bool) -> None:
    """빈 칸에 빈 줄을 붙이면 값이 없는 자리에 줄만 생긴다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison() if with_comparison else None,
    )

    cells = month_figure.data[0].cells
    assert any(value == "" for column in cells.values for value in column), "빈 칸이 없다"
    assert all(value == "" for column in cells.values for value in column if not value.strip())
