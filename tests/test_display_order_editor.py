import pandas as pd
import pytest

from capa_simulation.services.display_order_csv import (
    display_order_from_csv,
    display_order_to_csv,
)
from capa_simulation.services.display_order_editor import (
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


def test_display_order_csv_rejects_changed_columns() -> None:
    invalid = _rules().rename(columns={"분류컬럼": "잘못된 컬럼"})

    with pytest.raises(ValueError, match="컬럼 계약"):
        display_order_from_csv(invalid.to_csv(index=False).encode("utf-8-sig"))
