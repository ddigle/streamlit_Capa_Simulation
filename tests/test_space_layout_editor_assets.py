# Purpose: Space 배치 편집기 자산(HTML·CSS·JS)의 뷰어 크기·서랍·단추·층 블록 계약을 글자로 검사한다.

"""AppTest 는 편집기 JS 를 돌리지 못한다. 그래서 크기 바꾸기가 재실행을 일으키지 않는다는
것, 높이 손잡이·서랍 자리, 단추 결처럼 자산 글자로 드러나는 약속을 여기서 붙잡는다. 실제 동작은
브라우저로 본다.
"""

from __future__ import annotations

import re

from capa_simulation.components import space_layout_editor

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
    FAB 층 블록의 `열기` 둘뿐이다."""
    assert "setStateValue" not in JS
    assert sorted(re.findall(r"setTriggerValue\('([a-z]+)'", JS)) == ["apply", "navigate"]
    # 관찰자는 한 번만 만들고, 실행마다 새로 정의되는 S.onResize 를 부른다. 내릴 때 끊는다.
    assert JS.count("new ResizeObserver(") == 1
    assert "if (!S.ro &&" in JS and "S.onResize = " in JS
    assert "S.ro.disconnect()" in JS


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
