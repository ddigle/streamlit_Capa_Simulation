# Purpose: 판정 기준을 정수 % 로 읽고 확보율을 사사오입해 판정하며 여유를 0 에서 자르는 규칙을 본다.

"""2026-11-01 사용자 결정(결정 보드 N1 메모) — 「기준확보율 입력을 110% 정수 기준으로 할테니,
분류하는 기준적용시엔 자동적으로 소수점 한자리수 반올림한 기준으로 포함시켜 (110% 기준확보율
설정시, 확보율 109.5%인 공정은 확보 판정) 이렇게 반올림해서 겨우 기준대로 확보된 공정의 경우엔
여유가 0으로 표기되어야함」."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    STATUS_COLUMN,
    build_securement_shortfall_tables,
    securement_balance,
    surplus_held_at_zero,
    warning_need_units,
)
from capa_simulation.services.securement_threshold import (
    DEFAULT_SECURE_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    SecurementThresholds,
    capacity_status,
    judgment_boundary,
    meets_threshold,
    normalize_threshold,
    rounded_in,
    threshold_margin,
)
from capa_simulation.services.threshold_label import (
    boundary_percent_label,
    threshold_percent,
    threshold_percent_label,
)


def _reference_meets(rate: float, threshold: float) -> bool:
    """규칙 그대로의 십진 판정 — 확보율 십진 표기를 사사오입한 정수 % 가 T 이상인가."""
    percent = (Decimal(repr(float(rate))) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(percent) >= threshold_percent(threshold)


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (1.0949, "warning"),
        (1.094999, "warning"),
        (1.095, "secure"),
        (1.0951, "secure"),
        (1.10, "secure"),
        (0.995, "warning"),
        (0.9949999, "shortage"),
    ],
)
def test_the_boundary_rounds_the_rate_half_up_against_a_whole_threshold(
    rate: float, expected: str
) -> None:
    """T = 110 이면 109.5% 는 확보, 109.4999% 는 경고다(경고 100 이면 99.5% 는 경고)."""
    assert capacity_status(rate, secure_threshold=1.10, warning_threshold=1.00) == expected


def test_stored_half_step_and_whole_thresholds_judge_the_same() -> None:
    """옛 저장값 1.095·0.995 와 새 저장값 1.10·1.00 은 모든 확보율에서 같은 판정이다."""
    rates = [step / 10_000 for step in range(9_800, 11_200)]
    neighbours = [
        math.nextafter(value, direction)
        for value in (1.095, 0.995, 1.0949999999999998)
        for direction in (0.0, 2.0)
    ]
    for rate in [*rates, *neighbours, 1.095, 0.995]:
        old = capacity_status(rate, secure_threshold=1.095, warning_threshold=0.995)
        new = capacity_status(rate, secure_threshold=1.10, warning_threshold=1.00)
        assert old == new, rate
        assert SecurementThresholds(1.095, 0.995).status(rate, 202607) == new


def test_the_float_boundary_matches_the_decimal_rule() -> None:
    """경계 비율과의 부동소수 비교가 십진 사사오입 판정과 같다 — 경계 바로 위·아래 부동소수까지."""
    for percent in (50, 99, 100, 105, 109, 110, 115, 119, 120, 121, 130, 200):
        threshold = percent / 100
        boundary = judgment_boundary(threshold)
        assert boundary == float(Decimal(percent) - Decimal("0.5")) / 100
        probes = [boundary, math.nextafter(boundary, 0.0), math.nextafter(boundary, 9.0)]
        probes += [boundary + step * 1e-6 for step in range(-5, 6)]
        for rate in probes:
            assert meets_threshold(rate, threshold) == _reference_meets(rate, threshold), rate


def test_the_known_float_noise_case_stays_below_the_boundary() -> None:
    """소요 10.000000000000002 · 가용 10.95 의 확보율 1.0949999999999998 은 1.095 밑이다 — 옛 판정
    그대로(`1.095 × 100` 같은 부동소수 곱을 반올림하지 않는다)."""
    rate = 10.95 / 10.000000000000002
    assert rate < 1.095
    assert not meets_threshold(rate, 1.10)
    assert meets_threshold(10.95 / 10, 1.10)
    assert threshold_percent(1.095) == 110
    assert threshold_percent(0.995) == 100


def test_a_monthly_120_includes_119_5() -> None:
    thresholds = SecurementThresholds(1.10, 1.00, monthly=((202607, 1.20, None),))

    assert thresholds.status(1.195, 202607) == "secure"
    assert thresholds.status(1.1949, 202607) == "warning"
    assert thresholds.status(1.15, 202606) == "secure"
    assert thresholds.boundary_for(202607) == (judgment_boundary(1.2), judgment_boundary(1.0))


@pytest.mark.parametrize(
    ("stored", "whole"),
    [(1.095, 1.1), (0.995, 1.0), (1.20, 1.2), (1.195, 1.2), (1.094, 1.09), (1.1, 1.1)],
)
def test_stored_ratios_read_as_the_half_up_whole_percent(stored: float, whole: float) -> None:
    assert normalize_threshold(stored) == whole
    thresholds = SecurementThresholds(stored, 0.995, monthly=((202607, stored, None),))
    assert thresholds.default_secure == whole
    assert thresholds.for_month(202607) == (whole, 1.0)
    assert threshold_percent_label(thresholds.default_secure) == threshold_percent_label(stored)


def test_the_code_defaults_are_the_whole_business_thresholds() -> None:
    assert (DEFAULT_SECURE_THRESHOLD, DEFAULT_WARNING_THRESHOLD) == (1.10, 1.00)
    assert threshold_percent_label(DEFAULT_SECURE_THRESHOLD) == "110%"
    assert boundary_percent_label(DEFAULT_SECURE_THRESHOLD) == "109.5%"
    assert boundary_percent_label(DEFAULT_WARNING_THRESHOLD) == "99.5%"


@pytest.mark.parametrize(
    ("rate", "threshold", "expected"),
    [
        (1.095, 1.10, 0.0),  # 반올림으로 겨우 든 공정 — 실제 −0.5% 지만 0
        (1.097, 1.10, 0.0),
        (1.10, 1.10, 0.0),
        (1.12, 1.10, 0.02),
        (1.094, 1.10, -0.006),  # 판정이 확보가 아니면 실제 음수 그대로
        (1.195, 1.20, 0.0),
        (1.12, 1.095, 0.02),  # 옛 저장값도 정수 기준 110% 대비
    ],
)
def test_the_margin_is_clamped_to_zero_only_for_rounded_in_rates(
    rate: float, threshold: float, expected: float
) -> None:
    assert threshold_margin(rate, threshold) == pytest.approx(expected, abs=1e-12)


def _rate_rows(available: float, required: float, month: int = 202607) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [month],
            "공정": ["DEMO_P1"],
            "총보유대수": [available],
            "가용대수": [available],
            "소요대수": [required],
            "확보율": [available / required],
        }
    )


@pytest.mark.parametrize("stored", [(1.095, 0.995), (1.10, 1.00)])
def test_need_counts_and_balances_aim_at_the_judgment_boundary(
    stored: tuple[float, float],
) -> None:
    """필요대수·과부족은 판정 경계(1.095)까지다 — 옛 1.095 저장본과 새 1.10 저장본이 같은 수다."""
    thresholds = SecurementThresholds(*stored)

    # 108.6% — 1대 더하면 109.6% 로 확보다(110% 까지 2대가 아니라).
    warning, secure = build_securement_shortfall_tables(
        _rate_rows(108.6, 100.0), thresholds=thresholds
    )
    assert warning.empty
    assert secure["확보목표 총 필요대수"].tolist() == [1]
    assert secure["확보기준"].tolist() == [1.1]

    # 109.6% — 반올림으로 확보, 남는 대수는 0(빼면 경계 밑).
    balance = securement_balance(_rate_rows(109.6, 100.0), thresholds=thresholds)
    assert balance[STATUS_COLUMN].tolist() == ["secure"]
    assert balance[BALANCE_COLUMN].tolist() == [0]
    # 99.5% 는 경고(경고 100% 반올림), 99.4% 는 부족이고 경고까지 1대.
    assert securement_balance(_rate_rows(99.5, 100.0), thresholds=thresholds)[
        STATUS_COLUMN
    ].tolist() == ["warning"]
    short = securement_balance(_rate_rows(99.4, 100.0), thresholds=thresholds)
    assert short[STATUS_COLUMN].tolist() == ["shortage"]
    assert warning_need_units(100.0, 99.4, thresholds.warning_for(202607)) == 1


@pytest.mark.parametrize("stored", [(1.095, 0.995), (1.10, 1.00)])
def test_a_rounded_in_month_keeps_zero_surplus_even_with_a_large_demand(
    stored: tuple[float, float],
) -> None:
    """소요 400 · 가용 439.9 는 109.975% → 반올림 110% 로 확보다. 경계식
    (439.9 − 400 × 1.095 = +1.9)을 내리면 1대지만 확보율이 110% 밑이라 여유가 아니다 — 남는
    대수도 0 이다(「여유가 0으로」)."""
    thresholds = SecurementThresholds(*stored)

    held = securement_balance(_rate_rows(439.9, 400.0), thresholds=thresholds)
    assert held[STATUS_COLUMN].tolist() == ["secure"]
    assert held[BALANCE_COLUMN].tolist() == [0]
    assert surplus_held_at_zero(439.9, 400.0, thresholds.secure_for(202607))
    assert rounded_in(439.9 / 400.0, thresholds.secure_for(202607))

    # 110% 이상이면 경계식 그대로다 — 444 − 438 = 6.
    above = securement_balance(_rate_rows(444.0, 400.0), thresholds=thresholds)
    assert above[BALANCE_COLUMN].tolist() == [6]
    assert not surplus_held_at_zero(444.0, 400.0, thresholds.secure_for(202607))
    # 작은 공정의 반올림으로 든 달은 원래도 0 이라 묶음 표지가 서지 않는다.
    assert not surplus_held_at_zero(109.6, 100.0, thresholds.secure_for(202607))
