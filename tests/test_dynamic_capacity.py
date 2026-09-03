# Purpose: dynamic capacity 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
    calculate_dynamic_capacity,
    filter_dynamic_capacity,
)


def _input_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "일자": date(2026, 8, 1),
        "공정": "Test",
        "제품정보": "HBM라",
        "Stack": "12H",
        "WF 구분": "Core",
        "소요기준": "WF",
        "표준 Capa": 100.0,
        "표준 효율": 0.80,
        "실적 효율": 0.72,
        "표준 UPEH": 10.0,
        "실적 UPEH": 9.0,
        "계획시간": 8.0,
        "실가동시간": 6.0,
        "Rundown 시간": 3.0,
        "설비 Down 시간": 1.0,
        "기타 제약시간": 0.0,
        "실적수량": 50.0,
    }
    row.update(overrides)
    return row


def test_dynamic_capacity_bridge_balances_to_actual() -> None:
    result = calculate_dynamic_capacity(pd.DataFrame([_input_row()]))
    row = result.iloc[0]

    assert row["효율 반영 Capa"] == pytest.approx(90.0)
    assert row["실효 Capa"] == pytest.approx(81.0)
    assert row["모델 실적 Capa"] == pytest.approx(54.0)
    assert row["효율 손실 Capa"] == pytest.approx(10.0)
    assert row["UPEH 손실 Capa"] == pytest.approx(9.0)
    assert row["재공부족 미활용 Capa"] == pytest.approx(27.0)
    assert row["기타 정합성 Gap"] == pytest.approx(4.0)
    assert (
        row["표준 Capa"]
        - row["효율 손실 Capa"]
        - row["UPEH 손실 Capa"]
        - row["재공부족 미활용 Capa"]
        - row["기타 정합성 Gap"]
    ) == pytest.approx(row["실적수량"])


def test_dynamic_capacity_aggregation_uses_time_weighted_rates() -> None:
    detail = calculate_dynamic_capacity(
        pd.DataFrame(
            [
                _input_row(),
                _input_row(
                    일자=date(2026, 8, 2),
                    **{
                        "표준 Capa": 50.0,
                        "실적 효율": 0.76,
                        "실적 UPEH": 8.0,
                        "계획시간": 4.0,
                        "실가동시간": 2.0,
                        "Rundown 시간": 1.0,
                        "실적수량": 18.0,
                    },
                ),
            ]
        )
    )

    summary = aggregate_dynamic_capacity(detail, ["공정"]).iloc[0]

    assert summary["표준 Capa"] == pytest.approx(150.0)
    assert summary["실적 효율"] == pytest.approx((0.72 * 8 + 0.76 * 4) / 12)
    assert summary["실적 UPEH"] == pytest.approx((9.0 * 6 + 8.0 * 2) / 8)
    assert summary["Capa 실현률"] == pytest.approx(68.0 / 150.0)


def test_dynamic_capacity_demo_filters_process_product_and_date() -> None:
    demo = build_dynamic_capacity_demo()
    filtered = filter_dynamic_capacity(
        demo,
        start_date=date(2026, 8, 16),
        end_date=date(2026, 8, 18),
        process="Wafer Sorter",
        product="HBM라",
    )

    assert len(filtered) == 3
    assert filtered["공정"].eq("Wafer Sorter").all()
    assert filtered["제품정보"].eq("HBM라").all()
    assert filtered["일자"].min() == pd.Timestamp("2026-08-16")
    assert filtered["일자"].max() == pd.Timestamp("2026-08-18")


def test_dynamic_capacity_demo_has_one_requirement_basis_per_process() -> None:
    demo = build_dynamic_capacity_demo()
    assert demo.groupby("공정")["소요기준"].nunique().le(1).all()
