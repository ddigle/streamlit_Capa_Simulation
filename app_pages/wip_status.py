# Purpose: 일별 재공·유입·Flow를 제품별 표준 가능량과 비교하는 Dynamic Capa 하위 화면을 렌더링한다.

"""표준 대비 재공 현황(구현 중 — 재공 값은 결정론적 샘플).

머리에 배지 줄을 두지 않는다(구현 중 표지는 화면 탭 이름 곁, 합성 샘플 표지는 머리 띠).
「샘플 데이터」 는 사이드바 조회 조건 패널 줄이고, 공정 · 제품 고르기와 「조건 적용」 은 사이드바
「재공 현황 조건」 카드의 폼이다(본문 상단 문구 · 여백 최소화 — 2026-11-09 보드 T8, 설계 규칙
UI-LAY-02 · UI-INP-04). 두 칸은 적용한 값 한 줄이고 누르면 다중 선택 칸이 열린다(UI-LAY-06 ·
UI-CON-04). 본문은 지표와 격자뿐이다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_field import first_and_rest
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.sample_data import render_pending_source, render_sample_row
from capa_simulation.components.scroll_shell import horizontal_scroll_canvas
from capa_simulation.components.state_alerts import simulation_scope
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.wip_status_dashboard import (
    WIP_GRID_CELL_WIDTH_PX,
    remembered_wip_status_grid_figure,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.navigation import STANDARD_TARGET_CAPA
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    prune_list_selection,
    render_schema_ahead_warning,
)
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_standard_target_availability,
)
from capa_simulation.scenario_state import (
    ensure_active_scenario,
    scenario_month_table,
)
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.simulation_cache import (
    ScenarioCacheKey,
    display_order_digest,
    get_scenario_capacity_and_demand,
    get_weekly_standard_target_capacity,
    scenario_cache_key,
    standard_target_weekly_cache_key,
)
from capa_simulation.services.wip_status import (
    WipRouteChoices,
    build_wip_history_demo,
    expand_weekly_product_standard_to_daily,
    prepare_wip_route_choices,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

# 스위치 풍선과 연결 전 안내가 같은 이름을 보게 한다.
SOURCE = "재공 실적 DB"
# 공정 · 제품 고르기 카드(사이드바).
CARD_LABEL = "재공 현황 조건"
CARD_NAME = "wip_status"
PROCESS_FILTER_KEY = "wip_status_process_filter"
PRODUCT_FILTER_KEY = "wip_status_product_filter"
DEFAULT_PROCESS_COUNT = 5
DEFAULT_PRODUCT_COUNT = 4
# 카드의 공정 · 제품 칸은 이름 줄 + 고른 값 한 줄 팝오버(「WF 입고검사 외 4개」 — 안이 다중 선택
# 칸)다. 300px 카드에서는 칩이 한 줄에 하나씩 쌓여 다중 선택 칸 높이 상한에 다섯째 칩이 잘리고
# 「조건 적용」 이 1283 창 첫 화면 밖으로 밀린다(설계 규칙 UI-LAY-06 — 옮긴 자리 크기에 맞춰 다시
# 짠다). 필요 단축 일정 카드의 공정 칸과 같은 꼴이다(UI-CON-04 — `process_field.first_and_rest`).
PROCESS_POPOVER_KEY = "wip_status_process_popover"
PRODUCT_POPOVER_KEY = "wip_status_product_popover"
PROCESS_EMPTY = "표시할 공정 선택"
PRODUCT_EMPTY = "표시할 제품 선택"
_FIELD_NAME_CLASS = "capa-wip-field-name"
# 시나리오 소요대수에서만 나오는 준비물(경로·선택지) 한 벌과 그 키(세션 칸).
ROUTE_CHOICES_MEMO_KEY = "wip_status_route_choices_memo"
# 격자를 읽는 법은 자리에 늘 두지 않고 구획 제목 풍선이 말한다(설계 규칙 UI-TXT-01 · UI-TXT-02 —
# 화면 소개는 `guides/wip_status.md`).
GRID_HELP = (
    "가로는 STEP 순서, 세로는 제품 표시순서이며 각 칸은 같은 11일 구간입니다. Flow 막대는 표준 "
    "이상이면 초록색, 미달이면 빨간색입니다. 점선은 현재 `표준 목표 Capa`와 같은 산식(공정별 대당 "
    "Capa ÷ RUN_DAY × 주차별 가용대수)의 제품별 가능 수준입니다. 공정 소요기준에 따라 단위는 Kea "
    "또는 매이며 서로 합산하지 않습니다."
)


def _route_choices(
    scenario_key: ScenarioCacheKey,
    scenario_tables: dict[str, pd.DataFrame],
    reference_tables: dict[str, pd.DataFrame],
) -> WipRouteChoices:
    """표준 목표 규칙을 적용한 소요대수·경로 범위·공정·제품 선택지. 키는 시나리오 키
    (reference_version·**content_token**·조회 월)와 공용 표시순서 내용 지문이다 — 표시순서는
    reference_version 을 바꾸지 않고 바뀐다. 둘이 같으면 직전 회차의 묶음(사본)을 쓰고 소요대수도
    다시 꺼내지 않는다. 가용대수는 여기 들지 않는다(남이 바꾸는 현행값이라 매 회차 읽는다)."""
    display_order = reference_tables["RQ_DISPLAY_ORDER"]
    key = (scenario_key, display_order_digest(display_order))
    memo = st.session_state.get(ROUTE_CHOICES_MEMO_KEY)
    if (
        isinstance(memo, tuple)
        and len(memo) == 2
        and memo[0] == key
        and isinstance(memo[1], WipRouteChoices)
    ):
        return memo[1].copy()
    _, required_equipment = get_scenario_capacity_and_demand(
        scenario_key,
        _scenario_tables=scenario_tables,
        _reference_tables=reference_tables,
    )
    choices = prepare_wip_route_choices(required_equipment, display_order)
    st.session_state[ROUTE_CHOICES_MEMO_KEY] = (key, choices)
    return choices.copy()


def _field_head(name: str, popover_key: str) -> str:
    """이름 줄과 한 줄 칸의 꼴 — 이름은 위젯 라벨 글(0.875rem), 값은 왼쪽 · 펼침 표식은 오른쪽
    끝(팝오버 단추는 기본이 가운데 정렬이라 단추로 읽힌다). 서식과 이름을 한 `st.html` 에 실어
    카드 안 그 자리에 그린다(스타일만 든 `st.html` 은 이벤트 칸으로 간다 — AGENTS 9장)."""
    button = f'.st-key-{popover_key} button[data-testid="stPopoverButton"]'
    return (
        "<style>"
        f".{_FIELD_NAME_CLASS}{{margin:0 0 -0.25rem;font-size:0.875rem;line-height:1.6;}}"
        f"{button} > div{{width:100%;justify-content:space-between;min-width:0;}}"
        f"{button} > div > div:first-child{{justify-content:flex-start;min-width:0;}}"
        f"{button} p{{text-align:left;}}"
        "</style>"
        f'<p class="{_FIELD_NAME_CLASS}">{name}</p>'
    )


def _picked_field(
    name: str,
    *,
    options: list[str],
    key: str,
    popover_key: str,
    empty: str,
    format_func: Callable[[object], str] = str,
) -> list[str]:
    """폼 안의 이름 줄 + 고른 값 한 줄 팝오버(안이 다중 선택 칸). 한 줄 글은 **적용한** 값이다 —
    폼이라 세션 값은 「조건 적용」 때 바뀐다. 첫 이름은 가장 먼저 고른 것이고(다중 선택 값은 고른
    차례대로 쌓인다) 둘 이상이면 한 줄 칸의 풍선이 전체 목록이다."""
    applied = st.session_state.get(key)
    names = [
        literal_markdown(format_func(str(value)))
        for value in (applied if isinstance(applied, list) else [])
    ]
    st.html(_field_head(name, popover_key))
    with st.popover(
        first_and_rest(names) or empty,
        key=popover_key,
        width="stretch",
        wrap=False,
        help=" · ".join(names) if len(names) >= 2 else None,
    ):
        picked = st.multiselect(
            name,
            options=options,
            key=key,
            placeholder=empty,
            persist_state="session",
            label_visibility="collapsed",
            width="stretch",
            format_func=format_func,
        )
    return [str(value) for value in picked]


render_page_header("표준 대비 재공 현황 (구현중)", show_status=False)
render_page_guide("wip_status", title="표준 대비 재공 현황")
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()
if not render_sample_row(key="wip_status_sample_switch", source=SOURCE):
    render_pending_source(
        subject="표준 대비 재공 현황",
        source=SOURCE,
        expects=(
            "**일자 · 공정 · STEP_SEQ · 제품정보** 단위의 보유 재공",
            "같은 단위의 **유입량**과 **Flow량** — 막대 세 개가 이 세 값입니다",
            "집계 시점(일 마감 기준)과 STEP 코드 매핑 규칙",
            "표준 가능량 기준선은 활성 시나리오와 설비 DB에서 이미 나옵니다 — "
            "재공 실적만 붙이면 됩니다",
        ),
    )
    st.stop()

today = date.today()
start_date = today - timedelta(days=7)
end_date = today + timedelta(days=3)
calendar = build_iso_week_calendar(start_date, end_date)
start_month = int(calendar["생산계획년월"].min())
end_month = int(calendar["생산계획년월"].max())

try:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    # 계산 입력의 월 슬라이스는 캐시 래퍼 안에서 한다. 뒤의 주차 계산이 쓰는 RUN_DAY 만 자른다.
    filtered_tables = {
        "RQ_RUN_DAY": scenario_month_table(active_scenario, "RQ_RUN_DAY", start_month, end_month)
    }
    choices = _route_choices(
        scenario_cache_key(reference_version, active_scenario, start_month, end_month),
        active_scenario["tables"],
        reference_tables,
    )
    required_equipment = choices.required_equipment
    route_scope = choices.routes
    equipment_database = str(EQUIPMENT_DUCKDB_PATH.resolve())
    equipment_repository = get_equipment_repository(equipment_database)
    availability = load_standard_target_availability(equipment_database)
except BOOTSTRAP_ERRORS as exc:
    message = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    render_data_error(message, code="WIP-01", text="재공 현황을 준비하지 못했습니다")
    st.stop()
# 설비 DB 가 이 코드보다 새 버전이면(예전 배포로 되돌린 상태) 상태 알림(`GL-03`). 막지 않는다.
render_schema_ahead_warning(equipment_repository.schema_ahead)

if route_scope.empty:
    # 그릴 것이 없어 멈추는 빈 상태는 회색 평문 한 줄이다(설계 규칙 UI-TXT-04). 채울 입력이 빠진
    # 멈춤(바로 아래 주차별 가용대수)은 「데이터 Error」 마크다.
    st.caption("오늘 기준 조회 구간에 재공 현황을 구성할 공정·제품 경로가 없습니다.")
    st.stop()

if availability.empty:
    # 빈 표를 그대로 계산에 넣으면 prepare_weekly_availability 가 "가용설비 입력 표에 행이
    # 없습니다" 를 던진다 — 채울 입력이 표준 목표에 있으므로 그 화면으로 가는 길은 Alarm 줄의
    # 「그 화면으로」 다(자리에 링크 · 글을 두지 않는다).
    render_data_error(
        "재공 현황 — 설비 DB에 주차별 가용대수가 없어 표준 가능량 기준선을 만들 수 없습니다. "
        "`표준 목표` 페이지에서 주차별 가용설비를 입력하면 재공 현황에 그대로 반영됩니다.",
        code="WIP-01",
        text="재공 현황을 그리지 못했습니다 — 주차별 가용대수 없음",
        goto=(tab_label(STANDARD_TARGET_CAPA), STANDARD_TARGET_CAPA.href),
    )
    st.stop()

process_options = list(choices.processes)
product_options = list(choices.products)
prune_list_selection(
    PROCESS_FILTER_KEY, process_options, default=process_options[:DEFAULT_PROCESS_COUNT]
)
prune_list_selection(
    PRODUCT_FILTER_KEY, product_options, default=product_options[:DEFAULT_PRODUCT_COUNT]
)

# 공정 · 제품은 사이드바 카드의 폼이다 — 둘을 함께 바꾼 뒤 「조건 적용」 한 번에 다시
# 그린다(적용형 — 설계 규칙 UI-INP-04). 조회 구간(오늘 −7일 ~ +3일)은 값 한 줄로 카드 맨 위에
# 둔다(고르는 칸이 아니다).
with condition_card(CARD_LABEL, name=CARD_NAME, icon=":material/filter_alt:"):
    st.caption(
        f"기준일 {today:%Y-%m-%d} · {start_date:%m-%d} ~ {end_date:%m-%d}",
        help="조회 구간은 오늘 −7일 ~ +3일로 정해져 있습니다.",
    )
    with st.form("wip_status_filters", border=False):
        # 선택지 차례(공정은 STEP 의 P→T · 숫자 구간 오름차순, 제품은 공용 제품 표시순서)는 Guide
        # 가 말한다 — 한 줄 칸의 풍선은 고른 전체 목록이다.
        selected_processes = _picked_field(
            "공정",
            options=process_options,
            key=PROCESS_FILTER_KEY,
            popover_key=PROCESS_POPOVER_KEY,
            empty=PROCESS_EMPTY,
            # 표시만 바꾼다. 선택값은 아래 `isin` 이 원본 컬럼과 대조한다. 보이는 글자가
            # 겹치면 「표시명 (원본)」 으로 가른다(`unique_format_func`). 잡은 값은 위
            # `prune_list_selection` 이 매 회차 다시 적어 브라우저가 바뀐 글자를 받는다.
            format_func=process_labels.unique_format_func(process_options),
        )
        selected_products = _picked_field(
            "제품",
            options=product_options,
            key=PRODUCT_FILTER_KEY,
            popover_key=PRODUCT_POPOVER_KEY,
            empty=PRODUCT_EMPTY,
        )
        st.form_submit_button(
            "조건 적용",
            icon=":material/filter_alt:",
            type="primary",
            width="stretch",
        )

if not selected_processes or not selected_products:
    # 고른 것이 없어 그릴 것이 없는 멈춤도 회색 평문 한 줄이다 — 하는 법은 붙이지 않는다(설계 규칙
    # UI-TXT-04).
    st.caption("고른 공정 또는 제품이 없습니다.")
    st.stop()

selected_product_order = [
    product for product in product_options if product in set(selected_products)
]
selected_routes = route_scope.loc[
    route_scope["공정"].isin(selected_processes)
    & route_scope["제품정보"].isin(selected_product_order)
].reset_index(drop=True)
if selected_routes.empty:
    st.caption("선택한 공정과 제품 사이에 적용 가능한 STEP 경로가 없습니다.")
    st.stop()

try:
    # 키만 해시한다(표준 목표와 같은 캐시). 공정·제품 선택이 키에 들어 표준 목표 결과와
    # 섞이지 않는다.
    weekly_standard = get_weekly_standard_target_capacity(
        cache_key=standard_target_weekly_cache_key(
            scenario_cache_key(reference_version, active_scenario, start_month, end_month),
            availability=availability,
            start_date=start_date,
            end_date=end_date,
            detail_level="제품정보",
            processes=selected_processes,
            products=selected_product_order,
        ),
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
        _weekly_availability=availability,
    )
    daily_standard = expand_weekly_product_standard_to_daily(
        weekly_standard,
        start_date,
        end_date,
    )
    wip_history = build_wip_history_demo(
        selected_routes,
        daily_standard,
        start_date,
        end_date,
        today=today,
    )
    # 그림은 입력 내용이 같으면 직전 회차의 것을 다시 쓴다(세션 한 벌). 위 데이터 준비는 매 회차
    # 돌아 그 입력을 만든다. 받은 Figure 는 고치지 않는다 — 다음 회차가 이 객체를 그대로
    # 다시 그린다.
    figure = remembered_wip_status_grid_figure(
        wip_history,
        selected_routes,
        selected_product_order,
        start_date,
        end_date,
        process_labels=process_labels,
    )
except ValueError as exc:
    message = bootstrap_error_message(exc)
    render_data_error(message, code="WIP-01", text="재공 현황을 그리지 못했습니다")
    st.stop()

today_rows = wip_history.loc[wip_history["일자"].eq(today)]
today_met = int(today_rows["상태"].eq("충족").sum())
today_short = int(today_rows["상태"].eq("부족").sum())
today_unset = int(today_rows["상태"].eq("표준 미설정").sum())
route_count = len(selected_routes)
with metric_row(key="wip_status_metric_row"):
    st.metric("선택 경로", f"{route_count:,}개", border=True)
    render_status_metric(
        "오늘 표준 충족",
        f"{today_met:,}개",
        key="wip_metric_met",
        tone="good" if today_met else "neutral",
    )
    render_status_metric(
        "오늘 Flow 부족",
        f"{today_short:,}개",
        key="wip_metric_short",
        tone="critical" if today_short else "neutral",
    )
    render_status_metric(
        "표준 미설정",
        f"{today_unset:,}개",
        key="wip_metric_unset",
        tone=shortage_tone(today_unset),
    )

with st.container(border=True):
    st.markdown("#### :material/insights: 일별 재공·Flow와 표준 가능 수준", help=GRID_HELP)
    # 기준선을 못 그린 공정·주차는 상태 알림(`WIP-04` — 자리에 그리지 않는다). 채울 입력은 표준
    # 목표에 있어 그 화면으로 가는 길은 위 멈춤(`WIP-01`)과 같이 Alarm 줄의 「그 화면으로」
    # 다(자리에 링크를 두지 않는다). 줄의 화면 칸이 표준 목표이므로 어느 화면의 일인지는 전문이
    # 말한다. 없어도 부른다(해소). 수는 고른 공정·제품에 따라 바뀌므로 지문에 넣지 않는다 —
    # 거르기를 바꿀 때마다 다시 뜨지 않게.
    wip_scope = simulation_scope(active_scenario, dates=(start_date, end_date))
    alerts.state(
        "WIP-04",
        scope=wip_scope.scope,
        content=bool(today_unset),
        active=bool(today_unset),
        text=(
            f"재공 기준선을 못 그린 경로 {today_unset:,}개(가용대수 없음) — 표준 목표에서 주차별 "
            "가용설비 입력"
        ),
        full=(
            "재공 현황 — 일부 공정·주차에 가용대수가 없어 표준 가능량 기준선을 "
            "표시하지 못했습니다. 「표준 목표」 페이지에서 주차별 가용설비를 입력하면 같은 값이 "
            "반영됩니다."
        ),
        scope_label=wip_scope.label,
        goto=(tab_label(STANDARD_TARGET_CAPA), STANDARD_TARGET_CAPA.href),
    )

    lane_count = len(selected_routes[["STEP_SEQ", "공정"]].drop_duplicates())
    grid_width = max(430, lane_count * WIP_GRID_CELL_WIDTH_PX + 90)
    # 이 화면만 네이티브 스크롤바를 그대로 쓴다. 표 컴포넌트·HOME 은 숨기고 커스텀
    # 스크롤바를 표 위에 얹는다.
    with horizontal_scroll_canvas(
        key="wip_status_grid",
        content_width_px=grid_width,
        hide_native_scrollbar=False,
        padding_bottom="0.5rem",
        gap=None,
    ):
        st.plotly_chart(
            figure,
            width="stretch",
            height="content",
            theme=None,
            key="wip_status_grid",
            config={"displayModeBar": False, "responsive": True},
        )
