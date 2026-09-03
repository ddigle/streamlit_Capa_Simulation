# Purpose: scenario state 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

import pandas as pd
import pytest

from capa_simulation.scenario_state import ActiveScenario, replace_month_range, scenario_month_table


def test_replace_month_range_preserves_unselected_months() -> None:
    current = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608, 202609],
            "공정": ["A", "A", "A"],
            "값": [10.0, 20.0, 30.0],
        }
    )
    replacement = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["A"],
            "값": [99.0],
        }
    )

    result = replace_month_range(current, replacement, 202608, 202608, "TEST")

    assert result["생산계획년월"].tolist() == [202607, 202608, 202609]
    assert result["값"].tolist() == [10.0, 99.0, 30.0]


def test_replace_month_range_allows_zero_plan_to_remove_selected_rows() -> None:
    current = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608],
            "제품": ["HBM", "HBM"],
            "값": [10.0, 20.0],
        }
    )
    replacement = current.iloc[0:0].copy()

    result = replace_month_range(current, replacement, 202608, 202608, "TEST")

    assert result["생산계획년월"].tolist() == [202607]


def test_replace_month_range_rejects_rows_outside_selected_period() -> None:
    current = pd.DataFrame({"생산계획년월": [202607], "값": [1.0]})
    replacement = pd.DataFrame({"생산계획년월": [202608], "값": [2.0]})

    with pytest.raises(ValueError, match="선택 범위 밖"):
        replace_month_range(current, replacement, 202607, 202607, "TEST")


def test_scenario_month_table_copies_only_selected_rows() -> None:
    source = pd.DataFrame(
        {
            "생산계획년월": [202607, 202608, 202609],
            "값": [10.0, 20.0, 30.0],
        }
    )
    scenario: ActiveScenario = {
        "reference_version": 1,
        "revision": 2,
        "tables": {"RQ_PKG_PLAN": source},
    }

    selected = scenario_month_table(scenario, "RQ_PKG_PLAN", 202608, 202609)
    selected.loc[selected.index[0], "값"] = 999.0

    assert selected["생산계획년월"].tolist() == [202608, 202609]
    assert source["값"].tolist() == [10.0, 20.0, 30.0]
