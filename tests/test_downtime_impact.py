# Purpose: 공정 Capa 상세 ② 「비가동 영향」 의 손실 갈림·확보율 영향 계산과 캔버스 줄을 고정한다.

"""② 「비가동 영향」(2026-10-27 사용자 결정 「같이 넣어」).

달마다 손실 = 호기 비가동 손실(비가동을 비운 반사실 − 실제) + 입력 비가동 반영(0 에서 멈춘 뒤
실제로 뺀 몫)이고, 확보율 영향은 그 손실 ÷ 소요 × 100(%p)이다 — 가용·소요는 계획의 단축 전 값
(② 확보율과 같은 길)이다. 계산(`downtime_impact`)은 손으로 셀 수 있는 표와 실제 설비 일정 둘로
보고, 그림은 결합 캔버스 시험의 설비 일정(`_dynamic`)에 손실 칸만 덧입혀 본다.
"""

from __future__ import annotations

import json
import math
from datetime import date
from typing import Any

import pandas as pd
import pytest
from test_process_capa_canvas import (
    MONTHS,
    REQUIRED,
    _annotations,
    _canvas,
    _dynamic,
    _label_hovers,
    _row_center,
    _targets,
    _texts,
)
from test_process_equipment_timeline import _arrow_fixture, _old
from test_required_shortening import (
    EARLY,
    JUNE,
    MAY,
    PROCESS,
    _baseline,
    _cutoff,
    _downtime,
    _master,
    _required,
)

from capa_simulation.components.process_capa_canvas import (
    CUSTOMDATA_HOVER,
    CUSTOMDATA_MONTH,
    CUSTOMDATA_ROW,
    IMPACT_LABEL_HOVER,
    ROW_DYNAMIC_BALANCE,
    ROW_DYNAMIC_COMPARE,
    ROW_DYNAMIC_DELTA,
    ROW_DYNAMIC_IMPACT,
    TWO_LINE_ROW_HEIGHT_PX,
    DynamicCanvasInput,
    ProcessCapaCanvas,
)
from capa_simulation.design import tokens
from capa_simulation.services.process_equipment_timeline import (
    IMPACT_COLUMNS,
    build_process_equipment_timeline,
    downtime_impact,
)
from capa_simulation.services.required_shortening import plan_required_shortening

JULY = 202607
AUGUST = 202608
AXIS = (MAY, JUNE, JULY)
MINUS = "−"


# ------------------------------------------------------------------ 계산 — 손으로 센 표


def _impact_rows(bridge: dict[str, list[Any]], plan: dict[str, list[Any]]) -> pd.DataFrame:
    return downtime_impact(pd.DataFrame(bridge), pd.DataFrame(plan)).set_index("생산계획년월")


def test_the_loss_is_the_unit_and_input_split_and_the_points_divide_by_demand() -> None:
    """5월: 호기 0.6 + 입력 0.4 = 1.0 대, 소요 5 · 가용 4 → 비가동 없으면 5 (100%) · 지금 80% ·
    20%p. 6월은 깎은 것이 없고, 7월은 소요 0 이라 대수만, 8월은 계획에 없는 달이다."""
    frame = _impact_rows(
        {
            "생산계획년월": [MAY, JUNE, JULY, AUGUST],
            "호기 비가동 손실": [0.6, 0.0, 0.3, 0.2],
            "입력 비가동 반영": [0.4, 0.0, 0.0, 0.5],
        },
        {
            "생산계획년월": [MAY, JUNE, JULY],
            "소요대수": [5.0, 4.0, 0.0],
            "가용대수": [4.0, 4.0, 2.0],
        },
    )

    assert list(frame.reset_index().columns) == list(IMPACT_COLUMNS)
    may = frame.loc[MAY]
    assert (may["호기 비가동 손실"], may["입력 비가동 손실"], may["비가동 손실"]) == (0.6, 0.4, 1.0)
    assert may["비가동 없는 가용대수"] == 5.0
    assert may["확보율"] == pytest.approx(0.8)
    assert may["비가동 없는 확보율"] == pytest.approx(1.0)
    assert may["확보율 영향(%p)"] == pytest.approx(20.0)
    # 영향은 두 확보율의 차이 그 자체다.
    assert may["확보율 영향(%p)"] == pytest.approx(
        (may["비가동 없는 확보율"] - may["확보율"]) * 100
    )
    june = frame.loc[JUNE]
    assert (june["비가동 손실"], june["확보율 영향(%p)"]) == (0.0, 0.0)
    assert june["비가동 없는 가용대수"] == june["가용대수"] == 4.0
    july = frame.loc[JULY]
    assert july["비가동 손실"] == pytest.approx(0.3)
    assert july["비가동 없는 가용대수"] == pytest.approx(2.3)
    for column in ("확보율", "비가동 없는 확보율", "확보율 영향(%p)"):
        assert math.isnan(july[column]), column
    august = frame.loc[AUGUST]
    assert august["비가동 손실"] == pytest.approx(0.7)
    assert math.isnan(august["소요대수"]) and math.isnan(august["비가동 없는 가용대수"])


def test_an_empty_bridge_gives_the_empty_columns_and_a_repeated_month_stops() -> None:
    empty = downtime_impact(
        pd.DataFrame(columns=["생산계획년월", "호기 비가동 손실", "입력 비가동 반영"]),
        pd.DataFrame(),
    )
    assert empty.empty and list(empty.columns) == list(IMPACT_COLUMNS)
    with pytest.raises(ValueError, match="같은 달"):
        downtime_impact(
            pd.DataFrame(
                {"생산계획년월": [MAY], "호기 비가동 손실": [0.0], "입력 비가동 반영": [0.0]}
            ),
            pd.DataFrame(
                {"생산계획년월": [MAY, MAY], "소요대수": [1.0, 1.0], "가용대수": [1.0, 1.0]}
            ),
        )


# ------------------------------------------------------------------ 계산 — 실제 설비 일정


def _impact_timeline(
    rows: list[dict[str, Any]],
    downtime: pd.DataFrame,
    manual: tuple[tuple[int, float], ...] = (),
) -> pd.DataFrame:
    return build_process_equipment_timeline(
        _master(rows),
        downtime,
        _baseline(3.0),
        _cutoff(),
        process=PROCESS,
        months=AXIS,
        manual_downtime=manual,
    ).bridge


def test_the_unit_loss_is_the_hand_counted_counterfactual_gap_per_month() -> None:
    """`_arrow_fixture`(Cut-off 10) — 5월 구간 (4/20, 5/21] 31일에 OLD3(4/1~4/25)가 4/21~4/26 6일,
    6월 구간 30일에 OLD1 5일 + GA 2일 × 0.5 + OLD4 6/6~6/9 4일(6/10 반출), 7월 구간 31일에 OLD2
    7/11~7/21 11일(열린 구간)을 깎는다. 셋업 전 SET1·보관 ST1 의 비가동은 깎을 가용이 없다."""
    rows, downtime = _arrow_fixture()
    bridge = _impact_timeline(rows, downtime).set_index("생산계획년월")

    assert list(bridge["호기 비가동 손실"]) == pytest.approx([6 / 31, 10 / 30, 11 / 31])
    # 비가동을 비운 설비 일정의 가용 − 지금 가용과 같다.
    free = _impact_timeline(rows, _downtime()).set_index("생산계획년월")
    assert list(bridge["호기 비가동 손실"]) == pytest.approx(
        list(free["가용대수"] - bridge["가용대수"])
    )


def test_the_input_share_is_clamped_and_no_downtime_at_all_is_the_free_schedule() -> None:
    """6월에 입력 2.0 은 그대로 빠지고, 5월에 넣은 99.0 은 그 달 가용(기존보유 3 + 호기 가용)에서
    멈춘 몫만 손실이다. 비가동이 하나도 없을 때의 가용은 호기 비가동도 입력도 없는 설비 일정의
    가용이다. %p 는 계획(같은 입력)의 단축 전 가용 · 소요로 낸다."""
    rows, downtime = _arrow_fixture()
    manual = ((MAY, 99.0), (JUNE, 2.0))
    bridge = _impact_timeline(rows, downtime, manual)
    need = {MAY: 5.0, JUNE: 5.0, JULY: 5.0}
    plan = plan_required_shortening(
        equipment=_master(rows),
        downtime=downtime,
        baseline=_baseline(3.0),
        cutoff=_cutoff(),
        required_equipment=_required(need),
        months=AXIS,
        today=EARLY,
        levels=(1.0,),
        manual_downtime=tuple((PROCESS, month, value) for month, value in manual),
    ).at(1.0)
    impact = downtime_impact(bridge, plan.process_months).set_index("생산계획년월")
    by_month = bridge.set_index("생산계획년월")

    may = impact.loc[MAY]
    held = sum(
        float(by_month[column].to_numpy(dtype="float64")[AXIS.index(MAY)])
        for column in ("기존보유", "호기 가용")
    )
    assert may["입력 비가동 손실"] == pytest.approx(held)  # 99 가 아니라 멈춘 몫
    assert may["가용대수"] == 0.0
    assert impact.loc[JUNE, "입력 비가동 손실"] == 2.0
    assert impact.loc[JULY, "입력 비가동 손실"] == 0.0
    free = _impact_timeline(rows, _downtime()).set_index("생산계획년월")
    assert list(impact["비가동 없는 가용대수"]) == pytest.approx(list(free["가용대수"]))
    assert list(impact["가용대수"]) == pytest.approx(list(by_month["가용대수"]))
    assert list(impact["확보율 영향(%p)"]) == pytest.approx(list(impact["비가동 손실"] / 5.0 * 100))
    assert list(impact["확보율"]) == pytest.approx(list(plan.process_months["확보율"]))


def test_no_downtime_at_all_gives_zero_loss_every_month() -> None:
    bridge = _impact_timeline([_old("OLD1"), _old("OLD2")], _downtime())
    assert list(bridge["호기 비가동 손실"]) == [0.0, 0.0, 0.0]


# ------------------------------------------------------------------ 공정 Capa 상세 ② 줄


def _impact_dynamic(
    units: dict[int, float],
    manual: dict[int, float],
    *,
    plan: dict[int, tuple[float, float]] | None = None,
    **changes: Any,
) -> DynamicCanvasInput:
    """캔버스 시험의 설비 일정에 손실 칸(달 index → 대수)과 계획 소요·가용(달 index → (소요,
    가용))만 덧입힌다."""
    base = _dynamic(**changes)
    bridge = base.bridge.copy()
    bridge["호기 비가동 손실"] = [units.get(index, 0.0) for index in range(len(MONTHS))]
    bridge["입력 비가동 반영"] = [manual.get(index, 0.0) for index in range(len(MONTHS))]
    months = base.process_months.copy()
    for index, (need, available) in (plan or {}).items():
        at = months["생산계획년월"].eq(MONTHS[index])
        months.loc[at, "소요대수"] = need
        months.loc[at, "가용대수"] = available
    return DynamicCanvasInput(**{**base.__dict__, "bridge": bridge, "process_months": months})


def _cell_lines(canvas: ProcessCapaCanvas, row_id: str) -> dict[int, list[tuple[str, str]]]:
    """그 행 칸마다 (글, 색) — 위 줄부터."""
    center = _row_center(canvas, row_id)
    found: dict[int, list[tuple[float, str, str]]] = {}
    for x, y, text, color in _texts(canvas):
        if abs(y - center) < TWO_LINE_ROW_HEIGHT_PX / 2:
            found.setdefault(int(x), []).append((y, text, color))
    return {
        index: [(text, color) for _, text, color in sorted(items, reverse=True)]
        for index, items in found.items()
    }


def _hovers(canvas: ProcessCapaCanvas, row_id: str) -> dict[int, str]:
    return {
        int(data[CUSTOMDATA_MONTH]): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == row_id
    }


def test_the_impact_row_sits_right_under_the_monthly_change_with_two_lines() -> None:
    canvas = _canvas(dynamic=_impact_dynamic({0: 1.0}, {}))
    ids = list(canvas.row_ids)
    start = ids.index("title:dynamic")

    assert ids[start + 1 : start + 6] == [
        ROW_DYNAMIC_COMPARE,
        "dynamic_available",
        ROW_DYNAMIC_DELTA,
        ROW_DYNAMIC_IMPACT,
        ROW_DYNAMIC_BALANCE,
    ]
    targets = [item for item in _targets(canvas) if item[0][CUSTOMDATA_ROW] == ROW_DYNAMIC_IMPACT]
    assert {height for _, _, height in targets} == {TWO_LINE_ROW_HEIGHT_PX}
    assert len(targets) == len(MONTHS)  # 빈 달도 칸(풍선)이 있다
    labels = {item["text"] for item in _annotations(canvas.labels)}
    assert "비가동 영향" in labels
    assert _label_hovers(canvas)[ROW_DYNAMIC_IMPACT] == IMPACT_LABEL_HOVER
    # ② 를 접으면 함께 숨는다.
    folded = _canvas(dynamic=_impact_dynamic({0: 1.0}, {}), collapsed=frozenset({"dynamic"}))
    assert ROW_DYNAMIC_IMPACT not in folded.row_ids


def test_the_cell_reads_units_then_points_and_the_hover_names_both_rates_and_the_split() -> None:
    """26.11: 호기 1.2 + 입력 0.6 = 1.8 대, 소요 45 · 가용 45 → 비가동 없으면 104.0% · 지금 100.0% ·
    −4.0%p."""
    dynamic = _impact_dynamic({0: 1.2}, {0: 0.6}, plan={0: (45.0, 45.0)})
    canvas = _canvas(dynamic=dynamic)
    lines = _cell_lines(canvas, ROW_DYNAMIC_IMPACT)

    assert [text for text, _ in lines[0]] == [f"{MINUS}1.8대", f"{MINUS}4.0%p"]
    assert {color for _, color in lines[0]} == {tokens.TEXT}
    hover = _hovers(canvas, ROW_DYNAMIC_IMPACT)[MONTHS[0]]
    first, second = hover.split("<br>")
    assert first == f"<b>26.11</b> · 비가동 영향 {MINUS}1.8대 · {MINUS}4.0%p"
    assert second == (
        f"비가동 없으면 확보율 104.0% → 지금 100.0% · 호기 비가동 {MINUS}1.2대 + "
        f"입력 비가동 {MINUS}0.6대"
    )


def test_a_month_without_loss_is_blank_and_says_so_in_the_hover() -> None:
    canvas = _canvas(dynamic=_impact_dynamic({0: 1.2}, {}))
    lines = _cell_lines(canvas, ROW_DYNAMIC_IMPACT)
    hovers = _hovers(canvas, ROW_DYNAMIC_IMPACT)

    assert set(lines) == {0}
    for month in MONTHS[1:]:
        assert "비가동 영향 없음" in hovers[month]
        assert "%p" not in hovers[month]


def test_an_input_only_month_names_only_the_input_share() -> None:
    """27.01: 입력 0.5 만 — 소요 47.5 라 −1.1%p, 갈림은 입력 하나(0 인 호기 쪽은 뺀다)."""
    canvas = _canvas(dynamic=_impact_dynamic({}, {2: 0.5}))
    lines = _cell_lines(canvas, ROW_DYNAMIC_IMPACT)
    hover = _hovers(canvas, ROW_DYNAMIC_IMPACT)[MONTHS[2]]

    assert REQUIRED[2] == 47.5
    assert [text for text, _ in lines[2]] == [f"{MINUS}0.5대", f"{MINUS}1.1%p"]
    assert hover.endswith(f" · 입력 비가동 {MINUS}0.5대")
    assert "호기 비가동" not in hover and " + " not in hover


def test_a_zero_demand_month_shows_units_only() -> None:
    canvas = _canvas(dynamic=_impact_dynamic({3: 0.7}, {}, plan={3: (0.0, 2.0)}))
    lines = _cell_lines(canvas, ROW_DYNAMIC_IMPACT)
    hover = _hovers(canvas, ROW_DYNAMIC_IMPACT)[MONTHS[3]]

    assert [text for text, _ in lines[3]] == [f"{MINUS}0.7대"]
    assert hover.split("<br>") == [
        f"<b>27.02</b> · 비가동 영향 {MINUS}0.7대",
        f"소요 0 — 확보율 영향 없음 · 호기 비가동 {MINUS}0.7대",
    ]


def test_a_split_that_does_not_add_up_as_written_gets_the_approx_mark() -> None:
    """0.85 + 0.85 = 1.7 인데 적힌 갈림은 −0.8 + −0.8(= −1.6)이다 — 갈림 앞에 「≈」."""
    canvas = _canvas(dynamic=_impact_dynamic({5: 0.85}, {5: 0.85}))
    hover = _hovers(canvas, ROW_DYNAMIC_IMPACT)[MONTHS[5]]
    assert f"비가동 영향 {MINUS}1.7대" in hover
    assert f"≈ 호기 비가동 {MINUS}0.8대 + 입력 비가동 {MINUS}0.8대" in hover
    exact = _hovers(_canvas(dynamic=_impact_dynamic({0: 1.2}, {0: 0.6})), ROW_DYNAMIC_IMPACT)
    assert "≈" not in exact[MONTHS[0]]


def test_a_tiny_loss_is_not_written_as_zero() -> None:
    """하루치 손실 × 작은 환산비(0.003대)도 「0.0」 이 아니라 자리를 늘려 적는다."""
    canvas = _canvas(dynamic=_impact_dynamic({1: 0.003}, {}))
    texts = [text for text, _ in _cell_lines(canvas, ROW_DYNAMIC_IMPACT)[1]]
    assert texts[0] == f"{MINUS}0.003대"


def test_past_months_are_muted_in_the_impact_row() -> None:
    canvas = _canvas(dynamic=_impact_dynamic({0: 1.0, 4: 1.0}, {}, today=date(2027, 2, 10)))
    lines = _cell_lines(canvas, ROW_DYNAMIC_IMPACT)
    assert {color for _, color in lines[0]} == {tokens.TEXT_MUTED}
    assert {color for _, color in lines[4]} == {tokens.TEXT}


def test_the_upeh_plan_marks_the_impact_row_and_its_hover() -> None:
    """가정 계획이면 %p 가 가정 소요로 바뀌어 라벨에 표지를 달고 풍선이 그 기준을 밝힌다."""
    dynamic = _impact_dynamic({0: 1.0}, {})
    marked = DynamicCanvasInput(**{**dynamic.__dict__, "official_pulls": {}})
    canvas = _canvas(dynamic=marked)
    labels = json.dumps(_annotations(canvas.labels), ensure_ascii=False)
    assert "비가동 영향 · UPEH 가정" in labels
    assert _hovers(canvas, ROW_DYNAMIC_IMPACT)[MONTHS[0]].endswith("확보율은 UPEH 가정 소요 기준")
