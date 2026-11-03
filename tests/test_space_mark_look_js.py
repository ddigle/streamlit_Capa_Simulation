# Purpose: Space 편집기의 배율 글자 크기와 동선·베이 화살표 모양 판정을 node 로 검사한다.

"""2026-11-03 사용자 요청 셋 — U자 베이 화살표, 화살표 머리 크기(엑셀처럼), 배율에 따른 글자 크기.

순수 판정은 `editor.js` 의 `// <text-scale>`·`// <mark-look>` 구획이고 node 로 떼어 돌린다(node·bun
이 없으면 건너뛰고 CI 에서는 실패 — `test_space_module_group._node`). 모양 값 정규화는 파이썬
`floor_layout_mark.mark_look`·`bay_label` 과 대조한다. 그리기·선택 칸 배선은 자산 글자로 붙잡고 실제
모습은 브라우저로 본다.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.services.floor_layout_mark import (
    ARROW_HEADS,
    BAY_LABEL_MAX,
    LINE_COLOR_KEYS,
    LINE_STYLES,
    LINE_WIDTHS,
    LOOK_DEFAULTS,
    LOOK_KEYS,
    bay_label,
    mark_look,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_TEXT = re.compile(r"// <text-scale>\n(?P<body>.*?)\n\s*// </text-scale>", re.S)
_LOOK = re.compile(r"// <mark-look>\n(?P<body>.*?)\n\s*// </mark-look>", re.S)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
%s
const out = {}
const list = (key) => input[key] || []
out.scales = list('scales').map((ppu) => textScale(ppu))
out.callouts = list('callouts').map((s) => calloutScale(s))
out.texts = list('texts').map(([base, s]) => scaledText(base, s))
out.constants = { TEXT_REF_PPU, TEXT_SCALE_MAX, TEXT_MIN_PX, CALLOUT_SCALE }
out.lists = {
  LOOK_KEYS, LOOK_DEFAULTS, ARROW_HEADS, LINE_COLORS, LINE_WIDTHS, LINE_STYLES, BAY_NUMBER_MAX,
}
out.arrows = list('arrows').map(([lw, lh, head]) => arrowShape(lw, lh, head))
out.bays = list('bays').map(([lw, lh, head]) => bayShape(lw, lh, head))
out.places = list('places').map(([x, y, lw, lh, rot, flip]) => placeLocal(x, y, lw, lh, rot, flip))
out.autos = list('autos')
  .map(([lw, lh, head, rot, em]) => bayAutoSize(bayShape(lw, lh, head), rot, em))
out.looks = list('looks').map(([kind, look]) => lookText(cleanLook(look, kind)))
out.values = list('values').map(([kind, look, key]) => lookValue(look, kind, key) ?? null)
out.numbers = list('numbers').map((text) => bayNumber(text))
out.dashes = list('dashes').map(([style, w]) => lineDash(style, w))
process.stdout.write(JSON.stringify(out))
"""


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    return _node(_RUNNER % (_block(_TEXT), _block(_LOOK)), payload)


def _flat(points: list[list[float]]) -> list[float]:
    return [value for point in points for value in point]


# ------------------------------------------------------------------------------- 배율 글자


def test_the_text_scale_follows_screen_px_per_unit_up_to_twice() -> None:
    """s = ppu / 8, 위는 2배. 재지 못한 값은 1. 잰 화면(1500×950 C1 1F 전체 보기 ppu 5.4 — 샘플
    관측) 에서 이름표 11 은 7.4px 로 서고, FAB 전체 보기(9.3)는 1.16배다."""
    out = _run({"scales": [5.4, 8, 9.3, 16, 40, 0, -1, None]})

    assert out["constants"] == {
        "TEXT_REF_PPU": 8,
        "TEXT_SCALE_MAX": 2,
        "TEXT_MIN_PX": 6,
        "CALLOUT_SCALE": [0.75, 1.25],
    }
    assert out["scales"] == pytest.approx([0.675, 1, 1.1625, 2, 2, 1, 1, 1])
    assert 11 * out["scales"][0] == pytest.approx(7.425)


def test_text_below_six_px_hides_and_callouts_stay_within_their_band() -> None:
    out = _run(
        {
            "texts": [[11, 0.675], [9, 0.6], [9, 2 / 3], [24, 2], [11, 0.5]],
            "callouts": [0.3, 0.75, 1, 1.25, 2],
        }
    )

    assert [(round(text["px"], 3), text["shown"]) for text in out["texts"]] == [
        (7.425, True),
        (5.4, False),
        (6.0, True),
        (48.0, True),
        (5.5, False),
    ]
    assert out["callouts"] == [0.75, 0.75, 1, 1.25, 1.25]


# ------------------------------------------------------------------------------- 머리 크기


def test_the_lists_match_the_python_contract() -> None:
    lists = _run({})["lists"]

    assert {kind: tuple(keys) for kind, keys in lists["LOOK_KEYS"].items()} == LOOK_KEYS
    assert lists["LOOK_DEFAULTS"] == LOOK_DEFAULTS
    assert tuple(lists["ARROW_HEADS"]) == ARROW_HEADS
    assert tuple(lists["LINE_COLORS"]) == LINE_COLOR_KEYS
    assert tuple(lists["LINE_WIDTHS"]) == LINE_WIDTHS
    assert tuple(lists["LINE_STYLES"]) == LINE_STYLES
    assert lists["BAY_NUMBER_MAX"] == BAY_LABEL_MAX


@pytest.mark.parametrize(("lw", "lh"), [(16, 3), (4, 3), (40, 2), (3, 8)])
def test_the_medium_head_is_the_old_arrow_drawing(lw: float, lh: float) -> None:
    """옛 동선 그림: 머리 길이 min(lh × 1.1, lw × 0.35), 머리 y = lh × 0.15 … lh × 0.85, 몸통 lh ×
    0.3 → lw − 머리 × 0.9. 머리 크기 MM(처음 값)은 옛 데이터를 그대로 그린다."""
    (shape,) = _run({"arrows": [[lw, lh, "MM"]]})["arrows"]
    head = min(lh * 1.1, lw * 0.35)

    assert _flat(shape["head"]) == pytest.approx(
        [lw - head, lh * 0.15, lw, lh / 2, lw - head, lh * 0.85]
    )
    assert shape["shaft"] == pytest.approx(
        {"x1": lh * 0.3, "y1": lh / 2, "x2": lw - head * 0.9, "y2": lh / 2}
    )
    # 틀린 값은 MM 으로 그린다.
    (fallback,) = _run({"arrows": [[lw, lh, "ZZ"]]})["arrows"]
    assert fallback == shape


def test_nine_heads_grow_by_width_rows_and_length_columns_inside_the_box() -> None:
    arrows = _run({"arrows": [[16, 3, head] for head in ARROW_HEADS]})["arrows"]
    bays = _run({"bays": [[10, 4, head] for head in ARROW_HEADS]})["bays"]
    by_head = dict(zip(ARROW_HEADS, arrows, strict=True))
    bay_by_head = dict(zip(ARROW_HEADS, bays, strict=True))

    def width(points: list[list[float]]) -> float:
        return abs(points[2][1] - points[0][1])

    for size in "SML":
        widths = [width(by_head[f"{w}{size}"]["head"]) for w in "SML"]
        lengths = [by_head[f"{size}{length}"]["hl"] for length in "SML"]
        assert widths[0] < widths[1] < widths[2]
        assert lengths[0] < lengths[1] < lengths[2]
        bay_widths = [width(bay_by_head[f"{w}{size}"]["head"]) for w in "SML"]
        assert bay_widths[0] < bay_widths[1] < bay_widths[2]
    for shape in arrows:
        for x, y in shape["head"]:
            assert -1e-9 <= x <= 16 + 1e-9 and -1e-9 <= y <= 3 + 1e-9
    for shape in bays:
        for x, y in shape["head"]:
            assert -1e-9 <= x <= 10 + 1e-9 and -1e-9 <= y <= 4 + 1e-9


# ------------------------------------------------------------------------------- 베이


def test_the_default_bay_is_a_left_opening_u_with_its_head_at_the_lower_left() -> None:
    """10×4 베이: 팔 y = 1 · 3, 굽은 곳 반지름 1(오른쪽 끝 x = 10), 머리는 아래 팔 왼쪽 끝(0, 3)에서
    왼쪽, 머리 길이 min(1.1 × 2, 9 × 0.45) = 2.2, 너비 0.7 × 2 = 1.4. 글 자리는 머리를 비킨 틈
    가운데."""
    (bay,) = _run({"bays": [[10, 4, "MM"]]})["bays"]

    assert bay["d"] == "M 0 1 H 9 A 1 1 0 0 1 9 3 H 2.2"
    assert _flat(bay["head"]) == pytest.approx([2.2, 2.3, 0, 3, 2.2, 3.7])
    assert bay["text"] == pytest.approx({"x": 5.6, "y": 2})
    assert (bay["gapW"], bay["gapH"]) == pytest.approx((6.8, 2))


def test_a_narrow_bay_keeps_its_bend_inside_the_box() -> None:
    (bay,) = _run({"bays": [[1, 8, "LL"]]})["bays"]
    # 굽은 곳 반지름은 min(lh/4, lw/2) — 상자 밖으로 돌지 않는다. 머리 길이도 0 아래로 가지 않는다.
    assert bay["d"].startswith("M 0 2 H 0.5 A 0.5 2 0 0 1 0.5 6 H ")
    assert bay["hl"] >= 0


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_eight_directions_keep_the_head_and_text_inside_the_turned_box(
    rot: int, flip: bool
) -> None:
    """회전 넷 × 뒤집기 둘. 제자리(10×4)의 머리 세 점·글 자리를 뒤집기 → 돌림으로 옮기면 돌린 상자
    (90°·270° 는 4×10) 안이고, 머리 끝은 그 방향의 가장 바깥이다 — 0° 왼쪽, 뒤집으면 오른쪽, 돌리면
    그 뒤 방향."""
    (bay,) = _run({"bays": [[10, 4, "MM"]]})["bays"]
    points = [*bay["head"], [bay["text"]["x"], bay["text"]["y"]]]
    placed = _run({"places": [[x, y, 10, 4, rot, flip] for x, y in points]})["places"]
    half_w, half_h = (2, 5) if rot % 180 else (5, 2)

    for spot in placed:
        assert abs(spot["x"]) <= half_w + 1e-9 and abs(spot["y"]) <= half_h + 1e-9
    tip = placed[1]
    pointing = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[rot]
    if flip:
        pointing = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[rot]
    reach = tip["x"] * pointing[0] + tip["y"] * pointing[1]
    assert reach == pytest.approx(half_w if pointing[0] else half_h)


def test_the_auto_bay_text_fits_the_gap_as_the_screen_sees_it() -> None:
    """0°·180° 는 틈이 가로(높이 lh/2 × 0.75 · 폭 맞춤), 90°·270° 는 세로로 서서 틈 길이가
    높이다."""
    out = _run({"autos": [[10, 4, "MM", 0, 1.8], [10, 4, "MM", 90, 1.8], [10, 4, "MM", 180, 6]]})
    gap_w, gap_h = 6.8, 2

    assert out["autos"] == pytest.approx(
        [
            min(gap_h * 0.75, gap_w * 0.9 / 1.8),
            min(gap_w * 0.75, gap_h * 0.9 / 1.8),
            min(gap_h * 0.75, gap_w * 0.9 / 6),
        ]
    )


@pytest.mark.parametrize(
    "raw", ["80", "B80", "b 80", " B  12A ", "B", "", "BB1", "0123456789", "B0123456789", "가B"]
)
def test_bay_numbers_match_the_python_rule(raw: str) -> None:
    (number,) = _run({"numbers": [raw]})["numbers"]
    assert number == bay_label({"label": raw}, "B1")


def test_line_patterns_are_screen_px_multiples_of_the_width() -> None:
    out = _run({"dashes": [["solid", 2], ["dashed", 2], ["dotted", 1.5], ["weird", 3]]})
    assert out["dashes"] == ["", "6 4", "0.01 3", ""]


# ------------------------------------------------------------------------------- 모양 값


_VALID = [
    ("arrow", {}),
    ("arrow", {"head": "MM", "line": "accent", "lineStyle": "dashed"}),
    ("arrow", {"head": "LS"}),
    ("arrow", {"lineWidth": 2.0, "head": "SL"}),
    ("arrow", {"lineWidth": 0.75, "line": "ink", "lineStyle": "dotted"}),
    ("bay", {"lineWidth": 2, "flip": False, "line": "ink", "head": "MM", "lineStyle": "solid"}),
    ("bay", {"flip": True, "head": "LL"}),
    ("bay", {"line": "accent", "lineStyle": "dashed", "lineWidth": 6}),
    ("zone", {"head": "LL"}),
    ("text", {}),
]


@pytest.mark.parametrize(("kind", "look"), _VALID)
def test_a_clean_look_has_the_python_canonical_text(kind: str, look: dict[str, Any]) -> None:
    """편집기가 쥐고 보내는 정규 글(`lookText(cleanLook(…))`)이 파이썬 `mark_look` 과 같다 — 같은
    값이면 바뀜 판정·지문이 갈리지 않는다(숫자는 정수면 정수, 키 차례, 처음 값 빠짐)."""
    (text,) = _run({"looks": [[kind, json.loads(json.dumps(look))]]})["looks"]
    assert text == mark_look({"look": look}, kind, "M1")


def test_the_editor_drops_unknown_or_bad_values_the_server_would_refuse() -> None:
    """파이썬은 틀린 값을 거부하지만 편집기는 그릴 수 있는 것만 쥔다(모르는 키·틀린 값·다른 종류의
    키를 뺀다)."""
    out = _run(
        {
            "looks": [
                ["arrow", {"head": "XL", "flip": True, "lineWidth": 7, "line": "ink"}],
                ["bay", {"lineWidth": "2", "flip": "Y", "shape": "rect"}],
                ["arrow", None],
                ["arrow", [1, 2]],
            ],
            "values": [
                ["arrow", {}, "lineWidth"],
                ["arrow", {}, "line"],
                ["bay", {}, "lineWidth"],
                ["bay", {"flip": True}, "flip"],
                ["zone", {}, "head"],
            ],
        }
    )
    assert out["looks"] == ['{"line":"ink"}', "", "", ""]
    assert out["values"] == [None, "accent", 2, True, None]


# ------------------------------------------------------------------------------- 배선(자산 글자)


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


def test_the_look_travels_every_path_of_a_mark() -> None:
    """읽기(`readMark`)·처음 값 기록(`snapshot`)·바뀜 판정·적용값·복사·새 요소·되돌리기(set 기록이
    `snapshot` 을 쓴다)에 모두 든다. 모양 값은 갈아 끼우고 제자리에서 고치지 않는다."""
    assert "look: cleanLook(raw.look, String(raw.kind))," in _between(
        "const readMark = ", "function initFromData("
    )
    assert "...(String(raw.kind) === 'bay' ? { label: bayNumber(raw.label) } : {})," in JS
    assert "    look: item.look,\n  })" in _between("const snapshot = ", "const blockHead = ")
    assert "|| lookText(o.look) !== lookText(item.look)" in _between(
        "function isChanged(", "function isRenamed("
    )
    assert "look: cleanLook(m.look, m.kind)," in _between(
        "const marksPayload = ", "function moduleCaption("
    )
    assert "look: cleanLook(m.look, m.kind)," in _between(
        "const clipOf = ", "function writeClipboard("
    )
    add = _between(
        "function addMark(",
        "// ---------------------------------------------------------------- 도면 요소 복사",
    )
    assert "borderStyle: BORDER_STYLES[0], labelAlign: LABEL_ALIGNS[0], look: shape ? " in add
    assert "look: shape ? cleanLook({ shape }, 'shape') : {}," in add
    setter = _between("function setLooks(", "function flipMarks(")
    assert "m.look = next" in setter and "pushUndo(ops)" in setter
    assert "ops.push({ op: 'set', id: m.id, before: snapshot(m) })" in setter


def test_the_bay_is_floor_only_rotatable_and_drawn_from_the_pure_shape() -> None:
    assert "bay: { name: '베이', size: [10, 4], label: '', rotatable: true }," in JS
    assert "(kind !== 'bay' || !FAB)" in JS
    palette = HTML[HTML.index('data-kind="bay"') - 60 : HTML.index('data-kind="bay"')]
    assert 'class="sle-floor-only"' in palette
    draw = _between("function drawMark(", "function appendHandles(")
    assert "const geo = bayShape(lw, lh, lookValue(item.look, 'bay', 'head'))" in draw
    assert "const geo = arrowShape(lw, lh, lookValue(item.look, 'arrow', 'head'))" in draw
    # 뒤집기는 돌리기 앞(가운데 축 거울), 가운데 글은 돌리는 그룹 밖에 가로로 「B<번호>」.
    assert "rotate(${rot})${flip ? ' scale(-1 1)' : ''} translate(" in draw
    assert "const spot = placeLocal(geo.text.x, geo.text.y, lw, lh, rot, flip)" in draw
    # 자동 크기는 틈 맞춤이되 고를 수 있는 가장 큰 크기(24)의 배율 크기를 넘지 않는다.
    assert (
        "Math.min(bayAutoSize(geo, rot, emWidth(number)), Math.max(...FONT_SIZES) * ts * upp)"
        in draw
    )
    assert "const bayCaption = (item) => `B${item.label || ''}`" in JS
    assert "node.style.display = size / upp < TEXT_MIN_PX ? 'none' : ''" in draw
    assert ".sle-bay-line {" in CSS and "vector-effect: non-scaling-stroke" in CSS


def test_text_on_the_drawing_follows_the_scale_and_ui_marks_do_not() -> None:
    """이름표·글자 요소·층 블록 상한·호기 이름표 상한·Main 설비명·배지·견주기 꼬리표는 배율을
    따르고, 손잡이·초점 테·표식은 화면 px 그대로다."""
    draw = _between("function drawMark(", "function appendHandles(")
    assert "const ts = textScale(1 / upp)" in draw
    assert "if (caption.shown) {" in draw
    assert "if (item.label && caption.shown && (item.kind === 'shutter'" in draw
    assert "return Math.min(item.h * 0.32, fitFont, 14 * textScale(1 / upp) * upp)" in JS
    badges = _between("function drawShortBadges(", "function drawBadge(")
    assert "const k = calloutScale(ts)" in badges and "H(), k, ts)" in badges
    assert "settleBadges(drawn.map((entry) => entry.spot), upp, H(), k)" in badges
    compare = _between(
        "function drawCompare(",
        "// ---------------------------------------------------------------- 정렬선",
    )
    assert "COMPARE_TAG_PX * calloutScale(textScale(1 / upp)) * upp" in compare
    handles = _between("function positionHandles(", "function position(")
    assert "textScale" not in handles and "const hs = HANDLE_PX * unitsPerPx()" in handles


def test_the_inspector_offers_the_head_gallery_and_line_fields_for_arrows_and_bays() -> None:
    for selector in (
        'class="sle-lineprops"',
        'class="sle-head-toggle"',
        'class="sle-head-gallery"',
        'class="sle-line-color"',
        'class="sle-line-width"',
        'class="sle-line-style"',
        'data-flip="h"',
        'data-flip="v"',
        'class="sle-bay-prefix"',
    ):
        assert selector in HTML, selector
    gallery = _between("function fillLineOptions(", "const sharedLook = ")
    assert "button.setAttribute('aria-label', headAria(head))" in gallery
    head_aria = "const headAria = (head) => `너비 ${HEAD_WIDTH_WORDS[head[0]]} · 길이 "
    assert head_aria + "${HEAD_LENGTH_WORDS[head[1]]}`" in JS
    assert "const HEAD_WIDTH_WORDS = { S: '좁게', M: '보통', L: '넓게' }" in JS
    assert "const HEAD_LENGTH_WORDS = { S: '짧게', M: '보통', L: '길게' }" in JS
    flips = _between(
        "function flipMarks(",
        "// ---------------------------------------------------------------- 도형 서식",
    )
    assert "if (axis === 'v') m.rot = ((m.rot || 0) + 180) % 360" in flips
