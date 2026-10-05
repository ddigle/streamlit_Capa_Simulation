# Purpose: Capa 산출에 쓰는 입력값과 STEP 구성을 월별로 편집한다.

"""기준 정보 — 조건 카드·Guide·작업 줄 양식(2026-09-29 사용자 결정, 생산 계획이 샘플).

- 표 필터와 설비대수 현황의 「상세」는 사이드바 조건 카드 `표 조건` 이다. 모든 탭이 같은 카드를
  써서 한 번 편 카드는 탭을 옮겨도 편 채다.
- 작업 버튼(변경사항 적용·Excel 붙여넣기·편집 취소, STEP 추가·삭제)은 표 **위**다. 붙여넣기와
  STEP 추가·삭제는 팝업이다.
- 설명은 Guide(`guides/reference_data.md`)다.
- **적용하지 않은 편집이 남은 표는 탭이 닫혀도 그린다**(`month_editor`) — 전에는 탭을 옮기는
  순간 편집이 사라졌다. 그런 탭 이름 옆에는 주황 점이 찍힌다.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from capa_simulation.components.column_filter import render_column_filter_controls
from capa_simulation.components.editor_state import editor_has_edits
from capa_simulation.components.month_editor import (
    classification_styled,
    editor_notice,
    render_month_editor,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.reference_csv_tools import queue_reference_import_flash
from capa_simulation.components.scenario_edit_bar import (
    mark_own_change,
    register_pending_edits,
    reset_editors_on_source_change,
    source_token,
)
from capa_simulation.components.tab_marks import mark_pending_tabs
from capa_simulation.components.tab_state import OpenTab, stateful_tabs, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.scenario_state import (
    ActiveScenario,
    apply_month_updates,
    scenario_month_table,
)
from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    performance_from_edit_table,
    reference_from_edit_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_REFERENCE,
    TAB_EQUIPMENT_COUNT,
    TAB_LOT_RATIO,
    TAB_RUN_DAY,
    TAB_RUN_RATE,
    TAB_UPEH,
    TAB_VITAL,
    TAB_WF_RATIO,
)
from capa_simulation.services.equipment_count import (
    DETAILED_EQUIPMENT_DIMENSIONS,
    EQUIPMENT_DIMENSIONS,
    build_equipment_count_table,
    equipment_count_from_edit_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.reference_consistency import (
    validate_required_edit,
    validate_upeh_edit,
)
from capa_simulation.services.reference_csv import count_removed_values
from capa_simulation.services.route_step_editor import (
    ROUTE_GROUP_COLUMNS,
    clone_route_step,
    delete_route_step,
)
from capa_simulation.services.simulation_cache import (
    display_order_digest,
    get_reference_edit_table,
    get_route_step_tables,
    scenario_cache_key,
)
from capa_simulation.sidebar_status import table_card

# Capa 산출에 **넣는 값만** 둔다. 산출물은 `산출 결과` 페이지가 갖는다.
# 순서는 사용자가 정한 입력 순서다.
# 이름 앞 아이콘은 그 탭이 다루는 값이다(탭 목록 개선안 B). 라벨은 위젯 값이라 테스트·기억
# 칸이 이 문자열을 그대로 쓴다.
TAB_NAMES = (
    ":material/timer: UPEH",
    ":material/precision_manufacturing: 설비대수",
    ":material/speed: 효율",
    ":material/donut_small: 여유율",
    ":material/calendar_month: 일수",
    ":material/stacks: Lot측정률",
    ":material/album: WF측정률",
    ":material/route: STEP 구성",
)
TAB_KEY = "reference_data_active_tab"
EQUIPMENT_TAB_NAMES = (
    ":material/inventory: 보유",
    ":material/swap_horiz: 대여",
    ":material/check_circle: 가용",
    ":material/table_view: 현황",
)
EQUIPMENT_TAB_KEY = "equipment_count_active_tab"
# 조건 카드 이름(사이드바 `표 조건`). 모든 탭이 하나를 쓴다.
CARD_NAME = "reference_data"
# 지금 열린 팝업: 편집표 key(붙여넣기) 또는 `STEP_DIALOG`. 한 칸이라 한 회차에 팝업은 하나다.
DIALOG_KEY = f"reference_data{PAGE_DIALOG_SUFFIX}"
STEP_DIALOG = "step"
EDITOR_UPEH = "capa_upeh_editor"
EDITOR_RUN_RATE = "capa_run_rate_editor"
EDITOR_VITAL = "capa_vital_editor"
EDITOR_LOT_RATIO = "capa_lot_ratio_editor"
EDITOR_WF_RATIO = "capa_wf_ratio_editor"
EDITOR_RUN_DAY = "capa_run_day_editor"

# 설비대수 세 RQ. 이름·화면 표기·값 컬럼·편집기 키가 네 곳에서 따로 적히면 한 군데만
# 고쳐져 조용히 어긋난다. 한 줄로 묶어 두고 편집기·적용·왕복 CSV 가 모두 이것을 읽는다.
EQUIPMENT_EDITORS = (
    ("RQ_EQP_OWN", "보유", "설비보유", "capa_eqp_own_editor"),
    ("RQ_EQP_LENT", "대여", "설비대여평가", "capa_eqp_lent_editor"),
    ("RQ_EQP_AVBL", "가용", "가용대수", "capa_eqp_avbl_editor"),
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
render_page_header("기준 정보")
render_page_guide("reference_data", title="기준 정보")
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()

# 인덱스로 받지 않는다. 순서를 바꿀 때 `tabs[N]` 을 일일이 세다 하나를 놓치면 예외가
# 나지 않고 표가 다른 탭에 조용히 그려진다.
(
    upeh_tab,
    equipment_tab,
    run_rate_tab,
    vital_tab,
    run_day_tab,
    lot_ratio_tab,
    wf_ratio_tab,
    step_tab,
) = stateful_tabs(TAB_NAMES, key=TAB_KEY)


def _editor_needed(tab: OpenTab, editor_key: str) -> bool:
    """편집표를 그릴 회차인가 — 탭이 열렸거나, 닫혔어도 적용하지 않은 편집이 남았다."""
    return not tab_is_hidden(tab) or editor_has_edits(editor_key)


def _ratio_month_table(
    scenario: ActiveScenario, table_name: str, start_month: int, end_month: int
) -> pd.DataFrame:
    """측정률 표의 편집 기간 조각. **표가 통째로 비었으면 같은 컬럼의 빈 표다.**

    `scenario_month_table`(→ `month_filter`)은 행이 하나도 없는 표를 「… 선택할 생산계획년월
    데이터가 없습니다」로 막는다. 측정률은 행이 없으면 1.0 으로 가정하는 표라
    (`unit_capacity._join_reference`) 비어도 계산은 이어 가는데, 모든 칸을 비워 적용하거나
    원천에 측정률 행이 없으면 이 화면 전체가 그 오류로 섰다(2026-09-29 2차 리뷰). 다른 호출자는
    빈 표를 오류로 기대할 수 있어 공용 함수의 뜻은 두고 여기서만 가른다. 비지 않은 표는 그대로
    `scenario_month_table` 을 지나 월 형식 오류가 계속 드러난다.
    """
    table = scenario["tables"].get(table_name)
    if table is not None and table.empty and "생산계획년월" in table.columns:
        return table.head(0).copy()
    return scenario_month_table(scenario, table_name, start_month, end_month)


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
    # 편집표·STEP 목록은 **적용과 같은 기간**(선택기간 ∩ UPEH 기준정보 범위)으로 자른다. 적용은
    # 그 기간만 갈아끼우므로(`apply_month_updates`), 편집표를 선택기간으로 자르면 UPEH 에 없는
    # 달이 선택기간에 드는 순간 모든 적용이 「편집값에 선택 범위 밖의 년월이 있습니다」로
    # 막혔다(2026-09-29 버그 보고 횡전개). 설비대수 세 표·부하량 환산 화면과 같은 규칙이다.
    filtered_upeh = scenario_month_table(
        active_scenario, "RQ_UPEH", effective_start_month, effective_end_month
    )
    filtered_run_rate = scenario_month_table(
        active_scenario, "RQ_RUN_RATE", effective_start_month, effective_end_month
    )
    filtered_vital = scenario_month_table(
        active_scenario, "RQ_VITAL", effective_start_month, effective_end_month
    )
    filtered_run_day = scenario_month_table(
        active_scenario, "RQ_RUN_DAY", effective_start_month, effective_end_month
    )
    filtered_lot_ratio = _ratio_month_table(
        active_scenario, "RQ_LOT_RATIO", effective_start_month, effective_end_month
    )
    filtered_wf_ratio = _ratio_month_table(
        active_scenario, "RQ_WF_RATIO", effective_start_month, effective_end_month
    )
    filtered_plan = scenario_month_table(active_scenario, "RQ_PKG_PLAN", start_month, end_month)
    filtered_yield = scenario_month_table(active_scenario, "RQ_YLD", start_month, end_month)
    filtered_reqb = scenario_month_table(
        active_scenario, "RQ_REQB", effective_start_month, effective_end_month
    )

    # 편집표 여섯 개는 자기 탭이 열려 있거나 **적용하지 않은 편집이 남았을 때만** 만든다.
    # 그 밖의 닫힌 탭에서는 month_editor 가 default_table 을 읽기 전에 돌아가므로 만들어 봐야
    # 버려진다 — 기본 탭에서 rerun 마다 519~793ms 를 피벗·정렬에 쓰고 있었다. 만드는 표는
    # 편집 기간·표시순서 내용으로 캐시한다(`get_reference_edit_table`).
    edit_cache_key = scenario_cache_key(
        reference_version, active_scenario, effective_start_month, effective_end_month
    )
    edit_display_order_key = display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])

    def _edit_table(
        tab: OpenTab,
        editor_key: str,
        data: pd.DataFrame,
        *,
        table_name: str,
        dimensions: list[str],
        value_column: str | None,
        scope_tab: str,
    ) -> pd.DataFrame:
        if not _editor_needed(tab, editor_key):
            return pd.DataFrame()
        return get_reference_edit_table(
            edit_cache_key,
            edit_display_order_key,
            table_name=table_name,
            dimensions=tuple(dimensions),
            value_column=value_column,
            page=PAGE_REFERENCE,
            tab=scope_tab,
            _data=data,
            _display_order=display_order,
        )

    default_upeh_table = _edit_table(
        upeh_tab,
        EDITOR_UPEH,
        filtered_upeh,
        table_name="RQ_UPEH",
        dimensions=PERFORMANCE_EDITOR_DIMENSIONS,
        value_column=None,
        scope_tab=TAB_UPEH,
    )
    default_run_rate_table = _edit_table(
        run_rate_tab,
        EDITOR_RUN_RATE,
        filtered_run_rate,
        table_name="RQ_RUN_RATE",
        dimensions=RUN_RATE_DIMENSIONS,
        value_column="CAPA_RUN_RATE",
        scope_tab=TAB_RUN_RATE,
    )
    default_vital_table = _edit_table(
        vital_tab,
        EDITOR_VITAL,
        filtered_vital,
        table_name="RQ_VITAL",
        dimensions=VITAL_DIMENSIONS,
        value_column="편중률",
        scope_tab=TAB_VITAL,
    )
    default_run_day_table = _edit_table(
        run_day_tab,
        EDITOR_RUN_DAY,
        filtered_run_day,
        table_name="RQ_RUN_DAY",
        dimensions=RUN_DAY_DIMENSIONS,
        value_column="RUN_DAY",
        scope_tab=TAB_RUN_DAY,
    )
    default_lot_ratio_table = _edit_table(
        lot_ratio_tab,
        EDITOR_LOT_RATIO,
        filtered_lot_ratio,
        table_name="RQ_LOT_RATIO",
        dimensions=RATIO_DIMENSIONS,
        value_column="Lot 측정률",
        scope_tab=TAB_LOT_RATIO,
    )
    default_wf_ratio_table = _edit_table(
        wf_ratio_tab,
        EDITOR_WF_RATIO,
        filtered_wf_ratio,
        table_name="RQ_WF_RATIO",
        dimensions=RATIO_DIMENSIONS,
        value_column="WF측정률",
        scope_tab=TAB_WF_RATIO,
    )
    # STEP 구성 탭의 요약·목록. 목록은 작업·경로 선택 위젯의 options 라 탭이 닫혀 있어도
    # 있어야 한다(숨은 탭에서는 그림만 건너뛴다). 그래서 건너뛰는 대신 내용 토큰으로 캐시한다.
    step_summary, step_catalog = get_route_step_tables(
        edit_cache_key,
        _upeh=filtered_upeh,
        _reqb=filtered_reqb,
    )
except BOOTSTRAP_ERRORS as exc:
    st.error(bootstrap_error_message(exc))
    st.stop()

editor_keys = (
    EDITOR_UPEH,
    EDITOR_RUN_RATE,
    EDITOR_VITAL,
    EDITOR_LOT_RATIO,
    EDITOR_WF_RATIO,
    EDITOR_RUN_DAY,
    *(editor_key for _, _, _, editor_key in EQUIPMENT_EDITORS),
)
step_widget_keys = (
    "capacity_step_mode",
    "capacity_step_route",
    "capacity_step_new_mcp",
    "capacity_step_new_step",
    "capacity_step_delete_confirm",
)
SOURCE_TOKEN_KEY = "reference_data_source_token"
# 이 화면이 스스로 적용한 편집(표 하나·STEP). 원본이 바뀌어도 그 적용이 건드린 표만 비운다 —
# 다른 탭에서 고치고 아직 적용하지 않은 편집은 남는다.
OWN_CHANGE_KEY = "reference_data_own_change"
reset_editors_on_source_change(
    SOURCE_TOKEN_KEY,
    source_token(reference_version, active_scenario, effective_start_month, effective_end_month),
    editor_keys,
    other_keys=step_widget_keys,
    own_change_key=OWN_CHANGE_KEY,
)
# 사이드바가 저장·불러오기 전에 「적용하지 않은 편집」을 묻도록 이 화면의 편집표를 알린다. 방금
# 적용한 표는 사이드바가 빼고 센다(`OWN_CHANGE_KEY`).
register_pending_edits(
    "reference_data.py",
    "기준 정보",
    {
        EDITOR_UPEH: "UPEH",
        EDITOR_RUN_RATE: "효율",
        EDITOR_VITAL: "여유율",
        EDITOR_LOT_RATIO: "Lot측정률",
        EDITOR_WF_RATIO: "WF측정률",
        EDITOR_RUN_DAY: "일수",
        **{editor_key: f"설비대수 {label}" for _, label, _, editor_key in EQUIPMENT_EDITORS},
    },
    own_change_key=OWN_CHANGE_KEY,
)

# 적용하지 않은 편집이 남은 탭에 점을 찍는다(탭 목록 개선안 C). 원본이 바뀌어 편집표를 비운
# **뒤**에 정해야 비워진 편집에 점이 남지 않는다. 설비대수는 안쪽 탭(보유·대여·가용)에도 찍는다.
_pending_editors = {key for key in editor_keys if editor_has_edits(key)}
mark_pending_tabs(
    TAB_KEY,
    TAB_NAMES,
    {
        label
        for label, keys in (
            (TAB_NAMES[0], {EDITOR_UPEH}),
            (TAB_NAMES[1], {editor_key for _, _, _, editor_key in EQUIPMENT_EDITORS}),
            (TAB_NAMES[2], {EDITOR_RUN_RATE}),
            (TAB_NAMES[3], {EDITOR_VITAL}),
            (TAB_NAMES[4], {EDITOR_RUN_DAY}),
            (TAB_NAMES[5], {EDITOR_LOT_RATIO}),
            (TAB_NAMES[6], {EDITOR_WF_RATIO}),
        )
        if keys & _pending_editors
    },
)
mark_pending_tabs(
    EQUIPMENT_TAB_KEY,
    EQUIPMENT_TAB_NAMES,
    {
        label
        for label, (_, _, _, editor_key) in zip(
            EQUIPMENT_TAB_NAMES[:3], EQUIPMENT_EDITORS, strict=True
        )
        if editor_key in _pending_editors
    },
)

# 설비대수 세 표는 편집 왕복과 조회 표가 같은 슬라이스를 본다. 창을 갈라 두면
# `apply_month_updates` 가 화면에 없던 월을 지운다.
equipment_month_tables = {
    table_name: scenario_month_table(
        active_scenario,
        table_name,
        effective_start_month,
        effective_end_month,
    )
    for table_name in ("RQ_EQP_OWN", "RQ_EQP_LENT", "RQ_EQP_AVBL")
}
available_equipment_table = build_equipment_count_table(
    equipment_month_tables["RQ_EQP_OWN"],
    equipment_month_tables["RQ_EQP_LENT"],
    equipment_month_tables["RQ_EQP_AVBL"],
    detailed=False,
)
detailed_equipment_table = build_equipment_count_table(
    equipment_month_tables["RQ_EQP_OWN"],
    equipment_month_tables["RQ_EQP_LENT"],
    equipment_month_tables["RQ_EQP_AVBL"],
    detailed=True,
)
# 표시순서 스코프 문자열은 DB 공용 프로필의 행 키다. 페이지 이름이 바뀌어도 **이 두 인자는
# 그대로 둔다** — 안 맞으면 예외가 아니라 정렬이 조용히 사라진다.
available_equipment_table = apply_display_order(
    available_equipment_table,
    display_order,
    PAGE_REFERENCE,
    TAB_EQUIPMENT_COUNT,
)
detailed_equipment_table = apply_display_order(
    detailed_equipment_table,
    display_order,
    PAGE_REFERENCE,
    TAB_EQUIPMENT_COUNT,
)
equipment_edit_tables = {
    table_name: equipment_count_to_edit_table(
        equipment_month_tables[table_name], category, value_column
    )
    for table_name, category, value_column, _ in EQUIPMENT_EDITORS
}


def _close_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


def _open_dialog(name: str) -> None:
    st.session_state[DIALOG_KEY] = name


@st.dialog("STEP 추가·삭제", width="large", on_dismiss=_close_dialog)
def _step_dialog() -> None:
    """고른 경로 STEP 을 복제하거나 지운다. 조회기간의 모든 연결 수요에 함께 반영한다."""
    # STEP 을 더하거나 빼면 UPEH·측정률 표의 행이 바뀌어 그 표의 적용하지 않은 편집이 버려진다.
    dropped_edits = [
        name
        for key, name in (
            (EDITOR_UPEH, "UPEH"),
            (EDITOR_LOT_RATIO, "Lot측정률"),
            (EDITOR_WF_RATIO, "WF측정률"),
        )
        if editor_has_edits(key)
    ]
    if dropped_edits:
        st.warning(
            f"{'·'.join(dropped_edits)} 표에 적용하지 않은 편집이 있습니다. STEP 을 바꾸면 "
            "버려집니다 — 먼저 그 표의 「변경사항 적용」을 누르세요."
        )
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
    # 몇 개의 수요 변형이 함께 바뀌는지는 누르기 전에 보여야 하는 상태다.
    st.caption(
        f"함께 처리하는 수요 변형(Capa Code·Customer·CS) "
        f"{int(selected_route_row['수요 변형 수']):,}개"
    )

    with st.form("capacity_step_change_form", border=False):
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

    if not step_submitted:
        return
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
        return
    months_label = ", ".join(str(month) for month in step_result.affected_months)
    st.session_state["capacity_step_flash"] = (
        f"STEP을 {action_label}했습니다. 적용월 {months_label} · "
        f"수요 변형 {step_result.affected_variants:,}개 · "
        f"RQ_REQB {step_result.affected_reqb_rows:,}행"
    )
    # STEP 을 더하거나 빼면 UPEH·측정률 두 표의 행이 바뀐다 — 그 편집표와 STEP 선택만 비운다.
    mark_own_change(
        OWN_CHANGE_KEY,
        (EDITOR_UPEH, EDITOR_LOT_RATIO, EDITOR_WF_RATIO, *step_widget_keys),
    )
    _close_dialog()
    st.rerun()


with step_tab:
    if step_catalog.empty:
        st.info(
            "선택한 조회기간에 편집할 공정 경로 STEP이 없습니다. "
            "사이드바에서 조회기간을 넓혀 보세요."
        )
    else:
        # 작업 줄은 표 위다. 추가·삭제는 가끔 하는 쓰기라 팝업으로 연다.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.button(
                "STEP 추가·삭제",
                icon=":material/edit_road:",
                key="open_capacity_step_dialog",
                type="primary",
                on_click=_open_dialog,
                args=(STEP_DIALOG,),
            )
    flash_message = st.session_state.pop("capacity_step_flash", None)
    if isinstance(flash_message, str):
        st.success(flash_message)
    # 요약 표는 그림이라 숨은 탭에서는 건너뛴다.
    if not tab_is_hidden(step_tab):
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

    if not step_catalog.empty and st.session_state.get(DIALOG_KEY) == STEP_DIALOG:
        _step_dialog()

with equipment_tab:
    # 세 RQ 를 한 탭에 세로로 쌓으면 편집표 하나가 500px 라 화면이 세 배로 길어진다.
    # 다른 기준정보 탭과 **같은 편집기**를 쓰되 탭을 한 겹 더 둔다. `현황` 은 세 RQ 를
    # 합친 조회 표라 편집 대상이 아니다 — 보유·대여를 합친 값에 숫자를 쓸 자리가 없다.
    (
        equipment_own_tab,
        equipment_lent_tab,
        equipment_available_tab,
        equipment_overview_tab,
    ) = stateful_tabs(EQUIPMENT_TAB_NAMES, key=EQUIPMENT_TAB_KEY)

# `현황` 은 보는 표다. 「상세」와 필터는 사이드바 `표 조건` 카드이고, 바깥·안쪽 탭이 **둘 다**
# 열렸을 때만 선다 — 안쪽 탭은 바깥이 닫혀 있어도 자기 선택만 알기 때문이다. 선택은
# `persist_state` 로 남는다.
if not (tab_is_hidden(equipment_tab) or tab_is_hidden(equipment_overview_tab)):
    with table_card(CARD_NAME):
        show_equipment_detail = st.toggle(
            "상세",
            key="equipment_count_detail",
            persist_state="session",
        )
        if show_equipment_detail:
            equipment_table = detailed_equipment_table.copy()
            equipment_dimensions = DETAILED_EQUIPMENT_DIMENSIONS
        else:
            equipment_table = available_equipment_table.copy()
            equipment_dimensions = EQUIPMENT_DIMENSIONS
        equipment_table = render_column_filter_controls(
            equipment_table,
            equipment_dimensions,
            key_prefix="equipment_count_filter",
            value_labels=process_labels.value_labels(),
        )
    with equipment_overview_tab:
        equipment_month_columns = [
            column for column in equipment_table.columns if column not in equipment_dimensions
        ]
        displayed_equipment_table = equipment_table.copy()
        displayed_equipment_table[equipment_month_columns] = displayed_equipment_table[
            equipment_month_columns
        ].mask(displayed_equipment_table[equipment_month_columns].eq(0))
        # 필터를 먼저 걸고 그 뒤에 표시명을 입힌다. 순서가 바뀌면 위 `isin` 이 원본 컬럼과
        # 맞지 않는다. 같은 탭의 왕복 양식은 `equipment_edit_tables` 라는 별도 프레임이라
        # 이 복사본이 붙여넣기 경로에 닿지 않는다.
        displayed_equipment_table["공정"] = process_labels.series(displayed_equipment_table["공정"])
        st.dataframe(
            classification_styled(displayed_equipment_table, equipment_dimensions),
            hide_index=True,
            width="content",
            height=500,
            row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
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


# 붙여넣기로 비운 칸이 어떻게 되는지는 **표마다 다르다**(2026-09-29 버그 보고 횡전개). 전에는
# 모든 표에 「계산에서 빠집니다」라고 적었는데 그것은 UPEH(경로가 빠진다)에서만 사실이다.
REMOVED_DROPS = "값이 지워진 칸 {count:,}개는 계산에서 빠집니다. "
# 측정률은 행이 없으면 1.0 으로 가정한다(`unit_capacity._join_reference`).
REMOVED_RATIO = "값이 지워진 칸 {count:,}개는 측정률 1.0 으로 계산합니다. "
# 효율·여유율·일수는 UPEH 경로가 쓰는 칸을 비우면 적용이 막힌다(`cleared_keys_in_use`). 적용까지
# 온 빈칸은 쓰는 경로가 없는 칸뿐이다.
REMOVED_UNUSED = (
    "값이 지워진 칸 {count:,}개는 행을 지웠습니다 — 쓰는 UPEH 경로가 없어 계산은 그대로입니다. "
)
# 설비대수는 빈칸을 0 대로 저장한다(`equipment_count_from_edit_table`).
REMOVED_EQUIPMENT = "빈칸 {count:,}개는 0 대로 저장했습니다. "


# `eq=False` — 표(DataFrame)를 품어 값 비교가 뜻이 없다. 같은 편집표인지는 객체로 가른다.
@dataclass(frozen=True, eq=False)
class _Editor:
    """편집표 하나의 적용 규칙. 격자 적용과 팝업 붙여넣기가 같은 규칙을 탄다.

    `removed_notice` 는 붙여넣기로 비운 칸을 알리는 문구(`{count}` 자리)다. `blank_is_zero` 인
    표(설비대수)는 양식의 0 이 「원래 없던 조합」이라, 0 인 칸을 비운 것은 바뀐 것이 없어 세지
    않는다.
    """

    table_name: str
    editor_key: str
    tab: OpenTab
    dimensions: list[str]
    template: pd.DataFrame
    to_rows: Callable[[pd.DataFrame], pd.DataFrame]
    removed_notice: str = REMOVED_DROPS
    blank_is_zero: bool = False


def _edit_flash(
    editor_key: str,
    table_name: str,
    *,
    imported: bool,
    removed: int = 0,
    removed_notice: str = REMOVED_DROPS,
) -> tuple[str, str]:
    """적용 결과를 **누른 자리** 바로 아래에 남긴다.

    버튼으로 고친 경우에는 화면이 그대로 다시 그려질 뿐이라, 눌렸는지 어디에 반영됐는지
    알 길이 없었다. 두 길을 가르는 것은 앞부분 한 마디뿐이고, 저장까지 가야 리비전으로
    남는다는 사실은 양쪽 모두 같다.

    **자리는 하나다.** 표 위 `변경사항 적용` 도, 팝업 붙여넣기도 결과는 작업 줄 바로 아래
    (`f"{editor_key}_apply"` — `render_month_editor` 가 꺼낸다)다. 붙여넣기 팝업은 적용하면
    닫히므로 그 결과(「지워진 칸」 경고 포함)도 작업 줄 아래에서 본다.

    **`editor_key` 는 편집기를 그릴 때 쓴 값 그대로여야 한다.** 여기에 리터럴을 다시 적으면
    쓰는 키와 읽는 키가 갈라져 문구가 조용히 사라진다 — 실제로 `capa_` 접두어가 빠져 여섯
    탭이 그랬다.
    """
    origin = "붙여넣기 데이터를" if imported else "편집값을"
    # 지워진 칸은 대개 **오류가 아니라 정당한 편집**이다(효율·여유율·일수에서 UPEH 경로가 쓰는
    # 칸은 적용 전에 막힌다). 다만 붙여넣기는 격자와 달리 적용 전에 변경 수를 보여 주지 않아, 한
    # 열이 통째로 비어 와도 조용히 지나간다. 그래서 그 칸이 무엇이 됐는지를 표마다 맞는 말로
    # 알린다 — UPEH 는 경로가 빠져 부하량을 그대로 둔 채 대당 Capa 만 잃는다.
    removal = ""
    if removed:
        removal = removed_notice.format(count=removed)
    return (
        f"{editor_key}_apply",
        f"{table_name} {origin} 활성 시나리오에 적용했습니다. "
        f"{removal}"
        "리비전으로 남기려면 사이드바 「저장」 → 「신규 리비전 저장」을 누르세요.",
    )


def _removed_values(editor: _Editor, imported_table: pd.DataFrame | None) -> int:
    """붙여넣기로 비워진 칸 수. 격자 편집은 이미 적용 전에 변경 수를 보여 준다."""
    if imported_table is None:
        return 0
    template = editor.template
    if editor.blank_is_zero:
        # 양식의 0 은 원래 없던 조합이다. 비워 붙여도 0 대로 저장돼 바뀐 것이 없다.
        month_columns = [column for column in template.columns if column not in editor.dimensions]
        template = template.copy()
        template[month_columns] = template[month_columns].mask(template[month_columns].eq(0))
    return count_removed_values(template, imported_table, editor.dimensions)


def _upeh_rows(table: pd.DataFrame) -> pd.DataFrame:
    """UPEH 의 적용 행. 새로 만든 경로의 결손 검사는 `validate_upeh_edit` 가 한다."""
    # 원본(편집표를 만든 같은 기간의 시나리오 `RQ_UPEH`)을 넘겨 **고치지 않은 것은 원본 그대로**
    # 돌려받는다 — Main 행의 ST·MI 행의 UPEH, 값이 빈 실재 행, `Area_Name` 표기(2026-09-29).
    rows = performance_from_edit_table(table, filtered_upeh)
    validate_upeh_edit(filtered_upeh, rows, active_scenario["tables"])
    return rows


def _required_rows(
    table_name: str,
    label: str,
    dimensions: list[str],
    value_column: str,
    source: pd.DataFrame,
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """효율·여유율·일수의 적용 행. **UPEH 경로가 쓰는 칸을 비우거나 0 이하로 하면 막는다.**

    막는 규칙은 `validate_required_edit` 에 있다. `source` 는 편집표를 만든 같은 기간의 원본이다.
    격자 적용과 붙여넣기가 모두 이 함수를 지난다.
    """

    def to_rows(table: pd.DataFrame) -> pd.DataFrame:
        rows = reference_from_edit_table(table, dimensions, value_column, f"{label} 편집값")
        upeh = active_scenario["tables"]["RQ_UPEH"]
        validate_required_edit(table_name, label, source, rows, value_column, upeh)
        return rows

    return to_rows


def _apply_edit(editor: _Editor, source: pd.DataFrame, *, imported: bool) -> None:
    """편집값 또는 붙여넣은 표를 활성 시나리오에 적용하고 완료 알림을 남긴다.

    막히면 `KeyError`/`ValueError` 를 던진다. 적용이 끝나면 `mark_own_change` 로 다음 회차에 **이
    표만** 새 원본으로 다시 선다(다른 탭의 적용하지 않은 편집은 남는다). rerun 은 부르는 쪽이 한다.
    """
    rows = editor.to_rows(source)
    flash = _edit_flash(
        editor.editor_key,
        editor.table_name,
        imported=imported,
        removed=_removed_values(editor, source if imported else None),
        removed_notice=editor.removed_notice,
    )
    apply_month_updates(
        active_scenario,
        {editor.table_name: rows},
        effective_start_month,
        effective_end_month,
    )
    queue_reference_import_flash(*flash)
    # 적용한 이 표만 새 원본으로 다시 세운다. 다른 탭의 적용하지 않은 편집은 그대로 둔다.
    # STEP 팝업의 선택도 비운다 — 경로 선택은 목록의 순번이라, UPEH 한 행을 비우면 경로가 빠져
    # 뒤 순번이 당겨지고 다음에 열 때 다른 경로가 골라져 있다(2026-09-29 2차 리뷰).
    mark_own_change(OWN_CHANGE_KEY, (editor.editor_key, *step_widget_keys))


def _paste_into(editor: _Editor) -> Callable[[pd.DataFrame], None]:
    def paste(table: pd.DataFrame) -> None:
        _apply_edit(editor, table, imported=True)

    return paste


EDITORS = (
    _Editor(
        "RQ_UPEH",
        EDITOR_UPEH,
        upeh_tab,
        PERFORMANCE_EDITOR_DIMENSIONS,
        default_upeh_table,
        _upeh_rows,
    ),
    _Editor(
        "RQ_RUN_RATE",
        EDITOR_RUN_RATE,
        run_rate_tab,
        RUN_RATE_DIMENSIONS,
        default_run_rate_table,
        _required_rows(
            "RQ_RUN_RATE", "효율", RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", filtered_run_rate
        ),
        REMOVED_UNUSED,
    ),
    _Editor(
        "RQ_VITAL",
        EDITOR_VITAL,
        vital_tab,
        VITAL_DIMENSIONS,
        default_vital_table,
        _required_rows("RQ_VITAL", "여유율", VITAL_DIMENSIONS, "편중률", filtered_vital),
        REMOVED_UNUSED,
    ),
    _Editor(
        "RQ_LOT_RATIO",
        EDITOR_LOT_RATIO,
        lot_ratio_tab,
        RATIO_DIMENSIONS,
        default_lot_ratio_table,
        lambda table: reference_from_edit_table(
            table, RATIO_DIMENSIONS, "Lot 측정률", "Lot측정률 편집값"
        ),
        REMOVED_RATIO,
    ),
    _Editor(
        "RQ_WF_RATIO",
        EDITOR_WF_RATIO,
        wf_ratio_tab,
        RATIO_DIMENSIONS,
        default_wf_ratio_table,
        lambda table: reference_from_edit_table(
            table, RATIO_DIMENSIONS, "WF측정률", "WF측정률 편집값"
        ),
        REMOVED_RATIO,
    ),
    _Editor(
        "RQ_RUN_DAY",
        EDITOR_RUN_DAY,
        run_day_tab,
        RUN_DAY_DIMENSIONS,
        default_run_day_table,
        _required_rows("RQ_RUN_DAY", "일수", RUN_DAY_DIMENSIONS, "RUN_DAY", filtered_run_day),
        REMOVED_UNUSED,
    ),
)


def _equipment_rows(category: str, value_column: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def to_rows(table: pd.DataFrame) -> pd.DataFrame:
        return equipment_count_from_edit_table(table, category, value_column)

    return to_rows


# 설비대수도 다른 기준정보와 **같은 편집기**를 쓴다. 값붙여넣기만 되던 화면이라 한 칸을
# 고치려면 표 전체를 Excel 로 왕복해야 했다.
EQUIPMENT_EDITOR_SPECS = tuple(
    _Editor(
        table_name,
        editor_key,
        equipment_sub_tab,
        EQUIPMENT_DIMENSIONS,
        equipment_edit_tables[table_name],
        _equipment_rows(category, value_column),
        REMOVED_EQUIPMENT,
        blank_is_zero=True,
    )
    for equipment_sub_tab, (table_name, category, value_column, editor_key) in zip(
        (equipment_own_tab, equipment_lent_tab, equipment_available_tab),
        EQUIPMENT_EDITORS,
        strict=True,
    )
)
# 편집기의 값 형식. (숫자 형식, 한 칸 증분, 최댓값)
EDITOR_FORMATS: dict[str, tuple[str, float, float | None]] = {
    "RQ_UPEH": ("%,.2f", 0.01, None),
    "RQ_RUN_RATE": ("percent", 0.001, 1.0),
    "RQ_VITAL": ("percent", 0.001, None),
    "RQ_LOT_RATIO": ("percent", 0.001, 1.0),
    "RQ_WF_RATIO": ("percent", 0.001, 1.0),
    "RQ_RUN_DAY": ("%,.0f", 1.0, None),
    "RQ_EQP_OWN": ("%,.2f", 0.01, None),
    "RQ_EQP_LENT": ("%,.2f", 0.01, None),
    "RQ_EQP_AVBL": ("%,.2f", 0.01, None),
}

# 측정률 표에 이 기간 행이 없으면 편집표가 0 행이다(모든 칸을 비워 적용했거나 원천에 행이 없다).
# 계산은 1.0 으로 이어 가므로 오류가 아니지만, 빈 표만 보이면 무엇으로 계산되는지 알 수 없다.
# 이 편집표는 행을 더할 수 없다(원래 한계) — 무엇이 계산되는지만 알린다(2026-09-29 2차 리뷰).
RATIO_EMPTY_NOTICE = (
    "이 기간에 {label} 행이 없어 모든 경로를 측정률 1.0 으로 계산합니다. 이 표에서는 행을 더할 수 "
    "없습니다."
)
for ratio_tab, ratio_rows, ratio_label in (
    (lot_ratio_tab, filtered_lot_ratio, "Lot측정률"),
    (wf_ratio_tab, filtered_wf_ratio, "WF측정률"),
):
    if ratio_rows.empty and not tab_is_hidden(ratio_tab):
        with ratio_tab:
            st.info(RATIO_EMPTY_NOTICE.format(label=ratio_label))

editor_results: list[tuple[_Editor, pd.DataFrame, bool]] = []
for editor in (*EDITORS, *EQUIPMENT_EDITOR_SPECS):
    number_format, step, max_value = EDITOR_FORMATS[editor.table_name]
    is_equipment = editor in EQUIPMENT_EDITOR_SPECS
    edited_table, applied = render_month_editor(
        editor.tab,
        editor.template,
        editor.dimensions,
        editor.editor_key,
        number_format,
        step,
        max_value=max_value,
        table_name=editor.table_name,
        csv_file_name=f"{editor.table_name}_{effective_start_month}_{effective_end_month}.csv",
        dialog_key=DIALOG_KEY,
        on_paste=_paste_into(editor),
        card_name=CARD_NAME,
        # 필터 옵션 표기만 다른 화면과 맞춘다. 선택값·편집표·왕복 CSV 는 원본 공정명이다.
        value_labels=process_labels.value_labels(),
        outer_tab=equipment_tab if is_equipment else None,
    )
    editor_results.append((editor, edited_table, applied))

for editor, edited_table, applied in editor_results:
    if not applied:
        continue
    try:
        _apply_edit(editor, edited_table, imported=False)
    except (KeyError, ValueError) as exc:
        # 표 위 `변경사항 적용` 에서 난 오류는 그 버튼 바로 아래 자리에 쓴다.
        notice = editor_notice(editor.editor_key)
        if notice is not None:
            notice.error(str(exc))
        else:
            with editor.tab:
                st.error(str(exc))
        st.stop()
    st.rerun()
