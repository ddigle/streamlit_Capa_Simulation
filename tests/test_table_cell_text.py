# Purpose: 분류 셀 글자가 Plotly 행 높이를 흔들지 않는지 고정한다.

"""분류 셀 글자 치환 계약.

Plotly `go.Table` 은 칸 글자에 `&`·`<`·`>` 가 하나라도 있으면 HTML 해석 경로로 넘어가
**그 행만** 높이 바닥을 올린다. 브라우저 실측으로 27px → 35px 였다(1.30배).

격자·그룹 경계선은 행 높이가 균일하다는 전제로 paper 좌표에 그리므로, 그런 행 하나가
그 아래 전부를 8px 씩 밀어낸다. 사용자 신고가 정확히 이것이었다 — 공정 표시명에 `&` 가
둘 있어 두 행이 1.25배쯤 높아졌고, 그 아래가 반 칸 밀린 채 표 끝까지 유지됐다.

`&amp;` 로 이스케이프해도 같은 경로를 탄다(실측). 그래서 글자 자체를 전각으로 바꾼다.
"""

import pandas as pd

from capa_simulation.components.grouped_monthly_table import build_grouped_monthly_export
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
)
from capa_simulation.components.monthly_table_base import (
    classification_cell_text,
    restore_cell_text,
)

# 이 셋이 행 높이를 올린다. 공백은 올리지 않지만 줄바꿈을 막으려고 예전부터 함께 바꾼다.
ROW_HEIGHT_BREAKERS = ("&", "<", ">")


def test_the_three_row_height_breakers_never_reach_a_cell() -> None:
    text = classification_cell_text("B/D & Cure <Main>", None)

    for character in ROW_HEIGHT_BREAKERS:
        assert character not in text, (character, text)
    assert " " not in text, text


def test_escaping_is_not_a_fix_so_we_substitute_the_glyph() -> None:
    """`&amp;` 도 같은 HTML 경로를 탄다. 전각으로 바꿔야 행 높이가 그대로다."""
    text = classification_cell_text("A&B", None)

    assert "&amp;" not in text
    assert text == "A＆B"


def test_a_name_without_breakers_is_left_alone() -> None:
    assert classification_cell_text("Wafer_Sorter", None) == "Wafer_Sorter"
    assert classification_cell_text("AVI-CoW", None) == "AVI-CoW"
    assert classification_cell_text("B/D", None) == "B/D"


def test_restore_puts_the_original_glyphs_back() -> None:
    original = "B/D & Cure <Main>"

    assert restore_cell_text(classification_cell_text(original, None)) == original


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["A&B", "A&B", "C<D"],
            "소요기준": ["WF", "CHIP", "WF"],
            202601: [1.0, 2.0, 3.0],
        }
    )


def test_the_hierarchical_csv_keeps_the_original_glyphs() -> None:
    """화면 글자를 그대로 내보내면 Excel VLOOKUP 이 조용히 어긋난다."""
    export = build_hierarchical_monthly_export(
        _frame(),
        classification_columns=["공정", "소요기준"],
        column_labels={},
        decimal_places=0,
    )

    assert export["공정"].tolist() == ["A&B", "", "C<D"]


def test_the_grouped_csv_keeps_the_original_glyphs() -> None:
    export = build_grouped_monthly_export(
        _frame(),
        classification_columns=["공정", "소요기준"],
        column_labels={},
    )

    assert "A&B" in export["공정"].tolist()
