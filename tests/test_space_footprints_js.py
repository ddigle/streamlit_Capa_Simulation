# Purpose: Space 편집기 발자국의 경로 · 개수 · 선 꼴 판정을 node 로 돌려 파이썬 계약과 견준다.

"""2026-11-12 Space 시안 보드 6-1 ~ 6-6 — 발자국(`footprints`).

순수 판정은 `editor.js` 의 `// <foot-geometry>`(모양 표 · 개수 · 경로 · 끝 손잡이 · 띠 맞춤)와
`// <mark-look>`(모양 값 정규화)이고 node 로 떼어 돌린다(node · bun 이 없으면 건너뛰고 CI
에서는 실패 — `test_space_module_group._node`). 띠 · 가장 짧은 길이 · 모양 키는 파이썬
`floor_layout_mark` 와 대조한다. 그리기 · 선택 칸 배선은 자산 글자로 붙잡고 실제 모습은
브라우저로 본다.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from test_space_format_paint_js import _APPLY_DECLS
from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor
from capa_simulation.services.floor_layout_mark import (
    FOOT_BAND,
    FOOT_GAPS,
    FOOT_MIN_LENGTH,
    FOOT_SHAPE_NAMES,
    FOOT_SHAPES,
    mark_look,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_FOOT = re.compile(r"// <foot-geometry>\n(?P<body>.*?)\n\s*// </foot-geometry>", re.S)
_LOOK = re.compile(r"// <mark-look>\n(?P<body>.*?)\n\s*// </mark-look>", re.S)
_PAINT = re.compile(r"// <format-paint>\n(?P<body>.*?)\n\s*// </format-paint>", re.S)
_TILING = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)
LENGTHS: list[float] = [3, 3.5, 4.8, 5.1, 7.3, 10, 16, 23, 30, 31.7]

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
%s
const list = (key) => input[key] || []
const out = {
  constants: { FOOT_BAND, FOOT_MIN_LENGTH, FOOT_STRIDE, FOOT_ROWS, FOOT_BIRD_STROKE },
  shapes: Object.fromEntries(Object.entries(FOOT_SHAPES).map(([key, spec]) => [key, spec.name])),
  lookKeys: { FOOT_SHAPE_KEYS, FOOT_GAP_KEYS },
}
out.counts = list('counts').map(([length, gap]) => footCount(length, gap))
out.paths = list('paths').map(([lw, foot, gap]) => footprintsShape(lw, foot, gap))
out.feet = list('feet').map(([foot, cx, cy, left]) => footParts(foot, cx, cy, left))
out.ends = list('ends').map((rot) => footLineEnds(rot))
out.fitted = list('fitted').map(([rot, w, h]) => footFitted(rot, w, h))
out.looks = list('looks').map((look) => lookText(cleanLook(look, 'footprints')))
process.stdout.write(JSON.stringify(out))
"""


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    return _node(_RUNNER % (_block(_LOOK), _block(_FOOT)), payload)


def _between(start: str, end: str) -> str:
    begin = JS.index(start)
    return JS[begin : JS.index(end, begin)]


_TOKEN = re.compile(r"[MLCAZ]|-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _bounds(d: str, pad: float = 0.0) -> tuple[float, float, float, float]:
    """절대 좌표 경로(M · L · C · A · Z)의 바깥 상자 — 곡선은 조절점까지(곡선은 조절점 볼록 껍질
    안에 든다), 반원 호는 두 끝의 가운데 ± 반지름. pad 는 선 굵기의 반."""
    tokens = _TOKEN.findall(d)
    xs: list[float] = []
    ys: list[float] = []
    here = (0.0, 0.0)
    i = 0
    while i < len(tokens):
        command = tokens[i]
        i += 1
        if command == "Z":
            continue
        if command in "ML":
            here = (float(tokens[i]), float(tokens[i + 1]))
            xs.append(here[0])
            ys.append(here[1])
            i += 2
        elif command == "C":
            values = [float(value) for value in tokens[i : i + 6]]
            xs += values[0::2]
            ys += values[1::2]
            here = (values[4], values[5])
            i += 6
        elif command == "A":
            rx, ry = float(tokens[i]), float(tokens[i + 1])
            end = (float(tokens[i + 5]), float(tokens[i + 6]))
            cx, cy = (here[0] + end[0]) / 2, (here[1] + end[1]) / 2
            xs += [cx - rx, cx + rx]
            ys += [cy - ry, cy + ry]
            here = end
            i += 7
        else:  # pragma: no cover - 경로 꼴이 바뀌면 여기서 멈춘다
            raise AssertionError(f"모르는 경로 명령: {command}")
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _subpaths(d: str) -> list[str]:
    return [f"M{piece.rstrip()}" for piece in d.split("M") if piece.strip()]


# ------------------------------------------------------------------------------- 파이썬 짝


def test_the_band_shapes_and_gaps_match_the_python_contract() -> None:
    out = _run({})

    assert out["constants"]["FOOT_BAND"] == FOOT_BAND
    assert out["constants"]["FOOT_MIN_LENGTH"] == FOOT_MIN_LENGTH
    assert out["constants"]["FOOT_STRIDE"] == {"narrow": 2.6, "normal": 3.5, "wide": 4.8}
    assert out["constants"]["FOOT_ROWS"] == [0.9, 2.1]
    assert tuple(out["shapes"]) == FOOT_SHAPES
    assert out["shapes"] == dict(FOOT_SHAPE_NAMES)
    assert tuple(out["constants"]["FOOT_STRIDE"]) == FOOT_GAPS
    assert tuple(out["lookKeys"]["FOOT_SHAPE_KEYS"]) == FOOT_SHAPES
    assert tuple(out["lookKeys"]["FOOT_GAP_KEYS"]) == FOOT_GAPS


@pytest.mark.parametrize(
    "look",
    [
        {},
        {"foot": "sole", "gap": "normal", "line": "accent", "flip": False},
        {"foot": "cat", "gap": "wide"},
        {"line": "rose", "flip": True},
        {"foot": "heel", "gap": "narrow", "line": "ink"},
    ],
)
def test_the_editor_look_is_the_python_canonical_text(look: dict[str, Any]) -> None:
    (text,) = _run({"looks": [look]})["looks"]
    assert text == mark_look({"look": look}, "footprints", "F1")


def test_the_editor_drops_keys_and_values_the_python_would_refuse() -> None:
    """편집기는 그릴 수 있는 것만 쥔다 — 모르는 모양 · 간격 · 도형 전용 선 · 머리 · 굵기는 뺀다."""
    looks = _run(
        {
            "looks": [
                {"foot": "dog", "gap": "huge"},
                {"line": "auto", "head": "LL", "lineWidth": 2, "lineStyle": "solid"},
                {"foot": "bird", "shape": "rect"},
            ]
        }
    )["looks"]
    assert looks == ["", "", '{"foot":"bird"}']


# ------------------------------------------------------------------------------- 개수 · 크기


def test_the_count_follows_length_and_gap_only() -> None:
    """개수 = max(1, ⌊길이 ÷ 걸음⌋) — 걸음 좁게 2.6 · 보통 3.5 · 넓게 4.8칸. 16칸(넣을 때)은 6 · 4 ·
    3, 30칸은 11 · 8 · 6(시안 보드 그림과 같다)."""
    pairs = [(length, gap) for length in (3, 10, 16, 30) for gap in FOOT_GAPS]
    counts = _run({"counts": pairs})["counts"]
    assert counts == [1, 1, 1, 3, 2, 2, 6, 4, 3, 11, 8, 6]
    paths = _run({"paths": [[16, foot, "normal"] for foot in FOOT_SHAPES]})["paths"]
    assert {path["count"] for path in paths} == {4}


@pytest.mark.parametrize("foot", FOOT_SHAPES)
def test_lengthening_keeps_the_first_feet_and_only_adds_at_the_end(foot: str) -> None:
    """발 크기는 길이 · 상자를 따르지 않는다 — 늘여도 앞 발들의 윤곽이 같고 새 발이 끝에 는다."""
    short, long = _run({"paths": [[10, foot, "normal"], [30, foot, "normal"]]})["paths"]
    key = "stroke" if foot == "bird" else "fill"
    first, more = _subpaths(short[key]), _subpaths(long[key])
    assert len(more) > len(first) > 0
    assert more[: len(first)] == first


def test_one_short_foot_stands_in_the_middle_and_the_left_foot_leads_on_the_top_row() -> None:
    (alone,) = _run({"paths": [[3, "dots", "wide"]]})["paths"]
    x0, y0, x1, y1 = _bounds(alone["fill"])
    assert alone["count"] == 1
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((1.5, 0.9))
    (two,) = _run({"paths": [[7, "dots", "normal"]]})["paths"]
    first, second = (_bounds(piece) for piece in _subpaths(two["fill"]))
    assert (first[1] + first[3]) / 2 == pytest.approx(0.9)
    assert (second[1] + second[3]) / 2 == pytest.approx(2.1)
    assert (first[0] + first[2]) / 2 == pytest.approx(1.75)
    assert (second[0] + second[2]) / 2 == pytest.approx(5.25)


def test_every_shape_gap_and_length_stays_inside_the_band_and_the_length() -> None:
    """모든 모양 × 간격 × 길이(3 ~ 31.7칸)에서 발이 띠 [0, 3] · 길이 [0, lw] 안에 든다 — 곡선은
    조절점까지, 새 발자국 선은 굵기의 반까지 넣어 본다(손으로 적은 점 자료를 지킨다)."""
    cases = [(length, foot, gap) for foot in FOOT_SHAPES for gap in FOOT_GAPS for length in LENGTHS]
    paths = _run({"paths": [list(case) for case in cases]})["paths"]
    stroke = float(_run({})["constants"]["FOOT_BIRD_STROKE"])
    for (length, foot, gap), path in zip(cases, paths, strict=True):
        assert path["fill"] or path["stroke"], (foot, gap, length)
        for d, pad in ((path["fill"], 0.0), (path["stroke"], stroke / 2)):
            if not d:
                continue
            x0, y0, x1, y1 = _bounds(d, pad)
            assert x0 >= -1e-9 and x1 <= length + 1e-9, (foot, gap, length, x0, x1)
            assert y0 >= -1e-9 and y1 <= FOOT_BAND + 1e-9, (foot, gap, length, y0, y1)


def test_the_six_shapes_draw_six_different_feet() -> None:
    feet = _run({"feet": [[foot, 1.1, 0.9, True] for foot in FOOT_SHAPES]})["feet"]
    drawn = ["|".join(part["fill"] + part["stroke"]) for part in feet]
    assert len(set(drawn)) == len(FOOT_SHAPES)
    by_shape = dict(zip(FOOT_SHAPES, feet, strict=True))
    # 구두는 앞창 + 굽 두 조각, 발가락 · 고양이는 발바닥 + 발가락, 새는 선 넷뿐이다.
    assert (len(by_shape["heel"]["fill"]), len(by_shape["toes"]["fill"])) == (2, 6)
    assert len(by_shape["cat"]["fill"]) == 5
    assert (by_shape["bird"]["fill"], len(by_shape["bird"]["stroke"])) == ([], 4)
    # 왼발과 오른발은 거울이다(바깥이 위 · 아래).
    (right,) = _run({"feet": [["sole", 1.1, 0.9, False]]})["feet"]
    assert right["fill"] != by_shape["sole"]["fill"]


# ------------------------------------------------------------------------------- 그리기 배선


def test_the_footprints_kind_is_a_rotatable_floor_and_fab_mark_after_the_arrow() -> None:
    entry = "footprints: { name: '발자국', size: [16, 3], label: '', rotatable: true },"
    assert entry in JS
    assert JS.index("arrow: { name: '동선'") < JS.index(entry) < JS.index("bay: { name: '베이'")
    # 범위 class 가 없어 층 · FAB 둘 다에 선다 — 동선 단추 바로 뒤.
    button = HTML[HTML.index('data-kind="footprints"') - 40 : HTML.index('data-kind="footprints"')]
    assert "sle-floor-only" not in button and "sle-fab-only" not in button
    assert HTML.index('data-kind="arrow"') < HTML.index('data-kind="footprints"')
    assert HTML.index('data-kind="footprints"') < HTML.index('data-kind="bay"')
    # 동선처럼 호기 위 층이다(영역 · 도형만 호기 아래).
    assert "const onZoneLayer = (item) => item.kind === 'zone' || item.kind === 'shape'" in JS


def test_draw_mark_fills_the_feet_with_the_line_colour_and_flips_before_turning() -> None:
    draw = _between("function drawMark(", "function appendHandles(")
    branch = draw[draw.index("} else if (item.kind === 'footprints') {") :]
    branch = branch[: branch.index("} else if (item.kind === 'bay') {")]
    assert (
        "footprintsShape(lw, lookValue(item.look, 'footprints', 'foot'), "
        "lookValue(item.look, 'footprints', 'gap'))"
    ) in branch
    assert "lineInk(lookValue(item.look, 'footprints', 'line'))" in branch
    assert "lines.style.strokeWidth = String(FOOT_BIRD_STROKE)" in branch
    # 동선 갈래 바로 뒤다.
    assert draw.index("} else if (item.kind === 'arrow') {") < draw.index(
        "} else if (item.kind === 'footprints') {"
    )
    assert (
        "|| (item.kind === 'footprints' && lookValue(item.look, 'footprints', 'flip') === true)"
        in draw
    )
    # 이름표는 동선과 같은 자리(옆 가로 글)다.
    assert "const lineLike = item.kind === 'arrow' || item.kind === 'footprints'" in draw
    assert ".sle-foot { fill: var(--sle-accent); }" in CSS
    assert "isFootprints(m))" in _between("const canFlip = ", "function flipMarks(")


# ------------------------------------------------------------------------------- 선 꼴 편집


def test_only_the_two_ends_on_the_walking_axis_are_handles() -> None:
    out = _run({"ends": [0, 90, 180, 270, -90, None]})
    assert out["ends"] == [["e", "w"], ["n", "s"], ["e", "w"], ["n", "s"], ["n", "s"], ["e", "w"]]


def test_the_box_keeps_the_band_and_the_shortest_length() -> None:
    fitted = _run(
        {
            "fitted": [
                [0, 16, 3],
                [0, 16, 10],
                [0, 2, 3],
                [90, 10, 20],
                [180, 1, 1],
                [270, 3, 2.5],
            ]
        }
    )["fitted"]
    assert fitted == [
        {"w": 16, "h": 3},
        {"w": 16, "h": 3},
        {"w": 3, "h": 3},
        {"w": 3, "h": 20},
        {"w": 3, "h": 3},
        {"w": 3, "h": 3},
    ]


# 크기를 바꾸는 길 — editor.js 선언을 글자 그대로 떼어 돌린다(서식 붙이기 둘레와 같은 선언 +
# 손잡이 끌기). 돌리기는 편집기 `rotateMark` 의 상자 맞바꿈 뒤 `fit` 이다.
_FIT_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const W = () => 100
const H = () => 60
const roundTo = (v) => Math.round(v * SCALE) / SCALE
const floorTo = (v) => Math.floor(v * SCALE + 1e-9) / SCALE
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi))
const minSize = () => 1 / SCALE
const window = { localStorage: { getItem: () => null, setItem: () => {} } }
const S = { items: new Map(), ghosts: new Map(), original: new Map(), flash: '', formatParts: null }
const stack = []
const pushUndo = (ops) => { if (ops.length) { S.flash = ''; stack.push(ops) } }
const redraw = () => {}
%s
%s
const make = (m) => {
  const item = {
    placed: true, moveTo: null, sizeGuessed: false, rot: 0, label: '', color: '', hatch: false,
    keepOut: false, link: '', fontSize: null, fontColor: '', borderStyle: 'dashed',
    labelAlign: 'left', look: {}, group: null, kind: 'footprints', x: 10, y: 10, w: 16, h: 3, ...m,
  }
  S.items.set(item.id, item)
  S.original.set(item.id, snapshot(item))
  return item
}
const box = (m) => [m.rot, m.x, m.y, m.w, m.h]
const out = {}
out.sizes = (input.sizes || []).map(([raw, patch]) => {
  const item = make(raw)
  const { entries } = sizeEntries([item], (m) => (typeof patch === 'string'
    ? { w: m.w + (patch === 'right' ? 0.5 : 0), h: m.h + (patch === 'up' ? 0.5 : 0) } : patch))
  return [...box(item), entries.length]
})
out.turns = (input.turns || []).map((raw) => {
  const item = make(raw)
  const cx = item.x + item.w / 2
  const cy = item.y + item.h / 2
  const rot = ((item.rot || 0) + 90) %% 360
  Object.assign(item, { rot, w: item.h, h: item.w, x: cx - item.h / 2, y: cy - item.w / 2 })
  fit(item)
  return box(item)
})
out.drags = (input.drags || []).map(([raw, dir, dx, dTop]) => {
  const item = make(raw)
  resizeTo(item, snapshot(item), dir, dx, dTop)
  return box(item)
})
out.formats = (input.formats || []).map(([source, target]) => {
  S.items = new Map()
  const from = make(source)
  const to = make(target)
  applyFormat([to], { fmt: formatOf(formatShell(from)), origin: '' })
  return [...box(to), lookText(to.look)]
})
process.stdout.write(JSON.stringify(out))
"""


def _run_fit(payload: dict[str, Any]) -> dict[str, Any]:
    blocks = "\n".join(_block(pattern) for pattern in (_LOOK, _PAINT, _TILING, _FOOT))
    heads = (*_APPLY_DECLS, "function resizedBox(", "function resizeTo(")
    decls = "\n".join(_js_decl(head) for head in heads)
    return _node(_FIT_RUNNER % (blocks, decls), payload)


def test_every_size_path_keeps_the_band_and_only_changes_the_length() -> None:
    """숫자 칸 · Ctrl+방향키는 `sizeEntries` → `fit` 을 지난다 — 띠 쪽 값(0° 의 높이 칸 · Ctrl+↑)은
    바뀐 것이 없어 되돌리기 기록도 늘지 않고, 길이 쪽은 3칸 아래로 줄지 않는다."""
    turned = {"id": "F", "rot": 90, "w": 3, "h": 16}
    sizes = _run_fit(
        {
            "sizes": [
                [{"id": "F"}, {"h": 10}],
                [{"id": "F"}, {"w": 20}],
                [{"id": "F"}, {"w": 2}],
                [{"id": "F"}, "up"],
                [{"id": "F"}, "right"],
                [turned, {"w": 10}],
                [turned, {"h": 25}],
                [turned, "right"],
                [turned, "up"],
            ]
        }
    )["sizes"]
    assert sizes == [
        [0, 10, 10, 16, 3, 0],
        [0, 10, 10, 20, 3, 1],
        [0, 10, 10, 3, 3, 1],
        [0, 10, 10, 16, 3, 0],
        [0, 10, 10, 16.5, 3, 1],
        [90, 10, 10, 3, 16, 0],
        [90, 10, 10, 3, 25, 1],
        [90, 10, 10, 3, 16, 0],
        [90, 10, 10, 3, 16.5, 1],
    ]


def test_turning_moves_the_band_and_the_end_handles_never_shorten_below_three() -> None:
    out = _run_fit(
        {
            "turns": [{"id": "F", "x": 20, "y": 20}],
            "drags": [
                [{"id": "F"}, "e", 9, 0],
                [{"id": "F"}, "e", -20, 0],
                [{"id": "F"}, "w", 14, 0],
                [{"id": "F", "rot": 90, "w": 3, "h": 16}, "n", 0, -5],
                [{"id": "F", "rot": 90, "w": 3, "h": 16}, "s", 0, -20],
            ],
        }
    )
    # 16 × 3 을 돌리면 3 × 16 — 가운데 그대로, 띠가 따라간다.
    assert out["turns"] == [[90, 26.5, 13.5, 3, 16]]
    assert out["drags"] == [
        [0, 10, 10, 25, 3],
        [0, 10, 10, 3, 3],
        [0, 23, 10, 3, 3],
        [90, 10, 10, 3, 21],
        [90, 10, 23, 3, 3],
    ]


def test_the_format_brush_moves_length_line_colour_and_gap_but_not_the_shape() -> None:
    """발자국끼리는 길이 · 선 색 · 간격을 옮기고 발 모양 · 뒤집기는 옮기지 않는다. 동선 ↔ 발자국은
    선 색만 오간다(동선의 굵기 · 선 모양 · 머리는 그대로)."""
    source = {
        "id": "S",
        "w": 24,
        "look": {"foot": "cat", "gap": "wide", "line": "rose", "flip": True},
    }
    arrow = {
        "id": "A",
        "kind": "arrow",
        "look": {"line": "ink", "lineWidth": 3, "lineStyle": "solid", "head": "LL"},
    }
    formats = _run_fit(
        {
            "formats": [
                [source, {"id": "T", "rot": 90, "w": 3, "h": 16, "look": {"foot": "bird"}}],
                [arrow, {"id": "T", "look": {"gap": "narrow"}}],
                [source, {**arrow, "id": "T"}],
            ]
        }
    )["formats"]
    assert formats == [
        [90, 10, 10, 3, 24, '{"foot":"bird","gap":"wide","line":"rose"}'],
        [0, 10, 10, 16, 3, '{"gap":"narrow","line":"ink"}'],
        [0, 10, 10, 16, 3, '{"head":"LL","line":"rose","lineStyle":"solid","lineWidth":3}'],
    ]


def test_the_editor_wires_line_editing_and_the_inspector() -> None:
    handles = _between("function positionHandles(", "function position(")
    assert "const ends = item.kind === 'footprints' ? footLineEnds(item.rot) : null" in handles
    assert "handle.style.display = ends.includes(dir) ? '' : 'none'" in handles
    assert "handle.setAttribute('rx', hs / 2)" in handles
    fit = _between("const fit = (item) => {", "const clampShift = ")
    assert (
        "if (item.kind === 'footprints') Object.assign(item, footFitted(item.rot, item.w, item.h))"
        in fit
    )
    assert "fit(item)" in _between("function pasteMarks(", "\n  }\n")
    inspector = _between("  function syncInspector() {", "  function syncLineProps(")
    assert inspector.index("syncShapeProps(chosen)") < inspector.index("footSyncProps(chosen, ")
    title = _between("const markTitle = ", "// 두 옆 칸")
    assert "lookValue(item.look, 'footprints', 'gap'))}개`" in title
    lines = _between("  function syncLineProps(", "  function setLooks(")
    assert "const headed = lined.filter((m) => m.kind !== 'footprints')" in lines
    assert "sharedLook(headed, 'lineWidth')" in lines and "sharedLook(lined, 'line')" in lines
    # 선택 칸 — 선 칸 바로 아래 발 모양 그림 판 · 간격(고르면 그 값, 다르면 「여러 값」).
    for selector in (
        'class="sle-footprops"',
        'class="sle-foot-toggle"',
        'class="sle-foot-gallery"',
        'class="sle-foot-gap"',
    ):
        assert selector in HTML, selector
    assert HTML.index('class="sle-lineprops"') < HTML.index('class="sle-footprops"')
    assert HTML.index('class="sle-footprops"') < HTML.index('class="sle-shapeprops"')
    assert "setLooks({ foot: cell.dataset.foot })" in JS
    assert "setLooks({ gap: footGap.value })" in JS
    # 고른 발자국은 점선 상자 대신 가운데 축 점선이다.
    assert ".mark-footprints.is-selected .sle-foot-axis { display: inline; }" in CSS
    assert ".sle-lineprops > .sle-field[hidden], .sle-fields .sle-field[hidden]" in CSS
