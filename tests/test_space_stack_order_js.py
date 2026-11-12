# Purpose: Space 편집기 도면 요소의 그리는 차례(되돌리기 · 끌기 · 순서 단추)를 node 로 검사한다.

"""Space 편집기에서 겹 안 그리는 차례는 `S.items` 차례이고, 그것이 곧 도면 요소의 저장
차례(`floor_layout_mark.source_row_no` · `fab_layout_mark`)다(2026-11-12 Space 요청 7). 편집기
JS 의 선언을 글자 그대로 떼어 node 로 돌린다(node · bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`). 브라우저 조작 자체는 브라우저로 본다.
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _GHOST_DECLS, _js_decl, _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")

# 빼기 · 지우기와 되돌리기 둘레 — 선언은 editor.js 글자 그대로이고 그리기 · 선택만 빈 함수다.
_UNDO_DECLS = (
    *_GHOST_DECLS,
    "function setItemOrder(",
    "function restoreItem(",
    "function undo() {",
)
_UNDO_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const S = { items: new Map(), ghosts: new Map(), original: new Map(), undo: [], canvas: null }
const FLOOR = 'C1 1F'
const OTHER_FLOORS = []
const pushUndo = (ops) => { if (ops.length) S.undo.push({ kind: 'ops', ops }) }
const clearSelection = () => {}
const pruneSelection = () => {}
const renderItems = () => {}
const updateStatus = () => {}
const drawStatic = () => {}
%s
for (const [id, kind] of input.items) {
  const m = { id, kind, label: id, group: null, x: 0, y: 0, w: 4, h: 4, placed: true, moveTo: null }
  S.items.set(id, m)
  S.original.set(id, snapshot(m))
}
const out = []
for (const ids of input.removes) {
  removeItems(ids.map((id) => S.items.get(id)))
  out.push([...S.items.keys()])
}
for (const _ of input.removes) {
  undo()
  out.push([...S.items.keys()])
}
process.stdout.write(JSON.stringify(out))
"""


def _remove_and_undo(items: list[tuple[str, str]], removes: list[list[str]]) -> list[list[str]]:
    source = _UNDO_RUNNER % "\n".join(_js_decl(head) for head in _UNDO_DECLS)
    out: Any = _node(source, {"items": items, "removes": removes})
    return [list(step) for step in out]


_FLOOR_ITEMS = [
    ("Z-1", "zone"),
    ("EQ-01", "unit"),
    ("Z-2", "zone"),
    ("T-1", "text"),
    ("Z-3", "zone"),
    ("EQ-02", "unit"),
    ("T-2", "text"),
]


def test_an_undone_delete_puts_the_mark_back_in_its_own_place() -> None:
    """지운 도면 요소를 되돌리면 그 겹 맨 위(끝)가 아니라 지운 자리에 다시 선다 — 다른 요소
    고침과 함께 적용해도 저장 차례가 말없이 바뀌지 않는다(2026-11-12 order 조사에서 찾은 결함,
    PRC-01). 떨어진 둘을 한 번에 지워도, 지우기를 거듭해도 되돌리기마다 그 앞 차례 그대로다."""
    start = [item_id for item_id, _ in _FLOOR_ITEMS]
    out = _remove_and_undo(_FLOOR_ITEMS, [["Z-2", "T-2"], ["Z-1"]])
    assert out[0] == ["Z-1", "EQ-01", "T-1", "Z-3", "EQ-02"]
    assert out[1] == ["EQ-01", "T-1", "Z-3", "EQ-02"]
    assert out[2] == ["Z-1", "EQ-01", "T-1", "Z-3", "EQ-02"]
    assert out[3] == start


def test_a_delete_record_from_before_the_fix_still_restores_at_the_end() -> None:
    """자리를 모르는 기록(`at` 없음)은 끝에 붙는다 — 되돌리기는 끊기지 않는다."""
    body = _js_decl("function restoreItem(")
    source = (
        "const S = { items: new Map([['A', {}], ['B', {}]]) }\n"
        + _js_decl("function setItemOrder(")
        + body
        + "restoreItem({ id: 'C' }, undefined)\nrestoreItem({ id: 'D' }, 1)\n"
        + "process.stdout.write(JSON.stringify([...S.items.keys()]))\n"
    )
    out: Any = _node(source, {})
    assert out == ["A", "D", "B", "C"]


_RESTACK_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const parent = (name) => ({
  name, kids: [],
  append(node) { this.insertBefore(node, null) },
  insertBefore(node, ref) {
    this.kids = this.kids.filter((k) => k !== node)
    const at = ref ? this.kids.indexOf(ref) : this.kids.length
    this.kids.splice(at < 0 ? this.kids.length : at, 0, node)
    node.parentNode = this
  },
})
const layers = { zone: parent('zones'), unit: parent('items'), text: parent('marks') }
const isMark = (m) => m.kind !== 'unit'
const S = { items: new Map(), groups: new Map() }
for (const [id, kind] of input.items) {
  S.items.set(id, { id, kind })
  const group = { id, parentNode: null }
  layers[kind].append(group)
  S.groups.set(id, group)
}
%s
for (const id of input.pressed) S.groups.get(id).parentNode.append(S.groups.get(id))
const ids = () => Object.fromEntries(
  Object.entries(layers).map(([k, l]) => [k, l.kids.map((g) => g.id)]),
)
const pressed = ids()
restackMarks(input.pressed)
const after = ids()
process.stdout.write(JSON.stringify({ pressed, after }))
"""


def test_a_pressed_mark_goes_back_to_its_drawing_place_when_the_drag_ends() -> None:
    """누를 때 끌 준비로 제 겹 맨 위에 붙인 도면 요소는 손을 떼면(끌었든 눌러 고르기만 했든)
    제 차례 자리로 돌아간다 — 그리는 차례가 저장 차례와 같다. 호기는 그대로 둔다(호기끼리
    차례는 바꾸지 않는다). 여럿을 함께 끌어도 서로의 차례를 지킨다."""
    source = _RESTACK_RUNNER % _js_decl("function restackMarks(")
    out: Any = _node(source, {"items": _FLOOR_ITEMS, "pressed": ["Z-1", "Z-2", "EQ-01", "T-1"]})
    assert out["pressed"]["zone"] == ["Z-3", "Z-1", "Z-2"]
    assert out["after"] == {
        "zone": ["Z-1", "Z-2", "Z-3"],
        "unit": ["EQ-02", "EQ-01"],
        "text": ["T-1", "T-2"],
    }
    up = JS[JS.index("  svg.onpointerup = svg.onpointercancel = (event) => {") :]
    up = up[: up.index("svg.onlostpointercapture")]
    restack = up.index("restackMarks(drag.ids)")
    assert up.index("clearDragOverlap()") < restack < up.index("if (drag.toTray)")
    cancel = _js_decl("function cancelDrag(")
    assert "restackMarks([...drag.befores.keys()])" in cancel


_STACK = re.compile(r"// <stack-order>\n(?P<body>.*?)\n\s*// </stack-order>", re.S)


def _stack_body() -> str:
    match = _STACK.search(JS)
    assert match, "editor.js 에 // <stack-order> 구획이 없습니다"
    return match.group("body")


_MOVE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const out = input.cases.map(([entries, chosen, how]) => stackMove(entries, new Set(chosen), how))
process.stdout.write(JSON.stringify(out))
"""


def _box(item_id: str, tier: str, x: float, y: float, w: float = 4, h: float = 4) -> dict[str, Any]:
    return {"id": item_id, "tier": tier, "x": x, "y": y, "w": w, "h": h}


def _moves(cases: list[tuple[list[dict[str, Any]], list[str], str]]) -> list[Any]:
    out: Any = _node(_MOVE_RUNNER % _stack_body(), {"cases": [list(case) for case in cases]})
    return list(out)


def test_a_step_passes_the_nearest_overlapping_mark_in_that_direction() -> None:
    """「앞으로 · 뒤로」 한 걸음은 그 쪽에서 겹친 요소 하나를 넘는다(보드 7-3 B (가)) — 사이의
    겹치지 않은 요소는 함께 넘는다(목록 한 칸은 화면에 아무 변화가 없다). 그 쪽에 겹친 요소가
    없으면 끝이다(null — 단추 잠금 「이미 맨 앞 · 뒤입니다」)."""
    a = _box("A", "below", 0, 0)
    b = _box("B", "below", 50, 50)
    c = _box("C", "below", 2, 2)
    out = _moves(
        [
            ([a, b, c], ["A"], "fwd"),
            ([a, b, c], ["C"], "bwd"),
            ([a, b, c], ["C"], "fwd"),
            ([a, b, c], ["A"], "bwd"),
            ([a, b, c], ["B"], "fwd"),
            ([a, b, c], ["B"], "back"),
        ]
    )
    assert out == [["B", "C", "A"], ["C", "A", "B"], None, None, None, None]


def test_front_and_back_gather_the_chosen_at_that_end_only_when_something_covers_them() -> None:
    """맨 앞 · 맨 뒤는 고른 것을 그 끝으로 모으고 고른 것끼리의 차례는 지킨다. 그 쪽에서 겹친
    다른 요소가 없으면(이미 맨 앞 · 뒤로 보인다) 움직이지 않는다 — 보이지 않는 차례 바꿈으로
    「변경 1」 이 서지 않는다."""
    a = _box("A", "below", 0, 0)
    b = _box("B", "below", 1, 1)
    x = _box("X", "below", 2, 2)
    far = _box("F", "below", 90, 90)
    out = _moves(
        [
            ([a, b, x, far], ["A", "B"], "front"),
            ([x, a, b, far], ["A", "B"], "back"),
            ([a, far], ["A"], "front"),
            ([a, b, x], ["X"], "front"),
        ]
    )
    assert out == [["X", "F", "A", "B"], ["A", "B", "X", "F"], None, None]


def test_several_chosen_keep_their_order_and_do_not_jump_over_each_other() -> None:
    """여럿을 고르면 그 쪽 끝의 것부터 저마다 한 걸음이고, 다른 고른 것은 넘지 않는다."""
    a = _box("A", "below", 0, 0)
    x = _box("X", "below", 1, 1)
    b = _box("B", "below", 40, 40)
    y = _box("Y", "below", 41, 41)
    assert _moves([([a, x, b, y], ["A", "B"], "fwd")]) == [["X", "A", "Y", "B"]]
    # A 위에서 겹친 X 는 고른 B 너머라 한 걸음으로는 못 가고(null), 맨 앞으로는 간다.
    lone = _box("B", "below", 60, 60)
    out = _moves([([a, lone, x], ["A", "B"], "fwd"), ([a, lone, x], ["A", "B"], "front")])
    assert out == [None, ["X", "A", "B"]]


def test_each_mark_moves_only_inside_its_own_tier_and_units_stay() -> None:
    """겹은 서로 넘지 않는다 — 영역 · 도형(호기 아래)과 그 밖의 요소(호기 위)는 따로 움직이고,
    호기와 순서 밖(tier '')의 자리는 그대로다. 겹친 것이 다른 겹이면 넘을 것이 아니다."""
    z1 = _box("Z1", "below", 0, 0)
    unit = _box("EQ-01", "unit", 1, 1)
    t1 = _box("T1", "above", 1, 1)
    z2 = _box("Z2", "below", 2, 2)
    t2 = _box("T2", "above", 2, 2)
    off = _box("OFF", "", 2, 2)
    entries = [z1, unit, t1, off, z2, t2]
    out = _moves(
        [(entries, ["Z1", "T1"], "front"), (entries, ["Z1"], "fwd"), ([z1, unit], ["Z1"], "fwd")]
    )
    assert out == [
        ["Z2", "EQ-01", "T2", "OFF", "Z1", "T1"],
        ["Z2", "EQ-01", "T1", "OFF", "Z1", "T2"],
        None,
    ]


def test_every_mark_kind_has_a_tier_that_matches_its_drawing_layer() -> None:
    """종류 → 겹은 한 곳(`STACK_TIERS`)이고, 아래 겹은 그리는 층(`onZoneLayer` — 호기 아래)과 같다.
    도면 요소 종류를 더하고 겹을 빠뜨리면 여기서 실패한다(순서 줄이 서지 않는다)."""
    source = (
        _js_decl("const MARK_KINDS = {")
        + "\n"
        + _js_decl("const onZoneLayer = ")
        + "\n"
        + _stack_body()
        + "\nprocess.stdout.write(JSON.stringify(Object.keys(MARK_KINDS).map((kind) =>"
        + " [kind, tierOf({ kind }), onZoneLayer({ kind })])))\n"
    )
    rows: Any = _node(source, {})
    assert rows and all(tier in ("below", "above") for _, tier, _ in rows), rows
    assert all((tier == "below") == below for _, tier, below in rows), rows
    unit: Any = _node(
        _stack_body() + "\nprocess.stdout.write(JSON.stringify(tierOf({ kind: 'unit' })))", {}
    )
    assert unit == "unit"


def test_the_order_keys_read_the_key_position_with_ctrl_only() -> None:
    """Ctrl+Shift+] 맨 앞으로 · Ctrl+] 앞으로 · Ctrl+[ 뒤로 · Ctrl+Shift+[ 맨 뒤로 — 글쇠
    자리(code)라 자판과 상관없다. ⌘ 만(브라우저 앞 · 뒤) · Alt 와 함께 · IME 조합 중 · 다른
    글쇠는 아니다."""
    events = [
        {"ctrlKey": True, "code": "BracketRight", "key": "]"},
        {"ctrlKey": True, "shiftKey": True, "code": "BracketRight", "key": "}"},
        {"ctrlKey": True, "code": "BracketLeft", "key": "["},
        {"ctrlKey": True, "shiftKey": True, "code": "BracketLeft", "key": "{"},
        {"metaKey": True, "code": "BracketLeft", "key": "["},
        {"ctrlKey": True, "altKey": True, "code": "BracketRight", "key": "]"},
        {"ctrlKey": True, "isComposing": True, "code": "BracketRight", "key": "]"},
        {"ctrlKey": True, "code": "KeyA", "key": "a"},
    ]
    source = (
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))\n"
        + _stack_body()
        + "\nprocess.stdout.write(JSON.stringify(input.events.map(orderKeyOf)))\n"
    )
    out: Any = _node(source, {"events": events})
    assert out == ["fwd", "front", "bwd", "back", None, None, None, None]


_ORDER_DECLS = (
    "function markChangeCount(",
    "function markOrderChanged(",
    "function orderLockReason(",
    "function stackEntries(",
    "function stackChosen(",
    "function stackOrder(",
    "function syncOrder(",
    "function setItemOrder(",
    "function restoreItem(",
    "function undo() {",
)
_ORDER_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const data = input.data
const S = {
  items: new Map(), ghosts: new Map(), originalMarkIds: new Set(), undo: [], selection: new Set(),
}
const isUnit = (m) => m.kind === 'unit'
const isMark = (m) => m.kind !== 'unit'
const onCanvas = (m) => m.placed && !m.moveTo
const isChanged = () => false
const itemOf = (id) => S.items.get(id)
const selectedItems = () => [...S.selection].map((id) => S.items.get(id)).filter(Boolean)
const pushUndo = (ops) => { if (ops.length) S.undo.push({ kind: 'ops', ops }) }
const renderItems = () => {}
const updateStatus = () => {}
const pruneSelection = () => {}
const drawStatic = () => {}
const lockWith = (button, reason) => { button.reason = reason }
const orderRow = { hidden: true }
const orderButtons = ['front', 'fwd', 'bwd', 'back']
  .map((order) => ({ dataset: { order }, reason: null }))
%s
%s
for (const [id, kind, x, y, w, h] of input.items) {
  S.items.set(id, { id, kind, x, y, w, h, placed: true, moveTo: null })
  if (kind !== 'unit') S.originalMarkIds.add(id)
}
const look = (step) => {
  syncOrder()
  return {
    step, order: [...S.items.keys()], changes: markChangeCount(), undo: S.undo.length,
    row: !orderRow.hidden,
    locks: Object.fromEntries(
      orderButtons.map((b) => [b.dataset.order, orderRow.hidden ? null : b.reason]),
    ),
  }
}
const out = []
for (const [pick, act] of input.steps) {
  if (pick) S.selection = new Set(pick)
  if (act === 'undo') undo()
  else if (act) out.push(stackOrder(act))
  out.push(look(act || 'look'))
}
process.stdout.write(JSON.stringify(out))
"""
_ITEMS = [
    ("Z-1", "zone", 0, 0, 10, 10),
    ("EQ-01", "unit", 2, 2, 4, 4),
    ("Z-2", "zone", 5, 5, 10, 10),
    ("S-1", "shape", 30, 30, 5, 5),
    ("T-1", "text", 1, 1, 3, 3),
    ("Z-3", "zone", 8, 8, 4, 4),
]
_START = ["Z-1", "EQ-01", "Z-2", "S-1", "T-1", "Z-3"]
_FRONT = "이미 맨 앞입니다"
_BACK = "이미 맨 뒤입니다"


def _order_run(steps: list[Any], data: dict[str, Any] | None = None) -> list[Any]:
    decls = "\n".join(_js_decl(head) for head in _ORDER_DECLS)
    source = _ORDER_RUNNER % (_stack_body(), decls)
    out: Any = _node(source, {"items": _ITEMS, "steps": steps, "data": data or {}})
    return list(out)


def test_an_order_only_change_counts_as_one_and_undo_brings_it_back_to_zero() -> None:
    """차례만 바꿔도 「적용 안 한 변경 1건」 이고(층 하나에 한 건 — 적용이 새 차례의 요소 목록을
    보낸다), 단추 한 번이 되돌리기 한 번이다. 다 되돌리면 0 이다. 끝에 닿은 쪽 단추는 잠그고 풍선
    「이미 맨 앞입니다」 · 「이미 맨 뒤입니다」 다."""
    out = _order_run(
        [[["Z-1"], None], [None, "fwd"], [None, "front"], [None, "undo"], [None, "undo"]]
    )
    first, fwd_ok, fwd, front_ok, front, undo_one, undo_two = out
    assert first["order"] == _START and first["changes"] == 0 and first["row"] is True
    assert first["locks"] == {"front": "", "fwd": "", "bwd": _BACK, "back": _BACK}
    assert fwd_ok is True and fwd["order"] == ["Z-2", "EQ-01", "Z-1", "S-1", "T-1", "Z-3"]
    assert fwd["changes"] == 1 and fwd["undo"] == 1
    assert front_ok is True and front["order"] == ["Z-2", "EQ-01", "S-1", "Z-3", "T-1", "Z-1"]
    assert front["changes"] == 1 and front["undo"] == 2
    assert front["locks"] == {"front": _FRONT, "fwd": _FRONT, "bwd": "", "back": ""}
    assert undo_one["order"] == fwd["order"] and undo_one["changes"] == 1
    assert undo_two["order"] == _START and undo_two["changes"] == 0 and undo_two["undo"] == 0


def test_the_order_row_hides_for_units_only_and_locks_a_lone_mark_at_both_ends() -> None:
    """호기만 고르면 「순서」 줄이 없다(호기 순서는 이 판에 없는 기능 — UI-INP-07 숨김). 겹친
    것이 없는 요소는 이미 맨 앞이자 맨 뒤라 넷 다 잠긴다. 호기를 섞어 고르면 요소만 움직인다."""
    out = _order_run(
        [[["EQ-01"], None], [None, "front"], [["T-1"], None], [["EQ-01", "Z-1"], "front"]]
    )
    units, refused, units_after, lone, mixed_ok, mixed = out
    assert units["row"] is False and refused is False and units_after["order"] == _START
    assert lone["row"] is True
    assert lone["locks"] == {"front": _FRONT, "fwd": _FRONT, "bwd": _BACK, "back": _BACK}
    assert mixed_ok is True and mixed["order"] == ["Z-2", "EQ-01", "S-1", "Z-3", "T-1", "Z-1"]


def test_an_editor_that_does_not_change_the_order_locks_all_four_with_the_reason() -> None:
    """가정 설비 시나리오 편집기(`orderEditable` 거짓)는 단추 넷을 잠그고 받은 까닭을 풍선으로
    단다 — 단축키도 듣지 않는다(같은 `stackOrder` 길). 까닭이 비면 기본 글이다."""
    reason = "겹친 순서는 공식 설비 시나리오에서 바꿉니다"
    out = _order_run([[["Z-1"], "front"]], {"orderEditable": False, "orderLock": reason})
    refused, after = out
    assert refused is False and after["order"] == _START and after["changes"] == 0
    assert set(after["locks"].values()) == {reason}
    bare = _order_run([[["Z-1"], None]], {"orderEditable": False})[0]
    assert set(bare["locks"].values()) == {"이 편집기에서는 겹친 순서를 바꾸지 않습니다"}
    assert _order_run([[["Z-1"], None]], {"orderEditable": True})[0]["locks"]["front"] == ""


def test_the_order_row_sits_under_the_turns_row_and_rides_the_existing_apply() -> None:
    """「순서」 줄은 선택 칸 돌리기 · 뒤집기 줄 바로 밑에 둘씩 두 줄(맨 앞으로 · 앞으로 · 뒤로 · 맨
    뒤로)이고, 잠긴 단추의 풍선은 감싼 칸이 받는다. 숨김은 `[hidden]` 이 이긴다. 선택 칸을 다시 그릴
    때마다 맞춘다. 적용은 따로 갈래가 없다 — 차례가 바뀌면 요소 변경 수가 서서 요소 목록이 새 차례로
    간다(`marksPayload`)."""
    turns = HTML.index('<span class="sle-turns"')
    row = HTML.index('<span class="sle-order" hidden role="group" aria-label="순서">')
    assert turns < row < HTML.index('<span class="sle-lineprops"')
    block = HTML[row : HTML.index('<span class="sle-lineprops"')]
    assert re.findall(r'data-order="(\w+)"', block) == ["front", "fwd", "bwd", "back"]
    assert block.count('<span class="sle-tiphost" aria-describedby="sle-tip"><button') == 4
    assert re.findall(r"</svg>([^<]+)</button>", block) == [
        "맨 앞으로",
        "앞으로",
        "뒤로",
        "맨 뒤로",
    ]
    assert "display: none !important" in CSS[CSS.index(".sle-order[hidden]") :].split("}")[0]
    inspector = _js_decl("function syncInspector(")
    assert "syncTurns(chosen, mark)\n    syncOrder()\n" in inspector
    apply = JS[JS.index("  applyButton.onclick = () => {") :]
    apply = apply[: apply.index("\n  }\n")]
    assert "const marksChanged = markChangeCount() > 0" in apply
    assert "marks: marksChanged ? marksPayload() : null" in apply
    assert "return count + (markOrderChanged() ? 1 : 0)" in _js_decl("function markChangeCount(")
    assert "for (const button of orderButtons) button.onclick = () => stackOrder(" in JS
