# Purpose: 공정 설비 일정의 생산월 좌표·신규 호기 줄·비가동 손실·전월 대비·판정·캐시를 고정한다.

"""공정 하나의 설비 일정(`services/process_equipment_timeline.py`)과 캐시 래퍼.

숫자는 손으로 셀 수 있게 잡았다 — Cut-off 10, 축 5~7월. W/D 구간은 5월 `(4/20, 5/21]`(31일),
6월 `(5/21, 6/20]`(30일), 7월 `(6/20, 7/21]`(31일)이고, 날짜 `d` 는 `d + 10` 의 달 칸에 선다.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_equipment_view_cache import ANCHOR, MONTHS, _fleet
from test_equipment_view_cache import _required as _fleet_required
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

from capa_simulation.services import simulation_cache
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.process_equipment_timeline import (
    ARROW_COLUMNS,
    BRIDGE_COLUMNS,
    EXIT_UNIT_COLUMNS,
    MISSING_CUTOFF,
    NEW_UNIT_COLUMNS,
    NO_COUNTED_UNITS,
    NO_EQUIPMENT,
    NO_SNAPSHOT,
    READY,
    ROW_NEW,
    ROW_SHORTENED,
    ROW_VIRTUAL,
    UNIT_EVENT_COLUMNS,
    UNIT_MONTH_COLUMNS,
    ProcessEquipmentTimeline,
    build_process_equipment_timeline,
    dynamic_readiness,
    new_unit_availability,
    production_position,
    unit_events,
)
from capa_simulation.services.required_shortening import (
    MonthlyTarget,
    ShorteningPlan,
    plan_required_shortening,
)
from capa_simulation.services.wd_window import wd_window

JULY = 202607
AXIS = (MAY, JUNE, JULY)


def _timeline(
    rows: list[dict[str, Any]],
    downtime: pd.DataFrame | None = None,
    *,
    baseline: float = 0.0,
    months: tuple[int, ...] = AXIS,
) -> ProcessEquipmentTimeline:
    return build_process_equipment_timeline(
        _master(rows),
        _downtime() if downtime is None else downtime,
        _baseline(baseline),
        _cutoff(),
        process=PROCESS,
        months=months,
    )


def _plan(
    rows: list[dict[str, Any]],
    need: dict[int, float],
    downtime: pd.DataFrame | None = None,
    *,
    baseline: float = 0.0,
    level: float = 1.0,
) -> ShorteningPlan:
    return plan_required_shortening(
        equipment=_master(rows),
        downtime=_downtime() if downtime is None else downtime,
        baseline=_baseline(baseline),
        cutoff=_cutoff(),
        required_equipment=_required(need),
        months=sorted(need),
        today=EARLY,
        levels=(level,),
    )


def _x(day: date, months: tuple[int, ...] = AXIS) -> float:
    return production_position(day, 10, months).x


# ---------------------------------------------------------------------- 생산월 좌표


@pytest.mark.parametrize("cutoff_days", [0, 10, 15, 34, 61, 90.7])
def test_the_production_position_is_the_wd_window_that_holds_the_day(cutoff_days: float) -> None:
    """2026~2028 의 모든 W/D 구간의 모든 날이 그 구간의 달 칸에, 구간 첫날부터 차례로 선다.

    칸 안 위치는 `(구간 안 몇째 날 - 1) / 구간일수` 다 — 구간 첫날이 칸의 왼쪽 끝이다. 축 앞뒤의
    날은 0 과 달 수로 잘리고 앞·뒤를 알린다.
    """
    months = tuple(year * 100 + month for year in (2026, 2027, 2028) for month in range(1, 13))
    for index, month in enumerate(months):
        window = wd_window(month, cutoff_days)
        for offset in range(window.days):
            day = window.first_day + timedelta(days=offset)
            position = production_position(day, cutoff_days, months)
            assert position.month == month
            assert not position.before and not position.after
            assert position.x == pytest.approx(index + offset / window.days)
    first = wd_window(months[0], cutoff_days)
    last = wd_window(months[-1], cutoff_days)
    before = production_position(first.boundary_start, cutoff_days, months)
    after = production_position(last.boundary_end + timedelta(days=1), cutoff_days, months)
    assert (before.x, before.before, before.after) == (0.0, True, False)
    assert (after.x, after.before, after.after) == (float(len(months)), False, True)


def test_a_qual_on_the_25th_stands_in_the_next_months_cell_with_cutoff_10() -> None:
    """범례 예 — Cut-off 10 이면 10/25 Qual 의 기여 시작(10/26)은 11월 칸 5일째(11/05)에 선다."""
    months = (202610, 202611, 202612)
    position = production_position(date(2026, 10, 26), 10, months)
    assert position.month == 202611
    assert position.x == pytest.approx(1 + 4 / 30)
    assert calendar.monthrange(2026, 11)[1] == 30


def test_a_gap_month_in_the_axis_goes_to_the_next_cells_left_edge() -> None:
    position = production_position(date(2026, 5, 25), 10, (MAY, JULY))
    assert position.month == JUNE
    assert (position.x, position.before, position.after) == (1.0, False, False)


# ---------------------------------------------------------------------- Dynamic 판정


def test_the_readiness_checks_snapshot_then_name_then_cutoff_then_counted_units() -> None:
    """처음 걸린 까닭 하나를 돌려준다 — 저장본 → 이름 → Cut-off → HBM·EDP 차례.

    설비도 Cut-off 도 없는 공정은 「설비 없음」이다 — Cut-off 를 적어도 열리지 않기 때문이다.
    """
    counted = _master([_unit("EQ1", date(2026, 5, 1))])
    general = _master([_unit("GEN1", date(2026, 5, 1), attributes={"사용기준": "범용"})])
    no_baseline = _baseline(0.0).iloc[0:0]

    missing = dynamic_readiness(None, _baseline(3.0), _cutoff(), process=PROCESS)
    assert missing.status == NO_SNAPSHOT
    assert missing.badge == "설비 일정 없음: 저장본 없음"
    assert not missing.ready

    no_cutoff = dynamic_readiness(counted, None, None, process=PROCESS)
    assert (no_cutoff.status, no_cutoff.cutoff_days, no_cutoff.has_units) == (
        MISSING_CUTOFF,
        None,
        True,
    )
    other_cutoff = _cutoff(process="Mold")
    assert dynamic_readiness(counted, None, other_cutoff, process=PROCESS).status == MISSING_CUTOFF
    baseline_only = dynamic_readiness(_master([]), _baseline(2.0), None, process=PROCESS)
    assert (baseline_only.status, baseline_only.has_baseline) == (MISSING_CUTOFF, True)

    nothing = dynamic_readiness(counted, no_baseline, None, process="Mold")
    assert nothing.status == NO_EQUIPMENT
    assert nothing.badge == "설비 일정 없음: 설비 없음"
    assert dynamic_readiness(counted, no_baseline, other_cutoff, process="Mold").status == (
        NO_EQUIPMENT
    )

    # 이름은 앞뒤 공백만 뗀다 — 대소문자가 다르면 다른 공정이다(Cut-off 가 있든 없든).
    renamed = _master([_unit("EQ1", date(2026, 5, 1), process="die attach")])
    assert dynamic_readiness(renamed, no_baseline, _cutoff(), process=PROCESS).status == (
        NO_EQUIPMENT
    )
    assert dynamic_readiness(renamed, no_baseline, None, process=PROCESS).status == NO_EQUIPMENT
    spaced = _master([_unit("EQ1", date(2026, 5, 1), process=f" {PROCESS} ")])
    assert dynamic_readiness(spaced, no_baseline, _cutoff(), process=PROCESS).ready

    not_counted = dynamic_readiness(general, no_baseline, _cutoff(), process=PROCESS)
    assert not_counted.status == NO_COUNTED_UNITS
    assert not_counted.badge == "설비 일정 없음: HBM·EDP 호기 없음"
    assert not_counted.detail

    ready = dynamic_readiness(counted, no_baseline, _cutoff(10.9), process=PROCESS)
    assert (ready.status, ready.cutoff_days, ready.has_units, ready.has_baseline) == (
        READY,
        10,
        True,
        False,
    )
    assert ready.badge == "설비 일정 참고"
    assert ready.reason == "" and ready.detail == ""


def test_a_baseline_only_process_is_ready_without_unit_rows() -> None:
    """기존보유만 있으면 ② 만 선다 — 판정은 통과하고 호기는 없다."""
    general = _master([_unit("GEN1", date(2026, 5, 1), attributes={"사용기준": "범용"})])
    readiness = dynamic_readiness(general, _baseline(4.0), _cutoff(), process=PROCESS)
    assert (readiness.status, readiness.has_units, readiness.has_baseline) == (READY, False, True)

    empty = dynamic_readiness(_master([]), _baseline(4.0), _cutoff(), process=PROCESS)
    assert (empty.status, empty.has_units) == (READY, False)


def test_the_readiness_reason_matches_the_plans_split_of_unmatched_processes() -> None:
    """같은 입력이면 판정의 까닭이 필요 단축 일정 계획의 갈래와 맞는다.

    「Cut-off 미기재」 = `missing_cutoff`(설비나 기존보유는 있고 Cut-off 가 없는 공정),
    「설비 없음」 = 그 밖의 `required_only`(Cut-off 가 있든 없든), 통과 = 맞댄 공정. 탭과 새
    페이지가 같은 공정에 서로 다른 까닭을 말하지 않게 한다.
    """
    master = _master(
        [
            _unit("EQ1", date(2026, 5, 1)),
            _unit("WB1", date(2026, 5, 1), process="Wire Bond"),
        ]
    )
    baseline = _baseline(2.0, process="Plate")
    cutoff = prepare_process_cutoff(
        pd.DataFrame({"공정": [PROCESS, "Saw"], "Cutoff일수": [10.0, 10.0], "비고": [None, None]})
    )
    processes = (PROCESS, "Wire Bond", "Plate", "Mold", "Saw")
    plan = plan_required_shortening(
        equipment=master,
        downtime=_downtime(),
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=pd.concat(
            [_required({MAY: 1.0}, process=process) for process in processes], ignore_index=True
        ),
        months=[MAY],
        today=EARLY,
        levels=(1.0,),
    )
    status = {
        process: dynamic_readiness(master, baseline, cutoff, process=process).status
        for process in processes
    }

    assert status == {
        PROCESS: READY,
        "Wire Bond": MISSING_CUTOFF,
        "Plate": MISSING_CUTOFF,
        "Mold": NO_EQUIPMENT,
        "Saw": NO_EQUIPMENT,
    }
    assert set(plan.processes) == {name for name, found in status.items() if found == READY}
    assert set(plan.missing_cutoff) == {
        name for name, found in status.items() if found == MISSING_CUTOFF
    }
    assert set(plan.required_only) - set(plan.missing_cutoff) == {
        name for name, found in status.items() if found == NO_EQUIPMENT
    }


# ---------------------------------------------------------------------- 신규 호기 줄


def _new_unit_fixture() -> tuple[list[dict[str, Any]], dict[int, float]]:
    """7월이 모자라 축 뒤의 LATE1 을 바닥(6/20)까지 당기고 추가1 을 더하는 공정.

    7월 가용 = OLD1 1 + EARLY1 1 + EQ1 1 + G1(0.5 x 2) 1 + EQ2(7/1 반출 → 6/21~6/30) 10/31.
    소요 6 이면 1 + 21/31 이 모자란다 — LATE1(8/20)이 31일을 덮고 추가1 이 21일(6/30 Qual)을 덮는다.
    """
    rows = [
        _unit("OLD1", date(2026, 1, 10), arrival=date(2026, 1, 1), existing="Y"),
        _unit("ST1", date(2026, 5, 10), storage="Y"),
        _unit("GEN1", date(2026, 5, 10), attributes={"사용기준": "범용"}),
        _unit("EARLY1", date(2026, 3, 1), arrival=date(2026, 2, 1), confirmation="완료"),
        _unit("EQ1", date(2026, 6, 5), arrival=date(2026, 5, 1), confirmation="완료"),
        _unit("EQ2", date(2026, 5, 15), removal=date(2026, 7, 1)),
        _unit("M2", date(2026, 6, 20), ratio=0.5, parent="G1", attributes={"Model": "BOND-Y"}),
        _unit("M1", date(2026, 6, 10), ratio=0.5, parent="G1", attributes={"Model": "BOND-X"}),
        _unit("LATE1", date(2026, 8, 20), arrival=date(2026, 8, 1)),
    ]
    return rows, {MAY: 1.0, JUNE: 1.0, JULY: 6.0}


def test_new_unit_rows_take_one_line_per_unit_key_with_the_latest_module_qual() -> None:
    """대상은 기존 N·보관 N·HBM·EDP·Qual 있음이다 — 확정 「완료」와 정지 예정도 든다.

    모듈 묶음은 한 줄이고 Qual 은 가장 늦은 모듈(6/20), 모듈별 Qual 은 풍선용 튜플이다.
    """
    rows, _ = _new_unit_fixture()
    new_units = _timeline(rows).new_units

    assert tuple(new_units.columns) == NEW_UNIT_COLUMNS
    assert list(new_units["호기"]) == ["EARLY1", "EQ2", "EQ1", "G1", "LATE1"]
    assert list(new_units["축 안"]) == [False, True, True, True, False]
    group = new_units.set_index("호기").loc["G1"]
    assert group["설비명"] == "M1, M2"
    assert group["모듈 수"] == 2
    assert group["Qual일정"] == date(2026, 6, 20)
    assert group["기여 시작"] == date(2026, 6, 21)
    assert group["Model"] == "BOND-X, BOND-Y"
    assert group["모듈별 Qual"] == (("M1", date(2026, 6, 10)), ("M2", date(2026, 6, 20)))
    leaving = new_units.set_index("호기").loc["EQ2"]
    assert (leaving["반출이설일"], leaving["반출이설구분"]) == (date(2026, 7, 1), "정지")


def test_unit_events_put_shortened_then_new_then_virtual_rows() -> None:
    """차례 — 단축 대상(계획 차례) → 나머지 신규(기여 시작 순) → 추가N.

    LATE1 은 기여 시작(8/21)이 축 뒤지만 계획이 6/20 으로 당겨 줄에 선다 — 반입(8/1)보다 이른 목표라
    「반입 전」이다. 기여 시작이 축 앞인 EARLY1 은 줄이 없다.
    """
    rows, need = _new_unit_fixture()
    timeline = _timeline(rows)
    plan = _plan(rows, need)
    events = unit_events(timeline, plan.at(1.0).units)

    assert tuple(events.columns) == UNIT_EVENT_COLUMNS
    assert list(events["줄"]) == [ROW_SHORTENED, ROW_NEW, ROW_NEW, ROW_NEW, ROW_VIRTUAL]
    assert list(events["호기"]) == ["LATE1", "EQ2", "EQ1", "G1", "추가1"]
    by_unit = events.set_index("호기")

    late = by_unit.loc["LATE1"]
    assert late["목표 Qual"] == date(2026, 6, 20)
    assert late["목표 기여 시작"] == date(2026, 6, 21)
    assert late["단축일수"] == 61
    assert bool(late["반입 전"]) is True
    assert bool(late["기여 시작 축 밖"]) is True
    assert late["기여 시작 위치"] == 3.0
    assert late["목표 기여 위치"] == pytest.approx(2.0)
    assert late["대상 월"] == JULY
    assert late["해소 기여 월"] == (JULY,)
    assert late["반입 위치"] == 3.0

    leaving = by_unit.loc["EQ2"]
    assert leaving["반출이설 위치"] == pytest.approx(_x(date(2026, 7, 1)))
    assert leaving["반출이설 위치"] == pytest.approx(2 + 10 / 31)
    assert pd.isna(leaving["목표 기여 위치"])
    assert bool(leaving["반입 전"]) is False
    assert by_unit.loc["EQ1", "Qual상태"] == "완료"
    assert by_unit.loc["EQ1", "기여 시작 위치"] == pytest.approx(1 + 15 / 30)
    # 반입도 다음 날 좌표다 — 5/1 반입은 x(5/2) = 5월 칸 12째 날.
    assert by_unit.loc["EQ1", "반입 위치"] == pytest.approx(11 / 31)

    virtual = by_unit.loc["추가1"]
    assert virtual["목표 Qual"] == date(2026, 6, 30)
    assert virtual["목표 기여 위치"] == pytest.approx(2 + 10 / 31)
    assert pd.isna(virtual["기여 시작 위치"])
    assert virtual["모듈 수"] == 1
    assert virtual["늘어난 환산대수"] == pytest.approx(21 / 31)


def test_the_arrival_marker_stands_on_the_day_after_like_the_engine() -> None:
    """반입은 「다음 날부터」 좌표다 — 5월 구간 끝날(5/21) 반입은 6월 칸 왼쪽 끝 x(5/22)에 선다.

    당일 좌표면 5월 칸(30/31)에 서서 표지가 앉은 칸과 가용이 바뀐 칸이 갈린다.
    """
    timeline = _timeline([_unit("N1", date(2026, 6, 10), arrival=date(2026, 5, 21))])
    events = unit_events(timeline, pd.DataFrame())

    assert list(events["호기"]) == ["N1"]
    arrival = events.set_index("호기").loc["N1", "반입 위치"]
    assert arrival == pytest.approx(_x(date(2026, 5, 22))) == pytest.approx(1.0)
    assert arrival != pytest.approx(_x(date(2026, 5, 21)))


def test_a_shortened_row_takes_qual_and_modules_from_the_plan_when_the_group_splits() -> None:
    """묶음 G 의 M1 은 정지 예정(9/1)이라 단축 후보에서 빠지고 M2(6/20)만 당긴다.

    단축 줄의 기존 Qual·기여 시작·모듈 수는 계획의 것(6/20·6/21·1모듈)이라 ●→◀ 길이가 단축일수와
    같다. 묶음의 가장 늦은 Qual(M1 7/15)로 그리면 81일 선에 「−55일」이 붙는다. 갈린 모듈은 모듈별
    Qual 이 보이고, 정지일정은 묶음의 것이다.
    """
    rows = [
        _unit("M1", date(2026, 7, 15), ratio=0.5, parent="G", removal=date(2026, 9, 1)),
        _unit("M2", date(2026, 6, 20), ratio=0.5, parent="G"),
    ]
    need = {MAY: 1.0, JUNE: 1.0, JULY: 1.0}
    plan_units = _plan(rows, need, baseline=0.6).at(1.0).units
    planned = plan_units.set_index("호기").loc["G"]
    assert (planned["구분"], planned["기존 Qual"], planned["모듈 수"]) == (
        "단축",
        date(2026, 6, 20),
        1,
    )

    events = unit_events(_timeline(rows, baseline=0.6), plan_units)
    assert list(events["줄"]) == [ROW_SHORTENED]
    row = events.set_index("호기").loc["G"]
    assert (row["Qual일정"], row["기여 시작"], row["모듈 수"]) == (
        date(2026, 6, 20),
        date(2026, 6, 21),
        1,
    )
    assert (row["기여 시작"] - row["목표 기여 시작"]).days == row["단축일수"] == planned["단축일수"]
    assert row["모듈별 Qual"] == (("M1", date(2026, 7, 15)), ("M2", date(2026, 6, 20)))
    assert (row["반출이설일"], row["반출이설구분"]) == (date(2026, 9, 1), "정지")


def test_unit_events_ignore_other_processes_in_the_plan() -> None:
    rows, need = _new_unit_fixture()
    timeline = _timeline(rows)
    units = _plan(rows, need).at(1.0).units
    other = units.assign(공정="Mold")
    assert list(unit_events(timeline, other)["줄"]) == [ROW_NEW, ROW_NEW, ROW_NEW]
    no_cutoff = build_process_equipment_timeline(
        _master(rows),
        _downtime(),
        _baseline(0.0),
        _cutoff(process="Mold"),
        process=PROCESS,
        months=AXIS,
    )
    assert no_cutoff.cutoff_days is None
    assert unit_events(no_cutoff, units).empty
    assert no_cutoff.bridge.empty and no_cutoff.arrows.empty and no_cutoff.new_units.empty
    assert no_cutoff.exits.empty


def test_units_leaving_inside_the_axis_without_a_new_unit_row_are_listed() -> None:
    """③ 에 줄이 없는 호기의 축 안 반출·이설 — 기존 Y 호기(GONE), 축 앞에 Qual 을 마친 호기(EARLY1).

    ③ 에 선 신규 호기(EQ2, 기여 시작 축 안)는 그 줄에 ▼ 가 서므로 빼고, 축 뒤 반출(LATER)·보관(ST1)·
    사용기준 제외(GEN1)도 뺀다. 전월 대비의 `반출이설` 이 이 호기들에서 온다.
    """
    rows = [
        _old("GONE", existing="Y", removal=date(2026, 6, 10)),
        _unit("EARLY1", date(2026, 3, 1), arrival=date(2026, 2, 1), relocation=date(2026, 7, 5)),
        _unit("EQ2", date(2026, 5, 15), removal=date(2026, 7, 1)),
        _old("LATER", existing="Y", removal=date(2026, 9, 1)),
        _old("ST1", storage="Y", removal=date(2026, 6, 1)),
        _old("GEN1", existing="Y", removal=date(2026, 6, 1), attributes={"사용기준": "범용"}),
    ]
    timeline = _timeline(rows)
    exits = timeline.exits

    assert tuple(exits.columns) == EXIT_UNIT_COLUMNS
    assert list(exits["호기"]) == ["GONE", "EARLY1"]
    by_unit = exits.set_index("호기")
    gone = by_unit.loc["GONE"]
    assert (gone["반출이설일"], gone["반출이설구분"], gone["기존설비여부"]) == (
        date(2026, 6, 10),
        "정지",
        "Y",
    )
    # 반출은 당일 좌표 — 6/10 은 6/20 의 6월 칸 20째 날.
    assert gone["반출이설 위치"] == pytest.approx(1 + 19 / 30)
    assert (by_unit.loc["EARLY1", "반출이설구분"], by_unit.loc["EARLY1", "기존설비여부"]) == (
        "반출/이설",
        "N",
    )
    assert "EQ2" in set(timeline.new_units.loc[timeline.new_units["축 안"], "호기"])
    bridge = timeline.bridge.set_index("생산계획년월")
    assert list(bridge.loc[[JUNE, JULY], "반출이설"] < 0) == [True, True]


def test_a_same_day_stop_and_exit_is_a_stop_across_modules_and_an_exit_within_a_row() -> None:
    """같은 날이면 정지가 먼저다 — 모듈 A 정지·모듈 B 반출/이설이 같은 날인 묶음의 ▼ 는 개편
    전(정지 = 옛 반출)처럼 「정지」다(글자 차례면 「반출/이설」이 앞선다). 한 행에 두 날짜가 같은
    날이면 그 행은 그날 바로 반출/이설 완료라 「반출/이설」이다."""
    gone, qual, arrival = date(2026, 7, 5), date(2026, 3, 1), date(2026, 2, 1)
    rows = [
        _unit("MA", qual, arrival=arrival, ratio=0.5, parent="M", removal=gone),
        _unit("MB", qual, arrival=arrival, ratio=0.5, parent="M", relocation=gone),
        _unit("SAME", qual, arrival=arrival, removal=gone, relocation=gone),
    ]

    exits = _timeline(rows).exits.set_index("호기")

    assert (exits.loc["M", "반출이설일"], exits.loc["M", "반출이설구분"]) == (gone, "정지")
    assert (exits.loc["SAME", "반출이설일"], exits.loc["SAME", "반출이설구분"]) == (
        gone,
        "반출/이설",
    )


# ---------------------------------------------------------------------- 비가동 화살표·손실


def _old(name: str, **kwargs: Any) -> dict[str, Any]:
    """축 내내 가용인 호기(1월 Qual 완료)."""
    return _unit(name, date(2026, 1, 10), arrival=date(2026, 1, 1), confirmation="완료", **kwargs)


def _arrow_fixture() -> tuple[list[dict[str, Any]], pd.DataFrame]:
    rows = [
        _old("OLD1"),
        _old("OLD2"),
        _old("OLD3"),
        _old("OLD4", removal=date(2026, 6, 10)),
        _old("GA", ratio=0.5, parent="G"),
        _old("GB", ratio=0.5, parent="G"),
        _old("OLD5"),
        _unit("SET1", date(2026, 6, 25), arrival=date(2026, 5, 1)),
        _unit("ST1", date(2026, 3, 1), arrival=date(2026, 2, 1), storage="Y"),
    ]
    downtime = _downtime(
        [
            ("OLD1", date(2026, 6, 1), date(2026, 6, 5)),
            ("OLD2", date(2026, 7, 10), None),
            ("OLD3", date(2026, 4, 1), date(2026, 4, 25)),
            ("OLD4", date(2026, 6, 5), date(2026, 6, 30)),
            ("GA", date(2026, 6, 1), date(2026, 6, 2)),
            ("OLD5", date(2026, 8, 1), date(2026, 8, 5)),
            ("OLD5", date(2026, 3, 1), date(2026, 3, 10)),
            ("SET1", date(2026, 5, 10), date(2026, 5, 20)),
            ("ST1", date(2026, 5, 10), date(2026, 5, 20)),
        ]
    )
    return rows, downtime


def _arrow(arrows: pd.DataFrame, unit: str, start: date) -> dict[str, Any]:
    """(설비명, 시작일) 로 화살표 한 행."""
    found = [
        {str(key): value for key, value in row.items()}
        for row in arrows.to_dict("records")
        if row["설비명"] == unit and row["시작일"] == start
    ]
    assert len(found) == 1
    return found[0]


def test_each_downtime_row_becomes_an_arrow_from_the_next_day_to_the_day_after_its_end() -> None:
    """꼬리 x(시작 + 1), 촉 x(종료 + 2) — 손실 기여일 `[시작 + 1, 종료 + 1]` 을 덮는다.

    OLD1 6/1~6/5 는 6/2~6/6 의 5일(6월 칸 12~16째 날)을 깎아 5/30 대다.
    """
    rows, downtime = _arrow_fixture()
    arrows = _timeline(rows, downtime).arrows

    assert tuple(arrows.columns) == ARROW_COLUMNS
    first = _arrow(arrows, "OLD1", date(2026, 6, 1))
    assert first["꼬리 위치"] == pytest.approx(1 + 11 / 30)
    assert first["촉 위치"] == pytest.approx(1 + 16 / 30)
    assert first["덮는 날 수"] == 5
    assert first["손실 기여일수"] == 5
    assert first["손실 환산대수"] == pytest.approx(5 / 30)
    assert first["달별 손실"] == ((JUNE, pytest.approx(5 / 30)),)
    assert first["손실 최대 월"] == JUNE
    assert bool(first["가용 감소"]) is True
    assert bool(first["열린 구간"]) is False and bool(first["이전부터"]) is False


def test_open_early_exit_module_and_idle_arrows() -> None:
    """열린 구간은 축 끝까지, 축 앞에서 시작한 것은 0 부터, 반출 뒤 날은 손실이 아니다.

    - OLD2 7/10~(열림): 7/11~7/21 의 11일, 촉은 축 끝(3).
    - OLD3 4/1~4/25: 4/2~4/26 가운데 축 안(4/21~)의 6일, 꼬리 0·「이전부터」.
    - OLD4 6/5~6/30, 6/10 반출: 화살표는 6/6~7/1 의 26일을 덮지만 깎은 것은 반출 전 6/6~6/9 의 4일.
    - GA(모듈, 환산비 0.5) 6/1~6/2: 2일 x 0.5 / 30, 행은 묶음 G(2모듈).
    - SET1(셋업 중)·ST1(보관)은 가용이 아니던 날이라 깎은 것이 없다 — 흐린 화살표.
    - OLD5 의 축 밖 두 줄은 화살표가 없다.
    """
    rows, downtime = _arrow_fixture()
    arrows = _timeline(rows, downtime).arrows

    opened = _arrow(arrows, "OLD2", date(2026, 7, 10))
    assert bool(opened["열린 구간"]) is True
    assert opened["촉 위치"] == 3.0
    assert opened["덮는 날 수"] == 11
    assert opened["손실 환산대수"] == pytest.approx(11 / 31)

    early = _arrow(arrows, "OLD3", date(2026, 4, 1))
    assert bool(early["이전부터"]) is True
    assert early["꼬리 위치"] == 0.0
    assert early["덮는 날 수"] == 6
    assert early["손실 기여일수"] == 6
    assert early["첫 달"] == MAY

    leaving = _arrow(arrows, "OLD4", date(2026, 6, 5))
    assert leaving["덮는 날 수"] == 26
    assert leaving["손실 기여일수"] == 4
    assert leaving["달별 손실"] == ((JUNE, pytest.approx(4 / 30)), (JULY, 0.0))

    module = _arrow(arrows, "GA", date(2026, 6, 1))
    assert (module["설비키"], module["모듈 수"]) == ("G", 2)
    assert module["손실 환산대수"] == pytest.approx(2 * 0.5 / 30)

    for name in ("SET1", "ST1"):
        idle = _arrow(arrows, name, date(2026, 5, 10))
        assert bool(idle["가용 감소"]) is False
        assert idle["손실 환산대수"] == 0.0
        assert pd.isna(idle["손실 최대 월"])
    assert "OLD5" not in set(arrows["설비명"])

    # 가용을 깎은 호기가 앞 — 호기마다 첫 손실 비가동의 시작일 차례(같은 날이면 번호 있는 OLD1 이
    # 번호 없는 묶음 G 앞), 흐린 호기는 뒤.
    assert list(arrows["설비명"]) == [
        "OLD3",
        "OLD1",
        "GA",
        "OLD4",
        "OLD2",
        "SET1",
        "ST1",
    ]


def test_arrow_days_equal_the_contribution_days_each_unit_lost() -> None:
    """불변식 — 화살표 행들이 깎은 기여일수의 합 = 그 호기의 (비가동 없음 - 실제) 기여일수.

    축 내내 가용인 호기로 축 안에 닫힌 비가동이면 그 화살표가 덮는 날 수도 그 차이와 같다.
    """
    rows, downtime = _arrow_fixture()
    timeline = _timeline(rows, downtime)
    lost = timeline.unit_months.groupby("설비명")["손실 기여일수"].sum()
    by_arrow = timeline.arrows.groupby("설비명")["손실 기여일수"].sum()

    assert tuple(timeline.unit_months.columns) == UNIT_MONTH_COLUMNS
    for unit, days in by_arrow.items():
        assert lost.get(unit, 0) == days
    assert set(lost[lost > 0].index) == set(by_arrow[by_arrow > 0].index)
    covered = timeline.arrows.set_index("설비명").loc["OLD1", "덮는 날 수"]
    assert covered == lost["OLD1"] == 5
    weighted = timeline.unit_months.groupby("설비명")["손실 환산대수"].sum()
    by_arrow_weighted = timeline.arrows.groupby("설비명")["손실 환산대수"].sum()
    for unit, value in by_arrow_weighted.items():
        assert weighted.get(unit, 0.0) == pytest.approx(value)


def test_overlapping_downtime_rows_of_one_unit_count_each_lost_day_once() -> None:
    """같은 호기의 비가동 행이 겹치면 겹친 날은 시작일이 이른 행의 몫이다 — 행들의 합 = 호기 손실.

    OLD1 6/1~6/10·6/5~6/15·6/7~6/9(표 차례는 뒤섞음)는 손실 기여일 6/2~6/16 의 15일을 깎는다.
    앞 행이 6/2~6/11 의 10일, 둘째 행이 겹치지 않은 6/12~6/16 의 5일, 셋째 행은 0 이라 흐린
    화살표다. 덮는 날 수는 행마다 그대로다(10·11·3).
    """
    downtime = _downtime(
        [
            ("OLD1", date(2026, 6, 5), date(2026, 6, 15)),
            ("OLD1", date(2026, 6, 7), date(2026, 6, 9)),
            ("OLD1", date(2026, 6, 1), date(2026, 6, 10)),
        ]
    )
    timeline = _timeline([_old("OLD1")], downtime)
    arrows = timeline.arrows

    assert list(arrows["시작일"]) == [date(2026, 6, 1), date(2026, 6, 5), date(2026, 6, 7)]
    assert list(arrows["덮는 날 수"]) == [10, 11, 3]
    assert list(arrows["손실 기여일수"]) == [10, 5, 0]
    assert list(arrows["손실 환산대수"]) == pytest.approx([10 / 30, 5 / 30, 0.0])
    assert list(arrows["가용 감소"]) == [True, True, False]
    assert timeline.unit_months["손실 기여일수"].sum() == arrows["손실 기여일수"].sum() == 15
    assert timeline.unit_months["손실 환산대수"].sum() == pytest.approx(
        arrows["손실 환산대수"].sum()
    )
    june = timeline.bridge.set_index("생산계획년월").loc[JUNE]
    assert june["비가동"] == pytest.approx(-arrows["손실 환산대수"].sum())


# ---------------------------------------------------------------------- 전월 대비·계획과 맞대기


def test_the_bridge_total_is_the_plans_availability_and_splits_the_monthly_change() -> None:
    """불변식 — 기존보유 + 호기 가용 = 계획의 가용대수(같은 달), 전월대비 = 신규 + 비가동 + 반출.

    6월: OLD4 가 6/10 반출로 7월에 빠지고, OLD1·GA 의 비가동이 6월에 깎고 7월에 풀린다.
    """
    rows, downtime = _arrow_fixture()
    timeline = _timeline(rows, downtime, baseline=3.0)
    plan = _plan(rows, {MAY: 5.0, JUNE: 5.0, JULY: 5.0}, downtime, baseline=3.0)
    bridge = timeline.bridge

    assert tuple(bridge.columns) == BRIDGE_COLUMNS
    assert list(bridge["가용대수"]) == pytest.approx(list(plan.at(1.0).process_months["가용대수"]))
    assert list(bridge["기존보유"]) == [3.0, 3.0, 3.0]
    assert bridge["전월대비"].isna().iloc[0]
    later = bridge.iloc[1:]
    assert list(later["전월대비"]) == pytest.approx(
        list(later["신규"] + later["비가동"] + later["반출이설"])
    )
    july = bridge.set_index("생산계획년월").loc[JULY]
    # OLD4 는 6월 구간에 6/9 까지 19일 → 7월 0 — 반사실로 19/30 이 빠진다.
    assert july["반출이설"] == pytest.approx(-19 / 30)
    # 6월 손실(OLD1 5 + GA 2 x 0.5 + OLD4 4)/30 이 풀리고 7월 손실 OLD2 11/31 이 생긴다.
    assert july["비가동"] == pytest.approx((5 + 1 + 4) / 30 - 11 / 31)
    # SET1(6/25 Qual)이 6/26 부터 7월 구간 26일을 보탠다.
    assert july["신규"] == pytest.approx(26 / 31)
    assert timeline.baseline_units == 3.0


def test_steady_units_count_units_fully_available_all_axis_long() -> None:
    """④ 의 「변동 없는 가용 호기 k대」 — 축의 모든 날 가용인 설비키(모듈은 묶음 전체)."""
    rows, downtime = _arrow_fixture()
    # 가용 내내: OLD5(축 밖 비가동뿐)·GB 는 있지만 묶음 G 는 GA 가 깎였다. OLD1~4 는 깎였다.
    assert _timeline(rows, downtime).steady_units == 1
    assert _timeline(rows).steady_units == 5  # 비가동이 없으면 OLD1~3·OLD5·G(OLD4 는 반출).


def test_the_sample_fleet_meets_both_invariants_for_every_process() -> None:
    """합성 fleet(여섯 공정, 비가동·반출·이설·보관·사용기준 제외 섞임)에서 두 불변식이 모두 선다."""
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    plan = plan_required_shortening(
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=_fleet_required(processes, MONTHS),
        months=MONTHS,
        today=ANCHOR,
        levels=(MonthlyTarget(1.095),),
    )
    months = plan.at(MonthlyTarget(1.095)).process_months
    for process in processes:
        timeline = build_process_equipment_timeline(
            equipment, downtime, baseline, cutoff, process=process, months=MONTHS
        )
        expected = months.loc[months["공정"].eq(process), "가용대수"]
        assert list(timeline.bridge["가용대수"]) == pytest.approx(list(expected))
        lost = timeline.unit_months.groupby("설비명")["손실 기여일수"].sum()
        for unit, days in timeline.arrows.groupby("설비명")["손실 기여일수"].sum().items():
            assert lost.get(unit, 0) == days


def test_the_process_slice_of_an_all_process_plan_is_the_single_process_plan() -> None:
    """공정끼리 따로 계산하므로 전 공정 계획을 한 공정으로 고른 것 = 그 공정만으로 세운 계획이다."""
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    required = _fleet_required(processes, MONTHS)
    target = MonthlyTarget(1.095, ((MONTHS[-1], 1.2),))
    process = processes[0]

    def planned(
        master: pd.DataFrame, stops: pd.DataFrame, held: pd.DataFrame, need: pd.DataFrame
    ) -> ShorteningPlan:
        return plan_required_shortening(
            equipment=master,
            downtime=stops,
            baseline=held,
            cutoff=cutoff,
            required_equipment=need,
            months=MONTHS,
            today=ANCHOR,
            levels=(target,),
        )

    everything = planned(equipment, downtime, baseline, required).at(target)
    own = equipment["공정소분류"].astype(str).eq(process)
    alone = planned(
        equipment.loc[own].reset_index(drop=True),
        downtime.loc[downtime["설비명"].isin(equipment.loc[own, "설비명"])].reset_index(drop=True),
        baseline.loc[baseline["공정"].eq(process)].reset_index(drop=True),
        required.loc[required["공정"].eq(process)].reset_index(drop=True),
    ).at(target)

    sliced = everything.process_months.loc[everything.process_months["공정"].eq(process)]
    assert_frame_equal(sliced.reset_index(drop=True), alone.process_months)
    units = everything.units.loc[everything.units["공정"].eq(process)]
    assert_frame_equal(units.reset_index(drop=True), alone.units.reset_index(drop=True))


# ---------------------------------------------------------------------- 캐시 래퍼


def test_the_timeline_cache_keys_by_inputs_not_today_and_matches_a_fresh_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """키는 네 표의 내용 지문 + 달 + 공정이다. 오늘은 들지 않는다 — 필요 단축 일정 키로 낸 키와
    같다.

    적중하면 다시 만들지 않고, 비가동 한 줄이 바뀌면 새로 만든다. 공용 구간 캐시는 쓰지 않는다.
    """
    simulation_cache.get_process_equipment_timeline.clear()
    equipment, downtime, baseline, cutoff = _fleet()
    process = "Final Test"

    def refuse(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("설비 일정은 공용 구간 캐시를 쓰지 않는다")

    monkeypatch.setattr(simulation_cache, "get_equipment_lifecycle_spans", refuse)
    built: list[str] = []

    def counting(*args: Any, **kwargs: Any) -> ProcessEquipmentTimeline:
        built.append(str(kwargs["process"]))
        return build_process_equipment_timeline(*args, **kwargs)

    monkeypatch.setattr(simulation_cache, "build_process_equipment_timeline", counting)

    def cached(stops: pd.DataFrame) -> tuple[Any, ProcessEquipmentTimeline]:
        key = simulation_cache.process_equipment_timeline_cache_key(
            equipment=equipment,
            downtime=stops,
            baseline=baseline,
            cutoff=cutoff,
            months=MONTHS,
            process=process,
        )
        return key, simulation_cache.get_process_equipment_timeline(
            key, equipment, stops, baseline, cutoff
        )

    key, first = cached(downtime)
    again_key, again = cached(downtime)
    assert again_key == key
    assert built == [process]

    for day in (ANCHOR, ANCHOR + timedelta(days=40)):
        shortening_key = simulation_cache.required_shortening_cache_key(
            (1, "token", MONTHS[0], MONTHS[-1]),
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=cutoff,
            months=MONTHS,
            today=day,
        )
        assert simulation_cache.process_timeline_key_from_shortening(shortening_key, process) == key

    fresh = build_process_equipment_timeline(
        equipment, downtime, baseline, cutoff, process=process, months=MONTHS
    )
    for cached_frame, fresh_frame in (
        (again.bridge, fresh.bridge),
        (again.arrows, fresh.arrows),
        (again.new_units, fresh.new_units),
        (again.unit_months, fresh.unit_months),
    ):
        assert_frame_equal(cached_frame, fresh_frame)

    fewer = downtime.loc[downtime["설비명"].ne("SAMPLE-C23F-08")].reset_index(drop=True)
    other_key, other = cached(fewer)
    assert other_key != key
    assert built == [process, process]
    assert len(other.arrows) == len(first.arrows) - 1


def test_the_timeline_cache_key_moves_with_every_input() -> None:
    """마스터 한 칸·비가동 한 줄·기존보유·Cut-off·달·공정 — 하나씩 바꾸면 키가 모두 서로 다르다.

    키 튜플에서 원소 하나가 빠지면 그 입력이 바뀌어도 낡은 설비 일정이 적중한다.
    """
    equipment, downtime, baseline, cutoff = _fleet()
    process = "Final Test"
    first_row = equipment.index == equipment.index[0]
    moved_master = equipment.assign(Model=equipment["Model"].mask(first_row, "MOVED-MODEL"))
    more_baseline = baseline.assign(기존보유대수=baseline["기존보유대수"] + 1)
    later_cutoff = prepare_process_cutoff(
        cutoff.assign(Cutoff일수=cutoff["Cutoff일수"].where(cutoff["공정"].ne(process), 30.0))
    )
    other_process = sorted(set(equipment["공정소분류"].astype(str)) - {process})[0]
    variants: dict[str, dict[str, Any]] = {
        "기준": {},
        "마스터": {"equipment": moved_master},
        "비가동": {"downtime": downtime.iloc[1:].reset_index(drop=True)},
        "기존보유": {"baseline": more_baseline},
        "Cut-off": {"cutoff": later_cutoff},
        "달": {"months": MONTHS[:-1]},
        "공정": {"process": other_process},
    }
    keys = {}
    for name, changes in variants.items():
        arguments: dict[str, Any] = {
            "equipment": equipment,
            "downtime": downtime,
            "baseline": baseline,
            "cutoff": cutoff,
            "months": MONTHS,
            "process": process,
        }
        arguments.update(changes)
        keys[name] = simulation_cache.process_equipment_timeline_cache_key(**arguments)
    assert len(set(keys.values())) == len(variants), keys


def test_a_cutoff_change_moves_the_cells_and_the_key() -> None:
    """Cut-off 가 바뀌면 키가 갈리고 표지가 다른 칸에 선다 — 생산월 좌표가 Cut-off 를 본다."""
    equipment, downtime, baseline, cutoff = _fleet()
    process = "Final Test"
    later = prepare_process_cutoff(
        cutoff.assign(Cutoff일수=cutoff["Cutoff일수"].where(cutoff["공정"].ne(process), 30.0))
    )
    keys = {
        simulation_cache.process_equipment_timeline_cache_key(
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=table,
            months=MONTHS,
            process=process,
        )
        for table in (cutoff, later)
    }
    assert len(keys) == 2
    near = build_process_equipment_timeline(
        equipment, downtime, baseline, cutoff, process=process, months=MONTHS
    )
    far = build_process_equipment_timeline(
        equipment, downtime, baseline, later, process=process, months=MONTHS
    )
    assert (near.cutoff_days, far.cutoff_days) == (10, 30)
    assert list(near.arrows["꼬리 위치"]) != list(far.arrows["꼬리 위치"])


# ------------------------------------------------------------------ 기준일 이후 신규 몫(제약
# 시뮬레이션)


def test_new_unit_availability_keeps_units_starting_on_or_after_the_reference_day() -> None:
    """기준일 6/12 — 기여 시작 6/21 인 G1(묶음은 가장 늦은 모듈)과 축 뒤 LATE1 만 신규다.

    몫은 모듈마다 — M1(Qual 6/10, 환산 0.5)은 6월 구간 6/11~6/20 10일 → 0.5 × 10/30 = 1/6, M2(Qual
    6/20)는 6월 0. 7월은 둘 다 온 달 0.5 + 0.5 = 1.0. LATE1(8/21)은 축 뒤라 0 이다.
    EQ1(6/6)·EQ2(5/16)· EARLY1(3/2)·OLD1(기존 Y)·ST1(보관)·GEN1(범용)은 신규가 아니다.
    """
    rows, _ = _new_unit_fixture()
    shares = new_unit_availability(_timeline(rows), since=date(2026, 6, 12))
    assert shares.since == date(2026, 6, 12)
    assert shares.units == ("G1", "LATE1")
    assert shares.in_axis == 1
    assert shares.before == 0.0
    assert [month for month, _ in shares.months] == list(AXIS)
    assert [value for _, value in shares.months] == pytest.approx([0.0, 1 / 6, 1.0])
    assert shares.by_month() == dict(shares.months)


@pytest.mark.parametrize(
    ("since", "units", "june", "july"),
    [
        (date(2026, 6, 21), ("G1", "LATE1"), 1 / 6, 1.0),
        (date(2026, 6, 22), ("LATE1",), 0.0, 0.0),
    ],
)
def test_the_reference_day_itself_counts_as_after(
    since: date, units: tuple[str, ...], june: float, july: float
) -> None:
    """「이후」 는 그날을 넣는다 — G1 기여 시작(6/21)이 기준일이면 들고 하루 뒤면 빠진다."""
    rows, _ = _new_unit_fixture()
    shares = new_unit_availability(_timeline(rows), since=since)
    assert shares.units == units
    assert [value for _, value in shares.months] == pytest.approx([0.0, june, july])


def test_the_share_before_the_axis_counts_units_that_came_earlier() -> None:
    """기준일 3/1 — EARLY1(3/2)·EQ2(5/16)·EQ1(6/6)·G1(6/21)·LATE1 이 신규다.

    5월 = EARLY1 1 + EQ2 5/16~5/21 6일 → 6/31. 6월 = EARLY1 1 + EQ2 1 + EQ1 6/6~6/20 15/30 + M1 1/6.
    7월 = EARLY1 1 + EQ2 6/21~6/30 10/31(7/1 정지 당일부터 빠짐) + EQ1 1 + G1 1.0. 축 앞 4월 구간
    (3/21, 4/20] 은 EARLY1 이 온 달(5월 행의 환산비 1 × 30/30)이고 EQ2 는 겹치지 않는다 — before
    1.0. 그래서 EARLY1 은 5월에 새로 붙은 신규가 아니다(기간 전에 들어온 신규).
    """
    rows, _ = _new_unit_fixture()
    shares = new_unit_availability(_timeline(rows), since=date(2026, 3, 1))
    assert shares.units == ("EARLY1", "EQ2", "EQ1", "G1", "LATE1")
    assert shares.in_axis == 3
    assert shares.before == pytest.approx(1.0)
    assert [value for _, value in shares.months] == pytest.approx(
        [1 + 6 / 31, 2 + 15 / 30 + 1 / 6, 3 + 10 / 31]
    )


def test_a_unit_half_into_the_month_before_the_axis_counts_its_share() -> None:
    """축 앞 달 가운데 들어온 신규는 그 달 몫만 before 에 든다 — 4/5 Qual(4/6~4/20 15일) → 15/30."""
    shares = new_unit_availability(
        _timeline([_unit("N1", date(2026, 4, 5), arrival=date(2026, 3, 1))]),
        since=date(2026, 1, 1),
    )
    assert shares.before == pytest.approx(15 / 30)
    assert [value for _, value in shares.months] == pytest.approx([1.0, 1.0, 1.0])


def test_operating_downtime_does_not_change_the_new_unit_share() -> None:
    """운영 비가동은 들어온 날을 바꾸지 않는다 — 몫은 비가동 없음 환산대수다(가용대수는 준다)."""
    rows, _ = _new_unit_fixture()
    downtime = _downtime([("M1", date(2026, 7, 1), date(2026, 7, 10))])
    quiet = new_unit_availability(_timeline(rows), since=date(2026, 6, 12))
    down_timeline = _timeline(rows, downtime)
    down = new_unit_availability(down_timeline, since=date(2026, 6, 12))
    assert down.months == quiet.months
    assert down_timeline.bridge["가용대수"].iloc[2] < _timeline(rows).bridge["가용대수"].iloc[2]


def test_the_new_unit_share_stays_within_the_fleet_availability() -> None:
    """합성 fleet 모든 공정 — 아주 이른 기준일의 몫은 그 달 비가동 없는 호기 가용 이하, 아주 늦은
    기준일은 호기도 몫도 없다."""
    equipment, downtime, baseline, cutoff = _fleet()
    for process in sorted(set(equipment["공정소분류"].astype(str))):
        timeline = build_process_equipment_timeline(
            equipment, downtime, baseline, cutoff, process=process, months=MONTHS
        )
        free = timeline.unit_months.groupby("생산계획년월")["비가동 없음 환산대수"].sum()
        early = new_unit_availability(timeline, since=date(1900, 1, 1))
        for month, value in early.months:
            assert 0.0 <= value <= float(free.get(month, 0.0)) + 1e-9
        late = new_unit_availability(timeline, since=date(2999, 1, 1))
        assert late.units == ()
        assert late.before == 0.0
        assert all(value == 0.0 for _, value in late.months)
