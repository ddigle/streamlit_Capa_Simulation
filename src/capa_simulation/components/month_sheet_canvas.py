# Purpose: 라벨·월 Figure 한 쌍으로 그리는 월 시트 캔버스의 일반 엔진(행·칸·글자·표적·서식)이다.

"""월 시트 캔버스 엔진.

HOME 틀 그대로 라벨 칸(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`, 260px)과 월 칸(달마다
`MONTH_COLUMN_WIDTH_PX`, 100px)이 Figure 한 쌍이고, 월 Figure 하나가 가로로 스크롤된다.
행(`Row`)마다 라벨과 달 칸(`Cell`)을 갖고, 칸 면은 `base` 로 띄운 가로막대, 숫자는
`Scatter(text)`, 칸마다 보이지 않는 표적 막대가 hover 와 클릭을 받는다. 표적의 `customdata` 는
`(YYYYMM, 행 id, 풍선 글)` 이다(`CUSTOMDATA_MONTH`·`CUSTOMDATA_ROW`·`CUSTOMDATA_HOVER`).
`go.Table`·`go.Heatmap` 은 점 선택이 없어 `on_select` 가 오지 않으므로 쓰지 않는다.

구획 제목과 그 세부 글은 **라벨 Figure** 에 쓴다 — 월 Figure 는 가로로 스크롤되므로 거기 둔 글은
잘리거나 사라진다. 세부 글은 라벨 칸 폭에 맞춰 「 · 」 마디로 줄을 나누고
(`title_detail_lines`), 그 줄 수만큼 제목 줄이 높아진다(`title_row_height`).

**쓰는 곳이 둘이다** — 공정 Capa 상세 결합 캔버스(`process_capa_canvas`)와 가용설비 현황
「Static 대비 일정」 비교 시트(`availability_sheet_canvas`). 엔진은 행·칸·글자·표적 막대·라벨
Figure 와 월 Figure 의 뼈대만 갖고, 쓰는 쪽만의 그림(③·④ 의 선과 표지, 부족 띠, 오늘 선,
지금 보는 달 열)은 월 Figure 의 훅(`month_figure` 의 `row_hook`·`header_hook`·`finish_hook`)으로
얹는다. 훅을 부르는 자리는 도형·주석·trace 의 차례를 정한다 — 공정 Capa 상세의 출력이 엔진으로
옮기기 전과 같다.

- **칸 글자색**(`Cell.text_color`)을 주면 그 색으로 쓴다. 글자 trace 는 (색, 크기)마다 하나다 — 한
  값인 글자색이어야 칸을 눌러도 흐려지지 않는다(`keep_unselected_opaque`).
- **고른 칸 테두리**(`month_figure` 의 `selected_cell`)는 그 칸 하나에 `ACCENT` 2px 를 두른다.
- **서식**(`one`·`signed_one`)은 자릿수(`digits`, 기본 1)를 받는다 — 공정 Capa 상세는 1자리, 비교
  시트는 2자리다.
- **풍선 없는 칸** — 풍선 글(`Cell.hover`, 없으면 `Row.hover`)이 빈 칸은 둘째 표적 trace 에
  모은다(`hoverinfo: "none"`, `hovertemplate` 없음). 풍선 상자는 뜨지 않고 누르면 그 칸이
  골라진다 — 한 trace 에 두면 `hovertemplate` 가 빈 글에도 16px 빈 상자를 띄우고, 점별
  `hoverinfo`(`"none"`·`"skip"`)는 `hovertemplate` 에 진다(2026-10-24 브라우저 확인). 그런 칸이
  없으면 trace 도 없다.
- **줄 이름 칸 풍선**(`Row.label_hover`) — 준 행만 라벨 Figure 에 보이지 않는 표적 막대가 서서
  그 줄 이름 칸에 풍선을 띄운다. 준 행이 없으면 라벨 Figure 에 trace 가 없다(쓰는 쪽은 그때
  `staticPlot` 그대로).

순수 함수다. 세션·캐시·DB 를 보지 않는다.
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.home_figure_common import (
    _HIDDEN_AXIS,
    _fit_to_units,
    _text_width_units,
)
from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    append_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.month_columns import month_label

__all__ = [
    "CELL_INSET_PX",
    "CUSTOMDATA_HOVER",
    "CUSTOMDATA_MONTH",
    "CUSTOMDATA_ROW",
    "DETAIL_FONT_PX",
    "EMPTY",
    "HEADER_FONT_PX",
    "HEADER_HEIGHT_PX",
    "KIND_ARROW",
    "KIND_HEADER",
    "KIND_NOTE",
    "KIND_TITLE",
    "KIND_UNIT",
    "KIND_VALUE",
    "LABEL_FONT_PX",
    "LABEL_INSET_PX",
    "MINUS",
    "NOTE_ROW_HEIGHT_PX",
    "PRODUCT_FONT_PX",
    "PRODUCT_INDENT_PX",
    "ROW_NOTE_PREFIX",
    "ROW_TITLE_PREFIX",
    "SELECTED_BORDER_PX",
    "SUB_VALUE_FONT_PX",
    "TITLE_BOTTOM_PX",
    "TITLE_DETAIL_FONT_PX",
    "TITLE_DETAIL_LINE_PX",
    "TITLE_FONT_PX",
    "TITLE_HEIGHT_PX",
    "TITLE_LINE_PX",
    "VALUE_FONT_PX",
    "VALUE_ROW_HEIGHT_PX",
    "Cell",
    "MonthLayers",
    "Points",
    "Row",
    "bold",
    "canvas_point",
    "data_hline",
    "data_rect",
    "fine_one",
    "fit",
    "label_figure",
    "month_figure",
    "note_row",
    "one",
    "percent",
    "signed_int",
    "signed_one",
    "stack_rows",
    "text_points",
    "title_detail_lines",
    "title_row",
    "title_row_height",
]

# ------------------------------------------------------------------ 치수
# 머리는 HOME 주요공정·상세 B/N 과 같은 36px 다. 값 행은 요약 표 27px(`TABLE_ROW_HEIGHT_PX`).
HEADER_HEIGHT_PX: Final = 36
# 구획 제목 줄 — 세부 글이 없으면 제목 한 줄(28px), 있으면 제목 칸(26px) 아래에 세부 글 줄(14px)을
# 쌓고 바닥 여백(4px)을 둔다.
TITLE_HEIGHT_PX: Final = 28
TITLE_LINE_PX: Final = 26
TITLE_DETAIL_LINE_PX: Final = 14
TITLE_BOTTOM_PX: Final = 4
VALUE_ROW_HEIGHT_PX: Final = tokens.TABLE_ROW_HEIGHT_PX
NOTE_ROW_HEIGHT_PX: Final = 24
# 칠한 칸은 행·열 경계에서 이만큼 들어온다 — 월 경계선이 칸 사이 틈에 남아 한 칸씩 읽힌다.
CELL_INSET_PX: Final = 3
SELECTED_BORDER_PX: Final = 2
LABEL_INSET_PX: Final = 10
PRODUCT_INDENT_PX: Final = 14
HEADER_FONT_PX: Final = 14
TITLE_FONT_PX: Final = 13
TITLE_DETAIL_FONT_PX: Final = 11
LABEL_FONT_PX: Final = 13
PRODUCT_FONT_PX: Final = 12
DETAIL_FONT_PX: Final = 11
VALUE_FONT_PX: Final = 13
SUB_VALUE_FONT_PX: Final = 11

# ------------------------------------------------------------------ 행 id·customdata
ROW_TITLE_PREFIX: Final = "title:"
ROW_NOTE_PREFIX: Final = "note:"
CUSTOMDATA_MONTH: Final = 0
CUSTOMDATA_ROW: Final = 1
CUSTOMDATA_HOVER: Final = 2

MINUS: Final = "−"
EMPTY: Final = "—"

# 행 종류. 그리는 길이 종류마다 다르다 — 머리(월 글자)·구획 제목(라벨 Figure 에만 글)·값·알림 한 줄·
# 두 줄 라벨(호기)·화살표 줄.
KIND_HEADER: Final = "header"
KIND_TITLE: Final = "title"
KIND_VALUE: Final = "value"
KIND_NOTE: Final = "note"
KIND_UNIT: Final = "unit"
KIND_ARROW: Final = "arrow"


@dataclass
class Cell:
    """달 칸 하나. `text_color` 를 주면 그 색으로, 아니면 `muted` 에 따라 본문·흐린 글자색이다."""

    text: str = ""
    sub: str = ""
    fill: str | None = None
    muted: bool = False
    bold: bool = False
    hover: str = ""
    text_color: str | None = None


@dataclass
class Row:
    row_id: str
    kind: str
    height: float
    label: str = ""
    detail: str = ""
    detail_lines: tuple[str, ...] = ()
    """구획 제목 줄의 세부 글을 라벨 칸 폭으로 나눈 줄(`title_detail_lines`)."""

    label_fill: str | None = None
    month_fill: str | None = None
    label_bold: bool = False
    label_muted: bool = False
    indent: bool = False
    label_indent: float = 0.0
    """라벨 글을 이만큼(px) 들인다 — 글자 크기는 그대로다(`indent` 는 제품 줄이라 글자도 줄인다)."""

    group_start: bool = False
    clickable: bool = True
    cells: dict[int, Cell] = field(default_factory=dict)
    hover: str = ""
    label_hover: str = ""
    """줄 이름 칸(라벨 Figure)의 풍선 글. 비면 그 칸에 풍선이 없다."""

    payload: Any = None
    top: float = 0.0


@dataclass
class MonthLayers:
    """월 Figure 에 쌓이는 것. 훅은 여기에 더한다 — 넣은 차례가 곧 그리는 차례다.

    `traces` 는 칸 면(fills) trace 뒤·글자 trace 앞에 선다.
    """

    below: list[dict[str, Any]] = field(default_factory=list)
    above: list[dict[str, Any]] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    traces: list[Any] = field(default_factory=list)


RowHook = Callable[[MonthLayers, Row, float, float], None]
"""행 하나를 다 그린 뒤 — (쌓인 것, 행, 행 가운데 y, 행 바닥 y)."""

LayerHook = Callable[[MonthLayers], None]


class Points:
    """trace 하나에 모을 점들."""

    def __init__(self) -> None:
        self.x: list[float] = []
        self.y: list[float] = []
        self.width: list[float] = []
        self.color: list[str] = []
        self.text: list[str] = []
        self.data: list[list[object]] = []

    def add(
        self,
        *,
        x: float,
        y: float,
        width: float = 0.0,
        color: str = "",
        text: str = "",
        data: list[object] | None = None,
    ) -> None:
        self.x.append(x)
        self.y.append(y)
        self.width.append(width)
        self.color.append(color)
        self.text.append(text)
        self.data.append(data or [])


# ================================================================== 행 쌓기·칸 읽기


def stack_rows(rows: Sequence[Row]) -> int:
    """행마다 위 끝(`top`)을 적고 전체 높이(px, 올림)를 돌려준다."""
    top = 0.0
    for row in rows:
        row.top = top
        top += row.height
    return int(math.ceil(top))


def canvas_point(selection_state: object) -> tuple[int, str] | None:
    """`st.plotly_chart` 선택 상태(`{"selection": {"points": [...]}}`)에서 누른 칸의 (달, 행 id).

    빈 선택(고른 점을 다시 눌러 풀거나 더블클릭)이나 표적이 아닌 점이면 None 이다 — 그 뜻은
    쓰는 쪽이 정한다(공정 Capa 상세는 보던 달 그대로, 비교 시트는 닫기).
    """
    if not isinstance(selection_state, Mapping):
        return None
    selection = selection_state.get("selection")
    if not isinstance(selection, Mapping):
        return None
    points = selection.get("points")
    if not isinstance(points, Sequence) or isinstance(points, str):
        return None
    for point in points:
        if not isinstance(point, Mapping):
            continue
        data = point.get("customdata")
        if not isinstance(data, Sequence) or isinstance(data, str) or len(data) <= CUSTOMDATA_ROW:
            continue
        month, row_id = data[CUSTOMDATA_MONTH], data[CUSTOMDATA_ROW]
        if isinstance(month, bool) or not isinstance(month, (int, float)):
            continue
        if not isinstance(row_id, str):
            continue
        return int(month), row_id
    return None


# ================================================================== 공용 행


def title_detail_lines(detail: str) -> tuple[str, ...]:
    """구획 제목 세부 글을 라벨 칸 폭(260px − 좌우 여백)에 맞춰 「 · 」 마디로 나눈 줄들.

    마디는 자르지 않고 다음 줄로 넘긴다. 한 마디가 칸보다 길 때만 그 줄을 말줄임한다. 비면 ().
    """
    if not detail:
        return ()
    budget = (DASHBOARD_LABEL_COLUMN_WIDTH_PX - 2 * LABEL_INSET_PX) / TITLE_DETAIL_FONT_PX
    lines: list[str] = []
    current = ""
    for part in detail.split(" · "):
        candidate = f"{current} · {part}" if current else part
        if current and _text_width_units(candidate) > budget:
            lines.append(fit(current, budget))
            current = part
        else:
            current = candidate
    if current:
        lines.append(fit(current, budget))
    return tuple(lines)


def title_row_height(detail: str) -> int:
    """구획 제목 줄 높이(px) — 세부 글 줄 수만큼 높아진다."""
    lines = title_detail_lines(detail)
    if not lines:
        return TITLE_HEIGHT_PX
    return TITLE_LINE_PX + len(lines) * TITLE_DETAIL_LINE_PX + TITLE_BOTTOM_PX


def title_row(
    name: str,
    title: str,
    detail: str,
    *,
    label_fill: str | None = None,
    month_fill: str | None = None,
) -> Row:
    """구획 제목 줄. 면을 주지 않으면 캔버스 바탕(`CHART_CANVAS`)이다. 누를 수 없다."""
    return Row(
        f"{ROW_TITLE_PREFIX}{name}",
        KIND_TITLE,
        title_row_height(detail),
        label=title,
        detail=detail,
        detail_lines=title_detail_lines(detail),
        label_bold=True,
        label_fill=tokens.CHART_CANVAS if label_fill is None else label_fill,
        month_fill=tokens.CHART_CANVAS if month_fill is None else month_fill,
        group_start=True,
        clickable=False,
    )


def note_row(name: str, text: str) -> Row:
    """라벨 칸에 흐린 글 한 줄만 있는 행(누를 수 없다)."""
    return Row(
        f"{ROW_NOTE_PREFIX}{name}",
        KIND_NOTE,
        NOTE_ROW_HEIGHT_PX,
        label=text,
        label_muted=True,
        label_fill=tokens.SURFACE_CLASSIFICATION,
        clickable=False,
    )


# ================================================================== 라벨 Figure


def label_figure(rows: Sequence[Row], height: int) -> go.Figure:
    """라벨 칸 Figure — 행 면·행 경계·라벨 글(제목 줄은 제목과 세부 글 줄), 그리고 `label_hover` 를
    준 행의 줄 이름 칸 풍선(보이지 않는 표적 막대 — `customdata` 는 `(행 id, 풍선 글)`)."""
    figure = go.Figure()
    figure.update_layout(
        height=height,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.SURFACE,
        showlegend=False,
        dragmode=False,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
        xaxis={**_HIDDEN_AXIS, "range": [0, 1]},
        yaxis={**_HIDDEN_AXIS, "range": [0, height]},
    )
    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        y0 = 1 - (row.top + row.height) / height
        y1 = 1 - row.top / height
        middle = (y0 + y1) / 2
        if row.label_fill is not None:
            shapes.append(_paper_rect(0, 1, y0, y1, row.label_fill))
        if position > 0:
            strong = row.group_start or rows[position - 1].kind == KIND_HEADER
            shapes.append(_paper_rule(y1, strong=strong))
        budget = DASHBOARD_LABEL_COLUMN_WIDTH_PX - 2 * LABEL_INSET_PX
        if row.kind == KIND_TITLE:
            annotations += _title_annotations(row, budget, height)
            continue
        indent = PRODUCT_INDENT_PX if row.indent else row.label_indent
        font = PRODUCT_FONT_PX if row.indent else LABEL_FONT_PX
        two_lines = bool(row.detail) and row.kind == KIND_UNIT
        annotations.append(
            _label_annotation(
                fit(row.label, (budget - indent) / font),
                y=middle,
                shift=7 if two_lines else 0,
                indent=indent,
                size=font,
                bold=row.label_bold,
                muted=row.label_muted,
            )
        )
        if two_lines:
            annotations.append(
                _label_annotation(
                    fit(row.detail, budget / DETAIL_FONT_PX),
                    y=middle,
                    shift=-8,
                    indent=0,
                    size=DETAIL_FONT_PX,
                    bold=False,
                    muted=True,
                )
            )
    hovered = [row for row in rows if row.label_hover]
    if hovered:
        # 막대는 오른쪽 끝(1)에서 왼쪽 끝(0)으로 긋는다 — Plotly 는 풍선을 막대 끝에 붙이므로 풍선이
        # 라벨 칸 왼쪽에서 오른쪽으로 펴지고, 칸보다 넓으면 월 컬럼 쪽으로 넘친다(왼쪽으로 넘치면
        # 사이드바 경계에서 잘린다 — 2026-10-24 브라우저).
        figure.add_trace(
            go.Bar(
                x=[-1.0] * len(hovered),
                y=[height - row.top - row.height / 2 for row in hovered],
                base=[1.0] * len(hovered),
                width=[row.height for row in hovered],
                orientation="h",
                marker={"color": tokens.HIT_TARGET, "line": {"width": 0}},
                customdata=[[row.row_id, row.label_hover] for row in hovered],
                hovertemplate="%{customdata[1]}<extra></extra>",
                showlegend=False,
            )
        )
        # 라벨 칸은 좁아 Plotly 가 풍선을 가운데 맞춤으로 당긴다 — 여러 줄 글은 왼쪽 맞춤으로
        # 읽힌다.
        figure.update_layout(
            barmode="overlay",
            bargap=0,
            hovermode="closest",
            hoverlabel={**_hover_label(), "align": "left"},
        )
    append_layout_items(figure, shapes=shapes, annotations=annotations)
    add_figure_outer_border(figure, emphasize_bottom=True)
    return figure


def _hover_label() -> dict[str, Any]:
    """두 Figure 풍선의 서식. 토큰은 부를 때 읽는다(테마가 회차마다 다르다)."""
    return {
        "bgcolor": tokens.SURFACE,
        "bordercolor": tokens.BORDER_STRONG,
        "font": {"color": tokens.TEXT, "size": 12, "family": tokens.FONT_FAMILY},
    }


def _title_annotations(row: Row, budget: float, height: int) -> list[dict[str, Any]]:
    """구획 제목(굵게) 한 줄과 그 아래 세부 글 줄들(회색). 라벨 칸은 스크롤되지 않아 늘 보인다."""

    def paper_y(offset: float) -> float:
        return 1 - (row.top + offset) / height

    title_center = (TITLE_LINE_PX if row.detail_lines else TITLE_HEIGHT_PX) / 2
    annotations = [
        _label_annotation(
            fit(row.label, budget / TITLE_FONT_PX),
            y=paper_y(title_center),
            shift=0,
            indent=0,
            size=TITLE_FONT_PX,
            bold=True,
            muted=False,
        )
    ]
    for position, line in enumerate(row.detail_lines):
        annotations.append(
            _label_annotation(
                line,
                y=paper_y(TITLE_LINE_PX + (position + 0.5) * TITLE_DETAIL_LINE_PX),
                shift=0,
                indent=0,
                size=TITLE_DETAIL_FONT_PX,
                bold=False,
                muted=True,
            )
        )
    return annotations


def _label_annotation(
    text: str,
    *,
    y: float,
    shift: float,
    indent: float,
    size: int,
    bold: bool,
    muted: bool,
) -> dict[str, Any]:
    escaped = html.escape(text)
    return {
        "x": 0,
        "y": y,
        "xref": "paper",
        "yref": "paper",
        "xanchor": "left",
        "yanchor": "middle",
        "xshift": LABEL_INSET_PX + indent,
        "yshift": shift,
        "text": f"<b>{escaped}</b>" if bold else escaped,
        "showarrow": False,
        "font": {
            "color": tokens.TEXT_MUTED if muted else tokens.TEXT,
            "size": size,
            "family": tokens.FONT_FAMILY,
        },
    }


def _paper_rect(x0: float, x1: float, y0: float, y1: float, color: str) -> dict[str, Any]:
    return {
        "type": "rect",
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1,
        "xref": "paper",
        "yref": "paper",
        "fillcolor": color,
        "line": {"width": 0},
        "layer": "below",
    }


def _paper_rule(y: float, *, strong: bool) -> dict[str, Any]:
    return {
        "type": "line",
        "x0": 0,
        "x1": 1,
        "y0": y,
        "y1": y,
        "xref": "paper",
        "yref": "paper",
        "line": {
            "color": tokens.BORDER_STRONG if strong else tokens.BORDER,
            "width": 1.5 if strong else tokens.GRID_LINE_WIDTH_PX,
        },
        "layer": "above",
    }


# ================================================================== 월 Figure


def month_figure(
    rows: Sequence[Row],
    axis: Sequence[int],
    height: int,
    *,
    row_hook: RowHook | None = None,
    header_hook: LayerHook | None = None,
    finish_hook: LayerHook | None = None,
    selected_cell: tuple[int, str] | None = None,
    meta: object = None,
) -> go.Figure:
    """월 칸 Figure. `rows[0]` 은 머리 행(달 글자)이다.

    차례: 행마다(월 면 → 묶음 경계 → 칸 표적·면·글자 → `row_hook`) → 머리 달 글자 → `header_hook` →
    월 경계 세로선 → `finish_hook` → 고른 칸 테두리(`selected_cell` = (열 위치, 행 id)). trace 는
    표적 막대 · (풍선 없는 칸의 표적 막대 — 그런 칸이 있을 때만) · 칸 면 막대 · 훅이 더한 trace ·
    글자((색, 크기)마다 하나) 차례다. `meta` 는 그림의 `layout.meta` 로 싣는다(그리는 것은 바꾸지
    않는다).
    """
    count = len(axis)
    inset = CELL_INSET_PX / tokens.MONTH_COLUMN_WIDTH_PX
    header = rows[0]

    targets = Points()
    silent = Points()
    fills = Points()
    texts: dict[tuple[str, int], Points] = {}
    layers = MonthLayers()

    for position, row in enumerate(rows):
        bottom = height - row.top - row.height
        center = bottom + row.height / 2
        if row.month_fill is not None and row.month_fill != tokens.SURFACE:
            layers.below.append(data_rect(0, count, bottom, bottom + row.height, row.month_fill))
        if position > 0 and (row.group_start or rows[position - 1].kind == KIND_HEADER):
            strong_top = bottom + row.height
            layers.above.append(data_hline(strong_top, count))
        if row.kind == KIND_TITLE:
            # 제목·세부 글은 라벨 Figure 에 있다 — 여기는 면만 깐다(스크롤로 잘리지 않게).
            continue
        for index in range(count):
            cell = row.cells.get(index)
            if cell is None:
                continue
            if row.clickable:
                hover = cell.hover or row.hover
                (targets if hover else silent).add(
                    x=index,
                    y=center,
                    width=row.height,
                    data=[int(axis[index]), row.row_id, hover],
                )
            if cell.fill is not None:
                fills.add(
                    x=index + inset,
                    y=center,
                    width=row.height - 2 * CELL_INSET_PX,
                    color=cell.fill,
                )
            if row.kind == KIND_HEADER:
                continue
            size = PRODUCT_FONT_PX if row.indent else VALUE_FONT_PX
            if cell.sub:
                text_points(texts, cell, size).add(
                    x=index + 0.5, y=center + 6, text=bold(cell.text, cell.bold)
                )
                text_points(texts, cell, SUB_VALUE_FONT_PX).add(
                    x=index + 0.5, y=center - 8, text=bold(cell.sub, cell.bold)
                )
            elif cell.text:
                text_points(texts, cell, size).add(
                    x=index + 0.5, y=center, text=bold(cell.text, cell.bold)
                )
        if row_hook is not None:
            row_hook(layers, row, center, bottom)

    header_center = height - header.height / 2
    for index, month in enumerate(axis):
        layers.annotations.append(
            {
                "x": index + 0.5,
                "y": header_center,
                "xref": "x",
                "yref": "y",
                "text": f"<b>{html.escape(month_label(month))}</b>",
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {
                    "color": tokens.TEXT,
                    "size": HEADER_FONT_PX,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
    if header_hook is not None:
        header_hook(layers)
    # 월 경계 세로선(첫 달 앞은 테두리가 맡는다). 칠한 칸이 경계에서 들어와 선이 그 틈에 남는다.
    layers.below += [
        {
            "type": "line",
            "x0": index,
            "x1": index,
            "y0": 0,
            "y1": height,
            "xref": "x",
            "yref": "y",
            "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
            "layer": "below",
        }
        for index in range(1, count)
    ]
    if finish_hook is not None:
        finish_hook(layers)
    if selected_cell is not None:
        layers.above += _cell_border(rows, height, selected_cell, count)

    traces: list[Any] = [
        go.Bar(
            x=[1.0] * len(targets.x),
            y=targets.y,
            base=targets.x,
            width=targets.width,
            orientation="h",
            marker={"color": tokens.HIT_TARGET, "line": {"width": 0}},
            customdata=targets.data,
            hovertemplate="%{customdata[2]}<extra></extra>",
            showlegend=False,
        ),
        *_silent_targets(silent),
        go.Bar(
            x=[1.0 - 2 * inset] * len(fills.x),
            y=fills.y,
            base=fills.x,
            width=fills.width,
            orientation="h",
            marker={"color": fills.color, "line": {"width": 0}},
            hoverinfo="skip",
            showlegend=False,
        ),
        *layers.traces,
    ]
    for (color, size), points in sorted(texts.items()):
        traces.append(
            go.Scatter(
                x=points.x,
                y=points.y,
                mode="text",
                text=points.text,
                textposition="middle center",
                textfont={"color": color, "size": size, "family": tokens.FONT_FAMILY_NUMERIC},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    figure = go.Figure(traces)
    figure.update_layout(
        height=height,
        width=count * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.SURFACE,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
        barmode="overlay",
        bargap=0,
        showlegend=False,
        dragmode=False,
        hovermode="closest",
        hoverlabel=_hover_label(),
        xaxis={**_HIDDEN_AXIS, "range": [0, count]},
        yaxis={**_HIDDEN_AXIS, "range": [0, height]},
    )
    if meta is not None:
        figure.update_layout(meta=meta)
    append_layout_items(figure, shapes=layers.below + layers.above, annotations=layers.annotations)
    add_figure_outer_border(figure, emphasize_left=False, emphasize_bottom=True)
    return figure


def _silent_targets(points: Points) -> list[Any]:
    """풍선 글이 빈 칸의 표적 막대 — `hoverinfo: "none"` 이라 풍선 상자가 뜨지 않고 hover·누름
    사건은 그대로라 누르면 그 칸이 골라진다. 그런 칸이 없으면 trace 를 두지 않는다."""
    if not points.x:
        return []
    return [
        go.Bar(
            x=[1.0] * len(points.x),
            y=points.y,
            base=points.x,
            width=points.width,
            orientation="h",
            marker={"color": tokens.HIT_TARGET, "line": {"width": 0}},
            customdata=points.data,
            hoverinfo="none",
            showlegend=False,
        )
    ]


def _cell_border(
    rows: Sequence[Row], height: int, selected: tuple[int, str], count: int
) -> list[dict[str, Any]]:
    """고른 칸 하나의 `ACCENT` 테두리. 열이 축 밖이거나 그 행이 없으면 그리지 않는다."""
    index, row_id = selected
    if not 0 <= index < count:
        return []
    row = next((item for item in rows if item.row_id == row_id), None)
    if row is None:
        return []
    edge = 1 / tokens.MONTH_COLUMN_WIDTH_PX
    bottom = height - row.top - row.height
    return [
        {
            "type": "rect",
            "x0": index + edge,
            "x1": index + 1 - edge,
            "y0": bottom + 1,
            "y1": bottom + row.height - 1,
            "xref": "x",
            "yref": "y",
            "fillcolor": tokens.TRANSPARENT,
            "line": {"color": tokens.ACCENT, "width": SELECTED_BORDER_PX},
            "layer": "above",
        }
    ]


def data_rect(
    x0: float, x1: float, y0: float, y1: float, color: str, *, layer: str = "below"
) -> dict[str, Any]:
    return {
        "type": "rect",
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1,
        "xref": "x",
        "yref": "y",
        "fillcolor": color,
        "line": {"width": 0},
        "layer": layer,
    }


def data_hline(y: float, count: int) -> dict[str, Any]:
    """묶음 경계 — 1.5px `BORDER_STRONG`. 행 경계는 라벨 칸에만 긋는다."""
    return {
        "type": "line",
        "x0": 0,
        "x1": count,
        "y0": y,
        "y1": y,
        "xref": "x",
        "yref": "y",
        "line": {"color": tokens.BORDER_STRONG, "width": 1.5},
        "layer": "above",
    }


def text_points(texts: dict[tuple[str, int], Points], cell: Cell, size: int) -> Points:
    """글자색마다 trace 하나 — 글자색이 한 값이어야 칸을 눌러도 흐려지지 않는다
    (`keep_unselected_opaque` 는 한 값인 글자색만 못박는다)."""
    color = cell.text_color or (tokens.TEXT_MUTED if cell.muted else tokens.TEXT)
    return texts.setdefault((color, size), Points())


# ================================================================== 서식


def one(value: float | None, digits: int = 1) -> str:
    """천 단위 쉼표와 소수 `digits` 자리. 값이 없으면 「—」."""
    return EMPTY if value is None else f"{value:,.{digits}f}"


def percent(value: float | None) -> str:
    return EMPTY if value is None else f"{value:.0%}"


def signed_int(value: int) -> str:
    """부호 있는 정수 — 여유 「+n」, 부족 「−n」, 0 은 「0」."""
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{MINUS}{abs(value):,}"
    return "0"


def signed_one(value: float | None, digits: int = 1) -> str:
    """부호 있는 값 — 소수 `digits` 자리. 그 자리로 0 이 되는 0 아닌 값은 한 자리 더 적는다 —
    목표에 0.04 대 모자란 칸을 칠해 두고 「0.0」 으로 적으면 왜 칠했는지 읽히지 않는다. 0 은
    「0.0」(자릿수만큼)."""
    if value is None:
        return EMPTY
    rounded, shown = _fine_round(value, digits)
    if rounded > 0:
        return f"+{rounded:,.{shown}f}"
    if rounded < 0:
        return f"{MINUS}{abs(rounded):,.{shown}f}"
    return f"{0:.{digits}f}"


def fine_one(value: float | None, digits: int = 1) -> str:
    """부호 없는 값 — `one` 꼴에 `signed_one` 의 자릿수 규칙(그 자리로 0 이 되는 0 아닌 값은 한
    자리 더)을 쓴다. 0 은 「0.0」(자릿수만큼)."""
    if value is None:
        return EMPTY
    rounded, shown = _fine_round(value, digits)
    return f"{rounded:,.{shown}f}" if rounded != 0 else f"{0:.{digits}f}"


def _fine_round(value: float, digits: int) -> tuple[float, int]:
    """(반올림한 값, 적을 자릿수) — `digits` 자리로 0 이 되는 0 아닌 값은 한 자리 더 본다."""
    value = round(value, 9)
    shown = digits if value == 0 or abs(round(value, digits)) > 0 else digits + 1
    return round(value, shown), shown


def bold(text: str, strong: bool) -> str:
    escaped = html.escape(text)
    return f"<b>{escaped}</b>" if strong else escaped


def fit(text: str, budget_units: float) -> str:
    return _fit_to_units(text, budget_units, _text_width_units)
