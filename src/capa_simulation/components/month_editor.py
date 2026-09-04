# Purpose: 월별 Wide 기준정보를 탭 안에서 편집하는 공통 data_editor 를 제공한다.

"""Shared month-column editor used by the Capa reference tabs.

`app_pages/**` 는 직접 실행 스크립트를 유지하고 재사용 UI 는 `components/` 에 둔다는
규칙에 맞춰 `capacity_standards` 안에 있던 68줄짜리 렌더러를 옮겼다. 같은 페이지에서
7번 불리며, 분류 컬럼은 고정·비활성으로 두고 월 컬럼만 숫자로 편집하게 한다.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

import pandas as pd
import streamlit as st

from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.reference_csv_tools import render_reference_clipboard_tools
from capa_simulation.design import tokens


class OpenTab(Protocol):
    @property
    def open(self) -> bool | None: ...

    def __enter__(self) -> OpenTab: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


def render_month_editor(
    tab: OpenTab,
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    caption: str,
    number_format: str,
    step: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    *,
    table_name: str,
    csv_file_name: str,
) -> tuple[pd.DataFrame, bool, pd.DataFrame | None]:
    if tab.open is False:
        return pd.DataFrame(), False, None
    month_columns = [column for column in default_table.columns if column not in dimensions]
    styled_table = default_table.style.set_properties(
        subset=pd.Index(dimensions),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )
    with tab:
        st.caption(caption)
        edited = st.data_editor(
            styled_table,
            key=editor_key,
            hide_index=True,
            width="content",
            height=500,
            row_height=25,
            num_rows="fixed",
            disabled=dimensions,
            column_config={
                **{
                    column: st.column_config.TextColumn(
                        COLUMN_LABELS.get(column, column),
                        alignment="center",
                        pinned=True,
                    )
                    for column in dimensions
                },
                **{
                    month: st.column_config.NumberColumn(
                        month,
                        width=80,
                        min_value=min_value,
                        max_value=max_value,
                        step=step,
                        format=number_format,
                        alignment="center",
                    )
                    for month in month_columns
                },
            },
        )
        submitted = st.button(
            "변경사항 적용",
            icon=":material/check:",
            key=f"{editor_key}_apply",
            type="primary",
        )
        imported = render_reference_clipboard_tools(
            default_table,
            table_name=table_name,
            key_columns=dimensions,
            file_name=csv_file_name,
            key=f"{editor_key}_csv",
        )
    return edited, submitted, imported
