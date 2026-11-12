# Purpose: 공정 Capa 상세의 표 도구 줄·결합 월 캔버스·범례·근거 패널을 키 붙은 프래그먼트로 그린다.

"""공정 Capa 상세 — 본문 프래그먼트(`process_detail_view`)와 그 둘레.

페이지(`app_pages/process_capa_detail.py`)가 앱 전체 회차에서 공정·축·요약·설비 일정을 모두
정해 `ProcessDetailView` 하나로 넘기면, 여기서는 **지금 보는 달**에 닿는 것만 그린다.

- **표 도구 줄** — 「구획」 칩(`st.pills`, ①~⑤ 가운데 고른 것 = 펼침 — 라벨을 숨긴 칸이라 뜻은
  칩 바로 뒤 ⓘ 하나, 2026-11-10 보드 Q-8), 「비가동 기준」 고르기(`st.segmented_control` —
  Static · 일정, 설비 일정이 서는 공정에서 ③ 을 펼쳤을 때만 — 「③ 비가동」 의 실가용을 어느 가용에서
  빼나, 처음은 Static, 2026-11-12 사용자 답 q5b (가) · k-c4)와 「④ 단축」 보기 고르기(전체 · 단축
  필요만) — 둘 다 보이는 캡션 없이 라벨을 숨긴 칸이고 뜻은 마지막 고르기 바로 뒤 ⓘ 하나다(2026-11-12
  남은 물음 보드 ③-2 (가) — 1600 창 한 줄, 설계 규칙 UI-LAY-11), 「제품별 소요대수」
  펼침(`st.toggle` — ① · ② 를 함께 — q4 (가))과 펼쳤을 때의 「분류」(`st.segmented_control`),
  그리고 오른쪽 끝 「내려받기 ▾」 메뉴 하나(2026-11-10 답 Q2-7) — 「이 공정 단축 일정 CSV」(설비
  일정이 설 때만 — ④ 구획의 호기 표 곁, 설계 규칙 UI-LAY-03. 없으면 메뉴 없이 시트 엑셀 단추
  하나)와 「시트 엑셀」(늘 — 지금 화면 상태 그대로의 상세 시트를 화면 서식째, 2026-11-10 보드
  c2-picked —
  `components/process_capa_workbook.py`. 통은 회차마다 만들지 않고 조건이 바뀐 뒤 처음 그리는 회차에
  한 번 만들어 세션에 몇 벌 기억한다 — `remembered_sheet`, 그림 기억과 같은 꼴). 단축 목표 글은
  Guide 가 적는다(2026-11-12 사용자 메모 k-c4 — 고르는 위젯은 처음부터 없다). 이 줄은 조건 카드가
  아니라 본문이다 — 2026-09-29 「상세는 카드」 규칙의 예외다(펼침·분류는 2026-10-15 사용자 결정 4 —
  목업 그대로, 구획은 2026-10-22 사용자 요청 「소요대수처럼 접기」). 구획 칩은 선택지 다섯을 늘
  고정한다 — 설비 일정이 없는 공정에서 ②~⑤ 를 빼면 세션 값이 선택지 밖으로 나가 지워진다. 밖에서
  들어온 회차에는 그 길이 가리키는 구획을 다시 편다(`reopen_entry_section` — HOME → ①, 가용설비
  현황 → ⑤, 필요 단축 일정 카드 → ④).
- **결합 월 캔버스** — HOME 틀 그대로 라벨 Figure(260px) + 월 Figure(달마다 100px, hover)를 스크롤
  상자 하나에 둔다. 라벨 Figure 는 줄 이름 칸 풍선(구획 제목 줄 · ④ 호기 줄 · ⑤ 입력 비가동)이
  있을 때만 hover 를 켜고 아니면 `staticPlot` 이다. 월 Figure 의 칸을 누르면 `on_select` 콜백이 세션
  달을 적고 이 프래그먼트만 다시 돈다 — 프래그먼트 안 위젯이라 기본이 이 프래그먼트 회차이고,
  콜백 끝의 `rerun_app_unless_alone` 이 `rerun_fragment_if_alone` 과 같은 판정으로 프래그먼트만
  돌면 안 될 때(끊긴 전체 실행·다른 위젯도 바뀜)만 앱 전체로 올린다. 빈 선택(같은 칸 다시
  누르기·더블클릭)은 보던 달을 둔다. 그림은 세션에 몇 벌 기억한다(`remembered_canvas`, 재공
  현황 꼴) — 새 `st.cache_data` 를 두지 않는다.
- **「더 보기」 토글 둘**(④·⑤ 30줄 상한, 그 구획이 접히면 숨는다)·**설비 일정 없음 자리**(데이터
  Error 마크 또는 빈 상태 평문 — 제약 시뮬레이션과 같은 꼴). 시트 범례(띠 · 칸 색 · 표지)는 Guide
  「시트 범례」 절이다(2026-11-12 사용자 답 k-c5).
- **산출 근거 패널** — 접힌 머리 한 줄 「산출 근거 · 달 · 공정」(기억 상자 — 달 칸을 누르거나
  ◀▶ 로 달을 옮기면 펼친다, k-c5). 안은 ① 소요 ② 가용 ③ 판정·원인 ④ 단축 근거(설비 일정 공정·그
  달이 충족이 아닐 때)와 ◀▶ 달 이동, 그 달 부족 원인의 다음 화면 링크(원인별 다음 화면은 이 화면에서
  여기 하나다 — 2026-11-10 보드 c2-picked), 닫힌 「경로별 인자」(`st.dataframe` 만 — Plotly 를
  넣지 않는다).

**이벤트 칸 수는 갈래마다 같다**(AGENTS 「본문 프래그먼트」). 이 프래그먼트가 이벤트 칸에 쓰는
것은 스타일만 든 `st.html` 셋 — 두 컬럼 폭(`split_scroll_columns_style`)·라벨 칸 위 여백(표 도구
줄 내려받기 칸 서식을 함께 싣는다)·스크롤 상자(`horizontal_scroll_canvas`) — 이고 어느 갈래(펼침·
분류·설비 일정 유무·고른 달·비가동 기준)에서도 셋 그대로다. 근거 카드의 서식은 그 표시 HTML 과 한
`st.html` 에 실어 본문 칸으로 보낸다.
토스트·팝업은 없다.

**프래그먼트 회차는 직전 앱 전체 회차의 인자를 쓴다** — 오늘·판정 기준·설비 일정·표시명이
그렇다. 공정·조회기간·제품 거르기(조건 카드)는 앱 전체 회차다.

정리 줄(값 표지, 그 화면 카드에서 오지 않은 방문의 필요 단축 일정 화면 링크 —
`shortening_link_needed`), KPI 넷, 머리 공정명 옆 ◀▶(확보 기준 미달 공정 넘기기)는 달에 닿지 않아
프래그먼트 밖에서 페이지가 그린다 — 그 그리기 함수도 여기 있다.

**UPEH 가정**(조건 카드의 「이 세션만」 % — `components/upeh_assumption_controls.py`)이 켜지면
페이지가 가정 요약(`ProcessDetailView.assumed_summary`)과 가정 계획(`DynamicView`)을 넘긴다.
**판정은 한 기준이다** — 캔버스 부족 띠·KPI 미달·부족 원인·근거 패널의 ③ 판정 카드(머리 식·판정·
원인)와 다음 화면은 가정 요약으로, 가정 전 값은 ① Static 줄과 KPI 회색 줄(「가정 전 n」), ③ 카드의
회색 「가정 전: …」 한 줄에만 둔다(이름은 2026-11-12 사용자 답 q2 (가) — Core Data 숫자는
「Static」, 가정과 견주는 값은 「가정 전」). ② · ③ 의 소요대수도 가정 소요다. 그림 캐시 키에 가정
토큰이 든다. 시트 엑셀도 같은 행 모델이라 가정 세 줄 · 가정 판정 칠이 그대로 서고 파일 이름에 가정
꼬리가 붙는다. 내려받는 두 파일 이름(`detail_file_names`)은 조회 달 · 가정 꼬리 뒤 끝에 화면의 공정
이름(표시명)을 단다 — 공정마다 파일 이름이 다르다(2026-11-11 남은 물음 보드 B3).

**부족 원인의 다음 화면**(근거 패널 — 고른 달의 원인) — 보유로도 부족 → 「투자 검토 대상」 표지와
산출 결과, 가용 불일치 → 가용설비 현황 `Summary` › `Static 대비 일정`, 일정 → 필요 단축 일정 이
공정 카드 강조(`open_shortening_page` — 공정 필터를 심지 않고 강조 칸만 적는다). 화면을 옮기는
단추는 콜백이 아니라 본문에서 옮긴다(`if st.button(...)`) — 근거 패널은 프래그먼트라 콜백 안의
`st.switch_page` 가 서버 로그 경고를 남긴다(`process_detail_state.open_process_detail`).
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from typing import Final, NamedTuple

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitPageNotFoundError

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.constraint_equipment_plan import EQUIPMENT_SCREEN, absent_note
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.formula_text import APPROX, equals_mark, written_value
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    NARROW_LABEL_COLUMN_WIDTH_PX,
    NARROW_VIEWPORT_MAX_PX,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.month_sheet_canvas import signed_int
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.plotly_layout import hover_chart_config, static_chart_config
from capa_simulation.components.process_capa_canvas import (
    BASIS_SCHEDULE,
    BASIS_STATIC,
    SECTION_DOWNTIME,
    SECTION_DYNAMIC,
    SECTION_EFFECT,
    SECTION_IDS,
    SECTION_SUMMARY,
    SECTION_UNITS,
    UNITS_ALL,
    UNITS_SHORTENING,
    AssumptionCanvasInput,
    DynamicCanvasInput,
    ProcessCapaCanvas,
    build_process_capa_canvas,
    canvas_point,
    loss_text,
)
from capa_simulation.components.process_capa_workbook import (
    WorkbookRequest,
    process_capa_workbook,
)
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.sheet_download import remembered_bytes
from capa_simulation.components.shortening_board import (
    HIGHLIGHT_FROM_DETAIL,
    highlight_shortening_process,
)
from capa_simulation.components.shortening_timeline import month_day
from capa_simulation.components.status_metric import (
    MetricTone,
    metric_row,
    render_status_metric,
)
from capa_simulation.components.tab_state import remember_open_tab
from capa_simulation.components.table_toolbar import (
    SHEET_XLSX_LABEL,
    CsvFile,
    SheetFile,
    download_menu_key,
    file_name_part,
    render_download_pair,
    render_sheet_download,
    toolbar_clearance,
)
from capa_simulation.design import theme, tokens
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_SUMMARY_TAB_KEY,
    EQUIPMENT_TAB_KEY,
    REQUIRED_SHORTENING,
)
from capa_simulation.page_tabs_state import refused_at_tab_limit
from capa_simulation.process_detail_state import (
    FROM_GAP,
    FROM_HOME,
    FROM_SHORTENING,
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    PROCESS_DETAIL_EXPAND_KEY,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_NEXT_PROCESS_KEY,
    PROCESS_DETAIL_PREVIOUS_PROCESS_KEY,
    PROCESS_DETAIL_SECTIONS_KEY,
    PROCESS_DETAIL_SPLIT_KEY,
    PROCESS_DETAIL_VIEW_FRAGMENT_KEY,
    ProcessStep,
    ProcessSteps,
    step_to_process,
)
from capa_simulation.services.display_order import PreparedDisplayOrder
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import (
    CAUSE_AVAILABILITY_MISMATCH,
    DEFAULT_PRODUCT_SPLIT,
    LENT_COLUMN,
    MISMATCH_COLUMN,
    PRODUCT_DEMAND_SPLITS,
    ROUTE_COLUMNS,
    ProcessCapaKpis,
    ProcessMonthTrace,
)
from capa_simulation.services.process_equipment_timeline import (
    NO_COUNTED_UNITS,
    NO_SNAPSHOT,
    ROW_SHORTENED,
    ROW_VIRTUAL,
    DynamicReadiness,
    month_share,
    production_position,
)
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    STATUS_EXPIRED,
    STATUS_MET,
    STATUS_NEW_LIMIT,
    TargetLevel,
    single_target,
    target_for_month,
)
from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    CAUSE_OWNED_SHORT,
    CAUSE_RENTAL,
    OWNED_COLUMN,
    STATUS_COLUMN,
    surplus_held_at_zero,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import ScenarioCacheKey
from capa_simulation.services.threshold_label import (
    boundary_percent_label,
    threshold_percent_label,
)
from capa_simulation.services.upeh_assumption import (
    NO_ASSUMPTION,
    UpehToken,
    token_factor,
    token_months,
    token_percent,
)
from capa_simulation.services.wd_window import wd_window
from capa_simulation.sidebar_status import (
    remembered_box_key,
    remembered_expander,
    rerun_app_unless_alone,
)

MONTH: Final = "생산계획년월"
# 내려받는 두 파일 이름의 머리와, 공정 표시명이 파일 이름에 쓸 글자를 남기지 않을 때의 꼬리.
DETAIL_FILE_STEM: Final = "process_capa_detail"
_PROCESS_FILE_FALLBACK: Final = "process"

# ------------------------------------------------------------------ 위젯·칸 키
# ③·④ 의 30줄 상한(`ROW_LIMIT`)을 넘긴 줄을 모두 그리는 토글. 그림 캐시 키에 든다.
SHOW_ALL_UNITS_KEY: Final = "process_detail_show_all_units"
SHOW_ALL_ARROWS_KEY: Final = "process_detail_show_all_arrows"
# 근거 패널의 ◀▶ 달 이동.
PREVIOUS_MONTH_KEY: Final = "process_detail_previous_month"
NEXT_MONTH_KEY: Final = "process_detail_next_month"
# 닫힌 「경로별 인자」 상자(편 상태를 기억한다).
ROUTE_FACTORS_EXPANDER_KEY: Final = "process_detail_route_factors"
# 표 도구 줄의 내려받기 둘(호기 CSV · 시트 엑셀)은 「내려받기 ▾」 메뉴 하나다(2026-11-10 답 Q2-7 —
# 호기 CSV 가 없는 공정은 시트 엑셀 단추 하나). 줄에 선 단추(메뉴 또는 시트 엑셀)의 높이는 곁의
# 「구획」 칩과 같은 28px 이고 `table_toolbar.render_download_pair` 가 정한다(설계 규칙 UI-CON-01 ·
# 2026-11-11 남은 물음 보드 C9). 칸 서식(줄바꿈 없음)은 라벨 칸 서식 `st.html` 에 함께 싣는다
# (이벤트 칸 자리 수가 갈리지 않게).
UNITS_CSV_KEY: Final = "process_detail_units_csv"
SHEET_XLSX_KEY: Final = "process_detail_sheet_xlsx"
DOWNLOAD_MENU_KEY: Final = download_menu_key("process_detail")
# 내려받기 자리를 담는 칸 — 줄이 모자라면 칸째 다음 줄 오른쪽 끝으로 간다.
DOWNLOADS_KEY: Final = "process_detail_downloads"
# 「구획」 칩과 그 뜻 ⓘ 를 담는 칸 — ⓘ 가 칩과 작은 간격으로 붙는다(옆 토글의 풍선으로 읽히지 않게).
SECTIONS_ROW_KEY: Final = "process_detail_sections_row"
# 고르기를 줄바꿈 없는 한 칸에 담는 자리 셋 — 비가동 기준 · ④ 보기(마지막 것이 뜻 ⓘ 를 함께
# 담는다)와 분류(캡션과 한 칸). 줄이 모자라면 칸째 다음 줄로 간다(캡션 · ⓘ 만 윗줄 끝에 남지 않게 —
# 설계 규칙 UI-LAY-11).
BASIS_ROW_KEY: Final = "process_detail_basis_row"
UNITS_VIEW_ROW_KEY: Final = "process_detail_units_view_row"
SPLIT_ROW_KEY: Final = "process_detail_split_row"
_UNBROKEN_KEYS: Final = (BASIS_ROW_KEY, UNITS_VIEW_ROW_KEY, SPLIT_ROW_KEY, DOWNLOADS_KEY)
DOWNLOAD_STYLE: Final = (
    "<style>"
    + "".join(
        f".st-key-{key} {{ flex-wrap: nowrap; }}"
        f'[data-testid="stLayoutWrapper"]:has(> .st-key-{key}) '
        "{ flex-shrink: 0; min-width: max-content; }"
        for key in _UNBROKEN_KEYS
    )
    + "</style>"
)
# 「구획」 칩의 뜻 — 라벨을 숨긴 칸이라 위젯 풍선이 서지 않는다(Streamlit 1.63 은 풍선을 라벨 줄에
# 그린다). 칩 바로 뒤 빈 캡션 풍선 하나가 말한다(설계 규칙 UI-TXT-02, 2026-11-10 보드 Q-8).
SECTIONS_HELP: Final = (
    "고른 구획만 펼칩니다 — 접힌 구획은 제목 줄(▸)만 남습니다. ②~⑤ 는 설비 일정이 서는 공정에만 "
    "있습니다."
)
# 「구획」 칩이 아는 구획 id 를 적어 두는 칸(위젯 아님) — 구획이 늘어난 뒤 처음 그리는 회차에 새
# 구획을 펴 둔다(전에 연 세션에서 새 구획이 접힌 채 뜨지 않게 — 2026-11-12 시안 카드 k-c4).
SECTIONS_KNOWN_KEY: Final = "process_detail_sections_known"
# 칸이 없던 세션이 알던 구획 — ③ 비가동이 서기 전의 넷.
_SECTIONS_BEFORE_KNOWN: Final = (SECTION_SUMMARY, SECTION_DYNAMIC, SECTION_UNITS, SECTION_DOWNTIME)
# 「③ 비가동」 의 비가동 기준 고르기(`st.segmented_control`, 세션 값 — 처음은 Static). ③ 이 펼쳐진
# 공정에만 선다(④ 보기와 같은 꼴).
BASIS_KEY: Final = "process_detail_downtime_basis"
BASIS_LABELS: Final[Mapping[str, str]] = {BASIS_STATIC: "Static", BASIS_SCHEDULE: "일정"}
# 「④ 단축」 의 보기 고르기 — 전체 · 단축 필요만(`st.segmented_control`, 세션 값 — 처음은 전체,
# 2026-11-12 사용자 답 q6 (가) · 메모). ④ 가 펼쳐진 공정에만 선다.
UNITS_VIEW_KEY: Final = "process_detail_units_view"
UNITS_VIEW_LABELS: Final[Mapping[str, str]] = {UNITS_ALL: "전체", UNITS_SHORTENING: "단축 필요만"}
# 두 고르기는 보이는 캡션이 없다 — 숨긴 위젯 라벨(접근성 이름)은 뜻 있는 이름이고(설계 규칙
# UI-LAY-13), 뜻은 마지막 고르기 바로 뒤 ⓘ 하나가 말한다(`picker_help` — 2026-11-12 남은 물음 보드
# ③-2 (가), UI-TXT-02).
BASIS_LABEL: Final = "비가동 기준"
UNITS_VIEW_LABEL: Final = "④ 단축 보기"
BASIS_HELP: Final = (
    "Static · 일정 — ③ 비가동의 실가용대수를 ① Static 가용대수에서 뺄지, ② 일정 가용대수에서 "
    "뺄지 고릅니다."
)
UNITS_VIEW_HELP: Final = (
    "전체 · 단축 필요만 — ④ 단축에 호기 줄을 모두 볼지, 단축 대상과 신규 필요(추가N) 줄만 볼지 "
    "고릅니다."
)
# 시트 엑셀 머리 값 줄의 두 고르기 이름.
BASIS_HEADING: Final = "비가동 기준"
UNITS_VIEW_HEADING: Final = "④ 단축"
# 정리 줄의 필요 단축 일정 화면 링크.
SHORTENING_TAB_LINK_KEY: Final = "process_detail_open_shortening_tab"
# 부족 원인별 다음 화면 단추 — 근거 패널(그 달)이 그린다.
EVIDENCE_GAP_BUTTON_KEY: Final = "process_detail_evidence_open_gap"
EVIDENCE_SHORTENING_BUTTON_KEY: Final = "process_detail_evidence_open_shortening"
# 라벨 칸·월 칸·스크롤 상자 컨테이너 key — CSS 가 이 이름으로 폭과 여백을 못박는다.
LABEL_CANVAS_KEY: Final = "process_detail_label_canvas"
MONTH_REGION_KEY: Final = "process_detail_month_region"
SCROLL_KEY: Final = "process_detail_canvas"
SCROLLBAR_KEY: Final = "process_detail_scrollbar"
LABEL_CHART_KEY: Final = "process_detail_summary_labels"
EVIDENCE_PANEL_KEY: Final = "process_detail_evidence"
# 산출 근거 접는 상자(기억 상자 — `remembered_expander`). 달 칸을 누르면 펼친다.
EVIDENCE_BOX_KEY: Final = "process_detail_evidence_box"
DYNAMIC_ABSENT_KEY: Final = "process_detail_dynamic_absent"
KPI_ROW_KEY: Final = "process_detail_kpis"

# KPI 줄의 값 글자 크기(rem). 다른 화면의 큰 숫자보다 한 단계 작다 — 값에 글이 섞인다.
KPI_VALUE_FONT_REM: Final = 1.55
# 부족 원인 KPI 의 짧은 이름과 그 풍선.
SCHEDULE_CAUSE: Final = "일정"
CAUSE_SHORT_NAMES: Final[Mapping[str, str]] = {
    CAUSE_OWNED_SHORT: "보유",
    CAUSE_RENTAL: "대여",
    CAUSE_AVAILABILITY_MISMATCH: "불일치",
    SCHEDULE_CAUSE: "일정",
}
CAUSE_HELP: Final = (
    "달 수입니다. 보유 = 보유로도 부족(총보유 ÷ 소요도 확보 기준 미달 — 단축으로 못 메우는 투자 "
    "검토), 대여 = 대여 영향(총보유로는 확보, 대여를 빼면 미달), 불일치 = 가용 불일치(가용대수가 "
    "보유 − 대여와 다름), 일정 = 오늘이 든 생산월부터 설비 일정 기준 가용이 단축 목표 미달인 달"
    "(참고 — 단축 대상). 지난 달은 단축으로 바꿀 수 없어 세지 않습니다."
)
# 직전에 만든 캔버스 몇 벌(세션 칸). 칸을 오가며 누를 때 같은 달 그림을 다시 만들지 않는다.
CANVAS_MEMO_KEY: Final = "process_detail_canvas_memo"
CANVAS_MEMO_LIMIT: Final = 6
# 그림 모양이 바뀌면 올린다 — 같은 조건의 옛 그림이 세션에 남아 있어도 다시 만든다.
CANVAS_SCHEMA_VERSION: Final = 10
# 직전에 만든 시트 엑셀 몇 벌(세션 칸) — 조건이 같은 회차(달 칸 누름 · 다른 위젯)는 통을 다시 만들지
# 않는다. 시트 꼴이 바뀌면 버전을 올린다.
SHEET_MEMO_KEY: Final = "process_detail_sheet_memo"
SHEET_MEMO_LIMIT: Final = 4
SHEET_SCHEMA_VERSION: Final = 5

# ③ 판정 — 반올림으로만 확보인 달에서 경계식의 여유(1대 이상)를 0 으로 묶었을 때의 까닭 한 줄.
ROUNDED_IN_NOTE: Final = (
    "반올림으로 겨우 확보 — 확보율이 {threshold} 에 못 미쳐 남는 대수는 0 으로 적습니다"
)

# 「구획」 칩 글자(값은 캔버스의 구획 id). 선택지는 늘 다섯이다(2026-11-12 사용자 답 k-c4).
SECTION_LABELS: Final[Mapping[str, str]] = {
    SECTION_SUMMARY: "① Static",
    SECTION_DYNAMIC: "② 일정 가용",
    SECTION_EFFECT: "③ 비가동",
    SECTION_UNITS: "④ 단축",
    SECTION_DOWNTIME: "⑤ 비가동 일정",
}
# 밖에서 들어온 길(`from`)이 가리키는 구획 — 그 회차에 다시 편다. HOME 출처 띠는 ① 의 원
# 확보율을, 가용설비 현황 링크 글은 「비가동 일정에서 화살표로 보기」(⑤)를, 필요 단축 일정 카드는
# ④ 의 호기를 가리킨다.
ENTRY_SECTIONS: Final[Mapping[str, str]] = {
    FROM_HOME: SECTION_SUMMARY,
    FROM_GAP: SECTION_DOWNTIME,
    FROM_SHORTENING: SECTION_UNITS,
}

# 가용설비 현황(설비 일정 원천이 사는 화면)과 산출 결과.
AVAILABLE_EQUIPMENT_PAGE: Final = AVAILABLE_EQUIPMENT_STATUS.path
CALCULATION_RESULT_PAGE: Final = "app_pages/calculation_result.py"
# 보유로도 부족 원인의 표지 — 단축으로 못 메우는 투자 검토 대상이다.
INVESTMENT_BADGE: Final = ":red-badge[투자 검토 대상]"
# 시트 엑셀 머리 값 줄에 적는 단축 목표의 이름. 화면에서는 Guide 「단축 목표와 대책」 이 적는다
# (2026-11-12 사용자 메모 k-c4).
TARGET_NAME: Final = "확보 기준(월별)"
# UPEH 가정이 켜졌을 때 경로별 인자 위 표지와 풍선 — 그 표는 기준정보 UPEH 그대로다.
ROUTE_FACTORS_UPEH_MARK: Final = ":material/science: UPEH 가정 미반영 · 기준정보 UPEH"
ROUTE_FACTORS_UPEH_HELP: Final = (
    "경로별 인자는 기준정보 UPEH 그대로입니다 — UPEH 가정은 소요대수에만 사후로 "
    "겁니다(대당 Capa ×f 와 같습니다)."
)
# 설비 일정이 멈춘 알림 전문의 끝. Alarm 줄에는 표 곁이 없어 「위」 라 하지 않고 ① 로 가리킨다.
DYNAMIC_OFFICIAL_KEPT: Final = "① Static 기준은 그대로입니다."
# ②~⑤ 가 서는 조건 — 입력이 빠져 멈춘 자리 알림 전문의 끝.
DYNAMIC_ABSENT_RULE: Final = (
    "일정 가용·비가동·단축·비가동 일정(②~⑤)은 설비 DB 에 저장본이 있고 이름이 같으며 Cut-off 가 "
    f"적힌 공정에만 섭니다. {DYNAMIC_OFFICIAL_KEPT}"
)
# 입력은 다 있고 셀 호기가 없는 공정의 빈 상태 평문 줄 풍선 — 그 공정에 빠진 조건만 적는다.
NO_COUNTED_UNITS_HELP: Final = (
    "일정 가용·비가동·단축·비가동 일정(②~⑤)은 사용기준 HBM·EDP 호기나 기존보유가 있는 공정에만 "
    "섭니다."
)
# 판정은 통과했는데 설비 일정 계산이 멈춘 갈래의 알림 짧은 글(머리 배지와 같은 말).
DYNAMIC_ERROR_TITLE: Final = "설비 일정 없음: 계산 오류"
DYNAMIC_DB_ERROR_TITLE: Final = "설비 일정 없음: 설비 DB 를 읽지 못했습니다"

_MINUS: Final = "−"
_EMPTY: Final = "—"
_STATUS_NAMES: Final[Mapping[str, str]] = {"secure": "확보", "warning": "경고", "shortage": "부족"}
_SHORT_STATUSES: Final = frozenset({"warning", "shortage"})


class DetailFileNames(NamedTuple):
    """표 도구 줄 「내려받기 ▾」 의 두 파일 이름."""

    units_csv: str
    sheet: str


def detail_file_names(
    months: Sequence[int], *, process_label: str, upeh_token: UpehToken = NO_ASSUMPTION
) -> DetailFileNames:
    """「이 공정 단축 일정 CSV」 · 「시트 엑셀」 파일 이름 — 머리 · 조회 첫 달 · 끝 달 · (UPEH
    가정이 켜졌으면) 가정 꼬리 `_upeh<%>_<구간 첫 달>_<끝 달>` · 공정 이름 차례로, 두 파일이 같은
    꼴이다.

    공정 이름은 공정 값 칸 · 고르기 판과 같은 글자다 — 표시명이고(사람이 파일을 고르는 이름 —
    설계 규칙 UI-DAT-10 판단 「사람이 읽나」), 그 화면 선택지 안에서 원본이 다른 공정과 표시명이
    겹치면 「표시명 (원본)」 이다(부르는 쪽이 `ProcessLabels.unique_format_func` 로 지어 넘긴다 —
    2026-11-11 다음 배포 물음 보드 B3 뒤 (나) · 2차 보드 Q2-18). 파일 이름에 못 쓰는 글자 · 빈칸은
    `_` 로 바꾼다(`table_toolbar.file_name_part`). 2026-11-11 남은 물음 보드 B3 (가) 「두 파일
    이름 끝에 공정 이름을 붙인다」.
    """
    upeh = f"_upeh{upeh_token[0]}_{upeh_token[1][0]}_{upeh_token[1][-1]}" if upeh_token else ""
    tail = f"{months[0]}_{months[-1]}{upeh}_" + file_name_part(
        process_label, fallback=_PROCESS_FILE_FALLBACK
    )
    return DetailFileNames(
        units_csv=f"{DETAIL_FILE_STEM}_units_{tail}.csv",
        sheet=f"{DETAIL_FILE_STEM}_{tail}.xlsx",
    )


# ================================================================== 넘겨받는 묶음


@dataclass(frozen=True, eq=False)
class DynamicView:
    """설비 일정(②~④)이 설 때 패널·KPI 가 함께 읽는 것. 캔버스 재료는 `canvas` 다."""

    canvas: DynamicCanvasInput
    units: pd.DataFrame
    """`plan.at(목표).units` 를 이 공정으로 거른 것(단축·추가N)."""

    memo_key: tuple[object, ...]
    """그림 캐시 키에 넣는 설비 일정 입력 — 계획 키(오늘·목표·UPEH 가정 토큰 포함)와 설비 일정 키,
    일정 미정 글."""

    official_units: pd.DataFrame | None = None
    """UPEH 가정 계획을 그릴 때 — 같은 공정의 **가정 전** 계획 호기 표(KPI 회색 줄 「가정 전 n」).
    공식 계획을 그릴 때는 None 이다(`units` 가 곧 공식이다)."""

    official_process_months: pd.DataFrame | None = None
    """위와 같은 때의 공식 계획 공정·월 표."""


@dataclass(frozen=True, eq=False)
class ProcessDetailView:
    """프래그먼트 인자 — 앱 전체 회차가 정한 공정·축·요약·설비 일정.

    표들은 키 전용 캐시 래퍼(`get_process_product_demand`·`get_process_month_trace`)에 `_` 인자로만
    넘긴다. 키는 `scenario_key`(시나리오 내용·기간)·`display_order_key` 다.
    """

    process: str
    process_label: str
    months: tuple[int, ...]
    summary: pd.DataFrame
    thresholds: SecurementThresholds
    scenario_key: ScenarioCacheKey
    display_order_key: str
    scenario_tables: Mapping[str, pd.DataFrame]
    reference_tables: Mapping[str, pd.DataFrame]
    display_order: PreparedDisplayOrder | None
    products: tuple[str, ...] = ()
    """조건 카드의 제품 거르기(펼친 행에만 걸린다). 비면 거르지 않는다."""

    splits: tuple[str, ...] = tuple(PRODUCT_DEMAND_SPLITS)
    """「분류」 선택지. 공정 안에서 늘 한 값인 분류(소요기준)는 페이지가 뺀다."""

    home_rates: Mapping[int, float | None] | None = None
    dynamic: DynamicView | None = None
    readiness: DynamicReadiness | None = None
    """설비 일정 판정. None 이면 설비 DB 를 읽지 못한 것이다(`dynamic_error`)."""

    dynamic_error: str = ""
    assumed_summary: pd.DataFrame | None = None
    """UPEH 가정이 켜졌을 때의 가정 요약(소요 ÷f 를 건 확보율로 `build_process_capa_summary`). 판정
    기준이다."""

    upeh_token: UpehToken = NO_ASSUMPTION
    """UPEH 가정 토큰(`upeh_assumption.UpehToken`) — 그림 캐시 키에 든다. 꺼졌으면 `()`."""

    initial_month: int | None = None
    """스크롤 시작 달(`ProcessDetailEntry.scroll_month`) — 새 방문·밖에서 들어옴·공정을 바꾼
    회차에만 바뀐다. 스크롤바는 이 값이 바뀔 때만 오프셋을 다시 걸므로, 칸을 눌러 달을 옮긴 뒤의
    앱 전체 회차가 보던 가로 위치를 되돌리지 않는다."""

    units_csv: bytes | None = None
    """표 도구 줄 「이 공정 단축 일정 CSV」 의 바이트. 설비 일정이 서지 않으면 None(단추 없음)."""

    units_csv_file_name: str = ""
    """그 파일 이름(`detail_file_names` — 가정 계획이면 UPEH 가정 꼬리, 끝에 공정 이름)."""

    shortening_link_help: str | None = None
    """필요 단축 일정으로 옮기는 단추의 풍선(`render_closing_row` 의 `link_help` 와 같은 글)."""

    units_export: pd.DataFrame | None = None
    """「이 공정 단축 일정 CSV」 와 같은 표 — 시트 엑셀의 둘째 시트. 설비 일정이 서지 않으면
    None."""

    sheet_heading: tuple[tuple[str, str], ...] = ()
    """시트 엑셀 맨 위 (이름, 값) 줄 — 공정 · 시나리오 · 조회기간 · 설비 시나리오처럼 페이지가 아는
    머리 값. 구획 · 펼침 · 단축 목표는 프래그먼트가 덧붙인다."""

    sheet_file_name: str = "process_capa_detail.xlsx"
    """시트 엑셀 파일 이름(`detail_file_names` — 가정 계획이면 UPEH 가정 꼬리, 끝에 공정 이름)."""

    @property
    def judgement_summary(self) -> pd.DataFrame:
        """판정·부족 원인을 읽는 요약 — UPEH 가정이 켜졌으면 가정 요약, 아니면 공식 요약."""
        return self.assumed_summary if self.assumed_summary is not None else self.summary


# ================================================================== 프래그먼트


@st.fragment(key=PROCESS_DETAIL_VIEW_FRAGMENT_KEY)
def render_process_detail_view(view: ProcessDetailView) -> None:
    """표 도구 줄 → 결합 캔버스 → 더 보기 → (설비 일정 없음 카드) → 산출 근거 패널."""
    month = viewed_month(view.months)
    expanded, split, collapsed, sheet_slot = _render_tool_row(view)
    basis = current_basis()
    units_view = current_units_view()
    product_demand = (
        simulation_cache.get_process_product_demand(
            view.scenario_key,
            view.display_order_key,
            view.process,
            split,
            view.months,
            _scenario_tables=view.scenario_tables,
            _reference_tables=view.reference_tables,
            _display_order=view.display_order,
            products=view.products,
        )
        if expanded
        else None
    )
    show_all_units = bool(st.session_state.get(SHOW_ALL_UNITS_KEY, False))
    show_all_arrows = bool(st.session_state.get(SHOW_ALL_ARROWS_KEY, False))
    render_sheet_download(
        sheet_slot,
        SheetFile(
            data=remembered_sheet(
                sheet_memo_key(
                    view,
                    expanded=expanded,
                    split=split,
                    show_all_units=show_all_units,
                    show_all_arrows=show_all_arrows,
                    collapsed=collapsed,
                    basis=basis,
                    units_view=units_view,
                ),
                partial(
                    process_capa_workbook,
                    sheet_request(
                        view,
                        expanded=expanded,
                        split=split,
                        collapsed=collapsed,
                        product_demand=product_demand,
                        show_all_units=show_all_units,
                        show_all_arrows=show_all_arrows,
                        basis=basis,
                        units_view=units_view,
                    ),
                ),
            ),
            file_name=view.sheet_file_name,
            key=SHEET_XLSX_KEY,
            label=SHEET_XLSX_LABEL,
        ),
    )
    canvas = remembered_canvas(
        view,
        month=month,
        expanded=expanded,
        split=split,
        product_demand=product_demand,
        show_all_units=show_all_units,
        show_all_arrows=show_all_arrows,
        collapsed=collapsed,
        basis=basis,
        units_view=units_view,
    )
    _render_canvas(view, canvas)
    _render_more_toggles(
        canvas,
        show_all_units=show_all_units,
        show_all_arrows=show_all_arrows,
        collapsed=collapsed,
    )
    # 시트 범례는 Guide 「시트 범례」 절이다(2026-11-12 사용자 답 k-c5) — 시트 아래에 서지 않는다.
    if view.dynamic is None:
        _render_dynamic_absent(view)
    _render_evidence_panel(view, month)


def viewed_month(months: Sequence[int]) -> int:
    """지금 보는 달 — 세션 달이 축 안이면 그 달, 아니면 첫 달(그 값을 세션에 적는다)."""
    saved = st.session_state.get(PROCESS_DETAIL_MONTH_KEY)
    if isinstance(saved, int) and saved in months:
        return saved
    st.session_state[PROCESS_DETAIL_MONTH_KEY] = int(months[0])
    return int(months[0])


def _render_tool_row(
    view: ProcessDetailView,
) -> tuple[bool, str, frozenset[str], DeltaGenerator]:
    """「구획」 칩 · 그 뜻 ⓘ · 「Static · 일정」 비가동 기준 고르기(설비 일정이 서는 공정에서 ③ 을
    펼쳤을 때만) · 「전체 · 단축 필요만」 ④ 보기 고르기(호기 줄이 있는 공정에서 ④ 를 펼쳤을 때만) ·
    그 두 고르기의 뜻 ⓘ 하나(선 것 가운데 마지막 고르기 바로 뒤) · 「제품별 소요대수」 펼침 ·
    「분류」(펼쳤을 때) · 오른쪽 끝 「내려받기 ▾」 메뉴(호기 CSV — 설비 일정이 설 때만, 시트 엑셀 —
    늘. 호기 CSV 가 없으면 메뉴 없이 시트 엑셀 단추 하나). 고르기 셋은 저마다 줄바꿈 없는 칸이라
    (ⓘ · 「분류」 캡션과 함께) 줄이 모자라면 칸째 다음 줄로 간다(`_picker_pair`). 두 고르기는 구획을
    접어 서지 않는 회차에도 세션 값을 그대로 쓴다(`current_basis` · `current_units_view`).

    돌려주는 것은 (제품 행을 그릴지, 분류, 접힌 구획, 시트 엑셀 자리) 다. 「제품별 소요대수」 는 ① ·
    ② 를 함께 펼친다(2026-11-12 사용자 답 q4 (가)) — 둘 다 접혔으면(설비 일정이 없으면 ① 만 보고)
    제품 행을 그리지 않는다. 시트 엑셀 단추는 제품 행 표를 받은 뒤 그 자리에 채운다
    (`render_process_detail_view`). 내려받기를 안쪽 칸에 두는 것은 `st.space("stretch")` 를 쓰면
    틈이 한 번 더 들어 기준 창에서 줄이 넘어가기 때문이다.
    """
    options = list(view.splits) or [DEFAULT_PRODUCT_SPLIT]
    seed_sections()
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.caption("구획", width="content")
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            gap="small",
            width="content",
            key=SECTIONS_ROW_KEY,
        ):
            opened = st.pills(
                "구획",
                list(SECTION_IDS),
                selection_mode="multi",
                format_func=lambda section: SECTION_LABELS.get(str(section), str(section)),
                key=PROCESS_DETAIL_SECTIONS_KEY,
                persist_state="session",
                label_visibility="collapsed",
            )
            st.caption("", help=SECTIONS_HELP, width="content")
        collapsed = frozenset(SECTION_IDS) - {str(section) for section in opened or ()}
        show_basis = view.dynamic is not None and SECTION_EFFECT not in collapsed
        show_units = (
            view.dynamic is not None
            and view.dynamic.canvas.has_units
            and SECTION_UNITS not in collapsed
        )
        if show_basis:
            seed_basis()
            with _picker_pair(BASIS_ROW_KEY):
                st.segmented_control(
                    BASIS_LABEL,
                    list(BASIS_LABELS),
                    format_func=lambda value: BASIS_LABELS.get(str(value), str(value)),
                    key=BASIS_KEY,
                    required=True,
                    persist_state="session",
                    label_visibility="collapsed",
                )
                if not show_units:
                    st.caption("", help=picker_help(basis=True, units=False), width="content")
        if show_units:
            seed_units_view()
            with _picker_pair(UNITS_VIEW_ROW_KEY):
                st.segmented_control(
                    UNITS_VIEW_LABEL,
                    list(UNITS_VIEW_LABELS),
                    format_func=lambda value: UNITS_VIEW_LABELS.get(str(value), str(value)),
                    key=UNITS_VIEW_KEY,
                    required=True,
                    persist_state="session",
                    label_visibility="collapsed",
                )
                st.caption("", help=picker_help(basis=show_basis, units=True), width="content")
        products_open = SECTION_SUMMARY not in collapsed or (
            view.dynamic is not None and SECTION_DYNAMIC not in collapsed
        )
        expanded = st.toggle(
            "제품별 소요대수",
            key=PROCESS_DETAIL_EXPAND_KEY,
            persist_state="session",
            disabled=not products_open,
            help=(
                "켜면 ① · ② 소요대수 아래에 분류별 행이 펼쳐집니다. 사이드바 제품 거르기는 이 "
                "행에만 걸립니다. ① · ② 가 모두 접혀 있으면 쓰지 않습니다."
            ),
        )
        split = DEFAULT_PRODUCT_SPLIT
        if expanded and products_open:
            # 선택지에 없는 값(공정이 바뀌어 빠진 「소요기준」 등)은 지우지 않고 기본값을 적는다.
            if st.session_state.get(PROCESS_DETAIL_SPLIT_KEY) not in options:
                st.session_state[PROCESS_DETAIL_SPLIT_KEY] = (
                    DEFAULT_PRODUCT_SPLIT if DEFAULT_PRODUCT_SPLIT in options else options[0]
                )
            with _picker_pair(SPLIT_ROW_KEY):
                st.caption("분류", width="content")
                chosen = st.segmented_control(
                    "분류",
                    options,
                    key=PROCESS_DETAIL_SPLIT_KEY,
                    persist_state="session",
                    label_visibility="collapsed",
                )
            split = str(chosen) if chosen in options else options[0]
        with st.container(horizontal=True, horizontal_alignment="right", key=DOWNLOADS_KEY):
            # 「내려받기 ▾」 — 호기 CSV(설비 일정이 설 때만)와 시트 엑셀 자리. 엑셀은 제품 행 표를
            # 받은 뒤 채운다.
            sheet_slot = render_download_pair(
                csv=(
                    CsvFile(
                        data=view.units_csv,
                        file_name=view.units_csv_file_name,
                        key=UNITS_CSV_KEY,
                        label="이 공정 단축 일정 CSV",
                    )
                    if view.units_csv is not None
                    else None
                ),
                menu_key=DOWNLOAD_MENU_KEY,
            )
    return bool(expanded) and products_open, split, collapsed, sheet_slot


def picker_help(*, basis: bool, units: bool) -> str:
    """표 도구 줄 두 고르기(비가동 기준 · ④ 보기)의 뜻 ⓘ 풍선 — 선 고르기의 뜻만 차례로 적는다."""
    return "\n\n".join(
        text for text, shown in ((BASIS_HELP, basis), (UNITS_VIEW_HELP, units)) if shown
    )


def _picker_pair(key: str) -> DeltaGenerator:
    """표 도구 줄의 고르기 하나와 그 곁 글(캡션 · ⓘ)을 담는 칸 — 줄이 모자라면 칸째 다음 줄로
    간다(칸 서식은 `DOWNLOAD_STYLE`)."""
    return st.container(
        horizontal=True, vertical_alignment="center", gap="small", width="content", key=key
    )


def seed_basis() -> None:
    """「비가동 기준」 값을 위젯 앞에서 다진다 — 칸이 없거나 모르는 값이면 처음 값(Static)을
    **적는다**(지우지 않는다 — AGENTS 9장)."""
    if st.session_state.get(BASIS_KEY) not in BASIS_LABELS:
        st.session_state[BASIS_KEY] = BASIS_STATIC


def current_basis() -> str:
    """지금 「③ 비가동」 의 비가동 기준 — 세션 값이 모르는 값이면 처음 값(Static). 고르기가 서지
    않은 회차(③ 접힘)에도 세션 값을 그대로 쓴다 — 다시 펴면 고른 기준이다."""
    value = st.session_state.get(BASIS_KEY)
    return str(value) if value in BASIS_LABELS else BASIS_STATIC


def seed_units_view() -> None:
    """「④ 단축」 보기 값을 위젯 앞에서 다진다 — 칸이 없거나 모르는 값이면 처음 값(전체)을
    **적는다**(지우지 않는다 — AGENTS 9장)."""
    if st.session_state.get(UNITS_VIEW_KEY) not in UNITS_VIEW_LABELS:
        st.session_state[UNITS_VIEW_KEY] = UNITS_ALL


def current_units_view() -> str:
    """지금 「④ 단축」 의 보기 — 세션 값이 모르는 값이면 처음 값(전체). 고르기가 서지 않은 회차(④
    접힘)에도 세션 값을 그대로 쓴다 — 다시 펴면 보던 보기다."""
    value = st.session_state.get(UNITS_VIEW_KEY)
    return str(value) if value in UNITS_VIEW_LABELS else UNITS_ALL


def sheet_request(
    view: ProcessDetailView,
    *,
    expanded: bool,
    split: str,
    collapsed: frozenset[str],
    product_demand: pd.DataFrame | None,
    show_all_units: bool,
    show_all_arrows: bool,
    basis: str = BASIS_STATIC,
    units_view: str = UNITS_ALL,
) -> WorkbookRequest:
    """시트 엑셀 재료 — 이 회차의 화면 상태 그대로(켜진 구획 · 펼친 제품 행과 분류 · 조회기간의 달 ·
    UPEH 가정 · HOME 표시 확보율 · 「더 보기」 · 비가동 기준 · ④ 보기). 머리 값은 페이지 값 뒤에
    구획 · 펼침 · 두 고르기 · 단축 목표를 덧붙인다 — 「구획」 은 시트에 실제로 선 구획만이고(설비
    일정이 서지 않으면 ② ~ ⑤ 칩이 켜져 있어도 ① 뿐), 「비가동 기준」 · 「④ 단축」 은 그 구획이
    시트에 펼쳐 섰을 때만이다. 그림 캔버스와 같은 인자로 같은 행 모델을 세운다
    (`remembered_canvas`)."""
    heading = list(view.sheet_heading)
    drawn = _drawn_sections(view)
    opened = [SECTION_LABELS[section] for section in drawn if section not in collapsed]
    heading.append(("구획", " · ".join(opened) if opened else "모두 접힘"))
    if expanded:
        filtered = f" · 제품 거르기 {len(view.products)}개" if view.products else ""
        heading.append(("제품별 소요대수", f"펼침 · 분류 {split}{filtered}"))
    if SECTION_EFFECT in _opened_ids(drawn, collapsed):
        heading.append((BASIS_HEADING, BASIS_LABELS.get(basis, basis)))
    if SECTION_UNITS in _opened_ids(drawn, collapsed):
        heading.append((UNITS_VIEW_HEADING, UNITS_VIEW_LABELS.get(units_view, units_view)))
    if view.dynamic is not None:
        heading.append(("단축 목표", target_text(view.dynamic.canvas.target, view.months)))
    dynamic = (
        replace(
            view.dynamic.canvas,
            show_all_units=show_all_units,
            show_all_arrows=show_all_arrows,
            downtime_basis=basis,
            units_view=units_view,
        )
        if view.dynamic is not None
        else None
    )
    return WorkbookRequest(
        heading=tuple(heading),
        process_label=view.process_label,
        months=view.months,
        summary=view.summary,
        thresholds=view.thresholds,
        product_demand=product_demand if expanded else None,
        home_rates=view.home_rates,
        dynamic=dynamic,
        collapsed=frozenset(collapsed),
        assumption=(
            AssumptionCanvasInput(
                percent=token_percent(view.upeh_token),
                months=token_months(view.upeh_token),
                summary=view.assumed_summary,
            )
            if view.upeh_token and view.assumed_summary is not None
            else None
        ),
        units_export=view.units_export if view.dynamic is not None else None,
    )


def _drawn_sections(view: ProcessDetailView) -> tuple[str, ...]:
    """시트에 서는 구획 — 설비 일정이 없으면 ① 뿐, 호기 줄이 없는 공정(기존보유만)은 ① ~ ③."""
    if view.dynamic is None:
        return (SECTION_SUMMARY,)
    if not view.dynamic.canvas.has_units:
        return (SECTION_SUMMARY, SECTION_DYNAMIC, SECTION_EFFECT)
    return SECTION_IDS


def _opened_ids(drawn: Sequence[str], collapsed: Collection[str]) -> tuple[str, ...]:
    """선 구획 가운데 펼친 것(차례 그대로)."""
    return tuple(section for section in drawn if section not in collapsed)


def seed_sections() -> None:
    """「구획」 칩 값을 위젯 앞에서 다진다 — 칸이 없으면 다섯 모두(기본 모두 펼침), 모르는 값이
    섞였으면 아는 값만 남긴 새 목록을 **적는다**(지우지 않는다 — AGENTS 9장).

    세션이 알던 구획(`SECTIONS_KNOWN_KEY`, 칸이 없으면 ③ 비가동이 서기 전의 넷)에 없던 구획은 한 번
    펴 둔다 — 전에 연 세션에서 새 구획이 접힌 채 뜨지 않게. 그 뒤로는 접고 펴는 대로다.
    """
    saved = st.session_state.get(PROCESS_DETAIL_SECTIONS_KEY)
    seen = st.session_state.get(SECTIONS_KNOWN_KEY)
    st.session_state[SECTIONS_KNOWN_KEY] = tuple(SECTION_IDS)
    if not isinstance(saved, (list, tuple)):
        st.session_state[PROCESS_DETAIL_SECTIONS_KEY] = list(SECTION_IDS)
        return
    before = set(seen) if isinstance(seen, tuple) else set(_SECTIONS_BEFORE_KNOWN)
    opened = {str(item) for item in saved} | (set(SECTION_IDS) - before)
    known = [section for section in SECTION_IDS if section in opened]
    if known != list(saved):
        st.session_state[PROCESS_DETAIL_SECTIONS_KEY] = known


def reopen_entry_section(source: str | None) -> None:
    """밖에서 들어온 회차에 그 길이 가리키는 구획을 다시 편다(다른 구획의 접힘은 둔다).

    페이지가 공정·달을 정한 뒤, 본문 프래그먼트(칩 위젯)보다 앞에서 부른다. 길이 없거나 구획을
    가리키지 않으면(`from` 없는 주소) 아무것도 않는다.
    """
    section = ENTRY_SECTIONS.get(source or "")
    if section is None:
        return
    saved = st.session_state.get(PROCESS_DETAIL_SECTIONS_KEY)
    if not isinstance(saved, (list, tuple)):
        # 칸이 없으면 칩 앞의 `seed_sections` 가 다섯 모두로 심는다 — 이미 펼침이다.
        return
    opened = {str(item) for item in saved}
    if section in opened:
        return
    opened.add(section)
    st.session_state[PROCESS_DETAIL_SECTIONS_KEY] = [item for item in SECTION_IDS if item in opened]


def target_text(target: TargetLevel, months: Sequence[int]) -> str:
    """단축 목표 표기 — 「확보 기준(월별)」, 모든 달이 같으면 그 값도. 시트 엑셀 머리 값 줄이 쓴다 —
    화면에서는 Guide 가 적는다(2026-11-12 사용자 메모 k-c4)."""
    value = single_target(target, months)
    if value is not None:
        return f"{TARGET_NAME} {target_label(value)}"
    return TARGET_NAME


def target_label(value: float) -> str:
    """목표 하나 — 정수 기준 「110%」(2026-11-01 사용자 결정 — 기준은 정수만 적는다).

    목표 값은 HOME 확보 기준의 판정 경계(`target_from_thresholds` — 110% 면 1.095)라 사사오입한
    정수가 곧 그 기준이다. 식 줄은 곱한 값을 판정 경계로 적는다(`boundary_percent_label`).
    """
    return threshold_percent_label(value)


def _ratio_percent(value: float) -> str:
    """식 줄에 곱한 목표 비율을 퍼센트로(1.095 → 「109.5%」) — 곱한 값 그대로라 검산된다."""
    return f"{round(float(value) * 100, 6):g}%"


# ================================================================== 캔버스


def canvas_memo_key(
    view: ProcessDetailView,
    *,
    month: int,
    expanded: bool,
    split: str,
    show_all_units: bool,
    show_all_arrows: bool,
    collapsed: Collection[str] = (),
    basis: str = BASIS_STATIC,
    units_view: str = UNITS_ALL,
) -> tuple[object, ...]:
    """그림을 바꾸는 조건 전부. 지금 보는 달·오늘(설비 일정 키 안)·목표·접힌 구획·UPEH 가정 토큰·
    비가동 기준 · ④ 보기가 그림에 구워지므로 든다(가정 요약은 그 토큰과 시나리오 키·판정 기준이
    정한다)."""
    home = tuple(sorted(view.home_rates.items())) if view.home_rates is not None else None
    return (
        CANVAS_SCHEMA_VERSION,
        theme.current_mode(),
        view.scenario_key,
        view.display_order_key,
        view.months,
        view.process,
        view.process_label,
        view.thresholds.digest,
        bool(expanded),
        split if expanded else "",
        view.products if expanded else (),
        int(month),
        home,
        view.dynamic.memo_key if view.dynamic is not None else None,
        bool(show_all_units),
        bool(show_all_arrows),
        tuple(sorted(str(section) for section in collapsed)),
        view.upeh_token,
        str(basis),
        str(units_view),
    )


def remembered_canvas(
    view: ProcessDetailView,
    *,
    month: int,
    expanded: bool,
    split: str,
    product_demand: pd.DataFrame | None,
    show_all_units: bool,
    show_all_arrows: bool,
    collapsed: Collection[str] = (),
    basis: str = BASIS_STATIC,
    units_view: str = UNITS_ALL,
) -> ProcessCapaCanvas:
    """결합 캔버스를 세션에 몇 벌 기억한다(`CANVAS_MEMO_LIMIT`). 꺼낸 그림은 고치지 않는다.

    키(`canvas_memo_key`)는 그림을 바꾸는 조건 전부다 — 테마·시나리오 키·표시순서
    지문·축·공정·표시명· 판정 기준 지문·펼침/분류/거르기·지금 보는 달·HOME 표시 확보율·설비 일정
    키(오늘·목표·네 표 지문)· 더 보기 둘·접힌 구획·비가동 기준·④ 보기·그림 모양 버전. 만들다
    실패하면 기억하지 않는다.
    """
    key = canvas_memo_key(
        view,
        month=month,
        expanded=expanded,
        split=split,
        show_all_units=show_all_units,
        show_all_arrows=show_all_arrows,
        collapsed=collapsed,
        basis=basis,
        units_view=units_view,
    )
    memo = st.session_state.get(CANVAS_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], ProcessCapaCanvas]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key and isinstance(stored, ProcessCapaCanvas):
            return stored
    dynamic = (
        replace(
            view.dynamic.canvas,
            show_all_units=show_all_units,
            show_all_arrows=show_all_arrows,
            downtime_basis=basis,
            units_view=units_view,
        )
        if view.dynamic is not None
        else None
    )
    canvas = build_process_capa_canvas(
        process_label=view.process_label,
        months=view.months,
        summary=view.summary,
        thresholds=view.thresholds,
        selected_month=month,
        product_demand=product_demand,
        home_rates=view.home_rates,
        dynamic=dynamic,
        collapsed=frozenset(collapsed),
        assumption=(
            AssumptionCanvasInput(
                percent=token_percent(view.upeh_token),
                months=token_months(view.upeh_token),
                summary=view.assumed_summary,
            )
            if view.upeh_token and view.assumed_summary is not None
            else None
        ),
    )
    entries = [entry for entry in entries if entry[0] != key][-(CANVAS_MEMO_LIMIT - 1) :]
    st.session_state[CANVAS_MEMO_KEY] = [*entries, (key, canvas)]
    return canvas


def sheet_memo_key(
    view: ProcessDetailView,
    *,
    expanded: bool,
    split: str,
    show_all_units: bool,
    show_all_arrows: bool,
    collapsed: Collection[str] = (),
    basis: str = BASIS_STATIC,
    units_view: str = UNITS_ALL,
) -> tuple[object, ...]:
    """시트 엑셀을 바꾸는 조건 전부 — 그림 기억 키(`canvas_memo_key`)에서 지금 보는 달 · 테마를 뺀
    것(시트는 고른 달 표지가 없고 늘 밝은 색이다)에 머리 값 줄 · 시트 꼴 버전을 더한다. 둘째
    시트(호기 표)는 설비 일정 키(계획 키 — 오늘 · 목표 · UPEH 가정 토큰)가 정한다."""
    home = tuple(sorted(view.home_rates.items())) if view.home_rates is not None else None
    return (
        SHEET_SCHEMA_VERSION,
        view.scenario_key,
        view.display_order_key,
        view.months,
        view.process,
        view.process_label,
        view.thresholds.digest,
        bool(expanded),
        split if expanded else "",
        view.products if expanded else (),
        home,
        view.dynamic.memo_key if view.dynamic is not None else None,
        bool(show_all_units),
        bool(show_all_arrows),
        tuple(sorted(str(section) for section in collapsed)),
        view.upeh_token,
        view.sheet_heading,
        str(basis),
        str(units_view),
    )


def remembered_sheet(key: tuple[object, ...], build: Callable[[], bytes]) -> bytes:
    """시트 엑셀 바이트를 세션에 몇 벌 기억한다(`SHEET_MEMO_LIMIT`) — 같은 조건이면 다시 만들지
    않는다. 빗나간 회차는 이 자리에서 바로 만들어 오류가 화면에 드러난다(만들다 실패하면 기억하지
    않는다). 기억하는 길은 산출 결과 시트 엑셀과 같은 `sheet_download.remembered_bytes` 다."""
    return remembered_bytes(SHEET_MEMO_KEY, key, build, limit=SHEET_MEMO_LIMIT)


def pick_canvas_month(months: Sequence[int]) -> None:
    """월 그림의 칸 선택 콜백 — 누른 칸의 달을 세션에 적는다. 이 프래그먼트 회차로 다시 그린다.

    빈 선택과 축 밖의 점은 달을 바꾸지 않는다 — 보던 달 그대로다. ④·⑤ 줄을 눌러도 그 열의 달이다
    (표적 막대가 그 줄까지 덮는다). 콜백이 오면 어느 경우든 접힌 산출 근거를 펼친다(2026-11-12
    사용자 답 k-c5). 다만 이미 골라 둔 칸을 다시 누르면 그림이 선택 사건을 보내지 않아(Streamlit
    1.63 — 사본 앱 브라우저 확인) 이 콜백이 돌지 않는다 — 접은 뒤 같은 달 칸을 다시 누르면
    펼쳐지지 않는 것은 시안 카드가 적은 「잃는 것」 그대로다(다른 달 칸 · 머리 누름은 펼친다).
    """
    point = canvas_point(st.session_state.get(PROCESS_DETAIL_CANVAS_CHART_KEY))
    if point is not None and point[0] in set(int(month) for month in months):
        st.session_state[PROCESS_DETAIL_MONTH_KEY] = int(point[0])
    open_evidence()
    rerun_app_unless_alone(PROCESS_DETAIL_CANVAS_CHART_KEY)


def open_evidence() -> None:
    """산출 근거 접는 상자를 편다 — 콜백에서 부른다(위젯 값 · 기억 칸을 함께 적는다. 기억 칸의
    라벨을 비워 두면 `remembered_expander` 가 다음 회차에 그 펼침을 위젯 값으로 다시 적는다)."""
    st.session_state[EVIDENCE_BOX_KEY] = True
    st.session_state[remembered_box_key(EVIDENCE_BOX_KEY)] = (True, "")


def _render_canvas(view: ProcessDetailView, canvas: ProcessCapaCanvas) -> None:
    """HOME 틀 — 라벨 칸 260px(px 로 못박음 — 좁은 창은 150px) + 월 칸(스크롤 상자 하나, 위에 가로
    스크롤바)."""
    count = len(view.months)
    visible = min(max(count, 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)
    st.html(
        split_scroll_columns_style(
            label_key=LABEL_CANVAS_KEY,
            month_key=MONTH_REGION_KEY,
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
            narrow_label_width_px=NARROW_LABEL_COLUMN_WIDTH_PX,
            narrow_viewport_max_px=NARROW_VIEWPORT_MAX_PX,
        )
    )
    label_column, month_column = st.columns(
        [DASHBOARD_LABEL_COLUMN_WIDTH_PX, visible * tokens.MONTH_COLUMN_WIDTH_PX], gap=None
    )
    with label_column:
        with st.container(key=LABEL_CANVAS_KEY, gap=None):
            # 라벨 Figure 의 trace 는 줄 이름 칸 풍선(구획 제목 줄·④ 호기 줄·⑤ 입력 비가동)의
            # 표적뿐이다 — 있을 때만 hover 를 켠다.
            st.plotly_chart(
                canvas.labels,
                width="stretch",
                key=LABEL_CHART_KEY,
                config=hover_chart_config() if canvas.labels.data else static_chart_config(),
            )
    with month_column:
        # 서식은 이 한 `st.html` 에 둔다(이벤트 칸 수는 갈래마다 같다) — 표 도구 줄 내려받기 칸
        # 서식도 여기 싣는다(보이는 글이 없는 서식 `st.html` 은 이벤트 칸을 쓴다).
        st.html(label_overflow_style() + DOWNLOAD_STYLE)
        with st.container(key=MONTH_REGION_KEY, gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{SCROLL_KEY}_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key=SCROLLBAR_KEY,
                initial_offset_px=initial_scroll_px(view.months, view.initial_month),
            )
            with horizontal_scroll_canvas(
                key=SCROLL_KEY,
                content_width_px=count * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=None,
            ):
                # hover 로 칸 풍선을 읽고, 칸을 누르면 그 달이 아래 근거 패널의 달이 된다 — 선택은
                # 점 하나(`points`)다. 선택을 켜면 그림 위 터치 스크롤이 막히므로 이 key 는 `app.py`
                # 의 터치 스크롤 막이 묶음에 들어 있다.
                st.plotly_chart(
                    canvas.months,
                    width="stretch",
                    key=PROCESS_DETAIL_CANVAS_CHART_KEY,
                    config=hover_chart_config(),
                    on_select=partial(pick_canvas_month, view.months),
                    selection_mode="points",
                )


def label_overflow_style() -> str:
    """라벨 칸의 높이 맞춤과 줄 이름 칸 풍선이 넘치게 하는 `<style>`.

    라벨 칸은 월 칸 위에 얹힌 스크롤바 높이만큼 내려야 행이 맞는다(HOME 과 같은 값). 줄 이름 칸
    풍선은 260px 그림보다 넓을 수 있어(세 줄 ≈ 230~290px) 그림 둘레의 `overflow` 를 풀고 라벨
    컬럼을 월 컬럼 위로 올린다 — 안 풀면 넘친 몫이 잘린다(2026-10-24 브라우저).

    풀어 두는 것은 풍선을 담은 마지막 SVG(Plotly 의 `_hoverpaper` — 그림·글 SVG 뒤에 붙는다) 하나다.
    그림·글 SVG 는 **어느 창 폭에서나** 칸 안으로 자른다 — 풀어 두면 라벨 그림의 테와 흰 바탕이 칸
    밖으로 새어 구분 칸이 월 칸 위에 떠 보이고(두 배 굵기 테 · 흰 둘레 — 2026-11-12 사용자 답
    k-b3), 좁은 창(`NARROW_VIEWPORT_MAX_PX` 이하 — 라벨 칸이 `NARROW_LABEL_COLUMN_WIDTH_PX` 로
    준다)에서는 260px 에 맞춘 줄 이름이 월 칸 위에 겹친다(E2E r1 #20 — 개선 거리 I12).
    """
    chart = f".st-key-{LABEL_CHART_KEY}"
    return (
        f"<style>.st-key-{LABEL_CANVAS_KEY} {{ padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px; }}"
        f'[data-testid="stColumn"]:has(.st-key-{LABEL_CANVAS_KEY}) '
        "{ position: relative; z-index: 2; }"
        f"{chart}, {chart} .js-plotly-plot, {chart} .plot-container, {chart} .svg-container, "
        f"{chart} .main-svg {{ overflow: visible !important; }}"
        f"{chart} svg.main-svg:not(:last-of-type) {{ overflow: hidden !important; }}"
        "</style>"
    )


def initial_scroll_px(months: Sequence[int], month: int | None) -> float:
    """화면을 연 달이 왼쪽에서 둘째 칸쯤 서게 하는 시작 위치(px). 첫 두 달이면 0."""
    if month is None or month not in months:
        return 0.0
    return float(max(0, list(months).index(month) - 1) * tokens.MONTH_COLUMN_WIDTH_PX)


def _render_more_toggles(
    canvas: ProcessCapaCanvas,
    *,
    show_all_units: bool,
    show_all_arrows: bool,
    collapsed: Collection[str] = (),
) -> None:
    """30줄 상한을 넘긴 ③·④ 를 모두 그리는 토글. 넘긴 줄이 있거나 켜 둔 동안만 서고, 그 구획이
    접혔으면 켜 둔 채여도 숨는다(값은 세션에 남아 다시 펴면 그대로다)."""
    wanted = [
        (
            SECTION_UNITS not in collapsed and (canvas.hidden_units > 0 or show_all_units),
            "더 보기 — 신규 설비 모두",
            SHOW_ALL_UNITS_KEY,
        ),
        (
            SECTION_DOWNTIME not in collapsed
            and (canvas.hidden_arrow_units > 0 or show_all_arrows),
            "더 보기 — 비가동 호기 모두",
            SHOW_ALL_ARROWS_KEY,
        ),
    ]
    shown = [(label, key) for wanted_here, label, key in wanted if wanted_here]
    if not shown:
        return
    with st.container(horizontal=True, gap="medium"):
        for label, key in shown:
            st.toggle(label, key=key, persist_state="session")


def _render_dynamic_absent(view: ProcessDetailView) -> None:
    """설비 일정(②~④) 대신 서는 자리 한 칸 — 데이터 Error 마크 또는 빈 상태 평문 한 줄."""
    with st.container(key=DYNAMIC_ABSENT_KEY):
        if view.readiness is None:
            render_data_error(
                view.dynamic_error or "설비 DB 를 열지 못했습니다.",
                code="PD-01",
                text=DYNAMIC_DB_ERROR_TITLE,
            )
        elif view.dynamic_error:
            # 판정은 통과했는데 계획·설비 일정 계산이 멈춘 갈래 — 조건은 이미 맞아 안내하지 않는다.
            render_data_error(
                f"{view.dynamic_error} {DYNAMIC_OFFICIAL_KEPT}",
                code="PD-01",
                text=DYNAMIC_ERROR_TITLE,
            )
        elif view.readiness.status == NO_COUNTED_UNITS:
            # 채울 입력이 없는 빈 상태다 — 평문 한 줄(설계 규칙 UI-TXT-04).
            st.caption(view.readiness.detail, help=NO_COUNTED_UNITS_HELP)
        else:
            whole_database = view.readiness.status == NO_SNAPSHOT
            note = absent_note(
                view.readiness.badge,
                f"{view.readiness.detail} {DYNAMIC_ABSENT_RULE}",
                screen="공정 Capa 상세",
                process_label=None if whole_database else view.process_label,
            )
            render_data_error(note.message, code="PD-01", text=note.text, goto=EQUIPMENT_SCREEN)


# ================================================================== 산출 근거 패널


class EvidenceCard(NamedTuple):
    """근거 카드 하나 — 제목, 숫자를 넣은 식(여러 줄), 회색 메모."""

    title: str
    formula: str
    notes: tuple[str, ...] = ()
    reference: bool = False
    """참고(설비 일정 기준) 카드 — 점선 테두리."""


def _render_evidence_panel(view: ProcessDetailView, month: int) -> None:
    months = list(view.months)
    index = months.index(month)
    previous = months[index - 1] if index > 0 else None
    following = months[index + 1] if index + 1 < len(months) else None
    trace: ProcessMonthTrace | None
    try:
        trace = simulation_cache.get_process_month_trace(
            view.scenario_key,
            view.process,
            month,
            _scenario_tables=view.scenario_tables,
            _reference_tables=view.reference_tables,
        )
    except (KeyError, ValueError):
        trace = None
    # 접힌 머리 한 줄(2026-11-12 사용자 답 k-c5) — 달 칸을 누르면 펼친다(`open_evidence`). 머리의
    # 달 · 공정은 라벨이라 달을 옮기면 라벨이 바뀌어도 펼침은 기억 칸이 잇는다.
    with (
        st.container(key=EVIDENCE_PANEL_KEY),
        remembered_expander(
            f"산출 근거 · {month_label(month)} · {literal_markdown(view.process_label)}",
            key=EVIDENCE_BOX_KEY,
            icon=":material/calculate:",
        ),
    ):
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            horizontal_alignment="right",
            gap="small",
        ):
            st.button(
                f"◀ {month_label(previous)}" if previous is not None else "◀ 첫 달",
                key=PREVIOUS_MONTH_KEY,
                type="tertiary",
                on_click=step_month,
                args=(view.months, -1, PREVIOUS_MONTH_KEY),
            )
            st.button(
                f"{month_label(following)} ▶" if following is not None else "끝 달 ▶",
                key=NEXT_MONTH_KEY,
                type="tertiary",
                on_click=step_month,
                args=(view.months, 1, NEXT_MONTH_KEY),
            )
        cards = evidence_cards(view, month, trace)
        st.html(evidence_cards_html(cards))
        _render_month_next_screens(view, month)
        with remembered_expander(
            "경로별 인자 — 반영 UPEH·환산 UPEH·측정률과 공통 인자",
            key=ROUTE_FACTORS_EXPANDER_KEY,
            icon=":material/table_rows:",
        ):
            if view.upeh_token:
                st.caption(ROUTE_FACTORS_UPEH_MARK, help=ROUTE_FACTORS_UPEH_HELP)
            _render_route_factors(trace, under_head=not view.upeh_token)


def step_month(months: Sequence[int], step: int, widget_key: str) -> None:
    """◀▶ 콜백 — 보던 달에서 한 칸 옮긴다. 축 끝이면 그대로다. 이 프래그먼트 회차로 다시 그린다.
    단추는 펼친 산출 근거 안에 있어 펼침은 그대로다(옮긴 달의 라벨로 펼친 채 잇는다)."""
    axis = [int(month) for month in months]
    current = st.session_state.get(PROCESS_DETAIL_MONTH_KEY)
    position = axis.index(current) if current in axis else 0
    target = position + step
    if 0 <= target < len(axis):
        st.session_state[PROCESS_DETAIL_MONTH_KEY] = axis[target]
        open_evidence()
    rerun_app_unless_alone(widget_key)


def evidence_cards(
    view: ProcessDetailView, month: int, trace: ProcessMonthTrace | None
) -> list[EvidenceCard]:
    """고른 달의 근거 카드 — ① 소요 ② 가용 ③ 판정 (+ ④ 단축 근거)."""
    record = _summary_record(view.summary, month)
    bridge = _month_record(view.dynamic.canvas.bridge, month) if view.dynamic is not None else None
    assumed = (
        _month_record(view.assumed_summary, month)
        if view.assumed_summary is not None and month in token_months(view.upeh_token)
        else None
    )
    cards = [
        demand_card(trace, record, assumed=assumed, token=view.upeh_token),
        availability_card(record, bridge),
        judgement_card(record, view.thresholds, month, assumed=assumed, token=view.upeh_token),
    ]
    if view.dynamic is not None:
        card = shortening_card(view.dynamic, month)
        if card is not None:
            cards.append(card)
    return cards


def demand_card(
    trace: ProcessMonthTrace | None,
    record: Mapping[str, object],
    *,
    assumed: Mapping[str, object] | None = None,
    token: UpehToken = NO_ASSUMPTION,
) -> EvidenceCard:
    """① 소요 — Σ 경로 부하량 ÷ 대당 Capa 와 경로 수·제외 경로, 상위 제품. 그 달이 UPEH 가정
    구간이면 (`assumed`) 가정 소요 한 줄을 더한다."""
    required = _number(record.get("소요대수"))
    assumed_note = _assumed_demand_note(required, assumed, token)
    if trace is None:
        return EvidenceCard(
            "① 소요",
            f"Σ 경로 부하량 ÷ 대당 Capa\n= {_one(required)} 대",
            (
                "경로 인자를 읽지 못했습니다 — 산출 결과 화면에서 확인합니다.",
                *((assumed_note,) if assumed_note else ()),
            ),
        )
    evidence = trace.evidence
    head = f"경로 {evidence.route_count} · 제외 {evidence.excluded_route_count}"
    formula = f"Σ 경로 부하량 ÷ 대당 Capa\n= {_one(evidence.required)} 대  ({head})"
    notes: list[str] = []
    if evidence.effective_capacity is not None:
        notes.append(
            _effective_capacity_note(
                evidence.unique_demand_load, evidence.effective_capacity, evidence.required
            )
        )
    top = evidence.top_products
    if not top.empty:
        parts = [
            f"{name} {value:,.1f}"
            for name, value in zip(top["제품정보"], top["소요대수"], strict=True)
        ]
        rest = evidence.product_count - len(parts)
        notes.append(" · ".join(parts) + (f" · 그 밖 {rest}개" if rest > 0 else ""))
    if evidence.rule_excluded_route_count:
        notes.append(f"규칙상 제외 {evidence.rule_excluded_route_count}경로(PKG 의 Buffer 아닌 행)")
    if evidence.assumed_ratio_routes:
        notes.append(f"측정률 행 없음 → 1.0 가정 {evidence.assumed_ratio_routes}경로")
    if evidence.blank_ratio_routes:
        notes.append(f"측정률 빈칸·0 → 1.0 {evidence.blank_ratio_routes}경로")
    if assumed_note:
        notes.append(assumed_note)
    return EvidenceCard("① 소요", formula, tuple(notes))


def _effective_capacity_note(load: float, capacity: float, required: float) -> str:
    """① 소요 카드의 「원수요 부하량 L ÷ 실효 대당 Capa C」 — 실효 대당 Capa 는 L ÷ 소요로
    정의하므로(`services/process_capa_detail._evidence`) 이 나눗셈이 카드의 「= 소요 대」 를 낸다.
    줄에 등호가 없어, 적힌 L·C 로 다시 셈한 값이 적힌 소요와 다를 때만 식 앞에 「≈」 를 둔다(결합
    캔버스 과부족 풍선과 같은 길)."""
    load_text, capacity_text = f"{load:,.0f}", f"{capacity:,.1f}"
    written_load, written_capacity = written_value(load_text), written_value(capacity_text)
    recomputed = (
        _one(written_load / written_capacity)
        if written_load is not None and written_capacity
        else ""
    )
    prefix = f"{APPROX} " if equals_mark(_one(required), recomputed) == APPROX else ""
    return f"{prefix}원수요 부하량 {load_text} ÷ 실효 대당 Capa {capacity_text}"


def _assumed_demand_note(
    required: float | None, assumed: Mapping[str, object] | None, token: UpehToken
) -> str:
    """「UPEH 가정 110%: 소요 12.40 ÷ 1.1 = 11.27 (−1.13대)」 — 구간 밖이면 빈 글자. 적힌 소요로
    다시 셈한 값이 가정 소요와 다르면 「≈」 다(③ 의 「소요 = 가정 전 ÷ f」 와 같은 검산). 괄호
    차이도 적힌 두 소요로 다시 빼면 어긋날 때 앞에 「≈」 다(값은 원값의 차이 그대로)."""
    if assumed is None or required is None:
        return ""
    value = _number(assumed.get("소요대수"))
    if value is None:
        return ""
    factor = token_factor(token)
    mark = equals_mark(_two(value), _two(round(required, 2) / factor))
    change = _signed_two(value - required)
    if equals_mark(change, _signed_two(round(value, 2) - round(required, 2))) == APPROX:
        change = f"{APPROX} {change}"
    return (
        f"UPEH 가정 {token_percent(token)}%: 소요 {_two(required)} ÷ {factor:g} {mark} "
        f"{_two(value)} ({change}대)"
    )


def availability_card(
    record: Mapping[str, object], bridge: Mapping[str, object] | None
) -> EvidenceCard:
    """② 가용 — 보유 − 대여 = 가용(Static). 설비 일정이 서면 두 줄을 더한다(2026-11-12 사용자 답
    n1 (가)) — 「② 일정 가용」 가용대수(기존보유 + 호기, 비가동 빼기 전)와, 비가동이 깎은 달이면
    「③ 비가동」 일정 기준 실가용(그 가용 − 비가동 = 필요 단축 일정의 가용). 식 모두 적힌 수로 다시
    셈한 값이 결과와 다르면 「≈」 다."""
    owned = _number(record.get(OWNED_COLUMN))
    lent = _number(record.get(LENT_COLUMN))
    available = _number(record.get("가용대수"))
    derived = None if owned is None else owned - (lent or 0.0)
    derived_mark = equals_mark(
        _one(derived), _one(None if owned is None else round(owned, 1) - round(lent or 0.0, 1))
    )
    formula = (
        f"보유 {_one(owned)} − 대여 {_one(lent)} {derived_mark} {_one(derived)}\n"
        f"가용대수 {_one(available)} (Static)"
    )
    notes: list[str] = []
    if bool(record.get(MISMATCH_COLUMN, False)):
        notes.append("⚠ 가용대수가 보유 − 대여와 다릅니다 — 기준정보 표를 따로 고쳤습니다.")
    if bridge is not None:
        notes += _schedule_availability_notes(bridge)
    return EvidenceCard("② 가용", formula, tuple(notes))


def _schedule_availability_notes(bridge: Mapping[str, object]) -> list[str]:
    """② 가용 카드의 설비 일정 줄 — 「일정 가용(참고): 기존보유 a + 호기 b = c」(비가동 빼기 전)와,
    깎은 비가동이 있으면 「③ 일정 기준 실가용: c − 비가동 d = e」(e 는 필요 단축 일정의 가용)."""
    baseline = _number(bridge.get("기존보유"))
    units_now = _number(bridge.get("호기 가용"))
    unit_loss = _number(bridge.get("호기 비가동 손실")) or 0.0
    removed = _number(bridge.get("입력 비가동 반영")) or 0.0
    total = _number(bridge.get("가용대수"))
    if baseline is None or units_now is None:
        return [f"일정 가용(참고): {_EMPTY}"]
    units = units_now + unit_loss
    free = baseline + units
    free_mark = equals_mark(_one(free), _one(round(baseline, 1) + round(units, 1)))
    notes = [
        f"일정 가용(참고): 기존보유 {_one(baseline)} + 호기 {_one(units)} {free_mark} "
        f"{_one(free)} (환산 · 비가동 빼기 전)"
    ]
    loss = unit_loss + removed
    if round(loss, 9) > 0 and total is not None:
        # 비가동은 ③ 비가동대수 칸과 같은 글이다 — 0 이 아닌 작은 값도 0 이 아니게 적는다.
        loss_written = loss_text(loss)
        loss_mark = equals_mark(
            _one(total), _one(round(free, 1) - (written_value(loss_written) or 0.0))
        )
        notes.append(
            f"③ 일정 기준 실가용: {_one(free)} − 비가동 {loss_written} {loss_mark} {_one(total)} "
            "(필요 단축 일정의 가용)"
        )
    return notes


def judgement_card(
    record: Mapping[str, object],
    thresholds: SecurementThresholds,
    month: int,
    *,
    assumed: Mapping[str, object] | None = None,
    token: UpehToken = NO_ASSUMPTION,
) -> EvidenceCard:
    """③ 판정 — 확보율 식·과부족 식(그 달 확보 기준)과 원인.

    그 달이 UPEH 가정 구간이면(`assumed`) 판정은 한 기준이다 — 머리 식·판정·원인을 가정 레코드로
    내고 식 첫 줄에 「소요 = 가정 전 ÷ f」 를 드러낸다. 가정 전 판정은 회색 「가정 전: …」 한 줄로
    내린다(부족 띠·KPI·다음 화면 줄이 가정 요약을 읽는 것과 같은 기준이다).
    """
    secure, warning = thresholds.for_month(month)
    secure_bound = thresholds.boundary_for(month)[0]
    basis = record if assumed is None else assumed
    available = _number(basis.get("가용대수"))
    required = _number(basis.get("소요대수"))
    status = basis.get(STATUS_COLUMN)
    title = "③ 판정" if assumed is None else f"③ 판정 (UPEH 가정 {token_percent(token)}%)"
    # 기준은 정수 하나다. 판정은 확보율을 사사오입한 정수 % 로 견주므로 과부족 식은 그 판정 경계
    # (110% 면 109.5%)를 곱한다 — 그만큼 더하면 확보로 판정된다.
    bases = (
        f"확보 기준 {threshold_percent_label(secure)} · 경고 기준 "
        f"{threshold_percent_label(warning)} — 사사오입 판정(확보 "
        f"{boundary_percent_label(secure)} 이상)"
    )
    if required is None or required <= 0 or available is None:
        return EvidenceCard(title, "소요 없음 — 판정하지 않습니다", (bases,))
    rate = available / required
    name = _STATUS_NAMES.get(str(status), _EMPTY)
    balance = _whole(basis.get(BALANCE_COLUMN))
    raw = available - required * secure_bound
    # 식의 숫자는 소수 둘째 자리다. 적은 숫자로 다시 셈한 값이 결과와 다르면 「≈」 로 밝힌다 —
    # 결과는 반올림 전 값으로 낸다(판정·과부족이 그 값을 쓴다).
    shown_available, shown_required = round(available, 2), round(required, 2)
    rate_text = f"{rate:.1%}"
    rate_mark = equals_mark(
        rate_text,
        f"{shown_available / shown_required:.1%}" if shown_required > 0 else "",
    )
    raw_text = _signed_two(raw)
    raw_mark = equals_mark(raw_text, _signed_two(shown_available - shown_required * secure_bound))
    lines = [
        f"확보율 = {_two(available)} ÷ {_two(required)} {rate_mark} {rate_text} → {name}",
        f"과부족 = {_two(available)} − {_two(required)}×{boundary_percent_label(secure)}"
        f" {raw_mark} {raw_text} → {signed_int(balance) if balance is not None else _EMPTY}",
    ]
    if assumed is not None:
        lines.insert(0, _assumed_required_line(_number(record.get("소요대수")), required, token))
    notes = [bases]
    cause_note = _cause_note(basis, required)
    if cause_note:
        notes.append(cause_note)
    if str(status) in _SHORT_STATUSES and balance == 0:
        notes.append("잡음 경계 — 확보율이 기준에 아주 조금 못 미쳐 칠했지만 과부족은 0 입니다")
    if str(status) == "secure" and surplus_held_at_zero(available, required, secure):
        notes.append(ROUNDED_IN_NOTE.format(threshold=threshold_percent_label(secure)))
    if assumed is not None:
        notes.append(_official_judgement_note(record))
    return EvidenceCard(title, "\n".join(lines), tuple(notes))


def _assumed_required_line(official: float | None, assumed: float, token: UpehToken) -> str:
    """「소요 = 49.80 ÷ 1.5 = 33.20」 — 가정 판정의 소요가 가정 전 소요에서 어떻게 왔는지(검산이
    어긋나면 「≈」)."""
    factor = token_factor(token)
    if official is None:
        return f"소요 = 가정 전 ÷ {factor:g} = {_two(assumed)}"
    mark = equals_mark(_two(assumed), _two(round(official, 2) / factor))
    return f"소요 = {_two(official)} ÷ {factor:g} {mark} {_two(assumed)}"


def _cause_note(record: Mapping[str, object], required: float) -> str:
    """「원인: …」 한 줄 — 원인이 없으면 빈 글자. `required` 는 그 레코드의 소요(0 보다 크다)."""
    cause = "" if record.get(CAUSE_COLUMN) is None else str(record.get(CAUSE_COLUMN))
    owned = _number(record.get(OWNED_COLUMN))
    if cause == CAUSE_OWNED_SHORT and owned is not None:
        shown = f"{owned / required:.1%}"
        written_required = round(required, 1)
        mark = equals_mark(
            shown, f"{round(owned, 1) / written_required:.1%}" if written_required else ""
        )
        return (
            f"원인: {cause} — 총보유 {_one(owned)} ÷ 소요 {_one(required)} {mark} "
            f"{shown} 도 확보 기준 미달(투자 검토)"
        )
    if cause == CAUSE_RENTAL:
        return (
            f"원인: {cause} — 총보유로는 확보, 대여 {_one(_number(record.get(LENT_COLUMN)))} 대를 "
            "빼면 미달"
        )
    if cause == CAUSE_AVAILABILITY_MISMATCH:
        return f"원인: {cause} — 보유 − 대여로는 확보인데 가용대수가 따로 낮습니다"
    return f"원인: {cause}" if cause else ""


def _official_judgement_note(record: Mapping[str, object]) -> str:
    """UPEH 가정 달의 회색 한 줄 — 「가정 전: 확보율 100.4% → 경고 · 과부족 −5 · 원인 보유로도
    부족」."""
    available = _number(record.get("가용대수"))
    required = _number(record.get("소요대수"))
    if required is None or required <= 0 or available is None:
        return "가정 전: 소요 없음 — 판정하지 않습니다"
    balance = _whole(record.get(BALANCE_COLUMN))
    cause = "" if record.get(CAUSE_COLUMN) is None else str(record.get(CAUSE_COLUMN))
    return (
        f"가정 전: 확보율 {available / required:.1%} → "
        f"{_STATUS_NAMES.get(str(record.get(STATUS_COLUMN)), _EMPTY)} · 과부족 "
        + (signed_int(balance) if balance is not None else _EMPTY)
        + (f" · 원인 {cause}" if cause else "")
    )


def shortening_card(dynamic: DynamicView, month: int) -> EvidenceCard | None:
    """④ 단축 근거 — 그 달 설비 일정 상태가 충족이 아닐 때만. 목표·구간·바닥·당긴 호기·단축 후."""
    record = _month_record(dynamic.canvas.process_months, month)
    if record is None:
        return None
    state = "" if record.get("상태") is None else str(record.get("상태"))
    if not state or state == STATUS_MET:
        return None
    canvas = dynamic.canvas
    target = target_for_month(canvas.target, month)
    required = _number(record.get("소요대수"))
    target_units = _number(record.get("목표대수"))
    before = _number(record.get("가용대수"))
    after = _number(record.get("단축후가용대수"))
    gap = _number(record.get("과부족"))
    gap_after = _number(record.get("단축후과부족"))
    window = wd_window(month, canvas.cutoff_days)
    floor = max(window.first_day, canvas.today)
    target_mark = equals_mark(
        _two(target_units),
        _two(round(required, 2) * target) if required is not None else "",
    )
    gap_mark = equals_mark(
        _signed_two(gap),
        _signed_two(round(before, 2) - round(target_units, 2))
        if before is not None and target_units is not None
        else "",
    )
    lines = [
        f"목표 {_two(target_units)} {target_mark} 소요 {_two(required)} × {_ratio_percent(target)}",
        f"가용 {_two(before)} − 목표 {_two(target_units)} {gap_mark} {_signed_two(gap)}",
        f"구간 {_day(window.first_day, canvas.today)}~{_day(window.boundary_end, canvas.today)}"
        f" · 바닥 {_day(floor, canvas.today)}(구간 시작·오늘 중 늦은 날)",
    ]
    for unit in contributing_units(dynamic.canvas.unit_events, month, today=canvas.today):
        lines.append(unit)
    lines.append(f"→ 단축 후 {_two(after)} ({_signed_two(gap_after)})")
    notes = [f"상태: {state}"]
    today_month = production_position(canvas.today, canvas.cutoff_days, [month]).month
    if month < today_month:
        notes.append("기한 지남 — 지난 달은 단축으로 바꿀 수 없습니다")
    elif month == today_month:
        notes.append("오늘이 든 달 — 남은 날만 셉니다(추가N 이 크게 나올 수 있음)")
    if state in (STATUS_EXPIRED, STATUS_NEW_LIMIT):
        notes.append("단축·신규로도 이 달을 다 채우지 못했습니다")
    return EvidenceCard(
        f"④ 단축 근거 (설비 일정 · 목표 {target_label(target)})",
        "\n".join(lines),
        tuple(notes),
        reference=True,
    )


def contributing_units(unit_events: pd.DataFrame, month: int, *, today: date) -> list[str]:
    """그 달을 메운 호기 줄 — 대상 월이 그 달이거나 해소 기여 월에 그 달이 든 단축·추가N.

    괄호의 증분은 **그 달** 몫(`월별 늘어난 환산대수`)이다 — 호기 표의 `늘어난 환산대수` 는 대상 월
    구간의 몫이라, 앞 달에 당긴 호기를 뒤 달 카드에 적으면 식(가용 + 호기 증분 = 단축 후)이 맞지
    않는다. 그 달 몫을 모르면 「-」다.
    """
    if unit_events.empty:
        return []
    lines: list[str] = []
    for record in unit_events.to_dict("records"):
        kind = str(record.get("줄"))
        if kind not in (ROW_SHORTENED, ROW_VIRTUAL):
            continue
        target_month = _whole(record.get("대상 월"))
        resolved = _month_tuple(record.get("해소 기여 월"))
        if target_month != month and month not in resolved:
            continue
        unit = str(record.get("호기"))
        gain = month_share(record.get("월별 늘어난 환산대수"), month)
        gain_text = f"+{gain:,.2f}" if gain is not None else _EMPTY
        target = _as_date(record.get("목표 Qual"))
        if kind == ROW_VIRTUAL:
            lines.append(f"→ {unit} 신규 필요 Qual {_day(target, today)} ({gain_text})")
            continue
        original = _as_date(record.get("Qual일정"))
        days = _whole(record.get("단축일수")) or 0
        lines.append(
            f"→ {unit} {_day(original, today)}→{_day(target, today)} "
            f"({_MINUS}{days}일, {gain_text})"
            + (" · 반입 전" if bool(record.get("반입 전")) else "")
        )
    return lines


def evidence_cards_html(cards: Sequence[EvidenceCard]) -> str:
    """근거 카드 묶음(서식 포함) — 넓으면 한 줄에 넷, 좁으면 접힌다."""
    body = "".join(
        f'<div class="pcd-card{" ref" if card.reference else ""}">'
        f"<h5>{html.escape(card.title)}</h5>"
        f'<div class="pcd-f">{html.escape(card.formula)}</div>'
        + "".join(f'<div class="pcd-m">{html.escape(note)}</div>' for note in card.notes)
        + "</div>"
        for card in cards
    )
    return (
        "<style>"
        ".pcd-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}"
        f".pcd-card{{border:1px solid {tokens.BORDER};border-radius:8px;padding:8px 10px;"
        f"background:{tokens.SURFACE};display:grid;gap:4px;align-content:start;min-width:0}}"
        ".pcd-card.ref{border-style:dashed}"
        f".pcd-card h5{{margin:0;padding:0;font-size:13px;font-weight:700;color:{tokens.TEXT};"
        f"font-family:{tokens.FONT_FAMILY}}}"
        f".pcd-f{{font-family:{tokens.FONT_FAMILY_NUMERIC};font-size:12.5px;line-height:1.6;"
        f"white-space:pre-wrap;color:{tokens.TEXT};font-variant-numeric:tabular-nums}}"
        f".pcd-m{{font-size:12px;color:{tokens.TEXT_MUTED};font-family:{tokens.FONT_FAMILY}}}"
        "</style>"
        f'<div class="pcd-cards">{body}</div>'
    )


def _render_route_factors(trace: ProcessMonthTrace | None, *, under_head: bool) -> None:
    """경로마다 인자·근거 칸, 공통 인자(양산구분별 효율·여유율, 일수·모듈수), 제외 경로.

    `under_head` 면 경로 표가 「경로별 인자」 펼침의 첫 요소라 바로 위가 펼침 머리다 — 표 도구
    막대가 머리 오른쪽 끝 아래쪽을 덮어 머리를 누른 손이 막대 단추(찾기 등)에 먹히지 않게 표
    앞에 띄움을 둔다(AGENTS 9장 「표 도구 막대」). UPEH 가정 표지가 머리와 표 사이에 서면
    띄움이 없다."""
    if trace is None:
        render_data_error("경로 인자를 읽지 못했습니다.", code="PD-01")
        return
    routes = trace.routes.reindex(columns=ROUTE_COLUMNS)
    if routes.empty:
        st.caption("이 달 이 공정의 경로가 없습니다.")
    else:
        if under_head:
            toolbar_clearance()
        # 경로마다 UPEH(Main)·ST(MI) 가운데 하나만 값이다 — 다른 칸은 비워 둔다. 주지 않으면
        # Streamlit 이 그 칸에 「None」 글자를 그린다.
        st.dataframe(
            routes,
            hide_index=True,
            width="stretch",
            placeholder="",
            column_config={"ST": "ST(분)"},
            key="process_detail_routes",
        )
    common = trace.common_factors
    parts = []
    if common.run_day is not None:
        parts.append(f"RUN_DAY {common.run_day:g}")
    if common.module_count is not None:
        parts.append(f"모듈수 {common.module_count:g}")
    for row in common.by_class.to_dict("records"):
        run_rate = _number(row.get("CAPA_RUN_RATE"))
        vital = _number(row.get("편중률"))
        parts.append(
            f"{row.get('양산구분')} 효율 {_ratio_text(run_rate)} · "
            f"여유율(편중률) {_ratio_text(vital)}"
        )
    if parts:
        st.caption("공통 인자 — " + " · ".join(parts))
    if not trace.excluded.empty:
        st.caption(f"제외 경로 {len(trace.excluded)}행(규칙상 제외 포함)")
        st.dataframe(
            trace.excluded, hide_index=True, width="stretch", key="process_detail_excluded"
        )


# ================================================================== KPI · 정리 줄


class Prescription(NamedTuple):
    """대책 — 이 공정의 단축 호기 수·추가N 수와 설비 일정 기준으로 남은 미달 달 수."""

    shortened: int
    new: int
    unresolved_months: int
    dynamic_short_months: int
    """오늘이 든 생산월부터 설비 일정 기준 가용이 단축 목표에 못 미친 달 수(단축 대상). 지난 달은
    단축으로 바꿀 수 없어 세지 않는다 — 캔버스 ② 가 흐리게 두는 달과 같다."""


def prescription(dynamic: DynamicView) -> Prescription:
    """설비 일정 계획을 이 공정으로 센다 — 단축(구분 「단축」)·신규(「신규」 = 추가N)·못 채운 달."""
    return _prescription(dynamic.units, dynamic.canvas.process_months, dynamic.canvas)


def official_prescription(dynamic: DynamicView) -> Prescription | None:
    """UPEH 가정 계획을 그릴 때 같은 공정의 가정 전 계획 셈(KPI 회색 줄). 가정 전 계획을 그리면
    None."""
    if dynamic.official_units is None or dynamic.official_process_months is None:
        return None
    return _prescription(dynamic.official_units, dynamic.official_process_months, dynamic.canvas)


def _prescription(
    units: pd.DataFrame, months: pd.DataFrame, canvas: DynamicCanvasInput
) -> Prescription:
    kinds = units["구분"].astype("string") if "구분" in units.columns else pd.Series(dtype="string")
    gaps = (
        pd.to_numeric(months["과부족"], errors="coerce").round(9)
        if "과부족" in months.columns
        else pd.Series(dtype="float64")
    )
    if "과부족" in months.columns and MONTH in months.columns and not months.empty:
        # 오늘이 기여하는 생산월(축과 무관한 값 — 축은 자리만 정한다)보다 앞선 달은 뺀다.
        plan_months = pd.to_numeric(months[MONTH], errors="coerce")
        known = plan_months.dropna()
        if not known.empty:
            today_month = production_position(
                canvas.today, canvas.cutoff_days, [int(known.iloc[0])]
            ).month
            gaps = gaps.where(plan_months.ge(today_month).to_numpy())
    states = (
        months["상태"].astype("string") if "상태" in months.columns else pd.Series(dtype="string")
    )
    return Prescription(
        shortened=int(kinds.eq(KIND_SHORTENED).sum()),
        new=int(kinds.eq(KIND_NEW).sum()),
        unresolved_months=int(states.isin([STATUS_EXPIRED, STATUS_NEW_LIMIT]).sum()),
        dynamic_short_months=int(gaps.lt(0).sum()),
    )


def render_process_kpis(
    kpis: ProcessCapaKpis,
    *,
    thresholds: SecurementThresholds,
    dynamic: DynamicView | None,
    official: ProcessCapaKpis | None = None,
) -> None:
    """KPI 넷 — 최저 확보율, 확보 기준 미달 달·월 최대 부족, 부족 원인, 대책(설비 일정 기준).

    값 글자를 짧게 둔다(카드 폭에 한 줄). 뜻풀이는 값 아래 회색 한 줄과 `?` 풍선이다. UPEH 가정이
    켜졌으면 `kpis` 는 가정 요약의 것이고 `official` 이 가정 전(Static) 요약의 것이다 — 회색 줄에
    「가정 전 n」 을 함께 적는다(2026-11-12 사용자 답 q2 (가)).
    """
    lowest_tone: MetricTone = "neutral"
    if kpis.lowest_rate is not None and kpis.lowest_rate_month is not None:
        status = thresholds.status(kpis.lowest_rate, kpis.lowest_rate_month)
        if status == "shortage":
            lowest_tone = "critical"
        elif status == "warning":
            lowest_tone = "attention"
    plan = prescription(dynamic) if dynamic is not None else None
    official_plan = official_prescription(dynamic) if dynamic is not None else None
    lowest_note = (
        f" · 가정 전 {official.lowest_rate:.1%}"
        if official is not None and official.lowest_rate is not None
        else ""
    )
    shortage_note = f" · 가정 전 {official.shortage_months}개월" if official is not None else ""
    prescription_note = (
        f" · 가정 전 {prescription_text(official_plan)}" if official_plan is not None else ""
    )
    # 이 줄의 값은 글이 섞여 다른 화면의 큰 숫자보다 길다 — 한 단계 작게 둔다.
    st.html(
        f'<style>.st-key-{KPI_ROW_KEY} [data-testid="stMetricValue"] '
        f"{{font-size:{KPI_VALUE_FONT_REM}rem}}</style>"
    )
    with metric_row(key=KPI_ROW_KEY):
        render_status_metric(
            "최저 확보율",
            f"{kpis.lowest_rate:.1%}" if kpis.lowest_rate is not None else _EMPTY,
            key="process_detail_kpi_lowest",
            tone=lowest_tone,
            caption=(
                (month_label(kpis.lowest_rate_month) + lowest_note)
                if kpis.lowest_rate_month is not None
                else (lowest_note.removeprefix(" · ") or None)
            ),
        )
        render_status_metric(
            "확보 기준 미달",
            f"{kpis.shortage_months}개월" if kpis.shortage_months else "없음",
            key="process_detail_kpi_shortage",
            tone="attention" if kpis.shortage_months else "neutral",
            # 회색 줄은 좁은 창에서 끝이 말줄임으로 잘린다 — 끝에 부정(「기간 합 아님」)을 두면
            # 「기간 합…」 만 남아 거꾸로 읽히므로 그 말은 풍선으로 옮긴다.
            caption=(
                f"월 최대 {_MINUS}{kpis.max_shortage}대"
                if kpis.shortage_months
                else "월별 확보 기준"
            )
            + shortage_note,
            help=(
                "판정이 확보가 아닌 달 수와, 그 달들 가운데 확보 기준까지 모자란 대수의 "
                "최댓값입니다. 기간 합이 아닙니다 — 같은 설비가 여러 달에 다시 쓰입니다."
            ),
        )
        render_status_metric(
            "부족 원인",
            cause_summary(kpis, plan),
            key="process_detail_kpi_cause",
            caption="달 수 · "
            + ("UPEH 가정 기준" if official is not None else "Static 기준")
            + (" · 일정은 설비 일정" if plan is not None else ""),
            help=CAUSE_HELP,
        )
        render_status_metric(
            "대책",
            prescription_text(plan),
            key="process_detail_kpi_prescription",
            caption=f"설비 일정 기준{prescription_note}",
            help=(
                "필요 단축 일정과 같은 계산을 이 공정 하나로 본 것입니다 — "
                "단축은 Qual 을 당길 호기, 신규는 당겨도 모자라 더 들여야 하는 추가N 입니다."
            ),
        )


def cause_summary(kpis: ProcessCapaKpis, plan: Prescription | None) -> str:
    """「보유 a · 대여 b · 불일치 m · 일정 c」(달 수) — 0 인 갈래는 뺀다. 모두 0 이면 「없음」."""
    parts = [
        (CAUSE_SHORT_NAMES[CAUSE_OWNED_SHORT], kpis.owned_short_months),
        (CAUSE_SHORT_NAMES[CAUSE_RENTAL], kpis.rental_months),
        (CAUSE_SHORT_NAMES[CAUSE_AVAILABILITY_MISMATCH], kpis.mismatch_months),
        (CAUSE_SHORT_NAMES[SCHEDULE_CAUSE], plan.dynamic_short_months if plan is not None else 0),
    ]
    shown = [f"{name} {count}" for name, count in parts if count]
    return " · ".join(shown) if shown else "없음"


def prescription_text(plan: Prescription | None) -> str:
    """대책 글 — 「단축 n대 · 신규 m대」, 할 것이 없으면 「목표 충족」, 설비 일정이 없으면
    「일정 없음」(까닭은 머리 배지)."""
    if plan is None:
        return "일정 없음"
    if plan.shortened == 0 and plan.new == 0:
        return "목표 충족" if plan.unresolved_months == 0 else "기한 지남"
    return f"단축 {plan.shortened}대 · 신규 {plan.new}대"


def shortening_link_needed(*, arrived_from_card: bool) -> bool:
    """맨 아래 필요 단축 일정 링크가 서는가 — 그 화면 카드에서 온 방문(출처 띠 곁 「← 필요 단축
    일정」 이 같은 길)만 뺀다.

    일정 부족 달이 있는 공정에도 선다 — 근거 패널 「이 달 일정 부족 — 필요 단축 일정」 은 그 달을
    골랐을 때만 서서, 처음 연 달이 일정 부족 달이 아니면 이 화면에 그리 가는 단추가
    없었다(2026-11-10 답 Q2-8 — 설계 규칙 UI-LAY-12 예외). KPI 아래에는 그리 가는 줄을 두지
    않는다(2026-11-10 보드 c2-picked).
    """
    return not arrived_from_card


def render_closing_row(
    *,
    process: str,
    marks: Sequence[tuple[str, str]],
    show_link: bool,
    link_help: str | None,
) -> None:
    """정리 줄 — 값 표지(있을 때만), 필요 단축 일정 화면 링크(그 화면 카드에서 온 방문은 없음).

    `marks` 는 (값 한 마디, 그 풍선) 이다 — 지금은 입력 비가동 반영(n칸 · 합 x대) 하나. 늘 서던
    설명 · 내역 글은 걷었다(설계 규칙 UI-TXT-01 · 04 · 07 — 같은 말이 캔버스 · Guide · 풍선 · 상태
    알림에 있다). `show_link` 는 `shortening_link_needed` 이고, `link_help` 는 링크의 풍선이다(HOME
    칸 방문이라 두 화면의 설비 기준이 갈릴 때)."""
    for mark, mark_help in marks:
        st.caption(f":material/event_busy: {mark}", help=mark_help)
    if show_link:
        st.button(
            "필요 단축 일정에서 전체 공정·진척 비교 보기",
            key=SHORTENING_TAB_LINK_KEY,
            icon=":material/arrow_forward:",
            type="tertiary",
            on_click=open_shortening_page,
            args=(process,),
            help=link_help,
        )


def open_shortening_page(process: str) -> None:
    """필요 단축 일정 화면을 이 공정 카드 **강조**로 연다 — 강조 칸 하나만 적는다.

    그 화면의 「강조 공정」(`shortening_board.SHORTENING_HIGHLIGHT_KEY`)에 이 공정을 적고 옮긴다 —
    그 카드가 맨 위에 테두리·「공정 Capa 상세에서 연 공정」 배지로 선다. **공정 필터는 심지
    않는다**: 필터 칸은 공용 조회 조건(설비 DB `0019`)의 세션 칸이라, 심은 [공정] 을 사용자가 지우면
    빈 선택이 공용 프로필에 저장됐다(2026-10-22 결함). 기준선(`0021`)도 읽지도 쓰지도 않는다. 갈
    곳이 없으면(내비게이션이 없는 단독 실행) 옮기지 않는다. 화면 탭 상한에 걸리면 강조 칸을 적지
    않는다 — 실패한 클릭의 강조가 나중에 사이드바로 연 그 화면에 서지 않게(`refused_at_tab_limit`).
    """
    if refused_at_tab_limit(REQUIRED_SHORTENING.path):
        return
    highlight_shortening_process(str(process), source=HIGHLIGHT_FROM_DETAIL)
    try:
        st.switch_page(REQUIRED_SHORTENING.path)
    except StreamlitPageNotFoundError:
        return


# ================================================================== 부족 원인의 다음 화면


def open_availability_gap() -> None:
    """가용설비 현황 `Summary` › `Static 대비 일정` 탭으로 옮긴다 — 그 화면의 바깥·안쪽 탭 기억
    칸만 적는다.

    그 탭의 공정·호기 필터는 심지 않는다(그 탭의 조건은 그 탭이 정한다). 갈 곳이 없으면(단독
    실행) 옮기지 않는다. 콜백이 아니라 본문에서 부른다 — 프래그먼트 콜백 안의 `st.switch_page` 는
    서버 로그 경고를 남긴다. 화면 탭 상한에 걸리면 탭 기억 칸도 적지 않는다(`refused_at_tab_limit`).
    """
    if refused_at_tab_limit(AVAILABLE_EQUIPMENT_PAGE):
        return
    remember_open_tab(EQUIPMENT_TAB_KEY, EQUIPMENT_SUMMARY_TAB)
    remember_open_tab(EQUIPMENT_SUMMARY_TAB_KEY, EQUIPMENT_GAP_TAB)
    try:
        st.switch_page(AVAILABLE_EQUIPMENT_PAGE)
    except StreamlitPageNotFoundError:
        return


class NextScreens(NamedTuple):
    """원인마다 다음 화면 단추 글. None 인 원인은 단추가 없다."""

    owned: str | None = None
    """보유로도 부족 → 「투자 검토 대상」 표지와 산출 결과."""

    mismatch: str | None = None
    """가용 불일치 → 가용설비 현황 `Static 대비 일정`."""

    schedule: str | None = None
    """일정(설비 일정 기준 단축 목표 미달) → 필요 단축 일정."""

    def present(self) -> bool:
        return any(text is not None for text in self)


def month_next_screens(view: ProcessDetailView, month: int) -> NextScreens:
    """고른 달의 원인으로 낸 다음 화면 글 — ③ 판정 카드의 원인과, 그 달이 설비 일정 기준 단축 대상
    (오늘이 든 생산월부터 목표 미달)이면 일정."""
    cause = _summary_record(view.judgement_summary, month).get(CAUSE_COLUMN)
    cause_text = "" if cause is None else str(cause)
    return NextScreens(
        owned="이 달 보유로도 부족 — 산출 결과" if cause_text == CAUSE_OWNED_SHORT else None,
        mismatch=(
            "이 달 가용 불일치 — 가용설비 현황"
            if cause_text == CAUSE_AVAILABILITY_MISMATCH
            else None
        ),
        schedule=(
            "이 달 일정 부족 — 필요 단축 일정"
            if view.dynamic is not None and schedule_short_month(view.dynamic, month)
            else None
        ),
    )


def schedule_short_month(dynamic: DynamicView, month: int) -> bool:
    """그 달이 KPI 「부족 원인 · 일정」 에 드는가 — 오늘이 든 생산월부터, 설비 일정 기준 가용이 단축
    목표에 못 미친 달(`prescription` 이 세는 달과 같다)."""
    record = _month_record(dynamic.canvas.process_months, month)
    if record is None:
        return False
    gap = _number(record.get("과부족"))
    if gap is None or round(gap, 9) >= 0:
        return False
    today_month = production_position(
        dynamic.canvas.today, dynamic.canvas.cutoff_days, [int(month)]
    ).month
    return int(month) >= today_month


def _render_month_next_screens(view: ProcessDetailView, month: int) -> None:
    """근거 패널 — 고른 달의 원인으로 낸 다음 화면(본문 프래그먼트 안)."""
    screens = month_next_screens(view, month)
    if screens.present():
        _render_next_screens(
            screens,
            process=view.process,
            gap_key=EVIDENCE_GAP_BUTTON_KEY,
            shortening_key=EVIDENCE_SHORTENING_BUTTON_KEY,
            shortening_help=view.shortening_link_help,
        )


def _render_next_screens(
    screens: NextScreens,
    *,
    process: str,
    gap_key: str,
    shortening_key: str,
    shortening_help: str | None,
) -> None:
    """다음 화면 줄 — 「다음 화면」 글 뒤에 원인마다 링크·단추. 화면을 옮기는 단추는 본문에서
    옮긴다(근거 패널은 프래그먼트다)."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption("다음 화면", width="content")
        if screens.owned is not None:
            st.markdown(INVESTMENT_BADGE, width="content")
            render_page_link(
                CALCULATION_RESULT_PAGE, label=screens.owned, icon=":material/calculate:"
            )
        if screens.mismatch is not None and st.button(
            screens.mismatch,
            key=gap_key,
            type="tertiary",
            icon=":material/compare_arrows:",
        ):
            open_availability_gap()
        if screens.schedule is not None and st.button(
            screens.schedule,
            key=shortening_key,
            type="tertiary",
            icon=":material/event_upcoming:",
            help=shortening_help,
        ):
            open_shortening_page(process)


# ================================================================== 머리 ◀▶ 공정 넘기기


def render_process_steps(steps: ProcessSteps, *, label_of: Callable[[str], str]) -> None:
    """머리 공정명 옆 ◀▶ — 확보 기준 미달 공정을 조회기간 최저 확보율이 낮은 차례로 넘긴다
    (세션 값).

    미달 공정이 없으면 그리지 않는다. 콜백(`step_to_process`)이 공정 상자 값과 그 공정의 첫 미달
    달을 적고 앱 전체 회차로 다시 돈다 — 머리 줄은 프래그먼트 밖이다.

    단추 라벨은 갈 곳을 말하는 글(「다음 미달 공정: …」)이라 읽기 도구가 그 이름으로 읽고, 화면에는
    그 글을 시각적으로만 숨기고(sr-only) 기호 ◀ ▶ 를 CSS 생성 글(대체 글 없음)로 보인다
    (`_STEP_BUTTON_STYLE`). 풍선은 전처럼 공정명 · 최저 확보율이다.
    """
    if steps.total == 0:
        return
    st.html(_STEP_BUTTON_STYLE)
    _step_button("◀", steps.previous, key=PROCESS_DETAIL_PREVIOUS_PROCESS_KEY, label_of=label_of)
    st.caption(
        f"미달 {steps.position}/{steps.total}"
        if steps.position is not None
        else f"미달 공정 {steps.total}개",
        width="content",
        help=(
            "확보 기준 미달 공정(판정이 확보가 아닌 달이 있는 공정)을 조회기간 최저 확보율이 낮은 "
            "차례로 넘깁니다. 옮기면 그 공정의 첫 미달 달을 엽니다."
        ),
    )
    _step_button("▶", steps.following, key=PROCESS_DETAIL_NEXT_PROCESS_KEY, label_of=label_of)


# 머리 ◀ ▶ 단추 — 라벨 글은 읽기 도구에만 남기고(1px 상자 밖을 자른다 — `display: none` 이면
# 접근 이름에서도 빠진다), 기호는 `::before` 생성 글로 그린다. 생성 글의 대체 글을 비워(`/ ""`)
# 접근 이름에 기호가 끼지 않는다.
_STEP_BUTTON_MARKS = {
    PROCESS_DETAIL_PREVIOUS_PROCESS_KEY: "◀",
    PROCESS_DETAIL_NEXT_PROCESS_KEY: "▶",
}
_STEP_BUTTON_STYLE = (
    "<style>"
    + "".join(
        f'.st-key-{key} button [data-testid="stMarkdownContainer"]{{position:absolute!important;'
        "width:1px;height:1px;margin:-1px;overflow:hidden;clip-path:inset(50%);"
        "white-space:nowrap}"
        f'.st-key-{key} button::before{{content:"{mark}" / ""}}'
        for key, mark in _STEP_BUTTON_MARKS.items()
    )
    + "</style>"
)


def step_button_label(mark: str, step: ProcessStep | None, label_of: Callable[[str], str]) -> str:
    """머리 ◀ ▶ 단추의 라벨(곧 접근 이름) — 「다음 미달 공정: Laser Marking · 최저 1.1%」, 갈
    곳이 없으면 「다음 미달 공정 없음」. 공정 표시명은 사람 글이라 마크다운 글자 그대로 막는다."""
    direction = "이전" if mark == "◀" else "다음"
    if step is None:
        return f"{direction} 미달 공정 없음"
    rate = f" · 최저 {step.minimum_rate:.1%}" if step.minimum_rate is not None else ""
    return f"{direction} 미달 공정: {literal_markdown(label_of(step.process))}{rate}"


def _step_button(
    mark: str, step: ProcessStep | None, *, key: str, label_of: Callable[[str], str]
) -> None:
    if step is None:
        st.button(
            step_button_label(mark, step, label_of),
            key=key,
            type="tertiary",
            disabled=True,
            help="이쪽으로 넘길 미달 공정이 없습니다",
        )
        return
    rate = f" · 최저 {step.minimum_rate:.1%}" if step.minimum_rate is not None else ""
    st.button(
        step_button_label(mark, step, label_of),
        key=key,
        type="tertiary",
        help=f"{literal_markdown(label_of(step.process))}{rate}",
        on_click=step_to_process,
        args=(step.process, step.month),
    )


# ================================================================== 값 다루기


def _summary_record(summary: pd.DataFrame, month: int) -> dict[str, object]:
    record = _month_record(summary, month)
    return record if record is not None else {}


def _month_record(frame: pd.DataFrame, month: int) -> dict[str, object] | None:
    if frame.empty or MONTH not in frame.columns:
        return None
    rows = frame.loc[pd.to_numeric(frame[MONTH], errors="coerce").eq(int(month))]
    if rows.empty:
        return None
    return {str(key): value for key, value in rows.iloc[0].items()}


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _whole(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    return None


def _month_tuple(value: object) -> tuple[int, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(int(item) for item in value if _whole(item) is not None)
    if isinstance(value, str):
        return tuple(int(part) for part in value.replace(" ", "").split(",") if part.isdigit())
    return ()


def _day(day: date | None, today: date) -> str:
    """호기 줄과 같은 날짜 글 — 올해면 `MM.DD`, 해가 다르면 `YY.MM.DD`."""
    return "미정" if day is None else month_day(day, today=today)


def _one(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:,.1f}"


def _two(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:,.2f}"


def _signed_two(value: float | None) -> str:
    if value is None:
        return _EMPTY
    rounded = round(value, 2) + 0.0
    if rounded > 0:
        return f"+{rounded:,.2f}"
    if rounded < 0:
        return f"{_MINUS}{abs(rounded):,.2f}"
    return "0.00"


def _ratio_text(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:g}"
