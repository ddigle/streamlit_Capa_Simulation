# Purpose: 제약 시뮬레이션 그래프·계산표 그림과 고른 달 계산 글·개조 일정 줄·요약 넷 글을
# 손계산 하네스로 본다.

"""제약 시뮬레이션 그림(`components/constraint_simulation_figures.py`)과 순수
글(`constraint_simulation_view`).

하네스는 서비스 시험과 같은 승인 초안의 합성 예시(`tests/test_constraint_simulation.py` 의 `_run`)다
— 업무 사실이 아니다. 기간 202706~202712 · 제약 120% · 기준 110% · 개조 30일 · Cut-off 7.

- 그래프: 선 넷(비중 토글 끄면 셋)·기준선(달마다 다르면 `hv` 계단)·개조 막대 다섯(W/D 비례 — 202706
  몫은 202705 칸 안)·표적 `customdata` = 달·`layout.meta` 세대·`HIT_TARGET`·모든 trace `unselected`
  불투명 1·오른쪽 끝 두 글이 가까우면 비켜 서로 덮지 않음.
- 계산표: 행 차례·기간 밖 제약 칸 빈칸·미달 칸 글자색·고른 달 열 테두리.
- 고른 달 계산 다섯 줄(202705·202706·202801)·개조 일정 줄·모자란 달 줄.
- 요약 넷의 값·회색 줄(`render_constraint_kpis` — 지표 카드 그리기를 바꿔 끼워 글만 받는다).
- 정규형 spec — 검증을 켠 길과 끈 길의 Figure JSON 이 같다(`tests/test_plotly_fast_path.py` 규칙).
"""

from __future__ import annotations

import json
import re
from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from typing import Any

import plotly.io as pio
import pytest
from test_constraint_simulation import CONDITIONS, _run

from capa_simulation.components import constraint_simulation_figures as figures
from capa_simulation.components import constraint_simulation_view as view_module
from capa_simulation.components.constraint_simulation_figures import (
    END_LABEL_MIN_PLOT_PX,
    ROW_IDS,
    ConstraintLabels,
    build_sheet_canvas,
    chart_point_month,
    day_position,
    end_label_anchors,
    general_label,
    rate_figure,
    rate_text,
    signed_points,
    units_text,
)
from capa_simulation.components.constraint_simulation_view import (
    LATE_SUFFIX,
    default_month,
    month_steps,
    overdrawn_lines,
    render_constraint_kpis,
    schedule_lines,
    short_lines,
)
from capa_simulation.components.month_sheet_canvas import CUSTOMDATA_MONTH, CUSTOMDATA_ROW
from capa_simulation.components.plotly_layout import plotly_validation
from capa_simulation.design import tokens
from capa_simulation.services.constraint_simulation import (
    ConstraintMonthInput,
    ConstraintResult,
    simulate_constraint,
)

LABELS = ConstraintLabels(
    process="TC Bonding",
    process_label="TC Bonding",
    product="HBM라E",
    target_percent=120,
    general_percent=None,
)
LINE_NAMES = {
    "제약 없을 때(공정 전체)",
    "기존 제품 — 비중대로 나눴을 때",
    "제약 제품",
    "기존 제품 — 제약 반영",
}


def _spec(figure: Any) -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(pio.to_json(figure, validate=False))
    return spec


def _traces(figure: Any, name: str) -> list[dict[str, Any]]:
    return [trace for trace in _spec(figure)["data"] if trace.get("name") == name]


# ------------------------------------------------------------------ 서식


def test_unit_and_rate_texts_follow_the_mock_rounding() -> None:
    assert units_text(5.806451) == "5.81"
    assert units_text(42.0) == "42"
    assert units_text(41.999) == "42"
    assert units_text(-1.5) == "−1.50"
    assert units_text(None) == "—"
    assert rate_text(1.00460829) == "100.5%"
    assert rate_text(None) == "—"
    assert signed_points(-0.13826) == "−13.8%p"
    assert signed_points(0.012) == "+1.2%p"


@pytest.mark.parametrize(
    ("available", "words"), [(4.0, "가용 4를 "), (3.35, "가용 3.35를 "), (4.53, "가용 4.53을 ")]
)
def test_the_proportional_hover_picks_the_object_particle_by_the_number(
    available: float, words: str
) -> None:
    """비중 칸 풍선의 목적격 조사는 가용 수의 끝소리로 고른다 — 「가용 4 을」 이 아니다."""
    row = next(row for row in _run().months if row.in_period)
    hover = figures._proportional_cell(replace(row, available=available)).hover
    assert words in hover


def test_the_general_label_names_home_and_monthly_exceptions() -> None:
    result = _run()
    assert general_label(LABELS, result) == "HOME 110%"
    assert general_label(replace(LABELS, general_percent=105.0), result) == "105%"
    monthly = _run(general_by_month={202706: 1.05})
    assert general_label(LABELS, monthly) == "HOME(월별)"


# ------------------------------------------------------------------ 그래프


def test_the_rate_figure_draws_four_lines_and_three_without_the_proportional_toggle() -> None:
    result = _run()
    shown = {
        trace.get("name")
        for trace in _spec(
            rate_figure(result, LABELS, selected_month=202705, show_proportional=True)
        )["data"]
    }
    assert LINE_NAMES <= shown
    hidden = {
        trace.get("name")
        for trace in _spec(
            rate_figure(result, LABELS, selected_month=202705, show_proportional=False)
        )["data"]
    }
    assert LINE_NAMES - hidden == {"기존 제품 — 비중대로 나눴을 때"}


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_end_labels_use_text_colours_and_the_constrained_points_get_an_outline(
    mode: str,
) -> None:
    """주의 색(`STATUS_WARNING`)은 글자를 얹는 면색이다 — 오른쪽 끝 「제약 n%」 글을 그 색으로 쓰면
    두 테마 모두 작은 글자 대비(4.5:1)에 못 미쳤다(밝은 2.3:1 · 어두운 3.0:1). 글은 본문색이고, 제약
    제품 점은 `LINE` 테두리로 그림 요소 대비(3:1)를 넘는다."""
    from test_design_tokens import contrast_ratio

    from capa_simulation.design import theme

    theme._LOCAL.mode = mode
    try:
        palette = tokens._PALETTES[mode]
        spec = _spec(rate_figure(_run(), LABELS, selected_month=202705, show_proportional=True))
        labels = {item["text"]: item["font"]["color"] for item in spec["layout"]["annotations"]}
        assert labels["제약 120%"] == palette["TEXT"]
        assert palette["STATUS_WARNING"] not in labels.values()
        for color in labels.values():
            assert contrast_ratio(color, palette["SURFACE"]) >= 4.5
        (constrained,) = _traces(
            rate_figure(_run(), LABELS, selected_month=202705, show_proportional=True), "제약 제품"
        )
        outline = constrained["marker"]["line"]
        assert outline["color"] == palette["LINE"] and outline["width"] >= 1
        assert contrast_ratio(palette["LINE"], palette["SURFACE"]) >= 3
    finally:
        theme._LOCAL.mode = "light"


# 오른쪽 끝 글 한 줄 높이(px) — 사본 앱에서 15~16px 였다(2026-10-25 E2E).
_END_LABEL_PX = 16


def _end_label_boxes(
    y_values: dict[str, tuple[float, str]], *, low: float, high: float, plot_px: float
) -> dict[str, tuple[float, float]]:
    """끝 글마다 (위, 아래) 화면 px — 그림 칸 높이 `plot_px`, 위가 0."""
    boxes: dict[str, tuple[float, float]] = {}
    for name, (value, anchor) in y_values.items():
        line = (high - value) / (high - low) * plot_px
        top = {"middle": line - _END_LABEL_PX / 2, "bottom": line - _END_LABEL_PX, "top": line}[
            anchor
        ]
        boxes[name] = (top, top + _END_LABEL_PX)
    return boxes


def _covers(boxes: dict[str, tuple[float, float]]) -> float:
    (top_a, bottom_a), (top_b, bottom_b) = boxes.values()
    return max(0.0, min(bottom_a, bottom_b) - max(top_a, top_b))


@pytest.mark.parametrize(
    ("general", "target", "low", "high"),
    [
        (109.5, 120.0, -10.0, 200.0),  # 사본 앱 Die Attach 기본 — 세로 7px 겹침
        (110.00000000000001, 110.0, 60.0, 4040.0),  # DAF Attach 110 · 110 — 한 자리
        (110.0, 120.0, 60.0, 4040.0),  # DAF Attach 기본 — 0.5px 차이
        (120.0, 110.0, 90.0, 140.0),
        (110.0, 120.0, 90.0, 140.0),  # 손계산 하네스 — 멀어 가운데 그대로
        (100.0, 300.0, 0.0, 310.0),
    ],
)
@pytest.mark.parametrize("plot_px", [END_LABEL_MIN_PLOT_PX, 130, 160, 221, 400])
def test_the_end_labels_never_cover_each_other(
    general: float, target: float, low: float, high: float, plot_px: int
) -> None:
    """오른쪽 끝 「기준 …」 · 「제약 n%」 는 같은 x 에 선다 — 두 선이 가까우면 서로 덮었다(사본
    앱 1440px Die Attach 7px, DAF Attach 는 기준 글이 통째로 숨음, 110 · 110 은 한 글로만 보임 —
    2026-10-25 E2E). 그림 칸이 `END_LABEL_MIN_PLOT_PX` 이상이면 어떤 두 값에서도 덮지 않는다."""
    general_anchor, target_anchor = end_label_anchors(general, target, low=low, high=high)
    boxes = _end_label_boxes(
        {"기준": (general, general_anchor), "제약": (target, target_anchor)},
        low=low,
        high=high,
        plot_px=plot_px,
    )
    assert _covers(boxes) == 0


def test_far_end_labels_stay_centred_on_their_lines_and_a_tie_puts_the_target_on_top() -> None:
    assert end_label_anchors(110.0, 120.0, low=90.0, high=140.0) == ("middle", "middle")
    assert end_label_anchors(100.0, 300.0, low=0.0, high=310.0) == ("middle", "middle")
    # 가까우면 큰 값이 선 위(bottom), 작은 값이 선 아래(top). 같으면 「제약」 이 위다.
    assert end_label_anchors(109.5, 120.0, low=-10.0, high=200.0) == ("top", "bottom")
    assert end_label_anchors(120.0, 110.0, low=60.0, high=4040.0) == ("bottom", "top")
    assert end_label_anchors(110.00000000000001, 110.0, low=60.0, high=4040.0) == (
        "top",
        "bottom",
    )


def test_the_rate_figure_moves_close_end_labels_apart() -> None:
    """같은 값(제약 110% · 기준 110%)의 두 끝 글이 한 자리에 포개지던 그림 — 「제약」 은 선 위,
    「기준」 은 선 아래에 선다. 먼 값(손계산 하네스 제약 120% · 기준 110%)은 둘 다 선 가운데
    그대로다."""

    def anchors(labels: ConstraintLabels) -> dict[str, tuple[float, str]]:
        spec = _spec(rate_figure(_run(), labels, selected_month=None, show_proportional=True))
        return {
            item["text"].split()[0]: (item["y"], item["yanchor"])
            for item in spec["layout"]["annotations"]
        }

    tie = anchors(replace(LABELS, target_percent=110))
    assert tie["제약"][1] == "bottom" and tie["기준"][1] == "top"
    assert tie["제약"][0] == pytest.approx(tie["기준"][0])
    far = anchors(LABELS)
    assert far["제약"] == (120.0, "middle") and far["기준"][1] == "middle"


def test_the_constrained_and_proportional_lines_stay_inside_the_period() -> None:
    result = _run()
    figure = rate_figure(result, LABELS, selected_month=None, show_proportional=True)
    months = [row.month for row in result.months]
    constrained = _traces(figure, "제약 제품")[0]["y"]
    proportional = _traces(figure, "기존 제품 — 비중대로 나눴을 때")[0]["y"]
    for index, month in enumerate(months):
        inside = 202706 <= month <= 202712
        assert (constrained[index] is not None) == inside, month
        assert (proportional[index] is not None) == inside, month
    # 202706 제약 6/5 = 120%, 기존 40/38 = 105.26%(손계산 표).
    existing = _traces(figure, "기존 제품 — 제약 반영")[0]
    assert constrained[months.index(202706)] == pytest.approx(120.0)
    assert existing["y"][months.index(202706)] == pytest.approx(105.263, abs=1e-3)
    # 기준 미달 점은 부족색, 지킨 점은 강조색.
    colors = existing["marker"]["color"]
    assert colors[months.index(202705)] == tokens.STATUS_SHORTAGE
    assert colors[months.index(202704)] == tokens.ACCENT


def test_the_general_line_is_flat_or_a_step_when_months_differ() -> None:
    flat = rate_figure(_run(), LABELS, selected_month=None, show_proportional=False)
    line = _traces(flat, "기준")[0]
    assert line["line"]["shape"] == "linear"
    assert line["y"] == pytest.approx([110.0, 110.0])

    monthly = _run(general_by_month={202706: 1.05})
    step = _traces(
        rate_figure(monthly, LABELS, selected_month=None, show_proportional=False), "기준"
    )[0]
    assert step["line"]["shape"] == "hv"
    months = [row.month for row in monthly.months]
    assert step["y"][months.index(202706)] == pytest.approx(105.0)
    assert len(step["x"]) == len(months) + 1


def test_the_downtime_bars_follow_the_wd_window_of_each_month() -> None:
    """창 다섯 — 202706 몫 6대(4/25~5/24)는 202705 칸(W/D 4/24~5/24, 31일) 안, 끝은 202706 칸 왼쪽
    끝."""
    result = _run()
    figure = rate_figure(result, LABELS, selected_month=None, show_proportional=False)
    bars = _traces(figure, "개조 비가동")
    assert len(bars) == 1
    bar = bars[0]
    assert bar["orientation"] == "h"
    assert bar["yaxis"] == "y2"
    assert bar["text"] == ["6대", "2대", "1대", "1대", "1대"]
    months = [row.month for row in result.months]
    may = months.index(202705)
    assert bar["base"][0] == pytest.approx(may - 0.5 + 1 / 31)
    assert bar["base"][0] + bar["x"][0] == pytest.approx(may + 0.5)
    assert bar["x"][0] == pytest.approx(30 / 31)
    # 202707 몫 2대는 202706 W/D(5/25~6/23, 30일) 를 통째로 덮는다.
    june = months.index(202706)
    assert bar["base"][1] == pytest.approx(june - 0.5)
    assert bar["x"][1] == pytest.approx(1.0)
    # 겹치지 않으니 한 줄이다. 막대를 누르면 비가동이 든 첫 달을 고른다.
    assert bar["y"] == [0, 0, 0, 0, 0]
    assert [item[0] for item in bar["customdata"]] == [202705, 202706, 202707, 202708, 202710]


def test_overlapping_windows_drop_to_a_second_lane() -> None:
    """45일 개조면 202706 몫(4/17~5/31)과 202707 몫(5/17~6/30)이 겹쳐 둘째 줄로 내려간다."""
    result = _run(replace(CONDITIONS, modification_days=45, cutoff_days=0))
    bar = _traces(
        rate_figure(result, LABELS, selected_month=None, show_proportional=False), "개조 비가동"
    )[0]
    assert bar["y"][0] == 0
    assert bar["y"][1] == 1


def test_the_day_position_clips_before_the_first_month() -> None:
    months = [202701, 202702]
    assert day_position(date(2026, 11, 25), months, 7) == pytest.approx(-0.5)
    assert day_position(date(2027, 3, 30), months, 7) == pytest.approx(1.5)


def test_the_hit_targets_carry_each_month_and_keep_every_trace_opaque() -> None:
    result = _run()
    figure = rate_figure(
        result, LABELS, selected_month=202705, show_proportional=True, generation=7
    )
    spec = _spec(figure)
    hit = spec["data"][0]
    assert hit["type"] == "bar"
    assert hit["marker"]["color"] == tokens.HIT_TARGET
    assert [item[0] for item in hit["customdata"]] == [row.month for row in result.months]
    assert spec["layout"]["meta"] == {"generation": 7}
    for trace in spec["data"]:
        assert trace["unselected"]["marker"]["opacity"] == 1, trace.get("name")
    # 고른 달 띠와 제약 기간 칠 — 도형 둘(새 색 토큰 없이 opacity).
    rects = [shape for shape in spec["layout"]["shapes"] if shape["type"] == "rect"]
    assert len(rects) == 2
    months = [row.month for row in result.months]
    assert rects[0]["x0"] == pytest.approx(months.index(202706) - 0.5)
    assert rects[0]["x1"] == pytest.approx(months.index(202712) + 0.5)
    assert rects[1]["x0"] == pytest.approx(months.index(202705) - 0.5)


def test_the_chart_point_reads_the_month_of_the_clicked_target() -> None:
    state = {"selection": {"points": [{"customdata": [202706, "풍선"]}]}}
    assert chart_point_month(state) == 202706
    assert chart_point_month({"selection": {"points": []}}) is None
    assert chart_point_month(None) is None
    assert chart_point_month({"selection": {"points": [{"customdata": "글"}]}}) is None


def test_the_figures_keep_the_plotly_canonical_spec() -> None:
    """검증을 건너뛰는 길과 전부 검증하는 길이 같은 Figure JSON 을 낸다."""
    result = _run()
    fast_chart = rate_figure(result, LABELS, selected_month=202705, show_proportional=True)
    fast_sheet = build_sheet_canvas(result, LABELS, selected_month=202705, show_proportional=True)
    with plotly_validation():
        slow_chart = rate_figure(result, LABELS, selected_month=202705, show_proportional=True)
        slow_sheet = build_sheet_canvas(
            result, LABELS, selected_month=202705, show_proportional=True
        )
    assert _spec(fast_chart) == _spec(slow_chart)
    assert _spec(fast_sheet.months) == _spec(slow_sheet.months)
    assert _spec(fast_sheet.labels) == _spec(slow_sheet.labels)


# ------------------------------------------------------------------ 계산표


def _cells(canvas: Any, row_id: str) -> dict[int, str]:
    """월 Figure 의 표적 칸에서 그 행의 (달 → 풍선) — 칸이 있는 달만."""
    found: dict[int, str] = {}
    for trace in _spec(canvas.months)["data"]:
        for item in trace.get("customdata") or []:
            if (
                isinstance(item, list)
                and len(item) > CUSTOMDATA_ROW
                and item[CUSTOMDATA_ROW] == row_id
            ):
                found[int(item[CUSTOMDATA_MONTH])] = str(item[2] if len(item) > 2 else "")
    return found


def _texts(canvas: Any) -> list[tuple[str, str]]:
    """(글자색, 글) 모두 — 글자 trace 는 (색, 크기)마다 하나다."""
    pairs: list[tuple[str, str]] = []
    for trace in _spec(canvas.months)["data"]:
        if trace.get("mode") == "text":
            color = trace["textfont"]["color"]
            pairs += [(color, text) for text in trace["text"]]
    return pairs


def test_the_sheet_rows_follow_the_mock_order() -> None:
    result = _run()
    canvas = build_sheet_canvas(result, LABELS, selected_month=202705, show_proportional=True)
    assert canvas.row_ids == ROW_IDS
    off = build_sheet_canvas(
        _run(replace(CONDITIONS, modification_days=None)),
        LABELS,
        selected_month=None,
        show_proportional=False,
    )
    assert "title:modification" not in off.row_ids
    assert "increment" not in off.row_ids
    assert "proportional_rate" not in off.row_ids
    assert canvas.labels.layout.height == canvas.months.layout.height == canvas.height


def test_the_sheet_leaves_constraint_cells_blank_outside_the_period() -> None:
    result = _run()
    canvas = build_sheet_canvas(result, LABELS, selected_month=None, show_proportional=False)
    need = _cells(canvas, "need")
    # 칸은 누를 수 있게 늘 선다(풍선 없는 칸은 표적 trace 를 따로 둔다).
    assert set(need) == {row.month for row in result.months}
    assert "5 × 120% = 6.00 → 6대" in need[202706]
    assert "제약 기간 밖" in need[202801]
    demand = _cells(canvas, "constrained_demand")
    assert "원 소요 10대는 기존 제품에 셉니다" in demand[202801]
    downtime = _cells(canvas, "downtime")
    assert "27년 6월 몫 6대 × 30/31일 = 5.81" in downtime[202705]


def _fills(canvas: Any) -> list[str]:
    """칸 면 막대의 색들(칸마다 한 값)."""
    for trace in _spec(canvas.months)["data"]:
        marker = trace.get("marker", {})
        if trace.get("type") == "bar" and isinstance(marker.get("color"), list):
            colors: list[str] = marker["color"]
            return colors
    return []


def test_the_sheet_fills_shortfall_cells_and_marks_decreases() -> None:
    """미달 칸은 부족색 면(공정 Capa 상세 ① 과 같은 꼴 — 두 테마에서 글자가 읽힌다), 줄어든 값은
    감소색 글자다. 기존 미달 다섯 달 · 제약 없을 때 미달 0 · 제약 미충족 0 이라 부족색 면은 다섯
    칸이다."""
    result = _run()
    canvas = build_sheet_canvas(result, LABELS, selected_month=None, show_proportional=False)
    assert _fills(canvas).count(tokens.STATUS_SHORTAGE) == len(result.kpis.below_months) == 5
    decreases = [text for color, text in _texts(canvas) if color == tokens.DELTA_DECREASE]
    assert "−5.81" in decreases
    assert "−13.8%p" in decreases


def test_the_sheet_outlines_the_selected_month_and_tints_the_period_head() -> None:
    result = _run()
    canvas = build_sheet_canvas(
        result, LABELS, selected_month=202705, show_proportional=False, generation=3
    )
    spec = _spec(canvas.months)
    assert spec["layout"]["meta"] == {"generation": 3}
    months = [row.month for row in result.months]
    outline = [
        shape
        for shape in spec["layout"]["shapes"]
        if shape.get("line", {}).get("color") == tokens.ACCENT
    ]
    assert len(outline) == 1
    assert outline[0]["x0"] == pytest.approx(months.index(202705), abs=0.02)
    tinted = [
        shape
        for shape in spec["layout"]["shapes"]
        if shape.get("fillcolor") == tokens.STATUS_WARNING
    ]
    assert len(tinted) == 7
    for trace in spec["data"]:
        assert trace["unselected"]["marker"]["opacity"] == 1


# ------------------------------------------------------------------ 고른 달 계산·개조 일정


def test_the_default_month_is_the_first_impact_month() -> None:
    assert default_month(_run()) == 202705
    no_impact = _run(replace(CONDITIONS, period_start=202901, period_end=202903))
    assert default_month(no_impact) == 202701


def test_the_month_steps_walk_through_the_five_calculations() -> None:
    result = _run()
    may = month_steps(result.month(202705), result, LABELS, show_proportional=True)
    assert may.title == "27.05 · TC Bonding"
    assert [step.body for step in may.steps] == [
        "소요 **42대** = 기존 42 + HBM라E 0",
        "제약 제품에 따로 떼는 대수 없음",
        "개조 중 비가동 **−5.81대**",
        "기존 가용 = 48 − 5.81 = **42.19대**",
        "기존 확보율 = 42.19 ÷ 42 = **100.5%**",
    ]
    assert may.steps[0].note == "제약 기간 밖이라 HBM라E 도 기존 제품에 함께 셉니다."
    assert may.steps[2].note == "27년 6월 몫 6대가 이 달 30일 개조 중 → 5.81대"
    assert may.steps[3].note == "공정 가용 − 개조 중"
    assert may.steps[4].note == "제약 없을 때 114.3% · −13.8%p"
    assert may.verdict == "기존 제품이 기준 110% 에 못 미칩니다"
    assert may.verdict_secure is False
    assert may.proportional == ""

    june = month_steps(result.month(202706), result, LABELS, show_proportional=True)
    assert june.title == "27.06 · TC Bonding · 제약 기간"
    assert june.steps[0].body == "소요 **43대** = 기존 38 + HBM라E 5"
    assert june.steps[1].body == "HBM라E 필요 대수 = 5 × 120% = 6.00 → **6대**"
    assert june.steps[2].note == "27년 7월 몫 2대가 이 달 30일 개조 중 → 2대"
    assert june.steps[3].body == "기존 가용 = 48 − 2 − 6 = **40대**"
    assert june.steps[4].body == "기존 확보율 = 40 ÷ 38 = **105.3%**"
    assert june.verdict == (
        "기존 제품이 기준 110% 에 못 미칩니다 · 제약 제품 120.0% (제약 120% 충족)"
    )
    assert june.proportional.startswith("비중대로만 나눴다면: 제약 6대(120.0%) · 기존 42대(110.5%)")

    after = month_steps(result.month(202801), result, LABELS, show_proportional=True)
    assert after.steps[0].body == "소요 **48대** = 기존 48 + HBM라E 0"
    assert after.steps[2].body == "이 달 개조 비가동 없음"
    assert after.steps[3].body == "기존 가용 = 공정 가용 **54대**"
    assert after.steps[4].body == "기존 확보율 = 54 ÷ 48 = **112.5%**"
    assert after.verdict == "기존 제품이 기준 110%를 지킵니다"
    assert after.verdict_secure is True


def _written_numbers(text: str) -> list[float]:
    return [float(number.replace(",", "")) for number in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


@pytest.mark.parametrize("demand", [0.0215, 1.5703, 0.0549, 5.0, 2.345])
def test_the_need_step_recomputes_from_the_written_numbers(demand: float) -> None:
    """2단계 「소요 × 제약 % = 곱」 은 적힌 소요로 다시 셈해도 적힌 곱이 나온다.

    소요를 둘째 자리로 깎아 적고 곱은 원값으로 내면 「0.02 × 120% = 0.03」 처럼 어긋났다. 그때만
    소요를 한 자리씩 더 적는다(맞으면 둘째 자리 그대로 — 「5 × 120% = 6.00」).
    """
    result = _run()
    row = replace(result.month(202706), constrained_demand=demand)
    body = month_steps(row, result, LABELS, show_proportional=False).steps[1].body
    written_demand, target, written_product = _written_numbers(body.split("→")[0].split("=", 1)[1])
    assert target == 120
    assert f"{written_demand * target / 100:.2f}" == f"{written_product:.2f}"
    assert f"{demand * target / 100:.2f}" == f"{written_product:.2f}"


@pytest.mark.parametrize(
    ("available", "demand"), [(2.0, 1.9375), (40.0, 38.0), (42.1935, 42.0), (3.3349, 2.8751)]
)
def test_the_existing_rate_step_recomputes_from_the_written_numbers(
    available: float, demand: float
) -> None:
    """5단계 「가용 ÷ 소요 = 확보율」 도 적힌 수로 다시 셈하면 적힌 확보율이다(「2 ÷ 1.94 = 103.2%」
    가 아니다 — 적힌 수로는 103.1%)."""
    result = _run()
    row = replace(
        result.month(202706),
        existing_available=available,
        existing_demand=demand,
        existing_rate=available / demand,
    )
    body = month_steps(row, result, LABELS, show_proportional=False).steps[4].body
    written_available, written_demand, written_rate = _written_numbers(body.split("=", 1)[1])
    assert f"{written_available / written_demand * 100:.1f}" == f"{written_rate:.1f}"
    assert f"{available / demand * 100:.1f}" == f"{written_rate:.1f}"


@pytest.mark.parametrize(
    ("existing", "constrained"),
    [(141.2649, 1.3649), (38.0, 5.0), (41.996, 0.0), (2.0041, 0.0049), (12.3333, 4.6667)],
)
def test_the_demand_split_step_recomputes_from_the_written_numbers(
    existing: float, constrained: float
) -> None:
    """1단계 「소요 = 기존 + 제약」 도 적힌 두 수를 더하면 적힌 소요다 — 「142.63 = 141.26 + 1.36」
    이 아니다(적힌 수의 합은 142.62, 2026-10-26 E2E). 회색 줄은 「합하면 원래 소요와 같습니다」."""
    result = _run()
    row = replace(
        result.month(202706),
        required=existing + constrained,
        existing_demand=existing,
        constrained_demand=constrained,
    )
    step = month_steps(row, result, LABELS, show_proportional=False).steps[0]
    assert "≈" not in step.body
    written_required, written_existing, written_constrained = _written_numbers(step.body)
    assert units_text(written_existing + written_constrained) == units_text(written_required)
    assert units_text(existing + constrained) == units_text(written_required)
    assert step.note == "제약 기간이라 공정 소요를 두 갈래로 나눕니다(합하면 원래 소요와 같습니다)."


@pytest.mark.parametrize(
    ("available", "downtime", "allocated"),
    [(3.3549, 0.9651, 0), (48.004, 2.006, 6), (48.0, 2.0, 6), (40.0, 0.0, 7), (5.0, 5.806, 0)],
)
def test_the_existing_available_step_recomputes_from_the_written_numbers(
    available: float, downtime: float, allocated: int
) -> None:
    """4단계 「공정 가용 − 개조 중 − 제약 배정 = 기존 가용」 도 적힌 수로 다시 셈하면 적힌 기존
    가용이다 — 「3.35 − 0.97 = 2.39」 가 아니다(적힌 수로는 2.38, 2026-10-26 E2E). 비가동이 가용보다
    많으면 쓸 수 있는 가용을 0 으로 두는 것까지 같은 셈이다."""
    result = _run()
    usable = max(0.0, available - downtime)
    row = replace(
        result.month(202706),
        available=available,
        downtime=downtime,
        usable=usable,
        overdrawn=available - downtime < 0,
        allocated=allocated,
        existing_available=usable - allocated,
    )
    body = month_steps(row, result, LABELS, show_proportional=False).steps[3].body
    assert "≈" not in body
    *operands, written_available = _written_numbers(body)
    written_usable = max(0.0, operands[0] - (operands[1] if downtime > 0 else 0.0))
    written_allocated = operands[-1] if allocated > 0 else 0
    assert units_text(written_usable - written_allocated) == units_text(written_available)
    assert units_text(usable - allocated) == units_text(written_available)


def test_a_step_that_no_digits_can_match_says_approximately() -> None:
    """어느 자릿수 후보로도 적힌 결과가 안 나오면 둘째 자리로 적고 등호를 「≈」 로 둔다(AGENTS
    「화면 숫자는 검산되어야 한다」) — 여섯째 자리까지 늘린 「=」 가 아니다."""
    result = _run()
    row = replace(
        result.month(202706),
        required=100.0,
        existing_demand=90.123456789,
        constrained_demand=4.0,
    )
    body = month_steps(row, result, LABELS, show_proportional=False).steps[0].body
    assert body == "소요 **100대** ≈ 기존 90.12 + HBM라E 4"


def test_a_dedicated_pool_above_need_says_it_stays() -> None:
    """누적 최대 — 202710 소요가 8 → 7 로 줄어도 전용 10대가 남는다(합성 한 줄)."""
    product = (0, 0, 0, 0, 0, 5, 6, 7, 8, 7, 9, 9, 10, 10, 11)
    result = _run(product=product)
    october = month_steps(result.month(202710), result, LABELS, show_proportional=False)
    assert october.steps[1].note == "이미 개조한 10대는 전용으로 남습니다(줄여도 되돌리지 않음)."


def test_the_steps_without_modification_say_so() -> None:
    result = _run(replace(CONDITIONS, modification_days=None))
    steps = month_steps(result.month(202706), result, LABELS, show_proportional=False)
    assert steps.steps[2].body == "개조 없음 — 비가동 없이 나누기만 합니다"


def test_the_schedule_lines_mark_late_windows() -> None:
    result = _run()
    lines = schedule_lines(result.windows, today=date(2027, 5, 1))
    assert lines[0] == ("27년 6월 몫 · 2027-04-25 \\~ 2027-05-24 비가동 · **6대**" + LATE_SUFFIX)
    assert not lines[1].endswith(LATE_SUFFIX)
    assert len(lines) == 5
    assert all(
        not line.endswith(LATE_SUFFIX)
        for line in schedule_lines(result.windows, today=date(2027, 1, 1))
    )


def test_the_short_and_overdrawn_lines_name_each_month() -> None:
    """과개조 — 202705·202706, R 4·8, A 5·5, Rc 0·6, 기간 202706, 제약 100%, 30일(명세 2-8 ⑩)."""
    rows = (
        ConstraintMonthInput(202705, 4.0, 0.0, 5.0, 1.1),
        ConstraintMonthInput(202706, 8.0, 6.0, 5.0, 1.1),
    )
    result = simulate_constraint(
        rows,
        replace(CONDITIONS, period_start=202706, period_end=202706, constraint_target=1.0),
    )
    assert short_lines(result).startswith("27.06: 필요 6대 중 5대만 배정")
    assert overdrawn_lines(result) == [
        "27.05: 개조 비가동 5.81대가 가용 5대보다 많습니다 — 이 공정 설비로는 이 개조 일정이 "
        "서지 않습니다."
    ]
    assert short_lines(_run()) == ""
    may = month_steps(result.month(202705), result, LABELS, show_proportional=False)
    assert "0 으로 둡니다" in may.steps[3].note


# ------------------------------------------------------------------ 요약 넷


def _kpi_cards(
    monkeypatch: pytest.MonkeyPatch, result: ConstraintResult
) -> dict[str, tuple[str, str | None]]:
    """요약 넷을 그려 카드마다 (값, 회색 줄) 을 받는다 — Streamlit 없이(카드 그리기를 바꿔 낀다)."""
    cards: dict[str, tuple[str, str | None]] = {}

    def capture(label: str, value: str, *, caption: str | None = None, **_: object) -> None:
        cards[label] = (value, caption)

    monkeypatch.setattr(view_module, "metric_row", lambda **_: nullcontext())
    monkeypatch.setattr(view_module, "render_status_metric", capture)
    render_constraint_kpis(result, LABELS)
    return cards


def test_the_modification_kpi_says_there_is_nothing_to_modify_without_demand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """제약 기간(202703)에 제약 제품 소요가 없으면 넷째 칸은 「0대 · 0번에 나눠 개조」 가 아니라
    「개조할 대수가 없습니다」 다(2026-10-26 E2E). 값 「0대」 는 명세 2-6 「max pool 대」 그대로."""
    empty = _run(replace(CONDITIONS, period_start=202703, period_end=202703))
    assert empty.kpis.window_count == 0
    cards = _kpi_cards(monkeypatch, empty)
    assert cards["개조 대수"] == ("0대", "개조할 대수가 없습니다")
    assert cards["제약 제품 확보율 충족"] == ("—", "제약 기간에 제약 제품 소요가 없습니다")

    cards = _kpi_cards(monkeypatch, _run())
    value, caption = cards["개조 대수"]
    assert value == "11대"
    assert caption is not None and caption.startswith("5번에 나눠 개조 · 첫 비가동 ")

    off = _run(replace(CONDITIONS, modification_days=None))
    cards = _kpi_cards(monkeypatch, off)
    assert cards["개조 대수"] == ("—", "개조를 끄면 비가동 없이 배정만 바꿉니다")
