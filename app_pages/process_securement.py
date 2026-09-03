# Purpose: 공정별 확보율·소요대수 결과와 보유·대여·가용 설비대수 입력을 제공한다.

import pandas as pd
import streamlit as st

from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.reference_csv_tools import (
    queue_reference_import_flash,
    render_reference_clipboard_tools,
)
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.scenario_state import (
    apply_month_updates,
    scenario_month_table,
)
from capa_simulation.services.display_order import (
    apply_display_order,
    reorder_display_columns,
)
from capa_simulation.services.equipment_count import (
    DETAILED_EQUIPMENT_DIMENSIONS,
    EQUIPMENT_DIMENSIONS,
    build_equipment_count_table,
    equipment_count_from_edit_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import (
    SECUREMENT_DIMENSIONS,
    securement_rate_to_month_table,
)
from capa_simulation.services.simulation_cache import (
    get_required_equipment,
    get_securement_rate,
    get_unit_capacity,
)
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
)

TAB_NAMES = ("📊 확보율", "📊 소요대수", "설비대수")
DISPLAY_COLUMN_LABELS = {
    "Area_Name": "Area",
    "양산구분": "양산",
    "제품정보": "제품",
    "Capa Code": "PKG Code",
    "WF 구분": "속성",
    "STEP_SEQ": "Step",
    "MCP_SEQ": "MCP",
}


st.title("공정별 확보율")
availability_tab, required_tab, equipment_tab = st.tabs(TAB_NAMES)

try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    display_order = context.display_order
    active_scenario = context.active_scenario
    effective_start, effective_end = resolve_effective_months(
        context,
        active_scenario["tables"]["RQ_REQB"],
        "RQ_REQB",
        empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
    )

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
        table_name: scenario_month_table(
            active_scenario,
            table_name,
            effective_start,
            effective_end,
        )
        for table_name in monthly_table_names
    }
    simulation_plan = filtered["RQ_PKG_PLAN"]
    simulation_yield = filtered["RQ_YLD"]

    unit_capacity = get_unit_capacity(
        upeh=filtered["RQ_UPEH"],
        run_rate=filtered["RQ_RUN_RATE"],
        vital=filtered["RQ_VITAL"],
        module=reference_tables["RQ_MODULE"],
        run_day=filtered["RQ_RUN_DAY"],
        lot_ratio=filtered["RQ_LOT_RATIO"],
        wf_ratio=filtered["RQ_WF_RATIO"],
    )
    required_equipment = get_required_equipment(
        reqb=filtered["RQ_REQB"],
        plan=simulation_plan,
        yield_data=simulation_yield,
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    capacity_exclusions = unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
    required_exclusions = required_equipment.attrs.get(
        REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR, pd.DataFrame()
    )
    required_table = required_equipment_to_month_table(required_equipment)
    required_table = apply_display_order(
        required_table,
        display_order,
        "공정별 확보율",
        "소요대수",
    )
    required_table, required_detail_dimensions = reorder_display_columns(
        required_table,
        RESULT_DIMENSIONS,
        display_order,
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
        display_order,
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
        display_order,
        "공정별 확보율",
        "설비대수",
    )
    equipment_edit_tables = {
        table_name: equipment_count_to_edit_table(filtered[table_name], category, value_column)
        for table_name, category, value_column in (
            ("RQ_EQP_OWN", "보유", "설비보유"),
            ("RQ_EQP_LENT", "대여", "설비대여평가"),
            ("RQ_EQP_AVBL", "가용", "가용대수"),
        )
    }
    securement_rate = get_securement_rate(
        filtered["RQ_EQP_AVBL"],
        required_equipment,
    )
    securement_table = securement_rate_to_month_table(securement_rate)
    securement_table = apply_display_order(
        securement_table,
        display_order,
        "공정별 확보율",
        "확보율",
    )
except BOOTSTRAP_ERRORS as exc:
    with availability_tab:
        st.error(str(exc))
    with required_tab:
        st.error(str(exc))
    with equipment_tab:
        st.error(str(exc))
else:
    with availability_tab:
        st.caption("월간 공정별 확보율 (가용대수 ÷ 소요대수)")
        securement_filter_keys = [f"securement_filter_{column}" for column in SECUREMENT_DIMENSIONS]
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
        securement_export = build_hierarchical_monthly_export(
            displayed_securement_table,
            classification_columns=SECUREMENT_DIMENSIONS,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=2,
            value_format="percent",
        )
        securement_csv = securement_export.to_csv(index=False).encode("utf-8-sig")
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader("확보율", width="content")
            st.download_button(
                ":material/download: CSV 다운로드",
                data=securement_csv,
                file_name=f"Capa_Securement_Rate_{effective_start}_{effective_end}.csv",
                mime="text/csv;charset=utf-8",
                key="download_securement_rate_csv",
                on_click="ignore",
                width="content",
            )
        render_hierarchical_monthly_table(
            displayed_securement_table,
            classification_columns=SECUREMENT_DIMENSIONS,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=2,
            value_format="percent",
            key="securement_rate_monthly_table",
        )

    with required_tab:
        if not capacity_exclusions.empty:
            st.warning(
                f"0 이하 기준값으로 대당 Capa {len(capacity_exclusions):,}건을 제외했습니다."
            )
            with st.expander("제외된 대당 Capa 기준정보", expanded=False):
                displayed_capacity_exclusions, _ = reorder_display_columns(
                    capacity_exclusions,
                    [
                        column
                        for column in RESULT_DIMENSIONS
                        if column in capacity_exclusions.columns
                    ],
                    display_order,
                    "공정별 확보율",
                    "소요대수",
                )
                st.dataframe(
                    displayed_capacity_exclusions,
                    hide_index=True,
                    width="stretch",
                )
        if not required_exclusions.empty:
            positive_load_exclusions = required_exclusions.loc[required_exclusions["부하량"].gt(0)]
            st.warning(
                "대당 Capa가 없어 소요대수 산출에서 "
                f"{len(required_exclusions):,}건을 제외했습니다"
                f" (부하량 발생 {len(positive_load_exclusions):,}건)."
            )
            with st.expander("소요대수 제외 기준정보", expanded=False):
                displayed_required_exclusions, _ = reorder_display_columns(
                    required_exclusions,
                    [
                        column
                        for column in RESULT_DIMENSIONS
                        if column in required_exclusions.columns
                    ],
                    display_order,
                    "공정별 확보율",
                    "소요대수",
                )
                st.dataframe(
                    displayed_required_exclusions,
                    hide_index=True,
                    width="stretch",
                )
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
            table_dimensions = required_detail_dimensions
            view_table = required_table.copy()
        else:
            table_dimensions = ["Area_Name", "공정"]
            view_table = required_table.groupby(table_dimensions, as_index=False, sort=False)[
                all_month_columns
            ].sum(min_count=1)

        filter_keys = [f"required_equipment_filter_{column}" for column in table_dimensions]
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
        required_export = build_hierarchical_monthly_export(
            filtered_required_table,
            classification_columns=table_dimensions,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=2,
        )
        required_csv = required_export.to_csv(index=False, float_format="%.2f").encode("utf-8-sig")
        required_view_name = "Detail" if show_detail else "Summary"
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader("소요대수", width="content")
            st.download_button(
                ":material/download: CSV 다운로드",
                data=required_csv,
                file_name=(
                    "Capa_Required_Equipment_"
                    f"{required_view_name}_{effective_start}_{effective_end}.csv"
                ),
                mime="text/csv;charset=utf-8",
                key=(
                    "download_required_equipment_detail_csv"
                    if show_detail
                    else "download_required_equipment_summary_csv"
                ),
                on_click="ignore",
                width="content",
            )
        render_hierarchical_monthly_table(
            filtered_required_table,
            classification_columns=table_dimensions,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=2,
            key=(
                "required_equipment_detail_table"
                if show_detail
                else "required_equipment_summary_table"
            ),
            page_size=60 if show_detail else None,
        )

    with equipment_tab:
        st.caption("월간 설비대수")
        with st.container(border=True):
            st.markdown("#### 설비대수 RQ Excel 붙여넣기")
            st.caption(
                "보유·대여·가용 RQ는 각각 내려받아 값을 수정한 뒤 적용합니다. "
                "적용값은 활성 시나리오의 다른 계산 페이지에 즉시 반영됩니다."
            )
            imported_equipment: dict[str, pd.DataFrame] = {}
            for table_name, category, value_column in (
                ("RQ_EQP_OWN", "보유", "설비보유"),
                ("RQ_EQP_LENT", "대여", "설비대여평가"),
                ("RQ_EQP_AVBL", "가용", "가용대수"),
            ):
                imported = render_reference_clipboard_tools(
                    equipment_edit_tables[table_name],
                    table_name=table_name,
                    key_columns=EQUIPMENT_DIMENSIONS,
                    file_name=f"{table_name}_{effective_start}_{effective_end}.csv",
                    key=f"{table_name.lower()}_csv",
                    expander_label=f"{category}설비 - Excel 붙여넣기",
                )
                if imported is not None:
                    try:
                        imported_equipment[table_name] = equipment_count_from_edit_table(
                            imported,
                            category,
                            value_column,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
            if imported_equipment:
                try:
                    apply_month_updates(
                        active_scenario,
                        imported_equipment,
                        effective_start,
                        effective_end,
                    )
                except (KeyError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    applied_table = next(iter(imported_equipment))
                    queue_reference_import_flash(
                        f"{applied_table.lower()}_csv",
                        f"{applied_table} 붙여넣기 데이터를 활성 시나리오에 일괄 적용했습니다.",
                    )
                    st.rerun()
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
                equipment_table = equipment_table.loc[equipment_table[column].isin(selected_values)]
        equipment_month_columns = [
            column for column in equipment_table.columns if column not in equipment_dimensions
        ]
        displayed_equipment_table = equipment_table.copy()
        displayed_equipment_table[equipment_month_columns] = displayed_equipment_table[
            equipment_month_columns
        ].mask(displayed_equipment_table[equipment_month_columns].eq(0))
        styled_equipment_table = displayed_equipment_table.style.set_properties(
            subset=pd.Index(equipment_dimensions),
            **{"background-color": tokens.SURFACE_CLASSIFICATION},
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
