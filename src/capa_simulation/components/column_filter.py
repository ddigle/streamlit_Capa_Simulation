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
                    # 일괄선택은 이 화면에서 실제로 쓰는 기능이라 임계값에 맡기지 않고 켠다.
                    # 두 가지로 쓴다: 쳐서 좁힌 뒤 `Select N matches` 로 일치분만 담기,
                    # 그리고 전부 담은 뒤 몇 개를 빼서 "이것만 빼고 보기". 둘 다 결과가
                    # **부분 선택**이라 아래 `isin` 이 실제로 일한다 — 전체선택이 미선택과
                    # 같아지는 것은 전부 선택된 최종 상태뿐이다.
                    #
                    # 여기 들어오는 컬럼은 공정·Area_Name·Stack·STEP_SEQ 같은 분류 축뿐이라
                    # 옵션이 많아야 수십 개다. 수천 개를 한 번에 담아 브라우저가 멈추는
                    # `select_all=True` 의 주의사항은 이 컴포넌트에 해당하지 않는다.
                    select_all=True,
                )

    filtered = data
    for column, selected in selections.items():
        if selected:
            filtered = filtered.loc[filtered[column].isin(selected)]
    return filtered.copy()
