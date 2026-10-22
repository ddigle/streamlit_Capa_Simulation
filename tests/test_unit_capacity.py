# Purpose: UPEH·ST 기반 경로별 대당 Capa와 제외 규칙을 검증한다.

import pickle
import re
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
)
from capa_simulation.services.simulation_cache import get_capacity_and_demand
from capa_simulation.services.unit_capacity import (
    CAPACITY_ASSUMED_MONTHS_ATTR,
    CAPACITY_ASSUMPTIONS_ATTR,
    CAPACITY_EXCLUSIONS_ATTR,
    MODULE_KEYS,
    RUN_DAY_KEYS,
    UNIT_CAPACITY_DIMENSIONS,
    VITAL_KEYS,
    calculate_unit_capacity,
    capacity_assumptions,
    converted_upeh,
    unit_capacity_to_month_table,
)


def test_unit_capacity_uses_upeh_for_main_and_converted_st_for_mi() -> None:
    """MI 행 ST 는 한 개당 분이다(정의) — ST 36분 → 시간당 60/36 개, PKG 라 다시 ÷1000."""
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
    # 결측 표기 두 가지를 섞는다. pandas-stubs 의 열 값 타입에는 NA·None 이 없다.
    lot_blanks: list[Any] = [pd.NA, ""]
    wf_blanks: list[Any] = [None, pd.NA]
    lot_ratio = shared_detail.assign(
        Area_Name=["main", "MI"],
        **{"Lot 측정률": lot_blanks},
    )
    wf_ratio = shared_detail.assign(Area_Name=["Main", "MI"], WF측정률=wf_blanks)

    result = calculate_unit_capacity(upeh, run_rate, vital, module, run_day, lot_ratio, wf_ratio)

    assert result.loc[result["Area_Name"].eq("Main"), "대당 Capa"].iloc[0] == pytest.approx(
        (100 / 1000) * 24 * 0.8 * 2 * 30
    )
    assert result.loc[result["Area_Name"].eq("MI"), "환산_UPEH"].iloc[0] == pytest.approx(
        (60 / 36) / 1000
    )
    assert result.loc[result["Area_Name"].eq("MI"), "대당 Capa"].iloc[0] == pytest.approx(
        ((60 / 36) / 1000) * 24 * 0.8 * 2 * 30
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


def test_mi_st_is_minutes_per_unit_so_the_hourly_rate_is_sixty_over_st() -> None:
    """`RQ_UPEH` 의 MI 행 ST 는 한 개당 분(정의, 2026-10-22) — 값 크기로 단위를 가르지 않는다.

    ST 2분 → 시간당 30개(WF), CHIP·PKG 는 다시 ÷1000. 작은 ST(0.0005분)도 같은 식이다.
    """
    upeh = pd.DataFrame(
        {
            "생산계획년월": 202608,
            "Area_Name": ["Main", "MI", "MI", "MI"],
            "소요기준": ["WF", "WF", "CHIP", "PKG"],
            "공정": ["Main-WF", "MI-WF", "MI-CHIP", "MI-PKG"],
            "STEP_SEQ": "P100",
            "MCP_SEQ": "1A",
            "양산구분": "양산",
            "제품정보": "Product-A",
            "Stack": "12H",
            "WF 구분": "Core",
            "UPEH": [45.0, None, None, None],
            "ST": [None, 2.0, 0.0005, 0.25],
        }
    )
    route = upeh.drop(columns=["소요기준", "UPEH", "ST"])
    by_month = route[["생산계획년월", "공정", "양산구분"]]

    result = calculate_unit_capacity(
        upeh,
        by_month.assign(CAPA_RUN_RATE=1.0),
        by_month.assign(편중률=1.0),
        route[["공정"]].assign(모듈수=1.0),
        route[["생산계획년월", "공정"]].assign(RUN_DAY=1.0),
        route.assign(**{"Lot 측정률": 1.0}),
        route.assign(WF측정률=1.0),
    )

    rate = result.set_index("공정")["환산_UPEH"]
    assert rate["Main-WF"] == pytest.approx(45.0)
    assert rate["MI-WF"] == pytest.approx(30.0)
    assert rate["MI-CHIP"] == pytest.approx(60 / 0.0005 / 1000)
    assert rate["MI-PKG"] == pytest.approx(60 / 0.25 / 1000)
    # 대당 Capa 는 환산_UPEH × 24 (나머지 인자 1).
    assert result.set_index("공정").loc["MI-WF", "대당 Capa"] == pytest.approx(30.0 * 24)


def test_converted_upeh_leaves_rows_that_are_neither_main_nor_mi_blank() -> None:
    upeh = pd.Series([10.0, 10.0, 10.0])
    st = pd.Series([3.0, 3.0, 3.0])

    rate = converted_upeh(
        upeh,
        st,
        main=pd.Series([True, False, False]),
        mi=pd.Series([False, True, False]),
        per_kea=pd.Series([False, True, False]),
    )

    assert rate.iloc[0] == 10.0
    assert rate.iloc[1] == pytest.approx(60 / 3 / 1000)
    assert pd.isna(rate.iloc[2])


def test_unit_capacity_names_each_excluded_row_by_its_own_cause() -> None:
    """예전에는 `CAPA_RUN_RATE = 0` 이 `대당 Capa 0 이하` 로 뭉뚱그려졌다.

    제외표는 남고 값도 보이지만, 사유가 곱의 결과만 말하면 사용자는 UPEH 쪽을 뒤진다.
    이제 각 행은 자기 원인으로 적히고, `대당 Capa 0 이하` 는 모든 인자가 양수인데도
    곱이 0 으로 떨어지는 경우만 받는 마지막 안전망이다.
    """
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
    wf_ratio = shared_detail.assign(WF측정률=[1.0, -1.0, 1.0])

    result = calculate_unit_capacity(upeh, run_rate, vital, module, run_day, lot_ratio, wf_ratio)
    excluded = result.attrs["excluded_capacity_rows"]

    assert result["공정"].tolist() == ["Process-A"]
    assert excluded[["공정", "제외사유"]].to_dict("records") == [
        {"공정": "Process-C", "제외사유": "CAPA_RUN_RATE 0 이하"},
        {"공정": "Process-B", "제외사유": "WF측정률 음수"},
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
# 같은 쌍둥이 기준정보다. 아래 검증은 두 컬럼이 **0 이면 1.0 을 적용**하고 **음수일 때만**
# 같은 행 제외 규칙을 따르며, 제외될 행 때문에 남은 기준정보 검증이 화면을 멈추지 않는지
# 고정한다.

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


def test_nonpositive_upeh_says_upeh_not_just_the_capacity_result() -> None:
    """원천 접힘으로 UPEH 0 이 저장됐을 때 제외 사유가 원인을 가리켜야 한다."""
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    inputs["upeh"] = inputs["upeh"].assign(UPEH=[100.0, 0.0])

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "UPEH 0 이하"}]


def test_nonpositive_run_rate_says_run_rate_not_the_capacity_result() -> None:
    """CAPA_RUN_RATE 는 분자인데 제외 사유는 `대당 Capa 0 이하` 로만 적혀 UPEH 를 가리켰다.

    편중률 0 은 하드 오류로 즉시 멈추는데 효율 0 은 조용히 빠지는 비대칭이 있었다.
    멈추지 않는 쪽은 유지하되(원천이 "해당 없음" 을 0 으로 적는 일이 실제로 있다),
    무엇이 0 인지는 사유가 말해야 한다.
    """
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    inputs["run_rate"] = inputs["run_rate"].assign(CAPA_RUN_RATE=[0.8, 0.0])

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "CAPA_RUN_RATE 0 이하"}]


def test_a_negative_run_rate_is_excluded_for_the_same_reason() -> None:
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    inputs["run_rate"] = inputs["run_rate"].assign(CAPA_RUN_RATE=[0.8, -1.0])

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "CAPA_RUN_RATE 0 이하"}]


def test_zero_measurement_ratios_apply_one_instead_of_excluding_the_row() -> None:
    """측정률 0 은 빈 값과 같은 뜻이라 1.0 을 적용한다. 행을 빼지 않는다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B", "Process-C"],
        lot_ratio=[1.0, 0.0, 1.0],
        wf_ratio=[1.0, 1.0, 0.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    # 1.0 으로 나눈 것과 같으므로 세 줄의 대당 Capa 가 서로 같다.
    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY] * 3)
    assert _exclusion_records(result) == []


def test_zero_on_both_measurement_ratios_of_one_row_still_applies_one() -> None:
    """한 행에서 두 측정률이 모두 0 이어도 제외하지 않는다."""
    inputs = _capacity_inputs(["Process-A"], lot_ratio=[0.0], wf_ratio=[0.0])

    result = calculate_unit_capacity(**inputs)

    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY])
    assert _exclusion_records(result) == []


def test_negative_lot_ratio_excludes_the_row_instead_of_stopping_the_page() -> None:
    """음수 `Lot 측정률` 한 줄이 HOME·공정별 Capa 를 통째로 멈추면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B", "Process-C"],
        lot_ratio=[1.0, -0.5, -1.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY])
    assert _exclusion_records(result) == [
        {"공정": "Process-B", "제외사유": "Lot 측정률 음수"},
        {"공정": "Process-C", "제외사유": "Lot 측정률 음수"},
    ]


def test_lot_ratio_exclusions_keep_the_joined_reference_values() -> None:
    inputs = _capacity_inputs(["Process-A", "Process-B"], lot_ratio=[1.0, -0.5])

    excluded = calculate_unit_capacity(**inputs).attrs[CAPACITY_EXCLUSIONS_ATTR]

    assert {"UPEH", "ST", "CAPA_RUN_RATE", "Lot 측정률", "WF측정률"}.issubset(excluded.columns)
    assert excluded["Lot 측정률"].tolist() == [-0.5]


def test_wf_ratio_exclusion_wins_when_both_ratios_are_negative_on_one_row() -> None:
    """한 행이 두 조건에 다 걸려도 제외 목록에 두 번 나오면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B"],
        lot_ratio=[1.0, -0.5],
        wf_ratio=[1.0, -0.5],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "WF측정률 음수"}]


def test_both_ratios_are_excluded_when_they_fail_on_different_rows() -> None:
    inputs = _capacity_inputs(
        ["Process-A", "Process-B", "Process-C"],
        lot_ratio=[1.0, 1.0, -0.5],
        wf_ratio=[1.0, -0.5, 1.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [
        {"공정": "Process-B", "제외사유": "WF측정률 음수"},
        {"공정": "Process-C", "제외사유": "Lot 측정률 음수"},
    ]


def test_remaining_checks_ignore_rows_that_are_already_excluded() -> None:
    """제외될 행의 편중률 0 은 계산 대상이 아니므로 예외가 되면 안 된다."""
    inputs = _capacity_inputs(
        ["Process-A", "Process-B"],
        wf_ratio=[1.0, -0.5],
        vital=[1.0, 0.0],
    )

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert _exclusion_records(result) == [{"공정": "Process-B", "제외사유": "WF측정률 음수"}]


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
    inputs = _capacity_inputs(["Process-A", "Process-B"], lot_ratio=[1.0, -0.5])
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
        {"공정": "Process-B", "제외사유": "Lot 측정률 음수"}
    ]
    # 공정별 확보율 화면의 두 번째 제외 expander 가 읽는 자리도 같은 왕복을 거친다.
    assert REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR in required_equipment.attrs


# ------------------------------------- 측정률 행 부재: 멈추지 않고 1.0 으로 잇되 **센다**


def test_a_missing_ratio_row_no_longer_stops_the_whole_page() -> None:
    """빈 UPEH 를 채우면 측정률 짝이 없어 화면이 통째로 섰다(2026-09-23 사내).

    측정률은 **중립값이 있는** 기준정보다. 빈 값과 `0` 은 이미 1.0 으로 결정돼 있고
    (`MEASUREMENT_RATIO_ZERO_DEFAULT`), 행 부재만 하드 오류로 남아 있었다. 같은 선 안으로
    들인다 — 어차피 빠질 행 하나 때문에 그 값을 고칠 편집기조차 못 여는 쪽이 더 나쁘다.
    """
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    inputs["lot_ratio"] = inputs["lot_ratio"].iloc[:1]

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A", "Process-B"]
    # 1.0 은 분모이므로 값이 그대로다 — 짝이 있던 행과 같은 대당 Capa 가 나온다.
    assert result["대당 Capa"].tolist() == pytest.approx(
        [EXPECTED_UNIT_CAPACITY, EXPECTED_UNIT_CAPACITY]
    )


def test_the_assumed_rows_are_counted_so_the_screen_can_say_it() -> None:
    """**세지 않고 메우면 조용히 틀린다.**

    측정률은 대당 Capa 의 분모다. 실제가 1 보다 작은 경로에 1.0 을 쓰면 대당 Capa 과소 →
    소요대수 과대 → 확보율 과소(보수 쪽)이고, 1 보다 크면 그 반대다. 어느 쪽이든 그 사실이
    화면에 닿아야 완화가 「경고하고 계속」이지 「조용히 계속」이 아니다.
    """
    inputs = _capacity_inputs(["Process-A", "Process-B", "Process-C"])
    inputs["lot_ratio"] = inputs["lot_ratio"].iloc[:1]
    inputs["wf_ratio"] = inputs["wf_ratio"].iloc[:2]

    assumed = calculate_unit_capacity(**inputs).attrs[CAPACITY_ASSUMPTIONS_ATTR]

    assert assumed == {"RQ_LOT_RATIO": 2, "RQ_WF_RATIO": 1}


def test_the_assumed_months_are_kept_so_the_screen_can_name_them() -> None:
    """건수만 말하면 어느 달 칸을 채울지 다시 찾아야 한다. 시나리오 전체를 한 번에 계산하므로
    조회기간 밖의 달이면 왜 떴는지도 모른다."""
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    inputs["lot_ratio"] = inputs["lot_ratio"].iloc[:1]

    result = calculate_unit_capacity(**inputs)

    assert result.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] == {"RQ_LOT_RATIO": (202608,)}
    assert capacity_assumptions(result).counts == {"RQ_LOT_RATIO": 1}


def test_no_missing_rows_leaves_the_assumption_report_empty() -> None:
    """없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    result = calculate_unit_capacity(**_capacity_inputs(["Process-A"]))

    assert result.attrs[CAPACITY_ASSUMPTIONS_ATTR] == {}


def test_tables_without_a_neutral_default_still_stop_hard() -> None:
    """가동률·편중률·모듈수·가동일수에는 중립값이 없다.

    1.0 을 넣으면 「가동률 100%」 같은 거짓 주장이 되고, 기준정보가 통째로 빠진 배포에서도
    숫자가 나와 버린다. 완화는 측정률 둘에만 적용한다.
    """
    for table in ("run_rate", "vital", "module", "run_day"):
        inputs = _capacity_inputs(["Process-A", "Process-B"])
        inputs[table] = inputs[table].iloc[:1]

        with pytest.raises(ValueError, match="연결값이 없는 대당 Capa 기준이 있습니다"):
            calculate_unit_capacity(**inputs)


# ------------------------- 계산에 안 쓰는 행의 빈 값은 멈추지 않는다 — 붙은 행만 검사한다
# 효율·여유율·모듈수·일수 표 전체를 붙이기 **전에** 숫자 검사를 하면, BOX·PCB 처럼 계산이 쓰지
# 않는 공정이나 UPEH 가 없는 달의 빈 칸 하나가 대당 Capa 전체를 멈춘다. 붙은 행이 걸릴 때는 빈 칸과
# 숫자가 아닌 값을 갈라 어느 행인지 적는다(사내 감사 P6).

# 표마다 정상값. 빈 칸 하나만 바꿔 넣는다.
HEALTHY_VALUES = {"run_rate": 0.8, "vital": 1.0, "module": 2.0, "run_day": 30.0}
REQUIRED_REFERENCES = [
    ("run_rate", "CAPA_RUN_RATE", "RQ_RUN_RATE", ["생산계획년월", "공정", "양산구분"]),
    ("vital", "편중률", "RQ_VITAL", VITAL_KEYS),
    ("module", "모듈수", "RQ_MODULE", MODULE_KEYS),
    ("run_day", "RUN_DAY", "RQ_RUN_DAY", RUN_DAY_KEYS),
]


@pytest.mark.parametrize(("argument", "column"), [item[:2] for item in REQUIRED_REFERENCES])
def test_a_blank_value_on_a_box_process_row_does_not_stop_the_calculation(
    argument: str, column: str
) -> None:
    """BOX 공정은 UPEH 단계에서 빠진다. 그 공정의 기준값이 비어도 남은 경로는 계산된다."""
    inputs = _capacity_inputs(["Process-A", "Process-BOX"])
    inputs["upeh"] = inputs["upeh"].assign(소요기준=["CHIP", "BOX"])
    blank: list[Any] = [HEALTHY_VALUES[argument], None]
    inputs[argument] = inputs[argument].assign(**{column: blank})

    result = calculate_unit_capacity(**inputs)

    assert result["공정"].tolist() == ["Process-A"]
    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY])


@pytest.mark.parametrize(
    ("argument", "column"),
    [item[:2] for item in REQUIRED_REFERENCES if item[0] != "module"],
)
def test_a_blank_value_in_a_month_without_upeh_does_not_stop_the_calculation(
    argument: str, column: str
) -> None:
    """UPEH 가 없는 달의 행은 어느 경로에도 붙지 않는다. 그 칸이 비어도 계산은 그대로다."""
    inputs = _capacity_inputs(["Process-A"])
    frame = inputs[argument]
    doubled = pd.concat([frame, frame.assign(생산계획년월=202609)], ignore_index=True)
    doubled.loc[1, column] = float("nan")
    inputs[argument] = doubled

    result = calculate_unit_capacity(**inputs)

    assert result["대당 Capa"].tolist() == pytest.approx([EXPECTED_UNIT_CAPACITY])


@pytest.mark.parametrize(("argument", "column", "table_name", "keys"), REQUIRED_REFERENCES)
def test_a_blank_value_on_a_used_row_is_named_blank_with_its_own_keys(
    argument: str, column: str, table_name: str, keys: list[str]
) -> None:
    """쓰는 행의 빈 칸은 그대로 멈춘다 — 중립값이 없다. 다만 「빈 값」이라 부르고 키를 적는다."""
    inputs = _capacity_inputs(["Process-A", "Process-B"])
    blank: list[Any] = [HEALTHY_VALUES[argument], None]
    inputs[argument] = inputs[argument].assign(**{column: blank})

    with pytest.raises(ValueError) as error:
        calculate_unit_capacity(**inputs)

    message = str(error.value)
    assert message.startswith(f"{table_name}의 {column} 값이 빈 대당 Capa 기준이 있습니다: 1건, ")
    assert "숫자가 아닌" not in message
    assert EXAMPLE_KEY_PATTERN.findall(message.split("예시 ", 1)[1]) == keys
    assert "'공정': 'Process-B'" in message


@pytest.mark.parametrize(
    ("argument", "column", "table_name", "keys"),
    [
        *REQUIRED_REFERENCES,
        ("lot_ratio", "Lot 측정률", "RQ_LOT_RATIO", DETAIL_KEYS),
        ("wf_ratio", "WF측정률", "RQ_WF_RATIO", DETAIL_KEYS),
    ],
)
def test_a_non_numeric_value_stops_only_on_a_used_row_and_names_the_value(
    argument: str, column: str, table_name: str, keys: list[str]
) -> None:
    """숫자로 못 읽는 값은 쓰는 행에서만 멈춘다. 그때는 그 값과 키를 함께 적는다."""
    values: list[Any] = [HEALTHY_VALUES.get(argument, 1.0), "N/A"]
    unused = _capacity_inputs(["Process-A", "Process-BOX"])
    unused["upeh"] = unused["upeh"].assign(소요기준=["CHIP", "BOX"])
    unused[argument] = unused[argument].assign(**{column: values})

    assert calculate_unit_capacity(**unused)["공정"].tolist() == ["Process-A"]

    used = _capacity_inputs(["Process-A", "Process-B"])
    used[argument] = used[argument].assign(**{column: values})
    with pytest.raises(ValueError) as error:
        calculate_unit_capacity(**used)

    message = str(error.value)
    assert message.startswith(f"{table_name}의 {column} 컬럼에 숫자가 아닌 값이 있습니다: 1건, ")
    assert EXAMPLE_KEY_PATTERN.findall(message.split("예시 ", 1)[1]) == [*keys, column]
    assert "'공정': 'Process-B'" in message
    assert f"'{column}': 'N/A'" in message
