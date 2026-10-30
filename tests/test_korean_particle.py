# Purpose: 이름 뒤 조사(을/를·은/는·이/가·으로/로)를 끝소리로 고르는 규칙을 고정한다.

import pytest

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.services.korean_particle import (
    direction_particle,
    object_particle,
    subject_particle,
    topic_particle,
    with_direction_particle,
    with_object_particle,
    with_subject_particle,
    with_topic_particle,
)


@pytest.mark.parametrize(
    ("word", "particle"),
    [
        ("E2E 동시 시나리오", "를"),
        ("E2E-D 복제 시나리오", "를"),
        ("복제본", "을"),
        ("2", "를"),
        ("4", "를"),
        ("7", "을"),
        ("10", "을"),
        ("「주요 공정」", "을"),
        ("85%", "를"),
        ("Customer", "을(를)"),
        ("", "을(를)"),
    ],
)
def test_the_particle_follows_the_final_sound(word: str, particle: str) -> None:
    """받침 없는 이름 뒤 「을」이 틀리던 문구(2026-10-05 E2E). 읽는 법을 모르면 `을(를)` 이다."""
    assert object_particle(word) == particle


@pytest.mark.parametrize(
    ("word", "particle"),
    [
        ("시뮬레이션", "은"),
        ("가용설비", "는"),
        ("이름 바꾼 시나리오", "는"),
        ("서울", "은"),
        ("202609281727", "은"),
        ("202609281729", "는"),
        ("seq 10", "은"),
        ("「Wire Bond」", "은(는)"),
        ("**복제본**", "은"),
        ("WB\\(2\\)", "는"),
        ("「WB\\(2\\)」", "는"),
        ("Wire\\~Bond\\~", "은(는)"),
        ("", "은(는)"),
    ],
)
def test_the_topic_particle_follows_the_final_sound(word: str, particle: str) -> None:
    """`은/는` 도 받침 유무로 갈린다. 읽는 법을 모르면 `은(는)` 이다."""
    assert topic_particle(word) == particle


@pytest.mark.parametrize(
    ("word", "particle"),
    [
        ("시나리오", "로"),
        ("서울", "로"),
        ("부산", "으로"),
        ("seq 1", "로"),
        ("seq 7", "로"),
        ("seq 8", "로"),
        ("seq 3", "으로"),
        ("seq 6", "으로"),
        ("seq 10", "으로"),
        ("900", "으로"),
        ("1.5", "로"),
        ("backup.duckdb", "(으)로"),
        ("", "(으)로"),
    ],
)
def test_the_direction_particle_treats_rieul_like_no_final(word: str, particle: str) -> None:
    """`으로/로` 는 받침이 없거나 ㄹ 이면 `로` 다 — 받침 유무만 보면 「서울으로」가 된다."""
    assert direction_particle(word) == particle


@pytest.mark.parametrize(
    ("word", "particle"),
    [
        ("설비 마스터", "가"),
        ("공정", "이"),
        ("4", "가"),
        ("27-06", "이"),
        ("`numpy`", "이(가)"),
        ("시뮬레이션 DB", "가"),
        ("**공정 A1**", "이"),
        ("", "이(가)"),
    ],
)
def test_the_subject_particle_follows_the_final_sound(word: str, particle: str) -> None:
    """`이/가` 도 받침 유무로 갈린다(2026-10-25 E2E 「27-06 가」). 읽는 법을 모르면 `이(가)` 다."""
    assert subject_particle(word) == particle


def test_escaped_markdown_reads_the_same_final_as_the_plain_name() -> None:
    """`literal_markdown` 이 escape 한 이름의 `\\` 도 건너뛴다 — 감싸는 차례와 상관없이 같다."""
    for name in ("WB(2)", "A~B~C", "$x$", "공정*", "Die Attach_1"):
        escaped = literal_markdown(name)
        assert topic_particle(escaped) == topic_particle(name), (name, escaped)
        assert object_particle(f"「{escaped}」") == object_particle(name), (name, escaped)


@pytest.mark.parametrize(
    ("word", "topic", "direction"),
    [
        ("C2 2F", "는", "로"),
        ("Xsize", "는", "로"),
        ("「투자Capa」", "는", "로"),
        ("DuckDB", "는", "로"),
        ("Kea", "는", "로"),
        ("Staff", "은(는)", "(으)로"),
    ],
)
def test_fixed_vocabulary_latin_tails_are_read(word: str, topic: str, direction: str) -> None:
    """층 이름의 `F`·`DB`·`size`·`Capa`·`Kea` 는 읽는다(「C2 2F는」·「Xsize를」). 대소문자도 그대로
    견준다(「Staff」 의 `ff` 는 `F` 가 아니다)."""
    assert topic_particle(word) == topic
    assert direction_particle(word) == direction


@pytest.mark.parametrize(
    ("word", "particles"),
    [
        # 한 글자 끝 — 알파벳 이름으로 읽는다(비·에이치·에이·엑스·지).
        ("셋업 B", ("를", "는", "가", "로")),
        ("「셋업 B」", ("를", "는", "가", "로")),
        ("HBM가상 · 2H", ("를", "는", "가", "로")),
        ("DEL-A", ("를", "는", "가", "로")),
        ("E2E~가정~B", ("를", "는", "가", "로")),
        ("EQ-X", ("를", "는", "가", "로")),
        ("셋업 b", ("를", "는", "가", "로")),
        # 받침이 있는 이름은 엘·엠·엔·알 넷 — 엘·알은 ㄹ 이라 「로」, 엠·엔은 「으로」.
        ("가정 L", ("을", "은", "이", "로")),
        ("가정 R", ("을", "은", "이", "로")),
        ("가정 M", ("을", "은", "이", "으로")),
        ("가정 N", ("을", "은", "이", "으로")),
        # 대문자 두세 글자 — 약어로 보고 끝 글자를 읽는다.
        ("HBM", ("을", "은", "이", "으로")),
        ("EDP", ("를", "는", "가", "로")),
        ("HBM·EDP", ("를", "는", "가", "로")),
        # 낱말일 수 있는 끝은 그대로 갈래 꼴이다(유저·본딩을 글자로 읽지 않는다).
        ("USER", ("을(를)", "은(는)", "이(가)", "(으)로")),
        ("TC Bonding", ("을(를)", "은(는)", "이(가)", "(으)로")),
        ("Tc", ("을(를)", "은(는)", "이(가)", "(으)로")),
    ],
)
def test_a_lone_latin_letter_or_a_short_capital_tail_is_read_by_its_letter_name(
    word: str, particles: tuple[str, str, str, str]
) -> None:
    """「「셋업 B」(으)로 했습니다」·「프리셋 「DEL-A」을(를) 저장했습니다」 — 라틴 글자로 끝나는
    이름은 갈래 꼴이었다(E2E 1~3회차). 끝이 한 글자이거나 대문자 두세 글자면 알파벳 이름으로
    읽는다."""
    assert (
        object_particle(word),
        topic_particle(word),
        subject_particle(word),
        direction_particle(word),
    ) == particles


def test_percent_has_no_final_consonant() -> None:
    """`%` 는 퍼센트·프로 어느 쪽으로 읽어도 받침이 없다(「85% 로」 → 「85%로」)."""
    assert with_direction_particle("85%") == "85%로"
    assert with_object_particle("100%") == "100%를"
    assert with_topic_particle("0.5%") == "0.5%는"
    assert with_subject_particle("12%") == "12%가"


def test_with_particle_helpers_join_the_word_and_the_particle() -> None:
    assert with_object_particle("r2") == "r2를"
    assert with_topic_particle("가용설비") == "가용설비는"
    assert with_subject_particle("r3") == "r3이"
    assert with_direction_particle("seq 1") == "seq 1로"
