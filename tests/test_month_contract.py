# Purpose: 입력·저장·계산·조회 경계가 같은 YYYYMM 계약과 각자의 반환·빈값 정책을 지키는지 검증한다.

from collections.abc import Callable

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import _validate_production_month, normalize_core_data
from capa_simulation.persistence._sql_helpers import normalize_months
from capa_simulation.services.frame_contracts import normalize_month_column
from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
    valid_month_mask,
)


def _normalize_frame(values: pd.Series) -> None:
    normalize_month_column(values.to_frame(name="생산계획년월"), "RQ_TEST")


BOUNDARIES: tuple[tuple[Callable[[pd.Series], object], str], ...] = (
    (_validate_production_month, "Core Data 생산계획년월은 유효한 YYYYMM 정수여야 합니다."),
    (
        lambda values: normalize_months(values, "RQ_TEST"),
        "RQ_TEST의 생산계획년월은 YYYYMM 형식이어야 합니다.",
    ),
    (_normalize_frame, "RQ_TEST의 생산계획년월은 YYYYMM 형식이어야 합니다."),
    (
        lambda values: available_month_range(values.to_frame(name="생산계획년월"), "RQ_TEST"),
        "RQ_TEST의 생산계획년월은 YYYYMM 형식이어야 합니다:",
    ),
)


@pytest.mark.parametrize(("validate", "message"), BOUNDARIES)
@pytest.mark.parametrize(
    "invalid",
    [
        1,
        -99,
        1000001,
        100,
        202600,
        202613,
        202601.5,
        "abc",
        "",
        None,
        pd.NA,
        float("nan"),
        float("inf"),
        -float("inf"),
        1e100,
        2**64,
    ],
)
def test_all_month_boundaries_reject_invalid_calendar_values_before_integer_cast(
    validate: Callable[[pd.Series], object], message: str, invalid: object
) -> None:
    values = pd.Series([202601, invalid], index=[8, 3], dtype=object)

    with pytest.raises(ValueError) as error:
        validate(values)

    assert str(error.value).startswith(message)


def test_calendar_limits_and_values_outside_the_ui_range_remain_valid() -> None:
    values = pd.Series(["101", 999912.0, 200001, "203112"], index=[8, 3, 8, 2], name="month")
    original = values.copy()
    expected = pd.Series([101, 999912, 200001, 203112], index=values.index, name=values.name)

    assert _validate_production_month(values) is None
    pd.testing.assert_series_equal(normalize_months(values, "RQ_TEST"), expected)
    data = values.to_frame(name="월")
    assert normalize_month_column(data, "RQ_TEST", column="월") is None
    pd.testing.assert_series_equal(data["월"], expected.rename("월"))
    assert available_month_range(values.to_frame(name="생산계획년월"), "RQ_TEST") == (101, 999912)
    pd.testing.assert_series_equal(values, original)


def test_nullable_mask_preserves_index_and_marks_missing_values_false() -> None:
    values = pd.Series([101, pd.NA, 999912, 1000001], index=[4, 2, 4, 1], dtype="Int64")

    result = valid_month_mask(values)

    assert result.index.equals(values.index)
    assert result.tolist() == [True, False, True, False]
    assert not result.isna().any()


def test_valid_nullable_months_keep_the_existing_int64_result_dtype() -> None:
    values = pd.Series([101, 999912], index=[9, 2], dtype="Int64", name="생산계획년월")
    expected = values.astype("int64")

    pd.testing.assert_series_equal(normalize_months(values, "RQ_TEST"), expected)
    data = values.to_frame()
    normalize_month_column(data, "RQ_TEST")
    pd.testing.assert_series_equal(data["생산계획년월"], expected)


def test_empty_input_policy_belongs_to_each_boundary() -> None:
    values = pd.Series([], dtype="Int64", name="생산계획년월")

    assert _validate_production_month(values) is None
    pd.testing.assert_series_equal(normalize_months(values, "RQ_TEST"), values.astype("int64"))
    data = values.to_frame()
    normalize_month_column(data, "RQ_TEST")
    assert str(data["생산계획년월"].dtype) == "int64"
    with pytest.raises(ValueError, match="RQ_TEST에 선택할 생산계획년월 데이터가 없습니다"):
        available_month_range(data, "RQ_TEST")


def test_invalid_month_does_not_partially_mutate_the_frame() -> None:
    data = pd.DataFrame({"월": [202601, -99], "value": [1, 2]}, index=[7, 3])
    original = data.copy()

    with pytest.raises(ValueError, match="RQ_TEST의 월은 YYYYMM 형식이어야 합니다"):
        normalize_month_column(data, "RQ_TEST", column="월")

    pd.testing.assert_frame_equal(data, original)


@pytest.mark.parametrize("invalid", [202601.5, float("inf"), -99, 1000001])
def test_filter_boundaries_require_whole_calendar_months(invalid: object) -> None:
    data = pd.DataFrame({"생산계획년월": [202601]})

    with pytest.raises(ValueError, match="시작년월은 YYYYMM 형식이어야 합니다"):
        filter_month_range(data, invalid, 202612, "RQ_TEST")
    with pytest.raises(ValueError, match="종료년월은 YYYYMM 형식이어야 합니다"):
        filter_month_range(data, 202601, invalid, "RQ_TEST")


@pytest.mark.parametrize("invalid", [1, -99, 1000001, 1e100, 2**64])
def test_core_data_rejects_invalid_month_before_nullable_integer_conversion(
    invalid: object,
) -> None:
    from test_core_data_pipeline import _core_data_row

    source = _core_data_row()
    source["생산계획년월"] = pd.Series([invalid], dtype=object)

    with pytest.raises(ValueError, match="Core Data 생산계획년월은 유효한 YYYYMM 정수"):
        normalize_core_data(source)


@pytest.mark.parametrize("month", [101, 999912])
def test_core_data_keeps_nullable_integer_month_dtype(month: int) -> None:
    from test_core_data_pipeline import _core_data_row

    source = _core_data_row()
    source["생산계획년월"] = [month]

    normalized = normalize_core_data(source)

    assert normalized["생산계획년월"].tolist() == [month]
    assert str(normalized["생산계획년월"].dtype) == "Int64"
