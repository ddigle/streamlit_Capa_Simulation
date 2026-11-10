# Purpose: 공정 Capa 상세 시트 엑셀이 화면 그림과 같은 칸 글 · 칠 · 띠를 숫자 셀로 옮기는지 본다.

"""`components/process_capa_workbook.py` — 결합 캔버스와 같은 행 모델을 엑셀로.

재료는 결합 캔버스 시험의 합성 공정(`tests/test_process_capa_canvas.py`)이다. 판정 · 미달 칠 · 띠를
다시 셈하지 않고 그림과 같은 칸을 옮기는지 — 엑셀이 보일 글(숫자 꼴로 다시 적은 글)이 그림 칸 글과
같고 칠이 그림 칸 색과 같은지 — 를 본다. 통의 꼴은 `tests/test_xlsx_small.py` 가 본다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pandas as pd
import pytest
from test_process_capa_canvas import (
    AVAILABLE,
    MONTHS,
    REQUIRED,
    THRESHOLDS,
    _assumed_summary,
    _canvas,
    _dynamic,
    _products,
    _row_fills,
    _row_texts,
    _summary,
)
from xlsx_read import ReadSheet, read_workbook

from capa_simulation.components.process_capa_canvas import (
    ROW_BALANCE,
    ROW_DYNAMIC_BALANCE,
    ROW_RATE,
    SECTION_DOWNTIME,
    SECTION_UNITS,
    AssumptionCanvasInput,
)
from capa_simulation.components.process_capa_workbook import (
    DETAIL_SHEET,
    UNITS_SHEET,
    WorkbookRequest,
    process_capa_workbook,
    screen_number,
)
from capa_simulation.design import theme, tokens
from capa_simulation.services.month_columns import month_label

MINUS = "−"
LABEL = "Die Attach"


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _home() -> dict[int, float | None]:
    return {m: a / r + 0.02 for m, a, r in zip(MONTHS, AVAILABLE, REQUIRED, strict=True)}


def _request(**changes: object) -> WorkbookRequest:
    values: dict[str, object] = {
        "heading": (("공정", LABEL), ("조회기간", "26.11–27.06")),
        "process_label": LABEL,
        "months": tuple(MONTHS),
        "summary": _summary(),
        "thresholds": THRESHOLDS,
        "product_demand": _products(),
        "home_rates": _home(),
        "dynamic": _dynamic(),
    }
    values.update(changes)
    return WorkbookRequest(**values)  # type: ignore[arg-type]


def _detail(request: WorkbookRequest) -> ReadSheet:
    return read_workbook(process_capa_workbook(request))[DETAIL_SHEET]


def _excel_text(value: float, code: str) -> str:
    """이 시트가 쓰는 숫자 꼴만 — 엑셀이 그 값을 어떤 글로 보일지(시험용 작은 해석기)."""
    sections = code.split(";")
    if value > 0 or len(sections) == 1:
        section = sections[0]
    elif value < 0:
        section = sections[1]
    else:
        section = sections[2] if len(sections) > 2 else sections[0]
    shown = abs(value) if len(sections) > 1 and value < 0 else value
    match = re.fullmatch(r'(".*?")?(\+)?(".*?")?(#,##0|0)(\.0+)?(%)?(".*?")?', section)
    assert match is not None, section
    head, plus, middle, whole, decimals, percent, tail = match.groups()
    number = shown * 100 if percent else shown
    digits = len(decimals) - 1 if decimals else 0
    grouping = "," if whole == "#,##0" else ""
    body = f"{number:{grouping}.{digits}f}" + ("%" if percent else "")
    return "".join(
        [
            (head or "").strip('"'),
            plus or "",
            (middle or "").strip('"'),
            body,
            (tail or "").strip('"'),
        ]
    )


@pytest.mark.parametrize(
    ("text", "value", "shown"),
    [
        ("25.0", 25.0, "25.0"),
        ("1,234.5", 1234.5, "1,234.5"),
        ("126%", 1.26, "126%"),
        ("98%", 0.98, "98%"),
        ("110%", 1.1, "110%"),
        ("1234%", 12.34, "1234%"),
        ("1234", 1234.0, "1234"),
        ("+3", 3.0, "+3"),
        (f"{MINUS}2", -2.0, f"{MINUS}2"),
        ("0", 0.0, "0"),
        ("+1.9", 1.9, "+1.9"),
        (f"{MINUS}0.04", -0.04, f"{MINUS}0.04"),
        ("0.0", 0.0, "0.0"),
        (f"{MINUS}2.5대", -2.5, f"{MINUS}2.5대"),
        (f"{MINUS}10.8%", -0.108, f"{MINUS}10.8%"),
        ("→ 25.7", 25.7, "→ 25.7"),
        ("→ +0.02", 0.02, "→ +0.02"),
        (f"→ {MINUS}3.4", -3.4, f"→ {MINUS}3.4"),
        ("1.25⚠", 1.25, "1.25⚠"),
        ("24.0 ⚠", 24.0, "24.0 ⚠"),
    ],
)
def test_a_screen_number_reads_back_as_the_same_text(text: str, value: float, shown: str) -> None:
    parsed = screen_number(text)
    assert parsed is not None
    assert parsed[0] == pytest.approx(value)
    assert _excel_text(parsed[0], parsed[1]) == shown


@pytest.mark.parametrize("text", ["", "—", "기준✕·일정✕", "기한 지남", "26.11", "남은 날 부족"])
def test_words_and_month_labels_stay_text(text: str) -> None:
    if text == "26.11":
        # 달 머리는 숫자 꼴이지만 머리 줄은 글자로 쓴다 — 여기서는 해석기만 본다.
        assert screen_number(text) is not None
        return
    assert screen_number(text) is None


def test_value_rows_show_the_canvas_text_with_the_canvas_fill() -> None:
    """엑셀이 보일 글은 그림 칸 글과 같고(숫자 셀), 칠은 그림 칸 색과 같다 — ① 확보율 · 과부족과 ②
    목표 과부족에서 칠한 칸 모두."""
    canvas = _canvas(dynamic=_dynamic())
    sheet = _detail(_request())
    for row_id, label in (
        (ROW_RATE, "확보율"),
        (ROW_BALANCE, "확보 기준(110%) 과부족"),
        (ROW_DYNAMIC_BALANCE, "목표(110%) 과부족"),
    ):
        row = sheet.find_row(label)
        texts = _row_texts(canvas, row_id)
        fills = _row_fills(canvas, row_id)
        for index, (text, _) in texts.items():
            plain = re.sub(r"</?b>", "", text)
            cell = sheet.cells[(row, 2 + index)]
            assert cell.numeric, (label, plain)
            assert isinstance(cell.value, float)
            assert _excel_text(cell.value, cell.number_format) == plain
            if index in fills:
                assert cell.fill == "FF" + fills[index].lstrip("#").upper()
                assert cell.bold


def test_the_header_months_and_the_shortage_band_follow_the_canvas() -> None:
    """머리 줄은 화면 달 그대로(글자), 고정은 머리 아래 · 구분 두 열 뒤. 부족 달 띠는 그 줄 면 위에
    `SHORTAGE_MONTH_BAND` 알파를 섞은 불투명 색이다."""
    sheet = _detail(_request())
    header = sheet.find_row(f"구분 · {LABEL}")
    assert sheet.row(header)[2:] == [month_label(month) for month in MONTHS]
    assert sheet.freeze == (header + 1, 2)
    owned = sheet.find_row("총보유대수")
    statuses = _summary()["판정"].tolist()
    alpha = float(tokens.SHORTAGE_MONTH_BAND.rsplit(",", 1)[1].rstrip(")"))
    banded = tokens.opaque_mix(tokens.STATUS_SHORTAGE, tokens.SUMMARY_SUPPLY_SURFACE, alpha).lstrip(
        "#"
    )
    for index, status in enumerate(statuses):
        fill = sheet.cells[(owned, 2 + index)].fill
        if status in ("warning", "shortage"):
            assert fill == "FF" + banded
        else:
            assert fill == "FF" + tokens.SUMMARY_SUPPLY_SURFACE.lstrip("#").upper()


def test_two_line_cells_get_a_following_row_with_the_same_paint() -> None:
    sheet = _detail(_request())
    main = sheet.find_row("목표(110%) 과부족")
    sub = main + 1
    assert sheet.cells[(sub, 0)].value == "└ 단축 후 · 상태"
    painted = [
        index
        for index in range(len(MONTHS))
        if sheet.cells[(main, 2 + index)].fill == "FF" + tokens.STATUS_SHORTAGE.lstrip("#")
    ]
    assert painted
    for index in painted:
        assert sheet.cells[(sub, 2 + index)].fill == sheet.cells[(main, 2 + index)].fill
    assert sheet.cells[(sheet.find_row("가용 (환산)") + 1, 0)].value == "└ 단축 후"
    assert sheet.cells[(sheet.find_row("비가동 영향") + 1, 0)].value == "└ 확보율 영향"


def test_folded_sections_and_the_product_toggle_follow_the_screen() -> None:
    folded = _detail(
        _request(product_demand=None, collapsed=frozenset({SECTION_UNITS, SECTION_DOWNTIME}))
    )
    labels = [str(value) for value in folded.column(0) if value is not None]
    assert "소요대수 ▸" in labels and not any(label.startswith("└ PRODUCT") for label in labels)
    assert "③ 신규 설비 일정과 단축 ▸" in labels and "④ 호기별 비가동 ▸" in labels
    assert "EQ-21" not in labels
    opened = [str(value) for value in _detail(_request()).column(0) if value is not None]
    assert "소요대수 ▾" in opened and "└ PRODUCT_A" in opened
    assert "③ 신규 설비 일정과 단축 ▾" in opened and "EQ-21" in opened
    assert "확보율 (HOME 표시)" in opened


def test_the_units_and_downtime_rows_are_words_where_the_marks_are() -> None:
    sheet = _detail(_request())
    before_arrival = [
        cell
        for (row, column), cell in sheet.cells.items()
        if column >= 2 and isinstance(cell.value, str) and cell.value.startswith("반입 전 · ◀ ")
    ]
    assert before_arrival
    assert all(cell.fill == "FF" + tokens.STATUS_WARNING.lstrip("#") for cell in before_arrival)
    words = " ".join(str(cell.value) for (row, column), cell in sheet.cells.items() if column >= 2)
    for mark in ("◆ 반입", "● 기여 시작", f"◀ {MINUS}", "◌ 신규 필요", "해소"):
        assert mark in words, mark
    loss = tokens.EQUIPMENT_STAGE_COLORS["운영 비가동"].lstrip("#").upper()
    assert any(
        cell.color == "FF" + loss and "▶" in str(cell.value)
        for (row, column), cell in sheet.cells.items()
        if column >= 2
    )
    detail = sheet.cells[(sheet.find_row("EQ-22"), 1)].value
    assert isinstance(detail, str) and detail.startswith("기존 ") and " → 단축 " in detail


def test_the_assumption_rows_and_heading_stand_as_on_screen() -> None:
    window = set(MONTHS[:3])
    request = _request(
        heading=(("공정", LABEL), ("UPEH 가정", "UPEH 가정 120% · 26.11–27.01")),
        assumption=AssumptionCanvasInput(
            percent=120, months=frozenset(window), summary=_assumed_summary(120, window)
        ),
    )
    sheet = _detail(request)
    assert sheet.row(2)[:2] == ["UPEH 가정", "UPEH 가정 120% · 26.11–27.01"]
    row = sheet.find_row("UPEH 120% · 확보율")
    inside = [sheet.cells[(row, 2 + index)].value for index in range(len(MONTHS))]
    assert all(isinstance(value, float) for value in inside[:3])
    assert all(value is None for value in inside[3:])


def test_the_sheet_stays_light_under_a_dark_screen_and_restores_the_theme() -> None:
    light = process_capa_workbook(_request())
    theme._LOCAL.mode = "dark"
    try:
        dark_screen = process_capa_workbook(_request())
        assert theme.current_mode() == "dark"
    finally:
        theme._LOCAL.mode = "light"
    assert dark_screen == light


def test_the_units_sheet_is_the_csv_table() -> None:
    frame = pd.DataFrame(
        {
            "목표 확보율(%)": pd.array([110, None], dtype="Int64"),
            "호기": ["EQ-21", "추가1"],
            "단축일수": pd.array([17, pd.NA], dtype="Int64"),
            "늘어난 환산대수": [0.1666666, float("nan")],
            "대상 월": ["2027-01", ""],
        }
    )
    book = read_workbook(process_capa_workbook(_request(units_export=frame)))
    assert list(book) == [DETAIL_SHEET, UNITS_SHEET]
    units = book[UNITS_SHEET]
    assert units.row(0) == list(frame.columns)
    assert units.freeze == (1, 0)
    assert units.cells[(1, 0)].numeric and units.cells[(1, 0)].value == 110.0
    assert units.cells[(1, 3)].value == pytest.approx(0.1666666)
    assert units.cells[(2, 0)].value is None and units.cells[(2, 2)].value is None
    assert units.cells[(2, 3)].value is None
    assert units.cells[(1, 4)].value == "2027-01" and not units.cells[(1, 4)].numeric
    without = read_workbook(process_capa_workbook(_request(units_export=None)))
    assert list(without) == [DETAIL_SHEET]
