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
    DYNAMIC_WEIGHTED_ROW,
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


def test_a_process_missing_from_one_side_gets_no_gap_row() -> None:
    """한쪽에만 있는 공정은 GAP 을 내지 않는다(2026-10-01 사용자 결정).

    없는 쪽을 0 으로 보면 공정명 불일치가 「Dynamic 만큼 모자라다(넘친다)」로 읽혔다. 그 공정의
    분류·소계와 Static 행은 남아 따로 볼 수 있다.
    """
    comparison = build_availability_gap(monthly_for(3), static_for(5.0, "다른_공정"), MONTHS)

    rows = comparison.rows
    assert rows.loc[rows["행"] == GAP_ROW].empty
    subtotal = rows.loc[rows["행"] == DYNAMIC_SUBTOTAL_ROW]
    assert dict(zip(subtotal["공정"], subtotal["대수"], strict=True)) == {PROCESS: 3.0}
    static = rows.loc[rows["행"] == STATIC_ROW]
    assert dict(zip(static["공정"], static["대수"], strict=True)) == {"다른_공정": 5.0}
    assert GAP_ROW not in gap_matrix(rows, PROCESS).index


def test_only_the_process_on_both_sides_gets_a_gap_row() -> None:
    monthly = pd.concat(
        [monthly_for(3), monthly_for(2).assign(공정="설비만_공정")], ignore_index=True
    )
    static = pd.DataFrame(
        {"생산계획년월": MONTHS * 2, "공정": [PROCESS, "기준정보만_공정"], "가용대수": [4.0, 9.0]}
    )

    comparison = build_availability_gap(monthly, static, MONTHS)

    gaps = comparison.rows.loc[comparison.rows["행"] == GAP_ROW]
    assert dict(zip(gaps["공정"], gaps["대수"], strict=True)) == {PROCESS: -1.0}
    assert comparison.dynamic_only == ["설비만_공정"]
    assert comparison.static_only == ["기준정보만_공정"]


def test_static_rows_for_the_same_month_are_added_up() -> None:
    """기준정보 편집이 같은 월·공정을 두 줄로 쪼개 놓았을 수 있다."""
    split = pd.DataFrame(
        {"생산계획년월": MONTHS * 2, "공정": [PROCESS] * 2, "가용대수": [7.0, 5.0]}
    )

    comparison = build_availability_gap(monthly_for(0), split, MONTHS)

    assert value_of(comparison.rows, STATIC_ROW) == 12.0


def test_months_outside_the_request_are_dropped() -> None:
    other = pd.DataFrame(
        {"생산계획년월": [202601, *MONTHS], "공정": [PROCESS] * 2, "가용대수": [99.0, 1.0]}
    )

    comparison = build_availability_gap(monthly_for(2), other, MONTHS)

    assert 202601 not in set(comparison.rows["생산계획년월"])
    assert value_of(comparison.rows, GAP_ROW) == 1.0


def test_static_only_outside_the_request_leaves_the_process_one_sided() -> None:
    """조회 달에 Static 이 없으면 그 공정은 Dynamic 에만 있는 공정이다 — GAP 을 내지 않는다."""
    other = pd.DataFrame({"생산계획년월": [202601], "공정": [PROCESS], "가용대수": [99.0]})

    comparison = build_availability_gap(monthly_for(2), other, MONTHS)

    assert comparison.dynamic_only == [PROCESS]
    assert comparison.rows.loc[comparison.rows["행"] == GAP_ROW].empty


def test_the_matrix_puts_months_in_columns_and_orders_the_rows() -> None:
    comparison = build_availability_gap(monthly_for(8), static_for(12.0), MONTHS)

    matrix = gap_matrix(comparison.rows, PROCESS)

    assert list(matrix.columns) == ["202610"]
    # 환산 소계는 GAP **아래**다 — GAP 계산에 들어가지 않는다는 것을 자리로도 보인다.
    assert list(matrix.index)[-4:] == [
        DYNAMIC_SUBTOTAL_ROW,
        STATIC_ROW,
        GAP_ROW,
        DYNAMIC_WEIGHTED_ROW,
    ]
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


def test_a_blank_cutoff_row_is_dropped_not_refused() -> None:
    """화면이 공정 목록으로 빈 행을 한꺼번에 만든다 — 거부하면 아무것도 저장할 수 없다."""
    partly_filled = pd.DataFrame(
        {
            "공정": ["Die Attach", "Mold", "Saw"],
            "Cutoff일수": [15.0, None, float("nan")],
            "비고": [None, None, None],
        }
    )

    prepared = prepare_process_cutoff(partly_filled)

    assert list(prepared["공정"]) == ["Die Attach"]
    assert list(prepared["Cutoff일수"]) == [15.0]


def test_a_non_numeric_cutoff_is_still_refused() -> None:
    """적었는데 숫자가 아니면 막는다. 조용히 빠지면 적었다고 믿는 값이 사라진다."""
    typo = pd.DataFrame({"공정": ["Die Attach"], "Cutoff일수": ["열닷새"], "비고": [None]})

    with pytest.raises(ValueError, match="숫자가 아닙니다"):
        prepare_process_cutoff(typo)


def test_a_table_of_only_blank_rows_saves_as_empty() -> None:
    blanks = pd.DataFrame({"공정": ["A", "B"], "Cutoff일수": [None, None], "비고": [None, None]})

    assert prepare_process_cutoff(blanks).empty


def test_the_weighted_subtotal_is_reported_but_left_out_of_the_gap() -> None:
    """환산 소계는 보이되 GAP 에 안 들어간다 — Static 은 대수라 단위가 어긋난다."""
    spans = pd.DataFrame(
        {
            "호기": ["EQ-1"],
            "공정소분류": [PROCESS],
            "상태": ["가용"],
            "시작일": [date(2020, 1, 1)],
            "종료일": [date(2030, 1, 1)],
        }
    )
    baseline = pd.DataFrame(
        {"공정": pd.Series(dtype="string"), "기존보유대수": pd.Series(dtype="float64")}
    )
    cutoff = prepare_process_cutoff(
        pd.DataFrame({"공정": [PROCESS], "Cutoff일수": [0.0], "비고": [None]})
    )
    monthly = build_monthly_equipment_availability(
        spans, baseline, cutoff, MONTHS, conversion_ratios={"EQ-1": 1.5}
    )

    comparison = build_availability_gap(monthly, static_for(4.0), MONTHS)
    matrix = gap_matrix(comparison.rows, PROCESS)

    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "202610"] == 1.0
    assert matrix.loc[DYNAMIC_WEIGHTED_ROW, "202610"] == 1.5
    # GAP 은 대수끼리다: 1.0 - 4.0 = -3.0 (환산 1.5 를 쓰면 -2.5 가 되어 틀린다)
    assert matrix.loc[GAP_ROW, "202610"] == -3.0


def test_a_month_the_static_side_has_no_data_for_gets_no_gap() -> None:
    """설비 조회기간이 시나리오보다 넓은 달은 Static 자료가 아예 없다 — GAP 을 내지 않는다.

    이름이 맞는 공정이라도 그 달 Static 표에 어느 공정도 없으면 「대수 없음」이 아니라 「맞댈
    자료 없음」이다(2026-10-01 최종 재점검: 시나리오 밖 달에 GAP = +Dynamic 이 찍혔다).
    """
    months = [202610, 202611]
    spans = pd.DataFrame(
        {
            "호기": ["EQ-0", "EQ-1"],
            "공정소분류": [PROCESS, PROCESS],
            "상태": ["가용", "가용"],
            "시작일": [date(2020, 1, 1)] * 2,
            "종료일": [date(2030, 1, 1)] * 2,
        }
    )
    baseline = pd.DataFrame(
        {"공정": pd.Series(dtype="string"), "기존보유대수": pd.Series(dtype="float64")}
    )
    cutoff_table = prepare_process_cutoff(
        pd.DataFrame({"공정": [PROCESS], "Cutoff일수": [0.0], "비고": [None]})
    )
    monthly = build_monthly_equipment_availability(spans, baseline, cutoff_table, months)
    static = pd.DataFrame({"생산계획년월": [202610], "공정": [PROCESS], "가용대수": [5.0]})

    comparison = build_availability_gap(monthly, static, months)

    gap = comparison.rows.loc[comparison.rows["행"] == GAP_ROW]
    assert set(gap["생산계획년월"]) == {202610}
    assert float(gap["대수"].iloc[0]) == -3.0
