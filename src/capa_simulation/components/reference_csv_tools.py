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


def render_reference_clipboard_form(
    data: pd.DataFrame,
    *,
    table_name: str,
    key_columns: list[str],
    file_name: str,
    key: str,
) -> pd.DataFrame | None:
    """양식 내려받기와 붙여넣기 칸을 그리고, 제출되면 검증한 표를 돌려준다.

    팝업(`st.dialog`) 안에서 쓴다 — 붙여넣기는 표 위 작업 줄의 「Excel 붙여넣기」 팝업이다
    (2026-09-28·29 사용자 결정). 완료 알림은 팝업이 닫힌 뒤 본문 작업 줄 아래에 떠야 보이므로
    부르는 쪽이 정하고, 설명은 Guide 가 맡는다.
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
