# Purpose: scenario state 관련 정상·예외·회귀 동작을 검증한다.

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


def test_apply_month_updates_issues_a_new_content_token() -> None:
    """편집할 때마다 토큰이 새로 나와야 HOME 계산 캐시가 갈린다.

    `revision` 은 저장본과 비교해 미저장 변경을 감지하는 카운터라서 서로 다른 내용이
    같은 번호를 가질 수 있다. 세션 편집은 0,1,2... 로 올라가고 저장 리비전을 불러오면
    그 번호가 그대로 들어온다. 그 번호를 캐시 키로 쓰던 것이 HOME 이 예전 계획의 결과를
    보여주던 원인이었다.
    """
    import streamlit as st

    from capa_simulation.scenario_state import apply_month_updates

    source = pd.DataFrame({"생산계획년월": [202607, 202608], "값": [10.0, 20.0]})
    scenario: ActiveScenario = {
        "reference_version": 1,
        "revision": 2,
        "content_token": "before",
        "tables": {"RQ_PKG_PLAN": source},
    }
    replacement = pd.DataFrame({"생산계획년월": [202608], "값": [99.0]})

    try:
        updated = apply_month_updates(scenario, {"RQ_PKG_PLAN": replacement}, 202608, 202608)
    finally:
        st.session_state.clear()

    assert updated["content_token"] != scenario["content_token"]
    assert updated["revision"] == scenario["revision"] + 1
    assert updated["tables"]["RQ_PKG_PLAN"]["값"].tolist() == [10.0, 99.0]
