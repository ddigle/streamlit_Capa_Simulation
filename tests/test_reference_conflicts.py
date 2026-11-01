# Purpose: 업무 키 충돌의 승자 선택과 보고서 계약을 고정한다.

"""업무 키 충돌 수집의 결과 계약.

판정은 groupby 한 번으로 벡터화하고 보고서 생성 루프는 충돌 그룹에만 돈다. 실측으로 적재
한 번에 21,796 그룹을 돌며 8~14초를 쓰던 것이 충돌 0건이었다. 빨라진 대신 결과가 달라지면
안 되므로, 느린 참조 구현과 레코드를 그대로 대조한다.
"""

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.reference_conflicts import (
    TEMPORARY_CONFLICT_RESOLUTION,
    ZERO_BEFORE_BLANK_RESOLUTION,
    conflict_resolution,
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


def _upeh_rows(first_upeh: float | None, second_upeh: float | None) -> pd.DataFrame:
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
    assert records[0]["임시처리"] == conflict_resolution("RQ_UPEH") == ZERO_BEFORE_BLANK_RESOLUTION
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


# ------------------------- 0 행과 빈 값 행 — 효율·UPEH 는 원천 행 차례와 상관없이 0 행(2026-11-01
# 사용자 결정) 0 과 빈 값은 둘 다 「값 없음」 이라 예전에는 원천 행 차례로 골랐다. BigDataQuery
# 조회에는 차례가 없어 같은 원천이 한 번은 0(그 경로만 제외)으로, 한 번은 빈 값(계산 전체 멈춤)으로
# 저장됐다. 뜻이 확인된 두 표만 고정하고, 나머지 표는 0 의 뜻을 확인할 때까지 차례 그대로다.


def _run_rate_rows(first: float | None, second: float | None) -> pd.DataFrame:
    base = {"생산계획년월": 202606, "공정": "Process-A", "양산구분": "양산"}
    return pd.DataFrame([{**base, "CAPA_RUN_RATE": first}, {**base, "CAPA_RUN_RATE": second}])


@pytest.mark.parametrize(("first", "second"), [(0.0, None), (None, 0.0)])
def test_a_zero_run_rate_wins_over_a_blank_sibling_in_either_order(
    first: float | None, second: float | None
) -> None:
    records: list[dict[str, object]] = []

    distinct = validated_distinct(
        _run_rate_rows(first, second), "RQ_RUN_RATE", load_core_data_contract(), records
    )

    assert distinct["CAPA_RUN_RATE"].tolist() == [0.0]
    assert records[0]["임시처리"] == ZERO_BEFORE_BLANK_RESOLUTION


@pytest.mark.parametrize(("first", "second"), [(0.0, None), (None, 0.0)])
def test_a_zero_upeh_wins_over_a_blank_sibling_in_either_order(
    first: float | None, second: float | None
) -> None:
    distinct = validated_distinct(
        _upeh_rows(first, second), "RQ_UPEH", load_core_data_contract(), []
    )

    assert distinct["UPEH"].tolist() == [0.0]


def test_upeh_siblings_that_differ_only_in_which_column_is_zero_pick_the_same_row() -> None:
    """0 칸 수가 같으면 앞 값 컬럼의 0 이 이긴다 — 등록이 만드는 표의 차례(UPEH → ST)라 UPEH 0
    행이고, 어느 차례로 와도 같은 행이다."""
    rows = _upeh_rows(0.0, None)
    rows["ST"] = [None, 0.0]
    rows = rows[[*[c for c in rows.columns if c not in ("UPEH", "ST")], "UPEH", "ST"]]
    contract = load_core_data_contract()

    forward = validated_distinct(rows, "RQ_UPEH", contract, [])
    backward = validated_distinct(rows.iloc[::-1].reset_index(drop=True), "RQ_UPEH", contract, [])

    pd.testing.assert_frame_equal(forward, backward)
    assert forward["UPEH"].tolist() == [0.0]


def test_a_real_value_still_beats_zero_and_real_value_conflicts_keep_the_source_order() -> None:
    contract = load_core_data_contract()

    assert validated_distinct(_run_rate_rows(None, 0.8), "RQ_RUN_RATE", contract, [])[
        "CAPA_RUN_RATE"
    ].tolist() == [0.8]
    assert validated_distinct(_run_rate_rows(0.7, 0.8), "RQ_RUN_RATE", contract, [])[
        "CAPA_RUN_RATE"
    ].tolist() == [0.7]


def test_a_zero_in_another_column_does_not_decide_a_real_upeh_conflict() -> None:
    """UPEH 실값끼리 다른 형제는 ST 의 0 · 빈 값과 상관없이 지금처럼 원천 행 차례다.

    0 이 빈 값보다 먼저인 규칙은 0 과 빈 값만 다른 형제를 위한 것이다 — 실값 충돌의 승자까지 다른
    컬럼의 0 으로 바꾸면 결정 밖의 동작이다.
    """
    rows = _upeh_rows(50.0, 60.0)
    rows["ST"] = [0.0, None]
    contract = load_core_data_contract()

    forward = validated_distinct(rows, "RQ_UPEH", contract, [])
    backward = validated_distinct(rows.iloc[::-1].reset_index(drop=True), "RQ_UPEH", contract, [])

    assert forward["UPEH"].tolist() == [50.0]
    assert backward["UPEH"].tolist() == [60.0]


def test_other_tables_keep_the_source_order_until_their_zero_is_confirmed() -> None:
    """편중률(여유율) 같은 다른 표는 지금대로다 — 0 의 뜻을 확인하면 `ZERO_BEFORE_BLANK_TABLES` 에
    더한다."""
    contract = load_core_data_contract()
    base = {"생산계획년월": 202606, "공정": "Process-A", "양산구분": "양산"}
    zero_first = pd.DataFrame([{**base, "편중률": 0.0}, {**base, "편중률": None}])
    records: list[dict[str, object]] = []

    assert validated_distinct(zero_first, "RQ_VITAL", contract, records)["편중률"].tolist() == [0.0]
    blank_first = zero_first.iloc[::-1].reset_index(drop=True)
    assert validated_distinct(blank_first, "RQ_VITAL", contract, [])["편중률"].isna().tolist() == [
        True
    ]
    assert records[0]["임시처리"] == TEMPORARY_CONFLICT_RESOLUTION
