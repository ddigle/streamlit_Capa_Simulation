import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    build_monthly_volume,
    plan_from_edit_table,
    plan_to_edit_table,
)
from capa_simulation.settings import APP_NAME


def test_app_name() -> None:
    assert APP_NAME == "HBM PKG Capa Simulation"


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
    detailed_chip = build_monthly_volume(
        plan, yield_data, chip_qty, "Chip", detailed=True
    )
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
    wide_plan.loc[0, "202609"] = 250.0
    edited_plan = plan_from_edit_table(wide_plan)

    result = build_monthly_volume(
        edited_plan,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="PKG",
    )

    assert result.loc[0, "202608"] == pytest.approx(100.0)
    assert result.loc[0, "202609"] == pytest.approx(250.0)
