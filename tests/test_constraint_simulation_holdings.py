# Purpose: 제약 시뮬레이션의 보유 「호기 고르기」·묶음 신규 첫 모듈 규칙·보유로 덮이면 신규를 붙이지
# 않는 규칙과 신규가 일반 설비가 된 까닭을 손계산과 맞댄다.

"""제약 시뮬레이션 2판 옵션 — 2026-11-01 사용자 결정(B1 · B2 · B3)의 계산 몫.

**기대값은 손계산이다.** 하네스는 작은 합성 공정이다(업무 사실이 아니다) — 제약 확보율 100%,
Cut-off 7, 개조 30일, 달마다 소요 20 · 가용 30. W/D 첫날은 6월 5/25 · 7월 6/24 · 8월 7/25 이고 W/D
구간은 6월 5/25~6/23(30일) · 7월 6/24~7/24(31일)이다.

- **B1** — 늘어나는 달에서 남은 보유만으로 기간 끝까지 남은 증가를 다 채우면 그 증가부터 신규를
  붙이지 않는다(같은 날 「기간 전체로 한 번」 에서 증가마다로 넓힘 — 첫 증가에서 덮이면 옛 답과
  같다).
- **B2** — 묶음 신규는 첫 모듈 날짜로 판정하고 창 `[d, d + D]` 도 그날부터 센다. 모듈마다 제
  날짜부터 대기하고(B2-1), 증가의 t 에 아직 오지 않은 모듈은 그 증가에 붙지 않는다(B2-2).
- **B3** — 보유는 고른 호기 가운데 그 달 W/D 첫날에 있는 것의 환산 합 + 목록에 없는 보유 칸이다.
  나간 날부터 빼고(B3-1) 이미 쓴 몫은 풀지 않는다.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, timedelta
from typing import cast

import pytest
from test_constraint_simulation import _one

import capa_simulation.services.constraint_simulation as constraint_simulation
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
from capa_simulation.services.wd_window import wd_window

SINCE = date(2026, 10, 26)
JUNE_FIRST = date(2027, 5, 25)
JULY_FIRST = date(2027, 6, 24)


def _months(*demands: float) -> list[ConstraintMonthInput]:
    """6월부터 달마다 제약 소요(= 필요 대수, 확보율 100%)."""
    stamps = (202706, 202707, 202708, 202709, 202710)
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


# ------------------------------------------------------------------ B1 증가마다(2026-11-01 넓힘)
#
# 고른 H1(환산 1 · 6/1 들어옴)은 6월 W/D 첫날 5/25 에는 없고 7월 W/D 첫날 6/24 에는 있다 — 6월
# 증가는 보유로 못 덮어 기간 전체 시험이 늘 떨어지고(옛 규칙은 신규 먼저로 다시 돌렸다), 뒤
# 증가에서만 덮인다. 6/20 신규 N1 은 7월 증가(t 6/24)에 붙으면 6/20 ~ 6/23 4일 대기(6월 W/D
# 5/25 ~ 6/23, 30일)다.

LATE_HELD = (HeldUnit("H1", 1.0, start=date(2027, 6, 1)),)
LATE_UNIT = NewUnit("N1", date(2027, 6, 20), 1.0)


def test_holdings_covering_the_rest_stop_the_new_units_from_that_growth() -> None:
    """필요 6월 2 → 7월 3. 6월 증가 2 는 보유 0 이라 개조 2(N1 은 아직 없음). 7월 증가 1 에서 남은
    보유 1 이 남은 증가 1 을 다 덮어 그 증가부터 신규를 붙이지 않는다 — 보유 1, N1 은 기존 제품 몫,
    대기 0. 옛 규칙(기간 전체로 한 번)은 6월 개조 때문에 신규 먼저로 돌려 N1 을 7월에 붙였고 6월에
    대기 4/30 이 빠졌다(사본 앱 Die Attach 28.04 몫 CSS-DA2-012 대기 3일과 같은 꼴).

    6월 기존 확보율 = (30 − 2) ÷ 18 — 개조 창(06 몫 2대, 4/25 ~ 5/24)은 보이지 않는 5월 W/D 에 든다.
    """
    months = _months(2, 3)
    result = simulate_constraint(
        months, _conditions(months, held=LATE_HELD, new=True), (LATE_UNIT,)
    )
    assert _split(result, 202706) == (0, 0, 2)
    assert _split(result, 202707) == (0, 1, 0)
    assert result.assignments == ()
    assert all(row.waiting == 0.0 for row in result.months)
    assert result.month(202706).existing_rate == pytest.approx((30 - 2) / 18)
    assert [(window.month, window.units) for window in result.windows] == [(202706, 2)]
    assert result.new_units_stopped_month == 202707
    assert not result.new_units_skipped
    assert [unit.name for unit in result.held_back_units] == ["N1"]
    assert [unit.name for unit in result.ordinary_units] == ["N1"]


def test_new_units_attached_before_the_cover_stay() -> None:
    """필요 6월 2 → 7월 3 → 8월 4, 고른 H1 환산 2(6/1). 6월 증가 2 = 5/25 신규 N0 1(대기 0일) +
    개조 1 — 보유가 아직 없어 덮이지 않는다. 7월 증가 1 에서 남은 보유 2 가 7월 1 · 8월 1 을 다
    덮어 그 증가부터 신규를 붙이지 않는다 — 7월 · 8월 보유 1 씩, 6/20 N1 은 기존 제품 몫. 앞에
    붙은 N0 은 그대로다. 옛 규칙이면 N1 이 7월에 붙어 4일 대기했다."""
    months = _months(2, 3, 4)
    held = (HeldUnit("H1", 2.0, start=date(2027, 6, 1)),)
    units = (NewUnit("N0", JUNE_FIRST, 1.0), LATE_UNIT)
    result = simulate_constraint(months, _conditions(months, held=held, new=True), units)
    assert _split(result, 202706) == (1, 0, 1)
    assert _split(result, 202707) == (0, 1, 0)
    assert _split(result, 202708) == (0, 1, 0)
    assert [(item.unit, item.month, item.days) for item in result.assignments] == [
        ("N0", 202706, 0)
    ]
    assert result.month(202706).waiting == 0.0
    assert result.new_units_stopped_month == 202707
    assert [unit.name for unit in result.held_back_units] == ["N1"]
    assert result.kpis.modified_units == 1
    assert (result.kpis.owned_used, result.kpis.new_used) == (2, 1)


def test_holdings_must_cover_every_remaining_growth() -> None:
    """필요 6월 2 → 7월 3 → 8월 5. 7월 증가 1 은 보유 1 로 덮이지만 8월 증가 2 가 남아(보유만으로는
    8월 개조 2) 남은 증가를 다 덮지 못한다 — 7월은 차례 그대로 N1 1(대기 4일), 8월 증가 2 = 보유 1 +
    개조 1. 옛 규칙과 같은 답이다."""
    months = _months(2, 3, 5)
    result = simulate_constraint(
        months, _conditions(months, held=LATE_HELD, new=True), (LATE_UNIT,)
    )
    assert _split(result, 202707) == (1, 0, 0)
    assert _split(result, 202708) == (0, 1, 1)
    assert [(item.unit, item.month, item.days) for item in result.assignments] == [
        ("N1", 202707, 4)
    ]
    assert result.month(202706).waiting == pytest.approx(4 / 30)
    assert result.new_units_stopped_month is None
    assert result.held_back_units == ()


def test_only_units_that_could_attach_after_the_stop_are_held_back() -> None:
    """필요 6월 2 → 7월 3 → 8월 3. 7월 증가에서 덮여 그 뒤로 신규를 붙이지 않는다. N1(6/20)은
    7월 증가(t 6/24)에 붙을 수 있었으니 결정 B1 로 붙지 않은 호기이고, N2(7/1)는 창 7/1 ~ 7/31
    안에 증가가 없어(8월 증가 0) 어차피 붙지 않았을 호기라 들지 않는다 — 화면이 둘의 까닭을
    가른다."""
    months = _months(2, 3, 3)
    units = (LATE_UNIT, NewUnit("N2", date(2027, 7, 1), 1.0))
    result = simulate_constraint(months, _conditions(months, held=LATE_HELD, new=True), units)
    assert result.new_units_stopped_month == 202707
    assert [unit.name for unit in result.held_back_units] == ["N1"]
    assert [unit.name for unit in result.ordinary_units] == ["N1", "N2"]


def test_a_cover_from_the_first_growth_is_the_old_skip() -> None:
    """첫 증가에서 덮이면 신규는 하나도 붙지 않는다 — 옛 「기간 전체로 한 번」 의 답과 같다
    (`new_units_skipped`). 창 안에 증가가 없는 신규(6/20 — 6월 증가 t 5/25 앞, 7월 증가 0)는 붙지
    않은 호기에 들지 않는다."""
    months = _months(2, 2)
    held = (_held("H1"), _held("H2"))
    result = simulate_constraint(months, _conditions(months, held=held, new=True), (LATE_UNIT,))
    assert result.new_units_stopped_month == 202706 and result.new_units_skipped
    assert result.held_back_units == ()
    early = simulate_constraint(
        months, _conditions(months, held=held, new=True), (NewUnit("N0", JUNE_FIRST, 1.0),)
    )
    assert early.new_units_skipped
    assert [unit.name for unit in early.held_back_units] == ["N0"]


# ------------------------------------------------------------------ B1 증가마다 — 멈출 달 완전 탐색


def _random_case(
    rng: random.Random,
) -> tuple[list[ConstraintMonthInput], ConstraintConditions, tuple[NewUnit, ...]]:
    """합성 작은 문제 — 2 ~ 5달 제약 소요 사다리(줄기도 함), 목록에 없는 보유 0 ~ 2, 고른 호기 0 ~
    3(들어옴 · 나감 · 환산 0.5 ~ 2), 신규 1 ~ 3(기여 시작 · 반출 · 환산 0.5 ~ 1.5), 개조 15 ~ 45일.
    업무 사실이 아니다."""
    count = rng.randint(2, 5)
    level = 0
    demands: list[float] = []
    for _index in range(count):
        level = max(0, level + rng.choice((-1, 0, 1, 1, 2, 3)))
        demands.append(float(level))
    months = _months(*demands)
    first, last = date(2027, 4, 20), date(2027, 10, 20)
    span = (last - first).days

    def day() -> date:
        return first + timedelta(days=rng.randint(0, span))

    held = tuple(
        HeldUnit(
            f"H{index}",
            rng.choice((0.5, 1.0, 1.0, 2.0)),
            start=rng.choice((None, day())),
            until=rng.choice((None, None, day())),
        )
        for index in range(rng.randint(0, 3))
    )
    units = tuple(
        NewUnit(
            f"N{index}",
            day(),
            rng.choice((0.5, 1.0, 1.0, 1.5)),
            until=rng.choice((None, None, day())),
        )
        for index in range(rng.randint(1, 3))
    )
    conditions = replace(
        _conditions(months, owned=rng.choice((0, 0, 1, 2)), held=held, new=True),
        modification_days=rng.choice((15, 30, 45)),
    )
    return months, conditions, units


def _with_bundles(rng: random.Random, units: tuple[NewUnit, ...]) -> tuple[NewUnit, ...]:
    """신규를 열에 일곱꼴로 두 모듈 묶음(반씩, 뒤 모듈은 0 ~ 60일 늦게)으로 바꾼다 — 남는 모듈이
    증가 뒤에 오는 갈래(결정 B2-2)를 무작위 문제에 싣는다. 합성이다."""
    return tuple(
        _bundle(
            unit.name,
            (f"{unit.name}A", unit.start, unit.units / 2),
            (f"{unit.name}B", unit.start + timedelta(days=rng.randint(0, 60)), unit.units / 2),
            until=unit.until,
        )
        if rng.random() < 0.7
        else unit
        for unit in units
    )


def _splits(result: ConstraintResult) -> list[tuple[int, int, int]]:
    return [(row.new_increment, row.owned_increment, row.increment) for row in result.months]


def _forced(
    monkeypatch: pytest.MonkeyPatch,
    months: list[ConstraintMonthInput],
    conditions: ConstraintConditions,
    units: tuple[NewUnit, ...],
    stop: int | None,
) -> ConstraintResult:
    """멈출 달을 `stop` 으로 못박은 답 — 그 증가 앞은 신규 먼저, 그 증가부터는 보유만(None 이면 늘
    신규 먼저 — 결정 B1 이 없던 차례)."""
    with monkeypatch.context() as patch:
        patch.setattr(
            constraint_simulation,
            "_holdings_cover_rest",
            lambda rest, _conditions, _carry: stop is not None and rest[0].month == stop,
        )
        return simulate_constraint(months, conditions, units)


def test_the_stop_is_the_earliest_growth_whose_rest_the_holdings_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """작은 무작위 문제 600개 — 멈출 달을 늘어나는 달마다 못박아 본 답(완전 탐색)과 맞댄다.

    - 답은 「못박은 달부터 개조 창이 하나도 없는」 늘어나는 달 가운데 가장 이른 달을 못박은 답과
      같다(그런 달이 없으면 늘 신규 먼저인 답과 같다). 그 앞 늘어나는 달은 모두 못박으면 그 달부터
      개조가 남는다.
    - 멈춘 달부터는 신규 · 개조 몫이 0 이고, 달마다 전용(`dedicated`)은 늘 신규 먼저인 답과
      같으며 쓸 수 있는 가용(`usable`)은 그보다 작지 않고 개조 대수 · 대기는 그보다 크지 않다.
    - 보유가 없으면(목록에 없는 보유 0 · 고른 호기 없음) 늘 신규 먼저인 답과 모든 값이 같다.
    """
    rng = random.Random(20261101)
    seen = {"first": 0, "later": 0, "later_held_back": 0}
    for _case in range(600):
        months, conditions, units = _random_case(rng)
        result = simulate_constraint(months, conditions, units)
        plain = _forced(monkeypatch, months, conditions, units, None)
        growth_months = [row.month for row in plain.months if row.growth > 0]
        expected: int | None = None
        for month in growth_months:
            trial = _forced(monkeypatch, months, conditions, units, month)
            if not [window for window in trial.windows if window.month >= month]:
                expected = month
                break
        assert result.new_units_stopped_month == expected, (months, conditions, units)
        reference = (
            plain if expected is None else _forced(monkeypatch, months, conditions, units, expected)
        )
        assert _splits(result) == _splits(reference)
        assert result.assignments == reference.assignments
        assert [row.dedicated for row in result.months] == [row.dedicated for row in plain.months]
        for row, base in zip(result.months, plain.months, strict=True):
            assert row.usable >= base.usable - 1e-9
            assert row.waiting <= base.waiting + 1e-9
        assert (result.kpis.modified_units or 0) <= (plain.kpis.modified_units or 0)
        if expected is not None:
            after = [row for row in result.months if row.month >= expected]
            assert all(row.new_increment == 0 and row.increment == 0 for row in after)
            assert result.new_units_skipped == (expected == growth_months[0])
            if result.new_units_skipped:
                seen["first"] += 1
            else:
                seen["later"] += 1
                seen["later_held_back"] += bool(result.held_back_units)
        if conditions.owned_units == 0 and not conditions.held_units:
            assert expected is None
            assert result == replace(plain, new_units_stopped_month=None)
    # 하네스가 멈추는 갈래(첫 증가 · 뒤 증가 · 뒤 증가에서 신규를 붙이지 않음)를 실제로 지나는지 —
    # 표본이 바뀌면 다시 센다.
    assert seen["first"] >= 100 and seen["later"] >= 20 and seen["later_held_back"] >= 5, seen


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
    없었다 — `filled` 이고, 그 달 붙은 몫이 모두 H 것이라 `own` 이다(「이 호기 몫으로 다 참」 —
    「먼저 들어온 신규가 채움」 은 다른 호기가 채운 것처럼 읽혔다, 2026-11-01 리뷰)."""
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
    assert met.ordinary_reason(bundle) == OrdinaryReason(
        "filled", months=(202706,), attached=True, own=(202706,)
    )


def test_filled_names_only_the_increases_new_units_filled() -> None:
    """`filled` 의 달은 신규로 다 채운 증가뿐이다(2026-11-01 리뷰). 필요 6월 1 → 7월 2, 개조 45일,
    묶음 G(G-A 5/20 0.75 · G-B 6/05 0.75 — 창 [5/20, 7/4]). 6월 증가(t 5/25)에는 G-A 0.75대만 와
    있어 내림 0 — 개조 1 이다. 7월 증가(t 6/24)는 G-A 0.75 + G-B 0.25 가 채우고 G-B 0.5대가 남는다.
    남는 G-B 는 6월에 아직 오지 않아 `short` 가 아니고, 까닭은 7월 증가가 다 찬 것뿐이다 — 옛 판은
    창 안의 두 달을 다 적어 6월(개조 1대)도 「신규가 채워」 라고 했다. 7월은 G 몫으로만 찼다."""
    months = _months(1, 2)
    conditions = replace(_conditions(months, new=True), modification_days=45)
    bundle = _bundle("G", ("G-A", date(2027, 5, 20), 0.75), ("G-B", date(2027, 6, 5), 0.75))
    result = simulate_constraint(months, conditions, (bundle,))
    assert _split(result, 202706) == (0, 0, 1)
    assert _split(result, 202707) == (1, 0, 0)
    assert [(item.label, item.month, item.units) for item in result.assignments] == [
        ("G(G-A)", 202707, 0.75),
        ("G(G-B)", 202707, 0.25),
    ]
    assert result.ordinary_reason(bundle) == OrdinaryReason(
        "filled", months=(202707,), attached=True, own=(202707,)
    )


def test_filled_tells_its_own_increases_from_the_ones_others_filled() -> None:
    """하나짜리 U(5/25 · 1.5)는 창 [5/25, 6/24] 안에 6월 · 7월 증가(1 씩)가 있다. 6월은 먼저 들어온
    X(5/20)가 채우고 7월은 U 의 1대가 혼자 채워 0.5대가 남는다 — 두 달 모두 `filled` 이고 7월만
    `own` 이다. U 하나만이면 6월 증가 1 을 U 가 혼자 채운다(`own` — 리뷰의 1.5대 보기)."""
    first = NewUnit("X", date(2027, 5, 20), 1.0)
    unit = NewUnit("U", JUNE_FIRST, 1.5)
    both = _reason((first, unit), 1, 2)
    assert [(item.unit, item.month) for item in both.assignments] == [
        ("X", 202706),
        ("U", 202707),
    ]
    assert both.ordinary_reason(unit) == OrdinaryReason(
        "filled", months=(202706, 202707), attached=True, own=(202707,)
    )
    alone = _reason((replace(unit, start=date(2027, 5, 20)),), 1)
    assert alone.ordinary_reason(alone.new_units[0]) == OrdinaryReason(
        "filled", months=(202706,), attached=True, own=(202706,)
    )


def test_a_unit_held_back_by_the_cover_says_so_from_that_growth() -> None:
    """B1 증가마다와 호기마다 까닭(2026-11-01 — 두 갈래를 합친 꼴). 필요 6월 1 → 7월 2 → 8월 2,
    고른 H1(6/1). 6월 증가 1 은 보유가 아직 없어 덮이지 않고 X(5/20)가 채운다. 7월 증가 1 에서
    남은 보유가 남은 증가를 다 덮어 그 증가부터 신규를 붙이지 않는다. Y(5/25 — 창 [5/25, 6/24])는
    6월 증가를 X 가 채웠고 7월 증가(t 6/24)에는 붙을 수 있었다 — 까닭은 「7월부터 보유로
    덮임」(`skipped`)이지 7월 증가 때 1대가 안 돼서(`short`)가 아니다. Z(6/20)는 7월 W/D 첫날
    6/24 에 나가 `gone`, N2(7/1)는 창 안의 8월 증가가 0 이라 `no_growth` — 둘은 B1 로 붙지 않은
    호기가 아니다. W(5/21 — 창 [5/21, 6/20])는 멈춘 달 **앞** 6월 증가에만 붙을 수 있었고 그
    증가를 X 가 채웠다 — B1 로 붙지 않은 호기가 아니라 `filled` 다(「멈춘 달부터의 증가」 조건을
    못박는다, 2026-11-01 리뷰)."""
    months = _months(1, 2, 2)
    first = NewUnit("X", date(2027, 5, 20), 1.0)
    early = NewUnit("W", date(2027, 5, 21), 1.0)
    held = NewUnit("Y", JUNE_FIRST, 1.0)
    gone = NewUnit("Z", date(2027, 6, 20), 1.0, until=JULY_FIRST)
    late = NewUnit("N2", date(2027, 7, 1), 1.0)
    result = simulate_constraint(
        months, _conditions(months, held=LATE_HELD, new=True), (first, early, held, gone, late)
    )
    assert _split(result, 202706) == (1, 0, 0)
    assert _split(result, 202707) == (0, 1, 0)
    assert result.new_units_stopped_month == 202707 and not result.new_units_skipped
    assert [unit.name for unit in result.held_back_units] == ["Y"]
    assert result.held_back == ("Y",)
    assert result.ordinary_reason(held) == OrdinaryReason("skipped", months=(202707,))
    assert result.ordinary_reason(early) == OrdinaryReason("filled", months=(202706,))
    assert result.ordinary_reason(gone) == OrdinaryReason("gone", months=(202707,))
    assert result.ordinary_reason(late) == OrdinaryReason("no_growth")


def test_a_cover_from_the_first_growth_holds_back_only_units_that_could_attach() -> None:
    """첫 증가에서 덮이면 붙을 수 있던 N0(5/25)만 `skipped`(그 달 = 첫 증가)이고, 창 안에 증가가
    없던 6/20 신규는 `no_growth` 다 — 옛 판은 신규를 붙이지 않기만 하면 모두 「보유로 기간을 다
    덮어」 라고 적었다."""
    months = _months(2, 2)
    conditions = _conditions(months, held=(_held("H1"), _held("H2")), new=True)
    early = NewUnit("N0", JUNE_FIRST, 1.0)
    result = simulate_constraint(months, conditions, (early, LATE_UNIT))
    assert result.new_units_skipped
    assert result.ordinary_reason(early) == OrdinaryReason("skipped", months=(202706,))
    assert result.ordinary_reason(LATE_UNIT) == OrdinaryReason("no_growth")


def test_a_module_still_missing_after_the_cover_keeps_its_own_reason() -> None:
    """묶음 G(G-A 5/25 1.0 · G-B 6/30 0.5 — 창 [5/25, 6/24]). 6월 증가 2 에 G-A 1 이 붙고 개조 1,
    7월 증가 1 에서 남은 보유가 덮어 그 증가부터 신규를 붙이지 않는다. G-B 는 6월(t 5/25) · 7월(t
    6/24) 증가 모두 아직 오지 않아 붙을 수 없었다 — B1 로 붙지 않은 호기가 아니라 까닭은 오지 않은
    모듈이고, 멈춘 달(7월)의 증가도 그 까닭에 든다."""
    months = _months(2, 3, 3)
    bundle = _bundle("G", ("G-A", JUNE_FIRST, 1.0), ("G-B", date(2027, 6, 30), 0.5))
    result = simulate_constraint(months, _conditions(months, held=LATE_HELD, new=True), (bundle,))
    assert _split(result, 202706) == (1, 0, 1)
    assert _split(result, 202707) == (0, 1, 0)
    assert result.new_units_stopped_month == 202707
    assert result.held_back_units == ()
    assert result.ordinary_reason(bundle) == OrdinaryReason(
        "short", months=(202706, 202707), pending=("G-B",), attached=True
    )


# ------------------------------------------------------------------ B1 로 실제로 붙지 않은 호기
#
# 「붙일 수 있었나」(`_attachable`)만 보면 B1 이 없어도 붙지 않았을 호기(남는 몫의 내림이 0)가
# 「보유로 덮어」 를 받고 카드 한 줄이 섰다(2026-11-01 리뷰 — 무작위 합성 문제에서 한 줄이 선 셋에
# 하나꼴). 이제 멈춘 달부터 B1 없이 다시 돌려(같은 차례 · 내림 · 필요한 만큼만) 가른다.


def test_a_unit_that_could_not_make_one_unit_is_not_held_back() -> None:
    """리뷰의 보기 — 필요 6월 1 → 7월 2 → 8월 2, 목록에 없는 보유 1 + 고른 호기 셋, 신규 N0(5/05 ·
    0.5대 — 창 [5/05, 6/04]). 6월 증가에서 보유가 다 덮어 멈추지만, B1 이 없어도 N0 의 0.5대는 내림
    0 이라 6월 증가에 붙지 않는다 — 붙지 않은 호기가 아니고 까닭은 그 0.5대다(`short`)."""
    months = _months(1, 2, 2)
    held = (_held("H1"), _held("H2"), _held("H3"))
    unit = NewUnit("N0", date(2027, 5, 5), 0.5)
    result = simulate_constraint(months, _conditions(months, owned=1, held=held, new=True), (unit,))
    assert result.new_units_stopped_month == 202706 and result.new_units_skipped
    assert result.held_back_units == ()
    assert result.ordinary_reason(unit) == OrdinaryReason("short", months=(202706,), arrived=0.5)


def test_units_behind_one_that_would_have_filled_the_increase_are_held_back_too() -> None:
    """필요 6월 1, 보유 1 이 덮어 6월(첫 증가)에 멈춘다. B1 이 없었다면 A(5/20)가 6월 증가 1 을
    채웠다 — A 는 붙지 않은 호기다. B(5/21 · 1.0)와 C(5/22 · 0.5)도 그 증가에 붙을 수 있었지만 A 가
    필요한 만큼을 채웠을 것이다. 실제로는 그 증가를 보유가 덮었으니 둘의 까닭도 「보유로 덮음」 이다
    — 「먼저 들어온 신규가 채움」 은 일어나지 않은 일이다."""
    months = _months(1)
    units = (
        NewUnit("A", date(2027, 5, 20), 1.0),
        NewUnit("B", date(2027, 5, 21), 1.0),
        NewUnit("C", date(2027, 5, 22), 0.5),
    )
    result = simulate_constraint(months, _conditions(months, owned=1, new=True), units)
    assert result.new_units_skipped
    assert result.held_back == ("A", "B", "C")
    assert {result.ordinary_reason(unit).cause for unit in units} == {"skipped"}


def test_only_the_fraction_below_one_unit_keeps_its_own_reason() -> None:
    """필요 6월 2, 보유 2 가 덮어 6월에 멈춘다. B1 이 없었다면 6월 증가 2 에 A(1.0) + C(0.5) 의 내림
    1대만 붙었다 — A 가 받고 C 는 남은 0.5대가 1대가 되지 않는다. A 는 붙지 않은 호기(카드 한 줄이
    선다), C 는 `short` 다."""
    months = _months(2)
    first = NewUnit("A", date(2027, 5, 20), 1.0)
    half = NewUnit("C", date(2027, 5, 22), 0.5)
    result = simulate_constraint(months, _conditions(months, owned=2, new=True), (first, half))
    assert result.held_back == ("A",)
    assert result.ordinary_reason(first) == OrdinaryReason("skipped", months=(202706,))
    assert result.ordinary_reason(half) == OrdinaryReason("short", months=(202706,), arrived=0.5)


def test_held_back_units_follow_the_counterfactual_without_the_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """작은 무작위 문제 2000개(합성, 셋에 하나는 묶음) — 붙지 않은 호기는 B1 없이(늘 신규 먼저) 돈
    답과 맞댄다. 멈춘 달부터 그 답에서 몫을 받은 호기와, 그 달부터의 증가 가운데 그 답이 신규로 다
    채운 증가에 붙일 수 있던(창 · 들어옴 · 나가기 전 · 남는 몫) 호기를 합친 것이 `held_back` 이다.
    카드 한 줄은 그 답에서 몫을 받은 호기가 있을 때만 선다."""
    rng = random.Random(20261103)
    seen = {"received": 0, "behind": 0, "floor_only": 0}
    for case in range(2000):
        months, conditions, units = _random_case(rng)
        if case % 3 == 1:
            units = _with_bundles(rng, units)
        result = simulate_constraint(months, conditions, units)
        stopped = result.new_units_stopped_month
        if stopped is None:
            assert result.held_back == ()
            continue
        plain = _forced(monkeypatch, months, conditions, units, None)
        received = {item.unit for item in plain.assignments if item.month >= stopped}
        reach = timedelta(days=conditions.modification_days or 0)
        days = [
            wd_window(row.month, conditions.cutoff_days).first_day
            for row in plain.months
            if row.month >= stopped
            and row.new_increment > 0
            and row.new_increment == constraint_simulation._offered_to_new(row)
        ]
        behind: set[str] = set()
        for unit in result.new_units:
            if unit.name in received:
                continue
            for piece in unit.pieces:
                used = sum(
                    item.units
                    for item in result.assignments
                    if item.unit == unit.name and item.module == piece.name
                )
                if piece.units - used > 1e-9 and any(
                    unit.start <= day <= unit.start + reach
                    and piece.start is not None
                    and piece.start <= day
                    and (unit.until is None or day < unit.until)
                    for day in days
                ):
                    behind.add(unit.name)
        expected = received | behind
        assert set(result.held_back) == expected, (months, conditions, units)
        assert bool(received) == bool(result.held_back)
        seen["received"] += bool(received)
        seen["behind"] += bool(behind)
        seen["floor_only"] += any(
            result.ordinary_reason(unit).cause == "short"
            and result.ordinary_reason(unit).arrived > 0
            and max(result.ordinary_reason(unit).months) >= stopped
            for unit in result.ordinary_units
        )
    # 하네스가 세 갈래(받음 · 앞 차례가 채웠을 호기 · 1대가 안 돼 남는 호기)를 실제로 지나는지 —
    # 표본이 바뀌면 다시 센다.
    assert seen["received"] >= 100 and seen["behind"] >= 3 and seen["floor_only"] >= 20, seen
