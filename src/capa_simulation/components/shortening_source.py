# Purpose: 필요 단축 일정 화면과 Space 필요 단축 보기가 같은 함수·키·캐시 칸으로 계획을 꺼내게 한다.

"""필요 단축 계획 꺼내기 — 두 화면의 한 길(2026-10-24 사용자 결정 — Space 「필요 단축」 보기 R4).

필요 단축 일정 화면(`app_pages/required_shortening.py`·`required_shortening_panel`)과 Space 현황 색
기준 「필요 단축」(`space_shortening_view`)이 **같은 함수로 키를 내고 같은 캐시 칸**에서 계획을
받는다(AGENTS 5장 19 「같은 계산은 같은 함수로 키」). 이 모듈에는 캐시 데코레이터가 없다 — 캐시
경계는 `simulation_cache` 그대로다.

- 세 세션 칸(목표·시작 월·끝 월)은 여기 두고 패널이 다시 내보낸다.
- 수요(`load_shortening_demand`) — 활성 시나리오·조회기간 → 시나리오 키·소요대수 로더·계산 오류
  확인. 못 읽으면 `BOOTSTRAP_ERRORS` 를 그대로 올린다.
- 달(`shortening_month_options`) — Cut-off 빔·조회기간에 소요대수 없음·고를 달 없음이면
  `ShorteningStop`(두 화면이 같은 글로 멈춘다).
- 공용 조회 조건(0019)을 못 읽으면 빈 프로필(= 코드 기본 달)로 계속한다 — 두 화면이 같이 물러선다.
- 샘플 fleet 세 표(`shortening_frames`)와 계획(`load_official_shortening` — 공식 칸, UPEH 가정 토큰
  `()`).
- 입력 비가동 대수(`manual_downtime_for` — 가용설비 현황 › Preference, 설비 0032)는 두 화면이 같은
  값을 계획 키에 싣는다. 못 읽으면 예외를 그대로 올린다 — 빈 값으로 물러서면 가용이 말없이 커진다.

아래로 내려가는 부름은 **모듈 속성으로** 한다(`page_bootstrap.load_page_context()`·
`simulation_cache.…`·`equipment_cache.…`) — 시험이 모듈 속성을 갈아 끼워 부름을 센다. 공정
표시명을 읽지 않는다(표시명은 패널 몫이다).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Final

import pandas as pd

import capa_simulation.page_bootstrap as page_bootstrap
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.shortening_filter_profile import ShorteningFilterProfile

__all__ = [
    "SHORTENING_END_KEY",
    "SHORTENING_LEVEL_KEY",
    "SHORTENING_START_KEY",
    "CUTOFF_FIRST_MESSAGE",
    "Frames",
    "ShorteningDemand",
    "ShorteningStop",
    "load_official_shortening",
    "load_shortening_demand",
    "manual_downtime_for",
    "month_options",
    "shortening_filter_profile_or_default",
    "shortening_frames",
    "shortening_month_options",
]

SHORTENING_LEVEL_KEY: Final = "equipment_shortening_level_v1"
SHORTENING_START_KEY: Final = "equipment_shortening_start_month_v1"
SHORTENING_END_KEY: Final = "equipment_shortening_end_month_v1"

CUTOFF_FIRST_MESSAGE: Final = (
    "공정별 Cut-off 를 먼저 적어야 설비 일정 기준 가용대수와 필요 단축 일정을 낼 수 있습니다 "
    "(가용설비 현황 › 설정 › Cut-off)."
)

# (기존 보유대수, 설비 마스터, 비가동 일정).
Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]


@dataclass(frozen=True)
class ShorteningDemand:
    """활성 시나리오 쪽 — 화면 문맥, 시나리오 키, 소요대수 로더(빗나갈 때만 푼다)."""

    context: page_bootstrap.PageContext
    key: simulation_cache.ScenarioCacheKey
    loader: Callable[[], pd.DataFrame]


@dataclass(frozen=True)
class ShorteningStop:
    """계획을 세우지 못한 까닭 — 두 화면이 같은 글로 알리고 멈춘다.

    `kind` 는 `scenario`(활성 시나리오 경고 — `message` 는 덧붙일 까닭), `info`, `error` 다.
    """

    kind: str
    message: str | None = None


def load_shortening_demand() -> ShorteningDemand:
    """활성 시나리오·조회기간의 수요. 계산이 서는지 먼저 본다(적중이면 프레임을 풀지 않는다).

    못 읽었거나 계산이 멈췄으면 `BOOTSTRAP_ERRORS` 를 그대로 올린다 — 받는 화면이 까닭을 알린다.
    """
    context = page_bootstrap.load_page_context()
    key = simulation_cache.scenario_cache_key(
        context.reference_version,
        context.active_scenario,
        context.selected_start_month,
        context.selected_end_month,
    )
    loader = simulation_cache.scenario_required_equipment(
        key,
        scenario_tables=context.active_scenario["tables"],
        reference_tables=context.reference_tables,
    )
    simulation_cache.check_scenario_capacity(
        key,
        _scenario_tables=context.active_scenario["tables"],
        _reference_tables=context.reference_tables,
        _required_equipment=loader,
    )
    return ShorteningDemand(context=context, key=key, loader=loader)


def _months_between(start: int, end: int) -> list[int]:
    if start > end:
        return []
    months: list[int] = []
    year, month = divmod(start, 100)
    while year * 100 + month <= end:
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def month_options(context: page_bootstrap.PageContext, demand_months: tuple[int, int]) -> list[int]:
    """고를 수 있는 달 — 사이드바 조회기간 가운데 소요대수가 있는 범위(HOME 「적용」 범위).

    `demand_months` 는 소요대수가 있는 첫 달·끝 달(`get_required_month_span`)이다.
    """
    start = max(context.selected_start_month, demand_months[0])
    end = min(context.selected_end_month, demand_months[1])
    return _months_between(start, end)


def shortening_month_options(
    demand: ShorteningDemand, cutoff: pd.DataFrame
) -> list[int] | ShorteningStop:
    """고를 수 있는 달, 또는 멈출 까닭(Cut-off 빔·달 범위를 못 꺼냄·조회기간에 소요대수 없음·달
    없음)."""
    if cutoff.empty:
        return ShorteningStop("info", CUTOFF_FIRST_MESSAGE)
    try:
        demand_months = simulation_cache.get_required_month_span(
            demand.key, _required_equipment=demand.loader
        )
    except page_bootstrap.BOOTSTRAP_ERRORS as exc:
        # 오류 확인이 적중한 뒤 밀려난 소요대수를 다시 꺼내다 멈춘 자리다 — 수요를 못 읽은 것과 같은
        # 경고로 알린다.
        return ShorteningStop("scenario", page_bootstrap.bootstrap_error_message(exc))
    if demand_months is None:
        # 조회기간에 소요대수가 하나도 없다 — 다른 계산 화면(`resolve_effective_months`)과 같은
        # 문구.
        return ShorteningStop("error", page_bootstrap.no_demand_message(demand.context))
    options = month_options(demand.context, demand_months)
    if not options:
        return ShorteningStop("info", "조회기간에 월이 없습니다.")
    return options


def shortening_filter_profile_or_default(database_path: str | None) -> ShorteningFilterProfile:
    """공용 조회 조건. 경로가 없거나 못 읽으면 빈 프로필(= 코드 기본값)이다 — 화면은 떠야 한다."""
    if database_path is None:
        return ShorteningFilterProfile()
    try:
        return equipment_cache.load_shortening_filter_profile(database_path)
    except page_bootstrap.BOOTSTRAP_ERRORS:
        return ShorteningFilterProfile()


def shortening_frames(
    saved: Frames, *, sample: bool, show_sample: bool, has_snapshot: bool, today: date
) -> Frames:
    """계산에 넘길 세 표. 설비 마스터가 비어 샘플을 보이는 화면이면 합성 fleet(오늘에 맞춤)이다.

    `saved` 는 **샘플로 갈아 끼우기 전**의 계산 세 표(저장본의 계산 프레임, 없으면 빈 표)다. 기존
    보유는 저장본이 없고 비었을 때만 샘플이다(가용설비 현황 Main 과 같은 fleet).
    """
    baseline, equipment, downtime = saved
    if not (sample and show_sample):
        return baseline, equipment, downtime
    return (
        sample_equipment_baseline() if not has_snapshot and baseline.empty else baseline,
        sample_equipment_master(anchor_date=today),
        sample_downtime_schedule(anchor_date=today),
    )


def manual_downtime_for(database_path: str | None) -> ManualDowntime:
    """입력 비가동 대수(공용 프로필). 경로가 없으면(컴포넌트만 띄운 자리) 빈 값이다. 못 읽으면
    `BOOTSTRAP_ERRORS` 를 그대로 올린다 — 공용 조회 조건과 달리 빈 값으로 물러서지 않는다
    (가용이 말없이 커진다)."""
    if database_path is None:
        return ManualDowntime()
    return equipment_cache.load_manual_downtime(database_path)


def load_official_shortening(
    demand: ShorteningDemand,
    frames: Frames,
    cutoff: pd.DataFrame,
    months: tuple[int, ...],
    today: date,
    *,
    manual_downtime: ManualDowntime,
) -> simulation_cache.KeyedShorteningPlan:
    """다섯 목표의 공식 계획(UPEH 가정 토큰 `()`)과 그 키. **두 화면의 키를 내는 함수가 이것
    하나다.** `manual_downtime` 은 `manual_downtime_for` 로 읽은 입력 비가동이다(키에 실린다).

    설비 마스터가 계약을 어기면 `ValueError` 가 그대로 올라간다.
    """
    baseline, equipment, downtime = frames
    key = simulation_cache.required_shortening_cache_key(
        demand.key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=tuple(months),
        today=today,
        manual_downtime=manual_downtime,
    )
    return simulation_cache.load_required_shortening(
        key, equipment, downtime, baseline, cutoff, required_equipment=demand.loader
    )
