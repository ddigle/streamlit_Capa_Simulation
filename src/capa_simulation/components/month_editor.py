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

from collections.abc import Callable, Mapping, Sequence
from typing import Final

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler
from streamlit.delta_generator import DeltaGenerator
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation.components.column_filter import (
    apply_column_filters,
    render_column_filter_controls,
)
from capa_simulation.components.editor_state import (
    discard_editor,
    editor_has_edits,
    editor_widget_key,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.process_labels import ProcessLabelFormatter
from capa_simulation.components.reference_csv_tools import render_reference_clipboard_form
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.sidebar_status import table_card

# 필터는 본문이 아니라 사이드바 조건 카드 `표 조건`(`sidebar_status.table_card`)에 선다
# (2026-09-29 사용자 결정 — 필터·조건은 사이드바). 카드 이름은 페이지가 준다.
# 필터를 바꾸면 보이는 행이 바뀌어 적용하지 않은 편집을 버려야 한다(편집 델타가 행 위치 기반).
# 그래서 고친 것이 남아 있으면 필터를 잠근다 — 조용히 버리는 것보다 낫다.
FILTER_LOCKED_NOTICE = (
    "적용하지 않은 편집이 있어 필터를 잠갔습니다. 적용하거나 「편집 취소」를 누른 뒤 바꾸세요."
)
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
# 표시명을 그리는 분류 컬럼의 폭 한계. `SelectboxColumn` 은 원본 값으로 폭을 재므로
# 표시명이 더 길면 잘린다.
DIMENSION_MIN_WIDTH_PX = 110
DIMENSION_MAX_WIDTH_PX = 280


def render_month_editor(
    tab: OpenTab,
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    number_format: str,
    step: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    *,
    table_name: str,
    csv_file_name: str,
    dialog_key: str,
    on_paste: Callable[[pd.DataFrame], None],
    card_name: str,
    value_labels: Mapping[str, Mapping[str, str]] | None = None,
    outer_tab: OpenTab | None = None,
) -> tuple[pd.DataFrame, bool]:
    """월 편집표 하나. 돌려주는 것은 (되머지한 전체 표, 적용 버튼이 눌렸는가) 다.

    **적용하지 않은 편집이 남은 표는 탭이 닫혀도 그린다.** `st.data_editor` 는 그리지 않은
    회차에 편집 상태를 잃는다 — 전에는 닫힌 탭을 건너뛰어, 고친 뒤 다른 탭을 누르는 순간 편집이
    조용히 사라졌다. 편집이 없는 닫힌 탭은 예전처럼 건너뛴다(그리는 비용 때문에).

    `outer_tab` 은 탭 안의 탭(설비대수 › 보유 등)의 바깥 탭이다. 안쪽 탭은 바깥이 닫혀도 제
    선택만 알아서, 바깥을 함께 봐야 지금 화면에 보이는지 안다.

    **붙여넣기는 팝업 안에서 끝난다.** 팝업은 fragment 라 안에서 제출하면 팝업 함수만 다시 돈다
    — 결과를 페이지로 돌려줄 길이 없으므로 `on_paste` 가 검증·적용하고, 막히면
    `KeyError`/`ValueError` 를 던진다. 팝업이 그 글을 팝업 안에 쓴다.
    """
    open_now = not (tab_is_hidden(tab) or tab_is_hidden(outer_tab))
    pending = editor_has_edits(editor_key)
    if not open_now and not pending:
        # 지난 회차의 알림 자리는 이번 화면에 없다. 남겨 두면 거기 쓴 오류가 사라진다.
        st.session_state.pop(_notice_key(editor_key), None)
        return pd.DataFrame(), False
    month_columns = [column for column in default_table.columns if column not in dimensions]
    visible_table = _visible_table(
        default_table,
        dimensions,
        editor_key,
        value_labels,
        card_name=card_name if open_now else None,
        locked=pending,
    )
    with tab:
        # 작업 줄은 표 **위**다. 표가 높이 500px 이라 아래에 두면 고친 뒤 버튼이 화면 밖이어서
        # 적용하지 않고 넘어가기 쉽다(2026-09-28 사용자 지적). 버튼 값은 표보다 먼저 만들어도
        # 누른 회차에 표의 편집값이 그대로 들어온다. 변경 개수는 표를 그린 뒤에야 알므로 자리만
        # 먼저 잡아 두고 뒤에서 채운다.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            # 고친 것이 없으면 누를 수 없다. 누르면 같은 값으로 리비전만 올라 사이드바가
            # `미저장 변경` 을 켠다(2026-09-29 2차 리뷰).
            submitted = st.button(
                "변경사항 적용",
                icon=":material/check:",
                key=f"{editor_key}_apply",
                type="primary",
                help=APPLY_NOTICE,
                disabled=not pending,
            )
            # 여는 버튼은 **콜백**으로 연다 — 콜백은 스크립트보다 먼저 돌아 한 회차에 팝업이 둘
            # 뜨지 않는다(생산 계획과 같은 규칙).
            st.button(
                "Excel 붙여넣기",
                icon=":material/content_paste:",
                key=f"{editor_key}_open_paste",
                on_click=_open_paste,
                args=(dialog_key, editor_key),
            )
            if pending:
                st.button(
                    "편집 취소",
                    icon=":material/undo:",
                    key=f"{editor_key}_discard",
                    on_click=_discard_edits,
                    args=(editor_key,),
                    help="이 표에서 적용하지 않은 편집을 버립니다.",
                )
            change_slot = st.empty()
        _render_scope(default_table, visible_table, month_columns)
        # **결과는 누른 자리에서 보인다.** 적용·붙여넣기의 성공과 적용 오류는 작업 줄 바로 아래
        # 자리에 쓴다. 오류는 적용이 표 뒤에서 도므로 이 자리를 세션에 적어 두고 페이지가 거기에
        # 쓴다(`editor_notice`).
        notice = st.empty()
        st.session_state[_notice_key(editor_key)] = notice
        applied_flash = st.session_state.pop(f"{editor_key}_apply_flash", None)
        if isinstance(applied_flash, str):
            notice.success(applied_flash)
        edited = st.data_editor(
            classification_styled(visible_table, dimensions),
            # 편집을 버릴 때마다 바뀌는 위젯 키다 — 세션만 지우면 브라우저가 옛 편집을 다시 보낸다.
            key=editor_widget_key(editor_key),
            hide_index=True,
            width="content",
            height=500,
            row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
            num_rows="fixed",
            disabled=dimensions,
            # **빈칸은 빈칸으로 그린다**(2026-10-01 브라우저 점검). `placeholder` 를 주지 않으면
            # Streamlit 이 결측 칸에 회색 `None` 글자를 쓴다 — 가이드·경고가 「빈칸」이라 부르는
            # 칸(비운 붙여넣기, 값이 없는 달)이 `None` 으로 읽혔다. 편집표는 모두 이 값을 준다.
            placeholder="",
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
        merged = merge_edited_months(default_table, edited, dimensions, month_columns)
        changed_cells, changed_rows = count_month_changes(default_table, merged, month_columns)
        if changed_cells:
            change_slot.markdown(
                f"**변경사항 확인** &nbsp;{changed_cells:,}개 값 · {changed_rows:,}개 행"
            )
    if open_now and st.session_state.get(dialog_key) == editor_key:
        # 왕복 CSV·붙여넣기는 전체 표 계약이다. 걸러진 표를 넘기면 양식이 부분 표가 되고, 그
        # 부분 표는 검증을 통과해 나머지 공정을 조회기간에서 지운다.
        _paste_dialog(
            default_table,
            table_name=table_name,
            dimensions=dimensions,
            file_name=csv_file_name,
            editor_key=editor_key,
            dialog_key=dialog_key,
            on_paste=on_paste,
            rename_notice=_has_display_labels(dimensions, value_labels),
        )
    return merged, submitted


def classification_styled(table: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame | Styler:
    """분류 컬럼에 배경색을 입힌 Styler 다. 칸 수가 상한을 넘으면 표를 그대로 돌려준다.

    판정은 **실제로 그리는 표**(필터를 건 뒤의 표)의 칸 수로 한다 — 비용이 그 표를 번역하는
    데서 나오기 때문이다. 그래서 큰 표도 필터로 상한 아래까지 좁히면 배경색이 돌아온다.
    """
    if table.size > CLASSIFICATION_STYLE_MAX_CELLS:
        return table
    return table.style.set_properties(
        subset=pd.Index(dimensions),
        **{"background-color": tokens.SURFACE_CLASSIFICATION},
    )


def _open_paste(dialog_key: str, editor_key: str) -> None:
    st.session_state[dialog_key] = editor_key


def _discard_edits(editor_key: str) -> None:
    discard_editor(editor_key)


def _paste_dialog(
    data: pd.DataFrame,
    *,
    table_name: str,
    dimensions: list[str],
    file_name: str,
    editor_key: str,
    dialog_key: str,
    on_paste: Callable[[pd.DataFrame], None],
    rename_notice: bool,
) -> None:
    def _close() -> None:
        st.session_state.pop(dialog_key, None)

    @st.dialog(f"Excel 붙여넣기 · {table_name}", width="large", on_dismiss=_close)
    def _body() -> None:
        # 붙여넣기를 적용하면 원본이 바뀌어 표의 편집 상태를 비운다. 버리기 전에 말한다.
        if editor_has_edits(editor_key):
            st.warning(PASTE_DROPS_EDITS_NOTICE)
        if rename_notice:
            st.caption(RENAME_NOTICE)
        imported = render_reference_clipboard_form(
            data,
            table_name=table_name,
            key_columns=dimensions,
            file_name=file_name,
            key=f"{editor_key}_csv",
        )
        if imported is None:
            return
        try:
            on_paste(imported)
        except (KeyError, ValueError) as exc:
            st.error(str(exc))
            return
        _close()
        st.rerun()

    _body()


def _notice_key(editor_key: str) -> str:
    return f"{editor_key}__notice"


def editor_notice(editor_key: str) -> DeltaGenerator | None:
    """이 편집표의 작업 줄 바로 아래 알림 자리. 이번 회차에 그 편집표를 그렸을 때만 있다.

    적용은 표를 다 그린 뒤 페이지가 처리하므로 오류를 쓸 자리를 따로 받아야 한다. 없으면
    (숨은 탭 등) `None` 이고 부르는 쪽은 예전처럼 탭 끝에 쓴다.
    """
    slot = st.session_state.get(_notice_key(editor_key))
    return slot if isinstance(slot, DeltaGenerator) else None


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


def _render_scope(
    default_table: pd.DataFrame, visible_table: pd.DataFrame, month_columns: list[str]
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


def _visible_table(
    default_table: pd.DataFrame,
    dimensions: list[str],
    editor_key: str,
    value_labels: Mapping[str, Mapping[str, str]] | None,
    *,
    card_name: str | None,
    locked: bool,
) -> pd.DataFrame:
    """화면에 그릴 행만 남긴 표. 필터를 걸 수 없는 표는 원본 그대로다.

    필터 위젯은 사이드바 조건 카드에 선다(`card_name`). 탭이 닫혀 카드를 세우지 않는 회차
    (`card_name=None` — 적용하지 않은 편집 때문에 닫힌 탭의 표를 그리는 경우)에는 세션에 남은
    선택만 읽는다. `locked` 면 카드의 필터를 잠근다.

    `value_labels` 는 필터 옵션의 **표시**에만 쓴다. 선택값·거른 프레임·편집표·왕복 CSV 는
    모두 원본 공정명이다. 표시명 조회는 페이지가 하고 이 모듈은 받은 매핑만 넘긴다.
    """
    if default_table.empty or any(column not in default_table.columns for column in dimensions):
        return default_table
    key_prefix = f"{editor_key}_filter"
    if card_name is None:
        visible = apply_column_filters(default_table, dimensions, key_prefix=key_prefix)
    else:
        with table_card(card_name):
            visible = render_column_filter_controls(
                default_table,
                dimensions,
                key_prefix=key_prefix,
                column_labels=COLUMN_LABELS,
                value_labels=value_labels,
                disabled=locked,
            )
            if locked:
                st.caption(FILTER_LOCKED_NOTICE)
    # data_editor 의 편집 델타는 행 '위치' 기반이라 보이는 행 집합이 바뀌면 남아 있던 편집이
    # 다른 행에 붙는다. 위젯을 만들기 전에 버려야 그 오염이 저장까지 가지 않는다.
    signature_key = f"{editor_key}_filter_rows"
    signature = hash(tuple(visible.index))
    previous = st.session_state.get(signature_key)
    # 처음 적는 회차는 바뀐 것이 아니다 — 거기서 버리면 편집표가 처음부터 새 세대로 선다.
    if previous is not None and previous != signature:
        discard_editor(editor_key)
    st.session_state[signature_key] = signature
    return visible
