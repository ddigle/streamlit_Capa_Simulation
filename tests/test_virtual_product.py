# Purpose: 기존 제품 복제로 만든 가상 제품이 기준정보 완결 상태로 등록되는지 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    load_exclusions,
)
from capa_simulation.services.virtual_product import (
    VirtualProductRequest,
    available_source_products,
    clone_product,
    clone_table_names,
    cloned_plan_months,
)


def _tables() -> dict[str, pd.DataFrame]:
    months = [202601, 202602]
    return {
        "RQ_PKG_PLAN": pd.DataFrame(
            {
                "생산계획년월": months,
                "양산구분": ["양산"] * 2,
                "제품정보": ["DEMO_A"] * 2,
                "Stack": ["8H"] * 2,
                "Capa Code": ["C1"] * 2,
                "Customer": ["DEMO_CUST"] * 2,
                "CS": ["MP"] * 2,
                "생산수량": [100.0, 200.0],
            }
        ),
        "RQ_YLD": pd.DataFrame(
            {
                "생산계획년월": months,
                "제품정보": ["DEMO_A"] * 2,
                "Stack": ["8H"] * 2,
                "WF 구분": ["Core"] * 2,
                "EDS_수율": [0.9] * 2,
                "BE_수율": [0.95] * 2,
            }
        ),
        "RQ_CHIP_QTY": pd.DataFrame(
            {
                "제품정보": ["DEMO_A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "구분_Chip": [4.0],
                "Net Die": [100.0],
            }
        ),
        "RQ_CHIP_EQ": pd.DataFrame(
            {
                "제품정보": ["DEMO_A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "구분_Chip": [4.0],
                "구분_EQ": [16.0],
            }
        ),
        # 공정 기준이라 제품 키가 없다. 복제 대상이 아니어야 한다.
        "RQ_RUN_DAY": pd.DataFrame(
            {"생산계획년월": months, "공정": ["P1"] * 2, "RUN_DAY": [30.0] * 2}
        ),
    }


def _request(product: str = "DEMO_NEW") -> VirtualProductRequest:
    return VirtualProductRequest("DEMO_A", "8H", product, "8H")


def test_only_product_keyed_tables_are_cloned() -> None:
    """공정 기준 테이블은 제품과 무관하므로 건드리면 안 된다."""
    assert clone_table_names(_tables()) == (
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
    )


def test_clone_adds_the_new_key_to_every_reference_table() -> None:
    tables = _tables()

    updates = clone_product(tables, _request())

    for name in clone_table_names(tables):
        assert "DEMO_NEW" in set(updates[name]["제품정보"]), name
        assert len(updates[name]) == len(tables[name]) * 2, name


def test_cloned_plan_starts_at_zero_quantity() -> None:
    """원본 계획을 그대로 복제하면 총 수요가 조용히 두 배가 된다."""
    updates = clone_product(_tables(), _request())

    plan = updates["RQ_PKG_PLAN"]
    cloned = plan.loc[plan["제품정보"].eq("DEMO_NEW")]
    assert len(cloned) == 2
    assert cloned["생산수량"].sum() == 0.0
    assert plan.loc[plan["제품정보"].eq("DEMO_A"), "생산수량"].tolist() == [100.0, 200.0]


def test_cloned_product_calculates_without_being_excluded() -> None:
    """복제의 목적은 기준정보 완결이다. 제외 목록에 뜨면 복제가 실패한 것이다."""
    tables = _tables()
    updates = clone_product(tables, _request())
    plan = updates["RQ_PKG_PLAN"].copy()
    plan.loc[plan["제품정보"].eq("DEMO_NEW"), "생산수량"] = 50.0

    chip_load, _ = calculate_chip_and_wafer_loads(plan, updates["RQ_YLD"], updates["RQ_CHIP_QTY"])

    assert load_exclusions(chip_load).empty
    assert sorted(set(chip_load["제품정보"])) == ["DEMO_A", "DEMO_NEW"]


def test_source_candidates_require_complete_reference_data() -> None:
    """한 곳이라도 비어 있는 제품을 복제하면 그 구멍이 그대로 따라온다."""
    tables = _tables()
    tables["RQ_CHIP_QTY"] = pd.concat(
        [
            tables["RQ_CHIP_QTY"],
            pd.DataFrame(
                {
                    "제품정보": ["DEMO_PARTIAL"],
                    "Stack": ["8H"],
                    "WF 구분": ["Core"],
                    "구분_Chip": [4.0],
                    "Net Die": [100.0],
                }
            ),
        ],
        ignore_index=True,
    )

    candidates = available_source_products(tables)

    assert candidates["제품정보"].tolist() == ["DEMO_A"]


def test_cloning_onto_the_source_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="원본과 같습니다"):
        clone_product(_tables(), _request("DEMO_A"))


def test_duplicate_key_is_rejected() -> None:
    """기준정보가 일부만 있는 제품 키로도 덮어쓰면 안 된다."""
    tables = _tables()
    tables["RQ_CHIP_QTY"] = pd.concat(
        [
            tables["RQ_CHIP_QTY"],
            tables["RQ_CHIP_QTY"].assign(제품정보="DEMO_B"),
        ],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="이미 있는 제품"):
        clone_product(tables, _request("DEMO_B"))


def test_blank_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="제품정보와 Stack"):
        clone_product(_tables(), VirtualProductRequest("DEMO_A", "8H", "  ", "8H"))


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="복제 원본 제품을 찾을 수 없습니다"):
        clone_product(_tables(), VirtualProductRequest("DEMO_MISSING", "8H", "DEMO_NEW", "8H"))


def test_cloned_plan_months_are_the_new_products_plan_months() -> None:
    """화면이 「새 제품이 지금 조회기간의 PKG PLAN 표에 나타나는가」를 이 달로 판단한다.

    원본 계획이 조회기간 밖에만 있으면 새 제품은 표에 행이 없어 입력할 수 없다(2026-09-29
    횡전개 감사). 원본의 달이 아니라 **새 제품** 행의 달을 돌려줘야 한다.
    """
    tables = _tables()
    tables["RQ_PKG_PLAN"] = pd.concat(
        [
            tables["RQ_PKG_PLAN"],
            tables["RQ_PKG_PLAN"].iloc[[0]].assign(제품정보="DEMO_OTHER", 생산계획년월=202612),
        ],
        ignore_index=True,
    )
    updates = clone_product(tables, _request())

    assert cloned_plan_months(updates, _request()) == (202601, 202602)
    assert cloned_plan_months({}, _request()) == ()
