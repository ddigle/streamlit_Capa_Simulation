# Purpose: 제약 시뮬레이션의 보유 「호기 고르기」·묶음 신규 첫 모듈 규칙·보유로 덮이면 신규를 붙이지
# 않는 규칙을 손계산과 맞댄다.

"""제약 시뮬레이션 2판 옵션 — 2026-11-01 사용자 결정(B1 · B2 · B3)의 계산 몫.

**기대값은 손계산이다.** 하네스는 작은 합성 공정이다(업무 사실이 아니다) — 제약 확보율 100%,
Cut-off 7, 개조 30일, 달마다 소요 20 · 가용 30. W/D 첫날은 6월 5/25 · 7월 6/24 · 8월 7/25 이고 W/D
구간은 6월 5/25~6/23(30일) · 7월 6/24~7/24(31일)이다.

- **B1** — 보유만으로 기간 끝까지 늘어난 전용을 다 채우면 신규를 붙이지 않는다.
- **B2** — 묶음 신규는 첫 모듈 날짜로 판정하고 창 `[d, d + D]` 도 그날부터 센다. 모듈마다 제
  날짜부터 대기하고(B2-1), 증가의 t 에 아직 오지 않은 모듈은 그 증가에 붙지 않는다(B2-2).
- **B3** — 보유는 고른 호기 가운데 그 달 W/D 첫날에 있는 것의 환산 합 + 목록에 없는 보유 칸이다.
  나간 날부터 빼고(B3-1) 이미 쓴 몫은 풀지 않는다.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from test_constraint_simulation import _one

from capa_simulation.services.constraint_simulation import (
    ConstraintConditions,
    ConstraintMonthInput,
    ConstraintResult,
    HeldUnit,
    NewUnit,
    OrdinaryReason,
    UnitModule,
    simulate_constraint,
)

SINCE = date(2026, 10, 26)
JUNE_FIRST = date(2027, 5, 25)
JULY_FIRST = date(2027, 6, 24)


def _months(*demands: float) -> list[ConstraintMonthInput]:
    """6월부터 달마다 제약 소요(= 필요 대수, 확보율 100%)."""
    stamps = (202706, 202707, 202708)
    return [
        _one(stamp, required=20, available=30, demand=demand)
        for stamp, demand in zip(stamps, demands, strict=False)
    ]


def _conditions(
    months: list[ConstraintMonthInput],
    *,
    owned: int = 0,
    held: tuple[HeldUnit, ...] = (),
    new: bool = False,
    days: int = 30,
) -> ConstraintConditions:
    return ConstraintConditions(
        months[0].month,
        months[-1].month,
        1.0,
        days,
        7,
        owned_units=owned,
        held_units=held,
        new_unit_since=SINCE if new else None,
    )


def _split(result: ConstraintResult, month: int) -> tuple[int, int, int]:
    row = result.month(month)
    return row.new_increment, row.owned_increment, row.increment


def _held(
    name: str, *, units: float = 1.0, start: date | None = None, until: date | None = None
) -> HeldUnit:
    return HeldUnit(name=name, units=units, start=start, until=until)


def _bundle(name: str, *modules: tuple[str, date, float], until: date | None = None) -> NewUnit:
    parts = tuple(UnitModule(module, start, units) for module, start, units in modules)
    return NewUnit(
        name=name,
        start=min(start for _module, start, _units in modules),
        units=sum(units for _module, _start, units in modules),
        until=until,
        modules=parts,
    )


# ------------------------------------------------------------------ B3 보유 「호기 고르기」


def test_picked_units_count_only_once_they_are_in() -> None:
    """6/20 에 들어오는 고른 호기 H1 — 6월 증가(5/25)에는 없어 개조 2, 7월 증가(6/24)에는 있어 보유
    1 + 개조 1. 그 달 보유는 6월 0 · 7월 1 이다."""
    months = _months(2, 4)
    held = (_held("H1", start=date(2027, 6, 20)),)
    result = simulate_constraint(months, _conditions(months, held=held))
    assert _split(result, 202706) == (0, 0, 2)
    assert _split(result, 202707) == (0, 1, 1)
    assert [row.holdings for row in result.months] == [0.0, 1.0]
    assert result.conditions.uses_owned_units and result.conditions.splits_dedicated


def test_a_picked_unit_leaving_is_dropped_but_its_use_is_not_released() -> None:
    """H1 이 6/24(7월 W/D 첫날)에 정지 — 6월 증가 2 는 보유 1 + 개조 1, 7월 증가 2 는 보유가 없어
    개조 2(결정 B3-1 — 그날부터 보유에서 뺀다). 6월에 쓴 1대는 풀지 않아 7월 보유 누적은 1
    그대로다."""
    months = _months(2, 4)
    held = (_held("H1", until=JULY_FIRST),)
    result = simulate_constraint(months, _conditions(months, held=held))
    assert _split(result, 202706) == (0, 1, 1)
    assert _split(result, 202707) == (0, 0, 2)
    july = result.month(202707)
    assert (july.owned_dedicated, july.modified_dedicated, july.dedicated) == (1, 3, 4)
    assert [row.holdings for row in result.months] == [1.0, 0.0]


def test_picked_units_add_to_the_number_field_and_round_down() -> None:
    """보유 = 목록에 없는 보유 칸 + 고른 호기 환산 합(내림) — 1 + 0.5 + 0.5 = 2, 1 + 0.5 = 1."""
    months = _months(3)
    halves = (_held("H1", units=0.5), _held("H2", units=0.5))
    both = simulate_constraint(months, _conditions(months, owned=1, held=halves))
    assert _split(both, 202706) == (0, 2, 1)
    one = simulate_constraint(months, _conditions(months, owned=1, held=halves[:1]))
    assert _split(one, 202706) == (0, 1, 2)
    assert one.month(202706).holdings == 1.5


def test_a_picked_bundle_counts_each_module_from_its_own_day() -> None:
    """고른 묶음 G — 모듈 G-A 처음부터 · G-B 6/10. 6월 W/D 첫날(5/25)에는 G-A 1대, 7월(6/24)에는
    2대."""
    months = _months(2, 3)
    bundle = HeldUnit(
        name="G",
        units=2.0,
        start=None,
        modules=(UnitModule("G-A", None, 1.0), UnitModule("G-B", date(2027, 6, 10), 1.0)),
    )
    result = simulate_constraint(months, _conditions(months, held=(bundle,)))
    assert _split(result, 202706) == (0, 1, 1)
    assert _split(result, 202707) == (0, 1, 0)
    assert [row.holdings for row in result.months] == [1.0, 2.0]


def test_held_units_are_locked_with_the_modification() -> None:
    """개조 끔이면 고른 호기도 걸리지 않는다(설비가 서로 바뀐다는 뜻)."""
    months = _months(2)
    off = ConstraintConditions(
        202706, 202706, 1.0, None, 7, held_units=(_held("H1"),), new_unit_since=SINCE
    )
    assert not off.uses_owned_units and not off.splits_dedicated
    assert off.holdings_on(JUNE_FIRST) == 0.0
    result = simulate_constraint(months, off)
    assert result.month(202706).holdings == 0.0
    assert result.kpis.owned_used == 0


@pytest.mark.parametrize(
    ("held", "message"),
    [
        ((_held("H1"), _held("H1")), "겹칩니다"),
        ((_held("H1", units=0.0),), "환산 대수"),
        ((_held("H1", start=cast(date, "2027-06-01")),), "날짜가 아닙니다"),
        (
            (
                HeldUnit(
                    "G",
                    2.0,
                    modules=(UnitModule("G-A", None, 1.0), UnitModule("G-B", None, 0.5)),
                ),
            ),
            "모듈 환산 몫 합",
        ),
        (
            (
                HeldUnit(
                    "G",
                    1.0,
                    start=date(2027, 6, 1),
                    modules=(UnitModule("G-A", date(2027, 6, 2), 1.0),),
                ),
            ),
            "첫 모듈",
        ),
    ],
)
def test_invalid_held_units_are_rejected(held: tuple[HeldUnit, ...], message: str) -> None:
    months = _months(2)
    with pytest.raises(ValueError, match=message):
        simulate_constraint(months, _conditions(months, held=held))


def test_a_held_unit_must_not_also_be_a_new_unit() -> None:
    """고른 호기는 신규 후보에서 빠져야 한다 — 둘 다에 들면 두 번 세므로 막는다."""
    months = _months(2)
    conditions = _conditions(months, held=(_held("N1"),), new=True)
    with pytest.raises(ValueError, match="두 번 셉니다"):
        simulate_constraint(months, conditions, (NewUnit("N1", JUNE_FIRST, 1.0),))


# ------------------------------------------------------------------ B1 보유로 덮이면 신규 없음


def test_picked_units_covering_the_period_skip_the_new_units() -> None:
    """고른 호기 둘이 6월 2 · 7월 2 를 다 덮는다 — 6/20 신규 N1 은 붙지 않고 기존 제품 몫이다."""
    months = _months(2, 2)
    held = (_held("H1"), _held("H2"))
    result = simulate_constraint(
        months, _conditions(months, held=held, new=True), (NewUnit("N1", date(2027, 6, 20), 1.0),)
    )
    assert _split(result, 202706) == (0, 2, 0)
    assert result.assignments == () and result.new_units_skipped
    assert [unit.name for unit in result.ordinary_units] == ["N1"]


def test_a_picked_unit_leaving_breaks_the_cover_and_brings_back_the_new_unit() -> None:
    """필요 6월 2 → 7월 3. 고른 H1 · H2 · H3 가운데 H3 가 6/24 에 나가면 보유만으로는 7월에 개조
    1 이 남아 덮지 못한다 — 차례 그대로 6/20 신규 N1 이 7월 증가에 붙는다(대기 4일). H3 가 나가지
    않으면 보유 셋이 덮어 N1 을 붙이지 않는다."""
    months = _months(2, 3)
    leaving = (_held("H1"), _held("H2"), _held("H3", until=JULY_FIRST))
    unit = (NewUnit("N1", date(2027, 6, 20), 1.0),)
    broken = simulate_constraint(months, _conditions(months, held=leaving, new=True), unit)
    assert _split(broken, 202706) == (0, 2, 0)
    assert _split(broken, 202707) == (1, 0, 0)
    assert [(item.unit, item.month, item.days) for item in broken.assignments] == [
        ("N1", 202707, 4)
    ]
    assert not broken.new_units_skipped

    staying = (_held("H1"), _held("H2"), _held("H3"))
    covered = simulate_constraint(months, _conditions(months, held=staying, new=True), unit)
    assert _split(covered, 202707) == (0, 1, 0)
    assert covered.assignments == () and covered.new_units_skipped


def test_without_growth_nothing_is_skipped() -> None:
    """제약 소요가 없으면 덮을 것도 붙일 것도 없다 — 「붙이지 않음」 표지도 서지 않는다."""
    months = _months(0, 0)
    result = simulate_constraint(
        months, _conditions(months, owned=2, new=True), (NewUnit("N1", JUNE_FIRST, 1.0),)
    )
    assert result.assignments == () and not result.new_units_skipped


# ------------------------------------------------------------------ B2 묶음 신규 — 첫 모듈 기준


def test_a_bundle_attaches_each_module_from_its_own_day() -> None:
    """묶음 G — 모듈 G-A 5/25 · G-B 6/10(환산 1 씩), 첫 모듈 5/25 라 창은 5/25 ~ 6/24.

    6월 증가 2(t 5/25) = G-A 1(대기 0일 — 결정 B2-2: G-B 는 아직 오지 않아 붙지 않는다) + 개조 1.
    7월 증가 2(t 6/24 — 창 끝 날) = G-B 1(대기 6/10 ~ 6/23 14일 — 결정 B2-1: 첫 모듈 날이 아니라 제
    날짜부터) + 개조 1. 6월 W/D(30일)의 대기는 14/30. 옛 규칙(가장 늦은 모듈 6/10 하나)이면 6월 개조
    2 · 7월 신규 2(둘 다 14일 대기)였다.
    """
    months = _months(2, 4)
    bundle = _bundle("G", ("G-A", JUNE_FIRST, 1.0), ("G-B", date(2027, 6, 10), 1.0))
    result = simulate_constraint(months, _conditions(months, new=True), (bundle,))
    assert _split(result, 202706) == (1, 0, 1)
    assert _split(result, 202707) == (1, 0, 1)
    assert [(item.label, item.month, item.start, item.days) for item in result.assignments] == [
        ("G(G-A)", 202706, JUNE_FIRST, 0),
        ("G(G-B)", 202707, date(2027, 6, 10), 14),
    ]
    june = result.month(202706)
    assert june.waiting == pytest.approx(14 / 30)
    assert [(share.label, share.days) for share in june.waiting_shares] == [("G(G-B)", 14)]
    assert result.ordinary_units == ()
    assert [(window.month, window.units) for window in result.windows] == [
        (202706, 1),
        (202707, 1),
    ]


def test_the_window_runs_from_the_first_module() -> None:
    """뒤 모듈 G-B(6/10)가 와도 창은 첫 모듈(5/20)부터 30일 — 6/19 에 닫힌다. 7월 증가(6/24)는 창
    밖이라 G-B 는 일반 설비다(남는 1대). 첫 모듈만 6월 증가에 붙는다(대기 5일)."""
    months = _months(2, 4)
    bundle = _bundle("G", ("G-A", date(2027, 5, 20), 1.0), ("G-B", date(2027, 6, 10), 1.0))
    result = simulate_constraint(months, _conditions(months, new=True), (bundle,))
    assert _split(result, 202706) == (1, 0, 1)
    assert _split(result, 202707) == (0, 0, 2)
    assert [(item.label, item.days) for item in result.assignments] == [("G(G-A)", 5)]
    assert [unit.name for unit in result.ordinary_units] == ["G"]
    assert result.left_units(result.new_units[0]) == 1.0


def test_a_bundle_whose_later_module_misses_the_growth_waits_no_longer() -> None:
    """뒤 모듈이 증가 뒤에 오면 묶음 전체를 기다리지 않는다(결정 B2-2 의 대안 「마지막 모듈까지
    기다림」 이 아니다) — G-A 5/25 · G-B 6/30, 필요 6월 2 그대로면 6월은 G-A 1 + 개조 1 이고 G-B 는
    붙을 증가가 없어 일반 설비다."""
    months = _months(2, 2)
    bundle = _bundle("G", ("G-A", JUNE_FIRST, 1.0), ("G-B", date(2027, 6, 30), 1.0))
    result = simulate_constraint(months, _conditions(months, new=True), (bundle,))
    assert _split(result, 202706) == (1, 0, 1)
    assert [(item.label, item.days) for item in result.assignments] == [("G(G-A)", 0)]
    assert result.left_units(result.new_units[0]) == 1.0


def test_bundles_are_taken_in_first_module_order() -> None:
    """먼저 들어온 호기부터(결정 B4) — 묶음은 첫 모듈 날로 줄 선다. 6월 증가 1 이면 첫 모듈 5/21 인
    G 가 5/23 하나짜리 S 보다 먼저 붙는다(옛 규칙이면 G 의 날은 뒤 모듈 6/1 이라 S 가 먼저였다)."""
    months = _months(1)
    bundle = _bundle("G", ("G-A", date(2027, 5, 21), 1.0), ("G-B", date(2027, 6, 1), 1.0))
    single = NewUnit("S", date(2027, 5, 23), 1.0)
    result = simulate_constraint(months, _conditions(months, new=True), (single, bundle))
    assert [unit.name for unit in result.new_units] == ["G", "S"]
    assert [(item.label, item.days) for item in result.assignments] == [("G(G-A)", 4)]


@pytest.mark.parametrize(
    ("unit", "message"),
    [
        (
            NewUnit("G", JUNE_FIRST, 2.0, modules=(UnitModule("G-A", JUNE_FIRST, 1.0),)),
            "모듈 환산 몫 합",
        ),
        (
            NewUnit(
                "G",
                JUNE_FIRST,
                2.0,
                modules=(UnitModule("G-A", None, 1.0), UnitModule("G-B", JUNE_FIRST, 1.0)),
            ),
            "기여 시작이 비었습니다",
        ),
        (
            NewUnit(
                "G",
                JUNE_FIRST,
                2.0,
                modules=(UnitModule("G-A", JULY_FIRST, 1.0), UnitModule("G-A", JULY_FIRST, 1.0)),
            ),
            "겹칩니다",
        ),
        (
            NewUnit("G", JULY_FIRST, 1.0, modules=(UnitModule("G-A", JUNE_FIRST, 1.0),)),
            "첫 모듈 날짜보다 늦습니다",
        ),
    ],
)
def test_invalid_bundles_are_rejected(unit: NewUnit, message: str) -> None:
    months = _months(2)
    with pytest.raises(ValueError, match=message):
        simulate_constraint(months, _conditions(months, new=True), (unit,))


# ------------------------------------------------------------------ 일반 설비가 된 까닭


def _reason(units: tuple[NewUnit, ...], *demands: float) -> ConstraintResult:
    months = _months(*demands)
    return simulate_constraint(months, _conditions(months, new=True), units)


def test_a_bundle_whose_late_module_misses_the_increase_is_short_not_without_growth() -> None:
    """묶음 G(G-A 5/10 0.5 · G-B 6/10 0.5)는 창 [5/10, 6/9] 안에 6월 증가(W/D 첫날 5/25)가
    있다 — 그때 G-A 0.5대만 와 있어 내림 0 이고 G-B 는 아직 오지 않았다(B2-2). 까닭은 「창 안
    증가 없음」 이 아니다(2026-11-01 E2E — 사본 SMP-DAF-12 의 카드가 「개조 30일 안에 늘어날
    전용이 없어」 라고 적었다). F(7/20)는 창 [7/20, 8/19] 안에 W/D 첫날이 없다."""
    bundle = _bundle("G", ("G-A", date(2027, 5, 10), 0.5), ("G-B", date(2027, 6, 10), 0.5))
    late = NewUnit("F", date(2027, 7, 20), 1.0)
    result = _reason((bundle, late), 1, 1, 1)
    assert _split(result, 202706) == (0, 0, 1)
    assert result.ordinary_reason(bundle) == OrdinaryReason(
        "short", months=(202706,), arrived=0.5, pending=("G-B",)
    )
    assert result.ordinary_reason(late) == OrdinaryReason("no_growth")


def test_the_other_reasons_follow_what_the_increase_met() -> None:
    """X(5/20)가 6월 증가 1 을 채워 Y(5/21)는 `filled`, Z 는 6월 W/D 첫날(5/25)에 나가 `gone`,
    C(5/20 · 1.5)는 증가 2 에 1대가 붙고 남은 0.5대가 내림 0 이라 `short`(일부 붙음), 묶음
    H(H-A 5/10 1.0 · H-B 6/10 0.5)는 H-A 가 증가를 다 채워 H-B 가 와 있었어도 붙을 자리가
    없었다 — `filled`."""
    first = NewUnit("X", date(2027, 5, 20), 1.0)
    second = NewUnit("Y", date(2027, 5, 21), 1.0)
    gone = NewUnit("Z", date(2027, 5, 20), 1.0, until=JUNE_FIRST)
    filled = _reason((first, second, gone), 1)
    assert filled.ordinary_reason(second) == OrdinaryReason("filled", months=(202706,))
    assert filled.ordinary_reason(gone) == OrdinaryReason("gone", months=(202706,))

    partly = NewUnit("C", date(2027, 5, 20), 1.5)
    split = _reason((partly,), 2)
    assert _split(split, 202706) == (1, 0, 1)
    assert split.ordinary_reason(partly) == OrdinaryReason(
        "short", months=(202706,), arrived=0.5, attached=True
    )

    bundle = _bundle("H", ("H-A", date(2027, 5, 10), 1.0), ("H-B", date(2027, 6, 10), 0.5))
    met = _reason((bundle,), 1)
    assert met.ordinary_reason(bundle) == OrdinaryReason("filled", months=(202706,), attached=True)
