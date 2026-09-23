# Purpose: 베이스 16표에 선택한 비중복 월을 합치고 무월 표 차이와 결과 월 축을 검증한다.

from collections.abc import Mapping

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column
from capa_simulation.services.month_filter import MONTH_COLUMN
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    NON_MONTHLY_TABLES,
    copy_scenario_tables,
    format_month,
    scenario_months,
    validate_month_axes,
)


def compare_non_monthly_tables(
    base: Mapping[str, pd.DataFrame], donor: Mapping[str, pd.DataFrame]
) -> pd.DataFrame:
    """행·컬럼 순서와 dtype 표현을 제외한 값 차이 및 양쪽 행 수를 표시한다."""
    rows = []
    for name in NON_MONTHLY_TABLES:
        left, right = base[name], donor[name]
        equal = set(left.columns) == set(right.columns)
        if equal:
            columns = sorted(left.columns)
            try:
                pd.testing.assert_frame_equal(
                    left[columns].sort_values(columns).reset_index(drop=True),
                    right[columns].sort_values(columns).reset_index(drop=True),
                    check_dtype=False,
                    check_exact=True,
                )
            except AssertionError:
                equal = False
        rows.append(
            {
                "표": name,
                "베이스 행 수": len(left),
                "덧붙일 쪽 행 수": len(right),
                "비교": "같음" if equal else "다름 · 베이스 유지",
            }
        )
    return pd.DataFrame(rows)


def merge_scenario_months(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
) -> dict[str, pd.DataFrame]:
    """월이 하나라도 겹치면 거부하며 월 없는 네 표는 베이스 사본을 유지한다."""
    bounds = pd.DataFrame({MONTH_COLUMN: [start_month, end_month]})
    normalize_month_column(bounds, "덧붙일 월 범위")
    start_month, end_month = (int(value) for value in bounds[MONTH_COLUMN])
    if start_month > end_month:
        raise ValueError("덧붙일 시작 월은 종료 월보다 클 수 없습니다.")
    result = copy_scenario_tables(base)
    donor_copy = copy_scenario_tables(donor)
    selected_months = {
        month for month in scenario_months(donor_copy) if start_month <= month <= end_month
    }
    if not selected_months:
        raise ValueError("선택한 범위에 덧붙일 월 데이터가 없습니다.")
    overlap = set(scenario_months(result)) & selected_months
    if overlap:
        sample = ", ".join(format_month(month) for month in sorted(overlap)[:12])
        raise ValueError(
            f"베이스와 {len(overlap)}개월이 겹쳐 저장할 수 없습니다: {sample}. "
            "덧붙일 월 범위를 좁혀 주세요."
        )
    for name in MONTHLY_TABLES:
        if set(result[name].columns) != set(donor_copy[name].columns):
            raise ValueError(f"{name}의 두 시나리오 컬럼이 일치하지 않습니다.")
        addition = donor_copy[name].loc[donor_copy[name][MONTH_COLUMN].isin(selected_months)]
        if not addition.empty:
            result[name] = pd.concat([result[name], addition], ignore_index=True)
    validate_month_axes(result)
    return result
