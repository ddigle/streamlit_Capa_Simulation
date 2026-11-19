# Purpose: 필요 단축 일정 Static 기준의 역산 · 두 기준 계획의 숫자 · 기준 키 칸을 고정한다.

"""필요 단축 일정 「현재 일정」 Static 기준(`services/static_qual_schedule.py`).

초안(2026-11-19) 2장 합성 예시 — 공정 `DEMO-A`, Cut-off 10일, 오늘 2026-11-19, 목표 110%, 고정 2대,
역산할
호기 `U1`~`U6`. 같은 호기 · 같은 소요인데 Static 기준은 3대 · 합 38일, 설비 마스터 기준은 5대 · 합
145일을 당기라고 나온다(부록 B 와 같은 숫자).

기준은 계획 키의 끝 칸이다(기본 설비 마스터 — 공정 Capa 상세 · 제약 시뮬레이션의 키는 그대로).
Static
역산은 어느 기준 · 가정 토큰의 키로 불러도 한 칸이고, Static 기준 계획은 활성 시나리오의 Static
가용대수가 있어야 한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

import capa_simulation.services.simulation_cache as simulation_cache
import capa_simulation.services.static_qual_schedule as static_qual_schedule
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.qual_deadline import (
    QualDeadlineInput,
    QualMonthInput,
    compute_qual_deadlines,
)
from capa_simulation.services.required_shortening import (
    BASIS_COLUMN,
    KIND_SHORTENED,
    ShorteningPlan,
    plan_required_shortening,
    process_month_export_frame,
    unit_export_frame,
)
from capa_simulation.services.static_qual_schedule import (
    BASIS_MASTER,
    BASIS_STATIC,
    ReverseUnit,
    StaticQualSchedule,
    build_static_qual_schedule,
    reverse_static_schedule,
    reverse_targets,
)

PROCESS = "DEMO-A"
TODAY = date(2026, 11, 19)
JAN, FEB, MAR = 202701, 202702, 202703
MONTHS = [JAN, FEB, MAR]
MASTER_QUALS = {
    "U1": date(2026, 12, 10),
    "U2": date(2027, 1, 25),
    "U3": date(2027, 2, 10),
    "U4": date(2027, 3, 5),
    "U5": date(2027, 3, 25),
    "U6": date(2027, 4, 15),
}


def _unit(
    name: str,
    qual: date | None,
    *,
    process: str = PROCESS,
    arrival: date | None = date(2026, 11, 1),
    ratio: float | None = None,
    parent: str | None = None,
    confirmation: str | None = "계획",
    existing: str = "N",
    actual: date | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": process,
            "공정대분류": "B/N",
            "사용기준": "HBM",
            "반입일정": arrival,
            "Qual일정": qual,
            "Qual실적": actual,
            "Qual상태": confirmation if qual is not None else None,
            "기존설비여부": existing,
            "보관유무": "N",
            "레이아웃표시": "N",
            "환산비": ratio,
            "Main 설비": parent,
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


def _cutoff(days: float = 10, processes: tuple[str, ...] = (PROCESS,)) -> pd.DataFrame:
    return prepare_process_cutoff(
        pd.DataFrame(
            {
                "공정": list(processes),
                "Cutoff일수": [days] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )


def _static(values: dict[int, float], process: str = PROCESS) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": list(values),
            "공정": [process] * len(values),
            "가용대수": list(values.values()),
        }
    )


def _required(values: dict[int, float], process: str = PROCESS) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": list(values),
            "공정": [process] * len(values),
            "소요대수": list(values.values()),
        }
    )


def _example_units(names: tuple[str, ...] = tuple(MASTER_QUALS)) -> list[dict[str, Any]]:
    extra = {"U7": date(2027, 5, 10), "U8": date(2027, 6, 10)}
    return [_unit(name, MASTER_QUALS.get(name) or extra[name]) for name in names]


def _plans(
    units: list[dict[str, Any]],
    *,
    required: dict[int, float],
    static: dict[int, float],
    baseline: pd.DataFrame | None = None,
    downtime: pd.DataFrame | None = None,
    level: float = 1.1,
) -> tuple[ShorteningPlan, ShorteningPlan, StaticQualSchedule]:
    equipment = _master(units)
    stops = _downtime() if downtime is None else downtime
    held = _baseline(2.0) if baseline is None else baseline
    schedule = build_static_qual_schedule(
        equipment=equipment,
        downtime=stops,
        baseline=held,
        cutoff=_cutoff(),
        static_availability=_static(static),
        months=MONTHS,
        today=TODAY,
    )
    common: dict[str, Any] = {
        "equipment": equipment,
        "downtime": stops,
        "baseline": held,
        "cutoff": _cutoff(),
        "required_equipment": _required(required),
        "months": MONTHS,
        "today": TODAY,
        "levels": (level,),
    }
    static_plan = plan_required_shortening(**common, basis=BASIS_STATIC, static_schedule=schedule)
    master_plan = plan_required_shortening(**common)
    return static_plan, master_plan, schedule


def _pulled(plan: ShorteningPlan, level: float = 1.1) -> list[tuple[str, date | None, date, int]]:
    units = plan.at(level).units
    return [
        (str(row["호기"]), row["기존 Qual"], row["목표 Qual"], row["단축일수"])
        for row in units.to_dict("records")
    ]


# ---------------------------------------------------------------- 역산 = 계산기


def _calculator_case(
    base: float, targets: list[float | None], count: int, cutoff: int
) -> tuple[StaticQualSchedule, Any]:
    names = [f"U{index + 1}" for index in range(count)]
    months = [202701 + index for index in range(12)]
    units = [ReverseUnit(PROCESS, name, ((name, 1.0),), date(2027, 1, 1), None) for name in names]
    schedule = reverse_static_schedule(
        units=units,
        fixed={(PROCESS, month): base for month in months},
        static={
            (PROCESS, month): value
            for month, value in zip(months, targets, strict=True)
            if value is not None
        },
        cutoff_days={PROCESS: cutoff},
        months=months,
        today=TODAY,
    )
    calculator = compute_qual_deadlines(
        QualDeadlineInput(
            cutoff_days=cutoff,
            year=2027,
            base_units=base,
            today=TODAY,
            months=(
                QualMonthInput(targets[0], " ".join(names)),
                *(QualMonthInput(value, "") for value in targets[1:]),
            ),
        )
    )
    return schedule, calculator


@pytest.mark.parametrize(
    ("base", "targets", "count", "cutoff"),
    [
        (2.0, [3.0, 4.5, 8.0, None, None, None, None, None, None, None, None, None], 6, 10),
        (18.0, [18, 19, 20, 20.5, 22, 22, 24, 24, 25, 26, 26, 27], 9, 10),
        (0.0, [0.3, 1.7, 2.2, 2.25, 4.9, 5.0, None, 6.1, 6.1, 7.4, 8.0, 9.9], 12, 23),
        (5.0, [5.5, 5.2, 7.0, 6.0, 9.75, 9.75, 10.01, 12, 12, 12, 12, 14], 7, 0),
    ],
)
def test_ratio_one_reverse_gives_the_calculator_deadlines_and_parts(
    base: float, targets: list[float | None], count: int, cutoff: int
) -> None:
    schedule, calculator = _calculator_case(base, targets, count, cutoff)

    assert [
        (item.unit, item.month % 100, item.deadline, round(item.part, 9))
        for item in schedule.assignments
    ] == [
        (unit.name, unit.month, unit.deadline, round(unit.part, 9)) for unit in calculator.assigned
    ]
    assert [unit.unit for unit in schedule.leftovers] == [unit.name for unit in calculator.leftover]
    assert [round(check.shortfall, 9) for check in schedule.checks] == [
        round(check.shortfall, 9) for check in calculator.checks
    ]


def test_example_reverse_matches_the_draft_dates() -> None:
    schedule, _ = _calculator_case(2.0, [3.0, 4.5, 8.0, *[None] * 9], 6, 10)

    assert {item.unit: item.deadline for item in schedule.assignments} == {
        "U1": date(2026, 12, 21),
        "U2": date(2027, 1, 21),
        "U3": date(2027, 2, 4),
        "U4": date(2027, 2, 18),
        "U5": date(2027, 2, 18),
        "U6": date(2027, 2, 18),
    }


# ---------------------------------------------------------------- 부록 B — 두 기준의 계획


def test_static_basis_pulls_three_units_38_days_master_basis_five_units_145_days() -> None:
    static_plan, master_plan, _ = _plans(
        _example_units(),
        required={JAN: 3.0, FEB: 5.0, MAR: 7.0},
        static={JAN: 3.0, FEB: 4.5, MAR: 8.0},
    )

    assert _pulled(static_plan) == [
        ("U2", date(2027, 1, 21), date(2027, 1, 11), 10),
        ("U3", date(2027, 2, 4), date(2027, 1, 21), 14),
        ("U4", date(2027, 2, 18), date(2027, 2, 4), 14),
    ]
    assert sum(days for *_, days in _pulled(static_plan)) == 38
    assert _pulled(master_plan) == [
        ("U2", date(2027, 1, 25), date(2027, 1, 11), 14),
        ("U3", date(2027, 2, 10), date(2027, 1, 21), 20),
        ("U4", date(2027, 3, 5), date(2027, 2, 4), 29),
        ("U5", date(2027, 3, 25), date(2027, 2, 18), 35),
        ("U6", date(2027, 4, 15), date(2027, 2, 27), 47),
    ]
    assert sum(days for *_, days in _pulled(master_plan)) == 145
    static_months = static_plan.at(1.1).process_months
    master_months = master_plan.at(1.1).process_months
    assert static_months["가용대수"].round(3).tolist() == [3.0, 4.5, 8.0]
    assert master_months["가용대수"].round(3).tolist() == [3.0, 4.143, 5.516]
    assert static_months["단축후가용대수"].round(3).tolist() == [3.323, 5.5, 8.0]
    assert master_months["단축후가용대수"].round(3).tolist() == [3.323, 5.5, 7.71]
    assert static_plan.basis == BASIS_STATIC
    assert master_plan.basis == BASIS_MASTER


def test_master_basis_ignores_a_static_schedule_and_exports_carry_the_basis() -> None:
    static_plan, master_plan, schedule = _plans(
        _example_units(),
        required={JAN: 3.0, FEB: 5.0, MAR: 7.0},
        static={JAN: 3.0, FEB: 4.5, MAR: 8.0},
    )
    common: dict[str, Any] = {
        "equipment": _master(_example_units()),
        "downtime": _downtime(),
        "baseline": _baseline(2.0),
        "cutoff": _cutoff(),
        "required_equipment": _required({JAN: 3.0, FEB: 5.0, MAR: 7.0}),
        "months": MONTHS,
        "today": TODAY,
        "levels": (1.1,),
    }
    with_schedule = plan_required_shortening(**common, basis=BASIS_MASTER, static_schedule=schedule)

    pd.testing.assert_frame_equal(
        with_schedule.at(1.1).units, master_plan.at(1.1).units, check_dtype=True
    )
    pd.testing.assert_frame_equal(
        with_schedule.at(1.1).process_months, master_plan.at(1.1).process_months
    )
    assert with_schedule.static_schedule is None
    units = unit_export_frame(static_plan, (1.1,))
    months = process_month_export_frame(master_plan, (1.1,))
    assert units.columns[0] == BASIS_COLUMN and set(units[BASIS_COLUMN]) == {BASIS_STATIC}
    assert months.columns[0] == BASIS_COLUMN and set(months[BASIS_COLUMN]) == {BASIS_MASTER}


def test_static_basis_needs_the_reverse_schedule() -> None:
    with pytest.raises(ValueError, match="Static 역산"):
        plan_required_shortening(
            equipment=_master(_example_units()),
            downtime=_downtime(),
            baseline=_baseline(2.0),
            cutoff=_cutoff(),
            required_equipment=_required({JAN: 3.0}),
            months=MONTHS,
            today=TODAY,
            basis=BASIS_STATIC,
        )


# ---------------------------------------------------------------- 갈래(Q06 ~ Q15)


def test_downtime_is_taken_after_the_reverse() -> None:
    """Q07 (가) — 고정 호기 하나가 2월 구간 14일 운영 비가동이어도 U3 은 2/4 그대로, 2월 가용
    4.0."""
    fixed = [_unit("E1", None, existing="Y"), _unit("E2", None, existing="Y")]
    static_plan, _, schedule = _plans(
        fixed + _example_units(),
        required={JAN: 3.0, FEB: 5.0, MAR: 7.0},
        static={JAN: 3.0, FEB: 4.5, MAR: 8.0},
        baseline=_baseline(0.0),
        downtime=_downtime([("E1", date(2027, 1, 21), date(2027, 2, 3))]),
    )

    assert schedule.assignment("U3") is not None
    assert schedule.assignment("U3").deadline == date(2027, 2, 4)  # type: ignore[union-attr]
    assert static_plan.at(1.1).process_months["가용대수"].round(3).tolist() == [3.0, 4.0, 8.0]


def test_units_short_of_static_leave_a_shortfall() -> None:
    """Q10 — 역산할 호기가 넷뿐이면 3월은 6.0 으로 Static 8.0 에 2.0대 모자란다."""
    _, _, schedule = _plans(
        _example_units(("U1", "U2", "U3", "U4")),
        required={JAN: 3.0, FEB: 5.0, MAR: 7.0},
        static={JAN: 3.0, FEB: 4.5, MAR: 8.0},
    )

    (shortage,) = schedule.shortages()
    assert (shortage.month, round(shortage.carried + shortage.added, 3)) == (MAR, 6.0)
    assert round(shortage.shortfall, 3) == 2.0


def test_leftover_units_come_before_virtual_units_without_a_current_date() -> None:
    """Q11 (가) — U7 · U8 은 3월까지 쓰이지 않는다. 3월 소요 8.0(목표 8.8)의 0.8대는 U7 이 필요
    2/24."""
    static_plan, _, schedule = _plans(
        _example_units(("U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8")),
        required={JAN: 3.0, FEB: 5.0, MAR: 8.0},
        static={JAN: 3.0, FEB: 4.5, MAR: 8.0},
    )

    assert [unit.unit for unit in schedule.leftovers] == ["U7", "U8"]
    rows = static_plan.at(1.1).units
    leftover = rows.loc[rows["호기"].eq("U7")].iloc[0]
    assert leftover["구분"] == KIND_SHORTENED
    assert leftover["기존 Qual"] is None
    assert pd.isna(leftover["단축일수"])
    assert leftover["목표 Qual"] == date(2027, 2, 24)
    assert not rows["호기"].str.startswith("추가").any()
    exported = unit_export_frame(static_plan, (1.1,))
    line = exported.loc[exported["호기"].eq("U7")].iloc[0]
    assert line["기존 Qual 완료일"] is None and line["목표 Qual 완료일"] == "2027-02-24"


def test_past_deadlines_move_to_today_without_draining_the_queue() -> None:
    """Q12 (가) — 2026-11 구간 (10/21, 11/20] 에 1대 더 → 역산 10/21(지남) → 현재 일정 11/19."""
    units = [_unit("U1", date(2026, 12, 1)), _unit("U2", date(2026, 12, 20))]
    schedule = build_static_qual_schedule(
        equipment=_master(units),
        downtime=_downtime(),
        baseline=_baseline(2.0),
        cutoff=_cutoff(),
        static_availability=_static({202611: 3.0}),
        months=[202611],
        today=TODAY,
    )

    (item,) = schedule.assignments
    assert (item.unit, item.deadline, item.current, item.past) == (
        "U1",
        date(2026, 10, 21),
        TODAY,
        True,
    )
    assert [unit.unit for unit in schedule.leftovers] == ["U2"]
    assert schedule.past_assignments() == (item,)


def test_processes_without_static_are_not_planned() -> None:
    """Q13 (가) — Static 행이 없는 공정은 계산하지 않고 `static_missing` 에 둔다."""
    other = "DEMO-B"
    units = [*_example_units(("U1", "U2")), _unit("B1", date(2027, 1, 10), process=other)]
    equipment = _master(units)
    required = pd.concat(
        [_required({JAN: 3.0}), _required({JAN: 1.0}, process=other)], ignore_index=True
    )
    cutoff = _cutoff(processes=(PROCESS, other))
    baseline = pd.concat([_baseline(2.0), _baseline(1.0, other)], ignore_index=True)
    schedule = build_static_qual_schedule(
        equipment=equipment,
        downtime=_downtime(),
        baseline=baseline,
        cutoff=cutoff,
        static_availability=_static({JAN: 3.0}),
        months=[JAN],
        today=TODAY,
    )
    plan = plan_required_shortening(
        equipment=equipment,
        downtime=_downtime(),
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=required,
        months=[JAN],
        today=TODAY,
        levels=(1.1,),
        basis=BASIS_STATIC,
        static_schedule=schedule,
    )

    assert plan.processes == (PROCESS,)
    assert plan.static_missing == (other,)


def test_qual_order_undated_units_and_finished_units() -> None:
    """Q08 · Q09 · Q15 — Qual 이른 순 → 번호, 일정 미정은 반입 순 뒤, Qual실적 · 완료는 고정."""
    units = [
        _unit("U4", date(2027, 3, 25)),
        _unit("U5", date(2027, 3, 5)),
        _unit("U9", None, arrival=date(2027, 1, 5)),
        _unit("U8", None, arrival=date(2027, 2, 5)),
        _unit("U7", None, arrival=None),
        _unit("U0", date(2026, 11, 1), actual=date(2026, 11, 10)),
        _unit("U6", date(2026, 11, 2), confirmation="완료"),
        _unit("M1", date(2027, 2, 1), ratio=0.5, parent="MAIN-1"),
        _unit("M2", date(2027, 2, 3), ratio=0.5, parent="MAIN-1"),
    ]

    targets = reverse_targets(_master(units))

    assert [unit.unit for unit in targets] == ["MAIN-1", "U5", "U4", "U9", "U8", "U7"]
    main = targets[0]
    assert main.modules == (("M1", 0.5), ("M2", 0.5))
    assert (main.ratio, main.master_qual) == (1.0, date(2027, 2, 3))


# ---------------------------------------------------------------- 캐시 키


def _frames() -> dict[str, Any]:
    return {
        "equipment": _master(_example_units()),
        "downtime": _downtime(),
        "baseline": _baseline(2.0),
        "cutoff": _cutoff(),
    }


def _key(basis: str | None = None) -> simulation_cache.RequiredShorteningCacheKey:
    extra: dict[str, Any] = {} if basis is None else {"basis": basis}
    return simulation_cache.required_shortening_cache_key(
        (1, "static-cache-token", JAN, MAR),
        **_frames(),
        months=tuple(MONTHS),
        today=TODAY,
        manual_downtime=ManualDowntime(),
        **extra,
    )


def test_the_basis_is_the_last_key_cell_and_defaults_to_the_master() -> None:
    default = _key()
    static = _key(BASIS_STATIC)

    assert simulation_cache.shortening_key_basis(default) == BASIS_MASTER
    assert simulation_cache.shortening_key_basis(static) == BASIS_STATIC
    assert default[:9] == static[:9]
    assert simulation_cache.with_basis(default, BASIS_STATIC) == static
    assert simulation_cache.with_upeh_token(static, ((90, (JAN,)),))[9] == BASIS_STATIC
    assert simulation_cache.static_schedule_key(default) == static


def test_both_bases_share_one_reverse_and_static_needs_its_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulation_cache.get_required_shortening.clear()
    simulation_cache._static_qual_schedule.clear()
    built: list[int] = []
    original = static_qual_schedule.build_static_qual_schedule

    def counting(**kwargs: Any) -> static_qual_schedule.StaticQualSchedule:
        built.append(1)
        return original(**kwargs)

    monkeypatch.setattr(simulation_cache, "build_static_qual_schedule", counting)
    frames = _frames()
    table = _static({JAN: 3.0, FEB: 4.5, MAR: 8.0})

    def loader() -> pd.DataFrame:
        return _required({JAN: 3.0, FEB: 5.0, MAR: 7.0})

    static_plan = simulation_cache.load_required_shortening(
        _key(BASIS_STATIC),
        frames["equipment"],
        frames["downtime"],
        frames["baseline"],
        frames["cutoff"],
        required_equipment=loader,
        static_availability=table,
    ).plan
    schedule = simulation_cache.get_static_qual_schedule(
        _key(),
        frames["equipment"],
        frames["downtime"],
        frames["baseline"],
        frames["cutoff"],
        _static_availability=table,
    )

    assert built == [1]
    assert static_plan.static_schedule == schedule
    assert schedule.static_current()["U3"] == date(2027, 2, 4)
    assert sorted(static_plan.at(1.1).units["단축일수"].tolist()) == [10, 14, 14]
    other = simulation_cache.required_shortening_cache_key(
        (1, "other-token", JAN, MAR),
        **frames,
        months=tuple(MONTHS),
        today=TODAY,
        manual_downtime=ManualDowntime(),
        basis=BASIS_STATIC,
    )
    with pytest.raises(ValueError, match="Static 가용대수"):
        simulation_cache.get_required_shortening(
            other,
            frames["equipment"],
            frames["downtime"],
            frames["baseline"],
            frames["cutoff"],
            _required_equipment=loader,
        )
