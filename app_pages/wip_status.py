# Purpose: 일별 재공·유입·Flow를 제품별 표준 가능량과 비교하는 Dynamic Capa 하위 화면을 렌더링한다.

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.scroll_shell import horizontal_scroll_canvas
from capa_simulation.components.status_metric import render_status_metric, shortage_tone
from capa_simulation.components.wip_status_dashboard import (
    WIP_GRID_CELL_WIDTH_PX,
    build_wip_status_grid_figure,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.scenario_state import (
    ensure_active_scenario,
    scenario_month_table,
    scenario_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.simulation_cache import (
    REFERENCE_INPUT_TABLES,
    SCENARIO_MONTHLESS_TABLES,
    get_capacity_and_demand,
    get_weekly_standard_target_capacity,
)
from capa_simulation.services.standard_target_capacity import (
    prepare_standard_target_required_equipment,
)
from capa_simulation.services.wip_status import (
    build_wip_history_demo,
    build_wip_route_scope,
    expand_weekly_product_standard_to_daily,
    processes_in_step_order,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

PROCESS_FILTER_KEY = "wip_status_process_filter"
PRODUCT_FILTER_KEY = "wip_status_product_filter"
DEFAULT_PROCESS_COUNT = 5
DEFAULT_PRODUCT_COUNT = 4


def _initialize_filter_state(key: str, options: list[str], default_count: int) -> None:
    saved = st.session_state.get(key)
    if not isinstance(saved, list):
        st.session_state[key] = options[:default_count]
        return
    st.session_state[key] = [str(value) for value in saved if str(value) in options]


def _products_in_display_order(
    routes: pd.DataFrame,
    display_order: pd.DataFrame,
) -> list[str]:
    products = routes[["제품정보"]].drop_duplicates().reset_index(drop=True)
    ordered = apply_display_order(
        products,
        display_order,
        "표준 목표 Capa",
        "목표 Capa",
    )
    return ordered["제품정보"].astype(str).tolist()


render_page_header(
    "표준 대비 재공 현황 (구현중)",
    description=(
        "공정·제품·STEP별 보유 재공, 유입과 Flow를 일 표준 가능량과 비교합니다. "
        "가로는 STEP 순서, 세로는 제품 표시순서이며 각 셀은 동일한 11일 구간을 표시합니다."
    ),
)
st.info(
    "현재 재공 값은 화면·연결 계약 검토용 결정론적 샘플입니다. 실제 재공 실적 DB의 "
    "일자·공정·STEP·제품·보유재공·유입·Flow 컬럼 매핑은 아직 연결하지 않았습니다."
)

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
    filtered_tables = {
        name: scenario_month_table(active_scenario, name, start_month, end_month)
        for name in (
            "RQ_UPEH",
            "RQ_RUN_RATE",
            "RQ_VITAL",
            "RQ_RUN_DAY",
            "RQ_LOT_RATIO",
            "RQ_WF_RATIO",
            "RQ_PKG_PLAN",
            "RQ_YLD",
            "RQ_REQB",
        )
    }
    unit_capacity, required_equipment = get_capacity_and_demand(
        {
            **filtered_tables,
            **{key: reference_tables[key] for key in REFERENCE_INPUT_TABLES},
            **{key: scenario_table(active_scenario, key) for key in SCENARIO_MONTHLESS_TABLES},
        }
    )
    required_equipment = prepare_standard_target_required_equipment(required_equipment)
    route_scope = build_wip_route_scope(required_equipment)
    availability = get_equipment_repository(
        str(EQUIPMENT_DUCKDB_PATH.resolve())
    ).load_standard_target_availability()
except (KeyError, OSError, RuntimeError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

if route_scope.empty:
    st.warning("오늘 기준 조회 구간에 재공 현황을 구성할 공정·제품 경로가 없습니다.")
    st.stop()

process_options = processes_in_step_order(route_scope)
product_options = _products_in_display_order(
    route_scope,
    reference_tables["RQ_DISPLAY_ORDER"],
)
_initialize_filter_state(PROCESS_FILTER_KEY, process_options, DEFAULT_PROCESS_COUNT)
_initialize_filter_state(PRODUCT_FILTER_KEY, product_options, DEFAULT_PRODUCT_COUNT)

with st.container(border=True):
    st.markdown("#### :material/filter_alt: 조회 조건")
    st.caption(
        f"기준일 {today:%Y-%m-%d} · 조회기간 {start_date:%Y-%m-%d} ~ {end_date:%Y-%m-%d} "
        "(오늘 -7일 ~ +3일)"
    )
    with st.form("wip_status_filters", border=False):
        filter_row = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
        with filter_row:
            selected_processes = st.multiselect(
                "공정",
                options=process_options,
                key=PROCESS_FILTER_KEY,
                placeholder="표시할 공정 선택",
                help="옵션과 차트 열은 STEP의 P→T, 숫자 구간 오름차순을 따릅니다.",
                persist_state="session",
                width=420,
            )
            selected_products = st.multiselect(
                "제품",
                options=product_options,
                key=PRODUCT_FILTER_KEY,
                placeholder="표시할 제품 선택",
                help="표준 목표 Capa의 공용 제품 표시순서를 따릅니다.",
                persist_state="session",
                width=420,
            )
            st.form_submit_button(
                ":material/filter_alt: 조건 적용",
                type="primary",
                width="content",
            )

if not selected_processes or not selected_products:
    st.info("차트를 표시하려면 공정과 제품을 각각 하나 이상 선택하세요.")
    st.stop()

selected_product_order = [
    product for product in product_options if product in set(selected_products)
]
selected_routes = route_scope.loc[
    route_scope["공정"].isin(selected_processes)
    & route_scope["제품정보"].isin(selected_product_order)
].reset_index(drop=True)
if selected_routes.empty:
    st.warning("선택한 공정과 제품 사이에 적용 가능한 STEP 경로가 없습니다.")
    st.stop()

selected_required = required_equipment.loc[
    required_equipment["공정"].isin(selected_processes)
    & required_equipment["제품정보"].isin(selected_product_order)
].reset_index(drop=True)
try:
    weekly_standard = get_weekly_standard_target_capacity(
        required_equipment=selected_required,
        run_day=filtered_tables["RQ_RUN_DAY"],
        weekly_availability=availability,
        start_date=start_date,
        end_date=end_date,
        detail_level="제품정보",
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
    figure = build_wip_status_grid_figure(
        wip_history,
        selected_routes,
        selected_product_order,
        start_date,
        end_date,
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

today_rows = wip_history.loc[wip_history["일자"].eq(today)]
today_met = int(today_rows["상태"].eq("충족").sum())
today_short = int(today_rows["상태"].eq("부족").sum())
today_unset = int(today_rows["상태"].eq("표준 미설정").sum())
route_count = len(selected_routes)
with st.container(horizontal=True):
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
    st.markdown("#### :material/insights: 일별 재공·Flow와 표준 가능 수준")
    st.caption(
        "Flow 막대는 표준 이상이면 초록색, 미달이면 빨간색입니다. 점선은 현재 `표준 목표 "
        "Capa`와 같은 산식(공정 유효 Capa ÷ RUN_DAY × 주차별 가용대수)의 제품별 가능 "
        "수준입니다. 공정 소요기준에 따라 단위는 Kea 또는 매이며 서로 합산하지 않습니다."
    )
    if today_unset:
        st.warning(
            "일부 공정·주차에 가용대수가 없어 표준 가능량 기준선을 표시하지 못했습니다. "
            "`표준 목표 Capa`에서 주차별 가용설비를 입력하면 같은 값이 반영됩니다."
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

with st.expander("데이터·계산 경계", expanded=False):
    st.markdown(
        "- 재공 실적 계약: `일자 + 공정 + STEP_SEQ + 제품정보 + 보유 재공 + 유입량 + "
        "Flow량`\n"
        "- 표준 기준: 활성 시나리오의 제품 Mix 기반 공정 유효 Capa와 설비 DB의 주차별 "
        "가용대수\n"
        "- 실제 DB 연결 시 샘플 생성부만 조회 Provider로 교체하고 표준 계산과 차트 계약은 "
        "유지합니다."
    )
