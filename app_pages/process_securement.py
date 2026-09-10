# Purpose: 공정별 확보율·소요대수 결과와 보유·대여·가용 설비대수 입력을 제공한다.

import pandas as pd
import streamlit as st

from capa_simulation.components.column_filter import render_column_filters
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.reference_csv_tools import (
    queue_reference_import_flash,
    render_reference_clipboard_tools,
)
from capa_simulation.components.tab_state import stateful_tabs
from capa_simulation.components.table_toolbar import render_csv_download, render_table_heading
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
    get_scenario_capacity_and_demand,
    get_securement_rate,
    scenario_cache_key,
)
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
)

TAB_NAMES = (
    ":material/insights: 확보율",
    ":material/precision_manufacturing: 소요대수",
    "설비대수",
)


render_page_header(
    "공정별 확보율",
    description=("월·공정별 가용대수를 소요대수로 나눠 확보율과 B/N 공정을 판정합니다."),
)
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()
availability_tab, required_tab, equipment_tab = stateful_tabs(
    TAB_NAMES,
    key="process_securement_active_tab",
)

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

    # 계산 입력의 월 슬라이스는 캐시 래퍼 안에서 한다. 여기서는 설비대수 표 세 개만 자른다.
    monthly_table_names = ("RQ_EQP_OWN", "RQ_EQP_LENT", "RQ_EQP_AVBL")
    filtered = {
        table_name: scenario_month_table(
            active_scenario,
            table_name,
            effective_start,
            effective_end,
        )
        for table_name in monthly_table_names
    }

    capacity_cache_key = scenario_cache_key(
        reference_version, active_scenario, effective_start, effective_end
    )
    unit_capacity, required_equipment = get_scenario_capacity_and_demand(
        capacity_cache_key,
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
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
        capacity_cache_key,
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
        displayed_securement_table = render_column_filters(
            securement_table,
            SECUREMENT_DIMENSIONS,
            key_prefix="securement_filter",
            value_labels=process_labels.value_labels(),
        )
        securement_export = build_hierarchical_monthly_export(
            displayed_securement_table,
            classification_columns=SECUREMENT_DIMENSIONS,
            column_labels=COLUMN_LABELS,
            decimal_places=2,
            value_format="percent",
        )
        securement_csv = securement_export.to_csv(index=False).encode("utf-8-sig")
        render_table_heading(
            "확보율",
            csv=securement_csv,
            file_name=f"Capa_Securement_Rate_{effective_start}_{effective_end}.csv",
            key="download_securement_rate_csv",
        )
        render_hierarchical_monthly_table(
            displayed_securement_table,
            classification_columns=SECUREMENT_DIMENSIONS,
            column_labels=COLUMN_LABELS,
            decimal_places=2,
            value_format="percent",
            key="securement_rate_monthly_table",
            value_labels=process_labels.value_labels(),
            owner_tab=availability_tab,
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
                render_csv_download(
                    data=displayed_capacity_exclusions.to_csv(index=False).encode("utf-8-sig"),
                    file_name=(
                        f"Capa_Unit_Capacity_Exclusions_{effective_start}_{effective_end}.csv"
                    ),
                    key="download_capacity_exclusions_csv",
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
                render_csv_download(
                    data=displayed_required_exclusions.to_csv(index=False).encode("utf-8-sig"),
                    file_name=(
                        f"Capa_Required_Equipment_Exclusions_{effective_start}_{effective_end}.csv"
                    ),
                    key="download_required_exclusions_csv",
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

        filtered_required_table = render_column_filters(
            view_table,
            table_dimensions,
            key_prefix="required_equipment_filter",
            column_labels=COLUMN_LABELS,
            value_labels=process_labels.value_labels(),
        )
        required_export = build_hierarchical_monthly_export(
            filtered_required_table,
            classification_columns=table_dimensions,
            column_labels=COLUMN_LABELS,
            decimal_places=2,
        )
        required_csv = required_export.to_csv(index=False, float_format="%.2f").encode("utf-8-sig")
        required_view_name = "Detail" if show_detail else "Summary"
        render_table_heading(
            "소요대수",
            csv=required_csv,
            file_name=(
                "Capa_Required_Equipment_"
                f"{required_view_name}_{effective_start}_{effective_end}.csv"
            ),
            key=(
                "download_required_equipment_detail_csv"
                if show_detail
                else "download_required_equipment_summary_csv"
            ),
        )
        render_hierarchical_monthly_table(
            filtered_required_table,
            classification_columns=table_dimensions,
            column_labels=COLUMN_LABELS,
            decimal_places=2,
            key=(
                "required_equipment_detail_table"
                if show_detail
                else "required_equipment_summary_table"
            ),
            value_labels=process_labels.value_labels(),
            page_size=60 if show_detail else None,
            owner_tab=required_tab,
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

        equipment_table = render_column_filters(
            equipment_table,
            equipment_dimensions,
            key_prefix="equipment_count_filter",
        )
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
