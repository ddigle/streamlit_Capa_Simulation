# Purpose: capacity reference editor 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd

from capa_simulation.services.capacity_reference_editor import (
    PERFORMANCE_EDITOR_DIMENSIONS,
    performance_from_edit_table,
    performance_to_edit_table,
    reference_from_edit_table,
    reference_to_edit_table,
)
from capa_simulation.services.route_step_editor import route_step_catalog

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


def _upeh_source() -> pd.DataFrame:
    """Main 행에 ST 가, MI 행에 UPEH 가 함께 있고 `Area_Name` 이 원천 표기(`MAIN`·`mi`)다.

    값이 빈 BOX 행은 계산이 쓰지 않아 비어 있어도 되는 실재 행이다.
    """
    base = {
        "공정": "Process-A",
        "Area_Name": "MAIN",
        "소요기준": "PKG",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "BUFFER",
        "STEP_SEQ": "P100",
        "MCP_SEQ": "1A",
    }
    mi = {**base, "Area_Name": "mi", "STEP_SEQ": "P200"}
    box = {**base, "소요기준": "BOX", "STEP_SEQ": "P900", "MCP_SEQ": "9A"}
    return pd.DataFrame(
        [
            {"생산계획년월": 202608, **base, "UPEH": 100.0, "ST": 36.0},
            {"생산계획년월": 202609, **base, "UPEH": 110.0, "ST": 37.0},
            {"생산계획년월": 202608, **mi, "UPEH": 5.0, "ST": 40.0},
            {"생산계획년월": 202608, **box, "UPEH": None, "ST": None},
        ]
    )[["생산계획년월", *PERFORMANCE_EDITOR_DIMENSIONS, "UPEH", "ST"]]


def _by_route(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["생산계획년월", "STEP_SEQ"], kind="stable").reset_index(drop=True)


def test_an_untouched_upeh_apply_gives_back_the_source_rows() -> None:
    """아무것도 안 고친 왕복은 원본 그대로다(결함 6).

    원본을 넘기지 않던 때는 Main 행의 ST·MI 행의 UPEH 가 NaN 이 되고, 값이 빈 BOX 행이 지워지고,
    `MAIN` 이 `Main` 으로 저장돼 `RQ_REQB` 와 정확 일치로 붙는 STEP 목록이 비었다.
    """
    source = _upeh_source()
    reqb = source.loc[[0], ["생산계획년월", *PERFORMANCE_EDITOR_DIMENSIONS]].assign(
        **{"Capa Code": "CAPA-A", "Customer": "Customer-A", "CS": "MP"}
    )

    restored = performance_from_edit_table(performance_to_edit_table(source), source)

    pd.testing.assert_frame_equal(_by_route(restored), _by_route(source), check_dtype=False)
    assert len(route_step_catalog(restored, reqb)) == len(route_step_catalog(source, reqb)) == 1


def test_an_upeh_edit_changes_only_the_cells_it_touched() -> None:
    """고친 칸만 바뀐다.

    값이 있던 칸을 비우면 그 행이 빠지고, 빈 달을 채운 행은 같은 경로의 원본 표기를 따른다.
    """
    source = _upeh_source()
    edit_table = performance_to_edit_table(source)
    p100 = edit_table["STEP_SEQ"].eq("P100")
    p200 = edit_table["STEP_SEQ"].eq("P200")
    edit_table.loc[p100, "202608"] = 120.0
    edit_table.loc[p100, "202609"] = None
    edit_table.loc[p200, "202609"] = 41.0

    restored = _by_route(performance_from_edit_table(edit_table, source))

    records = restored.to_dict("records")
    assert [(row["생산계획년월"], row["STEP_SEQ"]) for row in records] == [
        (202608, "P100"),
        (202608, "P200"),
        (202608, "P900"),
        (202609, "P200"),
    ]
    # Main 은 UPEH 만 고쳤고 ST 는 원본이다.
    assert (records[0]["Area_Name"], records[0]["UPEH"], records[0]["ST"]) == ("MAIN", 120.0, 36.0)
    # 고치지 않은 MI 행은 UPEH 까지 원본이다.
    assert (records[1]["UPEH"], records[1]["ST"]) == (5.0, 40.0)
    # 값이 빈 BOX 행은 그대로 남는다.
    assert pd.isna(records[2]["UPEH"]) and pd.isna(records[2]["ST"])
    # 새로 채운 MI 의 202609 는 같은 경로의 원본 표기(`mi`)로 ST 에 들어간다.
    assert records[3]["Area_Name"] == "mi"
    assert pd.isna(records[3]["UPEH"]) and records[3]["ST"] == 41.0
