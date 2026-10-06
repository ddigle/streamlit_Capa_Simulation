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
from capa_simulation.services.securement_threshold import SecurementThresholds

THRESHOLDS = {"thresholds": SecurementThresholds(1.095, 0.995)}


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
    summary = shortage_summary(_wide_table(), dimension_columns=["공정"], **THRESHOLDS)

    assert list(summary["공정"]) == ["TEST", "MOLD", "SAW"]
    assert list(summary["최초 부족"]) == ["26.01", "26.02", "26.03"]
    assert list(summary["부족 개월"]) == [2, 2, 1]


def test_shortage_summary_skips_processes_that_never_break() -> None:
    table = pd.DataFrame({"공정": ["SAW"], "202601": [1.5]})

    assert shortage_summary(table, dimension_columns=["공정"], **THRESHOLDS).empty


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


def _months(count: int) -> list[str]:
    """2026년 1월부터 `count` 개월의 `YYYYMM` 컬럼."""
    return [f"{2026 + index // 12}{index % 12 + 1:02d}" for index in range(count)]


def test_month_axis_turns_its_labels_instead_of_letting_them_touch() -> None:
    """고정한 가로 눈금은 1280px 창·30개월에서 「26.0726.08」처럼 붙었다(2026-10-06 사용자 보고).

    칸 폭은 브라우저에서야 정해지므로 각도는 Plotly 가 재어 고른다 — 들어가면 가로, 겹치면 세운다.
    툴바가 오른쪽 위 월 눈금을 덮던 것은 툴바를 끄고 확대를 막는 것으로 걷는다.
    """
    from capa_simulation.components.securement_heatmap import MONTH_TICK_ANGLES

    months = _months(30)
    table = pd.DataFrame({"공정": ["SAW", "MOLD"], **{month: [1.0, 0.9] for month in months}})

    figure = build_securement_heatmap(table, dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    xaxis = figure.layout.xaxis
    assert xaxis.tickangle is None
    assert tuple(xaxis.autotickangles) == MONTH_TICK_ANGLES
    assert MONTH_TICK_ANGLES[0] == 0
    assert (xaxis.side, xaxis.automargin, xaxis.fixedrange) == ("top", True, True)
    assert figure.layout.yaxis.fixedrange is True
    # 30개월은 세우면 모두 들어간다 — 솎지 않는다.
    assert xaxis.tickmode is None


def test_month_axis_thins_to_calendar_steps_only_when_turned_labels_would_still_touch() -> None:
    from capa_simulation.components.securement_heatmap import MAX_MONTH_TICKS

    months = _months(72)
    table = pd.DataFrame({"공정": ["SAW"], **{month: [1.0] for month in months}})

    figure = build_securement_heatmap(table, dimension_columns=["공정"], **THRESHOLDS)

    assert figure is not None
    xaxis = figure.layout.xaxis
    assert xaxis.tickmode == "array"
    assert len(xaxis.tickvals) <= MAX_MONTH_TICKS
    # 홀수 달(1·3·5…월)만 남는다. 눈금 값은 칸 이름과 같아 hover 는 모든 달을 그대로 말한다.
    assert list(xaxis.tickvals[:3]) == ["26.01", "26.03", "26.05"]
    assert list(xaxis.ticktext) == list(xaxis.tickvals)
    assert set(xaxis.tickvals) <= set(figure.data[0].x)


def test_heatmap_hides_the_plotly_toolbar_but_keeps_hover() -> None:
    from unittest.mock import patch

    from capa_simulation.components import securement_heatmap

    with (
        patch.object(securement_heatmap, "tab_is_hidden", return_value=False),
        patch.object(securement_heatmap.st, "markdown"),
        patch.object(securement_heatmap.st, "plotly_chart") as plotly_chart,
    ):
        securement_heatmap.render_securement_heatmap(
            _table(), dimension_columns=["공정"], key="heatmap", **THRESHOLDS
        )

    config = plotly_chart.call_args.kwargs["config"]
    assert config["displayModeBar"] is False
    assert not config.get("staticPlot", False)


def test_a_month_with_its_own_threshold_is_judged_by_it() -> None:
    """월별 예외가 있는 달 열만 그 달 기준으로 칠한다.

    같은 115% 가 기본 달은 확보, 120% 기준 달은 경고다.
    """
    table = pd.DataFrame({"공정": ["SAW"], "202601": [1.15], "202602": [1.15]})
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202602, 1.195, None),))

    figure = build_securement_heatmap(table, dimension_columns=["공정"], thresholds=thresholds)

    assert figure is not None
    assert list(figure.data[0].z[0]) == [SECURE_TIER, WARNING_TIER]


def test_shortage_summary_uses_each_months_warning_threshold() -> None:
    """부족은 **그 달의** 경고 기준 미만이다. 경고 기준만 올린 달에서만 부족으로 센다."""
    table = pd.DataFrame({"공정": ["SAW"], "202601": [1.05], "202602": [1.05]})
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202602, 1.195, 1.095),))

    summary = shortage_summary(table, dimension_columns=["공정"], thresholds=thresholds)

    assert list(summary["최초 부족"]) == ["26.02"]
    assert list(summary["부족 개월"]) == [1]
