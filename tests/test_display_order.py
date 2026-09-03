# Purpose: RQ_DISPLAY_ORDER 기반 행 정렬 규칙 적용을 검증한다.

import pandas as pd

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
