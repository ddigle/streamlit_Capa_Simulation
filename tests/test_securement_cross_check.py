# Purpose: Static·Dynamic 확보율 교차검증의 산식과 Static 대체 보고를 검사한다.

"""**채워 넣은 자리를 「차이 없음」으로 읽으면 안 된다.**

Dynamic 은 Cut-off 를 적은 공정만 덮는다. 나머지는 Static 값으로 채우는데, 그 행의
차이는 언제나 0 이다 — 두 값을 맞댄 것이 아니라 같은 값을 두 번 본 것이다. 화면이
그 구분을 드러낼 수 있도록 서비스가 목록을 돌려주는지 여기서 지킨다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.securement_cross_check import (
    build_securement_cross_check,
    dynamic_available_equipment,
)

MONTH = 202610


def frame(process_values: dict[str, float], column: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [MONTH] * len(process_values),
            "공정": list(process_values),
            column: list(process_values.values()),
        }
    )


def test_both_rates_come_from_the_same_required_count() -> None:
    """같은 소요대수에 두 가용대수를 각각 나눈다 — 분모가 갈리면 비교가 아니다."""
    check = build_securement_cross_check(
        frame({"A": 10.0}, "가용대수"),
        frame({"A": 8.0}, "가용대수"),
        frame({"A": 20.0}, "소요대수"),
    )

    row = check.rows.iloc[0]
    assert float(row["소요대수"]) == 20.0
    assert float(row["Static확보율"]) == 0.5
    assert float(row["Dynamic확보율"]) == 0.4
    assert round(float(row["확보율차이"]), 6) == -0.1
    assert not bool(row["Static대체"])
    assert check.fallback_processes == []


def test_a_process_without_a_cutoff_is_filled_and_reported() -> None:
    """Dynamic 이 못 덮는 공정은 Static 으로 채우되 목록으로 알린다."""
    check = build_securement_cross_check(
        frame({"A": 10.0, "B": 6.0}, "가용대수"),
        frame({"A": 8.0}, "가용대수"),
        frame({"A": 20.0, "B": 12.0}, "소요대수"),
    )

    assert check.fallback_processes == ["B"]
    assert check.compared_processes == ["A"]

    filled = check.rows.loc[check.rows["공정"] == "B"].iloc[0]
    assert float(filled["Static확보율"]) == float(filled["Dynamic확보율"]) == 0.5
    assert float(filled["확보율차이"]) == 0.0
    assert bool(filled["Static대체"])


def test_filling_keeps_the_other_process_comparable() -> None:
    """채우기가 없으면 예외로 멈춰 나머지 비교도 못 본다 — 그래서 채운다."""
    check = build_securement_cross_check(
        frame({"A": 10.0, "B": 6.0}, "가용대수"),
        frame({"A": 8.0}, "가용대수"),
        frame({"A": 20.0, "B": 12.0}, "소요대수"),
    )

    compared = check.rows.loc[check.rows["공정"] == "A"].iloc[0]
    assert round(float(compared["확보율차이"]), 6) == -0.1


def test_a_process_missing_from_static_too_is_filled_with_zero() -> None:
    """Static 에도 없으면 0 으로 채운다. 그 행은 Dynamic 이 0 이라고 말하는 것이 아니다."""
    check = build_securement_cross_check(
        frame({"A": 10.0}, "가용대수"),
        pd.DataFrame({"생산계획년월": [], "공정": [], "가용대수": []}),
        frame({"A": 20.0}, "소요대수"),
    )

    assert check.fallback_processes == ["A"]
    assert check.compared_processes == []


def test_the_weighted_axis_is_the_default() -> None:
    """확보율은 능력을 재는 값이라 분자도 환산비를 반영한 축이어야 한다."""
    monthly = pd.DataFrame(
        {
            "생산계획년월": [MONTH, MONTH],
            "공정": ["A", "A"],
            "분류": ["기존보유", "가용"],
            "대수": [4.0, 1.0],
            "환산대수": [4.0, 1.5],
            "부호": [1, 1],
            "가용반영": [True, True],
        }
    )

    weighted = dynamic_available_equipment(monthly)
    plain = dynamic_available_equipment(monthly, weighted=False)

    assert float(weighted["가용대수"].iloc[0]) == 5.5
    assert float(plain["가용대수"].iloc[0]) == 5.0


def test_an_empty_monthly_frame_gives_an_empty_availability() -> None:
    empty = pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "대수": pd.Series(dtype="float64"),
            "환산대수": pd.Series(dtype="float64"),
            "부호": pd.Series(dtype="int64"),
            "가용반영": pd.Series(dtype="bool"),
        }
    )

    assert dynamic_available_equipment(empty).empty
