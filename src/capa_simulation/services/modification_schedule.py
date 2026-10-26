# Purpose: 공정 하나에 N대 × D일 개조를 월별 기준 확보율을 지키며 언제 할지 찾고, 못 맞추면 대안
# 셋을 낸다.

"""개조 일정 — 「제약은 없지만 N대 × D일 개조가 생기면 언제 하면 확보율 기준을 지키나」.

제약 시뮬레이션 화면의 둘째 모드(「제약 영향 | 개조 일정」, 2026-10-26 사용자 결정 3 — 검토 문서
5장 C1~C16 의 권장 기본값 그대로)다. 제약 모드(`constraint_simulation`)는 개조 시점이 가정으로
정해지고 그 결과 확보율을 내는 **정방향**이고, 여기는 「확보율이 기준 밑으로 가지 않게」 가 조건이고
**개조 시점이 답**인 역방향이다. Streamlit·세션·캐시·DB 를 보지 않는다. pandas 는
어댑터(`schedule_month_inputs`) 하나만 쓴다.

**모델.** 보이는 달 j 의 W/D 구간(W_j 일, `wd_window`)에 든 개조 비가동의 대·일 합을 u_j 라 하면

    rate_j = (A_j − u_j / W_j) / R_j

이다 — 제약 모드 가정 5 의 W/D 일할(대수 × 겹친 일수 ÷ W/D 일수의 합)과 같은 좌표다. 그래서
확보율 판정에 드는 것은 달마다 u_j 하나다(5대 × 4일 = 1대 × 20일). 대수는 환산 대수, 호기는 고르지
않는다(대수 모델 — C8). 다만 **같은 날 개조 중인 대수는 그 달 가용을 넘지 않는다** — 날마다 동시
대수 ≤ min(동시 상한, ⌊A_j⌋)(A 가 환산 대수라 내림). 개조 대수 N 이 보이는 어느 달 ⌊A⌋ 보다도
많으면 검증에서 막는다(개조할 설비가 그만큼 없다).

권장 기본값(C1~C16)에서 계산에 걸리는 것:

1. **목적(C1)** — 기본은 모든 달 기준을 지키며 가장 빨리 끝내기(`earliest`). 기한이 있을 때만
   「가장 고르게」(`even` — 기한 안에서 개조가 든 달의 **기준 대비 여유**(확보율 − G(m)) 최솟값을
   가장 크게)를 고를 수 있다.
2. **시작·기한(C2)** — 가장 이른 시작(`earliest`, 화면은 내일 또는 고른 달 W/D 첫날)과 끝 날
   상한(`deadline`, 화면은 「X월 W/D 첫날 전」 = 그 첫날 − 1일). 보이는 첫 달 W/D 첫날보다 앞,
   보이는 마지막 달 W/D 끝 날보다 뒤에는 넣지 않는다(조회기간 밖은 A 를 모른다).
3. **동시 개조 상한(C3)** — 기본 없음(`None` — 그래도 그 달 ⌊A⌋ 는 넘지 않는다). 결과에 최대 동시
   대수를 낸다.
4. **시작일 격자(C5)** — 날 단위가 기본, 달 맞춤 창(`aligned` — 그 달 W/D 끝 날에 끝나는 창, 제약
   모드 창 꼴)은 선택지다. 같은 날 시작하는 묶음을 한 차수로 적는다(C4).
5. **개조 중·뒤(C6·C7)** — 개조 중 완전 비가동, 끝나면 원래 능력으로 일반 가용에 돌아온다.
6. **기준과 여유(C10·C11)** — 배치 기준은 그 달 G + 안전 여유 δ(기본 0). 개조 없이도 배치 기준
   미달인 달(`blocked`)에는 하루도 넣지 않는다. R 0 달은 가용이 음수가 아니기만 본다. 판정은
   `constraint_simulation.secure`(→ `capacity_status`) 한 길이다(AGENTS 6장 「판정은 한 길」).
7. **못 맞출 때(C12)** — 기한(없으면 조회기간 끝)까지 넣을 수 있는 대수 · 기한 없이 끝나는 날 ·
   기한을 지키려면 필요한 기준 완화 %p 를 함께 낸다(`ScheduleShortfall`). 0% 까지 낮춰도 못 넣으면
   그 까닭(넣을 창이 없음 · 동시 상한 · 가용)을 가른다.

**알고리즘(검토 3-2 + 완전 탐색).** 판정은 달마다 「대·일 합 ≤ 그 달 예산」(`_Model.caps` — 확보율
판정을 정수 대·일로 옮긴 값)과 날마다 「동시 대수 ≤ 그 달 동시 한도」 둘이다. 먼저 빠른 탐욕 둘을
돌린다 — 시작 후보(날 단위면 모든 날, 달 맞춤이면 달마다 하나)를 차례로 보며 그날 넣을 수 있는 만큼
넣는 이른 시작(EARLY)과, 완료 달 L 의 W/D 끝 날에서 거꾸로 채우는 늦은 시작(LATE). 탐욕이 「1대는
일찍 · 1대는 중간 · 1대는 늦게」 같은 나눠 넣기를 놓치는 자리는 **되짚기 완전 탐색**(`_Model.search`
— 시작을 차례로 고르는 깊이 우선, 실패 상태 기억 · 예산 합 · 동시 한도 가지치기)이 메운다. 완전
탐색은 실제 크기에서 「안 된다」 를 증명하는 데 지수 시간이 들 수 있어 마디 한도 안에서만 돈다(한 번
`SEARCH_CALL_NODES` · 한 계산 `SEARCH_NODE_LIMIT`). 대안 셋(「못 넣음」 · 넣을 수 있는 대수 · 필요
완화 · 까닭)을 세우는 탐색이 한도에 걸리면 그 셋은 **이 계산으로 찾은 범위**다
(`ScheduleShortfall.exact` 거짓 — 화면이 적는다). 완료 달 앞당기기와 「가장 고르게」 δ 의 탐색은
찾으면 쓰고 못 찾으면 탐욕 결과를 둔다(최적을 증명하지 않는다). EARLY 의 완료 달보다 앞 달 L 부터
차례로 LATE · 완전 탐색이 N 대를 다 넣으면 그 L 이 답이고, 없으면 EARLY 가 답이다. 「가장
고르게」 는 「다 드는가」 를 δ 에 대해 이분 탐색해(위 끝 = 열린 달의 A/R − G 가운데 가장 큰 값 —
그보다 큰 δ 는 결과가 같다) 그 δ 로 푼다. 필요한 기준 완화도 같은 이분 탐색이다.

**기준을 지키는 것은 늘 보장한다** — 모든 배치가 판정을 지나야만 기록되고, 결과 확보율도 같은
정수 대·일 합으로 낸다. 작은 무작위 문제(실수 R·A·G · 여유 · 기한 · 목적 · 동시 상한 · Cut-off ·
넓은 예산)를 따로 짠 완전 탐색과 맞댄 시험이 완료 달 · 넣은 대수 · 필요 완화 · 까닭 · 「가장
고르게」 δ 를 본다(`tests/test_modification_schedule.py`).

개조가 설비 DB(설비 시나리오) 비가동에 이미 들어 있으면 가용 A 에서 이미 빠져 있어 두 번 빠진다 —
화면은 「아직 일정에 넣지 않은 개조만」 이라고 적는다(C9). 저장하지 않는다(C13).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal, NamedTuple

import pandas as pd

from capa_simulation.services.constraint_simulation import (
    MODIFICATION_DAYS_RANGE,
    NEED_TOLERANCE,
    secure,
)
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "CONCURRENT_RANGE",
    "MARGIN_RANGE",
    "SEARCH_CALL_NODES",
    "SEARCH_NODE_LIMIT",
    "SEARCH_RESOLUTION",
    "UNITS_RANGE",
    "Objective",
    "ScheduleBatch",
    "ScheduleConditions",
    "ScheduleMonth",
    "ScheduleMonthInput",
    "ScheduleResult",
    "ScheduleShortfall",
    "ShortfallCause",
    "Strategy",
    "plan_modification_schedule",
    "schedule_month_inputs",
    "whole_units",
]

Objective = Literal["earliest", "even"]
"""`earliest` = 가장 빨리 끝내기(기본), `even` = 기한 안에서 가장 고르게(기한이 있어야 한다)."""

Strategy = Literal["early", "late", "search"]
"""답이 된 길 — 이른 시작 탐욕(`early`) · 완료 달 고정 늦은 시작 탐욕(`late`) · 완전
탐색(`search`)."""

ShortfallCause = Literal["window", "concurrent", "capacity"]
"""기준을 0% 까지 낮춰도 못 넣는 까닭 — 시작 ~ 끝 날 상한이 개조 기간보다 짧거나 넣을 날이 없음
(`window`), 사용자 동시 상한(`concurrent` — 상한을 걷으면 들어간다), 가용(`capacity`)."""

UNITS_RANGE: Final = (1, 500)
"""개조 대수(환산 대수, 정수)."""

CONCURRENT_RANGE: Final = (1, 500)
"""동시 개조 상한(대)."""

MARGIN_RANGE: Final = (0.0, 0.3)
"""안전 여유(비율 — 0.01 = 1%p). 기준에 더하기만 한다."""

SEARCH_RESOLUTION: Final = 2e-8
"""δ 이분 탐색 끝 폭(비율 — 0.000002%p). 위 끝이 데이터에서 오므로 횟수는 폭에서 정한다."""

_SEARCH_STEPS_LIMIT: Final = 64

SEARCH_CALL_NODES: Final = 4_000
"""완전 탐색 한 번의 마디 한도."""

SEARCH_NODE_LIMIT: Final = 40_000
"""한 계산(`plan_modification_schedule` 한 번)의 완전 탐색 마디 한도 — 대안 셋을 세우는 탐색과 그 밖
(완료 달 앞당기기 · 「가장 고르게」 δ)의 탐색이 따로 이만큼씩 쓴다. 대안 셋 쪽이 다 쓰면
`ScheduleShortfall.exact` 가 거짓이다."""


def whole_units(available: float) -> int:
    """그 달 가용(환산 대수)의 내림 — 같은 날 개조할 수 있는 가장 많은 대수(음수면 0)."""
    return max(0, math.floor(available + NEED_TOLERANCE))


# ================================================================== 입력·출력


@dataclass(frozen=True)
class ScheduleMonthInput:
    """보이는 달 하나의 입력(그 공정 하나)."""

    month: int
    """`YYYYMM`."""

    required: float
    """R — 공정 소요대수."""

    available: float
    """A — 설비 일정 기준 가용(환산 대수, 단축 전)."""

    general_target: float
    """G(m) — 그 달 기준 확보율(비율). 0 보다 크기만 하면 된다."""


@dataclass(frozen=True)
class ScheduleConditions:
    """화면이 고른 조건. 값으로 같고 해시된다(세션 memo 키 원소)."""

    units: int
    """N — 개조할 대수(환산)."""

    days: int
    """D — 한 대의 개조 일수(이어진 날)."""

    cutoff_days: int
    """그 공정의 Cut-off(내림 일수 — `wd_window` 와 같다)."""

    earliest: date
    """가장 이른 시작(포함)."""

    deadline: date | None = None
    """개조 끝 날 상한(포함). None 이면 보이는 마지막 달 W/D 끝 날."""

    concurrent: int | None = None
    """동시 개조 상한(대). None 이면 없음(그래도 그 달 ⌊A⌋ 는 넘지 않는다)."""

    margin: float = 0.0
    """안전 여유 δ(비율). 배치 기준 = G + δ."""

    objective: Objective = "earliest"
    aligned: bool = False
    """달 맞춤 창 — 시작 후보를 「그 달 W/D 끝 날에 끝나는 창」 으로만 둔다."""


@dataclass(frozen=True)
class ScheduleBatch:
    """한 차수 — 같은 날 시작하는 `units` 대."""

    start: date
    units: int
    days: int
    shares: tuple[tuple[int, int], ...]
    """(보이는 달, 그 W/D 구간과 겹친 일수) — 걸친 달 차례."""

    @property
    def last_day(self) -> date:
        """비가동 마지막 날(포함)."""
        return self.start + timedelta(days=self.days - 1)

    @property
    def end(self) -> date:
        """일반 가용으로 돌아오는 날(불포함 끝 경계)."""
        return self.start + timedelta(days=self.days)


@dataclass(frozen=True)
class ScheduleMonth:
    """보이는 달 하나의 결과."""

    month: int
    window_first_day: date
    window_last_day: date
    window_days: int
    required: float
    available: float
    general_target: float
    """G(m) — 판정(`secure_after`) 기준."""

    threshold: float
    """배치 기준 = G(m) + 적용 여유."""

    open: bool
    """그 W/D 구간에 넣을 수 있는 날이 있다(가장 이른 시작 ~ 끝 날 상한과 겹친다)."""

    blocked: bool
    """개조 없이도 G(m) + 안전 여유 미달 — 비가동을 넣지 않은 달(C11). 「가장 고르게」 가 올린 δ
    때문에만 비는 달은 아니다(그런 달은 개조 뒤 확보율이 배치 기준 밑이라 비가동이 들지 못할
    뿐이다)."""

    concurrent_cap: int
    """그 달 날마다의 동시 개조 한도 = min(동시 상한, ⌊A⌋)."""

    downtime_unit_days: int
    """그 W/D 구간에 든 개조 비가동 대·일 합."""

    downtime: float
    """환산 비가동 대수 = 대·일 ÷ W/D 일수."""

    slack: float
    """배치 기준 여유(대) = A − 배치 기준 × R. 음수면 그 기준으로는 비가동이 들 수 없다."""

    baseline_rate: float | None
    """개조 전 = A ÷ R. R 0 이면 None."""

    rate: float | None
    """개조 뒤 = (A − 비가동) ÷ R. R 0 이면 None."""

    baseline_secure: bool | None
    secure_after: bool | None
    """개조 뒤 확보율이 G(m)(여유 없이) 이상인가."""

    @property
    def margin(self) -> float | None:
        """기준 대비 여유 = 개조 뒤 확보율 − G(m). R 0 이면 None."""
        return None if self.rate is None else self.rate - self.general_target


@dataclass(frozen=True)
class ScheduleShortfall:
    """N 대를 다 넣지 못했을 때의 대안 셋(C12)."""

    placed: int
    """끝 날 상한까지 넣을 수 있는 대수."""

    by_deadline: bool
    """끝 날 상한이 사용자 기한이다(아니면 조회기간 끝)."""

    finish_without_deadline: date | None
    """기한 없이(조회기간 끝까지) 다 넣으면 끝나는 날. 기한이 없었거나 그래도 못 넣으면 None."""

    finish_month_without_deadline: int | None
    relief: float | None
    """끝 날 상한 안에 다 넣으려면 배치 기준에서 낮춰야 하는 폭(비율, 양수). 0% 까지 낮춰도 못
    넣으면 None."""

    cause: ShortfallCause | None = None
    """`relief` 가 None 일 때 그 까닭(아니면 None)."""

    exact: bool = True
    """넣을 수 있는 대수 · 필요 완화 · 까닭을 완전 탐색이 마디 한도 안에서 확인했다. 거짓이면 이
    계산으로 찾은 범위다 — 실제로는 더 넣거나 덜 낮춰도 될 수 있다(적힌 완화는 그래도 늘
    충분하다)."""


@dataclass(frozen=True)
class ScheduleResult:
    conditions: ScheduleConditions
    months: tuple[ScheduleMonth, ...]
    batches: tuple[ScheduleBatch, ...]
    first_day: date
    """넣을 수 있는 첫날(가장 이른 시작과 보이는 첫 달 W/D 첫날 중 늦은 날)."""

    last_day: date
    """끝 날 상한(기한과 보이는 마지막 달 W/D 끝 날 중 이른 날)."""

    applied_margin: float
    """배치에 쓴 δ — 「가장 빨리」 는 안전 여유, 「가장 고르게」 는 찾은 가장 큰 δ."""

    strategy: Strategy
    placed: int
    finish_day: date | None
    """다 넣었을 때 마지막 차수의 끝 날. 못 넣으면 None."""

    finish_month: int | None
    """`finish_day` 가 든 보이는 달(W/D)."""

    max_concurrent: int
    tightest_month: int | None
    """비가동이 든 달(R > 0) 가운데 기준 대비 여유(확보율 − G(m))가 가장 작은 달(같으면 이른 달)
    — 「가장 고르게」 가 키우는 바로 그 값이다."""

    tightest_rate: float | None
    """그 달 개조 뒤 확보율."""

    tightest_margin: float | None
    """그 달 개조 뒤 확보율 − G(m)."""

    shortfall: ScheduleShortfall | None
    fell_back: bool = False
    """「가장 고르게」 인데 안전 여유만으로도 기한을 못 맞춰 「가장 빨리」 로 풀었다."""

    @property
    def complete(self) -> bool:
        return self.placed >= self.conditions.units

    @property
    def remaining(self) -> int:
        return self.conditions.units - self.placed

    def month(self, month: int) -> ScheduleMonth:
        """그 달의 결과. 보이는 달이 아니면 KeyError."""
        for row in self.months:
            if row.month == month:
                return row
        raise KeyError(f"보이는 달이 아닙니다: {month}")


# ================================================================== 검증


def _valid_month(value: int) -> bool:
    year, month = divmod(int(value), 100)
    return 1001 <= year <= 9999 and 1 <= month <= 12


def _require_finite_non_negative(value: float, message: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(message)


def _require_positive(value: float, message: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(message)


def _validate(months: Sequence[ScheduleMonthInput], conditions: ScheduleConditions) -> None:
    if not months:
        raise ValueError("보이는 달이 없어 개조 일정을 찾을 수 없습니다.")
    if not UNITS_RANGE[0] <= conditions.units <= UNITS_RANGE[1]:
        raise ValueError(
            f"개조 대수는 {UNITS_RANGE[0]}~{UNITS_RANGE[1]}대여야 합니다: {conditions.units}"
        )
    if not MODIFICATION_DAYS_RANGE[0] <= conditions.days <= MODIFICATION_DAYS_RANGE[1]:
        raise ValueError(
            f"개조 기간은 {MODIFICATION_DAYS_RANGE[0]}~{MODIFICATION_DAYS_RANGE[1]}일이어야 "
            f"합니다: {conditions.days}"
        )
    if conditions.concurrent is not None and not (
        CONCURRENT_RANGE[0] <= conditions.concurrent <= CONCURRENT_RANGE[1]
    ):
        raise ValueError(
            f"동시 개조 상한은 {CONCURRENT_RANGE[0]}~{CONCURRENT_RANGE[1]}대여야 합니다: "
            f"{conditions.concurrent}"
        )
    if not (
        math.isfinite(conditions.margin) and MARGIN_RANGE[0] <= conditions.margin <= MARGIN_RANGE[1]
    ):
        raise ValueError(
            f"안전 여유는 {MARGIN_RANGE[0] * 100:g}~{MARGIN_RANGE[1] * 100:g}%p 여야 합니다: "
            f"{conditions.margin}"
        )
    if conditions.objective not in ("earliest", "even"):
        raise ValueError(f"목적은 earliest·even 가운데 하나여야 합니다: {conditions.objective}")
    if conditions.objective == "even" and conditions.deadline is None:
        raise ValueError("「가장 고르게」 는 기한이 있어야 합니다.")
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
        _require_finite_non_negative(
            row.required, f"{row.month} 공정 소요가 0 이상의 수가 아닙니다."
        )
        _require_finite_non_negative(
            row.available, f"{row.month} 가용대수가 0 이상의 수가 아닙니다."
        )
        _require_positive(row.general_target, f"{row.month} 기준 확보율은 0 보다 큰 수여야 합니다.")
    fleet = max(whole_units(row.available) for row in months)
    if conditions.units > fleet:
        raise ValueError(
            f"개조 대수 {conditions.units}대가 이 공정 가용보다 많습니다 — 보이는 달 가운데 가용이 "
            f"가장 많은 달도 {fleet}대(환산 대수 내림)입니다. 지금 있는 설비 가운데 아직 개조하지 "
            "않은 대수만 넣으세요."
        )


# ================================================================== 날 칸 모델


class _Placement(NamedTuple):
    """한 번 넣은 결과 — (시작 칸, 대수) 시작 차례·넣은 대수·답이 된 길."""

    batches: tuple[tuple[int, int], ...]
    placed: int
    strategy: Strategy


class _Exhausted(Exception):
    """완전 탐색 마디 한도를 다 썼다."""


_Pooled = tuple[int, tuple[tuple[int, int], ...], int]
"""완전 탐색 후보 — (시작 칸, 겹친 (달 차례, 일수), 시작 칸의 달 차례)."""


class _Model:
    """조건 하나에 고정된 날 칸 모델. 칸 0 = 넣을 수 있는 첫날(`first_day`).

    대·일 합은 늘 정수다(대수 × 겹친 일수) — 배치 판정과 결과 확보율이 같은 수를 보므로 부동소수
    잡음이 둘을 갈라 놓지 않는다. 판정은 달마다 정수 예산(`caps` — 확보율 판정을 대·일로 옮긴 값)과
    달마다 날 동시 한도(`month_caps`) 둘이다.
    """

    def __init__(
        self, months: Sequence[ScheduleMonthInput], conditions: ScheduleConditions
    ) -> None:
        self.rows = tuple(months)
        self.conditions = conditions
        self.windows: tuple[WdWindow, ...] = tuple(
            wd_window(row.month, conditions.cutoff_days) for row in self.rows
        )
        self.days = conditions.days
        self.units = conditions.units
        self.first_day = max(conditions.earliest, self.windows[0].first_day)
        horizon = self.windows[-1].boundary_end
        self.horizon_offset = (horizon - self.first_day).days
        self.limit_day = (
            horizon if conditions.deadline is None else min(conditions.deadline, horizon)
        )
        self.limit_offset = (self.limit_day - self.first_day).days
        # 달마다 칸 범위 [a_j, b_j](잘리지 않은 값 — 첫날 앞이면 음수). 이웃 달이 이어지지 않으면
        # 그 사이 날은 어느 달에도 들지 않아 그 날을 지나는 창을 두지 않는다(A 를 모른다).
        self.spans_of_month = tuple(
            (
                (window.first_day - self.first_day).days,
                (window.boundary_end - self.first_day).days,
            )
            for window in self.windows
        )
        self.minimum_target = min(row.general_target for row in self.rows)
        self.whole = tuple(whole_units(row.available) for row in self.rows)
        concurrent = conditions.concurrent
        capped = tuple(
            whole if concurrent is None else min(whole, concurrent) for whole in self.whole
        )
        self.concurrent_caps = capped
        self.month_caps = self._binding(capped)
        self.free_month_caps = self._binding(self.whole)
        # 대안 셋을 세우는 탐색(True)과 그 밖(False)의 남은 마디.
        self.nodes_left = {True: SEARCH_NODE_LIMIT, False: SEARCH_NODE_LIMIT}
        self.exhausted = False
        """대안 셋을 세우는 탐색이 마디 한도에 걸렸다."""
        self._overlaps: dict[int, tuple[tuple[int, int], ...] | None] = {}
        self._caps: dict[float, tuple[int, ...]] = {}
        self._day_month: list[int | None] = [
            self._scan_month(offset) for offset in range(max(self.horizon_offset + 1, 0))
        ]

    def _binding(self, caps: tuple[int, ...]) -> tuple[int, ...] | None:
        """날 동시 한도 — 어느 달도 N 대를 막지 않으면 None(보지 않는다)."""
        return caps if any(cap < self.units for cap in caps) else None

    # ------------------------------------------------------------ 날 칸

    def day(self, offset: int) -> date:
        return self.first_day + timedelta(days=offset)

    def _scan_month(self, offset: int) -> int | None:
        for index, (start, end) in enumerate(self.spans_of_month):
            if start <= offset <= end:
                return index
        return None

    def month_index(self, offset: int) -> int | None:
        """칸 `offset` 이 든 보이는 달 차례(보이는 달 밖·사이 날이면 None)."""
        if 0 <= offset < len(self._day_month):
            return self._day_month[offset]
        return self._scan_month(offset)

    def last_month_until(self, offset: int) -> int:
        """칸 `offset` 까지 시작하는 마지막 달 차례(없으면 −1)."""
        found = -1
        for index, (start, _) in enumerate(self.spans_of_month):
            if start <= offset:
                found = index
        return found

    def overlap(self, start: int) -> tuple[tuple[int, int], ...] | None:
        """칸 `start` 에서 시작하는 창이 겹치는 (달 차례, 일수).

        보이는 달 밖·사이 날을 지나면 None.
        """
        if start in self._overlaps:
            return self._overlaps[start]
        last = start + self.days - 1
        found: list[tuple[int, int]] = []
        cursor = start
        index = self.month_index(start)
        while index is not None and cursor <= last:
            _, month_end = self.spans_of_month[index]
            stop = min(month_end, last)
            found.append((index, stop - cursor + 1))
            cursor = stop + 1
            if cursor > last:
                break
            following = index + 1
            if following >= len(self.spans_of_month):
                index = None
            elif self.spans_of_month[following][0] != cursor:
                index = None
            else:
                index = following
        result = tuple(found) if cursor > last else None
        self._overlaps[start] = result
        return result

    def candidates(self, limit: int) -> list[int]:
        """끝 날 칸이 `limit` 이하인 시작 칸 — 날 단위면 모든 날, 달 맞춤이면 달 끝마다 하나."""
        latest = limit - self.days + 1
        if latest < 0:
            return []
        if not self.conditions.aligned:
            return list(range(0, latest + 1))
        starts = [end - self.days + 1 for _, end in self.spans_of_month]
        return [start for start in starts if 0 <= start <= latest]

    def is_open(self, index: int, limit: int) -> bool:
        month_start, month_end = self.spans_of_month[index]
        return month_end >= 0 and month_start <= limit

    # ------------------------------------------------------------ 판정

    def ok(self, index: int, unit_days: int, target: float) -> bool:
        """그 달 비가동 대·일 합이 `unit_days` 일 때 확보율이 `target` 이상인가(R 0 은 가용 ≥ 0)."""
        row = self.rows[index]
        usable = row.available - unit_days / self.windows[index].days
        if usable < -NEED_TOLERANCE:
            return False
        if row.required <= 0:
            return True
        return secure(usable / row.required, target)

    def _cap(self, index: int, target: float) -> int:
        """`ok` 인 가장 큰 대·일 합(−1 이면 하루도 못 넣는다). 닫힌 식으로 어림한 뒤 판정으로 맞춘다
        — `ok` 는 대·일에 대해 단조라 이 수 하나가 판정과 같다."""
        if not self.ok(index, 0, target):
            return -1
        row = self.rows[index]
        width = self.windows[index].days
        bound = row.available * width
        if row.required > 0:
            bound = min(bound, (row.available - target * row.required) * width)
        count = max(0, math.floor(bound + NEED_TOLERANCE))
        while count > 0 and not self.ok(index, count, target):
            count -= 1
        while self.ok(index, count + 1, target):
            count += 1
        return count

    def caps(self, delta: float) -> tuple[int, ...]:
        """달마다 대·일 예산 — 배치 기준 G(m) + `delta`."""
        held = self._caps.get(delta)
        if held is None:
            held = tuple(
                self._cap(index, row.general_target + delta) for index, row in enumerate(self.rows)
            )
            self._caps[delta] = held
        return held

    def targets(self, delta: float) -> list[float]:
        return [row.general_target + delta for row in self.rows]

    # ------------------------------------------------------------ 한 창에 넣을 수 있는 대수

    def _room(
        self,
        start: int,
        spans: tuple[tuple[int, int], ...],
        caps: tuple[int, ...],
        used: list[int],
        remaining: int,
        month_caps: tuple[int, ...] | None,
        active: list[int] | None,
        *,
        late: bool,
    ) -> int:
        """칸 `start` 에 더 넣을 수 있는 대수 — 남은 대수 · 겹친 달 예산 · 날 동시 한도.

        이미 넣은 차수가 모두 한쪽(이른 시작·완전 탐색은 앞, 늦은 시작은 뒤)에 있어 창 안 동시
        대수는 달 조각 안에서 단조다 — 그래서 조각마다 첫날(앞쪽) 또는 끝 날(뒤쪽) 하루만 보면
        된다.
        """
        take = remaining
        for index, overlap in spans:
            take = min(take, (caps[index] - used[index]) // overlap)
            if take <= 0:
                return 0
        if month_caps is not None and active is not None:
            cursor = start
            for index, overlap in spans:
                busiest = cursor + overlap - 1 if late else cursor
                take = min(take, month_caps[index] - active[busiest])
                if take <= 0:
                    return 0
                cursor += overlap
        return take

    def _apply(
        self,
        start: int,
        spans: tuple[tuple[int, int], ...],
        count: int,
        used: list[int],
        active: list[int] | None,
    ) -> None:
        for index, overlap in spans:
            used[index] += count * overlap
        if active is not None:
            for offset in range(start, start + self.days):
                active[offset] += count

    # ------------------------------------------------------------ 탐욕

    def greedy(
        self,
        caps: tuple[int, ...],
        *,
        limit: int,
        late: bool,
        month_caps: tuple[int, ...] | None,
    ) -> _Placement:
        """시작 후보를 앞(EARLY)·뒤(LATE)부터 보며 그날 넣을 수 있는 만큼 넣는다."""
        used = [0] * len(self.rows)
        active = [0] * (limit + 1) if month_caps is not None else None
        remaining = self.units
        batches: list[tuple[int, int]] = []
        starts = self.candidates(limit)
        if late:
            starts.reverse()
        for start in starts:
            if remaining <= 0:
                break
            spans = self.overlap(start)
            if spans is None:
                continue
            take = self._room(start, spans, caps, used, remaining, month_caps, active, late=late)
            if take <= 0:
                continue
            self._apply(start, spans, take, used, active)
            batches.append((start, take))
            remaining -= take
        ordered = tuple(sorted(batches))
        return _Placement(ordered, self.units - remaining, "late" if late else "early")

    # ------------------------------------------------------------ 완전 탐색

    def search(
        self,
        caps: tuple[int, ...],
        *,
        limit: int,
        units: int,
        month_caps: tuple[int, ...] | None,
        claim: bool,
    ) -> _Placement | None:
        """끝 날 칸 `limit` 안에 `units` 대를 넣는 배치 하나 — 없거나 마디 한도를 다 쓰면 None.

        `claim` 이 참이면 대안 셋(「못 넣음」 · 넣을 수 있는 대수 · 필요 완화 · 까닭)을 세우는
        탐색이라 한도에 걸리면 `exhausted` 를 남긴다. 거짓이면(완료 달 앞당기기 · 「가장 고르게」
        δ) 찾으면 쓰고 못 찾으면 탐욕 결과를 그대로 둔다.

        시작을 앞에서부터 차례로 고르는 되짚기다(한 칸에 넣을 대수는 많은 쪽부터 — 처음 닿는 잎이
        이른 시작 탐욕과 같다). 「이 칸부터 · 남은 대수 · 앞으로 걸릴 달의 쓴 예산 · 창이 걸친 앞
        차수」 가 같으면 결과가 같아 실패를 기억한다. 가지치기는 둘 — 남은 대수 × D 가 지금 칸부터
        상한까지 달 예산 남은 합보다 크거나, D 일 묶음마다(묶음 안에서 시작하는 창은 묶음 끝 날을
        함께 지난다) 그 날 동시 한도 남은 합보다 크면 더 볼 것이 없다(둘 다 칸이 뒤로 갈수록
        작아진다).
        """
        if units <= 0:
            return _Placement((), 0, "search")
        budget = min(SEARCH_CALL_NODES, self.nodes_left[claim])
        if budget <= 0:
            self.exhausted = self.exhausted or claim
            return None
        pool: list[_Pooled] = []
        for start in self.candidates(limit):
            spans = self.overlap(start)
            if spans is None or any(caps[index] < overlap for index, overlap in spans):
                continue
            if month_caps is not None and any(month_caps[index] < 1 for index, _ in spans):
                continue
            first_month = spans[0][0]
            pool.append((start, spans, first_month))
        if not pool:
            return None
        starts = [item[0] for item in pool]
        last_month = self.last_month_until(limit)
        days = self.days
        used = [0] * len(self.rows)
        active = [0] * (limit + 1) if month_caps is not None else None
        chosen: list[tuple[int, int]] = []
        failed: set[tuple[object, ...]] = set()
        spent = [0]

        def hopeful(position: int, remaining: int) -> bool:
            start, _, first_month = pool[position]
            room = 0
            for index in range(first_month, last_month + 1):
                spare = caps[index] - used[index]
                if spare > 0:
                    room += spare
            if remaining * days > room:
                return False
            if month_caps is None or active is None:
                return True
            count = 0
            cursor = position
            while cursor < len(pool) and count < remaining:
                anchor = starts[cursor]
                busiest = anchor + days - 1
                month = self.month_index(busiest)
                if month is not None:
                    count += max(0, month_caps[month] - active[busiest])
                cursor = bisect.bisect_left(starts, anchor + days, lo=cursor + 1)
            return remaining <= count

        def state(position: int, remaining: int) -> tuple[object, ...]:
            start, _, first_month = pool[position]
            spent = tuple(used[first_month : last_month + 1])
            if active is None:
                return (position, remaining, spent)
            recent: list[tuple[int, int]] = []
            for other, count in reversed(chosen):
                if other <= start - days:
                    break
                recent.append((start - other, count))
            return (position, remaining, spent, tuple(recent))

        def descend(first: int, remaining: int) -> bool:
            if remaining <= 0:
                return True
            seen: list[tuple[object, ...]] = []
            for position in range(first, len(pool)):
                spent[0] += 1
                if spent[0] > budget:
                    raise _Exhausted
                key = state(position, remaining)
                if key in failed:
                    break
                seen.append(key)
                if not hopeful(position, remaining):
                    break
                start, spans, _ = pool[position]
                take = self._room(
                    start, spans, caps, used, remaining, month_caps, active, late=False
                )
                while take > 0:
                    self._apply(start, spans, take, used, active)
                    chosen.append((start, take))
                    if descend(position + 1, remaining - take):
                        return True
                    chosen.pop()
                    self._apply(start, spans, -take, used, active)
                    take -= 1
            failed.update(seen)
            return False

        try:
            found = descend(0, units)
        except (_Exhausted, RecursionError):
            self.exhausted = self.exhausted or claim
            return None
        finally:
            self.nodes_left[claim] -= spent[0]
        if not found:
            return None
        return _Placement(tuple(chosen), units, "search")

    # ------------------------------------------------------------ 조합

    def complete(self, placement: _Placement) -> bool:
        return placement.placed >= self.units

    def finish_index(self, placement: _Placement) -> int | None:
        if not placement.batches:
            return None
        last = max(start for start, _ in placement.batches) + self.days - 1
        return self.month_index(last)

    def earliest_finish(
        self, delta: float, limit: int, *, month_caps: tuple[int, ...] | None
    ) -> _Placement:
        """EARLY 의 완료 달보다 앞 달 L 부터 LATE(L) · 완전 탐색(L) 이 다 넣으면 그것, 아니면 EARLY.

        다 넣는 길이 없으면 상한 안에 가장 많이 넣은 것이다(탐욕 가운데 많은 쪽에서 완전 탐색으로
        한 대씩 더 — 같으면 EARLY).
        """
        caps = self.caps(delta)
        early = self.greedy(caps, limit=limit, late=False, month_caps=month_caps)
        best = early
        early_month = self.finish_index(early) if self.complete(early) else None
        for index, (_, month_end) in enumerate(self.spans_of_month):
            end = min(month_end, limit)
            if end < self.days - 1:
                continue
            if early_month is not None and index >= early_month:
                break
            late = self.greedy(caps, limit=end, late=True, month_caps=month_caps)
            if self.complete(late):
                return late
            if late.placed > best.placed:
                best = late
            found = self.search(
                caps, limit=end, units=self.units, month_caps=month_caps, claim=end >= limit
            )
            if found is not None:
                return found
            if end >= limit:
                break
        if self.complete(best):
            return best
        for units in range(best.placed + 1, self.units):
            more = self.search(caps, limit=limit, units=units, month_caps=month_caps, claim=True)
            if more is None:
                break
            best = more
        return best

    def feasible(
        self, delta: float, limit: int, *, month_caps: tuple[int, ...] | None, claim: bool
    ) -> bool:
        """끝 날 상한 `limit` 안에 N 대가 다 드는가 — EARLY · LATE(상한) · 완전 탐색."""
        caps = self.caps(delta)
        if self.complete(self.greedy(caps, limit=limit, late=False, month_caps=month_caps)):
            return True
        if self.complete(self.greedy(caps, limit=limit, late=True, month_caps=month_caps)):
            return True
        found = self.search(caps, limit=limit, units=self.units, month_caps=month_caps, claim=claim)
        return found is not None

    def largest_delta(self, low: float, high: float, limit: int, *, claim: bool) -> float:
        """`feasible(low)` 가 참일 때 다 드는 가장 큰 δ(≤ high) — 이분 탐색."""
        if self.feasible(high, limit, month_caps=self.month_caps, claim=claim):
            return high
        for _ in range(_SEARCH_STEPS_LIMIT):
            if high - low <= SEARCH_RESOLUTION:
                break
            middle = (low + high) / 2
            if self.feasible(middle, limit, month_caps=self.month_caps, claim=claim):
                low = middle
            else:
                high = middle
        return low

    def ceiling(self, margin: float, limit: int) -> float:
        """「가장 고르게」 δ 의 위 끝 — 열린 달(R > 0)의 개조 전 A/R − G 가운데 가장 큰 값(여유보다
        작으면 여유). 그보다 큰 δ 에서는 그런 달 모두 하루도 못 넣어 결과가 같다."""
        values = [
            row.available / row.required - row.general_target
            for index, row in enumerate(self.rows)
            if row.required > 0 and self.is_open(index, limit)
        ]
        return max([margin, *values])

    def relief(self, margin: float, limit: int) -> float | None:
        """상한 안에 다 넣으려면 배치 기준에서 낮춰야 하는 폭. 가장 낮은 달 기준을 0 까지 낮춰도 못
        넣으면 None."""
        floor_delta = -self.minimum_target
        if not self.feasible(floor_delta, limit, month_caps=self.month_caps, claim=True):
            return None
        return margin - self.largest_delta(floor_delta, margin, limit, claim=True)

    def cause(self, limit: int) -> ShortfallCause:
        """기준을 0 까지 낮춰도 못 넣는 까닭 — 창 · 동시 상한 · 가용."""
        if not self.candidates(limit):
            return "window"
        if self.conditions.concurrent is not None and self.feasible(
            -self.minimum_target, limit, month_caps=self.free_month_caps, claim=True
        ):
            return "concurrent"
        return "capacity"


# ================================================================== 계산


def plan_modification_schedule(
    months: Sequence[ScheduleMonthInput], conditions: ScheduleConditions
) -> ScheduleResult:
    """N 대 × D 일 개조 일정을 찾고 달마다의 개조 전·뒤 확보율과 요약을 붙인다.

    검증에 걸리면 화면에 낼 글의 `ValueError` 다. 「가장 고르게」 에서 여유만으로도 기한을 못 맞추면
    안전 여유로 「가장 빨리」 처럼 풀고(`fell_back`) 대안 셋을 붙인다.
    """
    _validate(months, conditions)
    model = _Model(months, conditions)
    margin = float(conditions.margin)
    limit = model.limit_offset
    month_caps = model.month_caps
    delta = margin
    fell_back = False
    if conditions.objective == "even":
        if model.feasible(margin, limit, month_caps=month_caps, claim=False):
            delta = model.largest_delta(margin, model.ceiling(margin, limit), limit, claim=False)
        else:
            fell_back = True
    placement = model.earliest_finish(delta, limit, month_caps=month_caps)

    shortfall: ScheduleShortfall | None = None
    if not model.complete(placement):
        finish_day: date | None = None
        finish_month: int | None = None
        by_deadline = conditions.deadline is not None and limit < model.horizon_offset
        if by_deadline:
            free = model.earliest_finish(margin, model.horizon_offset, month_caps=month_caps)
            index = model.finish_index(free) if model.complete(free) else None
            if index is not None:
                last = max(start for start, _ in free.batches) + model.days - 1
                finish_day, finish_month = model.day(last), model.rows[index].month
        relief = model.relief(margin, limit)
        shortfall = ScheduleShortfall(
            placed=placement.placed,
            by_deadline=by_deadline,
            finish_without_deadline=finish_day,
            finish_month_without_deadline=finish_month,
            relief=relief,
            cause=None if relief is not None else model.cause(limit),
            exact=not model.exhausted,
        )
    return _result(model, placement, delta, shortfall, fell_back=fell_back)


def _result(
    model: _Model,
    placement: _Placement,
    delta: float,
    shortfall: ScheduleShortfall | None,
    *,
    fell_back: bool,
) -> ScheduleResult:
    conditions = model.conditions
    used = [0] * len(model.rows)
    batches: list[ScheduleBatch] = []
    for start, units in placement.batches:
        spans = model.overlap(start) or ()
        for index, overlap in spans:
            used[index] += units * overlap
        batches.append(
            ScheduleBatch(
                start=model.day(start),
                units=units,
                days=model.days,
                shares=tuple((model.rows[index].month, overlap) for index, overlap in spans),
            )
        )

    targets = model.targets(delta)
    rows: list[ScheduleMonth] = []
    for index, (row, window) in enumerate(zip(model.rows, model.windows, strict=True)):
        downtime = used[index] / window.days
        baseline_rate = row.available / row.required if row.required > 0 else None
        rate = (row.available - downtime) / row.required if row.required > 0 else None
        rows.append(
            ScheduleMonth(
                month=row.month,
                window_first_day=window.first_day,
                window_last_day=window.boundary_end,
                window_days=window.days,
                required=row.required,
                available=row.available,
                general_target=row.general_target,
                threshold=targets[index],
                open=model.is_open(index, model.limit_offset),
                blocked=not model.ok(index, 0, row.general_target + conditions.margin),
                concurrent_cap=model.concurrent_caps[index],
                downtime_unit_days=used[index],
                downtime=downtime,
                slack=row.available - targets[index] * row.required,
                baseline_rate=baseline_rate,
                rate=rate,
                baseline_secure=(
                    None if baseline_rate is None else secure(baseline_rate, row.general_target)
                ),
                secure_after=None if rate is None else secure(rate, row.general_target),
            )
        )

    complete = model.complete(placement)
    finish_day: date | None = None
    finish_month: int | None = None
    if complete and batches:
        finish_day = max(batch.last_day for batch in batches)
        finish_index = model.finish_index(placement)
        finish_month = None if finish_index is None else model.rows[finish_index].month

    affected = [row for row in rows if row.downtime_unit_days > 0 and row.rate is not None]
    tightest = min(affected, key=_margin_key) if affected else None
    return ScheduleResult(
        conditions=conditions,
        months=tuple(rows),
        batches=tuple(batches),
        first_day=model.first_day,
        last_day=model.limit_day,
        applied_margin=delta,
        strategy=placement.strategy,
        placed=placement.placed,
        finish_day=finish_day,
        finish_month=finish_month,
        max_concurrent=_max_concurrent(batches),
        tightest_month=None if tightest is None else tightest.month,
        tightest_rate=None if tightest is None else tightest.rate,
        tightest_margin=None if tightest is None else tightest.margin,
        shortfall=shortfall,
        fell_back=fell_back,
    )


def _margin_key(row: ScheduleMonth) -> float:
    """기준 대비 여유 최저 고르기 열쇠(같으면 `min` 이 앞 달을 남긴다)."""
    margin = row.margin
    return math.inf if margin is None else margin


def _max_concurrent(batches: Sequence[ScheduleBatch]) -> int:
    """같은 날 개조 중인 가장 많은 대수 — 시작 +대수, 끝 경계 −대수를 날 차례로 쓴다(끝이 먼저)."""
    events: list[tuple[date, int]] = []
    for batch in batches:
        events.append((batch.start, batch.units))
        events.append((batch.end, -batch.units))
    busiest = current = 0
    for _, change in sorted(events, key=lambda item: (item[0], item[1])):
        current += change
        busiest = max(busiest, current)
    return busiest


# ================================================================== 어댑터


def schedule_month_inputs(
    process_months: pd.DataFrame,
    *,
    process: str,
    months: Sequence[int],
    general_target: Callable[[int], float],
) -> tuple[ScheduleMonthInput, ...]:
    """필요 단축 일정 계획의 공정 × 월 표에서 그 공정의 달마다 (R, A, G) 를 꺼낸다.

    `process_months` 는 `ShorteningPlan.at(…).process_months` 다. 읽는 칸은 `공정`·`생산계획년월`·
    `소요대수`·`가용대수` 넷뿐이다(단축 열은 읽지 않는다 — 가용은 단축 전). 그 공정 행이 없으면
    `KeyError`, 보이는 달이 빠졌거나 겹치면 `ValueError` 다(제약 모드 어댑터와 같은 갈래).
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
    inputs: list[ScheduleMonthInput] = []
    for month in (int(value) for value in months):
        if month not in by_month:
            raise ValueError(f"설비 일정 기준 계획에 {month} 공정 「{key}」 행이 없습니다.")
        required, available = by_month[month]
        inputs.append(
            ScheduleMonthInput(
                month=month,
                required=required,
                available=available,
                general_target=float(general_target(month)),
            )
        )
    return tuple(inputs)
