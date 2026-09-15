# Purpose: 업무 키 충돌의 승자 선택과 보고서 계약을 고정한다.

"""업무 키 충돌 수집의 결과 계약.

판정은 groupby 한 번으로 벡터화하고 보고서 생성 루프는 충돌 그룹에만 돈다. 실측으로 적재
한 번에 21,796 그룹을 돌며 8~14초를 쓰던 것이 충돌 0건이었다. 빨라진 대신 결과가 달라지면
안 되므로, 느린 참조 구현과 레코드를 그대로 대조한다.
"""

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.reference_conflicts import (
    TEMPORARY_CONFLICT_RESOLUTION,
    validated_distinct,
)


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


def test_rows_that_differ_only_by_pack_code_are_two_plans_not_a_conflict() -> None:
    """`Pack Code` 가 업무 키이므로 그것만 다른 두 행은 충돌이 아니라 서로 다른 계획이다.

    승격 전에는 두 행이 같은 키로 접혀 둘째 행의 생산수량이 통째로 사라졌다. 사내 실데이터의
    같은 7키에서 119.93 과 72.51 이 "값 충돌" 로 보고되고 72.51 이 버려진 것이 그 결과다.
    """
    contract = load_core_data_contract()
    base = {
        "생산계획년월": 202601,
        "양산구분": "양산",
        "CS": "MP",
        "제품정보": "P",
        "Stack": "8H",
        "Capa Code": "C1",
        "Customer": "K",
        "생산수량": 119.93,
        "제품타입": "HBM",
        "Pack Code": "PK-5JK",
    }
    frame = pd.DataFrame([base, {**base, "Pack Code": "PK-5WC", "생산수량": 72.51}])
    records: list[dict[str, object]] = []

    distinct = validated_distinct(frame, "RQ_PKG_PLAN", contract, records)

    assert len(distinct) == 2
    assert records == []
    assert sorted(distinct["생산수량"]) == [72.51, 119.93]


# 업무 키가 Core Data 행을 유일하게 가르지 못해 형제 행이 접힌다. 예전 규칙("원천 행 순서상
# 첫 행")은 원천이 '해당 없음' 을 0 으로 적을 때 실값을 버리고 0 을 저장했고, 그 0 은
# `대당 Capa 0 이하` 로 조용히 제외돼 공정이 통째로 사라졌다. 아래가 그 회귀다.


def _upeh_rows(first_upeh: float, second_upeh: float) -> pd.DataFrame:
    """RQ_UPEH 9키가 같고 `Capa Code` 만 다른 형제 두 행. 키에 없는 컬럼이라 접힌다."""
    base = {
        "생산계획년월": 202601,
        "Area_Name": "Main",
        "공정": "Process-A",
        "STEP_SEQ": "P100",
        "MCP_SEQ": "1A",
        "양산구분": "양산",
        "제품정보": "P",
        "Stack": "8H",
        "WF 구분": "Core",
        "소요기준": "WF",
        "ST": None,
    }
    return pd.DataFrame(
        [
            {**base, "UPEH": first_upeh},
            {**base, "UPEH": second_upeh},
        ]
    )


def test_the_row_with_a_value_wins_even_when_the_zero_row_comes_first() -> None:
    """0 이 앞서도 형제의 실값이 살아남아야 한다. 이것이 신고된 결함의 핵심이다."""
    contract = load_core_data_contract()
    records: list[dict[str, object]] = []

    distinct = validated_distinct(_upeh_rows(0.0, 80672.0), "RQ_UPEH", contract, records)

    assert distinct["UPEH"].tolist() == [80672.0]
    assert records[0]["선택값"] == '{"UPEH":80672.0}'
    # 선택 근거를 보고서가 그대로 적어야 사후에 왜 이 행이 이겼는지 알 수 있다.
    assert records[0]["임시처리"] == TEMPORARY_CONFLICT_RESOLUTION
    assert records[0]["선택원천행번호"] == 2


def test_the_winner_does_not_change_when_the_value_row_already_comes_first() -> None:
    contract = load_core_data_contract()
    records: list[dict[str, object]] = []

    distinct = validated_distinct(_upeh_rows(80672.0, 0.0), "RQ_UPEH", contract, records)

    assert distinct["UPEH"].tolist() == [80672.0]
    assert records[0]["선택원천행번호"] == 1


def test_all_zero_siblings_still_collapse_to_zero_without_inventing_a_value() -> None:
    """값을 지어내지 않는다. 형제가 모두 0 이면 결과도 0 이고 충돌도 아니다."""
    contract = load_core_data_contract()
    records: list[dict[str, object]] = []

    distinct = validated_distinct(_upeh_rows(0.0, 0.0), "RQ_UPEH", contract, records)

    assert distinct["UPEH"].tolist() == [0.0]
    assert records == []


def test_collapsed_row_order_is_unchanged_by_the_new_winner_rule() -> None:
    """그룹의 자리는 그대로여야 한다. 흔들리면 `source_row_no`·`reference_hash` 가 바뀐다."""
    contract = load_core_data_contract()
    records: list[dict[str, object]] = []
    rows = pd.concat(
        [
            _upeh_rows(0.0, 80672.0),
            _upeh_rows(5.0, 5.0).assign(공정="Process-B"),
            _upeh_rows(0.0, 7.0).assign(공정="Process-C"),
        ],
        ignore_index=True,
    )

    distinct = validated_distinct(rows, "RQ_UPEH", contract, records)

    assert distinct["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert distinct["UPEH"].tolist() == [80672.0, 5.0, 7.0]
