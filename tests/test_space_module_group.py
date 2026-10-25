# Purpose: Space 편집기 모듈 묶음의 바둑판 규칙·JS 대조·적용 정규화·숨은 모듈·편집 길을 검사한다.

"""모듈 묶음 = 편집기에 실린 호기와 숨은 모듈 가운데 Main 설비가 같은 것이 둘 이상(2026-10-23
사용자 요청).

사람이 고치는 것은 묶음 범위뿐이고 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 자동으로
선다. 칸 자리는 지금 자리를 지키고(새로 놓을 때만 설비명 자연 정렬), 도면 대상이 아닌 형제(숨은
모듈)도 제 칸을 차지한 채 묶음과 함께 옮겨진다. 규칙의 정본은 `services/space_layout_edit` 이고
편집기 JS(`editor.js` 의 `// <module-tiling>` 구획)가 같은 값을 내는지 node 로 떼어 돌려 대조한다.
node·bun 이 없는 PC 에서는 그 대조만 건너뛰고, GitHub Actions 에서는 실패한다
(`test_intro_scene_behavior` 와 같은 규칙). 브라우저 조작 자체는 AppTest 가 못 돌리므로 모듈 하나만
편집하는 길이 막혔는지·다시 놓기를 어디서 부르는지는 자산 글자로 붙잡는다.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from datetime import date
from typing import Any

import pandas as pd
import pytest
from test_equipment_availability import _downtime
from test_space_layout_edit import CANVAS, FLOOR, _master, _parse, _status

from capa_simulation.components import space_layout_editor
from capa_simulation.services.equipment_availability import build_space_equipment_status
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.space_layout_edit import (
    UnitChange,
    apply_layout_edits,
    assign_module_cells,
    default_group_label,
    editor_inputs,
    module_cells,
    module_grid,
    module_tile_deviation,
    natural_name_key,
    tile_module_group,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
TICKS = 10
Box = tuple[float, float, float, float]


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


def test_two_and_three_modules_line_up_in_one_row_and_five_leave_a_cell_empty() -> None:
    """셋까지는 가로 한 줄(열 n·행 1 — 2026-10-23 사용자 답 「2모듈이거나 3모듈이면 가로로 일렬
    배치」), 넷부터는 거의 정사각(⌈√n⌉ 열)이다."""
    assert [module_grid(n) for n in (1, 2, 3)] == [(1, 1), (2, 1), (3, 1)]
    assert module_grid(4) == (2, 2) and module_grid(5) == (3, 2) and module_grid(6) == (3, 2)
    assert module_grid(9) == (3, 3) and module_grid(10) == (4, 3)

    assert tile_module_group((0.0, 0.0, 24.0, 7.0), ["M-2", "M-1"]) == {
        "M-1": (0.0, 0.0, 12.0, 7.0),
        "M-2": (12.0, 0.0, 12.0, 7.0),
    }
    # 셋은 한 줄로 범위 폭을 셋으로 나눈다(마지막 칸이 나머지를 받는다) — 빈 칸이 없다.
    assert tile_module_group((0.0, 0.0, 20.0, 14.0), ["C", "A", "B"]) == {
        "A": (0.0, 0.0, 6.6, 14.0),
        "B": (6.6, 0.0, 6.6, 14.0),
        "C": (13.2, 0.0, 6.8, 14.0),
    }
    five = tile_module_group((0.0, 0.0, 30.0, 14.0), list("EDCBA"))
    # 다섯은 3×2 — 오른쪽 아래 칸이 빈다. 그래도 바깥 상자는 범위 그대로다.
    assert five == {
        "A": (0.0, 7.0, 10.0, 7.0),
        "B": (10.0, 7.0, 10.0, 7.0),
        "C": (20.0, 7.0, 10.0, 7.0),
        "D": (0.0, 0.0, 10.0, 7.0),
        "E": (10.0, 0.0, 10.0, 7.0),
    }


def test_an_old_three_module_two_by_two_is_no_longer_a_tiling() -> None:
    """1·2차(셋도 2×2)로 놓인 모듈 셋 묶음은 이제 바둑판이 아니다(「3등분이 아님」) — 읽을 때는
    그대로 두고, 처음 옮기거나 키울 때 지금 바깥 상자를 범위로 삼아 한 줄로 다시 놓인다. 칸 배정은
    상자 중심에 가까운 칸이다(왼쪽 위·오른쪽 위·왼쪽 아래 → 왼쪽·가운데·왼쪽 다툼은 자연 정렬 앞이
    먼저)."""
    old: dict[str, Box | None] = {
        "T-A": (0.0, 7.0, 10.0, 7.0),
        "T-B": (10.0, 7.0, 10.0, 7.0),
        "T-C": (0.0, 0.0, 10.0, 7.0),
    }

    deviation = module_tile_deviation(old)
    assert deviation is not None and deviation > 1
    assert _relaid(old, (0.0, 0.0, 21.0, 14.0)) == {
        "T-A": (0.0, 0.0, 7.0, 14.0),
        "T-B": (14.0, 0.0, 7.0, 14.0),
        "T-C": (7.0, 0.0, 7.0, 14.0),
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


def test_cells_are_numbered_left_to_right_from_the_top_row() -> None:
    """칸 번호는 왼→오, 위→아래다(0 이 왼쪽 위). 칸 수는 열×행이라 모듈 다섯도 칸 여섯이다."""
    assert module_cells((0.0, 0.0, 30.0, 14.0), 5) == [
        (0.0, 7.0, 10.0, 7.0),
        (10.0, 7.0, 10.0, 7.0),
        (20.0, 7.0, 10.0, 7.0),
        (0.0, 0.0, 10.0, 7.0),
        (10.0, 0.0, 10.0, 7.0),
        (20.0, 0.0, 10.0, 7.0),
    ]
    assert module_cells((0.0, 0.0, 30.0, 14.0), 3) == [
        (0.0, 0.0, 10.0, 14.0),
        (10.0, 0.0, 10.0, 14.0),
        (20.0, 0.0, 10.0, 14.0),
    ]


def test_a_tiling_out_of_name_order_keeps_every_module_in_its_cell() -> None:
    """칸 모양이 맞는 바둑판이면 차례가 자연 정렬과 달라도(세로 우선·Y 위 좌표계에서 A 가 왼쪽
    아래) 바둑판이다 — 모듈마다 지금 칸을 지킨다. 자연 정렬 차례는 새로 놓을 때만이다."""
    upside = {
        "G7A": (30.0, 40.0, 10.0, 7.0),
        "G7B": (40.0, 40.0, 10.0, 7.0),
        "G7C": (30.0, 47.0, 10.0, 7.0),
        "G7D": (40.0, 47.0, 10.0, 7.0),
    }
    column_major: dict[str, Box | None] = {
        "P-12A": (50.0, 37.0, 10.0, 7.0),
        "P-12B": (50.0, 30.0, 10.0, 7.0),
        "P-12C": (60.0, 37.0, 10.0, 7.0),
        "P-12D": (60.0, 30.0, 10.0, 7.0),
    }

    assert module_tile_deviation(dict(upside)) == 0
    assert assign_module_cells(dict(upside)) == {"G7A": 2, "G7B": 3, "G7C": 0, "G7D": 1}
    assert module_tile_deviation(column_major) == 0
    assert assign_module_cells(column_major) == {"P-12A": 0, "P-12B": 2, "P-12C": 1, "P-12D": 3}
    cells = module_cells((51.0, 30.0, 20.0, 14.0), 4)
    slots = assign_module_cells(column_major)
    assert {name: cells[slot] for name, slot in slots.items()} == {
        name: (box[0] + 1.0, box[1], box[2], box[3])
        for name, box in column_major.items()
        if box is not None
    }


def test_an_old_group_takes_its_nearest_cells_and_coordless_siblings_the_rest() -> None:
    """바둑판이 아닌 옛 묶음은 상자 중심에 가까운 칸을 받고, 좌표 없는 형제는 남은 칸을 자연 정렬
    차례로 받는다. 칸 다툼은 가까운 짝 → 자연 정렬 앞 모듈 → 앞 칸 차례다."""
    assert assign_module_cells(
        {
            "G2-A": (5.0, 40.0, 8.0, 6.0),
            "G2-B": (14.0, 41.0, 9.0, 5.0),
            "G2-C": (6.0, 33.0, 7.0, 6.0),
            "G2-D": (15.0, 30.0, 10.0, 9.0),
        }
    ) == {"G2-A": 0, "G2-B": 1, "G2-C": 2, "G2-D": 3}
    # 상자가 하나뿐이면 그 상자가 곧 바깥 상자라 네 칸 중심이 모두 같은 거리다 — 그 모듈이 첫
    # 칸(왼쪽 위)을, 좌표 없는 형제가 남은 칸을 자연 정렬 차례로 받는다(한 모듈에만 그린 옛 설비).
    lone: dict[str, Box | None] = {
        "Z-D": (10.0, 0.0, 10.0, 7.0),
        "Z-A": None,
        "Z-B": None,
        "Z-C": None,
    }
    assert assign_module_cells(lone) == {"Z-D": 0, "Z-A": 1, "Z-B": 2, "Z-C": 3}
    # 상자 넷이 한 자리에 겹치면(네 칸 중심이 모두 같은 거리) 자연 정렬 차례로 칸을 나눠 갖는다.
    stacked: dict[str, Box | None] = {
        name: (0.0, 0.0, 4.0, 4.0) for name in ("Q-2", "Q-10", "Q-1", "Q-3")
    }
    assert assign_module_cells(stacked) == {"Q-1": 0, "Q-2": 1, "Q-3": 2, "Q-10": 3}


def test_the_deviation_is_zero_only_for_a_tiling() -> None:
    assert module_tile_deviation(dict(tile_module_group((3.0, 4.0, 20.1, 14.1), list("ABCD")))) == 0
    loose: dict[str, Box | None] = {"A": (0.0, 7.0, 10.0, 7.0), "B": (10.1, 7.0, 9.9, 7.0)}
    assert module_tile_deviation(loose) == 1
    assert module_tile_deviation({"A": (0.0, 7.0, 10.0, 7.0), "B": None}) is None
    assert module_tile_deviation({}) is None


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
G1 = ["G1-A", "G1-B", "G1-C", "G1-D"]


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


def _relaid(mods: dict[str, Box | None], box: Box) -> dict[str, Box]:
    """편집기가 묶음을 범위 `box` 로 다시 놓은 자리(지금 자리를 지키는 칸 배정)."""
    cells = module_cells(box, len(mods))
    return {name: cells[slot] for name, slot in assign_module_cells(mods).items()}


def test_the_editor_gets_every_module_of_a_group_boxed_on_one_module() -> None:
    _, items = _groups()
    by_id = {item["id"]: item for item in items}

    assert {by_id[name]["placed"] for name in ("G3-B", "G3-C", "G3-D")} == {False}
    assert {by_id[name]["group"] for name in ("G3-A", "G3-B", "G3-C", "G3-D")} == {"GRP-3"}


def test_a_moved_group_a_hair_off_the_rule_is_corrected_to_it() -> None:
    """브라우저 값이 칸과 한 눈금 다르면 거부하지 않고 칸 값으로 바로잡는다."""
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


def test_a_module_left_out_of_the_payload_is_fixed_only_when_it_is_off() -> None:
    """바뀐 모듈이 있는 묶음에서 바뀌지 않은 모듈은 칸과 같으면 그대로(변경에 넣지 않고), 한 눈금
    어긋나 있으면 바로잡는 변경으로 더한다."""
    master, items = _groups()

    same = _parse(
        {"changes": [_placed("G1-B", (60.0, 37.0, 10.0, 7.0))]}, master, editor_items=items
    )
    assert list(_by_id(same.changes)) == ["G1-B"]

    drifted = _master(*GROUP_ROWS[:3], {**GROUP_ROWS[3], "Xsize": 10.1})
    drift_items = editor_inputs(_status(drifted), floor=FLOOR).items
    fixed = _parse(
        {"changes": [_placed("G1-A", (50.0, 37.0, 10.0, 7.0))]}, drifted, editor_items=drift_items
    )
    assert _by_id(fixed.changes) == {
        "G1-A": (True, 50.0, 37.0, 10.0, 7.0, None),
        "G1-B": (True, 60.0, 37.0, 10.1, 7.0, None),
    }


def test_an_untouched_old_group_is_left_as_it_is() -> None:
    """바둑판이 아닌 옛 묶음은 읽을 때도, 다른 호기를 고친 적용에서도 바뀌지 않는다."""
    master, items = _groups()

    applied = _parse(
        {"changes": [_placed("EQ-01", (12.0, 10.0, 12.0, 7.0))]}, master, editor_items=items
    )

    assert list(_by_id(applied.changes)) == ["EQ-01"]
    assert _parse({"changes": []}, master, editor_items=items).changes == ()


def test_moving_an_old_group_keeps_each_module_in_its_nearest_cell() -> None:
    """옛 묶음을 처음 옮기면 편집기가 바깥 상자를 범위로 삼아 모듈마다 가까운 칸에 다시 놓는다 —
    그 값이 그대로 들어간다."""
    master, items = _groups()
    old = {
        str(item["id"]): (item["x"], item["y"], item["w"], item["h"])
        for item in items
        if item["group"] == "GRP-2"
    }
    expected = _relaid(dict(old), (7.0, 30.0, 20.0, 16.0))

    applied = _parse(
        {"changes": [_placed(name, box) for name, box in expected.items()]},
        master,
        editor_items=items,
    )

    assert {name: change[1:5] for name, change in _by_id(applied.changes).items()} == expected
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


def test_a_single_module_moved_or_resized_alone_is_refused() -> None:
    """모듈 하나만 멀리 옮기거나 키운 값(옛 편집기 탭의 Alt+끌기, 잘못된 브라우저 값)은 묶음 범위를
    넓혀 받아들이지 않고 거부한다 — 바로잡기는 한 눈금까지다."""
    master, items = _groups()

    with pytest.raises(ValueError, match="바둑판으로 나눈 칸에 서 있지 않습니다"):
        _parse({"changes": [_placed("G1-A", (0.0, 0.0, 10.0, 7.0))]}, master, editor_items=items)
    with pytest.raises(ValueError, match="바둑판으로 나눈 칸에 서 있지 않습니다"):
        _parse({"changes": [_placed("G1-B", (60.0, 37.0, 11.0, 7.0))]}, master, editor_items=items)
    with pytest.raises(ValueError, match="바둑판으로 나눈 칸에 서 있지 않습니다"):
        _parse({"changes": [_placed("G2-A", (3.0, 40.0, 8.0, 6.0))]}, master, editor_items=items)


def test_coordless_siblings_must_land_in_their_cells_when_the_group_moves() -> None:
    """한 모듈에만 상자를 그린 묶음을 옮기면 좌표 없던 형제가 그때 제 칸에 함께 놓인다(편집기가
    넷을 모두 보낸다). 상자 하나만 오면 갈라진 묶음이라 거부한다."""
    master, items = _groups()
    expected = tile_module_group((70.0, 40.0, 20.0, 12.0), ["G3-A", "G3-B", "G3-C", "G3-D"])

    applied = _parse(
        {"changes": [_placed(name, box) for name, box in expected.items()]},
        master,
        editor_items=items,
    )

    assert {name: change[1:5] for name, change in _by_id(applied.changes).items()} == expected
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    rows = result.set_index("설비명").loc[["G3-A", "G3-B", "G3-C", "G3-D"]]
    assert rows["X좌표"].notna().all() and set(rows["동"]) == {"C1"}
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})
    with pytest.raises(ValueError, match=r"G3-B, G3-C, G3-D이\(가\) 묶음 범위에 놓이지 않았습니다"):
        _parse({"changes": [_placed("G3-A", (70.0, 40.0, 20.0, 12.0))]}, master, editor_items=items)


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

    tray = _parse(
        {"changes": [{"id": name, "placed": False, "w": 10, "h": 7} for name in G1]},
        master,
        editor_items=items,
    )
    sent = _parse(
        {
            "changes": [
                {**_placed(name, (50.0 + 10 * (index % 2), 30.0, 10.0, 7.0)), "moveTo": "C2 2F"}
                for index, name in enumerate(G1)
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
    thin = [_placed(name, (99.9, 30.0, 0.1, 0.1)) for name in G1]

    with pytest.raises(ValueError, match="묶음 범위가 편집 영역"):
        _parse({"changes": thin}, master, editor_items=items)


# ---------------------------------------------------------------- 숨은 모듈(도면 대상이 아닌 형제)

STOPPED_ROWS: list[dict[str, Any]] = [
    {**row, "정지일정": "2026-09-15"} if row["설비명"] == "G1-B" else row for row in GROUP_ROWS[:4]
]


def _hidden_inputs(as_of: date) -> tuple[pd.DataFrame, Any]:
    """G1-B 에 정지일정 2026-09-15 가 있는 2×2 묶음 — 기준일이 그 뒤면 G1-B 는 도면에서 빠진다."""
    master = _master(*STOPPED_ROWS)
    return master, editor_inputs(
        build_space_equipment_status(master, _downtime(), as_of=as_of), floor=FLOOR
    )


def _shape(inputs: Any) -> dict[str, Box | None]:
    boxes: dict[str, Box | None] = {
        str(item["id"]): (item["x"], item["y"], item["w"], item["h"])
        for item in inputs.items
        if item["group"] == "GRP-1"
    }
    boxes.update(
        {
            str(ghost["id"]): (ghost["x"], ghost["y"], ghost["w"], ghost["h"])
            for ghost in inputs.ghosts
        }
    )
    return boxes


def _ghost_payload(inputs: Any, laid: dict[str, Box]) -> dict[str, Any]:
    ghosts = {str(ghost["id"]) for ghost in inputs.ghosts}
    return {
        "changes": [_placed(name, box) for name, box in laid.items() if name not in ghosts],
        "ghosts": [
            {"id": name, "x": box[0], "y": box[1], "w": box[2], "h": box[3]}
            for name, box in laid.items()
            if name in ghosts
        ],
    }


def test_a_hidden_module_keeps_its_cell_and_rides_along_with_the_group() -> None:
    """도면에서 빠진 형제(정지·반출 완료·레이아웃표시 N)는 숨은 모듈로 따로 간다. 기준일이 바뀌어도
    묶음은 넷짜리 바둑판 그대로라(「3등분이 아님」 없음) 남은 모듈이 제 칸을 지키고, 묶음을 옮기면
    숨은 모듈도 제 칸으로 함께 옮겨져 겹치지 않는다. 레이아웃표시·일정은 그대로다."""
    _, before = _hidden_inputs(date(2026, 9, 1))
    master, after = _hidden_inputs(date(2026, 10, 1))

    assert before.ghosts == ()
    assert [ghost["id"] for ghost in after.ghosts] == ["G1-B"]
    assert after.ghosts[0]["group"] == "GRP-1"
    assert "G1-B" not in {item["id"] for item in after.items}
    assert module_tile_deviation(_shape(before)) == module_tile_deviation(_shape(after)) == 0
    laid = _relaid(_shape(after), (51.0, 30.0, 20.0, 14.0))
    assert laid == {name: (box[0] + 1.0, *box[1:]) for name, box in _shape(after).items() if box}

    applied = _parse(
        _ghost_payload(after, laid),
        master,
        editor_items=after.items,
        editor_ghosts=after.ghosts,
    )

    assert sorted(_by_id(applied.changes)) == ["G1-A", "G1-C", "G1-D"]
    assert _by_id(applied.hidden_moves) == {"G1-B": (True, 61.0, 37.0, 10.0, 7.0, None)}
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    rows = result.set_index("설비명").loc[G1]
    assert rows[["X좌표", "Y좌표"]].values.tolist() == [[51, 37], [61, 37], [51, 30], [61, 30]]
    assert rows.loc["G1-B", "정지일정"] == "2026-09-15" and rows.loc["G1-B", "레이아웃표시"] == "Y"
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


def test_a_move_that_leaves_the_hidden_module_behind_is_refused() -> None:
    """보이는 모듈만 옮기고 숨은 모듈을 두고 온 적용은 바둑판이 아니라 거부한다."""
    master, after = _hidden_inputs(date(2026, 10, 1))
    laid = _relaid(_shape(after), (51.0, 30.0, 20.0, 14.0))
    payload = _ghost_payload(after, laid)

    with pytest.raises(ValueError, match="바둑판으로 나눈 칸에 서 있지 않습니다"):
        _parse(
            {"changes": payload["changes"]},
            master,
            editor_items=after.items,
            editor_ghosts=after.ghosts,
        )
    with pytest.raises(ValueError, match="이 편집기에 없는 숨은 모듈"):
        _parse(payload, master, editor_items=after.items)
    with pytest.raises(ValueError, match="숨은 모듈만 옮겨 왔습니다"):
        _parse(
            {
                "changes": [
                    {"id": name, "placed": False, "w": 10, "h": 7} for name in G1 if name != "G1-B"
                ],
                "ghosts": payload["ghosts"],
            },
            master,
            editor_items=after.items,
            editor_ghosts=after.ghosts,
        )
    with pytest.raises(ValueError, match="편집 영역"):
        _parse(
            {**payload, "ghosts": [{"id": "G1-B", "x": 95.0, "y": 37.0, "w": 10.0, "h": 7.0}]},
            master,
            editor_items=after.items,
            editor_ghosts=after.ghosts,
        )


def test_one_visible_module_with_hidden_siblings_is_still_a_group() -> None:
    """모듈 넷 가운데 셋이 레이아웃표시 N 이면 편집기에는 하나만 실리지만 그래도 넷짜리 묶음이다 —
    그 모듈 하나만 옮기거나 키운 값은 거부하고, 숨은 모듈과 함께 옮긴 값은 받는다(N 은 그대로)."""
    rows = [
        {**row, "레이아웃표시": "N"} if row["설비명"] != "G1-A" else row for row in GROUP_ROWS[:4]
    ]
    master = _master(*rows)
    inputs = editor_inputs(_status(master), floor=FLOOR)

    assert [item["id"] for item in inputs.items if item["group"]] == ["G1-A"]
    assert sorted(ghost["id"] for ghost in inputs.ghosts) == ["G1-B", "G1-C", "G1-D"]
    with pytest.raises(ValueError, match="바둑판으로 나눈 칸에 서 있지 않습니다"):
        _parse(
            {"changes": [_placed("G1-A", (52.0, 37.0, 10.0, 7.0))]},
            master,
            editor_items=inputs.items,
            editor_ghosts=inputs.ghosts,
        )
    laid = _relaid(_shape(inputs), (52.0, 30.0, 24.0, 14.0))
    applied = _parse(
        _ghost_payload(inputs, laid), master, editor_items=inputs.items, editor_ghosts=inputs.ghosts
    )
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    out = result.set_index("설비명").loc[G1]
    assert out["Xsize"].tolist() == [12.0] * 4
    assert out["레이아웃표시"].tolist() == ["Y", "N", "N", "N"]
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


@pytest.mark.parametrize("move_to", [None, "C2 2F"], ids=["빼기", "다른 층 보내기"])
def test_a_group_taken_off_after_a_move_returns_its_hidden_module_and_applies(
    move_to: str | None,
) -> None:
    """묶음을 옮기고 키운 뒤 빼거나 다른 층으로 보내면 편집기는 숨은 모듈을 처음(보낸) 자리로
    되돌린다(`restoreGhosts` — 적용값 `ghosts` 가 빈다). 옮기지 않고 바로 뺀 것과 같은 적용이라
    받아들여진다 — 빼면 숨은 모듈은 이 층 제자리에 남고, 보내면 묶음째 그 층으로 가며 X·Y 가
    비워진다(`_harmonize_groups`, 크기는 남는다). 따라 옮겨진 자리를 그대로 보낸 값은 여전히
    거부한다(묶음 없이 숨은 모듈만 옮긴 꼴)."""
    master, after = _hidden_inputs(date(2026, 10, 1))
    laid = _relaid(_shape(after), (51.0, 30.0, 24.0, 16.0))
    visible = [name for name in G1 if name != "G1-B"]
    if move_to is None:
        changes = [{"id": name, "placed": False, "w": 12.0, "h": 8.0} for name in visible]
    else:
        changes = [{**_placed(name, laid[name]), "moveTo": move_to} for name in visible]
    rode_along = _ghost_payload(after, laid)["ghosts"]

    with pytest.raises(ValueError, match="숨은 모듈만 옮겨 왔습니다"):
        _parse(
            {"changes": changes, "ghosts": rode_along},
            master,
            editor_items=after.items,
            editor_ghosts=after.ghosts,
        )
    applied = _parse(
        {"changes": changes, "ghosts": []},
        master,
        editor_items=after.items,
        editor_ghosts=after.ghosts,
    )

    assert sorted(_by_id(applied.changes)) == visible and applied.hidden_moves == ()
    result = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    rows = result.set_index("설비명").loc[G1]
    hidden = rows.loc["G1-B"]
    assert (hidden["Xsize"], hidden["Ysize"]) == (10.0, 7.0)
    assert hidden["정지일정"] == "2026-09-15" and hidden["레이아웃표시"] == "Y"
    if move_to is None:
        assert rows.loc[visible, ["X좌표", "Y좌표"]].isna().all(axis=None)
        assert rows.loc[visible, ["Xsize", "Ysize"]].values.tolist() == [[12.0, 8.0]] * 3
        assert (hidden["동"], hidden["층"], hidden["X좌표"], hidden["Y좌표"]) == (*FLOOR, 60, 37)
    else:
        assert {(row["동"], row["층"]) for _, row in rows.iterrows()} == {("C2", "2F")}
        assert rows.loc[visible, ["X좌표", "Y좌표"]].values.tolist() == [
            list(laid[name][:2]) for name in visible
        ]
        assert pd.isna(hidden["X좌표"]) and pd.isna(hidden["Y좌표"])
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


# ---------------------------------------------------------------- JS 와 대조(node)

_SECTION = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)
_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const asObject = (map) => Object.fromEntries(map)
const asMods = (boxes) => Object.entries(boxes).map(([name, box]) => (box
  ? { name, x: box[0], y: box[1], w: box[2], h: box[3], placed: true }
  : { name, placed: false }))
process.stdout.write(JSON.stringify({
  tiles: (input.tiles || []).map((c) => tileModuleGroup(c.box, c.names, 10)),
  cells: (input.cells || []).map((c) => moduleCells(c.box, c.count, 10)),
  sorted: (input.sorted || []).map((names) => [...names].sort(naturalCompare)),
  grids: (input.grids || []).map((n) => moduleGrid(n)),
  labels: (input.grids || []).map((n) => groupLabelDefault(n)),
  trays: (input.trays || []).map((sizes) => trayModuleRange(sizes, 10)),
  slots: (input.slots || []).map((boxes) => asObject(assignModuleCells(asMods(boxes), 10))),
  deviations: (input.slots || []).map((boxes) => {
    const d = tileDeviation(asMods(boxes), 10)
    return Number.isFinite(d) ? d : null
  }),
  relaid: (input.relaid || []).map((c) => {
    const mods = asMods(c.boxes)
    const slots = assignModuleCells(mods, 10)
    return relaidGroup(mods.map((m) => m.name), slots, c.from, c.to, 10)
  }),
  natural: (input.natural || []).map((names) => asObject(naturalSlots(names))),
}))
"""


def _runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


def _run_js(payload: dict[str, Any]) -> dict[str, Any]:
    match = _SECTION.search(JS)
    assert match, "editor.js 에 // <module-tiling> 구획이 없습니다"
    return _node(match.group("body") + _RUNNER, payload)


def _node(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """`source` 를 node(없으면 bun)로 돌려 표준 입력에 `payload`(JSON)를 주고 표준 출력
    JSON 을 읽는다."""
    runtime = _runtime()
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 모듈 묶음 JS 대조를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", source],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


# BMP 밖 글자(이모지·데저렛)도 섞는다 — UTF-16 단위로 견주면 파이썬과 갈린다.
_NAME_PARTS = ["SMP", "-", "GRP", "EQ", "12", "3", "007", "a", "B", "c", "가", "나", "_", "0"]
_NAME_PARTS += ["\U0001f600", "\U00010400", "\U00010428", "ｚ", "Σ", "ς", "İ", "ẞ"]


def _random_name(rnd: random.Random) -> str:
    return "".join(rnd.choice(_NAME_PARTS) for _ in range(rnd.randint(1, 6)))


def _random_box(rnd: random.Random) -> dict[str, float]:
    return {
        "x": round(rnd.uniform(-5, 400), rnd.choice([0, 1, 2, 3])),
        "y": round(rnd.uniform(-5, 400), rnd.choice([0, 1, 2, 3])),
        "w": round(rnd.uniform(0, 150), rnd.choice([0, 1, 2, 3])),
        "h": round(rnd.uniform(0, 150), rnd.choice([0, 1, 2, 3])),
    }


def _random_layout(rnd: random.Random) -> dict[str, list[float] | None]:
    """무작위 묶음 — 바둑판(이름 차례를 섞은 것), 한 눈금 흐트린 바둑판, 제각각인 옛 꼴, 좌표 없는
    형제가 섞인 꼴."""
    names = sorted({_random_name(rnd) for _ in range(rnd.randint(1, 9))})
    box = _random_box(rnd)
    cells = module_cells((box["x"], box["y"], box["w"], box["h"]), len(names))
    rnd.shuffle(cells)
    kind = rnd.random()
    layout: dict[str, list[float] | None] = {}
    for name, cell in zip(names, cells, strict=False):
        if kind < 0.35:
            layout[name] = list(cell)
        elif kind < 0.55:
            layout[name] = [round(v + rnd.choice([-0.1, 0.0, 0.1]), 1) for v in cell]
        elif kind < 0.85:
            layout[name] = [
                round(rnd.uniform(0, 300), 1),
                round(rnd.uniform(0, 300), 1),
                round(rnd.uniform(0.1, 40), 1),
                round(rnd.uniform(0.1, 40), 1),
            ]
        else:
            layout[name] = list(cell) if rnd.random() < 0.4 else None
    return layout


def _as_boxes(layout: dict[str, list[float] | None]) -> dict[str, Box | None]:
    return {
        name: None if box is None else (box[0], box[1], box[2], box[3])
        for name, box in layout.items()
    }


def test_the_editor_js_tiles_exactly_like_python() -> None:
    """무작위 범위(정밀도 밖 소수 포함)·이름(BMP 밖 글자 포함) 수백 건에서 JS 의 `tileModuleGroup`·
    `moduleCells`·`naturalCompare`·`moduleGrid`·`trayModuleRange`·`assignModuleCells`·`tileDeviation`·
    `groupLabelDefault` 가 파이썬과 같은 값을 낸다 — 좌표는 부동소수까지 같다."""
    rnd = random.Random(1023)
    tiles: list[dict[str, Any]] = []
    for _ in range(600):
        names = sorted({_random_name(rnd) for _ in range(rnd.randint(1, 12))})
        rnd.shuffle(names)
        tiles.append({"box": _random_box(rnd), "names": names})
    cells: list[dict[str, Any]] = [
        {"box": _random_box(rnd), "count": rnd.randint(1, 17)} for _ in range(200)
    ]
    sorted_cases = [[_random_name(rnd) for _ in range(rnd.randint(0, 9))] for _ in range(400)]
    trays = [
        [
            {"w": round(rnd.uniform(0.1, 30), 1), "h": round(rnd.uniform(0.1, 30), 1)}
            for _ in range(rnd.randint(1, 9))
        ]
        for _ in range(200)
    ]
    layouts = [_random_layout(rnd) for _ in range(600)]
    grids = list(range(1, 50))

    result = _run_js(
        {
            "tiles": tiles,
            "cells": cells,
            "sorted": sorted_cases,
            "grids": grids,
            "trays": trays,
            "slots": layouts,
        }
    )

    for case, spots in zip(tiles, result["tiles"], strict=True):
        box = case["box"]
        expected = tile_module_group((box["x"], box["y"], box["w"], box["h"]), case["names"])
        assert [spot["name"] for spot in spots] == list(expected), case
        assert {spot["name"]: (spot["x"], spot["y"], spot["w"], spot["h"]) for spot in spots} == (
            expected
        ), case
    for case, got in zip(cells, result["cells"], strict=True):
        box = case["box"]
        expected_cells = module_cells((box["x"], box["y"], box["w"], box["h"]), case["count"])
        assert [(c["x"], c["y"], c["w"], c["h"]) for c in got] == expected_cells, case
    for names, ordered in zip(sorted_cases, result["sorted"], strict=True):
        assert ordered == sorted(names, key=natural_name_key), names
    assert [tuple(grid) for grid in result["grids"]] == [module_grid(n) for n in grids]
    assert result["labels"] == [default_group_label(n) for n in grids]
    for sizes, tray in zip(trays, result["trays"], strict=True):
        cols, rows = module_grid(len(sizes))
        cell_w = max(_ticks(size["w"]) for size in sizes)
        cell_h = max(_ticks(size["h"]) for size in sizes)
        assert (tray["w"], tray["h"]) == (cols * cell_w / TICKS, rows * cell_h / TICKS), sizes
    for layout, slots, deviation in zip(
        layouts, result["slots"], result["deviations"], strict=True
    ):
        assert slots == assign_module_cells(_as_boxes(layout)), layout
        assert deviation == module_tile_deviation(_as_boxes(layout)), layout


def test_the_editor_js_keeps_cells_and_leaves_an_unchanged_range_alone() -> None:
    """다시 놓기(`relaidGroup`)는 범위가 눈금까지 그대로면 null 이다 — 벽에 막힌 방향키·제자리에서
    뗀 끌기·같은 숫자가 바둑판이 아닌 옛 묶음을 바꾸지 않는다. 범위가 바뀌면 모듈마다 지금 칸을
    지킨다(이름 차례가 아니다). 새로 놓기(`naturalSlots`)만 자연 정렬이다."""
    old: dict[str, list[float] | None] = {
        "G2A": [40, 10, 8, 6],
        "G2B": [50, 10, 6, 6],
        "G2C": [40, 20, 10, 5],
        "G2D": [52, 18, 5, 9],
    }
    upside = {
        "G7A": [30, 40, 10, 7],
        "G7B": [40, 40, 10, 7],
        "G7C": [30, 47, 10, 7],
        "G7D": [40, 47, 10, 7],
    }
    outer = {"x": 40, "y": 10, "w": 17, "h": 17}
    result = _run_js(
        {
            "slots": [upside],
            "relaid": [
                {"boxes": old, "from": outer, "to": dict(outer)},
                {"boxes": old, "from": outer, "to": {**outer, "x": 40.04}},
                {"boxes": old, "from": outer, "to": {**outer, "x": 41}},
                {
                    "boxes": upside,
                    "from": {"x": 30, "y": 40, "w": 20, "h": 14},
                    "to": {"x": 31, "y": 40, "w": 20, "h": 14},
                },
            ],
            "natural": [["G7D", "G7B", "G7C", "G7A"]],
        }
    )

    assert result["deviations"] == [0]
    assert result["relaid"][0] is None and result["relaid"][1] is None
    moved = {
        spot["name"]: (spot["x"], spot["y"], spot["w"], spot["h"]) for spot in result["relaid"][2]
    }
    slots = assign_module_cells(_as_boxes(old))
    cells = module_cells((41.0, 10.0, 17.0, 17.0), 4)
    assert moved == {name: cells[slot] for name, slot in slots.items()}
    kept = {spot["name"]: (spot["x"], spot["y"]) for spot in result["relaid"][3]}
    assert kept == {"G7A": (31, 40), "G7B": (41, 40), "G7C": (31, 47), "G7D": (41, 47)}
    assert result["natural"] == [{"G7A": 0, "G7B": 1, "G7C": 2, "G7D": 3}]


def test_the_editor_js_lines_up_three_modules_and_relays_an_old_two_by_two_three() -> None:
    """JS 도 모듈 셋은 한 줄이다 — 서랍 범위는 3 × 가장 큰 모듈 폭 × 1 × 가장 큰 모듈 높이이고,
    1·2차의 2×2 로 놓인 셋 묶음은 「3등분이 아님」(편차 > 0)이며 범위가 그대로면 다시 놓지 않고
    범위가 바뀌면 한 줄로 다시 놓는다(파이썬 `_relaid` 와 같은 칸)."""
    old: dict[str, list[float] | None] = {
        "T-A": [0, 7, 10, 7],
        "T-B": [10, 7, 10, 7],
        "T-C": [0, 0, 10, 7],
    }
    outer = {"x": 0, "y": 0, "w": 20, "h": 14}
    result = _run_js(
        {
            "trays": [[{"w": 12.0, "h": 7.0}, {"w": 10.0, "h": 8.0}, {"w": 11.5, "h": 6.0}]],
            "slots": [old],
            "relaid": [
                {"boxes": old, "from": outer, "to": dict(outer)},
                {"boxes": old, "from": outer, "to": {"x": 0, "y": 0, "w": 21, "h": 14}},
            ],
        }
    )

    assert result["trays"] == [{"w": 36.0, "h": 8.0}]
    assert result["deviations"][0] == module_tile_deviation(_as_boxes(old)) and (
        result["deviations"][0] > 1
    )
    assert result["relaid"][0] is None
    relaid = {
        spot["name"]: (spot["x"], spot["y"], spot["w"], spot["h"]) for spot in result["relaid"][1]
    }
    assert relaid == _relaid(_as_boxes(old), (0.0, 0.0, 21.0, 14.0))
    assert {box[3] for box in relaid.values()} == {14.0}


def test_a_group_dropped_from_the_tray_spans_the_old_tray_grid_and_is_split_evenly() -> None:
    """서랍에서 놓는 모듈 묶음의 범위는 지금까지의 서랍 격자와 같다(열 × 가장 큰 모듈 폭, 행 ×
    가장 큰 모듈 높이). 안은 그 범위를 똑같이 나누고 새로 놓기라 자연 정렬 차례다 — 모듈마다 제
    크기가 아니라 칸 크기다. 숨은 모듈도 그 칸에 함께 놓인다."""
    sizes = [
        {"w": 12.0, "h": 7.0},
        {"w": 10.0, "h": 8.0},
        {"w": 11.5, "h": 7.0},
        {"w": 9.0, "h": 6.0},
    ]
    result = _run_js({"trays": [sizes]})

    assert result["trays"] == [{"w": 24.0, "h": 16.0}]
    tiles = tile_module_group((0.0, 0.0, 24.0, 16.0), ["G-1A", "G-1B", "G-1C", "G-1D"])
    assert {tile[2:] for tile in tiles.values()} == {(12.0, 8.0)}
    plan = JS[JS.index("function trayPlan(") : JS.index("function placeFromTray(")]
    assert "trayModuleRange(sizes, SCALE)" in plan
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert (
        "layModules(piece.mods, fitRange(spot, piece.mods.length), "
        "naturalSlots(piece.mods.map((m) => m.id)))" in place
    )
    assert "const shown = placed.filter((m) => !m.ghost)" in place


# ---------------------------------------------------------------- 편집 길(자산 글자)


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


def test_no_path_moves_or_resizes_a_single_module() -> None:
    """Alt+끌기 단독 이동이 없고, 모듈 상자의 손잡이는 숨고 눌려도 옮기기이며, 크기는 묶음 범위
    테두리의 손잡이(`mode: 'range'`)로만 바꾼다. 끌기·방향키·X·Y 칸은 `movePlan`(모듈 묶음은 범위),
    크기(폭·높이 칸·Ctrl+방향키)는 `setSizes` 를 지난다."""
    down = _between("svg.onpointerdown = (event) => {", "svg.onpointermove = (event) => {")
    assert "altKey" not in down and "Alt+끌기" not in JS
    assert "sle-range-handle" in down and "mode: 'range'" in down
    assert "const mode = onlyThis && dir && !moduleMembers(item) ? 'resize' : 'move'" in down
    assert "movePlan(selectedItems())" in down
    move = _between("svg.onpointermove = (event) => {", "svg.onpointerup = ")
    assert (
        "relayGroup(g, resizedBox(g.range, drag.dir, dx, dTop, cols / SCALE, rows / SCALE), "
        "drag.befores)" in move
    )
    assert re.search(r"\.sle-unit\.is-module \.sle-handle \{ display: none; \}", CSS)
    assert "group.classList.toggle('is-module', (counts.get(groupKeyOf(item)) || 0) >= 2)" in JS
    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    assert "else moveItems(standing, ax, ay)" in keys and "setSizes(standing," in keys
    fields = _between("for (const input of fieldInputs) {", "const selectedMark = () => {")
    assert "movePlan(standing).box" in fields and "setSizes(standing," in fields
    sizes = _between("function setSizes(list, patchOf) {", "function retileModules(item) {")
    assert (
        "relayGroup({ mods, range, slots: groupSlots(mods) }, "
        "fitRange({ ...range, ...patchOf(range) }, mods.length))" in sizes
    )


def test_an_edit_that_keeps_the_range_does_not_relay_an_old_group() -> None:
    """옮기기·크기 조작은 묶음을 `relayGroup` 으로 다시 놓고, 그것은 범위가 눈금까지 그대로면 다시
    놓지 않는다(`relaidGroup` 이 null) — 벽에 막힌 방향키(Ctrl+A 뒤 포함)·제자리에서 뗀 끌기·같은
    숫자·이동 없는 범위 손잡이가 옛 묶음을 바꾸지 않는다. 끌기는 제자리로 돌아오면 처음 값으로
    되돌린다. 다시 놓기만 하는 길은 「범위에 맞춰 n등분」 하나다."""
    relay = _between("function relayGroup(g, to, befores) {", "function isTiled(mods) {")
    assert "relaidGroup(g.mods.map((m) => m.id), g.slots, g.range, to, SCALE)" in relay
    assert "if (befores) for (const m of g.mods) Object.assign(m, befores.get(m.id))" in relay
    moves = _between("function moveItems(list, dx, dy) {", "function setSizes(list, patchOf) {")
    assert (
        "for (const g of plan.groups) relayGroup(g, { ...g.range, "
        "x: roundTo(g.range.x + shift.dx), y: roundTo(g.range.y + shift.dy) })" in moves
    )
    assert "layModules(" not in moves
    drag = _between("svg.onpointermove = (event) => {", "svg.onpointerup = ")
    assert (
        "relayGroup(g, { ...g.range, x: roundTo(g.range.x + shift.dx), "
        "y: roundTo(g.range.y + shift.dy) }, drag.befores)" in drag
    )
    assert "layModules(" not in drag
    retile = _between("function retileModules(item) {", "function setMarkProps(item, patch) {")
    assert "layModules(mods, range)" in retile
    assert "slots: groupSlots(mods)" in _between(
        "function movePlan(list) {", "function onePerGroup("
    )


def test_the_editor_judges_a_tiling_by_shape_and_keeps_cells() -> None:
    """「n등분이 아님」 판정은 칸 모양(`tileDeviation` — 지금 자리 배정)이고 이름 차례를 보지
    않는다. 다시 놓을 때 칸 배정은 지금 자리(`groupSlots` = `assignModuleCells`)다."""
    tiled = _between("function isTiled(mods) {", "// 움직일 단위.")
    assert "return tileDeviation(mods.map(slotView), SCALE) === 0" in tiled
    lay = _between(
        "function layModules(mods, range, slots = groupSlots(mods)) {", "function relayGroup("
    )
    assert "layModuleGroup(range, mods.map((m) => m.id), slots, SCALE)" in lay
    assert "const groupSlots = (mods) => assignModuleCells(mods.map(slotView), SCALE)" in JS


def test_hidden_modules_ride_along_in_the_editor() -> None:
    """숨은 모듈(`data.ghosts`)은 그리지 않고 고르지 않지만 묶음의 칸·모듈 수에 들고 묶음과 함께
    옮겨져 적용값 `ghosts` 로 간다. 되돌리기·끌기 취소는 숨은 모듈도 되돌리고, 묶음 이름을 바꿔도
    처음 Main 설비 이름(`groupKeyOf`)으로 이어진다."""
    init = _between("function initFromData() {", "function adoptAsOf(incoming) {")
    assert (
        "for (const raw of data.ghosts || [])" in init and "S.ghosts.set(ghost.id, ghost)" in init
    )
    members = _between("const moduleMembers = (item) => {", "// 묶음 열쇠 → 이 편집기의 모듈 수")
    assert "const list = [...members(item), ...ghostsOf(item)]" in members
    counts = _between("const groupCounts = () => {", "// 범위를 정밀도")
    assert "for (const g of S.ghosts.values()) add(g.group)" in counts
    assert "if (!mods.some((m) => !m.ghost && onCanvas(m))) return null" in JS
    assert "ghosts: ghostChanges()," in _between("applyButton.onclick = () => {", "// ----")
    assert "const item = itemOf(op.id)" in _between("function undo() {", "function cancelDrag() {")
    cancel = _between("function cancelDrag() {", "function resizedBox(")
    assert "Object.assign(itemOf(id), before)" in cancel
    assert "const shown = list.filter((m) => m && !m.ghost)" in _between(
        "function redraw(list) {", "function moveItems("
    )
    assert ".sle-ghost-cell" in CSS and "class: 'sle-ghost-cell'" in JS
    assert "for (const item of [...S.items.values(), ...S.ghosts.values()])" in _between(
        "const extents = () => {", "// ---"
    )


def _js_decl(head: str) -> str:
    """editor.js 의 한 선언(`const …`·`function …`)을 글자 그대로 떼어 낸다. 첫 줄이 `{` 로 끝나면
    같은 들여쓰기의 닫는 줄(`}`·`})`)까지다."""
    start = JS.index(f"\n  {head}") + 1
    first_end = JS.index("\n", start)
    if not JS[start:first_end].rstrip().endswith("{"):
        return JS[start:first_end]
    close = re.compile(r"\n  \}\)?\n").search(JS, first_end)
    assert close, head
    return JS[start : close.end()]


# 빼기·보내기 둘레를 node 로 돌린다 — 선언은 editor.js 글자 그대로이고 그리기·선택만 빈 함수다.
# 되돌리기는 편집기 `undo` 의 'set' 갈래(`Object.assign(itemOf(op.id), op.before)`)와 같다.
_GHOST_DECLS = (
    "const isUnit = ",
    "const isMark = ",
    "const snapshot = ",
    "const sameGeometry = ",
    "const onCanvas = ",
    "const members = ",
    "const itemOf = ",
    "const groupKeyOf = ",
    "const placedMembers = ",
    "const expanded = ",
    "function restoreGhosts(",
    "function removeItems(",
    "function sendItems(",
)
_GHOST_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const S = { items: new Map(), ghosts: new Map(), original: new Map() }
const FLOOR = 'C1 1F'
const OTHER_FLOORS = ['C2 2F']
const stack = []
const pushUndo = (ops) => { if (ops.length) stack.push(ops) }
const clearSelection = () => {}
const renderItems = () => {}
const updateStatus = () => {}
%s
const undo = () => {
  for (const op of [...stack.pop()].reverse()) Object.assign(itemOf(op.id), op.before)
}
const unit = (id, group, box, ghost) => ({
  id, kind: 'unit', label: id, group, x: box[0], y: box[1], w: box[2], h: box[3],
  placed: true, moveTo: null, sizeGuessed: false, ...(ghost ? { ghost: true } : {}),
})
for (const [id, group, box, ghost] of input.units) {
  const m = unit(id, group, box, ghost)
  ;(ghost ? S.ghosts : S.items).set(id, m)
  S.original.set(id, snapshot(m))
}
const all = () => [...S.items.values(), ...S.ghosts.values()]
const nudge = (key, dx, dw) => {
  for (const m of all()) if (m.group === key) { m.x += dx; m.w += dw }
}
const state = () => Object.fromEntries(all().map((m) => [m.id,
  [m.x, m.y, m.w, m.h, Boolean(m.placed), m.moveTo || null]]))
const out = []
const note = (step) => out.push({
  step, undo: stack.length, last: stack.length ? stack[stack.length - 1].length : 0, state: state(),
})
nudge('GRP-1', 1, 2)
nudge('GRP-9', 1, 0)
removeItems([S.items.get('G1-A')])
note('removed')
undo()
note('undone')
sendItems([S.items.get('G1-C')], 'C2 2F')
note('sent')
undo()
note('unsent')
removeItems([S.items.get('G5-A')])
note('unmoved')
process.stdout.write(JSON.stringify({ steps: out }))
"""


def test_taking_a_moved_group_off_returns_its_hidden_modules_in_one_undo_step() -> None:
    """옮기거나 키운 묶음을 빼거나(빼기·Delete) 다른 층으로 보내면 그 묶음의 숨은 모듈은 처음 자리로
    돌아간다 — 옮기지 않고 바로 뺀 것과 같아 적용값 `ghosts` 가 비고 파이썬이 「숨은 모듈만 옮겨
    왔습니다」로 거부하지 않는다. 되돌리기 한 번에 보이는 모듈과 숨은 모듈이 함께 옮긴 자리로
    돌아온다. 다른 묶음의 숨은 모듈과 옮기지 않은 묶음은 건드리지 않는다(기록도 없다)."""
    units = [
        ["G1-A", "GRP-1", [50, 37, 10, 7], False],
        ["G1-B", "GRP-1", [60, 37, 10, 7], True],
        ["G1-C", "GRP-1", [50, 30, 10, 7], False],
        ["G1-D", "GRP-1", [60, 30, 10, 7], False],
        ["G9-A", "GRP-9", [10, 10, 5, 5], False],
        ["G9-B", "GRP-9", [15, 10, 5, 5], True],
        ["G5-A", "GRP-5", [10, 40, 5, 5], False],
        ["G5-B", "GRP-5", [15, 40, 5, 5], True],
    ]
    source = _GHOST_RUNNER % "\n".join(_js_decl(head) for head in _GHOST_DECLS)
    steps = {step["step"]: step for step in _node(source, {"units": units})["steps"]}

    moved_b = [61, 37, 12, 7, True, None]
    removed = steps["removed"]["state"]
    assert removed["G1-B"] == [60, 37, 10, 7, True, None]
    assert [removed[name][4] for name in ("G1-A", "G1-C", "G1-D")] == [False] * 3
    assert removed["G9-B"] == [16, 10, 5, 5, True, None]
    assert (steps["removed"]["undo"], steps["removed"]["last"]) == (1, 4)
    undone = steps["undone"]["state"]
    assert undone["G1-B"] == moved_b and undone["G1-A"] == [51, 37, 12, 7, True, None]
    assert steps["undone"]["undo"] == 0
    sent = steps["sent"]["state"]
    assert sent["G1-B"] == [60, 37, 10, 7, True, None]
    assert {sent[name][5] for name in ("G1-A", "G1-C", "G1-D")} == {"C2 2F"}
    assert (steps["sent"]["undo"], steps["sent"]["last"]) == (1, 4)
    unsent = steps["unsent"]["state"]
    assert unsent["G1-B"] == moved_b and unsent["G1-C"] == [51, 30, 12, 7, True, None]
    unmoved = steps["unmoved"]
    assert unmoved["state"]["G5-B"] == [15, 40, 5, 5, True, None] and unmoved["last"] == 1
    assert unmoved["state"]["G5-A"][4] is False
    remove = _between("function removeItems(list) {", "function sendItems(list, floor) {")
    assert "ops.push(...restoreGhosts(units))" in remove
    send = _between("function sendItems(list, floor) {", "const renameTarget = (item) => {")
    assert "pushUndo([...ops, ...restoreGhosts(sent)])" in send


def test_an_empty_cell_inside_a_picked_group_drags_the_group() -> None:
    """모듈 다섯 묶음의 남는 칸이나 숨은 모듈 칸처럼 고른 묶음 범위 안의 빈 곳을 누르면 선택이
    풀리지 않고 그 묶음을 끈다(사각형 고르기보다 먼저 본다)."""
    down = _between("svg.onpointerdown = (event) => {", "svg.onpointermove = (event) => {")
    held = down.index("if (!group && !additive && pickedRangeAt(picked, p)) {")
    assert held < down.index("mode: 'marquee'")
    assert "mode: 'move'" in down[held : down.index("mode: 'marquee'")]
    at = _between("function pickedRangeAt(picked, p) {", "svg.onpointerdown = ")
    assert "groupRange(mods)" in at and "const y = H() - p.top" in at


def test_a_group_is_picked_and_dropped_whole() -> None:
    """선택에는 묶음당 한 대만 남고(`onePerGroup` — 고르기·사각형·전체 선택·서랍),
    Shift/Ctrl+클릭은 묶음째 더하고 뺀다. 빼기·다른 층 보내기는 묶음 전체다. 서랍은 도면에 선
    묶음의 좌표 없는 모듈을 따로 내놓지 않는다."""
    select = _between("function setSelection(ids, primary) {", "function select(id) {")
    assert "onePerGroup(" in select
    assert "S.selection = new Set(onePerGroup(drag.additive" in JS
    down = _between("svg.onpointerdown = (event) => {", "svg.onpointermove = (event) => {")
    assert "const bundle = (moduleMembers(item) || [item]).map((m) => m.id)" in down
    remove = _between("function removeItems(list) {", "function sendItems(list, floor) {")
    assert "expanded(list.filter((m) => isUnit(m) && !m.created))" in remove
    send = _between("function sendItems(list, floor) {", "const renameTarget = (item) => {")
    assert "for (const m of members(item))" in send
    keep = _between("function trayKeep() {", "function trayEntries(keep) {")
    assert "!(m.group && standing.has(m.group))" in keep
    assert JS.count("trayEntries(trayKeep())") == 3


def test_the_inspector_edits_the_group_range_and_offers_to_regrid_an_old_group() -> None:
    """검사 칸의 X·Y·폭·높이는 묶음 범위다. 바둑판이 아닌 옛 묶음이면 「n등분이 아님 …」 한 줄과
    「범위에 맞춰 n등분」 단추가 선다. 숨은 모듈 수도 알린다. 옛 묶음은 읽을 때 바꾸지 않는다(처음
    그리기·같은 epoch 합치기에 다시 놓기가 없다)."""
    sync = _between("function syncInspector() {", "function hasPendingEdits() {")
    assert "input.value = String(extent(single)[field])" in sync
    assert "moduleTile.hidden = !loose" in sync and "`범위에 맞춰 ${loose.length}등분`" in sync
    caption = _between("function moduleCaption(item) {", "function syncInspector() {")
    assert "등분이 아님 — 옮기거나 크기를 바꾸면 범위 안에 다시 놓입니다" in caption
    assert "숨은 모듈 ${hidden}" in caption
    assert "moduleTile.onclick" in JS and "retileModules(chosen[0])" in JS
    init = _between("function initFromData() {", "function adoptAsOf(incoming) {")
    merge = _between(
        "// ------------------------------------------------------------- 회차마다",
        "svg.onmousedown",
    )
    assert "layModules(" not in init and "layModules(" not in merge


def test_one_group_edit_is_one_undo_step() -> None:
    """묶음 조작 하나는 모듈 모두(숨은 모듈 포함)를 한 기록(`commit`)에 담는다 — 되돌리기 한 번에
    넷이 같이 돌아온다."""
    for name, end in (
        ("function moveItems(list, dx, dy) {", "function setSizes(list, patchOf) {"),
        ("function setSizes(list, patchOf) {", "function retileModules(item) {"),
        ("function retileModules(item) {", "function setMarkProps(item, patch) {"),
        (
            "function placeFromTray(lead, list, p, name, free) {",
            "function addMark(kind, at, free) {",
        ),
    ):
        body = _between(name, end)
        assert body.count("commit(") == 1, name
    up = _between("svg.onpointerup = ", "svg.onlostpointercapture")
    assert ".filter((e) => !sameSpot(e.before, itemOf(e.id)))" in up and "commit(entries)" in up
