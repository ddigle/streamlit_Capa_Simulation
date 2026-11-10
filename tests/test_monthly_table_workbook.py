# Purpose: 산출 결과 시트 엑셀이 화면 월 표와 같은 칸 글 · 줄무늬 · 숫자 꼴 · 선을 옮기는지 본다.

"""`components/monthly_table_workbook.py` — 분류 고정 월 표를 화면 그대로.

화면 표(`render_hierarchical_monthly_table`)가 Figure 를 짓는 인자(`build_split_table_figures`)를
잡아 시트와 견준다 — 분류 칸 글(반복 접두 생략 · 표시명), 분류 칸 · 월 칸 줄무늬, 월 칸 글이 엑셀이
보일 글과 같은지. 통의 꼴은 `tests/test_xlsx_small.py` 가 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from xlsx_read import ReadSheet, read_workbook

import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
from capa_simulation.components.monthly_table_base import COLUMN_LABELS, restore_cell_text
from capa_simulation.components.monthly_table_workbook import (
    MonthlySheetRequest,
    monthly_table_workbook,
    screen_cell_value,
)
from capa_simulation.design import theme, tokens

MONTHS = ["202611", "202612", "202701"]
LABELS = {"공정": {"Process-A": "가공 & 조립"}}
HEADING = (("시나리오", "합성 · r1"), ("조회기간", "26.11–27.01"), ("공정", "전체"))
# 제목 한 줄 · 머리 값 줄 · 빈 줄 다음이 표 머리 줄이다.
HEADER = 1 + len(HEADING) + 1


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _table() -> pd.DataFrame:
    """공정 둘(Process-A 는 표시명 있음) · 소요기준 · 제품 — 위 줄과 같은 앞부분이 비는 꼴, 0 · 빈
    값, 반올림 경계(2.5 · 1234.565), 천 단위 값."""
    return pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A", "Process-A", "Process-B", "Process-B"],
            "소요기준": ["WF", "WF", "CHIP", "PKG", "PKG"],
            "제품정보": ["P1", "P2", "P1", "P1", "P1"],
            "202611": [2.5, 0.0, 1234.565, None, 12.004],
            "202612": [1500.0, 3.333, 0.0, 7.0, 0.5],
            "202701": [None, 1.0, 2.0, 3.0, 4.0],
        }
    )


def _request(decimal_places: int, **changes: Any) -> MonthlySheetRequest:
    values: dict[str, Any] = {
        "sheet_name": "대당 Capa",
        "title": "공정별 대당 Capa",
        "data": _table(),
        "classification_columns": ("공정", "소요기준", "제품정보"),
        "column_labels": COLUMN_LABELS,
        "decimal_places": decimal_places,
        "heading": HEADING,
        "value_labels": LABELS,
    }
    values.update(changes)
    return MonthlySheetRequest(**values)


class _Captured(Exception):
    pass


def _screen(monkeypatch: pytest.MonkeyPatch, decimal_places: int) -> dict[str, Any]:
    """화면 표가 Figure 를 짓는 인자 — 그리기 전에 멈춘다."""
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        raise _Captured

    monkeypatch.setattr(hierarchical_table, "build_split_table_figures", capture)
    with pytest.raises(_Captured):
        hierarchical_table.render_hierarchical_monthly_table(
            _table(),
            classification_columns=["공정", "소요기준", "제품정보"],
            column_labels=COLUMN_LABELS,
            decimal_places=decimal_places,
            key="workbook_parity",
            value_labels=LABELS,
        )
    return captured


def _sheet(decimal_places: int) -> tuple[ReadSheet, int]:
    book = read_workbook(monthly_table_workbook(_request(decimal_places)))
    return book["대당 Capa"], HEADER


def _argb(color: str) -> str:
    return "FF" + color.lstrip("#").upper()


@pytest.mark.parametrize("decimal_places", [0, 2])
def test_the_sheet_holds_the_screen_cells(
    monkeypatch: pytest.MonkeyPatch, decimal_places: int
) -> None:
    """분류 칸 글(반복 접두 생략 · 표시명) · 칠, 월 칸이 보일 글 · 칠이 화면 표와 같다."""
    screen = _screen(monkeypatch, decimal_places)
    sheet, header = _sheet(decimal_places)
    rows = range(header + 1, header + 1 + len(_table()))

    for column, values in enumerate(screen["classification_values"]):
        assert [sheet.cells[(row, column)].value or "" for row in rows] == [
            restore_cell_text(text) for text in values
        ]
    for column, fills in enumerate(screen["classification_fill_colors"]):
        assert [sheet.cells[(row, column)].fill for row in rows] == [_argb(fill) for fill in fills]
    surface = _argb(tokens.SURFACE)
    for offset, texts in enumerate(screen["month_values"]):
        column = 3 + offset
        shown = []
        for row in rows:
            cell = sheet.cells[(row, column)]
            if cell.value is None:
                shown.append("")
                continue
            assert cell.numeric and isinstance(cell.value, float)
            assert cell.number_format == ("#,##0.00" if decimal_places else "#,##0")
            shown.append(format(cell.value, f",.{decimal_places}f"))
        assert shown == texts
        assert [sheet.cells[(row, column)].fill or surface for row in rows] == [
            _argb(color) for color in screen["month_row_colors"]
        ]


def test_heading_title_freeze_and_widths() -> None:
    sheet, header = _sheet(0)

    assert sheet.row(0) == ["공정별 대당 Capa"]
    assert [tuple(sheet.row(index)) for index in range(1, 1 + len(HEADING))] == list(HEADING)
    assert sheet.row(header) == ["공정", "소요기준", "제품", "26.11", "26.12", "27.01"]
    assert all(sheet.cells[(header, column)].bold for column in range(6))
    assert sheet.cells[(header, 0)].fill == _argb(tokens.HEADER_BACKGROUND)
    assert sheet.freeze == (header + 1, 3)
    # 달 칸 100px · 분류 칸은 화면 px 를 같은 눈금(7.7px)으로.
    assert sheet.widths[3] == sheet.widths[5] == round(tokens.MONTH_COLUMN_WIDTH_PX / 7.7, 1)
    assert all(
        sheet.widths[column] >= round(tokens.CLASSIFICATION_MIN_WIDTH_PX / 7.7, 1)
        for column in range(3)
    )


def test_group_boundaries_quarter_and_outer_lines() -> None:
    """묶음 경계선은 바뀐 분류 열부터(최상위가 바뀌면 굵게), 분기가 바뀌는 달 · 분류와 달 사이 ·
    바깥은 굵은 선, 그 밖은 가는 선."""
    sheet, header = _sheet(2)
    strong = f"medium:{_argb(tokens.BORDER_STRONG)}"
    minor = f"thin:{_argb(tokens.BORDER_STRONG)}"
    grid = f"thin:{_argb(tokens.BORDER)}"
    first = header + 1

    # 둘째 줄은 제품만 바뀐다 — 공정 · 소요기준 칸에는 선이 없고 제품 칸부터 달 끝까지 가는 선.
    assert [sheet.cells[(first + 1, column)].top for column in range(6)] == [
        None,
        None,
        minor,
        minor,
        minor,
        minor,
    ]
    # 넷째 줄은 공정이 바뀐다 — 줄 전체 굵은 선.
    assert {sheet.cells[(first + 3, column)].top for column in range(6)} == {strong}
    # 다섯째 줄은 앞 줄과 같다 — 마지막 분류 열부터.
    assert sheet.cells[(first + 4, 1)].top is None
    assert sheet.cells[(first + 4, 2)].top == minor
    # 세로선: 첫 칸 · 분류와 달 사이 · 27.01(분기 바뀜)은 굵게, 분류 열 사이 · 26.12 는 가늘게.
    assert [sheet.cells[(first, column)].left for column in range(6)] == [
        strong,
        grid,
        grid,
        strong,
        grid,
        strong,
    ]
    assert sheet.cells[(first, 5)].right == strong
    assert {sheet.cells[(first + 4, column)].bottom for column in range(6)} == {strong}
    assert sheet.cells[(first, 0)].top is None


def test_values_are_what_the_screen_writes() -> None:
    """엑셀 값은 화면 글이 적는 값이다 — 엑셀이 화면과 다르게 반올림하지 않는다. 0 · 빈 값은 빈
    칸."""
    assert screen_cell_value(2.5, 0, "number") == 2.0  # 화면 「2」(파이썬 서식 반올림)
    assert screen_cell_value(1234.565, 2, "number") == float(format(1234.565, ".2f"))
    assert screen_cell_value(0.0, 2, "number") is None
    assert screen_cell_value(float("nan"), 2, "number") is None
    assert screen_cell_value(None, 2, "number") is None
    assert screen_cell_value(pd.NA, 2, "number") is None
    assert screen_cell_value(1.23456, 2, "percent") == 1.2346
    book = read_workbook(
        monthly_table_workbook(_request(2, value_format="percent", sheet_name="확보율"))
    )
    sheet = book["확보율"]
    cell = sheet.cells[(HEADER + 1, 3)]
    assert cell.number_format == "0.00%" and cell.value == 2.5  # 화면 「250.00%」


def test_an_empty_table_still_writes_the_heading_and_header() -> None:
    request = _request(0, data=_table().iloc[0:0])
    sheet = read_workbook(monthly_table_workbook(request))["대당 Capa"]
    assert sheet.row(HEADER)[:3] == ["공정", "소요기준", "제품"]
    assert not sheet.row(HEADER + 1)


def test_the_same_request_gives_the_same_bytes() -> None:
    assert monthly_table_workbook(_request(2)) == monthly_table_workbook(_request(2))
