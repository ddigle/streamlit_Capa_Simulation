import pandas as pd
import pytest

from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.dashboard import (
    build_monthly_bottlenecks,
    build_production_dashboard,
)
from capa_simulation.services.equipment_count import build_equipment_count_table
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    build_monthly_volume,
    plan_from_edit_table,
    plan_to_edit_table,
    yield_from_edit_table,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import (
    available_month_range,
    filter_month_range,
)
from capa_simulation.services.required_equipment import (
    RESULT_DIMENSIONS,
    calculate_required_equipment,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import (
    calculate_securement_rate,
    securement_rate_to_month_table,
)
from capa_simulation.services.unit_capacity import (
    UNIT_CAPACITY_DIMENSIONS,
    calculate_unit_capacity,
    unit_capacity_to_month_table,
)
from capa_simulation.settings import APP_NAME


def test_app_name() -> None:
    assert APP_NAME == "🏭S.PKG Capa Simulation"


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

    edited_plan = plan_from_edit_table(wide_plan)
    assert len(edited_plan) == 2
    assert edited_plan["생산수량"].gt(0).all()

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


def test_production_dashboard_groups_density_by_product_and_stack() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609],
            "양산구분": ["양산", "ER", "양산"],
            "제품정보": ["HBM다E", "HBM다E", "HBM다E"],
            "Stack": ["12H", "12H", "12H"],
            "생산수량": [100.0, 50.0, 200.0],
        }
    )
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )

    monthly, detail = build_production_dashboard(plan, density_data)

    assert monthly["년월"].tolist() == ["26.08", "26.09"]
    assert monthly["부하량"].tolist() == pytest.approx(
        [150 * 11 * 24 / 100_000, 200 * 11 * 24 / 100_000]
    )
    assert list(detail.columns) == ["제품정보", "Stack", "26.08", "26.09"]
    assert detail.loc[0, "26.08"] == pytest.approx(150 * 11 * 24 / 100_000)


def test_dashboard_selects_lowest_monthly_securement_process() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609, 202609],
            "공정": ["Process-B", "Process-A", "Process-C", "Process-D"],
            "확보율": [0.8, 0.8, 1.2, 0.9],
        }
    )

    result = build_monthly_bottlenecks(securement)

    assert result["년월"].tolist() == ["26.08", "26.09"]
    assert result["공정"].tolist() == ["Process-A", "Process-D"]
    assert result["확보율"].tolist() == pytest.approx([0.8, 0.9])
    assert result["축레이블"].tolist() == [
        "26.08<br>Process-A",
        "26.09<br>Process-D",
    ]


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


def test_workbook_display_order_supports_custom_and_ascending_rules() -> None:
    data = pd.DataFrame(
        {
            "양산구분": ["ER", "양산", "양산", "양산"],
            "제품정보": ["제품B", "제품B", "제품A", "제품A"],
            "Capa Code": ["Z", "B", "C", "A"],
        }
    )
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 5,
            "탭 구분": ["PKG PLAN"] * 5,
            "정렬우선순위": [1, 1, 2, 2, 3],
            "분류컬럼": ["양산구분", "양산구분", "제품정보", "제품정보", "Capa Code"],
            "정렬방식": ["사용자지정", "사용자지정", "사용자지정", "사용자지정", "오름차순"],
            "분류값": ["양산", "ER", "제품A", "제품B", None],
            "값표시순서": [1, 2, 1, 2, None],
            "활성여부": ["Y", "Y", "Y", "Y", "Y"],
        }
    )

    result = apply_display_order(data, display_order, "부하량", "PKG PLAN")

    assert result[["양산구분", "제품정보", "Capa Code"]].to_dict("records") == [
        {"양산구분": "양산", "제품정보": "제품A", "Capa Code": "A"},
        {"양산구분": "양산", "제품정보": "제품A", "Capa Code": "C"},
        {"양산구분": "양산", "제품정보": "제품B", "Capa Code": "B"},
        {"양산구분": "ER", "제품정보": "제품B", "Capa Code": "Z"},
    ]


def test_month_range_uses_only_the_intersection_with_source_data() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608, 202701, 202712],
            "생산수량": [10.0, 20.0, 30.0, 40.0],
        }
    )

    assert available_month_range(plan, "RQ_PKG_PLAN") == (202607, 202712)
    narrow = filter_month_range(plan, 202607, 202612, "RQ_PKG_PLAN")
    wide = filter_month_range(plan, 202605, 202812, "RQ_PKG_PLAN")

    assert narrow["생산계획년월"].tolist() == [202607, 202608]
    assert wide["생산계획년월"].tolist() == [202607, 202608, 202701, 202712]


def test_unit_capacity_uses_upeh_for_main_and_converted_st_for_mi() -> None:
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "MI"],
            "소요기준": ["CHIP", "PKG"],
            "공정": ["Process-A", "Process-B"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Core"],
            "UPEH": [100.0, None],
            "ST": [None, 36.0],
        }
    )
    detail_keys = ["생산계획년월", "공정", "양산구분", "제품정보", "Stack", "WF 구분"]
    shared_detail = upeh[detail_keys]
    run_rate = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(CAPA_RUN_RATE=0.8)
    vital = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(편중률=1.0)
    module = pd.DataFrame({"공정": ["Process-A", "Process-B"], "모듈수": [2.0, 2.0]})
    run_day = shared_detail[["생산계획년월", "공정"]].assign(RUN_DAY=30.0)
    lot_ratio = shared_detail.assign(**{"Lot 측정률": 1.0})
    wf_ratio = shared_detail.assign(WF측정률=1.0)

    result = calculate_unit_capacity(upeh, run_rate, vital, module, run_day, lot_ratio, wf_ratio)

    assert result.loc[result["Area_Name"].eq("Main"), "대당 Capa"].iloc[0] == pytest.approx(
        (100 / 1000) * 24 * 0.8 * 2 * 30
    )
    assert result.loc[result["Area_Name"].eq("MI"), "대당 Capa"].iloc[0] == pytest.approx(
        ((3600 / 36) / 1000) * 24 * 0.8 * 2 * 30
    )


def test_unit_capacity_excludes_unimplemented_box_and_pcb_bases() -> None:
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "MI"],
            "소요기준": ["BOX", "pcb"],
            "공정": ["Process-A", "Process-B"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Core"],
            "UPEH": [100.0, None],
            "ST": [None, 36.0],
        }
    )

    result = calculate_unit_capacity(
        upeh,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    table = unit_capacity_to_month_table(result)

    assert result.empty
    assert list(table.columns) == UNIT_CAPACITY_DIMENSIONS


def test_required_equipment_aggregates_reqb_rows_after_calculation() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "Main"],
            "공정": ["Process-A", "Process-A"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-B"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "WF 구분": ["Core", "Core"],
            "STEP_SEQ": [10, 20],
            "MCP_SEQ": [1, 1],
            "소요기준": ["chip", "CHIP"],
        }
    )
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-B"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "생산수량": [60.0, 40.0],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "EDS_수율": [0.8],
            "BE_수율": [0.5],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [2.0],
            "Net Die": [500.0],
        }
    )
    unit_capacity = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "소요기준": ["Chip"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "대당 Capa": [200.0],
        }
    )

    result = calculate_required_equipment(reqb, plan, yield_data, chip_qty, unit_capacity)
    table = required_equipment_to_month_table(result)

    assert len(result) == 2
    assert result["부하량"].tolist() == pytest.approx([240.0, 160.0])
    assert result["소요대수"].tolist() == pytest.approx([1.2, 0.8])
    assert len(table) == 1
    assert "Capa Code" not in table.columns
    assert "Customer" not in table.columns
    assert "CS" not in table.columns
    assert "STEP_SEQ" not in table.columns
    assert "MCP_SEQ" not in table.columns
    assert table.loc[0, "202608"] == pytest.approx(2.0)


def test_required_equipment_uses_zero_when_load_is_missing() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-B"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["PKG"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
            "소요기준": ["PKG"],
        }
    )
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "생산수량": [100.0],
        }
    )
    unit_capacity = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "소요기준": ["PKG"],
            "양산구분": ["양산"],
            "제품정보": ["Product-B"],
            "Stack": ["12H"],
            "WF 구분": ["PKG"],
            "대당 Capa": [10.0],
        }
    )

    result = calculate_required_equipment(
        reqb, plan, pd.DataFrame(), pd.DataFrame(), unit_capacity
    )

    assert result.loc[0, "부하량"] == 0
    assert result.loc[0, "소요대수"] == 0


def test_required_equipment_excludes_unimplemented_box_and_pcb_bases() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "Main"],
            "공정": ["Process-A", "Process-B"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-A"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "WF 구분": ["Core", "Core"],
            "STEP_SEQ": [10, 20],
            "MCP_SEQ": [1, 1],
            "소요기준": ["BOX", "pcb"],
        }
    )

    result = calculate_required_equipment(
        reqb,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    table = required_equipment_to_month_table(result)

    assert result.empty
    assert list(table.columns) == RESULT_DIMENSIONS


def test_required_equipment_recognizes_wf_as_wafer_basis() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["Core"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
            "소요기준": ["WF"],
        }
    )
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "생산수량": [100.0],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "EDS_수율": [0.8],
            "BE_수율": [1.0],
        }
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [2.0],
            "Net Die": [500.0],
        }
    )
    unit_capacity = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "소요기준": ["Wafer"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "대당 Capa": [25.0],
        }
    )

    result = calculate_required_equipment(reqb, plan, yield_data, chip_qty, unit_capacity)

    assert result.loc[0, "소요기준"] == "WF"
    assert result.loc[0, "부하량"] == pytest.approx(500.0)
    assert result.loc[0, "소요대수"] == pytest.approx(20.0)


def test_equipment_count_supports_available_summary_and_detailed_rows() -> None:
    own = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "설비보유": [10.0, 11.0],
        }
    )
    lent = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "설비대여평가": [2.0, 3.0],
        }
    )
    available = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "가용대수": [12.0, 14.0],
        }
    )

    summary = build_equipment_count_table(own, lent, available, detailed=False)
    detailed = build_equipment_count_table(own, lent, available, detailed=True)

    assert list(summary.columns) == ["공정", "202608", "202609"]
    assert summary.loc[0, "202608"] == pytest.approx(12.0)
    assert detailed["구분"].tolist() == ["보유", "대여", "가용"]
    assert detailed["202609"].tolist() == pytest.approx([11.0, 3.0, 14.0])


def test_securement_rate_uses_process_required_sum_and_available_equipment() -> None:
    available = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Pre B/D", "Pre B/D"],
            "가용대수": [10.0, 12.0],
        }
    )
    required = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609],
            "공정": ["Pre B/D", "Pre B/D", "Pre B/D"],
            "소요대수": [3.0, 2.0, 4.0],
        }
    )

    result = calculate_securement_rate(available, required)
    table = securement_rate_to_month_table(result)

    assert result["소요대수"].tolist() == pytest.approx([5.0, 4.0])
    assert table.loc[0, "202608"] == pytest.approx(2.0)
    assert table.loc[0, "202609"] == pytest.approx(3.0)


def test_securement_rate_is_blank_when_required_equipment_is_zero() -> None:
    available = pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Pre B/D"], "가용대수": [10.0]}
    )
    required = pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Pre B/D"], "소요대수": [0.0]}
    )

    result = calculate_securement_rate(available, required)

    assert pd.isna(result.loc[0, "확보율"])
