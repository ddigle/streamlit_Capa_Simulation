# Purpose: 제약 시뮬레이션의 보유 「호기 고르기」·묶음 신규 첫 모듈 규칙·보유로 덮이면 신규를 붙이지
# 않는 규칙을 손계산과 맞댄다.

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
    UnitModule,
    simulate_constraint,
)

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
