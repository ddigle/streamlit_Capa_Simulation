# Purpose: 분류(라벨) 컬럼 폭이 창 크기와 무관하게 px 로 고정되는지 지킨다.

"""분류 컬럼이 창 폭에 따라 줄어 이름이 잘리던 문제를 고정한다.

`st.columns` 의 인자는 비율이다. 그런데 분류 폭은 px 로 계산한 값을 그대로 넘기고 있어서,
컨테이너가 설계 폭보다 좁으면 분류 컬럼도 같이 줄었다. 1280px 창의 HOME 에서 구분 컬럼이
260px 대신 149px 로 잡혀 "Capa LOB 현황" 이 잘렸고, 반대로 조회 월이 두세 달뿐이면 비율이
커져 분류 컬럼이 필요 이상 넓어졌다.
"""

import re
from pathlib import Path

from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.scroll_shell import split_scroll_columns_style

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rules(css: str) -> list[str]:
    return [line.strip() for line in re.sub(r"<[^>]+>", "", css).split("\n") if line.strip()]


def test_label_column_is_pinned_and_month_column_takes_the_rest() -> None:
    assert _rules(
        split_scroll_columns_style(
            label_key="demo_label_canvas",
            month_key="demo_month_region",
            label_width_px=318,
        )
    ) == _rules(
        """
        [data-testid="stColumn"]:has(.st-key-demo_label_canvas) {
            flex: 0 0 318px !important;
            width: 318px !important;
            min-width: 318px !important;
        }
        [data-testid="stColumn"]:has(.st-key-demo_month_region) {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        """
    )


def test_month_column_may_shrink_below_its_content() -> None:
    """월 영역은 가로로 스크롤하므로 0 까지 줄어도 내용이 잘리지 않는다.

    `min-width: 0` 이 빠지면 flex 항목의 기본 `min-width: auto` 때문에 월 Figure 의 폭이
    컬럼의 최소 폭이 되고, 분류 컬럼이 다시 밀려 잘린다.
    """
    css = split_scroll_columns_style(
        label_key="demo_label_canvas",
        month_key="demo_month_region",
        label_width_px=200,
    )

    assert "min-width: 0 !important;" in css


def test_home_dashboard_label_width_fits_its_longest_label() -> None:
    """구분 컬럼에는 구획 제목과 가장 긴 행 이름이 함께 들어간다.

    실측(1920px 창, Malgun Gothic 20px): "▍Capa LOB 현황" 159px, "Density (억Gb)" 140px.
    셀 좌우 여백까지 감안해 260px 로 잡았다. 이 값을 줄이면 제목이 다시 잘린다.
    """
    assert DASHBOARD_LABEL_COLUMN_WIDTH_PX >= 200


def test_split_layouts_pin_their_label_column() -> None:
    """분류 + 월 2단 배치를 쓰는 곳은 반드시 폭을 못박아야 한다."""
    owners = {
        "src/capa_simulation/components/monthly_table_base.py",
        "src/capa_simulation/components/home_rendering.py",
    }

    for relative in sorted(owners):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "split_scroll_columns_style(" in source, f"{relative} 가 폭을 고정하지 않습니다."
