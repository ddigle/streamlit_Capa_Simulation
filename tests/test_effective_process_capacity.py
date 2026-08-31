import pandas as pd
import pytest

from capa_simulation.services.weighted_unit_capacity import (
    effective_process_capacity_long,
    effective_process_capacity_to_month_table,
)


def _required_equipment() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for step_seq in ("S1", "S2"):
        for capa_code, customer, cs, load in (
            ("C1", "Customer-A", "MP", 60.0),
            ("C2", "Customer-B", "ER", 40.0),
        ):
            rows.append(
                {
                    "생산계획년월": 202608,
                    "Area_Name": "Main",
                    "공정": "Process-A",
                    "소요기준": "CHIP",
                    "양산구분": "양산",
                    "제품정보": "Product-A",
                    "Stack": "8H",
                    "Capa Code": capa_code,
                    "Customer": customer,
                    "CS": cs,
                    "WF 구분": "Core",
                    "MCP_SEQ": "M1",
                    "STEP_SEQ": step_seq,
                    "부하량": load,
                    "대당 Capa": 100.0,
                    "소요대수": load / 100.0,
                }
            )
    return pd.DataFrame(rows)


def test_effective_capacity_counts_each_original_demand_once_across_steps() -> None:
    result = effective_process_capacity_to_month_table(_required_equipment(), "공정")

    assert result.loc[0, "공정"] == "Process-A"
    assert result.loc[0, "202608"] == pytest.approx(50.0)


def test_effective_capacity_long_keeps_weighting_inputs() -> None:
    result = effective_process_capacity_long(_required_equipment(), "제품정보")

    assert result.loc[0, "원수요_부하량"] == pytest.approx(100.0)
    assert result.loc[0, "STEP_소요대수"] == pytest.approx(2.0)
    assert result.loc[0, "공정 유효 Capa"] == pytest.approx(50.0)


def test_effective_capacity_rejects_conflicting_load_for_same_original_demand() -> None:
    required = _required_equipment()
    required.loc[2, "부하량"] = 61.0

    with pytest.raises(ValueError, match="동일 원수요 키"):
        effective_process_capacity_to_month_table(required, "공정")
