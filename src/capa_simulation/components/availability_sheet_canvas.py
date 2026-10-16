# Purpose: 비교 시트 9행(Static·설비 일정 기준·GAP)을 월 시트 엔진의 Figure 한 쌍으로 그린다.

"""「Static 대비 일정」 비교 시트 — 월 캔버스.

`SheetView`(9행 × 달, 「—」 칸은 까닭)를 공정 Capa 상세 결합 캔버스와 같은 꼴로 그린다
(`month_sheet_canvas` 엔진 — 라벨 260px · 달 100px · 행 27px · 머리 36px). 줄은 머리 하나 + 구획
제목 셋(Static · 기준정보 / 설비 일정 기준 / GAP (설비 일정 − Static)) + 값 아홉 = 13줄이다.

- Static 묶음은 공정 Capa 상세 ① 공급 묶음과 같은 면(`SUMMARY_SUPPLY_*`)이다 — 같은 원천이다.
- 설비 일정 기준·GAP 은 라벨 칸만 분류 면이다. GAP 은 면을 칠하지 않고 글자색만 쓴다 — + 는
  `DELTA_INCREASE`, − 는 `DELTA_DECREASE`, 0 은 흐린 글자(「모자람」이 아니라 「어긋남」이라 판정
  3색을 쓰지 않는다).
- 값은 소수 2자리(보유·가용), 대여·GAP 은 부호를 붙인다(마이너스는 U+2212). 2자리로 0 이 되는 0 아닌
  값은 3자리다. 풍선은 3자리와 식이다.
- 「—」 칸은 흐린 글자에 풍선으로 까닭을 적는다. 머리 칸은 누를 수 없다.
- 고른 칸(`selected`)은 `ACCENT` 2px 테두리다(지금 보는 달의 열 테두리는 없다).

표적의 `customdata` 는 엔진 그대로 `(YYYYMM, 행 id, 풍선)` 이다. 그림의 `layout.meta` 에 칸 누름
세대 (`generation`)를 싣는다 — 칸을 누를 때마다 그림 내용이 달라져 브라우저가 새 그림으로
받는다(남은 선택 상태가 다음 누름을 삼키지 않게, `availability_gap_panel` 의 칸 누름).

순수 함수다. 세션·캐시·DB 를 보지 않는다.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Final, NamedTuple

import plotly.graph_objects as go

from capa_simulation.components.home_figure_common import keep_unselected_opaque
from capa_simulation.components.month_sheet_canvas import (
    EMPTY,
    HEADER_HEIGHT_PX,
    KIND_HEADER,
    KIND_VALUE,
    VALUE_ROW_HEIGHT_PX,
    Cell,
    Row,
    label_figure,
    month_figure,
    one,
    signed_one,
    stack_rows,
    title_row,
)
from capa_simulation.components.plotly_layout import flush_layout_items
from capa_simulation.design import tokens
from capa_simulation.services.availability_sheet import (
    GAP_PAIRS,
    GAP_ROWS,
    REASON_NO_DYNAMIC_MONTH,
    REASON_NO_DYNAMIC_PROCESS,
    REASON_NO_STATIC_MONTH,
    REASON_NO_STATIC_PROCESS,
    REASON_STATIC_UNREADABLE,
    REASON_UNIT_FILTER,
    ROW_ITEMS,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_LENT,
    ROW_STATIC_OWNED,
    SCHEDULE_ROWS,
    STATIC_ROWS,
    SheetView,
)
from capa_simulation.services.month_columns import month_label

__all__ = [
    "GROUP_TITLES",
    "REASON_TEXTS",
    "ROW_HEADER",
    "SHEET_DIGITS",
    "STATIC_TITLE_DETAIL",
    "AvailabilitySheetCanvas",
    "build_availability_sheet_canvas",
    "gap_text_color",
    "reason_text",
    "sheet_value_text",
]

ROW_HEADER: Final = "header"
# 칸 글자 자릿수(보유·가용). 공정 Capa 상세는 1자리 — 같은 값이 두 화면에서 자릿수만 다르다.
SHEET_DIGITS: Final = 2
HOVER_DIGITS: Final = 3
STATIC_TITLE_DETAIL: Final = "저장 리비전 · RQ_EQP_OWN·LENT·AVBL · 대수"
GAP_TITLE_DETAIL: Final = "음수 = 기준정보가 많음"
GROUP_TITLES: Final[Mapping[str, str]] = {
    "static": "Static · 기준정보",
    "sched": "설비 일정 기준",
    "gap": "GAP (설비 일정 − Static)",
}
REASON_TEXTS: Final[Mapping[str, str]] = {
    REASON_NO_STATIC_PROCESS: "기준정보(Static)에 없는 공정이라 맞대지 않습니다",
    REASON_NO_DYNAMIC_PROCESS: (
        "설비 일정 기준이 나오지 않는 공정이라(Cut-off·설비 없음) 맞대지 않습니다"
    ),
    REASON_NO_STATIC_MONTH: "이 달은 기준정보(Static) 자료가 없습니다",
    REASON_NO_DYNAMIC_MONTH: "이 달은 설비 일정 자료가 없습니다",
    REASON_UNIT_FILTER: "호기 필터 중에는 공정 단위 기준정보(Static)와 맞대지 않습니다",
    REASON_STATIC_UNREADABLE: "Static 을 읽지 못해 맞대지 않습니다",
}
_SIGNED_ROWS: Final = frozenset({ROW_STATIC_LENT, ROW_SCHEDULE_LENT, *GAP_ROWS})


class AvailabilitySheetCanvas(NamedTuple):
    """시트 캔버스 한 쌍. 두 Figure 는 높이가 같고 행이 맞는다."""

    labels: go.Figure
    months: go.Figure
    height: int
    row_ids: tuple[str, ...]
    """위에서 아래로 그린 행 id."""


def reason_text(reason: str | None) -> str:
    """「—」 칸 까닭 한 문장. 모르는 까닭은 빈 글자다."""
    return REASON_TEXTS.get(reason or "", "")


def sheet_value_text(row: str, value: float | None, digits: int = SHEET_DIGITS) -> str:
    """칸 글자 — 보유·가용은 그대로, 대여·GAP 은 부호를 붙인다. 「—」 면 None."""
    if value is None:
        return EMPTY
    return signed_one(value, digits) if row in _SIGNED_ROWS else one(value, digits)


def gap_text_color(value: float | None) -> str:
    """GAP 글자색 — 증감 방향만 본다. 반올림해 0 이면 흐린 글자다."""
    if value is None or round(value, 9) == 0:
        return tokens.TEXT_MUTED
    return tokens.DELTA_INCREASE if value > 0 else tokens.DELTA_DECREASE


def build_availability_sheet_canvas(
    *,
    view: SheetView,
    process_label: str,
    schedule_detail: str,
    selected: tuple[int, str] | None = None,
    generation: int = 0,
    scope: str = "",
) -> AvailabilitySheetCanvas:
    """9행 시트의 라벨 Figure · 월 Figure.

    - `process_label` 은 머리 글자(공정 표시명 또는 「전체 합계」)다.
    - `schedule_detail` 은 설비 일정 기준 제목의 세부 글(설비 DB · 환산대수 · 생산월 …)이다.
    - `selected` 는 고른 칸 (YYYYMM, 행 id)이다. 축에 없으면 테두리를 그리지 않는다.
    - `generation` 은 칸 누름 세대, `scope` 는 범위 지문 — 둘 다 그림의 `layout.meta` 에
      싣는다(그리는 것은 바꾸지 않는다).
    """
    axis = [int(month) for month in view.months]
    if not axis:
        raise ValueError("비교 시트의 월 축이 비었습니다.")
    rows: list[Row] = [_header_row(process_label)]
    rows.append(
        title_row(
            "static",
            GROUP_TITLES["static"],
            STATIC_TITLE_DETAIL,
            label_fill=tokens.SUMMARY_SUPPLY_CLASSIFICATION,
            month_fill=tokens.SUMMARY_SUPPLY_SURFACE,
        )
    )
    rows += [_value_row(view, axis, row, supply=True) for row in STATIC_ROWS]
    rows.append(title_row("sched", GROUP_TITLES["sched"], schedule_detail))
    rows += [_value_row(view, axis, row, supply=False) for row in SCHEDULE_ROWS]
    rows.append(title_row("gap", GROUP_TITLES["gap"], GAP_TITLE_DETAIL))
    rows += [_value_row(view, axis, row, supply=False) for row in GAP_ROWS]

    height = stack_rows(rows)
    position = {month: index for index, month in enumerate(axis)}
    cell = (
        (position[selected[0]], selected[1])
        if selected is not None and selected[0] in position
        else None
    )
    labels = label_figure(rows, height)
    months = month_figure(
        rows,
        axis,
        height,
        selected_cell=cell,
        meta={"generation": generation, "scope": scope},
    )
    flush_layout_items(labels, months)
    keep_unselected_opaque(months)
    return AvailabilitySheetCanvas(
        labels=labels,
        months=months,
        height=height,
        row_ids=tuple(row.row_id for row in rows),
    )


def _header_row(process_label: str) -> Row:
    return Row(
        ROW_HEADER,
        KIND_HEADER,
        HEADER_HEIGHT_PX,
        label=f"구분 · {process_label}",
        label_bold=True,
        label_fill=tokens.HEADER_BACKGROUND,
        month_fill=tokens.HEADER_BACKGROUND,
        clickable=False,
    )


def _value_row(view: SheetView, axis: list[int], row_id: str, *, supply: bool) -> Row:
    row = Row(
        row_id,
        KIND_VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=ROW_ITEMS[row_id],
        label_fill=tokens.SUMMARY_SUPPLY_CLASSIFICATION
        if supply
        else tokens.SURFACE_CLASSIFICATION,
        month_fill=tokens.SUMMARY_SUPPLY_SURFACE if supply else None,
    )
    for index, month in enumerate(axis):
        row.cells[index] = _cell(view, row_id, month)
    return row


def _cell(view: SheetView, row: str, month: int) -> Cell:
    head = f"<b>{html.escape(month_label(month))}</b>"
    value = view.value(row, month)
    if value is None:
        reason = reason_text(view.reason(row, month))
        return Cell(
            text=EMPTY,
            muted=True,
            hover=f"{head} · {EMPTY}" + (f" · {html.escape(reason)}" if reason else ""),
        )
    mismatch = row == ROW_STATIC_AVAILABLE and month in view.mismatch
    text = sheet_value_text(row, value) + (" ⚠" if mismatch else "")
    color = gap_text_color(value) if row in GAP_ROWS else None
    return Cell(text=text, text_color=color, hover=_hover(view, row, month, head))


def _three(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return EMPTY
    return signed_one(value, HOVER_DIGITS) if signed else one(value, HOVER_DIGITS)


def _hover(view: SheetView, row: str, month: int, head: str) -> str:
    value = view.value(row, month)
    if row == ROW_STATIC_OWNED:
        return f"{head} · Static 보유 {_three(value)}대 · RQ_EQP_OWN 설비보유"
    if row == ROW_STATIC_LENT:
        return (
            f"{head} · Static 대여 {_three(value, signed=True)}대 · RQ_EQP_LENT 설비대여평가"
            "<br>DB 의 양수 값에 − 를 붙여 보입니다"
        )
    if row == ROW_STATIC_AVAILABLE:
        text = (
            f"{head} · Static 가용 {_three(value)}대 · RQ_EQP_AVBL 가용대수"
            f"<br>보유 {_three(view.value(ROW_STATIC_OWNED, month))} + 대여 "
            f"{_three(view.value(ROW_STATIC_LENT, month), signed=True)}"
        )
        if month in view.mismatch:
            text += "<br>⚠ 가용대수가 보유 + 대여와 다릅니다(기준정보 표를 따로 고쳤습니다)"
        return text
    if row == ROW_SCHEDULE_OWNED:
        baseline = view.baseline.get(month)
        base = float(baseline) if baseline is not None and baseline == baseline else 0.0
        units = (value or 0.0) - base
        return (
            f"{head} · 설비 일정 기준 보유 {_three(value)} (환산대수)"
            f"<br>= 기존보유 {_three(base)} + 비가동이 없었다면 가용인 호기 {_three(units)}"
            "<br>누르면 호기"
        )
    if row == ROW_SCHEDULE_LENT:
        return (
            f"{head} · 대여(비가동) {_three(value, signed=True)} (환산대수)"
            "<br>비가동이 실제로 깎은 가용 — 셋업 중·보관 호기의 비가동은 들지 않습니다"
            "<br>누르면 호기"
        )
    if row == ROW_SCHEDULE_AVAILABLE:
        return (
            f"{head} · 설비 일정 기준 가용 {_three(value)} = 보유 "
            f"{_three(view.value(ROW_SCHEDULE_OWNED, month))} + 대여(비가동) "
            f"{_three(view.value(ROW_SCHEDULE_LENT, month), signed=True)}"
            "<br>교차검증·필요단축일정·공정 Capa 상세 ② 와 같은 값 · 누르면 호기"
        )
    schedule, static = GAP_PAIRS[row]
    signed = schedule == ROW_SCHEDULE_LENT
    return (
        f"{head} · GAP {ROW_ITEMS[row]} {_three(value, signed=True)} = 설비 일정 "
        f"{_three(view.value(schedule, month), signed=signed)} − Static "
        f"{_three(view.value(static, month), signed=signed)}"
        "<br>음수 = 기준정보가 많음 · 누르면 짝 호기"
    )
