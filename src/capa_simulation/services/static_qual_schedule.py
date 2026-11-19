# Purpose: Static 월별 가용대수 · Cut-off · Qual 순서로 신규 호기의 Qual 마감(현재 일정)을 역산한다.

"""필요 단축 일정의 「현재 일정」 — Static 역산(2026-11-20 사용자 보드 답 Static-0 · Q01 ~ Q15).

필요 단축 일정은 호기의 현재 Qual 일정에서 얼마나 당겨야 목표 확보율을 채우는지 낸다. 그 **현재
일정**을 무엇으로 잡나가 기준(`basis`)이다.

- **설비 마스터**(`BASIS_MASTER`) — 설비 마스터 `Qual일정` 칸 그대로(2026-10-07 부터의 계산).
- **Static**(`BASIS_STATIC`, 화면 기본값) — 세션 활성 시나리오의 기준정보 월별 가용대수
  (`RQ_EQP_AVBL`, 미저장 편집 포함 — Q04)를 채우려면 **늦어도 언제** Qual 해야 하는지를 Qual 마감
  계산기(`services/qual_deadline.py`)와 같은 규칙으로 역산한 날짜.

이 모듈은 Static 쪽 역산만 한다. 어느 DB 도 열지 않고 Streamlit 도 모른다. 단축 계산은 그대로
`services/required_shortening.py` 가 한다 — 현재 일정만 이 결과로 바뀐다.

## 무엇을 역산하나(Q06 · Q08 · Q09 · Q15)

- **역산할 호기**(`reverse_targets`) — 신규(`기존설비여부` N) · `보관유무` N · 정지/반출 일정 없음 ·
  사용기준 HBM/EDP(`counts_for_capacity`) · **아직 Qual 이 끝나지 않은** 호기. 끝났다는 것은
  `Qual상태` 가 「완료」 이거나 `Qual실적` 이 적힌 것이다(Q15). 모듈 행은 설비키(`Main 설비`, 없으면
  `설비명`)로 묶어 한 대다 — 환산비는 모듈 환산비의 합이다(단축 후보와 같은 묶음). `Qual일정` 이 빈
  호기(일정 미정)도 든다(Q08).
- **차례**(Q09) — 설비 마스터 `Qual일정` 이른 순 → 같으면 호기 번호, 일정 미정 호기는 그 뒤에
  `반입일정` 이른 순(없으면 맨 뒤) → 호기 번호.
- **고정 대수**(Q06) — 역산하지 않는 모든 호기(기존 보유대수 표 · 기존설비 · Qual 이 끝난 호기 ·
  정지/반출 일정이 있는 호기 …)가 그 달에 몇 대(환산)인지. 설비 일정 기준 가용과 같은 엔진으로
  달마다 세고(반출 · 정지 반영), **비가동은 보지 않는다**(Q07 (가) — 역산은 호기 수로만). 계산기의
  「직전 달 가용대수」 자리다.

## 역산(계산기 규칙 — 초안 6장 2 · 3)

공정마다 계산할 달을 차례로 본다. 「고정 대수 + 앞 달까지 배정된 호기의 이 달 몫」 이 Static
가용대수에 모자라면 차례대로 호기를 꺼낸다.

- 모자람이 그 호기의 환산비 이상이면 마감은 구간 앞 경계(그 달을 통째로 채움 — 몫 = 환산비),
- 작으면 모자란 몫을 채우는 날 수만큼 구간 끝에서 당긴 날(가장 늦은 날 — 몫 = 환산비 x 날 수 /
  구간일수)이다.
- 환산비 1 이면 계산기(`compute_qual_deadlines`)와 같은 마감 · 몫이다(시험이 맞댄다).
- Static 가용대수가 없는 달(그 공정 행이 없거나 빈 값)은 계산기의 「목표를 비운 달」 처럼 판정하지
  않는다. 공정에 Static 행이 하나도 없으면 그 공정은 역산하지 않는다(Q13 — 부르는 쪽이 알린다).
- Static 이 줄어드는 달도 호기를 빼지 않는다(초안 6장 6).

## 남는 몫 셋(Q10 · Q11 · Q12)

- **호기 부족**(Q10) — 꺼낼 호기가 바닥났는데 모자라면 그 달의 `shortfall` 이다. 가용은 있는 호기
  만큼이고 모자란 몫은 목표 대비 단축 · 추가N 으로 이어진다.
- **남는 호기**(Q11) — 끝까지 쓰이지 않은 호기(`leftovers`). 현재 일정이 없다 — 단축 계산은 이
  호기를 추가N 보다 먼저 이름 있는 호기로 쓴다.
- **지난 마감**(Q12) — 역산 마감이 오늘보다 앞이면 현재 일정은 오늘로 미룬다(`current`). 그 달의
  남은 모자람은 미루기 전 몫으로 줄인다 — 미룬 몫을 다시 메우면 차례의 호기가 모두 지난 달로 빨려
  든다. 그래서 그 달 부족은 단축 계산에서 드러난다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    CONVERSION_RATIO_COLUMN,
    DONE_STAGE_STATUS,
    EQUIPMENT_ID_COLUMN,
    EXIT_SCHEDULE_COLUMNS,
    QUAL_ACTUAL_COLUMN,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    STORAGE_FLAG_COLUMN,
    counts_for_capacity,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    span_date_range,
)
from capa_simulation.services.process_cutoff import cutoff_lookup
from capa_simulation.services.securement_cross_check import dynamic_available_equipment
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "BASES",
    "BASIS_MASTER",
    "BASIS_STATIC",
    "DEFAULT_BASIS",
    "ReverseUnit",
    "StaticAssignment",
    "StaticMonthCheck",
    "StaticQualSchedule",
    "basis_label",
    "build_static_qual_schedule",
    "fixed_counts",
    "reverse_static_schedule",
    "reverse_targets",
    "static_availability_lookup",
    "unit_order",
]

BASIS_STATIC = "Static"
BASIS_MASTER = "설비 마스터"
BASES: tuple[str, ...] = (BASIS_STATIC, BASIS_MASTER)
"""현재 일정 기준 둘 — 화면 전환의 차례(기본값이 왼쪽)."""

DEFAULT_BASIS = BASIS_STATIC
"""필요 단축 일정 · Space 「필요 단축」 보기의 처음 기준(세션 값 — 초안 6장 1). 계산 함수의 인자
기본값은 `BASIS_MASTER` 다 — 공정 Capa 상세 · 제약 시뮬레이션은 설비 마스터 그대로다(Q03)."""

# 몫이 이보다 크면 호기를 더 꺼낸다(계산기 `_EPS`), 남은 부족은 `_SHORT_EPS` 로 가른다(계산기와
# 같다).
_EPS = 1e-9
_SHORT_EPS = 1e-6


def basis_label(basis: str) -> str:
    """알 수 없는 값은 설비 마스터로 읽는다 — 옛 기준선(기준 칸 NULL)도 설비 마스터다(Q14)."""
    return basis if basis in BASES else BASIS_MASTER


def unit_order(name: str) -> tuple[int, int, str]:
    """호기 번호 차례 — 이름 끝 숫자, 없으면 번호 있는 호기 뒤(`required_shortening.unit_order`
    와 같은 규칙. 그 모듈이 이 모듈을 부르므로 여기 따로 둔다)."""
    digits = ""
    for character in reversed(name.rstrip()):
        if not character.isdigit():
            break
        digits = character + digits
    number = int(digits) if digits else None
    return (0 if number is not None else 1, number or 0, name)


@dataclass(frozen=True)
class ReverseUnit:
    """역산할 호기 하나(모듈 묶음은 한 대)."""

    process: str
    unit: str
    modules: tuple[tuple[str, float], ...]
    """`(설비명, 환산비)` — 사용기준 HBM/EDP 인 모듈만, 설비명 차례."""

    master_qual: date | None
    """설비 마스터 Qual일정 — 묶음은 가장 늦은 모듈. 한 모듈이라도 비면 None(일정 미정)."""

    arrival: date | None
    """반입일정 — 묶음은 가장 늦은 모듈. 일정 미정 호기의 차례에만 쓴다."""

    @property
    def ratio(self) -> float:
        return sum(ratio for _, ratio in self.modules)

    @property
    def equipment_ids(self) -> tuple[str, ...]:
        return tuple(equipment_id for equipment_id, _ in self.modules)


@dataclass(frozen=True)
class StaticAssignment:
    """Static 을 채우려고 날짜를 받은 호기."""

    process: str
    unit: str
    month: int
    """처음 쓰이는 달(`YYYYMM`)."""
    deadline: date
    """역산 마감 — 이 날 Qual 을 끝내면 다음 날부터 기여한다."""
    current: date
    """현재 일정 — 마감이 오늘보다 앞이면 오늘(Q12), 아니면 마감."""
    part: float
    """쓰이는 달에 보태는 몫(환산)."""

    @property
    def past(self) -> bool:
        """마감이 이미 지났나(현재 일정을 오늘로 미뤘나)."""
        return self.deadline < self.current


@dataclass(frozen=True)
class StaticMonthCheck:
    """공정 · 달 하나의 역산 점검."""

    process: str
    month: int
    static: float | None
    """Static 가용대수. 없는 달은 None — 판정하지 않는다."""
    fixed: float
    """고정 대수(비가동을 보지 않은 환산)."""
    carried: float
    """고정 대수 + 앞 달까지 배정된 호기의 이 달 몫."""
    added: float
    """이 달에 꺼낸 호기의 몫 합."""
    shortfall: float
    """호기가 바닥나 채우지 못한 몫(Q10). 없으면 0."""


@dataclass(frozen=True)
class StaticQualSchedule:
    """Static 역산 결과. 어느 공정을 맞댈지는 부르는 쪽(`plan_required_shortening`)이 정한다."""

    months: tuple[int, ...]
    today: date
    units: tuple[ReverseUnit, ...]
    """역산할 호기 전부(공정 · 차례 순)."""
    assignments: tuple[StaticAssignment, ...]
    checks: tuple[StaticMonthCheck, ...]
    static_processes: tuple[str, ...]
    """역산한 공정 — 계산할 달에 Static 행이 하나라도 있고 Cut-off 가 있는 공정(이름순)."""

    @property
    def leftovers(self) -> tuple[ReverseUnit, ...]:
        """끝까지 쓰이지 않은 호기(Q11) — Static 행이 있는 공정만."""
        assigned = {(item.process, item.unit) for item in self.assignments}
        with_static = set(self.static_processes)
        return tuple(
            unit
            for unit in self.units
            if unit.process in with_static and (unit.process, unit.unit) not in assigned
        )

    @property
    def reversed_ids(self) -> frozenset[str]:
        """역산하는 모듈 행의 설비명 — Static 행이 있는 공정만(없는 공정은 역산하지 않는다)."""
        with_static = set(self.static_processes)
        return frozenset(
            equipment_id
            for unit in self.units
            if unit.process in with_static
            for equipment_id in unit.equipment_ids
        )

    def assignment(self, unit: str) -> StaticAssignment | None:
        return next((item for item in self.assignments if item.unit == unit), None)

    def static_current(self) -> dict[str, date]:
        """호기마다 Static 현재 일정(날짜를 받은 호기만)."""
        return {item.unit: item.current for item in self.assignments}

    def master_current(self) -> dict[str, date]:
        """호기마다 설비 마스터 Qual일정(일정이 있는 호기만)."""
        return {unit.unit: unit.master_qual for unit in self.units if unit.master_qual is not None}

    def shortages(self) -> tuple[StaticMonthCheck, ...]:
        """호기가 바닥나 Static 을 못 채운 달(Q10)."""
        return tuple(check for check in self.checks if check.shortfall > 0)

    def past_assignments(self) -> tuple[StaticAssignment, ...]:
        """마감이 지나 오늘로 미룬 호기(Q12)."""
        return tuple(item for item in self.assignments if item.past)


def _as_date(value: object) -> date | None:
    if value is None or value is pd.NaT:
        return None
    try:
        if pd.isna(value):  # type: ignore[call-overload]
            return None
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(value).date()  # type: ignore[arg-type]


def reverse_targets(equipment: pd.DataFrame) -> tuple[ReverseUnit, ...]:
    """역산할 호기 — 공정마다 Qual 순서(Q09)로 줄 세운 묶음(모듈 docstring 「무엇을 역산하나」)."""
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return ()
    status = prepared[QUAL_STATUS_COLUMN].astype("string").str.strip()
    actual = (
        prepared[QUAL_ACTUAL_COLUMN].notna()
        if QUAL_ACTUAL_COLUMN in prepared.columns
        else pd.Series(False, index=prepared.index)
    )
    eligible = (
        (
            prepared["기존설비여부"].eq("N")
            & prepared[STORAGE_FLAG_COLUMN].eq("N")
            & ~status.eq(DONE_STAGE_STATUS).fillna(False)
            & ~actual
            & prepared.loc[:, list(EXIT_SCHEDULE_COLUMNS)].isna().all(axis=1)
            & counts_for_capacity(prepared)
        )
        .fillna(False)
        .astype(bool)
    )
    if not eligible.any():
        return ()
    keys = unit_keys(prepared)
    chosen = prepared.loc[eligible.to_numpy()]
    groups: dict[str, list[tuple[str, str, float, date | None, date | None]]] = {}
    for equipment_id, process, qual, arrival, ratio, key in zip(
        chosen[EQUIPMENT_ID_COLUMN].astype("string").str.strip(),
        chosen["공정소분류"].astype("string").str.strip(),
        chosen[QUAL_DATE_COLUMN],
        chosen[ARRIVAL_DATE_COLUMN],
        pd.to_numeric(chosen[CONVERSION_RATIO_COLUMN]),
        keys.loc[chosen.index].astype("string").str.strip(),
        strict=True,
    ):
        groups.setdefault(str(key), []).append(
            (str(equipment_id), str(process), float(ratio), _as_date(qual), _as_date(arrival))
        )
    units: list[ReverseUnit] = []
    for key, members in groups.items():
        quals = [member[3] for member in members]
        arrivals = [member[4] for member in members if member[4] is not None]
        units.append(
            ReverseUnit(
                process=members[0][1],
                unit=key,
                modules=tuple(sorted((member[0], member[2]) for member in members)),
                master_qual=None if any(qual is None for qual in quals) else max(quals),  # type: ignore[type-var]
                arrival=max(arrivals) if arrivals else None,
            )
        )
    return tuple(sorted(units, key=_queue_order))


def _queue_order(unit: ReverseUnit) -> tuple[str, int, date, tuple[int, int, str]]:
    """공정 → 일정 있는 호기(Qual 순) → 일정 미정 호기(반입 순, 없으면 맨 뒤) → 호기 번호(Q09)."""
    if unit.master_qual is not None:
        return (unit.process, 0, unit.master_qual, unit_order(unit.unit))
    return (unit.process, 1, unit.arrival or date.max, unit_order(unit.unit))


def static_availability_lookup(
    static_availability: pd.DataFrame, months: Iterable[int]
) -> dict[tuple[str, int], float]:
    """`RQ_EQP_AVBL`(`생산계획년월` · `공정` · `가용대수`)을 `(공정, 달) → 가용대수` 로. 계산할
    달만,
    같은 자리는 더하고, 빈 값 · 숫자가 아닌 값은 뺀다(그 달은 판정하지 않는다)."""
    wanted = {int(month) for month in months}
    columns = {"생산계획년월", "공정", "가용대수"}
    if static_availability.empty or not columns <= set(static_availability.columns):
        return {}
    frame = static_availability.loc[:, ["생산계획년월", "공정", "가용대수"]].copy()
    frame["생산계획년월"] = pd.to_numeric(
        frame["생산계획년월"].astype("string").str.replace("-", "", regex=False), errors="coerce"
    )
    frame["가용대수"] = pd.to_numeric(frame["가용대수"], errors="coerce")
    frame["공정"] = frame["공정"].astype("string").str.strip()
    frame = frame.dropna(subset=["생산계획년월", "가용대수", "공정"])
    frame = frame.loc[frame["생산계획년월"].astype("int64").isin(wanted)]
    lookup: dict[tuple[str, int], float] = {}
    for process, month, value in zip(
        frame["공정"], frame["생산계획년월"].astype("int64"), frame["가용대수"], strict=True
    ):
        if not str(process):
            continue
        place = (str(process), int(month))
        lookup[place] = lookup.get(place, 0.0) + float(value)
    return lookup


def _share(window: WdWindow, deadline: date) -> float:
    """마감이 `deadline` 인 호기가 이 구간에 보태는 몫(환산비 1) — 다음 날부터 센다."""
    days = (window.boundary_end - max(deadline, window.boundary_start)).days
    return max(0, days) / window.days


def reverse_static_schedule(
    *,
    units: Sequence[ReverseUnit],
    fixed: Mapping[tuple[str, int], float],
    static: Mapping[tuple[str, int], float],
    cutoff_days: Mapping[str, float],
    months: Sequence[int],
    today: date,
) -> StaticQualSchedule:
    """역산 몸통 — 순수 계산(모듈 docstring 「역산」 · 「남는 몫 셋」).

    `units` 는 `reverse_targets` 의 차례 그대로다. `fixed` 는 `(공정, 달) → 고정 대수`(비가동 없이
    센
    환산)이고 없는 자리는 0 이다. `static` 은 `static_availability_lookup` 의 결과다. Cut-off 가
    없는
    공정은 역산하지 않는다(설비 일정 기준 가용도 낼 수 없다).
    """
    ordered = tuple(sorted({int(month) for month in months}))
    by_process: dict[str, list[ReverseUnit]] = {}
    for unit in units:
        by_process.setdefault(unit.process, []).append(unit)
    static_processes = sorted({process for process, _ in static if process in cutoff_days})
    assignments: list[StaticAssignment] = []
    checks: list[StaticMonthCheck] = []
    for process in static_processes:
        queue = list(by_process.get(process, []))
        placed: list[tuple[ReverseUnit, date]] = []
        for month in ordered:
            window = wd_window(month, float(cutoff_days[process]))
            base = float(fixed.get((process, month), 0.0))
            carried_shares = 0.0
            for unit, deadline in placed:
                carried_shares += unit.ratio * _share(window, deadline)
            carried = base + carried_shares
            target = static.get((process, month))
            if target is None or not math.isfinite(target):
                checks.append(StaticMonthCheck(process, month, None, base, carried, 0.0, 0.0))
                continue
            need = float(target) - carried
            added = 0.0
            while need > _EPS and queue:
                unit = queue.pop(0)
                ratio = unit.ratio
                if ratio <= 0:
                    continue
                if need >= ratio - _EPS:
                    deadline = window.boundary_start
                    part = ratio
                else:
                    days = math.ceil(need * window.days / ratio - _EPS)
                    deadline = window.boundary_end - timedelta(days=days)
                    part = ratio * days / window.days
                placed.append((unit, deadline))
                assignments.append(
                    StaticAssignment(
                        process=process,
                        unit=unit.unit,
                        month=month,
                        deadline=deadline,
                        current=max(deadline, today),
                        part=part,
                    )
                )
                added += part
                need -= part
            shortfall = need if need > _SHORT_EPS else 0.0
            checks.append(
                StaticMonthCheck(process, month, float(target), base, carried, added, shortfall)
            )
    return StaticQualSchedule(
        months=ordered,
        today=today,
        units=tuple(units),
        assignments=tuple(assignments),
        checks=tuple(checks),
        static_processes=tuple(static_processes),
    )


def fixed_counts(
    *,
    spans: pd.DataFrame,
    equipment: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    excluded: Iterable[str],
) -> dict[tuple[str, int], float]:
    """`(공정, 달) → 고정 대수` — `excluded`(역산하는 모듈 행) 밖 호기와 기존 보유대수 표의 환산
    가용.

    `spans` 는 **비가동 없이** 만든 세는
    구간(`build_equipment_lifecycle_spans(with_unit_share=True)`)
    이다(Q07 (가)). 설비 일정 기준 가용과 같은 엔진 · 같은 환산이라 반출 · 정지 · 사용기준이 그대로
    든다. 모듈 행을 걸러도 남은 행의 지분은 그대로다(지분은 구간을 만들 때 매긴다).
    """
    ordered = sorted({int(month) for month in months})
    if not ordered:
        return {}
    dropped = {str(name).strip() for name in excluded}
    kept = (
        spans.loc[
            ~spans[EQUIPMENT_ID_COLUMN].astype("string").str.strip().isin(dropped).fillna(False)
        ]
        if not spans.empty and dropped
        else spans
    )
    prepared = prepare_equipment_master(equipment)
    ratios = {
        str(unit).strip(): float(ratio)
        for unit, ratio in zip(
            prepared[EQUIPMENT_ID_COLUMN], prepared[CONVERSION_RATIO_COLUMN], strict=True
        )
    }
    monthly = build_monthly_equipment_availability(
        kept, baseline, cutoff, ordered, conversion_ratios=ratios
    )
    available = dynamic_available_equipment(monthly, weighted=True)
    return {
        (str(process).strip(), int(month)): float(value)
        for month, process, value in zip(
            available["생산계획년월"], available["공정"], available["가용대수"], strict=True
        )
    }


def build_static_qual_schedule(
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    static_availability: pd.DataFrame,
    months: Sequence[int],
    today: date,
    spans_without_downtime: pd.DataFrame | None = None,
) -> StaticQualSchedule:
    """설비 마스터 · 기존 보유 · Cut-off · Static 가용대수로 역산한다. **어느 DB 도 열지 않는다.**

    `spans_without_downtime` 은 같은 마스터를 **비가동 없이**(`downtime` 의 빈 사본)
    `span_date_range(months, cutoff)` 범위로 만든 세는 구간이다(`simulation_cache` 가 캐시한 것).
    주지
    않으면 여기서 만든다. `downtime` 은 그 빈 사본의 칸 꼴에만 쓴다 — 역산은 비가동을 보지 않는다.
    """
    ordered = tuple(sorted({int(month) for month in months}))
    units = reverse_targets(equipment)
    lookup = cutoff_lookup(cutoff)
    static = static_availability_lookup(static_availability, ordered)
    reversing = {process for process, _ in static if process in lookup}
    excluded = [
        equipment_id
        for unit in units
        if unit.process in reversing
        for equipment_id in unit.equipment_ids
    ]
    span = span_date_range(ordered, cutoff) if ordered else None
    fixed: dict[tuple[str, int], float] = {}
    if span is not None:
        if spans_without_downtime is None:
            spans_without_downtime = build_equipment_lifecycle_spans(
                equipment,
                downtime.iloc[0:0],
                start_date=span[0],
                end_date=span[1],
                with_unit_share=True,
            )
        fixed = fixed_counts(
            spans=spans_without_downtime,
            equipment=equipment,
            baseline=baseline,
            cutoff=cutoff,
            months=ordered,
            excluded=excluded,
        )
    return reverse_static_schedule(
        units=units,
        fixed=fixed,
        static=static,
        cutoff_days=lookup,
        months=ordered,
        today=today,
    )
