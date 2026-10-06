# Purpose: 이름 뒤 조사(을/를·은/는·으로/로)를 끝소리로 고르는 규칙을 고정한다.

import pytest

from capa_simulation.services.korean_particle import (
    direction_particle,
    object_particle,
    topic_particle,
    with_direction_particle,
    with_object_particle,
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


def test_with_particle_helpers_join_the_word_and_the_particle() -> None:
    assert with_object_particle("r2") == "r2를"
    assert with_topic_particle("가용설비") == "가용설비는"
    assert with_direction_particle("seq 1") == "seq 1로"
