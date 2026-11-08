# Purpose: 제약 시뮬레이션 그래프·계산표 그림과 모자란 달 줄·요약 넷 글을 손계산 하네스로 본다.

"""제약 시뮬레이션 그림(`components/constraint_simulation_figures.py`)과 순수
글(`constraint_simulation_view`).

하네스는 서비스 시험과 같은 승인 초안의 합성 예시(`tests/test_constraint_simulation.py` 의 `_run`)다
— 업무 사실이 아니다. 기간 202706~202712 · 제약 120% · 기준 110% · 개조 30일 · Cut-off 7.

- 그래프: 선 넷(비중 토글 끄면 셋)·기준선(달마다 다르면 `hv` 계단)·개조 막대 다섯(W/D 비례 — 202706
  몫은 202705 칸 안)·표적 `customdata` = 달·`layout.meta` 세대·`HIT_TARGET`·모든 trace `unselected`
  불투명 1·오른쪽 끝 두 글이 가까우면 비켜 서로 덮지 않음.
- 계산표: 행 차례·기간 밖 제약 칸 빈칸·미달 칸 글자색·고른 달 열 테두리·칸 풍선 까닭 글.
- 모자란 달 줄.
- 요약 넷의 값·회색 줄(`render_constraint_kpis` — 지표 카드 그리기를 바꿔 끼워 글만 받는다).
- 정규형 spec — 검증을 켠 길과 끈 길의 Figure JSON 이 같다(`tests/test_plotly_fast_path.py` 규칙).
"""

from __future__ import annotations

import json
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from typing import Any

import plotly.io as pio
import pytest
from test_constraint_simulation import CONDITIONS, _inputs, _run
from test_constraint_simulation_holdings import (
    JUNE_FIRST,
    LATE_HELD,
    LATE_UNIT,
    _bundle,
    _conditions,
    _held,
    _months,
    _random_case,
    _with_bundles,
)
from test_constraint_simulation_options import NEW_ON, SINCE, _unit

from capa_simulation.components import constraint_simulation_figures as figures
from capa_simulation.components import constraint_simulation_view as view_module
from capa_simulation.components.constraint_simulation_figures import (
    CONSTRAINT_FIGURE_SCHEMA_VERSION,
    END_LABEL_MIN_PLOT_PX,
    ROW_IDS,
    ConstraintLabels,
    build_sheet_canvas,
    chart_point_month,
    day_position,
    dedicated_split_text,
    end_label_anchors,
    general_label,
    rate_figure,
    rate_text,
    signed_points,
    units_text,
)
from capa_simulation.components.constraint_simulation_view import (
    SHORT_INLINE_LIMIT,
    default_month,
    overdrawn_lines,
    render_constraint_kpis,
    short_lines,
    short_month_lines,
)
from capa_simulation.components.month_sheet_canvas import CUSTOMDATA_MONTH, CUSTOMDATA_ROW, MINUS
from capa_simulation.components.plotly_layout import plotly_validation
from capa_simulation.design import tokens
from capa_simulation.services.constraint_simulation import (
    FILL_NEW,
    FILL_ORDER,
    FILL_OWNED,
    ConstraintMonthInput,
    ConstraintResult,
    NewUnit,
    secure,
    simulate_constraint,
)
from capa_simulation.services.securement_threshold import capacity_status
from capa_simulation.services.wd_window import wd_window

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
    return _traces_in(_spec(figure), name)


def _traces_in(spec: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [trace for trace in spec["data"] if trace.get("name") == name]


def _stopped(result: ConstraintResult) -> bool:
    """결정 B1 로 신규를 더 붙이지 않았고 실제로 붙지 않은 호기가 있는가 — 덮지 않았다면 붙었을
    신규가 있을 때만 참이다(그 호기의 까닭이 「보유로 덮음」 — 계산표 풍선)."""
    return result.new_units_stopped_month is not None and bool(result.held_back_units)


# ------------------------------------------------------------------ 서식


def test_unit_and_rate_texts_follow_the_mock_rounding() -> None:
    assert units_text(5.806451) == "5.81"
    assert units_text(42.0) == "42"
    assert units_text(41.999) == "42"
    assert units_text(-1.5) == "−1.50"
    assert units_text(None) == "—"
    assert rate_text(1.00460829) == "100.5%"
    assert rate_text(None) == "—"
    # 퍼센트 차이도 「%」 로 적는다 — 「%p」 를 쓰지 않는다(2026-11-01 사용자 결정).
    assert signed_points(-0.13826) == "−13.8%"
    assert signed_points(0.012) == "+1.2%"
    assert signed_points(0.0) == "0.0%"


@pytest.mark.parametrize(
    ("available", "words"), [(4.0, "가용 4를 "), (3.35, "가용 3.35를 "), (4.53, "가용 4.53을 ")]
)
def test_the_proportional_hover_picks_the_object_particle_by_the_number(
    available: float, words: str
) -> None:
    """비중 칸 풍선의 목적격 조사는 가용 수의 끝소리로 고른다 — 「가용 4 을」 이 아니다."""
    row = next(row for row in _run().months if row.in_period)
    hover = figures._proportional_cell(replace(row, available=available), {}).hover
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


def test_a_huge_constrained_rate_is_pinned_to_the_top_with_a_triangle() -> None:
    """제약 소요가 0.025대인 달의 제약 확보율 4000% 가 y 축을 4000% 까지 늘려 기존 제품 선과
    기준선이 바닥에 눌렸다(2026-10-25 E2E #13·#107). 축은 다른 선·기준으로 잡고 제약 제품 점은 그
    범위 폭만큼 위까지만 넣는다 — 넘는 점은 위 끝에 ▲(잘리지 않게 `cliponaxis` 끔)·풍선에 값과
    「▲ 그래프 위 끝 넘음」. 넘는 점이 없으면 축과 점은 예전 그대로다."""
    product = (0, 0, 0, 0, 0, 0.025, 6, 7, 8, 8, 9, 9, 10, 10, 11)
    result = _run(product=product)
    axis = figures.rate_axis(result, LABELS, show_proportional=True)
    assert axis.above_months == (202706,)
    assert axis.high <= 300
    spec = _spec(rate_figure(result, LABELS, selected_month=None, show_proportional=True))
    assert spec["layout"]["yaxis"]["range"] == [axis.low, axis.high]
    (line,) = _traces_in(spec, "제약 제품")
    index = [row.month for row in result.months].index(202706)
    assert line["y"][index] == axis.high
    assert line["marker"]["symbol"][index] == "triangle-up"
    assert line["marker"]["symbol"][index + 1] == "circle"
    assert line["cliponaxis"] is False
    hover = spec["data"][0]["customdata"][index][1]
    assert "제약 4000.0%(최소 1대) ▲ 그래프 위 끝 넘음" in hover

    plain = _run()
    assert figures.rate_axis(plain, LABELS, show_proportional=True).above_months == ()
    plain_spec = _spec(rate_figure(plain, LABELS, selected_month=None, show_proportional=True))
    every = [
        value * 100
        for row in plain.months
        for value in (
            row.baseline_rate,
            row.existing_rate,
            row.constrained_rate if row.in_period else None,
            row.proportional_existing_rate if row.in_period else None,
            row.general_target,
        )
        if value is not None
    ] + [float(LABELS.target_percent)]
    assert plain_spec["layout"]["yaxis"]["range"] == list(figures.axis_bounds(every))
    (plain_line,) = _traces_in(plain_spec, "제약 제품")
    assert set(plain_line["marker"]["symbol"]) == {"circle"}
    assert plain_line["cliponaxis"] is True


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


OPTION_ROWS = ("new_starts", "growth", "owned_increment", "new_increment", "waiting")


def test_the_sheet_rows_follow_the_mock_order() -> None:
    result = _run()
    canvas = build_sheet_canvas(result, LABELS, selected_month=202705, show_proportional=True)
    # 2판 옵션 행은 그 옵션이 걸릴 때만 선다 — 기본값이면 1판 행 그대로다.
    assert canvas.row_ids == tuple(row for row in ROW_IDS if row not in OPTION_ROWS)
    every = build_sheet_canvas(
        simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=3, new_unit_since=SINCE)),
        LABELS,
        selected_month=202705,
        show_proportional=True,
    )
    assert every.row_ids == ROW_IDS
    # 「신규 설비로」·「보유 제약 설비로」 는 채우는 차례(`FILL_ORDER` — 신규 → 보유)로 선다.
    assert every.row_ids.index("new_increment") < every.row_ids.index("owned_increment")
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
    assert "−13.8%" in decreases


def _home_labels(result: Any) -> ConstraintLabels:
    """기준이 HOME 인 화면 글자 — 달마다 경고 기준 100% 의 판정 경계."""
    return replace(LABELS, warning_targets=tuple((row.month, 0.995) for row in result.months))


def _judged_rates(result: Any) -> list[tuple[int, float]]:
    """기준 확보율에 견주는 세 줄의 (달, 확보율) — 비중대로 줄은 기간 안 달만 값이다."""
    rates = [
        (row.month, rate)
        for row in result.months
        for rate in (row.baseline_rate, row.existing_rate)
        if rate is not None
    ]
    return rates + [
        (row.month, row.proportional_existing_rate)
        for row in result.months
        if row.in_period and row.proportional_existing_rate is not None
    ]


def test_the_sheet_paints_the_three_status_colors_on_the_home_basis() -> None:
    """기준이 HOME 이면 확보율 칸이 다른 화면과 같은 세 단계 색이다(설계 규칙 UI-DAT-03) — 경고 구간
    값이 부족색으로 서지 않는다. 판정은 `capacity_status` 한 길이다."""
    result = _run()
    canvas = build_sheet_canvas(
        result, _home_labels(result), selected_month=None, show_proportional=True
    )
    statuses = [
        capacity_status(rate, secure_threshold=1.1, warning_threshold=1.0)
        for _, rate in _judged_rates(result)
    ]
    assert statuses.count("warning") >= 1, "합성 예에 경고 구간 값이 있어야 시험이 뜻이 있다"
    fills = _fills(canvas)
    assert fills.count(tokens.STATUS_WARNING) == statuses.count("warning")
    assert fills.count(tokens.STATUS_SHORTAGE) == statuses.count("shortage")
    assert fills.count(tokens.STATUS_SECURE) == statuses.count("secure")


def test_a_typed_general_target_keeps_two_steps_because_it_has_no_warning_line() -> None:
    """직접 넣은 기준에는 경고 경계가 없다 — 못 미친 칸만 부족색이고 지킨 칸은 칠하지 않는다."""
    result = _run()
    canvas = build_sheet_canvas(result, LABELS, selected_month=None, show_proportional=True)
    below = sum(
        1
        for month, rate in _judged_rates(result)
        if not secure(rate, result.month(month).general_target)
    )
    fills = _fills(canvas)
    assert fills.count(tokens.STATUS_SHORTAGE) == below
    assert tokens.STATUS_WARNING not in fills and tokens.STATUS_SECURE not in fills


def test_the_constrained_rate_keeps_its_own_target_on_the_home_basis() -> None:
    """제약 제품 확보율은 제약 목표에 견주는 칸이라 HOME 세 단계를 입히지 않는다."""
    row = _run().month(202706)
    assert figures._constrained_rate_cell(replace(row, met=False)).fill == tokens.STATUS_SHORTAGE
    assert figures._constrained_rate_cell(replace(row, met=True)).fill is None


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


def test_a_constraint_demand_below_one_unit_says_the_minimum_one_unit() -> None:
    """제약 소요가 1대 미만(0.025대)이면 필요 대수를 올림해 1대를 떼 제약 제품 확보율이 4000% 다 —
    계산표 두 칸 풍선·그래프 풍선이 「최소 1대」 를 곁들여 그 까닭을 말한다(2026-10-25 E2E #64).
    소요가 1대 이상인 달에는 붙지 않는다."""
    product = (0, 0, 0, 0, 0, 0.025, 6, 7, 8, 8, 9, 9, 10, 10, 11)
    result = _run(product=product)
    june = result.month(202706)
    assert (june.need, june.allocated) == (1, 1)
    assert figures.minimum_unit(june)
    assert figures._need_cell(june, 120).hover.endswith("→ 1대(최소)")
    rate_hover = figures._constrained_rate_cell(june).hover
    assert "0.03대가 1대 미만이라도 최소 1대를 떼어" in rate_hover
    assert "제약 4000.0%(최소 1대)" in figures._hit_hover(june, result.conditions)

    july = result.month(202707)
    assert not figures.minimum_unit(july)
    assert "최소" not in figures._hit_hover(july, result.conditions)
    assert "최소" not in figures._need_cell(july, 120).hover


def test_the_minimum_unit_explains_the_rate_only_when_that_one_unit_is_allocated() -> None:
    """「최소 1대」 는 필요 대수 쪽(필요 칸)에는 늘 붙지만, 확보율 쪽(확보율 칸 · 그래프 풍선)에는
    그 1대를 배정한 달에만 붙는다. 소요가 0.3대로 줄어도 개조한
    전용 6대를 남긴 달의 2000% 는 남긴 전용 때문이고, 가용이 모자라 배정하지 못한 달은 0% 라
    「최소 1대를 떼어 크게 나온다」 가 틀린 말이다."""
    retained = _run(product=(0, 0, 0, 0, 0, 5, 0.3, 7, 8, 8, 9, 9, 10, 10, 11))
    july = retained.month(202707)
    assert (july.need, july.dedicated, july.allocated) == (1, 6, 6)
    assert figures.minimum_unit(july) and not figures.minimum_rate(july)
    assert figures._need_cell(july, 120).hover.endswith("→ 1대(최소)")
    assert "최소" not in figures._constrained_rate_cell(july).hover
    assert "최소" not in figures._hit_hover(july, retained.conditions)

    short = simulate_constraint(
        (
            ConstraintMonthInput(202705, 3.0, 0.0, 3.0, 1.1),
            ConstraintMonthInput(202706, 3.0, 0.3, 0.6, 1.1),
        ),
        replace(CONDITIONS, period_start=202706, period_end=202706),
    )
    june = short.month(202706)
    assert (june.need, june.dedicated, june.allocated, june.short) == (1, 1, 0, True)
    assert figures.minimum_unit(june) and not figures.minimum_rate(june)
    assert figures._need_cell(june, 120).hover.endswith("→ 1대(최소)")
    assert "최소" not in figures._constrained_rate_cell(june).hover
    assert "최소" not in figures._hit_hover(june, short.conditions)


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
    assert short_lines(result).startswith("27.06: 전용 6대 중 5대만 배정")
    assert short_month_lines(result) == []
    assert overdrawn_lines(result) == [
        "27.05: 개조 비가동 5.81대가 가용 5대보다 많습니다 — 이 공정 설비로는 이 개조 창이 "
        "서지 않습니다."
    ]
    assert short_lines(_run()) == ""


def test_the_short_line_names_the_dedicated_units_and_folds_many_months() -> None:
    """모자란 달의 값은 그 달 필요(need)가 아니라 전용(dedicated)이다 — 기간 안 소요가 0 으로 내려도
    개조한 전용 6대를 유지하는 달(202707)에 「필요 6대」 라고 적었다(2026-10-25 E2E). 모자란 달이
    `SHORT_INLINE_LIMIT` 보다 많으면 한 줄에는 달 수·첫·끝 달만 적고 달마다 값은 접힌 줄로 간다."""
    rows = tuple(
        ConstraintMonthInput(month, 8.0, demand, 5.0, 1.1)
        for month, demand in zip(
            (202705, 202706, 202707, 202708, 202709, 202710), (0, 6, 0, 6, 6, 6), strict=True
        )
    )
    result = simulate_constraint(
        rows,
        replace(CONDITIONS, period_start=202706, period_end=202710, constraint_target=1.0),
    )
    july = result.month(202707)
    assert (july.need, july.dedicated, july.short) == (0, 6, True)
    assert len(result.short_months) == 5 > SHORT_INLINE_LIMIT
    line = short_lines(result)
    # 까닭(`SHORT_REASON_TEXT`)은 구획 제목 풍선이다 — 줄은 값만(설계 규칙 UI-TXT-04).
    assert line == "전용 대수를 다 배정하지 못한 달 5개월(27.06–27.10 사이)"
    assert "필요" not in line
    details = short_month_lines(result)
    assert len(details) == 5
    assert details[1].startswith("27.07: 전용 6대 중 ")
    assert all(": 전용 6대 중 " in text for text in details)


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


# ------------------------------------------------------------------ 2판 옵션 — 보유 · 신규 · 개조로
# 나눠 보이기 · 신규 대기

# 보유 4(서비스 시험 ①)와 신규 다섯 대(2026-10-26 오후 결정 — 개조 일수 30 안의 증가에 미리 붙임,
# `tests/test_constraint_simulation_options.py` 와 같은 손계산):
# N01 5/10 → 6월 몫(대기 15일, 5월 W/D) · N02 5/25 → 6월 몫(대기 0) · N03 6/10 → 7월 몫(대기 14일,
# 6월 W/D) · N04 8/1 → 9월 몫(대기 24일, 8월 W/D 7/25~8/24) · N05 9/1 → 일반 설비(11월 증가 10/25
# 는 54일 뒤). 증가 06 6 = 신규 2 + 개조 4 · 07 2 = 신규 1 + 개조 1 · 08 1 = 개조 · 09 1 = 신규 1 ·
# 11 1 = 개조 → 개조 7 · 신규 4.
NEW_UNITS = (
    _unit("N01", date(2027, 5, 10)),
    _unit("N02", date(2027, 5, 25)),
    _unit("N03", date(2027, 6, 10)),
    _unit("N04", date(2027, 8, 1)),
    _unit("N05", date(2027, 9, 1)),
)


def _owned(owned: int = 4) -> ConstraintResult:
    return simulate_constraint(_inputs(), replace(CONDITIONS, owned_units=owned))


def _new(*, owned: int = 0) -> ConstraintResult:
    return simulate_constraint(_inputs(), replace(NEW_ON, owned_units=owned), NEW_UNITS)


def test_the_schema_version_moved_with_the_new_rows() -> None:
    """계산표 행·띠 막대가 바뀌었다 — 세션 memo 의 옛 그림을 쓰지 않게 그림 버전을 올렸다(AGENTS 5장
    16). 7 은 「신규 설비로」·「보유 제약 설비로」 행이 채우는 차례(신규 → 보유)로 선 판이고, 8 은
    그래프 풍선에 「최소 1대」 를 곁들인 판, 9 는 y 축 상한을 자르고 넘는 점을 ▲ 로 찍은 판, 10 은
    묶음 신규의 모듈 몫(「HB-07(HB-07B)」)과 「보유로 제약 기간을 다 덮음」 풍선 글을
    싣고(2026-11-01 사용자 결정 B1 · B2) 차이를 「%」 로 적고(「%p」 없음) 기준선을 판정
    경계에 그은 판이다(2026-11-01 사용자 결정 N1 — 같은 배포의 두 갈래라 한 번 올렸다). 11 은
    계산표 「신규 기여 시작」 풍선의 일반 설비 까닭을 호기마다 되짚고(2026-11-01 E2E — 「개조 30일
    안에 늘어날 전용 없음」 이 일부 모듈만 온 묶음에도 섰다) B1 을 증가마다로 넓혀 뒤 증가부터 덮인
    호기에 「27년 7월부터 보유로 다 덮음」 을 적은 판이다(같은 날 — 두 갈래 모두 배포 전이라 한 번
    올렸다). 12 는 기준이 HOME 일 때 계산표 확보율 칸을 세 단계 색으로 칠하고 제약 없을 때 대비
    칸의 어긋난 차이에 「≈」 를 단 판이다(2026-11-07 사용자 답 — 한 번 올렸다). 13 은 고른 달 계산
    카드를 걷어 달 칸 풍선 끝의 「누르면 이 달 계산」 을 뺀 판이다(2026-11-08 사용자 그림 메모
    g12)."""
    assert CONSTRAINT_FIGURE_SCHEMA_VERSION == 13


def test_each_option_row_stands_only_with_its_option() -> None:
    owned = build_sheet_canvas(_owned(), LABELS, selected_month=None, show_proportional=False)
    assert {"growth", "owned_increment"} <= set(owned.row_ids)
    assert not {"new_starts", "new_increment", "waiting"} & set(owned.row_ids)
    new = build_sheet_canvas(_new(), LABELS, selected_month=None, show_proportional=False)
    assert {"new_starts", "growth", "new_increment", "waiting"} <= set(new.row_ids)
    assert "owned_increment" not in new.row_ids
    # 개조 끔이면 옵션이 걸리지 않아 행도 없다.
    off = build_sheet_canvas(
        simulate_constraint(
            _inputs(),
            replace(NEW_ON, modification_days=None, owned_units=4),
            NEW_UNITS,
        ),
        LABELS,
        selected_month=None,
        show_proportional=False,
    )
    assert not set(OPTION_ROWS) & set(off.row_ids)


def test_the_sheet_splits_the_growth_and_shows_the_wait() -> None:
    result = _new(owned=2)
    canvas = build_sheet_canvas(result, LABELS, selected_month=None, show_proportional=False)
    # 06: 증가 6 = 보유 2 + 신규 2 + 개조 2 · 07: 증가 2 = 신규 1 + 개조 1 · 09: 증가 1 = 신규 1.
    june, july = result.month(202706), result.month(202707)
    assert (june.growth, june.owned_increment, june.new_increment, june.increment) == (6, 2, 2, 2)
    assert (july.growth, july.new_increment, july.increment) == (2, 1, 1)
    assert result.month(202709).new_increment == 1
    starts = _cells(canvas, "new_starts")
    first = "N01 · 2027-05-10 기여 시작 · 1대 → 27년 6월 몫 전용"
    assert f"{first}(2027-05-10 ~ 2027-05-24 대기 15일)" in starts[202705]
    assert (
        "N02 · 2027-05-25 기여 시작 · 1대 → 27년 6월 몫 전용(대기 없음(W/D 첫날 기여 시작))"
        in (starts[202706])
    )
    assert (
        "N05 · 2027-09-01 기여 시작 · 1대 → 일반 설비(개조 30일 안에 늘어날 전용 없음)"
        in (starts[202709])
    )
    waiting = _cells(canvas, "waiting")
    assert "N01 · 27년 6월 몫 1대 × 15/31일 = 0.48" in waiting[202705]
    assert "N03 · 27년 7월 몫 1대 × 14/30일 = 0.47" in waiting[202706]
    assert "N04 · 27년 9월 몫 1대 × 24/31일 = 0.77" in waiting[202708]
    assert "신규 대기 없음" in waiting[202707]
    texts = [text for _, text in _texts(canvas)]
    assert f"{MINUS}0.48" in texts and f"{MINUS}0.77" in texts
    allocated = _cells(canvas, "allocated")
    assert "전용 6대 = 신규 2 · 보유 2 · 개조 2" in allocated[202706]
    available = _cells(canvas, "existing_available")
    assert "− 신규 대기 0.48" in available[202705]


def test_the_split_text_names_only_the_options_in_use() -> None:
    owned = _owned()
    assert (
        dedicated_split_text(owned.month(202706), owned.conditions) == "전용 6대 = 보유 4 · 개조 2"
    )
    assert dedicated_split_text(owned.month(202705), owned.conditions) == ""
    new = _new()
    assert dedicated_split_text(new.month(202707), new.conditions) == "전용 8대 = 신규 3 · 개조 5"
    plain = _run()
    assert dedicated_split_text(plain.month(202706), plain.conditions) == ""


def test_the_split_text_follows_the_fill_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """구성 글은 `FILL_ORDER` 차례다(지금 신규 → 보유) — 차례를 바꾸면 글도 따라간다(값은 서비스가
    다시 센다)."""
    both = _new(owned=2)
    assert dedicated_split_text(both.month(202706), both.conditions).startswith(
        "전용 6대 = 신규 2 · 보유 2"
    )
    monkeypatch.setattr(figures, "FILL_ORDER", (FILL_OWNED, FILL_NEW))
    assert dedicated_split_text(both.month(202706), both.conditions).startswith(
        "전용 6대 = 보유 2 · 신규 2"
    )


def test_the_hit_target_hover_carries_the_split_and_the_wait() -> None:
    result = _owned()
    hit = _spec(rate_figure(result, LABELS, selected_month=None, show_proportional=False))["data"][
        0
    ]
    hovers = {item[0]: item[1] for item in hit["customdata"]}
    assert "전용 6대 = 보유 4 · 개조 2" in hovers[202706]
    assert "전용" not in hovers[202705]
    plain = _spec(rate_figure(_run(), LABELS, selected_month=None, show_proportional=False))
    assert all("전용" not in item[1] for item in plain["data"][0]["customdata"])
    assert all("신규 대기" not in item[1] for item in plain["data"][0]["customdata"])
    new = _spec(rate_figure(_new(), LABELS, selected_month=None, show_proportional=False))
    new_hovers = {item[0]: item[1] for item in new["data"][0]["customdata"]}
    assert f"신규 대기 {MINUS}0.48대" in new_hovers[202705]


def test_the_downtime_bars_shrink_to_the_modified_units() -> None:
    """보유 4 — 06 몫 막대가 2대로 준다(창이 개조 몫만 내므로 그림 코드는 그대로). 신규가 없으면
    「신규 대기」 막대가 없다."""
    figure = rate_figure(_owned(), LABELS, selected_month=None, show_proportional=False)
    bars = _traces(figure, "개조 비가동")
    assert bars[0]["text"] == ["2대", "2대", "1대", "1대", "1대"]
    assert _traces(figure, "신규 대기") == []


def test_the_waiting_bars_share_the_band_with_the_modification() -> None:
    """신규 대기 막대(빗금)는 대기가 0일인 몫(N02)을 빼고 셋 — 개조 막대와 겹치는 줄은 아래로
    내린다. 누르면 그 대기가 든 첫 보이는 달을 고른다."""
    result = _new()
    spec = _spec(rate_figure(result, LABELS, selected_month=None, show_proportional=False))
    waits = [trace for trace in spec["data"] if trace.get("name") == "신규 대기"]
    assert len(waits) == 1
    bar = waits[0]
    assert bar["text"] == ["1대", "1대", "1대"]
    assert [item[0] for item in bar["customdata"]] == [202705, 202706, 202708]
    assert "27년 6월 몫 · 신규 N01 1대 대기" in bar["customdata"][0][1]
    assert bar["marker"]["pattern"]["shape"] == "/"
    modification = next(trace for trace in spec["data"] if trace.get("name") == "개조 비가동")
    # 6월 몫 개조(4/25~5/24)와 N01 대기(5/10~5/24)가 겹쳐 대기는 다른 줄이다.
    assert bar["y"][0] != modification["y"][0]
    assert spec["layout"]["yaxis2"]["range"][0] >= 1 - 0.5


def test_a_later_cover_names_its_month_and_splits_the_reasons() -> None:
    """B1 증가마다(2026-11-01 넓힘) — 필요 6월 2 → 7월 3 → 8월 3, 고른 H1(6/1). 7월 증가부터
    남은 보유가 남은 증가를 다 덮어 신규를 붙이지 않았다. 일반 설비가 된 신규의 까닭은 호기마다 —
    N1(6/20)은 7월 증가에 붙을 수 있었으니 「27년 7월 증가부터 보유 제약 설비로 다 덮어」, N2(7/1)는
    창 안에 증가가 없어 「개조 30일 안에 늘어날 전용이 없어」 다. 계산표 풍선이 같은 갈래를 쓴다."""
    months = _months(2, 3, 3)
    units = (LATE_UNIT, NewUnit("N2", date(2027, 7, 1), 1.0))
    result = simulate_constraint(months, _conditions(months, held=LATE_HELD, new=True), units)
    assert _stopped(result) and not result.new_units_skipped
    assert result.new_units_stopped_month == 202707
    first, second = result.new_units
    assert figures.ordinary_reason_text(first, result) == (
        "27년 7월 증가부터 보유 제약 설비로 다 덮어"
    )
    assert figures.ordinary_reason_text(second, result) == "개조 30일 안에 늘어날 전용이 없어"
    assert figures.new_unit_fate(first, result) == "일반 설비(27년 7월부터 보유로 다 덮음)"
    assert figures.new_unit_fate(second, result) == "일반 설비(개조 30일 안에 늘어날 전용 없음)"


def test_a_first_growth_cover_speaks_only_when_a_unit_was_held_back() -> None:
    """첫 증가부터 덮여도 「보유로 덮여 붙지 않은 호기」 는 붙지 않은 호기가 있을 때만이다 — 6/20
    신규는 6월 증가(t 5/25) 앞이고 7월 증가가 없어 어차피 붙지 않았을 호기라 까닭이 「보유 제약
    설비로 제약 기간을 다 덮어」 가 아니라 「개조 30일 안에 늘어날 전용이 없어」 다(cs2 리뷰가 남긴
    작은 어긋남). 5/25 신규는 6월 증가에 붙을 수 있었으니 「보유로 덮음」 이다."""
    months = _months(2, 2)
    conditions = _conditions(months, held=(_held("H1"), _held("H2")), new=True)
    late = simulate_constraint(months, conditions, (LATE_UNIT,))
    assert late.new_units_skipped
    assert not _stopped(late)
    assert figures.ordinary_reason_text(late.new_units[0], late) == (
        "개조 30일 안에 늘어날 전용이 없어"
    )
    early = simulate_constraint(months, conditions, (NewUnit("N0", JUNE_FIRST, 1.0),))
    assert _stopped(early) and early.new_units_skipped
    assert figures.ordinary_reason_text(early.new_units[0], early) == figures.SKIPPED_REASON
    assert (
        figures.new_unit_fate(early.new_units[0], early) == "일반 설비(보유로 제약 기간을 다 덮음)"
    )
    assert not _stopped(_new())


def test_the_stop_line_and_the_reasons_tell_the_same_story() -> None:
    """B1 증가마다(`feat/b1-widen-1101`)와 호기마다 까닭(`fix/e2e-1101`)을 합친 꼴의 맞물림 — 작은
    무작위 문제 600개(`_random_case`, 셋에 하나는 묶음 — `_with_bundles`, 합성). 일반 설비가 된
    신규마다:

    - 까닭이 「보유로 덮임」(`skipped`)인 것은 B1 로 실제로 붙지 않은 호기(`held_back_units`)와 꼭
      같고, 그 달은 신규를 붙이지 않기 시작한 달이다 — 글에 「보유」 가 드는 것도 그 호기뿐이다.
      붙지 않은 호기는 멈춘 달부터의 증가 가운데 붙일 수 있던 증가가 있다(무엇이 붙지 않은
      호기인지는 `tests/test_constraint_simulation_holdings.py` 가 B1 없이 돈 답과 맞댄다).
    - 「신규를 더 붙이지 않음」(멈춘 달 + 붙지 않은 호기 — `_stopped`)은 그런 호기가 있을 때만이다 —
      그 표지는 없는데 까닭만 「보유로 덮어」 이거나, 표지는 섰는데 그렇게 적힌 호기가 없는 일이
      없다.
    - 멈춘 달부터의 증가는 신규가 0 이라 「신규가 채움」 의 달에 들지 않는다. 「들어온 몫이 1대가
      안 됨」 에는 들 수 있다 — B1 없이도 그 증가에 1대가 되지 않는 몫이다.
    - 「신규가 채움」 의 달은 신규로 다 채운 증가이고, 「이 호기 몫으로 다 참」 의 달은 그 달 붙은
      몫이 모두 그 호기 것이다.
    """
    rng = random.Random(20261102)
    seen = {"skipped": 0, "other_after_stop": 0, "own": 0}
    for case in range(600):
        months, conditions, units = _random_case(rng)
        if case % 3 == 1:
            units = _with_bundles(rng, units)
        result = simulate_constraint(months, conditions, units)
        stopped = result.new_units_stopped_month
        held = {unit.name for unit in result.held_back_units}
        reach = conditions.modification_days or 0
        skipped = False
        for unit in result.ordinary_units:
            reason = result.ordinary_reason(unit)
            assert (reason.cause == "skipped") == (unit.name in held), (months, conditions, units)
            text = figures.ordinary_reason_text(unit, result)
            assert ("보유" in text) == (reason.cause == "skipped"), text
            if reason.cause == "skipped":
                skipped = True
                seen["skipped"] += 1
                assert reason.months == (stopped,)
                assert figures.month_name(reason.months[0]) in text or result.new_units_skipped
                assert stopped is not None
                assert any(
                    row.month >= stopped
                    and row.growth > 0
                    and unit.start <= (day := wd_window(row.month, 7).first_day)
                    and (day - unit.start).days <= reach
                    and (unit.until is None or day < unit.until)
                    for row in result.months
                ), (unit, months, conditions)
            elif reason.cause == "filled":
                assert reason.months, reason
                for month in reason.months:
                    row = result.month(month)
                    offered = row.growth - (
                        row.owned_increment
                        if FILL_ORDER.index(FILL_OWNED) < FILL_ORDER.index(FILL_NEW)
                        else 0
                    )
                    assert row.new_increment > 0 and row.new_increment == offered, reason
                    owners = {item.unit for item in result.assignments if item.month == month}
                    assert (month in reason.own) == (owners == {unit.name}), (reason, owners)
                    seen["own"] += month in reason.own
                if stopped is not None:
                    assert all(month < stopped for month in reason.months), reason
            if stopped is not None and reason.cause != "skipped":
                seen["other_after_stop"] += 1
        assert _stopped(result) == skipped, (months, conditions, units)
    # 표본이 갈래(붙지 않은 호기 · 멈춘 뒤 다른 까닭 · 제 몫으로 참)를 실제로 지나는지 — 표본이
    # 바뀌면 다시 센다.
    assert seen["skipped"] >= 20 and seen["other_after_stop"] >= 20 and seen["own"] >= 5, seen


def test_a_cover_where_no_unit_would_have_attached_says_nothing_on_the_card() -> None:
    """2026-11-01 리뷰의 보기 — 보유가 6월 증가부터 다 덮어 멈췄지만 신규 N0(5/05 · 0.5대)은 B1 이
    없어도 내림 0 이라 붙지 않았다. 「보유로 덮여 붙지 않은 호기」 는 없고, N0 의 까닭은 「보유로
    덮어」 가 아니라 그 0.5대다."""
    months = _months(1, 2, 2)
    held = (_held("H1"), _held("H2"), _held("H3"))
    unit = NewUnit("N0", date(2027, 5, 5), 0.5)
    result = simulate_constraint(months, _conditions(months, owned=1, held=held, new=True), (unit,))
    assert result.new_units_skipped
    assert not _stopped(result)
    assert figures.ordinary_reason_text(unit, result) == (
        "27년 6월 증가 때 들어온 0.50대로는 1대가 되지 않아"
    )


def test_an_increase_the_unit_filled_by_itself_is_not_said_to_be_filled_by_another() -> None:
    """그 달 붙은 몫이 모두 그 호기 것이면 「먼저 들어온 신규가 채워」 가 아니라 「이 호기 몫으로 다
    차」 다(2026-11-01 리뷰). 묶음 G(G-A 5/20 0.75 · G-B 6/05 0.75, 개조 45일)는 7월 증가를 제
    두 모듈로 채우고 G-B 0.5대가 남는다 — 6월(개조 1대)은 적지 않는다. 하나짜리 U(5/25 · 1.5)는
    6월 증가를 앞선 X 가, 7월 증가를 제 1대가 채웠다 — 두 말을 잇는다."""
    months = _months(1, 2)
    conditions = replace(_conditions(months, new=True), modification_days=45)
    bundle = _bundle("G", ("G-A", date(2027, 5, 20), 0.75), ("G-B", date(2027, 6, 5), 0.75))
    result = simulate_constraint(months, conditions, (bundle,))
    assert figures.ordinary_reason_text(bundle, result) == "27년 7월 증가는 이 호기 몫으로 다 차"
    assert figures.new_unit_fate(bundle, result).endswith(
        " · 남는 0.50대 일반 설비(27년 7월 증가는 이 호기 몫으로 다 참)"
    )

    unit = NewUnit("U", JUNE_FIRST, 1.5)
    both = simulate_constraint(
        months, _conditions(months, new=True), (NewUnit("X", date(2027, 5, 20), 1.0), unit)
    )
    assert figures.ordinary_reason_text(unit, both) == (
        "27년 6월 증가를 먼저 들어온 신규가 채우고 27년 7월 증가는 이 호기 몫으로 다 차"
    )
    assert figures.ordinary_reason_text(unit, both, noun=True) == (
        "27년 6월 증가를 먼저 들어온 신규가 채우고 27년 7월 증가는 이 호기 몫으로 다 참"
    )


def test_a_partly_attached_unit_is_named_with_its_leftover() -> None:
    """환산 1.5 인 신규 C(5/25)는 6월 몫에 1대가 붙고 0.5대가 남는다 — 계산표 풍선은 C 를 「붙음」
    과 「기존 제품 몫」 으로 통째로 함께 적지 않고 남는 0.50대만 일반 설비로 적는다(2026-10-26
    리뷰). 남는 까닭은 「창 안 증가
    없음」 이 아니다 — 6월(개조 5대)·7월(W/D 첫날 6/24 = 5/25 + 30일) 증가가 창 안에 있었지만 남은
    0.5대가 내림 정수 1대가 되지 않았다(2026-11-01 E2E — 까닭 글은 호기마다 되짚는다)."""
    result = simulate_constraint(_inputs(), NEW_ON, (_unit("C", date(2027, 5, 25), units=1.5),))
    (unit,) = result.new_units
    assert result.assigned_units(unit) == 1 and result.left_units(unit) == 0.5
    assert figures.ordinary_reason_text(unit, result) == (
        "27년 6월 · 27년 7월 증가 때 남은 0.50대로는 1대가 되지 않아"
    )
    assert figures.new_unit_fate(result.new_units[0], result) == (
        "27년 6월 몫 1대 전용(대기 없음(W/D 첫날 기여 시작)) · 남는 0.50대 일반 설비(27년 6월 · "
        "27년 7월 증가 때 남은 0.50대로는 1대가 되지 않음)"
    )


def test_the_reasons_say_why_each_unit_became_ordinary() -> None:
    """계산표 풍선은 호기마다 까닭을 적는다(2026-11-01 E2E). 묶음 G(G-A 5/25 · G-B 6/10)는 6월
    증가(W/D 첫날 5/25)가 창 안에 있었는데 G-A 0.5대만 와 있었고 G-B 는 오지 않았다 — 「개조 30일
    안에 늘어날 전용이 없어」 가 아니다. F 는 창 안 증가가 없어 그 글 그대로다."""
    months = _months(1, 1, 1)
    bundle = _bundle("G", ("G-A", date(2027, 5, 25), 0.5), ("G-B", date(2027, 6, 10), 0.5))
    late = NewUnit("F", date(2027, 7, 20), 1.0)
    result = simulate_constraint(months, _conditions(months, new=True), (bundle, late))

    assert figures.ordinary_reason_text(bundle, result) == (
        "27년 6월 증가 때 들어온 0.50대로는 1대가 되지 않고 G-B는 아직 오지 않아"
    )
    assert figures.ordinary_reason_text(late, result) == "개조 30일 안에 늘어날 전용이 없어"
    assert figures.new_unit_fate(bundle, result) == (
        "일반 설비(27년 6월 증가 때 들어온 0.50대로는 1대가 되지 않고 G-B는 아직 오지 않음)"
    )
    assert figures.new_unit_fate(late, result) == "일반 설비(개조 30일 안에 늘어날 전용 없음)"


def test_the_modification_kpi_counts_only_the_modified_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """값 = 실제로 개조하는 대수, 회색 줄 = 전용 최대의 구성(보유 4 → 11 = 4 + 7). 회색 줄은
    카드 넷이 한 줄에 서게 짧다 — 창 수·첫 비가동은 개조 창 카드가 말한다."""
    cards = _kpi_cards(monkeypatch, _owned())
    assert cards["개조 대수"] == ("7대", "전용 최대 11대 = 보유 4 · 개조 7")
    cards = _kpi_cards(monkeypatch, _new(owned=3))
    assert cards["개조 대수"] == ("4대", "전용 최대 11대 = 신규 4 · 보유 3 · 개조 4")
    cards = _kpi_cards(monkeypatch, _new())
    assert cards["개조 대수"] == ("7대", "전용 최대 11대 = 신규 4 · 개조 7")
