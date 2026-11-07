# Purpose: Capa 산출에 쓰는 입력값과 STEP 구성을 월별로 편집한다.

"""기준 정보 — 조건 카드·Guide·작업 줄 양식(2026-09-29 사용자 결정, 생산 계획이 샘플).

- **탭 대신 종류 단추 한 줄 + 큰 편집 표 하나**(2026-11-02 사용자 결정 — 편집 표 횡전개). 단추는
  네이티브 `st.segmented_control`(`reference_grid_keys.DATASET_KEY`)이고 옛 탭·안쪽 탭(설비대수 ›
  보유·대여·가용·현황)을 한 줄로 편 것이다. 고른 편집 표(아홉 모두)를 범용 편집 그리드(마운트 하나
  — `components/reference_grid.py`)에 싣는다. 초안은 표마다 세션(업무 키)이라 다른 종류를 고르거나
  화면을 떠나도 남고, 적용하지 않은 편집이 남은 종류 단추 옆에는 주황 점이 찍힌다.
- 읽기 보기 둘(「설비대수 현황」·「STEP 구성」)은 그리드 자리 **아래** 보기 칸에 그 종류를 골랐을
  때만 그린다 — 그 회차에도 그리드 마운트는 표 없이 같은 자리에 남는다.
- 표 필터와 설비대수 현황의 「상세」는 사이드바 조건 카드 `표 조건` 이다. 모든 종류가 같은 카드를
  써서 한 번 편 카드는 종류를 바꿔도 편 채다. 그리드 표의 필터는 보기만 좁히고(브라우저가 거른다)
  초안이 업무 키라 잠그지 않는다.
- 작업 버튼(변경사항 적용·Excel 붙여넣기·편집 취소, STEP 추가·삭제)은 표 **위**다. 붙여넣기와
  STEP 추가·삭제는 팝업이다.
- 설명은 Guide(`guides/reference_data.md`)다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components import reference_grid
from capa_simulation.components.column_filter import render_column_filter_controls
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.month_editor import classification_styled, paste_dialog
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.reference_csv_tools import queue_reference_import_flash
from capa_simulation.components.scenario_edit_bar import (
    mark_own_change,
    only_revision_changed,
    pending_edit_labels,
    register_pending_edits,
    reset_editors_on_source_change,
    source_token,
)
from capa_simulation.components.tab_marks import mark_pending_segments
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    load_page_context,
    prune_choice,
    resolve_effective_months,
)
from capa_simulation.reference_grid_keys import (
    DATASET_KEY,
    DATASETS,
    DEFAULT_DATASET,
    EDIT_TABLES,
    EQUIPMENT_OVERVIEW,
    STEP_VIEW,
    TEMPLATE_DIGESTS_KEY,
    cells_key,
    history_key,
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
    STEP_PAIR_COLUMNS,
    clone_route_step,
    delete_route_step,
)
from capa_simulation.services.simulation_cache import (
    display_order_digest,
    frame_digest,
    get_reference_edit_table,
    get_route_step_tables,
    scenario_cache_key,
)
from capa_simulation.sidebar_status import table_card

# Capa 산출에 **넣는 값만** 둔다. 산출물은 `산출 결과` 페이지가 갖는다.
# 종류 단추의 차례·글은 `reference_grid_keys.DATASETS` 다(옛 탭 차례 — 사용자가 정한 입력 순서).
# 조건 카드 이름(사이드바 `표 조건`). 모든 종류가 하나를 쓴다.
CARD_NAME = "reference_data"
# 지금 열린 팝업: 편집 표 key(붙여넣기) 또는 `STEP_DIALOG`. 한 칸이라 한 회차에 팝업은 하나다.
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
# 행이 없으면 1.0 으로 가정하는 표 — 통째로 비어도 화면을 세우지 않는다(`_ratio_month_table`).
RATIO_TABLES = ("RQ_LOT_RATIO", "RQ_WF_RATIO")
# STEP 을 더하거나 빼면 행이 바뀌는 표 — 그 표의 적용하지 않은 편집은 버린다(팝업이 먼저 말한다).
STEP_ROUTE_EDIT_TABLES = ("RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO")
# 기준정보 표(설비대수 셋 밖)의 편집 양식 — (분류 컬럼, 값 컬럼, 표시순서 범위). 양식은
# `get_reference_edit_table` 이 편집 기간·표시순서 내용으로 캐시한다. UPEH 는 값 컬럼 둘(UPEH·ST)을
# Main/MI 행으로 한 칸에 모은다(`value_column=None`).
TABLE_SOURCES: dict[str, tuple[list[str], str | None, str]] = {
    "RQ_UPEH": (PERFORMANCE_EDITOR_DIMENSIONS, None, TAB_UPEH),
    "RQ_RUN_RATE": (RUN_RATE_DIMENSIONS, "CAPA_RUN_RATE", TAB_RUN_RATE),
    "RQ_VITAL": (VITAL_DIMENSIONS, "편중률", TAB_VITAL),
    "RQ_RUN_DAY": (RUN_DAY_DIMENSIONS, "RUN_DAY", TAB_RUN_DAY),
    "RQ_LOT_RATIO": (RATIO_DIMENSIONS, "Lot 측정률", TAB_LOT_RATIO),
    "RQ_WF_RATIO": (RATIO_DIMENSIONS, "WF측정률", TAB_WF_RATIO),
}
# 편집 표 → 편집 표 key(작업 줄 단추·알림 자리·필터·붙여넣기 칸의 key 앞머리). 사이드바 필터 선택·
# 따라하기 가이드·화면 확인 스크립트가 같은 key 를 쓴다.
EDITOR_KEYS: dict[str, str] = {
    "RQ_UPEH": EDITOR_UPEH,
    "RQ_RUN_RATE": EDITOR_RUN_RATE,
    "RQ_VITAL": EDITOR_VITAL,
    "RQ_RUN_DAY": EDITOR_RUN_DAY,
    "RQ_LOT_RATIO": EDITOR_LOT_RATIO,
    "RQ_WF_RATIO": EDITOR_WF_RATIO,
    **{table_name: editor_key for table_name, _, _, editor_key in EQUIPMENT_EDITORS},
}
assert set(EDITOR_KEYS) == set(EDIT_TABLES)
# 편집 표 이름 — 사이드바 「적용 전 편집」 목록·고칠 칸 알림·STEP 팝업 경고가 같은 이름을 쓴다
# (종류 단추 글). 값 칸의 표시·다듬기 규칙(형식·하한·상한·정수·빈칸 = 0)은
# `reference_grid.GRID_FORMATS` 다 — UPEH 는 유효숫자 여섯 자리(MI 행 값은 ST(분)라 0.01 보다 작은
# 값이 정의대로 들어온다).
TABLE_NAMES = {table_name: DATASETS[table_name] for table_name in EDIT_TABLES}
# 월 칸 머리의 도움말 — 한 칸에 행마다 다른 값이 들어가는 표만 그 뜻·단위를 밝힌다.
EDITOR_VALUE_HELP: dict[str, str] = {
    "RQ_UPEH": "Main 행은 UPEH(시간당 처리량), MI 행은 ST(분) — 한 개를 처리하는 데 드는 분입니다.",
}
render_page_header("기준 정보")
render_page_guide("reference_data", title="기준 정보")
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()


def _dataset_label(dataset: str) -> str:
    return DATASETS.get(dataset, dataset)


# 고른 종류는 세션에 남는다(`persist_state="session"`) — 사이드바 「불러오기」 의 `st.rerun()` 이
# 페이지 본문을 건너뛴 회차나 다른 화면에 다녀온 뒤에도 보던 표로 돌아온다. 처음(또는 목록 밖
# 값)에는 UPEH 를 세션에 심는다 — 위젯에 `default=` 를 주지 않아 세션 값과 기본값이 겹치지 않는다.
if st.session_state.get(DATASET_KEY) not in DATASETS:
    st.session_state[DATASET_KEY] = DEFAULT_DATASET
_chosen = st.segmented_control(
    "기준 정보 종류",
    list(DATASETS),
    format_func=_dataset_label,
    key=DATASET_KEY,
    required=True,
    persist_state="session",
    label_visibility="collapsed",
)
current_dataset = _chosen if isinstance(_chosen, str) and _chosen in DATASETS else DEFAULT_DATASET
# 작업 줄 → 그리드 자리 → 읽기 보기 칸. 모두 **늘 서 있는 칸**이라 안의 칸 수가 바뀌어도 아래 자리
# (그리드 마운트의 앞 형제 순번)가 밀리지 않는다 — 밀리면 그리드가 다시 마운트되어 보내지 않은
# 출납을 잃는다. 읽기 보기(설비대수 현황·STEP 구성)는 그리드 **아래**라 그 높이가 그리드 자리를
# 밀지 않는다. 편집 표를 고른 회차에는 보기 칸이 비어 표 아래에 아무것도 없다(명세 1-2 의 19 — 표
# 아래 단추에 초점이 가면 본문이 내려가 머리와 도구 막대가 탭 줄 밑으로 숨는다).
actions_box = st.container(key="reference_actions")
grid_box = st.container(key="reference_grid_box")
view_box = st.container(key="reference_view")


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


class _EditSlices:
    """이 회차 적용 기간 조각 — **쓰는 순간에만** 자르고, 같은 회차 안에서는 다시 쓴다.

    편집 표는 고르지 않았거나 캐시가 적중하면 조각을 읽지 않고, STEP 경로표는 그 종류에서만 쓴다.
    이 화면이 쓰지 않는 RQ_PKG_PLAN·RQ_YLD 는 자르지 않는다. 조각은 만든 회차의 활성 시나리오·적용
    기간에 묶인다 — 팝업(fragment) 재실행도 그 회차 객체를 쓴다. 측정률 두 표는
    `_ratio_month_table` 특례(통째로 빈 표)를 지킨다.
    """

    def __init__(self, scenario: ActiveScenario, start_month: int, end_month: int) -> None:
        self._scenario = scenario
        self._start_month = start_month
        self._end_month = end_month
        self._memo: dict[str, pd.DataFrame] = {}

    def get(self, table_name: str) -> pd.DataFrame:
        """조각. 자르다 난 오류(월 형식·빈 표)는 그대로 던진다 — 페이지 앞 `try` 안에서 부른다."""
        if table_name not in self._memo:
            slicer = _ratio_month_table if table_name in RATIO_TABLES else scenario_month_table
            self._memo[table_name] = slicer(
                self._scenario, table_name, self._start_month, self._end_month
            )
        return self._memo[table_name]

    def loader(self, table_name: str) -> Callable[[], pd.DataFrame]:
        """캐시 래퍼에 넘기는 조각 — 캐시가 빗나갈 때만 자른다."""
        return lambda: self.get(table_name)

    def get_or_stop(self, table_name: str) -> pd.DataFrame:
        """페이지 앞 `try` 밖(적용·붙여넣기·STEP 제출·안내)에서 부르는 조각. 오류는 그 `try` 와 같은
        문구로 멈춘다 — 잡지 않으면 친절한 오류 대신 traceback 이 뜬다."""
        try:
            return self.get(table_name)
        except BOOTSTRAP_ERRORS as exc:
            render_data_error(bootstrap_error_message(exc), code="ST-20")
            st.stop()


def _source_template(table_name: str) -> pd.DataFrame:
    """편집 표 하나의 양식(분류 컬럼 + 월 컬럼, 표시순서 차례). 자르다 난 오류는 그대로 던진다.

    설비대수 세 표는 `equipment_count_to_edit_table` 로 펴서 표시순서(기준 정보 › 설비대수)를
    입힌다 — 편집 왕복과 `현황` 표가 같은 조각을 본다(창을 갈라 두면 `apply_month_updates` 가
    화면에 없던 월을
    지운다). 나머지는 `get_reference_edit_table` 이 편집 기간·표시순서 내용으로 캐시한다(rerun 마다
    다시 만들면 UPEH 2,660×39 에서 약 320ms — 샘플 관측)."""
    for equipment_table, category, count_column, _ in EQUIPMENT_EDITORS:
        if table_name == equipment_table:
            return apply_display_order(
                equipment_count_to_edit_table(edit_slices.get(table_name), category, count_column),
                display_order,
                PAGE_REFERENCE,
                TAB_EQUIPMENT_COUNT,
            )
    dimensions, value_column, scope_tab = TABLE_SOURCES[table_name]
    return get_reference_edit_table(
        edit_cache_key,
        edit_display_order_key,
        table_name=table_name,
        dimensions=tuple(dimensions),
        value_column=value_column,
        page=PAGE_REFERENCE,
        tab=scope_tab,
        _data=edit_slices.loader(table_name),
        _display_order=display_order,
    )


try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    display_order = context.display_order
    active_scenario = context.active_scenario
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
    # 조각은 쓰는 자리에서만 자른다(`_EditSlices`).
    edit_slices = _EditSlices(active_scenario, effective_start_month, effective_end_month)
    edit_cache_key = scenario_cache_key(
        reference_version, active_scenario, effective_start_month, effective_end_month
    )
    edit_display_order_key = display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])
    # STEP 구성의 요약·목록. 쓰는 곳은 그 보기와 STEP 팝업(경로 선택 상자는 팝업 안이다) 뿐이라,
    # **그 종류를 골랐거나 팝업이 열린 회차에만** 만든다. 다른 종류에서도 만들면 적용마다(새 토큰)
    # 경로표 전체를 다시 계산하고, 적중해도 RQ_REQB 를 회차마다 자르게 된다. 만들 때는 이 회차 활성
    # 시나리오·적용 기간 조각(캐시가 빗나갈 때만 자른다)을 내용 토큰으로 캐시한다. 월 형식 오류는
    # 여기 try 가 받는다 — 밖으로 옮기면 친절한 오류 대신 traceback 이 뜬다.
    step_tables: tuple[pd.DataFrame, pd.DataFrame] | None = None
    if current_dataset == STEP_VIEW or st.session_state.get(DIALOG_KEY) == STEP_DIALOG:
        step_tables = get_route_step_tables(
            edit_cache_key,
            _upeh=edit_slices.loader("RQ_UPEH"),
            _reqb=edit_slices.loader("RQ_REQB"),
        )
except BOOTSTRAP_ERRORS as exc:
    render_data_error(bootstrap_error_message(exc), code="ST-20")
    st.stop()


# 그리드 표의 초안·이력 세션 칸 — 업무 키라 줄 차례만 바뀐 회차에도 남는다(`order_free_keys`).
grid_session_keys = tuple(
    key for table_name in EDIT_TABLES for key in (cells_key(table_name), history_key(table_name))
)
# STEP 복제·삭제 대상 상자. 값은 경로 키다(`_step_route_choices`).
STEP_ROUTE_KEY = "capacity_step_route"
step_widget_keys = (
    "capacity_step_mode",
    STEP_ROUTE_KEY,
    "capacity_step_new_mcp",
    "capacity_step_new_step",
    "capacity_step_delete_confirm",
)
SOURCE_TOKEN_KEY = "reference_data_source_token"
# 이 화면이 스스로 적용한 편집(표 하나·STEP). 원본이 바뀌어도 그 적용이 건드린 표만 비운다 —
# 다른 표에서 고치고 아직 적용하지 않은 편집은 남는다.
OWN_CHANGE_KEY = "reference_data_own_change"
# 다른 화면의 적용으로 그리드 초안을 버린 회차의 알림(표 이름 · 칸 수).
GRID_DROPPED_NOTICE = (
    "다른 화면의 적용으로 표 내용이 바뀌어 적용하지 않은 편집({tables})을 버렸습니다"
    " — 다시 입력하세요."
)
# 그 알림 칸(작업 줄 맨 위 — `render_flash` 가 늘 세우는 한 칸).
GRID_DROPPED_FLASH_KEY = "reference_grid_dropped_flash"
GRID_DROPPED_ICON = ":material/sync_problem:"


def _template_or_stop(table_name: str) -> pd.DataFrame:
    """페이지 앞 `try` 밖에서 만드는 양식 — 자르다 난 오류는 그 `try` 와 같은 문구로 멈춘다."""
    try:
        return _source_template(table_name)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(bootstrap_error_message(exc), code="ST-20")
        st.stop()


def _template_digest(table_name: str) -> str:
    """그 표 양식(분류 칸 + 월 칸, 줄 차례대로)의 내용 지문."""
    return frame_digest(_template_or_stop(table_name))


def _grid_survivors(previous: object, token: str) -> tuple[set[str], dict[str, int]]:
    """다른 화면의 적용(활성 리비전만 오름)에 남길 그리드 표와 버릴 표(표 → 적용하지 않은 칸 수).

    다른 화면(생산 계획 PKG PLAN·수율 등)의 적용은 원본 토큰의 리비전을 올리지만 이 화면의
    표 대부분은 그대로다. 초안은 업무 키 + 월이라 그 표의 양식 내용이 같으면 같은 칸에 그대로
    붙는다 — 초안이 있는 표마다 지금 양식의 지문을 초안을 둔 때의 지문(`TEMPLATE_DIGESTS_KEY`,
    `_remember_grid_digests`)과 견줘 같으면 남기고, 다르거나 지문이 없으면 버리고 알린다
    (2026-11-03 리뷰 — 전에는 어느 화면의 적용이든 아홉 표 초안을 말없이 모두 버렸다). 이 화면
    자신의 적용(`OWN_CHANGE_KEY`)·시나리오·기간·줄 차례가 바뀐 회차는
    `reset_editors_on_source_change` 가 지금처럼 가른다.
    """
    if st.session_state.get(OWN_CHANGE_KEY) is not None or not only_revision_changed(
        previous, token
    ):
        return set(), {}
    digests = st.session_state.get(TEMPLATE_DIGESTS_KEY)
    saved = digests if isinstance(digests, dict) else {}
    kept: set[str] = set()
    dropped: dict[str, int] = {}
    for table_name in EDIT_TABLES:
        cells = reference_grid.draft_counts(table_name)[0]
        if not cells:
            continue
        before = saved.get(table_name)
        if isinstance(before, tuple) and before[1] == _template_digest(table_name):
            kept.add(table_name)
        else:
            dropped[table_name] = cells
    return kept, dropped


def _remember_grid_digests() -> None:
    """초안이 있는 표의 양식 지문을 적어 둔다(`_grid_survivors` 가 다음에 견줄 값). 양식 키
    (내용 토큰·기간·줄 차례)가 그대로면 다시 재지 않는다 — 적용·리비전이 바뀐 회차에만 초안이
    있는 표를 잰다."""
    stamp = f"{edit_cache_key}|{edit_display_order_key}"
    digests = st.session_state.get(TEMPLATE_DIGESTS_KEY)
    saved = dict(digests) if isinstance(digests, dict) else {}
    for table_name in EDIT_TABLES:
        if not reference_grid.draft_counts(table_name)[0]:
            saved.pop(table_name, None)
            continue
        before = saved.get(table_name)
        if not (isinstance(before, tuple) and before[0] == stamp):
            saved[table_name] = (stamp, _template_digest(table_name))
    if saved != digests:
        st.session_state[TEMPLATE_DIGESTS_KEY] = saved


# 줄 차례 지문은 편집 표 캐시 키와 같은 표시순서 지문이다 — 아홉 표가 모두 이 표시순서로 줄을
# 세운다(설비대수 세 표는 `apply_display_order`). 그리드 초안(업무 키)과 STEP 복제·삭제 상자(경로
# 키)는 차례만 바뀐 회차에 남는다 — 비우고 알리지 않는다.
# 기준정보 버전·기간이 바뀌면 모두 버린다 — 그리드 이력도 함께 지워져 다음 회차의 새 `gen` 이
# 그 전에 보낸 op 를 버린다. 리비전만 바뀐 회차(다른 화면의 적용)에는 내용이 그대로인 표의
# 그리드 초안·이력을 남기고, 바뀐 표만 버리고 작업 줄 칸에 한 번 알린다(`_grid_survivors`).
reference_token = source_token(
    reference_version,
    active_scenario,
    effective_start_month,
    effective_end_month,
    row_order=edit_display_order_key,
)
grid_kept, grid_dropped = _grid_survivors(st.session_state.get(SOURCE_TOKEN_KEY), reference_token)
kept_grid_keys = {
    key for table_name in grid_kept for key in (cells_key(table_name), history_key(table_name))
}
# 앱 머리(칩 · 탭 점 · 사이드바 줄)는 이 본문보다 먼저 이 값으로 그렸다.
edits_in_head = pending_edit_labels("reference_data.py")
reset_editors_on_source_change(
    SOURCE_TOKEN_KEY,
    reference_token,
    (),
    other_keys=(
        *step_widget_keys,
        *(key for key in grid_session_keys if key not in kept_grid_keys),
    ),
    own_change_key=OWN_CHANGE_KEY,
    order_free_keys=(*step_widget_keys, *grid_session_keys),
)
head_is_stale = bool(set(edits_in_head) - set(pending_edit_labels("reference_data.py")))
# 버림 알림은 담아 두기만 한다 — 아래에서 이 회차를 다시 돌리는지(초안을 버리거나 비운 회차) 정해진
# 뒤에 꺼낸다. 먼저 꺼내면 두 회차가 표지를 따로 보내 한 번 일어난 일을 Alarm 이 「×2」 로 센다.
if grid_dropped:
    queue_flash(
        GRID_DROPPED_FLASH_KEY,
        GRID_DROPPED_NOTICE.format(
            tables=" · ".join(
                f"{TABLE_NAMES[table_name]} {cells:,}칸"
                for table_name, cells in grid_dropped.items()
            )
        ),
        kind="warning",
        icon=GRID_DROPPED_ICON,
    )


def _filter_prefix(table_name: str) -> str:
    """사이드바 「표 조건」 필터 key 앞머리 — 표마다 따로라 한 표의 선택이 다른 표에 새지 않는다."""
    return f"{EDITOR_KEYS[table_name]}_filter"


def _grid_table(table_name: str) -> reference_grid.GridTable:
    """그리드 표 하나 — 양식과 그 색인·껍데기 본문(캐시). 큰 표는 사이드바 필터 선택으로 줄을
    고른다."""
    dimensions = (
        EQUIPMENT_DIMENSIONS
        if table_name in {name for name, _, _, _ in EQUIPMENT_EDITORS}
        else TABLE_SOURCES[table_name][0]
    )
    return reference_grid.build_grid_table(
        table_name,
        TABLE_NAMES[table_name],
        EDITOR_KEYS[table_name],
        _template_or_stop(table_name),
        dimensions,
        cache_key=edit_cache_key,
        order_digest=edit_display_order_key,
        value_labels=process_labels.value_labels(),
        value_help=EDITOR_VALUE_HELP.get(table_name),
        filter_prefix=_filter_prefix(table_name),
    )


# 그리드 표는 **고른 표와 inbox 에 op 가 쌓인 표만** 싣는다(양식·색인은 캐시). 원본을 본 **뒤**
# 반영해야 버린 초안에 옛 op 가 붙지 않는다. 지금 고르지 않은 표의 op(표를 바꾸기 직전에 보낸
# 편집)도 그 표 초안에 쓴다.
_inbox_tables = reference_grid.inbox_tables()
grid_tables = {
    table_name: _grid_table(table_name)
    for table_name in EDIT_TABLES
    if table_name == current_dataset or table_name in _inbox_tables
}
if reference_grid.apply_grid_inbox(grid_tables) or head_is_stale:
    # 원본이 바뀌어 초안을 버렸거나, 반영이 어느 표의 초안 칸을 비웠다(Ctrl+Z 로 0칸 · 초안 없던
    # 표의 첫 op 가 아무것도 바꾸지 않음). 사이드바 「적용 전 편집」·화면 탭 점·변경 칩·테마 표지는
    # `app.py` 가 이 본문보다 **먼저** 옛 칸으로 그렸다 — 그대로 두면 다음 조작까지 남는다(그리드는
    # 다시 보내지 않는다). 한 번 다시 돈다(양식·색인은 캐시라 싸고, 다음 회차는 버릴 초안도 inbox
    # 도 없어 되풀이되지 않는다).
    st.rerun()
with actions_box:
    render_flash(GRID_DROPPED_FLASH_KEY)
_remember_grid_digests()
# 사이드바가 저장·불러오기 전에 「적용하지 않은 편집」을 묻도록 이 화면의 편집을 알린다. 그리드
# 초안은 세션 칸이라 어느 화면에서나 센다(화면 탭 점·테마 단추·새로고침 확인이 함께 따라오고, 떠날
# 때는 묻지 않는다). 방금 적용한 표는 사이드바가 빼고 센다(`OWN_CHANGE_KEY`).
register_pending_edits(
    "reference_data.py",
    "기준 정보",
    {},
    drafts={cells_key(table_name): TABLE_NAMES[table_name] for table_name in EDIT_TABLES},
    own_change_key=OWN_CHANGE_KEY,
)

# 적용하지 않은 편집이 남은 종류 단추 옆에 점을 찍는다(탭 목록 개선안 C 를 단추로). 원본이 바뀌어
# 편집을 비운 **뒤**, inbox 를 반영한 **뒤**에 정해야 비워진 편집에 점이 남지 않고 방금 고친 표에
# 점이 선다.
mark_pending_segments(
    DATASET_KEY,
    list(DATASETS),
    {table_name for table_name in EDIT_TABLES if reference_grid.draft_pending(table_name)},
)


def _close_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


def _open_dialog(name: str) -> None:
    st.session_state[DIALOG_KEY] = name


def _step_route_choices(catalog: pd.DataFrame) -> dict[str, str]:
    """STEP 복제·삭제 상자의 선택지 — 경로 키 → 보이는 글자(목록 차례 그대로).

    Streamlit 1.63 selectbox 는 값을 **보이는 글자**로 주고받아, 글자가 같은 줄이 둘이면 마지막
    줄로 돌아온다(2026-10-10 병합 전 리뷰 재현 — 다른 공정에 STEP 이 복사되거나 다른 공정의 STEP
    이 지워졌고, 고르지 않아도 첫 왕복에서 기본값이 다른 줄로 바뀌었다). 그래서 글자에 행의 **진짜
    키**(`ROUTE_GROUP_COLUMNS` 전부 — `양산구분` 포함 — 와 MCP/STEP)를 다 싣는다. 공정은 표시명이
    다른 공정의 원본과 겹치면 「표시명 (원본)」 으로 가르고(`unique_format_func`, 목록의 공정
    전체로), 그래도 같은 글자가 남는 드문 경우(키 값 안에 구분자 「 · 」 가 든 줄 등)는 뒤 줄에
    「 #n」 을 붙인다. 앞뒤 공백만 다른 값은 `_prepare` 가 이미 잘라 한 경로로 합치고, 안쪽 공백만
    다른 값은 글자는 달라도 브라우저가 공백을 하나로 보여 같아 보인다 — 값(경로 키)은 맞으니 쓰기는
    틀리지 않는다. 값은 행 위치가 아니라 경로 키다 — STEP 을 더하거나 빼 목록이 밀려도 다른 줄을
    가리키지 않는다.
    """
    key_columns = [*ROUTE_GROUP_COLUMNS, *STEP_PAIR_COLUMNS]
    process_text = process_labels.unique_format_func(catalog["공정"].astype(str))
    choices: dict[str, str] = {}
    used: set[str] = set()
    for row in catalog.to_dict("records"):
        route_id = candidate_id = "\x1f".join(str(row[column]) for column in key_columns)
        suffix = 2
        while candidate_id in choices:
            candidate_id = f"{route_id}\x1f#{suffix}"
            suffix += 1
        text = candidate = (
            f"{process_text(row['공정'])} · {row['양산구분']} · {row['제품정보']} · "
            f"{row['Stack']} · {row['WF 구분']} · {row['Area_Name']} · {row['소요기준']} · "
            f"MCP {row['MCP_SEQ']} / STEP {row['STEP_SEQ']} · {row['적용월수']}개월"
        )
        suffix = 2
        while candidate in used:
            candidate = f"{text} #{suffix}"
            suffix += 1
        used.add(candidate)
        choices[candidate_id] = candidate
    return choices


# STEP 구성 요약을 dtype 을 줄여 한꺼번에 보내는 행 수의 끝. Streamlit 1.63 은 이보다 긴 pandas
# 표를 `lazy=None` 에서 스스로 lazy 로 보낸다(`lazy_df_source.AUTO_LAZY_ROW_THRESHOLD` — 첫
# 덩어리만 보내고 정렬은 서버가 한다). 그 서버 정렬은 category 열에서 실패해 표 전체가 「Failed to
# load data」 가 되므로 그 길에는 줄인 사본을 넘기지 않는다. 거꾸로 긴 표를 `lazy=False` 로 못
# 박으면 화면이 정렬을 끈다(한꺼번에 받은 표가 이 행 수를 넘으면 정렬 단추가 없다). 그래서 긴 표는
# 예전 그대로 Streamlit 에 맡긴다.
STEP_SUMMARY_EAGER_MAX_ROWS = 150_000
# 요약에서 수인 열(화면 이름). 나머지는 경로 글자 열이다.
STEP_SUMMARY_NUMBER_COLUMNS = ("월", "STEP 수", "수요 변형 수")
# 조회기간에 편집할 경로 STEP 이 없을 때의 빈 결과 한 줄과 그 풍선.
STEP_EMPTY_TEXT = "선택한 조회기간에 편집할 공정 경로 STEP이 없습니다."
STEP_EMPTY_HELP = "사이드바 조회기간을 넓히면 그 기간의 경로 STEP 이 나옵니다."


def _compact_step_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """STEP 구성 요약의 화면 사본에서 dtype 만 줄인다 — 값·차례·보이는 글자는 그대로다.

    요약은 월 × 경로 그룹의 긴 표라 경로 글자 열(Area·공정·양산·제품·Stack·속성·소요기준)이
    행마다 되풀이되어 Arrow 글자로 실린다. 그 열은 `category`(고유 글자를 한 번만 싣는다)로, 월과
    두 개수는 값이 들어가는 가장 좁은 정수(`downcast` 는 넘치지 않는 폭을 고른다)로 보낸다.
    부르는 쪽이 표시명을 입힌 **뒤**에 부른다 — category 의 값이 곧 보이는 글자다.
    """
    compact = summary.astype(
        {
            column: "category"
            for column in summary.columns
            if column not in STEP_SUMMARY_NUMBER_COLUMNS
        }
    )
    for column in STEP_SUMMARY_NUMBER_COLUMNS:
        if column in compact.columns:
            compact[column] = pd.to_numeric(compact[column], downcast="integer")
    return compact


@st.dialog("STEP 추가·삭제", width="large", on_dismiss=_close_dialog)
def _step_dialog(step_catalog: pd.DataFrame) -> None:
    """고른 경로 STEP 을 복제하거나 지운다. 조회기간의 모든 연결 수요에 함께 반영한다.

    목록과 네 경로 표 조각은 팝업을 연 회차(full run)가 그 회차 활성 시나리오에서 만든 것이다 —
    팝업 안 조작(fragment 재실행)도 같은 목록 인자와 그 회차 `edit_slices` 로 다시 불린다.
    """
    # STEP 을 더하거나 빼면 UPEH·측정률 표의 행이 바뀌어 그 표의 적용하지 않은 편집이 버려진다.
    dropped_edits = [
        TABLE_NAMES[table_name]
        for table_name in STEP_ROUTE_EDIT_TABLES
        if reference_grid.draft_pending(table_name)
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
    # 값은 경로 키이고 글자만 표시명이다. 아래에서 그 키의 원본 행을 읽어 STEP 복제·삭제에 넘기므로
    # 값 경로에는 표시명이 닿지 않는다.
    route_choices = _step_route_choices(step_catalog)
    route_ids = list(route_choices)
    # 잡은 값을 매 회차 세션에 다시 적는다(없거나 목록 밖이면 첫 줄). 적은 값만 브라우저에 가므로
    # 글자가 바뀌는 회차(표시명 변경·적용월수 변화)에도 브라우저가 새 글자를 받는다. 기본값을 세션에
    # 심으므로 위젯에 `index=` 를 주지 않는다.
    prune_choice(STEP_ROUTE_KEY, route_ids, default=route_ids[0])
    selected_route_id = st.selectbox(
        "복제 원본 또는 삭제 대상 STEP",
        options=route_ids,
        # 목록 밖 값(옛 세션 값)은 키 글자 그대로 — 어떤 줄의 글자와도 겹치지 않는다.
        format_func=lambda route_id: route_choices.get(str(route_id), str(route_id)),
        key=STEP_ROUTE_KEY,
        persist_state="page",
    )
    selected_route_row = step_catalog.iloc[route_ids.index(str(selected_route_id))]
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
        table_name: edit_slices.get_or_stop(table_name)
        for table_name in ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO")
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
        st.error(bootstrap_error_message(exc))
        return
    months_label = ", ".join(str(month) for month in step_result.affected_months)
    # 버린 편집은 팝업이 미리 말했지만 닫힌 뒤에도 무엇이 사라졌는지 남긴다.
    dropped_notice = (
        f". {'·'.join(dropped_edits)} 표의 적용하지 않은 편집은 버렸습니다" if dropped_edits else ""
    )
    st.session_state["capacity_step_flash"] = (
        f"STEP을 {action_label}했습니다. 적용월 {months_label} · "
        f"수요 변형 {step_result.affected_variants:,}개 · "
        f"RQ_REQB {step_result.affected_reqb_rows:,}행{dropped_notice}"
    )
    # STEP 을 더하거나 빼면 UPEH·측정률 두 표의 행이 바뀐다 — 그 표의 초안·이력과 STEP 선택만
    # 비운다.
    mark_own_change(
        OWN_CHANGE_KEY,
        (
            *(cells_key(table_name) for table_name in STEP_ROUTE_EDIT_TABLES),
            *(history_key(table_name) for table_name in STEP_ROUTE_EDIT_TABLES),
            *step_widget_keys,
        ),
    )
    _close_dialog()
    st.rerun()


def _render_step_view(
    step_summary: pd.DataFrame, step_catalog: pd.DataFrame, flash_message: object
) -> None:
    """「STEP 구성」 보기 — 작업 줄(STEP 추가·삭제 팝업 열기)·알림·요약 표."""
    if step_catalog.empty:
        # 빈 결과 한 줄(값) — 고칠 곳은 풍선이 말한다(설계 규칙 UI-TXT-03 · 04).
        st.caption(STEP_EMPTY_TEXT, help=STEP_EMPTY_HELP)
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
    # 추가·삭제 결과는 오른쪽 아래 알림창으로만 낸다(2026-11-03 결정 보드 D3 (가) — 버튼 곁에는 오류
    # · 거부만). 이 보기를 그리는 회차마다 표지 한 자리다(알릴 것이 없으면 빈 스타일).
    sending: list[alerts.AlertNote] = []
    if isinstance(flash_message, str):
        note = alerts.event_note("FL-01", text=flash_message, full=flash_message)
        # 버튼 곁 결과 알림과 같은 꼴(`flash.render_flash`)이라 종류 · 원문을 함께 싣는다.
        note["flash"] = "success"
        note["markdown"] = flash_message
        sending.append(note)
    alerts.emit(sending)
    # `step_summary` 는 캐시된 프레임이다. 제자리에서 고치면 다음 rerun 이 표시명 프레임을 계산
    # 입력으로 받으므로 화면 복사본에만 표시명을 입힌다.
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
    # 한꺼번에 보내는 표만 바이트를 줄이고 `lazy=False` 로 못 박는다. 그보다 긴 표는 예전처럼
    # Streamlit 이 고르게 둔다(`STEP_SUMMARY_EAGER_MAX_ROWS`).
    summary_is_eager = len(displayed_step_summary) <= STEP_SUMMARY_EAGER_MAX_ROWS
    st.dataframe(
        _compact_step_summary(displayed_step_summary)
        if summary_is_eager
        else displayed_step_summary,
        hide_index=True,
        width="stretch",
        height=260,
        column_config={
            # 글자 열은 글자 칸으로 못 박는다 — category 열을 그대로 두면 화면이 선택 칸 꼴로 그려
            # 글자 자리가 화소 단위로 어긋난다. 글자 칸이면 정렬·검색·CSV 까지 예전 글자 열과 같다.
            **{
                column: st.column_config.TextColumn()
                for column in displayed_step_summary.columns
                if column not in STEP_SUMMARY_NUMBER_COLUMNS
            },
            "STEP 수": st.column_config.NumberColumn(format="%d"),
            "수요 변형 수": st.column_config.NumberColumn(format="%d"),
        },
        key="capacity_step_summary",
        lazy=False if summary_is_eager else None,
    )


# STEP 추가·삭제 알림은 매 회차 꺼낸다 — 그리는 것은 STEP 구성 보기를 그리는 회차뿐이다. 꺼내기까지
# 보기에 묶으면 다른 종류를 보다 리비전을 불러온 뒤 STEP 구성을 고를 때 옛 문구가 남는다.
flash_message = st.session_state.pop("capacity_step_flash", None)
if step_tables is not None:
    step_summary, step_catalog = step_tables
    # 팝업만 열린 회차(다른 종류를 고른 채)에는 보기를 그리지 않는다.
    if current_dataset == STEP_VIEW:
        with view_box:
            _render_step_view(step_summary, step_catalog, flash_message)
    if not step_catalog.empty and st.session_state.get(DIALOG_KEY) == STEP_DIALOG:
        _step_dialog(step_catalog)

# `현황` 은 보는 표다(보유·대여를 합친 값에 숫자를 쓸 자리가 없어 편집 대상이 아니다). 「상세」와
# 필터는 사이드바 `표 조건` 카드이고 그 종류를 골랐을 때만 선다. 선택은 `persist_state` 로 남는다.
# 표도 그 회차에만, 「상세」 값에 맞는 한 벌만 만든다.
if current_dataset == EQUIPMENT_OVERVIEW:
    # 조각은 카드 밖에서 자른다 — 자르다 난 오류 문구가 사이드바 카드가 아니라 본문에 선다.
    own_count, lent_count, available_count = (
        edit_slices.get_or_stop(table_name) for table_name, _, _, _ in EQUIPMENT_EDITORS
    )
    with table_card(CARD_NAME):
        show_equipment_detail = st.toggle(
            "상세",
            key="equipment_count_detail",
            persist_state="session",
        )
        equipment_dimensions = (
            DETAILED_EQUIPMENT_DIMENSIONS if show_equipment_detail else EQUIPMENT_DIMENSIONS
        )
        # 표시순서 스코프 문자열은 DB 공용 프로필의 행 키다. 페이지 이름이 바뀌어도 **이 두 인자는
        # 그대로 둔다** — 안 맞으면 예외가 아니라 정렬이 조용히 사라진다.
        equipment_table = apply_display_order(
            build_equipment_count_table(
                own_count, lent_count, available_count, detailed=show_equipment_detail
            ),
            display_order,
            PAGE_REFERENCE,
            TAB_EQUIPMENT_COUNT,
        )
        equipment_table = render_column_filter_controls(
            equipment_table,
            equipment_dimensions,
            key_prefix="equipment_count_filter",
            value_labels=process_labels.value_labels(),
        )
    with view_box:
        equipment_month_columns = [
            column for column in equipment_table.columns if column not in equipment_dimensions
        ]
        displayed_equipment_table = equipment_table.copy()
        displayed_equipment_table[equipment_month_columns] = displayed_equipment_table[
            equipment_month_columns
        ].mask(displayed_equipment_table[equipment_month_columns].eq(0))
        # 필터를 먼저 걸고 그 뒤에 표시명을 입힌다. 순서가 바뀌면 위 `isin` 이 원본 컬럼과
        # 맞지 않는다. 설비대수 편집 표의 왕복 양식은 따로 만든 프레임이라 이 복사본이 붙여넣기
        # 경로에 닿지 않는다.
        displayed_equipment_table["공정"] = process_labels.series(displayed_equipment_table["공정"])
        st.dataframe(
            # 고정 uuid — 내용이 같으면 회차마다 같은 메시지라 브라우저가 표를 다시 받지 않는다.
            # 「상세」 두 꼴은 다른 표라 값을 가른다.
            classification_styled(
                displayed_equipment_table,
                equipment_dimensions,
                uuid="equipment_count_detail" if show_equipment_detail else "equipment_count",
            ),
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
    """편집 표 하나의 적용 규칙. 그리드 적용과 팝업 붙여넣기가 같은 규칙을 탄다.

    `removed_notice` 는 붙여넣기로 비운 칸을 알리는 문구(`{count}` 자리)다. `blank_is_zero` 인
    표(설비대수)는 양식의 0 이 「원래 없던 조합」이라, 0 인 칸을 비운 것은 바뀐 것이 없어 세지
    않는다.
    """

    table_name: str
    editor_key: str
    dimensions: list[str]
    template: pd.DataFrame
    to_rows: Callable[[pd.DataFrame], pd.DataFrame]
    removed_notice: str = REMOVED_DROPS
    blank_is_zero: bool = False

    @property
    def own_keys(self) -> tuple[str, ...]:
        """적용으로 다음 회차에 비울 이 표의 편집 상태 — 그리드 초안·이력 세션 칸."""
        return (cells_key(self.table_name), history_key(self.table_name))


def _edit_flash(
    editor_key: str,
    label: str,
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
    (`f"{editor_key}_apply"` — `reference_grid.render_actions` 가 꺼낸다)다. 붙여넣기 팝업은
    적용하면 닫히므로 그 결과(「지워진 칸」 경고 포함)도 작업 줄 아래에서 본다.

    **`editor_key` 는 작업 줄을 그릴 때 쓴 값 그대로여야 한다.** 여기에 리터럴을 다시 적으면
    쓰는 키와 읽는 키가 갈라져 문구가 조용히 사라진다 — 실제로 `capa_` 접두어가 빠져 여섯
    탭이 그랬다.
    """
    origin = "붙여넣기 데이터를" if imported else "편집값을"
    # 지워진 칸은 대개 **오류가 아니라 정당한 편집**이다(효율·여유율·일수에서 UPEH 경로가 쓰는
    # 칸은 적용 전에 막힌다). 다만 붙여넣기는 그리드와 달리 적용 전에 변경 수를 보여 주지 않아, 한
    # 열이 통째로 비어 와도 조용히 지나간다. 그래서 그 칸이 무엇이 됐는지를 표마다 맞는 말로
    # 알린다 — UPEH 는 경로가 빠져 부하량을 그대로 둔 채 대당 Capa 만 잃는다.
    removal = ""
    if removed:
        removal = removed_notice.format(count=removed)
    return (
        f"{editor_key}_apply",
        f"{label} {origin} 활성 시나리오에 적용했습니다. "
        f"{removal}"
        "리비전으로 남기려면 사이드바 시나리오 칸 → 「신규 리비전 저장」을 누르세요.",
    )


def _removed_values(editor: _Editor, imported_table: pd.DataFrame | None) -> int:
    """붙여넣기로 비워진 칸 수. 그리드 편집은 이미 적용 전에 변경 수를 보여 준다."""
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
    source = edit_slices.get_or_stop("RQ_UPEH")
    rows = performance_from_edit_table(table, source)
    validate_upeh_edit(source, rows, active_scenario["tables"])
    return rows


def _required_rows(
    table_name: str,
    label: str,
    dimensions: list[str],
    value_column: str,
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """효율·여유율·일수의 적용 행. **UPEH 경로가 쓰는 칸을 비우거나 0 이하로 하면 막는다.**

    막는 규칙은 `validate_required_edit` 에 있다. `source` 는 편집표를 만든 같은 기간의 원본
    (이 회차 조각)이다. 격자 적용과 붙여넣기가 모두 이 함수를 지난다.
    """

    def to_rows(table: pd.DataFrame) -> pd.DataFrame:
        rows = reference_from_edit_table(table, dimensions, value_column, f"{label} 편집값")
        source = edit_slices.get_or_stop(table_name)
        validate_required_edit(
            table_name, label, source, rows, value_column, active_scenario["tables"]
        )
        return rows

    return to_rows


def _apply_edit(editor: _Editor, source: pd.DataFrame, *, imported: bool) -> None:
    """편집값 또는 붙여넣은 표를 활성 시나리오에 적용하고 완료 알림을 남긴다.

    막히면 `KeyError`/`ValueError` 를 던진다. 적용이 끝나면 `mark_own_change` 로 다음 회차에 **이
    표만** 새 원본으로 다시 선다(다른 표의 적용하지 않은 편집은 남는다). rerun 은 부르는 쪽이 한다.
    """
    rows = editor.to_rows(source)
    flash = _edit_flash(
        editor.editor_key,
        TABLE_NAMES[editor.table_name],
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
    # 적용한 이 표만 새 원본으로 다시 세운다. 다른 표의 적용하지 않은 편집은 그대로 둔다.
    # STEP 팝업의 선택도 비운다 — 경로 선택은 목록의 순번이라, UPEH 한 행을 비우면 경로가 빠져
    # 뒤 순번이 당겨지고 다음에 열 때 다른 경로가 골라져 있다(2026-09-29 2차 리뷰).
    mark_own_change(OWN_CHANGE_KEY, (*editor.own_keys, *step_widget_keys))


def _paste_into(editor: _Editor) -> Callable[[pd.DataFrame], None]:
    def paste(table: pd.DataFrame) -> None:
        _apply_edit(editor, table, imported=True)

    return paste


def _editor(table_name: str, template: pd.DataFrame) -> _Editor:
    """편집 표 하나의 적용 규칙(양식은 부르는 쪽이 — 옛 편집표는 그 회차 양식, 그리드는 그 표
    양식)."""
    editor_key = EDITOR_KEYS[table_name]
    for equipment_table, category, count_column, _ in EQUIPMENT_EDITORS:
        if table_name == equipment_table:
            # 설비대수도 다른 기준정보와 **같은 편집기**를 쓴다. 값붙여넣기만 되던 화면이라 한 칸을
            # 고치려면 표 전체를 Excel 로 왕복해야 했다. 빈칸은 0 대로 저장한다.
            return _Editor(
                table_name,
                editor_key,
                EQUIPMENT_DIMENSIONS,
                template,
                _equipment_rows(category, count_column),
                REMOVED_EQUIPMENT,
                blank_is_zero=True,
            )
    dimensions, value_column, _ = TABLE_SOURCES[table_name]
    if table_name == "RQ_UPEH":
        return _Editor(table_name, editor_key, dimensions, template, _upeh_rows)
    if table_name in RATIO_TABLES:
        label = TABLE_NAMES[table_name]
        assert value_column is not None
        column = value_column
        return _Editor(
            table_name,
            editor_key,
            dimensions,
            template,
            lambda table: reference_from_edit_table(table, dimensions, column, f"{label} 편집값"),
            REMOVED_RATIO,
        )
    assert value_column is not None
    return _Editor(
        table_name,
        editor_key,
        dimensions,
        template,
        _required_rows(table_name, TABLE_NAMES[table_name], dimensions, value_column),
        REMOVED_UNUSED,
    )


def _equipment_rows(category: str, value_column: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def to_rows(table: pd.DataFrame) -> pd.DataFrame:
        return equipment_count_from_edit_table(table, category, value_column)

    return to_rows


# 측정률 표에 이 기간 행이 없으면 편집 표가 0 행이다(모든 칸을 비워 적용했거나 원천에 행이 없다).
# 계산은 1.0 으로 이어 가므로 오류가 아니다 — 자리에는 빈 결과 한 줄(값)만 두고, 무엇으로
# 계산되는지와 이 표에서 행을 더할 수 없다는 것(원래 한계)은 그 줄의 풍선이 말한다(설계 규칙
# UI-TXT-01 · 04).
RATIO_EMPTY_TEXT = "이 기간에 {label} 행이 없습니다."
RATIO_EMPTY_HELP = "모든 경로를 측정률 1.0 으로 계산합니다. 이 표에서는 행을 더할 수 없습니다."


def _open_grid_paste(editor_key: str) -> None:
    st.session_state[DIALOG_KEY] = editor_key


# 편집 표를 고른 회차 — 표 조건(사이드바) → 작업 줄(표 위) → 그리드. 그리드 자리는 종류와 상관없이
# 늘 같은 자리에서 그린다(읽기 보기를 골랐으면 표 없는 껍데기 — 마운트만 남는다).
current_grid = grid_tables.get(current_dataset)
grid_actions: reference_grid.Actions | None = None
if current_grid is not None:
    grid_filter_prefix = _filter_prefix(current_dataset)
    # 필터는 보기만 좁힌다 — 초안이 업무 키라 필터를 바꿔도 편집이 다른 줄에 붙지 않아 잠그지
    # 않는다. 고른 값은 feed 로 가 브라우저가 거른다(편집 범위 줄은 서버가 같은 선택으로 센다). 행이
    # 없는 표(측정률이 통째로 빈 기간)에는 거를 것이 없어 세우지 않는다.
    grid_visible = current_grid.template
    if not current_grid.template.empty:
        with table_card(CARD_NAME):
            grid_visible = render_column_filter_controls(
                current_grid.template,
                list(current_grid.dimensions),
                key_prefix=grid_filter_prefix,
                column_labels=COLUMN_LABELS,
                value_labels=process_labels.value_labels(),
            )
    with actions_box:
        # 그 종류를 골랐을 때만 조각을 본다 — 고르지 않은 표 때문에 자르지 않는다.
        if current_dataset in RATIO_TABLES and edit_slices.get_or_stop(current_dataset).empty:
            st.caption(
                RATIO_EMPTY_TEXT.format(label=TABLE_NAMES[current_dataset]), help=RATIO_EMPTY_HELP
            )
        grid_actions = reference_grid.render_actions(
            current_grid,
            grid_visible,
            open_paste=partial(_open_grid_paste, current_grid.editor_key),
        )
    with grid_box:
        reference_grid.render_grid(current_grid, key_prefix=grid_filter_prefix)
    if st.session_state.get(DIALOG_KEY) == current_grid.editor_key:
        grid_editor = _editor(current_dataset, current_grid.template)
        fmt = reference_grid.GRID_FORMATS[current_dataset]
        # 왕복 CSV·붙여넣기는 전체 표 계약이다(걸러진 표를 넘기면 나머지 공정을 그 기간에서
        # 지운다). 붙여넣기도 그리드와 같은 하한·상한·정수 규칙을 지난다(그리드만 막으면 붙여넣은
        # 85·1.2·음수·일수 30.5 가 들어온다).
        paste_dialog(
            current_grid.template,
            table_name=TABLE_NAMES[current_dataset],
            dimensions=list(current_grid.dimensions),
            file_name=f"{current_dataset}_{effective_start_month}_{effective_end_month}.csv",
            editor_key=current_grid.editor_key,
            dialog_key=DIALOG_KEY,
            on_paste=_paste_into(grid_editor),
            rename_notice=bool(current_grid.labels),
            min_value=fmt.min_value,
            max_value=fmt.max_value,
            integer=fmt.integer,
            pending_notice=reference_grid.paste_notice(current_dataset),
        )
else:
    with grid_box:
        reference_grid.render_grid(None)

# 「변경사항 적용」 — 칸 오류가 남았으면 고칠 칸을 알리고 멈춘다(업무 규칙 검사 전에). 아니면 양식에
# 초안을 업무 키로 덮어 옛 편집표와 같은 적용 길을 탄다(업무 규칙 오류는 문장으로, 초안은 남긴다).
if current_grid is not None and grid_actions is not None and grid_actions.submitted:
    blocked = reference_grid.error_notice(current_grid, process_labels.label)
    if blocked is not None:
        grid_actions.notice.error(blocked, icon=":material/error:")
    else:
        grid_editor = _editor(current_dataset, current_grid.template)
        try:
            merged = reference_grid.merged_template(current_grid)
            _apply_edit(grid_editor, merged, imported=False)
        except (KeyError, ValueError) as exc:
            grid_actions.notice.error(bootstrap_error_message(exc))
        else:
            st.rerun()
