# Purpose: 제약 시뮬레이션 두 모드(제약 영향 · 개조 일정)가 함께 쓰는 설비 일정 확인(판정 · 까닭
# 카드) · 계획 칸 받기와 조건 카드 · 출처 띠의 같은 글 조각을 한 곳에 둔다.

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
  모듈에서 찾는다(페이지 시험이 그 속성을 바꾼다). 제약 영향 모드는 같은 `try` 안에서 두 가지를 더
  받는다 — 「신규 설비는 개조 없이」 를 켠 회차에는 같은 키의 설비 일정 칸(공정 Capa 상세 ③·④ —
  `with_timeline`), 매 회차(개조 켬 · 끔과 무관 — 끄면 칸이 잠긴 채 고름을 보인다) 보유 「호기
  고르기」 선택지(`with_held_units` — 같은 마스터 지문의 가벼운 캐시, 2026-11-01 사용자 결정 B3).
  그 계산이 터져도 「설비 일정을 계산하지 못했습니다」 갈래다. 기준일 거르기 · 고른 호기 빼기는
  페이지가 고른 뒤에 한다(호기 고르기는 이 블록 뒤에 서므로).
- **같은 글 조각** — 두 모드가 글자까지 같게 적는 조건 카드 「이 세션만」 머리
  (`SESSION_ONLY_CAPTION`)와 출처 띠 조각: 소요 시나리오 이름표(`source_scenario_text`) · 설비 기준
  괄호(`source_equipment_text`) · 환산 대수 단서(`CONVERTED_UNITS_NOTE`) · UPEH 가정을 켠 세션의
  단서(`upeh_assumption_note`). 띠의 나머지(소요 설명 · 입력 비가동 · 보유 · 신규)는 모드마다
  다르다.

저장하지 않는다 — 어느 DB 에도 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Final, NamedTuple, Protocol

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
from capa_simulation.scenario_activation import active_scenario_label
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    DynamicReadiness,
    HeldUnitChoice,
    ProcessEquipmentTimeline,
    dynamic_readiness,
)
from capa_simulation.services.required_shortening import (
    MonthlyTarget,
    ShorteningPlan,
    target_from_thresholds,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_DEFAULT_PERCENT,
    UPEH_ASSUMPTION_PERCENT_KEY,
)

__all__ = [
    "CONVERTED_UNITS_NOTE",
    "SESSION_ONLY_CAPTION",
    "UPEH_NOT_APPLIED_NOTE",
    "EquipmentPlan",
    "EquipmentPlanSource",
    "ReasonCard",
    "equipment_readiness",
    "first_ready_process",
    "render_equipment_plan",
    "source_equipment_text",
    "source_scenario_text",
    "upeh_assumption_note",
]

SESSION_ONLY_CAPTION: Final = ":material/person: **이 세션만** — 저장하지 않습니다"
"""조건 카드 「이 세션만」 묶음의 머리 캡션."""

CONVERTED_UNITS_NOTE: Final = (
    " · 대수는 환산 대수 — HOME·Static 확보율(기준정보 가용)과 다를 수 있음"
)
"""출처 띠의 대수 단서 — 설비 기준 괄호 바로 뒤에 잇는다(앞 「 · 」 까지 든다)."""

UPEH_NOT_APPLIED_NOTE: Final = " · UPEH 가정은 이 화면에 걸리지 않습니다(공식 소요)"
"""UPEH 가정을 켠 세션의 출처 띠 단서(`upeh_assumption_note`, 앞 「 · 」 까지 든다)."""


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
    timeline: ProcessEquipmentTimeline | None
    """`with_timeline` 을 준 회차의 그 공정 설비 일정(공정 Capa 상세 ③·④ 와 같은 키). 아니면
    None."""

    held_choices: tuple[HeldUnitChoice, ...]
    """`with_held_units` 를 준 회차의 보유 「호기 고르기」 선택지. 아니면 빈다."""


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


def first_ready_process(source: EquipmentPlanSource, options: Sequence[str]) -> str | None:
    """공정 칸이 비었을 때(사이드바로 처음 열기)의 기본 공정 — 설비 일정이 서는 첫 공정(선택지
    차례). 처음 화면이 까닭 카드가 아니라 계산이게(2026-10-25 E2E). 서는 공정이 없거나 설비 DB 를
    못 읽으면 첫 공정이다. 판정은 `equipment_readiness`(까닭 카드)와 같은 `dynamic_readiness` 이고
    설비 프레임은 한 번만 거른다 — 캐시된 스냅샷을 거를 뿐이라 DB 를 열지 않는다(칸이 빈 회차에만
    부른다)."""
    if not options:
        return None
    snapshot = source.snapshot
    if snapshot is not None and not source.equipment_error:
        equipment_frame = snapshot.calculation_frames()[1]
        for option in options:
            readiness = dynamic_readiness(
                equipment_frame, snapshot.baseline, source.cutoff, process=option
            )
            if readiness.ready:
                return str(option)
    return str(options[0])


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
    with_timeline: bool = False,
    with_held_units: bool = False,
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
        plan, target_level, timeline, held_choices = _load_plan(
            source,
            snapshot,
            process=process,
            cutoff_days=int(readiness.cutoff_days),
            with_timeline=with_timeline,
            with_held_units=with_held_units,
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
        timeline=timeline,
        held_choices=held_choices,
    )


def _load_plan(
    source: EquipmentPlanSource,
    snapshot: EquipmentSnapshot,
    *,
    process: str,
    cutoff_days: int,
    with_timeline: bool,
    with_held_units: bool,
) -> tuple[
    ShorteningPlan, MonthlyTarget, ProcessEquipmentTimeline | None, tuple[HeldUnitChoice, ...]
]:
    """공정 Capa 상세 ②·두 모드와 같은 계획 칸을 같은 키로(목표는 키 맞춤용 HOME 확보기준). 고르면
    같은 키의 설비 일정 칸과 보유 「호기 고르기」 선택지도 받는다. 예외는 그대로 올린다."""
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
    timeline_key = simulation_cache.process_timeline_key_from_shortening(shortening_key, process)
    timeline = (
        simulation_cache.get_process_equipment_timeline(
            timeline_key, equipment, downtime, baseline, source.cutoff
        )
        if with_timeline
        else None
    )
    held_choices = (
        simulation_cache.get_process_held_units(timeline_key, cutoff_days, equipment)
        if with_held_units
        else ()
    )
    return plan, target_level, timeline, held_choices


# ================================================================== 같은 글 조각


def source_scenario_text() -> str:
    """출처 띠의 소요 시나리오 — 이 세션 활성 리비전 이름표 「이름 rN」(이름은 막는다). 이름표가
    없으면(`active_scenario_label` 이 None) 「활성 시나리오」."""
    scenario_label = active_scenario_label()
    return (
        f"「{literal_markdown(scenario_label.scenario_name)} r{scenario_label.revision_no}」"
        if scenario_label is not None
        else "활성 시나리오"
    )


def source_equipment_text(equipment_text: str | None) -> str:
    """출처 띠 「가용 = 설비 일정 기준」 뒤 괄호 — 「(설비 기준 글, 단축 전)」(글은 막는다). 설비
    기준 글이 없거나 비면 「(단축 전)」."""
    return f"({literal_markdown(equipment_text)}, 단축 전)" if equipment_text else "(단축 전)"


def upeh_assumption_note() -> str:
    """세션 UPEH 가정 %(정수)가 기본값이 아니면 출처 띠 끝 단서(`UPEH_NOT_APPLIED_NOTE`), 아니면 빈
    글자 — 두 모드 모두 UPEH 가정을 걸지 않는다(공식 소요). 정수가 아닌 칸 값은 켬으로 보지
    않는다."""
    upeh_percent = st.session_state.get(
        UPEH_ASSUMPTION_PERCENT_KEY, UPEH_ASSUMPTION_DEFAULT_PERCENT
    )
    if isinstance(upeh_percent, int) and upeh_percent != UPEH_ASSUMPTION_DEFAULT_PERCENT:
        return UPEH_NOT_APPLIED_NOTE
    return ""
