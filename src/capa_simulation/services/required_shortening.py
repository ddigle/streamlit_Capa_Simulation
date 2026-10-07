# Purpose: 목표 확보율에 모자란 공정·월마다 신규 호기 Qual 을 며칠 당겨야 하는지 계산한다.

"""필요단축일정.

Dynamic 가용대수(호기 일정을 Cut-off W/D 구간에 일할한 환산대수)가 시나리오 소요대수 x 목표
확보율에 모자라는 달이 있으면, **아직 Qual 이 끝나지 않은 신규 호기의 Qual 을 얼마나 앞당기면
그 달을 채우는가**를 낸다. 당길 호기가 바닥나면 「추가1」「추가2」… 가상 호기가 언제까지 Qual 을
마쳐야 하는지를 낸다(2026-10-07 사용자 결정).

## 가용과 소요

- 가용은 `build_monthly_equipment_availability` 의 **환산 소계**(`기존보유` + `가용`)다 —
  Static/Dynamic 탭의 Dynamic 과 같은 줄에서 나온다. 비가동도 그대로 반영되고, 사용기준이 HBM 인
  호기만 들며, 실행일 전의 반출·이설 예정 호기도 가용이면 든다(실행일 당일부터는 빠진다).
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
   **오늘이 구간 안인 달은 한 대가 남은 날만큼만 덮는다** — 오늘이 구간 끝에 가까울수록 대수가 늘고,
   그 대수가 뒤 달에 온전한 1대씩으로 남아 뒤 달 가용이 필요보다 크게 넘친다. 그래도 그 달을 다 채울
   때까지 더한다(사용자 결정 2026-10-07: 지금대로).
5. 그 달 구간이 이미 오늘로 끝났으면(`max(구간 앞, 오늘) >= 구간 끝`) 당겨서 채울 수 없으므로
   「단축으로 못 채움(기한 지남)」으로 두고 넘어간다.
6. 한 달에 가상 호기가 상한(`_MAX_VIRTUAL_UNITS_PER_MONTH`)을 넘으면 그 달에 더한 가상 호기를
   **모두 걷고** 「신규로도 못 채움(남은 날 부족)」으로 남은 부족을 보인다. 남겨 두면 뒤 달이 그
   몫을 공짜로 받아 실제 부족을 가린다. 그 달에 당긴 실제 호기는 그대로 둔다.
7. 원래 모자랐는데 그 달에 손대지 않고 채워진 달은 무엇이 채웠는지 적는다 — 앞 달의 단축이면
   「앞달 단축으로 해소」, 앞 달의 가상 호기면 「앞달 신규로 해소」, 둘 다면
   「앞달 단축·신규로 해소」.

## 후보

신규 호기(`기존설비여부` N, `보관유무` N) 가운데 사용기준이 HBM 이고(`counts_for_capacity` — 다른
호기는 가용대수에 들지 않으니 당겨도 늘지 않는다) Qual일정이 있고 확정상태가 「완료」가 아니며
반출·이설 일정이 없는 것. 모듈 행은 설비키(`Main 설비`, 없으면 `설비명`)로 묶어 **한 대로 함께
당긴다** — 묶음의 Qual 은 가장 늦은 모듈의 Qual 이고, 목표 날짜보다 늦은 모듈만 그 날짜로 온다.
묶음의 환산비는 모듈 행 환산비의 합이다. 묶음에 HBM 이 아닌 모듈이 섞이면 HBM 모듈만 묶는다.

**반입일정은 보지 않는다**(하한이 아니다). 상태 판정 엔진은 반입 전을 「입고 예정」으로 세므로
당긴 날짜가 반입보다 이르면 엔진으로 다시 재면 0 이 된다 — 그래서 늘어나는 몫은 엔진을 다시
돌리지 않고 위 식으로 낸다. 그 호기의 **운영 비가동 일정**과 겹친 날은 엔진처럼 기여하지 않는다.

## 내보내기

`unit_export_frame` 은 호기마다 한 줄로 기존 일정 → 단축 일정과 호기 마스터 속성, 대상 월의
부족을 펼친 표다(「호기별 단축 일정 CSV」). 목표 여럿을 넘기면 목표마다 블록으로 잇고
`목표 확보율(%)` 칸으로 가른다. 마스터 속성은 계산할 때 후보마다 한 번 모아 결과
(`ShorteningPlan.unit_master`)에 싣는다 — 화면이 rerun 마다 호기 마스터를 다시 검증하지 않게.
모듈 묶음은 **옮기는 모듈 행**의 값이고, 묶음 안에서 값이 갈리면 글자는 서로 다른 값을 모듈
차례로 「, 」로 잇고 반입일정은 가장 늦은 모듈의 날이다(묶음 Qual 과 같은 규칙). 가상 호기
「추가N」은 마스터에 없으므로 속성·기존 일정이 빈칸이다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    counts_for_capacity,
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
    "LEVEL_COLUMN",
    "PROCESS_MONTH_COLUMNS",
    "PROCESS_MONTH_EXPORT_COLUMNS",
    "STATUS_CARRIED",
    "STATUS_CARRIED_BOTH",
    "STATUS_CARRIED_NEW",
    "STATUS_EXPIRED",
    "STATUS_MET",
    "STATUS_NEW_LIMIT",
    "STATUS_SHORTENED",
    "STATUS_WITH_NEW",
    "TARGET_LEVELS",
    "UNIT_EXPORT_COLUMNS",
    "UNIT_MASTER_COLUMNS",
    "UNIT_PLAN_COLUMNS",
    "VIRTUAL_UNIT_PREFIX",
    "CandidateModule",
    "CandidateUnit",
    "LevelPlan",
    "ShorteningPlan",
    "level_percent",
    "plan_from_availability",
    "plan_required_shortening",
    "process_month_export_frame",
    "shortening_candidates",
    "unit_export_frame",
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
STATUS_CARRIED_NEW = "앞달 신규로 해소"
STATUS_CARRIED_BOTH = "앞달 단축·신규로 해소"
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

LEVEL_COLUMN = "목표 확보율(%)"
"""내보내기 표의 목표 칸. 90·100·110·120·130 정수다(`level_percent`)."""

# 내보내기 표가 호기 줄에 붙이는 호기 마스터 속성. 이름은 마스터 계약 그대로다.
_MASTER_TEXT_COLUMNS = (
    "공정대분류",
    "공정소분류",
    "Model",
    "동",
    "층",
    "투자구분",
    PARENT_EQUIPMENT_COLUMN,
)
UNIT_MASTER_COLUMNS = (
    "호기",
    *_MASTER_TEXT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    "모듈 수",
    CONVERSION_RATIO_COLUMN,
    ARRIVAL_DATE_COLUMN,
    "확정상태",
)
"""후보 호기(모듈 묶음은 한 대)마다 마스터 속성 한 줄. `설비명` 은 묶음의 모듈 행을 잇는다."""

UNIT_EXPORT_COLUMNS = (
    LEVEL_COLUMN,
    "공정",
    "Cut-off(일)",
    "호기",
    "구분",
    *UNIT_MASTER_COLUMNS[1:],
    "기존 Qual 완료일",
    "기존 기여 시작일",
    "목표 Qual 완료일",
    "목표 기여 시작일",
    "단축일수",
    "늘어난 환산대수",
    "대상 월",
    "대상 월 부족 대수(단축 전)",
    "대상 월 부족 대수(단축 후)",
    "해소 기여 월",
)
"""「호기별 단축 일정 CSV」 의 칸. 날짜는 `YYYY-MM-DD`, 달은 `YYYY-MM` 글자다."""

PROCESS_MONTH_EXPORT_COLUMNS = (LEVEL_COLUMN, *PROCESS_MONTH_COLUMNS)
"""「공정·월 CSV」 의 칸 — 공정 x 월 표 앞에 목표 칸을 붙인다."""

_ONE_DAY = timedelta(days=1)
# 부동소수 끝자리를 털어 내는 자리. `securement_rate._ceil_positive` 와 같은 9자리다 — 0 이어야 할
# 과부족이 -1e-15 로 남으면 그것이 「부족」으로 읽혀 호기 하나를 쓸데없이 당긴다.
_DECIMALS = 9
# 한 공정·한 달에 더하는 가상 호기의 상한(폭주 방지). 구간이 거의 지난 이번 달은 한 대가 1/31 대만
# 덮어 수십 대가 필요하다고 나올 수 있다 — 넘으면 그 달의 가상 호기를 걷고 「신규로도 못 채움」이다.
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

    unit_master: pd.DataFrame = field(default_factory=lambda: _empty_unit_master())
    """후보 호기마다 마스터 속성 한 줄(`UNIT_MASTER_COLUMNS`). 내보내기가 `호기` 로 붙인다.

    호기 마스터에서 나오므로 캐시 키의 마스터 내용 지문이 이것도 덮는다.
    """

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


def level_percent(level: float) -> int:
    """목표 확보율의 백분율 정수(1.1 → 110). 내보내기의 목표 칸과 파일 이름이 쓴다."""
    return round(level * 100)


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
            # 사용기준이 HBM 이 아닌 호기는 당겨도 가용대수가 늘지 않는다 — 후보로 끌어오지 않는다.
            & counts_for_capacity(prepared)
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
    spans: pd.DataFrame | None = None,
) -> ShorteningPlan:
    """호기 마스터·비가동·기존보유·Cut-off·소요대수로 다섯 목표의 단축 일정을 낸다.

    **어느 DB 도 열지 않는다.** 가용은 Static/Dynamic 탭과 같은 길로 만든다 — W/D 구간이 Cut-off
    만큼 앞으로 밀리므로 호기 구간은 `span_date_range` 가 알려 주는 범위로 만들고, 지분이 바뀌는
    날에도 끊는다(`with_unit_share=True`).

    `spans` 는 그 구간을 이미 만들어 둔 것이다(`simulation_cache` 가 Static/Dynamic 과 나눠 쓰는
    캐시). **같은 마스터·비가동으로 `span_date_range(months, cutoff)` 범위를 `with_unit_share=True`
    로 만든 표여야 한다** — 주지 않으면 여기서 만든다.
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
        if spans is None:
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
        unit_master=_unit_master(prepared, candidates),
    )


def _unit_master(prepared: pd.DataFrame, candidates: Sequence[CandidateUnit]) -> pd.DataFrame:
    """후보마다 마스터 속성 한 줄. `prepared` 는 `prepare_equipment_master` 를 거친 표다.

    모듈 묶음은 **옮기는 모듈 행**(`CandidateUnit.modules`)만 본다 — 모듈 수·환산비가 계산이 쓴 그
    묶음의 것이어야 `늘어난 환산대수` 와 맞는다. 공정대분류·공정소분류·투자구분·동·층은 검증이 묶음
    안에서 같게 막아 두고, 그 밖의 글자(Model·확정상태)가 갈리면 서로 다른 값을 모듈 차례로 잇는다.
    반입일정은 가장 늦은 모듈의 날이다 — 묶음 Qual 이 가장 늦은 모듈의 Qual 인 것과 같다.
    """
    if prepared.empty or not candidates:
        return _empty_unit_master()
    ids = prepared[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    wanted = {module.equipment_id for unit in candidates for module in unit.modules}
    chosen = ids.isin(wanted).fillna(False).to_numpy()
    by_id = {
        str(equipment_id): {str(key): value for key, value in row.items()}
        for equipment_id, row in zip(
            ids.loc[chosen], prepared.loc[chosen].to_dict("records"), strict=True
        )
    }
    rows: list[dict[str, object]] = []
    for unit in candidates:
        members = [by_id[module.equipment_id] for module in unit.modules]
        arrivals = [
            day for member in members if (day := _as_date(member[ARRIVAL_DATE_COLUMN])) is not None
        ]
        row: dict[str, object] = {"호기": unit.unit}
        for column in (*_MASTER_TEXT_COLUMNS, "확정상태"):
            row[column] = _distinct_text(member[column] for member in members)
        row[EQUIPMENT_ID_COLUMN] = ", ".join(module.equipment_id for module in unit.modules)
        row["모듈 수"] = len(unit.modules)
        row[CONVERSION_RATIO_COLUMN] = round(unit.ratio, _DECIMALS)
        row[ARRIVAL_DATE_COLUMN] = max(arrivals) if arrivals else None
        rows.append(row)
    frame = pd.DataFrame(rows, columns=list(UNIT_MASTER_COLUMNS))
    frame["모듈 수"] = frame["모듈 수"].astype("int64")
    frame[CONVERSION_RATIO_COLUMN] = frame[CONVERSION_RATIO_COLUMN].astype("float64")
    return frame


def _distinct_text(values: Iterable[object]) -> str | None:
    """빈칸을 빼고 서로 다른 값을 처음 나온 차례로 「, 」로 잇는다. 하나도 없으면 None."""
    seen: list[str] = []
    for value in values:
        if _blank(value):
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return ", ".join(seen) if seen else None


def _blank(value: object) -> bool:
    """표 칸이 비었는가 — None·`pd.NA`·NaN·NaT."""
    return (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    )


def _as_date(value: object) -> date | None:
    """표 칸의 날짜. `pd.NaT` 도 `datetime` 이라 먼저 걸러야 한다."""
    if _blank(value) or not isinstance(value, date):
        return None
    return value.date() if isinstance(value, datetime) else value


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
                units=_unit_frame(unit_rows),
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
                # 그 달에 더한 가상 호기를 **모두 걷는다.** 남기면 뒤 달이 그 몫을 공짜로 받아
                # 실제 부족을 가린다 — 뒤 달은 걷은 뒤의 가용으로 제 가상 호기를 따로 받는다.
                for virtual in virtuals[-added:]:
                    _remove_virtual(virtual, windows, after)
                del virtuals[-added:]
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
        _month_status(
            base[index] - required[index] * level,
            actions[index],
            pulled=any(_adds(state.extra, window.year_month) for state in states),
            added=any(_adds(virtual.extra, window.year_month) for virtual in virtuals),
        )
        for index, window in enumerate(windows)
    ]
    return _ProcessOutcome(windows, base, after, required, status, states, virtuals)


def _adds(extra: Mapping[int, float], year_month: int) -> bool:
    return round(extra.get(year_month, 0.0), _DECIMALS) > 0


def _month_status(before_gap: float, action: str, *, pulled: bool, added: bool) -> str:
    """원래 모자랐는데 이 달에 손대지 않고 채워졌으면, 앞 달의 무엇이 채웠는지를 가른다."""
    if not _short(-before_gap):
        return STATUS_MET
    if action:
        return action
    if added and pulled:
        return STATUS_CARRIED_BOTH
    return STATUS_CARRIED_NEW if added else STATUS_CARRIED


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


def _remove_virtual(virtual: _VirtualState, windows: list[WdWindow], after: list[float]) -> None:
    """`_add_virtual` 이 더한 몫을 그대로 뺀다."""
    for index, window in enumerate(windows):
        after[index] -= virtual.extra.get(window.year_month, 0.0)


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


def _unit_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """호기 표. 정수 칸은 가상 호기의 빈칸 때문에 실수로 바뀌지 않게 `Int64` 로 못박는다."""
    frame = _frame(rows, UNIT_PLAN_COLUMNS, _empty_units())
    for column in ("단축일수", "대상 월", "모듈 수"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    frame["늘어난 환산대수"] = pd.to_numeric(frame["늘어난 환산대수"]).astype("float64")
    return frame


def _empty_process_months() -> pd.DataFrame:
    frame = pd.DataFrame({column: pd.Series(dtype="float64") for column in PROCESS_MONTH_COLUMNS})
    frame["공정"] = frame["공정"].astype("object")
    frame["생산계획년월"] = frame["생산계획년월"].astype("int64")
    frame["상태"] = frame["상태"].astype("object")
    return frame


def _empty_units() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in UNIT_PLAN_COLUMNS})


def _empty_unit_master() -> pd.DataFrame:
    frame = pd.DataFrame({column: pd.Series(dtype="object") for column in UNIT_MASTER_COLUMNS})
    frame["모듈 수"] = frame["모듈 수"].astype("int64")
    frame[CONVERSION_RATIO_COLUMN] = frame[CONVERSION_RATIO_COLUMN].astype("float64")
    return frame


# ---------------------------------------------------------------------- 내보내기


def unit_export_frame(
    plan: ShorteningPlan,
    levels: Sequence[float],
    processes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """호기마다 한 줄 — 「호기별 단축 일정 CSV」 의 표(`UNIT_EXPORT_COLUMNS`).

    `levels` 마다 블록으로 잇고 `목표 확보율(%)` 칸으로 가른다. 공정은 `processes` 차례(화면의 표시
    순서)이고, 없으면 맞댄 공정 전체다. 공정 안은 계산 결과의 차례(당긴 호기는 기존 Qual 순, 그
    뒤에 가상 호기)다. 달은 고르지 않는다 — 결과는 이미 고른 달로만 계산한 것이다.

    - `기존/목표 기여 시작일` 은 Qual 다음 날이다(`services/wd_window.py` 의 규약).
    - `대상 월 부족 대수(단축 전/후)` 는 그 목표에서 대상 월의 `목표대수 - 가용대수` 를 0 아래로
      자른 양수다. 단축 후는 **그 목표의 모든 단축·가상 호기를 반영한 뒤**의 값이라 호기 하나의 몫이
      아니다.
    - 가상 호기 「추가N」은 마스터 속성·기존 일정·단축일수가 빈칸이다.
    """
    names = list(plan.processes) if processes is None else [str(name) for name in processes]
    master = {
        str(row["호기"]): {str(key): value for key, value in row.items()}
        for row in plan.unit_master.to_dict("records")
    }
    rows: list[dict[str, object]] = []
    for level in levels:
        level_plan = plan.at(level)
        months = level_plan.process_months
        gaps = {
            (str(process), int(month)): (float(before), float(after))
            for process, month, before, after in zip(
                months["공정"],
                months["생산계획년월"],
                months["과부족"],
                months["단축후과부족"],
                strict=True,
            )
        }
        by_process: dict[str, list[dict[str, object]]] = {}
        for record in level_plan.units.to_dict("records"):
            row = {str(key): value for key, value in record.items()}
            by_process.setdefault(str(row["공정"]), []).append(row)
        for process in names:
            for row in by_process.get(process, []):
                rows.append(
                    _export_row(
                        row,
                        level=level,
                        cutoff_days=plan.cutoff_days.get(process),
                        master=master,
                        gaps=gaps,
                    )
                )
    frame = pd.DataFrame(rows, columns=list(UNIT_EXPORT_COLUMNS))
    for column in (LEVEL_COLUMN, "Cut-off(일)", "모듈 수", "단축일수"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    for column in (
        CONVERSION_RATIO_COLUMN,
        "늘어난 환산대수",
        "대상 월 부족 대수(단축 전)",
        "대상 월 부족 대수(단축 후)",
    ):
        frame[column] = pd.to_numeric(frame[column]).astype("float64")
    return frame


def _export_row(
    row: Mapping[str, object],
    *,
    level: float,
    cutoff_days: int | None,
    master: Mapping[str, Mapping[str, object]],
    gaps: Mapping[tuple[str, int], tuple[float, float]],
) -> dict[str, object]:
    process = str(row["공정"])
    shortened = row["구분"] == KIND_SHORTENED
    attributes = master.get(str(row["호기"]), {}) if shortened else {}
    original = _as_date(row["기존 Qual"]) if shortened else None
    target = _as_date(row["목표 Qual"])
    month = _whole_number(row["대상 월"])
    before, after = (math.nan, math.nan)
    if month is not None:
        before, after = gaps.get((process, month), (math.nan, math.nan))
    contributed = "" if _blank(row["해소 기여 월"]) else str(row["해소 기여 월"])
    return {
        LEVEL_COLUMN: level_percent(level),
        "공정": process,
        "Cut-off(일)": cutoff_days,
        "호기": row["호기"],
        "구분": row["구분"],
        **{column: attributes.get(column) for column in UNIT_MASTER_COLUMNS[1:]},
        ARRIVAL_DATE_COLUMN: _iso_date(_as_date(attributes.get(ARRIVAL_DATE_COLUMN))),
        "기존 Qual 완료일": _iso_date(original),
        "기존 기여 시작일": _iso_date(original + _ONE_DAY if original else None),
        "목표 Qual 완료일": _iso_date(target),
        "목표 기여 시작일": _iso_date(target + _ONE_DAY if target else None),
        "단축일수": None if _blank(row["단축일수"]) else row["단축일수"],
        # 하루씩 더한 몫이라 끝자리에 부동소수 찌꺼기가 남는다(1.0 이 0.9999999999999993).
        "늘어난 환산대수": round(float(str(row["늘어난 환산대수"])), _DECIMALS),
        "대상 월": _iso_month(month),
        "대상 월 부족 대수(단축 전)": _shortage(before),
        "대상 월 부족 대수(단축 후)": _shortage(after),
        "해소 기여 월": ", ".join(
            _iso_month(int(part)) or "" for part in contributed.split(",") if part.strip()
        ),
    }


def process_month_export_frame(
    plan: ShorteningPlan,
    levels: Sequence[float],
    processes: Sequence[str] | None = None,
    months: Sequence[int] | None = None,
) -> pd.DataFrame:
    """「공정·월 CSV」 의 표(`PROCESS_MONTH_EXPORT_COLUMNS`).

    목표마다 블록이고 공정은 `processes` 차례, 공정 안은 달 차례다.
    """
    names = list(plan.processes) if processes is None else [str(name) for name in processes]
    wanted = list(plan.months if months is None else (int(month) for month in months))
    order = {name: index for index, name in enumerate(names)}
    blocks: list[pd.DataFrame] = []
    for level in levels:
        frame = plan.at(level).process_months
        chosen = frame.loc[frame["공정"].isin(names) & frame["생산계획년월"].isin(wanted)].copy()
        chosen["_order"] = chosen["공정"].map(order)
        chosen = chosen.sort_values(["_order", "생산계획년월"], kind="stable").drop(
            columns="_order"
        )
        chosen.insert(0, LEVEL_COLUMN, level_percent(level))
        blocks.append(chosen)
    if not blocks:
        return pd.DataFrame(columns=list(PROCESS_MONTH_EXPORT_COLUMNS))
    return pd.concat(blocks, ignore_index=True).loc[:, list(PROCESS_MONTH_EXPORT_COLUMNS)]


def _whole_number(value: object) -> int | None:
    """표 칸의 정수(`Int64` 의 빈칸은 None)."""
    return None if _blank(value) else int(str(value))


def _iso_date(day: date | None) -> str | None:
    return day.isoformat() if day is not None else None


def _iso_month(month: int | None) -> str | None:
    """`202605` → `2026-05`."""
    return None if month is None else f"{month // 100}-{month % 100:02d}"


def _shortage(gap: float) -> float | None:
    """과부족(음수가 부족)을 부족 대수(양수, 채웠으면 0)로. 그 달 행이 없으면 None."""
    if math.isnan(gap):
        return None
    return max(0.0, round(-gap, _DECIMALS))
