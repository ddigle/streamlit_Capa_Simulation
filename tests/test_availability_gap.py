# Purpose: Static·Dynamic 가용대수 비교표의 행 구성과 맞대지 못한 공정 보고를 검사한다.

"""**한쪽에만 있는 공정이 조용히 사라지면 안 된다.**

Static(기준정보 `RQ_EQP_AVBL`)과 Dynamic(호기 마스터 안분)은 서로 다른 DB 에 있고,
공정 이름이 같은 값이라는 것을 강제하는 장치가 저장소에 없다. 그래서 조인에서 떨어진
공정을 반드시 목록으로 돌려줘야 화면이 그것을 드러낼 수 있다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    GAP_ROW,
    STATIC_ROW,
    build_availability_gap,
    gap_matrix,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff

PROCESS = "DEMO_ATTACH"
MONTHS = [202610]


def monthly_for(units: int, *, cutoff: float = 0) -> pd.DataFrame:
    spans = pd.DataFrame(
        {
            "호기": [f"EQ-{index}" for index in range(units)],
            "공정소분류": [PROCESS] * units,
            "상태": ["가용"] * units,
            "시작일": [date(2020, 1, 1)] * units,
            "종료일": [date(2030, 1, 1)] * units,
        }
    )
    baseline = pd.DataFrame(
        {"공정": pd.Series(dtype="string"), "기존보유대수": pd.Series(dtype="float64")}
    )
    cutoff_table = prepare_process_cutoff(
        pd.DataFrame({"공정": [PROCESS], "Cutoff일수": [cutoff], "비고": [None]})
    )
    return build_monthly_equipment_availability(spans, baseline, cutoff_table, MONTHS)


def static_for(count: float, process: str = PROCESS) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": MONTHS, "공정": [process], "가용대수": [count]})


def value_of(rows: pd.DataFrame, row_name: str) -> float:
    return float(rows.loc[rows["행"] == row_name, "대수"].iloc[0])


def test_the_gap_is_dynamic_minus_static() -> None:
    comparison = build_availability_gap(monthly_for(8), static_for(12.0), MONTHS)

    assert value_of(comparison.rows, DYNAMIC_SUBTOTAL_ROW) == 8.0
    assert value_of(comparison.rows, STATIC_ROW) == 12.0
    assert value_of(comparison.rows, GAP_ROW) == -4.0


def test_a_process_only_in_the_equipment_side_is_reported() -> None:
    comparison = build_availability_gap(monthly_for(3), static_for(5.0, "다른_공정"), MONTHS)

    assert comparison.dynamic_only == [PROCESS]
    assert comparison.static_only == ["다른_공정"]


def test_a_process_missing_from_one_side_still_gets_a_gap_row() -> None:
    """없는 쪽을 0 으로 본다 — 행이 통째로 사라지면 차이를 볼 수 없다."""
    comparison = build_availability_gap(monthly_for(3), static_for(5.0, "다른_공정"), MONTHS)

    gaps = comparison.rows.loc[comparison.rows["행"] == GAP_ROW]
    by_process = dict(zip(gaps["공정"], gaps["대수"], strict=True))
    assert by_process[PROCESS] == 3.0
    assert by_process["다른_공정"] == -5.0


def test_static_rows_for_the_same_month_are_added_up() -> None:
    """기준정보 편집이 같은 월·공정을 두 줄로 쪼개 놓았을 수 있다."""
    split = pd.DataFrame(
        {"생산계획년월": MONTHS * 2, "공정": [PROCESS] * 2, "가용대수": [7.0, 5.0]}
    )

    comparison = build_availability_gap(monthly_for(0), split, MONTHS)

    assert value_of(comparison.rows, STATIC_ROW) == 12.0


def test_months_outside_the_request_are_dropped() -> None:
    other = pd.DataFrame({"생산계획년월": [202601], "공정": [PROCESS], "가용대수": [99.0]})

    comparison = build_availability_gap(monthly_for(2), other, MONTHS)

    assert 202601 not in set(comparison.rows["생산계획년월"])
    assert value_of(comparison.rows, GAP_ROW) == 2.0


def test_the_matrix_puts_months_in_columns_and_orders_the_rows() -> None:
    comparison = build_availability_gap(monthly_for(8), static_for(12.0), MONTHS)

    matrix = gap_matrix(comparison.rows, PROCESS)

    assert list(matrix.columns) == ["202610"]
    assert list(matrix.index)[-3:] == [DYNAMIC_SUBTOTAL_ROW, STATIC_ROW, GAP_ROW]
    assert matrix.loc[GAP_ROW, "202610"] == -4.0


def test_the_matrix_without_a_process_sums_every_process() -> None:
    monthly = pd.concat(
        [monthly_for(3), monthly_for(3).assign(공정="두번째_공정")], ignore_index=True
    )
    static = pd.DataFrame(
        {
            "생산계획년월": MONTHS * 2,
            "공정": [PROCESS, "두번째_공정"],
            "가용대수": [4.0, 4.0],
        }
    )

    comparison = build_availability_gap(monthly, static, MONTHS)
    matrix = gap_matrix(comparison.rows)

    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "202610"] == 6.0
    assert matrix.loc[GAP_ROW, "202610"] == -2.0


def test_empty_inputs_give_an_empty_comparison() -> None:
    comparison = build_availability_gap(monthly_for(0), pd.DataFrame(), MONTHS)

    assert comparison.rows.empty
    assert comparison.dynamic_only == []
    assert comparison.static_only == []
    assert gap_matrix(comparison.rows).empty


def test_a_static_table_missing_a_column_is_refused() -> None:
    broken = pd.DataFrame({"생산계획년월": MONTHS, "공정": [PROCESS]})

    with pytest.raises(ValueError, match="필수 컬럼"):
        build_availability_gap(monthly_for(1), broken, MONTHS)
