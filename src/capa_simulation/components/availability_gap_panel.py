# Purpose: Static·설비 일정 기준 비교에서 고른 가용대수 그림·9행 시트·확보율 결과 하나를 그린다.

"""Static · 설비 일정 기준 가용대수 비교 탭(「Static 대비 일정」).

이 탭만 **시뮬레이션 DB** 를 본다. 나머지 탭은 설비 운영 DB 만 열며, 이 페이지는 활성
시나리오가 없어도 열리는 유일한 계산 계열 화면이다. 그래서 Static 을 못 읽는 상황
(시나리오 없음·DB 잠김)은 **이 탭 안에서만** 알리고 다른 탭을 막지 않는다 — 페이지가
통째로 죽으면 Cut-off 를 적으러 들어올 수조차 없다.

가용대수 그림·분류별 내역·확보율 교차검증 중 선택한 결과만 그린다.

**분류별 내역은 9행 비교 시트다**(`services/availability_sheet.py`, 2026-10-17 사용자 결정). Static
보유·대여·가용(기준정보 값 그대로) · 설비 일정 기준 보유·대여(비가동)·가용(환산대수, 반사실) ·
GAP 세 행을 공정 Capa 상세 결합 캔버스 꼴(`availability_sheet_canvas`)로 그린다. 칸을 누르면 아래
근거 카드에 그 칸이 어떻게 나왔는지 뜬다 — 설비 일정 기준 칸은 호기 줄(줄을 더하면 칸), Static
칸은 출처, GAP 칸은 식과 짝 호기. 시트와 근거 카드는 키 붙은
프래그먼트라(`render_availability_sheet`) 칸을 누르면 그 둘만 다시 그린다. `표시` 를 `호기 목록`
으로 바꾸면 상태별 기여(입고 예정·셋업 진행중·보관 …)를 긴 표로 본다.

**칸 누름** — 콜백(`pick_gap_sheet_cell`)이 세션 칸에 (범위 지문, 달, 행 id)를 적는다. 같은 칸을
다시 누르면 닫는다 — **닫는 길은 이것뿐이다**(닫기 단추는 없다). 빈 선택도 닫지만 방어용 갈래다 —
누를 때마다 그림이 새 요소라 브라우저에 풀 선택이 남지 않아 더블클릭은 빈 선택을 보내지 않는다.
범위 지문이 지금 범위와 다르면 지난 칸은 무시한다 — 다른 공정으로 따라가지 않는다. 누를 때마다
세대(`GAP_SHEET_GENERATION_KEY`)를 올려 그림 `layout.meta` 에 싣는다 — 그림 내용이 늘 새로워
브라우저가 지난 선택 상태를 들고 오지 않는다(같은 그림으로 되돌아오면 남은 선택 때문에 첫 누름이
선택 해제가 되거나 값이 같아 이벤트가 오지 않는다).

**분류별 내역은 설비 마스터의 컬럼으로 호기를 좁혀 더할 수 있다**(`호기 필터`, 2026-09-29 사용자
요청). 필터가 걸리면 설비 일정 기준 세 행은 걸린 호기만(실제·반사실 구간을 같은 호기로 좁힌다,
기존보유 제외) 다시 더하고, Static·GAP 여섯 행은 「—」 다 — 걸러진 설비 일정을 거르지 않은 Static
과 맞대면 GAP 이 거짓말을 한다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Collection, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.elements.lib.column_types import ColumnConfig
from streamlit.errors import StreamlitPageNotFoundError

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.availability_gap_figure import build_availability_gap_figure
from capa_simulation.components.availability_sheet_canvas import (
    GROUP_TITLES,
    SHEET_DIGITS,
    AvailabilitySheetCanvas,
    build_availability_sheet_canvas,
    reason_text,
    sheet_value_text,
)
from capa_simulation.components.availability_sheet_keys import (
    GAP_SHEET_CELL_KEY,
    GAP_SHEET_CHART_KEY,
    GAP_SHEET_CSV_KEY,
    GAP_SHEET_EVIDENCE_KEY,
    GAP_SHEET_FRAGMENT_KEY,
    GAP_SHEET_GENERATION_KEY,
    GAP_SHEET_LABEL_CANVAS_KEY,
    GAP_SHEET_LABEL_CHART_KEY,
    GAP_SHEET_MEMO_KEY,
    GAP_SHEET_MONTH_REGION_KEY,
    GAP_SHEET_SCROLL_KEY,
    GAP_SHEET_SCROLLBAR_KEY,
)
from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.month_sheet_canvas import EMPTY, canvas_point
from capa_simulation.components.plotly_layout import hover_chart_config, static_chart_config
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import theme, tokens
from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    NO_DEMAND_MESSAGE,
    bootstrap_error_message,
    prune_choice,
)
from capa_simulation.process_detail_state import FROM_GAP, FROM_PARAM, MONTH_PARAM, PROCESS_PARAM
from capa_simulation.services.availability_gap import GapComparison
from capa_simulation.services.availability_sheet import (
    BREAKDOWN_LENT_COLUMN,
    GAP_PAIRS,
    GAP_ROWS,
    KIND_BASELINE_LINE,
    KIND_UNIT_LINE,
    REASON_STATIC_UNREADABLE,
    REASON_UNIT_FILTER,
    ROW_GROUPS,
    ROW_ITEMS,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_LENT,
    ROW_STATIC_OWNED,
    SHEET_ROWS,
    STATIC_ROWS,
    AvailabilitySheet,
    SheetView,
    build_availability_sheet,
    downtime_without_loss,
    sheet_view,
    unit_availability_breakdown,
)
from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    EQUIPMENT_ID_COLUMN,
    INVESTMENT_CAPA_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_STATUS_COLUMN,
    STORAGE_FLAG_COLUMN,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.monthly_equipment_availability import (
    CATEGORIES,
    build_monthly_equipment_availability,
    processes_in,
    span_date_range,
)
from capa_simulation.services.process_cutoff import cutoff_lookup
from capa_simulation.services.simulation_cache import (
    DynamicMonthlyCacheKey,
    ScenarioCacheKey,
    SecurementCrossCheckCacheKey,
    availability_comparison_cache_key,
    availability_sheet_cache_key,
    dynamic_monthly_cache_key,
    get_availability_comparison,
    get_availability_sheet,
    get_monthly_equipment_contributions,
    get_securement_cross_check,
    get_undated_equipment,
    get_usage_excluded_equipment,
    securement_cross_check_result,
)
from capa_simulation.services.undated_equipment import undated_equipment_notice
from capa_simulation.services.usage_basis import usage_exclusion_notice
from capa_simulation.sidebar_status import rerun_app_unless_alone

__all__ = [
    "DETAIL_CATEGORY_KEY",
    "DETAIL_MODE_KEY",
    "PROCESS_FILTER_KEY",
    "RESULT_VIEW_KEY",
    "UNIT_FILTER_COLUMNS",
    "UNIT_FILTER_COLUMNS_KEY",
    "GapSheetBundle",
    "open_sheet_cell",
    "pick_gap_sheet_cell",
    "render_availability_gap_panel",
    "render_availability_sheet",
    "unit_filter_key",
]

PROCESS_FILTER_KEY = "equipment_gap_process_filter_v1"
RESULT_VIEW_KEY = "equipment_gap_result_view_v1"
DETAIL_MODE_KEY = "equipment_gap_detail_mode_v2"
DETAIL_CATEGORY_KEY = "equipment_gap_detail_category_v1"
UNIT_FILTER_COLUMNS_KEY = "equipment_gap_unit_filter_columns_v1"
_UNIT_FILTER_KEY_PREFIX = "equipment_gap_unit_filter_v1"
# 분류별 내역을 더할 호기를 좁히는 설비 마스터 컬럼. 공정(`공정소분류`)은 위 `공정` 이 맡는다.
# 날짜·좌표·환산비처럼 호기마다 다른 연속값은 고를 값이 아니라 뺀다.
UNIT_FILTER_COLUMNS = (
    "공정대분류",
    "공정구분",
    "투자구분",
    INVESTMENT_CAPA_COLUMN,
    "담당자",
    "Maker",
    "Model",
    AREA_CODE_COLUMN,
    "사용기준",
    "동",
    "층",
    ARRIVAL_STATUS_COLUMN,
    QUAL_STATUS_COLUMN,
    STORAGE_FLAG_COLUMN,
    "기존설비여부",
    PARENT_EQUIPMENT_COLUMN,
    EQUIPMENT_ID_COLUMN,
)
_ALL_PROCESSES = "전체 합계"
_RESULT_VIEWS = ("가용대수 비교", "분류별 내역", "확보율 교차검증")
_DETAIL_MODES = ("시트", "호기 목록")
_CATEGORY_NAMES = tuple(category.name for category in CATEGORIES)
# 목록의 대수 표시 자릿수. **값은 반올림하지 않는다** — 1/3 지분 셋을 0.333 으로 잘라 더하면
# 0.999 가 되어 「같은 칸을 더하면 표의 값」이 깨진다. CSV 도 반올림 없이 나간다.
_UNIT_NUMBER_FORMAT = {
    column: st.column_config.NumberColumn(format="%.3f")
    for column in ("대수", "환산대수", "보유", BREAKDOWN_LENT_COLUMN, "가용")
}
_UNIT_NUMBER_FORMAT["환산비"] = st.column_config.NumberColumn(format="%.2f")
# 확보율 교차검증 표의 화면 머리. 내부 컬럼은 그대로다.
_CROSS_CHECK_HEADERS = {
    "Dynamic가용대수": "일정기준가용대수",
    "Dynamic확보율": "일정기준확보율",
}
# 그림을 바꾸는 꼴이 바뀌면 올린다 — 세션에 남은 옛 그림을 쓰지 않는다.
_SHEET_SCHEMA_VERSION = 3
_SHEET_MEMO_LIMIT = 4
_TOTAL_ROW = "합계"


@dataclass(frozen=True, eq=False)
class GapSheetBundle:
    """시트 프래그먼트 인자 — 앱 전체 회차가 정한 범위·시트·근거 재료."""

    view: SheetView
    sheet: AvailabilitySheet
    process: str | None
    """고른 공정(원본). 전체 합계면 None."""

    process_label: str
    scope: frozenset[str]
    fingerprint: str
    """범위 지문 — 공정·달·호기 필터·시트 키. 고른 칸이 이 범위의 것인지 가린다."""

    schedule_detail: str
    contributions: Callable[[], tuple[pd.DataFrame, pd.DataFrame]]
    """(실제, 반사실) 호기별 기여 — 범위·호기 필터를 건 것. 누른 칸이 있을 때만 부른다."""

    labels: ProcessLabels
    conversion_ratios: Mapping[str, float] | None = None
    downtime: pd.DataFrame | None = None
    cutoff: pd.DataFrame | None = None
    unit_filtered: bool = False


def render_availability_gap_panel(
    *,
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: list[int],
    static_availability: pd.DataFrame | None,
    static_owned: pd.DataFrame | None = None,
    static_lent: pd.DataFrame | None = None,
    static_error: str | None = None,
    span_bounds: tuple[date, date] | None = None,
    conversion_ratios: Mapping[str, float] | None = None,
    required_equipment: pd.DataFrame | Callable[[], pd.DataFrame] | None = None,
    required_equipment_key: ScenarioCacheKey | None = None,
    no_demand_message: Callable[[], str] | None = None,
    owner_tab: OpenTab | None = None,
    conditions: DeltaGenerator | None = None,
    units: pd.DataFrame | None = None,
    process_labels: ProcessLabels | None = None,
    downtime: pd.DataFrame | None = None,
    counterfactual_spans: pd.DataFrame | Callable[[], pd.DataFrame] | None = None,
) -> None:
    """비교 탭 본문.

    `spans` 는 `build_equipment_lifecycle_spans` 의 결과다. **호출자는 그 구간을
    `span_date_range` 가 알려 주는 범위로 만들어 넘겨야 한다** — Cut-off 가 크면 그 달의
    W/D 구간이 앞으로 크게 밀려, 조회기간만큼만 만든 구간으로는 첫 달이 조용히 모자라게
    세어진다. 그 범위를 여기서도 다시 재어 어긋나면 알린다.
    숨은 탭은 계산과 렌더링을 건너뛰고, 두 선택값은 세션에 남긴다.

    Static 은 기준정보 세 표다 — `static_availability`(`RQ_EQP_AVBL`)·`static_owned`
    (`RQ_EQP_OWN`)·`static_lent`(`RQ_EQP_LENT`). 페이지는 세션 활성 저장 리비전에서 셋을 함께
    읽는다. `static_availability` 가 None 이면 Static 을 읽지 못한 것이다(시트의 Static·GAP 은
    「—」).

    `counterfactual_spans` 는 `spans` 와 같은 마스터·같은 범위에서 **비가동만 비운** 구간(또는
    그것을 꺼내는 로더)이다 — 비교 시트의 설비 일정 기준 보유·대여가 이것으로 나온다. 로더는 `분류별
    내역` 의 시트를 그리는 회차에만 부른다. 주지 않으면(마스터 없이 띄우는 테스트) `spans` 를 그대로
    쓴다 — 비가동이 없다고 보는 셈이라 대여가 0 이다. `downtime` 은 근거 카드의 `비가동 내역` 칸에만
    쓴다.

    거르는 조건(공정·호기 필터)은 `conditions`(사이드바 조건 카드)에 선다. 주지 않으면 본문 제자리에
    그린다 — 홀로 띄우는 테스트가 쓴다. `units` 는 `spans` 를 만든 설비 마스터이고, 주면 분류별
    내역에 `호기 필터` 가 선다. **무엇을 볼지 고르는 전환(조회 결과·표시)은 본문이다**
    — 탭 안의 하위 탭과 같은 것이라 카드에 넣으면 지금 어느 결과를 보는지 본문에서 사라진다
    (2026-09-29 사용자 결정). 읽는 법(Static·설비 일정 기준의 뜻, 9행)은 가용설비 현황 Guide 다.

    `process_labels` 는 **보이는 글자에만** 쓴다(2026-10-10 사용자 결정) — `공정` 선택지, 시트 머리,
    근거 카드·호기 목록·확보율 교차검증 표의 `공정` 칸. 선택값(세션)·범위 지문·CSV 는 원본이다.
    공정명이 맞지 않는 자리를 알리는 문구(두 쪽 공정명 경고, 한쪽에만 있는 공정의 까닭)도 원본이다 —
    설비 마스터·기준정보에서 고칠 이름이다(AGENTS 8장 ③). 계산 캐시에는 닿지 않는다.

    `required_equipment` 는 소요대수 프레임이거나 그것을 꺼내는 로더(인자 없는 함수)다. 페이지는
    로더(`simulation_cache.scenario_required_equipment`)를 넘긴다 — 소요대수는 확보율 교차검증에만
    들고, 그 보기에서도 캐시가 빗나갈 때만 푼다. `required_equipment_key` 는 그 소요대수를 낸
    시나리오 키다. 주면 확보율 교차검증을 (비교 키, 이 키)로 캐시한다(`get_securement_cross_check`).
    `no_demand_message` 는 조회기간에 소요대수가 없을 때의 안내를 만드는 함수다 — 페이지는
    `page_bootstrap.no_demand_message` 에 활성 상태를 묶어 넘겨 데이터 범위를 붙인다. 그 갈래에서만
    부른다. 주지 않으면 범위 없는 첫 문장(`NO_DEMAND_MESSAGE`)이다.
    """
    if tab_is_hidden(owner_tab):
        return
    labels = process_labels or ProcessLabels()
    controls = conditions if conditions is not None else nullcontext()

    st.markdown("#### :material/compare_arrows: Static · 설비 일정 기준 가용대수 비교")

    if cutoff.empty:
        st.info("공정별 Cut-off 를 먼저 적어야 설비 일정 기준 가용대수를 낼 수 있습니다.")
        return
    if not months:
        st.info("조회기간에 월이 없습니다.")
        return

    required = span_date_range(months, cutoff)
    if required is not None and span_bounds is not None and required[0] < span_bounds[0]:
        st.warning(
            f"Cut-off 때문에 {required[0]:%Y-%m-%d} 부터의 설비 상태가 필요한데 "
            f"조회기간이 {span_bounds[0]:%Y-%m-%d} 부터입니다. 첫 달이 모자라게 세어집니다 — "
            "조회기간의 시작일을 앞당기세요."
        )

    # **`or` 를 쓰지 않는다.** 프레임에 `or` 를 걸면 `__bool__` 이 불려
    # 「truth value of a DataFrame is ambiguous」로 죽는다. 빈 프레임도 거짓이라
    # 값이 있는 쪽에서만 터지는데, 그 경로가 곧 실제 화면이다.
    static = pd.DataFrame() if static_availability is None else static_availability
    owned = pd.DataFrame() if static_owned is None else static_owned
    lent = pd.DataFrame() if static_lent is None else static_lent
    # 월별 분해와 비교는 입력 전부의 내용 지문으로 캐시한다 — 조회 결과·공정·표시를 바꾸는 rerun 은
    # 결과를 고르기만 한다(2026-10-08 점검 A2).
    monthly_key = dynamic_monthly_cache_key(
        spans=spans,
        baseline=baseline,
        cutoff=cutoff,
        months=months,
        conversion_ratios=conversion_ratios,
    )
    comparison_key = availability_comparison_cache_key(monthly_key, static=static)
    monthly, comparison = get_availability_comparison(
        comparison_key,
        _spans=spans,
        _baseline=baseline,
        _cutoff=cutoff,
        _static=static,
        _conversion_ratios=conversion_ratios,
    )

    if static_error:
        st.warning(f"Static 가용대수를 읽지 못해 설비 일정 기준만 표시합니다 — {static_error}")

    _render_unmatched(comparison.dynamic_only, comparison.static_only, labels)

    # 두 전환(조회 결과 · 표시)은 한 줄에 나란히 선다. `표시` 는 분류별 내역에서만, 범위를 정한
    # 뒤에 이 줄로 들어온다 — 그 사이의 안내는 줄 아래에 남는다.
    switches = st.container(horizontal=True, vertical_alignment="bottom", gap="large")
    with switches:
        result_view = st.segmented_control(
            "조회 결과",
            options=_RESULT_VIEWS,
            default=_RESULT_VIEWS[0],
            required=True,
            key=RESULT_VIEW_KEY,
            persist_state="session",
        )
    # 값은 원본 공정명이고 글자만 표시명이다. 보이는 글자가 다른 공정이나 `전체 합계` 와 겹치면
    # 「표시명 (원본)」 으로 가른다 — 겹친 글자로는 고른 것과 다른 공정이 돌아오고, `전체 합계` 와
    # 겹치면 다음 회차의 기본값이 그 공정으로 바뀌었다(`unique_format_func`). 겹침은 조회 달과
    # 상관없는 이 탭의 공정 전체(설비·기존보유·Cut-off·Static)로 가른다 — 달을 옮겨 선택지가
    # 바뀌어도 글자가 덜 흔들린다. 차례는 보이는 글자의 가나다순(표시명이 없으면 지금처럼 원본
    # 순서)이고 `전체 합계` 는 맨 앞 그대로다.
    processes = set(comparison.rows["공정"].dropna().astype(str))
    known = processes | set(processes_in(spans, baseline))
    for frame in (cutoff, static):
        if "공정" in frame.columns:
            known |= set(frame["공정"].dropna().astype(str))
    process_format = labels.unique_format_func([_ALL_PROCESSES, *known], reserved=(_ALL_PROCESSES,))
    options = [
        _ALL_PROCESSES,
        *sorted(processes, key=lambda name: (process_format(name), name)),
    ]
    # 잡은 값을 매 회차 세션에 다시 적는다(없어졌으면 `전체 합계`). 적은 값만 브라우저에 가므로,
    # 보이는 글자가 바뀌는 회차에도 브라우저가 새 글자를 받아 옛 글자로 다른 공정을 되보내지 않는다
    # (2026-10-10 재검증). 지우지(`pop`) 않는다 — AGENTS 9장.
    prune_choice(PROCESS_FILTER_KEY, options, default=_ALL_PROCESSES)
    with controls:
        selected = st.selectbox(
            "공정",
            options=options,
            format_func=process_format,
            key=PROCESS_FILTER_KEY,
            persist_state="session",
        )
    process = None if selected == _ALL_PROCESSES else selected
    undated = _undated_rows(units)
    usage_excluded = _usage_excluded_rows(units)

    if result_view == "확보율 교차검증":
        _render_undated_notice(
            undated,
            usage_excluded,
            {process} if process is not None else set(monthly["공정"].astype(str)),
        )
        _render_securement_cross_check(
            monthly=monthly,
            static_availability=static,
            required_equipment=required_equipment,
            cache_key=(
                None if required_equipment_key is None else (comparison_key, required_equipment_key)
            ),
            process=process,
            labels=labels,
            no_demand_message=no_demand_message,
        )
        return

    if process is None:
        # **한쪽에만 있는 공정을 합계에서 뺀다.** 넣으면 「Cut-off 를 아직 안 적었다」가
        # 「수백 대 모자라다」로 읽힌다 — 경고 한 줄로는 그 인상을 못 지운다. 공정을
        # 직접 고르면 한쪽짜리도 있는 쪽 값은 보이므로 감추는 것이 아니다(GAP 만 없다).
        excluded = set(comparison.dynamic_only) | set(comparison.static_only)
        scope = processes - excluded
        if excluded:
            # 상자 글자가 이름과 다를 때만 그렇다고 적는다 — 표시명이 없으면 예전 문장 그대로다.
            relabelled = any(process_format(name) != name for name in excluded)
            st.caption(
                f"전체 합계에서 한쪽에만 있는 공정 {len(excluded)}개를 뺐습니다. "
                "그 공정은 조회 조건의 `공정` 에서 이름을 골라 따로 봅니다."
                + (" 상자에는 공정 표시명으로 보입니다." if relabelled else "")
            )
    else:
        scope = {process}
    if not scope:
        st.info("표시할 값이 없습니다.")
        return

    if not processes_in(spans, baseline):
        st.caption("설비 마스터와 기존보유대수가 모두 비어 있어 설비 일정 기준이 0 입니다.")

    static_blocked = REASON_STATIC_UNREADABLE if static_availability is None else None
    one_sided = _one_sided_reason(process, comparison, static_missing=static_blocked is not None)
    process_label = _ALL_PROCESSES if process is None else labels.label(process)

    def sheet_for(free_spans: pd.DataFrame | None) -> tuple[AvailabilitySheet, str]:
        free_key = (
            None
            if free_spans is None
            else dynamic_monthly_cache_key(
                spans=free_spans,
                baseline=baseline,
                cutoff=cutoff,
                months=months,
                conversion_ratios=conversion_ratios,
            )
        )
        key = availability_sheet_cache_key(
            monthly_key,
            free_key,
            static_owned=owned,
            static_lent=lent,
            static_available=static,
        )
        sheet = get_availability_sheet(
            key,
            _actual_monthly=monthly,
            _free_spans=free_spans,
            _baseline=baseline,
            _cutoff=cutoff,
            _conversion_ratios=conversion_ratios,
            _static_owned=owned,
            _static_lent=lent,
            _static_available=static,
        )
        return sheet, _key_digest(key)

    if result_view == "가용대수 비교":
        _render_undated_notice(undated, usage_excluded, scope)
        if one_sided is not None:
            # 그림은 Static 과 설비 일정 기준을 나란히 세우고 그 차이를 막대 위에 적는다. 한쪽이
            # 없으면 맞댈 것이 없다.
            st.info(f"{one_sided} 있는 쪽 값은 `분류별 내역` 에서 봅니다.")
            return
        # 그림은 가용만 쓴다 — 반사실 구간을 만들지 않는다(보유·대여가 빈 시트).
        bare, _ = sheet_for(None)
        st.plotly_chart(
            build_availability_gap_figure(
                sheet_view(bare, processes=scope, static_blocked=static_blocked)
            ),
            width="stretch",
            config=hover_chart_config(),
        )
        return

    with switches:
        detail_mode = st.segmented_control(
            "표시",
            options=_DETAIL_MODES,
            default=_DETAIL_MODES[0],
            required=True,
            key=DETAIL_MODE_KEY,
            persist_state="session",
        )
    if one_sided is not None:
        st.caption(f":material/info: {one_sided} 있는 쪽 값만 보입니다.")
    chosen_units: set[str] | None = None
    if units is not None:
        with controls:
            chosen_units, applied = _render_unit_filters(units, scope)
        if chosen_units is not None:
            # 무엇으로 걸렀는지는 본문에도 남긴다 — 카드가 접혀 있으면 표만 보고는 알 수 없다.
            st.caption(
                ":material/filter_alt: 호기 필터 · "
                + " · ".join(applied)
                + f" — 호기 {len(chosen_units):,}개만 더합니다. 기존보유는 호기 속성이 없어 "
                "빠지고, Static·GAP 은 공정 단위 기준정보라 맞대지 않습니다(—)."
            )
    _render_undated_notice(undated, usage_excluded, scope, chosen_units)
    if detail_mode == "호기 목록":
        _render_unit_list(
            _scoped_contributions(
                monthly_key, spans, baseline, cutoff, conversion_ratios, scope, chosen_units
            ),
            controls=controls,
            labels=labels,
        )
        return
    st.caption(
        "셋업 진행중·입고 예정·보관 같은 상태별 대수는 `표시` 를 「호기 목록」으로 바꿔 봅니다."
    )

    free_spans = _counterfactual(counterfactual_spans, spans)
    free_key = dynamic_monthly_cache_key(
        spans=free_spans,
        baseline=baseline,
        cutoff=cutoff,
        months=months,
        conversion_ratios=conversion_ratios,
    )
    if chosen_units is None:
        sheet, sheet_digest = sheet_for(free_spans)
        view = sheet_view(sheet, processes=scope, static_blocked=static_blocked)
    else:
        sheet = _unit_filtered_sheet(
            spans, free_spans, cutoff, months, conversion_ratios, chosen_units
        )
        sheet_digest = _key_digest(
            (monthly_key, free_key, tuple(sorted(chosen_units)), "unit-filter")
        )
        if not set(sheet.dynamic_processes) & scope:
            st.info("호기 필터에 든 호기가 조회기간에 더할 대수가 없습니다.")
            return
        view = sheet_view(sheet, processes=scope, static_blocked=REASON_UNIT_FILTER)

    def contributions() -> tuple[pd.DataFrame, pd.DataFrame]:
        return (
            _scoped_contributions(
                monthly_key, spans, baseline, cutoff, conversion_ratios, scope, chosen_units
            ),
            _scoped_contributions(
                free_key, free_spans, baseline, cutoff, conversion_ratios, scope, chosen_units
            ),
        )

    fingerprint = _key_digest((process, tuple(months), sheet_digest))
    render_availability_sheet(
        GapSheetBundle(
            view=view,
            sheet=sheet,
            process=process,
            process_label=process_label,
            scope=frozenset(scope),
            fingerprint=fingerprint,
            schedule_detail=_schedule_detail(process, cutoff),
            contributions=contributions,
            labels=labels,
            conversion_ratios=conversion_ratios,
            downtime=downtime,
            cutoff=cutoff,
            unit_filtered=chosen_units is not None,
        )
    )


def _counterfactual(
    source: pd.DataFrame | Callable[[], pd.DataFrame] | None, spans: pd.DataFrame
) -> pd.DataFrame:
    if source is None:
        return spans
    return source() if callable(source) else source


def _key_digest(key: object) -> str:
    return hashlib.sha1(repr(key).encode("utf-8")).hexdigest()[:16]


def _schedule_detail(process: str | None, cutoff: pd.DataFrame) -> str:
    """설비 일정 기준 제목의 세부 글 — 출처·축·Cut-off(라벨 칸 한 줄). 「칸을 누르면」 안내는
    시트 위 도구 줄과 풍선이 맡는다."""
    days = cutoff_lookup(cutoff).get(process) if process is not None else None
    production = f"Cut-off {days:g}일" if days is not None else "Cut-off 공정별"
    return f"설비 DB · 환산대수 · {production}"


# ================================================================== 시트 프래그먼트


@st.fragment(key=GAP_SHEET_FRAGMENT_KEY)
def render_availability_sheet(bundle: GapSheetBundle) -> None:
    """도구 줄(안내 · 시트 CSV) → 9행 캔버스 → 범례 → 근거 카드. 키 붙은 프래그먼트다.

    칸을 누르는 조작은 이것만 다시 돌린다 — 조건 카드에 설 위젯을 바꾸지 않는 본문 조작이다. 시트·
    호기별 기여(`bundle.contributions`, 누른 칸이 설비 일정 기준·GAP 일 때만 부른다)는 직전 앱 전체
    회차의 입력에서 나온다. 그 입력을 바꾸는 조작(조건 카드·조회 결과·표시·탭·저장)은 앱 전체 회차라
    새 인자로 다시 부른다.

    이벤트 칸에는 스타일만 든 `st.html` 셋(두 컬럼 폭·라벨 칸 위 여백·스크롤 상자)만 쓴다 — 칸을
    누른 회차·안 누른 회차, 안내 칸, 한쪽 공정, 호기 필터 모두 같은 셋이다. 토스트는 쓰지 않는다.
    """
    cell = open_sheet_cell(bundle)
    generation = int(st.session_state.get(GAP_SHEET_GENERATION_KEY, 0) or 0)
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.caption(
            "칸을 누르면 그 달·항목의 근거를 아래에 보여 줍니다. 같은 칸을 다시 누르면 닫힙니다.",
            width="stretch",
        )
        render_csv_download(
            data=_sheet_csv(bundle).encode("utf-8-sig"),
            file_name=f"Static_대비_일정_시트_{bundle.view.months[0]}_{bundle.view.months[-1]}.csv",
            key=GAP_SHEET_CSV_KEY,
            label="시트 CSV",
        )
    canvas = remembered_sheet_canvas(bundle, cell, generation)
    _render_canvas(bundle, canvas)
    st.html(sheet_legend_html())
    _render_evidence(bundle, cell)


def open_sheet_cell(bundle: GapSheetBundle) -> tuple[int, str] | None:
    """세션의 고른 칸이 이 범위의 것이면 (달, 행 id). 다른 범위·축 밖·모르는 행이면 None."""
    saved = st.session_state.get(GAP_SHEET_CELL_KEY)
    if not isinstance(saved, tuple) or len(saved) != 3:
        return None
    fingerprint, month, row = saved
    if fingerprint != bundle.fingerprint or month not in bundle.view.months:
        return None
    if row not in SHEET_ROWS:
        return None
    return int(month), str(row)


def pick_gap_sheet_cell(fingerprint: str, months: Sequence[int]) -> None:
    """월 그림의 칸 선택 콜백 — 누른 칸을 세션에 적는다. 이 프래그먼트 회차로 다시 그린다.

    같은 칸을 다시 누르면 닫는다(세션 칸을 비운다) — 닫는 길은 이것뿐이다. 빈 선택이 오면 그것도
    닫지만 방어용이다(브라우저는 보통 보내지 않는다 — 모듈 docstring). 머리·축 밖의 점은 무시한다.
    누를 때마다 세대를 올린다 — 다음 그림이 새 그림이라 브라우저에 지난 선택이 남지 않는다(모듈
    docstring).
    """
    point = canvas_point(st.session_state.get(GAP_SHEET_CHART_KEY))
    current = st.session_state.get(GAP_SHEET_CELL_KEY)
    if point is None:
        st.session_state[GAP_SHEET_CELL_KEY] = None
    elif point[0] in {int(month) for month in months} and point[1] in SHEET_ROWS:
        chosen = (fingerprint, int(point[0]), str(point[1]))
        st.session_state[GAP_SHEET_CELL_KEY] = None if current == chosen else chosen
    generation = int(st.session_state.get(GAP_SHEET_GENERATION_KEY, 0) or 0)
    st.session_state[GAP_SHEET_GENERATION_KEY] = generation + 1
    rerun_app_unless_alone(GAP_SHEET_CHART_KEY)


def remembered_sheet_canvas(
    bundle: GapSheetBundle, cell: tuple[int, str] | None, generation: int
) -> AvailabilitySheetCanvas:
    """시트 그림을 세션에 몇 벌 기억한다. 키는 그림을 바꾸는 것 전부 — 테마·범위 지문·머리 글자·
    고른 칸·세대. 새 `st.cache_data` 를 두지 않는다(CLAUDE.md 캐시 경계)."""
    key = (
        _SHEET_SCHEMA_VERSION,
        theme.current_mode(),
        bundle.fingerprint,
        bundle.process_label,
        bundle.schedule_detail,
        cell,
        generation,
    )
    memo = st.session_state.get(GAP_SHEET_MEMO_KEY)
    entries: list[tuple[tuple[object, ...], AvailabilitySheetCanvas]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key and isinstance(stored, AvailabilitySheetCanvas):
            return stored
    canvas = build_availability_sheet_canvas(
        view=bundle.view,
        process_label=bundle.process_label,
        schedule_detail=bundle.schedule_detail,
        selected=cell,
        generation=generation,
        scope=bundle.fingerprint,
    )
    entries = [entry for entry in entries if entry[0] != key][-(_SHEET_MEMO_LIMIT - 1) :]
    st.session_state[GAP_SHEET_MEMO_KEY] = [*entries, (key, canvas)]
    return canvas


def _render_canvas(bundle: GapSheetBundle, canvas: AvailabilitySheetCanvas) -> None:
    """HOME 틀 — 라벨 칸 260px(px 로 못박음) + 월 칸(스크롤 상자 하나, 위에 가로 스크롤바)."""
    count = len(bundle.view.months)
    visible = min(max(count, 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)
    st.html(
        split_scroll_columns_style(
            label_key=GAP_SHEET_LABEL_CANVAS_KEY,
            month_key=GAP_SHEET_MONTH_REGION_KEY,
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
        )
    )
    label_column, month_column = st.columns(
        [DASHBOARD_LABEL_COLUMN_WIDTH_PX, visible * tokens.MONTH_COLUMN_WIDTH_PX], gap=None
    )
    with label_column:
        with st.container(key=GAP_SHEET_LABEL_CANVAS_KEY, gap=None):
            st.plotly_chart(
                canvas.labels,
                width="stretch",
                key=GAP_SHEET_LABEL_CHART_KEY,
                config=static_chart_config(),
            )
    with month_column:
        # 라벨 칸은 월 칸 위에 얹힌 스크롤바 높이만큼 내려야 행이 맞는다(HOME 과 같은 값).
        st.html(
            f"<style>.st-key-{GAP_SHEET_LABEL_CANVAS_KEY} "
            f"{{ padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px; }}</style>"
        )
        with st.container(key=GAP_SHEET_MONTH_REGION_KEY, gap=None):
            # 시작 위치는 0 이다 — 누른 칸에 묶지 않는다(묶으면 누를 때마다 튄다).
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=f".st-key-{GAP_SHEET_SCROLL_KEY}_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key=GAP_SHEET_SCROLLBAR_KEY,
            )
            with horizontal_scroll_canvas(
                key=GAP_SHEET_SCROLL_KEY,
                content_width_px=count * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=None,
            ):
                # 선택을 켜면 그림 위 터치 스크롤이 막히므로 이 key 는 `app.py` 의 터치 스크롤 막이
                # 묶음에 들어 있다.
                st.plotly_chart(
                    canvas.months,
                    width="stretch",
                    key=GAP_SHEET_CHART_KEY,
                    config=hover_chart_config(),
                    on_select=partial(
                        pick_gap_sheet_cell, bundle.fingerprint, tuple(bundle.view.months)
                    ),
                    selection_mode="points",
                )


def sheet_legend_html() -> str:
    """시트 아래 범례 한 줄(서식 포함)."""
    swatch = "display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px"
    items = [
        f'<span style="{swatch};background:{tokens.SUMMARY_SUPPLY_SURFACE};border:1px solid '
        f'{tokens.BORDER}"></span>Static = 기준정보(공정 Capa 상세 ① 과 같은 면)',
        f'<span style="{swatch};border:2px solid {tokens.ACCENT}"></span>고른 칸',
        f'<span style="color:{tokens.DELTA_DECREASE};font-weight:700">−</span> 기준정보가 많음',
        f'<span style="color:{tokens.DELTA_INCREASE};font-weight:700">+</span> 설비 일정이 많음',
        "⚠ 기준정보 가용 ≠ 보유 + 대여",
        f'<span style="color:{tokens.TEXT_MUTED}">— 맞댈 수 없는 칸(올려 보면 까닭)</span>',
    ]
    body = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px">{item}</span>'
        for item in items
    )
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;'
        f'color:{tokens.TEXT_MUTED}">{body}</div>'
    )


def _sheet_csv(bundle: GapSheetBundle) -> str:
    """시트 CSV — 원본 공정명(전체 합계), 그룹·항목·YYYYMM…. 값은 반올림하지 않는다(「—」 는
    빈칸)."""
    view = bundle.view
    rows = []
    for row in SHEET_ROWS:
        record: dict[str, object] = {
            "공정": bundle.process if bundle.process is not None else _ALL_PROCESSES,
            "그룹": ROW_GROUPS[row],
            "항목": ROW_ITEMS[row],
        }
        for month in view.months:
            record[str(month)] = view.value(row, month)
        rows.append(record)
    return pd.DataFrame(rows).to_csv(index=False)


# ================================================================== 근거 카드


def _render_evidence(bundle: GapSheetBundle, cell: tuple[int, str] | None) -> None:
    with st.container(border=True, key=GAP_SHEET_EVIDENCE_KEY):
        if cell is None:
            st.markdown("**칸을 누르면 근거가 여기에 뜹니다**")
            st.caption(
                "설비 일정 기준 칸은 호기별로 보유 → 대여(비가동) → 가용이 어떻게 나왔는지, Static "
                "칸은 기준정보 출처를, GAP 칸은 두 값의 차이와 짝 호기를 보여 줍니다."
            )
            return
        month, row = cell
        group = ROW_GROUPS[row]
        st.markdown(
            f"##### {month_label(month)} · {group} {ROW_ITEMS[row]} · {bundle.process_label}"
        )
        if bundle.view.value(row, month) is None:
            reason = reason_text(bundle.view.reason(row, month)) or "맞댈 값이 없습니다"
            st.info(f"{reason}.")
            return
        if row in STATIC_ROWS:
            _render_static_evidence(bundle, month, row)
        elif row in GAP_ROWS:
            _render_gap_evidence(bundle, month, row)
        else:
            _render_schedule_evidence(bundle, month, row)


def _text(row: str, value: float | None) -> str:
    return sheet_value_text(row, value, SHEET_DIGITS)


def _render_static_evidence(bundle: GapSheetBundle, month: int, row: str) -> None:
    view = bundle.view
    owned = view.value(ROW_STATIC_OWNED, month)
    lent = view.value(ROW_STATIC_LENT, month)
    available = view.value(ROW_STATIC_AVAILABLE, month)
    st.markdown(
        f"보유 {_text(ROW_STATIC_OWNED, owned)} + 대여 {_text(ROW_STATIC_LENT, lent)} = "
        f"{_text(ROW_STATIC_OWNED, (owned or 0.0) + (lent or 0.0))} · 기준정보 가용 "
        f"{_text(ROW_STATIC_AVAILABLE, available)}"
    )
    if month in view.mismatch:
        st.warning(
            "⚠ 기준정보 가용이 보유 + 대여와 다릅니다 — 기준 정보 화면에서 세 표를 따로 고친 "
            "달입니다.",
            icon=":material/warning:",
        )
    st.caption(
        "Static 은 기준정보라 호기 목록이 없습니다. 출처: RQ_EQP_OWN(설비보유) · RQ_EQP_LENT"
        "(설비대여평가) · RQ_EQP_AVBL(가용대수), 세션 활성 시나리오의 저장 리비전. 고치는 곳: "
        "「기준 정보」 화면의 설비대수 표. 대여는 DB 의 양수 값에 − 를 붙여 보입니다."
    )
    if bundle.process is None:
        _card_table(bundle, _per_process(bundle, month, [*STATIC_ROWS], sort_by=row))


def _render_gap_evidence(bundle: GapSheetBundle, month: int, row: str) -> None:
    view = bundle.view
    schedule, static = GAP_PAIRS[row]
    st.markdown(
        f"GAP {ROW_ITEMS[row]} = 설비 일정 {_text(schedule, view.value(schedule, month))} − "
        f"Static {_text(static, view.value(static, month))} = {_text(row, view.value(row, month))}"
    )
    gap = view.value(row, month) or 0.0
    st.caption(
        "음수: 기준정보(약속)가 설비 일정보다 많습니다."
        if round(gap, 9) < 0
        else (
            "양수: 설비 일정이 기준정보보다 많습니다." if round(gap, 9) > 0 else "두 값이 같습니다."
        )
    )
    if bundle.process is None:
        _card_table(bundle, _per_process(bundle, month, [schedule, static], sort_by=row, gap=row))
    st.caption(f"아래는 짝 칸 「{GROUP_TITLES['sched']} {ROW_ITEMS[schedule]}」의 호기입니다.")
    _render_schedule_evidence(bundle, month, schedule, with_formula=False)


def _per_process(
    bundle: GapSheetBundle,
    month: int,
    rows: Sequence[str],
    *,
    sort_by: str,
    gap: str | None = None,
) -> pd.DataFrame:
    """전체 합계의 그 달 공정별 값(원본 공정명 — 화면에 얹을 때 표시명을 입힌다). |값| 큰 차례."""
    table = bundle.sheet.rows.loc[
        bundle.sheet.rows["생산계획년월"].eq(month)
        & bundle.sheet.rows["공정"].astype(str).isin(bundle.scope)
    ]
    shown = pd.DataFrame({"공정": table["공정"].astype(str).to_numpy()})
    names: list[str] = []
    for row in rows:
        name = f"{ROW_GROUPS[row]} {ROW_ITEMS[row]}"
        shown[name] = table[row].to_numpy()
        names.append(name)
    key = names[-1] if gap is None else f"GAP {ROW_ITEMS[gap]}"
    if gap is not None:
        shown[key] = shown[names[0]] - shown[names[1]]
    elif sort_by in rows:
        key = f"{ROW_GROUPS[sort_by]} {ROW_ITEMS[sort_by]}"
    order = shown[key].abs().sort_values(ascending=False, kind="stable").index
    return shown.loc[order].reset_index(drop=True)


def _render_schedule_evidence(
    bundle: GapSheetBundle, month: int, row: str, *, with_formula: bool = True
) -> None:
    view = bundle.view
    actual, free = bundle.contributions()
    actual = actual.loc[actual["생산계획년월"].eq(month)]
    free = free.loc[free["생산계획년월"].eq(month)]
    lines = unit_availability_breakdown(
        actual,
        free,
        conversion_ratios=bundle.conversion_ratios,
        downtime=bundle.downtime,
        cutoff=bundle.cutoff,
    )
    units = int(lines["구분"].eq(KIND_UNIT_LINE).sum())
    baseline_lines = int(lines["구분"].eq(KIND_BASELINE_LINE).sum())
    if with_formula:
        available, owned, lent = (
            _text(row_id, view.value(row_id, month))
            for row_id in (ROW_SCHEDULE_AVAILABLE, ROW_SCHEDULE_OWNED, ROW_SCHEDULE_LENT)
        )
        st.markdown(
            f"설비 일정 기준 가용 {available} = 보유 {owned} + 대여(비가동) {lent} · "
            f"호기 {units:,} · 기존보유 {baseline_lines}줄"
        )
    shown = _schedule_lines(lines, row, with_process=bundle.process is None)
    if shown.empty:
        st.caption(
            "이 칸에 기여한 호기가 없습니다."
            + (" 이 달에는 가용을 깎은 비가동이 없습니다." if row == ROW_SCHEDULE_LENT else "")
        )
    else:
        _card_table(bundle, shown, column_config=_UNIT_NUMBER_FORMAT)
    notes: list[str] = []
    idle = downtime_without_loss(actual, lines)
    if not idle.empty:
        names = ", ".join(str(name) for name in idle["설비명"].head(6))
        more = " …" if len(idle) > 6 else ""
        notes.append(
            f"참고: 가용을 깎지 않은 비가동 {len(idle)}호기({names}{more} — 셋업 중·보관처럼 "
            "원래 가용이 아니던 날). 대여(비가동)에 넣지 않습니다 — `호기 목록` 의 "
            "`운영 비가동` 에는 듭니다."
        )
    notes.append(
        "정지·반출/이설은 대여가 아니라 보유 자체를 줄입니다(그날부터 뺌). `손실 기여일수` 는 "
        "정지·반출/이설일에 닿는 비가동을 그날부터 세어 `비가동 내역` 보다 하루 길 수 있습니다."
    )
    if bundle.unit_filtered:
        notes.append("호기 필터 중이라 기존보유는 들지 않습니다.")
    for note in notes:
        st.caption(note)
    if bundle.process is not None:
        _render_detail_link(bundle.process, month)


def _card_table(
    bundle: GapSheetBundle,
    table: pd.DataFrame,
    *,
    column_config: Mapping[str, ColumnConfig] | None = None,
) -> None:
    """근거 카드의 표 하나. 값이 없는 칸(기존보유 줄의 환산비·일수, 합계 줄의 일수)은 「—」 다 —
    Streamlit 은 빈 값을 흐린 「None」 으로 적는다(`placeholder`). 숫자 칸은 표시만 세 자리이고 값은
    그대로다(1/3 지분 셋이 합에서 0.999 가 되지 않게). 설정이 없으면 `공정` 밖의 칸을 모두 그렇게
    적는다(공정별 표)."""
    config: dict[str, ColumnConfig] = (
        dict(column_config)
        if column_config is not None
        else {
            str(column): st.column_config.NumberColumn(format="%.3f")
            for column in table.columns
            if column != "공정"
        }
    )
    st.dataframe(
        bundle.labels.frame(table),
        hide_index=True,
        width="stretch",
        column_config=config,
        placeholder=EMPTY,
    )


def _schedule_lines(lines: pd.DataFrame, row: str, *, with_process: bool = True) -> pd.DataFrame:
    """누른 칸에 보일 호기 줄과 맨 아래 합계 줄. 칸 차례는 행마다 다르다. `공정` 칸은 여러 공정을
    더한 전체 합계에서만 싣는다(`with_process`)."""
    if row == ROW_SCHEDULE_OWNED:
        chosen = lines.loc[lines["보유"].gt(0)]
        columns = ["공정", "구분", EQUIPMENT_ID_COLUMN, "환산비", "구간일수"]
        columns += ["비가동 없음 기여일수", "보유"]
    elif row == ROW_SCHEDULE_LENT:
        chosen = lines.loc[lines[BREAKDOWN_LENT_COLUMN].lt(0)]
        columns = ["공정", EQUIPMENT_ID_COLUMN, "환산비", "비가동 내역", "손실 기여일수"]
        columns += [BREAKDOWN_LENT_COLUMN]
    else:
        chosen = lines.loc[lines["보유"].gt(0)].copy()
        # 대여가 있는 호기를 위에 둔다(기존보유 줄이 맨 앞). 다 깎여 가용 0 인 호기도 남긴다.
        chosen["_order"] = chosen["구분"].eq(KIND_UNIT_LINE).astype(int)
        chosen = chosen.sort_values(["_order", BREAKDOWN_LENT_COLUMN], kind="stable").drop(
            columns="_order"
        )
        columns = ["공정", "구분", EQUIPMENT_ID_COLUMN, "환산비", "비가동 없음 기여일수"]
        columns += ["손실 기여일수", "실제 기여일수", "보유", BREAKDOWN_LENT_COLUMN, "가용"]
        columns += ["비가동 내역"]
    if not with_process:
        columns.remove("공정")
    if chosen.empty:
        return pd.DataFrame()
    table = chosen.copy()
    baseline = table["구분"].eq(KIND_BASELINE_LINE)
    table[EQUIPMENT_ID_COLUMN] = (
        table[EQUIPMENT_ID_COLUMN]
        .astype("object")
        .where(~baseline, "기존보유 · " + table["기존보유분류"].astype("string").fillna("전체"))
    )
    modules = table["설비키"].notna() & table["설비키"].ne(table[EQUIPMENT_ID_COLUMN])
    if bool(modules.any()):
        table = table.rename(columns={"설비키": "설비"})
        columns.insert(columns.index(EQUIPMENT_ID_COLUMN) + 1, "설비")
    shown = table.loc[:, columns].reset_index(drop=True)
    # 합계 줄은 값 칸 셋만 채운다. 나머지는 빈 값이라 표에 「—」(`_card_table` 의 `placeholder`)로
    # 적힌다 — 시안의 합계 줄과 같다.
    total: dict[str, object] = dict.fromkeys(columns)
    total["구분" if "구분" in columns else EQUIPMENT_ID_COLUMN] = _TOTAL_ROW
    for column in ("보유", BREAKDOWN_LENT_COLUMN, "가용"):
        if column in columns:
            total[column] = float(shown[column].sum())
    # 합계 줄을 표와 같은 칸 타입으로 만들어 잇는다 — 빈 칸이 많은 한 줄이 칸 타입을 흔들지 않게.
    # 정수 칸은 빈 값을 담는 `Int64` 로 맞춘다(합계 줄의 일수는 비운다).
    dtypes = {
        str(column): "Int64" if pd.api.types.is_integer_dtype(dtype) else dtype
        for column, dtype in shown.dtypes.items()
    }
    total_row = pd.DataFrame([total], columns=columns).astype(dtypes)
    return pd.concat([shown.astype(dtypes), total_row], ignore_index=True)


def _render_detail_link(process: str, month: int) -> None:
    """공정 Capa 상세 ④(비가동 화살표)로 — 그 공정·그 달로 연다(주소 인자). `from=gap` 이라 상세
    화면이 ④ 를 접어 두었어도 다시 편다."""
    params = {PROCESS_PARAM: process, MONTH_PARAM: str(month), FROM_PARAM: FROM_GAP}
    current_theme = st.query_params.get(THEME_QUERY_PARAM)
    if current_theme:
        params[THEME_QUERY_PARAM] = current_theme
    try:
        st.page_link(
            PROCESS_CAPA_DETAIL.path,
            label="공정 Capa 상세 ④ 에서 비가동 화살표로 보기",
            icon=":material/troubleshoot:",
            query_params=params,
        )
    except StreamlitPageNotFoundError:
        st.caption("사이드바의 공정 Capa 상세 ④ 에서 비가동 화살표로 봅니다.")


# ================================================================== 둘레


def _undated_rows(units: pd.DataFrame | None) -> pd.DataFrame | None:
    """일정(반입·Qual)이 비어 설비 일정 기준에 들지 못하는 신규 호기. 표가 없거나 못 읽으면
    `None`."""
    if units is None:
        return None
    try:
        return get_undated_equipment(units)
    except ValueError:
        return None


def _usage_excluded_rows(units: pd.DataFrame | None) -> pd.DataFrame | None:
    """사용기준이 HBM·EDP 가 아니어서 세지 않는 호기. 표가 없거나 못 읽으면 `None`."""
    if units is None:
        return None
    try:
        return get_usage_excluded_equipment(units)
    except ValueError:
        return None


def _render_undated_notice(
    undated: pd.DataFrame | None,
    excluded: pd.DataFrame | None,
    scope: Collection[str],
    chosen_units: Collection[str] | None = None,
) -> None:
    """둘러싼 대수와 같은 범위(공정, 호기 필터)의 일정 미정·사용기준 제외 설비 한 줄씩.

    0대인 줄은 그리지 않는다.
    """
    if undated is not None:
        notice = undated_equipment_notice(undated, processes=scope, unit_ids=chosen_units)
        if notice is not None:
            st.caption(f":material/event_busy: {notice}")
    if excluded is not None:
        usage = usage_exclusion_notice(excluded, processes=scope, unit_ids=chosen_units)
        if usage is not None:
            st.caption(f":material/filter_alt_off: {usage}")


def _scoped_contributions(
    monthly_key: DynamicMonthlyCacheKey,
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    conversion_ratios: Mapping[str, float] | None,
    scope: Collection[str],
    chosen_units: set[str] | None = None,
) -> pd.DataFrame:
    """범위의 호기별 기여. 목록·근거 카드를 볼 때만 만든다 — 시트만 보면 들지 않는 비용이다.

    기여 줄 전체는 월별과 같은 키(`monthly_key`, 달이 그 안에 있다)로 캐시하고 범위는 여기서
    좁힌다. `chosen_units` 가 있으면 그 호기만 남긴다. 기존보유 줄은 `설비명` 이 비어 함께 빠진다
    — 호기 필터를 건 시트(`_unit_filtered_sheet`)와 같은 범위다.
    """
    contributions = get_monthly_equipment_contributions(
        monthly_key,
        _spans=spans,
        _baseline=baseline,
        _cutoff=cutoff,
        _conversion_ratios=conversion_ratios,
    )
    kept = contributions["공정"].astype(str).isin(list(scope))
    if chosen_units is not None:
        kept &= contributions[EQUIPMENT_ID_COLUMN].isin(chosen_units).fillna(False).astype(bool)
    return contributions.loc[kept].reset_index(drop=True)


def unit_filter_key(column: str) -> str:
    """호기 필터 한 컬럼의 값 선택 칸."""
    return f"{_UNIT_FILTER_KEY_PREFIX}_{column}"


def _text_values(values: pd.Series) -> pd.Series:
    """필터가 대조하는 문자열. 설비 마스터는 자유 텍스트라 앞뒤 공백을 떼고 빈 칸은 값이 없다."""
    text = values.astype("string").str.strip()
    return text.mask(text.eq(""))


def _reset_unit_filters(columns: Sequence[str]) -> None:
    st.session_state[UNIT_FILTER_COLUMNS_KEY] = []
    for column in columns:
        st.session_state[unit_filter_key(column)] = []


def _drop_unchosen_values(columns: Sequence[str]) -> None:
    # 컬럼을 빼면 그 컬럼의 값 선택도 버린다. 남기면 다시 고를 때 잊은 조건이 되살아난다.
    chosen = st.session_state.get(UNIT_FILTER_COLUMNS_KEY) or []
    for column in columns:
        if column not in chosen:
            st.session_state[unit_filter_key(column)] = []


def _render_unit_filters(
    units: pd.DataFrame, scope: Collection[str]
) -> tuple[set[str] | None, list[str]]:
    """분류별 내역을 더할 호기를 설비 마스터의 컬럼으로 좁힌다. 걸린 값이 없으면 `None`.

    컬럼을 먼저 고르고 그 컬럼의 값만 세운다 — 열일곱 컬럼을 다 세우면 사이드바가 필터로
    덮인다. 값 목록은 지금 범위(공정)의 호기에서 나오되, 이미 고른 값은 범위를 옮겨도 남긴다
    (다른 공정을 봤다 돌아와도 선택이 그대로다). 설비 마스터에 없는 값만 떨군다.
    """
    columns = [column for column in UNIT_FILTER_COLUMNS if column in units.columns]
    present = {column: _text_values(units[column]) for column in columns}
    offered = [column for column in columns if present[column].notna().any()]
    saved_columns = st.session_state.get(UNIT_FILTER_COLUMNS_KEY)
    if isinstance(saved_columns, list):
        st.session_state[UNIT_FILTER_COLUMNS_KEY] = [
            column for column in saved_columns if column in offered
        ]
    st.markdown("**호기 필터**")
    chosen_columns = st.multiselect(
        "필터할 컬럼",
        options=offered,
        key=UNIT_FILTER_COLUMNS_KEY,
        persist_state="session",
        placeholder="컬럼 선택 · 공정구분·Model·동 …",
        on_change=_drop_unchosen_values,
        args=(columns,),
    )
    if not chosen_columns:
        return None, []
    in_scope = (
        _text_values(units["공정소분류"]).isin(list(scope)).fillna(False).astype(bool)
        if "공정소분류" in units.columns
        else pd.Series(False, index=units.index)
    )
    kept = pd.Series(True, index=units.index)
    applied: list[str] = []
    for column in chosen_columns:
        key = unit_filter_key(column)
        known = set(present[column].dropna())
        saved = st.session_state.get(key)
        selected_before = (
            [value for value in saved if value in known] if isinstance(saved, list) else []
        )
        st.session_state[key] = selected_before
        options = list(
            dict.fromkeys([*sorted(present[column].loc[in_scope].dropna()), *selected_before])
        )
        selected = st.multiselect(
            column,
            options=options,
            key=key,
            persist_state="session",
            placeholder="전체",
            select_all=True,
        )
        if selected:
            kept &= present[column].isin(selected).fillna(False).astype(bool)
            applied.append(f"{column}: {', '.join(selected)}")
    st.button(
        "호기 필터 초기화",
        icon=":material/filter_alt_off:",
        key="equipment_gap_unit_filter_reset_v1",
        width="stretch",
        on_click=_reset_unit_filters,
        args=(columns,),
    )
    if not applied:
        return None, []
    # 공정 범위 안의 호기만 돌려준다. 시트는 어차피 범위로 다시 좁히지만, 본문 캡션이 이 수를
    # 「호기 N개만 더합니다」로 적는다 — 범위 밖 호기까지 세면 그 수가 시트와 어긋났다(2026-10-01).
    unit_ids = _text_values(units[EQUIPMENT_ID_COLUMN]).loc[kept & in_scope]
    return set(unit_ids.dropna()), applied


def _unit_filtered_sheet(
    spans: pd.DataFrame,
    free_spans: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: list[int],
    conversion_ratios: Mapping[str, float] | None,
    chosen_units: set[str],
) -> AvailabilitySheet:
    """호기 필터에 든 호기만 다시 더한 시트 — 실제·반사실 구간을 같은 호기로 좁힌다.

    시트와 같은 길(`build_monthly_equipment_availability` → `build_availability_sheet`)을 걷되
    기존보유와 Static 을 넣지 않는다. 필터를 건 회차에만 돌고 캐시하지 않는다. Static·GAP 은 화면이
    `REASON_UNIT_FILTER` 로 비운다.
    """

    def chosen(frame: pd.DataFrame) -> pd.DataFrame:
        ids = _text_values(frame[EQUIPMENT_ID_COLUMN])
        return frame.loc[ids.isin(chosen_units).fillna(False).astype(bool)]

    empty = pd.DataFrame()
    actual, free = (
        build_monthly_equipment_availability(
            chosen(frame), empty, cutoff, months, conversion_ratios=conversion_ratios
        )
        for frame in (spans, free_spans)
    )
    return build_availability_sheet(actual, free, None, None, None, months)


def _one_sided_reason(
    process: str | None, comparison: GapComparison, *, static_missing: bool = False
) -> str | None:
    """고른 공정이 한쪽에만 있으면 GAP 이 없는 까닭 한 문장. 양쪽에 다 있거나 전체 합계면 `None`.

    서비스가 한쪽짜리 공정의 GAP 을 내지 않는다(`services/availability_sheet`). 화면은 GAP 이
    **왜** 없는지를 말한다 — 말하지 않으면 「차이 없음」이나 「계산 누락」으로 읽힌다. Static 을
    아예 못 읽었으면 모든 공정이 설비 쪽에만 있게 되므로 그 까닭을 따로 적는다.
    """
    if process is None:
        return None
    if static_missing:
        return f"Static 을 읽지 못해 「{process}」 공정의 GAP 을 내지 않습니다."
    if process in comparison.dynamic_only:
        return f"「{process}」 공정은 기준정보(Static)에 없어 GAP 을 내지 않습니다."
    if process in comparison.static_only:
        return (
            f"「{process}」 공정은 설비 일정 기준이 나오지 않아(Cut-off·설비 없음) GAP 을 내지 "
            "않습니다."
        )
    return None


def _unit_table(rows: pd.DataFrame, *, with_month: bool) -> pd.DataFrame:
    """화면에 얹는 호기 목록. 기존보유 줄은 호기 자리에 그 분류를 적는다.

    설비키는 모듈 행이 있을 때만 보인다(비모듈은 호기와 같은 값이라 칸만 는다).
    """
    table = rows.copy()
    is_baseline = table[EQUIPMENT_ID_COLUMN].isna()
    table[EQUIPMENT_ID_COLUMN] = (
        table[EQUIPMENT_ID_COLUMN]
        .astype("string")
        .mask(is_baseline, "기존보유 · " + table["기존보유분류"].astype("string").fillna("전체"))
    )
    columns = ["공정", "분류", EQUIPMENT_ID_COLUMN]
    if bool(
        table["설비키"].notna().any()
        and table["설비키"].ne(rows[EQUIPMENT_ID_COLUMN]).fillna(False).any()
    ):
        table = table.rename(columns={"설비키": "설비"})
        columns.append("설비")
    columns += ["기여일수", "구간일수", "대수", "환산대수"]
    if with_month:
        table.insert(0, "월", table["생산계획년월"].map(lambda month: month_label(int(month))))
        columns.insert(0, "월")
    return table.loc[:, columns]


def _render_unit_list(
    contributions: pd.DataFrame,
    *,
    controls: AbstractContextManager[object],
    labels: ProcessLabels,
) -> None:
    """같은 조건의 호기별 기여(호기 상태 분류)를 긴 표 하나로. 분류로 좁히고 CSV 로 내려받는다.

    화면 표의 `공정` 은 표시명이고 CSV 는 원본이다 — 화면 프레임과 CSV 프레임을 나눈다(AGENTS 8장).
    """
    if contributions.empty:
        st.info("표시할 호기가 없습니다.")
        return
    st.caption(
        "분류는 호기 상태 기준이라 `운영 비가동` 은 시트의 대여(비가동)와 다를 수 있습니다 — "
        "셋업 중·보관 호기의 비가동도 듭니다. 대수(몇 대) 축은 이 목록의 `대수` 칸, 시트·확보율의 "
        "축은 `환산대수` 칸입니다."
    )
    present = [name for name in _CATEGORY_NAMES if name in set(contributions["분류"].astype(str))]
    with controls:
        chosen = st.multiselect(
            "분류",
            options=present,
            placeholder="전체 분류",
            key=DETAIL_CATEGORY_KEY,
            persist_state="session",
        )
    rows = contributions.loc[contributions["분류"].isin(chosen)] if chosen else contributions
    table = _unit_table(rows, with_month=True)
    st.dataframe(
        labels.frame(table), hide_index=True, width="stretch", column_config=_UNIT_NUMBER_FORMAT
    )
    months = sorted(int(month) for month in rows["생산계획년월"].unique())
    stamp = f"{months[0]}_{months[-1]}" if months else "empty"
    render_csv_download(
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"일정기준_가용대수_호기목록_{stamp}.csv",
        key="download_equipment_gap_unit_list_csv",
    )


def _render_securement_cross_check(
    *,
    monthly: pd.DataFrame,
    static_availability: pd.DataFrame,
    required_equipment: pd.DataFrame | Callable[[], pd.DataFrame] | None,
    cache_key: SecurementCrossCheckCacheKey | None,
    process: str | None,
    labels: ProcessLabels,
    no_demand_message: Callable[[], str] | None = None,
) -> None:
    """같은 소요대수에 두 가용대수를 각각 나눈 확보율.

    **HOME·B/N 은 그대로 Static 을 본다.** 여기는 기준정보 값을 교차검증하는 자리이고,
    값이 믿을 만해지고 Cut-off 가 채워진 뒤에 전역 전환을 정한다. 전환하려면 먼저 HOME 계산 캐시
    키에 설비 DB·Cut-off 지문을 넣고, Cut-off 를 적지 않은 공정에서 멈추지 않게 해야 한다.

    소요대수가 로더면 캐시가 빗나갈 때만 부른다. 소요대수가 비었는지·Static 이 비었는지도 그
    결과(`SecurementCrossCheckResult`)가 말한다 — 프레임을 풀지 않고 같은 차례로 안내한다.
    소요대수가 없음(`None`, 읽지 못함)과 비었음(조회기간에 없음)은 문구가 갈린다 — 빈 쪽은 다른
    계산 화면과 같은 「선택 범위에 소요대수 산출 기준이 없습니다.」 이고 `no_demand_message` 가
    있으면 데이터 범위를 붙인다. 맞대지 못했거나 로더가 멈추면(`BOOTSTRAP_ERRORS`) 이 보기 안에서
    경고로 알린다. 표 머리의
    `Dynamic가용대수`·`Dynamic확보율` 은 보일 때만 「일정기준…」 으로 바꾼다(내부 컬럼 그대로).
    """
    st.markdown("##### :material/fact_check: 확보율 교차검증")
    if required_equipment is None:
        st.info("소요대수를 읽지 못해 확보율을 맞댈 수 없습니다.")
        return
    load = required_equipment if callable(required_equipment) else _frame_loader(required_equipment)

    try:
        result = (
            securement_cross_check_result(static_availability, monthly, load())
            if cache_key is None
            else get_securement_cross_check(
                cache_key,
                _monthly=monthly,
                _static=static_availability,
                _required_equipment=load,
            )
        )
    except BOOTSTRAP_ERRORS as exc:
        # 맞대기(`KeyError`·`ValueError`)뿐 아니라 로더의 실패도 받는다 — 페이지의 오류 확인이
        # 적중한 뒤 밀려난 소요대수를 다시 꺼내다 멈춘 자리다.
        st.warning(f"확보율을 맞대지 못했습니다 — {bootstrap_error_message(exc)}")
        return
    if not result.has_demand:
        # 읽었지만 조회기간에 소요대수가 없다 — 읽기 실패(위 `None` 갈래)처럼 알리면 DB·시나리오가
        # 깨진 것으로 읽힌다. 다른 계산 화면처럼 옮겨 갈 데이터 범위를 알린다.
        st.info(NO_DEMAND_MESSAGE if no_demand_message is None else no_demand_message())
        return
    check = result.check
    if check is None:
        st.info("Static 가용대수가 없어 맞댈 대상이 없습니다.")
        return

    if check.months:
        st.caption(
            f"맞대어 본 달: {month_label(check.months[0])} ~ {month_label(check.months[-1])} "
            f"({len(check.months)}개월). **설비 조회기간이 덮는 달로 좁혔습니다** — "
            "시나리오 조회기간이 더 넓어도 그 달의 설비 상태를 만들지 않았으면 맞댈 수 "
            "없습니다. 조회기간을 넓히면 늘어납니다."
        )
    if check.fallback_processes:
        st.caption(
            f"Cut-off 가 없어 Static 값으로 채운 공정 {len(check.fallback_processes)}개는 "
            "**차이가 늘 0** 입니다 — 맞대어 본 것이 아니라 같은 값을 두 번 본 자리입니다. "
            f"실제로 비교한 공정은 {len(check.compared_processes)}개입니다."
        )
    # 기준정보에 없는 공정은 소요대수·Static 이 없어 행이 없다(서비스가 뺀다, 2026-10-01).
    if check.dynamic_only_processes:
        st.caption(
            f"기준정보(Static)에 없는 공정 {len(check.dynamic_only_processes)}개는 소요대수·"
            "Static 가용대수가 없어 맞대지 않았습니다 — 공정명은 위 경고를 봅니다."
        )
    if process is not None and process in check.dynamic_only_processes:
        st.info(f"「{process}」 공정은 기준정보(Static)에 없어 확보율을 맞대지 않습니다.")
        return

    rows = check.rows
    if process is not None:
        rows = rows.loc[rows["공정"] == process]
    # 채운 자리는 비교가 아니므로 기본으로 감춘다. 위 캡션이 개수를 이미 알린다.
    compared = rows.loc[~rows["Static대체"]]
    if compared.empty:
        # Cut-off 를 다 적어도 공정명이 기준정보와 다르면 비어 있다 — 그때는 이름이 까닭이다.
        remedy = (
            "Cut-off 를 적고 공정명을 기준정보와 맞추면"
            if check.dynamic_only_processes
            else "Cut-off 를 적으면"
        )
        st.info(f"아직 맞대어 볼 수 있는 공정이 없습니다. {remedy} 여기에 나타납니다.")
        return

    # **확보율 두 값을 같이 보인다.** 차이만 보이면 「29.5 차이」가 무슨 뜻인지 알 수 없다 —
    # 확보율은 비율이라 소요대수가 작은 공정에서 차이가 크게 나온다.
    display = compared.loc[
        :,
        [
            "생산계획년월",
            "공정",
            "소요대수",
            "Static가용대수",
            "Dynamic가용대수",
            "Static확보율",
            "Dynamic확보율",
            "확보율차이",
        ],
    ].copy()
    display["생산계획년월"] = display["생산계획년월"].map(lambda month: month_label(int(month)))
    display = display.rename(columns=_CROSS_CHECK_HEADERS)
    st.dataframe(labels.frame(display.round(3)), hide_index=True, width="stretch")


def _frame_loader(frame: pd.DataFrame) -> Callable[[], pd.DataFrame]:
    """이미 있는 소요대수 프레임을 로더 꼴로 감싼다(홀로 띄우는 자리)."""
    return lambda: frame


def _render_unmatched(
    dynamic_only: list[str], static_only: list[str], labels: ProcessLabels
) -> None:
    """한쪽에만 있는 공정. **조용히 떨어지면 GAP 이 이유 없이 커 보인다.**

    이름은 원본 공정명이다(설비 마스터·기준정보에서 고칠 이름). 나열한 이름 가운데 표시명이 붙은
    것이 있을 때만 그렇다고 한 문장 더 적는다 — 상자에는 표시명만 보이기 때문이다.
    """
    if not dynamic_only and not static_only:
        return
    listed = [*dynamic_only[:8], *static_only[:8]]
    note = (
        " 아래 이름은 공정 표시명이 아니라 원본 공정명입니다 — 조회 조건의 `공정` 상자에는 "
        "표시명으로 보입니다."
        if any(labels.label(name) != name for name in listed)
        else ""
    )
    lines = []
    if dynamic_only:
        lines.append(
            f"- 설비에는 있는데 기준정보에 없는 공정 {len(dynamic_only)}개: "
            f"{', '.join(dynamic_only[:8])}{' …' if len(dynamic_only) > 8 else ''}"
        )
    if static_only:
        lines.append(
            f"- 기준정보에는 있는데 설비 일정 기준이 안 나온 공정 {len(static_only)}개: "
            f"{', '.join(static_only[:8])}{' …' if len(static_only) > 8 else ''}"
        )
    st.warning(
        "두 쪽의 공정명이 맞지 않는 자리가 있습니다. 설비 마스터의 `공정소분류` 와 "
        "기준정보의 `공정` 이 같은 값이어야 맞댈 수 있습니다." + note + "\n" + "\n".join(lines)
    )
