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
