# Purpose: 이름 뒤 목적격 조사(을/를)를 끝소리로 고르는 규칙을 고정한다.

import pytest

from capa_simulation.services.korean_particle import object_particle, with_object_particle


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


def test_with_object_particle_joins_the_word_and_the_particle() -> None:
    assert with_object_particle("r2") == "r2를"
