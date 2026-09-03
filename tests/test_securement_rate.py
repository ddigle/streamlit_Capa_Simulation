# Purpose: 공정별 확보율과 소요대수 0 처리를 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import (
    calculate_securement_rate,
    securement_rate_to_month_table,
)


def test_securement_rate_uses_process_required_sum_and_available_equipment() -> None:
    available = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "가용대수": [10.0, 12.0],
        }
    )
    required = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609],
            "공정": ["Pre B/D", "Pre B/D", "Pre B/D"],
            "소요대수": [3.0, 2.0, 4.0],
        }
    )

    result = calculate_securement_rate(available, required)
    table = securement_rate_to_month_table(result)

    assert result["소요대수"].tolist() == pytest.approx([5.0, 4.0])
    assert table.loc[0, "202608"] == pytest.approx(2.0)
    assert table.loc[0, "202609"] == pytest.approx(3.0)


def test_securement_rate_is_blank_when_required_equipment_is_zero() -> None:
    available = pd.DataFrame({"생산계획년월": [202608], "공정": ["Pre B/D"], "가용대수": [10.0]})
    required = pd.DataFrame({"생산계획년월": [202608], "공정": ["Pre B/D"], "소요대수": [0.0]})

    result = calculate_securement_rate(available, required)

    assert pd.isna(result.loc[0, "확보율"])
