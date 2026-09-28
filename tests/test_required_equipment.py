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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER", "BUFFER"],
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
            "WF 구분": ["BUFFER", "BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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


# ------------------------------------------------------------------ 소요기준 PKG
# 사내 버그 보고(2026-09-28): 실제 `RQ_REQB` 의 PKG 행은 WF 구분에 `BUFFER` 같은 실제 분류값을
# 싣는다. 예전 픽스처는 REQB·대당 Capa 모두 `"PKG"` 로 맞춰 코드의 잘못된 가정을 가렸다.


def _pkg_reqb(*divisions: str) -> pd.DataFrame:
    count = len(divisions)
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * count,
            "Area_Name": ["Main"] * count,
            "공정": ["Process-A"] * count,
            "양산구분": ["양산"] * count,
            "제품정보": ["Product-A"] * count,
            "Stack": ["12H"] * count,
            "Capa Code": ["CAPA-A"] * count,
            "Customer": ["Customer-A"] * count,
            "CS": ["MP"] * count,
            "WF 구분": list(divisions),
            "STEP_SEQ": [10] * count,
            "MCP_SEQ": [1] * count,
            "소요기준": ["PKG"] * count,
        }
    )


def _pkg_plan(quantity: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "생산수량": [quantity],
        }
    )


def _pkg_capacity(*divisions: str, capacity: float = 50.0) -> pd.DataFrame:
    count = len(divisions)
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * count,
            "Area_Name": ["Main"] * count,
            "공정": ["Process-A"] * count,
            "STEP_SEQ": [10] * count,
            "MCP_SEQ": [1] * count,
            "소요기준": ["PKG"] * count,
            "양산구분": ["양산"] * count,
            "제품정보": ["Product-A"] * count,
            "Stack": ["12H"] * count,
            "WF 구분": list(divisions),
            "대당 Capa": [capacity] * count,
        }
    )


def test_required_equipment_pkg_basis_matches_real_wf_gubun_values() -> None:
    """실데이터 재현: PKG 기준 STEP 의 실제 WF 구분은 'PKG' 가 아니라 BUFFER 다."""
    result = calculate_required_equipment(
        _pkg_reqb("BUFFER"), _pkg_plan(), pd.DataFrame(), pd.DataFrame(), _pkg_capacity("BUFFER")
    )

    # 생산수량 100 / 대당 Capa 50 = 2.0. 예전 코드는 부하량·소요대수가 모두 0 이었다.
    assert result["부하량"].tolist() == pytest.approx([100.0])
    assert result["소요대수"].tolist() == pytest.approx([2.0])


def test_pkg_load_ignores_yield_and_chip_composition() -> None:
    """PKG 공정에는 Good Die 만 들어온다 — 수율 표가 있어도 부하량은 생산수량 그대로다."""
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Buffer"],
            "EDS_수율": [0.5],
            "BE_수율": [0.5],
        }
    )

    result = calculate_required_equipment(
        _pkg_reqb("Buffer"), _pkg_plan(), yield_data, pd.DataFrame(), _pkg_capacity("Buffer")
    )

    assert result["부하량"].tolist() == pytest.approx([100.0])


def test_pkg_basis_counts_only_buffer_and_reports_the_other_divisions() -> None:
    """스택된 Chip 은 Buffer 로만 센다. Core·Top·Dummy 에 부하량을 붙이면 스택 수만큼 센다.

    세지 않는 행은 조용히 0 으로 두지 않고 사유를 달아 제외 목록에 남긴다.
    """
    divisions = ("BUFFER", "CORE", "TOP", "DUMMY")

    result = calculate_required_equipment(
        _pkg_reqb(*divisions),
        _pkg_plan(),
        pd.DataFrame(),
        pd.DataFrame(),
        _pkg_capacity(*divisions),
    )
    excluded = result.attrs["excluded_required_equipment_rows"]

    assert result["WF 구분"].tolist() == ["BUFFER"]
    assert result["소요대수"].sum() == pytest.approx(2.0)
    assert sorted(excluded["WF 구분"]) == ["CORE", "DUMMY", "TOP"]
    assert set(excluded["제외사유"]) == {"PKG 기준은 Buffer 로만 계수"}
    assert excluded["부하량"].eq(0).all()


def test_pkg_rows_keep_their_reqb_order_next_to_chip_rows() -> None:
    """PKG 와 CHIP 이 섞인 REQB 에서 행 순서와 연결이 서로 흐트러지지 않는다."""
    reqb = pd.concat(
        [
            _pkg_reqb("BUFFER"),
            _pkg_reqb("Core").assign(소요기준="CHIP", 공정="Process-B"),
            _pkg_reqb("BUFFER").assign(공정="Process-C"),
        ],
        ignore_index=True,
    )
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [4],
            "Net Die": [1000],
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
    capacity = pd.concat(
        [
            _pkg_capacity("BUFFER"),
            _pkg_capacity("Core").assign(소요기준="CHIP", 공정="Process-B"),
            _pkg_capacity("BUFFER").assign(공정="Process-C"),
        ],
        ignore_index=True,
    )

    result = calculate_required_equipment(reqb, _pkg_plan(), yield_data, chip_qty, capacity)

    assert result["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    # Chip = 100 × 4 ÷ 0.5 = 800. PKG 는 100 그대로.
    assert result["부하량"].tolist() == pytest.approx([100.0, 800.0, 100.0])
