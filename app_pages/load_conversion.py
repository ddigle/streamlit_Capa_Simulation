from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    DemandBasis,
    build_monthly_volume,
    plan_from_edit_table,
    plan_to_edit_table,
    yield_from_edit_table,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
)
from capa_simulation.settings import PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

CLASSIFICATION_BACKGROUND_COLOR = "#F0F2F6"
DISPLAY_COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "Capa Code": "PKG Code",
    "Customer": "거래선",
    "수율 구분": "구분",
    "WF 구분": "속성",
}

st.title("부하량")


@st.cache_data(show_spinner="Excel 기준정보를 불러오는 중입니다.")
def load_data(workbook_path: str, modified_time_ns: int) -> dict[str, pd.DataFrame]:
    """Load saved Excel tables; modified time invalidates the cache after an update."""
    del modified_time_ns
    return load_reference_tables(Path(workbook_path))


workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_tables = load_data(str(workbook.resolve()), workbook.stat().st_mtime_ns)
except Exception as exc:
    st.error(f"기준정보를 불러오지 못했습니다: {exc}")
    st.stop()

try:
    source_start_month, source_end_month = available_month_range(
        reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN"
    )
    selected_start_label, selected_end_label = st.session_state[
        "production_month_range_v2"
    ]
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
        reference_tables["RQ_PKG_PLAN"],
        effective_start_month,
        effective_end_month,
        "RQ_PKG_PLAN",
    )
    filtered_yield = filter_month_range(
        reference_tables["RQ_YLD"],
        effective_start_month,
        effective_end_month,
        "RQ_YLD",
    )
    default_plan_table = plan_to_edit_table(
        filtered_plan, reference_tables["RQ_DISPLAY_ORDER"]
    )
    default_yield_table = yield_to_edit_table(
        filtered_yield, reference_tables["RQ_DISPLAY_ORDER"]
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

plan_editor_key = "pkg_plan_editor"
yield_editor_key = "yield_editor"
source_token_key = "load_conversion_source_token"
source_token = (
    f"{workbook.resolve()}:{workbook.stat().st_mtime_ns}:"
    f"{effective_start_month}:{effective_end_month}"
)
if st.session_state.get(source_token_key) != source_token:
    st.session_state.pop(plan_editor_key, None)
    st.session_state.pop(yield_editor_key, None)
    st.session_state[source_token_key] = source_token

conversion_tab, pkg_plan_tab, yield_tab = st.tabs(["📊 환산", "PKG PLAN", "수율"])

with pkg_plan_tab:
    st.caption(
        "Excel 계획을 기본값으로 불러왔습니다. "
        "월별 생산수량만 수정할 수 있습니다. 단위: Kea"
    )
    plan_month_columns = [
        column for column in default_plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    displayed_plan_table = default_plan_table.copy()
    displayed_plan_table[plan_month_columns] = displayed_plan_table[
        plan_month_columns
    ].mask(displayed_plan_table[plan_month_columns].eq(0))
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
                    width=None,
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

try:
    simulation_plan = plan_from_edit_table(edited_plan_table)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

with yield_tab:
    st.caption(
        "Excel 수율을 기본값으로 불러왔습니다. "
        "EDS·BE 수율의 월별 값만 수정할 수 있으며 환산수량에 즉시 반영됩니다."
    )
    yield_month_columns = [
        column
        for column in default_yield_table.columns
        if column not in YIELD_EDITOR_DIMENSIONS
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
                    width=None,
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

try:
    simulation_yield = yield_from_edit_table(edited_yield_table)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

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

    try:
        monthly_volume = build_monthly_volume(
            plan=simulation_plan,
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
    conversion_number_format = "%,.2f" if demand_basis == "Density" else "%,.0f"

    with st.container(border=True):
        st.subheader("환산")
        st.caption(f"단위: {unit}")

        classification_columns = {"양산구분", "제품정보", "Stack"}
        if show_detail:
            classification_columns.add("WF 구분")
        month_columns = [
            column for column in monthly_volume.columns if column not in classification_columns
        ]
        displayed_classification_columns = [
            column for column in monthly_volume.columns if column in classification_columns
        ]
        displayed_monthly_volume = monthly_volume.copy()
        displayed_monthly_volume[month_columns] = displayed_monthly_volume[
            month_columns
        ].mask(displayed_monthly_volume[month_columns].eq(0))
        styled_monthly_volume = displayed_monthly_volume.style.set_properties(
            subset=pd.Index(displayed_classification_columns),
            **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
        )
        st.dataframe(
            styled_monthly_volume,
            hide_index=True,
            width="content",
            height=500,
            row_height=25,
            column_config={
                **{
                    column: st.column_config.TextColumn(
                        DISPLAY_COLUMN_LABELS.get(column, column),
                        width=None,
                        alignment="center",
                        pinned=True,
                    )
                    for column in classification_columns
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        format=conversion_number_format,
                        alignment="center",
                    )
                    for month in month_columns
                },
            },
        )
