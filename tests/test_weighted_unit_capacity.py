# Purpose: 부하량 가중 공정 유효 Capa 표시값을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.weighted_unit_capacity import weighted_unit_capacity_to_month_table


def test_weighted_unit_capacity_uses_process_load_at_selected_detail_level() -> None:
    required_equipment = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202608, 202608],
            "공정": ["Process-A", "Process-A", "Process-A", "Process-B"],
            "소요기준": ["WF", "WF", "WF", "CHIP"],
            "양산구분": ["양산", "양산", "ER", "양산"],
            "제품정보": ["Product-A", "Product-A", "Product-B", "Product-A"],
            "Stack": ["12H", "12H", "8H", "12H"],
            "WF 구분": ["Core", "Top", "Core", "Core"],
            "부하량": [60.0, 40.0, 0.0, 50.0],
            "대당 Capa": [100.0, 200.0, 300.0, 400.0],
        }
    )

    process_table = weighted_unit_capacity_to_month_table(required_equipment, "공정")
    wf_table = weighted_unit_capacity_to_month_table(required_equipment, "WF 구분")

    process_a = process_table.loc[process_table["공정"].eq("Process-A")].iloc[0]
    assert process_a["소요기준"] == "WF"
    assert process_a["202608"] == pytest.approx(140.0)
    assert pd.isna(
        wf_table.loc[
            wf_table["양산구분"].eq("ER") & wf_table["WF 구분"].eq("Core"),
            "202608",
        ].iloc[0]
    )
    assert required_equipment["대당 Capa"].tolist() == [100.0, 200.0, 300.0, 400.0]


def test_weighted_unit_capacity_rejects_multiple_bases_for_one_process() -> None:
    required_equipment = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "공정": ["Process-A", "Process-A"],
            "소요기준": ["WF", "CHIP"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Core"],
            "부하량": [60.0, 40.0],
            "대당 Capa": [100.0, 200.0],
        }
    )

    with pytest.raises(ValueError, match="공정별 소요기준이 둘 이상"):
        weighted_unit_capacity_to_month_table(required_equipment, "공정")
