# Purpose: 실행 Capa 반영의 값 정규화와 퍼센트포인트 차감 적용을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    apply_execution_adjustment,
    clamped_execution_adjustments,
    empty_execution_capacity,
    prepare_execution_capacity,
    unmatched_execution_adjustments,
)


def _rows(records: list[tuple[int, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=list(EXECUTION_CAPACITY_COLUMNS))


def _securement(records: list[tuple[int, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["생산계획년월", "공정", "확보율"])


def test_adjustment_is_percentage_points_not_a_ratio() -> None:
    """105% 에 -10 을 넣으면 95% 다. 비율 곱셈이면 94.5% 가 나온다.

    목적이 '비가동대수가 늘어 가용대수가 줄었다' 같은 변수를 확보율에 바로 얹는 것이라
    입력 숫자가 화면 퍼센트와 같은 눈금이어야 한다.
    """
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 1.05)]),
        _rows([(202607, "DEMO_A", -10.0, "비가동 3대")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.95)
    assert adjusted.loc[0, "기준 확보율"] == pytest.approx(1.05)
    assert adjusted.loc[0, "확보율 증감"] == pytest.approx(-10.0)
    assert adjusted.loc[0, "실행 비고"] == "비가동 3대"


def test_baseline_columns_exist_even_with_no_adjustment() -> None:
    """조정 0건이어도 세 컬럼을 만든다. 뒤의 순위·Figure 가 컬럼 유무로 갈라지면 안 된다."""
    securement = _securement([(202607, "DEMO_A", 1.05), (202608, "DEMO_B", 0.80)])

    adjusted = apply_execution_adjustment(securement, empty_execution_capacity())

    assert {"기준 확보율", "확보율 증감", "실행 비고"} <= set(adjusted.columns)
    assert adjusted["확보율"].tolist() == securement["확보율"].tolist()
    assert adjusted["확보율 증감"].eq(0.0).all()


def test_only_the_matching_month_and_process_moves() -> None:
    """년월과 공정이 **둘 다** 같은 행만 움직인다."""
    adjusted = apply_execution_adjustment(
        _securement(
            [
                (202607, "DEMO_A", 1.00),
                (202608, "DEMO_A", 1.00),
                (202607, "DEMO_B", 1.00),
            ]
        ),
        _rows([(202607, "DEMO_A", -20.0, "")]),
    )

    assert adjusted["확보율"].tolist() == pytest.approx([0.80, 1.00, 1.00])


def test_zero_rows_are_dropped_but_a_clearing_save_is_still_valid() -> None:
    """증감 0 은 '넣지 않은 행' 이다. 지정하지 않은 것과 결과가 같다."""
    prepared = prepare_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, "유지"), (202607, "DEMO_B", 0.0, "버려짐")])
    )

    assert prepared["공정"].tolist() == ["DEMO_A"]
    assert prepare_execution_capacity(empty_execution_capacity()).empty


def test_duplicate_month_and_process_is_rejected() -> None:
    """같은 달·공정이 두 번 들어오면 어느 값이 맞는지 알 수 없다."""
    with pytest.raises(ValueError, match="같은 달·공정이 두 번"):
        prepare_execution_capacity(
            _rows([(202607, "DEMO_A", -10.0, ""), (202607, "DEMO_A", -5.0, "")])
        )


def test_month_must_be_yyyymm() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        prepare_execution_capacity(_rows([(202613, "DEMO_A", -10.0, "")]))


def test_process_is_normalized_so_stray_spaces_still_match() -> None:
    """공정은 원본 코드 기준이고 정규화는 저장·조회가 같은 함수를 쓴다."""
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 1.00)]),
        _rows([(202607, "  DEMO_A  ", -10.0, "")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.90)


def test_negative_result_is_clamped_at_zero_and_reported() -> None:
    """음수 확보율은 막대 길이도 순위도 무의미해진다. 0 에서 자르고 알린다."""
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 0.05)]),
        _rows([(202607, "DEMO_A", -20.0, "재공 부진")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.0)
    clamped = clamped_execution_adjustments(adjusted)
    assert clamped["공정"].tolist() == ["DEMO_A"]


def test_rows_without_a_match_are_reported_not_rejected() -> None:
    """공용 프로필이라 다른 시나리오에서는 유효할 수 있다. 저장은 막지 않고 알린다."""
    securement = _securement([(202607, "DEMO_A", 1.00)])
    rows = _rows([(202607, "DEMO_A", -10.0, ""), (202609, "DEMO_Z", -5.0, "다른 시나리오")])

    unmatched = unmatched_execution_adjustments(securement, rows)

    assert unmatched["공정"].tolist() == ["DEMO_Z"]
    # 매칭되는 행은 정상 적용된다.
    assert apply_execution_adjustment(securement, rows).loc[0, "확보율"] == pytest.approx(0.90)


def test_column_contract_is_enforced() -> None:
    with pytest.raises(ValueError, match="컬럼 계약"):
        prepare_execution_capacity(pd.DataFrame({"생산계획년월": [202607]}))
