# Purpose: HOME 요약 구획의 생산계획 LOB·Wafer·B/N Top5·제품별 비중 Figure 한 쌍을 만든다.

"""생산계획 LOB 요약 Figure.

고정 분류 영역과 스크롤 월 영역 두 Figure 를 한 쌍으로 돌려준다. 표 세 줄(Density·Wafer
계획·Wafer Capa)과 LOB 꺾은선·B/N 막대·Top5 밴드, 맨 아래 `제품별 비중` 도넛 행이 한 Figure
안에 세로로 선다.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from typing import Any, NamedTuple, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    LOB_BAR_OUTLINE_WIDTH_PX,
    LOB_BAR_WIDTH,
    LOB_BARGAP,
    LOB_BOTTOM_MARGIN_PX,
    LOB_CHART_HEIGHT_PX,
    LOB_FIGURE_HEIGHT_PX,
    LOB_PANEL_BOTTOM_Y,
    LOB_PLOT_AREA_HEIGHT_PX,
    LOB_PRODUCT_SHARE_GAP_PX,
    LOB_PRODUCT_SHARE_HOLE,
    LOB_PRODUCT_SHARE_INSET_PX,
    LOB_PRODUCT_SHARE_MIN_DRAWN_SHARE,
    LOB_PRODUCT_SHARE_ROW_HEIGHT_PX,
    LOB_PRODUCT_SHARE_TOP_Y,
    LOB_TABLE_HEIGHT_PX,
    LOB_TABLE_ROW_HEIGHTS_PX,
    LOB_TOP5_HEIGHT_PX,
    LOB_TOP5_LABEL_ZONE_PX,
    LOB_TOP_MARGIN_PX,
    LOB_VALUE_FONT_SIZE_PX,
    TOP5_BAR_OUTLINE_WIDTH_PX,
    TOP5_BAR_WIDTH,
    TOP5_PROCESS_LABEL_FONT_SIZE_PX,
    TOP5_PROCESS_LABEL_YSHIFT_PX,
    TOP5_RATE_LABEL_GAP_PX,
    TOP5_WAFER_LABEL_XSHIFT_PX,
    top5_axis_headroom_px,
    top5_process_label_room_px,
)
from capa_simulation.components.home_figure_common import (
    _calibri_width_units,
    _capacity_color,
    _column_surface_rects,
    _execution_delta_note,
    _fit_to_units,
    _month_surface,
    _paper_hrule,
    _paper_month_lines,
    _text_width_units,
)
from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    add_fixed_table_row,
    add_quarter_boundaries,
    append_layout_items,
    delta_color,
    fixed_row_domains,
    flush_layout_items,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import tokens
from capa_simulation.services.product_share import (
    PRODUCT_SHARE_BASIS_WAFER,
    ProductShareCell,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.top5_band import (
    DEFAULT_TOP5_MAX_RATE,
    DEFAULT_TOP5_MIN_RATE,
    clamp_rate,
)

# 생산계획 LOB 막대 안 확보율 글자.
LOB_BAR_LABEL_FONT_SIZE_PX = 22


# `제품별 비중` 구분 칸. 제목 한 줄 아래에 두 칸짜리 범례가 선다. 조각은 `기타` 를 넣어 여섯
# 까지지만, 계산 구간 제품이 여섯이고 과거 구간에만 있는 제품이 `기타` 로 접히면 일곱이 되므로
# 네 줄까지 받는다.
PRODUCT_SHARE_TITLE_FONT_SIZE_PX = 20
PRODUCT_SHARE_UNIT_FONT_SIZE_PX = 14
PRODUCT_SHARE_LEGEND_FONT_SIZE_PX = 13
_PRODUCT_SHARE_TITLE_LINE_PX = 24
_PRODUCT_SHARE_LEGEND_GAP_PX = 6
# 줄 간격. 세 줄까지는 18px, 네 줄이면 16px 로 좁혀 100px 칸 안에 넣는다.
_PRODUCT_SHARE_LEGEND_ROW_PX = 18
_PRODUCT_SHARE_LEGEND_TIGHT_ROW_PX = 16
_PRODUCT_SHARE_LEGEND_COLUMNS = 2
_PRODUCT_SHARE_LEGEND_MAX_ROWS = 4
# 범례 두 칸의 왼쪽 끝(구분 칸 폭 비율). 260px 칸에서 16px·138px 이고 두 칸 폭이 같다.
_PRODUCT_SHARE_LEGEND_X = (0.06, 0.53)
# 한 칸 오른쪽 끝에 남기는 틈. 왼쪽 칸 이름은 오른쪽 칸의 색 네모와, 오른쪽 칸 이름은 구분 칸
# 테두리와 이만큼 떨어진다.
_PRODUCT_SHARE_LEGEND_GUTTER_PX = 6
_PRODUCT_SHARE_LEGEND_SWATCH = "■ "
# hover 글자 크기와 줄 수. 도넛이 그림 맨 아래에 붙어 있어(아래 여백 0) 6시 방향 조각의 hover
# 는 기준점 아래로 18px 남짓밖에 자리가 없다 — Plotly 는 pie hover 를 그림 안으로 밀어 넣지
# 않고 잘라 버린다. **두 줄**과 이 크기면 그 안에 든다. 줄을 늘리지 않는다.
_PRODUCT_SHARE_HOVER_FONT_SIZE_PX = 12
# `기타` hover 에 이름을 적는 제품 수. 나머지는 「외 N」으로 줄인다(둘째 줄에 함께 적는다).
_PRODUCT_SHARE_HOVER_MEMBERS = 3
# 단위별 hover 수량 표기. Wafer 는 매 → K, PKG 생산수량은 이미 K(Kea) 단위다.
_PRODUCT_SHARE_SCALE = {PRODUCT_SHARE_BASIS_WAFER: 1_000.0}


def _product_color(slot: int | None) -> str:
    """조각 색. 칸 번호가 없으면 `기타` 회색이다."""
    if slot is None:
        return tokens.PRODUCT_SHARE_OTHER
    return str(tokens.PRODUCT_SHARE_COLORS[slot])


def _legend_name_budget_units() -> float:
    """범례 이름 한 칸의 폭 예산(글자 크기 1px 기준). 색 네모와 틈을 뺀 자리다.

    `_text_width_units`(반각 0.6·전각 1.0)가 이 범례 서체(Noto Sans KR 13px)의 대문자·숫자
    실측(0.56~0.62em)과 맞는다. 글자 수로 어림하면 대문자·숫자 이름이 옆 칸의 색 네모를 덮거나
    구분 칸 테두리 밖에서 잘린다(말줄임표까지 잘려 줄였다는 표시도 사라진다).
    """
    column_px = (
        _PRODUCT_SHARE_LEGEND_X[1] - _PRODUCT_SHARE_LEGEND_X[0]
    ) * DASHBOARD_LABEL_COLUMN_WIDTH_PX
    text_px = column_px - _PRODUCT_SHARE_LEGEND_GUTTER_PX
    return text_px / PRODUCT_SHARE_LEGEND_FONT_SIZE_PX - _text_width_units(
        _PRODUCT_SHARE_LEGEND_SWATCH
    )


def _share_amount(value: float, basis: str) -> str:
    return f"{value / _PRODUCT_SHARE_SCALE.get(basis, 1.0):,.1f}K"


def _product_share_hover(cell: ProductShareCell, basis: str) -> list[str]:
    """조각마다 hover 두 줄. 둘째 줄에 분모(그 칸 합계)를 적어 `Wafer 계획` 행과 맞대어 본다.

    `기타` 는 무엇이 모였는지 둘째 줄에 잇는다 — 접었다고 정보를 지우지 않는다. 과거 구간 칸은
    그 수량이 `과거 계획 세부수량` 입력값이라는 것을 적는다(계산 구간과 정의가 다를 수 있다).
    """
    source = " · 과거 입력값" if cell.past else ""
    texts: list[str] = []
    for piece in cell.slices:
        amounts = (
            f"{basis} {_share_amount(piece.value, basis)} / "
            f"{_share_amount(cell.total, basis)}{source}"
        )
        if piece.members:
            listed = ", ".join(
                f"{name} {value / cell.total:.1%}"
                for name, value in piece.members[:_PRODUCT_SHARE_HOVER_MEMBERS]
            )
            rest = len(piece.members) - _PRODUCT_SHARE_HOVER_MEMBERS
            amounts += f" · {listed}" + (f" 외 {rest}" if rest > 0 else "")
        texts.append(f"{cell.label} · {piece.product} {piece.share:.1%}<br>{amounts}")
    return texts


def _drawn_values(cell: ProductShareCell) -> list[float]:
    """그릴 조각 크기. 0 이 아닌 조각은 **최소 `LOB_PRODUCT_SHARE_MIN_DRAWN_SHARE`** 로 그린다.

    지름 80px 도넛에서 1% 안팎의 조각은 바깥 호가 2px 남짓이라 조각 사이 2px 틈에 통째로
    묻힌다 — 범례에는 있는데 도넛에서 보이지도 짚이지도 않는다. 그 조각만 최소 크기로 키워
    그리고, 정확한 비중은 hover 가 적는다(hover 는 이 값이 아니라 `share` 를 읽는다).
    """
    return [max(piece.share, LOB_PRODUCT_SHARE_MIN_DRAWN_SHARE) for piece in cell.slices]


def product_share_traces(
    cells: Mapping[str, ProductShareCell],
    month_labels: Sequence[str],
    *,
    basis: str,
    year_totals: Collection[str],
    past_month_labels: Collection[str] | None,
) -> list[go.Pie]:
    """칸마다 도넛 하나. 모든 도넛이 **같은 크기의 정사각형 영역**을 받아 반지름이 같다.

    조각 차례는 칸 배정 차례 그대로다(`sort=False`). Plotly 기본값은 값이 큰 순으로 다시
    세워, 달마다 같은 제품이 다른 자리에 서고 색만 같은 도넛이 된다. 12시에서 시계 방향이다.
    """
    count = max(len(month_labels), 1)
    inset_x = LOB_PRODUCT_SHARE_INSET_PX / (count * tokens.MONTH_COLUMN_WIDTH_PX)
    inset_y = LOB_PRODUCT_SHARE_INSET_PX / LOB_PLOT_AREA_HEIGHT_PX
    traces: list[go.Pie] = []
    for index, label in enumerate(month_labels):
        cell = cells.get(label)
        if cell is None:
            continue
        surface = _month_surface(label, year_totals, past_month_labels)
        # 조각 사이 틈은 그 칸의 **실제 바탕**으로 긋는다. 기본 월 칸은 면을 따로 깔지 않아
        # 캔버스가 바탕이고, 연간 Total·과거 칸은 제 면색 띠가 깔려 있다.
        gap_color = tokens.CHART_CANVAS if surface == tokens.SURFACE else surface
        traces.append(
            go.Pie(
                name=label,
                labels=[piece.product for piece in cell.slices],
                values=_drawn_values(cell),
                sort=False,
                direction="clockwise",
                rotation=0,
                hole=LOB_PRODUCT_SHARE_HOLE,
                textinfo="none",
                marker={
                    "colors": [_product_color(piece.slot) for piece in cell.slices],
                    "line": {"color": gap_color, "width": LOB_PRODUCT_SHARE_GAP_PX},
                },
                domain={
                    "x": [index / count + inset_x, (index + 1) / count - inset_x],
                    "y": [inset_y, LOB_PRODUCT_SHARE_TOP_Y - inset_y],
                },
                hovertext=_product_share_hover(cell, basis),
                hovertemplate="%{hovertext}<extra></extra>",
                hoverlabel={"font": {"size": _PRODUCT_SHARE_HOVER_FONT_SIZE_PX}},
                showlegend=False,
            )
        )
    return traces


def product_share_legend(cells: Mapping[str, ProductShareCell]) -> list[tuple[str, int | None]]:
    """범례 항목. **화면에 실제로 그려진 조각만** 칸 번호 차례로 모은다.

    EDP 를 끈 화면에서는 EDP 제품이 칸을 가진 채 조각이 없다. 범례에 두면 그리지 않은
    제품을 알리는 셈이라 뺀다(색 칸은 그대로 비워 둔다 — 남은 제품이 색을 바꾸지 않는다).
    """
    seen: dict[str, int | None] = {}
    for cell in cells.values():
        for piece in cell.slices:
            seen.setdefault(piece.product, piece.slot)
    named = sorted(
        ((name, slot) for name, slot in seen.items() if slot is not None),
        key=lambda item: item[1] if item[1] is not None else -1,
    )
    others = [(name, slot) for name, slot in seen.items() if slot is None]
    return [*named, *others]


def _product_share_label_annotations(
    cells: Mapping[str, ProductShareCell],
    basis: str,
    *,
    row_top: float,
) -> list[dict[str, Any]]:
    """구분 칸의 제목(`제품별 비중` + 단위)과 색 범례.

    범례가 이 칸에 있는 이유: 월 칸은 가로로 흐르지만 구분 칸은 늘 보인다. 제품 이름을
    도넛 안에 적을 자리가 없으므로(지름 80px) 색의 뜻은 여기서 읽는다.
    """
    entries = product_share_legend(cells)
    limit = _PRODUCT_SHARE_LEGEND_COLUMNS * _PRODUCT_SHARE_LEGEND_MAX_ROWS
    shown = entries[:limit]
    rows = math.ceil(len(shown) / _PRODUCT_SHARE_LEGEND_COLUMNS)
    row_px = _PRODUCT_SHARE_LEGEND_ROW_PX if rows <= 3 else _PRODUCT_SHARE_LEGEND_TIGHT_ROW_PX
    block = _PRODUCT_SHARE_TITLE_LINE_PX + (
        _PRODUCT_SHARE_LEGEND_GAP_PX + rows * row_px if rows else 0
    )
    top_px = (LOB_PRODUCT_SHARE_ROW_HEIGHT_PX - block) / 2
    name_budget = _legend_name_budget_units()

    def paper_y(offset_px: float) -> float:
        return row_top - offset_px / LOB_PLOT_AREA_HEIGHT_PX

    annotations: list[dict[str, Any]] = [
        {
            "x": 0.5,
            "y": paper_y(top_px + _PRODUCT_SHARE_TITLE_LINE_PX / 2),
            "xref": "paper",
            "yref": "paper",
            "text": (
                "<b>제품별 비중</b> "
                f'<span style="font-size:{PRODUCT_SHARE_UNIT_FONT_SIZE_PX}px;'
                f'color:{tokens.TEXT_MUTED}">{basis}</span>'
            ),
            "showarrow": False,
            "xanchor": "center",
            "yanchor": "middle",
            "font": {
                "size": PRODUCT_SHARE_TITLE_FONT_SIZE_PX,
                "color": tokens.TEXT,
                "family": tokens.FONT_FAMILY,
            },
        }
    ]
    for position, (name, slot) in enumerate(shown):
        row, column = divmod(position, _PRODUCT_SHARE_LEGEND_COLUMNS)
        fitted = _fit_to_units(name, name_budget, _text_width_units)
        single = len(shown) == 1
        annotations.append(
            {
                "x": 0.5 if single else _PRODUCT_SHARE_LEGEND_X[column],
                "y": paper_y(
                    top_px
                    + _PRODUCT_SHARE_TITLE_LINE_PX
                    + _PRODUCT_SHARE_LEGEND_GAP_PX
                    + (row + 0.5) * row_px
                ),
                "xref": "paper",
                "yref": "paper",
                # 이름은 본문 글자색이고 색 네모만 제품색이다 — 글자에 계열색을 입히면 밝은
                # 계열에서 읽히지 않는다.
                "text": (
                    f'<span style="color:{_product_color(slot)}">'
                    f"{_PRODUCT_SHARE_LEGEND_SWATCH.strip()}</span> {fitted}"
                ),
                "hovertext": name if fitted != name else None,
                "showarrow": False,
                "xanchor": "center" if single else "left",
                "yanchor": "middle",
                "font": {
                    "size": PRODUCT_SHARE_LEGEND_FONT_SIZE_PX,
                    "color": tokens.TEXT,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
    return annotations


class ExecutionDeltaBars(NamedTuple):
    """세로 막대에 실행 Capa 증감을 그리기 위한 조각.

    `drawn` 은 값 막대가 실제로 그릴 높이다 — 두 값 중 **짧은 쪽**이다. 줄었으면 결과값
    까지(적분홍 제외), 늘었으면 기준값까지이고 그 위를 연두가 잇는다.
    """

    drawn: list[float]
    outline_widths: list[float]
    traces: list[go.Bar]
    # 점마다 조정 전후가 다른가. 값 막대의 머리를 둥글릴지 가르는 근거다(`value_bar_traces`).
    adjusted: list[bool]


def build_execution_delta_bars(
    *,
    positions: Sequence[float],
    values: Sequence[float],
    baselines: Sequence[float] | None,
    hover_notes: Sequence[str] | None,
    width: float | None,
    outline_width: float,
) -> ExecutionDeltaBars:
    """증감 영역과 「늘어난 결과값 전체」 테두리를 만든다.

    조정이 한 건도 없으면 `traces` 가 비고 `outline_widths` 도 전부 같은 값이다. 그때
    호출자는 스칼라 테두리를 그대로 써서 Figure 규격이 조정 전과 다르지 않게 유지한다.
    """
    numeric_values = [0.0 if pd.isna(cast(Any, value)) else float(value) for value in values]
    if baselines is None:
        numeric_baselines = list(numeric_values)
    else:
        numeric_baselines = [
            numeric_values[index] if pd.isna(cast(Any, base)) else float(base)
            for index, base in enumerate(baselines)
        ]
    notes = list(hover_notes) if hover_notes is not None else [""] * len(numeric_values)

    drawn: list[float] = []
    outline_widths: list[float] = []
    delta_positions: list[float] = []
    delta_bases: list[float] = []
    delta_heights: list[float] = []
    delta_colors: list[str] = []
    delta_notes: list[str] = []
    grew_positions: list[float] = []
    grew_heights: list[float] = []
    adjusted: list[bool] = []
    for index, value in enumerate(numeric_values):
        baseline = numeric_baselines[index]
        grew = baseline < value
        drawn.append(min(baseline, value))
        outline_widths.append(0.0 if grew else outline_width)
        adjusted.append(baseline != value)
        if baseline != value:
            delta_positions.append(positions[index])
            delta_bases.append(min(baseline, value))
            delta_heights.append(abs(value - baseline))
            delta_colors.append(tokens.DELTA_AREA_INCREASE if grew else tokens.DELTA_AREA_DECREASE)
            delta_notes.append(notes[index] if index < len(notes) else "")
        if grew:
            grew_positions.append(positions[index])
            grew_heights.append(value)

    traces: list[go.Bar] = []
    if delta_positions:
        traces.append(
            go.Bar(
                x=delta_positions,
                y=delta_heights,
                base=delta_bases,
                width=width,
                marker={"color": delta_colors, "line": {"width": 0}},
                customdata=[[note] for note in delta_notes],
                hovertemplate="%{customdata[0]}<extra></extra>",
                showlegend=False,
            )
        )
    if grew_positions:
        traces.append(
            go.Bar(
                x=grew_positions,
                y=grew_heights,
                width=width,
                marker={
                    "color": tokens.TRANSPARENT,
                    "line": {"color": tokens.LINE, "width": outline_width},
                },
                hoverinfo="skip",
                showlegend=False,
            )
        )
    return ExecutionDeltaBars(
        drawn=drawn, outline_widths=outline_widths, traces=traces, adjusted=adjusted
    )


def value_bar_traces(
    *,
    name: str,
    adjusted: Sequence[bool],
    corner_radius: float,
    x: Sequence[float],
    y: Sequence[float],
    customdata: pd.DataFrame,
    colors: Sequence[str],
    line_widths: Sequence[float] | float,
    text: Sequence[str] | None = None,
    showlegend: bool | None = None,
    **common: Any,
) -> list[go.Bar]:
    """값 막대를 **머리가 둥근 달**과 **실행 조정한 달(네모 머리)** 로 가른다.

    반경은 trace 마다 스칼라로만 먹는다 — plotly.js 는 점마다 다른 반경 배열을 조용히 버리고
    직각으로 그린다. 조정한 달은 값 막대 위에 증감 조각과 결과 윤곽이 서는데, overlay 에서
    값 막대 윗끝이 결과 윤곽보다 반경만큼 낮지 않으면 둥근 모서리가 파여 보인다(통합 실측:
    LOB |증감| < 8px, Top5 < 3px). 그 달의 머리는 증감 조각이 맡으므로 값 막대는 네모로 둔다.

    조정이 한 건도 없으면 trace 는 **하나**다. 그래서 조정 0건의 Figure 는 조정 전과 같다.
    둘로 가를 때는 점마다 딸린 배열(customdata·text·색·테두리 굵기)을 같이 가르고, 둘째
    trace 는 범례에 따로 서지 않게 같은 `legendgroup` 으로 묶는다.
    """
    groups: list[tuple[bool | None, float]] = (
        [(False, corner_radius), (True, 0)] if any(adjusted) else [(None, corner_radius)]
    )
    # 자리로 고른다. pandas Series 가 섞여 들어와도 색인이 아니라 차례로 집도록 먼저 목록으로 편다.
    columns: dict[str, list[Any]] = {"x": list(x), "y": list(y), "color": list(colors)}
    if text is not None:
        columns["text"] = list(text)
    if not isinstance(line_widths, (int, float)):
        columns["line_width"] = list(line_widths)
    traces: list[go.Bar] = []
    for wanted, radius in groups:
        keep = [
            index
            for index in range(len(columns["x"]))
            if wanted is None or bool(adjusted[index]) == wanted
        ]
        if not keep:
            continue
        chosen = {key: [values[index] for index in keep] for key, values in columns.items()}
        widths = chosen.get("line_width", line_widths)
        extra: dict[str, Any] = {}
        if "text" in chosen:
            extra["text"] = chosen["text"]
        second = wanted is True
        if second:
            extra["showlegend"] = False
        elif showlegend is not None:
            extra["showlegend"] = showlegend
        traces.append(
            go.Bar(
                name=name,
                legendgroup=name,
                x=chosen["x"],
                y=chosen["y"],
                customdata=customdata.iloc[keep],
                marker={
                    "color": chosen["color"],
                    "line": {"color": tokens.LINE, "width": widths},
                    "cornerradius": radius,
                },
                **extra,
                **common,
            )
        )
    return traces


def _execution_series(frame: pd.DataFrame, column: str) -> pd.Series | None:
    """있을 때만 돌려준다. Figure 는 조정 컬럼 없이도 그려져야 한다."""
    return frame[column] if column in frame.columns else None


def _banded_rate_heights(
    monthly_top5: pd.DataFrame,
    rate_column: str,
    band: tuple[float, float],
) -> list[float]:
    """막대 높이. **밴드로 자른 확보율 그 자체**이고 다른 것을 곱하지 않는다.

    예전에는 `부하량 × 확보율`(= B/N Capa)을 높이로 썼다. "한 달 안에서는 부하량이 같으니
    높이가 곧 확보율에 비례한다" 는 전제였는데, Top5 는 한 달에 **서로 다른 공정 다섯 줄**
    이라 부하량이 제각각이다. 그래서 같은 확보율도 부하량이 크면 긴 막대가 됐고, 밴드가
    막대 길이를 묶지 못했다.

    지금은 확보율만 쓴다. 그래서 **확보율이 같으면 어느 달의 어느 공정이든 막대가 같은
    길이**다 — 180% 공정은 그 달의 LOB B/N 확보율이 100% 든 150% 든 같은 높이에 선다.
    축 위끝도 데이터 최대가 아니라 밴드 상한이라, 다시 그려도 같은 확보율은 같은 자리다.

    hover 의 Capa 숫자는 여전히 자르지 않은 실제 값이다. 자르는 것은 막대 길이뿐이다.
    """
    rates = pd.to_numeric(monthly_top5[rate_column], errors="coerce")
    return [0.0 if pd.isna(rate) else clamp_rate(float(rate), band) for rate in rates]


# 증감이 이 값보다 작으면 적지 않는다. 화면에 보이는 자릿수에서 달라지지 않은 칸까지
# `+0.00` 을 달면 무엇이 움직였는지 오히려 안 읽힌다.
_GAP_EPSILON = 5e-3
# Wafer 계획 증감의 글자(천 매 단위). 값 칸(`2K`)과 같은 0 자리로 쓰면 5~499 매가 `+0K`·`-0K` 로
# 찍혀 0 이 아닌 증감이 0 으로 읽혔다(2026-10-01 브라우저 점검). 한 자리를 더 쓰고, 그 자리에서도
# 0 으로 보이는 증감(50 매 미만)은 `_visible_gap` 이 적지 않는다.
_WAFER_GAP_FORMAT = "{:+,.1f}K"


def _contiguous_segments(indices: Sequence[int]) -> list[tuple[int, int]]:
    """이어진 정수를 `(시작, 끝)` 구간으로 접는다. 끝은 포함이다.

    연간 Total 열이 월 사이에 끼면 월 축이 끊긴다. 그 끊긴 자리를 건너뛰고 선을 그으려면
    구간 목록이 필요하다.
    """
    segments: list[tuple[int, int]] = []
    for index in indices:
        if segments and index == segments[-1][1] + 1:
            segments[-1] = (segments[-1][0], index)
        else:
            segments.append((index, index))
    return segments


def _threshold_runs(
    segments: Sequence[tuple[int, int]], values: Sequence[float]
) -> list[tuple[int, int, float]]:
    """이어진 월 구간을 다시 **같은 기준값이 이어지는** 구간으로 쪼갠다. 끝은 포함이다.

    `values[i]` 는 월 축 i 번째 칸의 실효 기준이다. 월별 예외가 없으면 구간마다 값이 하나라
    입력 구간이 그대로 나온다 — 기준선 도형 수가 예전과 같다.
    """
    runs: list[tuple[int, int, float]] = []
    for start, end in segments:
        run_start = start
        for index in range(start + 1, end + 1):
            if values[index] != values[index - 1]:
                runs.append((run_start, index - 1, values[index - 1]))
                run_start = index
        runs.append((run_start, end, values[end]))
    return runs


def _aligned_by_label(frame: pd.DataFrame | None, month_labels: list[str]) -> pd.DataFrame | None:
    """월 축 라벨 차례로 프레임을 맞춘다. 축에 없는 칸은 결측이 된다."""
    if frame is None or "년월" not in frame.columns:
        return None
    return frame.set_index(frame["년월"].astype("string")).reindex(month_labels)


def _axis_series(frame: pd.DataFrame | None, column: str) -> list[float | None]:
    """칸마다 값 하나. 결측은 `None` 이라 Plotly 가 선을 끊는다."""
    if frame is None or column not in frame.columns:
        return []
    return [None if pd.isna(value) else float(value) for value in frame[column]]


def _axis_values(
    frame: pd.DataFrame,
    month_labels: list[str],
    totals: Mapping[str, Mapping[str, float]],
    column: str,
    number_format: str,
    *,
    scale: float = 1.0,
) -> list[str]:
    """표 한 행의 칸 글자. 연간 Total 칸은 미리 더해 둔 값에서 꺼낸다."""
    values = frame[column] if column in frame.columns else pd.Series(dtype="float64")
    rendered: list[str] = []
    for label, value in zip(month_labels, values, strict=True):
        total = totals.get(label, {}).get(column)
        amount = total if total is not None else value
        rendered.append("" if pd.isna(amount) else number_format.format(float(amount) / scale))
    return rendered


def _value_gaps(
    current: pd.DataFrame,
    baseline: pd.DataFrame | None,
    column: str,
    number_format: str,
    *,
    scale: float = 1.0,
) -> list[str] | None:
    """칸마다 적을 증감 문구. 기준이 없거나 달라진 칸이 없으면 `None` 이다."""
    if baseline is None or column not in current.columns or column not in baseline.columns:
        return None
    differences = (
        pd.to_numeric(current[column], errors="coerce").to_numpy()
        - pd.to_numeric(baseline[column], errors="coerce").to_numpy()
    ) / scale
    gaps = [
        ""
        if pd.isna(value) or abs(value) < _GAP_EPSILON
        else _visible_gap(number_format.format(value))
        for value in differences
    ]
    return gaps if any(gaps) else None


def _visible_gap(text: str) -> str:
    """증감 글자 하나. 형식 자릿수에서 0 으로 보이면(`+0.0K`·`-0.00`) 적지 않는다.

    `_GAP_EPSILON` 은 소수 둘째 자리 형식에 맞춘 값이라 자릿수가 다른 형식에는 맞지 않는다.
    글자로 판정하면 형식이 무엇이든 「0 이 아닌 증감이 0 으로 찍히는」 칸이 생기지 않는다.
    """
    return text if any(character in "123456789" for character in text) else ""


def _bottleneck_rate_labels(
    bottleneck_capacity: pd.DataFrame,
    baseline: pd.DataFrame | None,
) -> list[str]:
    """막대 안 확보율 글자. 선행 전 기준이 있으면 그 위에 증감을 작게 얹는다.

    `texttemplate` 대신 칸마다 문자열을 만든다 — 한 trace 안에서 어떤 칸만 두 줄이 되고
    글자 크기도 달라야 하는데 서식 문자열 하나로는 그렇게 나눌 수 없다.
    """
    rates = pd.to_numeric(bottleneck_capacity["확보율"], errors="coerce")
    if baseline is None or "확보율" not in baseline.columns:
        return [_bar_rate_text(rate) for rate in rates]
    base_rates = pd.to_numeric(
        bottleneck_capacity[["생산계획년월"]].merge(
            baseline[["생산계획년월", "확보율"]], on="생산계획년월", how="left"
        )["확보율"],
        errors="coerce",
    )
    labels: list[str] = []
    for rate, base_rate in zip(rates, base_rates, strict=True):
        if pd.isna(rate):
            labels.append("")
            continue
        body = _bar_rate_text(rate)
        difference = rate - base_rate if pd.notna(base_rate) else float("nan")
        if pd.isna(difference) or abs(difference) < _GAP_EPSILON:
            labels.append(body)
            continue
        color = delta_color(f"{difference:+.0%}")
        gap = f'<span style="color:{color}">{difference * 100:+.0f}%</span>'
        labels.append(f"{gap}<br>{body}")
    return labels


def _bar_rate_label(rate: float) -> str:
    """Top5 막대 위에 세우는 확보율 글자. 축 여유를 재는 쪽과 **같은 함수**를 본다.

    두 곳이 따로 서식을 적으면 글자 수가 갈라져 비워 둔 자리 밖으로 라벨이 나간다.
    """
    if pd.isna(rate):
        return ""
    return f"{rate:.0%}"


def _bar_rate_text(rate: float) -> str:
    """막대 안 확보율 한 줄.

    trace 의 글자 크기는 증감 크기로 낮추고 값만 span 으로 키운다. Plotly 는 `<br>` 줄
    간격을 **요소의 글자 크기**로 정하므로, 값 크기를 그대로 두면 증감이 값에서 한 줄
    높이(약 29px)만큼 떨어져 따로 노는 글자로 읽힌다.
    """
    if pd.isna(rate):
        return ""
    return f'<span style="font-size:{LOB_BAR_LABEL_FONT_SIZE_PX}px"><b>{rate:.0%}</b></span>'


def build_lob_summary_figures(
    *,
    monthly_density: pd.DataFrame,
    monthly_top5: pd.DataFrame,
    bottleneck_capacity: pd.DataFrame,
    lob_summary: pd.DataFrame,
    month_labels: list[str],
    thresholds: SecurementThresholds,
    process_labels: ProcessLabels | None = None,
    baseline_lob_summary: pd.DataFrame | None = None,
    comparison_density: pd.DataFrame | None = None,
    comparison_wafer: pd.DataFrame | None = None,
    year_totals: Mapping[str, Mapping[str, float]] | None = None,
    top5_rate_band: tuple[float, float] = (DEFAULT_TOP5_MIN_RATE, DEFAULT_TOP5_MAX_RATE),
    past_month_labels: Collection[str] | None = None,
    product_share_cells: Mapping[str, ProductShareCell] | None = None,
    product_share_basis: str = PRODUCT_SHARE_BASIS_WAFER,
) -> tuple[go.Figure, go.Figure]:
    """생산계획·Wafer Capa·Bottleneck·제품별 비중 요약 Figure 한 쌍을 만든다.

    `process_labels` 는 **화면 문자열에만** 쓴다. 프레임의 `공정` 값은 그대로 두므로
    월 위치 계산과 확보율 색 판정은 원본을 본다.

    `thresholds` 는 공용 판정 기준이다. 막대 색과 Top 5 기준선은 **그 달의 실효 기준**을
    쓴다 — 월별 예외가 없으면 모든 달이 기본값이라 예전 한 짝 기준과 같은 그림이다.

    `baseline_lob_summary` 는 선행 반영 **전**의 같은 요약이다. 주면 Density·Wafer 계획
    칸에 증감을 값 **위**에 작게 얹고 생산계획 LOB 에 기존 계획을 점선으로 함께 그린다.
    Wafer Capa 는 `계획 × 확보율` 이라 선행 전후가 정확히 같으므로 증감을 적지 않는다.

    `comparison_density`·`comparison_wafer` 는 비교 시나리오의 같은 월별 표다. 주면 값
    **아래**에 증감을 적는다. 위아래를 나눠 둔 것은 한 칸에 둘이 함께 붙을 수 있어서다.

    `product_share_cells` 는 월 축 라벨 → 도넛 칸이다(`services/product_share`). 행 자체는
    늘 있고, 칸이 없는 라벨은 비워 둔다. `product_share_basis` 는 구분 칸에 적는 단위다.
    """
    labels = process_labels or ProcessLabels()
    totals = dict(year_totals or {})
    # 월 축의 근거는 `month_labels` 하나뿐이다. 연간 Total 칸이 끼면 프레임의 행 수와 칸
    # 수가 더는 같지 않으므로 라벨로 맞춘다. 맞추고 나면 Total 칸은 결측이라 증감도
    # 자연히 비고, 그것이 맞다 — 합계 칸에 전월 대비를 적을 자리는 없다.
    if "년월" not in lob_summary.columns:
        raise ValueError("LOB 요약에 월 축을 맞출 `년월` 컬럼이 없습니다.")
    aligned_summary = _aligned_by_label(lob_summary, month_labels)
    aligned_baseline = _aligned_by_label(baseline_lob_summary, month_labels)
    aligned_comparison_density = _aligned_by_label(comparison_density, month_labels)
    aligned_comparison_wafer = _aligned_by_label(comparison_wafer, month_labels)
    assert aligned_summary is not None
    density_gaps = _value_gaps(aligned_summary, aligned_baseline, "부하량", "{:+,.2f}")
    wafer_plan_gaps = _value_gaps(
        aligned_summary, aligned_baseline, "Wafer 부하량", _WAFER_GAP_FORMAT, scale=1_000
    )
    # GAP 은 **원 데이터끼리의** 차이다. 선행을 켜면 `aligned_summary` 는 이미 선행이 반영된
    # 값이라 그대로 빼면 비교 시나리오와의 차이에 내가 넣은 선행 물량이 섞인다. 비교
    # 시나리오 쪽에는 선행이 반영되지 않으므로(선행은 이 화면에만 얹는 공용 설정이다)
    # 기준을 선행 전 값으로 맞춘다. 선행이 꺼져 있으면 둘이 같은 프레임이다.
    raw_summary = aligned_baseline if aligned_baseline is not None else aligned_summary
    density_comparison_gaps = _value_gaps(
        raw_summary, aligned_comparison_density, "부하량", "{:+,.2f}"
    )
    wafer_plan_comparison_gaps = _value_gaps(
        raw_summary, aligned_comparison_wafer, "Wafer 부하량", _WAFER_GAP_FORMAT, scale=1_000
    )
    month_positions = list(range(len(month_labels)))
    month_position_by_value = {
        int(month): index
        for index, month in enumerate(aligned_summary["생산계획년월"])
        if pd.notna(month)
    }
    value_fills = [_month_surface(label, totals, past_month_labels) for label in month_labels]
    # 넷째 줄은 축이 없는 자리다. 위쪽은 B/N Top 5 공정명이 드리우는 띠, 아래쪽은 도넛
    # 행이다. 도넛은 축이 아니라 paper 좌표의 `domain` 으로 놓으므로 이 줄은 자리만 잡는다.
    subplot_options = {
        "rows": 4,
        "cols": 1,
        "specs": [[{"type": "table"}], [{"type": "xy"}], [{"type": "xy"}], [None]],
        "shared_xaxes": False,
        "vertical_spacing": 0,
        "row_heights": [
            LOB_TABLE_HEIGHT_PX,
            LOB_CHART_HEIGHT_PX,
            LOB_TOP5_HEIGHT_PX,
            LOB_TOP5_LABEL_ZONE_PX + LOB_PRODUCT_SHARE_ROW_HEIGHT_PX,
        ],
    }
    label_figure = make_subplots(**subplot_options)
    month_figure = make_subplots(**subplot_options)
    label_table_rows = (
        ("구분", tokens.HEADER_BACKGROUND, 21, True),
        ("Density (억Gb)", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer 계획", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer Capa", tokens.SURFACE_CLASSIFICATION, 20, True),
    )
    month_table_rows = (
        (
            [f"{month}" for month in month_labels],
            tokens.HEADER_BACKGROUND,
            21,
            True,
            None,
            None,
        ),
        (
            _axis_values(aligned_summary, month_labels, totals, "부하량", "{:,.2f}"),
            value_fills,
            LOB_VALUE_FONT_SIZE_PX,
            False,
            density_gaps,
            density_comparison_gaps,
        ),
        (
            _axis_values(
                aligned_summary, month_labels, totals, "Wafer 부하량", "{:,.0f}K", scale=1_000
            ),
            value_fills,
            LOB_VALUE_FONT_SIZE_PX,
            False,
            wafer_plan_gaps,
            wafer_plan_comparison_gaps,
        ),
        (
            # Wafer Capa 는 연간 Total 을 적지 않는다. 월별 Capa 의 단순 합은 연간 Capa 가
            # 아니다 — 더해 놓으면 그 해 투입 가능량으로 읽힌다.
            _axis_values(aligned_summary, month_labels, {}, "Wafer Capa", "{:,.0f}K", scale=1_000),
            value_fills,
            20,
            False,
            None,
            None,
        ),
    )
    lob_chart_domain = cast(Any, month_figure.layout.yaxis).domain
    full_table_domain = (float(lob_chart_domain[1]), 1.0)
    lob_table_domains = fixed_row_domains(
        float(full_table_domain[0]),
        float(full_table_domain[1]),
        LOB_TABLE_ROW_HEIGHTS_PX,
    )
    for row_domain, (value, fill_color, font_size, bold) in zip(
        lob_table_domains,
        label_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            label_figure,
            domain=row_domain,
            values=[value],
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    # 라벨 칸과 이름을 나눈다. 월 칸은 연간 Total 만 달리 칠하려고 칸별 면색 목록을 받는데,
    # 같은 이름을 쓰면 검사기가 라벨 칸의 단일 색 타입으로 고정한다.
    for row_domain, (
        month_values,
        month_fill,
        month_font_size,
        month_bold,
        gaps,
        lower_gaps,
    ) in zip(lob_table_domains, month_table_rows, strict=True):
        add_fixed_table_row(
            month_figure,
            domain=row_domain,
            values=month_values,
            fill_color=month_fill,
            font_size=month_font_size,
            bold=month_bold,
            gaps=gaps,
            lower_gaps=lower_gaps,
        )
    if bottleneck_capacity["B/N Capa"].notna().any():
        bottleneck_positions = [
            month_position_by_value[month] for month in bottleneck_capacity["생산계획년월"]
        ]
        # 순위 재배치 뒤의 **최종 B/N 공정** 기준으로 증감을 그린다. `기준 B/N Capa` 는
        # 같은 공정의 조정 전 Capa 이고, 서비스가 부하량 × 기준 확보율로 미리 만든다.
        bottleneck_delta = build_execution_delta_bars(
            positions=bottleneck_positions,
            values=bottleneck_capacity["B/N Capa"].tolist(),
            baselines=(
                series.tolist()
                if (series := _execution_series(bottleneck_capacity, "기준 B/N Capa")) is not None
                else None
            ),
            hover_notes=[
                _execution_delta_note(delta, note)
                for delta, note in zip(
                    bottleneck_capacity.get(
                        "확보율 증감", pd.Series(0.0, index=bottleneck_capacity.index)
                    ),
                    bottleneck_capacity.get(
                        "실행 비고", pd.Series("", index=bottleneck_capacity.index)
                    ),
                    strict=True,
                )
            ],
            width=LOB_BAR_WIDTH,
            outline_width=LOB_BAR_OUTLINE_WIDTH_PX,
        )
        # 값 막대의 머리를 둥글린다(굵기 70px — 넓음 등급). 실행 조정한 달은 네모로 남는다.
        for value_trace in value_bar_traces(
            name="B/N 공정",
            adjusted=bottleneck_delta.adjusted,
            corner_radius=tokens.BAR_CORNER_RADIUS_WIDE_PX,
            x=bottleneck_positions,
            y=bottleneck_delta.drawn,
            customdata=bottleneck_capacity[["년월", "확보율"]].assign(
                공정=labels.series(bottleneck_capacity["공정"])
            ),
            colors=[
                _capacity_color(rate, thresholds=thresholds, month=int(month))
                for rate, month in zip(
                    bottleneck_capacity["확보율"],
                    bottleneck_capacity["생산계획년월"],
                    strict=True,
                )
            ],
            # 조정이 없으면 굵기가 모두 같다. 그때는 스칼라로 남겨 Figure 규격이 조정 전과
            # 다르지 않게 한다.
            line_widths=(
                bottleneck_delta.outline_widths
                if bottleneck_delta.traces
                else LOB_BAR_OUTLINE_WIDTH_PX
            ),
            text=_bottleneck_rate_labels(bottleneck_capacity, baseline_lob_summary),
            width=LOB_BAR_WIDTH,
            textposition="inside",
            insidetextanchor="start",
            # 값은 `_bar_rate_text` 가 span 으로 키운다. 여기 크기는 줄 간격을 정한다.
            textfont={
                "color": tokens.TEXT,
                "size": tokens.DELTA_FONT_SIZE_PX,
                "family": tokens.FONT_FAMILY_NUMERIC,
            },
            hovertemplate=(
                "%{customdata[0]} · B/N %{customdata[2]}"
                "<br>Capa %{y:,.2f} 억Gb"
                "<br>확보율 %{customdata[1]:.1%}<extra></extra>"
            ),
        ):
            month_figure.add_trace(value_trace, row=2, col=1)
        for delta_trace in bottleneck_delta.traces:
            month_figure.add_trace(delta_trace, row=2, col=1)
    if baseline_lob_summary is not None:
        # 기존 계획은 비교용이라 표식과 라벨을 지운다. 두 줄 모두 값을 적으면 숫자가
        # 겹쳐 어느 쪽이 지금 기준인지 읽히지 않는다.
        month_figure.add_trace(
            go.Scatter(
                name="Density (선행 전)",
                x=month_positions,
                y=_axis_series(aligned_baseline, "부하량"),
                customdata=month_labels,
                mode="lines",
                line={"color": tokens.TEXT_MUTED, "width": 2, "dash": "dot"},
                cliponaxis=False,
                hovertemplate="%{customdata} · 선행 전<br>%{y:,.2f} 억Gb<extra></extra>",
            ),
            row=2,
            col=1,
        )
    month_figure.add_trace(
        go.Scatter(
            name="Density",
            x=month_positions,
            # 연간 Total 칸에서는 선을 끊는다. 합계 칸을 가로지르면 그 값이 그 달의 계획인
            # 것처럼 읽힌다.
            y=_axis_series(aligned_summary, "부하량"),
            customdata=month_labels,
            mode="lines+markers+text",
            text=_axis_series(aligned_summary, "부하량"),
            texttemplate="<b>%{text:,.2f}</b>",
            textposition="top center",
            textfont={"size": 20, "color": tokens.TEXT, "family": tokens.FONT_FAMILY_NUMERIC},
            line={"color": tokens.LINE, "width": 3},
            marker={
                "color": tokens.SURFACE,
                "size": 8,
                "line": {"color": tokens.LINE, "width": 2.0},
            },
            cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:,.2f} 억Gb<extra></extra>",
        ),
        row=2,
        col=1,
    )
    top5_annotations: list[dict[str, Any]] = []
    if not monthly_top5.empty:
        # 막대 높이는 **밴드로 자른 확보율**이다. 부하량을 곱하지 않으므로 확보율이 같으면
        # 달과 공정이 달라도 길이가 같다. hover 의 Capa 숫자는 자르지 않은 실제 값 그대로다.
        top5_bar_values = _banded_rate_heights(monthly_top5, "확보율", top5_rate_band)
        top5_baseline_values = (
            _banded_rate_heights(monthly_top5, "기준 확보율", top5_rate_band)
            if "기준 확보율" in monthly_top5.columns
            else None
        )
        # 축 위쪽은 라벨이 먹는 픽셀만큼만 비운다. 나머지는 막대가 쓴다 — 확보율 구간을
        # 잘라 여러 달이 같은 높이에 서면 그 위로 쓰지 않는 띠가 그대로 드러난다.
        #
        # 자리는 **그 화면에서 가장 긴 라벨**이 정한다. 라벨은 밴드로 자르기 전의 원
        # 확보율이라 상한을 200% 로 두어도 `1250%` 가 뜰 수 있고, 네 글자를 가정하면 그
        # 순간 라벨이 행 밖으로 나가 위 구획을 침범한다.
        top5_headroom_px = top5_axis_headroom_px(
            max((len(_bar_rate_label(rate)) for rate in monthly_top5["확보율"]), default=0)
        )
        top5_headroom = min(top5_headroom_px / LOB_TOP5_HEIGHT_PX, 0.5)
        # 축 위끝은 **밴드 상한**이다. 데이터 최대로 잡으면 같은 확보율이 다시 그릴 때마다
        # 다른 높이에 서서, 막대 길이를 밴드에 묶은 뜻이 없어진다.
        top5_axis_max = top5_rate_band[1] / (1 - top5_headroom)
        wafer_capa_label_y = top5_axis_max * 0.04
        slot_offsets = {1: -0.36, 2: -0.18, 3: 0.0, 4: 0.18, 5: 0.36}
        top5_positions = [
            month_position_by_value[month] + slot_offsets[int(rank)]
            for month, rank in zip(monthly_top5["생산계획년월"], monthly_top5["순위"], strict=True)
        ]
        # 증감은 **슬롯이 아니라 공정 기준**이다. 순위가 재배치돼 슬롯 3 이 다른 공정이
        # 되어도, 그 자리에 선 공정의 조정 전·후를 그린다.
        top5_delta = build_execution_delta_bars(
            positions=top5_positions,
            values=top5_bar_values,
            baselines=top5_baseline_values,
            hover_notes=[
                _execution_delta_note(delta, note)
                for delta, note in zip(
                    monthly_top5.get("확보율 증감", pd.Series(0.0, index=monthly_top5.index)),
                    monthly_top5.get("실행 비고", pd.Series("", index=monthly_top5.index)),
                    strict=True,
                )
            ],
            width=TOP5_BAR_WIDTH,
            outline_width=TOP5_BAR_OUTLINE_WIDTH_PX,
        )
        # 머리를 둥글린다. 막대가 15px 로 가늘어 좁음 등급(3px)이다 — 넓음 반경이면 머리 전체가
        # 반원이 된다. 밴드 상한에서 잘린 막대도 같은 머리다(3px 라 「잘렸다」는 모양은 거의
        # 같다). 실행 조정한 달은 네모로 남는다.
        for value_trace in value_bar_traces(
            name="B/N Capa Top 5",
            adjusted=top5_delta.adjusted,
            corner_radius=tokens.BAR_CORNER_RADIUS_NARROW_PX,
            x=top5_positions,
            y=top5_delta.drawn,
            # 막대 길이는 잘렸어도 hover 숫자는 실제 Capa 다. `%{y}` 를 쓰면 잘린
            # 값이 그대로 뜬다.
            customdata=monthly_top5[["년월", "공정", "확보율", "Wafer Capa", "B/N Capa"]].assign(
                공정=labels.series(monthly_top5["공정"])
            ),
            colors=[
                _capacity_color(rate, thresholds=thresholds, month=int(month))
                for rate, month in zip(
                    monthly_top5["확보율"], monthly_top5["생산계획년월"], strict=True
                )
            ],
            line_widths=(
                top5_delta.outline_widths if top5_delta.traces else TOP5_BAR_OUTLINE_WIDTH_PX
            ),
            width=TOP5_BAR_WIDTH,
            hovertemplate=(
                "%{customdata[0]} · %{customdata[1]}"
                "<br>Capa %{customdata[4]:,.2f} 억Gb"
                "<br>확보율 %{customdata[2]:.1%}"
                "<br>Wafer Capa %{customdata[3]:,.0f} 매"
                "<extra></extra>"
            ),
            showlegend=False,
        ):
            month_figure.add_trace(value_trace, row=3, col=1)
        for delta_trace in top5_delta.traces:
            month_figure.add_trace(delta_trace, row=3, col=1)
        # 판정 기준을 선으로 긋는다. 이 축은 **확보율 자체**라(막대 높이 = 자른 확보율)
        # 기준값을 그대로 y 로 쓸 수 있다. 지금까지 이 기준은 오직 막대 **색**으로만
        # 존재해서, 경고색 막대를 보고도 기준에서 얼마나 모자란지 눈으로 못 쟀다.
        #
        # 밴드 밖으로 나가는 기준은 긋지 않는다. Top5 밴드는 사용자가 바꿀 수 있어
        # 기준이 축 위로 올라갈 수 있는데, 그때 선을 축 끝에 붙이면 「기준에 닿았다」로
        # 잘못 읽힌다.
        #
        # 선은 **월 칸 위에만** 긋는다. 연간 Total 열은 확보율을 더하지 않아 비워 둔
        # 칸인데 그 위로 선이 지나가면 합계에도 기준이 있는 것처럼 읽힌다. `add_hline`
        # 은 축 전체를 가로지르므로 쓸 수 없고, 이어진 월 구간마다 선분을 따로 긋는다.
        #
        # 기준은 **달마다** 다를 수 있다(월별 예외). 이어진 월 구간을 다시 「같은 값이 이어지는
        # 구간」으로 나눠 그 높이에 긋는다. 예외가 없으면 값이 하나라 구간이 예전과 같다.
        month_line_segments = _contiguous_segments(
            [index for index, label in enumerate(month_labels) if label not in totals]
        )
        month_by_position = [
            None if pd.isna(month) else int(month) for month in aligned_summary["생산계획년월"]
        ]
        #
        # **`add_shape`·`add_hline` 을 쓰지 않는다.** 그 둘은 `figure.layout.shapes` 에
        # 곧바로 쓰는데, 이 Figure 의 나머지 도형은 전부 `append_layout_items` 누적함에
        # 모였다가 마지막에 `update_layout(shapes=...)` 한 번으로 들어간다. Plotly 의
        # `update_layout` 은 배열을 **갈아끼우지 않고 자리마다 병합**하므로, 먼저 들어가
        # 있던 기준선 N 개가 누적함의 **앞쪽 도형 N 개를 잡아먹는다**. 실제로 표 머리글
        # 면색과 첫 달 값 칸의 면색이 사라져 그 두 칸만 캔버스 색으로 보였다.
        # 같은 누적함에 넣으면 순서도 개수도 어긋나지 않는다.
        threshold_shapes = [
            {
                "type": "line",
                "x0": segment_start - 0.5,
                "x1": segment_end + 0.5,
                "y0": threshold,
                "y1": threshold,
                "xref": "x2",
                "yref": "y2",
                "line": {"color": tokens.LINE, "width": 1, "dash": "dot"},
                "layer": "above",
            }
            for pick in (0, 1)
            for segment_start, segment_end, threshold in _threshold_runs(
                month_line_segments,
                [thresholds.for_month(month)[pick] for month in month_by_position],
            )
            if 0 < threshold <= top5_rate_band[1]
        ]
        append_layout_items(month_figure, shapes=threshold_shapes)
        for x_position, capa, rate in zip(
            top5_positions,
            # 라벨은 그려진 막대 끝에 붙어야 한다. 실제 Capa 를 쓰면 잘린 막대에서 떨어진다.
            top5_bar_values,
            monthly_top5["확보율"],
            strict=True,
        ):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": capa,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"<b>{_bar_rate_label(rate)}</b>",
                    "textangle": 270,
                    # 가로는 보정하지 않는다. `xanchor="center"` 가 세운 글자의 상자
                    # 가운데를 막대 중심에 정확히 놓는다 — 브라우저에서 회전 중심과 막대
                    # 중심을 대조해 10개 라벨 모두 오차 0 임을 확인했다. 숫자는 디센더가
                    # 없어 상자 안에서 위로 몰릴 것 같지만, 실측한 잉크 중심이 상자
                    # 중심과 같았다. 여기에 `xshift` 를 두면 그만큼 그대로 어긋난다.
                    "xanchor": "center",
                    "yanchor": "bottom",
                    # 축 여유를 계산한 값과 **같은 상수**를 쓴다. 둘이 갈라지면 라벨이
                    # 비워 둔 자리 밖으로 나가 잘린다.
                    "yshift": TOP5_RATE_LABEL_GAP_PX,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        for x_position, wafer_capa in zip(top5_positions, monthly_top5["Wafer Capa"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": wafer_capa_label_y,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"{wafer_capa / 1_000:,.0f}K",
                    "textangle": 270,
                    # **확보율 레이블과 가로 보정이 다르다.** 두 라벨은 x 위치를 공유하지만
                    # 확보율은 `<b>` 굵은 글자라 글꼴 상자가 달라, 같은 기준으로 두면 이쪽만
                    # 오른쪽으로 치우쳐 보인다. 그 차이를 여기서만 되민다.
                    "xanchor": "center",
                    "xshift": TOP5_WAFER_LABEL_XSHIFT_PX,
                    "yanchor": "bottom",
                    "yshift": -6.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        # 공정명은 띠(`LOB_TOP5_LABEL_ZONE_PX`) 안에서 끝나야 한다 — 넘치면 아래 도넛 위에
        # 얹힌다(`top5_process_label_budget` 설명). 줄인 이름은 hover 가 전체를 보여 준다.
        # 서체가 Calibri 라 그 서체로 잰 폭 모형을 쓴다(`_calibri_width_units`).
        process_budget = top5_process_label_room_px() / TOP5_PROCESS_LABEL_FONT_SIZE_PX
        for x_position, process in zip(top5_positions, monthly_top5["공정"], strict=True):
            process_label = labels.label(process)
            fitted_label = _fit_to_units(process_label, process_budget, _calibri_width_units)
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": 0,
                    "xref": "x2",
                    "yref": "y2",
                    "text": fitted_label,
                    "hovertext": process_label if fitted_label != process_label else None,
                    "textangle": 270,
                    "xanchor": "right",
                    "yanchor": "top",
                    "xshift": 11.0,
                    "yshift": -TOP5_PROCESS_LABEL_YSHIFT_PX,
                    "showarrow": False,
                    "font": {
                        "size": TOP5_PROCESS_LABEL_FONT_SIZE_PX,
                        "color": tokens.TEXT_MUTED,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
    common_layout = {
        "height": LOB_FIGURE_HEIGHT_PX,
        "margin": {
            "l": 0,
            "r": 0,
            "t": LOB_TOP_MARGIN_PX,
            "b": LOB_BOTTOM_MARGIN_PX,
            # Plotly 는 그림 밖으로 나가는 글자에 맞춰 여백을 **스스로 늘린다**. 두 Figure 의
            # 글자가 다르므로 늘어나는 양도 달라지고, 그러면 왼쪽 라벨 칸과 월 칸의 행이
            # 어긋난다. 제목 여백 44px 이 그 차이를 가려 주고 있었다. 여백을 적은 대로만
            # 쓰게 해 두 칸이 같은 자리에서 시작하게 한다.
            "autoexpand": False,
        },
        "barmode": "overlay",
        "bargap": LOB_BARGAP,
        # 드래그로 영역을 잡아 확대하는 동작을 끈다. hover 는 그대로 살아 있다 —
        # `staticPlot` 을 쓰면 툴팁까지 죽으므로 그 방법은 쓰지 않는다.
        "dragmode": False,
        "plot_bgcolor": tokens.CHART_CANVAS,
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    label_figure.update_layout(**common_layout, showlegend=False)
    month_figure.update_layout(
        **common_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"color": tokens.TEXT_MUTED, "size": 13},
        },
    )
    append_layout_items(month_figure, annotations=top5_annotations)
    month_figure.add_traces(
        product_share_traces(
            product_share_cells or {},
            month_labels,
            basis=product_share_basis,
            year_totals=totals,
            past_month_labels=past_month_labels,
        )
    )
    # 조정 **전** Capa 도 함께 본다. 빼먹으면 한 달만 조정해도 전 달 막대 높이가 바뀌어
    # 「조정이 없는 달은 그대로」가 무너진다.
    axis_candidates = [
        monthly_density["부하량"].max(),
        bottleneck_capacity["B/N Capa"].max(),
    ]
    if "기준 B/N Capa" in bottleneck_capacity.columns:
        axis_candidates.append(bottleneck_capacity["기준 B/N Capa"].max())
    lob_axis_max = max(
        (float(value) for value in axis_candidates if pd.notna(value)),
        default=1.0,
    )
    lob_axis_max = max(lob_axis_max, 1.0)
    # 두 축 모두 `fixedrange` 여야 hover 를 켜 둔 채로 드래그 확대가 붙지 않는다. 상세
    # B/N 월 Figure 가 같은 이유로 같은 설정을 쓴다.
    for target_figure in (label_figure, month_figure):
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            range=[0, lob_axis_max * 1.35],
            row=2,
            col=1,
        )
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            range=[
                0,
                top5_axis_max if not monthly_top5.empty else 1.0,
            ],
            row=3,
            col=1,
        )
    for row_number in (2, 3):
        month_figure.update_xaxes(
            tickmode="array",
            tickvals=month_positions,
            ticktext=month_labels,
            showticklabels=False,
            title=None,
            showgrid=False,
            fixedrange=True,
            range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
            domain=[0.0, 1.0],
            row=row_number,
            col=1,
        )
        label_figure.update_xaxes(
            showticklabels=False,
            title=None,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            row=row_number,
            col=1,
        )
    panel_bottom = LOB_PANEL_BOTTOM_Y
    lob_y_domain = month_figure.layout.yaxis.domain
    top5_y_domain = month_figure.layout.yaxis2.domain
    table_y_domain = (lob_table_domains[-1][0], lob_table_domains[0][1])
    share_top = LOB_PRODUCT_SHARE_TOP_Y
    horizontal_boundaries = [
        panel_bottom,
        share_top,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    append_layout_items(
        label_figure,
        annotations=[
            # 밀리지 마라 **`xanchor`·`yanchor` 를 빼면 안 된다.** 기본값 `"auto"` 는 paper 참조·
            # 화살표 없는 주석에서 **가장 가까운 변**으로 붙는다 — 위·아래 각 1/3 구간이면
            # `top`·`bottom` 이 되고 가운데 1/3 에서만 `middle` 이다. `B/N Top 5` 는 밴드가
            # 아래쪽이라 `y≈0.16` 이고, 그래서 글자 높이의 절반만큼 위로 들렸다(브라우저에서
            # 실측 −14.8px, 글자 높이 29). `생산계획 LOB` 는 가운데 구간에 들어 우연히 맞았을
            # 뿐이다 — 밴드 높이가 바뀌면 같이 어긋난다.
            {
                "x": 0.5,
                "y": (lob_y_domain[0] + lob_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>생산계획 LOB</b>",
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {
                    "size": 20,
                    "color": tokens.TEXT,
                    "family": tokens.FONT_FAMILY,
                },
            },
            # `B/N Top 5` 는 **눈에 보이는 칸**의 한가운데다. 그 칸은 막대 밴드(`yaxis2`)에 공정명이
            # 드리우는 띠까지 더한 면이라, 밴드 가운데에 두면 칸 위쪽으로 치우친다(띠 130px 의
            # 절반만큼). 칸은 아래 분류 면(`horizontal_boundaries[1]`~`[2]`)과 같은 경계를 쓴다.
            {
                "x": 0.5,
                "y": (horizontal_boundaries[1] + horizontal_boundaries[2]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>B/N Top 5</b>",
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {
                    "size": 20,
                    "color": tokens.TEXT,
                    "family": tokens.FONT_FAMILY,
                },
            },
            *_product_share_label_annotations(
                product_share_cells or {},
                product_share_basis,
                row_top=share_top,
            ),
        ],
    )
    # 구획 경계(도넛 행 위·Top5 위·LOB 위)는 굵게, 맨 아래·맨 위는 바깥 테두리가 따로 긋는다.
    section_boundaries = {1, 2, 3}
    horizontal_shapes = [
        _paper_hrule(
            y_boundary,
            color=tokens.BORDER_STRONG if boundary_index in section_boundaries else tokens.BORDER,
            width=tokens.OUTER_BORDER_WIDTH_PX
            if boundary_index in section_boundaries
            else tokens.GRID_LINE_WIDTH_PX,
            layer="above" if boundary_index in section_boundaries else "below",
        )
        for boundary_index, y_boundary in enumerate(horizontal_boundaries)
    ]
    append_layout_items(
        label_figure,
        shapes=[
            *[
                {
                    "type": "rect",
                    "x0": 0,
                    "x1": 1,
                    "y0": y0,
                    "y1": y1,
                    "xref": "paper",
                    "yref": "paper",
                    "fillcolor": tokens.SURFACE_CLASSIFICATION,
                    "line": {"width": 0},
                    "layer": "below",
                }
                for y0, y1 in (
                    (horizontal_boundaries[0], horizontal_boundaries[1]),
                    (horizontal_boundaries[1], horizontal_boundaries[2]),
                    (horizontal_boundaries[2], horizontal_boundaries[3]),
                )
            ],
            *[
                {
                    "type": "line",
                    "x0": x_boundary,
                    "x1": x_boundary,
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                    "layer": "below",
                }
                for x_boundary in (0.0, 1.0)
            ],
            *horizontal_shapes,
        ],
    )
    append_layout_items(
        month_figure,
        shapes=[
            *_paper_month_lines(len(month_labels), y0=panel_bottom, layer="below"),
            *horizontal_shapes,
        ],
    )
    add_figure_outer_border(
        label_figure,
        y0=panel_bottom,
        emphasize_bottom=True,
    )
    add_figure_outer_border(
        month_figure,
        y0=panel_bottom,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    lob_row_boundaries = (
        (lob_table_domains[0][0], tokens.OUTER_BORDER_WIDTH_PX, tokens.BORDER_STRONG),
        (lob_table_domains[1][0], tokens.GRID_LINE_WIDTH_PX, tokens.BORDER),
        (lob_table_domains[2][0], tokens.GRID_LINE_WIDTH_PX, tokens.BORDER),
    )
    lob_row_shapes = [
        _paper_hrule(boundary_y, color=boundary_color, width=boundary_width)
        for boundary_y, boundary_width, boundary_color in lob_row_boundaries
    ]
    append_layout_items(label_figure, shapes=lob_row_shapes)
    # 차트 세 칸(생산계획 LOB·B/N Top 5·제품별 비중)의 연간 Total·과거 구간 열. 표 칸은
    # 행마다 칠했지만 차트는 면이 하나라 여기서 세로 띠로 덮는다. 과거 구간에는 막대·
    # 꺾은선이 있으므로 `layer: below` 로 값 아래에 깐다.
    column_surface_shapes = _column_surface_rects(
        month_labels,
        y0=panel_bottom,
        y1=lob_table_domains[-1][0],
        year_totals=totals,
        past_month_labels=past_month_labels,
    )
    append_layout_items(month_figure, shapes=[*column_surface_shapes, *lob_row_shapes])
    add_quarter_boundaries(month_figure, month_labels, y0=panel_bottom)
    flush_layout_items(label_figure, month_figure)
    return label_figure, month_figure
