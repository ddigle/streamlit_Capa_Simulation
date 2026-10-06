# Purpose: HOME 결론 요약의 집계가 필터와 구간 판정을 화면과 같게 지키는지 검사한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.securement_heatmap import _tier
from capa_simulation.services.home_decision import build_capacity_decision
from capa_simulation.services.securement_threshold import SecurementThresholds

SECURE = 1.095
WARNING = 0.995


def _rates(rows: list[tuple[int, str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "확보율"])


def _decision(frame: pd.DataFrame, included: list[str] | None = None):
    return build_capacity_decision(
        frame,
        included_processes=included,
        thresholds=SecurementThresholds(SECURE, WARNING),
    )


def test_the_worst_row_becomes_the_headline() -> None:
    """결론은 **가장 낮은** 공정·월 하나다. 최저가 여럿이면 그중 하나만 말한다."""
    decision = _decision(_rates([(202601, "가", 1.20), (202602, "나", 0.80), (202603, "다", 1.00)]))

    assert (decision.process, decision.month) == ("나", 202602)
    assert decision.rate == pytest.approx(0.80)
    assert decision.judged == 3


def test_the_process_filter_moves_the_headline() -> None:
    """공정을 걸러 놓았으면 **거른 뒤의** 최저값을 말해야 한다.

    거르기 전 값을 말하면 화면에 없는 공정을 가리킨다. 그림이 쓰는
    `build_monthly_bottleneck_ranking` 과 같은 자리에서 같은 필터를 받는 이유다.
    """
    frame = _rates([(202601, "가", 1.20), (202602, "나", 0.80), (202603, "다", 1.00)])

    assert _decision(frame, ["가", "다"]).process == "다"
    assert _decision(frame, ["가", "다"]).judged == 2
    # 거르기 전에는 「나」가 최저였다.
    assert _decision(frame).process == "나"


def test_the_tier_counts_match_the_heatmap_rule() -> None:
    """구간 판정은 히트맵과 **같은 부등호**여야 한다. 경계가 갈리면 두 화면이 다른 말을 한다."""
    boundary = _rates(
        [
            (202601, "초과", SECURE + 0.001),
            (202602, "경계_확보", SECURE),  # 이상이므로 확보다(2026-10-06 사용자 결정)
            (202603, "경계_경고", WARNING),  # 이상이므로 경고다
            (202604, "미만", WARNING - 0.001),
        ]
    )
    decision = _decision(boundary)

    assert (decision.warning, decision.shortage) == (1, 1)
    assert decision.below == 2
    # 같은 값을 히트맵 규칙에 넣어도 같은 수가 나온다.
    tiers = [
        _tier(rate, thresholds=SecurementThresholds(SECURE, WARNING), month=int(month))
        for rate, month in zip(boundary["확보율"], boundary["생산계획년월"], strict=True)
    ]
    assert tiers.count(1.0) == decision.warning
    assert tiers.count(0.0) == decision.shortage


def test_missing_values_are_not_judged() -> None:
    """빈 확보율은 **판정 가능한 수**에서 빠진다. 0 으로 세면 없는 부족이 생긴다."""
    decision = _decision(_rates([(202601, "가", None), (202602, "나", 1.20)]))

    assert decision.judged == 1
    assert decision.shortage == 0


def test_an_empty_frame_reports_no_data() -> None:
    """값이 없으면 0% 가 아니라 「판정할 데이터 없음」이다."""
    decision = _decision(_rates([]))

    assert not decision.has_data
    assert decision.process is None and decision.rate is None


def test_filtering_everything_out_reports_no_data() -> None:
    """필터로 공정을 모두 걸러 낸 것도 데이터 없음이다 — 오류가 아니다."""
    decision = _decision(_rates([(202601, "가", 0.5)]), ["없는공정"])

    assert not decision.has_data


def test_each_month_is_judged_by_its_own_threshold() -> None:
    """월별 예외가 있는 달은 **그 달의** 기준으로 센다. 같은 115% 라도 120% 기준 달에서는 경고다."""
    frame = _rates([(202601, "가", 1.15), (202607, "가", 1.15)])
    thresholds = SecurementThresholds(SECURE, WARNING, monthly=((202607, 1.195, None),))

    decision = build_capacity_decision(frame, included_processes=None, thresholds=thresholds)

    assert (decision.warning, decision.shortage) == (1, 0)
