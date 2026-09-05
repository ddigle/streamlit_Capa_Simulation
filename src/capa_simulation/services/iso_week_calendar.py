# Purpose: ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱 규칙을 제공한다.

"""ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱 규칙을 제공한다.

월 경계에 걸친 주차는 **일수가 더 많은 달**에 귀속한다. 7일은 4:3 으로만 갈리므로
동수가 없다. 예전 규칙(월요일이 속한 달)은 6일이 다음 달인 주도 이전 달로 보냈다.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta

import pandas as pd

WEEK_CALENDAR_COLUMNS = ["Weeknum", "주차시작일", "주차종료일", "생산계획년월"]

_WEEK_PATTERN = re.compile(r"^(?P<year>\d{2})-W(?P<week>\d{2})$")


def build_iso_week_calendar(start_date: date, end_date: date) -> pd.DataFrame:
    """Build Monday-start ISO weeks intersecting the requested date range."""
    if start_date > end_date:
        raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    first_monday = start - pd.Timedelta(days=start.weekday())
    last_monday = end - pd.Timedelta(days=end.weekday())
    rows: list[dict[str, object]] = []
    for week_start in pd.date_range(first_monday, last_monday, freq="7D"):
        week_end = week_start + pd.Timedelta(days=6)
        iso_calendar = week_start.isocalendar()
        rows.append(
            {
                "Weeknum": f"{iso_calendar.year % 100:02d}-W{iso_calendar.week:02d}",
                "주차시작일": week_start.date(),
                "주차종료일": week_end.date(),
                "생산계획년월": owning_month(week_start.date()),
            }
        )
    return pd.DataFrame(rows, columns=WEEK_CALENDAR_COLUMNS)


def owning_month(week_start: date) -> int:
    """주차가 귀속되는 `YYYYMM` 을 돌려준다. **일수가 더 많은 달**이 가져간다.

    한 주가 두 달에 걸치면 어느 달의 실적으로 셀지 정해야 한다. 예전에는 월요일이 속한
    달로 보냈는데, 그러면 6일이 다음 달인 주도 이전 달로 갔다. 생산계획 주차 운영 기준에
    맞춰 **더 많은 날이 들어간 달**로 바꿨다(2026-09-05 확정).

    7일은 홀수라 4:3 으로만 갈리므로 동수가 나오지 않는다. 판정이 애매한 경우가 없다.
    """
    week_end = week_start + timedelta(days=6)
    if week_start.year == week_end.year and week_start.month == week_end.month:
        return week_start.year * 100 + week_start.month
    # 걸친 주는 두 달뿐이다. 시작 월의 마지막 날까지 며칠인지 세면 나머지는 다음 달이다.
    days_in_start_month = monthrange(week_start.year, week_start.month)[1] - week_start.day + 1
    if days_in_start_month * 2 > 7:
        return week_start.year * 100 + week_start.month
    return week_end.year * 100 + week_end.month


def valid_weeknum(value: object) -> bool:
    matched = _WEEK_PATTERN.fullmatch(str(value))
    if matched is None:
        return False
    year = 2000 + int(matched.group("year"))
    week = int(matched.group("week"))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True


def weeknum_start_date(value: object) -> date:
    """`YY-W##` 주차 코드가 가리키는 월요일을 돌려준다."""
    matched = _WEEK_PATTERN.fullmatch(str(value).strip().upper())
    if matched is None:
        raise ValueError(f"Weeknum은 YY-W## 형식이어야 합니다: {value!r}")
    return date.fromisocalendar(2000 + int(matched.group("year")), int(matched.group("week")), 1)
