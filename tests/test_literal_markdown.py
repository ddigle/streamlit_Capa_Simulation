# Purpose: 마크다운 자리에 싣는 사람 글이 ASCII 구두점만 escape 되고 나머지는 그대로인지 검증한다.

import string

from capa_simulation.components.literal_markdown import literal_markdown


def test_every_ascii_punctuation_gets_a_backslash() -> None:
    escaped = literal_markdown(string.punctuation)

    assert escaped == "".join(f"\\{char}" for char in string.punctuation)


def test_markdown_syntax_in_a_title_becomes_plain_characters() -> None:
    assert literal_markdown("1~3월 $1.2 ![x](u) *익명*") == r"1\~3월 \$1\.2 \!\[x\]\(u\) \*익명\*"


def test_hangul_digits_spaces_and_non_ascii_marks_stay_as_they_are() -> None:
    text = "홍길동 제조기술 2026 · → ～ 「확인」"

    assert literal_markdown(text) == text


def test_non_strings_are_written_as_text_first() -> None:
    assert literal_markdown(1.5) == r"1\.5"


def _badge(label: str) -> None:
    import streamlit as st

    st.badge(label)


def test_a_badge_label_shows_brackets_without_a_backslash() -> None:
    """`st.badge` 는 라벨의 `[`·`]` 를 스스로 막는다 — `literal_markdown` 으로 감싸면 `\\[` 가
    한 번 더 막혀 「설비 시나리오 · \\[가정\\] 10월 증설안」 으로 역슬래시가 보였다(2026-10-26
    E2E). 다른 구두점은 그대로 막는다(`*증설*` 이 기울임이 되지 않게)."""
    from streamlit.testing.v1 import AppTest

    from capa_simulation.components.literal_markdown import literal_badge

    name = "[가정] 10월 *증설*안"
    assert literal_badge(name) == r"[가정] 10월 \*증설\*안"
    app = AppTest.from_function(_badge, args=(literal_badge(name),)).run()

    body = app.markdown[0].value
    assert body == r":blue-badge[\[가정\] 10월 \*증설\*안]", body


def test_no_badge_label_wraps_a_name_in_literal_markdown() -> None:
    """`st.badge(...)` 라벨 안에서 `literal_markdown(…)` 을 부르면 `[`·`]` 가 두 번 막힌다 — 그
    자리는 `literal_badge` 를 쓴다."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    found = []
    for path in [*(root / "src").rglob("*.py"), *(root / "app_pages").glob("*.py")]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "badge"
                and node.args
            ):
                continue
            calls = [
                inner.func.id
                for inner in ast.walk(node.args[0])
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            ]
            if "literal_markdown" in calls:
                found.append(f"{path.relative_to(root)}:{node.lineno}")

    assert not found, found
