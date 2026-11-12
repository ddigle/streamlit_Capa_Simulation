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
from test_space_module_group import _node

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
LENGTHS = [3, 3.5, 4.8, 5.1, 7.3, 10, 16, 23, 30, 31.7]

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
    cases = [[length, foot, gap] for foot in FOOT_SHAPES for gap in FOOT_GAPS for length in LENGTHS]
    paths = _run({"paths": cases})["paths"]
    stroke = _run({})["constants"]["FOOT_BIRD_STROKE"]
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
