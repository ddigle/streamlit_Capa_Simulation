# Purpose: UPEH·ST 기반 경로별 대당 Capa와 제외 규칙을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.unit_capacity import (
    UNIT_CAPACITY_DIMENSIONS,
    calculate_unit_capacity,
    unit_capacity_to_month_table,
)


def test_unit_capacity_uses_upeh_for_main_and_converted_st_for_mi() -> None:
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["MAIN", "mi"],
            "소요기준": ["CHIP", "PKG"],
            "공정": ["Process-A", "Process-B"],
            "STEP_SEQ": ["P100", "P200"],
            "MCP_SEQ": ["1A", "1B"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "WF 구분": ["Core", "Core"],
            "UPEH": [100.0, None],
            "ST": [None, 36.0],
        }
    )
    detail_keys = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "STEP_SEQ",
        "MCP_SEQ",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
    ]
    shared_detail = upeh[detail_keys]
    run_rate = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(CAPA_RUN_RATE=0.8)
    vital = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(편중률=1.0)
    module = pd.DataFrame({"공정": ["Process-A", "Process-B"], "모듈수": [2.0, 2.0]})
    run_day = shared_detail[["생산계획년월", "공정"]].assign(RUN_DAY=30.0)
    lot_ratio = shared_detail.assign(
        Area_Name=["main", "MI"],
        **{"Lot 측정률": [pd.NA, ""]},
    )
    wf_ratio = shared_detail.assign(Area_Name=["Main", "MI"], WF측정률=[None, pd.NA])

    result = calculate_unit_capacity(upeh, run_rate, vital, module, run_day, lot_ratio, wf_ratio)

    assert result.loc[result["Area_Name"].eq("Main"), "대당 Capa"].iloc[0] == pytest.approx(
        (100 / 1000) * 24 * 0.8 * 2 * 30
    )
    assert result.loc[result["Area_Name"].eq("MI"), "대당 Capa"].iloc[0] == pytest.approx(
        ((3600 / 36) / 1000) * 24 * 0.8 * 2 * 30
    )

    invalid_lot_ratio = lot_ratio.copy()
    invalid_lot_ratio.loc[0, "Lot 측정률"] = "invalid"
    with pytest.raises(ValueError, match="RQ_LOT_RATIO의 Lot 측정률 컬럼에 숫자가 아닌 값"):
        calculate_unit_capacity(
            upeh,
            run_rate,
            vital,
            module,
            run_day,
            invalid_lot_ratio,
            wf_ratio,
        )


def test_unit_capacity_excludes_nonpositive_wf_ratio_and_capacity() -> None:
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202608],
            "Area_Name": ["Main", "Main", "Main"],
            "소요기준": ["WF", "WF", "WF"],
            "공정": ["Process-A", "Process-B", "Process-C"],
            "STEP_SEQ": ["P100", "P200", "P300"],
            "MCP_SEQ": ["1A", "1B", "1C"],
            "양산구분": ["양산", "양산", "양산"],
            "제품정보": ["Product-A", "Product-A", "Product-A"],
            "Stack": ["12H", "12H", "12H"],
            "WF 구분": ["Core", "Core", "Core"],
            "UPEH": [100.0, 100.0, 100.0],
            "ST": [None, None, None],
        }
    )
    detail_keys = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "STEP_SEQ",
        "MCP_SEQ",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
    ]
    shared_detail = upeh[detail_keys]
    run_rate = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(
        CAPA_RUN_RATE=[0.8, 0.8, 0.0]
    )
    vital = shared_detail[["생산계획년월", "공정", "양산구분"]].assign(편중률=1.0)
    module = pd.DataFrame({"공정": ["Process-A", "Process-B", "Process-C"], "모듈수": 2.0})
    run_day = shared_detail[["생산계획년월", "공정"]].assign(RUN_DAY=30.0)
    lot_ratio = shared_detail.assign(**{"Lot 측정률": 1.0})
    wf_ratio = shared_detail.assign(WF측정률=[1.0, 0.0, 1.0])

    result = calculate_unit_capacity(upeh, run_rate, vital, module, run_day, lot_ratio, wf_ratio)
    excluded = result.attrs["excluded_capacity_rows"]

    assert result["공정"].tolist() == ["Process-A"]
    assert excluded[["공정", "제외사유"]].to_dict("records") == [
        {"공정": "Process-B", "제외사유": "WF측정률 0 이하"},
        {"공정": "Process-C", "제외사유": "대당 Capa 0 이하"},
    ]
    assert {"UPEH", "ST", "CAPA_RUN_RATE", "WF측정률"}.issubset(excluded.columns)


def test_unit_capacity_excludes_unimplemented_box_and_pcb_bases() -> None:
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "Area_Name": ["Main", "MI"],
            "소요기준": ["BOX", "pcb"],
            "공정": ["Process-A", "Process-B"],
            "STEP_SEQ": ["P100", "P200"],
            "MCP_SEQ": ["1A", "1B"],
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
    assert UNIT_CAPACITY_DIMENSIONS[-2:] == ["STEP_SEQ", "MCP_SEQ"]
