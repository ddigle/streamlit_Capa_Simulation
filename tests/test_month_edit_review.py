# Purpose: 월별 편집기의 변경량 집계가 실제 저장될 차이와 같은지 검사한다.

from __future__ import annotations

import pandas as pd

from capa_simulation.components.month_editor import count_month_changes, merge_edited_months

MONTHS = ["202601", "202602"]
DIMENSIONS = ["공정"]


def _table(rows: list[tuple[str, float | None, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["공정", *MONTHS])


def test_no_edit_is_no_change() -> None:
    table = _table([("가", 1.0, 2.0), ("나", 3.0, None)])

    assert count_month_changes(table, table.copy(), MONTHS) == (0, 0)


def test_the_same_blank_is_not_a_change() -> None:
    """`NaN != NaN` 이라 그냥 비교하면 손대지 않은 빈칸이 전부 변경으로 잡힌다."""
    table = _table([("가", None, None), ("나", None, 2.0)])

    assert count_month_changes(table, table.copy(), MONTHS) == (0, 0)


def test_changed_cells_and_rows_are_counted_separately() -> None:
    """한 행에서 두 칸을 고치면 값 2 · 행 1 이다."""
    table = _table([("가", 1.0, 2.0), ("나", 3.0, 4.0)])
    merged = table.copy()
    merged.loc[0, MONTHS] = [9.0, 8.0]

    assert count_month_changes(table, merged, MONTHS) == (2, 1)


def test_filling_a_blank_counts_as_a_change() -> None:
    """빈칸에 값을 넣은 것은 변경이다 — 저장되는 값이 실제로 달라진다."""
    table = _table([("가", None, 2.0)])
    merged = table.copy()
    merged.loc[0, "202601"] = 0.0

    assert count_month_changes(table, merged, MONTHS) == (1, 1)


def test_counting_follows_the_merged_whole_table_not_the_visible_rows() -> None:
    """필터로 가려진 행의 변경도 세어야 한다.

    변경량을 **되머지 결과**와 원본으로 재는 이유다. 화면에 보이는 편집표로 재면 필터
    밖에서 일어난 변경이 요약에서 사라지는데, 저장은 그 행까지 한다.
    """
    table = _table([("가", 1.0, 2.0), ("나", 3.0, 4.0)])
    # 화면에는 「나」만 보이고 그 행을 고쳤다.
    visible_edited = table.loc[[1]].copy()
    visible_edited.loc[1, "202601"] = 99.0
    merged = merge_edited_months(table, visible_edited, DIMENSIONS, MONTHS)

    assert merged.shape == table.shape
    assert count_month_changes(table, merged, MONTHS) == (1, 1)
