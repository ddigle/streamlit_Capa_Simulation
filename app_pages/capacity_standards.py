# Purpose: 공정 유효 Capa와 STEP 상세를 표시하고 관련 기준정보 및 STEP 구성을 편집한다.


import pandas as pd
import streamlit as st

from capa_simulation.components.exclusion_table import render_exclusion_table
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.month_editor import render_month_editor
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.reference_csv_tools import (
    queue_reference_import_flash,
)
from capa_simulation.components.scenario_edit_bar import render_scenario_edit_bar
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import render_table_heading
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.scenario_state import (
    apply_month_updates,
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
)
from capa_simulation.services.simulation_cache import (
    get_effective_process_capacity_table,
    get_route_step_tables,
    get_scenario_capacity_and_demand,
    scenario_cache_key,
)
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    unit_capacity_to_month_table,
)
from capa_simulation.services.weighted_unit_capacity import WEIGHTED_CAPACITY_HIERARCHY

TAB_NAMES = (
    ":material/insights: 공정 유효 Capa",
    "STEP 구성",
    "UPEH",
    "효율",
    "여유율",
    "Lot측정률",
    "WF측정률",
    "일수",
)

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


render_page_header(
    "공정별 Capa",
    description=(
        "경로별 대당 Capa와 공정 유효 Capa를 산출하고, 계산에 쓰는 기준정보를 월별로 편집합니다."
    ),
)
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()

tabs = stateful_tabs(TAB_NAMES, key="capacity_standards_active_tab")
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

    # 편집표 여섯 개는 자기 탭이 열려 있을 때만 만든다. 숨은 탭에서는 month_editor 가
    # default_table 을 읽기 전에 돌아가므로 만들어 봐야 버려진다 — 기본 탭에서 rerun 마다
    # 519~793ms 를 피벗·정렬에 쓰고 있었다.
    default_upeh_table = pd.DataFrame()
    if not tab_is_hidden(tabs[2]):
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
    default_run_rate_table = pd.DataFrame()
    if not tab_is_hidden(tabs[3]):
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
    default_vital_table = pd.DataFrame()
    if not tab_is_hidden(tabs[4]):
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
    default_run_day_table = pd.DataFrame()
    if not tab_is_hidden(tabs[7]):
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
    default_lot_ratio_table = pd.DataFrame()
    if not tab_is_hidden(tabs[5]):
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
    default_wf_ratio_table = pd.DataFrame()
    if not tab_is_hidden(tabs[6]):
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
    # STEP 구성 탭의 요약·목록. 목록은 작업·경로 선택 위젯의 options 라 탭이 닫혀 있어도
    # 있어야 한다(숨은 탭에서는 그림만 건너뛴다). 그래서 건너뛰는 대신 내용 토큰으로 캐시한다.
    step_summary, step_catalog = get_route_step_tables(
        scenario_cache_key(reference_version, active_scenario, start_month, end_month),
        _upeh=filtered_upeh,
        _reqb=filtered_reqb,
    )
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

render_scenario_edit_bar(
    active_scenario,
    reference_tables,
    reference_version,
    reset_key="reset_capacity_active_scenario",
    clear_session_keys=(source_token_key,),
)

with tabs[1]:
    flash_message = st.session_state.pop("capacity_step_flash", None)
    if isinstance(flash_message, str):
        st.success(flash_message)
    st.caption(
        "STEP 수는 같은 공정·제품 경로 안의 MCP_SEQ·STEP_SEQ 고유 조합 수입니다. "
        "추가·삭제는 조회기간 안에서 RQ_REQB·UPEH·Lot/WF 측정률에 함께 반영됩니다."
    )
    # 요약 표는 그림이라 숨은 탭에서는 건너뛴다. 아래 작업·경로 선택과 form 은 위젯이라
    # 항상 그린다 — 본문을 통째로 건너뛰면 탭을 오갈 때 선택값이 초기화된다.
    if not tab_is_hidden(tabs[1]):
        # `step_summary` 는 캐시된 프레임이다. 제자리에서 고치면 다음 rerun 이 표시명 프레임을
        # 계산 입력으로 받으므로 화면 복사본에만 표시명을 입힌다.
        displayed_step_summary = step_summary.rename(
            columns={
                "생산계획년월": "월",
                "Area_Name": "Area",
                "양산구분": "양산",
                "제품정보": "제품",
                "WF 구분": "속성",
            }
        ).copy()
        displayed_step_summary["공정"] = process_labels.series(displayed_step_summary["공정"])
        st.dataframe(
            displayed_step_summary,
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
            # 표시 문자열만 만든다. 선택값은 정수 인덱스이고 아래에서 다시 `step_catalog` 의
            # 원본 행을 읽어 STEP 복제·삭제에 넘기므로 값 경로에는 표시명이 닿지 않는다.
            row = step_catalog.iloc[index]
            return (
                f"{process_labels.label(row['공정'])} · {row['제품정보']} · "
                f"{row['Stack']} · {row['WF 구분']} · "
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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
    # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
    value_labels=process_labels.value_labels(),
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

# 표시 방식·집계 수준·공정 필터는 입력 위젯이라 탭이 닫혀 있어도 항상 그린다. 본문을
# 통째로 건너뛰면 Streamlit 이 세 위젯의 상태를 버려 탭을 오갈 때마다 선택이 초기화된다.
# 건너뛰는 것은 계산·표·CSV·Plotly 뿐이다.
capacity_tab_hidden = tab_is_hidden(unit_capacity_tab)
process_filter_key = "unit_capacity_process_filter"
excluded_capacity_rows = pd.DataFrame()
capacity_error: str | None = None
capacity_ready = False
process_options: list[str] = []
if not capacity_tab_hidden:
    try:
        # 편집은 apply_month_updates 로 활성 시나리오에 반영되고 content_token 이 바뀐다.
        # 그래서 활성 시나리오 표를 키로 캐시한 계산이 곧 "편집 중인 기준정보" 계산이다.
        unit_capacity, required_equipment_for_display = get_scenario_capacity_and_demand(
            scenario_cache_key(reference_version, active_scenario, start_month, end_month),
            _scenario_tables=active_scenario["tables"],
            _reference_tables=reference_tables,
        )
    except ValueError as exc:
        capacity_error = str(exc)
    else:
        capacity_ready = True
        excluded_capacity_rows = unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
        process_order = required_equipment_for_display[["공정"]].drop_duplicates()
        process_order = apply_display_order(
            process_order,
            display_order,
            "공정별 Capa",
            "대당 Capa",
        )
        process_options = process_order["공정"].astype(str).tolist()

saved_processes = st.session_state.get(process_filter_key, [])
if not isinstance(saved_processes, list):
    saved_processes = []
if not capacity_ready:
    # 옵션을 만들 계산을 돌리지 않은 렌더다. 지금 선택값을 그대로 옵션으로 두어야
    # multiselect 가 그 선택을 버리지 않는다.
    process_options = [str(process) for process in saved_processes]
st.session_state[process_filter_key] = [
    process for process in saved_processes if process in process_options
]

with unit_capacity_tab:
    if capacity_error is not None:
        st.error(capacity_error)
    if not excluded_capacity_rows.empty:
        st.warning(f"대당 Capa 산출에서 {len(excluded_capacity_rows):,}개 기준을 제외했습니다.")
        with st.expander("제외 기준정보 확인", expanded=False):
            render_exclusion_table(
                excluded_capacity_rows,
                dimensions=UNIT_CAPACITY_DIMENSIONS,
                display_order=display_order,
                page="공정별 Capa",
                tab="대당 Capa",
                labels=process_labels,
                file_name=(
                    "Capa_Unit_Capacity_Exclusions_"
                    f"{effective_start_month}_{effective_end_month}.csv"
                ),
                key="download_unit_capacity_exclusions_csv",
            )

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
                placeholder=(
                    "공정을 선택하세요"
                    if capacity_view == "STEP별 대당 Capa"
                    else "미선택 시 전체 공정"
                ),
                key=process_filter_key,
                # 표시만 바꾼다. 선택값은 원본이어야 아래 `isin` 이 원본 컬럼과 맞는다.
                format_func=process_labels.format_func(),
            )

    selected_level = next(
        level for level, label in CAPACITY_LEVEL_LABELS.items() if label == selected_level_label
    )
    if capacity_ready:
        # STEP 뷰는 경로 하나하나가 행이라 전 공정을 그리면 Plotly 표가 수천 행이 된다.
        # 미선택이면 표를 만들지도 CSV 로 인코딩하지도 않고 안내만 남긴다. 선택 해제를
        # 허용하는 컨트롤이라 `capacity_view` 는 None 일 수 있으므로 명시 비교로 판단한다.
        if capacity_view == "STEP별 대당 Capa" and not selected_processes:
            st.info(
                "STEP별 대당 Capa는 선택한 공정만 그립니다. 위 공정 필터에서 공정을 선택하세요. "
                "전체 공정을 한 번에 보려면 공정 유효 Capa를 사용하세요."
            )
        else:
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
                unit_capacity_table = get_effective_process_capacity_table(
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
                column_labels=COLUMN_LABELS,
                decimal_places=0,
            )
            capacity_csv = capacity_export.to_csv(index=False, float_format="%.0f").encode(
                "utf-8-sig"
            )
            st.caption(output_caption)
            render_table_heading(
                output_title,
                csv=capacity_csv,
                file_name=(
                    f"{file_prefix}_{selected_level}_"
                    f"{effective_start_month}_{effective_end_month}.csv"
                ),
                key="download_unit_capacity_csv",
            )
            render_hierarchical_monthly_table(
                unit_capacity_table,
                classification_columns=classification_columns,
                column_labels=COLUMN_LABELS,
                decimal_places=0,
                key="unit_capacity_monthly_table",
                value_labels=process_labels.value_labels(),
            )
