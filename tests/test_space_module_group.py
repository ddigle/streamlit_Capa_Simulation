# Purpose: Space 편집기 Main 설비 모듈 묶음의 바둑판 규칙·JS 대조·적용 정규화·편집 길을 검사한다.

"""모듈 묶음 = 편집기에 실린 호기 가운데 Main 설비가 같은 것이 둘 이상(2026-10-23 사용자 요청).

사람이 고치는 것은 묶음 범위뿐이고 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 자동으로
선다. 규칙의 정본은 `services/space_layout_edit.tile_module_group` 이고 편집기 JS(`editor.js` 의
`// <module-tiling>` 구획)가 같은 값을 내는지 node 로 떼어 돌려 대조한다. node·bun 이 없는
PC 에서는 그 대조만 건너뛰고, GitHub Actions 에서는 실패한다(`test_intro_scene_behavior` 와 같은
규칙). 브라우저 조작 자체는 AppTest 가 못 돌리므로 모듈 하나만 편집하는 길이 막혔는지는 자산
글자로 붙잡는다.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from typing import Any

import pandas as pd
import pytest
from test_space_layout_edit import CANVAS, FLOOR, _master, _parse, _status

from capa_simulation.components import space_layout_editor
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.space_layout_edit import (
    UnitChange,
    apply_layout_edits,
    editor_inputs,
    module_grid,
    natural_name_key,
    tile_module_group,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
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


# ---------------------------------------------------------------- JS 와 대조(node)

_SECTION = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)
_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  tiles: input.tiles.map((c) => tileModuleGroup(c.box, c.names, 10)),
  sorted: input.sorted.map((names) => [...names].sort(naturalCompare)),
  grids: input.grids.map((n) => moduleGrid(n)),
  trays: input.trays.map((sizes) => trayModuleRange(sizes, 10)),
}))
"""


def _runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


def _run_js(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 모듈 묶음 JS 대조를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    match = _SECTION.search(JS)
    assert match, "editor.js 에 // <module-tiling> 구획이 없습니다"
    completed = subprocess.run(
        [runtime, "-e", match.group("body") + _RUNNER],
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


def _random_name(rnd: random.Random) -> str:
    parts = ["SMP", "-", "GRP", "EQ", "12", "3", "007", "a", "B", "c", "가", "나", "_", "0"]
    return "".join(rnd.choice(parts) for _ in range(rnd.randint(1, 6)))


def test_the_editor_js_tiles_exactly_like_python() -> None:
    """무작위 범위(정밀도 밖 소수 포함)·이름 수백 건에서 JS `tileModuleGroup`·`naturalCompare`·
    `moduleGrid`·`trayModuleRange` 가 파이썬과 같은 값을 낸다 — 좌표는 부동소수까지 같다."""
    rnd = random.Random(1023)
    tiles: list[dict[str, Any]] = []
    for _ in range(600):
        names = sorted({_random_name(rnd) for _ in range(rnd.randint(1, 12))})
        rnd.shuffle(names)
        box = {
            "x": round(rnd.uniform(-5, 400), rnd.choice([0, 1, 2, 3])),
            "y": round(rnd.uniform(-5, 400), rnd.choice([0, 1, 2, 3])),
            "w": round(rnd.uniform(0, 150), rnd.choice([0, 1, 2, 3])),
            "h": round(rnd.uniform(0, 150), rnd.choice([0, 1, 2, 3])),
        }
        tiles.append({"box": box, "names": names})
    sorted_cases = [[_random_name(rnd) for _ in range(rnd.randint(0, 9))] for _ in range(300)]
    trays = [
        [
            {"w": round(rnd.uniform(0.1, 30), 1), "h": round(rnd.uniform(0.1, 30), 1)}
            for _ in range(rnd.randint(1, 9))
        ]
        for _ in range(200)
    ]
    grids = list(range(1, 50))

    result = _run_js({"tiles": tiles, "sorted": sorted_cases, "grids": grids, "trays": trays})

    for case, spots in zip(tiles, result["tiles"], strict=True):
        box = case["box"]
        expected = tile_module_group((box["x"], box["y"], box["w"], box["h"]), case["names"])
        assert [spot["name"] for spot in spots] == list(expected), case
        assert {spot["name"]: (spot["x"], spot["y"], spot["w"], spot["h"]) for spot in spots} == (
            expected
        ), case
    for names, ordered in zip(sorted_cases, result["sorted"], strict=True):
        assert ordered == sorted(names, key=natural_name_key), names
    assert [tuple(grid) for grid in result["grids"]] == [module_grid(n) for n in grids]
    for sizes, tray in zip(trays, result["trays"], strict=True):
        cols, rows = module_grid(len(sizes))
        cell_w = max(_ticks(size["w"]) for size in sizes)
        cell_h = max(_ticks(size["h"]) for size in sizes)
        assert (tray["w"], tray["h"]) == (cols * cell_w / TICKS, rows * cell_h / TICKS), sizes


def test_a_group_dropped_from_the_tray_spans_the_old_tray_grid_and_is_split_evenly() -> None:
    """서랍에서 놓는 모듈 묶음의 범위는 지금까지의 서랍 격자와 같다(열 × 가장 큰 모듈 폭, 행 ×
    가장 큰 모듈 높이). 안은 그 범위를 똑같이 나눈다 — 모듈마다 제 크기가 아니라 칸 크기다."""
    sizes = [
        {"w": 12.0, "h": 7.0},
        {"w": 10.0, "h": 8.0},
        {"w": 11.5, "h": 7.0},
        {"w": 9.0, "h": 6.0},
    ]
    result = _run_js({"tiles": [], "sorted": [], "grids": [], "trays": [sizes]})

    assert result["trays"] == [{"w": 24.0, "h": 16.0}]
    tiles = tile_module_group((0.0, 0.0, 24.0, 16.0), ["G-1A", "G-1B", "G-1C", "G-1D"])
    assert {tile[2:] for tile in tiles.values()} == {(12.0, 8.0)}
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert "trayModuleRange(sizes, SCALE)" in place
    assert "layModules(piece.mods, fitRange(spot, piece.mods.length))" in place


# ---------------------------------------------------------------- 모듈 하나만 고치는 길(자산 글자)


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


def test_no_path_moves_or_resizes_a_single_module() -> None:
    """Alt+끌기 단독 이동이 없고, 모듈 상자의 손잡이는 숨고 눌려도 옮기기이며, 크기는 묶음 범위
    테두리의 손잡이(`mode: 'range'`)로만 바꾼다. 끌기·방향키·숫자 칸은 모두 `movePlan`(모듈
    묶음은 범위)을 지난다."""
    down = _between("svg.onpointerdown = (event) => {", "svg.onpointermove = (event) => {")
    assert "altKey" not in down and "Alt+끌기" not in JS
    assert "sle-range-handle" in down and "mode: 'range'" in down
    assert "const mode = onlyThis && dir && !moduleMembers(item) ? 'resize' : 'move'" in down
    assert "movePlan(selectedItems())" in down
    move = _between("svg.onpointermove = (event) => {", "svg.onpointerup = ")
    assert (
        "layModules(g.mods, resizedBox(g.range, drag.dir, dx, dTop, cols / SCALE, rows / SCALE))"
        in (move)
    )
    assert re.search(r"\.sle-unit\.is-module \.sle-handle \{ display: none; \}", CSS)
    assert "group.classList.toggle('is-module', (counts.get(item.group) || 0) >= 2)" in JS
    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    assert "else moveItems(standing, ax, ay)" in keys and "setSizes(standing," in keys
    fields = _between("for (const input of fieldInputs) {", "const selectedMark = () => {")
    assert "movePlan(standing).box" in fields and "setSizes(standing," in fields
    sizes = _between("function setSizes(list, patchOf) {", "function retileModules(item) {")
    assert "layModules(mods, fitRange({ ...range, ...patchOf(range) }, mods.length))" in sizes


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
    「범위에 맞춰 n등분」 단추가 선다. 옛 묶음은 읽을 때 바꾸지 않는다(처음 그리기·같은 epoch
    합치기에 다시 놓기가 없다)."""
    sync = _between("function syncInspector() {", "function hasPendingEdits() {")
    assert "input.value = String(extent(single)[field])" in sync
    assert "moduleTile.hidden = !loose" in sync and "`범위에 맞춰 ${loose.length}등분`" in sync
    caption = _between("function moduleCaption(item) {", "function syncInspector() {")
    assert "등분이 아님 — 옮기거나 크기를 바꾸면 범위 안에 다시 놓입니다" in caption
    assert "moduleTile.onclick" in JS and "retileModules(chosen[0])" in JS
    init = _between("function initFromData() {", "function adoptAsOf(incoming) {")
    merge = _between(
        "// ------------------------------------------------------------- 회차마다",
        "svg.onmousedown",
    )
    assert "layModules(" not in init and "layModules(" not in merge


def test_one_group_edit_is_one_undo_step() -> None:
    """묶음 조작 하나는 모듈 모두를 한 기록(`commit`)에 담는다 — 되돌리기 한 번에 넷이 같이
    돌아온다."""
    for name, end in (
        ("function moveItems(list, dx, dy) {", "function setSizes(list, patchOf) {"),
        ("function setSizes(list, patchOf) {", "function retileModules(item) {"),
        ("function retileModules(item) {", "function setMarkProps(item, patch) {"),
        ("function placeFromTray(lead, list, p, name) {", "function addMark(kind, at) {"),
    ):
        body = _between(name, end)
        assert body.count("commit(") == 1, name
    up = _between("svg.onpointerup = ", "svg.onlostpointercapture")
    assert (
        ".filter((e) => !sameSpot(e.before, S.items.get(e.id)))" in up and "commit(entries)" in up
    )
