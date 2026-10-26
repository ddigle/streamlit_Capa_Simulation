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


def test_placeholders_use_the_muted_ink_of_the_theme() -> None:
    """미배치 호기 찾기·새 호기 설비명 칸의 자리표시 글이 브라우저 기본(#757575)이면 어두운 테마
    바탕에서 4.5:1 에 못 미친다(설비 마스터 표와 같은 꼴, 2026-10-26 E2E). TEXT_MUTED 로 그린다."""
    rule = re.search(r"\.sle input::placeholder\s*\{(?P<body>[^}]*)\}", CSS)
    assert rule, "editor.css 에 자리표시 규칙이 없다"
    assert "color: var(--sle-muted)" in rule.group("body") and "opacity: 1" in rule.group("body")


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
    FAB 층 블록의 `열기`·층 상세 뷰어에서 누른 호기(`pick`, 트리거), 그리고 기준일 `asOf`(상태 —
    페이더를 놓을 때·FAB 「오늘로」)뿐이다."""
    assert sorted(re.findall(r"setStateValue\('([A-Za-z]+)'", JS)) == ["asOf", "asOf"]
    assert JS.count("setStateValue(") == 2
    assert sorted(re.findall(r"setTriggerValue\('([a-z]+)'", JS)) == ["apply", "navigate", "pick"]
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
        "const placing = S.drag && (S.drag.mode === 'move' || S.drag.mode === 'resize' "
        "|| S.drag.mode === 'range')"
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
        ".sle-zone-only[hidden], .sle-mark-rotate[hidden], .sle-module-tile[hidden]"
    )
    # 모듈 묶음의 「범위에 맞춰 n등분」 단추도 층 보내기 칸 안에서 자리를 남긴 채 숨는다.
    sendto = HTML[HTML.index('class="sle-field sle-sendto"') : HTML.index('class="sle-markprops"')]
    assert 'class="sle-module-tile" hidden' in sendto
    assert "visibility: hidden" in hidden and "display: none" not in hidden
    # 이름 칸은 글자 길이와 무관한 정한 폭으로 줄을 나눈다.
    title = _rule(".sle-inspector > .sle-panel-title")
    assert re.search(r"flex: 1 1 \d+em", title) and "text-overflow: ellipsis" in title


def test_the_inspector_wraps_inside_its_panel_on_a_narrow_window() -> None:
    """390px 창에서 층 배치 편집을 켜면 층 보내기 칸(이름·보낼 층·보내기, 숨은 「범위에 맞춰
    n등분」·「Main 설비명」)이 한 줄로 553px 을 차지해 선택 칸 밖으로 넘치고 본문이 596px 로
    넓어졌다(2026-10-26 E2E). 겹친 칸은 선택 칸 폭을 넘지 않고, 층 보내기 칸은 그 안에서 줄을
    바꾼다."""
    ext = _rule(".sle-inspector-ext, .sle-markprops-kind")
    assert "display: inline-grid" in ext and "max-width: 100%" in ext
    sendto = _rule(".sle-sendto")
    assert "flex-wrap: wrap" in sendto
    # 다른 번갈아 보이는 칸(도면 요소·영역·층 블록 속성)은 이미 줄을 바꾼다.
    for selector in (".sle-markprops", ".sle-zone-props", ".sle-block-props"):
        assert "flex-wrap: wrap" in _rule(selector), selector


def test_only_a_floor_block_in_the_fab_viewer_opens_a_floor() -> None:
    """누르면 열리는 것은 보기 전용 FAB 의 층 블록뿐이다. 끌었으면 열지 않고, 키보드(Enter·
    Space)로도 연다. 영역·글자는 꾸밈이라 눌림을 받지 않는다. 층 블록은 FAB 범위에서만 그린다."""
    assert JS.count("setTriggerValue('navigate'") == 1
    assert (
        "Boolean(VIEW && FAB && item && item.kind === 'block' && item.link && !blockOff(item))"
        in JS
    )
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


def test_an_inactive_floor_block_is_grey_hatched_and_never_opens() -> None:
    """비활성 층(사용 안 함·생산라인 아님)을 가리키는 블록은 회색 면 + 영역 빗금 + 흐린 사유 글자로
    그리고, 보기에서 눌러도·Enter 로도 열리지 않으며 고르지도 않는다(강조 테두리가 서지 않는다).
    편집에서는 그대로 옮기고 [열기] 만 꺼진다. 사유는 연결 층의 `linkStats.inactive` 에서 온다."""
    assert "LINK_STATS[item.link].inactive" in JS
    # 사유 줄이 대수 줄을 대신한다(풍선에는 대수가 남고 「누르면 열기」 는 없다).
    assert "if (blockOff(item)) return [blockHead(item), blockOff(item)]" in JS
    assert (
        "[blockHead(item), '비활성', blockOff(item), stats.placed, stats.unplaced, stats.layout]"
        in JS
    )
    # 면·빗금·글자: 인라인 고른 색과 「글자 색」 을 달지 않는다(인라인이 CSS 를 이긴다).
    draw = JS[JS.index("} else if (item.kind === 'block') {") : JS.index("function appendHandles(")]
    assert "group.classList.toggle('is-inactive', Boolean(off))" in draw
    assert "item.color && markColors[item.color] && !off" in draw
    assert "class: 'sle-block-hatch'" in draw and "fill: 'url(#sle-hatch)'" in draw
    assert "const ink = blockOff(item) ? '' : fontInk(item)" in JS
    # 보기 FAB 에서 비활성이면 Tab 이 건너뛴다(초점·역할을 걷는다).
    assert "group.removeAttribute('tabindex')" in draw
    # 보기 누름: 블록 위인지는 종류로 정해 비활성 블록을 고르지 않는다 — 열지 말지는 `openFloor` 가
    # 거른다.
    assert "S.lastViewOnBlock = Boolean(FAB && item && item.kind === 'block')" in JS
    assert "S.lastViewOnBlock = opensFloor(item)" not in JS
    # 편집 [열기] 잠금과 선택 칸 경로.
    assert "blockOpen.disabled = pending || !mark.link || Boolean(blockOff(mark))" in JS
    assert "item.link && !hasPendingEdits() && !blockOff(item)" in JS
    # 올리면 선택 줄에 어디서 여는지 알린다.
    hint = JS[JS.index("S.showBlockHint = (group) => {") : JS.index("const opensFromInspector")]
    assert hint.index("blockOff(item)") < hint.index("if (!opensFloor(item))")
    assert "「비활성 층」에서 엽니다" in hint
    # CSS: 회색 면이 고른 색을 이기고, 사유 글자는 muted, 보기에서는 손가락·강조 테두리가 없다.
    assert "fill: var(--sle-block-off) !important" in _rule(
        ".mark-block.is-inactive .sle-block-fill"
    )
    assert "fill: var(--sle-muted)" in _rule(".mark-block.is-inactive .sle-mark-text")
    assert "cursor: default" in _rule(".sle.is-view.is-fab .mark-block.is-inactive")
    assert "stroke: var(--sle-frame)" in _rule(
        ".sle.is-view.is-fab .mark-block.is-inactive:hover .sle-block-border"
    )


def test_a_dropped_unit_keeps_the_drawer_open_and_is_revealed() -> None:
    """놓아도 서랍은 열어 둔다(이어서 놓는다). 놓은 호기가 서랍 아래면 화면을 옮겨 보이고, 서랍이
    열려 있는 동안만 서랍 폭만큼 더 옮길 수 있다 — 접으면 제자리로 돌아온다."""
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert "setDrawer(false)" not in place
    assert "revealFromTray(shown)" in place
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
    fields = (
        "fill",
        "ink",
        "storage",
        "realFrom",
        "exitOn",
        "stopOn",
        "delays",
        "offline",
        "flag",
        "layer",
        "dim",
    )
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
                "layer": "m",
                "dim": True,
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
    # 「필요 단축」 칸은 값이 있을 때만 실린다(끈 동안 payload 그대로) — 모르는 구간·참이 아닌 dim
    # 은 버린다.
    assert cleaned["layer"] == "m" and cleaned["dim"] is True
    assert "layer" not in blank and "dim" not in blank
    odd = space_layout_editor._clean_items(
        [{"id": "U3", "x": 1, "y": 1, "w": 2, "h": 2, "layer": "q", "dim": 1}]
    )[0]
    assert "layer" not in odd and "dim" not in odd

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
    assert "fontSize / upp < UNIT_LABEL_MIN_PX ? 'none' : ''" in position
    assert "const UNIT_LABEL_MIN_PX = 7" in JS
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
    """Ctrl(⌘)+누르기로 서랍 칩을 하나씩 더하거나 빼고, Shift+누르기로 기준 칩부터 그 칩까지(보이는
    차례) 고르며(2026-10-23 사용자 요청 — Ctrl+Shift 는 그 범위를 더한다), 고른 칩 하나를 끌면 모두
    한 격자로 함께 놓인다.

    배치는 모듈 설비를 한 번에 놓는 격자(`placeFromTray`)를 그대로 쓴다. 고르지 않은 칩을 끌면
    지금처럼 그 칩만 놓이고, 수식키 없이 누르면 그 칩 하나만 골라진다. 놓은 뒤에는 놓은 것이 모두
    골라진 채다. 범위 판정은 `tests/test_space_editor_tools.py` 가 node 로 돌린다.
    """
    chip = JS[JS.index("function buildChip(") : JS.index("function renderItems()")]
    assert "const keys = { ctrl: event.ctrlKey || event.metaKey, shift: event.shiftKey }" in chip
    assert "placeManyFromTray(lead, picked, p, free)" in chip
    assert "() => pickChip(lead, list, keys)" in chip
    pick = JS[JS.index("function pickChip(") : JS.index("function placeManyFromTray(")]
    assert "trayRangeIds(order, S.trayAnchor, lead.id)" in pick
    assert "visible: !chip.hidden" in pick and "keys.ctrl ? [...S.selection]" in pick
    assert "S.trayAnchor = lead.id" in pick and "if (keys.ctrl) toggleTrayPick(list)" in pick
    many = JS[JS.index("function placeManyFromTray(") : JS.index("function placeFromTray(")]
    assert "placeFromTray(lead, list, p," in many
    place = JS[JS.index("function placeFromTray(") : JS.index("function addMark(")]
    assert "S.selection = new Set(onePerGroup(name ? shown.map((m) => m.id) : [lead.id]))" in place
    assert "<b>Ctrl</b>" in HTML and "<b>Shift</b>" in HTML and "<b>Ctrl+Shift</b>" in HTML


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
    # 날짜는 입력의 `aria-valuetext` 가 말한다 — 끄는 동안 프레임마다 바뀌는 칩은 낭독
    # 영역으로 두지 않는다.
    assert "aria-live" not in fader
    assert "setAttr(faderInput, 'aria-valuetext'" in JS
    pinned = row[row.index('class="sle-pinned ') :]
    assert "sle-edit-only" in pinned and "편집 중 고정" in pinned
    assert "height: 36px" in _rule(".sle-daterow")
    assert "const DATE_ROW_PX = 36" in JS
    assert "const CHROME_PX = VIEW_CHROME_PX + (FAB ? 0 : DATE_ROW_PX + 8)" in JS
    assert "window.innerHeight - CHROME_PX" in JS
    assert "gap: 8px" in _rule(".sle")
    assert "if (PINNED) setText(pinnedDate, `기준일 ${S.asOf" in JS
    assert "const PINNED = (!VIEW && !FAB) || ASOF_PINNED" in JS


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
    도면 단축키(화면 이동·확대)로 새지 않는다. 「오늘」 단추는 누르면 꺼지므로 초점을 먼저 페이더로
    옮긴다(키보드로 누른 초점이 문서 맨 앞으로 떨어지지 않게)."""
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
    today = fader[fader.index("faderToday.onclick = () => {") : fader.index("faderInput.onkeydown")]
    assert today.index("faderInput.focus({ preventScroll: true })") < today.index("jumpTo(TODAY)")


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
    미확인이 있으면 「! 미확인 N대」(0 이면 숨김). 「오늘로」는 누르면 꺼지고 숨으므로 초점을 먼저
    도면으로 옮긴다."""
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('class="sle-summary')]
    for part in ("sle-asof", "sle-totoday", "sle-flagnote"):
        tag = toolbar[
            toolbar.rindex("<", 0, toolbar.index(part)) : toolbar.index(">", toolbar.index(part))
        ]
        assert "sle-fab-only" in tag and "sle-view-only" in tag, part
    assert '>오늘<span class="sle-totoday-tail">로</span></button>' in toolbar
    assert 'aria-label="기준일을 오늘로"' in toolbar
    fab = JS[
        JS.index("fabAsOf.hidden = !S.asOf") : JS.index(
            "// ---------------------------------------------------------------- 높이 손잡이"
        )
    ]
    assert "setText(fabAsOfDate, S.asOf || '')" in fab
    assert "fabToToday.hidden = !TODAY || !S.asOf || S.asOf === TODAY" in fab
    assert "setStateValue('asOf', TODAY)" in fab
    click = fab[fab.index("fabToToday.onclick = () => {") : fab.index("const flagged")]
    assert click.index("svg.focus({ preventScroll: true })") < click.index(
        "fabToToday.disabled = true"
    )
    assert "flagNote.hidden = flagged === 0" in fab
    assert "setText(flagCount, `${flagged.toLocaleString('ko-KR')}대`)" in fab
    assert "display: none" in _rule(
        ".sle-asof[hidden], .sle button.sle-totoday[hidden], .sle-flagnote[hidden]"
    )


def test_a_narrow_fab_toolbar_folds_step_by_step_and_keeps_the_summary_whole() -> None:
    """사이드바를 연 1024px 창처럼 FAB 도구 줄이 넘치면 `fitFabBar` 가 접는 차례를 하나씩
    더한다 — ① 선택 안내·「기준일」·「미확인」 말머리(화면에서만 — 낭독기용으로 남김), ② 미확인
    대수(「!」만), ③ 「오늘로」 → 「오늘」, ④ 기준일 날짜 말줄임, ⑤ 요약 말줄임. 요약은 마지막에야
    줄고, 대수 글자는 반만 잘리지 않는다."""
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('<div class="sle-panels')]
    assert '<span class="sle-asof-label">기준일 </span>' in toolbar
    assert 'class="sle-flagnote-word">미확인 </span>' in toolbar
    fit = _between(
        "function fitFabBar() {",
        "// ---------------------------------------------------------------- 높이 손잡이",
    )
    assert (
        "const FIT_STEPS = ['is-fit1', 'is-fit2', 'is-fit3', 'is-fit4', 'is-fit5', 'is-fit6']" in JS
    )
    assert fit.index("toolbar.classList.remove(...FIT_STEPS)") < fit.index("if (!(VIEW && FAB)")
    assert "if (toolbar.scrollWidth <= toolbar.clientWidth) return" in fit
    resize = _between("S.onResize = () => {", "if (!S.ro && typeof ResizeObserver")
    assert "fitFabBar()" in resize
    hidden = _rule(
        ".sle-toolbar.is-fit1 .sle-asof-label, .sle-toolbar.is-fit1 .sle-flagnote-word, "
        ".sle-toolbar.is-fit2 .sle-flagnote-text"
    )
    assert "display: none" not in hidden and "clip-path: inset(50%)" in hidden
    assert "content: none" in _rule(".sle-toolbar.is-fit1 .sle-pick:empty::before")
    assert "display: none" in _rule(".sle-toolbar.is-fit3 .sle-totoday-tail")
    # 기준일 날짜 말줄임 다음, 마지막에야 요약도 말줄임(풍선에 온 글)이다.
    last = _rule(".sle-toolbar.is-fit4 .sle-asof, .sle-toolbar.is-fit5 .sle-summary")
    assert "text-overflow: ellipsis" in last
    # 요약 글(겹쳐 숨긴 반입 예정 대수를 붙인 것)이 그대로 풍선이다(`showSummary`).
    summary = _between("function showSummary() {", "function overlapPairs() {")
    assert "setText(node, text)" in summary and "setAttr(node, 'title', text)" in summary
    # 대수 글자(미확인)는 말줄임으로 반만 잘리지 않는다 — 접을 때는 통째로.
    assert "ellipsis" not in _rule(".sle-flagnote")
    assert "flex: none" in _rule(".sle-toolbar > *")
    assert "flex" not in _rule(".sle-summary")


def test_a_fab_toolbar_too_narrow_for_a_readable_summary_moves_it_to_a_second_line() -> None:
    """390px 휴대폰 폭에서는 확대 묶음(268px)만으로 FAB 도구 줄(327px)이 거의 차 ④·⑤
    말줄임이 기준일을 2px(「2」 조각)·요약을 9px(「배」)로 깎았다(2026-10-26 E2E).

    말줄임은 앞머리가 읽히는 폭까지만 주고(기준일 4em·요약 6em), 그래도 넘치면 ⑥
    기준일·「오늘」·미확인·요약을 둘째 줄로 내린다 — 보기에서 숨는 빈 칸이 온 폭 줄바꿈이
    된다. 한 줄 설계의 까닭(고를 때 높이가 튀지 않음)은 두 줄도 창 폭으로만 정해져 그대로다."""
    assert "\n.sle-toolbar.is-fit4 .sle-asof { min-width: 4em; }" in CSS
    assert "\n.sle-toolbar.is-fit5 .sle-summary { min-width: 6em; }" in CSS
    assert "min-width: 0" not in _rule(
        ".sle-toolbar.is-fit4 .sle-asof, .sle-toolbar.is-fit5 .sle-summary"
    )
    wrap = _rule(".sle-toolbar.is-fit6")
    assert "flex-wrap: wrap" in wrap and "height: auto" in wrap
    spacer = _rule(".sle.is-view .sle-toolbar.is-fit6 .sle-spacer")
    assert "display: block" in spacer and "flex: 0 0 100%" in spacer
    # 빈 칸은 선택 줄 바로 뒤, 기준일·미확인·요약 앞이다 — 첫 줄은 확대 묶음과 선택 줄.
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('<div class="sle-panels')]
    assert (
        toolbar.index('class="sle-pick')
        < toolbar.index('class="sle-spacer"')
        < toolbar.index('class="sle-asof')
        < toolbar.index('class="sle-summary')
    )
    # ⑥ 은 ⑤ 뒤 마지막 차례다(읽히는 말줄임이 되면 둘째 줄로 내리지 않는다).
    assert "'is-fit5', 'is-fit6']" in JS


def test_the_pre_arrival_ring_is_drawn_thick() -> None:
    """반입 예정(실물 없음) 테는 굵은 점선이다(2026-10-23 사용자 요청 — 2px 은 면색 위에서 잘 안
    보였다). 범례 견본(`space_layout._mark_swatches`)은 3px 이다."""
    ring = _rule(".sle.is-view .sle-unit.is-pre .sle-ring")
    match = re.search(r"stroke-width: ([\d.]+)", ring)
    assert match and float(match.group(1)) >= 3 and "stroke-dasharray" in ring


def test_the_shortening_view_pins_the_date_and_draws_badges_only_when_python_says_so() -> None:
    """색 기준 「필요 단축」(명세 6-7·10-3 T-B4). 파이썬이 `asOfPinned` 를 실은 층 보기만 기준일
    고정 줄을 세우고(페이더 숨김 — `is-pinned`), 배지(`shortBadges`)를 그리며, 모든 호기의 지연·보관
    면을 칠하지 않는다(결정 D12). 표시된 호기는 겹쳐 숨기지 않는다(`<view-cover>`). 흐림·고정 규칙은
    보기 아래에만 있고, `is-dim` 토글은 `if (!VIEW) return` 뒤다. 배지만 바뀐 같은 epoch 회차는 배지
    지문으로 다시 그린다."""
    assert "typeof data.asOfPinned === 'string'" in JS
    assert "host.classList.toggle('is-pinned', ASOF_PINNED)" in JS
    assert "const FADER = VIEW && !FAB && !ASOF_PINNED" in JS
    assert "Array.isArray(data.shortBadges)" in JS
    colours = JS[JS.index("function unitColors(item, st) {") : JS.index("const color = (item)")]
    assert colours.index("if (item.layer)") < colours.index("st.delay")
    assert "st.delay && !ASOF_PINNED" in colours and "st.storage && !ASOF_PINNED" in colours
    cover = JS[JS.index("function coveredBy(") : JS.index("// </view-cover>")]
    assert "if (item.layer) return false" in cover
    paint = JS[JS.index("function paintUnit(group, item) {") : JS.index("function buildMark(")]
    assert paint.index("if (!VIEW) return") < paint.index("group.classList.toggle('is-dim'")
    assert "JSON.stringify(SHORT_BADGES)" in JS and "S.badgeKey !== badgeKey" in JS
    assert "drawShortBadges()" in JS[JS.index("function drawGroupNames() {") :]
    assert "// <short-badge>" in JS and "function badgeSpot(" in JS
    # 고정 줄 뒷글 — 보기는 data 글, 편집기는 HTML 글 그대로.
    assert "ASOF_PINNED ? ` · ${data.asOfPinned}` : S.pinnedNoteDefault" in JS
    assert '<g class="sle-short-badges"></g>' in HTML
    for rule in (".sle.is-view .sle-unit.is-dim", ".sle.is-view.is-pinned .sle-fader"):
        assert rule in CSS, rule
    assert ".sle.is-view.is-pinned .sle-pinned { display: flex !important; }" in CSS
    dim_rules = [line for line in CSS.splitlines() if ".is-dim" in line]
    assert dim_rules and all(".sle.is-view" in line for line in dim_rules)
    # 블록 셋째 줄(단축)은 비활성 블록에 서지 않는다(사유 줄만).
    lines = JS[JS.index("const blockLines = (item) => {") : JS.index("const opensFloor")]
    assert lines.index("if (blockOff(item))") < lines.index("stats.short")
