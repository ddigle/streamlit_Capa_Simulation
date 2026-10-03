# Purpose: 판정 기준 표시 글자가 사사오입한 정수 퍼센트이고 판정은 정확한 기준을 쓰는지 검증한다.

from __future__ import annotations

import pytest

from capa_simulation.components.home_figure_common import capacity_status
from capa_simulation.components.home_preference import status_legend_markup
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


def test_the_legend_shows_rounded_boundaries_while_judgement_stays_exact() -> None:
    """범례는 110%·100% 로 적지만, 109.7% 는 확보·109.4% 는 경고로 판정한다(기준 109.5%)."""
    markup = status_legend_markup(secure_threshold=1.095, warning_threshold=0.995)

    assert "확보 110% 초과" in markup
    assert "경고 100%~110%" in markup
    assert "부족 100% 미만" in markup
    assert "109" not in markup and "99%" not in markup
    assert capacity_status(1.097, secure_threshold=1.095, warning_threshold=0.995) == "secure"
    assert capacity_status(1.094, secure_threshold=1.095, warning_threshold=0.995) == "warning"
    assert capacity_status(0.996, secure_threshold=1.095, warning_threshold=0.995) == "warning"
    assert capacity_status(0.994, secure_threshold=1.095, warning_threshold=0.995) == "shortage"
