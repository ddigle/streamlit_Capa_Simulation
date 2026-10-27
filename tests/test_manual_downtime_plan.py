# Purpose: 입력 비가동이 계획·전월 대비·계산 키·공정 Capa 상세 ④ 줄에 닿는지 검증한다.

"""입력 비가동 대수(2026-10-27 사용자 결정)가 실행 관리 쪽 가용에 함께 닿는다.

손으로 셀 수 있게 잡았다 — Cut-off 10, 5~7월. 기존보유 2대 + 3월에 Qual 을 마친 호기 하나(U1)로
달마다 가용 3.0 이고, 7/15 Qual 호기 U2 는 7월 구간 `(6/20, 7/21]` 에 6일만 기여한다(6/31).
소요 3.0 · 목표 100% 면 5·6월은 충족이다. 6월에 입력 비가동 1.0 을 넣으면 6월 가용이 2.0 이 되어
U2 를 당겨야 한다.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_process_capa_canvas import MONTHS as CANVAS_MONTHS
from test_process_capa_canvas import _canvas, _dynamic, _label_hovers, _row_texts, _targets
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
    _unit,
)

from capa_simulation.components.process_capa_canvas import (
    CUSTOMDATA_HOVER,
    CUSTOMDATA_MONTH,
    CUSTOMDATA_ROW,
    MANUAL_DOWNTIME_ROW_LABEL,
    ROW_DYNAMIC_AVAILABLE,
    ROW_MANUAL_DOWNTIME,
)
from capa_simulation.services import simulation_cache
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    BRIDGE_COLUMNS,
    build_process_equipment_timeline,
)
from capa_simulation.services.required_shortening import ShorteningPlan, plan_required_shortening

JULY = 202607
AXIS = (MAY, JUNE, JULY)
UNITS = [
    _unit("U1", date(2026, 3, 1), arrival=date(2026, 2, 1)),
    _unit("U2", date(2026, 7, 15)),
]
NEED = {MAY: 3.0, JUNE: 3.0, JULY: 3.0}


def _plan(manual: tuple[tuple[str, int, float], ...] | None = None) -> ShorteningPlan:
    arguments: dict[str, Any] = {
        "equipment": _master(UNITS),
        "downtime": _downtime(),
        "baseline": _baseline(2.0),
        "cutoff": _cutoff(),
        "required_equipment": _required(NEED),
        "months": AXIS,
        "today": EARLY,
        "levels": (1.0,),
    }
    if manual is not None:
        arguments["manual_downtime"] = manual
    return plan_required_shortening(**arguments)


def _available(plan: ShorteningPlan) -> dict[int, float]:
    frame = plan.at(1.0).process_months
    return {
        int(month): round(float(value), 9)
        for month, value in zip(frame["생산계획년월"], frame["가용대수"], strict=True)
    }


# ------------------------------------------------------------------ 계획


def test_no_input_gives_exactly_the_plan_before() -> None:
    """옵션 끔(칸 없음)은 전과 같은 숫자다 — 빈 칸을 넘긴 계획과 인자를 안 넘긴 계획이 같다."""
    before, empty = _plan(), _plan(())
    assert_frame_equal(before.at(1.0).process_months, empty.at(1.0).process_months)
    assert_frame_equal(before.at(1.0).units, empty.at(1.0).units)
    assert empty.manual_downtime.empty
    assert _available(before) == {MAY: 3.0, JUNE: 3.0, JULY: pytest.approx(2.0 + 1.0 + 6 / 31)}


def test_input_lowers_that_month_and_the_plan_pulls_a_unit_for_it() -> None:
    before, after = _plan(), _plan(((PROCESS, JUNE, 1.0),))
    assert _available(after) == {**_available(before), JUNE: 2.0}
    june = after.at(1.0).process_months.set_index("생산계획년월").loc[JUNE]
    assert june["과부족"] == pytest.approx(-1.0)
    assert june["단축후과부족"] >= -1e-9
    assert "U2" in set(after.at(1.0).units["호기"])
    assert "U2" not in set(before.at(1.0).units["호기"])
    assert after.manual_downtime.to_dict("records") == [
        {"공정": PROCESS, "생산계획년월": JUNE, "입력대수": 1.0, "반영대수": 1.0, "초과": False}
    ]


def test_input_above_the_month_availability_stops_at_zero_and_is_flagged() -> None:
    plan = _plan(((PROCESS, MAY, 10.0),))
    assert _available(plan)[MAY] == 0.0
    record = plan.manual_downtime.iloc[0]
    assert (record["반영대수"], bool(record["초과"])) == (3.0, True)


def test_input_for_a_process_or_month_the_plan_does_not_compare_is_ignored() -> None:
    plan = _plan((("Other", JUNE, 1.0), (PROCESS, 202612, 1.0)))
    assert _available(plan) == _available(_plan())
    assert plan.manual_downtime.empty


# ------------------------------------------------------------------ ② 전월 대비


def _timeline(manual: tuple[tuple[int, float], ...] = ()) -> pd.DataFrame:
    return build_process_equipment_timeline(
        _master(UNITS),
        _downtime(),
        _baseline(2.0),
        _cutoff(),
        process=PROCESS,
        months=AXIS,
        manual_downtime=manual,
    ).bridge


def _value(bridge: pd.DataFrame, month: int, column: str) -> float:
    """전월 대비 한 칸(그 달 줄)."""
    return float(bridge.loc[bridge["생산계획년월"].eq(month), column].to_numpy(dtype="float64")[0])


def test_the_bridge_subtracts_the_input_and_books_its_change_as_downtime() -> None:
    plain, bridge = _timeline(), _timeline(((JUNE, 1.0), (JULY, 5.0)))
    assert list(bridge.columns) == list(BRIDGE_COLUMNS)
    rows = bridge.set_index("생산계획년월")
    # 가용대수는 필요 단축 계획과 같은 값이다(같은 칸·같은 멈춤 규칙).
    plan = _plan(((PROCESS, JUNE, 1.0), (PROCESS, JULY, 5.0)))
    for month, value in _available(plan).items():
        assert rows.loc[month, "가용대수"] == pytest.approx(value)
    assert rows.loc[JULY, "입력 비가동 반영"] == pytest.approx(
        _value(bridge, JULY, "기존보유") + 1 + 6 / 31
    )
    assert rows.loc[JULY, "가용대수"] == 0.0
    # 전월대비 = 신규 + 비가동 + 반출이설, 비가동은 입력 비가동 증감을 품는다.
    for month in (JUNE, JULY):
        row = rows.loc[month]
        assert row["전월대비"] == pytest.approx(row["신규"] + row["비가동"] + row["반출이설"])
    assert rows.loc[JUNE, "입력 비가동 증감"] == pytest.approx(-1.0)
    assert rows.loc[JUNE, "비가동"] == pytest.approx(_value(plain, JUNE, "비가동") - 1.0)
    # 입력이 없으면 새 칸은 0 이고 나머지는 전과 같다.
    old_columns = [column for column in BRIDGE_COLUMNS if not column.startswith("입력")]
    assert_frame_equal(plain.loc[:, old_columns], _timeline().loc[:, old_columns])
    assert plain["입력 비가동"].tolist() == [0.0, 0.0, 0.0]
    assert math.isnan(plain["입력 비가동 증감"].iloc[0])


# ------------------------------------------------------------------ 캐시 키


def _key(manual: ManualDowntime) -> simulation_cache.RequiredShorteningCacheKey:
    return simulation_cache.required_shortening_cache_key(
        (1, "token", MAY, JULY),
        equipment=_master(UNITS),
        downtime=_downtime(),
        baseline=_baseline(2.0),
        cutoff=_cutoff(),
        months=AXIS,
        today=EARLY,
        manual_downtime=manual,
    )


def test_a_save_inside_the_months_moves_the_key_and_one_outside_does_not() -> None:
    empty = _key(ManualDowntime())
    saved = _key(ManualDowntime(rows=((PROCESS, JUNE, 1.0),), version=1))
    assert saved != empty
    # 끝 칸이 계산할 달로 좁힌 칸 그 자체다.
    assert saved[8] == ((PROCESS, JUNE, 1.0),)
    # 조회기간 밖 칸·version 만 다른 저장은 계산을 가르지 않는다.
    outside = _key(ManualDowntime(rows=((PROCESS, 202612, 4.0),), version=9))
    assert outside == empty
    # UPEH 가정 토큰만 바꾼 키도 칸을 그대로 싣는다. 설비 일정 키는 그 공정 칸만 싣는다.
    assert simulation_cache.with_upeh_token(saved, (90, (JUNE,)))[8] == saved[8]
    assert simulation_cache.process_timeline_key_from_shortening(saved, PROCESS)[-1] == (
        (JUNE, 1.0),
    )
    assert simulation_cache.process_timeline_key_from_shortening(saved, "Other")[-1] == ()


def test_the_cached_plan_rebuilds_the_input_from_its_key() -> None:
    """계산 래퍼는 키의 칸으로 입력 비가동을 다시 세운다 — 키가 다르면 다른 계획이다."""
    simulation_cache.get_required_shortening.clear()
    simulation_cache.get_equipment_lifecycle_spans.clear()

    def plan(manual: ManualDowntime) -> ShorteningPlan:
        return simulation_cache.get_required_shortening(
            _key(manual),
            _master(UNITS),
            _downtime(),
            _baseline(2.0),
            _cutoff(),
            _required_equipment=lambda: _required(NEED),
        )

    try:
        plain = plan(ManualDowntime())
        lowered = plan(ManualDowntime(rows=((PROCESS, JUNE, 1.0),)))
        assert plain.manual_downtime.empty
        june = lowered.at(1.1).process_months.set_index("생산계획년월").loc[JUNE, "가용대수"]
        assert june == pytest.approx(2.0)
    finally:
        simulation_cache.get_required_shortening.clear()
        simulation_cache.get_equipment_lifecycle_spans.clear()


# ------------------------------------------------------------------ 공정 Capa 상세 ④


def _manual_bridge(values: dict[int, float]) -> pd.DataFrame:
    """캔버스 시험의 설비 일정(`_dynamic`)에 입력 비가동 칸만 덧입힌 전월 대비."""
    bridge = _dynamic().bridge.copy()
    entered = bridge["생산계획년월"].map(lambda month: values.get(int(month), 0.0))
    bridge["입력 비가동"] = entered.astype("float64")
    bridge["입력 비가동 반영"] = [
        min(value, float(total)) for value, total in zip(entered, bridge["가용대수"], strict=True)
    ]
    return bridge


def test_the_fourth_section_gets_the_input_row_only_when_there_is_input() -> None:
    plain = _canvas(dynamic=_dynamic())
    assert ROW_MANUAL_DOWNTIME not in plain.row_ids

    first, second = CANVAS_MONTHS[1], CANVAS_MONTHS[3]
    bridge = _manual_bridge({first: 1.5, second: 2.0})
    # 둘째 칸은 가용보다 크게 넣은 것으로 둔다(반영이 입력보다 작다).
    bridge.loc[bridge["생산계획년월"].eq(second), "입력 비가동 반영"] = 0.5
    canvas = _canvas(dynamic=_dynamic(bridge=bridge))
    ids = list(canvas.row_ids)
    assert ids[ids.index("title:downtime") + 1] == ROW_MANUAL_DOWNTIME
    texts = _row_texts(canvas, ROW_MANUAL_DOWNTIME)
    assert texts[1][0] == "1.5"
    assert texts[3][0] == "2⚠"
    assert texts[3][1] != texts[1][1]  # 넘친 칸은 경고색이다
    assert 0 not in texts  # 빈 달은 비운다
    hovers = {
        int(data[CUSTOMDATA_MONTH]): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == ROW_MANUAL_DOWNTIME
    }
    assert "가용에서 1.5 뺌" in hovers[first]
    assert "0 에서 멈췄습니다" in hovers[second]
    assert "Preference" in _label_hovers(canvas)[ROW_MANUAL_DOWNTIME]
    assert MANUAL_DOWNTIME_ROW_LABEL == "월별 비가동 대수(입력)"


def test_the_input_row_hover_writes_the_removed_share_like_the_available_hover() -> None:
    """④ 첫 줄 칸 풍선의 뺀 몫은 작은 몫도 0 이 아니게, ② 가용 칸 풍선과 같은 수로 적는다.

    2026-10-27 E2E — 0.04 를 넣으면 ④ 가 「입력 비가동 0.04대 — 가용에서 0.0 뺌」, 같은 달 ② 가용이
    「입력 비가동 −0.04 반영」 이었다. 넘치지 않은 달은 뺀 몫 = 넣은 대수라 ④ 의 두 수가 같은
    글이고(1.25 를 「1.2 뺌」 으로 적으면 덜 뺀 것처럼 읽힌다), 넘친 달의 작은 몫(가용 0.003 만
    남음)도 0 이 아니게 적는다.
    """
    entered = {CANVAS_MONTHS[0]: 0.01, CANVAS_MONTHS[1]: 0.04, CANVAS_MONTHS[2]: 1.25}
    overdrawn = CANVAS_MONTHS[3]
    bridge = _manual_bridge({**entered, overdrawn: 2.0})
    bridge.loc[bridge["생산계획년월"].eq(overdrawn), "입력 비가동 반영"] = 0.003
    canvas = _canvas(dynamic=_dynamic(bridge=bridge))
    hovers = {
        (str(data[CUSTOMDATA_ROW]), int(data[CUSTOMDATA_MONTH])): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
    }
    removed = {CANVAS_MONTHS[0]: "0.01", CANVAS_MONTHS[1]: "0.04", CANVAS_MONTHS[2]: "1.25"}
    for month, text in removed.items():
        assert f"입력 비가동 {text}대 — 가용에서 {text} 뺌" in hovers[(ROW_MANUAL_DOWNTIME, month)]
        assert f"입력 비가동 −{text} 반영" in hovers[(ROW_DYNAMIC_AVAILABLE, month)]
    assert "입력 비가동 2대 — 가용에서 0.003 뺌" in hovers[(ROW_MANUAL_DOWNTIME, overdrawn)]
    assert "0 에서 멈췄습니다" in hovers[(ROW_MANUAL_DOWNTIME, overdrawn)]
    assert "입력 비가동 −0.003 반영" in hovers[(ROW_DYNAMIC_AVAILABLE, overdrawn)]


def test_the_bridge_hover_names_the_input_share_of_downtime() -> None:
    bridge = _dynamic().bridge.copy()
    month = CANVAS_MONTHS[2]
    bridge.loc[bridge["생산계획년월"].eq(month), "입력 비가동 증감"] = -0.5
    canvas = _canvas(dynamic=_dynamic(bridge=bridge))
    hover = next(
        str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == "dynamic_delta" and int(data[CUSTOMDATA_MONTH]) == month
    )
    assert "(입력 비가동 −0.5 포함)" in hover
