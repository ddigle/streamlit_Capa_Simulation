import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

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
from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    performance_from_edit_table,
    performance_to_edit_table,
    reference_from_edit_table,
    reference_to_edit_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.month_filter import available_month_range, filter_month_range
from capa_simulation.services.simulation_cache import get_unit_capacity
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    unit_capacity_to_month_table,
)
from capa_simulation.settings import PROJECT_ROOT
from capa_simulation.sidebar_status import show_applied_month_range

TAB_NAMES = (
    "📊 대당 Capa",
    "UPEH",
    "효율",
    "여유율",
    "Lot측정률",
    "WF측정률",
    "일수",
)

DISPLAY_COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
    "Area_Name": "Area",
}
CLASSIFICATION_BACKGROUND_COLOR = "#F0F2F6"
RUN_RATE_DIMENSIONS = ["공정", "양산구분"]
VITAL_DIMENSIONS = ["공정", "양산구분"]
RUN_DAY_DIMENSIONS = ["공정"]
RATIO_DIMENSIONS = ["공정", "양산구분", "제품정보", "Stack", "WF 구분"]


def selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


def filter_monthly_table(
    data: pd.DataFrame, start_month: int, end_month: int, table_name: str
) -> pd.DataFrame:
    if data.empty:
        return data.copy()
    return filter_month_range(data, start_month, end_month, table_name)


def render_month_editor(
    tab: DeltaGenerator,
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    caption: str,
    number_format: str,
    step: float,
    min_value: float = 0.0,
    max_value: float | None = None,
) -> tuple[pd.DataFrame, bool]:
    month_columns = [column for column in default_table.columns if column not in dimensions]
    styled_table = default_table.style.set_properties(
        subset=pd.Index(dimensions),
        **{"background-color": CLASSIFICATION_BACKGROUND_COLOR},
    )
    with tab:
        st.caption(caption)
        edited = st.data_editor(
            styled_table,
            key=editor_key,
            hide_index=True,
            width="content",
            height=500,
            row_height=25,
            num_rows="fixed",
            disabled=dimensions,
            column_config={
                **{
                    column: st.column_config.TextColumn(
                        DISPLAY_COLUMN_LABELS.get(column, column),
                        alignment="center",
                        pinned=True,
                    )
                    for column in dimensions
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        min_value=min_value,
                        max_value=max_value,
                        step=step,
                        format=number_format,
                        alignment="center",
                    )
                    for month in month_columns
                },
            },
        )
        submitted = st.button(
            ":material/check: 변경사항 적용",
            key=f"{editor_key}_apply",
            type="primary",
        )
    return edited, submitted


st.title("공정별 Capa")

tabs = st.tabs(TAB_NAMES)
unit_capacity_tab = tabs[0]

workbook = PROJECT_ROOT / "templates" / "structure_template.xlsb"
if not workbook.is_file():
    st.error(f"기준정보 파일을 찾을 수 없습니다: {workbook}")
    st.stop()

try:
    reference_version = get_reference_cache_version()
    reference_tables = get_reference_tables(str(workbook.resolve()))
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    start_month, end_month = selected_month_range()
    source_start_month, source_end_month = available_month_range(
        reference_tables["RQ_UPEH"], "RQ_UPEH"
    )
    effective_start_month = max(start_month, source_start_month)
    effective_end_month = min(end_month, source_end_month)
    if effective_start_month > effective_end_month:
        raise ValueError("선택 범위에 공정별 Capa 기준정보가 없습니다.")
    show_applied_month_range(effective_start_month, effective_end_month)
    filtered_upeh = filter_monthly_table(
        scenario_table(active_scenario, "RQ_UPEH"), start_month, end_month, "RQ_UPEH"
    )
    filtered_run_rate = filter_monthly_table(
        scenario_table(active_scenario, "RQ_RUN_RATE"),
        start_month,
        end_month,
        "RQ_RUN_RATE",
    )
    filtered_vital = filter_monthly_table(
        scenario_table(active_scenario, "RQ_VITAL"), start_month, end_month, "RQ_VITAL"
    )
    filtered_run_day = filter_monthly_table(
        scenario_table(active_scenario, "RQ_RUN_DAY"),
        start_month,
        end_month,
        "RQ_RUN_DAY",
    )
    filtered_lot_ratio = filter_monthly_table(
        scenario_table(active_scenario, "RQ_LOT_RATIO"),
        start_month,
        end_month,
        "RQ_LOT_RATIO",
    )
    filtered_wf_ratio = filter_monthly_table(
        scenario_table(active_scenario, "RQ_WF_RATIO"),
        start_month,
        end_month,
        "RQ_WF_RATIO",
    )

    default_upeh_table = performance_to_edit_table(filtered_upeh)
    default_upeh_table = apply_display_order(
        default_upeh_table, reference_tables["RQ_DISPLAY_ORDER"], "공정별 Capa", "UPEH"
    )
    default_run_rate_table = reference_to_edit_table(
        filtered_run_rate, RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", "RQ_RUN_RATE"
    )
    default_run_rate_table = apply_display_order(
        default_run_rate_table, reference_tables["RQ_DISPLAY_ORDER"], "공정별 Capa", "효율"
    )
    default_vital_table = reference_to_edit_table(
        filtered_vital, VITAL_DIMENSIONS, "편중률", "RQ_VITAL"
    )
    default_vital_table = apply_display_order(
        default_vital_table, reference_tables["RQ_DISPLAY_ORDER"], "공정별 Capa", "여유율"
    )
    default_run_day_table = reference_to_edit_table(
        filtered_run_day, RUN_DAY_DIMENSIONS, "RUN_DAY", "RQ_RUN_DAY"
    )
    default_run_day_table = apply_display_order(
        default_run_day_table, reference_tables["RQ_DISPLAY_ORDER"], "공정별 Capa", "일수"
    )
    default_lot_ratio_table = reference_to_edit_table(
        filtered_lot_ratio, RATIO_DIMENSIONS, "Lot 측정률", "RQ_LOT_RATIO"
    )
    default_lot_ratio_table = apply_display_order(
        default_lot_ratio_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 Capa",
        "Lot측정률",
    )
    default_wf_ratio_table = reference_to_edit_table(
        filtered_wf_ratio, RATIO_DIMENSIONS, "WF측정률", "RQ_WF_RATIO"
    )
    default_wf_ratio_table = apply_display_order(
        default_wf_ratio_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 Capa",
        "WF측정률",
    )
except (OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

editor_keys = (
    "capa_upeh_editor",
    "capa_run_rate_editor",
    "capa_vital_editor",
    "capa_lot_ratio_editor",
    "capa_wf_ratio_editor",
    "capa_run_day_editor",
)
source_token_key = "capacity_standards_source_token"
source_token = (
    f"{workbook.resolve()}:{reference_version}:{active_scenario['revision']}:"
    f"{start_month}:{end_month}"
)
if st.session_state.get(source_token_key) != source_token:
    for editor_key in editor_keys:
        st.session_state.pop(editor_key, None)
    st.session_state[source_token_key] = source_token

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"활성 시나리오 · 수정본 {active_scenario['revision']}")
    if st.button(
        ":material/restart_alt: 전체 입력 원본으로 초기화",
        key="reset_capacity_active_scenario",
    ):
        reset_active_scenario(reference_tables, reference_version)
        st.session_state.pop(source_token_key, None)
        st.rerun()

edited_upeh_table, apply_upeh = render_month_editor(
    tabs[1],
    default_upeh_table,
    PERFORMANCE_EDITOR_DIMENSIONS,
    editor_keys[0],
    "Main은 UPEH, MI는 ST(초)를 수정합니다. 수정 후 적용 버튼을 누르세요.",
    "%,.2f",
    0.01,
)
edited_run_rate_table, apply_run_rate = render_month_editor(
    tabs[2],
    default_run_rate_table,
    RUN_RATE_DIMENSIONS,
    editor_keys[1],
    "공정·양산별 효율을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
)
edited_vital_table, apply_vital = render_month_editor(
    tabs[3],
    default_vital_table,
    VITAL_DIMENSIONS,
    editor_keys[2],
    "공정·양산별 여유율을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
)
edited_lot_ratio_table, apply_lot_ratio = render_month_editor(
    tabs[4],
    default_lot_ratio_table,
    RATIO_DIMENSIONS,
    editor_keys[3],
    "분류별 Lot측정률을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
)
edited_wf_ratio_table, apply_wf_ratio = render_month_editor(
    tabs[5],
    default_wf_ratio_table,
    RATIO_DIMENSIONS,
    editor_keys[4],
    "분류별 WF측정률을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
)
edited_run_day_table, apply_run_day = render_month_editor(
    tabs[6],
    default_run_day_table,
    RUN_DAY_DIMENSIONS,
    editor_keys[5],
    "공정별 가동일수를 수정한 후 적용 버튼을 누르세요.",
    "%,.0f",
    1.0,
)

pending_updates: dict[str, pd.DataFrame] = {}
update_error_tab = unit_capacity_tab
try:
    if apply_upeh:
        update_error_tab = tabs[1]
        pending_updates["RQ_UPEH"] = performance_from_edit_table(edited_upeh_table)
    if apply_run_rate:
        update_error_tab = tabs[2]
        pending_updates["RQ_RUN_RATE"] = reference_from_edit_table(
            edited_run_rate_table, RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", "효율 편집값"
        )
    if apply_vital:
        update_error_tab = tabs[3]
        pending_updates["RQ_VITAL"] = reference_from_edit_table(
            edited_vital_table, VITAL_DIMENSIONS, "편중률", "여유율 편집값"
        )
    if apply_lot_ratio:
        update_error_tab = tabs[4]
        pending_updates["RQ_LOT_RATIO"] = reference_from_edit_table(
            edited_lot_ratio_table,
            RATIO_DIMENSIONS,
            "Lot 측정률",
            "Lot측정률 편집값",
        )
    if apply_wf_ratio:
        update_error_tab = tabs[5]
        pending_updates["RQ_WF_RATIO"] = reference_from_edit_table(
            edited_wf_ratio_table, RATIO_DIMENSIONS, "WF측정률", "WF측정률 편집값"
        )
    if apply_run_day:
        update_error_tab = tabs[6]
        pending_updates["RQ_RUN_DAY"] = reference_from_edit_table(
            edited_run_day_table, RUN_DAY_DIMENSIONS, "RUN_DAY", "일수 편집값"
        )
    if pending_updates:
        apply_month_updates(
            active_scenario,
            pending_updates,
            effective_start_month,
            effective_end_month,
        )
        st.session_state.pop(source_token_key, None)
        st.rerun()
except (KeyError, ValueError) as exc:
    with update_error_tab:
        st.error(str(exc))
    st.stop()

simulation_upeh = filtered_upeh
simulation_run_rate = filtered_run_rate
simulation_vital = filtered_vital
simulation_lot_ratio = filtered_lot_ratio
simulation_wf_ratio = filtered_wf_ratio
simulation_run_day = filtered_run_day

try:
    unit_capacity = get_unit_capacity(
        upeh=simulation_upeh,
        run_rate=simulation_run_rate,
        vital=simulation_vital,
        module=reference_tables["RQ_MODULE"],
        run_day=simulation_run_day,
        lot_ratio=simulation_lot_ratio,
        wf_ratio=simulation_wf_ratio,
    )
    unit_capacity_table = unit_capacity_to_month_table(unit_capacity)
    excluded_capacity_rows = unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
    unit_capacity_table = apply_display_order(
        unit_capacity_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "공정별 Capa",
        "대당 Capa",
    )
except ValueError as exc:
    with unit_capacity_tab:
        st.error(str(exc))
else:
    with unit_capacity_tab:
        if not excluded_capacity_rows.empty:
            st.warning(f"대당 Capa 산출에서 {len(excluded_capacity_rows):,}개 기준을 제외했습니다.")
            with st.expander("제외 기준정보 확인", expanded=False):
                st.dataframe(excluded_capacity_rows, hide_index=True, width="stretch")
        st.caption("공정·제품 분류별 월간 대당 Capa")
        month_columns = [
            column
            for column in unit_capacity_table.columns
            if column not in UNIT_CAPACITY_DIMENSIONS
        ]
        styled_table = unit_capacity_table.style.set_properties(
            subset=pd.Index(UNIT_CAPACITY_DIMENSIONS),
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
                    for column in UNIT_CAPACITY_DIMENSIONS
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        format="%,.0f",
                        alignment="center",
                    )
                    for month in month_columns
                },
            },
        )
