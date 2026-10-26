# Purpose: Space 도면을 키보드만으로 고르고 놓는 길과 다시 그린 뒤의 초점을 검사한다.

"""키보드만으로는 도면의 호기를 하나씩 고를 수도, 서랍 칩을 놓을 수도 없었다(2026-10-26 E2E —
호기 상자에 초점이 오지 않아 Tab 이 도면을 지나쳤고, 칩에는 초점·역할이 없었다). 고른 길:

- 호기(편집·층 보기)와 편집의 도면 요소가 Tab 자리다. Enter·Space 는 누르기와 같다 — 편집은 그것
  하나를 고르고 Ctrl·Shift 는 더하거나 빼며(이어서 방향키·Ctrl+방향키·Delete), 층 보기는 그 호기
  정보 한 줄과 아래 표(`pick`)다.
- 서랍 칩은 이름이 단추다(칩 안의 「×」 와 나란해 단추 안에 단추가 들지 않는다). Enter 는
  끌어 놓기 — 지금 보이는 도면 가운데에 놓고 초점을 놓은 호기로 옮긴다. Space 는 누르기(고르기)다.
- 다시 그리면(`renderItems`) 같은 것의 새 노드에 초점을 돌려준다.

AppTest 는 편집기 JS 를 돌리지 못한다 — 처리기는 글자로 붙잡고, 초점 되돌리기는 선언을 글자 그대로
떼어 가짜 DOM 위에서 node 로 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패). 실제 동작은
브라우저로 본다.
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    begin = JS.index(start)
    return JS[begin : JS.index(end, begin)]


def _rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"{selector} 규칙이 없습니다."
    return match.group(1)


def test_units_and_edit_marks_are_tab_stops_and_enter_or_space_picks_them() -> None:
    """호기 상자는 편집·층 보기 모두, 도면 요소는 편집에서만 Tab 자리(단추)다. 보기 FAB 의 층 블록은
    지금처럼 여는 단추이고 비활성 블록은 초점을 걷는다."""
    unit = _between("function buildGroup(item) {", "function paintUnit(")
    assert "group.setAttribute('tabindex', '0')" in unit
    assert "group.setAttribute('role', 'button')" in unit
    mark = _between("function buildMark(item) {", "// 트레이 칩.")
    assert mark.index("if (opensFloor(item)) {") < mark.index("} else if (!VIEW) {")
    edit_marks = mark[mark.index("} else if (!VIEW) {") :]
    assert "group.setAttribute('tabindex', '0')" in edit_marks.split("appendHandles(group)")[0]

    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    view, edit = keys.split("if (event.key === 'Escape' && S.drag)")
    # 층 보기: 초점이 온 호기에서 Enter·Space 는 누르기(고르기 + 아래 표)와 같다.
    # FAB 보기에는 호기가 없다.
    assert "const unitNode = FAB ? null : canvasItemOf(event.target)" in view
    picked = view[view.index("if (unitNode &&") :]
    assert picked.index("select(unitNode.dataset.id)") < picked.index("notePick()")
    # 편집: Enter·Space 는 그것 하나를 고르고 Ctrl·Shift 는 더하거나 뺀다. 입력 칸에서는 비킨다.
    assert edit.index("if (typing) return") < edit.index(
        "const focusedItem = canvasItemOf(event.target)"
    )
    chosen = edit[edit.index("if (focusedItem && (event.key === 'Enter' || event.key === ' ')") :]
    assert "if (ctrl || event.shiftKey) toggleSelected(item)" in chosen
    assert "else select(item.id)" in chosen
    # 고른 뒤 Delete 는 초점이 호기에 있어도 듣는다(툴바 단추 뒤 Backspace 는 여전히 비킨다).
    assert "if (!chosen.length || (event.target !== svg && !focusedItem)) return" in edit
    # Shift/Ctrl+클릭과 같은 갈래다.
    assert "toggleSelected(item)" in _between(
        "svg.onpointerdown = (event) => {", "svg.onpointermove"
    )
    # 골라졌는지는 낭독기에도 간다.
    assert "setAttr(group, 'aria-pressed'" in _between(
        "function markSelection() {", "const overlaps ="
    )


def test_tray_chip_names_are_buttons_where_enter_places_and_space_picks() -> None:
    chip = _between("function buildChip(", "function renderItems()")
    assert "text.tabIndex = 0" in chip and "text.setAttribute('role', 'button')" in chip
    assert "— Enter 도면에 놓기 · Space 고르기" in chip
    keys = chip[chip.index("text.onkeydown = (event) => {") : chip.index("chip.onpointerdown")]
    assert (
        "pickChip(lead, list, { ctrl: event.ctrlKey || event.metaKey, shift: event.shiftKey })"
        in keys
    )
    assert "placeChipByKey(lead, list, event.altKey)" in keys
    # 칩 전체가 단추가 아니다 — 「×」 단추가 단추 안에 들지 않게.
    assert "chip.tabIndex" not in chip and "chip.setAttribute('role'" not in chip
    place = _between("function placeChipByKey(", "// 크기를 빌려 줄 종류")
    # 놓는 점은 열린 서랍이 덮지 않은 도면 가운데, 고른 칩 여럿 가운데 하나면 함께(끌기와 같다).
    assert "S.view.x + Math.max(viewW() - trayReserve(), 0) / 2" in place
    assert "picked.some((entry) => entry.lead.id === lead.id)" in place
    assert "placeManyFromTray(lead, picked, p, free)" in place
    assert "placeFromTray(lead, list, p, undefined, free)" in place
    # 놓았으면 초점은 놓은 호기로(이어서 방향키), 못 놓았으면 칩에 남는다.
    assert place.index("if (!onCanvas(lead) && !list.some(onCanvas)) return") < place.index(
        "group.focus({ preventScroll: true })"
    )
    hint = HTML[HTML.index('<p class="sle-tray-hint">') :]
    assert "<b>Enter</b>" in hint and "<b>Space</b>" in hint


def test_the_keyboard_focus_ring_is_a_screen_px_rect_not_an_outline() -> None:
    """SVG 안의 outline 은 도면 배율로 커진다(확대하면 테가 수십 px). 초점 테는 상자 밖으로 화면 px
    만큼 띄운 rect 이고(선 굵기도 배율과 무관), 초점이 있을 때만 선다."""
    assert "outline: none" in _rule(".sle-unit:focus, .sle:not(.is-view) .sle-mark:focus")
    ring = _rule(".sle-focus-ring")
    assert "display: none" in ring and "vector-effect: non-scaling-stroke" in ring
    assert "pointer-events: none" in ring
    shown = _rule(
        ".sle-unit:focus-visible > .sle-focus-ring, .sle:not(.is-view) .sle-mark:focus-visible > "
        ".sle-focus-ring"
    )
    assert "display: inline" in shown
    assert "outline: 2px" not in CSS[CSS.index(".sle-item {") : CSS.index("/* ---- 호기 ---- */")]
    handles = _between("function positionHandles(", "function position(group, item)")
    assert "const gap = FOCUS_GAP_PX * unitsPerPx()" in handles
    assert "group.append(el('rect', { class: 'sle-focus-ring'" in _between(
        "function appendHandles(group) {", "function buildGroup("
    )


# 가짜 DOM — 초점·포함·가까운 조상·자식 찾기만. 다시 그리기는 칩·상자 노드를 새로 만든다.
_FOCUS_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const root = { activeElement: null }
const body = { tag: 'BODY' }
function mk(cls, parent, attrs) {
  const n = { cls: new Set(cls.split(' ').filter(Boolean)), parent, kids: [], attrs: attrs || {} }
  n.dataset = {}
  n.hidden = false
  n.classList = { contains: (c) => n.cls.has(c) }
  n.hasAttribute = (a) => a in n.attrs
  n.closest = (sel) => {
    for (let x = n; x; x = x.parent) if (x.cls && x.cls.has(sel.slice(1))) return x
    return null
  }
  n.contains = (o) => {
    for (let x = o; x; x = x.parent) if (x === n) return true
    return false
  }
  n.querySelector = (sel) => {
    const walk = (x) => {
      for (const k of x.kids) {
        if (k.cls.has(sel.slice(1))) return k
        const f = walk(k)
        if (f) return f
      }
      return null
    }
    return walk(n)
  }
  n.focus = () => { root.activeElement = n }
  Object.defineProperty(n, 'parentNode', { get: () => n.parent })
  Object.defineProperty(n, 'children', { get: () => n.kids })
  if (parent) parent.kids.push(n)
  return n
}
const host = mk('sle', null)
host.getRootNode = () => root
const svg = mk('sle-canvas', host, { tabindex: '0' })
const trayBox = mk('sle-tray', host)
const traySearch = mk('sle-tray-search', trayBox)
const trayList = mk('sle-tray-list', trayBox)
const S = { groups: new Map() }
const draw = (units, chips) => {
  svg.kids = []
  S.groups = new Map()
  for (const id of units) {
    const g = mk('sle-item sle-unit', svg, { tabindex: '0' })
    g.dataset.id = id
    S.groups.set(id, g)
  }
  trayList.kids = []
  for (const [id, created, hidden] of chips) {
    const chip = mk('sle-chip', trayList)
    chip.dataset.id = id
    chip.hidden = Boolean(hidden)
    mk('sle-chip-name', chip, { tabindex: '0' })
    if (created) mk('sle-chip-remove', chip)
  }
}
const describe = (node) => {
  if (!node || node === body) return 'BODY'
  if (node === svg) return 'svg'
  if (node === traySearch) return 'search'
  const owner = node.closest('.sle-chip') || node.closest('.sle-item')
  const kind = node.cls.has('sle-chip-remove') ? 'remove'
    : node.cls.has('sle-chip-name') ? 'chip' : 'item'
  return `${kind}:${owner.dataset.id}`
}
%s
const out = {}
for (const c of input.cases) {
  draw(c.before.units, c.before.chips)
  const focusAt = c.focus
  const [kind, id] = focusAt.split(':')
  if (kind === 'item') S.groups.get(id).focus()
  else {
    const chip = trayList.kids.find((k) => k.dataset.id === id)
    chip.querySelector(kind === 'remove' ? '.sle-chip-remove' : '.sle-chip-name').focus()
  }
  const spot = focusSpot()
  draw(c.after.units, c.after.chips)
  root.activeElement = body
  restoreFocus(spot)
  out[c.name] = describe(root.activeElement)
}
process.stdout.write(JSON.stringify(out))
"""

_FOCUS_DECLS = ("function canvasItemOf(", "function focusSpot(", "function restoreFocus(")


def _focus_after_redraw(cases: list[dict[str, Any]]) -> dict[str, str]:
    source = _FOCUS_RUNNER % "\n".join(_js_decl(head) for head in _FOCUS_DECLS)
    result: dict[str, str] = _node(source, {"cases": cases})
    return result


def test_a_redraw_gives_focus_back_to_the_same_unit_or_chip() -> None:
    """방향키로 옮긴 모듈 묶음·되돌리기·적용처럼 상자를 다시 그려도 초점은 같은 호기의 새 상자에
    남는다. 트레이로 뺀(Delete) 호기는 도면에 둔다. 칩도 같은 칩의 새 이름 단추로 돌아온다."""
    units = ["U1", "U2", "U3"]
    chips = [["C1", False, False], ["C2", True, False]]
    cases = [
        {
            "name": "same_unit",
            "focus": "item:U2",
            "before": {"units": units, "chips": chips},
            "after": {"units": units, "chips": chips},
        },
        {
            "name": "unit_to_tray",
            "focus": "item:U2",
            "before": {"units": units, "chips": chips},
            "after": {"units": ["U1", "U3"], "chips": [["U2", False, False], *chips]},
        },
        {
            "name": "same_chip",
            "focus": "chip:C1",
            "before": {"units": units, "chips": chips},
            "after": {"units": units, "chips": chips},
        },
        {
            "name": "same_remove",
            "focus": "remove:C2",
            "before": {"units": units, "chips": chips},
            "after": {"units": units, "chips": chips},
        },
    ]

    result = _focus_after_redraw(cases)

    assert result == {
        "same_unit": "item:U2",
        "unit_to_tray": "svg",
        "same_chip": "chip:C1",
        "same_remove": "remove:C2",
    }
    render = _js_decl("function renderItems() {")
    assert render.index("const focused = focusSpot()") < render.index("layer.replaceChildren()")
    assert render.index("showSummary()") < render.index("restoreFocus(focused)\n  }\n")
