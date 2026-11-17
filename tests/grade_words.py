# Purpose: 화면 · 문서 글의 「관리자」 가 새 뜻 허용 꼴뿐인지 가르는 그물의 허용 목록.

"""「관리자」 낱말 그물의 허용 목록(2026-11-18 접속 등급 결정 1 — 낱말 셋으로 가름).

지금 앱 글의 옛 뜻 「관리자」(Admin Area 쪽 · 「관리자만 여는 화면」 · 「관리자로」 ·
「관리자(환경변수)」
· 「관리자가 넣음」 등)는 「개발자」 로 바꾸고, 새 「관리자」 는 옛 공식 지정자 뜻으로만 쓴다. 뜻이
뒤집힌 낱말이 남지 않게 **허용 목록 방식**으로 본다 — 「관리자」 가 든 글은 아래 꼴 가운데 하나여야
한다. 그 밖은 실패다. 역할 이름 「앱 관리자」 는 「앱 관리자(개발자)」 로 이어 적고, 앱 밖 사람
「저장소 관리자」 는 그대로다. 「개발자 도구」(Space Guide 의 브라우저 도구) · 「기록 열람」(접속 ·
작업 기록 갈래)은 다른 뜻의 허용 낱말이다(등급 「개발자」 · 「열람」 과 겹치지 않는다).

core 그물(`tests/test_grade_name_net.py`)과 modules_docs 그물(`tests/test_grade_name_net_docs.py`)이
이 한 벌을 같이 쓴다.
"""

from __future__ import annotations

import re
from typing import Final

# 「관리자」 가 들어도 되는 꼴(새 뜻 구절 · 역할 이름 · 앱 밖 사람 · 합성 견본 이름). 긴 것부터
# 지운다.
ALLOWED_MANAGER_PHRASES: Final = (
    "앱 관리자(개발자)",
    "저장소 관리자",
    "열람 · 실무자 · 관리자 · 개발자",
    "열람 · 실무자 · 관리자",
    "실무자 · 관리자 · 개발자",
    "실무자 · 관리자",
    "관리자 · 개발자",
    "관리자부터",
    "관리자 이상",
    "관리자 몫",
    "관리자로 올",
    "관리자까지",
    "관리자 아래",
    "관리자 화면",
    # 합성 견본의 지정자 이름(`scripts/review_sample_story.py` — 공식 지정자 = 새 「관리자」 뜻).
    "DEMO 관리자",
)
# 등급 이름표 자체(낱말 하나 「관리자」)를 둘 수 있는 파일 — 등급 표 · 감사 등급 값 표.
LABEL_TABLE_FILES: Final = (
    "src/capa_simulation/auth/grades.py",
    "src/capa_simulation/audit/events.py",
)
# 다른 뜻의 허용 낱말(등급 낱말과 겹치지 않는다 — 결정 1 의 낱말 주의).
OTHER_MEANINGS: Final = ("개발자 도구", "기록 열람")

_WORD: Final = "관리자"


def stray_manager_words(text: str) -> list[str]:
    """허용 꼴을 지운 뒤에도 남은 「관리자」 의 앞뒤 글(15자씩). 없으면 빈 목록."""
    remaining = text
    for phrase in sorted(ALLOWED_MANAGER_PHRASES, key=len, reverse=True):
        remaining = remaining.replace(phrase, "□" * len(phrase))
    found: list[str] = []
    for match in re.finditer(_WORD, remaining):
        start = max(0, match.start() - 15)
        found.append(text[start : match.end() + 15].replace("\n", " "))
    return found
