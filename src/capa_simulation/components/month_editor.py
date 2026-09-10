# Purpose: 월별 Wide 기준정보를 탭 안에서 편집하는 공통 data_editor 를 제공한다.

"""Capa 기준정보 탭 여섯 개가 함께 쓰는 월 컬럼 편집기.

분류 컬럼은 고정·비활성으로 두고 월 컬럼만 숫자로 편집한다.

**필터는 보기만 좁히고 저장은 전체다.** 분류 컬럼 필터는 화면에 그릴 행만 줄이고, 이
함수가 돌려주는 표는 언제나 `default_table` 과 **행 수·행 순서가 같은 전체 표**다. 편집값은
`dimensions` 를 키로 원본에 되머지한다. 이 되머지를 지우고 걸러진 표를 그대로 돌려주면
`scenario_state.replace_month_range` 가 조회기간의 행을 편집값으로 통째로 갈아끼우므로
**화면에서 걸러진 공정이 그 기간에서 조용히 삭제된다.**

되머지가 정확한 근거는 `num_rows="fixed"` 와 `disabled=dimensions` 다. 행 추가·삭제가
불가능하고 분류 컬럼도 잠겨 있어 사용자가 바꿀 수 있는 것은 월 컬럼 숫자뿐이다.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st

from capa_simulation.components.column_filter import render_column_filters
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.reference_csv_tools import render_reference_clipboard_tools
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

# 필터 위젯은 숨은 탭에서 그려지지 않는다(아래 조기 반환). 그려지지 않은 위젯의 상태는
# Streamlit 이 버리므로 탭을 옮기면 선택이 남지 않는다. 그 사실을 화면에도 적어 둔다.
FILTER_NOTICE = (
    "필터는 화면만 좁힙니다. 변경사항 적용은 필터와 무관하게 표 전체를 저장합니다. "
    "필터를 바꾸면 아직 적용하지 않은 편집은 사라지고, 다른 탭으로 옮기면 필터 선택도 "
    "초기화됩니다."
)


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
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[pd.DataFrame, bool, pd.DataFrame | None]:
    if tab_is_hidden(tab):
        return pd.DataFrame(), False, None
    month_columns = [column for column in default_table.columns if column not in dimensions]
    with tab:
        st.caption(caption)
        visible_table = _visible_table(default_table, dimensions, editor_key, value_labels)
        styled_table = visible_table.style.set_properties(
            subset=pd.Index(dimensions),
            **{"background-color": tokens.SURFACE_CLASSIFICATION},
        )
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
        # 왕복 CSV·붙여넣기는 전체 표 계약이다. 여기에 걸러진 표를 넘기면 양식이 부분 표가
        # 되고, 그 부분 표는 검증을 통과해 나머지 공정을 조회기간에서 지운다.
        imported = render_reference_clipboard_tools(
            default_table,
            table_name=table_name,
            key_columns=dimensions,
            file_name=csv_file_name,
            key=f"{editor_key}_csv",
        )
    return (
        merge_edited_months(default_table, edited, dimensions, month_columns),
        submitted,
        imported,
    )


def merge_edited_months(
    default_table: pd.DataFrame,
    edited: pd.DataFrame,
    dimensions: list[str],
    month_columns: list[str],
) -> pd.DataFrame:
    """필터로 좁힌 편집표의 월 값을 원본 전체에 되머지한다.

    `dimensions` 를 키로 쓴다. 결과는 `default_table` 과 행 수·행 순서·분류값이 같고 월
    값만 편집값으로 덮인다. 필터가 걸리지 않았으면 편집표가 곧 전체 표라 그대로 돌려준다.
    """
    if edited.index.equals(default_table.index):
        return edited
    merged = default_table.copy()
    if not dimensions or not month_columns or edited.empty:
        return merged
    target_keys = pd.MultiIndex.from_frame(merged[dimensions].astype(str))
    edited_keys = pd.MultiIndex.from_frame(edited[dimensions].astype(str))
    positions = target_keys.get_indexer(edited_keys)
    matched = positions >= 0
    if not matched.any():
        return merged
    # 위치가 아니라 분류 키로 찾은 행에만 쓴다. 필터가 인덱스를 어떻게 바꾸든 값이 다른
    # 행에 얹히지 않는다.
    target_labels = merged.index[positions[matched]]
    merged.loc[target_labels, month_columns] = edited.loc[matched, month_columns].to_numpy()
    return merged


def _visible_table(
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    value_labels: Mapping[str, Mapping[str, str]] | None,
) -> pd.DataFrame:
    """화면에 그릴 행만 남긴 표. 필터를 걸 수 없는 표는 원본 그대로다.

    `value_labels` 는 필터 옵션의 **표시**에만 쓴다. 선택값·거른 프레임·편집표·왕복 CSV 는
    모두 원본 공정명이다. 표시명 조회는 페이지가 하고 이 모듈은 받은 매핑만 넘긴다.
    """
    if default_table.empty or any(column not in default_table.columns for column in dimensions):
        return default_table
    visible = render_column_filters(
        default_table,
        dimensions,
        key_prefix=f"{editor_key}_filter",
        column_labels=COLUMN_LABELS,
        value_labels=value_labels,
    )
    st.caption(FILTER_NOTICE)
    # data_editor 의 편집 델타는 행 '위치' 기반이라 보이는 행 집합이 바뀌면 남아 있던 편집이
    # 다른 행에 붙는다. 위젯을 만들기 전에 버려야 그 오염이 저장까지 가지 않는다.
    signature_key = f"{editor_key}_filter_rows"
    signature = hash(tuple(visible.index))
    if st.session_state.get(signature_key) != signature:
        st.session_state.pop(editor_key, None)
        st.session_state[signature_key] = signature
    return visible
