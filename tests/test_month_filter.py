# Purpose: 조회기간과 원천 데이터의 교집합 산출을 검증한다.

import pandas as pd

from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
)


def test_month_range_uses_only_the_intersection_with_source_data() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608, 202701, 202712],
            "생산수량": [10.0, 20.0, 30.0, 40.0],
        }
    )

    assert available_month_range(plan, "RQ_PKG_PLAN") == (202607, 202712)
    narrow = filter_month_range(plan, 202607, 202612, "RQ_PKG_PLAN")
    wide = filter_month_range(plan, 202605, 202812, "RQ_PKG_PLAN")

    assert narrow["생산계획년월"].tolist() == [202607, 202608]
    assert wide["생산계획년월"].tolist() == [202607, 202608, 202701, 202712]
