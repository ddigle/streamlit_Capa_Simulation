# Purpose: 서비스 공용 컬럼 계약 검증과 업무 키 정규화 규칙을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.frame_contracts import (
    AREA_NAMES,
    DEMAND_BASES,
    normalize_area_name,
    normalize_demand_basis,
    normalize_demand_basis_value,
    require_columns,
    validate_demand_basis,
)


def test_require_columns_reports_every_missing_column_in_order() -> None:
    data = pd.DataFrame({"공정": ["P"], "소요기준": ["WF"]})

    require_columns(data, ["공정", "소요기준"], "RQ_REQB")

    with pytest.raises(ValueError, match=r"RQ_REQB 필수 컬럼이 없습니다: 생산계획년월, 제품정보"):
        require_columns(data, ["공정", "생산계획년월", "제품정보"], "RQ_REQB")


def test_demand_basis_normalization_absorbs_case_whitespace_and_wafer_alias() -> None:
    values = pd.Series(["  wf ", "WAFER", "wafer", "Chip", "pkg"])

    assert normalize_demand_basis(values).tolist() == ["WF", "WF", "WF", "CHIP", "PKG"]
    assert set(DEMAND_BASES) == {"PKG", "CHIP", "WF"}


def test_demand_basis_normalization_passes_unsupported_values_through() -> None:
    """BOX·PCB가 섞인 원천도 정규화만 하고 통과시켜야 하는 경로가 있다."""
    values = pd.Series([" box ", "PCB"])

    assert normalize_demand_basis(values).tolist() == ["BOX", "PCB"]


def test_demand_basis_validation_rejects_unsupported_values_with_examples() -> None:
    values = pd.Series(["WF", "BOX", "PCB"])

    with pytest.raises(ValueError, match=r"RQ_UPEH에 지원하지 않는 소요기준이 있습니다"):
        validate_demand_basis(values, "RQ_UPEH")

    assert validate_demand_basis(pd.Series([" wafer "]), "RQ_UPEH").tolist() == ["WF"]


def test_demand_basis_scalar_matches_the_series_rule() -> None:
    for raw, expected in ((" wafer ", "WF"), ("WAFER", "WF"), ("chip", "CHIP"), ("PKG", "PKG")):
        assert normalize_demand_basis_value(raw) == expected
        assert normalize_demand_basis(pd.Series([raw])).tolist() == [expected]


def test_area_name_normalization_unifies_case_and_whitespace() -> None:
    values = pd.Series([" main", "MAIN", "mi", " Mi "])

    assert normalize_area_name(values, "RQ_UPEH").tolist() == ["Main", "Main", "MI", "MI"]
    assert AREA_NAMES == ("Main", "MI")


def test_area_name_normalization_rejects_other_values_and_nulls() -> None:
    with pytest.raises(ValueError, match=r"RQ_UPEH의 Area_Name은 Main 또는 MI여야 합니다"):
        normalize_area_name(pd.Series(["Main", "TEST"]), "RQ_UPEH")

    with pytest.raises(ValueError, match=r"RQ_UPEH의 Area_Name은 Main 또는 MI여야 합니다"):
        normalize_area_name(pd.Series(["Main", None]), "RQ_UPEH")
