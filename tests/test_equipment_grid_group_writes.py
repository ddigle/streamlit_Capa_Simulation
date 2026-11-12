# Purpose: 모듈 묶음 한 줄 고침이 계획 · 표 출납 · 되돌리기에서 형제 줄을 함께 바꾸는지 본다.

"""모듈 묶음 한 줄을 고치면 형제 줄이 같이 바뀐다(2026-11-12 사용자 답 3-1 · 3-3 · 3-5).

`equipment_units.plan_group_writes` 는 고친 칸 `(줄 자리, 칸, 값)` 을 쓰기 계획으로 편다 — 표의
칸 · 붙여넣기 · 값 넣기와 Space 「호기 정보」 창이 같이 부른다. 같이 바뀌는 칸은
`UNIT_SHARED_COLUMNS`(읽기 막음 여섯 + 저장 때만 막음 일곱 + 레이아웃표시)이고, 묶음은
`module_group_rows`(Main 설비가 같은 행이 표 전체에서 둘 이상) 한 판정이다. 잠금과 값 다듬기는
호출부 몫이라 여기서는 보지 않는다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
import test_equipment_grid_ops as ops
from grid_fake import Calls, grid_results, install_fake_grid, last, load, send_ops
from test_equipment_data_workspace import _app as workspace_app
from test_equipment_data_workspace import _save as workspace_save
from test_equipment_grid_ops import _apply as ops_apply
from test_equipment_grid_ops import _id as ops_id
from test_equipment_grid_ops import _op as ops_op
from test_equipment_grid_ops import _saved as ops_saved
from test_space_module_group_save import _fix_first as save_fix_first
from test_space_module_group_save import _saved as save_saved
from test_space_module_group_save import _seed as save_seed

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import BUFFER_KEY
from capa_simulation.components.equipment_import_dialog import _master_has_errors
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services import equipment_grid as eg
from capa_simulation.services import space_layout_edit
from capa_simulation.services.equipment_contract import UNIT_SHARED_COLUMNS
from capa_simulation.services.equipment_units import (
    GroupPlan,
    GroupWrite,
    module_group_rows,
    parent_equipment,
    plan_group_writes,
)
from capa_simulation.services.equipment_validation import equipment_master_issues


def _master() -> pd.DataFrame:
    """GRP-1 넷(표 차례가 섞임 — 다른 층 · 숨은 모듈 포함), GRP-2 둘, 한 줄 묶음 LONE, 비모듈 둘."""
    rows: list[dict[str, Any]] = [
        {"설비명": "G1-A", "Main 설비": "GRP-1", "동": "C1", "층": "1F", "레이아웃표시": "Y"},
        {"설비명": "EQ-01", "Main 설비": None, "동": "C1", "층": "1F", "레이아웃표시": "Y"},
        {"설비명": "G1-B", "Main 설비": " GRP-1 ", "동": "C1", "층": "1F", "레이아웃표시": "Y"},
        {"설비명": "G2-A", "Main 설비": "GRP-2", "동": "C2", "층": "2F", "레이아웃표시": "Y"},
        {"설비명": "G1-C", "Main 설비": "GRP-1", "동": "C2", "층": "3F", "레이아웃표시": "Y"},
        {"설비명": "L-A", "Main 설비": "LONE", "동": "C1", "층": "1F", "레이아웃표시": "Y"},
        {"설비명": "G2-B", "Main 설비": "GRP-2", "동": "C2", "층": "2F", "레이아웃표시": "Y"},
        {"설비명": "G1-D", "Main 설비": "GRP-1", "동": "C1", "층": "1F", "레이아웃표시": "N"},
        {"설비명": "EQ-02", "Main 설비": "", "동": "C1", "층": "1F", "레이아웃표시": "Y"},
    ]
    return pd.DataFrame(rows)


GRP_1 = (0, 2, 4, 7)
GRP_2 = (3, 6)


# ------------------------------------------------------------------ 묶음 판정


def test_the_parent_is_trimmed_and_a_blank_one_is_missing() -> None:
    parents = parent_equipment(_master())

    assert parents.iloc[2] == "GRP-1"
    assert all(pd.isna(parents.iloc[i]) for i in (1, 8))
    lone = pd.DataFrame({"설비명": ["EQ-01"]})
    assert parent_equipment(lone).isna().all()


def test_a_group_needs_two_rows_and_is_judged_in_one_place() -> None:
    groups = module_group_rows(_master())
    names = groups.fillna("").tolist()

    assert [i for i, name in enumerate(names) if name == "GRP-1"] == list(GRP_1)
    assert [i for i, name in enumerate(names) if name == "GRP-2"] == list(GRP_2)
    # 한 줄 묶음 · 비모듈 줄은 묶음 밖이다.
    assert all(pd.isna(groups.iloc[i]) for i in (1, 5, 8))
    # Space 쪽 옛 자리 이름은 같은 함수다 — 판정이 둘로 갈리지 않는다.
    assert space_layout_edit.module_group_rows is module_group_rows


# ------------------------------------------------------------------ 같이 쓰기 계획


@pytest.mark.parametrize("column", UNIT_SHARED_COLUMNS)
def test_a_shared_column_spreads_to_every_sibling_in_table_order(column: str) -> None:
    """같이 바뀌는 14칸 — 묶음 한 줄을 고치면 표 전체의 형제(다른 층 · 숨은 모듈 포함)를 표 차례로
    쓴다."""
    plan = plan_group_writes(_master(), [(4, column, "값")])

    assert plan == GroupPlan(
        writes=(GroupWrite(group="GRP-1", column=column, value="값", rows=GRP_1, asked=(4,)),),
        split=(),
    )


@pytest.mark.parametrize("column", ["사용기준", "Main 설비", "반입일정", "X좌표", "메모1"])
def test_a_column_outside_the_shared_set_writes_its_row_only(column: str) -> None:
    """사용기준(답 3-3 「사용기준만 제외」) · Main 설비(답 3-2 move — 그 모듈만 옮긴다) · 일정 ·
    좌표 · 메모는 그 줄 하나다."""
    plan = plan_group_writes(_master(), [(2, column, "값")])

    assert plan.writes == (GroupWrite(None, column, "값", rows=(2,), asked=(2,)),)
    assert plan.split == ()


@pytest.mark.parametrize("position", [1, 5, 8])
def test_a_row_outside_a_group_writes_itself_only(position: int) -> None:
    """비모듈 줄 · 한 줄 묶음(Main 설비가 그 줄뿐)은 형제가 없다."""
    plan = plan_group_writes(_master(), [(position, "담당자", "담당B")])

    assert plan.writes == (GroupWrite(None, "담당자", "담당B", (position,), (position,)),)


def test_the_same_value_on_several_rows_of_a_group_is_one_write() -> None:
    """붙여넣기 · 값 넣기가 묶음 줄 둘에 같은 값을 넣으면 쓰기 하나다 — 고친 줄은 넘긴 차례다."""
    plan = plan_group_writes(_master(), [(7, "동", "C3"), (0, "동", "C3"), (7, "동", "C3")])

    assert plan.writes == (GroupWrite("GRP-1", "동", "C3", rows=GRP_1, asked=(7, 0)),)
    assert plan.split == ()


def test_a_blank_and_a_missing_value_agree() -> None:
    plan = plan_group_writes(_master(), [(0, "Maker", pd.NA), (2, "Maker", ""), (4, "Maker", None)])

    assert len(plan.writes) == 1 and plan.writes[0].rows == GRP_1
    assert plan.writes[0].value is pd.NA
    assert plan.split == ()


def test_different_values_for_one_group_column_are_not_spread() -> None:
    """한 번에 같은 묶음 · 같은 칸에 다른 값이 오면 같이 바꾸지 않고 받은 칸만 쓴다 — 어느 값이
    맞는지 고르지 않는다. 다른 묶음 · 다른 칸은 그대로 같이 바뀐다."""
    cells: list[tuple[int, str, object]] = [
        (0, "담당자", "담당B"),
        (3, "담당자", "담당C"),
        (2, "담당자", "담당D"),
        (0, "Maker", "M1"),
    ]

    plan = plan_group_writes(_master(), cells)

    assert plan.split == (("GRP-1", "담당자"),)
    assert plan.writes == (
        GroupWrite(None, "담당자", "담당B", (0,), (0,)),
        GroupWrite(None, "담당자", "담당D", (2,), (2,)),
        GroupWrite("GRP-2", "담당자", "담당C", GRP_2, (3,)),
        GroupWrite("GRP-1", "Maker", "M1", GRP_1, (0,)),
    )


def test_writes_keep_the_order_the_cells_first_came_in() -> None:
    plan = plan_group_writes(
        _master(), [(6, "층", "4F"), (1, "메모1", "x"), (4, "층", "4F"), (3, "층", "4F")]
    )

    assert [(w.group, w.column, w.asked) for w in plan.writes] == [
        ("GRP-2", "층", (6, 3)),
        (None, "메모1", (1,)),
        ("GRP-1", "층", (4,)),
    ]


def test_the_plan_neither_coerces_nor_checks_locks() -> None:
    """값은 호출부가 다듬어 넘긴 그대로이고, 잠금은 길마다 달라 호출부가 `rows` 로 본다."""
    value = object()

    plan = plan_group_writes(_master(), [(0, "레이아웃표시", value)])

    assert plan.writes[0].value is value and plan.writes[0].rows == GRP_1


def test_no_cells_and_an_empty_table_plan_nothing() -> None:
    assert plan_group_writes(_master(), []) == GroupPlan(writes=(), split=())
    assert plan_group_writes(_master().iloc[0:0], []) == GroupPlan(writes=(), split=())


def test_a_row_outside_the_table_is_refused() -> None:
    with pytest.raises(IndexError):
        plan_group_writes(_master(), [(99, "동", "C1")])


# ------------------------------------------------------------------ 표 출납(`apply_ops`)
#
# 합성 fleet(`sample_equipment_master`)의 줄 0 · 2 · 4 · 6 을 GRP-1, 1 · 3 을 GRP-2 로 묶은
# 저장본에서 표 한 칸 · 호기 상세(둘 다 op `cell`) · 붙여넣기 · 값 넣기가 같은 `_write_shared` 를
# 지나는지 본다.

GROUP = [0, 2, 4, 6]
PAIR = [1, 3]


def _grouped_frames() -> eg.Frames:
    saved = ops_saved()
    master = saved[1].copy()
    for name, rows in (("GRP-1", GROUP), ("GRP-2", PAIR)):
        master.loc[rows, "Main 설비"] = name
        master.loc[rows, "공정소분류"] = master.loc[rows[0], "공정소분류"]
    return (saved[0], master, saved[2])


def _grouped(
    master: pd.DataFrame | None = None, *, loaded: tuple[str, ...] = (), **changes: Any
) -> eg.GridState:
    saved = _grouped_frames()
    edited = (saved[1] if master is None else master).copy()
    state = eg.GridState(frames=(saved[0], edited, saved[2]), saved=saved, **changes)
    if loaded:
        return replace(state, loaded=loaded)
    return state


def _ids(state: eg.GridState, rows: list[int]) -> list[str]:
    return [ops_id(state, position) for position in rows]


def _column(applied: eg.GridApplied, column: str, rows: list[int]) -> list[str]:
    master = applied.state.frames[1]
    return [eg.cell_text(master.iloc[position][column]) for position in rows]


def _mixed(applied: eg.GridApplied) -> list[tuple[int, str]]:
    """묶음 갈림 규칙(여섯 · 일곱)의 막는 칸 결과 — 저장 때(`today`)."""
    issues = equipment_master_issues(applied.state.frames[1], today=ops.ANCHOR)
    return [
        (issue.position, issue.column)
        for issue in issues
        if issue.blocking and issue.rule.startswith("unit_group_mixed")
    ]


def _split(column: str, value: str) -> pd.DataFrame:
    """GRP-1 의 줄 4 만 그 칸이 다른 편집본(옛 저장본 꼴 — 저장은 막히고 읽기는 된다)."""
    master = _grouped_frames()[1].copy()
    master.loc[4, column] = value
    return master


def test_one_module_cell_changes_every_sibling_and_one_undo_takes_all_back() -> None:
    """모듈 한 줄의 동을 바꾸면 묶음 넷이 함께 바뀌고 묶음 갈림이 없다. 되돌리기 단계는 하나이고
    「한 단계 되돌리기」 한 번에 넷이 돌아온다. 알림창 한 줄은 「GRP-1 묶음 4줄 동 C2」 다."""
    state = _grouped()

    result = ops_apply(state, ops_op("cell", 1, id=ops_id(state, 2), col="동", text="C2"))

    assert _column(result, "동", GROUP) == ["C2"] * 4
    assert _column(result, "동", PAIR) == ["C1", "C1"]
    assert _mixed(result) == []
    assert len(result.state.undo) == 1 and result.changed and not result.refused
    assert result.toast == "GRP-1 묶음 4줄 동 C2"
    back = ops_apply(result.state, ops_op("undo", 2))
    assert _column(back, "동", GROUP) == ["C1"] * 4


@pytest.mark.parametrize(
    ("column", "value", "kept"),
    [("투자구분", "신규", "양산"), ("담당자", "다른 담당", "샘플 담당자")],
)
def test_putting_the_same_value_again_mends_a_split_group_on_every_path(
    column: str, value: str, kept: str
) -> None:
    """갈린 묶음(여섯 칸 투자구분 · 일곱 칸 담당자)은 한 줄에 그 줄 값을 다시 넣어도 풀린다 — 고친
    줄은 그대로라도 형제가 맞춰져 바뀐 것이다. 표 한 칸 · 호기 상세(op `cell`) · 붙여넣기 · 값
    넣기 네 길이 같다."""
    state = _grouped(_split(column, value))
    target = ops_id(state, 0)
    paths = [
        ops_op("cell", 1, id=target, col=column, text=kept),
        ops_op("paste", 1, ids=[target], cols=[column], rows=[[kept]]),
        ops_op("set", 1, ids=[target], col=column, text=kept),
    ]
    assert _mixed(ops_apply(state, ops_op("undo", 1))) != []
    for op in paths:
        result = ops_apply(state, op)
        assert result.changed, op["op"]
        assert _column(result, column, GROUP) == [kept] * 4, op["op"]
        assert _mixed(result) == [], op["op"]


def test_a_locked_sibling_refuses_the_whole_group_write_and_says_why() -> None:
    """배치 편집이 잠긴 회차 — 있는 묶음에 새로 넣은 모듈의 레이아웃표시는 그 줄은 안 잠겼지만
    형제(있던 호기)의 배치 칸이 잠겨 있다. 형제 하나라도 잠기면 그 쓰기를 통째로 넣지 않고(부분
    쓰기 없음) 알림창 경고에 잠금 까닭을 단다. 잠기지 않은 회차면 같은 op 가 다섯 줄 모두 바꾼다."""
    saved = _grouped_frames()
    joiner = saved[1].iloc[[0]].copy()
    joiner.loc[joiner.index, "설비명"] = "GRP1-NEW"
    master = pd.concat([saved[1], joiner], ignore_index=True)
    state = _grouped(master)
    new_id = ops_id(state, len(master) - 1)
    assert new_id == "n:GRP1-NEW"
    op = ops_op("cell", 1, id=new_id, col="레이아웃표시", text="N")

    refused = ops_apply(state, op, context=ops.LOCKED)

    assert refused.refused == 1 and not refused.changed
    assert refused.state.frames[1]["레이아웃표시"].tolist() == master["레이아웃표시"].tolist()
    assert refused.toast == (
        "GRP-1 묶음 — 형제 4줄의 레이아웃표시 칸이 잠겨 같이 고치지 않았습니다(배치 편집 잠금)"
    )
    taken = ops_apply(state, op)
    assert _column(taken, "레이아웃표시", [*GROUP, len(master) - 1]) == ["N"] * 5


def test_an_unreadable_value_stays_a_draft_on_its_own_row() -> None:
    """못 다듬은 글(동 「Z9」)은 그 줄 칸 초안만 생기고 형제에게 퍼지지 않는다."""
    state = _grouped()

    result = ops_apply(state, ops_op("cell", 1, id=ops_id(state, 2), col="동", text="Z9"))

    assert result.state.overlay == {eg.overlay_key(ops_id(state, 2), "동"): "Z9"}
    assert _column(result, "동", GROUP) == ["C1"] * 4


def test_a_paste_spreads_one_value_per_group_and_leaves_a_split_alone() -> None:
    """붙여넣기 — 같은 묶음 두 줄에 같은 값이면 묶음 전체가 바뀌고, 다른 값이면 받은 칸만 넣어
    빨갛게 남긴다(어느 값이 맞는지 고르지 않는다). 결과 글 꼬리가 같이 바뀐 묶음 · 칸 수와 갈린 칸
    수를 단다."""
    state = _grouped()
    ids = _ids(state, [0, 2, 1, 3])

    same = ops_apply(
        state,
        ops_op("paste", 1, ids=ids, cols=["담당자"], rows=[["가"], ["가"], ["나"], ["나"]]),
    )
    assert _column(same, "담당자", GROUP) == ["가"] * 4
    assert _column(same, "담당자", PAIR) == ["나"] * 2
    assert same.toast == "붙여넣기 4줄 → 4칸 바뀜 · 묶음 1개 2칸 같이"

    split = ops_apply(
        state, ops_op("paste", 1, ids=ids[:2], cols=["담당자"], rows=[["가"], ["다"]])
    )
    assert _column(split, "담당자", GROUP) == ["가", "다", "샘플 담당자", "샘플 담당자"]
    assert split.toast == (
        "붙여넣기 2줄 → 2칸 바뀜 · 묶음 안에 서로 다른 값이 와 같이 바꾸지 않은 칸 1"
    )


def test_a_set_over_part_of_two_groups_takes_both_whole_groups() -> None:
    """값 넣기 — 묶음 일부만 골라도 나머지가 따라간다. 고른 줄이 묶음 둘이면 둘 다다."""
    state = _grouped()

    result = ops_apply(
        state, ops_op("set", 1, ids=_ids(state, [6, 1]), col="Maker", text="새 Maker")
    )

    assert _column(result, "Maker", [*GROUP, *PAIR]) == ["새 Maker"] * 6
    assert result.toast == "값 넣기 — 2칸 바뀜 · 묶음 2개 4칸 같이"


def test_siblings_not_loaded_come_in_right_below_the_edited_row() -> None:
    """불러오지 않은 형제는 고친 줄 바로 아래에 표 차례로 끼운다 — 이미 불러온 형제는 자리
    그대로다(2026-11-12 사용자 답 3-4). 끼운 id 는 `inserted` 로 나간다. 되돌려도 끼운 줄은 남는다.
    고친 줄이 목록에 없으면(호기 상세만 연 호기) 끼우지 않는다."""
    base = _grouped()
    other, edited, loaded_sibling = (ops_id(base, k) for k in (10, 4, 6))
    state = replace(base, loaded=(other, edited, ops_id(base, 11), loaded_sibling))

    result = ops_apply(state, ops_op("cell", 1, id=edited, col="Model", text="M-9"))

    first, third = ops_id(base, 0), ops_id(base, 2)
    assert result.state.loaded == (other, edited, first, third, ops_id(base, 11), loaded_sibling)
    assert result.inserted == (first, third)
    back = ops_apply(result.state, ops_op("undo", 2))
    assert back.state.loaded == result.state.loaded and back.inserted == ()

    hidden = replace(base, loaded=(other,))
    detail_only = ops_apply(hidden, ops_op("cell", 1, id=edited, col="Model", text="M-9"))
    assert detail_only.state.loaded == (other,) and detail_only.inserted == ()
    assert _column(detail_only, "Model", GROUP) == ["M-9"] * 4


@pytest.mark.parametrize(
    ("position", "column", "text"),
    [
        (2, "Main 설비", "GRP-2"),
        (2, "사용기준", "EDP"),
        (2, "메모1", "메모"),
        (2, "반입일정", "2026-12-01"),
        (5, "담당자", "혼자"),
    ],
)
def test_other_columns_and_rows_outside_a_group_change_one_row(
    position: int, column: str, text: str
) -> None:
    """Main 설비(답 3-2 move — 그 모듈만 옮긴다) · 사용기준 · 메모 · 일정은 그 줄만, 묶음 밖 줄도
    그 줄만이다 — 알림창 묶음 글도 없다."""
    state = _grouped()
    before = state.frames[1]

    result = ops_apply(state, ops_op("cell", 1, id=ops_id(state, position), col=column, text=text))

    master = result.state.frames[1]
    changed = [
        (k, name)
        for k in range(len(master))
        for name in master.columns
        if eg.cell_text(master.iloc[k][name]) != eg.cell_text(before.iloc[k][name])
    ]
    assert changed == [(position, column)]
    assert result.toast is None and result.inserted == ()


def test_the_detail_carries_the_group_and_the_shared_columns() -> None:
    """「호기 상세」 data — 모듈 묶음(둘 이상) 줄에만 `group`(Main 설비 · 형제 포함 줄 수)이 서고,
    같이 바뀌는 14칸 자리(`sharedCols`)가 늘 실린다. 묶음 밖 줄 · 한 줄 묶음에는 없다."""
    master = _grouped_frames()[1].copy()
    master.loc[8, "Main 설비"] = "LONE"
    state = _grouped(master)
    view = eg.build_grid_view(eg.GridSource(frames=state.frames, saved=state.saved), ops.CONTEXT)

    data = eg.detail_data(view, ops_id(state, 4))
    assert data["unit"]["group"] == {"name": "GRP-1", "count": 4}
    assert [eg.GRID_COLUMNS[k].name for k in data["sharedCols"]] == list(UNIT_SHARED_COLUMNS)
    for position in (5, 8):
        assert "group" not in eg.detail_data(view, ops_id(state, position))["unit"]


def test_reverting_a_shared_cell_brings_every_sibling_back_to_its_saved_value() -> None:
    """「저장 전 변경」 의 칸 · 호기 되돌리기(G2 (가)) — 모듈 줄의 같이 바뀌는 칸이면 형제 줄의 그
    칸도 저마다의 저장본 값으로 돌린다(묶음이 갈리지 않는다). 호기 되돌리기가 Main 설비도 돌려 그
    줄이 묶음을 떠나면 남은 형제는 같이 돌리지 않는다."""
    state = _grouped()
    changed = ops_apply(state, ops_op("cell", 1, id=ops_id(state, 2), col="담당자", text="가"))
    assert _column(changed, "담당자", GROUP) == ["가"] * 4

    cell = ops_apply(changed.state, ops_op("revert", 2, id=ops_id(state, 6), col="담당자"))
    assert _column(cell, "담당자", GROUP) == ["샘플 담당자"] * 4
    assert cell.toast is not None and cell.toast.endswith(" · 묶음 1개 3칸 같이")

    unit = ops_apply(changed.state, ops_op("revert", 2, id=ops_id(state, 6), col=None))
    assert _column(unit, "담당자", GROUP) == ["샘플 담당자"] * 4

    moved = changed.state.frames[1].copy()
    moved.loc[6, "Main 설비"] = "GRP-2"
    left = ops_apply(
        replace(changed.state, frames=(changed.state.frames[0], moved, changed.state.frames[2])),
        ops_op("revert", 2, id=ops_id(state, 6), col=None),
    )
    assert _column(left, "담당자", GROUP) == ["가", "가", "가", "샘플 담당자"]


# ------------------------------------------------------------------ 설비 마스터 탭(AppTest)


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


def test_a_group_edit_in_the_master_tab_brings_its_siblings_in_and_says_one_line(
    tmp_path: Path, grid: Calls
) -> None:
    """설비 마스터 탭에서 모듈 한 줄(G1-B)의 담당자를 바꾸면 형제 셋이 함께 바뀌어 고친 줄 바로
    아래에 끼어 오고(그 회차 표 data 에 `inserted` 가 한 번 실린다), 알림창 한 줄이 「GRP-1 묶음
    4줄 담당자 담당B」 다. 저장 전 고칠 것이 없어 「리비전 저장」 이 된다."""
    path = tmp_path / "equipment.duckdb"
    repository = save_seed(path, save_saved())
    app = workspace_app(path)
    load(app, ["s:G1-B", "s:EQ-01"])

    send_ops(app, grid, {"op": "cell", "id": "s:G1-B", "col": "담당자", "text": "담당B"})

    table = last(grid, emg.GRID_KEY)
    order = ["s:G1-B", "s:G1-A", "s:G1-C", "s:G1-D", "s:EQ-01"]
    assert [row["id"] for row in table["rows"]] == order
    assert table["inserted"] == ["s:G1-A", "s:G1-C", "s:G1-D"]
    assert "GRP-1 묶음 4줄 담당자 담당B" in grid_results(app, "success")
    master = app.session_state[BUFFER_KEY][1].set_index("설비명")
    assert master.loc[["G1-A", "G1-B", "G1-C", "G1-D"], "담당자"].tolist() == ["담당B"] * 4
    app.run()
    assert last(grid, emg.GRID_KEY)["inserted"] == []
    workspace_save(app)
    assert not save_fix_first(grid)
    assert len(repository.list_revisions()) == 2


def test_a_split_group_blocks_the_save_until_one_of_its_cells_is_put_again(
    tmp_path: Path, grid: Calls
) -> None:
    """담당자가 갈린 묶음(옛 저장본 꼴 — 저장소에 바로 넣음)은 「리비전 저장」 을 막고 「저장 전
    변경」 고칠 것에 그 묶음 줄을 낸다. 묶음 한 줄에 그 줄 값을 다시 넣기만 해도 형제가 맞춰져
    저장된다(2026-11-12 사용자 답 3-3 · 설계 G4)."""
    path = tmp_path / "equipment.duckdb"
    repository = save_seed(path, save_saved())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "UPDATE equipment_ops.equipment_master_snapshot SET manager_name = '담당B' "
            "WHERE equipment_id = 'G2-A'"
        )
    app = workspace_app(path)
    workspace_save(app)
    assert "같은 Main 설비의 모듈 행은 담당자 칸이 같아야 합니다" in save_fix_first(grid)
    assert len(repository.list_revisions()) == 1

    kept = app.session_state[BUFFER_KEY][1].set_index("설비명").loc["G2-B", "담당자"]
    load(app, ["s:G2-B"])
    send_ops(app, grid, {"op": "cell", "id": "s:G2-B", "col": "담당자", "text": str(kept)})
    master = app.session_state[BUFFER_KEY][1].set_index("설비명")
    assert master.loc[["G2-A", "G2-B", "G2-C", "G2-D"], "담당자"].tolist() == [kept] * 4
    workspace_save(app)
    assert len(repository.list_revisions()) == 2


def test_the_import_refusal_hint_counts_a_split_in_a_save_only_column() -> None:
    """「엑셀·CSV로 한꺼번에」 미리보기가 막히면 편집본에 고칠 것이 있을 때 「저장 전 변경」 을 먼저
    고치라는 덧말을 붙인다 — 저장 때만 막는 일곱 칸 갈림도 고칠 것이다(저장 때 표지 `today`)."""
    baseline, master, downtime = _grouped_frames()
    split = master.copy()
    split.loc[4, "담당자"] = "다른 담당"

    assert _master_has_errors((baseline, master, downtime), {}) is False
    assert _master_has_errors((baseline, split, downtime), {}) is True
