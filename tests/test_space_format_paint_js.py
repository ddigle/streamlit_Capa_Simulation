# Purpose: Space 편집기 서식 복사·붙여넣기(엑셀 서식 붓)의 종류별 붙는 칸·한 번 되돌리기·키 차례를
# node 로 검사한다.

"""2026-11-03 사용자 요청 — 레이아웃 편집기에서 크기·색 같은 서식을 복사해 붙여넣는 키(엑셀처럼).

순수 판정은 `editor.js` 의 `// <format-paint>`
구획(`formatOf`·`formatPatch`·`patchedLook`·`formatFrom`)이고 `// <mark-look>` 과 함께 node 로 떼어
돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 — `test_space_module_group._node`). 종류 × 종류 ×
붙일 것 체크의 모든 쌍을 사양 5-1 표를 옮긴 파이썬 모형과 견주고, 붙인 뒤의 요소가 파이썬
검증(`prepare_floor_layout_marks`·`prepare_fab_layout_marks`)을 지나는지 본다. 붙이기 한 번이
되돌리기 한 번인지는 실제 함수 `applyFormat`·`sizeEntries`(모듈 묶음은 바둑판 순수 함수까지)를 떼어
돌린다. 키 갈래 차례·붓·저장소는 자산 글자로 붙잡고 실제 모습은 브라우저로 본다.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

import pytest
from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor
from capa_simulation.services.fab_layout import FAB_MARK_KINDS, prepare_fab_layout_marks
from capa_simulation.services.floor_layout_mark import (
    LINE_COLOR_KEYS,
    LINE_WIDTHS,
    MARK_COLOR_KEYS,
    MARK_KINDS,
    SHAPE_FILL_KEYS,
    SHAPE_LINE_KEYS,
    ZONE_BORDER_STYLES,
    ZONE_LABEL_ALIGNS,
    prepare_floor_layout_marks,
)

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_LOOK = re.compile(r"// <mark-look>\n(?P<body>.*?)\n\s*// </mark-look>", re.S)
_PAINT = re.compile(r"// <format-paint>\n(?P<body>.*?)\n\s*// </format-paint>", re.S)
_TILING = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)
_CANVAS = (400.0, 400.0)
_PARTS: dict[str, dict[str, bool]] = {
    "all": {"size": True, "paint": True, "text": True},
    "size": {"size": True, "paint": False, "text": False},
    "paint": {"size": False, "paint": True, "text": False},
    "text": {"size": False, "paint": False, "text": True},
    "none": {"size": False, "paint": False, "text": False},
}


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


_PURE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const out = {}
out.lists = { FORMAT_PARTS, FORMAT_COLORS, FORMAT_BORDERS, FORMAT_ALIGNS }
out.patches = (input.pairs || []).map(([source, target, parts]) => {
  const patch = formatPatch(target, formatOf(source), parts)
  if (!patch) return null
  const look = patchedLook(target.look, patch.look, target.kind)
  const result = { ...target, ...patch.fields, ...(patch.size || {}), look }
  return { size: patch.size, fields: patch.fields, look: patch.look, result }
})
out.froms = (input.froms || []).map(([raw, sizes]) => formatFrom(raw, sizes))
process.stdout.write(JSON.stringify(out))
"""


def _run_pure(payload: dict[str, Any]) -> dict[str, Any]:
    return _node(_PURE_RUNNER % (_block(_LOOK) + "\n" + _block(_PAINT)), payload)


def _mark(kind: str, **values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"M-{kind}",
        "kind": kind,
        "x": 10,
        "y": 10,
        "w": 8,
        "h": 4,
        "rot": 0,
        "label": "",
        "color": "",
        "hatch": False,
        "keepOut": False,
        "link": "",
        "fontSize": None,
        "fontColor": "",
        "borderStyle": "dashed",
        "labelAlign": "left",
        "look": {},
    }
    base.update(values)
    return base


# 붙이는 쪽 — 모든 칸을 처음 값이 아닌 값으로 채운다(그대로 옮겨졌는지 보이게).
_SOURCES: dict[str, dict[str, Any]] = {
    "unit": {"kind": "unit", "module": False, "w": 12, "h": 7},
    "module": {"kind": "unit", "module": True, "w": 24, "h": 14},
    "zone": _mark(
        "zone",
        w=20,
        h=12,
        color="green",
        hatch=True,
        keepOut=True,
        borderStyle="solid",
        labelAlign="right",
        label="창고",
        fontSize=13,
        fontColor="rose",
    ),
    "shutter": _mark("shutter", w=12, h=5, rot=90, fontSize=16, fontColor="sky", label="반입"),
    "door": _mark("door", w=4, h=4, fontSize=9),
    "column": _mark("column", w=1.5, h=1.5, fontColor="gray"),
    "text": _mark("text", w=14, h=3, fontSize=20, fontColor="violet", label="메모"),
    "arrow": _mark(
        "arrow",
        w=16,
        h=3,
        fontSize=11,
        look={"head": "LS", "line": "rose", "lineWidth": 3, "lineStyle": "dotted"},
    ),
    "bay": _mark(
        "bay",
        w=10,
        h=4,
        label="80",
        look={"head": "SL", "line": "green", "lineWidth": 4.5, "lineStyle": "dashed", "flip": True},
    ),
    "shape": _mark(
        "shape",
        w=9,
        h=6,
        rot=90,
        color="violet",
        hatch=True,
        fontSize=24,
        look={
            "shape": "lbox",
            "adj": [0.5, 0.6],
            "fillAlpha": 40,
            "line": "sky",
            "lineWidth": 2,
            "lineStyle": "dashed",
            "flip": True,
        },
    ),
    "block": _mark("block", w=16, h=6, color="sky", link="C1 1F", fontColor="blue"),
}
# 받는 쪽 — 붙는 쪽과 다른 값(돌린 것도 섞는다).
_TARGETS: dict[str, dict[str, Any]] = {
    "unit": {"kind": "unit", "module": False, "w": 5, "h": 5},
    "module": {"kind": "unit", "module": True, "w": 6, "h": 6},
    "zone": _mark("zone", id="T-zone", color="blue", label="대상"),
    "shutter": _mark("shutter", id="T-shutter"),
    "door": _mark("door", id="T-door", rot=90),
    "column": _mark("column", id="T-column", w=2, h=2),
    "text": _mark("text", id="T-text", label="글"),
    "arrow": _mark("arrow", id="T-arrow", rot=90, w=3, h=16),
    "bay": _mark("bay", id="T-bay", label="12", look={"flip": True}),
    "shape": _mark(
        "shape", id="T-shape", color="gray", look={"shape": "triangle", "adj": [0.2], "line": "ink"}
    ),
    "block": _mark("block", id="T-block", link="C2 2F", color=""),
}
_LINED = ("arrow", "bay", "shape")
_HEADED = ("arrow", "bay")
_HATCHED = ("zone", "shape")
_COLORS: dict[str, tuple[str, ...]] = {
    "zone": MARK_COLOR_KEYS,
    "shape": SHAPE_FILL_KEYS,
    "block": ("", *MARK_COLOR_KEYS),
}


def _turned(item: dict[str, Any]) -> bool:
    return item["kind"] != "unit" and int(item.get("rot") or 0) % 180 != 0


def _expected(
    source: dict[str, Any], target: dict[str, Any], parts: dict[str, bool]
) -> dict[str, Any]:
    """사양 5-1 표를 그대로 옮긴 모형 — 붙을 칸 이름(`size`·`fields.<칸>`·`look.<키>`) → 값."""
    out: dict[str, Any] = {}
    s_kind, t_kind = source["kind"], target["kind"]
    same = s_kind == t_kind and (s_kind != "unit" or source["module"] == target["module"])
    if parts["size"] and same:
        lw, lh = (source["h"], source["w"]) if _turned(source) else (source["w"], source["h"])
        out["size"] = (lh, lw) if _turned(target) else (lw, lh)
    if "unit" in (s_kind, t_kind):
        return out
    look = source.get("look") or {}
    if parts["paint"]:
        if s_kind in _COLORS and t_kind in _COLORS and source["color"] in _COLORS[t_kind]:
            out["fields.color"] = source["color"]
        if s_kind == t_kind == "shape":
            out["look.fillAlpha"] = look["fillAlpha"]
        style = source["borderStyle"] if s_kind == "zone" else look.get("lineStyle")
        if s_kind in _LINED and t_kind in _LINED:
            allowed = SHAPE_LINE_KEYS if t_kind == "shape" else LINE_COLOR_KEYS
            if look["line"] in allowed:
                out["look.line"] = look["line"]
            if look["lineWidth"] in LINE_WIDTHS:
                out["look.lineWidth"] = look["lineWidth"]
        if style is not None and t_kind in _LINED:
            out["look.lineStyle"] = style
        if style in ZONE_BORDER_STYLES and t_kind == "zone":
            out["fields.borderStyle"] = style
        if s_kind in _HEADED and t_kind in _HEADED:
            out["look.head"] = look["head"]
        if s_kind in _HATCHED and t_kind in _HATCHED:
            out["fields.hatch"] = source["hatch"]
    if parts["text"]:
        out["fields.fontSize"] = source["fontSize"]
        out["fields.fontColor"] = source["fontColor"]
        if s_kind == t_kind == "zone":
            out["fields.labelAlign"] = source["labelAlign"]
    return out


def _flat(patch: dict[str, Any] | None) -> dict[str, Any]:
    if patch is None:
        return {}
    out: dict[str, Any] = {}
    if patch["size"]:
        out["size"] = (patch["size"]["w"], patch["size"]["h"])
    out.update({f"fields.{key}": value for key, value in patch["fields"].items()})
    out.update({f"look.{key}": value for key, value in patch["look"].items()})
    return out


def test_the_format_constants_match_the_python_contract() -> None:
    out = _run_pure({})
    assert out["lists"]["FORMAT_PARTS"] == ["size", "paint", "text"]
    assert out["lists"]["FORMAT_COLORS"] == list(MARK_COLOR_KEYS)
    assert out["lists"]["FORMAT_BORDERS"] == list(ZONE_BORDER_STYLES)
    assert out["lists"]["FORMAT_ALIGNS"] == list(ZONE_LABEL_ALIGNS)


@pytest.mark.parametrize("parts", sorted(_PARTS))
def test_every_kind_pair_takes_only_the_fields_of_the_spec_table(parts: str) -> None:
    """종류 × 종류마다 붙는 칸이 사양 5-1 표와 같다 — 크기는 같은 종류끼리만(호기는 낱
    호기끼리·묶음끼리, 돌린 요소는 자기 방향으로), 호기에는 크기만, 자리·이름표 글·회전·뒤집기·도형
    꼴·모양 조절 값·설비 금지·연결 층은 어디로도 가지 않는다. 체크를 끈 묶음은 빠지고 다 끄면 붙을
    것이 없다(null)."""
    pairs = list(itertools.product(_SOURCES, _TARGETS))
    flags = _PARTS[parts]
    out = _run_pure(
        {"pairs": [[_SOURCES[s], _TARGETS[t], flags] for s, t in pairs]},
    )
    for (s, t), patch in zip(pairs, out["patches"], strict=True):
        expected = _expected(_SOURCES[s], _TARGETS[t], flags)
        assert _flat(patch) == expected, (s, t)
        if patch is None:
            assert not expected
            continue
        result = patch["result"]
        for kept in ("x", "y", "rot", "label", "keepOut", "link", "id"):
            assert result.get(kept) == _TARGETS[t].get(kept), (s, t, kept)
        target_look = _TARGETS[t].get("look") or {}
        for kept in ("shape", "adj", "flip"):
            assert result["look"].get(kept) == target_look.get(kept), (s, t, kept)


def _floor_raw(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "module"}


def test_pasted_marks_pass_the_server_validation_on_floors_and_the_fab() -> None:
    """붙인 뒤의 도면 요소는 층·FAB 검증을 그대로 지난다 — 받는 쪽에 없는 값(도형의 진하게 → 영역,
    동선의 강조색 → 도형, 점 → 영역 테두리)은 그 칸만 건너뛰어 저장이 거부되지 않는다."""
    sources = dict(_SOURCES)
    sources["shape-ink"] = {**_SOURCES["shape"], "color": "ink", "look": {"line": "none"}}
    sources["arrow-plain"] = _mark("arrow")
    pairs = [(s, t) for s in sources for t in _TARGETS if "unit" not in (sources[s]["kind"], t)]
    out = _run_pure({"pairs": [[sources[s], _TARGETS[t], _PARTS["all"]] for s, t in pairs]})
    floor: list[dict[str, Any]] = []
    fab: list[dict[str, Any]] = []
    for (s, t), patch in zip(pairs, out["patches"], strict=True):
        result = patch["result"] if patch else _TARGETS[t]
        raw = {**_floor_raw(result), "id": f"{s}-{t}"}
        if t in MARK_KINDS:
            floor.append(raw)
        if t in FAB_MARK_KINDS:
            fab.append(raw)
    assert len(prepare_floor_layout_marks(floor, _CANVAS)) == len(floor)
    assert len(prepare_fab_layout_marks(fab, _CANVAS)) == len(fab)


def test_values_the_receiver_lacks_are_skipped_and_the_target_keeps_its_own() -> None:
    """도형의 진하게·바탕 면은 영역·층 블록에 가지 않고 층 블록의 기본 면(빈 값)은 영역·도형에 가지
    않는다. 도형의 자동·없음 선은 동선·베이에, 동선의 강조색은 도형에 가지 않는다. 동선의 자동
    굵기는 동선에만 「자동」으로 가고(키를 지움) 베이·도형은 제 굵기 그대로다. 점 선은 영역 테두리에
    가지 않는다."""
    ink_shape = _mark("shape", color="ink", look={"line": "none", "lineStyle": "dotted"})
    plain_block = _mark("block", color="")
    plain_arrow = _mark("arrow")
    targets = [
        _TARGETS["zone"],
        _TARGETS["block"],
        _TARGETS["arrow"],
        _TARGETS["bay"],
        _TARGETS["shape"],
    ]
    pairs = [
        [source, target, _PARTS["paint"]]
        for source in (ink_shape, plain_block, plain_arrow)
        for target in targets
    ]
    patches = _run_pure({"pairs": pairs})["patches"]
    by = {
        (source["kind"] + ("-ink" if source is ink_shape else ""), target["kind"]): patch
        for (source, target, _), patch in zip(pairs, patches, strict=True)
    }
    zone_from_ink = by[("shape-ink", "zone")]
    assert zone_from_ink is None or "color" not in zone_from_ink["fields"]
    assert "borderStyle" not in (zone_from_ink or {"fields": {}})["fields"]
    assert "color" not in (by[("shape-ink", "block")] or {"fields": {}})["fields"]
    assert "line" not in by[("shape-ink", "arrow")]["look"]
    assert by[("shape-ink", "arrow")]["look"]["lineStyle"] == "dotted"
    assert "line" not in by[("shape-ink", "bay")]["look"]
    assert by[("shape-ink", "shape")]["fields"]["color"] == "ink"
    assert by[("shape-ink", "shape")]["result"]["look"]["line"] == "none"
    assert by[("block", "block")]["fields"]["color"] == ""
    assert by[("block", "zone")] is None and by[("block", "shape")] is None
    arrow_to_arrow = by[("arrow", "arrow")]
    assert (
        arrow_to_arrow["look"]["lineWidth"] is None
        and "lineWidth" not in arrow_to_arrow["result"]["look"]
    )
    assert arrow_to_arrow["look"]["line"] == "accent" and arrow_to_arrow["look"]["head"] == "MM"
    assert "line" not in by[("arrow", "shape")]["look"]
    assert by[("arrow", "shape")]["result"]["look"]["line"] == "ink"
    assert (
        "lineWidth" not in by[("arrow", "bay")]["look"]
        and "lineWidth" not in by[("arrow", "shape")]["look"]
    )
    assert by[("arrow", "zone")]["fields"] == {"borderStyle": "dashed"}


def test_stored_formats_are_read_back_only_in_shape() -> None:
    """sessionStorage 에서 읽은 서식은 꼴이 맞을 때만 쓴다 — 종류가 없으면 버리고, 크기는 양수만,
    모르는 칸은 떼고, 글자 크기는 고를 수 있는 것만, 글자 색은 색 키만 남긴다. 호기는 크기만
    남는다."""
    sizes = [9, 11, 13]
    froms = [
        [None, sizes],
        [{"kind": ""}, sizes],
        [
            {
                "kind": "zone",
                "size": {"w": -1, "h": 4},
                "paint": {"color": "blue", "evil": 1},
                "text": {"fontSize": 14, "fontColor": "x"},
            },
            sizes,
        ],
        [
            {
                "kind": "unit",
                "module": True,
                "size": {"w": 3, "h": 4},
                "paint": {"color": "blue"},
                "text": {"fontSize": 9},
            },
            sizes,
        ],
        [
            {"kind": "text", "text": {"fontSize": 11, "fontColor": "rose", "labelAlign": "center"}},
            sizes,
        ],
    ]
    out = _run_pure({"froms": froms})["froms"]
    assert out[0] is None and out[1] is None
    assert out[2] == {
        "kind": "zone",
        "module": False,
        "size": None,
        "paint": {"color": "blue"},
        "text": {},
    }
    assert out[3] == {
        "kind": "unit",
        "module": True,
        "size": {"w": 3, "h": 4},
        "paint": None,
        "text": None,
    }
    assert out[4]["text"] == {"fontSize": 11, "fontColor": "rose", "labelAlign": "center"}


# 붙이기 둘레 — editor.js 선언을 글자 그대로 떼어 돌린다(그리기·저장소만 빈 함수). 되돌리기는 편집기
# `undo` 의 'set' 갈래(`Object.assign(itemOf(op.id), op.before)`)와 같다.
_APPLY_DECLS = (
    "const isUnit = ",
    "const isMark = ",
    "const snapshot = ",
    "const sameGeometry = ",
    "const sameNumber = ",
    "const sameSize = ",
    "const onCanvas = ",
    "const members = ",
    "const itemOf = ",
    "const groupKeyOf = ",
    "const ghostsOf = ",
    "const placedMembers = ",
    "const bbox = ",
    "const fit = ",
    "const sameSpot = ",
    "const moduleMembers = ",
    "function fitRange(",
    "function groupRange(",
    "const slotView = ",
    "const groupSlots = ",
    "const setSpots = ",
    "function relayGroup(",
    "function sizeEntries(",
    "function formatShell(",
    "function formatParts(",
    "function applyFormat(",
)
_APPLY_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const W = () => 200
const H = () => 120
const roundTo = (v) => Math.round(v * SCALE) / SCALE
const floorTo = (v) => Math.floor(v * SCALE + 1e-9) / SCALE
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi))
const minSize = () => 1 / SCALE
const window = { localStorage: { getItem: () => null, setItem: () => {} } }
const S = { items: new Map(), ghosts: new Map(), original: new Map(), flash: '', formatParts: null }
const stack = []
const pushUndo = (ops) => { if (ops.length) { S.flash = ''; stack.push(ops) } }
const redrawn = []
const redraw = (list) => { redrawn.push(list.map((m) => m.id)) }
%s
%s
const add = (m) => {
  const item = {
    placed: true, moveTo: null, sizeGuessed: false, rot: 0, label: '', color: '', hatch: false,
    keepOut: false, link: '', fontSize: null, fontColor: '', borderStyle: 'dashed',
    labelAlign: 'left', look: {}, group: null, ...m,
  }
  S.items.set(item.id, item)
  S.original.set(item.id, snapshot(item))
}
for (const m of input.items) add(m)
const state = () => Object.fromEntries([...S.items.values()].map((m) => [m.id, {
  x: m.x, y: m.y, w: m.w, h: m.h, rot: m.rot, label: m.label, color: m.color, hatch: m.hatch,
  keepOut: m.keepOut, fontSize: m.fontSize, fontColor: m.fontColor, borderStyle: m.borderStyle,
  labelAlign: m.labelAlign, look: lookText(m.look),
}]))
const undo = () => {
  for (const op of [...stack.pop()].reverse()) Object.assign(itemOf(op.id), op.before)
}
const before = state()
const source = S.items.get(input.source)
const clip = { fmt: formatOf(formatShell(source)), origin: '' }
S.formatParts = input.parts || null
const count = applyFormat(input.targets.map((id) => S.items.get(id)), clip)
const after = state()
const undoCount = stack.length
const lastOps = stack.length ? stack[stack.length - 1].map((op) => op.id).sort() : []
const flash = S.flash
if (stack.length) undo()
const out = { count, before, after, undoCount, lastOps, flash, undone: state(), redrawn }
process.stdout.write(JSON.stringify(out))
"""


def _run_apply(**payload: Any) -> dict[str, Any]:
    blocks = "\n".join(_block(pattern) for pattern in (_LOOK, _PAINT, _TILING))
    decls = "\n".join(_js_decl(head) for head in _APPLY_DECLS)
    return _node(_APPLY_RUNNER % (blocks, decls), payload)


_APPLY_ITEMS: list[dict[str, Any]] = [
    {
        "id": "Z1",
        "kind": "zone",
        "x": 10,
        "y": 10,
        "w": 20,
        "h": 12,
        "color": "green",
        "hatch": True,
        "borderStyle": "solid",
        "labelAlign": "right",
        "label": "창고",
        "fontSize": 13,
        "fontColor": "rose",
    },
    {
        "id": "Z2",
        "kind": "zone",
        "x": 60,
        "y": 60,
        "w": 8,
        "h": 6,
        "color": "blue",
        "label": "통로",
    },
    {
        "id": "S1",
        "kind": "shape",
        "x": 100,
        "y": 20,
        "w": 8,
        "h": 6,
        "color": "gray",
        "look": {"shape": "lbox"},
    },
    {"id": "A1", "kind": "arrow", "x": 40, "y": 80, "w": 16, "h": 3},
    {"id": "T1", "kind": "text", "x": 5, "y": 100, "w": 14, "h": 3, "label": "메모"},
    {"id": "U1", "kind": "unit", "x": 150, "y": 50, "w": 12, "h": 7, "label": "DEMO-01"},
    {"id": "U2", "kind": "unit", "x": 150, "y": 70, "w": 6, "h": 5, "label": "DEMO-02"},
    {
        "id": "GA1",
        "kind": "unit",
        "x": 10,
        "y": 40,
        "w": 6,
        "h": 4,
        "label": "DEMO-GA1",
        "group": "DEMO-GA",
    },
    {
        "id": "GA2",
        "kind": "unit",
        "x": 16,
        "y": 40,
        "w": 6,
        "h": 4,
        "label": "DEMO-GA2",
        "group": "DEMO-GA",
    },
    {
        "id": "GB1",
        "kind": "unit",
        "x": 120,
        "y": 90,
        "w": 10,
        "h": 8,
        "label": "DEMO-GB1",
        "group": "DEMO-GB",
    },
    {
        "id": "GB2",
        "kind": "unit",
        "x": 130,
        "y": 90,
        "w": 10,
        "h": 8,
        "label": "DEMO-GB2",
        "group": "DEMO-GB",
    },
]


def test_one_paste_onto_many_kinds_is_one_undo_step_and_keeps_places_and_labels() -> None:
    """영역의 서식을 영역·도형·동선·글자·호기에 한 번에 붙이면 받는 쪽마다 맞는 칸만 바뀌고(호기는
    그대로), 바뀐 것 모두가 되돌리기 한 번에 든다. 자리·이름표 글은 그대로이고 되돌리면 처음과
    같다."""
    out = _run_apply(items=_APPLY_ITEMS, source="Z1", targets=["Z2", "S1", "A1", "T1", "U1"])
    before, after = out["before"], out["after"]
    assert out["count"] == 4 and out["undoCount"] == 1
    assert out["lastOps"] == ["A1", "S1", "T1", "Z2"]
    assert (
        out["flash"].startswith("서식을 4개에 붙였습니다")
        and "호기에는 같은 호기의 크기만" in out["flash"]
    )
    z2 = after["Z2"]
    assert (z2["w"], z2["h"], z2["color"], z2["hatch"], z2["borderStyle"], z2["labelAlign"]) == (
        20,
        12,
        "green",
        True,
        "solid",
        "right",
    )
    assert (z2["x"], z2["y"], z2["label"], z2["fontSize"], z2["fontColor"]) == (
        60,
        60,
        "통로",
        13,
        "rose",
    )
    s1 = after["S1"]
    assert (s1["w"], s1["h"], s1["color"], s1["hatch"], s1["fontSize"]) == (8, 6, "green", True, 13)
    assert s1["look"] == '{"shape":"lbox"}'
    assert after["A1"]["look"] == '{"lineStyle":"solid"}' and after["A1"]["fontColor"] == "rose"
    assert after["T1"]["fontSize"] == 13 and after["T1"]["label"] == "메모"
    assert after["U1"] == before["U1"]
    assert out["undone"] == before


def test_unit_sizes_go_only_to_the_same_kind_of_unit_and_module_groups_relay_as_a_range() -> None:
    """호기의 서식은 크기뿐이다 — 낱 호기는 낱 호기에, Main 설비 모듈 묶음은 묶음에(범위 크기, 안은
    바둑판으로 다시 섬). 묶음 모듈 모두가 한 기록에 들고 되돌리기 한 번에 돌아온다. 도면 요소에는
    붙지 않는다."""
    single = _run_apply(items=_APPLY_ITEMS, source="U1", targets=["U2", "GA1", "Z2"])
    assert single["count"] == 1 and single["lastOps"] == ["U2"]
    assert (single["after"]["U2"]["w"], single["after"]["U2"]["h"]) == (12, 7)
    assert single["after"]["GA1"] == single["before"]["GA1"]
    assert single["after"]["Z2"] == single["before"]["Z2"]
    assert single["undone"] == single["before"]

    grouped = _run_apply(items=_APPLY_ITEMS, source="GB1", targets=["GA2", "U2"])
    assert grouped["count"] == 1 and grouped["undoCount"] == 1
    assert grouped["lastOps"] == ["GA1", "GA2"]
    boxes = sorted(
        (
            grouped["after"][name]["x"],
            grouped["after"][name]["y"],
            grouped["after"][name]["w"],
            grouped["after"][name]["h"],
        )
        for name in ("GA1", "GA2")
    )
    assert boxes == [(10, 40, 10, 8), (20, 40, 10, 8)]
    assert grouped["after"]["U2"] == grouped["before"]["U2"]
    assert grouped["undone"] == grouped["before"]


def test_nothing_to_paste_says_why_and_records_nothing() -> None:
    """붙을 것이 없으면 기록이 없고 상태 줄이 까닭을 말한다 — 호기 → 요소, 체크를 다 끔, 이미 같은
    서식."""
    unit = _run_apply(items=_APPLY_ITEMS, source="U1", targets=["Z2", "S1"])
    assert (
        unit["count"] == 0
        and unit["undoCount"] == 0
        and unit["flash"] == "호기에는 같은 호기의 크기만 붙습니다"
    )
    off = _run_apply(items=_APPLY_ITEMS, source="Z1", targets=["Z2"], parts=_PARTS["none"])
    assert off["undoCount"] == 0 and "모두 꺼져 있습니다" in off["flash"]
    same = _run_apply(items=_APPLY_ITEMS, source="Z1", targets=["Z1"])
    assert same["undoCount"] == 0 and same["flash"] == "이미 같은 서식입니다"
    size_only = _run_apply(
        items=_APPLY_ITEMS, source="Z1", targets=["Z2", "S1"], parts=_PARTS["size"]
    )
    assert size_only["count"] == 1 and size_only["after"]["Z2"]["color"] == "blue"
    assert (size_only["after"]["Z2"]["w"], size_only["after"]["Z2"]["h"]) == (20, 12)


def test_format_keys_come_before_element_copy_and_leave_text_fields_alone() -> None:
    """Ctrl+Shift+C/V 는 서식 갈래로 가고 요소 복사(Ctrl+C/V)로 새지 않는다 — 서식 갈래가 먼저이고
    요소 복사는 Shift 가 없을 때만이다. 둘 다 글 칸 입력 중이면 비키고(글 칸의 Ctrl+Shift+V 는
    브라우저 것) 한글 자판에서도 글쇠 자리로 듣는다. Esc 는 든 붓을 먼저 내린다."""
    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    typing = keys.index("if (typing) return")
    fmt_copy = keys.index("if (formatKey && letter === 'c')")
    fmt_paste = keys.index("if (formatKey && letter === 'v')")
    copy = keys.index("if (ctrl && !event.shiftKey && letter === 'c')")
    paste = keys.index("if (ctrl && !event.shiftKey && letter === 'v')")
    assert typing < fmt_copy < fmt_paste < copy < paste
    assert "const formatKey = ctrl && event.shiftKey && !event.altKey" in keys
    assert "event.code === 'KeyC' ? 'c' : event.code === 'KeyV' ? 'v'" in keys
    assert "if (ctrl && letter === 'c')" not in keys and "if (ctrl && letter === 'v')" not in keys
    esc = keys.index(
        "if (event.key === 'Escape' && S.paint) { event.preventDefault(); setBrush(null); return }"
    )
    assert esc < typing and esc < keys.index("if (event.key === 'Escape' && S.selection.size)")
    assert "Ctrl+Shift+C/V 서식 복사·붙여넣기" in _between(
        "const HINT = FAB", "const q = (selector)"
    )


def test_the_brush_paints_on_press_and_by_rectangle_without_moving() -> None:
    """붓을 든 채 누르면 끌지 않고 그것(손잡이·묶음 범위 안 빈 칸도 그것)에 붙이고, 빈 곳을 끌면
    놓을 때 사각형 안 전부에 붙인다. 누르기만 한 빈 곳은 고른 것을 지킨다. 한 번 붓은 붙인 뒤 내리고
    잠금은 든 채다. 새 epoch 에 붓을 내린다. 두 번 누름은 잠금이다(엑셀)."""
    down = _between("svg.onpointerdown = (event) => {", "svg.onpointermove = (event) => {")
    brush = down.index("if (S.paint) {")
    assert down.index("S.spaceDown") < brush < down.index("const rangeDir =")
    assert "paintOnto([target])" in down[brush:] and "mode: 'marquee', paint: true" in down
    up = _between("svg.onpointerup = ", "svg.onlostpointercapture")
    assert (
        "if (drag.paint && drag.moved && S.selection.size) { paintOnto(selectedItems()); return }"
        in up
    )
    assert "S.selection = new Set(drag.before)" in up
    paint = _between("function paintOnto(targets) {", "function paintTargetAt(")
    assert (
        "if (!brush.sticky) S.paint = null" in paint and "applyFormat(targets, brush.clip)" in paint
    )
    target = _between("function paintTargetAt(", "function syncFormatPanel(")
    assert "node.dataset.for" in target and "pickedRangeAt(picked, p)" in target
    click = _between("paintButton.onclick = (event) => {", "paintPaste.onclick")
    assert "event.detail >= 2" in click and "sticky: true" in click and "sticky: false" in click
    epoch = _between("if (S.epoch !== data.epoch) {", "initFromData()")
    assert "S.paint = null" in epoch
    status = _between("function updateStatus() {", "function commitTyping() {")
    assert "if (S.paint) {" in status and "syncFormatPanel()" in status
    assert ".sle-canvas.is-painting" in CSS and "cursor: copy" in CSS


def test_the_format_clipboard_and_checks_live_in_browser_storage_only() -> None:
    """담은 서식은 sessionStorage(층·FAB 공용 한 칸) + 페이지 안 쪽지, 붙일 것 체크는 localStorage
    이고 읽기·쓰기는 모두 try 안이다. 파이썬으로 보내지 않는다(트리거 없음)."""
    assert "const FORMAT_CLIP_KEY = 'capa.space.formatClip.v1'" in JS
    assert "const FORMAT_PARTS_KEY = 'capa.space.formatPaint.v1'" in JS
    for start, end in (
        ("function formatParts() {", "function storeFormatParts() {"),
        ("function storeFormatParts() {", "function writeFormat(clip) {"),
        ("function writeFormat(clip) {", "function readFormat() {"),
        ("function readFormat() {", "S.formatClip = readFormat()"),
    ):
        assert "try {" in _between(start, end), start
    section = _between("const FORMAT_CLIP_KEY", "// 방향키·숫자 칸의 X·Y 는")
    assert "setTriggerValue" not in section and "setStateValue" not in section
    apply = _between("function applyFormat(targets, clip) {", "function pasteFormat() {")
    assert apply.count("pushUndo(") == 1 and "sizeEntries([item]" in apply
    sizes = _between("function setSizes(list, patchOf) {", "function sizeEntries(")
    assert "sizeEntries(list, patchOf)" in sizes and sizes.count("commit(") == 1


def test_the_left_panel_has_a_format_section_with_the_brush() -> None:
    """왼쪽 칸 「서식」 묶음(선택 다음) — 붓(aria-pressed · Ctrl+Shift+C), 붙이기(Ctrl+Shift+V),
    붙일 것 체크 셋(크기 · 색·선 · 글자 — 처음 켬), 담은 서식 한 줄. 편집에서만 선다."""
    start = HTML.index('data-sec="format"')
    assert HTML.index('data-sec="inspector"') < start < HTML.index('data-sec="grid"')
    section = HTML[HTML.rindex("<section", 0, start) : HTML.index("</section>", start)]
    assert 'class="sle-sec sle-edit-only"' in section
    assert 'class="sle-paint" aria-pressed="false" aria-keyshortcuts="Control+Shift+C"' in section
    assert 'class="sle-paint-paste" aria-keyshortcuts="Control+Shift+V"' in section
    parts = re.findall(r'class="sle-paint-part" type="checkbox" data-part="(\w+)" checked', section)
    assert parts == ["size", "paint", "text"]
    assert 'class="sle-paint-now" aria-live="polite"' in section
