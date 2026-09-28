# Purpose: Reusable Streamlit controls for Excel clipboard updates of wide RQ tables.

"""Reusable Streamlit controls for Excel clipboard updates of wide RQ tables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL, render_csv_download
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
)


def render_reference_clipboard_tools(
    data: pd.DataFrame,
    *,
    table_name: str,
    key_columns: list[str],
    file_name: str,
    key: str,
    expander_label: str = "Excel 붙여넣기 일괄 수정",
) -> pd.DataFrame | None:
    """Render template download/paste controls and return a validated table."""
    flash = st.session_state.pop(f"{key}_flash", None)
    if isinstance(flash, str):
        st.success(flash)

    with st.expander(expander_label, icon=":material/content_paste:"):
        st.caption(
            "현재 조회 범위의 양식을 내려받아 Excel에서 값만 수정하세요. "
            "헤더를 포함한 전체 표를 복사해 아래에 붙여넣으면 파일 업로드 없이 적용합니다. "
            "행·컬럼 구조는 변경할 수 없습니다. "
            '분류 값 중 Excel이 숫자로 바꿔 읽는 것(예: `4.00E+02`)은 양식에서 `="…"` 로 '
            "묶어 내려갑니다 — 그대로 두시면 됩니다."
        )
        return render_reference_clipboard_form(
            data, table_name=table_name, key_columns=key_columns, file_name=file_name, key=key
        )


def render_reference_clipboard_form(
    data: pd.DataFrame,
    *,
    table_name: str,
    key_columns: list[str],
    file_name: str,
    key: str,
) -> pd.DataFrame | None:
    """양식 내려받기와 붙여넣기 칸만 그린다. 접는 틀·완료 알림은 부르는 쪽이 정한다.

    팝업(`st.dialog`) 안에서 쓰려고 뗐다 — 팝업에서는 접는 틀이 한 겹 더 두를 뿐이고, 완료
    알림은 팝업이 닫힌 뒤 본문 작업 줄 아래에 떠야 보인다(설명은 Guide 가 맡는다).
    """
    render_csv_download(
        data=reference_edit_csv_bytes(data, key_columns),
        file_name=file_name,
        key=f"{key}_download",
        label=CSV_TEMPLATE_LABEL,
    )
    with st.form(f"{key}_clipboard_form", border=False):
        clipboard_text = st.text_area(
            f"{table_name} 표 붙여넣기",
            key=f"{key}_clipboard",
            height=180,
            placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
        )
        submitted = st.form_submit_button(
            "붙여넣기 일괄 적용",
            icon=":material/content_paste:",
            type="primary",
        )
    if not submitted:
        return None
    if not clipboard_text.strip():
        st.error("적용할 표를 Excel에서 복사해 붙여넣으세요.")
        return None
    try:
        return parse_reference_edit_clipboard(
            clipboard_text,
            data,
            key_columns,
            table_name,
        )
    except ValueError as exc:
        st.error(str(exc))
        return None


def queue_reference_import_flash(key: str, message: str) -> None:
    """Show a successful clipboard apply message after the page reruns."""
    st.session_state[f"{key}_flash"] = message
