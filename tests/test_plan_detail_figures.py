# Purpose: 계획 세부수량 두 칸의 세로 정렬이 GAP 유무에 따라 어떻게 갈리는지 고정한다.

"""계획 세부수량 칸의 세로 정렬 계약.

칸 글자는 표 칸이 아니라 숨긴 축 위 글자 trace 가 그린다 — `data[0]` 이 머리글, `data[1]` 이
값이고 y 는 그림 위에서 잰 px 다. 칸이 `<br>` 같은 마크업을 품으면 Plotly 가 칸마다 그린 뒤
재서 옮겨 칸 수만큼 느려진다.

증감이 오는 칸만 칸 위에 붙는 자리에 선다. 그 아래가 GAP 주석 자리이기 때문이다. 나머지는
행 한가운데다.
"""

import math
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest
from custom_key_tables import PART_A, PART_B, TWO_PART_PRODUCT
from home_two_part_app import home_script, publish_two_part_revision
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    lower_delta_row_height,
    table_row_height,
)
from capa_simulation.components.home_figure_common import (
    HOVER_LABEL_FONT_SIZE_PX,
    _table_label_width_units,
)
from capa_simulation.components.home_figures import build_plan_detail_figures
from capa_simulation.components.home_plan_detail_figures import (
    DETAIL_HEADER_FONT_SIZE_PX,
    DETAIL_HOVER_LINE_MAX_PX,
    DETAIL_LABEL_INSET_PX,
    DETAIL_VALUE_FONT_SIZE_PX,
    plan_detail_label_width_px,
)
from capa_simulation.components.plotly_layout import table_text_max_width_px, table_text_y
from capa_simulation.design import tokens
from capa_simulation.services.dashboard import (
    DETAIL_DIMENSION_WIDTHS,
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
)
from capa_simulation.services.product_parts import PART_NOT_SPLIT, product_part_label

MONTHS = ["202608", "202609"]
HEADER_HEIGHT = table_row_height(DETAIL_HEADER_FONT_SIZE_PX)
ROW_HEIGHT = lower_delta_row_height(DETAIL_VALUE_FONT_SIZE_PX)
CENTERED = round(table_text_y(0, DETAIL_VALUE_FONT_SIZE_PX, markup=True), 6)
RAISED = round(table_text_y(0, DETAIL_VALUE_FONT_SIZE_PX, markup=False), 6)


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["A", "A", "B"],
            "Stack": ["12H", "8H", "4H"],
            "202608": [1000.0, 500.0, 0.0],
            "202609": [2000.0, 0.0, 300.0],
        }
    )


def _comparison() -> pd.DataFrame:
    compared = _detail()
    compared["202608"] = [900.0, 500.0, 0.0]
    compared["202609"] = [2500.0, 0.0, 100.0]
    return compared


def _values(figure: Any) -> list[str]:
    return list(figure.data[1].text)


def _offsets(figure: Any) -> set[float]:
    """값 글자가 제 행 위 모서리에서 내려온 거리. 나머지 셈의 부동소수 찌꺼기는 반올림한다."""
    return {round((y - HEADER_HEIGHT) % ROW_HEIGHT, 6) for y in figure.data[1].y}


PAST_MONTHS = ["26.01", "26.07", "26.08", "26년"]


def _past_detail() -> pd.DataFrame:
    """과거 구간(26.01) 과 DB 계산 구간(26.07·26.08), 그리고 연간 Total."""
    return pd.DataFrame(
        {
            "제품정보": ["A"],
            "Stack": ["12H"],
            "26.01": [1000.0],
            "26.07": [200.0],
            "26.08": [300.0],
            "26년": [1500.0],
        }
    )


def _past_comparison() -> pd.DataFrame:
    """비교 프레임에는 과거도 연간 Total 도 없다 — 실제 파이프라인과 같은 모양이다."""
    return pd.DataFrame(
        {
            "제품정보": ["A"],
            "Stack": ["12H"],
            "26.07": [150.0],
            "26.08": [300.0],
        }
    )


def _gap_notes(figure: go.Figure) -> list[str]:
    annotations = figure.layout.annotations
    return [annotation.text for annotation in annotations if annotation.text]


def test_past_months_get_no_gap() -> None:
    """과거 구간은 공용 프로필에서 와 두 시나리오가 같은 값을 받는다.

    비교 프레임에는 과거가 병합되지 않으므로, 거르지 않으면 과거 입력 전액이 거짓 증감으로
    찍힌다. 여기서는 26.01 의 1,000K 가 그것이다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
        gap_month_labels={"26.07", "26.08"},
    )

    notes = _gap_notes(month_figure)

    assert "+1,000K" not in notes, f"과거 구간에 증감이 찍혔다: {notes}"
    assert "+50K" in notes, f"DB 구간 증감이 사라졌다: {notes}"


def test_year_total_gap_sums_only_the_db_range() -> None:
    """연간 Total 은 DB 계산 구간의 차이만 더한다.

    비교 프레임에 `26년` 컬럼이 없어 그대로 두면 그 해 합계 전액(1,500K)이 증감이 된다.
    실제 차이는 26.07 의 +50K 하나뿐이다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
        gap_month_labels={"26.07", "26.08"},
    )

    notes = _gap_notes(month_figure)

    assert "+1,500K" not in notes, f"연간 Total 에 그 해 전액이 찍혔다: {notes}"
    # 26.07 의 +50K 와 Total 의 +50K 둘 다 나온다.
    assert notes.count("+50K") == 2, notes


def test_without_a_month_whitelist_every_month_keeps_its_gap() -> None:
    """`gap_month_labels` 를 주지 않으면 예전과 같이 모든 달에 증감을 낸다.

    과거 구간을 쓰지 않는 호출자(테스트·다른 화면)가 이 인자를 몰라도 동작이 바뀌지 않아야
    한다.
    """
    _, month_figure = build_plan_detail_figures(
        production_detail=_past_detail(),
        month_labels=PAST_MONTHS,
        comparison_detail=_past_comparison(),
        year_total_labels=["26년"],
    )

    notes = _gap_notes(month_figure)

    assert "+1,000K" in notes, notes


def test_both_columns_center_without_a_comparison() -> None:
    """GAP 이 없으면 두 칸 모두 행 한가운데다. 한쪽만 가운데면 같은 행의 글자가 어긋나 보인다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(), month_labels=MONTHS
    )

    assert _values(label_figure), "분류 칸이 비어 있다"
    assert _values(month_figure), "월 칸이 비어 있다"
    assert _offsets(label_figure) == _offsets(month_figure) == {CENTERED}
    # 점은 표의 마크업 칸 자리(맑은 고딕 기준선보다 0.25em 위)라 행 가운데보다 1px 남짓 아래다.
    # 기준선 위로 서는 글리프의 가운데는 그보다 위라 눈으로는 가운데다.
    assert abs(CENTERED - ROW_HEIGHT / 2) <= 1.5
    assert not any(
        "<" in text for figure in (label_figure, month_figure) for text in _values(figure)
    )


def test_the_month_column_yields_the_lower_line_to_the_gap() -> None:
    """GAP 이 오면 월 칸만 위로 붙는다. 분류 칸은 증감이 없으므로 가운데에 그대로 선다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison(),
    )

    assert _offsets(label_figure) == {CENTERED}
    assert _offsets(month_figure) == {RAISED}
    assert RAISED < CENTERED
    gaps = [annotation.text for annotation in month_figure.layout.annotations if annotation.text]
    assert sorted(gaps) == ["+100K", "+200K", "-500K"]


def test_the_row_height_does_not_move_with_the_toggle() -> None:
    """토글 하나에 표 높이가 출렁이면 아래 구획이 통째로 밀린다. 움직이는 것은 글자뿐이다."""
    plain = build_plan_detail_figures(production_detail=_detail(), month_labels=MONTHS)
    compared = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison(),
    )

    for without, with_gap in zip(plain, compared, strict=True):
        assert without.layout.height == with_gap.layout.height
        assert without.layout.yaxis.range == with_gap.layout.yaxis.range
        assert list(without.data[0].y) == list(with_gap.data[0].y)
    # 두 칸의 행이 어긋나면 표 전체가 틀어진다.
    assert plain[0].layout.height == plain[1].layout.height
    assert list(plain[0].data[1].y) == list(compared[0].data[1].y)


@pytest.mark.parametrize("with_comparison", [False, True])
def test_an_empty_cell_gets_no_text(with_comparison: bool) -> None:
    """빈 칸(0·결측)에는 글자를 두지 않는다 — 없는 값 자리에 빈 글자만 생긴다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        comparison_detail=_comparison() if with_comparison else None,
    )

    assert _values(month_figure) == ["1,000K", "500K", "2,000K", "300K"]


def _customer_detail(customers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["A"] * len(customers),
            "Stack": ["12H"] * len(customers),
            "Customer": customers,
            "202608": [1000.0] * len(customers),
            "202609": [2000.0] * len(customers),
        }
    )


def _value_texts(figure: Any) -> list[str]:
    """분류 칸 값 글자 전부(자르지 않는 trace + 자르는 trace, 머리글 제외)."""
    headers = {"<b>제품</b>", "<b>Stack</b>", "<b>거래선</b>"}
    return [
        str(text)
        for trace in figure.data
        if trace.type == "scatter"
        for text in trace.text
        if text not in headers
    ]


DIMENSIONS = ["제품정보", "Stack", "Customer"]


def test_a_customer_name_of_the_sample_length_stays_whole_in_its_column() -> None:
    """거래선은 끝 글자로 갈린다(「-1」 · 「-2」) — 칸이 좁아 앞뒤가 잘리면 값을 읽지 못한다. 값
    길이는 합성 표본 기준이다."""
    label_figure, _ = build_plan_detail_figures(
        production_detail=_customer_detail(["DEMO_CUST-1", "DEMO_CUST-2"]),
        month_labels=MONTHS,
        detail_dimensions=DIMENSIONS,
    )

    assert {"DEMO_CUST-1", "DEMO_CUST-2"} <= set(_value_texts(label_figure))
    column_px = (
        DETAIL_DIMENSION_WIDTHS["Customer"]
        / sum(DETAIL_DIMENSION_WIDTHS.values())
        * DASHBOARD_LABEL_COLUMN_WIDTH_PX
    )
    assert column_px >= 94 + 2 * DETAIL_LABEL_INSET_PX


def test_a_name_that_does_not_fit_ends_in_an_ellipsis_and_shows_whole_on_hover() -> None:
    """칸보다 긴 이름은 끝을 줄이고 마우스를 올린 칸에 전체 이름이 뜬다. 풍선 막대는 칸 전체를 덮고
    자르는 축보다 뒤 번호 축에 얹혀 마우스를 받는다."""
    whole = "DEMO_CUSTOMER_WITH_A_VERY_LONG_NAME-1"
    label_figure, _ = build_plan_detail_figures(
        production_detail=_customer_detail([whole, "B"]),
        month_labels=MONTHS,
        detail_dimensions=DIMENSIONS,
    )

    (shown,) = [text for text in _value_texts(label_figure) if text.startswith("DEMO_")]
    assert shown.endswith("…") and shown != whole
    (bar,) = [trace for trace in label_figure.data if trace.type == "bar"]
    assert [str(name).replace("<br>", "") for name in bar.hovertext] == [whole]
    assert bar.hoverinfo == "text"
    assert list(bar.base) == [2.0]
    assert list(bar.x) == [DETAIL_DIMENSION_WIDTHS["Customer"]]
    axes = sorted(key for key in label_figure.layout if key.startswith("xaxis"))
    assert bar.xaxis == f"x{axes[-1].removeprefix('xaxis')}"
    assert label_figure.layout[axes[-1]].domain == (0, 1)


def _product_detail(product: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"제품정보": [product], "Stack": ["8H"], "202608": [1000.0], "202609": [2000.0]}
    )


def _hover_bar(figure: Any) -> Any:
    (bar,) = [trace for trace in figure.data if trace.type == "bar"]
    return bar


def test_the_hover_axis_alone_keeps_the_axis_background_transparent() -> None:
    """원래 이름은 넘치고 줄인 글은 드는 이름은 자르는 축 없이 풍선 축만 생긴다. 이 축의 영역도 앞
    축과 겹쳐, 바탕이 불투명하면 머리글과 모든 행의 이름을 덮는다."""
    label_figure, _ = build_plan_detail_figures(
        production_detail=_product_detail("가상 제품 고객 전용 샘플 1차 시험 판매 확대"),
        month_labels=MONTHS,
    )

    assert [trace.xaxis for trace in label_figure.data if trace.type == "scatter"][2:] == []
    assert _hover_bar(label_figure).xaxis == "x2"
    assert label_figure.layout.plot_bgcolor == tokens.TRANSPARENT


def _hover_lines(name: str) -> list[str]:
    label_figure, _ = build_plan_detail_figures(
        production_detail=_product_detail(name),
        month_labels=MONTHS,
    )
    return str(_hover_bar(label_figure).hovertext[0]).split("<br>")


def test_a_hover_name_wider_than_the_figure_breaks_into_lines() -> None:
    """풍선은 그림 밖에서 잘린다 — 말줄임된 이름을 읽는 길이 풍선뿐이라 줄을 나눠 전체가 그림 안에
    든다."""
    whole = "DEMO_PRODUCT_LONG_NAME_ALPHA_BETA_GAMMA_DELTA_EPSILON"

    lines = _hover_lines(whole)

    assert len(lines) > 1
    assert "".join(lines) == whole
    for line in lines:
        width = table_text_max_width_px(line, HOVER_LABEL_FONT_SIZE_PX)
        assert width <= DETAIL_HOVER_LINE_MAX_PX


def test_a_hover_name_breaks_at_its_spaces_and_stays_escaped() -> None:
    whole = "가상 제품 고객 전용 샘플 1차 시험 판매 확대 & 추가 물량 검토 대상 후보 묶음"

    lines = _hover_lines(whole)

    assert len(lines) > 1
    assert " ".join(lines) == whole.replace("&", "&amp;")


def test_names_that_cannot_overflow_get_no_hover_bar() -> None:
    label_figure, _ = build_plan_detail_figures(production_detail=_detail(), month_labels=MONTHS)

    assert [trace for trace in label_figure.data if trace.type == "bar"] == []


def test_the_two_column_split_does_not_move_when_the_customer_column_widens() -> None:
    """거래선 폭은 거래선이 있을 때만 쓴다 — 기본 두 칸의 경계는 그대로다."""
    assert DETAIL_DIMENSION_WIDTHS["제품정보"] / 2.0 == pytest.approx(0.7)
    assert DETAIL_DIMENSION_WIDTHS["Stack"] / 2.0 == pytest.approx(0.3)


# ---------------------------------------------------------------- 부품(CUSTOM) 갈라 보임


def _part_detail() -> pd.DataFrame:
    """DEMO_A 를 두 부품으로 가르고(부품 A 는 Stack 둘) DEMO_B 는 접힌 표."""
    return pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_A", "DEMO_A", "DEMO_B"],
            "CUSTOM": ["DEMO_CUSTOM_A", "DEMO_CUSTOM_A", "DEMO_CUSTOM_B", PART_NOT_SPLIT],
            "Stack": ["12H", "8H", "8H", "4H"],
            "202608": [1000.0, 500.0, 400.0, 300.0],
            "202609": [2000.0, 0.0, 100.0, 300.0],
        }
    )


def _named_by_label(detail: pd.DataFrame) -> pd.DataFrame:
    """부품 칸 대신 제품 칸 글이 이름표인 표."""
    named = detail.drop(columns=["CUSTOM"])
    named["제품정보"] = [
        product_part_label(str(product), str(part))
        for product, part in zip(detail["제품정보"], detail["CUSTOM"], strict=True)
    ]
    return named


def _group_rules(figure: go.Figure) -> int:
    """제품(이름표) 경계의 굵은 선 수."""
    return sum(
        1
        for shape in figure.layout.shapes
        if shape.type == "line"
        and shape.line.color == tokens.BORDER_STRONG
        and shape.line.width == tokens.GROUP_BORDER_WIDTH_PX
    )


def _shapes_at_the_product_boundary(figure: go.Figure) -> list[dict[str, Any]]:
    """분류 칸 도형 — 제품 칸 경계의 x 는 「경계」 로 바꿔 적는다(부품 이름표에 맞춰 제품 칸을 넓힌
    그림은 그 경계가 오른쪽이다)."""
    boundary = next(
        shape.x0
        for shape in figure.layout.shapes
        if shape.type == "line"
        and shape.x0 == shape.x1
        and shape.line.color == tokens.BORDER
        and shape.line.width == tokens.GRID_LINE_WIDTH_PX
    )
    shapes: list[dict[str, Any]] = []
    for shape in figure.layout.shapes:
        spec = shape.to_plotly_json()
        for edge in ("x0", "x1"):
            if spec.get(edge) == boundary:
                spec[edge] = "경계"
        shapes.append(spec)
    return shapes


def test_each_part_gets_its_own_band_and_rule_like_a_product_named_by_its_label() -> None:
    """부품은 칸으로 그리지 않는다 — 머리글은 제품 · Stack 그대로이고 줄무늬 띠 · 굵은 선은 이름표
    단위라, 제품 칸 글을 이름표로 바꾼 표와 칸 면색 · 선이 같다(제품 칸 경계 자리만 넓힌 만큼
    다르다). 한 부품 안의 Stack 경계는 얇은 선이다."""
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_part_detail(), month_labels=MONTHS
    )
    named_label, named_month = build_plan_detail_figures(
        production_detail=_named_by_label(_part_detail()),
        month_labels=MONTHS,
        detail_dimensions=["제품정보", "Stack"],
    )

    assert list(label_figure.data[0].text) == ["<b>제품</b>", "<b>Stack</b>"]
    assert _shapes_at_the_product_boundary(label_figure) == _shapes_at_the_product_boundary(
        named_label
    )
    assert month_figure.layout.shapes == named_month.layout.shapes
    assert _group_rules(month_figure) == 2
    assert month_figure.to_json() == named_month.to_json()


def test_the_product_cell_names_each_part_and_hovers_the_whole_label() -> None:
    """제품 칸은 부품마다 이름표 하나(한 부품의 둘째 Stack 행은 비움)이고, 넘칠 수 있는 칸은 전체
    이름표가 풍선에 뜬다."""
    label_figure, _ = build_plan_detail_figures(
        production_detail=_part_detail(), month_labels=MONTHS
    )

    texts = _value_texts(label_figure)
    assert "DEMO_B" in texts
    assert sum(text.endswith("(DEMO_CUSTOM_A)") for text in texts) == 1
    assert sum(text.endswith("(DEMO_CUSTOM_B)") for text in texts) == 1
    bars = [trace for trace in label_figure.data if trace.type == "bar"]
    hovered = {str(name).replace("<br>", " ") for bar in bars for name in bar.hovertext}
    for whole in ("DEMO_A (DEMO_CUSTOM_A)", "DEMO_A (DEMO_CUSTOM_B)"):
        assert whole in texts or whole in hovered


def test_a_narrow_product_cell_keeps_the_part_and_shortens_the_product_first() -> None:
    """거래선 칸이 붙어 제품 칸이 좁아지면 앞을 남기는 줄임은 두 부품을 같은 글로 만든다. 부품의
    구별되는 끝을 남기고 제품 쪽을 먼저 줄인다(UI-ACC-02)."""
    detail = pd.DataFrame(
        {
            "제품정보": [TWO_PART_PRODUCT, TWO_PART_PRODUCT],
            "CUSTOM": [PART_A, PART_B],
            "Stack": ["8H", "8H"],
            "Customer": ["DEMO_CUST-1", "DEMO_CUST-1"],
            "202608": [1000.0, 1000.0],
            "202609": [2000.0, 2000.0],
        }
    )

    label_figure, _ = build_plan_detail_figures(
        production_detail=detail,
        month_labels=MONTHS,
        detail_dimensions=PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    )

    product_texts = [
        text for text in _value_texts(label_figure) if text not in {"8H", "DEMO_CUST-1"}
    ]
    assert len(product_texts) == 2
    assert len(set(product_texts)) == 2
    assert product_texts[0].endswith("_A)") and product_texts[1].endswith("_B)")
    assert all("…" in text for text in product_texts)


# 이 환경의 Chrome 이 표 칸 글꼴 스택(`tokens.FONT_FAMILY`)을 그리는 Liberation Sans 와 fontconfig
# 기본 DejaVu Sans 보통 꼴의 글자 너비(글자 크기 배수 — 캔버스 `measureText`, 2026-11-24). 그림
# 글이 실제로 칸에 드는지를 줄임 모형과 따로 잰다(그림 확인에서 「DEM… (DEMO_CUSTOM_A)」 가 기본
# 폭 칸 경계에서 잘렸다 — 모형 173.6px, 실제 185.6px).
_RENDERED_EM: dict[str, tuple[float, float]] = {
    "A": (0.667, 0.684),
    "B": (0.667, 0.686),
    "C": (0.722, 0.698),
    "D": (0.722, 0.77),
    "E": (0.667, 0.632),
    "H": (0.722, 0.752),
    "I": (0.278, 0.295),
    "K": (0.667, 0.656),
    "M": (0.833, 0.863),
    "O": (0.778, 0.787),
    "P": (0.667, 0.603),
    "R": (0.722, 0.695),
    "S": (0.667, 0.635),
    "T": (0.611, 0.611),
    "U": (0.722, 0.732),
    "1": (0.556, 0.636),
    "2": (0.556, 0.636),
    " ": (0.278, 0.318),
    "(": (0.333, 0.39),
    ")": (0.333, 0.39),
    "-": (0.333, 0.361),
    "_": (0.556, 0.5),
    "…": (1.0, 1.0),
}


def _rendered_px(text: str, size: float) -> float:
    return max(sum(_RENDERED_EM[character][font] for character in text) for font in (0, 1)) * size


def _product_cell_px(label_figure: go.Figure, dimensions: list[str]) -> float:
    """그림의 제품 칸 폭(px) — 기본 칸 폭에 부품 이름표에 맞춰 넓힌 몫(분류 칸 그림 폭 − 기본 폭)을
    더한다. 넓힌 몫은 상한 안이다."""
    widths = [DETAIL_DIMENSION_WIDTHS[column] for column in dimensions if column != "CUSTOM"]
    extra = plan_detail_label_width_px(label_figure) - DASHBOARD_LABEL_COLUMN_WIDTH_PX
    assert 0 <= extra <= tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX
    return widths[0] / sum(widths) * DASHBOARD_LABEL_COLUMN_WIDTH_PX + extra


@pytest.mark.parametrize("product", [TWO_PART_PRODUCT, "DEMO-H12A"])
@pytest.mark.parametrize(
    "dimensions", [PRODUCTION_DETAIL_DIMENSIONS, PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS]
)
def test_a_part_label_fits_the_product_cell_at_its_rendered_width(
    product: str, dimensions: list[str]
) -> None:
    """상세 계획을 끈 기본 폭(약 182px)에서도 켠 좁은 폭에서도 부품 이름표는 실제로 그린 폭이 제품
    칸 안(양쪽 여백을 뺀 자리 — 부품 이름표에 맞춰 넓힌 칸)에 든다 — 칸 경계에서 첫 글자와 끝 괄호가
    잘리지 않는다. 두 부품은 서로 다른 글이고 부품 끝을 남긴다."""
    detail = pd.DataFrame(
        {
            "제품정보": [product, product],
            "CUSTOM": [PART_A, PART_B],
            "Stack": ["12H", "12H"],
            "Customer": ["DEMO_CUST-1", "DEMO_CUST-1"],
            "202608": [1000.0, 1000.0],
            "202609": [2000.0, 2000.0],
        }
    )

    label_figure, _ = build_plan_detail_figures(
        production_detail=detail, month_labels=MONTHS, detail_dimensions=list(dimensions)
    )

    product_px = _product_cell_px(label_figure, dimensions)
    texts = [text for text in _value_texts(label_figure) if text not in {"12H", "DEMO_CUST-1"}]
    assert len(texts) == 2 and len(set(texts)) == 2
    assert texts[0].endswith("_A)") and texts[1].endswith("_B)")
    for text in texts:
        assert (
            _rendered_px(text, DETAIL_VALUE_FONT_SIZE_PX) <= product_px - 2 * DETAIL_LABEL_INSET_PX
        ), text


@pytest.mark.parametrize(
    "dimensions", [PRODUCTION_DETAIL_DIMENSIONS, PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS]
)
def test_parts_that_share_their_end_stay_apart_in_the_product_cell(dimensions: list[str]) -> None:
    """끝 글자를 길게 같이 쓰는 두 부품도 제품 칸에서 서로 다른 글이다 — 끝에서부터 처음 갈리는
    글자를 남긴다. 실제로 그린 폭은 칸 안이다."""
    parts = ["DEMO_P1_CUSTOM_KIT_SET", "DEMO_P2_CUSTOM_KIT_SET"]
    detail = pd.DataFrame(
        {
            "제품정보": [TWO_PART_PRODUCT, TWO_PART_PRODUCT],
            "CUSTOM": parts,
            "Stack": ["12H", "12H"],
            "Customer": ["DEMO_CUST-1", "DEMO_CUST-1"],
            "202608": [1000.0, 1000.0],
            "202609": [2000.0, 2000.0],
        }
    )

    label_figure, _ = build_plan_detail_figures(
        production_detail=detail, month_labels=MONTHS, detail_dimensions=list(dimensions)
    )

    product_px = _product_cell_px(label_figure, dimensions)
    texts = [text for text in _value_texts(label_figure) if text not in {"12H", "DEMO_CUST-1"}]
    assert len(texts) == 2 and len(set(texts)) == 2
    assert "1" in texts[0] and "2" in texts[1]
    for text in texts:
        assert (
            _rendered_px(text, DETAIL_VALUE_FONT_SIZE_PX) <= product_px - 2 * DETAIL_LABEL_INSET_PX
        ), text


@pytest.mark.parametrize(
    "dimensions", [PRODUCTION_DETAIL_DIMENSIONS, PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS]
)
def test_parts_chained_by_their_end_stay_apart_in_the_product_cell(dimensions: list[str]) -> None:
    """끝이 이어진 부품 셋(짧은 것이 가운데 것의 끝, 가운데 것이 긴 것의 끝)도 제품 칸에서 서로 다른
    글이다 — 상세 계획을 켠 좁은 칸에서 짧은 두 부품이 같은 「(…_KIT_SET)」 이 되지 않는다. 실제로
    그린 폭은 칸 안이다."""
    parts = ["CUSTOM_KIT_SET", "A_CUSTOM_KIT_SET", "DEMO_A_CUSTOM_KIT_SET"]
    detail = pd.DataFrame(
        {
            "제품정보": [TWO_PART_PRODUCT] * 3,
            "CUSTOM": parts,
            "Stack": ["12H"] * 3,
            "Customer": ["DEMO_CUST-1"] * 3,
            "202608": [1000.0] * 3,
            "202609": [2000.0] * 3,
        }
    )

    label_figure, _ = build_plan_detail_figures(
        production_detail=detail, month_labels=MONTHS, detail_dimensions=list(dimensions)
    )

    product_px = _product_cell_px(label_figure, dimensions)
    texts = [text for text in _value_texts(label_figure) if text not in {"12H", "DEMO_CUST-1"}]
    assert len(texts) == 3 and len(set(texts)) == 3
    for text in texts:
        assert (
            _rendered_px(text, DETAIL_VALUE_FONT_SIZE_PX) <= product_px - 2 * DETAIL_LABEL_INSET_PX
        ), text


@pytest.mark.parametrize("with_comparison", [False, True])
def test_a_folded_frame_draws_the_same_figures_as_the_frame_without_the_part_column(
    with_comparison: bool,
) -> None:
    """부품이 하나뿐인 제품만 있으면(접힌 값) 부품 칸이 없는 표와 같은 그림이다 — 옛 리비전 ·
    제품마다 실값 하나인 새 등록은 칸 · 색 · 글자 · 선까지 지금과 같다."""
    folded = _detail().assign(CUSTOM=PART_NOT_SPLIT)[["제품정보", "CUSTOM", "Stack", *MONTHS]]
    compared = _comparison().assign(CUSTOM=PART_NOT_SPLIT)[["제품정보", "CUSTOM", "Stack", *MONTHS]]

    with_parts = build_plan_detail_figures(
        production_detail=folded,
        month_labels=MONTHS,
        detail_dimensions=PRODUCTION_DETAIL_DIMENSIONS,
        comparison_detail=compared if with_comparison else None,
    )
    without = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTHS,
        detail_dimensions=["제품정보", "Stack"],
        comparison_detail=_comparison() if with_comparison else None,
    )

    for left, right in zip(with_parts, without, strict=True):
        assert left.to_json() == right.to_json()


def _sample_part_detail(parts: list[str], *, customer: bool = False) -> pd.DataFrame:
    """검수용 견본의 DEMO-H12A 처럼 부품 둘로 가른 제품 하나와 접힌 제품 하나."""
    frame = pd.DataFrame(
        {
            "제품정보": ["DEMO-H12A", "DEMO-H12A", "DEMO-H8A"],
            "CUSTOM": [*parts, PART_NOT_SPLIT],
            "Stack": ["12H", "12H", "8H"],
            "202608": [1000.0, 500.0, 300.0],
            "202609": [2000.0, 600.0, 300.0],
        }
    )
    if customer:
        frame.insert(3, "Customer", ["DEMO_CUST-1"] * 3)
    return frame


def _column_px(label_figure: go.Figure, dimensions: list[str]) -> list[float]:
    """분류 칸마다 px 폭 — 제품 칸 경계 선과 그림 폭으로 낸다(넓힌 그림은 그림 폭이 크다)."""
    width = plan_detail_label_width_px(label_figure)
    widths = [DETAIL_DIMENSION_WIDTHS[column] for column in dimensions if column != "CUSTOM"]
    rest = sum(widths[1:])
    product_px = width - rest / sum(widths) * DASHBOARD_LABEL_COLUMN_WIDTH_PX
    return [product_px, *(w / sum(widths) * DASHBOARD_LABEL_COLUMN_WIDTH_PX for w in widths[1:])]


@pytest.mark.parametrize(
    "dimensions", [PRODUCTION_DETAIL_DIMENSIONS, PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS]
)
def test_the_product_cell_widens_until_the_longest_part_label_fits(dimensions: list[str]) -> None:
    """부품을 가른 제품이 있으면 제품 칸만 가장 긴 부품 이름표가 다 들 만큼 넓힌다(2026-11-24 그림
    보드 3 답 q7-narrow-label (다)) — 「DEMO-H12A (DEMO_CUSTOM_A)」 가 줄지 않고 다 선다. Stack ·
    거래선 칸은 px 폭이 그대로라 분류 칸 그림이 넓힌 만큼 넓어지고, 그 폭을 `layout.width` 에
    싣는다. 넓히는 몫은 상한(`tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX`) 안이고 상한을 넘으면 그
    상한이다."""
    customer = "Customer" in dimensions
    detail = _sample_part_detail([PART_A, PART_B], customer=customer)

    label_figure, month_figure = build_plan_detail_figures(
        production_detail=detail, month_labels=MONTHS, detail_dimensions=list(dimensions)
    )
    _, unsplit_month = build_plan_detail_figures(
        production_detail=detail.assign(CUSTOM=PART_NOT_SPLIT),
        month_labels=MONTHS,
        detail_dimensions=list(dimensions),
    )

    width = plan_detail_label_width_px(label_figure)
    labels = [f"DEMO-H12A ({PART_A})", f"DEMO-H12A ({PART_B})"]
    base_product_px = (
        DETAIL_DIMENSION_WIDTHS["제품정보"]
        / sum(DETAIL_DIMENSION_WIDTHS[column] for column in dimensions if column != "CUSTOM")
        * DASHBOARD_LABEL_COLUMN_WIDTH_PX
    )
    needed = max(_table_label_width_units(label) for label in labels) * DETAIL_VALUE_FONT_SIZE_PX
    needed += 2 * DETAIL_LABEL_INSET_PX
    extra = min(math.ceil(needed - base_product_px), tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX)
    assert width == DASHBOARD_LABEL_COLUMN_WIDTH_PX + extra
    assert label_figure.layout.width == width
    columns = _column_px(label_figure, list(dimensions))
    assert columns[0] == pytest.approx(base_product_px + extra)
    texts = _value_texts(label_figure)
    if extra < tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX:
        assert set(labels) <= set(texts)
    else:
        # 상한을 넘는 이름표는 부품을 남기고 제품 쪽부터 줄인다(지금 꼴).
        fitted = [text for text in texts if text.endswith(f"({PART_A})")]
        assert len(fitted) == 1 and "…" in fitted[0]
    # 달 칸은 넓히지 않는다 — 부품 칸을 접은 표와 같은 폭 · 같은 칸이다.
    assert month_figure.layout.width == unsplit_month.layout.width


def test_the_sample_part_label_stands_whole_in_the_default_view() -> None:
    """검수용 견본의 DEMO-H12A 부품 이름표는 상세 계획을 끈 기본 보기에서 상한 안에서 다 든다 — 보드
    (다) 의 그림(「DEMO-H12A (DEMO_CUSTOM_A)」)이 그대로 선다."""
    label_figure, _ = build_plan_detail_figures(
        production_detail=_sample_part_detail([PART_A, PART_B]), month_labels=MONTHS
    )

    texts = _value_texts(label_figure)
    assert f"DEMO-H12A ({PART_A})" in texts and f"DEMO-H12A ({PART_B})" in texts
    assert (
        plan_detail_label_width_px(label_figure)
        < DASHBOARD_LABEL_COLUMN_WIDTH_PX + tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX
    )


def test_a_part_label_longer_than_the_cap_is_shortened_like_before() -> None:
    """상한을 넘는 부품 이름표는 제품 칸을 상한까지만 넓히고, 부품을 남기고 제품 쪽부터 줄인다 — 두
    부품은 서로 다른 글이고 그린 폭은 넓힌 칸 안이다."""
    parts = ["DEMO_CUSTOM_PART_ROUTE_SETUP_KIT_A", "DEMO_CUSTOM_PART_ROUTE_SETUP_KIT_B"]

    label_figure, _ = build_plan_detail_figures(
        production_detail=_sample_part_detail(parts), month_labels=MONTHS
    )

    assert (
        plan_detail_label_width_px(label_figure)
        == DASHBOARD_LABEL_COLUMN_WIDTH_PX + tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX
    )
    product_px = _product_cell_px(label_figure, PRODUCTION_DETAIL_DIMENSIONS)
    part_texts = [
        text for text in _value_texts(label_figure) if text not in {"12H", "8H", "DEMO-H8A"}
    ]
    assert len(part_texts) == 2 and len(set(part_texts)) == 2
    assert part_texts[0].endswith("_A)") and part_texts[1].endswith("_B)")
    for text in part_texts:
        assert "…" in text
        assert _rendered_px(text, DETAIL_VALUE_FONT_SIZE_PX) <= product_px - 2 * (
            DETAIL_LABEL_INSET_PX
        )


@pytest.mark.parametrize("with_comparison", [False, True])
@pytest.mark.parametrize(
    "dimensions", [PRODUCTION_DETAIL_DIMENSIONS, PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS]
)
def test_without_a_split_part_the_label_figure_keeps_its_width(
    with_comparison: bool, dimensions: list[str]
) -> None:
    """부품을 가른 제품이 없으면(접힌 값뿐) 제품 칸 · 분류 칸 그림 폭이 넓히기 전과 같다 — 그림이
    `layout.width` 를 싣지 않고 HOME 분류 칸은 `DASHBOARD_LABEL_COLUMN_WIDTH_PX` 다. 상세 계획 ·
    GAP 에서도 같다."""
    detail = _sample_part_detail([PART_A, PART_B], customer="Customer" in dimensions).assign(
        CUSTOM=PART_NOT_SPLIT
    )

    label_figure, _ = build_plan_detail_figures(
        production_detail=detail,
        month_labels=MONTHS,
        detail_dimensions=list(dimensions),
        comparison_detail=detail if with_comparison else None,
    )

    assert label_figure.layout.width is None
    assert plan_detail_label_width_px(label_figure) == DASHBOARD_LABEL_COLUMN_WIDTH_PX


def test_the_widened_width_rides_with_the_figure_through_the_shared_store() -> None:
    """넓힌 폭은 그림 레이아웃에 실려 공용 칸 왕복(`to_dict` → 검증 없이 다시 세움)에도 남는다 —
    캐시에서 꺼낸 그림으로 그리는 회차도 HOME 분류 칸이 같은 폭이다."""
    label_figure, _ = build_plan_detail_figures(
        production_detail=_sample_part_detail([PART_A, PART_B]), month_labels=MONTHS
    )

    restored = go.Figure(label_figure.to_dict(), _validate=False)

    assert plan_detail_label_width_px(restored) == plan_detail_label_width_px(label_figure)
    assert plan_detail_label_width_px(restored) > DASHBOARD_LABEL_COLUMN_WIDTH_PX


def test_a_gap_view_widens_the_product_cell_by_the_same_rule() -> None:
    """GAP(비교 시나리오) 을 켜도 같은 규칙이다 — 비교에만 있는 옛 리비전의 「제품 (-)」 줄이 끼어도
    넓히는 몫은 가른 부품 이름표가 정한다."""
    detail = _sample_part_detail([PART_A, PART_B])
    compared = pd.concat(
        [
            detail,
            pd.DataFrame(
                {
                    "제품정보": ["DEMO-H12A"],
                    "CUSTOM": ["-"],
                    "Stack": ["12H"],
                    "202608": [900.0],
                    "202609": [900.0],
                }
            ),
        ],
        ignore_index=True,
    )

    plain, _ = build_plan_detail_figures(production_detail=detail, month_labels=MONTHS)
    gap, _ = build_plan_detail_figures(
        production_detail=compared, month_labels=MONTHS, comparison_detail=compared
    )

    assert plan_detail_label_width_px(gap) == plan_detail_label_width_px(plain)
    assert "DEMO-H12A (-)" in _value_texts(gap)


def test_home_draws_one_plan_detail_band_per_part(tmp_path: Path) -> None:
    """두 부품 공식버전을 연 HOME 의 계획 세부수량은 그 제품을 부품마다 한 줄로 그린다(전체 이름표는
    좁은 제품 칸 대신 풍선이 나른다)."""
    database_path = tmp_path / "scenario.duckdb"
    publish_two_part_revision(database_path)

    app = AppTest.from_string(home_script(database_path), default_timeout=300).run()

    assert not list(app.exception)
    label_figure = app.session_state["spy_figures"]["production_detail_labels"]
    texts = _value_texts(label_figure)
    assert sum(text.endswith(f"({PART_A})") for text in texts) == 1
    assert sum(text.endswith(f"({PART_B})") for text in texts) == 1
    hovered = {
        str(name).replace("<br>", " ")
        for trace in label_figure.data
        if trace.type == "bar"
        for name in trace.hovertext
    }
    assert {
        product_part_label(TWO_PART_PRODUCT, PART_A),
        product_part_label(TWO_PART_PRODUCT, PART_B),
    } <= hovered


def _label_column_px(app: AppTest) -> set[int]:
    """HOME 대시보드 구분 컬럼을 못박는 CSS 의 px 폭(`split_scroll_columns_style`)."""
    widths: set[int] = set()
    for element in app.get("html"):
        body = str(element.proto.body)
        if ".st-key-production_lob_label_canvas)" not in body:
            continue
        head = body.index(".st-key-production_lob_label_canvas)")
        rule = body[head : body.index("}", head)]
        widths.add(int(rule.split("flex: 0 0 ", 1)[1].split("px", 1)[0]))
    return widths


def test_home_widens_the_shared_label_column_to_the_plan_detail_figure(tmp_path: Path) -> None:
    """두 부품 공식버전을 연 HOME 은 계획 세부수량 분류 칸 그림이 실은 폭으로 구분 컬럼을 못박는다 —
    네 구획이 한 컬럼이라 행이 맞고, 넓힌 몫은 상한 안이다."""
    database_path = tmp_path / "scenario.duckdb"
    publish_two_part_revision(database_path)

    app = AppTest.from_string(home_script(database_path), default_timeout=300).run()

    assert not list(app.exception)
    label_figure = app.session_state["spy_figures"]["production_detail_labels"]
    width = plan_detail_label_width_px(label_figure)
    assert DASHBOARD_LABEL_COLUMN_WIDTH_PX < width
    assert width <= DASHBOARD_LABEL_COLUMN_WIDTH_PX + tokens.PLAN_DETAIL_PRODUCT_WIDEN_MAX_PX
    assert _label_column_px(app) == {width}
