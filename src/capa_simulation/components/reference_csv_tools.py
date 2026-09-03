# Purpose: Reusable Streamlit controls for Excel clipboard updates of wide RQ tables.

"""Reusable Streamlit controls for Excel clipboard updates of wide RQ tables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

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
            "행·컬럼 구조는 변경할 수 없습니다."
        )
        st.download_button(
            ":material/download: CSV 다운로드",
            data=reference_edit_csv_bytes(data),
            file_name=file_name,
            mime="text/csv;charset=utf-8",
            key=f"{key}_download",
            on_click="ignore",
            width="content",
        )
        with st.form(f"{key}_clipboard_form", border=False):
            clipboard_text = st.text_area(
                f"{table_name} 표 붙여넣기",
                key=f"{key}_clipboard",
                height=180,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            submitted = st.form_submit_button(
                ":material/content_paste: 붙여넣기 일괄 적용",
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
