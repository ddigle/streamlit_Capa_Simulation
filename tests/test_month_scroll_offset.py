# Purpose: 가로 스크롤 시작 위치와 B/N Top5 축 여유의 근거를 고정한다.

"""화면을 열었을 때 무엇이 왼쪽에 서고, 막대 위에 얼마를 비우는가.

둘 다 「보기 좋게」가 아니라 **셀 수 있는 근거**에서 나온다. 앞머리의 과거 칸 수와
확보율 라벨이 먹는 픽셀이 그것이다. 눈대중 비율로 적으면 행 높이나 조회기간을 바꿀
때마다 조용히 어긋난다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from capa_simulation.components.home_dimensions import (
    LOB_TOP5_HEIGHT_PX,
    TOP5_RATE_LABEL_CHAR_PX,
    TOP5_RATE_LABEL_GAP_PX,
    top5_axis_headroom_px,
)
from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.components.horizontal_scrollbar import render_horizontal_scrollbar
from capa_simulation.services.month_columns import (
    build_past_month_labels,
    leading_past_column_count,
)

# ------------------------------------------------------ 스크롤 시작 위치의 근거


def test_the_offset_counts_only_the_leading_past_columns() -> None:
    labels = ["26.01", "26.02", "26.07", "26.08"]
    past = build_past_month_labels(labels, [], {"26.07", "26.08"})

    assert leading_past_column_count(labels, past) == 2


def test_a_year_total_inside_the_past_run_is_counted() -> None:
    """25년 Total 은 그 해가 모두 과거라 과거 칸이다. 건너뛰지 않으면 그 칸이 왼쪽에 선다."""
    labels = ["25.11", "25.12", "25년", "26.07"]
    past = build_past_month_labels(labels, ["25년"], {"26.07"})

    assert leading_past_column_count(labels, past) == 3


def test_a_past_column_after_the_db_range_does_not_move_the_start() -> None:
    """연속된 앞머리만 건너뛴다. 중간 칸까지 세면 그 뒤의 열 순서가 어긋난다."""
    labels = ["26.07", "26.08", "26.09"]
    past = {"26.09"}

    assert leading_past_column_count(labels, past) == 0


def test_every_column_being_past_still_yields_a_full_count() -> None:
    labels = ["26.01", "26.02"]

    assert leading_past_column_count(labels, {"26.01", "26.02"}) == 2


# ------------------------------------------------------------- 컴포넌트 계약


def test_the_scrollbar_passes_the_offset_to_the_browser(monkeypatch: Any) -> None:
    sent: list[dict[str, Any]] = []
    _stub_component(monkeypatch, sent)

    render_horizontal_scrollbar(
        target_selector=".target",
        height=12,
        key="k",
        initial_offset_px=300.0,
    )

    assert sent[0]["initialOffsetPx"] == 300.0


def test_the_scrollbar_defaults_to_the_left_edge(monkeypatch: Any) -> None:
    """과거 구간을 쓰지 않는 다른 화면의 스크롤바가 움직이면 안 된다."""
    sent: list[dict[str, Any]] = []
    _stub_component(monkeypatch, sent)

    render_horizontal_scrollbar(target_selector=".target", height=12, key="k")

    assert sent[0]["initialOffsetPx"] == 0.0


def test_a_negative_offset_is_refused(monkeypatch: Any) -> None:
    """음수는 스크롤 위치가 아니다. 브라우저는 0 으로 자르므로 조용히 틀린 값이 산다."""
    _stub_component(monkeypatch, [])

    with pytest.raises(ValueError, match="0 이상"):
        render_horizontal_scrollbar(
            target_selector=".target",
            height=12,
            key="k",
            initial_offset_px=-1.0,
        )


def test_the_offset_is_applied_once_per_target_element() -> None:
    """리런마다 다시 걸면 사용자가 옮겨 둔 위치를 계속 되돌린다.

    표시는 컴포넌트가 아니라 **대상 요소**에 남긴다. 이 모듈이 다시 실행돼도 대상 DOM 이
    살아 있으면 표시가 함께 살아남는다.
    """
    from capa_simulation.components.horizontal_scrollbar import _SCROLLBAR_JS

    assert "target.dataset[INITIAL_OFFSET_MARK] !== String(initialOffsetPx)" in _SCROLLBAR_JS
    assert "target.dataset[INITIAL_OFFSET_MARK] = String(initialOffsetPx)" in _SCROLLBAR_JS


def test_a_data_change_tears_down_the_previous_instance() -> None:
    """**Streamlit 은 `data` 가 바뀌면 정리 없이 이 모듈을 다시 실행한다.**

    돌려주는 정리 함수는 unmount 때 한 번만 불리고 HTML 은 다시 그리지 않으므로 track 이
    같은 노드다. 손수 끊지 않으면 리스너가 겹쳐 붙어 휠 한 칸이 두 칸·세 칸으로 움직이고,
    죽은 인스턴스의 `MutationObserver` 가 남아 스크롤을 자기 오프셋으로 되돌린다.

    `initial_offset_px` 가 들어오기 전에는 `data` 가 고정이라 이 경로가 돌지 않았다 —
    조회기간·과거 구간에 따라 변하는 값이 생기면서 처음 살아난 길이다.
    """
    from capa_simulation.components.horizontal_scrollbar import _SCROLLBAR_JS

    # 다시 실행되면 앞 인스턴스를 먼저 끊는다.
    assert (
        "if (typeof track.__capaScrollbarTeardown === 'function') track.__capaScrollbarTeardown()"
        in _SCROLLBAR_JS
    )
    # 다음 실행이 찾을 수 있도록 track 에 걸어 두고, unmount 경로를 위해 돌려주기도 한다.
    assert "track.__capaScrollbarTeardown = teardown" in _SCROLLBAR_JS
    assert "return teardown" in _SCROLLBAR_JS
    # 떼어 낸 요소를 겨냥하던 예약은 버린다. 남으면 다음에 붙는 요소가 물려받는다.
    assert _SCROLLBAR_JS.count("pendingInitialOffset = false") >= 2


def _stub_component(monkeypatch: Any, sent: list[dict[str, Any]]) -> None:
    import capa_simulation.components.horizontal_scrollbar as bar

    monkeypatch.setattr(
        bar,
        "_HORIZONTAL_SCROLLBAR",
        lambda **kwargs: sent.append(kwargs["data"]),
    )


# ------------------------------------------------------- Top5 축 위쪽 여유


def _lob_frames() -> dict[str, pd.DataFrame]:
    months = [202608]
    labels = ["26.08"]
    return {
        "monthly_density": pd.DataFrame({"생산계획년월": months, "년월": labels, "부하량": [1.5]}),
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "부하량": [1.5],
                "Wafer 부하량": [12_000.0],
                "Wafer Capa": [11_000.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "공정": ["SAW"],
                "확보율": [0.82],
                "B/N Capa": [1.2],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "순위": [1],
                "공정": ["SAW"],
                "확보율": [3.0],
                "Wafer Capa": [11_000.0],
                "B/N Capa": [4.5],
            }
        ),
    }


def _top5_axis_range(figure: Any) -> tuple[float, float]:
    """Top5 는 세 번째 행이지만 첫 행이 표라 축은 두 번째다."""
    return tuple(figure.layout.yaxis2.range)


def _top5_peak(figure: Any) -> float:
    bars = next(trace for trace in figure.data if trace.name == "B/N Capa Top 5")
    return max(float(value) for value in bars.y)


def test_the_axis_leaves_only_the_label_its_pixels() -> None:
    """봉우리 위에 남는 자리가 라벨이 먹는 픽셀과 같아야 한다.

    예전의 `봉우리 × 1.8` 은 위쪽 44% 를 늘 비웠다. 확보율 구간을 잘라 여러 달이 같은
    높이에 서면 그 띠가 그대로 눈에 띈다.
    """
    _, month_figure = build_lob_summary_figures(
        **_lob_frames(),
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
    )
    low, high = _top5_axis_range(month_figure)
    peak = _top5_peak(month_figure)

    assert low == 0
    leftover_px = (high - peak) / high * LOB_TOP5_HEIGHT_PX
    # 이 프레임의 라벨은 `300%` 네 글자다.
    assert leftover_px == pytest.approx(top5_axis_headroom_px(4), abs=0.5)


def test_a_longer_label_reserves_more_room() -> None:
    """라벨은 밴드로 자르기 전의 원 확보율이라 글자 수에 상한이 없다.

    네 글자를 가정하고 고정값을 쓰면 `1250%` 가 뜨는 순간 라벨이 행 밖으로 나가 위
    구획을 침범한다.
    """
    frames = _lob_frames()
    frames["monthly_top5"] = frames["monthly_top5"].assign(확보율=[12.5])

    _, month_figure = build_lob_summary_figures(
        **frames,
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
    )
    _, high = _top5_axis_range(month_figure)
    peak = _top5_peak(month_figure)

    leftover_px = (high - peak) / high * LOB_TOP5_HEIGHT_PX
    # `1250%` 는 다섯 글자다.
    assert leftover_px == pytest.approx(top5_axis_headroom_px(5), abs=0.5)
    assert top5_axis_headroom_px(5) - top5_axis_headroom_px(4) == pytest.approx(
        TOP5_RATE_LABEL_CHAR_PX
    )


def test_a_short_label_never_shrinks_below_the_floor() -> None:
    """`0%` 두 글자만 있는 달에서 여유를 더 줄이면 옆 달의 긴 라벨과 기준이 갈린다."""
    assert top5_axis_headroom_px(1) == top5_axis_headroom_px(4)


def test_the_bars_grew_against_the_old_ratio() -> None:
    """같은 봉우리에서 막대가 더 높아야 한다. 예전 축은 봉우리의 1.8 배였다."""
    _, month_figure = build_lob_summary_figures(
        **_lob_frames(),
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
    )
    _, high = _top5_axis_range(month_figure)
    peak = _top5_peak(month_figure)

    assert peak / high > 1 / 1.8


def test_the_label_gap_comes_from_the_same_constant() -> None:
    """여유를 계산한 값과 라벨을 띄운 값이 갈라지면 라벨이 비워 둔 자리 밖으로 나간다."""
    _, month_figure = build_lob_summary_figures(
        **_lob_frames(),
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
    )
    rate_labels = [
        annotation
        for annotation in month_figure.layout.annotations
        if annotation.textangle == -90 and str(annotation.text).endswith("%</b>")
    ]

    assert rate_labels
    assert all(annotation.yshift == TOP5_RATE_LABEL_GAP_PX for annotation in rate_labels)
