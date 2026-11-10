# Purpose: 분류 고정 월 표(산출 결과 대당 Capa · 소요대수)를 화면 글자 · 서식 그대로 엑셀로 옮긴다.

"""산출 결과 「시트 엑셀」 — 분류 고정 월 표 하나를 화면 그대로.

화면 표(`hierarchical_monthly_table.render_hierarchical_monthly_table`)가 그리는 것을 칸 하나하나로
옮긴다. 무엇을 그릴지는 부르는 쪽이 화면에 넘긴 것과 **같은 인자**(거른 표 · 분류 열 · 열 이름 ·
소수 자리 · 표시명)로 정한다.

- **분류 칸 글** — 화면의 공개 내보내기(`build_hierarchical_monthly_export` — CSV 와 같은 반복 접두
  생략)에 화면 표시명을 입힌 표를 넘겨 얻는다. 그래서 위 줄과 같은 앞부분은 비고, 공정은 화면처럼
  표시명이다(CSV 는 원본 — 이 시트는 화면 그대로다).
- **월 칸** — 화면이 쓰는 꼴(`,.nf` · `.n%`)로 적은 글이 적는 값을 숫자 셀로, 같은 글로 보이는 엑셀
  숫자 꼴(`#,##0` · `#,##0.00` · `0.00%`)을 붙인다. 0 · 빈 값은 화면처럼 빈 칸이다.
- **서식** — 밝은 테마 토큰(엑셀은 흰 바탕 — `theme.pinned_mode`). 머리 띠(`HEADER_BACKGROUND` ·
  굵게), 최상위 묶음 줄무늬(분류 칸 `SURFACE_CLASSIFICATION` · `_GROUP`, 월 칸 `SURFACE` ·
  `SURFACE_SUBTLE`), 묶음 경계선(바뀐 분류 열부터 오른쪽 끝까지, 최상위가 바뀌면 굵게), 분류 열
  사이 · 달 사이 가는 선, 분기 경계 · 분류와 달 사이 · 바깥 테두리는 굵은 선. 판정 칠은 없다(이 두
  표는 화면에도 판정 색이 없다). 열 너비는 화면 px(`classification_widths` ·
  `MONTH_COLUMN_WIDTH_PX`)를 엑셀 단위로, 머리 줄과 분류 열을 고정한다.
- 맨 위에 제목과 (이름, 값) 머리 줄(시나리오 · 조회기간 · 보기 · 거름)을 두고 한 줄 띄운다.

순수 함수다 — Streamlit 을 import 하지 않고 세션 · 캐시를 읽지 않는다. 화면은 그 바이트를 조건 키로
세션에 기억한다(`sheet_download.remembered_bytes`).
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

import pandas as pd

from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
)
from capa_simulation.components.monthly_table_base import (
    classification_cell_text,
    classification_widths,
    display_value_text,
    month_label,
    quarter_key,
)
from capa_simulation.design import theme, tokens
from capa_simulation.io.xlsx_small import Edge, Sheet, Style, XlsxCell, workbook_bytes

__all__ = [
    "MonthlySheetRequest",
    "monthly_table_sheet",
    "monthly_table_workbook",
    "screen_cell_value",
]

ValueFormat = Literal["number", "percent"]

# 화면 px → 엑셀 열 너비(맑은 고딕 10pt 숫자 한 글자 ≈ 7.7px — 공정 Capa 상세 시트와 같은 눈금).
PX_PER_WIDTH: Final = 7.7
# 글자 크기(pt) — 값 · 머리 값 줄 · 제목.
VALUE_SIZE: Final = 10.0
SMALL_SIZE: Final = 9.0
TITLE_SIZE: Final = 12.0


@dataclass(frozen=True, eq=False)
class MonthlySheetRequest:
    """시트 하나의 재료 — 화면 표에 넘긴 것과 같은 인자(회차가 값으로 잡아 넘긴다).

    `data` 는 화면이 그린 표(거름 · 표시순서까지 끝난 것), `heading` 은 제목 아래 (이름, 값) 줄이다.
    `value_labels` 는 분류 열 → {원본: 화면 글자}(공정 표시명)다.
    """

    sheet_name: str
    title: str
    data: pd.DataFrame
    classification_columns: tuple[str, ...]
    column_labels: Mapping[str, str]
    decimal_places: int
    heading: tuple[tuple[str, str], ...] = ()
    value_labels: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    value_format: ValueFormat = "number"


def monthly_table_workbook(request: MonthlySheetRequest) -> bytes:
    """엑셀 통 바이트 — 시트 하나(`request.sheet_name`)."""
    with theme.pinned_mode("light"):
        sheet = monthly_table_sheet(request)
    return workbook_bytes([sheet])


def monthly_table_sheet(request: MonthlySheetRequest) -> Sheet:
    """화면 표 → 시트. 색은 지금 테마의 토큰이다 — `monthly_table_workbook` 이 밝게로 못박고
    부른다."""
    columns = list(request.classification_columns)
    data = request.data
    months = [column for column in data.columns if column not in columns]
    shown = _shown_classifications(data, columns, request.value_labels)
    blanked = _blanked_classifications(
        shown, columns, request.column_labels, request.decimal_places
    )
    widths_px = classification_widths(
        [[classification_cell_text(text, None) for text in values] for values in blanked],
        columns,
        request.column_labels,
    )
    rows: list[list[XlsxCell | None]] = [
        [XlsxCell(request.title, Style(bold=True, size=TITLE_SIZE, color=_hex(tokens.TEXT)))]
    ]
    for name, value in request.heading:
        rows.append(
            [
                XlsxCell(name, Style(color=_hex(tokens.TEXT_MUTED), size=SMALL_SIZE)),
                XlsxCell(value, Style(color=_hex(tokens.TEXT), size=SMALL_SIZE)),
            ]
        )
    rows.append([])
    header_index = len(rows)
    looks = _Looks(
        months,
        len(columns),
        _number_format(request.decimal_places, request.value_format),
    )
    header: list[XlsxCell | None] = [
        XlsxCell(request.column_labels.get(column, column), looks.header(index))
        for index, column in enumerate(columns)
    ]
    header += [
        XlsxCell(month_label(str(month)), looks.header(len(columns) + index))
        for index, month in enumerate(months)
    ]
    rows.append(header)
    groups = _top_groups(shown)
    changed = _changed_columns(shown)
    numeric = [pd.to_numeric(data[month], errors="coerce").to_numpy() for month in months]
    count = len(data)
    for position in range(count):
        odd = groups[position] % 2 == 1
        boundary = changed[position] if position else None
        last = position == count - 1
        line: list[XlsxCell | None] = [
            XlsxCell(
                values[position] or None,
                looks.label(index, odd=odd, boundary=boundary, last=last),
            )
            for index, values in enumerate(blanked)
        ]
        line += [
            XlsxCell(
                screen_cell_value(values[position], request.decimal_places, request.value_format),
                looks.month(index, odd=odd, boundary=boundary, last=last),
            )
            for index, values in enumerate(numeric)
        ]
        rows.append(line)
    widths = {index: _width(px) for index, px in enumerate(widths_px)}
    widths.update(
        {len(columns) + index: _width(tokens.MONTH_COLUMN_WIDTH_PX) for index in range(len(months))}
    )
    return Sheet(
        name=request.sheet_name,
        rows=rows,
        widths=widths,
        freeze=(header_index + 1, len(columns)),
    )


# ================================================================== 칸 글 · 값


def _shown_classifications(
    data: pd.DataFrame,
    columns: Sequence[str],
    value_labels: Mapping[str, Mapping[str, str]],
) -> list[list[str]]:
    """분류 열마다 화면 글자(표시명 적용 — `display_value_text`, 반복 생략 전)."""
    return [
        [display_value_text(value, value_labels.get(column)) for value in data[column]]
        for column in columns
    ]


def _blanked_classifications(
    shown: Sequence[Sequence[str]],
    columns: Sequence[str],
    column_labels: Mapping[str, str],
    decimal_places: int,
) -> list[list[str]]:
    """분류 칸 글 — 화면 글자 표를 화면의 공개 내보내기에 넘겨 반복 접두를 비운다(CSV 와 같은
    길)."""
    if not columns:
        return []
    frame = pd.DataFrame(
        {column: list(values) for column, values in zip(columns, shown, strict=True)}
    )
    # 내보내기는 달 열이 하나는 있어야 행을 낸다 — 글만 보므로 0 한 열을 붙였다 뗀다.
    frame["__month__"] = 1.0
    export = build_hierarchical_monthly_export(
        frame,
        classification_columns=list(columns),
        column_labels={},
        decimal_places=decimal_places,
    )
    return [["" if pd.isna(text) else str(text) for text in export[column]] for column in columns]


def screen_cell_value(
    value: object, decimal_places: int, value_format: ValueFormat
) -> float | None:
    """화면 월 칸 글이 적는 값 — 0 · 빈 값은 None(빈 칸). 화면 글(`,.nf` · `.n%`)을 그대로 되읽어
    엑셀이 화면과 다르게 반올림하지 않게 한다."""
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return None
    number = float(value)
    if math.isnan(number) or number == 0:
        return None
    if value_format == "percent":
        text = format(number, f".{decimal_places}%")
        return round(float(text[:-1]) / 100, decimal_places + 2)
    return float(format(number, f",.{decimal_places}f").replace(",", ""))


def _number_format(decimal_places: int, value_format: ValueFormat) -> str:
    fraction = f".{'0' * decimal_places}" if decimal_places > 0 else ""
    if value_format == "percent":
        return f"0{fraction}%"
    return f"#,##0{fraction}"


# ================================================================== 묶음


def _top_groups(shown: Sequence[Sequence[str]]) -> list[int]:
    """줄마다 최상위 묶음 번호 — 첫 분류 열 글자가 바뀔 때 하나 는다(줄무늬)."""
    if not shown:
        return []
    groups: list[int] = []
    current = -1
    previous: str | None = None
    for position, text in enumerate(shown[0]):
        if position == 0 or text != previous:
            current += 1
        groups.append(current)
        previous = text
    return groups


def _changed_columns(shown: Sequence[Sequence[str]]) -> list[int]:
    """줄마다 앞 줄과 처음 다른 분류 열 번호(모두 같으면 마지막 열) — 묶음 경계선이 그 열에서
    선다."""
    if not shown:
        return []
    count = len(shown[0])
    last = len(shown) - 1
    changed = [0]
    for position in range(1, count):
        changed.append(
            next(
                (
                    index
                    for index, values in enumerate(shown)
                    if values[position] != values[position - 1]
                ),
                last,
            )
        )
    return changed


# ================================================================== 칸 서식


class _Looks:
    """시트 하나의 칸 서식 — 토큰 색을 한 번 읽고, 같은 서식은 같은 객체로 돌려준다(칸마다 서식을
    새로 지어 검사하면 2,660줄 표에서 짓는 시간의 대부분이 서식 검사였다 — 합성 표 샘플 관측).

    선: 바깥 테두리 · 머리 선 · 분류와 달 사이 · 분기 경계는 굵은 선(`BORDER_STRONG`), 분류 열
    사이 · 달 사이는 가는 선(`BORDER`). 묶음 경계선은 바뀐 분류 열부터 오른쪽 끝까지 — 최상위가
    바뀌면 굵게, 깊으면 가늘게(화면은 깊어질수록 가늘어지는 `BORDER_STRONG`).
    """

    def __init__(self, months: Sequence[str], column_count: int, number_format: str) -> None:
        self._text = _hex(tokens.TEXT)
        self._header_fill = _hex(tokens.HEADER_BACKGROUND)
        self._strong = Edge("medium", _hex(tokens.BORDER_STRONG))
        self._grid = Edge("thin", _hex(tokens.BORDER))
        self._minor = Edge("thin", _hex(tokens.BORDER_STRONG))
        self._label_fills = (
            _hex(tokens.SURFACE_CLASSIFICATION),
            _hex(tokens.SURFACE_CLASSIFICATION_GROUP),
        )
        subtle = _hex(tokens.SURFACE_SUBTLE)
        self._month_faces = (None, None if subtle == _hex(tokens.SURFACE) else subtle)
        self._month_lefts = [self._month_left(months, index) for index in range(len(months))]
        self._columns = column_count
        self._months = len(months)
        self._number_format = number_format
        self._cache: dict[tuple[object, ...], Style] = {}

    def header(self, index: int) -> Style:
        """머리 칸(분류 열 다음 달 열 차례의 `index`) — 회색 띠 · 굵게 · 위 바깥 · 아래 머리 선."""
        key: tuple[object, ...] = ("header", self._left(index), self._right(index))
        style = self._cache.get(key)
        if style is None:
            style = Style(
                bold=True,
                color=self._text,
                fill=self._header_fill,
                horizontal="center",
                left=self._left(index),
                top=self._strong,
                bottom=self._strong,
                right=self._right(index),
            )
            self._cache[key] = style
        return style

    def label(self, index: int, *, odd: bool, boundary: int | None, last: bool) -> Style:
        """분류 칸 — 묶음 줄무늬, 경계선은 바뀐 열(`boundary`)부터."""
        top = self._boundary(boundary) if boundary is not None and index >= boundary else None
        return self._body(index, self._label_fills[odd], None, top, last)

    def month(self, index: int, *, odd: bool, boundary: int | None, last: bool) -> Style:
        """달 칸 — 줄 면 · 숫자 꼴, 경계선은 줄 전체."""
        column = self._columns + index
        top = self._boundary(boundary) if boundary is not None else None
        return self._body(column, self._month_faces[odd], self._number_format, top, last)

    def _body(
        self, column: int, fill: str | None, number_format: str | None, top: Edge | None, last: bool
    ) -> Style:
        key: tuple[object, ...] = ("body", column if column < self._columns else -1, fill, top)
        key += (last, self._left(column), self._right(column), number_format)
        style = self._cache.get(key)
        if style is None:
            style = Style(
                color=self._text,
                size=VALUE_SIZE,
                fill=fill,
                number_format=number_format,
                horizontal="center",
                left=self._left(column),
                top=top,
                bottom=self._strong if last else None,
                right=self._right(column),
            )
            self._cache[key] = style
        return style

    def _boundary(self, changed: int) -> Edge:
        return self._strong if changed == 0 else self._minor

    def _left(self, column: int) -> Edge:
        if column == 0:
            return self._strong
        if column < self._columns:
            return self._grid
        return self._month_lefts[column - self._columns]

    def _right(self, column: int) -> Edge | None:
        return self._strong if column == self._columns + self._months - 1 else None

    def _month_left(self, months: Sequence[str], index: int) -> Edge:
        """달 칸 왼쪽 선 — 첫 달은 분류와 가르는 굵은 선, 분기가 바뀌는 달은 굵은 선, 그 밖은
        가는 선."""
        if index == 0:
            return self._strong
        current = quarter_key(str(months[index]))
        previous = quarter_key(str(months[index - 1]))
        if current is not None and previous is not None and current != previous:
            return self._strong
        return self._grid


def _width(px: float) -> float:
    return round(px / PX_PER_WIDTH, 1)


def _hex(color: str) -> str:
    """토큰 색 → 불투명 `#RRGGBB`(반투명이면 흰 면 위에 섞는다)."""
    solid = tokens.opaque_over(color, tokens.SURFACE)
    if solid is None:
        raise ValueError(f"엑셀 색으로 옮길 수 없습니다: {color!r}")
    return solid
