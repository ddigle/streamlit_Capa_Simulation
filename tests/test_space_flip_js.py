# Purpose: Space 편집기 돌리기·뒤집기 줄과 Shift+H/V 키 · 여럿 한 번에 뒤집기를 검사한다.

"""2026-11-04 Space 결정 보드 답 — 「도형 반전 기능도 추가하자」.

뒤집기는 이미 있었지만(베이 · 비대칭 도형의 선택 칸 맨 끝 — 빗금 밑) 찾기 어려웠다. 그래서

- 이름표 칸 바로 밑 한 줄 「돌리기·뒤집기」(`.sle-turns`)에 `90° 돌리기` 곁으로 `좌우 뒤집기` ·
  `상하 뒤집기` 를 둔다 — 고른 것 가운데 뒤집을 것(베이 · ㄴ자 · ㄷ자 · 삼각형 · 블록 화살표)이
  하나라도 있으면 선다(여럿 골라도). 대칭 도형만이면 숨긴다(돌리기도).
- 키는 Shift+H(좌우) · Shift+V(상하)다(`// <flip-key>` `flipKeyOf` — 수정 키는 Shift 하나만, 글쇠
  자리 code, IME 조합 중은 비킴). 서식 키(Alt+Shift · Ctrl+Shift+C/V) · 요소 복사(Ctrl+C/V)와
  겹치지 않는다. 뒤집을 것이 없으면 키를 막지 않는다.
- 고른 것 모두를 한 번에 뒤집고 되돌리기 한 번(`flipMarks`). 뒤집기는 서식이 아니다(서식 붓이
  옮기지 않는다).

키 판정은 node 로 떼어 돌리고(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`) 배선은 자산 글자로 붙잡는다. 실제 동작은 브라우저로 본다.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_FLIP = re.compile(r"// <flip-key>\n(?P<body>.*?)\n\s*// </flip-key>", re.S)
_FORMAT = re.compile(r"// <format-key>\n(?P<body>.*?)\n\s*// </format-key>", re.S)
_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
%s
process.stdout.write(JSON.stringify({
  flips: input.events.map((event) => flipKeyOf(event)),
  formats: input.events.map((event) => formatKeyOf(event)),
}))
"""


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _between(start: str, end: str) -> str:
    begin = JS.index(start)
    return JS[begin : JS.index(end, begin)]


def _key(
    key: str,
    code: str,
    *,
    ctrl: bool = False,
    meta: bool = False,
    alt: bool = False,
    shift: bool = True,
    composing: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "code": code,
        "ctrlKey": ctrl,
        "metaKey": meta,
        "altKey": alt,
        "shiftKey": shift,
        "isComposing": composing,
    }


def _run(events: list[dict[str, Any]]) -> dict[str, list[str | None]]:
    out: dict[str, list[str | None]] = _node(
        _RUNNER % (_block(_FLIP), _block(_FORMAT)), {"events": events}
    )
    return out


_CASES: list[tuple[str, dict[str, Any], str | None]] = [
    ("Shift+H", _key("H", "KeyH"), "h"),
    ("Shift+V", _key("V", "KeyV"), "v"),
    # 한글 자판(조합 아님)은 key 가 자모다 — 글쇠 자리로 잡는다.
    ("한글 자판 Shift+ㅗ", _key("ㅗ", "KeyH"), "h"),
    ("한글 자판 Shift+ㅍ", _key("ㅍ", "KeyV"), "v"),
    # 글쇠 자리가 H·V 가 아닌 자판(드보락 등)은 key 로.
    ("드보락 Shift+H", _key("H", "KeyJ"), "h"),
    # IME 조합 중은 비킨다.
    ("조합 중 Shift+H", _key("Process", "KeyH", composing=True), None),
    # Shift 하나만 — 서식 붙여넣기(Alt+Shift+V · Ctrl+Shift+V)·Ctrl+Shift+H 는 아니다.
    ("Alt+Shift+V", _key("V", "KeyV", alt=True), None),
    ("Ctrl+Shift+V", _key("V", "KeyV", ctrl=True), None),
    ("⌘+Shift+H", _key("h", "KeyH", meta=True), None),
    ("Shift 없이 H", _key("h", "KeyH", shift=False), None),
    ("Shift+C", _key("C", "KeyC"), None),
]


def test_flip_key_takes_shift_h_and_v_by_key_position_only() -> None:
    got = _run([event for _, event, _ in _CASES])["flips"]
    assert {name: value for (name, _, _), value in zip(_CASES, got, strict=True)} == {
        name: want for name, _, want in _CASES
    }


def test_flip_keys_never_overlap_format_keys_or_element_copy() -> None:
    """수정 키 모든 짝 × 글쇠 넷(H · V · C · X) — 뒤집기 키는 Shift 만일 때 H · V 이고, 그 이벤트는
    서식 키(`formatKeyOf`)도 요소 복사(Ctrl · ⌘ + Shift 없음)도 아니다."""
    events: list[dict[str, Any]] = []
    want: list[str | None] = []
    for ctrl, meta, alt, shift, composing in itertools.product((False, True), repeat=5):
        for letter in ("h", "v", "c", "x"):
            events.append(
                _key(
                    letter.upper(),
                    f"Key{letter.upper()}",
                    ctrl=ctrl,
                    meta=meta,
                    alt=alt,
                    shift=shift,
                    composing=composing,
                )
            )
            only_shift = shift and not (ctrl or meta or alt or composing)
            want.append(letter if letter in "hv" and only_shift else None)
    out = _run(events)
    assert out["flips"] == want
    for event, flip, fmt in zip(events, out["flips"], out["formats"], strict=True):
        if flip is not None:
            assert fmt is None
            assert not (event["ctrlKey"] or event["metaKey"])


def test_the_turns_row_sits_under_the_name_fields_with_rotate_and_both_flips() -> None:
    """「돌리기·뒤집기」 줄은 요소 속성 칸(이름표 · 글자 크기 · 색 …) 바로 밑, 선 · 도형 서식 칸
    앞이다 — 옛 자리(베이는 선 칸 끝, 도형은 빗금 밑 맨 끝)의 뒤집기 단추는 없다. 단추에는 그림과
    키 풍선(Shift+H · Shift+V)이 붙는다."""
    marks = HTML.index('<span class="sle-markprops"')
    turns = HTML.index('<span class="sle-turns" hidden role="group" aria-label="돌리기·뒤집기">')
    lines = HTML.index('<span class="sle-lineprops"')
    shapes = HTML.index('<span class="sle-shapeprops"')
    assert marks < turns < lines < shapes
    row = HTML[turns:lines]
    assert (
        row.index('class="sle-mark-rotate"')
        < row.index('data-flip="h"')
        < row.index('data-flip="v"')
    )
    assert 'aria-keyshortcuts="Shift+H"' in row and 'aria-keyshortcuts="Shift+V"' in row
    assert row.count("<svg") == 2
    for gone in ("sle-bay-flips", "sle-bay-flip", "sle-shape-flips", "sle-shape-flip"):
        assert gone not in HTML and gone not in JS and gone not in CSS, gone
    assert HTML.count('class="sle-mark-rotate"') == 1
    assert ".sle-turns[hidden], .sle-flip[hidden] { display: none !important; }" in CSS


def test_flips_follow_the_selection_and_flip_all_at_once_in_one_undo() -> None:
    """뒤집기 단추는 고른 것 가운데 뒤집을 것(베이 · 비대칭 도형 — 도면에 선 것)이 있을 때만,
    돌리기는 돌릴 수 있는 요소 하나일 때만(대칭 도형은 숨김) 선다. 누르기 · 키 모두 `flipMarks` 한
    길이고 고른 것 모두를 되돌리기 한 번에 뒤집는다(상하 = 180° 돌림 + 좌우)."""
    turns = _between(
        "  function syncTurns(",
        "// ---------------------------------------------------------------- 도형 서식",
    )
    assert "MARK_KINDS[mark.kind].rotatable && (!isShape(mark) || turnsShape(mark))" in turns
    assert "const flips = chosen.some(canFlip)" in turns
    assert "turnsRow.hidden = !rotates && !flips" in turns
    assert "const canFlip = (m) => onCanvas(m) && (isBay(m) || turnsShape(m))" in JS
    flip = _between("  function flipMarks(", "  // 돌리기·뒤집기 줄")
    assert "const list = selectedItems().filter(canFlip)" in flip
    assert "if (!list.length) return false" in flip
    assert flip.count("pushUndo(ops)") == 1 and "return true" in flip
    assert "if (axis === 'v') m.rot = ((m.rot || 0) + 180) % 360" in flip
    assert (
        "for (const button of flipButtons) button.onclick = () => flipMarks(button.dataset.flip)"
        in JS
    )
    assert "syncTurns(chosen, mark)" in _between(
        "  function syncInspector() {", "  function syncLineProps("
    )
    # 예전 「대칭 도형은 돌려도 같습니다」 꺼진 단추 풍선은 없다(숨긴다).
    assert "대칭 도형은 돌려도 같습니다" not in JS


def test_the_keys_flip_after_the_format_keys_and_only_when_something_flips() -> None:
    keys = _between("host.onkeydown = (event) => {", "for (const input of fieldInputs) {")
    edit = keys[keys.index("if (event.key === 'Escape' && S.drag)") :]
    typing = edit.index("if (typing) return")
    fmt = edit.index("if (formatKey === 'v') { event.preventDefault(); pasteFormat(); return }")
    flip = edit.index("const flipKey = flipKeyOf(event)")
    copy = edit.index("if (ctrl && !event.shiftKey && letter === 'c')")
    assert typing < fmt < flip < copy
    assert "if (flipKey) { if (flipMarks(flipKey)) event.preventDefault(); return }" in edit
    # 보기 화면에는 뒤집기 키가 없다(고치는 키가 없다).
    view = keys[: keys.index("if (event.key === 'Escape' && S.drag)")]
    assert "flipKeyOf" not in view


def test_the_help_lists_the_flip_keys_and_the_format_paint_leaves_flips_alone() -> None:
    hint = _between("const HINT = FAB", "const q = (selector)")
    texts = re.findall(r"'([^']*)'", hint)
    assert len(texts) == 2
    assert "Shift+H/V 좌우·상하 뒤집기(비대칭 도형)" in texts[0]
    assert "Shift+H/V 좌우·상하 뒤집기(베이·비대칭 도형)" in texts[1]
    # 서식 붓은 뒤집기를 옮기지 않는다 — 붙이는 모양 값에 flip 이 없다.
    paint = re.search(r"// <format-paint>\n(?P<body>.*?)\n\s*// </format-paint>", JS, re.S)
    assert paint and "flip" not in paint.group("body")
