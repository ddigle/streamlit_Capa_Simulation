# Purpose: 걸러진 월 표의 값을 원본 전체에 분류 키로 되머지하는 규칙을 검증한다.

"""필터는 보기만 좁히고 저장은 전체다.

`merge_edited_months` 는 걸러진 표의 월 값을 원본 전체에 **분류 키**로 되머지한다. 걸러진
표를 그대로 돌려주면 `scenario_state.replace_month_range` 가 조회기간의 행을 편집값으로
갈아끼우면서 화면에서 걸러진 공정을 그 기간에서 지운다. 기준 정보 그리드의 같은 계약(초안을
업무 키로 전체 양식에 덮음)은 `tests/test_reference_grid_page.py` 가 본다.
"""

import pandas as pd

from capa_simulation.components.month_editor import merge_edited_months

RUN_DAY_TABLE = pd.DataFrame(
    {
        "공정": ["Process-A", "Process-B", "Process-C"],
        "202608": [31.0, 30.0, 29.0],
        "202609": [28.0, 27.0, 26.0],
    }
)

RATIO_TABLE = pd.DataFrame(
    {
        "공정": ["Process-A", "Process-A", "Process-B"],
        "Area_Name": ["Main", "MI", "Main"],
        "양산구분": ["양산", "양산", "개발"],
        "202608": [1.0, 2.0, 3.0],
    }
)


def test_merge_edited_months_keeps_the_rows_the_filter_hid() -> None:
    """걸러진 행은 원본 값 그대로 남고, 행 수와 순서도 원본과 같다."""
    visible = RUN_DAY_TABLE.loc[RUN_DAY_TABLE["공정"].eq("Process-B")].copy()
    visible["202608"] = 15.0

    merged = merge_edited_months(RUN_DAY_TABLE, visible, ["공정"], ["202608", "202609"])

    assert merged["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert merged["202608"].tolist() == [31.0, 15.0, 29.0]
    assert merged["202609"].tolist() == [28.0, 27.0, 26.0]
    assert len(merged) == len(RUN_DAY_TABLE)


def test_merge_edited_months_returns_the_editor_frame_when_nothing_is_filtered() -> None:
    """필터가 걸리지 않으면 편집표가 곧 전체 표다. 되머지 전 동작과 같아야 한다."""
    visible = RUN_DAY_TABLE.copy()
    visible.loc[0, "202608"] = 99.0

    merged = merge_edited_months(RUN_DAY_TABLE, visible, ["공정"], ["202608", "202609"])

    pd.testing.assert_frame_equal(merged, visible)


def test_merge_edited_months_matches_by_every_tab_dimension() -> None:
    """공정만으로는 행이 갈리지 않는 탭이 있다. 되머지 키는 그 탭의 분류 컬럼 전부다."""
    dimensions = ["공정", "Area_Name", "양산구분"]
    visible = RATIO_TABLE.loc[RATIO_TABLE["Area_Name"].eq("MI")].copy()
    visible["202608"] = 9.0

    merged = merge_edited_months(RATIO_TABLE, visible, dimensions, ["202608"])

    assert merged["202608"].tolist() == [1.0, 9.0, 3.0]
    assert merged[dimensions].equals(RATIO_TABLE[dimensions])
