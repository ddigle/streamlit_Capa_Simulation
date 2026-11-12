# Purpose: 모듈 묶음 같이 쓰기 계획이 형제 줄 · 한 줄 쓰기 · 한 번에 온 다른 값을 가르는지 본다.

"""모듈 묶음 한 줄을 고치면 형제 줄이 같이 바뀐다(2026-11-12 사용자 답 3-1 · 3-3 · 3-5).

`equipment_units.plan_group_writes` 는 고친 칸 `(줄 자리, 칸, 값)` 을 쓰기 계획으로 편다 — 표의
칸 · 붙여넣기 · 값 넣기와 Space 「호기 정보」 창이 같이 부른다. 같이 바뀌는 칸은
`UNIT_SHARED_COLUMNS`(읽기 막음 여섯 + 저장 때만 막음 일곱 + 레이아웃표시)이고, 묶음은
`module_group_rows`(Main 설비가 같은 행이 표 전체에서 둘 이상) 한 판정이다. 잠금과 값 다듬기는
호출부 몫이라 여기서는 보지 않는다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from capa_simulation.services import space_layout_edit
from capa_simulation.services.equipment_contract import UNIT_SHARED_COLUMNS
from capa_simulation.services.equipment_units import (
    GroupPlan,
    GroupWrite,
    module_group_rows,
    parent_equipment,
    plan_group_writes,
)


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
