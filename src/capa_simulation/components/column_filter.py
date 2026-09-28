# Purpose: 분류 컬럼 다중선택 필터와 초기화 버튼을 한 모양으로 제공한다.

"""Shared per-column multiselect filters.

공정별 확보율의 세 탭이 같은 블록을 각자 복제하고 있었다. 초기화 버튼, 늘어선 multiselect,
선택값으로 프레임을 거르는 절차가 같고 대상 컬럼만 달랐다.

두 모양이 있다. 본문 표 위의 접는 틀(`render_column_filters`)과, 사이드바 조건 카드 안에 세로로
쌓는 모양(`render_column_filter_controls`, 2026-09-29 사용자 결정 — 필터는 사이드바 조건 카드).
카드는 그 탭이 열렸을 때만 서므로, 닫힌 탭의 표를 걸러야 할 때는 위젯 없이 세션에 남은 선택만
읽는다(`apply_column_filters`). 선택은 `persist_state="session"` 이라 위젯이 없는 회차에도 남는다.
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
                    persist_state="session",
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


def column_filter_key(key_prefix: str, column: str) -> str:
    return f"{key_prefix}_{column}"


def apply_column_filters(
    data: pd.DataFrame,
    columns: Sequence[str],
    *,
    key_prefix: str,
) -> pd.DataFrame:
    """세션에 남은 선택으로만 거른다. 위젯을 그리지 않는 회차(카드가 없는 탭)에 쓴다."""
    filtered = data
    for column in columns:
        selected = st.session_state.get(column_filter_key(key_prefix, column))
        if isinstance(selected, list) and selected and column in filtered.columns:
            filtered = filtered.loc[filtered[column].isin(selected)]
    return filtered.copy()


def render_column_filter_controls(
    data: pd.DataFrame,
    columns: Sequence[str],
    *,
    key_prefix: str,
    column_labels: Mapping[str, str] | None = None,
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
    disabled: bool = False,
) -> pd.DataFrame:
    """조건 카드 안에 필터를 **세로로** 쌓고 거른 프레임을 돌려준다(접는 틀 없음).

    사이드바 폭이라 가로로 늘어놓지 않는다. `disabled` 는 필터를 바꾸면 사라질 것(적용하지
    않은 편집)이 있을 때 부르는 쪽이 잠그는 데 쓴다 — 선택은 그대로 걸린다.
    """
    filter_keys = {column: column_filter_key(key_prefix, column) for column in columns}
    if st.button(
        "필터 초기화",
        key=f"{key_prefix}_reset",
        icon=":material/filter_alt_off:",
        width="stretch",
        disabled=disabled,
    ):
        for filter_key in filter_keys.values():
            st.session_state[filter_key] = []
    selections: dict[str, list[str]] = {}
    for column in columns:
        options = data[column].dropna().drop_duplicates().tolist()
        labels = (value_labels or {}).get(column)
        selections[column] = st.multiselect(
            (column_labels or {}).get(column, column),
            options=options,
            key=filter_keys[column],
            persist_state="session",
            placeholder="전체",
            format_func=ProcessLabelFormatter(labels) if labels else str,
            select_all=True,
            disabled=disabled,
        )
    filtered = data
    for column, selected in selections.items():
        if selected:
            filtered = filtered.loc[filtered[column].isin(selected)]
    return filtered.copy()
