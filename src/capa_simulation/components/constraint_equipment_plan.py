# Purpose: 제약 시뮬레이션 두 모드(제약 영향 · 개조 일정)가 함께 쓰는 설비 일정 확인(판정 · 멈춘
# 자리) · 계획 칸 받기와 조건 카드 · 머리 줄 표지의 같은 글 조각을 한 곳에 둔다.

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
  머리 한 줄과 멈춘 자리를 그리고 None 을 돌려준다 — `st.stop` 은 부르는 쪽이 쥔다.
- **멈춘 자리**(공정 Capa 상세도 같은 꼴 — `absent_note`) — 가용설비 현황에서 채울 입력(저장본 ·
  이름 · Cut-off)이 빠진 자리는 데이터 Error 마크다. 까닭은 알림 전문, 고치는 화면은 Alarm 줄의
  「그 화면으로」 다(설계 규칙 UI-NTF-08 — 자리에 링크를 두지 않는다). 호기가 있어도 사용기준
  HBM·EDP 가 없고 기존보유도 없는 공정(`NO_COUNTED_UNITS`)은 채울 입력이 없는 빈 상태라 회색 평문
  한 줄이다(UI-TXT-04 — 마크로 세우면 그 공정을 고를 때마다 Alarm 에 오류가 쌓인다). 그 줄이 까닭을
  적으므로 머리 배지는 「설비 일정 없음」 까지다(UI-TXT-07). 저장본 없음은 공정마다 다른 일이 아니라
  설비 DB 전체의 일이라 알림 글에 공정을 넣지 않는다 — 공정을 넘겨도 같은 알림 하나다(UI-NTF-07).
- **계획** — 공정 Capa 상세 ② 와 같은 칸을 **같은 키**로(`load_required_shortening_for_target`,
  목표는 키 맞춤용 HOME 확보 기준 — 단축 열은 읽지 않는다). 계산 함수는 부를 때 `simulation_cache`
  모듈에서 찾는다(페이지 시험이 그 속성을 바꾼다). 제약 영향 모드는 같은 `try` 안에서 두 가지를 더
  받는다 — 「신규 설비는 개조 없이」 를 켠 회차에는 같은 키의 설비 일정 칸(공정 Capa 상세 ③·④ —
  `with_timeline`), 매 회차(개조 켬 · 끔과 무관 — 끄면 칸이 잠긴 채 고름을 보인다) 보유 「호기
  고르기」 선택지(`with_held_units` — 같은 마스터 지문의 가벼운 캐시, 2026-11-01 사용자 결정 B3).
  그 계산이 터져도 「설비 일정을 계산하지 못했습니다」 갈래다. 기준일 거르기 · 고른 호기 빼기는
  페이지가 고른 뒤에 한다(호기 고르기는 이 블록 뒤에 서므로).
- **같은 글 조각** — 두 모드가 글자까지 같게 적는 조건 카드 「이 세션만」 머리
  (`SESSION_ONLY_CAPTION`)와 머리 줄의 표지(`applied_marks` — 계획이 건 입력 비가동 · UPEH 가정을 켠
  세션의 「미적용」, 뜻은 풍선). 머리 줄을 그리는 함수의 꼴은 `HeaderRenderer` 다. 소요 · 가용의
  출처를 적던 띠는 걷었다 — 출처와 읽는 법은 Guide 다(2026-11-08 사용자 그림 메모 g12).

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
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.constraint_simulation_state import CONSTRAINT_ABSENT_KEY
from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    ProcessPageInputs,
    bootstrap_error_message,
)
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    NO_COUNTED_UNITS,
    NO_SNAPSHOT,
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
    "CUTOFF_SOURCE_HELP",
    "EQUIPMENT_SCREEN",
    "SESSION_ONLY_CAPTION",
    "SESSION_ONLY_HELP",
    "UPEH_NOT_APPLIED_HELP",
    "UPEH_NOT_APPLIED_MARK",
    "EquipmentPlan",
    "AbsentNote",
    "EquipmentPlanSource",
    "HeaderRenderer",
    "absent_note",
    "applied_marks",
    "equipment_readiness",
    "first_ready_process",
    "render_equipment_plan",
]

SESSION_ONLY_CAPTION: Final = ":material/person: **이 세션만** — 저장하지 않습니다"
"""조건 카드 「이 세션만」 묶음의 머리 캡션(표지)."""

SESSION_ONLY_HELP: Final = (
    "저장하지 않는 시뮬레이션입니다 — 조건은 이 세션에만 남고 다른 사람에게 보이지 않습니다. 공식 "
    "확보율·HOME·필요 단축 일정은 그대로입니다."
)
"""「이 세션만」 표지의 풍선 — 보관 범위 설명은 자리에 늘 두지 않는다(설계 규칙 UI-TXT-01)."""

CUTOFF_SOURCE_HELP: Final = (
    "가용설비 현황 사이드바 「가용설비 설정」 팝업의 공정별 값입니다(모든 설비 시나리오 공용)."
)
"""조건 카드 Cut-off 값 줄의 풍선 — 값이 어디서 오는지(고치는 곳)는 자리에 적지
않는다(UI-TXT-03)."""

_NO_SCHEDULE_BADGE: Final = "설비 일정 없음"
"""빈 상태의 머리 배지 — 까닭은 바로 아래 평문 한 줄이 적는다(설계 규칙 UI-TXT-07)."""

UPEH_NOT_APPLIED_MARK: Final = "UPEH 가정 미적용"
"""UPEH 가정을 켠 세션의 머리 줄 표지(`applied_marks`)."""

UPEH_NOT_APPLIED_HELP: Final = (
    "공정 Capa 상세 · 필요 단축 일정의 UPEH 가정은 이 화면에 걸리지 않습니다(공식 소요)."
)
"""「UPEH 가정 미적용」 표지의 풍선."""

MANUAL_DOWNTIME_HELP: Final = (
    "가용설비 현황 › Preference 의 공정 × 달 비가동 대수를 가용에서 뺐습니다(공정 Capa 상세 ② 와 "
    "같은 가용)."
)
"""「입력 비가동 반영(…)」 표지의 풍선."""

EQUIPMENT_SCREEN: Final = (tab_label(AVAILABLE_EQUIPMENT_STATUS), AVAILABLE_EQUIPMENT_STATUS.href)
"""채울 입력이 있는 화면(이름, 주소) — 멈춘 자리 알림 줄의 「그 화면으로」 가 연다."""


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
    """키 맞춤용 HOME 확보 기준 — `plan.at(target_level)` 로 공정 달을 꺼낸다."""

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
    차례). 처음 화면이 멈춘 자리가 아니라 계산이게(2026-10-25 E2E). 서는 공정이 없거나 설비 DB 를
    못 읽으면 첫 공정이다. 판정은 `equipment_readiness`(멈춘 자리)와 같은 `dynamic_readiness` 이고
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
    before_plan: Callable[[], bool] | None = None,
    with_timeline: bool = False,
    with_held_units: bool = False,
) -> EquipmentPlan | None:
    """설비 일정 확인 → (`before_plan`) → 계획. 멈추는 갈래면 머리 한 줄과 멈춘 자리를 그리고 None.

    `subject` 는 멈춘 자리 풀이의 주어이자 알림 전문 첫머리(「제약 시뮬레이션」 · 「개조 일정」)다.
    `before_plan` 은 판정을 지난 뒤 계획 앞에 볼 그 모드의 갈래다 — 까닭을 그리고 거짓을 돌려주면
    멈춘다(계획을 받지 않는다).
    """
    bold = f"**{literal_markdown(process_label)}**"
    if readiness is None:
        render_header(process, f"{bold} :blue-badge[설비 일정 없음: 설비 DB 오류]")
        with st.container(key=CONSTRAINT_ABSENT_KEY):
            render_data_error(
                source.equipment_error or "설비 DB 를 열지 못했습니다.",
                code="CS-01",
                text="설비 일정 없음: 설비 DB 를 읽지 못했습니다",
            )
        return None
    snapshot = source.snapshot
    if not readiness.ready or readiness.cutoff_days is None or snapshot is None:
        empty = readiness.status == NO_COUNTED_UNITS
        badge = _NO_SCHEDULE_BADGE if empty else readiness.badge
        render_header(process, f"{bold} :blue-badge[{badge}]")
        rule = (
            f"{subject}{topic_particle(subject)} 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 "
            "값)으로 계산하므로"
        )
        with st.container(key=CONSTRAINT_ABSENT_KEY):
            if empty:
                st.caption(
                    readiness.detail,
                    help=f"{rule} 사용기준 HBM·EDP 호기나 기존보유가 있는 공정에만 섭니다.",
                )
            else:
                _render_absent(
                    readiness.badge,
                    f"{readiness.detail} {rule} 설비 DB 에 저장본이 있고 이름이 같으며 Cut-off 가 "
                    "적힌 공정에만 섭니다.",
                    screen=subject,
                    process_label=None if readiness.status == NO_SNAPSHOT else process_label,
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
        render_data_error(
            "설비 일정을 계산하지 못했습니다 — "
            + bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)),
            code="CS-01",
            text="설비 일정을 계산하지 못했습니다",
        )
        return None
    if process not in plan.processes:
        # 판정을 지나도 계획은 「가용 공정 ∩ 소요 공정」 만 맞댄다 — KeyError 로 떨어뜨리지 않는다.
        missing_cutoff = process in plan.missing_cutoff
        badge = (
            "설비 일정 없음: Cut-off 미기재"
            if missing_cutoff
            else "설비 일정 없음: 계획에 공정 없음"
        )
        render_header(process, f"{bold} :blue-badge[{badge}]")
        with st.container(key=CONSTRAINT_ABSENT_KEY):
            _render_absent(
                badge,
                (
                    "가용설비 현황의 공정별 Cut-off 에 이 공정이 없습니다."
                    if missing_cutoff
                    else "설비 일정 기준 가용에 이 공정이 없습니다. 설비 마스터 "
                    "공정소분류·기존보유 공정 이름이 시나리오 공정과 완전히 같아야 맞댑니다."
                ),
                screen=subject,
                process_label=process_label,
            )
        return None
    return EquipmentPlan(
        plan=plan,
        target_level=target_level,
        cutoff_days=int(readiness.cutoff_days),
        timeline=timeline,
        held_choices=held_choices,
    )


class AbsentNote(NamedTuple):
    """채울 입력이 빠져 멈춘 자리의 알림 글 — `message` 전문, `text` 알림창 짧은 글."""

    message: str
    text: str


def absent_note(badge: str, reason: str, *, screen: str, process_label: str | None) -> AbsentNote:
    """멈춘 자리 알림 글 — 줄의 화면 칸은 고칠 화면이라 전문 첫머리가 어느 화면 · 공정의 일인지
    적는다(설계 규칙 UI-NTF-02). 마크는 `EQUIPMENT_SCREEN` 을 `goto` 로 받아 그 화면의 코드로
    그린다.

    `process_label` 이 None 이면 공정의 일이 아니라 설비 DB 전체의 일이다(저장본 없음). 글에 공정을
    넣지 않아야 공정을 넘겨도 알림 id 와 묶음 열쇠(코드 + 짧은 글)가 같다(UI-NTF-07)."""
    if process_label is None:
        return AbsentNote(f"{screen} — {reason}", badge)
    return AbsentNote(
        f"{screen} · {literal_markdown(process_label)} — {reason}",
        f"{process_label} — {badge}",
    )


def _render_absent(badge: str, reason: str, *, screen: str, process_label: str | None) -> None:
    """두 모드의 멈춘 자리 — 데이터 Error 마크 한 칸(`CS-01`)."""
    note = absent_note(badge, reason, screen=screen, process_label=process_label)
    render_data_error(note.message, code="CS-01", text=note.text, goto=EQUIPMENT_SCREEN)


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
    """공정 Capa 상세 ②·두 모드와 같은 계획 칸을 같은 키로(목표는 키 맞춤용 HOME 확보 기준). 고르면
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


class HeaderRenderer(Protocol):
    """머리 줄을 그리는 함수(페이지의 `render_header`) — 왼쪽은 멈춘 갈래의 공정 · 배지(`line`)나
    계산이 건 표지(`marks` · 풍선 `marks_help`), 오른쪽 끝은 「← 공정 Capa 상세」."""

    def __call__(
        self, process: str, line: str = "", *, marks: str = "", marks_help: str = ""
    ) -> None: ...


def _upeh_assumption_on() -> bool:
    """세션 UPEH 가정 %(정수)가 기본값이 아닌가. 정수가 아닌 칸 값은 켬으로 보지 않는다."""
    upeh_percent = st.session_state.get(
        UPEH_ASSUMPTION_PERCENT_KEY, UPEH_ASSUMPTION_DEFAULT_PERCENT
    )
    return isinstance(upeh_percent, int) and upeh_percent != UPEH_ASSUMPTION_DEFAULT_PERCENT


def applied_marks(manual_note: str) -> tuple[str, str]:
    """머리 줄 표지와 그 풍선 — 계획이 건 입력 비가동(`manual_effect_band` 글, 없으면 빈 글자)과
    UPEH 가정을 켠 세션의 「UPEH 가정 미적용」(두 모드 모두 UPEH 가정을 걸지 않는다 — 공식 소요).
    둘 다 없으면 ("", "")."""
    marks: list[str] = []
    helps: list[str] = []
    if manual_note:
        marks.append(manual_note)
        helps.append(MANUAL_DOWNTIME_HELP)
    if _upeh_assumption_on():
        marks.append(UPEH_NOT_APPLIED_MARK)
        helps.append(UPEH_NOT_APPLIED_HELP)
    return " · ".join(marks), " ".join(helps)
