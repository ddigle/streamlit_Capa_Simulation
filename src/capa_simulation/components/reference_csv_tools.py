"""Reusable Streamlit controls for wide RQ table CSV round trips."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.services.reference_csv import (
    parse_reference_edit_csv,
    reference_edit_csv_bytes,
)


def render_reference_csv_tools(
    data: pd.DataFrame,
    *,
    table_name: str,
    key_columns: list[str],
    file_name: str,
    key: str,
    expander_label: str = "CSV 일괄 수정",
) -> pd.DataFrame | None:
    """Render download/upload controls and return a validated submitted table."""
    flash = st.session_state.pop(f"{key}_flash", None)
    if isinstance(flash, str):
        st.success(flash)

    with st.expander(expander_label, icon=":material/csv:"):
        st.caption(
            "현재 조회 범위의 분류 행과 월 컬럼을 그대로 내려받습니다. "
            "값만 수정하고 행·컬럼 구조는 변경하지 않은 파일을 다시 적용하세요."
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
        with st.form(f"{key}_upload_form", border=False):
            uploaded_file = st.file_uploader(
                f"{table_name} CSV 선택",
                type=["csv"],
                key=f"{key}_file",
            )
            submitted = st.form_submit_button(
                ":material/upload: CSV 일괄 적용",
                type="primary",
            )
        if not submitted:
            return None
        if uploaded_file is None:
            st.error("적용할 CSV 파일을 선택하세요.")
            return None
        try:
            return parse_reference_edit_csv(
                uploaded_file.getvalue(),
                data,
                key_columns,
                table_name,
            )
        except ValueError as exc:
            st.error(str(exc))
            return None


def queue_reference_csv_flash(key: str, message: str) -> None:
    """Show a successful CSV apply message after the page reruns."""
    st.session_state[f"{key}_flash"] = message
