# Purpose: 계산 계약보다 앞선 리비전을 불러오기 전에 가려내는 규칙을 고정한다.

import pandas as pd
import pytest
from custom_key_tables import custom_keyed_tables as custom_keyed_tables_from_contract

from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.revision_compatibility import (
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
