# Purpose: Space 편집기 도구 줄 「단축키」 판의 표 · 화면별 줄과 상태 줄의 값 · 표지 꼴을 검사한다.

"""검수 equip-61 — 상태 줄의 하는 법 글을 걷고, 지금 화면에서 쓸 수 있는 키를 도구 줄 「호기 정보」
옆 「단축키」 판에 「키조합 : 기능」 으로 모았다. 표는 `editor.js` 의 `// <shortcuts>` 구획 한
곳이고 node 로 떼어 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`). 표의 모든 줄은 맡는 코드 표식과 맞대고(`HANDLED`), 거꾸로 도면 키
처리의 키도 표와 맞댄다(`KEYS_IN_HANDLER`). 둘레(판 열기 · 닫기)는 자산 글자로 붙잡고 실제 동작은
브라우저로 본다.
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_SHORTCUTS = re.compile(r"// <shortcuts>\n(?P<body>.*?)\n\s*// </shortcuts>", re.S)
SCREENS = ("vf", "vb", "ef", "eb")

_RUNNER = """
%s
process.stdout.write(JSON.stringify(Object.fromEntries(
  ['vf', 'vb', 'ef', 'eb'].map((screen) => [screen, shortcutRows(screen)])
)))
"""


def _rows() -> dict[str, Any]:
    match = _SHORTCUTS.search(JS)
    assert match, "editor.js 에 // <shortcuts> 구획이 없습니다"
    return _node(_RUNNER % match.group("body"), {})


def _keys(screen: str) -> list[str]:
    return [row[0] for row in _rows()[screen]]


def _status() -> str:
    return JS[JS.index("  function updateStatus() {") : JS.index("  function commitTyping() {")]


def test_each_screen_lists_only_the_keys_it_has() -> None:
    """고치는 키는 편집 화면에만, 호기 키는 층 화면에만, 페이더 키는 층 보기에만 선다. 한 화면에
    같은 키조합이 두 번 서지 않는다."""
    rows = _rows()
    for screen in SCREENS:
        keys = [row[0] for row in rows[screen]]
        assert keys and len(keys) == len(set(keys)), screen
        assert all(row[0] and row[1] for row in rows[screen]), screen
    for screen in ("vf", "vb"):
        for key in ("Ctrl+Z", "Delete", "Ctrl+C · Ctrl+V", "Alt+Shift+C", "Shift+H", "Space+끌기"):
            assert key not in _keys(screen), (screen, key)
    for screen in ("ef", "eb"):
        for key in ("Ctrl+Z", "Delete", "Ctrl+방향키", "Alt+Shift+V", "Alt 누른 채 끌기"):
            assert key in _keys(screen), (screen, key)
    assert "호기 두 번 클릭" in _keys("vf") and "호기 두 번 클릭" in _keys("ef")
    assert (
        "칩 Enter" in _keys("ef")
        and "칩 Enter" not in _keys("eb")
        and "칩 Enter" not in _keys("vf")
    )
    assert "호기 두 번 클릭" not in _keys("vb") and "호기 두 번 클릭" not in _keys("eb")
    assert "PageUp · PageDown" in _keys("vf") and "PageUp · PageDown" not in _keys("ef")
    # 같은 Enter 라도 층 보기는 호기, FAB 보기는 층을 연다.
    assert dict(map(tuple, rows["vf"]))["Enter · Space"] == "초점 둔 호기 고르기"
    assert dict(map(tuple, rows["vb"]))["Enter · Space"] == "초점 둔 층 열기"


# 표의 모든 줄 → 그 줄을 맡는 코드 표식(키조합, 기능). 표에 줄을 더하면 여기에도 더해야 하고,
# 코드에서 표식이 사라지면 실패한다 — 듣지 않는 키를 표에 적거나 표에서 빠뜨린 줄을 잡는다.
HANDLED: dict[tuple[str, str], str] = {
    ("Ctrl+휠", "확대 · 축소"): "zoomAt(S.view.z * Math.exp(-event.deltaY * unit * 0.002)",
    ("+ · −", "확대 · 축소"): "event.key === '-'",
    ("0", "전체 보기"): "event.key === '0'",
    ("화면 고정 중 휠", "도면 옮기기"): "if (S.lock) {",
    (
        "화면 고정 중 Shift+휠",
        "도면 가로로 옮기기",
    ): "(event.shiftKey ? event.deltaY : event.deltaX) * unit",
    ("방향키", "화면 옮기기"): "const moves = { ArrowLeft: [-step, 0]",
    ("Tab", "다음 호기로"): "canvasItemOf(event.target)",
    ("Tab", "다음 층 블록으로"): "closest('.mark-block')",
    ("Enter · Space", "초점 둔 호기 고르기"): "if (unitNode && (event.key === 'Enter'",
    ("Enter · Space", "초점 둔 층 열기"): "if (block && (event.key === 'Enter'",
    ("Esc", "고르기 풀기"): "event.key === 'Escape'",
    ("호기 두 번 클릭", "호기 정보 창 열기"): "openSheet('picked')",
    ("← · →", "페이더에서 기준일 하루"): "ArrowLeft",
    ("PageUp · PageDown", "페이더에서 기준일 한 달"): "PageUp",
    ("Home · End", "페이더에서 기준일 범위 끝"): "Home",
    ("Ctrl+Z", "실행 취소"): "event.key.toLowerCase() === 'z'",
    ("Ctrl+A", "전체 고르기"): "event.key.toLowerCase() === 'a'",
    (
        "Ctrl · Shift+클릭",
        "고르기에 더하기 · 빼기",
    ): "const additive = event.shiftKey || event.ctrlKey",
    ("빈 곳 끌기", "사각형으로 여러 개 고르기"): "mode: 'marquee', additive",
    ("Tab · Enter", "초점 옮겨 고르기"): "focusedItem && (event.key === 'Enter'",
    ("Ctrl+Enter", "고르기에 더하기 · 빼기"): "if (ctrl || event.shiftKey) toggleSelected(item)",
    ("Esc", "붓 내리기 · 고르기 풀기"): "if (event.key === 'Escape' && S.paint)",
    ("방향키", "고른 것 옮기기"): "moveItems(standing, ax, ay)",
    ("Shift+방향키", "고른 것 다섯 칸 옮기기"): "event.shiftKey ? 5 : 1",
    ("Ctrl+방향키", "고른 것 크기 바꾸기"): "setSizes(standing",
    ("Delete", "빼기 · 지우기"): "event.key === 'Delete'",
    ("Ctrl+C · Ctrl+V", "도면 요소 복사 · 붙여넣기"): "letter === 'c'",
    ("Alt+Shift+C", "서식 복사(Ctrl+Shift+C 도)"): "formatKey === 'c'",
    ("Alt+Shift+V", "서식 붙여넣기(Ctrl+Shift+V 도)"): "formatKey === 'v'",
    ("Shift+H", "좌우 뒤집기"): "flipKeyOf(event)",
    ("Shift+V", "상하 뒤집기"): "flipMarks(flipKey)",
    ("Shift+모서리 끌기", "도형 비율 유지"): "Shift 는 가로세로 비율",
    ("Alt 누른 채 끌기", "정렬선에 붙이지 않기"): "showDragGuides(drag, event.altKey)",
    ("Space+끌기", "화면 옮기기"): "S.spaceDown = true",
    ("칩 Ctrl+클릭", "미배치 칩 더하기 · 빼기"): "ctrl: event.ctrlKey || event.metaKey, shift",
    ("칩 Shift+클릭", "미배치 칩 범위 고르기"): "shift: event.shiftKey }",
    ("칩 Ctrl+Shift+클릭", "미배치 칩 범위 더하기"): "() => pickChip(lead, list, keys)",
    ("칩 Enter", "미배치 칩을 도면 가운데에 놓기"): "placeChipByKey(lead, list",
    ("칩 Space", "미배치 칩 고르기(Ctrl · Shift 도)"): "if (event.key === ' ') pickChip(lead",
    # 「호기 정보」 창 칸 고치기(배치 편집 — 2026-11-12 시안 보드 답 5-4).
    ("창 칸 두 번 클릭 · F2", "호기 정보 칸 열기(글자를 치면 바로)"): "if (event.key === 'F2' || ",
    (
        "창 칸 Enter · Tab",
        "칸 확정하고 다음 칸으로",
    ): "closeSheetCell(true, event.shiftKey ? 'left'",
    ("창 칸 Esc", "칸 고치기 취소"): "closeSheetCell(false, 'stay')",
    ("창 칸 Delete", "칸 비우기"): "commitSheetCell(cursor.id, cursor.col, '')",
}
# 도면 키 처리(`host.onkeydown`)가 이름으로 견주는 키 — 표에 없는 키를 처리에 더하면 실패한다. 값은
# 그 키를 적은 표 줄의 키조합이다.
KEYS_IN_HANDLER: dict[str, str] = {
    "Escape": "Esc",
    "Enter": "Enter · Space",
    " ": "Enter · Space",
    "+": "+ · −",
    "=": "+ · −",
    "-": "+ · −",
    "0": "0",
    "z": "Ctrl+Z",
    "a": "Ctrl+A",
    "Delete": "Delete",
    "Backspace": "Delete",
    "KeyC": "Ctrl+C · Ctrl+V",
    "KeyV": "Ctrl+C · Ctrl+V",
    "c": "Ctrl+C · Ctrl+V",
    "v": "Ctrl+C · Ctrl+V",
}


def _table_rows() -> set[tuple[str, str]]:
    rows = _rows()
    return {(row[0], row[1]) for screen in SCREENS for row in rows[screen]}


def _handler() -> str:
    start = JS.index("  host.onkeydown = (event) => {")
    return JS[start : JS.index("for (const input of fieldInputs) {", start)]


def test_every_row_of_the_table_is_handled_in_the_code() -> None:
    """표의 모든 줄은 맡는 코드가 있다 — 듣지 않는 키를 표에 적거나 맡는 코드를 빼면 실패한다."""
    assert _table_rows() == set(HANDLED), "표와 HANDLED 가 다릅니다"
    missing = {row: mark for row, mark in HANDLED.items() if mark not in JS}
    assert not missing, missing


def test_the_key_handler_listens_only_to_keys_the_table_names() -> None:
    """거꾸로 — 도면 키 처리에 표에 없는 키를 더하면 실패한다(표는 키 처리의 한 곳이다)."""
    keys = _handler()
    named = set(re.findall(r"event\.(?:key|code)(?:\.toLowerCase\(\))? === '([^']+)'", keys))
    named |= set(re.findall(r"\(event\.key === '([^']+)'", keys))
    named |= set(re.findall(r"event\.code === '([^']+)' \? '[^']+'", keys))
    named |= set(re.findall(r"\? '([a-z])' : event\.code", keys))
    named |= set(re.findall(r"\? '([a-z])' : event\.key", keys))
    assert named == set(KEYS_IN_HANDLER), "도면 키 처리의 키가 표 맞댐과 다릅니다"
    table_keys = {row[0] for row in _table_rows()}
    assert set(KEYS_IN_HANDLER.values()) <= table_keys


def test_two_presses_on_the_same_unit_open_the_sheet_on_the_edit_screen() -> None:
    """편집 화면은 눌린 상자를 맨 위에 다시 붙여 dblclick 이 서지 않는다 — 움직이지 않은 누름 둘을
    직접 잡는다. 판정은 같은 호기 · 짧은 사이만 두 번 누름이다."""
    match = _SHORTCUTS.search(JS)
    assert match
    out: Any = _node(
        match.group("body")
        + """
process.stdout.write(JSON.stringify([
  isDoublePress(null, 'A', 100),
  isDoublePress({ id: 'A', at: 100 }, 'A', 100 + DOUBLE_PRESS_MS),
  isDoublePress({ id: 'A', at: 100 }, 'A', 101 + DOUBLE_PRESS_MS),
  isDoublePress({ id: 'B', at: 100 }, 'A', 200),
]))
""",
        {},
    )
    assert out == [False, True, False, False]
    release = JS[JS.index("  svg.onpointerup = svg.onpointercancel = (event) => {") :]
    release = release[: release.index("svg.onlostpointercapture")]
    assert "isDoublePress(S.lastPress, drag.id, pressedAt)" in release
    assert release.index("isDoublePress") < release.index("openSheet('picked')")


def test_the_button_sits_next_to_the_unit_sheet_and_folds_with_it() -> None:
    """단추는 도구 줄 「호기 정보」 바로 옆이고 FAB 에도 선다(`sle-floor-only` 없음). 좁은 도구
    줄에서는 「호기 정보」 와 함께 아이콘만 남는다. 판은 몸 안에 겹쳐 뜬다(도구 줄은 넘침을
    자른다)."""
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('<div class="sle-body">')]
    sheet = toolbar.index('class="sle-sheet-toggle')
    keys = toolbar.index('class="sle-keys-toggle"')
    assert sheet < keys < toolbar.index('class="sle-lock"')
    assert toolbar[sheet:keys].count("<button") == 1
    assert ".sle-toolbar.is-efit1:not(.is-fit6) .sle-keys-toggle-word" in CSS
    body = HTML[HTML.index('<div class="sle-body">') :]
    assert (
        'class="sle-keys" id="sle-keys" role="dialog" aria-label="단축키" tabindex="-1" hidden'
        in body
    )


def test_the_panel_closes_by_esc_outside_press_and_stays_in_the_browser() -> None:
    """Esc 는 판을 먼저 닫는다(고른 것 · 붓은 그대로) · 판 밖 누르기 · 단추 · × 로도 닫힌다. 열림은
    보기 상태라 파이썬으로 보내지 않는다. 판은 초점을 받는다(`tabindex="-1"`) — 판 안 글을 눌러도
    초점이 편집기 밖으로 빠지지 않아 Esc 가 듣는다."""
    keydown = JS[JS.index("  host.onkeydown = (event) => {") :]
    closes = keydown.index("if (event.key === 'Escape' && keysOpen())")
    assert closes < keydown.index("if (VIEW) {")
    section = JS[
        JS.index("const keysToggle = q(") : JS.index("// ---", JS.index("const keysToggle = q("))
    ]
    assert "document.addEventListener('pointerdown', S.onKeysPointer, true)" in section
    assert "path.includes(keysPanel)" in section and "path.includes(keysToggle)" in section
    assert "document.removeEventListener('pointerdown', S.onKeysPointer, true)" in JS
    assert "setStateValue" not in section and "setTriggerValue" not in section
    assert "textContent" in section and "innerHTML" not in section
    assert 'id="sle-keys" role="dialog" aria-label="단축키" tabindex="-1"' in HTML


def test_the_status_line_keeps_values_and_drops_how_to_text() -> None:
    """상태 줄은 값 · 표지만이다 — 빈 선택 안내 · 묶음 설명 · 고정 글 · 붓 설명은 없다. 왼쪽 칸
    「도움말」 묶음도 없다(단축키는 판, 하는 법은 Guide)."""
    status = _status()
    for gone in (
        "단축키는 왼쪽 칸",
        "끌어 옮기고",
        "함께 움직입니다",
        "바둑판에 자동으로",
        "다시 놓입니다",
        "그리지 않고 제 칸",
        "누를 때마다 붙입니다",
        "다른 층으로 보낼 수 있습니다",
        "lockNote",
        "다시 빼면 버림",
    ):
        assert gone not in status, gone
    for value in ("add('선택 '", "X ${item.x} · Y ${item.y}", "add('적용 안 한 변경 '"):
        assert value in status, value
    assert "서식 붓 잠금" in status and "`모듈 ${mods.length}대 · ${cols}×${rows}`" in status
    assert 'data-sec="help"' not in HTML and "sle-help" not in CSS
    # 왼쪽 칸 「선택」 의 빈 줄도 값이다(하는 법 글 없음).
    assert "inspectorName.textContent = '— 고른 것 없음'" in JS and "고르세요(빈 곳을" not in JS
    assert "const GUIDE =" not in JS and "const HINT =" not in JS and "buildHelp" not in JS


def test_the_scroll_lock_marks_a_hidden_unsaved_panel_on_its_button() -> None:
    """고정 중 위 「저장 안 한 배치」 상자가 화면 밖이면 상태 글 대신 「화면 고정」 단추의 점과
    풍선이 말한다(표지 + 풍선 — UI-TXT-04). 보기 · 편집 모두 회차마다 맞춘다."""
    mark = JS[JS.index("  function showLockMark() {") : JS.index("  function alignLock() {")]
    assert "lockDot.hidden = !offScreen" in mark
    assert "Boolean(S.lock && data.pendingSave)" in mark and "S.lockTip" in mark
    assert JS.count("\n  showLockMark()\n") == 1
    assert '<span class="sle-lock-dot" aria-hidden="true" hidden></span>' in HTML
    assert "저장 안 한 배치가 있습니다" not in _status()
