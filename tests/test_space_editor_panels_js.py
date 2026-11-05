# Purpose: Space 배치 편집기 두 옆 칸·스크롤 고정·미배치 칸 놓기 판정을 검사한다.

"""2026-11-03 사용자 요청 — 편집 영역 3단(왼쪽 도구 칸 · 도면 · 오른쪽 미배치 칸, 두 칸 폭
끌기·접기·기억)· 스크롤 고정 단추·미배치 호기 슬롯 이동성(도면 호기를 오른쪽 칸에 놓으면 미배치).

순수 판정은 `editor.js` 의 `// <side-panels>` 구획이고 node 로 떼어 돌린다(node·bun 이 없으면
건너뛰고 CI 에서는 실패 — `test_space_module_group._node`). 둘레(칸 그리기·끌기·고정 맞춤)는 자산
글자로 붙잡고 실제 동작은 브라우저로 본다.
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.page_tabs_state import PAGE_TABS_COMPONENT_KEY

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_PANELS = re.compile(r"// <side-panels>\n(?P<body>.*?)\n\s*// </side-panels>", re.S)

EDIT = {"lo": 200, "defLo": 220, "defShare": 0.18, "defHi": 300, "hi": 480, "hiShare": 0.4}
VIEW = {"lo": 160, "defLo": 200, "defShare": 0, "defHi": 200, "hi": 360, "hiShare": 0.3}

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
process.stdout.write(JSON.stringify({
  bounds: (input.bounds || []).map((c) => panelBounds(c.w, c.spec)),
  clamps: (input.clamps || []).map((c) => clampPanel(c.px, panelBounds(c.w, c.spec))),
  stored: (input.stored || []).map((raw) => storedPanels(raw)),
  keys: (input.keys || []).map((c) => splitKey(c.key, c.shift, c.side, c.now, c.bounds)),
  fits: (input.fits || []).map((c) => fitPanels(c.w, c.left, c.right, c.last, 360, 6)),
  limits: (input.limits || []).map((c) => dragLimit(c.w, c.other, c.splits, 360, c.lo)),
  heights: (input.heights || []).map((c) => lockHeight(c.vh, c.top, c.status, 280)),
  tops: (input.tops || []).map((c) => lockTop(c)),
  inside: (input.inside || []).map((c) => insideRect(c.rect, c.x, c.y)),
}))
"""


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    match = _PANELS.search(JS)
    assert match, "editor.js 에 // <side-panels> 구획이 없습니다"
    return _node(_RUNNER % match.group("body"), payload)


def test_panel_bounds_follow_the_spec_table() -> None:
    """편집 칸 — 기본 clamp(220, 폭 × 0.18, 300) · 최소 200 · 최대 min(480, 폭 × 0.4). 층 보기 범례
    칸 — 기본 200 · 최소 160 · 최대 min(360, 폭 × 0.3). 좁은 편집기에서도 최대가 최소 아래로 가지
    않는다."""
    result = _run(
        {
            "bounds": [
                {"w": 1500, "spec": EDIT},
                {"w": 1000, "spec": EDIT},
                {"w": 2400, "spec": EDIT},
                {"w": 400, "spec": EDIT},
                {"w": 1500, "spec": VIEW},
                {"w": 500, "spec": VIEW},
            ]
        }
    )

    assert result["bounds"] == [
        {"lo": 200, "hi": 480, "def": 270},
        {"lo": 200, "hi": 400, "def": 220},
        {"lo": 200, "hi": 480, "def": 300},
        {"lo": 200, "hi": 200, "def": 200},
        {"lo": 160, "hi": 360, "def": 200},
        {"lo": 160, "hi": 160, "def": 160},
    ]


def test_a_stored_width_is_clamped_and_a_missing_one_is_the_default() -> None:
    result = _run(
        {
            "clamps": [
                {"px": None, "w": 1500, "spec": EDIT},
                {"px": 999, "w": 1500, "spec": EDIT},
                {"px": 120, "w": 1500, "spec": EDIT},
                {"px": 333.6, "w": 1500, "spec": EDIT},
                {"px": -5, "w": 1500, "spec": EDIT},
            ]
        }
    )

    assert result["clamps"] == [270, 480, 200, 334, 200]


def test_stored_panels_keep_only_well_formed_modes_and_sides() -> None:
    """저장값 꼴 — {'<floor|fab>.<edit|view>': {left|right: {w, min}}}. 망가진 글·모르는 모드·꼴이
    다른 칸은 버리고, 폭은 0 초과 4000 이하의 수만(아니면 null = 기본), 접힘은 참일 때만."""
    good = (
        '{"floor.edit":{"left":{"w":281.4,"min":false},"right":{"w":300,"min":true}},'
        '"fab.edit":{"left":{"w":250}}}'
    )
    result = _run(
        {
            "stored": [
                good,
                "not json",
                "null",
                "[1,2]",
                '{"floor.edit":{"left":{"w":"wide","min":"yes"},"right":{"w":0}},"home.view":{"left":{"w":1}}}',
                '{"floor.view":{"left":{"w":99999,"min":true},"right":7}}',
            ]
        }
    )

    assert result["stored"] == [
        {
            "floor.edit": {"left": {"w": 281, "min": False}, "right": {"w": 300, "min": True}},
            "fab.edit": {"left": {"w": 250, "min": False}},
        },
        {},
        {},
        {},
        {"floor.edit": {"left": {"w": None, "min": False}, "right": {"w": None, "min": False}}},
        {"floor.view": {"left": {"w": None, "min": True}}},
    ]


def test_splitter_keys_widen_toward_the_stage_and_fold_with_enter() -> None:
    """왼쪽 칸은 → 가, 오른쪽 칸은 ← 가 넓힌다(16px, Shift 64px). Home 최대 · End 최소 · Enter 접기.
    그 밖의 키는 놓아 둔다(null) — 도면 단축키로도 새지 않게 칸막이가 멈춘다(둘레 시험)."""
    bounds = {"lo": 200, "hi": 480, "def": 270}
    cases = [
        ("ArrowRight", False, "left", {"width": 266}),
        ("ArrowLeft", False, "left", {"width": 234}),
        ("ArrowRight", True, "left", {"width": 314}),
        ("ArrowLeft", False, "right", {"width": 266}),
        ("ArrowRight", True, "right", {"width": 186}),
        ("Home", False, "right", {"width": 480}),
        ("End", False, "left", {"width": 200}),
        ("Enter", False, "left", {"fold": True}),
        ("a", False, "left", None),
        ("ArrowUp", False, "right", None),
    ]
    result = _run(
        {
            "keys": [
                {"key": key, "shift": shift, "side": side, "now": 250, "bounds": bounds}
                for key, shift, side, _ in cases
            ]
        }
    )

    assert result["keys"] == [expected for *_, expected in cases]


def test_two_wide_panels_leave_the_stage_its_minimum_by_shrinking_the_last_dragged_first() -> None:
    """두 칸을 다 넓혀 무대가 360px 아래로 가면 마지막에 끈 칸부터, 그래도 모자라면 다른 칸을 그
    최소까지 줄인다. 접힌 칸은 자리가 없다(단추는 무대 위에 뜬다)."""
    open_left = {"w": 400, "lo": 200, "open": True}
    open_right = {"w": 400, "lo": 200, "open": True}
    strip = {"w": 0, "lo": 0, "open": False}
    result = _run(
        {
            "fits": [
                {"w": 1500, "left": open_left, "right": open_right, "last": "right"},
                {"w": 1000, "left": open_left, "right": open_right, "last": "right"},
                {"w": 1000, "left": open_left, "right": open_right, "last": "left"},
                {"w": 700, "left": open_left, "right": open_right, "last": "left"},
                {"w": 700, "left": open_left, "right": strip, "last": "left"},
                {
                    "w": 1000,
                    "left": {"w": 0, "lo": 0, "open": False},
                    "right": open_right,
                    "last": None,
                },
            ]
        }
    )

    # 1000 − 12(칸막이 둘) − 360 = 628 이 두 칸 몫이다.
    assert result["fits"] == [
        {"left": 400, "right": 400},
        {"left": 400, "right": 228},
        {"left": 228, "right": 400},
        {"left": 200, "right": 200},
        {"left": 334, "right": 0},
        {"left": 0, "right": 400},
    ]


def test_a_folded_panel_leaves_the_stage_and_floats_a_button_over_it() -> None:
    """검수 eqp-side-01 — 접으면 칸 자리가 0 이 되어 도면이 넓어지고, 단추 하나만 무대 가장자리 8px
    안쪽 위에 뜬다(왼쪽 칸은 왼쪽, 오른쪽 칸은 오른쪽). 생김은 옛 미배치 서랍 단추 그대로다 — 앱
    단추 꼴(`.sle button`)에 면 색만 더하고 세로 글 · 화살표가 없다. 편집 · 보기 모두 같은
    규칙이다."""
    layout = JS[JS.index("function layoutPanels() {") : JS.index("function resizePanel(")]
    assert "w: open ? clampPanel(panelState(side).w, bounds) : 0" in layout
    assert "PANEL_STRIP_PX" not in JS
    floating = CSS[CSS.index(".sle-body > .sle-side.is-min {") :][:200]
    assert "position: absolute" in floating and "top: 8px" in floating
    assert "z-index: 2" in floating and "width: max-content" in floating
    assert ".sle-body > .sle-side.is-min.is-left { left: 8px; }" in CSS
    assert ".sle-body > .sle-side.is-min.is-right { right: 8px; }" in CSS
    assert (
        ".sle.is-narrow .sle-body > .sle-side.is-min { bottom: auto; width: max-content; }" in CSS
    )
    strip = CSS[CSS.index(".sle button.sle-side-strip {") :][:80]
    assert strip.startswith(".sle button.sle-side-strip { background: var(--sle-surface); }")
    assert "writing-mode" not in CSS
    assert (
        "›</span></button>" not in HTML and '>‹</span><span class="sle-side-strip-text"' not in HTML
    )
    # 끌어 놓기는 그대로 — 접힌 단추 위에 호기를 놓아도 미배치다(칸 상자가 곧 그 단추다).
    assert "insideRect(drawer.getBoundingClientRect(), event.clientX, event.clientY)" in JS


def test_a_dragged_panel_stops_where_the_stage_would_drop_under_its_minimum() -> None:
    result = _run(
        {
            "limits": [
                {"w": 1500, "other": 270, "splits": 12, "lo": 200},
                {"w": 900, "other": 300, "splits": 12, "lo": 200},
            ]
        }
    )

    assert result["limits"] == [858, 228]


def test_the_locked_stage_fills_the_window_below_its_top() -> None:
    """스크롤 고정 무대 높이 = 창 높이 − 무대 위 끝 − (상태 줄 + 12), 최소 280. 편집기 맨 위는 가림
    끝(화면 탭 줄 아래 끝, 없으면 머리 띠 72) + 8."""
    result = _run(
        {
            "heights": [
                {"vh": 950, "top": 140, "status": 20},
                {"vh": 1080, "top": 140, "status": 0},
                {"vh": 400, "top": 140, "status": 40},
            ],
            "tops": [89, 0, 60.4, 120.6],
        }
    )

    assert result["heights"] == [778, 928, 280]
    assert result["tops"] == [97, 80, 80, 129]


def test_a_drop_point_is_inside_the_right_panel_box() -> None:
    rect = {"left": 1200, "right": 1460, "top": 300, "bottom": 900, "width": 260, "height": 600}
    result = _run(
        {
            "inside": [
                {"rect": rect, "x": 1300, "y": 500},
                {"rect": rect, "x": 1200, "y": 300},
                {"rect": rect, "x": 1199, "y": 500},
                {"rect": {**rect, "width": 0}, "x": 1300, "y": 500},
                {"rect": None, "x": 1300, "y": 500},
            ]
        }
    )

    assert result["inside"] == [True, True, False, False, False]


# ---------------------------------------------------------------- 둘레(자산 글자)


def test_the_panels_are_remembered_per_scope_and_mode_only_in_the_browser() -> None:
    """칸 폭·접힘은 `capa.space.panels.v1`(범위·모드별), 묶음 접힘은 `capa.space.sections.v1` 이고
    파이썬으로 보내지 않는다(epoch 에도 넣지 않는다 — AGENTS 9장 「브라우저 전용 보기 상태」)."""
    assert "const PANELS_STORE_KEY = 'capa.space.panels.v1'" in JS
    assert "const SECTIONS_STORE_KEY = 'capa.space.sections.v1'" in JS
    assert "const PANEL_MODE = `${SCOPE}.${VIEW ? 'view' : 'edit'}`" in JS
    assert "const HAS_LEFT = !(VIEW && FAB)" in JS and "const HAS_RIGHT = !VIEW && !FAB" in JS
    # 처음엔 미배치 칸 도움말만 접힘.
    assert "sectionFolded(name, false)" in JS
    assert "sectionFolded('trayHint', true)" in JS


def test_the_splitters_are_keyboard_separators_that_do_not_leak_into_the_drawing() -> None:
    for side, label in (("left", "왼쪽 도구 칸 폭"), ("right", "오른쪽 미배치 칸 폭")):
        start = HTML.index(f'class="sle-split is-{side}')
        tag = HTML[HTML.rindex("<div", 0, start) : HTML.index(">", start)]
        assert 'role="separator"' in tag and 'aria-orientation="vertical"' in tag, side
        assert 'tabindex="0"' in tag and f'aria-label="{label}"' in tag, side
    bind = JS[
        JS.index("function bindSplit(side) {") : JS.index(
            "// ---------------- 왼쪽 칸 묶음".replace("---------------- ", "-" * 64 + " ")
        )
    ]
    assert "split.setPointerCapture(event.pointerId)" in bind
    assert "event.stopPropagation()" in bind and "splitKey(event.key, event.shiftKey, side" in bind
    assert "split.ondblclick" in bind and "panelState(side).w = null" in bind


def test_dragging_a_unit_onto_the_right_panel_unplaces_it_with_one_undo() -> None:
    """도면의 호기를 오른쪽 칸(접힌 단추 포함) 위로 끌면 「여기 놓으면 미배치로」 테가 서고, 놓으면
    끈 자리를 처음으로 돌린 뒤 호기만 빼기·지우기와 같은 길(`removeItems` — 되돌리기 한 번)로
    미배치다. 도면 요소는 제자리다."""
    move = JS[JS.index("    if (drag.mode === 'move') {\n      // 도면의 호기를") :]
    assert "insideRect(drawer.getBoundingClientRect(), event.clientX, event.clientY)" in move
    assert "drawer.classList.toggle('is-drop-target', toTray)" in move
    up = JS[JS.index("    if (drag.toTray) {") : JS.index("    const entries = drag.ids\n")]
    assert up.index("Object.assign(itemOf(id), before)") < up.index("removeItems(units)")
    assert "isUnit(m) && !m.ghost && onCanvas(m)" in up
    assert ".sle-side.is-drop-target .sle-drop-note" in CSS
    assert '<div class="sle-drop-note" aria-hidden="true">여기 놓으면 미배치로</div>' in HTML


def test_the_scroll_lock_lives_on_the_html_attribute_and_the_page_style() -> None:
    """고정은 `<html data-space-lock="1">` 과 페이지 서식(파이썬 `space_lock_style`)이다 — 다른
    화면으로 가면 서식이 사라져 풀린다. 마운트에만 두고(새 마운트는 풀린 채 — 앞에서 남은 속성을
    걷는다) 내릴 때 걷는다. 고정 중에는 높이 손잡이가 없고, 무대는 창 높이에 맞춘다(고른 높이·기억은
    그대로)."""
    assert "const LOCK_ATTR = 'data-space-lock'" in JS
    assert (
        "docEl.setAttribute(LOCK_ATTR, '1')" in JS and JS.count("removeAttribute(LOCK_ATTR)") == 3
    )
    assert "if (!S.lockReady) {" in JS
    fit = JS[JS.index("function fitStage() {") : JS.index("function chooseHeight(")]
    assert fit.index("if (S.lock && S.lockH) {") < fit.index("savedHeight()")
    assert "display: none" in CSS[CSS.index(".sle.is-locked .sle-resize {") :][:60]
    style = space_layout_editor.space_lock_style()
    assert style.startswith("<style>") and "/*" not in style
    assert 'html[data-space-lock="1"] [data-testid="stMain"]' in style
    assert "overflow:hidden !important" in style
    # 고정 높이는 화면 탭 줄(sticky) 아래부터다 — 편집기가 글자로 찾는 탭 줄 key 가 앱의 key 와
    # 같아야 한다(어긋나면 탭 줄을 못 찾아 위 72px 로 떨어지고 sticky 탭 줄이 편집기 위를 가린다 —
    # 리뷰 rules-7).
    cover = JS[JS.index("function coverBottom() {") :][:400]
    assert f"document.querySelector('.st-key-{PAGE_TABS_COMPONENT_KEY}')" in cover
    button = HTML[
        HTML.index('class="sle-lock"') - 30 : HTML.index(
            "</button>", HTML.index('class="sle-lock"')
        )
    ]
    assert 'aria-pressed="false"' in button
    # 도구 줄 오른쪽 끝(편집은 `적용` 바로 앞).
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('<div class="sle-body">')]
    assert (
        toolbar.index('class="sle-summary')
        < toolbar.index('class="sle-lock"')
        < toolbar.index('class="sle-apply')
    )


def test_the_legend_reaches_the_page_only_as_text_and_css_text() -> None:
    """범례는 편집기 왼쪽 칸 「범례」 다(2026-11-03 — 머리 줄 범례를 옮겼다). 파이썬이 칸
    목록(`label`·`css`·`inner`)과 끝 줄 「기준 YYYY-MM-DD」 를 data `legend`(epoch 밖)로 보내고, JS
    는 견본 꼴을 `style.cssText`, 글을 `textContent` 로만 단다 — HTML 로 읽지 않는다. 파이썬은 셋 다
    글자인 칸만 싣는다."""
    draw = JS[JS.index("function drawLegend() {") : JS.index("const keysToggle = q(")]
    assert "swatch.style.cssText = String(entry.css || '')" in draw
    assert "text.textContent = String(entry.label || '')" in draw
    assert "innerHTML" not in draw and "insertAdjacentHTML" not in draw
    assert "legendSection.hidden = !legend" in draw
    cleaned = space_layout_editor._clean_legend(
        {
            "entries": [
                {"label": "PKG 3대", "css": "width:11px", "inner": ""},
                {"label": 3, "css": "x", "inner": ""},
                "흐림",
            ],
            "asOf": "기준 2026-11-03",
        }
    )
    assert cleaned == {
        "entries": [{"label": "PKG 3대", "css": "width:11px", "inner": ""}],
        "asOf": "기준 2026-11-03",
    }
    assert space_layout_editor._clean_legend(None) is None
