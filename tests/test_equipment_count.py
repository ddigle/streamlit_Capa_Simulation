# Purpose: 보유·대여·가용 설비대수 조회 표를 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.equipment_count import build_equipment_count_table


def test_equipment_count_supports_available_summary_and_detailed_rows() -> None:
    own = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "설비보유": [10.0, 11.0],
        }
    )
    lent = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "설비대여평가": [2.0, 3.0],
        }
    )
    available = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "가용대수": [12.0, 14.0],
        }
    )

    summary = build_equipment_count_table(own, lent, available, detailed=False)
    detailed = build_equipment_count_table(own, lent, available, detailed=True)

    assert list(summary.columns) == ["공정", "202608", "202609"]
    assert summary.loc[0, "202608"] == pytest.approx(12.0)
    assert detailed["구분"].tolist() == ["보유", "대여", "가용"]
    assert detailed["202609"].tolist() == pytest.approx([11.0, 3.0, 14.0])
