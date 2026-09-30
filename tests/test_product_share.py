# Purpose: HOME 제품별 비중 행의 수량 합산·색 칸 배정·칸별 비중과 도넛 Figure 모양을 고정한다.

import pandas as pd
import pytest

from capa_simulation.components.home_dimensions import (
    LOB_PLOT_AREA_HEIGHT_PX,
    LOB_PRODUCT_SHARE_INSET_PX,
    LOB_PRODUCT_SHARE_ROW_HEIGHT_PX,
    LOB_PRODUCT_SHARE_TOP_Y,
    top5_process_label_budget,
)
from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.design import tokens
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_PKG_PLAN
from capa_simulation.services.product_share import (
    OTHER_PRODUCT_LABEL,
    PRODUCT_SHARE_SLOT_COUNT,
    assign_product_slots,
    build_product_share_cells,
    build_product_volume,
    combine_product_volume,
    past_product_volume,
)


def _plan(rows: list[tuple[int, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "제품정보", "양산구분", "생산수량"])


def _wafer(rows: list[tuple[int, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "제품정보", "양산구분", "물량"])


def _volume() -> pd.DataFrame:
    """두 달, 세 제품. DEMO_A 는 양산·ER 이 함께 있다."""
    plan = _plan(
        [
            (202609, "DEMO_A", "양산", 300.0),
            (202609, "DEMO_A", "ER", 100.0),
            (202609, "DEMO_B", "양산", 400.0),
            (202609, "DEMO_C", "양산", 200.0),
            (202610, "DEMO_A", "양산", 500.0),
            (202610, "DEMO_B", "양산", 500.0),
        ]
    )
    wafer = _wafer(
        [
            (202609, "DEMO_A", "양산", 3_000.0),
            (202609, "DEMO_A", "ER", 1_000.0),
            (202609, " DEMO_B ", "양산", 5_000.0),
            (202609, "DEMO_C", "양산", 2_000.0),
            (202610, "DEMO_A", "양산", 4_000.0),
            (202610, "DEMO_B", "양산", 4_000.0),
        ]
    )
    return build_product_volume(plan, wafer)


# ---------------------------------------------------------------- 수량·비중


def test_production_classes_are_summed_per_product() -> None:
    volume = _volume().set_index(["생산계획년월", "제품정보"])

    # 양산 300 + ER 100. 양산구분을 나누지 않는다(사용자 지정).
    assert volume.loc[(202609, "DEMO_A"), "생산수량"] == 400.0
    assert volume.loc[(202609, "DEMO_A"), "Wafer 부하량"] == 4_000.0
    # 앞뒤 공백은 같은 제품이다.
    assert volume.loc[(202609, "DEMO_B"), "Wafer 부하량"] == 5_000.0


@pytest.mark.parametrize(("basis", "total"), [("Wafer", 11_000.0), ("PKG", 1_000.0)])
def test_each_month_sums_to_one_and_its_total_is_the_plan(basis: str, total: float) -> None:
    volume = _volume()
    slots = assign_product_slots(volume)
    cells = build_product_share_cells(volume, basis, slots, month_labels=["26.09", "26.10"])

    september = cells["26.09"]
    # Wafer 분모는 `Wafer 계획` 행(그 달 전체 Wafer 부하량)과 같은 값이다.
    assert september.total == total
    for cell in cells.values():
        assert sum(piece.share for piece in cell.slices) == pytest.approx(1.0)
    shares = {piece.product: piece.share for piece in september.slices}
    expected_a = 4_000.0 / 11_000.0 if basis == "Wafer" else 400.0 / 1_000.0
    assert shares["DEMO_A"] == pytest.approx(expected_a)


def test_a_product_keeps_its_slot_and_order_in_every_month() -> None:
    volume = _volume()
    slots = assign_product_slots(volume)
    cells = build_product_share_cells(volume, "Wafer", slots, month_labels=["26.09", "26.10"])

    for cell in cells.values():
        order = [piece.product for piece in cell.slices]
        assert order == [product for product in slots.order if product in order]
        for piece in cell.slices:
            assert piece.slot == slots.slot[piece.product]


def test_removing_a_product_does_not_repaint_the_survivors() -> None:
    """EDP 를 끄면 제품이 빠진다. 칸은 EDP 포함 목록에서 정하므로 남은 제품의 색이 그대로다."""
    volume = _volume()
    slots = assign_product_slots(volume)
    without_a = volume.loc[volume["제품정보"].ne("DEMO_A")]

    cells = build_product_share_cells(without_a, "PKG", slots, month_labels=["26.09"])

    assert {piece.product: piece.slot for piece in cells["26.09"].slices} == {
        "DEMO_B": slots.slot["DEMO_B"],
        "DEMO_C": slots.slot["DEMO_C"],
    }
    assert slots.slot["DEMO_B"] != 0, "DEMO_A 가 빠져도 DEMO_B 가 첫 칸으로 당겨지지 않는다"


def test_slots_follow_the_display_order() -> None:
    display_order = pd.DataFrame(
        {
            "페이지 구분": [PAGE_PLAN] * 3,
            "탭 구분": [TAB_PKG_PLAN] * 3,
            "정렬우선순위": [1, 1, 1],
            "분류컬럼": ["제품정보"] * 3,
            "정렬방식": ["사용자지정"] * 3,
            "분류값": ["DEMO_C", "DEMO_A", "DEMO_B"],
            "값표시순서": [1, 2, 3],
            "활성여부": ["Y"] * 3,
        }
    )

    slots = assign_product_slots(_volume(), display_order)

    assert slots.order == ("DEMO_C", "DEMO_A", "DEMO_B")


def test_products_beyond_the_slot_count_fold_into_other_by_volume() -> None:
    products = [f"DEMO_{index}" for index in range(PRODUCT_SHARE_SLOT_COUNT + 2)]
    plan = _plan(
        [(202609, name, "양산", float(10 * (index + 1))) for index, name in enumerate(products)]
    )
    wafer = _wafer(
        [(202609, name, "양산", float(100 * (index + 1))) for index, name in enumerate(products)]
    )
    volume = build_product_volume(plan, wafer)

    slots = assign_product_slots(volume)
    cells = build_product_share_cells(volume, "Wafer", slots, month_labels=["26.09"])

    # 물량이 작은 앞의 세 제품이 접히고 다섯이 이름을 갖는다(다섯 + 기타 = 여섯 조각).
    assert slots.folded == frozenset(products[:3])
    assert len(slots.order) == PRODUCT_SHARE_SLOT_COUNT - 1
    pieces = cells["26.09"].slices
    assert len(pieces) == PRODUCT_SHARE_SLOT_COUNT
    other = pieces[-1]
    assert other.product == OTHER_PRODUCT_LABEL and other.slot is None
    assert {name for name, _ in other.members} == set(products[:3])
    assert sum(piece.share for piece in pieces) == pytest.approx(1.0)


def test_past_months_draw_pkg_but_leave_wafer_blank() -> None:
    """과거 입력은 제품별 Wafer 가 없다. Wafer 칸은 비우고 PKG 칸만 그린다."""
    past = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609],
            "제품정보": ["DEMO_A", "DEMO_B", "DEMO_A"],
            "Stack": ["12H", "12H", "12H"],
            "Customer": ["DEMO-CUST", "DEMO-CUST", "DEMO-CUST"],
            "생산수량": [30.0, 10.0, 999.0],
        }
    )
    past_volume = past_product_volume(
        past, start_month=202608, end_month=202610, exclude_months={202609, 202610}
    )
    volume = combine_product_volume(_volume(), past_volume)
    slots = assign_product_slots(volume)
    labels = ["26.08", "26.09", "26.10"]

    wafer_cells = build_product_share_cells(volume, "Wafer", slots, month_labels=labels)
    pkg_cells = build_product_share_cells(volume, "PKG", slots, month_labels=labels)

    assert "26.08" not in wafer_cells
    assert {piece.product: piece.share for piece in pkg_cells["26.08"].slices} == {
        "DEMO_A": pytest.approx(0.75),
        "DEMO_B": pytest.approx(0.25),
    }
    # 계산 결과가 있는 달의 과거 값(999)은 쓰지 않는다.
    assert pkg_cells["26.09"].total == 1_000.0


def test_a_year_total_is_drawn_only_when_every_month_of_that_year_is() -> None:
    months = list(range(202601, 202613))
    labels = [f"26.{month % 100:02d}" for month in months]
    plan = _plan([(month, "DEMO_A", "양산", 10.0) for month in months])
    wafer = _wafer([(month, "DEMO_A", "양산", 100.0) for month in months])
    volume = build_product_volume(plan, wafer)
    slots = assign_product_slots(volume)

    full = build_product_share_cells(
        volume, "Wafer", slots, month_labels=[*labels, "26년"], year_total_labels=["26년"]
    )
    assert full["26년"].total == 1_200.0

    # 한 달의 Wafer 를 모르면(과거 구간) 그해 합계는 위 `Wafer 계획` Total 과 분모가 다르다.
    volume.loc[volume["생산계획년월"].eq(202601), "Wafer 부하량"] = float("nan")
    partial = build_product_share_cells(
        volume, "Wafer", slots, month_labels=[*labels, "26년"], year_total_labels=["26년"]
    )
    assert "26년" not in partial
    assert "26.02" in partial


def test_an_unknown_basis_is_refused() -> None:
    volume = _volume()
    with pytest.raises(ValueError, match="단위"):
        build_product_share_cells(volume, "Chip", assign_product_slots(volume), month_labels=[])


# ---------------------------------------------------------------- Figure


def _figures(cells: dict | None, labels: list[str], basis: str = "Wafer"):
    density = pd.DataFrame(
        {
            "생산계획년월": [int(f"20{label[:2]}{label[3:]}") for label in labels],
            "년월": labels,
            "부하량": [1.5] * len(labels),
        }
    )
    summary = density.assign(**{"Wafer 부하량": 12_000.0, "Wafer Capa": 11_000.0})
    empty_top5 = pd.DataFrame(
        columns=["생산계획년월", "년월", "순위", "공정", "확보율", "Wafer Capa", "B/N Capa"]
    )
    bottleneck = density.assign(공정="DEMO_P", 확보율=0.9, **{"B/N Capa": 1.2})
    return build_lob_summary_figures(
        monthly_density=density,
        monthly_top5=empty_top5,
        bottleneck_capacity=bottleneck,
        lob_summary=summary,
        month_labels=labels,
        secure_threshold=1.095,
        warning_threshold=0.995,
        product_share_cells=cells,
        product_share_basis=basis,
    )


def _pies(figure) -> list:
    return [trace for trace in figure.data if trace.type == "pie"]


def test_every_donut_gets_the_same_square_so_the_radius_is_constant() -> None:
    volume = _volume()
    labels = ["26.09", "26.10"]
    cells = build_product_share_cells(
        volume, "Wafer", assign_product_slots(volume), month_labels=labels
    )
    _, month_figure = _figures(cells, labels)
    pies = _pies(month_figure)
    width_px = len(labels) * tokens.MONTH_COLUMN_WIDTH_PX

    assert len(pies) == 2
    sizes = set()
    for pie in pies:
        x0, x1 = pie.domain.x
        y0, y1 = pie.domain.y
        size = (round((x1 - x0) * width_px, 6), round((y1 - y0) * LOB_PLOT_AREA_HEIGHT_PX, 6))
        sizes.add(size)
        assert y1 <= LOB_PRODUCT_SHARE_TOP_Y and y0 >= 0
        # 조각은 칸 배정 차례 그대로다 — Plotly 기본값은 값 순으로 다시 세운다.
        assert pie.sort is False and pie.direction == "clockwise"
        assert pie.textinfo == "none"
    expected = tokens.MONTH_COLUMN_WIDTH_PX - 2 * LOB_PRODUCT_SHARE_INSET_PX
    assert sizes == {(expected, expected)}
    # 칸은 정사각형이다 — 행 높이가 월 칸 폭과 같다.
    assert LOB_PRODUCT_SHARE_ROW_HEIGHT_PX == tokens.MONTH_COLUMN_WIDTH_PX


def test_the_same_product_has_the_same_color_in_every_donut() -> None:
    volume = _volume()
    labels = ["26.09", "26.10"]
    cells = build_product_share_cells(
        volume, "PKG", assign_product_slots(volume), month_labels=labels
    )
    _, month_figure = _figures(cells, labels, basis="PKG")

    color_of: dict[str, set[str]] = {}
    for pie in _pies(month_figure):
        for label, color in zip(pie.labels, pie.marker.colors, strict=True):
            color_of.setdefault(label, set()).add(color)
    assert all(len(colors) == 1 for colors in color_of.values()), color_of
    assert len({next(iter(colors)) for colors in color_of.values()}) == len(color_of)


def test_the_label_cell_names_the_row_its_unit_and_the_products() -> None:
    volume = _volume()
    labels = ["26.09"]
    cells = build_product_share_cells(
        volume, "PKG", assign_product_slots(volume), month_labels=labels
    )
    label_figure, _ = _figures(cells, labels, basis="PKG")
    texts = [str(annotation.text) for annotation in label_figure.layout.annotations]

    title = next(text for text in texts if "제품별 비중" in text)
    assert "PKG" in title
    for product in ("DEMO_A", "DEMO_B", "DEMO_C"):
        assert any(text.endswith(f"■</span> {product}") for text in texts), product


def test_the_bn_top5_label_sits_in_the_middle_of_its_visible_cell() -> None:
    """칸은 막대 밴드에 공정명이 드리우는 띠까지 더한 면이다. 밴드 가운데가 아니다."""
    label_figure, month_figure = _figures(None, ["26.09"])
    label = next(
        annotation
        for annotation in label_figure.layout.annotations
        if annotation.text == "<b>B/N Top 5</b>"
    )
    band = month_figure.layout.yaxis2.domain
    cell_top = band[1]
    cell_bottom = LOB_PRODUCT_SHARE_TOP_Y

    assert label.y == pytest.approx((cell_top + cell_bottom) / 2)
    assert label.y < (band[0] + band[1]) / 2
    assert label.yanchor == "middle"
    # 같은 경계에 분류 면이 깔려 있다 — 글자 칸과 면이 같은 칸을 가리킨다.
    rects = [
        (shape.y0, shape.y1)
        for shape in label_figure.layout.shapes
        if shape.type == "rect" and shape.fillcolor == tokens.SURFACE_CLASSIFICATION
    ]
    assert any(
        y0 == pytest.approx(cell_bottom) and y1 == pytest.approx(cell_top) for y0, y1 in rects
    )


def test_the_row_stays_even_without_data() -> None:
    """도넛이 하나도 없어도 행과 구분 칸은 그대로다 — 행 높이가 데이터에 따라 출렁이지 않는다."""
    label_figure, month_figure = _figures(None, ["26.09"])

    assert _pies(month_figure) == []
    assert any("제품별 비중" in str(item.text) for item in label_figure.layout.annotations)


def test_long_top5_process_names_end_inside_their_band_above_the_donuts() -> None:
    """Plotly 는 주석을 자르지 못한다. 띠를 넘칠 공정명은 줄이고 전체 이름은 hover 로 준다."""
    long_name = "DEMO Post Singulation Edge Inspection"
    density = pd.DataFrame({"생산계획년월": [202609], "년월": ["26.09"], "부하량": [1.5]})
    top5 = pd.DataFrame(
        {
            "생산계획년월": [202609, 202609],
            "년월": ["26.09", "26.09"],
            "순위": [1, 2],
            "공정": [long_name, "DEMO SAW"],
            "확보율": [0.9, 1.0],
            "Wafer Capa": [11_000.0, 12_000.0],
            "B/N Capa": [1.2, 1.3],
        }
    )
    _, month_figure = build_lob_summary_figures(
        monthly_density=density,
        monthly_top5=top5,
        bottleneck_capacity=density.assign(공정="DEMO SAW", 확보율=0.9, **{"B/N Capa": 1.2}),
        lob_summary=density.assign(**{"Wafer 부하량": 12_000.0, "Wafer Capa": 11_000.0}),
        month_labels=["26.09"],
        secure_threshold=1.095,
        warning_threshold=0.995,
    )
    rotated = {
        str(item.hovertext or item.text): item
        for item in month_figure.layout.annotations
        if item.textangle == -90 and item.yanchor == "top"
    }

    shortened = rotated[long_name]
    assert shortened.text.endswith("…")
    assert len(shortened.text) <= top5_process_label_budget()
    assert long_name.startswith(shortened.text[:-1].rstrip())
    assert rotated["DEMO SAW"].text == "DEMO SAW"
    assert rotated["DEMO SAW"].hovertext is None
