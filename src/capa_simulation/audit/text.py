# Purpose: 감사 기록 · 통합인증 로그의 글을 다듬는다 — 줄바꿈 정리 · 길이 상한 · 토큰 꼴 가림.

"""글 다듬기(표준 라이브러리만).

두 갈래다.

- `log_field` — 서버 로그 `sso event=… key=value` 의 한 칸. 공백 · `=` · 제어 문자를 `_` 로 바꿔 한
  줄이 다른 칸으로 읽히지 않게 한다(`auth/runtime.record_event` 가 쓴다).
- `clean_text` — 감사 기록 한 줄(JSON)의 글. 줄바꿈 · 제어 문자를 지우고(공백 하나로) 상한에서
  자른다. 토큰처럼 보이는 글(JWT 세 토막 · 대소문자와 숫자가 섞인 40자 넘는 덩이)은 통째로
  가린다 — 부르는 쪽 실수로 비밀이 기록에 남지 않게 하는 마지막 그물이다.
"""

from __future__ import annotations

import re
from typing import Final

LOG_FIELD_LIMIT: Final = 200
TEXT_LIMIT: Final = 200
LABEL_LIMIT: Final = 60
CLAIMED_LIMIT: Final = 40
REVIEW_LIMIT: Final = 500
REDACTED: Final = "[가림]"

# 줄을 가르는 유니코드 글자(NEL · 줄 구분 · 문단 구분)도 줄바꿈과 같이 다룬다.
_LINE_BREAKS: Final = frozenset("\u0085  ")
_JWT: Final = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_LONG_RUN: Final = re.compile(r"[A-Za-z0-9+/=_-]{40,}")
_SPACES: Final = re.compile(r" {2,}")


def _is_control(character: str) -> bool:
    code = ord(character)
    return code < 32 or code == 127 or 0x80 <= code < 0xA0 or character in _LINE_BREAKS


def log_field(value: object, limit: int = LOG_FIELD_LIMIT) -> str:
    """서버 로그 한 칸 — 공백 · `=` · 제어 문자를 `_` 로 바꾸고 상한에서 자른다. 비면 `-`."""
    text = str(value)
    cleaned = "".join(
        "_" if (ch.isspace() or ch == "=" or ord(ch) < 32 or ord(ch) == 127) else ch for ch in text
    )
    return cleaned[:limit] or "-"


def looks_like_secret(text: str) -> bool:
    """토큰 꼴인가 — JWT 세 토막, 또는 대문자 · 소문자 · 숫자가 모두 든 40자 넘는 덩이.

    해시(16진 소문자) · UUID · 조각 키(소문자 경로)는 대문자가 없어 걸리지 않는다.
    """
    if _JWT.search(text):
        return True
    for match in _LONG_RUN.finditer(text):
        run = match.group(0)
        if (
            any(ch.isupper() for ch in run)
            and any(ch.islower() for ch in run)
            and any(ch.isdigit() for ch in run)
        ):
            return True
    return False


def clean_text(value: object, limit: int = TEXT_LIMIT) -> str:
    """감사 기록 한 칸 — 줄바꿈 · 제어 문자는 공백으로, 겹친 공백은 하나로, 앞뒤 공백은 떼고
    상한에서 자른다. 토큰 꼴이면 `REDACTED`."""
    text = "".join(" " if _is_control(ch) else ch for ch in str(value))
    text = _SPACES.sub(" ", text).strip()
    if looks_like_secret(text):
        return REDACTED
    return text[:limit]
