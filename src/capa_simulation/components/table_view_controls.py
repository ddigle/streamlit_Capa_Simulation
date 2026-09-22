# Purpose: 편집표의 보이는 컬럼과 행을 고르게 하고, 편집분을 원본 전체에 되머지한다.

"""보기만 좁히고 저장은 전체로.

컬럼이 서른 개가 넘는 표에서 지금 손볼 몇 개만 보고 싶다는 요구는 자연스럽다. 그런데
**편집표에 필터를 걸면 저장이 위험해진다** — 이 표들은 편집 결과가 곧 다음 불변 리비전의
전부라서, 걸러진 행이 빠진 채로 저장되면 그 행은 되돌릴 수 없이 사라진다.

그래서 두 가지를 갈라 둔다.

- **컬럼 숨김은 무해하다.** `st.data_editor` 는 `column_config={컬럼: None}` 으로 감춘
  컬럼도 값을 그대로 반환한다(브라우저 밖 `AppTest` 로 실측). 감춰도 저장에 영향이 없다.
- **행 필터는 되머지가 받쳐야 한다.** 거른 프레임은 원본 인덱스를 그대로 들고 있고,
  필터가 걸린 동안에는 행 추가·삭제를 막아(`num_rows="fixed"`) 편집표의 인덱스가 원본의
  부분집합으로 남는다. 그 인덱스 자리에만 편집값을 얹으면 걸러진 행은 손대지 않는다.

행 추가·삭제를 막는 것은 이 화면에 새로 생기는 제약이다. 부분만 보이는 상태에서 「삭제」는
「이 행을 지운다」와 「그냥 안 보인다」를 구분할 수 없기 때문이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
import streamlit as st

FILTERED_NOTICE = (
    "필터가 걸려 있어 행 추가·삭제를 잠갔습니다. 보이지 않는 행도 저장에는 그대로 "
    "들어갑니다. 행을 더하거나 지우려면 필터를 비우세요."
)
MAX_FILTER_OPTIONS = 200


@dataclass(frozen=True)
class TableView:
    """보기 설정이 적용된 편집표 한 벌."""

    frame: pd.DataFrame
    hidden_columns: tuple[str, ...] = ()
    filtered: bool = False
    column_config: Mapping[str, None] = field(default_factory=dict)

    @property
    def row_mode(self) -> Literal["fixed", "dynamic"]:
        """필터가 걸린 동안에는 행을 더하거나 지울 수 없다."""
        return "fixed" if self.filtered else "dynamic"


def _options(data: pd.DataFrame, column: str) -> list[str]:
    values = data[column].dropna().astype(str).str.strip()
    return sorted(value for value in values.unique().tolist() if value)


def render_table_view_controls(
    data: pd.DataFrame,
    *,
    key_prefix: str,
    editor_key: str,
    filter_columns: Sequence[str],
    locked_columns: Sequence[str] = (),
    label: str = "표 보기 설정",
    expanded: bool = False,
) -> TableView:
    """컬럼 선택과 행 필터를 그리고 그 결과를 돌려준다.

    `locked_columns` 는 감출 수 없는 컬럼이다 — 키와 필수 입력이 화면에서 사라지면
    사용자가 무엇을 고치고 있는지 알 수 없고, 새 행을 만들 수도 없다.

    `expanded` 는 이 설정이 **이미 한 번 접혀 있는 자리**(popover 안)에 들어갈 때 편다.
    접힌 것을 또 접으면 「볼 컬럼」 하나를 고르는 데 두 번을 눌러야 한다.
    """
    if data.empty:
        return TableView(data)

    columns = list(data.columns)
    locked = [column for column in locked_columns if column in columns]
    hideable = [column for column in columns if column not in locked]
    shown_key = f"{key_prefix}_columns"

    with st.expander(label, icon=":material/view_column:", expanded=expanded):
        shown = st.multiselect(
            "볼 컬럼",
            options=hideable,
            default=st.session_state.get(shown_key, hideable),
            key=shown_key,
            persist_state="session",
            help="고정 컬럼은 여기서 감출 수 없습니다. 감춘 컬럼의 값도 그대로 저장됩니다.",
        )
        selections: dict[str, list[str]] = {}
        available = [column for column in filter_columns if column in columns]
        if available:
            with st.container(horizontal=True, gap="small"):
                for column in available:
                    options = _options(data, column)
                    # 값이 수백 가지인 컬럼(호기 등)은 다중선택이 오히려 못 쓴다.
                    if not options or len(options) > MAX_FILTER_OPTIONS:
                        continue
                    selections[column] = st.multiselect(
                        column,
                        options=options,
                        placeholder="전체",
                        key=f"{key_prefix}_filter_{column}",
                        persist_state="session",
                        width=220,
                    )

    visible = data
    for column, chosen in selections.items():
        if chosen:
            visible = visible.loc[visible[column].astype(str).str.strip().isin(chosen)]
    filtered = len(visible) != len(data)
    # `st.data_editor` 의 편집 델타는 행 **위치** 기반이다. 보이는 행 집합이 바뀌면 남아
    # 있던 편집이 다른 행에 붙는다. 위젯을 만들기 전에 버려야 그 오염이 저장까지 가지
    # 않는다. `month_editor` 가 같은 이유로 같은 일을 한다.
    signature_key = f"{key_prefix}_rows"
    signature = hash(tuple(visible.index))
    if st.session_state.get(signature_key) != signature:
        st.session_state.pop(editor_key, None)
        st.session_state[signature_key] = signature
    if filtered:
        st.caption(FILTERED_NOTICE)

    hidden = tuple(column for column in hideable if column not in shown)
    return TableView(
        frame=visible,
        hidden_columns=hidden,
        filtered=filtered,
        column_config={column: None for column in hidden},
    )


def merge_edited_rows(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    filtered: bool,
) -> pd.DataFrame:
    """거른 편집표의 값을 원본 전체에 되돌려 얹는다.

    **`filtered` 는 호출자가 알려 줘야 한다 — 인덱스로는 알아낼 수 없다.** 필터 없이 행을
    지우면 `st.data_editor` 가 인덱스를 다시 매겨 원본과 달라지는데, 그것은 「거른 편집」이
    아니라 「정말 지운 것」이다. 둘을 인덱스 모양으로 가르려 했더니 지운 행이 되살아났고,
    그 되살아난 행이 그대로 불변 리비전에 저장될 뻔했다.

    필터가 걸렸을 때만 인덱스로 맞춘다. 필터는 `.loc` 로 좁히므로 원본 인덱스가 그대로
    살아 있고, 그동안에는 행 추가·삭제를 막아 편집표가 원본의 부분집합으로 남는다. 키
    컬럼을 고쳐도 자리를 잃지 않는 것이 키 대조보다 나은 점이다.
    """
    if not filtered:
        # 편집표가 곧 전체 표다. 행 추가·삭제가 살아 있으므로 그대로 돌려준다.
        return edited
    merged = original.copy()
    shared = [column for column in edited.columns if column in merged.columns]
    known = edited.index.intersection(merged.index)
    if len(known):
        merged.loc[known, shared] = edited.loc[known, shared]
    return merged
