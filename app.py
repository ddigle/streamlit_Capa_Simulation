from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.io.excel_reader import load_reference_tables
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    build_monthly_volume,
    plan_from_edit_table,
    plan_to_edit_table,
)
from capa_simulation.settings import APP_NAME, PROJECT_ROOT

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")
st.title(APP_NAME)


@st.cache_data(show_spinner="Excel 기준정보를 불러오는 중입니다.")
def load_data(workbook_path: str, modified_time_ns: int) -> dict[str, pd.DataFrame]:
    """Load saved Excel tables; modified time invalidates the cache after a file update."""
    del modified_time_ns
    return load_reference_tables(Path(workbook_path))


default_workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
workbook_text = st.sidebar.text_input("기준정보 파일", value=str(default_workbook))
workbook = Path(workbook_text).expanduser()

if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_tables = load_data(str(workbook.resolve()), workbook.stat().st_mtime_ns)
except Exception as exc:
    st.error(f"기준정보를 불러오지 못했습니다: {exc}")
    st.stop()

try:
    default_plan_table = plan_to_edit_table(reference_tables["RQ_PKG_PLAN"])
except ValueError as exc:
    st.error(str(exc))
    st.stop()

editor_key = "pkg_plan_editor"
source_token_key = "pkg_plan_source_token"
source_token = f"{workbook.resolve()}:{workbook.stat().st_mtime_ns}"
if st.session_state.get(source_token_key) != source_token:
    st.session_state.pop(editor_key, None)
    st.session_state[source_token_key] = source_token

pkg_plan_tab, monthly_volume_tab = st.tabs(["PKG PLAN", "월별 물량"])

with pkg_plan_tab:
    st.caption(
        "Excel 계획을 기본값으로 불러왔습니다. "
        "월별 생산수량만 수정할 수 있습니다. 단위: Kea"
    )
    plan_month_columns = [
        column for column in default_plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    edited_plan_table = st.data_editor(
        default_plan_table,
        key=editor_key,
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        disabled=PLAN_EDITOR_DIMENSIONS,
        column_config={
            month: st.column_config.NumberColumn(
                month,
                min_value=0.0,
                format="%,.2f",
            )
            for month in plan_month_columns
        },
    )

try:
    simulation_plan = plan_from_edit_table(edited_plan_table)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

with monthly_volume_tab:
    demand_basis = st.selectbox(
        "소요기준",
        options=["PKG", "Chip", "Wafer"],
        key="monthly_volume_basis",
    )
    show_detail = st.toggle("상세", key="monthly_volume_detail")

    try:
        monthly_volume = build_monthly_volume(
            plan=simulation_plan,
            yield_data=reference_tables["RQ_YLD"],
            chip_qty=reference_tables["RQ_CHIP_QTY"],
            demand_basis=demand_basis,
            detailed=show_detail,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    unit = "Kea" if demand_basis in {"PKG", "Chip"} else "매"
    st.caption(f"단위: {unit}")

    classification_columns = {"양산구분", "제품정보", "Stack"}
    if show_detail:
        classification_columns.add("WF 구분")
    month_columns = [
        column
        for column in monthly_volume.columns
        if column not in classification_columns
    ]
    st.dataframe(
        monthly_volume,
        hide_index=True,
        width="stretch",
        column_config={
            month: st.column_config.NumberColumn(month, format="%,.2f")
            for month in month_columns
        },
    )
