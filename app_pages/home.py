from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_DIMENSIONS,
    build_bottleneck_capacity,
    build_monthly_bottlenecks,
    build_production_dashboard,
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

with st.container(border=True):
    st.subheader("생산계획 현황")
    figure = go.Figure()
    if bottleneck_capacity["B/N Capa"].notna().any():
        figure.add_trace(
            go.Bar(
                name="B/N 공정 Capa",
                x=bottleneck_capacity["년월"],
                y=bottleneck_capacity["B/N Capa"],
                customdata=bottleneck_capacity[["확보율", "공정"]],
                text=bottleneck_capacity["확보율"],
                texttemplate="%{text:.1%}",
                textposition="inside",
                insidetextanchor="start",
                textfont={"color": "white"},
                marker={"color": "#90CAF9"},
                hovertemplate=(
                    "%{x}<br>B/N %{customdata[1]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[0]:.1%}<extra></extra>"
                ),
            )
        )
    figure.add_trace(
        go.Scatter(
            name="양산 부하량",
            x=monthly_density["년월"],
            y=monthly_density["부하량"],
            mode="lines+markers+text",
            text=monthly_density["부하량"],
            texttemplate="%{text:,.2f}",
            textposition="top center",
            line={"color": "#2E7D32", "width": 3},
            marker={"color": "#2E7D32", "size": 8},
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y:,.2f} 억Gb<extra></extra>",
        )
    )
    figure.update_layout(
        height=330,
        margin={"l": 20, "r": 20, "t": 35, "b": 20},
        xaxis={"title": "생산계획년월", "type": "category"},
        yaxis={"title": "부하량 / B/N Capa (억Gb)", "rangemode": "tozero"},
        barmode="overlay",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
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
