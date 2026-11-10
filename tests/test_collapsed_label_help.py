# Purpose: 라벨을 숨긴 칸이 위젯 풍선(help)을 들지 않고 그 뜻을 줄 끝 ⓘ 하나에 두는지 본다.

"""숨긴 라벨 칸의 뜻은 줄 끝 ⓘ 하나다(설계 규칙 UI-TXT-02 · UI-LAY-13 — 2026-11-09 상단 정리 통합).

`label_visibility="collapsed"` 는 라벨 줄을 통째로 걷는다 — Streamlit 1.63 은 위젯 풍선(ⓘ)을
그 라벨 줄 안에 그리므로 같은 칸의 `help=` 는 화면 어디에도 서지 않는다(뜻이 소리 없이
사라진다). 그래서 이름 줄을 걷은 칸의 뜻은 그 줄 끝 빈 캡션 풍선(`st.caption("", help=…)`)이나
그 줄 제목 풍선 하나가 말하고, 라벨 글은 접근성 이름으로만 남긴다. 화면 코드 전체에서
`collapsed` 와 `help=` 를 함께 준 부름을 찾는다.

남길 자리는 `KEPT` 에 까닭과 함께 적는다 — 지금은 없다. 목록 밖에서 새로 생기면 실패한다.
"""

from __future__ import annotations

import ast

from source_sites import screen_calls, screen_files

KEPT: dict[tuple[str, str], str] = {}


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _collapsed_with_help() -> set[tuple[str, str]]:
    found = set()
    for path, outer, _, _, call in screen_calls(screen_files()):
        hidden = _keyword(call, "label_visibility")
        if not (isinstance(hidden, ast.Constant) and hidden.value == "collapsed"):
            continue
        help_text = _keyword(call, "help")
        if help_text is None or (isinstance(help_text, ast.Constant) and help_text.value is None):
            continue
        found.add((path, outer))
    return found


def test_a_collapsed_label_carries_no_widget_help() -> None:
    wrong = _collapsed_with_help() - set(KEPT)
    assert not wrong, sorted(wrong)


def test_the_kept_sites_still_carry_the_hidden_help() -> None:
    """남긴 자리를 고치면(뜻을 줄 끝 ⓘ · Guide 로 옮기면) 목록에서도 뺀다."""
    assert set(KEPT) <= _collapsed_with_help(), set(KEPT) - _collapsed_with_help()
