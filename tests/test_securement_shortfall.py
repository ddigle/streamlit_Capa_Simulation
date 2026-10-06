# Purpose: securement shortfall 관련 정상·예외·회귀 동작을 검증한다.

from typing import cast

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import build_securement_shortfall_tables
from capa_simulation.services.securement_threshold import SecurementThresholds


def test_a_process_exactly_on_the_threshold_needs_no_equipment() -> None:
    """`50 × 1.1 = 55.00000000000001` — 부동소수 먼지가 설비 1대를 만들어 냈다.

    가용 55·소요 50·경고 1.1 이면 확보율이 정확히 1.1 이라 경고 기준을 이미 채웠다.
    그런데 `소요 × 기준 − 가용` 이 0 이 아니라 1.4e-14 로 남아 올림이 1대를 요구했다.
    확보 구획으로 가는 공정에서는 그 가짜 1대가 화면에 안 보인 채 `확보기준 추가대수` 만
    1대 깎아 먹으므로, 조용한 오답과 눈에 띄는 과대 요구가 한 결함에서 같이 나온다.
    """
    securement = pd.DataFrame(
        {
            "생산계획년월": [202607],
            "공정": ["OnThreshold"],
            "가용대수": [55.0],
            "소요대수": [50.0],
            "확보율": [1.1],
        }
    )

    warning_rows, secure_rows = build_securement_shortfall_tables(
        securement,
        thresholds=SecurementThresholds(1.2, 1.1),
    )

    assert warning_rows.empty
    assert secure_rows["경고기준 필요대수"].tolist() == [0]
    assert secure_rows["확보목표 총 필요대수"].tolist() == [5]
    assert secure_rows["확보기준 추가대수"].tolist() == [5]


def test_shortfall_steps_partition_minimum_equipment_to_secure_threshold() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202607, 202607, 202607],
            "공정": ["Urgent", "Watch", "Secure"],
            "가용대수": [8.0, 10.0, 12.0],
            "소요대수": [10.2, 10.2, 10.0],
            "확보율": [8.0 / 10.2, 10.0 / 10.2, 1.2],
        }
    )

    warning_rows, secure_rows = build_securement_shortfall_tables(
        securement,
        thresholds=SecurementThresholds(1.1, 0.9),
    )

    assert warning_rows["공정"].tolist() == ["Urgent"]
    assert warning_rows.loc[0, "경고기준 필요대수"] == 2
    assert warning_rows.loc[0, "확보기준 추가대수"] == 2
    assert warning_rows.loc[0, "확보목표 총 필요대수"] == 4
    warning_needed = cast(int, warning_rows.loc[0, "경고기준 필요대수"])
    secure_increment = cast(int, warning_rows.loc[0, "확보기준 추가대수"])
    secure_total = cast(int, warning_rows.loc[0, "확보목표 총 필요대수"])
    assert warning_needed + secure_increment == secure_total

    assert secure_rows["공정"].tolist() == ["Watch"]
    assert secure_rows.loc[0, "경고기준 필요대수"] == 0
    assert secure_rows.loc[0, "확보기준 추가대수"] == 2
    assert secure_rows.loc[0, "확보목표 총 필요대수"] == 2


def test_shortfall_excludes_zero_demand_and_recalculates_rate_from_counts() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608],
            "공정": ["No demand", "Recalculated"],
            "가용대수": [5.0, 9.0],
            "소요대수": [0.0, 10.0],
            "확보율": [float("nan"), 9.9],
        }
    )

    warning_rows, secure_rows = build_securement_shortfall_tables(
        securement,
        thresholds=SecurementThresholds(1.05, 0.95),
    )

    assert warning_rows["공정"].tolist() == ["Recalculated"]
    assert warning_rows.loc[0, "확보율"] == pytest.approx(0.9)
    assert secure_rows.empty


@pytest.mark.parametrize(
    ("warning_threshold", "secure_threshold"),
    [(-0.1, 1.1), (1.2, 1.1)],
)
def test_shortfall_rejects_invalid_thresholds(
    warning_threshold: float,
    secure_threshold: float,
) -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202607],
            "공정": ["Process"],
            "가용대수": [1.0],
            "소요대수": [1.0],
            "확보율": [1.0],
        }
    )

    with pytest.raises(ValueError):
        build_securement_shortfall_tables(
            securement,
            thresholds=SecurementThresholds(secure_threshold, warning_threshold),
        )


def test_each_row_uses_its_months_threshold() -> None:
    """기준은 행의 달마다다. 확보 기준만 올린 달은 같은 대수라도 확보 기준 미달 구획에 든다."""
    securement = pd.DataFrame(
        {
            "생산계획년월": [202601, 202607],
            "공정": ["Process", "Process"],
            "가용대수": [11.5, 11.5],
            "소요대수": [10.0, 10.0],
            "확보율": [1.15, 1.15],
        }
    )
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202607, 1.195, None),))

    warning_rows, secure_rows = build_securement_shortfall_tables(securement, thresholds=thresholds)

    assert warning_rows.empty
    assert secure_rows["생산계획년월"].tolist() == [202607]
    assert secure_rows["확보기준"].tolist() == [1.195]
    assert secure_rows["경고기준"].tolist() == [0.995]
    assert secure_rows["확보기준 추가대수"].tolist() == [1]


def test_a_reversed_monthly_pair_is_rejected() -> None:
    """저장 단계가 막는 거꾸로 된 짝이 직접 호출로 들어와도 계산하지 않는다."""
    securement = pd.DataFrame(
        {
            "생산계획년월": [202607],
            "공정": ["Process"],
            "가용대수": [1.0],
            "소요대수": [1.0],
            "확보율": [1.0],
        }
    )
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202607, 0.9, None),))

    with pytest.raises(ValueError):
        build_securement_shortfall_tables(securement, thresholds=thresholds)
