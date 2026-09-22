# Purpose: W/D 구간이 한 해를 빈틈·겹침 없이 덮는지와 기여도 산식을 검사한다.

"""**한 해의 열두 구간을 더하면 정확히 365일(윤년 366일)이어야 한다.**

이것이 이 모듈의 유일한 안전장치다. Cutoff 를 어떻게 바꾸든 구간이 앞으로 밀릴 뿐
길이는 그 달의 달력일수여야 하므로, 합이 어긋나면 어느 달의 생산이 두 번 세어지거나
아무 달에도 안 잡힌 것이다. 둘 다 화면에 오류로 뜨지 않고 숫자만 조용히 틀어진다.

구간이 **반열린**(`(앞 경계, 뒤 경계]`)이라는 것이 숫자를 정한다. 사용자가 준 세 값
— 10월 `(9/15, 10/16]`, 2월 `(1/16, 2/13]` 28일, 9/30 Qual 설비의 10월 기여 16일 —
은 이 모델에서만 동시에 맞는다. 양 끝을 포함으로 세면 마지막이 17일이 된다.
"""

from __future__ import annotations

import calendar
from datetime import date

import pytest

from capa_simulation.services.wd_window import WdWindow, wd_window, wd_windows_for_months

# 0 은 달력 월 그대로, 15 는 사용자가 예로 든 값, 45·120 은 한 달을 넘는 Cutoff,
# 31 은 말일에 정확히 걸리는 값, 0.9 는 소수점 입력이 내림되는지 본다.
CUTOFFS = (0, 0.9, 15, 31, 45, 120)
YEARS = (2025, 2026, 2028, 2100)  # 2028 윤년, 2100 은 윤년이 아닌 세기
FAR_FUTURE = date(2999, 12, 31)


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_twelve_windows_cover_the_year_exactly(year: int, cutoff: float) -> None:
    months = [year * 100 + month for month in range(1, 13)]
    windows = wd_windows_for_months(months, cutoff)

    expected = 366 if calendar.isleap(year) else 365
    assert sum(window.days for window in windows) == expected, (
        f"{year}년 cutoff={cutoff}: 열두 구간의 합이 {expected}일이 아닙니다. "
        "어느 달이 두 번 세어지거나 빠졌습니다."
    )


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_windows_are_contiguous_without_gap_or_overlap(year: int, cutoff: float) -> None:
    """앞 구간의 뒤 경계가 곧 뒤 구간의 앞 경계다 — 반열린 구간이라 그대로 맞물린다."""
    months = [year * 100 + month for month in range(1, 13)]
    windows = wd_windows_for_months(months, cutoff)

    # 길이가 12 와 11 로 다른 것이 의도다 — 이웃 쌍을 훑는다.
    for earlier, later in zip(windows, windows[1:], strict=False):
        assert later.boundary_start == earlier.boundary_end, (
            f"{earlier.year_month} 와 {later.year_month} 사이가 이어지지 않습니다 "
            f"({earlier.boundary_end} → {later.boundary_start})."
        )


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_window_length_is_the_calendar_month_length(cutoff: float) -> None:
    """구간 길이는 Cutoff 와 무관하게 그 달의 달력일수다."""
    for month in range(1, 13):
        window = wd_window(202600 + month, cutoff)
        assert window.days == calendar.monthrange(2026, month)[1]


def test_the_user_example_february_with_cutoff_15() -> None:
    """Cutoff 15일 공정의 2026-02 는 (1/16, 2/13], 첫날 1/17, 28일."""
    window = wd_window(202602, 15)

    assert window.boundary_start == date(2026, 1, 16)
    assert window.first_day == date(2026, 1, 17)
    assert window.boundary_end == date(2026, 2, 13)
    assert window.days == 28


def test_the_user_example_october_with_cutoff_15() -> None:
    """같은 공정의 2026-10 은 (9/15, 10/16], 31일."""
    window = wd_window(202610, 15)

    assert window.boundary_start == date(2026, 9, 15)
    assert window.first_day == date(2026, 9, 16)
    assert window.boundary_end == date(2026, 10, 16)
    assert window.days == 31


def test_a_zero_cutoff_is_the_plain_calendar_month() -> None:
    window = wd_window(202602, 0)

    assert window.first_day == date(2026, 2, 1)
    assert window.boundary_end == date(2026, 2, 28)


def test_contribution_matches_the_worked_example() -> None:
    """9/30 Qual 완료 설비는 10/1 부터 가용이고, 2026-10 기여는 16일/31일 = 0.52대."""
    window = wd_window(202610, 15)
    available_from = date(2026, 10, 1)  # Qual 완료일 다음 날

    assert window.overlap_days(available_from, FAR_FUTURE) == 16
    assert round(window.contribution(available_from, FAR_FUTURE), 2) == 0.52


def test_a_single_day_span_counts_as_one_day() -> None:
    """하루짜리 비가동도 1일로 세어야 한다 — 경계 변환에서 0 이 되면 안 된다."""
    window = wd_window(202610, 15)

    assert window.overlap_days(date(2026, 10, 5), date(2026, 10, 5)) == 1


def test_a_span_outside_the_window_contributes_nothing() -> None:
    window = wd_window(202610, 15)

    assert window.overlap_days(date(2026, 10, 17), date(2026, 10, 31)) == 0
    assert window.contribution(date(2026, 10, 17), date(2026, 10, 31)) == 0.0


def test_a_span_covering_the_window_contributes_everything() -> None:
    window = wd_window(202610, 15)

    assert window.contribution(date(2020, 1, 1), date(2030, 1, 1)) == 1.0


def test_the_boundary_start_day_belongs_to_the_previous_month() -> None:
    """앞 경계 하루만 걸친 구간은 이 달에 0일 기여한다 — 그 날은 앞 달 몫이다."""
    window = wd_window(202610, 15)

    assert window.overlap_days(date(2026, 9, 15), date(2026, 9, 15)) == 0


def test_a_fractional_cutoff_is_floored_so_the_year_still_adds_up() -> None:
    """0.9 일은 0 일과 같은 구간을 낸다 — 반올림하면 연간 합이 깨진다."""
    assert wd_window(202602, 0.9) == wd_window(202602, 0)


def test_a_january_window_reaches_into_the_previous_year() -> None:
    window = wd_window(202601, 15)

    assert window.first_day == date(2025, 12, 17)
    assert window.boundary_end == date(2026, 1, 16)


@pytest.mark.parametrize("bad", [202613, 202600, 99, 1000000])
def test_a_malformed_month_is_refused(bad: int) -> None:
    with pytest.raises(ValueError):
        wd_window(bad, 15)


def test_a_negative_cutoff_is_refused() -> None:
    with pytest.raises(ValueError, match="음수"):
        wd_window(202602, -1)


def test_the_window_is_hashable_and_comparable() -> None:
    """캐시 키에 실리므로 frozen dataclass 여야 한다."""
    left = wd_window(202602, 15)
    right = wd_window(202602, 15)

    assert left == right
    assert len({left, right}) == 1
    assert isinstance(left, WdWindow)
