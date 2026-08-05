from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.equipment_count import (
    DETAILED_EQUIPMENT_DIMENSIONS,
    EQUIPMENT_DIMENSIONS,
    build_equipment_count_table,
)
from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
)
from capa_simulation.services.required_equipment import (
    RESULT_DIMENSIONS,
    calculate_required_equipment,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import (
    SECUREMENT_DIMENSIONS,
    calculate_securement_rate,
    securement_rate_to_month_table,
)
from capa_simulation.services.unit_capacity import calculate_unit_capacity
from capa_simulation.settings import PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

TAB_NAMES = ("📊 확보율", "📊 소요대수", "설비대수")
CLASSIFICATION_BACKGROUND_COLOR = "#F0F2F6"
DISPLAY_COLUMN_LABELS = {
    "Area_Name": "Area",
    "양산구분": "양산",
    "제품정보": "제품",
    "Capa Code": "PKG Code",
    "WF 구분": "속성",
}


@st.cache_data(show_spinner="공정별 확보율 기준정보를 불러오는 중입니다.")
def load_data(workbook_path: str, modified_time_ns: int) -> dict[str, pd.DataFrame]:
    del modified_time_ns
    return load_reference_tables(Path(workbook_path))


def selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


st.title("공정별 확보율")
availability_tab, required_tab, equipment_tab = st.tabs(TAB_NAMES)

workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_tables = load_data(str(workbook.resolve()), workbook.stat().st_mtime_ns)
    selected_start, selected_end = selected_month_range()
    source_start, source_end = available_month_range(reference_tables["RQ_REQB"], "RQ_REQB")
    effective_start = max(selected_start, source_start)
    effective_end = min(selected_end, source_end)
    if effective_start > effective_end:
        raise ValueError("선택 범위에 소요대수 산출 기준이 없습니다.")
    show_applied_month_range(effective_start, effective_end)

    monthly_table_names = (
        "RQ_REQB",
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
    )
    filtered = {
        table_name: filter_month_range(
            reference_tables[table_name], effective_start, effective_end, table_name
        )
        for table_name in monthly_table_names
    }
    load_inputs = st.session_state.get("load_conversion_inputs", {})
    load_inputs_are_current = (
        load_inputs.get("workbook_mtime_ns") == workbook.stat().st_mtime_ns
        and load_inputs.get("start_month") == effective_start
        and load_inputs.get("end_month") == effective_end
    )
    simulation_plan = (
        load_inputs["plan"] if load_inputs_are_current else filtered["RQ_PKG_PLAN"]
    )
    simulation_yield = (
        load_inputs["yield"] if load_inputs_are_current else filtered["RQ_YLD"]
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
            upeh=filtered["RQ_UPEH"],
            run_rate=filtered["RQ_RUN_RATE"],
            vital=filtered["RQ_VITAL"],
            module=reference_tables["RQ_MODULE"],
            run_day=filtered["RQ_RUN_DAY"],
            lot_ratio=filtered["RQ_LOT_RATIO"],
            wf_ratio=filtered["RQ_WF_RATIO"],
        )
    required_equipment = calculate_required_equipment(
        reqb=filtered["RQ_REQB"],
        plan=simulation_plan,
        yield_data=simulation_yield,
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    required_table = required_equipment_to_month_table(required_equipment)
    required_table = apply_display_order(
        required_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 확보율",
        "소요대수",
    )
    available_equipment_table = build_equipment_count_table(
        filtered["RQ_EQP_OWN"],
        filtered["RQ_EQP_LENT"],
        filtered["RQ_EQP_AVBL"],
        detailed=False,
    )
    available_equipment_table = apply_display_order(
        available_equipment_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 확보율",
        "설비대수",
    )
    detailed_equipment_table = build_equipment_count_table(
        filtered["RQ_EQP_OWN"],
        filtered["RQ_EQP_LENT"],
        filtered["RQ_EQP_AVBL"],
        detailed=True,
    )
    detailed_equipment_table = apply_display_order(
        detailed_equipment_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 확보율",
        "설비대수",
    )
    securement_rate = calculate_securement_rate(
        filtered["RQ_EQP_AVBL"],
        required_equipment,
    )
    securement_table = securement_rate_to_month_table(securement_rate)
    securement_table = apply_display_order(
        securement_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 확보율",
        "확보율",
    )
except (KeyError, OSError, ValueError) as exc:
    with availability_tab:
        st.error(str(exc))
    with required_tab:
        st.error(str(exc))
    with equipment_tab:
        st.error(str(exc))
else:
    with availability_tab:
        st.caption("월간 공정별 확보율 (가용대수 ÷ 소요대수)")
        securement_filter_keys = [
            f"securement_filter_{column}" for column in SECUREMENT_DIMENSIONS
        ]
        with st.expander("필터", expanded=False):
            if st.button("필터 초기화", key="securement_filter_reset"):
                for filter_key in securement_filter_keys:
                    st.session_state[filter_key] = []
            securement_filters: dict[str, list[str]] = {}
            with st.container(horizontal=True, gap="small"):
                for index, column in enumerate(SECUREMENT_DIMENSIONS):
                    options = securement_table[column].dropna().drop_duplicates().tolist()
                    securement_filters[column] = st.multiselect(
                        column,
                        options=options,
                        key=securement_filter_keys[index],
                        placeholder="전체",
                        width=180,
                    )

        displayed_securement_table = securement_table.copy()
        for column, selected_values in securement_filters.items():
            if selected_values:
                displayed_securement_table = displayed_securement_table.loc[
                    displayed_securement_table[column].isin(selected_values)
                ]
        securement_month_columns = [
            column
            for column in displayed_securement_table.columns
            if column not in SECUREMENT_DIMENSIONS
        ]
        styled_securement_table = displayed_securement_table.style.set_properties(
            subset=pd.Index(SECUREMENT_DIMENSIONS),
            **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
        )
        st.dataframe(
            styled_securement_table,
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
                    for column in SECUREMENT_DIMENSIONS
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        format="percent",
                        alignment="center",
                    )
                    for month in securement_month_columns
                },
            },
        )

    with required_tab:
        st.caption("월간 소요대수 (부하량 ÷ 대당 Capa)")
        show_detail = st.toggle(
            "상세",
            key="required_equipment_detail",
            width=90,
        )
        all_month_columns = [
            column for column in required_table.columns if column not in RESULT_DIMENSIONS
        ]
        if show_detail:
            table_dimensions = RESULT_DIMENSIONS
            view_table = required_table.copy()
        else:
            table_dimensions = ["Area_Name", "공정"]
            view_table = (
                required_table.groupby(table_dimensions, as_index=False, sort=False)[
                    all_month_columns
                ]
                .sum(min_count=1)
            )

        filter_keys = [
            f"required_equipment_filter_{column}" for column in table_dimensions
        ]
        with st.expander("필터", expanded=False):
            if st.button("필터 초기화", key="required_equipment_filter_reset"):
                for filter_key in filter_keys:
                    st.session_state[filter_key] = []
            selected_filters: dict[str, list[str]] = {}
            with st.container(horizontal=True, gap="small"):
                for index, column in enumerate(table_dimensions):
                    options = view_table[column].dropna().drop_duplicates().tolist()
                    selected_filters[column] = st.multiselect(
                        DISPLAY_COLUMN_LABELS.get(column, column),
                        options=options,
                        key=filter_keys[index],
                        placeholder="전체",
                        width=180,
                    )

        filtered_required_table = view_table.copy()
        for column, selected_values in selected_filters.items():
            if selected_values:
                filtered_required_table = filtered_required_table.loc[
                    filtered_required_table[column].isin(selected_values)
                ]
        month_columns = [
            column
            for column in filtered_required_table.columns
            if column not in table_dimensions
        ]
        displayed_table = filtered_required_table.copy()
        displayed_table[month_columns] = displayed_table[month_columns].mask(
            displayed_table[month_columns].eq(0)
        )
        styled_table = displayed_table.style.set_properties(
            subset=pd.Index(table_dimensions),
            **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
        )
        st.dataframe(
            styled_table,
            hide_index=True,
            width="content",
            height=500,
            row_height=25,
            column_config={
                **{
                    column: st.column_config.TextColumn(
                        DISPLAY_COLUMN_LABELS.get(column, column),
                        alignment="center",
                        pinned=True,
                    )
                    for column in table_dimensions
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

    with equipment_tab:
        st.caption("월간 설비대수")
        show_equipment_detail = st.toggle(
            "상세",
            key="equipment_count_detail",
            width=90,
        )
        if show_equipment_detail:
            equipment_table = detailed_equipment_table.copy()
            equipment_dimensions = DETAILED_EQUIPMENT_DIMENSIONS
        else:
            equipment_table = available_equipment_table.copy()
            equipment_dimensions = EQUIPMENT_DIMENSIONS

        equipment_filter_keys = [
            f"equipment_count_filter_{column}" for column in equipment_dimensions
        ]
        with st.expander("필터", expanded=False):
            if st.button("필터 초기화", key="equipment_count_filter_reset"):
                for filter_key in equipment_filter_keys:
                    st.session_state[filter_key] = []
            equipment_filters: dict[str, list[str]] = {}
            with st.container(horizontal=True, gap="small"):
                for index, column in enumerate(equipment_dimensions):
                    options = equipment_table[column].dropna().drop_duplicates().tolist()
                    equipment_filters[column] = st.multiselect(
                        column,
                        options=options,
                        key=equipment_filter_keys[index],
                        placeholder="전체",
                        width=180,
                    )

        for column, selected_values in equipment_filters.items():
            if selected_values:
                equipment_table = equipment_table.loc[
                    equipment_table[column].isin(selected_values)
                ]
        equipment_month_columns = [
            column for column in equipment_table.columns if column not in equipment_dimensions
        ]
        displayed_equipment_table = equipment_table.copy()
        displayed_equipment_table[equipment_month_columns] = displayed_equipment_table[
            equipment_month_columns
        ].mask(displayed_equipment_table[equipment_month_columns].eq(0))
        styled_equipment_table = displayed_equipment_table.style.set_properties(
            subset=pd.Index(equipment_dimensions),
            **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
        )
        st.dataframe(
            styled_equipment_table,
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
                    for column in equipment_dimensions
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        format="%,.2f",
                        alignment="center",
                    )
                    for month in equipment_month_columns
                },
            },
        )
