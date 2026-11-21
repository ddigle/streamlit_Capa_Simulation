# Purpose: 비교 계획 행의 CUSTOM 다시 짝짓기 차례(Capa Code → 제품 하나 → 원래 값)를 고정한다.

"""비교 GAP 의 CUSTOM 다시 짝짓기.

CUSTOM 을 싣기 전 리비전의 계획은 모든 행이 빈 값 표지라, 그대로 현재 수율 · Chip 표로 환산하면 두
부품 제품의 짝이 없다. 여기서는 순수 함수의 차례만 본다 — 다시 짝지은 옛 계획이 현재 계획과 같은
키를 갖는 것까지다. 환산을 거쳐 GAP 이 0 인 것은 비교 계획 길에 이 함수를 잇는 단계의 시험이다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
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
