# Purpose: RQ_DISPLAY_ORDER 기반 행 정렬 규칙 적용을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.display_order import apply_display_order


def test_workbook_display_order_supports_custom_and_ascending_rules() -> None:
    data = pd.DataFrame(
        {
            "양산구분": ["ER", "양산", "양산", "양산"],
            "제품정보": ["제품B", "제품B", "제품A", "제품A"],
            "Capa Code": ["Z", "B", "C", "A"],
        }
    )
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 5,
            "탭 구분": ["PKG PLAN"] * 5,
            "정렬우선순위": [1, 1, 2, 2, 3],
            "분류컬럼": ["양산구분", "양산구분", "제품정보", "제품정보", "Capa Code"],
            "정렬방식": ["사용자지정", "사용자지정", "사용자지정", "사용자지정", "오름차순"],
            "분류값": ["양산", "ER", "제품A", "제품B", None],
            "값표시순서": [1, 2, 1, 2, None],
            "활성여부": ["Y", "Y", "Y", "Y", "Y"],
        }
    )

    result = apply_display_order(data, display_order, "부하량", "PKG PLAN")

    assert result[["양산구분", "제품정보", "Capa Code"]].to_dict("records") == [
        {"양산구분": "양산", "제품정보": "제품A", "Capa Code": "A"},
        {"양산구분": "양산", "제품정보": "제품A", "Capa Code": "C"},
        {"양산구분": "양산", "제품정보": "제품B", "Capa Code": "B"},
        {"양산구분": "ER", "제품정보": "제품B", "Capa Code": "Z"},
    ]


# 사용자가 실제로 겪은 것: `WF 구분` 정렬을 만들며 분류값에 `Top` 이라고 적었는데 원천은
# `TOP` 이라 규칙이 걸리지 않았다. 오류도 경고도 없이 그 값만 화면 맨 뒤로 밀린다.


def test_a_rule_matches_its_value_whatever_the_case() -> None:
    data = pd.DataFrame({"WF 구분": ["Master", "TOP", "core", "dummy"]})
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 4,
            "탭 구분": ["환산"] * 4,
            "정렬우선순위": [1] * 4,
            "분류컬럼": ["WF 구분"] * 4,
            "정렬방식": ["사용자지정"] * 4,
            # 규칙은 사람이 읽기 좋은 표기로 적는다. 원천 표기와 달라도 같은 값이다.
            "분류값": ["Dummy", "Top", "Core", "Master"],
            "값표시순서": [1, 2, 3, 4],
            "활성여부": ["Y"] * 4,
        }
    )

    result = apply_display_order(data, display_order, "부하량", "환산")

    assert result["WF 구분"].tolist() == ["dummy", "TOP", "core", "Master"]


def test_surrounding_spaces_do_not_break_a_rule() -> None:
    """규칙 쪽은 저장할 때 공백을 떼는데 원천 쪽은 떼지 않았다. 한쪽만 떼면 짝이 안 맞는다."""
    data = pd.DataFrame({"WF 구분": [" Core ", "Top"]})
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 2,
            "탭 구분": ["환산"] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["Core", "Top"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )

    result = apply_display_order(data, display_order, "부하량", "환산")

    assert result["WF 구분"].tolist() == [" Core ", "Top"]


def test_rules_that_differ_only_in_case_are_rejected() -> None:
    """`Top` 과 `TOP` 을 따로 두면 둘 다 같은 값에 걸려 행 순서가 승자를 정한다."""
    data = pd.DataFrame({"WF 구분": ["Top"]})
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 2,
            "탭 구분": ["환산"] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["Top", "TOP"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )

    with pytest.raises(ValueError, match="사용자지정 값이 중복"):
        apply_display_order(data, display_order, "부하량", "환산")


def test_the_edp_top_rule_is_derived_from_a_differently_cased_top() -> None:
    """`Top_e` 는 앱이 `Top` 규칙에서 파생한다. 규칙을 `TOP` 으로 적어도 파생돼야 한다.

    파생되지 않으면 `Top_e` 가 규칙 없는 값이 되어 무한대로 밀리고, 화면 맨 뒤에 선다.
    """
    data = pd.DataFrame({"WF 구분": ["Core", "Top_e", "Top"]})
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 2,
            "탭 구분": ["환산"] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["TOP", "Core"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )

    result = apply_display_order(data, display_order, "부하량", "환산")

    assert result["WF 구분"].tolist() == ["Top", "Top_e", "Core"]
