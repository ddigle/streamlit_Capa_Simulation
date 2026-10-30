# Purpose: 이름 뒤에 붙는 조사(을/를·은/는·이/가·으로/로)를 그 이름의 끝소리로 고른다.

"""조사 고르기.

「`E2E 동시 시나리오`을 저장했습니다」·「r2을 저장했습니다」처럼 이름 뒤에 조사를 못박아 둔
문구는 끝소리가 다른 이름에서 틀린다(2026-10-05 E2E). 한글 음절과 숫자·`%`(퍼센트)는 끝소리를
정확히 안다. 영문 끝은 두 가지를 읽는다.

- **글자로 읽는 끝** — 끝의 영문이 한 글자(「셋업 B」·「2H」·「DEL-A」·「EQ-X」)이거나 대문자 두세
  글자(「HBM」·「EDP」)이면 알파벳 이름(비·에이치·에이·엑스·엠·피)으로 읽는다. 받침이 있는 이름은
  엘·엠·엔·알 넷뿐이다. 한 글자는 낱말일 수 없고, 두세 대문자는 이 앱에서 거의 늘 약어라
  낱말로 읽어도 끝소리가 같은 일이 많다(「RAM」 램·엠). 넷 이상(「USER」 유저·알)은 낱말과
  갈리지 않아 읽지 않는다.
- **고정 어휘의 끝** — 이 앱이 늘 끼우는 어휘의 영문 끝(층 이름 「C1 1F」의 `F`·「DuckDB」의 `DB`·
  「Xsize」의 `size`·「투자Capa」의 `Capa`·수량 단위 `Kea`)은 읽기를 표(`_LATIN_TAIL_FINAL`)로 둔다.

그 밖의 끝(「Bonding」·「Customer」 같은 영문 낱말)은 읽는 법을 알 수 없어 `을(를)`·`은(는)`·
`이(가)`·`(으)로` 로 둔다 — 틀린 조사보다 낫다.

`으로/로` 는 받침 유무만으로 갈리지 않는다. 받침이 없거나 ㄹ 이면 `로`(서울로·r1로), 그 밖의
받침이면 `으로`(부산으로·r3으로)다.

f-string·`str.format`·JS 템플릿에 끼운 값 바로 뒤에 조사를 못박지 않고 늘 이 모듈(JS 는
`space_layout_editor_assets/editor.js` 의 같은 표 `withJosa`)로 고른다 —
`tests/test_particle_sites.py` 가 지킨다(AGENTS 8장).
"""

from __future__ import annotations

# 한글이 아닌 끝 글자 가운데 읽는 법을 아는 것의 종성 번호(0 은 받침 없음). 숫자는 한국어로 읽었을
# 때 끝 글자다 — 영(ㅇ)·일(ㄹ)·삼(ㅁ)·육(ㄱ)·칠(ㄹ)·팔(ㄹ)은 받침이 있고 이·사·오·구는 없다. 끝자리
# 0 은 영·십·백·천·만 어느 쪽으로 읽어도 ㄹ 이 아닌 받침이라 같은 답이 된다. `%` 는 퍼센트·프로
# 어느 쪽으로 읽어도 받침이 없다.
_KNOWN_FINAL = {
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
    "%": 0,
}
# 고정 어휘의 영문 끝 → 종성 번호(대소문자 그대로 견준다). 에프·디비·사이즈·카파·케이이에이 모두
# 받침이 없다. 글자로 읽는 끝(아래)보다 먼저 본다 — 「DuckDB」 는 소문자가 섞여 글자로 읽지 않는다.
_LATIN_TAIL_FINAL = {
    "F": 0,
    "DB": 0,
    "size": 0,
    "Capa": 0,
    "Kea": 0,
}
# 알파벳 이름의 종성 번호. 받침이 있는 이름은 엘(ㄹ)·엠(ㅁ)·엔(ㄴ)·알(ㄹ) 넷이고 나머지(에이·비·씨·
# 디·이·에프·지·에이치·아이·제이·케이·오·피·큐·에스·티·유·브이·더블유·엑스·와이·제트)는 받침이 없다.
_LETTER_NAME_FINAL = {"L": 8, "M": 16, "N": 4, "R": 8}
_ASCII_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
# 대문자 끝을 글자로 읽는 가장 긴 길이 — 넷부터는 낱말(「USER」·「PLAN」)과 갈리지 않는다.
_SPELLED_CAPITALS = 3
_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3
_FINALS = 28
_FINAL_RIEUL = 8
# 이름을 감싼 따옴표·괄호·Markdown 굵게 표시는 읽지 않으므로 끝소리를 볼 때 건너뛴다. 백슬래시도
# 건너뛴다 — `literal_markdown` 이 escape 한 이름(「WB\(2\)」)도 escape 하기 전과 같은
# 끝소리를 읽는다.
_SKIPPED_TAIL = "\"'`)]」』*\\"


def _final_consonant(word: str) -> int | None:
    """끝소리의 종성 번호. 받침이 없으면 0, 읽는 법을 알 수 없으면 `None` 이다."""
    text = word.strip()
    end = len(text)
    while end and (text[end - 1].isspace() or text[end - 1] in _SKIPPED_TAIL):
        end -= 1
    if not end:
        return None
    char = text[end - 1]
    if _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST:
        return (ord(char) - _HANGUL_FIRST) % _FINALS
    if char in _KNOWN_FINAL:
        return _KNOWN_FINAL[char]
    head = text[:end]
    known = next((final for tail, final in _LATIN_TAIL_FINAL.items() if head.endswith(tail)), None)
    if known is not None:
        return known
    return _spelled_final(head)


def _spelled_final(head: str) -> int | None:
    """끝의 영문을 글자로 읽을 때의 종성 번호 — 한 글자이거나 대문자 두세 글자일 때만.

    「셋업 B」 → 비(받침 없음)·「HBM」 → 엠(ㅁ)·「가정 R」 → 알(ㄹ). 그 밖(「Bonding」·「USER」)은
    `None` 이다.
    """
    letters = head[len(head.rstrip(_ASCII_LETTERS)) :]
    if not letters:
        return None
    if len(letters) == 1 or (len(letters) <= _SPELLED_CAPITALS and letters.isupper()):
        return _LETTER_NAME_FINAL.get(letters[-1].upper(), 0)
    return None


def object_particle(word: str) -> str:
    """`word` 뒤에 붙일 목적격 조사. 끝 글자를 읽지 못하면 `을(를)` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "을(를)"
    return "을" if final else "를"


def topic_particle(word: str) -> str:
    """`word` 뒤에 붙일 보조사 `은/는`. 끝 글자를 읽지 못하면 `은(는)` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "은(는)"
    return "은" if final else "는"


def subject_particle(word: str) -> str:
    """`word` 뒤에 붙일 주격 조사 `이/가`. 끝 글자를 읽지 못하면 `이(가)` 이다."""
    final = _final_consonant(word)
    if final is None:
        return "이(가)"
    return "이" if final else "가"


def direction_particle(word: str) -> str:
    """`word` 뒤에 붙일 부사격 조사 `으로/로`. 끝 글자를 읽지 못하면 `(으)로` 이다."""
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


def with_subject_particle(word: str) -> str:
    """`word` 와 그 뒤의 `이/가` 를 붙여 돌려준다."""
    return f"{word}{subject_particle(word)}"


def with_direction_particle(word: str) -> str:
    """`word` 와 그 뒤의 `으로/로` 를 붙여 돌려준다."""
    return f"{word}{direction_particle(word)}"
