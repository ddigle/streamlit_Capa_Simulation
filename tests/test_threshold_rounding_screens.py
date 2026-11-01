# Purpose: 정수 기준 규칙이 화면 글자(정수 기준·경계 식·여유 0·%)와 개조 일정 여유에 닿는지 본다.

from __future__ import annotations

from datetime import date

import pytest

from capa_simulation.components.constraint_simulation_figures import signed_points
from capa_simulation.components.modification_schedule_figures import relief_points
from capa_simulation.components.process_capa_canvas import _balance_hover
from capa_simulation.components.process_capa_view import (
    judgement_card,
    short_target_text,
    target_label,
    target_text,
)
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.scenario_preset_state import (
    DEFAULT_SECURE_THRESHOLD_PERCENT,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
)
from capa_simulation.services.modification_schedule import (
    ScheduleConditions,
    ScheduleMonthInput,
    plan_modification_schedule,
)
from capa_simulation.services.required_shortening import target_from_thresholds
from capa_simulation.services.securement_rate import CAUSE_COLUMN, OWNED_COLUMN
from capa_simulation.services.securement_threshold import SecurementThresholds, judgment_boundary

MONTH = 202611


def test_the_process_detail_target_is_a_plain_whole_percent() -> None:
    """공정 Capa 상세의 목표는 정수 「110%」 하나다 — 「110% (1.095)」 꼴을 걷었다(N1 정수만)."""
    target = target_from_thresholds(SecurementThresholds(1.095, 0.995), [MONTH])

    assert target_label(target.for_month(MONTH)) == "110%"
    assert target_text(target, [MONTH]) == "HOME Preference 확보기준(월별) 110%"
    assert short_target_text(target, [MONTH]) == "110%"
    assert "1.095" not in target_text(target, [MONTH])


def test_the_judgement_card_names_whole_thresholds_and_multiplies_the_boundary() -> None:
    """③ 판정 — 기준은 정수(「확보기준 110% · 경고기준 100%」), 과부족 식은 판정 경계 109.5% 를
    곱한다(그 대수가 확보로 판정되는 선이라 식이 결과와 검산된다)."""
    record: dict[str, object] = {
        "가용대수": 109.6,
        "소요대수": 100.0,
        "판정": "secure",
        "확보기준 과부족": 0,
        OWNED_COLUMN: 109.6,
        CAUSE_COLUMN: "",
    }
    card = judgement_card(record, SecurementThresholds(1.10, 1.00), MONTH)

    assert card.notes[0].startswith("확보기준 110% · 경고기준 100%")
    assert "(1.1)" not in card.notes[0] and "(1.095)" not in card.notes[0]
    assert "100.00×109.5% = +0.10 → 0" in card.formula
    assert "확보율 = 109.60 ÷ 100.00 = 109.6% → 확보" in card.formula


def test_the_canvas_balance_balloon_multiplies_the_boundary() -> None:
    text = _balance_hover("<b>26.11</b>", 0, 109.6, 100.0, 1.10, None)

    assert "확보기준 과부족 0대 (+0.10)" in text
    assert "소요 100.0 × 109.5%" in text


def test_differences_are_written_with_a_plain_percent_sign() -> None:
    """「%p」 를 쓰지 않는다(2026-11-01 사용자 결정 — 「%p표기하지말고 %로만」)."""
    assert signed_points(0.0) == "0.0%"
    assert signed_points(-0.005) == "−0.5%"
    assert relief_points(0.0171) == "1.71%"


def test_the_preset_defaults_are_whole_percents() -> None:
    assert (DEFAULT_SECURE_THRESHOLD_PERCENT, DEFAULT_WARNING_THRESHOLD_PERCENT) == (110, 100)
    preset = ScenarioPreset(202601, 202612, ("DEMO_P1",))
    assert (preset.secure_threshold, preset.warning_threshold) == (1.10, 1.00)


def _schedule(available: float) -> list[ScheduleMonthInput]:
    # G 는 화면이 넘기는 판정 경계(기준 110% → 1.095)다.
    boundary = judgment_boundary(1.10)
    return [
        ScheduleMonthInput(202701, 10.0, available, boundary),
        ScheduleMonthInput(202702, 10.0, 20.0, boundary),
    ]


def test_a_rounded_in_month_shows_a_zero_margin() -> None:
    """개조 뒤 109.7% 인 달은 110% 기준에 반올림으로 든 달이라 여유 0.0%(실제 −0.3%)다."""
    result = plan_modification_schedule(
        _schedule(11.97),
        ScheduleConditions(units=1, days=31, cutoff_days=0, earliest=date(2027, 1, 1)),
    )
    january = result.month(202701)

    assert january.downtime_unit_days == 31 and january.rate == pytest.approx(1.097)
    assert january.secure_after is True
    assert january.margin == 0.0
    assert result.tightest_month == 202701 and result.tightest_margin == 0.0
    assert signed_points(result.tightest_margin) == "0.0%"


def test_a_month_above_the_whole_threshold_keeps_its_real_margin() -> None:
    result = plan_modification_schedule(
        _schedule(13.0),
        ScheduleConditions(units=1, days=31, cutoff_days=0, earliest=date(2027, 1, 1)),
    )
    january = result.month(202701)

    assert january.rate == pytest.approx(1.2)
    assert january.margin == pytest.approx(0.1)


def test_the_schedule_plans_against_the_judgment_boundary() -> None:
    """HOME 의 옛 저장값 1.095 와 새 저장값 1.10 은 같은 G(판정 경계 1.095)를 내 계획이 같다 —
    개조 뒤 109.5% 까지 넣는다."""
    old = SecurementThresholds(1.095, 0.995).boundary_for(202701)[0]
    new = SecurementThresholds(1.10, 1.00).boundary_for(202701)[0]
    assert old == new == 1.095

    result = plan_modification_schedule(
        [ScheduleMonthInput(202701, 10.0, 12.0, new)],
        ScheduleConditions(units=1, days=31, cutoff_days=0, earliest=date(2027, 1, 1)),
    )
    assert result.complete
    assert result.month(202701).rate == pytest.approx(1.1)
    assert result.month(202701).margin == pytest.approx(0.0)
