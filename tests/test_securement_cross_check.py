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


def two_month_frame(values: dict[tuple[int, str], float], column: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [month for month, _ in values],
            "공정": [process for _, process in values],
            column: list(values.values()),
        }
    )


def test_months_the_dynamic_side_does_not_cover_are_left_out() -> None:
    """**설비 조회기간과 시나리오 조회기간은 다른 위젯이다.**

    좁히지 않으면 시나리오 쪽에만 있는 달에서 모든 공정이 Static 으로 채워지고, 그
    공정들이 「Cut-off 가 없다」로 잘못 보고된다 — 실제로는 Cut-off 가 다 적혀 있다.
    """
    static = two_month_frame({(202609, "A"): 10.0, (202610, "A"): 10.0}, "가용대수")
    required = two_month_frame({(202609, "A"): 20.0, (202610, "A"): 20.0}, "소요대수")
    # Dynamic 은 10월만 덮는다.
    dynamic = frame({"A": 8.0}, "가용대수")

    check = build_securement_cross_check(static, dynamic, required)

    assert check.months == [202610]
    assert check.fallback_processes == [], "10월은 Dynamic 이 덮으므로 채울 것이 없다"
    assert check.compared_processes == ["A"]
    assert set(check.rows["생산계획년월"]) == {202610}


def test_a_genuinely_missing_process_is_still_reported() -> None:
    """달을 좁혀도 그 달에 Cut-off 가 없는 공정은 여전히 채움으로 잡혀야 한다."""
    static = two_month_frame({(MONTH, "A"): 10.0, (MONTH, "B"): 6.0}, "가용대수")
    required = two_month_frame({(MONTH, "A"): 20.0, (MONTH, "B"): 12.0}, "소요대수")
    dynamic = frame({"A": 8.0}, "가용대수")

    check = build_securement_cross_check(static, dynamic, required)

    assert check.months == [MONTH]
    assert check.fallback_processes == ["B"]


def test_a_process_only_on_the_dynamic_side_is_listed_not_compared() -> None:
    """기준정보에 없는 공정은 소요대수·Static 이 없어 맞댈 수 없다(2026-10-01).

    행으로 싣던 때는 Dynamic 가용대수 한 칸 말고 모두 빈 행이 「실제로 비교한 공정」으로
    세어졌다 — 맞댄 공정이 0개인데 수십 개로 보고됐다(브라우저 재현).
    """
    check = build_securement_cross_check(
        frame({"A": 10.0}, "가용대수"),
        frame({"A": 8.0, " Die Attach ": 49.0}, "가용대수"),
        frame({"A": 20.0}, "소요대수"),
    )

    assert set(check.rows["공정"]) == {"A"}
    assert check.compared_processes == ["A"]
    assert check.dynamic_only_processes == ["Die Attach"]
    assert check.fallback_processes == []


def test_only_fallback_and_dynamic_only_processes_compare_nothing() -> None:
    """실측 모양 — Static 쪽 공정은 모두 채움이고 Dynamic 쪽 공정은 모두 기준정보에 없다."""
    check = build_securement_cross_check(
        frame({"DEMO_A": 10.0}, "가용대수"),
        frame({"Die Attach": 49.0, "AVI": 21.0}, "가용대수"),
        frame({"DEMO_A": 20.0}, "소요대수"),
    )

    assert check.fallback_processes == ["DEMO_A"]
    assert check.compared_processes == []
    assert check.dynamic_only_processes == ["AVI", "Die Attach"]
    assert set(check.rows["공정"]) == {"DEMO_A"}
    assert check.rows["소요대수"].notna().all()


def test_months_static_does_not_cover_are_not_counted_as_compared() -> None:
    """Dynamic 이 Static 보다 긴 달까지 덮으면 넘친 달은 행에서 빠진다 — 달 수도 그만 센다.

    캡션 「맞대어 본 달 (N개월)」이 행에 없는 달까지 세어 결과와 어긋났다(2026-10-01 검토 실측).
    """
    static = two_month_frame({(202611, "A"): 10.0, (202612, "A"): 10.0}, "가용대수")
    required = two_month_frame({(202611, "A"): 20.0, (202612, "A"): 20.0}, "소요대수")
    dynamic = two_month_frame(
        {(202611, "A"): 8.0, (202612, "A"): 8.0, (202701, "A"): 8.0, (202702, "A"): 8.0},
        "가용대수",
    )

    check = build_securement_cross_check(static, dynamic, required)

    assert set(check.rows["생산계획년월"]) == {202611, 202612}
    assert check.months == [202611, 202612]
