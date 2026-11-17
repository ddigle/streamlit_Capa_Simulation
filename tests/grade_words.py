# Purpose: 화면 · 문서 글의 「관리자」 가 새 뜻 허용 꼴뿐인지 가르는 그물의 허용 목록.

"""「관리자」 낱말 그물의 허용 목록(2026-11-18 접속 등급 결정 1 — 낱말 셋으로 가름).

지금 앱 글의 옛 뜻 「관리자」(Admin Area 쪽 · 「관리자만 여는 화면」 · 「관리자로」 ·
「관리자(환경변수)」
· 「관리자가 넣음」 등)는 「개발자」 로 바꾸고, 새 「관리자」 는 옛 공식 지정자 뜻으로만 쓴다. 뜻이
뒤집힌 낱말이 남지 않게 **허용 목록 방식**으로 본다 — 「관리자」 가 든 글은 아래 꼴 가운데 하나여야
한다. 그 밖은 실패다. 「관리자 몫」 처럼 옛 뜻으로도 읽히는 꼴은 같은 문장에 새 뜻 표지(공식 지정 ·
다른 등급 이름 · 「등급」)가 있을 때만 지나간다. 역할 이름 「앱 관리자」 는 「앱 관리자(개발자)」 로
이어 적고, 앱 밖 사람 「저장소 관리자」 는 그대로다. 「개발자 도구」(Space Guide 의 브라우저
도구) · 「기록 열람」(접속 · 작업 기록 갈래)은 다른 뜻의 허용 낱말이다(등급 「개발자」 · 「열람」 과
겹치지 않는다).

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
    # 높은 차례로 센 등급 넷(「통합인증 점검」 의 접속 명단 줄 — `sso_status.access_line`).
    "개발자 n · 관리자 n · 실무자 n · 열람 n",
    "개발자 · 관리자 · 실무자 · 열람",
    "열람 · 실무자 · 관리자",
    "실무자 · 관리자 · 개발자",
    "실무자 · 관리자",
    "관리자 · 개발자",
    "관리자부터",
    "관리자 이상",
    "관리자로 올",
    "관리자 아래 등급",
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

# 문맥이 있어야 새 뜻인 꼴 — 같은 문장(마침표 · 빈 줄 · 목록 머리 · 표 칸으로 가름)에 새 뜻 표지
# (공식 지정 · 다른 등급 이름 · 「등급」)가 있을 때만 지나간다. 옛 뜻 구절(「관리자 몫 알림이 서지
# 않습니다」 — 옛 코드에 실제로 있던 꼴)이 다시 들어와도 잡힌다.
CONTEXT_MANAGER_PHRASES: Final = ("관리자 몫",)
NEW_SENSE_ANCHORS: Final = ("공식 지정", "실무자", "열람", "개발자", "등급")
_SENTENCE_BREAK: Final = re.compile(r"(?<=[.!?。])\s+|\n\s*\n|\n\s*[-*]\s|\|")

_WORD: Final = "관리자"

# 옛 두 등급의 낱말 「일반」(명단 저장 값 `user` 의 옛 화면 이름)이 등급처럼 남지 않게 — 등급
# 자리에 「일반」 이 서는 꼴만 잡는다(일반 설비 · 일반 가용 · 일반 사용자 같은 보통 낱말은
# 지나간다). 등급 넷에는 「일반」 이 없다(신청 = 열람 — 2026-11-18 결정). 옛 기록 표시와 되돌림
# 설명의 옛 「일반」 은 허용.
ALLOWED_OLD_GRADE_PHRASES: Final = ("일반(옛 기록)", "옛 「일반」")
OLD_GRADE_PATTERNS: Final = (
    re.compile(r"일반\s*등급"),
    re.compile(r"·\s*일반\s*(?:[0-9n]|·)"),
    re.compile(r"등급을\s*일반"),
    re.compile(r"일반으로\s*(?:넣|내리|읽)"),
)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """문장 자리(시작, 끝) — `_SENTENCE_BREAK` 로 가른다."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def _mask_in_context(text: str, remaining: str) -> str:
    """문맥 꼴(`CONTEXT_MANAGER_PHRASES`)을 새 뜻 표지가 있는 문장에서만 지운다(길이는 그대로)."""
    pieces: list[str] = []
    last = 0
    for start, end in _sentence_spans(text):
        pieces.append(remaining[last:start])
        piece = remaining[start:end]
        if any(anchor in text[start:end] for anchor in NEW_SENSE_ANCHORS):
            for phrase in CONTEXT_MANAGER_PHRASES:
                piece = piece.replace(phrase, "□" * len(phrase))
        pieces.append(piece)
        last = end
    pieces.append(remaining[last:])
    return "".join(pieces)


def stray_manager_words(text: str) -> list[str]:
    """허용 꼴을 지운 뒤에도 남은 「관리자」 의 앞뒤 글(15자씩). 없으면 빈 목록."""
    remaining = text
    for phrase in sorted(ALLOWED_MANAGER_PHRASES, key=len, reverse=True):
        remaining = remaining.replace(phrase, "□" * len(phrase))
    remaining = _mask_in_context(text, remaining)
    found: list[str] = []
    for match in re.finditer(_WORD, remaining):
        start = max(0, match.start() - 15)
        found.append(text[start : match.end() + 15].replace("\n", " "))
    return found


def stray_old_grade_words(text: str) -> list[str]:
    """허용 꼴을 지운 뒤에도 등급 자리에 남은 옛 낱말 「일반」 의 앞뒤 글(15자씩)."""
    remaining = text
    for phrase in ALLOWED_OLD_GRADE_PHRASES:
        remaining = remaining.replace(phrase, "□" * len(phrase))
    found: list[str] = []
    for pattern in OLD_GRADE_PATTERNS:
        for match in pattern.finditer(remaining):
            start = max(0, match.start() - 15)
            found.append(text[start : match.end() + 15].replace("\n", " "))
    return found
