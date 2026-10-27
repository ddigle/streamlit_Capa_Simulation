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
   칠한다), 가용(환산, 단축 후는 둘째 줄), 전월 대비, 비가동 영향(그 달 비가동이 깎은 가용
   「−1.8대」 와 둘째 줄 확보율 영향 「−4.2%p」 — 깎은 것이 없으면 빈칸, 소요 0 이면 대수만), 목표
   과부족(음수만 칠한다, 단축 후·기한 지남은 둘째 줄). 목표는 달마다 다른 확보기준이다
   (`MonthlyTarget`).
3. **③ 신규 설비** — 호기마다 한 줄. ◆ 반입 · ● 기여 시작(Qual상태 색), 단축 대상이면 같은 줄에
   ◀ 목표 기여 시작과 「−N일」, 목표 Qual 이 반입보다 이르면 「반입 전」 배지. 축 안에서
   정지·반출/이설되는 다른 호기는 ▼ 한 줄, 추가N(◌)은 맨 아래. 30행 상한(`ROW_LIMIT`)을 넘으면
   「n대 더」 한 줄이다.
4. **④ 호기별 비가동** — 비가동 한 행이 화살표 하나. 가용을 깎은 것만 진한 실선과 촉, 나머지는 흐린
   점선이다. 글자는 비가동유형과 「◂ 이전부터」·「계속 ▸」. 축 안에 입력 비가동(가용설비 현황 ›
   Preference — 공정 × 생산월 대수)이 있으면 구획 첫 줄이 「월별 비가동 대수(입력)」 이다 —
   달마다 넣은 대수이고, 그 달 가용보다 커 0 에서 멈춘 칸은 「⚠」 와 경고색이다. ② 가용·전월
   대비 「비가동」 은 이 몫을 이미 뺐다(호기별 비가동과 별도 손실). 호기 줄이 없는
   공정(기존보유만)은 ② 아래에 선다.

호기·Model 라벨에는 모듈 수를 적지 않는다(2026-10-22 사용자 요청) — 모듈 묶음은 풍선이
밝힌다. ③ 호기 줄·정지 줄 풍선 첫 줄에 「· 모듈 N」, ④ 풍선 첫 줄에 「· 모듈 N」과 화살표
줄마다 그 모듈의 설비명이다.

**③ 풍선은 세 줄이고 그림 위에서만 뜬다**(2026-10-24 사용자 결정 (가)) — 「호기 · −N일 · Model」,
「Qual MM.DD → 목표 MM.DD · MM.DD부터 기여 +0.10대」, 「해소 YY.MM · ⚠ 반입 전」(`_unit_hover`).
반입일·Qual상태·대상 월은 그림 표지(◆ · ● 색)와 CSV 가 말해 적지 않고, UPEH 가정 계획만 넷째
줄이다. 줄 이름 칸의 「+0.10대」 는 호기 하나의 요약(대상 월 구간의 몫 — CSV
`늘어난 환산대수`)이고, 단축 · 추가N 줄의 **달 칸**은 그 자리에 그 달 몫 「· 이 달 +0.57대」 를
적는다(그 달 몫이 없으면 숫자를 뺀다) — 앞 달에 당긴 호기가 뒤 달을 메운 몫은 대상 월 몫과
다르다. 그 호기 그림(선·화살표·표지와 붙은 글자)이 걸친 달 칸과 줄 이름 칸(라벨 Figure 의
`label_hover`)에서만 뜨고, 빈 달 칸은 풍선 없는 표적이라 누르면 그 달만 골라진다. 풍선 칸과 그림은
한 자리(`_unit_marks`)에서 낸다 — 표지는 반지름까지, 붙은 글자는 어림 폭의 몫
(`_SPAN_TEXT_SHARE`)까지 센다(어림만 달 경계를 넘은 빈 칸에 풍선이 뜨지 않게).

**UPEH 가정**(`assumption` — 공정 Capa 상세 조건 카드의 「이 세션만」 값)이 켜지면 ① 끝(기준 확보율
아래)에 「UPEH 가정」 세 줄(소요대수·확보율·확보기준 과부족)이 선다 — 구간 달만 값이고 밖은
빈칸이다(풍선 「구간 밖 — 공식과 같음」). ① 의 공식 줄은 공식 그대로다. **판정 기준은 하나다** —
가정이 켜지면 부족 띠·② 판정 대조는 가정 요약의 판정으로 칠한다(②~④ 가 가정 계획이라 한 그림에서
공식 판정과 섞이지 않게) — ② 판정 대조 풍선도 「공식은 …」 이 아니라 「UPEH 가정 기준은 …」
이다. 「UPEH 가정」 표지는 실제로 바뀌는 행에만 단다 — 가정 세 줄, ② 판정 대조·비가동 영향(%p 가
가정 소요로 바뀐다)·목표 과부족의 행 라벨, ③ 호기 풍선. ② 가용·전월 대비와 ④ 는 설비 일정이라
UPEH 와 무관하다.
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

**풍선의 식**(① 가용 「보유 − 대여」·확보율 「가용 ÷ 소요」·과부족 「가용 − 소요 × 기준」, UPEH 가정
소요 「공식 ÷ f」, ② 목표 과부족 「가용 − 목표대수」)은 인수를 칸 자릿수로 적고, 적힌 수로 다시 셈한
값이 결과와 다르면 「=」 대신 「≈」 다(`formula_text.equals_mark` — 근거 패널 ③·④ 와 같은 길). 두
과부족 식 줄과 ② 비가동 영향 풍선의 두 식(「비가동 없으면 확보율 X% → 지금 Y%」 — 첫 줄
%p 를 낸다, 「호기 비가동 −a대 + 입력 비가동 −b대」 — 첫 줄 대수를 낸다)은 결과가 앞 줄에
있고 등호가 없어 어긋날 때만 식 앞에 「≈」 를 둔다.

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

from capa_simulation.components.formula_text import APPROX, EQUALS, equals_mark, written_value
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
from capa_simulation.services.manual_downtime import MANUAL_DOWNTIME_BAND, manual_units_text
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
    downtime_impact,
    month_share,
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
    "IMPACT_LABEL_HOVER",
    "MANUAL_DOWNTIME_ROW_LABEL",
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
    "ROW_DYNAMIC_IMPACT",
    "ROW_EXIT_PREFIX",
    "ROW_HEADER",
    "ROW_HOME_RATE",
    "ROW_LIMIT",
    "ROW_MANUAL_DOWNTIME",
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
# ③ 표지 둘레 글자 — 단축 촉 왼쪽 「−N일」(촉에서 달 단위 0.08 떨어짐)과 그 왼쪽 「반입 전」
# 배지(8px 틈·안쪽 여백 2px), 추가N ◌(반지름 6px)과 그 오른쪽 「신규 필요」(달 단위 0.1 떨어짐).
_PULL_TEXT_GAP: Final = 0.08
_BADGE_GAP_PX: Final = 8
_BADGE_PAD_PX: Final = 2
_BEFORE_ARRIVAL_TEXT: Final = "반입 전"
_VIRTUAL_RADIUS_PX: Final = 6.0
_VIRTUAL_TEXT_GAP: Final = 0.1
_VIRTUAL_TEXT: Final = "신규 필요"
# ③ 표지 크기(px, Plotly `marker.size` — 지름). 풍선 칸(`_unit_span`)도 이 반지름까지 센다 — 달
# 경계에 선 표지는 앞뒤 두 달 칸에 반씩 그려진다.
_ARRIVAL_MARKER_PX: Final = 9
_START_MARKER_PX: Final = 12
_PULL_HEAD_MARKER_PX: Final = 12
_EXIT_MARKER_PX: Final = 11
# 풍선 칸을 셀 때 쓰는 글자 폭 몫. 글자 폭 어림(`_text_width_units` — 전각 1.0 · 반각 0.6)은 넘치지
# 않게 잡은 위 끝이라 렌더 폭보다 넓다(headless Chrome 「−198일」 34.9px ↔ 어림 37.4px, 「반입 전」
# 배지 35px ↔ 40px). 어림 그대로 세면 그림은 달 경계 안인데 어림만 앞 달로 넘어가 아무것도 없는 칸에
# 풍선이 뜬다 — 어림의 이 몫까지만 센다.
_SPAN_TEXT_SHARE: Final = 0.85
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
# ② 「비가동 영향」 — 전월 대비 바로 아래. 그 달 비가동(호기 + 입력)이 깎은 가용과 확보율 영향(%p).
ROW_DYNAMIC_IMPACT: Final = "dynamic_impact"
IMPACT_LABEL_HOVER: Final = (
    "그 달 비가동이 없었다면 더 있었을 가용(환산)과 그만큼의 확보율 차이(%p)<br>"
    "호기 비가동(④ 진한 화살표) + 입력 비가동(Preference — 가용에서 실제로 뺀 몫)<br>"
    "확보율 = 단축 전 가용 ÷ 소요 · 깎은 것이 없으면 빈칸 · 소요 0 이면 대수만"
)
# ④ 첫 줄 「월별 비가동 대수(입력)」 — 축 안에 입력 비가동이 있을 때만 선다.
ROW_MANUAL_DOWNTIME: Final = "manual_downtime"
MANUAL_DOWNTIME_ROW_LABEL: Final = "월별 비가동 대수(입력)"
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
            axis, statuses, causes, dynamic, folded, assumed=assumption is not None
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
        available.cells[index] = _Cell(
            text=f"{_one(available_count)}{' ⚠' if mismatch else ''}",
            hover=_available_hover(head, available_count, owned_count, lent_count, mismatch),
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
        change = _assumed_change(official_demand, demand, factor)
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


def _available_hover(
    head: str,
    available: float | None,
    owned: float | None,
    lent: float | None,
    mismatch: bool,
) -> str:
    """가용대수 칸 풍선 — 「보유 − 대여 = 가용」. 적힌 수로 다시 셈한 값이 결과와 다르면 「≈」."""
    derived = _difference(owned, lent)
    written = _difference(
        None if owned is None else round(owned, 1), None if lent is None else round(lent, 1)
    )
    text = (
        f"{head} · 가용대수 {_one(available)}대"
        f"<br>보유 {_one(owned)} {_MINUS} 대여 {_one(lent)} "
        f"{equals_mark(_one(derived), _one(written))} {_one(derived)}"
    )
    if mismatch:
        text += "<br>⚠ 가용대수가 보유 − 대여와 다릅니다(기준정보 표를 따로 고쳤습니다)"
    return text


def _assumed_change(official: float | None, demand: float | None, factor: float) -> str:
    """UPEH 가정 소요 칸 풍선의 둘째 줄 — 「공식 49.80 ÷ 1.5 = 33.20 (−16.60대)」. 적힌 공식
    소요로 다시 셈한 값이 가정 소요와 다르면 「≈」(근거 패널 ③ 의 「소요 = 공식 ÷ f」 와 같다)."""
    if official is None or demand is None:
        return ""
    mark = equals_mark(_two(demand), _two(round(official, 2) / factor))
    return (
        f"<br>공식 {_two(official)} ÷ {factor:g} {mark} {_two(demand)} "
        f"({_signed_two(demand - official)}대)"
    )


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
    # 적힌 가용·소요(첫째 자리)로 다시 셈한 확보율이 적힌 확보율과 다르면 「≈」.
    written_demand = None if demand is None else round(demand, 1)
    mark = equals_mark(
        _percent(rate),
        _percent(round(available, 1) / written_demand)
        if available is not None and written_demand
        else "",
    )
    return (
        f"{head} · 확보율 {_percent(rate)} {mark} 가용 {_one(available)} ÷ 소요 {_one(demand)}"
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
    # 정수 옆에 올림·내림 전 값(가용 − 소요 × 확보기준)을 소수 둘째 자리로 단다. 그 아래 식의
    # 적힌 가용·소요(첫째 자리)로 다시 셈한 값이 그 값과 다르면 식 앞에 「≈」 를 둔다.
    unrounded = ""
    mark = EQUALS
    if available is not None and demand is not None:
        raw = _signed_two(available - demand * secure)
        unrounded = f" ({raw})"
        mark = equals_mark(raw, _signed_two(round(available, 1) - round(demand, 1) * secure))
    text = (
        f"{head} · 확보기준 과부족 {_signed_int(balance)}대{unrounded}"
        f"<br>{f'{APPROX} ' if mark == APPROX else ''}가용 {_one(available)} {_MINUS} "
        f"소요 {_one(demand)} × {_ratio(secure)} (부족은 올림, 여유는 내림)"
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
    *,
    assumed: bool = False,
) -> tuple[list[_Row], int, int]:
    """② ~ ④ 행. `assumed` 면 `statuses`·`causes` 가 UPEH 가정 요약의 판정이다 — ② 판정 대조 풍선이
    그 기준을 「UPEH 가정 기준」 이라 부른다(공식 값은 ① 공식 줄과 KPI 회색 줄에만)."""
    today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
    # 오늘이 든 생산월보다 앞선 달은 「기한 지남」이다 — 단축으로 바꿀 수 없어 흐리게 둔다.
    today_month = today_position.month
    plan = _by_month(dynamic.process_months, axis, unique=True)
    bridge = _by_month(dynamic.bridge, axis)
    impacts = _by_month(downtime_impact(dynamic.bridge, dynamic.process_months), axis)
    target_text = _target_text(dynamic.target, axis)
    detail = f"참고 · 설비 DB · 환산대수 · 생산월(Cut-off {dynamic.cutoff_days}일)"
    if any(
        round(_number(bridge.get(month, {}).get("입력 비가동")) or 0.0, 9) > 0 for month in axis
    ):
        detail += f" · {MANUAL_DOWNTIME_BAND}"
    if not today_position.before and not today_position.after:
        detail += f" · 점선은 오늘({dynamic.today:%m.%d})"
    rows: list[_Row] = [_section_title_row(SECTION_DYNAMIC, detail, folded)]
    # UPEH 가정 계획이면 바뀌는 행(판정 대조·비가동 영향 %p·목표 과부족)의 라벨에만 표지를 단다 —
    # 제목 줄 높이는 그대로다.
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
    # 대수와 %p 를 한 줄에 적으면 달 칸(100px)을 넘는다 — 가용 (환산)·목표 과부족처럼 둘째 줄에 %p.
    impact = _Row(
        ROW_DYNAMIC_IMPACT,
        _VALUE,
        TWO_LINE_ROW_HEIGHT_PX,
        label=f"비가동 영향{assumed_mark}",
        label_fill=tokens.SURFACE_CLASSIFICATION,
        label_hover=IMPACT_LABEL_HOVER,
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
            for row in (compare, available, impact, balance):
                row.cells[index] = _Cell(
                    text=_EMPTY, muted=True, hover=f"{head} · 설비 일정 계획에 없는 달"
                )
        else:
            before = _number(record.get("가용대수"))
            after = _number(record.get("단축후가용대수"))
            removed = _number(bridge.get(month, {}).get("입력 비가동 반영")) or 0.0
            gap = _number(record.get("과부족"))
            gap_after = _number(record.get("단축후과부족"))
            target_units = _number(record.get("목표대수"))
            state = "" if _blank(record.get("상태")) else str(record.get("상태"))
            dynamic_short = gap is not None and round(gap, 9) < 0
            compare.cells[index] = _compare_cell(
                head,
                static_short,
                dynamic_short,
                cause=causes.get(month, ""),
                past=past,
                assumed=assumed,
            )
            available.cells[index] = _Cell(
                text=_one(before),
                sub=f"→ {_one(after)}" if _changed(before, after) else "",
                muted=past,
                hover=(
                    f"{head} · 설비 일정 기준 가용 {_one(before)} (환산대수)"
                    + (f"<br>입력 비가동 {_signed_one(-removed)} 반영" if removed > 0 else "")
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
            impact.cells[index] = _impact_cell(
                head, impacts.get(month, {}), past=past, assumed=dynamic.official_pulls is not None
            )
        bridge_record = bridge.get(month, {})
        change = _number(bridge_record.get("전월대비"))
        manual_change = _number(bridge_record.get("입력 비가동 증감")) or 0.0
        delta.cells[index] = _Cell(
            text=_signed_one(change) if change is not None else _EMPTY,
            muted=past,
            hover=(
                f"{head} · 전월 대비 {_signed_one(change)} = 신규 "
                f"{_signed_one(_number(bridge_record.get('신규')) or 0.0)} · 비가동 "
                f"{_signed_one(_number(bridge_record.get('비가동')) or 0.0)}"
                + (
                    f"(입력 비가동 {_signed_one(manual_change)} 포함)"
                    if round(manual_change, 9) != 0
                    else ""
                )
                + " · 정지·반출/이설 "
                f"{_signed_one(_number(bridge_record.get('반출이설')) or 0.0)}"
                if change is not None
                else f"{head} · 축 첫 달이라 전월 대비가 없습니다"
            ),
        )
    if SECTION_DYNAMIC not in folded:
        rows += [compare, available, delta, impact, balance]
    manual_row = _manual_downtime_row(axis, bridge, today_month)
    if not dynamic.has_units:
        # 호기 줄이 없는 공정은 ④ 가 서지 않는다 — 입력 비가동 줄은 ② 아래에 둔다(② 를 접으면 함께
        # 접는다).
        if manual_row is not None and SECTION_DYNAMIC not in folded:
            rows.append(manual_row)
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
        if manual_row is not None:
            rows.append(manual_row)
        arrow_rows, hidden_arrow_units = _arrow_rows(axis, dynamic)
        rows += arrow_rows
    return rows, hidden_units, hidden_arrow_units


def _manual_downtime_row(
    axis: Sequence[int], bridge: Mapping[int, Mapping[str, object]], today_month: int
) -> _Row | None:
    """④ 첫 줄 「월별 비가동 대수(입력)」 — 축 안 어느 달에도 입력이 없으면 None(줄이 없다).

    칸 글은 그 달에 넣은 대수(소수 둘째 자리까지)이고 빈 달은 비운다. 입력이 그 달 가용(기존보유 +
    호기 가용)보다 커 가용이 0 에서 멈춘 칸은 「⚠」 와 경고색이다 — 풍선이 실제로 뺀 몫을 적는다.
    """
    entered = {month: _number(bridge.get(month, {}).get("입력 비가동")) or 0.0 for month in axis}
    if not any(round(value, 9) > 0 for value in entered.values()):
        return None
    row = _Row(
        ROW_MANUAL_DOWNTIME,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=MANUAL_DOWNTIME_ROW_LABEL,
        label_fill=tokens.SURFACE_CLASSIFICATION,
        label_hover=(
            "가용설비 현황 › Preference 에서 공정 × 달로 넣은 비가동 대수(환산)<br>"
            "호기별 비가동과 별도 손실 — ② 가용에서 이미 뺐습니다"
        ),
    )
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        value = entered[month]
        if round(value, 9) <= 0:
            row.cells[index] = _Cell(hover=f"{head} · 입력 비가동 없음")
            continue
        removed = _number(bridge.get(month, {}).get("입력 비가동 반영")) or 0.0
        overdrawn = round(value - removed, 9) > 0
        text = manual_units_text(value)
        row.cells[index] = _Cell(
            text=f"{text}⚠" if overdrawn else text,
            muted=month < today_month and not overdrawn,
            text_color=tokens.STATUS_WARNING if overdrawn else None,
            hover=(
                f"{head} · 입력 비가동 {text}대 — 가용에서 {_one(removed)} 뺌"
                + (
                    "<br>⚠ 그 달 가용보다 커 가용이 0 에서 멈췄습니다(넘친 만큼은 빼지 않음)"
                    if overdrawn
                    else ""
                )
            ),
        )
    return row


def _impact_cell(
    head: str, record: Mapping[str, object], *, past: bool, assumed: bool = False
) -> _Cell:
    """② 비가동 영향 칸 하나 — `downtime_impact` 한 행(없으면 빈 dict).

    깎은 것이 없으면(손실 0) 빈칸이다. 첫 줄은 손실 대수 「−1.8대」, 둘째 줄은 확보율 영향
    「−4.2%p」 이고 소요가 0 이면(영향 NaN) 대수만 적는다. 풍선 둘째 줄은 「비가동 없으면 확보율
    X% → 지금 Y%」 와 손실의 갈림(0 인 쪽은 뺀다)이다. 둘 다 결과가 첫 줄에 있는 등호 없는 식이라
    적힌 수로 다시 셈한 글이 첫 줄과 다를 때만 그 식 앞에 「≈」 를 둔다(과부족 풍선과 같은 길) —
    갈림 둘을 적힌 대로 더한 값이 첫 줄 대수와, 적힌 Y − X 가 첫 줄 %p 와 견줄 짝이다(X·Y 를 소수
    첫째 자리로 따로 반올림하면 %p 와 0.1 어긋날 수 있다).
    """
    units_loss = _number(record.get("호기 비가동 손실")) or 0.0
    manual_loss = _number(record.get("입력 비가동 손실")) or 0.0
    loss = _number(record.get("비가동 손실")) or 0.0
    if round(loss, 9) <= 0:
        return _Cell(muted=past, hover=f"{head} · 비가동 영향 없음 — 가용을 깎은 비가동이 없습니다")
    points = _number(record.get("확보율 영향(%p)"))
    points_number = _nonzero_signed(-points) if points is not None else ""
    units_text = f"{_nonzero_signed(-loss)}대"
    points_text = f"{points_number}%p" if points_number else ""
    parts = [
        f"{name} {_nonzero_signed(-value)}대"
        for name, value in (("호기 비가동", units_loss), ("입력 비가동", manual_loss))
        if round(value, 9) > 0
    ]
    split = " + ".join(parts)
    if len(parts) == 2:
        written = [written_value(_nonzero_signed(-value)) for value in (units_loss, manual_loss)]
        recomputed = (
            _nonzero_signed(sum(value for value in written if value is not None))
            if all(value is not None for value in written)
            else ""
        )
        if equals_mark(_nonzero_signed(-loss), recomputed) == APPROX:
            split = f"{APPROX} {split}"
    rate = _number(record.get("확보율"))
    free_rate = _number(record.get("비가동 없는 확보율"))
    if points is None or rate is None or free_rate is None:
        detail = f"소요 0 — 확보율 영향 없음 · {split}"
    else:
        free_text, rate_text = f"{free_rate:.1%}", f"{rate:.1%}"
        pair = f"비가동 없으면 확보율 {free_text} → 지금 {rate_text}"
        written_free, written_rate = written_value(free_text), written_value(rate_text)
        recomputed_points = (
            _nonzero_signed((written_rate - written_free) * 100)
            if written_free is not None and written_rate is not None
            else ""
        )
        if equals_mark(points_number, recomputed_points) == APPROX:
            pair = f"{APPROX} {pair}"
        detail = f"{pair} · {split}"
    hover = (
        f"{head} · 비가동 영향 {units_text}"
        + (f" · {points_text}" if points_text else "")
        + f"<br>{detail}"
        + ("<br>확보율은 UPEH 가정 소요 기준" if assumed and points_text else "")
    )
    return _Cell(text=units_text, sub=points_text, muted=past, hover=hover)


_NONZERO_LAST_DIGITS: Final = 8
"""`_nonzero_signed` 가 `signed_one` 에 넘기는 가장 큰 자릿수 — 그 자리로 0 이면 한 자리 더(아홉째)
적어 `round(값, 9)` 가 0 이 아닌 값은 0 이 아니게 적힌다."""


def _nonzero_signed(value: float) -> str:
    """부호 있는 값(`signed_one`) — 0 이 아닌 값이 0 으로 적히면 0 이 아니게 적힐 때까지 한
    자리씩 더 본다.

    하루치 손실이 환산비 작은 호기에 서면 0.003대일 수 있다 — 깎았는데 「0.0」·「0.00」 이면 빈칸
    규칙(깎은 것이 없으면 빈칸)과 어긋나 읽힌다. 빈칸 판정과 같은 문턱(`round(값, 9)`)까지 보므로
    빈칸이 아닌 칸은 늘 0 이 아닌 글이다(`signed_one` 은 `digits` + 1 자리까지 적어 아홉째 자리면
    멈춘다).
    """
    digits = 1
    text = _signed_one(value, digits)
    while round(value, 9) != 0 and written_value(text) == 0 and digits < _NONZERO_LAST_DIGITS:
        digits += 1
        text = _signed_one(value, digits)
    return text


def _compare_cell(
    head: str,
    static_short: bool,
    dynamic_short: bool,
    *,
    cause: str = "",
    past: bool,
    assumed: bool = False,
) -> _Cell:
    """② 판정 대조 칸 하나. `assumed` 면 「기준」 판정이 UPEH 가정 요약이라 풍선이 그 이름으로
    부른다 — 공식 판정이 아니다."""
    basis = "UPEH 가정" if assumed else "공식"
    subject = "UPEH 가정 기준은" if assumed else "공식은"
    if static_short and dynamic_short:
        return _Cell(
            text="기준✕·일정✕",
            fill=None if past else tokens.STATUS_SHORTAGE,
            bold=not past,
            muted=past,
            hover=(
                f"{head} · {basis}·설비 일정 두 기준 모두 부족 — 아래 단축이 이 달을 메웁니다"
                "(단위가 달라 크기는 참고)"
            ),
        )
    if static_short:
        hover = (
            f"{head} · {subject} 부족, 설비 일정으로는 충족 — Core Data 보유·대여와 "
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
            hover=f"{head} · {subject} 충족 — 설비 일정 기준으로만 부족(참고)",
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
    # 첫 줄의 과부족을 둘째 줄 식(등호 없음)이 낸다. 적힌 가용·목표대수(첫째 자리)로 다시 셈한
    # 값이 그 과부족과 다르면 식 앞에 「≈」 를 둔다(① 과부족 풍선과 같은 길).
    mark = EQUALS
    if available is not None and target_units is not None:
        mark = equals_mark(
            _signed_one(gap), _signed_one(round(available, 1) - round(target_units, 1))
        )
    hover = (
        f"{head} · 목표 {threshold_percent_label(target)} 과부족 {_signed_one(gap)}"
        f"<br>{f'{APPROX} ' if mark == APPROX else ''}가용 {_one(available)} {_MINUS} "
        f"목표대수 {_one(target_units)} (환산대수)"
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
        # 풍선은 그 호기 그림이 걸친 달 칸과 줄 이름 칸에서만 뜬다. 빈 달 칸도 칸은 두어(풍선 없는
        # 표적) 줄 어디를 눌러도 그 열의 달이 골라진다.
        span = _unit_span(_unit_marks(kind, record, axis, dynamic), len(axis))
        for index, month in enumerate(axis):
            inside = span is not None and span[0] <= index <= span[1]
            hover = ""
            if inside:
                hover = (
                    _unit_cell_hover(record, dynamic, month) if kind == "event" else row.label_hover
                )
            row.cells[index] = _Cell(hover=hover)
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
    hover = _unit_hover(event, today) + _assumption_line(event, dynamic)
    released = False
    change = None if dynamic.official_pulls is None else dynamic.official_pulls.get(unit)
    # 가정으로 단축이 필요 없어진 호기 — 흐린 줄로 남긴다(P5).
    if change is not None and kind != ROW_SHORTENED:
        released = True
        detail = f"가정으로 단축 불필요 · 공식 {_MINUS}{change[0]}일"
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
        label_hover=hover,
    )


def _assumption_line(event: Mapping[str, object], dynamic: DynamicCanvasInput) -> str:
    """UPEH 가정 계획만 붙는 넷째 줄(앞 `<br>` 포함) — 표지와, 공식과 단축일수가 다른 호기면
    「공식 −N일 → 가정 −M일」. 공식 계획이면 빈 글자."""
    if dynamic.official_pulls is None:
        return ""
    mark = "UPEH 가정 계획"
    change = dynamic.official_pulls.get(str(event.get("호기")))
    if change is not None:
        official_days, assumed_days = change
        mark += f" · 공식 {_MINUS}{official_days}일 → 가정 " + (
            f"{_MINUS}{assumed_days}일" if assumed_days else "0일"
        )
    return f"<br>{mark}"


def _unit_cell_hover(event: Mapping[str, object], dynamic: DynamicCanvasInput, month: int) -> str:
    """③ 호기 줄 달 칸의 풍선 — 줄 이름 칸 풍선과 같은 줄이되 증분은 그 달 몫이다."""
    return _unit_hover(event, dynamic.today, month=month) + _assumption_line(event, dynamic)


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
        label_hover=(
            html.escape(unit)
            + (f" · {html.escape(model)}" if model else "")
            + _module_text(record)
            + f"<br>{html.escape(kind or '정지·반출/이설')} {_day(day, dynamic.today)}부터 가용에서"
            " 빠집니다"
        ),
    )


def _module_text(record: Mapping[str, object]) -> str:
    """모듈 묶음이면 「 · 모듈 N」, 단독 호기면 빈 글자 — 라벨에서 걷은 모듈 수를 풍선 첫 줄에
    둔다."""
    modules = _whole(record.get("모듈 수")) or 1
    return f" · 모듈 {modules}" if modules > 1 else ""


def _unit_hover(event: Mapping[str, object], today: date, *, month: int | None = None) -> str:
    """③ 호기 줄 풍선 — 세 줄까지. 그림 표지(◆ 반입 · ● 색 = Qual상태)와 줄 라벨·CSV 가 이미 말하는
    반입일·Qual상태·대상 월은 적지 않는다. 날짜는 줄 라벨과 같은 짧은 꼴(올해 밖이면 연도)이다.

    - 1줄 — 호기 · (단축이면 −N일, 추가N 이면 「신규」) · Model · (모듈 묶음이면 「모듈 N」).
    - 2줄 — 단축 「Qual MM.DD → 목표 MM.DD · MM.DD부터 기여 +0.10대」, 추가N 「필요 Qual MM.DD ·
      MM.DD부터 기여 +1.00대」, 그 밖 신규 「Qual MM.DD · MM.DD부터 기여」.
    - 3줄 — 해소 기여 월(단축 · 추가N 만 — 해소 눈금이 서는 줄) · 「⚠ 반입 전」 · 정지·반출/이설일 ·
      모듈마다 Qual 이 갈리면 그 범위. 조각이 없으면 줄이 없다.

    `month` 를 주면(달 칸 풍선) 단축 · 추가N 의 증분을 그 달 몫 「· 이 달 +0.57대」 로 적는다 —
    그 달 몫이 0 이면 숫자를 빼고, 몫을 모르면(칸 없음) 요약 값 그대로다. UPEH 가정 계획의 넷째
    줄은 `_assumption_line` 이 붙인다.
    """
    kind = str(event.get("줄"))
    first = [html.escape(str(event.get("호기")))]
    if kind == ROW_SHORTENED:
        first.append(f"{_MINUS}{_whole(event.get('단축일수')) or 0}일")
    elif kind == ROW_VIRTUAL:
        first.append("신규")
    if not _blank(event.get("Model")):
        first.append(html.escape(str(event.get("Model"))))
    lines = [" · ".join(first) + _module_text(event)]
    gain = _number(event.get("늘어난 환산대수"))
    contribution = " 기여" + (f" +{gain:,.2f}대" if gain is not None else "")
    share = None if month is None else month_share(event.get("월별 늘어난 환산대수"), month)
    if share is not None:
        contribution = " 기여" + (f" · 이 달 +{share:,.2f}대" if round(share, 2) > 0 else "")
    target = _as_date(event.get("목표 Qual"))
    target_start = _as_date(event.get("목표 기여 시작")) or _next_day(target)
    if kind == ROW_SHORTENED:
        lines.append(
            f"Qual {_day(_as_date(event.get('Qual일정')), today)} → 목표 {_day(target, today)} · "
            f"{_day(target_start, today)}부터{contribution}"
        )
    elif kind == ROW_VIRTUAL:
        lines.append(
            f"필요 Qual {_day(target, today)} · {_day(target_start, today)}부터{contribution}"
        )
    else:
        lines.append(
            f"Qual {_day(_as_date(event.get('Qual일정')), today)} · "
            f"{_day(_as_date(event.get('기여 시작')), today)}부터 기여"
        )
    last: list[str] = []
    # 해소 기여 월은 해소 눈금을 그리는 줄(단축 · 추가N)만 적는다 — UPEH 가정으로 단축이 필요 없어진
    # 흐린 신규 줄은 공식 계획의 해소 달을 들고 오지만 그림에는 눈금이 없다.
    resolved = (
        _month_tuple(event.get("해소 기여 월")) if kind in (ROW_SHORTENED, ROW_VIRTUAL) else ()
    )
    if resolved:
        last.append("해소 " + ", ".join(month_label(month) for month in resolved))
    if kind == ROW_SHORTENED and bool(event.get("반입 전")):
        last.append("⚠ 반입 전")
    exit_day = _as_date(event.get("반출이설일"))
    if exit_day is not None:
        exit_kind = "" if _blank(event.get("반출이설구분")) else str(event.get("반출이설구분"))
        last.append(f"{html.escape(exit_kind or '정지·반출/이설')} {_day(exit_day, today)}")
    spread = _module_qual_spread(event.get("모듈별 Qual"), today)
    if spread:
        last.append(spread)
    if last:
        lines.append(" · ".join(last))
    return "<br>".join(lines)


def _module_qual_spread(value: object, today: date) -> str:
    """모듈 묶음의 모듈마다 Qual 이 갈리면 「모듈 Qual MM.DD~MM.DD」(가장 이른 ~ 가장 늦은), 같거나
    단독 호기면 빈 글자. 모듈마다의 날짜는 가용설비 현황 Main(설비 마스터 모듈 행)이 적는다."""
    if not isinstance(value, (tuple, list)):
        return ""
    days = sorted(
        {
            day
            for item in value
            if isinstance(item, (tuple, list))
            and len(item) == 2
            and (day := _as_date(item[1])) is not None
        }
    )
    if len(days) < 2:
        return ""
    return f"모듈 Qual {_day(days[0], today)}~{_day(days[-1], today)}"


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
            traces.append(
                _marker_trace(self.arrival, "diamond", _ARRIVAL_MARKER_PX, tokens.TEXT_MUTED)
            )
        if self.start.x:
            traces.append(
                _marker_trace(
                    self.start, "circle", _START_MARKER_PX, self.start.color, outline=tokens.TEXT
                )
            )
        if self.pull_head.x:
            traces.append(
                _marker_trace(self.pull_head, "triangle-left", _PULL_HEAD_MARKER_PX, tokens.TEXT)
            )
        if self.exit.x:
            traces.append(
                _marker_trace(
                    self.exit,
                    "triangle-down",
                    _EXIT_MARKER_PX,
                    self.exit.color,
                    outline=tokens.TEXT,
                )
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


@dataclass(frozen=True)
class _UnitMarks:
    """③ 한 줄의 그림 자리(달 단위 x). `_draw_unit` 이 그리고 `_unit_span` 이 풍선을 띄울 달 칸을
    고른다 — 한 곳에서 내야 그림과 풍선 칸이 어긋나지 않는다."""

    arrival: float | None = None
    """◆ 반입(반입 다음 날). 축 밖이면 None."""

    start: float | None = None
    """● 기여 시작. 축 밖이라 잘렸으면 None."""

    pull: tuple[float, float] | None = None
    """단축 선 (기여 시작, 목표 기여 시작) — 기여 시작이 축 밖이면 잘린 자리(축 끝)에서 긋는다."""

    pull_days: int = 0
    before_arrival: bool = False
    virtual: float | None = None
    """추가N ◌ 의 목표 기여 자리."""

    exit: float | None = None
    """▼ 정지·반출/이설. 축 밖이면 None."""

    resolved: tuple[int, ...] = ()
    """해소 기여 월 눈금의 열 index(축 안만)."""


def _unit_marks(
    kind: str, record: Mapping[str, object], axis: Sequence[int], dynamic: DynamicCanvasInput
) -> _UnitMarks:
    def inside(day: date | None) -> float | None:
        if day is None:
            return None
        position = production_position(day, dynamic.cutoff_days, axis)
        return None if position.before or position.after else position.x

    if kind == "exit":
        return _UnitMarks(exit=inside(_as_date(record.get("반출이설일"))))
    line = str(record.get("줄"))
    columns = {month: index for index, month in enumerate(axis)}
    resolved = tuple(
        columns[month] for month in _month_tuple(record.get("해소 기여 월")) if month in columns
    )
    if line == ROW_VIRTUAL:
        target_x = _number(record.get("목표 기여 위치"))
        return _UnitMarks() if target_x is None else _UnitMarks(virtual=target_x, resolved=resolved)
    start_x = _number(record.get("기여 시작 위치"))
    pull: tuple[float, float] | None = None
    if line == ROW_SHORTENED:
        target_x = _number(record.get("목표 기여 위치"))
        if target_x is not None and start_x is not None:
            pull = (start_x, target_x)
    return _UnitMarks(
        arrival=inside(_next_day(_as_date(record.get("반입일정")))),
        start=None if bool(record.get("기여 시작 축 밖")) else start_x,
        pull=pull,
        pull_days=_whole(record.get("단축일수")) or 0,
        before_arrival=bool(record.get("반입 전")),
        exit=inside(_as_date(record.get("반출이설일"))),
        resolved=resolved if line == ROW_SHORTENED else (),
    )


def _unit_span(marks: _UnitMarks, count: int) -> tuple[int, int] | None:
    """그 줄 그림(선·화살표·표지와 붙은 글자 — 「−N일」·「반입 전」·「신규 필요」)이 걸친 달 칸의
    (첫 열, 끝 열) — 가장 이른 것 ~ 가장 늦은 것이 든 달이고 축 안으로 자른다. 그릴 것이 없으면
    None 이다(풍선은 줄 이름 칸에만 뜬다).

    표지는 반지름까지 센다 — 달 경계에 선 ◆ 는 앞 달 칸에도 반이 그려진다. 글자는 그리는 앵커는
    `_draw_unit` 과 같고, 앵커에서 펴지는 폭만 어림의 `_SPAN_TEXT_SHARE` 몫으로 센다.
    """
    column_px = tokens.MONTH_COLUMN_WIDTH_PX

    def around(x: float, size_px: float) -> tuple[float, float]:
        half = size_px / 2 / column_px
        return x - half, x + half

    extents = [
        around(x, size_px)
        for x, size_px in (
            (marks.arrival, _ARRIVAL_MARKER_PX),
            (marks.start, _START_MARKER_PX),
            (marks.exit, _EXIT_MARKER_PX),
        )
        if x is not None
    ]
    if marks.pull is not None:
        start_x, target_x = marks.pull
        # 「−N일」 은 촉 왼쪽 앵커에서, 「반입 전」 배지는 그보다 왼쪽 앵커에서 왼쪽으로 펴진다.
        label_right = target_x - _PULL_TEXT_GAP
        left = label_right - _pull_label_px(marks.pull_days) * _SPAN_TEXT_SHARE / column_px
        if marks.before_arrival:
            badge_right = _badge_right(target_x, marks.pull_days)
            left = min(left, badge_right - _badge_px(_SPAN_TEXT_SHARE) / column_px)
        head_left, head_right = around(target_x, _PULL_HEAD_MARKER_PX)
        extents.append((min(left, head_left, start_x), max(start_x, head_right)))
    if marks.virtual is not None:
        text_px = _text_width_units(_VIRTUAL_TEXT) * TRACK_TEXT_FONT_PX * _SPAN_TEXT_SHARE
        extents.append(
            (
                marks.virtual - _VIRTUAL_RADIUS_PX / column_px,
                marks.virtual + _VIRTUAL_TEXT_GAP + text_px / column_px,
            )
        )
    extents += [(index + 0.35, index + 0.65) for index in marks.resolved]
    if not extents:
        return None

    def column(x: float) -> int:
        return min(count - 1, max(0, math.floor(x)))

    # 오른쪽 끝이 달 경계에 딱 닿는 선·글자는 그 다음 달에 들지 않는다(점 하나는 그 자리의 달).
    first = min(column(left) for left, _ in extents)
    last = max(column(right - 1e-9 if right > left else right) for left, right in extents)
    return first, last


def _pull_label_px(days: int) -> float:
    """단축 촉 왼쪽 「−N일」 글자 폭(px)."""
    return _text_width_units(f"{_MINUS}{days}일") * TRACK_TEXT_FONT_PX


def _badge_px(text_share: float = 1.0) -> float:
    """「반입 전」 배지 폭(px) — 글자(어림의 `text_share` 몫)와 좌우 안쪽 여백."""
    return (
        _text_width_units(_BEFORE_ARRIVAL_TEXT) * ARROW_TEXT_FONT_PX * text_share
        + 2 * _BADGE_PAD_PX
    )


def _badge_right(target_x: float, pull_days: int) -> float:
    """「반입 전」 배지 오른쪽 끝(달 단위 x) — 「−N일」 어림 폭과 틈만큼 그 글자 왼쪽이다."""
    return (
        target_x
        - _PULL_TEXT_GAP
        - (_pull_label_px(pull_days) + _BADGE_GAP_PX) / tokens.MONTH_COLUMN_WIDTH_PX
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
    marks = _unit_marks(kind, record, axis, dynamic)
    if kind == "exit":
        if marks.exit is not None:
            track.exit.add(x=marks.exit, y=center, color=_exit_color(record.get("반출이설구분")))
        return
    line = str(record.get("줄"))
    if line == ROW_VIRTUAL:
        if marks.virtual is None:
            return
        target_x = marks.virtual
        half = _VIRTUAL_RADIUS_PX / tokens.MONTH_COLUMN_WIDTH_PX
        # 추가N ◌ — 부족 면에 점선 테두리. Plotly 표지는 테두리를 점선으로 못 그려 도형으로 둔다.
        shapes.append(
            {
                "type": "circle",
                "x0": target_x - half,
                "x1": target_x + half,
                "y0": center - _VIRTUAL_RADIUS_PX,
                "y1": center + _VIRTUAL_RADIUS_PX,
                "xref": "x",
                "yref": "y",
                "fillcolor": tokens.STATUS_SHORTAGE,
                "line": {"color": tokens.TEXT, "width": 1.5, "dash": "dot"},
                "layer": "above",
            }
        )
        track.virtual_text.add(
            x=target_x + _VIRTUAL_TEXT_GAP, y=center, text=f"<b>{_VIRTUAL_TEXT}</b>"
        )
        _resolved_ticks(marks.resolved, bottom, shapes)
        return
    if marks.arrival is not None:
        track.arrival.add(x=marks.arrival, y=center)
    if line == ROW_SHORTENED:
        if marks.pull is not None:
            start_x, target_x = marks.pull
            track.pull_x += [start_x, target_x, None]
            track.pull_y += [center, center, None]
            track.pull_head.add(x=target_x, y=center)
            label = f"{_MINUS}{marks.pull_days}일"
            track.pull_text.add(x=target_x - _PULL_TEXT_GAP, y=center, text=f"<b>{label}</b>")
            if marks.before_arrival:
                annotations.append(
                    {
                        "x": _badge_right(target_x, marks.pull_days),
                        "y": center,
                        "xref": "x",
                        "yref": "y",
                        "xanchor": "right",
                        "yanchor": "middle",
                        "text": f"<b>{_BEFORE_ARRIVAL_TEXT}</b>",
                        "showarrow": False,
                        "bgcolor": tokens.STATUS_WARNING,
                        "borderpad": _BADGE_PAD_PX,
                        "font": {
                            "color": tokens.TEXT,
                            "size": ARROW_TEXT_FONT_PX,
                            "family": tokens.FONT_FAMILY,
                        },
                    }
                )
        _resolved_ticks(marks.resolved, bottom, shapes)
    if marks.start is not None:
        track.start.add(
            x=marks.start, y=center, color=_confirmation_color(record.get(QUAL_STATUS_COLUMN))
        )
    if marks.exit is not None:
        track.exit.add(x=marks.exit, y=center, color=_exit_color(record.get("반출이설구분")))


def _resolved_ticks(columns: Sequence[int], bottom: float, shapes: list[dict[str, Any]]) -> None:
    """「해소 기여 월」 칸 아래 가장자리 2px 눈금 — 이 호기가 메운 달."""
    for index in columns:
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
