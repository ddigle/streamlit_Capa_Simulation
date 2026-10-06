# Purpose: 이름 뒤에 붙는 조사(을/를·은/는·으로/로)를 그 이름의 끝소리로 고른다.

"""조사 고르기.

「`E2E 동시 시나리오`을 저장했습니다」·「r2을 저장했습니다」처럼 이름 뒤에 조사를 못박아 둔
문구는 끝소리가 다른 이름에서 틀린다(2026-10-05 E2E). 한글 음절과 숫자는 끝소리를 정확히
안다. 영문 등 읽는 법을 알 수 없는 끝은 `을(를)`·`은(는)`·`(으)로` 로 둔다 — 틀린 조사보다
낫다.

`으로/로` 는 받침 유무만으로 갈리지 않는다. 받침이 없거나 ㄹ 이면 `로`(서울로·r1로), 그 밖의
받침이면 `으로`(부산으로·r3으로)다.
"""

from __future__ import annotations

# 숫자를 한국어로 읽었을 때 끝 글자의 종성 번호(0 은 받침 없음). 영(ㅇ)·일(ㄹ)·삼(ㅁ)·육(ㄱ)·
# 칠(ㄹ)·팔(ㄹ)은 받침이 있고 이·사·오·구는 없다. 끝자리 0 은 영·십·백·천·만 어느 쪽으로 읽어도
# ㄹ 이 아닌 받침이라 같은 답이 된다.
_DIGIT_FINAL = {
    "0": 21,
    "1": 8,
    "2": 0,
    "3": 16,
    "4": 0,
    "5": 0,
    "6": 1,
    "7": 8,
    "8": 8,
    "9": 0,
}
_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3
_FINALS = 28
_FINAL_RIEUL = 8
# 이름을 감싼 따옴표·괄호·Markdown 굵게 표시는 읽지 않으므로 끝소리를 볼 때 건너뛴다.
_SKIPPED_TAIL = "\"'`)]」』*"


def _final_consonant(word: str) -> int | None:
    """끝소리의 종성 번호. 받침이 없으면 0, 읽는 법을 알 수 없으면 `None` 이다."""
    for char in reversed(word.strip()):
        if char.isspace() or char in _SKIPPED_TAIL:
            continue
        if _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST:
            return (ord(char) - _HANGUL_FIRST) % _FINALS
        return _DIGIT_FINAL.get(char)
    return None


def object_particle(word: str) -> str:
    """`word` 뒤에 붙일 목적격 조사. 끝 글자가 한글·숫자가 아니면 `을(를)` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "을(를)"
    return "을" if final else "를"


def topic_particle(word: str) -> str:
    """`word` 뒤에 붙일 보조사 `은/는`. 끝 글자가 한글·숫자가 아니면 `은(는)` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "은(는)"
    return "은" if final else "는"


def direction_particle(word: str) -> str:
    """`word` 뒤에 붙일 부사격 조사 `으로/로`. 끝 글자가 한글·숫자가 아니면 `(으)로` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "(으)로"
    return "로" if final in (0, _FINAL_RIEUL) else "으로"


def with_object_particle(word: str) -> str:
    """`word` 와 그 뒤의 목적격 조사를 붙여 돌려준다."""
    return f"{word}{object_particle(word)}"


def with_topic_particle(word: str) -> str:
    """`word` 와 그 뒤의 `은/는` 을 붙여 돌려준다."""
    return f"{word}{topic_particle(word)}"


def with_direction_particle(word: str) -> str:
    """`word` 와 그 뒤의 `으로/로` 를 붙여 돌려준다."""
    return f"{word}{direction_particle(word)}"
