# Purpose: PKG PLAN과 수율을 편집하고 PKG·Chip·Wafer·Density 부하량 환산 결과를 제공한다.

from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.grouped_monthly_table import (
    build_grouped_monthly_export,
    render_grouped_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.reference_csv_tools import (
    queue_reference_import_flash,
    render_reference_clipboard_tools,
)
from capa_simulation.components.scenario_edit_bar import render_scenario_edit_bar
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.scenario_state import (
    apply_month_updates,
    apply_table_updates,
    remember_virtual_product,
    scenario_month_table,
    scenario_table,
    session_virtual_products,
)
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    DemandBasis,
    filter_edp_plan,
    load_exclusions,
    plan_from_edit_table,
    plan_to_edit_table,
    yield_from_edit_table,
    yield_to_edit_table,
)
from capa_simulation.services.simulation_cache import get_monthly_volume
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    available_source_products,
    clone_product,
    records_to_frame,
)

PRODUCT_COLUMN_WIDTH_PX = 100

render_page_header(
    "부하량",
    description=(
        "월별 PKG 생산계획을 Chip·Wafer·Density 부하량으로 환산합니다. "
        "계획과 수율을 편집하면 다른 페이지의 산출값이 함께 바뀝니다."
    ),
)


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
# 붙여넣기 결과는 곧바로 전역에 반영하지 않고 이 키에 담아 PKG PLAN 탭에만 보여준다.
# 사용자가 "변경사항 적용" 을 눌러야 활성 시나리오로 넘어간다.
plan_staged_key = "pkg_plan_staged_paste"
plan_applied_flash_key = "pkg_plan_applied_flash"
product_registered_flash_key = "virtual_product_registered_flash"
source_token = (
    f"duckdb:{reference_version}:{active_scenario['revision']}:"
    f"{effective_start_month}:{effective_end_month}"
)
if st.session_state.get(source_token_key) != source_token:
    st.session_state.pop(plan_editor_key, None)
    st.session_state.pop(yield_editor_key, None)
    # 원본이 바뀌면 아직 적용하지 않은 붙여넣기는 행·월 구성이 맞지 않으므로 버린다.
    st.session_state.pop(plan_staged_key, None)
    st.session_state[source_token_key] = source_token

render_scenario_edit_bar(
    active_scenario,
    reference_tables,
    reference_version,
    reset_key="reset_load_active_scenario",
    clear_session_keys=(source_token_key, plan_staged_key),
)

conversion_tab, pkg_plan_tab, yield_tab, product_tab = st.tabs(
    [":material/insights: 환산", "PKG PLAN", "수율", "제품 등록"]
)

with pkg_plan_tab:
    applied_flash = st.session_state.pop(plan_applied_flash_key, None)
    if isinstance(applied_flash, str):
        st.success(applied_flash, icon=":material/published_with_changes:")
    st.caption(
        "활성 시나리오의 월별 생산수량을 수정합니다. "
        "수정 후 적용 버튼을 눌러야 다른 페이지의 산출값에 반영됩니다. 단위: Kea"
    )
    # 붙여넣기한 표가 있으면 그것을 편집 대상으로 보여준다. 아직 전역에는 반영되지 않았다.
    staged_plan_table = st.session_state.get(plan_staged_key)
    plan_editor_source = (
        staged_plan_table if isinstance(staged_plan_table, pd.DataFrame) else default_plan_table
    )
    plan_month_columns = [
        column for column in plan_editor_source.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    displayed_plan_table = plan_editor_source.copy()
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
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        apply_plan = st.button(
            ":material/check: PKG PLAN 변경사항 적용",
            key="apply_pkg_plan_changes",
            type="primary",
        )
        st.caption("적용을 누르면 환산·홈 대시보드 등 전역 계획값에 반영됩니다.")
    imported_plan_table = render_reference_clipboard_tools(
        plan_editor_source,
        table_name="RQ_PKG_PLAN",
        key_columns=PLAN_EDITOR_DIMENSIONS,
        file_name=f"RQ_PKG_PLAN_{effective_start_month}_{effective_end_month}.csv",
        key="rq_pkg_plan_csv",
    )

simulation_plan = filtered_plan

# 붙여넣기는 PKG PLAN 탭에만 반영한다. 전역 계획값은 아래 "변경사항 적용" 에서만 바꾼다.
if imported_plan_table is not None:
    try:
        plan_from_edit_table(imported_plan_table)
    except ValueError as exc:
        with pkg_plan_tab:
            st.error(str(exc))
    else:
        st.session_state[plan_staged_key] = imported_plan_table
        # 편집기 위젯이 이전 표의 편집 상태를 덮어쓰지 않도록 초기화한다.
        st.session_state.pop(plan_editor_key, None)
        queue_reference_import_flash(
            "rq_pkg_plan_csv",
            "붙여넣기 표를 PKG PLAN 탭에 반영했습니다. "
            "확인 후 'PKG PLAN 변경사항 적용'을 눌러야 전역 계획값에 반영됩니다.",
        )
        st.rerun()

if apply_plan:
    try:
        updated_plan = plan_from_edit_table(edited_plan_table)
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
        st.session_state.pop(plan_staged_key, None)
        st.session_state[plan_applied_flash_key] = (
            f"PKG PLAN을 전역 계획값에 반영했습니다. "
            f"{effective_start_month}~{effective_end_month} 구간의 환산·소요대수·확보율과 "
            f"홈 대시보드가 이 계획으로 다시 계산됩니다."
        )
        st.session_state.pop(source_token_key, None)
        st.rerun()

with product_tab:
    registered_flash = st.session_state.pop(product_registered_flash_key, None)
    if isinstance(registered_flash, str):
        st.success(registered_flash, icon=":material/library_add:")
    st.caption(
        "기존 제품의 기준정보를 새 제품 키로 복제해 가상 제품을 만듭니다. "
        "환산·소요대수가 참조할 수율·Chip·경로 기준이 함께 복제되므로 계산에서 빠지지 "
        "않습니다. 계획 수량은 0으로 시작하니 PKG PLAN 탭에서 입력하세요."
    )
    source_candidates = available_source_products(active_scenario["tables"])
    if source_candidates.empty:
        st.info("복제할 수 있는 제품이 없습니다. 기준정보가 완결된 제품이 하나는 있어야 합니다.")
    else:
        source_labels = [
            f"{row['제품정보']} · {row['Stack']}" for _, row in source_candidates.iterrows()
        ]
        with st.form("virtual_product_form", border=True):
            st.markdown("**복제 원본**")
            selected_source = st.selectbox(
                "기준이 될 제품",
                options=range(len(source_labels)),
                format_func=lambda index: source_labels[index],
                key="virtual_product_source",
            )
            st.markdown("**새 제품 키**")
            with st.container(horizontal=True, gap="small"):
                new_product = st.text_input("제품정보", key="virtual_product_name")
                new_stack = st.text_input(
                    "Stack",
                    value=str(source_candidates.iloc[selected_source]["Stack"]),
                    key="virtual_product_stack",
                )
            registered = st.form_submit_button(
                ":material/library_add: 가상 제품 등록", type="primary"
            )
        if registered:
            source_row = source_candidates.iloc[selected_source]
            try:
                request = VirtualProductRequest(
                    source_product=str(source_row["제품정보"]),
                    source_stack=str(source_row["Stack"]),
                    product=new_product,
                    stack=new_stack,
                )
                updates = clone_product(active_scenario["tables"], request)
            except ValueError as exc:
                st.error(str(exc))
            else:
                apply_table_updates(active_scenario, updates)
                remember_virtual_product(VirtualProductRecord.from_request(request))
                st.session_state.pop(plan_staged_key, None)
                st.session_state.pop(source_token_key, None)
                st.session_state[product_registered_flash_key] = (
                    f"가상 제품 {request.normalized().product} · "
                    f"{request.normalized().stack} 을 등록했습니다. "
                    f"기준정보 {len(updates)}종을 복제했습니다. "
                    "PKG PLAN 탭에서 계획 수량을 입력하세요."
                )
                st.rerun()
        st.caption(
            "가상 제품은 실적과 대조할 수 없습니다. 리비전을 저장해 공식버전으로 발행할 "
            "때 포함 여부를 확인하세요."
        )

    registered_records = session_virtual_products()
    if registered_records:
        st.markdown("#### 이 세션에서 등록한 가상 제품")
        st.dataframe(
            records_to_frame(cast(tuple[VirtualProductRecord, ...], registered_records)),
            hide_index=True,
            width="content",
        )
        st.caption("리비전을 저장하면 이 목록이 함께 기록되어 공식버전 발행 시 확인할 수 있습니다.")

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
            chip_qty=scenario_table(active_scenario, "RQ_CHIP_QTY"),
            demand_basis=demand_basis,
            detailed=show_detail,
            density_data=scenario_table(active_scenario, "RQ_CHIP_EQ"),
            display_order=reference_tables["RQ_DISPLAY_ORDER"],
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    # 기준정보가 없어 계산에서 빠진 계획 행은 조용히 사라지면 안 된다. 예전에는 여기서
    # 예외를 던져 페이지 전체가 멈췄고, 지금은 해당 제품만 빼고 목록으로 알린다.
    excluded_load_rows = load_exclusions(monthly_volume)
    if not excluded_load_rows.empty:
        st.warning(
            f"기준정보가 없어 계산에서 제외한 계획이 {len(excluded_load_rows):,}건 있습니다. "
            "아래 목록의 기준정보를 채우면 환산과 소요대수에 반영됩니다.",
            icon=":material/link_off:",
        )
        with st.expander("제외한 계획 확인", icon=":material/rule:"):
            st.dataframe(excluded_load_rows, hide_index=True, width="stretch")

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
