# Purpose: 비교 계획 행의 CUSTOM 다시 짝짓기 차례(Capa Code → 제품 하나 → 원래 값)를 고정한다.

"""비교 GAP 의 CUSTOM 다시 짝짓기.

CUSTOM 을 싣기 전 리비전의 계획은 모든 행이 빈 값 표지라, 그대로 현재 수율 · Chip 표로 환산하면 두
부품 제품의 짝이 없다. 여기서는 순수 함수의 차례만 본다 — 다시 짝지은 옛 계획이 현재 계획과 같은
키를 갖는 것까지다. 끝 시험은 비교 계획 길(`get_home_comparison_plan`)을 거쳐 GAP 이 0 인 것을 본다.
"""

from __future__ import annotations

import pandas as pd
from custom_key_tables import PART_A, TWO_PART_PRODUCT, custom_keyed_tables, two_part_tables

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    load_exclusions,
)
from capa_simulation.services.plan_gap import repair_comparison_plan_custom


def _plan(rows: list[tuple[str, str, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202701] * len(rows),
            "제품정보": pd.Series([row[0] for row in rows], dtype="string"),
            "Stack": pd.Series([row[1] for row in rows], dtype="string"),
            "Capa Code": pd.Series([row[2] for row in rows], dtype="string"),
            "CUSTOM": pd.Series([row[3] for row in rows], dtype="string"),
            "생산수량": [row[4] for row in rows],
        }
    )


def _yield(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": pd.Series([row[0] for row in rows], dtype="string"),
            "Stack": pd.Series([row[1] for row in rows], dtype="string"),
            "CUSTOM": pd.Series([row[2] for row in rows], dtype="string"),
        }
    )


CURRENT_PLAN = _plan(
    [
        ("DEMO_P1", "8H", "DEMO_CC1", "DEMO_CUSTOM_A", 100.0),
        ("DEMO_P1", "8H", "DEMO_CC2", "DEMO_CUSTOM_B", 50.0),
    ]
)
CURRENT_TABLES = [
    _yield([("DEMO_P1", "8H", "DEMO_CUSTOM_A"), ("DEMO_P1", "8H", "DEMO_CUSTOM_B")]),
    _yield([("DEMO_P2", "12H", "DEMO_CUSTOM_A")]),
]


def test_old_plan_rows_take_the_custom_of_the_same_capa_code() -> None:
    """옛 리비전(모두 표지)의 두 부품 Capa Code 행은 현재 계획의 같은 Capa Code 값을 받는다."""
    old = _plan(
        [
            ("DEMO_P1", "8H", "DEMO_CC1", CUSTOM_BLANK, 100.0),
            ("DEMO_P1", "8H", "DEMO_CC2", CUSTOM_BLANK, 50.0),
        ]
    )

    repaired = repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES)

    pd.testing.assert_frame_equal(repaired, CURRENT_PLAN)


def test_a_missing_capa_code_takes_the_only_custom_of_the_product() -> None:
    """현재 계획에 없는 Capa Code 는 현재 표에서 그 제품의 CUSTOM 이 하나뿐일 때 그 값을 받는다."""
    old = _plan([("DEMO_P2", "12H", "DEMO_CC9", CUSTOM_BLANK, 10.0)])

    repaired = repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES)

    assert repaired["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]


def test_an_undecided_row_keeps_its_original_value() -> None:
    """현재 표에서 그 제품의 CUSTOM 이 둘이면 고르지 않고 원래 값을 둔다 — 제외 목록이 센다."""
    old = _plan([("DEMO_P1", "8H", "DEMO_CC9", CUSTOM_BLANK, 10.0)])

    repaired = repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES)

    assert repaired["CUSTOM"].tolist() == [CUSTOM_BLANK]
    assert repaired is old


def test_the_rows_and_other_columns_are_kept() -> None:
    """행 수 · 차례 · 인덱스 · 다른 칸은 그대로다."""
    old = _plan(
        [
            ("DEMO_P1", "8H", "DEMO_CC2", CUSTOM_BLANK, 50.0),
            ("DEMO_P2", "12H", "DEMO_CC9", CUSTOM_BLANK, 10.0),
            ("DEMO_P1", "8H", "DEMO_CC1", CUSTOM_BLANK, 100.0),
        ]
    ).set_axis([7, 3, 5])

    repaired = repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES)

    assert repaired.index.tolist() == [7, 3, 5]
    assert repaired["CUSTOM"].tolist() == ["DEMO_CUSTOM_B", "DEMO_CUSTOM_A", "DEMO_CUSTOM_A"]
    pd.testing.assert_frame_equal(repaired.drop(columns="CUSTOM"), old.drop(columns="CUSTOM"))


def test_a_plan_without_custom_is_returned_as_is() -> None:
    """CUSTOM 칸이 없는 계획은 손대지 않는다."""
    old = _plan([("DEMO_P1", "8H", "DEMO_CC1", CUSTOM_BLANK, 1.0)]).drop(columns="CUSTOM")

    assert repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES) is old


def test_the_same_capa_code_wins_over_the_only_custom_of_the_product() -> None:
    """두 단계가 다른 값을 낼 때 현재 계획의 같은 Capa Code 가 현재 표의 제품 하나보다 앞선다."""
    current_plan = _plan([("DEMO_P3", "8H", "DEMO_CC1", "DEMO_CUSTOM_A", 100.0)])
    current_tables = [_yield([("DEMO_P3", "8H", "DEMO_CUSTOM_B")])]
    old = _plan([("DEMO_P3", "8H", "DEMO_CC1", CUSTOM_BLANK, 100.0)])

    repaired = repair_comparison_plan_custom(old, current_plan, current_tables)

    assert repaired["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]


def test_a_real_original_value_is_also_repaired() -> None:
    """원래 값이 표지가 아니어도(새 리비전끼리 비교) 늘 다시 짝짓는다 — 표지 행만 고치지 않는다."""
    old = _plan([("DEMO_P1", "8H", "DEMO_CC1", "DEMO_CUSTOM_B", 100.0)])

    repaired = repair_comparison_plan_custom(old, CURRENT_PLAN, CURRENT_TABLES)

    assert repaired["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]


def test_an_ambiguous_capa_code_falls_through_to_the_product() -> None:
    """현재 계획에서 같은 Capa Code 의 CUSTOM 이 둘이면 고르지 않고 제품 하나 단계로 넘어간다."""
    current_plan = _plan(
        [
            ("DEMO_P2", "12H", "DEMO_CC5", "DEMO_CUSTOM_A", 10.0),
            ("DEMO_P2", "12H", "DEMO_CC5", "DEMO_CUSTOM_B", 10.0),
        ]
    )
    old = _plan([("DEMO_P2", "12H", "DEMO_CC5", CUSTOM_BLANK, 20.0)])

    repaired = repair_comparison_plan_custom(old, current_plan, CURRENT_TABLES)

    assert repaired["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]


def _comparison(tag: str, tables: dict[str, pd.DataFrame], plan: pd.DataFrame) -> pd.DataFrame:
    """비교 계획 `plan` 을 현재 `tables` 로 환산한 HOME 월 Density · Wafer(한 표로 이음)."""
    months = sorted(int(month) for month in tables["RQ_PKG_PLAN"]["생산계획년월"].unique())
    simulation_cache.get_home_comparison_plan.clear()
    density, wafer, _detail = simulation_cache.get_home_comparison_plan(
        cache_key=(0, f"custom-gap-{tag}", months[0], months[-1], "order"),
        _tables=tables,
        _comparison_plan=plan,
        _display_order=tables["RQ_DISPLAY_ORDER"],
        comparison_revision_id=f"R-{tag}",
        include_edp=False,
        detail_dimensions=("제품정보", "Stack"),
    )
    simulation_cache.get_home_comparison_plan.clear()
    return density.merge(wafer, on="생산계획년월", validate="one_to_one")


def test_an_old_blank_custom_plan_has_no_gap_against_the_same_two_part_plan() -> None:
    """CUSTOM 을 싣기 전 리비전(모두 표지)의 같은 수량 계획은 두 부품 현재 표로 환산해도 GAP 이
    없다 — 비교 길이 환산 전에 다시 짝짓는다. 짝짓지 않으면 두 부품 제품 계획이 Chip 짝을 못 찾아
    빠진다."""
    tables = two_part_tables()
    current = tables["RQ_PKG_PLAN"]
    old = current.assign(CUSTOM=CUSTOM_BLANK)

    own = _comparison("own", tables, current)
    compared = _comparison("old", tables, old)

    pd.testing.assert_frame_equal(compared, own)
    assert own.drop(columns="생산계획년월").select_dtypes("number").to_numpy().sum() > 0


def test_a_capa_code_gone_from_the_current_plan_takes_the_product_step_or_is_left_out() -> None:
    """옛 계획의 Capa Code 가 현재 계획에 없으면 첫 단계(같은 Capa Code)로 짝짓지 못한다. 두 부품
    제품은 둘째 단계(현재 표에서 그 제품의 CUSTOM 이 하나)로도 고르지 못해 원래 값(표지)이 남는다 —
    현재 표에 짝이 없어 환산에서 빠지고 제외 목록이 그 제품만 센다. 둘째 단계가 한 부품 제품에 값을
    넣는 것은 아래 시험이 본다(이 견본의 한 부품 제품은 현재 표에서도 표지다)."""
    tables = two_part_tables()
    current = tables["RQ_PKG_PLAN"]
    old = current.assign(CUSTOM=CUSTOM_BLANK, **{"Capa Code": "DEMO_CAPA_GONE"})
    single_part = current.loc[current["제품정보"].ne(TWO_PART_PRODUCT)]

    compared = _comparison("gone", tables, old)

    pd.testing.assert_frame_equal(compared, _comparison("single", tables, single_part))
    repaired = repair_comparison_plan_custom(
        old, current, (tables["RQ_YLD"], tables["RQ_CHIP_QTY"], tables["RQ_CHIP_EQ"])
    )
    _, wafer = calculate_chip_and_wafer_loads(repaired, tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
    assert set(load_exclusions(wafer)["제품정보"]) == {TWO_PART_PRODUCT}


def _one_part_tables(part: str) -> dict[str, pd.DataFrame]:
    """내장 시드의 CUSTOM 키 표 여덟 CUSTOM 을 모두 `part` 로 바꾼 사본 — 모든 제품이 표지가 아닌
    부품 하나를 갖는 꼴."""
    tables = dict(build_builtin_seed_dataset().reference_tables)
    for name in custom_keyed_tables():
        tables[name] = tables[name].assign(CUSTOM=part)
    return tables


def test_the_comparison_path_gives_a_single_part_product_its_only_custom() -> None:
    """옛 계획(모두 표지)의 Capa Code 가 현재 계획에 없고 현재 표의 제품마다 부품이 표지 아닌 값
    하나면, 비교 길(`get_home_comparison_plan`)이 둘째 단계 — 현재 수율 · Chip 표에서 그 제품의
    CUSTOM 이 하나 — 로 짝지어 GAP 이 없다. 비교 길이 둘째 단계 표를 넘기지 않으면 표지가 남아
    계획이 Chip 짝을 못 찾고 환산에서 말없이 빠진다(HOME · Summary GAP 에 거짓 감소)."""
    tables = _one_part_tables(PART_A)
    current = tables["RQ_PKG_PLAN"]
    old = current.assign(CUSTOM=CUSTOM_BLANK, **{"Capa Code": "DEMO_CAPA_GONE"})

    own = _comparison("own-part", tables, current)
    compared = _comparison("gone-part", tables, old)

    assert own.drop(columns="생산계획년월").select_dtypes("number").to_numpy().sum() > 0
    pd.testing.assert_frame_equal(compared, own)
