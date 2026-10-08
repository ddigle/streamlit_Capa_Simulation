# Purpose: 필요단축일정 호기 타임라인의 달 축·위치·격자선·날짜 글자를 두 화면 조각에 준다.

"""필요단축일정 호기 타임라인의 축 계산.

공정 카드의 한 줄 호기 타임라인(`required_shortening_panel`)과 진척 비교의 두 줄
타임라인(`shortening_progress_panel`)이 **같은 축**을 쓴다 — 고른 달의 첫날부터 마지막 달의 다음
달 첫날까지, 위치는 백분율이다. 한쪽만 고치면 두 화면의 같은 날이 다른 자리에 선다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

__all__ = ["month_day", "timeline_axis", "timeline_grid_lines", "timeline_position"]


def timeline_axis(months: Sequence[int]) -> tuple[date, date]:
    """`months`(`YYYYMM`, 차례대로)의 축 — 첫 달 1일과 마지막 달 다음 달 1일."""
    first = date(months[0] // 100, months[0] % 100, 1)
    year, month = divmod(months[-1], 100)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, following


def timeline_position(day: date, axis: tuple[date, date]) -> float:
    """축 위 백분율. 축 밖의 날은 양 끝(0·100)으로 자른다."""
    span = (axis[1] - axis[0]).days
    return min(100.0, max(0.0, (day - axis[0]).days / span * 100))


def timeline_grid_lines(months: Sequence[int], axis: tuple[date, date]) -> str:
    """달 경계 세로선(첫 달 앞은 긋지 않는다)."""
    lines = []
    for month in months[1:]:
        start = date(month // 100, month % 100, 1)
        lines.append(
            f'<span class="shk-grid-line" style="left:{timeline_position(start, axis):.3f}%">'
            "</span>"
        )
    return "".join(lines)


def month_day(day: date, *, today: date) -> str:
    """호기 줄의 날짜. 올해면 `MM.DD`, 해가 다르면 `YY.MM.DD` 다(2026-10-08 사용자 결정 — 해를 넘는
    단축이 「02.25 → 10.08」 처럼 거꾸로 읽혔다). 전체 날짜는 줄의 풍선(`title`)에도 있다."""
    return f"{day:%m.%d}" if day.year == today.year else f"{day:%y.%m.%d}"
