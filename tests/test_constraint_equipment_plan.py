# Purpose: 제약 시뮬레이션 두 모드가 함께 쓰는 설비 일정 확인 · 계획 블록(`render_equipment_plan`)의
# 멈추는 갈래 차례와 까닭 글을 화면 없이 본다.

"""`components/constraint_equipment_plan` — 멈추는 갈래(순수 호출).

페이지 시험(`tests/test_constraint_simulation_page.py` ·
`tests/test_modification_schedule_page.py`)은 두 모드의 화면 갈래를 AppTest 로 본다. 여기서는 함수
하나가 두 모드에 같은 갈래 차례를 주는지 — 설비 DB 오류 · 설비 일정이 서지 않음(풀이 주어
`subject`) · 그 모드의 앞 갈래(`before_plan`) · 계획 계산 오류 — 를 머리 · 까닭 카드 그리기를 적는
가짜로 본다. 계획 받기가 불리면 실패하는 가짜 `simulation_cache` 함수로 「앞 갈래가 멈추면 계획을
받지 않는다」 를 잡는다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
import streamlit as st

# 공용 블록은 계획 함수를 부를 때 이 모듈에서 찾는다 — 모듈 속성을 바꿔 끼운다.
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.constraint_equipment_plan import (
    EquipmentPlanSource,
    equipment_readiness,
    render_equipment_plan,
)
from capa_simulation.page_bootstrap import ProcessPageInputs
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    NO_EQUIPMENT,
    READY,
    DynamicReadiness,
)

PROCESS = "DEMO_Chip_Attach"


class _Recorder:
    """머리 한 줄 · 까닭 카드 · 오류 글을 차례대로 적는다."""

    def __init__(self) -> None:
        self.headers: list[tuple[str, str]] = []
        self.cards: list[tuple[str, str, bool]] = []

    def header(self, process: str, line: str) -> None:
        self.headers.append((process, line))

    def card(self, title: str, detail: str, *, equipment_link: bool) -> None:
        self.cards.append((title, detail, equipment_link))


class _BrokenSnapshot:
    """계획 키를 만들려고 계산 칸을 꺼내면 깨지는 스냅샷."""

    def calculation_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        raise ValueError("시험 — 계산 칸을 꺼내지 못했습니다")


def _source(*, snapshot: object | None = None, equipment_error: str = "") -> EquipmentPlanSource:
    page_inputs = SimpleNamespace(
        months=(202601, 202602),
        context=SimpleNamespace(active_scenario={"tables": {}}, reference_tables={}),
        thresholds=None,
        capacity_cache_key="key",
    )
    return EquipmentPlanSource(
        page_inputs=cast(ProcessPageInputs, page_inputs),
        snapshot=cast(EquipmentSnapshot, snapshot),
        cutoff=pd.DataFrame(),
        equipment_error=equipment_error,
        today=date(2026, 1, 15),
        manual_downtime=ManualDowntime(),
    )


@pytest.fixture
def no_plan_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """계획 받기(`simulation_cache` 의 키 · 계획 함수)가 불리면 시험이 실패한다."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("멈춘 갈래가 계획을 받았다")

    for name in (
        "required_shortening_cache_key",
        "load_required_shortening_for_target",
        "get_process_equipment_timeline",
    ):
        monkeypatch.setattr(simulation_cache, name, refuse)


def _run(
    source: EquipmentPlanSource,
    readiness: DynamicReadiness | None,
    recorder: _Recorder,
    *,
    subject: str = "개조 일정",
    before_plan: Any = None,
) -> object:
    return render_equipment_plan(
        source,
        readiness,
        process=PROCESS,
        process_label=PROCESS,
        subject=subject,
        render_header=recorder.header,
        render_reason_card=recorder.card,
        before_plan=before_plan,
    )


def test_readiness_is_none_when_the_equipment_db_failed_or_no_process_is_chosen() -> None:
    assert equipment_readiness(_source(equipment_error="잠김"), PROCESS) is None
    assert equipment_readiness(_source(), None) is None


@pytest.mark.usefixtures("no_plan_loading")
def test_an_equipment_db_error_stops_with_its_own_reason_and_no_equipment_link() -> None:
    recorder = _Recorder()

    assert _run(_source(equipment_error="설비 DB 가 잠겼습니다."), None, recorder) is None

    ((process, line),) = recorder.headers
    assert process == PROCESS and line.endswith(":blue-badge[설비 일정 없음: 설비 DB 오류]")
    assert recorder.cards == [
        ("설비 일정 없음: 설비 DB 를 읽지 못했습니다", "설비 DB 가 잠겼습니다.", False)
    ]


@pytest.mark.usefixtures("no_plan_loading")
@pytest.mark.parametrize(
    ("subject", "phrase"),
    [
        (
            "제약 시뮬레이션",
            "제약 시뮬레이션은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 값)으로",
        ),
        ("개조 일정", "개조 일정은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 값)으로"),
    ],
)
def test_a_process_whose_schedule_cannot_stand_names_the_mode_and_skips_the_mode_branch(
    subject: str, phrase: str
) -> None:
    """설비 일정이 서지 않으면 그 모드의 앞 갈래(제약 영향의 제품 갈래)보다 먼저 멈춘다 — 까닭 카드
    풀이의 주어만 모드마다 다르다."""
    recorder = _Recorder()
    asked: list[bool] = []

    def before_plan() -> bool:
        asked.append(True)
        return True

    stopped = _run(
        _source(),
        DynamicReadiness(NO_EQUIPMENT, cutoff_days=7),
        recorder,
        subject=subject,
        before_plan=before_plan,
    )

    assert stopped is None and not asked
    ((title, detail, link),) = recorder.cards
    assert title == "설비 일정 없음: 설비 없음" and link
    assert phrase in detail


@pytest.mark.usefixtures("no_plan_loading")
def test_the_mode_branch_stops_after_the_check_and_before_the_plan() -> None:
    """판정을 지난 뒤 `before_plan` 이 거짓이면 계획을 받지 않고 멈춘다(까닭은 그 갈래가 그린다)."""
    recorder = _Recorder()

    stopped = _run(
        _source(snapshot=_BrokenSnapshot()),
        DynamicReadiness(READY, cutoff_days=7, has_units=True),
        recorder,
        subject="제약 시뮬레이션",
        before_plan=lambda: False,
    )

    assert stopped is None
    assert not recorder.headers and not recorder.cards


def test_a_failure_while_building_the_plan_key_is_the_plan_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """계획 키를 만드는 단계(계산 칸 꺼내기)에서 깨져도 「설비 일정을 계산하지 못했습니다」 갈래다 —
    두 모드가 같은 `try` 를 쓴다(제약 영향 모드는 합치기 전에는 키 만들기가 `try` 밖이었다)."""
    recorder = _Recorder()
    errors: list[str] = []
    monkeypatch.setattr(st, "error", errors.append)

    stopped = _run(
        _source(snapshot=_BrokenSnapshot()),
        DynamicReadiness(READY, cutoff_days=7, has_units=True),
        recorder,
        subject="제약 시뮬레이션",
        before_plan=lambda: True,
    )

    assert stopped is None
    ((_, line),) = recorder.headers
    assert line.endswith(":blue-badge[설비 일정 없음: 계산 오류]")
    (error,) = errors
    assert error.startswith("설비 일정을 계산하지 못했습니다 — ")
    assert "계산 칸을 꺼내지 못했습니다" in error
    assert not recorder.cards
