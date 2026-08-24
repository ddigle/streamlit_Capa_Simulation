import pandas as pd
import streamlit as st

from capa_simulation.components.grouped_monthly_table import (
    build_grouped_monthly_export,
    render_grouped_monthly_table,
)
from capa_simulation.io.reference_cache import (
    get_reference_cache_version,
    get_reference_tables,
)
from capa_simulation.scenario_state import (
    apply_month_updates,
    ensure_active_scenario,
    reset_active_scenario,
    scenario_table,
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
from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
)
from capa_simulation.services.simulation_cache import get_monthly_volume
from capa_simulation.settings import PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

CLASSIFICATION_BACKGROUND_COLOR = "#F0F2F6"
PRODUCT_COLUMN_WIDTH_PX = 100
DISPLAY_COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "Capa Code": "PKG Code",
    "Customer": "거래선",
    "수율 구분": "구분",
    "WF 구분": "속성",
}

st.title("부하량")


workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_version = get_reference_cache_version()
    reference_tables = get_reference_tables(str(workbook.resolve()))
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
except Exception as exc:
    st.error(f"기준정보를 불러오지 못했습니다: {exc}")
    st.stop()

try:
    source_start_month, source_end_month = available_month_range(
        reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN"
    )
    selected_start_label, selected_end_label = st.session_state["production_month_range_v2"]
    selected_start_month = int(selected_start_label.replace("-", ""))
    selected_end_month = int(selected_end_label.replace("-", ""))
    effective_start_month = max(selected_start_month, source_start_month)
    effective_end_month = min(selected_end_month, source_end_month)
    if effective_start_month > effective_end_month:
        with st.sidebar:
            st.warning("선택 범위에 PKG PLAN 데이터가 없습니다.")
        st.stop()

    show_applied_month_range(effective_start_month, effective_end_month)
    filtered_plan = filter_month_range(
        scenario_table(active_scenario, "RQ_PKG_PLAN"),
        effective_start_month,
        effective_end_month,
        "RQ_PKG_PLAN",
    )
    filtered_yield = filter_month_range(
        scenario_table(active_scenario, "RQ_YLD"),
        effective_start_month,
        effective_end_month,
        "RQ_YLD",
    )
    default_plan_table = plan_to_edit_table(filtered_plan, reference_tables["RQ_DISPLAY_ORDER"])
    default_yield_table = yield_to_edit_table(filtered_yield, reference_tables["RQ_DISPLAY_ORDER"])
except ValueError as exc:
    st.error(str(exc))
    st.stop()

plan_editor_key = "pkg_plan_editor"
yield_editor_key = "yield_editor"
source_token_key = "load_conversion_source_token"
source_token = (
    f"{workbook.resolve()}:{reference_version}:"
    f"{active_scenario['revision']}:"
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
        **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
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
                    DISPLAY_COLUMN_LABELS.get(column, column),
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

simulation_plan = filtered_plan
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
        **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
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
                    DISPLAY_COLUMN_LABELS.get(column, column),
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

simulation_yield = filtered_yield
if apply_yield:
    try:
        updated_yield = yield_from_edit_table(edited_yield_table)
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
            column_labels=DISPLAY_COLUMN_LABELS,
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
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=conversion_decimal_places,
            key="conversion_volume_table",
        )
