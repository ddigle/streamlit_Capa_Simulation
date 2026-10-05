# Purpose: 월별 표의 분류 컬럼 배경색이 작은 표에만 입혀지고 큰 표에서는 빠지는지 검증한다.

"""분류 컬럼 배경색(pandas Styler)은 칸 수 상한 이하의 표에만 입힌다.

Streamlit 은 Styler 를 그릴 때마다 표의 모든 칸을 번역해 큰 표에서 rerun 마다 1초 넘게
들었다. `month_editor.CLASSIFICATION_STYLE_MAX_CELLS` 를 넘는 표는 배경색 없이 그리고, 그
이하의 표는 **전과 똑같이** 그린다 — 마샬링한 proto 바이트가 예전 식과 같아야 한다.
"""

import pandas as pd
from pandas.io.formats.style import Styler
from streamlit.elements.lib.pandas_styler_utils import marshall_styler
from streamlit.proto.ArrowData_pb2 import ArrowData
from streamlit.testing.v1 import AppTest

from capa_simulation.components.month_editor import (
    CLASSIFICATION_STYLE_MAX_CELLS,
    classification_styled,
)
from capa_simulation.design import tokens

DIMENSIONS = ["공정", "Area_Name"]


def _table(cells: int) -> pd.DataFrame:
    """분류 2열 + 월 2열, 칸 수가 정확히 `cells` 인 표(`cells` 는 4의 배수)."""
    assert cells % 4 == 0
    rows = cells // 4
    return pd.DataFrame(
        {
            "공정": [f"Process-{index % 7}" for index in range(rows)],
            "Area_Name": ["Main"] * rows,
            "202608": [float(index) for index in range(rows)],
            "202609": [float(index) * 2 for index in range(rows)],
        }
    )


def test_table_at_the_cell_limit_keeps_the_classification_background() -> None:
    table = _table(CLASSIFICATION_STYLE_MAX_CELLS)
    assert table.size == CLASSIFICATION_STYLE_MAX_CELLS

    assert isinstance(classification_styled(table, DIMENSIONS), Styler)


def test_table_over_the_cell_limit_is_drawn_without_styler() -> None:
    table = _table(CLASSIFICATION_STYLE_MAX_CELLS + 4)

    result = classification_styled(table, DIMENSIONS)

    assert not isinstance(result, Styler)
    assert result is table


def test_small_table_marshals_exactly_as_before() -> None:
    """작은 표는 예전 식(`table.style.set_properties`)과 같은 proto 를 낸다."""
    table = _table(40)
    before = table.style.set_properties(
        subset=pd.Index(DIMENSIONS),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )
    after = classification_styled(table, DIMENSIONS)
    assert isinstance(after, Styler)

    # pandas 는 Styler 마다 무작위 uuid 를 붙인다. CSS 선택자가 그 uuid 를 담으므로 맞춰 둔다.
    before.set_uuid("fixed")
    after.set_uuid("fixed")
    expected, actual = ArrowData(), ArrowData()
    marshall_styler(expected, before, "fixed")
    marshall_styler(actual, after, "fixed")

    assert actual.SerializeToString() == expected.SerializeToString()
    assert f"background-color: {tokens.SURFACE_CLASSIFICATION}" in actual.styler.styles


EDITOR_SCRIPT = r"""
import pandas as pd
import streamlit as st

import capa_simulation.components.month_editor as month_editor
from capa_simulation.components.tab_state import stateful_tabs

ROWS = 3
table = pd.DataFrame(
    {
        "공정": [f"Process-{index}" for index in range(ROWS)],
        "202608": [float(index) for index in range(ROWS)],
        "202609": [float(index) for index in range(ROWS)],
    }
)
tabs = stateful_tabs(["편집"], key="style_test_tab")
month_editor.render_month_editor(
    tabs[0],
    table,
    ["공정"],
    "style_demo_editor",
    "%,.0f",
    1.0,
    table_name="RQ_DEMO",
    csv_file_name="demo.csv",
    dialog_key="style_demo_dialog",
    on_paste=lambda imported: None,
    card_name="style_demo",
)
"""


def _editor_styles(rows: int) -> str:
    app = AppTest.from_string(
        EDITOR_SCRIPT.replace("ROWS = 3", f"ROWS = {rows}"), default_timeout=60
    ).run()
    assert not app.exception
    (editor,) = app.get("dataframe")
    return str(editor.proto.arrow_data.styler.styles)


def test_month_editor_paints_small_tables_and_skips_large_ones() -> None:
    """편집기는 그리는 표가 상한 이하이면 분류 컬럼을 칠하고, 넘으면 Styler 를 보내지 않는다."""
    small_styles = _editor_styles(3)
    large_rows = CLASSIFICATION_STYLE_MAX_CELLS // 3 + 1

    assert f"background-color: {tokens.SURFACE_CLASSIFICATION}" in small_styles
    assert _editor_styles(large_rows) == ""
