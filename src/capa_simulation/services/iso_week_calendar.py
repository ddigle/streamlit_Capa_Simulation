# Purpose: ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱 규칙을 제공한다.

"""ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱 규칙을 제공한다."""

from __future__ import annotations

import re
from datetime import date

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
                # A cross-month week uses the month containing its Monday.
                "생산계획년월": week_start.year * 100 + week_start.month,
            }
        )
    return pd.DataFrame(rows, columns=WEEK_CALENDAR_COLUMNS)


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
