# Purpose: 편집표의 보기 설정이 저장 대상 행을 잃지 않는지 검사한다.

from __future__ import annotations

import pandas as pd

from capa_simulation.components.table_view_controls import TableView, merge_edited_rows


def _fleet() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": ["E1", "E2", "E3", "E4"],
            "공정소분류": ["가", "나", "가", "나"],
            "비고": ["", "", "", ""],
        }
    )


def test_an_unfiltered_edit_is_the_whole_table() -> None:
    """필터가 없으면 편집표가 곧 전체 표다 — 행 추가·삭제가 살아 있어야 한다."""
    original = _fleet()
    edited = original.drop(index=1).copy()  # 사용자가 한 행을 지웠다
    edited.index = pd.RangeIndex(len(edited))

    merged = merge_edited_rows(original, edited, filtered=False)

    assert len(merged) == 3
    assert "E2" not in merged["호기"].tolist()


def test_a_filtered_edit_never_drops_the_hidden_rows() -> None:
    """**이 검사가 이 모듈의 존재 이유다.**

    편집 결과가 곧 다음 불변 리비전의 전부다. 거른 편집표를 그대로 저장하면 걸러진 행이
    되돌릴 수 없이 사라진다.
    """
    original = _fleet()
    # 「가」만 보이게 거른다. `.loc` 라 원본 인덱스가 그대로 남는다.
    visible = original.loc[original["공정소분류"] == "가"]
    assert visible.index.tolist() == [0, 2]

    edited = visible.copy()
    edited.loc[0, "비고"] = "점검"

    merged = merge_edited_rows(original, edited, filtered=True)

    assert len(merged) == len(original)
    assert merged["호기"].tolist() == ["E1", "E2", "E3", "E4"]
    assert merged.loc[0, "비고"] == "점검"
    # 보이지 않던 행은 글자 하나도 달라지지 않는다.
    pd.testing.assert_frame_equal(merged.loc[[1, 3]], original.loc[[1, 3]])


def test_editing_a_key_column_keeps_its_place() -> None:
    """키 컬럼을 고쳐도 자리를 잃지 않는다 — 인덱스로 맞추기 때문이다."""
    original = _fleet()
    visible = original.loc[[1]]
    edited = visible.copy()
    edited.loc[1, "호기"] = "E2-renamed"

    merged = merge_edited_rows(original, edited, filtered=True)

    assert merged["호기"].tolist() == ["E1", "E2-renamed", "E3", "E4"]


def test_a_filtered_view_locks_row_addition() -> None:
    """부분만 보이는 상태에서 「삭제」는 「지운다」와 「안 보인다」를 가를 수 없다."""
    assert TableView(_fleet(), filtered=True).row_mode == "fixed"
    assert TableView(_fleet(), filtered=False).row_mode == "dynamic"


def test_hidden_columns_become_a_column_config_of_none() -> None:
    """`column_config={컬럼: None}` 이 감추는 방법이다. 값은 반환 프레임에 그대로 남는다."""
    view = TableView(_fleet(), hidden_columns=("비고",), column_config={"비고": None})

    assert view.column_config == {"비고": None}
