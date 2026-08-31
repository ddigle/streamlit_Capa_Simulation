import html
import unicodedata
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from capa_simulation.components.horizontal_scrollbar import render_horizontal_scrollbar
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.performance import PerformanceTrace
from capa_simulation.scenario_state import ensure_active_scenario, scenario_month_table
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_DIMENSIONS,
    build_bottleneck_capacity,
    build_monthly_bottleneck_ranking,
    build_monthly_bottleneck_top5_from_ranking,
    build_monthly_bottleneck_top10_details_from_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_production_lob_summary,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.simulation_cache import (
    get_home_simulation,
)
from capa_simulation.settings import APP_NAME
from capa_simulation.sidebar_status import show_applied_month_range

CLASSIFICATION_BACKGROUND_COLOR = "#F4F4F5"
CLASSIFICATION_GROUP_BACKGROUND_COLOR = "#EAEBED"
SURFACE_COLOR = "#FFFFFF"
GROUP_SURFACE_COLOR = "#FAFAFA"
SUBTLE_SURFACE_COLOR = "#F4F4F5"
HEADER_COLOR = "#E4E4E7"
BORDER_COLOR = "#D4D4D8"
GROUP_BORDER_COLOR = "#A1A1AA"
OUTER_BORDER_WIDTH_PX = 1.8
TRANSPARENT_COLOR = "rgba(0, 0, 0, 0)"
TEXT_COLOR = "#27272A"
MUTED_TEXT_COLOR = "#52525B"
LINE_COLOR = "#3F3F46"
SECURE_COLOR = "#D4D4D8"
WARNING_COLOR = "#FDE68A"
SHORTAGE_COLOR = "#FDA4AF"
MONTH_COLUMN_WIDTH_PX = 100
MONTH_SCROLL_THRESHOLD = 10
DASHBOARD_SCROLLBAR_HEIGHT_PX = 15
DASHBOARD_SECTION_GAP_PX = 16
DASHBOARD_TITLE_HEIGHT_PX = 44
DASHBOARD_TITLE_GAP_PX = 8
LOB_TABLE_HEADER_HEIGHT_PX = 45
LOB_DENSITY_ROW_HEIGHT_PX = 36
LOB_WAFER_PLAN_ROW_HEIGHT_PX = 36
LOB_WAFER_CAPA_ROW_HEIGHT_PX = 36
LOB_TABLE_ROW_HEIGHTS_PX = (
    LOB_TABLE_HEADER_HEIGHT_PX,
    LOB_DENSITY_ROW_HEIGHT_PX,
    LOB_WAFER_PLAN_ROW_HEIGHT_PX,
    LOB_WAFER_CAPA_ROW_HEIGHT_PX,
)
LOB_TABLE_HEIGHT_PX = sum(LOB_TABLE_ROW_HEIGHTS_PX)
LOB_CHART_HEIGHT_PX = 150
LOB_TOP5_HEIGHT_PX = 150
LOB_BOTTOM_MARGIN_PX = 130
LOB_FIGURE_HEIGHT_PX = (
    DASHBOARD_TITLE_HEIGHT_PX
    + LOB_TABLE_HEIGHT_PX
    + LOB_CHART_HEIGHT_PX
    + LOB_TOP5_HEIGHT_PX
    + LOB_BOTTOM_MARGIN_PX
)
HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"
HOME_FIGURE_CACHE_MAX_ENTRIES = 3
HOME_FIGURE_SCHEMA_VERSION = 23

HomeFigureSet = tuple[Any, ...]
HomeFigureCacheKey = tuple[int, int, int, int, int, tuple[str, ...], float, float, bool]


def selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


def home_figure_cache() -> dict[HomeFigureCacheKey, HomeFigureSet]:
    cached = st.session_state.setdefault(HOME_FIGURE_CACHE_KEY, {})
    return cast(dict[HomeFigureCacheKey, HomeFigureSet], cached)


def store_home_figures(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
) -> None:
    cache = home_figure_cache()
    cache.pop(cache_key, None)
    cache[cache_key] = figures
    while len(cache) > HOME_FIGURE_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)))


def render_home_performance(
    trace: PerformanceTrace,
    *,
    cache_hit: bool,
    enabled: bool,
) -> None:
    if not enabled:
        return
    with st.sidebar.expander("HOME 실행 시간", expanded=True):
        st.caption(f"Figure 캐시: {'적중' if cache_hit else '생성'}")
        st.dataframe(
            pd.DataFrame(trace.rows()),
            hide_index=True,
            width="stretch",
        )


def dashboard_title_annotation(text: str) -> dict[str, Any]:
    return {
        "x": 0,
        "y": 1,
        "xref": "paper",
        "yref": "paper",
        "text": text,
        "showarrow": False,
        "xanchor": "left",
        "yanchor": "bottom",
        "yshift": DASHBOARD_TITLE_GAP_PX,
        "font": {"size": 20, "color": TEXT_COLOR, "family": "Malgun Gothic"},
    }


def append_layout_items(
    figure: go.Figure,
    *,
    shapes: list[dict[str, Any]] | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> None:
    """Append Plotly layout collections with one validation pass per collection."""
    updates: dict[str, Any] = {}
    if shapes:
        updates["shapes"] = [*list(figure.layout.shapes or ()), *shapes]
    if annotations:
        updates["annotations"] = [*list(figure.layout.annotations or ()), *annotations]
    if updates:
        figure.update_layout(**updates)


def add_figure_outer_border(
    figure: go.Figure,
    *,
    y0: float = 0.0,
    emphasize_left: bool = True,
    emphasize_bottom: bool = False,
    compensate_bottom: bool = True,
) -> None:
    shapes: list[dict[str, Any]] = []
    if emphasize_left:
        shapes.append(
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "fillcolor": TRANSPARENT_COLOR,
                "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
                "layer": "above",
            }
        )
    else:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": 1,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
                "layer": "above",
            }
        )
    if emphasize_left:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 0,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {
                    "color": GROUP_BORDER_COLOR,
                    "width": OUTER_BORDER_WIDTH_PX * 2,
                },
                "layer": "above",
            }
        )
    shapes.append(
        {
            "type": "line",
            "x0": 1,
            "x1": 1,
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX * 2},
            "layer": "above",
        }
    )
    if emphasize_bottom:
        bottom_width = OUTER_BORDER_WIDTH_PX * (2 if compensate_bottom else 1)
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": y0,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": GROUP_BORDER_COLOR, "width": bottom_width},
                "layer": "above",
            }
        )
    append_layout_items(figure, shapes=shapes)


def add_quarter_boundaries(
    figure: go.Figure,
    month_labels: list[str],
    *,
    y0: float = 0.0,
) -> None:
    quarter_keys = [
        (int(month.split(".")[0]), (int(month.split(".")[1]) - 1) // 3) for month in month_labels
    ]
    shapes = [
        {
            "type": "line",
            "x0": month_index / len(quarter_keys),
            "x1": month_index / len(quarter_keys),
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for month_index in range(1, len(quarter_keys))
        if quarter_keys[month_index] != quarter_keys[month_index - 1]
    ]
    append_layout_items(figure, shapes=shapes)


def fixed_row_domains(
    domain_bottom: float,
    domain_top: float,
    row_heights: tuple[int, ...],
) -> list[tuple[float, float]]:
    total_height = sum(row_heights)
    current_top = domain_top
    domains: list[tuple[float, float]] = []
    for row_height in row_heights:
        row_bottom = current_top - (row_height / total_height * (domain_top - domain_bottom))
        domains.append((row_bottom, current_top))
        current_top = row_bottom
    return domains


def add_fixed_table_row(
    figure: go.Figure,
    *,
    domain: tuple[float, float],
    values: list[str],
    fill_color: str,
    font_size: int,
    bold: bool,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer."""
    value_count = max(len(values), 1)
    annotations = []
    for value_index, value in enumerate(values):
        escaped_value = html.escape(value)
        annotations.append(
            {
                "x": (value_index + 0.5) / value_count,
                "y": (domain[0] + domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": f"<b>{escaped_value}</b>" if bold else escaped_value,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {
                    "color": TEXT_COLOR,
                    "size": font_size,
                    "family": "Malgun Gothic",
                },
            }
        )
    append_layout_items(
        figure,
        shapes=[
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": domain[0],
                "y1": domain[1],
                "xref": "paper",
                "yref": "paper",
                "fillcolor": fill_color,
                "line": {"width": 0},
                "layer": "below",
            }
        ],
        annotations=annotations,
    )


@st.fragment
def render_home_figures(
    figures: HomeFigureSet,
    month_labels: list[str],
    title_column_width: float,
    month_column_width: float,
) -> None:
    if len(figures) not in {2, 6}:
        raise ValueError("HOME Figure 묶음은 요약 2개 또는 상세 포함 6개여야 합니다.")
    label_figure, month_figure = figures[:2]
    detail_figures = figures[2:]
    visible_month_count = min(max(len(month_labels), 1), MONTH_SCROLL_THRESHOLD)

    with st.container(border=True):
        label_column, month_column = st.columns(
            [title_column_width, visible_month_count * month_column_width],
            gap=None,
        )
        with label_column:
            with st.container(
                key="production_lob_label_canvas",
                gap=DASHBOARD_SECTION_GAP_PX,
            ):
                st.plotly_chart(
                    label_figure,
                    width="stretch",
                    key="production_lob_labels",
                    config={"displayModeBar": False, "staticPlot": True},
                )
                if detail_figures:
                    st.plotly_chart(
                        detail_figures[0],
                        width="stretch",
                        key="production_detail_labels",
                        config={"displayModeBar": False, "staticPlot": True},
                    )
                    st.plotly_chart(
                        detail_figures[2],
                        width="stretch",
                        key="bottleneck_detail_labels",
                        config={"displayModeBar": False, "staticPlot": True},
                    )
        with month_column:
            month_chart_width = len(month_labels) * MONTH_COLUMN_WIDTH_PX
            st.html(
                f"""
                <style>
                .st-key-production_lob_label_canvas {{
                    padding-top: calc({DASHBOARD_SCROLLBAR_HEIGHT_PX}px + 0.0rem);
                }}
                .st-key-production_lob_month_scroll {{
                    overflow-x: auto;
                    overflow-y: hidden;
                    padding-bottom: 0.25rem;
                    scrollbar-width: none !important;
                    -ms-overflow-style: none;
                }}
                .st-key-production_lob_month_scroll::-webkit-scrollbar {{
                    width: 0 !important;
                    height: 0 !important;
                    display: none !important;
                }}
                .st-key-production_lob_month_canvas {{
                    width: {month_chart_width}px !important;
                    min-width: {month_chart_width}px !important;
                    max-width: none !important;
                }}
                </style>
                """
            )
            with st.container(key="production_lob_month_region", gap=None):
                render_horizontal_scrollbar(
                    target_selector=".st-key-production_lob_month_scroll",
                    height=DASHBOARD_SCROLLBAR_HEIGHT_PX,
                    key="production_lob_custom_scrollbar",
                )
                with st.container(key="production_lob_month_scroll"):
                    with st.container(
                        key="production_lob_month_canvas",
                        gap=DASHBOARD_SECTION_GAP_PX,
                    ):
                        st.plotly_chart(
                            month_figure,
                            width="stretch",
                            key="production_lob_months",
                            config={"displayModeBar": False, "responsive": True},
                        )
                        if detail_figures:
                            st.plotly_chart(
                                detail_figures[1],
                                width="stretch",
                                key="production_detail_months",
                                config={"displayModeBar": False, "staticPlot": True},
                            )
                            st.plotly_chart(
                                detail_figures[3],
                                width="stretch",
                                key="bottleneck_detail_months",
                                config={"displayModeBar": False, "staticPlot": True},
                            )


st.title(APP_NAME)
show_home_details = st.toggle(
    "계획·B/N 상세표 표시",
    value=False,
    key="dashboard_show_details",
    persist_state="session",
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
        raise ValueError("선택 범위에 생산계획 데이터가 없습니다.")
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
    home_trace.mark("월 범위 데이터 준비")
    (
        monthly_density,
        production_detail,
        monthly_wafer,
        securement_rate,
    ) = get_home_simulation(
        plan=simulation_plan,
        yield_data=simulation_yield,
        density_data=reference_tables["RQ_CHIP_EQ"],
        display_order=reference_tables["RQ_DISPLAY_ORDER"],
        upeh=simulation_upeh,
        run_rate=simulation_run_rate,
        vital=simulation_vital,
        module=reference_tables["RQ_MODULE"],
        run_day=simulation_run_day,
        lot_ratio=simulation_lot_ratio,
        wf_ratio=simulation_wf_ratio,
        reqb=simulation_reqb,
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        available_equipment=simulation_available,
    )
    home_trace.mark("HOME 계산 파이프라인")
except (KeyError, OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

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
secure_threshold_key = "dashboard_secure_threshold_percent"
warning_threshold_key = "dashboard_warning_threshold_percent"
if secure_threshold_key not in st.session_state:
    st.session_state[secure_threshold_key] = 109.5
if warning_threshold_key not in st.session_state:
    st.session_state[warning_threshold_key] = 99.5
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
title_column_width = 2.0
month_column_width = 1.0
figure_cache_key: HomeFigureCacheKey = (
    HOME_FIGURE_SCHEMA_VERSION,
    reference_version,
    active_scenario["revision"],
    effective_start,
    effective_end,
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
        title_column_width,
        month_column_width,
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


def capacity_color(rate: float) -> str:
    if rate > secure_threshold:
        return SECURE_COLOR
    if rate >= warning_threshold:
        return WARNING_COLOR
    return SHORTAGE_COLOR


if cached_figures is None:
    month_positions = list(range(len(month_labels)))
    month_position_by_value = dict(
        zip(monthly_density["생산계획년월"], month_positions, strict=True)
    )
    subplot_options = {
        "rows": 3,
        "cols": 1,
        "specs": [[{"type": "table"}], [{"type": "xy"}], [{"type": "xy"}]],
        "shared_xaxes": False,
        "vertical_spacing": 0,
        "row_heights": [
            LOB_TABLE_HEIGHT_PX,
            LOB_CHART_HEIGHT_PX,
            LOB_TOP5_HEIGHT_PX,
        ],
    }
    label_figure = make_subplots(**subplot_options)
    month_figure = make_subplots(**subplot_options)
    label_table_rows = (
        ("구분", HEADER_COLOR, 21, True),
        ("Density (억Gb)", SUBTLE_SURFACE_COLOR, 20, True),
        ("Wafer 계획", SUBTLE_SURFACE_COLOR, 20, True),
        ("Wafer Capa", SUBTLE_SURFACE_COLOR, 20, True),
    )
    month_table_rows = (
        ([f"{month}" for month in month_labels], HEADER_COLOR, 21, True),
        (
            [f"{row['부하량']:,.2f}" for _, row in lob_summary.iterrows()],
            SURFACE_COLOR,
            20,
            False,
        ),
        (
            [f"{row['Wafer 부하량'] / 1_000:,.0f}K" for _, row in lob_summary.iterrows()],
            SURFACE_COLOR,
            20,
            False,
        ),
        (
            [
                "" if pd.isna(row["Wafer Capa"]) else f"{row['Wafer Capa'] / 1_000:,.0f}K"
                for _, row in lob_summary.iterrows()
            ],
            SURFACE_COLOR,
            20,
            False,
        ),
    )
    lob_chart_domain = cast(Any, month_figure.layout.yaxis).domain
    full_table_domain = (float(lob_chart_domain[1]), 1.0)
    lob_table_domains = fixed_row_domains(
        float(full_table_domain[0]),
        float(full_table_domain[1]),
        LOB_TABLE_ROW_HEIGHTS_PX,
    )
    for row_domain, (value, fill_color, font_size, bold) in zip(
        lob_table_domains,
        label_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            label_figure,
            domain=row_domain,
            values=[value],
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    for row_domain, (values, fill_color, font_size, bold) in zip(
        lob_table_domains,
        month_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            month_figure,
            domain=row_domain,
            values=values,
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    if bottleneck_capacity["B/N Capa"].notna().any():
        month_figure.add_trace(
            go.Bar(
                name="B/N 공정",
                x=[month_position_by_value[month] for month in bottleneck_capacity["생산계획년월"]],
                y=bottleneck_capacity["B/N Capa"],
                customdata=bottleneck_capacity[["년월", "확보율", "공정"]],
                text=bottleneck_capacity["확보율"],
                texttemplate="<b>%{text:.0%}</b>",
                textposition="inside",
                insidetextanchor="start",
                textfont={"color": TEXT_COLOR, "size": 22, "family": "Calibri"},
                marker={
                    "color": [capacity_color(rate) for rate in bottleneck_capacity["확보율"]],
                    "line": {"color": LINE_COLOR, "width": 1.2},
                },
                hovertemplate=(
                    "%{customdata[0]} · B/N %{customdata[2]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[1]:.1%}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )
    month_figure.add_trace(
        go.Scatter(
            name="Density",
            x=month_positions,
            y=monthly_density["부하량"],
            customdata=monthly_density["년월"],
            mode="lines+markers+text",
            text=monthly_density["부하량"],
            texttemplate="<b>%{text:,.2f}</b>",
            textposition="top center",
            textfont={"size": 20, "color": TEXT_COLOR, "family": "Calibri"},
            line={"color": LINE_COLOR, "width": 3},
            marker={
                "color": SURFACE_COLOR,
                "size": 8,
                "line": {"color": LINE_COLOR, "width": 2.0},
            },
            cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:,.2f} 억Gb<extra></extra>",
        ),
        row=2,
        col=1,
    )
    top5_annotations: list[dict[str, Any]] = []
    if not monthly_top5.empty:
        top5_axis_max = max(float(monthly_top5["B/N Capa"].max()) * 1.8, 1.0)
        wafer_capa_label_y = top5_axis_max * 0.04
        slot_offsets = {1: -0.36, 2: -0.18, 3: 0.0, 4: 0.18, 5: 0.36}
        top5_positions = [
            month_position_by_value[month] + slot_offsets[int(rank)]
            for month, rank in zip(monthly_top5["생산계획년월"], monthly_top5["순위"], strict=True)
        ]
        month_figure.add_trace(
            go.Bar(
                name="B/N Capa Top 5",
                x=top5_positions,
                y=monthly_top5["B/N Capa"],
                width=0.15,
                customdata=monthly_top5[["년월", "공정", "확보율", "Wafer Capa"]],
                marker={
                    "color": [capacity_color(rate) for rate in monthly_top5["확보율"]],
                    "line": {"color": LINE_COLOR, "width": 0.8},
                },
                hovertemplate=(
                    "%{customdata[0]} · %{customdata[1]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[2]:.1%}"
                    "<br>Wafer Capa %{customdata[3]:,.0f} 매"
                    "<extra></extra>"
                ),
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        for x_position, capa, rate in zip(
            top5_positions,
            monthly_top5["B/N Capa"],
            monthly_top5["확보율"],
            strict=True,
        ):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": capa,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"<b>{rate:.0%}</b>",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": 10.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": TEXT_COLOR,
                        "family": "Calibri",
                    },
                }
            )
        for x_position, wafer_capa in zip(top5_positions, monthly_top5["Wafer Capa"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": wafer_capa_label_y,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"{wafer_capa / 1_000:,.0f}K",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": -6.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": TEXT_COLOR,
                        "family": "Calibri",
                    },
                }
            )
        for x_position, process in zip(top5_positions, monthly_top5["공정"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": 0,
                    "xref": "x2",
                    "yref": "y2",
                    "text": str(process),
                    "textangle": 270,
                    "xanchor": "right",
                    "yanchor": "top",
                    "xshift": 11.0,
                    "yshift": -8.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": MUTED_TEXT_COLOR,
                        "family": "Calibri",
                    },
                }
            )
    common_layout = {
        "height": LOB_FIGURE_HEIGHT_PX,
        "margin": {
            "l": 0,
            "r": 0,
            "t": DASHBOARD_TITLE_HEIGHT_PX,
            "b": LOB_BOTTOM_MARGIN_PX,
        },
        "barmode": "overlay",
        "bargap": 0.16,
        "plot_bgcolor": SURFACE_COLOR,
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    label_figure.update_layout(**common_layout, showlegend=False)
    month_figure.update_layout(
        **common_layout,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"color": MUTED_TEXT_COLOR, "size": 13},
        },
    )
    append_layout_items(month_figure, annotations=top5_annotations)
    lob_axis_max = max(
        (
            float(value)
            for value in (
                monthly_density["부하량"].max(),
                bottleneck_capacity["B/N Capa"].max(),
            )
            if pd.notna(value)
        ),
        default=1.0,
    )
    lob_axis_max = max(lob_axis_max, 1.0)
    for target_figure in (label_figure, month_figure):
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[0, lob_axis_max * 1.35],
            row=2,
            col=1,
        )
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[
                0,
                top5_axis_max if not monthly_top5.empty else 1.0,
            ],
            row=3,
            col=1,
        )
    for row_number in (2, 3):
        month_figure.update_xaxes(
            tickmode="array",
            tickvals=month_positions,
            ticktext=month_labels,
            showticklabels=False,
            title=None,
            showgrid=False,
            range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
            domain=[0.0, 1.0],
            row=row_number,
            col=1,
        )
        label_figure.update_xaxes(
            showticklabels=False,
            title=None,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            row=row_number,
            col=1,
        )
    panel_bottom = -0.28
    lob_y_domain = month_figure.layout.yaxis.domain
    top5_y_domain = month_figure.layout.yaxis2.domain
    table_y_domain = (lob_table_domains[-1][0], lob_table_domains[0][1])
    append_layout_items(
        label_figure,
        annotations=[
            dashboard_title_annotation("☝️<b>Capa LOB 현황</b>"),
            {
                "x": 0.5,
                "y": (lob_y_domain[0] + lob_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>생산계획 LOB</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": MUTED_TEXT_COLOR,
                    "family": "Malgun Gothic",
                },
            },
            {
                "x": 0.5,
                "y": (top5_y_domain[0] + top5_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>B/N Top 5</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": MUTED_TEXT_COLOR,
                    "family": "Malgun Gothic",
                },
            },
        ],
    )
    horizontal_boundaries = [
        panel_bottom,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    horizontal_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": y_boundary,
            "y1": y_boundary,
            "xref": "paper",
            "yref": "paper",
            "line": {
                "color": GROUP_BORDER_COLOR if boundary_index in {1, 2} else BORDER_COLOR,
                "width": OUTER_BORDER_WIDTH_PX if boundary_index in {1, 2} else 0.8,
            },
            "layer": "above" if boundary_index in {1, 2} else "below",
        }
        for boundary_index, y_boundary in enumerate(horizontal_boundaries)
    ]
    append_layout_items(
        label_figure,
        shapes=[
            *[
                {
                    "type": "rect",
                    "x0": 0,
                    "x1": 1,
                    "y0": y0,
                    "y1": y1,
                    "xref": "paper",
                    "yref": "paper",
                    "fillcolor": SUBTLE_SURFACE_COLOR,
                    "line": {"width": 0},
                    "layer": "below",
                }
                for y0, y1 in (
                    (horizontal_boundaries[0], horizontal_boundaries[1]),
                    (horizontal_boundaries[1], horizontal_boundaries[2]),
                )
            ],
            *[
                {
                    "type": "line",
                    "x0": x_boundary,
                    "x1": x_boundary,
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": BORDER_COLOR, "width": 0.8},
                    "layer": "below",
                }
                for x_boundary in (0.0, 1.0)
            ],
            *horizontal_shapes,
        ],
    )
    append_layout_items(
        month_figure,
        shapes=[
            *[
                {
                    "type": "line",
                    "x0": index / len(month_labels),
                    "x1": index / len(month_labels),
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": BORDER_COLOR, "width": 0.8},
                    "layer": "below",
                }
                for index in range(1, len(month_labels))
            ],
            *horizontal_shapes,
        ],
    )
    add_figure_outer_border(
        label_figure,
        y0=panel_bottom,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    add_figure_outer_border(
        month_figure,
        y0=panel_bottom,
        emphasize_left=False,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    lob_row_boundaries = (
        (lob_table_domains[0][0], OUTER_BORDER_WIDTH_PX, GROUP_BORDER_COLOR),
        (lob_table_domains[1][0], 0.8, BORDER_COLOR),
        (lob_table_domains[2][0], 0.8, BORDER_COLOR),
    )
    lob_row_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": boundary_y,
            "y1": boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": boundary_color, "width": boundary_width},
            "layer": "above",
        }
        for boundary_y, boundary_width, boundary_color in lob_row_boundaries
    ]
    append_layout_items(label_figure, shapes=lob_row_shapes)
    append_layout_items(month_figure, shapes=lob_row_shapes)
    add_quarter_boundaries(month_figure, month_labels, y0=panel_bottom)
    if not show_home_details:
        cached_figures = (label_figure, month_figure)
        store_home_figures(figure_cache_key, cached_figures)
        home_trace.mark("요약 Figure 생성")
        render_home_figures(
            cached_figures,
            month_labels,
            title_column_width,
            month_column_width,
        )
        home_trace.mark("Plotly 전달")
        render_home_performance(
            home_trace,
            cache_hit=False,
            enabled=show_home_performance,
        )
        st.stop()
    detail_month_columns = [month for month in month_labels if month in production_detail.columns]
    displayed_detail = production_detail.copy()
    detail_dimension_values = [
        ["" if pd.isna(value) else str(value) for value in displayed_detail[column]]
        for column in PRODUCTION_DETAIL_DIMENSIONS
    ]
    grouped_dimension_values = [values.copy() for values in detail_dimension_values]
    for dimension_index, values in enumerate(grouped_dimension_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(len(displayed_detail)):
            current_prefix = tuple(
                detail_dimension_values[prefix_index][row_index]
                for prefix_index in range(dimension_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix

    detail_group_indices: list[int] = []
    detail_group_starts: list[int] = []
    previous_product: str | None = None
    group_index = -1
    product_values = detail_dimension_values[0] if detail_dimension_values else []
    for row_index, product in enumerate(product_values):
        if row_index == 0 or product != previous_product:
            group_index += 1
            if row_index > 0:
                detail_group_starts.append(row_index)
        detail_group_indices.append(group_index)
        previous_product = product

    detail_label_row_colors = [
        CLASSIFICATION_BACKGROUND_COLOR
        if group_number % 2 == 0
        else CLASSIFICATION_GROUP_BACKGROUND_COLOR
        for group_number in detail_group_indices
    ]
    detail_month_row_colors = [
        SURFACE_COLOR if group_number % 2 == 0 else GROUP_SURFACE_COLOR
        for group_number in detail_group_indices
    ]
    detail_row_height = 27
    detail_header_height = 36
    detail_figure_height = (
        DASHBOARD_TITLE_HEIGHT_PX
        + detail_header_height
        + max(len(displayed_detail), 1) * detail_row_height
    )
    detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[1.4, 0.6],
            header={
                "values": ["<b>제품</b>", "<b>Stack</b>"],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 15,
                    "family": "Malgun Gothic",
                },
                "height": detail_header_height,
            },
            cells={
                "values": grouped_dimension_values,
                "align": "center",
                "fill_color": [detail_label_row_colors for _ in PRODUCTION_DETAIL_DIMENSIONS],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 14,
                    "family": "Malgun Gothic",
                },
                "height": detail_row_height,
            },
        )
    )
    detail_month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(detail_month_columns),
            header={
                "values": [f"<b>{month}</b>" for month in detail_month_columns],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 15,
                    "family": "Malgun Gothic",
                },
                "height": detail_header_height,
            },
            cells={
                "values": [
                    [
                        "" if pd.isna(value) or float(value) == 0 else f"{float(value):,.0f}K"
                        for value in displayed_detail[month]
                    ]
                    for month in detail_month_columns
                ],
                "align": "center",
                "fill_color": [detail_month_row_colors for _ in detail_month_columns],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 14,
                    "family": "Malgun Gothic",
                },
                "height": detail_row_height,
            },
        )
    )
    detail_layout = {
        "height": detail_figure_height,
        "margin": {"l": 0, "r": 0, "t": DASHBOARD_TITLE_HEIGHT_PX, "b": 0},
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    detail_label_figure.update_layout(**detail_layout)
    append_layout_items(
        detail_label_figure,
        annotations=[dashboard_title_annotation("✌️<b>계획 세부수량</b>")],
    )
    detail_month_figure.update_layout(
        **detail_layout,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    detail_table_height = detail_header_height + max(len(displayed_detail), 1) * detail_row_height
    detail_header_boundary_y = 1 - detail_header_height / detail_table_height
    add_figure_outer_border(detail_label_figure, emphasize_bottom=True)
    add_figure_outer_border(
        detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    detail_header_shape = {
        "type": "line",
        "x0": 0,
        "x1": 1,
        "y0": detail_header_boundary_y,
        "y1": detail_header_boundary_y,
        "xref": "paper",
        "yref": "paper",
        "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
        "layer": "above",
    }
    append_layout_items(
        detail_label_figure,
        shapes=[
            detail_header_shape,
            {
                "type": "line",
                "x0": 1.4 / 2.0,
                "x1": 1.4 / 2.0,
                "y0": 0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": BORDER_COLOR, "width": 0.8},
                "layer": "above",
            },
        ],
    )
    append_layout_items(
        detail_month_figure,
        shapes=[
            detail_header_shape,
            *[
                {
                    "type": "line",
                    "x0": month_index / len(detail_month_columns),
                    "x1": month_index / len(detail_month_columns),
                    "y0": 0,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": BORDER_COLOR, "width": 0.8},
                    "layer": "above",
                }
                for month_index in range(1, len(detail_month_columns))
            ],
        ],
    )
    add_quarter_boundaries(detail_month_figure, detail_month_columns)
    detail_group_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": 1
            - (detail_header_height + group_start * detail_row_height) / detail_table_height,
            "y1": 1
            - (detail_header_height + group_start * detail_row_height) / detail_table_height,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": GROUP_BORDER_COLOR, "width": 1.4},
            "layer": "above",
        }
        for group_start in detail_group_starts
    ]
    append_layout_items(detail_label_figure, shapes=detail_group_shapes)
    append_layout_items(detail_month_figure, shapes=detail_group_shapes)
    bottleneck_detail_ranks = list(range(1, 11))
    bottleneck_detail_labels = "확보율<br>공정명<br>가용대수<br>필요대수<br>Wafer Capa"
    bottleneck_detail_lookup = {
        (int(row["생산계획년월"]), int(row["순위"])): row
        for _, row in monthly_top10_details.iterrows()
    }

    def format_equipment_count(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return ""
        return f"{float(cast(Any, value)):,.1f}대"

    def format_process_name(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return ""
        process = str(value)
        width_units = sum(
            1.0 if unicodedata.east_asian_width(character) in {"F", "W"} else 0.6
            for character in process
        )
        process_font_size = max(8, min(13, round(88 / max(width_units, 1.0))))
        return f'<span style="font-size:{process_font_size}px">{html.escape(process)}</span>'

    def format_bottleneck_detail(month: int, rank: int) -> str:
        row = bottleneck_detail_lookup.get((month, rank))
        if row is None:
            return "<br><br><br><br>"
        rate = "" if pd.isna(row["확보율"]) else f"{float(row['확보율']):.1%}"
        process = format_process_name(row["공정"])
        available = format_equipment_count(row["가용대수"])
        required = format_equipment_count(row["소요대수"])
        wafer_capa = (
            "" if pd.isna(row["Wafer Capa"]) else f"{float(row['Wafer Capa']) / 1_000:,.0f}K"
        )
        return "<br>".join((rate, process, available, required, wafer_capa))

    bottleneck_detail_row_height = 110
    bottleneck_detail_header_height = 36
    bottleneck_detail_figure_height = (
        DASHBOARD_TITLE_HEIGHT_PX
        + bottleneck_detail_header_height
        + len(bottleneck_detail_ranks) * bottleneck_detail_row_height
    )
    bottleneck_detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[0.65, 1.35],
            header={
                "values": ["<b>B/N</b>", "<b>구분</b>"],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 15,
                    "family": "Malgun Gothic",
                },
                "height": bottleneck_detail_header_height,
            },
            cells={
                "values": [
                    [f"<br><br>{rank}<br><br>" for rank in bottleneck_detail_ranks],
                    [bottleneck_detail_labels] * len(bottleneck_detail_ranks),
                ],
                "align": "center",
                "fill_color": CLASSIFICATION_BACKGROUND_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": [20, 13],
                    "family": "Malgun Gothic",
                },
                "height": bottleneck_detail_row_height,
            },
        )
    )
    bottleneck_detail_month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(month_labels),
            header={
                "values": [f"<b>{month}</b>" for month in month_labels],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 15,
                    "family": "Malgun Gothic",
                },
                "height": bottleneck_detail_header_height,
            },
            cells={
                "values": [
                    [format_bottleneck_detail(int(month), rank) for rank in bottleneck_detail_ranks]
                    for month in monthly_density["생산계획년월"]
                ],
                "align": "center",
                "fill_color": SURFACE_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 13,
                    "family": "Malgun Gothic",
                },
                "height": bottleneck_detail_row_height,
            },
        )
    )
    bottleneck_detail_layout = {
        "height": bottleneck_detail_figure_height,
        "margin": {
            "l": 0,
            "r": 0,
            "t": DASHBOARD_TITLE_HEIGHT_PX,
            "b": 0,
        },
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    bottleneck_detail_label_figure.update_layout(**bottleneck_detail_layout)
    append_layout_items(
        bottleneck_detail_label_figure,
        annotations=[dashboard_title_annotation("👌<b>상세 B/N 공정</b>")],
    )
    bottleneck_detail_month_figure.update_layout(
        **bottleneck_detail_layout,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    bottleneck_detail_table_height = (
        bottleneck_detail_header_height
        + len(bottleneck_detail_ranks) * bottleneck_detail_row_height
    )
    bottleneck_detail_boundaries = [
        1 - bottleneck_detail_header_height / bottleneck_detail_table_height,
        *[
            1
            - (bottleneck_detail_header_height + rank_index * bottleneck_detail_row_height)
            / bottleneck_detail_table_height
            for rank_index in range(1, len(bottleneck_detail_ranks))
        ],
    ]
    add_figure_outer_border(
        bottleneck_detail_label_figure,
        emphasize_bottom=True,
    )
    add_figure_outer_border(
        bottleneck_detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    bottleneck_boundary_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": boundary_y,
            "y1": boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": GROUP_BORDER_COLOR, "width": OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for boundary_y in bottleneck_detail_boundaries
    ]
    append_layout_items(bottleneck_detail_label_figure, shapes=bottleneck_boundary_shapes)
    append_layout_items(bottleneck_detail_month_figure, shapes=bottleneck_boundary_shapes)
    add_quarter_boundaries(bottleneck_detail_month_figure, month_labels)
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
    title_column_width,
    month_column_width,
)
home_trace.mark("Plotly 전달")
render_home_performance(
    home_trace,
    cache_hit=False,
    enabled=show_home_performance,
)
