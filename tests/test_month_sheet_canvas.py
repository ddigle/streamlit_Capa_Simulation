# Purpose: 월 시트 캔버스 엔진의 글자색·고른 칸 테두리·풍선 없는 칸·줄 이름 칸 풍선을 검사한다.

"""월 시트 캔버스 엔진(`components/month_sheet_canvas.py`).

공정 Capa 상세 결합 캔버스의 출력은 `tests/test_process_capa_canvas.py` 가 그대로 지킨다. 여기는
엔진에 더한 것 — 칸 글자색, 고른 칸 테두리, 풍선 없는 칸의 표적, 줄 이름 칸 풍선, 서식 자릿수, 그림
`meta` — 만 본다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import plotly.io as pio
import pytest

from capa_simulation.components.home_figure_common import keep_unselected_opaque
from capa_simulation.components.month_sheet_canvas import (
    CUSTOMDATA_HOVER,
    CUSTOMDATA_MONTH,
    CUSTOMDATA_ROW,
    HEADER_HEIGHT_PX,
    KIND_HEADER,
    KIND_VALUE,
    SELECTED_BORDER_PX,
    VALUE_ROW_HEIGHT_PX,
    Cell,
    Row,
    canvas_point,
    fine_one,
    label_figure,
    month_figure,
    one,
    signed_one,
    stack_rows,
    title_row,
)
from capa_simulation.components.plotly_layout import flush_layout_items
from capa_simulation.design import theme, tokens

AXIS = [202610, 202611, 202612]


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _rows() -> list[Row]:
    header = Row("header", KIND_HEADER, HEADER_HEIGHT_PX, label="구분", clickable=False)
    plain = Row("plain", KIND_VALUE, VALUE_ROW_HEIGHT_PX, label="보유")
    colored = Row("colored", KIND_VALUE, VALUE_ROW_HEIGHT_PX, label="GAP")
    for index in range(len(AXIS)):
        plain.cells[index] = Cell(text=one(1.5 + index, 2), hover="h")
        colored.cells[index] = Cell(
            text=signed_one(index - 1.0, 2),
            text_color=(tokens.DELTA_DECREASE, tokens.TEXT_MUTED, tokens.DELTA_INCREASE)[index],
            hover="g",
        )
    return [header, title_row("t", "묶음", "세부"), plain, colored]


def _json(figure: Any) -> Any:
    return json.loads(pio.to_json(figure, validate=False))


def _figure(**kwargs: Any) -> Any:
    rows = _rows()
    height = stack_rows(rows)
    figure = month_figure(rows, AXIS, height, **kwargs)
    flush_layout_items(figure)
    keep_unselected_opaque(figure)
    return _json(figure)


def test_cell_text_colours_split_into_one_trace_per_colour() -> None:
    """칸마다 글자색을 주면 (색, 크기)마다 글자 trace 하나다 — 한 값인 글자색이라 눌러도 흐려지지
    않는다(`keep_unselected_opaque` 가 못박는다)."""
    figure = _figure()
    texts = [trace for trace in figure["data"] if trace.get("mode") == "text"]
    colors = {trace["textfont"]["color"] for trace in texts}
    assert {tokens.TEXT, tokens.DELTA_DECREASE, tokens.DELTA_INCREASE, tokens.TEXT_MUTED} <= colors
    for trace in texts:
        assert isinstance(trace["textfont"]["color"], str)
        assert trace["unselected"]["textfont"]["color"] == trace["textfont"]["color"]
    decrease = next(trace for trace in texts if trace["textfont"]["color"] == tokens.DELTA_DECREASE)
    assert decrease["text"] == ["−1.00"]


def test_the_header_row_draws_no_target_and_value_cells_carry_month_and_row() -> None:
    figure = _figure()
    targets = figure["data"][0]["customdata"]
    assert len(targets) == 2 * len(AXIS)
    assert {(item[CUSTOMDATA_MONTH], item[CUSTOMDATA_ROW]) for item in targets} == {
        (month, row) for month in AXIS for row in ("plain", "colored")
    }


def test_cells_without_a_hover_get_a_silent_target_that_still_selects() -> None:
    """풍선 글이 빈 칸은 둘째 표적 trace 다 — `hoverinfo: "none"` 에 `hovertemplate` 가 없어
    풍선 상자가 뜨지 않고(한 trace 에 두면 빈 글에도 빈 상자가 뜬다), 달 · 행 id 를 실어 누르면
    그 칸이 골라진다. 그런 칸이 없으면 trace 도 없다(위 시험의 그림 그대로)."""
    rows = _rows()
    quiet = Row("quiet", KIND_VALUE, VALUE_ROW_HEIGHT_PX, label="호기")
    for index in range(len(AXIS)):
        quiet.cells[index] = Cell(hover="풍선" if index == 1 else "")
    rows.append(quiet)
    figure = month_figure(rows, AXIS, stack_rows(rows))
    keep_unselected_opaque(figure)
    hovered, silent = (trace for trace in _json(figure)["data"] if trace.get("customdata"))

    assert hovered["hovertemplate"] == "%{customdata[2]}<extra></extra>"
    assert [item[CUSTOMDATA_MONTH] for item in hovered["customdata"] if item[1] == "quiet"] == [
        AXIS[1]
    ]
    assert silent["hoverinfo"] == "none" and "hovertemplate" not in silent
    assert [(item[CUSTOMDATA_MONTH], item[CUSTOMDATA_ROW]) for item in silent["customdata"]] == [
        (AXIS[0], "quiet"),
        (AXIS[2], "quiet"),
    ]
    assert all(item[CUSTOMDATA_HOVER] == "" for item in silent["customdata"])
    assert silent["unselected"]["marker"]["opacity"] == 1
    point = {"selection": {"points": [{"customdata": silent["customdata"][0]}]}}
    assert canvas_point(point) == (AXIS[0], "quiet")
    assert sum(1 for trace in _figure()["data"] if trace.get("customdata")) == 1


def test_label_hovers_put_one_target_bar_on_the_label_figure_only_when_given() -> None:
    rows = _rows()
    height = stack_rows(rows)
    assert _json(label_figure(rows, height))["data"] == []

    rows[2].label_hover = "줄 풍선"
    height = stack_rows(rows)
    figure = _json(label_figure(rows, height))
    (trace,) = figure["data"]
    assert trace["customdata"] == [["plain", "줄 풍선"]]
    assert trace["hovertemplate"] == "%{customdata[1]}<extra></extra>"
    assert trace["y"] == [pytest.approx(height - rows[2].top - rows[2].height / 2)]
    # 오른쪽 끝에서 왼쪽 끝으로 — 풍선이 막대 끝(왼쪽)에 붙어 오른쪽으로 펴진다.
    assert trace["width"] == [rows[2].height] and trace["base"] == [1.0] and trace["x"] == [-1.0]
    assert trace["marker"]["color"] == tokens.HIT_TARGET
    assert figure["layout"]["hovermode"] == "closest"


def test_the_selected_cell_gets_one_accent_border_and_none_without_a_choice() -> None:
    def borders(figure: Any) -> list[dict[str, Any]]:
        return [
            shape
            for shape in figure["layout"].get("shapes", [])
            if shape.get("type") == "rect" and shape.get("line", {}).get("color") == tokens.ACCENT
        ]

    assert borders(_figure()) == []
    chosen = borders(_figure(selected_cell=(1, "colored")))
    assert len(chosen) == 1
    border = chosen[0]
    assert border["line"]["width"] == SELECTED_BORDER_PX
    assert 1 < border["x0"] < border["x1"] < 2
    # 칸 하나 높이 안이다(값 행 27px).
    assert border["y1"] - border["y0"] == pytest.approx(VALUE_ROW_HEIGHT_PX - 2)
    # 축 밖 열·없는 행은 그리지 않는다.
    assert borders(_figure(selected_cell=(9, "colored"))) == []
    assert borders(_figure(selected_cell=(0, "missing"))) == []


def test_meta_rides_on_the_layout_without_changing_the_drawing() -> None:
    plain = _figure()
    tagged = _figure(meta={"generation": 3})
    assert tagged["layout"]["meta"] == {"generation": 3}
    del tagged["layout"]["meta"]
    assert tagged == plain


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (12.733, 1, "12.7"),
        (12.733, 2, "12.73"),
        (1234.5, 2, "1,234.50"),
        (None, 2, "—"),
    ],
)
def test_one_keeps_the_requested_digits(value: float | None, digits: int, expected: str) -> None:
    assert one(value, digits) == expected


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (0.0, 1, "0.0"),
        (0.0, 2, "0.00"),
        (-0.567, 2, "−0.57"),
        (0.004, 2, "+0.004"),
        (-0.04, 1, "−0.04"),
        (0.0004, 2, "0.00"),
        (1.0, 2, "+1.00"),
        (None, 2, "—"),
    ],
)
def test_signed_one_adds_one_digit_only_when_rounding_would_hide_the_value(
    value: float | None, digits: int, expected: str
) -> None:
    assert signed_one(value, digits) == expected


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (0.0, 2, "0.00"),
        (12.733, 2, "12.73"),
        (1234.5, 2, "1,234.50"),
        (0.0032, 2, "0.003"),
        (-0.0032, 2, "-0.003"),
        (0.0004, 2, "0.00"),
        (-0.0004, 2, "0.00"),
        (None, 2, "—"),
    ],
)
def test_fine_one_follows_the_signed_digit_rule_without_a_sign(
    value: float | None, digits: int, expected: str
) -> None:
    """부호 없는 칸도 그 자리로 0 이 되는 0 아닌 값은 한 자리 더 적는다 — 「0.00」 으로 적힌 칸에
    값이 숨지 않게."""
    assert fine_one(value, digits) == expected
