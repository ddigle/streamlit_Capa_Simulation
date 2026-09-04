# Purpose: PKG PLAN 편집 왕복과 계산 캐시 키가 사용자의 입력과 어긋나지 않는지 고정한다.

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    drop_unplanned_rows,
    plan_from_edit_table,
    plan_to_edit_table,
)
from capa_simulation.services.simulation_cache import build_home_simulation_cache_key

DIMENSIONS = {
    "양산구분": "양산",
    "제품정보": "DEMO_P1",
    "Stack": "8H",
    "Capa Code": "DEMO_C1",
    "Customer": "DEMO_CUST",
    "CS": "DEMO_CS",
}
DISPLAY_ORDER = pd.DataFrame(
    {"화면": ["부하량"], "컬럼": ["제품정보"], "정렬": ["오름차순"], "사용자지정순서": [None]}
)


def _wide(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame([{**DIMENSIONS, **row} for row in rows])


def test_zero_quantity_rows_survive_the_editor_roundtrip() -> None:
    """계획이 0인 달이 있어도 편집 격자에서 행이 사라지면 안 된다.

    행이 사라지면 그 제품에 다시 물량을 넣을 수 없고, 내려받은 CSV 와 행 수가 달라져
    붙여넣기가 어긋난다. 사용자가 보고한 "행 수가 변경된 경우" 의 원인이었다.
    """
    wide = _wide(
        [
            {"제품정보": "DEMO_P1", "202601": 100.0, "202602": 200.0},
            {"제품정보": "DEMO_P2", "202601": 0.0, "202602": 0.0},
            {"제품정보": "DEMO_P3", "202601": 50.0, "202602": 0.0},
        ]
    )

    rebuilt = plan_to_edit_table(plan_from_edit_table(wide))

    assert list(rebuilt["제품정보"]) == ["DEMO_P1", "DEMO_P2", "DEMO_P3"]
    assert len(rebuilt) == len(wide)
    pd.testing.assert_frame_equal(
        rebuilt[[*PLAN_EDITOR_DIMENSIONS, "202601", "202602"]].reset_index(drop=True),
        wide[[*PLAN_EDITOR_DIMENSIONS, "202601", "202602"]].reset_index(drop=True),
        check_dtype=False,
    )


def test_edited_quantities_survive_the_roundtrip() -> None:
    """사용자가 넣은 값이 그대로 돌아와야 한다."""
    wide = _wide([{"제품정보": "DEMO_P1", "202601": 0.0, "202602": 777.0}])

    rebuilt = plan_to_edit_table(plan_from_edit_table(wide))

    assert float(rebuilt.loc[0, "202601"]) == 0.0
    assert float(rebuilt.loc[0, "202602"]) == 777.0


def test_calculation_boundary_drops_unplanned_rows() -> None:
    """계산은 계획이 없는 행까지 RQ_CHIP_QTY·RQ_YLD 매칭을 요구하므로 여기서 제외한다."""
    long_plan = plan_from_edit_table(
        _wide(
            [
                {"제품정보": "DEMO_P1", "202601": 100.0},
                {"제품정보": "DEMO_P2", "202601": 0.0},
            ]
        )
    )

    assert sorted(set(long_plan["제품정보"])) == ["DEMO_P1", "DEMO_P2"]
    assert sorted(set(drop_unplanned_rows(long_plan)["제품정보"])) == ["DEMO_P1"]


def test_home_cache_key_separates_different_scenario_contents() -> None:
    """서로 다른 시나리오 내용이 같은 HOME 캐시 키를 가지면 안 된다.

    예전 키는 시나리오 편집 카운터를 썼다. 세션 편집은 0,1,2... 로 올라가고 저장 리비전을
    불러오면 그 번호가 그대로 들어와, 내용이 달라도 번호가 겹쳤다. `st.cache_data` 는
    프로세스 전역이라 다른 브라우저 세션과도 겹쳤다. 그래서 HOME 이 예전 계획의 결과를
    그대로 보여줬다.
    """
    common = {
        "reference_version": 1,
        "start_month": 202601,
        "end_month": 202612,
        "display_order": DISPLAY_ORDER,
    }

    first = build_home_simulation_cache_key(scenario_token="token-a", **common)
    second = build_home_simulation_cache_key(scenario_token="token-b", **common)
    same = build_home_simulation_cache_key(scenario_token="token-a", **common)

    assert first != second
    assert first == same


def test_active_scenario_issues_a_new_token_on_every_change() -> None:
    """시나리오 테이블이 바뀔 때마다 토큰이 새로 발급되어야 캐시가 갈린다."""
    pytest.importorskip("streamlit")
    from capa_simulation import scenario_state

    tokens = {scenario_state._new_content_token() for _ in range(50)}

    assert len(tokens) == 50
