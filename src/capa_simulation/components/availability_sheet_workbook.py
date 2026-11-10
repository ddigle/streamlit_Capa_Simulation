# Purpose: 가용설비 현황 「Static 대비 일정」 9행 시트 · 호기 목록을 화면 서식째 엑셀 통으로 짓는다.

"""「Static 대비 일정」 시트 엑셀.

화면 시트가 그리는 **같은 행 모델**(`availability_sheet_canvas.build_availability_sheet_rows`)을
읽어 공정 Capa 상세 시트 엑셀과 같은 길(`process_capa_workbook.month_rows_sheet`)로 칸 하나하나
옮긴다 — 칸 글 · GAP 증감 글자색 · Static 묶음 면 · 「—」 흐린 글자 · ⚠ 표지를 다시 셈하지 않는다
(화면과 갈리면 안 된다). 그래서 공정(하나 또는 전체 합계) · 조회기간의 달 · 호기 필터(설비 일정
기준만, Static · GAP 은 「—」) · 입력 비가동 반영이 화면 그대로 선다.

- **서식** — 밝은 테마 토큰(엑셀은 흰 바탕 — `theme.pinned_mode`). 고른 칸 테두리 · 굵은 글자는 화면
  조작 표지라 옮기지 않는다(공정 Capa 상세의 지금 보는 달 테두리와 같다). 「—」 칸의 까닭은 화면
  풍선이라 엑셀에는 「—」 만 선다.
- **숫자는 숫자 셀** — 칸 글(소수 2자리 · 부호 · U+2212 · 「 ⚠」)을 같은 글로 보이는 숫자 꼴로
  되읽는다(`process_capa_workbook.screen_number`).

**호기 목록**(`표시` 를 `호기 목록` 으로 바꾼 보기 — 목록 아래 CSV 와 짝)은 화면 표(`st.dataframe`)
그대로 — 공정 표시명 · 분류 거름 · 같은 열 · 화면 숫자 꼴(`%.3f` → `0.000`)의 숫자 칸 · 빈 값은 빈
칸 · 회색 머리 줄(고정)이다(`unit_list_workbook`).

순수 함수다 — Streamlit 을 import 하지 않고 세션 · 캐시를 읽지 않는다. 화면은 그 바이트를 조건
키로 세션에 기억한다(`availability_gap_panel.render_sheet_downloads` —
`sheet_download.remembered_bytes`).
"""

from __future__ import annotations

import math
import numbers
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from capa_simulation.components.availability_sheet_canvas import build_availability_sheet_rows
from capa_simulation.components.process_capa_workbook import month_rows_sheet
from capa_simulation.design import theme, tokens
from capa_simulation.io.xlsx_small import Edge, Sheet, Style, XlsxCell, workbook_bytes
from capa_simulation.services.availability_sheet import SheetView

__all__ = [
    "GAP_SHEET_NAME",
    "UNIT_LIST_SHEET",
    "GapWorkbookRequest",
    "UnitListWorkbookRequest",
    "availability_sheet_workbook",
    "excel_number_format",
    "unit_list_workbook",
]

GAP_SHEET_NAME: Final = "Static 대비 일정"
TITLE: Final = "Static 대비 일정 · 분류별 내역"
UNIT_LIST_SHEET: Final = "호기 목록"
UNIT_LIST_TITLE: Final = "Static 대비 일정 · 호기 목록"
# 글자 크기(pt) — 값 · 머리 값 줄 · 제목(공정 Capa 상세 시트와 같다).
VALUE_SIZE: Final = 10.0
SMALL_SIZE: Final = 9.0
TITLE_SIZE: Final = 12.0
# 열 너비의 끝(엑셀 단위 ≈ 숫자 한 글자).
MIN_WIDTH: Final = 6.0
MAX_WIDTH: Final = 40.0


@dataclass(frozen=True, eq=False)
class GapWorkbookRequest:
    """엑셀 한 벌의 재료 — 화면 회차가 값으로 잡아 넘긴다. 시트 인자는 화면 시트와 같고(고른 칸만
    없음), `heading` 은 맨 위 (이름, 값) 줄이다(공정 · 조회기간 · 설비 시나리오 · 호기 필터)."""

    view: SheetView
    process_label: str
    schedule_detail: str
    heading: Sequence[tuple[str, str]]


def availability_sheet_workbook(request: GapWorkbookRequest) -> bytes:
    """엑셀 통 바이트 — 시트 「Static 대비 일정」 한 장."""
    with theme.pinned_mode("light"):
        rows = build_availability_sheet_rows(
            view=request.view,
            process_label=request.process_label,
            schedule_detail=request.schedule_detail,
        )
        sheet = month_rows_sheet(
            name=GAP_SHEET_NAME,
            title=TITLE,
            rows=rows,
            axis=[int(month) for month in request.view.months],
            heading=request.heading,
        )
    return workbook_bytes([sheet])


# ================================================================== 호기 목록


@dataclass(frozen=True, eq=False)
class UnitListWorkbookRequest:
    """호기 목록 엑셀의 재료 — 화면 표 그대로(표시명을 입힌 것)와 열마다 소수 자릿수(화면
    `NumberColumn` 꼴과 같은 수), 맨 위 (이름, 값) 줄."""

    table: pd.DataFrame
    digits: Mapping[str, int]
    heading: Sequence[tuple[str, str]]


def excel_number_format(digits: int) -> str:
    """화면 숫자 꼴 `%.{n}f`(천 단위 쉼표 없음)와 같은 글로 보이는 엑셀 숫자 꼴."""
    return "0" + (f".{'0' * digits}" if digits > 0 else "")


def unit_list_workbook(request: UnitListWorkbookRequest) -> bytes:
    """엑셀 통 바이트 — 시트 「호기 목록」 한 장."""
    with theme.pinned_mode("light"):
        sheet = _unit_list_sheet(request)
    return workbook_bytes([sheet])


def _unit_list_sheet(request: UnitListWorkbookRequest) -> Sheet:
    """맨 위 제목 · 머리 값 줄, 한 줄 띄고 머리(고정) · 행. 숫자 열은 화면 자릿수 꼴의 숫자
    칸이다."""
    text = _hex(tokens.TEXT)
    muted = _hex(tokens.TEXT_MUTED)
    rows: list[list[XlsxCell | None]] = [
        [XlsxCell(UNIT_LIST_TITLE, Style(bold=True, size=TITLE_SIZE, color=text))]
    ]
    for item, value in request.heading:
        rows.append(
            [
                XlsxCell(item, Style(color=muted, size=SMALL_SIZE)),
                XlsxCell(value, Style(color=text, size=SMALL_SIZE)),
            ]
        )
    rows.append([])
    header_index = len(rows)
    header_style = Style(
        bold=True,
        color=text,
        fill=_hex(tokens.HEADER_BACKGROUND),
        horizontal="center",
        bottom=Edge("medium", _hex(tokens.BORDER_STRONG)),
    )
    columns = [str(column) for column in request.table.columns]
    rows.append([XlsxCell(name, header_style) for name in columns])
    grid = Edge("thin", _hex(tokens.BORDER))
    styles = [
        Style(
            color=text,
            size=VALUE_SIZE,
            number_format=(
                excel_number_format(request.digits[name]) if name in request.digits else None
            ),
            bottom=grid,
        )
        for name in columns
    ]
    widths = [_text_width(name) for name in columns]
    for record in request.table.itertuples(index=False, name=None):
        line: list[XlsxCell | None] = []
        for position, value in enumerate(record):
            cell_value = _plain_value(value)
            line.append(XlsxCell(cell_value, styles[position]))
            if cell_value is not None:
                widths[position] = max(widths[position], _text_width(str(cell_value)))
        rows.append(line)
    return Sheet(
        name=UNIT_LIST_SHEET,
        rows=rows,
        widths={
            position: min(MAX_WIDTH, max(MIN_WIDTH, width + 2))
            for position, width in enumerate(widths)
        },
        freeze=(header_index + 1, 0),
    )


def _plain_value(value: object) -> str | int | float | None:
    """표 칸 값 → 엑셀 칸 값. pandas 빈 값(NA · NaN · NaT)은 빈 칸(화면 `placeholder=""`), 숫자는
    숫자, 그 밖은 글자."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else None
    return str(value)


def _hex(color: str) -> str:
    """토큰 색 → 불투명 `#RRGGBB`(반투명이면 흰 면 위에 섞는다)."""
    solid = tokens.opaque_over(color, tokens.SURFACE)
    if not solid:
        raise ValueError(f"엑셀 색으로 옮길 수 없습니다: {color!r}")
    return solid


def _text_width(text: str) -> float:
    """엑셀 열 너비 어림 — 넓은 글자(한글)는 둘, 그 밖은 하나."""
    return float(sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text))
