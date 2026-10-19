# Purpose: 표 밖으로 옮긴 칸 글자의 자리(열 가운데·축 범위)와 제 칸 경계에서 잘리는 계약을 고정한다.

"""표 밖 칸 글자(`plotly_layout.table_text_layer`)의 계약.

`go.Table` 은 칸 글자를 열마다 열 경계(± 선 굵기 반, 1px)에서 잘랐다. 표 밖 scatter 글자는 축
영역에서만 잘리므로, 넘칠 수 있는 글자만 그 열 하나를 덮는 축에 따로 얹어 같은 자리에서 자른다.
넘칠 수 없는 글자는 축을 늘리지 않는다 — 축 하나가 그대로 노드와 전송 바이트다.
"""

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pytest

from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.home_figures import build_plan_detail_figures
from capa_simulation.components.monthly_table_base import (
    MONTH_COLUMN_WIDTH_PX,
    build_split_table_figures,
    header_label,
)
from capa_simulation.components.plotly_layout import (
    TABLE_COLUMN_CLIP_OVERHANG_PX,
    TableText,
    figure_from_spec,
    plotly_validation,
    table_text_layer,
    table_text_max_width_px,
)
from capa_simulation.design import tokens
from capa_simulation.services.dashboard import DETAIL_DIMENSION_WIDTHS

FONT = {"size": 14, "family": "sans-serif", "color": "#000000"}
# 40자 이름. 사내 실데이터의 긴 제품명·거래선 자리다(값은 합성).
LONG_NAME = "DEMO_" + "X" * 35


def _as_json(figure: Any) -> Any:
    return json.loads(pio.to_json(figure, validate=False))


def _px(axis: dict[str, Any], width_px: float, x: float) -> float:
    """축 영역·범위로 x 가 서는 px. 같은 x 는 어느 축에서든 같은 px 여야 한다."""
    low, high = axis["range"]
    domain_low, domain_high = axis.get("domain", [0, 1])
    return float(width_px * (domain_low + (x - low) / (high - low) * (domain_high - domain_low)))


def test_text_that_fits_stays_on_the_shared_axis() -> None:
    """넘칠 수 없는 글자뿐이면 축도 trace 도 늘지 않는다 — 월 칸·짧은 머리글이 그렇다."""
    traces, layout = table_text_layer(
        [TableText(cells=[(0, 10.0, "<b>26.07</b>"), (1, 10.0, "1,000K")], font=FONT)],
        column_widths=[1.0, 1.0],
        width_px=2 * MONTH_COLUMN_WIDTH_PX,
        height_px=50,
    )

    assert len(traces) == 1
    assert traces[0]["cliponaxis"] is False and "xaxis" not in traces[0]
    assert traces[0]["x"] == [0.5, 1.5]
    assert set(layout) == {"xaxis", "yaxis", "plot_bgcolor"}
    # 종이와 같은 색이면 Plotly 가 축 바탕을 그리지 않는다.
    assert layout["plot_bgcolor"] == tokens.CHART_CANVAS
    assert layout["xaxis"]["range"] == [0, 2.0]
    assert layout["yaxis"]["range"] == [50, 0]


def test_text_that_may_overflow_is_clipped_at_its_own_column() -> None:
    """넘칠 수 있는 글자는 그 열 하나를 덮는 축에 얹혀 `go.Table` 처럼 열 경계 ± 1px 에서 잘린다."""
    widths = [84.0, 150.0, 110.0]
    width_px = sum(widths)
    traces, layout = table_text_layer(
        [
            TableText(cells=[(0, 5.0, "짧음"), (1, 5.0, LONG_NAME), (2, 5.0, "")], font=FONT),
            TableText(cells=[(1, 30.0, "값"), (2, 30.0, LONG_NAME)], font=FONT),
        ],
        column_widths=widths,
        width_px=width_px,
        height_px=60,
    )

    # 벌마다 자르지 않는 trace 가 차례대로 먼저, 자르는 trace 는 열 차례로 그 뒤다.
    assert [trace["text"] for trace in traces] == [["짧음"], ["값"], [LONG_NAME], [LONG_NAME]]
    assert [trace.get("xaxis") for trace in traces] == [None, None, "x2", "x3"]
    assert [trace["cliponaxis"] for trace in traces] == [False, False, True, True]
    assert traces[2]["y"] == [5.0] and traces[3]["y"] == [30.0]
    # 글자 점은 늘 제 열 가운데다 — 축이 달라도 같은 px 에 선다.
    for trace, column in ((traces[2], 1), (traces[3], 2)):
        axis = layout["xaxis" + trace["xaxis"][1:]]
        center = sum(widths[:column]) + widths[column] / 2
        assert trace["x"] == [center]
        assert _px(axis, width_px, center) == pytest.approx(center)
        # 축 영역은 열 구간 ± 1px — `go.Table` 의 `columnBoundaryClippath` 와 같다.
        low = sum(widths[:column]) - TABLE_COLUMN_CLIP_OVERHANG_PX
        high = min(width_px, sum(widths[: column + 1]) + TABLE_COLUMN_CLIP_OVERHANG_PX)
        assert axis["domain"] == pytest.approx([low / width_px, high / width_px])
        assert axis["range"] == pytest.approx([low, high])
        assert axis["visible"] is False and axis["anchor"] == "y"
    # 마지막 열은 그림 끝에서 멈춘다(영역은 0~1 밖으로 나갈 수 없다).
    assert layout["xaxis3"]["domain"][1] == 1.0
    # 자르는 축의 영역은 앞 축과 겹쳐 Plotly 가 그 바탕을 아래층 도형 위에 깐다. 바탕은 투명이다.
    assert layout["plot_bgcolor"] == tokens.TRANSPARENT


def test_the_first_column_clip_stops_at_the_figure_edge() -> None:
    traces, layout = table_text_layer(
        [TableText(cells=[(0, 5.0, LONG_NAME)], font=FONT)],
        column_widths=[1.0, 1.0],
        width_px=200,
        height_px=20,
    )

    assert traces[0]["text"] == [] and traces[1]["xaxis"] == "x2"
    assert layout["xaxis2"]["domain"] == pytest.approx([0.0, 101 / 200])
    assert layout["xaxis2"]["range"] == pytest.approx([0.0, 1.01])


def test_a_figure_without_width_clips_nothing() -> None:
    """폭이 0 인 그림(칸이 없는 표)은 자를 자리가 없다. 0 으로 나누지 않는다."""
    traces, layout = table_text_layer(
        [TableText(cells=[(0, 5.0, LONG_NAME)], font=FONT)],
        column_widths=[1.0],
        width_px=0,
        height_px=20,
    )

    assert traces[0]["text"] == [LONG_NAME]
    assert "xaxis2" not in layout


def test_the_width_bound_reads_through_plotly_markup() -> None:
    """`<b>` 는 폭이 없고, `<br>` 는 줄을 나누고, `&amp;` 는 한 글자다."""
    assert table_text_max_width_px("<b>ab</b>", 10) == table_text_max_width_px("ab", 10)
    assert table_text_max_width_px("ab<br>a", 10) == table_text_max_width_px("ab", 10)
    assert table_text_max_width_px("a&amp;b", 10) == table_text_max_width_px("a&b", 10)
    # 표 머리글·월 값처럼 짧은 글자는 월 칸(100px)에 넘칠 수 없다고 본다.
    assert table_text_max_width_px(header_label("26.07"), 14) <= MONTH_COLUMN_WIDTH_PX
    assert table_text_max_width_px("10,000K", 14) <= MONTH_COLUMN_WIDTH_PX
    # 한글·그 밖의 글자도 위 한계가 있다.
    assert table_text_max_width_px("거래선", 10) == pytest.approx(33)
    assert table_text_max_width_px("→", 10) == pytest.approx(13)


def test_result_table_headers_sit_at_their_column_centers() -> None:
    """결과표 머리글 글자의 x 는 열 폭 누적의 가운데, 축 범위는 열 폭 합이다.

    폭이 서로 다른 분류 열에서 이 셈이 틀리면 머리글만 옆으로 밀린다.
    """
    widths = [84, 150, 110]
    label_figure, month_figure = build_split_table_figures(
        classification_headers=[header_label(name) for name in ("공정", "제품", "PKG Code")],
        classification_values=[["a"], ["b"], ["c"]],
        classification_fill_colors=[["#FFFFFF"]] * 3,
        column_widths=widths,
        month_headers=[header_label(month) for month in ("26.01", "26.02", "26.03")],
        month_values=[["1"], ["2"], ["3"]],
        month_row_colors=["#FFFFFF"],
        row_count=1,
    )

    label_headers = label_figure.data[1]
    assert list(label_headers.x) == [42, 84 + 75, 84 + 150 + 55]
    assert tuple(label_figure.layout.xaxis.range) == (0, sum(widths))
    assert len(label_figure.data) == 2, "짧은 머리글은 자르는 trace 를 만들지 않는다"
    month_headers = month_figure.data[1]
    assert list(month_headers.x) == [0.5, 1.5, 2.5]
    assert tuple(month_figure.layout.xaxis.range) == (0, 3)
    assert month_figure.layout.width == 3 * MONTH_COLUMN_WIDTH_PX


def test_a_long_result_table_header_is_clipped_and_keeps_the_fast_path() -> None:
    """넘칠 수 있는 머리글은 그 열에서 잘리고, 번호 붙은 축이 있어도 검증 없는 길로 세운다."""
    kwargs: dict[str, Any] = {
        "classification_headers": [header_label("공정"), header_label(LONG_NAME)],
        "classification_values": [["a"], ["b"]],
        "classification_fill_colors": [["#FFFFFF"]] * 2,
        "column_widths": [84, 220],
        "month_headers": [header_label("26.01")],
        "month_values": [["1"]],
        "month_row_colors": ["#FFFFFF"],
        "row_count": 1,
    }
    fast = [_as_json(figure) for figure in build_split_table_figures(**kwargs)]
    with plotly_validation():
        checked = [_as_json(figure) for figure in build_split_table_figures(**kwargs)]

    assert fast == checked
    label = fast[0]
    assert [trace.get("xaxis") for trace in label["data"][1:]] == [None, "x2"]
    assert label["data"][1]["text"] == [header_label("공정")]
    assert label["data"][2]["text"] == [header_label(LONG_NAME)]
    assert label["layout"]["xaxis2"]["domain"] == pytest.approx([83 / 304, 1.0])
    assert "xaxis2" not in fast[1]["layout"]


def test_numbered_axes_do_not_send_a_spec_to_the_validating_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`xaxis2` 는 아는 이름이다. Plotly 가 이름을 바꿔 담는 `xaxis1` 은 검증 생성자로 간다."""
    calls: list[bool] = []
    original = go.Figure.__init__

    def spy(self: Any, *args: Any, **kwargs: Any) -> None:
        calls.append(kwargs.get("_validate", True))
        original(self, *args, **kwargs)

    monkeypatch.setattr(go.Figure, "__init__", spy)
    axis = {"visible": False, "range": [0, 1], "domain": [0, 0.5], "anchor": "y"}
    figure_from_spec({"data": [], "layout": {"xaxis2": axis}})
    figure_from_spec({"data": [], "layout": {"xaxis1": axis}})
    figure_from_spec({"data": [], "layout": {"xaxis02": axis}})

    assert calls == [False, True, True]


def _long_detail() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": [LONG_NAME, LONG_NAME, "DEMO_B"],
            "Stack": ["8H", "12H", "8H"],
            "Customer": ["DEMO_C", LONG_NAME, "DEMO_C"],
            "202608": [1000.0, 500.0, 300.0],
        }
    )


def test_long_plan_detail_names_are_clipped_at_their_column() -> None:
    """「상세 계획」 칸(제품·Stack·거래선)의 긴 이름은 제 칸에서 잘린다.

    짧은 값과 월 칸은 그대로다.
    """
    dimensions = ["제품정보", "Stack", "Customer"]
    label_figure, month_figure = build_plan_detail_figures(
        production_detail=_long_detail(),
        month_labels=["202608"],
        detail_dimensions=dimensions,
    )

    widths = [DETAIL_DIMENSION_WIDTHS[column] for column in dimensions]
    units = sum(widths)
    px_per_unit = DASHBOARD_LABEL_COLUMN_WIDTH_PX / units
    layout = label_figure.layout
    values = label_figure.data[1]
    # 같은 제품의 둘째 행은 비운다(묶음). 남는 긴 이름 셋은 모두 자르는 trace 로 갔다.
    assert LONG_NAME not in list(values.text)
    clipped = {trace.xaxis: list(trace.text) for trace in label_figure.data[2:]}
    product_axis = layout["xaxis" + next(k for k, v in clipped.items() if v == [LONG_NAME])[1:]]
    assert product_axis.domain[0] == 0
    assert product_axis.domain[1] == pytest.approx(
        (widths[0] * px_per_unit + 1) / DASHBOARD_LABEL_COLUMN_WIDTH_PX
    )
    assert all(trace.cliponaxis for trace in label_figure.data[2:])
    assert sum(len(texts) for texts in clipped.values()) >= 2
    # 넘칠 수 없는 값(Stack·짧은 거래선)은 자르지 않는 trace 에 남는다.
    assert {"8H", "12H", "DEMO_B", "DEMO_C"} <= set(values.text)
    # 월 칸 값은 넘치지 않는다 — 축이 늘지 않는다.
    assert "xaxis2" not in _as_json(month_figure)["layout"]
    assert len(month_figure.data) == 2
