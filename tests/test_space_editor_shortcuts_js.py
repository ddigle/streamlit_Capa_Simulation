# Purpose: Space 편집기 도구 줄 「단축키」 판의 표 · 화면별 줄과 상태 줄의 값 · 표지 꼴을 검사한다.

"""검수 equip-61 — 상태 줄의 하는 법 글을 걷고, 지금 화면에서 쓸 수 있는 키를 도구 줄 「호기 정보」
옆 「단축키」 판에 「키조합 : 기능」 으로 모았다. 표는 `editor.js` 의 `// <shortcuts>` 구획 한
곳이고 node 로 떼어 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`). 둘레(판 열기 · 닫기)는 자산 글자로 붙잡고 실제 동작은 브라우저로
본다.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
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
    assert "호기 두 번 클릭" not in _keys("vb") and "호기 두 번 클릭" not in _keys("eb")
    assert "PageUp · PageDown" in _keys("vf") and "PageUp · PageDown" not in _keys("ef")
    # 같은 Enter 라도 층 보기는 호기, FAB 보기는 층을 연다.
    assert dict(map(tuple, rows["vf"]))["Enter · Space"] == "초점 둔 호기 고르기"
    assert dict(map(tuple, rows["vb"]))["Enter · Space"] == "초점 둔 층 열기"


@pytest.mark.parametrize(
    ("key", "handled"),
    [
        ("Ctrl+Z", "event.key.toLowerCase() === 'z'"),
        ("Ctrl+A", "event.key.toLowerCase() === 'a'"),
        ("Delete", "event.key === 'Delete'"),
        ("Ctrl+C · Ctrl+V", "letter === 'c'"),
        ("Alt+Shift+C", "formatKey === 'c'"),
        ("Alt+Shift+V", "formatKey === 'v'"),
        ("Shift+H", "flipKeyOf(event)"),
        ("Ctrl+방향키", "setSizes(standing"),
        ("Shift+방향키", "event.shiftKey ? 5 : 1"),
        ("+ · −", "event.key === '-'"),
        ("0", "event.key === '0'"),
        ("Esc", "event.key === 'Escape'"),
        ("Tab · Enter", "focusedItem && (event.key === 'Enter'"),
        ("Ctrl+Enter", "if (ctrl || event.shiftKey) toggleSelected(item)"),
        ("Space+끌기", "S.spaceDown = true"),
    ],
)
def test_the_table_only_names_keys_the_handler_listens_to(key: str, handled: str) -> None:
    """표의 키는 `host.onkeydown` 이 실제로 듣는 키다 — 키를 빼면 표도 함께 고친다."""
    start = JS.index("  host.onkeydown = (event) => {")
    keys = JS[start : JS.index("for (const input of fieldInputs) {", start)]
    assert key in _keys("ef")
    assert handled in keys, key


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
    assert 'class="sle-keys" id="sle-keys" role="dialog" aria-label="단축키" hidden' in body


def test_the_panel_closes_by_esc_outside_press_and_stays_in_the_browser() -> None:
    """Esc 는 판을 먼저 닫는다(고른 것 · 붓은 그대로) · 판 밖 누르기 · 단추 · × 로도 닫힌다. 열림은
    보기 상태라 파이썬으로 보내지 않는다."""
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
    """고정 중 위 「저장 안 한 배치」 상자가 화면 밖이면 상태 글 대신 「고정」 단추의 점과 풍선이
    말한다(표지 + 풍선 — UI-TXT-04). 보기 · 편집 모두 회차마다 맞춘다."""
    mark = JS[JS.index("  function showLockMark() {") : JS.index("  function alignLock() {")]
    assert "lockDot.hidden = !offScreen" in mark
    assert "Boolean(S.lock && data.pendingSave)" in mark and "S.lockTip" in mark
    assert JS.count("\n  showLockMark()\n") == 1
    assert '<span class="sle-lock-dot" aria-hidden="true" hidden></span>' in HTML
    assert "저장 안 한 배치가 있습니다" not in _status()
