# Purpose: 공정 유효 Capa와 STEP 상세를 표시하고 관련 기준정보 및 STEP 구성을 편집한다.

from types import TracebackType
from typing import Protocol

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
    reset_active_scenario,
    scenario_month_table,
)
from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    performance_from_edit_table,
    performance_to_edit_table,
    reference_from_edit_table,
    reference_to_edit_table,
)
from capa_simulation.services.display_order import (
    apply_display_order,
    reorder_display_columns,
)
from capa_simulation.services.route_step_editor import (
    ROUTE_GROUP_COLUMNS,
    clone_route_step,
    delete_route_step,
    route_step_catalog,
    route_step_summary,
)
from capa_simulation.services.simulation_cache import get_required_equipment, get_unit_capacity
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    unit_capacity_to_month_table,
)
from capa_simulation.services.weighted_unit_capacity import (
    WEIGHTED_CAPACITY_HIERARCHY,
    effective_process_capacity_to_month_table,
)

TAB_NAMES = (
    "📊 공정 유효 Capa",
    "STEP 구성",
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
    "STEP_SEQ": "Step",
    "MCP_SEQ": "MCP",
}
RUN_RATE_DIMENSIONS = ["공정", "양산구분"]
VITAL_DIMENSIONS = ["공정", "양산구분"]
RUN_DAY_DIMENSIONS = ["공정"]
RATIO_DIMENSIONS = [
    "공정",
    "Area_Name",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
]
CAPACITY_LEVEL_LABELS = {
    "공정": "공정",
    "양산구분": "양산",
    "제품정보": "제품",
    "Stack": "Stack",
    "WF 구분": "WF 속성",
}


class OpenTab(Protocol):
    @property
    def open(self) -> bool | None: ...

    def __enter__(self) -> "OpenTab": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


def selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


def render_month_editor(
    tab: OpenTab,
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    caption: str,
    number_format: str,
    step: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    *,
    table_name: str,
    csv_file_name: str,
) -> tuple[pd.DataFrame, bool, pd.DataFrame | None]:
    if tab.open is False:
        return pd.DataFrame(), False, None
    month_columns = [column for column in default_table.columns if column not in dimensions]
    styled_table = default_table.style.set_properties(
        subset=pd.Index(dimensions),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
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
        imported = render_reference_clipboard_tools(
            default_table,
            table_name=table_name,
            key_columns=dimensions,
            file_name=csv_file_name,
            key=f"{editor_key}_csv",
        )
    return edited, submitted, imported


st.title("공정별 Capa")

tabs = st.tabs(
    TAB_NAMES,
    key="capacity_standards_active_tab",
    on_change="rerun",
)
unit_capacity_tab = tabs[0]

try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    display_order = context.display_order
    active_scenario = context.active_scenario
    start_month = context.selected_start_month
    end_month = context.selected_end_month
    effective_start_month, effective_end_month = resolve_effective_months(
        context,
        reference_tables["RQ_UPEH"],
        "RQ_UPEH",
        empty_message="선택 범위에 공정별 Capa 기준정보가 없습니다.",
    )
    filtered_upeh = scenario_month_table(active_scenario, "RQ_UPEH", start_month, end_month)
    filtered_run_rate = scenario_month_table(active_scenario, "RQ_RUN_RATE", start_month, end_month)
    filtered_vital = scenario_month_table(active_scenario, "RQ_VITAL", start_month, end_month)
    filtered_run_day = scenario_month_table(active_scenario, "RQ_RUN_DAY", start_month, end_month)
    filtered_lot_ratio = scenario_month_table(
        active_scenario, "RQ_LOT_RATIO", start_month, end_month
    )
    filtered_wf_ratio = scenario_month_table(active_scenario, "RQ_WF_RATIO", start_month, end_month)
    filtered_plan = scenario_month_table(active_scenario, "RQ_PKG_PLAN", start_month, end_month)
    filtered_yield = scenario_month_table(active_scenario, "RQ_YLD", start_month, end_month)
    filtered_reqb = scenario_month_table(active_scenario, "RQ_REQB", start_month, end_month)

    default_upeh_table = performance_to_edit_table(filtered_upeh)
    default_upeh_table = apply_display_order(
        default_upeh_table, display_order, "공정별 Capa", "UPEH"
    )
    default_upeh_table, _ = reorder_display_columns(
        default_upeh_table,
        PERFORMANCE_EDITOR_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "UPEH",
    )
    default_run_rate_table = reference_to_edit_table(
        filtered_run_rate, RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", "RQ_RUN_RATE"
    )
    default_run_rate_table = apply_display_order(
        default_run_rate_table, display_order, "공정별 Capa", "효율"
    )
    default_run_rate_table, _ = reorder_display_columns(
        default_run_rate_table,
        RUN_RATE_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "효율",
    )
    default_vital_table = reference_to_edit_table(
        filtered_vital, VITAL_DIMENSIONS, "편중률", "RQ_VITAL"
    )
    default_vital_table = apply_display_order(
        default_vital_table, display_order, "공정별 Capa", "여유율"
    )
    default_vital_table, _ = reorder_display_columns(
        default_vital_table,
        VITAL_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "여유율",
    )
    default_run_day_table = reference_to_edit_table(
        filtered_run_day, RUN_DAY_DIMENSIONS, "RUN_DAY", "RQ_RUN_DAY"
    )
    default_run_day_table = apply_display_order(
        default_run_day_table, display_order, "공정별 Capa", "일수"
    )
    default_run_day_table, _ = reorder_display_columns(
        default_run_day_table,
        RUN_DAY_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "일수",
    )
    default_lot_ratio_table = reference_to_edit_table(
        filtered_lot_ratio, RATIO_DIMENSIONS, "Lot 측정률", "RQ_LOT_RATIO"
    )
    default_lot_ratio_table = apply_display_order(
        default_lot_ratio_table,
        display_order,
        "공정별 Capa",
        "Lot측정률",
    )
    default_lot_ratio_table, _ = reorder_display_columns(
        default_lot_ratio_table,
        RATIO_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "Lot측정률",
    )
    default_wf_ratio_table = reference_to_edit_table(
        filtered_wf_ratio, RATIO_DIMENSIONS, "WF측정률", "RQ_WF_RATIO"
    )
    default_wf_ratio_table = apply_display_order(
        default_wf_ratio_table,
        display_order,
        "공정별 Capa",
        "WF측정률",
    )
    default_wf_ratio_table, _ = reorder_display_columns(
        default_wf_ratio_table,
        RATIO_DIMENSIONS,
        display_order,
        "공정별 Capa",
        "WF측정률",
    )
    step_summary = route_step_summary(filtered_reqb)
    step_catalog = route_step_catalog(filtered_upeh, filtered_reqb)
except BOOTSTRAP_ERRORS as exc:
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
step_widget_keys = (
    "capacity_step_mode",
    "capacity_step_route",
    "capacity_step_new_mcp",
    "capacity_step_new_step",
    "capacity_step_delete_confirm",
)
source_token_key = "capacity_standards_source_token"
source_token = f"duckdb:{reference_version}:{active_scenario['revision']}:{start_month}:{end_month}"
if st.session_state.get(source_token_key) != source_token:
    for editor_key in editor_keys:
        st.session_state.pop(editor_key, None)
    for widget_key in step_widget_keys:
        st.session_state.pop(widget_key, None)
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

with tabs[1]:
    flash_message = st.session_state.pop("capacity_step_flash", None)
    if isinstance(flash_message, str):
        st.success(flash_message)
    st.caption(
        "STEP 수는 같은 공정·제품 경로 안의 MCP_SEQ·STEP_SEQ 고유 조합 수입니다. "
        "추가·삭제는 조회기간 안에서 RQ_REQB·UPEH·Lot/WF 측정률에 함께 반영됩니다."
    )
    st.dataframe(
        step_summary.rename(
            columns={
                "생산계획년월": "월",
                "Area_Name": "Area",
                "양산구분": "양산",
                "제품정보": "제품",
                "WF 구분": "속성",
            }
        ),
        hide_index=True,
        width="stretch",
        height=260,
        column_config={
            "STEP 수": st.column_config.NumberColumn(format="%d"),
            "수요 변형 수": st.column_config.NumberColumn(format="%d"),
        },
        key="capacity_step_summary",
    )

    if step_catalog.empty:
        st.warning("선택한 조회기간에 편집할 공정 경로 STEP이 없습니다.")
    else:
        step_mode = st.segmented_control(
            "작업",
            options=["STEP 추가", "STEP 삭제"],
            default="STEP 추가",
            key="capacity_step_mode",
            persist_state="page",
            # 선택 해제를 허용하면 step_mode가 None이 되어 아래 분기가 `STEP 삭제`로
            # 넘어간다.
            required=True,
        )
        route_options = list(range(len(step_catalog)))

        def route_label(index: int) -> str:
            row = step_catalog.iloc[index]
            return (
                f"{row['공정']} · {row['제품정보']} · {row['Stack']} · {row['WF 구분']} · "
                f"{row['Area_Name']} · {row['소요기준']} · "
                f"MCP {row['MCP_SEQ']} / STEP {row['STEP_SEQ']} · {row['적용월수']}개월"
            )

        selected_route_index = st.selectbox(
            "복제 원본 또는 삭제 대상 STEP",
            options=route_options,
            format_func=route_label,
            key="capacity_step_route",
            persist_state="page",
        )
        selected_route_row = step_catalog.iloc[int(selected_route_index)]
        st.info(
            "기본 일괄 적용: 선택한 원본 STEP에 연결된 "
            f"Capa Code·Customer·CS 수요 변형 {int(selected_route_row['수요 변형 수']):,}개를 "
            "모두 함께 처리합니다."
        )

        with st.form("capacity_step_change_form"):
            if step_mode == "STEP 추가":
                new_mcp_seq = st.text_input(
                    "신규 MCP_SEQ",
                    placeholder="실제 MCP_SEQ 입력",
                    key="capacity_step_new_mcp",
                )
                new_step_seq = st.text_input(
                    "신규 STEP_SEQ",
                    placeholder="실제 STEP_SEQ 입력",
                    key="capacity_step_new_step",
                )
                step_submitted = st.form_submit_button(
                    "STEP 일괄 추가",
                    icon=":material/add:",
                    type="primary",
                )
                delete_confirmed = False
            else:
                delete_confirmed = st.checkbox(
                    "선택한 STEP을 조회기간의 모든 연결 수요에서 삭제합니다.",
                    key="capacity_step_delete_confirm",
                )
                step_submitted = st.form_submit_button(
                    "STEP 일괄 삭제",
                    icon=":material/delete:",
                    type="primary",
                )
                new_mcp_seq = ""
                new_step_seq = ""

        if step_submitted:
            route = {column: selected_route_row[column] for column in ROUTE_GROUP_COLUMNS}
            route_tables = {
                "RQ_REQB": filtered_reqb,
                "RQ_UPEH": filtered_upeh,
                "RQ_LOT_RATIO": filtered_lot_ratio,
                "RQ_WF_RATIO": filtered_wf_ratio,
            }
            try:
                if step_mode == "STEP 추가":
                    step_result = clone_route_step(
                        route_tables,
                        route,
                        source_mcp_seq=str(selected_route_row["MCP_SEQ"]),
                        source_step_seq=str(selected_route_row["STEP_SEQ"]),
                        new_mcp_seq=new_mcp_seq,
                        new_step_seq=new_step_seq,
                    )
                    action_label = "추가"
                elif delete_confirmed:
                    step_result = delete_route_step(
                        route_tables,
                        route,
                        mcp_seq=str(selected_route_row["MCP_SEQ"]),
                        step_seq=str(selected_route_row["STEP_SEQ"]),
                    )
                    action_label = "삭제"
                else:
                    raise ValueError("STEP 삭제 확인이 필요합니다.")
                apply_month_updates(
                    active_scenario,
                    step_result.replacements,
                    effective_start_month,
                    effective_end_month,
                )
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                months_label = ", ".join(str(month) for month in step_result.affected_months)
                st.session_state["capacity_step_flash"] = (
                    f"STEP을 {action_label}했습니다. 적용월 {months_label} · "
                    f"수요 변형 {step_result.affected_variants:,}개 · "
                    f"RQ_REQB {step_result.affected_reqb_rows:,}행"
                )
                st.session_state.pop(source_token_key, None)
                st.rerun()

edited_upeh_table, apply_upeh, imported_upeh_table = render_month_editor(
    tabs[2],
    default_upeh_table,
    PERFORMANCE_EDITOR_DIMENSIONS,
    editor_keys[0],
    "Main은 UPEH, MI는 ST(초)를 수정합니다. 수정 후 적용 버튼을 누르세요.",
    "%,.2f",
    0.01,
    table_name="RQ_UPEH",
    csv_file_name=f"RQ_UPEH_{effective_start_month}_{effective_end_month}.csv",
)
edited_run_rate_table, apply_run_rate, imported_run_rate_table = render_month_editor(
    tabs[3],
    default_run_rate_table,
    RUN_RATE_DIMENSIONS,
    editor_keys[1],
    "공정·양산별 효율을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
    table_name="RQ_RUN_RATE",
    csv_file_name=f"RQ_RUN_RATE_{effective_start_month}_{effective_end_month}.csv",
)
edited_vital_table, apply_vital, imported_vital_table = render_month_editor(
    tabs[4],
    default_vital_table,
    VITAL_DIMENSIONS,
    editor_keys[2],
    "공정·양산별 여유율을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    table_name="RQ_VITAL",
    csv_file_name=f"RQ_VITAL_{effective_start_month}_{effective_end_month}.csv",
)
edited_lot_ratio_table, apply_lot_ratio, imported_lot_ratio_table = render_month_editor(
    tabs[5],
    default_lot_ratio_table,
    RATIO_DIMENSIONS,
    editor_keys[3],
    "분류별 Lot측정률을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
    table_name="RQ_LOT_RATIO",
    csv_file_name=f"RQ_LOT_RATIO_{effective_start_month}_{effective_end_month}.csv",
)
edited_wf_ratio_table, apply_wf_ratio, imported_wf_ratio_table = render_month_editor(
    tabs[6],
    default_wf_ratio_table,
    RATIO_DIMENSIONS,
    editor_keys[4],
    "분류별 WF측정률을 수정한 후 적용 버튼을 누르세요.",
    "percent",
    0.001,
    max_value=1.0,
    table_name="RQ_WF_RATIO",
    csv_file_name=f"RQ_WF_RATIO_{effective_start_month}_{effective_end_month}.csv",
)
edited_run_day_table, apply_run_day, imported_run_day_table = render_month_editor(
    tabs[7],
    default_run_day_table,
    RUN_DAY_DIMENSIONS,
    editor_keys[5],
    "공정별 가동일수를 수정한 후 적용 버튼을 누르세요.",
    "%,.0f",
    1.0,
    table_name="RQ_RUN_DAY",
    csv_file_name=f"RQ_RUN_DAY_{effective_start_month}_{effective_end_month}.csv",
)

pending_updates: dict[str, pd.DataFrame] = {}
update_error_tab = unit_capacity_tab
import_flash: tuple[str, str] | None = None
try:
    if apply_upeh or imported_upeh_table is not None:
        update_error_tab = tabs[2]
        source = imported_upeh_table if imported_upeh_table is not None else edited_upeh_table
        pending_updates["RQ_UPEH"] = performance_from_edit_table(source)
        if imported_upeh_table is not None:
            import_flash = ("upeh_editor_csv", "RQ_UPEH 붙여넣기 데이터를 일괄 적용했습니다.")
    if apply_run_rate or imported_run_rate_table is not None:
        update_error_tab = tabs[3]
        source = (
            imported_run_rate_table
            if imported_run_rate_table is not None
            else edited_run_rate_table
        )
        pending_updates["RQ_RUN_RATE"] = reference_from_edit_table(
            source, RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", "효율 편집값"
        )
        if imported_run_rate_table is not None:
            import_flash = (
                "run_rate_editor_csv",
                "RQ_RUN_RATE 붙여넣기 데이터를 일괄 적용했습니다.",
            )
    if apply_vital or imported_vital_table is not None:
        update_error_tab = tabs[4]
        source = imported_vital_table if imported_vital_table is not None else edited_vital_table
        pending_updates["RQ_VITAL"] = reference_from_edit_table(
            source, VITAL_DIMENSIONS, "편중률", "여유율 편집값"
        )
        if imported_vital_table is not None:
            import_flash = (
                "vital_editor_csv",
                "RQ_VITAL 붙여넣기 데이터를 일괄 적용했습니다.",
            )
    if apply_lot_ratio or imported_lot_ratio_table is not None:
        update_error_tab = tabs[5]
        source = (
            imported_lot_ratio_table
            if imported_lot_ratio_table is not None
            else edited_lot_ratio_table
        )
        pending_updates["RQ_LOT_RATIO"] = reference_from_edit_table(
            source,
            RATIO_DIMENSIONS,
            "Lot 측정률",
            "Lot측정률 편집값",
        )
        if imported_lot_ratio_table is not None:
            import_flash = (
                "lot_ratio_editor_csv",
                "RQ_LOT_RATIO 붙여넣기 데이터를 일괄 적용했습니다.",
            )
    if apply_wf_ratio or imported_wf_ratio_table is not None:
        update_error_tab = tabs[6]
        source = (
            imported_wf_ratio_table
            if imported_wf_ratio_table is not None
            else edited_wf_ratio_table
        )
        pending_updates["RQ_WF_RATIO"] = reference_from_edit_table(
            source, RATIO_DIMENSIONS, "WF측정률", "WF측정률 편집값"
        )
        if imported_wf_ratio_table is not None:
            import_flash = (
                "wf_ratio_editor_csv",
                "RQ_WF_RATIO 붙여넣기 데이터를 일괄 적용했습니다.",
            )
    if apply_run_day or imported_run_day_table is not None:
        update_error_tab = tabs[7]
        source = (
            imported_run_day_table if imported_run_day_table is not None else edited_run_day_table
        )
        pending_updates["RQ_RUN_DAY"] = reference_from_edit_table(
            source, RUN_DAY_DIMENSIONS, "RUN_DAY", "일수 편집값"
        )
        if imported_run_day_table is not None:
            import_flash = (
                "run_day_editor_csv",
                "RQ_RUN_DAY 붙여넣기 데이터를 일괄 적용했습니다.",
            )
    if pending_updates:
        apply_month_updates(
            active_scenario,
            pending_updates,
            effective_start_month,
            effective_end_month,
        )
        if import_flash is not None:
            queue_reference_import_flash(*import_flash)
        st.session_state.pop(source_token_key, None)
        st.rerun()
except (KeyError, ValueError) as exc:
    with update_error_tab:
        st.error(str(exc))
    st.stop()

if not unit_capacity_tab.open:
    st.stop()

simulation_upeh = filtered_upeh
simulation_run_rate = filtered_run_rate
simulation_vital = filtered_vital
simulation_lot_ratio = filtered_lot_ratio
simulation_wf_ratio = filtered_wf_ratio
simulation_run_day = filtered_run_day
simulation_plan = filtered_plan
simulation_yield = filtered_yield

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
    required_equipment_for_display = get_required_equipment(
        reqb=filtered_reqb,
        plan=simulation_plan,
        yield_data=simulation_yield,
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    excluded_capacity_rows = unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
except ValueError as exc:
    with unit_capacity_tab:
        st.error(str(exc))
else:
    with unit_capacity_tab:
        if not excluded_capacity_rows.empty:
            st.warning(f"대당 Capa 산출에서 {len(excluded_capacity_rows):,}개 기준을 제외했습니다.")
            with st.expander("제외 기준정보 확인", expanded=False):
                displayed_exclusions, _ = reorder_display_columns(
                    excluded_capacity_rows,
                    [
                        column
                        for column in UNIT_CAPACITY_DIMENSIONS
                        if column in excluded_capacity_rows.columns
                    ],
                    display_order,
                    "공정별 Capa",
                    "대당 Capa",
                )
                st.dataframe(displayed_exclusions, hide_index=True, width="stretch")

        process_order = required_equipment_for_display[["공정"]].drop_duplicates()
        process_order = apply_display_order(
            process_order,
            display_order,
            "공정별 Capa",
            "대당 Capa",
        )
        process_options = process_order["공정"].astype(str).tolist()
        process_filter_key = "unit_capacity_process_filter"
        saved_processes = st.session_state.get(process_filter_key, [])
        if isinstance(saved_processes, list):
            st.session_state[process_filter_key] = [
                process for process in saved_processes if process in process_options
            ]
        with st.container(border=True):
            view_column, level_column, process_column = st.columns([1.4, 1, 2])
            with view_column:
                capacity_view = st.segmented_control(
                    "표시 방식",
                    options=["공정 유효 Capa", "STEP별 대당 Capa"],
                    default="공정 유효 Capa",
                    key="unit_capacity_view_mode",
                    persist_state="page",
                )
            with level_column:
                selected_level_label = st.selectbox(
                    "집계 수준",
                    options=list(CAPACITY_LEVEL_LABELS.values()),
                    index=0,
                    key="unit_capacity_detail_level",
                    disabled=capacity_view == "STEP별 대당 Capa",
                )
            with process_column:
                selected_processes = st.multiselect(
                    "공정 필터",
                    options=process_options,
                    placeholder="미선택 시 전체 공정",
                    key=process_filter_key,
                )

        selected_level = next(
            level for level, label in CAPACITY_LEVEL_LABELS.items() if label == selected_level_label
        )
        if capacity_view == "STEP별 대당 Capa":
            unit_capacity_table = unit_capacity_to_month_table(unit_capacity)
            classification_columns = list(UNIT_CAPACITY_DIMENSIONS)
            output_title = "STEP별 대당 Capa"
            output_caption = (
                "각 MCP_SEQ·STEP_SEQ 경로의 상세 대당 Capa입니다. "
                "공정 전체 Capa 판단에는 기본 공정 유효 Capa를 사용하세요."
            )
            file_prefix = "Capa_Step_Unit_Capacity"
        else:
            unit_capacity_table = effective_process_capacity_to_month_table(
                required_equipment_for_display,
                selected_level,
            )
            classification_columns = [
                column
                for column in ["공정", "소요기준", *WEIGHTED_CAPACITY_HIERARCHY[1:]]
                if column in unit_capacity_table.columns
            ]
            output_title = "공정 유효 Capa"
            output_caption = (
                "중복되지 않은 원수요 부하량을 STEP별 소요대수 합계로 나눈 값입니다. "
                "STEP이 추가되면 소요대수는 누적되고 공정 유효 Capa는 감소합니다."
            )
            file_prefix = "Capa_Effective_Process_Capacity"
        unit_capacity_table = apply_display_order(
            unit_capacity_table,
            display_order,
            "공정별 Capa",
            "대당 Capa",
        )
        unit_capacity_table, classification_columns = reorder_display_columns(
            unit_capacity_table,
            classification_columns,
            display_order,
            "공정별 Capa",
            "대당 Capa",
        )
        if selected_processes:
            unit_capacity_table = unit_capacity_table.loc[
                unit_capacity_table["공정"].isin(selected_processes)
            ].reset_index(drop=True)

        capacity_export = build_hierarchical_monthly_export(
            unit_capacity_table,
            classification_columns=classification_columns,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=0,
        )
        capacity_csv = capacity_export.to_csv(index=False, float_format="%.0f").encode("utf-8-sig")
        st.caption(output_caption)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader(output_title, width="content")
            st.download_button(
                ":material/download: CSV 다운로드",
                data=capacity_csv,
                file_name=(
                    f"{file_prefix}_"
                    f"{selected_level}_{effective_start_month}_{effective_end_month}.csv"
                ),
                mime="text/csv;charset=utf-8",
                key="download_unit_capacity_csv",
                on_click="ignore",
                width="content",
            )
        render_hierarchical_monthly_table(
            unit_capacity_table,
            classification_columns=classification_columns,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=0,
            key="unit_capacity_monthly_table",
        )
