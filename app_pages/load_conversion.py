# Purpose: PKG PLAN과 수율을 편집하고 PKG·Chip·Wafer·Density 부하량 환산 결과를 제공한다.

import pandas as pd
import streamlit as st

from capa_simulation.components.grouped_monthly_table import (
    build_grouped_monthly_export,
    render_grouped_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
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
    reset_active_scenario,
    scenario_month_table,
)
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    DemandBasis,
    filter_edp_plan,
    plan_from_edit_table,
    plan_to_edit_table,
    yield_from_edit_table,
    yield_to_edit_table,
)
from capa_simulation.services.simulation_cache import get_monthly_volume

PRODUCT_COLUMN_WIDTH_PX = 100

st.title("부하량")


try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    active_scenario = context.active_scenario
    prepared_display_order = context.display_order
    selected_start_month = context.selected_start_month
    selected_end_month = context.selected_end_month
except BOOTSTRAP_ERRORS as exc:
    st.error(f"기준정보를 불러오지 못했습니다: {exc}")
    st.stop()

try:
    effective_start_month, effective_end_month = resolve_effective_months(
        context,
        reference_tables["RQ_PKG_PLAN"],
        "RQ_PKG_PLAN",
        empty_message="선택 범위에 PKG PLAN 데이터가 없습니다.",
    )
    filtered_plan = scenario_month_table(
        active_scenario,
        "RQ_PKG_PLAN",
        effective_start_month,
        effective_end_month,
    )
    filtered_yield = scenario_month_table(
        active_scenario,
        "RQ_YLD",
        effective_start_month,
        effective_end_month,
    )
    default_plan_table = plan_to_edit_table(filtered_plan, prepared_display_order)
    default_yield_table = yield_to_edit_table(filtered_yield, prepared_display_order)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

plan_editor_key = "pkg_plan_editor"
yield_editor_key = "yield_editor"
source_token_key = "load_conversion_source_token"
source_token = (
    f"duckdb:{reference_version}:{active_scenario['revision']}:"
    f"{effective_start_month}:{effective_end_month}"
)
if st.session_state.get(source_token_key) != source_token:
    st.session_state.pop(plan_editor_key, None)
    st.session_state.pop(yield_editor_key, None)
    st.session_state[source_token_key] = source_token

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"활성 시나리오 · 수정본 {active_scenario['revision']}")
    if st.button(
        ":material/restart_alt: 전체 입력 원본으로 초기화",
        key="reset_load_active_scenario",
    ):
        reset_active_scenario(reference_tables, reference_version)
        st.session_state.pop(source_token_key, None)
        st.rerun()

conversion_tab, pkg_plan_tab, yield_tab = st.tabs(["📊 환산", "PKG PLAN", "수율"])

with pkg_plan_tab:
    st.caption(
        "활성 시나리오의 월별 생산수량을 수정합니다. "
        "수정 후 적용 버튼을 눌러야 다른 페이지의 산출값에 반영됩니다. 단위: Kea"
    )
    plan_month_columns = [
        column for column in default_plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    displayed_plan_table = default_plan_table.copy()
    displayed_plan_table[plan_month_columns] = displayed_plan_table[plan_month_columns].mask(
        displayed_plan_table[plan_month_columns].eq(0)
    )
    styled_plan_table = displayed_plan_table.style.set_properties(
        subset=pd.Index(PLAN_EDITOR_DIMENSIONS),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )
    edited_plan_table = st.data_editor(
        styled_plan_table,
        key=plan_editor_key,
        hide_index=True,
        width="content",
        height=500,
        row_height=25,
        num_rows="fixed",
        disabled=PLAN_EDITOR_DIMENSIONS,
        column_config={
            **{
                column: st.column_config.TextColumn(
                    COLUMN_LABELS.get(column, column),
                    width=(PRODUCT_COLUMN_WIDTH_PX if column == "제품정보" else None),
                    alignment="center",
                    pinned=True,
                )
                for column in PLAN_EDITOR_DIMENSIONS
            },
            **{
                month: st.column_config.NumberColumn(
                    month,
                    width=80,
                    min_value=0.0,
                    step=0.01,
                    format="%,.0f",
                    alignment="center",
                )
                for month in plan_month_columns
            },
        },
    )
    apply_plan = st.button(
        ":material/check: PKG PLAN 변경사항 적용",
        key="apply_pkg_plan_changes",
        type="primary",
    )
    imported_plan_table = render_reference_clipboard_tools(
        default_plan_table,
        table_name="RQ_PKG_PLAN",
        key_columns=PLAN_EDITOR_DIMENSIONS,
        file_name=f"RQ_PKG_PLAN_{effective_start_month}_{effective_end_month}.csv",
        key="rq_pkg_plan_csv",
    )

simulation_plan = filtered_plan
if apply_plan or imported_plan_table is not None:
    try:
        plan_source = imported_plan_table if imported_plan_table is not None else edited_plan_table
        updated_plan = plan_from_edit_table(plan_source)
        apply_month_updates(
            active_scenario,
            {"RQ_PKG_PLAN": updated_plan},
            effective_start_month,
            effective_end_month,
        )
    except ValueError as exc:
        with pkg_plan_tab:
            st.error(str(exc))
    else:
        if imported_plan_table is not None:
            queue_reference_import_flash(
                "rq_pkg_plan_csv",
                "RQ_PKG_PLAN 붙여넣기 데이터를 활성 시나리오에 일괄 적용했습니다.",
            )
        st.session_state.pop(source_token_key, None)
        st.rerun()

with yield_tab:
    st.caption(
        "활성 시나리오의 EDS·BE 수율을 수정합니다. "
        "수정 후 적용 버튼을 눌러야 환산수량과 다른 페이지에 반영됩니다."
    )
    yield_month_columns = [
        column for column in default_yield_table.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    styled_yield_table = default_yield_table.style.set_properties(
        subset=pd.Index(YIELD_EDITOR_DIMENSIONS),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )
    edited_yield_table = st.data_editor(
        styled_yield_table,
        key=yield_editor_key,
        hide_index=True,
        width="content",
        height=500,
        row_height=25,
        num_rows="fixed",
        disabled=YIELD_EDITOR_DIMENSIONS,
        column_config={
            **{
                column: st.column_config.TextColumn(
                    COLUMN_LABELS.get(column, column),
                    width=(PRODUCT_COLUMN_WIDTH_PX if column == "제품정보" else None),
                    alignment="center",
                    pinned=True,
                )
                for column in YIELD_EDITOR_DIMENSIONS
            },
            **{
                month: st.column_config.NumberColumn(
                    month,
                    width=80,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="percent",
                    alignment="center",
                )
                for month in yield_month_columns
            },
        },
    )
    apply_yield = st.button(
        ":material/check: 수율 변경사항 적용",
        key="apply_yield_changes",
        type="primary",
    )
    imported_yield_table = render_reference_clipboard_tools(
        default_yield_table,
        table_name="RQ_YLD",
        key_columns=YIELD_EDITOR_DIMENSIONS,
        file_name=f"RQ_YLD_{effective_start_month}_{effective_end_month}.csv",
        key="rq_yield_csv",
    )

simulation_yield = filtered_yield
if apply_yield or imported_yield_table is not None:
    try:
        yield_source = (
            imported_yield_table if imported_yield_table is not None else edited_yield_table
        )
        updated_yield = yield_from_edit_table(yield_source)
        apply_month_updates(
            active_scenario,
            {"RQ_YLD": updated_yield},
            effective_start_month,
            effective_end_month,
        )
    except ValueError as exc:
        with yield_tab:
            st.error(str(exc))
    else:
        if imported_yield_table is not None:
            queue_reference_import_flash(
                "rq_yield_csv",
                "RQ_YLD 붙여넣기 데이터를 활성 시나리오에 일괄 적용했습니다.",
            )
        st.session_state.pop(source_token_key, None)
        st.rerun()

with conversion_tab:
    demand_basis_options: tuple[DemandBasis, ...] = ("PKG", "Chip", "Wafer", "Density")
    with st.container(border=True):
        st.subheader("설정")
        with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
            demand_basis = st.selectbox(
                "소요기준",
                options=demand_basis_options,
                key="monthly_volume_basis",
                width=180,
            )
            show_detail = st.toggle("상세", key="monthly_volume_detail", width=90)
            include_edp = st.toggle("EDP", key="monthly_volume_edp", width=90)

    try:
        conversion_plan = filter_edp_plan(simulation_plan, include_edp)
        monthly_volume = get_monthly_volume(
            plan=conversion_plan,
            yield_data=simulation_yield,
            chip_qty=reference_tables["RQ_CHIP_QTY"],
            demand_basis=demand_basis,
            detailed=show_detail,
            density_data=reference_tables["RQ_CHIP_EQ"],
            display_order=reference_tables["RQ_DISPLAY_ORDER"],
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    unit = {
        "PKG": "Kea",
        "Chip": "Kea",
        "Wafer": "매",
        "Density": "억Gb",
    }[demand_basis]
    conversion_decimal_places = 2 if demand_basis == "Density" else 0

    with st.container(border=True):
        classification_columns = {"양산구분", "제품정보", "Stack"}
        if show_detail:
            classification_columns.add("WF 구분")
        displayed_classification_columns = [
            column for column in monthly_volume.columns if column in classification_columns
        ]
        conversion_export = build_grouped_monthly_export(
            monthly_volume,
            classification_columns=displayed_classification_columns,
            column_labels=COLUMN_LABELS,
        )
        conversion_csv = conversion_export.to_csv(
            index=False,
            float_format=f"%.{conversion_decimal_places}f",
        ).encode("utf-8-sig")
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader("환산", width="content")
            st.caption(f"단위: {unit}", width="content")
            st.download_button(
                ":material/download: CSV 다운로드",
                data=conversion_csv,
                file_name=(
                    "Capa_Conversion_"
                    f"{demand_basis}_{effective_start_month}_{effective_end_month}.csv"
                ),
                mime="text/csv;charset=utf-8",
                key="download_conversion_csv",
                on_click="ignore",
                width="content",
            )
        render_grouped_monthly_table(
            monthly_volume,
            classification_columns=displayed_classification_columns,
            column_labels=COLUMN_LABELS,
            decimal_places=conversion_decimal_places,
            key="conversion_volume_table",
        )
