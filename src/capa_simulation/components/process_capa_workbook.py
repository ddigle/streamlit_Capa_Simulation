# Purpose: 월 시트 행 모델(공정 Capa 상세 · Static 대비 일정 시트)을 화면 서식째 엑셀로 옮긴다.

"""공정 Capa 상세 「시트 엑셀」.

화면이 그리는 **같은 행 모델**(`process_capa_canvas.build_process_capa_rows`)을 읽어 칸 하나하나를
엑셀 칸으로 옮긴다 — 판정 · 미달 칠 · 띠를 다시 셈하지 않는다(화면과 갈리면 안 된다). 그래서 켜진
구획(① ~ ⑤ 칩) · 「제품별 소요대수」 펼침과 분류 · 조회기간의 달 · UPEH 가정 세 줄 · HOME 표시
확보율 줄 · 「더 보기」 30줄 상한이 화면 그대로 선다.

- **서식** — 색은 `design/tokens.py` 의 밝은 테마 토큰이다(엑셀은 흰 바탕 — `theme.pinned_mode`).
  줄 면(① 공급 파랑 · 소요 베이지 · 제품 줄무늬 · 구획 제목 바탕) · 칸 칠(판정 3색 · 목표 미달) ·
  부족 달 세로 띠(`SHORTAGE_MONTH_BAND` 의 알파를 그 줄 면 위에 섞은 불투명 색 — 엑셀 칠에는 알파가
  없다) · 머리 아래 부족 달 띠(굵은 아래 테두리) · 묶음 경계(굵은 위 테두리) · 달 경계선 · 굵기 ·
  흐린 글자를 옮긴다. 지금 보는 달 테두리 · 오늘 점선은 화면 조작 표지라 옮기지 않는다.
- **숫자는 숫자 셀** — 칸 글(`one` · `percent` · `signed_int` · `signed_one` · 기준 % 라벨)을 그
  글이 적는 값과 같은 꼴의 숫자 꼴로 되읽는다(`screen_number`). 엑셀이 보이는 글은 화면 글과
  같다(값은 화면이 반올림한 값이다). 꼴을 모르는 글(「기준✕·일정✕」 · 「—」 · 「기한 지남」)은
  글자 셀이다.
- **두 줄 칸**(칸 둘째 줄 `Cell.sub`)은 숫자 셀 하나에 두 값을 못 담아 바로 아래에 「└ 둘째
  줄」 딸린 줄을 두고 같은 칠을 잇는다.
- **④ · ⑤** 는 그림 대신 글이다(`process_capa_canvas.track_texts` — 그림과 같은 자리) — 호기 줄
  이름 칸 옆 「세부」 열에 화면 둘째 줄(기존 → 단축 날짜 등)을 둔다.
- **둘째 시트**는 「이 공정 단축 일정 CSV」 와 같은 표(설비 일정이 설 때만)다.

행 모델 → 시트 한 장(`month_rows_sheet`)은 같은 월 시트 엔진(`month_sheet_canvas` 의 `Row` ·
`Cell`)을 쓰는 가용설비 현황 「Static 대비 일정」 시트 엑셀(`availability_sheet_workbook`)도 그대로
쓴다.

순수 함수다 — Streamlit 을 import 하지 않고 세션 · 캐시를 읽지 않는다. 회차가 값으로 잡아 넘긴
것(`WorkbookRequest`)만 쓰고, 화면은 그 바이트를 세션에 기억한다
(`process_capa_view.remembered_sheet`).
"""

from __future__ import annotations

import math
import numbers
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from capa_simulation.components.month_sheet_canvas import (
    KIND_ARROW,
    KIND_HEADER,
    KIND_NOTE,
    KIND_TITLE,
    KIND_UNIT,
    KIND_VALUE,
    Cell,
    Row,
)
from capa_simulation.components.process_capa_canvas import (
    AssumptionCanvasInput,
    DynamicCanvasInput,
    ProcessCapaRows,
    TrackText,
    build_process_capa_rows,
    track_texts,
)
from capa_simulation.design import theme, tokens
from capa_simulation.io.xlsx_small import Edge, Sheet, Style, XlsxCell, workbook_bytes
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.securement_threshold import SecurementThresholds

__all__ = [
    "DETAIL_SHEET",
    "UNITS_SHEET",
    "WorkbookRequest",
    "detail_sheet",
    "month_rows_sheet",
    "process_capa_workbook",
    "screen_number",
    "units_sheet",
]

DETAIL_SHEET: Final = "상세 Capa"
UNITS_SHEET: Final = "단축 일정"
TITLE: Final = "공정 Capa 상세"
# 열 — 구분(줄 이름) · 세부(화면 둘째 줄) · 달.
LABEL_COLUMN: Final = 0
DETAIL_COLUMN: Final = 1
FIRST_MONTH_COLUMN: Final = 2
# 열 너비(엑셀 단위 ≈ 숫자 한 글자). 라벨 칸 260px · 달 칸 100px 에 맞춘 값이다.
LABEL_WIDTH: Final = 34.0
DETAIL_WIDTH: Final = 30.0
MONTH_WIDTH: Final = 13.0
# 글자 크기(pt) — 값 · 제품 줄 · 둘째 줄 · 세부 글 · 제목.
VALUE_SIZE: Final = 10.0
SMALL_SIZE: Final = 9.0
TITLE_SIZE: Final = 12.0
# 두 줄 칸의 딸린 줄 이름 — 화면 풍선이 그 둘째 줄을 부르는 말이다.
SUB_ROW_LABELS: Final[Mapping[str, str]] = {}
SUB_ROW_FALLBACK: Final = "둘째 줄"
# 둘째 시트 열 너비의 끝(엑셀 단위).
UNITS_MIN_WIDTH: Final = 6.0
UNITS_MAX_WIDTH: Final = 40.0
# 화면 칸 글 → (값, 숫자 꼴). `one` · `percent` · `signed_int` · `signed_one` · 기준 % 라벨 ·
# 대수 「−1.8대」 · 입력 비가동 「1.25⚠」 · 둘째 줄 「→ 25.7」 꼴만 숫자다.
_SCREEN_NUMBER: Final = re.compile(
    r"^(?P<prefix>→ )?(?P<sign>[+−-])?(?P<whole>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.(?P<fraction>\d+))?(?P<percent>%)?(?P<unit>대)?(?P<mark> ?⚠)?$"
)


@dataclass(frozen=True, eq=False)
class WorkbookRequest:
    """엑셀 한 벌의 재료 — 화면 회차가 값으로 잡아 넘긴다(세션 · 캐시를 읽지 않는다).

    캔버스 인자는 `build_process_capa_rows` 와 같고(화면 상태 그대로), `heading` 은 시트 맨 위에
    적을 (이름, 값) 줄 — 공정 · 시나리오 · 조회기간 · 설비 시나리오 · 구획 같은 머리 띠 값이다.
    `units_export` 는 「이 공정 단축 일정 CSV」 와 같은 표(설비 일정이 서지 않으면 None — 시트
    없음).
    """

    heading: tuple[tuple[str, str], ...]
    process_label: str
    months: tuple[int, ...]
    summary: pd.DataFrame
    thresholds: SecurementThresholds
    product_demand: pd.DataFrame | None = None
    home_rates: Mapping[int, float | None] | None = None
    dynamic: DynamicCanvasInput | None = None
    collapsed: frozenset[str] = field(default_factory=frozenset)
    assumption: AssumptionCanvasInput | None = None
    units_export: pd.DataFrame | None = None


def process_capa_workbook(request: WorkbookRequest) -> bytes:
    """엑셀 통 바이트 — 첫 시트 「상세 Capa」, 설비 일정이 서면 둘째 시트 「단축 일정」."""
    with theme.pinned_mode("light"):
        model = build_process_capa_rows(
            process_label=request.process_label,
            months=request.months,
            summary=request.summary,
            thresholds=request.thresholds,
            product_demand=request.product_demand,
            home_rates=request.home_rates,
            dynamic=request.dynamic,
            collapsed=request.collapsed,
            assumption=request.assumption,
        )
        sheets = [detail_sheet(model, request.heading, request.dynamic)]
        if request.units_export is not None:
            sheets.append(units_sheet(request.units_export))
    return workbook_bytes(sheets)


# ================================================================== 상세 시트


def detail_sheet(
    model: ProcessCapaRows,
    heading: Sequence[tuple[str, str]],
    dynamic: DynamicCanvasInput | None,
) -> Sheet:
    """행 모델 → 「상세 Capa」 시트. 맨 위에 제목과 머리 값 줄, 한 줄 띄고 머리(달) · 행이다.

    색은 지금 테마의 토큰이다 — `process_capa_workbook` 이 밝게로 못박고 부른다.
    """
    return month_rows_sheet(
        name=DETAIL_SHEET,
        title=TITLE,
        rows=model.rows,
        axis=model.axis,
        shortage=frozenset(model.shortage_indices),
        heading=heading,
        dynamic=dynamic,
    )


def month_rows_sheet(
    *,
    name: str,
    title: str,
    rows: Sequence[Row],
    axis: Sequence[int],
    heading: Sequence[tuple[str, str]],
    shortage: frozenset[int] = frozenset(),
    dynamic: DynamicCanvasInput | None = None,
) -> Sheet:
    """월 시트 행 모델(첫 행이 머리) → 시트 한 장 — 맨 위에 제목과 머리 값 줄, 한 줄 띄고 머리(달) ·
    행이다. 열은 구분 · 세부 · 달, 머리 줄 · 두 열은 고정이다. `shortage` 는 부족 달 띠를 칠할 달
    자리, `dynamic` 은 ④ · ⑤ 호기 줄을 글로 옮길 재료(공정 Capa 상세만)다.

    색은 지금 테마의 토큰이다 — 부르는 쪽이 밝게로 못박고 부른다(`theme.pinned_mode`).
    """
    count = len(axis)
    last_column = FIRST_MONTH_COLUMN + count - 1
    sheet_rows: list[list[XlsxCell | None]] = [
        [XlsxCell(title, Style(bold=True, size=TITLE_SIZE, color=_hex(tokens.TEXT)))]
    ]
    for item, value in heading:
        sheet_rows.append(
            [
                XlsxCell(item, Style(color=_hex(tokens.TEXT_MUTED), size=SMALL_SIZE)),
                XlsxCell(value, Style(color=_hex(tokens.TEXT), size=SMALL_SIZE)),
            ]
        )
    sheet_rows.append([])
    header_index = len(sheet_rows)
    sheet_rows.append(_header_cells(rows[0], axis, shortage))
    for position, row in enumerate(rows[1:], start=1):
        strong_top = row.group_start or rows[position - 1].kind == KIND_HEADER
        sheet_rows += _body_rows(row, axis, shortage, dynamic, strong_top=strong_top)
    widths = {LABEL_COLUMN: LABEL_WIDTH, DETAIL_COLUMN: DETAIL_WIDTH}
    widths.update({column: MONTH_WIDTH for column in range(FIRST_MONTH_COLUMN, last_column + 1)})
    return Sheet(
        name=name,
        rows=sheet_rows,
        widths=widths,
        freeze=(header_index + 1, FIRST_MONTH_COLUMN),
    )


def _header_cells(row: Row, axis: Sequence[int], shortage: frozenset[int]) -> list[XlsxCell | None]:
    """머리 줄 — 회색 면 · 굵게, 달 칸 아래 테두리는 부족 달이면 부족색 띠(화면 4px 띠)다. 달 글은
    머리 칸 글이고, 칸이 비면 엔진이 그 자리에 그리는 달 이름(`month_label`)이다."""
    fill = _solid(row.month_fill) or _solid(tokens.HEADER_BACKGROUND)
    strong = Edge("medium", _hex(tokens.BORDER_STRONG))
    cells: list[XlsxCell | None] = [
        XlsxCell(
            row.label,
            Style(
                bold=True,
                color=_hex(tokens.TEXT),
                fill=_solid(row.label_fill) or fill,
                bottom=strong,
            ),
        ),
        XlsxCell(None, Style(fill=_solid(row.label_fill) or fill, bottom=strong)),
    ]
    for index in range(len(axis)):
        cell = row.cells.get(index)
        bottom = Edge("thick", _hex(tokens.STATUS_SHORTAGE)) if index in shortage else strong
        cells.append(
            XlsxCell(
                cell.text if cell is not None and cell.text else month_label(axis[index]),
                Style(
                    bold=True,
                    color=_hex(tokens.TEXT),
                    fill=fill,
                    horizontal="center",
                    left=_grid(),
                    bottom=bottom,
                ),
            )
        )
    return cells


def _body_rows(
    row: Row,
    axis: Sequence[int],
    shortage: frozenset[int],
    dynamic: DynamicCanvasInput | None,
    *,
    strong_top: bool,
) -> list[list[XlsxCell | None]]:
    """행 하나 → 엑셀 줄 하나(두 줄 칸이 있으면 딸린 줄까지 둘)."""
    count = len(axis)
    top = Edge("medium", _hex(tokens.BORDER_STRONG)) if strong_top else None
    label_fill = _solid(row.label_fill)
    label_style = Style(
        bold=row.label_bold,
        color=_hex(tokens.TEXT_MUTED if row.label_muted else tokens.TEXT),
        size=SMALL_SIZE if row.indent else VALUE_SIZE,
        fill=label_fill,
        # 제품 줄(`indent` — 글자도 작게)과 들인 값 줄(`label_indent` px — 글자 그대로)은 한 칸
        # 들인다.
        indent=1 if row.indent or row.label_indent > 0 else 0,
        top=top,
        bottom=_grid(),
    )
    detail_style = Style(
        color=_hex(tokens.TEXT_MUTED), size=SMALL_SIZE, fill=label_fill, top=top, bottom=_grid()
    )
    main: list[XlsxCell | None] = [
        XlsxCell(row.label, label_style),
        XlsxCell(row.detail or None, detail_style),
    ]
    tracks = (
        track_texts(row, axis, dynamic)
        if dynamic is not None and row.kind in (KIND_UNIT, KIND_ARROW)
        else {}
    )
    has_sub = row.kind == KIND_VALUE and any(cell.sub for cell in row.cells.values())
    sub: list[XlsxCell | None] = []
    if has_sub:
        sub_label = SUB_ROW_LABELS.get(row.row_id, SUB_ROW_FALLBACK)
        sub = [
            XlsxCell(
                f"└ {sub_label}",
                Style(
                    color=_hex(tokens.TEXT_MUTED),
                    size=SMALL_SIZE,
                    fill=label_fill,
                    indent=1,
                    bottom=_grid(),
                ),
            ),
            XlsxCell(None, Style(fill=label_fill, bottom=_grid())),
        ]
    for index in range(count):
        base = _month_base(row, index, shortage)
        cell = row.cells.get(index)
        if row.kind in (KIND_UNIT, KIND_ARROW):
            main.append(_track_cell(tracks.get(index), base, top=top))
            continue
        if row.kind in (KIND_TITLE, KIND_NOTE) or cell is None:
            main.append(XlsxCell(None, Style(fill=base, left=_grid(), top=top)))
            if has_sub:
                sub.append(XlsxCell(None, Style(fill=base, left=_grid())))
            continue
        main.append(_value_cell(cell.text, cell, base, size=_value_size(row), top=top))
        if has_sub:
            sub.append(_value_cell(cell.sub, cell, base, size=SMALL_SIZE, top=None))
    return [main, sub] if has_sub else [main]


def _value_cell(
    text: str, cell: Cell, base: str | None, *, size: float, top: Edge | None
) -> XlsxCell:
    """값 칸 하나 — 칸 칠 > 부족 띠 > 줄 면, 글자색은 칸 색 · 흐림 그대로, 숫자 꼴은 칸 글에서."""
    number = screen_number(text)
    style = Style(
        bold=cell.bold,
        color=_hex(cell.text_color or (tokens.TEXT_MUTED if cell.muted else tokens.TEXT)),
        size=size,
        fill=_solid(cell.fill) or base,
        number_format=number[1] if number is not None else None,
        horizontal="center",
        left=_grid(),
        top=top,
    )
    if number is not None:
        return XlsxCell(number[0], style)
    return XlsxCell(text or None, style)


def _track_cell(track: TrackText | None, base: str | None, *, top: Edge | None) -> XlsxCell:
    """④ · ⑤ 달 칸 — 그림 대신 글. 「반입 전」 은 경고색 칠, 가용을 깎은 화살표는 그 색 글자."""
    if track is None:
        return XlsxCell(None, Style(fill=base, left=_grid(), top=top))
    if track.loss:
        color = tokens.EQUIPMENT_STAGE_COLORS["운영 비가동"]
    elif track.muted:
        color = tokens.TEXT_MUTED
    else:
        color = tokens.TEXT
    return XlsxCell(
        track.text,
        Style(
            bold=track.warning,
            color=_hex(color),
            size=SMALL_SIZE,
            fill=_solid(tokens.STATUS_WARNING) if track.warning else base,
            horizontal="center",
            left=_grid(),
            top=top,
        ),
    )


def _value_size(row: Row) -> float:
    return SMALL_SIZE if row.indent else VALUE_SIZE


def _month_base(row: Row, index: int, shortage: frozenset[int]) -> str | None:
    """달 칸 바탕 — 줄 면(없으면 흰 면) 위에 부족 달이면 세로 띠를 섞은 불투명 색. 흰 면 그대로면
    칠하지 않는다(None)."""
    surface = _hex(tokens.SURFACE)
    face = _solid(row.month_fill) or surface
    if index in shortage:
        return _over(tokens.SHORTAGE_MONTH_BAND, face)
    return None if face == surface else face


def _grid() -> Edge:
    """달 경계선 · 라벨 칸 행 경계 — 화면의 1px `BORDER`."""
    return Edge("thin", _hex(tokens.BORDER))


# ================================================================== 숫자


def screen_number(text: str) -> tuple[float, str] | None:
    """화면 칸 글 → (그 글이 적는 값, 같은 글로 보이는 엑셀 숫자 꼴). 숫자 꼴이 아니면 None.

    「126%」 → (1.26, `#,##0%`), 「−2」 → (−2, `+#,##0;"−"#,##0;#,##0`), 「→ 25.7」 → (25.7,
    `"→ "#,##0.0`), 「−1.8대」 → (−1.8, …`"대"`…), 「1.25⚠」 → (1.25, `#,##0.00"⚠"`). 부호 글자는
    화면처럼 U+2212 다. 천 단위 쉼표도 글을 따른다 — 네 자리 이상인데 쉼표가 없으면(화면 % 글
    「1234%」) `0` 꼴이다.
    """
    match = _SCREEN_NUMBER.match(text.strip())
    if match is None:
        return None
    written = match.group("whole")
    whole = written.replace(",", "")
    fraction = match.group("fraction") or ""
    value = float(f"{whole}.{fraction}" if fraction else whole)
    sign = match.group("sign") or ""
    if sign in ("−", "-"):
        value = -value
    grouped = "," in written or len(whole) < 4
    body = ("#,##0" if grouped else "0") + (f".{'0' * len(fraction)}" if fraction else "")
    if match.group("percent"):
        value = round(value / 100, len(fraction) + 2)
        body += "%"
    tail = (match.group("unit") or "") + (match.group("mark") or "")
    suffix = f'"{tail}"' if tail else ""
    prefix = '"→ "' if match.group("prefix") else ""
    if sign == "+" or sign == "−":
        negative = f'"→ −"{body}' if prefix else f'"−"{body}'
        return value, f"{prefix}+{body}{suffix};{negative}{suffix};{prefix}{body}{suffix}"
    if sign == "-":
        return value, f"{prefix}{body}{suffix};{prefix}-{body}{suffix}"
    return value, f"{prefix}{body}{suffix}"


# ================================================================== 색


def _hex(color: str) -> str:
    """토큰 색 → `#RRGGBB`(반투명이면 흰 면 위에 섞는다)."""
    solid = _solid(color)
    if solid is None:
        raise ValueError(f"엑셀 색으로 옮길 수 없습니다: {color!r}")
    return solid


def _solid(color: str | None) -> str | None:
    """토큰 색 → 불투명 `#RRGGBB`. 반투명은 흰 면(`SURFACE`) 위에 섞고, 비거나 투명이면 None."""
    if not color:
        return None
    return tokens.opaque_over(color, tokens.SURFACE)


def _over(color: str, base: str) -> str:
    """반투명(또는 불투명) 토큰 색을 `base` 위에 얹은 불투명 색 — 엑셀 칠에는 알파가 없다."""
    return tokens.opaque_over(color, base) or base.upper()


# ================================================================== 둘째 시트


def units_sheet(frame: pd.DataFrame) -> Sheet:
    """「이 공정 단축 일정 CSV」 와 같은 표 — 머리 한 줄(고정) · 숫자 칸은 숫자 셀 · 빈 값은 빈
    칸."""
    header_style = Style(
        bold=True,
        color=_hex(tokens.TEXT),
        fill=_hex(tokens.HEADER_BACKGROUND),
        horizontal="center",
        bottom=Edge("medium", _hex(tokens.BORDER_STRONG)),
    )
    body_style = Style(color=_hex(tokens.TEXT), bottom=Edge("thin", _hex(tokens.BORDER)))
    columns = [str(column) for column in frame.columns]
    rows: list[list[XlsxCell | None]] = [[XlsxCell(name, header_style) for name in columns]]
    widths = [_text_width(name) for name in columns]
    for record in frame.itertuples(index=False, name=None):
        line: list[XlsxCell | None] = []
        for position, value in enumerate(record):
            cell_value = _plain_value(value)
            line.append(XlsxCell(cell_value, body_style))
            if cell_value is not None:
                widths[position] = max(widths[position], _text_width(str(cell_value)))
        rows.append(line)
    return Sheet(
        name=UNITS_SHEET,
        rows=rows,
        widths={
            position: min(UNITS_MAX_WIDTH, max(UNITS_MIN_WIDTH, width + 2))
            for position, width in enumerate(widths)
        },
        freeze=(1, 0),
    )


def _plain_value(value: object) -> str | int | float | None:
    """표 칸 값 → 엑셀 칸 값. pandas 빈 값(NA · NaN · NaT)은 빈 칸, 숫자는 숫자, 그 밖은 글자."""
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


def _text_width(text: str) -> float:
    """엑셀 열 너비 어림 — 넓은 글자(한글)는 둘, 그 밖은 하나."""
    return float(sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text))
