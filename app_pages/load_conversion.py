# Purpose: PKG PLAN과 수율을 편집하고 PKG·Chip·Wafer·Density 부하량 환산 결과를 제공한다.

"""생산 계획 — 사이드바 조건 카드와 Guide 를 처음 적용한 화면(2026-09-28 사용자 결정).

- **환산 조건**(소요기준·상세·EDP)은 본문이 아니라 사이드바 「조회 조건」의 카드다. 환산
  탭이 열렸을 때만 서고, 기본은 접힘이며 한 번 편 카드는 탭을 오가도 편 채로 남는다.
- **설명은 Guide 로 옮겼다**(`guides/load_conversion.md`). 본문에는 결과와 그 결과에 대한
  행동(적용·붙여넣기·등록)과 상태 알림만 남는다.
- **작업 줄은 표 위다.** 적용 버튼이 높이 500px 표 아래에 있으면 고친 뒤 버튼이 화면 밖이라
  적용하지 않고 넘어가기 쉽다(사용자 지적). 완료 알림도 작업 줄 바로 아래 — 누른 자리에서
  보인다.
- **Excel 붙여넣기와 가상 제품 등록은 팝업**이다. 가끔 하는 쓰기 작업이라 표 자리를 차지할
  이유가 없고, 사이드바 조회 조건에 두면 「사이드바 = 보는 조건」이 흐려진다. 「가상 제품 등록」 은
  PKG PLAN 작업 줄 「Excel 붙여넣기」 바로 뒤 「⋯」 메뉴 안이다(2026-11-12 보드 답 n2 나).
- **PKG PLAN · 수율 표는 범용 편집 그리드다**(2026-11-12 보드 답 k-a1 · k-a2 — 기준 정보와 같은
  편집기, `components/plan_grid.py`). 초안은 표마다 세션 칸(업무 키)이라 탭을 오가거나 화면을 떠나도
  남고, 줄 차례만 바뀐 회차에도 제 칸에 붙는다. 닫힌 탭의 그리드는 표 없는 껍데기로 마운트만 남는다.
"""

from typing import cast

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation import alerts
from capa_simulation.components import plan_grid
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import pending_flash, queue_flash
from capa_simulation.components.grouped_monthly_table import (
    build_grouped_monthly_export,
    render_grouped_monthly_table,
)
from capa_simulation.components.literal_markdown import literal_markdown, quoted
from capa_simulation.components.month_editor import PASTE_DROPS_EDITS_NOTICE
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.paste_form import refuse_paste
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.reference_csv_tools import render_reference_clipboard_form
from capa_simulation.components.required_exclusion_notice import (
    FULL_SCOPE,
    alert_uncounted_demand,
    plan_exclusion_lists,
)
from capa_simulation.components.scenario_edit_bar import (
    mark_own_change,
    pending_edit_labels,
    register_pending_edits,
    reset_editors_on_source_change,
    show_row_order_reset,
    source_token,
)
from capa_simulation.components.state_alerts import (
    ALARM_ROW_PLACE,
    AlertScope,
    alarm_table_place,
    alert_table,
    clipped_label,
    simulation_scope,
    table_clipped,
)
from capa_simulation.components.tab_marks import mark_pending_tabs
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import (
    render_csv_download,
    render_table_heading,
)
from capa_simulation.components.write_guard import held_flash, note_notice, notice_marks
from capa_simulation.navigation import LOAD_CONVERSION_TAB_KEY
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    PageContext,
    bootstrap_error_message,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.plan_grid_keys import PLAN_TABLE, YIELD_TABLE, cells_key, history_key
from capa_simulation.scenario_state import (
    ActiveScenario,
    apply_month_updates,
    apply_table_updates,
    remember_virtual_product,
    scenario_month_table,
    scenario_table,
    session_virtual_products,
)
from capa_simulation.services.korean_particle import direction_particle, with_object_particle
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    PLAN_QUANTITY_BLANK_REASON,
    YIELD_EDITOR_DIMENSIONS,
    YIELD_KEYS,
    YIELD_LOCK_REASON_COLUMN,
    YIELD_VALUE_COLUMNS,
    DemandBasis,
    attach_plan_attributes,
    count_plan_value_changes,
    filter_edp_plan,
    load_exclusions,
    plan_from_edit_table,
    restore_locked_yield_rows,
    yield_from_edit_table,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.reference_csv import count_removed_values
from capa_simulation.services.required_equipment import (
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
    UNROUTED_LOADS_ATTR,
    required_exclusion_counts,
)
from capa_simulation.services.simulation_cache import (
    display_order_digest,
    frame_digest,
    get_full_capacity_outcome,
    get_monthly_volume,
    get_plan_edit_table,
    get_yield_edit_tables,
    scenario_cache_key,
)
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    available_source_products,
    clone_product,
    cloned_plan_months,
    records_to_frame,
)
from capa_simulation.sidebar_status import condition_card

render_page_header("생산 계획")
render_page_guide("load_conversion", title="생산 계획")


try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    active_scenario = context.active_scenario
    prepared_display_order = context.display_order
    selected_start_month = context.selected_start_month
    selected_end_month = context.selected_end_month
except BOOTSTRAP_ERRORS as exc:
    render_data_error(
        f"기준정보를 불러오지 못했습니다: {bootstrap_error_message(exc)}", code="ST-20"
    )
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
    # 편집표 원본은 (시나리오 내용·편집 기간·표시순서)의 순수 함수라 그 키로 캐시한다. 환산 조건
    # 토글·탭 전환마다 같은 피벗을 다시 하지 않는다.
    edit_table_key = scenario_cache_key(
        reference_version, active_scenario, effective_start_month, effective_end_month
    )
    display_order_key = display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])
    default_plan_table = get_plan_edit_table(
        edit_table_key,
        display_order_key,
        _plan=filtered_plan,
        _display_order=prepared_display_order,
    )
except ValueError as exc:
    render_data_error(bootstrap_error_message(exc), code="ST-20")
    st.stop()

# 수율 표는 따로 세운다. 예전에는 위 `try` 에 함께 있어 RQ_YLD 한 행의 값이 비었거나 0 이면
# PKG PLAN 편집·붙여넣기·가상 제품 등록·환산 탭까지 전부 섰다(2026-09-29 횡전개 감사). 값이
# 잘못된 행은 「편집 불가」로 알리고 표에는 그 달 칸을 빈칸으로 싣는다 — 제품의 모든 달이
# 잠겨도 행이 남아 여기서 고칠 수 있다(2026-09-29 리뷰). 적용 때 빈칸은 원본 그대로 되붙인다.
# 연결 키 결측·중복처럼 표를 세울 수 없는 오류는 수율 탭 안에만 띄운다.
yield_build_error: str | None = None
default_yield_table: pd.DataFrame | None = None
locked_yield_rows = pd.DataFrame(columns=[*YIELD_KEYS, *YIELD_VALUE_COLUMNS])
try:
    default_yield_table, locked_yield_rows = get_yield_edit_tables(
        edit_table_key,
        display_order_key,
        _yield_data=filtered_yield,
        _display_order=prepared_display_order,
    )
except ValueError as exc:
    yield_build_error = bootstrap_error_message(exc)

SOURCE_TOKEN_KEY = "load_conversion_source_token"
# 붙여넣기 결과는 곧바로 전역에 반영하지 않고 이 키에 담아 PKG PLAN 탭에만 보여준다.
# 사용자가 "변경사항 적용" 을 눌러야 활성 시나리오로 넘어간다.
PLAN_STAGED_KEY = "pkg_plan_staged_paste"
PLAN_APPLIED_FLASH_KEY = "pkg_plan_applied_flash"
PRODUCT_REGISTERED_FLASH_KEY = "virtual_product_registered_flash"
PLAN_PASTE_KEY = "rq_pkg_plan_csv"
# 붙여넣은 표는 대기 표로 올라갈 뿐 적용이 아니다 — 수율 · 기준 정보의 「붙여넣기 적용」 과 가른다.
PLAN_PASTE_APPLY_LABEL = "붙여넣기 올리기"
YIELD_PASTE_KEY = "rq_yield_csv"
VIRTUAL_SOURCE_KEY = "virtual_product_source"
VIRTUAL_STACK_KEY = "virtual_product_stack"
# 작업 줄 알림 칸 — 붙여넣기·적용·등록 알림이 같은 아이콘의 성공 알림으로 선다.
PLAN_PASTE_FLASH_KEY = f"{PLAN_PASTE_KEY}_flash"
YIELD_FLASH_KEY = f"{YIELD_PASTE_KEY}_flash"
APPLIED_ICON = ":material/published_with_changes:"
# 적용 버튼 툴팁. 「적용해야 반영된다」는 동작을 좌우하는 안내라 Guide 로만 보내지 않고
# 버튼에 남긴다(2026-09-28 사용자 결정).
PLAN_APPLY_HELP = "누르면 환산·소요대수·확보율과 홈 대시보드가 이 계획으로 다시 계산됩니다."
YIELD_APPLY_HELP = "누르면 환산수량과 다른 페이지의 산출값이 이 수율로 다시 계산됩니다."
# 잠긴 적용 단추의 풍선은 하는 일이 아니라 까닭이다(설계 규칙 UI-INP-07).
APPLY_LOCKED_HELP = "고친 칸이 있으면 누를 수 있습니다."
# 버려질 편집이 있을 때 등록 단추의 풍선 — 남기는 법. 무엇이 버려지는지는 창 맨 위 값 줄이다.
VIRTUAL_DROP_HELP = (
    "편집을 남기려면 먼저 그 표의 「변경사항 적용」 을 누릅니다. 붙여넣기는 등록한 뒤 다시 "
    "붙여넣어도 됩니다."
)
# 원본이 바뀌면 아직 적용하지 않은 붙여넣기는 행·월 구성이 맞지 않으므로 함께 버린다. 이 화면이
# 스스로 적용한 것이면(`mark_own_change`) 그 탭의 그리드 초안만 비운다 — 수율을 적용했다고 PKG
# PLAN 에서 고치고 아직 적용하지 않은 값까지 사라지면 안 된다.
OWN_CHANGE_KEY = "load_conversion_own_change"
# 앱 머리를 고치려 다시 도는 회차가 넘기는 줄 차례 비움 결과 — 알림은 다시 돈 회차가 낸다.
SOURCE_RESET_KEY = "load_conversion_source_reset"
# 그리드 초안 · 붙여넣기 대기 이름 — 변경 판 「적용 전 편집」 목록과 줄 차례 비움 알림이 같은 이름을
# 쓴다.
DRAFT_NAMES = {cells_key(PLAN_TABLE): "PKG PLAN", cells_key(YIELD_TABLE): "수율"}
STAGED_NAMES = {PLAN_STAGED_KEY: "PKG PLAN 붙여넣기"}
# 그리드 초안 · 이력 세션 칸 — 원본이 바뀌면(기준정보 버전 · 리비전 · 기간) 함께 버린다.
GRID_SESSION_KEYS = tuple(
    key for table in (PLAN_TABLE, YIELD_TABLE) for key in (cells_key(table), history_key(table))
)
# 앱 머리(칩 · 탭 점)는 이 본문보다 먼저 이 값으로 그렸다.
edits_in_head = pending_edit_labels("load_conversion.py")
source_reset = reset_editors_on_source_change(
    SOURCE_TOKEN_KEY,
    source_token(
        reference_version,
        active_scenario,
        effective_start_month,
        effective_end_month,
        row_order=display_order_key,
    ),
    (),
    other_keys=(PLAN_STAGED_KEY, *GRID_SESSION_KEYS),
    own_change_key=OWN_CHANGE_KEY,
    names={**DRAFT_NAMES, **STAGED_NAMES},
    # 줄 차례만 바뀐 회차에는 남긴다 — 그리드 초안은 업무 키 + 월이라 제 칸에 붙고, 붙여넣기 대기
    # 표는 붙여넣은 차례 그대로 PKG PLAN 그리드의 원본이 되며 적용도 업무 키로 한다.
    order_free_keys=(PLAN_STAGED_KEY, *GRID_SESSION_KEYS),
)
if set(edits_in_head) - set(pending_edit_labels("load_conversion.py")):
    # 원본이 바뀌어 편집을 버렸는데 칩 · 탭 점은 버리기 전 값으로 섰다 — 그대로 두면 다음 조작까지
    # 남는다. 한 번 다시 돈다(다음 회차엔 버릴 편집이 없어 되풀이되지 않는다). 알림을 지금 내면
    # 끊긴 회차와 함께 사라질 수 있어 결과를 넘긴다.
    st.session_state[SOURCE_RESET_KEY] = source_reset
    st.rerun()
# 줄 차례가 바뀌어 적용 전 편집을 버린 회차는 오른쪽 아래 알림창에 한 번 알린다(사건 알림 `ST-09`).
show_row_order_reset(st.session_state.pop(SOURCE_RESET_KEY, source_reset))
# 붙여넣기 대기 표는 PKG PLAN 그리드의 원본이다. `source_token` 은 원본의 버전·기간만 보고 표
# 스키마는 보지 않는다. 그래서 행 차원이 늘어난 뒤에도(예: `Pack Code` 업무 키 승격) 옛 스키마로
# 붙여넣어 둔 표가 세션에 남아 원본이 되면 양식 색인이 `KeyError` 로 죽는다 — 그 표는 버린다.
staged_plan_table = st.session_state.get(PLAN_STAGED_KEY)
if isinstance(staged_plan_table, pd.DataFrame) and not set(PLAN_EDITOR_DIMENSIONS).issubset(
    staged_plan_table.columns
):
    st.session_state.pop(PLAN_STAGED_KEY, None)
    staged_plan_table = None
plan_staged = isinstance(staged_plan_table, pd.DataFrame)
plan_editor_source: pd.DataFrame = (
    staged_plan_table if isinstance(staged_plan_table, pd.DataFrame) else default_plan_table
)
# 사이드바가 저장·불러오기 전에 「적용하지 않은 편집」을 묻도록 이 화면의 그리드 초안과 붙여넣기
# 대기분을 알린다. 둘 다 세션 칸이라 화면을 옮겨도 남는다. 방금 적용한 표는 사이드바가 빼고 센다.
register_pending_edits(
    "load_conversion.py",
    "생산 계획",
    {},
    staged=STAGED_NAMES,
    drafts=DRAFT_NAMES,
    own_change_key=OWN_CHANGE_KEY,
)

# 본문은 제목 · 탭 · 탭 내용만이다. 「활성 시나리오 · 수정본 N」 줄은 없앴다 — 미저장 여부는
# 사이드바 시나리오 줄의 배지가 이미 말하고, 편집을 버리는 「편집 되돌리기」도 그 줄의 팝업에
# 있다(모든 화면의 편집을 버리는 시나리오 단위 동작이다). 되돌리면 리비전 번호가 올라
# 위 `source_token` 이 바뀌므로 이 화면의 편집표·붙여넣기 대기분도 다음 회차에 함께 비워진다.
# 탭 이름 앞 아이콘은 탭이 하는 일이다 — 환산은 계산해 보는 곳, PKG PLAN·수율은 값을 고치는
# 곳이다(2026-09-29 사용자 결정, 탭 목록 개선안 B).
TAB_KEY = LOAD_CONVERSION_TAB_KEY
TAB_CONVERSION = ":material/calculate: 환산"
TAB_PKG_PLAN = ":material/edit_calendar: PKG PLAN"
TAB_YIELD = ":material/percent: 수율"
TAB_LABELS = (TAB_CONVERSION, TAB_PKG_PLAN, TAB_YIELD)
# 알림이 「그 화면으로」 로 열 탭 이름(아이콘 없이 — 탭 단추 글의 끝과 맞댄다). 붙여넣기 창 · 적용
# 알림이 부르는 표 이름도 이 이름이다 — 내부 표 이름은 양식 파일 이름에만 남는다(UI-CON-02).
CONVERSION_TAB_NAME = "환산"
PKG_PLAN_TAB_NAME = "PKG PLAN"
YIELD_TAB_NAME = "수율"
# 그 알림(`ST-05` · `ST-06`)의 Alarm 줄 표 이름 — 조건의 내역이라 본문 접힘에 두지 않는다(2026-11-05
# 사용자 요청(검수표), 설계 규칙 UI-TXT-04). 둘 다 크기와 상관없이 Alarm 에서 본다 — 상한을 넘으면
# 앞부분만 싣고 전체는 그 탭(환산 · 수율) 맨 아래 이 CSV 단추 하나다(알림 글이 그 자리를 부른다).
EXCLUDED_PLAN_TITLE = "제외한 계획"
EXCLUDED_PLAN_CSV_LABEL = "제외한 계획 전체 CSV 다운로드"
LOCKED_YIELD_TITLE = "편집 불가 수율 행"
LOCKED_YIELD_CSV_LABEL = "편집 불가 수율 행 전체 CSV 다운로드"
LOCKED_YIELD_FILE_NAME = "Capa_Locked_Yield_Rows.csv"
LOCKED_YIELD_COLUMNS = [*YIELD_KEYS, *YIELD_VALUE_COLUMNS, YIELD_LOCK_REASON_COLUMN]
# 그 표의 까닭 칸(`누락 기준정보` · `사유`) 머리 풍선 — 고칠 곳과 계산에서 어떻게 되는지. 건수는
# 알림이 말하고(자리에 경고 상자를 그리지 않는다 — 2026-11-03 결정 보드 D2 (나)), 설명 문장을 늘
# 띄우지 않는다(설계 규칙 UI-TXT-01 · 02 — 풍선 · Guide 로 옮긴 말).
EXCLUDED_PLAN_GUIDE = (
    "기준정보(수율·Chip 구성 등)가 없어 계산에서 제외한 계획은 그 기준정보를 채우면 환산과 "
    "소요대수에 반영됩니다. 생산수량이 빈 계획은 계획 없음(0)으로 봤습니다."
)
LOCKED_YIELD_GUIDE = (
    "원천 수율 값이 비었거나 0 이하·100% 초과인 행은 표에서 값을 뺐습니다(편집 불가 — 그 달 칸이 "
    "빈칸으로 보입니다). 값이 빈 행은 환산에서 빠지고, 0 이하·100% 초과 행은 Chip·Wafer 환산과 "
    "HOME·소요대수·확보율 계산을 멈춥니다. 그 달 칸에 EDS·BE 를 모두 넣어 적용하면 고쳐집니다 — "
    "비워 두면 원본 그대로 남습니다."
)
conversion_tab, pkg_plan_tab, yield_tab = stateful_tabs(TAB_LABELS, key=TAB_KEY)


def _plan_content_key() -> str:
    """PKG PLAN 그리드 양식의 내용 지문 — 시나리오 내용 · 편집 기간에, 붙여넣기 대기 표가 원본이면
    그 표 지문을 더한다(같은 시나리오에서 다른 표를 붙여넣으면 껍데기가 바뀌어야 한다)."""
    content = "/".join(str(part) for part in edit_table_key)
    if isinstance(staged_plan_table, pd.DataFrame):
        content += f"|staged:{frame_digest(staged_plan_table)}"
    return content


def _plan_grid_table() -> plan_grid.PlanGrid:
    return plan_grid.build(
        PLAN_TABLE,
        PKG_PLAN_TAB_NAME,
        plan_grid.zero_as_blank(plan_editor_source, PLAN_EDITOR_DIMENSIONS),
        PLAN_EDITOR_DIMENSIONS,
        content_key=_plan_content_key(),
        order_digest=display_order_key,
    )


def _yield_grid_table(table: pd.DataFrame) -> plan_grid.PlanGrid:
    return plan_grid.build(
        YIELD_TABLE,
        YIELD_TAB_NAME,
        table,
        YIELD_EDITOR_DIMENSIONS,
        content_key="/".join(str(part) for part in edit_table_key),
        order_digest=display_order_key,
    )


# 그리드는 **열린 탭과 inbox 에 op 가 쌓인 표만** 양식을 싣는다 — 한 번도 연 적 없는 탭은 그리드를
# 세우지 않고(`plan_grid.mounted`), 연 적 있는 탭이 닫히면 앞서 보낸 껍데기를 그대로 다시 보내
# 마운트만 남긴다(`plan_grid.render_grid`). 원본을 본 **뒤** 반영해야 버린 초안에 옛 op 가 붙지
# 않는다. 탭을 바꾸기 직전에 보낸 편집도 그 표 초안에 쓴다.
_grid_inbox = plan_grid.inbox_tables()
_grid_mounted = plan_grid.mounted(
    table
    for table, tab in ((PLAN_TABLE, pkg_plan_tab), (YIELD_TABLE, yield_tab))
    if not tab_is_hidden(tab)
)
plan_table: plan_grid.PlanGrid | None = None
if not tab_is_hidden(pkg_plan_tab) or PLAN_TABLE in _grid_inbox:
    plan_table = _plan_grid_table()
yield_table: plan_grid.PlanGrid | None = None
if default_yield_table is not None and (not tab_is_hidden(yield_tab) or YIELD_TABLE in _grid_inbox):
    yield_table = _yield_grid_table(default_yield_table)
if plan_grid.apply_inbox({PLAN_TABLE: plan_table, YIELD_TABLE: yield_table}):
    # 반영이 어느 표의 초안 칸을 비웠다(Ctrl+Z 로 0칸 · 초안 없던 표의 첫 op 가 아무것도 바꾸지
    # 않음). 화면 탭 점 · 변경 칩은 `app.py` 가 이 본문보다 먼저 옛 칸으로 그렸다 — 한 번 다시 돈다.
    st.rerun()
# 적용하지 않은 편집이나 붙여넣고 아직 적용하지 않은 표가 남은 탭에 점을 찍는다(개선안 C). 다른
# 탭으로 옮겨도 「저 탭에 아직 적용할 것이 있다」가 보인다.
mark_pending_tabs(
    TAB_KEY,
    TAB_LABELS,
    {
        *([TAB_PKG_PLAN] if plan_grid.draft_pending(PLAN_TABLE) or plan_staged else []),
        *([TAB_YIELD] if plan_grid.draft_pending(YIELD_TABLE) else []),
    },
)


# 지금 열린 팝업. **세션에 적어 두고 그 동안 매 회차 팝업 함수를 부른다** — 버튼을 누른
# 회차에만 부르면 팝업 안에서 폼을 제출하는 회차에 팝업이 다시 그려지지 않을 수 있다. 닫기(X·
# 바깥 클릭)는 `on_dismiss` 가, 성공은 팝업 스스로 지운다.
DIALOG_KEY = f"load_conversion{PAGE_DIALOG_SUFFIX}"
PLAN_PASTE_DIALOG = "plan_paste"
YIELD_PASTE_DIALOG = "yield_paste"
VIRTUAL_PRODUCT_DIALOG = "virtual_product"


def _close_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


def _open_dialog(name: str) -> None:
    st.session_state[DIALOG_KEY] = name


def _dialog_is_open(name: str) -> bool:
    return st.session_state.get(DIALOG_KEY) == name


def _queue_done(key: str, message: str) -> None:
    """작업 줄 알림 칸 `key` 에 완료 알림을 담고 쓰기 알림 표지에도 적는다 — 적용·붙여넣기·등록이
    성공한 바로 뒤에 부른다.

    「…변경사항 적용」 을 0.3초 간격으로 두 번 누르면 둘째 누름은 적용 뒤 잠긴 단추에 닿아 버려지고,
    그 회차가 화면을 다시 그리며 앞 회차가 꺼내 그린 알림을 지웠다(2026-10-27 E2E). 표지에 적은
    알림은 그 창(`write_guard.TRAILING_PRESS_SECONDS`) 안의 회차가 다시
    그린다(`flash.render_flash`). 표지는 dict 칸이라 끊기지 않으므로 담기보다 먼저 적는다.
    """
    note_notice(notice_marks(), key, message, icon=APPLIED_ICON)
    queue_flash(key, message, icon=APPLIED_ICON)


def _render_uncounted_demand_after_apply(context: PageContext, slot: DeltaGenerator) -> None:
    """PKG PLAN 적용 알림이 서는 회차 — 소요대수에 들지 않은 수요의 상태 알림(`ST-04` — 자리에는
    그리지 않고 건수가 바뀔 때만 알림창에 뜬다). 셈 동안의 스피너는 그 알림 칸(`slot`)에 선다.

    그 달 `RQ_REQB` 경로가 없는 칸에 넣은 계획은 소요대수에 들지 않아 「다시 계산됩니다」 뒤에도
    현황 요약 수가 그대로라 「고쳤는데 안 바뀐다」 고 헷갈렸다(E2E r2 static #57, 개선 I38). 셈은
    저장·발행 검사와 같은 시나리오 전체 기간 결과(`get_full_capacity_outcome`
    — 적용으로 내용 토큰이 바뀌어 여기서 처음 계산하면 HOME·산출 결과가 그 결과를 그대로 쓴다)다.
    계산이 멈추면 그 오류는 계산 화면들이 말하므로 여기서는 말하지 않는다. 계획 쪽 건수만 싣는다
    (`plan_side_counts` — 경로 쪽 「대당 Capa 가 없어 뺀 부하 경로」 는 계획을 고치지 않아도 늘 있을
    수 있어 적용할 때마다 서는 경고가 된다).

    **PKG PLAN 편집표를 그린 뒤에 부른다.** 칸은 편집표 위에 이미 서 있고 글만 나중에 채운다 —
    그 전에 부르면 적용 직후 시나리오 전체 기간 계산(합성 표본 DB 사본의 리비전 하나에 0.5~1.4초 —
    `inspect_revision_calculations.py`, 샘플 관측)이 끝날 때까지 편집표가 서지 않아 다음 편집을
    기다리게 했다.

    셈하지 못한 회차도 이벤트 칸 한 자리를 쓴다(`alerts.flush` — 부르는 쪽의 적용 알림 없는 회차와
    같다).
    """
    scenario = context.active_scenario
    try:
        with slot, st.spinner("적용한 계획의 소요대수 반영을 확인하는 중입니다..."):
            outcome = get_full_capacity_outcome(
                (context.reference_version, str(scenario["content_token"])),
                _scenario_tables=scenario["tables"],
                _reference_tables=context.reference_tables,
            )
    except BOOTSTRAP_ERRORS:
        alerts.flush()
        return
    if outcome.error is not None or outcome.required_equipment is None:
        alerts.flush()
        return
    required = outcome.required_equipment
    alert_uncounted_demand(
        required_exclusion_counts(required),
        code="ST-04",
        scope=simulation_scope(scenario),
        scope_name=FULL_SCOPE,
        lists=plan_exclusion_lists(
            required.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR),
            required.attrs.get(UNROUTED_LOADS_ATTR),
            display_order=context.display_order,
            labels=get_process_labels(),
            file_suffix="Full_Period",
        ),
        tab=PKG_PLAN_TAB_NAME,
    )


def _clipped_table_sentence(table: alerts.AlertTable, *, tab: str, csv_label: str) -> str:
    """앞부분만 실은 표의 전문 머리 — 그 크기와 전체를 받는 단추 자리. 줄 글은 패널에서 두 줄까지만
    보이니 전문 맨 앞에 두고, 한 Alarm 에 두 탭의 줄이 함께 서므로 탭을 이름으로 부른다."""
    return (
        f"Alarm 표는 {clipped_label(table)} — 전체는 {tab} 탭 맨 아래 "
        f"{quoted(csv_label)}{direction_particle(csv_label)} 받습니다."
    )


def _report_excluded_plans(
    excluded: pd.DataFrame, *, scope: AlertScope, file_name: str
) -> alerts.AlertTable | None:
    """환산에서 빠진 계획 — 상태 알림 `ST-05` 와 그 줄의 표(까닭 `누락 기준정보` 칸). 환산 탭이 열린
    회차마다(없어도) 부른다. 표가 크면 앞부분만 싣고 전문이 그 크기와 CSV 단추 자리를 말한다 —
    단추는 부르는 쪽이 탭 맨 아래에 세운다(`table_clipped`). 빠진 계획이 없으면 None 이다."""
    blank_plans = (
        int(excluded["누락 기준정보"].eq(PLAN_QUANTITY_BLANK_REASON).sum())
        if not excluded.empty
        else 0
    )
    missing_plans = len(excluded) - blank_plans
    table = (
        None
        if excluded.empty
        else alert_table(
            excluded,
            title=EXCLUDED_PLAN_TITLE,
            file_name=file_name,
            column_help={"누락 기준정보": EXCLUDED_PLAN_GUIDE},
            clip=True,
        )
    )
    sentences = []
    if table is not None and table_clipped(table):
        sentences.append(
            _clipped_table_sentence(
                table, tab=CONVERSION_TAB_NAME, csv_label=EXCLUDED_PLAN_CSV_LABEL
            )
        )
    if missing_plans:
        sentences.append(
            f"기준정보가 없어 계산에서 제외한 계획이 {missing_plans:,}건 있습니다. "
            f"목록({alarm_table_place(EXCLUDED_PLAN_TITLE)})의 기준정보를 채우면 환산과 소요대수에 "
            "반영됩니다."
        )
    if blank_plans:
        sentences.append(f"생산수량이 빈 계획 {blank_plans:,}건은 계획 없음(0)으로 봤습니다.")
    alerts.state(
        "ST-05",
        scope=scope.scope,
        content=[missing_plans, blank_plans],
        active=not excluded.empty,
        text=f"환산에서 빠진 계획 {len(excluded):,}건 — 목록: {ALARM_ROW_PLACE}",
        full=" ".join(sentences),
        scope_label=scope.label,
        tab=CONVERSION_TAB_NAME,
        tables=[table],
    )
    return table


def _report_locked_yield_rows(
    locked: pd.DataFrame, *, scope: AlertScope | None
) -> alerts.AlertTable | None:
    """원천 값이 비었거나 범위 밖이라 수율 표에서 값을 뺀 행 — 상태 알림(`ST-06`)과 그 줄의 표(까닭
    `사유` 칸). 표가 크면 앞부분만 싣고 전문이 그 크기와 CSV 단추 자리를 말한다 — 단추는 부르는 쪽이
    탭 맨 아래에 세운다(`table_clipped`). 뺀 행이 없거나 탭이 닫혔으면 None 이다.

    말없이 빼면 그 달 칸이 원천에 행이 없는 달과 똑같이 빈칸으로 보인다. 목록에는 까닭(`사유`)을
    함께 싣는다. 계산에서 두 경우는 다르다 — 값 없는 행은 환산의 「제외한 계획」으로 내려가고,
    0 이하·100% 초과 행은 Chip·Wafer 환산과 HOME·소요대수·확보율을 멈춘다(2026-09-28 사용자
    결정). 예전 문구는 둘 다 원본대로 남는다고만 해 계산이 서는 것을 알리지 않았다(2026-09-29 리뷰).
    고칠 곳은 `사유` 칸 머리 풍선 · 알림 전문 · Guide 가 말한다. 알림은 수율 탭이 열린 회차에만
    낸다(`scope` 가 None 이면 닫힌 탭 — 설계 2-3 「숨은 자리는 세지 않는다」). 닫힌 회차도 이벤트 칸
    한 자리를 써(`alerts.flush`) 바로 뒤 수율 붙여넣기 팝업의 자리가 탭에 따라 밀리지 않는다.
    """
    if scope is None:
        alerts.flush()
        return None
    table = (
        None
        if locked.empty
        else alert_table(
            locked[LOCKED_YIELD_COLUMNS],
            title=LOCKED_YIELD_TITLE,
            file_name=LOCKED_YIELD_FILE_NAME,
            column_help={YIELD_LOCK_REASON_COLUMN: LOCKED_YIELD_GUIDE},
            clip=True,
        )
    )
    sentences = []
    if table is not None and table_clipped(table):
        sentences.append(
            _clipped_table_sentence(table, tab=YIELD_TAB_NAME, csv_label=LOCKED_YIELD_CSV_LABEL)
        )
    sentences.append(
        f"원천 수율 행 {len(locked):,}개(목록: {alarm_table_place(LOCKED_YIELD_TITLE)}) — "
        f"{LOCKED_YIELD_GUIDE}"
    )
    alerts.state(
        "ST-06",
        scope=scope.scope,
        content=len(locked),
        active=not locked.empty,
        text=(
            f"수율 표에서 값을 뺀 원천 행 {len(locked):,}개 — 그 달 EDS·BE 를 넣어 적용하면 고쳐짐"
        ),
        full=" ".join(sentences),
        scope_label=scope.label,
        tab=YIELD_TAB_NAME,
        tables=[table],
    )
    return table


@st.dialog("Excel 붙여넣기 · PKG PLAN", width="large", on_dismiss=_close_dialog)
def _plan_paste_dialog(source: pd.DataFrame, file_name: str) -> None:
    """붙여넣은 표는 PKG PLAN 탭에만 올린다. 전역 반영은 「변경사항 적용」 한 곳이다.

    붙여넣은 표가 편집 대상이 되며 표의 편집을 버린다 — 창을 연 회차에 알린다(기준 정보와 같다).
    """
    imported = render_reference_clipboard_form(
        source,
        table_name=PKG_PLAN_TAB_NAME,
        key_columns=PLAN_EDITOR_DIMENSIONS,
        file_name=file_name,
        key=PLAN_PASTE_KEY,
        opening=PASTE_DROPS_EDITS_NOTICE if plan_grid.draft_pending(PLAN_TABLE) else None,
        apply_label=PLAN_PASTE_APPLY_LABEL,
    )
    if imported is None:
        return
    try:
        plan_from_edit_table(imported)
    except ValueError as exc:
        refuse_paste(PLAN_PASTE_KEY, bootstrap_error_message(exc))
        return
    st.session_state[PLAN_STAGED_KEY] = imported
    # 붙여넣은 표가 그리드의 새 원본이다 — 앞 원본에 붙은 초안 · 이력은 버린다(누름 직전에 보낸 op
    # 도 알림 없이).
    plan_grid.discard(PLAN_TABLE)
    _queue_done(
        PLAN_PASTE_FLASH_KEY,
        "붙여넣기 표를 PKG PLAN 탭에 올렸습니다. "
        "확인 후 「변경사항 적용」을 눌러야 전역 계획값에 반영됩니다.",
    )
    _close_dialog()
    st.rerun()


def _discard_plan_edits() -> None:
    plan_grid.discard(PLAN_TABLE)
    st.session_state.pop(PLAN_STAGED_KEY, None)


def _apply_yield(table: pd.DataFrame, origin: str, *, note: str = "") -> None:
    """수율 편집값이나 붙여넣은 표를 활성 시나리오에 바로 적용한다(수율은 대기 칸이 없다).

    표에서 뺀 「편집 불가」 행은 여기서 원본 그대로 되붙인다 — 편집표와 붙여넣기가 모두 이
    길을 지난다. 되붙이지 않으면 기간 교체가 그 행을 지운다.
    """
    apply_month_updates(
        active_scenario,
        {"RQ_YLD": restore_locked_yield_rows(yield_from_edit_table(table), locked_yield_rows)},
        effective_start_month,
        effective_end_month,
    )
    _queue_done(
        YIELD_FLASH_KEY,
        f"{YIELD_TAB_NAME} {origin} 활성 시나리오에 적용했습니다.{note} "
        "리비전으로 남기려면 사이드바 시나리오 칸 → 「신규 리비전 저장」을 누르세요.",
    )
    mark_own_change(OWN_CHANGE_KEY, plan_grid.own_keys(YIELD_TABLE))


def _removed_yield_note(source: pd.DataFrame, applied: pd.DataFrame) -> str:
    """양식에는 값이 있는데 적용하는 표에서는 빈 칸 수를 완료 문구 꼬리로. 없으면 빈 문자열.

    한 (키, 월)의 EDS·BE 를 둘 다 비우면 그 달 수율 행이 지워지고 그 계획은 환산·소요대수에서
    빠진다. 붙여넣기는 적용 전에 변경 수를 보여 주지 않고, 그리드는 적용 전 변경 수가 「지운 칸」을
    따로 세지 않는다. 그래서 두 길이 같은 문구로 적용 뒤에 말한다 — 한쪽만 알리면 같은 일이 길에
    따라 말없이 지나간다.
    """
    removed = count_removed_values(source, applied, YIELD_EDITOR_DIMENSIONS)
    if not removed:
        return ""
    return (
        f" {removed:,}칸을 비워 그 달 수율 행을 지웠습니다 — 해당 계획은 환산에서 빠집니다"
        "(소요대수에서도 빠져 산출 결과 → 소요대수 탭을 열면 Alarm 이 건수와 목록을 알립니다)."
    )


@st.dialog("Excel 붙여넣기 · 수율", width="large", on_dismiss=_close_dialog)
def _yield_paste_dialog(source: pd.DataFrame, file_name: str) -> None:
    # 붙여넣기는 곧바로 적용되어 수율 표를 새로 세운다 — 표의 편집은 버려진다(창을 연 회차에
    # 알린다).
    imported = render_reference_clipboard_form(
        source,
        table_name=YIELD_TAB_NAME,
        key_columns=YIELD_EDITOR_DIMENSIONS,
        file_name=file_name,
        key=YIELD_PASTE_KEY,
        opening=PASTE_DROPS_EDITS_NOTICE if plan_grid.draft_pending(YIELD_TABLE) else None,
    )
    if imported is None:
        return
    try:
        _apply_yield(imported, "붙여넣기 데이터를", note=_removed_yield_note(source, imported))
    except ValueError as exc:
        refuse_paste(YIELD_PASTE_KEY, bootstrap_error_message(exc))
        return
    _close_dialog()
    st.rerun()


@st.dialog("가상 제품 등록", width="medium", on_dismiss=_close_dialog)
def _virtual_product_dialog(scenario: ActiveScenario) -> None:
    """기존 제품의 기준정보를 새 제품 키로 복제한다. 계획은 0 으로 시작한다."""
    source_candidates = available_source_products(scenario["tables"])
    if source_candidates.empty:
        st.caption(
            "복제할 수 있는 제품이 없습니다.",
            help="기준정보가 완결된 제품이 하나는 있어야 복제할 수 있습니다.",
        )
        return
    source_labels = [
        f"{row['제품정보']} · {row['Stack']}" for _, row in source_candidates.iterrows()
    ]
    # 등록하면 시나리오가 바뀌어 붙여넣고 아직 적용하지 않은 PKG PLAN 표는 행 구성이 맞지 않아
    # 버린다(그대로 적용하면 새 제품의 0 계획 행을 기간에서 지운다). 버리기 전에 말한다.
    staged_paste = isinstance(st.session_state.get(PLAN_STAGED_KEY), pd.DataFrame)
    # 두 표에 행이 더해지므로 표에서 고치고 적용하지 않은 편집도 버려진다(2026-09-29 2차 리뷰).
    dropped_edits = {
        name: cells
        for table, name in ((PLAN_TABLE, PKG_PLAN_TAB_NAME), (YIELD_TABLE, YIELD_TAB_NAME))
        if (cells := plan_grid.counts(table)[0])
    }
    pasted_cells = (
        count_plan_value_changes(default_plan_table, st.session_state[PLAN_STAGED_KEY])
        if staged_paste
        else 0
    )
    dropped = {
        **dropped_edits,
        **({STAGED_NAMES[PLAN_STAGED_KEY]: pasted_cells} if pasted_cells else {}),
    }
    if dropped:
        st.caption(f"적용 안 한 편집 {sum(dropped.values()):,}개 버림 · {' · '.join(dropped)}")

    # 기준 제품은 폼 밖이다 — 폼 안 칸은 제출 때까지 서버에 오지 않아 제품을 바꿔도 Stack 칸이 첫
    # 제품 값으로 남고, 그대로 누르면 기준과 다른 Stack 으로 등록됐다.
    selected_source = st.selectbox(
        "기준이 될 제품",
        options=range(len(source_labels)),
        format_func=lambda index: source_labels[index],
        key=VIRTUAL_SOURCE_KEY,
    )
    with st.form("virtual_product_form", border=False):
        with st.container(horizontal=True, gap="small"):
            new_product = st.text_input("제품정보", key="virtual_product_name")
            # Stack 칸은 기준 제품마다 다른 위젯이다. 같은 칸에 세션으로 값을 써 넣으면 화면만
            # 바뀌고 브라우저 폼이 들고 있던 미제출 값이 그대로 제출돼, 보이는 값과 등록 값이
            # 어긋난다.
            new_stack = st.text_input(
                "Stack",
                value=str(source_candidates.iloc[selected_source]["Stack"]),
                key=f"{VIRTUAL_STACK_KEY}_{selected_source}",
            )
        registered = st.form_submit_button(
            "가상 제품 등록",
            icon=":material/library_add:",
            type="primary",
            help=VIRTUAL_DROP_HELP if dropped else None,
        )
    registered_records = session_virtual_products()
    if registered_records:
        st.markdown("**이 세션에서 등록한 가상 제품**")
        st.dataframe(
            records_to_frame(cast(tuple[VirtualProductRecord, ...], registered_records)),
            hide_index=True,
            width="stretch",
        )
    if not registered:
        return
    source_row = source_candidates.iloc[selected_source]
    try:
        request = VirtualProductRequest(
            source_product=str(source_row["제품정보"]),
            source_stack=str(source_row["Stack"]),
            product=new_product,
            stack=new_stack,
        )
        updates = clone_product(scenario["tables"], request)
    except ValueError as exc:
        st.error(bootstrap_error_message(exc))
        return
    apply_table_updates(scenario, updates)
    remember_virtual_product(VirtualProductRecord.from_request(request))
    # 복제는 계획·수율 두 표에 행을 더한다 — 두 그리드 초안과 붙여넣기 대기를 비운다.
    mark_own_change(
        OWN_CHANGE_KEY,
        (*plan_grid.own_keys(PLAN_TABLE), *plan_grid.own_keys(YIELD_TABLE), PLAN_STAGED_KEY),
    )
    # 복제된 계획은 원본의 달을 따른다. 그 달이 모두 조회기간 밖이면 새 제품은 PKG PLAN 표에
    # 행이 없어 「아래 표에서 입력」이 거짓이 된다(2026-09-29 횡전개 감사). 기간 달을 0 행으로
    # 채워 주지 않는 것은 그 달의 수율 기준이 없어 넣은 수량이 환산에서 빠지기 때문이다.
    plan_months = cloned_plan_months(updates, request)
    shown_months = ", ".join(str(month) for month in plan_months[:6]) + (
        f" 외 {len(plan_months) - 6}개월" if len(plan_months) > 6 else ""
    )
    plan_row_hint = (
        " 아래 표에서 계획 수량을 입력하세요."
        if any(effective_start_month <= month <= effective_end_month for month in plan_months)
        else (
            " 복제된 계획이 모두 조회기간 밖이라 지금 PKG PLAN 표에는 없습니다 — 조회기간을 "
            f"넓혀야 PKG PLAN 표에 나타납니다(복제된 계획 달: {shown_months or '없음'})."
        )
    )
    # 알림은 다음 회차에 `st.success`(마크다운)로 그린다 — 사람이 적은 제품정보·Stack 은 막아
    # 싣는다(「HBM4~시제~」 의 물결표가 지움선, `*1*` 이 기울임이 되지 않게).
    normalized = request.normalized()
    _queue_done(
        PRODUCT_REGISTERED_FLASH_KEY,
        f"가상 제품 {literal_markdown(normalized.product)} · "
        f"{with_object_particle(literal_markdown(normalized.stack))} "
        f"등록했습니다. 기준정보 {len(updates)}종을 복제했습니다."
        + plan_row_hint
        + (" 적용하지 않았던 붙여넣기 표는 버렸습니다 — 다시 붙여넣으세요." if staged_paste else "")
        + (
            f" 적용하지 않았던 {'·'.join(dropped_edits)} 표 편집도 버렸습니다."
            if dropped_edits
            else ""
        ),
    )
    _close_dialog()
    st.rerun()


def _open_plan_paste() -> None:
    _open_dialog(PLAN_PASTE_DIALOG)


def _open_virtual_product() -> None:
    _open_dialog(VIRTUAL_PRODUCT_DIALOG)


def _open_yield_paste() -> None:
    _open_dialog(YIELD_PASTE_DIALOG)


def _discard_yield_edits() -> None:
    plan_grid.discard(YIELD_TABLE)


# 여는 단추는 **콜백**으로 연다. 콜백은 스크립트보다 먼저 돌아 열린 팝업이 회차 시작부터 하나로
# 정해진다 — 단추 값으로 열면 앞 탭의 팝업을 그린 뒤 뒤 탭의 팝업을 또 그려 Streamlit 이 「팝업은 한
# 번에 하나」로 멈춘다(테스트로 재현).
PLAN_APPLY_BUTTON = plan_grid.Button("변경사항 적용", ":material/check:", "apply_pkg_plan_changes")
PLAN_PASTE_BUTTON = plan_grid.Button(
    "Excel 붙여넣기", ":material/content_paste:", "open_plan_paste", _open_plan_paste
)
VIRTUAL_PRODUCT_BUTTON = plan_grid.Button(
    "가상 제품 등록", ":material/library_add:", "open_virtual_product", _open_virtual_product
)
YIELD_APPLY_BUTTON = plan_grid.Button(
    "수율 변경사항 적용", ":material/check:", "apply_yield_changes"
)
YIELD_PASTE_BUTTON = plan_grid.Button(
    "Excel 붙여넣기", ":material/content_paste:", "open_yield_paste", _open_yield_paste
)

with pkg_plan_tab:
    # 작업 줄 칸 → 그리드 칸. 둘 다 **늘 서 있는 칸**이라 안의 칸 수가 바뀌어도 그리드 마운트의 앞
    # 형제 순번이 밀리지 않는다(밀리면 다시 마운트되어 보내지 않은 출납을 잃는다). 기준 창에서는 표
    # 도구 막대가 단추 줄 곁에 함께 선다(`plan_grid.LAYOUTS`).
    plan_layout = plan_grid.LAYOUTS[PLAN_TABLE]
    plan_actions_box = st.container(key=plan_layout.actions_box)
    plan_grid_box = st.container(key=plan_layout.grid_box)
    # 적용 알림이 서는 회차(담아 둔 알림, 또는 쓰기 직후 창 안에서 다시 그리는 알림)에는 같은 칸
    # 맨 아래에 소요대수에 들지 않은 수요도 적는다 — 칸 안이라 그리드 자리가 밀리지 않는다. 그
    # 셈(시나리오 전체 기간 계산)은 그리드를 그린 **뒤**에 한다(아래) — 앞에서 하면 적용 직후 그
    # 계산이 끝날 때까지 그리드가 서지 않는다.
    applied_notice_shown = (
        pending_flash(PLAN_APPLIED_FLASH_KEY) is not None
        or held_flash(PLAN_APPLIED_FLASH_KEY) is not None
    )
    with plan_actions_box:
        # 고친 칸도 붙여넣기 대기도 없으면 「변경사항 적용」 을 잠근다(같은 값으로 리비전만 올라
        # `미저장 변경` 이 켜진다). 「편집 취소」 는 적용하지 않은 편집과 붙여넣기 대기분을 함께
        # 버린다 — 사이드바 「편집 되돌리기」는 **적용한** 변경이 있을 때만 서서 붙여넣기만 해 둔
        # 표는 버릴 길이 없었다(2026-09-29 2차 리뷰). 적용 · 붙여넣기 · 등록 알림과 적용이 막힌
        # 까닭은 단추 줄 바로 아래다.
        plan_actions = plan_grid.render_actions(
            PLAN_TABLE,
            apply=PLAN_APPLY_BUTTON,
            apply_help=PLAN_APPLY_HELP,
            locked_help=APPLY_LOCKED_HELP,
            paste=PLAN_PASTE_BUTTON,
            more=(VIRTUAL_PRODUCT_BUTTON,),
            more_key="pkg_plan_more",
            discard_help="PKG PLAN 표에서 적용하지 않은 편집과 붙여넣기 대기분을 버립니다.",
            discard_click=_discard_plan_edits,
            discard_key="discard_pkg_plan_edits",
            staged=plan_staged,
            flash_keys=(PLAN_APPLIED_FLASH_KEY, PLAN_PASTE_FLASH_KEY, PRODUCT_REGISTERED_FLASH_KEY),
        )
    if _dialog_is_open(PLAN_PASTE_DIALOG):
        _plan_paste_dialog(
            plan_editor_source,
            f"RQ_PKG_PLAN_{effective_start_month}_{effective_end_month}.csv",
        )
    elif _dialog_is_open(VIRTUAL_PRODUCT_DIALOG):
        _virtual_product_dialog(active_scenario)
    if PLAN_TABLE in _grid_mounted:
        with plan_grid_box:
            plan_grid.render_grid(PLAN_TABLE, plan_table, hidden=tab_is_hidden(pkg_plan_tab))
    # 적용 알림 칸(위)이 서는 회차의 소요대수에 들지 않은 수요 — 그리드를 다 그린 뒤에 센다. 적용
    # 알림이 없는 회차에도 이 자리에서 이벤트 칸 한 자리를 쓴다 — 뒤 수율 붙여넣기 팝업의 이벤트 칸
    # 자리가 회차마다 같게(AGENTS 9장 「알림 칸」 — 표지를 쓰는 함수는 늘 같은 자리에서 한 자리).
    if applied_notice_shown:
        _render_uncounted_demand_after_apply(context, plan_actions.notice)
    else:
        alerts.flush()

simulation_plan = filtered_plan

apply_yield = False
with yield_tab:
    yield_layout = plan_grid.LAYOUTS[YIELD_TABLE]
    yield_actions_box = st.container(key=yield_layout.actions_box)
    yield_grid_box = st.container(key=yield_layout.grid_box)
    if default_yield_table is None:
        # 표를 세울 수 없는 원천(연결 키 결측·중복 등)이면 이 탭만 멈춘다. 붙여넣기 양식도 이
        # 표라 팝업을 열 수 없다 — 열려 있던 기억은 지워 원천을 고친 뒤 저절로 뜨지 않게 한다.
        # 그리드 마운트는 표 없는 껍데기로 같은 자리에 남는다.
        if _dialog_is_open(YIELD_PASTE_DIALOG):
            _close_dialog()
        yield_stop_message = (
            f"수율 표를 만들지 못했습니다: {yield_build_error} 원천 RQ_YLD 를 고치기 전까지 이 "
            "탭만 멈춥니다 — PKG PLAN 편집과 가상 제품 등록은 그대로 쓸 수 있습니다."
        )
        with yield_actions_box:
            render_data_error(yield_stop_message, code="ST-20", tab=YIELD_TAB_NAME)
        locked_table = None
    else:
        with yield_actions_box:
            yield_actions = plan_grid.render_actions(
                YIELD_TABLE,
                apply=YIELD_APPLY_BUTTON,
                apply_help=YIELD_APPLY_HELP,
                locked_help=APPLY_LOCKED_HELP,
                paste=YIELD_PASTE_BUTTON,
                discard_help="수율 표에서 적용하지 않은 편집을 버립니다.",
                discard_click=_discard_yield_edits,
                discard_key="discard_yield_edits",
                flash_keys=(YIELD_FLASH_KEY,),
            )
        apply_yield = yield_actions.submitted
        locked_table = _report_locked_yield_rows(
            locked_yield_rows,
            scope=(
                None
                if tab_is_hidden(yield_tab)
                else simulation_scope(active_scenario, (effective_start_month, effective_end_month))
            ),
        )
        if _dialog_is_open(YIELD_PASTE_DIALOG):
            _yield_paste_dialog(
                default_yield_table,
                f"RQ_YLD_{effective_start_month}_{effective_end_month}.csv",
            )
    if YIELD_TABLE in _grid_mounted:
        with yield_grid_box:
            plan_grid.render_grid(YIELD_TABLE, yield_table, hidden=tab_is_hidden(yield_tab))
    # 원본·줄 차례가 바뀌어 편집을 버린 회차에는 단추가 잠겨 그려지고, Streamlit 은 잠겨 그린 단추의
    # 클릭을 서버에서 버린다 — 그 회차에 함께 온 클릭은 여기까지 오지 않는다. 칸 오류가 남았으면
    # 고칠 칸을 알리고 멈춘다(업무 규칙 검사 전에).
    if apply_yield and default_yield_table is not None:
        # 닫힌 탭의 단추가 눌린 회차(탭을 바꾸는 사이)에도 적용은 그 표 양식으로 한다.
        if yield_table is None:
            yield_table = _yield_grid_table(default_yield_table)
        yield_blocked = plan_grid.error_notice(yield_table)
        if yield_blocked is not None:
            yield_actions.notice.error(yield_blocked, icon=":material/error:")
        else:
            try:
                edited_yield_table = plan_grid.merged(yield_table)
                _apply_yield(
                    edited_yield_table,
                    "편집값을",
                    note=_removed_yield_note(default_yield_table, edited_yield_table),
                )
            except ValueError as exc:
                yield_actions.notice.error(bootstrap_error_message(exc))
            else:
                st.rerun()
    if locked_table is not None and table_clipped(locked_table):
        render_csv_download(
            data=locked_yield_rows[LOCKED_YIELD_COLUMNS].to_csv(index=False).encode("utf-8-sig"),
            file_name=LOCKED_YIELD_FILE_NAME,
            key="download_locked_yield_csv",
            label=LOCKED_YIELD_CSV_LABEL,
        )

# PKG PLAN 적용은 **두 탭을 모두 그린 뒤**에 한다. 적용은 `st.rerun()` 으로 끝나는데, Streamlit 은
# 그것을 정상 완료로 보고 그 회차에 그리지 않은 위젯의 상태를 서버에서 지운다 — 수율 그리드의 출납
# 상태가 그 회차에 그려진 뒤여야 한다. 칸 오류가 남았으면 고칠 칸을 알리고 멈춘다(업무 규칙 검사
# 전에). 오류 알림은 작업 줄 아래 자리(`plan_actions.notice`)에 쓰므로 여기서 처리해도 누른 자리에
# 뜬다. 편집을 버린 회차의 클릭은 잠겨 그린 단추라 Streamlit 이 버린다(수율과 같다).
if plan_actions.submitted:
    if plan_table is None:
        plan_table = _plan_grid_table()
    plan_blocked = plan_grid.error_notice(plan_table)
    if plan_blocked is not None:
        plan_actions.notice.error(plan_blocked, icon=":material/error:")
    else:
        try:
            updated_plan = attach_plan_attributes(
                plan_from_edit_table(plan_grid.merged(plan_table)), simulation_plan
            )
            apply_month_updates(
                active_scenario,
                {"RQ_PKG_PLAN": updated_plan},
                effective_start_month,
                effective_end_month,
            )
        except ValueError as exc:
            plan_actions.notice.error(bootstrap_error_message(exc))
        else:
            _queue_done(
                PLAN_APPLIED_FLASH_KEY,
                f"PKG PLAN을 전역 계획값에 반영했습니다. "
                f"{month_label(effective_start_month)}–{month_label(effective_end_month)} "
                "구간의 환산·소요대수·확보율과 "
                f"홈 대시보드가 이 계획으로 다시 계산됩니다. "
                "리비전으로 남기려면 사이드바 시나리오 칸 → 「신규 리비전 저장」을 누르세요.",
            )
            st.session_state.pop(PLAN_STAGED_KEY, None)
            mark_own_change(OWN_CHANGE_KEY, (*plan_grid.own_keys(PLAN_TABLE), PLAN_STAGED_KEY))
            st.rerun()

simulation_yield = filtered_yield

# 환산 조건은 환산 탭이 열렸을 때만 사이드바에 선다. 다른 탭에서는 쓰지 않는 조건이라 세우면
# 「사이드바 = 이 화면의 조건」이 흐려진다. 안 그려진 회차에도 선택은 `persist_state` 가,
# 카드의 여닫힘은 `condition_card` 의 기억 칸이 지킨다. 계산도 그때만 한다 — 보이지 않는
# 표를 위해 환산을 돌릴 이유가 없다.
if not tab_is_hidden(conversion_tab):
    demand_basis_options: tuple[DemandBasis, ...] = ("PKG", "Chip", "Wafer", "Density")
    with condition_card("환산 조건", name="load_conversion"):
        demand_basis = st.selectbox(
            "소요기준",
            options=demand_basis_options,
            key="monthly_volume_basis",
            persist_state="session",
        )
        with st.container(horizontal=True, gap="medium"):
            show_detail = st.toggle(
                "상세",
                key="monthly_volume_detail",
                persist_state="session",
            )
            include_edp = st.toggle(
                "EDP",
                key="monthly_volume_edp",
                persist_state="session",
            )

    with conversion_tab:
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
            render_data_error(bootstrap_error_message(exc), code="ST-20", tab=CONVERSION_TAB_NAME)
            st.stop()

        # 기준정보가 없어 계산에서 빠진 계획 행은 조용히 사라지면 안 된다. 예전에는 여기서
        # 예외를 던져 페이지 전체가 멈췄고, 지금은 해당 제품만 빼고 목록으로 알린다 — 건수는 상태
        # 알림(`ST-05`, 이 탭이 열린 회차마다), 목록은 그 줄의 표다. 생산수량이 빈 행은 기준정보
        # 문제가 아니라 계획 없음(0)으로 본 것이다 — 한 문장에 섞으면 채울 기준정보가 없는데 찾으러
        # 간다.
        excluded_load_rows = load_exclusions(monthly_volume)
        excluded_file_name = (
            f"Capa_Conversion_Excluded_Plans_{effective_start_month}_{effective_end_month}.csv"
        )
        excluded_table = _report_excluded_plans(
            excluded_load_rows,
            scope=simulation_scope(active_scenario, (effective_start_month, effective_end_month)),
            file_name=excluded_file_name,
        )

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
            render_table_heading(
                "환산",
                caption=f"단위: {unit}",
                csv=conversion_csv,
                file_name=(
                    f"Capa_Conversion_{demand_basis}_{effective_start_month}_"
                    f"{effective_end_month}.csv"
                ),
                key="download_conversion_csv",
            )
            render_grouped_monthly_table(
                monthly_volume,
                classification_columns=displayed_classification_columns,
                column_labels=COLUMN_LABELS,
                decimal_places=conversion_decimal_places,
                key="conversion_volume_table",
                owner_tab=conversion_tab,
            )

        if excluded_table is not None and table_clipped(excluded_table):
            render_csv_download(
                data=excluded_load_rows.to_csv(index=False).encode("utf-8-sig"),
                file_name=excluded_file_name,
                key="download_excluded_plans_csv",
                label=EXCLUDED_PLAN_CSV_LABEL,
            )
