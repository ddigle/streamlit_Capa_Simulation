# Purpose: 필요단축일정의 기여일 산식·단축 차례·최소 단축·가상 호기·후보 조건과 CSV 표를 고정한다.

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

from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    span_date_range,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LEVEL_COLUMN,
    PROCESS_MONTH_EXPORT_COLUMNS,
    STATUS_CARRIED,
    STATUS_CARRIED_BOTH,
    STATUS_CARRIED_NEW,
    STATUS_EXPIRED,
    STATUS_MET,
    STATUS_NEW_LIMIT,
    STATUS_SHORTENED,
    STATUS_WITH_NEW,
    TARGET_LEVELS,
    UNIT_EXPORT_COLUMNS,
    LevelPlan,
    ShorteningPlan,
    plan_required_shortening,
    process_month_export_frame,
    shortening_candidates,
    unit_export_frame,
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
    attributes: dict[str, Any] | None = None,
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
            **(attributes or {}),
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


def _engine(
    rows: list[dict[str, Any]],
    downtime: pd.DataFrame,
    months: list[int],
    *,
    baseline: float = 10.0,
) -> dict[int, float]:
    """Static/Dynamic 탭과 같은 길(넓힌 구간 → 월별 안분 → 환산 소계)로 잰 Dynamic 가용."""
    master = _master(rows)
    span = span_date_range(months, _cutoff())
    assert span is not None
    spans = build_equipment_lifecycle_spans(
        master, downtime, start_date=span[0], end_date=span[1], with_unit_share=True
    )
    prepared = prepare_equipment_master(master)
    ratios = {
        str(unit): float(ratio)
        for unit, ratio in zip(prepared["설비명"], prepared["환산비"], strict=True)
    }
    monthly = build_monthly_equipment_availability(
        spans, _baseline(baseline), _cutoff(), months, conversion_ratios=ratios
    )
    dynamic = dynamic_available_equipment(monthly)
    return {
        int(month): float(value)
        for month, value in zip(dynamic["생산계획년월"], dynamic["가용대수"], strict=True)
    }


def test_the_unit_already_counted_matches_the_dynamic_availability() -> None:
    """가용은 Static/Dynamic 탭의 환산 소계와 같은 길이다. A 의 5/2 부터의 20일이 이미 들어 있다."""
    plan = _plan([_unit("A1", date(2026, 5, 1))], {MAY: 11.0})

    engine = _engine([_unit("A1", date(2026, 5, 1))], _downtime(), [MAY])
    assert _month(plan.at(1.0), MAY)["가용대수"] == pytest.approx(engine[MAY])
    assert engine[MAY] == pytest.approx(10 + 20 / 31)
    assert _month(plan.at(1.0), MAY)["소요대수"] == pytest.approx(11.0)


def test_an_always_available_unit_fills_the_first_month_exactly() -> None:
    """조회 전부터 가용인 호기는 **첫 달**에도 정확히 1대다 — 엔진도 계산도.

    호기 구간을 첫 구간의 첫날(`first_day`)부터 만들면 그 첫날의 기여를 정하는 전날 상태가 빠져
    호기마다 1/31 씩 모자랐다. 늘 가용인 30대가 29.03대로 세어지고 가짜 「추가1」이 붙었다
    (2026-10-07 리뷰). `span_date_range` 가 앞 경계부터 돌려주어 Static/Dynamic 도 함께 고쳐진다.
    """
    old = [
        _unit(f"OLD{i}", date(2026, 1, 10), arrival=date(2026, 1, 1), confirmation="완료")
        for i in range(30)
    ]
    assert _engine(old, _downtime(), [MAY, JUNE], baseline=0.0) == pytest.approx(
        {MAY: 30.0, JUNE: 30.0}
    )
    level = _plan(old, {MAY: 30.0, JUNE: 30.0}, baseline=0.0).at(1.0)
    assert _month(level, MAY)["가용대수"] == pytest.approx(30.0)
    assert _month(level, MAY)["상태"] == STATUS_MET
    assert level.units.empty


def test_the_engine_agrees_with_the_plan_once_the_quals_are_moved() -> None:
    """계획대로 Qual 을 옮기고 가상 호기를 호기로 더해 엔진에 다시 넣으면 달마다 단축 후 가용이다.

    모듈 묶음(환산비가 다른 두 모듈)·환산비 1.5·비가동이 섞인 경우다. 반입은 하한이 아니므로
    (사용자 결정) 옮긴 호기의 반입은 목표 Qual 로 당긴다 — 엔진은 반입 전을 입고 예정으로 센다.
    """
    months = [MAY, JUNE, 202607, 202608]
    rows = [
        _unit("OLD1", date(2026, 1, 10), arrival=date(2026, 1, 1)),
        _unit("U1", date(2026, 6, 15), ratio=1.5),
        _unit("M1", date(2026, 6, 10), ratio=0.5, parent="G9"),
        _unit("M2", date(2026, 7, 5), ratio=0.7, parent="G9"),
        _unit("U3", date(2026, 7, 20)),
    ]
    downtime = _downtime(
        [("U3", date(2026, 6, 1), date(2026, 6, 5)), ("U1", date(2026, 5, 10), date(2026, 5, 12))]
    )
    need = {MAY: 3.0, JUNE: 4.0, 202607: 5.0, 202608: 5.0}
    level = _plan(rows, need, baseline=0.0, downtime=downtime, months=months).at(1.0)
    statuses = [_month(level, month)["상태"] for month in months]
    assert statuses == [STATUS_SHORTENED, STATUS_SHORTENED, STATUS_WITH_NEW, STATUS_CARRIED_NEW]

    targets: dict[str, date] = {}
    moved = []
    for unit in level.units.to_dict("records"):
        target = unit["목표 Qual"]
        assert isinstance(target, date)
        if unit["구분"] == KIND_NEW:
            moved.append(_unit(str(unit["호기"]), target, arrival=target))
        else:
            targets[str(unit["호기"])] = target
    for row in rows:
        target = targets.get(str(row["Main 설비"] or row["설비명"]))
        if target is not None and row["Qual일정"] > target:
            row = {**row, "Qual일정": target, "반입일정": min(row["반입일정"], target)}
        moved.append(row)

    engine = _engine(moved, downtime, months, baseline=0.0)
    for month in months:
        assert engine[month] == pytest.approx(_month(level, month)["단축후가용대수"])
        assert engine[month] >= need[month] - 1e-9


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
    # 6월은 당긴 EQ1 과 5월의 추가1 이 함께 채운다.
    assert june["상태"] == STATUS_CARRIED_BOTH
    assert june["단축후가용대수"] == pytest.approx(12.0)


def test_a_later_month_names_what_covered_it() -> None:
    """손대지 않고 채워진 달은 앞 달의 무엇이 채웠는지 말한다 — 단축이면 단축, 가상 호기면 신규."""
    pulled = _plan([_unit("EQ1", date(2026, 7, 15))], {MAY: 11.0, JUNE: 11.0}).at(1.0)
    assert _month(pulled, JUNE)["상태"] == STATUS_CARRIED

    added = _plan([], {MAY: 11.0, JUNE: 11.0}).at(1.0)
    assert list(added.units["호기"]) == ["추가1"]
    assert _month(added, JUNE)["상태"] == STATUS_CARRIED_NEW


def test_hitting_the_new_unit_cap_rolls_that_month_back() -> None:
    """하루 남은 10월에 2.0대가 모자라면 가상 호기 62대(한 대 1/31)가 필요해 상한(50)을 넘는다.

    그 달에 더한 가상 호기는 모두 걷고 「신규로도 못 채움」으로 남은 부족을 보인다. 11월은 걷은
    뒤의 가용으로 제 가상 호기(한 대씩 온전한 1대)를 받는다 — 걷지 않으면 11월이 그 50대를 공짜로
    받아 실제 부족 10대를 가렸다(2026-10-07 리뷰).
    """
    months = [202610, 202611, 202612]
    plan = plan_required_shortening(
        equipment=_master([]),
        downtime=_downtime(),
        baseline=_baseline(4.0),
        cutoff=_cutoff(),
        required_equipment=_required({202610: 6.0, 202611: 14.0, 202612: 14.0}),
        months=months,
        today=date(2026, 10, 20),
    )
    level = plan.at(1.0)
    october = _month(level, 202610)
    assert october["상태"] == STATUS_NEW_LIMIT
    assert october["단축후가용대수"] == pytest.approx(4.0)
    assert october["단축후과부족"] == pytest.approx(-2.0)
    # 남은 것은 11월 몫 10대뿐이다(KPI 「신규 필요」 가 세는 표).
    assert len(level.units) == 10
    assert set(level.units["대상 월"]) == {202611}
    assert list(level.units["늘어난 환산대수"]) == pytest.approx([1.0] * 10)
    assert _month(level, 202611)["단축후가용대수"] == pytest.approx(14.0)
    assert _month(level, 202612)["상태"] == STATUS_CARRIED_NEW


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


# ---------------------------------------------------------------------- 내보내기(CSV 표)


def _export_rows(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        str(row["호기"]): {str(key): value for key, value in row.items()}
        for row in frame.to_dict("records")
    }


def _worked_example() -> ShorteningPlan:
    return _plan(
        [
            _unit("A1", date(2026, 5, 1)),
            _unit("B2", date(2026, 5, 31)),
            _unit("C3", date(2026, 6, 15)),
        ],
        {MAY: 12 + 20 / 31},
    )


def test_the_unit_export_has_the_user_facing_columns_in_order() -> None:
    """칸 차례는 사용자가 읽는 차례다 — 목표·공정·호기 → 마스터 속성 → 일정 → 효과 → 대상 월."""
    frame = unit_export_frame(_worked_example(), (1.0,))

    assert tuple(frame.columns) == UNIT_EXPORT_COLUMNS
    assert list(frame.columns) == [
        "목표 확보율(%)",
        "공정",
        "Cut-off(일)",
        "호기",
        "구분",
        "공정대분류",
        "공정소분류",
        "Model",
        "동",
        "층",
        "투자구분",
        "Main 설비",
        "설비명",
        "모듈 수",
        "환산비",
        "반입일정",
        "확정상태",
        "기존 Qual 완료일",
        "기존 기여 시작일",
        "목표 Qual 완료일",
        "목표 기여 시작일",
        "단축일수",
        "늘어난 환산대수",
        "대상 월",
        "대상 월 부족 대수(단축 전)",
        "대상 월 부족 대수(단축 후)",
        "해소 기여 월",
    ]
    assert list(frame["호기"]) == ["A1", "B2", "C3"]
    assert set(frame[LEVEL_COLUMN]) == {100}
    assert set(frame["Cut-off(일)"]) == {10}


def test_the_unit_export_dates_are_iso_and_contribution_starts_the_next_day() -> None:
    """기여 시작일 = Qual + 1 — 달이 넘어가도(B2 기존 Qual 5/31 → 6/1)."""
    rows = _export_rows(unit_export_frame(_worked_example(), (1.0,)))

    assert rows["A1"]["기존 Qual 완료일"] == "2026-05-01"
    assert rows["A1"]["기존 기여 시작일"] == "2026-05-02"
    assert rows["A1"]["목표 Qual 완료일"] == "2026-04-20"
    assert rows["A1"]["목표 기여 시작일"] == "2026-04-21"
    assert rows["A1"]["단축일수"] == 11
    assert rows["B2"]["기존 Qual 완료일"] == "2026-05-31"
    assert rows["B2"]["기존 기여 시작일"] == "2026-06-01"
    assert rows["B2"]["단축일수"] == 41
    # 하루씩 더한 몫의 끝자리 찌꺼기는 털어 낸다(1.0 이 0.9999999999999993 으로 남지 않게).
    assert rows["B2"]["늘어난 환산대수"] == 1.0
    assert rows["C3"]["늘어난 환산대수"] == pytest.approx(20 / 31)
    assert rows["A1"]["대상 월"] == "2026-05"
    assert rows["A1"]["해소 기여 월"] == "2026-05"


def test_the_unit_export_shows_the_target_months_shortage_before_and_after() -> None:
    """5월 과부족 -2.0 → 부족 대수 단축 전 2.0, 단축 후 0(그 목표의 모든 단축을 반영한 뒤)."""
    rows = _export_rows(unit_export_frame(_worked_example(), (1.0,)))

    for name in ("A1", "B2", "C3"):
        assert rows[name]["대상 월 부족 대수(단축 전)"] == pytest.approx(2.0)
        assert rows[name]["대상 월 부족 대수(단축 후)"] == 0.0


def test_the_shortage_after_stays_when_the_new_unit_cap_rolls_back() -> None:
    """하루 남은 10월 — EQ1 을 바닥(10/20)까지 당겨도 1/31 만 늘고 가상 호기는 상한을 넘어 걷힌다.

    호기 줄의 단축 후 부족은 그 달에 남은 부족(2 - 1/31)이다.
    """
    plan = plan_required_shortening(
        equipment=_master([_unit("EQ1", date(2026, 11, 30))]),
        downtime=_downtime(),
        baseline=_baseline(4.0),
        cutoff=_cutoff(),
        required_equipment=_required({202610: 6.0}),
        months=[202610],
        today=date(2026, 10, 20),
    )
    assert _month(plan.at(1.0), 202610)["상태"] == STATUS_NEW_LIMIT
    rows = _export_rows(unit_export_frame(plan, (1.0,)))

    assert list(rows) == ["EQ1"]
    assert rows["EQ1"]["목표 Qual 완료일"] == "2026-10-20"
    assert rows["EQ1"]["대상 월"] == "2026-10"
    assert rows["EQ1"]["대상 월 부족 대수(단축 전)"] == pytest.approx(2.0)
    assert rows["EQ1"]["대상 월 부족 대수(단축 후)"] == pytest.approx(2 - 1 / 31)


def test_a_module_group_exports_the_groups_shared_attributes() -> None:
    """모듈 묶음은 한 줄이다 — 설비명은 모듈 행을 잇고, 환산비는 모듈 합, 반입일정은 가장 늦은 모듈.

    묶음 안에서 같게 막힌 값(공정대분류·동·층·투자구분)은 그대로, 갈리는 글자(Model·확정상태)는
    서로 다른 값을 모듈 차례로 잇는다.
    """
    shared = {"동": "C2", "층": "3F", "투자구분": "신규투자"}
    plan = _plan(
        [
            _unit(
                "APW01A",
                date(2026, 5, 10),
                ratio=0.5,
                parent="APW01",
                arrival=date(2026, 4, 1),
                attributes={**shared, "Model": "BOND-X"},
            ),
            _unit(
                "APW01B",
                date(2026, 5, 12),
                ratio=0.5,
                parent="APW01",
                arrival=date(2026, 4, 3),
                confirmation="확정",
                attributes={**shared, "Model": "BOND-Y"},
            ),
        ],
        {MAY: 10 + (11 + 9) * 0.5 / 31 + 21 / 31},
    )
    rows = _export_rows(unit_export_frame(plan, (1.0,)))

    assert list(rows) == ["APW01"]
    unit = rows["APW01"]
    assert unit["설비명"] == "APW01A, APW01B"
    assert unit["Main 설비"] == "APW01"
    assert unit["모듈 수"] == 2
    assert unit["환산비"] == pytest.approx(1.0)
    assert unit["공정대분류"] == "B/N"
    assert unit["공정소분류"] == PROCESS
    assert (unit["동"], unit["층"], unit["투자구분"]) == ("C2", "3F", "신규투자")
    assert unit["Model"] == "BOND-X, BOND-Y"
    assert unit["확정상태"] == "계획, 확정"
    assert unit["반입일정"] == "2026-04-03"
    # 묶음 Qual 은 가장 늦은 모듈(5/12)이다.
    assert unit["기존 Qual 완료일"] == "2026-05-12"
    assert unit["목표 Qual 완료일"] == "2026-04-20"
    assert unit["단축일수"] == 22


def test_a_single_unit_exports_its_own_master_row() -> None:
    plan = _plan(
        [
            _unit(
                "EQ7",
                date(2026, 5, 10),
                ratio=1.5,
                arrival=date(2026, 4, 2),
                attributes={"Model": "DA-9", "동": "C1", "층": "2F", "투자구분": "증설"},
            )
        ],
        {MAY: 10 + 1.5 * 11 / 31 + 0.3},
    )
    unit = _export_rows(unit_export_frame(plan, (1.0,)))["EQ7"]

    assert unit["설비명"] == "EQ7"
    assert pd.isna(unit["Main 설비"])
    assert unit["모듈 수"] == 1
    assert unit["환산비"] == pytest.approx(1.5)
    assert (unit["Model"], unit["동"], unit["층"]) == ("DA-9", "C1", "2F")
    assert unit["투자구분"] == "증설"
    assert unit["반입일정"] == "2026-04-02"
    assert unit["확정상태"] == "계획"


def test_virtual_units_export_blank_master_attributes_and_original_dates() -> None:
    """「추가N」은 마스터에 없는 호기다 — 속성·기존 일정·단축일수는 빈칸, 목표 일정·효과만 있다."""
    plan = _plan([], {MAY: 11.5})
    frame = unit_export_frame(plan, (1.0,))
    rows = _export_rows(frame)

    assert list(rows) == ["추가1", "추가2"]
    virtual = rows["추가2"]
    assert virtual["구분"] == KIND_NEW
    for column in (
        "공정대분류",
        "공정소분류",
        "Model",
        "동",
        "층",
        "투자구분",
        "Main 설비",
        "설비명",
        "모듈 수",
        "환산비",
        "반입일정",
        "확정상태",
        "기존 Qual 완료일",
        "기존 기여 시작일",
        "단축일수",
    ):
        assert pd.isna(virtual[column]), column
    assert virtual["목표 Qual 완료일"] == "2026-05-05"
    assert virtual["목표 기여 시작일"] == "2026-05-06"
    assert virtual["늘어난 환산대수"] == pytest.approx(16 / 31)
    assert virtual["대상 월"] == "2026-05"
    assert virtual["대상 월 부족 대수(단축 전)"] == pytest.approx(1.5)
    assert virtual["대상 월 부족 대수(단축 후)"] == 0.0
    # 빈칸은 CSV 에서 빈 칸이다(`<NA>`·`nan` 글자가 아니다).
    csv = frame.to_csv(index=False)
    assert "<NA>" not in csv and "nan" not in csv.lower()


def test_the_month_list_carries_into_later_months_as_iso_months() -> None:
    plan = _plan([_unit("EQ1", date(2026, 7, 15))], {MAY: 12.0, JUNE: 12.0})
    rows = _export_rows(unit_export_frame(plan, (1.0,)))

    assert rows["EQ1"]["해소 기여 월"] == "2026-05, 2026-06"


def test_all_levels_export_stacks_five_level_blocks() -> None:
    """목표 다섯을 한 파일로 — 목표마다 블록이고, 블록은 그 목표 하나만 낸 표와 같다."""
    plan = _plan(
        [_unit("EQ1", date(2026, 6, 25)), _unit("EQ2", date(2026, 7, 10))],
        {MAY: 12.0},
    )
    frame = unit_export_frame(plan, TARGET_LEVELS)

    assert tuple(frame.columns) == UNIT_EXPORT_COLUMNS
    assert list(dict.fromkeys(frame[LEVEL_COLUMN])) == [90, 100, 110, 120, 130]
    assert len(frame) == sum(len(plan.at(level).units) for level in TARGET_LEVELS)
    blocks = [unit_export_frame(plan, (level,)) for level in TARGET_LEVELS]
    pd.testing.assert_frame_equal(frame, pd.concat(blocks, ignore_index=True))
    for level, block in zip(TARGET_LEVELS, blocks, strict=True):
        assert set(block[LEVEL_COLUMN]) == {round(level * 100)}
        assert len(block) == len(plan.at(level).units) > 0


def test_the_exports_follow_the_given_process_order_and_scope() -> None:
    """공정은 넘긴 차례(화면의 표시순서)이고 넘기지 않은 공정은 빠진다.

    공정·월 표에는 목표 칸이 앞에 붙고 목표마다 블록이다.
    """
    required = pd.concat([_required({MAY: 12.0}), _required({MAY: 6.0}, process="Mold")])
    plan = plan_required_shortening(
        equipment=_master(
            [_unit("EQ1", date(2026, 6, 25)), _unit("MD1", date(2026, 6, 20), process="Mold")]
        ),
        downtime=_downtime(),
        baseline=pd.concat([_baseline(10.0), _baseline(5.0, process="Mold")], ignore_index=True),
        cutoff=pd.concat([_cutoff(), _cutoff(process="Mold")], ignore_index=True),
        required_equipment=required,
        months=[MAY],
        today=EARLY,
    )
    assert plan.processes == (PROCESS, "Mold")

    ordered = unit_export_frame(plan, (1.0,), ["Mold", PROCESS])
    assert list(dict.fromkeys(ordered["공정"])) == ["Mold", PROCESS]
    only_mold = unit_export_frame(plan, (1.0,), ["Mold"])
    assert set(only_mold["공정"]) == {"Mold"}

    months = process_month_export_frame(plan, (1.0, 1.1), ["Mold", PROCESS], [MAY])
    assert tuple(months.columns) == PROCESS_MONTH_EXPORT_COLUMNS
    assert list(months.columns[:2]) == [LEVEL_COLUMN, "공정"]
    assert list(zip(months[LEVEL_COLUMN], months["공정"], strict=True)) == [
        (100, "Mold"),
        (100, PROCESS),
        (110, "Mold"),
        (110, PROCESS),
    ]
    assert process_month_export_frame(plan, (1.0,), ["Mold"], [JUNE]).empty
