# Purpose: EDP-TSV 의 `Top` 을 `Top_e` 로 가르는 변환이 입력을 건드리지 않고 끝까지 가는지 지킨다.

"""`Top_e` 변환의 경계와 파급을 고정한다 (2026-09-05 지시).

두 제품군이 `Top` 이라는 같은 이름을 쓰는 것이 문제였다. 화면에서 서로 다른 두 가지가 한
이름으로 섞이고, `WF 구분` 만 보고 쓴 규칙은 양쪽에 다 걸린다. 그래서 EDP-TSV 의 `Top` 을
앱 안에서 `Top_e` 로 부른다.

**변환 지점은 `build_q_core_data` 한 곳이다.** 원천 78컬럼이 작업 프레임이 되는 경계이고,
거기서 한 번 바꾸면 16개 RQ 표·부하량·소요대수·화면이 전부 같은 값을 본다. 두 층에서
따로 바꾸면 조인 한쪽만 바뀌어 수율이나 Chip 이 조용히 안 붙는다.

**입력은 그대로 받는다.** Capa 기준정보 DB·실적 DB 어디에도 `Top_e` 는 없고,
`raw_data.core_data` 에 보존되는 원천 스냅샷도 `Top` 그대로다.
"""

import pandas as pd
from test_core_data_pipeline import _core_data_row, _display_order

from capa_simulation.services.core_data_derivation import build_q_core_data
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.product_type import (
    EDP_PRODUCT_TYPE,
    EDP_TOP_DIVISION,
    HBM_PRODUCT_TYPE,
    SOURCE_TOP_DIVISION,
    apply_edp_wf_division,
)
from capa_simulation.services.reference_transformer import build_reference_tables


def _frame(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품타입": pd.Series([t for t, _ in rows], dtype="string"),
            "WF 구분": pd.Series([d for _, d in rows], dtype="string"),
        }
    )


def test_only_the_edp_top_is_renamed() -> None:
    """HBM 의 `Top` 은 그대로 둔다. 둘을 같이 바꾸면 가른 의미가 없다."""
    result = apply_edp_wf_division(
        _frame(
            [
                (EDP_PRODUCT_TYPE, "Top"),
                (HBM_PRODUCT_TYPE, "Top"),
                (EDP_PRODUCT_TYPE, "Master"),
                (EDP_PRODUCT_TYPE, "Slave"),
                (HBM_PRODUCT_TYPE, "Dummy"),
            ]
        )
    )

    assert result["WF 구분"].tolist() == ["Top_e", "Top", "Master", "Slave", "Dummy"]


def test_surrounding_whitespace_does_not_hide_the_value() -> None:
    """원천은 공백이 붙어 오기도 한다. 놓치면 그 행만 `Top` 으로 남아 조인이 갈린다."""
    result = apply_edp_wf_division(_frame([(EDP_PRODUCT_TYPE, " Top ")]))

    assert result["WF 구분"].tolist() == [EDP_TOP_DIVISION]


def test_a_frame_without_a_product_type_is_left_alone() -> None:
    """판단 근거가 없으면 바꾸지 않는다. 추측해서 바꾸면 되돌릴 수 없다."""
    frame = pd.DataFrame({"WF 구분": pd.Series(["Top"], dtype="string")})

    assert apply_edp_wf_division(frame)["WF 구분"].tolist() == ["Top"]


def _source(product_type: str, division: str) -> pd.DataFrame:
    row = _core_data_row()
    row["제품타입"] = pd.Series([product_type], dtype="string")
    row["WF 구분"] = pd.Series([division], dtype="string")
    return row


def test_the_derivation_boundary_applies_the_rename() -> None:
    """`build_q_core_data` 가 유일한 변환 지점이다. 여기서 안 바뀌면 아무 데서도 안 바뀐다."""
    core = build_q_core_data(_source(EDP_PRODUCT_TYPE, SOURCE_TOP_DIVISION))

    assert core["WF 구분"].tolist() == [EDP_TOP_DIVISION]


def test_the_raw_input_frame_is_not_modified() -> None:
    """입력은 그대로 받는다. 원천 스냅샷이 바뀌면 다시 파생할 근거가 사라진다."""
    source = _source(EDP_PRODUCT_TYPE, SOURCE_TOP_DIVISION)

    build_q_core_data(source)

    assert source["WF 구분"].tolist() == [SOURCE_TOP_DIVISION]


def test_every_rq_table_sees_the_same_name() -> None:
    """조인 한쪽만 바뀌면 수율·Chip 이 조용히 안 붙는다. 전부 같은 값이어야 한다."""
    tables = build_reference_tables(
        _source(EDP_PRODUCT_TYPE, SOURCE_TOP_DIVISION), _display_order()
    )

    carrying = {
        name: frame
        for name, frame in tables.items()
        if "WF 구분" in frame.columns and not frame.empty
    }
    assert carrying, "WF 구분 을 싣는 RQ 표가 하나도 없다"
    for name, frame in carrying.items():
        assert set(frame["WF 구분"].dropna()) == {EDP_TOP_DIVISION}, name


def _order_rules(values: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["생산 계획"] * len(values),
            "탭 구분": ["환산"] * len(values),
            "정렬우선순위": [1] * len(values),
            "분류컬럼": ["WF 구분"] * len(values),
            "정렬방식": ["사용자지정"] * len(values),
            "분류값": values,
            "값표시순서": list(range(1, len(values) + 1)),
            "활성여부": ["Y"] * len(values),
        }
    )


def test_the_display_rule_for_top_e_is_derived_next_to_top() -> None:
    """표시순서는 입력이라 `Top_e` 규칙이 없다. 없으면 화면 맨 뒤로 조용히 밀린다."""
    data = pd.DataFrame({"WF 구분": ["Master", "Top_e", "Top", "Core"]})

    ordered = apply_display_order(
        data, _order_rules(["Top", "Core", "Master"]), "생산 계획", "환산"
    )

    assert ordered["WF 구분"].tolist() == ["Top", "Top_e", "Core", "Master"]


def test_a_hand_written_top_e_rule_is_not_duplicated() -> None:
    """사용자가 직접 넣어 두었으면 그 순서를 존중한다. 파생이 덮으면 안 된다."""
    data = pd.DataFrame({"WF 구분": ["Top_e", "Top", "Core"]})

    ordered = apply_display_order(data, _order_rules(["Top", "Core", "Top_e"]), "생산 계획", "환산")

    assert ordered["WF 구분"].tolist() == ["Top", "Core", "Top_e"]
