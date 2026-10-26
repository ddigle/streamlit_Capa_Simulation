# Purpose: 개조 일정 모드의 월별 확보율 그래프(개조 전·뒤 · 기준선 · 개조 비가동 막대)와 차수·대안
# 글을 계산 결과에서 순수하게 만든다.

"""개조 일정 — 그림 하나(월별 확보율 그래프)와 차수·「못 맞출 때」 글.

순수 함수다. 세션·캐시·DB 를 보지 않는다. 입력은 계산 결과(`services/modification_schedule.
ScheduleResult`)와 화면 글자(`ScheduleLabels`)뿐이고 같은 입력이면 같은 그림이다.

**월별 확보율 그래프**(`schedule_figure`) — 제약 모드 그래프(`constraint_simulation_figures.
rate_figure`)와 같은 틀이다.

- x 는 **수 축**이다(달 i 가 [i − 0.5, i + 0.5)) — 차수 막대를 W/D 구간 날짜 비례로 놓는다
  (`day_position`, 가용대수가 일할된 바로 그 좌표). 그래서 달력 11월 비가동이 12월 W/D 칸에 설 수
  있다(Cut-off 좌표 — 본문 캡션이 말한다).
- 선: 개조 전(`TEXT_MUTED` 파선) · 개조 뒤(`ACCENT` 굵게, 점은 기준 미달이면 `STATUS_SHORTAGE`) ·
  기준선(달마다 G 가 다르면 `hv` 계단) · 안전 여유나 「가장 고르게」 로 기준을 올렸으면 배치 기준선
  (점선). 오른쪽 끝 글은 글자색(`TEXT_MUTED`)이다.
- 개조 없이도 배치 기준(기준 + 안전 여유) 미달이라 비가동을 넣지 않은 달은 옅은 부족색 칠, 넣을 수
  없는 달(가장 이른 시작 앞·끝 날 상한 뒤)은 옅은 회색 칠이다(도형 `opacity` — 새 색 토큰을 두지
  않는다). 안전 여유가 있으면 풍선이 「배치 기준(기준 +n%p) 미달」 이라고 적는다 — 그 달 확보율이
  기준 자체는 넘을 수 있다.
- 아래 띠(y2): 차수마다 가로 막대 하나(`base` = 시작 위치, `x` = 길이, 글 = 대수). 겹치는 차수는
  아래 줄로 내린다.
- 달마다 보이지 않는 표적 막대(`HIT_TARGET`)가 풍선을 받는다. 누름은 받지 않는다(이 모드는 달을
  고르지 않는다).

대수는 모두 환산 대수다.
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import plotly.graph_objects as go

from capa_simulation.components.constraint_simulation_figures import (
    CHART_HEIGHT_PX,
    day_position,
    rate_text,
    signed_points,
    units_text,
)
from capa_simulation.components.month_sheet_canvas import MINUS
from capa_simulation.components.plotly_layout import (
    append_layout_items,
    figure_from_spec,
    flush_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.modification_schedule import (
    ScheduleBatch,
    ScheduleMonth,
    ScheduleResult,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.threshold_label import threshold_percent_label

__all__ = [
    "SCHEDULE_FIGURE_SCHEMA_VERSION",
    "ScheduleLabels",
    "batch_line",
    "general_text",
    "relief_points",
    "schedule_figure",
    "shortfall_lines",
]

# 그림 모양을 바꾸면 올린다 — 세션 memo 의 옛 그림을 쓰지 않게(AGENTS 5장 16).
SCHEDULE_FIGURE_SCHEMA_VERSION: Final = 2
_MARGIN_LEFT_PX: Final = 52
_MARGIN_RIGHT_PX: Final = 76
_BAND_TOP: Final = 0.14
_MAIN_BOTTOM: Final = 0.22
_BLOCKED_OPACITY: Final = 0.10
_CLOSED_OPACITY: Final = 0.06
# 배치 기준선을 기준선과 따로 그리는 차이(%p) — 이보다 작으면 같은 선이다.
_SHIFT_HIDDEN_POINTS: Final = 0.005


@dataclass(frozen=True)
class ScheduleLabels:
    """그림·글에 쓰는 화면 글자. 값으로 같고 해시된다(memo 키 원소)."""

    process_label: str
    general_percent: float | None
    """기준 확보율(%). None 이면 HOME 판정 기준(달마다)."""


# ================================================================== 글


def general_text(labels: ScheduleLabels, result: ScheduleResult) -> str:
    """기준 확보율 한 마디 — 「HOME 110%」·「HOME(월별)」·「105%」."""
    if labels.general_percent is not None:
        return f"{labels.general_percent:g}%"
    targets = {row.general_target for row in result.months}
    if len(targets) == 1:
        return f"HOME {threshold_percent_label(next(iter(targets)))}"
    return "HOME(월별)"


def _line_label(labels: ScheduleLabels, result: ScheduleResult) -> str:
    """기준선 끝 글 — 「110%」·「(월별)」. 「HOME」 은 머리 한 줄이 말한다(오른쪽 여백이 좁다 — 제약
    모드 그래프와 같다)."""
    if labels.general_percent is not None:
        return f"{labels.general_percent:g}%"
    targets = {row.general_target for row in result.months}
    if len(targets) == 1:
        return threshold_percent_label(next(iter(targets)))
    return "(월별)"


def relief_points(value: float) -> str:
    """필요한 기준 완화(비율)를 0.01%p **올림** 글자로 — 적힌 만큼 낮추면 늘 들어간다."""
    points = math.ceil(value * 10_000 - 1e-6) / 100
    return f"{max(points, 0.01):.2f}%p"


def batch_line(number: int, batch: ScheduleBatch) -> str:
    """차수 한 줄 — 「**1** · 2026-11-05 \\~ 2026-11-25 · **1대** · 26.11 17일 · 26.12 4일」."""
    shares = " · ".join(f"{month_label(month)} {days}일" for month, days in batch.shares)
    return (
        f"**{number}** · {batch.start.isoformat()} \\~ {batch.last_day.isoformat()} · "
        f"**{batch.units}대** · {shares}"
    )


def _blocked_reason(result: ScheduleResult) -> str:
    """기준을 0% 까지 낮춰도 못 넣는 까닭 한 마디(`ScheduleShortfall.cause`)."""
    shortfall = result.shortfall
    conditions = result.conditions
    cause = None if shortfall is None else shortfall.cause
    if cause == "window":
        target = "기한" if shortfall is not None and shortfall.by_deadline else "조회기간 끝"
        if result.last_day < result.first_day:
            return (
                f"{target}({result.last_day.isoformat()})이 넣을 수 있는 첫날"
                f"({result.first_day.isoformat()})보다 앞입니다"
            )
        span = (result.last_day - result.first_day).days + 1
        return (
            f"넣을 수 있는 첫날({result.first_day.isoformat()}) \\~ {target}"
            f"({result.last_day.isoformat()})이 {span}일로 개조 기간 {conditions.days}일보다 "
            "짧습니다"
        )
    if cause == "concurrent":
        return (
            f"동시 개조 상한 {conditions.concurrent}대가 막습니다 — 상한을 올리면 기준을 지키며 더 "
            "넣을 수 있습니다"
        )
    return "기준을 0% 까지 낮춰도 들어가지 않습니다(그 공정 가용 · 같은 날 가용 대수가 모자랍니다)"


def shortfall_lines(result: ScheduleResult) -> list[str]:
    """다 넣지 못했을 때의 대안 셋(C12). 다 넣었으면 빈 목록.

    완전 탐색이 마디 한도에 걸렸으면(`exact` 거짓) 「이 계산으로 찾은 범위」 라고 끝에 적는다.
    """
    shortfall = result.shortfall
    if shortfall is None:
        return []
    units = result.conditions.units
    limit = result.last_day.isoformat()
    lines = [
        (
            f"기한({limit})까지 넣을 수 있는 대수: **{shortfall.placed} / {units}대**"
            if shortfall.by_deadline
            else f"조회기간 끝({limit})까지 넣을 수 있는 대수: **{shortfall.placed} / {units}대**"
        )
    ]
    if shortfall.by_deadline:
        lines.append(
            "기한 없이 기준을 지키면 끝나는 날: "
            + (
                f"**{shortfall.finish_without_deadline.isoformat()}** "
                f"({month_label(shortfall.finish_month_without_deadline)} W/D)"
                if shortfall.finish_without_deadline is not None
                and shortfall.finish_month_without_deadline is not None
                else "조회기간 안에 다 넣지 못합니다"
            )
        )
    target = "기한" if shortfall.by_deadline else "조회기간"
    lines.append(
        f"{target} 안에 다 넣으려면 필요한 기준 완화: "
        + (
            f"**{MINUS}{relief_points(shortfall.relief)}**"
            if shortfall.relief is not None
            else _blocked_reason(result)
        )
    )
    if not shortfall.exact:
        lines.append(
            "탐색 한도에 걸려 위 수는 **이 계산으로 찾은 범위**입니다 — 실제로는 더 넣거나 "
            "덜 낮춰도 될 수 있습니다(적힌 완화만큼 낮추면 들어가는 것은 그대로입니다)."
        )
    return lines


# ================================================================== 그래프


def _percent(value: float | None) -> float | None:
    return None if value is None else value * 100


def _axis_bounds(values: Sequence[float]) -> tuple[float, float]:
    """y 축 범위 — (최솟값 − 5) 의 10 단위 내림 ~ (최댓값 + 5) 의 10 단위 올림(제약 모드와 같다)."""
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0, 100.0
    low = math.floor((min(finite) - 5) / 10) * 10
    high = math.ceil((max(finite) + 5) / 10) * 10
    return float(low), float(high if high > low else low + 10)


def _lanes(spans: Sequence[tuple[float, float]]) -> list[int]:
    """겹치는 막대를 아래 줄로 — 줄마다 마지막 끝 이후에 시작하는 첫 줄(차수는 시작 차례다)."""
    ends: list[float] = []
    chosen: list[int] = []
    for start, end in spans:
        for lane, last_end in enumerate(ends):
            if start >= last_end - 1e-9:
                ends[lane] = end
                chosen.append(lane)
                break
        else:
            ends.append(end)
            chosen.append(len(ends) - 1)
    return chosen


def _hover(row: ScheduleMonth, margin: float) -> str:
    parts = [
        f"<b>{html.escape(month_label(row.month))}</b>"
        f" · W/D {row.window_first_day.isoformat()} ~ {row.window_last_day.isoformat()}",
        f"개조 전 {rate_text(row.baseline_rate)} → 개조 뒤 {rate_text(row.rate)}",
        f"소요 {units_text(row.required)}대 · 가용 {units_text(row.available)}대 · "
        f"기준 {threshold_percent_label(row.general_target)}",
    ]
    if row.downtime_unit_days > 0:
        parts.append(
            f"개조 비가동 {MINUS}{units_text(row.downtime)}대({row.downtime_unit_days:,}대·일)"
        )
    if row.blocked:
        parts.append(
            f"개조 없이도 배치 기준(기준 {signed_points(margin)}) 미달 — 넣지 않음"
            if margin > 0
            else "개조 없이도 기준 미달 — 넣지 않음"
        )
    elif not row.open:
        parts.append("넣을 수 없는 달(시작 앞 · 기한 뒤)")
    else:
        parts.append(f"배치 기준 여유 {units_text(row.slack)}대")
    return "<br>".join(parts)


def _batch_hover(number: int, batch: ScheduleBatch) -> str:
    shares = " · ".join(f"{month_label(month)} {days}일" for month, days in batch.shares)
    return (
        f"<b>{number}차 · {batch.units}대 개조</b>"
        f"<br>{batch.start.isoformat()} ~ {batch.last_day.isoformat()} 비가동"
        f"<br>{html.escape(shares)}"
    )


def schedule_figure(result: ScheduleResult, labels: ScheduleLabels) -> go.Figure:
    """월별 확보율 그래프 — 개조 전·뒤 두 선, 기준선(과 배치 기준선), 달 칠, 차수 막대."""
    rows = result.months
    count = len(rows)
    if count == 0:
        raise ValueError("월별 확보율 그래프의 달이 비었습니다.")
    months = [row.month for row in rows]
    xs = list(range(count))
    cutoff = result.conditions.cutoff_days
    before = [_percent(row.baseline_rate) for row in rows]
    after = [_percent(row.rate) for row in rows]
    general = [row.general_target * 100 for row in rows]
    shifted = [row.threshold * 100 for row in rows]
    shows_shift = abs(result.applied_margin * 100) >= _SHIFT_HIDDEN_POINTS
    low, high = _axis_bounds(
        [value for value in (*before, *after) if value is not None]
        + general
        + (shifted if shows_shift else [])
    )

    batches = result.batches
    has_band = bool(batches)
    main_domain = [_MAIN_BOTTOM, 1.0] if has_band else [0.0, 1.0]
    spans = [
        (day_position(batch.start, months, cutoff), day_position(batch.end, months, cutoff))
        for batch in batches
    ]
    lanes = _lanes(spans)
    lane_count = max(lanes, default=0) + 1

    data: list[dict[str, Any]] = [
        {
            "type": "bar",
            "x": xs,
            "y": [high - low] * count,
            "base": [low] * count,
            "width": [1.0] * count,
            "marker": {"color": tokens.HIT_TARGET, "line": {"width": 0}},
            "customdata": [[row.month, _hover(row, result.conditions.margin)] for row in rows],
            "hovertemplate": "%{customdata[1]}<extra></extra>",
            "showlegend": False,
            "name": "",
        }
    ]
    same_general = len(set(general)) == 1
    data.append(_threshold_line(general, same=same_general, dash="dash", name="기준"))
    if shows_shift:
        data.append(
            _threshold_line(shifted, same=len(set(shifted)) == 1, dash="dot", name="배치 기준")
        )
    data.append(
        {
            "type": "scatter",
            "x": xs,
            "y": before,
            "mode": "lines",
            "line": {"color": tokens.TEXT_MUTED, "width": 2, "dash": "dash"},
            "hoverinfo": "skip",
            "name": "개조 전",
        }
    )
    data.append(
        {
            "type": "scatter",
            "x": xs,
            "y": after,
            "mode": "lines+markers",
            "line": {"color": tokens.ACCENT, "width": 3},
            "marker": {
                "color": [
                    tokens.STATUS_SHORTAGE if row.secure_after is False else tokens.ACCENT
                    for row in rows
                ],
                "size": 8,
                "line": {"color": tokens.SURFACE, "width": 1.5},
            },
            "hoverinfo": "skip",
            "name": "개조 뒤",
        }
    )
    if has_band:
        data.append(
            {
                "type": "bar",
                "orientation": "h",
                "x": [end - start for start, end in spans],
                "base": [start for start, _ in spans],
                "y": lanes,
                "width": [0.8] * len(spans),
                "yaxis": "y2",
                "marker": {
                    "color": tokens.STATUS_WARNING,
                    "line": {"color": tokens.STATUS_WARNING, "width": 1},
                },
                "text": [f"{batch.units}대" for batch in batches],
                "textposition": "inside",
                "insidetextanchor": "middle",
                "textangle": 0,
                "textfont": {"color": tokens.TEXT, "size": 11},
                "customdata": [
                    [index, _batch_hover(index, batch)] for index, batch in enumerate(batches, 1)
                ],
                "hovertemplate": "%{customdata[1]}<extra></extra>",
                "name": "개조 비가동(차수)",
            }
        )

    layout: dict[str, Any] = {
        "height": CHART_HEIGHT_PX,
        "margin": {"l": _MARGIN_LEFT_PX, "r": _MARGIN_RIGHT_PX, "t": 36, "b": 28},
        "paper_bgcolor": tokens.CHART_CANVAS,
        "plot_bgcolor": tokens.SURFACE,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
        "barmode": "overlay",
        "bargap": 0,
        "dragmode": False,
        "hovermode": "closest",
        "hoverlabel": {
            "bgcolor": tokens.SURFACE,
            "bordercolor": tokens.BORDER_STRONG,
            "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
            "align": "left",
        },
        "showlegend": True,
        "legend": {
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": 1.02,
            "yanchor": "bottom",
            "font": {"size": 11.5, "color": tokens.TEXT},
            "bgcolor": tokens.TRANSPARENT,
        },
        "xaxis": {
            "range": [-0.5, count - 0.5],
            "tickmode": "array",
            "tickvals": xs,
            "ticktext": [month_label(month) for month in months],
            "showgrid": False,
            "zeroline": False,
            "fixedrange": True,
            "tickfont": {"size": 11.5, "color": tokens.TEXT},
            "linecolor": tokens.BORDER,
            "anchor": "y2" if has_band else "y",
        },
        "yaxis": {
            "domain": main_domain,
            "range": [low, high],
            "ticksuffix": "%",
            "gridcolor": tokens.BORDER,
            "zeroline": False,
            "fixedrange": True,
            "tickfont": {"size": 11, "color": tokens.TEXT_MUTED},
        },
    }
    if has_band:
        layout["yaxis2"] = {
            "domain": [0.0, _BAND_TOP],
            "range": [lane_count - 0.5, -0.5],
            "visible": False,
            "fixedrange": True,
        }
    figure = figure_from_spec({"data": data, "layout": layout})

    shapes: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if row.blocked and row.open:
            color, opacity = tokens.STATUS_SHORTAGE, _BLOCKED_OPACITY
        elif not row.open:
            color, opacity = tokens.TEXT_MUTED, _CLOSED_OPACITY
        else:
            continue
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": index - 0.5,
                "x1": index + 0.5,
                "y0": main_domain[0],
                "y1": 1.0,
                "fillcolor": color,
                "opacity": opacity,
                "line": {"width": 0},
                "layer": "below",
            }
        )
    annotations = [
        {
            "x": count - 0.5,
            "y": general[-1],
            "xref": "x",
            "yref": "y",
            "text": html.escape(f"기준 {_line_label(labels, result)}"),
            "showarrow": False,
            "xanchor": "left",
            "yanchor": "top" if shows_shift else "middle",
            "xshift": 4,
            "font": {"size": 11, "color": tokens.TEXT_MUTED},
        }
    ]
    if shows_shift:
        annotations.append(
            {
                "x": count - 0.5,
                "y": shifted[-1],
                "xref": "x",
                "yref": "y",
                "text": html.escape(f"배치 {signed_points(result.applied_margin)}"),
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "bottom",
                "xshift": 4,
                "font": {"size": 11, "color": tokens.TEXT},
            }
        )
    append_layout_items(figure, shapes=shapes, annotations=annotations)
    flush_layout_items(figure)
    return figure


def _threshold_line(values: list[float], *, same: bool, dash: str, name: str) -> dict[str, Any]:
    count = len(values)
    return {
        "type": "scatter",
        "x": [-0.5, count - 0.5] if same else [*[x - 0.5 for x in range(count)], count - 0.5],
        "y": [values[0], values[0]] if same else [*values, values[-1]],
        "mode": "lines",
        "line": {
            "color": tokens.TEXT_MUTED,
            "width": 1.2,
            "dash": dash,
            "shape": "linear" if same else "hv",
        },
        "hoverinfo": "skip",
        "showlegend": False,
        "name": name,
    }
