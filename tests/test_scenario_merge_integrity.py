# Purpose: 월 머지 결과의 월 없는 표 보충·결손 검사·달력 공백·가상제품 이력 정리를 검증한다.

"""**덧붙인 달이 쓰는 제품·공정의 월 없는 기준정보가 결과에 남아야 한다.**

월 없는 네 표(`RQ_CHIP_QTY`·`RQ_CHIP_EQ`·`RQ_MODULE`·`RQ_DISPLAY_ORDER`)를 베이스 것만 남기면
덧붙일 쪽에만 있는 공정은 `RQ_MODULE` 결손으로 계산이 멈추고(사내 머지 ①), 덧붙일 쪽에만 있는
제품(가상 제품 포함)은 `RQ_CHIP_*` 결손으로 부하량에서 조용히 빠진다(사내 머지 ②, 감사 D1).
"""

import pandas as pd
import pytest
from test_duckdb_repository import _reference_tables

from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.scenario_month_merge import (
    NON_MONTHLY_SUPPLEMENT_KEYS,
    compare_non_monthly_tables,
    merge_scenario_months,
    merged_table_gaps,
)
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    format_month_runs,
    missing_calendar_months,
)
from capa_simulation.services.scenario_virtual_products import merge_result_virtual_products
from capa_simulation.services.simulation_cache import get_capacity_and_demand
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    clone_product,
)

SEED_MONTHS = tuple(range(202601, 202613))
FIRST_HALF = SEED_MONTHS[:6]
SECOND_HALF = SEED_MONTHS[6:]


def _seed() -> dict[str, pd.DataFrame]:
    return {
        name: frame.copy(deep=True)
        for name, frame in build_builtin_seed_dataset().reference_tables.items()
    }


def _within(tables: dict[str, pd.DataFrame], months: tuple[int, ...]) -> dict[str, pd.DataFrame]:
    return {
        name: (
            frame.loc[frame["생산계획년월"].isin(months)].reset_index(drop=True)
            if name in MONTHLY_TABLES
            else frame.copy(deep=True)
        )
        for name, frame in tables.items()
    }


def _required_by_month(tables: dict[str, pd.DataFrame], months: tuple[int, ...]) -> pd.Series:
    _, required = get_capacity_and_demand(
        {name: frame.copy(deep=True) for name, frame in tables.items()}
    )
    selected = required.loc[required["생산계획년월"].isin(months)]
    return selected.groupby("생산계획년월")["소요대수"].sum()


def test_a_process_only_the_donor_has_takes_its_module_from_the_donor() -> None:
    """사내 머지 ①: 베이스(공식버전)에 없는 공정이 덧붙인 달에만 있어도 그 달이 계산된다."""
    process = "DEMO_Final_Test"
    base = _within(_seed(), FIRST_HALF)
    for name in (*MONTHLY_TABLES, "RQ_MODULE"):
        if "공정" in base[name].columns:
            base[name] = base[name].loc[base[name]["공정"].ne(process)].reset_index(drop=True)
    donor = _within(_seed(), SECOND_HALF)
    # 두 원본은 각자 계산된다 — 결손은 머지가 만든다.
    _required_by_month(base, FIRST_HALF)
    expected = _required_by_month(donor, SECOND_HALF)

    merged = merge_scenario_months(base, donor, SECOND_HALF[0], SECOND_HALF[-1])

    assert process in set(merged["RQ_MODULE"]["공정"])
    pd.testing.assert_series_equal(_required_by_month(merged, SECOND_HALF), expected)
    assert merged_table_gaps(merged).blocking == ()


def test_a_virtual_product_only_the_donor_has_keeps_its_load() -> None:
    """감사 D1: 덧붙일 쪽에만 있는 가상 제품도 덧붙인 달의 부하량에 든다(덧붙일 쪽 단독과 같다)."""
    seed = _seed()
    request = VirtualProductRequest("DEMO PRODUCT A", "8H", "DEMO_VIRTUAL_X", "8H")
    donor = {**seed, **clone_product(seed, request)}
    plan = donor["RQ_PKG_PLAN"]
    donor["RQ_PKG_PLAN"] = plan.assign(
        생산수량=plan["생산수량"].mask(plan["제품정보"].eq("DEMO_VIRTUAL_X"), 1000.0)
    )
    base = _within(seed, FIRST_HALF)
    expected = _required_by_month(donor, SECOND_HALF)

    merged = merge_scenario_months(base, donor, SECOND_HALF[0], SECOND_HALF[-1])

    for name in ("RQ_CHIP_QTY", "RQ_CHIP_EQ"):
        assert "DEMO_VIRTUAL_X" in set(merged[name]["제품정보"])
    pd.testing.assert_series_equal(_required_by_month(merged, SECOND_HALF), expected)
    assert merged_table_gaps(merged) == ((), ())


def test_shared_keys_keep_the_base_values_and_only_missing_keys_come_from_the_donor() -> None:
    """겹치는 키는 베이스 값, 베이스에 없는 키만 덧붙일 쪽 행을 더한다(사용자 확인 대기 기본안)."""
    base, donor = _reference_tables(), _reference_tables()
    for name in MONTHLY_TABLES:
        donor[name] = donor[name].assign(생산계획년월=202701)
    donor["RQ_CHIP_QTY"] = pd.concat(
        [
            donor["RQ_CHIP_QTY"].assign(**{"Net Die": 999.0}),
            donor["RQ_CHIP_QTY"].assign(제품정보="Product-B", Stack="12H"),
        ],
        ignore_index=True,
    )
    donor["RQ_CHIP_EQ"] = pd.concat(
        [donor["RQ_CHIP_EQ"], donor["RQ_CHIP_EQ"].assign(제품정보="Product-B", Stack="12H")],
        ignore_index=True,
    )
    donor["RQ_MODULE"] = pd.DataFrame({"공정": ["Process-A", "Process-B"], "모듈수": [9.0, 3.0]})
    donor["RQ_DISPLAY_ORDER"] = donor["RQ_DISPLAY_ORDER"].assign(분류값="Donor")

    merged = merge_scenario_months(base, donor, 202701, 202701)

    chip = merged["RQ_CHIP_QTY"].set_index(["제품정보", "Stack"])
    assert chip.loc[("Product-A", "8H"), "Net Die"] == 1000.0
    assert ("Product-B", "12H") in chip.index
    assert len(merged["RQ_CHIP_EQ"]) == 2
    module = merged["RQ_MODULE"].set_index("공정")["모듈수"]
    assert module.to_dict() == {"Process-A": 2.0, "Process-B": 3.0}
    pd.testing.assert_frame_equal(merged["RQ_DISPLAY_ORDER"], base["RQ_DISPLAY_ORDER"])
    comparison = compare_non_monthly_tables(base, donor).set_index("표")
    assert comparison.loc["RQ_CHIP_QTY", "보충 행 수"] == 1
    assert comparison.loc["RQ_MODULE", "보충 행 수"] == 1
    assert comparison.loc["RQ_DISPLAY_ORDER", "보충 행 수"] == 0
    assert set(NON_MONTHLY_SUPPLEMENT_KEYS) == {"RQ_CHIP_QTY", "RQ_CHIP_EQ", "RQ_MODULE"}


def test_gap_check_blocks_a_module_gap_and_warns_about_planned_products_without_chips() -> None:
    """계산이 멈출 결손은 막고, 조용히 빠질 결손은 경고한다 — 둘 다 표·키 예시와 함께."""
    tables = _reference_tables()
    tables["RQ_UPEH"] = pd.concat(
        [tables["RQ_UPEH"], tables["RQ_UPEH"].assign(공정="Process-Z", 생산계획년월=202609)],
        ignore_index=True,
    )
    tables["RQ_PKG_PLAN"] = pd.concat(
        [
            tables["RQ_PKG_PLAN"],
            tables["RQ_PKG_PLAN"].assign(제품정보="Product-Z", 생산수량=50.0),
            tables["RQ_PKG_PLAN"].assign(제품정보="Product-Unplanned", 생산수량=0.0),
        ],
        ignore_index=True,
    )

    gaps = merged_table_gaps(tables)

    assert len(gaps.blocking) == 1
    assert "RQ_MODULE" in gaps.blocking[0] and "Process-Z" in gaps.blocking[0]
    assert "2026-09" in gaps.blocking[0]
    assert len(gaps.warnings) == 2
    for name, warning in zip(("RQ_CHIP_QTY", "RQ_CHIP_EQ"), gaps.warnings, strict=True):
        assert name in warning and "Product-Z · 8H" in warning
        assert "Product-Unplanned" not in warning
    assert merged_table_gaps(_reference_tables()) == ((), ())


def test_unimplemented_bases_do_not_need_a_module() -> None:
    """BOX·PCB 소요기준 행은 대당 Capa 계산에서 먼저 빠진다 — 모듈수가 없어도 멈추지 않는다."""
    tables = _reference_tables()
    tables["RQ_UPEH"] = pd.concat(
        [tables["RQ_UPEH"], tables["RQ_UPEH"].assign(공정="Process-BOX", 소요기준="box")],
        ignore_index=True,
    )

    assert merged_table_gaps(tables).blocking == ()


def test_calendar_gaps_between_the_first_and_last_month_are_listed() -> None:
    """감사 D6: 머지는 표끼리의 월 축만 견주므로 결과 월 사이의 빈 달을 따로 찾는다."""
    assert missing_calendar_months((202611, 202612, 202703, 202704)) == (202701, 202702)
    assert missing_calendar_months((202612, 202701)) == ()
    assert missing_calendar_months(()) == ()
    assert format_month_runs((202701, 202702, 202703, 202706)) == "2027-01~2027-03, 2027-06"


def test_merged_history_keeps_only_keys_left_in_the_result() -> None:
    """감사 D4: 결과 표에 그 제품 키가 하나도 없으면 이력에서 뺀다(뺀 수를 알린다)."""
    base, donor = _reference_tables(), _reference_tables()
    for name, frame in donor.items():
        if "제품정보" in frame.columns:
            donor[name] = frame.assign(제품정보="Product-D")
    kept = VirtualProductRecord("Product-A", "8H", "원본 A", "8H")
    gone = VirtualProductRecord("Product-Gone", "8H", "원본 A", "8H")

    history = merge_result_virtual_products(
        (kept,), (gone,), base_tables=base, donor_tables=donor, result_tables=base
    )

    assert history.records == (kept,)
    assert history.dropped == (gone,)
    assert history.mixed == ()


@pytest.mark.parametrize("virtual_side", ["base", "donor"])
def test_a_virtual_product_that_is_real_on_the_other_side_is_reported(virtual_side: str) -> None:
    """감사 D4: 한쪽의 가상 제품이 다른 쪽에선 실제 제품이면 결과에서 두 값이 섞인다."""
    base, donor = _reference_tables(), _reference_tables()
    record = VirtualProductRecord("Product-A", "8H", "원본 A", "8H")
    base_records = (record,) if virtual_side == "base" else ()
    donor_records = (record,) if virtual_side == "donor" else ()

    history = merge_result_virtual_products(
        base_records, donor_records, base_tables=base, donor_tables=donor, result_tables=base
    )

    assert history.records == (record,)
    assert history.mixed == (record,)
    same_on_both_sides = merge_result_virtual_products(
        (record,), (record,), base_tables=base, donor_tables=donor, result_tables=base
    )
    assert same_on_both_sides.mixed == ()
