# Purpose: 코어 화면의 처리 못 한 오류를 참고 번호와 함께 프로세스 안에 적고 읽는다(UI 없음).

"""코어 화면 실패 기록(2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p2-rare — 처리 못 한 오류).

코어 화면 감싸기(`components/page_failure_card.run_core_page`)가 적고, 관리자 상태 알림 `AD-22`
(`page_failure_card.render_page_failure_alert` — `app.py`)가 읽는다. 오류가 난 탭은 관리자의 탭이
아니어서 알림은 그 세션이 아니라 프로세스 기록에서 낸다.

- **메시지 본문은 적지 않는다** — 시각 · 화면 이름 · 주소 · 예외 형식 이름 · 참고 번호만. 실데이터
  값이 기록과 알림에 남지 않게 한다(모듈 기록 `module_failures` 와 같은 꼴). 원문은 그 화면의 카드
  「관리자용 진단」 과 서버 로그(참고 번호로 찾는다)에 있다.
- 프로세스 전역 줄 하나에 `threading.Lock` 을 건다(스레드를 세우지 않는다). 최근 `RECENT_LIMIT` 건만
  남기고, 재시작하면 비어 있다.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Final

RECENT_LIMIT: Final = 20


@dataclass(frozen=True)
class PageFailure:
    """코어 화면 실패 하나 — 사용자가 문의할 때 대는 참고 번호(`ref`)로 서버 로그와 잇는다."""

    ref: str
    # "HH:MM:SS"(서버 시각).
    at: str
    # 화면 이름 · 주소(알림 「그 화면으로」).
    page: str
    href: str
    # 예외 형식 이름.
    kind: str


_LOCK = threading.Lock()
_RECENT: deque[PageFailure] = deque(maxlen=RECENT_LIMIT)


def new_ref() -> str:
    """참고 번호 — 8자리 대문자 16진(말로 옮기기 쉽게)."""
    return uuid.uuid4().hex[:8].upper()


def record_failure(*, page: str, href: str, kind: str) -> PageFailure:
    """실패 하나를 적고 돌려준다."""
    failure = PageFailure(
        ref=new_ref(), at=time.strftime("%H:%M:%S"), page=page, href=href, kind=kind
    )
    with _LOCK:
        _RECENT.append(failure)
    return failure


def recent_failures() -> tuple[PageFailure, ...]:
    """최근 실패(오래된 것부터). 읽기 전용 사본이다."""
    with _LOCK:
        return tuple(_RECENT)


def forget_failures() -> None:
    """기록을 비운다(시험)."""
    with _LOCK:
        _RECENT.clear()
