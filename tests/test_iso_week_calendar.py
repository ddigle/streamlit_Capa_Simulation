# Purpose: 월 경계 주차가 일수가 더 많은 달에 귀속되는지 고정한다.

"""월 경계 ISO 주차의 귀속 규칙 (2026-09-05 확정).

예전에는 월요일이 속한 달이 그 주를 가져갔다. 그러면 7일 중 6일이 다음 달인 주도 이전
달 실적으로 세어져 월별 일 표준 가능량이 어긋난다. 생산계획 주차 운영 기준에 맞춰
**더 많은 날이 들어간 달**이 가져가도록 바꿨다.

7일은 홀수라 4:3 으로만 갈린다. 동수가 나오지 않으므로 예외 규칙이 필요 없다.
"""

from datetime import date, timedelta

from capa_simulation.services.iso_week_calendar import build_iso_week_calendar, owning_month


def _split(week_start: date) -> tuple[int, int]:
    """그 주가 두 달에 며칠씩 걸치는지 센다."""
    days = [week_start + timedelta(days=offset) for offset in range(7)]
    first = sum(1 for day in days if day.month == week_start.month)
    return first, 7 - first


def test_the_month_with_more_days_owns_the_week() -> None:
    cases = {
        # 8월 1일 · 9월 6일
        date(2026, 8, 31): 202609,
        # 9월 3일 · 10월 4일
        date(2026, 9, 28): 202610,
        # 6월 2일 · 7월 5일
        date(2026, 6, 29): 202607,
        # 3월 2일 · 4월 5일
        date(2026, 3, 30): 202604,
    }

    for week_start, expected in cases.items():
        assert owning_month(week_start) == expected, f"{week_start} 귀속이 어긋납니다"


def test_a_week_inside_one_month_stays_there() -> None:
    assert owning_month(date(2026, 9, 7)) == 202609


def test_a_week_crossing_the_year_keeps_the_majority_month() -> None:
    """연말 주차는 달과 해가 함께 바뀐다. 12월 4일 · 1월 3일이므로 12월이 가져간다."""
    assert _split(date(2026, 12, 28)) == (4, 3)
    assert owning_month(date(2026, 12, 28)) == 202612


def test_the_majority_month_never_ties() -> None:
    """7일은 4:3 으로만 갈린다. 2년치를 전수로 확인한다."""
    day = date(2026, 1, 5)
    while day < date(2028, 1, 1):
        first, second = _split(day)
        assert first != second, f"{day} 에서 동수가 나왔습니다"
        assert owning_month(day) in {
            day.year * 100 + day.month,
            (day + timedelta(days=6)).year * 100 + (day + timedelta(days=6)).month,
        }
        day += timedelta(days=7)


def test_calendar_uses_the_same_rule() -> None:
    """캘린더 생성도 같은 규칙을 써야 한다. 예전에는 여기서만 월요일 기준이었다."""
    calendar = build_iso_week_calendar(date(2026, 8, 24), date(2026, 9, 14))
    owned = dict(zip(calendar["주차시작일"], calendar["생산계획년월"], strict=True))

    assert owned[date(2026, 8, 24)] == 202608
    assert owned[date(2026, 8, 31)] == 202609
