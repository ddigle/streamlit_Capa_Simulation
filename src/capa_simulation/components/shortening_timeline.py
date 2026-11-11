# Purpose: 필요 단축 일정 호기 줄의 달 축·위치·격자선·날짜 글자와 이름 칸을 두 화면 조각에 준다.

"""필요 단축 일정 호기 타임라인의 축 계산.

공정 카드의 한 줄 호기 타임라인(`required_shortening_panel`)과 진척 비교의 두 줄
타임라인(`shortening_progress_panel`)이 **같은 축**을 쓴다 — 달 목록의 첫 달 첫날부터 마지막 달의
다음 달 첫날까지, 위치는 백분율이다. 한쪽만 고치면 두 화면의 같은 날이 다른 자리에 선다.

넘기는 달 목록만 다르다. 공정 카드는 고른 조회 달 그대로이고, 진척 비교는 그 달을 두 시점의 날짜가
모두 들도록 앞뒤로 넓힌 목록(`timeline_months_covering`)이다 — 기준선 날짜가 지금 조회 달 밖이면
양 끝에 잘려 붙던 표식이 제자리에 선다(2026-10-08 사용자 결정 「넓히기」).

호기 이름 칸(`unit_name`)도 두 조각이 같은 꼴이다 — 칸보다 긴 이름은 **앞을 줄이고 끝(호기 번호)을
남긴다**(남은 물음 보드 D6 (다) — 같은 공정 호기가 「DEMO-MLD-…」 처럼 같은 글자로 보이지 않게).
칸 서식(`UNIT_NAME_STYLE`)은 오른쪽에서 왼쪽으로 흘려 넘친 쪽(왼쪽 끝)에 말줄임을 두고, 이름은 그
안에서 왼쪽에서 오른쪽 한 덩이(`dir="ltr"` — 기호 · 숫자 차례가 뒤집히지 않는다)로 둔다. 넘치지
않으면 왼쪽 맞춤이다. 전체 이름은 줄 풍선(`title`)에 그대로 있다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

__all__ = [
    "UNIT_NAME_STYLE",
    "month_day",
    "timeline_axis",
    "timeline_grid_lines",
    "timeline_months_covering",
    "timeline_position",
    "unit_name",
]

# 호기 이름 칸 `.shk-unit-name` 의 넘침 서식 — 앞을 줄이고 끝을 남긴다(`unit_name`).
UNIT_NAME_STYLE = (
    "direction:rtl;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
)


def timeline_axis(months: Sequence[int]) -> tuple[date, date]:
    """`months`(`YYYYMM`, 차례대로)의 축 — 첫 달 1일과 마지막 달 다음 달 1일."""
    first = date(months[0] // 100, months[0] % 100, 1)
    year, month = divmod(months[-1], 100)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, following


def timeline_months_covering(months: Sequence[int], days: Iterable[date | None]) -> tuple[int, ...]:
    """`months`(`YYYYMM`, 차례대로)를 앞뒤로 넓혀 `days` 의 날짜가 모두 축 안에 들게 한 달 목록.

    가운데(`months`)는 그대로 두고 그 앞뒤에 빠진 달만 잇는다 — 날짜가 모두 안이면 `months`
    그대로다. None 은 건너뛴다. `months` 가 비면 빈 목록이다(축이 없다 — 날짜로 축을 새로 세우지
    않는다).
    """
    if not months:
        return ()
    keys = [day.year * 100 + day.month for day in days if day is not None]
    first, last = min([months[0], *keys]), max([months[-1], *keys])
    before = _months_until(first, months[0])
    after = _months_until(_following_month(months[-1]), _following_month(last))
    return (*before, *months, *after)


def _following_month(month: int) -> int:
    year, number = divmod(month, 100)
    return (year + 1) * 100 + 1 if number == 12 else month + 1


def _months_until(start: int, stop: int) -> list[int]:
    """`start` 부터 `stop` 앞 달까지(`stop` 은 빼고)."""
    months: list[int] = []
    while start < stop:
        months.append(start)
        start = _following_month(start)
    return months


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


def unit_name(name: str) -> str:
    """호기 이름 칸 — `name` 은 이스케이프한 글이다. 칸(`.shk-unit-name`, 서식 `UNIT_NAME_STYLE`)
    안에서 이름을 왼쪽에서 오른쪽 한 덩이로 둬, 넘치면 앞이 말줄임되고 끝이 남는다."""
    return f'<span class="shk-unit-name"><span dir="ltr">{name}</span></span>'
