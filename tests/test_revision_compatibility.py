# Purpose: 계산 계약보다 앞선 리비전을 불러오기 전에 가려내는 규칙을 고정한다.

import pandas as pd
import pytest
from custom_key_tables import custom_keyed_tables as custom_keyed_tables_from_contract

from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.revision_compatibility import (
    BEFORE_CUSTOM_COPY,
    CUSTOM_MIGRATION,
    custom_blank_filled,
    custom_incompatible_tables,
    custom_keyed_tables,
    revision_block_reason,
    route_key_incompatible_tables,
)


def _upeh(step_seq: object, mcp_seq: object, custom: object = CUSTOM_BLANK) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202601],
            "공정": ["P-A"],
            "STEP_SEQ": [step_seq],
            "MCP_SEQ": [mcp_seq],
            "UPEH": [10.0],
            "CUSTOM": [custom],
        }
    )


def test_a_revision_saved_before_the_route_keys_is_blocked() -> None:
    """경로 키가 빈 리비전을 활성화하면 계산이 첫 줄에서 멈추고 되돌릴 방법이 없다."""
    tables = {"RQ_UPEH": _upeh(None, None)}

    assert route_key_incompatible_tables(tables) == ["RQ_UPEH"]
    reason = revision_block_reason(tables)
    assert reason is not None
    assert "STEP·MCP" in reason


def test_an_empty_string_key_counts_as_missing() -> None:
    """빈 문자열도 조인 키로 쓸 수 없다. null 만 보면 절반을 놓친다."""
    assert route_key_incompatible_tables({"RQ_UPEH": _upeh("", "")}) == ["RQ_UPEH"]


def test_a_revision_with_route_keys_passes() -> None:
    tables = {"RQ_UPEH": _upeh("S1", "M1")}

    assert route_key_incompatible_tables(tables) == []
    assert revision_block_reason(tables) is None


def test_a_table_without_the_columns_at_all_is_blocked() -> None:
    """컬럼 자체가 없는 저장분도 같은 이유로 못 쓴다."""
    tables = {"RQ_UPEH": pd.DataFrame({"생산계획년월": [202601], "공정": ["P-A"]})}

    assert route_key_incompatible_tables(tables) == ["RQ_UPEH"]


def test_an_empty_table_is_not_a_reason_to_block() -> None:
    """행이 없으면 키가 빌 일도 없다. 빈 표를 막으면 정상 저장분이 걸린다."""
    empty = pd.DataFrame(columns=["생산계획년월", "공정", "STEP_SEQ", "MCP_SEQ"])

    assert route_key_incompatible_tables({"RQ_UPEH": empty}) == []


def test_the_custom_safety_net_covers_the_contract_custom_tables() -> None:
    """칸을 더한 표 목록은 새 상수가 아니라 계약에서 낸다 — 계약의 CUSTOM 키 표 전부다."""
    assert custom_keyed_tables() == custom_keyed_tables_from_contract()
    assert "RQ_UPEH" in custom_keyed_tables() and "RQ_RUN_RATE" not in custom_keyed_tables()


@pytest.mark.parametrize("custom", [None, "", "  ", pd.NA])
def test_a_blank_custom_value_blocks_the_revision(custom: object) -> None:
    """빈 CUSTOM 을 표지로 채우면 다른 부품 행이 한 줄로 접힐 수 있다 — 채우지 않고 막는다."""
    tables = {"RQ_UPEH": _upeh("S1", "M1", custom)}

    assert custom_incompatible_tables(tables) == ["RQ_UPEH"]
    reason = revision_block_reason(tables)
    assert reason is not None and "CUSTOM" in reason
    assert "STEP·MCP" not in reason


def test_a_table_without_the_custom_column_blocks_the_revision() -> None:
    tables = {"RQ_UPEH": _upeh("S1", "M1").drop(columns=["CUSTOM"])}

    assert custom_incompatible_tables(tables) == ["RQ_UPEH"]


def test_the_blank_marker_and_part_values_pass() -> None:
    """빈 값 표지는 값이다 — 0039 가 옛 행에 넣은 그대로 통과한다."""
    tables = {
        "RQ_UPEH": pd.concat(
            [_upeh("S1", "M1"), _upeh("S1", "M1", "DEMO_CUSTOM_A")], ignore_index=True
        )
    }

    assert custom_incompatible_tables(tables) == []
    assert revision_block_reason(tables) is None


def test_both_reasons_are_given_when_both_contracts_fail() -> None:
    reason = revision_block_reason({"RQ_UPEH": _upeh(None, None, None)})

    assert reason is not None
    assert "STEP·MCP" in reason and "CUSTOM" in reason


def test_the_custom_migration_number_is_the_migration_that_adds_the_column() -> None:
    """확인 스크립트가 견주는 번호는 CUSTOM 칸을 더한 그 마이그레이션이고, 표지 글자도 그 번호다."""
    migration = next(item for item in load_migrations() if item.version == CUSTOM_MIGRATION)

    assert migration.name == "0039_custom_product_key.sql"
    assert BEFORE_CUSTOM_COPY == "사본 0039 전"


def test_the_blank_filler_adds_the_marker_only_where_a_custom_table_has_no_column() -> None:
    """0039 와 같은 뜻 — 칸이 없는 CUSTOM 키 표(빈 표 포함)에만 표지 칸을 끝에 붙인다.

    칸이 있는 표는 빈 값이 있어도 같은 객체 그대로다(그것은 안전망이 막는다). CUSTOM 키 표가 아닌
    표 · 받지 않은 표는 건드리지 않고, 받은 표는 고치지 않는다."""
    old_upeh = _upeh("S1", "M1").drop(columns=["CUSTOM"])
    blank_ratio = _upeh("S1", "M1", None)
    run_rate = pd.DataFrame({"생산계획년월": [202601], "공정": ["P-A"], "CAPA_RUN_RATE": [0.9]})
    empty_yield = pd.DataFrame(columns=["생산계획년월", "제품정보", "Stack", "WF 구분", "수율"])
    tables = {
        "RQ_UPEH": old_upeh,
        "RQ_LOT_RATIO": blank_ratio,
        "RQ_RUN_RATE": run_rate,
        "RQ_YLD": empty_yield,
    }

    filled = custom_blank_filled(tables)

    assert list(filled) == list(tables)
    assert list(filled["RQ_UPEH"].columns) == [*old_upeh.columns, "CUSTOM"]
    assert filled["RQ_UPEH"]["CUSTOM"].tolist() == [CUSTOM_BLANK]
    pd.testing.assert_frame_equal(filled["RQ_UPEH"].drop(columns=["CUSTOM"]), old_upeh)
    assert list(filled["RQ_YLD"].columns) == [*empty_yield.columns, "CUSTOM"]
    assert filled["RQ_YLD"].empty
    assert filled["RQ_LOT_RATIO"] is blank_ratio
    assert filled["RQ_RUN_RATE"] is run_rate
    assert "CUSTOM" not in old_upeh.columns and "CUSTOM" not in empty_yield.columns
    assert custom_incompatible_tables(filled) == ["RQ_LOT_RATIO"]


def test_a_filled_copy_passes_the_safety_net_like_a_migrated_revision() -> None:
    """채운 0039 전 표는 0039 뒤 저장분처럼 안전망을 지나고, 불러오기를 막을 이유가 없다."""
    tables = {"RQ_UPEH": _upeh("S1", "M1").drop(columns=["CUSTOM"])}

    assert custom_incompatible_tables(tables) == ["RQ_UPEH"]
    assert revision_block_reason(custom_blank_filled(tables)) is None
