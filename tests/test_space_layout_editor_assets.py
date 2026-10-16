# Purpose: Space 배치 편집기 자산(HTML·CSS·JS)의 뷰어 크기·서랍·단추·층 블록 계약을 글자로 검사한다.

"""AppTest 는 편집기 JS 를 돌리지 못한다. 그래서 크기 바꾸기가 재실행을 일으키지 않는다는
것, 높이 손잡이·서랍 자리, 단추 결처럼 자산 글자로 드러나는 약속을 여기서 붙잡는다. 실제 동작은
브라우저로 본다.
"""

from __future__ import annotations

import re

from capa_simulation.components import space_layout_editor
from capa_simulation.design import tokens
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_STATUSES,
    STATUS_EXIT_PLANNED,
    STATUS_STOP_PLANNED,
    STATUS_STOPPED,
)

ASSETS = space_layout_editor._ASSETS
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    """`selector {` 로 시작하는 첫 규칙의 본문."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"{selector} 규칙이 없습니다."
    return match.group(1)


def test_every_css_variable_comes_from_the_palette() -> None:
    """색은 등록 CSS 가 아니라 회차마다 `data.palette` 로 온다.

    CSS 가 쓰는 `--sle-*` 는 모두 그 안에 있어야 한다."""
    used = set(re.findall(r"var\(--sle-([a-z-]+)", CSS))

    assert used <= set(space_layout_editor._palette()), used - set(space_layout_editor._palette())


def test_the_stage_fills_the_column_and_the_svg_fills_the_stage() -> None:
    """옛 78vh 상한(SVG max-width)은 없다. 무대가 높이를 갖고 SVG 는 무대를 100%×100% 채운다."""
    assert "78vh" not in JS and "maxWidth" not in JS
    canvas = _rule(".sle-canvas")
    assert "width: 100%" in canvas and "height: 100%" in canvas
    assert "height:" in _rule(".sle-stage")


def test_the_height_handle_is_a_horizontal_separator_under_the_stage() -> None:
    stage = HTML.index('<div class="sle-stage">')
    handle = HTML.index('class="sle-resize"')
    tag = HTML[HTML.rindex("<div", 0, handle) : HTML.index(">", handle)]

    assert stage < handle
    assert 'role="separator"' in tag and 'aria-orientation="horizontal"' in tag
    assert 'tabindex="0"' in tag


def test_resizing_stays_in_the_browser() -> None:
    """크기는 파이썬으로 보내지 않는다(보내면 페이지 전체가 다시 돈다). 보내는 것은 `적용` 과
    FAB 층 블록의 `열기`(트리거), 그리고 기준일 `asOf`(상태 — 페이더를 놓을 때·FAB
    「오늘로」)뿐이다."""
    assert sorted(re.findall(r"setStateValue\('([A-Za-z]+)'", JS)) == ["asOf", "asOf"]
    assert JS.count("setStateValue(") == 2
    assert sorted(re.findall(r"setTriggerValue\('([a-z]+)'", JS)) == ["apply", "navigate"]
    # 관찰자는 한 번만 만들고, 실행마다 새로 정의되는 S.onResize 를 부른다. 내릴 때 끊는다.
    assert JS.count("new ResizeObserver(") == 1
    assert "if (!S.ro &&" in JS and "S.onResize = " in JS
    assert "S.ro.disconnect()" in JS


def test_a_plain_wheel_scrolls_the_page_even_when_zoomed() -> None:
    """휠은 Ctrl/Cmd 와 함께일 때만 확대이고, 맨 휠은 확대 중에도 도면을 옮기지 않는다.

    확대한 도면이 먼저 굴러가다 끝에 닿아야 페이지가 굴러가면 도면 위아래 단추로 가는 스크롤이
    꼬였다(2026-10-10 사용자 요청). 맨 휠이 도면을 옮기는 것은 편집기에서 호기·요소를 끌어
    옮기거나 크기를 바꾸는 동안뿐이다."""
    assert JS.count("onwheel") == 1
    start = JS.index("svg.onwheel = (event) => {")
    body = JS[start : JS.index("\n  }\n", start)]
    zoom = body.index("if (event.ctrlKey || event.metaKey) {")
    guard = body.index(
        "const placing = S.drag && (S.drag.mode === 'move' || S.drag.mode === 'resize')"
    )
    pan = body.index("panBy(")

    assert zoom < guard < pan
    assert "if (!placing || S.view.z <= 1) return" in body[guard:pan]
    assert body.count("panBy(") == 1


def test_every_browser_storage_access_is_guarded() -> None:
    """사생활 창·막힌 저장소에서는 localStorage 가 던진다. 모든 접근이 try 안이다."""
    lines = JS.splitlines()
    uses = [n for n, line in enumerate(lines) if "localStorage." in line]

    assert uses
    for n in uses:
        assert any(line.strip() == "try {" for line in lines[max(0, n - 3) : n]), lines[n]


def test_the_tray_is_a_drawer_inside_the_stage() -> None:
    """편집 모드의 트레이는 무대 오른쪽의 접히는 서랍이다 — 보기·편집에서 도면 상자가 같다."""
    stage = HTML.index('<div class="sle-stage">')
    drawer = HTML.index('class="sle-drawer')
    tray = HTML.index('class="sle-tray"')
    handle = HTML.index('class="sle-resize"')

    assert stage < drawer < tray < handle
    assert 'aria-expanded="false"' in HTML[drawer:tray]
    assert "position: absolute" in _rule(".sle-drawer")


def test_buttons_follow_the_app_button_grain() -> None:
    """앱 단추와 같은 결 — 모서리 8px · 굵기 600 · 테두리 BORDER · 글자 TEXT · 도구 줄 높이."""
    button = _rule(".sle button")

    assert "border-radius: 8px" in button
    assert "font-weight: 600" in button
    assert "var(--sle-border)" in button and "var(--sle-ui-text)" in button
    height = re.search(r"(?<![-\w])height: (\d+)px", button)
    assert height and 26 <= int(height.group(1)) <= 28
    # 도구 줄은 한 줄·고정 높이다(고를 때 도면이 튀지 않게).
    toolbar = _rule(".sle-toolbar")
    assert "flex-wrap: nowrap" in toolbar and re.search(r"(?<![-\w])height: \d+px", toolbar)
    # 좁은 열에서 도구 줄이 옆으로 밀려도 편집을 보내는 `적용` 은 오른쪽 끝에 붙어 보인다.
    apply = _rule(".sle button.sle-apply")
    assert "position: sticky" in apply and "right: 0" in apply


def test_the_inspector_keeps_its_size_whatever_is_selected() -> None:
    """고를 때 선택 칸 크기가 바뀌면 칸 줄 높이가 달라져 도면이 위아래로 튄다.

    번갈아 보이는 칸은 한 칸(`.sle-inspector-ext`)에 겹쳐 두고, 숨길 때도 자리를 남긴다."""
    ext = HTML.index('class="sle-inspector-ext"')
    assert ext < HTML.index('class="sle-field sle-sendto"') < HTML.index('class="sle-markprops"')
    hidden = _rule(
        ".sle-markprops[hidden], .sle-sendto[hidden], "
        ".sle-zone-only[hidden], .sle-mark-rotate[hidden]"
    )
    assert "visibility: hidden" in hidden and "display: none" not in hidden
    # 이름 칸은 글자 길이와 무관한 정한 폭으로 줄을 나눈다.
    title = _rule(".sle-inspector > .sle-panel-title")
    assert re.search(r"flex: 1 1 \d+em", title) and "text-overflow: ellipsis" in title


def test_only_a_floor_block_in_the_fab_viewer_opens_a_floor() -> None:
    """누르면 열리는 것은 보기 전용 FAB 의 층 블록뿐이다. 끌었으면 열지 않고, 키보드(Enter·
    Space)로도 연다. 영역·글자는 꾸밈이라 눌림을 받지 않는다. 층 블록은 FAB 범위에서만 그린다."""
    assert JS.count("setTriggerValue('navigate'") == 1
    assert "Boolean(VIEW && FAB && item && item.kind === 'block' && item.link)" in JS
    assert "if (!drag.travelled) openFloor(item)" in JS
    assert "(event.key === 'Enter' || event.key === ' ')" in JS
    assert "group.setAttribute('tabindex', '0')" in JS
    assert "const drawable = (kind) => Boolean(MARK_KINDS[kind]) && (kind !== 'block' || FAB)" in JS
    assert "pointer-events: none !important" in _rule(
        ".sle.is-view.is-fab .sle-mark:not(.mark-block), "
        ".sle.is-view.is-fab .sle-mark:not(.mark-block) *"
    )
    # 블록 대수는 epoch 밖의 `data.linkStats` 로 온다(같은 epoch 회차에도 글자를 다시 쓴다).
    assert "const LINK_STATS = data.linkStats || {}" in JS


def test_the_fab_editor_shows_only_fab_tools() -> None:
    """FAB 편집(`scope="fab"`)에는 호기가 없다 — 트레이 서랍·반입구·문·기둥·설비 금지가 숨고,
    층 블록 넣기와 블록 속성(연결 층·색·[열기])은 FAB 에만 선다."""
    rule = _rule(".sle.is-fab .sle-floor-only, .sle:not(.is-fab) .sle-fab-only")
    assert "display: none !important" in rule
    for kind in ("shutter", "door", "column"):
        assert f'class="sle-floor-only" data-kind="{kind}"' in HTML
    assert 'class="sle-fab-only" data-kind="block"' in HTML
    assert 'class="sle-drawer sle-edit-only sle-floor-only"' in HTML
    props = HTML[HTML.index('class="sle-block-props') :]
    assert props.index('class="sle-block-link"') < props.index('class="sle-block-open"')
    # 블록 속성은 영역 속성·돌리기와 한 칸에 겹쳐 숨을 때도 자리를 남긴다(고를 때 도면이 튀지 않게).
    assert "visibility: hidden" in _rule(".sle-block-props[hidden]")
    assert HTML.index('class="sle-markprops-kind"') < HTML.index('class="sle-block-props')


def test_the_inspector_open_is_locked_while_fab_edits_are_unapplied() -> None:
    """[열기] 는 적용하지 않은 FAB 편집이 있으면 잠긴다(열면 편집기가 내려가 그 편집이 사라진다).
    여는 길은 보기 전용 블록과 같은 `openFloor` 하나다 — `navigate` 를 보내는 자리는 하나뿐이다."""
    assert "blockOpen.disabled = pending || !mark.link" in JS
    assert "function hasPendingEdits()" in JS and "markChangeCount() > 0 || canvasChanged()" in JS
    assert "blockOpen.onclick = () => openFloor(selectedMark(), true)" in JS
    assert "(fromInspector && opensFromInspector(item))" in JS
    assert "!VIEW && FAB && item && item.kind === 'block' && item.link && !hasPendingEdits()" in JS


def test_a_dropped_unit_keeps_the_drawer_open_and_is_revealed() -> None:
    """놓아도 서랍은 열어 둔다(이어서 놓는다). 놓은 호기가 서랍 아래면 화면을 옮겨 보이고, 서랍이
    열려 있는 동안만 서랍 폭만큼 더 옮길 수 있다 — 접으면 제자리로 돌아온다."""
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert "setDrawer(false)" not in place
    assert "revealFromTray(list)" in place
    assert "function trayReserve()" in JS
    clamp = JS[JS.index("function clampView(") : JS.index("function applyView(")]
    assert "trayReserve()" in clamp and "center + reserve" in clamp
    set_drawer = JS[JS.index("function setDrawer(") : JS.index("function revealFromTray(")]
    assert "applyView(" in set_drawer
    assert "서랍이 접힙니다" not in HTML


def test_every_mark_takes_a_font_size_and_colour_from_the_inspector() -> None:
    """글자 크기·색 두 칸은 도면 요소 속성(`.sle-markprops`) 안이다 — 숨을 때도 자리를 지켜 선택 칸
    크기가 그대로다. 색은 팔레트의 `mark-text-<키>` 로 와 테마를 따라간다."""
    from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS, MARK_FONT_SIZES

    props = HTML[HTML.index('class="sle-markprops"') : HTML.index('class="sle-markprops-kind"')]
    assert 'class="sle-mark-font-size"' in props and 'class="sle-mark-font-color"' in props
    palette = space_layout_editor._palette()
    assert {f"mark-text-{key}" for key in MARK_COLOR_KEYS} <= set(palette)
    assert "`var(--sle-mark-text-${item.fontColor})`" in JS
    assert list(MARK_FONT_SIZES) == [9, 11, 13, 16, 20, 24]
    # 손대지 않은 요소가 바뀐 것으로 보이지 않게 원본 비교와 보내는 값이 두 칸을 함께 본다.
    assert "(o.fontSize ?? null) !== (item.fontSize ?? null)" in JS
    assert "fontSize: m.fontSize ?? null, fontColor: m.fontColor || ''" in JS
    assert "fontSize: fontSizeOf(raw.fontSize), fontColor: String(raw.fontColor || '')" in JS


def test_a_tinted_floor_block_is_painted_opaque_from_the_palette() -> None:
    """색을 고른 FAB 층 블록 면은 불투명이다(2026-10-07 사용자 결정 — 뒤가 비치지 않는다).

    색은 파이썬이 캔버스 위에 미리 섞어 팔레트의 `block-tint-<키>` 로 보낸다 — JS 에 색을 적지 않고,
    CSS `color-mix()` 나 `fill-opacity` 로 브라우저에 맡기지 않는다. 블록 글자는 `SURFACE` 테두리를
    두른다(글자 색이 색 블록과 바로 맞닿지 않게)."""
    from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS

    palette = space_layout_editor._palette()
    assert {f"block-tint-{key}" for key in MARK_COLOR_KEYS} <= set(palette)
    assert "`var(--sle-block-tint-${item.color})`" in JS
    assert "is-tinted" not in JS and "is-tinted" not in CSS
    assert "fill-opacity" not in _rule(".sle-block-fill")
    assert "color-mix" not in CSS and "color-mix" not in JS
    label = _rule(".sle-mark-text")
    assert "paint-order: stroke" in label and "stroke: var(--sle-surface)" in label


def test_a_named_column_writes_its_name_in_the_middle_without_the_cross() -> None:
    """기둥(2026-10-16 사용자 결정): 이름이 있으면 X 두 줄 없이 이름을 기둥 가운데에 돌리지 않고
    쓴다(자동 11px·고른 크기, 넘치면 넘쳐 그린다). 이름이 없으면 지금처럼 X 다."""
    draw = JS[JS.index("function drawMark(") : JS.index("function appendHandles(")]
    column = draw[
        draw.index("} else if (item.kind === 'column') {") : draw.index(
            "} else if (item.kind === 'text') {"
        )
    ]
    assert "if (!item.label) {" in column and column.count("sle-column-cross") == 2
    # 이름은 돌리는 `inner` 밖, 상자 가운데(cx, cy)에 이름표 크기(fs)로 쓴다.
    assert (
        "if (item.kind === 'column' && item.label) shape.append(text(item.label, cx, cy, fs))"
        in draw
    )
    assert "const fs = (item.fontSize || LABEL_PX) * upp" in draw and "const LABEL_PX = 11" in JS
    outside = draw[
        draw.index("// 반입구·문·동선의 이름표는") : draw.index("const tip = group.querySelector")
    ]
    assert "'column'" not in outside


def test_unit_colours_and_boundary_dates_pass_all_three_paths() -> None:
    """호기의 면·글자(`fill`·`ink`)와 경계 날짜는 세 곳을 모두 지나야 도면에 닿는다 — 파이썬
    `_clean_items` 화이트리스트, 첫 회차의 `readUnit`, 같은 epoch 회차의 합치기. 하나라도 빠지면
    체크·기준일을 바꾼 회차에 색이 옛 값으로 남는다. 이름 `group`·`arrived` 는 이미 다른 뜻이다."""
    fields = ("fill", "ink", "storage", "realFrom", "exitOn", "stopOn", "delays", "offline", "flag")
    cleaned = space_layout_editor._clean_items(
        [
            {
                "id": "U1",
                "x": 1,
                "y": 1,
                "w": 2,
                "h": 2,
                "fill": tokens.SPACE_LINE_TYPE_FILLS["PKG"],
                "ink": "red",
                "storage": 1,
                "realFrom": "0000-01-01",
                "exitOn": "2027-01-01",
                "stopOn": "2026/12/01",
                "delays": [["2026-09-01", None], ["bad", "2026-10-01"], "x"],
                "offline": (("2026-10-10", "2026-10-20"),),
                "flag": True,
            }
        ]
    )[0]
    assert set(fields) <= set(cleaned)
    assert cleaned["fill"] == tokens.SPACE_LINE_TYPE_FILLS["PKG"] and cleaned["ink"] == ""
    assert cleaned["storage"] is True and cleaned["flag"] is True
    assert (cleaned["realFrom"], cleaned["exitOn"], cleaned["stopOn"]) == (
        "0000-01-01",
        "2027-01-01",
        None,
    )
    assert cleaned["delays"] == [["2026-09-01", None]]
    assert cleaned["offline"] == [["2026-10-10", "2026-10-20"]]
    blank = space_layout_editor._clean_items([{"id": "U2", "x": 1, "y": 1, "w": 2, "h": 2}])[0]
    assert blank["fill"] == "" and blank["realFrom"] is None and blank["delays"] == []

    look = JS[JS.index("const unitLook = (raw) => ({") : JS.index("const readUnit = (raw)")]
    for field in fields:
        assert f"{field}: " in look, field
    assert "group" not in look and "arrived" not in look
    read = JS[JS.index("const readUnit = (raw)") : JS.index("const readMark = (raw)")]
    assert "...unitLook(raw)" in read
    merge = JS[JS.index("// 같은 epoch: 기하는") : JS.index("svg.onmousedown")]
    assert "...unitLook(raw)" in merge and "Object.assign(item, next)" in merge
    assert "refreshUnits(touched, previous)" in merge and "repaint()" in merge
    # 받은 값을 견주는 칸에 면·글자·경계 날짜가 다 든다 — 빠지면 그 값만 바뀐 회차를 「그대로」로
    # 본다.
    key = JS[JS.index("const sameLook = (o, n) =>") : JS.index("function refreshUnits(")]
    for field in fields:
        assert f"o.{field}" in key, field
    # 기준일은 epoch 밖의 `asOf` 로 온다 — 새 epoch 는 그대로 쓰고, 같은 epoch 는 `adoptAsOf` 가
    # 가른다.
    assert "S.asOf = AS_OF" in JS and "data.asOf" in JS and "adoptAsOf(AS_OF)" in merge


def test_the_unit_tip_does_not_repeat_what_the_stage_name_says() -> None:
    """풍선·선택 줄은 상태 이름(일정 기준)과 기준일의 판정 글자를 잇는다. 이름이 이미 말하는 뜻은
    거듭 적지 않는다 — 「반출/이설 예정」과 정지만 적힌 「정지 예정」은 도면 이탈 날짜를 이름에
    붙이고, 「정지」·「보관 설비」·「운영 비가동」이면 그 판정 낱말을 뺀다. JS 가 견주는 이름은
    파이썬 상태 이름 목록에 있어야 한다(이름을 바꾸면 여기서 걸린다)."""
    words = JS[JS.index("function unitWords(item) {") : JS.index("const zoneColor")]
    compared = set(re.findall(r"stage [!=]== '([^']+)'", words))
    assert compared == {
        STATUS_EXIT_PLANNED,
        STATUS_STOP_PLANNED,
        STATUS_STOPPED,
        "보관 설비",
        "운영 비가동",
    }
    assert compared <= set(EQUIPMENT_STATUSES)
    assert "!item.stopOn" in words and "${stage} ${item.exitOn}" in words
    tip = JS[JS.index("const unitTip = (item) => {") : JS.index("const sameGeometry")]
    pick = JS[JS.index("function pickText(item) {") : JS.index("function updateStatus()")]
    for line in (tip, pick):
        assert "const { stage, words } = unitWords(item)" in line
        assert "item.stage" not in line
    assert "stateWords" not in JS


def test_the_editor_draws_no_meaning_rings_only_edit_marks() -> None:
    """배치 편집 화면의 테는 선택·묶음·다른 층·겹침 전용이다(2026-10-16 — 표 #15). 의미
    표시(반입 전·반출/이설 예정 테, 빗금, 「!」, 비가동 표식, 겹침 꼭지, 선택 후광)는 보기 화면만
    그린다 — CSS 규칙은 `.sle.is-view` 아래에만, JS 는 보기에서만 부품을 만들고 class 를 단다."""
    for meaning in ("is-pre", "is-exitplan", "is-stopped", "has-flag", "is-offline", "is-gone"):
        rules = [line for line in CSS.splitlines() if f".{meaning}" in line]
        assert rules, meaning
        assert all(".sle.is-view" in line for line in rules), (meaning, rules)
    shown = [
        selector.strip()
        for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
        if "display: inline" in body
        for selector in selectors.split(",")
    ]
    for part in (
        ".sle-halo",
        ".sle-ring",
        ".sle-ring-out",
        ".sle-hatch",
        ".sle-flag",
        ".sle-corner",
    ):
        found = [selector for selector in shown if selector.endswith(part)]
        assert found and all(selector.startswith(".sle.is-view") for selector in found), part
    edit_rings = [line for line in CSS.splitlines() if "is-selected .sle-rect" in line]
    assert edit_rings and all(line.startswith(".sle:not(.is-view)") for line in edit_rings)
    paint = JS[JS.index("function paintUnit(group, item) {") : JS.index("function buildMark(")]
    first_class = paint.index("group.classList.toggle(")
    assert paint.index("if (!VIEW) return") < first_class
    build = JS[JS.index("function buildGroup(item) {") : JS.index("function paintUnit(")]
    assert "if (VIEW) {" in build and "group.append(rect, label, tip)" in build
    # 보기 화면의 호기 겹침은 테가 아니라 오른쪽 위 꼭지 삼각이다.
    assert ".sle.is-view .sle-unit.is-overlap .sle-corner" in CSS
    assert "polygon" in build and "sle-corner" in build


def test_a_unit_label_is_fitted_by_its_measured_width() -> None:
    """호기 이름표는 잰 글자 폭으로 상자 폭에 맞춘다. 글자 수 어림(한 글자 0.62em)은 한글·굵은
    대문자를 덜 쳐서 C1 4F 의 「설비호기1」이 상자를 넘어 옆 「SAMPLE1」과 붙어 보였다(2026-10-08).
    재는 굵기는 이름표 CSS 의 굵기와 같아야 한다. 7px 아래 숨김 규칙은 그대로다."""
    position = JS[JS.index("function position(") : JS.index("function drawMark(")]
    assert "labelEm(item.label)" in position
    assert "item.label.length" not in position
    assert "fontSize / upp < 7 ? 'none' : ''" in position
    measure = JS[JS.index("const labelEm = ") : JS.index("const snapshot = ")]
    assert "measureText(text)" in measure and "`600 100px ${" in measure
    assert "font-weight: 600" in _rule(".sle-label")
    # 서체를 받는 중에 잰 값은 기억하지 않는다 — 받기 전 대체 서체의 폭이 굳지 않게.
    assert "document.fonts.status === 'loaded'" in measure


def test_dropping_from_the_tray_keeps_the_tray_scroll_position() -> None:
    """놓은 뒤에도 서랍 스크롤이 보던 자리다(2026-10-08 사용자 요청 — 이어서 놓을 때마다 맨 위로
    돌아갔다).

    `renderItems` 가 서랍 목록을 비웠다 다시 채우는 동안 목록 높이가 줄어 브라우저가 스크롤을 0 으로
    잘라 낸다. 비우기 전에 서랍(`.sle-tray`, 스크롤 칸)의 `scrollTop` 을 기억했다 다 채운 뒤
    되돌린다.
    """
    body = JS[JS.index("function renderItems()") : JS.index("function markSelection()")]
    assert body.index("const trayScroll = trayBox.scrollTop") < body.index(
        "trayList.replaceChildren()"
    )
    assert body.index("trayList.append(") < body.index("trayBox.scrollTop = trayScroll")


def test_several_tray_chips_can_be_picked_and_dropped_together() -> None:
    """Ctrl·Shift(⌘)+누르기로 서랍 칩 여럿을 고르고, 고른 칩 하나를 끌면 모두 한 격자로 함께
    놓인다.

    배치는 모듈 설비를 한 번에 놓는 격자(`placeFromTray`)를 그대로 쓴다. 고르지 않은 칩을 끌면
    지금처럼 그 칩만 놓이고, 수식키 없이 누르면 그 칩 하나만 골라진다. 놓은 뒤에는 놓은 것이 모두
    골라진 채다.
    """
    chip = JS[JS.index("function buildChip(") : JS.index("function renderItems()")]
    assert "const additive = event.shiftKey || event.ctrlKey || event.metaKey" in chip
    assert "placeManyFromTray(lead, picked, p)" in chip
    assert "additive ? toggleTrayPick(list) : select(lead.id)" in chip
    many = JS[JS.index("function placeManyFromTray(") : JS.index("function placeFromTray(")]
    assert "placeFromTray(lead, list, p," in many
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert "S.selection = new Set(name ? list.map((m) => m.id) : [lead.id])" in place
    assert "Ctrl·Shift" in HTML


def test_the_tray_lists_units_by_name_and_can_be_searched() -> None:
    """서랍 칩은 보이는 이름의 오름차순(숫자는 수로)이고, 검색 칸에 이름 일부를 치면 그 호기만
    남아 바로 끌어 놓을 수 있다(2026-10-08 사용자 요청). 검색은 목록을 다시 만들지 않고 칩만
    감추며, 가려진 칩은 고른 채여도 함께 놓이지 않는다. 검색어가 있으면 Esc 는 서랍을 접기 전에
    검색어부터 지운다."""
    entries = JS[JS.index("function trayEntries(") : JS.index("function trayMatches(")]
    assert "TRAY_ORDER.compare(chipName(a), chipName(b))" in entries
    assert "new Intl.Collator('ko', { numeric: true" in JS
    assert 'class="sle-tray-search"' in HTML and 'type="search"' in HTML
    assert 'class="sle-tray-empty" hidden' in HTML
    apply = JS[JS.index("function applyTrayFilter(") : JS.index("function buildChip(")]
    assert "chip.hidden = !visible" in apply and "trayCount.textContent" in apply
    picked = JS[JS.index("function pickedTrayEntries(") : JS.index("function toggleTrayPick(")]
    assert "trayMatches(entry)" in picked
    assert "traySearch.onkeydown" in JS and "S.trayQuery = ''" in JS


# ---------------------------------------------------------------- 기준일 페이더(2026-10-16 결정 5)


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end)]


def test_the_date_row_tops_the_floor_drawing_with_one_height_for_view_and_edit() -> None:
    """층 도면 상자 맨 위 한 줄(36px)이 기준일 줄이다 — 보기는 페이더(날짜 칩·트랙·「오늘」), 배치
    편집은 같은 자리·같은 높이의 「기준일 … · 편집 중 고정」 줄. FAB 에는 없다(`sle-floor-only`).
    무대 기본 높이는 그 줄과 틈만큼 덜어 보기·편집의 도면 상자 크기가 같다."""
    row = HTML[HTML.index('<div class="sle-daterow') : HTML.index('<div class="sle-toolbar">')]
    assert HTML.index('class="sle-daterow') < HTML.index('class="sle-toolbar"')
    assert 'class="sle-daterow sle-floor-only"' in row
    fader = row[row.index('class="sle-fader ') : row.index('class="sle-pinned ')]
    assert "sle-view-only" in fader
    assert 'type="range"' in fader and 'step="1"' in fader
    for part in ("sle-fader-date", "sle-fader-rel", "sle-fader-note", "sle-fader-ticks"):
        assert f'class="{part}"' in fader, part
    assert 'class="sle-fader-today"' in fader and ">오늘</button>" in fader
    pinned = row[row.index('class="sle-pinned ') :]
    assert "sle-edit-only" in pinned and "편집 중 고정" in pinned
    assert "height: 36px" in _rule(".sle-daterow")
    assert "const DATE_ROW_PX = 36" in JS
    assert "const CHROME_PX = VIEW_CHROME_PX + (FAB ? 0 : DATE_ROW_PX + 8)" in JS
    assert "window.innerHeight - CHROME_PX" in JS
    assert "gap: 8px" in _rule(".sle")
    assert "if (PINNED) setText(pinnedDate, `기준일 ${S.asOf" in JS
    assert "const PINNED = !VIEW && !FAB" in JS


def test_the_fader_spans_the_range_python_sends_with_today_in_bold() -> None:
    """범위·오늘은 파이썬이 보낸다(`asOfMin`·`asOfMax`·`today` — `space_unit_state.as_of_range`).
    눈금은 달마다, 분기는 길게 글자를 달고, 오늘은 굵은 강조색 눈금과 「오늘」 글자다. 칩은
    「날짜 · 오늘」 또는 「날짜 · +3개월 2주」다."""
    assert "dayOr(data.today)" in JS and "dayOr(data.asOfMin)" in JS and "dayOr(data.asOfMax)" in JS
    build = _between("function buildFader() {", "function showFader() {")
    assert "'sle-tick is-quarter'" in build and "'sle-tick is-today'" in build
    assert "'sle-tick-label is-today', today, '오늘'" in build
    assert "faderInput.max = String(hi - lo)" in build
    assert "background: var(--sle-accent)" in _rule(".sle-tick.is-today")
    rel = _between("function relText(T) {", "const lowDay = ")
    assert "'오늘'" in rel and "개월" in rel and "주" in rel and "일" in rel
    show = _between("function showFader() {", "function setAsOf(T) {")
    assert "setText(faderRel, `· ${relText(S.asOf)}`)" in show
    assert "faderRel.classList.toggle('is-today', isToday)" in show


def test_the_fader_keys_move_a_day_a_month_or_to_the_ends_and_stay_in_the_fader() -> None:
    """←/→ 하루, PageUp/PageDown 한 달, Home/End 범위 끝, 두 번 누르기·「오늘」 단추는 오늘. 키는
    도면 단축키(화면 이동·확대)로 새지 않는다."""
    keys = _between("faderInput.onkeydown = (event) => {", "if (PINNED)")
    for expected in (
        "ArrowLeft: now - 1",
        "ArrowRight: now + 1",
        "PageDown: addMonths(now, -1)",
        "PageUp: addMonths(now, 1)",
        "Home: lowDay()",
        "End: highDay()",
    ):
        assert expected in keys, expected
    assert keys.index("event.stopPropagation()") < keys.index("const next = {")
    assert "event.preventDefault()" in keys
    fader = _between("if (FADER) {\n    buildFader()", "if (PINNED)")
    assert "faderInput.ondblclick" in fader and "jumpTo(TODAY)" in fader
    assert "faderToday.onclick = () => jumpTo(TODAY)" in fader


def test_dragging_paints_in_frames_and_releasing_sends_the_date_once() -> None:
    """끄는 동안 서버 회차는 없다 — `input` 은 requestAnimationFrame 으로 프레임마다 마지막 날만
    칠하고(`paintAsOf` — 앞 날과 새 날 사이에 경계 날짜가 든 호기만, 그중 판정 부호가 바뀐
    상자만), 손을 떼면(`change`·`pointerup`) `setStateValue` 를 한 번 보낸다. 키는 누를 때마다
    보내지 않고 멈춘 뒤 한 번이다. 파이썬이 이미 쥐었거나 곧 쥘 날이면 보내지 않는다. 겹침은 짝을
    한 번 구해 두고 숨김이 바뀐 프레임에만 다시 본다."""
    fader = _between("if (FADER) {\n    buildFader()", "if (PINNED)")
    oninput = fader[fader.index("faderInput.oninput") : fader.index("faderInput.onchange")]
    assert "setStateValue" not in oninput and "setAsOf(" in oninput
    assert "faderInput.onchange = () => commitAsOf()" in fader
    assert "S.commitTimer = setTimeout(commitAsOf, KEY_COMMIT_MS)" in fader
    frame = _between("function setAsOf(T) {", "function commitAsOf() {")
    assert "requestAnimationFrame(flushAsOf)" in frame and "if (!S.faderFrame)" in frame
    assert "paintAsOf(previous)" in frame
    commit = _between("function commitAsOf() {", "const jumpTo = ")
    assert commit.count("setStateValue('asOf', T)") == 1
    assert "const expected = S.sent.size ? S.lastSent : S.dataAsOf" in commit
    assert "if (T && T !== expected)" in commit
    paint = _between("function buildEvents() {", "// 풍선 글은 올려 둘 때")
    # 두 날 사이(앞날 < 날 ≤ 뒷날)의 경계 날짜만 찾는다 — 운영 비가동은 끝날 다음 날에 바뀐다.
    assert "isoOf(dayNumber(until) + 1)" in paint and "events[mid][0] <= lo" in paint
    assert "paintUnits(previous && S.events ? changedBetween(previous, S.asOf) : null)" in paint
    # 숨김이 바뀐 때만 겹침을 다시 본다. 기하(`position`)는 건드리지 않는다.
    assert "if (flipped.length) markOverlaps(flipped)" in paint and "position(" not in paint
    overlap = _between("function markOverlaps(flipped) {", "// 끄는 동안에는 움직이는 것만")
    view = overlap[: overlap.index("const units = [...S.items.values()]")]
    assert "const pairs = overlapPairs()" in view and "for (let b = a + 1" not in view
    pairs = _between("function overlapPairs() {", "// 끄는 동안에는 움직이는 것만")
    assert "if (S.adjacency) return S.adjacency" in pairs and "OVERLAP_CELL" in pairs
    render = _between("function renderItems()", "function markSelection()")
    assert "S.adjacency = null" in render and "if (VIEW && !FAB) buildEvents()" in render
    unit = _between("function paintUnit(group, item) {", "function buildMark(")
    assert "if (group.__paint === code) return" in unit


def test_a_same_epoch_run_keeps_the_browser_date_and_repaints_nothing_unchanged() -> None:
    """같은 epoch 회차에 받은 기준일이 지난 회차와 같으면(끄는 중·보낸 날이 아직 안 돌아옴·다른
    위젯의 회차) 브라우저가 칠한 날을 지키고, 보낸 날이 돌아오면 맞았다고 보며, 파이썬이 따로 바꾼
    날만 따른다. 받은 호기 값이 쥔 값과 같으면 다시 칠하지 않는다(전체 `repaint` 는 1,289대에
    70~100ms)."""
    adopt = _between(
        "function adoptAsOf(incoming) {",
        "// ------------------------------------------------------------- 회차마다",
    )
    assert "if (incoming === S.dataAsOf) return ''" in adopt
    assert "if (S.sent.has(incoming)) {" in adopt
    assert "if (S.faderBusy || S.commitTimer) return ''" in adopt
    merge = JS[JS.index("// 같은 epoch: 기하는") : JS.index("svg.onmousedown")]
    assert "if (sameLook(item, next)) continue" in merge
    refresh = _between("function refreshUnits(touched, previous) {", "function isChanged(item) {")
    assert "if (!touched.length && !previous) {" in refresh and "paintUnits(ids)" in refresh
    assert "if (touched.length) buildEvents()" in refresh
    # 상태 이름은 파이썬이 쥔 날의 것이다 — 다른 날을 보는 동안에는 「(그날 기준)」을 단다.
    words = _between("function unitWords(item) {", "const zoneColor")
    assert "`${named}(${S.dataAsOf} 기준)`" in words


def test_the_fab_toolbar_shows_the_as_of_date_a_back_to_today_button_and_unconfirmed_units() -> (
    None
):
    """FAB 전체에는 페이더가 없다. 도구 줄 요약 앞에 「기준일 …」, 오늘이 아니면 「오늘로」,
    미확인이 있으면 「! 미확인 N대」(0 이면 숨김)."""
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('class="sle-summary')]
    for part in ("sle-asof", "sle-totoday", "sle-flagnote"):
        tag = toolbar[
            toolbar.rindex("<", 0, toolbar.index(part)) : toolbar.index(">", toolbar.index(part))
        ]
        assert "sle-fab-only" in tag and "sle-view-only" in tag, part
    assert ">오늘로</button>" in toolbar
    fab = JS[
        JS.index("if (VIEW && FAB) {\n    setText(fabAsOf") : JS.index(
            "// ---------------------------------------------------------------- 높이 손잡이"
        )
    ]
    assert "fabToToday.hidden = !TODAY || !S.asOf || S.asOf === TODAY" in fab
    assert "setStateValue('asOf', TODAY)" in fab
    assert "flagNote.hidden = flagged === 0" in fab
    assert "display: none" in _rule(".sle button.sle-totoday[hidden], .sle-flagnote[hidden]")
