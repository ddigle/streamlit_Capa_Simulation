# Purpose: B/N Top5 확보율 구간의 검증·저장·막대 높이 반영을 고정한다.

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.design import tokens
from capa_simulation.services.process_rename import PROCESS_RENAME_COLUMNS
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.top5_band import (
    DEFAULT_TOP5_MAX_RATE,
    DEFAULT_TOP5_MIN_RATE,
    clamp_rate,
    validate_top5_band,
)

LABELS = process_labels_from_rules(
    pd.DataFrame([], columns=list(PROCESS_RENAME_COLUMNS)),
    version=1,
)
MONTHS = ["26.08"]


def test_default_band_is_fifty_to_two_hundred_percent() -> None:
    """화면 기본값이다. 확보율은 비율이라 0.5 = 50% 다."""
    assert (DEFAULT_TOP5_MIN_RATE, DEFAULT_TOP5_MAX_RATE) == (0.50, 2.00)


def test_band_rejects_an_inverted_or_negative_range() -> None:
    with pytest.raises(ValueError, match="상한은 하한보다"):
        validate_top5_band(2.0, 0.5)
    with pytest.raises(ValueError, match="0% 이상"):
        validate_top5_band(-0.1, 2.0)


def test_clamp_cuts_at_both_ends() -> None:
    band = (0.5, 2.0)
    assert clamp_rate(0.2, band) == pytest.approx(0.5)
    assert clamp_rate(1.0, band) == pytest.approx(1.0)
    assert clamp_rate(28.6, band) == pytest.approx(2.0)


def _frames() -> dict[str, pd.DataFrame]:
    """한 달, Top5 세 줄. 확보율이 밴드 아래·안·위로 하나씩이다."""
    density = pd.DataFrame({"생산계획년월": [202608], "년월": ["26.08"], "부하량": [10.0]})
    return {
        "monthly_density": density,
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "부하량": [10.0],
                "Wafer 부하량": [1000.0],
                "Wafer Capa": [900.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "공정": ["P1"],
                "확보율": [0.3],
                "B/N Capa": [3.0],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": [202608, 202608, 202608],
                "년월": ["26.08"] * 3,
                "공정": ["P1", "P2", "P3"],
                "순위": [1, 2, 3],
                "부하량": [10.0, 10.0, 10.0],
                "확보율": [0.30, 1.00, 28.60],
                "B/N Capa": [3.0, 10.0, 286.0],
                "Wafer Capa": [300.0, 1000.0, 28600.0],
            }
        ),
    }


def _top5_trace(figure: object) -> object:
    return next(
        trace
        for trace in figure.data  # type: ignore[attr-defined]
        if getattr(trace, "name", "") == "B/N Capa Top 5"
    )


def _build(band: tuple[float, float]) -> object:
    frames = _frames()
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=MONTHS,
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        top5_rate_band=band,
    )
    return month_figure


def test_bar_heights_are_cut_at_the_band() -> None:
    """막대 높이는 **밴드로 자른 확보율 그 자체**다. 부하량을 곱하지 않는다.

    밴드가 없으면 확보율 2860% 인 공정 하나가 그 달의 다른 막대를 눈동자로 만든다.
    """
    trace = _top5_trace(_build((0.5, 2.0)))

    # 30% → 50% 로 올리고, 100% 는 그대로, 2860% → 200% 로 자른다.
    assert list(trace.y) == pytest.approx([0.5, 1.0, 2.0])  # type: ignore[attr-defined]


def test_a_wider_band_lets_the_tall_bar_grow() -> None:
    """구간을 넓히면 잘리던 막대가 그만큼 자란다."""
    trace = _top5_trace(_build((0.5, 5.0)))

    assert list(trace.y) == pytest.approx([0.5, 1.0, 5.0])  # type: ignore[attr-defined]


def _two_month_frames() -> dict[str, pd.DataFrame]:
    """부하량이 다른 두 달. 각 달에 확보율 180% 공정이 하나씩 있다."""
    months = [202608, 202609]
    labels = ["26.08", "26.09"]
    loads = [10.0, 40.0]
    density = pd.DataFrame({"생산계획년월": months, "년월": labels, "부하량": loads})
    return {
        "monthly_density": density,
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "부하량": loads,
                "Wafer 부하량": [1000.0, 4000.0],
                # 두 달의 LOB B/N 확보율이 100% 와 150% 로 다르다.
                "Wafer Capa": [1000.0, 6000.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "공정": ["P1", "P1"],
                "확보율": [1.00, 1.50],
                "B/N Capa": [10.0, 60.0],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "공정": ["P9", "P9"],
                "순위": [1, 1],
                # 부하량이 4배 차이 난다. 예전 규칙이면 막대 길이도 4배 차이 났다.
                "부하량": loads,
                "확보율": [1.80, 1.80],
                "B/N Capa": [18.0, 72.0],
                "Wafer Capa": [1800.0, 7200.0],
            }
        ),
    }


def test_equal_rates_draw_equal_bars_even_when_loads_differ() -> None:
    """확보율이 같으면 막대 길이가 같아야 한다. 사용자가 신고한 그 조건이다.

    LOB B/N 확보율이 100% 인 달과 150% 인 달에 각각 180% 공정이 있고 부하량은 4배 차이다.
    예전 규칙(`부하량 × 확보율`)에서는 두 막대가 18 과 72 로 갈렸다.
    """
    frames = _two_month_frames()
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=["26.08", "26.09"],
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        top5_rate_band=(0.5, 2.0),
    )

    heights = list(_top5_trace(month_figure).y)  # type: ignore[attr-defined]
    assert heights[0] == pytest.approx(heights[1])
    assert heights == pytest.approx([1.8, 1.8])


def test_the_axis_top_is_the_band_ceiling_not_the_data_peak() -> None:
    """축 위끝이 데이터 최대면 다시 그릴 때마다 같은 확보율이 다른 높이에 선다."""
    tall = _top5_trace(_build((0.5, 2.0)))
    assert max(tall.y) == pytest.approx(2.0)  # type: ignore[attr-defined]

    axis_range = _build((0.5, 2.0)).layout.yaxis2.range  # type: ignore[attr-defined]
    # 라벨 자리만큼 위가 비므로 상한보다 크되, 상한에 묶여 있어야 한다.
    assert axis_range[0] == pytest.approx(0.0)
    assert 2.0 < axis_range[1] < 2.0 / (1 - 0.5)


def test_hover_keeps_the_real_capa_not_the_cut_bar() -> None:
    """자르는 것은 막대 길이뿐이다. hover 숫자는 실제 Capa 여야 한다."""
    trace = _top5_trace(_build((0.5, 2.0)))

    template = trace.hovertemplate  # type: ignore[attr-defined]
    assert "customdata[4]" in template, template
    assert "%{y" not in template, "잘린 막대 값이 hover 에 뜬다"
    assert list(trace.customdata[2])[4] == pytest.approx(286.0)  # type: ignore[attr-defined]


def test_the_threshold_lines_skip_the_year_total_column() -> None:
    """판정 기준선은 **월 칸 위에만** 긋는다.

    연간 Total 열은 확보율을 더하지 않는 빈 칸이라 그 위로 선이 지나가면 합계에도 기준이
    있는 것처럼 읽힌다. `add_hline` 은 축 전체를 가로지르므로 쓸 수 없다 — 이어진 월
    구간마다 선분을 따로 그어야 한다.
    """
    frames = _frames()
    months = ["26.07", "26.08", "26년", "27.01"]
    for frame_name in ("lob_summary", "monthly_density", "bottleneck_capacity", "monthly_top5"):
        frames[frame_name] = frames[frame_name].copy()
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=months,
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        year_totals={"26년": {}},
    )
    year_total_index = months.index("26년")
    threshold_lines = [
        shape
        for shape in month_figure.layout.shapes
        if shape.type == "line" and shape.yref == "y2" and shape.y0 == shape.y1
    ]

    # 기준 둘 × 끊긴 월 구간 둘 = 선분 넷. 어느 선분도 합계 열을 지나지 않는다.
    assert len(threshold_lines) == 4
    assert all(
        shape.x1 <= year_total_index - 0.5 or shape.x0 >= year_total_index + 0.5
        for shape in threshold_lines
    )


def test_the_month_header_keeps_its_fill_when_threshold_lines_are_drawn() -> None:
    """기준선을 `add_shape` 로 넣으면 **표 머리글 면색이 사라진다.**

    이 Figure 의 도형은 전부 `append_layout_items` 누적함에 모였다가 마지막에
    `update_layout(shapes=...)` 한 번으로 들어간다. Plotly 의 `update_layout` 은 배열을
    갈아끼우지 않고 **자리마다 병합**하므로, `add_shape` 로 먼저 들어간 기준선 N 개가
    누적함의 앞쪽 도형 N 개를 잡아먹는다 — 머리글 띠와 첫 달 값 칸이 캔버스 색으로
    비었던 실제 결함이다. 기준선 수가 달라져도 머리글은 남아야 한다.
    """
    frames = _frames()
    months = ["26.07", "26.08", "26년", "27.01"]
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=months,
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        year_totals={"26년": {}},
    )
    rects = [shape for shape in month_figure.layout.shapes if shape.type == "rect"]
    header_fills = [shape.fillcolor for shape in rects if shape.y1 == 1.0 and shape.yref == "paper"]
    # 값 세 줄은 칸마다 면색을 받으므로 달 수만큼 사각형이 있어야 한다. 하나라도 비면
    # 그 칸만 캔버스 색으로 보인다.
    value_row_counts = Counter(
        round(float(shape.y0), 6) for shape in rects if shape.yref == "paper" and shape.y1 < 1.0
    )

    assert tokens.HEADER_BACKGROUND in header_fills
    assert sorted(value_row_counts.values())[-3:] == [len(months)] * 3


def test_migration_is_registered(tmp_path: Path) -> None:
    """0022 가 카탈로그에 등재돼 있어야 한다. 기존 SQL 은 한 글자도 고치지 않는다."""
    root = Path(__file__).resolve().parents[1]
    catalog = (root / "docs/migration_catalog.md").read_text(encoding="utf-8")

    assert "0022_global_top5_band.sql" in catalog


def test_threshold_lines_step_with_a_monthly_exception() -> None:
    """월별 예외가 있으면 기준선이 **그 달 칸 폭만큼** 그 달 높이로 갈린다.

    기준이 바뀌지 않는 경고선은 한 줄 그대로다. 예외가 없으면 기준마다 이어진 월 구간 하나다.
    """
    frames = _frames()
    frames["lob_summary"] = pd.concat(
        [frames["lob_summary"].assign(생산계획년월=202607, 년월="26.07"), frames["lob_summary"]],
        ignore_index=True,
    )
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=["26.07", "26.08"],
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995, monthly=((202608, 1.195, None),)),
    )
    threshold_lines = sorted(
        (shape.y0, shape.x0, shape.x1)
        for shape in month_figure.layout.shapes
        if shape.type == "line" and shape.yref == "y2" and shape.y0 == shape.y1
    )

    assert threshold_lines == [(0.995, -0.5, 1.5), (1.095, -0.5, 0.5), (1.195, 0.5, 1.5)]
