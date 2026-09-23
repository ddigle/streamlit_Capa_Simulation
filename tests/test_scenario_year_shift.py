# Purpose: 연도 Shift의 달력 경계·입력 검증과 원본 및 월 없는 기준정보 보존을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES
from capa_simulation.services.scenario_year_shift import shift_scenario_years


def _tables(months: list[int] | None = None) -> dict[str, pd.DataFrame]:
    selected = [202701, 202712, 202801] if months is None else months
    tables = {
        name: pd.DataFrame(
            {
                "생산계획년월": pd.Series(selected, dtype="int64"),
                "기준정보년월": [202601] * len(selected),
                "분류": pd.Series(["값 유지"] * len(selected), dtype="string"),
                "값": pd.Series([1.25] * len(selected), dtype="Float64"),
            }
        )
        for name in MONTHLY_TABLES
    }
    tables.update(
        {
            name: pd.DataFrame(
                {
                    "분류": pd.Series(["첫 값", None], dtype="string"),
                    "값": pd.Series([7.5, None], dtype="Float64"),
                }
            )
            for name in NON_MONTHLY_TABLES
        }
    )
    return tables


@pytest.mark.parametrize(
    ("years", "expected"),
    [
        (1, [202801, 202812, 202901]),
        (-2, [202501, 202512, 202601]),
        (0, [202701, 202712, 202801]),
        (17, [204401, 204412, 204501]),
    ],
)
def test_shifts_every_monthly_table_and_keeps_month_numbers(
    years: int, expected: list[int]
) -> None:
    original = _tables()

    result = shift_scenario_years(original, years)

    assert len(result) == 16
    for name in MONTHLY_TABLES:
        assert result[name]["생산계획년월"].tolist() == expected
        pd.testing.assert_frame_equal(
            result[name].drop(columns="생산계획년월"),
            original[name].drop(columns="생산계획년월"),
        )
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(result[name], original[name])


@pytest.mark.parametrize(
    ("months", "years", "expected"),
    [
        ([201, 212], -1, [101, 112]),
        ([999801, 999812], 1, [999901, 999912]),
        ([101, 999912], 0, [101, 999912]),
    ],
)
def test_accepts_full_calendar_year_boundaries(
    months: list[int], years: int, expected: list[int]
) -> None:
    result = shift_scenario_years(_tables(months), years)

    assert result["RQ_PKG_PLAN"]["생산계획년월"].tolist() == expected


@pytest.mark.parametrize(
    ("month", "years"),
    [
        (101, -1),
        (999912, 1),
        (202701, 10**100),
        (202701, -(10**100)),
    ],
)
def test_rejects_out_of_range_result_with_the_table_name(month: int, years: int) -> None:
    tables = _tables([])
    tables["RQ_UPEH"] = _tables([month])["RQ_UPEH"]

    with pytest.raises(ValueError, match="RQ_UPEH.*YYYYMM"):
        shift_scenario_years(tables, years)


@pytest.mark.parametrize("years", [True, False, 1.0, 0.5, "1", None])
def test_rejects_non_integer_and_boolean_shift(years: object) -> None:
    with pytest.raises(ValueError, match="연도 이동량은 정수"):
        shift_scenario_years(_tables(), years)  # type: ignore[arg-type]


def test_result_is_independent_of_input_frames_on_success() -> None:
    tables = _tables()
    originals = {name: frame.copy(deep=True) for name, frame in tables.items()}

    shifted = shift_scenario_years(tables, 1)
    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, originals[name])
        assert shifted[name] is not frame
    shifted["RQ_CHIP_QTY"].loc[0, "값"] = 42
    shifted["RQ_PKG_PLAN"].loc[0, "값"] = 42

    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, originals[name])


def test_input_is_unchanged_when_a_later_table_fails() -> None:
    tables = _tables()
    tables["RQ_WF_RATIO"]["생산계획년월"] = [999901, 999910, 999912]
    originals = {name: frame.copy(deep=True) for name, frame in tables.items()}

    with pytest.raises(ValueError, match="RQ_WF_RATIO.*YYYYMM"):
        shift_scenario_years(tables, 1)

    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, originals[name])


def test_normalizes_input_months_without_rewriting_the_original() -> None:
    tables = _tables([202701, 202712])
    tables["RQ_PKG_PLAN"]["생산계획년월"] = pd.Series(["202701", 202712.0], dtype="object")
    original = tables["RQ_PKG_PLAN"].copy(deep=True)

    shifted = shift_scenario_years(tables, 1)

    assert shifted["RQ_PKG_PLAN"]["생산계획년월"].tolist() == [202801, 202812]
    pd.testing.assert_frame_equal(tables["RQ_PKG_PLAN"], original)


def test_shift_preserves_different_month_sets_and_empty_tables() -> None:
    tables = _tables()
    tables["RQ_YLD"] = tables["RQ_YLD"].iloc[[1]].copy()
    tables["RQ_RUN_DAY"] = tables["RQ_RUN_DAY"].iloc[:0].copy()

    shifted = shift_scenario_years(tables, -1)

    assert shifted["RQ_YLD"]["생산계획년월"].tolist() == [202612]
    pd.testing.assert_frame_equal(shifted["RQ_RUN_DAY"], tables["RQ_RUN_DAY"])


def test_rejects_invalid_source_month_instead_of_repairing_it() -> None:
    tables = _tables()
    tables["RQ_UPEH"]["생산계획년월"] = [202700, 202713, 202801]

    with pytest.raises(ValueError, match="RQ_UPEH.*YYYYMM"):
        shift_scenario_years(tables, 1)
