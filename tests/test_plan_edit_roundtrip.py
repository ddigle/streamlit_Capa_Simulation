# Purpose: PKG PLAN 편집 왕복과 계산 캐시 키가 사용자의 입력과 어긋나지 않는지 고정한다.

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    attach_plan_attributes,
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
    "Pack Code": "DEMO_PK",
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


def test_plan_attributes_survive_the_apply_path() -> None:
    """편집 격자에 없는 `제품타입` 이 적용에서 사라지면 안 된다.

    사라지면 `replace_month_range` 가 "편집값에 원본 컬럼이 없습니다" 로 막고, 화면에는
    오류만 뜬 채 계획 적용이 조용히 무산된다. 실제로 그 상태가 되어 붙여넣기 적용 테스트가
    "총량이 안 바뀐다" 로 잡아냈다.
    """
    source = pd.DataFrame(
        [
            {**DIMENSIONS, "생산계획년월": 202601, "생산수량": 100.0},
            {
                **DIMENSIONS,
                "제품정보": "DEMO_P2",
                "생산계획년월": 202601,
                "생산수량": 50.0,
            },
        ]
    ).assign(제품타입=["HBM", "EDP-TSV"])
    wide = _wide(
        [
            {"제품정보": "DEMO_P1", "202601": 120.0},
            {"제품정보": "DEMO_P2", "202601": 60.0},
        ]
    )

    applied = attach_plan_attributes(plan_from_edit_table(wide), source)

    assert set(applied.columns) >= {*PLAN_EDITOR_DIMENSIONS, "제품타입"}
    by_product = dict(zip(applied["제품정보"], applied["제품타입"], strict=True))
    assert by_product == {"DEMO_P1": "HBM", "DEMO_P2": "EDP-TSV"}


def test_a_row_with_no_source_gets_no_invented_attributes() -> None:
    """붙일 원본이 없는 새 행을 아무 값으로 채우면 EDP 판별이 조용히 틀린다."""
    source = pd.DataFrame([{**DIMENSIONS, "생산계획년월": 202601, "생산수량": 100.0}]).assign(
        제품타입=["HBM"]
    )
    wide = _wide([{"제품정보": "새 제품", "202601": 10.0}])

    applied = attach_plan_attributes(plan_from_edit_table(wide), source)

    assert applied["제품타입"].isna().all()


def test_attaching_is_a_no_op_when_the_source_has_no_attributes() -> None:
    """옛 스냅샷처럼 속성 컬럼이 아예 없는 계획도 그대로 통과해야 한다."""
    source = pd.DataFrame([{**DIMENSIONS, "생산계획년월": 202601, "생산수량": 100.0}])
    long_plan = plan_from_edit_table(_wide([{"제품정보": "DEMO_P1", "202601": 10.0}]))

    assert attach_plan_attributes(long_plan, source).equals(long_plan)


def test_a_space_only_cell_reads_as_an_empty_quantity() -> None:
    """공백 한 칸(`' '`)은 빈칸과 같다 — 0 수량으로 읽는다.

    붙여넣기 검증은 `' '` 를 빈칸으로 통과시키는데 변환은 「숫자가 아닌 값」으로 표 전체를
    거부했고 어느 칸인지도 알리지 않았다(2026-09-29 횡전개 감사).
    """
    spaced = plan_from_edit_table(_wide([{"202601": " ", "202602": 20.0}]))
    empty = plan_from_edit_table(_wide([{"202601": None, "202602": 20.0}]))

    assert spaced["생산수량"].tolist() == [0.0, 20.0]
    pd.testing.assert_frame_equal(spaced, empty)


def test_a_non_numeric_plan_cell_is_still_rejected() -> None:
    """공백만 빈칸으로 읽는다. 글자가 든 칸은 여전히 거부한다."""
    with pytest.raises(ValueError, match="숫자가 아닌 값"):
        plan_from_edit_table(_wide([{"202601": "N/A"}]))
