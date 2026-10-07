# Purpose: 공정별 Cutoff 를 받아 각 월이 실제로 잡는 W/D 날짜 구간을 계산한다.

"""월별 W/D(생산 귀속) 구간.

어떤 달의 생산에 기여하려면 설비가 **그 달보다 Cutoff 만큼 먼저** 있어야 한다.
Cutoff 는 그 공정 이후 입고(마지막 공정)까지의 표준 납기이기 때문이다. 그래서 한 달이
실제로 잡는 날짜 구간은 달력 월이 아니라 그만큼 앞으로 밀린 구간이다.

구간은 **반열린 구간**이다. 앞 경계는 앞 달의 몫이고 뒤 경계가 이 달의 몫이다.

    W/D(M) = ( 전월 말일 - cutoff ,  당월 말일 - cutoff ]

**구간 길이는 언제나 그 달의 달력일수와 같다** — 양 끝이 같은 Cutoff 만큼 밀리기
때문이다. 그래서 한 해의 열두 구간은 빈틈도 겹침도 없이 그 해를 정확히 덮고, 합이
365일(윤년 366일)이 된다. `tests/test_wd_window.py` 가 그것을 지킨다.

예 — Cutoff 15일:

    2026-02  →  (2026-01-16, 2026-02-13]   28일   첫날 2026-01-17
    2026-10  →  (2026-09-15, 2026-10-16]   31일   첫날 2026-09-16

반열린 구간인 것이 숫자를 정한다. 2026-10 에 9월 30일 Qual 이 끝난 설비 한 대는
`10/16 - 9/30 = 16일` 을 기여해 `1대 x 16/31 = 0.52대` 가 된다. 양 끝을 포함으로 세면
17일이 되어 사용자가 준 값과 어긋난다.

**날짜는 시각을 가진 경계다.** 시 단위로 적으면 같은 2026-02 가

    2026-01-16 22:00  <  t  <=  2026-02-13 22:00      (28일)

이고 길이가 날짜 단위와 정확히 같다. 22시는 하루의 경계 시각일 뿐이라 구조가 달라지지
않는다 — 나중에 공정·Bonder 차수별 재공을 상세분류할 때 이 모듈에 오프셋 하나를 더하는
일이 된다. 지금 그 경계를 앞당겨 만들지 않는다.

**가용 시작일 규약**: 어떤 날 `D` 에 일정이 완료되면 그 설비는 `D` 의 경계 시각 이후,
즉 **다음 날부터** 기여한다. 그래서 호출자는 `D + 1일` 을 구간 시작으로 넘긴다.
`services/equipment_availability.py` 의 시점 판정(`Qual일정 <= 기준일`)은 완료 당일을
가용으로 세므로 **그쪽과 하루가 다르다** — 그쪽은 「오늘 쓸 수 있나」를 묻고 여기는
「이 달 생산에 며칠 보탰나」를 묻는다. **반출·이설로 가용을 잃는 날은 예외다** — 그날부터
기여하지 않아 시점 판정과 같은 날 빠진다(`services/monthly_equipment_availability.py`).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

__all__ = ["WdWindow", "month_end", "wd_window", "wd_windows_for_months"]

_ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class WdWindow:
    """한 달이 잡는 W/D 구간. `(boundary_start, boundary_end]` 반열린 구간이다."""

    year_month: int
    """`YYYYMM`. 시뮬레이션 쪽 `생산계획년월` 과 같은 표기다."""

    boundary_start: date
    """**이 달에 속하지 않는다.** 앞 달의 마지막 날이다."""

    boundary_end: date
    """이 달의 마지막 날. 포함한다."""

    @property
    def first_day(self) -> date:
        """이 달에 실제로 속하는 첫날. 화면과 표에 보일 값이다."""
        return self.boundary_start + _ONE_DAY

    @property
    def days(self) -> int:
        """구간 일수. 그 달의 달력일수와 같다."""
        return (self.boundary_end - self.boundary_start).days

    def overlap_days(self, span_start: date, span_end: date) -> int:
        """`[span_start, span_end]`(양 끝 포함하는 날짜 구간)와 겹치는 일수.

        들어온 구간도 경계로 바꿔 센다 — `span_start` 하루 전의 경계부터 `span_end`
        까지다. 그래서 하루짜리 구간(`span_start == span_end`)은 1일로 센다.
        """
        latest_start = max(self.boundary_start, span_start - _ONE_DAY)
        earliest_end = min(self.boundary_end, span_end)
        return max(0, (earliest_end - latest_start).days)

    def contribution(self, span_start: date, span_end: date) -> float:
        """겹친 일수를 구간 길이로 나눈 기여도(0.0~1.0).

        설비 한 대가 `[span_start, span_end]` 동안만 그 상태였다면 그 달에 기여하는
        대수가 이 값이다 — 1대 x 16일 / 31일 = 0.516.
        """
        return self.overlap_days(span_start, span_end) / self.days


def month_end(year: int, month: int) -> date:
    """그 달의 말일."""
    return date(year, month, calendar.monthrange(year, month)[1])


def wd_window(year_month: int, cutoff_days: float) -> WdWindow:
    """`YYYYMM` 한 달의 W/D 구간.

    `cutoff_days` 는 소수점을 받는다(입력 표가 그렇다). 날짜 단위까지만 다루는 지금은
    **내림해서 일 단위로 쓴다** — 0.5일을 날짜로 표현할 방법이 없고, 반올림하면 같은
    Cutoff 가 달마다 다른 길이를 내어 연간 365일 불변조건이 깨진다.
    """
    if year_month < 100101 or year_month > 999912:
        raise ValueError(f"생산계획년월은 YYYYMM 형식이어야 합니다: {year_month}")
    year, month = divmod(year_month, 100)
    if not 1 <= month <= 12:
        raise ValueError(f"생산계획년월의 월은 01~12 여야 합니다: {year_month}")
    if cutoff_days < 0:
        raise ValueError(f"Cutoff 는 음수일 수 없습니다: {cutoff_days}")

    delta = timedelta(days=int(cutoff_days))
    previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return WdWindow(
        year_month=year_month,
        boundary_start=month_end(previous_year, previous_month) - delta,
        boundary_end=month_end(year, month) - delta,
    )


def wd_windows_for_months(months: list[int], cutoff_days: float) -> list[WdWindow]:
    """여러 달의 W/D 구간. 들어온 차례를 지킨다."""
    return [wd_window(month, cutoff_days) for month in months]
