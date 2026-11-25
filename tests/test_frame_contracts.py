# Purpose: 서비스 공용 컬럼 계약 검증·업무 키 정규화·빈칸 판정 규칙을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.frame_contracts import (
    AREA_NAMES,
    DEMAND_BASES,
    UNIMPLEMENTED_BASES,
    UnimplementedProcess,
    assert_complete,
    blank_cell,
    normalize_area_name,
    normalize_demand_basis,
    normalize_demand_basis_value,
    normalize_month_column,
    require_columns,
    to_numeric_strict,
    unimplemented_basis_processes,
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


def test_unimplemented_bases_have_one_owner_shared_by_both_calculations() -> None:
    """대당 Capa 와 소요대수가 같은 소요기준을 빼야 한다. 사본이 생기면 한쪽만 고쳐 갈라진다."""
    from capa_simulation.services import reference_consistency, required_equipment, unit_capacity

    assert set(UNIMPLEMENTED_BASES) == {"BOX", "PCB"}
    assert not set(UNIMPLEMENTED_BASES) & set(DEMAND_BASES)
    for module in (unit_capacity, required_equipment, reference_consistency):
        assert module.UNIMPLEMENTED_BASES is UNIMPLEMENTED_BASES


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


def test_month_column_normalization_accepts_valid_yyyymm_and_rejects_others() -> None:
    data = pd.DataFrame({"생산계획년월": ["202608", 202612.0]})

    normalize_month_column(data, "RQ_PKG_PLAN")

    assert data["생산계획년월"].tolist() == [202608, 202612]

    for invalid in (["202613"], ["2026"], ["abc"], [None]):
        with pytest.raises(ValueError, match=r"생산계획년월은 YYYYMM 형식이어야 합니다"):
            normalize_month_column(pd.DataFrame({"생산계획년월": invalid}), "RQ_PKG_PLAN")


def test_assert_complete_rejects_nulls_and_blank_strings() -> None:
    assert_complete(
        pd.DataFrame({"공정": ["P"], "제품정보": ["A"]}), ["공정", "제품정보"], "RQ_REQB"
    )

    for broken in ({"공정": [None]}, {"공정": [""]}, {"공정": ["  "]}):
        frame = pd.DataFrame(broken)
        frame["공정"] = frame["공정"].astype("string").str.strip()
        with pytest.raises(ValueError, match=r"RQ_REQB의 필수 연결 키에 누락값이 있습니다"):
            assert_complete(frame, ["공정"], "RQ_REQB")


def test_to_numeric_strict_rejects_both_text_and_missing_values() -> None:
    assert to_numeric_strict(pd.Series(["1.5", 2]), "부하량").tolist() == [1.5, 2.0]

    for invalid in (["abc"], [None]):
        with pytest.raises(ValueError, match=r"부하량에 숫자가 아닌 값 또는 누락값이 있습니다"):
            to_numeric_strict(pd.Series(invalid), "부하량")


def test_blank_cell_counts_only_missing_markers_not_empty_text() -> None:
    for missing in (None, pd.NA, pd.NaT, float("nan")):
        assert blank_cell(missing)
    for present in (
        "",
        " ",
        "nan",
        0,
        0.0,
        -1.5,
        float("inf"),
        False,
        (),
        pd.Timestamp("2026-05-01"),
    ):
        assert not blank_cell(present)


def test_unimplemented_basis_processes_lists_box_and_pcb_routes_in_the_period() -> None:
    """계산 밖 공정은 조회기간 안 BOX · PCB 경로가 있는 공정이다. 표기만 다른 값(`box `)도 계산이
    버리는 꼴로 센다. 남은 경로(PKG · 빈 소요기준)와 섞인 공정은 `whole` 이 거짓이고, 기간 밖 경로는
    `whole` 판정에도 들지 않는다. 달을 못 읽는 행 · 공정이 빈 행은 세지 않고 멈추지도 않는다."""
    reqb = pd.DataFrame(
        {
            "생산계획년월": [
                202608,
                202608,
                202609,
                202612,
                202608,
                202609,
                202612,
                "2026-08",
                202608,
                202608,
                202608,
            ],
            "공정": [
                "DEMO_P1",
                "DEMO_BOX_A",
                " DEMO_BOX_A ",
                "DEMO_BOX_A",
                "DEMO_MIX",
                "DEMO_MIX",
                "DEMO_BOX_LATE",
                "DEMO_BOX_BAD",
                None,
                "DEMO_BLANK_BASIS",
                "DEMO_BLANK_BASIS",
            ],
            "소요기준": [
                "PKG",
                "box ",
                "PCB",
                "PKG",
                "PKG",
                " Box",
                "BOX",
                "BOX",
                "PCB",
                "BOX",
                None,
            ],
        }
    )
    before = reqb.copy()

    listed = unimplemented_basis_processes(reqb, start_month=202608, end_month=202609)

    assert listed == (
        UnimplementedProcess(process="DEMO_BOX_A", bases=("BOX", "PCB"), whole=True),
        UnimplementedProcess(process="DEMO_MIX", bases=("BOX",), whole=False),
        UnimplementedProcess(process="DEMO_BLANK_BASIS", bases=("BOX",), whole=False),
    )
    pd.testing.assert_frame_equal(reqb, before)
    assert unimplemented_basis_processes(reqb.iloc[:0], start_month=202608, end_month=202609) == ()
    counted_only = reqb.loc[reqb["공정"].eq("DEMO_P1")]
    assert unimplemented_basis_processes(counted_only, start_month=202608, end_month=202609) == ()
    assert unimplemented_basis_processes(reqb, start_month=202610, end_month=202611) == ()
    with pytest.raises(ValueError, match=r"RQ_REQB 필수 컬럼이 없습니다: 소요기준"):
        unimplemented_basis_processes(
            reqb.drop(columns="소요기준"), start_month=202608, end_month=202609
        )
