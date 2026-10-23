# Purpose: Space 배치 편집기의 편집 조작 넷과 영역·Main 설비명 모양을 검사한다.

"""2026-10-23 사용자 요청 넷(편집기 조작).

- 정렬선: 끌기·크기 바꾸기·서랍·팔레트에서 놓기·붙여넣기 때 움직이는 것의 왼·가운데·오른 x 와
  아래·가운데·위 y 가 화면에 보이는 다른 호기·도면 요소(모듈 묶음은 범위)의 같은 선과 화면 6px
  안이면 그 선에 붙고 선을 긋는다. Alt 를 누른 채면 붙지 않는다. 격자 붙임보다 먼저다.
- 크기 불러오기: 서랍에서 크기 없는 호기만, 같은 앞 3자리·같은 종류(모듈/호기)에서 이번 편집에
  마지막으로 놓은 것 → 편집본에서 설비명 자연 정렬이 가장 뒤인 것(파이썬 `prefix_sizes`) → 이 층
  가운데 크기.
- 서랍 Shift 범위: 기준 칩부터 누른 칩까지 지금 보이는 차례, Ctrl+Shift 는 더하기, 묶음 칩은 한 칸.
- 복사·붙여넣기: 도면 요소만, 마우스 자리 또는 격자 한 칸 비켜, 영역 안, 새 id, 되돌리기 한 번,
  sessionStorage(막히면 페이지 안 쪽지), 층 블록은 빈 층으로.

순수 판정은 `editor.js` 의 `// <edit-tools>` 구획이고 node 로 떼어 돌린다. 편집기 둘레 함수는
`test_space_module_group` 처럼 선언을 글자 그대로 떼어 그리기·선택만 빈 함수로 둔 채 돌린다.
node·bun 이 없는 PC 에서는 건너뛰고 GitHub Actions 에서는 실패한다.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

import pandas as pd
import pytest
from test_space_layout_edit import _master
from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor
from capa_simulation.services.space_layout_edit import (
    module_parents,
    name_prefix,
    new_unit_options,
    prefix_sizes,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")

_TOOLS = re.compile(r"// <edit-tools>\n(?P<body>.*?)\n\s*// </edit-tools>", re.S)
_TILING = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  snaps: (input.snaps || []).map((c) => nearestSnap(c.moving, c.targets, c.tol)),
  segments: (input.segments || []).map((c) =>
    guideSegments(c.box, c.others, c.eps, c.useX, c.useY)),
  prefixes: (input.prefixes || []).map((name) => namePrefix(name)),
  borrowed: (input.borrowed || []).map((c) => borrowedSize(c.name, c.kind, c.recent, c.saved)),
  ranges: (input.ranges || []).map((c) => trayRangeIds(c.order, c.anchor, c.target)),
  pastes: (input.pastes || []).map((c) => pasteShift(c.marks, c.canvas, c.at, c.offset, 10)),
  links: (input.links || []).map((c) => freeLinks(c.count, c.taken, c.targets)),
}))
"""


def _run_tools(payload: dict[str, Any]) -> dict[str, Any]:
    return _node(_block(_TOOLS) + _RUNNER, payload)


# ---------------------------------------------------------------- 순수 판정(node)


def test_a_line_within_the_tolerance_snaps_to_the_nearest_target() -> None:
    """움직이는 선 셋 가운데 목표 선과 가장 가까운 짝의 이동량이다. 허용 거리 밖이면 null."""
    result = _run_tools(
        {
            "snaps": [
                {"moving": [10, 15, 20], "targets": [30, 20.6, 9.2], "tol": 1},
                {"moving": [10, 15, 20], "targets": [30, 22], "tol": 1},
                {"moving": [10, 15, 20], "targets": [14.5, 10.5], "tol": 1},
                {"moving": [0], "targets": [], "tol": 5},
            ]
        }
    )

    snaps = result["snaps"]
    assert abs(snaps[0] - 0.6) < 1e-9
    assert snaps[1] is None
    # 같은 거리면 먼저 본 짝(움직이는 선 차례 → 목표 선 차례)이 이긴다.
    assert snaps[2] == 0.5
    assert snaps[3] is None


def test_guide_segments_join_every_box_sharing_the_line() -> None:
    """붙은 선마다 한 줄이고, 길이는 움직이는 상자와 그 선을 함께 쓰는 상자들을 모두 잇는다. 쓸 선만
    본다(크기 바꾸기는 움직이는 변만)."""
    box = {"x": 10, "y": 10, "w": 10, "h": 4}
    others = [
        {"x": 10, "y": 30, "w": 6, "h": 2},  # 왼쪽 선 같음(위)
        {"x": 2, "y": 0, "w": 8, "h": 3},  # 오른쪽 변 x=10 이 왼쪽 선과 같음(아래)
        {"x": 40, "y": 14, "w": 5, "h": 5},  # 아래 변 y=14 가 위 선과 같음
        {"x": 60, "y": 60, "w": 1, "h": 1},  # 아무 선도 같지 않음
    ]
    result = _run_tools(
        {
            "segments": [
                {"box": box, "others": others, "eps": 0.05},
                {"box": box, "others": others, "eps": 0.05, "useX": [2], "useY": [2]},
            ]
        }
    )

    full, edges = result["segments"]
    assert full == [
        {"axis": "x", "at": 10, "from": 0, "to": 32},
        {"axis": "y", "at": 14, "from": 10, "to": 45},
    ]
    assert edges == [{"axis": "y", "at": 14, "from": 10, "to": 45}]


def test_the_name_prefix_matches_python() -> None:
    """앞 3자리 = 앞뒤 공백을 걷은 첫 세 글자(대소문자 그대로, 코드 포인트). 세 글자보다 짧으면 ''.
    BMP 밖 글자가 섞여도 파이썬 `name_prefix` 와 같다."""
    rnd = random.Random(20261023)
    parts = ["SMP", "-", "DAF", "1", "a", "가", " ", "\U0001f600", "\U00010400", "Σ", "ẞ", "  "]
    parts += ["\ufeff", "\x1c", "\x85", "\xa0", "\u2028", "\t"]
    names = ["SMP-DAF-11", " smp-x ", "AB", "  AB  ", "", "가나다라", "\U0001f600\U0001f600x"]
    # JS `trim` 과 파이썬 `str.strip` 이 다르게 걷는 글자 — BOM 은 남고,
    # U+001C~U+001F·U+0085 는 걷힌다.
    names += ["\ufeffABC-1", "ABC\ufeff", "\x1cABC-1", "\x1f\x85ABC", "AB\x85", "\u3000\u2028ABC"]
    names += ["".join(rnd.choice(parts) for _ in range(rnd.randint(0, 6))) for _ in range(300)]

    result = _run_tools({"prefixes": names})

    assert result["prefixes"] == [name_prefix(name) for name in names]
    assert name_prefix("SMP-DAF-11") == "SMP" and name_prefix(" smp-x ") == "smp"
    assert name_prefix("AB") == "" and name_prefix(None) == "" and name_prefix(pd.NA) == ""


def test_a_sizeless_unit_borrows_the_last_placed_then_the_saved_size() -> None:
    """같은 앞 3자리·같은 종류에서 이번 편집에 마지막으로 놓은 것 → 편집본 표 → 없음(null)."""
    saved = {
        "unit": {"SMP": {"name": "SMP-DAF-30", "w": 9, "h": 5}},
        "module": {"SMP": {"name": "SMP-GRP-9D", "w": 4, "h": 3}},
    }
    recent = [
        {"name": "SMP-DAF-11", "kind": "unit", "w": 12, "h": 7},
        {"name": "SMP-DAF-12", "kind": "unit", "w": 14, "h": 8},
        {"name": "SMP-GRP-1A", "kind": "module", "w": 6, "h": 4},
        {"name": "WBD-01", "kind": "unit", "w": 30, "h": 20},
    ]
    result = _run_tools(
        {
            "borrowed": [
                {"name": "SMP-DAF-40", "kind": "unit", "recent": recent, "saved": saved},
                {"name": "SMP-GRP-4A", "kind": "module", "recent": recent, "saved": saved},
                {"name": "SMP-DAF-40", "kind": "unit", "recent": [], "saved": saved},
                {"name": "SMP-GRP-4A", "kind": "module", "recent": recent[:2], "saved": saved},
                {"name": "smp-daf-40", "kind": "unit", "recent": recent, "saved": saved},
                {"name": "XY", "kind": "unit", "recent": recent, "saved": saved},
                {"name": "QQQ-1", "kind": "unit", "recent": recent, "saved": {}},
                {"name": "WBD-02", "kind": "module", "recent": recent, "saved": saved},
            ]
        }
    )

    assert result["borrowed"] == [
        {"from": "SMP-DAF-12", "w": 14, "h": 8},
        {"from": "SMP-GRP-1A", "w": 6, "h": 4},
        {"from": "SMP-DAF-30", "w": 9, "h": 5},
        {"from": "SMP-GRP-9D", "w": 4, "h": 3},
        # 대소문자가 다르면 다른 앞 3자리다.
        None,
        None,
        None,
        # 모듈은 호기(unit) 크기를 빌리지 않는다.
        None,
    ]


def test_shift_picks_the_visible_chips_between_the_anchor_and_the_click() -> None:
    """기준 칩부터 누른 칩까지(어느 쪽이 앞이든) 보이는 칩만, 묶음 칩은 한 칸(모듈 id 모두)이다.
    기준 칩이 서랍에 없으면 null(그냥 누른 것으로)."""
    order = [
        {"id": "A", "visible": True, "ids": ["A"]},
        {"id": "G1", "visible": True, "ids": ["G1A", "G1B", "G1C", "G1D"]},
        {"id": "B", "visible": False, "ids": ["B"]},
        {"id": "C", "visible": True, "ids": ["C"]},
        {"id": "D", "visible": True, "ids": ["D"]},
    ]
    result = _run_tools(
        {
            "ranges": [
                {"order": order, "anchor": "A", "target": "C"},
                {"order": order, "anchor": "D", "target": "G1"},
                {"order": order, "anchor": "B", "target": "D"},
                {"order": order, "anchor": "C", "target": "C"},
                {"order": order, "anchor": "Z", "target": "C"},
                {"order": order, "anchor": None, "target": "C"},
            ]
        }
    )

    assert result["ranges"] == [
        ["A", "G1A", "G1B", "G1C", "G1D", "C"],
        ["G1A", "G1B", "G1C", "G1D", "C", "D"],
        ["C", "D"],
        ["C"],
        None,
        None,
    ]


def test_a_paste_keeps_the_shape_and_stays_inside_the_canvas() -> None:
    """마우스 자리면 그 자리가 묶음의 왼쪽 아래, 아니면 오른쪽·아래로 offset. 영역 안으로 밀고
    눈금에 맞춘다. 비켜 붙일 때 영역 끝에 막혀 0 이 된 축은 반대쪽으로 같은 거리. 영역보다 크면
    null."""
    marks = [{"x": 10, "y": 20, "w": 4, "h": 2}, {"x": 16, "y": 18, "w": 2, "h": 2}]
    canvas = {"w": 100, "h": 60}
    result = _run_tools(
        {
            "pastes": [
                {"marks": marks, "canvas": canvas, "at": None, "offset": 1},
                {"marks": marks, "canvas": canvas, "at": None, "offset": 3},
                {"marks": marks, "canvas": canvas, "at": {"x": 50.04, "y": 30.06}, "offset": 0},
                {"marks": marks, "canvas": canvas, "at": {"x": 97, "y": -5}, "offset": 0},
                {
                    "marks": [{"x": 0, "y": 0, "w": 4, "h": 2}],
                    "canvas": canvas,
                    "at": None,
                    "offset": 1,
                },
                {
                    "marks": [{"x": 0, "y": 0, "w": 120, "h": 2}],
                    "canvas": canvas,
                    "at": None,
                    "offset": 1,
                },
                # 오른쪽 아래 끝의 기둥 — 두 축 다 막혀 반대쪽(왼쪽·위)으로.
                {
                    "marks": [{"x": 98.5, "y": 0, "w": 1.5, "h": 1.5}],
                    "canvas": canvas,
                    "at": None,
                    "offset": 2,
                },
                # 바닥에 닿은 전체 폭 통로 — 가로는 양쪽 다 막혀 0, 세로만 위로.
                {
                    "marks": [{"x": 0, "y": 0, "w": 100, "h": 4}],
                    "canvas": canvas,
                    "at": None,
                    "offset": 1,
                },
                # 영역을 가득 채운 요소 — 어느 쪽으로도 못 비킨다.
                {
                    "marks": [{"x": 0, "y": 0, "w": 100, "h": 60}],
                    "canvas": canvas,
                    "at": None,
                    "offset": 1,
                },
            ]
        }
    )

    pastes = result["pastes"]
    assert pastes[0] == {"dx": 1, "dy": -1}
    assert pastes[1] == {"dx": 3, "dy": -3}
    assert pastes[2] == {"dx": 40, "dy": 12.1}
    # 오른쪽 끝(18 → 100)·바닥(18 → 0)에 막힌다.
    assert pastes[3] == {"dx": 82, "dy": -18}
    # 바닥(0)에 닿은 요소 — 아래로 못 비켜 위로 같은 거리(원본 자리에 쌓이지 않게).
    assert pastes[4] == {"dx": 1, "dy": 1}
    assert pastes[5] is None
    assert pastes[6] == {"dx": -2, "dy": 2}
    assert pastes[7] == {"dx": 0, "dy": 1}
    assert pastes[8] == {"dx": 0, "dy": 0}


def test_pasted_floor_blocks_take_the_first_free_floors() -> None:
    result = _run_tools(
        {
            "links": [
                {"count": 2, "taken": ["C1 1F"], "targets": ["C1 1F", "C1 2F", "C1 3F"]},
                {"count": 2, "taken": ["C1 1F", "C1 2F"], "targets": ["C1 1F", "C1 2F"]},
                {"count": 1, "taken": [], "targets": []},
                {"count": 0, "taken": [], "targets": ["C1 1F"]},
            ]
        }
    )

    assert result["links"] == [["C1 2F", "C1 3F"], ["C1 1F", "C1 1F"], [""], []]


# ---------------------------------------------------------------- 편집기 둘레(node, 선언 그대로)

_GUIDE_DECLS = (
    "const isUnit = ",
    "const onCanvas = ",
    "const groupKeyOf = ",
    "const groupCounts = ",
    "const bbox = ",
    "const roundTo = ",
    "const snapDelta = ",
    "const clamp = ",
    "const GUIDE_PX = ",
    "const guideTol = ",
    "const GUIDE_EPS = ",
    "function guideTargets(",
    "const boxRect = ",
    "function dragGuides(",
    "const edgeLines = ",
    "function alignDrag(",
    "function dropSpot(",
)
_GUIDE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const S = { items: new Map(), ghosts: new Map(), original: new Map(), view: input.view, step: 0.5 }
const W = () => input.canvas.w
const H = () => input.canvas.h
const viewW = () => input.viewSize.w
const viewH = () => input.viewSize.h
const unitsPerPx = () => input.upp
%s
%s
for (const raw of input.items) {
  const m = { kind: 'unit', placed: true, moveTo: null, group: null, ...raw }
  ;(m.ghost ? S.ghosts : S.items).set(m.id, m)
}
const sorted = (boxes) => boxes.map((b) => [b.x, b.y, b.w, b.h])
  .sort((a, b) => a[0] - b[0] || a[1] - b[1])
const moveBox = { minX: 50, minY: 20, maxR: 60, maxT: 25 }
const out = {
  all: sorted(guideTargets(new Set()).boxes),
  withoutGroup: sorted(guideTargets(new Set(['G1-B'])).boxes),
  move: alignDrag({ mode: 'move', ids: ['M'], box: moveBox }, 9.7, 0, false),
  moveFree: alignDrag({ mode: 'move', ids: ['M'], box: moveBox }, 9.7, 0, true),
  moveFar: alignDrag({ mode: 'move', ids: ['M'], box: moveBox }, 3, 0, false),
  moveY: alignDrag({ mode: 'move', ids: ['M'], box: moveBox }, 0, -14.8, false),
  resizeE: alignDrag({ mode: 'resize', id: 'M', ids: ['M'], dir: 'e',
    befores: new Map([['M', { x: 50, y: 20, w: 10, h: 5 }]]) }, 9.8, 0, false),
  resizeW: alignDrag({ mode: 'resize', id: 'M', ids: ['M'], dir: 'w',
    befores: new Map([['M', { x: 50, y: 20, w: 10, h: 5 }]]) }, 9.8, 0, false),
  drop: dropSpot({ x: 75.2, top: 100 - 22.4 }, 10, 5, false),
  dropFree: dropSpot({ x: 75.2, top: 100 - 22.4 }, 10, 5, true),
  dropEdge: dropSpot({ x: 1, top: 1 }, 10, 5, true),
}
process.stdout.write(JSON.stringify(out))
"""


def _run_guides(items: list[dict[str, Any]]) -> dict[str, Any]:
    decls = "\n".join(_js_decl(head) for head in _GUIDE_DECLS)
    source = _GUIDE_RUNNER % (_block(_TOOLS), decls)
    payload = {
        "canvas": {"w": 200, "h": 100},
        "view": {"x": -5, "top": -5, "z": 1},
        "viewSize": {"w": 160, "h": 110},
        "upp": 0.2,
        "items": items,
    }
    return _node(source, payload)


def test_guides_snap_to_ranges_and_visible_boxes_and_alt_frees_them() -> None:
    """정렬선 상자는 화면에 걸친 것만이고, 모듈 묶음은 범위 하나(숨은 모듈 포함)다 — 묶음 모듈
    하나라도 움직이면 그 묶음은 통째로 빠진다. 허용 거리(6px × 0.2 = 1.2) 안의 선에 붙고,
    Alt(free)면 붙지 않는다. 크기 바꾸기는 움직이는 변만 붙는다. 놓기(`dropSpot`)는 격자보다
    정렬선이 이기고 영역 안으로 민다."""
    items = [
        {"id": "M", "x": 50, "y": 20, "w": 10, "h": 5},
        {"id": "A", "x": 70, "y": 40, "w": 10, "h": 6},
        {"id": "G1-A", "group": "G1", "x": 20, "y": 5, "w": 5, "h": 3},
        {"id": "G1-B", "group": "G1", "x": 25, "y": 5, "w": 5, "h": 3},
        {"id": "G1-C", "group": "G1", "x": 20, "y": 2, "w": 5, "h": 3, "ghost": True},
        {"id": "FAR", "x": 180, "y": 90, "w": 5, "h": 5},
        {"id": "Z1", "kind": "zone", "x": 0, "y": 60, "w": 30, "h": 10},
        {"id": "AWAY", "x": 100, "y": 10, "w": 5, "h": 5, "moveTo": "C2 2F"},
    ]
    out = _run_guides(items)

    assert out["all"] == [
        [0, 60, 30, 10],
        [20, 2, 10, 6],
        [50, 20, 10, 5],
        [70, 40, 10, 6],
    ]
    assert [70, 40, 10, 6] in out["withoutGroup"] and [20, 2, 10, 6] not in out["withoutGroup"]
    # 왼쪽 변 50+9.7=59.7 → 오른쪽 변이 A 의 왼쪽 70 에 0.3 가까움(60+9.7=69.7) — 붙여 dx=10.
    assert abs(out["move"]["dx"] - 10) < 1e-9 and out["move"]["dTop"] is None
    assert out["moveFree"] == {"dx": None, "dTop": None}
    assert out["moveFar"] == {"dx": None, "dTop": None}
    # 위로 14.8 → 아래 변 34.8, 위 변 39.8 이 A 의 아래 40 에 붙는다(dTop = -15).
    assert out["moveY"]["dx"] is None and abs(out["moveY"]["dTop"] + 15) < 1e-9
    assert abs(out["resizeE"]["dx"] - 10) < 1e-9
    # 왼쪽 변 손잡이는 왼쪽 변만 본다 — 59.8 둘레 1.2 안에 다른 상자의 선이 없다(오른쪽 변이
    # 70 에 닿아도 붙지 않는다).
    assert out["resizeW"]["dx"] is None
    # 놓기: 점(75.2, 22.4)이 가운데인 10×5 → 손 그대로 (70.2, 19.9). 정렬선이 A 의 왼쪽 70·M 의
    # 아래 20 에 붙인다. Alt 면 격자(0.5)로만 — 여기서는 같은 자리지만 선이 없다.
    drop, free = out["drop"], out["dropFree"]
    assert (drop["x"], drop["y"]) == (70, 20)
    assert {(s["axis"], s["at"]) for s in drop["segments"]} >= {("x", 70), ("y", 20)}
    assert (free["x"], free["y"], free["segments"]) == (70, 20, [])
    assert (out["dropEdge"]["x"], out["dropEdge"]["y"]) == (0, 95)


_TRAY_DECLS = (
    "const isUnit = ",
    "const onCanvas = ",
    "const hasSize = ",
    "const members = ",
    "const groupKeyOf = ",
    "const ghostsOf = ",
    "const moduleMembers = ",
    "const roundTo = ",
    "const sizeKind = ",
    "function recentSizes(",
    "function trayPlan(",
)
_TRAY_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const S = { items: new Map(), ghosts: new Map(), original: new Map(), placedLog: input.log }
const PREFIX_SIZES = input.saved
const MODULE_PARENTS = new Set(input.moduleParents || [])
const defaultSize = { w: 12, h: 7 }
%s
%s
%s
for (const raw of input.items) {
  const m = {
    kind: 'unit', placed: false, moveTo: null, group: null, sizeGuessed: false, sizeFrom: '',
    ...raw,
  }
  m.label = m.label || m.id
  for (const k of ['x', 'y', 'w', 'h']) if (m[k] === null || m[k] === undefined) m[k] = NaN
  S.items.set(m.id, m)
}
const plan = (ids) => {
  const p = trayPlan(ids.map((id) => S.items.get(id)))
  return { footprint: p.footprint, sizes: p.pieces.map((piece) => piece.sizes) }
}
const cases = input.cases.map((c) => [c.name, plan(c.ids)])
process.stdout.write(JSON.stringify(Object.fromEntries(cases)))
"""


def test_the_tray_borrows_sizes_only_for_sizeless_units() -> None:
    """크기 없는 호기만 빌린다 — 이번 편집에 놓은 것 가운데 도면에 서 있고 어림한 크기가 아닌 마지막
    것(같은 종류), 같이 놓는 제 크기 호기, 편집본 표, 이 층 가운데 크기 차례다. 모듈 묶음은 모듈마다
    빌린 크기로 범위를 잡는다(모듈 칸 크기)."""
    items = [
        {"id": "SMP-A1", "placed": True, "x": 0, "y": 0, "w": 10, "h": 8},
        {"id": "SMP-A2", "placed": True, "x": 20, "y": 0, "w": 11, "h": 9},
        # 이 층 가운데 크기로 어림해 놓은 것은 빌려 주지 않는다.
        {"id": "SMP-A3", "placed": True, "x": 40, "y": 0, "w": 12, "h": 7, "sizeGuessed": True},
        {"id": "SMP-NEW", "w": None, "h": None},
        {"id": "SMP-OWN", "w": 5, "h": 4},
        {"id": "QRS-NEW", "w": None, "h": None},
        {"id": "XYZ-NEW", "w": None, "h": None},
        {"id": "SMP-G-A", "group": "SMP-G", "w": None, "h": None},
        {"id": "SMP-G-B", "group": "SMP-G", "w": None, "h": None},
        {"id": "SMP-G-C", "group": "SMP-G", "w": None, "h": None},
        {"id": "SMP-G-D", "group": "SMP-G", "w": None, "h": None},
        # 형제가 이 편집기에 실리지 않은 모듈(설비 마스터에서는 Main 설비 행이 둘 이상) —
        # 모듈 크기를 빌린다.
        {"id": "SMP-X-1A", "group": "SMP-X", "w": None, "h": None},
    ]
    payload = {
        "items": items,
        "moduleParents": ["SMP-G", "SMP-X"],
        "log": ["SMP-A1", "SMP-A2", "SMP-A3", "GONE"],
        "saved": {
            "unit": {"QRS": {"name": "QRS-99", "w": 3, "h": 2}},
            "module": {"SMP": {"name": "SMP-Z-1D", "w": 6, "h": 4}},
        },
        "cases": [
            {"name": "last_placed", "ids": ["SMP-NEW"]},
            {"name": "with_own", "ids": ["SMP-NEW", "SMP-OWN"]},
            {"name": "saved", "ids": ["QRS-NEW"]},
            {"name": "fallback", "ids": ["XYZ-NEW"]},
            {"name": "own", "ids": ["SMP-OWN"]},
            {"name": "group", "ids": ["SMP-G-A"]},
            {"name": "lone_module", "ids": ["SMP-X-1A"]},
        ],
    }
    source = _TRAY_RUNNER % (
        _block(_TILING),
        _block(_TOOLS),
        "\n".join(_js_decl(head) for head in _TRAY_DECLS),
    )
    out = _node(source, payload)

    def size(case: str, piece: int = 0, unit: int = 0) -> dict[str, Any]:
        result: dict[str, Any] = out[case]["sizes"][piece][unit]
        return result

    assert size("last_placed") == {"w": 11, "h": 9, "guessed": True, "from": "SMP-A2"}
    assert size("with_own") == {"w": 5, "h": 4, "guessed": True, "from": "SMP-OWN"}
    assert size("with_own", 1) == {"w": 5, "h": 4, "guessed": False, "from": ""}
    assert size("saved") == {"w": 3, "h": 2, "guessed": True, "from": "QRS-99"}
    assert size("fallback") == {"w": 12, "h": 7, "guessed": True, "from": ""}
    assert size("own") == {"w": 5, "h": 4, "guessed": False, "from": ""}
    group = out["group"]["sizes"][0]
    assert {json.dumps(s, sort_keys=True) for s in group} == {
        json.dumps({"w": 6, "h": 4, "guessed": True, "from": "SMP-Z-1D"}, sort_keys=True)
    }
    assert out["group"]["footprint"] == {"w": 12, "h": 8}
    # 편집기에 하나만 실린 모듈도 파이썬 `prefix_sizes` 처럼 모듈이다 — 이번에 놓은 호기(SMP-A2)가
    # 아니라 편집본의 모듈 크기를 빌린다.
    assert size("lone_module") == {"w": 6, "h": 4, "guessed": True, "from": "SMP-Z-1D"}


_CLIP_DECLS = (
    "const isUnit = ",
    "const isMark = ",
    "const MARK_KINDS = {",
    "const drawable = ",
    "const num = ",
    "const roundTo = ",
    "const floorTo = ",
    "const snapDelta = ",
    "const clamp = ",
    "const minSize = ",
    "const fit = ",
    "const fontSizeOf = ",
    "const BORDER_STYLES = ",
    "const LABEL_ALIGNS = ",
    "const pickOr = ",
    "const readMark = ",
    "const bbox = ",
    "const boxRect = ",
    "const linkedFloors = ",
    "const CLIP_KEY = ",
    "const clipMemo = ",
    "const clipOf = ",
    "function writeClipboard(",
    "function readClipboard(",
    "function copyMarks(",
    "function stacksOnMarks(",
    "function pasteMarks(",
)
_CLIP_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const FAB = input.fab
const SCOPE = FAB ? 'fab' : 'floor'
const FONT_SIZES = [9, 11, 13]
const LINK_TARGETS = ['C1 1F', 'C1 2F', 'C1 3F']
const store = new Map()
const guard = () => { if (input.blocked) throw new Error('blocked') }
const window = { sessionStorage: {
  getItem: (k) => { guard(); return store.has(k) ? store.get(k) : null },
  setItem: (k, v) => { guard(); store.set(k, v) },
} }
const S = {
  items: new Map(), selection: new Set(), step: 0.5, seq: 0, hover: null, pasteSerial: 0, flash: '',
  note: '',
}
const W = () => 100
const H = () => 60
const undo = []
const pushUndo = (ops) => { if (ops.length) undo.push(ops) }
const renderItems = () => {}
const updateStatus = () => {}
const flashGuides = () => {}
const svg = { focus: () => {} }
const selectedItems = () => [...S.selection].map((id) => S.items.get(id))
const setSelection = (ids) => { S.selection = new Set(ids) }
const tick = (v) => Math.round(v * 10) / 10
const dropSpot = (p, w, h) => ({
  x: tick(p.x - w / 2), y: tick(H() - p.top - h / 2), w, h, segments: [],
})
%s
%s
const mark = (id, kind, x, y, w, h, extra) => S.items.set(id, {
  id, kind, x, y, w, h, rot: 0, label: '', color: '', hatch: false, keepOut: false, link: '',
  fontSize: null, fontColor: '', placed: true, moveTo: null, ...extra,
})
for (const raw of input.marks) mark(...raw)
S.items.set('U1', { id: 'U1', kind: 'unit', x: 1, y: 1, w: 2, h: 2, placed: true })
const ids = () => [...S.items.keys()]
const view = (id) => {
  const m = S.items.get(id)
  return [m.kind, m.x, m.y, m.w, m.h, m.label, m.link || '']
}
const steps = {}
S.selection = new Set(['U1'])
steps.unitsOnly = { handled: copyMarks(), flash: S.flash, clip: readClipboard() }
S.selection = new Set(input.copy)
steps.copied = { handled: copyMarks(), flash: S.flash }
const before = new Set(ids())
steps.paste1 = { handled: pasteMarks(false) }
const first = ids().filter((id) => !before.has(id))
steps.paste1.items = first.map(view)
steps.paste1.selected = [...S.selection]
steps.paste1.looks = first.map((id) => [S.items.get(id).borderStyle, S.items.get(id).labelAlign])
steps.paste1.undo = undo.map((ops) => ops.map((op) => op.op))
const before2 = new Set(ids())
pasteMarks(false)
steps.paste2 = ids().filter((id) => !before2.has(id)).map(view)
S.hover = { x: 50, top: 30 }
const before3 = new Set(ids())
pasteMarks(false)
steps.hovered = ids().filter((id) => !before3.has(id)).map(view)
steps.undoCount = undo.length
steps.memo = Boolean(window.__capaSpaceClipboard && window.__capaSpaceClipboard[SCOPE])
steps.stored = store.has(CLIP_KEY)
process.stdout.write(JSON.stringify(steps))
"""


def _run_clipboard(**payload: Any) -> dict[str, Any]:
    source = _CLIP_RUNNER % (
        _block(_TOOLS),
        "\n".join(_js_decl(head) for head in _CLIP_DECLS),
    )
    return _node(source, payload)


def test_copy_takes_marks_only_and_paste_offsets_with_new_ids_in_one_undo_step() -> None:
    """호기만 고른 Ctrl+C 는 「호기는 복사하지 않습니다」만 알린다. 섞어 고르면 도면 요소만
    복사한다. 마우스가 도면 밖이면 원본에서 격자 한 칸(최소 1)씩 비켜 붙이고(거듭하면 한 칸 더),
    마우스가 도면 위면 그 자리가 가운데다. 새 id, 붙일 때마다 되돌리기 한 번, 붙인 것이 골라진다.
    sessionStorage 에 두고 페이지 안 쪽지에도 둔다."""
    out = _run_clipboard(
        fab=False,
        blocked=False,
        marks=[
            [
                "Z1",
                "zone",
                10,
                20,
                8,
                4,
                {"label": "창고", "color": "green", "borderStyle": "solid", "labelAlign": "right"},
            ],
            ["T1", "text", 30, 22, 6, 2, {"label": "메모"}],
        ],
        copy=["Z1", "T1", "U1"],
    )

    assert out["unitsOnly"]["handled"] is True and out["unitsOnly"]["clip"] is None
    # 영역의 테두리 모양·이름표 정렬도 함께 붙는다(다른 요소는 처음 값).
    assert out["paste1"]["looks"] == [["solid", "right"], ["dashed", "left"]]
    assert "호기는 복사하지 않습니다" in out["unitsOnly"]["flash"]
    assert out["copied"]["handled"] is True
    assert "도면 요소 2개 복사" in out["copied"]["flash"]
    assert "호기는 복사하지 않습니다" in out["copied"]["flash"]
    paste1 = out["paste1"]
    assert paste1["items"] == [
        ["zone", 11, 19, 8, 4, "창고", ""],
        ["text", 31, 21, 6, 2, "메모", ""],
    ]
    assert len(paste1["selected"]) == 2 and not {"Z1", "T1"} & set(paste1["selected"])
    assert paste1["undo"] == [["create", "create"]]
    assert out["paste2"] == [
        ["zone", 12, 18, 8, 4, "창고", ""],
        ["text", 32, 20, 6, 2, "메모", ""],
    ]
    # 묶음(10~36 × 20~24)의 가운데가 마우스(50, 60-30=30) — 왼쪽 아래 (37, 28).
    assert out["hovered"] == [
        ["zone", 37, 28, 8, 4, "창고", ""],
        ["text", 57, 30, 6, 2, "메모", ""],
    ]
    assert out["undoCount"] == 3
    assert out["memo"] is True and out["stored"] is True


def test_paste_lives_without_storage_and_blocks_link_free_floors() -> None:
    """sessionStorage 가 막혀도(던짐) 페이지 안 쪽지로 붙인다. FAB 층 블록은 새로 넣을 때처럼 아직
    블록이 없는 층을 차례로 가리킨다."""
    out = _run_clipboard(
        fab=True,
        blocked=True,
        marks=[["B1", "block", 10, 10, 16, 6, {"link": "C1 1F", "label": "1층"}]],
        copy=["B1"],
    )

    assert out["copied"]["handled"] is True and out["stored"] is False and out["memo"] is True
    assert out["paste1"]["items"] == [["block", 11, 9, 16, 6, "1층", "C1 2F"]]
    assert out["paste2"] == [["block", 12, 8, 16, 6, "1층", "C1 3F"]]
    # 층이 다 찼으면 첫 층.
    assert out["hovered"][0][-1] == "C1 1F"


_STACK_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const FAB = false
const SCOPE = 'floor'
const FONT_SIZES = [9, 11, 13]
const LINK_TARGETS = ['C1 1F']
const window = { sessionStorage: { getItem: () => null, setItem: () => {} } }
const S = {
  items: new Map(), selection: new Set(), step: 0.5, seq: 0, hover: null, pasteSerial: 0, flash: '',
  note: '',
}
const W = () => 100
const H = () => 60
const pushUndo = () => {}
const renderItems = () => {}
const updateStatus = () => {}
const flashGuides = () => {}
const svg = { focus: () => {} }
const selectedItems = () => [...S.selection].map((id) => S.items.get(id))
const setSelection = (ids) => { S.selection = new Set(ids) }
const tick = (v) => Math.round(v * 10) / 10
// 마우스 자리 그대로(정렬선 없이) — 원본 가운데를 가리키면 원본 자리다.
const dropSpot = (p, w, h) => ({
  x: tick(p.x - w / 2), y: tick(H() - p.top - h / 2), w, h, segments: [],
})
%s
%s
const mark = (id, kind, x, y, w, h) => S.items.set(id, {
  id, kind, x, y, w, h, rot: 0, label: '', color: '', hatch: false, keepOut: false, link: '',
  fontSize: null, fontColor: '', placed: true, moveTo: null,
})
mark('T1', 'text', 70, 40, 14, 3)
mark('C1', 'column', 98.5, 0, 1.5, 1.5)
mark('F1', 'zone', 0, 0, 100, 60)
const pasted = (before) => [...S.items.values()]
  .filter((m) => !before.has(m.id)).map((m) => [m.kind, m.x, m.y])
const step = () => {
  const before = new Set(S.items.keys())
  const handled = pasteMarks(false)
  return { handled, items: pasted(before), note: S.note }
}
const out = {}
S.selection = new Set(['T1'])
copyMarks()
S.hover = { x: 77, top: 60 - 41.5 }
out.onSource = step()
out.onSourceAgain = step()
S.hover = { x: 30, top: 30 }
out.elsewhere = step()
S.hover = null
S.selection = new Set(['C1'])
copyMarks()
out.corner = step()
out.cornerAgain = step()
S.selection = new Set(['F1'])
copyMarks()
out.full = step()
process.stdout.write(JSON.stringify(out))
"""


def test_a_paste_never_stacks_exactly_on_the_same_mark() -> None:
    """사본이 같은 종류 요소와 자리·크기까지 똑같이 겹치지 않는다(겹친 사본은 보이지 않은 채
    두 겹으로 저장된다).

    - 고른 직후 마우스를 원본 위에 둔 채 Ctrl+C·V — 마우스 자리가 원본 그대로라 격자 한 칸씩
      비켜 붙인다(거듭하면 한 칸 더). 다른 자리면 그 자리다.
    - 영역 오른쪽 아래 끝의 기둥 — 비켜 붙일 때 막힌 두 축이 반대쪽(왼쪽·위)으로 비킨다.
    - 영역을 가득 채운 영역 — 비킬 자리가 없어 붙이지 않고 알린다."""
    source = _STACK_RUNNER % (
        _block(_TOOLS),
        "\n".join(_js_decl(head) for head in _CLIP_DECLS),
    )
    out = _node(source, {})

    assert out["onSource"]["items"] == [["text", 71, 39]]
    assert out["onSourceAgain"]["items"] == [["text", 72, 38]]
    assert out["elsewhere"]["items"] == [["text", 23, 28.5]]
    assert out["corner"]["items"] == [["column", 97.5, 1]]
    assert out["cornerAgain"]["items"] == [["column", 96.5, 2]]
    assert out["full"]["handled"] is True and out["full"]["items"] == []
    assert "붙이지 않았습니다" in out["full"]["note"]


# ---------------------------------------------------------------- 파이썬 정본 · 자산 글자


def test_prefix_sizes_pick_the_naturally_last_sized_row_per_kind() -> None:
    """편집본에서 앞 3자리마다 크기가 있는 설비 가운데 설비명 자연 정렬이 가장 뒤인 것. 모듈
    묶음의 모듈(Main 설비가 같은 행이 둘 이상)과 그 밖은 따로다. 크기 없거나 0 이하·세 글자 미만
    이름은 뺀다. 서랍 크기 불러오기에 쓰도록 `new_unit_options` 가 함께 보낸다."""
    master = pd.DataFrame(
        {
            "설비명": [
                "SMP-DAF-9",
                "SMP-DAF-11",
                "SMP-DAF-2",
                "SMP-DAF-12",
                "AB",
                "WBD-1A",
                "WBD-1B",
                "WBD-01",
                "smp-low",
            ],
            "Xsize": [10.0, 12.04, 8.0, None, 1.0, 5.0, 5.0, 0.0, 3.0],
            "Ysize": [7.0, 7.96, 6.0, 9.0, 1.0, 4.0, 4.0, 2.0, 2.0],
            "Main 설비": [None, None, None, None, None, "WBD-1", "WBD-1", None, None],
        }
    )

    sizes = prefix_sizes(master)

    assert sizes == {
        "unit": {
            "SMP": {"name": "SMP-DAF-11", "w": 12.0, "h": 8.0},
            "smp": {"name": "smp-low", "w": 3.0, "h": 2.0},
        },
        "module": {"WBD": {"name": "WBD-1B", "w": 5.0, "h": 4.0}},
    }
    json.dumps(sizes, allow_nan=False)
    assert prefix_sizes(master.iloc[0:0]) == {"unit": {}, "module": {}}
    assert new_unit_options(_master())["prefixSizes"] == prefix_sizes(_master())
    # 종류를 가르는 같은 기준(Main 설비 행이 둘 이상)을 편집기에도 보낸다 — 형제가 편집기에 실리지
    # 않은 모듈도 모듈로 빌리게.
    assert module_parents(master) == {"WBD-1"}
    lone = master.copy()
    lone["Main 설비"] = [None, None, None, None, None, "WBD-1", None, None, "X"]
    assert module_parents(lone) == set()
    grouped = _master(
        {"설비명": "MOD-A", "Main 설비": "MOD"},
        {"설비명": "MOD-B", "Main 설비": "MOD"},
        {"설비명": "ONE-A", "Main 설비": "ONE"},
    )
    assert new_unit_options(grouped)["moduleParents"] == ["MOD"]


def test_drags_snap_to_guides_before_the_grid_and_alt_skips_them() -> None:
    """끌기는 정렬선 이동량이 격자 이동량을 이기고(`alignDrag(...) ?? snapDelta`), Alt 면 붙지
    않는다. 끄는 동안 선을 긋고 놓거나 취소하면 지운다. 서랍·팔레트 놓기는 미리 본
    자리(`dropSpot`)에 놓인다. 정렬선은 도면 맨 위 층이고 색은 팔레트의 `guide` 다."""
    move = _between("svg.onpointermove = (event) => {", "svg.onpointerup = ")
    assert (
        "const aligned = alignDrag(drag, p.x - drag.startX, p.top - drag.startTop, event.altKey)"
        in move
    )
    assert "const dx = aligned.dx ?? snapDelta(p.x - drag.startX)" in move
    assert "const dTop = aligned.dTop ?? snapDelta(p.top - drag.startTop)" in move
    assert "showDragGuides(drag, event.altKey)" in move
    assert "clearGuides()" in _between("svg.onpointerup = ", "svg.onlostpointercapture")
    assert "clearGuides()" in _between("function cancelDrag() {", "function resizedBox(")
    ghost = _between("function ghostDrag(", "function pickedTrayEntries(")
    assert "const spot = dropSpot(p, size.w, size.h, e.altKey)" in ghost
    assert "if (p) onDrop(p, e.altKey)" in ghost and "clearGuides()" in ghost
    place = _between("function placeFromTray(", "function addMark(")
    assert "const at = dropSpot(p, footprint.w, footprint.h, free)" in place
    assert "dropSpot(at, w, h, free)" in _between("function addMark(", "// ----")
    assert HTML.index('<g class="sle-overlay"></g>') < HTML.index('<g class="sle-guides"></g>')
    canvas_end = HTML.index("</svg>", HTML.index('class="sle-canvas"'))
    assert HTML.index('<g class="sle-guides"></g>') < canvas_end
    assert "pointer-events: none" in CSS[CSS.index(".sle-guides {") :]
    assert "var(--sle-guide)" in CSS and "guide" in space_layout_editor._palette()


def test_copy_paste_keys_leave_text_fields_alone_and_marks_alone_are_copied() -> None:
    """Ctrl+C·V 는 글 칸에서 입력 중이면 가로채지 않고(앞에서 비킨다) 한글 자판에서도 듣는다. 복사는
    도면 요소(`isMark`)만이고 저장소 읽기·쓰기는 모두 try 안이다. 붙인 요소는 `readMark` 로 새 id 를
    받고 되돌리기 한 번(`pushUndo` 한 번)이다."""
    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    typing = keys.index("if (typing) return")
    copy = keys.index("if (ctrl && letter === 'c')")
    assert typing < copy < keys.index("if (ctrl && letter === 'v')")
    assert "event.code === 'KeyC' ? 'c' : event.code === 'KeyV' ? 'v'" in keys
    copy_body = _between("function copyMarks() {", "function pasteMarks(")
    assert "const marks = chosen.filter(isMark)" in copy_body
    for start, end in (
        ("function writeClipboard(", "function readClipboard("),
        ("function readClipboard(", "function copyMarks("),
    ):
        body = _between(start, end)
        assert "try {" in body and "sessionStorage" in body
    paste = _between("function pasteMarks(", "// 자리를 바꾼 것을 다시 그린다.")
    assert paste.count("pushUndo(") == 1 and "readMark({ ...source, id," in paste
    assert "setSelection(ids, ids[ids.length - 1])" in paste
    assert "freeLinks(" in paste and "S.hover" in paste


def test_borrowed_sizes_are_guesses_and_say_where_they_came_from() -> None:
    """빌린 크기는 `sizeGuessed`(트레이로 다시 빼면 버림)이고 어디서 불러왔는지(`sizeFrom`)를
    상태 줄에 「크기를 … 에서 불러옴」으로 알린다. 되돌리기가 되돌리도록 기록(`snapshot`)에 든다."""
    place = _between("function placeFromTray(", "function addMark(")
    assert "m.sizeGuessed = piece.sizes[k].guessed" in place
    assert "m.sizeFrom = piece.sizes[k].from" in place
    assert "S.placedLog.push(...shown.map((m) => m.id))" in place
    assert "sizeFrom: item.sizeFrom" in _between("const snapshot = (item) => ({", "})")
    note = _between("function sizeNote(list) {", "function updateStatus() {")
    assert "`크기를 ${named} 에서 불러옴`" in note
    remove = _between("function removeItems(list) {", "function sendItems(")
    assert "m.sizeFrom = ''" in remove
    assert "NEW_UNIT.prefixSizes" in JS


# ---------------------------------------------------------------- 영역 모양 · Main 설비명

_LOOK = re.compile(r"// <layout-look>\n(?P<body>.*?)\n\s*// </layout-look>", re.S)
_LOOK_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  tags: input.tags.map((c) => zoneTagX(c.lw, c.tagW, c.align)),
  spots: input.spots.map((c) => groupNameSpot(c.range, c.position, c.fs, c.gap, c.canvasH ?? 100)),
  sizes: input.sizes.map((c) =>
    groupNameSize(c.range, c.position, c.em, c.max, c.upp, c.min ?? 7, c.bare ?? false)),
  shown: (input.shown || []).map((boxes) => shownRange(boxes)),
}))
"""


def test_zone_tags_sit_left_centre_or_right_on_the_top_edge() -> None:
    """영역 이름표 꼬리표는 위 변의 왼쪽(처음 값 — 지금 모습)·가운데·오른쪽이다. 모르는 값은
    왼쪽."""
    out = _node(
        _block(_LOOK) + _LOOK_RUNNER,
        {
            "tags": [
                {"lw": 20, "tagW": 6, "align": "left"},
                {"lw": 20, "tagW": 6, "align": "center"},
                {"lw": 20, "tagW": 6, "align": "right"},
                {"lw": 20, "tagW": 6, "align": "weird"},
            ],
            "spots": [],
            "sizes": [],
        },
    )

    assert out["tags"] == [0, 7, 14, 0]


def test_a_group_name_sits_in_the_middle_or_just_outside_the_range() -> None:
    """가운데(처음 값)는 범위 정가운데(넷이면 모듈 꼭짓점이 만나는 자리), 위·아래는 범위 바깥에
    테두리를 띄워 붙인다(알약 반 높이 fs × 0.8 + 틈). 글자는 화면 최대 크기에서 범위 폭에 맞춰 줄고,
    가운데면 범위 높이의 0.16 배를 넘지 않는다."""
    box = {"x": 10, "y": 20, "w": 24, "h": 16}
    out = _node(
        _block(_LOOK) + _LOOK_RUNNER,
        {
            "tags": [],
            "spots": [
                {"range": box, "position": "center", "fs": 1.5, "gap": 0.25},
                {"range": box, "position": "top", "fs": 1.5, "gap": 0.25},
                {"range": box, "position": "bottom", "fs": 1.5, "gap": 0.25},
            ],
            "sizes": [
                {"range": box, "position": "top", "em": 5, "max": 12, "upp": 0.125},
                {"range": box, "position": "center", "em": 5, "max": 12, "upp": 0.25},
                {"range": {**box, "w": 6}, "position": "top", "em": 10, "max": 12, "upp": 0.05},
            ],
        },
    )

    assert out["spots"] == [
        {"x": 22, "y": 28},
        {"x": 22, "y": 20 + 16 + 0.25 + 1.2},
        {"x": 22, "y": 20 - 0.25 - 1.2},
    ]
    sizes = out["sizes"]
    assert sizes[0] == pytest.approx(1.5)  # 화면 12px × 0.125
    assert sizes[1] == pytest.approx(16 * 0.16)  # 가운데는 범위 높이로 막힌다
    assert sizes[2] == pytest.approx(6 * 0.92 / 10.9)  # 좁은 범위는 폭에 맞춰 준다


def test_a_small_group_keeps_its_centre_name_and_edge_names_turn_inward() -> None:
    """작은 묶음 · 영역 끝 묶음 · 일부만 보이는 묶음의 Main 설비명(2026-10-23 E2E · 리뷰).

    - 범위 12×6(1px = 0.164 단위)인 묶음은 가운데 글자가 범위 높이 0.16 배(5.85px)로 7px
      아래다. 모듈 칸 이름표가 하나도 서 있지 않으면(bare) 7px 알약이 범위 안에 들어 7px 로
      선다 — 모듈 이름표가 서 있으면, 또는 7px 알약이 범위에 안 들면 숨는다(null). 위·아래는
      bare 와 상관없이 7px 아래면 숨는다.
    - 위·아래 알약이 영역 위·아래 끝 밖이면 범위 안쪽 띠로 뒤집는다(좁은 무대에서 잘리지 않게).
    - 보기 화면에서 일부 모듈만 보이면 보이는 모듈 상자의 바깥 상자에 세운다."""
    small = {"x": 50, "y": 30, "w": 12, "h": 6}
    upp = 0.164
    top_edge = {"x": 10, "y": 50, "w": 20, "h": 10}
    floor_edge = {"x": 10, "y": 0, "w": 20, "h": 10}
    out = _node(
        _block(_LOOK) + _LOOK_RUNNER,
        {
            "tags": [],
            "spots": [
                {"range": top_edge, "position": "top", "fs": 1, "gap": 0.2, "canvasH": 60},
                {"range": floor_edge, "position": "bottom", "fs": 1, "gap": 0.2, "canvasH": 60},
                {"range": top_edge, "position": "top", "fs": 1, "gap": 0.2, "canvasH": 70},
                {"range": floor_edge, "position": "top", "fs": 1, "gap": 0.2, "canvasH": 60},
            ],
            "sizes": [
                {
                    "range": small,
                    "position": "center",
                    "em": 3,
                    "max": 12,
                    "upp": upp,
                    "bare": True,
                },
                {"range": small, "position": "center", "em": 3, "max": 12, "upp": upp},
                {"range": small, "position": "top", "em": 3, "max": 12, "upp": upp, "bare": True},
                {
                    "range": {**small, "h": 1.5},
                    "position": "center",
                    "em": 3,
                    "max": 12,
                    "upp": upp,
                    "bare": True,
                },
                {
                    "range": {**small, "w": 3},
                    "position": "center",
                    "em": 3,
                    "max": 12,
                    "upp": upp,
                    "bare": True,
                },
            ],
            "shown": [
                [{"x": 65, "y": 25, "w": 10, "h": 6}, {"x": 65, "y": 31, "w": 10, "h": 6}],
                [],
            ],
        },
    )

    sizes = out["sizes"]
    assert sizes[0] == pytest.approx(7 * upp)
    assert sizes[1] is None and sizes[3] is None and sizes[4] is None
    assert sizes[2] == pytest.approx(min(12 * upp, 12 * 0.92 / 3.9))
    # 위 끝(60)에 닿은 범위의 「위」 — 바깥(60.2 + 0.8, 알약 위 끝 61.8)이 영역 밖이라
    # 안쪽 띠(60 - 0.2 - 0.8).
    assert out["spots"][0] == {"x": 20, "y": pytest.approx(59)}
    # 바닥(0)에 닿은 범위의 「아래」 — 안쪽 띠(0 + 0.2 + 0.8).
    assert out["spots"][1] == {"x": 20, "y": pytest.approx(1)}
    # 위에 자리가 있으면 바깥 그대로.
    assert out["spots"][2] == {"x": 20, "y": pytest.approx(61)}
    assert out["spots"][3] == {"x": 20, "y": pytest.approx(11)}
    assert out["shown"] == [{"x": 65, "y": 25, "w": 10, "h": 12}, None]


def test_the_group_name_follows_the_label_rule_and_the_shown_modules() -> None:
    """그리는 쪽 배선 — 모듈 칸 이름표 크기(`unitLabelSize`, 7px 아래 숨김)와 같은 기준으로
    bare 를 정하고, 보기 화면은 기준일에 보이는 모듈(`seenModule`)이 일부일 때 그 바깥 상자에
    세우며, 위·아래는 영역 높이 `H()` 를 넘겨 안쪽으로 뒤집을 수 있다."""
    draw = _between("function drawGroupNames() {", "const GUIDE_PX = ")
    assert "const seen = mods.filter(seenModule)" in draw
    assert "VIEW && seen.length < mods.filter(onCanvas).length ? shownRange(seen) : whole" in draw
    assert "unitLabelSize(m, upp) / upp >= UNIT_LABEL_MIN_PX" in draw
    assert "GROUP_NAME_PX, upp, UNIT_LABEL_MIN_PX, bare)" in draw
    assert "if (fs === null) continue" in draw
    assert "groupNameSpot(range, position, fs, 2 * upp, H())" in draw
    seen = _js_decl("const seenModule = ")
    assert "S.groups.get(m.id)?.__visible !== false" in seen


def test_zone_looks_and_group_names_are_wired_through_the_editor() -> None:
    """영역의 테두리 모양·이름표 정렬은 읽기(`readMark`)·바뀜 판정·적용값·복사·되돌리기 기록에 모두
    들고,
    고른 영역의 강조는 테두리 모양과 따로(`sle-zone-select`)다. Main 설비명은 맨 위 가까운 층
    (`sle-group-names`, 눌림 없음)에 그리고, 묶음마다 선택 칸에서 고르며 되돌리기 한 번이고 적용값
    `groupLabels` 로 간다. 보기 화면은 기준일에 묶음이 숨으면 이름도 숨긴다."""
    for start, end in (
        ("const readMark = (raw) => ({", "})"),
        ("const marksPayload = () => [", "...S.passthrough"),
        ("const clipOf = (m) => ({", "})"),
        ("const snapshot = (item) => ({", "})"),
    ):
        body = _between(start, end)
        assert "borderStyle" in body and "labelAlign" in body, start
    changed = _between("function isChanged(item) {", "function isRenamed(")
    assert "pickOr(o.borderStyle, BORDER_STYLES)" in changed
    assert "pickOr(o.labelAlign, LABEL_ALIGNS)" in changed
    zone = _between("if (item.kind === 'zone') {", "} else if (item.kind === 'shutter')")
    assert "'sle-zone-border is-solid'" in zone and "class: 'sle-zone-select'" in zone
    assert "zoneTagX(lw, tagW, item.labelAlign)" in zone
    assert ".sle-zone-border.is-solid { stroke-dasharray: none; }" in CSS
    assert ".mark-zone.is-selected .sle-zone-select { display: inline;" in CSS
    # 고르면 테두리 모양이 바뀌던 규칙은 없다(강조는 바깥 테로 따로).
    assert ".mark-zone.is-selected .sle-zone-border" not in CSS
    assert 'class="sle-mark-border"' in HTML and 'class="sle-mark-align"' in HTML
    assert HTML.index('<g class="sle-marks"></g>') < HTML.index('<g class="sle-group-names"></g>')
    assert HTML.index('<g class="sle-group-names"></g>') < HTML.index('<g class="sle-overlay"></g>')
    assert ".sle-group-names { pointer-events: none; }" in CSS
    assert 'class="sle-group-label-pos"' in HTML
    setter = _between("function setGroupLabel(key, value) {", "const groupShown = ")
    assert setter.count("pushUndo(") == 1 and "op: 'groupLabel'" in setter
    assert "} else if (op.op === 'groupLabel') {" in _between(
        "function undo() {", "function cancelDrag("
    )
    apply = _between("applyButton.onclick = () => {", "// ---")
    assert "groupLabels: FAB ? null : groupLabelsPayload()" in apply
    assert "groupLabelChangeCount()" in _between(
        "function updateStatus() {", "function commitTyping("
    )
    assert "drawGroupNames()" in _between(
        "function drawSelectionBox() {", "overlay.replaceChildren()"
    )
    assert "!VIEW || mods.some(" in JS


def test_the_component_sends_only_top_or_bottom_group_labels() -> None:
    """가운데(처음 값)와 모르는 값은 보내지 않는다 — 브라우저는 없는 묶음을 가운데로 그린다."""
    cleaned = space_layout_editor._clean_group_labels(
        {"G-1": "top", "G-2": "center", "G-3": "bottom", "G-4": "left"}
    )

    assert cleaned == {"G-1": "top", "G-3": "bottom"}
    assert space_layout_editor._clean_group_labels(None) == {}
