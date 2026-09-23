# Purpose: 시나리오의 월별 12표를 지정한 연수만큼 이동하고 나머지 값과 원본을 보존한다.

"""저장된 월을 사용자 지정 연수만큼 이동한 독립 시나리오 표 묶음을 만든다."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column
from capa_simulation.services.month_filter import MONTH_COLUMN
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, copy_scenario_tables


def shift_scenario_years(tables: Mapping[str, pd.DataFrame], years: int) -> dict[str, pd.DataFrame]:
    """월 숫자는 유지하면서 연도만 이동한다. 원본과 월 없는 네 표는 바꾸지 않는다."""
    if isinstance(years, bool) or not isinstance(years, int):
        raise ValueError("연도 이동량은 정수로 입력하세요. 개월 단위 이동은 지원하지 않습니다.")

    shifted = copy_scenario_tables(tables)
    for table_name in MONTHLY_TABLES:
        frame = shifted[table_name]
        if frame.empty:
            continue
        months = frame[MONTH_COLUMN]
        first_year = int(months.min()) // 100
        last_year = int(months.max()) // 100
        # 큰 정수 이동량도 pandas 연산 전에 막아 int64 넘침으로 정상 월이 되지 않게 한다.
        if years < 1 - first_year or years > 9999 - last_year:
            raise ValueError(
                f"{table_name}의 연도 이동 결과가 유효한 YYYYMM 범위를 벗어납니다. "
                "연도 1~9999 안에 들어오도록 이동량을 줄이세요."
            )
        frame[MONTH_COLUMN] = (months // 100 + years) * 100 + months % 100
        normalize_month_column(frame, table_name)
    return shifted
