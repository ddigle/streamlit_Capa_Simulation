# Purpose: 조회 월 축에 완전한 해의 연간 Total 열을 끼워 넣는 규칙을 정의한다.

"""월 축과 연간 Total 열.

과거 데이터를 함께 보면 당해 연간 합계가 뜻을 갖는다. 다만 **1~12월이 모두 조회범위 안에
있는 해**만 그렇다. 일부 달만 든 해의 합계는 연간이 아니라 "조회한 달의 합" 이라 같은 칸에
같은 이름으로 두면 읽는 사람이 속는다.

Total 은 그 해 12월 바로 뒤에 들어간다. 다음 해가 이어지면 두 해 사이에 놓인다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

FULL_YEAR_MONTH_COUNT = 12


def month_label(month: int) -> str:
    """차트 월 칸 표기 `YY.MM`. 월 축을 만드는 모든 곳이 같은 함수를 써야 한다."""
    return f"{month // 100 % 100:02d}.{month % 100:02d}"


def year_total_label(year: int) -> str:
    """연간 Total 칸 표기. 월 칸과 한눈에 구분되도록 `YY년` 으로 적는다."""
    return f"{year % 100:02d}년"


def complete_years(months: Sequence[int]) -> list[int]:
    """1~12월이 모두 든 해. 조회범위가 그 해를 통째로 담고 있을 때만 연간 합계가 뜻을 갖는다."""
    by_year: dict[int, set[int]] = {}
    for month in months:
        by_year.setdefault(int(month) // 100, set()).add(int(month) % 100)
    return sorted(
        year
        for year, present in by_year.items()
        if len(present) == FULL_YEAR_MONTH_COUNT and present == set(range(1, 13))
    )


def build_past_month_labels(
    month_labels: Sequence[str],
    year_total_labels: Sequence[str],
    calculated_month_labels: Collection[str],
) -> frozenset[str]:
    """월 축에서 **과거 구간**인 칸. Past Data 로만 채워진 달이다.

    근거는 `calculated_month_labels` 하나다 — DB 계산 구간의 달 라벨이고, 그 밖의 달은
    공용 과거 프로필에서 온 입력값이다.

    연간 Total 은 **그 해의 달이 모두 과거일 때만** 과거로 본다. 한 달이라도 DB 값이
    섞이면 그 합계는 더는 지난 이력이 아니라 이력과 계획을 함께 더한 수이고, 과거로
    칠하면 읽는 사람이 전체를 확정된 실적으로 본다.
    """
    totals = set(year_total_labels)
    past = {
        label
        for label in month_labels
        if label not in totals and label not in calculated_month_labels
    }
    for total in totals:
        # 월 라벨은 `26.07`, Total 라벨은 `26년` 이라 앞 두 자리가 같은 해를 가리킨다.
        members = [label for label in month_labels if label.startswith(f"{total[:2]}.")]
        if members and all(label in past for label in members):
            past.add(total)
    return frozenset(past)


def build_month_axis(months: Sequence[int]) -> tuple[list[str], list[str]]:
    """(월 축 라벨, 그중 연간 Total 라벨).

    월 라벨 사이에 완전한 해의 Total 을 끼운 하나의 축을 돌려준다. 축이 하나여야 표·차트·
    가로 스크롤 폭이 같은 칸 수를 본다 — 축을 두 벌로 만들면 칸이 어긋난다.
    """
    ordered = [int(month) for month in months]
    totals = {year: year_total_label(year) for year in complete_years(ordered)}
    labels: list[str] = []
    for index, month in enumerate(ordered):
        labels.append(month_label(month))
        year = month // 100
        is_last_of_year = index + 1 == len(ordered) or ordered[index + 1] // 100 != year
        if is_last_of_year and year in totals:
            labels.append(totals[year])
    return labels, [totals[year] for year in sorted(totals)]
