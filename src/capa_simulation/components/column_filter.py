# Purpose: 분류 컬럼 다중선택 필터와 초기화 버튼을 한 모양으로 제공한다.

"""Shared expander with per-column multiselect filters.

공정별 확보율의 세 탭이 같은 블록을 각자 복제하고 있었다. 초기화 버튼, 가로로 늘어선
multiselect, 선택값으로 프레임을 거르는 절차가 같고 대상 컬럼만 달랐다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
import streamlit as st

from capa_simulation.components.process_labels import ProcessLabelFormatter

FILTER_WIDTH_PX = 180


def render_column_filters(
    data: pd.DataFrame,
    columns: Sequence[str],
    *,
    key_prefix: str,
    column_labels: Mapping[str, str] | None = None,
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
    label: str = "필터",
    expanded: bool = False,
) -> pd.DataFrame:
    """분류 컬럼별 다중선택 필터를 그리고 선택값으로 거른 프레임을 돌려준다.

    선택이 없는 컬럼은 거르지 않는다. 필터가 하나도 걸리지 않으면 원본 그대로다.

    `value_labels` 는 **표시에만** 쓴다(`format_func`). 옵션 값·세션 저장값은 원본이어야
    한다. 값을 표시명으로 바꾸면 아래 `isin` 이 원본 컬럼과 대조하지 못해 표가 오류 없이
    비어 버린다.
    """
    filter_keys = {column: f"{key_prefix}_{column}" for column in columns}
    selections: dict[str, list[str]] = {}
    with st.expander(label, expanded=expanded):
        if st.button("필터 초기화", key=f"{key_prefix}_reset"):
            for filter_key in filter_keys.values():
                st.session_state[filter_key] = []
        with st.container(horizontal=True, gap="small"):
            for column in columns:
                options = data[column].dropna().drop_duplicates().tolist()
                labels = (value_labels or {}).get(column)
                selections[column] = st.multiselect(
                    (column_labels or {}).get(column, column),
                    options=options,
                    key=filter_keys[column],
                    placeholder="전체",
                    width=FILTER_WIDTH_PX,
                    format_func=ProcessLabelFormatter(labels) if labels else str,
                )

    filtered = data
    for column, selected in selections.items():
        if selected:
            filtered = filtered.loc[filtered[column].isin(selected)]
    return filtered.copy()
