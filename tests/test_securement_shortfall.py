# Purpose: securement shortfall 관련 정상·예외·회귀 동작을 검증한다.

from typing import cast

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import build_securement_shortfall_tables


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
        warning_threshold=1.1,
        secure_threshold=1.2,
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
        warning_threshold=0.9,
        secure_threshold=1.1,
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
        warning_threshold=0.95,
        secure_threshold=1.05,
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
            warning_threshold=warning_threshold,
            secure_threshold=secure_threshold,
        )
