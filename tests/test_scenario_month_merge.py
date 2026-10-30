# Purpose: 월 머지의 겹침 정책과 미리보기 일치 및 원본·무월 표 보존과 월 축 검증을 확인한다.

from collections.abc import Callable

import pandas as pd
import pytest
from test_duckdb_repository import _reference_tables

from capa_simulation.services.scenario_month_merge import (
    OverlapPolicy,
    compare_non_monthly_tables,
    merge_scenario_months,
    preview_month_sources,
)
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES


def _month_tables(
    months: list[int], source: str, rows_per_month: int = 1
) -> dict[str, pd.DataFrame]:
    tables = _reference_tables()
    for name in MONTHLY_TABLES:
        template = tables[name]
        tables[name] = pd.concat(
            [
                template.assign(
                    생산계획년월=month,
                    **{
                        column: f"{source}-{row}"
                        for column in ("제품정보", "공정")
                        if column in template.columns
                    },
                )
                for month in months
                for row in range(rows_per_month)
            ],
            ignore_index=True,
        )
    return tables


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


@pytest.mark.parametrize("operation", [merge_scenario_months, preview_month_sources])
@pytest.mark.parametrize(
    "start,end,message",
    [
        (202700, 202701, "YYYYMM"),
        (202801, 202701, "클 수"),
        (202701, 202712, "월 데이터가 없습니다"),
    ],
)
def test_invalid_or_empty_range_is_rejected(
    operation: Callable[..., object], start: int, end: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        operation(_reference_tables(), _reference_tables(), start, end)


@pytest.mark.parametrize("policy", ["base", "donor"])
def test_overlap_policy_selects_whole_months_and_matches_preview(policy: OverlapPolicy) -> None:
    base = _month_tables([202608, 202609], "base")
    donor = _month_tables([202607, 202609, 202701, 202702], "donor", rows_per_month=2)
    for name in NON_MONTHLY_TABLES:
        donor[name] = donor[name].iloc[:0]
    before_base = {name: frame.copy(deep=True) for name, frame in base.items()}
    before_donor = {name: frame.copy(deep=True) for name, frame in donor.items()}

    preview = preview_month_sources(base, donor, 202609, 202701, overlap_policy=policy)
    merged = merge_scenario_months(base, donor, 202609, 202701, overlap_policy=policy)

    assert preview.columns.tolist() == ["생산계획년월", "베이스", "덧붙일 쪽", "선택 출처"]
    assert pd.api.types.is_integer_dtype(preview["생산계획년월"])
    assert pd.api.types.is_bool_dtype(preview["베이스"])
    assert pd.api.types.is_bool_dtype(preview["덧붙일 쪽"])
    assert preview["생산계획년월"].tolist() == [202608, 202609, 202701]
    assert preview["베이스"].tolist() == [True, True, False]
    assert preview["덧붙일 쪽"].tolist() == [False, True, True]
    assert preview["선택 출처"].tolist() == [
        "베이스",
        "베이스" if policy == "base" else "덧붙일 쪽",
        "덧붙일 쪽",
    ]
    for name in MONTHLY_TABLES:
        for month, source in preview[["생산계획년월", "선택 출처"]].itertuples(
            index=False, name=None
        ):
            winner = base[name] if source == "베이스" else donor[name]
            expected = winner.loc[winner["생산계획년월"].eq(month)].reset_index(drop=True)
            actual = merged[name].loc[merged[name]["생산계획년월"].eq(month)].reset_index(drop=True)
            pd.testing.assert_frame_equal(actual, expected)
        assert set(merged[name]["생산계획년월"]) == {202608, 202609, 202701}
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(merged[name], base[name])
    for name in base:
        pd.testing.assert_frame_equal(base[name], before_base[name])
        pd.testing.assert_frame_equal(donor[name], before_donor[name])


@pytest.mark.parametrize("policy", ["base", "donor"])
def test_fully_overlapping_months_keep_only_the_chosen_source(policy: OverlapPolicy) -> None:
    base = _month_tables([202608, 202609], "base")
    donor = _month_tables([202608, 202609], "donor", rows_per_month=2)

    merged = merge_scenario_months(base, donor, 202608, 202609, overlap_policy=policy)

    for name in MONTHLY_TABLES:
        expected = base[name] if policy == "base" else donor[name]
        pd.testing.assert_frame_equal(merged[name], expected)
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(merged[name], base[name])


@pytest.mark.parametrize("policy", ["base", "donor"])
def test_missing_winner_month_is_rejected_instead_of_using_loser_rows(
    policy: OverlapPolicy,
) -> None:
    base = _month_tables([202608, 202609], "base")
    donor = _month_tables([202609, 202701], "donor")
    winner = base if policy == "base" else donor
    winner["RQ_UPEH"] = winner["RQ_UPEH"].loc[winner["RQ_UPEH"]["생산계획년월"].ne(202609)]

    with pytest.raises(ValueError, match="RQ_UPEH: 누락 1개월"):
        merge_scenario_months(base, donor, 202609, 202701, overlap_policy=policy)


def test_default_preview_lists_overlaps_as_blocked_and_range_excludes_other_donor_months() -> None:
    base = _month_tables([202608, 202609], "base")
    donor = _month_tables([202608, 202609, 202701], "donor")

    preview = preview_month_sources(base, donor, 202609, 202609)

    assert preview.to_dict("records") == [
        {"생산계획년월": 202608, "베이스": True, "덧붙일 쪽": False, "선택 출처": "베이스"},
        {
            "생산계획년월": 202609,
            "베이스": True,
            "덧붙일 쪽": True,
            "선택 출처": "미선택 · 저장 차단",
        },
    ]
    with pytest.raises(ValueError, match="1개월이 겹쳐.*2026-09"):
        merge_scenario_months(base, donor, 202609, 202609)


def _months(first: int, count: int) -> list[int]:
    year, month = divmod(first, 100)
    months = []
    for _ in range(count):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


@pytest.mark.parametrize(
    ("overlap", "tail"),
    [(12, "2027-06. "), (13, "2027-06 외 1개월. "), (18, "2027-06 외 6개월. ")],
)
def test_the_overlap_refusal_names_twelve_months_and_counts_the_rest(
    overlap: int, tail: str
) -> None:
    """겹친 달이 많으면 앞 12개월만 적고 나머지는 「외 N개월」 로 센다 — 18개월이 겹쳐도 12개월만
    적고 생략 표시가 없던 것(2026-10-27 표적 E2E)."""
    base = _month_tables(_months(202607, overlap), "base")
    donor = _month_tables(_months(202607, overlap + 6), "donor")
    start, end = 202607, _months(202607, overlap + 6)[-1]

    with pytest.raises(ValueError) as caught:
        merge_scenario_months(base, donor, start, end)

    message = str(caught.value)
    assert message.startswith(f"베이스와 {overlap}개월이 겹쳐 저장할 수 없습니다: 2026-07, ")
    assert tail in message
    assert message.count(", 20") == 11


@pytest.mark.parametrize("operation", [merge_scenario_months, preview_month_sources])
def test_invalid_overlap_policy_is_rejected(operation: Callable[..., object]) -> None:
    with pytest.raises(ValueError, match="지원하지 않는 월 겹침 정책"):
        operation(_reference_tables(), _reference_tables(), 202608, 202608, overlap_policy="other")


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
