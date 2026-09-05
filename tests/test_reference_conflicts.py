# Purpose: 충돌 판정을 벡터화한 뒤에도 보고서가 그룹 루프와 같은지 고정한다.

"""업무 키 충돌 수집의 결과 계약.

판정은 groupby 한 번으로 벡터화하고 보고서 생성 루프는 충돌 그룹에만 돈다. 실측으로 적재
한 번에 21,796 그룹을 돌며 8~14초를 쓰던 것이 충돌 0건이었다. 빨라진 대신 결과가 달라지면
안 되므로, 느린 참조 구현과 레코드를 그대로 대조한다.
"""

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.reference_conflicts import validated_distinct


def _plan_rows() -> pd.DataFrame:
    """RQ_PKG_PLAN 업무 키 세 그룹. 둘째 그룹만 생산수량이 갈리고, 셋째는 값까지 같은 중복이다."""
    base = {
        "생산계획년월": 202601,
        "양산구분": "양산",
        "CS": "MP",
        "제품정보": "P",
        "Stack": "8H",
        "Capa Code": "C1",
        "Customer": "K",
        "생산수량": 10.0,
        "제품타입": "HBM",
        "Pack Code": "PK",
    }
    rows = [
        {**base},
        {**base, "Capa Code": "C2", "생산수량": 20.0},
        {**base, "Capa Code": "C2", "생산수량": 25.0},
        {**base, "Capa Code": "C3"},
        {**base, "Capa Code": "C3"},
    ]
    return pd.DataFrame(rows)


def _reference_records(frame: pd.DataFrame, keys: list[str]) -> list[tuple[str, int]]:
    """벡터화 전 규칙을 가장 단순하게 다시 쓴 것: 그룹마다 값이 갈리는 컬럼이 있으면 충돌."""
    values = [c for c in frame.columns if c not in keys]
    found = []
    for _, group in frame[frame.duplicated(subset=keys, keep=False)].groupby(keys, sort=False):
        columns = [c for c in values if group[c].nunique(dropna=False) > 1]
        if columns:
            found.append((" | ".join(columns), len(group)))
    return found


def test_only_groups_with_differing_values_are_reported() -> None:
    contract = load_core_data_contract()
    keys = list(contract.derived_keys["RQ_PKG_PLAN"])
    records: list[dict[str, object]] = []

    distinct = validated_distinct(_plan_rows(), "RQ_PKG_PLAN", contract, records)

    assert len(distinct) == 3
    assert [(r["충돌컬럼"], r["충돌행수"]) for r in records] == _reference_records(
        _plan_rows(), keys
    )
    assert records[0]["충돌그룹"] == "RQ_PKG_PLAN-0001"
    assert records[0]["선택값"] == '{"생산수량":20.0}'


def test_no_conflict_means_no_records_and_no_group_loop() -> None:
    """값이 같은 중복만 있으면 보고서에 아무것도 오르지 않는다."""
    contract = load_core_data_contract()
    frame = _plan_rows().iloc[[0, 3, 4]]
    records: list[dict[str, object]] = []

    distinct = validated_distinct(frame, "RQ_PKG_PLAN", contract, records)

    assert len(distinct) == 2
    assert records == []
