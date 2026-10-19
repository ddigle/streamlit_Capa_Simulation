# Purpose: RQ_REQB 경로 연결과 STEP별 소요대수, 소요대수에 들지 않은 계획 목록을 검증한다.

import pandas as pd
import pytest

from capa_simulation.components.required_exclusion_notice import (
    FULL_SCOPE,
    required_exclusion_message,
)
from capa_simulation.services.load_calculator import build_monthly_volume, load_exclusions
from capa_simulation.services.required_equipment import (
    CAPACITY_KEYS,
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    UNROUTED_KEY_MISMATCH_REASON,
    UNROUTED_LOADS_ATTR,
    UNROUTED_UNKNOWN_PRODUCT_REASON,
    UNROUTED_UNUSED_REASON,
    RequiredExclusionCounts,
    calculate_required_equipment,
    required_equipment_to_month_table,
    required_exclusion_counts,
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
    unrouted = result.attrs.get(UNROUTED_LOADS_ATTR)

    # Product-B 경로는 계획이 없어 정말 0 이다.
    assert result.loc[0, "부하량"] == 0
    assert result.loc[0, "소요대수"] == 0
    # 반대로 Product-A 계획 100 은 닿을 경로가 없다. 사라지지 않고 「경로 없는 계획」에 남는다.
    # Product-A 는 RQ_REQB 에 경로가 하나도 없는 제품이라 그 수요 전체가 빠진다 — 센다.
    assert isinstance(unrouted, pd.DataFrame)
    assert unrouted[["제품정보", "소요기준", "부하량", "제외사유"]].values.tolist() == [
        ["Product-A", "PKG", 100.0, UNROUTED_UNKNOWN_PRODUCT_REASON]
    ]
    assert required_exclusion_counts(result) == RequiredExclusionCounts(unrouted_loads=1)


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


def test_reqb_rows_that_differ_only_in_spelling_are_one_route() -> None:
    """표기만 다른 경로 행은 정규화하면 같은 경로다 — 한 번만 센다(사내 감사 P4).

    `WF`·`Wafer`, `Main`·`MAIN`, 앞뒤 공백처럼 표기만 다른 행은 원래 글자로 접으면 따로 남는다.
    계산은 그 행들을 같은 키로 정규화한 뒤 같은 부하량과 대당 Capa 를 붙이므로, 접지 않으면 그
    경로의 소요대수가 행 수만큼 곱해진다. 이미 그렇게 저장된 리비전도 있어 계산에서도 접는다.
    """
    route = {
        "생산계획년월": 202608,
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "12H",
        "Capa Code": "CAPA-A",
        "Customer": "Customer-A",
        "CS": "MP",
        "WF 구분": "Core",
        "STEP_SEQ": "10",
        "MCP_SEQ": "1",
        "소요기준": "WF",
    }
    reqb = pd.DataFrame(
        [
            route,
            {**route, "소요기준": "Wafer"},
            {**route, "Area_Name": "MAIN", "공정": " Process-A "},
        ]
    )
    plan_keys = ("생산계획년월", "양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS")
    plan = pd.DataFrame([{**{key: route[key] for key in plan_keys}, "생산수량": 100.0}])
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
    unit_capacity = pd.DataFrame([{key: route[key] for key in CAPACITY_KEYS}]).assign(
        **{"대당 Capa": 25.0}
    )

    result = calculate_required_equipment(reqb, plan, yield_data, chip_qty, unit_capacity)
    table = required_equipment_to_month_table(result)

    assert len(result) == 1
    assert result["소요대수"].tolist() == pytest.approx([20.0])
    assert table["202608"].tolist() == pytest.approx([20.0])


def test_registration_and_calculation_fold_the_same_route_rows() -> None:
    """등록의 경로 접기(`duplicate_route_rows`)와 계산의 접기는 같은 행을 남긴다.

    계산(`_prepare_reqb`)은 이미 정규화한 표를 `duplicated` 로 접어 정규화를 두 번 하지 않는다.
    두 접기가 갈리면 등록이 남긴 행을 계산이 또 접거나 서로 다른 행을 남긴다 — 등록한 표로 계산한
    결과와 원천 그대로 계산한 결과가 어긋난다.
    """
    from capa_simulation.services.frame_contracts import duplicate_route_rows
    from capa_simulation.services.required_equipment import REQB_COLUMNS

    route = {
        "생산계획년월": 202608,
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "12H",
        "Capa Code": "CAPA-A",
        "Customer": "Customer-A",
        "CS": "MP",
        "WF 구분": "Core",
        "STEP_SEQ": "10",
        "MCP_SEQ": "1",
        "소요기준": "WF",
    }
    routes = pd.DataFrame(
        [
            route,
            {**route, "소요기준": "Wafer"},
            {**route, "Area_Name": "MAIN", "공정": " Process-A "},
            {**route, "소요기준": " wf ", "생산계획년월": "202608"},
            {**route, "공정": "Process-B"},
            {**route, "STEP_SEQ": "20", "Area_Name": "mi"},
            {**route, "STEP_SEQ": "20", "Area_Name": "MI "},
        ]
    )

    canonical = [
        route,
        {**route, "공정": "Process-B"},
        {**route, "STEP_SEQ": "20", "Area_Name": "MI"},
    ]
    plan_keys = ("생산계획년월", "양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS")
    plan = pd.DataFrame([{**{key: route[key] for key in plan_keys}, "생산수량": 100.0}])
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
        [{key: row[key] for key in CAPACITY_KEYS} for row in canonical]
    ).assign(**{"대당 Capa": 25.0})

    registered = routes.loc[~duplicate_route_rows(routes, REQB_COLUMNS)]
    from_source = calculate_required_equipment(routes, plan, yield_data, chip_qty, unit_capacity)
    from_registered = calculate_required_equipment(
        registered, plan, yield_data, chip_qty, unit_capacity
    )

    assert len(registered) == 3
    assert len(from_source) == 3
    assert from_source["소요대수"].tolist() == pytest.approx([20.0, 20.0, 20.0])
    pd.testing.assert_frame_equal(from_registered, from_source)


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


# ------------------------------------------------------------------ 소요대수에 들지 않은 계획
# 사내 정적 감사(2026-10-13) P1·E3·P2·P5. 부하량 환산에서 빠진 계획과 `RQ_REQB` 경로에 닿지 않은
# 계획 부하가 소요대수 결과 어디에도 흔적 없이 0 이 되면 확보율이 그만큼 낙관 쪽으로 틀어지는데,
# 산출 결과·HOME·발행 검사가 아무 말도 하지 않는다.


def _route(product: str, capa_code: str = "K1", *, basis: str = "CHIP") -> dict[str, object]:
    return {
        "생산계획년월": 202608,
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": product,
        "Stack": "12H",
        "Capa Code": capa_code,
        "Customer": "Customer-A",
        "CS": "MP",
        "WF 구분": "Core",
        "STEP_SEQ": 10,
        "MCP_SEQ": 1,
        "소요기준": basis,
    }


def _plan_row(
    product: str, capa_code: str = "K1", quantity: float | None = 100.0
) -> dict[str, object]:
    return {
        "생산계획년월": 202608,
        "양산구분": "양산",
        "제품정보": product,
        "Stack": "12H",
        "Capa Code": capa_code,
        "Customer": "Customer-A",
        "CS": "MP",
        "생산수량": quantity,
    }


def _yield_rows(*products: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * len(products),
            "제품정보": list(products),
            "Stack": ["12H"] * len(products),
            "WF 구분": ["Core"] * len(products),
            "EDS_수율": [0.9] * len(products),
            "BE_수율": [0.9] * len(products),
        }
    )


def _chip_rows(*products: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": list(products),
            "Stack": ["12H"] * len(products),
            "WF 구분": ["Core"] * len(products),
            "구분_Chip": [1.0] * len(products),
            "Net Die": [500.0] * len(products),
        }
    )


def _route_capacity(*products: str, basis: str = "CHIP") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * len(products),
            "Area_Name": ["Main"] * len(products),
            "공정": ["Process-A"] * len(products),
            "STEP_SEQ": [10] * len(products),
            "MCP_SEQ": [1] * len(products),
            "소요기준": [basis] * len(products),
            "양산구분": ["양산"] * len(products),
            "제품정보": list(products),
            "Stack": ["12H"] * len(products),
            "WF 구분": ["Core"] * len(products),
            "대당 Capa": [10.0] * len(products),
        }
    )


def test_load_exclusions_reach_required_equipment() -> None:
    """P1 — `RQ_CHIP_QTY` 가 A 에만 있으면 B 의 계획은 부하량에서 빠진다. 결과 attrs 가 B 를
    싣는다.

    `_build_loads` 의 concat·groupby 가 부하량 쪽 제외 attrs 를 버리면 B 의 소요대수가 말없이
    0 이다.
    """
    reqb = pd.DataFrame([_route("DEMO-A"), _route("DEMO-B")])
    plan = pd.DataFrame([_plan_row("DEMO-A"), _plan_row("DEMO-B")])

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-A", "DEMO-B"),
        _chip_rows("DEMO-A"),
        _route_capacity("DEMO-A", "DEMO-B"),
    )
    excluded = result.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR)

    assert result.set_index("제품정보")["소요대수"].to_dict()["DEMO-B"] == 0
    assert isinstance(excluded, pd.DataFrame)
    assert excluded[["생산계획년월", "제품정보", "누락 기준정보"]].values.tolist() == [
        [202608, "DEMO-B", "RQ_CHIP_QTY"]
    ]


def test_a_month_without_yield_is_listed_instead_of_a_silent_zero() -> None:
    """E3 — 그 달 `RQ_YLD` 가 없는 (월, 제품)도 같은 목록에 남는다(PKG PLAN·수율 편집이 만드는
    꼴)."""
    reqb = pd.DataFrame([_route("DEMO-A"), _route("DEMO-X")])
    plan = pd.DataFrame([_plan_row("DEMO-A"), _plan_row("DEMO-X")])

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-A"),
        _chip_rows("DEMO-A", "DEMO-X"),
        _route_capacity("DEMO-A", "DEMO-X"),
    )
    excluded = result.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR)

    assert result.set_index("제품정보")["소요대수"].to_dict()["DEMO-X"] == 0
    assert isinstance(excluded, pd.DataFrame)
    assert excluded[["제품정보", "WF 구분", "누락 기준정보"]].values.tolist() == [
        ["DEMO-X", "Core", "RQ_YLD"]
    ]


def test_plan_load_that_reaches_no_route_is_listed() -> None:
    """P2 — 경로는 K1 하나, 계획은 K1·K2 각 100 이면 K2 의 부하량이 「경로 없는 계획」으로 남는다.

    계획 총 부하 = 결과에 붙은 부하 + 경로 없는 계획 부하. 목록이 없으면 K2 부하(246.9매)가
    어디에도 남지 않는다.
    """
    reqb = pd.DataFrame([_route("DEMO-A", "K1", basis="WF")])
    plan = pd.DataFrame([_plan_row("DEMO-A", "K1"), _plan_row("DEMO-A", "K2")])

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-A"),
        _chip_rows("DEMO-A"),
        _route_capacity("DEMO-A", basis="WF"),
    )
    unrouted = result.attrs.get(UNROUTED_LOADS_ATTR)

    # Wafer = 100 × 1,000 × 1 ÷ 0.9 ÷ 0.9 ÷ 500
    each = 100 * 1_000 / 0.9 / 0.9 / 500
    assert len(result) == 1
    assert result["부하량"].tolist() == pytest.approx([each])
    assert isinstance(unrouted, pd.DataFrame)
    assert unrouted[["Capa Code", "소요기준", "제외사유"]].values.tolist() == [
        ["K2", "WF", UNROUTED_KEY_MISMATCH_REASON]
    ]
    assert unrouted["부하량"].tolist() == pytest.approx([each])
    assert result["부하량"].sum() + unrouted["부하량"].sum() == pytest.approx(2 * each)


def test_blank_plan_quantity_reads_as_no_plan_and_is_listed() -> None:
    """P5 — 생산수량 빈 값은 「계획 없음(0)」 한 규칙이다. 소요대수도 환산처럼 멈추지 않고 목록에
    남긴다.

    환산·격자가 0 으로 보는 값을 소요대수(HOME·산출 결과·발행 검사)만 키 없는 「숫자가 아닌 값
    또는 누락값」으로 멈추면 같은 계획이 화면마다 다른 뜻이 된다.
    """
    reqb = pd.DataFrame([_route("DEMO-A"), _route("DEMO-B")])
    plan = pd.DataFrame([_plan_row("DEMO-A"), _plan_row("DEMO-B", quantity=None)])

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-A", "DEMO-B"),
        _chip_rows("DEMO-A", "DEMO-B"),
        _route_capacity("DEMO-A", "DEMO-B"),
    )
    excluded = result.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR)

    assert result.set_index("제품정보")["소요대수"].to_dict()["DEMO-B"] == 0
    assert isinstance(excluded, pd.DataFrame)
    assert excluded[["제품정보", "누락 기준정보"]].values.tolist() == [
        ["DEMO-B", "RQ_PKG_PLAN 생산수량 빈 값"]
    ]
    # 환산도 같은 행을 같은 사유로 알린다 — 두 경로가 빈 값을 같은 뜻으로 읽는다.
    volume = build_monthly_volume(
        plan, _yield_rows("DEMO-A", "DEMO-B"), _chip_rows("DEMO-A", "DEMO-B"), "Chip"
    )
    assert load_exclusions(volume)[["제품정보", "누락 기준정보"]].values.tolist() == [
        ["DEMO-B", "RQ_PKG_PLAN 생산수량 빈 값"]
    ]
    assert required_exclusion_counts(result) == RequiredExclusionCounts(blank_plans=1)


def test_a_non_numeric_plan_quantity_still_stops_and_names_the_row() -> None:
    """빈 값과 달리 숫자가 아닌 글자는 계획 없음으로 읽을 근거가 없다 — 어느 행인지 적어 멈춘다."""
    plan = pd.DataFrame([_plan_row("DEMO-A"), _plan_row("DEMO-B")]).astype({"생산수량": object})
    plan.loc[1, "생산수량"] = "약 100"

    with pytest.raises(ValueError, match="숫자가 아닌 값") as caught:
        calculate_required_equipment(
            pd.DataFrame([_route("DEMO-A")]),
            plan,
            _yield_rows("DEMO-A", "DEMO-B"),
            _chip_rows("DEMO-A", "DEMO-B"),
            _route_capacity("DEMO-A"),
        )

    assert "202608 · DEMO-B · 12H" in str(caught.value)


def test_exclusion_counts_count_only_routes_that_lose_load() -> None:
    """P3 — 건수는 소요대수를 실제로 줄이는 것만 센다.

    부하 0 인 경로(계획 없는 제품)가 대당 Capa 없이 빠져도 소요대수는 같다. 그것까지 세면 늘 뜨는
    경고가 되어 아무도 읽지 않는다.
    """
    reqb = pd.DataFrame(
        [_route("DEMO-A"), _route("DEMO-B"), _route("DEMO-C"), _route("DEMO-UNPLANNED")]
    )
    plan = pd.DataFrame(
        [_plan_row("DEMO-A"), _plan_row("DEMO-A", "K2"), _plan_row("DEMO-B"), _plan_row("DEMO-C")]
    )

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-A", "DEMO-C"),
        _chip_rows("DEMO-A", "DEMO-C"),
        _route_capacity("DEMO-A", "DEMO-B"),
    )

    assert required_exclusion_counts(result) == RequiredExclusionCounts(
        excluded_plans=1, unrouted_loads=1, excluded_routes=1
    )


# ------------------------------------------------------------------ 규칙상 쓰지 않는 조합
# 사내 리뷰(review/load R1). 그 제품이 그 소요기준·WF 구분의 경로를 아예 갖지 않는 부하는 고칠
# 키 어긋남이 아니라 구조다 — EDP-TSV 에는 PKG 공정이 없다. 세면 HOME·저장·발행 경고가 모두에게
# 늘 뜬다.


def _pkg_route(product: str, division: str = "BUFFER") -> dict[str, object]:
    return {**_route(product, basis="PKG"), "공정": "Process-P", "WF 구분": division}


def _pkg_route_capacity(product: str, division: str = "BUFFER") -> pd.DataFrame:
    return _route_capacity(product, basis="PKG").assign(공정="Process-P", **{"WF 구분": division})


def test_a_product_without_pkg_routes_does_not_count_its_pkg_load_as_unrouted() -> None:
    """R1 — PKG 경로는 HBM 에만 있고 모두 BUFFER, EDP-TSV 의 PKG 경로는 없다(사내 실데이터 구조).

    `_build_loads` 는 REQB 어딘가에 PKG 행이 있으면 계획 전 행(EDP 포함)에 PKG 부하를 만든다. EDP 의
    PKG 부하를 「경로 없는 계획」으로 세면 EDP 계획 키 × 달 수만큼 경고가 영구히 남는다.
    """
    reqb = pd.DataFrame([_pkg_route("DEMO-HBM"), _route("DEMO-HBM"), _route("DEMO-EDP")])
    plan = pd.DataFrame([_plan_row("DEMO-HBM"), _plan_row("DEMO-EDP")])
    capacity = pd.concat(
        [_pkg_route_capacity("DEMO-HBM"), _route_capacity("DEMO-HBM", "DEMO-EDP")],
        ignore_index=True,
    )

    result = calculate_required_equipment(
        reqb,
        plan,
        _yield_rows("DEMO-HBM", "DEMO-EDP"),
        _chip_rows("DEMO-HBM", "DEMO-EDP"),
        capacity,
    )
    counts = required_exclusion_counts(result)

    assert counts == RequiredExclusionCounts()
    # 알림 모음·저장·발행 경고가 쓰는 문장도 비어 있다.
    assert required_exclusion_message(counts, scope=FULL_SCOPE) == ""
    # HBM 의 PKG 부하는 Buffer 경로에 그대로 붙는다.
    assert result.loc[result["소요기준"].eq("PKG"), "부하량"].tolist() == pytest.approx([100.0])
    # EDP 의 PKG 부하는 목록에서 사라지지 않는다 — 사유를 달아 남아 「계획 총 부하 = 붙은 부하 + 이
    # 목록」이 그대로 맞는다. 세지만 않는다.
    unrouted = result.attrs[UNROUTED_LOADS_ATTR]
    assert unrouted[["제품정보", "소요기준", "부하량", "제외사유"]].values.tolist() == [
        ["DEMO-EDP", "PKG", 100.0, UNROUTED_UNUSED_REASON]
    ]


def test_a_product_whose_pkg_routes_are_not_buffer_is_not_counted_as_unrouted() -> None:
    """R1 — PKG 경로가 Core 행뿐인 제품. 경로 쪽은 「PKG 기준은 Buffer 로만 계수」로 세지 않는데
    부하 쪽만 경로 없는 계획으로 세면 같은 규칙을 두 쪽이 다르게 읽는다."""
    reqb = pd.DataFrame([_pkg_route("DEMO-HBM", "CORE"), _route("DEMO-HBM")])
    capacity = pd.concat(
        [_pkg_route_capacity("DEMO-HBM", "CORE"), _route_capacity("DEMO-HBM")],
        ignore_index=True,
    )

    result = calculate_required_equipment(
        reqb,
        pd.DataFrame([_plan_row("DEMO-HBM")]),
        _yield_rows("DEMO-HBM"),
        _chip_rows("DEMO-HBM"),
        capacity,
    )

    assert required_exclusion_counts(result) == RequiredExclusionCounts()


def test_a_division_without_any_route_is_not_counted_as_unrouted() -> None:
    """R1 — Chip 구성에는 있는데 그 소요기준에 경로가 하나도 없는 WF 구분도 구조다(경로 없는
    WF 구분).

    Core 경로만 있는 제품의 Top Chip 부하는 어느 공정에도 들지 않는 것이 맞다.
    """
    top = {"WF 구분": ["Top"]}
    yields = pd.concat([_yield_rows("DEMO-A"), _yield_rows("DEMO-A").assign(**top)])
    chips = pd.concat([_chip_rows("DEMO-A"), _chip_rows("DEMO-A").assign(**top)])

    result = calculate_required_equipment(
        pd.DataFrame([_route("DEMO-A")]),
        pd.DataFrame([_plan_row("DEMO-A")]),
        yields.reset_index(drop=True),
        chips.reset_index(drop=True),
        _route_capacity("DEMO-A"),
    )

    assert required_exclusion_counts(result) == RequiredExclusionCounts()


def test_a_key_mismatch_is_counted_even_when_the_product_has_other_routes() -> None:
    """R1 — 좁힌 셈이 키 어긋남은 그대로 잡는다. 경로가 다른 달에만 있는 계획(연도 이동·월 병합이
    만드는 꼴)은 같은 제품·소요기준·WF 구분 경로가 있으니 고칠 어긋남이다."""
    next_month = {"생산계획년월": 202609}
    reqb = pd.DataFrame([_route("DEMO-A"), _pkg_route("DEMO-A")])
    plan = pd.DataFrame([_plan_row("DEMO-A"), {**_plan_row("DEMO-A"), **next_month}])
    yields = pd.concat([_yield_rows("DEMO-A"), _yield_rows("DEMO-A").assign(**next_month)])
    capacity = pd.concat(
        [_route_capacity("DEMO-A"), _pkg_route_capacity("DEMO-A")], ignore_index=True
    )

    result = calculate_required_equipment(
        reqb, plan, yields.reset_index(drop=True), _chip_rows("DEMO-A"), capacity
    )
    unrouted = result.attrs[UNROUTED_LOADS_ATTR]

    assert unrouted[["생산계획년월", "소요기준", "제외사유"]].values.tolist() == [
        [202609, "PKG", UNROUTED_KEY_MISMATCH_REASON],
        [202609, "CHIP", UNROUTED_KEY_MISMATCH_REASON],
    ]
    assert required_exclusion_counts(result) == RequiredExclusionCounts(unrouted_loads=2)
