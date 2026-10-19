# Purpose: 계획 세부수량 두 칸의 세로 정렬이 GAP 유무에 따라 어떻게 갈리는지 고정한다.

"""계획 세부수량 칸의 세로 정렬 계약.

칸 글자는 표 칸이 아니라 숨긴 축 위 글자 trace 가 그린다 — `data[0]` 이 머리글, `data[1]` 이
값이고 y 는 그림 위에서 잰 px 다. 칸이 `<br>` 같은 마크업을 품으면 Plotly 가 칸마다 그린 뒤
재서 옮겨 칸 수만큼 느려진다.

증감이 오는 칸만 칸 위에 붙는 자리에 선다. 그 아래가 GAP 주석 자리이기 때문이다. 나머지는
행 한가운데다.
"""

from typing import Any

import pandas as pd
import pytest

from capa_simulation.components.home_dimensions import lower_delta_row_height, table_row_height
from capa_simulation.components.home_figures import build_plan_detail_figures
from capa_simulation.components.home_plan_detail_figures import (
    DETAIL_HEADER_FONT_SIZE_PX,
    DETAIL_VALUE_FONT_SIZE_PX,
)
from capa_simulation.components.plotly_layout import table_text_y

MONTHS = ["202608", "202609"]
HEADER_HEIGHT = table_row_height(DETAIL_HEADER_FONT_SIZE_PX)
ROW_HEIGHT = lower_delta_row_height(DETAIL_VALUE_FONT_SIZE_PX)
CENTERED = round(table_text_y(0, DETAIL_VALUE_FONT_SIZE_PX, markup=True), 6)
RAISED = round(table_text_y(0, DETAIL_VALUE_FONT_SIZE_PX, markup=False), 6)


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


def _values(figure: Any) -> list[str]:
    return list(figure.data[1].text)


def _offsets(figure: Any) -> set[float]:
    """값 글자가 제 행 위 모서리에서 내려온 거리. 나머지 셈의 부동소수 찌꺼기는 반올림한다."""
    return {round((y - HEADER_HEIGHT) % ROW_HEIGHT, 6) for y in figure.data[1].y}


PAST_MONTHS = ["26.01", "26.07", "26.08", "26년"]


def _past_detail() -> pd.DataFrame:
    """과거 구간(26.01) 과 DB 계산 구간(26.07·26.08), 그리고 연간 Total."""
    return pd.DataFrame(
        {
            "제품정보": ["A"],
            "Stack": ["12H"],
            "26.01": [1000.0],
            "26.07": [200.0],
            "26.08": [300.0],
            "26년": [1500.0],
        }
    )


def _past_comparison() -> pd.DataFrame:
    """비교 프레임에는 과거도 연간 Total 도 없다 — 실제 파이프라인과 같은 모양이다."""
    return pd.DataFrame(
        {
            "제품정보": ["A"],
            "Stack": ["12H"],
            "26.07": [150.0],
            "26.08": [300.0],
        }
    )


def _gap_notes(figure: object) -> list[str]:
    annotations = figure.layout.annotations  # type: ignore[attr-defined]
    return [annotation.text for annotation in annotations if annotation.text]


def test_past_months_get_no_gap() -> None:
    """과거 구간은 공용 프로필에서 와 두 시나리오가 같은 값을 받는다.

    비교 프레임에는 과거가 병합되지 않으므로, 거르지 않으면 과거 입력 전액이 거짓 증감으로
    찍힌다. 여기서는 26.01 의 1,000K 가 그것이다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
        gap_month_labels={"26.07", "26.08"},
    )

    notes = _gap_notes(month_figure)

    assert "+1,000K" not in notes, f"과거 구간에 증감이 찍혔다: {notes}"
    assert "+50K" in notes, f"DB 구간 증감이 사라졌다: {notes}"


def test_year_total_gap_sums_only_the_db_range() -> None:
    """연간 Total 은 DB 계산 구간의 차이만 더한다.

    비교 프레임에 `26년` 컬럼이 없어 그대로 두면 그 해 합계 전액(1,500K)이 증감이 된다.
    실제 차이는 26.07 의 +50K 하나뿐이다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
        gap_month_labels={"26.07", "26.08"},
    )

    notes = _gap_notes(month_figure)

    assert "+1,500K" not in notes, f"연간 Total 에 그 해 전액이 찍혔다: {notes}"
    # 26.07 의 +50K 와 Total 의 +50K 둘 다 나온다.
    assert notes.count("+50K") == 2, notes


def test_without_a_month_whitelist_every_month_keeps_its_gap() -> None:
    """`gap_month_labels` 를 주지 않으면 예전과 같이 모든 달에 증감을 낸다.

    과거 구간을 쓰지 않는 호출자(테스트·다른 화면)가 이 인자를 몰라도 동작이 바뀌지 않아야
    한다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
    )

    notes = _gap_notes(month_figure)

    assert "+1,000K" in notes, notes


def test_both_columns_center_without_a_comparison() -> None:
    """GAP 이 없으면 두 칸 모두 행 한가운데다. 한쪽만 가운데면 같은 행의 글자가 어긋나 보인다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(), month_labels=MONTHS
    )

    assert _values(label_figure), "분류 칸이 비어 있다"
    assert _values(month_figure), "월 칸이 비어 있다"
    assert _offsets(label_figure) == _offsets(month_figure) == {CENTERED}
    # 점은 표의 마크업 칸 자리(맑은 고딕 기준선보다 0.25em 위)라 행 가운데보다 1px 남짓 아래다.
    # 기준선 위로 서는 글리프의 가운데는 그보다 위라 눈으로는 가운데다.
    assert abs(CENTERED - ROW_HEIGHT / 2) <= 1.5
    assert not any(
        "<" in text for figure in (label_figure, month_figure) for text in _values(figure)
    )


def test_the_month_column_yields_the_lower_line_to_the_gap() -> None:
    """GAP 이 오면 월 칸만 위로 붙는다. 분류 칸은 증감이 없으므로 가운데에 그대로 선다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison(),
    )

    assert _offsets(label_figure) == {CENTERED}
    assert _offsets(month_figure) == {RAISED}
    assert RAISED < CENTERED
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
        assert without.layout.height == with_gap.layout.height
        assert without.layout.yaxis.range == with_gap.layout.yaxis.range
        assert list(without.data[0].y) == list(with_gap.data[0].y)
    # 두 칸의 행이 어긋나면 표 전체가 틀어진다.
    assert plain[0].layout.height == plain[1].layout.height
    assert list(plain[0].data[1].y) == list(compared[0].data[1].y)


@pytest.mark.parametrize("with_comparison", [False, True])
def test_an_empty_cell_gets_no_text(with_comparison: bool) -> None:
    """빈 칸(0·결측)에는 글자를 두지 않는다 — 없는 값 자리에 빈 글자만 생긴다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison() if with_comparison else None,
    )

    assert _values(month_figure) == ["1,000K", "500K", "2,000K", "300K"]
