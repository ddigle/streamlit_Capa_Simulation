# Purpose: 제약 시뮬레이션의 월별 확보율 그래프와 월별 계산표 캔버스를 계산 결과에서 순수하게
# 만든다.

"""제약 시뮬레이션 — 그림 둘(월별 확보율 그래프 · 월별 계산표 캔버스)과 칸 글자 서식.

순수 함수다. 세션·캐시·DB 를 보지 않는다. 입력은 계산
결과(`services/constraint_simulation.ConstraintResult`)와 화면 글자(`ConstraintLabels`)·고른 달·비중
토글·칸 누름 세대뿐이고, 같은 입력이면 같은 그림이다(세대는 그림 `layout.meta` 에만 든다 — 누를
때마다 새 요소가 되어 브라우저에 남은 옛 선택이 다음 누름을 삼키지 않는다).

**월별 확보율 그래프**(`rate_figure`)

- x 는 **수 축**이다 — 달 i 가 [i − 0.5, i + 0.5) 이고 눈금 글자는 `month_label`. 개조 비가동 막대를
  날짜 비례로 놓으려면 수 축이어야 한다(범주 축 규칙은 「26.07」 글자를 x 값으로 쓸 때의 것이고
  여기서는 글자를 x 에 쓰지 않는다).
- 선: 제약 없을 때(`TEXT_MUTED` 파선) · 기존 제품 — 제약 반영(`ACCENT` 굵게, 점은 기준 미달이면
  `STATUS_SHORTAGE`) · 제약 제품(`STATUS_WARNING`, 기간 안만 — 점은 `LINE` 테두리) · 비중대로
  (`SERIES_STANDARD` 점선, 토글 켬·기간 안만). 기준선은 달마다 G 가 다르면 `hv` 계단, 같으면
  수평선이고 제약 목표 수평선이 함께 선다. 오른쪽 끝 글(「기준 …」 `TEXT_MUTED` · 「제약 n%」
  `TEXT`)은 글자색이라 주의 색(면색)을 쓰지 않는다. 두 글은 늘 제 선 높이에 서되, 그림 칸이 가장
  낮을 때(`END_LABEL_MIN_PLOT_PX`) 두 선이 글 한 줄(`END_LABEL_GAP_PX`)보다 가까우면 위 값의 글은
  선 위로·아래 값의 글은 선 아래로 비켜 서로 덮지 않는다(값이 같으면 「제약」 이 위 —
  `end_label_anchors`).
- 그림 폭은 브라우저가 정한다(`width="stretch"`). 좁은 창에서 달 눈금이 포개지지 않게 본문이
  그림에 가장 좁은 폭(`chart_min_width_px` — 세운 달 글자 한 칸 `MONTH_SLOT_PX` × 달 수 + 좌우
  여백)을 주고 칸이 그보다 좁으면 가로로 스크롤한다(`constraint_simulation_view.top_row_style`).
  눈금을 솎지 않는다 — 서버는 칸 폭을 모르고, 넓은 창에서는 모든 달이 읽힌다.
- 아래 띠(y2): 개조 비가동 가로 막대 trace **하나**(`base` = 시작 위치, `x` = 길이). 날 → x 는 그
  날이 든 보이는 달 j 의 **W/D 구간**에서 `j − 0.5 + (날 − 첫날) ÷ 일수` 다 — 가용대수가 일할된 바로
  그 좌표다. 첫 달 앞은 −0.5, 마지막 달 뒤는 n − 0.5 로 자른다. 겹치는 창은 아래 줄로 내린다. 신규
  대기가 있으면 같은 띠에 빗금 막대 trace(「신규 대기」)가 하나 더 서고 개조 창 뒤 줄 자리를 잇는다.
- 제약 기간 칠과 고른 달 띠는 도형 둘(`append_layout_items` → `flush_layout_items`) — 새 색 토큰을
  더하지 않고 기존 토큰에 도형 `opacity` 를 준다(14-5).
- **달 고르기**(D9): 달마다 보이지 않는 표적 막대(`HIT_TARGET`, `customdata = (달, 풍선)`) 하나가
  풍선과 누름을 받는다. 선은 `hoverinfo: skip` 이라 누름이 표적으로 간다. `keep_unselected_opaque`
  로 눌러도 흐려지지 않는다.

**월별 계산표**(`build_sheet_canvas`) — 공정 Capa 상세·Static 대비 일정 비교 시트와 같은
`month_sheet_canvas` 엔진(라벨 260px · 달 100px). 구획은 공정 전체 → 제약 제품 → 개조(켬일 때) →
기존 제품. 기준(제약 칸은 제약 목표) 미달 칸은 부족색 면(`STATUS_SHORTAGE` — 공정 Capa 상세 ① 판정
칸과 같은 꼴, 글자는 본문색이라 두 테마에서 읽힌다), 줄어든 값(개조 중 비가동 · 제약 없을 때 대비
−)은 감소 글자색(`DELTA_DECREASE`), 기간 안 달 머리는 옅은 칠(`header_hook`), 고른 달은 열
테두리(`finish_hook`)다.

보유 제약 설비·「신규 설비는 개조 없이」 가 걸리면(`ConstraintConditions.splits_dedicated`) 전용
대수를 `FILL_ORDER` 차례(지금 「신규 · 보유 · 개조」)로 나눠 보인다(`dedicated_split_text`) —
계산표 공정 전체 구획에 「들어오는 신규 설비」, 개조 구획에 「늘어난 전용 대수」·「신규
설비로」·「보유 제약 설비로」(`FILL_ORDER` 차례)·「신규 대기」 행, 배정 칸·표적 풍선에 구성 한
줄(신규 대기가 있으면 그 줄도). 걸리지 않으면 1판 그림 그대로다.

대수는 모두 환산 대수다(가용이 호기별 환산비를 곱한 값 — `services/constraint_simulation.py`).
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, NamedTuple

import plotly.graph_objects as go

from capa_simulation.components.home_figure_common import keep_unselected_opaque
from capa_simulation.components.month_sheet_canvas import (
    EMPTY,
    HEADER_HEIGHT_PX,
    KIND_HEADER,
    KIND_VALUE,
    MINUS,
    VALUE_ROW_HEIGHT_PX,
    Cell,
    MonthLayers,
    Row,
    label_figure,
    month_figure,
    stack_rows,
    title_row,
)
from capa_simulation.components.plotly_layout import (
    append_layout_items,
    figure_from_spec,
    flush_layout_items,
)
from capa_simulation.design import tokens
from capa_simulation.services.constraint_simulation import (
    FILL_NEW,
    FILL_ORDER,
    FILL_OWNED,
    ConstraintConditions,
    ConstraintMonth,
    ConstraintResult,
    FillSource,
    ModificationWindow,
    NewUnit,
    NewUnitAssignment,
    secure,
)
from capa_simulation.services.korean_particle import with_object_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.threshold_label import threshold_percent_label
from capa_simulation.services.wd_window import wd_window

__all__ = [
    "CHART_HEIGHT_PX",
    "CONSTRAINT_FIGURE_SCHEMA_VERSION",
    "END_LABEL_GAP_PX",
    "END_LABEL_MIN_PLOT_PX",
    "MONTH_SLOT_PX",
    "ROW_IDS",
    "ConstraintLabels",
    "SheetCanvas",
    "build_sheet_canvas",
    "chart_min_width_px",
    "chart_point_month",
    "day_position",
    "dedicated_split_text",
    "end_label_anchors",
    "free_parts",
    "general_label",
    "new_unit_fate",
    "month_name",
    "rate_figure",
    "rate_text",
    "signed_points",
    "units_text",
    "waiting_text",
]

# 그림 모양을 바꾸면 올린다 — 세션 memo 의 옛 그림을 쓰지 않게(AGENTS 5장 16).
CONSTRAINT_FIGURE_SCHEMA_VERSION: Final = 7
CHART_HEIGHT_PX: Final = 340
# 그래프 좌우 여백(px) — 왼쪽은 y 눈금, 오른쪽은 끝 글 「기준 …」 · 「제약 n%」 자리.
_MARGIN_LEFT_PX: Final = 52
_MARGIN_RIGHT_PX: Final = 76
# 세운 달 눈금 한 칸(px). 세운 「26.07」(11.5px 글씨)의 폭이 12px 이라 1px 를 띄운다 — 사본 앱
# 390px 창에서는 칸이 6.6px 로 줄어 30개월 글자가 검은 띠로 포개졌다(2026-10-25 E2E). 1280px 창 ·
# 사이드바 펼침의 30개월(칸 13.1px)은 이 폭 안이라 스크롤이 생기지 않는다.
MONTH_SLOT_PX: Final = 13
# 오른쪽 끝 두 글의 비켜 놓기. 그림 칸(본 y 축) 높이는 범례 줄 수에 따라 바뀐다(사본 앱 1440px ·
# 1280px 창 160px, 390px 창 130px — 2026-10-25 E2E). 그보다 낮게 잡아 가깝다고 보는 쪽으로 기운다 —
# 비켜 놓은 두 글은 어떤 높이에서도 겹치지 않는다. 글 한 줄 높이는 15~16px 이다.
END_LABEL_MIN_PLOT_PX: Final = 100
END_LABEL_GAP_PX: Final = 18
_SAME_PERCENT_TOLERANCE: Final = 1e-6
# 아래 띠(개조 비가동 막대)와 본 그림의 y 도메인.
_BAND_TOP: Final = 0.12
_MAIN_BOTTOM: Final = 0.2
_PERIOD_OPACITY: Final = 0.08
_SELECTED_OPACITY: Final = 0.10
# 값 줄 라벨을 구획 제목보다 들인다(Static 대비 일정 비교 시트와 같다).
_VALUE_LABEL_INDENT_PX: Final = 12
# 「제약 없을 때 대비」 칸이 빈칸인 차이(%p).
_DELTA_HIDDEN_POINTS: Final = 0.05

_FILL_ROW_IDS: Final[Mapping[FillSource, str]] = {
    FILL_OWNED: "owned_increment",
    FILL_NEW: "new_increment",
}
"""채우는 몫마다의 계산표 행 id — 두 행은 `FILL_ORDER` 차례로 선다."""

ROW_IDS: Final = (
    "header",
    "title:process",
    "required",
    "available",
    "new_starts",
    "baseline_rate",
    "title:product",
    "constrained_demand",
    "need",
    "allocated",
    "constrained_rate",
    "title:modification",
    "growth",
    *(_FILL_ROW_IDS[source] for source in FILL_ORDER),
    "increment",
    "downtime",
    "waiting",
    "title:existing",
    "existing_demand",
    "existing_available",
    "existing_rate",
    "rate_delta",
    "proportional_rate",
)
"""계산표 행 id 의 차례(개조·비중 행은 켬일 때만, 「들어오는 신규」·「늘어난
전용」·「신규로」·「보유로」·「신규 대기」 는 그 옵션이 걸릴 때만 선다). 「신규로」·「보유로」 는
`FILL_ORDER` 차례다(채우는 차례가 곧 위에서 아래)."""


@dataclass(frozen=True)
class ConstraintLabels:
    """그림·글에 쓰는 화면 글자. 값으로 같고 해시된다(memo 키 원소)."""

    process: str
    """원본 공정명."""

    process_label: str
    """공정 표시명."""

    product: str
    """제약 제품(제품정보)."""

    target_percent: int
    """제약 확보율(%)."""

    general_percent: float | None
    """기준 확보율(%). None 이면 HOME 판정 기준(달마다)."""


class SheetCanvas(NamedTuple):
    """계산표 캔버스 한 쌍. 두 Figure 는 높이가 같고 행이 맞는다."""

    labels: go.Figure
    months: go.Figure
    height: int
    row_ids: tuple[str, ...]


# ================================================================== 서식


def units_text(value: float | None) -> str:
    """대수 글자 — 정수에 가까우면(0.005 안) 정수, 아니면 소수 둘째 자리. 없으면 「—」."""
    if value is None or not math.isfinite(value):
        return EMPTY
    rounded = round(value, 2)
    if abs(rounded - round(rounded)) < 0.005:
        whole = int(round(rounded))
        return f"{MINUS}{abs(whole):,}" if whole < 0 else f"{whole:,}"
    text = f"{abs(rounded):,.2f}"
    return f"{MINUS}{text}" if rounded < 0 else text


def rate_text(value: float | None) -> str:
    """확보율 글자 — 「100.5%」(소수 첫째 자리). 없으면 「—」."""
    if value is None or not math.isfinite(value):
        return EMPTY
    return f"{value * 100:.1f}%"


def signed_points(value: float | None) -> str:
    """%p 차이 — 「+1.2%p」·「−13.8%p」. 없으면 「—」."""
    if value is None or not math.isfinite(value):
        return EMPTY
    points = round(value * 100, 1)
    if points > 0:
        return f"+{points:.1f}%p"
    if points < 0:
        return f"{MINUS}{abs(points):.1f}%p"
    return "0.0%p"


def month_name(month: int) -> str:
    """「27년 6월」 — 개조 몫을 적는 꼴."""
    return f"{month // 100 % 100:02d}년 {month % 100}월"


def free_parts(conditions: ConstraintConditions, owned: str, new: str) -> list[str]:
    """개조 없이 채우는 몫의 글을 `FILL_ORDER` 차례로 — 걸린 옵션의 것만(보유 글 `owned`, 신규 글
    `new`). 차례를 바꾸면 모든 구성 글이 따라간다."""
    parts: list[str] = []
    for source in FILL_ORDER:
        if source == FILL_OWNED:
            if conditions.uses_owned_units:
                parts.append(owned)
        elif conditions.uses_new_units:
            parts.append(new)
    return parts


def dedicated_split_text(row: ConstraintMonth, conditions: ConstraintConditions) -> str:
    """전용 대수의 구성 — 「전용 10대 = 신규 3 · 보유 4 · 개조 3」(`FILL_ORDER` 차례). 걸린 옵션의
    몫만 적는다. 나눠 보이지 않는 조건(`splits_dedicated` 거짓)이나 전용 0 이면 빈 글자."""
    if not conditions.splits_dedicated or row.dedicated <= 0:
        return ""
    parts = free_parts(conditions, f"보유 {row.owned_dedicated}", f"신규 {row.new_dedicated}")
    parts.append(f"개조 {row.modified_dedicated}")
    return f"전용 {row.dedicated}대 = {' · '.join(parts)}"


def waiting_text(item: NewUnitAssignment) -> str:
    """신규 대기 날짜 글 — 「2027-06-10 ~ 2027-06-23 대기 14일」, 기여 시작이 곧 그 달 W/D 첫날이면
    「대기 없음(W/D 첫날 기여 시작)」."""
    if item.days <= 0:
        return "대기 없음(W/D 첫날 기여 시작)"
    return f"{item.start.isoformat()} ~ {item.last_day.isoformat()} 대기 {item.days}일"


def general_label(labels: ConstraintLabels, result: ConstraintResult) -> str:
    """기준 확보율 한 마디 — 「HOME 110%」·「HOME(월별)」·「105%」."""
    if labels.general_percent is not None:
        return f"{labels.general_percent:g}%"
    targets = {row.general_target for row in result.months}
    if len(targets) == 1:
        return f"HOME {threshold_percent_label(next(iter(targets)))}"
    return "HOME(월별)"


def _line_label(labels: ConstraintLabels, result: ConstraintResult) -> str:
    """그래프 기준선 끝 글 — 「110%」·「(월별)」. 「HOME」 은 머리 한 줄이 말한다(오른쪽 여백이
    좁다)."""
    if labels.general_percent is not None:
        return f"{labels.general_percent:g}%"
    targets = {row.general_target for row in result.months}
    if len(targets) == 1:
        return threshold_percent_label(next(iter(targets)))
    return "(월별)"


# ================================================================== 그래프


def day_position(day: date, months: Sequence[int], cutoff_days: int) -> float:
    """날 → x 위치. 그 날이 든 보이는 달 j 의 W/D 구간에서 `j − 0.5 + (날 − 첫날) ÷ 일수`.

    보이는 달의 어느 W/D 구간에도 들지 않으면 그 뒤 첫 구간의 왼쪽 끝(없으면 마지막 달의 오른쪽
    끝)이다 — 첫 달 앞은 −0.5 로 잘린다.
    """
    for index, month in enumerate(months):
        window = wd_window(int(month), cutoff_days)
        if window.first_day <= day <= window.boundary_end:
            return index - 0.5 + (day - window.first_day).days / window.days
        if day < window.first_day:
            return index - 0.5
    return len(months) - 0.5


def _window_lanes(
    spans: Sequence[tuple[float, float]], lanes: list[float] | None = None
) -> list[int]:
    """겹치는 막대를 아래 줄로 내린다 — 줄마다 마지막 끝보다 늦게 시작하는 첫 줄. `lanes` 를 주면 그
    줄 끝(앞 막대들이 채운 자리)을 이어 쓰고 고친다."""
    lanes = [] if lanes is None else lanes
    chosen: list[int] = []
    for start, end in spans:
        for lane, last_end in enumerate(lanes):
            if start >= last_end - 1e-9:
                lanes[lane] = end
                chosen.append(lane)
                break
        else:
            lanes.append(end)
            chosen.append(len(lanes) - 1)
    return chosen


def _window_hover(window: ModificationWindow) -> str:
    return (
        f"<b>{html.escape(month_name(window.month))} 몫 {window.units}대 개조</b>"
        f"<br>{window.start.isoformat()} ~ {window.last_day.isoformat()} 비가동"
    )


def _first_overlapped_month(window: ModificationWindow, result: ConstraintResult) -> int:
    """개조 막대를 누르면 고를 달 — 그 창의 비가동이 든 첫 보이는 달(없으면 그 몫의 달)."""
    for row in result.months:
        if any(share.source_month == window.month for share in row.downtime_shares):
            return row.month
    return window.month


def _waiting_hover(item: NewUnitAssignment) -> str:
    return (
        f"<b>{html.escape(month_name(item.month))} 몫 · 신규 {html.escape(item.unit)} "
        f"{units_text(item.units)}대 대기</b><br>{html.escape(waiting_text(item))} — 셋업 때부터 "
        "제약용이라 기존 제품이 못 씀"
    )


def _first_waiting_month(item: NewUnitAssignment, result: ConstraintResult) -> int:
    """신규 대기 막대를 누르면 고를 달 — 그 대기가 든 첫 보이는 달(없으면 그 몫의 달)."""
    for row in result.months:
        if any(
            share.source_month == item.month and share.unit == item.unit
            for share in row.waiting_shares
        ):
            return row.month
    return item.month


def _hit_hover(row: ConstraintMonth, conditions: ConstraintConditions) -> str:
    parts = [
        f"<b>{html.escape(month_label(row.month))}</b>",
        f"기존 {rate_text(row.existing_rate)}",
        f"제약 없을 때 {rate_text(row.baseline_rate)}",
    ]
    if row.in_period and row.constrained_rate is not None:
        parts.append(f"제약 {rate_text(row.constrained_rate)}")
    text = " · ".join(parts)
    split = dedicated_split_text(row, conditions) if row.in_period else ""
    if split:
        text += f"<br>{html.escape(split)}"
    if row.downtime > 0:
        text += f"<br>개조 중 비가동 {MINUS}{units_text(row.downtime)}대"
    if row.waiting > 0:
        text += f"<br>신규 대기 {MINUS}{units_text(row.waiting)}대"
    return text + "<br>누르면 이 달 계산"


def _percent(value: float | None) -> float | None:
    return None if value is None else value * 100


def chart_min_width_px(month_count: int) -> int:
    """그래프에 주는 가장 좁은 폭(px) — 세운 달 눈금이 이웃과 포개지지 않는 폭(좌우 여백 + 달 수 ×
    `MONTH_SLOT_PX`). 본문 칸이 이보다 좁으면 가로로 스크롤한다."""
    return _MARGIN_LEFT_PX + _MARGIN_RIGHT_PX + max(int(month_count), 1) * MONTH_SLOT_PX


def end_label_anchors(general: float, target: float, *, low: float, high: float) -> tuple[str, str]:
    """오른쪽 끝 두 글(「기준 …」, 「제약 n%」)의 `yanchor`.

    그림 칸이 `END_LABEL_MIN_PLOT_PX` 일 때 두 선이 `END_LABEL_GAP_PX` 보다 가까우면 큰 값의 글은 선
    위(`bottom`)·작은 값의 글은 선 아래(`top`)에 선다 — 두 글이 맞닿을 수는 있어도 덮지 않는다(값이
    같으면 「제약」 이 위). 멀면 둘 다 선 가운데(`middle`)다.
    """
    span = high - low
    if span <= 0 or abs(target - general) * END_LABEL_MIN_PLOT_PX / span >= END_LABEL_GAP_PX:
        return "middle", "middle"
    # 같은 값도 부동소수 꼬리(110 · 110.00000000000001)가 다를 수 있다 — 그 차이는 같다고 본다.
    if target >= general - _SAME_PERCENT_TOLERANCE:
        return "top", "bottom"
    return "bottom", "top"


def _axis_bounds(values: Sequence[float]) -> tuple[float, float]:
    """y 축 범위 — (최솟값 − 5) 의 10 단위 내림 ~ (최댓값 + 5) 의 10 단위 올림(초안과 같다)."""
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0, 100.0
    low = math.floor((min(finite) - 5) / 10) * 10
    high = math.ceil((max(finite) + 5) / 10) * 10
    return float(low), float(high if high > low else low + 10)


def rate_figure(
    result: ConstraintResult,
    labels: ConstraintLabels,
    *,
    selected_month: int | None,
    show_proportional: bool,
    generation: int = 0,
) -> go.Figure:
    """월별 확보율 그래프 — 선 넷(비중은 토글), 기준·제약 선, 제약 기간 칠, 고른 달 띠, 개조 비가동
    막대."""
    rows = result.months
    months = [row.month for row in rows]
    count = len(rows)
    if count == 0:
        raise ValueError("월별 확보율 그래프의 달이 비었습니다.")
    xs = list(range(count))
    cutoff = result.conditions.cutoff_days
    target_percent = float(labels.target_percent)

    baseline = [_percent(row.baseline_rate) for row in rows]
    existing = [_percent(row.existing_rate) for row in rows]
    constrained = [_percent(row.constrained_rate) if row.in_period else None for row in rows]
    proportional = [
        _percent(row.proportional_existing_rate) if row.in_period else None for row in rows
    ]
    general = [row.general_target * 100 for row in rows]
    shown = [*baseline, *existing, *constrained, *(proportional if show_proportional else [])]
    low, high = _axis_bounds(
        [value for value in shown if value is not None] + general + [target_percent]
    )

    windows = result.windows
    waits = [item for item in result.assignments if item.days > 0]
    has_band = bool(windows) or bool(waits)
    main_domain = [_MAIN_BOTTOM, 1.0] if has_band else [0.0, 1.0]
    spans = [
        (day_position(window.start, months, cutoff), day_position(window.end, months, cutoff))
        for window in windows
    ]
    wait_spans = [
        (day_position(item.start, months, cutoff), day_position(item.end, months, cutoff))
        for item in waits
    ]
    lane_ends: list[float] = []
    lanes = _window_lanes(spans, lane_ends)
    wait_lanes = _window_lanes(wait_spans, lane_ends)
    lane_count = max([*lanes, *wait_lanes], default=0) + 1

    data: list[dict[str, Any]] = [
        {
            "type": "bar",
            "x": xs,
            "y": [high - low] * count,
            "base": [low] * count,
            "width": [1.0] * count,
            "marker": {"color": tokens.HIT_TARGET, "line": {"width": 0}},
            "customdata": [[row.month, _hit_hover(row, result.conditions)] for row in rows],
            "hovertemplate": "%{customdata[1]}<extra></extra>",
            "showlegend": False,
            "name": "",
        }
    ]
    same_general = len(set(general)) == 1
    data.append(
        {
            "type": "scatter",
            "x": [-0.5, count - 0.5] if same_general else [*[x - 0.5 for x in xs], count - 0.5],
            "y": [general[0], general[0]] if same_general else [*general, general[-1]],
            "mode": "lines",
            "line": {
                "color": tokens.TEXT_MUTED,
                "width": 1.2,
                "dash": "dash",
                "shape": "linear" if same_general else "hv",
            },
            "hoverinfo": "skip",
            "showlegend": False,
            "name": "기준",
        }
    )
    data.append(
        {
            "type": "scatter",
            "x": [-0.5, count - 0.5],
            "y": [target_percent, target_percent],
            "mode": "lines",
            "line": {"color": tokens.STATUS_WARNING, "width": 1.2, "dash": "dot"},
            "hoverinfo": "skip",
            "showlegend": False,
            "name": "제약 목표",
        }
    )
    data.append(
        {
            "type": "scatter",
            "x": xs,
            "y": baseline,
            "mode": "lines",
            "line": {"color": tokens.TEXT_MUTED, "width": 2, "dash": "dash"},
            "hoverinfo": "skip",
            "name": "제약 없을 때(공정 전체)",
        }
    )
    if show_proportional:
        data.append(
            {
                "type": "scatter",
                "x": xs,
                "y": proportional,
                "mode": "lines",
                "line": {"color": tokens.SERIES_STANDARD, "width": 1.8, "dash": "dot"},
                "hoverinfo": "skip",
                "name": "기존 제품 — 비중대로 나눴을 때",
            }
        )
    data.append(
        {
            "type": "scatter",
            "x": xs,
            "y": constrained,
            "mode": "lines+markers",
            "line": {"color": tokens.STATUS_WARNING, "width": 2.4},
            # 주의 색은 면색이라 밝은 그림 면에서 2.3:1 이다 — 점마다 `LINE` 테두리를 둘러 점이 그림
            # 요소 대비(3:1)를 넘게 한다(새 색 토큰을 두지 않는다).
            "marker": {
                "color": tokens.STATUS_WARNING,
                "size": 7,
                "line": {"color": tokens.LINE, "width": 1},
            },
            "hoverinfo": "skip",
            "name": "제약 제품",
        }
    )
    data.append(
        {
            "type": "scatter",
            "x": xs,
            "y": existing,
            "mode": "lines+markers",
            "line": {"color": tokens.ACCENT, "width": 3},
            "marker": {
                "color": [
                    tokens.STATUS_SHORTAGE if row.existing_secure is False else tokens.ACCENT
                    for row in rows
                ],
                "size": 8,
                "line": {"color": tokens.SURFACE, "width": 1.5},
            },
            "hoverinfo": "skip",
            "name": "기존 제품 — 제약 반영",
        }
    )
    if windows:
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
                "text": [f"{window.units}대" for window in windows],
                "textposition": "inside",
                "insidetextanchor": "middle",
                "textangle": 0,
                "textfont": {"color": tokens.TEXT, "size": 11},
                "customdata": [
                    [_first_overlapped_month(window, result), _window_hover(window)]
                    for window in windows
                ],
                "hovertemplate": "%{customdata[1]}<extra></extra>",
                "name": "개조 비가동",
            }
        )
    if waits:
        # 신규 대기 — 개조 비가동과 같은 띠에 같은 색의 빗금(새 색 토큰을 두지 않는다).
        data.append(
            {
                "type": "bar",
                "orientation": "h",
                "x": [end - start for start, end in wait_spans],
                "base": [start for start, _ in wait_spans],
                "y": wait_lanes,
                "width": [0.8] * len(wait_spans),
                "yaxis": "y2",
                "marker": {
                    "color": tokens.SURFACE,
                    "line": {"color": tokens.STATUS_WARNING, "width": 1},
                    "pattern": {"shape": "/", "fgcolor": tokens.STATUS_WARNING, "solidity": 0.35},
                },
                "text": [f"{units_text(item.units)}대" for item in waits],
                "textposition": "inside",
                "insidetextanchor": "middle",
                "textangle": 0,
                "textfont": {"color": tokens.TEXT, "size": 11},
                "customdata": [
                    [_first_waiting_month(item, result), _waiting_hover(item)] for item in waits
                ],
                "hovertemplate": "%{customdata[1]}<extra></extra>",
                "name": "신규 대기",
            }
        )

    ticktext = [
        f"<b>{month_label(row.month)}</b>" if row.in_period else month_label(row.month)
        for row in rows
    ]
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
            "ticktext": ticktext,
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
        "meta": {"generation": int(generation)},
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
    period = [index for index, row in enumerate(rows) if row.in_period]
    if period:
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": period[0] - 0.5,
                "x1": period[-1] + 0.5,
                "y0": main_domain[0],
                "y1": 1.0,
                "fillcolor": tokens.STATUS_WARNING,
                "opacity": _PERIOD_OPACITY,
                "line": {"width": 0},
                "layer": "below",
            }
        )
    if selected_month is not None and selected_month in months:
        index = months.index(selected_month)
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": index - 0.5,
                "x1": index + 0.5,
                "y0": main_domain[0],
                "y1": 1.0,
                "fillcolor": tokens.ACCENT,
                "opacity": _SELECTED_OPACITY,
                "line": {"width": 0},
                "layer": "below",
            }
        )
    general_anchor, target_anchor = end_label_anchors(
        general[-1], target_percent, low=low, high=high
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
            "yanchor": general_anchor,
            "xshift": 4,
            "font": {"size": 11, "color": tokens.TEXT_MUTED},
        },
        {
            "x": count - 0.5,
            "y": target_percent,
            "xref": "x",
            "yref": "y",
            "text": html.escape(f"제약 {labels.target_percent}%"),
            "showarrow": False,
            "xanchor": "left",
            "yanchor": target_anchor,
            "xshift": 4,
            # 글자는 본문색이다 — 주의 색(면색) 11px 글자는 두 테마 모두 4.5:1 에 못 미쳤다.
            "font": {"size": 11, "color": tokens.TEXT},
        },
    ]
    append_layout_items(figure, shapes=shapes, annotations=annotations)
    flush_layout_items(figure)
    keep_unselected_opaque(figure)
    return figure


def chart_point_month(selection_state: object) -> int | None:
    """그래프 선택 상태(`{"selection": {"points": [...]}}`)에서 누른 점의 달(`customdata[0]`).

    빈 선택(같은 점을 다시 눌러 풀거나 더블클릭)·표적이 아닌 점이면 None — 보던 달 그대로다.
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
        if not isinstance(data, Sequence) or isinstance(data, str) or not data:
            continue
        month = data[0]
        if isinstance(month, (int, float)) and not isinstance(month, bool):
            return int(month)
    return None


# ================================================================== 계산표


def build_sheet_canvas(
    result: ConstraintResult,
    labels: ConstraintLabels,
    *,
    selected_month: int | None,
    show_proportional: bool,
    generation: int = 0,
) -> SheetCanvas:
    """월별 계산표의 라벨 Figure · 월 Figure."""
    rows_in = result.months
    axis = [row.month for row in rows_in]
    if not axis:
        raise ValueError("월별 계산표의 달이 비었습니다.")
    target = labels.target_percent
    conditions = result.conditions
    rows: list[Row] = [
        Row(
            "header",
            KIND_HEADER,
            HEADER_HEIGHT_PX,
            label="구분 · 환산 대수",
            label_bold=True,
            label_fill=tokens.HEADER_BACKGROUND,
            month_fill=tokens.HEADER_BACKGROUND,
            clickable=False,
        ),
        title_row("process", f"공정 전체 · {labels.process_label}", "설비 일정 기준 · 단축 전"),
        _row("required", "소요대수", rows_in, lambda row: Cell(units_text(row.required))),
        _row(
            "available", "가용대수 (개조 전)", rows_in, lambda row: Cell(units_text(row.available))
        ),
    ]
    if conditions.uses_new_units:
        rows.append(
            _row(
                "new_starts",
                "들어오는 신규 설비 (기준일 이후)",
                rows_in,
                lambda row: _new_starts_cell(row, result),
            )
        )
    rows += [
        _row(
            "baseline_rate",
            "확보율 — 제약 없을 때",
            rows_in,
            lambda row: Cell(
                rate_text(row.baseline_rate),
                fill=_shortage_fill(row.baseline_secure),
                bold=row.baseline_secure is False,
            ),
        ),
        title_row("product", f"제약 제품 · {labels.product}", "제약 기간 안만"),
        _row("constrained_demand", "소요대수", rows_in, _constrained_demand_cell),
        _row(
            "need",
            f"필요 대수 (× 제약 {target}%, 올림)",
            rows_in,
            lambda row: _need_cell(row, target),
        ),
        _row(
            "allocated",
            "배정 가용 (전용)",
            rows_in,
            lambda row: _allocated_cell(row, conditions),
        ),
        _row(
            "constrained_rate",
            "확보율",
            rows_in,
            lambda row: Cell(
                rate_text(row.constrained_rate) if row.in_period else "",
                muted=not row.in_period,
                fill=_shortage_fill(row.met),
                bold=row.met is False,
            ),
        ),
    ]
    if conditions.modifies:
        rows.append(title_row("modification", "개조", "그 달 W/D 일할 · 환산 대수"))
        if conditions.splits_dedicated:
            rows.append(
                _row(
                    "growth",
                    "늘어난 전용 대수 (그 달)",
                    rows_in,
                    lambda row: _count_cell(row.growth, bold=True),
                )
            )
        for source in FILL_ORDER:
            if source == FILL_OWNED:
                if conditions.uses_owned_units:
                    rows.append(
                        _row(
                            _FILL_ROW_IDS[FILL_OWNED],
                            "보유 제약 설비로",
                            rows_in,
                            lambda row: _count_cell(row.owned_increment),
                        )
                    )
            elif conditions.uses_new_units:
                rows.append(
                    _row(
                        _FILL_ROW_IDS[FILL_NEW],
                        "신규 설비로 (개조 없음)",
                        rows_in,
                        lambda row: _count_cell(row.new_increment),
                    )
                )
        rows += [
            _row(
                "increment",
                "개조에 들어가는 대수 (그 달 몫)",
                rows_in,
                lambda row: Cell(
                    str(row.increment) if row.increment > 0 else "",
                    bold=row.increment > 0,
                ),
            ),
            _row("downtime", "개조 중 비가동 (환산 대수)", rows_in, _downtime_cell),
        ]
        if conditions.uses_new_units:
            rows.append(_row("waiting", "신규 대기 (환산 대수)", rows_in, _waiting_cell))
    rows += [
        title_row("existing", "기존 제품", "남는 몫 ÷ 기존 소요"),
        _row(
            "existing_demand",
            "소요대수",
            rows_in,
            lambda row: Cell(units_text(row.existing_demand)),
        ),
        _row("existing_available", "가용대수 (남는 몫)", rows_in, _existing_available_cell),
        _row(
            "existing_rate",
            "확보율 — 제약 반영",
            rows_in,
            lambda row: Cell(
                rate_text(row.existing_rate),
                bold=True,
                fill=_shortage_fill(row.existing_secure),
            ),
        ),
        _row("rate_delta", "제약 없을 때 대비 (%p)", rows_in, _delta_cell),
    ]
    if show_proportional:
        rows.append(
            _row("proportional_rate", "확보율 — 비중대로 나눴을 때", rows_in, _proportional_cell)
        )

    height = stack_rows(rows)
    period = [index for index, row in enumerate(rows_in) if row.in_period]
    header = rows[0]
    header_bottom = height - header.top - header.height

    def header_hook(layers: MonthLayers) -> None:
        for index in period:
            layers.below.append(
                {
                    "type": "rect",
                    "xref": "x",
                    "yref": "y",
                    "x0": index,
                    "x1": index + 1,
                    "y0": header_bottom,
                    "y1": header_bottom + header.height,
                    "fillcolor": tokens.STATUS_WARNING,
                    "opacity": 0.22,
                    "line": {"width": 0},
                    "layer": "below",
                }
            )

    def finish_hook(layers: MonthLayers) -> None:
        if selected_month is None or selected_month not in axis:
            return
        index = axis.index(selected_month)
        edge = 1 / tokens.MONTH_COLUMN_WIDTH_PX
        layers.above.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "y",
                "x0": index + edge,
                "x1": index + 1 - edge,
                "y0": 1,
                "y1": height - 1,
                "fillcolor": tokens.TRANSPARENT,
                "line": {"color": tokens.ACCENT, "width": 2},
                "layer": "above",
            }
        )

    label_fig = label_figure(rows, height)
    month_fig = month_figure(
        rows,
        axis,
        height,
        header_hook=header_hook,
        finish_hook=finish_hook,
        meta={"generation": int(generation)},
    )
    flush_layout_items(label_fig, month_fig)
    keep_unselected_opaque(month_fig)
    return SheetCanvas(
        labels=label_fig,
        months=month_fig,
        height=height,
        row_ids=tuple(row.row_id for row in rows),
    )


def _row(
    row_id: str,
    label: str,
    rows: Sequence[ConstraintMonth],
    make: Callable[[ConstraintMonth], Cell],
) -> Row:
    row = Row(
        row_id,
        KIND_VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=label,
        label_indent=_VALUE_LABEL_INDENT_PX,
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    for index, month_row in enumerate(rows):
        cell = make(month_row)
        if not cell.hover:
            cell.hover = (
                f"<b>{html.escape(month_label(month_row.month))}</b> · {html.escape(label)}"
            )
        row.cells[index] = cell
    return row


def _shortage_fill(secure: bool | None) -> str | None:
    """기준(또는 제약 목표)에 못 미친 칸의 면 — 부족색(공정 Capa 상세 ① 판정 칸과 같은 꼴, 글자는
    본문 색이라 두 테마에서 읽힌다). 판정이 없거나 지키면 칠하지 않는다."""
    return tokens.STATUS_SHORTAGE if secure is False else None


def _head(row: ConstraintMonth) -> str:
    return f"<b>{html.escape(month_label(row.month))}</b>"


def _constrained_demand_cell(row: ConstraintMonth) -> Cell:
    if row.in_period:
        return Cell(units_text(row.constrained_demand))
    hover = f"{_head(row)} · 제약 기간 밖"
    if row.product_demand > 0:
        hover += f" — 원 소요 {units_text(row.product_demand)}대는 기존 제품에 셉니다"
    return Cell("", muted=True, hover=hover)


def _need_cell(row: ConstraintMonth, target: int) -> Cell:
    if not row.in_period:
        return Cell("", muted=True, hover=f"{_head(row)} · 제약 기간 밖")
    product = row.constrained_demand * target / 100
    return Cell(
        str(row.need),
        hover=(
            f"{_head(row)} · {units_text(row.constrained_demand)} × {target}% = "
            f"{product:.2f} → {row.need}대"
        ),
    )


def _allocated_cell(row: ConstraintMonth, conditions: ConstraintConditions) -> Cell:
    if not row.in_period:
        return Cell("", muted=True, hover=f"{_head(row)} · 제약 기간 밖")
    split = dedicated_split_text(row, conditions)
    tail = f"<br>{html.escape(split)}" if split else ""
    if row.short:
        return Cell(
            str(row.allocated),
            bold=True,
            fill=tokens.STATUS_SHORTAGE,
            hover=(
                f"{_head(row)} · 가용이 모자라 필요 {row.dedicated}대 중 {row.allocated}대만 배정"
                + tail
            ),
        )
    if row.dedicated > row.need:
        note = (
            f"전용 {row.dedicated}대는 기간 안에서 그대로 남습니다"
            if split
            else f"이미 개조한 {row.dedicated}대는 전용으로 남습니다"
        )
    else:
        note = "제약 확보율을 먼저 맞춘 정수 대수"
    return Cell(str(row.allocated), bold=True, hover=f"{_head(row)} · {note}{tail}")


def _count_cell(value: int, *, bold: bool = False) -> Cell:
    """정수 대수 칸 — 0 이면 빈칸."""
    return Cell(str(value) if value > 0 else "", bold=bold and value > 0)


def new_unit_fate(unit: NewUnit, result: ConstraintResult) -> str:
    """신규 호기 하나가 어떻게 쓰였나 — 「27년 7월 몫 전용(2027-06-10 ~ 2027-06-23 대기 14일)」 ·
    「일반 설비(개조 30일 안에 늘어날 전용 없음)」. 나눠 붙었으면 몫마다 잇는다."""
    pieces = [item for item in result.assignments if item.unit == unit.name]
    parts = [
        f"{month_name(item.month)} 몫 {units_text(item.units)}대 전용({waiting_text(item)})"
        if len(pieces) > 1 or abs(item.units - unit.units) > 1e-9
        else f"{month_name(item.month)} 몫 전용({waiting_text(item)})"
        for item in pieces
    ]
    left = result.left_units(unit)
    if left > 0:
        days = result.conditions.modification_days or 0
        reason = f"개조 {days}일 안에 늘어날 전용 없음"
        parts.append(
            f"남는 {units_text(left)}대 일반 설비({reason})" if pieces else f"일반 설비({reason})"
        )
    return " · ".join(parts)


def _new_starts_cell(row: ConstraintMonth, result: ConstraintResult) -> Cell:
    """그 달 W/D 구간에 기여를 시작하는 신규 설비(환산 대수)와 호기마다의 쓰임."""
    units = result.units_starting_in(row.month)
    total = sum(unit.units for unit in units)
    if not units:
        return Cell("", muted=True, hover=f"{_head(row)} · 이 달 기여를 시작하는 신규 설비 없음")
    lines = [
        f"{html.escape(unit.name)} · {unit.start.isoformat()} 기여 시작 · "
        f"{units_text(unit.units)}대 → {html.escape(new_unit_fate(unit, result))}"
        for unit in units
    ]
    return Cell(
        units_text(total),
        hover=f"{_head(row)} · 들어오는 신규 설비<br>" + "<br>".join(lines),
    )


def _waiting_cell(row: ConstraintMonth) -> Cell:
    if row.waiting <= 0:
        return Cell("", muted=True, hover=f"{_head(row)} · 신규 대기 없음")
    lines = [
        f"{html.escape(share.unit)} · {html.escape(month_name(share.source_month))} 몫 "
        f"{units_text(share.units)}대 × {share.days}/{share.window_days}일 = "
        f"{units_text(share.equivalent)}"
        for share in row.waiting_shares
    ]
    if row.overdrawn:
        lines.append("비가동이 그 달 가용보다 많아 쓸 수 있는 가용 0")
    return Cell(
        f"{MINUS}{units_text(row.waiting)}",
        text_color=tokens.DELTA_DECREASE,
        hover=(
            f"{_head(row)} · 신규 대기(셋업 때부터 제약용 — 기존 제품이 못 씀)<br>"
            + "<br>".join(lines)
        ),
    )


def _downtime_cell(row: ConstraintMonth) -> Cell:
    if row.downtime <= 0:
        return Cell("", muted=True, hover=f"{_head(row)} · 개조 비가동 없음")
    lines = [
        f"{html.escape(month_name(share.source_month))} 몫 {share.units}대 × "
        f"{share.days}/{share.window_days}일 = {units_text(share.equivalent)}"
        for share in row.downtime_shares
    ]
    if row.overdrawn:
        lines.append("비가동이 그 달 가용보다 많아 쓸 수 있는 가용 0")
    return Cell(
        f"{MINUS}{units_text(row.downtime)}",
        text_color=tokens.DELTA_DECREASE,
        hover=f"{_head(row)} · 개조 중 비가동<br>" + "<br>".join(lines),
    )


def _existing_available_cell(row: ConstraintMonth) -> Cell:
    text = f"가용 {units_text(row.available)}"
    if row.downtime > 0:
        text += f" − 개조 중 {units_text(row.downtime)}"
    if row.waiting > 0:
        text += f" − 신규 대기 {units_text(row.waiting)}"
    if row.allocated > 0:
        text += f" − 제약 배정 {row.allocated}"
    return Cell(
        units_text(row.existing_available),
        bold=True,
        hover=f"{_head(row)} · {text} = {units_text(row.existing_available)}",
    )


def _delta_cell(row: ConstraintMonth) -> Cell:
    if row.existing_rate is None or row.baseline_rate is None:
        return Cell("", muted=True)
    delta = row.existing_rate - row.baseline_rate
    if abs(delta * 100) < _DELTA_HIDDEN_POINTS:
        return Cell("", muted=True, hover=f"{_head(row)} · 제약 없을 때와 같음")
    return Cell(
        signed_points(delta),
        text_color=tokens.DELTA_DECREASE if delta < 0 else None,
        muted=delta > 0,
    )


def _proportional_cell(row: ConstraintMonth) -> Cell:
    if not row.in_period:
        return Cell("", muted=True, hover=f"{_head(row)} · 제약 기간 밖")
    rate = row.proportional_existing_rate
    return Cell(
        rate_text(rate),
        fill=_shortage_fill(None if rate is None else secure(rate, row.general_target)),
        hover=(
            f"{_head(row)} · 가용 {with_object_particle(units_text(row.available))} "
            "소요 비중대로: 제약 "
            f"{row.proportional_constrained}대 · 기존 {units_text(row.proportional_existing)}대 "
            f"(제약 확보율 {rate_text(row.proportional_constrained_rate)})"
        ),
    )
