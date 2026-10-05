# Purpose: 이름 뒤에 붙는 목적격 조사(을/를)를 그 이름의 끝소리로 고른다.

"""목적격 조사 고르기.

「`E2E 동시 시나리오`을 저장했습니다」·「r2을 저장했습니다」처럼 이름 뒤에 `을` 을 못박아 둔
문구가 받침 없는 이름에서 틀렸다(2026-10-05 E2E). 한글 음절과 숫자는 끝소리를 정확히 안다.
영문 등 읽는 법을 알 수 없는 끝은 `을(를)` 로 둔다 — 틀린 조사보다 낫다.
"""

from __future__ import annotations

# 숫자를 한국어로 읽었을 때 받침이 있는가. 영·일·삼·육·칠·팔은 있고 이·사·오·구는 없다.
_DIGIT_HAS_FINAL = {
    "0": True,
    "1": True,
    "2": False,
    "3": True,
    "4": False,
    "5": False,
    "6": True,
    "7": True,
    "8": True,
    "9": False,
}
_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3
_FINALS = 28


def object_particle(word: str) -> str:
    """`word` 뒤에 붙일 목적격 조사. 끝 글자가 한글·숫자가 아니면 `을(를)` 이다."""
    for char in reversed(word.strip()):
        if char.isspace() or char in "\"'`)]」』":
            continue
        if _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST:
            return "을" if (ord(char) - _HANGUL_FIRST) % _FINALS else "를"
        if char in _DIGIT_HAS_FINAL:
            return "을" if _DIGIT_HAS_FINAL[char] else "를"
        break
    return "을(를)"


def with_object_particle(word: str) -> str:
    """`word` 와 그 뒤의 목적격 조사를 붙여 돌려준다."""
    return f"{word}{object_particle(word)}"
