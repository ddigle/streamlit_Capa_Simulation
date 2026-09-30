# Purpose: Admin Area 의 Proc Rename 탭에서 공용 공정 표시명을 CSV·붙여넣기·직접 편집으로 관리한다.

"""공용 공정 표시명 프로필의 웹 편집기와 Excel 붙여넣기 가져오기.

여기서 저장한 표시명은 **화면 표기에만** 적용된다. 보고용 다운로드와 DB 저장값은 원본
공정명 그대로다. 저장은 시나리오와 무관한 공용 DB 프로필이라 리비전을 만들지 않는다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_process_rename_cache,
    load_global_process_rename,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    drop_blank_process_rename_rows,
    empty_process_rename_rules,
    prepare_process_rename_rules,
    process_rename_from_clipboard,
    process_rename_to_csv,
)

# 이 탭의 붙여넣기 팝업. Admin Area 의 팝업 칸은 하나라 값이 탭을 가른다.
PASTE_DIALOG = "process_rename_paste"
CLIPBOARD_KEY = "admin_area_process_rename_clipboard"
# 전체 교체 확인 체크박스의 자리. 적용에 성공하면 비워 다음 붙여넣기가 다시 확인을 거친다.
CLIPBOARD_CONFIRM_KEY = "admin_area_process_rename_clipboard_confirm"
EDITOR_KEY = "admin_area_process_rename_editor"


@st.cache_data(show_spinner=False, max_entries=4)
def _process_rename_csv(database_path: str, version: int, _rules: pd.DataFrame) -> bytes:
    """내려받기 CSV. 순수 함수라 공용 버전이 같으면 결과도 같다.

    이 탭은 닫혀 있어도 항상 그리므로(폼 입력값 보존) 직렬화 비용이 모든 rerun 에 실린다.
    규칙은 교체할 때마다 version 이 오르므로 키에 version 만 있으면 된다.
    """
    del database_path, version
    return process_rename_to_csv(_rules)


def render_process_rename_management(
    repository: DuckDBScenarioRepository,
    available_processes: list[str],
) -> None:
    """Proc Rename 탭 한 장. `available_processes` 는 안내용이며 비어 있어도 편집·저장한다."""
    st.subheader("Proc Rename")
    database_path = str(repository.database_path)
    try:
        profile = load_global_process_rename(database_path)
        csv_bytes = _process_rename_csv(database_path, profile.version, profile.rules)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return

    version_caption = profile_version_caption(profile, empty="아직 지정한 표시명이 없습니다")
    # 작업 줄: 양식 내려받기와 Excel 붙여넣기(팝업). 붙여넣기는 가끔 하는 전체 교체라 본문을
    # 차지하지 않는다(2026-09-29 사용자 결정). 여는 버튼은 콜백으로 연다.
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(version_caption)
        render_csv_download(
            data=csv_bytes,
            file_name=f"PROC_RENAME_v{profile.version}.csv",
            key="admin_area_process_rename_download",
        )
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key="admin_area_process_rename_open_paste",
            on_click=open_admin_dialog,
            args=(PASTE_DIALOG,),
        )
    render_flash("process_rename_flash")

    labels = process_labels_from_rules(profile.rules, profile.version)
    unmatched = labels.unmatched(available_processes)
    if unmatched:
        st.info(
            "보유하지 않은 공정에 지정된 표시명 "
            f"{len(unmatched):,}건은 무시합니다: {', '.join(unmatched[:10])}"
        )
    collisions = labels.owned_name_collisions(available_processes)
    if collisions:
        st.warning(
            f"보유 공정의 원본명과 같은 표시명 {len(collisions):,}건이 있습니다: "
            f"{', '.join(collisions[:10])}. 화면에서 서로 다른 두 공정이 같은 이름으로 "
            "보입니다. 값은 원본이라 계산·조인은 그대로이며 저장은 막지 않습니다."
        )

    if admin_dialog_is_open(PASTE_DIALOG):
        _clipboard_dialog(repository, profile.rules)
    _render_direct_editor(repository, profile.rules, available_processes)


@st.dialog("Excel 붙여넣기 · 공정 표시명", width="large", on_dismiss=close_admin_dialog)
def _clipboard_dialog(
    repository: DuckDBScenarioRepository,
    current: pd.DataFrame,
) -> None:
    # 적용이 무엇을 바꾸는지는 누르기 전에 알아야 해 팝업 안에 남긴다.
    st.caption("적용하면 현재 공용 표시명 **전체**가 교체됩니다.")
    with st.form("admin_area_process_rename_clipboard_form", border=False):
        clipboard_text = st.text_area(
            "공정 표시명 표 붙여넣기",
            key=CLIPBOARD_KEY,
            height=220,
            placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
        )
        confirmed = st.checkbox(
            "현재 공용 공정 표시명 전체 교체를 확인했습니다.",
            key=CLIPBOARD_CONFIRM_KEY,
        )
        submitted = st.form_submit_button(
            "붙여넣기 표시명 적용",
            icon=":material/content_paste:",
            type="primary",
            width="stretch",
        )
    if not submitted:
        return
    if not clipboard_text.strip():
        st.error("적용할 공정 표시명 표를 Excel에서 복사해 붙여넣으세요.")
        return
    if not confirmed:
        st.error("전체 교체 확인을 선택하세요.")
        return
    try:
        imported = process_rename_from_clipboard(clipboard_text)
        if imported.equals(prepare_process_rename_rules(current)):
            st.info("붙여넣은 공정 표시명이 현재 공용 설정과 동일합니다.")
            return
        _save_process_rename(repository, imported, source="Excel 붙여넣기")
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        # 확인 체크는 이번 교체 한 번에만 유효하다. 폼은 제출해도 값을 비우지 않으므로
        # 여기서 버려야 다음 붙여넣기가 확인 관문을 다시 거친다.
        st.session_state.pop(CLIPBOARD_CONFIRM_KEY, None)
        queue_flash(
            "process_rename_flash",
            "붙여넣은 공정 표시명을 공용 설정으로 적용했습니다.",
        )
        close_admin_dialog()
        st.rerun()


def _render_direct_editor(
    repository: DuckDBScenarioRepository,
    current: pd.DataFrame,
    available_processes: list[str],
) -> None:
    st.markdown("#### 직접 편집")
    if available_processes:
        with st.expander(f"보유 공정 {len(available_processes):,}개", icon=":material/list:"):
            # 원본 공정명이다. 여기에 표시명을 입히면 붙여넣을 원본을 확인할 수 없다.
            st.dataframe(
                pd.DataFrame({"공정": available_processes}),
                hide_index=True,
                width="stretch",
                height=240,
            )
    editable = (
        empty_process_rename_rules() if current.empty else prepare_process_rename_rules(current)
    )
    with st.form("admin_area_process_rename_edit_form"):
        # 작업 줄(저장·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            submitted = st.form_submit_button(
                "공용 공정 표시명 저장",
                icon=":material/save:",
                type="primary",
            )
            note = st.text_input(
                "변경 메모",
                placeholder="예: LOB 차트 공정명 축약",
                key="admin_area_process_rename_note",
            )
        edited = st.data_editor(
            editable,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            height=420,
            # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
            placeholder="",
            column_config={
                "공정": st.column_config.TextColumn("공정 (원본)"),
                "표시명": st.column_config.TextColumn("표시명 (화면 표기)"),
            },
            key=EDITOR_KEY,
        )
    if not submitted:
        return
    try:
        revised = drop_blank_process_rename_rows(
            pd.DataFrame(edited, columns=list(PROCESS_RENAME_COLUMNS))
        )
        _save_process_rename(repository, revised, source=note.strip() or "웹 직접 편집")
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        queue_flash("process_rename_flash", "공정 표시명을 공용 설정으로 저장했습니다.")
        st.rerun()


def _save_process_rename(
    repository: DuckDBScenarioRepository,
    rules: pd.DataFrame,
    *,
    source: str,
) -> None:
    """검증 → 교체 저장 → 캐시 폐기.

    1:1 위반은 반드시 파이썬 `ValueError` 로 먼저 낸다. DB 의 UNIQUE 는 마지막 방어선이고
    그 위반은 `duckdb.ConstraintException` 이라 화면 오류 문구로 바뀌지 않는다.
    """
    prepared = prepare_process_rename_rules(rules)
    repository.replace_global_process_rename(prepared, source=source)
    clear_global_process_rename_cache()
