# Purpose: 확보율 히트맵의 상태 판정과 색 눈금이 화면 기준과 같은지 검증한다.

import pandas as pd

from capa_simulation.components.securement_heatmap import (
    SECURE_TIER,
    SHORTAGE_TIER,
    WARNING_TIER,
    build_securement_heatmap,
    shortage_summary,
)
from capa_simulation.design import tokens

THRESHOLDS = {"secure_threshold": 1.095, "warning_threshold": 0.995}


def _table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["SAW", "MOLD"],
            "202601": [1.2, 0.9],
            "202602": [1.0, float("nan")],
        }
    )


def test_tiers_match_the_three_status_bands() -> None:
    figure = build_securement_heatmap(_table(), dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    heatmap = figure.data[0]
    assert list(heatmap.z[0]) == [SECURE_TIER, WARNING_TIER]
    assert heatmap.z[1][0] == SHORTAGE_TIER
    # 결측은 계단이 아니라 빈 칸이다. 0 으로 접으면 「부족」으로 거짓말한다.
    assert heatmap.z[1][1] is None


def test_hover_keeps_the_uncut_rate() -> None:
    """색만 3계단으로 접는다. 숫자는 실제 확보율이어야 한다."""
    figure = build_securement_heatmap(_table(), dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    assert figure.data[0].customdata[0][0] == 120.0


def test_colorscale_has_no_blend_between_the_three_steps() -> None:
    figure = build_securement_heatmap(_table(), dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    colors = [color for _, color in figure.data[0].colorscale]
    assert colors == [
        tokens.STATUS_SHORTAGE,
        tokens.STATUS_SHORTAGE,
        tokens.STATUS_WARNING,
        tokens.STATUS_WARNING,
        tokens.STATUS_SECURE,
        tokens.STATUS_SECURE,
    ]


def test_months_are_read_top_down_like_the_table() -> None:
    figure = build_securement_heatmap(_table(), dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    assert list(figure.data[0].x) == ["26.01", "26.02"]
    assert figure.layout.yaxis.autorange == "reversed"


def test_empty_table_draws_nothing() -> None:
    assert (
        build_securement_heatmap(
            pd.DataFrame(columns=["공정"]), dimension_columns=["공정"], **THRESHOLDS
        )
        is None
    )


def _wide_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["SAW", "MOLD", "TEST"],
            "202601": [1.2, 1.2, 0.5],
            "202602": [1.2, 0.8, 0.4],
            "202603": [0.7, 0.9, 1.3],
        }
    )


def test_shortage_summary_answers_when_each_process_breaks() -> None:
    summary = shortage_summary(_wide_table(), dimension_columns=["공정"], warning_threshold=0.995)

    assert list(summary["공정"]) == ["TEST", "MOLD", "SAW"]
    assert list(summary["최초 부족"]) == ["26.01", "26.02", "26.03"]
    assert list(summary["부족 개월"]) == [2, 2, 1]


def test_shortage_summary_skips_processes_that_never_break() -> None:
    table = pd.DataFrame({"공정": ["SAW"], "202601": [1.5]})

    assert shortage_summary(table, dimension_columns=["공정"], warning_threshold=0.995).empty


def test_every_process_row_keeps_its_name_when_many_are_shown() -> None:
    """공정을 다 깔아도 **모든 행에 이름**이 붙는다.

    70공정을 900px 에 눌러 담으니 칸이 12.9px 이 되고 Plotly 자동 눈금이 이름을 하나 건너
    하나만 그려 35개 행이 이름 없이 남았다(2026-10-05 E2E). 행마다 눈금을 두고 칸이 너무
    낮아지지 않게 그래프를 늘인다.
    """
    from capa_simulation.components.securement_heatmap import (
        CHART_CHROME_PX,
        MIN_LABELLED_ROW_PX,
    )

    names = [f"P{index:02d}" for index in range(70)]
    table = pd.DataFrame({"공정": names, "202601": [1.0] * 70})

    figure = build_securement_heatmap(table, dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    yaxis = figure.layout.yaxis
    assert (yaxis.tickmode, yaxis.dtick) == ("linear", 1)
    assert (figure.layout.height - CHART_CHROME_PX) / len(names) >= MIN_LABELLED_ROW_PX
    assert yaxis.tickfont.size < MIN_LABELLED_ROW_PX
