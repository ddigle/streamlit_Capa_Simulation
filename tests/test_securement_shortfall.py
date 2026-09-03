# Purpose: securement shortfall 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from typing import cast

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import build_securement_shortfall_tables


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
