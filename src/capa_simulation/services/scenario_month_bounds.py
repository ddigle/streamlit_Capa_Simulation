# Purpose: 기본 조회기간을 활성 기준정보에 실제로 존재하는 월까지 넓혀 선택기 범위를 정한다.

from collections.abc import Mapping

import pandas as pd

from capa_simulation.services.month_filter import MONTH_COLUMN, valid_month_mask


def scenario_month_bounds(
    tables: Mapping[str, pd.DataFrame], default_start: int, default_end: int
) -> tuple[int, int]:
    """기본 범위와 실제 월의 합집합만 구한다. 값의 연도 오류를 추정하거나 고치지 않는다."""
    start, end = default_start, default_end
    for frame in tables.values():
        if MONTH_COLUMN not in frame.columns or frame.empty:
            continue
        numeric = pd.to_numeric(frame[MONTH_COLUMN], errors="coerce")
        months = numeric.loc[valid_month_mask(numeric)]
        if not months.empty:
            start = min(start, int(months.min()))
            end = max(end, int(months.max()))
    return start, end
