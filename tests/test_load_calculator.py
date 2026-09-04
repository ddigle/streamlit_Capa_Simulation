# Purpose: PKG·Chip·Wafer·Density 부하량 환산과 계획·수율 편집 왕복을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
    drop_unplanned_rows,
    filter_edp_plan,
    plan_from_edit_table,
    plan_to_edit_table,
    yield_from_edit_table,
    yield_to_edit_table,
)


def test_edp_filter_excludes_ddr_products_only_when_disabled() -> None:
    plan = pd.DataFrame(
        {
            "제품정보": ["HBM다E", "DDR5", "Mobile ddr", None],
            "생산수량": [100.0, 200.0, 300.0, 400.0],
        }
    )

    excluded = filter_edp_plan(plan, include_edp=False)
    included = filter_edp_plan(plan, include_edp=True)

    assert excluded["제품정보"].fillna("").tolist() == ["HBM다E", ""]
    assert included.equals(plan)


def test_monthly_pkg_and_wafer_volume() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["HBM라"],
            "Stack": ["12H"],
            "생산수량": [100.0],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "제품정보": ["HBM라", "HBM라"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Dummy"],
            "EDS_수율": [0.8, 0.8],
            "BE_수율": [0.9, 0.9],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["HBM라", "HBM라"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Dummy"],
            "구분_Chip": [11, 1],
            "Net Die": [500, 500],
        }
    )

    pkg = build_monthly_volume(plan, yield_data, chip_qty, "PKG")
    chip = build_monthly_volume(plan, yield_data, chip_qty, "Chip")
    wafer = build_monthly_volume(plan, yield_data, chip_qty, "Wafer")
    detailed_chip = build_monthly_volume(plan, yield_data, chip_qty, "Chip", detailed=True)
    detailed_pkg = build_monthly_volume(plan, yield_data, chip_qty, "PKG", detailed=True)

    assert pkg.loc[0, "202608"] == pytest.approx(100.0)
    expected_core_chip = 100 * 11 / 0.9
    expected_dummy_chip = 100 * 1 / 0.8 / 0.9 * (1 - 0.8)
    assert chip.loc[0, "202608"] == pytest.approx(expected_core_chip + expected_dummy_chip)
    expected_core = 100 * 1_000 * 11 / 0.8 / 0.9 / 500
    expected_dummy = 100 * 1_000 * 1 / 0.8 / 0.9 / 500 * (1 - 0.8)
    assert wafer.loc[0, "202608"] == pytest.approx(expected_core + expected_dummy)
    assert set(detailed_chip["WF 구분"]) == {"Core", "Dummy"}
    assert detailed_chip["202608"].sum() == pytest.approx(chip.loc[0, "202608"])
    assert detailed_pkg.loc[0, "WF 구분"] == "PKG"


def test_dummy_load_recognizes_uppercase_wf_type_with_outer_whitespace() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "생산수량": [1831.6],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "WF 구분": [" DUMMY "],
            "EDS_수율": [0.78],
            "BE_수율": [0.879],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "WF 구분": ["DUMMY"],
            "구분_Chip": [1.0],
            "Net Die": [100.0],
        }
    )

    chip_load, wafer_load = calculate_chip_and_wafer_loads(plan, yield_data, chip_qty)

    expected_chip_load = 1831.6 / 0.78 / 0.879 * (1 - 0.78)
    expected_wafer_load = expected_chip_load * 1_000 / 100.0
    assert chip_load.loc[0, "물량"] == pytest.approx(expected_chip_load)
    assert wafer_load.loc[0, "물량"] == pytest.approx(expected_wafer_load)


def test_chip_and_wafer_bundle_prepares_shared_base_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from capa_simulation.services import load_calculator

    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["HBM라"],
            "Stack": ["12H"],
            "생산수량": [100.0],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["HBM라"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "EDS_수율": [0.8],
            "BE_수율": [0.9],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["HBM라"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11],
            "Net Die": [500],
        }
    )
    original_prepare = load_calculator._prepare_load_base
    call_count = 0

    def counted_prepare(
        plan_data: pd.DataFrame,
        yield_frame: pd.DataFrame,
        chip_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return original_prepare(plan_data, yield_frame, chip_frame)

    monkeypatch.setattr(load_calculator, "_prepare_load_base", counted_prepare)
    chip, wafer = calculate_chip_and_wafer_loads(plan, yield_data, chip_qty)

    assert call_count == 1
    assert chip["물량"].sum() == pytest.approx(100 * 11 / 0.9)
    assert wafer["물량"].sum() == pytest.approx(100 * 1_000 * 11 / 0.8 / 0.9 / 500)


def test_edited_pkg_plan_recalculates_monthly_volume() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "양산구분": ["양산", "양산"],
            "CS": ["MP", "MP"],
            "제품정보": ["HBM라", "HBM라"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-A"],
            "Customer": ["Customer-A", "Customer-A"],
            "생산수량": [100.0, 120.0],
        }
    )
    wide_plan = plan_to_edit_table(plan)
    assert list(wide_plan.columns[: len(PLAN_EDITOR_DIMENSIONS)]) == [
        "양산구분",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "CS",
    ]
    wide_plan.loc[0, "202609"] = 250.25
    edited_plan = plan_from_edit_table(wide_plan)

    result = build_monthly_volume(
        edited_plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="PKG",
    )

    assert result.loc[0, "202608"] == pytest.approx(100.0)
    assert result.loc[0, "202609"] == pytest.approx(250.25)


def test_load_display_aggregates_internal_plan_detail_columns() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "양산구분": ["양산", "양산"],
            "제품정보": ["HBM라", "HBM라"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-B"],
            "Customer": ["Customer-A", "Customer-B"],
            "CS": ["MP", "MP"],
            "생산수량": [60.0, 40.0],
        }
    )

    result = build_monthly_volume(
        plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="PKG",
    )

    assert list(result.columns) == ["양산구분", "제품정보", "Stack", "202608"]
    assert result.loc[0, "202608"] == pytest.approx(100.0)


def test_sparse_pkg_plan_treats_missing_months_as_zero_demand() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608],
            "양산구분": ["양산", "양산"],
            "CS": ["MP", "MP"],
            "제품정보": ["HBM다E", "HBM라"],
            "Stack": ["12H", "8H"],
            "Capa Code": ["ABCD", "EFGH"],
            "Customer": ["others", "Customer-A"],
            "생산수량": [100.0, 200.0],
        }
    )

    wide_plan = plan_to_edit_table(plan)
    hbm_dae = wide_plan.loc[wide_plan["제품정보"].eq("HBM다E")].iloc[0]
    hbm_ra = wide_plan.loc[wide_plan["제품정보"].eq("HBM라")].iloc[0]

    assert hbm_dae["202607"] == pytest.approx(100.0)
    assert hbm_dae["202608"] == pytest.approx(0.0)
    assert hbm_ra["202607"] == pytest.approx(0.0)
    assert hbm_ra["202608"] == pytest.approx(200.0)

    # 편집 격자는 계획이 없는 달도 0 으로 들고 있어야 사용자가 다시 물량을 넣을 수 있다.
    # 계산에서 빼는 것은 drop_unplanned_rows 의 몫이다.
    edited_plan = plan_from_edit_table(wide_plan)
    assert len(edited_plan) == 4
    assert edited_plan["생산수량"].ge(0).all()
    assert len(drop_unplanned_rows(edited_plan)) == 2

    result = build_monthly_volume(
        edited_plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="PKG",
    )
    assert result["202607"].sum() == pytest.approx(100.0)
    assert result["202608"].sum() == pytest.approx(200.0)


def test_monthly_density_uses_capacity_bearing_chip_types() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "생산수량": [100.0],
        }
    )
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E", "HBM다E"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Top"],
            "구분_Chip": [11, 1],
            "구분_EQ": [24.0, 24.0],
        }
    )

    density = build_monthly_volume(
        plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="Density",
        density_data=density_data,
    )
    detailed_density = build_monthly_volume(
        plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="Density",
        detailed=True,
        density_data=density_data,
    )

    expected_density = 100 * (11 * 24 + 1 * 24) / 100_000
    assert density.loc[0, "202608"] == pytest.approx(expected_density)
    assert set(detailed_density["WF 구분"]) == {"Core", "Top"}
    assert detailed_density["202608"].sum() == pytest.approx(expected_density)


def test_edited_yield_recalculates_chip_volume() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "양산구분": ["양산", "양산"],
            "제품정보": ["HBM다E", "HBM다E"],
            "Stack": ["12H", "12H"],
            "생산수량": [100.0, 100.0],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "제품정보": ["HBM다E", "HBM다E"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Core"],
            "EDS_수율": [0.8, 0.8],
            "BE_수율": [0.9, 0.9],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11],
            "Net Die": [500],
        }
    )

    wide_yield = yield_to_edit_table(yield_data)
    assert list(wide_yield.columns[: len(YIELD_EDITOR_DIMENSIONS)]) == [
        "수율 구분",
        "제품정보",
        "Stack",
        "WF 구분",
    ]
    assert set(wide_yield["수율 구분"]) == {"BE", "EDS"}
    be_row = wide_yield["수율 구분"].eq("BE")
    wide_yield.loc[be_row, "202609"] = 0.5
    edited_yield = yield_from_edit_table(wide_yield)

    result = build_monthly_volume(
        plan,
        yield_data=edited_yield,
        chip_qty=chip_qty,
        demand_basis="Chip",
    )

    assert result.loc[0, "202608"] == pytest.approx(100 * 11 / 0.9)
    assert result.loc[0, "202609"] == pytest.approx(100 * 11 / 0.5)
