# Purpose: 화면 · 알림 · 복사 글에 그리는 시각의 시각대 한 곳 — 서버 시각대(TZ)에 기대지 않고
# KST 로 옮긴다.

"""사람이 읽는 시각은 한국 시각(KST — +09:00 고정, 일광 절약 시간 없음)이다.

저장 · 서버 로그 · 파일 이름은 UTC(또는 그 자리의 정한 꼴) 그대로이고, 화면 · 알림 · 복사 글에 옮길
때만 여기를 지난다. 「… UTC」 로 적기로 정한 자리(참고 줄 · 앱 밖 화면 바닥 · 시작 실패 줄)는 UTC
그대로다. `datetime.astimezone()`(인자 없음) · `time.localtime` · `time.strftime(꼴)` ·
`datetime.fromtimestamp(초)`(시각대 없음)처럼 서버 시각대를 따르는 변환은 화면 코드에 쓰지 않는다 —
C-DEP 컨테이너의 시각대는 이미지가 정하고(UTC 일 수 있다) 사내 PC 는 KST 라, 같은 Admin Area 에서
같은 일이 9시간 어긋나 보인다. 그물은 `tests/test_server_clock_sites.py`(남은 자리와 까닭) ·
`tests/test_screen_clock_kst.py`(UTC 서버에서 본 대표 자리)다.

표준 라이브러리만 쓴다 — 앱 밖 화면(`auth/page_frame.py`) · 감사 읽기(`audit/read.py`)도 들인다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

KST: Final = timezone(timedelta(hours=9), "KST")


def kst_clock(moment: datetime | float, layout: str) -> str:
    """시각대가 붙은 시각 · UNIX 초 → KST 글(`layout` 은 `strftime` 꼴).

    시각대가 없는 시각은 `ValueError` 다 — 어느 시각대인지 몰라 옮기지 않는다(받은 글을 그대로 두는
    것은 부르는 쪽 몫). 어느 시각대로도 못 옮길 먼 시각은 `OverflowError` · `OSError` 그대로 올린다.
    """
    if isinstance(moment, datetime):
        if moment.utcoffset() is None:
            raise ValueError("시각대가 없는 시각")
        return moment.astimezone(KST).strftime(layout)
    return datetime.fromtimestamp(moment, tz=KST).strftime(layout)
