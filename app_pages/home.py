from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_DIMENSIONS,
    build_bottleneck_capacity,
    build_monthly_bottleneck_top5,
    build_monthly_bottlenecks,
    build_monthly_wafer_load,
    build_production_dashboard,
    build_production_lob_summary,
)
from capa_simulation.services.month_filter import available_month_range, filter_month_range
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.unit_capacity import calculate_unit_capacity
from capa_simulation.settings import APP_NAME, PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

CLASSIFICATION_BACKGROUND_COLOR = "#F0F2F6"


@st.cache_data(show_spinner="홈 대시보드 데이터를 불러오는 중입니다.")
def load_data(workbook_path: str, modified_time_ns: int) -> dict[str, pd.DataFrame]:
    del modified_time_ns
    return load_reference_tables(Path(workbook_path))


def selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


st.title(APP_NAME)

workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_tables = load_data(str(workbook.resolve()), workbook.stat().st_mtime_ns)
    selected_start, selected_end = selected_month_range()
    source_start, source_end = available_month_range(
        reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN"
    )
    effective_start = max(selected_start, source_start)
    effective_end = min(selected_end, source_end)
    if effective_start > effective_end:
        raise ValueError("선택 범위에 생산계획 데이터가 없습니다.")
    show_applied_month_range(effective_start, effective_end)

    load_inputs = st.session_state.get("load_conversion_inputs", {})
    load_inputs_are_current = (
        load_inputs.get("workbook_mtime_ns") == workbook.stat().st_mtime_ns
        and load_inputs.get("start_month") == effective_start
        and load_inputs.get("end_month") == effective_end
    )
    if load_inputs_are_current:
        simulation_plan = load_inputs["plan"]
        simulation_yield = load_inputs["yield"]
    else:
        simulation_plan = filter_month_range(
            reference_tables["RQ_PKG_PLAN"],
            effective_start,
            effective_end,
            "RQ_PKG_PLAN",
        )
        simulation_yield = filter_month_range(
            reference_tables["RQ_YLD"],
            effective_start,
            effective_end,
            "RQ_YLD",
        )
    monthly_density, production_detail = build_production_dashboard(
        simulation_plan,
        reference_tables["RQ_CHIP_EQ"],
    )
    monthly_wafer = build_monthly_wafer_load(
        simulation_plan,
        simulation_yield,
        reference_tables["RQ_CHIP_QTY"],
    )

    capacity_result = st.session_state.get("unit_capacity_result", {})
    capacity_result_is_current = (
        capacity_result.get("workbook_mtime_ns") == workbook.stat().st_mtime_ns
        and capacity_result.get("start_month") == effective_start
        and capacity_result.get("end_month") == effective_end
    )
    if capacity_result_is_current:
        unit_capacity = capacity_result["data"]
    else:
        unit_capacity = calculate_unit_capacity(
            upeh=filter_month_range(
                reference_tables["RQ_UPEH"],
                effective_start,
                effective_end,
                "RQ_UPEH",
            ),
            run_rate=filter_month_range(
                reference_tables["RQ_RUN_RATE"],
                effective_start,
                effective_end,
                "RQ_RUN_RATE",
            ),
            vital=filter_month_range(
                reference_tables["RQ_VITAL"],
                effective_start,
                effective_end,
                "RQ_VITAL",
            ),
            module=reference_tables["RQ_MODULE"],
            run_day=filter_month_range(
                reference_tables["RQ_RUN_DAY"],
                effective_start,
                effective_end,
                "RQ_RUN_DAY",
            ),
            lot_ratio=filter_month_range(
                reference_tables["RQ_LOT_RATIO"],
                effective_start,
                effective_end,
                "RQ_LOT_RATIO",
            ),
            wf_ratio=filter_month_range(
                reference_tables["RQ_WF_RATIO"],
                effective_start,
                effective_end,
                "RQ_WF_RATIO",
            ),
        )
    required_equipment = calculate_required_equipment(
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
    securement_rate = calculate_securement_rate(
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
)
lob_summary = build_production_lob_summary(
    monthly_density,
    monthly_wafer,
    monthly_bottlenecks,
)
secure_threshold = secure_threshold_percent / 100.0
warning_threshold = warning_threshold_percent / 100.0


def capacity_color(rate: float) -> str:
    if rate > secure_threshold:
        return "#D9D9D9"
    if rate >= warning_threshold:
        return "#FFF2B2"
    return "#F8C8D0"

with st.container(border=True):
    st.subheader("생산계획 현황")
    month_labels = monthly_density["년월"].tolist()
    month_positions = list(range(len(month_labels)))
    month_position_by_value = dict(
        zip(monthly_density["생산계획년월"], month_positions, strict=True)
    )
    figure = make_subplots(
        rows=3,
        cols=1,
        specs=[[{"type": "table"}], [{"type": "xy"}], [{"type": "xy"}]],
        shared_xaxes=False,
        vertical_spacing=0.09,
        row_heights=[0.27, 0.45, 0.28],
    )
    title_column_width = 1.30
    month_column_width = 1.0
    chart_domain_start = title_column_width / (
        title_column_width + len(month_labels) * month_column_width
    )
    figure.add_trace(
        go.Table(
            columnwidth=[title_column_width, *([month_column_width] * len(month_labels))],
            header={
                "values": ["<b>구분</b>", *[f"<b>{month}</b>" for month in month_labels]],
                "align": ["left", *(["center"] * len(month_labels))],
                "fill_color": "#E5E7EB",
                "line_color": "#808080",
                "font": {
                    "color": "#222222",
                    "size": 24,
                    "family": "Malgun Gothic",
                },
                "height": 38,
            },
            cells={
                "values": [
                    ["생산계획 (억Gb)", "생산계획 (Wafer)", "Wafer Capa"],
                    *[
                        [
                            f"{row['부하량']:,.2f}",
                            f"{row['Wafer 부하량'] / 1_000:,.2f}",
                            f"{row['Wafer Capa'] / 1_000:,.2f}",
                        ]
                        for _, row in lob_summary.iterrows()
                    ],
                ],
                "align": ["left", *(["center"] * len(month_labels))],
                "fill_color": ["#F0F2F6", *(["#FFFFFF"] * len(month_labels))],
                "line_color": "#A0A0A0",
                "font": {
                    "color": "#222222",
                    "size": 18,
                    "family": "Malgun Gothic",
                },
                "height": 38,
            },
        ),
        row=1,
        col=1,
    )
    if bottleneck_capacity["B/N Capa"].notna().any():
        figure.add_trace(
            go.Bar(
                name="B/N 공정",
                x=[
                    month_position_by_value[month]
                    for month in bottleneck_capacity["생산계획년월"]
                ],
                y=bottleneck_capacity["B/N Capa"],
                customdata=bottleneck_capacity[["년월", "확보율", "공정"]],
                text=bottleneck_capacity["확보율"],
                texttemplate="<b>%{text:.1%}</b>",
                textposition="inside",
                insidetextanchor="start",
                textfont={"color": "#111111", "size": 22, "family": "Calibri"},
                marker={
                    "color": [
                        capacity_color(rate)
                        for rate in bottleneck_capacity["확보율"]
                    ],
                    "line": {"color": "#4A4A4A", "width": 1},
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
    figure.add_trace(
        go.Scatter(
            name="생산계획(억Gb)",
            x=month_positions,
            y=monthly_density["부하량"],
            customdata=monthly_density["년월"],
            mode="lines+markers+text",
            text=monthly_density["부하량"],
            texttemplate="%{text:,.2f}",
            textposition="top center",
            textfont={"size": 24, "family": "Calibri"},
            line={"color": "#4A4A4A", "width": 3},
            marker={"color": "#4A4A4A", "size": 8},
            cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:,.2f} 억Gb<extra></extra>",
        ),
        row=2,
        col=1,
    )
    if not monthly_top5.empty:
        slot_offsets = {1: -0.28, 2: -0.14, 3: 0.0, 4: 0.14, 5: 0.28}
        top5_positions = [
            month_position_by_value[month] + slot_offsets[int(rank)]
            for month, rank in zip(
                monthly_top5["생산계획년월"], monthly_top5["순위"], strict=True
            )
        ]
        figure.add_trace(
            go.Bar(
                name="B/N Capa Top 5",
                x=top5_positions,
                y=monthly_top5["B/N Capa"],
                width=0.11,
                customdata=monthly_top5[["년월", "공정", "확보율"]],
                text=monthly_top5["확보율"],
                texttemplate="<b>%{text:.1%}</b>",
                textposition="outside",
                textangle=270,
                textfont={"size": 22, "color": "#222222", "family": "Calibri"},
                cliponaxis=False,
                marker={
                    "color": [capacity_color(rate) for rate in monthly_top5["확보율"]],
                    "line": {"color": "#4A4A4A", "width": 1.5},
                },
                hovertemplate=(
                    "%{customdata[0]} · %{customdata[1]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[2]:.1%}<extra></extra>"
                ),
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        for x_position, process in zip(
            top5_positions, monthly_top5["공정"], strict=True
        ):
            figure.add_annotation(
                x=x_position,
                y=0,
                text=str(process),
                textangle=270,
                xanchor="right",
                yanchor="top",
                yshift=-18,
                showarrow=False,
                font={"size": 24, "color": "#333333", "family": "Calibri"},
                row=3,
                col=1,
            )
    figure.update_layout(
        height=880,
        margin={"l": 20, "r": 20, "t": 55, "b": 220},
        barmode="overlay",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.08},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    figure.update_xaxes(
        tickmode="array",
        tickvals=month_positions,
        ticktext=month_labels,
        showticklabels=False,
        title=None,
        showgrid=False,
        range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
        domain=[chart_domain_start, 1.0],
        row=2,
        col=1,
    )
    figure.update_xaxes(
        tickmode="array",
        tickvals=month_positions,
        ticktext=month_labels,
        showticklabels=False,
        title=None,
        showgrid=False,
        range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
        domain=[chart_domain_start, 1.0],
        row=3,
        col=1,
    )
    figure.update_yaxes(
        title=None,
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        rangemode="tozero",
        row=2,
        col=1,
    )
    figure.update_yaxes(
        title=None,
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        rangemode="tozero",
        autorange=True,
        row=3,
        col=1,
    )
    month_area_width = 1.0 - chart_domain_start
    month_boundaries = [
        chart_domain_start + month_area_width * index / len(month_labels)
        for index in range(len(month_labels) + 1)
    ]
    panel_bottom = -0.22
    lob_y_domain = figure.layout.yaxis.domain
    top5_y_domain = figure.layout.yaxis2.domain
    table_y_domain = figure.data[0].domain.y
    horizontal_boundaries = [
        panel_bottom,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    for x_boundary in [0.0, *month_boundaries]:
        figure.add_shape(
            type="line",
            x0=x_boundary,
            x1=x_boundary,
            y0=panel_bottom,
            y1=1,
            xref="paper",
            yref="paper",
            line={"color": "#A0A0A0", "width": 1},
            layer="below",
        )
    for y_boundary in horizontal_boundaries:
        figure.add_shape(
            type="line",
            x0=0,
            x1=1,
            y0=y_boundary,
            y1=y_boundary,
            xref="paper",
            yref="paper",
            line={"color": "#A0A0A0", "width": 1},
            layer="below",
        )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.markdown("#### 세부수량")
    month_columns = [
        column
        for column in production_detail.columns
        if column not in PRODUCTION_DETAIL_DIMENSIONS
    ]
    displayed_detail = production_detail.copy()
    displayed_detail[month_columns] = displayed_detail[month_columns].mask(
        displayed_detail[month_columns].eq(0)
    )
    styled_detail = displayed_detail.style.set_properties(
        subset=pd.Index(PRODUCTION_DETAIL_DIMENSIONS),
        **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
    )
    st.dataframe(
        styled_detail,
        hide_index=True,
        width="content",
        height=500,
        row_height=25,
        column_config={
            **{
                column: st.column_config.TextColumn(
                    column,
                    alignment="center",
                    pinned=True,
                )
                for column in PRODUCTION_DETAIL_DIMENSIONS
            },
            **{
                month: st.column_config.NumberColumn(
                    month,
                    width=80,
                    format="%,.2f",
                    alignment="center",
                )
                for month in month_columns
            },
        },
    )

with st.container(border=True):
    st.subheader("주요공정 확보율 현황")
    if monthly_bottlenecks.empty:
        st.info("선택 범위에 산출 가능한 Bottleneck 공정이 없습니다.")
    else:
        bottleneck_figure = go.Figure(
            go.Bar(
                x=monthly_bottlenecks["축레이블"],
                y=monthly_bottlenecks["확보율"],
                text=monthly_bottlenecks["확보율"],
                texttemplate="%{text:.1%}",
                textposition="outside",
                cliponaxis=False,
                marker={"color": "#EF6C00"},
                hovertemplate="%{x}<br>확보율 %{y:.1%}<extra></extra>",
            )
        )
        bottleneck_figure.update_layout(
            height=330,
            margin={"l": 20, "r": 20, "t": 35, "b": 20},
            xaxis={"title": "생산계획년월 / Bottleneck 공정", "type": "category"},
            yaxis={"title": "확보율", "tickformat": ".0%", "rangemode": "tozero"},
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            bottleneck_figure,
            width="stretch",
            config={"displayModeBar": False},
        )
