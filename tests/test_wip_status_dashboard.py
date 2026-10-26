# Purpose: wip status dashboard 관련 정상·예외·회귀 동작을 검증한다.

import math
from datetime import date

import pandas as pd
import pytest

from capa_simulation.components.wip_status_dashboard import (
    WIP_GRID_CELL_HEIGHT_PX,
    WIP_GRID_CELL_WIDTH_PX,
    WIP_GRID_ROW_GAP_PX,
    build_wip_status_grid_figure,
)
from capa_simulation.services.wip_status import build_wip_history_demo

# 가로 범례 한 줄(11px 서체)의 높이 — 브라우저 실측 29px(2026-10-27, 1줄 격자의 범례 상자).
_LEGEND_PX_PER_FONT_PX = 29 / 11
# plotly 자동 여백이 범례 바깥에 두는 띄움(`margin.pad` 가 없을 때 12px 와 가장 작은 여백 가운데
# 작은 값). 범례 위 끝 + 이 띄움이 위 여백을 넘으면 plotly 가 위 여백을 늘린다.
_AUTOMARGIN_PAD_PX = 12


def test_wip_grid_places_steps_in_columns_and_products_in_rows() -> None:
    routes = pd.DataFrame(
        {
            "공정": ["T-Process", "P-Process", "T-Process", "P-Process"],
            "STEP_SEQ": ["T100", "P100", "T100", "P100"],
            "제품정보": ["Product-B", "Product-B", "Product-A", "Product-A"],
            "소요기준": ["WF", "CHIP", "WF", "CHIP"],
        }
    )
    dates = pd.date_range("2026-09-01", "2026-09-02", freq="D")
    standard_rows: list[dict[str, object]] = []
    for current_date in dates:
        for process, basis in (("P-Process", "CHIP"), ("T-Process", "WF")):
            for product in ("Product-A", "Product-B"):
                standard_rows.append(
                    {
                        "일자": current_date,
                        "공정": process,
                        "소요기준": basis,
                        "제품정보": product,
                        "일 표준 가능량": 100.0,
                    }
                )
    history = build_wip_history_demo(
        routes,
        pd.DataFrame(standard_rows),
        date(2026, 9, 1),
        date(2026, 9, 2),
        today=date(2026, 9, 1),
    )

    figure = build_wip_status_grid_figure(
        history,
        routes,
        ["Product-B", "Product-A"],
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    titles = [annotation.text for annotation in figure.layout.annotations]
    assert titles[:4] == [
        "<b>P100</b> · P-Process<br>Product-B",
        "<b>T100</b> · T-Process<br>Product-B",
        "<b>P100</b> · P-Process<br>Product-A",
        "<b>T100</b> · T-Process<br>Product-A",
    ]
    assert figure.layout.width == 2 * WIP_GRID_CELL_WIDTH_PX + 90
    assert figure.layout.height == 92 + 50 + 2 * WIP_GRID_CELL_HEIGHT_PX + WIP_GRID_ROW_GAP_PX
    assert figure.layout.barmode == "group"
    trace_names = {trace.name for trace in figure.data}
    assert {"보유 재공", "유입", "표준 가능량"}.issubset(trace_names)
    assert {"Flow 충족", "Flow 부족"} & trace_names


def _products_by_two_grid(count: int) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """제품 `count` 줄 × (P·T) 두 칸 격자의 재공 이력·경로·제품."""
    products = [f"Product-{chr(ord('A') + index)}" for index in range(count)]
    routes = pd.DataFrame(
        [
            {"공정": process, "STEP_SEQ": step, "제품정보": product, "소요기준": basis}
            for product in products
            for process, step, basis in (("P-Process", "P100", "CHIP"), ("T-Process", "T100", "WF"))
        ]
    )
    standard_rows = [
        {
            "일자": current_date,
            "공정": process,
            "소요기준": basis,
            "제품정보": product,
            "일 표준 가능량": 100.0,
        }
        for current_date in pd.date_range("2026-10-20", "2026-10-26", freq="D")
        for process, basis in (("P-Process", "CHIP"), ("T-Process", "WF"))
        for product in products
    ]
    history = build_wip_history_demo(
        routes,
        pd.DataFrame(standard_rows),
        date(2026, 10, 20),
        date(2026, 10, 26),
        today=date(2026, 10, 26),
    )
    return history, routes, products


def test_rows_leave_room_for_the_two_line_title_and_the_tilted_date_ticks() -> None:
    """둘째 줄부터의 두 줄 칸 제목이 바로 위 칸의 -45° 날짜 눈금과 겹쳤다(2026-10-26 E2E — 줄 사이
    약 27px 에 제목 약 29px + 기울인 눈금 약 23px). 줄 사이 틈(px)이 그 둘을 담고도 사이가 뜬다.

    글자 높이는 그림의 서체 크기로 어림한다 — 제목은 줄 수 × 크기 × 1.3(plotly.js 줄 간격), 눈금은
    가장 긴 글자 폭(숫자 0.6em)과 크기를 -45° 로 돌린 상자의 높이다.
    """
    history, routes, products = _products_by_two_grid(3)
    figure = build_wip_status_grid_figure(
        history, routes, products, date(2026, 10, 20), date(2026, 10, 26)
    )

    plot_height = figure.layout.height - figure.layout.margin.t - figure.layout.margin.b
    title = figure.layout.annotations[0]
    title_px = (str(title.text).count("<br>") + 1) * title.font.size * 1.3
    axis = figure.get_subplot(1, 1).xaxis
    tick_size = axis.tickfont.size
    longest = max(len(str(text)) for text in axis.ticktext)
    tick_px = (longest * 0.6 * tick_size + tick_size) * math.sin(math.radians(abs(axis.tickangle)))
    for row in (1, 2):
        for col in (1, 2):
            upper = figure.get_subplot(row, col).yaxis.domain
            lower = figure.get_subplot(row + 1, col).yaxis.domain
            gap_px = (upper[0] - lower[1]) * plot_height
            # 눈금과 제목 사이도 떠야 제목이 아래 칸 것으로 읽힌다
            # (64px 틈은 어림 7px — 브라우저 2px).
            assert gap_px - (title_px + tick_px) >= 16, (row, col, gap_px, title_px, tick_px)
    # 칸 높이는 줄 수와 상관없이 그대로다.
    for row in (1, 2, 3):
        domain = figure.get_subplot(row, 1).yaxis.domain
        assert round((domain[1] - domain[0]) * plot_height) == WIP_GRID_CELL_HEIGHT_PX


@pytest.mark.parametrize("rows", [1, 2, 3, 4])
def test_the_legend_clears_the_first_row_titles_whatever_the_row_count(rows: int) -> None:
    """제품을 하나만 고르면(격자 1줄) 범례가 첫 줄 칸 제목 위에 17px 겹쳐 그려졌다(2026-10-27 E2E).
    범례 y(`1.055`)가 축 영역 비율이라 1줄(축 영역 300px)에서는 약 16px 만 떠, 두 줄 제목(약
    31px) 안에 들어갔다. 범례 아래 끝은 줄 수와 상관없이 첫 줄 제목 위로 떠야 하고, 범례 위 끝은 위
    여백 안이어야 한다 — 위 여백을 넘으면 plotly 가 위 여백을 늘려 칸 높이가 줄어든다(3줄의 1.055 도
    브라우저에서 약 7px 늘었다).

    제목 높이는 줄 수 × 크기 × 1.3(plotly.js 줄 간격)으로, 범례 높이는 서체 크기에 대한 브라우저
    실측 비로 어림한다.
    """
    history, routes, products = _products_by_two_grid(rows)
    figure = build_wip_status_grid_figure(
        history, routes, products, date(2026, 10, 20), date(2026, 10, 26)
    )

    legend = figure.layout.legend
    assert legend.yanchor == "bottom"
    plot_height = figure.layout.height - figure.layout.margin.t - figure.layout.margin.b
    title = figure.layout.annotations[0]
    title_px = (str(title.text).count("<br>") + 1) * title.font.size * 1.3
    first_row_top = figure.get_subplot(1, 1).yaxis.domain[1]
    lift_px = (legend.y - first_row_top) * plot_height
    assert lift_px - title_px >= 16, (rows, lift_px, title_px)
    legend_px = legend.font.size * _LEGEND_PX_PER_FONT_PX
    assert lift_px + legend_px + _AUTOMARGIN_PAD_PX <= figure.layout.margin.t, (rows, lift_px)
