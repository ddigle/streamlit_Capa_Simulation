# Purpose: 목표 확보율에 모자란 공정·월마다 신규 호기 Qual 을 며칠 당겨야 하는지 계산한다.

"""필요단축일정.

Dynamic 가용대수(호기 일정을 Cut-off W/D 구간에 일할한 환산대수)가 시나리오 소요대수 x 목표
확보율에 모자라는 달이 있으면, **아직 Qual 이 끝나지 않은 신규 호기의 Qual 을 얼마나 앞당기면
그 달을 채우는가**를 낸다. 당길 호기가 바닥나면 「추가1」「추가2」… 가상 호기가 언제까지 Qual 을
마쳐야 하는지를 낸다(2026-10-07 사용자 결정).

## 가용과 소요

- 가용은 `build_monthly_equipment_availability` 의 **환산 소계**(`기존보유` + `가용`)다 —
  Static/Dynamic 탭의 Dynamic 과 같은 줄에서 나온다. 비가동도 그대로 반영된다.
- 소요는 시나리오의 소요대수를 `calculate_securement_rate` 로 `(월, 공정)` 에 모은 값이다 —
  확보율 교차검증(`securement_cross_check`)과 같은 함수, 같은 집계다.
- 공정은 호기 마스터 `공정소분류` 와 시뮬레이션 `공정` 이 **같은 이름일 때만** 맞댄다. 한쪽에만
  있는 공정은 목록으로 돌려주고 비교하지 않는다.

## 기여 규칙

호기는 Qual 다음 날부터 기여한다(`services/wd_window.py` 의 규약). 한 달의 W/D 구간은
`(전월 말일 - cutoff, 당월 말일 - cutoff]` 이고 분모는 그 구간의 일수다. 그래서 Qual 을 `q` 에서
`t` 로 당기면 그 달에 늘어나는 환산대수는 `환산비 x |(max(t, 구간 앞), min(q, 구간 끝)]| / 구간일수`
다. 예 — Cut-off 10, 2026-05 구간 `(4/20, 5/21]`(31일):

- Qual 5/1 호기는 5/2 부터 기여해 `20/31 = 0.645` 대다.
- 4/20 으로 당기면 구간 전체를 덮어 `+11/31 = +0.355` 대가 는다.

## 단축 차례

공정마다 달을 차례로 본다. 부족한 달(`가용 - 소요 x 목표 < 0`)이면

1. 그 달 구간의 바닥 `max(구간 앞 경계, 오늘)` 보다 Qual 이 늦은 후보 가운데 **Qual 이 가장 이른**
   호기를 고른다. 같으면 **호기 번호가 작은** 쪽(이름 끝 숫자, 그다음 이름)이다.
2. 그 호기를 **모자란 만큼만** 당긴다(하루 단위). 바닥까지 당겨도 모자라면 다음 후보로 간다.
3. 앞 달에 당긴 호기는 뒤 달의 가용도 올린다. 그래서 달마다 그때까지 당긴 결과를 반영한 가용으로
   다시 잰다. 앞 달에 당긴 호기의 Qual 은 다음 달 구간 앞 경계보다 이르므로 자연히 다시 뽑히지
   않는다.
4. 후보가 바닥나면 환산비 1 의 가상 호기 「추가N」을 더한다. Qual 은 그 달의 남은 부족을 덮는 가장
   늦은 날이고, 한 대로 모자라면 바닥 날짜로 한 대씩 더 둔다. 가상 호기도 뒤 달에 남는다.
5. 그 달 구간이 이미 오늘로 끝났으면(`max(구간 앞, 오늘) >= 구간 끝`) 당겨서 채울 수 없으므로
   「단축으로 못 채움(기한 지남)」으로 두고 넘어간다.

## 후보

신규 호기(`기존설비여부` N, `보관유무` N) 가운데 Qual일정이 있고 확정상태가 「완료」가 아니며
반출·이설 일정이 없는 것. 모듈 행은 설비키(`Main 설비`, 없으면 `설비명`)로 묶어 **한 대로 함께
당긴다** — 묶음의 Qual 은 가장 늦은 모듈의 Qual 이고, 목표 날짜보다 늦은 모듈만 그 날짜로 온다.
묶음의 환산비는 모듈 행 환산비의 합이다.

**반입일정은 보지 않는다**(하한이 아니다). 상태 판정 엔진은 반입 전을 「입고 예정」으로 세므로
당긴 날짜가 반입보다 이르면 엔진으로 다시 재면 0 이 된다 — 그래서 늘어나는 몫은 엔진을 다시
돌리지 않고 위 식으로 낸다. 그 호기의 **운영 비가동 일정**과 겹친 날은 엔진처럼 기여하지 않는다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    span_date_range,
)
from capa_simulation.services.process_cutoff import cutoff_lookup
from capa_simulation.services.securement_cross_check import dynamic_available_equipment
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "DEFAULT_TARGET_LEVEL",
    "KIND_NEW",
    "KIND_SHORTENED",
    "PROCESS_MONTH_COLUMNS",
    "STATUS_CARRIED",
    "STATUS_EXPIRED",
    "STATUS_MET",
    "STATUS_NEW_LIMIT",
    "STATUS_SHORTENED",
    "STATUS_WITH_NEW",
    "TARGET_LEVELS",
    "UNIT_PLAN_COLUMNS",
    "VIRTUAL_UNIT_PREFIX",
    "CandidateModule",
    "CandidateUnit",
    "LevelPlan",
    "ShorteningPlan",
    "plan_from_availability",
    "plan_required_shortening",
    "shortening_candidates",
    "unit_number",
]

TARGET_LEVELS: tuple[float, ...] = (0.9, 1.0, 1.1, 1.2, 1.3)
"""미리 계산하는 목표 확보율 다섯. 화면은 이 가운데 하나를 고른다(다시 계산하지 않는다)."""

DEFAULT_TARGET_LEVEL = 1.1
"""처음 여는 화면의 목표. 업무 확보 기준 110% 다(시안과 같다)."""

COMPLETED_CONFIRMATION = "완료"
VIRTUAL_UNIT_PREFIX = "추가"
KIND_SHORTENED = "단축"
KIND_NEW = "신규"

STATUS_MET = "충족"
STATUS_SHORTENED = "단축으로 해소"
STATUS_CARRIED = "앞달 단축으로 해소"
STATUS_WITH_NEW = "신규 포함 해소"
STATUS_EXPIRED = "단축으로 못 채움(기한 지남)"
STATUS_NEW_LIMIT = "신규로도 못 채움(남은 날 부족)"

PROCESS_MONTH_COLUMNS = (
    "공정",
    "생산계획년월",
    "소요대수",
    "목표대수",
    "가용대수",
    "단축후가용대수",
    "확보율",
    "단축후확보율",
    "과부족",
    "단축후과부족",
    "상태",
)

UNIT_PLAN_COLUMNS = (
    "공정",
    "호기",
    "구분",
    "기존 Qual",
    "목표 Qual",
    "기여 시작",
    "단축일수",
    "늘어난 환산대수",
    "대상 월",
    "해소 기여 월",
    "모듈 수",
)

_ONE_DAY = timedelta(days=1)
# 부동소수 끝자리를 털어 내는 자리. `securement_rate._ceil_positive` 와 같은 9자리다 — 0 이어야 할
# 과부족이 -1e-15 로 남으면 그것이 「부족」으로 읽혀 호기 하나를 쓸데없이 당긴다.
_DECIMALS = 9
# 한 공정·한 달에 더하는 가상 호기의 상한. 구간이 거의 지난 이번 달은 한 대가 1/31 대만 덮어
# 수십 대가 필요하다고 나올 수 있다 — 그 이상은 「신규로도 못 채움」으로 알린다.
_MAX_VIRTUAL_UNITS_PER_MONTH = 50
_TRAILING_NUMBER = re.compile(r"(\d+)\s*$")


@dataclass(frozen=True)
class CandidateModule:
    """후보 호기의 한 행(모듈 행이면 모듈 하나)."""

    equipment_id: str
    qual: date
    ratio: float
    blocked: tuple[tuple[date, date | None], ...] = ()
    """**기여일** 기준으로 비가동이 걸린 날 구간(양 끝 포함, 끝이 None 이면 열림)."""

    def contributes_on(self, day: date) -> bool:
        """Qual 을 `day` 전으로 당겼을 때 그날 기여하는가 — 원래 Qual 뒤이거나 비가동이면 아니다."""
        if day > self.qual:
            return False
        return not any(start <= day and (end is None or day <= end) for start, end in self.blocked)


@dataclass(frozen=True)
class CandidateUnit:
    """한 대로 함께 당기는 후보. 모듈 행은 설비키로 묶인다."""

    process: str
    unit: str
    modules: tuple[CandidateModule, ...]

    @property
    def qual(self) -> date:
        """묶음의 Qual — 가장 늦은 모듈이 끝나야 설비 한 대가 다 선다."""
        return max(module.qual for module in self.modules)

    @property
    def ratio(self) -> float:
        return sum(module.ratio for module in self.modules)

    def weight_on(self, day: date) -> float:
        """Qual 을 `day` 전으로 당겼을 때 그날 늘어나는 환산 몫(구간일수로 나누기 전)."""
        return sum(module.ratio for module in self.modules if module.contributes_on(day))


@dataclass(frozen=True)
class LevelPlan:
    """목표 확보율 하나의 결과."""

    level: float
    process_months: pd.DataFrame
    """공정 x 월. `PROCESS_MONTH_COLUMNS`."""

    units: pd.DataFrame
    """당긴 호기와 가상 호기. `UNIT_PLAN_COLUMNS`."""


@dataclass(frozen=True)
class ShorteningPlan:
    """다섯 목표의 결과와, **맞대지 못한 자리**."""

    months: tuple[int, ...]
    today: date
    processes: tuple[str, ...]
    """양쪽에 다 있어 맞댄 공정(이름순). 화면이 표시순서로 다시 정렬한다."""

    cutoff_days: Mapping[str, int]
    levels: tuple[LevelPlan, ...]
    required_only: tuple[str, ...] = ()
    """시나리오 소요대수에만 있는 공정. Cut-off 가 없거나 호기 마스터에 없는 이름이다."""

    availability_only: tuple[str, ...] = ()
    """Dynamic 가용에만 있고 시나리오에 없는 공정."""

    missing_cutoff: tuple[str, ...] = ()
    """설비도 소요도 있는데 Cut-off 를 안 적어 맞대지 못한 공정(`required_only` 의 일부)."""

    candidate_units: int = 0
    """맞댄 공정의 단축 후보 대수(모듈 묶음은 한 대)."""

    def at(self, level: float) -> LevelPlan:
        """고른 목표의 결과. 미리 계산하지 않은 목표면 KeyError 다."""
        for plan in self.levels:
            if math.isclose(plan.level, level):
                return plan
        raise KeyError(f"계산하지 않은 목표 확보율입니다: {level}")


def unit_number(name: str) -> int | None:
    """호기 이름 끝의 숫자. 없으면 None — 번호가 있는 호기 뒤에 선다."""
    found = _TRAILING_NUMBER.search(name)
    return int(found.group(1)) if found else None


def _unit_order(name: str) -> tuple[int, int, str]:
    number = unit_number(name)
    return (0 if number is not None else 1, number or 0, name)


# ---------------------------------------------------------------------- 후보


def shortening_candidates(
    equipment: pd.DataFrame, downtime: pd.DataFrame
) -> tuple[CandidateUnit, ...]:
    """당길 수 있는 신규 호기를 설비키로 묶어 돌려준다.

    오늘과의 비교는 여기서 하지 않는다 — 달마다 바닥(`max(구간 앞, 오늘)`)이 달라 계산이 고른다.
    """
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return ()
    confirmation = prepared["확정상태"].astype("string").str.strip()
    eligible = (
        (
            prepared["기존설비여부"].eq("N")
            & prepared[STORAGE_FLAG_COLUMN].eq("N")
            & prepared["Qual일정"].notna()
            & ~confirmation.eq(COMPLETED_CONFIRMATION).fillna(False)
            & prepared["반출일정"].isna()
            & prepared[RELOCATION_DATE_COLUMN].isna()
        )
        .fillna(False)
        .astype(bool)
    )
    if not eligible.any():
        return ()
    keys = unit_keys(prepared)
    blocked = _blocked_days(prepare_downtime_for_prepared_equipment(downtime, prepared))
    groups: dict[str, list[tuple[str, CandidateModule]]] = {}
    chosen = prepared.loc[eligible.to_numpy()]
    for equipment_id, process, qual, ratio, key in zip(
        chosen[EQUIPMENT_ID_COLUMN].astype("string").str.strip(),
        chosen["공정소분류"].astype("string").str.strip(),
        pd.to_datetime(chosen["Qual일정"]),
        pd.to_numeric(chosen[CONVERSION_RATIO_COLUMN]),
        keys.loc[chosen.index].astype("string").str.strip(),
        strict=True,
    ):
        module = CandidateModule(
            equipment_id=str(equipment_id),
            qual=qual.date(),
            ratio=float(ratio),
            blocked=blocked.get(str(equipment_id), ()),
        )
        groups.setdefault(str(key), []).append((str(process), module))
    units = [
        CandidateUnit(
            process=members[0][0],
            unit=key,
            modules=tuple(sorted((module for _, module in members), key=lambda m: m.equipment_id)),
        )
        for key, members in groups.items()
    ]
    return tuple(sorted(units, key=lambda unit: (unit.process, _unit_order(unit.unit))))


def _blocked_days(downtime: pd.DataFrame) -> dict[str, tuple[tuple[date, date | None], ...]]:
    """호기별 비가동을 **기여일**로 옮긴다. 시점 `t` 의 상태가 기여일 `t + 1` 을 정한다."""
    if downtime.empty:
        return {}
    spans: dict[str, list[tuple[date, date | None]]] = {}
    for unit, began, finished in zip(
        downtime[EQUIPMENT_ID_COLUMN], downtime["시작일"], downtime["종료일"], strict=True
    ):
        start = pd.Timestamp(began).date() + _ONE_DAY
        end = None if pd.isna(finished) else pd.Timestamp(finished).date() + _ONE_DAY
        spans.setdefault(str(unit).strip(), []).append((start, end))
    return {unit: tuple(found) for unit, found in spans.items()}


# ---------------------------------------------------------------------- 계산


def plan_required_shortening(
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    required_equipment: pd.DataFrame,
    months: Sequence[int],
    today: date,
    levels: Sequence[float] = TARGET_LEVELS,
) -> ShorteningPlan:
    """호기 마스터·비가동·기존보유·Cut-off·소요대수로 다섯 목표의 단축 일정을 낸다.

    **어느 DB 도 열지 않는다.** 가용은 Static/Dynamic 탭과 같은 길로 만든다 — W/D 구간이 Cut-off
    만큼 앞으로 밀리므로 호기 구간은 `span_date_range` 가 알려 주는 범위로 만들고, 지분이 바뀌는
    날에도 끊는다(`with_unit_share=True`).
    """
    ordered = tuple(sorted({int(month) for month in months}))
    lookup = cutoff_lookup(cutoff)
    cutoff_days = {process: int(days) for process, days in lookup.items()}
    required = _required_in_months(required_equipment, ordered)
    required_processes = (
        set(required["공정"].astype("string").str.strip().dropna()) if not required.empty else set()
    )
    prepared = prepare_equipment_master(equipment)
    span = span_date_range(ordered, cutoff) if ordered else None
    if span is None:
        monthly = build_monthly_equipment_availability(
            pd.DataFrame(), baseline, cutoff, ordered, conversion_ratios={}
        )
    else:
        spans = build_equipment_lifecycle_spans(
            equipment, downtime, start_date=span[0], end_date=span[1], with_unit_share=True
        )
        ratios = {
            str(unit).strip(): float(ratio)
            for unit, ratio in zip(
                prepared[EQUIPMENT_ID_COLUMN], prepared[CONVERSION_RATIO_COLUMN], strict=True
            )
        }
        monthly = build_monthly_equipment_availability(
            spans, baseline, cutoff, ordered, conversion_ratios=ratios
        )
    availability_processes = (
        set(monthly["공정"].astype("string").str.strip().dropna()) if not monthly.empty else set()
    )
    compared = sorted(availability_processes & required_processes)
    equipment_processes = set(prepared["공정소분류"].astype("string").str.strip().dropna())
    if not baseline.empty and "공정" in baseline.columns:
        equipment_processes |= set(baseline["공정"].astype("string").str.strip().dropna())
    required_only = sorted(required_processes - availability_processes)
    missing_cutoff = sorted(
        process
        for process in required_only
        if process in equipment_processes and process not in lookup
    )

    candidates = [
        unit for unit in shortening_candidates(equipment, downtime) if unit.process in compared
    ]
    plan_levels = plan_from_availability(
        available=dynamic_available_equipment(monthly, weighted=True),
        required=required,
        candidates=candidates,
        cutoff_days=cutoff_days,
        processes=compared,
        months=ordered,
        today=today,
        levels=levels,
    )
    return ShorteningPlan(
        months=ordered,
        today=today,
        processes=tuple(compared),
        cutoff_days={process: cutoff_days[process] for process in compared},
        levels=plan_levels,
        required_only=tuple(required_only),
        availability_only=tuple(sorted(availability_processes - required_processes)),
        missing_cutoff=tuple(missing_cutoff),
        candidate_units=len(candidates),
    )


def _required_in_months(required_equipment: pd.DataFrame, months: Sequence[int]) -> pd.DataFrame:
    if required_equipment.empty or not {"생산계획년월", "공정", "소요대수"} <= set(
        required_equipment.columns
    ):
        return pd.DataFrame({"생산계획년월": [], "공정": [], "소요대수": []})
    numeric = pd.to_numeric(required_equipment["생산계획년월"], errors="coerce")
    return required_equipment.loc[
        numeric.isin(list(months)), ["생산계획년월", "공정", "소요대수"]
    ].copy()


def plan_from_availability(
    *,
    available: pd.DataFrame,
    required: pd.DataFrame,
    candidates: Sequence[CandidateUnit],
    cutoff_days: Mapping[str, float],
    processes: Sequence[str],
    months: Sequence[int],
    today: date,
    levels: Sequence[float] = TARGET_LEVELS,
) -> tuple[LevelPlan, ...]:
    """맞댈 공정의 가용(`생산계획년월·공정·가용대수`)과 소요대수로 목표마다의 결과를 낸다.

    가용과 소요는 `calculate_securement_rate` 로 `(월, 공정)` 에 모은다 — 교차검증과 같은 함수다.
    가용 행이 없는 달은 0 대로 채운다(그 달에 가용 분류의 호기가 하나도 없는 것이다).
    """
    ordered = tuple(sorted({int(month) for month in months}))
    names = [str(process).strip() for process in processes]
    if not ordered or not names:
        return tuple(
            LevelPlan(float(level), _empty_process_months(), _empty_units()) for level in levels
        )
    grid = pd.MultiIndex.from_product([ordered, names], names=["생산계획년월", "공정"]).to_frame(
        index=False
    )
    if available.empty:
        filled = grid.assign(가용대수=0.0)
    else:
        source = available.loc[:, ["생산계획년월", "공정", "가용대수"]].copy()
        source["생산계획년월"] = pd.to_numeric(source["생산계획년월"], errors="coerce")
        source = source.dropna(subset=["생산계획년월"])
        source["생산계획년월"] = source["생산계획년월"].astype("int64")
        source["공정"] = source["공정"].astype("string").str.strip()
        source = source.groupby(["생산계획년월", "공정"], as_index=False)[["가용대수"]].sum()
        source["공정"] = source["공정"].astype(object)
        filled = grid.merge(source, on=["생산계획년월", "공정"], how="left", validate="one_to_one")
        filled["가용대수"] = filled["가용대수"].fillna(0.0)
    # 맞대는 공정·달만 남긴다. 남기면 확보율 계산이 「가용대수가 없는 공정」으로 멈춘다.
    demand = _required_in_months(required, ordered)
    if not demand.empty:
        demand_process = demand["공정"].astype("string").str.strip()
        demand = demand.loc[demand_process.isin(names).fillna(False).to_numpy()]
    rate = calculate_securement_rate(filled, demand)
    by_key = {
        (int(month), str(process)): (float(supply), float(need))
        for month, process, supply, need in zip(
            rate["생산계획년월"], rate["공정"], rate["가용대수"], rate["소요대수"], strict=True
        )
    }
    by_process: dict[str, list[CandidateUnit]] = {}
    for unit in candidates:
        by_process.setdefault(unit.process, []).append(unit)

    results: list[LevelPlan] = []
    for level in levels:
        month_rows: list[dict[str, object]] = []
        unit_rows: list[dict[str, object]] = []
        for process in names:
            windows = [wd_window(month, float(cutoff_days[process])) for month in ordered]
            base = [by_key.get((month, process), (0.0, 0.0))[0] for month in ordered]
            need = [by_key.get((month, process), (0.0, 0.0))[1] for month in ordered]
            outcome = _plan_process(
                windows, base, need, by_process.get(process, []), float(level), today
            )
            month_rows.extend(_process_month_rows(process, outcome, float(level)))
            unit_rows.extend(_unit_rows(process, outcome))
        results.append(
            LevelPlan(
                level=float(level),
                process_months=_frame(month_rows, PROCESS_MONTH_COLUMNS, _empty_process_months()),
                units=_frame(unit_rows, UNIT_PLAN_COLUMNS, _empty_units()),
            )
        )
    return tuple(results)


@dataclass
class _UnitState:
    unit: CandidateUnit
    target: date
    gain: float = 0.0
    pulled_months: list[int] = field(default_factory=list)
    extra: dict[int, float] = field(default_factory=dict)


@dataclass
class _VirtualState:
    name: str
    target: date
    month: int
    gain: float
    extra: dict[int, float] = field(default_factory=dict)


@dataclass
class _ProcessOutcome:
    windows: list[WdWindow]
    base: list[float]
    after: list[float]
    required: list[float]
    status: list[str]
    states: list[_UnitState]
    virtuals: list[_VirtualState]


def _short(value: float) -> bool:
    return round(value, _DECIMALS) > 0


def _plan_process(
    windows: list[WdWindow],
    base: list[float],
    required: list[float],
    candidates: Sequence[CandidateUnit],
    level: float,
    today: date,
) -> _ProcessOutcome:
    after = list(base)
    states = [_UnitState(unit=unit, target=unit.qual) for unit in candidates]
    virtuals: list[_VirtualState] = []
    actions: list[str] = []
    for index, window in enumerate(windows):
        if not _short(required[index] * level - after[index]):
            actions.append("")
            continue
        floor = max(window.boundary_start, today)
        if floor >= window.boundary_end:
            actions.append(STATUS_EXPIRED)
            continue
        action = ""
        tried: set[str] = set()
        added = 0
        while _short(required[index] * level - after[index]):
            state = _next_candidate(states, floor, tried)
            if state is not None:
                shortfall = required[index] * level - after[index]
                target, gain = _minimum_pull(state, window, floor, shortfall)
                if gain <= 0:
                    tried.add(state.unit.unit)
                    continue
                _move(state, target, windows, after)
                state.gain += gain
                state.pulled_months.append(window.year_month)
                action = action or STATUS_SHORTENED
                continue
            if added >= _MAX_VIRTUAL_UNITS_PER_MONTH:
                action = STATUS_NEW_LIMIT
                break
            shortfall = required[index] * level - after[index]
            virtual = _virtual_unit(
                f"{VIRTUAL_UNIT_PREFIX}{len(virtuals) + 1}", window, floor, shortfall
            )
            _add_virtual(virtual, windows, after)
            virtuals.append(virtual)
            added += 1
            action = STATUS_WITH_NEW
        actions.append(action)
    status = [
        _month_status(base[index] - required[index] * level, actions[index])
        for index in range(len(windows))
    ]
    return _ProcessOutcome(windows, base, after, required, status, states, virtuals)


def _month_status(before_gap: float, action: str) -> str:
    if not _short(-before_gap):
        return STATUS_MET
    return action or STATUS_CARRIED


def _next_candidate(states: list[_UnitState], floor: date, tried: set[str]) -> _UnitState | None:
    """바닥보다 Qual 이 늦은 후보 가운데 Qual 이 가장 이른 것. 같으면 호기 번호가 작은 것."""
    eligible = [state for state in states if state.target > floor and state.unit.unit not in tried]
    if not eligible:
        return None
    return min(eligible, key=lambda state: (state.target, _unit_order(state.unit.unit)))


def _minimum_pull(
    state: _UnitState, window: WdWindow, floor: date, shortfall: float
) -> tuple[date, float]:
    """모자란 만큼만 당긴 목표 Qual 과 그 달에 늘어나는 환산대수.

    구간 끝(또는 지금 Qual) 쪽 날부터 하루씩 덮어 가며 부족을 채우는 첫 날에서 멈춘다 — 그날의
    전날이 목표 Qual 이다. 바닥까지 가도 모자라면 바닥이 목표다.
    """
    day = min(state.target, window.boundary_end)
    gained = 0.0
    while day > floor:
        gained += state.unit.weight_on(day) / window.days
        if round(gained - shortfall, _DECIMALS) >= 0:
            return day - _ONE_DAY, gained
        day -= _ONE_DAY
    return floor, gained


def _move(state: _UnitState, target: date, windows: list[WdWindow], after: list[float]) -> None:
    """목표 Qual 을 옮기고, 새로 덮인 날을 **모든 달**의 가용에 더한다(뒤 달로 이어진다)."""
    for index, window in enumerate(windows):
        first = max(target, window.boundary_start) + _ONE_DAY
        last = min(state.target, window.boundary_end)
        day = first
        added = 0.0
        while day <= last:
            added += state.unit.weight_on(day)
            day += _ONE_DAY
        if added:
            share = added / window.days
            after[index] += share
            state.extra[window.year_month] = state.extra.get(window.year_month, 0.0) + share
    state.target = target


def _virtual_unit(name: str, window: WdWindow, floor: date, shortfall: float) -> _VirtualState:
    """남은 부족을 덮는 가장 늦은 Qual. 한 대로 모자라면 바닥 날짜다."""
    available_days = (window.boundary_end - floor).days
    needed_days = max(1, math.ceil(round(shortfall * window.days, _DECIMALS)))
    covered = min(needed_days, available_days)
    target = window.boundary_end - timedelta(days=covered)
    return _VirtualState(
        name=name, target=target, month=window.year_month, gain=covered / window.days
    )


def _add_virtual(virtual: _VirtualState, windows: list[WdWindow], after: list[float]) -> None:
    for index, window in enumerate(windows):
        covered = (window.boundary_end - max(virtual.target, window.boundary_start)).days
        if covered > 0:
            share = covered / window.days
            after[index] += share
            virtual.extra[window.year_month] = share


# ---------------------------------------------------------------------- 결과 표


def _process_month_rows(
    process: str, outcome: _ProcessOutcome, level: float
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, window in enumerate(outcome.windows):
        need = outcome.required[index]
        target = need * level
        before = outcome.base[index]
        after = outcome.after[index]
        rows.append(
            {
                "공정": process,
                "생산계획년월": window.year_month,
                "소요대수": need,
                "목표대수": target,
                "가용대수": before,
                "단축후가용대수": after,
                "확보율": before / need if need > 0 else float("nan"),
                "단축후확보율": after / need if need > 0 else float("nan"),
                "과부족": round(before - target, _DECIMALS),
                "단축후과부족": round(after - target, _DECIMALS),
                "상태": outcome.status[index],
            }
        )
    return rows


def _unit_rows(process: str, outcome: _ProcessOutcome) -> list[dict[str, object]]:
    short_months = {
        window.year_month
        for index, window in enumerate(outcome.windows)
        if outcome.status[index] != STATUS_MET
    }
    rows: list[dict[str, object]] = []
    moved = [state for state in outcome.states if state.target < state.unit.qual]
    for state in sorted(moved, key=lambda s: (s.unit.qual, _unit_order(s.unit.unit))):
        rows.append(
            {
                "공정": process,
                "호기": state.unit.unit,
                "구분": KIND_SHORTENED,
                "기존 Qual": state.unit.qual,
                "목표 Qual": state.target,
                "기여 시작": state.target + _ONE_DAY,
                "단축일수": (state.unit.qual - state.target).days,
                "늘어난 환산대수": state.gain,
                "대상 월": state.pulled_months[0] if state.pulled_months else None,
                "해소 기여 월": _month_list(state.extra, short_months),
                "모듈 수": len(state.unit.modules),
            }
        )
    for virtual in outcome.virtuals:
        rows.append(
            {
                "공정": process,
                "호기": virtual.name,
                "구분": KIND_NEW,
                "기존 Qual": None,
                "목표 Qual": virtual.target,
                "기여 시작": virtual.target + _ONE_DAY,
                "단축일수": None,
                "늘어난 환산대수": virtual.gain,
                "대상 월": virtual.month,
                "해소 기여 월": _month_list(virtual.extra, short_months),
                "모듈 수": 1,
            }
        )
    return rows


def _month_list(extra: Mapping[int, float], short_months: set[int]) -> str:
    return ", ".join(
        str(month)
        for month, value in sorted(extra.items())
        if month in short_months and round(value, _DECIMALS) > 0
    )


def _frame(
    rows: list[dict[str, object]], columns: Sequence[str], empty: pd.DataFrame
) -> pd.DataFrame:
    if not rows:
        return empty
    return pd.DataFrame(rows, columns=list(columns))


def _empty_process_months() -> pd.DataFrame:
    frame = pd.DataFrame({column: pd.Series(dtype="float64") for column in PROCESS_MONTH_COLUMNS})
    frame["공정"] = frame["공정"].astype("object")
    frame["생산계획년월"] = frame["생산계획년월"].astype("int64")
    frame["상태"] = frame["상태"].astype("object")
    return frame


def _empty_units() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in UNIT_PLAN_COLUMNS})
