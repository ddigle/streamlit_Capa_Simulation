# Purpose: Space 편집기 Main 설비 모듈 묶음의 바둑판 규칙과 적용 정규화를 검사한다.

"""모듈 묶음 = 편집기에 실린 호기 가운데 Main 설비가 같은 것이 둘 이상(2026-10-23 사용자 요청).

사람이 고치는 것은 묶음 범위뿐이고 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 자동으로
선다. 규칙의 정본은 `services/space_layout_edit.tile_module_group` 이고, 적용 때
`parse_editor_apply` 가 같은 규칙으로 바로잡는다.
"""

from __future__ import annotations

import random
from typing import Any

import pandas as pd
import pytest
from test_space_layout_edit import CANVAS, FLOOR, _master, _parse, _status

from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.space_layout_edit import (
    UnitChange,
    apply_layout_edits,
    editor_inputs,
    module_grid,
    natural_name_key,
    tile_module_group,
)

TICKS = 10


def _ticks(value: float) -> int:
    return int(value * TICKS + 0.5) if value >= 0 else -int(-value * TICKS + 0.5)


def _cells(tiles: dict[str, tuple[float, float, float, float]]) -> list[tuple[int, int, int, int]]:
    return [(_ticks(x), _ticks(y), _ticks(w), _ticks(h)) for x, y, w, h in tiles.values()]


# ---------------------------------------------------------------- 규칙(파이썬 정본)


def test_four_modules_split_the_range_two_by_two_in_natural_name_order() -> None:
    """넷이면 2×2 로 범위를 똑같이 나누고, 설비명 자연 정렬로 왼→오·위→아래(첫 모듈 왼쪽 위)."""
    tiles = tile_module_group((50.0, 30.0, 20.0, 14.0), ["X-12D", "X-12B", "X-12A", "X-12C"])

    assert list(tiles) == ["X-12A", "X-12B", "X-12C", "X-12D"]
    assert tiles == {
        "X-12A": (50.0, 37.0, 10.0, 7.0),
        "X-12B": (60.0, 37.0, 10.0, 7.0),
        "X-12C": (50.0, 30.0, 10.0, 7.0),
        "X-12D": (60.0, 30.0, 10.0, 7.0),
    }


def test_the_last_column_and_bottom_row_take_the_remainder() -> None:
    """칸은 눈금으로 범위 ÷ 열(행)의 내림이고 마지막 열(오른쪽)·마지막 행(맨 아래)이 나머지를
    받는다."""
    tiles = tile_module_group((1.5, 2.0, 20.1, 14.1), ["A", "B", "C", "D"])

    assert tiles == {
        "A": (1.5, 9.1, 10.0, 7.0),
        "B": (11.5, 9.1, 10.1, 7.0),
        "C": (1.5, 2.0, 10.0, 7.1),
        "D": (11.5, 2.0, 10.1, 7.1),
    }


def test_two_modules_sit_side_by_side_and_three_leave_the_last_cell_empty() -> None:
    assert module_grid(2) == (2, 1) and module_grid(3) == (2, 2) and module_grid(4) == (2, 2)
    assert module_grid(5) == (3, 2) and module_grid(9) == (3, 3) and module_grid(10) == (4, 3)

    assert tile_module_group((0.0, 0.0, 24.0, 7.0), ["M-2", "M-1"]) == {
        "M-1": (0.0, 0.0, 12.0, 7.0),
        "M-2": (12.0, 0.0, 12.0, 7.0),
    }
    three = tile_module_group((0.0, 0.0, 20.0, 14.0), ["A", "B", "C"])
    # 오른쪽 아래 칸이 빈다 — 그래도 바깥 상자는 범위 그대로다.
    assert three == {
        "A": (0.0, 7.0, 10.0, 7.0),
        "B": (10.0, 7.0, 10.0, 7.0),
        "C": (0.0, 0.0, 10.0, 7.0),
    }


def test_a_range_thinner_than_a_tick_per_cell_grows_up_and_right() -> None:
    """칸마다 최소 크기는 저장 정밀도 한 눈금(0.1)이다 — 더 작은 범위는 오른쪽·위로 넓힌다."""
    tiles = tile_module_group((3.0, 4.0, 0.1, 0.0), ["A", "B", "C", "D"])

    assert _cells(tiles) == [(30, 41, 1, 1), (31, 41, 1, 1), (30, 40, 1, 1), (31, 40, 1, 1)]


def test_natural_order_reads_numbers_as_numbers_and_ignores_case() -> None:
    names = ["SMP-12D", "SMP-12b", "SMP-2A", "SMP-12A", "smp-12C", "SMP-02A", "SMP-12"]

    assert sorted(names, key=natural_name_key) == [
        "SMP-02A",
        "SMP-2A",
        "SMP-12",
        "SMP-12A",
        "SMP-12b",
        "smp-12C",
        "SMP-12D",
    ]


def test_cells_fill_the_range_without_gaps_or_overlaps() -> None:
    """무작위 범위·모듈 수에서 칸은 눈금으로 서로 겹치지 않고, 칸이 다 차면 범위를 꼭 덮는다.
    빈 칸이 있어도 바깥 상자는 범위다(첫 행이 다 차고 마지막 행에 하나는 있다)."""
    rnd = random.Random(20261023)
    for _ in range(400):
        count = rnd.randint(2, 16)
        box = (
            round(rnd.uniform(0, 300), 1),
            round(rnd.uniform(0, 300), 1),
            round(rnd.uniform(0.1, 120), 1),
            round(rnd.uniform(0.1, 120), 1),
        )
        cells = _cells(tile_module_group(box, [f"M-{index}" for index in range(count)]))
        cols, rows = module_grid(count)
        width, height = max(_ticks(box[2]), cols), max(_ticks(box[3]), rows)
        for index, (x, y, w, h) in enumerate(cells):
            assert w >= 1 and h >= 1
            for ox, oy, ow, oh in cells[index + 1 :]:
                assert not (x < ox + ow and ox < x + w and y < oy + oh and oy < y + h)
        left, bottom = _ticks(box[0]), _ticks(box[1])
        assert min(x for x, _, _, _ in cells) == left
        assert min(y for _, y, _, _ in cells) == bottom
        assert max(x + w for x, _, w, _ in cells) == left + width
        assert max(y + h for _, y, _, h in cells) == bottom + height
        if count == cols * rows:
            assert sum(w * h for _, _, w, h in cells) == width * height


# ---------------------------------------------------------------- 적용(서버 정규화)

GROUP_ROWS: list[dict[str, Any]] = [
    # GRP-1: 범위 (50, 30, 20 × 14) 를 2×2 로 맞게 나눈 묶음.
    {"설비명": "G1-A", "Main 설비": "GRP-1", "X좌표": 50.0, "Y좌표": 37.0, "Xsize": 10, "Ysize": 7},
    {"설비명": "G1-B", "Main 설비": "GRP-1", "X좌표": 60.0, "Y좌표": 37.0, "Xsize": 10, "Ysize": 7},
    {"설비명": "G1-C", "Main 설비": "GRP-1", "X좌표": 50.0, "Y좌표": 30.0, "Xsize": 10, "Ysize": 7},
    {"설비명": "G1-D", "Main 설비": "GRP-1", "X좌표": 60.0, "Y좌표": 30.0, "Xsize": 10, "Ysize": 7},
    # GRP-2: 옛 꼴 — 모듈 크기·자리가 제각각이다.
    {"설비명": "G2-A", "Main 설비": "GRP-2", "X좌표": 5.0, "Y좌표": 40.0, "Xsize": 8, "Ysize": 6},
    {"설비명": "G2-B", "Main 설비": "GRP-2", "X좌표": 14.0, "Y좌표": 41.0, "Xsize": 9, "Ysize": 5},
    {"설비명": "G2-C", "Main 설비": "GRP-2", "X좌표": 6.0, "Y좌표": 33.0, "Xsize": 7, "Ysize": 6},
    {"설비명": "G2-D", "Main 설비": "GRP-2", "X좌표": 15.0, "Y좌표": 30.0, "Xsize": 10, "Ysize": 9},
    # GRP-3: 한 모듈에만 상자를 그렸다(형제는 좌표가 없다).
    {
        "설비명": "G3-A",
        "Main 설비": "GRP-3",
        "X좌표": 75.0,
        "Y좌표": 40.0,
        "Xsize": 20,
        "Ysize": 12,
    },
    {"설비명": "G3-B", "Main 설비": "GRP-3", "X좌표": None, "Y좌표": None},
    {"설비명": "G3-C", "Main 설비": "GRP-3", "X좌표": None, "Y좌표": None},
    {"설비명": "G3-D", "Main 설비": "GRP-3", "X좌표": None, "Y좌표": None},
]


def _groups() -> tuple[pd.DataFrame, tuple[dict[str, Any], ...]]:
    master = _master(*GROUP_ROWS)
    return master, editor_inputs(_status(master), floor=FLOOR).items


def _placed(unit_id: str, box: tuple[float, float, float, float]) -> dict[str, Any]:
    x, y, w, h = box
    return {"id": unit_id, "placed": True, "x": x, "y": y, "w": w, "h": h}


def _by_id(changes: tuple[UnitChange, ...]) -> dict[str, tuple[Any, ...]]:
    return {
        change.unit_id: (change.placed, change.x, change.y, change.w, change.h, change.move_to)
        for change in changes
    }


def test_the_editor_gets_every_module_of_a_group_boxed_on_one_module() -> None:
    _, items = _groups()
    by_id = {item["id"]: item for item in items}

    assert {by_id[name]["placed"] for name in ("G3-B", "G3-C", "G3-D")} == {False}
    assert {by_id[name]["group"] for name in ("G3-A", "G3-B", "G3-C", "G3-D")} == {"GRP-3"}


def test_a_moved_group_a_hair_off_the_rule_is_corrected_to_it() -> None:
    """브라우저 값이 규칙과 한 끝 다르면 거부하지 않고 규칙 값으로 바로잡는다."""
    master, items = _groups()
    payload = {
        "changes": [
            _placed("G1-A", (55.0, 37.0, 10.0, 7.0)),
            _placed("G1-B", (64.9, 37.0, 10.0, 7.0)),
            _placed("G1-C", (55.0, 30.0, 10.0, 7.0)),
            _placed("G1-D", (65.0, 30.0, 10.0, 7.0)),
        ]
    }

    applied = _parse(payload, master, editor_items=items)

    assert _by_id(applied.changes) == {
        "G1-A": (True, 55.0, 37.0, 10.0, 7.0, None),
        "G1-B": (True, 65.0, 37.0, 10.0, 7.0, None),
        "G1-C": (True, 55.0, 30.0, 10.0, 7.0, None),
        "G1-D": (True, 65.0, 30.0, 10.0, 7.0, None),
    }
    # 정규화를 주지 않으면(옛 호출) 받은 값 그대로다.
    assert _by_id(_parse(payload, master).changes)["G1-B"][1] == 64.9


def test_an_untouched_old_group_is_left_as_it_is() -> None:
    """바둑판이 아닌 옛 묶음은 읽을 때도, 다른 호기를 고친 적용에서도 바뀌지 않는다."""
    master, items = _groups()

    applied = _parse(
        {"changes": [_placed("EQ-01", (12.0, 10.0, 12.0, 7.0))]}, master, editor_items=items
    )

    assert list(_by_id(applied.changes)) == ["EQ-01"]
    assert _parse({"changes": []}, master, editor_items=items).changes == ()


def test_moving_an_old_group_regrids_it_inside_its_new_outer_box() -> None:
    """옛 묶음을 처음 옮기면 바깥 상자가 범위가 되어 바둑판으로 다시 선다. 편집기는 이미 그렇게
    보내지만, 모듈 하나만 온 적용도 묶음 전체를 같은 규칙으로 놓는다."""
    master, items = _groups()
    # 옛 바깥 상자 (5, 30)–(25, 46) 를 오른쪽으로 2 옮긴 범위.
    expected = tile_module_group((7.0, 30.0, 20.0, 16.0), ["G2-A", "G2-B", "G2-C", "G2-D"])
    from_editor = {"changes": [_placed(name, box) for name, box in expected.items()]}

    applied = _parse(from_editor, master, editor_items=items)

    assert {name: change[1:5] for name, change in _by_id(applied.changes).items()} == expected
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})

    # 모듈 하나(G2-A)만 옮겨 왔어도 그 뒤의 바깥 상자로 넷을 모두 다시 놓는다.
    single = _parse(
        {"changes": [_placed("G2-A", (3.0, 40.0, 8.0, 6.0))]}, master, editor_items=items
    )
    outer = tile_module_group((3.0, 30.0, 22.0, 16.0), ["G2-A", "G2-B", "G2-C", "G2-D"])
    assert {name: change[1:5] for name, change in _by_id(single.changes).items()} == outer


def test_coordless_siblings_land_in_their_cells_when_the_group_moves() -> None:
    """한 모듈에만 상자를 그린 묶음을 옮기면 좌표 없던 형제가 그때 제 칸에 함께 놓인다."""
    master, items = _groups()
    expected = tile_module_group((70.0, 40.0, 20.0, 12.0), ["G3-A", "G3-B", "G3-C", "G3-D"])

    applied = _parse(
        {"changes": [_placed("G3-A", (70.0, 40.0, 20.0, 12.0))]}, master, editor_items=items
    )

    assert {name: change[1:5] for name, change in _by_id(applied.changes).items()} == expected
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    rows = result.set_index("설비명").loc[["G3-A", "G3-B", "G3-C", "G3-D"]]
    assert rows["X좌표"].notna().all() and set(rows["동"]) == {"C1"}
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


def test_a_group_split_by_the_browser_is_refused() -> None:
    """편집기는 모듈 하나만 빼거나 보내는 길을 막는다 — 갈라진 묶음이 오면 적용 전체를 거부한다."""
    master, items = _groups()

    with pytest.raises(ValueError, match="묶음째"):
        _parse(
            {"changes": [{"id": "G1-A", "placed": False, "w": 10, "h": 7}]},
            master,
            editor_items=items,
        )
    with pytest.raises(ValueError, match="G1-B 만 따로"):
        _parse(
            {
                "changes": [
                    _placed("G1-A", (51.0, 37.0, 10.0, 7.0)),
                    {
                        "id": "G1-B",
                        "placed": True,
                        "x": 60,
                        "y": 37,
                        "w": 10,
                        "h": 7,
                        "moveTo": "C2 2F",
                    },
                ]
            },
            master,
            editor_items=items,
        )


def test_a_group_sent_whole_to_the_tray_or_another_floor_is_not_regridded() -> None:
    master, items = _groups()
    names = ["G1-A", "G1-B", "G1-C", "G1-D"]

    tray = _parse(
        {"changes": [{"id": name, "placed": False, "w": 10, "h": 7} for name in names]},
        master,
        editor_items=items,
    )
    sent = _parse(
        {
            "changes": [
                {**_placed(name, (50.0 + 10 * (index % 2), 30.0, 10.0, 7.0)), "moveTo": "C2 2F"}
                for index, name in enumerate(names)
            ]
        },
        master,
        editor_items=items,
    )

    assert {change[0] for change in _by_id(tray.changes).values()} == {False}
    assert {change[5] for change in _by_id(sent.changes).values()} == {("C2", "2F")}
    assert len(tray.changes) == len(sent.changes) == 4


def test_a_regridded_group_never_leaves_the_canvas() -> None:
    """칸마다 한 눈금으로 넓힌 범위가 영역 밖이면 바로잡지 못하고 거부한다(편집기는 영역 안으로
    민다)."""
    master, items = _groups()
    thin = [_placed(name, (99.9, 30.0, 0.1, 0.1)) for name in ["G1-A", "G1-B", "G1-C", "G1-D"]]

    with pytest.raises(ValueError, match="묶음 범위가 편집 영역"):
        _parse({"changes": thin}, master, editor_items=items)
