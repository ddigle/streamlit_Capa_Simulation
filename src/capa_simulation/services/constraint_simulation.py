# Purpose: 한 공정 소요·가용을 제약·기존 제품으로 나눠 개조 비가동과 우선 배정의 확보율을 계산한다.

"""제약 시뮬레이션 — 「한 공정에 미래 제약이 생기면 기존 제품 확보율이 언제부터 얼마나 주나」.

제약은 특정 제품(제약 제품)만 쓸 수 있게 개조·전용해야 하는 설비다(2026-10-24 사용자 결정). 공정
하나의 월별 소요대수(R)를 제약 제품(Rc)과 기존 제품(Re = R − Rc)으로 나누고, 설비 일정 기준 가용(A,
단축 전 환산 대수)에서 **제약 몫을 먼저 떼어 준 뒤** 남는 몫으로 기존 제품 확보율을 낸다.
Streamlit·세션·캐시·DB 를 보지 않는다. pandas 는 어댑터(`constraint_month_inputs`) 하나만 쓰고
계산 몸통은 파이썬 수다.

일곱 가정(사용자 「권장대로」 결정 그대로). `in(m)` 은 제약 기간 안, 「앞 달」 은 **보이는 달
차례에서 바로 앞 달**이고 그 달도 기간 안일 때만 그 값을 잇는다(기간 첫 달은 0 부터).

1. 제약 몫 필요 대수 = 올림(제약 소요 × 제약 확보율) — `required_units`, 올림 전 `NEED_TOLERANCE`
   를 뺀다.
2. 제약 소요가 늘어나는 달마다 늘어난 대수만 그 달 앞에 새로 개조한다(`increment` > 0 이면 개조 창
   하나).
3. 기간 안에서는 개조한 대수를 줄이지 않는다 — 개조 켬이면 `dedicated = max(앞 달 dedicated,
   need)`. 개조 끔이면 설비가 서로 바뀌므로 그 달 필요만 뗀다(`dedicated = need`).
4. 기간이 끝나면 바로 기존 제품 가용으로 돌아간다(원복 개조 없음 — 기간 밖 `dedicated = 0`).
5. 개조 비가동 = `[그 달 1일 − Cut-off − 개조 일수, 그 달 1일 − Cut-off)` 이고 달마다 **W/D 구간
   일수 비율**로 환산 대수를 뺀다. 창 끝이 곧 그 달 W/D 첫날이라(`wd_window(m, c).first_day`)
   가용대수 A 가 일할된 바로 그 구간 좌표에서 뺀다 — 개조 일수가 앞 달 W/D 일수 이하면 비가동은
   모두 앞 달 한 칸에 든다(D1).
6. 가용이 모자라면 제약 몫부터 정수로 채우고(`allocated = min(dedicated, floor(usable))`) 남는 것을
   기존 제품에 준다 — 모자란 달은 `short_months`.
7. 기간 밖의 제약 제품 소요는 기존 제품에 합쳐 센다(`constrained_demand` 는 기간 안에서만 값).

판정은 경계를 이 모듈에 다시 적지 않는다(AGENTS 6장 「판정은 한 길」). 기준 확보율(G) 판정은
`securement_threshold.capacity_status` 를 지나는 `secure()` 하나 — 허용치 없는 「이상」 이라 HOME
과 같은 비율을 같게 칠한다. 제약 충족(`met`)은 `allocated >= need` **정수 비교**다 — `need` 가 제약
확보율을 맞추는 가장 작은 정수라 「제약 % ≥ T」 와 같은 뜻이고 부동소수 잡음이
없다(`tests/test_constraint_simulation.py`). 「영향 시작」 의 0.05%p 문턱(`IMPACT_TOLERANCE`)은
판정이 아니라 표시 문턱이다.

「소요 비중대로 나눴을 때」 견주기는 개조 비가동 없이 가용을 소요 비중대로 **사사오입** 정수로
나눈다(초안의 `Math.round` — 파이썬 `round` 는 은행가 반올림이라 쓰지 않는다, D15).

대수는 모두 **환산 대수**다 — 가용 A 가 호기별 환산비를 곱한 값이라(소요대수가 능력 기준 대수라서)
「개조 n대」·「배정 n대」 도 환산 대수다. 어느 호기를 개조하는지는 정하지 않는다(대수 모델).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import pandas as pd

from capa_simulation.services.process_capa_detail import OTHER_ROW_COLUMN, month_column
from capa_simulation.services.securement_threshold import capacity_status
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "GENERAL_INPUT_RANGE",
    "IMPACT_TOLERANCE",
    "MODIFICATION_DAYS_RANGE",
    "NEED_TOLERANCE",
    "SUM_TOLERANCE",
    "TARGET_RANGE",
    "ConstraintConditions",
    "ConstraintKpis",
    "ConstraintMonth",
    "ConstraintMonthInput",
    "ConstraintResult",
    "DowntimeShare",
    "ModificationWindow",
    "constraint_month_inputs",
    "modification_window",
    "required_units",
    "secure",
    "simulate_constraint",
]

NEED_TOLERANCE: Final = 1e-9
"""올림·내림 전에 빼고 더하는 잡음(10 × 1.1 = 11.000000000000002 → 11)."""

IMPACT_TOLERANCE: Final = 0.0005
"""「영향 시작」: 기존 확보율이 제약 없을 때보다 0.05%p 넘게 낮은 첫 달. 판정이 아니라 표시
문턱이다."""

SUM_TOLERANCE: Final = 1e-6
"""어댑터가 제품별 소요 합과 공정 소요를 맞댈 때의 상대 허용치(`× max(1, R)`) — 합 차례의 부동소수
잡음."""

TARGET_RANGE: Final = (0.5, 3.0)
"""제약 확보율(비율) 50~300%."""

GENERAL_INPUT_RANGE: Final = (0.5, 2.0)
"""기준 확보율 **직접 입력 칸**의 범위(50~200%). 서비스 검증에는 쓰지 않는다 — HOME 월별 예외는
범위 밖일 수 있다."""

MODIFICATION_DAYS_RANGE: Final = (1, 365)
"""개조 기간(일)."""

_ONE_DAY = timedelta(days=1)


# ================================================================== 입력·출력


@dataclass(frozen=True)
class ConstraintMonthInput:
    """보이는 달 하나의 입력. 모두 그 공정 하나의 값이다."""

    month: int
    """`YYYYMM`."""

    required: float
    """R — 공정 소요대수(모든 제품의 합)."""

    constrained_demand: float
    """제약 제품 소요(기간과 무관한 원값, 0 이상 R 이하)."""

    available: float
    """A — 설비 일정 기준 가용(환산 대수, 개조 전·단축 전)."""

    general_target: float
    """G(m) — 그 달 기준 확보율(비율). 0 보다 크기만 하면 된다."""


@dataclass(frozen=True)
class ConstraintConditions:
    """화면이 고른 조건. 값으로 같고 해시된다(그림 memo 키 원소)."""

    period_start: int
    period_end: int
    constraint_target: float
    """T — 제약 확보율(비율)."""

    modification_days: int | None
    """개조 기간(일). None 이면 개조하지 않는다."""

    cutoff_days: int
    """그 공정의 Cut-off(내림 일수 — `wd_window` 와 같다)."""

    @property
    def modifies(self) -> bool:
        return self.modification_days is not None

    def in_period(self, month: int) -> bool:
        return self.period_start <= month <= self.period_end


@dataclass(frozen=True)
class ModificationWindow:
    """개조 비가동 창 하나. 반열린 `[start, end)` 이다."""

    month: int
    """그 대수를 쓰기 시작하는 달(이 달 몫)."""

    units: int
    """이 달 몫으로 새로 개조하는 대수(환산)."""

    start: date
    """비가동 첫날(포함)."""

    end: date
    """비가동 끝 경계(불포함) = 그 달 W/D 첫날."""

    @property
    def last_day(self) -> date:
        """비가동 마지막 날(포함). 화면에 적을 값이다."""
        return self.end - _ONE_DAY


@dataclass(frozen=True)
class DowntimeShare:
    """보이는 달 하나에 든 개조 비가동 한 몫 — 창 하나 × 그 달 W/D 구간."""

    source_month: int
    """어느 달 몫의 개조인가(`ModificationWindow.month`)."""

    units: int
    days: int
    """창이 그 달 W/D 구간과 겹친 일수."""

    window_days: int
    """그 달 W/D 구간 일수(분모)."""

    @property
    def equivalent(self) -> float:
        """환산 비가동 대수 = 대수 × 겹친 일수 ÷ W/D 일수."""
        return self.units * self.days / self.window_days


@dataclass(frozen=True)
class ConstraintMonth:
    """보이는 달 하나의 결과."""

    month: int
    in_period: bool
    required: float
    """R."""

    product_demand: float
    """제약 제품의 원 소요(기간과 무관) — 기간 밖 달의 「원값」 을 적을 때 쓴다."""

    constrained_demand: float
    """Rc' — 기간 안에서만 원값, 밖은 0(가정 7)."""

    existing_demand: float
    """Re = R − Rc'."""

    available: float
    """A."""

    general_target: float
    """G(m)."""

    need: int
    """제약 몫 필요 대수(가정 1). 기간 밖·Rc' 0 이면 0."""

    dedicated: int
    """제약 제품에 떼는 대수(가정 3 — 개조 켬이면 기간 안 누적 최대)."""

    increment: int
    """이 달 몫으로 새로 개조하는 대수(가정 2). 개조 끔이면 0."""

    downtime: float
    """이 달 W/D 구간에 든 개조 비가동(환산 대수)."""

    downtime_shares: tuple[DowntimeShare, ...]
    usable: float
    """A − 비가동. 음수면 0 으로 둔다(`overdrawn`)."""

    overdrawn: bool
    """개조 비가동이 그 달 가용보다 많다 — 이 공정 설비로는 그 개조 일정이 서지 않는다."""

    allocated: int
    """제약 제품에 실제로 준 정수 대수(가정 6)."""

    short: bool
    """가용이 모자라 `dedicated` 를 다 못 줬다."""

    existing_available: float
    """기존 제품 몫 = usable − allocated(소수 그대로)."""

    baseline_rate: float | None
    """제약 없을 때(공정 전체) = A ÷ R. R 0 이면 None."""

    existing_rate: float | None
    """기존 제품 = 기존 몫 ÷ Re. Re 0 이면 None."""

    constrained_rate: float | None
    """제약 제품 = allocated ÷ Rc'. 기간 밖·Rc' 0 이면 None."""

    met: bool | None
    """제약 확보율 충족 = `allocated >= need`(정수). 기간 밖·Rc' 0 이면 None."""

    existing_secure: bool | None
    """기존 확보율이 기준 이상인가(`secure`). 확보율이 없으면 None."""

    baseline_secure: bool | None
    """제약 없을 때 확보율이 기준 이상인가. 확보율이 없으면 None."""

    proportional_constrained: int
    """비중대로 나눈 제약 몫(사사오입 정수, 개조 비가동 없음). 기간 밖·R 0 이면 0."""

    proportional_existing: float
    """비중대로 나눈 기존 몫 = A − 제약 몫."""

    proportional_existing_rate: float | None
    proportional_constrained_rate: float | None


@dataclass(frozen=True)
class ConstraintKpis:
    """요약 넷의 값."""

    constrained_months: int
    """기간 안이고 Rc' > 0 인 달 수(n)."""

    constrained_met_months: int
    """그중 `met` 인 달 수."""

    lowest_existing_month: int | None
    lowest_existing_rate: float | None
    lowest_baseline_rate: float | None
    """기존 최저 달의 제약 없을 때 확보율."""

    below_months: tuple[int, ...]
    """기존 확보율이 그 달 기준에 못 미치는 달."""

    newly_below_months: tuple[int, ...]
    """그중 제약이 없었다면 기준 이상이었던 달."""

    first_impact_month: int | None
    """기존 확보율이 제약 없을 때보다 `IMPACT_TOLERANCE` 넘게 낮은 첫 달."""

    max_dedicated: int | None
    """개조 대수(가장 큰 `dedicated`). 개조 끔이면 None."""

    window_count: int
    first_downtime_day: date | None


@dataclass(frozen=True)
class ConstraintResult:
    conditions: ConstraintConditions
    months: tuple[ConstraintMonth, ...]
    windows: tuple[ModificationWindow, ...]
    kpis: ConstraintKpis
    starts_before_range: bool
    """첫 개조 비가동이 첫 보이는 달의 W/D 첫날보다 앞 — 그 앞 달의 감소는 표에 없다."""

    short_months: tuple[int, ...]
    """가용이 모자라 제약 몫을 다 못 준 달."""

    overdrawn_months: tuple[int, ...]
    """개조 비가동이 그 달 가용보다 많은 달."""

    def month(self, month: int) -> ConstraintMonth:
        """그 달의 결과. 보이는 달이 아니면 KeyError."""
        for row in self.months:
            if row.month == month:
                return row
        raise KeyError(f"보이는 달이 아닙니다: {month}")


# ================================================================== 작은 규칙


def required_units(demand: float, target: float) -> int:
    """제약 몫 필요 대수 = 올림(소요 × 확보율). 소요가 0 이하면 0 이다.

    올림 전에 `NEED_TOLERANCE` 를 뺀다 — 10 × 1.1 이 11.000000000000002 라 12 가 되지 않게.
    """
    if demand <= 0:
        return 0
    return max(0, math.ceil(demand * target - NEED_TOLERANCE))


def secure(rate: float | None, target: float) -> bool:
    """확보율이 기준 이상인가. 경계는 `capacity_status` 한 길이다(허용치 없음 — HOME 과 같다).

    확보율이 없으면(None) False 다 — 판정 대상이 아니라는 뜻은 부르는 쪽이 None 으로 가른다.
    """
    if rate is None:
        return False
    status = capacity_status(rate, secure_threshold=target, warning_threshold=target)
    return status == "secure"


def modification_window(
    month: int, *, units: int, days: int, cutoff_days: int
) -> ModificationWindow:
    """`month` 몫 `units` 대의 개조 비가동 창. 끝 경계는 그 달 W/D 첫날(1일 − Cut-off)이다."""
    end = wd_window(month, cutoff_days).first_day
    return ModificationWindow(month=month, units=units, start=end - timedelta(days=days), end=end)


def _downtime_shares(
    window: WdWindow, windows: Sequence[ModificationWindow]
) -> tuple[DowntimeShare, ...]:
    shares: list[DowntimeShare] = []
    for item in windows:
        days = window.overlap_days(item.start, item.last_day)
        if days > 0:
            shares.append(DowntimeShare(item.month, item.units, days, window.days))
    return tuple(shares)


def _optional_secure(rate: float | None, target: float) -> bool | None:
    return None if rate is None else secure(rate, target)


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def _half_up(value: float) -> int:
    """사사오입 정수(초안 `Math.round` 와 같다 — 2.5 → 3)."""
    return math.floor(value + 0.5)


# ================================================================== 검증


def _valid_month(value: int) -> bool:
    year, month = divmod(int(value), 100)
    return 1001 <= year <= 9999 and 1 <= month <= 12


def _require_within(value: float, bounds: tuple[float, float], message: str) -> None:
    low, high = bounds
    if not low <= value <= high:
        raise ValueError(message)


def _require_non_negative(value: float, message: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(message)


def _require_positive(value: float, message: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(message)


def _validate(months: Sequence[ConstraintMonthInput], conditions: ConstraintConditions) -> None:
    for value in (conditions.period_start, conditions.period_end):
        if not _valid_month(value):
            raise ValueError(f"제약 기간은 YYYYMM 이어야 합니다: {value}")
    if conditions.period_start > conditions.period_end:
        raise ValueError(
            f"제약 시작({conditions.period_start})이 제약 끝({conditions.period_end})보다 뒤입니다."
        )
    _require_within(
        conditions.constraint_target,
        TARGET_RANGE,
        f"제약 확보율은 {TARGET_RANGE[0]:.0%}~{TARGET_RANGE[1]:.0%} 여야 합니다: "
        f"{conditions.constraint_target}",
    )
    if conditions.modification_days is not None:
        _require_within(
            conditions.modification_days,
            MODIFICATION_DAYS_RANGE,
            f"개조 기간은 {MODIFICATION_DAYS_RANGE[0]}~{MODIFICATION_DAYS_RANGE[1]}일이어야 "
            f"합니다: {conditions.modification_days}",
        )
    if conditions.cutoff_days < 0:
        raise ValueError(f"Cut-off 는 음수일 수 없습니다: {conditions.cutoff_days}")

    previous: int | None = None
    for row in months:
        if not _valid_month(row.month):
            raise ValueError(f"보이는 달은 YYYYMM 이어야 합니다: {row.month}")
        if previous is not None and row.month <= previous:
            raise ValueError(
                f"보이는 달은 겹치지 않는 오름차순이어야 합니다: {previous} → {row.month}"
            )
        previous = row.month
        _require_non_negative(row.required, f"{row.month} 공정 소요가 0 이상의 수가 아닙니다.")
        _require_non_negative(
            row.constrained_demand, f"{row.month} 제약 제품 소요가 0 이상의 수가 아닙니다."
        )
        _require_non_negative(row.available, f"{row.month} 가용대수가 0 이상의 수가 아닙니다.")
        _require_positive(row.general_target, f"{row.month} 기준 확보율은 0 보다 큰 수여야 합니다.")
        if row.constrained_demand > row.required:
            raise ValueError(
                f"{row.month} 제약 제품 소요({row.constrained_demand:g})가 공정 소요"
                f"({row.required:g})보다 큽니다."
            )


# ================================================================== 계산


def simulate_constraint(
    months: Sequence[ConstraintMonthInput], conditions: ConstraintConditions
) -> ConstraintResult:
    """보이는 달마다 일곱 가정으로 제약 몫·개조 비가동·배정·확보율을 내고 요약을 붙인다.

    `months` 는 보이는 달 오름차순이다(띄엄띄엄이어도 된다 — 「앞 달」 은 보이는 차례의 앞 달이고,
    보이지 않는 달에 든 비가동은 셈하지 않는다). 검증에 걸리면 화면에 낼 글의 `ValueError` 다.
    """
    _validate(months, conditions)
    cutoff = conditions.cutoff_days

    # 1단계 — 제약 몫(가정 7·1·3·2·4)과 개조 창. 달마다 (기간 안, Rc', need, pool, inc).
    plans: list[tuple[bool, float, int, int, int]] = []
    windows: list[ModificationWindow] = []
    previous_in_period = False
    previous_pool = 0
    for row in months:
        inside = conditions.in_period(row.month)
        constrained = row.constrained_demand if inside else 0.0
        need = required_units(constrained, conditions.constraint_target) if inside else 0
        carried = previous_pool if inside and previous_in_period else 0
        if not inside:
            pool, increment = 0, 0
        elif conditions.modification_days is not None:
            pool = max(carried, need)
            increment = pool - carried
            if increment > 0:
                windows.append(
                    modification_window(
                        row.month,
                        units=increment,
                        days=conditions.modification_days,
                        cutoff_days=cutoff,
                    )
                )
        else:
            pool, increment = need, 0
        plans.append((inside, constrained, need, pool, increment))
        previous_in_period, previous_pool = inside, pool

    # 2단계 — 개조 비가동(가정 5)·배정(가정 6)·확보율·비중 견주기.
    results: list[ConstraintMonth] = []
    for row, (inside, constrained, need, pool, increment) in zip(months, plans, strict=True):
        existing = row.required - constrained
        shares = _downtime_shares(wd_window(row.month, cutoff), windows)
        downtime = sum(share.equivalent for share in shares)
        remaining = row.available - downtime
        overdrawn = remaining < -NEED_TOLERANCE
        usable = max(0.0, remaining)
        allocated = min(pool, math.floor(usable + NEED_TOLERANCE)) if inside else 0
        existing_available = usable - allocated
        baseline_rate = _ratio(row.available, row.required)
        existing_rate = _ratio(existing_available, existing)
        has_constraint = inside and constrained > 0
        constrained_rate = _ratio(allocated, constrained) if has_constraint else None
        proportional = (
            _half_up(row.available * constrained / row.required)
            if inside and row.required > 0
            else 0
        )
        proportional_existing = row.available - proportional
        results.append(
            ConstraintMonth(
                month=row.month,
                in_period=inside,
                required=row.required,
                product_demand=row.constrained_demand,
                constrained_demand=constrained,
                existing_demand=existing,
                available=row.available,
                general_target=row.general_target,
                need=need,
                dedicated=pool,
                increment=increment,
                downtime=downtime,
                downtime_shares=shares,
                usable=usable,
                overdrawn=overdrawn,
                allocated=allocated,
                short=inside and allocated < pool,
                existing_available=existing_available,
                baseline_rate=baseline_rate,
                existing_rate=existing_rate,
                constrained_rate=constrained_rate,
                met=(allocated >= need) if has_constraint else None,
                existing_secure=_optional_secure(existing_rate, row.general_target),
                baseline_secure=_optional_secure(baseline_rate, row.general_target),
                proportional_constrained=proportional,
                proportional_existing=proportional_existing,
                proportional_existing_rate=_ratio(proportional_existing, existing),
                proportional_constrained_rate=(
                    _ratio(proportional, constrained) if has_constraint else None
                ),
            )
        )

    month_rows = tuple(results)
    first_day = wd_window(month_rows[0].month, cutoff).first_day if month_rows else None
    starts_before = bool(windows) and first_day is not None and windows[0].start < first_day
    return ConstraintResult(
        conditions=conditions,
        months=month_rows,
        windows=tuple(windows),
        kpis=_kpis(month_rows, tuple(windows), modifies=conditions.modifies),
        starts_before_range=starts_before,
        short_months=tuple(row.month for row in month_rows if row.short),
        overdrawn_months=tuple(row.month for row in month_rows if row.overdrawn),
    )


def _kpis(
    months: tuple[ConstraintMonth, ...],
    windows: tuple[ModificationWindow, ...],
    *,
    modifies: bool,
) -> ConstraintKpis:
    constrained = [row for row in months if row.met is not None]
    rated = [row for row in months if row.existing_rate is not None]
    lowest = min(rated, key=_existing_rate_key) if rated else None
    below = tuple(row.month for row in rated if row.existing_secure is False)
    newly = tuple(
        row.month for row in rated if row.existing_secure is False and row.baseline_secure is True
    )
    impact = next(
        (
            row.month
            for row in rated
            if row.baseline_rate is not None
            and row.existing_rate is not None
            and row.existing_rate < row.baseline_rate - IMPACT_TOLERANCE
        ),
        None,
    )
    return ConstraintKpis(
        constrained_months=len(constrained),
        constrained_met_months=sum(1 for row in constrained if row.met),
        lowest_existing_month=None if lowest is None else lowest.month,
        lowest_existing_rate=None if lowest is None else lowest.existing_rate,
        lowest_baseline_rate=None if lowest is None else lowest.baseline_rate,
        below_months=below,
        newly_below_months=newly,
        first_impact_month=impact,
        max_dedicated=max((row.dedicated for row in months), default=0) if modifies else None,
        window_count=len(windows),
        first_downtime_day=windows[0].start if windows else None,
    )


def _existing_rate_key(row: ConstraintMonth) -> float:
    """기존 확보율 최저 고르기 열쇠(같으면 `min` 이 앞 달을 남긴다)."""
    return math.inf if row.existing_rate is None else row.existing_rate


# ================================================================== 어댑터


def constraint_month_inputs(
    process_months: pd.DataFrame,
    product_demand: pd.DataFrame,
    *,
    process: str,
    product: str,
    months: Sequence[int],
    general_target: Callable[[int], float],
) -> tuple[ConstraintMonthInput, ...]:
    """필요 단축 일정 계획의 공정 x 월 표와 제품별 소요대수 표를 달마다의 입력으로 맞댄다.

    - `process_months` 는 `ShorteningPlan.at(…).process_months`(`PROCESS_MONTH_COLUMNS`)다. 읽는
      칸은 `공정`·`생산계획년월`·`소요대수`·`가용대수` 넷뿐이다(단축 열은 읽지 않는다 — 가용은 단축
      전). 그 공정 행이 하나도 없으면 `KeyError`, 보이는 달이 빠졌거나 겹치면 `ValueError` 다.
    - `product_demand` 는 `build_process_product_demand(split="제품정보")` 꼴(그 공정, 보이는 달
      칸)이다. **행을 다 더하면 그 공정 소요**라 `|Σ 표 − R| > SUM_TOLERANCE × max(1, R)` 이면
      `ValueError` 다. Rc 는 `제품정보 == product` 이고 「그 밖」 이 아닌 행이다(없으면 0).
      `Rc > R + NEED_TOLERANCE` 도 `ValueError`, `R < Rc ≤ R + NEED_TOLERANCE` 면 Rc = R 로
      접는다. 다른 제품 소요가 0 인 달도 Rc = R 로 접는다 — 합하는 차례만 다른 두 근거가 1e-16
      만큼 어긋나 Re 가 0 이 아닌 잡음이 되지 않게.
    - `general_target(m)` 은 그 달 기준 확보율(비율)이다.
    """
    key = str(process).strip()
    names = process_months["공정"].astype("string").str.strip()
    rows = process_months.loc[names.eq(key).fillna(False).to_numpy()]
    if rows.empty:
        raise KeyError(f"설비 일정 기준 계획에 공정 「{key}」 이 없습니다.")
    by_month: dict[int, tuple[float, float]] = {}
    for month, required, available in zip(
        pd.to_numeric(rows["생산계획년월"], errors="coerce"),
        pd.to_numeric(rows["소요대수"], errors="coerce"),
        pd.to_numeric(rows["가용대수"], errors="coerce"),
        strict=True,
    ):
        if pd.isna(month):
            raise ValueError(f"설비 일정 기준 계획의 생산계획년월이 수가 아닙니다: {month}")
        stamp = int(month)
        if stamp in by_month:
            raise ValueError(f"설비 일정 기준 계획에 {stamp} 공정 「{key}」 행이 둘 이상입니다.")
        by_month[stamp] = (float(required), float(available))

    wanted = str(product).strip()
    names_column = product_demand["제품정보"] if "제품정보" in product_demand.columns else None
    other_column = (
        product_demand[OTHER_ROW_COLUMN] if OTHER_ROW_COLUMN in product_demand.columns else None
    )
    if names_column is None or other_column is None:
        if not product_demand.empty:
            raise ValueError("제품별 소요대수 표에 `제품정보`·`그 밖` 칸이 없습니다.")
        chosen = pd.Series(dtype="bool")
    else:
        others = other_column.astype("boolean").fillna(False).astype("bool")
        chosen = (
            names_column.astype("string").str.strip().eq(wanted).fillna(False).astype("bool")
            & ~others
        )

    inputs: list[ConstraintMonthInput] = []
    for month in (int(value) for value in months):
        if month not in by_month:
            raise ValueError(f"설비 일정 기준 계획에 {month} 공정 「{key}」 행이 없습니다.")
        required, available = by_month[month]
        column = month_column(month)
        if column in product_demand.columns:
            values = pd.to_numeric(product_demand[column], errors="coerce").fillna(0.0)
            table_total = float(values.sum())
            constrained = float(values.loc[chosen.to_numpy()].sum()) if len(chosen) else 0.0
        else:
            table_total, constrained = 0.0, 0.0
        if abs(table_total - required) > SUM_TOLERANCE * max(1.0, abs(required)):
            raise ValueError(
                f"제품별 소요 합이 공정 소요와 다릅니다 — {month} 공정 「{key}」: "
                f"제품별 합 {table_total:g} · 공정 {required:g}."
            )
        if constrained > required + NEED_TOLERANCE:
            raise ValueError(
                f"제품별 소요 합이 공정 소요와 다릅니다 — {month} 「{wanted}」 소요 "
                f"{constrained:g} 가 공정 소요 {required:g} 보다 큽니다."
            )
        if constrained > required or (constrained > 0 and table_total - constrained <= 0):
            constrained = required
        inputs.append(
            ConstraintMonthInput(
                month=month,
                required=required,
                constrained_demand=constrained,
                available=available,
                general_target=float(general_target(month)),
            )
        )
    return tuple(inputs)
