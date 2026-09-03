# Purpose: capacity reference editor 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

import pandas as pd

from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    performance_from_edit_table,
    performance_to_edit_table,
    reference_from_edit_table,
    reference_to_edit_table,
)

RATIO_DIMENSIONS = [
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "Area_Name",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
]


def test_performance_editor_keeps_route_sequence_identity() -> None:
    source = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "공정": ["Process-A", "Process-A"],
            "STEP_SEQ": ["P100", "P200"],
            "MCP_SEQ": ["1A", "2A"],
            "Area_Name": ["Main", "Main"],
            "소요기준": ["PKG", "PKG"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["8H", "8H"],
            "WF 구분": ["PKG", "PKG"],
            "UPEH": [100.0, 80.0],
            "ST": [float("nan"), float("nan")],
        }
    )

    edit_table = performance_to_edit_table(source)
    restored = performance_from_edit_table(edit_table)

    assert list(edit_table.columns[: len(PERFORMANCE_EDITOR_DIMENSIONS)]) == (
        PERFORMANCE_EDITOR_DIMENSIONS
    )
    assert PERFORMANCE_EDITOR_DIMENSIONS[-2:] == ["STEP_SEQ", "MCP_SEQ"]
    assert edit_table[["STEP_SEQ", "MCP_SEQ"]].to_dict("records") == [
        {"STEP_SEQ": "P100", "MCP_SEQ": "1A"},
        {"STEP_SEQ": "P200", "MCP_SEQ": "2A"},
    ]
    pd.testing.assert_frame_equal(
        restored.reindex(columns=source.columns),
        source,
        check_dtype=False,
    )


def test_ratio_editor_keeps_area_and_route_sequence_identity() -> None:
    source = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "공정": ["Process-A", "Process-A"],
            "STEP_SEQ": ["P100", "P200"],
            "MCP_SEQ": ["1A", "2A"],
            "Area_Name": ["Main", "Main"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["8H", "8H"],
            "WF 구분": ["PKG", "PKG"],
            "Lot 측정률": [1.0, 0.8],
        }
    )

    edit_table = reference_to_edit_table(
        source,
        RATIO_DIMENSIONS,
        "Lot 측정률",
        "RQ_LOT_RATIO",
    )
    restored = reference_from_edit_table(
        edit_table,
        RATIO_DIMENSIONS,
        "Lot 측정률",
        "RQ_LOT_RATIO",
    )

    pd.testing.assert_frame_equal(
        restored.reindex(columns=source.columns),
        source,
        check_dtype=False,
    )
