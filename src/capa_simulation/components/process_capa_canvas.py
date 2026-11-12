# Purpose: 공정 Capa 상세 결합 월 캔버스의 행 모델을 세워 라벨·월 Figure 한 쌍으로 그린다.

"""공정 Capa 상세 — 결합 월 캔버스.

공정 하나를 **한 스크롤 상자**에 위에서 아래로 쌓는다. HOME 대시보드 틀 그대로 라벨 칸
(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`, 260px)과 월 칸(달마다 `MONTH_COLUMN_WIDTH_PX`, 100px)이 Figure
한 쌍이고, 월 Figure 하나가 가로로 스크롤된다. 구획은 다섯이다(2026-11-12 사용자 답 k-c0).

1. **① Static 기준**(Core Data · 대수 · 확보율에 쓰는 숫자 — 제목 줄 풍선) —
   총보유대수·가용대수(공급 묶음 면), 소요대수(수요 묶음 면, 펼치면 분류 행이 줄무늬·들여쓰기로
   붙는다), 확보율(판정 3색 칸), 확보 기준 과부족(부호 있는 정수, 부족이면 확보율과 **같은**
   판정색, 풍선은 정수 옆에 올림·내림 전 값을 소수 둘째 자리로), 기준 확보율(달마다 확보 기준 % —
   회색 글자만, 참고 줄), 그리고 넘겨받았을 때만 확보율(HOME 표시).
2. **② 일정 가용**(설비 DB · 환산대수 · 생산월 — 제목 줄 풍선이 Cut-off n일 · 오늘 점선 날짜) —
   총보유대수(달력 월 — `owned_units`), 가용대수(기존보유 + 호기 — **비가동을 빼기 전**, n1 (가)),
   전월 대비(그 차이 — 풍선은 호기 묶음 몫, k-c3), 소요대수(판정 기준 소요 — 펼치면 ① 과 함께
   분류 행, q4 (가)), 확보율 · 확보 기준 과부족(① 과 같은 양식 · 같은 판정 길 `judge_supply`).
3. **③ 비가동** — 비가동대수(호기별 비가동 일정이 깎은 대수 + 입력 비가동 반영 —
   `downtime_impact`, q5 (가)), 실가용대수(비가동 기준 `DynamicCanvasInput.downtime_basis` 의
   가용에서 뺀 값, 0 에서 멈춤. Static 이면 ① 가용대수, 일정이면 ② 가용대수 — 이때 필요 단축
   일정의 가용과 같다), 소요대수(합계만), 확보율 · 확보 기준 과부족.
4. **④ 단축** — 호기마다 한 줄. ◆ 반입 · ● 기여 시작(Qual상태 색), 단축 대상이면 같은 줄에 ◀ 목표
   기여 시작과 「−N일」, 목표 Qual 이 반입보다 이르면 「반입 전」 배지. 축 안에서 정지·반출/이설되는
   다른 호기는 ▼ 한 줄, 추가N(◌)은 맨 아래. 30행 상한(`ROW_LIMIT`)을 넘으면 「n대 더」 한 줄이다.
5. **⑤ 비가동 일정** — 비가동 한 행이 화살표 하나. 가용을 깎은 것만 진한 실선과 촉, 나머지는 흐린
   점선이다. 글자는 비가동유형과 「◂ 이전부터」·「계속 ▸」. 축 안에 입력 비가동(가용설비 현황 ›
   Preference — 공정 × 생산월 대수)이 있으면 구획 첫 줄이 「월별 비가동대수(입력)」 이다 — 달마다
   넣은 대수이고, 그 달 가용보다 커 0 에서 멈춘 칸은 「⚠」 와 경고색이다. 그 몫은 ③ 비가동대수에
   든다. 호기 줄이 없는 공정(기존보유만)은 ④ · ⑤ 가 서지 않고 그 줄은 ③ 끝에 선다.

**판정 띠는 한 기준이다** — 부족 달 세로 띠는 판정 기준 요약(① Static, UPEH 가정이 켜지면 가정
요약)의 판정 하나이고, ② · ③ 의 확보율 · 과부족 칸은 그 구획의 가용으로 낸 제 판정 색만 칠한다
(2026-11-12 사용자 답 q8 (가)).

호기·Model 라벨에는 모듈 수를 적지 않는다(2026-10-22 사용자 요청) — 모듈 묶음은 풍선이
밝힌다. ④ 호기 줄·정지 줄 풍선 첫 줄에 「· 모듈 N」, ⑤ 풍선 첫 줄에 「· 모듈 N」과 화살표
줄마다 그 모듈의 설비명이다.

**④ 풍선은 세 줄이고 그림 위에서만 뜬다**(2026-10-24 사용자 결정 (가)) — 「호기 · −N일 · Model」,
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
아래)에 「UPEH 가정」 세 줄(소요대수·확보율·확보 기준 과부족)이 선다 — 구간 달만 값이고 밖은
빈칸이다(풍선 「구간 밖 — 가정 전과 같음」). ① 의 Static 줄은 그대로다. 가정과 견주는 값은 「가정
전」 이라 부른다(2026-11-12 사용자 답 q2 (가)). 가정이 켜지면 부족 띠는 가정 요약의 판정이고(④ 가
가정 계획이라 한 그림에서 가정 전 판정과 섞이지 않게), ② · ③ 의 소요대수도 가정 소요다(칸 풍선에
「UPEH 가정 p%」, ② 분류 행은 가정이 걸린 달에 ÷f). 「UPEH 가정 계획」 표지는 ④ 호기 풍선에만
단다 — ② 총보유 · 가용 · 전월 대비, ③ 비가동대수와 ⑤ 는 설비 일정이라 UPEH 와 무관하다. 가정 전
계획에서는 당겼지만 가정 계획에서는 덜 당기는 호기는 ④ 에 흐린 줄로 남고 풍선에 「가정 전 −45일 →
가정 0일」 이다(`DynamicCanvasInput.official_pulls`).

**구획 접기**(`collapsed`, 구획 id `SECTION_IDS`) — 접힌 구획은 제목 줄만 남고(글자 끝 ▸, 펼친
구획은 ▾) 그 밑 행을 그리지 않는다. 판정은 요약 프레임에서 그대로 내므로 ① 을 접어도 부족 띠와
② · ③ 확보율은 같다. 접힌 ④·⑤ 는 줄을 만들지 않아 「n대 더」 수도 0 이다.

**다섯 구획이 한 Figure 쌍인 까닭** — 확보 기준에 못 미친 달의 세로 띠(`SHORTAGE_MONTH_BAND`)와 지금
보는 달의 열 테두리가 구획을 넘어 이어져야 하고(구획마다 그림을 나누면 제목 줄에서 끊긴다), 칸
선택(`on_select`)이 그림 하나에서 와야 한다. 그래서 구획 제목도 Figure 안의 한 줄이다. 제목은
**라벨 Figure** 에 쓴다 — 월 Figure 는 가로로 스크롤되므로 거기 둔 글은 고른 달로 밀어 연 화면에서
잘리거나 사라진다. 제목 아래 세부 글은 두지 않는다 — 출처 · 단위는 제목 줄 풍선(`Row.label_hover`)과
Guide 가 적는다(2026-11-12 사용자 답 k-c1 · k-c2).

`go.Table`·`go.Heatmap` 을 쓰지 않는다 — 둘 다 점 선택이 없어 `on_select` 가 오지 않는다. 칸 면은
`base` 로 띄운 가로막대, 숫자는 `Scatter(text)`, 칸마다 보이지 않는 표적 막대가 hover 와 클릭을
받는다(HOME 주요공정 히트맵과 같은 방법). 표적의 `customdata` 는 `(YYYYMM, 행 id, 풍선 글)` 이다
(`CUSTOMDATA_MONTH`·`CUSTOMDATA_ROW`·`CUSTOMDATA_HOVER`). 지금 보는 달의 머리 밑줄과 열 테두리는
그림에 그린다 — 그래서 그림 캐시 키에 그 달이 든다.

**풍선의 식**(① 가용 「보유 − 대여」·확보율 「가용 ÷ 소요」·과부족 「가용 − 소요 × 기준」, UPEH
가정 소요 「가정 전 ÷ f」, ② 총보유 「기존보유 + 반입 − 반출/이설」 · 가용 「기존보유 + 호기」 ·
전월 대비 갈림, ③ 실가용 「기준 가용 − 비가동」)은 인수를 칸 자릿수로 적고, 적힌 수로 다시 셈한
값이 결과와 다르면 「=」 대신 「≈」 다(`formula_text.equals_mark` — 근거 패널 ③·④ 와 같은 길).
과부족 식 줄과 ③ 비가동대수 풍선의 갈림(「호기 비가동 a + 입력 비가동 b」 — 칸 글을 낸다)은 결과가
앞 줄에 있고 등호가 없어 어긋날 때만 식 앞에 「≈」 를 둔다.

순수 함수다. 세션·캐시·DB 를 보지 않는다. 그림 캐시·칸 선택 콜백은 페이지가 맡고, 시트 범례는
Guide 다.
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
from capa_simulation.services.manual_downtime import (
    manual_removed_text,
    manual_units_text,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import (
    LENT_COLUMN,
    MISMATCH_COLUMN,
    OTHER_ROW_COLUMN,
    PRODUCT_LABEL_COLUMN,
    judge_supply,
    month_column,
)
from capa_simulation.services.process_equipment_timeline import (
    EXIT_KIND_RELOCATION,
    ROW_SHORTENED,
    ROW_VIRTUAL,
    downtime_impact,
    month_share,
    production_position,
    unit_month_changes,
)
from capa_simulation.services.required_shortening import TargetLevel
from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    OWNED_COLUMN,
    STATUS_COLUMN,
    surplus_held_at_zero,
)
from capa_simulation.services.securement_threshold import SecurementThresholds, judgment_boundary
from capa_simulation.services.threshold_label import (
    boundary_percent_label,
    threshold_percent_label,
)

__all__ = [
    "BASIS_SCHEDULE",
    "BASIS_STATIC",
    "MANUAL_DOWNTIME_ROW_LABEL",
    "CUSTOMDATA_HOVER",
    "CUSTOMDATA_MONTH",
    "CUSTOMDATA_ROW",
    "ROW_ARROW_PREFIX",
    "ROW_AVAILABLE",
    "ROW_BALANCE",
    "ROW_DYNAMIC_AVAILABLE",
    "ROW_DYNAMIC_BALANCE",
    "ROW_DYNAMIC_DELTA",
    "ROW_DYNAMIC_OWNED",
    "ROW_DYNAMIC_PRODUCT_PREFIX",
    "ROW_DYNAMIC_RATE",
    "ROW_DYNAMIC_REQUIRED",
    "ROW_EFFECT_AVAILABLE",
    "ROW_EFFECT_BALANCE",
    "ROW_EFFECT_LOSS",
    "ROW_EFFECT_RATE",
    "ROW_EFFECT_REQUIRED",
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
    "SECTION_EFFECT",
    "SECTION_IDS",
    "SECTION_SUMMARY",
    "SECTION_UNITS",
    "SUMMARY_TITLE_HEIGHT_PX",
    "SUMMARY_TITLE_HOVER",
    "AssumptionCanvasInput",
    "DynamicCanvasInput",
    "ProcessCapaCanvas",
    "ProcessCapaRows",
    "TrackText",
    "build_process_capa_canvas",
    "build_process_capa_rows",
    "track_texts",
    "canvas_point",
    "loss_text",
    "title_detail_lines",
    "title_row_height",
]

MONTH: Final = "생산계획년월"

# ------------------------------------------------------------------ 치수
# 머리 36px·값 행 27px·제목 줄·글자 크기는 엔진(`month_sheet_canvas`)의 값이다(위에서 다시
# 내보낸다). 여기는 이 캔버스만의 행 — 호기 줄은 라벨 두 줄이 드는 34px 다.
# ① 제목 줄 풍선 글 — 구획 제목 아래 회색 세부 글은 Guide 와 제목 줄 풍선으로 옮겼다(2026-11-12
# 사용자 답 k-c1). 제목 줄 높이(`SUMMARY_TITLE_HEIGHT_PX`, 파일 끝)로 화면 확인 스크립트가 확보율
# 줄의 세로 자리를 센다.
SUMMARY_TITLE_HOVER: Final = "Core Data · 대수 · 확보율에 쓰는 숫자"
PRODUCT_ROW_HEIGHT_PX: Final = 23
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
# ④·⑤ 의 줄 상한. 넘으면 「n대 더」 한 줄을 두고, 페이지의 「더 보기」가 모두 그린다.
ROW_LIMIT: Final = 30
# ② 전월 대비 풍선의 호기 묶음 몫 — 큰 차례로 여섯까지(나머지는 「외 n대」), 한 줄에 셋.
_MOVE_LIMIT: Final = 6
_MOVES_PER_LINE: Final = 3
# ⑤ 화살표 위 비가동유형 글자의 상한(글자 수).
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
# ② 일정 가용 — 총보유대수 · 가용대수 · 전월 대비 · 소요대수(제품 줄) · 확보율 · 확보 기준 과부족.
ROW_DYNAMIC_OWNED: Final = "dynamic_owned"
ROW_DYNAMIC_AVAILABLE: Final = "dynamic_available"
ROW_DYNAMIC_DELTA: Final = "dynamic_delta"
ROW_DYNAMIC_REQUIRED: Final = "dynamic_required"
ROW_DYNAMIC_PRODUCT_PREFIX: Final = "dynamic_product:"
ROW_DYNAMIC_RATE: Final = "dynamic_rate"
ROW_DYNAMIC_BALANCE: Final = "dynamic_balance"
# ③ 비가동 — 비가동대수 · 실가용대수 · 소요대수(합계) · 확보율 · 확보 기준 과부족.
ROW_EFFECT_LOSS: Final = "effect_loss"
ROW_EFFECT_AVAILABLE: Final = "effect_available"
ROW_EFFECT_REQUIRED: Final = "effect_required"
ROW_EFFECT_RATE: Final = "effect_rate"
ROW_EFFECT_BALANCE: Final = "effect_balance"
# ⑤ 첫 줄 「월별 비가동대수(입력)」 — 축 안에 입력 비가동이 있을 때만 선다. 줄 이름은 다른 대수
# 줄(총보유대수 · 가용대수 · 소요대수 · 비가동대수)처럼 붙여 쓴다(2026-11-12 사용자 메모 k-c0).
ROW_MANUAL_DOWNTIME: Final = "manual_downtime"
MANUAL_DOWNTIME_ROW_LABEL: Final = "월별 비가동대수(입력)"
ROW_UNIT_PREFIX: Final = "unit:"
ROW_EXIT_PREFIX: Final = "exit:"
ROW_ARROW_PREFIX: Final = "arrow:"

# 구획 id — 제목 줄 행 id(`title:<id>`)의 꼬리이고, 페이지의 「구획」 칩 값이다. 차례는 ① Static
# 기준 · ② 일정 가용 · ③ 비가동 · ④ 단축 · ⑤ 비가동 일정(2026-11-12 사용자 답 k-c0).
SECTION_SUMMARY: Final = "summary"
SECTION_DYNAMIC: Final = "dynamic"
SECTION_EFFECT: Final = "downtime_effect"
SECTION_UNITS: Final = "units"
SECTION_DOWNTIME: Final = "downtime"
SECTION_IDS: Final = (
    SECTION_SUMMARY,
    SECTION_DYNAMIC,
    SECTION_EFFECT,
    SECTION_UNITS,
    SECTION_DOWNTIME,
)
# 「③ 비가동」 의 비가동 기준 — 실가용대수를 어느 가용에서 빼나(① Static 가용 · ② 일정 가용).
# 처음은 Static 이다(2026-11-12 사용자 답 q5b (가)).
BASIS_STATIC: Final = "static"
BASIS_SCHEDULE: Final = "schedule"

_SHORT_STATUSES: Final = frozenset({"warning", "shortage"})
_STATUS_NAMES: Final[Mapping[str, str]] = {"secure": "확보", "warning": "경고", "shortage": "부족"}


@dataclass(frozen=True, eq=False)
class DynamicCanvasInput:
    """② ~ ⑤ 의 재료 — 설비 일정이 「참고」로 설 때(`dynamic_readiness(...).ready`)만 넘긴다.

    프레임은 모두 **공정 하나**의 것이다. `process_months` 는 `LevelPlan.process_months` 를 그
    공정으로 거른 것(달마다 한 행), `bridge`·`arrows`·`exits`·`owned_units`·`unit_months` 는
    `ProcessEquipmentTimeline` 의 칸, `unit_events` 는 `unit_events(timeline, plan.units)` 다.
    `exits` 에서 ④ 에 이미 선 호기는 여기서 뺀다.
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
    """설비 마스터에 HBM·EDP 호기가 있는가. 기존보유만 있는 공정은 ② · ③ 만 서고 「호기 일정 없음」
    한 줄이다."""

    steady_units: int = 0
    """축 내내 비가동 없이 가용인 호기 수 — ⑤ 끝의 「k대」 한 줄."""

    undated_notice: str = ""
    """④ 끝에 적는 「일정 미정 k대」 글(`undated_equipment_notice`). 비면 줄이 없다."""

    show_all_units: bool = False
    show_all_arrows: bool = False
    official_pulls: Mapping[str, tuple[int, int]] | None = None
    """UPEH 가정 계획을 그릴 때만 — 가정 전 계획과 단축일수가 다른 호기 → (가정 전 일, 가정 일)
    (`upeh_assumption.pull_changes`). None 이면 가정 전 계획이다(④ 풍선에 표지를 달지 않는다)."""

    owned_units: pd.DataFrame = field(default_factory=pd.DataFrame)
    """② 총보유대수(`ProcessEquipmentTimeline.owned_units` — 달력 월). 비면 그 줄이 빈칸이다."""

    unit_months: pd.DataFrame = field(default_factory=pd.DataFrame)
    """호기 x 월 기여(`ProcessEquipmentTimeline.unit_months`) — ② 전월 대비 풍선의 호기 묶음 몫."""

    downtime_basis: str = BASIS_STATIC
    """「③ 비가동」 의 비가동 기준(`BASIS_STATIC` · `BASIS_SCHEDULE`) — 표 도구 줄 고르기 값."""


@dataclass(frozen=True, eq=False)
class AssumptionCanvasInput:
    """UPEH 가정 — ① 끝 세 줄과 판정 기준(가정 요약)의 재료. ② · ③ 의 소요대수도 가정 요약의
    소요다."""

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
    """30행 상한으로 그리지 않은 ④ 호기 수(추가N 은 늘 그린다)."""

    hidden_arrow_units: int
    """30대 상한으로 그리지 않은 ⑤ 호기 수."""

    row_ids: tuple[str, ...]
    """위에서 아래로 그린 행 id."""


# ================================================================== 공개 함수


class ProcessCapaRows(NamedTuple):
    """결합 캔버스의 행 모델 — 그림(`build_process_capa_canvas`)과 엑셀
    (`process_capa_workbook`)이 같은 행 · 칸 · 칠을 읽는다(판정 · 미달 칠을 따로 다시 셈하지
    않는다)."""

    rows: list[_Row]
    """위에서 아래로 — 첫 행이 머리(달 글자)다."""

    axis: tuple[int, ...]
    shortage_indices: tuple[int, ...]
    """부족 달 세로 띠가 서는 열(판정 기준 요약의 경고 · 부족 달)."""

    hidden_units: int
    hidden_arrow_units: int
    dynamic_first: int | None
    """②~⑤ 첫 행의 자리. 설비 일정이 없으면 None."""

    today_x: float | None
    """오늘 점선 자리(달 단위 x). 축 밖이면 None."""


def build_process_capa_rows(
    *,
    process_label: str,
    months: Sequence[int],
    summary: pd.DataFrame,
    thresholds: SecurementThresholds,
    product_demand: pd.DataFrame | None = None,
    home_rates: Mapping[int, float | None] | None = None,
    dynamic: DynamicCanvasInput | None = None,
    collapsed: Collection[str] = frozenset(),
    assumption: AssumptionCanvasInput | None = None,
) -> ProcessCapaRows:
    """결합 캔버스의 행 모델. 인자는 `build_process_capa_canvas` 와 같다(고른 달만 없다 — 행에
    닿지 않는다). 색은 지금 테마의 토큰이다."""
    axis = [int(month) for month in months]
    if not axis:
        raise ValueError("결합 캔버스의 월 축이 비었습니다.")
    if len(set(axis)) != len(axis) or axis != sorted(axis):
        raise ValueError("결합 캔버스의 월 축은 겹치지 않는 오름차순이어야 합니다.")
    index_of = {month: position for position, month in enumerate(axis)}
    folded = frozenset(str(section) for section in collapsed)

    # 판정은 요약 프레임에서 낸다 — ① 을 접어도 부족 띠가 바뀌지 않는다. UPEH 가정이 켜지면 그 요약
    # 하나가 판정 기준이다(②~④ 가 가정 계획 · 가정 소요다). 부족 띠는 그 판정 하나다 — ② · ③ 의
    # 확보율 칸은 제 판정 색만 칠한다(2026-11-12 사용자 답 q8 (가)).
    judged = assumption.summary if assumption is not None else summary
    statuses = _summary_statuses(judged, axis)
    rows: list[_Row] = [_header_row(process_label, axis, thresholds)]
    if SECTION_SUMMARY in folded:
        rows.append(_section_title_row(SECTION_SUMMARY, folded, hover=SUMMARY_TITLE_HOVER))
    else:
        rows += _summary_rows(axis, summary, thresholds, product_demand, home_rates, assumption)
    hidden_units = 0
    hidden_arrow_units = 0
    today_x: float | None = None
    dynamic_first: int | None = None
    if dynamic is not None:
        dynamic_first = len(rows)
        dynamic_rows, hidden_units, hidden_arrow_units = _dynamic_rows(
            axis,
            dynamic,
            folded,
            process_label=process_label,
            summary=_by_month(summary, axis),
            judged=_by_month(judged, axis),
            thresholds=thresholds,
            product_demand=product_demand,
            assumption=assumption,
        )
        rows += dynamic_rows
        today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
        if not today_position.before and not today_position.after:
            today_x = today_position.x
    shortage_indices = tuple(
        index_of[month] for month, status in statuses.items() if status in _SHORT_STATUSES
    )
    return ProcessCapaRows(
        rows=rows,
        axis=tuple(axis),
        shortage_indices=shortage_indices,
        hidden_units=hidden_units,
        hidden_arrow_units=hidden_arrow_units,
        dynamic_first=dynamic_first,
        today_x=today_x,
    )


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
    - `dynamic` 이 None 이면 ① 만 그린다(설비 일정 없음 — 그 자리는 화면이 둔다). ② 의 제품 줄도
      `product_demand` 를 따른다(① · ② 함께 펼침 — 2026-11-12 사용자 답 q4 (가)).
    - `selected_month` 는 지금 보는 달이다. 축에 없으면 표시하지 않는다.
    - `collapsed` 는 접힌 구획 id(`SECTION_IDS`)다. 접힌 구획은 제목 줄(▸)만 남는다. 없는 구획의
      id 는 무시한다.
    - `assumption` 을 넘기면 ① 끝에 「UPEH 가정」 세 줄이 서고, 부족 띠는 그 요약의 판정을, ② · ③
      의 소요대수는 그 요약의 소요를 쓴다. `dynamic` 도 그때는 가정 계획이어야 한다(페이지가
      맞춘다).

    행 모델은 `build_process_capa_rows` 가 낸다 — 엑셀 내려받기도 같은 행을 읽는다.
    """
    model = build_process_capa_rows(
        process_label=process_label,
        months=months,
        summary=summary,
        thresholds=thresholds,
        product_demand=product_demand,
        home_rates=home_rates,
        dynamic=dynamic,
        collapsed=collapsed,
        assumption=assumption,
    )
    rows = model.rows
    axis = list(model.axis)
    index_of = {month: position for position, month in enumerate(axis)}
    height = stack_rows(rows)
    selected_index = index_of.get(int(selected_month)) if selected_month is not None else None

    label_figure = _label_figure(rows, height)
    month_figure = _month_figure(
        rows,
        axis,
        height,
        shortage_indices=model.shortage_indices,
        selected_index=selected_index,
        today_x=model.today_x,
        dynamic_rows=rows[model.dynamic_first :] if model.dynamic_first is not None else [],
        dynamic=dynamic,
    )
    flush_layout_items(label_figure, month_figure)
    keep_unselected_opaque(month_figure)
    return ProcessCapaCanvas(
        labels=label_figure,
        months=month_figure,
        height=height,
        hidden_units=model.hidden_units,
        hidden_arrow_units=model.hidden_arrow_units,
        row_ids=tuple(row.row_id for row in rows),
    )


# ================================================================== ① Static 기준


def _summary_statuses(summary: pd.DataFrame, axis: Sequence[int]) -> dict[int, str | None]:
    records = _by_month(summary, axis)
    return {month: _status(records.get(month, {}).get(STATUS_COLUMN)) for month in axis}


# 구획 제목 글자. 끝에 펼침(▾)·접힘(▸)을 붙인다 — ① 소요대수 줄의 ▾/▸ 와 같은 꼴이다.
_SECTION_TITLES: Final[Mapping[str, str]] = {
    SECTION_SUMMARY: "① Static 기준",
    SECTION_DYNAMIC: "② 일정 가용",
    SECTION_EFFECT: "③ 비가동",
    SECTION_UNITS: "④ 단축",
    SECTION_DOWNTIME: "⑤ 비가동 일정",
}


def _section_title_row(section: str, folded: Collection[str], *, hover: str = "") -> _Row:
    """구획 제목 줄. 접혔으면 「▸」, 펼쳤으면 「▾」 — 줄 높이는 그대로다. 세부 글은 두지 않고 출처 ·
    단위 같은 말은 제목 줄 풍선(`hover`)과 Guide 가 적는다(2026-11-12 사용자 답 k-c1 · k-c2)."""
    mark = "▸" if section in folded else "▾"
    row = _title_row(section, f"{_SECTION_TITLES[section]} {mark}", "")
    row.label_hover = hover
    return row


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
                f"<br>확보 기준 {threshold_percent_label(secure)} · "
                f"경고 기준 {threshold_percent_label(warning)}"
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
        label=_balance_label(thresholds, axis),
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    # 참고 줄 — 달마다 확보 기준(%) 그대로다. 강조하지 않는다(회색 글자, 면색·굵기 없음).
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
        rate.cells[index], balance.cells[index] = _judgement_cells(
            head, record, thresholds, month, cause=record.get(CAUSE_COLUMN)
        )
        reference.cells[index] = _Cell(
            text=threshold_percent_label(secure),
            muted=True,
            hover=(
                f"{head} · 확보 기준 {threshold_percent_label(secure)} · "
                f"경고 기준 {threshold_percent_label(warning)}"
            ),
        )
    rows = [_section_title_row(SECTION_SUMMARY, (), hover=SUMMARY_TITLE_HOVER)]
    rows += [owned, available, required]
    if product_demand is not None:
        parents = {month: _number(records.get(month, {}).get("소요대수")) for month in axis}
        rows += _product_rows(axis, product_demand, parents, prefix=ROW_PRODUCT_PREFIX)
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
    """① 끝 「UPEH 가정」 세 줄 — 구간 달만 값, 밖은 빈칸(풍선 「구간 밖 — 가정 전과 같음」)."""
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
        label=f"{prefix} · 확보 기준 과부족",
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        if month not in assumption.months:
            outside = f"{head} · 구간 밖 — 가정 전과 같음"
            for row in (required, rate, balance):
                row.cells[index] = _Cell(text="", muted=True, hover=outside)
            continue
        official = records.get(month, {})
        record = assumed.get(month, {})
        demand = _number(record.get("소요대수"))
        official_demand = _number(official.get("소요대수"))
        change = _assumed_change(official_demand, demand, factor)
        required.cells[index] = _Cell(
            text=_one(demand),
            bold=True,
            hover=f"{head} · UPEH 가정 {assumption.percent}% 소요대수 {_one(demand)}대{change}",
        )
        rate_cell, balance_cell = _judgement_cells(
            head, record, thresholds, month, cause=record.get(CAUSE_COLUMN)
        )
        rate_cell.hover += (
            f"<br>UPEH 가정 {assumption.percent}% — 가정 전 확보율 "
            f"{_percent(_number(official.get('확보율')))}"
        )
        value = _whole(record.get(BALANCE_COLUMN))
        official_value = _whole(official.get(BALANCE_COLUMN))
        if value is not None and official_value is not None:
            balance_cell.hover += (
                f"<br>가정 전 {_signed_int(official_value)} → 가정 {_signed_int(value)}"
            )
        rate.cells[index], balance.cells[index] = rate_cell, balance_cell
    return [required, rate, balance]


def _product_rows(
    axis: Sequence[int],
    product_demand: pd.DataFrame,
    parents: Mapping[int, float | None],
    *,
    prefix: str,
    factors: Mapping[int, float] | None = None,
) -> list[_Row]:
    """「제품별 소요대수」 의 분류 줄 — `parents` 는 부모 소요대수 줄의 달별 값이다.

    `factors` 를 주면(② — UPEH 가정이 걸린 달 → f) 그 달 값을 ÷f 한다. 가정은 소요대수만 ÷f 하므로
    분류마다 ÷f 해야 줄을 다 더한 값이 부모(가정 소요)와 같다.
    """
    rows: list[_Row] = []
    for position, record in enumerate(product_demand.to_dict("records")):
        label = str(record.get(PRODUCT_LABEL_COLUMN, ""))
        other = bool(record.get(OTHER_ROW_COLUMN, False))
        row = _Row(
            f"{prefix}{label}",
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
            factor = (factors or {}).get(month)
            assumed = ""
            if factor is not None:
                value = value / factor
                assumed = f" · UPEH 가정 ÷{factor:g}"
            parent = parents.get(month)
            share = f" · 소요의 {value / parent:.0%}" if parent else ""
            row.cells[index] = _Cell(
                text=_one(value),
                hover=(
                    f"<b>{month_label(month)}</b> · {html.escape(label)} {_one(value)}대"
                    f"{share}{assumed}"
                ),
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
    """UPEH 가정 소요 칸 풍선의 둘째 줄 — 「가정 전 49.80 ÷ 1.5 = 33.20 (−16.60대)」. 적힌 가정 전
    소요로 다시 셈한 값이 가정 소요와 다르면 「≈」(근거 패널 ③ 의 「소요 = 가정 전 ÷ f」 와
    같다)."""
    if official is None or demand is None:
        return ""
    mark = equals_mark(_two(demand), _two(round(official, 2) / factor))
    return (
        f"<br>가정 전 {_two(official)} ÷ {factor:g} {mark} {_two(demand)} "
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
        f"<br>판정 {_STATUS_NAMES.get(status, status)} — "
        f"확보 기준 {threshold_percent_label(secure)}"
        f" · 경고 기준 {threshold_percent_label(warning)}"
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
        return f"{head} · 확보 기준 과부족 {_EMPTY}"
    # 정수 옆에 올림·내림 전 값(가용 − 소요 × 판정 경계)을 소수 둘째 자리로 단다. 과부족은 확보 기준
    # 의 판정 경계(110% 면 109.5% — 사사오입 판정)에 대한 대수다(`securement_balance`). 그 아래 식의
    # 적힌 가용·소요(첫째 자리)로 다시 셈한 값이 그 값과 다르면 식 앞에 「≈」 를 둔다.
    bound = judgment_boundary(secure)
    unrounded = ""
    mark = EQUALS
    if available is not None and demand is not None:
        raw = _signed_two(available - demand * bound)
        unrounded = f" ({raw})"
        mark = equals_mark(raw, _signed_two(round(available, 1) - round(demand, 1) * bound))
    text = (
        f"{head} · 확보 기준 과부족 {_signed_int(balance)}대{unrounded}"
        f"<br>{f'{APPROX} ' if mark == APPROX else ''}가용 {_one(available)} {_MINUS} "
        f"소요 {_one(demand)} × {boundary_percent_label(secure)} (부족은 올림, 여유는 내림)"
    )
    held = (
        balance == 0
        and available is not None
        and demand is not None
        and surplus_held_at_zero(available, demand, secure)
    )
    if held:
        # 반올림으로만 확보인 달 — 경계식은 1대 이상 남지만 확보율이 기준 밑이라 여유가 아니다.
        text += f"<br>반올림으로 겨우 확보 — {threshold_percent_label(secure)} 에 못 미쳐 여유 0"
    reason = "" if _blank(cause) else str(cause)
    if reason:
        text += f"<br>원인 {html.escape(reason)}"
    return text


# ================================================================== ② ~ ⑤ 설비 일정


def _dynamic_rows(
    axis: Sequence[int],
    dynamic: DynamicCanvasInput,
    folded: Collection[str],
    *,
    process_label: str,
    summary: Mapping[int, Mapping[str, object]],
    judged: Mapping[int, Mapping[str, object]],
    thresholds: SecurementThresholds,
    product_demand: pd.DataFrame | None,
    assumption: AssumptionCanvasInput | None,
) -> tuple[list[_Row], int, int]:
    """② 일정 가용 · ③ 비가동 · ④ 단축 · ⑤ 비가동 일정 행.

    `summary` 는 ① Static 요약, `judged` 는 판정 기준 요약(UPEH 가정이 켜지면 가정 요약)의 달별
    레코드다. ② · ③ 의 소요대수는 판정 기준의 소요이고, 확보율 · 과부족 칸은 그 구획의 가용으로 낸
    제 판정 색이다(부족 띠는 판정 기준 하나 — 2026-11-12 사용자 답 q8 (가)).
    """
    today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
    # 오늘이 든 생산월보다 앞선 달은 흐리게 둔다(② · ③ 의 대수 줄 · ④ · ⑤).
    today_month = today_position.month
    bridge = _by_month(dynamic.bridge, axis)
    demand = {month: _number(judged.get(month, {}).get("소요대수")) for month in axis}
    free = {month: _free_available(bridge.get(month)) for month in axis}
    rows = _schedule_rows(
        axis,
        dynamic,
        folded,
        process_label=process_label,
        bridge=bridge,
        free=free,
        demand=demand,
        thresholds=thresholds,
        product_demand=product_demand,
        assumption=assumption,
    )
    rows += _effect_rows(
        axis,
        dynamic,
        folded,
        process_label=process_label,
        bridge=bridge,
        free=free,
        summary=summary,
        demand=demand,
        thresholds=thresholds,
        assumption=assumption,
    )
    manual_row = _manual_downtime_row(axis, bridge, today_month)
    if not dynamic.has_units:
        # 호기 줄이 없는 공정은 ④ · ⑤ 가 서지 않는다 — 입력 비가동 줄은 그 몫이 드는 ③ 끝에 둔다
        # (③ 을 접으면 함께 접는다).
        if manual_row is not None and SECTION_EFFECT not in folded:
            rows.append(manual_row)
        # ④ · ⑤ 가 서지 않는 공정의 까닭 — ③ 을 접어도 남긴다(④ · ⑤ 자리의 글이다).
        rows.append(_note_row("no_units", "호기 일정 없음 — 기존보유만 있는 공정입니다"))
        return rows, 0, 0
    hidden_units = 0
    hidden_arrow_units = 0
    # 표지(◆ 반입 · ● 기여 시작 · ◀ 목표 기여 시작)의 뜻은 Guide 「시트 범례」 가 적는다.
    rows.append(_section_title_row(SECTION_UNITS, folded))
    if SECTION_UNITS not in folded:
        unit_rows, hidden_units = _unit_rows(axis, dynamic)
        rows += unit_rows
    # 진한 화살표 · 끝 날의 읽는 법도 Guide 「시트 범례」 다(설계 규칙 UI-TXT-01 · 02).
    rows.append(_section_title_row(SECTION_DOWNTIME, folded))
    if SECTION_DOWNTIME not in folded:
        if manual_row is not None:
            rows.append(manual_row)
        arrow_rows, hidden_arrow_units = _arrow_rows(axis, dynamic)
        rows += arrow_rows
    return rows, hidden_units, hidden_arrow_units


def _free_available(record: Mapping[str, object] | None) -> float | None:
    """② 가용대수 — 비가동을 빼기 전 설비 일정 기준 가용(기존보유 + 호기 가용 + 호기 비가동 손실).

    비가동(호기 비가동 · 입력 비가동)은 ③ 비가동에서 한 번만 뺀다(2026-11-12 사용자 답 n1 (가)). 그
    달 행이 없으면 None 이다.
    """
    if not record:
        return None
    parts = [_number(record.get(name)) for name in ("기존보유", "호기 가용", "호기 비가동 손실")]
    if any(part is None for part in parts):
        return None
    return _tidy(sum(part or 0.0 for part in parts))


def _schedule_rows(
    axis: Sequence[int],
    dynamic: DynamicCanvasInput,
    folded: Collection[str],
    *,
    process_label: str,
    bridge: Mapping[int, Mapping[str, object]],
    free: Mapping[int, float | None],
    demand: Mapping[int, float | None],
    thresholds: SecurementThresholds,
    product_demand: pd.DataFrame | None,
    assumption: AssumptionCanvasInput | None,
) -> list[_Row]:
    """② 일정 가용 — 총보유대수 · 가용대수 · 전월 대비 · 소요대수(▾ 면 제품 줄) · 확보율 · 확보 기준
    과부족(2026-11-12 사용자 답 k-c2 · q3 · q4 · n1). ① Static 기준과 같은 면 · 판정 칸이다."""
    today_position = production_position(dynamic.today, dynamic.cutoff_days, axis)
    today_month = today_position.month
    tips = [
        f"설비 DB · 환산대수 · 칸 = 생산월(Cut-off {dynamic.cutoff_days}일) — "
        f"{_production_example(dynamic.cutoff_days, axis)}",
        "총보유대수는 달력 월(Cut-off 없이) · 비가동은 ③ 비가동에서 뺍니다",
    ]
    if not today_position.before and not today_position.after:
        tips.append(f"점선은 오늘({dynamic.today:%m.%d})")
    title = _section_title_row(SECTION_DYNAMIC, folded, hover="<br>".join(tips))
    if SECTION_DYNAMIC in folded:
        return [title]
    supply_label, supply_month = tokens.SUMMARY_SUPPLY_CLASSIFICATION, tokens.SUMMARY_SUPPLY_SURFACE
    owned = _Row(
        ROW_DYNAMIC_OWNED,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="총보유대수",
        label_fill=supply_label,
        month_fill=supply_month,
        group_start=True,
    )
    available = _Row(
        ROW_DYNAMIC_AVAILABLE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="가용대수",
        label_fill=supply_label,
        month_fill=supply_month,
    )
    delta = _Row(
        ROW_DYNAMIC_DELTA,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="전월 대비",
        label_fill=supply_label,
        month_fill=supply_month,
    )
    owned_records = _by_month(
        dynamic.owned_units.rename(columns={"년월": MONTH})
        if "년월" in dynamic.owned_units.columns
        else pd.DataFrame(),
        axis,
    )
    moves = unit_month_changes(dynamic.unit_months, axis)
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        past = month < today_month
        owned.cells[index] = _owned_cell(head, owned_records.get(month), past=past)
        record = bridge.get(month, {})
        available.cells[index] = _schedule_available_cell(head, record, free.get(month), past=past)
        if index == 0:
            delta.cells[index] = _Cell(
                text=_EMPTY, muted=True, hover=f"{head} · 축 첫 달이라 전월 대비가 없습니다"
            )
            continue
        previous = axis[index - 1]
        delta.cells[index] = _schedule_delta_cell(
            head,
            free.get(month),
            free.get(previous),
            record,
            bridge.get(previous, {}),
            moves.get(month, ()),
            past=past,
        )
    rows = [title, owned, available, delta]
    factors = _assumed_factors(axis, assumption)
    products = (
        _product_rows(
            axis,
            product_demand,
            demand,
            prefix=ROW_DYNAMIC_PRODUCT_PREFIX,
            factors=factors,
        )
        if product_demand is not None
        else []
    )
    rows += _judged_rows(
        axis,
        free,
        demand,
        thresholds,
        process_label=process_label,
        ids=(ROW_DYNAMIC_REQUIRED, ROW_DYNAMIC_RATE, ROW_DYNAMIC_BALANCE),
        required_label=f"소요대수 {'▾' if product_demand is not None else '▸'}",
        products=products,
        assumption=assumption,
    )
    return rows


def _production_example(cutoff_days: int, axis: Sequence[int]) -> str:
    """「칸 = 생산월」 예 — 첫 달 25일 Qual 이 어느 달 칸에 서는가(다음 날 + Cut-off)."""
    first = int(axis[0])
    qual = date(first // 100, first % 100, 25)
    position = production_position(qual + timedelta(days=1), cutoff_days, axis)
    return f"{qual:%m.%d} Qual 은 {position.month % 100}월 칸"


def _owned_cell(head: str, record: Mapping[str, object] | None, *, past: bool) -> _Cell:
    """② 총보유대수 칸 — 풍선은 「기존보유 a + 반입 b − 반출/이설 c」 와 달력 월 표지."""
    if not record:
        return _Cell(text=_EMPTY, muted=True, hover=f"{head} · 총보유대수 {_EMPTY}")
    total = _number(record.get("총보유대수"))
    held = _number(record.get("기존보유"))
    arrived = _number(record.get("반입"))
    gone = _number(record.get("반출이설"))
    written = (
        round(held, 1) + round(arrived, 1) - round(gone, 1)
        if held is not None and arrived is not None and gone is not None
        else None
    )
    mark = equals_mark(_one(total), _one(written))
    return _Cell(
        text=_one(total),
        muted=past,
        hover=(
            f"{head} · 총보유대수 {_one(total)}대 — 달력 월 기준(Cut-off 없이) · 환산"
            f"<br>기존보유 {_one(held)} + 반입 {_one(arrived)} {_MINUS} 반출/이설 {_one(gone)} "
            f"{mark} {_one(total)}"
        ),
    )


def _schedule_available_cell(
    head: str, record: Mapping[str, object], value: float | None, *, past: bool
) -> _Cell:
    """② 가용대수 칸 — 비가동을 빼기 전 값. 풍선은 「기존보유 + 호기 = 가용」(적힌 수로 검산)."""
    if value is None:
        return _Cell(text=_EMPTY, muted=True, hover=f"{head} · 설비 일정에 없는 달")
    held = _number(record.get("기존보유")) or 0.0
    units = (_number(record.get("호기 가용")) or 0.0) + (
        _number(record.get("호기 비가동 손실")) or 0.0
    )
    mark = equals_mark(_one(value), _one(round(held, 1) + round(units, 1)))
    return _Cell(
        text=_one(value),
        muted=past,
        hover=(
            f"{head} · 가용대수 {_one(value)} (설비 일정 · 환산 · 생산월)"
            f"<br>기존보유 {_one(held)} + 호기 {_one(units)} {mark} {_one(value)} — 비가동 빼기 전"
        ),
    )


def _schedule_delta_cell(
    head: str,
    value: float | None,
    previous: float | None,
    record: Mapping[str, object],
    previous_record: Mapping[str, object],
    moves: Sequence[tuple[str, float]],
    *,
    past: bool,
) -> _Cell:
    """② 전월 대비 칸 — 비가동을 빼기 전 가용의 증감. 풍선 첫 줄은 「신규 + · 정지·반출 −」 갈림,
    아래는 호기 묶음별 몫을 큰 차례로 여섯까지(나머지는 「외 n대」 — 2026-11-12 사용자 답 k-c3)."""
    if value is None or previous is None:
        return _Cell(text=_EMPTY, muted=True, hover=f"{head} · 전월 대비 {_EMPTY}")
    change = _tidy(value - previous)
    gained = _number(record.get("신규")) or 0.0
    lost = _number(record.get("반출이설")) or 0.0
    held_change = _tidy(
        (_number(record.get("기존보유")) or 0.0) - (_number(previous_record.get("기존보유")) or 0.0)
    )
    parts = [f"신규 {_signed_one(gained)}", f"정지·반출 {_signed_one(lost)}"]
    written_parts = [_signed_one(gained), _signed_one(lost)]
    if held_change != 0:
        parts.append(f"기존보유 {_signed_one(held_change)}")
        written_parts.append(_signed_one(held_change))
    written = [written_value(text) for text in written_parts]
    recomputed = (
        _signed_one(sum(number for number in written if number is not None))
        if all(number is not None for number in written)
        else ""
    )
    mark = equals_mark(_signed_one(change), recomputed)
    lines = [f"{head} · 전월 대비 {_signed_one(change)} {mark} " + " · ".join(parts)]
    shown = [f"{html.escape(unit)} {_signed_two(share)}" for unit, share in moves[:_MOVE_LIMIT]]
    for start in range(0, len(shown), _MOVES_PER_LINE):
        lines.append(" · ".join(shown[start : start + _MOVES_PER_LINE]))
    if len(moves) > _MOVE_LIMIT:
        lines.append(f"외 {len(moves) - _MOVE_LIMIT}대")
    return _Cell(text=_signed_one(change), muted=past, hover="<br>".join(lines))


def _effect_rows(
    axis: Sequence[int],
    dynamic: DynamicCanvasInput,
    folded: Collection[str],
    *,
    process_label: str,
    bridge: Mapping[int, Mapping[str, object]],
    free: Mapping[int, float | None],
    summary: Mapping[int, Mapping[str, object]],
    demand: Mapping[int, float | None],
    thresholds: SecurementThresholds,
    assumption: AssumptionCanvasInput | None,
) -> list[_Row]:
    """③ 비가동 — 비가동대수 · 실가용대수 · 소요대수(합계만) · 확보율 · 확보 기준 과부족
    (2026-11-12 사용자 답 q5 (가) · q5b (가)).

    비가동대수는 호기별 비가동 일정이 깎은 대수 + 입력 비가동 대수(가용에서 실제로 뺀 몫 —
    `downtime_impact` 의 `비가동 손실`)다. 실가용대수는 고른
    기준(`DynamicCanvasInput.downtime_basis` — Static 이면 ① 가용대수, 일정이면 ② 가용대수)에서
    비가동대수를 뺀 값이고 0 아래로 내려가지 않는다. 기준이 일정이면 실가용이 필요 단축 일정의
    가용(계획 `가용대수`)과 같다.
    """
    today_month = production_position(dynamic.today, dynamic.cutoff_days, axis).month
    static_basis = dynamic.downtime_basis != BASIS_SCHEDULE
    basis_name = "Static 가용" if static_basis else "일정 가용"
    title = _section_title_row(
        SECTION_EFFECT,
        folded,
        hover=(
            "비가동대수를 뺀 실가용대수로 본 확보율 · 과부족<br>"
            + (
                "비가동 기준 Static — ① 가용대수에서 뺍니다"
                if static_basis
                else "비가동 기준 일정 — ② 가용대수에서 뺍니다"
            )
        ),
    )
    if SECTION_EFFECT in folded:
        return [title]
    supply_label, supply_month = tokens.SUMMARY_SUPPLY_CLASSIFICATION, tokens.SUMMARY_SUPPLY_SURFACE
    loss_row = _Row(
        ROW_EFFECT_LOSS,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="비가동대수",
        label_fill=supply_label,
        month_fill=supply_month,
        group_start=True,
    )
    real_row = _Row(
        ROW_EFFECT_AVAILABLE,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="실가용대수",
        label_fill=supply_label,
        month_fill=supply_month,
    )
    impacts = _by_month(downtime_impact(dynamic.bridge, dynamic.process_months), axis)
    real: dict[int, float | None] = {}
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        past = month < today_month
        impact = impacts.get(month, {})
        unit_loss = _number(impact.get("호기 비가동 손실")) or 0.0
        manual_loss = _number(impact.get("입력 비가동 손실")) or 0.0
        loss = _number(impact.get("비가동 손실")) or 0.0
        base = _number(summary.get(month, {}).get("가용대수")) if static_basis else free.get(month)
        if base is None or month not in bridge:
            real[month] = None
        else:
            real[month] = max(0.0, _tidy(base - loss))
        loss_row.cells[index] = _loss_cell(head, loss, unit_loss, manual_loss, past=past)
        real_row.cells[index] = _real_cell(head, real[month], base, loss, basis_name, past=past)
    return [
        title,
        loss_row,
        real_row,
        *_judged_rows(
            axis,
            real,
            demand,
            thresholds,
            process_label=process_label,
            ids=(ROW_EFFECT_REQUIRED, ROW_EFFECT_RATE, ROW_EFFECT_BALANCE),
            required_label="소요대수",
            products=[],
            assumption=assumption,
        ),
    ]


def loss_text(value: float) -> str:
    """비가동대수 글 — 소수 첫째 자리, 0 이 아닌 값이 0 으로 적히면 0 이 아니게 적힐 때까지 한
    자리씩 더 본다(0.05 미만이 「0.0」 으로 읽히지 않게)."""
    digits = 1
    text = _one(value, digits)
    while round(value, 9) != 0 and written_value(text) == 0 and digits < _NONZERO_LAST_DIGITS:
        digits += 1
        text = _one(value, digits)
    return text


def _loss_cell(
    head: str, loss: float, unit_loss: float, manual_loss: float, *, past: bool
) -> _Cell:
    """③ 비가동대수 칸 — 깎은 것이 없으면 빈칸. 풍선은 「호기 비가동 a + 입력 비가동 b」 갈림(0 인
    쪽은 뺀다, 둘을 적힌 대로 더한 값이 칸 글과 다르면 「≈」). 입력 몫은 ⑤ 첫 줄 풍선 「가용에서 b
    뺌」 과 같은 글이다(`manual_removed_text`)."""
    if round(loss, 9) <= 0:
        return _Cell(muted=past, hover=f"{head} · 비가동 없음 — 가용을 깎은 비가동이 없습니다")
    text = loss_text(loss)
    parts = [
        (name, writer(value))
        for name, value, writer in (
            ("호기 비가동", unit_loss, loss_text),
            ("입력 비가동", manual_loss, manual_removed_text),
        )
        if round(value, 9) > 0
    ]
    split = " + ".join(f"{name} {part}" for name, part in parts)
    if len(parts) == 2:
        written = [written_value(part) for _, part in parts]
        recomputed = (
            loss_text(sum(number for number in written if number is not None))
            if all(number is not None for number in written)
            else ""
        )
        if equals_mark(text, recomputed) == APPROX:
            split = f"{APPROX} {split}"
    return _Cell(text=text, muted=past, hover=f"{head} · 비가동대수 {text}<br>{split}")


def _real_cell(
    head: str,
    value: float | None,
    base: float | None,
    loss: float,
    basis_name: str,
    *,
    past: bool,
) -> _Cell:
    """③ 실가용대수 칸 — 「기준 가용 − 비가동 = 실가용」(0 에서 멈췄으면 그 표지)."""
    if value is None or base is None:
        return _Cell(text=_EMPTY, muted=True, hover=f"{head} · 실가용대수 {_EMPTY}")
    clamped = round(base - loss, 9) < 0
    loss_written = loss_text(loss) if round(loss, 9) > 0 else "0"
    written_loss = written_value(loss_written) or 0.0
    mark = equals_mark(_one(value), _one(max(0.0, round(base, 1) - written_loss)))
    return _Cell(
        text=_one(value),
        muted=past,
        hover=(
            f"{head} · 실가용대수 {_one(value)}"
            f"<br>{basis_name} {_one(base)} {_MINUS} 비가동 {loss_written} {mark} {_one(value)}"
            + ("<br>비가동이 가용보다 커 0 에서 멈췄습니다" if clamped else "")
        ),
    )


def _assumed_factors(
    axis: Sequence[int], assumption: AssumptionCanvasInput | None
) -> dict[int, float]:
    """UPEH 가정이 걸린 달 → f(가정 % ÷ 100). 가정이 없으면 빈 dict."""
    if assumption is None:
        return {}
    factor = assumption.percent / 100
    return {month: factor for month in axis if month in assumption.months}


def _judged_rows(
    axis: Sequence[int],
    available: Mapping[int, float | None],
    demand: Mapping[int, float | None],
    thresholds: SecurementThresholds,
    *,
    process_label: str,
    ids: tuple[str, str, str],
    required_label: str,
    products: list[_Row],
    assumption: AssumptionCanvasInput | None,
) -> list[_Row]:
    """소요대수 · (제품 줄) · 확보율 · 확보 기준 과부족 — ① Static 기준과 같은 면 · 판정 칸 · 풍선.

    판정은 ① 요약과 같은 길이다(`judge_supply`). `available` 이 그 구획의 가용(② 일정 가용 · ③
    실가용)이고 `demand` 는 판정 기준의 소요다.
    """
    required_id, rate_id, balance_id = ids
    judged = _by_month(
        judge_supply(
            available,
            demand,
            process=process_label,
            months=axis,
            thresholds=thresholds,
        ),
        axis,
    )
    required = _Row(
        required_id,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=required_label,
        label_bold=True,
        label_fill=tokens.SUMMARY_DEMAND_CLASSIFICATION,
        month_fill=tokens.SUMMARY_DEMAND_SURFACE,
        group_start=True,
    )
    rate = _Row(
        rate_id,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label="확보율",
        label_fill=tokens.SURFACE_CLASSIFICATION,
        group_start=True,
    )
    balance = _Row(
        balance_id,
        _VALUE,
        VALUE_ROW_HEIGHT_PX,
        label=_balance_label(thresholds, axis),
        label_fill=tokens.SURFACE_CLASSIFICATION,
    )
    factors = _assumed_factors(axis, assumption)
    for index, month in enumerate(axis):
        head = f"<b>{month_label(month)}</b>"
        need = demand.get(month)
        assumed = (
            f" · UPEH 가정 {assumption.percent}%"
            if assumption is not None and month in factors
            else ""
        )
        required.cells[index] = _Cell(
            text=_one(need), bold=True, hover=f"{head} · 소요대수 {_one(need)}대{assumed}"
        )
        record = judged.get(month)
        if record is None:
            rate.cells[index] = _Cell(text=_EMPTY, muted=True, hover=f"{head} · 확보율 {_EMPTY}")
            balance.cells[index] = _Cell(
                text=_EMPTY, muted=True, hover=f"{head} · 확보 기준 과부족 {_EMPTY}"
            )
            continue
        rate.cells[index], balance.cells[index] = _judgement_cells(
            head, record, thresholds, month, cause=None
        )
    return [required, *products, rate, balance]


def _balance_label(thresholds: SecurementThresholds, axis: Sequence[int]) -> str:
    """확보 기준 과부족 줄 이름 — 월별 예외가 없으면 기준을 함께 적는다(① · ② · ③ 같은 이름)."""
    if thresholds.exception_months_within(axis):
        return "확보 기준 과부족"
    return f"확보 기준({threshold_percent_label(thresholds.default_secure)}) 과부족"


def _judgement_cells(
    head: str,
    record: Mapping[str, object],
    thresholds: SecurementThresholds,
    month: int,
    *,
    cause: object,
) -> tuple[_Cell, _Cell]:
    """확보율 칸 · 확보 기준 과부족 칸 한 쌍 — 판정 3색(과부족은 경고 · 부족만 칠함)과 풍선 식.

    ① Static 기준 · UPEH 가정 줄 · ② 일정 가용 · ③ 비가동이 같은 칸을 쓴다(같은 역할은 같은 꼴 —
    설계 규칙 UI-CON-03).
    """
    available = _number(record.get("가용대수"))
    demand = _number(record.get("소요대수"))
    rate_value = _number(record.get("확보율"))
    status = _status(record.get(STATUS_COLUMN))
    secure, warning = thresholds.for_month(month)
    fill = _status_color(status)
    rate = _Cell(
        text=_percent(rate_value) if status is not None else _EMPTY,
        fill=fill,
        bold=fill is not None,
        hover=_rate_hover(head, rate_value, available, demand, status, secure, warning),
    )
    value = _whole(record.get(BALANCE_COLUMN))
    painted = _status_color(status) if status in _SHORT_STATUSES else None
    balance = _Cell(
        text=_signed_int(value) if value is not None else _EMPTY,
        fill=painted,
        bold=painted is not None,
        hover=_balance_hover(head, value, available, demand, secure, cause),
    )
    return rate, balance


def _manual_downtime_row(
    axis: Sequence[int], bridge: Mapping[int, Mapping[str, object]], today_month: int
) -> _Row | None:
    """⑤ 첫 줄 「월별 비가동대수(입력)」 — 축 안 어느 달에도 입력이 없으면 None(줄이 없다).

    칸 글은 그 달에 넣은 대수(소수 둘째 자리까지)이고 빈 달은 비운다. 입력이 그 달 가용(기존보유 +
    호기 가용)보다 커 가용이 0 에서 멈춘 칸은 「⚠」 와 경고색이다 — 풍선이 실제로 뺀 몫을 적는다
    (`manual_removed_text`).
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
            "호기별 비가동과 별도 손실 — ③ 비가동대수에 듭니다"
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
                f"{head} · 입력 비가동 {text}대 — 가용에서 {manual_removed_text(removed)} 뺌"
                + (
                    "<br>⚠ 그 달 가용보다 커 가용이 0 에서 멈췄습니다(넘친 만큼은 빼지 않음)"
                    if overdrawn
                    else ""
                )
            ),
        )
    return row


_NONZERO_LAST_DIGITS: Final = 9
"""`loss_text` 가 `one` 에 넘기는 가장 큰 자릿수 — `round(값, 9)` 가 0 이 아닌 값은 0 이 아니게
적힌다(빈칸 판정과 같은 문턱)."""


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
        detail = f"가정으로 단축 불필요 · 가정 전 {_MINUS}{change[0]}일"
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
    """UPEH 가정 계획만 붙는 넷째 줄(앞 `<br>` 포함) — 표지와, 가정 전과 단축일수가 다른 호기면
    「가정 전 −N일 → 가정 −M일」. 가정 전 계획이면 빈 글자."""
    if dynamic.official_pulls is None:
        return ""
    mark = "UPEH 가정 계획"
    change = dynamic.official_pulls.get(str(event.get("호기")))
    if change is not None:
        official_days, assumed_days = change
        mark += f" · 가정 전 {_MINUS}{official_days}일 → 가정 " + (
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


# ------------------------------------------------------------------ ③·④ 글(엑셀)


class TrackText(NamedTuple):
    """③·④ 줄 달 칸 하나의 글 — 그림 대신 엑셀에 적는다(`process_capa_workbook`). 표지 · 글은
    그림과 같은 자리(`_unit_marks` · 화살표 꼬리 · 촉)에서 낸다."""

    text: str
    warning: bool = False
    """「반입 전」 배지가 선 칸 — 그림의 배지처럼 경고색으로 칠한다."""

    loss: bool = False
    """가용을 깎은 비가동 화살표가 지나는 칸 — 그 화살표 색 글자."""

    muted: bool = False
    """영향 없는 비가동 화살표만 지나는 칸 — 흐린 글자."""


def track_texts(
    row: _Row, axis: Sequence[int], dynamic: DynamicCanvasInput
) -> dict[int, TrackText]:
    """③ 호기 줄 · ④ 화살표 줄을 달 칸(열 index)마다 글로 — 그림 대신 엑셀 칸에 적는다.

    ③ 은 ◆ 반입 · ● 기여 시작 · ◀ −N일(「반입 전」 이면 그 앞에) · 그 사이 ━ · ◌ 신규 필요 ·
    ▼ 정지·반출/이설 · 해소(해소 기여 월 눈금)를, ④ 는 화살표 꼬리 칸에 그림 글(비가동유형 ·
    ◂ 이전부터 · 계속 ▸)과 지나는 칸에 ━ ▶(가용을 깎음) · ┄(영향 없음)을 적는다. 같은 칸의
    표지는 왼쪽부터 「 · 」 로 잇는다. 그 밖의 줄은 빈 dict 다.

    ◀ 는 촉이 선 칸(목표 기여 시작의 생산월)에 둔다. 「−N일」 · 「반입 전」 은 그림에서 촉 왼쪽에
    펴지는 글이라 그 글 가운데가 든 칸에 적는다 — 촉이 달 경계에 서면 글은 앞 달 칸이고, 그때
    「−N일」 은 ◀ 와 갈려 따로 선다. 경고색 칠은 「반입 전」 이 든 칸이다.
    """
    count = len(axis)
    if count == 0:
        return {}
    if row.kind == _ARROW:
        return _arrow_texts(row.payload, count)
    if row.kind != _UNIT or not isinstance(row.payload, tuple):
        return {}
    kind, record = row.payload
    marks = _unit_marks(kind, record, axis, dynamic)
    pieces: list[tuple[float, str]] = []
    warned: set[int] = set()

    def column(x: float) -> int:
        return min(count - 1, max(0, math.floor(x)))

    exit_kind = "" if _blank(record.get("반출이설구분")) else str(record.get("반출이설구분"))
    if marks.exit is not None:
        pieces.append((marks.exit, f"▼ {exit_kind or '정지·반출/이설'}"))
    if kind != "exit":
        if marks.virtual is not None:
            pieces.append((marks.virtual, f"◌ {_VIRTUAL_TEXT}"))
        if marks.arrival is not None:
            pieces.append((marks.arrival, "◆ 반입"))
        if marks.pull is not None:
            start_x, target_x = marks.pull
            column_px = tokens.MONTH_COLUMN_WIDTH_PX
            days = f"{_MINUS}{marks.pull_days}일"
            # 글 가운데 — 앵커(`_draw_unit`)에서 어림 폭(`_unit_span` 과 같은 몫)의 반만큼 왼쪽.
            label_x = (
                target_x
                - _PULL_TEXT_GAP
                - _pull_label_px(marks.pull_days) * _SPAN_TEXT_SHARE / 2 / column_px
            )
            if column(label_x) == column(target_x):
                pieces.append((target_x, f"◀ {days}"))
            else:
                pieces += [(label_x, days), (target_x, "◀")]
            if marks.before_arrival:
                badge_x = (
                    _badge_right(target_x, marks.pull_days)
                    - _badge_px(_SPAN_TEXT_SHARE) / 2 / column_px
                )
                pieces.append((badge_x, _BEFORE_ARRIVAL_TEXT))
                warned.add(column(badge_x))
            pieces += [(index + 0.5, "━") for index in range(column(target_x) + 1, column(start_x))]
        if marks.start is not None:
            pieces.append((marks.start, "● 기여 시작"))
        pieces += [(index + 0.5, "해소") for index in marks.resolved]
    cells: dict[int, list[str]] = {}
    # 해소 눈금은 칸 아래 가장자리 표지라 같은 칸의 다른 표지 뒤에 적는다.
    for x, text in sorted(pieces, key=lambda piece: (piece[1] == "해소", piece[0])):
        cells.setdefault(column(x), []).append(text)
    return {
        index: TrackText(text=" · ".join(texts), warning=index in warned)
        for index, texts in cells.items()
    }


def _arrow_texts(arrows: object, count: int) -> dict[int, TrackText]:
    """④ 한 줄의 화살표들 — 꼬리 칸에 그림 글, 지나는 칸에 선 글자(`_draw_arrows` 와 같은 자리)."""
    if not isinstance(arrows, list):
        return {}
    cells: dict[int, list[tuple[str, bool]]] = {}
    for arrow in arrows:
        tail = max(0.0, _number(arrow.get("꼬리 위치")) or 0.0)
        head = min(float(count), _number(arrow.get("촉 위치")) or tail)
        first = min(count - 1, math.floor(tail))
        last = max(first, min(count - 1, math.ceil(head) - 1))
        loss = bool(arrow.get("가용 감소"))
        kind = str(arrow.get("비가동유형") or "비가동").strip()
        if len(kind) > ARROW_TYPE_MAX_CHARS:
            kind = kind[:ARROW_TYPE_MAX_CHARS] + "…"
        label = kind
        if bool(arrow.get("이전부터")):
            label += " · ◂ 이전부터"
        if bool(arrow.get("열린 구간")):
            label += " · 계속 ▸"
        line = "━" if loss else "┄"
        for index in range(first, last + 1):
            text = label if index == first else line
            if index == last and loss:
                text += " ▶" if index == first else "▶"
            cells.setdefault(index, []).append((text, loss))
    return {
        index: TrackText(
            text=" · ".join(text for text, _ in items),
            loss=any(loss for _, loss in items),
            muted=not any(loss for _, loss in items),
        )
        for index, items in cells.items()
    }


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


def _tidy(value: float) -> float:
    """끝자리 부동소수 찌꺼기를 털고 -0.0 을 0.0 으로 둔다(칸에 「-0」 이 찍히지 않게)."""
    return round(value, 9) + 0.0


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None:
        return None
    return left - (right or 0.0)


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
SUMMARY_TITLE_HEIGHT_PX: Final = title_row_height("")
