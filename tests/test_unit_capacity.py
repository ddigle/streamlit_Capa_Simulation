# Purpose: UPEH·ST 기반 경로별 대당 Capa와 제외 규칙을 검증한다.

import pickle
import re

import pandas as pd
import pytest

from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
)
from capa_simulation.services.simulation_cache import get_capacity_and_demand
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    MODULE_KEYS,
    RUN_DAY_KEYS,
    UNIT_CAPACITY_DIMENSIONS,
    VITAL_KEYS,
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


# `Lot 측정률` 과 `WF측정률` 은 원천 컬럼 쌍·업무키 9개·결측 기본값 1.0·분모 자리까지
# 같은 쌍둥이 기준정보다. 아래 검증은 두 컬럼이 0 이하 값을 만났을 때도 같은 행 제외
# 규칙을 따르고, 제외될 행 때문에 남은 기준정보 검증이 화면을 멈추지 않는지 고정한다.

DETAIL_KEYS = [
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
# 소요기준 CHIP 은 UPEH 를 Kea 로 환산한다: (100 / 1000) × 24 × 0.8 × 2 × 30
EXPECTED_UNIT_CAPACITY = (100 / 1000) * 24 * 0.8 * 2 * 30


def _capacity_inputs(
    processes: list[str],
    *,
    lot_ratio: list[float] | float = 1.0,
    wf_ratio: list[float] | float = 1.0,
    vital: list[float] | float = 1.0,
    module: list[float] | float = 2.0,
    run_day: list[float] | float = 30.0,
) -> dict[str, pd.DataFrame]:
    """공정 이름 하나에 경로 한 줄씩인 대당 Capa 입력 일곱 장을 만든다."""
    count = len(processes)
    upeh = pd.DataFrame(
        {
            "생산계획년월": [202608] * count,
            "Area_Name": ["Main"] * count,
            "소요기준": ["CHIP"] * count,
            "공정": processes,
            "STEP_SEQ": [f"P{index}00" for index in range(1, count + 1)],
            "MCP_SEQ": [f"{index}A" for index in range(1, count + 1)],
            "양산구분": ["양산"] * count,
            "제품정보": ["Product-A"] * count,
            "Stack": ["12H"] * count,
            "WF 구분": ["Core"] * count,
            "UPEH": [100.0] * count,
            "ST": [None] * count,
        }
    )
    detail = upeh[DETAIL_KEYS]
    return {
        "upeh": upeh,
        "run_rate": detail[["생산계획년월", "공정", "양산구분"]].assign(CAPA_RUN_RATE=0.8),
        "vital": detail[["생산계획년월", "공정", "양산구분"]].assign(편중률=vital),
        "module": pd.DataFrame({"공정": processes, "모듈수": module}),
        "run_day": detail[["생산계획년월", "공정"]].assign(RUN_DAY=run_day),
        "lot_ratio": detail.assign(**{"Lot 측정률": lot_ratio}),
        "wf_ratio": detail.assign(WF측정률=wf_ratio),
    }


def _exclusion_records(result: pd.DataFrame) -> list[dict[str, object]]:
    excluded = result.attrs[CAPACITY_EXCLUSIONS_ATTR]
    return list(excluded[["공정", "제외사유"]].to_dict("records"))


def test_nonpositive_lot_ratio_excludes_the_row_instead_of_stopping_the_page() -> None:
    """0·음수 `Lot 측정률` 한 줄이 HOME·공정별 Capa 를 통째로 멈추면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B", "Process-C"],
        lot_ratio=[1.0, 0.0, -0.5],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY])
    assert _exclusion_records(result) == [
        {"공정": "Process-B", "제외사유": "Lot 측정률 0 이하"},
        {"공정": "Process-C", "제외사유": "Lot 측정률 0 이하"},
    ]


def test_lot_ratio_exclusions_keep_the_joined_reference_values() -> None:
    inputs = _capacity_inputs(["Process-A", "Process-B"], lot_ratio=[1.0, 0.0])

    excluded = calculate_unit_capacity(**inputs).attrs[CAPACITY_EXCLUSIONS_ATTR]

    assert {"UPEH", "ST", "CAPA_RUN_RATE", "Lot 측정률", "WF측정률"}.issubset(excluded.columns)
    assert excluded["Lot 측정률"].tolist() == [0.0]


def test_wf_ratio_exclusion_wins_when_both_ratios_are_nonpositive_on_one_row() -> None:
    """한 행이 두 조건에 다 걸려도 제외 목록에 두 번 나오면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B"],
        lot_ratio=[1.0, 0.0],
        wf_ratio=[1.0, 0.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "WF측정률 0 이하"}]


def test_both_ratios_are_excluded_when_they_fail_on_different_rows() -> None:
    inputs = _capacity_inputs(
        ["Process-A", "Process-B", "Process-C"],
        lot_ratio=[1.0, 1.0, 0.0],
        wf_ratio=[1.0, 0.0, 1.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [
        {"공정": "Process-B", "제외사유": "WF측정률 0 이하"},
        {"공정": "Process-C", "제외사유": "Lot 측정률 0 이하"},
    ]


def test_remaining_checks_ignore_rows_that_are_already_excluded() -> None:
    """제외될 행의 편중률 0 은 계산 대상이 아니므로 예외가 되면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B"],
        wf_ratio=[1.0, 0.0],
        vital=[1.0, 0.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "WF측정률 0 이하"}]


# 예시 dict 의 키 이름만 뽑는다. 값 쪽 문자열은 뒤에 `:` 가 붙지 않아 걸리지 않는다.
EXAMPLE_KEY_PATTERN = re.compile(r"'([^']+)':")


@pytest.mark.parametrize(
    ("column", "table_name", "keys", "argument"),
    [
        ("편중률", "RQ_VITAL", VITAL_KEYS, "vital"),
        ("모듈수", "RQ_MODULE", MODULE_KEYS, "module"),
        ("RUN_DAY", "RQ_RUN_DAY", RUN_DAY_KEYS, "run_day"),
    ],
)
def test_nonpositive_reference_value_names_the_count_and_its_own_keys(
    column: str,
    table_name: str,
    keys: list[str],
    argument: str,
) -> None:
    """세 검증이 각자의 연결 키로 보고하는지 고정한다.

    세 표는 연결 키가 다르다(RQ_VITAL 3개 · RQ_MODULE 1개 · RQ_RUN_DAY 2개). 메시지가
    남의 키 목록을 실으면 사용자는 엉뚱한 편집표에서 없는 행을 찾게 된다.
    """
    inputs = _capacity_inputs(["Process-A", "Process-B"], **{argument: [1.0, 0.0]})

    with pytest.raises(ValueError) as error:
        calculate_unit_capacity(**inputs)

    message = str(error.value)
    assert message.startswith(f"{table_name}의 {column} 값은 0보다 커야 합니다: 1건, 예시 ")
    examples = message.split("예시 ", 1)[1]
    assert EXAMPLE_KEY_PATTERN.findall(examples) == [*keys, column]
    assert "'공정': 'Process-B'" in examples
    assert f"'{column}': 0.0" in examples


def test_healthy_reference_data_excludes_nothing() -> None:
    inputs = _capacity_inputs(["Process-A", "Process-B"])

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A", "Process-B"]
    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY] * 2)
    assert result.attrs[CAPACITY_EXCLUSIONS_ATTR].empty


def test_exclusions_survive_the_cache_round_trip_at_the_end_of_the_pipeline() -> None:
    """화면이 읽는 `attrs` 는 `st.cache_data` 의 피클 왕복을 한 번 거친 것이다.

    페이지는 `get_capacity_and_demand` 를 직접 부르지 않고 `st.cache_data` 로 감싼
    `get_scenario_capacity_and_demand` 를 부른다. 그 캐시는 결과를 피클로 저장했다가
    되돌려 주므로, `attrs` 가 왕복에서 사라지면 제외 경고와 상세 표가 화면에서 통째로
    없어진다. 여기서는 그 왕복을 `pickle` 로 재현한다.
    """
    inputs = _capacity_inputs(["Process-A", "Process-B"], lot_ratio=[1.0, 0.0])
    tables = {
        "RQ_UPEH": inputs["upeh"],
        "RQ_RUN_RATE": inputs["run_rate"],
        "RQ_VITAL": inputs["vital"],
        "RQ_MODULE": inputs["module"],
        "RQ_RUN_DAY": inputs["run_day"],
        "RQ_LOT_RATIO": inputs["lot_ratio"],
        "RQ_WF_RATIO": inputs["wf_ratio"],
        "RQ_REQB": pd.DataFrame(
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
                "STEP_SEQ": ["P100"],
                "MCP_SEQ": ["1A"],
                "소요기준": ["CHIP"],
            }
        ),
        "RQ_PKG_PLAN": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "양산구분": ["양산"],
                "제품정보": ["Product-A"],
                "Stack": ["12H"],
                "Capa Code": ["CAPA-A"],
                "Customer": ["Customer-A"],
                "CS": ["MP"],
                "생산수량": [60.0],
            }
        ),
        "RQ_YLD": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "제품정보": ["Product-A"],
                "Stack": ["12H"],
                "WF 구분": ["Core"],
                "EDS_수율": [0.8],
                "BE_수율": [0.5],
            }
        ),
        "RQ_CHIP_QTY": pd.DataFrame(
            {
                "제품정보": ["Product-A"],
                "Stack": ["12H"],
                "WF 구분": ["Core"],
                "구분_Chip": [2.0],
                "Net Die": [500.0],
            }
        ),
    }

    cached = pickle.loads(pickle.dumps(get_capacity_and_demand(tables)))
    unit_capacity, required_equipment = cached

    assert unit_capacity["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(unit_capacity) == [
        {"공정": "Process-B", "제외사유": "Lot 측정률 0 이하"}
    ]
    # 공정별 확보율 화면의 두 번째 제외 expander 가 읽는 자리도 같은 왕복을 거친다.
    assert REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR in required_equipment.attrs
