# Purpose: 생산계획·Wafer Capa·Bottleneck 요약과 상세표를 결합한 HOME 대시보드를 렌더링한다.


import pandas as pd
import streamlit as st

from capa_simulation.components.home_figures import (
    build_bottleneck_detail_figures,
    build_lob_summary_figures,
    build_plan_detail_figures,
)
from capa_simulation.components.home_rendering import (
    HOME_FIGURE_SCHEMA_VERSION,
    HomeFigureCacheKey,
    home_figure_cache,
    render_home_figures,
    render_home_performance,
    store_home_figures,
)
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    selected_month_range,
)
from capa_simulation.performance import PerformanceTrace
from capa_simulation.scenario_preset_state import (
    DEFAULT_SECURE_THRESHOLD_PERCENT,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)
from capa_simulation.scenario_state import (
    ensure_active_scenario,
    scenario_month_table,
    scenario_table,
)
from capa_simulation.services.dashboard import (
    build_bottleneck_capacity,
    build_monthly_bottleneck_ranking,
    build_monthly_bottleneck_top5_from_ranking,
    build_monthly_bottleneck_top10_details_from_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_production_lob_summary,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    get_home_simulation,
)
from capa_simulation.settings import APP_NAME
from capa_simulation.sidebar_status import (
    format_short_month,
    show_applied_month_range,
    show_month_range_unavailable,
)

render_page_header(
    APP_NAME,
    description=(
        "월별 생산계획을 부하량으로 환산해 Density·Wafer 현황과 "
        "확보율이 가장 낮은 B/N 공정을 한 화면에서 봅니다."
    ),
)
# 대시보드는 Plotly 그림이라 셀을 복사할 수 없다. 표 내용을 그대로 쓰려면 CSV 가 있어야
# 하는데, 내보낼 데이터는 아래 계산이 끝나야 나온다. 줄만 먼저 잡고 뒤에서 채운다.
detail_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
with detail_row:
    show_home_details = st.toggle(
        # 켠 상태로 시작한다. 계획 세부수량과 B/N 상세 시트를 매번 손으로 펼치던 것을
        # 없앤다. 요약만 보려면 끄면 되고, 그 선택은 세션 동안 유지된다.
        "계획·B/N 상세표 표시",
        value=True,
        key="dashboard_show_details",
        persist_state="session",
        help="제품·Stack별 계획 세부수량과 상세 B/N 공정 시트를 아래에 함께 펼칩니다.",
    )
show_home_performance = st.sidebar.toggle(
    "HOME 성능 진단",
    value=False,
    key="dashboard_show_performance",
    persist_state="session",
)
home_trace = PerformanceTrace()

try:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    selected_start, selected_end = selected_month_range()
    source_start, source_end = available_month_range(reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    effective_start = max(selected_start, source_start)
    effective_end = min(selected_end, source_end)
    if effective_start > effective_end:
        show_month_range_unavailable()
        raise ValueError(
            "선택 범위에 생산계획 데이터가 없습니다 "
            f"(데이터 범위 {format_short_month(source_start)}–{format_short_month(source_end)})"
        )
    show_applied_month_range(effective_start, effective_end)
    home_trace.mark("기준정보·시나리오")

    simulation_plan = scenario_month_table(
        active_scenario,
        "RQ_PKG_PLAN",
        effective_start,
        effective_end,
    )
    simulation_yield = scenario_month_table(
        active_scenario,
        "RQ_YLD",
        effective_start,
        effective_end,
    )
    simulation_upeh = scenario_month_table(
        active_scenario,
        "RQ_UPEH",
        effective_start,
        effective_end,
    )
    simulation_run_rate = scenario_month_table(
        active_scenario,
        "RQ_RUN_RATE",
        effective_start,
        effective_end,
    )
    simulation_vital = scenario_month_table(
        active_scenario,
        "RQ_VITAL",
        effective_start,
        effective_end,
    )
    simulation_run_day = scenario_month_table(
        active_scenario,
        "RQ_RUN_DAY",
        effective_start,
        effective_end,
    )
    simulation_lot_ratio = scenario_month_table(
        active_scenario,
        "RQ_LOT_RATIO",
        effective_start,
        effective_end,
    )
    simulation_wf_ratio = scenario_month_table(
        active_scenario,
        "RQ_WF_RATIO",
        effective_start,
        effective_end,
    )
    simulation_reqb = scenario_month_table(
        active_scenario,
        "RQ_REQB",
        effective_start,
        effective_end,
    )
    simulation_available = scenario_month_table(
        active_scenario,
        "RQ_EQP_AVBL",
        effective_start,
        effective_end,
    )
    home_simulation_cache_key = build_home_simulation_cache_key(
        reference_version=reference_version,
        scenario_token=active_scenario["content_token"],
        start_month=effective_start,
        end_month=effective_end,
        display_order=reference_tables["RQ_DISPLAY_ORDER"],
    )
    home_trace.mark("월 범위 데이터 준비")
    (
        monthly_density,
        production_detail,
        monthly_wafer,
        securement_rate,
    ) = get_home_simulation(
        cache_key=home_simulation_cache_key,
        _plan=simulation_plan,
        _yield_data=simulation_yield,
        _density_data=scenario_table(active_scenario, "RQ_CHIP_EQ"),
        _display_order=reference_tables["RQ_DISPLAY_ORDER"],
        _upeh=simulation_upeh,
        _run_rate=simulation_run_rate,
        _vital=simulation_vital,
        _module=reference_tables["RQ_MODULE"],
        _run_day=simulation_run_day,
        _lot_ratio=simulation_lot_ratio,
        _wf_ratio=simulation_wf_ratio,
        _reqb=simulation_reqb,
        _chip_qty=scenario_table(active_scenario, "RQ_CHIP_QTY"),
        _available_equipment=simulation_available,
    )
    home_trace.mark("HOME 계산 파이프라인")
except BOOTSTRAP_ERRORS as exc:
    st.error(bootstrap_error_message(exc))
    st.stop()

with detail_row:
    # 화면은 K 단위로 줄여 적지만 내보내기는 원래 수량을 그대로 준다.
    render_csv_download(
        data=production_detail.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"Home_Plan_Detail_{effective_start}_{effective_end}.csv",
        key="download_home_plan_detail",
        label="계획 세부수량 CSV",
    )

process_options = sorted(
    securement_rate["공정"].astype("string").str.strip().dropna().unique().tolist()
)
process_selection_key = "dashboard_bottleneck_process_selection"
process_dialog_draft_key = "dashboard_bottleneck_process_dialog_draft"
process_dialog_editor_key = "dashboard_bottleneck_process_dialog_editor"
if process_selection_key not in st.session_state:
    st.session_state[process_selection_key] = [
        process
        for process in process_options
        if st.session_state.get(f"dashboard_bottleneck_process_{process}", True)
    ]
else:
    saved_processes = st.session_state[process_selection_key]
    if isinstance(saved_processes, list):
        st.session_state[process_selection_key] = [
            process for process in saved_processes if process in process_options
        ]


def set_process_dialog_selection(processes: list[str]) -> None:
    st.session_state[process_dialog_draft_key] = list(processes)
    st.session_state.pop(process_dialog_editor_key, None)


@st.dialog(
    "B/N 집계 공정 선택",
    width="large",
    icon=":material/filter_alt:",
    on_dismiss="rerun",
)
def show_process_filter_dialog(options: list[str]) -> None:
    draft_selection = st.session_state.get(process_dialog_draft_key, [])
    if not isinstance(draft_selection, list):
        draft_selection = []
    selected_set = {str(process) for process in draft_selection if process in options}

    st.caption(
        "B/N 공정과 Capa 집계에 포함할 공정을 선택합니다. 표의 검색 기능으로 공정명을 "
        "찾을 수 있으며, 적용 전까지 기존 대시보드 조건은 유지됩니다."
    )
    with st.container(horizontal=True, gap="small"):
        st.button(
            "전체 ON",
            icon=":material/select_all:",
            on_click=set_process_dialog_selection,
            args=(options,),
            key="dashboard_bottleneck_process_all_on",
        )
        st.button(
            "전체 OFF",
            icon=":material/deselect:",
            on_click=set_process_dialog_selection,
            args=([],),
            key="dashboard_bottleneck_process_all_off",
        )
        st.button(
            "적용값 복원",
            icon=":material/undo:",
            on_click=set_process_dialog_selection,
            args=(list(st.session_state[process_selection_key]),),
            key="dashboard_bottleneck_process_restore",
        )

    selection_frame = pd.DataFrame(
        {
            "포함": [process in selected_set for process in options],
            "공정": options,
        }
    )
    with st.form("dashboard_bottleneck_process_dialog_form", border=False):
        edited_selection = st.data_editor(
            selection_frame,
            key=process_dialog_editor_key,
            hide_index=True,
            disabled=["공정"],
            num_rows="fixed",
            width="stretch",
            height=520,
            row_height=34,
            column_config={
                "포함": st.column_config.CheckboxColumn(
                    "포함",
                    help="B/N 집계에 포함하려면 선택합니다.",
                    width="small",
                ),
                "공정": st.column_config.TextColumn("공정", width="large"),
            },
        )
        apply_selection = st.form_submit_button(
            "선택 공정 적용",
            type="primary",
            icon=":material/check:",
            width="stretch",
        )
    if apply_selection:
        included_mask = edited_selection["포함"].fillna(False).astype(bool)
        st.session_state[process_selection_key] = (
            edited_selection.loc[included_mask, "공정"].astype(str).tolist()
        )
        st.session_state.pop(process_dialog_draft_key, None)
        st.rerun()


included_processes = list(st.session_state[process_selection_key])
# 키와 기본값은 리비전 프리셋 소유다. Static Capa 본문의 같은 컨트롤과 세션 상태를
# 공유하므로 여기서 문자열을 다시 적으면 조용히 끊어진다.
secure_threshold_key = SECURE_THRESHOLD_KEY
warning_threshold_key = WARNING_THRESHOLD_KEY
if secure_threshold_key not in st.session_state:
    st.session_state[secure_threshold_key] = DEFAULT_SECURE_THRESHOLD_PERCENT
if warning_threshold_key not in st.session_state:
    st.session_state[warning_threshold_key] = DEFAULT_WARNING_THRESHOLD_PERCENT
with st.sidebar.container(border=True):
    st.markdown("#### :material/filter_alt: B/N 집계 공정")
    with st.form("dashboard_bottleneck_filter_form", border=False):
        st.markdown("**판정 기준**")
        secure_threshold_percent = st.number_input(
            "확보 기준 (%)",
            min_value=0.0,
            step=0.1,
            key=secure_threshold_key,
            persist_state="session",
        )
        warning_threshold_percent = st.number_input(
            "경고 기준 (%)",
            min_value=0.0,
            step=0.1,
            key=warning_threshold_key,
            persist_state="session",
        )
        st.form_submit_button("판정 기준 적용", width="stretch")
    st.caption(f"공정 선택 · {len(included_processes)} / {len(process_options)}개 포함")
    if st.button(
        "공정 선택창 열기",
        icon=":material/filter_list:",
        width="stretch",
        disabled=not process_options,
        key="dashboard_bottleneck_process_dialog_open",
    ):
        set_process_dialog_selection(included_processes)
        show_process_filter_dialog(process_options)
    if warning_threshold_percent > secure_threshold_percent:
        st.warning("경고 기준은 확보 기준보다 클 수 없습니다.")
    if not process_options:
        st.caption("집계 가능한 공정이 없습니다.")

secure_threshold = secure_threshold_percent / 100.0
warning_threshold = warning_threshold_percent / 100.0
month_labels = [str(value) for value in monthly_density["년월"].tolist()]
figure_cache_key: HomeFigureCacheKey = (
    HOME_FIGURE_SCHEMA_VERSION,
    reference_version,
    active_scenario["content_token"],
    effective_start,
    effective_end,
    home_simulation_cache_key[-1],
    tuple(included_processes),
    float(secure_threshold_percent),
    float(warning_threshold_percent),
    show_home_details,
)
cached_figures = home_figure_cache().get(figure_cache_key)
if cached_figures is not None:
    home_trace.mark("Figure 캐시 조회")
    render_home_figures(
        cached_figures,
        month_labels,
    )
    home_trace.mark("Plotly 전달")
    render_home_performance(
        home_trace,
        cache_hit=True,
        enabled=show_home_performance,
    )
    st.stop()

bottleneck_ranking = build_monthly_bottleneck_ranking(
    securement_rate,
    included_processes=included_processes,
)
monthly_bottlenecks = build_monthly_bottlenecks_from_ranking(bottleneck_ranking)
bottleneck_capacity = build_bottleneck_capacity(monthly_density, monthly_bottlenecks)
monthly_top5 = build_monthly_bottleneck_top5_from_ranking(
    bottleneck_ranking,
    monthly_density,
    monthly_wafer=monthly_wafer,
)
if show_home_details:
    monthly_top10_details = build_monthly_bottleneck_top10_details_from_ranking(
        bottleneck_ranking,
        monthly_wafer,
    )
lob_summary = build_production_lob_summary(
    monthly_density,
    monthly_wafer,
    monthly_bottlenecks,
)
home_trace.mark("B/N 단일 순위·파생")


# 위 캐시 적중 분기가 st.stop() 으로 끝나므로 여기부터는 항상 캐시 미적중 경로다.
label_figure, month_figure = build_lob_summary_figures(
    monthly_density=monthly_density,
    monthly_top5=monthly_top5,
    bottleneck_capacity=bottleneck_capacity,
    lob_summary=lob_summary,
    month_labels=month_labels,
    secure_threshold=secure_threshold,
    warning_threshold=warning_threshold,
)
if not show_home_details:
    cached_figures = (label_figure, month_figure)
    store_home_figures(figure_cache_key, cached_figures)
    home_trace.mark("요약 Figure 생성")
    render_home_figures(
        cached_figures,
        month_labels,
    )
    home_trace.mark("Plotly 전달")
    render_home_performance(
        home_trace,
        cache_hit=False,
        enabled=show_home_performance,
    )
    st.stop()
detail_label_figure, detail_month_figure = build_plan_detail_figures(
    production_detail=production_detail,
    month_labels=month_labels,
)
bottleneck_detail_label_figure, bottleneck_detail_month_figure = build_bottleneck_detail_figures(
    monthly_density=monthly_density,
    monthly_top10_details=monthly_top10_details,
    month_labels=month_labels,
)
cached_figures = (
    label_figure,
    month_figure,
    detail_label_figure,
    detail_month_figure,
    bottleneck_detail_label_figure,
    bottleneck_detail_month_figure,
)
store_home_figures(figure_cache_key, cached_figures)
home_trace.mark("상세 Figure 생성")

render_home_figures(
    cached_figures,
    month_labels,
)
home_trace.mark("Plotly 전달")
render_home_performance(
    home_trace,
    cache_hit=False,
    enabled=show_home_performance,
)
