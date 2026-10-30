# Purpose: 제약 시뮬레이션 두 모드(제약 영향 · 개조 일정)가 함께 쓰는 설비 일정 확인(판정 · 까닭
# 카드)과 계획 칸 받기를 한 함수로 둔다.

"""제약 시뮬레이션 — 두 모드가 함께 쓰는 「설비 일정 확인 → 계획」 블록.

두 모드는 같은 가용(설비 일정 기준 단축 전 — 공정 Capa 상세 ② 와 같은 값)으로 계산하므로 멈추는
갈래와 계획 칸이 같다. 페이지(제약 영향)와 `modification_schedule_view`(개조 일정)가 따로 들던 같은
꼴의 블록을 `render_equipment_plan` 하나로 모았다.

- **판정**(`equipment_readiness`) — 설비 DB 를 못 읽었으면 None, 아니면 `dynamic_readiness`. 두 모드
  모두 카드 안에서(개조 일정은 시작 · 기한 선택지에, 제약 영향은 Cut-off 캡션에) 먼저 쓰므로 판정은
  따로 내고 그 값을 `render_equipment_plan` 에 넘긴다.
- **멈추는 갈래**(차례 그대로) — 설비 DB 오류 · 설비 일정이 서지 않음(`readiness.badge`) · (그
  모드의 앞 갈래 `before_plan` — 제약 영향의 제품 갈래) · 계획 계산 오류(「설비 일정을 계산하지
  못했습니다」 + 두 DB 경로) · 계획에 공정 없음(「Cut-off 미기재」 · 「계획에 공정 없음」). 갈래마다
  머리 한 줄과 까닭(카드 또는 오류)을 그리고 None 을 돌려준다 — `st.stop` 은 부르는 쪽이 쥔다.
- **계획** — 공정 Capa 상세 ② 와 같은 칸을 **같은 키**로(`load_required_shortening_for_target`,
  목표는 키 맞춤용 HOME 확보기준 — 단축 열은 읽지 않는다). 계산 함수는 부를 때 `simulation_cache`
  모듈에서 찾는다(페이지 시험이 그 속성을 바꾼다). 제약 영향 모드가 「신규 설비는 개조 없이」 를 켠
  회차에는 같은 키의 설비 일정 칸(공정 Capa 상세 ③·④)을 기준일로 거른 신규 호기도 같은 `try` 안에서
  받는다 — 그 계산이 터져도 「설비 일정을 계산하지 못했습니다」 갈래다.

저장하지 않는다 — 어느 DB 에도 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import NamedTuple, Protocol

import pandas as pd
import streamlit as st

# 이름이 아니라 모듈을 잡는다 — 페이지 시험이 계획 함수를 바꿔 끼운다.
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    ProcessPageInputs,
    bootstrap_error_message,
)
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    DynamicReadiness,
    NewUnitAvailability,
    dynamic_readiness,
    new_unit_availability,
)
from capa_simulation.services.required_shortening import (
    MonthlyTarget,
    ShorteningPlan,
    target_from_thresholds,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

__all__ = [
    "EquipmentPlan",
    "EquipmentPlanSource",
    "ReasonCard",
    "equipment_readiness",
    "render_equipment_plan",
]


class ReasonCard(Protocol):
    """페이지의 까닭 카드 그리기(제목 · 풀이 · 가용설비 현황 링크)."""

    def __call__(self, title: str, detail: str, *, equipment_link: bool) -> None: ...


class EquipmentPlanSource(NamedTuple):
    """설비 일정 확인 · 계획에 드는 것 — 페이지가 공통 진입 · 설비 세션 뒤 한 번 만든다."""

    page_inputs: ProcessPageInputs
    snapshot: EquipmentSnapshot | None
    cutoff: pd.DataFrame
    equipment_error: str
    """설비 DB 를 못 읽은 까닭(빈 글자 = 읽음)."""

    today: date
    manual_downtime: ManualDowntime
    """입력 비가동 대수(가용설비 현황 › Preference) — 계획 키에 실린다(공정 Capa 상세와 같은
    가용)."""


class EquipmentPlan(NamedTuple):
    """멈추지 않은 회차의 계획 — 공정은 `plan.processes` 에 있다."""

    plan: ShorteningPlan
    target_level: MonthlyTarget
    """키 맞춤용 HOME 확보기준 — `plan.at(target_level)` 로 공정 달을 꺼낸다."""

    cutoff_days: int
    new_units: NewUnitAvailability | None
    """`new_unit_since` 를 준 회차의 신규 호기. 아니면 None."""


def equipment_readiness(
    source: EquipmentPlanSource, process: str | None
) -> DynamicReadiness | None:
    """설비 일정을 세울 수 있는가 — 설비 DB 를 못 읽었거나 공정이 없으면 None."""
    if source.equipment_error or process is None:
        return None
    snapshot = source.snapshot
    return dynamic_readiness(
        snapshot.calculation_frames()[1] if snapshot is not None else None,
        snapshot.baseline if snapshot is not None else None,
        source.cutoff,
        process=str(process),
    )


def render_equipment_plan(
    source: EquipmentPlanSource,
    readiness: DynamicReadiness | None,
    *,
    process: str,
    process_label: str,
    subject: str,
    render_header: Callable[[str, str], None],
    render_reason_card: ReasonCard,
    before_plan: Callable[[], bool] | None = None,
    new_unit_since: date | None = None,
) -> EquipmentPlan | None:
    """설비 일정 확인 → (`before_plan`) → 계획. 멈추는 갈래면 머리 한 줄과 까닭을 그리고 None.

    `subject` 는 서지 않는 까닭 카드 풀이의 주어(「제약 시뮬레이션」 · 「개조 일정」)다.
    `before_plan` 은 판정을 지난 뒤 계획 앞에 볼 그 모드의 갈래다 — 까닭을 그리고 거짓을 돌려주면
    멈춘다(계획을 받지 않는다).
    """
    bold = f"**{literal_markdown(process_label)}**"
    if readiness is None:
        render_header(process, f"{bold} :blue-badge[설비 일정 없음: 설비 DB 오류]")
        render_reason_card(
            "설비 일정 없음: 설비 DB 를 읽지 못했습니다",
            source.equipment_error or "설비 DB 를 열지 못했습니다.",
            equipment_link=False,
        )
        return None
    snapshot = source.snapshot
    if not readiness.ready or readiness.cutoff_days is None or snapshot is None:
        render_header(process, f"{bold} :blue-badge[{readiness.badge}]")
        render_reason_card(
            readiness.badge,
            f"{readiness.detail} {subject}{topic_particle(subject)} 설비 일정 기준 가용(공정 Capa "
            "상세 ② 와 같은 값)으로 계산하므로 설비 DB 에 저장본이 있고 이름이 같으며 Cut-off 가 "
            "적힌 공정에만 섭니다.",
            equipment_link=True,
        )
        return None
    if before_plan is not None and not before_plan():
        return None
    try:
        plan, target_level, new_units = _load_plan(
            source, snapshot, process=process, new_unit_since=new_unit_since
        )
    except BOOTSTRAP_ERRORS as exc:
        render_header(process, f"{bold} :blue-badge[설비 일정 없음: 계산 오류]")
        st.error(
            "설비 일정을 계산하지 못했습니다 — "
            + bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH))
        )
        return None
    if process not in plan.processes:
        # 판정을 지나도 계획은 「가용 공정 ∩ 소요 공정」 만 맞댄다 — KeyError 로 떨어뜨리지 않는다.
        missing_cutoff = process in plan.missing_cutoff
        render_header(process, f"{bold} :blue-badge[설비 일정 없음]")
        render_reason_card(
            "설비 일정 없음: Cut-off 미기재"
            if missing_cutoff
            else "설비 일정 없음: 계획에 공정 없음",
            (
                "가용설비 현황의 공정별 Cut-off 에 이 공정이 없습니다."
                if missing_cutoff
                else "설비 일정 기준 가용에 이 공정이 없습니다 — 설비 마스터 공정소분류·기존보유 "
                "공정 이름이 시나리오 공정과 완전히 같아야 맞댑니다."
            ),
            equipment_link=True,
        )
        return None
    return EquipmentPlan(
        plan=plan,
        target_level=target_level,
        cutoff_days=int(readiness.cutoff_days),
        new_units=new_units,
    )


def _load_plan(
    source: EquipmentPlanSource,
    snapshot: EquipmentSnapshot,
    *,
    process: str,
    new_unit_since: date | None,
) -> tuple[ShorteningPlan, MonthlyTarget, NewUnitAvailability | None]:
    """공정 Capa 상세 ②·두 모드와 같은 계획 칸을 같은 키로(목표는 키 맞춤용 HOME 확보기준). 신규
    기준일을 주면 같은 키의 설비 일정 칸을 그 날로 거른 신규 호기도 받는다. 예외는 그대로 올린다."""
    page_inputs = source.page_inputs
    months = list(page_inputs.months)
    active_scenario = page_inputs.context.active_scenario
    baseline, equipment, downtime = snapshot.calculation_frames()
    target_level = target_from_thresholds(page_inputs.thresholds, months)
    shortening_key = simulation_cache.required_shortening_cache_key(
        page_inputs.capacity_cache_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=source.cutoff,
        months=tuple(months),
        today=source.today,
        manual_downtime=source.manual_downtime,
    )
    plan = simulation_cache.load_required_shortening_for_target(
        simulation_cache.required_shortening_target_cache_key(shortening_key, target_level),
        equipment,
        downtime,
        baseline,
        source.cutoff,
        required_equipment=simulation_cache.scenario_required_equipment(
            page_inputs.capacity_cache_key,
            scenario_tables=active_scenario["tables"],
            reference_tables=page_inputs.context.reference_tables,
        ),
    )
    new_units: NewUnitAvailability | None = None
    if new_unit_since is not None:
        new_units = new_unit_availability(
            simulation_cache.get_process_equipment_timeline(
                simulation_cache.process_timeline_key_from_shortening(shortening_key, process),
                equipment,
                downtime,
                baseline,
                source.cutoff,
            ),
            since=new_unit_since,
        )
    return plan, target_level, new_units
