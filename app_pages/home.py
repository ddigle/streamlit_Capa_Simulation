import html
import unicodedata
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from capa_simulation.io.reference_cache import (
    get_reference_cache_version,
    get_reference_tables,
)
from capa_simulation.scenario_state import ensure_active_scenario, scenario_table
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_DIMENSIONS,
    build_bottleneck_capacity,
    build_monthly_bottleneck_top5,
    build_monthly_bottleneck_top10_details,
    build_monthly_bottlenecks,
    build_production_lob_summary,
)
from capa_simulation.services.month_filter import available_month_range, filter_month_range
from capa_simulation.services.simulation_cache import (
    get_monthly_wafer_load,
    get_production_dashboard,
    get_required_equipment,
    get_securement_rate,
    get_unit_capacity,
)
from capa_simulation.settings import APP_NAME, PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

CLASSIFICATION_BACKGROUND_COLOR = "#F4F4F5"
SURFACE_COLOR = "#FFFFFF"
SUBTLE_SURFACE_COLOR = "#F4F4F5"
HEADER_COLOR = "#E4E4E7"
BORDER_COLOR = "#D4D4D8"
TEXT_COLOR = "#27272A"
MUTED_TEXT_COLOR = "#52525B"
LINE_COLOR = "#3F3F46"
SECURE_COLOR = "#D4D4D8"
WARNING_COLOR = "#FDE68A"
SHORTAGE_COLOR = "#FDA4AF"
MONTH_COLUMN_WIDTH_PX = 100
MONTH_SCROLL_THRESHOLD = 10
HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"
HOME_FIGURE_CACHE_MAX_ENTRIES = 8
HOME_FIGURE_SCHEMA_VERSION = 2

HomeFigureSet = tuple[Any, Any, Any, Any, Any, Any]
HomeFigureCacheKey = tuple[int, int, int, int, int, tuple[str, ...], float, float]


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


@st.fragment
def render_home_figures(
    figures: HomeFigureSet,
    month_labels: list[str],
    title_column_width: float,
    month_column_width: float,
) -> None:
    (
        label_figure,
        month_figure,
        detail_label_figure,
        detail_month_figure,
        bottleneck_detail_label_figure,
        bottleneck_detail_month_figure,
    ) = figures
    visible_month_count = min(max(len(month_labels), 1), MONTH_SCROLL_THRESHOLD)

    with st.container(border=True):
        label_column, month_column = st.columns(
            [title_column_width, visible_month_count * month_column_width],
            gap=None,
        )
        with label_column:
            st.plotly_chart(
                label_figure,
                width="stretch",
                key="production_lob_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
            st.plotly_chart(
                detail_label_figure,
                width="stretch",
                key="production_detail_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
            st.plotly_chart(
                bottleneck_detail_label_figure,
                width="stretch",
                key="bottleneck_detail_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
        with month_column:
            month_chart_width = len(month_labels) * MONTH_COLUMN_WIDTH_PX
            st.html(
                f"""
                <style>
                .st-key-production_lob_month_scroll {{
                    overflow-x: auto;
                    overflow-y: hidden;
                    padding-bottom: 0.25rem;
                }}
                .st-key-production_lob_month_canvas {{
                    width: {month_chart_width}px !important;
                    min-width: {month_chart_width}px !important;
                    max-width: none !important;
                }}
                </style>
                """
            )
            with st.container(key="production_lob_month_scroll"):
                with st.container(key="production_lob_month_canvas"):
                    st.plotly_chart(
                        month_figure,
                        width="stretch",
                        key="production_lob_months",
                        config={"displayModeBar": False, "responsive": True},
                    )
                    st.plotly_chart(
                        detail_month_figure,
                        width="stretch",
                        key="production_detail_months",
                        config={"displayModeBar": False, "staticPlot": True},
                    )
                    st.plotly_chart(
                        bottleneck_detail_month_figure,
                        width="stretch",
                        key="bottleneck_detail_months",
                        config={"displayModeBar": False, "staticPlot": True},
                    )


st.title(APP_NAME)

workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_version = get_reference_cache_version()
    reference_tables = get_reference_tables(str(workbook.resolve()))
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    selected_start, selected_end = selected_month_range()
    source_start, source_end = available_month_range(reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    effective_start = max(selected_start, source_start)
    effective_end = min(selected_end, source_end)
    if effective_start > effective_end:
        raise ValueError("선택 범위에 생산계획 데이터가 없습니다.")
    show_applied_month_range(effective_start, effective_end)

    simulation_plan = filter_month_range(
        scenario_table(active_scenario, "RQ_PKG_PLAN"),
        effective_start,
        effective_end,
        "RQ_PKG_PLAN",
    )
    simulation_yield = filter_month_range(
        scenario_table(active_scenario, "RQ_YLD"),
        effective_start,
        effective_end,
        "RQ_YLD",
    )
    monthly_density, production_detail = get_production_dashboard(
        simulation_plan,
        reference_tables["RQ_CHIP_EQ"],
        reference_tables["RQ_DISPLAY_ORDER"],
    )
    monthly_wafer = get_monthly_wafer_load(
        simulation_plan,
        simulation_yield,
        reference_tables["RQ_CHIP_QTY"],
    )

    unit_capacity = get_unit_capacity(
        upeh=filter_month_range(
            scenario_table(active_scenario, "RQ_UPEH"),
            effective_start,
            effective_end,
            "RQ_UPEH",
        ),
        run_rate=filter_month_range(
            scenario_table(active_scenario, "RQ_RUN_RATE"),
            effective_start,
            effective_end,
            "RQ_RUN_RATE",
        ),
        vital=filter_month_range(
            scenario_table(active_scenario, "RQ_VITAL"),
            effective_start,
            effective_end,
            "RQ_VITAL",
        ),
        module=reference_tables["RQ_MODULE"],
        run_day=filter_month_range(
            scenario_table(active_scenario, "RQ_RUN_DAY"),
            effective_start,
            effective_end,
            "RQ_RUN_DAY",
        ),
        lot_ratio=filter_month_range(
            scenario_table(active_scenario, "RQ_LOT_RATIO"),
            effective_start,
            effective_end,
            "RQ_LOT_RATIO",
        ),
        wf_ratio=filter_month_range(
            scenario_table(active_scenario, "RQ_WF_RATIO"),
            effective_start,
            effective_end,
            "RQ_WF_RATIO",
        ),
    )
    required_equipment = get_required_equipment(
        reqb=filter_month_range(
            reference_tables["RQ_REQB"],
            effective_start,
            effective_end,
            "RQ_REQB",
        ),
        plan=simulation_plan,
        yield_data=simulation_yield,
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    securement_rate = get_securement_rate(
        filter_month_range(
            reference_tables["RQ_EQP_AVBL"],
            effective_start,
            effective_end,
            "RQ_EQP_AVBL",
        ),
        required_equipment,
    )
except (KeyError, OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

process_options = sorted(
    securement_rate["공정"].astype("string").str.strip().dropna().unique().tolist()
)
included_processes = []
with st.sidebar.container(border=True):
    st.markdown("#### :material/filter_alt: B/N 집계 공정")
    st.markdown("**판정 기준**")
    secure_threshold_percent = st.number_input(
        "확보 기준 (%)",
        min_value=0.0,
        value=109.5,
        step=0.1,
        key="dashboard_secure_threshold_percent",
        persist_state="session",
    )
    warning_threshold_percent = st.number_input(
        "경고 기준 (%)",
        min_value=0.0,
        value=99.5,
        step=0.1,
        key="dashboard_warning_threshold_percent",
        persist_state="session",
    )
    if warning_threshold_percent > secure_threshold_percent:
        st.warning("경고 기준은 확보 기준보다 클 수 없습니다.")
    st.caption("끄면 대시보드의 B/N 후보에서 제외됩니다.")
    if not process_options:
        st.caption("집계 가능한 공정이 없습니다.")
    else:
        for process in process_options:
            if st.toggle(
                process,
                value=True,
                key=f"dashboard_bottleneck_process_{process}",
                persist_state="session",
            ):
                included_processes.append(process)

monthly_bottlenecks = build_monthly_bottlenecks(
    securement_rate,
    included_processes=included_processes,
)
bottleneck_capacity = build_bottleneck_capacity(monthly_density, monthly_bottlenecks)
monthly_top5 = build_monthly_bottleneck_top5(
    securement_rate,
    monthly_density,
    included_processes=included_processes,
    monthly_wafer=monthly_wafer,
)
monthly_top10_details = build_monthly_bottleneck_top10_details(
    securement_rate,
    monthly_wafer,
    included_processes=included_processes,
)
lob_summary = build_production_lob_summary(
    monthly_density,
    monthly_wafer,
    monthly_bottlenecks,
)
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
)
cached_figures = home_figure_cache().get(figure_cache_key)


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
        "row_heights": [143, 143, 143],
    }
    label_figure = make_subplots(**subplot_options)
    month_figure = make_subplots(**subplot_options)
    label_figure.add_trace(
        go.Table(
            columnwidth=[title_column_width],
            header={
                "values": ["<b>구분</b>"],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 21,
                    "family": "Malgun Gothic",
                },
                "height": 36,
            },
            cells={
                "values": [["Density (억Gb)", "Wafer 계획", "Wafer Capa"]],
                "align": "center",
                "fill_color": SUBTLE_SURFACE_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 20,
                    "family": "Malgun Gothic",
                    "weight": "bold",
                },
                "height": 30,
            },
        ),
        row=1,
        col=1,
    )
    month_figure.add_trace(
        go.Table(
            columnwidth=[month_column_width] * len(month_labels),
            header={
                "values": [f"<b>{month}</b>" for month in month_labels],
                "align": "center",
                "fill_color": HEADER_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 21,
                    "family": "Malgun Gothic",
                },
                "height": 36,
            },
            cells={
                "values": [
                    [
                        f"{row['부하량']:,.2f}",
                        f"{row['Wafer 부하량'] / 1_000:,.0f}K",
                        f"{row['Wafer Capa'] / 1_000:,.0f}K",
                    ]
                    for _, row in lob_summary.iterrows()
                ],
                "align": "center",
                "fill_color": SURFACE_COLOR,
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 20,
                    "family": "Malgun Gothic",
                },
                "height": 30,
            },
        ),
        row=1,
        col=1,
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
        "height": 600,
        "margin": {"l": 0, "r": 3, "t": 58, "b": 130},
        "barmode": "overlay",
        "bargap": 0.16,
        "plot_bgcolor": SURFACE_COLOR,
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    label_figure.update_layout(**common_layout, showlegend=False)
    month_figure.update_layout(
        **common_layout,
        annotations=top5_annotations,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.035,
            "xanchor": "right",
            "x": 1,
            "font": {"color": MUTED_TEXT_COLOR, "size": 13},
        },
    )
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
    table_y_domain = month_figure.data[0].domain.y
    label_figure.add_annotation(
        x=0,
        y=1.035,
        xref="paper",
        yref="paper",
        text="☝️<b>Capa LOB 현황</b>",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"size": 20, "color": TEXT_COLOR, "family": "Malgun Gothic"},
    )
    label_figure.add_annotation(
        x=0.5,
        y=(lob_y_domain[0] + lob_y_domain[1]) / 2,
        xref="paper",
        yref="paper",
        text="<b>생산계획 LOB</b>",
        showarrow=False,
        font={"size": 20, "color": MUTED_TEXT_COLOR, "family": "Malgun Gothic"},
    )
    label_figure.add_annotation(
        x=0.5,
        y=(top5_y_domain[0] + top5_y_domain[1]) / 2,
        xref="paper",
        yref="paper",
        text="<b>B/N Top 5</b>",
        showarrow=False,
        font={"size": 20, "color": MUTED_TEXT_COLOR, "family": "Malgun Gothic"},
    )
    horizontal_boundaries = [
        panel_bottom,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    for y0, y1 in (
        (horizontal_boundaries[0], horizontal_boundaries[1]),
        (horizontal_boundaries[1], horizontal_boundaries[2]),
    ):
        label_figure.add_shape(
            type="rect",
            x0=0,
            x1=1,
            y0=y0,
            y1=y1,
            xref="paper",
            yref="paper",
            fillcolor=SUBTLE_SURFACE_COLOR,
            line={"width": 0},
            layer="below",
        )
    for x_boundary in (0.0, 1.0):
        label_figure.add_shape(
            type="line",
            x0=x_boundary,
            x1=x_boundary,
            y0=panel_bottom,
            y1=1,
            xref="paper",
            yref="paper",
            line={"color": BORDER_COLOR, "width": 0.8},
            layer="below",
        )
    for x_boundary in [index / len(month_labels) for index in range(len(month_labels) + 1)]:
        month_figure.add_shape(
            type="line",
            x0=x_boundary,
            x1=x_boundary,
            y0=panel_bottom,
            y1=1,
            xref="paper",
            yref="paper",
            line={"color": BORDER_COLOR, "width": 0.8},
            layer="below",
        )
    for target_figure in (label_figure, month_figure):
        for y_boundary in horizontal_boundaries:
            target_figure.add_shape(
                type="line",
                x0=0,
                x1=1,
                y0=y_boundary,
                y1=y_boundary,
                xref="paper",
                yref="paper",
                line={"color": BORDER_COLOR, "width": 0.8},
                layer="below",
            )
    detail_month_columns = [month for month in month_labels if month in production_detail.columns]
    displayed_detail = production_detail.copy()
    detail_row_height = 25
    detail_header_height = 36
    detail_title_height = 34
    detail_figure_height = (
        detail_title_height
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
                "line_color": BORDER_COLOR,
                "font": {
                    "color": TEXT_COLOR,
                    "size": 15,
                    "family": "Malgun Gothic",
                },
                "height": detail_header_height,
            },
            cells={
                "values": [
                    ["" if pd.isna(value) else str(value) for value in displayed_detail[column]]
                    for column in PRODUCTION_DETAIL_DIMENSIONS
                ],
                "align": "center",
                "fill_color": CLASSIFICATION_BACKGROUND_COLOR,
                "line_color": BORDER_COLOR,
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
                "line_color": BORDER_COLOR,
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
                "fill_color": SURFACE_COLOR,
                "line_color": BORDER_COLOR,
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
        "margin": {"l": 0, "r": 3, "t": detail_title_height, "b": 0},
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    detail_label_figure.update_layout(
        **detail_layout,
        title={
            "text": "✌️<b>계획 세부수량</b>",
            "x": 0,
            "xanchor": "left",
            "y": 0.98,
            "yanchor": "top",
            "font": {"size": 20, "color": TEXT_COLOR, "family": "Malgun Gothic"},
        },
    )
    detail_month_figure.update_layout(
        **detail_layout,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
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
    bottleneck_detail_title_height = 56
    bottleneck_detail_figure_height = (
        bottleneck_detail_title_height
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
                    [str(rank) for rank in bottleneck_detail_ranks],
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
            "r": 3,
            "t": bottleneck_detail_title_height,
            "b": 0,
        },
        "paper_bgcolor": SURFACE_COLOR,
        "font": {"color": TEXT_COLOR, "family": "Malgun Gothic"},
    }
    bottleneck_detail_label_figure.update_layout(
        **bottleneck_detail_layout,
        title={
            "text": "👌<b>상세 B/N 공정</b>",
            "x": 0,
            "xanchor": "left",
            "y": 0.995,
            "yanchor": "top",
            "font": {"size": 20, "color": TEXT_COLOR, "family": "Malgun Gothic"},
        },
    )
    bottleneck_detail_month_figure.update_layout(
        **bottleneck_detail_layout,
        width=len(month_labels) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
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

render_home_figures(
    cached_figures,
    month_labels,
    title_column_width,
    month_column_width,
)
