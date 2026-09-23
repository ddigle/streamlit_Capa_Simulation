# Purpose: 선택한 겹침 정책으로 월별 원본을 정해 16표를 합치고 무월 표와 결과 월 축을 검증한다.

from collections.abc import Mapping
from typing import Literal

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

OverlapPolicy = Literal["reject", "base", "donor"]


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


def _prepare_month_sources(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    overlap_policy: OverlapPolicy,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame]:
    """미리보기와 저장이 같은 범위 검증 및 월 전체 선택 규칙을 사용하게 한다."""
    if overlap_policy not in ("reject", "base", "donor"):
        raise ValueError(f"지원하지 않는 월 겹침 정책입니다: {overlap_policy}")
    bounds = pd.DataFrame({MONTH_COLUMN: [start_month, end_month]})
    normalize_month_column(bounds, "덧붙일 월 범위")
    start_month, end_month = (int(value) for value in bounds[MONTH_COLUMN])
    if start_month > end_month:
        raise ValueError("덧붙일 시작 월은 종료 월보다 클 수 없습니다.")
    base_copy = copy_scenario_tables(base)
    donor_copy = copy_scenario_tables(donor)
    selected_months = {
        month for month in scenario_months(donor_copy) if start_month <= month <= end_month
    }
    if not selected_months:
        raise ValueError("선택한 범위에 덧붙일 월 데이터가 없습니다.")
    base_months = set(scenario_months(base_copy))
    overlap_source = {
        "reject": "미선택 · 저장 차단",
        "base": "베이스",
        "donor": "덧붙일 쪽",
    }[overlap_policy]
    rows = []
    for month in sorted(base_months | selected_months):
        in_base, in_donor = month in base_months, month in selected_months
        selected_source = (
            overlap_source if in_base and in_donor else "베이스" if in_base else "덧붙일 쪽"
        )
        rows.append(
            {
                MONTH_COLUMN: month,
                "베이스": in_base,
                "덧붙일 쪽": in_donor,
                "선택 출처": selected_source,
            }
        )
    return base_copy, donor_copy, pd.DataFrame(rows)


def preview_month_sources(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    *,
    overlap_policy: OverlapPolicy = "reject",
) -> pd.DataFrame:
    """베이스 전체와 선택 범위의 덧붙일 월을 비교하고 월별 선택 출처를 보여 준다."""
    _, _, preview = _prepare_month_sources(base, donor, start_month, end_month, overlap_policy)
    return preview


def merge_scenario_months(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    *,
    overlap_policy: OverlapPolicy = "reject",
) -> dict[str, pd.DataFrame]:
    """겹친 월 전체를 고른 원본에서 가져오고 월 없는 네 표는 베이스를 유지한다."""
    result, donor_copy, preview = _prepare_month_sources(
        base, donor, start_month, end_month, overlap_policy
    )
    blocked = preview.loc[preview["선택 출처"].eq("미선택 · 저장 차단"), MONTH_COLUMN]
    if not blocked.empty:
        sample = ", ".join(format_month(int(month)) for month in blocked.iloc[:12])
        raise ValueError(
            f"베이스와 {len(blocked)}개월이 겹쳐 저장할 수 없습니다: {sample}. "
            "겹친 월에 사용할 시나리오를 선택하거나 덧붙일 월 범위를 좁혀 주세요."
        )
    base_months = preview.loc[preview["선택 출처"].eq("베이스"), MONTH_COLUMN]
    donor_months = preview.loc[preview["선택 출처"].eq("덧붙일 쪽"), MONTH_COLUMN]
    for name in MONTHLY_TABLES:
        if set(result[name].columns) != set(donor_copy[name].columns):
            raise ValueError(f"{name}의 두 시나리오 컬럼이 일치하지 않습니다.")
        # 제품·공정 키가 달라도 패자의 그 월 행은 전부 제외한다. 누락값을 보충하지 않는다.
        result[name] = result[name].loc[result[name][MONTH_COLUMN].isin(base_months)].copy()
        addition = donor_copy[name].loc[donor_copy[name][MONTH_COLUMN].isin(donor_months)]
        if not addition.empty:
            result[name] = pd.concat([result[name], addition], ignore_index=True)
    validate_month_axes(result)
    return result
