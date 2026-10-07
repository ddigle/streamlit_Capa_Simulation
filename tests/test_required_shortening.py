# Purpose: 필요단축일정 계산의 기여일 산식·단축 차례·최소 단축·가상 호기·후보 조건을 고정한다.

"""필요단축일정(`services/required_shortening.py`).

숫자는 모두 손으로 셀 수 있게 잡았다. 기준 예 — Cut-off 10, 2026-05 W/D 구간 `(4/20, 5/21]`
31일, 첫 기여일 4/21.

- Qual 5/1 호기는 5/2 부터 기여해 `20/31 = 0.645` 대다.
- 4/20 으로 당기면 구간을 다 덮어 `+11/31 = +0.355` 대가 는다(11일 단축).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    STATUS_CARRIED,
    STATUS_EXPIRED,
    STATUS_MET,
    STATUS_SHORTENED,
    STATUS_WITH_NEW,
    TARGET_LEVELS,
    LevelPlan,
    ShorteningPlan,
    plan_required_shortening,
    shortening_candidates,
    unit_number,
)
from capa_simulation.services.securement_cross_check import dynamic_available_equipment

PROCESS = "Die Attach"
MAY = 202605
JUNE = 202606
EARLY = date(2026, 4, 1)


def _unit(
    name: str,
    qual: date | None,
    *,
    process: str = PROCESS,
    arrival: date | None = date(2026, 4, 1),
    ratio: float | None = None,
    parent: str | None = None,
    confirmation: str | None = "계획",
    existing: str = "N",
    storage: str = "N",
    removal: date | None = None,
    relocation: date | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": process,
            "공정대분류": "B/N",
            "반입일정": arrival,
            "Qual일정": qual,
            "확정상태": confirmation if qual is not None else None,
            "기존설비여부": existing,
            "보관유무": storage,
            "레이아웃표시": "N",
            "환산비": ratio,
            "Main 설비": parent,
            "반출일정": removal,
            "이설일정": relocation,
        }
    )
    return row


def _master(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS))


def _downtime(rows: list[tuple[str, date, date | None]] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        [(name, "공사", start, end, None, None) for name, start, end in rows or []],
        columns=["설비명", "비가동유형", "시작일", "종료일", "상세사유", "비고"],
    )


def _baseline(count: float, process: str = PROCESS) -> pd.DataFrame:
    return pd.DataFrame(
        {"공정": [process], "분류": ["전체"], "기존보유대수": [count], "비고": [None]}
    )


def _cutoff(days: float = 10, process: str = PROCESS) -> pd.DataFrame:
    return prepare_process_cutoff(
        pd.DataFrame({"공정": [process], "Cutoff일수": [days], "비고": [None]})
    )


def _required(values: dict[int, float], process: str = PROCESS) -> pd.DataFrame:
    # 소요대수는 STEP 단위 상세로 온다. 두 줄로 나눠 넣어 (월, 공정) 합산을 함께 본다.
    rows = []
    for month, value in values.items():
        rows.append({"생산계획년월": month, "공정": process, "STEP": "S1", "소요대수": value / 2})
        rows.append({"생산계획년월": month, "공정": process, "STEP": "S2", "소요대수": value / 2})
    return pd.DataFrame(rows)


def _plan(
    units: list[dict[str, Any]],
    required: dict[int, float],
    *,
    baseline: float = 10.0,
    today: date = EARLY,
    downtime: pd.DataFrame | None = None,
    months: list[int] | None = None,
) -> ShorteningPlan:
    return plan_required_shortening(
        equipment=_master(units),
        downtime=_downtime() if downtime is None else downtime,
        baseline=_baseline(baseline),
        cutoff=_cutoff(),
        required_equipment=_required(required),
        months=months or sorted(required),
        today=today,
    )


def _units(level: LevelPlan) -> dict[str, dict[str, Any]]:
    return {
        str(row["호기"]): {str(key): value for key, value in row.items()}
        for row in level.units.to_dict("records")
    }


def _month(level: LevelPlan, month: int) -> dict[str, Any]:
    rows = level.process_months.loc[level.process_months["생산계획년월"].eq(month)]
    assert len(rows) == 1
    return dict(rows.iloc[0])


def test_the_worked_example_pulls_each_unit_only_as_far_as_needed() -> None:
    """5월 부족 2.0 대를 A(5/1)·B(5/31)·C(6/15) 차례로 채운다.

    A 는 4/20 으로 11일 당겨 +11/31, B 는 구간 밖이라 41일 당겨 +31/31, 남은 20/31 은 C 를
    5/1 로(45일) 당겨 덮는다 — 11 + 31 + 20 = 62일 = 2 x 31.
    """
    plan = _plan(
        [
            _unit("A1", date(2026, 5, 1)),
            _unit("B2", date(2026, 5, 31)),
            _unit("C3", date(2026, 6, 15)),
        ],
        {MAY: 12 + 20 / 31},
    )
    level = plan.at(1.0)
    may = _month(level, MAY)

    assert may["가용대수"] == pytest.approx(10 + 20 / 31)
    assert may["과부족"] == pytest.approx(-2.0)
    assert may["단축후과부족"] == pytest.approx(0.0)
    assert may["상태"] == STATUS_SHORTENED

    units = _units(level)
    assert units["A1"]["목표 Qual"] == date(2026, 4, 20)
    assert units["A1"]["기여 시작"] == date(2026, 4, 21)
    assert units["A1"]["단축일수"] == 11
    assert units["A1"]["늘어난 환산대수"] == pytest.approx(11 / 31)
    assert round(units["A1"]["늘어난 환산대수"], 3) == 0.355
    assert units["B2"]["목표 Qual"] == date(2026, 4, 20)
    assert units["B2"]["단축일수"] == 41
    assert units["B2"]["늘어난 환산대수"] == pytest.approx(1.0)
    assert units["C3"]["목표 Qual"] == date(2026, 5, 1)
    assert units["C3"]["단축일수"] == 45
    assert units["C3"]["늘어난 환산대수"] == pytest.approx(20 / 31)
    assert set(level.units["구분"]) == {KIND_SHORTENED}
    assert units["A1"]["대상 월"] == MAY
    assert units["A1"]["해소 기여 월"] == str(MAY)


def test_the_unit_already_counted_matches_the_dynamic_availability() -> None:
    """가용은 Static/Dynamic 탭의 환산 소계와 같은 길이다. A 의 5/2 부터의 20일이 이미 들어 있다."""
    units = _master([_unit("A1", date(2026, 5, 1))])
    plan = _plan([_unit("A1", date(2026, 5, 1))], {MAY: 11.0})
    from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans

    spans = build_equipment_lifecycle_spans(
        units,
        _downtime(),
        start_date=date(2026, 4, 21),
        end_date=date(2026, 5, 21),
        with_unit_share=True,
    )
    monthly = build_monthly_equipment_availability(spans, _baseline(10.0), _cutoff(), [MAY])
    dynamic = dynamic_available_equipment(monthly)

    assert _month(plan.at(1.0), MAY)["가용대수"] == pytest.approx(
        float(dynamic["가용대수"].iloc[0])
    )
    assert _month(plan.at(1.0), MAY)["소요대수"] == pytest.approx(11.0)


def test_a_tie_goes_to_the_lower_unit_number() -> None:
    """Qual 이 같으면 이름 끝 숫자가 작은 호기 — 글자순이면 EQ10 이 EQ9 앞에 선다."""
    plan = _plan(
        [_unit("EQ10", date(2026, 5, 10)), _unit("EQ9", date(2026, 5, 10))],
        {MAY: 10 + 22 / 31 + 1 / 31},
    )
    assert list(plan.at(1.0).units["호기"]) == ["EQ9"]
    assert unit_number("EQ10") == 10
    assert unit_number("TCB") is None


def test_the_closest_qual_after_the_window_start_goes_first() -> None:
    plan = _plan(
        [_unit("EQ1", date(2026, 5, 15)), _unit("EQ2", date(2026, 5, 5))],
        {MAY: 10 + (6 + 16) / 31 + 2 / 31},
    )
    units = _units(plan.at(1.0))
    assert list(units) == ["EQ2"]
    # 모자란 2/31 만큼, 이틀만 당긴다.
    assert units["EQ2"]["목표 Qual"] == date(2026, 5, 3)
    assert units["EQ2"]["단축일수"] == 2


def test_the_pull_is_the_minimum_whole_days() -> None:
    """2.5/31 이 모자라면 사흘을 당긴다 — 하루 단위라 모자라지 않게 올린다."""
    plan = _plan([_unit("EQ1", date(2026, 5, 10))], {MAY: 10 + 11 / 31 + 2.5 / 31})
    units = _units(plan.at(1.0))
    assert units["EQ1"]["목표 Qual"] == date(2026, 5, 7)
    assert units["EQ1"]["늘어난 환산대수"] == pytest.approx(3 / 31)


def test_today_is_the_floor_and_new_units_fill_the_rest() -> None:
    """오늘 5/5 — 4/21~5/5 는 이미 지나 당길 수 없다. 바닥은 5/5 이고 남은 16일만 셀 수 있다.

    EQ1(5/15)을 5/5 로 당겨 +10/31, 남은 21/31 은 추가1(5/5, 16/31)·추가2(5/16, 5/31)가 덮는다.
    오늘보다 Qual 이 이른 EQ0 은 후보가 아니다.
    """
    plan = _plan(
        [_unit("EQ0", date(2026, 5, 3)), _unit("EQ1", date(2026, 5, 15))],
        {MAY: 10 + 18 / 31 + 6 / 31 + 1.0},
        today=date(2026, 5, 5),
    )
    level = plan.at(1.0)
    units = _units(level)
    assert units["EQ1"]["목표 Qual"] == date(2026, 5, 5)
    assert units["EQ1"]["늘어난 환산대수"] == pytest.approx(10 / 31)
    assert "EQ0" not in units
    assert units["추가1"]["구분"] == KIND_NEW
    assert units["추가1"]["목표 Qual"] == date(2026, 5, 5)
    assert units["추가1"]["늘어난 환산대수"] == pytest.approx(16 / 31)
    assert units["추가2"]["목표 Qual"] == date(2026, 5, 16)
    assert units["추가2"]["기여 시작"] == date(2026, 5, 17)
    assert units["추가2"]["늘어난 환산대수"] == pytest.approx(5 / 31)
    assert pd.isna(units["추가1"]["기존 Qual"]) and pd.isna(units["추가1"]["단축일수"])
    assert _month(level, MAY)["상태"] == STATUS_WITH_NEW
    assert _month(level, MAY)["단축후과부족"] == pytest.approx(0.0)


def test_virtual_units_take_the_latest_date_that_covers_the_need() -> None:
    """후보가 없으면 1.5 대를 추가1(4/20, 1.0)·추가2(5/5, 16/31)로 덮는다.

    15.5일은 16일로 올린다 — 하루 단위라 모자라지 않게.
    """
    plan = _plan([], {MAY: 11.5})
    units = _units(plan.at(1.0))
    assert list(units) == ["추가1", "추가2"]
    assert units["추가1"]["목표 Qual"] == date(2026, 4, 20)
    assert units["추가1"]["늘어난 환산대수"] == pytest.approx(1.0)
    assert units["추가2"]["목표 Qual"] == date(2026, 5, 5)
    assert units["추가2"]["늘어난 환산대수"] == pytest.approx(16 / 31)


def test_an_earlier_pull_carries_into_later_months() -> None:
    """5월을 위해 7/15 → 4/20 으로 당긴 호기는 6월도 채운다. 6월은 따로 당기지 않는다.

    가상 호기도 뒤 달에 남는다 — 5월에 더한 추가1 이 6월에도 한 대로 선다.
    """
    plan = _plan(
        [_unit("EQ1", date(2026, 7, 15))],
        {MAY: 12.0, JUNE: 12.0},
    )
    level = plan.at(1.0)
    units = _units(level)
    assert units["EQ1"]["목표 Qual"] == date(2026, 4, 20)
    assert units["EQ1"]["해소 기여 월"] == f"{MAY}, {JUNE}"
    assert list(units) == ["EQ1", "추가1"]
    assert _month(level, MAY)["상태"] == STATUS_WITH_NEW
    june = _month(level, JUNE)
    assert june["상태"] == STATUS_CARRIED
    assert june["단축후가용대수"] == pytest.approx(12.0)


def test_module_rows_move_together_as_one_unit() -> None:
    """APW01A(5/10)·B(5/12) 는 설비 한 대다. 4/20 으로 함께 당겨 20일·22일 x 0.5 = 21/31 이 는다."""
    plan = _plan(
        [
            _unit("APW01A", date(2026, 5, 10), ratio=0.5, parent="APW01"),
            _unit("APW01B", date(2026, 5, 12), ratio=0.5, parent="APW01"),
        ],
        {MAY: 10 + (11 + 9) * 0.5 / 31 + 21 / 31},
    )
    units = _units(plan.at(1.0))
    assert list(units) == ["APW01"]
    assert units["APW01"]["모듈 수"] == 2
    assert units["APW01"]["기존 Qual"] == date(2026, 5, 12)
    assert units["APW01"]["목표 Qual"] == date(2026, 4, 20)
    assert units["APW01"]["단축일수"] == 22
    assert units["APW01"]["늘어난 환산대수"] == pytest.approx(21 / 31)


def test_the_conversion_ratio_weights_the_gain() -> None:
    """환산비 1.5 — 0.3 대가 모자라면 6.2일, 곧 7일을 당긴다(1.5 x 7/31)."""
    plan = _plan([_unit("EQ1", date(2026, 5, 10), ratio=1.5)], {MAY: 10 + 1.5 * 11 / 31 + 0.3})
    units = _units(plan.at(1.0))
    assert units["EQ1"]["목표 Qual"] == date(2026, 5, 3)
    assert units["EQ1"]["늘어난 환산대수"] == pytest.approx(1.5 * 7 / 31)


def test_downtime_days_add_nothing_when_pulled() -> None:
    """4/25~4/30 공사(기여일 4/26~5/1)와 겹친 날은 당겨도 가용이 아니다 — 20일 중 14일만 는다."""
    plan = _plan(
        [_unit("EQ1", date(2026, 5, 10))],
        {MAY: 11.0 + 11 / 31},
        downtime=_downtime([("EQ1", date(2026, 4, 25), date(2026, 4, 30))]),
    )
    units = _units(plan.at(1.0))
    assert units["EQ1"]["목표 Qual"] == date(2026, 4, 20)
    assert units["EQ1"]["늘어난 환산대수"] == pytest.approx(14 / 31)
    assert units["추가1"]["늘어난 환산대수"] == pytest.approx(17 / 31)


def test_the_arrival_date_is_not_a_lower_bound() -> None:
    """반입 5/10 · Qual 5/15 호기도 4/20 까지 당긴다. 반입일정은 하한이 아니다."""
    plan = _plan(
        [_unit("EQ1", date(2026, 5, 15), arrival=date(2026, 5, 10))],
        {MAY: 11.0},
    )
    units = _units(plan.at(1.0))
    assert units["EQ1"]["목표 Qual"] == date(2026, 4, 20)
    assert units["EQ1"]["늘어난 환산대수"] == pytest.approx(25 / 31)


def test_a_window_already_past_is_marked_not_pulled() -> None:
    """오늘이 5월 구간 끝(5/21) 뒤면 5월은 당겨 채울 수 없다. 6월은 그대로 계산한다."""
    plan = _plan(
        [_unit("EQ1", date(2026, 6, 25))],
        {MAY: 11.0, JUNE: 10.5},
        today=date(2026, 5, 25),
    )
    level = plan.at(1.0)
    assert _month(level, MAY)["상태"] == STATUS_EXPIRED
    assert _month(level, MAY)["단축후과부족"] == pytest.approx(-1.0)
    assert _month(level, JUNE)["상태"] == STATUS_SHORTENED
    assert _units(level)["EQ1"]["대상 월"] == JUNE


def test_excluded_candidates_never_move() -> None:
    """기존·보관·완료·반출·이설·Qual 없음은 후보가 아니다."""
    rows = [
        _unit("OK1", date(2026, 5, 10)),
        _unit("EXIST1", date(2026, 5, 10), existing="Y"),
        _unit("STORE1", date(2026, 5, 10), storage="Y"),
        _unit("DONE1", date(2026, 5, 10), confirmation="완료"),
        _unit("OUT1", date(2026, 5, 10), removal=date(2026, 9, 1)),
        _unit("MOVE1", date(2026, 5, 10), relocation=date(2026, 9, 1)),
        _unit("NOQUAL1", None),
    ]
    names = [unit.unit for unit in shortening_candidates(_master(rows), _downtime())]
    assert names == ["OK1"]


def test_the_five_levels_are_computed_up_front_and_grow() -> None:
    plan = _plan([_unit("EQ1", date(2026, 6, 25))], {MAY: 10.0})
    assert [level.level for level in plan.levels] == list(TARGET_LEVELS)
    gaps = [_month(level, MAY)["과부족"] for level in plan.levels]
    assert gaps == pytest.approx([1.0, 0.0, -1.0, -2.0, -3.0])
    assert _month(plan.at(0.9), MAY)["상태"] == STATUS_MET
    assert plan.at(1.0).units.empty
    assert len(plan.at(1.3).units) > len(plan.at(1.1).units)


def test_processes_on_one_side_are_listed_not_compared() -> None:
    required = pd.concat([_required({MAY: 10.0}), _required({MAY: 5.0}, process="Mold")])
    plan = plan_required_shortening(
        equipment=_master(
            [_unit("EQ1", date(2026, 5, 10)), _unit("UF1", None, process="Underfill")]
        ),
        downtime=_downtime(),
        baseline=_baseline(10.0),
        cutoff=pd.concat([_cutoff(), _cutoff(process="Underfill")], ignore_index=True),
        required_equipment=required,
        months=[MAY],
        today=EARLY,
    )
    assert plan.processes == (PROCESS,)
    assert plan.required_only == ("Mold",)
    assert plan.availability_only == ("Underfill",)
    assert set(plan.at(1.1).process_months["공정"]) == {PROCESS}


def test_a_process_without_a_cutoff_is_named() -> None:
    required = _required({MAY: 3.0}, process="Mold")
    plan = plan_required_shortening(
        equipment=_master([_unit("MD1", date(2026, 5, 10), process="Mold")]),
        downtime=_downtime(),
        baseline=_baseline(10.0),
        cutoff=_cutoff(),
        required_equipment=required,
        months=[MAY],
        today=EARLY,
    )
    assert plan.missing_cutoff == ("Mold",)
    assert plan.processes == ()
