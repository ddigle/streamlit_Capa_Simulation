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
  이유가 없고, 사이드바 조회 조건에 두면 「사이드바 = 보는 조건」이 흐려진다.
"""

from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.editor_state import (
    discard_editor,
    editor_has_edits,
    editor_widget_key,
)
from capa_simulation.components.grouped_monthly_table import (
    build_grouped_monthly_export,
    render_grouped_monthly_table,
)
from capa_simulation.components.month_editor import PASTE_DROPS_EDITS_NOTICE
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.reference_csv_tools import (
    queue_reference_import_flash,
    render_reference_clipboard_form,
)
from capa_simulation.components.scenario_edit_bar import (
    mark_own_change,
    register_pending_edits,
    reset_editors_on_source_change,
    source_token,
)
from capa_simulation.components.tab_marks import mark_pending_tabs
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import render_table_heading
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
    apply_table_updates,
    remember_virtual_product,
    scenario_month_table,
    scenario_table,
    session_virtual_products,
)
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    YIELD_KEYS,
    YIELD_LOCK_REASON_COLUMN,
    YIELD_VALUE_COLUMNS,
    DemandBasis,
    attach_plan_attributes,
    filter_edp_plan,
    load_exclusions,
    plan_from_edit_table,
    plan_to_edit_table,
    restore_locked_yield_rows,
    split_editable_yield_rows,
    yield_from_edit_table,
    yield_to_edit_table,
)
from capa_simulation.services.reference_csv import count_removed_values
from capa_simulation.services.simulation_cache import get_monthly_volume
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    available_source_products,
    clone_product,
    cloned_plan_months,
    records_to_frame,
)
from capa_simulation.sidebar_status import condition_card

PRODUCT_COLUMN_WIDTH_PX = 100

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
    st.error(f"기준정보를 불러오지 못했습니다: {bootstrap_error_message(exc)}")
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
except ValueError as exc:
    st.error(str(exc))
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
    editable_yield, locked_yield_rows = split_editable_yield_rows(filtered_yield)
    default_yield_table = yield_to_edit_table(
        editable_yield, prepared_display_order, locked=locked_yield_rows
    )
except ValueError as exc:
    yield_build_error = str(exc)

PLAN_EDITOR_KEY = "pkg_plan_editor"
YIELD_EDITOR_KEY = "yield_editor"
SOURCE_TOKEN_KEY = "load_conversion_source_token"
# 붙여넣기 결과는 곧바로 전역에 반영하지 않고 이 키에 담아 PKG PLAN 탭에만 보여준다.
# 사용자가 "변경사항 적용" 을 눌러야 활성 시나리오로 넘어간다.
PLAN_STAGED_KEY = "pkg_plan_staged_paste"
PLAN_APPLIED_FLASH_KEY = "pkg_plan_applied_flash"
PRODUCT_REGISTERED_FLASH_KEY = "virtual_product_registered_flash"
PLAN_PASTE_KEY = "rq_pkg_plan_csv"
YIELD_PASTE_KEY = "rq_yield_csv"
# 적용 버튼 툴팁. 「적용해야 반영된다」는 동작을 좌우하는 안내라 Guide 로만 보내지 않고
# 버튼에 남긴다(2026-09-28 사용자 결정).
PLAN_APPLY_HELP = "누르면 환산·소요대수·확보율과 홈 대시보드가 이 계획으로 다시 계산됩니다."
YIELD_APPLY_HELP = "누르면 환산수량과 다른 페이지의 산출값이 이 수율로 다시 계산됩니다."
# 원본이 바뀌면 아직 적용하지 않은 붙여넣기는 행·월 구성이 맞지 않으므로 함께 버린다. 이 화면이
# 스스로 적용한 것이면(`mark_own_change`) 그 탭의 편집표만 비운다 — 수율을 적용했다고 PKG PLAN
# 에서 고치고 아직 적용하지 않은 값까지 사라지면 안 된다.
OWN_CHANGE_KEY = "load_conversion_own_change"
reset_editors_on_source_change(
    SOURCE_TOKEN_KEY,
    source_token(reference_version, active_scenario, effective_start_month, effective_end_month),
    (PLAN_EDITOR_KEY, YIELD_EDITOR_KEY),
    other_keys=(PLAN_STAGED_KEY,),
    own_change_key=OWN_CHANGE_KEY,
)
# 사이드바가 저장·불러오기 전에 「적용하지 않은 편집」을 묻도록 이 화면의 편집표와 붙여넣기
# 대기분을 알린다. 붙여넣기 대기분은 화면을 옮겨도 남는다. 방금 적용한 표는 사이드바가 빼고 센다.
register_pending_edits(
    "load_conversion.py",
    "생산 계획",
    {PLAN_EDITOR_KEY: "PKG PLAN", YIELD_EDITOR_KEY: "수율"},
    staged={PLAN_STAGED_KEY: "PKG PLAN 붙여넣기"},
    own_change_key=OWN_CHANGE_KEY,
)

# 본문은 제목 · 탭 · 탭 내용만이다. 「활성 시나리오 · 수정본 N」 줄은 없앴다 — 미저장 여부는
# 사이드바 시나리오 상자의 배지가 이미 말하고, 편집을 버리는 「편집 되돌리기」도 그 상자에
# 있다(모든 화면의 편집을 버리는 시나리오 단위 동작이다). 되돌리면 리비전 번호가 올라
# 위 `source_token` 이 바뀌므로 이 화면의 편집표·붙여넣기 대기분도 다음 회차에 함께 비워진다.
# 탭 이름 앞 아이콘은 탭이 하는 일이다 — 환산은 계산해 보는 곳, PKG PLAN·수율은 값을 고치는
# 곳이다(2026-09-29 사용자 결정, 탭 목록 개선안 B).
TAB_KEY = "load_conversion_active_tab"
TAB_CONVERSION = ":material/calculate: 환산"
TAB_PKG_PLAN = ":material/edit_calendar: PKG PLAN"
TAB_YIELD = ":material/percent: 수율"
TAB_LABELS = (TAB_CONVERSION, TAB_PKG_PLAN, TAB_YIELD)
conversion_tab, pkg_plan_tab, yield_tab = stateful_tabs(TAB_LABELS, key=TAB_KEY)
# 적용하지 않은 편집이나 붙여넣고 아직 적용하지 않은 표가 남은 탭에 점을 찍는다(개선안 C). 다른
# 탭으로 옮겨도 「저 탭에 아직 적용할 것이 있다」가 보인다.
mark_pending_tabs(
    TAB_KEY,
    TAB_LABELS,
    {
        *(
            [TAB_PKG_PLAN]
            if editor_has_edits(PLAN_EDITOR_KEY)
            or isinstance(st.session_state.get(PLAN_STAGED_KEY), pd.DataFrame)
            else []
        ),
        *([TAB_YIELD] if editor_has_edits(YIELD_EDITOR_KEY) else []),
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


def _render_flashes(*keys: str) -> None:
    """작업 줄 바로 아래에 완료 알림을 띄운다. 팝업이 남긴 알림도 여기서 뜬다."""
    for key in keys:
        message = st.session_state.pop(key, None)
        if isinstance(message, str):
            st.success(message, icon=":material/published_with_changes:")


def _render_locked_yield_rows(locked: pd.DataFrame) -> None:
    """원천 값이 비었거나 범위 밖이라 수율 표에서 값을 뺀 행을 알린다.

    말없이 빼면 그 달 칸이 원천에 행이 없는 달과 똑같이 빈칸으로 보인다. 목록에는 까닭(`사유`)을
    함께 싣는다. 계산에서 두 경우는 다르다 — 값 없는 행은 환산의 「제외한 계획」으로 내려가고,
    0 이하·100% 초과 행은 Chip·Wafer 환산과 HOME·소요대수·확보율을 멈춘다(2026-09-28 사용자
    결정). 예전 문구는 둘 다 원본대로 남는다고만 해 계산이 서는 것을 알리지 않았다(2026-09-29 리뷰).
    """
    if locked.empty:
        return
    st.warning(
        f"원천 수율 값이 비었거나 0 이하·100% 초과인 {len(locked):,}행은 표에서 값을 뺐습니다"
        "(편집 불가 — 그 달 칸이 빈칸으로 보입니다). 값이 빈 행은 환산에서 빠지고, 0 이하·100% "
        "초과 행은 Chip·Wafer 환산과 HOME·소요대수·확보율 계산을 멈춥니다. 그 달 칸에 EDS·BE 를 "
        "모두 넣어 적용하면 고쳐집니다 — 비워 두면 원본 그대로 남습니다.",
        icon=":material/lock:",
    )
    with st.expander("편집 불가 수율 행", icon=":material/rule:"):
        st.dataframe(
            locked[[*YIELD_KEYS, *YIELD_VALUE_COLUMNS, YIELD_LOCK_REASON_COLUMN]],
            hide_index=True,
            width="stretch",
        )


@st.dialog("Excel 붙여넣기 · PKG PLAN", width="large", on_dismiss=_close_dialog)
def _plan_paste_dialog(source: pd.DataFrame, file_name: str) -> None:
    """붙여넣은 표는 PKG PLAN 탭에만 올린다. 전역 반영은 「변경사항 적용」 한 곳이다."""
    # 붙여넣은 표가 편집 대상이 되며 표의 편집을 버린다. 버리기 전에 말한다(기준 정보와 같다).
    if editor_has_edits(PLAN_EDITOR_KEY):
        st.warning(PASTE_DROPS_EDITS_NOTICE)
    imported = render_reference_clipboard_form(
        source,
        table_name="RQ_PKG_PLAN",
        key_columns=PLAN_EDITOR_DIMENSIONS,
        file_name=file_name,
        key=PLAN_PASTE_KEY,
    )
    if imported is None:
        return
    try:
        plan_from_edit_table(imported)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state[PLAN_STAGED_KEY] = imported
    # 편집기 위젯이 이전 표의 편집 상태를 덮어쓰지 않도록 브라우저까지 비운다.
    discard_editor(PLAN_EDITOR_KEY)
    queue_reference_import_flash(
        PLAN_PASTE_KEY,
        "붙여넣기 표를 PKG PLAN 탭에 반영했습니다. "
        "확인 후 「PKG PLAN 변경사항 적용」을 눌러야 전역 계획값에 반영됩니다.",
    )
    _close_dialog()
    st.rerun()


def _discard_plan_edits() -> None:
    discard_editor(PLAN_EDITOR_KEY)
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
    queue_reference_import_flash(
        YIELD_PASTE_KEY,
        f"RQ_YLD {origin} 활성 시나리오에 적용했습니다.{note} "
        "리비전으로 남기려면 사이드바 「저장」 → 「신규 리비전 저장」을 누르세요.",
    )
    mark_own_change(OWN_CHANGE_KEY, (YIELD_EDITOR_KEY,))


@st.dialog("Excel 붙여넣기 · 수율", width="large", on_dismiss=_close_dialog)
def _yield_paste_dialog(source: pd.DataFrame, file_name: str) -> None:
    # 붙여넣기는 곧바로 적용되어 수율 표를 새로 세운다 — 표의 편집은 버려진다.
    if editor_has_edits(YIELD_EDITOR_KEY):
        st.warning(PASTE_DROPS_EDITS_NOTICE)
    imported = render_reference_clipboard_form(
        source,
        table_name="RQ_YLD",
        key_columns=YIELD_EDITOR_DIMENSIONS,
        file_name=file_name,
        key=YIELD_PASTE_KEY,
    )
    if imported is None:
        return
    # 한 (키, 월)의 EDS·BE 를 둘 다 비우면 그 달 수율 행이 지워지고 그 계획은 환산에서 빠진다.
    # 붙여넣기는 적용 전에 변경 수를 보여 주지 않아 말없이 지나갔다(2026-09-29 횡전개 감사).
    removed = count_removed_values(source, imported, YIELD_EDITOR_DIMENSIONS)
    note = (
        f" {removed:,}칸을 비워 그 달 수율 행을 지웠습니다 — 해당 계획은 환산에서 빠집니다."
        if removed
        else ""
    )
    try:
        _apply_yield(imported, "붙여넣기 데이터를", note=note)
    except ValueError as exc:
        st.error(str(exc))
        return
    _close_dialog()
    st.rerun()


@st.dialog("가상 제품 등록", width="medium", on_dismiss=_close_dialog)
def _virtual_product_dialog(scenario: ActiveScenario) -> None:
    """기존 제품의 기준정보를 새 제품 키로 복제한다. 계획은 0 으로 시작한다."""
    source_candidates = available_source_products(scenario["tables"])
    if source_candidates.empty:
        st.info("복제할 수 있는 제품이 없습니다. 기준정보가 완결된 제품이 하나는 있어야 합니다.")
        return
    source_labels = [
        f"{row['제품정보']} · {row['Stack']}" for _, row in source_candidates.iterrows()
    ]
    # 등록하면 시나리오가 바뀌어 붙여넣고 아직 적용하지 않은 PKG PLAN 표는 행 구성이 맞지 않아
    # 버린다(그대로 적용하면 새 제품의 0 계획 행을 기간에서 지운다). 버리기 전에 말한다.
    staged_paste = isinstance(st.session_state.get(PLAN_STAGED_KEY), pd.DataFrame)
    if staged_paste:
        st.warning(
            "적용하지 않은 PKG PLAN 붙여넣기가 있습니다. 등록하면 버려집니다 — 먼저 "
            "「PKG PLAN 변경사항 적용」을 누르거나, 등록한 뒤 다시 붙여넣으세요."
        )
    # 두 표에 행이 더해지므로 표에서 고치고 적용하지 않은 편집도 버려진다(2026-09-29 2차 리뷰).
    dropped_edits = [
        name
        for key, name in ((PLAN_EDITOR_KEY, "PKG PLAN"), (YIELD_EDITOR_KEY, "수율"))
        if editor_has_edits(key)
    ]
    if dropped_edits:
        st.warning(
            f"{'·'.join(dropped_edits)} 표에 적용하지 않은 편집이 있습니다. 등록하면 버려집니다 "
            "— 먼저 그 표의 「변경사항 적용」을 누르세요."
        )
    with st.form("virtual_product_form", border=False):
        selected_source = st.selectbox(
            "기준이 될 제품",
            options=range(len(source_labels)),
            format_func=lambda index: source_labels[index],
            key="virtual_product_source",
        )
        with st.container(horizontal=True, gap="small"):
            new_product = st.text_input("제품정보", key="virtual_product_name")
            new_stack = st.text_input(
                "Stack",
                value=str(source_candidates.iloc[selected_source]["Stack"]),
                key="virtual_product_stack",
            )
        registered = st.form_submit_button(
            "가상 제품 등록", icon=":material/library_add:", type="primary"
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
        st.error(str(exc))
        return
    apply_table_updates(scenario, updates)
    remember_virtual_product(VirtualProductRecord.from_request(request))
    # 복제는 계획·수율 두 표에 행을 더한다 — 두 편집표와 붙여넣기 대기를 비운다.
    mark_own_change(OWN_CHANGE_KEY, (PLAN_EDITOR_KEY, YIELD_EDITOR_KEY, PLAN_STAGED_KEY))
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
    st.session_state[PRODUCT_REGISTERED_FLASH_KEY] = (
        f"가상 제품 {request.normalized().product} · {request.normalized().stack} 을 "
        f"등록했습니다. 기준정보 {len(updates)}종을 복제했습니다."
        + plan_row_hint
        + (" 적용하지 않았던 붙여넣기 표는 버렸습니다 — 다시 붙여넣으세요." if staged_paste else "")
        + (
            f" 적용하지 않았던 {'·'.join(dropped_edits)} 표 편집도 버렸습니다."
            if dropped_edits
            else ""
        )
    )
    _close_dialog()
    st.rerun()


with pkg_plan_tab:
    # 붙여넣기한 표가 있으면 그것을 편집 대상으로 보여준다. 아직 전역에는 반영되지 않았다.
    staged_plan_table = st.session_state.get(PLAN_STAGED_KEY)
    if isinstance(staged_plan_table, pd.DataFrame) and not set(PLAN_EDITOR_DIMENSIONS).issubset(
        staged_plan_table.columns
    ):
        # `source_token` 은 원본의 버전·기간만 보고 격자 스키마는 보지 않는다. 그래서 행
        # 차원이 늘어난 뒤에도(예: `Pack Code` 업무 키 승격) 옛 스키마로 붙여넣어 둔 표가
        # 세션에 남아 편집 원본이 되고, 아래 `set_properties` 가 `KeyError` 로 죽는다.
        st.session_state.pop(PLAN_STAGED_KEY, None)
        staged_plan_table = None
    plan_editor_source = (
        staged_plan_table if isinstance(staged_plan_table, pd.DataFrame) else default_plan_table
    )
    # 작업 줄은 표 **위**다. 버튼 값은 표보다 먼저 만들어도 누른 회차에 표의 편집값이 그대로
    # 들어온다(편집값은 위젯 상태라 그리는 차례와 상관없다).
    plan_pending = editor_has_edits(PLAN_EDITOR_KEY) or isinstance(staged_plan_table, pd.DataFrame)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        # 고친 것이 없으면 누를 수 없다. 같은 값으로 리비전만 올라 `미저장 변경` 이 켜진다.
        apply_plan = st.button(
            "PKG PLAN 변경사항 적용",
            icon=":material/check:",
            key="apply_pkg_plan_changes",
            type="primary",
            help=PLAN_APPLY_HELP,
            disabled=not plan_pending,
        )
        # 여는 버튼은 **콜백**으로 연다. 콜백은 스크립트보다 먼저 돌아 열린 팝업이 회차 시작부터
        # 하나로 정해진다 — 버튼 값으로 열면 앞 탭의 팝업을 그린 뒤 뒤 탭의 팝업을 또 그려
        # Streamlit 이 「팝업은 한 번에 하나」로 멈춘다(테스트로 재현).
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key="open_plan_paste",
            on_click=_open_dialog,
            args=(PLAN_PASTE_DIALOG,),
        )
        st.button(
            "가상 제품 등록",
            icon=":material/library_add:",
            key="open_virtual_product",
            on_click=_open_dialog,
            args=(VIRTUAL_PRODUCT_DIALOG,),
        )
        # 적용하지 않은 편집·붙여넣기 대기분을 버리는 자리. 사이드바 「편집 되돌리기」는 **적용한**
        # 변경이 있을 때만 서서, 붙여넣기만 해 둔 표는 버릴 길이 없었다(2026-09-29 2차 리뷰).
        if plan_pending:
            st.button(
                "편집 취소",
                icon=":material/undo:",
                key="discard_pkg_plan_edits",
                on_click=_discard_plan_edits,
                help="PKG PLAN 표에서 적용하지 않은 편집과 붙여넣기 대기분을 버립니다.",
            )
    # 적용이 막힌 까닭도 작업 줄 바로 아래다 — 적용 처리는 표 뒤에서 돌지만 알림은 여기 선다.
    plan_notice = st.empty()
    _render_flashes(PLAN_APPLIED_FLASH_KEY, f"{PLAN_PASTE_KEY}_flash", PRODUCT_REGISTERED_FLASH_KEY)
    if _dialog_is_open(PLAN_PASTE_DIALOG):
        _plan_paste_dialog(
            plan_editor_source,
            f"RQ_PKG_PLAN_{effective_start_month}_{effective_end_month}.csv",
        )
    elif _dialog_is_open(VIRTUAL_PRODUCT_DIALOG):
        _virtual_product_dialog(active_scenario)
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
        key=editor_widget_key(PLAN_EDITOR_KEY),
        hide_index=True,
        width="content",
        height=500,
        row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
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

simulation_plan = filtered_plan

with yield_tab:
    if default_yield_table is None:
        # 표를 세울 수 없는 원천(연결 키 결측·중복 등)이면 이 탭만 멈춘다. 붙여넣기 양식도 이
        # 표라 팝업을 열 수 없다 — 열려 있던 기억은 지워 원천을 고친 뒤 저절로 뜨지 않게 한다.
        if _dialog_is_open(YIELD_PASTE_DIALOG):
            _close_dialog()
        st.error(
            f"수율 표를 만들지 못했습니다: {yield_build_error} 원천 RQ_YLD 를 고치기 전까지 이 "
            "탭만 멈춥니다 — PKG PLAN 편집과 가상 제품 등록은 그대로 쓸 수 있습니다.",
            icon=":material/error:",
        )
    else:
        yield_pending = editor_has_edits(YIELD_EDITOR_KEY)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            apply_yield = st.button(
                "수율 변경사항 적용",
                icon=":material/check:",
                key="apply_yield_changes",
                type="primary",
                help=YIELD_APPLY_HELP,
                disabled=not yield_pending,
            )
            st.button(
                "Excel 붙여넣기",
                icon=":material/content_paste:",
                key="open_yield_paste",
                on_click=_open_dialog,
                args=(YIELD_PASTE_DIALOG,),
            )
            if yield_pending:
                st.button(
                    "편집 취소",
                    icon=":material/undo:",
                    key="discard_yield_edits",
                    on_click=discard_editor,
                    args=(YIELD_EDITOR_KEY,),
                    help="수율 표에서 적용하지 않은 편집을 버립니다.",
                )
        yield_notice = st.empty()
        _render_flashes(f"{YIELD_PASTE_KEY}_flash")
        _render_locked_yield_rows(locked_yield_rows)
        if _dialog_is_open(YIELD_PASTE_DIALOG):
            _yield_paste_dialog(
                default_yield_table,
                f"RQ_YLD_{effective_start_month}_{effective_end_month}.csv",
            )
        yield_month_columns = [
            column
            for column in default_yield_table.columns
            if column not in YIELD_EDITOR_DIMENSIONS
        ]
        styled_yield_table = default_yield_table.style.set_properties(
            subset=pd.Index(YIELD_EDITOR_DIMENSIONS),
            **{"background-color": tokens.SURFACE_CLASSIFICATION},
        )
        edited_yield_table = st.data_editor(
            styled_yield_table,
            key=editor_widget_key(YIELD_EDITOR_KEY),
            hide_index=True,
            width="content",
            height=500,
            row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
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
        if apply_yield:
            try:
                _apply_yield(edited_yield_table, "편집값을")
            except ValueError as exc:
                yield_notice.error(str(exc))
            else:
                st.rerun()

# PKG PLAN 적용은 **두 편집표를 모두 그린 뒤**에 한다. 적용은 `st.rerun()` 으로 끝나는데,
# Streamlit 은 그것을 정상 완료로 보고 그 회차에 그리지 않은 위젯의 상태를 서버에서 지운다. 예전에는
# 이 블록이 수율 표보다 앞이라, 수율에 적용하지 않은 편집이 있는 채 PKG PLAN 을 적용하면 그 편집이
# 서버에서 사라져 수율 탭 점과 사이드바 경고가 꺼졌다. 그때 누른 「신규 리비전 저장」은 다음 조작에
# 브라우저가 되보낸 편집 때문에 잠긴 버튼이 되어 말없이 무시됐다(2026-10-01 브라우저 E2E). 오류
# 알림은 작업 줄 아래 자리(`plan_notice`)에 쓰므로 여기서 처리해도 누른 자리에 뜬다.
if apply_plan:
    try:
        updated_plan = attach_plan_attributes(
            plan_from_edit_table(edited_plan_table), simulation_plan
        )
        apply_month_updates(
            active_scenario,
            {"RQ_PKG_PLAN": updated_plan},
            effective_start_month,
            effective_end_month,
        )
    except ValueError as exc:
        plan_notice.error(str(exc))
    else:
        st.session_state.pop(PLAN_STAGED_KEY, None)
        st.session_state[PLAN_APPLIED_FLASH_KEY] = (
            f"PKG PLAN을 전역 계획값에 반영했습니다. "
            f"{effective_start_month}~{effective_end_month} 구간의 환산·소요대수·확보율과 "
            f"홈 대시보드가 이 계획으로 다시 계산됩니다. "
            "리비전으로 남기려면 사이드바 「저장」 → 「신규 리비전 저장」을 누르세요."
        )
        mark_own_change(OWN_CHANGE_KEY, (PLAN_EDITOR_KEY, PLAN_STAGED_KEY))
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
