# Purpose: 고름 하나와 이름(·순서)을 바로 고치는 편집표의 미저장 초안·접기·위젯 key 를 둔다.

"""시나리오 관리 목록 관리의 두 편집표(시나리오 목록·리비전 표)가 함께 쓰는 초안 장치.

편집표(`st.data_editor`)의 편집은 **행 위치**로 남는다. key 가 같으면 다른 세션이 목록 차례를 바꿔도
브라우저가 옛 위치의 편집을 새 차례의 행에 되보낸다. 또 편집을 버리는 길(`discard_editor` — key
세대를 올린다)은 모든 편집을 함께 버린다. 그래서

- 고친 값은 회차마다 **행 id 로** 세션 초안(`TableDraft`)에 접어 둔다(`fold_edits`).
- 위젯 key 에 그 회차 행 id 차례의 지문을 싣는다(`table_widget_key`). 차례가 바뀌면 새 위젯으로
  서고 초안이 id 로 값을 다시 싣는다 — 옛 위치의 편집이 다른 행에 붙지 않는다.
- 고름은 하나만이다. 두 줄이 골라지면 새로 고른 줄만 남기고 표를 다시 세운다(`remount_table` —
  초안을 먼저 적고 세대를 올린다). 이름·순서 편집은 초안에 있어 잃지 않는다.
- 순서 칸에 숫자를 넣으면 그 자리로 끼워 넣고(나머지는 한 칸씩 밀린다) 표를 그 차례로 다시
  세운다. 칸은 늘 1..n 이라 중복·빈 번호가 생기지 않는다.

다시 세우는 일은 **위젯을 그리기 전에** 한다(`settle_table`). 회차 머리에서 브라우저가 보낸 위젯
상태를 읽어 접고, 다시 세워야 하면 세대를 올린 새 key 로 그린다 — 본문 `st.rerun()` 이 없다. 단추
콜백은 같은 접기를 쓰기 없이 다시 해(`peek_table`) 누른 회차의 편집까지 본다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

import streamlit as st

from capa_simulation.components.editor_state import discard_editor, editor_widget_key


@dataclass(frozen=True)
class TableDraft:
    """편집표 하나의 미저장 초안. 모두 행 id 로 적는다.

    `names` 는 저장된 이름과 다르게 고친 이름(앞뒤 공백을 뗀 글)이다. `order` 는 고친 화면 차례이고
    저장 차례 그대로면 `None` 이다. `order_base` 는 순서를 처음 고친 회차의 저장 차례 — 저장할 때
    지금 차례와 견줘 그 사이 다른 곳에서 바뀌었으면 쓰지 않는다. `picked` 는 고른 행 하나다.
    """

    names: dict[str, str] = field(default_factory=dict)
    order: tuple[str, ...] | None = None
    order_base: tuple[str, ...] | None = None
    picked: str | None = None


@dataclass(frozen=True)
class TableColumns:
    """편집표의 칸 이름 — 고름 체크, 이름 글, (있으면) 순서 숫자."""

    pick: str
    name: str
    order: str | None = None


def draft_session_key(key: str) -> str:
    """초안이 사는 세션 칸."""
    return f"{key}__draft"


def shown_session_key(key: str) -> str:
    """지난 회차에 그린 편집표(`ShownTable`)가 사는 세션 칸."""
    return f"{key}__shown"


@dataclass(frozen=True)
class ShownTable:
    """지난 회차에 그린 편집표 — 위젯 key 와 그 행 차례. 브라우저의 위치 편집은 이 차례로 읽는다."""

    widget_key: str
    rows: tuple[str, ...]


def load_draft(key: str) -> TableDraft:
    held = st.session_state.get(draft_session_key(key))
    return held if isinstance(held, TableDraft) else TableDraft()


def store_draft(key: str, draft: TableDraft) -> None:
    st.session_state[draft_session_key(key)] = draft


def shown_table(key: str) -> ShownTable | None:
    """지난 회차에 그린 편집표. 아직 그린 적이 없으면 `None`."""
    held = st.session_state.get(shown_session_key(key))
    return held if isinstance(held, ShownTable) else None


def remount_table(key: str, draft: TableDraft) -> None:
    """초안을 적고 편집표를 새 위젯으로 세운다. 브라우저의 위치 편집은 버리고 초안이 값을 싣는다."""
    store_draft(key, draft)
    discard_editor(key)
    st.session_state.pop(shown_session_key(key), None)


def forget_table_edits(key: str) -> None:
    """이름·순서 편집만 버린다. 고른 행은 남긴다(「편집 버리기」·저장 성공)."""
    remount_table(key, TableDraft(picked=load_draft(key).picked))


def forget_table(key: str) -> None:
    """고른 행까지 모두 버린다(편집표의 주인이 바뀔 때)."""
    remount_table(key, TableDraft())


def table_rows(draft: TableDraft, base_ids: Sequence[str]) -> tuple[str, ...]:
    """화면 행 차례. 순서를 고쳤으면 그 차례, 아니면 저장 차례다."""
    return draft.order if draft.order is not None else tuple(base_ids)


def table_widget_key(key: str, rows: Sequence[str]) -> str:
    """편집표 위젯 key — 버림 세대와 행 id 차례의 지문을 싣는다. 차례가 바뀌면 새 위젯이다."""
    digest = hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()[:10]
    return f"{editor_widget_key(key)}__{digest}"


def widget_edits(widget_key: str) -> dict[int, Mapping[str, object]]:
    """그 위젯이 브라우저에서 받은 칸 편집(행 위치 → 칸 → 값). 그리기 전에도 세션에서 읽힌다."""
    state = st.session_state.get(widget_key)
    if not isinstance(state, Mapping):
        return {}
    rows = state.get("edited_rows")
    if not isinstance(rows, Mapping):
        return {}
    return {
        int(position): change for position, change in rows.items() if isinstance(change, Mapping)
    }


def reconcile(draft: TableDraft, base_ids: Sequence[str]) -> TableDraft:
    """초안을 지금 저장된 행에 맞춘다. 사라진 행은 빼고, 새 행은 고친 차례 끝에 붙인다.

    고친 차례가 저장 차례와 같아지면 순서 편집이 없는 것이다.
    """
    present = set(base_ids)
    order = draft.order
    if order is not None:
        kept = [row_id for row_id in order if row_id in present]
        order = (*kept, *(row_id for row_id in base_ids if row_id not in set(kept)))
        if order == tuple(base_ids):
            order = None
    return TableDraft(
        names={row_id: name for row_id, name in draft.names.items() if row_id in present},
        order=order,
        order_base=draft.order_base if order is not None else None,
        picked=draft.picked if draft.picked in present else None,
    )


def with_order(draft: TableDraft, order: Sequence[str], base_ids: Sequence[str]) -> TableDraft:
    """초안의 화면 차례를 `order` 로 바꾼다. 처음 고치는 순서면 지금 저장 차례를 기준으로 적는다."""
    if tuple(order) == tuple(base_ids):
        return replace(draft, order=None, order_base=None)
    base = draft.order_base if draft.order is not None else tuple(base_ids)
    return replace(draft, order=tuple(order), order_base=base)


def move_row(order: Sequence[str], row_id: str, index: int) -> tuple[str, ...]:
    """`row_id` 를 `index` 자리로 끼워 넣는다. 나머지는 차례대로 밀린다. 끝 밖은 끝에 붙인다."""
    rest = [item for item in order if item != row_id]
    position = min(max(index, 0), len(rest))
    return (*rest[:position], row_id, *rest[position:])


def _order_number(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def fold_edits(
    draft: TableDraft,
    rows: Sequence[str],
    base_names: Mapping[str, str],
    edits: Mapping[int, Mapping[str, object]],
    columns: TableColumns,
) -> tuple[TableDraft, bool]:
    """브라우저 칸 편집을 초안에 접는다. 두 번째 값은 표를 다시 세워야 하는가다.

    `rows` 는 그 편집이 붙은 위젯을 그린 회차의 행 차례다 — 편집의 행 위치를 이것으로 id 로 바꾼다.
    이름은 저장된 이름(`base_names`)과 같아지면 초안에서 뺀다. 두 줄이 골라졌으면 초안의 고른 행이
    아닌 쪽(새로 고른 줄)을 남기고, 순서 칸을 고쳤으면 그 자리로 끼워 넣는다 — 둘 다 표를 다시
    세운다. 같은 편집을 두 번 접어도 결과가 같다. 지금 저장된 행에 맞추는 것은 `reconcile` 몫이다.
    """
    names = dict(draft.names)
    checked: list[str] = []
    moves: list[tuple[str, int]] = []
    for position, row_id in enumerate(rows):
        change = edits.get(position, {})
        if columns.name in change:
            typed = change[columns.name]
            text = "" if typed is None else str(typed).strip()
            if text == base_names.get(row_id):
                names.pop(row_id, None)
            else:
                names[row_id] = text
        if bool(change.get(columns.pick, row_id == draft.picked)):
            checked.append(row_id)
        if columns.order is not None:
            number = _order_number(change.get(columns.order))
            if number is not None:
                moves.append((row_id, number))
    remount = False
    if len(checked) > 1:
        fresh = [row_id for row_id in checked if row_id != draft.picked]
        picked = fresh[0] if fresh else draft.picked
        remount = True
    else:
        picked = checked[0] if checked else None
    order = tuple(rows)
    for row_id, number in moves:
        order = move_row(order, row_id, number - 1)
    folded = TableDraft(names=names, order=draft.order, order_base=draft.order_base, picked=picked)
    if order != tuple(rows):
        remount = True
        base = draft.order_base if draft.order is not None else tuple(rows)
        folded = replace(folded, order=order, order_base=base)
    return folded, remount


def peek_table(
    key: str, base_ids: Sequence[str], base_names: Mapping[str, str], columns: TableColumns
) -> TableDraft:
    """지금 초안 + 지난 회차에 그린 위젯의 편집. 세션에 쓰지 않는다.

    단추 콜백이 누른 회차의 편집까지 읽는다.
    """
    draft = load_draft(key)
    shown = shown_table(key)
    if shown is not None:
        draft, _ = fold_edits(
            draft, shown.rows, base_names, widget_edits(shown.widget_key), columns
        )
    return reconcile(draft, base_ids)


def settle_table(
    key: str, base_ids: Sequence[str], base_names: Mapping[str, str], columns: TableColumns
) -> tuple[TableDraft, str]:
    """편집표를 그리기 **전에** 부른다. 위젯 편집을 접어 초안에 적고, 필요하면 새 위젯으로 세운다.

    돌려준 초안의 행 차례(`table_rows`)와 위젯 key 로 그린다. 그리는 데이터는 이 초안 값이고
    브라우저는 남은 위치 편집을 그 위에 다시 얹는다 — 둘은 같은 값이다. 저장 차례가 바뀌어 위젯
    key 가 달라지면 옛 위치 편집은 버려지고 초안이 id 로 값을 다시 싣는다.
    """
    draft = load_draft(key)
    shown = shown_table(key)
    remount = False
    if shown is not None:
        draft, remount = fold_edits(
            draft, shown.rows, base_names, widget_edits(shown.widget_key), columns
        )
    draft = reconcile(draft, base_ids)
    if remount:
        remount_table(key, draft)
    else:
        store_draft(key, draft)
    return draft, mark_shown(key, draft, base_ids)


def mark_shown(key: str, draft: TableDraft, base_ids: Sequence[str]) -> str:
    """이번 회차에 그릴 위젯 key 를 정하고 그 행 차례와 함께 적는다(다음 회차의 접기가 읽는다)."""
    rows = table_rows(draft, base_ids)
    widget_key = table_widget_key(key, rows)
    st.session_state[shown_session_key(key)] = ShownTable(widget_key=widget_key, rows=rows)
    return widget_key


def repick_table(key: str, draft: TableDraft, picked: str | None, base_ids: Sequence[str]) -> str:
    """고른 행을 코드가 바꾼다(올라와 있는 리비전이 바뀜 등). 브라우저의 고름 편집과 겹치지 않게
    새 위젯으로 세우고, 이번 회차에 그릴 위젯 key 를 돌려준다."""
    remount_table(key, replace(draft, picked=picked))
    return mark_shown(key, load_draft(key), base_ids)


def changed_names(draft: TableDraft, base_names: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """저장할 이름 바꾸기 — 행 id → (지금 저장된 이름, 새 이름)."""
    return {
        row_id: (base_names[row_id], name)
        for row_id, name in draft.names.items()
        if row_id in base_names and name != base_names[row_id]
    }


def moved_count(draft: TableDraft, base_ids: Sequence[str]) -> int:
    """저장 차례와 자리가 다른 행 수."""
    if draft.order is None:
        return 0
    return sum(1 for shown, stored in zip(draft.order, base_ids, strict=False) if shown != stored)
