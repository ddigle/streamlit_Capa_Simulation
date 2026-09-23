# Purpose: 월 머지가 원본과 무월 표를 보존하고 겹침·부분 월 누락을 저장 전에 막는지 검증한다.

import pandas as pd
import pytest
from test_duckdb_repository import _reference_tables

from capa_simulation.services.scenario_month_merge import (
    compare_non_monthly_tables,
    merge_scenario_months,
)
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES


def test_merge_selects_months_and_keeps_all_base_non_monthly_values() -> None:
    base, donor = _reference_tables(), _reference_tables()
    original_base = {name: frame.copy(deep=True) for name, frame in base.items()}
    for name in MONTHLY_TABLES:
        donor[name] = pd.concat(
            [donor[name].assign(생산계획년월=month) for month in (202608, 202701, 202702)]
        )
    for name in NON_MONTHLY_TABLES:
        donor[name] = donor[name].iloc[:0]
    original_donor = {name: frame.copy(deep=True) for name, frame in donor.items()}
    merged = merge_scenario_months(base, donor, 202701, 202701)
    for name in MONTHLY_TABLES:
        assert merged[name]["생산계획년월"].tolist() == [202608, 202701]
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(merged[name], base[name])
    for name in base:
        pd.testing.assert_frame_equal(base[name], original_base[name])
        pd.testing.assert_frame_equal(donor[name], original_donor[name])


def test_overlap_is_rejected_even_when_only_one_table_has_the_month() -> None:
    base, donor = _reference_tables(), _reference_tables()
    for name in MONTHLY_TABLES:
        donor[name]["생산계획년월"] = 202701
    base["RQ_UPEH"]["생산계획년월"] = 202701
    with pytest.raises(ValueError, match="겹쳐"):
        merge_scenario_months(base, donor, 202701, 202701)


def test_merge_rejects_result_axis_gaps() -> None:
    base, donor = _reference_tables(), _reference_tables()
    for name in MONTHLY_TABLES:
        donor[name]["생산계획년월"] = 202701
    donor["RQ_UPEH"] = donor["RQ_UPEH"].iloc[:0]
    with pytest.raises(ValueError, match="RQ_UPEH: 누락 1개월"):
        merge_scenario_months(base, donor, 202701, 202701)


@pytest.mark.parametrize(
    "start,end,message",
    [
        (202700, 202701, "YYYYMM"),
        (202801, 202701, "클 수"),
        (202701, 202712, "월 데이터가 없습니다"),
    ],
)
def test_invalid_or_empty_range_is_rejected(start: int, end: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        merge_scenario_months(_reference_tables(), _reference_tables(), start, end)


def test_non_monthly_comparison_checks_values_counts_and_ignores_order() -> None:
    base, donor = _reference_tables(), _reference_tables()
    base["RQ_CHIP_EQ"] = pd.concat([base["RQ_CHIP_EQ"], base["RQ_CHIP_EQ"].assign(제품정보="B")])
    donor["RQ_CHIP_EQ"] = base["RQ_CHIP_EQ"].iloc[::-1, ::-1]
    donor["RQ_CHIP_QTY"]["Net Die"] = 999
    donor["RQ_MODULE"] = donor["RQ_MODULE"].iloc[:0]
    donor["RQ_DISPLAY_ORDER"]["분류값"] = "다른 제품"
    comparison = compare_non_monthly_tables(base, donor).set_index("표")
    assert comparison.loc["RQ_CHIP_EQ", "비교"] == "같음"
    for name in NON_MONTHLY_TABLES[1:]:
        assert comparison.loc[name, "비교"] == "다름 · 베이스 유지"
    assert comparison.loc["RQ_MODULE", "베이스 행 수"] == 1
    assert comparison.loc["RQ_MODULE", "덧붙일 쪽 행 수"] == 0
