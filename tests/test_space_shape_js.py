# Purpose: Space 편집기 도형의 경로·노란 모양 조절 손잡이·비율 유지·모양 값 정규화를 node 로
# 검사한다.

"""2026-11-03 사용자 요청 — 도면 요소 도형(원·사각형·ㄴ자 박스·프리셋)과 엑셀처럼 모양 바꾸기.

순수 판정은 `editor.js` 의 `// <mark-look>`(프리셋 표·모양 값 정규화)과 `// <shape-geometry>`(경로
`shapePath`·손잡이 `shapeHandles`·값 되돌림 `handleValue`·`unplaceLocal`·비율 유지 `keepAspect`·
손잡이 비키기 `nudgeHandle`) 구획이고 node 로 떼어 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패
— `test_space_module_group._node`). 모양 값 정규화는 파이썬 `floor_layout_mark.mark_look` 과
대조한다. 끌기는 실제 함수 `adjustedLook` 을 떼어 돌린다. 그리기·선택 칸 배선은 자산 글자로 붙잡고
실제 모습은 브라우저로 본다.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

import pytest
from test_space_editor_tools import _run_clipboard
from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor
from capa_simulation.services.floor_layout_mark import (
    FILL_ALPHA_STEP,
    SHAPE_ADJUST,
    SHAPE_FILL_KEYS,
    SHAPE_LINE_KEYS,
    SHAPE_NAMES,
    SHAPE_PRESETS,
    mark_look,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_LOOK = re.compile(r"// <mark-look>\n(?P<body>.*?)\n\s*// </mark-look>", re.S)
_GEOMETRY = re.compile(r"// <shape-geometry>\n(?P<body>.*?)\n\s*// </shape-geometry>", re.S)
_ROTATIONS = (0, 90, 180, 270)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
%s
const H = 60
const svgTop = (item) => H - (item.y + item.h)
%s
const out = {}
const list = (key) => input[key] || []
out.lists = { SHAPE_PRESETS, SHAPE_KEYS, SHAPE_FILLS, SHAPE_LINES, FILL_ALPHA_STEP }
out.paths = list('paths').map(([key, lw, lh, adj]) => shapePath(key, lw, lh, adj))
out.handles = list('handles').map(([key, lw, lh, adj]) => shapeHandles(key, lw, lh, adj))
out.values = list('values')
  .map(([key, index, x, y, lw, lh]) => handleValue(key, index, x, y, lw, lh))
out.trips = list('trips').map(([key, lw, lh, adj, rot, flip]) => shapeHandles(key, lw, lh, adj)
  .map((h) => {
    const spot = placeLocal(h.x, h.y, lw, lh, rot, flip)
    const back = unplaceLocal(spot.x, spot.y, lw, lh, rot, flip)
    return { spot, back, value: handleValue(key, h.index, back.x, back.y, lw, lh) }
  }))
out.placed = list('placed').map(([key, lw, lh, adj, rot, flip]) => shapePath(key, lw, lh, adj)
  .pts.map(([x, y]) => placeLocal(x, y, lw, lh, rot, flip)))
out.aspects = list('aspects')
  .map(([b, r, dir, maxW, maxH]) => keepAspect(b, r, dir, maxW, maxH, 0.1, 10))
out.nudges = list('nudges')
  .map(([pt, axis, centers, gap, center]) => nudgeHandle(pt, axis, centers, gap, center))
out.looks = list('looks').map((look) => lookText(cleanLook(look, 'shape')))
out.adjs = list('adjs').map((look) => shapeAdj(look))
out.presets = list('presets').map((look) => shapeOf(look))
out.fills = list('fills').map((color) => shapeFillOf(color))
out.drags = list('drags').map(([item, index, p]) => {
  const next = adjustedLook(item, index, p)
  return next === null ? null : lookText(next)
})
process.stdout.write(JSON.stringify(out))
"""


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    source = _RUNNER % (_block(_LOOK), _block(_GEOMETRY), _js_decl("function adjustedLook("))
    return _node(source, payload)


def _defaults(key: str) -> list[float]:
    return [spec[2] for spec in SHAPE_ADJUST[key]]


def _ends(key: str) -> list[list[float]]:
    """모양 조절 값 범위 끝의 모든 짝(값이 없으면 빈 목록 하나)과 처음 값."""
    specs = SHAPE_ADJUST[key]
    ends = [list(combo) for combo in itertools.product(*[(low, high) for low, high, _ in specs])]
    return [*ends, _defaults(key)]


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


# ------------------------------------------------------------------------------- 계약


def test_the_preset_table_matches_the_python_contract() -> None:
    lists = _run({})["lists"]
    assert tuple(lists["SHAPE_KEYS"]) == SHAPE_PRESETS
    for key in SHAPE_PRESETS:
        preset = lists["SHAPE_PRESETS"][key]
        assert preset["name"] == SHAPE_NAMES[key]
        assert [tuple(spec) for spec in preset["adj"]] == list(SHAPE_ADJUST[key])
        assert len(preset["words"]) == len(SHAPE_ADJUST[key])
    assert tuple(lists["SHAPE_FILLS"]) == SHAPE_FILL_KEYS
    assert tuple(lists["SHAPE_LINES"]) == SHAPE_LINE_KEYS
    assert lists["FILL_ALPHA_STEP"] == FILL_ALPHA_STEP
    # 넣는 크기(사양 4b-1)와 돌리기에 뜻이 있는 꼴.
    sizes = {key: tuple(lists["SHAPE_PRESETS"][key]["size"]) for key in SHAPE_PRESETS}
    assert sizes == {
        "rect": (8, 6),
        "ellipse": (6, 6),
        "lbox": (8, 8),
        "cbox": (8, 8),
        "frame": (10, 8),
        "triangle": (8, 7),
        "diamond": (8, 8),
        "cross": (8, 8),
        "arrowblock": (10, 5),
    }
    turns = {key for key in SHAPE_PRESETS if lists["SHAPE_PRESETS"][key]["turn"]}
    assert turns == {"lbox", "cbox", "triangle", "arrowblock"}


# ------------------------------------------------------------------------------- 경로


_SIZES: list[tuple[float, float]] = [(8, 6), (6, 8), (40, 2), (2, 40), (0.1, 0.1), (0.1, 3)]


@pytest.mark.parametrize("key", SHAPE_PRESETS)
def test_every_preset_path_stays_inside_its_box_at_the_ends_of_its_adjust_range(key: str) -> None:
    """프리셋마다 모양 조절 범위 끝·처음 값 × 크기 여섯(아주 작은 0.1 포함)에서 꼭짓점·호 끝점이
    모두 상자(lw×lh) 안이다. 테만 evenodd(가운데가 빈다)이고 안쪽 틀은 양수 넓이다. 사각형 둥글기는
    짧은 변의 반을 넘지 않는다."""
    cases: list[tuple[str, float, float, list[float]]] = [
        (key, lw, lh, adj) for lw, lh in _SIZES for adj in _ends(key)
    ]
    paths = _run({"paths": cases})["paths"]
    for (_, lw, lh, adj), path in zip(cases, paths, strict=True):
        assert path["rule"] == ("evenodd" if key == "frame" else "nonzero")
        assert path["d"].startswith("M ") and path["d"].endswith("Z")
        numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", path["d"])]
        assert numbers and all(abs(value) < 1e6 for value in numbers)
        for x, y in path["pts"]:
            assert -1e-9 <= x <= lw + 1e-9 and -1e-9 <= y <= lh + 1e-9, (adj, lw, lh, x, y)
        if key == "rect" and "r" in path:
            assert path["r"] <= min(lw, lh) / 2 + 1e-9
        if key == "frame":
            inner = path["pts"][4:]
            xs = sorted({round(x, 9) for x, _ in inner})
            ys = sorted({round(y, 9) for _, y in inner})
            assert xs[0] < xs[-1] and ys[0] < ys[-1]
        if key == "cbox":
            # 위·아래 팔이 맞닿지 않는다(팔 두께 ≤ 0.49 · lh).
            assert path["pts"][3][1] < path["pts"][4][1]


def test_the_default_drawings_are_the_spec_paths() -> None:
    """사양 4b-1 의 그리기 경로(8×6 · 처음 값). 사각형 둥글기 0 은 네 귀 다각형, 둥글기가 있으면 호
    넷이다."""
    keys = list(SHAPE_PRESETS)
    paths = _run({"paths": [[key, 8, 6, _defaults(key)] for key in keys]})["paths"]
    drawn = dict(zip(keys, (path["d"] for path in paths), strict=True))

    assert drawn["rect"] == "M 0 0 L 8 0 L 8 6 L 0 6 Z"
    assert drawn["ellipse"] == "M 0 3 A 4 3 0 1 0 8 3 A 4 3 0 1 0 0 3 Z"
    assert drawn["lbox"] == "M 0 0 L 2.8 0 L 2.8 3.9 L 8 3.9 L 8 6 L 0 6 Z"
    assert drawn["cbox"] == "M 0 0 L 8 0 L 8 1.8 L 2.4 1.8 L 2.4 4.2 L 8 4.2 L 8 6 L 0 6 Z"
    assert (
        drawn["frame"]
        == "M 0 0 L 8 0 L 8 6 L 0 6 Z M 0.72 0.72 L 0.72 5.28 L 7.28 5.28 L 7.28 0.72 Z"
    )
    assert drawn["triangle"] == "M 4 0 L 8 6 L 0 6 Z"
    assert drawn["diamond"] == "M 4 0 L 8 3 L 4 6 L 0 3 Z"
    assert drawn["cross"].startswith("M 2.98 0 L 5.02 0 L 5.02 1.98 L 8 1.98")
    assert drawn["arrowblock"] == "M 0 1.5 L 5.2 1.5 L 5.2 0 L 8 3 L 5.2 6 L 5.2 4.5 L 0 4.5 Z"
    (rounded,) = _run({"paths": [["rect", 8, 6, [0.5]]]})["paths"]
    assert rounded["d"] == (
        "M 1.5 0 H 6.5 A 1.5 1.5 0 0 1 8 1.5 V 4.5 A 1.5 1.5 0 0 1 6.5 6 H 1.5 "
        "A 1.5 1.5 0 0 1 0 4.5 V 1.5 A 1.5 1.5 0 0 1 1.5 0 Z"
    )


@pytest.mark.parametrize("rot", _ROTATIONS)
@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("key", ["lbox", "triangle", "arrowblock", "cbox"])
def test_turned_and_flipped_shapes_stay_inside_the_turned_box(
    key: str, rot: int, flip: bool
) -> None:
    """돌림 넷 × 뒤집기 둘 — 제자리(8×6) 꼭짓점을 화면 자리로 옮기면 돌린 상자(90°·270° 는 6×8)
    안이다."""
    placed = _run({"placed": [[key, 8, 6, _defaults(key), rot, flip]]})["placed"][0]
    half_w, half_h = (3, 4) if rot % 180 else (4, 3)
    for spot in placed:
        assert abs(spot["x"]) <= half_w + 1e-9 and abs(spot["y"]) <= half_h + 1e-9


def test_a_flipped_lbox_opens_to_the_other_side() -> None:
    """ㄴ자(세로 팔 왼쪽 · 가로 팔 아래)를 좌우로 뒤집으면 세로 팔이 오른쪽이다(ㄱ 거울 꼴 — 」)."""
    (plain, mirrored) = _run(
        {"placed": [["lbox", 8, 6, [0.25, 0.25], 0, False], ["lbox", 8, 6, [0.25, 0.25], 0, True]]}
    )["placed"]
    # 둘째 꼭짓점 = 세로 팔 위 오른쪽 귀(x = t1). 뒤집으면 거울 자리.
    assert plain[1] == pytest.approx({"x": -2, "y": -3})
    assert mirrored[1] == pytest.approx({"x": 2, "y": -3})


# ------------------------------------------------------------------------------- 노란 손잡이


_ADJUSTABLE = [key for key in SHAPE_PRESETS if SHAPE_ADJUST[key]]


@pytest.mark.parametrize("key", _ADJUSTABLE)
@pytest.mark.parametrize("rot", _ROTATIONS)
@pytest.mark.parametrize("flip", [False, True])
def test_each_handle_reads_back_its_own_value_through_turns_and_flips(
    key: str, rot: int, flip: bool
) -> None:
    """손잡이를 제자리 → 화면(뒤집기 · 돌림) → 제자리로 되돌려 읽으면 그 모양 조절 값이다 — 범위
    끝·처음 값 모두, 크기 셋에서. 손잡이 수는 값 수와 같고 번호는 0·1 차례다."""
    cases: list[tuple[str, float, float, list[float], int, bool]] = [
        (key, lw, lh, adj, rot, flip)
        for lw, lh in [(8.0, 6.0), (3.0, 10.0), (0.4, 0.2)]
        for adj in _ends(key)
    ]
    trips = _run({"trips": cases})["trips"]
    for (_, lw, lh, adj, _, _), handles in zip(cases, trips, strict=True):
        assert len(handles) == len(adj)
        for index, handle in enumerate(handles):
            assert handle["value"] == pytest.approx(adj[index]), (lw, lh, adj, index)
            assert -1e-9 <= handle["back"]["x"] <= lw + 1e-9
            assert -1e-9 <= handle["back"]["y"] <= lh + 1e-9


def test_handles_follow_the_spec_spots_and_presets_without_values_have_none() -> None:
    out = _run(
        {
            "handles": [
                ["rect", 8, 6, [0.5]],
                ["lbox", 8, 6, [0.35, 0.5]],
                ["cbox", 8, 6, [0.3, 0.3]],
                ["frame", 10, 8, [0.12]],
                ["triangle", 8, 7, [0.25]],
                ["cross", 8, 8, [0.5]],
                ["arrowblock", 10, 5, [0.5, 0.35]],
                ["ellipse", 6, 6, []],
                ["diamond", 8, 8, []],
            ]
        }
    )["handles"]
    spots = [
        [(round(h["x"], 6), round(h["y"], 6), h["axis"], h["index"]) for h in handles]
        for handles in out
    ]
    assert spots == [
        [(1.5, 0, "x", 0)],
        [(2.8, 0, "x", 0), (8, 3, "y", 1)],
        [(2.4, 3, "x", 0), (8, 1.8, "y", 1)],
        [(0.96, 0.96, "y", 0)],
        [(2, 0, "x", 0)],
        [(6, 1, "x", 0)],
        [(3.25, 1.25, "y", 0), (6.5, 0, "x", 1)],
        [],
        [],
    ]


def test_handle_values_clamp_to_the_range_and_snap_to_hundredths() -> None:
    out = _run(
        {
            "values": [
                ["lbox", 0, -5, 0, 8, 6],
                ["lbox", 0, 50, 0, 8, 6],
                ["lbox", 1, 8, 5.987, 8, 6],
                ["rect", 0, 99, 0, 8, 6],
                ["triangle", 0, 2.004, 0, 8, 6],
                ["cbox", 1, 8, 5.9, 8, 6],
                ["arrowblock", 0, 5, -1, 10, 5],
                ["ellipse", 0, 1, 1, 6, 6],
                ["lbox", 2, 1, 1, 8, 6],
            ]
        }
    )["values"]
    assert out == [0.05, 0.95, 0.05, 1, 0.25, 0.49, 1, None, None]


def _shape_item(**values: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": "shape", "x": 10, "y": 10, "w": 8, "h": 6, "rot": 0, "look": {}}
    item.update(values)
    return item


def test_dragging_a_yellow_handle_changes_only_that_value() -> None:
    """실제 `adjustedLook` — 상자 (10, 10, 8×6), 캔버스 높이 60(화면 위 = 60 − (y+h) = 44). ㄴ자
    세로 팔 손잡이를 화면 x 14 로 끌면 a1 = 4/8 = 0.5(가로 팔은 그대로), 90° 돌린 ㄴ자(6×8 상자 —
    화면 위 42, 제자리 8×6)는 화면 세로가 그 축이다(세로 팔이 위로 간다). 처음 값으로 돌아오면 그
    키가 빠지고, 같은 값이면 null 이다."""
    lbox = _shape_item(look={"shape": "lbox"})
    turned = _shape_item(w=6, h=8, rot=90, look={"shape": "lbox"})
    flipped = _shape_item(look={"shape": "triangle", "flip": True})
    out = _run(
        {
            "drags": [
                [lbox, 0, {"x": 14, "top": 44}],
                [lbox, 1, {"x": 18, "top": 44 + 3}],
                [_shape_item(look={"shape": "lbox", "adj": [0.5, 0.35]}), 0, {"x": 12.8, "top": 0}],
                [lbox, 0, {"x": 12.8, "top": 30}],
                # 90°: 제자리 x 축이 화면 y 축(아래로). 화면 위 끝(top 42)에서 4 아래 = 제자리 x 4.
                [turned, 0, {"x": 99, "top": 42 + 4}],
                # 좌우 뒤집은 삼각형: 꼭짓점을 화면 왼쪽 1/4 로 끌면 제자리 3/4.
                [flipped, 0, {"x": 12, "top": 44}],
            ]
        }
    )["drags"]
    assert out == [
        '{"adj":[0.5,0.35],"shape":"lbox"}',
        '{"adj":[0.35,0.5],"shape":"lbox"}',
        '{"shape":"lbox"}',
        None,
        '{"adj":[0.5,0.35],"shape":"lbox"}',
        '{"adj":[0.75],"flip":true,"shape":"triangle"}',
    ]


def test_a_handle_on_a_resize_handle_is_drawn_aside_along_its_axis() -> None:
    """둥글기 0 사각형의 손잡이(왼쪽 위 귀)는 모서리 손잡이를 덮지 않게 축(가로)을 따라 상자
    안쪽으로 비킨다. 멀면 그대로다. 두 쪽이 다 가까우면 더 먼 쪽이다."""
    corner = [{"x": 0, "y": 0}, {"x": 20, "y": 0}]
    out = _run(
        {
            "nudges": [
                [{"x": 0, "y": 0}, "x", corner, 1.2, {"x": 10, "y": 5}],
                [{"x": 5, "y": 0}, "x", corner, 1.2, {"x": 10, "y": 5}],
                [{"x": 10, "y": 0.5}, "y", [{"x": 10, "y": 0}], 1.2, {"x": 10, "y": 5}],
                [
                    {"x": 19.5, "y": 0},
                    "x",
                    [{"x": 19, "y": 0}, {"x": 21, "y": 0}],
                    1.2,
                    {"x": 10, "y": 5},
                ],
            ]
        }
    )["nudges"]
    assert out == pytest.approx(
        [{"x": 1.2, "y": 0}, {"x": 5, "y": 0}, {"x": 10, "y": 1.7}, {"x": 18.3, "y": 0}]
    )


# ------------------------------------------------------------------------------- 비율 유지


@pytest.mark.parametrize("corner", ["ne", "nw", "se", "sw"])
def test_shift_corner_resizing_keeps_the_ratio_and_the_opposite_corner(corner: str) -> None:
    """처음 상자 (20, 20, 8×6). 손이 더 많이 움직인 축을 따라 키우고(가로 16 → 높이 12), 맞은편 귀가
    그대로다. 영역(60×40) 밖으로는 넘지 않고 가장 짧은 변이 0.1 아래로 줄지 않는다."""
    box = {"x": 20, "y": 20, "w": 8, "h": 6}
    east, north = "e" in corner, "n" in corner
    wide = {
        "x": 20 if east else 12,
        "y": 20 if north else 19,
        "w": 16,
        "h": 7,
    }
    huge = {"x": 20 if east else 0, "y": 20 if north else 0, "w": 200, "h": 6}
    tiny = {"x": 20, "y": 20, "w": 0.01, "h": 6}
    out = _run(
        {
            "aspects": [
                [box, wide, corner, 60, 40],
                [box, huge, corner, 60, 40],
                [box, tiny, corner, 60, 40],
            ]
        }
    )["aspects"]
    grown, capped, least = out
    assert (grown["w"], grown["h"]) == (16, 12)
    anchor_x = 20 if east else 28
    anchor_y = 20 if north else 26
    assert (grown["x"] if east else grown["x"] + grown["w"]) == pytest.approx(anchor_x)
    assert (grown["y"] if north else grown["y"] + grown["h"]) == pytest.approx(anchor_y)
    assert capped["x"] >= -1e-9 and capped["x"] + capped["w"] <= 60 + 1e-9
    assert capped["y"] >= -1e-9 and capped["y"] + capped["h"] <= 40 + 1e-9
    assert capped["w"] / capped["h"] == pytest.approx(8 / 6, rel=0.02)
    assert min(least["w"], least["h"]) >= 0.1 - 1e-9


# ------------------------------------------------------------------------------- 모양 값


_VALID = [
    {},
    {"shape": "rect", "adj": [0], "fillAlpha": 20, "line": "auto", "lineWidth": 1.5},
    {"shape": "ellipse", "fillAlpha": 0, "line": "none"},
    {"shape": "lbox", "adj": [0.35, 0.6]},
    {"shape": "lbox", "adj": [0.35, 0.35], "flip": True},
    {"shape": "cbox", "adj": [0.95, 0.49], "lineStyle": "dashed", "lineWidth": 6},
    {"shape": "frame", "adj": [0.02]},
    {"shape": "triangle", "adj": [0], "line": "ink"},
    {"shape": "triangle", "adj": [1]},
    {"shape": "cross", "adj": [0.07], "fillAlpha": 100},
    {"shape": "arrowblock", "adj": [1, 0.05], "line": "sky", "lineWidth": 0.75},
    {"adj": [0.3]},
    {"fillAlpha": 55, "lineStyle": "dotted"},
]


@pytest.mark.parametrize("look", _VALID)
def test_a_clean_shape_look_has_the_python_canonical_text(look: dict[str, Any]) -> None:
    (text,) = _run({"looks": [json.loads(json.dumps(look))]})["looks"]
    assert text == mark_look({"look": look}, "shape", "S1")


def test_the_editor_drops_shape_values_the_server_would_refuse() -> None:
    """파이썬은 틀린 값을 거부하지만 편집기는 그릴 수 있는 것만 쥔다 — 개수·범위가 어긋난 모양 조절
    값, 강조색 선, 5 단위가 아닌 투명도, 모르는 프리셋(사각형으로)을 뺀다. 0.01 단위가 아닌 값은
    맞춘다."""
    out = _run(
        {
            "looks": [
                {"shape": "lbox", "adj": [0.5]},
                {"shape": "lbox", "adj": [0.01, 0.5]},
                {"shape": "hexagon", "adj": [0.5]},
                {"line": "accent", "fillAlpha": 7, "head": "LL"},
                {"adj": [0.333]},
                {"adj": ["0.5"]},
            ],
            "adjs": [
                {},
                {"shape": "lbox"},
                {"shape": "lbox", "adj": [0.5, 0.5]},
                {"shape": "cross", "adj": [9]},
            ],
            "presets": [{}, {"shape": "diamond"}, {"shape": "nope"}, None],
            "fills": ["ink", "surface", "rose", "accent", "", None],
        }
    )
    assert out["looks"] == [
        '{"shape":"lbox"}',
        '{"shape":"lbox"}',
        '{"adj":[0.5]}',
        "",
        '{"adj":[0.33]}',
        "",
    ]
    assert out["adjs"] == [[0], [0.35, 0.35], [0.5, 0.5], [0.34]]
    assert out["presets"] == ["rect", "diamond", "rect", "rect"]
    assert out["fills"] == ["ink", "surface", "rose", "blue", "blue", "blue"]


def test_copy_and_paste_carry_the_shape_look() -> None:
    """Ctrl+C/V 요소 복사(`clipOf` → `readMark`)에 도형의 프리셋·모양 조절·채우기 투명도가
    따라간다."""
    look = {"shape": "cbox", "adj": [0.5, 0.2], "fillAlpha": 60}
    out = _run_clipboard(
        fab=False,
        blocked=False,
        marks=[["S1", "shape", 10, 20, 8, 8, {"label": "자재", "color": "ink", "look": look}]],
        copy=["S1"],
    )
    assert out["paste1"]["marks"] == [["shape", mark_look({"look": look}, "shape", "S"), "자재"]]


# ------------------------------------------------------------------------------- 배선(자산 글자)


def test_shapes_are_drawn_from_the_pure_path_under_the_units() -> None:
    draw = _between("function drawMark(", "function drawAdjusts(")
    assert "const geo = shapePath(preset, lw, lh, adj)" in draw
    assert "body.style.fillOpacity = String(alpha / 100)" in draw
    assert "shapeLineInk(lookValue(item.look, 'shape', 'line'), shapeFillOf(item.color))" in draw
    assert "class: alpha > 0 || item.hatch ? 'sle-shape-hit' : 'sle-shape-hit is-hollow'" in draw
    assert (
        "(item.kind === 'bay' || item.kind === 'shape') && lookValue(item.look, item.kind, 'flip')"
        in draw
    )
    assert "drawAdjusts(group, item, preset, adj, { lw, lh, rot, flip, cx, cy, upp })" in draw
    # 호기 아래 층(영역과 같은 층)에 그린다.
    assert "const onZoneLayer = (item) => item.kind === 'zone' || item.kind === 'shape'" in JS
    assert "(onZoneLayer(item) ? zonesLayer : marksLayer).append(buildMark(item))" in JS
    assert "shape: { name: '도형', size: [8, 6], label: '', rotatable: true }," in JS
    # 막는 요소가 아니다.
    blocks = JS[
        JS.index("const blocks = (m) =>") : JS.index("\n", JS.index("const blocks = (m) =>"))
    ]
    assert "shape" not in blocks


def test_shapes_catch_the_pointer_only_on_their_drawing() -> None:
    def rule(selector: str) -> str:
        start = CSS.index(selector + " {")
        return CSS[start : CSS.index("}", start)]

    assert "pointer-events: none" in rule(".mark-shape .sle-mark-box")
    hit = rule(".sle-shape-hit")
    assert "pointer-events: all" in hit and "stroke-width: 12" in hit
    assert "non-scaling-stroke" in hit
    assert "pointer-events: stroke" in rule(".sle-shape-hit.is-hollow")
    assert "pointer-events: all" in rule(".mark-shape .sle-mark-text.is-grab")
    adjust = rule(".sle-adjust")
    assert "var(--sle-adjust)" in adjust and "display: none" in adjust
    assert "display: inline" in rule(".sle:not(.is-view) .sle-item.is-selected .sle-adjust")
    assert "display: none !important" in rule(".sle-canvas.is-multi .sle-adjust")


def test_handles_of_a_mark_under_the_units_are_raised_to_the_top_layer() -> None:
    """호기 아래 층(영역·도형)에서 하나만 고른 것의 크기·모양 조절 손잡이는 맨 위 층
    (`sle-overlay`)에 다시 선다 — 호기가 덮은 귀에서도 잡힌다. 누르면 data-for 의 요소 손잡이를
    누른 것과 같다."""

    def rule(selector: str) -> str:
        start = CSS.index(selector + " {")
        return CSS[start : CSS.index("}", start)]

    box = _between("function drawSelectionBox(", "function markSelection(")
    assert "!VIEW && chosen.length === 1 && isMark(chosen[0]) && onZoneLayer(chosen[0])" in box
    assert "proxyHandles(chosen[0])" in box
    proxy = _between("function proxyHandles(", "function markSelection(")
    assert "group.querySelectorAll('.sle-handle, .sle-adjust')" in proxy
    assert "proxy.dataset.for = item.id" in proxy and "overlay.append(proxy)" in proxy
    down = _between("svg.onpointerdown = ", "svg.onpointermove = ")
    assert "const proxyFor = event.target.dataset ? event.target.dataset.for : undefined" in down
    assert "S.groups.get(proxyFor)" in down
    assert "display: none !important" in rule(".sle-zones .sle-handle, .sle-zones .sle-adjust")
    assert "pointer-events: auto" in rule(".sle-proxy-handle")
    assert "display: inline" in rule(".sle:not(.is-view) .sle-overlay .sle-proxy-adjust")
    # 노란 손잡이를 끄는 동안 맨 위 층 손잡이도 따라간다.
    move = _between("svg.onpointermove = ", "svg.onpointerup = ")
    adjust = move[move.index("if (drag.mode === 'adjust') {") :]
    assert "drawSelectionBox()" in adjust[: adjust.index("return\n")]


def test_the_yellow_handle_drag_is_one_undo_step_and_shift_keeps_the_ratio() -> None:
    down = _between("svg.onpointerdown = ", "svg.onpointermove = ")
    assert "if (additive && !grip) {" in down
    assert "mode: 'adjust', index: Number(event.target.dataset.index) || 0" in down
    assert "grab: { x: Number.isFinite(tx) ? tx - p.x : 0" in down
    move = _between("svg.onpointermove = ", "svg.onpointerup = ")
    assert (
        "adjustedLook(item, drag.index, { x: p.x + drag.grab.x, top: p.top + drag.grab.top })"
        in move
    )
    assert "if (event.shiftKey && item.kind === 'shape' && drag.dir.length === 2) {" in move
    assert "keepAspect(before, item, drag.dir, W(), H(), minSize(), SCALE)" in move
    up = _between("svg.onpointerup = ", "svg.onlostpointercapture = ")
    assert "if (item && lookText(before.look) !== lookText(item.look)) " in up
    assert "pushUndo([{ op: 'set', id: item.id, before }])" in up
    mark = _between("function buildMark(", "// 트레이 칩.")
    assert (
        "if (item.kind === 'shape' && !VIEW) group.append(el('g', { class: 'sle-adjusts' }))"
        in mark
    )


def test_the_inspector_and_palette_offer_excel_like_shape_tools() -> None:
    for selector in (
        'class="sle-shape-toggle"',
        'class="sle-shape-palette"',
        'class="sle-shapeprops"',
        'class="sle-shape-swap"',
        'class="sle-shape-gallery"',
        'class="sle-shape-adj"',
        'class="sle-shape-fill"',
        'class="sle-shape-clear"',
        'class="sle-shape-line"',
        'class="sle-shape-width"',
        'class="sle-shape-style"',
        'class="sle-shape-hatch"',
        'class="sle-shape-flip" data-flip="h"',
        'class="sle-shape-flip" data-flip="v"',
    ):
        assert selector in HTML, selector
    # 도형 넣기는 층·FAB 둘 다다(층 전용·FAB 전용 꼬리표가 없다).
    toggle = HTML[
        HTML.index('class="sle-shape-toggle"') - 40 : HTML.index('class="sle-shape-toggle"')
    ]
    assert "sle-floor-only" not in toggle and "sle-fab-only" not in toggle
    # 도형 바꾸기는 프리셋만 바꾸고 모양 조절 값을 새 프리셋의 처음 값으로(크기·채우기·선·글자는
    # 그대로).
    assert "setShapes({ shape: cell.dataset.shape, adj: null })" in JS
    setter = _between("function setShapes(", "// 브라우저가 쥔 적용 전 편집")
    assert "pushUndo(ops)" in setter and "m.look = next" in setter
    assert "ops.push({ op: 'set', id: m.id, before: snapshot(m) })" in setter
    # 투명도는 엑셀처럼 100 − 불투명.
    assert "setShapes({ fillAlpha: 100 - clear })" in JS
    assert "shapeClear.value = alpha === null ? '' : String(100 - alpha)" in JS
    # 넣기는 누르기(보이는 가운데)·끌기(놓은 자리)·키보드.
    palette = _between(
        "shapePalette.replaceChildren(",
        "for (const button of host.querySelectorAll('.sle-palette [data-kind]'))",
    )
    assert "(p, free) => addMark('shape', p, free, key)" in palette
    assert "if (event.detail === 0) addMark('shape', null, false, key)" in palette
    # 대칭 꼴은 돌리기·뒤집기가 꺼진다.
    assert "markRotate.disabled = still" in JS
    assert "for (const button of shapeFlips) button.disabled = !turns" in JS
