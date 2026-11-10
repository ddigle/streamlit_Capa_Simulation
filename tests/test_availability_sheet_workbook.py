# Purpose: Static 대비 일정 시트 엑셀이 화면 9행 시트의 칸 글 · 색 · 면을 숫자 셀로 옮기는지 본다.

"""`components/availability_sheet_workbook.py` — 화면 9행 시트와 같은 행 모델을 엑셀로.

재료는 시트 캔버스 시험의 합성 범위(`tests/test_availability_sheet_panel.py::_view`)다. 칸 글 ·
GAP 증감 글자색 · Static 묶음 면을 다시 셈하지 않고 그림과 같은 행 모델
(`build_availability_sheet_rows`)을 옮기는지 — 엑셀이 보일 글(숫자 꼴로 다시 적은 글)이 그림 칸
글과 같은지 — 를 본다. 화면 쪽(「내려받기 ▾」 메뉴 · 통 기억)은
`tests/test_availability_gap_panel.py` 가 본다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from test_availability_sheet_panel import MONTHS, _view
from test_process_capa_workbook import _excel_text
from xlsx_read import ReadSheet, read_workbook

from capa_simulation.components.availability_sheet_canvas import (
    GROUP_TITLES,
    STATIC_TITLE_DETAIL,
    build_availability_sheet_rows,
)
from capa_simulation.components.availability_sheet_workbook import (
    GAP_SHEET_NAME,
    GapWorkbookRequest,
    availability_sheet_workbook,
)
from capa_simulation.components.month_sheet_canvas import EMPTY
from capa_simulation.design import theme, tokens
from capa_simulation.services.availability_sheet import (
    GAP_ROWS,
    ROW_ITEMS,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_OWNED,
    SHEET_ROWS,
)
from capa_simulation.services.month_columns import month_label

HEADING = (("공정", "공정 · 표시"), ("조회기간", "26.10–26.11"), ("설비 시나리오", "「운영」 r3"))
DETAIL = "설비 DB · 환산대수"


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _sheet() -> ReadSheet:
    request = GapWorkbookRequest(
        view=_view(), process_label="공정 · 표시", schedule_detail=DETAIL, heading=HEADING
    )
    book = read_workbook(availability_sheet_workbook(request))
    assert list(book) == [GAP_SHEET_NAME]
    return book[GAP_SHEET_NAME]


def _argb(color: str) -> str:
    """토큰 색 → 엑셀이 되읽는 꼴(「FF」 + 불투명 RRGGBB)."""
    return "FF" + str(tokens.opaque_over(color, tokens.SURFACE)).lstrip("#").upper()


def _shown(sheet: ReadSheet, row: int, column: int) -> str | None:
    """엑셀이 그 칸에 보일 글 — 숫자 셀은 숫자 꼴로 다시 적은 글."""
    cell = sheet.cells.get((row, column))
    if cell is None or cell.value is None:
        return None
    if cell.numeric:
        assert isinstance(cell.value, float)
        return _excel_text(cell.value, cell.number_format)
    return str(cell.value)


def test_the_sheet_heads_with_the_title_and_the_screen_conditions() -> None:
    sheet = _sheet()
    assert sheet.row(0) == ["Static 대비 일정 · 분류별 내역"]
    assert [sheet.row(index)[:2] for index in range(1, 1 + len(HEADING))] == [
        list(pair) for pair in HEADING
    ]
    header = 1 + len(HEADING) + 1
    assert sheet.row(header) == [
        "구분 · 공정 · 표시",
        None,
        *(month_label(month) for month in MONTHS),
    ]
    # 머리 줄 · 구분 · 세부 두 열은 고정이다(공정 Capa 상세 시트와 같은 꼴).
    assert sheet.freeze == (header + 1, 2)


def test_the_rows_carry_the_screen_texts_and_colours_of_the_same_row_model() -> None:
    """그림이 읽는 행 모델과 칸마다 같은 글 · 글자색 · 면 — 구획 제목 셋(세부 글은 「세부」 열)과 값
    아홉, 「—」 칸은 흐린 글자, ⚠ 표지는 숫자 꼴 꼬리, GAP 은 증감 글자색이다."""
    sheet = _sheet()
    with theme.pinned_mode("light"):
        rows = build_availability_sheet_rows(
            view=_view(), process_label="공정 · 표시", schedule_detail=DETAIL
        )
    header = 1 + len(HEADING) + 1
    labels = [row.label for row in rows[1:]]
    assert labels == [
        GROUP_TITLES["static"],
        *(ROW_ITEMS[row] for row in SHEET_ROWS[:3]),
        GROUP_TITLES["sched"],
        *(ROW_ITEMS[row] for row in SHEET_ROWS[3:6]),
        GROUP_TITLES["gap"],
        *(ROW_ITEMS[row] for row in SHEET_ROWS[6:]),
    ]
    for offset, row in enumerate(rows[1:], start=1):
        line = header + offset
        assert sheet.row(line)[0] == row.label
        if row.detail:
            assert sheet.row(line)[1] == row.detail
        for index in range(len(MONTHS)):
            cell = row.cells.get(index)
            if cell is None:
                continue
            assert _shown(sheet, line, 2 + index) == cell.text, (row.row_id, index)
            read = sheet.cells[(line, 2 + index)]
            expected = cell.text_color or (tokens.TEXT_MUTED if cell.muted else tokens.TEXT)
            assert read.color == _argb(expected), (row.row_id, index)
    static_title = header + 1
    assert sheet.row(static_title)[1] == STATIC_TITLE_DETAIL
    line_of = {row.row_id: header + offset for offset, row in enumerate(rows[1:], start=1)}
    owned = line_of[ROW_STATIC_OWNED]
    # Static 묶음은 화면처럼 공급 면이고, 값 줄 이름은 들인다(글자 크기는 그대로).
    assert sheet.cells[(owned, 2)].fill == _argb(tokens.SUMMARY_SUPPLY_SURFACE)
    available = line_of[ROW_STATIC_AVAILABLE]
    # 원값부터 다른 달(⚠)은 숫자 셀 + 꼬리 「 ⚠」 다.
    assert sheet.cells[(available, 2)].numeric
    assert str(_shown(sheet, available, 2)).endswith(" ⚠")
    gap = line_of[GAP_ROWS[0]]
    assert sheet.cells[(gap, 2)].numeric and sheet.cells[(gap, 2)].value == -2.5
    assert sheet.cells[(gap, 2)].color == _argb(tokens.DELTA_DECREASE)
    # Static 이 없는 달은 「—」 흐린 글자 셀이다(까닭은 화면 풍선 — 엑셀에 싣지 않는다).
    assert _shown(sheet, gap, 3) == EMPTY and not sheet.cells[(gap, 3)].numeric


def test_the_chosen_cell_is_a_screen_mark_and_stays_out_of_the_sheet() -> None:
    """고른 칸 굵은 글자 · 테두리는 화면 조작 표지라 엑셀에 옮기지 않는다 — 통은 고른 칸과 상관없이
    같다(그래서 칸 누름이 통을 다시 짓지 않는다)."""
    sheet = _sheet()
    header = 1 + len(HEADING) + 1
    assert not any(
        sheet.cells[(line, column)].bold
        for line in range(header + 1, header + 1 + 12)
        for column in range(2, 2 + len(MONTHS))
        if (line, column) in sheet.cells
    )
