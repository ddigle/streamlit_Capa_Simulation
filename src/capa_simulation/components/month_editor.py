# Purpose: 월별 Wide 기준정보 표의 공용 조각(붙여넣기 팝업·편집 범위·분류 칸 배경·되머지)을 둔다.

"""월 컬럼 표(분류 컬럼 + 월 컬럼)를 고치는 화면이 함께 쓰는 조각.

기준 정보 편집 표 아홉의 칸 편집은 범용 편집 그리드(`components/reference_grid.py` —
2026-11-02 사용자 결정 「편집 표 횡전개」)가 맡는다. 여기에는 그 그리드와 생산 계획 화면
(`load_conversion.py`)이 함께 쓰는 조각만 둔다.

- `paste_dialog` — 「Excel 붙여넣기」 표 전체 팝업(CSV 양식 왕복). **왕복 CSV·붙여넣기는 전체 표
  계약이다** — 걸러진 표를 넘기면 그 부분 표가 검증을 통과해 나머지 공정을 조회기간에서 지운다.
- `render_scope` — 「편집 범위」 한 줄(월 · 개월 수 · 행 수 · 필터로 보이는 행 수).
- `classification_styled` — 분류 컬럼 배경색(작은 표만 — `CLASSIFICATION_STYLE_MAX_CELLS`).
- `merge_edited_months` · `count_month_changes` — 걸러진 표의 월 값을 원본 전체에 분류 키로
  되머지하고, 적용하면 실제로 달라지는 칸·행을 센다(빈값끼리는 변경이 아니다).
- `float_month_columns` — 정수 dtype 월 칸을 실수로(생산 계획 편집표가 소수를 버리지 않게).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from capa_simulation.components.reference_csv_tools import render_reference_clipboard_form
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import bootstrap_error_message

# 화면은 표시명이지만 CSV 양식과 붙여넣기 검증은 원본 공정명 계약이다. 붙여넣기 팝업에만 적는다.
RENAME_NOTICE = (
    "분류 컬럼은 화면 표시명으로 보입니다. CSV 양식과 붙여넣기는 원본 공정명 계약이므로 "
    "양식을 내려받아 그 이름 그대로 수정하세요."
)
PASTE_DROPS_EDITS_NOTICE = (
    "이 표에 적용하지 않은 편집이 있습니다. 붙여넣기를 적용하면 그 편집은 버려집니다 — 먼저 "
    "「변경사항 적용」을 누르거나, 고친 값을 붙여넣을 표에 함께 담으세요."
)
# 적용을 누르면 어디까지 반영되는지. 동작을 좌우하는 안내라 Guide 로만 보내지 않고 버튼
# 툴팁에 남긴다(생산 계획과 같다).
APPLY_NOTICE = "적용 후 계산에 반영됩니다. 보관하려면 새 리비전을 저장하세요."
# **큰 표는 분류 컬럼 배경색을 입히지 않는다**(2026-10-05 사용자 결정 N1 = B). 배경색은 pandas
# Styler 로만 줄 수 있는데(`column_config` 에 배경색이 없다), Streamlit 은 그 Styler 를 그릴
# 때마다(rerun 마다) 분류 컬럼만이 아니라 **표의 모든 칸**을 번역한다. 비용은 셀 수에
# 비례해 칸당 약 15 µs 다(샘플 관측 — `scripts/generate_sample_core_data.py` 합성 DB 의
# UPEH 편집표를 행 수별로 잘라 `marshall_styler` 를 잰 값: 9,750칸 143 ms, 11,700칸 187 ms,
# 2,660×39 = 103,740칸 약 1.5 s). 그래서 약 150 ms 를 넘는 표, 곧 이 칸 수를 넘는 표는
# 배경색 없이 그린다. 그보다 작은 표는 전과 똑같이 그린다.
CLASSIFICATION_STYLE_MAX_CELLS: Final = 10_000


def float_month_columns(table: pd.DataFrame, month_columns: Sequence[str]) -> pd.DataFrame:
    """정수 dtype 월 칸을 실수(`float64`)로 바꾼 표. 바꿀 칸이 없으면 받은 표 그대로다.

    `step` 을 주지 않은 `NumberColumn` 은 정수 칸에 증분 1 을 스스로 걸어(Streamlit 1.63) 소수
    아래를 버린다 — 붙여넣기가 정수만 실어 와 표가 정수 dtype 이 되면 98.75% 효율이 0, 0.333 대가 0
    이 된다. 결측이 섞인 정수 칸(`Int64`)은 결측을 `NaN` 으로 옮긴다.
    """
    integer_columns = [
        column
        for column in month_columns
        if column in table.columns
        and pd.api.types.is_integer_dtype(table[column])
        and not pd.api.types.is_bool_dtype(table[column])
    ]
    if not integer_columns:
        return table
    return table.astype(dict.fromkeys(integer_columns, "float64"))


def classification_styled(
    table: pd.DataFrame, dimensions: Sequence[str], *, uuid: str | None = None
) -> pd.DataFrame | Styler:
    """분류 컬럼에 배경색을 입힌 Styler 다. 칸 수가 상한을 넘으면 표를 그대로 돌려준다.

    판정은 **실제로 그리는 표**(필터를 건 뒤의 표)의 칸 수로 한다 — 비용이 그 표를 번역하는
    데서 나오기 때문이다. 그래서 큰 표도 필터로 상한 아래까지 좁히면 배경색이 돌아온다.

    `uuid` 는 `st.dataframe` 으로 그리는 표에 준다(표마다 다른 고정값). pandas Styler 는 만들 때마다
    무작위 uuid 를 갖고 Streamlit 은 그것을 CSS 이름에 그대로 쓰므로, 주지 않으면 내용이 같아도
    회차마다 메시지가 달라 브라우저가 표를 통째로 다시 받는다. `st.data_editor` 는 Streamlit 이
    위젯 키로 uuid 를 고정하므로 주지 않아도 된다.
    """
    if table.size > CLASSIFICATION_STYLE_MAX_CELLS:
        return table
    styler = table.style.set_properties(
        subset=pd.Index(dimensions),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )
    if uuid is not None:
        styler.set_uuid(uuid)
    return styler


def paste_dialog(
    data: pd.DataFrame,
    *,
    table_name: str,
    dimensions: list[str],
    file_name: str,
    editor_key: str,
    dialog_key: str,
    on_paste: Callable[[pd.DataFrame], None],
    rename_notice: bool,
    min_value: float | None,
    max_value: float | None,
    pending_notice: str | None,
) -> None:
    """「Excel 붙여넣기」 팝업(표 전체 CSV 양식 — 붙여넣어 적용하면 팝업이 닫힌다).

    `pending_notice` 는 그 표에 적용하지 않은 편집이 있을 때 첫 줄에 쓰는 경고다 — 붙여넣기를
    적용하면 원본이 바뀌어 그 편집을 버리므로 버리기 전에 말한다. 편집이 어디에 사는지(편집표
    위젯·그리드 초안)는 부르는 쪽이 안다. `editor_key` 는 양식 칸·내려받기 key 의 앞머리다.
    """

    def _close() -> None:
        st.session_state.pop(dialog_key, None)

    @st.dialog(f"Excel 붙여넣기 · {table_name}", width="large", on_dismiss=_close)
    def _body() -> None:
        if pending_notice:
            st.warning(pending_notice)
        if rename_notice:
            st.caption(RENAME_NOTICE)
        imported = render_reference_clipboard_form(
            data,
            table_name=table_name,
            key_columns=dimensions,
            file_name=file_name,
            key=f"{editor_key}_csv",
            min_value=min_value,
            max_value=max_value,
        )
        if imported is None:
            return
        try:
            on_paste(imported)
        except (KeyError, ValueError) as exc:
            st.error(bootstrap_error_message(exc))
            return
        _close()
        st.rerun()

    _body()


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


def render_scope(
    default_table: pd.DataFrame, visible_table: pd.DataFrame, month_columns: Sequence[str]
) -> None:
    """무엇을 편집하고 있는지 한 줄. 표를 보기 전에 범위를 알려 준다.

    월 이름은 표 머리글에 쓰는 컬럼명 그대로다 — 여기서만 다른 형식으로 적으면 같은
    달을 두 이름으로 부르게 된다. 필터가 행을 줄였으면 그 사실도 적는다 — 필터는 사이드바
    카드에 있어 접혀 있으면 본문만 보고는 행이 빠진 까닭을 알 수 없다.
    """
    if not month_columns:
        return
    span = (
        f"{month_columns[0]} – {month_columns[-1]}"
        if len(month_columns) > 1
        else str(month_columns[0])
    )
    filtered = (
        f" · :material/filter_alt: 필터로 {len(visible_table):,}개 행 표시"
        if len(visible_table) != len(default_table)
        else ""
    )
    st.markdown(
        f"**편집 범위** &nbsp;{span} · {len(month_columns)}개월 · "
        f"전체 {len(default_table):,}개 행{filtered}"
    )


def count_month_changes(
    default_table: pd.DataFrame,
    merged: pd.DataFrame,
    month_columns: list[str],
) -> tuple[int, int]:
    """적용을 누르면 **실제로 달라지는** 칸 수와 행 수.

    편집표가 아니라 `merge_edited_months` 를 거친 **전체 표**를 원본과 맞댄다. 그래야
    필터로 가려진 행까지 셈에 들어가고, 화면마다 다른 빈칸 규칙(PKG PLAN 은 표시용
    빈칸을 0 으로 저장하고 수율은 아니다)을 여기서 따로 알 필요가 없다 — 되머지가 이미
    그 화면의 규칙대로 값을 써 놓았기 때문이다.

    **같은 빈값끼리는 변경이 아니다.** `NaN != NaN` 이라 그냥 비교하면 손대지 않은 빈칸이
    전부 변경으로 잡힌다.
    """
    columns = [column for column in month_columns if column in default_table.columns]
    if not columns or merged.empty or not merged.index.equals(default_table.index):
        return 0, 0
    before = default_table[columns].apply(pd.to_numeric, errors="coerce")
    after = merged[columns].apply(pd.to_numeric, errors="coerce")
    differs = (before != after) & ~(before.isna() & after.isna())
    return int(differs.to_numpy().sum()), int(differs.any(axis=1).sum())
