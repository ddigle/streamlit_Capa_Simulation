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

**분류 컬럼의 값은 언제나 원본이다.** 표시명이 지정된 컬럼은 `SelectboxColumn` 으로 그려
셀에 보이는 글자만 바꾼다. 그 컬럼 설정은 옵션의 `value` 와 `label` 을 나눠 갖고 편집
결과·복사 데이터로는 `value` 를 돌려주므로 아래 되머지 키와 왕복 CSV 가 원본으로 남는다.
값 자체를 표시명으로 갈면 되머지 키가 어긋나 편집이 조용히 버려지고, 필터를 걸지 않은
단축 반환 경로에서는 표시명이 그대로 `RQ_*` 저장값이 된다.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation.components.column_filter import render_column_filters
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.process_labels import ProcessLabelFormatter
from capa_simulation.components.reference_csv_tools import render_reference_clipboard_tools
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

# 필터 위젯은 숨은 탭에서 그려지지 않는다(아래 조기 반환). 그래도 선택이 남는 것은
# `column_filter` 의 `persist_state="session"` 덕이다. 화면에는 실제로 사라지는 것, 곧
# 아직 적용하지 않은 편집만 적는다.
FILTER_NOTICE = (
    "필터는 화면만 좁힙니다. 변경사항 적용은 필터와 무관하게 표 전체를 저장합니다. "
    "필터를 바꾸면 아직 적용하지 않은 편집은 사라집니다. 필터 선택 자체는 탭을 옮겨도 "
    "남습니다."
)
# 화면은 표시명이지만 아래 CSV 양식과 붙여넣기 검증은 원본 공정명 계약이다. 화면 이름을
# 그대로 적어 붙여넣으면 분류 행 대조에서 막히므로 그 사실을 표 아래에 적는다.
RENAME_NOTICE = (
    "분류 컬럼은 화면 표시명으로 보입니다. CSV 양식과 붙여넣기는 원본 공정명 계약이므로 "
    "양식을 내려받아 그 이름 그대로 수정하세요."
)
# 표시명을 그리는 분류 컬럼의 폭 한계. `SelectboxColumn` 은 원본 값으로 폭을 재므로
# 표시명이 더 길면 잘린다.
DIMENSION_MIN_WIDTH_PX = 110
DIMENSION_MAX_WIDTH_PX = 280


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
            row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
            num_rows="fixed",
            disabled=dimensions,
            column_config={
                **_dimension_column_config(default_table, dimensions, value_labels),
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
        if _has_display_labels(dimensions, value_labels):
            st.caption(RENAME_NOTICE)
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


def _has_display_labels(
    dimensions: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None,
) -> bool:
    return any((value_labels or {}).get(column) for column in dimensions)


def _dimension_column_config(
    default_table: pd.DataFrame,
    dimensions: list[str],
    value_labels: Mapping[str, Mapping[str, str]] | None,
) -> dict[str, ColumnConfig]:
    """분류 컬럼의 `column_config`. 표시명이 있는 컬럼만 `SelectboxColumn` 으로 그린다.

    매핑이 없는 컬럼은 `TextColumn` 으로 원본 값을 그대로 그린다. `SelectboxColumn` 에는
    `alignment` 가 없어 그 컬럼만 가운데 정렬이 아니며, 열 폭은 표시명이 아니라 원본 값으로
    재므로 명시 폭을 준다.
    """
    config: dict[str, ColumnConfig] = {}
    for column in dimensions:
        title = COLUMN_LABELS.get(column, column)
        labels = (value_labels or {}).get(column)
        if not labels or column not in default_table.columns:
            config[column] = st.column_config.TextColumn(
                title,
                alignment="center",
                pinned=True,
            )
            continue
        # 셀 값이 옵션에 없으면 빈칸으로 그려진다. 표에 나오는 값 전체를 옵션에 넣는다.
        options = default_table[column].dropna().drop_duplicates().tolist()
        formatter = ProcessLabelFormatter(labels)
        longest = max((len(formatter(option)) for option in options), default=0)
        config[column] = st.column_config.SelectboxColumn(
            title,
            options=options,
            format_func=formatter,
            pinned=True,
            width=min(DIMENSION_MAX_WIDTH_PX, max(DIMENSION_MIN_WIDTH_PX, 13 * longest)),
        )
    return config


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
