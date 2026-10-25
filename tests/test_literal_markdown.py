# Purpose: 마크다운 자리에 싣는 사람 글·이름·예외 글이 막는 길을 지나 글자 그대로 남는지 검증한다.

import string

import duckdb
import pytest

from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
    quoted,
)
from capa_simulation.page_bootstrap import bootstrap_error_message
from capa_simulation.services.korean_particle import object_particle


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


def test_markdown_safe_tildes_blocks_only_bare_tildes_once() -> None:
    """물결표만 막고 굵게·코드는 산다. 이미 막힌 `\\~` 는 다시 막지 않는다 — 막은 글을 한 번 더
    감싸도 같다."""
    once = markdown_safe_tildes("**동** C1~C5 · `1F~6F`")

    assert once == r"**동** C1\~C5 · `1F\~6F`"
    assert markdown_safe_tildes(once) == once
    assert markdown_safe_tildes(literal_markdown("A~B~C")) == literal_markdown("A~B~C")


def test_quoted_wraps_the_name_in_corner_brackets_and_escapes_it() -> None:
    assert quoted("E2E~가정~A") == r"「E2E\~가정\~A」"
    assert quoted("10~12월 증설") == r"「10\~12월 증설」"
    assert quoted("셋업 실무") == "「셋업 실무」"


@pytest.mark.parametrize("missing", [None, ""])
def test_quoted_without_a_name_returns_the_stand_in(missing: str | None) -> None:
    assert quoted(missing) == "「」"
    assert quoted(missing, empty="이 설비 시나리오") == "이 설비 시나리오"


def test_a_particle_picked_from_the_quoted_name_matches_the_raw_name() -> None:
    """끝이 구두점이 아닌 이름은 감싼 글로 골라도 이름으로 고른 조사와 같다(`」` 를 건너뛴다)."""
    for name in ("E2E~가정~A", "10~12월 증설", "운영 일정", "r3"):
        assert object_particle(quoted(name)) == object_particle(name), name


def test_a_service_error_naming_a_tilde_name_reaches_markdown_with_the_tildes_blocked() -> None:
    """저장소·서비스 예외 글(ValueError)은 사람이 지은 이름을 날로 담는다 — 마크다운 자리로 가는
    기본 갈래는 물결표를 막는다. 마크다운이 아닌 자리(콘솔)는 `markdown=False` 로 원문을 받는다."""
    error = ValueError("설비 시나리오 「E2E~가정~A」 가 먼저 바뀌었습니다 — 범위 0 ~ 1")

    assert bootstrap_error_message(error) == (
        r"설비 시나리오 「E2E\~가정\~A」 가 먼저 바뀌었습니다 — 범위 0 \~ 1"
    )
    assert bootstrap_error_message(error, markdown=False) == str(error)
    # 이미 막힌 글(quoted 를 지난 이름)을 담은 예외는 그대로다.
    assert bootstrap_error_message(ValueError(f"{quoted('A~B')} 없음")) == r"「A\~B」 없음"
    assert bootstrap_error_message(ValueError("한국어 문장")) == "한국어 문장"


def test_the_duckdb_branch_is_the_same_with_or_without_markdown() -> None:
    """DuckDB 갈래는 앱이 지은 안내(파일 경로·원문 코드)라 `markdown` 과 상관없이 같다."""
    error = duckdb.IOException('IO Error: Cannot open file "x~y.duckdb": Permission denied')

    shown = bootstrap_error_message(error)

    assert shown == bootstrap_error_message(error, markdown=False)
    assert shown.startswith("데이터베이스를 열지 못했습니다.")
