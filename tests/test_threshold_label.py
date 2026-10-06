# Purpose: 판정 기준 표시 글자가 사사오입한 정수 퍼센트이고 판정은 정확한 기준을 쓰는지 검증한다.

from __future__ import annotations

import pytest

from capa_simulation.components.home_figure_common import capacity_status
from capa_simulation.components.home_preference import status_legend_markup
from capa_simulation.services.securement_threshold import (
    SecurementThresholds,
    securement_threshold_caption,
)
from capa_simulation.services.threshold_label import (
    MISSING_THRESHOLD_LABEL,
    threshold_percent_label,
)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (1.095, "110%"),
        (0.995, "100%"),
        (1.094, "109%"),
        (1.2, "120%"),
        (1.1, "110%"),
        (1.0, "100%"),
        # 짝수 쪽으로 가르는 `round` 와 갈리는 값 — 반은 언제나 올린다.
        (1.085, "109%"),
        (1.005, "101%"),
        (0.985, "99%"),
        (0.0, "0%"),
    ],
)
def test_threshold_label_rounds_half_up_to_a_whole_percent(ratio: float, expected: str) -> None:
    assert threshold_percent_label(ratio) == expected


def test_threshold_label_survives_the_percent_round_trip_of_the_session_widgets() -> None:
    """세션 칸은 %(109.5)로, 저장은 비율(1.095)로 오간다. 그 왕복의 이진 잡음에 내려가지 않는다."""
    for tenth in range(0, 3001):
        percent = tenth / 10
        expected = int(percent + 0.5 + 1e-9)
        assert threshold_percent_label(percent / 100.0) == f"{expected}%"
        assert threshold_percent_label((percent / 100.0 * 100.0) / 100.0) == f"{expected}%"


@pytest.mark.parametrize("ratio", [float("nan"), float("inf")])
def test_a_threshold_that_is_not_a_number_does_not_stop_the_screen(ratio: float) -> None:
    assert threshold_percent_label(ratio) == MISSING_THRESHOLD_LABEL


def test_the_legend_names_three_states_without_numbers() -> None:
    """범례는 「초과 확보 · 경고 · 부족」 세 이름만 적는다(2026-10-06 사용자 결정).

    기준이 달마다 다를 수 있어 숫자 한 짝을 적으면 예외 달에서 거짓이 된다. 과거 구간 칩도 없다.
    """
    markup = status_legend_markup()

    for name in ("초과 확보", "경고", "부족"):
        assert name in markup
    assert "%" not in markup
    assert "과거 구간" not in markup


def test_judgement_stays_exact_while_labels_are_rounded() -> None:
    """화면 글자는 110%·100% 지만, 109.7% 는 확보·109.4% 는 경고로 판정한다(기준 109.5%)."""
    assert capacity_status(1.097, secure_threshold=1.095, warning_threshold=0.995) == "secure"
    assert capacity_status(1.094, secure_threshold=1.095, warning_threshold=0.995) == "warning"
    assert capacity_status(0.996, secure_threshold=1.095, warning_threshold=0.995) == "warning"
    assert capacity_status(0.994, secure_threshold=1.095, warning_threshold=0.995) == "shortage"


def test_a_monthly_exception_moves_only_its_month() -> None:
    """월별 예외는 그 달의 판정만 바꾼다. 빈 항목(경고)은 기본값을 따른다."""
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202607, 1.195, None),))

    assert thresholds.status(1.15, 202606) == "secure"
    assert thresholds.status(1.15, 202607) == "warning"
    assert thresholds.status(0.99, 202607) == "shortage"
    assert thresholds.status(1.15, None) == "secure"


def test_the_caption_names_the_default_and_counts_exceptions_in_the_period() -> None:
    """공정 선택 창 캡션: 기본 기준과 **기간 안에서 기본값과 다른 달** 수."""
    thresholds = SecurementThresholds(
        1.095,
        0.995,
        monthly=((202607, 1.195, None), (202608, 1.095, None), (202701, 1.195, None)),
    )

    assert (
        securement_threshold_caption(thresholds, start_month=202601, end_month=202612)
        == "확보 기준 110% · 월별 예외 1개월"
    )
    assert (
        securement_threshold_caption(SecurementThresholds(1.095, 0.995), start_month=1, end_month=2)
        == "확보 기준 110%"
    )
    assert (
        securement_threshold_caption(
            thresholds, start_month=202601, end_month=202712, with_warning=True
        )
        == "확보 기준 110% · 경고 기준 100% · 월별 예외 2개월"
    )
