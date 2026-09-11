# Purpose: 계산 계약보다 앞선 리비전을 불러오기 전에 가려내는 규칙을 고정한다.

import pandas as pd

from capa_simulation.services.revision_compatibility import (
    revision_block_reason,
    route_key_incompatible_tables,
)


def _upeh(step_seq: object, mcp_seq: object) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202601],
            "공정": ["P-A"],
            "STEP_SEQ": [step_seq],
            "MCP_SEQ": [mcp_seq],
            "UPEH": [10.0],
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
