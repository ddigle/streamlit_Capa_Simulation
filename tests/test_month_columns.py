# Purpose: 월 축에 연간 Total 열을 끼우는 규칙을 고정한다.

from capa_simulation.services.month_columns import (
    build_month_axis,
    complete_years,
    year_total_label,
)


def test_only_a_year_with_all_twelve_months_gets_a_total() -> None:
    """일부 달만 든 해의 합계는 연간이 아니라 조회한 달의 합이다. 같은 이름으로 두면 속는다."""
    months = [*(202600 + month for month in range(1, 13)), 202701, 202702]

    assert complete_years(months) == [2026]


def test_the_total_sits_right_after_that_years_december() -> None:
    months = [*(202600 + month for month in range(1, 13)), 202701]

    labels, totals = build_month_axis(months)

    assert labels[11] == "26.12"
    assert labels[12] == year_total_label(2026)
    assert labels[13] == "27.01"
    assert totals == ["26년"]


def test_two_complete_years_each_get_their_own_total() -> None:
    months = [
        *(202600 + month for month in range(1, 13)),
        *(202700 + month for month in range(1, 13)),
    ]

    labels, totals = build_month_axis(months)

    assert labels[12] == "26년"
    assert labels[-1] == "27년"
    assert totals == ["26년", "27년"]


def test_no_complete_year_leaves_the_axis_untouched() -> None:
    months = [202607, 202608, 202609]

    labels, totals = build_month_axis(months)

    assert labels == ["26.07", "26.08", "26.09"]
    assert totals == []
