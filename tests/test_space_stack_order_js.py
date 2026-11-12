# Purpose: Space 편집기 도면 요소의 그리는 차례(되돌리기 · 끌기 · 순서 단추)를 node 로 검사한다.

"""Space 편집기에서 겹 안 그리는 차례는 `S.items` 차례이고, 그것이 곧 도면 요소의 저장
차례(`floor_layout_mark.source_row_no` · `fab_layout_mark`)다(2026-11-12 Space 요청 7). 편집기
JS 의 선언을 글자 그대로 떼어 node 로 돌린다(node · bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`). 브라우저 조작 자체는 브라우저로 본다.
"""

from __future__ import annotations

from typing import Any

from test_space_module_group import _GHOST_DECLS, _js_decl, _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")

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
