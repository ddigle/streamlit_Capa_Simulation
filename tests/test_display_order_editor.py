import pandas as pd
import pytest

from capa_simulation.services.display_order import (
    classification_columns_in_display_order,
)
from capa_simulation.services.display_order_csv import (
    display_order_from_clipboard,
    display_order_from_csv,
    display_order_to_csv,
)
from capa_simulation.services.display_order_editor import (
    ensure_route_sequence_rules,
    replace_display_order_scope,
    validate_display_order,
)


def _rules() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["HOME", "HOME", "HOME"],
            "탭 구분": ["계획", "계획", "Capa"],
            "정렬우선순위": [1, 1, 1],
            "분류컬럼": ["제품정보", "제품정보", "공정"],
            "정렬방식": ["사용자지정", "사용자지정", "오름차순"],
            "분류값": ["A", "B", pd.NA],
            "값표시순서": [1, 2, pd.NA],
            "활성여부": ["Y", "Y", "Y"],
        }
    )


def test_replace_display_order_scope_preserves_other_scopes() -> None:
    edited = pd.DataFrame(
        {
            "정렬우선순위": [1, 1],
            "분류컬럼": ["제품정보", "제품정보"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["B", "A"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }
    )

    result = replace_display_order_scope(_rules(), "HOME", "계획", edited)

    plan = result.loc[result["탭 구분"].eq("계획")]
    assert plan["분류값"].tolist() == ["B", "A"]
    assert result.loc[result["탭 구분"].eq("Capa"), "분류컬럼"].tolist() == ["공정"]


def test_display_order_rejects_duplicate_custom_order() -> None:
    source = _rules()
    source.loc[1, "값표시순서"] = 1

    with pytest.raises(ValueError, match="값표시순서.*중복"):
        validate_display_order(source)


def test_display_order_csv_round_trip_supports_utf8_and_cp949() -> None:
    source = validate_display_order(_rules())

    utf8 = display_order_from_csv(display_order_to_csv(source))
    cp949 = display_order_from_csv(source.to_csv(index=False).encode("cp949"))

    pd.testing.assert_frame_equal(utf8, source)
    pd.testing.assert_frame_equal(cp949, source)


def test_display_order_clipboard_round_trip() -> None:
    source = validate_display_order(_rules())

    result = display_order_from_clipboard(source.to_csv(index=False, sep="\t"))

    pd.testing.assert_frame_equal(result, source)


def test_display_order_csv_rejects_changed_columns() -> None:
    invalid = _rules().rename(columns={"분류컬럼": "잘못된 컬럼"})

    with pytest.raises(ValueError, match="컬럼 계약"):
        display_order_from_csv(invalid.to_csv(index=False).encode("utf-8-sig"))


def test_route_sequence_rules_are_added_as_the_final_hierarchy() -> None:
    source = pd.DataFrame(
        {
            "페이지 구분": ["공정별 확보율", "공정별 확보율", "공정별 확보율"],
            "탭 구분": ["소요대수", "소요대수", "소요대수"],
            "정렬우선순위": [1, 2, 3],
            "분류컬럼": ["Area_Name", "공정", "제품정보"],
            "정렬방식": ["오름차순", "오름차순", "오름차순"],
            "분류값": [pd.NA, pd.NA, pd.NA],
            "값표시순서": [pd.NA, pd.NA, pd.NA],
            "활성여부": ["Y", "Y", "Y"],
        }
    )

    result = ensure_route_sequence_rules(source)

    scope = result.sort_values("정렬우선순위", kind="stable")
    assert scope["분류컬럼"].tolist() == [
        "Area_Name",
        "공정",
        "제품정보",
        "STEP_SEQ",
        "MCP_SEQ",
    ]
    assert scope["정렬우선순위"].tolist() == [1, 2, 3, 4, 5]


def test_classification_columns_follow_rules_but_keep_route_keys_last() -> None:
    source = ensure_route_sequence_rules(
        pd.DataFrame(
            {
                "페이지 구분": ["공정별 확보율", "공정별 확보율"],
                "탭 구분": ["소요대수", "소요대수"],
                "정렬우선순위": [1, 2],
                "분류컬럼": ["Area_Name", "공정"],
                "정렬방식": ["오름차순", "오름차순"],
                "분류값": [pd.NA, pd.NA],
                "값표시순서": [pd.NA, pd.NA],
                "활성여부": ["Y", "Y"],
            }
        )
    )

    result = classification_columns_in_display_order(
        ["공정", "STEP_SEQ", "MCP_SEQ", "제품정보", "Area_Name"],
        source,
        "공정별 확보율",
        "소요대수",
    )

    assert result == ["Area_Name", "공정", "제품정보", "STEP_SEQ", "MCP_SEQ"]
