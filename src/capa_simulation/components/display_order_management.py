# Purpose: Web editor and Excel clipboard import for the global display-order profile.

"""Web editor and Excel clipboard import for the global display-order profile."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.io.reference_cache import apply_global_display_order
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_display_order_cache,
    load_global_display_order,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.display_order_csv import (
    display_order_from_clipboard,
    display_order_to_csv,
)
from capa_simulation.services.display_order_editor import (
    DISPLAY_ORDER_RULE_COLUMNS,
    display_label_mistakes,
    replace_display_order_scope,
    validate_display_order,
)

# 이 탭의 붙여넣기 팝업. Admin Area 의 팝업 칸은 하나라 값이 탭을 가른다.
PASTE_DIALOG = "display_order_paste"
# 전체 교체 확인 체크박스의 자리. 적용에 성공하면 비워 다음 붙여넣기가 다시 확인을 거친다.
CLIPBOARD_CONFIRM_KEY = "global_display_order_clipboard_confirm"
DISPLAY_ORDER_EDITOR_KEY = "display_order_editor"
# 저장 뒤 「화면 표시명」 경고의 자리. 저장 성공은 곧바로 `st.rerun()` 하므로 그 회차에
# 그린 경고는 화면에 닿지 않는다. 성공 문구처럼 세션에 담았다가 다음 회차에 한 번 그린다.
LABEL_WARNINGS_KEY = "display_order_label_warnings"


@st.cache_data(show_spinner=False, max_entries=4)
def _validated_display_order(
    database_path: str,
    version: int,
    _rules: pd.DataFrame,
) -> tuple[pd.DataFrame, bytes]:
    """검증한 규칙과 내려받기 CSV. 둘 다 순수 함수라 공용 버전이 같으면 결과도 같다.

    검증 47ms + CSV 46ms(안에서 검증을 한 번 더 한다)를 rerun 마다 하고 있었다. 이 탭은
    닫혀 있어도 항상 그리므로(폼 입력값 보존) 그 비용이 페이지의 모든 rerun 에 실린다.
    규칙은 교체할 때마다 version 이 오르므로 키에 version 만 있으면 된다.
    """
    del database_path, version
    validated = validate_display_order(_rules)
    return validated, display_order_to_csv(validated)


def render_display_order_management(repository: DuckDBScenarioRepository) -> None:
    st.subheader("표시순서 관리")
    database_path = str(repository.database_path)
    try:
        profile = load_global_display_order(database_path)
        display_order, csv_bytes = _validated_display_order(
            database_path, profile.version, profile.rules
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        # 이 프로필만 `version == 0` 이 없다. 저장소가 1 부터 올리고 미초기화는
        # 예외라, 공통 캡션의 「없음」 갈래에는 닿지 않는다.
        st.caption(profile_version_caption(profile, empty="아직 저장한 표시순서가 없습니다"))
        render_csv_download(
            data=csv_bytes,
            file_name=f"RQ_DISPLAY_ORDER_v{profile.version}.csv",
            key="display_order_download",
        )
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key="display_order_open_paste",
            on_click=open_admin_dialog,
            args=(PASTE_DIALOG,),
        )
    render_flash("display_order_flash")
    _render_label_warnings()

    if admin_dialog_is_open(PASTE_DIALOG):
        _clipboard_dialog(repository, display_order)
    _render_direct_editor(repository, display_order)


@st.dialog("Excel 붙여넣기 · 표시순서", width="large", on_dismiss=close_admin_dialog)
def _clipboard_dialog(
    repository: DuckDBScenarioRepository,
    current: pd.DataFrame,
) -> None:
    # 적용이 무엇을 바꾸는지는 누르기 전에 알아야 해 팝업 안에 남긴다.
    st.caption("적용하면 현재 공용 표시순서 **전체**가 교체됩니다(시나리오 리비전은 만들지 않음).")
    with st.form("global_display_order_clipboard_form", border=False):
        clipboard_text = st.text_area(
            "표시순서 표 붙여넣기",
            key="global_display_order_clipboard",
            height=220,
            placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
        )
        confirmed = st.checkbox(
            "현재 공용 표시순서 전체 교체를 확인했습니다.",
            key=CLIPBOARD_CONFIRM_KEY,
        )
        submitted = st.form_submit_button(
            "붙여넣기 표시순서 적용",
            icon=":material/content_paste:",
            type="primary",
            width="stretch",
        )
    if not submitted:
        return
    if not clipboard_text.strip():
        st.error("적용할 표시순서 표를 Excel에서 복사해 붙여넣으세요.")
        return
    if not confirmed:
        st.error("전체 교체 확인을 선택하세요.")
        return
    try:
        imported = display_order_from_clipboard(clipboard_text)
        if imported.equals(current):
            st.info("붙여넣은 표시순서가 현재 공용 설정과 동일합니다.")
            return
        _save_global_display_order(repository, imported, source="Excel 붙여넣기")
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        # 확인 체크는 이번 교체 한 번에만 유효하다. 폼은 제출해도 값을 비우지 않으므로
        # 여기서 버려야 다음 붙여넣기가 확인 관문을 다시 거친다.
        st.session_state.pop(CLIPBOARD_CONFIRM_KEY, None)
        queue_flash(
            "display_order_flash",
            "붙여넣은 표시순서를 모든 시나리오의 공용 설정으로 적용했습니다.",
        )
        close_admin_dialog()
        st.rerun()


def _render_direct_editor(
    repository: DuckDBScenarioRepository,
    display_order: pd.DataFrame,
) -> None:
    st.markdown("#### 직접 편집")
    pages = display_order["페이지 구분"].drop_duplicates().tolist()
    selected_page = st.selectbox(
        "페이지 구분",
        options=pages,
        key="display_order_page",
        persist_state="session",
    )
    tabs = (
        display_order.loc[display_order["페이지 구분"].eq(selected_page), "탭 구분"]
        .drop_duplicates()
        .tolist()
    )
    selected_tab = st.selectbox(
        "탭 구분",
        options=tabs,
        key="display_order_tab",
        persist_state="session",
    )
    scope_mask = display_order["페이지 구분"].eq(selected_page) & display_order["탭 구분"].eq(
        selected_tab
    )
    scope_rules = display_order.loc[scope_mask, list(DISPLAY_ORDER_RULE_COLUMNS)].reset_index(
        drop=True
    )
    # 저장 오류는 저장 버튼 **바로 위**에 띄운다. 460px 표 아래에 두면 화면 밖이라 저장을 눌러도
    # 아무 일이 없는 것처럼 보였다(2026-10-05 E2E). 칸은 늘 세워 둬 아래 폼의 자리를 고정한다.
    save_status = st.container()
    with st.form("display_order_edit_form"):
        # 작업 줄(저장·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
        # 정렬 규칙을 쓰는 법은 Admin Area Guide 가 말한다.
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            submitted = st.form_submit_button(
                "공용 표시순서 저장",
                icon=":material/save:",
                type="primary",
            )
            note = st.text_input(
                "변경 메모",
                placeholder="예: 환산 탭 제품 표시순서 변경",
                key="display_order_note",
            )
        edited = st.data_editor(
            scope_rules,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            height=460,
            # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
            placeholder="",
            column_config={
                "정렬우선순위": st.column_config.NumberColumn(min_value=1, step=1),
                "정렬방식": st.column_config.SelectboxColumn(
                    options=["사용자지정", "오름차순", "내림차순"],
                    required=True,
                ),
                "값표시순서": st.column_config.NumberColumn(min_value=1, step=1),
                "활성여부": st.column_config.SelectboxColumn(
                    options=["Y", "N"],
                    required=True,
                ),
            },
            key=f"{DISPLAY_ORDER_EDITOR_KEY}::{selected_page}::{selected_tab}",
        )
    if not submitted:
        return
    try:
        revised = replace_display_order_scope(
            display_order,
            str(selected_page),
            str(selected_tab),
            pd.DataFrame(edited),
        )
        source = note.strip() or f"웹 직접 편집 · {selected_page}/{selected_tab}"
        _save_global_display_order(repository, revised, source=source)
        # 표시명을 적으면 저장은 통과하고 정렬만 조용히 걸리지 않는다. 막지 않고 알린다.
        mistakes = display_label_mistakes(pd.DataFrame(edited), COLUMN_LABELS)
        if mistakes:
            st.session_state[LABEL_WARNINGS_KEY] = mistakes
    except BOOTSTRAP_ERRORS as exc:
        save_status.error(bootstrap_error_message(exc))
    else:
        queue_flash(
            "display_order_flash",
            "표시순서를 모든 시나리오의 공용 설정으로 저장했습니다.",
        )
        st.rerun()


def _render_label_warnings() -> None:
    """저장한 회차에 담아 둔 표시명 경고를 성공 문구 바로 아래에 한 번 그리고 비운다."""
    mistakes = st.session_state.pop(LABEL_WARNINGS_KEY, None)
    if not isinstance(mistakes, dict):
        return
    for typed, column in mistakes.items():
        # 이름 뒤에 조사를 붙이지 않는다. `Customer` 같은 영문 이름은 받침을 가릴 수 없어
        # 「`Customer` 을」로 틀렸다(2026-10-05 E2E).
        st.warning(
            "화면 표시명을 적었습니다. 정렬은 원본 컬럼명을 보므로 원본 컬럼명으로 바꿔 적어야 "
            f"걸립니다: `{typed}` → `{column}`",
            icon=":material/help:",
        )


def _save_global_display_order(
    repository: DuckDBScenarioRepository,
    display_order: pd.DataFrame,
    *,
    source: str,
) -> None:
    validated = validate_display_order(display_order)
    profile = repository.replace_global_display_order(validated, source=source)
    clear_global_display_order_cache()
    try:
        apply_global_display_order(profile.rules)
    except RuntimeError:
        pass
