# Purpose: UPEH 가정(구간 달의 계획 UPEH ×f)을 소요대수 ÷f 사후 배수로 걸고, 역산·효과 글을 낸다.

"""UPEH 가정 — 「이 달들의 UPEH 가 p% 면」 을 세션 안에서만 보는 가정(what-if).

**무엇에 거나.** 활성 시나리오 기준정보 `RQ_UPEH` 의 계획 UPEH 전체다 — Main 경로의 `UPEH` 와 MI
경로의 `ST`(ST ÷ f 와 같은 뜻). 전 공정에 한 값이고, 구간(시작 월~끝 월)에 든 달에만 건다. 실적 UPEH
도 아니고 HOME 「확보율 보정」(확보율에 %p 를 더하는 공용 손입력)도 아니다 — 그래서 이름에
「보정」을 쓰지 않는다.

**어떻게 거나 — 사후 배수.** 대당 Capa 는 환산 UPEH 에 선형이고(`unit_capacity` 의 곱셈 식),
소요대수는 `부하량 ÷ 대당 Capa` 로 올림이 없는 실수다. 그래서 UPEH ×f 는 그 달 대당 Capa ×f,
소요대수 ÷f 와 같다 (`tests/test_upeh_assumption.py` 가 `RQ_UPEH` 를 고쳐 다시 계산한 결과와 맞대어
이 전제를 지킨다 — 식에 상한·하한·반올림이 들어오면 그 시험이 깨진다). 기준정보·`content_token`·전체
기간 계산 캐시는 건드리지 않는다. 110% 는 소요 −10% 가 아니라 −9.09%(1 − 1/1.1)다.

**토큰.** 가정은 캐시 키 안에서 `(퍼센트, 걸 달)` 튜플(`UpehToken`)로만 다닌다. 100% 이거나 구간이
계산하는 달과 겹치지 않으면 빈 튜플 `()` 이다 — 계산하지 않는 달이 키를 가르지
않게(`target_from_thresholds` 와 같은 선례). 배수(f)는 늘 토큰에서 다시 낸다.

**역산.** 닫힌 식이다 — 구간 안 달마다 「모자람이 없으려면 f 가 얼마여야 하나」의 최댓값을 정수 %로
올린다. 구간 안 달만 보고 앞 달 단축이 넘겨 주는 몫은 빼므로 보수적이다(실제보다 큰 %). 가용이 0 인
달이 있으면 UPEH 로는 채울 수 없다. 신규(추가N) 0 역산은 비선형이라 하지 않는다.

순수 함수다 — 세션·캐시·DB 를 보지 않는다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, NamedTuple, TypeAlias

import pandas as pd

from capa_simulation.services.month_columns import month_label
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.securement_threshold import SecurementThresholds

__all__ = [
    "INVERSE_ABOVE",
    "INVERSE_IMPOSSIBLE",
    "INVERSE_MET",
    "INVERSE_NO_MONTHS",
    "INVERSE_OK",
    "NO_ASSUMPTION",
    "PERCENT_DEFAULT",
    "PERCENT_MAX",
    "PERCENT_MIN",
    "AssumptionEffect",
    "InversePercent",
    "PlanCounts",
    "UpehAssumption",
    "UpehToken",
    "assumption_label",
    "clamp_percent",
    "demand_change_text",
    "effect_text",
    "inverse_text",
    "percent_to_clear_securement",
    "percent_to_clear_target",
    "plan_counts",
    "pull_changes",
    "required_drop",
    "scale_required_equipment",
    "scale_securement_rate",
    "token_factor",
    "token_label",
    "token_months",
    "token_percent",
]

PERCENT_MIN: Final = 80
PERCENT_MAX: Final = 150
PERCENT_DEFAULT: Final = 100
"""100% = 기준정보 그대로(가정 꺼짐)."""

UpehToken: TypeAlias = tuple[int, tuple[int, ...]] | tuple[()]
"""캐시 키에 싣는 가정 — `(퍼센트, 건 달 오름차순)`, 가정이 없으면 `()`."""

NO_ASSUMPTION: UpehToken = ()

MONTH: Final = "생산계획년월"
REQUIRED: Final = "소요대수"
UNIT_CAPACITY: Final = "대당 Capa"

# 역산 결과의 갈래.
INVERSE_OK: Final = "ok"
"""`PERCENT_MIN`~`PERCENT_MAX` 안의 값 — 「이 값으로」 를 그대로 적는다."""
INVERSE_MET: Final = "met"
"""`PERCENT_MIN` 으로도 이미 충족 — 「80% 로도 충족」."""
INVERSE_ABOVE: Final = "above"
"""`PERCENT_MAX` 를 넘어야 한다 — 「150% 로도 못 채움」."""
INVERSE_IMPOSSIBLE: Final = "impossible"
"""가용이 0 인 달이 있다 — 「UPEH 로는 못 채움」."""
INVERSE_NO_MONTHS: Final = "no_months"
"""구간 안에 볼 달이 없다(소요가 없거나 구간이 비었다)."""

# 부동소수 끝자리를 털어 내는 자리 — 계산(`securement_rate._ceil_positive`·`required_shortening`)과
# 같다.
_DECIMALS: Final = 9
_MINUS: Final = "−"


@dataclass(frozen=True)
class UpehAssumption:
    """조건 카드에서 고른 가정 한 벌. `percent` 가 100 이면 꺼진 것이다(구간은 남는다)."""

    percent: int
    start: int
    end: int

    def __post_init__(self) -> None:
        percent = int(self.percent)
        if not PERCENT_MIN <= percent <= PERCENT_MAX:
            raise ValueError(f"UPEH 가정은 {PERCENT_MIN}~{PERCENT_MAX}% 입니다: {percent}")
        first, last = sorted((int(self.start), int(self.end)))
        object.__setattr__(self, "percent", percent)
        object.__setattr__(self, "start", first)
        object.__setattr__(self, "end", last)

    @property
    def active(self) -> bool:
        return self.percent != PERCENT_DEFAULT

    @property
    def factor(self) -> float:
        return self.percent / 100

    def months_within(self, months: Iterable[int]) -> tuple[int, ...]:
        """`months` 가운데 구간에 든 달(오름차순)."""
        return tuple(
            sorted({int(month) for month in months if self.start <= int(month) <= self.end})
        )

    def token(self, months: Iterable[int]) -> UpehToken:
        """캐시 키에 싣는 토큰. 100% 이거나 `months` 와 구간이 겹치지 않으면 `()`."""
        if not self.active:
            return NO_ASSUMPTION
        within = self.months_within(months)
        return (self.percent, within) if within else NO_ASSUMPTION


def token_percent(token: UpehToken) -> int:
    """토큰의 퍼센트. 빈 토큰은 100."""
    return int(token[0]) if token else PERCENT_DEFAULT


def token_factor(token: UpehToken) -> float:
    """토큰의 배수 f. 빈 토큰은 1.0 — 배수는 늘 토큰에서만 나온다."""
    return token_percent(token) / 100


def token_months(token: UpehToken) -> frozenset[int]:
    """토큰이 건 달. 빈 토큰은 빈 집합."""
    return frozenset(int(month) for month in token[1]) if token else frozenset()


def assumption_label(assumption: UpehAssumption) -> str:
    """머리 배지·CSV 표지 글 — 「UPEH 가정 110% · 26-07–26-12」."""
    span = f"{_month_dash(assumption.start)}–{_month_dash(assumption.end)}"
    return f"UPEH 가정 {assumption.percent}% · {span}"


def token_label(token: UpehToken) -> str:
    """토큰의 글 — 건 달의 처음·끝으로 「UPEH 가정 110% · 26-07–26-12」. 빈 토큰은 빈 글자."""
    if not token:
        return ""
    months = sorted(token_months(token))
    return f"UPEH 가정 {token_percent(token)}% · {_month_dash(months[0])}–{_month_dash(months[-1])}"


def clamp_percent(value: int) -> int:
    """「이 값으로」 가 적을 값 — 입력 칸의 범위 안으로 깎는다(입력 칸은 범위 밖 값을 거절한다)."""
    return max(PERCENT_MIN, min(PERCENT_MAX, int(value)))


def demand_change_text(percent: int) -> str:
    """「소요 −9.1%」 — 소요대수가 몇 % 바뀌는지(1/f − 1). +10% 가 −10% 가 아님을 글로 보인다."""
    change = 100 / percent - 1
    if round(change, 6) == 0:
        return "소요 그대로"
    sign = "+" if change > 0 else _MINUS
    return f"소요 {sign}{abs(change) * 100:.1f}%"


# ================================================================== 사후 배수


def scale_required_equipment(frame: pd.DataFrame, token: UpehToken) -> pd.DataFrame:
    """소요대수 프레임의 구간 달 행에 소요대수 ÷f, (있으면) 대당 Capa ×f 를 건 **사본**.

    빈 토큰이면 받은 프레임을 그대로 돌려준다. 받은 프레임은 고치지 않는다 — 로더 프레임은 같은
    회차의 다른 쓰임(달 범위·교차검증)과 같은 객체다. `attrs`(제외 목록 등)는 사본에도 실린다.
    """
    if not token or frame.empty or MONTH not in frame.columns or REQUIRED not in frame.columns:
        return frame
    factor = token_factor(token)
    scaled = frame.copy()
    inside = pd.to_numeric(scaled[MONTH], errors="coerce").isin(list(token_months(token)))
    inside = inside.fillna(False).astype(bool)
    # 칸의 dtype(계산 결과는 `Float64`)은 그대로 둔다 — 구간 달 값만 나누고 곱한다.
    demand = pd.to_numeric(scaled[REQUIRED], errors="coerce")
    scaled[REQUIRED] = demand.where(~inside, demand / factor)
    if UNIT_CAPACITY in scaled.columns:
        capacity = pd.to_numeric(scaled[UNIT_CAPACITY], errors="coerce")
        scaled[UNIT_CAPACITY] = capacity.where(~inside, capacity * factor)
    return scaled


def scale_securement_rate(rate: pd.DataFrame, token: UpehToken) -> pd.DataFrame:
    """확보율 프레임(`calculate_securement_rate` 결과)에 가정을 건 새 확보율 프레임.

    구간 달 행의 소요대수를 ÷f 한 뒤 **같은 함수**(`calculate_securement_rate`)로 다시 낸다 — 산식을
    여기 다시 쓰지 않는다. 빈 토큰이면 받은 프레임을 그대로 돌려준다. **이 결과를 시나리오 키만 쓰는
    캐시 칸(`get_securement_rate`·`get_scenario_securement_rate`)에 넘기지 않는다** — HOME 과 같은
    칸이다.
    """
    if not token or rate.empty:
        return rate
    demand = scale_required_equipment(rate.loc[:, [MONTH, "공정", REQUIRED]], token)
    return calculate_securement_rate(rate.loc[:, [MONTH, "공정", "가용대수"]], demand)


# ================================================================== 역산


class InversePercent(NamedTuple):
    """역산 한 줄 — 모자람이 없어지는 가장 작은 정수 %와 그 갈래(`INVERSE_*`)."""

    status: str
    percent: int | None = None
    """그 갈래의 값. `INVERSE_OK` 는 그 %, `INVERSE_ABOVE` 는 계산한 % 그대로(150 초과),
    `INVERSE_MET`·`INVERSE_IMPOSSIBLE`·`INVERSE_NO_MONTHS` 는 None 이다."""

    @property
    def button_value(self) -> int | None:
        """「이 값으로」 가 적을 값. 단추를 둘 갈래가 아니면 None."""
        return self.percent if self.status == INVERSE_OK else None


def percent_to_clear_target(
    process_months: pd.DataFrame, months: Iterable[int], *, skip_states: Sequence[str] = ()
) -> InversePercent:
    """구간 안 단축 0 — 구간 달마다 `목표대수 ÷ f ≤ 가용대수`(설비 일정 기준, 단축 전) 가 서는 최소
    %.

    `process_months` 는 공식 계획의 공정·월 표(`LevelPlan.process_months` 를 볼 공정으로 거른 것)다.
    목표대수 = 소요 × 목표라 소요를 ÷f 하면 목표대수도 ÷f 다. 목표대수가 0 인 달은 보지 않는다.
    `skip_states` 의 상태인 달(「기한 지남」 — 당겨서 바꿀 수 없는 달)도 보지 않는다.
    """
    rows = _month_rows(process_months, {int(month) for month in months})
    if skip_states and "상태" in rows.columns:
        kept = ~rows["상태"].astype("string").isin(list(skip_states)).fillna(False)
        rows = rows.loc[kept.to_numpy()]
    pairs = [
        (float(target), float(available))
        for target, available in zip(
            pd.to_numeric(rows["목표대수"], errors="coerce").fillna(0.0),
            pd.to_numeric(rows["가용대수"], errors="coerce").fillna(0.0),
            strict=True,
        )
        if round(float(target), _DECIMALS) > 0
    ]

    def met(factor: float) -> bool:
        return all(round(need / factor - supply, _DECIMALS) <= 0 for need, supply in pairs)

    return _inverse(pairs, met)


def percent_to_clear_securement(
    summary: pd.DataFrame, thresholds: SecurementThresholds, months: Iterable[int]
) -> InversePercent:
    """확보기준 미달 0 — 구간 달마다 판정이 확보가 되는 최소 %(공식 가용 기준).

    `summary` 는 공식 요약(`build_process_capa_summary` — 생산계획년월·가용대수·소요대수)이다. 그 달
    확보율 = 가용 ÷ (소요 ÷ f) 를 `thresholds.status` 한 길로 판정해 확보인지 본다. 소요가 0 인 달은
    보지 않는다.
    """
    rows = _month_rows(summary, {int(month) for month in months})
    found: list[tuple[int, float, float]] = []
    for month, supply, need in zip(
        pd.to_numeric(rows[MONTH], errors="coerce"),
        pd.to_numeric(rows["가용대수"], errors="coerce").fillna(0.0),
        pd.to_numeric(rows[REQUIRED], errors="coerce").fillna(0.0),
        strict=True,
    ):
        if not pd.isna(month) and float(need) > 0:
            found.append((int(month), float(need), float(supply)))
    pairs = [(need * thresholds.secure_for(month), supply) for month, need, supply in found]

    def met(factor: float) -> bool:
        return all(
            thresholds.status(supply / (need / factor), month) == "secure"
            for month, need, supply in found
        )

    return _inverse(pairs, met)


def _inverse(pairs: Sequence[tuple[float, float]], met: Callable[[float], bool]) -> InversePercent:
    """`pairs` = (f=1 에서 필요한 양, 가용). 필요 ÷ f ≤ 가용 이 되는 최소 정수 % 를 찾는다.

    닫힌 식(`ceil(max 필요 ÷ 가용 × 100)`)으로 낸 뒤 실제 판정(`met`)으로 한 번 더 맞춰 본다 —
    부동소수 끝자리 때문에 경계에서 1% 가 모자라면 올린다.
    """
    if not pairs:
        return InversePercent(INVERSE_NO_MONTHS)
    if any(round(supply, _DECIMALS) <= 0 for _, supply in pairs):
        return InversePercent(INVERSE_IMPOSSIBLE)
    ratio = max(need / supply for need, supply in pairs)
    percent = max(1, math.ceil(round(ratio * 100, _DECIMALS)))
    for _ in range(3):
        if met(percent / 100):
            break
        percent += 1
    if percent <= PERCENT_MIN and met(PERCENT_MIN / 100):
        return InversePercent(INVERSE_MET)
    percent = max(percent, PERCENT_MIN)
    if percent > PERCENT_MAX:
        return InversePercent(INVERSE_ABOVE, percent)
    return InversePercent(INVERSE_OK, percent)


def inverse_text(goal: str, inverse: InversePercent) -> str:
    """역산 한 줄 글 — 「구간 안 단축 0 → UPEH ≥ 118%」 꼴."""
    if inverse.status == INVERSE_OK:
        return f"{goal} → UPEH ≥ {inverse.percent}%"
    if inverse.status == INVERSE_MET:
        return f"{goal} → {PERCENT_MIN}% 로도 충족"
    if inverse.status == INVERSE_ABOVE:
        return f"{goal} → {PERCENT_MAX}% 로도 못 채움(필요 {inverse.percent}%)"
    if inverse.status == INVERSE_IMPOSSIBLE:
        return f"{goal} → UPEH 로는 못 채움(가용 0 인 달)"
    return f"{goal} → 구간 안에 볼 달이 없음"


# ================================================================== 효과


class PlanCounts(NamedTuple):
    """단축 계획 한 벌의 셈 — 정수 대수와 연속값."""

    shortened: int
    """당긴 호기 수(구분 「단축」)."""

    days: int
    """단축일수 합계."""

    new: int
    """신규 필요(추가N) 대수."""

    max_gap: float
    """월 최대 환산 부족(단축 전, 0 이상) — 공정·월 표의 과부족 음수 크기의 최댓값."""


def plan_counts(
    units: pd.DataFrame,
    process_months: pd.DataFrame,
    processes: Iterable[str] | None = None,
) -> PlanCounts:
    """`LevelPlan` 의 호기 표·공정·월 표를 센다. `processes` 를 주면 그 공정만."""
    unit_rows = _process_rows(units, processes)
    month_rows = _process_rows(process_months, processes)
    kinds = (
        unit_rows["구분"].astype("string")
        if "구분" in unit_rows.columns
        else pd.Series(dtype="string")
    )
    shortened = kinds.eq("단축").fillna(False)
    days = (
        pd.to_numeric(unit_rows.loc[shortened.to_numpy(), "단축일수"], errors="coerce")
        if "단축일수" in unit_rows.columns
        else pd.Series(dtype="float64")
    )
    gaps = (
        pd.to_numeric(month_rows["과부족"], errors="coerce")
        if "과부족" in month_rows.columns
        else pd.Series(dtype="float64")
    )
    worst = float(-gaps.min()) if not gaps.dropna().empty and float(gaps.min()) < 0 else 0.0
    return PlanCounts(
        shortened=int(shortened.sum()),
        days=int(days.fillna(0).sum()),
        new=int(kinds.eq("신규").fillna(False).sum()),
        max_gap=round(worst, _DECIMALS),
    )


class AssumptionEffect(NamedTuple):
    """효과 줄 한 벌 — 공식 → 가정."""

    percent: int
    applied: bool
    """토큰이 비지 않았는가(구간이 이 화면의 달과 겹치는가)."""

    required_drop: float = 0.0
    """구간 달의 월 최대 소요 감소 대수(공식 − 가정, 100% 미만이면 음수)."""

    official: PlanCounts | None = None
    assumed: PlanCounts | None = None
    shortage_months: tuple[int, int] | None = None
    """확보기준 미달 달 수 (공식, 가정) — 공정 Capa 상세만."""


def effect_text(effect: AssumptionEffect) -> str:
    """효과 줄 — 「소요 −9.1%(월 최대 −1.13대) · 단축 호기 3→2 · 단축일 합계 45→12일 · …」.

    정수 대수가 그대로인데 단축일만 줄면 「부족이 남아 같은 호기를 덜 당김(−n일)」 으로 풀어 적는다.
    구간이 이 화면의 달과 겹치지 않으면 「적용된 달 없음」 이다.
    """
    if not effect.applied:
        return (
            f"UPEH 가정 {effect.percent}% — 적용된 달 없음(구간이 이 화면의 달과 겹치지 않습니다)"
        )
    drop = effect.required_drop
    parts = [
        demand_change_text(effect.percent)
        + (f"(월 최대 {_signed_two(-drop)}대)" if round(drop, 2) != 0 else "")
    ]
    if effect.shortage_months is not None:
        before, after = effect.shortage_months
        parts.append(f"확보기준 미달 {before}→{after}개월")
    official, assumed = effect.official, effect.assumed
    if official is not None and assumed is not None:
        parts += [
            f"단축 호기 {official.shortened}→{assumed.shortened}",
            f"단축일 합계 {official.days}→{assumed.days}일",
            f"신규 {official.new}→{assumed.new}",
            f"월 최대 환산 부족 {official.max_gap:,.2f}→{assumed.max_gap:,.2f}",
        ]
        same_units = (official.shortened, official.new) == (assumed.shortened, assumed.new)
        if same_units and official.days != assumed.days:
            change = assumed.days - official.days
            verb = "덜" if change < 0 else "더"
            parts.append(f"부족이 남아 같은 호기를 {verb} 당김({_signed_int(change)}일)")
    return " · ".join(parts)


def pull_changes(
    official_units: pd.DataFrame, assumed_units: pd.DataFrame, process: str
) -> dict[str, tuple[int, int]]:
    """공식 계획에서 당긴 호기 가운데 가정 계획에서 덜 당기거나 안 당기는 호기 → (공식 일, 가정 일).

    가정 계획에서 더 당기는 호기도 든다(100% 미만). 같은 날수면 들지 않는다. 추가N 은 이름이
    계획마다 새로 붙어 짝지을 수 없으므로 보지 않는다.
    """
    official = _pulled_days(official_units, process)
    assumed = _pulled_days(assumed_units, process)
    return {
        unit: (days, assumed.get(unit, 0))
        for unit, days in official.items()
        if assumed.get(unit, 0) != days
    }


def _pulled_days(units: pd.DataFrame, process: str) -> dict[str, int]:
    rows = _process_rows(units, [process])
    if rows.empty or not {"호기", "구분", "단축일수"} <= set(rows.columns):
        return {}
    pulled = rows.loc[rows["구분"].astype("string").eq("단축").fillna(False).to_numpy()]
    return {
        str(unit): int(days)
        for unit, days in zip(
            pulled["호기"],
            pd.to_numeric(pulled["단축일수"], errors="coerce").fillna(0),
            strict=True,
        )
    }


# ================================================================== 값 다루기


def _month_rows(frame: pd.DataFrame, months: set[int]) -> pd.DataFrame:
    if frame.empty or MONTH not in frame.columns:
        return frame.iloc[0:0]
    numeric = pd.to_numeric(frame[MONTH], errors="coerce")
    return frame.loc[numeric.isin(list(months)).fillna(False).to_numpy()]


def _process_rows(frame: pd.DataFrame, processes: Iterable[str] | None) -> pd.DataFrame:
    if processes is None or frame.empty or "공정" not in frame.columns:
        return frame
    wanted = {str(process).strip() for process in processes}
    names = frame["공정"].astype("string").str.strip()
    return frame.loc[names.isin(list(wanted)).fillna(False).to_numpy()]


def _month_dash(month: int) -> str:
    """「26-07」 — 배지·CSV 표지의 달 글(화면 달 글 「26.07」 과 겹치지 않게 가른다)."""
    return month_label(int(month)).replace(".", "-")


def _signed_two(value: float) -> str:
    rounded = round(value, 2) + 0.0
    if rounded > 0:
        return f"+{rounded:,.2f}"
    if rounded < 0:
        return f"{_MINUS}{abs(rounded):,.2f}"
    return "0.00"


def _signed_int(value: int) -> str:
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{_MINUS}{abs(value):,}"
    return "0"


def required_drop(official: pd.DataFrame, assumed: pd.DataFrame, months: Iterable[int]) -> float:
    """구간 달의 월 최대 소요 감소(공식 − 가정). 두 프레임은 생산계획년월·소요대수를 갖는다.

    한 달에 공정이 여럿이면 그 달 합으로 견준다 — 같은 달의 공정끼리만 더한다.
    """
    wanted = {int(month) for month in months}
    before = _monthly_required(_month_rows(official, wanted))
    after = _monthly_required(_month_rows(assumed, wanted))
    drops = [before.get(month, 0.0) - after.get(month, 0.0) for month in wanted]
    if not drops:
        return 0.0
    largest: float = max(drops, key=abs)
    return round(largest, _DECIMALS)


def _monthly_required(frame: pd.DataFrame) -> Mapping[int, float]:
    totals: dict[int, float] = {}
    if frame.empty:
        return totals
    for month, value in zip(
        pd.to_numeric(frame[MONTH], errors="coerce"),
        pd.to_numeric(frame[REQUIRED], errors="coerce").fillna(0.0),
        strict=True,
    ):
        if pd.isna(month):
            continue
        totals[int(month)] = totals.get(int(month), 0.0) + float(value)
    return totals
