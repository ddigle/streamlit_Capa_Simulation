# Purpose: HOME `Capa LOB 현황` 의 B/N·Top 5 막대가 공정 Capa 상세 이동 정보를 싣는지 지킨다.

"""`Capa LOB 현황` 막대 클릭 → 공정 Capa 상세(2026-10-18 사용자 요청).

히트맵·상세 B/N 칸처럼 막대 `customdata` **끝**에 이동 정보 일곱 칸(`HOME_CELL_LINK_FIELDS`)을 싣고,
같은 콜백(`home_rendering.open_clicked_home_cell`)이 읽는다. hover 칸 차례는 그대로다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.design import tokens
from capa_simulation.process_detail_state import (
    HOME_CELL_LINK_FIELDS,
    first_home_cell_link,
    parse_home_cell_link,
)
from capa_simulation.services.process_rename import PROCESS_RENAME_COLUMNS
from capa_simulation.services.securement_threshold import SecurementThresholds

LABELS = process_labels_from_rules(
    pd.DataFrame(
        [{"공정": "P1", "표시명": "표시-P1"}],
        columns=list(PROCESS_RENAME_COLUMNS),
    ),
    version=1,
)
MONTHS = ["26.07", "26.08", "26.09"]


def _frames(*, adjusted: bool = False) -> dict[str, pd.DataFrame]:
    """과거 실적 한 달(26.07)과 계획 두 달. 26.09 는 B/N 공정이 없다(빈 막대)."""
    months = [202607, 202608, 202609]
    density = pd.DataFrame({"생산계획년월": months, "년월": MONTHS, "부하량": [8.0, 10.0, 12.0]})
    bottleneck = pd.DataFrame(
        {
            "생산계획년월": months,
            "년월": MONTHS,
            "공정": ["P1", "P1", None],
            "확보율": [0.9, 0.8, None],
            "가용대수": [9.0, 8.0, None],
            "소요대수": [10.0, 10.0, None],
            "B/N Capa": [7.2, 8.0, None],
        }
    )
    top5 = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "년월": ["26.08", "26.08"],
            "공정": ["P1", "P2"],
            "순위": [1, 2],
            "부하량": [10.0, 10.0],
            "확보율": [0.8, 1.2],
            "가용대수": [8.0, 12.0],
            "소요대수": [10.0, 10.0],
            "B/N Capa": [8.0, 12.0],
            "Wafer Capa": [800.0, 1200.0],
        }
    )
    if adjusted:
        # 확보율 보정 +5%p — 막대 위에 증감 조각이 선다.
        for frame in (bottleneck, top5):
            frame["기준 확보율"] = frame["확보율"] - 0.05
            frame["확보율 증감"] = [5.0 if pd.notna(rate) else 0.0 for rate in frame["확보율"]]
        bottleneck["기준 B/N Capa"] = density["부하량"] * bottleneck["기준 확보율"]
        top5["기준 B/N Capa"] = top5["부하량"] * top5["기준 확보율"]
    return {
        "monthly_density": density,
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": MONTHS,
                "부하량": [8.0, 10.0, 12.0],
                "Wafer 부하량": [800.0, 1000.0, 1200.0],
                "Wafer Capa": [720.0, 800.0, None],
            }
        ),
        "bottleneck_capacity": bottleneck,
        "monthly_top5": top5,
    }


def _month_figure(*, adjusted: bool = False) -> Any:
    frames = _frames(adjusted=adjusted)
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=MONTHS,
        process_labels=LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        past_month_labels={"26.07"},
    )
    return month_figure


def _links(trace: Any) -> list[Any]:
    return [parse_home_cell_link(list(row)) for row in trace.customdata]


def _traces(figure: Any, name: str) -> list[Any]:
    return [trace for trace in figure.data if getattr(trace, "name", None) == name]


def test_the_bn_bars_carry_the_original_process_and_month() -> None:
    """생산계획 LOB 의 B/N 막대는 달마다 그 달 B/N 공정의 **원래 이름**과 달을 싣는다(hover 는
    표시명). 과거 실적 달과 B/N 공정이 없는 달은 비워 콜백이 무시한다."""
    (trace,) = _traces(_month_figure(), "B/N 공정")
    links = _links(trace)
    assert links[0] is None and links[2] is None
    link = links[1]
    assert link is not None
    assert (link.process, link.month) == ("P1", 202608)
    assert link.displayed_rate == pytest.approx(0.8)
    assert (link.available, link.required, link.raw_rate) == (8.0, 10.0, pytest.approx(0.8))
    # hover 칸 차례(년월 · 확보율 · 표시명)는 그대로다 — 이동 정보는 끝에만 붙는다.
    assert list(trace.customdata[1][:3]) == ["26.08", 0.8, "표시-P1"]
    assert len(trace.customdata[1]) == 3 + len(HOME_CELL_LINK_FIELDS)


def test_each_top5_bar_carries_its_own_process() -> None:
    (trace,) = _traces(_month_figure(), "B/N Capa Top 5")
    links = _links(trace)
    assert [(link.process, link.month) for link in links if link] == [
        ("P1", 202608),
        ("P2", 202608),
    ]
    assert list(trace.customdata[1][:2]) == ["26.08", "P2"]


def test_a_click_on_a_bar_picks_its_link() -> None:
    """Streamlit 선택 상태의 점 `customdata` 로 이동할 칸을 찾는다 — 히트맵과 같은 길."""
    (trace,) = _traces(_month_figure(), "B/N Capa Top 5")
    state = {"selection": {"points": [{"customdata": list(trace.customdata[1])}]}}
    link = first_home_cell_link(state)
    assert link is not None and (link.process, link.month) == ("P2", 202608)


def test_the_delta_piece_on_an_adjusted_bar_opens_the_same_process() -> None:
    """확보율 보정으로 막대 위에 선 증감 조각을 눌러도 그 막대와 같은 곳으로 간다. hover 는 첫 칸
    그대로다."""
    figure = _month_figure(adjusted=True)
    pieces = [
        trace
        for trace in figure.data
        if trace.type == "bar"
        and trace.hovertemplate == "%{customdata[0]}<extra></extra>"
        and trace.customdata is not None
    ]
    linked = [link for piece in pieces for link in _links(piece) if link is not None]
    assert ("P1", 202608) in {(link.process, link.month) for link in linked}
    assert ("P2", 202608) in {(link.process, link.month) for link in linked}


def test_a_click_does_not_dim_the_bars_or_their_text() -> None:
    """막대를 누르면 화면을 옮기는 것이지 고른 막대를 강조하는 것이 아니다 — 고르지 않은 막대·
    꺾은선·막대 안 글자가 흐려지지 않는다."""
    figure = _month_figure()
    for trace in figure.data:
        if trace.type in ("bar", "scatter"):
            assert trace.unselected.marker.opacity == 1, trace.name
    (bars,) = _traces(figure, "B/N 공정")
    assert bars.unselected.textfont.color == tokens.TEXT
    # 고른 쪽 글자색도 있어야 한다 — 한쪽만 있으면 Plotly 가 클릭 선택에서 멈춰 이동하지 않았다.
    assert bars.selected.textfont.color == tokens.TEXT


def test_the_density_points_open_the_month_bn_process() -> None:
    """Density 꺾은선 점은 그 달 B/N 막대와 같은 이동 정보를 싣는다 — Plotly 가 막대보다 점을 먼저
    잡아, 꺾은선에 가까운 막대 윗부분을 누르면 점이 골라지기 때문이다. hover 는 첫 칸(라벨)
    그대로이고, 과거 실적·B/N 없는 달은 비운다."""
    (density,) = _traces(_month_figure(), "Density")
    assert density.hovertemplate.startswith("%{customdata[0]}<br>")
    assert [row[0] for row in density.customdata] == MONTHS
    links = _links(density)
    assert links[0] is None and links[2] is None
    assert links[1] is not None and (links[1].process, links[1].month) == ("P1", 202608)
