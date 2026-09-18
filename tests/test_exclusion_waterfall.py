# Purpose: 제외 워터폴이 그리는 사유 순서가 계산이 실제로 거른 차례와 같은지 고정한다.

"""화면이 계산을 설명해야지 계산과 다른 이야기를 하면 안 된다.

`REASON_ORDER` 는 세로 막대가 서는 차례다. 그런데 사유 문자열이 `unit_capacity` 와
`exclusion_waterfall` 두 곳에 따로 적혀 있어서, 새 사유를 넣으면 계산에만 들어가고 그림은
모른다. 실제로 `CAPA_RUN_RATE 0 이하` 가 그렇게 빠졌다 — 계약에 없는 사유를 뒤에 붙이는
관대한 처리 덕에 예외는 나지 않고, 막대만 엉뚱한 자리에 섰다.

그래서 **문자열을 다시 베끼지 않는다.** 각 사유를 실제로 한 행씩 떨어뜨리는 입력으로
`calculate_unit_capacity` 를 돌리고, 제외표에 사유가 **등장한 차례**가 `REASON_ORDER` 의
부분수열인지 본다. `excluded_frames` 가 판정 순서대로 `concat` 되므로 그 차례가 곧 진짜
판정 차례다. 이 한 문장이 원소 누락과 순서 뒤집힘을 동시에 잡는다.
"""

import pandas as pd

from capa_simulation.components.exclusion_waterfall import REASON_ORDER
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    calculate_unit_capacity,
)

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


def _inputs(processes: list[str]) -> dict[str, pd.DataFrame]:
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
        "vital": detail[["생산계획년월", "공정", "양산구분"]].assign(편중률=1.0),
        "module": pd.DataFrame({"공정": processes, "모듈수": 2.0}),
        "run_day": detail[["생산계획년월", "공정"]].assign(RUN_DAY=30.0),
        "lot_ratio": detail.assign(**{"Lot 측정률": 1.0}),
        "wf_ratio": detail.assign(WF측정률=1.0),
    }


def _reason_sequence() -> list[str]:
    """사유마다 한 행씩 떨어뜨려, 계산이 실제로 거른 차례를 뽑는다."""
    processes = ["OK", "DropUpeh", "DropRunRate", "DropWf", "DropLot"]
    inputs = _inputs(processes)
    inputs["upeh"] = inputs["upeh"].assign(UPEH=[100.0, 0.0, 100.0, 100.0, 100.0])
    inputs["run_rate"] = inputs["run_rate"].assign(CAPA_RUN_RATE=[0.8, 0.8, 0.0, 0.8, 0.8])
    inputs["wf_ratio"] = inputs["wf_ratio"].assign(WF측정률=[1.0, 1.0, 1.0, -1.0, 1.0])
    inputs["lot_ratio"] = inputs["lot_ratio"].assign(**{"Lot 측정률": [1.0, 1.0, 1.0, 1.0, -1.0]})

    result = calculate_unit_capacity(**inputs)
    excluded = result.attrs[CAPACITY_EXCLUSIONS_ATTR]
    return list(excluded["제외사유"].drop_duplicates())


def _is_subsequence(inner: list[str], outer: tuple[str, ...]) -> bool:
    iterator = iter(outer)
    return all(item in iterator for item in inner)


def test_the_drawn_order_matches_the_order_the_calculation_excluded_in() -> None:
    sequence = _reason_sequence()

    assert sequence, "제외가 하나도 일어나지 않았습니다 — 입력이 규칙을 밟지 못합니다."
    assert _is_subsequence(sequence, REASON_ORDER), (
        "계산이 거른 차례가 그림의 순서와 다릅니다.\n"
        f"  계산: {sequence}\n"
        f"  그림: {list(REASON_ORDER)}"
    )


def test_every_reason_the_calculation_can_produce_is_drawn() -> None:
    """계약에 없는 사유는 뒤에 붙을 뿐 예외가 나지 않는다 — 그래서 누락이 조용하다."""
    missing = [reason for reason in _reason_sequence() if reason not in REASON_ORDER]

    assert not missing, (
        "계산이 내는 사유가 그림의 순서 목록에 없습니다. 막대가 맨 뒤에 섭니다:\n"
        + "\n".join(missing)
    )


def test_the_product_of_all_factors_is_the_last_resort() -> None:
    """`대당 Capa 0 이하` 는 모든 인자가 양수인데도 곱이 0 으로 떨어지는 경우만 받는다.

    원인을 가리키는 사유들보다 뒤에 서야 「무엇 때문에 빠졌나」가 왼쪽부터 읽힌다.
    """
    assert REASON_ORDER[-1] == "대당 Capa 0 이하"
