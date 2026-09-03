# Purpose: RQ_REQB 경로 연결과 STEP별 소요대수를 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.required_equipment import (
    CAPACITY_KEYS,
    RESULT_DIMENSIONS,
    calculate_required_equipment,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import calculate_securement_rate


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
            "STEP_SEQ": [10, 10],
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
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
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
    assert table["STEP_SEQ"].tolist() == ["10"]
    assert table["MCP_SEQ"].tolist() == ["1"]
    assert table.loc[0, "202608"] == pytest.approx(2.0)


def test_required_equipment_applies_dummy_loss_to_uppercase_wf_type() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Pre Bonder"],
            "양산구분": ["양산"],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["DUMMY"],
            "STEP_SEQ": ["P456"],
            "MCP_SEQ": ["1A"],
            "소요기준": ["CHIP"],
        }
    )
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "생산수량": [1831.6],
        }
    )
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "WF 구분": ["DUMMY"],
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
    unit_capacity = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Pre Bonder"],
            "STEP_SEQ": ["P456"],
            "MCP_SEQ": ["1A"],
            "소요기준": ["CHIP"],
            "양산구분": ["양산"],
            "제품정보": ["HBM4"],
            "Stack": ["12H"],
            "WF 구분": ["DUMMY"],
            "대당 Capa": [484.0],
        }
    )

    result = calculate_required_equipment(reqb, plan, yield_data, chip_qty, unit_capacity)

    expected_load = 1831.6 / 0.78 / 0.879 * (1 - 0.78)
    assert result["부하량"].tolist() == pytest.approx([expected_load])
    assert result["소요대수"].tolist() == pytest.approx([expected_load / 484.0])


def test_required_equipment_normalizes_area_name_before_capacity_join() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": [" MAIN "],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
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
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
            "소요기준": ["PKG"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["PKG"],
            "대당 Capa": [50.0],
        }
    )

    result = calculate_required_equipment(
        reqb,
        plan,
        pd.DataFrame(),
        pd.DataFrame(),
        unit_capacity,
    )

    assert result["Area_Name"].tolist() == ["Main"]
    assert result["소요대수"].tolist() == pytest.approx([2.0])
    assert result.attrs["excluded_required_equipment_rows"].empty
    securement = calculate_securement_rate(
        pd.DataFrame(
            {
                "생산계획년월": [202608],
                "공정": ["Process-A"],
                "가용대수": [4.0],
            }
        ),
        result,
    )
    assert securement["확보율"].tolist() == pytest.approx([2.0])


def test_required_equipment_increases_when_a_process_route_has_more_steps() -> None:
    reqb = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "Main"],
            "공정": ["Process-A", "Process-A"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["CAPA-A", "CAPA-A"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "WF 구분": ["PKG", "PKG"],
            "STEP_SEQ": [10, 20],
            "MCP_SEQ": [1, 1],
            "소요기준": ["PKG", "PKG"],
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
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "Main"],
            "공정": ["Process-A", "Process-A"],
            "STEP_SEQ": [10, 20],
            "MCP_SEQ": [1, 1],
            "소요기준": ["PKG", "PKG"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["PKG", "PKG"],
            "대당 Capa": [50.0, 50.0],
        }
    )

    result = calculate_required_equipment(
        reqb,
        plan,
        pd.DataFrame(),
        pd.DataFrame(),
        unit_capacity,
    )

    assert result["STEP_SEQ"].tolist() == ["10", "20"]
    assert result["부하량"].tolist() == pytest.approx([100.0, 100.0])
    assert result["소요대수"].tolist() == pytest.approx([2.0, 2.0])
    assert result["소요대수"].sum() == pytest.approx(4.0)


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
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
            "소요기준": ["PKG"],
            "양산구분": ["양산"],
            "제품정보": ["Product-B"],
            "Stack": ["12H"],
            "WF 구분": ["PKG"],
            "대당 Capa": [10.0],
        }
    )

    result = calculate_required_equipment(reqb, plan, pd.DataFrame(), pd.DataFrame(), unit_capacity)

    assert result.loc[0, "부하량"] == 0
    assert result.loc[0, "소요대수"] == 0


def test_required_equipment_excludes_rows_without_unit_capacity() -> None:
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

    empty_capacity = pd.DataFrame(columns=[*CAPACITY_KEYS, "대당 Capa"])
    result = calculate_required_equipment(
        reqb, plan, pd.DataFrame(), pd.DataFrame(), empty_capacity
    )
    excluded = result.attrs["excluded_required_equipment_rows"]

    assert result.empty
    assert excluded.loc[0, "부하량"] == pytest.approx(100.0)
    assert excluded.loc[0, "제외사유"] == "대당 Capa 없음"


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
    assert RESULT_DIMENSIONS[-2:] == ["STEP_SEQ", "MCP_SEQ"]


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
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": [10],
            "MCP_SEQ": [1],
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
