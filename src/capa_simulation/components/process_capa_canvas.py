# Purpose: 공정 Capa 상세의 결합 월 캔버스(요약 표·설비 일정)를 라벨·월 Figure 한 쌍으로 그린다.

"""공정 Capa 상세 — 결합 월 캔버스.

공정 하나를 **한 스크롤 상자**에 위에서 아래로 쌓는다. HOME 대시보드 틀 그대로 라벨 칸
(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`, 260px)과 월 칸(달마다 `MONTH_COLUMN_WIDTH_PX`, 100px)이 Figure
한 쌍이고, 월 Figure 하나가 가로로 스크롤된다.

1. **① 공식 기준**(Core Data · 대수) — 총보유대수·가용대수(공급 묶음 면), 소요대수(수요 묶음 면,
   펼치면 분류 행이 줄무늬·들여쓰기로 붙는다), 확보율(판정 3색 칸), 확보기준 과부족(부호 있는 정수,
   부족이면 확보율과 **같은** 판정색, 풍선은 정수 옆에 올림·내림 전 값을 소수 둘째 자리로), 기준
   확보율(달마다 확보기준 % — 회색 글자만, 참고 줄), 그리고 넘겨받았을 때만 확보율(HOME 표시).
2. **② 설비 일정 기준 가용**(참고 · 설비 DB · 환산대수 · 생산월) — 판정 대조(기준✕·일정✕ 만
   칠한다), 가용(환산, 단축 후는 둘째 줄), 전월 대비, 목표 과부족(음수만 칠한다, 단축 후·기한
   지남은 둘째 줄). 목표는 달마다 다른 확보기준이다(`MonthlyTarget`).
3. **③ 신규 설비** — 호기마다 한 줄. ◆ 반입 · ● 기여 시작(Qual상태 색), 단축 대상이면 같은 줄에
   ◀ 목표 기여 시작과 「−N일」, 목표 Qual 이 반입보다 이르면 「반입 전」 배지. 축 안에서
   정지·반출/이설되는 다른 호기는 ▼ 한 줄, 추가N(◌)은 맨 아래. 30행 상한(`ROW_LIMIT`)을 넘으면
   「n대 더」 한 줄이다.
4. **④ 호기별 비가동** — 비가동 한 행이 화살표 하나. 가용을 깎은 것만 진한 실선과 촉, 나머지는 흐린
   점선이다. 글자는 비가동유형과 「◂ 이전부터」·「계속 ▸」.

호기·Model 라벨에는 모듈 수를 적지 않는다(2026-10-22 사용자 요청) — 모듈 묶음은 풍선이
밝힌다. ③ 호기 줄·정지 줄 풍선 첫 줄에 「· 모듈 N」, ④ 풍선 첫 줄에 「· 모듈 N」과 화살표
줄마다 그 모듈의 설비명이다.

**UPEH 가정**(`assumption` — 공정 Capa 상세 조건 카드의 「이 세션만」 값)이 켜지면 ① 끝(기준 확보율
아래)에 「UPEH 가정」 세 줄(소요대수·확보율·확보기준 과부족)이 선다 — 구간 달만 값이고 밖은
빈칸이다(풍선 「구간 밖 — 공식과 같음」). ① 의 공식 줄은 공식 그대로다. **판정 기준은 하나다** —
가정이 켜지면 부족 띠·② 판정 대조는 가정 요약의 판정으로 칠한다(②~④ 가 가정 계획이라 한 그림에서
공식 판정과 섞이지 않게). 「UPEH 가정」 표지는 실제로 바뀌는 행에만 단다 — 가정 세 줄, ② 판정
대조·목표 과부족의 행 라벨, ③ 호기 풍선. ② 가용·전월 대비와 ④ 는 설비 일정이라 UPEH 와 무관하다.
공식 계획에서는 당겼지만 가정 계획에서는 덜 당기는 호기는 ③ 에 흐린 줄로 남고 풍선에 「공식 −45일 →
가정 0일」 이다(`DynamicCanvasInput.official_pulls`).

**구획 접기**(`collapsed`, 구획 id `SECTION_IDS`) — 접힌 구획은 제목 줄만 남고(글자 끝 ▸, 펼친
구획은 ▾) 그 밑 행을 그리지 않는다. 판정·부족 원인은 요약 프레임에서 그대로 내므로 ① 을 접어도 부족
띠와 ② 판정 대조는 같다. 접힌 ③·④ 는 줄을 만들지 않아 「n대 더」 수도 0 이다.

**네 구획이 한 Figure 쌍인 까닭** — 확보기준에 못 미친 달의 세로 띠(`SHORTAGE_MONTH_BAND`)와 지금
보는 달의 열 테두리가 구획을 넘어 이어져야 하고(구획마다 그림을 나누면 제목 줄에서 끊긴다), 칸
선택(`on_select`)이 그림 하나에서 와야 한다. 그래서 구획 제목도 Figure 안의 한 줄이다. 제목과 그
출처·단위 글(세부 글)은 **라벨 Figure** 에 쓴다 — 월 Figure 는 가로로 스크롤되므로 거기 둔 글은
고른 달로 밀어 연 화면에서 잘리거나 사라진다. 세부 글은 라벨 칸 폭에 맞춰 「 · 」 마디로 줄을
나누고(`title_detail_lines`), 그 줄 수만큼 제목 줄이 높아진다(`title_row_height`).

`go.Table`·`go.Heatmap` 을 쓰지 않는다 — 둘 다 점 선택이 없어 `on_select` 가 오지 않는다. 칸 면은
`base` 로 띄운 가로막대, 숫자는 `Scatter(text)`, 칸마다 보이지 않는 표적 막대가 hover 와 클릭을
받는다(HOME 주요공정 히트맵과 같은 방법). 표적의 `customdata` 는 `(YYYYMM, 행 id, 풍선 글)` 이다
(`CUSTOMDATA_MONTH`·`CUSTOMDATA_ROW`·`CUSTOMDATA_HOVER`). 지금 보는 달의 머리 밑줄과 열 테두리는
그림에 그린다 — 그래서 그림 캐시 키에 그 달이 든다.

순수 함수다. 세션·캐시·DB 를 보지 않는다. 그림 캐시·칸 선택 콜백·범례는 페이지가 맡는다.
"""

from __future__ import annotations

import html
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Final, NamedTuple, cast

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.home_figure_common import (
    _text_width_units,
    keep_unselected_opaque,
)
from capa_simulation.components.month_sheet_canvas import CELL_INSET_PX as CELL_INSET_PX
from capa_simulation.components.month_sheet_canvas import CUSTOMDATA_HOVER as CUSTOMDATA_HOVER
from capa_simulation.components.month_sheet_canvas import CUSTOMDATA_MONTH as CUSTOMDATA_MONTH
from capa_simulation.components.month_sheet_canvas import CUSTOMDATA_ROW as CUSTOMDATA_ROW
from capa_simulation.components.month_sheet_canvas import DETAIL_FONT_PX as DETAIL_FONT_PX
from capa_simulation.components.month_sheet_canvas import EMPTY as _EMPTY
from capa_simulation.components.month_sheet_canvas import HEADER_FONT_PX as HEADER_FONT_PX
from capa_simulation.components.month_sheet_canvas import HEADER_HEIGHT_PX as HEADER_HEIGHT_PX
from capa_simulation.components.month_sheet_canvas import KIND_ARROW as _ARROW
from capa_simulation.components.month_sheet_canvas import KIND_HEADER as _HEADER
from capa_simulation.components.month_sheet_canvas import KIND_TITLE as _TITLE
from capa_simulation.components.month_sheet_canvas import KIND_UNIT as _UNIT
from capa_simulation.components.month_sheet_canvas import KIND_VALUE as _VALUE
from capa_simulation.components.month_sheet_canvas import LABEL_FONT_PX as LABEL_FONT_PX
from capa_simulation.components.month_sheet_canvas import LABEL_INSET_PX as LABEL_INSET_PX
from capa_simulation.components.month_sheet_canvas import MINUS as _MINUS
from capa_simulation.components.month_sheet_canvas import NOTE_ROW_HEIGHT_PX as NOTE_ROW_HEIGHT_PX
from capa_simulation.components.month_sheet_canvas import PRODUCT_FONT_PX as PRODUCT_FONT_PX
from capa_simulation.components.month_sheet_canvas import PRODUCT_INDENT_PX as PRODUCT_INDENT_PX
from capa_simulation.components.month_sheet_canvas import ROW_NOTE_PREFIX as ROW_NOTE_PREFIX
from capa_simulation.components.month_sheet_canvas import ROW_TITLE_PREFIX as ROW_TITLE_PREFIX
from capa_simulation.components.month_sheet_canvas import SELECTED_BORDER_PX as SELECTED_BORDER_PX
from capa_simulation.components.month_sheet_canvas import SUB_VALUE_FONT_PX as SUB_VALUE_FONT_PX
from capa_simulation.components.month_sheet_canvas import TITLE_BOTTOM_PX as TITLE_BOTTOM_PX
from capa_simulation.components.month_sheet_canvas import (
    TITLE_DETAIL_FONT_PX as TITLE_DETAIL_FONT_PX,
)
from capa_simulation.components.month_sheet_canvas import (
    TITLE_DETAIL_LINE_PX as TITLE_DETAIL_LINE_PX,
)
from capa_simulation.components.month_sheet_canvas import TITLE_FONT_PX as TITLE_FONT_PX
from capa_simulation.components.month_sheet_canvas import TITLE_HEIGHT_PX as TITLE_HEIGHT_PX
from capa_simulation.components.month_sheet_canvas import TITLE_LINE_PX as TITLE_LINE_PX
from capa_simulation.components.month_sheet_canvas import VALUE_FONT_PX as VALUE_FONT_PX
from capa_simulation.components.month_sheet_canvas import (
    VALUE_ROW_HEIGHT_PX as VALUE_ROW_HEIGHT_PX,
)
from capa_simulation.components.month_sheet_canvas import Cell as _Cell
from capa_simulation.components.month_sheet_canvas import MonthLayers, stack_rows
from capa_simulation.components.month_sheet_canvas import Points as _Points
from capa_simulation.components.month_sheet_canvas import Row as _Row
from capa_simulation.components.month_sheet_canvas import canvas_point as canvas_point
from capa_simulation.components.month_sheet_canvas import data_rect as _data_rect
from capa_simulation.components.month_sheet_canvas import label_figure as _label_figure
from capa_simulation.components.month_sheet_canvas import month_figure as _engine_month_figure
from capa_simulation.components.month_sheet_canvas import note_row as _note_row
from capa_simulation.components.month_sheet_canvas import one as _one
from capa_simulation.components.month_sheet_canvas import percent as _percent
from capa_simulation.components.month_sheet_canvas import signed_int as _signed_int
from capa_simulation.components.month_sheet_canvas import signed_one as _signed_one
from capa_simulation.components.month_sheet_canvas import (
    title_detail_lines as title_detail_lines,
)
from capa_simulation.components.month_sheet_canvas import title_row as _title_row
from capa_simulation.components.month_sheet_canvas import (
    title_row_height as title_row_height,
)
from capa_simulation.components.plotly_layout import flush_layout_items
from capa_simulation.components.shortening_timeline import month_day
from capa_simulation.design import tokens
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    QUAL_STATUS_COLUMN,
    STATUS_EXITED,
    STATUS_STOPPED,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import (
    LENT_COLUMN,
    MISMATCH_COLUMN,
    OTHER_ROW_COLUMN,
    PRODUCT_LABEL_COLUMN,
    month_column,
)
from capa_simulation.services.process_equipment_timeline import (
    EXIT_KIND_RELOCATION,
    ROW_SHORTENED,
    ROW_VIRTUAL,
    production_position,
)
from capa_simulation.services.required_shortening import (
    STATUS_EXPIRED,
    STATUS_NEW_LIMIT,
    MonthlyTarget,
    TargetLevel,
)
from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    CAUSE_OWNED_SHORT,
    OWNED_COLUMN,
    STATUS_COLUMN,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.threshold_label import threshold_percent_label

__all__ = [
    "CUSTOMDATA_HOVER",
    "CUSTOMDATA_MONTH",
    "CUSTOMDATA_ROW",
    "ROW_ARROW_PREFIX",
    "ROW_AVAILABLE",
    "ROW_BALANCE",
    "ROW_DYNAMIC_AVAILABLE",
    "ROW_DYNAMIC_BALANCE",
    "ROW_DYNAMIC_COMPARE",
    "ROW_DYNAMIC_DELTA",
    "ROW_EXIT_PREFIX",
    "ROW_HEADER",
    "ROW_HOME_RATE",
    "ROW_LIMIT",
    "ROW_NOTE_PREFIX",
    "ROW_OWNED",
    "ROW_PRODUCT_PREFIX",
    "ROW_RATE",
    "ROW_REQUIRED",
    "ROW_THRESHOLD",
    "ROW_TITLE_PREFIX",
    "ROW_UNIT_PREFIX",
    "ROW_UPEH_BALANCE",
    "ROW_UPEH_RATE",
    "ROW_UPEH_REQUIRED",
    "SECTION_DOWNTIME",
    "SECTION_DYNAMIC",
    "SECTION_IDS",
    "SECTION_SUMMARY",
    "SECTION_UNITS",
    "SUMMARY_TITLE_DETAIL",
    "SUMMARY_TITLE_HEIGHT_PX",
    "AssumptionCanvasInput",
    "DynamicCanvasInput",
    "ProcessCapaCanvas",
    "build_process_capa_canvas",
    "canvas_point",
    "title_detail_lines",
    "title_row_height",
]

MONTH: Final = "생산계획년월"

# ------------------------------------------------------------------ 치수
# 머리 36px·값 행 27px·제목 줄·글자 크기는 엔진(`month_sheet_canvas`)의 값이다(위에서 다시
# 내보낸다). 여기는 이 캔버스만의 행 — 둘째 줄이 있는 칸(단축 후 값)은 36px, 호기 줄은 라벨 두
# 줄이 드는 34px 다.
# ① 제목 세부 글. 그 줄 높이(`SUMMARY_TITLE_HEIGHT_PX`, 파일 끝)로 화면 확인 스크립트가 확보율 줄의
# 세로 자리를 센다.
SUMMARY_TITLE_DETAIL: Final = "Core Data · 대수 · 확보율에 쓰는 숫자"
PRODUCT_ROW_HEIGHT_PX: Final = 23
TWO_LINE_ROW_HEIGHT_PX: Final = 36
UNIT_ROW_HEIGHT_PX: Final = 34
ARROW_ROW_HEIGHT_PX: Final = 26
# 부족 달 머리 아래 띠와 지금 보는 달 밑줄.
SHORTAGE_STRIP_PX: Final = 4
SELECTED_UNDERLINE_PX: Final = 1.5
TRACK_TEXT_FONT_PX: Final = 11
ARROW_TEXT_FONT_PX: Final = 10
# ③·④ 의 줄 상한. 넘으면 「n대 더」 한 줄을 두고, 페이지의 「더 보기」가 모두 그린다.
ROW_LIMIT: Final = 30
# ④ 화살표 위 비가동유형 글자의 상한(글자 수).
ARROW_TYPE_MAX_CHARS: Final = 12
# 같은 호기의 두 화살표가 한 줄에 서려면 앞 화살표의 촉과 이만큼(달 단위) 떨어져야 한다.
_LANE_GAP_MONTHS: Final = 0.02

# ------------------------------------------------------------------ 행 id·customdata
ROW_HEADER: Final = "header"
ROW_OWNED: Final = "owned"
ROW_AVAILABLE: Final = "available"
ROW_REQUIRED: Final = "required"
ROW_PRODUCT_PREFIX: Final = "product:"
ROW_RATE: Final = "rate"
ROW_BALANCE: Final = "balance"
ROW_THRESHOLD: Final = "threshold"
ROW_HOME_RATE: Final = "home_rate"
ROW_UPEH_REQUIRED: Final = "upeh_required"
ROW_UPEH_RATE: Final = "upeh_rate"
ROW_UPEH_BALANCE: Final = "upeh_balance"
ROW_DYNAMIC_COMPARE: Final = "dynamic_compare"
ROW_DYNAMIC_AVAILABLE: Final = "dynamic_available"
ROW_DYNAMIC_DELTA: Final = "dynamic_delta"
ROW_DYNAMIC_BALANCE: Final = "dynamic_balance"
ROW_UNIT_PREFIX: Final = "unit:"
ROW_EXIT_PREFIX: Final = "exit:"
ROW_ARROW_PREFIX: Final = "arrow:"

# 구획 id — 제목 줄 행 id(`title:<id>`)의 꼬리이고, 페이지의 「구획」 칩 값이다.
SECTION_SUMMARY: Final = "summary"
SECTION_DYNAMIC: Final = "dynamic"
SECTION_UNITS: Final = "units"
SECTION_DOWNTIME: Final = "downtime"
SECTION_IDS: Final = (SECTION_SUMMARY, SECTION_DYNAMIC, SECTION_UNITS, SECTION_DOWNTIME)

_SHORT_STATUSES: Final = frozenset({"warning", "shortage"})
_STATUS_NAMES: Final[Mapping[str, str]] = {"secure": "확보", "warning": "경고", "shortage": "부족"}


@dataclass(frozen=True, eq=False)
class DynamicCanvasInput:
    """② ~ ④ 의 재료 — 설비 일정이 「참고」로 설 때(`dynamic_readiness(...).ready`)만 넘긴다.

    프레임은 모두 **공정 하나**의 것이다. `process_months` 는 `LevelPlan.process_months` 를 그
    공정으로 거른 것(달마다 한 행), `bridge`·`arrows`·`exits` 는 `ProcessEquipmentTimeline` 의
    칸, `unit_events` 는 `unit_events(timeline, plan.units)` 다. `exits` 에서 ③ 에 이미 선 호기는
    여기서 뺀다.
    """

    cutoff_days: int
    target: TargetLevel
    today: date
    process_months: pd.DataFrame
    bridge: pd.DataFrame
    unit_events: pd.DataFrame
    arrows: pd.DataFrame
    exits: pd.DataFrame = field(default_factory=pd.DataFrame)
    has_units: bool = True
    """설비 마스터에 HBM·EDP 호기가 있는가. 기존보유만 있는 공정은 ② 만 서고 「호기 일정 없음」
    한 줄이다."""

    steady_units: int = 0
    """축 내내 비가동 없이 가용인 호기 수 — ④ 끝의 「k대」 한 줄."""

    undated_notice: str = ""
    """③ 끝에 적는 「일정 미정 k대」 글(`undated_equipment_notice`). 비면 줄이 없다."""

    show_all_units: bool = False
    show_all_arrows: bool = False
    official_pulls: Mapping[str, tuple[int, int]] | None = None
    """UPEH 가정 계획을 그릴 때만 — 공식 계획과 단축일수가 다른 호기 → (공식 일, 가정 일)
    (`upeh_assumption.pull_changes`). None 이면 공식 계획이다(② 라벨에 표지를 달지 않는다)."""


@dataclass(frozen=True, eq=False)
class AssumptionCanvasInput:
    """UPEH 가정 — ① 끝 세 줄과 판정 기준(가정 요약)의 재료."""

    percent: int
    months: frozenset[int]
    """가정을 건 달(토큰의 달)."""

    summary: pd.DataFrame
    """가정 요약 — 공식 요약과 같은 함수(`build_process_capa_summary`)에 소요 ÷f 를 건 확보율을 넣은
    것."""


class ProcessCapaCanvas(NamedTuple):
    """결합 캔버스 한 쌍. 두 Figure 는 높이가 같고 행이 맞는다."""

    labels: go.Figure
    months: go.Figure
    height: int
    hidden_units: int
    """30행 상한으로 그리지 않은 ③ 호기 수(추가N 은 늘 그린다)."""

    hidden_arrow_units: int
    """30대 상한으로 그리지 않은 ④ 호기 수."""

    row_ids: tuple[str, ...]
    """위에서 아래로 그린 행 id."""


# ================================================================== 공개 함수


def build_process_capa_canvas(
    *,
    process_label: str,
    months: Sequence[int],
    summary: pd.DataFrame,
    thresholds: SecurementThresholds,
    selected_month: int | None,
    product_demand: pd.DataFrame | None = None,
    home_rates: Mapping[int, float | None] | None = None,
    dynamic: DynamicCanvasInput | None = None,
    collapsed: Collection[str] = frozenset(),
    assumption: AssumptionCanvasInput | None = None,
) -> ProcessCapaCanvas:
    """공정 하나의 결합 월 캔버스(라벨 Figure · 월 Figure)를 만든다.

    - `months` 는 월 축(`YYYYMM`, 차례대로)이다 — 조회기간 ∩ 소요 달. 비면 `ValueError` 다.
    - `summary` 는 `build_process_capa_summary` 결과(같은 `thresholds`)다. 판정(`판정`)이 확보율 칸·
      과부족 칸·부족 띠의 색을 **한 길**로 정한다.
    - `product_demand` 는 「제품별 소요대수」를 펼쳤을 때의 `build_process_product_demand` 결과다.
      None 이면 접힌 것이다(소요대수 ▸).
    - `home_rates` 를 넘기면 맨 아래에 「확보율 (HOME 표시)」 줄이 선다(확보율 보정·선행 반영 값,
      회색).
    - `dynamic` 이 None 이면 ① 만 그린다(설비 일정 없음 — 페이지가 까닭 카드를 둔다).
    - `selected_month` 는 지금 보는 달이다. 축에 없으면 표시하지 않는다.
    - `collapsed` 는 접힌 구획 id(`SECTION_IDS`)다. 접힌 구획은 제목 줄(▸)만 남는다. 없는 구획의
      id 는 무시한다.
    - `assumption` 을 넘기면 ① 끝에 「UPEH 가정」 세 줄이 서고, 부족 띠·② 판정 대조는 그 요약의
      판정을 쓴다. `dynamic` 도 그때는 가정 계획이어야 한다(페이지가 맞춘다).
    """
    axis = [int(month) for month in months]
    if not axis:
        raise ValueError("결합 캔버스의 월 축이 비었습니다.")
    if len(set(axis)) != len(axis) or axis != sorted(axis):
        raise ValueError("결합 캔버스의 월 축은 겹치지 않는 오름차순이어야 합니다.")
    index_of = {month: position for position, month in enumerate(axis)}
    folded = frozenset(str(section) for section in collapsed)

    # 판정·원인은 요약 프레임에서 낸다 — ① 을 접어도 부족 띠·② 판정 대조가 바뀌지 않는다. UPEH
    # 가정이 켜지면 그 요약 하나가 판정 기준이다(②~④ 가 가정 계획이다).
    judged = assumption.summary if assumption is not None else summary
    statuses = _summary_statuses(judged, axis)
    causes = _summary_causes(judged, axis)
    rows: list[_Row] = [_header_row(process_label, axis, thresholds)]
    if SECTION_SUMMARY in folded:
        rows.append(_section_title_row(SECTION_SUMMARY, SUMMARY_TITLE_DETAIL, folded))
    else:
        rows += _summary_rows(axis, summary, thresholds, product_demand, home_rates, assumption)
    hidden_units = 0
    hidden_arrow_units = 0
    today_x: float | None = None
    dynamic_first: int | None = None
    if dynamic is not None:
        dynamic_first = len(rows)
        dynamic_rows, hidden_units, hidden_arrow_units = _dynamic_rows(
            axis, statuses, causes, dynamic, folded
        )
        rows += dynamic_rows
        today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
        if not today_position.before and not today_position.after:
            today_x = today_position.x

    height = stack_rows(rows)
    shortage_indices = [
        index_of[month] for month, status in statuses.items() if status in _SHORT_STATUSES
    ]
    selected_index = index_of.get(int(selected_month)) if selected_month is not None else None

    label_figure = _label_figure(rows, height)
    month_figure = _month_figure(
        rows,
        axis,
        height,
        shortage_indices=shortage_indices,
        selected_index=selected_index,
        today_x=today_x,
        dynamic_rows=rows[dynamic_first:] if dynamic_first is not None else [],
        dynamic=dynamic,
    )
    flush_layout_items(label_figure, month_figure)
    keep_unselected_opaque(month_figure)
    return ProcessCapaCanvas(
        labels=label_figure,
        months=month_figure,
        height=height,
        hidden_units=hidden_units,
        hidden_arrow_units=hidden_arrow_units,
        row_ids=tuple(row.row_id for row in rows),
    )


# ================================================================== ① 공식 기준


def _summary_statuses(summary: pd.DataFrame, axis: Sequence[int]) -> dict[int, str | None]:
    records = _by_month(summary, axis)
    return {month: _status(records.get(month, {}).get(STATUS_COLUMN)) for month in axis}


def _summary_causes(summary: pd.DataFrame, axis: Sequence[int]) -> dict[int, str]:
    """달마다 공식 기준 부족 원인(`부족 원인`). 확보인 달·원인이 빈 달은 「」이다."""
    records = _by_month(summary, axis)
    causes: dict[int, str] = {}
    for month in axis:
        cause = records.get(month, {}).get(CAUSE_COLUMN)
        causes[month] = "" if _blank(cause) else str(cause)
    return causes


# 구획 제목 글자. 끝에 펼침(▾)·접힘(▸)을 붙인다 — ① 소요대수 줄의 ▾/▸ 와 같은 꼴이다.
_SECTION_TITLES: Final[Mapping[str, str]] = {
    SECTION_SUMMARY: "① 공식 기준",
    SECTION_DYNAMIC: "② 설비 일정 기준 가용",
    SECTION_UNITS: "③ 신규 설비 일정과 단축",
    SECTION_DOWNTIME: "④ 호기별 비가동",
}


def _section_title_row(section: str, detail: str, folded: Collection[str]) -> _Row:
    """구획 제목 줄. 접혔으면 「▸」, 펼쳤으면 「▾」 — 세부 글은 같아 줄 높이가 그대로다."""
    mark = "▸" if section in folded else "▾"
    return _title_row(section, f"{_SECTION_TITLES[section]} {mark}", detail)


def _header_row(process_label: str, axis: Sequence[int], thresholds: SecurementThresholds) -> _Row:
    row = _Row(
        ROW_HEADER,
        _HEADER,
        HEADER_HEIGHT_PX,
        label=f"구분 · {process_label}",
        label_bold=True,
        label_fill=tokens.HEADER_BACKGROUND,
        month_fill=tokens.HEADER_BACKGROUND,
    )
    for index, month in enumerate(axis):
        secure, warning = thresholds.for_month(month)
        row.cells[index] = _Cell(
            text=month_label(month),
            hover=(
                f"<b>{month_label(month)}</b> · 누르면 이 달의 산출 근거"
                f"<br>확보기준 {threshold_percent_label(secure)} · "
                f"경고기준 {threshold_percent_label(warning)}"
            ),
        )
    return row


def _summary_rows(
    axis: Sequence[int],
    summary: pd.DataFrame,
    thresholds: SecurementThresholds,
    product_demand: pd.DataFrame | None,
    home_rates: Mapping[int, float | None] | None,
    assumption: AssumptionCanvasInput | None = None,
) -> list[_Row]:
    records = _by_month(summary, axis)
    supply_label, supply_month = (
        tokens.SUMMARY_SUPPLY_CLASSIFICATION,
        tokens.SUMMARY_SUPPLY_SURFACE,
    )
    demand_label, demand_month = (
        tokens.SUMMARY_DEMAND_CLASSIFICATION,
        tokens.SUMMARY_DEMAND_SURFACE,
    )
    owned = _Row(
        ROW_OWNED,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="총보유대수",
        label_fill=supply_label,
        month_fill=supply_month,
        group_start=True,
    )
    available = _Row(
        ROW_AVAILABLE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="가용대수",
        label_fill=supply_label,
        month_fill=supply_month,
    )
    required = _Row(
        ROW_REQUIRED,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=f"소요대수 {'▾' if product_demand is not None else '▸'}",
        label_bold=True,
        label_fill=demand_label,
        month_fill=demand_month,
        group_start=True,
    )
    uniform = not thresholds.exception_months_within(axis)
    balance_label = (
        f"확보기준({threshold_percent_label(thresholds.default_secure)}) 과부족"
        if uniform
        else "확보기준 과부족"
    )
    rate = _Row(
        ROW_RATE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="확보율",
        label_fill=tokens.SURFACE_CLASSIFICATION,
        group_start=True,
    )
    balance = _Row(
        ROW_BALANCE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=balance_label,
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    # 참고 줄 — 달마다 확보기준(%) 그대로다. 강조하지 않는다(회색 글자, 면색·굵기 없음).
    reference = _Row(
        ROW_THRESHOLD,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="기준 확보율",
        label_muted=True,
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    for index, month in enumerate(axis):
        record = records.get(month, {})
        head = f"<b>{month_label(month)}</b>"
        owned_count = _number(record.get(OWNED_COLUMN))
        lent_count = _number(record.get(LENT_COLUMN))
        available_count = _number(record.get("가용대수"))
        demand = _number(record.get("소요대수"))
        rate_value = _number(record.get("확보율"))
        status = _status(record.get(STATUS_COLUMN))
        mismatch = bool(record.get(MISMATCH_COLUMN, False))
        secure, warning = thresholds.for_month(month)
        owned.cells[index] = _Cell(
            text=_one(owned_count), hover=f"{head} · 총보유대수 {_one(owned_count)}대"
        )
        available_hover = (
            f"{head} · 가용대수 {_one(available_count)}대"
            f"<br>보유 {_one(owned_count)} {_MINUS} 대여 {_one(lent_count)} = "
            f"{_one(_difference(owned_count, lent_count))}"
        )
        if mismatch:
            available_hover += (
                "<br>⚠ 가용대수가 보유 − 대여와 다릅니다(기준정보 표를 따로 고쳤습니다)"
            )
        available.cells[index] = _Cell(
            text=f"{_one(available_count)}{' ⚠' if mismatch else ''}", hover=available_hover
        )
        required.cells[index] = _Cell(
            text=_one(demand), bold=True, hover=f"{head} · 소요대수 {_one(demand)}대"
        )
        fill = _status_color(status)
        rate.cells[index] = _Cell(
            text=_percent(rate_value) if status is not None else _EMPTY,
            fill=fill,
            bold=fill is not None,
            hover=_rate_hover(head, rate_value, available_count, demand, status, secure, warning),
        )
        balance_value = _whole(record.get(BALANCE_COLUMN))
        painted = _status_color(status) if status in _SHORT_STATUSES else None
        balance.cells[index] = _Cell(
            text=_signed_int(balance_value) if balance_value is not None else _EMPTY,
            fill=painted,
            bold=painted is not None,
            hover=_balance_hover(
                head, balance_value, available_count, demand, secure, record.get(CAUSE_COLUMN)
            ),
        )
        reference.cells[index] = _Cell(
            text=threshold_percent_label(secure),
            muted=True,
            hover=(
                f"{head} · 확보기준 {threshold_percent_label(secure)} ({_ratio(secure)}) · "
                f"경고기준 {threshold_percent_label(warning)} ({_ratio(warning)})"
            ),
        )
    rows = [_section_title_row(SECTION_SUMMARY, SUMMARY_TITLE_DETAIL, ())]
    rows += [owned, available, required]
    if product_demand is not None:
        rows += _product_rows(axis, product_demand, records)
    rows += [rate, balance, reference]
    if assumption is not None:
        rows += _assumption_rows(axis, records, thresholds, assumption)
    if home_rates is not None:
        home = _Row(
            ROW_HOME_RATE,
            _VALUE,
            VALUE_ROW_HEIGHT_PX,
            label="확보율 (HOME 표시)",
            label_muted=True,
            label_fill=tokens.SURFACE_CLASSIFICATION,
        )
        for index, month in enumerate(axis):
            value = _number(home_rates.get(month))
            home.cells[index] = _Cell(
                text=_percent(value),
                muted=True,
                hover=(
                    f"<b>{month_label(month)}</b> · HOME 표시 확보율 {_percent(value)}"
                    "<br>확보율 보정·선행 B/O 를 얹은 값 — 위 확보율은 원 확보율"
                ),
            )
        rows.append(home)
    return rows


def _assumption_rows(
    axis: Sequence[int],
    records: Mapping[int, Mapping[str, object]],
    thresholds: SecurementThresholds,
    assumption: AssumptionCanvasInput,
) -> list[_Row]:
    """① 끝 「UPEH 가정」 세 줄 — 구간 달만 값, 밖은 빈칸(풍선 「구간 밖 — 공식과 같음」)."""
    prefix = f"UPEH {assumption.percent}%"
    factor = assumption.percent / 100
    assumed = _by_month(assumption.summary, axis)
    required = _Row(
        ROW_UPEH_REQUIRED,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=f"{prefix} · 소요대수",
        label_bold=True,
        label_fill=tokens.SUMMARY_DEMAND_CLASSIFICATION,
        month_fill=tokens.SUMMARY_DEMAND_SURFACE,
        group_start=True,
    )
    rate = _Row(
        ROW_UPEH_RATE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=f"{prefix} · 확보율",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    balance = _Row(
        ROW_UPEH_BALANCE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=f"{prefix} · 확보기준 과부족",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        if month not in assumption.months:
            outside = f"{head} · 구간 밖 — 공식과 같음"
            for row in (required, rate, balance):
                row.cells[index] = _Cell(text="", muted=True, hover=outside)
            continue
        official = records.get(month, {})
        record = assumed.get(month, {})
        demand = _number(record.get("소요대수"))
        official_demand = _number(official.get("소요대수"))
        available = _number(record.get("가용대수"))
        rate_value = _number(record.get("확보율"))
        status = _status(record.get(STATUS_COLUMN))
        secure, warning = thresholds.for_month(month)
        change = (
            f"<br>공식 {_two(official_demand)} ÷ {factor:g} = {_two(demand)} "
            f"({_signed_two((demand or 0.0) - (official_demand or 0.0))}대)"
            if official_demand is not None and demand is not None
            else ""
        )
        required.cells[index] = _Cell(
            text=_one(demand),
            bold=True,
            hover=f"{head} · UPEH 가정 {assumption.percent}% 소요대수 {_one(demand)}대{change}",
        )
        fill = _status_color(status)
        rate.cells[index] = _Cell(
            text=_percent(rate_value) if status is not None else _EMPTY,
            fill=fill,
            bold=fill is not None,
            hover=_rate_hover(head, rate_value, available, demand, status, secure, warning)
            + f"<br>UPEH 가정 {assumption.percent}% — 공식 확보율 "
            + f"{_percent(_number(official.get('확보율')))}",
        )
        value = _whole(record.get(BALANCE_COLUMN))
        official_value = _whole(official.get(BALANCE_COLUMN))
        painted = _status_color(status) if status in _SHORT_STATUSES else None
        balance.cells[index] = _Cell(
            text=_signed_int(value) if value is not None else _EMPTY,
            fill=painted,
            bold=painted is not None,
            hover=_balance_hover(head, value, available, demand, secure, record.get(CAUSE_COLUMN))
            + (
                f"<br>공식 {_signed_int(official_value)} → 가정 {_signed_int(value)}"
                if value is not None and official_value is not None
                else ""
            ),
        )
    return [required, rate, balance]


def _product_rows(
    axis: Sequence[int],
    product_demand: pd.DataFrame,
    records: Mapping[int, Mapping[str, object]],
) -> list[_Row]:
    rows: list[_Row] = []
    for position, record in enumerate(product_demand.to_dict("records")):
        label = str(record.get(PRODUCT_LABEL_COLUMN, ""))
        other = bool(record.get(OTHER_ROW_COLUMN, False))
        row = _Row(
            f"{ROW_PRODUCT_PREFIX}{label}",
            _VALUE,
            PRODUCT_ROW_HEIGHT_PX,
            label=f"└ {label}",
            label_muted=other,
            indent=True,
            label_fill=tokens.SUMMARY_DEMAND_CLASSIFICATION,
            # 제품 행은 흰 면·줄무늬를 번갈아 칠한다 — 부모(소요대수) 수요 면과 갈려 자식이다.
            month_fill=tokens.SURFACE if position % 2 == 0 else tokens.SURFACE_SUBTLE,
        )
        for index, month in enumerate(axis):
            value = _number(record.get(month_column(month))) or 0.0
            parent = _number(records.get(month, {}).get("소요대수"))
            share = f" · 소요의 {value / parent:.0%}" if parent else ""
            row.cells[index] = _Cell(
                text=_one(value),
                hover=f"<b>{month_label(month)}</b> · {html.escape(label)} {_one(value)}대{share}",
            )
        rows.append(row)
    return rows


def _rate_hover(
    head: str,
    rate: float | None,
    available: float | None,
    demand: float | None,
    status: str | None,
    secure: float,
    warning: float,
) -> str:
    if status is None or rate is None:
        return f"{head} · 확보율 {_EMPTY} (소요대수 0)"
    return (
        f"{head} · 확보율 {_percent(rate)} = 가용 {_one(available)} ÷ 소요 {_one(demand)}"
        f"<br>판정 {_STATUS_NAMES.get(status, status)} — 확보기준 {threshold_percent_label(secure)}"
        f" · 경고기준 {threshold_percent_label(warning)}"
    )


def _balance_hover(
    head: str,
    balance: int | None,
    available: float | None,
    demand: float | None,
    secure: float,
    cause: object,
) -> str:
    if balance is None:
        return f"{head} · 확보기준 과부족 {_EMPTY}"
    # 정수 옆에 올림·내림 전 값(가용 − 소요 × 확보기준)을 소수 둘째 자리로 단다.
    unrounded = (
        f" ({_signed_two(available - demand * secure)})"
        if available is not None and demand is not None
        else ""
    )
    text = (
        f"{head} · 확보기준 과부족 {_signed_int(balance)}대{unrounded}"
        f"<br>가용 {_one(available)} {_MINUS} 소요 {_one(demand)} × {_ratio(secure)}"
        f" (부족은 올림, 여유는 내림)"
    )
    reason = "" if _blank(cause) else str(cause)
    if reason:
        text += f"<br>원인 {html.escape(reason)}"
    return text


# ================================================================== ② ~ ④ 설비 일정


def _dynamic_rows(
    axis: Sequence[int],
    statuses: Mapping[int, str | None],
    causes: Mapping[int, str],
    dynamic: DynamicCanvasInput,
    folded: Collection[str] = (),
) -> tuple[list[_Row], int, int]:
    today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
    # 오늘이 든 생산월보다 앞선 달은 「기한 지남」이다 — 단축으로 바꿀 수 없어 흐리게 둔다.
    today_month = today_position.month
    plan = _by_month(dynamic.process_months, axis, unique=True)
    bridge = _by_month(dynamic.bridge, axis)
    target_text = _target_text(dynamic.target, axis)
    detail = f"참고 · 설비 DB · 환산대수 · 생산월(Cut-off {dynamic.cutoff_days}일)"
    if not today_position.before and not today_position.after:
        detail += f" · 점선은 오늘({dynamic.today:%m.%d})"
    rows: list[_Row] = [_section_title_row(SECTION_DYNAMIC, detail, folded)]
    # UPEH 가정 계획이면 바뀌는 행(판정 대조·목표 과부족)의 라벨에만 표지를 단다 — 제목 줄 높이는
    # 그대로다.
    assumed_mark = " · UPEH 가정" if dynamic.official_pulls is not None else ""
    compare = _Row(
        ROW_DYNAMIC_COMPARE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=f"판정 대조{assumed_mark}",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    available = _Row(
        ROW_DYNAMIC_AVAILABLE,
        _VALUE,
        TWO_LINE_ROW_HEIGHT_PX,
        label="가용 (환산)",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    delta = _Row(
        ROW_DYNAMIC_DELTA,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="전월 대비",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    balance = _Row(
        ROW_DYNAMIC_BALANCE,
        _VALUE,
        TWO_LINE_ROW_HEIGHT_PX,
        label=f"{_target_balance_label(dynamic.target, axis)}{assumed_mark}",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        past = month < today_month
        record = plan.get(month)
        static_short = statuses.get(month) in _SHORT_STATUSES
        if record is None:
            for row in (compare, available, balance):
                row.cells[index] = _Cell(
                    text=_EMPTY, muted=True, hover=f"{head} · 설비 일정 계획에 없는 달"
                )
        else:
            before = _number(record.get("가용대수"))
            after = _number(record.get("단축후가용대수"))
            gap = _number(record.get("과부족"))
            gap_after = _number(record.get("단축후과부족"))
            target_units = _number(record.get("목표대수"))
            state = "" if _blank(record.get("상태")) else str(record.get("상태"))
            dynamic_short = gap is not None and round(gap, 9) < 0
            compare.cells[index] = _compare_cell(
                head, static_short, dynamic_short, cause=causes.get(month, ""), past=past
            )
            available.cells[index] = _Cell(
                text=_one(before),
                sub=f"→ {_one(after)}" if _changed(before, after) else "",
                muted=past,
                hover=(
                    f"{head} · 설비 일정 기준 가용 {_one(before)} (환산대수)"
                    + (f"<br>단축 후 {_one(after)}" if _changed(before, after) else "")
                ),
            )
            balance.cells[index] = _target_balance_cell(
                head,
                gap,
                gap_after,
                target_units,
                before,
                state,
                target=_target_for(dynamic.target, month),
                past=past,
            )
        bridge_record = bridge.get(month, {})
        change = _number(bridge_record.get("전월대비"))
        delta.cells[index] = _Cell(
            text=_signed_one(change) if change is not None else _EMPTY,
            muted=past,
            hover=(
                f"{head} · 전월 대비 {_signed_one(change)} = 신규 "
                f"{_signed_one(_number(bridge_record.get('신규')) or 0.0)} · 비가동 "
                f"{_signed_one(_number(bridge_record.get('비가동')) or 0.0)} · 정지·반출/이설 "
                f"{_signed_one(_number(bridge_record.get('반출이설')) or 0.0)}"
                if change is not None
                else f"{head} · 축 첫 달이라 전월 대비가 없습니다"
            ),
        )
    if SECTION_DYNAMIC not in folded:
        rows += [compare, available, delta, balance]
    if not dynamic.has_units:
        # ③·④ 가 서지 않는 공정의 까닭 — ② 를 접어도 남긴다(③·④ 자리의 글이다).
        rows.append(_note_row("no_units", "호기 일정 없음 — 기존보유만 있는 공정입니다"))
        return rows, 0, 0
    hidden_units = 0
    hidden_arrow_units = 0
    # 표지(◆ 반입 · ● 기여 시작 · ◀ 목표 기여 시작)는 캔버스 아래 범례가 적는다.
    rows.append(_section_title_row(SECTION_UNITS, f"{target_text} · 호기마다 한 줄", folded))
    if SECTION_UNITS not in folded:
        unit_rows, hidden_units = _unit_rows(axis, dynamic)
        rows += unit_rows
    rows.append(
        _section_title_row(
            SECTION_DOWNTIME,
            "진한 화살표만 가용을 깎았습니다 · 끝은 다음 날부터 셉니다",
            folded,
        )
    )
    if SECTION_DOWNTIME not in folded:
        arrow_rows, hidden_arrow_units = _arrow_rows(axis, dynamic)
        rows += arrow_rows
    return rows, hidden_units, hidden_arrow_units


def _compare_cell(
    head: str, static_short: bool, dynamic_short: bool, *, cause: str = "", past: bool
) -> _Cell:
    if static_short and dynamic_short:
        return _Cell(
            text="기준✕·일정✕",
            fill=None if past else tokens.STATUS_SHORTAGE,
            bold=not past,
            muted=past,
            hover=(
                f"{head} · 공식·설비 일정 두 기준 모두 부족 — 아래 단축이 이 달을 메웁니다"
                "(단위가 달라 크기는 참고)"
            ),
        )
    if static_short:
        hover = (
            f"{head} · 공식은 부족, 설비 일정으로는 충족 — Core Data 보유·대여와 "
            "설비 DB 일정이 어긋날 수 있습니다"
        )
        # 보유로도 부족이면 단축할 것이 없는 달이 아니라 투자를 볼 달이다(설계 logic_final 3).
        if cause == CAUSE_OWNED_SHORT:
            hover += f"<br>원인: {CAUSE_OWNED_SHORT} — 투자 검토(단축으로 못 메웁니다)"
        return _Cell(text="기준✕·일정✓", muted=True, hover=hover)
    if dynamic_short:
        return _Cell(
            text="기준✓·일정✕",
            muted=True,
            hover=f"{head} · 공식은 충족 — 설비 일정 기준으로만 부족(참고)",
        )
    return _Cell(hover=f"{head} · 두 기준 모두 충족")


def _target_balance_cell(
    head: str,
    gap: float | None,
    gap_after: float | None,
    target_units: float | None,
    available: float | None,
    state: str,
    *,
    target: float,
    past: bool,
) -> _Cell:
    if gap is None:
        return _Cell(text=_EMPTY, muted=True, hover=f"{head} · 목표 과부족 {_EMPTY}")
    short = round(gap, 9) < 0
    if state == STATUS_EXPIRED:
        sub = "기한 지남"
    elif state == STATUS_NEW_LIMIT:
        sub = "남은 날 부족"
    elif _changed(gap, gap_after):
        sub = f"→ {_signed_one(gap_after)}"
    else:
        sub = ""
    hover = (
        f"{head} · 목표 {threshold_percent_label(target)} 과부족 {_signed_one(gap)}"
        f"<br>가용 {_one(available)} {_MINUS} 목표대수 {_one(target_units)} (환산대수)"
    )
    if _changed(gap, gap_after):
        hover += f"<br>단축 후 {_signed_one(gap_after)}"
    if state:
        hover += f"<br>{html.escape(state)}"
    painted = short and not past
    return _Cell(
        text=_signed_one(gap),
        sub=sub,
        fill=tokens.STATUS_SHORTAGE if painted else None,
        bold=painted,
        muted=past,
        hover=hover,
    )


def _unit_rows(axis: Sequence[int], dynamic: DynamicCanvasInput) -> tuple[list[_Row], int]:
    events = _records(dynamic.unit_events)
    real = [event for event in events if event.get("줄") != ROW_VIRTUAL]
    virtual = [event for event in events if event.get("줄") == ROW_VIRTUAL]
    shown_units = {str(event.get("호기")) for event in events}
    exits = [
        record for record in _records(dynamic.exits) if str(record.get("호기")) not in shown_units
    ]
    entries: list[tuple[str, dict[str, object]]] = [("event", event) for event in real]
    entries += [("exit", record) for record in exits]
    hidden = 0
    if not dynamic.show_all_units and len(entries) > ROW_LIMIT:
        hidden = len(entries) - ROW_LIMIT
        entries = entries[:ROW_LIMIT]
    entries += [("event", event) for event in virtual]
    rows: list[_Row] = []
    for kind, record in entries:
        row = _exit_row(record, dynamic) if kind == "exit" else _unit_row(record, dynamic)
        # 칸마다 같은 호기 풍선 — 줄 어디를 눌러도 그 열의 달이 골라진다.
        for index, month in enumerate(axis):
            row.cells[index] = _Cell(hover=f"<b>{month_label(month)}</b> · {row.hover}")
        rows.append(row)
    if not rows:
        rows.append(_note_row("no_new_units", "조회기간에 새로 붙는 설비가 없습니다"))
    if hidden:
        rows.append(_note_row("more_units", f"외 {hidden}대 — 「더 보기」를 켜면 모두 그립니다"))
    if dynamic.undated_notice:
        rows.append(_note_row("undated", dynamic.undated_notice))
    return rows, hidden


def _unit_row(event: Mapping[str, object], dynamic: DynamicCanvasInput) -> _Row:
    today = dynamic.today
    kind = str(event.get("줄"))
    unit = str(event.get("호기"))
    arrival = _as_date(event.get("반입일정"))
    qual = _as_date(event.get("Qual일정"))
    target = _as_date(event.get("목표 Qual"))
    confirmation = _qual_status(event)
    if kind == ROW_VIRTUAL:
        detail = f"필요 {_day(target, today)} · 신규"
    elif kind == ROW_SHORTENED:
        detail = f"기존 {_day(qual, today)} → 단축 {_day(target, today)}"
    else:
        detail = f"반입 {_day(arrival, today)} · Qual {_day(qual, today)}" + (
            f" · {confirmation}" if confirmation else ""
        )
    hover = _unit_hover(event)
    released = False
    if dynamic.official_pulls is not None:
        hover = hover.replace("<br>", " · UPEH 가정 계획<br>", 1) if "<br>" in hover else hover
        change = dynamic.official_pulls.get(unit)
        if change is not None:
            official_days, assumed_days = change
            hover += f"<br>공식 {_MINUS}{official_days}일 → 가정 " + (
                f"{_MINUS}{assumed_days}일" if assumed_days else "0일"
            )
            # 가정으로 단축이 필요 없어진 호기 — 흐린 줄로 남긴다(P5).
            if kind != ROW_SHORTENED:
                released = True
                detail = f"가정으로 단축 불필요 · 공식 {_MINUS}{official_days}일"
    return _Row(
        f"{ROW_UNIT_PREFIX}{unit}",
        _UNIT,
        UNIT_ROW_HEIGHT_PX,
        label=unit,
        detail=detail,
        label_bold=not released,
        label_muted=released,
        label_fill=tokens.SURFACE_CLASSIFICATION,
        payload=("event", dict(event)),
        hover=hover,
    )


def _exit_row(record: Mapping[str, object], dynamic: DynamicCanvasInput) -> _Row:
    unit = str(record.get("호기"))
    kind = "" if _blank(record.get("반출이설구분")) else str(record.get("반출이설구분"))
    day = _as_date(record.get("반출이설일"))
    model = "" if _blank(record.get("Model")) else str(record.get("Model"))
    return _Row(
        f"{ROW_EXIT_PREFIX}{unit}",
        _UNIT,
        UNIT_ROW_HEIGHT_PX,
        label=unit,
        detail=f"{kind} {_day(day, dynamic.today)}" + (f" · {model}" if model else ""),
        label_bold=True,
        label_fill=tokens.SURFACE_CLASSIFICATION,
        payload=("exit", dict(record)),
        hover=(
            f"{html.escape(unit)}{_module_text(record)} · {html.escape(kind)} {_iso(day)}"
            + (f" · {html.escape(model)}" if model else "")
            + "<br>정지·반출/이설은 그날부터 가용에서 빠집니다"
        ),
    )


def _module_text(record: Mapping[str, object]) -> str:
    """모듈 묶음이면 「 · 모듈 N」, 단독 호기면 빈 글자 — 라벨에서 걷은 모듈 수를 풍선 첫 줄에
    둔다."""
    modules = _whole(record.get("모듈 수")) or 1
    return f" · 모듈 {modules}" if modules > 1 else ""


def _unit_hover(event: Mapping[str, object]) -> str:
    kind = str(event.get("줄"))
    unit = html.escape(str(event.get("호기")))
    lines = [f"{unit}"]
    model = "" if _blank(event.get("Model")) else str(event.get("Model"))
    if model:
        lines[0] += f" · {html.escape(model)}"
    lines[0] += _module_text(event)
    if kind == ROW_VIRTUAL:
        lines.append(f"신규 필요 Qual {_iso(_as_date(event.get('목표 Qual')))}")
    else:
        lines.append(
            f"반입 {_iso(_as_date(event.get('반입일정')))} · Qual "
            f"{_iso(_as_date(event.get('Qual일정')))} (기여 시작 "
            f"{_iso(_as_date(event.get('기여 시작')))})"
        )
        confirmation = _qual_status(event)
        if confirmation:
            lines[-1] += f" · {html.escape(confirmation)}"
    if kind == ROW_SHORTENED:
        days = _whole(event.get("단축일수"))
        lines.append(
            f"단축 목표 Qual {_iso(_as_date(event.get('목표 Qual')))} · {_MINUS}{days or 0}일"
        )
        if bool(event.get("반입 전")):
            lines.append("⚠ 목표 Qual 이 반입일정보다 이릅니다(반입 전)")
    gain = _number(event.get("늘어난 환산대수"))
    if gain is not None:
        lines.append(f"늘어난 환산대수 +{gain:,.2f}")
    target_month = _whole(event.get("대상 월"))
    if target_month is not None:
        lines.append(f"대상 월 {month_label(target_month)}")
    resolved = _month_tuple(event.get("해소 기여 월"))
    if resolved:
        lines.append("해소 기여 월 " + ", ".join(month_label(month) for month in resolved))
    exit_day = _as_date(event.get("반출이설일"))
    if exit_day is not None:
        lines.append(f"{html.escape(str(event.get('반출이설구분') or ''))} {_iso(exit_day)}")
    per_module = event.get("모듈별 Qual")
    if isinstance(per_module, (tuple, list)) and per_module:
        parts = [
            f"{html.escape(str(item[0]))} {_iso(_as_date(item[1]))}"
            for item in per_module
            if isinstance(item, (tuple, list)) and len(item) == 2
        ]
        if parts:
            lines.append("모듈별 Qual " + ", ".join(parts))
    return "<br>".join(lines)


def _arrow_rows(axis: Sequence[int], dynamic: DynamicCanvasInput) -> tuple[list[_Row], int]:
    groups: dict[str, list[dict[str, object]]] = {}
    for record in _records(dynamic.arrows):
        key = str(record.get("설비키") or record.get("설비명"))
        groups.setdefault(key, []).append(record)
    units = list(groups)
    hidden = 0
    if not dynamic.show_all_arrows and len(units) > ROW_LIMIT:
        hidden = len(units) - ROW_LIMIT
        units = units[:ROW_LIMIT]
    rows: list[_Row] = []
    for unit in units:
        arrows = groups[unit]
        first = arrows[0]
        model = "" if _blank(first.get("Model")) else str(first.get("Model"))
        name = unit + (f" · {model}" if model else "")
        for lane, members in enumerate(_lanes(arrows)):
            rows.append(
                _Row(
                    f"{ROW_ARROW_PREFIX}{unit}#{lane}",
                    _ARROW,
                    ARROW_ROW_HEIGHT_PX,
                    label=name if lane == 0 else "⋯ 같은 호기",
                    label_muted=lane > 0,
                    label_fill=tokens.SURFACE_CLASSIFICATION,
                    payload=members,
                )
            )
            for index, month in enumerate(axis):
                rows[-1].cells[index] = _Cell(hover=_arrow_hover(members, month))
    if not rows:
        rows.append(_note_row("no_downtime", "조회기간에 비가동 일정이 없습니다"))
    if hidden:
        rows.append(_note_row("more_arrows", f"외 {hidden}대 — 「더 보기」를 켜면 모두 그립니다"))
    if dynamic.steady_units:
        rows.append(_note_row("steady", f"비가동 없이 축 내내 가용 {dynamic.steady_units}대"))
    return rows, hidden


def _lanes(arrows: Sequence[dict[str, object]]) -> list[list[dict[str, object]]]:
    """같은 호기의 화살표를 겹치지 않는 줄로 나눈다. 대개 한 줄이고, 모듈 둘이 함께 멈추면
    줄이 는다."""
    lanes: list[list[dict[str, object]]] = []
    ends: list[float] = []
    for arrow in sorted(arrows, key=lambda item: _number(item.get("꼬리 위치")) or 0.0):
        tail = _number(arrow.get("꼬리 위치")) or 0.0
        head = _number(arrow.get("촉 위치")) or tail
        for position, end in enumerate(ends):
            if tail >= end + _LANE_GAP_MONTHS:
                lanes[position].append(arrow)
                ends[position] = head
                break
        else:
            lanes.append([arrow])
            ends.append(head)
    return lanes


def _arrow_hover(arrows: Sequence[Mapping[str, object]], month: int) -> str:
    """④ 줄 풍선 — 첫 줄은 달·호기(모듈 묶음이면 「· 모듈 N」), 화살표마다 한 줄. 모듈 묶음은 줄마다
    그 화살표의 모듈 설비명을 앞에 적는다 — 어느 모듈이 멈췄는지(같은 호기 둘째 줄의 까닭)."""
    first = arrows[0]
    grouped = bool(_module_text(first))
    lines = [
        f"<b>{month_label(month)}</b> · {html.escape(str(first.get('설비키') or ''))}"
        + _module_text(first)
    ]
    for arrow in arrows:
        kind = html.escape(str(arrow.get("비가동유형") or "비가동"))
        start = _iso(_as_date(arrow.get("시작일")))
        end_day = _as_date(arrow.get("종료일"))
        end = _iso(end_day) if end_day is not None else "계속"
        losses = dict(_month_losses(arrow.get("달별 손실")))
        if bool(arrow.get("가용 감소")):
            loss = losses.get(month, 0.0)
            effect = f"이 달 {_signed_one(-loss) if loss else '0.0'} (환산대수)"
        else:
            effect = "가용 영향 없음(셋업·보관·사용기준 제외 등)"
        module = str(arrow.get(EQUIPMENT_ID_COLUMN) or "").strip() if grouped else ""
        head = f"{html.escape(module)} · " if module else ""
        lines.append(f"{head}{kind} · {start}~{end} · {effect}")
    return "<br>".join(lines)


def _target_text(target: TargetLevel, axis: Sequence[int]) -> str:
    values = {_target_for(target, month) for month in axis}
    if len(values) == 1:
        return f"단축 목표 {threshold_percent_label(next(iter(values)))}"
    return "단축 목표 = 확보기준(달마다)"


def _target_balance_label(target: TargetLevel, axis: Sequence[int]) -> str:
    values = {_target_for(target, month) for month in axis}
    if len(values) == 1:
        return f"목표({threshold_percent_label(next(iter(values)))}) 과부족"
    return "목표 과부족"


def _target_for(target: TargetLevel, month: int) -> float:
    return target.for_month(month) if isinstance(target, MonthlyTarget) else float(target)


# ================================================================== 월 Figure


def _month_figure(
    rows: Sequence[_Row],
    axis: Sequence[int],
    height: int,
    *,
    shortage_indices: Sequence[int],
    selected_index: int | None,
    today_x: float | None,
    dynamic_rows: Sequence[_Row],
    dynamic: DynamicCanvasInput | None,
) -> go.Figure:
    """엔진 월 Figure(`month_sheet_canvas.month_figure`)에 이 캔버스만의 그림을 훅으로 얹는다 —
    ③ 호기 줄의 선·표지와 ④ 화살표(행마다), 부족 달 띠(머리 뒤), 지금 보는 달 열과 오늘 점선(끝)."""
    count = len(axis)
    header_bottom = height - rows[0].height
    track = _Track()

    def draw_row(layers: MonthLayers, row: _Row, center: float, bottom: float) -> None:
        if row.kind == _UNIT and dynamic is not None:
            _draw_unit(track, row, axis, center, bottom, dynamic, layers.above, layers.annotations)
        elif row.kind == _ARROW:
            _draw_arrows(track, row, center, count)

    def draw_shortage(layers: MonthLayers) -> None:
        for index in shortage_indices:
            layers.above.append(
                _data_rect(
                    index + 1 / tokens.MONTH_COLUMN_WIDTH_PX,
                    index + 1 - 1 / tokens.MONTH_COLUMN_WIDTH_PX,
                    header_bottom,
                    header_bottom + SHORTAGE_STRIP_PX,
                    tokens.STATUS_SHORTAGE,
                    layer="above",
                )
            )
            # 부족 달 세로 띠 — 행 면 위·칸 색 아래, 머리 아래부터 캔버스 끝까지 같은 달에 이어진다.
            layers.below.append(
                _data_rect(index, index + 1, 0, header_bottom, tokens.SHORTAGE_MONTH_BAND)
            )

    def finish(layers: MonthLayers) -> None:
        if selected_index is not None:
            underline_y = header_bottom + 8
            layers.above.append(
                {
                    "type": "line",
                    "x0": selected_index + 0.24,
                    "x1": selected_index + 0.76,
                    "y0": underline_y,
                    "y1": underline_y,
                    "xref": "x",
                    "yref": "y",
                    "line": {"color": tokens.ACCENT, "width": SELECTED_UNDERLINE_PX},
                    "layer": "above",
                }
            )
            edge = 1 / tokens.MONTH_COLUMN_WIDTH_PX
            layers.above.append(
                {
                    "type": "rect",
                    "x0": selected_index + edge,
                    "x1": selected_index + 1 - edge,
                    "y0": 1,
                    "y1": height - 1,
                    "xref": "x",
                    "yref": "y",
                    "fillcolor": tokens.TRANSPARENT,
                    "line": {"color": tokens.ACCENT, "width": SELECTED_BORDER_PX},
                    "layer": "above",
                }
            )
        if today_x is not None:
            # 오늘 점선 — ②~④ 본문에만 긋고 구획 제목 줄은 건너뛴다(제목 글을 가르지 않는다).
            # 무엇인지는 ② 제목 줄 글이 적는다.
            layers.above += [
                {
                    "type": "line",
                    "x0": today_x,
                    "x1": today_x,
                    "y0": height - (end.top + end.height),
                    "y1": height - start.top,
                    "xref": "x",
                    "yref": "y",
                    "line": {"color": tokens.TEXT_MUTED, "width": 1, "dash": "dash"},
                    "layer": "above",
                }
                for start, end in _body_runs(dynamic_rows)
            ]
        layers.traces += track.traces()

    return _engine_month_figure(
        rows,
        axis,
        height,
        row_hook=draw_row,
        header_hook=draw_shortage,
        finish_hook=finish,
    )


def _body_runs(rows: Sequence[_Row]) -> list[tuple[_Row, _Row]]:
    """제목 줄로 끊긴 본문 행의 이어진 덩어리마다 (첫 행, 끝 행)."""
    runs: list[tuple[_Row, _Row]] = []
    start: _Row | None = None
    previous: _Row | None = None
    for row in rows:
        if row.kind == _TITLE:
            if start is not None and previous is not None:
                runs.append((start, previous))
            start = None
        elif start is None:
            start = row
        previous = row
    if start is not None and previous is not None:
        runs.append((start, previous))
    return runs


# ------------------------------------------------------------------ ③ 호기 줄


class _Track:
    """③·④ 의 선·표지. 종류마다 trace 하나로 모은다(선은 None 으로 끊는다)."""

    def __init__(self) -> None:
        self.baseline_x: list[float | None] = []
        self.baseline_y: list[float | None] = []
        self.arrival = _Points()
        self.start = _Points()
        self.pull_x: list[float | None] = []
        self.pull_y: list[float | None] = []
        self.pull_head = _Points()
        self.pull_text = _Points()
        self.virtual_text = _Points()
        self.exit = _Points()
        self.loss_x: list[float | None] = []
        self.loss_y: list[float | None] = []
        self.idle_x: list[float | None] = []
        self.idle_y: list[float | None] = []
        self.loss_head = _Points()
        self.arrow_text = _Points()

    def traces(self) -> list[Any]:
        text_font = {"color": tokens.TEXT, "size": TRACK_TEXT_FONT_PX, "family": tokens.FONT_FAMILY}
        loss_color = tokens.EQUIPMENT_STAGE_COLORS["운영 비가동"]
        traces: list[Any] = []
        if self.baseline_x:
            traces.append(
                _line_trace(self.baseline_x, self.baseline_y, tokens.BORDER, 1.0, dash="dot")
            )
        if self.idle_x:
            traces.append(_line_trace(self.idle_x, self.idle_y, tokens.TEXT_MUTED, 1.5, dash="dot"))
        if self.loss_x:
            traces.append(_line_trace(self.loss_x, self.loss_y, loss_color, 3.0))
        if self.pull_x:
            traces.append(_line_trace(self.pull_x, self.pull_y, tokens.TEXT, 3.0))
        if self.arrival.x:
            traces.append(_marker_trace(self.arrival, "diamond", 9, tokens.TEXT_MUTED))
        if self.start.x:
            traces.append(
                _marker_trace(self.start, "circle", 12, self.start.color, outline=tokens.TEXT)
            )
        if self.pull_head.x:
            traces.append(_marker_trace(self.pull_head, "triangle-left", 12, tokens.TEXT))
        if self.exit.x:
            traces.append(
                _marker_trace(self.exit, "triangle-down", 11, self.exit.color, outline=tokens.TEXT)
            )
        if self.loss_head.x:
            traces.append(_marker_trace(self.loss_head, "triangle-right", 11, loss_color))
        for points, position, font in (
            (self.pull_text, "middle left", {**text_font, "size": TRACK_TEXT_FONT_PX}),
            (self.virtual_text, "middle right", text_font),
            (
                self.arrow_text,
                "middle right",
                {**text_font, "color": tokens.TEXT_MUTED, "size": ARROW_TEXT_FONT_PX},
            ),
        ):
            if points.x:
                traces.append(
                    go.Scatter(
                        x=points.x,
                        y=points.y,
                        mode="text",
                        text=points.text,
                        textposition=position,
                        textfont=font,
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )
        return traces


def _line_trace(
    x: list[float | None], y: list[float | None], color: str, width: float, *, dash: str = "solid"
) -> Any:
    return go.Scatter(
        x=x,
        y=y,
        mode="lines",
        line={"color": color, "width": width, "dash": dash},
        hoverinfo="skip",
        showlegend=False,
    )


def _marker_trace(
    points: _Points,
    symbol: str,
    size: int,
    color: str | list[str],
    *,
    outline: str | None = None,
) -> Any:
    return go.Scatter(
        x=points.x,
        y=points.y,
        mode="markers",
        marker={
            "symbol": symbol,
            "size": size,
            "color": color,
            "line": {"color": outline or tokens.TRANSPARENT, "width": 1.2 if outline else 0},
        },
        hoverinfo="skip",
        showlegend=False,
    )


def _draw_unit(
    track: _Track,
    row: _Row,
    axis: Sequence[int],
    center: float,
    bottom: float,
    dynamic: DynamicCanvasInput,
    shapes: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
) -> None:
    count = len(axis)
    track.baseline_x += [0.0, float(count), None]
    track.baseline_y += [center, center, None]
    kind, record = row.payload

    def inside(day: date | None) -> float | None:
        if day is None:
            return None
        position = production_position(day, dynamic.cutoff_days, axis)
        return None if position.before or position.after else position.x

    if kind == "exit":
        exit_x = inside(_as_date(record.get("반출이설일")))
        if exit_x is not None:
            track.exit.add(x=exit_x, y=center, color=_exit_color(record.get("반출이설구분")))
        return
    line = str(record.get("줄"))
    if line == ROW_VIRTUAL:
        target_x = _number(record.get("목표 기여 위치"))
        if target_x is None:
            return
        radius = 6.0
        half = radius / tokens.MONTH_COLUMN_WIDTH_PX
        # 추가N ◌ — 부족 면에 점선 테두리. Plotly 표지는 테두리를 점선으로 못 그려 도형으로 둔다.
        shapes.append(
            {
                "type": "circle",
                "x0": target_x - half,
                "x1": target_x + half,
                "y0": center - radius,
                "y1": center + radius,
                "xref": "x",
                "yref": "y",
                "fillcolor": tokens.STATUS_SHORTAGE,
                "line": {"color": tokens.TEXT, "width": 1.5, "dash": "dot"},
                "layer": "above",
            }
        )
        track.virtual_text.add(x=target_x + 0.1, y=center, text="<b>신규 필요</b>")
        _resolved_ticks(record, axis, bottom, shapes)
        return
    arrival_x = inside(_next_day(_as_date(record.get("반입일정"))))
    if arrival_x is not None:
        track.arrival.add(x=arrival_x, y=center)
    start_x = _number(record.get("기여 시작 위치"))
    clipped = bool(record.get("기여 시작 축 밖"))
    if line == ROW_SHORTENED:
        target_x = _number(record.get("목표 기여 위치"))
        if target_x is not None and start_x is not None:
            track.pull_x += [start_x, target_x, None]
            track.pull_y += [center, center, None]
            track.pull_head.add(x=target_x, y=center)
            days = _whole(record.get("단축일수")) or 0
            label = f"{_MINUS}{days}일"
            track.pull_text.add(x=target_x - 0.08, y=center, text=f"<b>{label}</b>")
            if bool(record.get("반입 전")):
                label_px = _text_width_units(label) * TRACK_TEXT_FONT_PX
                annotations.append(
                    {
                        "x": target_x - 0.08 - (label_px + 8) / tokens.MONTH_COLUMN_WIDTH_PX,
                        "y": center,
                        "xref": "x",
                        "yref": "y",
                        "xanchor": "right",
                        "yanchor": "middle",
                        "text": "<b>반입 전</b>",
                        "showarrow": False,
                        "bgcolor": tokens.STATUS_WARNING,
                        "borderpad": 2,
                        "font": {
                            "color": tokens.TEXT,
                            "size": ARROW_TEXT_FONT_PX,
                            "family": tokens.FONT_FAMILY,
                        },
                    }
                )
        _resolved_ticks(record, axis, bottom, shapes)
    if start_x is not None and not clipped:
        track.start.add(
            x=start_x, y=center, color=_confirmation_color(record.get(QUAL_STATUS_COLUMN))
        )
    exit_x = inside(_as_date(record.get("반출이설일")))
    if exit_x is not None:
        track.exit.add(x=exit_x, y=center, color=_exit_color(record.get("반출이설구분")))


def _resolved_ticks(
    record: Mapping[str, object], axis: Sequence[int], bottom: float, shapes: list[dict[str, Any]]
) -> None:
    """「해소 기여 월」 칸 아래 가장자리 2px 눈금 — 이 호기가 메운 달."""
    positions = {month: index for index, month in enumerate(axis)}
    for month in _month_tuple(record.get("해소 기여 월")):
        index = positions.get(month)
        if index is None:
            continue
        shapes.append(
            {
                "type": "line",
                "x0": index + 0.35,
                "x1": index + 0.65,
                "y0": bottom + 2,
                "y1": bottom + 2,
                "xref": "x",
                "yref": "y",
                "line": {"color": tokens.TEXT, "width": 2},
                "layer": "above",
            }
        )


def _confirmation_color(value: object) -> str:
    colors = tokens.QUAL_CONFIRMATION_COLORS
    name = "" if _blank(value) else str(value).strip()
    return colors.get(name, colors["계획"])


def _exit_color(value: object) -> str:
    stage = STATUS_EXITED if str(value).strip() == EXIT_KIND_RELOCATION else STATUS_STOPPED
    return tokens.EQUIPMENT_STAGE_COLORS[stage]


def _qual_status(event: Mapping[str, object]) -> str:
    """그 줄의 Qual상태 글자. 비었으면 빈 글자다."""
    value = event.get(QUAL_STATUS_COLUMN)
    return "" if _blank(value) else str(value)


# ------------------------------------------------------------------ ④ 화살표


def _draw_arrows(track: _Track, row: _Row, center: float, count: int) -> None:
    line_y = center - 4
    head_half = 5 / tokens.MONTH_COLUMN_WIDTH_PX
    for arrow in row.payload:
        tail = max(0.0, _number(arrow.get("꼬리 위치")) or 0.0)
        head = min(float(count), _number(arrow.get("촉 위치")) or tail)
        if bool(arrow.get("가용 감소")):
            tip = max(tail, head - head_half)
            track.loss_x += [tail, tip, None]
            track.loss_y += [line_y, line_y, None]
            track.loss_head.add(x=tip, y=line_y)
        else:
            track.idle_x += [tail, head, None]
            track.idle_y += [line_y, line_y, None]
        kind = str(arrow.get("비가동유형") or "비가동").strip()
        if len(kind) > ARROW_TYPE_MAX_CHARS:
            kind = kind[:ARROW_TYPE_MAX_CHARS] + "…"
        label = html.escape(kind)
        if bool(arrow.get("이전부터")):
            label += " · ◂ 이전부터"
        if bool(arrow.get("열린 구간")):
            label += " · 계속 ▸"
        track.arrow_text.add(x=tail + 0.02, y=center + 6, text=label)


# ================================================================== 값 다루기


def _by_month(
    frame: pd.DataFrame, axis: Sequence[int], *, unique: bool = False
) -> dict[int, dict[str, object]]:
    if frame.empty or MONTH not in frame.columns:
        return {}
    wanted = set(axis)
    result: dict[int, dict[str, object]] = {}
    for record in frame.to_dict("records"):
        month = _whole(record.get(MONTH))
        if month is None or month not in wanted:
            continue
        if month in result and unique:
            raise ValueError(
                f"설비 일정 계획에 같은 달({month})이 두 번 있습니다 — 공정 하나로 거른 표를 "
                "넘깁니다."
            )
        result.setdefault(month, {str(key): value for key, value in record.items()})
    return result


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [{str(key): value for key, value in row.items()} for row in frame.to_dict("records")]


def _status(value: object) -> str | None:
    if _blank(value):
        return None
    text = str(value)
    return text if text in _STATUS_NAMES else None


def _status_color(status: str | None) -> str | None:
    if status is None:
        return None
    return {
        "secure": tokens.STATUS_SECURE,
        "warning": tokens.STATUS_WARNING,
        "shortage": tokens.STATUS_SHORTAGE,
    }[status]


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (tuple, list)):
        return False
    return bool(pd.isna(cast(Any, value)))


def _number(value: object) -> float | None:
    if _blank(value) or isinstance(value, bool):
        return None
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _whole(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(round(number))


def _as_date(value: object) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.Timestamp(str(value)).date()
    except (TypeError, ValueError):
        return None


def _next_day(day: date | None) -> date | None:
    return None if day is None else day + timedelta(days=1)


def _month_tuple(value: object) -> tuple[int, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(month for item in value if (month := _whole(item)) is not None)
    if _blank(value):
        return ()
    return tuple(
        month for part in str(value).split(",") if (month := _whole(part.strip())) is not None
    )


def _month_losses(value: object) -> list[tuple[int, float]]:
    """화살표의 `달별 손실`(((YYYYMM, 환산대수), …))을 정수 달·실수 손실 짝으로."""
    if not isinstance(value, (tuple, list)):
        return []
    pairs: list[tuple[int, float]] = []
    for item in value:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        month, loss = _whole(item[0]), _number(item[1])
        if month is not None and loss is not None:
            pairs.append((month, loss))
    return pairs


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None:
        return None
    return left - (right or 0.0)


def _changed(before: float | None, after: float | None) -> bool:
    return before is not None and after is not None and abs(after - before) > 1e-9


def _ratio(value: float) -> str:
    """판정 기준 비율을 사람이 적은 꼴로(1.095 → 「1.095」)."""
    return f"{value:g}"


def _two(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:,.2f}"


def _signed_two(value: float) -> str:
    """부호 있는 소수 둘째 자리. 과부족처럼 9자리 반올림으로 부동소수 먼지를 턴 뒤 찍어 「−0.00」 이
    나오지 않는다 — 0 은 「0.00」."""
    rounded = round(round(value, 9), 2)
    if rounded > 0:
        return f"+{rounded:,.2f}"
    if rounded < 0:
        return f"{_MINUS}{abs(rounded):,.2f}"
    return "0.00"


def _day(day: date | None, today: date) -> str:
    return "미정" if day is None else month_day(day, today=today)


def _iso(day: date | None) -> str:
    return "미정" if day is None else f"{day:%Y-%m-%d}"


# 줄 나누기(`_fit`)가 위에서 정의된 뒤에 센다.
SUMMARY_TITLE_HEIGHT_PX: Final = title_row_height(SUMMARY_TITLE_DETAIL)
